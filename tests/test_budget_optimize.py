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


def _scores(n=300, seed=1):
    """전략 플래너가 받는 점수 묶음 — tests/test_strategy_plans.scores 와 같은 모양."""
    rng = np.random.default_rng(seed)
    idx = [f"C{i:08d}" for i in range(n)]
    cate = pd.DataFrame(rng.normal(0.02, 0.05, size=(n, 4)), columns=["T1", "T2", "T3", "T4"], index=idx)
    cate.iloc[:20] = -0.1
    cate.iloc[20:25] = np.nan
    return {
        "churn_p": pd.Series(rng.random(n), index=idx),
        "cate": cate,
        "clv": pd.Series(rng.lognormal(12, 0.5, n), index=idx),
        "days_since_last_purchase": pd.Series(rng.integers(0, 120, n).astype(float), index=idx),
        "eligible": pd.Series(True, index=idx),
        "margin_rate": 0.3,
    }


#: 리뷰 반례용 계획비 — 작은 수라 손으로 검산할 수 있다.
TINY_COST = {"T1": 1.0, "T2": 2.0, "T3": 12.0, "T4": 100.0}


def _one(cate: dict) -> dict:
    """고객 1명(S1 규칙 대상)의 점수 — CLV · margin_rate 를 1 로 두어 기대 증분가치 = CATE."""
    idx = ["C00000001"]
    return {
        "cate": pd.DataFrame([cate], index=idx)[["T1", "T2", "T3", "T4"]].astype(float),
        "clv": pd.Series(1.0, index=idx),
        "days_since_last_purchase": pd.Series(60.0, index=idx),
        "eligible": pd.Series(True, index=idx),
        "margin_rate": 1.0,
    }


@unittest.skipUnless(DEPS, REASON)
class TestBindingAndHybridWhatIf(unittest.TestCase):
    """#274 · DR-170 E1~E4 · E6 — 구속 예산 S4 대 S5 · 혼합 전략 S6 · 예산 근거."""

    def setUp(self) -> None:
        from src.decision.strategies import plan

        self.s = _scores()
        self.plan = plan
        self.c_rule = len(plan("S1", self.s, None, COST)) * COST["T3"]

    def test_ratios_are_the_values_fixed_before_results(self) -> None:
        from src.decision.optimize import BINDING_RATIOS

        self.assertEqual((0.25, 0.50, 0.75), BINDING_RATIOS)

    def test_binding_rows_follow_s4_cost(self) -> None:
        from src.decision.optimize import binding_what_if

        out = binding_what_if(self.s, COST, 10**9)
        s4_cost = sum(COST[t] for t in self.plan("S4", self.s, 10**9, COST).values())
        self.assertEqual("ok", out["status"])
        self.assertAlmostEqual(s4_cost, out["s4_planned_cost_krw"])
        self.assertEqual([("S4", 0.25), ("S5", 0.25), ("S4", 0.5), ("S5", 0.5), ("S4", 0.75), ("S5", 0.75)],
                         [(r["strategy_id"], r["ratio_of_s4_cost"]) for r in out["rows"]])
        for r in out["rows"]:
            self.assertAlmostEqual(s4_cost * r["ratio_of_s4_cost"], r["budget_krw"])
            self.assertLessEqual(r["spend_krw"], r["budget_krw"] + 1e-6)
        # 예산이 남으면(E1) 해석 문장 — 구속 여부와 배정 동일 여부를 따로 본다
        self.assertIs(False, out["binding_at_plan_budget"])
        self.assertEqual(out["same_assignment_at_plan_budget"], out["n_customers_assigned_differently"] == 0)
        self.assertIn("예산이 남는다", out["interpretation"])
        self.assertEqual(["S4", "S5"], [r["strategy_id"] for r in out["plan_budget_rows"]])
        self.assertIn("기대값", out["limitation"])

    def test_binding_flag_when_plan_budget_is_tight(self) -> None:
        from src.decision.optimize import binding_what_if

        out = binding_what_if(self.s, COST, 20_000)
        self.assertIs(True, out["binding_at_plan_budget"])
        self.assertIn("예산이 걸린다", out["interpretation"])
        self.assertLessEqual(out["s4_planned_cost_krw"], 20_000)

    def test_slack_budget_still_compares_actual_s4_s5_assignments(self) -> None:
        """PR #313 리뷰 반례 — 예산이 남아도 S5 탐욕 근사(효율 우선 · 업그레이드 1회)는 S4 와 다를 수 있다.

        계획비 T1 · T2 · T3 = 1 · 2 · 12, 기대 증분가치 3 · 5 · 23, 예산 20 → S4 = T3(순이익 11), S5 = T2(3)."""
        from src.decision.optimize import binding_what_if

        out = binding_what_if(_one({"T1": 3.0, "T2": 5.0, "T3": 23.0, "T4": -1.0}), TINY_COST, 20.0)
        self.assertIs(False, out["binding_at_plan_budget"])
        self.assertIs(False, out["same_assignment_at_plan_budget"])
        self.assertEqual(1, out["n_customers_assigned_differently"])
        self.assertEqual({"S4": {"T3": 1}, "S5": {"T2": 1}},
                         {r["strategy_id"]: r["treatment_mix"] for r in out["plan_budget_rows"]})
        gap = out["s5_minus_s4_at_plan_budget"]
        self.assertAlmostEqual(-8.0, gap["expected_net_diff_krw"])
        self.assertEqual((1, 0), (gap["n_compared"], gap["n_excluded_unscored"]))
        self.assertNotIn("추가 효과가 0", out["interpretation"])
        self.assertIn("탐욕 근사", out["interpretation"])
        self.assertIn("S5 − S4 = -8원", out["interpretation"])

    def test_slack_budget_and_same_assignment_says_no_extra_effect(self) -> None:
        from src.decision.optimize import binding_what_if

        out = binding_what_if(_one({"T1": 3.0, "T2": -1.0, "T3": -1.0, "T4": -1.0}), TINY_COST, 20.0)
        self.assertIs(False, out["binding_at_plan_budget"])
        self.assertIs(True, out["same_assignment_at_plan_budget"])
        self.assertAlmostEqual(0.0, out["s5_minus_s4_at_plan_budget"]["expected_net_diff_krw"])
        self.assertIn("추가 효과가 0", out["interpretation"])

    def test_s5_not_worse_than_s4_when_budget_binds(self) -> None:
        """DR-145 「이 결정이 틀렸다면」 — 같은 예산에서 S5 < S4 면 탐욕 근사가 나쁘다. 이 데이터에서는 그렇지 않다."""
        from src.decision.optimize import binding_what_if

        rows = binding_what_if(self.s, COST, 10**9)["rows"]
        for s4, s5 in zip(rows[0::2], rows[1::2]):
            self.assertGreaterEqual(s5["expected_net_krw"], s4["expected_net_krw"] - 1e-6)

    def test_hybrid_rows_at_c_rule(self) -> None:
        from src.decision.optimize import HYBRID_ROWS, hybrid_what_if

        out = hybrid_what_if(self.s, COST, self.c_rule)
        rows = {r["row_id"]: r for r in out["rows"]}
        self.assertEqual([rid for rid, _ in HYBRID_ROWS], [r["row_id"] for r in out["rows"]])
        self.assertEqual(rows["S1"]["target_count"], rows["S6"]["target_count"])   # 같은 고객
        self.assertEqual(0, out["s6"]["n_dropped_by_budget"])
        self.assertAlmostEqual(self.c_rule, rows["S1"]["spend_krw"])
        for r in out["rows"]:
            self.assertLessEqual(r["spend_krw"], self.c_rule + 1e-6, r["row_id"])
        self.assertAlmostEqual(self.c_rule - rows["S6"]["spend_krw"], out["s6_saved_budget_krw"])
        self.assertEqual(rows["S6"]["target_count"] + out["s6_ext_added_targets"], rows["S6_ext"]["target_count"])
        # S6 은 고객마다 기대 순이익이 가장 큰 처치를 고르므로 같은 고객의 T3 보다 나쁠 수 없다(모델 기준)
        self.assertGreaterEqual(rows["S6"]["expected_net_vs_S1_krw"], -1e-6)
        self.assertGreaterEqual(rows["S6_ext"]["expected_net_krw"], rows["S6"]["expected_net_krw"] - 1e-6)
        self.assertEqual(0.0, rows["S1"]["expected_net_vs_S1_krw"])
        # 결손 고객은 0 으로 채우지 않고 센다 — S1 · S6 둘 다 같은 고객이 결손이다
        self.assertEqual(rows["S1"]["n_unscored"], rows["S6"]["n_unscored"])
        self.assertGreater(rows["S1"]["n_unscored"], 0)
        self.assertIn("결손", rows["S1"]["expectation_scope"])
        self.assertIsNotNone(out["comparability"])
        # S1 대비 차이는 짝 비교 — 결손 고객은 비교에서 빠진다
        self.assertEqual(rows["S1"]["n_unscored"], rows["S6"]["vs_S1_n_excluded_unscored"])
        self.assertEqual(rows["S1"]["n_scored"], rows["S6"]["vs_S1_n_compared"])

    def test_vs_s1_is_paired_on_customers_scored_in_both(self) -> None:
        """PR #313 리뷰 반례 — 같은 고객 1명, T3 점수만 없다. S1 합은 비고 S6 은 T1(순이익 9)을 고른다.

        두 합을 따로 내 빼면 9 가 나오지만 범위가 다른 수끼리 뺀 것이다 — 짝 비교로는 비교할 고객이 0명이라 None."""
        from src.decision.optimize import hybrid_what_if

        s = _one({"T1": 10.0, "T2": np.nan, "T3": np.nan, "T4": np.nan})
        out = hybrid_what_if(s, TINY_COST, TINY_COST["T3"])
        rows = {r["row_id"]: r for r in out["rows"]}
        self.assertEqual({"T3": 1}, rows["S1"]["treatment_mix"])
        self.assertEqual({"T1": 1}, rows["S6"]["treatment_mix"])
        self.assertIsNone(rows["S1"]["expected_net_krw"])            # 배정 1명 · 점수 0명 — 0 이 아니다
        self.assertIsNone(rows["S1"]["expected_conversion"])
        self.assertAlmostEqual(9.0, rows["S6"]["expected_net_krw"])
        self.assertIsNone(rows["S6"]["expected_net_vs_S1_krw"])
        self.assertEqual((0, 1), (rows["S6"]["vs_S1_n_compared"], rows["S6"]["vs_S1_n_excluded_unscored"]))
        self.assertIsNotNone(out["comparability"])

    def test_paired_difference_equals_total_difference_without_missing_scores(self) -> None:
        from src.decision.optimize import hybrid_what_if

        s = dict(self.s, cate=self.s["cate"].fillna(0.01))
        out = hybrid_what_if(s, COST, self.c_rule)
        base = out["rows"][0]
        for r in out["rows"]:
            self.assertEqual(0, r["vs_S1_n_excluded_unscored"], r["row_id"])
            self.assertAlmostEqual(r["expected_net_krw"] - base["expected_net_krw"], r["expected_net_vs_S1_krw"],
                                   places=4, msg=r["row_id"])
        self.assertIsNone(out["comparability"])

    def test_ext_spends_the_saved_budget_outside_the_rule(self) -> None:
        """확장(E4)은 규칙 밖 고객에게만 — 규칙 대상과 겹치면 합친 배정의 대상 수가 S6 + 추가 수보다 작아진다."""
        from src.decision.optimize import hybrid_what_if

        out = hybrid_what_if(self.s, COST, self.c_rule)
        rows = {r["row_id"]: r for r in out["rows"]}
        self.assertGreater(out["s6"]["n_changed_from_rule"], 0)
        self.assertGreater(out["s6_saved_budget_krw"], 0, "T3 보다 싼 처치로 바뀐 고객이 있으면 예산이 남는다")
        self.assertGreater(out["s6_ext_added_targets"], 0)
        self.assertEqual(rows["S6"]["target_count"] + out["s6_ext_added_targets"], rows["S6_ext"]["target_count"])
        self.assertLessEqual(rows["S6_ext"]["spend_krw"], self.c_rule + 1e-6)

    def test_no_saved_budget_means_no_extension(self) -> None:
        from src.decision.optimize import hybrid_what_if

        s = dict(self.s, cate=self.s["cate"].assign(T1=-1.0, T2=-1.0, T4=-1.0, T3=0.5))  # 모두 T3 가 최선
        out = hybrid_what_if(s, COST, self.c_rule)
        self.assertEqual(0, out["s6"]["n_changed_from_rule"])
        self.assertAlmostEqual(0.0, out["s6_saved_budget_krw"])
        self.assertEqual(0, out["s6_ext_added_targets"])

    def test_missing_scores_are_not_computable(self) -> None:
        from src.decision.optimize import binding_what_if, hybrid_what_if
        from src.decision.strategies import NotComputable

        s = {k: v for k, v in self.s.items() if k != "margin_rate"}
        with self.assertRaises(NotComputable):
            binding_what_if(s, COST, 10**9)
        with self.assertRaises(NotComputable):
            hybrid_what_if(s, COST, self.c_rule)

    def test_assignment_expectation_does_not_fill_missing(self) -> None:
        from src.decision.optimize import assignment_expectation

        gain = pd.DataFrame({"T3": [10_000.0, np.nan]}, index=["C1", "C2"])
        conv = pd.DataFrame({"T3": [0.1, np.nan]}, index=["C1", "C2"])
        out = assignment_expectation({"C1": "T3", "C2": "T3"}, gain, COST, conv)
        self.assertEqual(2, out["target_count"])
        self.assertAlmostEqual(2 * 7030.0, out["spend_krw"])
        self.assertAlmostEqual(10_000.0, out["expected_gain_krw"])
        self.assertAlmostEqual(10_000.0 - 7030.0, out["expected_net_krw"])
        self.assertEqual(1, out["n_unscored"])
        self.assertAlmostEqual(0.1, out["expected_conversion"])
        # 배정은 있는데 점수 있는 고객이 0명 — 빈 합 0 이 아니라 계산 불가
        none = assignment_expectation({"C2": "T3"}, gain, COST, conv)
        self.assertEqual((None, None, None), (none["expected_gain_krw"], none["expected_net_krw"],
                                              none["expected_conversion"]))
        self.assertEqual((0, 1), (none["n_scored"], none["n_unscored"]))
        self.assertIn("0명", none["expectation_scope"])
        # 배정이 0명이면 기대값은 관측된 0 이다
        empty = assignment_expectation({}, gain, COST, conv)
        self.assertEqual((0.0, 0.0), (empty["expected_net_krw"], empty["expected_conversion"]))

    def test_budget_rationale(self) -> None:
        from src.decision.optimize import budget_rationale

        out = budget_rationale(70_300.0, 10, 1_000_000.0)
        self.assertAlmostEqual(7030.0, out["per_target_krw"])
        self.assertAlmostEqual(0.0703, out["revenue_share"])
        self.assertIsNone(out["revenue_share_reason"])
        missing = budget_rationale(70_300.0, 10, None)
        self.assertIsNone(missing["revenue_share"])
        self.assertIn("매출", missing["revenue_share_reason"])
        none = budget_rationale(None, None, None)
        self.assertEqual((None, "C_rule 없음"), (none["per_target_krw"], none["per_target_reason"]))
        zero = budget_rationale(0.0, 0, 1.0)
        self.assertIsNone(zero["per_target_krw"])          # 대상 0명 — 나눌 수 없다(0 으로 채우지 않는다)
        self.assertEqual(0.0, zero["revenue_share"])        # C_rule = 0 은 유효한 값이다(DR-170 D2)


if __name__ == "__main__":
    unittest.main()
