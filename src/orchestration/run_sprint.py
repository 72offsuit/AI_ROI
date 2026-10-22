"""스프린트 v0 실행 루프 — 명령 하나로 탐색 RCT → 모델 학습 → 전략 비교까지 돈다 (이슈 #146).

    python -m src.orchestration.run_sprint --seed 42 --customers 20000 --profile reference --out <dir>
    python -m src.orchestration.run_sprint --seed 42 --customers 2000 --profile small --out <dir>   # 스모크

흐름 (지휘자는 명령만 내린다 — `src/orchestration/AGENTS.md`):

1. ``sim.init`` → ``sim.advance(warmup)``. 끝 시각이 ``t1``.
2. **탐색 RCT** — ``t1`` 직전 ``active_days`` 일 안에 이벤트가 있는 고객을 T0 50% · T1~T4 각 12.5% 로
   무작위 배정(``random.Random(seed)``)하고 ``apply_treatment`` → ``advance(42)``. 끝 시각이 ``t2``.
   - X = Feature(t1, 이벤트 < t1), 결과 = outcomes(t1, 42일), 처치 = 배정표.
   - churn 은 T0 군으로, uplift 는 전 군으로, CLV 는 전 군 42일 매출로 학습한다.
3. **전략 비교** — ``t2`` 에서 ``snapshot()`` 한 토큰 **하나**로 S0~S5 를 각각 새 빈 루트에 ``restore`` 해
   같은 시점·같은 난수에서 출발시킨다. Feature(t2) 로 점수를 내고(``t1`` 에서 학습한 모델)
   ``plan`` → ``apply_treatment`` → ``advance(42)`` → ``sim.metrics(t2, t2+42)`` + 이벤트 기반 결과.
   기준은 S1 이다(PRD §63). S1 은 상한 없이 실행하고 그 비용을 S2~S5 의 예산으로 쓴다(DR-145).
   S1 입력(마지막 구매 경과일·누적 주문 수·eligible)은 이벤트에서 계산한다 — purchase 를 만들지 않는
   시뮬레이터 판이면 계산하지 않고 S1 은 not_run 이다.
4. ``<results_root>/sprint-v0/<run_id>/`` 에 JSON 7종과 ``latest`` 를 쓴다. ``docs/research/realism_report.json``
   이 있으면 같은 폴더로 사본을 둔다(대시보드는 docs/ 를 읽지 못한다).

의사결정 모듈(``src.decision.*``)은 **지연 로딩**한다. 모듈·함수가 없으면 그 단계를 ``not_run`` 으로
사유와 함께 적고 다음으로 간다. 결손을 0 으로 채우지 않는다 — 값이 없으면 ``null`` 과 사유다.

격리: ``src.simulator`` 는 ``docs/simulator_api.md`` 의 공개 계약(``api``)만 부른다. 숨김 영역 경로는
넘기지 않는다(``init`` 의 선택 인자를 쓰지 않는다). 진단 모듈은 import 하지 않는다.
"""

from __future__ import annotations

import argparse
import dataclasses
import enum
import hashlib
import importlib
import inspect
import json
import math
import os
import random
import secrets
import shutil
import subprocess
import sys
import time
import traceback
from collections import Counter
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Iterator, Mapping

from src.measurement import contracts as mc
from src.simulator import api as sim

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_RESULTS_ROOT = REPO_ROOT / "results"
SPRINT = "sprint-v0"
KST = timezone(timedelta(hours=9), "KST")

# ── 실험 상수 ───────────────────────────────────────────────────────────────
# 프로파일별 권장 warmup — docs/data_spec.html §2.2 표. `small` 은 시간축이 `short` 와 같다
# (docs/decisions/DR-S3-p6-signup.md U11). `--warmup-days` 로 덮어쓸 수 있다.
PROFILE_WARMUP_DAYS: dict[str, int] = {
    "smoke": 90, "short": 180, "small": 180, "reference": 273, "long": 365, "rolling": 273,
}
# label window 는 프로파일 간에도 고정이다(data_spec §2.2) — 인자로 받지 않는다.
LABEL_WINDOW_DAYS = 42

STRATEGIES: tuple[str, ...] = ("S0", "S1", "S2", "S3", "S4", "S5")
BASELINE_STRATEGY = "S1"
# 전략마다 있어야 하는 점수 (data_spec §13.1 의 타게팅 기준). 없으면 그 전략은 not_run 이다.
REQUIRED_SCORES: dict[str, tuple[str, ...]] = {
    "S0": (),
    "S1": ("days_since_last_purchase",),
    "S2": ("churn_p",),
    "S3": ("churn_p", "cate"),
    "S4": ("churn_p", "cate", "clv"),
    "S5": ("churn_p", "cate", "clv"),
}

RCT_ARMS: tuple[str, ...] = ("T0", "T1", "T2", "T3", "T4")
RCT_CONTROL_SHARE = 0.5  # T0 50% · 나머지를 T1~T4 에 균등(각 12.5%)
# 탐색 RCT 모집단 = t1 직전 90일 안에 이벤트가 1건 이상인 고객.
# 90일은 S1 규칙의 상한과 같은 근거다(data_spec §12.1 "90일을 넘기면 회수 확률이 급감").
DEFAULT_ACTIVE_DAYS = 90

# 예산 기본값 — data_spec §12.2 설계 추정치 C_rule ≈ 8,833,000원(26,000명 기준)을 고객 수에
# 비례해 환산한다. 정확한 C_rule 은 GATE 2 에서 S1 을 실측해 Lock 한다 — 이 값은 그 전의 추정이다.
C_RULE_ESTIMATE_KRW = 8_833_000
C_RULE_REFERENCE_CUSTOMERS = 26_000

ECONOMIC_CONFIG = REPO_ROOT / "config" / "economic_config.yaml"
# 대시보드가 docs/ 를 읽지 못하므로 있으면 결과 폴더로 사본을 둔다(없으면 not_run).
REALISM_REPORT = REPO_ROOT / "docs" / "research" / "realism_report.json"

# S1 의 eligible_flag — data_spec §4.1: 가입 ≥ 60일 · 구매 ≥ 1 · 마지막 구매 ≥ 14일.
# 가입일은 이벤트 계약에 없다(customers 테이블 부재, measurement_contract §6.4) — 첫 관측 이벤트 시각으로 근사한다.
ELIGIBLE_MIN_TENURE_DAYS = 60
ELIGIBLE_MIN_ORDERS = 1
ELIGIBLE_MIN_DAYS_SINCE_PURCHASE = 14

RESULT_FILES: tuple[str, ...] = (
    "run_meta", "churn_eval", "clv_eval", "uplift_eval", "segments", "strategy_comparison", "ab_test",
)

# 지연 로딩 대상 — (모듈, 함수). 시그니처는 이슈 #146 의 합의다.
DECISION_API: dict[str, tuple[str, str]] = {
    "load_events": ("src.decision.data", "load_events"),
    "build_feature_table": ("src.decision.features.sprint_table", "build_feature_table"),
    "build_outcomes": ("src.decision.features.sprint_table", "build_outcomes"),
    "evaluate_churn_models": ("src.decision.churn", "evaluate_churn_models"),
    "fit_best_churn": ("src.decision.churn", "fit_best_churn"),
    "predict_churn_proba": ("src.decision.churn", "predict_churn_proba"),
    "evaluate_temporal_holdout": ("src.decision.churn", "evaluate_temporal_holdout"),
    "fit_clv": ("src.decision.clv", "fit_clv"),
    "predict_clv": ("src.decision.clv", "predict_clv"),
    "evaluate_clv": ("src.decision.clv", "evaluate_clv"),
    "fit_uplift": ("src.decision.uplift", "fit_uplift"),
    "predict_cate": ("src.decision.uplift", "predict_cate"),
    "evaluate_uplift_models": ("src.decision.uplift", "evaluate_uplift_models"),
    "assign_segments": ("src.decision.segments", "assign_segments"),
    "plan": ("src.decision.strategies", "plan"),
    "planning_costs": ("src.decision.strategies", "planning_costs"),
    "s1_eligibility": ("src.decision.strategies", "s1_eligibility"),
    "summarize_strategy": ("src.decision.roi", "summarize_strategy"),
    "analyze_ab": ("src.decision.ab_test", "analyze_ab"),
}


# ── 단계 기록 ───────────────────────────────────────────────────────────────


class NotRun(Exception):
    """단계를 시도하지 않았다 — 선행 조건이 없다. 실패(`failed`)와 구분한다."""


def _log(message: str) -> None:
    stamp = datetime.now(KST).strftime("%H:%M:%S")
    print(f"[sprint {stamp}] {message}", flush=True)


class StageLog:
    """단계별 `status: ok|not_run|failed` · 사유 · 소요시간."""

    def __init__(self) -> None:
        self.stages: list[dict[str, Any]] = []

    def status(self, name: str) -> str | None:
        for stage in reversed(self.stages):
            if stage["name"] == name:
                return stage["status"]
        return None

    def ok(self, name: str) -> bool:
        return self.status(name) == "ok"

    def record(self, name: str, status: str, reason: str | None, seconds: float = 0.0) -> None:
        self.stages.append(
            {"name": name, "status": status, "reason": reason, "seconds": round(seconds, 3)}
        )
        tail = f" — {reason}" if reason else ""
        _log(f"{name}: {status} ({seconds:.1f}s){tail}")

    @contextmanager
    def stage(self, name: str, *, requires: tuple[str, ...] = ()) -> Iterator[None]:
        """`with log.stage(...)` 안에서 `NotRun` 은 not_run, 그 밖의 예외는 failed 로 적고 삼킨다."""
        missing = [r for r in requires if not self.ok(r)]
        if missing:
            self.record(name, "not_run", f"선행 단계가 ok 가 아니다: {', '.join(missing)}")
            # contextmanager 는 본문을 건너뛸 수 없다. `requires` 를 둔 본문은 첫 줄에서
            # `skip_if_not_run` 을 불러 `_SkipBody` 로 빠져나오고, 여기서 삼킨다.
            try:
                yield
            except _SkipBody:
                pass
            return
        _log(f"{name}: 시작")
        started = time.perf_counter()
        try:
            yield
        except NotRun as reason:
            self.record(name, "not_run", str(reason), time.perf_counter() - started)
        except Exception as error:  # noqa: BLE001 — 한 단계의 실패가 전체를 멈추지 않는다
            traceback.print_exc(file=sys.stderr)
            self.record(
                name, "failed", f"{type(error).__name__}: {error}", time.perf_counter() - started
            )
        else:
            self.record(name, "ok", None, time.perf_counter() - started)


class _SkipBody(Exception):
    pass


def skip_if_not_run(log: StageLog, name: str) -> None:
    """`stage` 가 선행 조건 미충족으로 이미 not_run 을 적었으면 본문을 건너뛴다."""
    if log.stages and log.stages[-1]["name"] == name and log.stages[-1]["status"] == "not_run":
        raise _SkipBody


# ── 의사결정 모듈 지연 로딩 ─────────────────────────────────────────────────


def decision_fn(key: str) -> Callable[..., Any]:
    """`DECISION_API[key]` 를 import 한다. 없으면 `NotRun`(사유 포함)."""
    module_name, attr = DECISION_API[key]
    try:
        module = importlib.import_module(module_name)
    except ImportError as error:
        missing = getattr(error, "name", None) or str(error)
        raise NotRun(f"{module_name} 를 import 할 수 없다 (없는 모듈: {missing})") from error
    fn = getattr(module, attr, None)
    if not callable(fn):
        raise NotRun(f"{module_name}.{attr} 가 없다")
    return fn


def decision_available(key: str) -> bool:
    try:
        decision_fn(key)
    except NotRun:
        return False
    return True


def call_by_name(fn: Callable[..., Any], pool: Mapping[str, Any]) -> Any:
    """시그니처가 확정되지 않은 함수를 매개변수 이름으로 부른다.

    `pool` 에 없는 **필수** 매개변수가 있으면 추측하지 않고 `NotRun` 을 낸다.
    """
    try:
        params = inspect.signature(fn).parameters
    except (TypeError, ValueError) as error:
        raise NotRun(f"{getattr(fn, '__name__', fn)} 의 시그니처를 읽을 수 없다") from error
    kwargs: dict[str, Any] = {}
    missing: list[str] = []
    for name, param in params.items():
        if param.kind in (param.VAR_POSITIONAL, param.VAR_KEYWORD):
            continue
        if name in pool:
            kwargs[name] = pool[name]
        elif param.default is param.empty:
            missing.append(name)
    if missing:
        raise NotRun(
            f"{getattr(fn, '__name__', fn)} 의 필수 인자 {missing} 를 오케스트레이션이 알지 못한다 "
            f"(제공 가능: {sorted(pool)})"
        )
    return fn(**kwargs)


# ── 예산 · 비용 ─────────────────────────────────────────────────────────────


def default_budget_krw(num_customers: int) -> int:
    return round(C_RULE_ESTIMATE_KRW * num_customers / C_RULE_REFERENCE_CUSTOMERS)


@dataclasses.dataclass(frozen=True)
class CostBasis:
    """economic_config 의 비용 근거 — 처치 단가 · 메시지 비용 · 캠페인 고정비."""

    treatment_unit_cost_krw: dict[str, int]
    message_cost_krw: int
    campaign_fixed_cost_krw: int


def load_cost_basis() -> tuple[CostBasis | None, str | None]:
    """못 읽으면 `(None, 사유)`."""
    try:
        from src.measurement import config_loader

        accounting = config_loader.load_economic_config(ECONOMIC_CONFIG).cost_accounting
    except Exception as error:  # noqa: BLE001 — PyYAML 부재 포함
        return None, f"economic_config 를 읽을 수 없다: {type(error).__name__}: {error}"
    return CostBasis(
        treatment_unit_cost_krw={str(k): int(v) for k, v in accounting.treatment_cost.items()},
        message_cost_krw=int(accounting.message_cost_krw),
        campaign_fixed_cost_krw=int(accounting.campaign_fixed_cost_krw),
    ), None


def plan_costs(basis: CostBasis | None) -> tuple[dict[str, float] | None, str]:
    """`plan` 에 넘길 고객당 계획 비용. 정의는 의사결정의 `strategies.planning_costs`(단가 + 메시지)다."""
    if basis is None:
        return None, "비용 근거 없음"
    try:
        fn = decision_fn("planning_costs")
    except NotRun as reason:
        return dict(basis.treatment_unit_cost_krw), f"처치 단가만 — {reason}"
    costs = dict(fn(basis.treatment_unit_cost_krw, basis.message_cost_krw))
    costs.setdefault("T0", 0.0)
    return costs, "strategies.planning_costs — 처치 단가 + 메시지 비용(쿠폰 전량 사용 가정의 상한)"


def resolve_budget(explicit_krw: int | None, s1_entry: Mapping[str, Any] | None,
                   basis: CostBasis | None, num_customers: int) -> dict[str, Any]:
    """S2~S5 의 예산. 기본은 **S1(상한 없이 실행)의 비용**이다 — 같은 예산 비교(data_spec §13).

    우선순위: `--budget-krw` → S1 실측 `marketing_cost`(측정 계층, 고정비 포함) → S1 계획 비용
    (쿠폰 전량 사용 상한 + 고정비) → 설계 추정 C_rule 비례 환산. `plan` 에는 캠페인 고정비를 뺀
    값을 넘긴다(고정비는 고객 단위가 아니다 — DR-145).
    """
    fixed = basis.campaign_fixed_cost_krw if basis is not None else None
    s1 = (s1_entry or {}).get("metrics") or {}
    planned = (s1_entry or {}).get("planned_cost_krw")
    if explicit_krw is not None:
        total, source = float(explicit_krw), "--budget-krw 인자 (캠페인 고정비 포함 총예산으로 본다)"
    elif s1.get("marketing_cost") is not None:
        total, source = float(s1["marketing_cost"]), "S1 실측 marketing_cost (측정 계층 · 캠페인 고정비 포함)"
    elif planned is not None and fixed is not None:
        total = float(planned) + fixed
        source = ("S1 계획 비용(쿠폰 전량 사용 가정 상한) + 캠페인 고정비 — 시뮬레이터가 marketing_cost 를 "
                  "만들지 않아 실현 비용 대신 썼다")
    else:
        total = float(default_budget_krw(num_customers))
        source = (f"data_spec §12.2 설계 추정 C_rule ≈ {C_RULE_ESTIMATE_KRW:,}원({C_RULE_REFERENCE_CUSTOMERS:,}명 기준)을 "
                  f"고객 수 {num_customers:,}명에 비례 환산 — S1 비용을 얻지 못했다. GATE 2 실측 전 추정치")
    planning = total - fixed if fixed is not None else total
    return {
        "budget_total_krw": total,
        "campaign_fixed_cost_krw": fixed,
        "planning_budget_krw": max(planning, 0.0),
        "planning_budget_note": "plan(S2~S5) 에 넘긴 값 = 총예산 − 캠페인 고정비. S1 은 상한 없이(None) 실행",
        "source": source,
    }


# ── 탐색 RCT 배정 ───────────────────────────────────────────────────────────


def rct_assign(customer_ids: list[str], seed: int) -> dict[str, str]:
    """T0 50% · T1~T4 각 12.5% 무작위 배정. 같은 고객 집합·같은 seed 면 같은 배정이다.

    고객 ID 를 정렬한 뒤 `random.Random(seed)` 로 섞는다 — 입력 순서에 의존하지 않는다.
    시뮬레이터의 난수 흐름과 섞이지 않도록 표준 라이브러리 난수기를 따로 쓴다.
    """
    ordered = sorted(set(customer_ids))
    random.Random(seed).shuffle(ordered)
    n_control = round(len(ordered) * RCT_CONTROL_SHARE)
    assignment = {cid: "T0" for cid in ordered[:n_control]}
    treated_arms = RCT_ARMS[1:]
    for i, cid in enumerate(ordered[n_control:]):
        assignment[cid] = treated_arms[i % len(treated_arms)]
    return assignment


# ── 이벤트 읽기 ─────────────────────────────────────────────────────────────


def _pd():
    import pandas as pd  # 지연 import — 의존성 없는 CI 에서 이 모듈의 정적 검사가 깨지지 않게

    return pd


def _timestamps(events: Any) -> Any:
    """`timestamp` 열을 datetime 으로. 시간대가 없으면(로더가 KST 벽시계로 냈다면) 그대로 둔다."""
    pd = _pd()
    column = events["timestamp"]
    if pd.api.types.is_datetime64_any_dtype(column):
        return column
    return pd.to_datetime(column, format="ISO8601")


STREAM_CHUNK = 200_000


def frame_from_stream(records: Any) -> Any:
    """`sim.events()` 스트림 → DataFrame. `timestamp` 는 시간대가 있는 datetime 으로 바꾼다.

    dict 목록 전체를 한꺼번에 들고 있지 않도록 청크 단위로 프레임을 만든다. 스트림 도중 예외가
    나면 그대로 올린다 — 받은 일부만으로 프레임을 만들지 않는다(simulator_api.md `events`).
    """
    pd = _pd()
    chunks: list[Any] = []
    buffer: list[dict[str, object]] = []
    for record in records:
        buffer.append(record)
        if len(buffer) >= STREAM_CHUNK:
            chunks.append(pd.DataFrame.from_records(buffer))
            buffer = []
    if buffer or not chunks:
        chunks.append(pd.DataFrame.from_records(buffer))
    frame = chunks[0] if len(chunks) == 1 else pd.concat(chunks, ignore_index=True)
    if "timestamp" in frame.columns and len(frame):
        frame["timestamp"] = pd.to_datetime(frame["timestamp"], format="ISO8601")
    return frame


class EventReader:
    """출력 루트를 `decision.data.load_events` 로 읽는다. 없으면 `sim.events(until)` 대체 경로.

    대체 경로는 **활성 세계**의 계보를 읽으므로 해당 `advance` 직후에 불러야 한다.
    """

    def __init__(self) -> None:
        try:
            self._load_events = decision_fn("load_events")
            self.source = "src.decision.data.load_events"
            self.fallback_reason = None
        except NotRun as reason:
            self._load_events = None
            self.source = "src.simulator.api.events"
            self.fallback_reason = str(reason)

    def read(self, root: Path, until: datetime, history: Any = None) -> Any:
        """`root` 의 이벤트(`timestamp < until`). 분기 루트는 분기 이전 이력을 `history` 로 붙인다."""
        if self._load_events is None:
            return frame_from_stream(sim.events(until))
        frame = self._load_events(root)
        if history is None:
            return frame
        return _pd().concat([history, frame], ignore_index=True)


def observed_values(frame: Any, column: str) -> list[Any]:
    if frame is None or column not in getattr(frame, "columns", ()):
        return []
    return sorted({v for v in frame[column].dropna().unique().tolist()}, key=str)


def active_customers(events: Any, until: datetime, days: int) -> list[str]:
    """`[until - days, until)` 에 이벤트가 1건 이상인 고객 — 탐색 RCT 모집단 정의."""
    stamps = _timestamps(events)
    end = until if stamps.dt.tz is not None else until.astimezone(KST).replace(tzinfo=None)
    window = (stamps >= end - timedelta(days=days)) & (stamps < end)
    return sorted(events.loc[window, "customer_id"].dropna().unique().tolist())


def event_count_by_type(frame: Any) -> dict[str, int]:
    if frame is None or "event_type" not in getattr(frame, "columns", ()):
        return {}
    return {str(k): int(v) for k, v in frame["event_type"].value_counts().sort_index().items()}


def s1_inputs(events: Any, index_time: datetime, population: Any) -> dict[str, Any]:
    """S1 규칙 입력 — `index_time` 미만 이벤트에서 고객별로 계산한다.

    - ``days_since_last_purchase``: 마지막 주문부터의 일수(소수). 주문이 없으면 NaN(0 으로 채우지 않는다).
    - ``lifetime_order_count``: 주문 수(``purchase`` 1행 = 주문 1건, 같은 order_id 는 1건).
    - ``eligible``: data_spec §4.1 — 첫 관측 ≥ 60일(가입일 근사) · 주문 ≥ 1 · 마지막 주문 ≥ 14일.

    ★ 주문 수의 0 은 **이 시뮬레이터 판이 purchase 를 만들 때만** 관측된 0 이다. 호출자가 확인한다.
    """
    pd = _pd()
    stamps = _timestamps(events)
    end = index_time if stamps.dt.tz is not None else index_time.astimezone(KST).replace(tzinfo=None)
    before = events.loc[stamps < end].assign(_ts=stamps[stamps < end])
    purchases = before[before["event_type"] == "purchase"]
    key = purchases["order_id"].where(purchases["order_id"].notna(), "evt:" + purchases["event_id"].astype(str))
    orders = purchases.assign(_key=key).drop_duplicates(subset=["customer_id", "_key"])
    count = orders.groupby("customer_id").size().reindex(population, fill_value=0).astype(float)
    last = orders.groupby("customer_id")["_ts"].max().reindex(population)
    days = (end - last).dt.total_seconds() / 86400.0
    first_seen = before.groupby("customer_id")["_ts"].min().reindex(population)
    tenure = (end - first_seen).dt.total_seconds() / 86400.0
    eligible = ((tenure >= ELIGIBLE_MIN_TENURE_DAYS) & (count >= ELIGIBLE_MIN_ORDERS)
                & (days >= ELIGIBLE_MIN_DAYS_SINCE_PURCHASE))
    return {
        "days_since_last_purchase": pd.Series(days.to_numpy(), index=population, name="days_since_last_purchase"),
        "lifetime_order_count": pd.Series(count.to_numpy(), index=population, name="lifetime_order_count"),
        "eligible": pd.Series(eligible.to_numpy(dtype=bool), index=population, name="eligible"),
    }


def purchase_generated(start: datetime, end: datetime) -> tuple[bool, str]:
    """이 시뮬레이터 판이 purchase 를 만드는가 — `sim.metrics` 의 `events.purchase` 상태로 판단한다.

    활성 세계에 대해 부른다. `ok` 의 0 은 측정된 0 이고, `not_run` 이면 이 판이 만들지 않는 유형이다.
    """
    try:
        metric = sim.metrics(start, end).get("events.purchase")
    except Exception as error:  # noqa: BLE001 — 확인 실패는 '만들지 않는다'로 다루고 사유를 남긴다
        return False, f"sim.metrics 확인 실패: {type(error).__name__}: {error}"
    if metric is None:
        return False, "sim.metrics 에 events.purchase 가 없다"
    status = getattr(metric.status, "value", metric.status)
    reason = getattr(metric.reason_code, "value", metric.reason_code)
    return status == "ok", f"events.purchase: {status}" + (f" / {reason}" if reason else "")


def two_classes(series: Any) -> bool:
    return series is not None and series.dropna().nunique() >= 2


# ── JSON ────────────────────────────────────────────────────────────────────


def to_jsonable(value: Any) -> Any:
    """numpy·pandas·datetime·MetricValue 를 JSON 값으로. NaN·inf 는 `null`(0 으로 채우지 않는다)."""
    if value is None or isinstance(value, (bool, str)):
        return value
    if isinstance(value, enum.Enum):
        return to_jsonable(value.value)
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, Path):
        return str(value)
    if type(value).__name__ == "MetricValue" and dataclasses.is_dataclass(value):
        return mc.metric_to_json(value)
    if isinstance(value, Mapping):
        return {str(k): to_jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set, frozenset)):
        return [to_jsonable(v) for v in value]
    module = type(value).__module__.split(".")[0]
    if module == "numpy":
        if hasattr(value, "tolist"):
            return to_jsonable(value.tolist())
        return to_jsonable(value.item())
    if module == "pandas":
        if hasattr(value, "isoformat"):  # Timestamp · NaT
            return None if str(value) == "NaT" else value.isoformat()
        if hasattr(value, "columns") and hasattr(value, "to_dict"):  # DataFrame
            return to_jsonable(value.to_dict(orient="index"))
        if hasattr(value, "to_dict"):  # Series
            return to_jsonable(value.to_dict())
        if hasattr(value, "tolist"):  # Index · Categorical
            return to_jsonable(value.tolist())
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        return to_jsonable(dataclasses.asdict(value))
    if hasattr(value, "item"):
        try:
            return to_jsonable(value.item())
        except (TypeError, ValueError):
            pass
    return repr(value)


def write_results(results_root: Path, run_id: str, payloads: Mapping[str, Mapping[str, Any]],
                  extra_files: Mapping[str, Path] | None = None) -> Path:
    """JSON 7종과 사본 파일을 쓰고 `latest` 를 이 실행으로 돌린다."""
    run_dir = results_root / SPRINT / run_id
    run_dir.mkdir(parents=True, exist_ok=False)
    for name in RESULT_FILES:
        text = json.dumps(to_jsonable(payloads[name]), ensure_ascii=False, indent=2, allow_nan=False)
        (run_dir / f"{name}.json").write_text(text + "\n", encoding="utf-8")
    for target, source in (extra_files or {}).items():
        shutil.copyfile(source, run_dir / target)
    _point_latest(results_root / SPRINT, run_id)
    return run_dir


def realism_copy(source: Path) -> tuple[dict[str, Any], dict[str, Path]]:
    """`realism_report.json` 사본 계획 — `(run_meta 기록, extra_files)`. 없으면 not_run."""
    record: dict[str, Any] = {"source": str(source), "target": "realism_report.json"}
    if not source.is_file():
        record.update(status="not_run", reason="파일이 없다 — 복사하지 않았다")
        return record, {}
    try:
        json.loads(source.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        record.update(status="failed", reason=f"JSON 으로 읽을 수 없다: {type(error).__name__}: {error}")
        return record, {}
    record.update(status="ok", reason=None)
    return record, {"realism_report.json": source}


def _point_latest(sprint_dir: Path, run_id: str) -> None:
    """`latest` → 이 실행. 심링크를 원자적으로 바꾸고, 못 만들면 사본을 둔다."""
    latest = sprint_dir / "latest"
    temp = sprint_dir / f".latest-{secrets.token_hex(4)}"
    try:
        os.symlink(run_id, temp, target_is_directory=True)
        if latest.is_dir() and not latest.is_symlink():
            shutil.rmtree(latest)
        os.replace(temp, latest)
    except OSError:
        if temp.is_symlink():
            temp.unlink()
        if latest.is_symlink():
            latest.unlink()
        elif latest.exists():
            shutil.rmtree(latest)
        shutil.copytree(sprint_dir / run_id, latest)


# ── 출처 기록 ───────────────────────────────────────────────────────────────


def _git(*args: str) -> str | None:
    try:
        result = subprocess.run(
            ["git", *args], cwd=REPO_ROOT, capture_output=True, text=True, timeout=10, check=False
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return result.stdout.strip() if result.returncode == 0 else None


def provenance() -> dict[str, Any]:
    simulator_commit = _git("log", "-1", "--format=%H", "--", "src/simulator")
    dirty = _git("status", "--porcelain", "--ignore-submodules=all", "--", "src/simulator")
    config_dir = REPO_ROOT / "config"
    config_sha256 = {
        p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(config_dir.glob("*.yaml"))
    }
    return {
        "repo_commit": _git("rev-parse", "HEAD"),
        "simulator_commit": simulator_commit,
        "simulator_worktree_dirty": None if dirty is None else bool(dirty),
        "config_sha256": config_sha256,
    }


# ── 실행 ────────────────────────────────────────────────────────────────────


@dataclasses.dataclass
class SprintConfig:
    seed: int
    num_customers: int
    profile: str
    out: Path
    results_root: Path = DEFAULT_RESULTS_ROOT
    warmup_days: int | None = None
    budget_krw: int | None = None
    active_days: int = DEFAULT_ACTIVE_DAYS
    run_id: str | None = None
    realism_report: Path = REALISM_REPORT


def new_run_id(now: datetime | None = None) -> str:
    moment = (now or datetime.now(KST)).astimezone(KST)
    return f"SP-{moment:%Y%m%d}-{moment:%H%M%S}-{secrets.token_hex(4)}"


def _header(run_id: str, generated_at: str) -> dict[str, Any]:
    return {"sprint": SPRINT, "sealed": False, "run_id": run_id, "generated_at": generated_at}


def _pick_method(evaluation: Any) -> Any:
    if isinstance(evaluation, Mapping):
        for key in ("best_method", "best"):
            if evaluation.get(key) is not None:
                return evaluation[key]
    return None


def _strategy_name(strategy: str) -> str | None:
    try:
        module = importlib.import_module(DECISION_API["plan"][0])
    except ImportError:
        return None
    names = getattr(module, "STRATEGY_NAMES", None)
    return names.get(strategy) if isinstance(names, Mapping) else None


def _segment_summary(segments: Any, scores: Mapping[str, Any]) -> dict[str, Any]:
    pd = _pd()
    frame = pd.DataFrame({"segment": segments})
    if scores.get("churn_p") is not None:
        frame["churn_p"] = scores["churn_p"]
    if scores.get("clv") is not None:
        frame["clv"] = scores["clv"]
    cate = scores.get("cate")
    if cate is not None:
        for column in cate.columns:
            frame[f"cate_{column}"] = cate[column]
    total = len(frame)
    summary: dict[str, Any] = {}
    for name, group in frame.groupby("segment", sort=True):
        row: dict[str, Any] = {"n": int(len(group)), "share": len(group) / total if total else None}
        for column in group.columns:
            if column != "segment":
                row[f"mean_{column}"] = float(group[column].mean())
        summary[str(name)] = row
    return summary


def _outcome_metrics(outcomes: Any, population: Any) -> dict[str, Any]:
    """이벤트 기반 결과 집계 — 모집단은 Feature(t2) 고객이다."""
    frame = outcomes.reindex(population)
    observed = frame.dropna(how="all")
    n = int(len(observed))
    result: dict[str, Any] = {
        "n_population": int(len(population)),
        "n_with_outcome": n,
        "n_outcome_missing": int(len(population) - n),
    }
    if "churn" in observed:
        churn = float(observed["churn"].mean()) if n else None
        result["churn_rate"] = churn
        result["retention_rate"] = None if churn is None else 1.0 - churn
    if "revenue" in observed:
        revenue = float(observed["revenue"].sum()) if n else None
        result["revenue_krw"] = revenue
        result["revenue_per_customer_krw"] = revenue / n if n else None
    if "purchases" in observed:
        result["purchases"] = float(observed["purchases"].sum()) if n else None
    return result


def run(config: SprintConfig) -> Path:
    """전 구간을 돌리고 결과 폴더 경로를 돌려준다. 단계 실패는 기록하고 다음으로 간다."""
    run_id = config.run_id or new_run_id()
    generated_at = mc.kst_now()
    log = StageLog()
    out = Path(config.out)
    main_root = out / "raw" / "main"
    warmup = config.warmup_days if config.warmup_days is not None else PROFILE_WARMUP_DAYS.get(config.profile)
    basis, basis_reason = load_cost_basis()
    costs, costs_source = plan_costs(basis)
    _log(f"run_id={run_id} seed={config.seed} N={config.num_customers} profile={config.profile} out={out}")

    ctx: dict[str, Any] = {"timeline": {}}
    reader = EventReader()
    if reader.fallback_reason:
        _log(f"이벤트 읽기: 대체 경로 sim.events — {reader.fallback_reason}")

    churn_eval: dict[str, Any] = {}
    clv_eval: dict[str, Any] = {}
    uplift_eval: dict[str, Any] = {}
    ab_test: dict[str, Any] = {}
    segments_out: dict[str, Any] = {}
    comparison: dict[str, Any] = {"baseline": BASELINE_STRATEGY, "strategies": {}}
    rct_meta: dict[str, Any] = {}

    try:
        # 1. warmup ---------------------------------------------------------
        with log.stage("simulate_warmup"):
            if warmup is None:
                raise NotRun(f"프로파일 {config.profile!r} 의 권장 warmup 을 모른다 — --warmup-days 필요")
            sim.init(config.seed, config.num_customers, config.profile, output_root=main_root)
            summary = sim.advance(warmup)
            ctx["t1"] = summary.end
            ctx["timeline"]["start"] = summary.start
            ctx["timeline"]["t1"] = summary.end

        with log.stage("read_events_t1", requires=("simulate_warmup",)):
            skip_if_not_run(log, "read_events_t1")
            ctx["events_t1"] = reader.read(main_root, ctx["t1"])
            _log(f"  이벤트 {len(ctx['events_t1']):,}건 (< t1)")

        # 2. 탐색 RCT -------------------------------------------------------
        with log.stage("rct_assign", requires=("read_events_t1",)):
            skip_if_not_run(log, "rct_assign")
            eligible = active_customers(ctx["events_t1"], ctx["t1"], config.active_days)
            if not eligible:
                raise NotRun(f"t1 직전 {config.active_days}일 활동 고객이 0명이다")
            assignment = rct_assign(eligible, config.seed)
            ctx["rct_assignment"] = assignment
            rct_meta.update(
                {
                    "assigned_at": ctx["t1"],
                    "population_definition": f"t1 직전 {config.active_days}일 안에 이벤트 1건 이상",
                    "n_eligible": len(eligible),
                    "arm_shares_design": {"T0": RCT_CONTROL_SHARE, **{t: (1 - RCT_CONTROL_SHARE) / 4 for t in RCT_ARMS[1:]}},
                    "arm_counts": dict(sorted(Counter(assignment.values()).items())),
                    "randomizer": f"random.Random({config.seed}) — 정렬한 고객 ID 를 섞는다",
                    "effect_window": "apply_treatment 시점부터 42일, 다음 호출이 덮어씀(시뮬레이터 S4~S6 정의 예정)",
                }
            )

        # Feature(t1) 은 처치 전에 계산한다 — t1 의 결정은 t1 까지의 정보만 쓴다.
        with log.stage("features_t1", requires=("read_events_t1",)):
            skip_if_not_run(log, "features_t1")
            build = decision_fn("build_feature_table")
            ctx["X1"] = build(ctx["events_t1"], ctx["t1"])
            _log(f"  Feature(t1) {ctx['X1'].shape}")
        ctx["simulator_version"] = observed_values(ctx.get("events_t1"), "simulator_version")
        ctx["random_seed"] = observed_values(ctx.get("events_t1"), "random_seed")
        ctx.pop("events_t1", None)  # 이후 단계는 t2 까지의 이벤트를 다시 읽는다 — 메모리를 돌려준다

        with log.stage("simulate_rct", requires=("rct_assign",)):
            skip_if_not_run(log, "simulate_rct")
            sim.apply_treatment(ctx["rct_assignment"])
            summary = sim.advance(LABEL_WINDOW_DAYS)
            ctx["t2"] = summary.end
            ctx["timeline"]["t2"] = summary.end

        with log.stage("read_events_t2", requires=("simulate_rct",)):
            skip_if_not_run(log, "read_events_t2")
            ctx["events_t2"] = reader.read(main_root, ctx["t2"])
            _log(f"  이벤트 {len(ctx['events_t2']):,}건 (< t2)")
            ctx["event_types_t2"] = event_count_by_type(ctx["events_t2"])
            # 본선 세계가 활성인 지금 확인한다 — 분기 뒤에는 이 세계로 돌아오지 않는다.
            ctx["purchase_generated"], ctx["purchase_detail"] = purchase_generated(
                ctx["timeline"]["start"], ctx["t2"]
            )

        with log.stage("outcomes_t1", requires=("read_events_t2",)):
            skip_if_not_run(log, "outcomes_t1")
            build_outcomes = decision_fn("build_outcomes")
            ctx["Y1"] = build_outcomes(ctx["events_t2"], ctx["t1"], window_days=LABEL_WINDOW_DAYS)

        with log.stage("training_set", requires=("rct_assign", "features_t1", "outcomes_t1")):
            skip_if_not_run(log, "training_set")
            pd = _pd()
            treatment_all = pd.Series(ctx["rct_assignment"], name="treatment").sort_index()
            index = treatment_all.index.intersection(ctx["X1"].index).intersection(ctx["Y1"].index)
            ctx["train_index"] = index
            ctx["treatment"] = treatment_all.loc[index]
            ctx["X_rct"] = ctx["X1"].loc[index]
            ctx["Y_rct"] = ctx["Y1"].loc[index]
            rct_meta["n_training"] = int(len(index))
            rct_meta["n_dropped_without_features_or_outcome"] = int(len(treatment_all) - len(index))
            if "purchase" not in ctx.get("event_types_t2", {}):
                rct_meta["label_warning"] = "purchase 이벤트 0건 — 결과 라벨이 구매에 근거하지 않는다"

        # churn — T0 군 ------------------------------------------------------
        with log.stage("churn", requires=("training_set",)):
            skip_if_not_run(log, "churn")
            control = ctx["treatment"] == "T0"
            X = ctx["X_rct"].loc[control]
            y = ctx["Y_rct"].loc[control, "churn"]
            churn_eval.update({"population": "탐색 RCT T0 군", "n": int(len(y)),
                               "label": f"churn (t1, {LABEL_WINDOW_DAYS}일)"})
            if not two_classes(y):
                raise NotRun("T0 군 churn 라벨이 한 값뿐이다 — 학습·평가 불가 (구매 이벤트 유무 확인)")
            churn_eval["positive_rate"] = float(y.mean())
            evaluation = decision_fn("evaluate_churn_models")(X, y, config.seed)
            churn_eval["evaluation"] = evaluation
            fit = decision_fn("fit_best_churn")
            if "eval_result" in inspect.signature(fit).parameters:
                ctx["churn_model"] = fit(X, y, config.seed, eval_result=evaluation)
            else:
                ctx["churn_model"] = fit(X, y, config.seed)
            ctx["churn_train"] = (X, y)
            if isinstance(evaluation, Mapping) and evaluation.get("best_proposed") is not None:
                ctx["churn_best_name"] = evaluation["best_proposed"]

        # uplift — 전 군 -----------------------------------------------------
        with log.stage("uplift", requires=("training_set",)):
            skip_if_not_run(log, "uplift")
            retention = 1 - ctx["Y_rct"]["churn"]
            uplift_eval.update({"population": "탐색 RCT 전 군 (T0~T4)", "n": int(len(retention)),
                                "outcome": "retention = 1 − churn",
                                "arm_counts": dict(sorted(Counter(ctx["treatment"].tolist()).items()))})
            if not two_classes(retention):
                raise NotRun("retention 라벨이 한 값뿐이다 — CATE 추정 불가 (구매 이벤트 유무 확인)")
            evaluation = decision_fn("evaluate_uplift_models")(
                ctx["X_rct"], ctx["treatment"], retention, config.seed
            )
            uplift_eval["evaluation"] = evaluation
            fit = decision_fn("fit_uplift")
            params = inspect.signature(fit).parameters
            kwargs: dict[str, Any] = {"seed": config.seed} if "seed" in params else {}
            method = _pick_method(evaluation)
            if method is None:
                if "method" in params and params["method"].default is inspect.Parameter.empty:
                    raise NotRun("evaluate_uplift_models 가 best_method 를 내지 않았고 fit_uplift 의 method 에 기본값이 없다")
                ctx["uplift_model"] = fit(ctx["X_rct"], ctx["treatment"], retention, **kwargs)
                uplift_eval["fitted_method"] = params["method"].default if "method" in params else None
                uplift_eval["fitted_method_source"] = "fit_uplift 기본값 (평가 결과에 best_method 없음)"
            else:
                ctx["uplift_model"] = fit(ctx["X_rct"], ctx["treatment"], retention, method, **kwargs)
                uplift_eval["fitted_method"] = method
                uplift_eval["fitted_method_source"] = "evaluate_uplift_models 의 best_method"

        # CLV — 전 군 42일 매출 ----------------------------------------------
        with log.stage("clv", requires=("training_set",)):
            skip_if_not_run(log, "clv")
            future_value = ctx["Y_rct"]["revenue"]
            clv_eval.update({"population": "탐색 RCT 전 군", "n": int(len(future_value)),
                             "target": f"t1 이후 {LABEL_WINDOW_DAYS}일 매출(원) — 12개월 CLV 가 아니다"})
            if future_value.dropna().nunique() < 2:
                raise NotRun("미래 매출이 한 값뿐이다 — CLV 학습 불가 (구매 이벤트 유무 확인)")
            fit = decision_fn("fit_clv")
            if "seed" in inspect.signature(fit).parameters:
                ctx["clv_model"] = fit(ctx["X_rct"], future_value, seed=config.seed)
            else:
                ctx["clv_model"] = fit(ctx["X_rct"], future_value)
            try:
                evaluate = decision_fn("evaluate_clv")
                clv_eval["evaluation"] = call_by_name(
                    evaluate, {"X": ctx["X_rct"], "future_value": future_value, "y": future_value,
                               "model": ctx["clv_model"], "seed": config.seed,
                               "horizon_days": LABEL_WINDOW_DAYS},
                )
            except NotRun as reason:
                clv_eval["evaluation"] = {"status": "not_run", "reason": str(reason)}

        # A/B — 탐색 RCT 자체 분석 -------------------------------------------
        with log.stage("ab_test", requires=("training_set",)):
            skip_if_not_run(log, "ab_test")
            analyze = decision_fn("analyze_ab")
            frame = ctx["Y_rct"].copy()
            frame["arm"] = ctx["treatment"]
            frame["retention"] = 1 - frame["churn"]
            ab_test["population"] = "탐색 RCT 전 군"
            ab_test["control"] = "T0"
            ab_test["results"] = {}
            # analyze_ab 는 비율 검정(이진 결과)만 받는다 — 연속 결과(매출)는 넘기지 않고 사유를 남긴다.
            for outcome in ("retention", "revenue"):
                if outcome not in frame:
                    continue
                values = set(frame[outcome].dropna().unique().tolist())
                if values <= {0, 1}:
                    ab_test["results"][outcome] = analyze(frame, "arm", outcome, control="T0")
                else:
                    ab_test["results"][outcome] = {
                        "status": "not_run", "reason": "이진(0/1) 결과가 아니다 — analyze_ab 는 비율 검정만 한다",
                    }

        # 3. 전략 비교 -------------------------------------------------------
        with log.stage("features_t2", requires=("read_events_t2",)):
            skip_if_not_run(log, "features_t2")
            ctx["X2"] = decision_fn("build_feature_table")(ctx["events_t2"], ctx["t2"])
            _log(f"  Feature(t2) {ctx['X2'].shape}")

        scores: dict[str, Any] = {}
        with log.stage("scores_t2", requires=("features_t2",)):
            skip_if_not_run(log, "scores_t2")
            X2 = ctx["X2"]
            reasons: dict[str, str] = {}
            if "churn_model" in ctx:
                scores["churn_p"] = decision_fn("predict_churn_proba")(ctx["churn_model"], X2)
            else:
                reasons["churn_p"] = f"churn 단계 {log.status('churn')}"
            if "uplift_model" in ctx:
                scores["cate"] = decision_fn("predict_cate")(ctx["uplift_model"], X2)
            else:
                reasons["cate"] = f"uplift 단계 {log.status('uplift')}"
            if "clv_model" in ctx:
                scores["clv"] = decision_fn("predict_clv")(ctx["clv_model"], X2)
            else:
                reasons["clv"] = f"clv 단계 {log.status('clv')}"
            # S1 입력 — 이벤트에서 계산한다. purchase 를 만들지 않는 판이면 계산하지 않는다(0 으로 채우지 않는다).
            if ctx.get("purchase_generated"):
                scores.update(s1_inputs(ctx["events_t2"], ctx["t2"], X2.index))
                comparison["s1_inputs"] = {
                    "source": "이벤트(t2 미만 purchase) — 오케스트레이션 계산",
                    "eligible_definition": (
                        f"첫 관측 ≥ {ELIGIBLE_MIN_TENURE_DAYS}일(가입일 근사 — 이벤트 계약에 가입일 없음) · "
                        f"주문 ≥ {ELIGIBLE_MIN_ORDERS} · 마지막 주문 ≥ {ELIGIBLE_MIN_DAYS_SINCE_PURCHASE}일 (data_spec §4.1)"
                    ),
                    "n_eligible": int(scores["eligible"].sum()),
                    "n_with_purchase_history": int(scores["days_since_last_purchase"].notna().sum()),
                }
            else:
                detail = ctx.get("purchase_detail", "purchase 생성 여부를 확인하지 못했다")
                for key in ("days_since_last_purchase", "lifetime_order_count", "eligible"):
                    reasons[key] = f"이 시뮬레이터 판이 purchase 를 만들지 않는다 ({detail})"
            ctx["score_missing"] = reasons
            comparison["scores_available"] = sorted(scores)
            comparison["scores_missing"] = reasons

        with log.stage("segments", requires=("scores_t2",)):
            skip_if_not_run(log, "segments")
            missing = [k for k in ("churn_p", "cate", "clv") if k not in scores]
            if missing:
                raise NotRun(f"점수가 없다: {missing}")
            seg = decision_fn("assign_segments")(scores["churn_p"], scores["cate"], scores["clv"])
            segments_out.update({"index_time": ctx["t2"], "n": int(len(seg)),
                                 "segments": _segment_summary(seg, scores)})

        with log.stage("snapshot_t2", requires=("simulate_rct",)):
            skip_if_not_run(log, "snapshot_t2")
            ctx["snapshot"] = sim.snapshot()

        population = ctx["X2"].index if "X2" in ctx else None
        strategy_results: dict[str, dict[str, Any]] = comparison["strategies"]
        for strategy in STRATEGIES:
            name = f"strategy_{strategy}"
            entry: dict[str, Any] = {"strategy_id": strategy}
            strategy_results[strategy] = entry
            with log.stage(name, requires=("snapshot_t2",)):
                skip_if_not_run(log, name)
                lacking = [k for k in REQUIRED_SCORES[strategy] if k not in scores]
                if lacking:
                    raise NotRun(f"필요한 점수가 없다: {lacking}")
                if strategy == "S0":
                    # PRD §60 — S0 은 정의상 무처치다. 전략 모듈이 없어도 실행할 수 있다.
                    try:
                        assignments = dict(decision_fn("plan")(strategy, scores, None, costs))
                    except NotRun:
                        assignments = {}
                        entry["plan_source"] = "정의상 무처치(PRD §60) — 전략 모듈 없음"
                elif strategy == BASELINE_STRATEGY:
                    # S1 은 상한 없이(None) 조건 충족 전원 — 그 비용이 S2~S5 의 예산이 된다(DR-145).
                    entry["budget_krw"] = None
                    assignments = dict(decision_fn("plan")(strategy, scores, None, costs))
                    try:
                        entry["s1_eligibility"] = decision_fn("s1_eligibility")(scores)
                    except NotRun as reason:
                        entry["s1_eligibility"] = {"status": "not_run", "reason": str(reason)}
                else:
                    if costs is None:
                        raise NotRun(basis_reason or "처치 비용을 읽을 수 없다")
                    budget = ctx["budget"]["planning_budget_krw"]
                    entry["budget_krw"] = budget
                    assignments = dict(decision_fn("plan")(strategy, scores, budget, costs))
                branch_root = out / "raw" / strategy
                sim.restore(ctx["snapshot"], output_root=branch_root)
                if assignments:
                    sim.apply_treatment(assignments)
                summary = sim.advance(LABEL_WINDOW_DAYS)
                ctx["timeline"]["end"] = summary.end
                counts = Counter(assignments.values())
                entry["n_assigned"] = len(assignments)
                entry["n_targeted"] = sum(v for t, v in counts.items() if t != "T0")
                entry["treatment_counts"] = dict(sorted(counts.items()))
                if costs is not None:
                    entry["planned_cost_krw"] = sum(costs.get(t, 0) * n for t, n in counts.items())
                    entry["planned_cost_note"] = (
                        "고객당 계획 비용 × 배정 수 — 쿠폰 전량 사용 가정의 상한, 캠페인 고정비 제외. 실집행 비용이 아니다"
                    )
                entry["event_count"] = summary.event_count
                entry["sim_metrics"] = {
                    k: mc.metric_to_json(v) for k, v in sim.metrics(ctx["t2"], summary.end).items()
                }

                def sim_value(key: str) -> Any:
                    metric = entry["sim_metrics"].get(key, {})
                    return metric.get("value") if metric.get("status") == "ok" else None

                # summarize_strategy(ROW_KEYS) 가 읽는 키. 값이 없으면 None — 계획 비용으로 대신하지 않는다.
                metrics: dict[str, Any] = {
                    "id": strategy,
                    "name": _strategy_name(strategy),
                    "n_targeted": entry["n_targeted"],
                    "treatment_mix": {t: n for t, n in sorted(counts.items()) if t != "T0"},
                    "revenue": sim_value("revenue"),
                    "marketing_cost": sim_value("marketing_cost"),
                    "contribution_profit": sim_value("contribution_profit"),
                    "churn_rate": sim_value("churn_rate"),
                    "planned_cost_krw": entry.get("planned_cost_krw"),
                }
                sources = {k: "sim.metrics" for k in ("revenue", "marketing_cost", "contribution_profit", "churn_rate")
                           if metrics[k] is not None}
                try:
                    build_outcomes = decision_fn("build_outcomes")
                    if population is None:
                        raise NotRun("Feature(t2) 가 없어 모집단을 정할 수 없다")
                    events = reader.read(branch_root, summary.end, history=ctx["events_t2"])
                    outcomes = build_outcomes(events, ctx["t2"], window_days=LABEL_WINDOW_DAYS)
                    entry["event_outcomes"] = _outcome_metrics(outcomes, population)
                    for key, value in entry["event_outcomes"].items():
                        metrics[f"event_{key}"] = value
                    # 이탈률은 이벤트 라벨(42일 무구매, Feature(t2) 모집단)을 먼저 쓰고, 매출은 측정 계층이 없을 때만 이벤트 합계
                    if entry["event_outcomes"].get("churn_rate") is not None:
                        metrics["churn_rate"], sources["churn_rate"] = entry["event_outcomes"]["churn_rate"], "events"
                    if metrics["revenue"] is None and entry["event_outcomes"].get("revenue_krw") is not None:
                        metrics["revenue"], sources["revenue"] = entry["event_outcomes"]["revenue_krw"], "events"
                    if strategy == "S0":
                        ctx["S0_outcomes"] = outcomes
                except NotRun as reason:
                    entry["event_outcomes"] = {"status": "not_run", "reason": str(reason)}
                metrics["metric_sources"] = sources
                entry["metrics"] = metrics
            if strategy == BASELINE_STRATEGY:
                # S1 이 끝난 직후 — 성공했든 아니든 S2~S5 의 예산을 정하고 근거를 남긴다.
                ctx["budget"] = resolve_budget(config.budget_krw, entry if log.ok(name) else None,
                                               basis, config.num_customers)
                comparison["budget"] = ctx["budget"]
                _log(f"  S2~S5 예산 {ctx['budget']['planning_budget_krw']:,.0f}원 — {ctx['budget']['source']}")

        if "snapshot" in ctx:
            sim.discard_snapshot(ctx["snapshot"])

        # ROI 요약 — 기준 S1 --------------------------------------------------
        with log.stage("roi_summary", requires=(f"strategy_{BASELINE_STRATEGY}",)):
            skip_if_not_run(log, "roi_summary")
            summarize = decision_fn("summarize_strategy")
            baseline = strategy_results[BASELINE_STRATEGY]["metrics"]
            for strategy, entry in strategy_results.items():
                if "metrics" in entry:
                    entry["summary"] = summarize(entry["metrics"], baseline)

        # temporal holdout — t1 모델을 t2 Feature · S0(무처치) 결과로 평가 ----
        with log.stage("churn_temporal_holdout", requires=("churn", "features_t2", "strategy_S0")):
            skip_if_not_run(log, "churn_temporal_holdout")
            if "S0_outcomes" not in ctx:
                raise NotRun("S0 분기의 이벤트 결과가 없다")
            holdout_y = ctx["S0_outcomes"]["churn"].reindex(ctx["X2"].index).dropna()
            holdout_X = ctx["X2"].loc[holdout_y.index]
            X_train, y_train = ctx["churn_train"]
            pool = {"model": ctx["churn_model"], "X_train": X_train, "y_train": y_train,
                    "X_test": holdout_X, "y_test": holdout_y, "seed": config.seed}
            if "churn_best_name" in ctx:
                pool["model_factory"] = ctx["churn_best_name"]
            churn_eval["temporal_holdout"] = call_by_name(decision_fn("evaluate_temporal_holdout"), pool)
            churn_eval["temporal_holdout_design"] = (
                "t1 T0군으로 학습(best_proposed) → Feature(t2) · S0 분기(무처치) 42일 churn 으로 1회 평가"
            )
    finally:
        stage_status = {s["name"]: s for s in log.stages}

        def status_of(main: str, *others: str) -> dict[str, Any]:
            """`status`·`reason` 은 대표 단계, `stages` 는 관련 단계 전부. 기록이 없으면 not_run."""
            def one(name: str) -> dict[str, Any]:
                stage = stage_status.get(name)
                if stage is None:
                    return {"status": "not_run", "reason": "단계에 도달하지 않았다(앞 단계에서 실행 중단)"}
                return {"status": stage["status"], "reason": stage["reason"]}

            return {**one(main), "stages": {n: one(n) for n in (main, *others)}}

        events_frame = ctx.get("events_t2", ctx.get("events_t1"))
        realism, extra_files = realism_copy(Path(config.realism_report))
        budget_record = ctx.get("budget") or {
            "status": "not_run", "reason": "S1 단계에 도달하지 않아 S2~S5 예산을 정하지 않았다",
            "explicit_budget_krw": config.budget_krw,
        }
        simulator_version = observed_values(events_frame, "simulator_version") or ctx.get("simulator_version")
        random_seed = observed_values(events_frame, "random_seed") or ctx.get("random_seed")
        header = _header(run_id, generated_at)
        run_meta = {
            **header,
            "seed": config.seed,
            "num_customers": config.num_customers,
            "profile": config.profile,
            "warmup_days": warmup,
            "warmup_basis": "--warmup-days 인자" if config.warmup_days is not None else "data_spec §2.2 프로파일 권장값",
            "label_window_days": LABEL_WINDOW_DAYS,
            "timeline": ctx["timeline"],
            "simulator_version": simulator_version or None,
            "random_seed_observed": random_seed or None,
            "event_counts_by_type_until_t2": ctx.get("event_types_t2"),
            "event_source": reader.source,
            "event_source_fallback_reason": reader.fallback_reason,
            "raw_roots": {"main": main_root, **{s: out / "raw" / s for s in STRATEGIES}},
            "budget": budget_record,
            "cost_basis": basis,
            "cost_basis_reason": basis_reason,
            "planning_costs_krw": costs,
            "planning_costs_source": costs_source,
            "purchase_generated": {"value": ctx.get("purchase_generated"), "detail": ctx.get("purchase_detail")},
            "margin_rate": {
                "status": "not_run",
                "reason": "plan 에 margin_rate 를 넘기지 않았다 — CLV 타깃이 42일 매출인데 이익 환산 근거가 측정 계층에 없다"
                          "(EC-1: 원가율을 곱하지 않는다). S4·S5 의 가치는 매출 기준이다",
            },
            "realism_report": realism,
            "rct": rct_meta,
            "strategy_comparison_protocol": {
                "snapshot_at": ctx["timeline"].get("t2"),
                "single_snapshot_token": "snapshot_t2" in stage_status and stage_status["snapshot_t2"]["status"] == "ok",
                "strategies_restored_from_it": [s for s in STRATEGIES if log.ok(f"strategy_{s}")],
                "same_random_numbers": "같은 토큰에서 restore — 같은 시점·같은 고객 상태·같은 난수 (docs/simulator_api.md restore)",
                "rct_effect_overlap": "RCT 처치 효과 창 [t1, t1+42) 는 t2 에서 끝난다 — 전략 창 [t2, t2+42) 와 겹치지 않는다(정의상)",
            },
            "decision_modules": {k: decision_available(k) for k in DECISION_API},
            "provenance": provenance(),
            "stages": log.stages,
        }
        payloads = {
            "run_meta": run_meta,
            "churn_eval": {**header, **status_of("churn", "churn_temporal_holdout"), **churn_eval},
            "clv_eval": {**header, **status_of("clv"), **clv_eval},
            "uplift_eval": {**header, **status_of("uplift"), **uplift_eval},
            "segments": {**header, **status_of("segments"), **segments_out},
            "strategy_comparison": {
                **header,
                **status_of("roi_summary", "snapshot_t2", *(f"strategy_{s}" for s in STRATEGIES)),
                "window": {"start": ctx["timeline"].get("t2"), "days": LABEL_WINDOW_DAYS},
                **comparison,
            },
            "ab_test": {**header, **status_of("ab_test"), "rct": rct_meta, **ab_test},
        }
        run_dir = write_results(Path(config.results_root), run_id, payloads, extra_files)
        _log(f"결과: {run_dir}")
    return run_dir


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m src.orchestration.run_sprint",
        description="스프린트 v0 — 탐색 RCT → Churn/Uplift/CLV → S0~S5 전략 비교를 한 번에 실행한다.",
    )
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--customers", type=int, default=20000)
    parser.add_argument("--profile", default="reference")
    parser.add_argument("--out", type=Path, required=True, help="시뮬레이터 출력 루트의 상위 폴더 (빈 폴더)")
    parser.add_argument("--results-root", type=Path, default=DEFAULT_RESULTS_ROOT)
    parser.add_argument("--warmup-days", type=int, default=None, help="기본: 프로파일 권장값(data_spec §2.2)")
    parser.add_argument("--budget-krw", type=int, default=None,
                        help="S2~S5 총예산(캠페인 고정비 포함). 기본: S1 을 상한 없이 실행한 비용")
    parser.add_argument("--active-days", type=int, default=DEFAULT_ACTIVE_DAYS,
                        help="탐색 RCT 모집단 — t1 직전 이 일수 안에 이벤트가 있는 고객")
    parser.add_argument("--run-id", default=None)
    parser.add_argument("--realism-report", type=Path, default=REALISM_REPORT,
                        help="있으면 결과 폴더로 사본을 둔다 (기본: docs/research/realism_report.json)")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    config = SprintConfig(
        seed=args.seed, num_customers=args.customers, profile=args.profile, out=args.out,
        results_root=args.results_root, warmup_days=args.warmup_days, budget_krw=args.budget_krw,
        active_days=args.active_days, run_id=args.run_id, realism_report=args.realism_report,
    )
    started = time.perf_counter()
    run_dir = run(config)
    meta = json.loads((run_dir / "run_meta.json").read_text(encoding="utf-8"))
    counts = Counter(stage["status"] for stage in meta["stages"])
    _log(f"완료 {time.perf_counter() - started:.1f}s — 단계 {dict(sorted(counts.items()))}")
    return 1 if counts.get("failed") else 0


if __name__ == "__main__":
    raise SystemExit(main())
