"""Pins that a coupon discount is deducted exactly once (issue #101).

Reported from the commerce side. The contract defines `order_amount` as
`Σ(unit_price × quantity) − discount` -- **post-discount** -- and `revenue` sums
it. `contribution_profit` then subtracted `coupon_cost` on top, so the same
discount came off twice.

The reporter's worked example: subtotal 15,700, discount 1,570, so
`order_amount` = 14,130. With COGS 11,000 the contribution is 3,130; the old code
produced 1,560.

★ A second problem, not in the report, turned out to matter more for the choice
  of fix: `coupon_cost()` does not use the actual discount. It derives one from
  `treatment_cost` (decision D-16: T2=3,000, T3=7,000). So on a commerce order
  discounted by 1,570 it subtracted 3,000 or 7,000 -- **double-counted and the
  wrong amount.** Gross-revenue accounting would have had to reconstruct revenue
  from that derived figure and would disagree with commerce; net revenue uses the
  real discount already inside `order_amount`, so the two agree by construction.
  Recorded in `docs/decisions/DR-101-revenue-basis.md`.

★ The coupon is still charged -- `marketing_cost()` keeps it as the ROI
  denominator. That is not the same deduction: the numerator already carries the
  discount as reduced revenue, and the denominator is what was spent. Dropping it
  from both would be the opposite error, so `test_coupon_is_still_marketing_cost`
  guards that side.

This was latent when it was found: `cogs()` returns `NO_COST_BASIS` without an
`order_items` table, so `contribution_profit` was almost always `unavailable` and
no wrong number was being published. It goes live the moment issue #100 supplies
real item costs -- which is why this had to land first.
"""

from __future__ import annotations

import unittest

from src.measurement import economics as ec
from src.measurement.kpi import MetricStatus
from tests.test_economics import fixture_config

#: 제보의 주문 그대로. 소계 15,700 · 할인 1,570 · 실제 결제 14,130.
SUBTOTAL = 15_700
DISCOUNT = 1_570
ORDER_AMOUNT = SUBTOTAL - DISCOUNT
UNIT_COST = 11_000


def discounted_order() -> ec.OrderView:
    """T3(7,000원 쿠폰)이 적용되고 실제로 사용된 주문."""
    return ec.OrderView(
        order_id="O00000001-000001",
        order_amount=ORDER_AMOUNT,
        items=(ec.OrderItem("P0001", 1, SUBTOTAL, unit_cost=UNIT_COST),),
        treatment_ids=("T3",),
        has_coupon_use=True,
    )


class TestDiscountIsDeductedExactlyOnce(unittest.TestCase):
    """★ 제보의 숫자를 그대로 고정한다."""

    def setUp(self) -> None:
        self.config = fixture_config()
        self.order = discounted_order()
        self.campaign = ec.CampaignView(
            campaign_id="CMP-1",
            messages_sent=0,
            targeted_customers=0,
            campaigns_run=0,
            coupon_used_orders=(self.order,),
        )

    def test_contribution_profit_is_revenue_minus_cogs(self) -> None:
        result = ec.contribution_profit(
            (self.order,), self.campaign, config=self.config
        )
        self.assertIs(MetricStatus.OK, result.status, result.reason_detail)
        self.assertEqual(
            float(ORDER_AMOUNT - UNIT_COST), result.value,
            "할인이 두 번 빠졌다. order_amount 는 이미 할인 후 금액이다",
        )

    def test_the_old_wrong_answer_is_not_produced(self) -> None:
        """★ 동일성만 보면 둘 다 틀려도 통과한다. 옛 값을 명시적으로 배제한다."""
        result = ec.contribution_profit(
            (self.order,), self.campaign, config=self.config
        )
        old_wrong = float(ORDER_AMOUNT - UNIT_COST - 7_000)
        self.assertNotEqual(
            old_wrong, result.value,
            "T3 유도값 7,000 이 매출에서 또 빠졌다 — 중복 차감이 돌아왔다",
        )

    def test_coupon_is_not_a_source_event_of_contribution_profit(self) -> None:
        """할인을 계상하지 않으므로 `coupon_use` 는 더는 이 지표의 근거가 아니다."""
        result = ec.contribution_profit(
            (self.order,), self.campaign, config=self.config
        )
        self.assertNotIn("coupon_use", result.basis.source_event_types)

    def test_undiscounted_order_is_unaffected(self) -> None:
        """★ 거짓 양성 — 할인 없는 주문에서 값이 달라지면 그것도 결함이다."""
        plain = ec.OrderView(
            order_id="O00000002-000001",
            order_amount=SUBTOTAL,
            items=(ec.OrderItem("P0001", 1, SUBTOTAL, unit_cost=UNIT_COST),),
        )
        campaign = ec.CampaignView(campaign_id="CMP-2", campaigns_run=0)
        result = ec.contribution_profit((plain,), campaign, config=self.config)
        self.assertIs(MetricStatus.OK, result.status, result.reason_detail)
        self.assertEqual(float(SUBTOTAL - UNIT_COST), result.value)


class TestCouponStaysInTheRoiDenominator(unittest.TestCase):
    """★ 반대 방향의 실수 — 분모에서도 빼 버리면 ROI 가 과대평가된다."""

    def test_coupon_is_still_marketing_cost(self) -> None:
        order = discounted_order()
        campaign = ec.CampaignView(
            campaign_id="CMP-1", messages_sent=1, targeted_customers=1,
            coupon_used_orders=(order,),
        )
        config = fixture_config()
        coupon = ec.coupon_cost(campaign, config=config)
        marketing = ec.marketing_cost(campaign, config=config)
        self.assertIs(MetricStatus.OK, coupon.status, coupon.reason_detail)
        self.assertIs(MetricStatus.OK, marketing.status, marketing.reason_detail)
        self.assertGreaterEqual(
            float(marketing.value), float(coupon.value),
            "쿠폰 비용이 마케팅 비용에서 사라졌다 — 지출한 돈이 분모에서 빠지면 "
            "ROI 가 과대평가된다",
        )
