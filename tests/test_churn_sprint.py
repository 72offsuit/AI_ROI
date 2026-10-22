"""스프린트 1 Churn 평가 (이슈 #144). 픽스처 기준 — 여기 지표는 실제 결과가 아니다.

검사하는 것은 **형식과 규율**이다(결과 dict 계약, 임계를 학습 쪽에서만 정하는가, 같은 seed
재현, 우연보다 나은가). 특정 AUC 값을 고정하지 않는다 — 픽스처 숫자를 맞추는 테스트는
모델을 픽스처에 과적합시키는 압력이 된다.

실행:
    python -m unittest tests.test_churn_sprint -v
"""

from __future__ import annotations

import importlib.util
import unittest

from tests.test_feature_sprint_table import FIXTURE_T0, HAVE_ML, SKIP_REASON, make_events

HAVE_TORCH = importlib.util.find_spec("torch") is not None
TORCH_SKIP = "BLOCKED: 선택 의존성 torch 없음 (requirements-ml.txt, CI 비대상)"


def _fixture(n: int = 160):
    import pandas as pd

    from src.decision.data import _coerce
    from src.decision.features.sprint_table import build_feature_table, build_outcomes

    events = _coerce(pd.DataFrame.from_records(make_events(n_customers=n)))
    return events, build_feature_table(events, FIXTURE_T0), build_outcomes(events, FIXTURE_T0)


@unittest.skipUnless(HAVE_ML, SKIP_REASON)
class TestChurnEvaluation(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        from src.decision.churn import evaluate_churn_models

        cls.events, cls.X, cls.y = _fixture()
        cls.result = evaluate_churn_models(cls.X, cls.y["churn"], seed=11)

    def test_result_contract(self) -> None:
        r = self.result
        self.assertEqual("index 이후 42일 무구매", r["label_def"])
        self.assertEqual(len(self.X), r["n"])
        self.assertAlmostEqual(float(self.y["churn"].mean()), r["pos_rate"])
        names = [m["name"] for m in r["models"]]
        self.assertEqual(["rule_recency", "logistic_regression", "random_forest", "hist_gb"], names)
        kinds = {m["name"]: m["kind"] for m in r["models"]}
        self.assertEqual("baseline", kinds["rule_recency"])
        self.assertEqual("baseline", kinds["logistic_regression"])
        self.assertEqual("proposed", kinds["random_forest"])
        self.assertEqual("proposed", kinds["hist_gb"])
        for m in r["models"]:
            for metric in ("roc_auc", "pr_auc", "f1", "lift_at_10"):
                stats = m["cv"][metric]
                self.assertEqual(5, stats["n_folds"], (m["name"], metric))
                self.assertIsInstance(stats["mean"], float)
                self.assertGreaterEqual(stats["std"], 0.0)
        self.assertIn(r["importance_method"], ("shap", "permutation"))
        self.assertTrue(r["shap_top"])
        self.assertTrue(all(set(t) == {"feature", "mean_abs"} for t in r["shap_top"]))
        from src.decision.features.sprint_table import ALIASES, model_columns

        features = set(model_columns(self.X))
        self.assertTrue(all(t["feature"] in features for t in r["shap_top"]))
        self.assertEqual(len(features), r["n_features"])  # 별칭 열은 모델 입력이 아니다
        self.assertFalse(set(ALIASES) & {t["feature"] for t in r["shap_top"]})

    def test_models_beat_chance_on_signal_fixture(self) -> None:
        """신호가 있는 픽스처에서 우연(0.5)보다 낫다 — 파이프라인이 정보를 버리지 않았다는 뜻만."""
        for m in self.result["models"]:
            self.assertGreater(m["cv"]["roc_auc"]["mean"], 0.55, m["name"])

    def test_same_seed_same_result(self) -> None:
        from src.decision.churn import evaluate_churn_models

        again = evaluate_churn_models(self.X, self.y["churn"], seed=11)
        for a, b in zip(self.result["models"], again["models"]):
            self.assertAlmostEqual(a["cv"]["roc_auc"]["mean"], b["cv"]["roc_auc"]["mean"], places=10)

    def test_rule_threshold_comes_from_training_only(self) -> None:
        """규칙 임계는 학습 데이터만으로 정해진다 — 시험 쪽 라벨을 뒤집어도 같다."""
        import numpy as np

        from src.decision.churn import RecencyRule

        X, y = self.X, self.y["churn"].to_numpy()
        half = len(y) // 2
        a = RecencyRule().fit(X.iloc[:half], y[:half])
        flipped = y.copy()
        flipped[half:] = 1 - flipped[half:]
        b = RecencyRule().fit(X.iloc[:half], flipped[:half])
        self.assertEqual(a.threshold_days_, b.threshold_days_)
        self.assertTrue(np.isfinite(a.threshold_days_))

    def test_fit_predict_and_temporal_holdout(self) -> None:
        import pandas as pd

        from src.decision.churn import evaluate_temporal_holdout, fit_best_churn, predict_churn_proba
        from src.decision.features.sprint_table import build_feature_table, build_outcomes

        model = fit_best_churn(self.X, self.y["churn"], seed=11, eval_result=self.result)
        self.assertEqual(self.result["best_proposed"], model.name)
        proba = predict_churn_proba(model, self.X)
        self.assertEqual(list(self.X.index), list(proba.index))
        self.assertTrue(((proba >= 0) & (proba <= 1)).all())

        earlier = pd.Timestamp(FIXTURE_T0) - pd.Timedelta(days=42)
        X_tr = build_feature_table(self.events, earlier)
        y_tr = build_outcomes(self.events, earlier)["churn"]
        for factory in ("rule_recency", "hist_gb"):
            out = evaluate_temporal_holdout(factory, X_tr, y_tr, self.X, self.y["churn"], seed=11)
            self.assertEqual("temporal_holdout", out["scheme"])
            for metric in ("roc_auc", "pr_auc", "f1", "lift_at_10"):
                self.assertIn(metric, out)

    def test_temporal_holdout_binds_by_name_like_orchestration(self) -> None:
        """#154 `call_by_name` 과 같은 방식(시그니처의 이름만 골라 키워드로)으로 부를 수 있다."""
        import inspect

        import pandas as pd

        from src.decision.churn import evaluate_temporal_holdout, fit_best_churn
        from src.decision.features.sprint_table import build_feature_table, build_outcomes

        earlier = pd.Timestamp(FIXTURE_T0) - pd.Timedelta(days=42)
        X_tr = build_feature_table(self.events, earlier)
        y_tr = build_outcomes(self.events, earlier)["churn"]
        fitted = fit_best_churn(X_tr, y_tr, seed=11)

        def call_by_name(fn, pool):
            params = inspect.signature(fn).parameters
            missing = [n for n, p in params.items() if n not in pool and p.default is p.empty
                       and p.kind not in (p.VAR_POSITIONAL, p.VAR_KEYWORD)]
            self.assertEqual([], missing)
            return fn(**{n: pool[n] for n in params if n in pool})

        pool = {"model": fitted, "X_train": X_tr, "y_train": y_tr, "X_test": self.X,
                "y_test": self.y["churn"], "seed": 11}
        given = call_by_name(evaluate_temporal_holdout, pool)
        self.assertEqual("given_fitted_model (재학습 없음)", given["model_source"])
        self.assertEqual(fitted.name, given["name"])
        with_name = call_by_name(evaluate_temporal_holdout, {**pool, "model_factory": "hist_gb"})
        self.assertEqual(given["roc_auc"], with_name["roc_auc"])  # model 이 우선
        refit = call_by_name(evaluate_temporal_holdout, {**pool, "model": None, "model_factory": "hist_gb"})
        self.assertEqual("refit_on_X_train", refit["model_source"])
        # 학습된 hist_gb 를 그대로 쓴 것과 같은 seed 로 다시 학습한 것은 같은 점수를 낸다
        self.assertAlmostEqual(given["roc_auc"], refit["roc_auc"], places=10)

    def test_label_mismatch_is_refused(self) -> None:
        from src.decision.churn import evaluate_churn_models

        with self.assertRaises(ValueError):
            evaluate_churn_models(self.X, self.y["churn"].iloc[:-3], seed=1)


@unittest.skipUnless(HAVE_ML, SKIP_REASON)
class TestF1Threshold(unittest.TestCase):
    def test_threshold_respects_ties_and_no_positive(self) -> None:
        import math

        import numpy as np

        from src.decision.churn import _best_f1_threshold, lift_at

        y = np.array([1, 1, 0, 0, 1, 0])
        s = np.array([0.9, 0.8, 0.8, 0.2, 0.7, 0.1])
        t = _best_f1_threshold(y, s)
        self.assertIn(t, set(s))
        self.assertTrue(math.isinf(_best_f1_threshold(np.zeros(4, dtype=int), np.arange(4.0))))
        self.assertTrue(math.isnan(lift_at(np.zeros(5, dtype=int), np.arange(5.0))))


@unittest.skipUnless(HAVE_ML, SKIP_REASON)
@unittest.skipUnless(HAVE_TORCH, TORCH_SKIP)
class TestChurnGRU(unittest.TestCase):
    def test_gru_runs_with_early_stopping_on_same_folds(self) -> None:
        from src.decision.churn_dl import CHANNELS, build_daily_sequences, evaluate_churn_gru

        events, X, y = _fixture(120)
        seqs = build_daily_sequences(events, FIXTURE_T0, X.index, lookback_days=28)
        self.assertEqual((len(X), 28, len(CHANNELS)), seqs.shape)
        out = evaluate_churn_gru(seqs, y["churn"].to_numpy(), seed=3)
        self.assertEqual("gru_daily", out["name"])
        self.assertEqual(5, out["cv"]["roc_auc"]["n_folds"])
        self.assertEqual(5, len(out["early_stopping"]))
        self.assertTrue(all(run["epochs_run"] >= 1 for run in out["early_stopping"]))

    def test_sequences_use_past_only(self) -> None:
        import numpy as np
        import pandas as pd

        from src.decision.churn_dl import build_daily_sequences

        events, X, _ = _fixture(40)
        past = events[events["timestamp"] < pd.Timestamp(FIXTURE_T0)]
        np.testing.assert_array_equal(build_daily_sequences(events, FIXTURE_T0, X.index),
                                      build_daily_sequences(past, FIXTURE_T0, X.index))


if __name__ == "__main__":
    unittest.main()
