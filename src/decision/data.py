"""측정 계층 Sink 출력 → 학습용 이벤트 DataFrame (스프린트 1, 이슈 #144).

읽는 것은 **공개 계약뿐**이다 — `src/measurement/sink.py` 가 쓰는 날짜 파티션
(`<root>/events/date=YYYY-MM-DD/part-NNNN.{parquet,jsonl.gz,jsonl,csv}`)과
`src/measurement/schema.py` 의 `EVENT_FIELDS` 22 개 컬럼. 시뮬레이터 내부·숨김 영역은
이 모듈이 모른다.

규율:
  - 결손을 0 으로 채우지 않는다. 정수 컬럼은 nullable `Int64` 로 두고 빈 값은 `<NA>` 다.
  - timestamp 는 tz-aware(`Asia/Seoul`)로 돌려준다. 오프셋이 없는 값은 순간을 특정할 수
    없으므로 추측하지 않고 `ValueError` 를 던진다.
  - 같은 `event_id` 가 두 번 나오면 첫 행만 남기고 그 수를 `df.attrs` 에 남긴다
    (조용히 버리지 않는다).

의존성: pandas (pyarrow 는 parquet 파티션이 있을 때만). 의존성 없는 CI 잡에서는 이
모듈을 import 하는 테스트가 skip 된다.
"""

from __future__ import annotations

import gzip
import json
import hashlib
import re
from collections.abc import Mapping
from pathlib import Path

import pandas as pd

from src.measurement.schema import EVENT_FIELDS, TIMEZONE

EVENT_COLUMNS: list[str] = [spec.name for spec in EVENT_FIELDS]
INT_COLUMNS: list[str] = [spec.name for spec in EVENT_FIELDS if spec.dtype == "int"]
STRING_COLUMNS: list[str] = [
    spec.name for spec in EVENT_FIELDS if spec.dtype not in ("int", "datetime[ms]")
]

_SUFFIXES = (".parquet", ".gz", ".jsonl", ".csv")


def verify_event_run(raw_root, run_id, known_parent_runs=(), *, history_evidence=None) -> dict:
    """실험용 simulator 단일 출처 실행의 파일·바이트·중복 제거 전 행 수를 대조한다 (#179).

    외부 부모는 검증된 history의 머리와 정확히 같아야 한다. ID 목록만으로는 승인하지 않는다.
    조상 실행의 거부 수는 감사에 보존하되 새 Feature/S1 차단 정책을 정하지 않는다.
    분기 루트 단독의 계보 결손을
    무시하지도, 부모가 다른 루트에 있다는 이유만으로 정상 분기를 거부하지도 않는다.
    """
    from src.measurement import sink

    root = Path(raw_root).resolve()
    audit = {"status": "not_run", "run_id": run_id, "root": str(root),
             "method": "file-digest-pre-dedup-rows-v1", "reason": None,
             "chain_rejected_total": None, "ancestor_rejected_total": None,
             "ancestor_rejection_policy": "audit_only_no_new_feature_or_s1_gate"}
    try:
        if not isinstance(run_id, str) or not run_id.strip():
            raise ValueError("검증할 실행 ID가 없다")
        known, inherited, history_head = set(known_parent_runs), {}, None
        if history_evidence is not None:
            audit["history_link_status"] = "not_run"
            if not isinstance(history_evidence, Mapping) or history_evidence.get("status") != "ok":
                raise ValueError("검증된 history 읽기 근거가 없다")
            ids = history_evidence.get("verified_run_ids")
            history_head = history_evidence.get("run_id")
            inherited = history_evidence.get("run_rejections")
            if (not isinstance(ids, list) or any(not isinstance(i, str) or not i for i in ids)
                    or len(ids) != len(set(ids)) or not isinstance(history_head, str) or history_head not in ids
                    or not isinstance(inherited, Mapping) or set(inherited) != set(ids)
                    or any(type(v) is not int or v < 0 for v in inherited.values())):
                raise ValueError("history 머리·실행별 거부 수 근거가 없거나 잘못됐다")
            if known and known != set(ids):
                raise ValueError("history 실행 목록과 별도 부모 목록이 다르다")
            known = set(ids)
            audit["history_head_run_id"] = history_head
        elif known:
            raise ValueError("실행 ID 목록만으로 history 머리·거부 수를 검증할 수 없다")
        else:
            audit["history_link_status"] = "not_applicable"
        records = sink.run_records(root)
        by_id = {}
        for record in records:
            if not isinstance(record, Mapping) or "unreadable" in record:
                raise ValueError("실행 기록이 dict가 아니거나 읽을 수 없다")
            if not {"run_id", "parent_run_id", "rows", "rejected", "files", "sha256", "sources"} <= record.keys():
                raise ValueError("실행 기록의 필수 필드가 빠졌다")
            rid = record.get("run_id")
            if not isinstance(rid, str) or rid in by_id:
                raise ValueError("실행 ID가 없거나 중복이다")
            by_id[rid] = record
        if run_id not in by_id:
            raise ValueError("해당 실행 기록이 없다")
        chain, cursor, external = [], run_id, None
        while cursor is not None:
            if cursor in chain:
                raise ValueError("실행 부모 사슬이 순환한다")
            if cursor not in by_id:
                if cursor not in known:
                    raise ValueError("외부 부모의 검증된 history가 없다")
                external = cursor
                break
            chain.append(cursor)
            parent = by_id[cursor].get("parent_run_id")
            if parent is not None and (not isinstance(parent, str) or not parent):
                raise ValueError("부모 실행 ID 형식이 잘못됐다")
            cursor = parent
        if set(chain) != set(by_id):
            raise ValueError("루트에 현재 세계 사슬 밖 실행이 섞였다")
        if history_evidence is not None and external != history_head:
            raise ValueError("HISTORY_PARENT_UNRESOLVED: 분기 외부 부모가 history 머리와 일치하지 않는다")
        if set(chain) & set(inherited):
            raise ValueError("분기와 history가 같은 실행 ID를 중복 주장한다")
        claimed, fingerprints = set(), {}
        run_rejections = dict(inherited)
        for rid in chain:
            record = by_id[rid]
            rows, rejected, files, expected = (record.get(k) for k in ("rows", "rejected", "files", "sha256"))
            if type(rows) is not int or rows < 0 or type(rejected) is not int or rejected < 0:
                raise ValueError("원시 행 수·거부 수는 0 이상의 정수여야 한다")
            run_rejections[rid] = rejected
            sources = record["sources"]
            if (not isinstance(sources, Mapping) or any(type(v) is not int or v < 0 for v in sources.values())
                    or sum(sources.values()) != rows or any(k != "simulator" and v for k, v in sources.items())):
                raise ValueError("실험 입력의 출처 근거가 simulator 단일 출처가 아니다")
            if (not isinstance(files, list) or any(not isinstance(x, str) for x in files)
                    or len(files) != len(set(files)) or not isinstance(expected, str)
                    or not re.fullmatch(r"[0-9a-fA-F]{64}", expected)):
                raise ValueError("필수 파일 목록·다이제스트가 없거나 잘못됐다")
            paths = []
            for name in files:
                if not re.fullmatch(r"events/date=\d{4}-\d{2}-\d{2}/part-\d+\.(?:parquet|jsonl\.gz|jsonl|csv)", name):
                    raise ValueError("공개 이벤트 파티션 밖 파일 주장")
                path = root / name
                if not path.resolve().is_relative_to(root / "events") or not path.is_file() or name in claimed:
                    raise ValueError("파일 부재·루트 이탈·중복 소유 주장")
                claimed.add(name)
                paths.append(path)
            digest, raw_rows = hashlib.sha256(), 0
            for path in sorted(paths):
                before = path.stat()
                digest.update(path.name.encode())  # EventSink 실행 다이제스트 계약과 같은 순서
                with path.open("rb") as stream:
                    for block in iter(lambda: stream.read(1024 * 1024), b""):
                        digest.update(block)
                raw_rows += len(_read_part(path))  # 아직 필터링·event_id 중복 제거하지 않는다
                after = path.stat()
                if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
                    raise ValueError("검증 도중 파일이 바뀌었다")
                fingerprints[path.relative_to(root).as_posix()] = [after.st_size, after.st_mtime_ns]
            if raw_rows != rows or digest.hexdigest() != expected.lower():
                raise ValueError("실행의 원시 행 수·파일 내용 주장이 실제와 다르다")
            if rid == run_id:
                audit.update(rejected=rejected, raw_rows=raw_rows, n_files=len(files))
        disk = {p.relative_to(root).as_posix() for p in (root / "events").rglob("part-*") if p.is_file()}
        if disk != claimed:
            raise ValueError("실행이 주장하지 않은 파티션이 있거나 주장 파일이 빠졌다")
        audit.update(status="ok", verified_run_ids=sorted(run_rejections), run_rejections=run_rejections,
                     chain_rejected_total=sum(run_rejections.values()),
                     ancestor_rejected_total=sum(v for rid, v in run_rejections.items() if rid != run_id),
                     history_link_status="ok" if history_evidence is not None else "not_applicable",
                     external_parent_run_id=external, fingerprints=fingerprints)
    except Exception as error:  # 근거 실패는 0이 아니라 not_run이다. 호출자가 해당 단계만 중단한다.
        audit["reason"] = f"{type(error).__name__}: {error}"
    return audit


def _events_dir(raw_root: Path) -> Path:
    """Sink root(`<root>/events/…`) 와 events 디렉터리 자체를 둘 다 받는다."""
    if (raw_root / "events").is_dir():
        return raw_root / "events"
    if any(raw_root.glob("date=*")):
        return raw_root
    raise FileNotFoundError(
        f"이벤트 파티션을 찾지 못했다: {raw_root} (기대: <root>/events/date=YYYY-MM-DD/part-*)"
    )


def _read_part(path: Path) -> pd.DataFrame:
    if path.suffix == ".parquet":
        return pd.read_parquet(path)
    if path.suffix == ".csv":
        return pd.read_csv(path, dtype=str, keep_default_na=False, na_values=[""])
    opener = gzip.open if path.suffix == ".gz" else open
    with opener(path, "rt", encoding="utf-8") as handle:  # type: ignore[operator]
        rows = [json.loads(line) for line in handle if line.strip()]
    return pd.DataFrame.from_records(rows)


def _coerce(frame: pd.DataFrame) -> pd.DataFrame:
    frame = frame.reindex(columns=EVENT_COLUMNS)
    for name in STRING_COLUMNS:
        # object 로 먼저 바꾼다 — 전부 결손인 컬럼은 float(NaN) 로 들어와 None 이
        # 다시 NaN 이 되고 str(nan) == "nan" 이 값처럼 보이게 된다.
        column = frame[name].astype(object)
        frame[name] = column.where(column.notna(), None).map(
            lambda value: None if value is None else str(value)
        )
    for name in INT_COLUMNS:
        frame[name] = pd.to_numeric(frame[name], errors="raise").astype("Int64")
    raw = frame["timestamp"].astype("string")
    naive = raw.notna() & ~raw.str.contains(r"(?:Z|[+-]\d{2}:?\d{2})$", regex=True, na=False)
    if naive.any():
        sample = raw[naive].iloc[0]
        raise ValueError(f"timestamp 에 UTC 오프셋이 없다 (순간 특정 불가): {sample!r}")
    frame["timestamp"] = pd.to_datetime(raw, utc=True, format="ISO8601").dt.tz_convert(TIMEZONE)
    return frame


def load_events(raw_root, *, allow_verified_empty: bool = False) -> pd.DataFrame:
    """Sink 출력 루트를 읽어 `EVENT_FIELDS` 22 컬럼 DataFrame 으로 돌려준다.

    반환 frame 은 `(timestamp, event_id)` 로 정렬되고 RangeIndex 를 가진다.
    `attrs` 에 `source_files`(읽은 파트 수)·`duplicate_event_ids`(제거한 중복 수)를 남긴다.
    """
    # 호출자가 실행 기록·빈 파일 목록·0행을 검증한 경우만 허용한다. 기본 경로는 부재를 오류로 낸다.
    events_dir = (Path(raw_root) / "events" if allow_verified_empty and not (Path(raw_root) / "events").exists()
                  else _events_dir(Path(raw_root)))
    parts = sorted(
        path for path in events_dir.rglob("part-*") if path.suffix in _SUFFIXES
    )
    frames = [_read_part(path) for path in parts]
    frames = [frame for frame in frames if len(frame)]
    if frames:
        frame = _coerce(pd.concat(frames, ignore_index=True, sort=False))
    else:
        frame = _coerce(pd.DataFrame(columns=EVENT_COLUMNS))
    before = len(frame)
    frame = frame.drop_duplicates(subset="event_id", keep="first")
    frame = frame.sort_values(["timestamp", "event_id"], kind="mergesort").reset_index(drop=True)
    frame.attrs["source_files"] = len(parts)
    frame.attrs["duplicate_event_ids"] = before - len(frame)
    return frame
