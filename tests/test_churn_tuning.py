"""#215 2부 — XGBoost · LightGBM · Validation 튜닝(Grid) · 시간 순서 검증.

  1. 설정 — 튜닝 격자(목록) 규칙이 빈 목록 · 중복 · 목록 아님을 거부한다(의존성 없이).
  2. 모델 — XGBoost · LightGBM 이 config 값으로 만들어지고, 학습 · 저장(pickle)된다.
  3. 튜닝 — 격자 전체를 **검증 데이터로만** 비교하고, 고른 값으로 확정 모델을 학습한다.
  4. 시간 순서 검증 — 앞 기준일 데이터가 오면 그것으로 고르고, 없거나 한 값뿐이면 그렇게 적는다.
  5. 패키지가 없으면 그 모델만 빠지고 사유가 남는다(조용히 건너뛰지 않는다).
시뮬레이터를 쓰지 않는다 — 합성 데이터다.
"""

from __future__ import annotations

import importlib.util
import pickle
import unittest
from unittest import mock

from tests.test_feature_sprint_table import HAVE_ML, SKIP_REASON

HAVE_BOOST = all(importlib.util.find_spec(m) is not None for m in ("xgboost", "lightgbm"))
BOOST_SKIP = "BLOCKED: xgboost/lightgbm 미설치 — pip install -r requirements.txt (통과가 아니다)"
#: 시험용 작은 격자 — 조합 수만 줄였다. 고르는 규칙은 config 격자와 같다.
SMALL_TUNING = {"enabled": True, "metric": "roc_auc", "grids": {
    "random_forest": {"min_samples_leaf": (3, 10), "n_estimators": (50,)},
    "hist_gb": {"learning_rate": (0.05, 0.1), "max_leaf_nodes": (15,)},
    "xgboost": {"max_depth": (3, 4), "learning_rate": (0.1,)},
    "lightgbm": {"num_leaves": (15,), "learning_rate": (0.05, 0.1)},
}}


class TestListRule(unittest.TestCase):
    """튜닝 격자 한 축 — 의존성 없이."""

    def test_rejects_empty_duplicate_and_non_list(self) -> None:
        from src.decision import config as dc

        rule = dc._list(dc._int(1))
        for bad in ([], [3, 3], "3", 3, [0]):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                rule.check(bad)
        self.assertEqual((1, 3, 10), rule.check([1, 3, 10]))
        self.assertEqual((1, 3), rule.check((1, 3)))  # 코드로 만든 설정(tuple)도 받는다

    def test_schema_declares_every_tuned_model(self) -> None:
        from src.decision import config as dc

        grids = dc.MODEL_SCHEMA["churn"]["tuning"]["grids"]
        self.assertEqual({"random_forest", "hist_gb", "xgboost", "lightgbm"}, set(grids))
        for name, axes in grids.items():
            for axis in axes:
                self.assertIn(axis, dc.MODEL_SCHEMA["churn"]["models"][name], f"{name}.{axis} 는 모델 인자여야 한다")


@unittest.skipUnless(HAVE_ML and HAVE_BOOST, f"{SKIP_REASON} · {BOOST_SKIP}")
class TestBoostingModels(unittest.TestCase):
    def test_built_from_config_and_round_trip(self) -> None:
        from src.decision import churn
        from tests.test_decision_persistence import _data

        X, t, y, _ = _data(61, n=400)
        Xp, yv = churn._prepare(X.loc[t == "T0"], y.loc[t == "T0"])
        for name in ("xgboost", "lightgbm"):
            with self.subTest(name):
                model = churn.make_model(name, 5)
                estimator = model[-1]
                for key, value in churn.CONFIG.models[name].items():
                    self.assertEqual(value, estimator.get_params()[key], f"{name}.{key}")
                self.assertEqual(5, estimator.get_params()["random_state"])
                model.fit(Xp, yv)
                again = pickle.loads(pickle.dumps(model))  # #214 모델 저장과 같은 경로
                self.assertEqual(model.predict_proba(Xp).tolist(), again.predict_proba(Xp).tolist())
        tuned = churn.make_model("xgboost", 5, {"max_depth": 3})[-1]
        self.assertEqual(3, tuned.get_params()["max_depth"])


@unittest.skipUnless(HAVE_ML and HAVE_BOOST, f"{SKIP_REASON} · {BOOST_SKIP}")
class TestTuningAndTemporalValidation(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        from src.decision import churn
        from tests.test_decision_persistence import _data

        X, t, y, _ = _data(71, n=800)
        prior_X, _, prior_y, _ = _data(72, n=800)  # 앞 기준일 대역 — 다른 고객, 같은 생성 규칙
        cls.X, cls.y = X.loc[t == "T0"], y.loc[t == "T0"]
        cls.prior = (prior_X, prior_y)
        with mock.patch.object(churn, "TUNING", SMALL_TUNING):
            cls.with_prior = churn.evaluate_churn_models(cls.X, cls.y, seed=4, prior=cls.prior)
            cls.without = churn.evaluate_churn_models(cls.X, cls.y, seed=4)
            cls.final = churn.fit_best_churn(cls.X, cls.y, 4, eval_result=cls.with_prior)

    def test_prior_drives_tuning_and_selection(self) -> None:
        r = self.with_prior
        self.assertEqual("temporal_validation", r["selection_basis"])
        self.assertEqual("ok", r["temporal_validation_data"]["status"])
        proposed = [m for m in r["models"] if m["kind"] == "proposed"]
        self.assertEqual(["random_forest", "hist_gb", "xgboost", "lightgbm"], [m["name"] for m in proposed])
        for m in proposed:
            grid = SMALL_TUNING["grids"][m["name"]]
            n_combos = 1
            for values in grid.values():
                n_combos *= len(values)
            self.assertEqual(n_combos, len(m["tuning"]["grid"]), m["name"])       # 격자 전체를 남긴다
            self.assertEqual("temporal_validation", m["tuning"]["basis"])
            best = max(m["tuning"]["grid"], key=lambda row: row["score"])
            self.assertEqual(best["score"], next(row["score"] for row in m["tuning"]["grid"]
                                                 if row["params"] == m["params"]))
        for m in r["models"]:  # 기준선까지 모두 같은 시간 순서 검증을 받는다
            self.assertEqual(len(self.y), m["temporal_validation"]["n_valid"])
        chosen = max(proposed, key=lambda m: m["temporal_validation"]["roc_auc"])
        self.assertEqual(chosen["name"], r["best_proposed"])
        self.assertEqual(chosen["params"], r["best_params"])

    def test_final_model_uses_the_tuned_values(self) -> None:
        r = self.with_prior
        self.assertEqual(r["best_proposed"], self.final.name)
        self.assertEqual(r["best_params"], self.final.params)
        params = self.final.estimator[-1].get_params()
        for key, value in r["best_params"].items():
            self.assertEqual(value, params[key], key)

    def test_without_prior_it_says_so(self) -> None:
        r = self.without
        self.assertEqual("random_cv", r["selection_basis"])
        self.assertEqual("not_run", r["temporal_validation_data"]["status"])
        self.assertNotIn("temporal_validation", r["models"][0])
        self.assertTrue(all(m["tuning"]["basis"].startswith("inner_cv")
                            for m in r["models"] if m["kind"] == "proposed"))
        self.assertIn("낙관적", r["selection_note"])

    def test_single_class_prior_is_refused_not_used(self) -> None:
        from src.decision import churn

        prior_X, prior_y = self.prior
        with mock.patch.object(churn, "TUNING", {**SMALL_TUNING, "enabled": False}):
            r = churn.evaluate_churn_models(self.X, self.y, seed=4, prior=(prior_X, prior_y * 0))
        self.assertEqual("not_run", r["temporal_validation_data"]["status"])
        self.assertEqual("random_cv", r["selection_basis"])


@unittest.skipUnless(HAVE_ML, SKIP_REASON)
class TestMissingPackage(unittest.TestCase):
    def test_missing_boosting_package_is_recorded_not_skipped_silently(self) -> None:
        from src.decision import churn
        from tests.test_decision_persistence import _data

        X, t, y, _ = _data(81, n=400)
        real = churn.model_unavailable
        fake = lambda name: "xgboost 미설치 — 시험" if name == "xgboost" else real(name)  # noqa: E731
        with mock.patch.object(churn, "model_unavailable", fake), \
                mock.patch.object(churn, "TUNING", {**SMALL_TUNING, "enabled": False}):
            r = churn.evaluate_churn_models(X.loc[t == "T0"], y.loc[t == "T0"], seed=2)
        self.assertNotIn("xgboost", [m["name"] for m in r["models"]])
        self.assertIn({"name": "xgboost", "reason": "xgboost 미설치 — 시험"}, r["models_unavailable"])


if __name__ == "__main__":
    unittest.main()
