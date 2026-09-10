"""Event Sink — 관측 이벤트를 받아 저장한다 (SRS PIPE-002, SIM-013, MEA-001~003).

시뮬레이터와 `Ecommerce_Service` 가 **같은 스키마로 이 Sink 에 기록**한다.
두 소스는 런타임 의존이 없고 공유하는 것은 스키마뿐이다.

세 가지를 지킨다.

1. **스키마 위반을 조용히 통과시키지 않는다.** `schema.validate_event()` 로
   검사하고, 거부한 레코드는 사유와 함께 남긴다.
2. **출처를 구분한다** (MEA-002). 실험 결과 산출에는 시뮬레이터 생성분만 쓴다.
3. **없는 필드를 0으로 채우지 않는다** (MEA-003). 커머스가 아직 주지 않는
   필드는 null 로 두고 결손을 기록하며, 그 필드에 의존하는 지표는
   **계산 불가로 표시**한다. 원가가 없는데 0으로 채우면 기여이익이 매출과
   같아져 잘못된 결론이 조용히 만들어진다.

저장 형식은 사용 가능한 것 중 최선을 고른다. pyarrow 가 설치되어 있으면
Parquet(SRS PIPE-002 권장), 없으면 gzip JSONL 로 쓴다. 의존성 매니페스트가
아직 없고 CI 에 설치 단계가 없으므로(ISO-005) **표준 라이브러리만으로도
동작해야 한다.**
"""

from __future__ import annotations

import csv
import gzip
import hashlib
import json
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Iterable, Iterator

from src.measurement import schema as sc

MANIFEST_NAME = "manifest.json"
REJECT_LOG_NAME = "rejected.jsonl"
DEFAULT_CHUNK_ROWS = 200_000


# ── 저장 형식 ───────────────────────────────────────────────────────────────

class SinkFormat(str, Enum):
    PARQUET = "parquet"
    JSONL_GZ = "jsonl.gz"
    JSONL = "jsonl"
    CSV = "csv"


def parquet_available() -> bool:
    try:
        import pyarrow  # noqa: F401
    except ImportError:
        return False
    return True


def resolve_format(requested: str | SinkFormat = "auto") -> SinkFormat:
    """`auto` 는 사용 가능한 것 중 최선을 고른다."""
    if requested == "auto":
        return SinkFormat.PARQUET if parquet_available() else SinkFormat.JSONL_GZ
    fmt = SinkFormat(requested)
    if fmt is SinkFormat.PARQUET and not parquet_available():
        raise RuntimeError(
            "parquet 형식을 요청했으나 pyarrow 가 없다. "
            "pyarrow 를 설치하거나 format='jsonl.gz' 를 사용한다."
        )
    return fmt


# ── 출처 구분 (MEA-002) ─────────────────────────────────────────────────────

class EventSource(str, Enum):
    SIMULATOR = "simulator"
    COMMERCE = "commerce"


def event_source(record: dict[str, object]) -> EventSource:
    """`simulator_version` · `random_seed` 가 모두 없으면 커머스 실측분이다."""
    if record.get("simulator_version") is None and record.get("random_seed") is None:
        return EventSource.COMMERCE
    return EventSource.SIMULATOR


# ── 결손 추적 (MEA-003) ─────────────────────────────────────────────────────

@dataclass
class FieldCoverage:
    """필드별 충족률. 값이 있는 레코드 수 / 해당 필드가 유효한 레코드 수."""

    present: int = 0
    applicable: int = 0

    @property
    def ratio(self) -> float:
        return 0.0 if self.applicable == 0 else self.present / self.applicable


@dataclass
class WriteResult:
    accepted: int = 0
    rejected: int = 0
    problems: list[str] = field(default_factory=list)

    def __bool__(self) -> bool:
        return self.rejected == 0


# ── Sink ────────────────────────────────────────────────────────────────────

class EventSink:
    """관측 이벤트를 파티션 파일로 append 한다.

        with EventSink(Path("data/raw")) as sink:
            sink.write_events(records)
        # __exit__ 에서 flush + manifest 기록

    이벤트는 `timestamp` 의 날짜로 파티션한다.
    `data/raw/events/date=2025-10-01/part-0000.jsonl.gz`
    """

    def __init__(
        self,
        root: Path | str,
        *,
        fmt: str | SinkFormat = "auto",
        chunk_rows: int = DEFAULT_CHUNK_ROWS,
        strict: bool = True,
    ) -> None:
        self.root = Path(root)
        self.format = resolve_format(fmt)
        self.chunk_rows = chunk_rows
        self.strict = strict
        """strict 면 스키마 위반 레코드를 거부한다. False 면 기록하되 표시한다."""

        self._buffer: list[dict[str, object]] = []
        self._rejected: list[dict[str, object]] = []
        self._source_counts: Counter[str] = Counter()
        self._event_type_counts: Counter[str] = Counter()
        self._coverage: dict[str, FieldCoverage] = {
            f.name: FieldCoverage() for f in sc.EVENT_FIELDS
        }
        self._rows_written = 0
        self._files: list[Path] = []
        self._part_index: Counter[str] = Counter()
        self.root.mkdir(parents=True, exist_ok=True)

    # ── 수집 ────────────────────────────────────────────────────────────
    def write_events(self, records: Iterable[dict[str, object]]) -> WriteResult:
        result = WriteResult()
        for record in records:
            problems = sc.validate_event(record)
            if problems:
                result.rejected += 1
                result.problems.extend(problems[:1])
                self._rejected.append({"record": record, "problems": problems})
                if self.strict:
                    continue
            self._observe(record)
            self._buffer.append(record)
            result.accepted += 1
            if len(self._buffer) >= self.chunk_rows:
                self.flush()
        return result

    def _observe(self, record: dict[str, object]) -> None:
        self._source_counts[event_source(record).value] += 1
        event_type = sc.EventType(record["event_type"])
        self._event_type_counts[event_type.value] += 1
        for name, coverage in self._coverage.items():
            if sc.requirement(event_type, name) is sc.Requirement.NOT_APPLICABLE:
                continue
            coverage.applicable += 1
            if record.get(name) is not None:
                coverage.present += 1

    # ── 저장 ────────────────────────────────────────────────────────────
    def flush(self) -> None:
        if not self._buffer:
            return
        by_date: dict[str, list[dict[str, object]]] = {}
        for record in self._buffer:
            by_date.setdefault(_partition_key(record["timestamp"]), []).append(record)
        for date_key, rows in sorted(by_date.items()):
            self._write_partition(date_key, rows)
        self._rows_written += len(self._buffer)
        self._buffer.clear()

    def _write_partition(self, date_key: str, rows: list[dict[str, object]]) -> None:
        directory = self.root / "events" / f"date={date_key}"
        directory.mkdir(parents=True, exist_ok=True)
        index = self._part_index[date_key]
        self._part_index[date_key] += 1
        path = directory / f"part-{index:04d}.{self.format.value}"
        _write_rows(path, rows, self.format)
        self._files.append(path)

    # ── 마감 ────────────────────────────────────────────────────────────
    def close(self) -> dict[str, object]:
        self.flush()
        if self._rejected:
            reject_path = self.root / REJECT_LOG_NAME
            with reject_path.open("w", encoding="utf-8") as handle:
                for entry in self._rejected:
                    handle.write(json.dumps(entry, ensure_ascii=False, default=str) + "\n")
        manifest = self.manifest()
        (self.root / MANIFEST_NAME).write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        return manifest

    def __enter__(self) -> EventSink:
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.close()

    # ── 리포트 ──────────────────────────────────────────────────────────
    def manifest(self) -> dict[str, object]:
        """무엇이 들어왔고 무엇이 비어 있으며 어떤 지표를 못 쓰는지."""
        coverage = {
            name: round(item.ratio, 4)
            for name, item in sorted(self._coverage.items())
            if item.applicable > 0
        }
        return {
            "schema_version": sc.SCHEMA_VERSION,
            "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "format": self.format.value,
            "partition": "date",
            "timezone": sc.TIMEZONE,
            "rows": self._rows_written,
            "rejected": len(self._rejected),
            "files": [str(p.relative_to(self.root)) for p in self._files],
            "sha256": self._digest(),
            "sources": dict(self._source_counts),
            "event_type_counts": dict(sorted(self._event_type_counts.items())),
            "field_coverage": coverage,
            "missing_fields": sorted(
                name for name, item in self._coverage.items()
                if item.applicable > 0 and item.present == 0
            ),
            "unavailable_metrics": self.unavailable_metrics(),
        }

    def unavailable_metrics(self) -> list[str]:
        """근거 이벤트가 하나도 들어오지 않아 계산할 수 없는 Observable 지표.

        MEA-003 — 추정값을 만들어내지 않고 계산 불가로 표시한다.
        """
        return sorted(
            metric
            for metric, sources in sc.OBSERVABLE_METRIC_SOURCES.items()
            if not any(self._event_type_counts.get(s, 0) for s in sources)
        )

    def _digest(self) -> str:
        digest = hashlib.sha256()
        for path in sorted(self._files):
            digest.update(path.name.encode())
            digest.update(path.read_bytes())
        return digest.hexdigest()


# ── 파일 입출력 ─────────────────────────────────────────────────────────────

_COLUMNS = [f.name for f in sc.EVENT_FIELDS]


def _partition_key(timestamp: object) -> str:
    """ISO 8601 문자열 또는 datetime 에서 `YYYY-MM-DD` 를 뽑는다."""
    if isinstance(timestamp, datetime):
        return timestamp.date().isoformat()
    text = str(timestamp)
    try:
        return datetime.fromisoformat(text).date().isoformat()
    except ValueError as error:
        raise ValueError(f"timestamp 를 해석할 수 없다: {timestamp!r}") from error


def _write_rows(path: Path, rows: list[dict[str, object]], fmt: SinkFormat) -> None:
    if fmt is SinkFormat.PARQUET:
        _write_parquet(path, rows)
    elif fmt is SinkFormat.CSV:
        with path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=_COLUMNS, extrasaction="ignore")
            writer.writeheader()
            writer.writerows(rows)
    else:
        opener = gzip.open if fmt is SinkFormat.JSONL_GZ else open
        with opener(path, "wt", encoding="utf-8") as handle:  # type: ignore[operator]
            for row in rows:
                handle.write(json.dumps(row, ensure_ascii=False, default=str) + "\n")


def _write_parquet(path: Path, rows: list[dict[str, object]]) -> None:
    import pyarrow as pa
    import pyarrow.parquet as pq

    table = pa.table({name: [row.get(name) for row in rows] for name in _COLUMNS})
    pq.write_table(table, path, compression="snappy")


def read_events(root: Path | str) -> Iterator[dict[str, object]]:
    """저장된 이벤트를 되읽는다. 검증과 소규모 분석용이다."""
    root = Path(root)
    for path in sorted((root / "events").rglob("part-*")):
        if path.suffix == ".gz":
            with gzip.open(path, "rt", encoding="utf-8") as handle:
                yield from (json.loads(line) for line in handle if line.strip())
        elif path.suffix == ".jsonl":
            with path.open(encoding="utf-8") as handle:
                yield from (json.loads(line) for line in handle if line.strip())
        elif path.suffix == ".csv":
            with path.open(encoding="utf-8", newline="") as handle:
                yield from csv.DictReader(handle)
        elif path.suffix == ".parquet":
            import pyarrow.parquet as pq

            yield from pq.read_table(path).to_pylist()
