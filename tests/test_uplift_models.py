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
    """x1>0 인 고객에게만 T3 효과 +0.25, T1 은 모두에게 +0.05, 일부에 역효과는 없음.

    실제 Feature 표(51 개 float, 결손 = NaN)를 흉내 내 x2 · x3 · seg 에 결손을 섞는다.
    """
    rng = np.random.default_rng(seed)
    idx = [f"C{i:08d}" for i in range(n)]
    X = pd.DataFrame({"x1": rng.normal(size=n), "x2": rng.normal(size=n),
                      "x3": rng.exponential(30.0, size=n),
                      "seg": rng.choice(["a", "b", "c"], n)}, index=idx)
    x2_true = X["x2"].copy()
    X.loc[rng.random(n) < 0.10, "x2"] = np.nan
    X.loc[rng.random(n) < 0.30, "x3"] = np.nan
    X.loc[rng.random(n) < 0.05, "seg"] = None
    t = pd.Series(rng.choice(list(arms), n, p=list(probs)), index=idx)
    base = 1 / (1 + np.exp(-(0.6 * x2_true - 0.3)))
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

    def test_feature_nan_is_kept_and_predicted(self) -> None:
        self.assertTrue(self.X["x2"].isna().any())
        cate = predict_cate(fit_uplift(self.X, self.t, self.y, "t_learner", seed=0), self.X)
        self.assertFalse(cate.loc[self.X["x2"].isna(), "T3"].isna().any())

    def test_missing_outcome_is_excluded_and_counted_not_filled(self) -> None:
        y = self.y.astype(float).copy()
        y.iloc[:7] = np.nan
        model = fit_uplift(self.X, self.t, y, "t_learner")
        self.assertEqual(7, model.n_outcome_missing_excluded)
        self.assertEqual(len(self.X) - 7, sum(model.n_by_arm.values()))

    def test_unknown_arm_rejected(self) -> None:
        t = self.t.copy()
        t.iloc[0] = "T9"
        with self.assertRaises(ValueError):
            fit_uplift(self.X, t, self.y, "t_learner")


@unittest.skipUnless(DEPS, REASON)
class TestDegenerateFeatureColumns(unittest.TestCase):
    """회귀 — 전부 NaN 인 Feature 열이 HistGB 비닝을 멈추던 결함(스프린트 통합 스모크).

    sklearn 1.9 에서 ``ValueError: window shape cannot be larger than input array shape``.
    """

    @classmethod
    def setUpClass(cls) -> None:
        X, t, y, _ = synthetic(n=2500, seed=11)
        X = X.copy()
        X["all_nan"] = np.nan                                   # 전체가 결측
        X["constant"] = 5.0                                     # 결측 없는 상수
        X["nan_in_T3_only"] = np.random.default_rng(1).normal(size=len(X))
        X.loc[t == "T3", "nan_in_T3_only"] = np.nan             # 한 처치군 안에서만 전부 결측
        cls.X, cls.t, cls.y = X, t, y

    def test_all_methods_fit_and_predict(self) -> None:
        for m in ("s_learner", "t_learner", "x_learner"):
            with self.subTest(method=m):
                model = fit_uplift(self.X, self.t, self.y, m, seed=0)
                self.assertEqual(["all_nan"], model.dropped_features["all_nan"])
                self.assertEqual(["constant"], model.dropped_features["constant"])
                self.assertNotIn("all_nan", model.columns)
                cate = predict_cate(model, self.X)
                self.assertFalse(cate[["T1", "T3"]].isna().any().any())
                if m != "s_learner":
                    self.assertIn("nan_in_T3_only", model.submodel_dropped["T3"])

    def test_predict_ignores_values_that_appear_later(self) -> None:
        """학습 때 제외한 열에 예측 시점 값이 생겨도 같은 열 집합으로 예측한다."""
        model = fit_uplift(self.X, self.t, self.y, "t_learner", seed=0)
        X2 = self.X.copy()
        X2["all_nan"] = 1.0
        pd.testing.assert_frame_equal(predict_cate(model, self.X), predict_cate(model, X2))

    def test_evaluate_records_screening(self) -> None:
        r = evaluate_uplift_models(self.X, self.t, self.y, seed=0)
        scr = r["feature_screening"]
        self.assertIn("all_nan", scr["train_dropped"]["all_nan"])
        self.assertIn("constant", scr["train_dropped"]["constant"])
        self.assertIn("t_learner", scr["submodel_extra_dropped"])
        self.assertIsNotNone(r["best_method"])
        json.dumps(r)

    def test_every_feature_unusable_falls_back_to_arm_means(self) -> None:
        X = pd.DataFrame({"a": np.nan, "b": 1.0}, index=self.X.index)
        model = fit_uplift(X, self.t, self.y, "t_learner", seed=0)
        cate = predict_cate(model, X)
        ate = self.y[self.t == "T3"].mean() - self.y[self.t == "T0"].mean()
        self.assertTrue(np.allclose(cate["T3"], ate))


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
        self.assertIn(r["best_method"], ("t_learner", "x_learner"))
        self.assertIn("validation", r["best_method_selection"]["basis"])
        self.assertEqual(0, r["n_outcome_missing_excluded"])
        # ID만 있는 외부 점수는 fit 계보가 없으므로 위험도 행만 거부해야 한다.
        risk = next(m for m in r["models"] if m["name"] == "churn_risk_targeting")
        self.assertEqual("not_run", risk["status"])
        self.assertIn("계보", risk["reason"])
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

    def test_orchestrator_call_shape(self) -> None:
        """오케스트레이션 호출: evaluate(X, treatment, retention, seed) → fit(…, best_method)."""
        y = self.y.astype(float).copy()
        y.iloc[:5] = np.nan
        r = evaluate_uplift_models(self.X.iloc[:2000], self.t.iloc[:2000], y.iloc[:2000], 3)
        self.assertEqual(5, r["n_outcome_missing_excluded"])
        model = fit_uplift(self.X.iloc[:2000], self.t.iloc[:2000], y.iloc[:2000], r["best_method"])
        self.assertEqual(r["best_method"], model.method)

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


@unittest.skipUnless(DEPS, REASON)
class TestRegularizationTuning(unittest.TestCase):
    """#217 3부 — DR-217-uplift-tuning 에 결과 전에 고정한 규칙(후보 순서 · 동점 · Test 미사용 · 비활성)."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.X, cls.t, cls.y, _ = synthetic(n=2400, seed=4)
        cls.res = evaluate_uplift_models(cls.X, cls.t, cls.y, seed=0, methods=("s_learner", "t_learner", "x_learner"))

    def test_candidates_start_with_current_then_grid_product(self) -> None:
        from src.decision import uplift

        base = dict(uplift.BASE_LEARNER)
        tuning = {"enabled": True, "metric": "qini", "grid": {"min_samples_leaf": (40, 80, 200), "max_depth": (2, 3)}}
        got = [(c["max_depth"], c["min_samples_leaf"]) for c in uplift.regularization_candidates(base, tuning)]
        self.assertEqual([(3, 80), (2, 40), (2, 80), (2, 200), (3, 40), (3, 200)], got)  # 현행값 첫째 · 중복 한 번
        for c in uplift.regularization_candidates(base, tuning):
            self.assertEqual({k: v for k, v in base.items() if k not in ("max_depth", "min_samples_leaf")},
                             {k: v for k, v in c.items() if k not in ("max_depth", "min_samples_leaf")})
        self.assertEqual([base], uplift.regularization_candidates(base, {**tuning, "enabled": False}))

    def test_selection_scores_every_candidate_and_reports_choice(self) -> None:
        from src.decision import uplift

        sel = self.res["best_method_selection"]
        configs = sel["tuning"]["configs"]
        self.assertEqual(uplift.regularization_candidates(), configs)
        self.assertEqual(len(configs) * 2, len(sel["tuning"]["grid"]))       # 제안 메타러너 2 × 규제 후보
        self.assertEqual(["t_learner", "x_learner"] * len(configs), [r["method"] for r in sel["tuning"]["grid"]])
        best = max((r for r in sel["tuning"]["grid"] if r["qini"] is not None), key=lambda r: r["qini"])
        self.assertEqual(best["method"], sel["best_method"])
        self.assertEqual(configs[best["config_id"]], sel["base_learner"])
        self.assertEqual(sel["base_learner"], self.res["base_learner"])
        self.assertEqual(best["config_id"] == 0, sel["base_learner_is_current"])
        # Test 의 모델 행은 고른 규제로 학습했고, 현행값 행은 보고만
        report = self.res["tuning_report"]
        self.assertEqual(sel["base_learner"], report["chosen_base_learner"])
        if report["chosen_is_current"]:
            self.assertIsNone(report["test_current_regularization"])
        else:
            self.assertEqual(f"{sel['best_method']}@current", report["test_current_regularization"]["name"])
        json.dumps(self.res)

    def test_ties_go_to_the_earlier_candidate(self) -> None:
        from unittest import mock

        from src.decision import uplift

        # 선택 함수만 — 모든 후보의 Validation Qini 가 같으면 첫 후보(현행값 · t_learner)
        with mock.patch.object(uplift, "qini_curve", return_value={"qini": 0.01}):
            sel = uplift._select_method(self.X.iloc[:1200], self.t.iloc[:1200], self.y.iloc[:1200],
                                        ("t_learner", "x_learner"), "T3", 0, True)
        self.assertEqual({0.01}, {r["qini"] for r in sel["tuning"]["grid"]})
        self.assertEqual(("t_learner", True), (sel["best_method"], sel["base_learner_is_current"]))
        self.assertEqual(dict(uplift.BASE_LEARNER), sel["base_learner"])

    def test_test_labels_do_not_change_the_choice(self) -> None:
        test_ids = self.res["evaluation_split"]["test_customer_ids"]
        flipped = self.y.copy()
        flipped.loc[test_ids] = 1 - flipped.loc[test_ids]
        again = evaluate_uplift_models(self.X, self.t, flipped, seed=0, methods=("s_learner", "t_learner", "x_learner"))
        self.assertEqual(self.res["best_method_selection"]["tuning"]["grid"],
                         again["best_method_selection"]["tuning"]["grid"])
        self.assertEqual(self.res["base_learner"], again["base_learner"])

    def test_disabled_tuning_keeps_the_current_regularization(self) -> None:
        from unittest import mock

        from src.decision import uplift

        off = {**dict(uplift.TUNING), "enabled": False}
        with mock.patch.object(uplift, "TUNING", off):
            r = evaluate_uplift_models(self.X.iloc[:1200], self.t.iloc[:1200], self.y.iloc[:1200], seed=0,
                                       methods=("t_learner", "x_learner"))
        sel = r["best_method_selection"]
        self.assertEqual(1, len(sel["tuning"]["configs"]))
        self.assertIs(False, sel["tuning"]["enabled"])
        self.assertEqual(dict(uplift.BASE_LEARNER), r["base_learner"])

    def test_fit_records_and_uses_the_given_regularization(self) -> None:
        from src.decision import uplift

        default = fit_uplift(self.X.iloc[:1200], self.t.iloc[:1200], self.y.iloc[:1200], "t_learner")
        self.assertEqual(dict(uplift.BASE_LEARNER), default.base_learner)
        shallow = {**uplift.BASE_LEARNER, "max_depth": 2, "min_samples_leaf": 40}
        model = fit_uplift(self.X.iloc[:1200], self.t.iloc[:1200], self.y.iloc[:1200], "t_learner", params=shallow)
        self.assertEqual(shallow, model.base_learner)
        est = model.models["T0"].est
        self.assertEqual((2, 40), (est.max_depth, est.min_samples_leaf))


@unittest.skipUnless(DEPS, REASON)
class Test179TiedEvaluation(unittest.TestCase):
    def test_ties_are_invariant_for_area_curve_and_fractional_topk(self):
        import itertools
        from src.decision.uplift import uplift_at_k_details, METRIC_VERSION
        score = np.array([3, 2, 1, 1, 1, 1, 0, 0, 0, 0], dtype=float)
        treated = np.array([1, 0, 1, 1, 0, 0, 1, 0, 1, 0])
        y = np.array([1, 0, 1, 0, 1, 0, 0, 0, 0, 0])
        reference = qini_curve(score, treated, y)
        for order in itertools.permutations(range(2, 6)):
            ids = [0, 1, *order, 6, 7, 8, 9]
            q = qini_curve(score[ids], treated[ids], y[ids])
            self.assertEqual(reference, q)
            self.assertAlmostEqual(2 / 3, uplift_at_k(score[ids], treated[ids], y[ids], 0.3))
        top = uplift_at_k_details(score, treated, y, 0.3)
        self.assertEqual(3, top["nominal_k"])
        self.assertEqual(3, top["effective_k"])
        self.assertEqual(0.25, top["boundary_weight"])
        self.assertEqual(1.5, top["weight_treated"])
        self.assertEqual(1.5, top["weight_control"])
        self.assertEqual(METRIC_VERSION, reference["metric_version"])
        # 동점 1명 무작위 추출 후 비율을 낸 평균은 3/4로 비례 가중 2/3과 다르다.
        draws = []
        for chosen in range(2, 6):
            ids = [0, 1, chosen]
            tt = treated[ids].astype(bool)
            draws.append(y[ids][tt].mean() - y[ids][~tt].mean())
        self.assertAlmostEqual(0.75, np.mean(draws))

    def test_all_equal_scores_have_only_endpoints_and_random_area(self):
        for points in (2, 50):
            q = qini_curve([0] * 4, [1, 1, 0, 0], [1, 0, 0, 0], points=points)
            self.assertAlmostEqual(0, q["qini"])
            self.assertAlmostEqual(0.25, q["auuc"])
            self.assertEqual([[0.0, 0.0], [1.0, 0.5]], q["curve"])
            self.assertEqual(1, q["score_ties"]["tied_customer_fraction"])
        self.assertAlmostEqual(0.5, uplift_at_k([0] * 4, [1, 1, 0, 0], [1, 0, 0, 0], 0.25))

    def test_display_sampling_does_not_change_area_or_add_tie_interior(self):
        score = np.repeat(np.arange(100), 10)
        treated = np.arange(1000) % 2
        y = np.arange(1000) % 3 == 0
        small = qini_curve(score, treated, y, points=7)
        full = qini_curve(score, treated, y, points=200)
        self.assertEqual(small["qini"], full["qini"])
        self.assertEqual(small["auuc"], full["auuc"])
        self.assertLessEqual(len(small["curve"]), 7)
        self.assertTrue(all(round(x * 1000) % 10 == 0 for x, _ in small["curve"]))

    def test_invalid_values_are_rejected_not_sorted_into_a_score(self):
        for score, t, y in [([np.inf, 0], [1, 0], [1, 0]), ([0, 1], [1, 0], [np.nan, 0]),
                             ([0, 1], [2, 0], [1, 0]), ([1], [1, 0], [1, 0])]:
            with self.subTest(score=score), self.assertRaises(ValueError):
                qini_curve(score, t, y)
        for fraction in (0, 1.1, np.nan):
            with self.assertRaises(ValueError):
                uplift_at_k([1, 0], [1, 0], [1, 0], fraction)


@unittest.skipUnless(DEPS, REASON)
class Test179RiskConnection(unittest.TestCase):
    def setUp(self):
        self.X, self.t, self.y, _ = synthetic(n=600, seed=17)
        self.X = self.X[["x1", "x2", "x3"]]
        self.y = self.y.astype(float)
        self.y.iloc[:13] = np.nan

    def factory(self, calls):
        from src.decision.churn import make_risk_model_factory
        base = make_risk_model_factory(7)
        def factory():
            underlying = base()
            class Spy:
                def fit(self, X, y):
                    calls.append({"X": X.copy(), "y": y.copy()})
                    underlying.fit(X, y)
                    self.classes_ = underlying.classes_
                    return self
                def predict_proba(self, X):
                    values = underlying.predict_proba(X)
                    calls[-1].update(test=X.copy(), proba=values.copy())
                    return values
            return Spy()
        factory.specification = base.specification
        return factory

    def run_eval(self, **kwargs):
        return evaluate_uplift_models(self.X, self.t, self.y, seed=7, methods=("s_learner", "t_learner"), **kwargs)

    @staticmethod
    def risk(result):
        return next(row for row in result["models"] if row["name"] == "churn_risk_targeting")

    def test_actual_evaluate_fit_uses_only_cleaned_train_controls_and_no_test_labels(self):
        calls = []
        first = self.run_eval(risk_model_factory=self.factory(calls))
        self.assertEqual("ok", self.risk(first)["status"])
        self.assertEqual(1, len(calls))
        train = pd.Index(first["evaluation_split"]["train_customer_ids"])
        test = pd.Index(first["evaluation_split"]["test_customer_ids"])
        expected = train[self.t.loc[train] == "T0"]
        self.assertEqual(set(expected), set(calls[0]["X"].index))
        self.assertEqual(set(), set(expected) & set(test))
        self.assertEqual(13, first["n_outcome_missing_excluded"])
        pd.testing.assert_series_equal(1 - self.y.loc[expected], calls[0]["y"])
        before = self.y.copy()
        self.y.loc[test] = 1 - self.y.loc[test]
        later = []
        second = self.run_eval(risk_model_factory=self.factory(later))
        pd.testing.assert_frame_equal(calls[0]["X"], later[0]["X"])
        pd.testing.assert_series_equal(calls[0]["y"], later[0]["y"])
        np.testing.assert_array_equal(calls[0]["proba"], later[0]["proba"])
        self.assertEqual(first["risk_baseline"]["model_spec"], second["risk_baseline"]["model_spec"])
        self.assertTrue(self.y.isna().equals(before.isna()))
        self.assertEqual(len(test), first["risk_baseline"]["test_n"])
        primary_n = int(self.t.loc[test].isin(["T0", first["primary_arm"]]).sum())
        self.assertEqual(primary_n, self.risk(first)["score_ties"]["n"])

    def test_one_class_does_not_call_factory_and_keeps_other_models(self):
        self.y.loc[self.t == "T0"] = 1.0
        calls = []
        result = self.run_eval(risk_model_factory=self.factory(calls))
        self.assertEqual([], calls)
        self.assertEqual("not_run", self.risk(result)["status"])
        self.assertTrue(all(row["qini"] is not None for row in result["models"] if row["name"] != "churn_risk_targeting"))

    def test_conflicting_inputs_do_not_call_factory(self):
        calls = []
        result = self.run_eval(churn_p=pd.Series(0.5, index=self.X.index), risk_model_factory=self.factory(calls))
        self.assertEqual([], calls)
        self.assertEqual("not_run", self.risk(result)["status"])
        self.assertIn("동시 입력", self.risk(result)["reason"])

    def test_external_predictions_are_disabled_even_with_plausible_lineage(self):
        calls = []
        base = self.run_eval(risk_model_factory=self.factory(calls))
        cp = pd.Series(calls[0]["proba"][:, 1], index=calls[0]["test"].index)
        cp.attrs.update(protocol="train-controls-to-test-v1", fit_customer_ids=calls[0]["X"].index.tolist(),
                        test_ids_sha256=base["evaluation_split"]["test_ids_sha256"],
                        model_spec=base["risk_baseline"]["model_spec"])
        cases = [cp.copy(), cp.to_numpy(), cp.iloc[:-1].copy(), pd.concat([cp, cp.iloc[:1]]),
                 cp.copy(), cp.copy(), cp.copy(), cp.copy()]
        cases[4].iloc[0] = np.nan
        cases[5].iloc[0] = np.inf
        cases[6].iloc[0] = 1.01
        cases[7].attrs.update(cp.attrs, model_spec={"name": "anything", "selection": "chosen_on_test"})
        for candidate in cases:
            with self.subTest(kind=type(candidate).__name__):
                result = self.run_eval(churn_p=candidate)
                self.assertEqual("not_run", self.risk(result)["status"])
                self.assertIn("비활성화", self.risk(result)["reason"])
                self.assertFalse(result["risk_baseline"]["external_predictions_supported"])
                self.assertTrue(all(row["qini"] is not None for row in result["models"] if row["name"] != "churn_risk_targeting"))
        result = evaluate_uplift_models(self.X, self.t, self.y, seed=7, churn_p=cases[7])
        names = {row["name"] for row in result["models"] if row["qini"] is not None}
        self.assertTrue({"s_learner", "t_learner", "x_learner"} <= names)

    def test_factory_failure_and_invalid_probability_are_isolated(self):
        def fail():raise RuntimeError("합성 학습 실패")
        self.assertEqual("not_run", self.risk(self.run_eval(risk_model_factory=fail))["status"])
        for probability in (np.nan, np.inf, -0.1, 1.1):
            class Invalid:
                def fit(self, X, y):self.classes_ = np.array([0, 1]);return self
                def predict_proba(self, X):return np.tile([1-probability, probability], (len(X), 1))
            result = self.run_eval(risk_model_factory=Invalid)
            self.assertEqual("not_run", self.risk(result)["status"])


if __name__ == "__main__":
    unittest.main()
