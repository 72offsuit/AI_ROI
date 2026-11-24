"""예산 최적화 — 다중선택 배낭(MCKP)의 탐욕 근사 · What-if (이슈 #145 · SRS OPT-001~005).

문제: 고객 i 마다 처치 t ∈ {T1..T4} 중 **최대 1개**를 고른다.

    maximize   Σ (gain[i,t] − cost[t]) · a[i,t]        (objective="net", 기본)
           또는 Σ gain[i,t] · a[i,t]                  (objective="gross", PRD §52 원식)
    s.t.       Σ cost[t] · a[i,t] ≤ budget,   Σ_t a[i,t] ≤ 1

``gain`` 은 처치의 **총 기대 증분가치(원, 비용 차감 전)** — 예: CATE × CLV(이익 기준).
``net = gain − cost`` 가 0 이하인 선택지는 처음부터 제외한다. 음수 gain(역효과 =
Sleeping Dog)은 net 도 음수이므로 자동으로 빠진다.

알고리즘(결정적):
  1) 고객마다 net>0 인 선택지 중 **효율(net/cost)** 최고를 고르고, 효율 내림차순으로
     예산이 허락하는 한 배정한다(동률은 customer_id 오름차순).
  2) 업그레이드 1회전 — 배정된 고객을 더 비싸지만 net 이 큰 선택지로 바꾸는 후보를
     **증분 효율(Δnet/Δcost)** 내림차순으로 남은 예산 안에서 적용한다.
이것은 근사다. 최적해 보장이 없고(LP 완화의 상계와 비교하지 않았다), 예산이 작아
고가 처치 1건이 다수 저가 처치보다 나은 경우를 놓칠 수 있다(DR-145).
"""

from __future__ import annotations

from typing import Any, Mapping

import numpy as np
import pandas as pd

TREATED = ("T1", "T2", "T3", "T4")


def _validate(expected_gain: pd.DataFrame, cost: Mapping[str, Any]) -> list[str]:
    arms = [t for t in TREATED if t in expected_gain.columns]
    if not arms:
        raise ValueError("expected_gain 에 T1~T4 열이 없다")
    for t in arms:
        if t not in cost or cost[t] is None:
            raise ValueError(f"cost[{t}] 가 없다 — 비용 결손을 0 으로 보지 않는다")
        if float(cost[t]) <= 0:
            raise ValueError(f"cost[{t}] 는 양수여야 한다 (효율 계산의 분모)")
    return arms


def optimize_budget(expected_gain: pd.DataFrame, cost: Mapping[str, Any], budget_krw: float,
                    objective: str = "net") -> dict[str, str]:
    """고객당 1 처치, 총비용 ≤ 예산. 반환 ``{customer_id: "T1".."T4"}`` (미배정 생략)."""
    return _solve(expected_gain, cost, budget_krw, objective)["assignment"]


def _solve(expected_gain: pd.DataFrame, cost: Mapping[str, Any], budget_krw: float,
           objective: str = "net") -> dict[str, Any]:
    if objective not in ("net", "gross"):
        raise ValueError("objective 는 'net' 또는 'gross'")
    if budget_krw is None or budget_krw < 0:
        raise ValueError("budget_krw 는 0 이상이어야 한다")
    arms = _validate(expected_gain, cost)
    c = {t: float(cost[t]) for t in arms}
    gain = expected_gain[arms].astype(float)
    net = gain - pd.Series(c)
    value = net if objective == "net" else gain
    feasible = (net > 0) & gain.notna()          # 이익이 안 나는 선택지·결손 제외

    # 1) 효율 최고 선택지로 탐욕 배정
    eff = value.where(feasible) / pd.Series(c)
    eff = eff[eff.notna().any(axis=1)]           # 선택지가 하나도 없는 고객은 후보가 아니다
    cand = pd.DataFrame({"t": eff.idxmax(axis=1, skipna=True), "eff": eff.max(axis=1, skipna=True)})
    cand["cid"] = cand.index.astype(str)
    cand = cand.sort_values(["eff", "cid"], ascending=[False, True], kind="mergesort")

    remaining = float(budget_krw)
    assign: dict[str, str] = {}
    for cid, t in zip(cand.index, cand["t"]):
        if c[t] <= remaining:
            assign[cid] = t
            remaining -= c[t]

    # 2) 업그레이드 1회전 — 더 큰 value 의 선택지로 교체
    ups = []
    for cid, t in assign.items():
        row_v, row_f = value.loc[cid], feasible.loc[cid]
        for t2 in arms:
            if t2 == t or not row_f[t2]:
                continue
            dv, dc = row_v[t2] - row_v[t], c[t2] - c[t]
            if dv > 0 and dc > 0:
                ups.append((dv / dc, str(cid), cid, t2, dc))
            elif dv > 0 and dc <= 0:
                ups.append((np.inf, str(cid), cid, t2, dc))
    ups.sort(key=lambda u: (-u[0], u[1]))
    upgraded = set()
    for _, _, cid, t2, dc in ups:
        if cid in upgraded or dc > remaining:
            continue
        assign[cid] = t2
        remaining -= dc
        upgraded.add(cid)

    spend = sum(c[t] for t in assign.values())
    exp_gain = float(sum(gain.at[cid, t] for cid, t in assign.items()))
    return {
        "assignment": assign, "budget_krw": float(budget_krw), "spend_krw": spend,
        "expected_gain_krw": exp_gain, "expected_net_krw": exp_gain - spend,
        "n_upgraded": len(upgraded), "objective": objective,
        "n_candidates_positive_net": int(feasible.any(axis=1).sum()),
    }


def what_if(budgets: list[float], expected_gain: pd.DataFrame, cost: Mapping[str, Any],
            expected_conversion: pd.DataFrame | None = None,
            expected_revenue: pd.DataFrame | None = None,
            objective: str = "net") -> list[dict[str, Any]]:
    """예산 시나리오별 결과 (SRS OPT-005 · PRD §54).

    ``expected_conversion`` — 처치별 증분 전환/유지 확률(예: 이진 결과의 CATE). 있으면
      배정 고객의 합 = 기대 전환 증분 = 기대 구제 고객 수. 없으면 **계산 불가(None)**.
    ``expected_revenue`` — 처치별 기대 증분 매출(원). 없으면 계산 불가(None).
    ROI = 기대 순이익 / 지출 (지출 0 이면 계산 불가).
    """
    rows = []
    for b in budgets:
        r = _solve(expected_gain, cost, b, objective)
        a = r["assignment"]
        mix: dict[str, int] = {}
        for t in a.values():
            mix[t] = mix.get(t, 0) + 1

        def total(df: pd.DataFrame | None) -> float | None:
            if df is None:
                return None
            vals = [df.at[cid, t] for cid, t in a.items()]
            if any(pd.isna(v) for v in vals):
                return None
            return float(sum(vals))

        conv = total(expected_conversion)
        rows.append({
            "budget_krw": float(b), "target_count": len(a), "treatment_mix": dict(sorted(mix.items())),
            "spend_krw": r["spend_krw"],
            "expected_gain_krw": r["expected_gain_krw"], "expected_net_krw": r["expected_net_krw"],
            "expected_conversion": conv, "expected_saved_customers": conv,
            "expected_revenue_krw": total(expected_revenue),
            "expected_roi": (r["expected_net_krw"] / r["spend_krw"]) if r["spend_krw"] > 0 else None,
        })
    return rows


def what_if_budgets(base_budget_krw: float, ratios: tuple[float, ...] = (0.5, 1.0, 2.0)) -> list[float]:
    """PRD §54 — 50% / 100% / 200% 예산."""
    return [base_budget_krw * r for r in ratios]


# ═════════════════════════════════════════════════════════════════════════════
# #274 · DR-170 추가 결정 E1~E4 · E6 — 예산이 걸리는 구간 · 혼합 전략 S6 · 예산 근거.
# 모두 **모델이 스스로 예측한 기대값**이다. 시뮬레이터 분기 결과(참 효과)가 아니다.
# ═════════════════════════════════════════════════════════════════════════════

#: DR-170 E2 — 구속 예산 = 같은 실행의 S4 계획 비용(plan 예산에서) × 이 비율. 결과를 보기 전에 고정(#274, 2026-11-16).
BINDING_RATIOS: tuple[float, ...] = (0.25, 0.50, 0.75)

WHAT_IF_LIMITATION = (
    "모델이 스스로 예측한 기대값(CATE × CLV × margin_rate − 계획 비용)이다 — 시뮬레이터 결과가 아니다. "
    "S4 · S5 는 이 값을 최대화하도록 만든 방법이라 같은 예산에서 기대값이 큰 것은 대부분 구조적이다(DR-170 한계)"
)
_TOL = 1e-6


def _spend(assignment: Mapping[str, str], cost: Mapping[str, Any]) -> float:
    return float(sum(float(cost[t]) for t in assignment.values()))


def _str_index(frame: pd.DataFrame) -> pd.DataFrame:
    out = frame.copy()
    out.index = [str(c) for c in out.index]
    return out


def _cell(frame: pd.DataFrame, cid: str, t: str) -> float:
    return frame.at[cid, t] if (cid in frame.index and t in frame.columns) else np.nan


def assignment_expectation(assignment: Mapping[str, str], expected_gain: pd.DataFrame, cost: Mapping[str, Any],
                           expected_conversion: pd.DataFrame | None = None) -> dict[str, Any]:
    """배정 하나의 모델 기대값 — 대상 수 · 처치 구성 · 계획 지출 · 기대 증분가치 · 기대 순이익 · 기대 전환.

    기대 증분가치가 없는 고객(점수 결손)은 합에서 빼고 ``n_unscored`` 로 센다 — 0 으로 채우지 않는다. 그때
    ``expected_*`` 는 점수 있는 고객만의 합이고(그 고객의 지출만 뺀다) ``expectation_scope`` 가 그렇게 말한다.
    배정은 있는데 점수 있는 고객이 0명이면 ``expected_*`` 는 None 이다 — 빈 합 0 은 "기대값 0" 과 다르다.
    배정이 0명이면 기대값은 관측된 0 이다(보낸 고객이 없다).
    """
    gain = _str_index(expected_gain)
    conv = _str_index(expected_conversion) if expected_conversion is not None else None
    mix: dict[str, int] = {}
    g_sum = scored_spend = c_sum = 0.0
    unscored = conv_missing = 0
    for cid, t in assignment.items():
        cid = str(cid)
        mix[t] = mix.get(t, 0) + 1
        g = _cell(gain, cid, t)
        if pd.isna(g):
            unscored += 1
            continue
        g_sum += float(g)
        scored_spend += float(cost[t])
        if conv is not None:
            c = _cell(conv, cid, t)
            if pd.isna(c):
                conv_missing += 1
            else:
                c_sum += float(c)
    n_scored = len(assignment) - unscored
    no_basis = bool(assignment) and n_scored == 0
    conversion = None if conv is None or conv_missing or no_basis else c_sum
    if no_basis:
        scope = f"점수 있는 고객 0명 — 배정 {unscored}명 전원이 결손이라 기대값을 계산할 수 없다"
    elif unscored:
        scope = f"점수 있는 고객만 — 결손 {unscored}명은 기대값 합에서 뺐다(0 으로 채우지 않음)"
    else:
        scope = "배정 고객 전원"
    return {
        "target_count": len(assignment), "treatment_mix": dict(sorted(mix.items())),
        "spend_krw": _spend(assignment, cost),
        "expected_gain_krw": None if no_basis else g_sum,
        "expected_net_krw": None if no_basis else g_sum - scored_spend,
        "expected_conversion": conversion, "expected_saved_customers": conversion,
        "n_scored": n_scored, "n_unscored": unscored,
        "expectation_scope": scope,
    }


def paired_net_difference(base: Mapping[str, str], other: Mapping[str, str], expected_gain: pd.DataFrame,
                          cost: Mapping[str, Any]) -> dict[str, Any]:
    """``other − base`` 기대 순이익 차이를 **고객마다 짝지어** 더한다 — 두 배정에 나오는 고객(합집합) 기준.

    - 한쪽에만 배정된 고객의 다른 쪽 순이익은 0 이다(처치 없음 · 비용 없음 — 관측된 0).
    - 어느 쪽이든 배정된 처치의 점수가 없는 고객은 **비교에서 빼고** ``n_excluded_unscored`` 로 센다. 두 합계를 따로 내고
      빼면 결손 고객이 한쪽 합에만 들어가 범위가 다른 수끼리 빼게 된다(PR #313 리뷰).
    - 결손이 없으면 값은 두 배정 기대 순이익 합의 차와 같다. 비교할 고객이 하나도 없으면(전원 결손) None.
    """
    gain = _str_index(expected_gain)
    base = {str(k): v for k, v in base.items()}
    other = {str(k): v for k, v in other.items()}
    diff, compared, excluded = 0.0, 0, 0
    for cid in sorted(set(base) | set(other)):
        nets = []
        for side in (base, other):
            t = side.get(cid)
            if t is None:
                nets.append(0.0)
                continue
            g = _cell(gain, cid, t)
            if pd.isna(g):
                break
            nets.append(float(g) - float(cost[t]))
        if len(nets) < 2:
            excluded += 1
            continue
        compared += 1
        diff += nets[1] - nets[0]
    value = None if (excluded and not compared) else diff
    return {
        "expected_net_diff_krw": value,
        "n_compared": compared,
        "n_excluded_unscored": excluded,
        "scope": ("두 배정에 나오는 고객 전원" if not excluded else
                  f"두 배정 모두 점수 있는 고객 {compared}명만 짝지어 비교 — 결손 {excluded}명 제외(0 으로 채우지 않음)"),
    }


def _diff_assignment_count(a: Mapping[str, str], b: Mapping[str, str]) -> int:
    """두 배정에서 처치가 다르거나 한쪽에만 있는 고객 수."""
    return sum(1 for cid in set(a) | set(b) if a.get(cid) != b.get(cid))


def _binding_interpretation(binding: bool, n_diff: int, gap: Mapping[str, Any]) -> str:
    """DR-170 E1 — 예산 구속 여부와 배정 동일 여부를 각각 본 결과로 문장을 고른다(PR #313 리뷰)."""
    head = "이 예산에서는 예산이 " + ("걸린다" if binding else "남는다")
    if n_diff == 0:
        tail = ("S4 와 S5 가 같은 배정이다 — 4단계(예산 최적화)의 추가 효과가 0 이다. "
                "예산이 걸리는 구간의 차이는 아래 구속 예산 행에서 본다(DR-170 E1)")
        return f"{head}. {tail}"
    value = gap["expected_net_diff_krw"]
    if value is None:
        amount = "기대 순이익 차이는 점수 결손으로 계산할 수 없다"
    else:
        amount = f"기대 순이익 S5 − S4 = {value:,.0f}원"
        if gap["n_excluded_unscored"]:
            amount += f"(점수 있는 고객 {gap['n_compared']}명 기준, 결손 {gap['n_excluded_unscored']}명 제외)"
    cause = ("차이는 예산 제약이 아니라 S5 탐욕 근사(비용 효율 우선 · 고객당 업그레이드 1회)에서 나온다"
             if not binding else "예산이 걸리는 구간의 순서대로 자르기와 최적화의 차이다")
    return f"{head}. S4 와 S5 의 배정이 고객 {n_diff}명에서 다르다 — {cause}. {amount}(DR-170 E1)"


def binding_what_if(scores: Mapping[str, Any], cost: Mapping[str, Any], plan_budget_krw: float,
                    ratios: tuple[float, ...] = BINDING_RATIOS) -> dict[str, Any]:
    """DR-170 E1 · E2 — 예산이 실제로 걸리는 구간에서 S4(순서대로 자르기)와 S5(최적화)를 나란히.

    구속 예산 = S4 계획 비용(plan 예산에서) × ``ratios``. plan 예산에서는 예산 구속 여부(``binding_at_plan_budget``)와
    배정 동일 여부(``same_assignment_at_plan_budget``)를 **따로** 재고, 실제 배정과 기대 순이익 차이(S5 − S4, 고객 짝
    비교)로 해석 문장(E1)을 고른다 — 예산이 남아도 S5 탐욕 근사는 S4 와 다를 수 있다(PR #313 리뷰).
    필요한 점수가 없으면 ``NotComputable``.
    """
    from .strategies import expected_gain_table, plan, within_eligible

    gain = expected_gain_table(scores)
    conv = within_eligible(scores)["cate"]
    s4_plan = plan("S4", scores, plan_budget_krw, cost)
    s5_plan = plan("S5", scores, plan_budget_krw, cost)
    s4_cost = _spend(s4_plan, cost)
    s4_free_cost = _spend(plan("S4", scores, float("inf"), cost), cost)
    binding = s4_free_cost > float(plan_budget_krw) + _TOL
    n_diff = _diff_assignment_count(s4_plan, s5_plan)
    gap = paired_net_difference(s4_plan, s5_plan, gain, cost)
    rows = []
    for ratio in ratios:
        budget = s4_cost * ratio
        for sid in ("S4", "S5"):
            a = plan(sid, scores, budget, cost)
            rows.append({"ratio_of_s4_cost": ratio, "budget_krw": budget, "strategy_id": sid,
                         **assignment_expectation(a, gain, cost, conv)})
    return {
        "status": "ok",
        "definition": "구속 예산 = S4 계획 비용(plan 예산에서) × ratios — 결과 전에 고정(#274 · DR-170 E2)",
        "ratios": list(ratios), "plan_budget_krw": float(plan_budget_krw),
        "s4_planned_cost_krw": s4_cost, "s4_unconstrained_cost_krw": s4_free_cost,
        "binding_at_plan_budget": binding,
        "same_assignment_at_plan_budget": n_diff == 0,
        "n_customers_assigned_differently": n_diff,
        "s5_minus_s4_at_plan_budget": gap,
        "plan_budget_rows": [{"strategy_id": sid, **assignment_expectation(a, gain, cost, conv)}
                             for sid, a in (("S4", s4_plan), ("S5", s5_plan))],
        "interpretation": _binding_interpretation(binding, n_diff, gap),
        "rows": rows,
        "limitation": WHAT_IF_LIMITATION,
    }


#: DR-170 E3 · E4 — 같은 예산 C_rule 에서 나란히 낼 배정. (행 ID, 설명)
HYBRID_ROWS: tuple[tuple[str, str], ...] = (
    ("S1", "규칙만 — 규칙 대상 전원 · T3"),
    ("S6", "규칙 + AI — 규칙 대상 전원 · 처치는 AI 가 고객별로(D-1)"),
    ("S6_ext", "S6 + 남은 예산을 규칙 밖 Eligible 고객에게 S5 방식으로(확장, What-if 전용)"),
    ("S4", "AI 만 — 기대 순이익 양수 고객 내림차순"),
    ("S5", "AI 만 + 예산 최적화 — 배낭 탐욕 근사"),
)


def hybrid_what_if(scores: Mapping[str, Any], cost: Mapping[str, Any], c_rule_krw: float) -> dict[str, Any]:
    """DR-170 E3 · E4 — 같은 예산 C_rule 에서 규칙만(S1) · 규칙 + AI(S6, D-1) · AI 만(S4 · S5)의 모델 기대값.

    S1 대 S6 은 같은 고객 · 같은 순서라 차이가 처치 선택에서만 나온다. 필요한 점수가 없으면 ``NotComputable``.
    """
    from .strategies import expected_gain_table, plan, s6_breakdown, within_eligible

    gain = expected_gain_table(scores)
    conv = within_eligible(scores)["cate"]
    budget = float(c_rule_krw)
    s1 = plan("S1", scores, None, cost)
    s6 = plan("S6", scores, budget, cost)
    remaining = budget - _spend(s6, cost)
    outside = [cid for cid in gain.index if cid not in s1]
    ext = (optimize_budget(gain.loc[outside], cost, remaining)
           if outside and remaining > _TOL else {})
    plans = {"S1": s1, "S6": s6, "S6_ext": {**s6, **ext},
             "S4": plan("S4", scores, budget, cost), "S5": plan("S5", scores, budget, cost)}
    rows = []
    for rid, label in HYBRID_ROWS:
        paired = paired_net_difference(s1, plans[rid], gain, cost)
        rows.append({"row_id": rid, "label": label, **assignment_expectation(plans[rid], gain, cost, conv),
                     "expected_net_vs_S1_krw": paired["expected_net_diff_krw"],
                     "vs_S1_n_compared": paired["n_compared"],
                     "vs_S1_n_excluded_unscored": paired["n_excluded_unscored"],
                     "vs_S1_scope": paired["scope"]})
    excluded = any(r["vs_S1_n_excluded_unscored"] for r in rows)
    return {
        "status": "ok",
        "definition": ("같은 예산 C_rule — S6 = 규칙(S1) 대상 전원 · 처치는 고객별 CATE × CLV × margin_rate − 계획 비용 최대"
                       "(결손은 T3) · S6_ext = S6 의 남은 예산을 규칙 밖 고객에게 S5 방식으로(#274 D-1 · DR-170 E3 · E4)"),
        "budget_krw": budget,
        "s6": s6_breakdown(scores, budget, cost),
        "s6_saved_budget_krw": remaining,
        "s6_ext_added_targets": len(ext),
        "rows": rows,
        "comparability": ("S1 대비 차이(expected_net_vs_S1_krw)는 고객마다 짝지어 두 배정 모두 점수 있는 고객만 비교했다 — "
                          "행마다 vs_S1_n_compared · vs_S1_n_excluded_unscored. 행의 expected_net_krw 끼리 빼지 않는다"
                          if excluded else None),
        "limitation": WHAT_IF_LIMITATION + ". 시뮬레이터 분기 실측은 #305",
    }


def budget_rationale(c_rule_krw: float | None, n_rule_targets: int | None,
                     period_revenue_krw: float | None) -> dict[str, Any]:
    """DR-170 E6 · SRS OPT-007 · PRD §52.1 — 기준 예산을 현업 비교 단위 둘로 함께 표시한다.

    ``period_revenue_krw`` = 무처치(S0) 분기의 같은 42일 측정 매출. 예산을 정할 때는 알 수 없는 값이라 **표시용**이다.
    계산할 수 없으면 None 과 사유 — 0 으로 채우지 않는다.
    """
    def ratio(num: float | None, den: float | None, what: str) -> tuple[float | None, str | None]:
        if num is None:
            return None, "C_rule 없음"
        if den is None:
            return None, f"{what} 없음"
        if float(den) <= 0:
            return None, f"{what} ≤ 0"
        return float(num) / float(den), None

    per_target, per_target_reason = ratio(c_rule_krw, n_rule_targets, "S1 규칙 대상 수")
    share, share_reason = ratio(c_rule_krw, period_revenue_krw, "같은 기간 매출(S0 분기 측정 매출)")
    return {
        "c_rule_krw": c_rule_krw,
        "n_rule_targets": n_rule_targets,
        "per_target_krw": per_target, "per_target_reason": per_target_reason,
        "period_revenue_krw": period_revenue_krw,
        "revenue_share": share, "revenue_share_reason": share_reason,
        "definition": ("고객당 단가 = C_rule ÷ S1 규칙 대상 수 · 매출 대비 비율 = C_rule ÷ 무처치(S0) 분기의 같은 42일 측정 매출"
                       "(전체 고객). 매출은 예산을 정한 뒤에야 아는 값이라 표시용 비교 지표다(DR-170 E6)"),
    }
