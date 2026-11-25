"""#303 — 모델 선택 근거 표시(SRS ML-011) · 평가 지표 확장(ML-009) · 인수 시험 AT-ML-03.

멘토링(11/17)에서 "랜덤 포레스트 점수가 더 높은데 XGBoost 가 확정"처럼 읽힌 원인은 CLI 요약이 무작위 CV 점수만
찍고 선택은 시간 순서 검증으로 했기 때문이다. 여기서는
  1. 선택 점수 최댓값 후보 = ``best_proposed`` (AT-ML-03),
  2. 결과 파일의 ``selection`` 이 선택 점수와 참고 점수(무작위 CV)를 나눠 싣는지,
  3. CLI 요약이 기준 · 후보별 선택 점수를 적고 무작위 CV 를 "참고"로만 적는지,
  4. ML-009 지표(혼동행렬 · 상위 10/20/30% 리프트 · 포착률 · 확률 분포)가 정의대로인지
를 본다. 시뮬레이터를 쓰지 않는다 — 합성 데이터다.
"""

from __future__ import annotations

import math
import unittest
from unittest import mock

from tests.test_feature_sprint_table import HAVE_ML, SKIP_REASON


def fmt(value, digits: int = 3) -> str:
    return "—" if value is None else (f"{value:.{digits}f}" if isinstance(value, float) else str(value))


@unittest.skipUnless(HAVE_ML, SKIP_REASON)
class TestClassificationReport(unittest.TestCase):
    def test_confusion_lift_capture_and_distribution(self) -> None:
        import numpy as np

        from src.decision.churn import classification_report

        # 점수 순서대로 10명 — 이탈자는 1 · 2 · 5 번째
        score = np.array([0.95, 0.85, 0.75, 0.65, 0.55, 0.45, 0.35, 0.25, 0.15, 0.05])
        y = np.array([1, 1, 0, 0, 1, 0, 0, 0, 0, 0])
        report = classification_report(y, score, threshold=0.5)
        self.assertEqual({"tp": 3, "fp": 2, "fn": 0, "tn": 5}, report["confusion_matrix"])
        top = {round(row["share"] * 100): row for row in report["top"]}
        self.assertEqual([10, 20, 30], sorted(top))
        self.assertAlmostEqual(1 / 0.3, top[10]["lift"])          # 상위 1명 이탈률 100% ÷ 전체 30%
        self.assertAlmostEqual(1 / 3, top[10]["capture"])          # 이탈자 3명 중 1명
        self.assertAlmostEqual(2 / 3, top[20]["capture"])
        self.assertAlmostEqual(2 / 3, top[30]["capture"])
        self.assertEqual(10, sum(row["n"] for row in report["probability_distribution"]))
        self.assertEqual("probability", report["threshold_unit"])

    def test_given_predictions_and_non_probability_scores(self) -> None:
        import numpy as np

        from src.decision.churn import capture_at, classification_report

        y = np.array([1, 0, 0, 1])
        report = classification_report(y, np.array([40.0, 10.0, 5.0, 60.0]), np.array([True, False, False, True]),
                                       threshold=30, threshold_unit="days", probability=False)
        self.assertEqual({"tp": 2, "fp": 0, "fn": 0, "tn": 2}, report["confusion_matrix"])
        self.assertIsNone(report["probability_distribution"])       # 확률이 아닌 점수는 분포를 싣지 않는다
        self.assertIn("확률이 아니다", report["probability_note"])
        self.assertTrue(math.isnan(capture_at(np.zeros(5), np.arange(5.0))))  # 이탈자 0명 — 0 이 아니라 계산 불가
        with self.assertRaises(ValueError):
            classification_report(y, np.zeros(4))


@unittest.skipUnless(HAVE_ML, SKIP_REASON)
class TestSelectionRecord(unittest.TestCase):
    MODELS = [
        {"name": "rule_recency", "kind": "baseline", "cv": {"roc_auc": {"mean": 0.60}},
         "temporal_validation": {"roc_auc": 0.62}},
        {"name": "random_forest", "kind": "proposed", "cv": {"roc_auc": {"mean": 0.806}},
         "temporal_validation": {"roc_auc": 0.70, "lift_at_20": 1.5, "ece": 0.10, "brier": 0.20}},
        {"name": "hist_gb", "kind": "proposed", "cv": {"roc_auc": {"mean": 0.79}},
         "temporal_validation": {"roc_auc": 0.74, "lift_at_20": 1.7, "ece": 0.05, "brier": 0.18}},
        {"name": "xgboost", "kind": "proposed", "cv": {"roc_auc": {"mean": 0.78}},
         "temporal_validation": {"roc_auc": 0.74, "lift_at_20": 1.8, "ece": 0.04, "brier": 0.17}},
    ]

    def test_selection_score_is_separate_from_random_cv(self) -> None:
        """멘토링 시연의 혼동 재현 — 무작위 CV 는 random_forest 가 가장 높지만 선택 점수는 아니다."""
        from src.decision.churn import selection_record

        record = selection_record(self.MODELS, "temporal_validation", "roc_auc", "hist_gb", 5)
        rows = {r["name"]: r for r in record["candidates"]}
        self.assertTrue(record["official"])
        self.assertIn("시간 순서 검증", record["basis_label"])
        self.assertIn("참고", record["reference_label"])
        self.assertEqual(0.806, rows["random_forest"]["random_cv_score"])
        self.assertEqual(0.70, rows["random_forest"]["selection_score"])
        self.assertEqual(3, rows["random_forest"]["rank"])
        # 동점(0.74)은 후보 순서 — hist_gb 가 xgboost 앞
        self.assertEqual((1, 2), (rows["hist_gb"]["rank"], rows["xgboost"]["rank"]))
        self.assertEqual(("hist_gb", 0.74), (record["chosen"], record["chosen_score"]))
        self.assertFalse(rows["rule_recency"]["eligible"])
        self.assertIsNone(rows["rule_recency"]["rank"])
        self.assertEqual(1.7, rows["hist_gb"]["lift_at_20"])       # 보조 지표는 선택과 같은 데이터
        self.assertIn("선택을 바꾸지 않는다", record["rule"]["secondary"])

    def test_random_cv_fallback_is_flagged_as_not_official(self) -> None:
        from src.decision.churn import selection_record

        record = selection_record(self.MODELS, "random_cv", "roc_auc", "random_forest", 5)
        rows = {r["name"]: r for r in record["candidates"]}
        self.assertFalse(record["official"])
        self.assertIn("무작위 교차검증", record["official_reason"])
        self.assertIsNone(record["reference_label"])             # 무작위 CV 가 곧 선택 점수 — 참고 열이 없다
        self.assertIn("개발 실행용", record["basis_label"])
        self.assertEqual(0.806, rows["random_forest"]["selection_score"])
        self.assertEqual(1, rows["random_forest"]["rank"])
        self.assertIsNone(rows["random_forest"]["lift_at_20"])      # CV 평균에 없는 지표는 None — 0 이 아니다

    def test_other_configured_metric_is_not_official(self) -> None:
        """#320 리뷰 — 설정이 허용하는 PR-AUC 로 고르면 시간 순서 검증이어도 정식 선택이 아니다."""
        from src.decision.churn import selection_record

        models = [{**m, "temporal_validation": {**m["temporal_validation"], "pr_auc": 0.3}} for m in self.MODELS]
        record = selection_record(models, "temporal_validation", "pr_auc", "random_forest", 5)
        self.assertFalse(record["official"])
        self.assertIn("PR-AUC", record["official_reason"])
        self.assertIn("ROC-AUC", record["official_criterion"])
        self.assertIn("정식 기준(ROC-AUC) 아님", record["basis_label"])
        self.assertIsNone(selection_record(self.MODELS, "temporal_validation", "roc_auc", "hist_gb", 5)["official_reason"])


@unittest.skipUnless(HAVE_ML, SKIP_REASON)
class TestEvaluationCarriesSelection(unittest.TestCase):
    """AT-ML-03 — 실제 ``evaluate_churn_models`` 결과에서 선택 점수 최댓값 = ``best_proposed``."""

    @classmethod
    def setUpClass(cls) -> None:
        from src.decision import churn
        from tests.test_churn_tuning import SMALL_TUNING
        from tests.test_decision_persistence import _data

        X, t, y, _ = _data(71, n=800)
        prior_X, _, prior_y, _ = _data(72, n=800)
        cls.X, cls.y = X.loc[t == "T0"], y.loc[t == "T0"]
        with mock.patch.object(churn, "TUNING", SMALL_TUNING):
            cls.with_prior = churn.evaluate_churn_models(cls.X, cls.y, seed=4, prior=(prior_X, prior_y))
            cls.without = churn.evaluate_churn_models(cls.X, cls.y, seed=4)

    def test_selection_max_is_best_proposed(self) -> None:
        for result in (self.with_prior, self.without):
            selection = result["selection"]
            eligible = [c for c in selection["candidates"] if c["eligible"]]
            best = max(eligible, key=lambda c: -1.0 if c["selection_score"] is None else c["selection_score"])
            self.assertEqual(result["best_proposed"], best["name"])
            self.assertEqual(result["best_proposed"], selection["chosen"])
            self.assertEqual(1, next(c["rank"] for c in eligible if c["chosen"]))
            self.assertEqual(result["selection_basis"], selection["basis"])

    def test_selection_score_is_the_temporal_validation_score(self) -> None:
        selection = self.with_prior["selection"]
        models = {m["name"]: m for m in self.with_prior["models"]}
        for c in selection["candidates"]:
            self.assertEqual(models[c["name"]]["temporal_validation"]["roc_auc"], c["selection_score"])
            self.assertEqual(models[c["name"]]["cv"]["roc_auc"]["mean"], c["random_cv_score"])
        self.assertTrue(selection["official"])
        self.assertFalse(self.without["selection"]["official"])

    def test_ml009_metrics_on_the_selection_data(self) -> None:
        report = self.with_prior["selection_report"]
        best = {m["name"]: m for m in self.with_prior["models"]}[self.with_prior["best_proposed"]]
        self.assertEqual("temporal_validation", report["basis"])
        self.assertEqual(best["temporal_validation"]["n_valid"], sum(report["confusion_matrix"].values()))
        self.assertEqual([0.10, 0.20, 0.30], [row["share"] for row in report["top"]])
        self.assertEqual(report["n"], sum(row["n"] for row in report["probability_distribution"]))
        rule = {m["name"]: m for m in self.with_prior["models"]}["rule_recency"]["temporal_validation"]["report"]
        self.assertEqual("days", rule["threshold_unit"])
        self.assertIsNone(rule["probability_distribution"])
        self.assertEqual("random_cv", self.without["selection_report"]["basis"])
        for name in ("lift_at_20", "lift_at_30", "capture_at_10", "capture_at_20", "capture_at_30"):
            self.assertIn(name, best["cv"])
            self.assertIn(name, best["temporal_validation"])


@unittest.skipUnless(HAVE_ML, SKIP_REASON)
class TestCliSelectionLines(unittest.TestCase):
    """CLI 요약만 읽어도 어떤 점수로 무엇을 골랐는지 보인다(#303 완료 조건)."""

    def test_churn_lines_show_basis_scores_and_reference(self) -> None:
        from src import main as cli
        from src.decision.churn import selection_record

        churn = {"selection": selection_record(TestSelectionRecord.MODELS, "temporal_validation", "roc_auc",
                                               "hist_gb", 5)}
        lines = cli.churn_selection_lines(churn, fmt)
        text = "\n".join(lines)
        self.assertIn("선택 기준 시간 순서 검증 ROC-AUC", lines[0])
        self.assertIn("hist_gb* 0.740", text)
        self.assertIn("→ 확정 hist_gb (0.740)", text)
        self.assertIn("random_forest 0.700", lines[1])                 # 선택 점수 줄에는 시간 순서 검증 점수
        reference = next(line for line in lines if "참고" in line)
        self.assertIn("random_forest 0.806", reference)                # 무작위 CV 는 참고 줄에만
        self.assertNotIn("0.806", lines[1])
        self.assertNotIn("개발 실행용", text)

    #: #303 이전 평가 함수가 남긴 모양 — selection 블록 없이 selection_basis · selection_metric · 모델별 점수.
    LEGACY_MODELS = [
        {"name": "rule_recency", "kind": "baseline", "cv": {"roc_auc": {"mean": 0.60}, "pr_auc": {"mean": 0.55}},
         "temporal_validation": {"roc_auc": 0.61, "pr_auc": 0.52}},
        {"name": "logistic_regression", "kind": "baseline",
         "cv": {"roc_auc": {"mean": 0.74}, "pr_auc": {"mean": 0.688}},
         "temporal_validation": {"roc_auc": 0.72, "pr_auc": 0.66}},
        {"name": "random_forest", "kind": "proposed", "cv": {"roc_auc": {"mean": 0.806}, "pr_auc": {"mean": 0.648}},
         "temporal_validation": {"roc_auc": 0.769, "pr_auc": 0.63}},
        {"name": "hist_gb", "kind": "proposed", "cv": {"roc_auc": {"mean": 0.79}, "pr_auc": {"mean": 0.62}},
         "temporal_validation": {"roc_auc": 0.727, "pr_auc": 0.61}},
    ]

    def legacy(self, basis: str | None, metric: str | None, chosen: str = "random_forest", models=None) -> dict:
        return {"selection_basis": basis, "selection_metric": metric, "best_proposed": chosen,
                "models": self.LEGACY_MODELS if models is None else models}

    def test_old_results_show_their_actual_selection_scores(self) -> None:
        """#320 리뷰 — 이전 판 결과도 후보별 실제 선택 점수(시간 순서 검증)를 적고, 기준선은 후보 밖에 둔다."""
        from src import main as cli

        lines = cli.churn_selection_lines(self.legacy("temporal_validation", "roc_auc"), fmt)
        text = "\n".join(lines)
        self.assertIn("선택 기준 시간 순서 검증 ROC-AUC", lines[0])
        self.assertIn("이전 판 결과", lines[1])
        self.assertIn("제안 random_forest* 0.769 · hist_gb 0.727 → 확정 random_forest (0.769)", text)
        self.assertIn("기준선(선택 대상 아님) rule_recency 0.610 · logistic_regression 0.720", text)
        reference = next(line for line in lines if "참고" in line)
        self.assertIn("무작위 교차검증 ROC-AUC 평균", reference)
        self.assertIn("random_forest 0.806", reference)
        self.assertNotIn("정식 선택이 아니다", text)

    def test_old_results_chosen_by_random_cv_name_the_metric_and_keep_baselines_out(self) -> None:
        """#320 리뷰 — CV PR-AUC 로 고른 이전 판: 어느 지표인지 적고, 기준선 PR-AUC 0.688 을 후보처럼 섞지 않는다."""
        from src import main as cli

        lines = cli.churn_selection_lines(self.legacy("random_cv", "pr_auc"), fmt)
        text = "\n".join(lines)
        self.assertIn("선택 기준 무작위 교차검증 PR-AUC 평균", lines[0])
        proposed = next(line for line in lines if "제안" in line)
        self.assertIn("random_forest* 0.648 · hist_gb 0.620", proposed)
        self.assertNotIn("logistic_regression", proposed)
        self.assertIn("기준선(선택 대상 아님) rule_recency 0.550 · logistic_regression 0.688", text)
        self.assertNotIn("참고", text)                                 # CV 점수가 곧 선택 점수
        self.assertIn("! 정식 선택이 아니다 — 앞 기준일 데이터가 없어 무작위 교차검증 평균으로 골랐다", text)
        other = "\n".join(cli.churn_selection_lines(self.legacy("temporal_validation", "pr_auc"), fmt))
        self.assertIn("! 정식 선택이 아니다 — 설정 지표 PR-AUC 로 골랐다", other)

    def test_old_results_mark_only_missing_values(self) -> None:
        """값이 없는 후보만 결손, 기준이나 지표가 없으면 어느 점수로 골랐는지 추정하지 않는다."""
        from src import main as cli

        models = [dict(m) for m in self.LEGACY_MODELS]
        models[3] = {k: v for k, v in models[3].items() if k != "temporal_validation"}
        text = "\n".join(cli.churn_selection_lines(self.legacy("temporal_validation", "roc_auc", models=models), fmt))
        self.assertIn("제안 random_forest* 0.769 · hist_gb —", text)
        for basis, metric in ((None, None), ("temporal_validation", None)):
            unknown = "\n".join(cli.churn_selection_lines(self.legacy(basis, metric), fmt))
            self.assertIn("어느 점수로 골랐는지 알 수 없다", unknown)
            self.assertNotIn("제안", unknown)

    def test_old_results_are_rebuilt_with_the_selection_record_rule(self) -> None:
        """CLI 가 다시 만든 블록 = 결정 모듈 selection_record 가 같은 입력으로 만드는 블록(겹치는 키)."""
        from src import main as cli
        from src.decision.churn import selection_record

        keys = ("name", "eligible", "selection_score", "random_cv_score", "chosen")
        for basis, metric in (("temporal_validation", "roc_auc"), ("temporal_validation", "pr_auc"),
                              ("random_cv", "pr_auc")):
            rebuilt = cli._legacy_churn_selection(self.legacy(basis, metric))
            record = selection_record(self.LEGACY_MODELS, basis, metric, "random_forest", 5)
            for key in ("basis", "metric", "official", "official_reason", "chosen", "chosen_score"):
                self.assertEqual(record[key], rebuilt[key], (basis, metric, key))
            self.assertEqual([{k: c[k] for k in keys} for c in record["candidates"]],
                             [{k: c[k] for k in keys} for c in rebuilt["candidates"]], (basis, metric))

    def test_new_results_chosen_by_random_cv_have_no_reference_line(self) -> None:
        from src import main as cli
        from src.decision.churn import selection_record

        churn = {"selection": selection_record(TestSelectionRecord.MODELS, "random_cv", "roc_auc", "random_forest", 5)}
        text = "\n".join(cli.churn_selection_lines(churn, fmt))
        self.assertIn("random_forest* 0.806", text)
        self.assertNotIn("참고", text)
        self.assertIn("! 정식 선택이 아니다 — 앞 기준일 데이터가 없어 무작위 교차검증 평균으로 골랐다", text)

    def test_uplift_lines_show_validation_qini_and_test_as_reference(self) -> None:
        from src import main as cli

        uplift = {"fitted_method": "t_learner", "fitted_method_source": "evaluate_uplift_models 의 best_method",
                  "best_method_selection": {"best_method": "t_learner", "basis": "validation Qini",
                                            "validation_qini": {"t_learner": 0.0123, "x_learner": 0.0101}},
                  "models": [{"name": "s_learner", "qini": 0.009}, {"name": "t_learner", "qini": 0.011}]}
        lines = cli.uplift_selection_lines(uplift, fmt)
        self.assertIn("선택 기준 validation Qini — t_learner* 0.0123 · x_learner 0.0101", lines[1])
        # #320 리뷰 — 규제 튜닝 전(#294 이전) 결과: 메타러너 선택만, 규제 · 격자는 말하지 않는다
        self.assertIn("Validation Qini 로 메타러너를 골랐다 — 이 결과 파일에는 규제 선택 기록이 없다", lines[2])
        self.assertNotIn("규제를 함께", "\n".join(lines))
        self.assertNotIn("tuning.grid", "\n".join(lines))
        self.assertIn("참고 Test Qini(선택에 쓰지 않음)", lines[3])

    def test_uplift_single_candidate_basis_names_the_fixed_regularization(self) -> None:
        """PR #320 재리뷰 — 규제 후보가 하나면 선택 기준 줄도 메타러너만 골랐다고 적는다. 결정 모듈이 실제로 남긴 기록으로 본다."""
        from src import main as cli
        from src.decision import uplift
        from tests.test_uplift_models import synthetic

        X, t, y, _ = synthetic(n=1200)
        with mock.patch.object(uplift, "TUNING", {**dict(uplift.TUNING), "enabled": False}):
            r = uplift.evaluate_uplift_models(X, t, y, seed=0, methods=("t_learner", "x_learner"))
        new = r["best_method_selection"]
        arm = r["primary_arm"]
        self.assertIs(False, new["tuning"]["enabled"])
        fixed = uplift.selection_basis(arm, joint=False)
        self.assertEqual(fixed, new["basis"])
        saved = {**new, "basis": uplift.selection_basis(arm, joint=True)}   # 수정 전 결정 모듈이 남긴 결과
        for selection in (new, saved):
            lines = cli.uplift_selection_lines({**r, "best_method_selection": selection}, fmt)
            self.assertIn(f"선택 기준 {fixed} — ", lines[1])
            self.assertNotIn("규제를 함께", "\n".join(lines))
            self.assertIn("현행 규제에서의 메타러너별 점수", lines[2])
            for name, value in selection["validation_qini"].items():         # Validation Qini · 후보별 점수는 그대로
                self.assertIn(f"{name}{'*' if name == selection['best_method'] else ''} {fmt(value, 4)}", lines[1])
        # 규제를 함께 고른 기록은 결정 모듈 문구 그대로
        joint = {**saved, "tuning": {**new["tuning"], "enabled": True}}
        self.assertEqual(uplift.selection_basis(arm, joint=True), cli.uplift_basis(joint))

    def test_uplift_states_are_told_apart(self) -> None:
        """#320 리뷰 — 선택 성공 · 선택 불가(기본 학습 방법) · 불러온 모델을 기존 메타데이터로 구분한다."""
        from src import main as cli
        from src.decision import uplift

        joint_basis = uplift.selection_basis("T1", joint=True)        # 결정 모듈이 실제로 남기는 문구
        selected = {"best_method_selection": {"best_method": "x_learner", "basis": joint_basis,
                                              "validation_qini": {"t_learner": 0.01, "x_learner": 0.02},
                                              "base_learner": {"max_depth": 3}, "base_learner_is_current": False,
                                              "tuning": {"grid": [{}] * 6}},
                    "tuning_report": {"selection_ok": True}}
        failed = {"fitted_method": "t_learner", "fitted_method_source": "fit_uplift 기본값 (평가 결과에 best_method 없음)",
                  "best_method_selection": {"best_method": None, "basis": "validation Qini",
                                            "validation_qini": {"t_learner": None, "x_learner": None}},
                  "tuning_report": {"selection_ok": False, "selection_reason": "유효한 Validation Qini 가 없다 — 현행값을 쓴다"}}
        loaded = {"model_source": "loaded (재학습 없음)", "loaded_from": "models/x", "trained_run": "SP-1"}
        self.assertEqual("selected", cli.uplift_selection_state(selected)[0])
        self.assertEqual("not_selected", cli.uplift_selection_state(failed)[0])
        self.assertEqual("loaded", cli.uplift_selection_state(loaded)[0])
        self.assertEqual("absent", cli.uplift_selection_state({})[0])
        self.assertIn("규제 max_depth=3에서의 메타러너별 점수 — 메타러너 × 규제 6개 조합 전체는 tuning.grid",
                      "\n".join(cli.uplift_selection_lines(selected, fmt)))
        self.assertEqual("Validation Qini 로 메타러너 × 규제를 함께 골랐다", cli.uplift_selection_state(selected)[1])
        self.assertIn(f"선택 기준 {joint_basis} — t_learner 0.0100 · x_learner* 0.0200",
                      "\n".join(cli.uplift_selection_lines(selected, fmt)))
        # PR #320 재리뷰 — 규제 후보 하나. 수정 전 결정 모듈은 이때도 '함께' 문구를 남겼다(저장된 결과)
        single = {"best_method_selection": {**selected["best_method_selection"], "base_learner_is_current": True,
                                            "tuning": {"enabled": False, "grid": [{}] * 2}},
                  "tuning_report": {"selection_ok": True}}
        self.assertEqual(("selected", "Validation Qini 로 메타러너를 골랐다 — 규제 후보가 하나라 규제는 고르지 않았다"),
                         cli.uplift_selection_state(single))
        text = "\n".join(cli.uplift_selection_lines(single, fmt))
        self.assertIn(f"선택 기준 {uplift.selection_basis('T1', joint=False)} — t_learner 0.0100 · x_learner* 0.0200", text)
        self.assertNotIn("규제를 함께", text)
        self.assertIn("현행 규제에서의 메타러너별 점수", text)
        self.assertNotIn("tuning.grid", text)
        text = "\n".join(cli.uplift_selection_lines(failed, fmt))
        self.assertIn("! Validation Qini 로 고르지 못했다 — 유효한 Validation Qini 가 없다", text)
        self.assertNotIn("선택 기준", text)                       # 빈 점수를 선택 근거처럼 적지 않는다
        self.assertIn("불러온 모델 — 이 실행에서 다시 고르지 않았다(학습 실행 SP-1)",
                      "\n".join(cli.uplift_selection_lines(loaded, fmt)))


if __name__ == "__main__":
    unittest.main()
