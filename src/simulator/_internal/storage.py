from __future__ import annotations

import errno
import hashlib
import json
import os
import tempfile
from pathlib import Path

from src.simulator._internal.rng import canonical_json

STATES_DIR = "states"
RUNS_DIR = "runs"
DERIVATIONS_DIR = "derivations"


def default_hidden_root() -> Path:
    return Path(__file__).resolve().parents[3].joinpath("data", "hidden", "simulator")


def is_empty_root(path: Path) -> bool:
    if not path.exists():
        return True
    return path.is_dir() and not any(path.iterdir())


# 이름 바꾸기는 이미 끝났다. 디렉터리 fsync 를 지원하지 않는 파일시스템의 오류는 실패로 보지 않는다.
_FSYNC_UNSUPPORTED = frozenset({errno.EINVAL, errno.ENOTSUP, errno.EBADF})


def _fsync_directory(directory: Path) -> None:
    if os.name != "posix":
        return
    handle = os.open(directory, os.O_RDONLY)
    try:
        os.fsync(handle)
    except OSError as error:
        if error.errno not in _FSYNC_UNSUPPORTED:
            raise
    finally:
        os.close(handle)


def atomic_write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    handle, temp_name = tempfile.mkstemp(dir=path.parent, prefix=".tmp-", suffix=path.suffix)
    try:
        with os.fdopen(handle, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp_name, path)
        _fsync_directory(path.parent)
    except BaseException:
        Path(temp_name).unlink(missing_ok=True)
        raise


def state_path(hidden_root: Path, state_id: str) -> Path:
    return hidden_root.joinpath(STATES_DIR, f"{state_id}.json")


def write_state(hidden_root: Path, state_id: str, data: bytes) -> None:
    atomic_write(state_path(hidden_root, state_id), data)


def read_state(hidden_root: Path, state_id: str) -> bytes:
    return state_path(hidden_root, state_id).read_bytes()


def sidecar_path(hidden_root: Path, run_id: str) -> Path:
    return hidden_root.joinpath(RUNS_DIR, f"{run_id}.json")


def write_sidecar(hidden_root: Path, record: dict[str, object]) -> None:
    atomic_write(sidecar_path(hidden_root, str(record["run_id"])), canonical_json(record))


def _read_object(path: Path) -> dict[str, object]:
    record = json.loads(path.read_text(encoding="ascii"))
    if not isinstance(record, dict):
        raise ValueError(f"계보 기록 {path.name} 이 객체가 아니다")
    return record


def read_sidecar(hidden_root: Path, run_id: str) -> dict[str, object] | None:
    path = sidecar_path(hidden_root, run_id)
    if not path.is_file():
        return None
    return _read_object(path)


def _records(directory: Path) -> list[dict[str, object]]:
    if not directory.is_dir():
        return []
    return [_read_object(path) for path in sorted(directory.glob("*.json"))]


def sidecars(hidden_root: Path) -> list[dict[str, object]]:
    return _records(hidden_root.joinpath(RUNS_DIR))


def write_derivation(hidden_root: Path, record: dict[str, object]) -> None:
    data = canonical_json(record)
    name = hashlib.sha256(data).hexdigest()[:32]
    atomic_write(hidden_root.joinpath(DERIVATIONS_DIR, f"{name}.json"), data)


def derivations(hidden_root: Path) -> list[dict[str, object]]:
    return _records(hidden_root.joinpath(DERIVATIONS_DIR))


# ── S4~S6(#143): 주문 기록 · Ground truth ────────────────────────────────────
#
# 주문(품목·주문 시점 원가 포함)은 세계 상태가 아니라 실행마다 따로 남긴다 — 상태가 주문 수에 비례해
# 커지면 advance 마다 하는 정준 직렬화·다이제스트가 느려진다. 주문은 관측 가능한 값이라 교환 묶음으로 나간다.
ORDERS_DIR = "orders"
GROUND_TRUTH_DIR = "ground_truth"


def default_ground_truth_root() -> Path:
    return Path(__file__).resolve().parents[3].joinpath("data", "ground_truth", "simulator")


def ground_truth_root(hidden_root: Path) -> Path:
    """기본 숨김 루트면 `data/ground_truth/simulator/`, 시험·도구가 준 루트면 그 아래 `ground_truth/`."""
    if hidden_root == default_hidden_root():
        return default_ground_truth_root()
    return hidden_root.joinpath(GROUND_TRUTH_DIR)


def _jsonl(rows: list[dict[str, object]]) -> bytes:
    return b"".join(canonical_json(row) + b"\n" for row in rows)


def write_orders(hidden_root: Path, run_id: str, orders: list[dict[str, object]]) -> None:
    atomic_write(hidden_root.joinpath(ORDERS_DIR, f"{run_id}.jsonl"), _jsonl(orders))


def read_orders(hidden_root: Path, run_id: str) -> list[dict[str, object]] | None:
    path = hidden_root.joinpath(ORDERS_DIR, f"{run_id}.jsonl")
    if not path.is_file():
        return None
    return [json.loads(line) for line in path.read_text(encoding="ascii").splitlines() if line]


def write_ground_truth(root: Path, name: str, rows: list[dict[str, object]]) -> Path:
    path = root.joinpath(f"{name}.jsonl")
    atomic_write(path, _jsonl(rows))
    return path


def write_json(path: Path, payload: object) -> None:
    atomic_write(path, json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2).encode("utf-8") + b"\n")


def write_jsonl(path: Path, rows: list[dict[str, object]]) -> None:
    atomic_write(path, b"".join(
        json.dumps(row, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8") + b"\n"
        for row in rows
    ))
