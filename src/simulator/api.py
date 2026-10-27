"""시뮬레이터 공개 계약. 외부(`orchestration`)는 이 모듈만 호출한다.

한 프로세스에 활성 세계는 하나다. 실패는 모두 예외로 알린다 — `False`·빈 결과로 돌려주지 않는다.
계약 문서: `docs/simulator_api.md`.
"""

from __future__ import annotations

import collections as _collections
import collections.abc as _abc
import contextlib as _contextlib
import dataclasses as _dataclasses
import datetime as _dt
import os as _os
import pathlib as _pathlib
import platform as _platform
import re as _re
import typing as _typing

from src.measurement import schema as _sc
from src.measurement import sink as _sk
from src.simulator._internal import behavior as _behavior
from src.simulator._internal import clock as _clock
from src.simulator._internal import engine as _engine
from src.simulator._internal import genconfig as _genconfig
from src.simulator._internal import lineage as _lineage
from src.simulator._internal import profiles as _profiles
from src.simulator._internal import runtime as _runtime
from src.simulator._internal import storage as _storage
from src.simulator._internal import treatment as _treatment
from src.simulator._internal import world as _wd

if _typing.TYPE_CHECKING:
    import os
    from datetime import datetime
    from typing import Iterator, Mapping

    from src.measurement import schema as sc

__all__ = [
    "SimulatorError",
    "NotInitializedError",
    "OutputRootError",
    "SnapshotError",
    "StateFormatError",
    "AssignmentError",
    "SinkFormatError",
    "RunSummary",
    "init",
    "advance",
    "snapshot",
    "restore",
    "discard_snapshot",
    "apply_treatment",
    "events",
    "metrics",
    "save_state",
    "load_state",
    "exchange_bundle",
]

_STATE_ID = _re.compile(r"state-[0-9a-f]{16}")
_BUSINESS_METRICS = ("churn_rate", "revenue", "contribution_profit", "marketing_cost")


class SimulatorError(Exception):
    """시뮬레이터 실패의 뿌리."""


class NotInitializedError(SimulatorError):
    """활성 세계가 없다. `init` 또는 `load_state` 를 먼저 부른다."""


class OutputRootError(SimulatorError):
    """출력 루트에 쓸 수 없거나 계보가 디스크와 어긋난다. 복구는 새 빈 루트로만 한다."""


class SnapshotError(SimulatorError):
    """스냅샷 토큰을 모르거나 활성 세계의 것이 아니다."""


class StateFormatError(SimulatorError):
    """저장 상태를 읽을 수 없거나 구조가 틀렸거나 판(`format_version`·`rng_scheme`·`simulator_version`·생성 설정)이 다르다."""


class AssignmentError(SimulatorError):
    """배정 목록에 틀린 항목이 있다. 아무것도 기록하지 않았다."""


class SinkFormatError(SimulatorError):
    """출력 루트의 저장 형식이 섞였거나 현재 런타임이 그 형식을 읽거나 쓸 수 없다."""


@_dataclasses.dataclass(frozen=True)
class RunSummary:
    """`advance` 1회의 결과. `run_id` 는 `days == 0` 이면 `None` 이다."""

    run_id: str | None
    start: datetime
    end: datetime
    event_count: int


def init(
    seed: int,
    num_customers: int,
    profile: str,
    output_root: str | os.PathLike[str],
    *,
    hidden_root: str | os.PathLike[str] | None = None,
    config_path: str | os.PathLike[str] | None = None,
) -> None:
    """새 세계를 만들어 활성 세계로 둔다. 이전 세계와 스냅샷 토큰은 버린다. 이벤트는 쓰지 않는다.

    Args:
        seed: `0 <= seed < 2**63` 정수.
        num_customers: 1 ~ 99,999,999 정수. 고객 ID 는 `C00000001` 부터 순번.
        profile: `smoke` · `short` · `small` · `reference` · `long` · `rolling` 중 하나.
        output_root: 이 세계 전용 Sink 루트. 없거나 빈 디렉터리여야 한다.
        hidden_root: 테스트·도구 전용. 오케스트레이션은 넘기지 않는다.
        config_path: 실험용 생성 설정 파일. `None` 이면 기본 설정이다. 고른 설정은 이 세계에 결속돼
            이후 `advance`·`snapshot` 이 그대로 쓴다. 실패하면 이전 세계와 그 설정이 그대로 남는다.

    Raises:
        TypeError: 인자 타입이 틀렸다(`bool` 포함).
        ValueError: 범위 밖이거나 모르는 profile.
        OutputRootError: `output_root` 가 비어 있지 않다.
        SimulatorError: 생성 설정을 읽을 수 없거나 형식이 틀렸다.
    """
    _check_int("seed", seed, 0, _wd.SEED_LIMIT - 1)
    _check_int("num_customers", num_customers, 1, _wd.MAX_CUSTOMERS)
    if not isinstance(profile, str):
        raise TypeError(f"profile 은 str 이어야 한다 (받음: {type(profile).__name__})")
    if profile not in _profiles.PROFILES:
        raise ValueError(f"모르는 profile: {profile!r} (허용: {sorted(_profiles.PROFILES)})")
    root = _root("output_root", output_root)
    hidden = _hidden_root(hidden_root)
    _check_config_path(config_path)
    _require_empty(root)

    def activate_new() -> None:
        world = _wd.new_world(seed, num_customers, profile)
        _runtime.activate(_runtime.Session(world, hidden, root, None, None), drop_snapshots=True)

    try:
        _genconfig.switch(config_path, activate_new)
    except _genconfig.ConfigError as error:
        raise SimulatorError(_config_unusable(config_path)) from error


def advance(days: int) -> RunSummary:
    """창 `[now, now + days)` 를 생성해 출력 루트에 기록하고 시각을 옮긴다.

    한 번 부를 때마다 Sink 실행 기록 1건과 시뮬레이터 계보 기록 1건이 남는다. `days == 0` 은
    아무것도 하지 않는다. 비어 있지 않은 출력 루트는 계보가 디스크와 맞아야만 이어 쓴다.

    Args:
        days: 0 이상의 `int`(`bool` 불가). 창 끝이 `session_id` 표기 한계를 넘으면 안 된다.

    Returns:
        `RunSummary` — 실행 ID · 창(KST) · 기록한 이벤트 수.

    Raises:
        TypeError · ValueError: `days` 가 틀렸다.
        NotInitializedError: 활성 세계가 없다.
        OutputRootError: 출력 루트·계보의 실행 기록이나 파티션 내용이 계보 기록과 다르거나, 머리가
            이 세계가 마지막으로 쓴 실행과 다르다.
        SinkFormatError: 루트의 저장 형식이 섞였거나 이 런타임이 그 형식을 쓸 수 없다.
        SimulatorError: 쓰기 실패 · 생성한 이벤트의 계약 위반 · 계보 기록 실패.
    """
    _check_int("days", days, 0, None)
    session = _active()
    world = session.world
    start_ms = world["now_ms"]
    end_ms = start_ms + days * _clock.DAY_MS
    if end_ms > _wd.MAX_TIME_MS:
        raise ValueError(f"창 끝 {end_ms} ms 가 session_id 표기 한계 {_wd.MAX_TIME_MS} 를 넘는다")
    if days == 0:
        return RunSummary(None, _clock.to_datetime(start_ms), _clock.to_datetime(start_ms), 0)
    root = session.output_root
    with _translated():
        verifier = _lineage.Verifier(session.hidden_root)
        if not _storage.is_empty_root(root):
            verifier.require_intact(root)
        verifier.chain(session.lineage_head)
        head = _sk.latest_run_id(root)
        if head != session.root_head:
            raise OutputRootError(
                f"{root} 의 계보 머리가 {head!r} 인데 이 세계가 마지막으로 쓴 실행은 "
                f"{session.root_head!r} 이다 — 다른 누군가 이 루트에 썼다. 새 빈 루트로 이어간다"
            )
        fmt = _lineage.write_format(root)
    start_bytes = _wd.encode(world)
    working = _decode_own(start_bytes)
    orders: list[dict[str, object]] = []
    try:
        sink = _sk.EventSink(root, fmt=fmt)
        written = sink.write_events(_engine.run(working, end_ms, orders))
        if not written:
            raise SimulatorError(
                f"생성한 이벤트 {written.rejected}건이 측정 계약을 어겼다: {written.problems[:3]}"
            )
        manifest = sink.close()
    except OSError as error:
        raise SimulatorError(
            f"출력 루트에 쓰지 못했다: {_reason(error)} — 이 루트는 더 이어 쓸 수 없다. "
            "새 빈 루트로 이어간다"
        ) from error
    run_id = str(manifest["run_id"])
    end_bytes = _wd.encode(working)
    try:
        _storage.write_orders(session.hidden_root, run_id, orders)
        _storage.write_sidecar(session.hidden_root, {
            "run_id": run_id,
            "parent_run_id": session.lineage_head,
            "output_root": str(root),
            "window": {
                "from_ms": start_ms,
                "to_ms": end_ms,
                "from": _clock.timestamp(start_ms),
                "to": _clock.timestamp(end_ms),
            },
            "mutations": session.pending,
            "start_state_digest": _wd.digest(start_bytes),
            "end_state_digest": _wd.digest(end_bytes),
            "world_id": world["world_id"],
            "simulator_version": world["simulator_version"],
            "seed": world["seed"],
            "num_customers": world["num_customers"],
            "profile": world["profile"],
            "sink_format": manifest["format"],
            "event_count": manifest["rows"],
            "files": manifest["files"],
            "sha256": manifest["sha256"],
            "rows": manifest["rows"],
            "runtime": {
                "implementation": _platform.python_implementation(),
                "version": _platform.python_version(),
                "platform": _platform.platform(),
            },
        })
    except OSError as error:
        raise SimulatorError(f"계보 기록을 쓰지 못했다 ({run_id}): {_reason(error)}") from error
    session.world = working
    session.root_head = run_id
    session.lineage_head = run_id
    session.pending = []
    return RunSummary(
        run_id, _clock.to_datetime(start_ms), _clock.to_datetime(end_ms), int(manifest["rows"])
    )


def snapshot() -> str:
    """현재 상태를 프로세스 안에 담고 불투명 토큰을 돌려준다. 같은 토큰으로 여러 번 `restore` 할 수 있다.

    Raises:
        NotInitializedError: 활성 세계가 없다.
    """
    session = _active()
    token = _runtime.new_token()
    _runtime.snapshots[token] = _runtime.Snapshot(
        str(session.world["world_id"]),
        _wd.encode(session.world),
        session.lineage_head,
        tuple(dict(mutation) for mutation in session.pending),
    )
    return token


def restore(snap: str, *, output_root: str | os.PathLike[str]) -> None:
    """토큰의 상태로 되돌리고 이후 쓰기를 빈 `output_root` 로 돌린다.

    Raises:
        TypeError: `snap` 이 `str` 이 아니다.
        SnapshotError: 모르는 토큰이거나 활성 세계의 토큰이 아니다.
        OutputRootError: `output_root` 가 비어 있지 않거나 계보 기록이 사라졌다.
        SinkFormatError: 이어받을 계보의 저장 형식을 이 런타임이 읽을 수 없다. 아무것도 바꾸지 않는다.
        SimulatorError: 생성 설정이 같은 프로세스 안에서 바뀌어 토큰의 상태를 다시 읽을 수 없다.
    """
    if not isinstance(snap, str):
        raise TypeError(f"snap 은 str 이어야 한다 (받음: {type(snap).__name__})")
    root = _root("output_root", output_root)
    entry = _runtime.snapshots.get(snap)
    if entry is None:
        raise SnapshotError(f"모르는 스냅샷 토큰: {snap!r}")
    session = _runtime.active
    if session is None or session.world["world_id"] != entry.world_id:
        raise SnapshotError(f"스냅샷 {snap!r} 은 활성 세계의 것이 아니다")
    _require_empty(root)
    _require_lineage_readable(session.hidden_root, entry.lineage_head)
    _runtime.activate(
        _runtime.Session(
            _decode_own(entry.data), session.hidden_root, root, None, entry.lineage_head,
            [dict(mutation) for mutation in entry.pending],
        ),
        drop_snapshots=False,
    )


def discard_snapshot(snap: str) -> None:
    """스냅샷을 지운다.

    Raises:
        TypeError: `snap` 이 `str` 이 아니다.
        SnapshotError: 모르는 토큰.
    """
    if not isinstance(snap, str):
        raise TypeError(f"snap 은 str 이어야 한다 (받음: {type(snap).__name__})")
    if _runtime.snapshots.pop(snap, None) is None:
        raise SnapshotError(f"모르는 스냅샷 토큰: {snap!r}")


def apply_treatment(assignments: Mapping[str, str]) -> None:
    """`customer_id → treatment_id` 배정을 현재 시각으로 배정 이력에 적는다.

    전부 검사한 뒤 하나라도 틀리면 아무것도 적지 않는다. 키는 이 세계의 `^C\\d{8}$` 고객,
    값은 `^T[0-4]$`. 적은 배정은 다음 `advance` 의 계보 기록(또는 그 전에 부른 `save_state`)에 남는다.

    의미(S6 #143): 배정 시각(지금의 세계 시각)에 노출 이벤트가 다음 `advance` 의 첫 순간에 기록되고,
    효과는 그 시각부터 42일 지속한다. 다음 `apply_treatment` 가 덮어쓴다(`T0` 은 효과를 끝낸다).
    배정된 고객마다 처치별 참 효과를 시뮬레이터 숨김 영역에 기록한다 — 호출자에게 돌려주지 않는다.

    Raises:
        TypeError: `assignments` 가 `Mapping` 이 아니다.
        NotInitializedError: 활성 세계가 없다.
        AssignmentError: 틀린 항목이 하나 이상 있다.
    """
    if not isinstance(assignments, _abc.Mapping):
        raise TypeError(
            f"assignments 는 Mapping 이어야 한다 (받음: {type(assignments).__name__})"
        )
    session = _active()
    world = session.world
    problems: list[str] = []
    for cid, tid in assignments.items():
        if not (
            isinstance(cid, str)
            and _sc.check_identifier("customer_id", cid)
            and 0 <= _wd.customer_index(cid) < world["num_customers"]
        ):
            problems.append(f"이 세계에 없는 고객: {cid!r}")
        if not (isinstance(tid, str) and _sc.check_identifier("treatment_id", tid)):
            problems.append(f"{cid!r} 의 처치 ID 형식 위반: {tid!r}")
    if problems:
        raise AssignmentError(
            f"배정 {len(problems)}건이 틀려 아무것도 기록하지 않았다: {sorted(problems)[:5]}"
        )
    if not assignments:
        return
    before = _wd.digest(_wd.encode(world))
    now = world["now_ms"]
    customers = world["customers"]
    ordered = {cid: assignments[cid] for cid in sorted(assignments)}
    try:
        # 같은 시작 상태(스냅샷에서 갈라진 전략 분기)의 반사실은 배정과 무관하게 같다 — 고객별로 재사용한다.
        if _PO_CACHE.get("before") != before:
            _PO_CACHE.clear()
            _PO_CACHE["before"] = before
        cache: dict[str, dict[str, object]] = _PO_CACHE.setdefault("rows", {})
        missing = [cid for cid in ordered if cid not in cache]
        for row in _treatment.potential_outcomes(world, missing):
            cache[str(row["customer_id"])] = row
        rows = [{**cache[cid], "assigned": tid} for cid, tid in ordered.items()]
        assignment_digest = _wd.digest(_rng_json(ordered))
        _storage.write_ground_truth(
            _storage.ground_truth_root(session.hidden_root),
            f"po-{world['world_id']}-{now}-{before[:16]}-{assignment_digest[:16]}", rows,
        )
    except OSError as error:
        raise SimulatorError(f"참 효과 기록을 쓰지 못했다: {_reason(error)} — 배정을 적지 않았다") from error
    for cid, tid in ordered.items():
        customer = customers[_wd.customer_index(cid)]
        customer["assignments"].append([now, tid])
        world["queue"].append((now, cid, _engine.next_seq(customer), "treat"))
    session.pending.append({
        "kind": "apply_treatment",
        "at_ms": now,
        "assignments": ordered,
        "before_digest": before,
        "after_digest": _wd.digest(_wd.encode(world)),
    })


def events(until: datetime) -> Iterator[dict[str, object]]:
    """이 세계의 계보가 기록한 이벤트 중 `timestamp < until` 인 것을 생성 순서로 돌려준다.

    분기 루트라면 분기 이전 이력도 계보를 따라 읽는다. 레코드는 측정 계약 형식 그대로다.
    계보 구성원 실행이 기록한 파일만 읽고, 그 내용이 계보 기록과 맞지 않으면 예외를 낸다.
    반복 도중 예외가 나면 그때까지 받은 이벤트는 불완전하므로 쓰지 않는다 — 전량을 받은 뒤에만 쓴다.

    Args:
        until: 시간대가 있는 `datetime`. 현재 시각 이하.

    Raises:
        TypeError: `until` 이 `datetime` 이 아니다.
        ValueError: naive 이거나 현재 시각보다 미래다.
        NotInitializedError: 활성 세계가 없다.
        OutputRootError: 계보가 가리키는 실행 기록·파티션이 사라졌거나 내용이 다르거나 사슬이 끊겼다.
        SinkFormatError: 계보의 루트를 이 런타임이 읽을 수 없다.
    """
    session = _active()
    upper = _instant_ms("until", until, session)
    chain, files = _verified_chain(session)
    return _iter_events(chain, files, session.world["calendar_start_ms"], upper)


def metrics(start: datetime, end: datetime) -> dict[str, sc.MetricValue]:
    """`[start, end)` 의 이벤트 건수.

    `events_total` 과 `events.<event_type>` 16종을 낸다. 이 시뮬레이터 판이 만들지 않는 유형과
    비즈니스 지표는 `not_run` · `PRECONDITION_MISSING` 이다 — 0 으로 채우지 않는다.

    Raises:
        TypeError · ValueError: `events` 와 같고, `start > end` 도 `ValueError`.
        NotInitializedError · OutputRootError · SinkFormatError: `events` 와 같다.
    """
    session = _active()
    lower = _instant_ms("start", start, session)
    upper = _instant_ms("end", end, session)
    if lower > upper:
        raise ValueError(f"start 가 end 보다 늦다: {start} > {end}")
    chain, files = _verified_chain(session)
    counts: _collections.Counter[str] = _collections.Counter(
        str(record["event_type"]) for record in _iter_events(chain, files, lower, upper)
    )
    label = f"[{_clock.timestamp(lower)}, {_clock.timestamp(upper)})"
    window = _sc.Window(_sc.WindowDirection.RETROSPECTIVE, label=label)
    produced = frozenset(_behavior.PRODUCED_EVENT_TYPES)
    version = session.world["simulator_version"]
    result: dict[str, _sc.MetricValue] = {
        "events_total": _count(counts.total(), produced, window),
    }
    for event_type in _sc.EventType:
        name = f"events.{event_type.value}"
        if event_type.value in produced:
            result[name] = _count(counts[event_type.value], (event_type.value,), window)
        else:
            result[name] = _sc.MetricValue.not_run(
                f"시뮬레이터 {version} 은 {event_type.value} 이벤트를 생성하지 않는다",
                reason_code=_sc.ReasonCode.PRECONDITION_MISSING,
                unit=_sc.Unit.COUNT,
            )
    for name in _BUSINESS_METRICS:
        result[name] = _sc.MetricValue.not_run(
            f"시뮬레이터 {version} 의 metrics 는 건수만 센다 — 비즈니스 지표는 측정 계층(publish)이 계산한다",
            reason_code=_sc.ReasonCode.PRECONDITION_MISSING,
        )
    return result


def save_state() -> str:
    """현재 상태를 시뮬레이터 소유 위치에 원자적으로 쓰고 `state_id` 를 돌려준다.

    같은 상태는 같은 `state_id` 를 받는다. 직전 실행 이후의 배정도 계보에 함께 남긴다.

    Raises:
        NotInitializedError: 활성 세계가 없다.
        SimulatorError: 쓰기에 실패했다. 이미 있던 상태 파일은 그대로 남는다.
    """
    session = _active()
    data = _wd.encode(session.world)
    state_digest = _wd.digest(data)
    state_id = _wd.state_id(state_digest)
    try:
        _storage.write_state(session.hidden_root, state_id, data)
        if session.pending:
            _storage.write_derivation(session.hidden_root, {
                "state_digest": state_digest,
                "parent_run_id": session.lineage_head,
                "mutations": session.pending,
                "world_id": session.world["world_id"],
                "simulator_version": session.world["simulator_version"],
            })
    except OSError as error:
        raise SimulatorError(f"상태 {state_id} 를 저장하지 못했다: {_reason(error)}") from error
    return state_id


def load_state(
    state_id: str,
    output_root: str | os.PathLike[str],
    *,
    hidden_root: str | os.PathLike[str] | None = None,
    config_path: str | os.PathLike[str] | None = None,
) -> None:
    """저장된 상태를 활성 세계로 둔다.

    `output_root` 는 비어 있거나, 계보가 디스크와 맞고 그 루트의 마지막 실행이 바로 이 상태에서
    끝났어야 한다. 빈 루트로 이어받을 때는 이 상태에 이르는 계보가 끝까지 검증돼야 한다.
    실행한 Python 판은 거부 사유가 아니다.

    Args:
        state_id: `save_state` 가 돌려준 값.
        output_root: 이후 쓰기를 받을 Sink 루트.
        hidden_root: 테스트·도구 전용. 오케스트레이션은 넘기지 않는다.
        config_path: 그 상태를 만든 생성 설정 파일. `None` 이면 기본 설정이다. 실패하면 이전 세계와 그
            설정이 그대로 남는다.

    Raises:
        TypeError · ValueError: 인자 타입·형식이 틀렸다.
        StateFormatError: 상태가 없거나 손상됐거나 구조가 틀렸거나 판이 다르다. 고른 생성 설정이 그 상태를
            만든 설정과 다를 때도 — 이때만 메시지에 두 설정의 판 이름·다이제스트 앞자리와 설정을 다시 지정하라는
            안내가 실린다. 실험 파일은 경로 대신 고정 문구로 표기한다.
        OutputRootError: 이어 쓸 수 없는 루트이거나 이 상태에 이르는 계보를 검증할 수 없다.
        SinkFormatError: 이어 쓸 루트나 이어받을 계보의 저장 형식을 이 런타임이 다룰 수 없다.
    """
    if not isinstance(state_id, str):
        raise TypeError(f"state_id 는 str 이어야 한다 (받음: {type(state_id).__name__})")
    if not _STATE_ID.fullmatch(state_id):
        raise ValueError(f"state_id 형식이 아니다: {state_id!r}")
    root = _root("output_root", output_root)
    hidden = _hidden_root(hidden_root)
    _check_config_path(config_path)
    try:
        data = _storage.read_state(hidden, state_id)
    except FileNotFoundError as error:
        raise StateFormatError(f"저장된 상태 {state_id} 가 없다") from error
    except OSError as error:
        raise StateFormatError(f"상태 {state_id} 를 읽지 못했다: {_reason(error)}") from error
    try:
        _genconfig.switch(config_path, lambda: _activate_saved(state_id, data, root, hidden, config_path))
    except _genconfig.ConfigError as error:
        raise StateFormatError(f"상태 {state_id} 를 검증하지 못했다 — {_config_unusable(config_path)}") from error


def _activate_saved(
    state_id: str,
    data: bytes,
    root: _pathlib.Path,
    hidden: _pathlib.Path,
    config_path: str | os.PathLike[str] | None,
) -> None:
    """`load_state` 의 검증·활성화 단계. 고른 생성 설정 아래에서 돌아야 한다(`genconfig.switch`)."""
    try:
        world = _wd.decode(data)
        canonical = _wd.encode(world)
    except _wd.GenerationMismatch as error:
        # 판은 같고 생성 설정만 다르다 — 설정 파일을 다시 고르면 읽을 수 있으니 그 길을 안내한다.
        raise StateFormatError(
            f"상태 {state_id} 의 판을 읽지 않는다: {error} — {_selected_config(config_path)}. "
            "이 상태를 만든 설정 파일을 다시 지정한다(API config_path · CLI --config)"
        ) from error
    except _wd.IncompatibleState as error:
        # format_version·simulator_version 등 판이 다르면 설정을 바꿔도 읽을 수 없다 — 설정 안내를 붙이지 않는다.
        raise StateFormatError(f"상태 {state_id} 의 판을 읽지 않는다: {error}") from error
    except ValueError as error:
        raise StateFormatError(f"상태 {state_id} 가 손상됐다: {error}") from error
    state_digest = _wd.digest(data)
    if canonical != data or _wd.state_id(state_digest) != state_id:
        raise StateFormatError(f"상태 {state_id} 의 내용이 정준형·다이제스트와 맞지 않는다")
    verifier = _lineage.Verifier(hidden)
    with _translated():
        if _storage.is_empty_root(root):
            root_head = None
            lineage_head, pending = _lineage.resolve_origin(verifier, world, state_digest)
        else:
            lineage_head, pending = _lineage.resolve_continuation(
                verifier, world, root, state_digest
            )
            root_head = lineage_head
            _lineage.write_format(root)
    _require_lineage_readable(hidden, lineage_head)
    _runtime.activate(
        _runtime.Session(world, hidden, root, root_head, lineage_head, pending),
        drop_snapshots=False,
    )


def exchange_bundle(until: datetime) -> dict[str, object]:
    """교환 묶음(주문·품목·고객·카탈로그, 계약 `commerce-exchange/v1` §11)을 출력 루트의 형제
    `simulator_exchange/` 에 전량 스냅샷으로 쓴다. 이 세계 계보의 주문 중 `ordered_at < until` 만 싣는다.

    Returns:
        `{"status": "ok", "path": 묶음 디렉터리, "orders": 주문 수, "order_items": 품목 수,
        "customers": 고객 수, "generated_at": until(KST)}`.

    Raises:
        TypeError · ValueError: `events` 의 `until` 과 같다.
        NotInitializedError: 활성 세계가 없다.
        OutputRootError: 계보의 실행에 주문 기록이 없거나 계보가 끊겼다.
        SimulatorError: 묶음을 쓰지 못했다.
    """
    session = _active()
    upper = _instant_ms("until", until, session)
    chain, _ = _verified_chain(session)
    stamp = _clock.timestamp(upper)
    orders: list[dict[str, object]] = []
    for record in chain:
        run_id = str(record["run_id"])
        try:
            rows = _storage.read_orders(session.hidden_root, run_id)
        except (OSError, ValueError) as error:
            raise OutputRootError(f"실행 {run_id} 의 주문 기록을 읽지 못했다: {type(error).__name__}") from error
        if rows is None:
            raise OutputRootError(f"실행 {run_id} 의 주문 기록이 없다 — 이 판 이전의 계보다")
        orders.extend(row for row in rows if str(row["ordered_at"]) < stamp)
    world = session.world
    customers = [
        {"customer_id": c["customer_id"], "signup_date": _clock.timestamp(c["signup_ms"])[:10]}
        for c in world["customers"] if c["signup_ms"] < upper
    ]
    catalog = [
        {"snapshot_at": stamp, "product_id": p["product_id"], "category": p["category"],
         "selling_price": p["unit_price"], "unit_cost": p["unit_cost"]}
        for p in world["catalog"]
    ]
    order_rows = [
        {key: order[key] for key in (
            "order_id", "customer_id", "ordered_at", "order_amount", "discount", "shipping_fee",
            "shipping_charged",
        )}
        for order in orders
    ]
    items = [
        {"order_id": order["order_id"], **item} for order in orders for item in order["items"]
    ]
    target = session.output_root.parent.joinpath("simulator_exchange")
    files = {
        "customers.jsonl": customers, "catalog.jsonl": catalog, "orders.jsonl": order_rows,
        "order_items.jsonl": items,
    }
    try:
        for name, rows in files.items():
            _storage.write_jsonl(target.joinpath(name), rows)
        _storage.write_json(target.joinpath("manifest.json"), {
            "contract": "commerce-exchange/v1",
            "source": "simulator",
            "source_commit": world["simulator_version"],
            "generated_at": stamp,
            "mode": "full",
            "files": {name: len(rows) for name, rows in files.items()},
        })
    except OSError as error:
        raise SimulatorError(f"교환 묶음을 쓰지 못했다: {_reason(error)}") from error
    return {
        "status": _sc.MetricStatus.OK.value,
        "path": str(target),
        "orders": len(order_rows),
        "order_items": len(items),
        "customers": len(customers),
        "generated_at": stamp,
    }


# 반사실 결과 캐시 — {"before": 배정 전 상태 다이제스트, "rows": {customer_id: 행}}. 시작 상태가 바뀌면 비운다.
_PO_CACHE: dict[str, object] = {}


def _rng_json(value: object) -> bytes:
    return _wd.canonical_json(value)


# config 오류의 자세한 사유(키·모수 값·페르소나 id)와 호출자가 준 파일 경로는 __cause__ 에만 둔다. 공개 메시지에는
# 숨은 필드의 이름과 값을 싣지 않는다(docs/persona_spec.md 5.3) — 실험 파일 이름에도 그런 이름이 들어갈 수 있다.
def _config_unusable(config_path: str | os.PathLike[str] | None) -> str:
    return (
        f"생성 설정 {_genconfig.public_label(config_path)} 을 쓸 수 없다 — 읽을 수 없거나 계약을 어겼다. "
        "자세한 사유는 원인 예외(__cause__)에 있다"
    )


def _selected_config(config_path: str | os.PathLike[str] | None) -> str:
    """지금 고른 생성 설정의 공개 표기 — 파일 표기(실험 파일은 경로 대신 고정 문구)와 판 이름·다이제스트 앞 12자."""
    config = _genconfig.active()
    return (
        f"지금 고른 생성 설정은 {_genconfig.public_label(config_path)}"
        f"({config.version}·{config.digest[:12]}) 이다"
    )


def _decode_own(data: bytes) -> dict[str, object]:
    """이 프로세스가 만든 상태를 다시 읽는다. 활성 세계가 있는 동안 config 는 불변이 계약이라 실패는
    그 계약이 깨졌다는 뜻이다. 내부 예외 대신 공개 예외로 알린다."""
    try:
        return _wd.decode(data)
    except (_wd.IncompatibleState, _genconfig.ConfigError) as error:
        raise SimulatorError(
            "활성 세계를 만든 생성 설정이 지금 설정과 다르다 — 생성 설정은 init·load_state 로만 바꾼다"
        ) from error


@_contextlib.contextmanager
def _translated() -> _typing.Iterator[None]:
    try:
        yield
    except _lineage.LineageBroken as error:
        raise OutputRootError(str(error)) from error
    except _lineage.FormatProblem as error:
        raise SinkFormatError(str(error)) from error
    except OSError as error:
        raise OutputRootError(f"출력 루트를 확인하지 못했다: {_reason(error)}") from error


def _reason(error: OSError) -> str:
    return error.strerror or type(error).__name__


def _count(value: int, sources: _abc.Iterable[str], window: _sc.Window) -> _sc.MetricValue:
    return _sc.MetricValue.ok(
        value,
        unit=_sc.Unit.COUNT,
        basis=_sc.Basis(
            population="이 세계의 계보가 기록한 시뮬레이터 이벤트",
            denominator_definition="분모 없음 (합계)",
            window=window,
            observed_count=value,
            source_event_types=tuple(sorted(sources)),
        ),
    )


def _check_int(name: str, value: object, lo: int, hi: int | None) -> None:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{name} 는 int 여야 한다 (받음: {type(value).__name__})")
    if value < lo or (hi is not None and value > hi):
        upper = "" if hi is None else f" ~ {hi}"
        raise ValueError(f"{name} 범위 밖: {value} (허용: {lo}{upper})")


def _root(name: str, value: object) -> _pathlib.Path:
    if not isinstance(value, (str, _os.PathLike)):
        raise TypeError(f"{name} 는 경로여야 한다 (받음: {type(value).__name__})")
    return _pathlib.Path(_os.fspath(value)).resolve()


def _check_config_path(value: object) -> None:
    if value is not None and not isinstance(value, (str, _os.PathLike)):
        raise TypeError(f"config_path 는 경로여야 한다 (받음: {type(value).__name__})")


def _hidden_root(value: object) -> _pathlib.Path:
    return _storage.default_hidden_root() if value is None else _root("hidden_root", value)


def _require_empty(root: _pathlib.Path) -> None:
    if not _storage.is_empty_root(root):
        raise OutputRootError(f"{root} 가 비어 있지 않다 — 시뮬레이터는 빈 루트에만 새로 쓴다")


def _active() -> _runtime.Session:
    if _runtime.active is None:
        raise NotInitializedError("활성 세계가 없다 — init() 또는 load_state() 를 먼저 부른다")
    return _runtime.active


def _instant_ms(name: str, value: object, session: _runtime.Session) -> int:
    if not isinstance(value, _dt.datetime):
        raise TypeError(f"{name} 는 datetime 이어야 한다 (받음: {type(value).__name__})")
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{name} 에 시간대가 없다: {value!r}")
    moment = _clock.ceil_ms(value)
    now = session.world["now_ms"]
    if moment > now:
        raise ValueError(
            f"{name} 가 현재 시각 {_clock.timestamp(now)} 보다 미래다: {value.isoformat()}"
        )
    return moment


def _verified_chain(
    session: _runtime.Session,
) -> tuple[list[dict[str, object]], dict[str, list[_pathlib.Path]]]:
    verifier = _lineage.Verifier(session.hidden_root)
    with _translated():
        chain = verifier.chain(session.lineage_head)
        formats = {str(record["sink_format"]) for record in chain}
        for paths in verifier.files.values():
            formats.update(path.name.split(".", 1)[1] for path in paths)
        _lineage.require_formats_readable(formats)
    return chain, verifier.files


def _require_lineage_readable(hidden: _pathlib.Path, head: str | None) -> None:
    with _translated():
        verifier = _lineage.Verifier(hidden)
        _lineage.require_formats_readable(_lineage.lineage_formats(verifier, head))


def _iter_events(
    chain: list[dict[str, object]],
    files: dict[str, list[_pathlib.Path]],
    lower: int,
    upper: int,
) -> _typing.Iterator[dict[str, object]]:
    low, high = _clock.timestamp(lower), _clock.timestamp(upper)
    for record in chain:
        window = record["window"]
        if max(int(window["from_ms"]), lower) >= min(int(window["to_ms"]), upper):
            continue
        run_id = str(record["run_id"])
        rows = 0
        try:
            for path in files[run_id]:
                for event in _lineage.read_file(path):
                    rows += 1
                    stamp = str(event["timestamp"])
                    if low <= stamp < high:
                        yield event
        except SimulatorError:
            raise
        except ImportError as error:
            raise SinkFormatError(f"실행 {run_id} 의 파티션을 읽을 의존성이 없다: {error.name}") from error
        except Exception as error:
            raise OutputRootError(
                f"실행 {run_id} 의 파티션을 읽지 못했다: {type(error).__name__}"
            ) from error
        if rows != record["event_count"]:
            raise OutputRootError(
                f"실행 {run_id} 의 파티션에서 {rows}건을 읽었는데 계보 기록은 {record['event_count']}건이다"
            )
