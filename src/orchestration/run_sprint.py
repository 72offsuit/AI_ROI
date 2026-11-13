"""스프린트 v0 실행 루프 — 명령 하나로 탐색 RCT → 모델 학습 → 전략 비교까지 돈다 (이슈 #146).

    python -m src.orchestration.run_sprint --out <dir>   # config 기본 — 50,000명 · reference · warmup 312일 (#211)
    python -m src.orchestration.run_sprint --seed 42 --customers 2000 --profile small --out <dir>   # 스모크

흐름 (지휘자는 명령만 내린다 — `src/orchestration/AGENTS.md`):

1. ``sim.init`` → ``sim.advance(warmup)``. 끝 시각이 ``t1``.
2. **탐색 RCT** — ``t1`` 의 data_spec §4.1 Eligible 고객을 T0 50% · T1~T4 각 12.5% 로
   무작위 배정(``random.Random(seed)``)하고 ``apply_treatment`` → ``advance(42)``. 끝 시각이 ``t2``.
   Eligible 은 시뮬 팀이 #164 에 공유한 정본 정의다(#194 · DR-234). 가입일은 교환 묶음의 고객 명부에서 읽는다.
   - X = Feature(t1, 이벤트 < t1), 결과 = outcomes(t1, 42일), 처치 = 배정표.
   - churn 은 T0 군으로, uplift 는 전 군으로, CLV 는 전 군 42일 매출로 학습한다.
3. **전략 비교** — ``t2`` 에서 ``snapshot()`` 한 토큰 **하나**로 S0~S5 를 각각 새 빈 루트에 ``restore`` 해
   같은 시점·같은 난수에서 출발시킨다. Feature(t2) 로 점수를 내고(``t1`` 에서 학습한 모델)
   ``plan`` → ``apply_treatment`` → ``advance(42)`` → ``sim.metrics(t2, t2+42)`` + 이벤트 기반 결과.
   기준은 S1 이다(PRD §63). S1 은 상한 없이 실행하고 그 계획 비용 합(C_rule)을 S2~S5 의 예산으로 쓴다(DR-145).
   분기마다 그 세계가 활성일 때 ``sim.exchange_bundle`` 로 교환 묶음을 받고, 측정 계층
   ``publish.build_kpi_report`` 로 분기 창의 매출·마케팅비·**실측 기여이익**(묶음의 주문 시점 원가로
   COGS 차감)을 계산해 ``measured_*`` 로 넘긴다(DR-169). 분기 창 금액 대조(DQ-09)나 주문당 purchase
   1건(DQ-02b)이 실패하면 그 분기 값은 넘기지 않는다(``quality_failed``). 분기 루트는 ``out/branches/{S}/raw`` —
   묶음이 그 형제 ``simulator_exchange/`` 에 분기별로 남는다.
   S4·S5 의 가치는 CLV × margin_rate 다 — 측정 계층 실현 기여이익률, 없으면 economic_config 매출 가중 마진.
   결과 JSON 은 대시보드 sprint 로더 타입(dashboard/src/lib/artifacts/sprint-types.ts)의 키로 낸다.
   S1 입력(마지막 구매 경과일·누적 주문 수·eligible)은 이벤트에서 계산한다 — purchase 를 만들지 않는
   시뮬레이터 판이면 계산하지 않고 S1 은 not_run 이다. S1~S5 는 모두 Eligible(t2) 안에서만 고르고
   (``strategies.plan``), 분기의 이벤트 결과도 Eligible(t2) 고객으로 집계한다(DR-234).
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

from src.decision.config import load_experiment_config, load_model_config
from src.decision.observation_contract import (
    outcome_observation_status as _contract_observation_status,
    event_content_hash, event_content_digest, verify_event_run,
)
from src.measurement import contracts as mc
from src.orchestration.provenance import (  # #262 · #264
    DIRTY_PATHS_LIMIT, DirtyRepoError, check_clean, provenance, repo_state,
)
from src.simulator import api as sim

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_RESULTS_ROOT = REPO_ROOT / "results"
SPRINT = "sprint-v0"
KST = timezone(timedelta(hours=9), "KST")

# ── 실험 상수 ───────────────────────────────────────────────────────────────
# config/experiment_config.yaml (#206) — 배정 비율 · 모집단 창 · 실행 기본값은 그 파일 한 곳에만 있다.
# 모델 config 도 여기서 한 번 읽어 검증한다: 잘못된 config 는 시뮬레이션을 시작하기 전에 import 에서 멈춘다.
EXPERIMENT = load_experiment_config()
load_model_config()
# 프로파일별 권장 warmup — docs/data_spec.html §2.2 표. `small` 은 시간축이 `short` 와 같다
# (docs/decisions/DR-S3-p6-signup.md U11). `--warmup-days` 로 덮어쓸 수 있다.
# config 의 기본 프로파일로 돌 때는 이 표가 아니라 config `run.warmup_days` 다(#211 · resolve_warmup).
PROFILE_WARMUP_DAYS: dict[str, int] = {
    "smoke": 90, "short": 180, "small": 180, "reference": 273, "long": 365, "rolling": 273,
}


def resolve_warmup(profile: str, warmup_days: int | None) -> tuple[int | None, str]:
    """warmup 일수(= t1)와 그 출처. 우선순위는 ① ``--warmup-days`` 인자 → ② config ``run.warmup_days`` —
    ``profile`` 이 config ``run.profile`` 과 같을 때만 → ③ 프로파일 권장값(data_spec §2.2).

    ②를 config 프로파일에만 묶는 것은 실험 규모(DR-234)가 그 프로파일의 실행을 위한 값이기 때문이다.
    ``--profile small`` 스모크가 312일을 돌지 않는다. 권장값을 모르는 프로파일이면 ``None`` 이고, 실행이
    warmup 단계에서 ``not_run`` 이 된다(DR-211).
    """
    if warmup_days is not None:
        return warmup_days, "--warmup-days 인자"
    if profile == EXPERIMENT.run.profile:
        return (EXPERIMENT.run.warmup_days,
                f"config/experiment_config.yaml run.warmup_days (프로파일 {profile} · DR-234 실험 규모)")
    return PROFILE_WARMUP_DAYS.get(profile), "data_spec §2.2 프로파일 권장값"
# label window 는 프로파일 간에도 고정이다(data_spec §2.2) — 인자로 받지 않는다.
LABEL_WINDOW_DAYS = 42

STRATEGIES: tuple[str, ...] = ("S0", "S1", "S2", "S3", "S4", "S5")
BASELINE_STRATEGY = "S1"
# 전략별 필수 점수는 의사결정(`strategies.REQUIRED_SCORES`)이 정한다 — 없으면 plan 이 NotComputable(→ not_run).

RCT_ARMS: tuple[str, ...] = ("T0", "T1", "T2", "T3", "T4")
RCT_CONTROL_SHARE = EXPERIMENT.rct.control_share  # T0 비율 · 나머지를 T1~T4 에 균등
# 탐색 RCT 모집단 = t1 의 Eligible(아래 ELIGIBLE_*). 예전의 "t1 직전 90일 활동 고객"(active_days)은
# 정본 모집단(#194)과 달라 없앴다 — DR-234.

# 예산 — C_rule = S1(상한 없음) 배정의 계획 비용 합(쿠폰 전량 사용 상한 · 캠페인 고정비 제외)이다
# (#170 · DR-170). `--budget-krw` 없이 S1 이 없으면 S2~S5 · What-if 는 not_run 이다 — 설계 추정치로
# 메우지 않는다(같은 예산이 아니다). `--budget-krw` 를 주면 S1 단계가 실패해도 처치 비용 근거가 있으면
# 그 예산으로 돈다 — 탐색 실행이고 S1 대비 정식 비교가 아니다(C_rule 이 없어 가드레일 · roi_summary 는
# not_run, DR-170 D2 · D3).

ECONOMIC_CONFIG = REPO_ROOT / "config" / "economic_config.yaml"
# 대시보드가 docs/ 를 읽지 못하므로 있으면 결과 폴더로 사본을 둔다(없으면 not_run).
REALISM_REPORT = REPO_ROOT / "docs" / "research" / "realism_report.json"

# Eligible — data_spec §4.1 · #164 정본 정의(#194): 가입 ≥ 60일 · T0 이전 구매 ≥ 1 · 마지막 구매 ≥ 14일.
# RCT 배정 · S1~S5 배정 · 분기 결과 집계가 같은 정의를 쓴다(DR-234). 세 조건 모두 T0 **이전** 관측만 본다.
# 일수는 KST 날짜 차다(정의가 "가입일" · "마지막 구매일" 이다). 가입일은 이벤트 계약에 없어(measurement_contract
# §6.4) 교환 묶음의 고객 명부(`customers.signup_date`, 교환 계약 v1)에서 읽는다 — 예전의 첫 관측 근사는 없앴다.
ELIGIBLE_MIN_TENURE_DAYS = 60
ELIGIBLE_MIN_ORDERS = 1
ELIGIBLE_MIN_DAYS_SINCE_PURCHASE = 14
ELIGIBLE_DEFINITION = (
    f"data_spec §4.1 Eligible(#194) — T0 − 가입일 ≥ {ELIGIBLE_MIN_TENURE_DAYS}일 · T0 이전 구매 ≥ "
    f"{ELIGIBLE_MIN_ORDERS}건 · T0 − 마지막 구매일 ≥ {ELIGIBLE_MIN_DAYS_SINCE_PURCHASE}일 (KST 날짜 차, "
    "가입일은 교환 묶음 고객 명부)"
)

RESULT_FILES: tuple[str, ...] = (
    "run_meta", "churn_eval", "clv_eval", "uplift_eval", "segments", "strategy_comparison", "ab_test",
)

# 지연 로딩 대상 — (모듈, 함수). 시그니처는 이슈 #146 의 합의다.
DECISION_API: dict[str, tuple[str, str]] = {
    "load_events": ("src.decision.data", "load_events"),
    "build_feature_table": ("src.decision.features.sprint_table", "build_feature_table"),
    "build_outcomes": ("src.decision.features.sprint_table", "build_outcomes"),
    "summarize_outcomes": ("src.decision.features.sprint_table", "summarize_outcomes"),
    "evaluate_churn_models": ("src.decision.churn", "evaluate_churn_models"),
    "fit_best_churn": ("src.decision.churn", "fit_best_churn"),
    "predict_churn_proba": ("src.decision.churn", "predict_churn_proba"),
    "evaluate_temporal_holdout": ("src.decision.churn", "evaluate_temporal_holdout"),
    "temporal_population_audit": ("src.decision.churn", "temporal_population_audit"),
    "make_risk_model_factory": ("src.decision.churn", "make_risk_model_factory"),
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
    "within_eligible": ("src.decision.strategies", "within_eligible"),
    "segment_stats": ("src.decision.segments", "segment_stats"),
    "what_if": ("src.decision.optimize", "what_if"),
    "what_if_budgets": ("src.decision.optimize", "what_if_budgets"),
    "summarize_strategy": ("src.decision.roi", "summarize_strategy"),
    "analyze_ab": ("src.decision.ab_test", "analyze_ab"),
    # #214 — 저장 · 불러오기 · 평가만 · NFR-01 버전
    "evaluate_fitted_churn": ("src.decision.churn", "evaluate_fitted_churn"),
    "evaluate_fitted_uplift": ("src.decision.uplift", "evaluate_fitted_uplift"),
    "evaluate_fitted_clv": ("src.decision.clv", "evaluate_fitted_clv"),
    "save_model": ("src.decision.model_store", "save_model"),
    "write_model_manifest": ("src.decision.model_store", "write_manifest"),
    "load_models": ("src.decision.model_store", "load_models"),
    "frame_digest": ("src.decision.model_store", "frame_digest"),
    "write_feature_table": ("src.decision.feature_store", "write_table"),
    "feature_version": ("src.decision.versions", "feature_version"),
    "versions_record": ("src.decision.versions", "versions_record"),
    # #215 — SHAP 요약 그림 · 고객별 설명
    "write_shap_summary": ("src.decision.churn", "write_shap_summary"),
    "explain_top_risk": ("src.decision.churn", "explain_top_risk"),
}


# ── 단계 기록 ───────────────────────────────────────────────────────────────


class NotRun(Exception):
    """단계를 시도하지 않았다 — 선행 조건이 없다. 실패(`failed`)와 구분한다."""


def _log(message: str) -> None:
    stamp = datetime.now(KST).strftime("%H:%M:%S")
    print(f"[sprint {stamp}] {message}", flush=True)


class StageLog:
    """단계별 `status: ok|not_run|failed` · 사유 · 소요시간.

    `selected` 가 있으면 그 밖의 단계는 시도하지 않고 not_run 으로 적는다 — 사유에 `scope` 를 쓴다
    (`src/main.py --mode` 가 실행 범위를 정한다, #206). None 이면 전 구간이다.
    """

    def __init__(self, selected: frozenset[str] | None = None, scope: str = "") -> None:
        self.stages: list[dict[str, Any]] = []
        self.selected = selected
        self.scope = scope

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
        out_of_scope = self.selected is not None and name not in self.selected
        missing = [r for r in requires if not self.ok(r)]
        if out_of_scope or missing:
            self.record(name, "not_run",
                        f"실행 범위 밖이다({self.scope or '선택한 단계'}) — 시도하지 않았다" if out_of_scope
                        else f"선행 단계가 ok 가 아니다: {', '.join(missing)}")
            # contextmanager 는 본문을 건너뛸 수 없다. 본문은 첫 줄에서 `skip_if_not_run` 을 불러
            # `_SkipBody` 로 빠져나오고, 여기서 삼킨다.
            try:
                yield
            except _SkipBody:
                return
            if out_of_scope:  # 범위 밖인데 본문이 돌았다 — 그 본문에 skip_if_not_run 이 없다
                raise RuntimeError(f"단계 {name} 는 실행 범위 밖인데 본문이 실행됐다 (skip_if_not_run 없음)")
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


#: C_rule 의 정의(#170 · DR-170) — 산출물에 그대로 싣는다.
C_RULE_DEFINITION = (
    "C_rule = S1(상한 없음) 배정의 계획 비용 합 = Σ planning_costs(처치 단가 + 메시지) × 배정 수. "
    "쿠폰 전량 사용 가정의 상한이고 캠페인 고정비는 넣지 않는다. S2~S5 도 같은 계획 비용으로 차감한다"
)


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
                   basis: CostBasis | None) -> dict[str, Any]:
    """S2~S5 의 `plan` 예산. 기본은 **C_rule**(``C_RULE_DEFINITION`` — #170 · DR-170)이다.

    우선순위: `--budget-krw`(변동비 plan 예산 — 캠페인 고정비 제외, 그대로 쓴다. 탐색용) → C_rule.
    **`--budget-krw` 가 없고 S1 계획 비용도 없으면 예산을 정하지 않는다** — ``planning_budget_krw`` 가
    ``None`` 이고 ``status: not_run`` 이다. 설계 추정치(data_spec §12.2)로 메우면 예산 단위(기대 비용)와
    배정 차감 단위(전량 사용 상한)가 섞이고 S1 과 같은 예산도 아니다(#170 D2 · #204).
    `--budget-krw` 가 있으면 S1 이 없어도 ``status: ok`` · ``c_rule_planned_krw: None`` 이다 — 기본 동일
    예산 비교(C_rule)가 아니라 명시 예산 독립 탐색이다. C_rule 이 없으므로 ``budget_guardrail`` 은 판정하지
    않고(``triggered: None``), S1 단계가 실패했으면 ``roi_summary`` 도 선행 조건 미충족으로 not_run 이다
    (DR-170 D2).
    S1 의 실측 marketing_cost 는 참고로만 적는다 — C_rule 대조는 ``budget_guardrail`` 이 한다.
    """
    fixed = basis.campaign_fixed_cost_krw if basis is not None else None
    s1_metrics = (s1_entry or {}).get("metrics") or {}
    planned = (s1_entry or {}).get("planned_cost_krw")
    status, reason = "ok", None
    planning: float | None
    if explicit_krw is not None:
        planning = float(explicit_krw)
        source = ("--budget-krw 인자 — 변동비 plan 예산(캠페인 고정비 제외)으로 그대로 쓴다. "
                  "탐색용이며 정식 비교(GATE 2)의 예산은 C_rule 이다")
    elif planned is not None:
        planning = float(planned)
        source = "C_rule = S1(상한 없음) 배정의 계획 비용 합 (planning_costs: 처치 단가 + 메시지, 쿠폰 전량 사용 가정 상한)"
    else:
        planning, source, status = None, None, "not_run"
        reason = ("S1 계획 비용(C_rule)이 없다 — S1 단계가 성공하지 못했거나 처치 비용 근거가 없다. "
                  "S2~S5 를 S1 과 같은 예산으로 비교할 수 없어 실행하지 않는다(설계 추정치로 메우지 않는다, #170)")
    return {
        "status": status,
        "reason": reason,
        "planning_budget_krw": max(planning, 0.0) if planning is not None else None,
        "c_rule_planned_krw": float(planned) if planned is not None else None,
        "c_rule_definition": C_RULE_DEFINITION,
        "s1_realized_marketing_cost_krw": s1_metrics.get("sim_marketing_cost"),
        "campaign_fixed_cost_krw": fixed,
        "note": "S1 은 상한 없이(None) 실행한다. 캠페인 고정비는 고객 단위가 아니어서 plan 예산에 넣지 않는다",
        "source": source,
    }


#: data_spec §14.1 가드레일 `Marketing Cost ≤ C_rule` 의 비교 범위(#170 D4 · DR-170).
BUDGET_GUARDRAIL_SCOPE = (
    "변동 마케팅비(메시지 + 쿠폰) ≤ C_rule — 양쪽 모두 캠페인 고정비 제외. 계획 = 이 분기 배정의 계획 비용 합, "
    "실현 = 측정 계층 message_cost + coupon_cost(시뮬레이터 출처, 분기 창)"
)
#: 계획 비용 합은 원 단위 정수의 합이지만 float 로 더한다 — 비교 허용 오차.
_BUDGET_TOLERANCE_KRW = 1e-6


def budget_guardrail(entry: Mapping[str, Any], c_rule_krw: float | None) -> dict[str, Any]:
    """data_spec §14.1 가드레일 `Marketing Cost ≤ C_rule` — 전략 분기 하나(#170 D4).

    C_rule 과 같은 단위(``BUDGET_GUARDRAIL_SCOPE``)로 계획 · 실현 둘 다 대조한다.
    ``triggered`` 는 ``True``(어느 쪽이든 초과) · ``False``(둘 다 대조했고 초과 없음) · ``None``(판정 못 함).
    한쪽만 대조했고 초과가 없으면 ``None`` 이다 — 대조하지 않은 쪽을 안전하다고 보고하지 않는다.
    """
    def judged(value: Any, reason: str | None) -> dict[str, Any]:
        if value is None or c_rule_krw is None:
            why = reason if value is None else "C_rule 이 없다"
            return {"value_krw": value, "exceeded": None, "reason": why}
        return {"value_krw": float(value), "exceeded": float(value) > float(c_rule_krw) + _BUDGET_TOLERANCE_KRW,
                "reason": None}

    planned = entry.get("planned_cost_krw")
    planned_check = judged(planned, None if planned is not None else "계획 비용이 없다(배정 또는 비용 근거 없음)")

    observation = (entry.get("economics_input_observation") or {}).get("status")
    record = entry.get("measured_economics")
    parts = {key: measured_value(record, key) for key in ("message_cost", "coupon_cost")}
    if observation != "ok":
        realized, why = None, "경제 지표 정식 입력의 관측 근거 미충족(economics_input_observation)"
    elif any(value is None for value in parts.values()):
        missing = sorted(key for key, value in parts.items() if value is None)
        realized, why = None, f"측정 계층 {missing} 계산 불가 — {(record or {}).get('status', '기록 없음')}"
    else:
        realized, why = float(parts["message_cost"]) + float(parts["coupon_cost"]), None
    realized_check = judged(realized, why)

    flags = [planned_check["exceeded"], realized_check["exceeded"]]
    triggered = True if True in flags else (False if all(f is False for f in flags) else None)
    return {
        "status": "ok" if triggered is not None else "not_run",
        "triggered": triggered,
        "c_rule_krw": float(c_rule_krw) if c_rule_krw is not None else None,
        "planned": planned_check,
        "realized_variable": realized_check,
        "scope": BUDGET_GUARDRAIL_SCOPE,
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


def write_assignment_file(path: Path, assigned_at: datetime, assignments: Mapping[str, str],
                          **extra: Any) -> Path:
    """배정 기록 — `{"assigned_at": ISO+오프셋, "assignments": {cid: tid}}` (realism_check `--assignments`)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"assigned_at": assigned_at.isoformat(), "assignments": dict(sorted(assignments.items())), **extra}
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    return path


@contextmanager
def override_attr(module_name: str, attr: str, value: Any) -> Iterator[dict[str, Any]]:
    """의사결정 모듈의 상수를 이 블록 동안만 바꾸고 되돌린다. 없는 이름이면 바꾸지 않고 그 사실을 적는다."""
    record: dict[str, Any] = {"target": f"{module_name}.{attr}", "requested": value}
    if value is None:
        record["applied"] = False
        yield record
        return
    module = importlib.import_module(module_name)
    if not hasattr(module, attr):
        record.update(applied=False, reason="모듈에 그 이름이 없다")
        yield record
        return
    original = getattr(module, attr)
    record.update(applied=True, default=original)
    setattr(module, attr, value)
    try:
        yield record
    finally:
        setattr(module, attr, original)


def stratified_cap(X: Any, y: Any, max_rows: int | None, seed: int) -> tuple[Any, Any, dict[str, Any]]:
    """학습 표본 상한 — 클래스 비율을 유지해 `max_rows` 건 근처로 줄인다(같은 seed 면 같은 표본)."""
    n = int(len(y))
    if max_rows is None or n <= max_rows:
        return X, y, {"applied": False, "n": n, "max_rows": max_rows}
    frac = max_rows / n
    picked = y.groupby(y, group_keys=False).sample(frac=frac, random_state=seed).index.sort_values()
    return X.loc[picked], y.loc[picked], {
        "applied": True, "n_before": n, "n": int(len(picked)), "max_rows": max_rows,
        "method": f"클래스별 비율 유지 무작위 추출(random_state={seed})",
    }


# ── 이벤트 읽기 ─────────────────────────────────────────────────────────────


def _pd():
    try:
        import pandas as pd  # 지연 import — 의존성 없는 CI 에서 정적 검사를 허용한다
    except ImportError as error:
        missing = getattr(error, "name", None) or str(error)
        raise NotRun(f"이벤트 처리의 필수 패키지를 불러올 수 없다: {missing}") from error

    return pd


def outcome_observation_status(index_time, window_days: int, observation: Mapping | None) -> dict:
    """계약 판정을 그대로 위임하고 필수 패키지 부재만 실행 상태로 변환한다 (#179 NB2)."""
    try:
        return _contract_observation_status(index_time, window_days, observation)
    except ImportError as error:
        missing = getattr(error, "name", None) or str(error)
        raise NotRun(f"관측 판정의 필수 패키지를 불러올 수 없다: {missing}") from error


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
        self._last_read = None
        self._snapshots: dict[str, dict[str, Any]] = {}
        self._active_branch = None
        try:
            self._load_events = decision_fn("load_events")
            self.source = "src.decision.data.load_events"
            self.fallback_reason = None
        except NotRun as reason:
            self._load_events = None
            self.source = "src.simulator.api.events"
            self.fallback_reason = str(reason)

    @staticmethod
    def _frame_signature(frame: Any) -> str:
        """변환 결과를 재계산하지 않고 이미 받은 history의 변경만 감지한다."""
        digest = hashlib.sha256()
        digest.update(repr([(str(c), str(d)) for c, d in zip(frame.columns, frame.dtypes)]).encode())
        digest.update(_pd().util.hash_pandas_object(frame, index=True).to_numpy().tobytes())
        digest.update(json.dumps(frame.attrs.get("run_read_evidence"), sort_keys=True).encode())
        return digest.hexdigest()

    @staticmethod
    def _unchanged_files(root: Path, proof: Mapping) -> None:
        for name, signature in proof.get("fingerprints", {}).items():
            stat = (root / name).stat()
            if [stat.st_size, stat.st_mtime_ns] != signature:
                raise NotRun("읽기 도중 이벤트 파일이 바뀌었다")

    def _check_history(self, capture: Mapping, *, verify_files: bool = True) -> None:
        if self._frame_signature(capture["history"]) != capture["signature"]:
            raise NotRun("스냅샷에 결속한 history 내용 또는 읽기 근거가 바뀌었다")
        proof = capture["proof"]
        if verify_files:
            current = verify_event_run(Path(proof["root"]), proof["run_id"])
            if current != proof:
                raise NotRun("스냅샷 본선의 실행·파일 근거가 바뀌었거나 검증되지 않는다")
        else:
            self._unchanged_files(Path(proof["root"]), proof)

    def snapshot(self, history: Any, until: datetime) -> str:
        """이 리더가 방금 검증한 본선 읽기에 공개 스냅샷을 결속한다."""
        last = self._last_read
        if last is None or last["history"] is not history or last["until"] != until:
            raise NotRun("이 리더의 최근 본선 읽기와 스냅샷 history·시각이 다르다")
        if last["proof"].get("status") != "ok":
            raise NotRun("스냅샷에는 검증된 본선 실행이 필요하다")
        self._check_history(last)
        self._active_branch = None
        from src.measurement.sink import read_events
        hashes = [event_content_hash(row) for row in read_events(Path(last["proof"]["root"]))]
        expected = event_content_digest(hashes)
        actual = event_content_digest([event_content_hash(row) for row in sim.events(until)])
        if expected != actual:
            raise NotRun("활성 세계의 공개 이력이 검증된 본선 내용과 다르다")
        self._check_history(last)
        token = sim.snapshot()
        if not isinstance(token, str):
            raise NotRun("공개 snapshot 토큰이 문자열이 아니다")
        self._snapshots[token] = {**last, "raw_hashes": hashes, "raw_content": expected}
        return token

    def restore(self, token: str, *, output_root: Path) -> None:
        """불투명 토큰을 공개 API에 그대로 넘긴다. 실패한 복원은 연결 근거가 아니다."""
        self._active_branch = None
        capture = self._snapshots.get(token)
        if capture is None:
            raise NotRun("이 리더가 history에 결속하지 않은 스냅샷이다")
        self._check_history(capture)
        sim.restore(token, output_root=output_root)
        self._active_branch = {"capture": capture, "root": Path(output_root).resolve(),
                               "snapshot_reference": hashlib.sha256(token.encode()).hexdigest(),
                               "summary": None}

    def advance(self, days: int) -> Any:
        """성공한 복원 뒤의 실제 RunSummary만 분기 읽기에 사용한다."""
        context = self._active_branch
        self._active_branch = None
        if context is None or context["summary"] is not None:
            raise NotRun("새로운 restore 뒤에 한 번 advance해야 한다")
        summary = sim.advance(days)
        context["summary"] = {k: getattr(summary, k, None) for k in ("run_id", "start", "end")}
        self._active_branch = context
        return summary

    def _branch_proof(self, context: Mapping, root: Path, run_id: str | None,
                      until: datetime, history: Any) -> dict:
        capture, summary = context["capture"], context["summary"]
        if (summary is None or root.resolve() != context["root"] or history is not capture["history"]
                or run_id != summary["run_id"] or until != summary["end"]
                or summary["start"] != capture["until"] or until <= capture["until"]):
            raise NotRun("복원·진행 기록과 분기 root·run_id·history·관측 창이 다르다")
        self._check_history(capture)
        parent = capture["proof"]
        # root-local 사슬은 독립 검증. 명시적 외부 부모는 기존 정확한 머리 검사로만 해소한다.
        proof = verify_event_run(root, run_id)
        if proof.get("status") != "ok":
            root_local_reason = proof.get("reason")
            proof = verify_event_run(root, run_id, history_evidence=parent)
            if proof.get("status") != "ok":
                raise NotRun("이벤트 원시 읽기 근거 미충족: "
                             f"root-local 검증: {root_local_reason}; history 검증: {proof.get('reason')}")
            local_ids = set(proof["verified_run_ids"]) - set(parent["verified_run_ids"])
        else:
            local_ids = set(proof["verified_run_ids"])
            if local_ids & set(parent["verified_run_ids"]):
                raise NotRun("분기와 history가 같은 실행 ID를 중복 주장한다")
        rejections = {**parent["run_rejections"], **proof["run_rejections"]}
        proof.update(verified_run_ids=sorted(rejections), run_rejections=rejections,
                     chain_rejected_total=sum(rejections.values()),
                     ancestor_rejected_total=sum(v for k, v in rejections.items() if k != run_id),
                     history_head_run_id=parent["run_id"], history_link_status="pending_public_stream",
                     history_link_method="controlled-snapshot-restore-advance-events-v1",
                     snapshot_reference=context["snapshot_reference"], branch_run_ids=sorted(local_ids),
                     snapshot_until=capture["until"].isoformat(),
                     summary_start=summary["start"].isoformat(), summary_end=until.isoformat())
        return proof

    def read(self, root: Path, until: datetime, history: Any = None, *, run_id: str | None = None) -> Any:
        """일반 파일 경로는 정확한 부모, 통제된 복원 분기는 공개 API 전량 읽기를 함께 요구한다."""
        root = Path(root)
        context = self._active_branch
        self._active_branch = None  # 실패·오입력·중간 오류 뒤 같은 연결을 재사용하지 않는다.
        proof = {"status": "not_run", "reason": "실행 ID 미제공", "verified_run_ids": []}
        history_proof = history.attrs.get("run_read_evidence") if history is not None else None
        if history is not None and (run_id is None or not isinstance(history_proof, Mapping)
                                    or history_proof.get("status") != "ok"):
            raise NotRun("분기 실행 ID와 검증된 history 머리 근거가 필요하다")
        if context is not None:
            proof = self._branch_proof(context, root, run_id, until, history)
        elif run_id is not None:
            proof = verify_event_run(root, run_id, history_evidence=history_proof)
            if proof.get("status") != "ok":
                raise NotRun(f"이벤트 원시 읽기 근거 미충족: {proof.get('reason')}")
        try:
            observed_hashes = []
            if context is not None:
                from src.measurement.sink import read_events
                raw_hashes = [event_content_hash(row) for row in read_events(root)]
                expected_content = event_content_digest(context["capture"]["raw_hashes"] + raw_hashes)

            def checked_stream():
                for record in sim.events(until):
                    if context is not None:
                        observed_hashes.append(event_content_hash(record))
                    yield record

            if self._load_events is None:
                frame = frame_from_stream(checked_stream())
            else:
                if context is not None:
                    for _ in checked_stream():
                        pass  # 전량 정상 종료가 필수. 일부만 소비하거나 예외를 삼키지 않는다.
                if proof.get("status") == "ok" and not proof.get("fingerprints") and proof.get("raw_rows") == 0:
                    frame = self._load_events(root, allow_verified_empty=True)
                else:
                    frame = self._load_events(root)
            self._unchanged_files(root, proof)
            if context is not None:
                actual_content = event_content_digest(observed_hashes)
                if actual_content != expected_content:
                    raise NotRun("공개 이벤트 전량이 검증된 history·분기 내용과 다르다")
                self._check_history(context["capture"])
                # 읽기 사이 실행 기록도 바뀌지 않았는지 같은 검증으로 확인한다.
                if self._branch_proof(context, root, run_id, until, history) != proof:
                    raise NotRun("분기 읽기 도중 실행 근거가 바뀌었다")
                proof["history_link_status"] = "ok"
                proof["public_stream_complete"] = True
                proof["public_stream_content"] = actual_content
                proof["history_content"] = context["capture"]["raw_content"]
        except (OSError, ValueError) as error:
            raise NotRun(f"이벤트 읽기를 완료하지 못했다: {type(error).__name__}: {error}") from error
        if history is not None and self._load_events is not None:
            frame = _pd().concat([history, frame], ignore_index=True)
        frame.attrs.update(run_read_evidence=proof, verified_run_ids=proof.get("verified_run_ids", []))
        if history is None and proof.get("status") == "ok":
            self._last_read = {"history": frame, "until": until, "signature": self._frame_signature(frame),
                               "proof": json.loads(json.dumps(proof))}
        return frame


def observed_values(frame: Any, column: str) -> list[Any]:
    if frame is None or column not in getattr(frame, "columns", ()):
        return []
    return sorted({v for v in frame[column].dropna().unique().tolist()}, key=str)


def customer_signups(until: datetime) -> dict[str, Any]:
    """활성 세계의 고객 명부 — ``sim.exchange_bundle(until)`` 의 ``customers.signup_date`` (교환 계약 v1).

    이벤트 계약에는 가입일이 없다(measurement_contract §6.4). 명부는 공개 계약이고 측정 계층
    ``exchange.read_exchange`` 로 읽는다. 받지 못하면 ``NotRun`` — 가입일을 다른 값으로 근사하지 않는다.
    """
    from src.measurement import exchange as ex
    from src.measurement.sink import EventSource

    bundle = sim.exchange_bundle(until)
    if bundle.get("status") != "ok":
        raise NotRun(f"sim.exchange_bundle 상태 {bundle.get('status')!r} — 가입일 명부가 없다")
    read = ex.read_exchange(Path(str(bundle["path"])), EventSource.SIMULATOR)
    if read is None:
        raise NotRun("교환 묶음을 읽지 못했다 — 가입일 명부가 없다")
    return dict(read.signup_dates)


def _kst_dates(stamps: Any) -> Any:
    """이벤트 시각 → KST 날짜. 시각이 naive 면 이미 KST 다(측정 계층이 저장 시 정규화한다)."""
    if stamps.dt.tz is not None:
        stamps = stamps.dt.tz_convert(KST)
    return stamps.dt.date


def eligibility(events: Any, index_time: datetime, population: Any,
                signups: Mapping[str, Any]) -> dict[str, Any]:
    """``population`` 고객의 data_spec §4.1 Eligible 여부(``ELIGIBLE_DEFINITION``) — ``index_time`` 미만 이벤트만 본다.

    - 가입일이 명부에 없는 고객은 **Eligible 이 아니다**(판정할 수 없다). 그 수를 ``n_signup_missing`` 에 남긴다.
    - 구매는 ``purchase`` 이벤트이고, 같은 ``order_id`` 는 1건이다.
    반환: ``flags``(Series, bool) · ``counts``(모집단 · Eligible · 조건별 탈락 수 — 한 고객이 여러 조건에 걸릴 수 있다).
    """
    pd = _pd()
    stamps = _timestamps(events)
    end = index_time if stamps.dt.tz is not None else index_time.astimezone(KST).replace(tzinfo=None)
    t0_day = index_time.astimezone(KST).date()
    before = events.loc[stamps < end].assign(_day=_kst_dates(stamps[stamps < end]))
    purchases = before[before["event_type"] == "purchase"]
    key = purchases["order_id"].where(purchases["order_id"].notna(), "evt:" + purchases["event_id"].astype(str))
    orders = purchases.assign(_key=key).drop_duplicates(subset=["customer_id", "_key"])
    count = orders.groupby("customer_id").size().reindex(population, fill_value=0)
    last_day = orders.groupby("customer_id")["_day"].max().reindex(population)
    signup = pd.Series([signups.get(cid) for cid in population], index=population, dtype=object)
    tenure = pd.Series([None if d is None else (t0_day - d).days for d in signup], index=population, dtype=float)
    recency = pd.Series([None if pd.isna(d) else (t0_day - d).days for d in last_day], index=population, dtype=float)
    tenure_ok = tenure >= ELIGIBLE_MIN_TENURE_DAYS
    orders_ok = count >= ELIGIBLE_MIN_ORDERS
    recency_ok = recency >= ELIGIBLE_MIN_DAYS_SINCE_PURCHASE
    flags = (tenure_ok & orders_ok & recency_ok).astype(bool).rename("eligible")
    return {
        "flags": flags,
        "counts": {
            "n_population": int(len(population)),
            "n_eligible": int(flags.sum()),
            "n_signup_missing": int(signup.isna().sum()),
            "n_excluded_tenure": int((~tenure_ok).sum()),
            "n_excluded_no_purchase": int((~orders_ok).sum()),
            "n_excluded_recent_purchase": int((orders_ok & ~recency_ok).sum()),
        },
    }


def event_count_by_type(frame: Any) -> dict[str, int]:
    if frame is None or "event_type" not in getattr(frame, "columns", ()):
        return {}
    return {str(k): int(v) for k, v in frame["event_type"].value_counts().sort_index().items()}


def s1_inputs(events: Any, index_time: datetime, population: Any, eligible: Any) -> dict[str, Any]:
    """S1 규칙 입력 — `index_time` 미만 이벤트에서 고객별로 계산한다.

    - ``days_since_last_purchase``: 마지막 주문부터의 일수(소수). 주문이 없으면 NaN(0 으로 채우지 않는다).
      S1 규칙(28~90일)이 이 값을 쓴다 — Eligible 의 날짜 차와는 따로다(DR-234).
    - ``lifetime_order_count``: 주문 수(``purchase`` 1행 = 주문 1건, 같은 order_id 는 1건).
    - ``eligible``: 호출자가 ``eligibility`` 로 낸 플래그를 ``population`` 에 맞춰 싣는다(data_spec §4.1).

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
    return {
        "days_since_last_purchase": pd.Series(days.to_numpy(), index=population, name="days_since_last_purchase"),
        "lifetime_order_count": pd.Series(count.to_numpy(), index=population, name="lifetime_order_count"),
        "eligible": eligible.reindex(population, fill_value=False).astype(bool).rename("eligible"),
    }


def purchase_generated(metrics: Mapping[str, Any] | None) -> tuple[bool | None, str]:
    """해당 세계의 원본 MetricValue로 구매 관측 상태를 판정한다 — JSON 변환 전 호출한다.

    `ok` 의 0 은 측정된 0 이고, `not_run` 이면 이 판이 만들지 않는 유형이다.
    """
    if metrics is None:
        return None, "sim.metrics 를 얻지 못했다"
    metric = metrics.get("events.purchase")
    if metric is None:
        return None, "sim.metrics 에 events.purchase 가 없다"
    status = getattr(metric, "status", None)
    reason = getattr(metric, "reason_code", None)
    status = getattr(status, "value", status)
    reason = getattr(reason, "value", reason)
    generated = True if status == "ok" else False if status == "not_run" else None
    return generated, f"events.purchase: {status}" + (f" / {reason}" if reason else "")


def outcome_observation(summary: Any, raw_root: Path, metrics: Mapping[str, Any] | None,
                        read_evidence: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """공개 RunSummary와 같은 실행의 측정 기록을 읽어 decision에 전달한다 (#179)."""
    from src.measurement import sink

    run_id = getattr(summary, "run_id", None)
    rejected, detail = None, "같은 실행의 읽을 수 있는 기록이 정확히 하나 필요하다"
    try:
        matches = [r for r in sink.run_records(raw_root)
                   if isinstance(r, Mapping) and isinstance(run_id, str) and r.get("run_id") == run_id]
        if len(matches) == 1 and "unreadable" not in matches[0]:
            value = matches[0].get("rejected")
            if type(value) is int and value >= 0:
                rejected, detail = value, None
    except (OSError, ValueError, TypeError) as error:
        detail = f"측정 실행 기록 읽기 실패: {type(error).__name__}: {error}"
    generated, purchase_detail = purchase_generated(metrics)
    if read_evidence is None:
        read_evidence = verify_event_run(raw_root, run_id)
    return {"start": getattr(summary, "start", None), "end": getattr(summary, "end", None),
            "run_id": run_id, "rejected": rejected, "write_detail": detail,
            "read_complete": (read_evidence.get("status") == "ok" and read_evidence.get("run_id") == run_id
                              and read_evidence.get("root") == str(Path(raw_root).resolve())
                              and type(read_evidence.get("rejected")) is int and read_evidence["rejected"] == rejected),
            "read_detail": read_evidence.get("reason"), "root": str(Path(raw_root).resolve()),
            "purchase_generated": generated, "purchase_detail": purchase_detail}


def margin_rate_basis(metrics: Mapping[str, Any] | None) -> tuple[float | None, dict[str, Any]]:
    """S4·S5 가치(CLV × margin_rate)에 쓸 기여이익률과 그 근거.

    1. 측정 계층 실현값 — 본선 `contribution_profit / revenue` (둘 다 ok, 매출 > 0).
    2. economic_config `product_margin` 의 매출 가중 평균(카테고리 빈도 × 중앙 가격 가중).
       **생성 파라미터를 계획 가정으로 쓴 것**이며 실현 마진이 아니다. 회계(economics.py)에는 쓰지 않는다(EC-1).
    """
    def ok_value(key: str) -> float | None:
        metric = (metrics or {}).get(key)
        if metric is None or getattr(metric.status, "value", metric.status) != "ok":
            return None
        return float(metric.value)

    profit, revenue = ok_value("contribution_profit"), ok_value("revenue")
    if profit is not None and revenue:
        return profit / revenue, {"status": "ok", "value": profit / revenue,
                                  "source": "측정 계층 실현 기여이익률 = contribution_profit / revenue (본선 시작~t2)"}
    try:
        from src.measurement import config_loader

        categories = config_loader.load_economic_config(ECONOMIC_CONFIG).product_generation.categories
    except Exception as error:  # noqa: BLE001
        return None, {"status": "not_run", "value": None,
                      "reason": f"측정 계층 값도 economic_config 도 없다: {type(error).__name__}: {error}"}
    weights = {k: c.frequency_weight * c.median_price_krw for k, c in categories.items()}
    total = sum(weights.values())
    rate = sum(categories[k].margin_rate * w for k, w in weights.items()) / total
    return rate, {
        "status": "ok", "value": rate,
        "source": "economic_config product_margin 매출 가중 평균(frequency_weight × median_price_krw) — "
                  "측정 계층 실현 기여이익률이 없어(구매 미생성) 생성 파라미터를 계획 가정으로 썼다. 실현 마진이 아니다",
    }


def two_classes(series: Any) -> bool:
    return series is not None and series.dropna().nunique() >= 2


# ── 실측 기여이익 — 분기별 교환 묶음 → 측정 계층 (#169 · DR-169) ─────────────────


def branch_raw_root(out: Path, strategy: str) -> Path:
    """전략 분기의 Sink 루트. 분기마다 **부모 폴더를 따로** 둔다.

    ``sim.exchange_bundle`` 은 활성 세계 출력 루트의 형제 ``simulator_exchange/`` 에 묶음을 쓴다
    (``docs/simulator_api.md``). 분기 루트가 한 부모 아래 있으면 마지막 분기가 앞 분기의 묶음을
    덮어써 분기별 원가 근거를 디스크에서 대조할 수 없다(DR-169). 이렇게 두면 묶음 위치가 측정
    계층 기본값(``exchange.default_roots`` — Sink 루트의 형제)과도 같다.
    """
    return out / "branches" / strategy / "raw"


#: 측정 계층 경제 지표의 조립(``publish.assemble_orders`` · ``assemble_campaign``)이 읽는 이벤트 —
#: 이 유형이거나 ``campaign_id`` 가 있는 이벤트. 나머지는 경제 지표에 영향이 없어 거른다(분기 창 이벤트가
#: 20K 실행에서 1.4M 건이다 — 전량 dict 로 들지 않는다). 조립이 다른 이벤트를 읽기 시작하면
#: ``tests/test_orchestration_sprint.py`` 의 전량 대조가 실패한다.
ECONOMIC_EVENT_TYPES = frozenset({"purchase", "coupon_use", "push_sent"})
#: ``build_kpi_report`` 에서 꺼내 남기는 경제 지표 — 기여이익과 그 구성요소.
ECONOMIC_METRICS: tuple[str, ...] = (
    "revenue", "cogs", "shipping_subsidy", "message_cost", "coupon_cost", "campaign_fixed_cost",
    "marketing_cost", "contribution_profit",
)
#: ``roi.summarize_strategy`` 에 ``measured_<이름>`` 으로 넘기는 지표.
MEASURED_KEYS: tuple[str, ...] = ("revenue", "marketing_cost", "contribution_profit")


def economic_events(raw_root: Path) -> list[dict[str, object]]:
    """``raw_root`` 의 이벤트 중 경제 지표 조립이 읽는 것만(``ECONOMIC_EVENT_TYPES`` 또는 ``campaign_id`` 보유)."""
    from src.measurement import sink

    return [
        event for event in sink.read_events(raw_root)
        if event.get("event_type") in ECONOMIC_EVENT_TYPES or isinstance(event.get("campaign_id"), str)
    ]


#: 분기 창 DQ-09 가 구조상 잡지 못하는 것 — 산출물에 그대로 싣는다(통과로 읽히지 않게).
WINDOW_AMOUNT_CHECK_GAP = (
    "묶음에만 있고 분기 창 purchase 이벤트가 빠진 주문 — 로더의 ExchangeOrder 가 주문 시각(계약의 "
    "ordered_at)을 돌려주지 않아 그 주문이 창 안인지 알 수 없다. 이벤트에만 있고 묶음에 없는 주문은 "
    "이 검사가 아니라 contribution_profit 의 NO_COST_BASIS 가 막는다. 같은 주문의 purchase 가 여럿이면 "
    "마지막 금액만 대조한다 — 그 경우는 single_purchase_check(DQ-02b)가 막는다"
)

#: 분기 창 DQ-02b 가 구조상 잡지 못하는 것.
WINDOW_SINGLE_PURCHASE_GAP = (
    "분기 창 밖(분기 이전 계보)에 같은 주문 ID 의 purchase 가 있는 경우 — 분기 창 이벤트만 읽는다"
)

#: 분기 기록에서 하나라도 ``fail`` 이면 ``quality_failed`` 인 검사 — (기록 키, 사유에 쓰는 이름).
BRANCH_QUALITY_CHECKS = (("amount_check", "금액 대조"), ("single_purchase_check", "주문당 purchase 1건"))


def _check_record(result: Any) -> dict[str, Any]:
    return {"check": result.id, "status": result.status, "examined_rows": result.examined_rows,
            "violations": result.violations, "samples": list(result.samples),
            "reason_detail": result.reason_detail}


def window_amount_check(bundle: Any, simulator_events: Any) -> dict[str, Any]:
    """분기 창의 ``DQ-09`` — 묶음을 **이 창의 시뮬레이터 purchase 주문 ID** 로 좁혀 측정 계층 검사에 넘긴다 (#237 R1).

    묶음은 계보 전량, 이벤트는 분기 창뿐이라 그대로 넘기면 창 이전 주문이 전부 "purchase 없음"
    거짓 위반이 된다. 창의 주문만 남긴 읽기 전용 뷰를 ``validate.check_amount_equation`` 에
    그대로 넘긴다 — 대조 규칙(품목 등식 · 이벤트 금액)은 측정 계층 한 벌이다.
    ``simulator_events`` 는 **시뮬레이터 출처만** 이어야 한다 — 같은 주문 ID 의 커머스 이벤트와
    대조하면 다른 출처의 금액으로 거짓 위반이 난다(#116 · #117).
    """
    from src.measurement import validate

    window_ids = {
        event.get("order_id") for event in simulator_events
        if event.get("event_type") == "purchase" and event.get("order_id") is not None
    }
    view = dataclasses.replace(
        bundle, orders={order_id: order for order_id, order in bundle.orders.items() if order_id in window_ids},
    )
    counts = {
        "n_window_purchase_orders": len(window_ids),
        "n_bundle_orders": len(bundle.orders),
        "n_bundle_orders_outside_window": len(bundle.orders) - len(view.orders),
        "n_window_orders_missing_from_bundle": len(window_ids - set(bundle.orders)),
        "not_detected": WINDOW_AMOUNT_CHECK_GAP,
    }
    if not view.orders:
        # check_amount_equation 은 대조한 주문이 0건이면 "purchase 가 없다"는 사유를 낸다 — 이 경우와 다르다.
        reason = ("분기 창에 시뮬레이터 purchase 가 없다" if not window_ids else
                  f"분기 창 주문 {len(window_ids)}건이 묶음에 하나도 없다 — 대조할 상대가 없다(원가는 NO_COST_BASIS)")
        return {"check": "DQ-09", "status": "not_run", "examined_rows": 0, "violations": None,
                "samples": [], "reason_detail": reason, **counts}
    result = validate.check_amount_equation([(view, simulator_events)])
    return {**_check_record(result), **counts}


def window_single_purchase_check(simulator_events: Any) -> dict[str, Any]:
    """분기 창의 ``DQ-02b`` — 주문 ID 당 시뮬레이터 purchase 1건 (#237 R3).

    ``DQ-09`` 는 같은 주문의 purchase 가 여럿이면 마지막 금액만 대조한다. 앞선 이벤트 금액이 틀려도
    마지막이 묶음과 맞으면 통과하고, 순서를 뒤집으면 실패한다 — 측정 계층 ``validate.run_all`` 이 두
    검사를 함께 돌리는 이유다. 같은 검사(``validate.check_order_id_single_purchase``)를 그대로 건다.
    ``simulator_events`` 는 **시뮬레이터 출처만** 이어야 한다 — 같은 주문 ID 의 커머스 이벤트까지 세면
    거짓 위반이다(#116 · #117).
    """
    from src.measurement import validate

    result = validate.check_order_id_single_purchase(simulator_events)
    return {**_check_record(result), "not_detected": WINDOW_SINGLE_PURCHASE_GAP}


def measured_economics(raw_root: Path, bundle_root: Path, index_date: Any,
                       events: list[dict[str, object]] | None = None) -> dict[str, Any]:
    """분기 창의 경제 지표 — 측정 계층 ``publish.build_kpi_report`` 를 **그대로** 부르고 시뮬레이터 출처 값만 꺼낸다.

    게시물 ``kpi_report`` 의 기여이익과 같은 함수·같은 조립이다(정의가 두 벌이 되지 않는다).
    묶음이 없으면 측정 계층이 ``contribution_profit`` 을 ``NO_COST_BASIS`` 로 낸다 — 그대로 싣는다.
    ``index_date`` 는 경제 지표에 쓰이지 않는다(``build_kpi_report`` 의 다른 지표용 인자).
    금액 대조(``DQ-09``)는 ``amount_check`` 에, 주문당 purchase 1건(``DQ-02b``)은 ``single_purchase_check``
    에 남긴다 — 어느 쪽이든 ``fail`` 이면 ``branch_economics`` 가 이 기록을 ``ok`` 로 두지 않는다(#237 R1 · R3).
    """
    from src.measurement import config_loader
    from src.measurement import exchange as ex
    from src.measurement import publish as mp
    from src.measurement.sink import EventSource

    config = config_loader.load_economic_config(ECONOMIC_CONFIG).cost_accounting
    bundle = ex.read_exchange(bundle_root, EventSource.SIMULATOR)
    events = economic_events(raw_root) if events is None else events
    split = mp.partition_by_source(events)
    source = EventSource.SIMULATOR.value
    report = mp.build_kpi_report(events, split, index_date=index_date, config=config,
                                 bundles={source: bundle} if bundle is not None else {})
    by_name = {entry["name"]: entry for entry in report["metrics"]}
    return {
        "source": "src.measurement.publish.build_kpi_report — 게시물 kpi_report 와 같은 함수·조립, "
                  "시뮬레이터 출처만(MEA-002)",
        "raw_root": raw_root,
        "bundle_root": bundle_root,
        "bundle": ({"status": "ok", "orders": len(bundle.orders), "generated_at": bundle.generated_at}
                   if bundle is not None else
                   {"status": "not_run", "reason": "교환 묶음이 없다 — 기여이익은 NO_COST_BASIS"}),
        "event_filter": f"event_type ∈ {sorted(ECONOMIC_EVENT_TYPES)} 또는 campaign_id 보유",
        "n_events_read": len(events),
        "n_simulator_events": len(split.simulator),
        "n_commerce_events_excluded": len(split.commerce),
        "amount_check": (window_amount_check(bundle, split.simulator) if bundle is not None else
                         {"check": "DQ-09", "status": "not_run", "reason_detail": "교환 묶음이 없다"}),
        "single_purchase_check": window_single_purchase_check(split.simulator),
        "metrics": {name: by_name[name]["value"]["by_source"][source] for name in ECONOMIC_METRICS},
    }


def branch_economics(raw_root: Path, end: datetime) -> dict[str, Any]:
    """활성 분기 세계의 묶음을 받고(``sim.exchange_bundle``) 측정 계층으로 경제 지표를 낸다.

    실패해도 분기 단계를 멈추지 않는다 — ``status: failed`` 와 사유를 남기고, 그때 ``measured_*``
    는 ``None`` 이라 증분이익은 계산 불가가 된다(0 으로 채우지 않는다).
    분기 창 품질 검사(``BRANCH_QUALITY_CHECKS`` — ``DQ-09`` · ``DQ-02b``) 중 하나라도 ``fail`` 이면
    ``status: quality_failed`` — 값과 근거는 그대로 남기되 ``measured_value`` 가 꺼내지 않아 이 분기의
    정식 기여이익 · 증분이익 · ROI 가 계산 불가가 된다(#237 R1 · R3). 다른 분기는 각자 판정한다.
    """
    try:
        bundle = sim.exchange_bundle(end)
        if bundle.get("status") != "ok":
            return {"status": "not_run", "reason": f"sim.exchange_bundle 상태 {bundle.get('status')!r}"}
        last_day = (end - timedelta(days=1)).astimezone(KST).date()
        economics = measured_economics(raw_root, Path(str(bundle["path"])), last_day)
        failed = [f"{economics[key]['check']} {name} 실패 — {economics[key]['reason_detail']}"
                  for key, name in BRANCH_QUALITY_CHECKS if economics[key]["status"] == "fail"]
        if failed:
            return {"status": "quality_failed", "reason": "분기 창 " + " · ".join(failed), **economics}
        return {"status": "ok", "reason": None, **economics}
    except Exception as error:  # noqa: BLE001 — 기여이익만 계산 불가로 두고 분기는 계속한다
        traceback.print_exc(file=sys.stderr)
        return {"status": "failed", "reason": f"{type(error).__name__}: {error}"}


def measured_value(record: Mapping[str, Any] | None, key: str) -> Any:
    """``measured_economics`` 기록에서 ``ok`` 인 값만. 아니면 ``None``(0 이 아니다)."""
    if not record or record.get("status") != "ok":
        return None
    metric = (record.get("metrics") or {}).get(key) or {}
    return metric.get("value") if metric.get("status") == "ok" else None


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
# `src/orchestration/provenance.py` 로 옮겼다(#264 — ML 의존성 없이 검사가 돌게). 위 import 참조.


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
    run_id: str | None = None
    realism_report: Path = REALISM_REPORT
    cv_folds: int | None = None       # churn CV fold 수 덮어쓰기 — 없으면 model_config churn.cv_folds
    max_train_rows: int | None = None  # churn 학습·CV 표본 상한 — 없으면 전원
    # src/main.py --mode (#206). 기본값이면 이전과 같다 — 전 구간을 돌고 아무것도 넘기지 않는다.
    stages: frozenset[str] | None = None   # 실행할 단계 이름 — None 이면 전 구간
    scope: str = ""                        # 범위 밖 단계의 not_run 사유에 쓰는 이름 (예: "--mode train")
    capture: dict[str, Any] | None = None  # 실행 뒤 ctx(점수 · 예산)·비용·결과 폴더를 넘겨받을 곳
    require_clean: bool = False            # #262 — 커밋 전 변경이 있으면 시뮬레이션 전에 멈춘다(DirtyRepoError)
    # #214 — None 이면 이전과 같다(저장 · 불러오기 없음). src/main.py 는 기본으로 저장한다.
    models_root: Path | None = None        # 학습한 모델을 <models_root>/<run_id>/ 에 저장(ML-008)
    feature_store_root: Path | None = None  # Feature · 라벨을 <root>/<run_id>/ 에 저장(FS-001/002)
    load_models: Path | None = None        # 저장된 모델 폴더 — 주면 다시 학습하지 않고 불러와 평가만 한다


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


def call_plan(strategy: str, scores: Mapping[str, Any], budget: Any, costs: Any) -> Mapping[str, str]:
    """`strategies.plan` — 필요한 점수가 없어 `NotComputable` 이면 not_run 으로 바꾼다(빈 배정으로 대신하지 않는다)."""
    plan = decision_fn("plan")
    try:
        return plan(strategy, scores, budget, costs)
    except Exception as error:
        if type(error).__name__ == "NotComputable":
            raise NotRun(f"NotComputable: {error}") from error
        raise


def _strategy_name(strategy: str) -> str | None:
    try:
        module = importlib.import_module(DECISION_API["plan"][0])
    except ImportError:
        return None
    names = getattr(module, "STRATEGY_NAMES", None)
    return names.get(strategy) if isinstance(names, Mapping) else None


def dashboard_segments(rows: list[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """`segment_stats` 행 → 대시보드 키(id·name·n·share·avg_*). 원래 키도 함께 싣는다."""
    out = []
    for row in rows:
        out.append({
            "id": row.get("prd_id") or row.get("segment"), "name": row.get("segment"),
            "n": row.get("customer_count"), "share": row.get("ratio"),
            "avg_churn_p": row.get("average_churn_probability"), "avg_cate": row.get("average_uplift"),
            "avg_clv": row.get("average_clv"), **dict(row),
        })
    return out


def dashboard_ab(result: Mapping[str, Any]) -> dict[str, Any]:
    """`analyze_ab`(이진 결과) → 대시보드 `srm`·`arms`·`power`."""
    srm = result.get("srm") or {}
    detected = srm.get("srm_detected")
    comps = result.get("comparisons") or {}
    control = result.get("control")
    control_rate = next((c.get("rate_control") for c in comps.values() if "rate_control" in c), None)
    arms = []
    for arm, n in (result.get("arms") or {}).items():
        comp = comps.get(arm, {})
        arms.append({
            "arm": arm, "n": n,
            "rate": control_rate if arm == control else comp.get("rate_treatment"),
            "diff_vs_control": comp.get("diff"), "ci95": comp.get("ci95"),
            "p_raw": comp.get("p_value"), "p_holm": comp.get("p_value_holm"),
        })
    power: dict[str, Any] = {"alpha": result.get("alpha"), "target_power": result.get("power_target"),
                             "mde_abs": result.get("mde")}
    for arm, comp in comps.items():
        power[f"achieved_power_{arm}"] = comp.get("achieved_power")
    return {
        "srm": {"chi2": srm.get("chi2"), "p": srm.get("p_value"),
                "ok": None if detected is None else not detected},
        "arms": arms, "power": power,
    }


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
    """Eligible(t2) 모집단을 전달하고 필드 계산은 decision에 위임한다(DR-234·#179)."""
    result = decision_fn("summarize_outcomes")(outcomes, population)
    result["population_definition"] = ELIGIBLE_DEFINITION + " — t2 기준"
    return result


# ── #214 모델 · Feature 저장과 불러오기 ─────────────────────────────────────


class ModelLoadError(Exception):
    """``--load-models`` 폴더를 쓸 수 없다 — 시뮬레이션 **전에** 멈춘다(종료 코드 6)."""

    exit_code = 6


def load_saved_models(path: Path) -> tuple[dict[str, tuple[Any, dict[str, Any]]], dict[str, Any]]:
    """저장된 모델을 시뮬레이션 전에 불러온다 — 한 시간 넘게 돈 뒤에야 못 쓴다는 것을 알면 늦다.

    저장 당시 feature_version 이 지금 코드와 다르면 멈춘다(`model_store.load_models`)."""
    try:
        expected = decision_fn("feature_version")()
        if expected is None:  # PR #279 리뷰 R2 — 대조를 건너뛰지 않는다
            raise ModelLoadError("지금 코드의 feature_version 을 잴 수 없다(정의 소스를 읽지 못했다) — 저장 모델과 "
                                 "호환되는지 확인할 수 없어 불러오지 않는다")
        loaded, manifest = decision_fn("load_models")(Path(path), expected_feature_version=expected)
    except ModelLoadError:
        raise
    except NotRun as reason:
        raise ModelLoadError(f"모델 불러오기 함수를 쓸 수 없다 — {reason}") from reason
    except Exception as error:  # ModelStoreError · unpickle 오류 — 사유를 그대로 올린다
        raise ModelLoadError(f"{path} 의 모델을 불러올 수 없다 — {error}") from error
    if not loaded:
        raise ModelLoadError(f"{path} 에 불러올 모델이 없다")
    return loaded, manifest


def _loaded_record(path: Path, meta: Mapping[str, Any], manifest: Mapping[str, Any]) -> dict[str, Any]:
    return {"model_source": "loaded (재학습 없음)", "loaded_from": str(path),
            "model_version": meta.get("model_version"), "model_sha256": meta.get("sha256"),
            "trained_run": (manifest.get("run") or {}).get("run_id")}


def _fitted_evaluation(key: str, *args: Any) -> dict[str, Any]:
    """불러온 모델 평가만. 함수가 없으면 ``NotRun`` 을 올려 **단계가 not_run** 이 된다(PR #279 리뷰 N2 — 평가 없이
    ok 로 끝나지 않게). 평가 중 오류는 단계 실패로 올린다(삼키지 않는다)."""
    return {"status": "ok", **decision_fn(key)(*args)}


def _pick(row: Any, keys: tuple[str, ...]) -> dict[str, Any] | None:
    if not isinstance(row, Mapping):
        return None
    picked = {k: row[k] for k in keys if k in row}
    return picked or None


def model_scores(kind: str, evaluation: Mapping[str, Any], name: Any) -> tuple[Any, Any, dict[str, str]]:
    """ML-008 ``cv_score`` · ``test_score`` — 이 실행의 평가 결과에서 옮긴다. 없으면 None 과 사유."""
    models = evaluation.get("models")
    row = next((m for m in models if isinstance(m, Mapping) and m.get("name") == name), None) \
        if isinstance(models, list) else None
    if kind == "churn":
        cv = None
        if row and isinstance(row.get("cv"), Mapping):
            cv = {k: v.get("mean") for k, v in row["cv"].items() if isinstance(v, Mapping)}
        test = _pick(evaluation.get("temporal_holdout"), ("roc_auc", "pr_auc", "f1", "lift_at_10", "n_test"))
        return cv, test, {
            "cv_score": f"교차검증 평균 — {evaluation.get('cv_scheme') or 'churn_eval.cv_scheme'}",
            "test_score": ("시간 홀드아웃 — 학습 · 선택에 쓰지 않은 t2 이후 무처치(S0) 분기 1회 평가" if test
                           else "시간 홀드아웃 결과가 없다(단계 미실행 · 실패) — null"),
        }
    if kind == "uplift":
        selection = evaluation.get("best_method_selection")
        cv = _pick(selection, ("validation_qini", "basis", "n_validation"))
        test = _pick(row, ("qini", "auuc", "uplift_at_k"))
        return cv, test, {
            "cv_score": "학습 데이터 안 검증 분할의 Qini — 방법 선택 근거",
            "test_score": ("분할 모델의 test 추정치(탐색 RCT test 분할 — 그 분할 모델의 학습 · 선택에 쓰지 않음). 저장한 "
                           "객체는 전체 RCT 로 다시 학습했으므로 이 점수가 저장 객체의 미학습 점수는 아니다"
                           if test else "test 분할 점수가 없다 — null"),
        }
    cv = _pick(row, ("mae", "rmse", "spearman", "top20_hit"))
    return cv, None, {
        "cv_score": f"교차검증 OOF — {evaluation.get('cv_scheme') or 'clv_eval.cv_scheme'}",
        "test_score": "CLV 는 학습에 쓰지 않은 데이터의 평가가 아직 없다 — null",
    }


def persist_models(root: Path, run_id: str, ctx: Mapping[str, Any],
                   evaluations: Mapping[str, Mapping[str, Any]], run_info: Mapping[str, Any]) -> dict[str, Any]:
    """학습한 모델을 ``<root>/<run_id>/`` 에 남긴다. 종류마다 성패를 따로 적는다 — 하나가 실패해도 나머지는 남긴다."""
    target = Path(root) / run_id
    feature_version = decision_fn("feature_version")()
    digest = decision_fn("frame_digest")
    save = decision_fn("save_model")
    plan = {
        "churn": ("churn_model", lambda: ctx["churn_train"],
                  getattr(ctx.get("churn_model"), "name", None) or evaluations["churn"].get("best_proposed")),
        "uplift": ("uplift_model", lambda: (ctx["X_rct"], ctx["treatment"], 1 - ctx["Y_rct"]["churn"]),
                   evaluations["uplift"].get("fitted_method")),
        "clv": ("clv_model", lambda: (ctx["X_rct"], ctx["Y_rct"]["revenue"]), "hist_gb"),
    }
    records: dict[str, Any] = {}
    results: dict[str, Any] = {}
    for kind, (key, data, name) in plan.items():
        if key not in ctx:
            results[kind] = {"status": "not_run", "reason": f"{kind} 모델이 없다 — 단계 미실행 또는 실패"}
            continue
        try:
            frames = data()
            cv, test, notes = model_scores(kind, evaluations[kind], name)
            meta = save(target, kind, ctx[key], model_version=f"{kind}-{name}-{run_id}",
                        dataset_version=f"rct-t1-{digest(*frames)[:12]}", feature_version=feature_version,
                        cv_score=cv, test_score=test, score_notes=notes,
                        extra={"run_id": run_id, "method": name, "training_rows": int(len(frames[0]))})
        except Exception as error:  # 저장 실패를 삼키지 않는다 — failed 로 적고 종료 코드에 반영한다
            results[kind] = {"status": "failed", "reason": f"{type(error).__name__}: {error}"}
            continue
        records[kind] = meta
        results[kind] = {"status": "ok", "file": str(target / meta["file"]), "model_version": meta["model_version"],
                         "sha256": meta["sha256"], "bytes": meta["bytes"]}
    if records:
        decision_fn("write_model_manifest")(target, records, run_info)
    return {"root": str(target), "feature_version": feature_version, "models": results}


def persist_features(root: Path, run_id: str, ctx: Mapping[str, Any]) -> dict[str, Any]:
    """Feature(t1 · t2)와 라벨(t1)을 ``<root>/<run_id>/`` 에 parquet 로 남긴다 (FS-001 · FS-002)."""
    target = Path(root) / run_id
    write = decision_fn("write_feature_table")
    version = decision_fn("feature_version")()
    results: dict[str, Any] = {}
    for name, key, at, kind in (("features_t1", "X1", "t1", "feature"), ("labels_t1", "Y1", "t1", "label"),
                                ("features_t2", "X2", "t2", "feature")):
        if key not in ctx or ctx.get(at) is None:
            results[name] = {"status": "not_run", "reason": f"{key} 가 없다 — 단계 미실행 또는 실패"}
            continue
        try:
            record = write(target, name, ctx[key], feature_version=version if kind == "feature" else None,
                           cutoff_time=ctx[at], kind=kind)
        except Exception as error:  # 삼키지 않는다 — failed
            results[name] = {"status": "failed", "reason": f"{type(error).__name__}: {error}"}
            continue
        results[name] = {"status": "ok", "file": str(target / record["file"]), "rows": record["rows"]}
    return {"root": str(target), "feature_version": version, "tables": results}


def churn_prior_origin(ctx: Mapping[str, Any], main_root: Path) -> dict[str, Any]:
    """#215 — 시간 순서 검증용 **앞 기준일**(t1 − 42일) 데이터: 그 시점 Eligible 고객의 Feature 와 [t1−42, t1) 라벨.

    두 기준일 모두 처치 전(워밍업 안)이고 Eligible 정의가 같다. 새로 시뮬레이션하지 않는다 — t2 까지 읽은
    이벤트 · t1 가입일 명부(그 시점 Eligible 판정에 충분하다) · 워밍업 실행 기록(라벨 창을 덮는다)을 다시 쓰고,
    라벨의 구매 관측 근거는 **그 창 [t1−42, t1) 의 metrics**(``ctx["prior_label_metrics"]``)다 — 본선 라벨이
    [t1, t2) 창을 따로 조회하는 것과 같은 규칙이다. 공개 계약(docs/simulator_api.md ``metrics``)은 창 단위
    ``[start, end)`` 이고 상태가 판 단위라는 명시는 없다 — 이력 창의 상태로 대신하지 않는다(PR #281 리뷰 Q1).
    못 만들면 not_run 과 사유 — 무작위 교차검증으로 대신했다고 적힌다.
    """
    t_prior = ctx["t1"] - timedelta(days=LABEL_WINDOW_DAYS)
    record: dict[str, Any] = {"index_time": t_prior, "label_window": {"start": t_prior, "end": ctx["t1"]}}
    try:
        if not ctx.get("purchase_generated"):
            raise NotRun("이 시뮬레이터 판이 purchase 를 만들지 않아 라벨 · Eligible 을 판정할 수 없다")
        if "signups_t1" not in ctx or "events_t2" not in ctx or "warmup_summary" not in ctx:
            raise NotRun("입력(t1 가입일 명부 · t2 까지 이벤트 · 워밍업 실행 기록)이 없다")
        events = ctx["events_t2"]
        stamps = _timestamps(events)
        cutoff = t_prior if stamps.dt.tz is not None else t_prior.astimezone(KST).replace(tzinfo=None)
        observed = sorted(events.loc[stamps < cutoff, "customer_id"].dropna().unique().tolist())
        judged = eligibility(events, t_prior, observed, ctx["signups_t1"])
        record["eligibility"] = judged["counts"]
        eligible = [cid for cid, flag in judged["flags"].items() if flag]
        if not eligible:
            raise NotRun(f"앞 기준일의 Eligible 고객이 0명이다 — {judged['counts']}")
        X_prior = decision_fn("build_feature_table")(events, t_prior)
        X_prior.attrs["event_read_evidence"] = (ctx.get("event_read_evidence") or {}).get("t2")
        observation = outcome_observation(ctx["warmup_summary"], main_root, ctx.get("prior_label_metrics"),
                                          (ctx.get("event_read_evidence") or {}).get("t1"))
        Y_prior = decision_fn("build_outcomes")(events, t_prior, window_days=LABEL_WINDOW_DAYS,
                                                observation=observation, allow_incomplete=True)
        status = Y_prior.attrs.get("outcome_observation", {}).get("status")
        record["label_observation"] = status
        if status != "ok":
            raise NotRun(f"앞 기준일 라벨 관측 근거 미충족: {Y_prior.attrs.get('outcome_observation')}")
        pd = _pd()
        index = X_prior.index.intersection(Y_prior.index).intersection(pd.Index(eligible))
        y = Y_prior.loc[index, "churn"].dropna()
        if not two_classes(y):
            raise NotRun("앞 기준일 라벨이 한 값뿐이다")
        record.update(status="ok", reason=None, n=int(len(y)), pos_rate=float(y.mean()),
                      X=X_prior.loc[y.index], y=y)
    except NotRun as reason:
        record.update(status="not_run", reason=str(reason))
    except Exception as error:  # 삼키지 않는다 — failed 와 사유. churn 은 무작위 교차검증으로 고른다
        record.update(status="failed", reason=f"{type(error).__name__}: {error}"[:300])
    return record


CATE_FILE = "cate.jsonl"
CATE_COLUMNS = ("customer_id", "t0", "cate_T1", "cate_T2", "cate_T3", "cate_T4")


def cate_file(path: Path, ctx: Mapping[str, Any], extra_files: dict[str, Path], *, loaded: bool) -> dict[str, Any]:
    """#217 · DR-S8 결정 1 — 고객별 τ̂ ``cate.jsonl`` (S8 채점 입력). 한 줄에 한 고객 · 한 기준 시각.

    열은 DR-S8 이 받기로 한 ``customer_id · t0 · cate_T1~cate_T4`` 그대로다(다른 키를 넣지 않는다).
      - t1 — RCT 배정 고객(Feature(t1) 이 있는 고객). S8 Qini 는 RCT 분기에서 잰다.
      - t2 — 점수를 매긴 고객(Feature(t2)). S8 PEHE · corr · 4분면.
    계산할 수 없는 처치군의 τ̂ 은 null — 0 으로 채우지 않는다(DR-S8 X3). 같은 실행에서 학습한 모델이면 t1 τ̂ 은
    **학습 데이터 위 예측**이다(`in_sample_t1`) — 채점은 모델을 불러온 Final Holdout 실행(#226)의 파일로 한다.
    """
    model = ctx.get("uplift_model")
    if model is None:
        return {"status": "not_run", "reason": "uplift 모델이 없다(단계 미실행 · 실패)"}
    try:
        predict = decision_fn("predict_cate")
        pd = _pd()
        blocks: list[tuple[str, Any, Any]] = []
        if ctx.get("X1") is not None and ctx.get("t1") is not None and ctx.get("rct_assignment"):
            ids = ctx["X1"].index.intersection(pd.Index(list(ctx["rct_assignment"])))
            blocks.append(("t1", ctx["t1"], predict(model, ctx["X1"].loc[ids])))
        cate_t2 = (ctx.get("scores") or {}).get("cate")
        if cate_t2 is None and ctx.get("X2") is not None:
            cate_t2 = predict(model, ctx["X2"])
        if cate_t2 is not None and ctx.get("t2") is not None:
            blocks.append(("t2", ctx["t2"], cate_t2))
        if not blocks:
            return {"status": "not_run", "reason": "τ̂ 을 낼 Feature(t1 · t2)가 없다"}
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        counts: dict[str, int] = {}
        missing: dict[str, int] = {}
        with path.open("w", encoding="utf-8") as handle:
            for label, t0, frame in blocks:
                stamp = to_jsonable(t0)
                arms = [f"cate_{arm}" for arm in RCT_ARMS[1:]]
                frame = frame.reindex(columns=list(RCT_ARMS[1:])).sort_index()
                for cid, values in zip(frame.index, frame.to_numpy(dtype=float)):
                    row = {"customer_id": str(cid), "t0": stamp}
                    for name, value in zip(arms, values):
                        row[name] = float(value) if math.isfinite(value) else None
                    handle.write(json.dumps(row, ensure_ascii=False, allow_nan=False) + "\n")
                counts[label] = int(len(frame))
                missing[label] = int(frame.isna().any(axis=1).sum())
    except NotRun as reason:
        return {"status": "not_run", "reason": str(reason)}
    except Exception as error:  # 삼키지 않는다 — failed 와 사유
        return {"status": "failed", "reason": f"{type(error).__name__}: {error}"[:300]}
    extra_files[CATE_FILE] = path
    return {"status": "ok", "file": CATE_FILE, "columns": list(CATE_COLUMNS), "rows": counts,
            "rows_with_null_arm": missing, "in_sample_t1": not loaded,
            "note": ("t1 τ̂ 은 같은 실행에서 학습한 모델의 학습 데이터 위 예측 — S8 채점은 Final Holdout(#226, "
                     "--load-models) 실행의 파일로 한다" if not loaded else
                     "불러온 모델(재학습 없음)의 예측 — t1 · t2 모두 학습에 쓰지 않은 데이터"),
            "contract": "DR-S8 결정 1 — customer_id · t0 · cate_T1~cate_T4, 계산 불가는 null"}


def shap_summary_file(model: Any, X: Any, out: Path, seed: int, extra_files: dict[str, Path]) -> dict[str, Any]:
    """#215 — ``shap_summary.png`` 를 ``<out>/artifacts/`` 에 그리고 결과 폴더 사본 목록에 올린다.

    그림이 실패해도 Churn 단계는 이어 간다(모델 · 지표는 그대로 유효) — 사유를 churn_eval 에 남긴다."""
    try:
        draw = decision_fn("write_shap_summary")
    except NotRun as reason:
        return {"status": "not_run", "reason": str(reason)}
    path = Path(out) / "artifacts" / "shap_summary.png"
    try:
        record = draw(model, X, path, seed=seed)
    except Exception as error:  # 삼키지 않는다 — failed 와 사유
        return {"status": "failed", "reason": f"{type(error).__name__}: {error}"[:300]}
    extra_files["shap_summary.png"] = path
    return record


def shap_local(model: Any, X: Any, candidates: Any) -> dict[str, Any]:
    """#215 — 이탈 확률 상위 고객의 SHAP Local. Eligible(t2) 가 있으면 그 안에서 고른다."""
    try:
        explain = decision_fn("explain_top_risk")
    except NotRun as reason:
        return {"status": "not_run", "reason": str(reason)}
    try:
        result = explain(model, X, candidates=candidates)
    except Exception as error:
        return {"status": "failed", "reason": f"{type(error).__name__}: {error}"[:300]}
    if candidates is not None and not result.get("n_pool"):  # #280 리뷰 N1 — 빈 Eligible 을 넓히지 않는다
        return {"status": "not_run", "reason": "Eligible(t2) 후보가 0명 — 전체 고객으로 넓혀 설명하지 않는다", **result}
    return {"status": "ok", **result}


def deployed_threshold(model: Any) -> dict[str, Any]:
    """#280 리뷰 R1 — 배치 객체의 임계와 그 근거. ``threshold_table``(고른 모델 종류의 바깥 CV OOF)과 근거가 다르다."""
    value = getattr(model, "threshold", None)
    return {"value": float(value) if isinstance(value, (int, float)) else None,
            "rule": getattr(model, "threshold_rule", None) or None,
            "note": "predicted_label 에 쓰는 임계 — churn_eval.threshold_table 은 같은 F1 최대 규칙을 다른 OOF 에 적용한 "
                    "비교표라 값이 다를 수 있다"}


def persistence_status(record: Mapping[str, Any]) -> str:
    """하위 결과 중 failed 가 하나라도 있으면 failed. 요청이 없었으면 not_requested."""
    statuses: list[str] = []
    for part in ("models", "features"):
        value = record.get(part)
        if not isinstance(value, Mapping):
            continue
        if "status" in value:
            statuses.append(value["status"])
        for item in (value.get("models") or value.get("tables") or {}).values():
            if isinstance(item, Mapping):
                statuses.append(item.get("status"))
    if not statuses:
        return "not_requested"
    if "failed" in statuses:
        return "failed"
    return "ok" if "ok" in statuses else "not_run"


def run(config: SprintConfig) -> Path:
    """전 구간을 돌리고 결과 폴더 경로를 돌려준다. 단계 실패는 기록하고 다음으로 간다."""
    run_id = config.run_id or new_run_id()
    generated_at = mc.kst_now()
    # 출처는 시작할 때 잰다 — 실행 중의 커밋 · 수정이 이 실행의 기록을 바꾸지 못하게 한다 (#262).
    start_state = repo_state()
    if config.require_clean:
        check_clean(start_state)
    # #214 — 불러올 모델은 시뮬레이션 전에 확인한다. 못 쓰면 ModelLoadError 로 바로 멈춘다.
    loaded_models: dict[str, tuple[Any, dict[str, Any]]] = {}
    loaded_manifest: dict[str, Any] = {}
    if config.load_models is not None:
        loaded_models, loaded_manifest = load_saved_models(config.load_models)
        _log(f"모델 불러옴 {config.load_models} ({' · '.join(sorted(loaded_models))}) — 다시 학습하지 않는다")

    log = StageLog(config.stages, config.scope)
    out = Path(config.out)
    main_root = out / "raw" / "main"
    warmup, warmup_basis = resolve_warmup(config.profile, config.warmup_days)
    basis, basis_reason = load_cost_basis()
    costs, costs_source = plan_costs(basis)
    _log(f"run_id={run_id} seed={config.seed} N={config.num_customers} profile={config.profile} out={out}")

    ctx: dict[str, Any] = {"timeline": {}}
    assignments_dir = out / "assignments"
    assignment_files: dict[str, Any] = {"rct": None, "strategies": {}}
    extra_outputs: dict[str, Path] = {}  # #215 — 결과 폴더에 함께 둘 파일(shap_summary.png)
    reader = EventReader()
    if reader.fallback_reason:
        _log(f"이벤트 읽기: 대체 경로 sim.events — {reader.fallback_reason}")

    churn_eval: dict[str, Any] = {}
    clv_eval: dict[str, Any] = {}
    uplift_eval: dict[str, Any] = {}
    ab_test: dict[str, Any] = {}
    segments_out: dict[str, Any] = {}
    comparison: dict[str, Any] = {"baseline": BASELINE_STRATEGY, "strategy_details": {}}
    rct_meta: dict[str, Any] = {}

    try:
        # 1. warmup ---------------------------------------------------------
        with log.stage("simulate_warmup"):
            if warmup is None:
                raise NotRun(f"프로파일 {config.profile!r} 의 권장 warmup 을 모른다 — --warmup-days 필요")
            sim.init(config.seed, config.num_customers, config.profile, output_root=main_root)
            summary = sim.advance(warmup)
            ctx["warmup_summary"] = summary
            ctx["t1"] = summary.end
            ctx["timeline"]["start"] = summary.start
            ctx["timeline"]["t1"] = summary.end

        with log.stage("read_events_t1", requires=("simulate_warmup",)):
            skip_if_not_run(log, "read_events_t1")
            ctx["events_t1"] = reader.read(main_root, ctx["t1"], run_id=ctx["warmup_summary"].run_id)
            ctx.setdefault("event_read_evidence", {})["t1"] = ctx["events_t1"].attrs.get("run_read_evidence")
            _log(f"  이벤트 {len(ctx['events_t1']):,}건 (< t1)")

        # 2. 탐색 RCT -------------------------------------------------------
        with log.stage("rct_assign", requires=("read_events_t1",)):
            skip_if_not_run(log, "rct_assign")
            # 모집단 = t1 의 Eligible(#194 · DR-234). 가입일 명부는 본선 세계가 t1 에 있을 때 받는다.
            observed = sorted(ctx["events_t1"]["customer_id"].dropna().unique().tolist())
            ctx["signups_t1"] = customer_signups(ctx["t1"])  # #215 — 홀드아웃 Eligible(t2) 판정에도 쓴다
            judged = eligibility(ctx["events_t1"], ctx["t1"], observed, ctx["signups_t1"])
            eligible = [cid for cid, flag in judged["flags"].items() if flag]
            if not eligible:
                raise NotRun(f"t1 의 Eligible 고객이 0명이다 — {judged['counts']}")
            assignment = rct_assign(eligible, config.seed)
            ctx["rct_assignment"] = assignment
            rct_meta.update(
                {
                    "assigned_at": ctx["t1"],
                    "population_definition": ELIGIBLE_DEFINITION + " — t1 기준, t1 미만 이벤트에 관측된 고객 중",
                    **judged["counts"],
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
            ctx["X1"].attrs["event_read_evidence"] = ctx["event_read_evidence"]["t1"]
            _log(f"  Feature(t1) {ctx['X1'].shape}")
        ctx["simulator_version"] = observed_values(ctx.get("events_t1"), "simulator_version")
        ctx["random_seed"] = observed_values(ctx.get("events_t1"), "random_seed")
        ctx.pop("events_t1", None)  # 이후 단계는 t2 까지의 이벤트를 다시 읽는다 — 메모리를 돌려준다

        with log.stage("simulate_rct", requires=("rct_assign",)):
            skip_if_not_run(log, "simulate_rct")
            sim.apply_treatment(ctx["rct_assignment"])
            rct_file = assignments_dir / f"T0-{ctx['t1'].astimezone(KST):%Y%m%d}.json"
            write_assignment_file(rct_file, ctx["t1"], ctx["rct_assignment"],
                                  kind="exploration_rct", includes_control=True)
            assignment_files["rct"] = rct_file
            summary = sim.advance(LABEL_WINDOW_DAYS)
            ctx["rct_summary"] = summary
            ctx["t2"] = summary.end
            ctx["timeline"]["t2"] = summary.end

        with log.stage("read_events_t2", requires=("simulate_rct",)):
            skip_if_not_run(log, "read_events_t2")
            ctx["events_t2"] = reader.read(main_root, ctx["t2"], run_id=ctx["rct_summary"].run_id)
            ctx.setdefault("event_read_evidence", {})["t2"] = ctx["events_t2"].attrs.get("run_read_evidence")
            _log(f"  이벤트 {len(ctx['events_t2']):,}건 (< t2)")
            ctx["event_types_t2"] = event_count_by_type(ctx["events_t2"])
            # 본선 세계가 활성인 지금 확인한다 — 분기 뒤에는 이 세계로 돌아오지 않는다.
            # B1: 계획 이익률·S1의 과거 구매 입력은 기존 전체 이력 창을 보존한다.
            try:
                main_metrics = sim.metrics(ctx["timeline"]["start"], ctx["t2"])
            except Exception as error:  # noqa: BLE001 — 사유를 남기고 구매 관측 불명으로 다룬다
                main_metrics = None
                _log(f"  본선 이력 sim.metrics 실패: {type(error).__name__}: {error}")
            ctx["purchase_generated"], ctx["purchase_detail"] = purchase_generated(main_metrics)
            ctx["margin_rate"], ctx["margin_basis"] = margin_rate_basis(main_metrics)
            # 라벨 구매 상태는 해당 42일 창의 별도 원본으로 확인한다. 이력 창에 덮어쓰지 않는다.
            try:
                label_metrics = sim.metrics(ctx["t1"], ctx["t2"])
            except Exception as error:  # noqa: BLE001 — 라벨만 미확정으로 남긴다
                label_metrics = None
                _log(f"  본선 라벨 sim.metrics 실패: {type(error).__name__}: {error}")
            # #215 · PR #281 리뷰 Q1 — 앞 기준일(t1 − 42일) 라벨도 그 42일 창의 별도 원본으로 확인한다.
            t_prior = ctx["t1"] - timedelta(days=LABEL_WINDOW_DAYS)
            try:
                prior_label_metrics = (sim.metrics(t_prior, ctx["t1"])
                                       if t_prior >= ctx["timeline"]["start"] else None)
            except Exception as error:  # noqa: BLE001 — 앞 기준일 라벨만 미확정으로 남긴다
                prior_label_metrics = None
                _log(f"  앞 기준일 라벨 sim.metrics 실패: {type(error).__name__}: {error}")
            ctx["prior_label_metrics"] = prior_label_metrics
            ctx["main_metric_windows"] = {
                "history": {"start": ctx["timeline"]["start"], "end": ctx["t2"],
                            "uses": ["margin_rate", "s1_purchase_gate"],
                            "purchase_generated": ctx["purchase_generated"]},
                "label": {"start": ctx["t1"], "end": ctx["t2"], "uses": ["Y1_purchase_observation"],
                          "purchase_generated": purchase_generated(label_metrics)[0]},
                "prior_label": {"start": t_prior, "end": ctx["t1"], "uses": ["churn_prior_origin_label_observation"],
                                "purchase_generated": purchase_generated(prior_label_metrics)[0]},
            }
            ctx["outcome_observation"] = outcome_observation(
                ctx["rct_summary"], main_root, label_metrics, ctx["events_t2"].attrs.get("run_read_evidence"))

        with log.stage("outcomes_t1", requires=("read_events_t2",)):
            skip_if_not_run(log, "outcomes_t1")
            build_outcomes = decision_fn("build_outcomes")
            ctx["Y1"] = build_outcomes(ctx["events_t2"], ctx["t1"], window_days=LABEL_WINDOW_DAYS,
                                       observation=ctx["outcome_observation"], allow_incomplete=True)
            ctx["label_observation"] = ctx["Y1"].attrs.get("outcome_observation", {})
            if ctx["label_observation"].get("status") != "ok":
                raise NotRun(f"본선 라벨 관측 근거 미충족: {ctx['label_observation']}")
            # #215 — 시간 순서 검증용 앞 기준일 데이터. 없거나 못 만들어도 이 단계는 실패하지 않는다(사유를 남긴다).
            ctx["churn_prior"] = churn_prior_origin(ctx, main_root)

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
            if config.load_models is not None:  # #214 — 다시 학습하지 않고 불러온 모델을 평가만 한다
                if "churn" not in loaded_models:
                    raise NotRun(f"{config.load_models} 에 churn 모델이 없다 — 다시 학습하지 않는다")
                model, meta = loaded_models["churn"]
                churn_eval.update(_loaded_record(config.load_models, meta, loaded_manifest))
                churn_eval["best_proposed"] = getattr(model, "name", None)
                churn_eval["fitted_evaluation"] = _fitted_evaluation("evaluate_fitted_churn", model, X, y)
                ctx["churn_model"] = model
                ctx["churn_train"] = (X, y)  # 시간 홀드아웃의 모집단 대조용 — 학습 모집단은 trained_run 쪽이다
                if churn_eval["best_proposed"] is not None:
                    ctx["churn_best_name"] = churn_eval["best_proposed"]
            else:
                X, y, churn_eval["training_sample"] = stratified_cap(X, y, config.max_train_rows, config.seed)
                evaluate = decision_fn("evaluate_churn_models")
                fit = decision_fn("fit_best_churn")
                prior = ctx.get("churn_prior") or {"status": "not_run", "reason": "앞 기준일 단계에 도달하지 않았다"}
                churn_eval["prior_origin"] = {k: v for k, v in prior.items() if k not in ("X", "y")}
                extra = ({"prior": (prior["X"], prior["y"])}
                         if prior.get("status") == "ok" and "prior" in inspect.signature(evaluate).parameters else {})
                with override_attr(DECISION_API["evaluate_churn_models"][0], "N_SPLITS", config.cv_folds) as folds:
                    churn_eval["cv_folds_override"] = folds
                    evaluation = evaluate(X, y, config.seed, **extra)
                    churn_eval.update(evaluation)  # label_def · n · pos_rate · models · shap_top … (대시보드 ChurnEval)
                    if "eval_result" in inspect.signature(fit).parameters:
                        ctx["churn_model"] = fit(X, y, config.seed, eval_result=evaluation)
                    else:
                        ctx["churn_model"] = fit(X, y, config.seed)
                ctx["churn_train"] = (X, y)
                if isinstance(evaluation, Mapping) and evaluation.get("best_proposed") is not None:
                    ctx["churn_best_name"] = evaluation["best_proposed"]
            churn_eval["deployed_threshold"] = deployed_threshold(ctx["churn_model"])
            # #215 — SHAP 요약 그림: 확정 모델 · 학습 모집단 표본(불러온 실행은 이 실행의 T0 군)
            churn_eval["shap_summary"] = shap_summary_file(ctx["churn_model"], ctx["churn_train"][0], out,
                                                           config.seed, extra_outputs)

        # uplift — 전 군 -----------------------------------------------------
        with log.stage("uplift", requires=("training_set",)):
            skip_if_not_run(log, "uplift")
            retention = 1 - ctx["Y_rct"]["churn"]
            uplift_eval.update({"population": "탐색 RCT 전 군 (T0~T4)", "n": int(len(retention)),
                                "outcome": "retention = 1 − churn",
                                "arm_counts": dict(sorted(Counter(ctx["treatment"].tolist()).items()))})
            if not two_classes(retention):
                raise NotRun("retention 라벨이 한 값뿐이다 — CATE 추정 불가 (구매 이벤트 유무 확인)")
            if config.load_models is not None:  # #214 — 불러온 메타러너를 평가만
                if "uplift" not in loaded_models:
                    raise NotRun(f"{config.load_models} 에 uplift 모델이 없다 — 다시 학습하지 않는다")
                model, meta = loaded_models["uplift"]
                uplift_eval.update(_loaded_record(config.load_models, meta, loaded_manifest))
                uplift_eval["fitted_method"] = getattr(model, "method", None)
                uplift_eval["fitted_method_source"] = "불러온 모델 (재학습 없음)"
                uplift_eval["fitted_evaluation"] = _fitted_evaluation(
                    "evaluate_fitted_uplift", model, ctx["X_rct"], ctx["treatment"], retention)
                ctx["uplift_model"] = model
            else:
                try:
                    risk_factory = decision_fn("make_risk_model_factory")(config.seed)
                except NotRun:
                    risk_factory = None  # 위험도 기준선만 not_run, 정상 S/T/X는 유지한다.
                evaluation = call_by_name(decision_fn("evaluate_uplift_models"), {
                    "X": ctx["X_rct"], "treatment": ctx["treatment"], "y": retention,
                    "seed": config.seed, "risk_model_factory": risk_factory,
                })
                uplift_eval.update(evaluation)  # n · arms · ate · models … (대시보드 UpliftEval)
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
            if config.load_models is not None:  # #214 — 불러온 CLV 모델을 평가만
                if "clv" not in loaded_models:
                    raise NotRun(f"{config.load_models} 에 clv 모델이 없다 — 다시 학습하지 않는다")
                model, meta = loaded_models["clv"]
                clv_eval.update(_loaded_record(config.load_models, meta, loaded_manifest))
                clv_eval["fitted_evaluation"] = _fitted_evaluation(
                    "evaluate_fitted_clv", model, ctx["X_rct"], future_value)
                ctx["clv_model"] = model
            else:
                fit = decision_fn("fit_clv")
                if "seed" in inspect.signature(fit).parameters:
                    ctx["clv_model"] = fit(ctx["X_rct"], future_value, seed=config.seed)
                else:
                    ctx["clv_model"] = fit(ctx["X_rct"], future_value)
                try:
                    evaluate = decision_fn("evaluate_clv")
                    clv_eval.update(call_by_name(
                        evaluate, {"X": ctx["X_rct"], "future_value": future_value, "y": future_value,
                                   "model": ctx["clv_model"], "seed": config.seed,
                                   "horizon_days": LABEL_WINDOW_DAYS},
                    ))  # horizon_days · models … (대시보드 ClvEval)
                except NotRun as reason:
                    clv_eval["evaluation_status"] = {"status": "not_run", "reason": str(reason)}

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
            # 설계 배정 비율을 넘겨 SRM 을 그 비율로 검사한다(기본값은 균등 가정이라 50/12.5% 설계를 오탐한다).
            design = {"T0": RCT_CONTROL_SHARE, **{t: (1 - RCT_CONTROL_SHARE) / 4 for t in RCT_ARMS[1:]}}
            expected = {a: design[a] for a in sorted(set(frame["arm"]))}
            for outcome in ("retention", "revenue"):
                if outcome in frame:
                    ab_test["results"][outcome] = analyze(frame, "arm", outcome, control="T0",
                                                          expected_ratio=expected)
            ab_test["primary_outcome"] = "retention"
            ab_test.update(dashboard_ab(ab_test["results"]["retention"]))  # 대시보드 AbTest

        # 3. 전략 비교 -------------------------------------------------------
        with log.stage("features_t2", requires=("read_events_t2",)):
            skip_if_not_run(log, "features_t2")
            ctx["X2"] = decision_fn("build_feature_table")(ctx["events_t2"], ctx["t2"])
            ctx["X2"].attrs["event_read_evidence"] = ctx["event_read_evidence"]["t2"]
            _log(f"  Feature(t2) {ctx['X2'].shape}")

        scores: dict[str, Any] = {}
        ctx["scores"] = scores  # 같은 dict — main.py 가 고객별 점수 CSV 를 쓴다(#206)

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
            # S1 입력 · Eligible(t2) — 이벤트에서 계산한다. purchase 를 만들지 않는 판이면 계산하지 않는다
            # (0 으로 채우지 않는다). 그러면 S1~S5 가 not_run 이다 — 모두 Eligible 안에서만 고른다(DR-234).
            # 가입일 명부는 본선 세계가 t2 에 있는 지금(분기 restore 전) 받는다.
            detail = None
            if not ctx.get("purchase_generated"):
                detail = ("이 시뮬레이터 판이 purchase 를 만들지 않는다 "
                          f"({ctx.get('purchase_detail', 'purchase 생성 여부를 확인하지 못했다')})")
            else:
                try:
                    judged = eligibility(ctx["events_t2"], ctx["t2"], X2.index, customer_signups(ctx["t2"]))
                except NotRun as reason:
                    detail = f"Eligible(t2) 를 판정하지 못했다 — {reason}"
            if detail is None:
                scores.update(s1_inputs(ctx["events_t2"], ctx["t2"], X2.index, judged["flags"]))
                ctx["eligible_t2"] = [cid for cid, flag in judged["flags"].items() if flag]
                comparison["s1_inputs"] = {
                    "source": "이벤트(t2 미만 purchase) · 교환 묶음 가입일 명부 — 오케스트레이션 계산",
                    "index_time": ctx["t2"],
                    "eligible_definition": ELIGIBLE_DEFINITION + " — t2 기준, Feature(t2) 고객 중",
                    **judged["counts"],
                    "n_with_purchase_history": int(scores["days_since_last_purchase"].notna().sum()),
                }
            else:
                for key in ("days_since_last_purchase", "lifetime_order_count", "eligible"):
                    reasons[key] = detail
            if ctx.get("margin_rate") is not None:
                scores["margin_rate"] = ctx["margin_rate"]
            else:
                reasons["margin_rate"] = (ctx.get("margin_basis") or {}).get("reason", "기여이익률 근거 없음")
            ctx["score_missing"] = reasons
            if "churn_model" in ctx:  # #215 — 위험 상위 고객의 SHAP Local, Eligible(t2) 안에서 고른다
                churn_eval["shap_local"] = shap_local(ctx["churn_model"], X2, ctx.get("eligible_t2"))
            comparison["scores_available"] = sorted(scores)
            comparison["scores_missing"] = reasons

        with log.stage("segments", requires=("scores_t2",)):
            skip_if_not_run(log, "segments")
            missing = [k for k in ("churn_p", "cate", "clv") if k not in scores]
            if missing:
                raise NotRun(f"점수가 없다: {missing}")
            seg = decision_fn("assign_segments")(scores["churn_p"], scores["cate"], scores["clv"])
            segments_out.update({"index_time": ctx["t2"], "n": int(len(seg))})
            try:
                rows = decision_fn("segment_stats")(seg, scores["churn_p"], scores["cate"], scores["clv"])
                segments_out["segments"] = dashboard_segments(rows)  # 대시보드 Segments
            except NotRun as reason:
                segments_out["segments_summary"] = _segment_summary(seg, scores)
                segments_out["segment_stats_status"] = {"status": "not_run", "reason": str(reason)}

        with log.stage("snapshot_t2", requires=("simulate_rct", "read_events_t2")):
            skip_if_not_run(log, "snapshot_t2")
            ctx["snapshot"] = reader.snapshot(ctx["events_t2"], ctx["t2"])

        # 분기 결과 집계의 모집단 = Eligible(t2) — 전략이 배정할 수 있는 고객과 같다(DR-234).
        population = ctx.get("eligible_t2")
        strategy_results: dict[str, dict[str, Any]] = comparison["strategy_details"]
        for strategy in STRATEGIES:
            name = f"strategy_{strategy}"
            entry: dict[str, Any] = {"strategy_id": strategy}
            strategy_results[strategy] = entry
            with log.stage(name, requires=("snapshot_t2",)):
                skip_if_not_run(log, name)
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
                    assignments = dict(call_plan(strategy, scores, None, costs))
                    try:
                        entry["s1_eligibility"] = decision_fn("s1_eligibility")(scores)
                    except NotRun as reason:
                        entry["s1_eligibility"] = {"status": "not_run", "reason": str(reason)}
                else:
                    if costs is None:
                        raise NotRun(basis_reason or "처치 비용을 읽을 수 없다")
                    budget_record = ctx.get("budget") or {}
                    budget = budget_record.get("planning_budget_krw")
                    if budget is None:
                        # 같은 예산이 아니면 S1 대비 비교가 성립하지 않는다 — 추정치로 메우지 않는다(#170 D2).
                        raise NotRun(budget_record.get("reason") or "S2~S5 예산(C_rule)을 정하지 않았다")
                    entry["budget_krw"] = budget
                    assignments = dict(call_plan(strategy, scores, budget, costs))
                branch_root = branch_raw_root(out, strategy)
                reader.restore(ctx["snapshot"], output_root=branch_root)
                if assignments:
                    sim.apply_treatment(assignments)
                strategy_file = write_assignment_file(
                    assignments_dir / "strategies" / f"{strategy}.json", ctx["t2"], assignments,
                    kind="strategy_branch", strategy_id=strategy, includes_control=False,
                    note="plan 이 고른 처치 대상만(T0 미포함). 같은 t2 스냅샷의 분기 — RCT 배정표와 섞지 않는다",
                )
                assignment_files["strategies"][strategy] = strategy_file
                summary = reader.advance(LABEL_WINDOW_DAYS)
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
                try:
                    raw_metrics = sim.metrics(ctx["t2"], summary.end)
                except Exception as error:  # noqa: BLE001 — 독립 측정값은 이어서 계산한다
                    raw_metrics = None
                    entry["sim_metrics_error"] = f"{type(error).__name__}: {error}"
                generated, detail = purchase_generated(raw_metrics)
                entry["purchase_generated"] = {"value": generated, "detail": detail}
                entry["sim_metrics"] = {k: mc.metric_to_json(v) for k, v in (raw_metrics or {}).items()}
                try:
                    events = reader.read(branch_root, summary.end, history=ctx["events_t2"], run_id=summary.run_id)
                    read_evidence = events.attrs.get("run_read_evidence")
                except NotRun as reason:
                    events = ctx["events_t2"]  # 과거 이력으로 진단 행만 보존한다. 관측 불명 라벨은 만들지 않는다.
                    read_evidence = {"status": "not_run", "run_id": summary.run_id, "reason": str(reason)}
                observation = outcome_observation(summary, branch_root, raw_metrics, read_evidence)
                entry["event_read_evidence"] = read_evidence
                observation_status = outcome_observation_status(
                    ctx["t2"], LABEL_WINDOW_DAYS, observation)
                # 측정 계산은 그대로 보존하되 정식 입력은 창·쓰기·읽기 성공이 필요하다.
                economics_observed = (observation_status["label_window_complete"]
                                      and observation_status["writing_complete"] and observation_status["read_complete"])
                economics_missing = [key for key in ("label_window_complete", "writing_complete", "read_complete")
                                     if not observation_status[key]]
                entry["economics_input_observation"] = {
                    "status": "ok" if economics_observed else "not_run",
                    "reason": (None if economics_observed else
                               "정식 경제 입력의 관측 근거 미충족: " + ", ".join(economics_missing)),
                    "observation": observation_status,
                }
                # 실측 기여이익 — 이 분기 세계가 활성인 지금 묶음을 받는다(다음 restore 전에, DR-169).
                entry["measured_economics"] = (branch_economics(branch_root, summary.end)
                    if observation_status["read_complete"] else {"status": "not_run", "reason": "원시 이벤트 읽기 근거 미충족"})

                def sim_value(key: str) -> Any:
                    metric = entry["sim_metrics"].get(key, {})
                    return metric.get("value") if metric.get("status") == "ok" else None

                # summarize_strategy 가 읽는 키 — 값을 고르는 순서(roi.CANDIDATES)는 의사결정이 정한다.
                # sim.metrics 값은 sim_*, 측정 계층 호출 값은 measured_*(DR-169), 이벤트 결과는
                # revenue_krw·churn_rate, 계획 비용은 planned_treatment_cost_krw.
                metrics: dict[str, Any] = {
                    "id": strategy,
                    "name": _strategy_name(strategy),
                    "n_targeted": entry["n_targeted"],
                    "treatment_mix": {t: n for t, n in sorted(counts.items()) if t != "T0"},
                    "planned_treatment_cost_krw": entry.get("planned_cost_krw"),
                }
                for key in ("revenue", "marketing_cost", "contribution_profit", "churn_rate"):
                    metrics[f"sim_{key}"] = sim_value(key) if economics_observed else None
                for key in MEASURED_KEYS:
                    metrics[f"measured_{key}"] = (measured_value(entry["measured_economics"], key)
                                                if economics_observed else None)
                try:
                    build_outcomes = decision_fn("build_outcomes")
                    outcomes = build_outcomes(events, ctx["t2"], window_days=LABEL_WINDOW_DAYS,
                                              observation=observation, allow_incomplete=True)
                    if strategy == "S0":
                        # temporal holdout 은 Feature(t2) 고객으로 평가한다 — 집계 모집단과 따로다(#179 범위)
                        ctx["S0_outcomes"] = outcomes
                    if population is None:
                        raise NotRun("Eligible(t2) 가 없어 집계 모집단을 정할 수 없다 — "
                                     + (ctx.get("score_missing") or {}).get("eligible", "scores_t2 단계 미실행"))
                    entry["event_outcomes"] = _outcome_metrics(outcomes, population)
                    metrics.update(entry["event_outcomes"])
                except NotRun as reason:
                    entry["event_outcomes"] = {"status": "not_run", "reason": str(reason)}
                entry["metrics"] = metrics
            if strategy == BASELINE_STRATEGY:
                # S1 이 끝난 직후 — 성공했든 아니든 S2~S5 의 예산을 정하고 근거를 남긴다.
                ctx["budget"] = resolve_budget(config.budget_krw, entry if log.ok(name) else None, basis)
                comparison["budget"] = ctx["budget"]
                if ctx["budget"]["planning_budget_krw"] is None:
                    _log(f"  S2~S5 예산 없음 — {ctx['budget']['reason']}")
                else:
                    _log(f"  S2~S5 예산 {ctx['budget']['planning_budget_krw']:,.0f}원 — {ctx['budget']['source']}")

        # data_spec §14.1 가드레일 `Marketing Cost ≤ C_rule` — 분기마다 계획 · 실현 변동비를 대조한다(#170 D4).
        c_rule_krw = (ctx.get("budget") or {}).get("c_rule_planned_krw")
        for strategy, entry in strategy_results.items():
            if strategy != "S0":
                entry["budget_guardrail"] = budget_guardrail(entry, c_rule_krw)

        if "snapshot" in ctx:
            sim.discard_snapshot(ctx["snapshot"])

        # What-if — 예산 50/100/200% (SRS OPT-005 · PRD §54) -------------------
        with log.stage("what_if", requires=("scores_t2",)):
            skip_if_not_run(log, "what_if")
            missing = [k for k in ("cate", "clv", "eligible") if k not in scores]
            if missing or costs is None:
                raise NotRun(f"점수·비용이 없다: {missing or '비용'}"
                             + (f" — {ctx['score_missing']['eligible']}" if "eligible" in ctx.get("score_missing", {}) else ""))
            base_budget = (ctx.get("budget") or {}).get("planning_budget_krw")
            if base_budget is None:
                raise NotRun((ctx.get("budget") or {}).get("reason") or "기준 예산(C_rule)을 정하지 않았다")
            budgets = decision_fn("what_if_budgets")(base_budget)
            # S5 와 같은 모집단 — Eligible(t2) 안에서만(DR-234). 거르기 규칙은 의사결정의 것을 그대로 쓴다.
            pool = decision_fn("within_eligible")(scores)
            cate = pool["cate"][[t for t in RCT_ARMS[1:] if t in pool["cate"].columns]].astype(float)
            if pool.get("margin_rate") is None:  # #217 — 매출 CLV 를 이익으로 쓰지 않는다(예전 기본 1.0 제거)
                raise NotRun(f"margin_rate(기여이익률)가 없다 — {(ctx.get('margin_basis') or {}).get('reason', '근거 없음')}")
            value = pool["clv"].astype(float) * float(pool["margin_rate"])
            # 기대 증분가치 = CATE × CLV × margin_rate (DR-145 S4·S5 와 같은 정의 — 의사결정의 공개 함수가 없어 여기서 만든다)
            gain = cate.mul(value.reindex(cate.index), axis=0)
            comparison["what_if"] = {
                "definition": "expected_gain = CATE(retention) × CLV × margin_rate, 비용 = planning_costs",
                "rows": decision_fn("what_if")(budgets, gain, costs, expected_conversion=cate),
            }

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
            if ctx["S0_outcomes"].attrs.get("outcome_observation", {}).get("status") != "ok":
                raise NotRun("S0 분기의 구매 라벨 관측 근거가 미충족이다")
            labels_all = ctx["S0_outcomes"]["churn"].reindex(ctx["X2"].index).dropna()
            if labels_all.empty:
                raise NotRun("S0 분기의 유효한 churn 라벨이 없다")
            # #215 — 학습 모집단(Eligible(t1) 중 RCT 무처치 T0 군)과 같은 정의로 평가한다: Eligible(t2) 이면서
            # t1 실험에서 쿠폰 · 알림(T1~T4)을 받지 않은 고객. 전체 고객 기준은 참고로만 싣는다(멘토 피드백).
            if ctx.get("eligible_t2") is not None:
                eligible, eligible_source = set(ctx["eligible_t2"]), "scores_t2 단계 판정"
            else:
                # --mode evaluate 는 scores_t2 를 돌지 않는다 — 여기서 같은 정의로 판정한다. t1 이후 가입자는 t2 에
                # 가입 42일이라 Eligible(가입 60일 이상)일 수 없으므로 t1 명부로 충분하다(시뮬레이터 추가 호출 없음).
                if not ctx.get("purchase_generated"):
                    raise NotRun("이 시뮬레이터 판이 purchase 를 만들지 않아 Eligible(t2) 를 판정할 수 없다")
                if "signups_t1" not in ctx or "events_t2" not in ctx:
                    raise NotRun("Eligible(t2) 판정 입력(t1 가입일 명부 · t2 이벤트)이 없다")
                judged = eligibility(ctx["events_t2"], ctx["t2"], ctx["X2"].index, ctx["signups_t1"])
                eligible = {cid for cid, flag in judged["flags"].items() if flag}
                eligible_source = "churn_temporal_holdout 단계 판정 (t1 가입일 명부)"
            if not eligible:
                raise NotRun("Eligible(t2) 가 없다 — 학습 모집단과 같은 범위로 평가할 수 없다")
            treated = {cid for cid, arm in (ctx.get("rct_assignment") or {}).items() if arm != "T0"}
            in_scope = [cid for cid in labels_all.index if cid in eligible and cid not in treated]
            holdout_y = labels_all.loc[in_scope]
            if holdout_y.empty:
                raise NotRun("Eligible(t2) · t1 무처치 고객 중 유효한 churn 라벨이 없다")
            holdout_X = ctx["X2"].loc[holdout_y.index]
            audit = decision_fn("temporal_population_audit")(
                *ctx["churn_train"], holdout_X, holdout_y,
                training_treatment=ctx["treatment"], evaluation_prior_treatment=ctx["treatment"],
            )
            churn_eval["temporal_population_audit"] = audit
            X_train, y_train = ctx["churn_train"]
            pool = {"model": ctx["churn_model"], "X_train": X_train, "y_train": y_train,
                    "X_test": holdout_X, "y_test": holdout_y, "seed": config.seed}
            if "churn_best_name" in ctx:
                pool["model_factory"] = ctx["churn_best_name"]
            holdout = call_by_name(decision_fn("evaluate_temporal_holdout"), pool)
            holdout = {**holdout, "population_audit": audit,
                       "population": "Eligible(t2) ∩ t1 실험 무처치(T0 · 미배정) — 학습 모집단과 같은 정의",
                       "eligible_source": eligible_source,
                       "n_labeled_all": int(len(labels_all)),
                       "n_excluded_not_eligible": int(sum(1 for cid in labels_all.index if cid not in eligible)),
                       "n_excluded_rct_treated": int(sum(1 for cid in labels_all.index
                                                         if cid in eligible and cid in treated))}
            if config.load_models is not None and "churn" in loaded_models:  # PR #279 리뷰 N1
                holdout["training_cohort"] = {
                    "source": "불러온 모델 — 학습은 원래 실행에서 했다(재학습 없음)",
                    "trained_run": (loaded_manifest.get("run") or {}).get("run_id"),
                    "training_rows": loaded_models["churn"][1].get("training_rows"),
                }
                holdout["n_train_meaning"] = "이 실행의 t1 T0 비교 군(모집단 감사용) — 불러온 모델의 학습 군이 아니다"
            churn_eval["temporal_holdout"] = holdout  # 확정 모델 1회 평가 — 전체 고객으로 다시 재지 않는다
            # 대시보드 ChurnModel.temporal_holdout — 같은 이름의 모델 행에 지표만 붙인다
            meta_keys = {"name", "scheme", "n_train", "n_test", "pos_rate_train", "pos_rate_test", "threshold",
                         "n_labeled_all", "n_excluded_not_eligible", "n_excluded_rct_treated"}  # #215 범위 기록
            models = churn_eval.get("models")
            for model in models if isinstance(models, list) else []:
                if isinstance(model, dict) and isinstance(holdout, Mapping) and model.get("name") == holdout.get("name"):
                    model["temporal_holdout"] = {k: v for k, v in holdout.items()
                                                 if k not in meta_keys and isinstance(v, (int, float))}
            churn_eval["temporal_holdout_design"] = (
                "불러온 모델(재학습 없음) → Feature(t2) · S0 분기(무처치) 42일 churn 으로 1회 평가"
                if config.load_models is not None else
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

        # 대시보드 StrategyComparison.strategies — S0~S5 순서의 요약 행. 실행하지 못한 전략도 행을 두고 사유를 단다.
        rows = []
        for strategy in STRATEGIES:
            detail = comparison["strategy_details"].get(strategy, {})
            stage = stage_status.get(f"strategy_{strategy}") or {"status": "not_run", "reason": "단계에 도달하지 않았다"}
            row = dict(detail.get("summary") or {"id": strategy, "name": _strategy_name(strategy)})
            row.update({"status": stage["status"], "reason": stage["reason"]})
            if "summary" not in detail and "metrics" in detail:
                row.update({k: detail["metrics"].get(k) for k in ("n_targeted", "treatment_mix")})
            rows.append(row)
        comparison["strategies"] = rows

        events_frame = ctx.get("events_t2", ctx.get("events_t1"))
        # #217 — 고객별 τ̂ (S8 채점 입력). 실패해도 결과 파일 쓰기는 이어 간다 — 사유를 uplift_eval 에 남긴다.
        uplift_eval["cate_file"] = cate_file(out / "artifacts" / CATE_FILE, ctx, extra_outputs,
                                             loaded=config.load_models is not None)
        realism, extra_files = realism_copy(Path(config.realism_report))
        extra_files = {**extra_files, **extra_outputs}
        budget_record = ctx.get("budget") or {
            "status": "not_run", "reason": "S1 단계에 도달하지 않아 S2~S5 예산을 정하지 않았다",
            "explicit_budget_krw": config.budget_krw,
        }
        simulator_version = observed_values(events_frame, "simulator_version") or ctx.get("simulator_version")
        random_seed = observed_values(events_frame, "random_seed") or ctx.get("random_seed")
        header = _header(run_id, generated_at)
        versions = [str(v) for v in (simulator_version or [])]

        # #214 — 모델(ML-008) · Feature(FS-001/002) 저장. 요청이 없으면 아무것도 쓰지 않는다.
        persistence: dict[str, Any] = {
            "requested": {"models_root": config.models_root, "feature_store_root": config.feature_store_root,
                          "load_models": config.load_models},
            "models": None, "features": None,
        }
        if config.models_root is not None:
            if config.load_models is not None:
                persistence["models"] = {"status": "not_run",
                                         "reason": "--load-models 실행 — 불러온 모델을 다시 저장하지 않는다"}
            else:
                run_info = {"run_id": run_id, "seed": config.seed, "num_customers": config.num_customers,
                            "profile": config.profile, "t1": ctx["timeline"].get("t1"),
                            "repo_commit": start_state.get("head"), "simulator_versions": versions}
                try:
                    persistence["models"] = persist_models(
                        Path(config.models_root), run_id, ctx,
                        {"churn": churn_eval, "uplift": uplift_eval, "clv": clv_eval}, run_info)
                except Exception as error:  # NotRun(모듈 없음) 포함 — 삼키지 않고 failed 로 적는다
                    persistence["models"] = {"status": "failed", "reason": f"{type(error).__name__}: {error}"}
        if config.feature_store_root is not None:
            try:
                persistence["features"] = persist_features(Path(config.feature_store_root), run_id, ctx)
            except Exception as error:
                persistence["features"] = {"status": "failed", "reason": f"{type(error).__name__}: {error}"}
        persistence["status"] = persistence_status(persistence)

        model_versions: dict[str, Any] = {
            kind: record.get("model_version")
            for kind, record in ((persistence.get("models") or {}).get("models") or {}).items()
            if isinstance(record, Mapping) and record.get("status") == "ok"
        }
        model_versions.update({kind: meta.get("model_version") for kind, (_, meta) in loaded_models.items()})
        try:  # NFR-01 — 8개 키. 모르는 값은 null
            nfr01 = decision_fn("versions_record")(
                service_version=start_state.get("head"), simulator_version=", ".join(versions) if versions else None,
                customer_seed=config.seed, random_seed=random_seed or None, model_versions=model_versions or None)
        except NotRun as reason:
            nfr01 = {"status": "not_run", "reason": str(reason)}

        run_meta = {
            **header,
            "seed": config.seed,
            "N": config.num_customers,
            "num_customers": config.num_customers,
            "profile": config.profile,
            "warmup_days": warmup,
            "warmup_basis": warmup_basis,
            "label_window_days": LABEL_WINDOW_DAYS,
            "timeline": ctx["timeline"],
            "simulator_version": ", ".join(versions) if versions else None,
            "simulator_versions": versions,
            "random_seed_observed": random_seed or None,
            "event_counts_by_type_until_t2": ctx.get("event_types_t2"),
            "event_source": reader.source,
            "event_source_fallback_reason": reader.fallback_reason,
            "raw_roots": {"main": main_root, **{s: branch_raw_root(out, s) for s in STRATEGIES}},
            "budget": budget_record,
            "cost_basis": basis,
            "cost_basis_reason": basis_reason,
            "planning_costs_krw": costs,
            "planning_costs_source": costs_source,
            "purchase_generated": {"value": ctx.get("purchase_generated"), "detail": ctx.get("purchase_detail")},
            "label_observation": ctx.get("label_observation"),
            "main_metric_windows": ctx.get("main_metric_windows"),
            "event_read_evidence": ctx.get("event_read_evidence", {}),
            "margin_rate": ctx.get("margin_basis") or {"status": "not_run", "reason": "본선 단계에 도달하지 않았다"},
            "feature_attrs": {
                key: {k: ctx[key].attrs.get(k) for k in ("index_time", "population_scope", "incomplete_windows")}
                for key in ("X1", "X2") if key in ctx and hasattr(ctx[key], "attrs")
            },
            "realism_report": realism,
            "assignment_files": assignment_files,
            "churn_options": {"cv_folds": config.cv_folds, "max_train_rows": config.max_train_rows,
                              "note": "지정하지 않으면 config/model_config.yaml churn.cv_folds "
                                      f"(Stratified {load_model_config().churn.cv_folds}-Fold) · 전원"},
            "rct": rct_meta,
            "strategy_comparison_protocol": {
                "snapshot_at": ctx["timeline"].get("t2"),
                "single_snapshot_token": "snapshot_t2" in stage_status and stage_status["snapshot_t2"]["status"] == "ok",
                "strategies_restored_from_it": [s for s in STRATEGIES if log.ok(f"strategy_{s}")],
                "same_random_numbers": "같은 토큰에서 restore — 같은 시점·같은 고객 상태·같은 난수 (docs/simulator_api.md restore)",
                "rct_effect_overlap": "RCT 처치 효과 창 [t1, t1+42) 는 t2 에서 끝난다 — 전략 창 [t2, t2+42) 와 겹치지 않는다(정의상)",
                "contribution_profit": "분기마다 sim.exchange_bundle → 측정 계층 publish.build_kpi_report 의 "
                                       "contribution_profit(교환 묶음 COGS 차감, 시뮬레이터 출처만). 결손이면 증분이익 "
                                       "계산 불가. 분기 창 DQ-09(창 주문으로 좁힌 묶음 ↔ 이벤트 금액) · DQ-02b(주문당 "
                                       "시뮬레이터 purchase 1건) 중 하나라도 fail 이면 quality_failed 로 같은 차단 — "
                                       "strategy_details.*.measured_economics (DR-169)",
            },
            "decision_modules": {k: decision_available(k) for k in DECISION_API},
            "versions": nfr01,           # NFR-01 (#214)
            "persistence": persistence,  # ML-008 · FS-001/002 (#214)
            "models_loaded_from": {
                "path": config.load_models, "trained_run": (loaded_manifest.get("run") or {}).get("run_id"),
                "kinds": sorted(loaded_models),
            } if config.load_models is not None else None,
            "provenance": provenance(start_state, require_clean=config.require_clean),
            "stages": log.stages,
        }
        # 머리(sprint·sealed·run_id·generated_at)와 단계 상태가 마지막에 오게 둔다 — 평가 결과의 키가 덮지 못한다.
        payloads = {
            "run_meta": run_meta,
            "churn_eval": {**churn_eval, **status_of("churn", "churn_temporal_holdout"), **header},
            "clv_eval": {**clv_eval, **status_of("clv"), **header},
            "uplift_eval": {**uplift_eval, **status_of("uplift"), **header},
            "segments": {**segments_out, **status_of("segments"), **header},
            "strategy_comparison": {
                **comparison,
                "budget_krw": (ctx.get("budget") or {}).get("planning_budget_krw"),
                "window": {"start": ctx["timeline"].get("t2"), "end": ctx["timeline"].get("end"),
                           "days": LABEL_WINDOW_DAYS},
                **status_of("roi_summary", "snapshot_t2", "what_if", *(f"strategy_{s}" for s in STRATEGIES)),
                **header,
            },
            "ab_test": {**ab_test, "rct": rct_meta, **status_of("ab_test"), **header},
        }
        run_dir = write_results(Path(config.results_root), run_id, payloads, extra_files)
        _log(f"결과: {run_dir}")
        if config.capture is not None:  # src/main.py --mode 산출물용 (#206)
            config.capture.update(ctx, costs=costs, run_dir=run_dir)
    return run_dir


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m src.orchestration.run_sprint",
        description="스프린트 v0 — 탐색 RCT → Churn/Uplift/CLV → S0~S5 전략 비교를 한 번에 실행한다.",
    )
    parser.add_argument("--seed", type=int, default=EXPERIMENT.holdout.development_seed)
    parser.add_argument("--customers", type=int, default=EXPERIMENT.run.num_customers)
    parser.add_argument("--profile", default=EXPERIMENT.run.profile)
    parser.add_argument("--out", type=Path, required=True, help="시뮬레이터 출력 루트의 상위 폴더 (빈 폴더)")
    parser.add_argument("--results-root", type=Path, default=DEFAULT_RESULTS_ROOT)
    parser.add_argument("--warmup-days", type=int, default=None,
                        help="기본: --profile 이 config run.profile 이면 config run.warmup_days, "
                             "아니면 프로파일 권장값(data_spec §2.2)")
    parser.add_argument("--budget-krw", type=int, default=None,
                        help="S2~S5 의 plan 예산(원) — 변동비(캠페인 고정비 제외), 탐색용. "
                             "기본: C_rule = S1(상한 없음) 배정의 계획 비용 합. S1 이 없으면 S2~S5 는 not_run")
    parser.add_argument("--run-id", default=None)
    parser.add_argument("--cv-folds", type=int, default=None,
                        help="churn 교차검증 fold 수 (기본: config/model_config.yaml churn.cv_folds)")
    parser.add_argument("--max-train-rows", type=int, default=None,
                        help="churn 학습·CV 표본 상한 — 클래스 비율 유지 추출 (기본: 전원)")
    parser.add_argument("--realism-report", type=Path, default=REALISM_REPORT,
                        help="있으면 결과 폴더로 사본을 둔다 (기본: docs/research/realism_report.json)")
    parser.add_argument("--require-clean", action="store_true",
                        help="저장소에 커밋 전 변경(추적 파일 변경 · .gitignore 밖 새 파일)이 있으면 시뮬레이션 전에 "
                             "멈춘다(종료 코드 4). 봉인 실행(GATE 2 Baseline)은 이 옵션으로 돌린다 (#262)")
    parser.add_argument("--models-root", type=Path, default=None,
                        help="학습한 모델을 <경로>/<run_id>/ 에 저장한다(ML-008, #214). 기본: 저장하지 않음 — "
                             "src/main.py 는 기본으로 models/ 에 저장한다")
    parser.add_argument("--feature-store-root", type=Path, default=None,
                        help="Feature · 라벨을 <경로>/<run_id>/ 에 parquet 로 저장한다(FS-001/002). 기본: 저장하지 않음")
    parser.add_argument("--load-models", type=Path, default=None,
                        help="저장된 모델 폴더(<models-root>/<run_id>) — 다시 학습하지 않고 불러와 이 실행의 데이터로 "
                             "평가만 한다(GATE 4 전제). 못 쓰면 시뮬레이션 전에 멈춘다(종료 코드 6)")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    config = SprintConfig(
        seed=args.seed, num_customers=args.customers, profile=args.profile, out=args.out,
        results_root=args.results_root, warmup_days=args.warmup_days, budget_krw=args.budget_krw,
        run_id=args.run_id, realism_report=args.realism_report,
        cv_folds=args.cv_folds, max_train_rows=args.max_train_rows, require_clean=args.require_clean,
        models_root=args.models_root, feature_store_root=args.feature_store_root, load_models=args.load_models,
    )
    started = time.perf_counter()
    try:
        run_dir = run(config)
    except (DirtyRepoError, ModelLoadError) as error:
        _log(str(error))
        return error.exit_code
    meta = json.loads((run_dir / "run_meta.json").read_text(encoding="utf-8"))
    counts = Counter(stage["status"] for stage in meta["stages"])
    saved = (meta.get("persistence") or {}).get("status")
    _log(f"완료 {time.perf_counter() - started:.1f}s — 단계 {dict(sorted(counts.items()))} · 저장 {saved}")
    return 1 if counts.get("failed") or saved == "failed" else 0


if __name__ == "__main__":
    raise SystemExit(main())
