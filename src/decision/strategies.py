"""전략 S0~S5 — 고객별 처치 배정 계획 (이슈 #145 · D7).

이 모듈은 **순수 함수**만 둔다. 입력은 고객 ID 를 키로 하는 점수 묶음이고 출력은
``{customer_id: "T1".."T4"}`` 다. 미배정(T0) 고객은 결과에 **넣지 않는다.**

★ GATE 2 정신 — S0·S1 은 AI 결과(Uplift·Churn 모델 성능)를 보기 **전에** 커밋한다.
  이 파일에서 ``S1_RULE`` 과 ``plan_S1`` 의 선정 규칙은 이후 바꾸지 않는다 (SRS BASE-003).
  기준선을 낮추면 Incremental Profit 이 올라가지만 아무 의미가 없다.

S0·S1 은 표준 라이브러리만 쓴다 — numpy/pandas 가 없는 CI 잡에서도 import 되고
테스트된다. ``scores`` 의 값은 ``pd.Series`` 든 ``dict`` 든 ``.items()`` 만 있으면 된다.
"""

from __future__ import annotations

import math
from typing import Any, Mapping

# ── S1 Rule-based Baseline ───────────────────────────────────────────────────
#
# 근거: docs/data_spec.html §12.1 (S1 선정 규칙 원안) · PRD §28 / SRS §churn
#       "At Risk = 28일 미구매, Churn = 42일 이상 미구매"(프로젝트 초기 가설) ·
#       PRD §60 / SRS BASE-002 "최근 N일 미구매 → Win-back Coupon" ·
#       PRD §15 T3 Strong Win-back Coupon · economic_config.yaml treatment_cost.T3.
#
#   N(하한) = 28일 — At Risk 진입 시점. 그 전에 보내면 어차피 살 고객에게 쿠폰을 낭비한다.
#   상한   = 90일 — 그 이후는 회수 확률이 급감한다고 보는 실무 제약(data_spec §12.1).
#   구매 2회 이상 — 1회 구매 후 이탈은 온보딩 실패이며 Win-back 대상이 아니다.
#   우선순위 — days_since_last_purchase 내림차순(가장 위험한 고객부터), 동률은 customer_id 오름차순.
#   예산 — budget_krw 가 None 이면 조건 충족 전원(= GATE 2 에서 C_rule 실측용 실행).
#          값이 있으면 위 순서대로 costs["T3"] 를 누적해 예산을 넘기기 직전까지.
S1_RULE: dict[str, Any] = {
    "id": "S1",
    "name": "Rule-based (기준선)",
    "action": "T3",
    "min_days_since_last_purchase": 28,
    "max_days_since_last_purchase": 90,
    "min_lifetime_order_count": 2,
    "order_by": "days_since_last_purchase DESC, customer_id ASC",
    "source": "docs/data_spec.html §12.1 · PRD §28·§60 · SRS BASE-002",
}

#: S0·S1 에 쓰이는 처치 어휘. T0 은 결과 dict 에 넣지 않는다.
TREATMENTS = ("T1", "T2", "T3", "T4")


def _missing(value: Any) -> bool:
    """None · NaN 을 결손으로 본다. 결손을 0 으로 채우지 않는다."""
    if value is None:
        return True
    try:
        return math.isnan(float(value))
    except (TypeError, ValueError):
        return True


def _as_mapping(series: Any) -> dict[str, Any]:
    """pd.Series 또는 dict → {customer_id: value}."""
    if series is None:
        return {}
    return {str(k): v for k, v in series.items()}


def plan_S0(scores: Mapping[str, Any] | None = None, budget_krw: int | None = None,
            costs: Mapping[str, Any] | None = None) -> dict[str, str]:
    """S0 무처치 — 아무에게도 보내지 않는다 (PRD §60 · SRS BASE-001).

    >>> plan_S0({"days_since_last_purchase": {"C00000001": 50}})
    {}
    """
    return {}


def s1_eligibility(scores: Mapping[str, Any]) -> dict[str, Any]:
    """S1 규칙의 조건별 적용 상태와 결손 건수.

    ``plan_S1`` 은 dict 만 돌려주므로, **어떤 조건이 실제로 적용됐는지**를 여기서 따로
    밝힌다. 선택 입력(``lifetime_order_count`` · ``eligible``)이 없으면 그 조건은
    ``not_run`` 이다 — 통과가 아니다.
    """
    days = _as_mapping(scores.get("days_since_last_purchase"))
    orders = scores.get("lifetime_order_count")
    eligible = scores.get("eligible")
    return {
        "rule": dict(S1_RULE),
        "n_customers": len(days),
        "n_days_missing": sum(1 for v in days.values() if _missing(v)),
        "conditions": {
            "days_window": "applied",
            "lifetime_order_count": "applied" if orders is not None else "not_run",
            "eligible_flag": "applied" if eligible is not None else "not_run",
        },
    }


def plan_S1(scores: Mapping[str, Any], budget_krw: int | None = None,
            costs: Mapping[str, Any] | None = None) -> dict[str, str]:
    """S1 Rule-based — 최근 28~90일 미구매 · 구매 2회 이상 → T3 Win-back 쿠폰.

    scores:
      ``days_since_last_purchase`` (필수) — customer_id → 일수. 결손(구매 이력 없음 등)은
        규칙을 판정할 수 없으므로 **배정하지 않는다** (0 일로 채우지 않는다).
      ``lifetime_order_count`` (선택) — 있으면 2 회 이상만. 없으면 조건 미적용(``s1_eligibility``).
      ``eligible`` (선택) — 있으면 참인 고객만.
    budget_krw: None 이면 상한 없음(C_rule 실측 실행). 값이 있으면 ``costs["T3"]`` 를
      고객당 계획 비용으로 우선순위 순서대로 누적해 예산을 넘기지 않는다.

    >>> plan_S1({"days_since_last_purchase": {"C1": 10, "C2": 30, "C3": 95, "C4": 60}})
    {'C4': 'T3', 'C2': 'T3'}
    >>> plan_S1({"days_since_last_purchase": {"C2": 30, "C4": 60}}, 7030, {"T3": 7030})
    {'C4': 'T3'}
    """
    days = _as_mapping(scores.get("days_since_last_purchase"))
    if not days and scores.get("days_since_last_purchase") is None:
        raise KeyError("plan_S1 은 scores['days_since_last_purchase'] 가 필요하다")
    orders = scores.get("lifetime_order_count")
    orders = _as_mapping(orders) if orders is not None else None
    eligible = scores.get("eligible")
    eligible = _as_mapping(eligible) if eligible is not None else None

    lo = S1_RULE["min_days_since_last_purchase"]
    hi = S1_RULE["max_days_since_last_purchase"]
    min_orders = S1_RULE["min_lifetime_order_count"]

    picked: list[tuple[float, str]] = []
    for cid, d in days.items():
        if _missing(d):
            continue
        d = float(d)
        if not (lo <= d <= hi):
            continue
        if orders is not None:
            n = orders.get(cid)
            if _missing(n) or float(n) < min_orders:
                continue
        if eligible is not None:
            flag = eligible.get(cid)
            if _missing(flag) or not bool(flag):
                continue
        picked.append((d, cid))

    picked.sort(key=lambda t: (-t[0], t[1]))

    action = S1_RULE["action"]
    if budget_krw is None:
        return {cid: action for _, cid in picked}

    if costs is None or _missing(costs.get(action)):
        raise ValueError("예산이 주어지면 costs['T3'](고객당 계획 비용)가 필요하다")
    unit = float(costs[action])
    out: dict[str, str] = {}
    spent = 0.0
    for _, cid in picked:
        if spent + unit > budget_krw:
            break
        out[cid] = action
        spent += unit
    return out
