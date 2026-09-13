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
from datetime import datetime, timedelta, timezone
from enum import Enum
from pathlib import Path
from typing import Iterable, Iterator

from src.measurement import schema as sc

MANIFEST_NAME = "manifest.json"
REJECT_LOG_NAME = "rejected.jsonl"
DEFAULT_CHUNK_ROWS = 200_000

KST = timezone(timedelta(hours=9), "KST")
"""`schema.TIMEZONE` ("Asia/Seoul") 을 고정 오프셋으로 표현한 것.

`zoneinfo.ZoneInfo("Asia/Seoul")` 대신 고정 오프셋을 쓴다. 한국은 1988 년 이후
서머타임이 없으므로 우리가 다루는 모든 시각에서 둘은 같은 값을 내고, 고정 오프셋은
`tzdata` 패키지가 없는 환경(일부 Windows·슬림 컨테이너)에서도 동작한다 — CI 에
설치 단계가 없으므로(ISO-005) 그게 중요하다."""

# ponytail: fixed +09:00 offset ignores pre-1988 Korean DST and any future rule change;
# swap to zoneinfo.ZoneInfo("Asia/Seoul") and add tzdata to requirements.txt if an event
# timestamp before 1988-10-09 ever needs ingesting, or if Korea reintroduces DST.


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

    이벤트는 **KST 기준** `timestamp` 의 날짜로 파티션한다.
    `data/raw/events/date=2025-10-01/part-0000.jsonl.gz`

    **append 는 인스턴스를 넘어서도 성립한다.** 같은 root 에 새 `EventSink` 를 만들어
    다시 기록하면 파트 번호가 디렉터리의 현재 상태에서 이어진다 — 시뮬레이터가
    `advance()` 를 반복하며 매번 새 Sink 로 기록하기 때문이다 (SIM-012 분할 불변성).
    `_next_part_index()` 참조.
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
        """strict 면 스키마 위반 레코드를 거부한다. False 면 기록하되 표시한다.

        `strict=False` 의 정확한 뜻은 **"수집이 죽지 않는다"** 이지 "무효 데이터를 전부
        저장한다" 가 아니다. 두 층으로 갈린다:

          - `event_type` 이 유효하면 → 위반을 보고하면서 저장한다 (관용)
          - `event_type` 이 무효·부재면 → 저장하지 않는다. 커버리지 행도 요구사항
            매트릭스도 만들 수 없으므로 저장할 의미가 없다. `_is_observable()` 참조

        관용 모드에서 통과시킨 레코드는 `WriteResult` 의 `accepted` 와 `rejected` **양쪽**
        에 계상된다. 의도된 것이다 — "받아들였다"와 "문제가 있었다"는 서로 배타적이지
        않고, `accepted` 를 줄이면 저장된 행 수와 어긋난다."""

        self._buffer: list[dict[str, object]] = []
        self._rejected: list[dict[str, object]] = []
        self._source_counts: Counter[str] = Counter()
        self._event_type_counts: Counter[str] = Counter()
        self._coverage: dict[str, FieldCoverage] = {
            f.name: FieldCoverage() for f in sc.EVENT_FIELDS
        }
        self._rows_written = 0
        self._files: list[Path] = []
        self._part_index: dict[str, int] = {}
        """date_key → 다음에 쓸 파트 번호.

        `Counter` 가 아니라 `dict` 다. `Counter` 는 없는 키에 0 을 돌려주므로
        "아직 디렉터리를 안 봤다"와 "0 번부터 쓰면 된다"를 구분할 수 없고, 그 구분이
        사라지는 것이 바로 D1-1(파티션 덮어쓰기)이었다. `in` 검사가 필요하다."""
        self.root.mkdir(parents=True, exist_ok=True)

    # ── 수집 ────────────────────────────────────────────────────────────
    def write_events(self, records: Iterable[dict[str, object]]) -> WriteResult:
        result = WriteResult()
        for record in records:
            problems = sc.validate_event(record)
            if problems:
                result.rejected += 1
                # 레코드당 첫 문제만 요약에 담는다. 전체 목록은 rejected.jsonl 에 있다.
                result.problems.extend(problems[:1])
                self._rejected.append({"record": record, "problems": problems})
                # strict 면 무엇이든 거부한다. 관용 모드에서도 event_type 이 없거나
                # 무효면 거부한다 — 그것 없이는 _observe 도 파티션도 불가능하다.
                if self.strict or not _is_observable(record):
                    continue
            self._observe(record)
            self._buffer.append(record)
            result.accepted += 1
            if len(self._buffer) >= self.chunk_rows:
                self.flush()
        return result

    def _observe(self, record: dict[str, object]) -> None:
        """`_is_observable(record)` 가 참인 레코드만 받는다 — 호출부가 보장한다.

        `record.get("event_type", "unknown")` 같은 방어를 여기 넣지 않는다. 그러면
        커버리지 집계에 스키마에 없는 가짜 이벤트 종류가 생기고, 거부됐어야 할
        레코드가 통계에 섞인 채 조용히 도는 쪽이 크래시보다 나쁘다.
        """
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
        """버퍼를 KST 날짜별 파티션으로 내린다.

        저장되는 `timestamp` 와 파티션 날짜를 **한 번의 파싱에서** 함께 만든다
        (`_normalize_timestamp`). 따로 계산하면 한쪽만 KST 로 바뀌어 파티션은
        `date=2025-10-02` 인데 저장된 값은 `…23:30:00Z` 가 되고, 되읽어 날짜를 다시
        뽑으면 10-01 이 나온다. 그 어긋남이 `DQ-06` 을 자기 저장물에서 실패시킨다.
        """
        if not self._buffer:
            return
        by_date: dict[str, list[dict[str, object]]] = {}
        for record in self._buffer:
            kst_text, date_key = _normalize_timestamp(record["timestamp"])
            if kst_text != record["timestamp"]:
                # 호출자의 dict 를 제자리에서 고치지 않는다. 값이 실제로 바뀔 때만
                # 복사하므로 이미 KST 인 입력(대다수)에는 복사 비용이 없다.
                record = {**record, "timestamp": kst_text}
            by_date.setdefault(date_key, []).append(record)
        for date_key, rows in sorted(by_date.items()):
            self._write_partition(date_key, rows)
        self._rows_written += len(self._buffer)
        self._buffer.clear()

    def _write_partition(self, date_key: str, rows: list[dict[str, object]]) -> None:
        directory = self.root / "events" / f"date={date_key}"
        directory.mkdir(parents=True, exist_ok=True)
        if date_key not in self._part_index:
            # 이 인스턴스가 이 날짜를 처음 쓸 때만 디렉터리를 본다. 이후로는 캐시를
            # 증가시키므로 스캔은 (인스턴스 × 날짜) 당 1 회다.
            self._part_index[date_key] = _next_part_index(directory)
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
            # KST. 이전에는 UTC 였고, 그것은 manifest 가 같은 파일에서 선언하는
            # "timezone": "Asia/Seoul" 과 어긋나는 자기 규약 위반이었다.
            "created_at": datetime.now(KST).isoformat(timespec="seconds"),
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


def _is_observable(record: dict[str, object]) -> bool:
    """`_observe()` 와 파티션 계산이 가능한 레코드인가.

    `event_type` 이 `EventType` 16종 중 하나여야 한다. 이것이 없으면 요구사항
    매트릭스(`sc.requirement`)를 조회할 수 없어 커버리지 행을 만들 수 없고, 저장해도
    아무 지표에 기여하지 못한다. 그래서 관용 모드에서도 저장하지 않는다.

        >>> _is_observable({"event_type": "purchase"})
        True
        >>> _is_observable({"event_type": "teleport"}), _is_observable({})
        (False, False)
    """
    try:
        sc.EventType(record.get("event_type"))
    except ValueError:
        return False
    return True


def _next_part_index(directory: Path) -> int:
    """디렉터리에 있는 가장 큰 파트 번호 + 1. 비어 있으면 0.

    **개수가 아니라 최댓값**을 본다. 중간 파일이 지워졌으면 개수는 번호와 달라지고,
    개수를 쓰면 살아 있는 파일을 덮어쓴다.

    확장자는 무시하고 번호만 읽는다 — 한 디렉터리에 `part-0000.jsonl.gz` 와
    `part-0000.parquet` 가 섞이면(pyarrow 유무가 다른 실행) 번호가 충돌하기 때문이다.

        part-0000.jsonl.gz · part-0002.parquet  →  3
        (빈 디렉터리)                            →  0
    """
    # ponytail: linear glob over one partition's parts, run once per (instance, date);
    # at the 20k x 30d bench this is 30 scans of <=1 file each and invisible in the
    # 78.7s total. If a partition ever holds thousands of parts (streaming ingest, or
    # chunk_rows lowered a lot) and bench_sink.py time regresses past 2x baseline,
    # persist the next index in manifest.json instead of re-deriving it from the dir.
    highest = -1
    for path in directory.glob("part-*"):
        number = path.name.split(".", 1)[0].removeprefix("part-")
        if number.isdigit():
            highest = max(highest, int(number))
    return highest + 1


def _normalize_timestamp(timestamp: object) -> tuple[str, str]:
    """`(KST 표기 문자열, 파티션 날짜)` 를 **한 번의 파싱**에서 만든다.

    이 함수가 하나인 이유가 D1-3 수정의 요점이다. 저장 값과 파티션 날짜를 따로
    계산하면 둘이 어긋날 수 있고, 어긋나는 순간 되읽기 정합성과 `DQ-06` 이 깨진다.
    한 튜플로 돌려주면 어긋날 자리가 없다.

        "2025-10-01T23:30:00.000Z"       → ("2025-10-02T08:30:00.000+09:00", "2025-10-02")
        "2025-10-01T09:00:00.000+09:00"  → ("2025-10-01T09:00:00.000+09:00", "2025-10-01")

    `ValueError` 를 던지는 경우가 둘 있고 **둘 다 조용히 넘기지 않는다**:
      - 파싱 불가 (`"어제"`) — `validate_event()` 가 일부러 통과시킨 것이 여기서 걸린다
      - 오프셋 없음 — 보통 `validate_event()` 가 먼저 거부하지만, `strict=False` 로
        통과한 경우와 naive `datetime` 객체가 직접 들어온 경우가 남는다
    """
    if isinstance(timestamp, datetime):
        moment = timestamp
    else:
        try:
            moment = datetime.fromisoformat(str(timestamp))
        except ValueError as error:
            raise ValueError(f"timestamp 를 해석할 수 없다: {timestamp!r}") from error
    if moment.tzinfo is None:
        raise ValueError(
            f"timestamp 에 UTC 오프셋이 없어 순간을 특정할 수 없다: {timestamp!r}"
        )
    moment = moment.astimezone(KST)
    return moment.isoformat(timespec=_ISOFORMAT_TIMESPEC), moment.date().isoformat()


_ISOFORMAT_TIMESPEC = "milliseconds"
"""`sc.TIMESTAMP_PRECISION` 이 선언한 정밀도를 `isoformat()` 인자로 옮긴 것.

`datetime.isoformat()` 은 이 문자열을 그대로 받는다. 정밀도를 고정하지 않으면 마이크로초가
0 인 시각만 `.000` 이 빠져 같은 데이터가 다른 바이트를 내고 `NFR-001` 대조가 흔들린다."""

assert _ISOFORMAT_TIMESPEC == sc.TIMESTAMP_PRECISION, (
    "저장 정밀도가 schema.TIMESTAMP_PRECISION 선언과 어긋난다 — "
    f"{_ISOFORMAT_TIMESPEC!r} vs {sc.TIMESTAMP_PRECISION!r}"
)


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
