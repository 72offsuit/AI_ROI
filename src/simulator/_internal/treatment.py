"""처치 반응(S6) — 반응 유형 · 효과 창 · 반사실(Potential Outcome) 실행.

의미(`docs/simulator_api.md` 의 `apply_treatment`):
- 배정 시각(그때의 세계 시각)에 노출 이벤트가 난다. 효과는 그 시각부터 `window_days` 일 지속한다.
- 다음 배정이 덮어쓴다. `T0` 배정은 앞선 처치의 효과를 끝낸다.

반응 유형은 고객마다 Trait 에서 정해지는 숨은 값이다.
- Negative(Sleeping Dog): 마케팅 피로 Trait 으로 정한다. 처치 종류와 무관한 고객 단위 성향이다.
- Positive: Negative 가 아닐 때 처치별 민감도 Trait(config 의 arms.*.sensitivity)과 마케팅 반응성 Trait 의 평균으로 정한다.
- Neutral: 그 밖. 쿠폰 할인·무료배송 같은 기계적 효과는 유형과 무관하게 모두에게 적용된다.

여기서 만든 값은 측정 계층을 지나지 않는다. 반사실 결과는 숨은 영역(`ground_truth`)에만 쓴다.
"""

from __future__ import annotations

import json

from src.simulator._internal import clock, params, rng

POSITIVE = "positive"
NEUTRAL = "neutral"
NEGATIVE = "negative"
ARMS = ("T0", "T1", "T2", "T3", "T4")
_TWO_64 = 1 << 64
_RESPONSE_DAY = -2  # 생성(-1)·행동(≥0) 스트림과 겹치지 않는 열쇠


def response_type(seed: int, customer_id: str, traits: dict[str, int], tid: str, p: params.Params) -> str:
    """`traits` 는 `world.behavior_traits` 의 별칭 묶음이다."""
    fatigue = traits["fatigue"] * p.negative_scale_pct // 100
    if rng.Stream(seed, customer_id, "response", _RESPONSE_DAY).next_u64() < fatigue * _TWO_64 // params.PPM:
        return NEGATIVE
    sensitivity = (traits[tid] + traits["responsiveness"]) // 2
    chance = sensitivity * p.positive_scale_pct // 100
    if rng.Stream(seed, customer_id, "response:" + tid, _RESPONSE_DAY).next_u64() < chance * _TWO_64 // params.PPM:
        return POSITIVE
    return NEUTRAL


def _active(window, customer: dict[str, object], at_ms: int) -> str | None:
    assignments = customer["assignments"]
    if not assignments:
        return None
    assigned_at, tid = assignments[-1]
    if tid == "T0" or not assigned_at <= at_ms < assigned_at + window.params.window_days * clock.DAY_MS:
        return None
    return tid


def effect(window, customer: dict[str, object], at_ms: int) -> tuple[params.Arm | None, str | None]:
    tid = _active(window, customer, at_ms)
    if tid is None:
        return None, None
    key = (customer["customer_id"], tid)
    found = window.responses.get(key)
    if found is None:
        found = window.responses[key] = response_type(
            window.seed, customer["customer_id"], window.traits(customer), tid, window.params
        )
    return window.params.arms[tid], found


def live_promo(window, customer: dict[str, object], at_ms: int) -> dict[str, object] | None:
    promo = customer["promo"]
    if promo is None or _active(window, customer, at_ms) != promo["treatment_id"]:
        return None
    if customer["assignments"][-1][0] != promo["at_ms"]:
        return None
    return promo


# ── 반사실 실행 ──────────────────────────────────────────────────────────────


def outcome(orders: list[dict[str, object]], tid: str, p: params.Params) -> dict[str, int]:
    revenue = cogs = subsidy = discount = 0
    for order in orders:
        revenue += int(order["order_amount"])
        subsidy += int(order["shipping_fee"]) - int(order["shipping_charged"])
        discount += int(order["discount"])
        for item in order["items"]:
            cogs += int(item["unit_cost"]) * int(item["quantity"])
    # 순매출 기준(DR-101): 쿠폰 할인은 이미 order_amount 에서 빠졌으므로 기여이익에서 다시 빼지 않는다.
    contribution = revenue - cogs - subsidy
    marketing = discount + (p.message_cost_krw if tid != "T0" else 0)
    return {
        "purchased": 1 if orders else 0,
        "orders": len(orders),
        "revenue": revenue,
        "cogs": cogs,
        "shipping_subsidy": subsidy,
        "discount": discount,
        "coupon_used": 1 if discount else 0,
        "contribution_profit": contribution,
        "marketing_cost": marketing,
        "net_profit": contribution - marketing,
    }


def potential_outcomes(world: dict[str, object], customer_ids: list[str]) -> list[dict[str, object]]:
    """고객마다 T0~T4 를 같은 난수 열쇠(CRN)로 `window_days` 일 돌린 결과. `world` 는 바꾸지 않는다.

    `world` 는 배정을 적기 **전** 상태여야 한다. 각 팔은 지금 시각에 그 처치를 배정한 것과 같다.
    """
    from src.simulator._internal import engine  # 순환 import 회피
    from src.simulator._internal.world import behavior_traits, customer_index

    p = params.active()
    now = world["now_ms"]
    end = now + p.window_days * clock.DAY_MS
    pending: dict[str, list] = {}
    for item in world["queue"]:
        pending.setdefault(item[1], []).append(tuple(item))
    rows = []
    for cid in customer_ids:
        original = world["customers"][customer_index(cid)]
        frozen = json.dumps(original)
        arms: dict[str, dict[str, int]] = {}
        types: dict[str, str] = {}
        for tid in ARMS:
            copy = json.loads(frozen)
            copy["assignments"].append([now, tid])
            queue = list(pending.get(cid, ()))
            queue.append((now, cid, copy["next_seq"], "treat"))
            copy["next_seq"] += 1
            orders = engine.simulate_customer(world, copy, queue, end)
            arms[tid] = outcome(orders, tid, p)
            if tid != "T0":
                types[tid] = response_type(world["seed"], cid, behavior_traits(original), tid, p)
        base = arms["T0"]
        rows.append({
            "customer_id": cid,
            "at": clock.timestamp(now),
            "window_days": p.window_days,
            "response_type": types,
            "outcomes": arms,
            "tau_purchase": {t: arms[t]["purchased"] - base["purchased"] for t in ARMS[1:]},
            "tau_net_profit": {t: arms[t]["net_profit"] - base["net_profit"] for t in ARMS[1:]},
        })
    return rows
