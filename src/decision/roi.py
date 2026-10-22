"""전략 요약 · Incremental Profit · ROI — 이슈 #145 (PRD §62~65 · SRS ROI-001~006).

표준 라이브러리만 쓴다. 입력 ``metrics`` 는 전략 1개의 집계(측정 계층이 계산한 값)이고
``baseline_metrics`` 는 **S1 Rule-based** 의 같은 집계다.

정의:
  incremental_profit_vs_S1  = contribution_profit − contribution_profit_S1     (ROI-003 · PRD §63)
  incremental_marketing_cost = marketing_cost − marketing_cost_S1
  roi (증분 마케팅 ROI)      = incremental_profit_vs_S1 / incremental_marketing_cost
                               분모 ≤ 0 이면 **계산 불가(None)** — 기준선보다 덜 쓰고 더 벌면
                               비율이 음수/무한대가 되어 해석이 뒤집히기 때문이다.
  ai_net_incremental_value   = incremental_profit_vs_S1 − ai_investment_cost   (ROI-004 · PRD §63)
  ai_roi                     = ai_net_incremental_value / ai_investment_cost   (ROI-005 · PRD §64)
                               ai_investment_cost 가 주어지지 않으면 계산 불가.
값이 하나라도 없으면 파생값은 None 이다 — 0 으로 채우지 않는다.

입력 키 — 오케스트레이션 집계(``sim_*``)와 단순 형식을 둘 다 받는다. 값마다 아래 후보를
순서대로 보되, **증분 계산에는 전략과 기준선 양쪽에 다 있는 첫 키**를 쓴다(기준이 섞이면
차이가 의미를 잃는다). 어떤 키를 썼는지 ``basis`` 에 남긴다.

  매출        sim_revenue → revenue → revenue_krw
  마케팅비    sim_marketing_cost → marketing_cost → planned_treatment_cost_krw(계획치)
  기여이익    sim_contribution_profit → contribution_profit
  이탈률      sim_churn_rate → churn_rate

★ 기여이익이 어느 한쪽에라도 없으면 **대체 계산** ``Δ(매출 − 마케팅비)`` 을 쓰고
  ``incremental_profit_basis = "fallback:revenue_minus_marketing_cost"`` 와 플래그
  ``PROFIT_FALLBACK_REVENUE_BASED`` 를 붙인다. 이 값은 **COGS 를 빼지 않았으므로 기여이익
  증분을 과대평가**하고, 순매출(할인 후, DR-101)에서 쿠폰비를 다시 빼므로 쿠폰 할인을
  이중 차감한다. 기여이익의 대용이 아니라 "기여이익이 없을 때의 방향 확인용" 이다.
"""

from __future__ import annotations

import math
from typing import Any, Mapping

from .strategies import STRATEGY_NAMES

ROW_KEYS = ("id", "name", "n_targeted", "treatment_mix", "revenue", "marketing_cost",
            "contribution_profit", "churn_rate")
CANDIDATES: dict[str, tuple[str, ...]] = {
    "revenue": ("sim_revenue", "revenue", "revenue_krw"),
    "marketing_cost": ("sim_marketing_cost", "marketing_cost", "planned_treatment_cost_krw"),
    "contribution_profit": ("sim_contribution_profit", "contribution_profit"),
    "churn_rate": ("sim_churn_rate", "churn_rate"),
}
#: 그대로 옮겨 싣는 부가 키(있으면).
PASSTHROUGH = ("n_population", "n_with_outcome", "n_outcome_missing", "retention_rate",
               "revenue_per_customer_krw", "purchases", "planned_treatment_cost_krw")
#: PRD §65 '마케팅 비용 폭증' 판정 — 기준선 대비 비용 증가율이 이 값 이상이면 경고.
#: 근거 문헌 없음: 스프린트 가정(DR-145). 경고일 뿐 결과를 바꾸지 않는다.
COST_SURGE_RATIO = 1.0


def _num(v: Any) -> float | None:
    if v is None:
        return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return None if math.isnan(f) else f


def _sub(a: Any, b: Any) -> float | None:
    a, b = _num(a), _num(b)
    return None if a is None or b is None else a - b


def _first(m: Mapping[str, Any], keys: tuple[str, ...]) -> tuple[float | None, str | None]:
    for k in keys:
        v = _num(m.get(k))
        if v is not None:
            return v, k
    return None, None


def _paired(m: Mapping[str, Any], b: Mapping[str, Any], keys: tuple[str, ...]) -> tuple[float | None, str | None]:
    """양쪽에 다 있는 첫 키로 차이를 낸다."""
    for k in keys:
        a, c = _num(m.get(k)), _num(b.get(k))
        if a is not None and c is not None:
            return a - c, k
    return None, None


def summarize_strategy(metrics: Mapping[str, Any], baseline_metrics: Mapping[str, Any] | None,
                       ai_investment_cost: float | None = None) -> dict[str, Any]:
    """전략 요약 행 1개. ``baseline_metrics`` 가 None 이면 증분 지표는 전부 계산 불가."""
    row: dict[str, Any] = {k: metrics.get(k) for k in ROW_KEYS}
    if row["id"] is None:
        row["id"] = metrics.get("strategy_id")
    if row["name"] is None and row["id"] in STRATEGY_NAMES:
        row["name"] = STRATEGY_NAMES[row["id"]]
    basis: dict[str, str | None] = {}
    for field, keys in CANDIDATES.items():
        row[field], basis[field] = _first(metrics, keys)
    for k in PASSTHROUGH:
        if k in metrics:
            row[k] = metrics[k]
    flags: list[str] = []
    base = baseline_metrics or {}
    inc = dcost = None
    if baseline_metrics:
        inc, pk = _paired(metrics, base, CANDIDATES["contribution_profit"])
        dcost, ck = _paired(metrics, base, CANDIDATES["marketing_cost"])
        basis["incremental_marketing_cost"] = ck
        if inc is not None:
            basis["incremental_profit"] = pk
        else:
            drev, rk = _paired(metrics, base, CANDIDATES["revenue"])
            if drev is not None and dcost is not None:
                inc = drev - dcost
                basis["incremental_profit"] = f"fallback:revenue_minus_marketing_cost({rk}−{ck})"
                flags.append("PROFIT_FALLBACK_REVENUE_BASED")
            else:
                basis["incremental_profit"] = None
        if ck == "planned_treatment_cost_krw":
            flags.append("MARKETING_COST_PLANNED_NOT_REALIZED")
    row["incremental_profit_vs_S1"] = inc
    row["incremental_profit_basis"] = basis.get("incremental_profit")
    row["incremental_marketing_cost"] = dcost
    row["basis"] = basis
    if inc is None or dcost is None:
        row["roi"], row["roi_status"] = None, "계산 불가 — 이익 또는 비용 결손"
    elif dcost <= 0:
        row["roi"], row["roi_status"] = None, "계산 불가 — 추가 마케팅비 ≤ 0"
    else:
        row["roi"], row["roi_status"] = inc / dcost, "ok"
    row["roi_definition"] = "incremental_profit_vs_S1 / (marketing_cost − marketing_cost_S1)"

    aic = _num(ai_investment_cost)
    if inc is None or aic is None or aic <= 0:
        row["ai_net_incremental_value"] = None
        row["ai_roi"] = None
        row["ai_roi_status"] = "계산 불가 — AI 투자비 미지정 또는 증분이익 결손"
    else:
        net = inc - aic
        row["ai_net_incremental_value"] = net
        row["ai_roi"] = net / aic
        row["ai_roi_status"] = "ok"
    row["flags"] = flags + (interpretation_flags(metrics, base) if baseline_metrics else [])
    return row


def interpretation_flags(metrics: Mapping[str, Any], base: Mapping[str, Any]) -> list[str]:
    """PRD §65 · ROI-006 — 좋은 결과로 보지 않는 조합."""
    flags = []
    drev, _ = _paired(metrics, base, CANDIDATES["revenue"])
    dprof, _ = _paired(metrics, base, CANDIDATES["contribution_profit"])
    if drev is not None and dprof is not None and drev > 0 and dprof < 0:
        flags.append("revenue_up_profit_down")
    dchurn, _ = _paired(metrics, base, CANDIDATES["churn_rate"])
    dcost, ck = _paired(metrics, base, CANDIDATES["marketing_cost"])
    c0 = _num(base.get(ck)) if ck else None
    if dchurn is not None and dchurn < 0 and dcost is not None and c0 is not None and c0 > 0:
        if dcost / c0 >= COST_SURGE_RATIO:
            flags.append("retention_up_cost_surge")
    return flags


def summarize_all(metrics_by_id: Mapping[str, Mapping[str, Any]], baseline_id: str = "S1",
                  ai_investment_cost: float | None = None) -> list[dict[str, Any]]:
    """S0~S5 집계 → 요약 행 목록. S1 행의 증분값은 자기 자신과의 차이라 정의상 0 이고,
    그 ROI 는 분모(추가 마케팅비)가 0 이라 계산 불가다. AI 투자비는 AI 전략(S2~S5)에만 붙인다."""
    base = metrics_by_id.get(baseline_id)
    rows = []
    for sid in sorted(metrics_by_id):
        m = dict(metrics_by_id[sid])
        m.setdefault("id", sid)
        rows.append(summarize_strategy(m, base, ai_investment_cost if sid not in ("S0", baseline_id) else None))
    return rows
