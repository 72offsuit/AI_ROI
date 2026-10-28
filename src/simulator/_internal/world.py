from __future__ import annotations

import hashlib
import json
import re

from src.simulator._internal import behavior, clock, genconfig, params, persona, profiles, traits
from src.simulator._internal.cart import MAX_QUANTITY
from src.simulator._internal.rng import RNG_SCHEME, canonical_json

# S2: 고객 항목에 persona·hidden_traits 가 생기고 world_id 열쇠에 생성 config 다이제스트가 들어간다
# (DR-S2-trait-sampling 6절). RNG_SCHEME 은 열쇠 형식이 그대로라 올리지 않는다.
# S3: P6 가입일이 Day 1~272 로 퍼져 이벤트가 바뀐다(DR-S3-p6-signup). 상태 형식은 그대로라 FORMAT_VERSION 은 둔다.
# S4~S6(#143): 구매 퍼널·이탈 진행·처치 반응이 생겨 고객 항목(engagement·churning·checkout_seq·promo)과
# 세션 항목(intent·stage·order), 큐 종류(treat), 카탈로그(240개, product_margin 생성)가 바뀐다.
# #183(F11 보정): 관측 중 가입 고객의 생애 첫 구매 뒤 재구매 게이트가 생겨 이벤트가 바뀐다. 상태 형식은 그대로라 FORMAT_VERSION 은 둔다.
# #183(sim-0.6): 구매 의향·이탈 onset·쿠폰 받기 보정, 반복 노출 감쇠, 게이트 탈락자 회복 분리로 이벤트가 바뀐다.
# 고객 항목에 gate_churning(재구매 게이트 탈락으로 시작한 이탈 표시)이 생겨 상태 형식도 바뀐다.
FORMAT_VERSION = "sim-state-v4"
# #196(sim-0.7): Sleeping Dog 직접 경로(Negative 노출 즉시 onset)와 Negative 비율 배율 상향으로 처치 이후 이벤트가 바뀐다.
SIMULATOR_VERSION = "sim-0.7"
WORLD_ID_SCHEME = "sim-world-v2"
SEED_LIMIT = 1 << 63
MAX_CUSTOMERS = 99_999_999
# session_id 는 13자리 epoch ms 다(schema.IDENTIFIER_PATTERNS). 이 시각을 넘는 창은 만들지 않는다.
MAX_TIME_MS = 10_000_000_000_000


_VERSIONED = (
    ("format_version", FORMAT_VERSION),
    ("rng_scheme", RNG_SCHEME),
    ("simulator_version", SIMULATOR_VERSION),
)
_TOP_KEYS = frozenset({
    "format_version", "simulator_version", "rng_scheme", "world_id", "seed",
    "num_customers", "profile", "calendar_start_ms", "cart_lifetime_ms", "now_ms",
    "queue", "catalog", "orders", "customers", "generation",
})
_CUSTOMER_KEYS = frozenset({
    "customer_id", "signup_ms", "lifecycle", "persona", "hidden_traits", "cart", "recent_views",
    "session", "rfm", "assignments", "next_seq", "engagement", "churning", "checkout_seq", "promo",
    "purchased", "gate_churning",
})
# 공개 오류 메시지 정책: 숨은 필드의 이름·페르소나 id·Trait 값을 싣지 않는다(docs/persona_spec.md 5.3).
# 메시지는 load_state 의 StateFormatError 로 시스템 팀까지 간다. 키 목록에서는 이 키들을 가린다.
# gate_churning 은 재구매 성향 Trait 에서 정해진 결과라 같은 취급을 한다.
_HIDDEN_KEYS = frozenset({"persona", "hidden_traits", "gate_churning"})
_CART_KEYS = frozenset({"quantity", "last_change_ms", "unit_price"})
_SESSION_KEYS = frozenset({
    "session_id", "start_ms", "last_activity_ms", "actions", "open", "intent", "stage", "order",
})
_SESSION_STAGES = frozenset({"browse", "checkout", "done"})
_PROMO_KEYS = frozenset({"treatment_id", "at_ms", "campaign_id", "coupon_id", "claim", "clicked", "used"})
_RFM_KEYS = frozenset({"order_count", "monetary", "last_purchase_ms", "last_visit_ms"})
_QUEUE_KINDS = frozenset({"visit", "action", "treat"})
_TREATMENT_ID = re.compile(r"T[0-4]")
_SESSION_ID = re.compile(r"S-(C\d{8})-\d{13}")


# 행동 엔진(engine·treatment·guardrails)이 읽는 Trait 의 중립 별칭. 숨은 이름 문자열은 이 모듈(생성·저장의
# 집)에만 둔다 — tests/test_isolation.py TestHiddenNameConfinement. 엔진은 별칭으로만 읽는다.
_BEHAVIOR_ALIASES = (
    ("visit", "base_visit_frequency"),
    ("purchase", "base_purchase_probability"),
    ("order_value", "base_order_value"),
    ("cycle", "purchase_cycle"),
    ("coupon", "coupon_sensitivity"),
    ("shipping", "shipping_fee_sensitivity"),
    ("churn", "base_churn_propensity"),
    ("responsiveness", "marketing_responsiveness"),
    ("fatigue", "marketing_fatigue"),
    ("abandon", "cart_abandonment_propensity"),
    ("loyalty", "brand_loyalty"),
    ("repurchase", "repurchase_propensity"),
)


def behavior_traits(customer: dict[str, object]) -> dict[str, int]:
    """엔진용 Trait 묶음: 별칭 → 값, 그리고 처치 ID(T1~T4) → 그 처치의 민감도 Trait 값(config 가 고른다)."""
    values = customer["hidden_traits"]
    found = {alias: values[name] for alias, name in _BEHAVIOR_ALIASES}
    for tid, arm in params.active().arms.items():
        found[tid] = values[arm.sensitivity]
    return found


class IncompatibleState(ValueError):
    pass


class GenerationMismatch(IncompatibleState):
    """판은 같고 상태를 만든 생성 config 만 지금 config 와 다르다 — config 를 다시 고르면 읽을 수 있다."""


def customer_id(index: int) -> str:
    return f"C{index + 1:08d}"


def customer_index(cid: str) -> int:
    return int(cid[1:]) - 1


def world_id(
    seed: int, num_customers: int, profile: str, calendar_start_ms: int, config_digest: str
) -> str:
    key = canonical_json(
        [WORLD_ID_SCHEME, seed, num_customers, profile, calendar_start_ms, config_digest]
    )
    return "W-" + hashlib.sha256(key).hexdigest()[:16]


def current_world_id(seed: int, num_customers: int, profile: str) -> str:
    """현재 생성 config 로 이 세 값의 세계를 만들면 받을 world_id. 계보가 config 변경을 가려내는 데 쓴다."""
    start_ms, _ = _profile_settings(profile)
    return world_id(seed, num_customers, profile, start_ms, genconfig.active().digest)


def _generation(config: genconfig.GenerationConfig) -> dict[str, str]:
    return {"config_version": config.version, "config_digest": config.digest}


def _profile_settings(profile: str) -> tuple[int, int]:
    settings = profiles.PROFILES[profile]
    start_ms = clock.kst_midnight_ms(settings["calendar_start"])
    return start_ms, int(settings["cart_lifetime_days"]) * clock.DAY_MS


def _catalog() -> list[dict[str, object]]:
    # 정본 경제 규칙 product_margin 의 사본(simulator_config.yaml catalog)으로 생성한다 — 계약 v1 §11.
    return [
        {"product_id": p.product_id, "category": p.category, "unit_price": p.unit_price,
         "unit_cost": p.unit_cost}
        for p in params.active().catalog
    ]


def _new_customer(
    cid: str, signup_ms: int, persona_id: str, hidden_traits: dict[str, int]
) -> dict[str, object]:
    return {
        "customer_id": cid,
        "signup_ms": signup_ms,
        "lifecycle": "active",
        "persona": persona_id,
        "hidden_traits": hidden_traits,
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
        "engagement": params.PPM,
        "churning": False,
        "gate_churning": False,
        "checkout_seq": 0,
        "promo": None,
        "purchased": [],
    }


def new_world(seed: int, num_customers: int, profile: str) -> dict[str, object]:
    """새 세계. 생성 config 를 처음 쓰는 프로세스라면 매듭표를 만들고(`traits.tables`) 캐시한다.

    Raises:
        genconfig.ConfigError: 생성 config 를 읽을 수 없거나 계약을 어겼다.
    """
    config = genconfig.active()
    start_ms, lifetime_ms = _profile_settings(profile)
    customers = []
    for index in range(num_customers):
        cid = customer_id(index)
        persona_id, hidden_traits = persona.generate(seed, cid, config)
        signup_ms = start_ms + persona.signup_day(seed, cid, persona_id, config) * clock.DAY_MS
        customers.append(_new_customer(cid, signup_ms, persona_id, hidden_traits))
    return {
        "format_version": FORMAT_VERSION,
        "simulator_version": SIMULATOR_VERSION,
        "rng_scheme": RNG_SCHEME,
        "generation": _generation(config),
        "world_id": world_id(seed, num_customers, profile, start_ms, config.digest),
        "seed": seed,
        "num_customers": num_customers,
        "profile": profile,
        "calendar_start_ms": start_ms,
        "cart_lifetime_ms": lifetime_ms,
        "now_ms": start_ms,
        "queue": [],
        "catalog": _catalog(),
        "orders": [],
        "customers": customers,
    }


# 열쇠에 config 다이제스트가 있어야 config 를 바꾼 같은 프로세스가 옛 기준값을 돌려주지 않는다.
_INITIAL_DIGESTS: dict[tuple[int, int, str, str], str] = {}


def initial_digest(seed: int, num_customers: int, profile: str) -> str:
    key = (seed, num_customers, profile, genconfig.active().digest)
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
    config = genconfig.active()
    expected_generation = _generation(config)
    if world.get("generation") != expected_generation:
        # 판 이름이 같고 내용만 다른 경우도 가려지게 다이제스트 앞 12자를 함께 싣는다.
        raise GenerationMismatch(
            f"generation 이 다르다 — 이 상태를 만든 생성 config 와 현재 config 가 다르다 "
            f"(기대 {_label(expected_generation)}, 발견 {_label(world.get('generation'))})"
        )
    _validate(world, config)
    world["queue"] = [tuple(item) for item in world["queue"]]
    return world


def _label(generation: object) -> str:
    if not isinstance(generation, dict):
        return repr(generation)[:40]
    digest_text = generation.get("config_digest")
    prefix = digest_text[:12] if isinstance(digest_text, str) else repr(digest_text)[:12]
    return f"{str(generation.get('config_version'))[:40]}·{prefix}"


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
            f"모르는 키 {_shown(set(value) - expected)} · 없는 키 {_shown(expected - set(value))}",
        )
    return value


def _shown(keys: set[str]) -> list[str]:
    return sorted("<숨은 필드>" if key in _HIDDEN_KEYS else key for key in keys)


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


def _validate(world: dict[str, object], config: genconfig.GenerationConfig) -> None:
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
    if world["world_id"] != world_id(seed, count, profile, start_ms, config.digest):
        raise _fail("world_id", "seed·num_customers·profile·생성 config 에서 유도한 값과 다르다")
    now = _int("now_ms", world["now_ms"], start_ms, MAX_TIME_MS)
    if (now - start_ms) % clock.DAY_MS:
        raise _fail("now_ms", "KST 자정이 아니다")
    if world["catalog"] != _catalog():
        raise _fail("catalog", "이 판의 카탈로그와 다르다")
    if _list("orders", world["orders"]):
        raise _fail("orders", "주문은 상태가 아니라 실행마다 교환 기록으로 남긴다 — 상태에는 비어 있어야 한다")
    customers = _list("customers", world["customers"])
    if len(customers) != count:
        raise _fail("customers", f"{len(customers)}명인데 num_customers 는 {count}")
    identity = _Identity(config)
    next_seqs = [
        _validate_customer(index, item, now, identity) for index, item in enumerate(customers)
    ]
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
        if kind == "treat" and not customers[index]["assignments"]:
            raise _fail(where, "배정 없는 노출 항목")


class _Identity:
    """페르소나·Trait 검사 기준. Trait 은 다시 생성하지 않는다 — `advance` 마다 도는 검사라서다.

    값이 그 페르소나 매듭표의 [Q[0], Q[K]] 안인지만 본다. 범위 안의 위조는 계보(초기 다이제스트)가 잡는다.
    """

    def __init__(self, config: genconfig.GenerationConfig) -> None:
        self.personas = frozenset(config.persona_ids)
        self.trait_names = frozenset(config.trait_names)
        # 오류 메시지는 Trait 을 이름 대신 config 순번(docs/persona_spec.md 3절 번호)으로 가리킨다.
        self.ordered = tuple(enumerate(config.trait_names, start=1))
        self.tables = traits.tables(config)
        self.product_ids = frozenset(p.product_id for p in params.active().catalog)

    def check(self, where: str, persona_id: object, values: object) -> None:
        # 위치와 사유만 남긴다 — 숨은 필드 이름·페르소나 id·Trait 값은 싣지 않는다.
        if not isinstance(persona_id, str) or persona_id not in self.personas:
            raise _fail(where, "페르소나가 생성 config 에 없는 값이다")
        if not isinstance(values, dict):
            raise _fail(where, "Trait 묶음이 객체가 아니다")
        if set(values) != self.trait_names:
            raise _fail(where, "Trait 이름 집합이 생성 config 와 다르다")
        for number, name in self.ordered:
            value = values[name]
            table = self.tables[name][persona_id]
            if isinstance(value, bool) or not isinstance(value, int):
                raise _fail(where, f"Trait #{number} 값이 정수가 아니다")
            if not table.lo <= value <= table.hi:
                raise _fail(where, f"Trait #{number} 값이 그 페르소나가 낼 수 있는 범위 밖이다")


def _validate_customer(index: int, value: object, now: int, identity: _Identity) -> int:
    where = f"customers[{index}]"
    product_ids = identity.product_ids
    customer = _keys(where, value, _CUSTOMER_KEYS)
    if customer["customer_id"] != customer_id(index):
        raise _fail(where, f"고객 ID 가 순번과 다르다: {customer['customer_id']!r}")
    _int(f"{where}.signup_ms", customer["signup_ms"], 0, MAX_TIME_MS)
    if customer["lifecycle"] != "active":
        raise _fail(where, f"모르는 lifecycle: {customer['lifecycle']!r}")
    identity.check(where, customer["persona"], customer["hidden_traits"])
    cart = customer["cart"]
    if not isinstance(cart, dict):
        raise _fail(f"{where}.cart", "객체가 아니다")
    for pid in sorted(cart):
        if pid not in product_ids:
            raise _fail(f"{where}.cart", f"카탈로그에 없는 상품: {pid!r}")
        item = _keys(f"{where}.cart.{pid}", cart[pid], _CART_KEYS)
        _int(f"{where}.cart.{pid}.quantity", item["quantity"], 1, MAX_QUANTITY)
        _int(f"{where}.cart.{pid}.last_change_ms", item["last_change_ms"], 0, now)
        _int(f"{where}.cart.{pid}.unit_price", item["unit_price"], 0)
    views = _list(f"{where}.recent_views", customer["recent_views"])
    if len(views) > behavior.RECENT_VIEWS_CAP:
        raise _fail(f"{where}.recent_views", f"{len(views)}건 — 상한을 넘는다")
    for view in views:
        if not isinstance(view, list) or len(view) != 2 or view[1] not in product_ids:
            raise _fail(f"{where}.recent_views", f"[time_ms, product_id] 가 아니다: {view!r}")
        _int(f"{where}.recent_views", view[0], 0, now)
    session = customer["session"]
    if session is not None:
        session = _keys(f"{where}.session", session, _SESSION_KEYS)
        # 고정 패턴 + 그룹 대조. 고객마다 패턴 문자열을 만들면 re 캐시(512)를 넘어 매번 컴파일된다.
        matched = (
            _SESSION_ID.fullmatch(session["session_id"])
            if isinstance(session["session_id"], str) else None
        )
        if matched is None or matched.group(1) != customer["customer_id"]:
            raise _fail(f"{where}.session", f"session_id 형식 위반: {session['session_id']!r}")
        _int(f"{where}.session.start_ms", session["start_ms"], 0, MAX_TIME_MS)
        _int(f"{where}.session.last_activity_ms", session["last_activity_ms"], 0, MAX_TIME_MS)
        _int(f"{where}.session.actions", session["actions"], 0)
        if not isinstance(session["open"], bool):
            raise _fail(f"{where}.session.open", "bool 이 아니다")
        _int(f"{where}.session.intent", session["intent"], 0)
        if session["stage"] not in _SESSION_STAGES:
            raise _fail(f"{where}.session.stage", f"모르는 단계: {session['stage']!r}")
        if session["order"] is not None and not isinstance(session["order"], dict):
            raise _fail(f"{where}.session.order", "객체가 아니다")
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
    _int(f"{where}.engagement", customer["engagement"], 0, params.PPM)
    if not isinstance(customer["churning"], bool):
        raise _fail(f"{where}.churning", "bool 이 아니다")
    # 숨은 필드라 이름을 싣지 않는다. 표시는 이탈 진행 중에만 켜질 수 있다.
    if not isinstance(customer["gate_churning"], bool) or (customer["gate_churning"] and not customer["churning"]):
        raise _fail(where, "숨은 필드가 bool 이 아니거나 이탈 진행 상태와 어긋난다")
    _int(f"{where}.checkout_seq", customer["checkout_seq"], 0, 999_999)
    purchased = _list(f"{where}.purchased", customer["purchased"])
    if len(purchased) > params.active().recent_purchases_cap or any(p not in product_ids for p in purchased):
        raise _fail(f"{where}.purchased", "상한을 넘거나 카탈로그에 없는 상품이 있다")
    promo = customer["promo"]
    if promo is not None:
        promo = _keys(f"{where}.promo", promo, _PROMO_KEYS)
        if not isinstance(promo["treatment_id"], str) or not _TREATMENT_ID.fullmatch(promo["treatment_id"]):
            raise _fail(f"{where}.promo", "처치 ID 형식 위반")
        _int(f"{where}.promo.at_ms", promo["at_ms"], 0, now)
        for flag in ("claim", "clicked", "used"):
            if not isinstance(promo[flag], bool):
                raise _fail(f"{where}.promo.{flag}", "bool 이 아니다")
    return _int(f"{where}.next_seq", customer["next_seq"], 0)
