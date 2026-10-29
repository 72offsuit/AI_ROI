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
        # 전원 Eligible — 아래 기존 검사는 거르기 전 동작을 본다. 거르기는 TestEligibleIsTheCommonPool.
        "eligible": pd.Series(True, index=idx),
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

    def test_orchestrator_unit_costs_with_t0(self) -> None:
        unit = {"T0": 0, "T1": 3000, "T2": 3000, "T3": 7000, "T4": 30}
        for sid in STRATEGY_NAMES:
            with self.subTest(strategy=sid):
                a = plan(sid, self.s, 100_000, unit)
                self.assertLessEqual(sum(unit[t] for t in a.values()), 100_000)

    def test_s1_through_dispatcher(self) -> None:
        a = plan("S1", self.s, None, COSTS)
        d = self.s["days_since_last_purchase"]
        self.assertEqual(set(d.index[(d >= 28) & (d <= 90)]), set(a))


@unittest.skipUnless(DEPS, REASON)
class TestEligibleIsTheCommonPool(unittest.TestCase):
    """S1~S5 는 Eligible 안에서만 고른다 — data_spec §4.1 · #194 · DR-234 (PR #154 리뷰 "eligible 범위가 다름")."""

    def setUp(self) -> None:
        self.s = scores()
        idx = self.s["churn_p"].index
        # 짝수 번째만 Eligible. 결손 플래그 하나는 Eligible 이 아니다(판정할 수 없다).
        flags = pd.Series([i % 2 == 0 for i in range(len(idx))], index=idx, dtype=object)
        flags.iloc[2] = None
        self.s["eligible"] = flags
        self.keep = {cid for i, cid in enumerate(idx) if i % 2 == 0 and i != 2}

    def test_no_strategy_assigns_an_ineligible_customer(self) -> None:
        for sid in ("S1", "S2", "S3", "S4", "S5"):
            with self.subTest(strategy=sid):
                a = plan(sid, self.s, None if sid == "S1" else 40 * 7030, COSTS)
                self.assertTrue(a, "배정이 비면 이 검사는 공허하다")
                self.assertEqual(set(), set(a) - self.keep)

    def test_budget_is_spent_inside_the_pool_not_left_over(self) -> None:
        """고른 뒤에 빼면 부적격 고객 몫의 예산이 남는다. 먼저 거르면 같은 예산으로 Eligible 만 40명이다."""
        a = plan("S2", self.s, 40 * 7030, COSTS)
        self.assertEqual(40, len(a))
        p = self.s["churn_p"]
        top = p[p.index.isin(self.keep)].sort_values(ascending=False).index[:40]
        self.assertEqual(set(top), set(a))

    def test_dict_scores_are_filtered_too(self) -> None:
        a = plan("S1", {"days_since_last_purchase": {"C1": 40, "C2": 50},
                        "eligible": {"C1": False, "C2": True}}, None, COSTS)
        self.assertEqual({"C2": "T3"}, a)


class TestMissingScores(unittest.TestCase):
    """필요한 점수가 없으면 판별 가능한 예외 — 빈 배정으로 대신하지 않는다 (표준 라이브러리)."""

    def test_each_strategy_names_what_is_missing(self) -> None:
        unit = {"T0": 0, "T1": 3000, "T2": 3000, "T3": 7000, "T4": 30}
        for sid in ("S1", "S2", "S3", "S4", "S5"):
            with self.subTest(strategy=sid), self.assertRaises(NotComputable):
                plan(sid, {}, 100_000, unit)
        self.assertEqual({}, plan("S0", {}, 100_000, unit))

    def test_without_eligible_s1_to_s5_are_not_computable(self) -> None:
        """purchase 를 만들지 않는 판처럼 Eligible 을 판정할 수 없으면, 다른 점수가 다 있어도 전략은 돌지 않는다.
        거르지 않은 채 S2~S5 만 돌면 S1 과 다른 모집단에서 고른 결과가 비교표에 오른다(DR-234)."""
        unit = {"T0": 0, "T1": 3000, "T2": 3000, "T3": 7000, "T4": 30}
        full = {"days_since_last_purchase": {"C1": 40}, "churn_p": {"C1": 0.9},
                "cate": {"C1": 0.1}, "clv": {"C1": 1.0}}
        for sid in ("S1", "S2", "S3", "S4", "S5"):
            with self.subTest(strategy=sid), self.assertRaises(NotComputable) as caught:
                plan(sid, full, None if sid == "S1" else 100_000, unit)
            self.assertIn("eligible", str(caught.exception))


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

    def test_orchestrator_metrics_prefer_sim_contribution_profit(self) -> None:
        base = {"strategy_id": "S1", "sim_revenue": 1000.0, "sim_contribution_profit": 300.0,
                "sim_marketing_cost": 100.0, "revenue_krw": 990.0, "planned_treatment_cost_krw": 120.0,
                "churn_rate": 0.2, "n_population": 10}
        ai = {"strategy_id": "S5", "sim_revenue": 1050.0, "sim_contribution_profit": 330.0,
              "sim_marketing_cost": 120.0, "revenue_krw": 1040.0, "planned_treatment_cost_krw": 150.0,
              "churn_rate": 0.18, "n_population": 10}
        r = summarize_strategy(ai, base)
        self.assertEqual("S5", r["id"])
        self.assertAlmostEqual(30.0, r["incremental_profit_vs_S1"])
        self.assertEqual("sim_contribution_profit", r["incremental_profit_basis"])
        self.assertAlmostEqual(30.0 / 20.0, r["roi"])
        self.assertNotIn("PROFIT_FALLBACK_REVENUE_BASED", r["flags"])
        self.assertEqual(10, r["n_population"])

    def test_revenue_fallback_is_separate_and_not_profit(self) -> None:
        """#169 — 대체값은 별도 필드다. 정식 증분이익 · ROI 는 계산 불가(이전에는 대체값으로 ROI ok)."""
        base = {"strategy_id": "S1", "sim_contribution_profit": None, "revenue_krw": 1000.0,
                "planned_treatment_cost_krw": 100.0}
        ai = {"strategy_id": "S2", "sim_contribution_profit": None, "revenue_krw": 1100.0,
              "planned_treatment_cost_krw": 140.0}
        r = summarize_strategy(ai, base, ai_investment_cost=5.0)
        self.assertIsNone(r["incremental_profit_vs_S1"])
        self.assertIsNone(r["incremental_profit_basis"])
        self.assertIn("계산 불가", r["incremental_profit_status"])
        self.assertAlmostEqual(100.0 - 40.0, r["directional_revenue_minus_marketing_vs_S1"])
        self.assertEqual("Δrevenue_krw − Δplanned_treatment_cost_krw", r["directional_basis"])
        self.assertIn("방향 확인용", r["directional_status"])
        self.assertIsNone(r["roi"])
        self.assertNotEqual("ok", r["roi_status"])
        self.assertIsNone(r["ai_roi"])
        self.assertNotEqual("ok", r["ai_roi_status"])
        self.assertIn("PROFIT_FALLBACK_REVENUE_BASED", r["flags"])
        self.assertIn("CONTRIBUTION_PROFIT_MISSING", r["flags"])
        self.assertIn("MARKETING_COST_PLANNED_NOT_REALIZED", r["flags"])

    def test_mixed_basis_is_not_compared(self) -> None:
        """한쪽만 sim 기여이익이 있고 매출도 공통 키가 없으면 계산 불가."""
        r = summarize_strategy({"strategy_id": "S2", "sim_contribution_profit": 10.0},
                               {"strategy_id": "S1", "contribution_profit": 5.0})
        self.assertIsNone(r["incremental_profit_vs_S1"])
        self.assertIn("기준 불일치", r["incremental_profit_status"])
        self.assertIsNone(r["directional_revenue_minus_marketing_vs_S1"])
        self.assertNotIn("PROFIT_FALLBACK_REVENUE_BASED", r["flags"])

    def test_summarize_all_keeps_baseline_zero(self) -> None:
        rows = summarize_all({"S1": self.BASE})
        self.assertEqual("ok", rows[0]["incremental_profit_status"])
        self.assertIn("not_run", rows[0]["directional_status"])

    def test_summarize_all(self) -> None:
        rows = summarize_all({"S1": self.BASE, "S0": {"marketing_cost": 0.0, "contribution_profit": 250.0}})
        self.assertEqual(["S0", "S1"], [r["id"] for r in rows])
        self.assertAlmostEqual(-50.0, rows[0]["incremental_profit_vs_S1"])
        self.assertEqual("무처치", rows[0]["name"])
        self.assertAlmostEqual(0.0, rows[1]["incremental_profit_vs_S1"])
        self.assertIsNone(rows[1]["roi"])


class TestRoiProfitBasis(unittest.TestCase):
    """#169 — 정식 증분이익은 공통 기여이익 차이로만. 결손 · 키 불일치는 계산 불가, 대체값은 별도."""

    #: 오케스트레이션이 측정 계층(build_kpi_report)으로 낸 분기 집계의 모양 (DR-169).
    S1 = {"strategy_id": "S1", "sim_contribution_profit": None, "sim_revenue": None, "sim_marketing_cost": None,
          "measured_revenue": 24_087_300.0, "measured_marketing_cost": 100_000.0,
          "measured_contribution_profit": 6_277_952.0, "revenue_krw": 900_000.0,
          "planned_treatment_cost_krw": 70_300.0, "churn_rate": 0.30}

    def test_measured_profit_is_the_formal_increment(self) -> None:
        ai = {**self.S1, "strategy_id": "S3", "measured_revenue": 24_435_800.0, "measured_marketing_cost": 280_000.0,
              "measured_contribution_profit": 6_198_289.0, "revenue_krw": 950_000.0, "churn_rate": 0.29}
        r = summarize_strategy(ai, self.S1, ai_investment_cost=1_000.0)
        self.assertAlmostEqual(6_198_289.0 - 6_277_952.0, r["incremental_profit_vs_S1"])
        self.assertEqual("measured_contribution_profit", r["incremental_profit_basis"])
        self.assertEqual("ok", r["incremental_profit_status"])
        # ROI 분모는 계획치가 아니라 측정 계층 실현 마케팅비다
        self.assertEqual("measured_marketing_cost", r["basis"]["incremental_marketing_cost"])
        self.assertAlmostEqual(-79_663.0 / 180_000.0, r["roi"])
        self.assertEqual("ok", r["ai_roi_status"])
        self.assertIsNone(r["directional_revenue_minus_marketing_vs_S1"])
        self.assertIn("not_run", r["directional_status"])
        for flag in ("PROFIT_FALLBACK_REVENUE_BASED", "CONTRIBUTION_PROFIT_MISSING",
                     "MARKETING_COST_PLANNED_NOT_REALIZED"):
            self.assertNotIn(flag, r["flags"])
        # 매출(측정)↑ · 기여이익↓ — 대체 계산으로는 영원히 판정할 수 없던 경우다
        self.assertEqual({"status": "ok", "triggered": True},
                         {k: r["guardrails"]["revenue_up_profit_down"][k] for k in ("status", "triggered")})
        self.assertEqual("measured_revenue", r["guardrails"]["revenue_up_profit_down"]["basis"]["revenue"])
        self.assertIn("revenue_up_profit_down", r["flags"])
        self.assertEqual("measured_revenue", r["basis"]["revenue"])  # 표의 매출도 기여이익과 같은 모집단

    def test_one_side_missing_is_not_computable(self) -> None:
        """전략 쪽만 결손 — 이전에는 대체 계산으로 떨어져 roi_status=ok 였다."""
        ai = {**self.S1, "strategy_id": "S2", "measured_contribution_profit": None,
              "measured_marketing_cost": 300_000.0, "measured_revenue": 25_000_000.0}
        r = summarize_strategy(ai, self.S1, ai_investment_cost=1_000.0)
        self.assertIsNone(r["incremental_profit_vs_S1"])
        self.assertIn("전략 쪽 contribution_profit 결손", r["incremental_profit_status"])
        self.assertIsNone(r["roi"])
        self.assertIn("계산 불가", r["roi_status"])
        self.assertIsNone(r["ai_roi"])
        self.assertIsNone(r["ai_net_incremental_value"])
        self.assertIn("계산 불가", r["ai_roi_status"])
        self.assertAlmostEqual(912_700.0 - 200_000.0, r["directional_revenue_minus_marketing_vs_S1"])
        self.assertIn("PROFIT_FALLBACK_REVENUE_BASED", r["flags"])
        self.assertIn("CONTRIBUTION_PROFIT_MISSING", r["flags"])

    def test_baseline_side_missing_is_named(self) -> None:
        base = {**self.S1, "measured_contribution_profit": None}
        r = summarize_strategy({**self.S1, "strategy_id": "S4"}, base)
        self.assertIsNone(r["incremental_profit_vs_S1"])
        self.assertIn("기준선 쪽 contribution_profit 결손", r["incremental_profit_status"])

    def test_key_mismatch_is_not_compared_even_with_revenue(self) -> None:
        """키 이름이 다르면 같은 정의라는 대조가 없다 — 차이를 내지 않는다."""
        ai = {"strategy_id": "S5", "sim_contribution_profit": 330.0, "revenue_krw": 1100.0,
              "planned_treatment_cost_krw": 150.0}
        base = {"strategy_id": "S1", "measured_contribution_profit": 300.0, "revenue_krw": 1000.0,
                "planned_treatment_cost_krw": 100.0}
        r = summarize_strategy(ai, base)
        self.assertIsNone(r["incremental_profit_vs_S1"])
        self.assertIn("기준 불일치", r["incremental_profit_status"])
        self.assertIn("sim_contribution_profit", r["incremental_profit_status"])
        self.assertIn("measured_contribution_profit", r["incremental_profit_status"])
        self.assertIsNone(r["roi"])
        self.assertAlmostEqual(100.0 - 50.0, r["directional_revenue_minus_marketing_vs_S1"])

    def test_missing_is_not_zero(self) -> None:
        """결손을 0 으로 채우지 않는다 — 0 은 정직한 값이다."""
        zero = {**self.S1, "strategy_id": "S0", "measured_contribution_profit": 0.0}
        r = summarize_strategy(zero, self.S1)
        self.assertAlmostEqual(-6_277_952.0, r["incremental_profit_vs_S1"])
        self.assertEqual("ok", r["incremental_profit_status"])
        nan = {**self.S1, "strategy_id": "S0", "measured_contribution_profit": float("nan")}
        self.assertIsNone(summarize_strategy(nan, self.S1)["incremental_profit_vs_S1"])

    def test_guardrail_is_not_run_without_common_profit(self) -> None:
        ai = {**self.S1, "strategy_id": "S2", "measured_contribution_profit": None, "measured_revenue": 30_000_000.0}
        r = summarize_strategy(ai, self.S1)
        verdict = r["guardrails"]["revenue_up_profit_down"]
        self.assertEqual("not_run", verdict["status"])
        self.assertIsNone(verdict["triggered"])  # False(통과) 가 아니다
        self.assertIn("공통 기여이익 차이 없음", verdict["reason"])
        self.assertIn("REVENUE_UP_PROFIT_DOWN_NOT_RUN", r["flags"])
        self.assertNotIn("revenue_up_profit_down", r["flags"])

    def test_guardrail_false_is_a_verdict(self) -> None:
        ai = {**self.S1, "strategy_id": "S3", "measured_contribution_profit": 6_500_000.0}
        verdict = summarize_strategy(ai, self.S1)["guardrails"]["revenue_up_profit_down"]
        self.assertEqual(("ok", False), (verdict["status"], verdict["triggered"]))

    def test_cost_surge_not_run_when_baseline_cost_is_zero(self) -> None:
        base = {**self.S1, "measured_marketing_cost": 0.0}
        ai = {**self.S1, "strategy_id": "S2", "measured_marketing_cost": 50_000.0, "churn_rate": 0.2}
        r = summarize_strategy(ai, base)
        self.assertEqual("not_run", r["guardrails"]["retention_up_cost_surge"]["status"])
        self.assertIn("RETENTION_UP_COST_SURGE_NOT_RUN", r["flags"])

    def test_without_baseline_everything_is_not_computable(self) -> None:
        r = summarize_strategy({**self.S1, "strategy_id": "S2"}, None)
        self.assertIsNone(r["incremental_profit_vs_S1"])
        self.assertIn("기준선", r["incremental_profit_status"])
        self.assertIsNone(r["roi"])
        self.assertEqual({"not_run"}, {v["status"] for v in r["guardrails"].values()})


if __name__ == "__main__":
    unittest.main()
