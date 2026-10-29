"""S7-lite 가드레일 검사 — 생성 이탈률 · 처치별 ATE · 쿠폰 사용률 · Sleeping Dog 비율.

봉인(GATE 1)은 하지 않는다. `config/gate1_lock.yaml` 과 정본 4종을 읽지도 쓰지도 않는다.
기준은 AI 성능이 아니라 SRS SIM-005(이탈률 15~25%)와 처치 강도 가드레일이다(src/simulator/AGENTS.md).

절차: 세계를 진행한 시각 T0 에서 모집단 두 개를 모두 계산하고, 지표마다 정본 모집단 하나로 판정한다
(docs/decisions/DR-194-population.md, 2026-10-28 사용자 결정 — 역할별 분리).
- ① 직전 active_lookback_days(42)일 구매 고객 — **이탈률(SIM-005)을 판정한다.** T0 와 무관하게 일정한
  이탈 기제의 성질이다(#193)
- ② 정본 eligible(docs/data_spec.html §4.1): 가입 60일 이상 ∧ T0 이전 구매 1건 이상 ∧ 마지막 구매가 T0 보다
  14일 이상 전 — **처치 지표(ATE · 쿠폰 · 4분면)를 판정한다.** RCT 배정 모집단과 같다(#234 가 결정 계층에 적용)
- 결과 JSON 최상위의 값이 판정값이다(이탈률은 ①, 처치 지표는 ②). 두 모집단의 전체 값은 `active42` ·
  `eligible_spec41` 블록에, 판정하지 않는 쪽 검사는 `active42_*` · `spec41_*` 이름에 `role: 참고` 로 싣는다
- 이탈률 = 모집단 중 T0(무처치) 팔에서 [T0, T0 + 42일) 무구매 비율
- ATE_k = 모집단 평균 [창 내 구매 여부 | T_k] − [… | T0] (CRN 반사실 실행)
- 쿠폰 사용률(판정) = 쿠폰 처치(T2·T3) 팔의 처치군 **전체** 중 유효기간 안에 쿠폰을 쓴 고객 비율. 띠 5~20%
  (2026-10-22 사용자 확정, docs/research/data_grounding.md §3-1 — PRD 원문 25~40% 폐기). 참고값으로
  "처치군 중 창 안 구매자" 분모도 함께 싣는다(판정하지 않는다)
- 잠재결과 4분면(arm 마다, 창 내 구매 여부 Y): Persuadable = Y(T_k)=1·Y(T0)=0, Sleeping Dog = 0·1,
  Sure Thing = 1·1, Lost Cause = 0·0. 판정 — Sleeping Dog 8~15%, Persuadable 11~21%(2026-10-22 사용자 확정,
  §3-2 — PRD 원문 20~30% 폐기), 항등식 P − D = ATE(±0.5%p, ATE 는 τ 평균으로 따로 계산)
- 반응 성향(Trait 유형)은 4분면과 정의가 달라 판정에 쓰지 않는다 — 참고값이다
"""

from __future__ import annotations

import json
from pathlib import Path

from src.simulator._internal import clock, params, storage, treatment
from src.simulator._internal.world import behavior_traits

ARMS = treatment.ARMS


def _bp(numerator: int, denominator: int) -> int | None:
    if denominator <= 0:
        return None
    return (numerator * 10_000 + denominator // 2) // denominator


def _count(values) -> int:
    total = 0
    for value in values:
        total += value
    return total


def _pick(ids: list[str], sample: int | None) -> list[str]:
    if sample is not None and 0 < sample < len(ids):
        return [ids[i * len(ids) // sample] for i in range(sample)]
    return ids


def _block(rows: list[dict[str, object]], p: params.Params) -> dict[str, object]:
    n = len(rows)
    return {
        "evaluated_customers": n,
        "churn_rate_bp": _bp(_count(1 - r["outcomes"]["T0"]["purchased"] for r in rows), n),
        "ate_bp": {t: _bp(_count(r["tau_purchase"][t] for r in rows), n) for t in ARMS[1:]},
        "ate_net_profit_krw": {
            t: (_count(r["tau_net_profit"][t] for r in rows) // n if n else None) for t in ARMS[1:]
        },
        "coupon_use_definition": "쿠폰 처치군(T2·T3) 전체 중 유효기간 안 사용 — 분모 = 평가 고객 전원",
        "coupon_use_bp": {
            t: _bp(_count(r["outcomes"][t]["coupon_used"] for r in rows), n)
            for t in ARMS[1:] if p.arms[t].coupon_discount_krw
        },
        "coupon_use_among_buyers_bp_reference": {
            t: _bp(
                _count(r["outcomes"][t]["coupon_used"] for r in rows),
                _count(r["outcomes"][t]["purchased"] for r in rows),
            )
            for t in ARMS[1:] if p.arms[t].coupon_discount_krw
        },
        "potential_outcome_quadrants": {t: _quadrants(rows, t) for t in ARMS[1:]},
        "response_mix_bp": {
            t: {kind: _bp(_count(1 for r in rows if r["response_type"][t] == kind), n)
                for kind in (treatment.POSITIVE, treatment.NEUTRAL, treatment.NEGATIVE)}
            for t in ARMS[1:]
        },
    }


def evaluate(
    world: dict[str, object], orders: list[dict[str, object]], sample: int | None
) -> tuple[dict[str, object], list[dict[str, object]]]:
    """이탈률은 ① 직전 42일 구매 고객, 처치 지표는 ② §4.1 eligible 로 판정한다(DR-194, 모듈 docstring).

    돌려주는 반사실 행은 모집단별 `{"active42": …, "eligible_spec41": …}` 이다.
    """
    p = params.active()
    now = world["now_ms"]
    lower = clock.timestamp(now - p.active_lookback_days * clock.DAY_MS)
    upper = clock.timestamp(now)
    active = sorted({str(o["customer_id"]) for o in orders if lower <= str(o["ordered_at"]) < upper})
    eligible = sorted(
        c["customer_id"] for c in world["customers"]
        if c["signup_ms"] <= now - 60 * clock.DAY_MS
        and c["rfm"]["last_purchase_ms"] is not None
        and now - c["rfm"]["last_purchase_ms"] >= 14 * clock.DAY_MS
    )
    rows = treatment.potential_outcomes(world, _pick(active, sample))
    spec_rows = treatment.potential_outcomes(world, _pick(eligible, sample))
    churn_block, treatment_block = _block(rows, p), _block(spec_rows, p)
    result: dict[str, object] = {
        "at": upper,
        "population": {
            "churn": f"① 직전 {p.active_lookback_days}일 구매 고객",
            "treatment": "② data_spec §4.1 eligible",
            "decision": "docs/decisions/DR-194-population.md",
        },
        "active_customers": len(active),
        "eligible_customers": len(eligible),
        # 판정값 — 이탈률은 ①, 처치 지표는 ②.
        "churn_rate_bp": churn_block["churn_rate_bp"],
        **{key: value for key, value in treatment_block.items() if key not in _CHURN_KEYS},
        "active42": {"customers": len(active), **churn_block},
        "eligible_spec41": {"customers": len(eligible), **treatment_block},
    }
    # 참고값: Trait 반응 성향 Negative 비율(전 고객). 4분면 Sleeping Dog 과 정의가 달라 판정하지 않는다.
    population = world["customers"]
    negative = _count(
        1 for c in population
        if treatment.response_type(world["seed"], c["customer_id"], behavior_traits(c), "T1", p)
        == treatment.NEGATIVE
    )
    result["negative_response_trait_bp_reference"] = _bp(negative, len(population))
    judged_churn, active_treatment = _split(_checks(churn_block, p))
    spec_churn, judged_treatment = _split(_checks(treatment_block, p))
    reference = [{**c, "name": "active42_" + c["name"], "role": "참고"} for c in active_treatment] + [
        {**c, "name": "spec41_" + c["name"], "role": "참고"} for c in spec_churn
    ]
    result["checks"] = [{**c, "role": "판정"} for c in judged_churn + judged_treatment] + reference
    return result, {"active42": rows, "eligible_spec41": spec_rows}


# `_block` 의 키 중 처치 지표가 아닌 것. 나머지는 모두 처치 지표라 ② 모집단 값이 최상위에 올라간다(DR-194) —
# `_block` 에 처치 지표가 늘어도 손으로 목록을 고칠 필요가 없다(#245 리뷰).
_CHURN_KEYS = frozenset({"evaluated_customers", "churn_rate_bp"})


def _split(checks: list[dict[str, object]]) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    """(이탈률 검사, 처치 지표 검사)."""
    return [c for c in checks if c["name"] == "churn_rate"], [c for c in checks if c["name"] != "churn_rate"]


def _quadrants(rows: list[dict[str, object]], tid: str) -> dict[str, object]:
    """창 내 구매 여부의 잠재결과 4분면(만분율). ATE 는 τ 평균으로 따로 세어 항등식 P − D = ATE 를 검사한다."""
    n = len(rows)
    cells = {"persuadable": 0, "sleeping_dog": 0, "sure_thing": 0, "lost_cause": 0}
    for row in rows:
        treated = row["outcomes"][tid]["purchased"]
        control = row["outcomes"]["T0"]["purchased"]
        key = (
            "sure_thing" if treated and control else "persuadable" if treated
            else "sleeping_dog" if control else "lost_cause"
        )
        cells[key] += 1
    ate_count = _count(row["tau_purchase"][tid] for row in rows)
    gap_count = cells["persuadable"] - cells["sleeping_dog"] - ate_count
    found: dict[str, object] = {f"{name}_bp": _bp(count, n) for name, count in cells.items()}
    found["ate_bp"] = _bp(ate_count, n)
    gap_bp = _bp(gap_count, n)
    found["identity_gap_bp"] = gap_bp
    # 부동소수를 쓰지 않으므로 %p 값은 정확한 십진 문자열로 싣는다(만분율 100 = 1%p).
    found["identity_gap_pp"] = None if gap_bp is None else _percent(gap_bp).rstrip("%")
    found["n"] = n
    return found


def _checks(result: dict[str, object], p: params.Params) -> list[dict[str, object]]:
    ranges = p.guardrail_ranges
    checks: list[dict[str, object]] = []

    def add(name: str, value: int | None, key: str) -> None:
        lo, hi = ranges.get(key, (None, None))
        if value is None or lo is None:
            status = "not_run"
        else:
            status = "pass" if lo <= value <= hi else "fail"
        checks.append({"name": name, "value_bp": value, "range_bp": [lo, hi], "status": status})

    add("churn_rate", result["churn_rate_bp"], "churn_rate_bp")
    for t, value in result["ate_bp"].items():
        add(f"ate_{t}", value, "ate_bp")
    for t, value in result["coupon_use_bp"].items():
        add(f"coupon_use_{t}", value, "coupon_use_bp")
    for t, quadrant in result["potential_outcome_quadrants"].items():
        add(f"sleeping_dog_{t}", quadrant["sleeping_dog_bp"], "sleeping_dog_bp")
        add(f"persuadable_{t}", quadrant["persuadable_bp"], "persuadable_bp")
        gap = quadrant["identity_gap_bp"]
        checks.append({
            "name": f"identity_{t}", "value_bp": gap, "range_bp": [-50, 50],
            "status": "not_run" if gap is None else ("pass" if -50 <= gap <= 50 else "fail"),
        })
    return checks


def _percent(bp: int | None) -> str:
    if bp is None:
        return "—"
    sign = "-" if bp < 0 else ""
    whole, frac = divmod(abs(bp), 100)
    return f"{sign}{whole}.{frac:02d}%"


def table(result: dict[str, object]) -> str:
    population = result["population"]
    lines = [
        f"가드레일 (T0 = {result['at']}) — 이탈률: {population['churn']} {result['active_customers']}명 중 "
        f"{result['active42']['evaluated_customers']}명 · 처치 지표: {population['treatment']} "
        f"{result['eligible_customers']}명 중 {result['eligible_spec41']['evaluated_customers']}명",
        f"{'검사':<24}{'값':>10}{'범위':>16}  결과  구분",
    ]
    for check in result["checks"]:
        lo, hi = check["range_bp"]
        bounds = "—" if lo is None else f"{_percent(lo)}~{_percent(hi)}"
        lines.append(
            f"{check['name']:<24}{_percent(check['value_bp']):>10}{bounds:>16}  {check['status']}  {check['role']}"
        )
    return "\n".join(lines)


def write(root: Path, result: dict[str, object], rows: dict[str, list[dict[str, object]]], name: str) -> Path:
    for population, found in rows.items():
        storage.write_ground_truth(root, f"{name}-potential-outcomes-{population}", found)
    path = root.joinpath(f"{name}.json")
    storage.write_json(path, result)
    return path
