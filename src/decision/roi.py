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
"""

from __future__ import annotations

import math
from typing import Any, Mapping

ROW_KEYS = ("id", "name", "n_targeted", "treatment_mix", "revenue", "marketing_cost",
            "contribution_profit", "churn_rate")
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


def summarize_strategy(metrics: Mapping[str, Any], baseline_metrics: Mapping[str, Any] | None,
                       ai_investment_cost: float | None = None) -> dict[str, Any]:
    """전략 요약 행 1개. ``baseline_metrics`` 가 None 이면 증분 지표는 전부 계산 불가."""
    row: dict[str, Any] = {k: metrics.get(k) for k in ROW_KEYS}
    base = baseline_metrics or {}
    inc = _sub(metrics.get("contribution_profit"), base.get("contribution_profit")) if baseline_metrics else None
    dcost = _sub(metrics.get("marketing_cost"), base.get("marketing_cost")) if baseline_metrics else None
    row["incremental_profit_vs_S1"] = inc
    row["incremental_marketing_cost"] = dcost
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
    row["flags"] = interpretation_flags(metrics, base) if baseline_metrics else []
    return row


def interpretation_flags(metrics: Mapping[str, Any], base: Mapping[str, Any]) -> list[str]:
    """PRD §65 · ROI-006 — 좋은 결과로 보지 않는 조합."""
    flags = []
    drev = _sub(metrics.get("revenue"), base.get("revenue"))
    dprof = _sub(metrics.get("contribution_profit"), base.get("contribution_profit"))
    if drev is not None and dprof is not None and drev > 0 and dprof < 0:
        flags.append("revenue_up_profit_down")
    dchurn = _sub(metrics.get("churn_rate"), base.get("churn_rate"))
    c, c0 = _num(metrics.get("marketing_cost")), _num(base.get("marketing_cost"))
    if dchurn is not None and dchurn < 0 and c is not None and c0 is not None and c0 > 0:
        if (c - c0) / c0 >= COST_SURGE_RATIO:
            flags.append("retention_up_cost_surge")
    return flags


def summarize_all(metrics_by_id: Mapping[str, Mapping[str, Any]], baseline_id: str = "S1",
                  ai_investment_cost: float | None = None) -> list[dict[str, Any]]:
    """S0~S5 집계 → 요약 행 목록. 기준선(S1) 행의 증분값은 0 이 아니라 정의상 0 이다."""
    base = metrics_by_id.get(baseline_id)
    rows = []
    for sid in sorted(metrics_by_id):
        m = dict(metrics_by_id[sid])
        m.setdefault("id", sid)
        rows.append(summarize_strategy(m, base, ai_investment_cost if sid not in ("S0", baseline_id) else None))
    return rows
