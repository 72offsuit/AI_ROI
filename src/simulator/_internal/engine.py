from __future__ import annotations

import heapq
from typing import Iterator

from src.measurement.schema import EVENT_FIELDS
from src.simulator._internal import behavior, cart, clock, rng
from src.simulator._internal.world import customer_index

_FIELD_NAMES = tuple(spec.name for spec in EVENT_FIELDS)

Event = dict[str, object]
QueueItem = tuple[int, str, int, str]


class _Window:
    __slots__ = ("world", "seed", "version", "lifetime", "catalog", "heap", "draws")

    def __init__(self, world: dict[str, object]) -> None:
        self.world = world
        self.seed = world["seed"]
        self.version = world["simulator_version"]
        self.lifetime = world["cart_lifetime_ms"]
        self.catalog = world["catalog"]
        self.heap: list[QueueItem] = world["queue"]
        self.draws = rng.DayDraws(self.seed, 0)

    def push(self, customer: dict[str, object], at_ms: int, kind: str) -> None:
        seq = customer["next_seq"]
        customer["next_seq"] = seq + 1
        heapq.heappush(self.heap, (at_ms, customer["customer_id"], seq, kind))

    def event(
        self,
        customer: dict[str, object],
        at_ms: int,
        seq: int,
        event_type: str,
        page_type: str,
        product: dict[str, object] | None = None,
        quantity: int | None = None,
        unit_price: int | None = None,
    ) -> Event:
        record: Event = dict.fromkeys(_FIELD_NAMES)
        cid = customer["customer_id"]
        record["event_id"] = rng.event_id(self.seed, cid, seq)
        record["customer_id"] = cid
        record["timestamp"] = clock.timestamp(at_ms)
        record["event_type"] = event_type
        record["session_id"] = customer["session"]["session_id"]
        record["page_type"] = page_type
        if product is not None:
            record["product_id"] = product["product_id"]
            record["category"] = product["category"]
            record["unit_price"] = product["unit_price"] if unit_price is None else unit_price
        record["quantity"] = quantity
        record["simulator_version"] = self.version
        record["random_seed"] = self.seed
        return record


def run(world: dict[str, object], end_ms: int) -> Iterator[Event]:
    # 창 끝(end_ms)은 멈춤 조건으로만 쓴다. 생성 규칙이 읽으면 분할 불변성이 깨진다.
    window = _Window(world)
    start_ms = world["calendar_start_ms"]
    customers = world["customers"]
    heap = window.heap
    now = world["now_ms"]
    while now < end_ms:
        window.draws = rng.DayDraws(window.seed, (now - start_ms) // clock.DAY_MS)
        for customer in customers:
            _day_start(window, customer, now)
        day_end = now + clock.DAY_MS
        while heap and heap[0][0] < day_end:
            at_ms, cid, seq, kind = heapq.heappop(heap)
            customer = customers[customer_index(cid)]
            if kind == "visit":
                record = _visit(window, customer, at_ms, seq)
            else:
                record = _action(window, customer, at_ms, seq)
            if record is not None:
                yield record
        now = day_end
        world["now_ms"] = now


def _day_start(window: _Window, customer: dict[str, object], day_ms: int) -> None:
    if customer["lifecycle"] != "active" or day_ms < customer["signup_ms"]:
        return
    cid = customer["customer_id"]
    if not window.draws.stream(cid, "visit").bernoulli(*behavior.visit_probability(cid)):
        return
    offset = window.draws.stream(cid, "session").below(clock.DAY_MS)
    window.push(customer, day_ms + offset, "visit")


def _visit(window: _Window, customer: dict[str, object], at_ms: int, seq: int) -> Event | None:
    session = customer["session"]
    if session is not None and (
        session["open"] or at_ms - session["last_activity_ms"] < clock.SESSION_TIMEOUT_MS
    ):
        return None
    cid = customer["customer_id"]
    customer["session"] = {
        "session_id": f"S-{cid}-{at_ms}",
        "start_ms": at_ms,
        "last_activity_ms": at_ms,
        "actions": 0,
        "open": True,
    }
    customer["rfm"]["last_visit_ms"] = at_ms
    record = window.event(customer, at_ms, seq, "session_start", "home")
    _continue(window, customer, at_ms, record)
    return record


def _action(window: _Window, customer: dict[str, object], at_ms: int, seq: int) -> Event:
    cid = customer["customer_id"]
    browse = window.draws.stream(cid, "browse")
    action = behavior.ACTIONS[browse.weighted(behavior.ACTION_WEIGHTS)]
    if action == "add_to_cart":
        record = _add_to_cart(window, customer, at_ms, seq)
    elif action == "remove_from_cart":
        record = _remove_from_cart(window, customer, at_ms, seq)
    elif action == "product_view":
        record = _product_view(window, customer, at_ms, seq)
    else:
        page = behavior.PAGE_VIEW_PAGES[browse.below(len(behavior.PAGE_VIEW_PAGES))]
        record = window.event(customer, at_ms, seq, "page_view", page)
    _continue(window, customer, at_ms, record)
    return record


def _product_view(window: _Window, customer: dict[str, object], at_ms: int, seq: int) -> Event:
    browse = window.draws.stream(customer["customer_id"], "browse")
    product = window.catalog[browse.below(len(window.catalog))]
    views = customer["recent_views"]
    views.append([at_ms, product["product_id"]])
    del views[: max(0, len(views) - behavior.RECENT_VIEWS_CAP)]
    return window.event(customer, at_ms, seq, "product_view", "detail", product)


def _add_to_cart(window: _Window, customer: dict[str, object], at_ms: int, seq: int) -> Event:
    views = customer["recent_views"]
    if not views:
        return _product_view(window, customer, at_ms, seq)
    product = _product(window, views[-1][1])
    wanted = window.draws.stream(customer["customer_id"], "cart").between(*behavior.ADD_QUANTITY)
    added = cart.add(
        customer["cart"], product["product_id"], wanted, product["unit_price"],
        at_ms, window.lifetime,
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
        _product(window, product_id), removed, unit_price,
    )


def _continue(
    window: _Window, customer: dict[str, object], at_ms: int, record: Event
) -> None:
    session = customer["session"]
    session["actions"] += 1
    session["last_activity_ms"] = at_ms
    draw = window.draws.stream(customer["customer_id"], "session")
    if session["actions"] < behavior.MAX_ACTIONS_PER_SESSION and draw.bernoulli(
        *behavior.CONTINUE_P
    ):
        window.push(customer, at_ms + draw.between(*behavior.ACTION_DELAY_MS), "action")
        session["open"] = True
        return
    session["open"] = False
    record["session_duration"] = (at_ms - session["start_ms"]) // 1000


def _product(window: _Window, product_id: str) -> dict[str, object]:
    for product in window.catalog:
        if product["product_id"] == product_id:
            return product
    raise KeyError(f"카탈로그에 없는 상품: {product_id}")
