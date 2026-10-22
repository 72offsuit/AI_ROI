"""예산 최적화(다중선택 배낭 탐욕 근사) · What-if (이슈 #145 · OPT-001~005)."""

from __future__ import annotations

import itertools
import unittest
from importlib.util import find_spec

DEPS = all(find_spec(m) for m in ("numpy", "pandas"))
REASON = "BLOCKED: numpy/pandas/scikit-learn 미설치"

if DEPS:
    import numpy as np
    import pandas as pd

    from src.decision.optimize import _solve, optimize_budget, what_if, what_if_budgets

COST = {"T1": 3030.0, "T2": 3030.0, "T3": 7030.0, "T4": 60.0}


def brute_force(gain, cost, budget):
    best = 0.0
    opts = [None, *gain.columns]
    for combo in itertools.product(opts, repeat=len(gain)):
        spend = sum(cost[t] for t in combo if t)
        if spend > budget:
            continue
        v = sum(gain.iloc[i][t] - cost[t] for i, t in enumerate(combo) if t)
        best = max(best, v)
    return best


@unittest.skipUnless(DEPS, REASON)
class TestOptimize(unittest.TestCase):
    def setUp(self) -> None:
        rng = np.random.default_rng(0)
        n = 400
        self.gain = pd.DataFrame(rng.normal(3000, 6000, size=(n, 4)), columns=["T1", "T2", "T3", "T4"],
                                 index=[f"C{i:08d}" for i in range(n)])

    def test_budget_never_exceeded(self) -> None:
        for b in (0, 10_000, 250_000, 10**9):
            with self.subTest(budget=b):
                a = optimize_budget(self.gain, COST, b)
                self.assertLessEqual(sum(COST[t] for t in a.values()), b)

    def test_negative_net_is_never_chosen(self) -> None:
        a = optimize_budget(self.gain, COST, 10**9)
        for cid, t in a.items():
            self.assertGreater(self.gain.at[cid, t] - COST[t], 0)
        sleeping = self.gain.index[(self.gain < 0).all(axis=1)]
        self.assertTrue(set(sleeping).isdisjoint(a))

    def test_one_treatment_per_customer(self) -> None:
        a = optimize_budget(self.gain, COST, 500_000)
        self.assertEqual(len(a), len(set(a)))
        self.assertTrue(set(a.values()) <= {"T1", "T2", "T3", "T4"})

    def test_close_to_brute_force_on_small_problem(self) -> None:
        g = self.gain.iloc[:6]
        b = 12_000
        opt = brute_force(g, COST, b)
        got = _solve(g, COST, b)["expected_net_krw"]
        self.assertLessEqual(got, opt + 1e-6)
        self.assertGreaterEqual(got, 0.7 * opt)   # 근사 — 최적 보장이 없음을 테스트가 숨기지 않는다

    def test_missing_cost_is_an_error(self) -> None:
        with self.assertRaises(ValueError):
            optimize_budget(self.gain, {"T1": 1.0}, 1000)

    def test_what_if(self) -> None:
        conv = self.gain / 100000.0
        rows = what_if(what_if_budgets(200_000), self.gain, COST, expected_conversion=conv)
        self.assertEqual([100_000, 200_000, 400_000], [r["budget_krw"] for r in rows])
        self.assertLessEqual(rows[0]["target_count"], rows[2]["target_count"])
        for r in rows:
            self.assertLessEqual(r["spend_krw"], r["budget_krw"])
            self.assertIsNone(r["expected_revenue_krw"])   # 입력 없으면 계산 불가
            self.assertIsNotNone(r["expected_saved_customers"])


if __name__ == "__main__":
    unittest.main()
