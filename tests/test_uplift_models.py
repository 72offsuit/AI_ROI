"""Uplift 메타러너 · Qini/AUUC · 평가 (이슈 #145).

합성 데이터는 이 파일에서 numpy 로 직접 만든다 — 시뮬레이터 코드를 참고하지 않는다.
"""

from __future__ import annotations

import json
import unittest
from importlib.util import find_spec

DEPS = all(find_spec(m) for m in ("numpy", "pandas", "sklearn"))
REASON = "BLOCKED: numpy/pandas/scikit-learn 미설치"

if DEPS:
    import numpy as np
    import pandas as pd

    from src.decision.uplift import (
        TREATED, evaluate_on_benchmark, evaluate_uplift_models, fit_uplift,
        predict_cate, qini_curve, uplift_at_k,
    )


def synthetic(n=2500, seed=0, arms=("T0", "T1", "T3"), probs=(0.4, 0.3, 0.3)):
    """x1>0 인 고객에게만 T3 효과 +0.25, T1 은 모두에게 +0.05, 일부에 역효과는 없음."""
    rng = np.random.default_rng(seed)
    idx = [f"C{i:08d}" for i in range(n)]
    X = pd.DataFrame({"x1": rng.normal(size=n), "x2": rng.normal(size=n),
                      "seg": rng.choice(["a", "b", "c"], n)}, index=idx)
    t = pd.Series(rng.choice(list(arms), n, p=list(probs)), index=idx)
    base = 1 / (1 + np.exp(-(0.6 * X["x2"] - 0.3)))
    tau = np.where(t == "T3", 0.25 * (X["x1"] > 0), 0.0) + np.where(t == "T1", 0.05, 0.0)
    y = pd.Series((rng.random(n) < np.clip(base + tau, 0, 1)).astype(int), index=idx)
    true_t3 = pd.Series(0.25 * (X["x1"] > 0), index=idx)
    return X, t, y, true_t3


@unittest.skipUnless(DEPS, REASON)
class TestQiniByHand(unittest.TestCase):
    def test_tiny_example(self) -> None:
        q = qini_curve([4, 3, 2, 1], [1, 0, 1, 0], [1, 0, 0, 0])
        self.assertAlmostEqual(0.0625, q["qini"])
        self.assertAlmostEqual(0.28125, q["auuc"])
        self.assertEqual([0.0, 0.0], q["curve"][0])
        self.assertEqual([1.0, 0.5], q["curve"][-1])

    def test_oracle_beats_reversed(self) -> None:
        X, t, y, true = synthetic(seed=3)
        sel = t.isin(["T0", "T3"]).to_numpy()
        tr = (t[sel] == "T3").to_numpy()
        good = qini_curve(true[sel].to_numpy() + 1e-9 * X["x1"][sel].to_numpy(), tr, y[sel].to_numpy())
        bad = qini_curve(-true[sel].to_numpy() - 1e-9 * X["x1"][sel].to_numpy(), tr, y[sel].to_numpy())
        self.assertGreater(good["qini"], 0)
        self.assertLess(bad["qini"], 0)

    def test_curve_point_cap(self) -> None:
        rng = np.random.default_rng(0)
        q = qini_curve(rng.random(1000), rng.random(1000) < 0.5, rng.random(1000) < 0.3)
        self.assertLessEqual(len(q["curve"]), 50)

    def test_uplift_at_k_empty_arm_is_none(self) -> None:
        self.assertIsNone(uplift_at_k([3, 2, 1, 0], [1, 1, 0, 0], [1, 0, 0, 0], 0.25))


@unittest.skipUnless(DEPS, REASON)
class TestMetaLearners(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.X, cls.t, cls.y, cls.true = synthetic()

    def test_columns_and_missing_arms_are_nan(self) -> None:
        for m in ("s_learner", "t_learner", "x_learner"):
            with self.subTest(method=m):
                cate = predict_cate(fit_uplift(self.X, self.t, self.y, m, seed=0), self.X.iloc[:50])
                self.assertEqual(list(TREATED), list(cate.columns))
                self.assertTrue(cate["T2"].isna().all())   # 표본 없는 처치군 = 계산 불가
                self.assertTrue(cate["T4"].isna().all())
                self.assertFalse(cate["T3"].isna().any())

    def test_t_and_x_learner_recover_heterogeneity(self) -> None:
        for m in ("t_learner", "x_learner"):
            with self.subTest(method=m):
                cate = predict_cate(fit_uplift(self.X, self.t, self.y, m, seed=0), self.X)
                pos = cate.loc[self.X["x1"] > 0.5, "T3"].mean()
                neg = cate.loc[self.X["x1"] < -0.5, "T3"].mean()
                self.assertGreater(pos - neg, 0.1)

    def test_same_seed_same_result(self) -> None:
        a = predict_cate(fit_uplift(self.X, self.t, self.y, "x_learner", seed=7), self.X.iloc[:100])
        b = predict_cate(fit_uplift(self.X, self.t, self.y, "x_learner", seed=7), self.X.iloc[:100])
        pd.testing.assert_frame_equal(a, b)

    def test_missing_outcome_is_rejected_not_filled(self) -> None:
        y = self.y.astype(float).copy()
        y.iloc[0] = np.nan
        with self.assertRaises(ValueError):
            fit_uplift(self.X, self.t, y, "t_learner")

    def test_unknown_arm_rejected(self) -> None:
        t = self.t.copy()
        t.iloc[0] = "T9"
        with self.assertRaises(ValueError):
            fit_uplift(self.X, t, self.y, "t_learner")


@unittest.skipUnless(DEPS, REASON)
class TestEvaluate(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.X, cls.t, cls.y, cls.true = synthetic(n=3000, seed=1)
        rng = np.random.default_rng(9)
        cls.churn = pd.Series(rng.random(len(cls.X)), index=cls.X.index)
        cls.res = evaluate_uplift_models(cls.X, cls.t, cls.y, seed=0, churn_p=cls.churn)

    def test_shape(self) -> None:
        r = self.res
        self.assertEqual(3000, r["n"])
        self.assertEqual("T3", r["primary_arm"])
        self.assertEqual(["T2", "T4"], r["not_evaluable_arms"])
        names = [m["name"] for m in r["models"]]
        self.assertEqual(["random", "churn_risk_targeting", "s_learner", "t_learner", "x_learner"], names)
        kinds = {m["name"]: m["kind"] for m in r["models"]}
        self.assertEqual("baseline", kinds["s_learner"])
        self.assertEqual("proposed", kinds["t_learner"])
        self.assertIsNone(r["ate"]["T2"]["value"])
        lo, hi = r["ate"]["T3"]["ci95"]
        self.assertLess(lo, r["ate"]["T3"]["value"])
        self.assertLess(r["ate"]["T3"]["value"], hi)
        json.dumps(r)   # 게시 가능한 형태

    def test_proposed_beat_random_on_strong_heterogeneity(self) -> None:
        q = {m["name"]: m["qini"] for m in self.res["models"]}
        self.assertGreater(q["t_learner"], 0.0)
        self.assertGreater(q["x_learner"], 0.0)

    def test_without_churn_p_baseline_is_not_run(self) -> None:
        r = evaluate_uplift_models(self.X.iloc[:1500], self.t.iloc[:1500], self.y.iloc[:1500],
                                   seed=0, methods=("t_learner",))
        row = [m for m in r["models"] if m["name"] == "churn_risk_targeting"][0]
        self.assertEqual("not_run", row["status"])
        self.assertIsNone(row["qini"])

    def test_singleton_arm_falls_back_to_random_split(self) -> None:
        t = self.t.iloc[:1500].copy()
        t.iloc[0] = "T2"                       # 표본 1 개 처치군 — 층화 불가
        r = evaluate_uplift_models(self.X.iloc[:1500], t, self.y.iloc[:1500], seed=0, methods=("t_learner",))
        self.assertEqual("random", r["split"])
        self.assertIn("T2", r["not_evaluable_arms"])

    def test_benchmark_binary(self) -> None:
        df = self.X.copy()
        df["arm"] = np.where(self.t == "T0", "No E-Mail", np.where(self.t == "T3", "Mens E-Mail", "Womens E-Mail"))
        df["visit"] = self.y
        r = evaluate_on_benchmark(df, ["x1", "x2", "seg"], "arm", "visit",
                                  treatment_value="Mens E-Mail", methods=("t_learner",))
        self.assertEqual("T1", r["primary_arm"])
        self.assertEqual("No E-Mail", r["benchmark"]["control_value"])
        self.assertGreater([m for m in r["models"] if m["name"] == "t_learner"][0]["qini"], 0)


if __name__ == "__main__":
    unittest.main()
