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


# ═════════════════════════════════════════════════════════════════════════════
# 이하 S2~S5 — S1 커밋(ce05a66) 이후에 추가했다. 위 S1 규칙은 건드리지 않았다.
# AI 전략은 pandas 가 필요하므로 함수 안에서 import 한다 (S0·S1 은 의존성 없이 동작).
# ═════════════════════════════════════════════════════════════════════════════

STRATEGY_NAMES: dict[str, str] = {
    "S0": "무처치",
    "S1": "Rule-based (기준선)",
    "S2": "Churn AI",
    "S3": "Churn + Uplift",
    "S4": "Churn + Uplift + CLV",
    "S5": "Full AI + 예산 최적화",
}

#: S2 의 기본 처치 — S1 과 같은 T3 로 두어 S1 대비 차이가 **타깃 선정**에서만 나오게 한다.
S2_DEFAULT_TREATMENT = "T3"


class NotComputable(ValueError):
    """필요한 점수가 없어 전략을 계산할 수 없다 — 빈 배정(0 명)으로 대신하지 않는다."""


def planning_costs(treatment_cost: Mapping[str, Any], message_cost_krw: float) -> dict[str, float]:
    """고객당 **계획 비용**(예산 차감용) = 처치 단가 + 메시지 비용.

    ``economic_config.yaml`` 의 ``treatment_cost``·``cost_accounting.message_cost_krw`` 를
    그대로 받는다(파일은 호출자가 읽는다). 쿠폰이 전부 쓰인다고 보는 **상한**이다 —
    실현 비용이 예산을 넘지 않게 하려는 보수적 선택이며, 사용률을 곱한 기대 비용이 아니다.
    캠페인 고정비는 고객 단위가 아니므로 여기 넣지 않는다(호출자가 예산에서 먼저 뺀다).
    """
    out = {}
    for t in TREATMENTS:
        unit = treatment_cost[t]["unit_cost_krw"] if isinstance(treatment_cost[t], Mapping) else treatment_cost[t]
        if _missing(unit):
            raise NotComputable(f"treatment_cost[{t}] 단가가 없다")
        out[t] = float(unit) + float(message_cost_krw)
    return out


def _need(scores: Mapping[str, Any], key: str, sid: str):
    v = scores.get(key)
    if v is None:
        raise NotComputable(f"{sid} 는 scores['{key}'] 가 필요하다")
    return v


def _need_budget(budget_krw: Any, costs: Mapping[str, Any] | None, sid: str) -> None:
    if budget_krw is None:
        raise ValueError(f"{sid} 는 예산 상한이 필요하다 (모든 AI 전략 ≤ C_rule)")
    if not costs:
        raise ValueError(f"{sid} 는 costs(고객당 계획 비용)가 필요하다")


def _fill(order: list[tuple[str, str]], budget_krw: float, costs: Mapping[str, Any]) -> dict[str, str]:
    """우선순위 순서대로 예산이 허락하는 고객을 배정한다(넘치는 고객은 건너뛴다)."""
    out: dict[str, str] = {}
    spent = 0.0
    for cid, t in order:
        unit = float(costs[t])
        if spent + unit <= budget_krw:
            out[cid] = t
            spent += unit
    return out


def _value(scores: Mapping[str, Any], sid: str):
    """CLV → 가치(원). ``margin_rate`` 가 있으면 CLV(매출 기준)에 곱하고, 없으면 CLV 가
    이미 이익 기준이라고 본다(DR-145)."""
    clv = _need(scores, "clv", sid)
    rate = scores.get("margin_rate")
    return clv.astype(float) * (float(rate) if rate is not None else 1.0)


def plan_S2(scores, budget_krw, costs) -> dict[str, str]:
    """S2 Churn AI — ``churn_p`` 내림차순, 전원 기본 처치(T3). 결손 churn_p 는 제외."""
    _need_budget(budget_krw, costs, "S2")
    p = _need(scores, "churn_p", "S2").astype(float).dropna()
    df = p.rename("p").to_frame()
    df["cid"] = df.index.astype(str)
    df = df.sort_values(["p", "cid"], ascending=[False, True], kind="mergesort")
    return _fill([(c, S2_DEFAULT_TREATMENT) for c in df["cid"]], budget_krw, costs)


def plan_S3(scores, budget_krw, costs) -> dict[str, str]:
    """S3 Churn + Uplift — 고객별 CATE 최대 처치를 고르고 ``churn_p × CATE`` 내림차순.

    CATE ≤ 0(효과 없음·역효과 = Sleeping Dog)은 제외한다. 비용은 순서에 반영하지 않는다
    (그것이 S4·S5 와의 차이다)."""
    _need_budget(budget_krw, costs, "S3")
    p = _need(scores, "churn_p", "S3").astype(float)
    cate = _need(scores, "cate", "S3").astype(float)
    cate = cate[[t for t in TREATMENTS if t in cate.columns]]
    cate = cate[cate.notna().any(axis=1)]
    best_t = cate.idxmax(axis=1)
    best_u = cate.max(axis=1)
    df = best_t.rename("t").to_frame()
    df["score"] = p.reindex(df.index) * best_u
    df = df[(best_u > 0) & df["score"].notna()]
    df["cid"] = df.index.astype(str)
    df = df.sort_values(["score", "cid"], ascending=[False, True], kind="mergesort")
    return _fill(list(zip(df["cid"], df["t"])), budget_krw, costs)


def _expected_gain(scores, sid: str):
    """처치별 총 기대 증분가치(원) = CATE × 가치. 비용 차감 전."""
    cate = _need(scores, "cate", sid).astype(float)
    cate = cate[[t for t in TREATMENTS if t in cate.columns]]
    return cate.mul(_value(scores, sid).reindex(cate.index), axis=0)


def plan_S4(scores, budget_krw, costs) -> dict[str, str]:
    """S4 + CLV — 고객별 ``CATE_t × 가치 − cost_t`` 최대 처치, 그 값 내림차순, 양수만.

    churn_p 는 순서에 직접 쓰지 않는다 — CATE 가 이미 '처치로 바뀌는 몫' 이다(data_spec §13.1)."""
    _need_budget(budget_krw, costs, "S4")
    import pandas as pd

    gain = _expected_gain(scores, "S4")
    net = gain - pd.Series({t: float(costs[t]) for t in gain.columns})
    net = net[net.notna().any(axis=1)]
    df = net.idxmax(axis=1).rename("t").to_frame()
    df["v"] = net.max(axis=1)
    df = df[df["v"] > 0]
    df["cid"] = df.index.astype(str)
    df = df.sort_values(["v", "cid"], ascending=[False, True], kind="mergesort")
    return _fill(list(zip(df["cid"], df["t"])), budget_krw, costs)


def plan_S5(scores, budget_krw, costs) -> dict[str, str]:
    """S5 Full AI + 예산 최적화 — ``optimize.optimize_budget`` (다중선택 배낭 탐욕 근사)."""
    from .optimize import optimize_budget

    _need_budget(budget_krw, costs, "S5")
    gain = _expected_gain(scores, "S5")
    return optimize_budget(gain, costs, budget_krw)


_PLANNERS = {"S0": plan_S0, "S1": plan_S1, "S2": plan_S2, "S3": plan_S3, "S4": plan_S4, "S5": plan_S5}


def plan(strategy_id: str, scores: Mapping[str, Any], budget_krw: int | None,
         costs: Mapping[str, Any] | None) -> dict[str, str]:
    """전략 ID → ``{customer_id: "T1".."T4"}``. 미배정(T0) 고객은 넣지 않는다.

    scores 키: ``churn_p``(Series) · ``cate``(DataFrame T1~T4) · ``clv``(Series|None) ·
    ``days_since_last_purchase``(Series) · ``eligible``(Series, S1~S5 필수) · 선택
    ``lifetime_order_count`` · ``margin_rate``. 필요한 점수(``REQUIRED_SCORES``)가 없으면 ``NotComputable`` — 빈 배정으로
    대신하지 않는다. ``costs`` 는 처치별 고객당 단가 dict(``T0`` 키가 있어도 된다).
    S2~S5 는 ``budget_krw`` 가 None 이면 ValueError(호출 오류 — 모든 AI 전략 ≤ C_rule).

    ★ S1~S5 는 **``eligible`` 이 참인 고객 안에서만** 고른다(data_spec §4.1 · #194 · DR-234). 전략마다
      고를 수 있는 고객이 다르면 S1 대비 증분이 "더 잘 골랐다" 가 아니라 "더 넓은 곳에서 골랐다" 가
      된다. 거르기는 플래너보다 **먼저** 한다 — 고른 뒤에 빼면 예산을 부적격 고객에게 쓰고 남긴다.
    """
    if strategy_id not in _PLANNERS:
        raise KeyError(f"알 수 없는 전략: {strategy_id!r} (S0~S5)")
    missing = [k for k in REQUIRED_SCORES[strategy_id] if scores.get(k) is None]
    if missing:
        raise NotComputable(f"{strategy_id} 에 필요한 점수가 없다: {missing}")
    if "eligible" in REQUIRED_SCORES[strategy_id]:
        scores = within_eligible(scores)
    return _PLANNERS[strategy_id](scores, budget_krw, costs)


def within_eligible(scores: Mapping[str, Any]) -> dict[str, Any]:
    """고객별 점수를 ``eligible`` 이 참인 고객으로 좁힌 사본. 결손 플래그는 거짓으로 본다(판정할 수 없다).

    Series · DataFrame 은 인덱스로, dict 는 키로 거른다. 스칼라(``margin_rate``)는 그대로 둔다.
    """
    flags = _as_mapping(scores["eligible"])
    keep = {cid for cid, flag in flags.items() if not _missing(flag) and bool(flag)}
    out: dict[str, Any] = {}
    for key, value in scores.items():
        if hasattr(value, "index") and hasattr(value, "loc"):
            out[key] = value.loc[[str(cid) in keep for cid in value.index]]
        elif isinstance(value, Mapping):
            out[key] = {cid: v for cid, v in value.items() if str(cid) in keep}
        else:
            out[key] = value
    return out


#: 전략별 필수 점수. 없으면 ``plan`` 이 ``NotComputable`` 을 던진다(빈 배정으로 대신하지 않는다).
#: S1~S5 는 ``eligible`` 이 필수다 — 그 안에서만 고른다(DR-234). 없으면 전략이 not_run 이다.
#: S1 의 ``lifetime_order_count`` 는 선택 — 없으면 그 조건이 not_run(``s1_eligibility``).
REQUIRED_SCORES: dict[str, tuple[str, ...]] = {
    "S0": (),
    "S1": ("days_since_last_purchase", "eligible"),
    "S2": ("churn_p", "eligible"),
    "S3": ("churn_p", "cate", "eligible"),
    "S4": ("cate", "clv", "eligible"),
    "S5": ("cate", "clv", "eligible"),
}


def plan_summary(assignment: Mapping[str, str]) -> dict[str, Any]:
    """배정 결과 → 요약 행의 ``n_targeted`` · ``treatment_mix``. 표준 라이브러리만 쓴다."""
    mix: dict[str, int] = {}
    for t in assignment.values():
        if t not in TREATMENTS:
            raise ValueError(f"배정에 처치 어휘 밖의 값이 있다: {t!r}")
        mix[t] = mix.get(t, 0) + 1
    return {"n_targeted": len(assignment), "treatment_mix": dict(sorted(mix.items()))}
