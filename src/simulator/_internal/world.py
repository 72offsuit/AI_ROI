from __future__ import annotations

import hashlib
import json
import re

from src.simulator._internal import behavior, clock, profiles
from src.simulator._internal.cart import MAX_QUANTITY
from src.simulator._internal.rng import RNG_SCHEME, canonical_json

FORMAT_VERSION = "sim-state-v1"
SIMULATOR_VERSION = "sim-0.1"
WORLD_ID_SCHEME = "sim-world-v1"
SEED_LIMIT = 1 << 63
MAX_CUSTOMERS = 99_999_999
# session_id 는 13자리 epoch ms 다(schema.IDENTIFIER_PATTERNS). 이 시각을 넘는 창은 만들지 않는다.
MAX_TIME_MS = 10_000_000_000_000

CATALOG: tuple[tuple[str, str, int], ...] = (
    ("P0001", "fresh_food", 4900),
    ("P0002", "meal_solution", 6500),
    ("P0003", "dairy", 2800),
    ("P0004", "beverage", 1500),
    ("P0005", "household", 3900),
)

_VERSIONED = (
    ("format_version", FORMAT_VERSION),
    ("rng_scheme", RNG_SCHEME),
    ("simulator_version", SIMULATOR_VERSION),
)
_TOP_KEYS = frozenset({
    "format_version", "simulator_version", "rng_scheme", "world_id", "seed",
    "num_customers", "profile", "calendar_start_ms", "cart_lifetime_ms", "now_ms",
    "queue", "catalog", "orders", "customers",
})
_CUSTOMER_KEYS = frozenset({
    "customer_id", "signup_ms", "lifecycle", "hidden_traits", "cart", "recent_views",
    "session", "rfm", "assignments", "next_seq",
})
_CART_KEYS = frozenset({"quantity", "last_change_ms", "unit_price"})
_SESSION_KEYS = frozenset({"session_id", "start_ms", "last_activity_ms", "actions", "open"})
_RFM_KEYS = frozenset({"order_count", "monetary", "last_purchase_ms", "last_visit_ms"})
_QUEUE_KINDS = frozenset({"visit", "action"})
_TREATMENT_ID = re.compile(r"T[0-4]")
_PRODUCT_IDS = frozenset(pid for pid, _, _ in CATALOG)


class IncompatibleState(ValueError):
    pass


def customer_id(index: int) -> str:
    return f"C{index + 1:08d}"


def customer_index(cid: str) -> int:
    return int(cid[1:]) - 1


def world_id(seed: int, num_customers: int, profile: str, calendar_start_ms: int) -> str:
    key = canonical_json([WORLD_ID_SCHEME, seed, num_customers, profile, calendar_start_ms])
    return "W-" + hashlib.sha256(key).hexdigest()[:16]


def _profile_settings(profile: str) -> tuple[int, int]:
    settings = profiles.PROFILES[profile]
    start_ms = clock.kst_midnight_ms(settings["calendar_start"])
    return start_ms, int(settings["cart_lifetime_days"]) * clock.DAY_MS


def _catalog() -> list[dict[str, object]]:
    return [
        {"product_id": pid, "category": category, "unit_price": price, "unit_cost": None}
        for pid, category, price in CATALOG
    ]


def _new_customer(cid: str, signup_ms: int) -> dict[str, object]:
    return {
        "customer_id": cid,
        "signup_ms": signup_ms,
        "lifecycle": "active",
        "hidden_traits": {},
        "cart": {},
        "recent_views": [],
        "session": None,
        "rfm": {
            "order_count": 0,
            "monetary": 0,
            "last_purchase_ms": None,
            "last_visit_ms": None,
        },
        "assignments": [],
        "next_seq": 0,
    }


def new_world(seed: int, num_customers: int, profile: str) -> dict[str, object]:
    start_ms, lifetime_ms = _profile_settings(profile)
    return {
        "format_version": FORMAT_VERSION,
        "simulator_version": SIMULATOR_VERSION,
        "rng_scheme": RNG_SCHEME,
        "world_id": world_id(seed, num_customers, profile, start_ms),
        "seed": seed,
        "num_customers": num_customers,
        "profile": profile,
        "calendar_start_ms": start_ms,
        "cart_lifetime_ms": lifetime_ms,
        "now_ms": start_ms,
        "queue": [],
        "catalog": _catalog(),
        "orders": [],
        "customers": [_new_customer(customer_id(i), start_ms) for i in range(num_customers)],
    }


_INITIAL_DIGESTS: dict[tuple[int, int, str], str] = {}


def initial_digest(seed: int, num_customers: int, profile: str) -> str:
    key = (seed, num_customers, profile)
    found = _INITIAL_DIGESTS.get(key)
    if found is None:
        found = _INITIAL_DIGESTS[key] = digest(encode(new_world(seed, num_customers, profile)))
    return found


def _reject_floats(value: object) -> None:
    stack = [value]
    while stack:
        item = stack.pop()
        if isinstance(item, float):
            raise ValueError(f"상태에 부동소수가 있다: {item!r}")
        if isinstance(item, dict):
            stack.extend(item.values())
        elif isinstance(item, (list, tuple)):
            stack.extend(item)


def encode(world: dict[str, object]) -> bytes:
    # 힙 배열 배치는 넣은 이력에 좌우되므로 키 순으로 정렬해 쓴다.
    payload = {**world, "queue": sorted(world["queue"])}
    _reject_floats(payload)
    return canonical_json(payload)


def decode(data: bytes) -> dict[str, object]:
    world = json.loads(data.decode("ascii"))
    if not isinstance(world, dict):
        raise ValueError("상태의 최상위가 객체가 아니다")
    for field, expected in _VERSIONED:
        if world.get(field) != expected:
            raise IncompatibleState(
                f"{field} 가 다르다 — 기대 {expected!r}, 발견 {world.get(field)!r}"
            )
    _validate(world)
    world["queue"] = [tuple(item) for item in world["queue"]]
    return world


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def state_id(state_digest: str) -> str:
    return "state-" + state_digest[:16]


def _fail(where: str, detail: str) -> ValueError:
    return ValueError(f"상태 구조 위반 — {where}: {detail}")


def _keys(where: str, value: object, expected: frozenset[str]) -> dict[str, object]:
    if not isinstance(value, dict):
        raise _fail(where, "객체가 아니다")
    if set(value) != expected:
        raise _fail(
            where,
            f"모르는 키 {sorted(set(value) - expected)} · 없는 키 {sorted(expected - set(value))}",
        )
    return value


def _int(where: str, value: object, lo: int | None = None, hi: int | None = None) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise _fail(where, f"정수가 아니다: {value!r}")
    if (lo is not None and value < lo) or (hi is not None and value > hi):
        raise _fail(where, f"범위 밖: {value}")
    return value


def _optional_int(where: str, value: object) -> None:
    if value is not None:
        _int(where, value, 0, MAX_TIME_MS)


def _list(where: str, value: object) -> list[object]:
    if not isinstance(value, list):
        raise _fail(where, "배열이 아니다")
    return value


def _validate(world: dict[str, object]) -> None:
    _keys("최상위", world, _TOP_KEYS)
    seed = _int("seed", world["seed"], 0, SEED_LIMIT - 1)
    count = _int("num_customers", world["num_customers"], 1, MAX_CUSTOMERS)
    profile = world["profile"]
    if not isinstance(profile, str) or profile not in profiles.PROFILES:
        raise _fail("profile", f"모르는 profile: {profile!r}")
    start_ms, lifetime_ms = _profile_settings(profile)
    if world["calendar_start_ms"] != start_ms or isinstance(world["calendar_start_ms"], bool):
        raise _fail("calendar_start_ms", "profile 의 시작일과 다르다")
    if world["cart_lifetime_ms"] != lifetime_ms or isinstance(world["cart_lifetime_ms"], bool):
        raise _fail("cart_lifetime_ms", "profile 의 설정과 다르다")
    if world["world_id"] != world_id(seed, count, profile, start_ms):
        raise _fail("world_id", "seed·num_customers·profile 에서 유도한 값과 다르다")
    now = _int("now_ms", world["now_ms"], start_ms, MAX_TIME_MS)
    if (now - start_ms) % clock.DAY_MS:
        raise _fail("now_ms", "KST 자정이 아니다")
    if world["catalog"] != _catalog():
        raise _fail("catalog", "이 판의 카탈로그와 다르다")
    if _list("orders", world["orders"]):
        raise _fail("orders", "이 판은 주문을 만들지 않는다")
    customers = _list("customers", world["customers"])
    if len(customers) != count:
        raise _fail("customers", f"{len(customers)}명인데 num_customers 는 {count}")
    next_seqs = [_validate_customer(index, item, now) for index, item in enumerate(customers)]
    for position, item in enumerate(_list("queue", world["queue"])):
        where = f"queue[{position}]"
        if not isinstance(item, list) or len(item) != 4:
            raise _fail(where, "[time_ms, customer_id, seq, kind] 가 아니다")
        at, cid, seq, kind = item
        _int(where, at, now, MAX_TIME_MS)
        if not isinstance(cid, str) or not re.fullmatch(r"C\d{8}", cid):
            raise _fail(where, f"고객 ID 형식 위반: {cid!r}")
        index = customer_index(cid)
        if not 0 <= index < count:
            raise _fail(where, f"이 세계에 없는 고객: {cid}")
        _int(where, seq, 0, next_seqs[index] - 1)
        if kind not in _QUEUE_KINDS:
            raise _fail(where, f"모르는 사건 종류: {kind!r}")


def _validate_customer(index: int, value: object, now: int) -> int:
    where = f"customers[{index}]"
    customer = _keys(where, value, _CUSTOMER_KEYS)
    if customer["customer_id"] != customer_id(index):
        raise _fail(where, f"고객 ID 가 순번과 다르다: {customer['customer_id']!r}")
    _int(f"{where}.signup_ms", customer["signup_ms"], 0, MAX_TIME_MS)
    if customer["lifecycle"] != "active":
        raise _fail(where, f"모르는 lifecycle: {customer['lifecycle']!r}")
    if customer["hidden_traits"] != {}:
        raise _fail(where, "이 판은 Hidden Trait 을 두지 않는다")
    cart = customer["cart"]
    if not isinstance(cart, dict):
        raise _fail(f"{where}.cart", "객체가 아니다")
    for pid in sorted(cart):
        if pid not in _PRODUCT_IDS:
            raise _fail(f"{where}.cart", f"카탈로그에 없는 상품: {pid!r}")
        item = _keys(f"{where}.cart.{pid}", cart[pid], _CART_KEYS)
        _int(f"{where}.cart.{pid}.quantity", item["quantity"], 1, MAX_QUANTITY)
        _int(f"{where}.cart.{pid}.last_change_ms", item["last_change_ms"], 0, now)
        _int(f"{where}.cart.{pid}.unit_price", item["unit_price"], 0)
    views = _list(f"{where}.recent_views", customer["recent_views"])
    if len(views) > behavior.RECENT_VIEWS_CAP:
        raise _fail(f"{where}.recent_views", f"{len(views)}건 — 상한을 넘는다")
    for view in views:
        if not isinstance(view, list) or len(view) != 2 or view[1] not in _PRODUCT_IDS:
            raise _fail(f"{where}.recent_views", f"[time_ms, product_id] 가 아니다: {view!r}")
        _int(f"{where}.recent_views", view[0], 0, now)
    session = customer["session"]
    if session is not None:
        session = _keys(f"{where}.session", session, _SESSION_KEYS)
        if not isinstance(session["session_id"], str) or not re.fullmatch(
            rf"S-{customer['customer_id']}-\d{{13}}", session["session_id"]
        ):
            raise _fail(f"{where}.session", f"session_id 형식 위반: {session['session_id']!r}")
        _int(f"{where}.session.start_ms", session["start_ms"], 0, MAX_TIME_MS)
        _int(f"{where}.session.last_activity_ms", session["last_activity_ms"], 0, MAX_TIME_MS)
        _int(f"{where}.session.actions", session["actions"], 0)
        if not isinstance(session["open"], bool):
            raise _fail(f"{where}.session.open", "bool 이 아니다")
    rfm = _keys(f"{where}.rfm", customer["rfm"], _RFM_KEYS)
    _int(f"{where}.rfm.order_count", rfm["order_count"], 0)
    _int(f"{where}.rfm.monetary", rfm["monetary"], 0)
    _optional_int(f"{where}.rfm.last_purchase_ms", rfm["last_purchase_ms"])
    _optional_int(f"{where}.rfm.last_visit_ms", rfm["last_visit_ms"])
    for entry in _list(f"{where}.assignments", customer["assignments"]):
        if not isinstance(entry, list) or len(entry) != 2:
            raise _fail(f"{where}.assignments", f"[time_ms, treatment_id] 가 아니다: {entry!r}")
        _int(f"{where}.assignments", entry[0], 0, now)
        if not isinstance(entry[1], str) or not _TREATMENT_ID.fullmatch(entry[1]):
            raise _fail(f"{where}.assignments", f"처치 ID 형식 위반: {entry[1]!r}")
    return _int(f"{where}.next_seq", customer["next_seq"], 0)
