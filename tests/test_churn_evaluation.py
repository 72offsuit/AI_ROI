"""#215 — Churn 평가 보강: 보정(calibration) · 임계값 비교표 · SHAP Local · shap_summary.png.

멘토 피드백(2026-11-13) — ROC-AUC 하나로는 채택 근거가 부족하다. 그래서
  1. 보정 지표(Brier · ECE · 구간표)가 정의대로 계산되는지,
  2. 임계값 비교표의 각 행이 자기 규칙을 지키는지(상위 비율 · 재현율 목표 · F1 최대),
  3. 규칙 기준선(점수가 확률이 아님)에는 보정 지표를 매기지 않는지,
  4. SHAP Local 이 위험 상위 고객을 후보 안에서 고르고, 요약 그림이 실제 파일로 나오는지
를 본다. 시뮬레이터를 쓰지 않는다 — 합성 데이터다.
"""

from __future__ import annotations

import importlib.util
import math
import tempfile
import unittest
from pathlib import Path

from tests.test_feature_sprint_table import HAVE_ML, SKIP_REASON

HAVE_PLOT = importlib.util.find_spec("matplotlib") is not None and importlib.util.find_spec("shap") is not None


@unittest.skipUnless(HAVE_ML, SKIP_REASON)
class TestCalibration(unittest.TestCase):
    def test_perfectly_calibrated_bins_have_zero_ece(self) -> None:
        import numpy as np

        from src.decision.churn import calibration

        # 확률 0.25 인 고객 4명 중 1명, 0.75 인 고객 4명 중 3명이 이탈 — 구간별로 정확히 맞다
        score = np.array([0.25] * 4 + [0.75] * 4)
        y = np.array([1, 0, 0, 0, 1, 1, 1, 0])
        result = calibration(y, score)
        self.assertAlmostEqual(0.0, result["ece"])
        self.assertAlmostEqual(float(np.mean((score - y) ** 2)), result["brier"])
        filled = [b for b in result["bins"] if b["n"]]
        self.assertEqual([4, 4], [b["n"] for b in filled])
        self.assertTrue(all(b["mean_pred"] is None for b in result["bins"] if not b["n"]))  # 0 으로 채우지 않는다

    def test_overconfident_scores_show_up_in_ece(self) -> None:
        import numpy as np

        from src.decision.churn import calibration

        y = np.array([0, 1] * 50)
        self.assertGreater(calibration(y, np.full(100, 0.95))["ece"], 0.4)  # 늘 95% 라 말하지만 실제 50%


@unittest.skipUnless(HAVE_ML, SKIP_REASON)
class TestThresholdTable(unittest.TestCase):
    def setUp(self) -> None:
        import numpy as np

        rng = np.random.default_rng(0)
        self.y = (rng.random(1000) < 0.3).astype(int)
        self.score = np.clip(0.3 + 0.4 * (self.y - 0.3) + rng.normal(0, 0.2, 1000), 0, 1)

    def test_each_row_keeps_its_rule(self) -> None:
        from src.decision.churn import THRESHOLD_TOP_SHARES, _best_f1_threshold, threshold_table

        rows = {r["rule"]: r for r in threshold_table(self.y, self.score)}
        self.assertEqual(_best_f1_threshold(self.y, self.score), rows["f1_max"]["threshold"])
        self.assertEqual(0.5, rows["probability_0.5"]["threshold"])
        for share in THRESHOLD_TOP_SHARES:
            row = rows[f"top_{round(share * 100)}pct"]
            self.assertAlmostEqual(share, row["flagged_share"], delta=0.01)
        self.assertGreaterEqual(rows["recall_80"]["recall"], 0.80)
        # SRS ML-006 최소 비교 항목 — 대상 수는 임계 이상 수, 비용은 근거가 없어 None(0 이 아니다, #280 리뷰 R2)
        for row in rows.values():
            self.assertEqual(int((self.score >= row["threshold"]).sum()), row["target_count"])
            self.assertIsNone(row["expected_campaign_cost"])
            self.assertLessEqual({"threshold", "precision", "recall", "f1", "target_count", "expected_campaign_cost"},
                                 set(row))
        # F1 최대 행의 F1 은 다른 어느 행보다 작지 않다
        self.assertGreaterEqual(rows["f1_max"]["f1"] + 1e-12, max(r["f1"] for r in rows.values()))

    def test_no_positive_means_no_recall_row_and_no_fake_zero(self) -> None:
        import numpy as np

        from src.decision.churn import threshold_table

        rows = threshold_table(np.zeros(20, dtype=int), np.linspace(0, 1, 20))
        self.assertNotIn("recall_80", {r["rule"] for r in rows})
        self.assertTrue(all(math.isnan(r["recall"]) for r in rows))


@unittest.skipUnless(HAVE_ML, SKIP_REASON)
class TestEvaluationCarriesTheNewTables(unittest.TestCase):
    """`evaluate_churn_models` 결과에 표가 붙고, 규칙 기준선에는 보정 지표가 없다."""

    @classmethod
    def setUpClass(cls) -> None:
        from src.decision import churn
        from tests.test_decision_persistence import _data

        X, t, y, _ = _data(31, n=700)
        control = t == "T0"
        cls.X, cls.y = X.loc[control], y.loc[control]
        cls.result = churn.evaluate_churn_models(cls.X, cls.y, seed=3)
        cls.model = churn.fit_best_churn(cls.X, cls.y, 3, eval_result=cls.result)

    def test_tables_belong_to_the_selected_model_and_say_they_used_no_test_data(self) -> None:
        r = self.result
        self.assertEqual(r["best_proposed"], r["threshold_table"]["model"])
        self.assertEqual(r["best_proposed"], r["calibration"]["model"])
        self.assertEqual("f1_max", r["threshold_table"]["selected"])
        self.assertIn("시험", r["threshold_table"]["basis"])
        for key in ("basis_model", "target_count_population", "expected_campaign_cost", "srs_ml006"):
            self.assertIn(key, r["threshold_table"])
        self.assertIn("부분 충족", r["threshold_table"]["srs_ml006"])
        self.assertEqual(len(self.y), sum(b["n"] for b in r["calibration"]["bins"]))

    def test_rule_baseline_has_no_calibration_but_models_do(self) -> None:
        by_name = {m["name"]: m for m in self.result["models"]}
        self.assertIsNone(by_name["rule_recency"]["cv"]["brier"]["mean"])
        self.assertIsNone(by_name["rule_recency"]["cv"]["ece"]["mean"])
        for name in ("logistic_regression", "random_forest", "hist_gb"):
            self.assertIsNotNone(by_name[name]["cv"]["brier"]["mean"], name)

    def test_shap_local_picks_the_riskiest_candidates(self) -> None:
        from src.decision import churn

        candidates = list(self.X.index[:100])
        out = churn.explain_top_risk(self.model, self.X, candidates=candidates, n=5, top=2)
        self.assertEqual("candidates", out["population"])
        self.assertEqual(5, out["n"])
        proba = churn.predict_churn_proba(self.model, self.X.loc[candidates]).sort_values(ascending=False)
        self.assertEqual(list(proba.index[:5]), [row["customer_id"] for row in out["rows"]])
        for row in out["rows"]:
            self.assertEqual(2, len(row["top"]))
            self.assertIn(row["top"][0]["direction"], ("raises_risk", "lowers_risk"))
        self.assertEqual(churn.shap_unit(self.model.name), out["shap_unit"])
        # 후보를 정하지 않으면(None) 전체에서, 후보가 비면 넓히지 않고 빈 결과(#280 리뷰 N1)
        everyone = churn.explain_top_risk(self.model, self.X, candidates=None, n=3)
        self.assertEqual(("all_scored", 3), (everyone["population"], everyone["n"]))
        for empty in ([], ["no-such-customer"]):
            none = churn.explain_top_risk(self.model, self.X, candidates=empty, n=3)
            self.assertEqual(("candidates", 0, 0, []), (none["population"], none["n_pool"], none["n"], none["rows"]))

    @unittest.skipUnless(importlib.util.find_spec("shap") is not None, "BLOCKED: shap 미설치 — 단위 실측 미실행")
    def test_shap_units_are_what_the_contributions_add_up_to(self) -> None:
        """#280 리뷰 N2 — 기여 합 + 기대값이 RF 는 확률, HistGB 는 로그오즈를 복원한다(SHAP_UNITS 가 맞는지 실측)."""
        import numpy as np
        import shap

        from src.decision import churn

        for name in ("random_forest", "hist_gb"):
            model = churn.make_model(name, 3).fit(self.X, self.y)
            Xt = model[:-1].transform(self.X.iloc[:15].astype(float))
            explainer = shap.TreeExplainer(model[-1])
            values = explainer.shap_values(Xt)
            values = np.asarray(values[1] if isinstance(values, list) else values)
            values = values[:, :, 1] if values.ndim == 3 else values
            base = np.atleast_1d(explainer.expected_value)
            total = values.sum(axis=1) + (base[1] if len(base) > 1 else base[0])
            proba = model.predict_proba(self.X.iloc[:15].astype(float))[:, 1]
            target = {"probability": proba, "log_odds": np.log(proba / (1 - proba))}[churn.shap_unit(name)]
            with self.subTest(name):
                self.assertTrue(np.allclose(total, target, atol=1e-8))

    @unittest.skipUnless(HAVE_PLOT, "BLOCKED: matplotlib/shap 미설치 — 그림 미생성(통과가 아니다)")
    def test_summary_plot_is_written(self) -> None:
        from src.decision import churn

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "artifacts" / "shap_summary.png"
            record = churn.write_shap_summary(self.model, self.X, path, seed=3, sample=200)
            self.assertEqual("ok", record["status"])
            self.assertEqual(b"\x89PNG", path.read_bytes()[:4])


if __name__ == "__main__":
    unittest.main()
