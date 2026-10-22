"""전략 S2~S5 · plan() 디스패처 · ROI 요약 (이슈 #145)."""

from __future__ import annotations

import unittest
from importlib.util import find_spec

from src.decision.roi import summarize_all, summarize_strategy
from src.decision.strategies import NotComputable, STRATEGY_NAMES, plan, plan_summary, planning_costs

DEPS = all(find_spec(m) for m in ("numpy", "pandas"))
REASON = "BLOCKED: numpy/pandas/scikit-learn 미설치"

if DEPS:
    import numpy as np
    import pandas as pd

ECON_TREATMENT_COST = {"T0": {"unit_cost_krw": 0}, "T1": {"unit_cost_krw": 3000},
                       "T2": {"unit_cost_krw": 3000}, "T3": {"unit_cost_krw": 7000},
                       "T4": {"unit_cost_krw": 30}}
COSTS = planning_costs(ECON_TREATMENT_COST, 30)


def scores(n=300, seed=0):
    rng = np.random.default_rng(seed)
    idx = [f"C{i:08d}" for i in range(n)]
    cate = pd.DataFrame(rng.normal(0.02, 0.05, size=(n, 4)), columns=["T1", "T2", "T3", "T4"], index=idx)
    cate.iloc[:20] = -0.1                        # 역효과 고객
    cate.iloc[20:25] = np.nan                    # CATE 계산 불가 고객
    return {
        "churn_p": pd.Series(rng.random(n), index=idx),
        "cate": cate,
        "clv": pd.Series(rng.lognormal(12, 0.5, n), index=idx),
        "days_since_last_purchase": pd.Series(rng.integers(0, 120, n).astype(float), index=idx),
    }


class TestPlanningCosts(unittest.TestCase):
    def test_upper_bound_cost(self) -> None:
        self.assertEqual({"T1": 3030.0, "T2": 3030.0, "T3": 7030.0, "T4": 60.0}, COSTS)


@unittest.skipUnless(DEPS, REASON)
class TestPlans(unittest.TestCase):
    def setUp(self) -> None:
        self.s = scores()
        self.budget = 40 * 7030

    def test_every_strategy_respects_budget_and_vocab(self) -> None:
        for sid in STRATEGY_NAMES:
            with self.subTest(strategy=sid):
                a = plan(sid, self.s, self.budget, COSTS)
                self.assertLessEqual(sum(COSTS[t] for t in a.values()), self.budget)
                self.assertTrue(set(a.values()) <= {"T1", "T2", "T3", "T4"})
                self.assertNotIn("T0", a.values())

    def test_s0_empty_s2_highest_risk(self) -> None:
        self.assertEqual({}, plan("S0", self.s, self.budget, COSTS))
        a = plan("S2", self.s, self.budget, COSTS)
        self.assertEqual(40, len(a))
        top = self.s["churn_p"].sort_values(ascending=False).index[:40]
        self.assertEqual(set(top), set(a))

    def test_uplift_strategies_avoid_sleeping_dogs(self) -> None:
        dogs = set(self.s["cate"].index[:20])
        for sid in ("S3", "S4", "S5"):
            with self.subTest(strategy=sid):
                self.assertTrue(dogs.isdisjoint(plan(sid, self.s, 10**9, COSTS)))

    def test_missing_clv_is_not_computable(self) -> None:
        s = dict(self.s, clv=None)
        for sid in ("S4", "S5"):
            with self.subTest(strategy=sid), self.assertRaises(NotComputable):
                plan(sid, s, self.budget, COSTS)

    def test_ai_strategy_requires_budget(self) -> None:
        with self.assertRaises(ValueError):
            plan("S2", self.s, None, COSTS)

    def test_s1_through_dispatcher(self) -> None:
        a = plan("S1", self.s, None, COSTS)
        d = self.s["days_since_last_purchase"]
        self.assertEqual(set(d.index[(d >= 28) & (d <= 90)]), set(a))


class TestPlanSummary(unittest.TestCase):
    def test_counts(self) -> None:
        self.assertEqual({"n_targeted": 3, "treatment_mix": {"T1": 1, "T3": 2}},
                         plan_summary({"C1": "T3", "C2": "T1", "C3": "T3"}))
        with self.assertRaises(ValueError):
            plan_summary({"C1": "T0"})


class TestRoi(unittest.TestCase):
    BASE = {"id": "S1", "revenue": 1000.0, "marketing_cost": 100.0, "contribution_profit": 300.0, "churn_rate": 0.2}

    def test_incremental_and_roi(self) -> None:
        r = summarize_strategy({"id": "S3", "revenue": 1100.0, "marketing_cost": 150.0,
                                "contribution_profit": 340.0, "churn_rate": 0.18}, self.BASE)
        self.assertAlmostEqual(40.0, r["incremental_profit_vs_S1"])
        self.assertAlmostEqual(40.0 / 50.0, r["roi"])
        self.assertIsNone(r["ai_roi"])       # AI 투자비 미지정 → 계산 불가

    def test_zero_extra_cost_is_not_computable(self) -> None:
        r = summarize_strategy({"id": "S5", "marketing_cost": 100.0, "contribution_profit": 310.0}, self.BASE)
        self.assertIsNone(r["roi"])
        self.assertIn("계산 불가", r["roi_status"])

    def test_missing_profit_propagates_none(self) -> None:
        r = summarize_strategy({"id": "S2", "marketing_cost": 120.0, "contribution_profit": None}, self.BASE)
        self.assertIsNone(r["incremental_profit_vs_S1"])
        self.assertIsNone(r["roi"])

    def test_ai_roi_and_flags(self) -> None:
        r = summarize_strategy({"id": "S4", "revenue": 1200.0, "marketing_cost": 250.0,
                                "contribution_profit": 290.0, "churn_rate": 0.1}, self.BASE,
                               ai_investment_cost=5.0)
        self.assertAlmostEqual((-10.0 - 5.0) / 5.0, r["ai_roi"])
        self.assertIn("revenue_up_profit_down", r["flags"])
        self.assertIn("retention_up_cost_surge", r["flags"])

    def test_summarize_all(self) -> None:
        rows = summarize_all({"S1": self.BASE, "S0": {"marketing_cost": 0.0, "contribution_profit": 250.0}})
        self.assertEqual(["S0", "S1"], [r["id"] for r in rows])
        self.assertAlmostEqual(-50.0, rows[0]["incremental_profit_vs_S1"])
        self.assertEqual("무처치", rows[0]["name"])
        self.assertAlmostEqual(0.0, rows[1]["incremental_profit_vs_S1"])
        self.assertIsNone(rows[1]["roi"])


if __name__ == "__main__":
    unittest.main()
