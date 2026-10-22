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
