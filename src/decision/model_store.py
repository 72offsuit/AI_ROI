"""모델 저장 · 불러오기 — SRS ML-008 (#214).

한 실행에서 학습한 Churn · Uplift · CLV 모델을 ``<root>/<kind>.pkl`` 로 쓰고, 학습 메타데이터를
``<root>/<kind>.json`` 에, 묶음 목록을 ``<root>/manifest.json`` 에 남긴다. 보통 ``models/<run_id>/`` 다
(``models/`` 는 .gitignore — 생성물을 커밋하지 않는다).

## 왜 필요한가
GATE 4 Final Holdout 은 **확정 모델을 다시 학습하지 않고** 새 seed 데이터에 한 번 적용한다. 프로세스가
끝나면 모델이 사라지던 구조(#184 잔여)에서는 그것을 할 수 없었다.

## ML-008 메타데이터
``model_version · dataset_version · feature_version · parameters · cv_score · test_score · created_at`` 에
더해 파일 SHA-256 · 모델 클래스 · 라이브러리 버전을 적는다.
  - ``cv_score`` 는 학습 데이터 안의 검증(교차검증 · 검증 분할), ``test_score`` 는 그 실행에서 학습에 쓰지
    않은 데이터의 점수다. 없으면 null 이고 사유를 ``score_notes`` 에 적는다. **Final Holdout 점수는 여기에
    쓰지 않는다** — 그것은 GATE 4 실행의 결과 파일에만 있다.

## 안전 — pickle 을 불러오는 것은 코드를 실행하는 것이다
``load_model`` 은 메타데이터의 SHA-256 과 파일 바이트가 같을 때만 unpickle 한다(바뀐 파일 · 덮어쓴 파일
거부). **이 저장소의 실행이 쓴 폴더만 불러온다** — 남이 건넨 .pkl 을 불러오지 않는다.

## 대조
``load_models(expected_feature_version=...)`` 는 저장 당시 feature_version 이 지금 코드와 다르면 멈춘다.
Feature 정의가 바뀐 뒤의 모델은 같은 이름의 다른 입력을 받게 된다.
"""

from __future__ import annotations

import dataclasses
import hashlib
import json
import os
import pickle
import platform
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Mapping

STORE_FORMAT = "model-store-v1"
KINDS = ("churn", "uplift", "clv")
MANIFEST = "manifest.json"
KST = timezone(timedelta(hours=9), "KST")


class ModelStoreError(Exception):
    """저장 · 불러오기를 할 수 없다 — 사유를 그대로 올린다(조용히 넘어가지 않는다)."""


def _now() -> str:
    return datetime.now(KST).isoformat(timespec="seconds")


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _write_atomic(path: Path, data: bytes) -> None:
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_bytes(data)
    os.replace(tmp, path)


def _jsonable(value: Any, depth: int = 0) -> Any:
    """메타데이터용 — JSON 으로 옮길 수 있는 값만 남기고 나머지는 클래스 이름 문자열로 적는다."""
    if value is None or isinstance(value, (bool, int, str)):
        return value
    if isinstance(value, float):
        return value if value == value and value not in (float("inf"), float("-inf")) else None
    if depth > 4:
        return type(value).__name__
    if isinstance(value, Mapping):
        return {str(k): _jsonable(v, depth + 1) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(v, depth + 1) for v in value]
    item = getattr(value, "item", None)  # numpy 스칼라
    if callable(item):
        try:
            return _jsonable(item(), depth + 1)
        except (TypeError, ValueError):
            pass
    return type(value).__name__


def library_versions() -> dict[str, str | None]:
    """불러올 때 같은 판인지 대조할 수 있게 — 다르면 sklearn 이 경고하고 결과가 달라질 수 있다."""
    versions: dict[str, str | None] = {"python": platform.python_version()}
    for name in ("numpy", "pandas", "sklearn", "scipy"):
        try:
            module = __import__(name)
            versions[name] = getattr(module, "__version__", None)
        except ImportError:
            versions[name] = None
    return versions


def frame_digest(*frames: Any) -> str:
    """학습 데이터의 지문 — 고객 id · 열 이름 · 값이 같으면 같다 (dataset_version 에 쓴다)."""
    import pandas as pd

    digest = hashlib.sha256()
    for frame in frames:
        obj = frame if isinstance(frame, (pd.DataFrame, pd.Series)) else pd.Series(frame)
        names = list(obj.columns) if isinstance(obj, pd.DataFrame) else [obj.name]
        digest.update(json.dumps([str(n) for n in names], ensure_ascii=False).encode("utf-8"))
        digest.update(pd.util.hash_pandas_object(obj, index=True).to_numpy().tobytes())
    return digest.hexdigest()


def model_parameters(model: Any) -> dict[str, Any]:
    """ML-008 ``parameters`` — 추정기 설정(sklearn ``get_params``)과 모델 자체의 설정 필드."""
    out: dict[str, Any] = {"class": f"{type(model).__module__}.{type(model).__qualname__}"}
    if dataclasses.is_dataclass(model) and not isinstance(model, type):
        for f in dataclasses.fields(model):
            value = getattr(model, f.name)
            if f.name in ("estimator", "models"):
                continue
            if f.name in ("features", "columns") and isinstance(value, list):
                out[f"n_{f.name}"] = len(value)
                continue
            out[f.name] = _jsonable(value)
        estimator = getattr(model, "estimator", None)
        if estimator is not None and hasattr(estimator, "get_params"):
            out["estimator"] = _jsonable(estimator.get_params(deep=True))
        sub = getattr(model, "models", None)
        if isinstance(sub, Mapping):
            out["submodels"] = {k: _jsonable(getattr(getattr(v, "est", None), "get_params", lambda **_: {})(deep=False))
                                for k, v in sub.items()}
    elif hasattr(model, "get_params"):
        out["estimator"] = _jsonable(model.get_params(deep=True))
        features = getattr(model, "features_", None)
        if isinstance(features, list):
            out["n_features"] = len(features)
    return out


def save_model(root: Path, kind: str, model: Any, *, model_version: str, dataset_version: str | None,
               feature_version: str | None, cv_score: Any = None, test_score: Any = None,
               score_notes: Mapping[str, str] | None = None, extra: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """``<root>/<kind>.pkl`` + ``<kind>.json``. 같은 이름이 이미 있으면 덮어쓰지 않는다(실행마다 새 폴더)."""
    if kind not in KINDS:
        raise ModelStoreError(f"모르는 모델 종류: {kind!r} (허용: {KINDS})")
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    pkl, meta_path = root / f"{kind}.pkl", root / f"{kind}.json"
    if pkl.exists() or meta_path.exists():
        raise ModelStoreError(f"{pkl} 가 이미 있다 — 덮어쓰지 않는다(다른 실행의 모델일 수 있다)")
    try:
        data = pickle.dumps(model, protocol=pickle.HIGHEST_PROTOCOL)
    except (pickle.PicklingError, AttributeError, TypeError) as error:
        raise ModelStoreError(f"{kind} 모델을 직렬화할 수 없다: {error}") from error
    _write_atomic(pkl, data)
    meta = {
        "store_format": STORE_FORMAT,
        "kind": kind,
        "file": pkl.name,
        "sha256": _sha256(data),
        "bytes": len(data),
        "model_version": model_version,
        "dataset_version": dataset_version,
        "feature_version": feature_version,
        "parameters": model_parameters(model),
        "cv_score": _jsonable(cv_score),
        "test_score": _jsonable(test_score),
        "score_notes": dict(score_notes or {}),
        "created_at": _now(),
        "libraries": library_versions(),
        **{k: _jsonable(v) for k, v in (extra or {}).items()},
    }
    _write_atomic(meta_path, (json.dumps(meta, ensure_ascii=False, indent=2) + "\n").encode("utf-8"))
    return meta


def write_manifest(root: Path, records: Mapping[str, Mapping[str, Any]], run: Mapping[str, Any]) -> dict[str, Any]:
    """묶음 목록 — 어느 실행이 어떤 모델을 남겼나. ``load_models`` 는 이 파일부터 읽는다."""
    manifest = {
        "store_format": STORE_FORMAT,
        "created_at": _now(),
        "run": _jsonable(dict(run)),
        "models": {kind: {k: rec.get(k) for k in ("file", "sha256", "model_version", "feature_version",
                                                   "dataset_version")}
                   for kind, rec in records.items()},
    }
    _write_atomic(Path(root) / MANIFEST, (json.dumps(manifest, ensure_ascii=False, indent=2) + "\n").encode("utf-8"))
    return manifest


def read_manifest(root: Path) -> dict[str, Any]:
    path = Path(root) / MANIFEST
    try:
        manifest = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as error:
        raise ModelStoreError(f"{path} 가 없다 — 모델 저장 폴더가 아니다") from error
    except json.JSONDecodeError as error:
        raise ModelStoreError(f"{path} 를 읽을 수 없다: {error}") from error
    if manifest.get("store_format") != STORE_FORMAT:
        raise ModelStoreError(f"저장 형식이 다르다: {manifest.get('store_format')!r} (기대 {STORE_FORMAT!r})")
    return manifest


#: manifest 와 개별 메타데이터가 같아야 하는 키 — 다른 실행의 파일 쌍이 섞이면 여기서 드러난다(PR #279 리뷰 R1).
LINK_KEYS = ("file", "sha256", "model_version", "feature_version", "dataset_version")


def _read_meta(root: Path, kind: str) -> dict[str, Any]:
    path = Path(root) / f"{kind}.json"
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as error:
        raise ModelStoreError(f"{path} 가 없다") from error
    except json.JSONDecodeError as error:
        raise ModelStoreError(f"{path} 를 읽을 수 없다: {error}") from error


def check_links(kind: str, meta: Mapping[str, Any], entry: Mapping[str, Any] | None,
                run: Mapping[str, Any] | None = None) -> None:
    """unpickle **전에** manifest 항목 · 실행 기록과 개별 메타데이터를 맞춰 본다. 다르면 ``ModelStoreError``.

    정상 저장 API 는 덮어쓰지 않지만, 파일을 옮기거나 복구하다 다른 실행의 ``{kind}.pkl`` · ``{kind}.json`` 쌍이
    섞이면 각 쌍의 해시는 맞아도 묶음과는 어긋난다 — 의도한 동결 모델과 다른 모델을 평가하게 된다.
    """
    if entry is None:
        raise ModelStoreError(f"{kind}: manifest 에 항목이 없다 — 이 묶음의 모델이 아니다")
    diff = {k: (entry.get(k), meta.get(k)) for k in LINK_KEYS if entry.get(k) != meta.get(k)}
    if diff:
        raise ModelStoreError(f"{kind}: manifest 와 개별 메타데이터가 다르다 {sorted(diff)} — 다른 실행의 파일이 "
                              "섞였을 수 있다. 불러오지 않는다")
    run_id = (run or {}).get("run_id")
    if run_id is not None and meta.get("run_id") is not None and meta["run_id"] != run_id:
        raise ModelStoreError(f"{kind}: 모델의 run_id {meta['run_id']!r} ≠ 묶음의 run_id {run_id!r} — 계보가 어긋난다")


def load_model(root: Path, kind: str, *, expected: Mapping[str, Any] | None = None,
               run: Mapping[str, Any] | None = None) -> tuple[Any, dict[str, Any]]:
    """메타데이터의 SHA-256 과 파일이 같을 때만 불러온다. ``expected``(manifest 항목)가 오면 연결도 먼저 대조한다."""
    root = Path(root)
    meta = _read_meta(root, kind)
    if expected is not None:
        check_links(kind, meta, expected, run)
    try:
        data = (root / meta["file"]).read_bytes()
    except (KeyError, FileNotFoundError) as error:
        raise ModelStoreError(f"{kind} 모델 파일이 없다: {error}") from error
    if _sha256(data) != meta.get("sha256"):
        raise ModelStoreError(f"{kind} 모델 파일의 SHA-256 이 메타데이터와 다르다 — 불러오지 않는다")
    return pickle.loads(data), meta  # noqa: S301 — 위에서 이 저장소가 쓴 바이트 · 묶음인지 대조했다


def load_models(root: Path, kinds: tuple[str, ...] = KINDS, *,
                expected_feature_version: str | None = None) -> tuple[dict[str, tuple[Any, dict[str, Any]]], dict[str, Any]]:
    """manifest 에 있는 모델만 불러온다. **하나라도** 어긋나면 아무것도 unpickle 하지 않고 멈춘다.

    대조 순서(모두 unpickle 전): manifest 항목 ↔ 개별 메타데이터(``LINK_KEYS``) · 실행 run_id →
    개별 메타데이터의 feature_version ↔ 지금 코드(``expected_feature_version``, 주어졌을 때).
    """
    manifest = read_manifest(root)
    listed = manifest.get("models") or {}
    run = manifest.get("run") or {}
    metas: dict[str, dict[str, Any]] = {}
    for kind in kinds:
        if kind not in listed:
            continue
        meta = _read_meta(root, kind)
        check_links(kind, meta, listed[kind], run)
        metas[kind] = meta
    if expected_feature_version is not None:
        stale = {k: m.get("feature_version") for k, m in metas.items()
                 if m.get("feature_version") != expected_feature_version}
        if stale:
            raise ModelStoreError(f"저장 당시 feature_version {stale} ≠ 지금 {expected_feature_version!r} — "
                                  "Feature 정의가 바뀐 뒤의 모델은 불러오지 않는다")
    loaded = {kind: load_model(root, kind, expected=listed[kind], run=run) for kind in metas}
    return loaded, manifest
