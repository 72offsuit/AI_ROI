"""이벤트 생성 엔진 — 방문·탐색·구매 퍼널(S4) · 이탈 진행(S5) · 처치 노출과 반응(S6).

난수는 (seed, customer_id, 용도, day) 열쇠의 스트림에서만 뽑는다. 고객끼리 공유하는 상태가 없어서
한 고객을 따로 떼어 같은 창을 다시 돌리면(`simulate_customer`) 같은 결과가 나온다 — 반사실 실행의 근거다.
"""

from __future__ import annotations

import heapq
from typing import Callable, Iterator

from src.measurement.schema import EVENT_FIELDS
from src.simulator._internal import behavior, cart, clock, params, rng, treatment
from src.simulator._internal.world import behavior_traits, customer_index

_FIELD_NAMES = tuple(spec.name for spec in EVENT_FIELDS)
_TWO_64 = 1 << 64
PPM = params.PPM

Event = dict[str, object]
QueueItem = tuple[int, str, int, str]


def _below_ppm(u: int, ppm: int) -> bool:
    return u < (min(max(ppm, 0), PPM) * _TWO_64) // PPM


class _Window:
    __slots__ = (
        "world", "seed", "version", "lifetime", "params", "heap", "draws", "orders", "responses",
        "_traits",
    )

    def __init__(self, world: dict[str, object], orders: list[dict[str, object]] | None) -> None:
        self.world = world
        self.seed = world["seed"]
        self.version = world["simulator_version"]
        self.lifetime = world["cart_lifetime_ms"]
        self.params = params.active()
        self.heap: list[QueueItem] = world["queue"]
        self.draws = rng.DayDraws(self.seed, 0)
        self.orders = orders
        self.responses: dict[tuple[str, str, int], str] = {}  # (고객, 처치, 앞선 노출 수) → 반응 유형
        self._traits: dict[str, dict[str, int]] = {}

    def traits(self, customer: dict[str, object]) -> dict[str, int]:
        cid = customer["customer_id"]
        found = self._traits.get(cid)
        if found is None:
            found = self._traits[cid] = behavior_traits(customer)
        return found

    def push(self, customer: dict[str, object], at_ms: int, kind: str) -> None:
        heapq.heappush(self.heap, (at_ms, customer["customer_id"], next_seq(customer), kind))

    def event(
        self,
        customer: dict[str, object],
        at_ms: int,
        seq: int,
        event_type: str,
        page_type: str | None,
        product: params.Product | None = None,
        quantity: int | None = None,
        unit_price: int | None = None,
        *,
        in_session: bool = True,
    ) -> Event:
        record: Event = dict.fromkeys(_FIELD_NAMES)
        cid = customer["customer_id"]
        record["event_id"] = rng.event_id(self.seed, cid, seq)
        record["customer_id"] = cid
        record["timestamp"] = clock.timestamp(at_ms)
        record["event_type"] = event_type
        if in_session:
            record["session_id"] = customer["session"]["session_id"]
        record["page_type"] = page_type
        if product is not None:
            record["product_id"] = product.product_id
            record["category"] = product.category
            record["unit_price"] = product.unit_price if unit_price is None else unit_price
        record["quantity"] = quantity
        record["simulator_version"] = self.version
        record["random_seed"] = self.seed
        return record


def next_seq(customer: dict[str, object]) -> int:
    seq = customer["next_seq"]
    customer["next_seq"] = seq + 1
    return seq


def run(
    world: dict[str, object], end_ms: int, orders: list[dict[str, object]] | None = None
) -> Iterator[Event]:
    """창 `[now, end_ms)` 의 이벤트를 생성 순서로 낸다. 완결된 주문은 `orders` 에 덧붙인다."""
    customers = world["customers"]
    return _loop(_Window(world, orders), customers, lambda cid: customers[customer_index(cid)], end_ms)


def simulate_customer(
    world: dict[str, object], customer: dict[str, object], queue: list[QueueItem], end_ms: int
) -> list[dict[str, object]]:
    """한 고객만 떼어 `[now, end_ms)` 를 돌리고 완결된 주문을 돌려준다. `world` 는 바꾸지 않는다.

    `customer`·`queue` 는 호출자가 넘긴 사본이며 이 함수가 바꾼다. 이벤트는 버린다.
    """
    shadow = {**world, "queue": list(queue), "now_ms": world["now_ms"]}
    heapq.heapify(shadow["queue"])
    orders: list[dict[str, object]] = []
    for _ in _loop(_Window(shadow, orders), [customer], lambda cid: customer, end_ms):
        pass
    return orders


def _loop(
    window: _Window,
    customers: list[dict[str, object]],
    lookup: Callable[[str], dict[str, object]],
    end_ms: int,
) -> Iterator[Event]:
    # 창 끝(end_ms)은 멈춤 조건으로만 쓴다. 생성 규칙이 읽으면 분할 불변성이 깨진다.
    world = window.world
    start_ms = world["calendar_start_ms"]
    heap = window.heap
    now = world["now_ms"]
    while now < end_ms:
        window.draws = rng.DayDraws(window.seed, (now - start_ms) // clock.DAY_MS)
        for customer in customers:
            _day_start(window, customer, now)
        day_end = now + clock.DAY_MS
        while heap and heap[0][0] < day_end:
            at_ms, cid, seq, kind = heapq.heappop(heap)
            customer = lookup(cid)
            if kind == "visit":
                records = _visit(window, customer, at_ms, seq)
            elif kind == "treat":
                records = _treat(window, customer, at_ms, seq)
            else:
                records = _action(window, customer, at_ms, seq)
            yield from records
        now = day_end
        world["now_ms"] = now


# ── 하루 시작: 이탈 전이 · 방문 결정 ──────────────────────────────────────────


def _day_start(window: _Window, customer: dict[str, object], day_ms: int) -> None:
    if customer["lifecycle"] != "active" or day_ms < customer["signup_ms"]:
        return
    p = window.params
    cid = customer["customer_id"]
    traits = window.traits(customer)
    arm, response = treatment.effect(window, customer, day_ms)
    positive = response == treatment.POSITIVE
    negative = response == treatment.NEGATIVE
    day = window.draws.stream(cid, "day")
    # 용도별 고정 순서: [0] 이탈 전이 [1] 방문 [2] 방문 시각. 처치가 달라도 같은 자리의 난수를 쓴다(CRN).
    u_transition = day.next_u64()
    u_visit = day.next_u64()
    if customer["churning"]:
        recovery = p.recovery_ppm
        if customer["gate_churning"]:
            # 재구매 게이트 탈락으로 들어온 이탈은 자연 회복만 낮춘다. 처치 Positive 가산은 처치 효과라 그대로 둔다.
            recovery = recovery * p.gate_recovery_scale_pct // 100
        if positive:
            recovery += arm.recovery_ppm
        if _below_ppm(u_transition, recovery):
            customer["churning"] = False
            customer["gate_churning"] = False
            customer["engagement"] = PPM
        else:
            customer["engagement"] = max(
                p.engagement_floor_ppm, customer["engagement"] * p.decay_ppm // PPM
            )
    else:
        hazard = traits["churn"] * p.onset_scale_ppm // PPM
        if positive:
            hazard = hazard * (100 - arm.onset_protect_pct) // 100
        elif negative:
            hazard = hazard * (100 + p.negative_onset_accel_pct) // 100
        if _below_ppm(u_transition, hazard):
            customer["churning"] = True
            customer["engagement"] = max(
                p.engagement_floor_ppm, customer["engagement"] * p.decay_ppm // PPM
            )
    override = behavior.visit_probability(cid)
    if override is not None:
        visits = u_visit < (override[0] * _TWO_64) // override[1]
    else:
        ppm = traits["visit"] * PPM // 7_000 * p.visit_scale_pct // 100
        ppm = ppm * customer["engagement"] // PPM
        if positive:
            ppm = ppm * (100 + arm.visit_boost_pct) // 100
        elif negative:
            ppm = ppm * (100 - p.negative_visit_penalty_pct) // 100
        visits = _below_ppm(u_visit, min(ppm, p.visit_max_ppm))
    if not visits:
        return
    offset = day.below(clock.DAY_MS)
    window.push(customer, day_ms + offset, "visit")


# ── 처치 노출 ────────────────────────────────────────────────────────────────


def _treat(window: _Window, customer: dict[str, object], at_ms: int, seq: int) -> list[Event]:
    assigned_at, tid = customer["assignments"][-1]
    if assigned_at != at_ms:
        # 같은 시각에 덮어쓴 배정이 아니면 옛 노출 항목이다 — 무시한다.
        return []
    if tid == "T0":
        customer["promo"] = None
        return []
    arm = window.params.arms[tid]
    stamp = clock.timestamp(at_ms)
    campaign_id = f"CMP-{stamp[0:4]}{stamp[5:7]}{stamp[8:10]}-{int(tid[1]):03d}"
    day_number = (at_ms - window.world["calendar_start_ms"]) // clock.DAY_MS
    coupon_id = f"CPN-{tid}{day_number % 10_000:04d}" if arm.coupon_discount_krw else None
    if customer["promo"] is not None and customer["promo"]["at_ms"] == at_ms:
        return []  # 같은 시각 두 번째 노출 항목(같은 배정의 재적용)은 한 번만 낸다
    claim = False
    if coupon_id:
        # 쿠폰을 받아 둘지는 노출 때 한 번 정한다. 반응 유형 Positive 는 민감도 그대로, 그 밖은 click_scale 만큼.
        _, response = treatment.effect(window, customer, at_ms)
        scale = 100 if response == treatment.POSITIVE else window.params.coupon_click_scale_pct
        chance = window.traits(customer)["coupon"] * scale // 100
        claim = _below_ppm(window.draws.stream(customer["customer_id"], "claim").next_u64(), chance)
    customer["promo"] = {
        "treatment_id": tid, "at_ms": at_ms, "campaign_id": campaign_id, "coupon_id": coupon_id,
        "claim": claim, "clicked": False, "used": False,
    }
    records = []
    kinds = ["campaign_exposed", "push_sent"] + (["coupon_exposed"] if coupon_id else [])
    for index, kind in enumerate(kinds):
        record = window.event(
            customer, at_ms, seq if index == 0 else next_seq(customer), kind, None, in_session=False
        )
        record["campaign_id"] = campaign_id
        record["coupon_id"] = coupon_id
        record["treatment_id"] = tid
        records.append(record)
    return records


# ── 방문·세션 ────────────────────────────────────────────────────────────────


def _visit(window: _Window, customer: dict[str, object], at_ms: int, seq: int) -> list[Event]:
    session = customer["session"]
    if session is not None and (
        session["open"] or at_ms - session["last_activity_ms"] < clock.SESSION_TIMEOUT_MS
    ):
        return []
    p = window.params
    cid = customer["customer_id"]
    traits = window.traits(customer)
    arm, response = treatment.effect(window, customer, at_ms)
    promo = treatment.live_promo(window, customer, at_ms)
    draw = window.draws.stream(cid, "intent")
    u_intent = draw.next_u64()
    target = 0
    if _below_ppm(u_intent, _intent_ppm(window, customer, at_ms, arm, response)):
        lo, hi = p.basket_spread_pct
        target = traits["order_value"] * draw.between(lo, hi) // 100
        target = _topped_up(window, customer, draw, target, promo, at_ms)
    customer["session"] = {
        "session_id": f"S-{cid}-{at_ms}",
        "start_ms": at_ms,
        "last_activity_ms": at_ms,
        "actions": 0,
        "open": True,
        "intent": target,
        "stage": "browse",
        "order": None,
    }
    customer["rfm"]["last_visit_ms"] = at_ms
    records = [window.event(customer, at_ms, seq, "session_start", "home")]
    if _coupon_open(window, promo, at_ms, "claim") and not promo["clicked"]:
        # 받아 두기로 한 고객은 노출 뒤 첫 방문에서 쿠폰을 누른다. 누른 쿠폰만 결제에 쓴다.
        promo["clicked"] = True
        record = window.event(customer, at_ms, next_seq(customer), "coupon_clicked", "home")
        record["coupon_id"] = promo["coupon_id"]
        record["campaign_id"] = promo["campaign_id"]
        record["treatment_id"] = promo["treatment_id"]
        records.append(record)
    _continue(window, customer, at_ms, records[-1])
    return records


def _coupon_open(window: _Window, promo: dict | None, at_ms: int, flag: str) -> bool:
    """쿠폰이 아직 쓸 수 있는가 — 받아 둠(flag), 미사용, 유효기간(배정 시각 + valid_days) 안."""
    if promo is None or not promo["coupon_id"] or not promo[flag] or promo["used"]:
        return False
    valid = window.params.arms[promo["treatment_id"]].coupon_valid_days
    return at_ms < promo["at_ms"] + valid * clock.DAY_MS


def _intent_ppm(
    window: _Window, customer: dict[str, object], at_ms: int, arm: params.Arm | None, response: str | None
) -> int:
    p = window.params
    traits = window.traits(customer)
    last = customer["rfm"]["last_purchase_ms"]
    if last is None:
        cycle = PPM
    else:
        cycle_ms = max(1, traits["cycle"] * clock.DAY_MS // 1000)
        cycle = min(max((at_ms - last) * PPM // cycle_ms, p.cycle_min_ppm), p.cycle_max_ppm)
    ppm = traits["purchase"] * cycle // PPM * p.intent_scale_pct // 100
    ppm = ppm * customer["engagement"] // PPM
    if response == treatment.POSITIVE:
        ppm = ppm * (100 + arm.intent_boost_pct) // 100
    elif response == treatment.NEGATIVE:
        ppm = ppm * (100 - p.negative_intent_penalty_pct) // 100
    return ppm


def _topped_up(
    window: _Window, customer: dict[str, object], draw: rng.Stream, target: int, promo: dict | None,
    at_ms: int,
) -> int:
    """기준 금액 바로 아래의 목표 금액을 기준까지 올린다 — 쿠폰 최소주문 · 일반 무료배송 기준."""
    p = window.params
    traits = window.traits(customer)
    if _coupon_open(window, promo, at_ms, "claim"):
        minimum = p.arms[promo["treatment_id"]].coupon_min_order_krw
        if target < minimum and (minimum - target) * 100 <= minimum * p.topup_max_gap_pct:
            chance = traits["coupon"] * p.coupon_topup_scale_pct // 100
            if _below_ppm(draw.next_u64(), chance):
                target = minimum
    free_shipping = promo is not None and promo["treatment_id"] == "T1"
    threshold = p.free_shipping_threshold_krw
    if not free_shipping and target < threshold and (threshold - target) * 100 <= threshold * p.topup_max_gap_pct:
        chance = traits["shipping"] * p.free_shipping_topup_scale_pct // 100
        if _below_ppm(draw.next_u64(), chance):
            target = threshold
    return target


def _action(window: _Window, customer: dict[str, object], at_ms: int, seq: int) -> list[Event]:
    session = customer["session"]
    if session["stage"] == "checkout":
        records = _complete(window, customer, at_ms, seq)
    elif session["intent"] and session["intent"] <= _cart_value(window, customer, at_ms) and (
        session["intent"] == 1
        or _cart_value(window, customer, at_ms) * 100 <= session["intent"] * window.params.intent_trim_over_pct
    ):
        records = [_checkout(window, customer, at_ms, seq)]
    else:
        cid = customer["customer_id"]
        browse = window.draws.stream(cid, "browse")
        if session["intent"] > 1 and _cart_value(window, customer, at_ms) * 100 > (
            session["intent"] * window.params.intent_trim_over_pct
        ):
            action = "remove_from_cart"  # 목표 금액을 크게 넘긴 장바구니는 덜어낸 뒤 결제한다
        else:
            action = behavior.ACTIONS[browse.weighted(_weights(window, customer, session))]
        if action == "add_to_cart":
            record = _add_to_cart(window, customer, at_ms, seq)
        elif action == "remove_from_cart":
            record = _remove_from_cart(window, customer, at_ms, seq)
        elif action == "product_view":
            record = _product_view(window, customer, at_ms, seq)
        else:
            page = behavior.PAGE_VIEW_PAGES[browse.below(len(behavior.PAGE_VIEW_PAGES))]
            record = window.event(customer, at_ms, seq, "page_view", page)
        records = [record]
    _continue(window, customer, at_ms, records[-1])
    return records


def _weights(window: _Window, customer: dict[str, object], session: dict[str, object]) -> tuple[int, ...]:
    p = window.params
    if session["intent"]:
        return p.intent_weights
    # 탐색 세션: page_view·product_view·remove 는 config 가중치(×1000), 담기는 장바구니 이탈 성향이 정한다.
    page, view, _, remove = p.browse_weights
    atc = window.traits(customer)["abandon"] * p.browse_atc_weight_pct // 100 // 1000
    return (page * 1000, view * 1000, atc, remove * 1000)


def _cart_value(window: _Window, customer: dict[str, object], at_ms: int) -> int:
    items = customer["cart"]
    total = 0
    for pid in cart.live_products(items, at_ms, window.lifetime):
        total += items[pid]["quantity"] * items[pid]["unit_price"]
    return total


def _checkout(window: _Window, customer: dict[str, object], at_ms: int, seq: int) -> Event:
    p = window.params
    items = customer["cart"]
    lines = [
        [pid, items[pid]["quantity"], items[pid]["unit_price"]]
        for pid in cart.live_products(items, at_ms, window.lifetime)
    ]
    subtotal = 0
    for _, quantity, price in lines:
        subtotal += quantity * price
    promo = treatment.live_promo(window, customer, at_ms)
    discount = 0
    coupon = None
    if _coupon_open(window, promo, at_ms, "clicked"):
        arm = p.arms[promo["treatment_id"]]
        if subtotal >= arm.coupon_min_order_krw:
            discount = min(arm.coupon_discount_krw, subtotal)
            coupon = [promo["coupon_id"], promo["campaign_id"]]
    # 커머스 정책: 할인 전 상품 합계가 기준 이상이면 일반 무료배송(정책 배송비 0). T1 은 그 미만의 배송비를 면제한다.
    shipping_fee = p.shipping_fee_krw if subtotal < p.free_shipping_threshold_krw else 0
    free_shipping = promo is not None and promo["treatment_id"] == "T1"
    customer["checkout_seq"] += 1
    order_id = f"O{customer['customer_id'][1:]}-{customer['checkout_seq']:06d}"
    treatment_id = None if promo is None else promo["treatment_id"]
    session = customer["session"]
    session["stage"] = "checkout"
    session["order"] = {
        "order_id": order_id,
        "lines": lines,
        "subtotal": subtotal,
        "discount": discount,
        "shipping_fee": shipping_fee,
        "shipping_charged": 0 if free_shipping else shipping_fee,
        "coupon": coupon,
        "treatment_id": treatment_id,
    }
    record = window.event(customer, at_ms, seq, "checkout_start", "checkout")
    record["order_id"] = order_id
    record["order_amount"] = subtotal - discount
    record["treatment_id"] = treatment_id
    return record


def _complete(window: _Window, customer: dict[str, object], at_ms: int, seq: int) -> list[Event]:
    p = window.params
    traits = window.traits(customer)
    session = customer["session"]
    order = session["order"]
    session["order"] = None
    session["intent"] = 0
    session["stage"] = "done"
    abandon = traits["abandon"] * p.abandon_scale_pct // 100
    if order["shipping_charged"]:
        abandon += traits["shipping"] * p.shipping_abandon_scale_pct // 100
    if _below_ppm(window.draws.stream(customer["customer_id"], "cart").next_u64(), abandon):
        return [window.event(customer, at_ms, seq, "page_view", "cart")]
    amount = order["subtotal"] - order["discount"]
    records = []
    if order["coupon"] is not None:
        customer["promo"]["used"] = True
        use = window.event(customer, at_ms, seq, "coupon_use", "checkout")
        use["coupon_id"], use["campaign_id"] = order["coupon"]
        use["order_id"] = order["order_id"]
        use["order_amount"] = amount
        use["treatment_id"] = order["treatment_id"]
        records.append(use)
        seq = next_seq(customer)
    record = window.event(customer, at_ms, seq, "purchase", "complete")
    record["order_id"] = order["order_id"]
    record["order_amount"] = amount
    if order["coupon"] is not None:
        record["coupon_id"], record["campaign_id"] = order["coupon"]
    record["treatment_id"] = order["treatment_id"]
    records.append(record)
    items = customer["cart"]
    history = customer["purchased"]
    for pid, _, _ in order["lines"]:
        items.pop(pid, None)
        if pid in history:
            history.remove(pid)
        history.append(pid)
    del history[: max(0, len(history) - window.params.recent_purchases_cap)]
    rfm = customer["rfm"]
    rfm["order_count"] += 1
    rfm["monetary"] += amount
    rfm["last_purchase_ms"] = at_ms
    if rfm["order_count"] == 1:
        _repurchase_gate(window, customer)
    if window.orders is not None:
        catalog = window.params.product_index
        window.orders.append({
            "order_id": order["order_id"],
            "customer_id": customer["customer_id"],
            "ordered_at": clock.timestamp(at_ms),
            "order_amount": amount,
            "discount": order["discount"],
            "shipping_fee": order["shipping_fee"],
            "shipping_charged": order["shipping_charged"],
            "treatment_id": order["treatment_id"],
            "items": [
                {
                    "line_no": number,
                    "product_id": pid,
                    "quantity": quantity,
                    "unit_price": price,
                    "unit_cost": catalog[pid].unit_cost,
                }
                for number, (pid, quantity, price) in enumerate(order["lines"], start=1)
            ],
        })
    return records


def _repurchase_gate(window: _Window, customer: dict[str, object]) -> None:
    """생애 첫 구매 직후 한 번, 재구매 성향 Trait 으로 다음 구매로 이어질 고객인지 정한다(#183, F11).

    0일차 고객은 시뮬레이터 안 첫 구매가 생애 첫 구매가 아니라 제외한다 — 관측 중 가입한 고객만 대상이다.
    통과하면 아무것도 바꾸지 않는다. 실패하면 `_day_start` 의 이탈 시작(onset)과 같은 처리로 이탈 진행에 넣고,
    그 이탈에는 표시(`gate_churning`)를 달아 회복 hazard 를 `gate_recovery_scale_pct` 로 낮춘다 — 비재구매자도
    돌아올 수 있되 일반 이탈자보다 느리다. 회복하면 표시를 지워 그 뒤로는 일반 고객과 같다.
    이탈 성향 Trait(churn)과 이중 계산이 아니다: 그쪽은 매일의 시간 기반 hazard 이고, 이 게이트는 첫 구매라는
    사건에 붙은 한 번뿐인 전이다.
    """
    if customer["signup_ms"] <= window.world["calendar_start_ms"]:
        return
    # 날짜·처치와 무관한 고객 고정 스트림 — 처치 분기(CRN)마다 첫 구매 날짜가 달라도 게이트 결과는 같다.
    draw = rng.Stream(window.seed, customer["customer_id"], "repurchase", rng.REPURCHASE_DAY)
    if _below_ppm(draw.next_u64(), window.traits(customer)["repurchase"]) or customer["churning"]:
        return  # 이미 이탈 진행 중이면 onset 을 다시 적용하지 않는다(감쇠를 하루 두 번 겹치지 않게)
    p = window.params
    customer["churning"] = True
    customer["gate_churning"] = True
    customer["engagement"] = max(p.engagement_floor_ppm, customer["engagement"] * p.decay_ppm // PPM)


def _product_view(window: _Window, customer: dict[str, object], at_ms: int, seq: int) -> Event:
    p = window.params
    browse = window.draws.stream(customer["customer_id"], "browse")
    purchased = customer["purchased"]
    reorder = window.traits(customer)["loyalty"] * p.reorder_scale_pct // 100
    if purchased and _below_ppm(browse.next_u64(), reorder):
        # 반복 구매: 과거에 산 상품을 다시 본다(브랜드 충성도 Trait).
        product = p.product_index[purchased[browse.below(len(purchased))]]
    else:
        pool = p.category_pools[browse.weighted(p.category_weights)]
        product = p.catalog[pool[browse.below(len(pool))]]
    views = customer["recent_views"]
    views.append([at_ms, product.product_id])
    del views[: max(0, len(views) - behavior.RECENT_VIEWS_CAP)]
    return window.event(customer, at_ms, seq, "product_view", "detail", product)


def _add_to_cart(window: _Window, customer: dict[str, object], at_ms: int, seq: int) -> Event:
    views = customer["recent_views"]
    if not views:
        return _product_view(window, customer, at_ms, seq)
    product = window.params.product_index[views[-1][1]]
    wanted = window.draws.stream(customer["customer_id"], "cart").between(*window.params.add_quantity)
    target = customer["session"]["intent"]
    if target > 1:
        # 구매 세션은 목표 금액에 필요한 만큼만 담는다(넘침은 한 개 단가 이하).
        remaining = target - _cart_value(window, customer, at_ms)
        wanted = max(1, min(wanted, -(-remaining // product.unit_price)))
    added = cart.add(
        customer["cart"], product.product_id, wanted, product.unit_price, at_ms, window.lifetime,
    )
    if added == 0:
        return window.event(customer, at_ms, seq, "page_view", "cart")
    return window.event(customer, at_ms, seq, "add_to_cart", "detail", product, added)


def _remove_from_cart(
    window: _Window, customer: dict[str, object], at_ms: int, seq: int
) -> Event:
    items = customer["cart"]
    live = cart.live_products(items, at_ms, window.lifetime)
    if not live:
        return window.event(customer, at_ms, seq, "page_view", "cart")
    draw = window.draws.stream(customer["customer_id"], "cart")
    product_id = live[draw.below(len(live))]
    item = items[product_id]
    unit_price = item["unit_price"]
    wanted = draw.between(1, item["quantity"] + 1)
    removed = cart.remove(items, product_id, wanted, at_ms, window.lifetime)
    return window.event(
        customer, at_ms, seq, "remove_from_cart", "cart",
        window.params.product_index[product_id], removed, unit_price,
    )


def _continue(
    window: _Window, customer: dict[str, object], at_ms: int, record: Event
) -> None:
    p = window.params
    session = customer["session"]
    session["actions"] += 1
    session["last_activity_ms"] = at_ms
    draw = window.draws.stream(customer["customer_id"], "session")
    stage = session["stage"]
    if stage == "checkout":
        proceed = True
    elif stage == "done":
        proceed = False
    elif session["intent"]:
        proceed = draw.bernoulli(p.continue_intent_ppm, PPM)
        if session["actions"] >= p.max_actions_intent:
            # 목표 금액에 못 미쳐도 담은 것이 있으면 결제로 간다. 없으면 세션을 끝낸다.
            proceed = _cart_value(window, customer, at_ms) > 0
            session["intent"] = 1 if proceed else 0
    else:
        proceed = session["actions"] < p.max_actions_browse and draw.bernoulli(
            p.continue_browse_ppm, PPM
        )
    if proceed:
        window.push(customer, at_ms + draw.between(*p.action_delay_ms), "action")
        session["open"] = True
        return
    session["open"] = False
    session["stage"] = "browse"
    session["intent"] = 0
    record["session_duration"] = (at_ms - session["start_ms"]) // 1000
