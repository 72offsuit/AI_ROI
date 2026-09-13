"""경제 규칙 계산 검사 — `ECONOMIC RULE v1` (이슈 #47).

**PyYAML 없이 전부 돈다.** `economics.py` 가 dataclass 를 인자로 받으므로 config 를
파일에서 읽을 필요가 없고, 그래서 의존성 미설치 CI 에서도 이 파일이 통과한다
(가정 A7 사슬의 첫 고리). 픽스처 config 를 손으로 만드는 것이 그 대가다 — 의도한
거래다.

★ 이 파일이 지키는 것 하나를 먼저 적는다: **`cogs` 가 `0` 을 돌려주지 않는다.**
`0` 이면 기여이익 = 매출이 되고, USP-1 전체가 끝난다.

실행:
    python3 -m unittest tests.test_economics -v
"""

from __future__ import annotations

import unittest

from src.measurement import economics as ec
from src.measurement.config_loader import AiInvestmentConfig, CostAccountingConfig
from src.measurement.schema import MetricStatus, ReasonCode, Unit


def fixture_config(**overrides: object) -> CostAccountingConfig:
    """`config/economic_config.yaml` 과 같은 값의 픽스처.

    파일을 읽지 않는다 — PyYAML 없이 돌아야 하기 때문이다. 값이 config 와 어긋나도
    이 파일의 테스트는 통과하지만, 그것이 문제가 되지 않는다: 여기서 검사하는 것은
    **계산 규칙**이고 값의 정합성은 `test_config_loader.py` 가 본다.
    """
    defaults: dict[str, object] = {
        "treatment_cost": {"T0": 0, "T1": 3000, "T2": 3000, "T3": 7000, "T4": 30},
        "treatment_occurs_at": {
            "T0": "none", "T1": "order_placed", "T2": "coupon_used",
            "T3": "coupon_used", "T4": "message_sent",
        },
        "coupon_treatments": ("T2", "T3"),
        "message_cost_krw": 30,
        "campaign_fixed_cost_krw": 100000,
        "discount_cost_krw": 7000,
        "shipping_fee_krw": 3000,
        "free_shipping_threshold_krw": 40000,
        "ai_investment": AiInvestmentConfig(
            model_development_cost_krw=12000000,
            compute_cost_krw=600000,
            model_operating_cost_krw_per_month=300000,
            monitoring_cost_krw_per_month=200000,
            amortization_months=12,
            is_estimate=True,
            estimate_note="가정 기반 추정치다",
        ),
        "assumptions": {"refund_adjusted": False},
    }
    defaults.update(overrides)
    return CostAccountingConfig(**defaults)  # type: ignore[arg-type]


class TestCostBasis(unittest.TestCase):
    """EC-2 — 가르는 기준은 출처가 아니라 `has_cost_basis(order)` 다."""

    def test_all_items_have_unit_cost(self) -> None:
        order = ec.OrderView(
            "O20251001-000123", 47000,
            (ec.OrderItem("P0042", 2, 8900, 6942), ec.OrderItem("P0043", 1, 6500, 4550)),
        )
        self.assertTrue(ec.has_cost_basis(order))

    def test_some_items_missing_unit_cost(self) -> None:
        order = ec.OrderView(
            "O20251001-000123", 47000,
            (ec.OrderItem("P0042", 2, 8900, 6942), ec.OrderItem("P0043", 1, 6500, None)),
        )
        self.assertFalse(ec.has_cost_basis(order))

    def test_empty_items_is_not_cost_basis(self) -> None:
        """★ C1 의 정상 경로다. 공허참을 참으로 쓰면 COGS 가 0 원이 된다."""
        self.assertFalse(ec.has_cost_basis(ec.OrderView("O20251001-000123", 47000)))


class TestCogs(unittest.TestCase):
    """EC-1 — 저장된 `unit_cost` 로만 계산한다. 추정하지 않는다."""

    def test_cogs_sums_stored_unit_cost(self) -> None:
        order = ec.OrderView(
            "O20251001-000123", 47000,
            (ec.OrderItem("P0042", 2, 8900, 6942), ec.OrderItem("P0043", 1, 6500, 4550)),
        )
        result = ec.cogs(order)
        self.assertIs(MetricStatus.OK, result.status)
        self.assertEqual(6942 * 2 + 4550, result.value)
        self.assertIsNotNone(result.basis)

    def test_cogs_without_basis_is_unavailable(self) -> None:
        result = ec.cogs(ec.OrderView("O20251001-000123", 47000))
        self.assertIs(MetricStatus.UNAVAILABLE, result.status)
        self.assertIs(ReasonCode.NO_COST_BASIS, result.reason_code)

    def test_cogs_never_returns_zero(self) -> None:
        """★★ 이 프로젝트의 핵심 회귀 테스트.

        `0` 을 돌려주면 기여이익 = 매출이 되고, `revenue_up_profit_down` 가드레일이
        원리적으로 발동할 수 없게 된다. 값이 `None` 이어야 한다 — `0` 이 아니다.
        """
        for order in (
            ec.OrderView("O20251001-000123", 47000),
            ec.OrderView("O20251001-000124", 47000, (ec.OrderItem("P1", 1, 8900, None),)),
        ):
            with self.subTest(order=order.order_id):
                result = ec.cogs(order)
                self.assertIsNone(result.value)
                self.assertNotEqual(0, result.value)
                self.assertIsNone(result.basis, "계산 불가는 basis 를 가질 수 없다")

    def test_cogs_is_not_a_multiple_of_order_amount(self) -> None:
        """추정 COGS 를 넣었는지 확인한다 — 넣으면 매출의 상수배가 된다."""
        cheap = ec.OrderView("O1", 10000, (ec.OrderItem("P1", 1, 10000, 500),))
        dear = ec.OrderView("O2", 10000, (ec.OrderItem("P2", 1, 10000, 9500),))
        self.assertNotEqual(ec.cogs(cheap).value, ec.cogs(dear).value)

    def test_missing_items_and_missing_cost_give_different_detail(self) -> None:
        """같은 `NO_COST_BASIS` 라도 해소 방법이 다르므로 사유가 달라야 한다."""
        no_items = ec.cogs(ec.OrderView("O1", 1000))
        no_cost = ec.cogs(ec.OrderView("O1", 1000, (ec.OrderItem("P1", 1, 1000, None),)))
        self.assertNotEqual(no_items.reason_detail, no_cost.reason_detail)
        self.assertNotEqual(
            no_items.blocked_by[0].kind, no_cost.blocked_by[0].kind
        )


class TestRevenue(unittest.TestCase):
    def test_revenue_ignores_cost_basis(self) -> None:
        """매출은 원가 유무와 무관하다 — 원가가 없어도 계산된다."""
        orders = (ec.OrderView("O1", 47000), ec.OrderView("O2", 12000))
        result = ec.revenue(orders)
        self.assertIs(MetricStatus.OK, result.status)
        self.assertEqual(59000, result.value)

    def test_zero_orders_is_not_zero_revenue(self) -> None:
        """★★ m-04 AC-4 · T-6 — 근거 없음을 0원으로 적지 않는다.

        1차 구현이 `ok`+0 을 냈다. m-03 이 이 경우를 규정하지 않았고 m-04 가
        `unavailable`+`NO_SOURCE_EVENT` 를 명시하므로 m-04 를 정본으로 따랐다.
        오늘 커머스는 이벤트를 0건 기록하므로 "매출 0원"이 아니라 "알 수 없음"이다.
        """
        result = ec.revenue(())
        self.assertIs(MetricStatus.UNAVAILABLE, result.status)
        self.assertIsNone(result.value)
        self.assertIs(ReasonCode.NO_SOURCE_EVENT, result.reason_code)
        self.assertIsNone(result.basis, "계산 불가는 basis 를 가질 수 없다")

    def test_observed_order_summing_to_zero_is_a_measured_zero(self) -> None:
        """★ 반대쪽 경계 — 관측했고 합이 0 이면 `ok` + 0 이다.

        위 테스트와 짝이다. 둘을 함께 보지 않으면 "0건이면 계산 불가" 를
        "합이 0 이면 계산 불가" 로 넓히는 실수를 잡을 수 없다.
        """
        result = ec.revenue((ec.OrderView("O1", 0),))
        self.assertIs(MetricStatus.OK, result.status)
        self.assertEqual(0, result.value)
        self.assertIsNotNone(result.basis, "측정된 0 에는 기준이 있다")
        self.assertEqual(1, result.basis.observed_count)  # type: ignore[union-attr]


class TestAccrual(unittest.TestCase):
    """EC-3 발생주의 3원칙."""

    def test_message_cost_charges_everyone_sent(self) -> None:
        """반응 무관 전원 계상. 역효과 고객 비용도 지우지 않는다."""
        campaign = ec.CampaignView("CMP-20251001-001", messages_sent=1000)
        result = ec.message_cost(campaign, config=fixture_config())
        self.assertEqual(1000 * 30, result.value)

    def test_coupon_cost_only_counts_used_coupons(self) -> None:
        used = ec.OrderView("O1", 60000, treatment_ids=("T3",), has_coupon_use=True)
        unused = ec.OrderView("O2", 20000, treatment_ids=("T3",), has_coupon_use=False)
        campaign = ec.CampaignView(
            "CMP-20251001-001", coupon_used_orders=(used, unused)
        )
        result = ec.coupon_cost(campaign, config=fixture_config())
        self.assertEqual(7000, result.value, "사용된 쿠폰 1건만 계상해야 한다")
        self.assertTrue(result.derived)
        self.assertIsNotNone(result.derivation, "유도값은 계산식을 함께 싣는다")

    def test_below_minimum_charges_message_only(self) -> None:
        """최소주문금액 미달 → 메시지 비용만. 할인은 0 이 아니라 발생하지 않는다."""
        config = fixture_config()
        unused = ec.OrderView("O2", 20000, treatment_ids=("T3",), has_coupon_use=False)
        campaign = ec.CampaignView(
            "CMP-20251001-001", messages_sent=1, coupon_used_orders=(unused,)
        )
        self.assertEqual(30, ec.message_cost(campaign, config=config).value)
        self.assertEqual(0, ec.coupon_cost(campaign, config=config).value)

    def test_unknown_treatment_is_not_free(self) -> None:
        """config 에 없는 처치를 0 원으로 읽지 않는다."""
        order = ec.OrderView("O1", 60000, treatment_ids=("T9",), has_coupon_use=True)
        campaign = ec.CampaignView("CMP-1", coupon_used_orders=(order,))
        config = fixture_config(coupon_treatments=("T2", "T3", "T9"))
        result = ec.coupon_cost(campaign, config=config)
        self.assertIs(MetricStatus.UNAVAILABLE, result.status)
        self.assertIs(ReasonCode.PRECONDITION_MISSING, result.reason_code)


class TestNTargeted(unittest.TestCase):
    """EC-4 — 발송된 고객 수다. 배정 인원도 반응 인원도 아니다."""

    def test_n_targeted_counts_sent_customers(self) -> None:
        campaign = ec.CampaignView("CMP-1", messages_sent=1200, targeted_customers=1000)
        self.assertEqual(1000, ec.n_targeted(campaign).value)

    def test_zero_n_targeted_does_not_divide(self) -> None:
        """★ 오늘이 정확히 0 건이다. 나누면 inf 나 0 이 게시물까지 간다."""
        campaign = ec.CampaignView("CMP-1", targeted_customers=0)
        result = ec.campaign_fixed_cost_per_customer(campaign, config=fixture_config())
        self.assertIs(MetricStatus.UNAVAILABLE, result.status)
        self.assertIsNone(result.value)
        self.assertIn("100,000", result.reason_detail or "", "고정비 총액은 남겨야 한다")

    def test_nonzero_n_targeted_divides_and_records_denominator(self) -> None:
        campaign = ec.CampaignView("CMP-1", targeted_customers=1000)
        result = ec.campaign_fixed_cost_per_customer(campaign, config=fixture_config())
        self.assertIs(MetricStatus.OK, result.status)
        self.assertEqual(100.0, result.value)
        self.assertEqual(1000, result.basis.denominator)  # type: ignore[union-attr]


class TestPlannedVersusRealized(unittest.TestCase):
    """EC-5 — 계획값과 실현값은 다른 이름이다."""

    def test_expected_and_realized_are_distinct_callables(self) -> None:
        self.assertIsNot(ec.expected_cost_per_customer, ec.realized_cost_per_customer)

    def test_expected_cost_is_unconfirmed_with_params(self) -> None:
        """계획값은 미확정 파라미터를 쓰므로 그것을 함께 싣는다."""
        result = ec.expected_cost_per_customer(
            config=fixture_config(), coupon_use_rate=0.30, treatment_id="T3"
        )
        self.assertIs(MetricStatus.UNCONFIRMED, result.status)
        self.assertAlmostEqual(30 + 0.30 * 7000, float(result.value))  # type: ignore[arg-type]
        self.assertIn("coupon_use_rate", result.params_used or {})

    def test_realized_cost_blocks_when_no_targets(self) -> None:
        campaign = ec.CampaignView("CMP-1", targeted_customers=0)
        result = ec.realized_cost_per_customer(campaign, config=fixture_config())
        self.assertIs(MetricStatus.UNAVAILABLE, result.status)
        self.assertIsNone(result.value)


class TestContributionProfit(unittest.TestCase):
    def test_profit_is_unavailable_when_cogs_missing(self) -> None:
        """C1 의 실제 경로. 여섯 항목 중 셋이 계산 불가다."""
        orders = (ec.OrderView("O1", 47000),)
        campaign = ec.CampaignView("CMP-1", messages_sent=10, targeted_customers=10)
        result = ec.contribution_profit(orders, campaign, config=fixture_config())
        self.assertIs(MetricStatus.UNAVAILABLE, result.status)
        self.assertIsNone(result.value)
        self.assertIs(ReasonCode.NO_COST_BASIS, result.reason_code)

    def test_blocked_by_names_the_real_cause(self) -> None:
        """화면이 결손→영향 사슬을 추론하지 않게 한다 (DB-012)."""
        orders = (ec.OrderView("O1", 47000),)
        campaign = ec.CampaignView("CMP-1")
        result = ec.contribution_profit(orders, campaign, config=fixture_config())
        self.assertIn("cogs", [ref.ref for ref in result.blocked_by])

    def test_profit_computes_when_every_component_is_available(self) -> None:
        orders = (
            ec.OrderView("O1", 47000, (ec.OrderItem("P1", 2, 8900, 6942),)),
        )
        campaign = ec.CampaignView("CMP-1", messages_sent=10, targeted_customers=10)
        result = ec.contribution_profit(orders, campaign, config=fixture_config())
        self.assertIs(MetricStatus.OK, result.status)
        expected = 47000 - 6942 * 2 - 0 - 0 - 10 * 30 - 100000
        self.assertEqual(expected, result.value)

    def test_partial_sum_is_never_returned(self) -> None:
        """계산된 항목만 더하면 부분 합계가 전체처럼 보인다."""
        orders = (ec.OrderView("O1", 47000),)
        campaign = ec.CampaignView("CMP-1")
        result = ec.contribution_profit(orders, campaign, config=fixture_config())
        self.assertNotEqual(47000, result.value)
        self.assertIsNone(result.value)


class TestRoiInterpretation(unittest.TestCase):
    """EC-7 — 판정 불가를 `False`(가드레일 통과)로 만들지 않는다."""

    def _outcome(self, name: str, revenue: int, profit: int) -> ec.StrategyOutcome:
        orders = (ec.OrderView("O1", revenue, (ec.OrderItem("P1", 1, revenue, revenue - profit),)),)
        campaign = ec.CampaignView("CMP-1")
        return ec.StrategyOutcome(
            name=name,
            revenue=ec.revenue(orders),
            contribution_profit=ec.cogs(orders[0]),
        )

    def test_uncomputable_input_gives_uncomputable_verdict(self) -> None:
        """★ `False` 를 돌려주면 확인하지 않은 것이 안전하다고 보고된다."""
        blank = ec.StrategyOutcome(
            name="baseline",
            revenue=ec.revenue(()),
            contribution_profit=ec.cogs(ec.OrderView("O1", 0)),
        )
        result = ec.revenue_up_profit_down(blank, blank)
        self.assertIs(MetricStatus.UNAVAILABLE, result.status)
        self.assertIsNot(False, result.value)
        self.assertIsNone(result.value)
        self.assertIs(ReasonCode.NEEDS_TWO_STRATEGIES, result.reason_code)

    def test_guardrail_triggers_on_revenue_up_profit_down(self) -> None:
        from src.measurement.schema import Basis, Window, WindowDirection

        def money(amount: int) -> object:
            from src.measurement.schema import MetricValue
            return MetricValue.ok(
                amount, unit=Unit.KRW,
                basis=Basis("주문", "분모 없음 (합계)", Window(WindowDirection.NONE)),
            )

        strategy = ec.StrategyOutcome("strategy", money(120), money(8))  # type: ignore[arg-type]
        baseline = ec.StrategyOutcome("baseline", money(100), money(10))  # type: ignore[arg-type]
        self.assertEqual("true", ec.revenue_up_profit_down(strategy, baseline).value)
        # 반대 방향에서는 발동하지 않는다.
        self.assertEqual("false", ec.revenue_up_profit_down(baseline, strategy).value)


class TestAiInvestment(unittest.TestCase):
    def test_ai_cost_is_unconfirmed_because_inputs_are_assumptions(self) -> None:
        result = ec.ai_investment_cost(config=fixture_config(), campaign_days=42)
        self.assertIs(MetricStatus.UNCONFIRMED, result.status)
        self.assertIs(ReasonCode.PARAM_UNCONFIRMED, result.reason_code)
        # ★ 상류 문서의 산술 오류를 그대로 베끼지 않았다.
        #
        # economic-rule-v1.md §5 (그리고 story-m-03 §4.3)은 계산식과 결과를 함께
        # 적었는데 둘이 어긋난다:
        #
        #     적힌 식   (12,600,000 / 12 + 500,000) × (42/30)
        #     적힌 결과 ≈ 2,020,000원
        #     실제 값   = 1,550,000 × 1.4 = 2,170,000원        (차이 150,000원)
        #
        # 식이 정본이라고 보고 식을 구현했다. 결과값을 맞추려면 식을 바꿔야 하는데
        # 그럴 근거가 없다(2,020,000 을 내는 식을 역산할 수 없었다). 조용히 어느
        # 한쪽에 맞추지 않고 리드에게 판정을 올렸다 — backend.md 의 미결 항목 참조.
        self.assertAlmostEqual(2170000.0, float(result.value), delta=1.0)  # type: ignore[arg-type]

    def test_ai_roi_needs_two_strategies_in_c1(self) -> None:
        investment = ec.ai_investment_cost(config=fixture_config(), campaign_days=42)
        incremental = ec.cogs(ec.OrderView("O1", 0))  # 계산 불가
        result = ec.ai_roi(incremental_profit=incremental, investment=investment)
        self.assertIs(MetricStatus.UNAVAILABLE, result.status)
        self.assertIsNone(result.value)


if __name__ == "__main__":
    unittest.main()
