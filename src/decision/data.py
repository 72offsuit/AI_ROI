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

from pathlib import Path

import pandas as pd

from src.measurement.schema import EVENT_FIELDS, TIMEZONE
from src.decision.observation_contract import read_event_part as _read_part, verify_event_run
from src.decision.return_visit import INPUT_METADATA, input_metadata

EVENT_COLUMNS: list[str] = [spec.name for spec in EVENT_FIELDS]
INT_COLUMNS: list[str] = [spec.name for spec in EVENT_FIELDS if spec.dtype == "int"]
STRING_COLUMNS: list[str] = [
    spec.name for spec in EVENT_FIELDS if spec.dtype not in ("int", "datetime[ms]")
]

_SUFFIXES = (".parquet", ".gz", ".jsonl", ".csv")


def _events_dir(raw_root: Path) -> Path:
    """Sink root(`<root>/events/…`) 와 events 디렉터리 자체를 둘 다 받는다."""
    if (raw_root / "events").is_dir():
        return raw_root / "events"
    if any(raw_root.glob("date=*")):
        return raw_root
    raise FileNotFoundError(
        f"이벤트 파티션을 찾지 못했다: {raw_root} (기대: <root>/events/date=YYYY-MM-DD/part-*)"
    )


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
    frame.attrs[INPUT_METADATA] = input_metadata(frame)
    return frame
