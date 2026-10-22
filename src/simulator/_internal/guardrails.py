"""S7-lite 가드레일 검사 — 생성 이탈률 · 처치별 ATE · 쿠폰 사용률 · Sleeping Dog 비율.

봉인(GATE 1)은 하지 않는다. `config/gate1_lock.yaml` 과 정본 4종을 읽지도 쓰지도 않는다.
기준은 AI 성능이 아니라 SRS SIM-005(이탈률 15~25%)와 처치 강도 가드레일이다(src/simulator/AGENTS.md).

절차: 세계를 진행한 시각 T0 에서
- 활성 고객 = [T0 − active_lookback_days, T0) 에 구매가 있는 고객
- 이탈률 = 활성 고객 중 T0(무처치) 팔에서 [T0, T0 + 42일) 무구매 비율
- ATE_k = 활성 고객 평균 [창 내 구매 여부 | T_k] − [… | T0] (CRN 반사실 실행)
- 쿠폰 사용률 = 쿠폰 처치(T2·T3) 팔에서 노출 고객 중 창 안에 쿠폰을 쓴 고객 비율
- Sleeping Dog = 반응 유형 Negative 비율(전 고객 · 처치 종류와 무관한 고객 성향)
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


def evaluate(
    world: dict[str, object], orders: list[dict[str, object]], sample: int | None
) -> tuple[dict[str, object], list[dict[str, object]]]:
    p = params.active()
    now = world["now_ms"]
    lower = clock.timestamp(now - p.active_lookback_days * clock.DAY_MS)
    upper = clock.timestamp(now)
    recent = sorted({str(o["customer_id"]) for o in orders if lower <= str(o["ordered_at"]) < upper})
    active = recent
    if sample is not None and 0 < sample < len(recent):
        active = [recent[i * len(recent) // sample] for i in range(sample)]
    rows = treatment.potential_outcomes(world, active)
    n = len(rows)
    result: dict[str, object] = {
        "at": upper,
        "active_customers": len(recent),
        "evaluated_customers": n,
        "churn_rate_bp": _bp(_count(1 - r["outcomes"]["T0"]["purchased"] for r in rows), n),
        "ate_bp": {t: _bp(_count(r["tau_purchase"][t] for r in rows), n) for t in ARMS[1:]},
        "ate_net_profit_krw": {
            t: (_count(r["tau_net_profit"][t] for r in rows) // n if n else None) for t in ARMS[1:]
        },
        "coupon_use_bp": {
            t: _bp(_count(r["outcomes"][t]["coupon_used"] for r in rows), n)
            for t in ARMS[1:] if p.arms[t].coupon_discount_krw
        },
        "response_mix_bp": {
            t: {kind: _bp(_count(1 for r in rows if r["response_type"][t] == kind), n)
                for kind in (treatment.POSITIVE, treatment.NEUTRAL, treatment.NEGATIVE)}
            for t in ARMS[1:]
        },
    }
    population = world["customers"]
    negative = _count(
        1 for c in population
        if treatment.response_type(world["seed"], c["customer_id"], behavior_traits(c), "T1", p)
        == treatment.NEGATIVE
    )
    result["sleeping_dog_bp"] = _bp(negative, len(population))
    result["checks"] = _checks(result, p)
    return result, rows


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
    add("sleeping_dog", result["sleeping_dog_bp"], "sleeping_dog_bp")
    return checks


def _percent(bp: int | None) -> str:
    if bp is None:
        return "—"
    sign = "-" if bp < 0 else ""
    whole, frac = divmod(abs(bp), 100)
    return f"{sign}{whole}.{frac:02d}%"


def table(result: dict[str, object]) -> str:
    lines = [
        f"가드레일 (T0 = {result['at']}, 활성 {result['active_customers']}명 중 "
        f"{result['evaluated_customers']}명 평가)",
        f"{'검사':<16}{'값':>10}{'범위':>16}  판정",
    ]
    for check in result["checks"]:
        lo, hi = check["range_bp"]
        bounds = "—" if lo is None else f"{_percent(lo)}~{_percent(hi)}"
        lines.append(f"{check['name']:<16}{_percent(check['value_bp']):>10}{bounds:>16}  {check['status']}")
    return "\n".join(lines)


def write(root: Path, result: dict[str, object], rows: list[dict[str, object]], name: str) -> Path:
    storage.write_ground_truth(root, f"{name}-potential-outcomes", rows)
    path = root.joinpath(f"{name}.json")
    storage.write_json(path, result)
    return path
