"""전략 요약 · Incremental Profit · ROI — 이슈 #145 · #169 (PRD §62~65 · SRS ROI-001~006).

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

입력 키 — 오케스트레이션 집계(``sim_*`` · ``measured_*``)와 단순 형식을 둘 다 받는다. 값마다 아래
후보를 순서대로 보되, **증분 계산에는 전략과 기준선 양쪽에 다 있는 첫 키**를 쓴다(기준이 섞이면
차이가 의미를 잃는다). 어떤 키를 썼는지 ``basis`` 에 남긴다.

  매출        sim_revenue → measured_revenue → revenue → revenue_krw
  마케팅비    sim_marketing_cost → measured_marketing_cost → marketing_cost → planned_treatment_cost_krw(계획치)
  기여이익    sim_contribution_profit → measured_contribution_profit → contribution_profit
  이탈률      sim_churn_rate → churn_rate

``measured_*`` 는 오케스트레이션이 분기마다 측정 계층(``publish.build_kpi_report``)으로 계산한
값이다 — 교환 묶음의 주문 시점 원가로 COGS 를 뺀 실측 기여이익(DR-169).

★ **기여이익이 양쪽에 같은 키로 없으면 정식 증분이익은 계산 불가다** (DR-169 · SRS MEA-003).
  ``incremental_profit_vs_S1`` 은 None, ``incremental_profit_status`` 가 사유(전략 쪽 · 기준선 쪽 ·
  양쪽 결손, 키 불일치)를 말하고 ``CONTRIBUTION_PROFIT_MISSING`` 플래그가 붙는다. ROI · AI ROI 도
  계산 불가다.

  방향 확인용 대체값 ``Δ(매출 − 마케팅비)`` 는 **별도 필드** ``directional_revenue_minus_marketing_vs_S1``
  와 별도 상태 ``directional_status`` 로 낸다(플래그 ``PROFIT_FALLBACK_REVENUE_BASED``). 이 값은
  COGS 를 빼지 않아 기여이익 증분을 과대평가하고, 순매출(할인 후, DR-101)에서 쿠폰비를 다시 빼므로
  쿠폰 할인을 이중 차감한다 — 부호조차 보장하지 않는다(DR-169 소규모 확인 실행). ROI · AI ROI ·
  가드레일에 쓰지 않는다.

★ 가드레일(PRD §65 · ROI-006)은 ``guardrails`` 에 ``status: ok | not_run`` 과 ``triggered`` 로 낸다.
  판정에 필요한 공통 차이가 없으면 ``not_run`` 이다 — "발동 안 함(false)" 과 "판정 못 함" 을 같은
  빈 플래그 목록으로 두지 않는다.
"""

from __future__ import annotations

import math
from typing import Any, Mapping

from .strategies import STRATEGY_NAMES

ROW_KEYS = ("id", "name", "n_targeted", "treatment_mix", "revenue", "marketing_cost",
            "contribution_profit", "churn_rate")
CANDIDATES: dict[str, tuple[str, ...]] = {
    "revenue": ("sim_revenue", "measured_revenue", "revenue", "revenue_krw"),
    "marketing_cost": ("sim_marketing_cost", "measured_marketing_cost", "marketing_cost",
                       "planned_treatment_cost_krw"),
    "contribution_profit": ("sim_contribution_profit", "measured_contribution_profit", "contribution_profit"),
    "churn_rate": ("sim_churn_rate", "churn_rate"),
}
#: 그대로 옮겨 싣는 부가 키(있으면).
PASSTHROUGH = ("n_population", "n_with_outcome", "n_outcome_missing", "retention_rate",
               "revenue_per_customer_krw", "purchases", "planned_treatment_cost_krw")
#: PRD §65 '마케팅 비용 폭증' 판정 — 기준선 대비 비용 증가율이 이 값 이상이면 경고.
#: 근거 문헌 없음: 스프린트 가정(DR-145). 경고일 뿐 결과를 바꾸지 않는다.
COST_SURGE_RATIO = 1.0

OK = "ok"
NOT_RUN = "not_run"
#: 가드레일 판정 불가 플래그 — 판정 못 한 것을 '발동 안 함' 과 구분한다(DR-169).
GUARDRAIL_NOT_RUN_FLAGS = {
    "revenue_up_profit_down": "REVENUE_UP_PROFIT_DOWN_NOT_RUN",
    "retention_up_cost_surge": "RETENTION_UP_COST_SURGE_NOT_RUN",
}


def _num(v: Any) -> float | None:
    if v is None:
        return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return None if math.isnan(f) else f


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


def _present(m: Mapping[str, Any], keys: tuple[str, ...]) -> list[str]:
    return [k for k in keys if _num(m.get(k)) is not None]


def _missing_reason(field: str, m: Mapping[str, Any], b: Mapping[str, Any]) -> str:
    """공통 키가 없을 때 무엇이 없는지 — 전략 쪽 · 기준선 쪽 · 양쪽 결손, 또는 키 불일치."""
    keys = CANDIDATES[field]
    mine, theirs = _present(m, keys), _present(b, keys)
    if not mine and not theirs:
        return f"양쪽 모두 {field} 결손"
    if not mine:
        return f"전략 쪽 {field} 결손 (기준선은 {', '.join(theirs)})"
    if not theirs:
        return f"기준선 쪽 {field} 결손 (전략은 {', '.join(mine)})"
    return (f"{field} 기준 불일치 — 전략 {', '.join(mine)} · 기준선 {', '.join(theirs)} "
            "(같은 키가 없어 차이를 내지 않는다)")


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
    directional = None
    if baseline_metrics:
        inc, pk = _paired(metrics, base, CANDIDATES["contribution_profit"])
        dcost, ck = _paired(metrics, base, CANDIDATES["marketing_cost"])
        basis["incremental_marketing_cost"] = ck
        basis["incremental_profit"] = pk
        if inc is not None:
            profit_reason, profit_status = None, OK
            directional_status = f"{NOT_RUN} — 정식 증분이익({pk})이 계산돼 대체값을 만들지 않았다"
            directional_basis = None
        else:
            profit_reason = _missing_reason("contribution_profit", metrics, base)
            profit_status = f"계산 불가 — {profit_reason}"
            flags.append("CONTRIBUTION_PROFIT_MISSING")
            drev, rk = _paired(metrics, base, CANDIDATES["revenue"])
            if drev is not None and dcost is not None:
                directional = drev - dcost
                directional_basis = f"Δ{rk} − Δ{ck}"
                directional_status = ("방향 확인용 — 증분이익 아님. COGS 미차감(과대평가) · 쿠폰 할인 이중 차감, "
                                      "부호도 보장하지 않는다 (DR-169)")
                flags.append("PROFIT_FALLBACK_REVENUE_BASED")
            else:
                directional_basis = None
                missing = ("revenue" if drev is None else "marketing_cost")
                directional_status = f"계산 불가 — {_missing_reason(missing, metrics, base)}"
        if ck == "planned_treatment_cost_krw":
            flags.append("MARKETING_COST_PLANNED_NOT_REALIZED")
        cost_reason = None if dcost is not None else _missing_reason("marketing_cost", metrics, base)
    else:
        basis["incremental_profit"] = None
        profit_reason = "기준선(S1) 집계 없음"
        profit_status = f"계산 불가 — {profit_reason}"
        directional_status, directional_basis = "계산 불가 — 기준선(S1) 집계 없음", None
        cost_reason = "기준선(S1) 집계 없음"
    row["incremental_profit_vs_S1"] = inc
    row["incremental_profit_status"] = profit_status
    row["incremental_profit_basis"] = basis.get("incremental_profit")
    row["directional_revenue_minus_marketing_vs_S1"] = directional
    row["directional_status"] = directional_status
    row["directional_basis"] = directional_basis
    row["incremental_marketing_cost"] = dcost
    row["basis"] = basis
    if inc is None:
        row["roi"], row["roi_status"] = None, f"계산 불가 — 증분이익 없음: {profit_reason}"
    elif dcost is None:
        row["roi"], row["roi_status"] = None, f"계산 불가 — 마케팅비 {cost_reason}"
    elif dcost <= 0:
        row["roi"], row["roi_status"] = None, "계산 불가 — 추가 마케팅비 ≤ 0"
    else:
        row["roi"], row["roi_status"] = inc / dcost, OK
    row["roi_definition"] = "incremental_profit_vs_S1 / (marketing_cost − marketing_cost_S1)"

    aic = _num(ai_investment_cost)
    if inc is None:
        row["ai_net_incremental_value"] = None
        row["ai_roi"] = None
        row["ai_roi_status"] = f"계산 불가 — 증분이익 없음: {profit_reason}"
    elif aic is None or aic <= 0:
        row["ai_net_incremental_value"] = None
        row["ai_roi"] = None
        row["ai_roi_status"] = "계산 불가 — AI 투자비 미지정"
    else:
        net = inc - aic
        row["ai_net_incremental_value"] = net
        row["ai_roi"] = net / aic
        row["ai_roi_status"] = OK
    row["guardrails"] = guardrails(metrics, baseline_metrics)
    for name, verdict in row["guardrails"].items():
        if verdict["status"] != OK:
            flags.append(GUARDRAIL_NOT_RUN_FLAGS[name])
        elif verdict["triggered"]:
            flags.append(name)
    row["flags"] = flags
    return row


def _verdict(triggered: bool | None, basis: dict[str, str | None], reason: str | None) -> dict[str, Any]:
    return {"status": OK if triggered is not None else NOT_RUN, "triggered": triggered,
            "basis": basis, "reason": reason}


def guardrails(metrics: Mapping[str, Any], base: Mapping[str, Any] | None) -> dict[str, dict[str, Any]]:
    """PRD §65 · ROI-006 — 좋은 결과로 보지 않는 조합. 판정할 수 없으면 ``not_run`` 이다.

    ``triggered`` 는 ``True`` (발동) · ``False`` (판정했고 발동 안 함) · ``None`` (판정 못 함) 의 셋이다.
    ``None`` 을 ``False`` 로 바꾸면 확인하지 않은 것이 안전하다고 보고된다.
    """
    if not base:
        reason = "기준선(S1) 집계 없음"
        return {name: _verdict(None, {}, reason) for name in GUARDRAIL_NOT_RUN_FLAGS}
    out: dict[str, dict[str, Any]] = {}

    drev, rk = _paired(metrics, base, CANDIDATES["revenue"])
    dprof, pk = _paired(metrics, base, CANDIDATES["contribution_profit"])
    basis = {"revenue": rk, "contribution_profit": pk}
    if dprof is None:
        out["revenue_up_profit_down"] = _verdict(
            None, basis, f"공통 기여이익 차이 없음 — {_missing_reason('contribution_profit', metrics, base)}")
    elif drev is None:
        out["revenue_up_profit_down"] = _verdict(
            None, basis, f"공통 매출 차이 없음 — {_missing_reason('revenue', metrics, base)}")
    else:
        out["revenue_up_profit_down"] = _verdict(drev > 0 and dprof < 0, basis, None)

    dchurn, hk = _paired(metrics, base, CANDIDATES["churn_rate"])
    dcost, ck = _paired(metrics, base, CANDIDATES["marketing_cost"])
    c0 = _num(base.get(ck)) if ck else None
    basis = {"churn_rate": hk, "marketing_cost": ck}
    if dchurn is None:
        out["retention_up_cost_surge"] = _verdict(
            None, basis, f"공통 이탈률 차이 없음 — {_missing_reason('churn_rate', metrics, base)}")
    elif dcost is None:
        out["retention_up_cost_surge"] = _verdict(
            None, basis, f"공통 마케팅비 차이 없음 — {_missing_reason('marketing_cost', metrics, base)}")
    elif c0 is None or c0 <= 0:
        out["retention_up_cost_surge"] = _verdict(
            None, basis, "기준선 마케팅비가 0 이하라 증가율을 정의할 수 없다")
    else:
        out["retention_up_cost_surge"] = _verdict(dchurn < 0 and dcost / c0 >= COST_SURGE_RATIO, basis, None)
    return out


def interpretation_flags(metrics: Mapping[str, Any], base: Mapping[str, Any]) -> list[str]:
    """PRD §65 · ROI-006 — 발동한 가드레일 이름만. 판정 불가는 ``guardrails()`` 의 ``not_run`` 을 본다."""
    return [name for name, v in guardrails(metrics, base).items() if v["triggered"]]


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
