"""행동·이탈·처치 반응 모수(`config/simulator_config.yaml` 의 behavior·catalog·guardrails) 해석 — S4~S6(#143).

값은 모두 정수다. 키가 빠지거나 남으면 로드 단계에서 거부한다(`genconfig.parse` 가 부른다).
모수의 근거 상태: `docs/decisions/DR-143-sim-sprint.md` — 초안 값이며 외부 근거 대조는 #148 이후 조정한다.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

from src.simulator._internal import fixedpoint as fx
from src.simulator._internal import traits as _traits

PPM = 1_000_000
TREATMENTS = ("T1", "T2", "T3", "T4")
ACTIONS = ("page_view", "product_view", "add_to_cart", "remove_from_cart")


def _block(where: str, value: object, keys: frozenset[str]) -> Mapping[str, object]:
    if not isinstance(value, dict):
        raise TypeError(f"{where}: 객체가 아니다")
    if set(value) != keys:
        raise KeyError(f"{where}: 키가 다르다 — 남는 {sorted(set(value) - keys)} · 없는 {sorted(keys - set(value))}")
    return value


def _int(where: str, value: object, lo: int = 0, hi: int | None = None) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{where}: 정수가 아니다 ({value!r})")
    if value < lo or (hi is not None and value > hi):
        raise ValueError(f"{where}: 범위 [{lo}, {hi}] 밖 ({value})")
    return value


def _pair(where: str, value: object, lo: int = 0) -> tuple[int, int]:
    if not isinstance(value, list) or len(value) != 2:
        raise TypeError(f"{where}: [lo, hi) 두 정수가 아니다")
    first = _int(f"{where}[0]", value[0], lo)
    second = _int(f"{where}[1]", value[1], first + 1)
    return first, second


def _weights(where: str, value: object) -> tuple[int, ...]:
    block = _block(where, value, frozenset(ACTIONS))
    weights = tuple(_int(f"{where}.{name}", block[name]) for name in ACTIONS)
    if not any(weights):
        raise ValueError(f"{where}: 가중치 합이 0 이다")
    return weights


@dataclass(frozen=True)
class Arm:
    treatment_id: str
    sensitivity: str
    visit_boost_pct: int
    intent_boost_pct: int
    onset_protect_pct: int
    recovery_ppm: int
    coupon_discount_krw: int | None
    coupon_min_order_krw: int | None
    coupon_valid_days: int | None


@dataclass(frozen=True)
class Product:
    product_id: str
    category: str
    unit_price: int
    unit_cost: int


class Params:
    """해석된 모수. 엔진은 이 객체의 속성만 읽는다 — 딕셔너리 조회를 매 고객·일마다 하지 않게."""

    def __init__(self, config) -> None:  # GenerationConfig — 순환 import 를 피해 타입을 적지 않는다
        behavior = _block("behavior", dict(config.behavior), frozenset(
            {"visit", "session", "purchase", "churn", "treatment"}
        ))
        visit = _block("behavior.visit", behavior["visit"], frozenset({"scale_pct", "max_daily_ppm"}))
        self.visit_scale_pct = _int("visit.scale_pct", visit["scale_pct"], 1, 1000)
        self.visit_max_ppm = _int("visit.max_daily_ppm", visit["max_daily_ppm"], 1, PPM)

        session = _block("behavior.session", behavior["session"], frozenset({
            "continue_browse_ppm", "continue_intent_ppm", "max_actions_browse", "max_actions_intent",
            "action_delay_ms", "browse_weights", "intent_weights", "add_quantity",
            "browse_add_to_cart_weight_pct", "intent_trim_over_pct", "reorder_scale_pct", "recent_purchases_cap",
        }))
        self.continue_browse_ppm = _int("session.continue_browse_ppm", session["continue_browse_ppm"], 0, PPM)
        self.continue_intent_ppm = _int("session.continue_intent_ppm", session["continue_intent_ppm"], 0, PPM)
        self.max_actions_browse = _int("session.max_actions_browse", session["max_actions_browse"], 1, 1000)
        self.max_actions_intent = _int("session.max_actions_intent", session["max_actions_intent"], 1, 1000)
        self.action_delay_ms = _pair("session.action_delay_ms", session["action_delay_ms"], 1)
        self.browse_weights = _weights("session.browse_weights", session["browse_weights"])
        self.intent_weights = _weights("session.intent_weights", session["intent_weights"])
        self.add_quantity = _pair("session.add_quantity", session["add_quantity"], 1)
        # 탐색 세션의 add_to_cart 가중치(단위 1/1000) = 장바구니 이탈 성향(ppm) × 이 값(%) / 100 / 1000.
        self.browse_atc_weight_pct = _int(
            "session.browse_add_to_cart_weight_pct", session["browse_add_to_cart_weight_pct"], 0, 10_000
        )
        self.intent_trim_over_pct = _int("session.intent_trim_over_pct", session["intent_trim_over_pct"], 100, 1000)
        self.reorder_scale_pct = _int("session.reorder_scale_pct", session["reorder_scale_pct"], 0, 1000)
        self.recent_purchases_cap = _int("session.recent_purchases_cap", session["recent_purchases_cap"], 1, 1000)

        purchase = _block("behavior.purchase", behavior["purchase"], frozenset({
            "intent_scale_pct", "cycle_factor_min_ppm", "cycle_factor_max_ppm", "basket_spread_pct",
            "abandon_scale_pct", "shipping_abandon_scale_pct", "topup_max_gap_pct",
            "free_shipping_topup_scale_pct", "coupon_topup_scale_pct", "shipping_fee_krw",
            "free_shipping_threshold_krw",
        }))
        self.intent_scale_pct = _int("purchase.intent_scale_pct", purchase["intent_scale_pct"], 0, 1000)
        self.cycle_min_ppm = _int("purchase.cycle_factor_min_ppm", purchase["cycle_factor_min_ppm"], 0, 10 * PPM)
        self.cycle_max_ppm = _int(
            "purchase.cycle_factor_max_ppm", purchase["cycle_factor_max_ppm"], self.cycle_min_ppm, 10 * PPM
        )
        self.basket_spread_pct = _pair("purchase.basket_spread_pct", purchase["basket_spread_pct"], 1)
        self.abandon_scale_pct = _int("purchase.abandon_scale_pct", purchase["abandon_scale_pct"], 0, 100)
        self.shipping_abandon_scale_pct = _int(
            "purchase.shipping_abandon_scale_pct", purchase["shipping_abandon_scale_pct"], 0, 100
        )
        self.topup_max_gap_pct = _int("purchase.topup_max_gap_pct", purchase["topup_max_gap_pct"], 0, 100)
        self.free_shipping_topup_scale_pct = _int(
            "purchase.free_shipping_topup_scale_pct", purchase["free_shipping_topup_scale_pct"], 0, 100
        )
        self.coupon_topup_scale_pct = _int(
            "purchase.coupon_topup_scale_pct", purchase["coupon_topup_scale_pct"], 0, 100
        )
        self.shipping_fee_krw = _int("purchase.shipping_fee_krw", purchase["shipping_fee_krw"])
        self.free_shipping_threshold_krw = _int(
            "purchase.free_shipping_threshold_krw", purchase["free_shipping_threshold_krw"]
        )

        churn = _block("behavior.churn", behavior["churn"], frozenset({
            "onset_hazard_scale_ppm", "decay_per_day_ppm", "engagement_floor_ppm", "recovery_hazard_ppm",
        }))
        self.onset_scale_ppm = _int("churn.onset_hazard_scale_ppm", churn["onset_hazard_scale_ppm"], 0, PPM)
        self.decay_ppm = _int("churn.decay_per_day_ppm", churn["decay_per_day_ppm"], 0, PPM)
        self.engagement_floor_ppm = _int("churn.engagement_floor_ppm", churn["engagement_floor_ppm"], 0, PPM)
        self.recovery_ppm = _int("churn.recovery_hazard_ppm", churn["recovery_hazard_ppm"], 0, PPM)

        treatment = _block("behavior.treatment", behavior["treatment"], frozenset({
            "window_days", "negative_scale_pct", "positive_scale_pct", "coupon_click_scale_pct",
            "message_cost_krw", "negative_effect", "arms",
        }))
        self.window_days = _int("treatment.window_days", treatment["window_days"], 1, 3650)
        self.negative_scale_pct = _int("treatment.negative_scale_pct", treatment["negative_scale_pct"], 0, 100)
        self.positive_scale_pct = _int("treatment.positive_scale_pct", treatment["positive_scale_pct"], 0, 100)
        self.coupon_click_scale_pct = _int(
            "treatment.coupon_click_scale_pct", treatment["coupon_click_scale_pct"], 0, 100
        )
        self.message_cost_krw = _int("treatment.message_cost_krw", treatment["message_cost_krw"])
        negative = _block("treatment.negative_effect", treatment["negative_effect"], frozenset({
            "visit_penalty_pct", "intent_penalty_pct", "onset_accel_pct",
        }))
        self.negative_visit_penalty_pct = _int("negative.visit_penalty_pct", negative["visit_penalty_pct"], 0, 100)
        self.negative_intent_penalty_pct = _int(
            "negative.intent_penalty_pct", negative["intent_penalty_pct"], 0, 100
        )
        self.negative_onset_accel_pct = _int("negative.onset_accel_pct", negative["onset_accel_pct"], 0, 1000)
        arms = _block("treatment.arms", treatment["arms"], frozenset(TREATMENTS))
        trait_names = frozenset(config.trait_names)
        self.arms: dict[str, Arm] = {}
        for tid in TREATMENTS:
            where = f"arms.{tid}"
            arm = _block(where, arms[tid], frozenset({
                "sensitivity", "visit_boost_pct", "intent_boost_pct", "onset_protect_pct", "recovery_ppm",
                "coupon",
            }))
            if arm["sensitivity"] not in trait_names:
                raise ValueError(f"{where}.sensitivity: 모르는 Trait")
            coupon = arm["coupon"]
            discount = minimum = None
            if coupon is not None:
                coupon = _block(f"{where}.coupon", coupon, frozenset({"discount_krw", "min_order_krw", "valid_days"}))
                discount = _int(f"{where}.coupon.discount_krw", coupon["discount_krw"], 1)
                minimum = _int(f"{where}.coupon.min_order_krw", coupon["min_order_krw"], discount)
                valid = _int(f"{where}.coupon.valid_days", coupon["valid_days"], 1, 3650)
            self.arms[tid] = Arm(
                tid, str(arm["sensitivity"]),
                _int(f"{where}.visit_boost_pct", arm["visit_boost_pct"], 0, 1000),
                _int(f"{where}.intent_boost_pct", arm["intent_boost_pct"], 0, 1000),
                _int(f"{where}.onset_protect_pct", arm["onset_protect_pct"], 0, 100),
                _int(f"{where}.recovery_ppm", arm["recovery_ppm"], 0, PPM),
                discount, minimum, valid if coupon is not None else None,
            )

        self.catalog = _catalog(config.catalog)
        self.category_weights, self.category_pools = _pools(config.catalog, self.catalog)
        self.product_index = {product.product_id: product for product in self.catalog}

        guardrails = dict(config.guardrails)
        if guardrails:
            _block("guardrails", guardrails, frozenset({
                "note", "active_lookback_days", "churn_rate_bp", "ate_bp", "coupon_use_bp", "sleeping_dog_bp",
                "persuadable_bp",
            }))
            self.active_lookback_days = _int("guardrails.active_lookback_days", guardrails["active_lookback_days"], 1)
            self.guardrail_ranges = {
                name: _pair(f"guardrails.{name}", guardrails[name])
                for name in ("churn_rate_bp", "ate_bp", "coupon_use_bp", "sleeping_dog_bp", "persuadable_bp")
            }
        else:
            self.active_lookback_days = 42
            self.guardrail_ranges = {}


def _catalog(raw: Mapping[str, object]) -> tuple[Product, ...]:
    block = _block("catalog", dict(raw), frozenset({"note", "price_sigma_ppm", "price_round_krw", "categories"}))
    sigma = fx.from_ratio(_int("catalog.price_sigma_ppm", block["price_sigma_ppm"], 1, PPM), PPM)
    step = _int("catalog.price_round_krw", block["price_round_krw"], 1)
    categories = block["categories"]
    if not isinstance(categories, list) or not categories:
        raise TypeError("catalog.categories: 비지 않은 배열이 아니다")
    products: list[Product] = []
    for index, entry in enumerate(categories):
        where = f"catalog.categories[{index}]"
        item = _block(where, entry, frozenset(
            {"category", "cost_rate_bp", "median_price_krw", "frequency_weight_bp", "pool_size"}
        ))
        category = item["category"]
        if not isinstance(category, str):
            raise TypeError(f"{where}.category: 문자열이 아니다")
        rate = _int(f"{where}.cost_rate_bp", item["cost_rate_bp"], 0, 10_000)
        median = _int(f"{where}.median_price_krw", item["median_price_krw"], 1)
        size = _int(f"{where}.pool_size", item["pool_size"], 1, 9_999)
        for k in range(size):
            # 층화 분위 (k + ½)/size 의 LogNormal(ln 중앙값, σ) 값. 난수를 쓰지 않아 seed 와 무관하고,
            # 정수 고정소수점(fixedpoint)만 써서 플랫폼·판과 무관하게 같은 값이다.
            z = _normal_quantile(fx.from_ratio(2 * k + 1, 2 * size))
            price = fx.round_to_int(median * fx.exp(fx.mul(sigma, z)))
            price = max(step, (price + step // 2) // step * step)
            products.append(Product(
                f"P{len(products) + 1:04d}", category, price, (price * rate + 5_000) // 10_000,
            ))
    if len(products) > 9_999:
        raise ValueError("catalog: 상품이 9,999개를 넘는다 (product_id 4자리)")
    return tuple(products)


def _normal_quantile(target: int) -> int:
    """Φ(z) = target 인 z (고정소수점). 정수 Φ(`traits.normal_cdf`) 위의 이분법 — 80걸음이면 2⁻⁶⁰ 안이다."""
    lo, hi = -8 * fx.ONE, 8 * fx.ONE
    for _ in range(80):
        mid = (lo + hi) >> 1
        if _traits.normal_cdf(mid) < target:
            lo = mid
        else:
            hi = mid
    return (lo + hi) >> 1


def _pools(raw: Mapping[str, object], catalog: tuple[Product, ...]) -> tuple[tuple[int, ...], tuple[tuple[int, ...], ...]]:
    weights: list[int] = []
    pools: list[tuple[int, ...]] = []
    for index, entry in enumerate(raw["categories"]):
        weights.append(_int(f"catalog.categories[{index}].frequency_weight_bp", entry["frequency_weight_bp"], 1))
        pools.append(tuple(i for i, p in enumerate(catalog) if p.category == entry["category"]))
    return tuple(weights), tuple(pools)


_CACHE: dict[str, Params] = {}


def active() -> Params:
    from src.simulator._internal import genconfig

    config = genconfig.active()
    found = _CACHE.get(config.digest)
    if found is None:
        found = _CACHE[config.digest] = Params(config)
    return found
