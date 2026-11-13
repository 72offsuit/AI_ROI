"""파일 기반 Feature Store — SRS FS-001 · FS-002 (#214).

한 실행이 계산한 Feature 테이블(예: t1 학습용 · t2 점수용)과 라벨을 ``<root>/<name>.parquet`` 로 쓰고,
``<root>/manifest.json`` 에 모양 · 지문 · 테이블 속성(attrs)을 남긴다. 보통 ``data/processed/<run_id>/``
다(``data/`` 는 .gitignore). SRS FS-001 은 MVP 로 파일 기반을 권장한다.

## FS-002 — 행마다 붙는 메타데이터
``customer_id · feature_version · feature_cutoff_time · generated_at``.
  - ``feature_cutoff_time`` = Feature 를 잰 기준 시각 T0. 이 시각 **미만** 의 이벤트만 쓴다
    (`sprint_table` 의 ``timestamp < T0`` · D1 ``[…, T0)``). manifest 의 ``cutoff_semantics`` 에도 적는다.
  - 라벨 테이블은 Feature 가 아니므로 같은 메타 열을 붙이되 ``kind = "label"`` 로 구분한다.

## 다시 읽기
``read_features`` 는 메타 열을 떼고 ``customer_id`` 를 인덱스로 돌려놓고, attrs 를 manifest 에서 되살린다.
`sprint_table.model_columns` 가 attrs 의 재방문 입력 메타데이터(#256)를 확인하므로 attrs 가 빠지면 모델
입력으로 쓸 수 없다 — 그래서 함께 저장한다. 시각 값은 문자열로 돌아온다(JSON).

결손은 NaN 그대로 쓴다 — 0 으로 채우지 않는다. 같은 이름이 이미 있으면 덮어쓰지 않는다.
"""

from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Mapping

STORE_FORMAT = "feature-store-v1"
MANIFEST = "manifest.json"
META_COLUMNS = ("customer_id", "feature_version", "feature_cutoff_time", "generated_at")
CUTOFF_SEMANTICS = "feature_cutoff_time 미만(<)의 이벤트만 쓴다 — sprint_table timestamp < T0, D1 [·, T0)"
KST = timezone(timedelta(hours=9), "KST")


class FeatureStoreError(Exception):
    """저장 · 읽기를 할 수 없다 — 사유를 그대로 올린다."""


def _json_default(value: Any) -> Any:
    item = getattr(value, "item", None)
    if callable(item):
        try:
            return item()
        except (TypeError, ValueError):
            pass
    isoformat = getattr(value, "isoformat", None)
    if callable(isoformat):
        return isoformat()
    if isinstance(value, (set, frozenset, tuple)):
        return list(value)
    return str(value)


def _attrs_json(attrs: Mapping[str, Any]) -> dict[str, Any]:
    return json.loads(json.dumps(dict(attrs), ensure_ascii=False, default=_json_default))


def _read_manifest(root: Path) -> dict[str, Any]:
    path = root / MANIFEST
    if not path.exists():
        return {"store_format": STORE_FORMAT, "tables": {}}
    manifest = json.loads(path.read_text(encoding="utf-8"))
    if manifest.get("store_format") != STORE_FORMAT:
        raise FeatureStoreError(f"저장 형식이 다르다: {manifest.get('store_format')!r} (기대 {STORE_FORMAT!r})")
    return manifest


def _write_manifest(root: Path, manifest: Mapping[str, Any]) -> None:
    tmp = root / (MANIFEST + ".tmp")
    tmp.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(tmp, root / MANIFEST)


def write_table(root: Path, name: str, frame: Any, *, feature_version: str | None, cutoff_time: Any,
                kind: str = "feature", generated_at: str | None = None,
                extra: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """Feature(또는 라벨) 테이블 하나를 parquet 로 쓴다. 인덱스가 customer_id 다."""
    import pandas as pd

    from src.decision.model_store import frame_digest

    if not isinstance(frame, pd.DataFrame):
        raise FeatureStoreError(f"{name}: DataFrame 이 아니다 ({type(frame).__name__})")
    if frame.index.has_duplicates:
        raise FeatureStoreError(f"{name}: customer_id 가 중복된다")
    clash = [c for c in META_COLUMNS if c in frame.columns]
    if clash:
        raise FeatureStoreError(f"{name}: 메타 열 이름과 겹치는 열이 있다 {clash}")
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    path = root / f"{name}.parquet"
    manifest = _read_manifest(root)
    if path.exists() or name in manifest["tables"]:
        raise FeatureStoreError(f"{path} 가 이미 있다 — 덮어쓰지 않는다")

    generated_at = generated_at or datetime.now(KST).isoformat(timespec="seconds")
    cutoff = pd.Timestamp(cutoff_time)
    table = frame.copy()
    table.attrs = {}
    table.insert(0, "customer_id", frame.index.astype(str))
    table.insert(1, "feature_version", feature_version)
    table.insert(2, "feature_cutoff_time", cutoff)
    table.insert(3, "generated_at", generated_at)
    table = table.reset_index(drop=True)
    table.to_parquet(path, index=False)

    record = {
        "file": path.name,
        "kind": kind,
        "rows": int(len(frame)),
        "columns": [str(c) for c in frame.columns],
        "dtypes": {str(c): str(t) for c, t in frame.dtypes.items()},
        "index_name": frame.index.name,
        "frame_sha256": frame_digest(frame),
        "file_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "feature_version": feature_version,
        "feature_cutoff_time": cutoff.isoformat(),
        "cutoff_semantics": CUTOFF_SEMANTICS,
        "generated_at": generated_at,
        "attrs": _attrs_json(frame.attrs),
        **{k: v for k, v in (extra or {}).items()},
    }
    manifest["tables"][name] = record
    _write_manifest(root, manifest)
    return record


def read_table(root: Path, name: str) -> Any:
    """``write_table`` 의 역 — 메타 열을 떼고 customer_id 인덱스 · attrs 를 되살린다. 지문이 다르면 멈춘다."""
    import pandas as pd

    from src.decision.model_store import frame_digest

    root = Path(root)
    manifest = _read_manifest(root)
    record = manifest["tables"].get(name)
    if record is None:
        raise FeatureStoreError(f"{root} 에 {name!r} 테이블이 없다")
    path = root / record["file"]
    if hashlib.sha256(path.read_bytes()).hexdigest() != record["file_sha256"]:
        raise FeatureStoreError(f"{path} 의 SHA-256 이 manifest 와 다르다 — 읽지 않는다")
    table = pd.read_parquet(path)
    frame = table.drop(columns=list(META_COLUMNS)).set_index(table["customer_id"].rename(record["index_name"]))
    frame = frame[record["columns"]]
    if frame_digest(frame) != record["frame_sha256"]:
        raise FeatureStoreError(f"{name}: 다시 읽은 값의 지문이 저장 때와 다르다")
    frame.attrs = dict(record["attrs"])
    return frame


def tables(root: Path) -> dict[str, Any]:
    return dict(_read_manifest(Path(root))["tables"])
