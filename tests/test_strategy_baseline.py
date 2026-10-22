"""S0 무처치 · S1 Rule-based 기준선 (이슈 #145).

표준 라이브러리만 쓴다 — 의존성 없는 CI 잡에서도 돈다.
S1 규칙은 AI 결과를 보기 전에 고정했다. 이 테스트는 규칙 상수가 조용히 바뀌는 것을 잡는다.
"""

from __future__ import annotations

import doctest
import unittest

from src.decision import strategies
from src.decision.strategies import S1_RULE, plan_S0, plan_S1, s1_eligibility


class TestS0(unittest.TestCase):
    def test_no_one_is_treated(self) -> None:
        self.assertEqual({}, plan_S0({"days_since_last_purchase": {"C00000001": 40}}, 10**9, {"T3": 1}))


class TestS1RuleIsFrozen(unittest.TestCase):
    def test_rule_constants(self) -> None:
        """GATE 2 정신 — 이 값이 바뀌면 Baseline 부터 전 전략 재실행 대상이다."""
        self.assertEqual(28, S1_RULE["min_days_since_last_purchase"])
        self.assertEqual(90, S1_RULE["max_days_since_last_purchase"])
        self.assertEqual(2, S1_RULE["min_lifetime_order_count"])
        self.assertEqual("T3", S1_RULE["action"])


class TestS1Selection(unittest.TestCase):
    DAYS = {"C01": 27, "C02": 28, "C03": 90, "C04": 91, "C05": None, "C06": float("nan"), "C07": 60}

    def test_window_is_inclusive_and_missing_is_not_treated(self) -> None:
        got = plan_S1({"days_since_last_purchase": self.DAYS})
        self.assertEqual({"C03": "T3", "C07": "T3", "C02": "T3"}, got)
        self.assertEqual(["C03", "C07", "C02"], list(got))  # recency 나쁜 순

    def test_order_count_and_eligibility_filters(self) -> None:
        scores = {
            "days_since_last_purchase": self.DAYS,
            "lifetime_order_count": {"C02": 2, "C03": 1, "C07": None},
            "eligible": {"C02": True, "C03": True, "C07": True},
        }
        self.assertEqual({"C02": "T3"}, plan_S1(scores))

    def test_budget_cuts_in_priority_order(self) -> None:
        got = plan_S1({"days_since_last_purchase": self.DAYS}, budget_krw=2 * 7030, costs={"T3": 7030})
        self.assertEqual({"C03": "T3", "C07": "T3"}, got)

    def test_budget_without_cost_is_an_error_not_a_zero(self) -> None:
        with self.assertRaises(ValueError):
            plan_S1({"days_since_last_purchase": self.DAYS}, budget_krw=10_000, costs={})

    def test_ties_break_by_customer_id(self) -> None:
        got = plan_S1({"days_since_last_purchase": {"C09": 40, "C08": 40}})
        self.assertEqual(["C08", "C09"], list(got))

    def test_unapplied_conditions_are_not_run(self) -> None:
        info = s1_eligibility({"days_since_last_purchase": self.DAYS})
        self.assertEqual("not_run", info["conditions"]["lifetime_order_count"])
        self.assertEqual(2, info["n_days_missing"])

    def test_doctests(self) -> None:
        result = doctest.testmod(strategies, verbose=False)
        self.assertGreater(result.attempted, 0)
        self.assertEqual(0, result.failed)


if __name__ == "__main__":
    unittest.main()
