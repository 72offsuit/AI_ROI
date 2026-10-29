"""처치 반응(S6) — 반응 유형 · 효과 창 · 반사실(Potential Outcome) 실행.

의미(`docs/simulator_api.md` 의 `apply_treatment`):
- 배정 시각(그때의 세계 시각)에 노출 이벤트가 난다. 효과는 그 시각부터 `window_days` 일 지속한다.
- 다음 배정이 덮어쓴다. `T0` 배정은 앞선 처치의 효과를 끝낸다.

반응 유형은 고객 × 처치 × 앞선 노출 수(`prior_exposures`)에서 정해지는 숨은 값이다.
- Negative(Sleeping Dog): 마케팅 피로 Trait 으로 정한다. 처치 종류와 무관한 고객 단위 성향이다.
- Positive: Negative 가 아닐 때 처치별 민감도 Trait(config 의 arms.*.sensitivity)과 마케팅 반응성 Trait 의 평균으로 정한다.
- Neutral: 그 밖. 쿠폰 할인·무료배송 같은 기계적 효과는 유형과 무관하게 모두에게 적용된다.
- 반복 노출(#183 ④, config `treatment.repeat_exposure`): 노출이 쌓일수록 Positive 문턱은 낮아지고 Negative 문턱은
  피로 Trait 비례로 높아진다. 난수는 노출 수와 무관한 고정 열쇠라 한 고객의 유형은 노출 수에 단조다
  (Positive → Neutral → Negative 쪽으로만 옮겨 간다). 앞선 노출이 없으면(n = 0) 반복 노출 계수를 읽지 않는다.

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


def prior_exposures(assignments: list[list]) -> int:
    """마지막 배정 직전까지 고객이 실제로 받은 처치 노출 수 — 반복 노출 감쇠의 n 을 정하는 유일한 규칙.

    마지막 배정 시각보다 이른 배정 중 `T0` 이 아닌 것을 센다. 같은 시각에 여러 번 적힌 배정은 마지막 것만
    노출되므로(`engine._treat`) 시각마다 하나로 센다. 배정 이력만 읽으므로 상태에 새 키가 필요 없다.
    노출 뒤 경과 시간으로 줄지 않는다(누적만 한다) — 시간 회복은 근거가 없어 두지 않았다.
    """
    if not assignments:
        return 0
    latest: dict[int, str] = {}
    for at_ms, tid in assignments:
        latest[at_ms] = tid
    current = assignments[-1][0]
    return len([at_ms for at_ms, tid in latest.items() if at_ms < current and tid != "T0"])


def negative_ppm(fatigue: int, exposures: int, p: params.Params) -> int:
    """Negative 확률(ppm). n 번째 앞선 노출마다 피로 × `negative_step_pct` 를 더하고 피로 × `negative_max_pct` 에서 멈춘다."""
    if exposures == 0:
        return fatigue * p.negative_scale_pct // 100
    rule = p.repeat_exposure
    pct = min(p.negative_scale_pct + exposures * rule.negative_step_pct, rule.negative_max_pct)
    return fatigue * pct // 100


def positive_ppm(sensitivity: int, exposures: int, p: params.Params) -> int:
    """Negative 가 아닐 때의 Positive 확률(ppm). 앞선 노출마다 `positive_decay_pct` 씩 기하 감쇠하고
    첫 노출 확률의 `positive_floor_pct` 아래로는 내려가지 않는다."""
    chance = sensitivity * p.positive_scale_pct // 100
    if exposures == 0:
        return chance
    rule = p.repeat_exposure
    keep = params.PPM
    floor = rule.positive_floor_pct * params.PPM // 100
    # 바닥에 닿으면 그 뒤 노출은 바닥에 묶이므로 멈춘다.
    for _ in range(exposures):
        keep = keep * (100 - rule.positive_decay_pct) // 100
        if keep <= floor:
            keep = floor
            break
    return chance * keep // params.PPM


def response_type(
    seed: int, customer_id: str, traits: dict[str, int], tid: str, p: params.Params, exposures: int = 0
) -> str:
    """`traits` 는 `world.behavior_traits` 의 별칭 묶음, `exposures` 는 `prior_exposures` 값이다.

    난수 열쇠에 노출 수·처치 분기를 넣지 않는다(CRN) — 같은 고객은 언제나 같은 u 를 쓰고 문턱만 바뀐다.
    `exposures` 기본값 0 은 단일 배정(첫 노출) 기준의 참고 집계용이다.
    """
    negative = negative_ppm(traits["fatigue"], exposures, p)
    if rng.Stream(seed, customer_id, "response", rng.RESPONSE_DAY).next_u64() < negative * _TWO_64 // params.PPM:
        return NEGATIVE
    chance = positive_ppm((traits[tid] + traits["responsiveness"]) // 2, exposures, p)
    if rng.Stream(seed, customer_id, "response:" + tid, rng.RESPONSE_DAY).next_u64() < chance * _TWO_64 // params.PPM:
        return POSITIVE
    return NEUTRAL


def response_mix(
    seed: int, customers: list[dict[str, object]], tid: str, exposures: int
) -> dict[str, int]:
    """`customers` 전원이 앞선 노출 `exposures` 번 뒤 `tid` 를 받을 때의 반응 유형별 인원 — 반복 노출 감쇠 곡선의 증거용."""
    from src.simulator._internal.world import behavior_traits  # 순환 import 회피

    p = params.active()
    counts = {POSITIVE: 0, NEUTRAL: 0, NEGATIVE: 0}
    for customer in customers:
        kind = response_type(seed, customer["customer_id"], behavior_traits(customer), tid, p, exposures)
        counts[kind] += 1
    return counts


def active_assignment(customer: dict[str, object], at_ms: int, p: params.Params) -> tuple[int, str] | None:
    """`at_ms` 에 효과가 살아 있는 배정 `(배정 시각, 처치)` — 마지막 배정이 비-`T0` 이고 효과 창 안일 때만.

    효과 창의 유일한 판정이다. 엔진(`effect`)과 창 안 재배정 표시(`api.apply_treatment` 의 `supersedes`)가 함께 쓴다.
    """
    assignments = customer["assignments"]
    if not assignments:
        return None
    assigned_at, tid = assignments[-1]
    if tid == "T0" or not assigned_at <= at_ms < assigned_at + p.window_days * clock.DAY_MS:
        return None
    return assigned_at, tid


def _active(window, customer: dict[str, object], at_ms: int) -> str | None:
    found = active_assignment(customer, at_ms, window.params)
    return None if found is None else found[1]


def effect(window, customer: dict[str, object], at_ms: int) -> tuple[params.Arm | None, str | None]:
    tid = _active(window, customer, at_ms)
    if tid is None:
        return None, None
    exposures = prior_exposures(customer["assignments"])
    key = (customer["customer_id"], tid, exposures)
    found = window.responses.get(key)
    if found is None:
        found = window.responses[key] = response_type(
            window.seed, customer["customer_id"], window.traits(customer), tid, window.params, exposures
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
            # 반사실 팔의 유형은 실제 실행(`effect`)과 같은 배정 이력에서 센 노출 수로 정한다.
            exposures = prior_exposures(copy["assignments"])
            queue = list(pending.get(cid, ()))
            queue.append((now, cid, copy["next_seq"], "treat"))
            copy["next_seq"] += 1
            orders = engine.simulate_customer(world, copy, queue, end)
            arms[tid] = outcome(orders, tid, p)
            if tid != "T0":
                types[tid] = response_type(world["seed"], cid, behavior_traits(original), tid, p, exposures)
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
