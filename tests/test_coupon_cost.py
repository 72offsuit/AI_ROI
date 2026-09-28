"""Pins where the coupon cost comes from, order by order (issue #108).

`coupon_cost()` used to derive the discount from treatment unit prices only
(decision D-16: Σ treatment_cost[t] for t in the order's T2/T3 treatments).
Commerce coupons are operating campaigns, not AI treatments, so commerce orders
carry no `treatment_id`. The derivation found nothing and published **0 KRW as
`ok`** -- on the real commerce sample the actual discount was 6,910 KRW. The ROI
denominator (`marketing_cost`) silently shrank.

The rule now, per coupon-used order, decided by what data exists (not by source):

  observed  the exchange file carries the actual discount  -> that value
  derived   a coupon treatment (T2/T3) applies              -> D-16
  neither   coupon_use exists but no basis                  -> unavailable, never 0

Recorded in `docs/decisions/DR-108-coupon-cost-basis.md`.
"""

from __future__ import annotations

import json
import unittest
from pathlib import Path

from src.measurement import economics as ec
from src.measurement import exchange as ex
from src.measurement import publish as pub
from src.measurement.kpi import MetricStatus
from src.measurement.schema import ReasonCode
from tests.test_economics import fixture_config

SAMPLE = Path(__file__).resolve().parent / "fixtures" / "commerce_exchange_v1"


def campaign(*orders: ec.OrderView) -> ec.CampaignView:
    return ec.CampaignView("CMP-20260928-001", coupon_used_orders=orders)


def commerce_order(order_id: str = "O1", **overrides: object) -> ec.OrderView:
    """커머스 모양 — 쿠폰은 썼고 처치 ID 는 없다."""
    fields: dict[str, object] = {
        "order_id": order_id, "order_amount": 14_130, "has_coupon_use": True,
    }
    fields.update(overrides)
    return ec.OrderView(**fields)  # type: ignore[arg-type]


class TestNoBasisIsNotZero(unittest.TestCase):
    """★★ #108 의 모양 그대로다."""

    def test_coupon_used_without_discount_or_treatment_is_unavailable(self) -> None:
        result = ec.coupon_cost(campaign(commerce_order()), config=fixture_config())
        self.assertIs(MetricStatus.UNAVAILABLE, result.status)
        self.assertIsNone(result.value, "값이 붙으면 0 채우기와 같다")
        self.assertIs(ReasonCode.MISSING_FIELD, result.reason_code)
        self.assertEqual(
            ["discount"], [b.ref for b in (result.blocked_by or ())],
            "무엇이 있어야 풀리는지 이름으로 말해야 한다",
        )

    def test_marketing_cost_does_not_publish_a_partial_sum(self) -> None:
        """분모에서 쿠폰만 빠진 합계를 전체처럼 게시하지 않는다."""
        result = ec.marketing_cost(campaign(commerce_order()), config=fixture_config())
        self.assertIs(MetricStatus.UNAVAILABLE, result.status)

    def test_unused_coupon_is_still_not_incurred(self) -> None:
        """쿠폰을 안 쓴 주문은 근거가 없어도 문제가 아니다 — 비용이 발생하지 않았다."""
        result = ec.coupon_cost(
            campaign(commerce_order(has_coupon_use=False)), config=fixture_config()
        )
        self.assertIs(MetricStatus.OK, result.status, result.reason_detail)
        self.assertEqual(0, result.value)


class TestObservedDiscountIsUsed(unittest.TestCase):
    def test_observed_discount_without_treatment(self) -> None:
        result = ec.coupon_cost(
            campaign(commerce_order(discount=1_570)), config=fixture_config()
        )
        self.assertIs(MetricStatus.OK, result.status, result.reason_detail)
        self.assertEqual(1_570, result.value)
        self.assertFalse(result.derived, "관측값을 유도값으로 표시하지 않는다")

    def test_observed_discount_wins_over_the_treatment_price(self) -> None:
        """T3 단가(7,000)가 아니라 실제로 깎아 준 금액을 쓴다."""
        order = commerce_order(discount=1_570, treatment_ids=("T3",))
        result = ec.coupon_cost(campaign(order), config=fixture_config())
        self.assertEqual(1_570, result.value)

    def test_mixed_sum_is_marked_derived(self) -> None:
        observed = commerce_order("O1", discount=1_570)
        simulated = commerce_order("O2", treatment_ids=("T3",))
        result = ec.coupon_cost(campaign(observed, simulated), config=fixture_config())
        self.assertEqual(1_570 + 7_000, result.value)
        self.assertTrue(result.derived)
        self.assertIn("관측 1건", result.derivation or "")

    def test_simulator_orders_are_unchanged(self) -> None:
        """★ 거짓 양성 — 처치 ID 가 있고 교환 파일이 없는 주문은 전과 같아야 한다."""
        order = commerce_order(treatment_ids=("T2",))
        result = ec.coupon_cost(campaign(order), config=fixture_config())
        self.assertEqual(3_000, result.value)
        self.assertTrue(result.derived)


class TestTheRealCommerceSample(unittest.TestCase):
    """실제 커머스 표본 — 쿠폰 주문 2건, 실제 할인 합계 6,910원."""

    def setUp(self) -> None:
        self.events = [
            json.loads(line)
            for line in (SAMPLE / "events.jsonl").read_text(encoding="utf-8").splitlines()
        ]
        self.exchange = ex.read_exchange(SAMPLE / "exchange")
        assert self.exchange is not None
        self.discounts = sum(o.discount for o in self.exchange.orders.values())
        self.commerce = json.loads((SAMPLE / "contribution.json").read_text(encoding="utf-8"))

    def test_the_sample_really_has_discounts(self) -> None:
        """★ 이것이 0 이면 아래 검사가 전부 공허하다."""
        self.assertEqual(self.commerce["couponDiscountKrw"], self.discounts)
        self.assertGreater(self.discounts, 0)

    def test_with_the_exchange_the_actual_discount_is_charged(self) -> None:
        result = ec.coupon_cost(
            pub.assemble_campaign(self.events, self.exchange), config=fixture_config()
        )
        self.assertIs(MetricStatus.OK, result.status, result.reason_detail)
        self.assertEqual(self.discounts, result.value)
        self.assertFalse(result.derived)

    def test_without_the_exchange_it_is_unavailable_not_zero(self) -> None:
        """★★ 수정 전에는 여기서 0 · ok 가 나왔다."""
        result = ec.coupon_cost(
            pub.assemble_campaign(self.events, None), config=fixture_config()
        )
        self.assertIs(MetricStatus.UNAVAILABLE, result.status)
        self.assertIsNone(result.value)

    def test_marketing_cost_includes_the_discount(self) -> None:
        view = pub.assemble_campaign(self.events, self.exchange)
        config = fixture_config()
        marketing = ec.marketing_cost(view, config=config)
        fixed = ec.campaign_fixed_cost(view, config=config)
        message = ec.message_cost(view, config=config)
        self.assertIs(MetricStatus.OK, marketing.status, marketing.reason_detail)
        self.assertEqual(
            float(fixed.value) + float(message.value) + self.discounts,  # type: ignore[arg-type]
            marketing.value,
        )
