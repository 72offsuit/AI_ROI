"""#303 ML-010 — 관측 등급별 ML-009 지표(t1 시간 순서 검증, DR-303 「고객군별 성능」).

  1. ``group_performance`` 의 고객군 지표가 그 고객군만 떼어 계산한 값과 같은지(임계는 전체 Validation 과 같다),
  2. 정의된 등급을 빼지 않는지(n = 0 · 표본 부족 · 정의 밖 코드),
  3. 약한 고객군 표시(기준선 · 나머지 고객보다 유의하게 낮음 — DeLong 95%)와 표본 부족 제외, DeLong 계산 자체,
  4. 실제 ``evaluate_churn_models`` 의 Validation 예측이 결과 블록에 섞이지 않고 따로 나오는지,
  5. 명부 대조(역할 · 누락) · 구매 횟수 구간 확정 전 보류(DR-221 한 번의 예외) · 결과 전 등록한 가설의 평가,
  6. run_sprint 연결(AST 로 떼어 실행 — 모듈을 import 하지 않는다)과 CLI 요약.
시뮬레이터를 쓰지 않는다 — 합성 데이터다.
"""

from __future__ import annotations

import ast
import json
import unittest
from unittest import mock

from tests.test_feature_sprint_table import HAVE_ML, SKIP_REASON


def fmt(value, digits: int = 3) -> str:
    return "—" if value is None else (f"{value:.{digits}f}" if isinstance(value, float) else str(value))


def _validation(y, chosen_score, baseline_score, ids, threshold=0.5, baseline_days=None):
    """``evaluate_churn_models(keep_predictions=True)`` 의 ``_validation`` 과 같은 모양."""
    import numpy as np
    import pandas as pd

    index = pd.Index([str(c) for c in ids])
    chosen_score = np.asarray(chosen_score, dtype=float)
    baseline_score = np.asarray(baseline_score, dtype=float)
    baseline_pred = baseline_score >= (0.5 if baseline_days is None else baseline_days)
    return {"y": pd.Series(np.asarray(y, dtype=int), index=index), "chosen": "random_forest",
            "models": {"rule_recency": {"score": pd.Series(baseline_score, index=index),
                                        "predicted": pd.Series(baseline_pred, index=index), "probability": False},
                       "random_forest": {"score": pd.Series(chosen_score, index=index),
                                         "predicted": pd.Series(chosen_score >= threshold, index=index),
                                         "probability": True}}}


@unittest.skipUnless(HAVE_ML, SKIP_REASON)
class TestGroupPerformance(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        import numpy as np
        import pandas as pd

        rng = np.random.default_rng(3)
        # A: 고른 모델이 거꾸로(기준선은 정확) · B: 고른 모델이 정확 · C: 50명(표본 부족) · D: 150명 중 이탈 5명(적은 쪽 부족)
        blocks = {"V1_LOW": 200, "V2_MID": 300, "V3_HIGH": 50, "V0_NONE": 150}
        ids, tier, y = [], [], []
        for code, n in blocks.items():
            labels = (rng.random(n) < 0.4).astype(int) if code != "V0_NONE" else np.r_[np.ones(5, int), np.zeros(n - 5, int)]
            ids += [f"{code}-{i}" for i in range(n)]
            tier += [code] * n
            y += list(labels)
        y = np.asarray(y)
        tier = np.asarray(tier)
        noise = rng.random(len(y)) * 0.2
        chosen = np.where(tier == "V1_LOW", 0.9 - 0.8 * y + noise, 0.1 + 0.8 * y + noise)
        chosen = np.where(tier == "V3_HIGH", 0.9 - 0.8 * y + noise, chosen)
        baseline = 0.1 + 0.8 * y + rng.random(len(y)) * 0.05
        cls.y, cls.tier, cls.chosen, cls.ids = y, tier, chosen, ids
        cls.validation = _validation(y, chosen, baseline, ids)
        # 등급 없는 고객 2명(명부에 없음) + 정의 밖 코드 하나
        groups = pd.DataFrame({"value_tier": tier}, index=pd.Index(ids))
        groups = groups.drop(index=ids[:2])
        groups.loc[ids[2], "value_tier"] = "V9_ODD"
        cls.groups = groups
        from src.decision import churn
        from src.decision.observed_tiers import TIER_LABELS

        cls.res = churn.group_performance(cls.validation, groups, {"value_tier": TIER_LABELS["value_tier"]},
                                          population="합성", groups_source="합성 등급")
        cls.rows = {row["group"]: row for row in cls.res["axes"]["value_tier"]}

    def test_group_metrics_equal_the_subset_computed_alone(self) -> None:
        import numpy as np
        from sklearn.metrics import average_precision_score, roc_auc_score

        from src.decision.churn import calibration, capture_at, lift_at

        mask = self.tier == "V2_MID"
        row = self.rows["V2_MID"]["models"]["random_forest"]
        y, s = self.y[mask], self.chosen[mask]
        self.assertEqual(int(mask.sum()), row["n"])
        self.assertAlmostEqual(roc_auc_score(y, s), row["roc_auc"])
        self.assertAlmostEqual(average_precision_score(y, s), row["pr_auc"])
        pred = s >= 0.5                                         # 전체 Validation 과 같은 임계 — 고객군마다 다시 정하지 않는다
        self.assertEqual({"tp": int((pred & (y == 1)).sum()), "fp": int((pred & (y == 0)).sum()),
                          "fn": int((~pred & (y == 1)).sum()), "tn": int((~pred & (y == 0)).sum())},
                         row["confusion_matrix"])
        self.assertEqual([0.10, 0.20, 0.30], [t["share"] for t in row["top"]])
        self.assertAlmostEqual(lift_at(y, s, 0.20), row["top"][1]["lift"])
        self.assertAlmostEqual(capture_at(y, s, 0.30), row["top"][2]["capture"])
        self.assertAlmostEqual(calibration(y, s)["ece"], row["ece"])
        self.assertEqual(int(mask.sum()), sum(b["n"] for b in row["probability_distribution"]))
        rule = self.rows["V2_MID"]["models"]["rule_recency"]                 # 규칙 점수는 확률이 아니다
        self.assertIsNone(rule["brier"])
        self.assertIsNone(rule["probability_distribution"])
        self.assertTrue(np.isfinite(rule["roc_auc"]))

    def test_every_defined_group_is_kept(self) -> None:
        from src.decision.observed_tiers import TIER_LABELS

        codes = [row["group"] for row in self.res["axes"]["value_tier"]]
        self.assertEqual(list(TIER_LABELS["value_tier"]) + ["V9_ODD"], codes)   # 정의 순서 + 정의 밖 코드는 뒤에
        empty = self.rows["UNKNOWN"]
        self.assertEqual((0, True, "고객 0명 < 100명", None), (empty["n"], empty["small_group"],
                                                            empty["small_group_reason"], empty["weak"]))
        self.assertIsNone(empty["models"]["random_forest"]["roc_auc"])
        self.assertIsNone(empty["models"]["random_forest"]["precision"])
        self.assertEqual((len(self.ids), len(self.ids) - 2, 2),
                         (self.res["n"], self.res["n_grouped"], self.res["n_without_group"]))
        json.dumps(self.res)

    def test_weak_groups_are_marked_and_small_groups_are_not_judged(self) -> None:
        low = self.rows["V1_LOW"]
        self.assertIs(True, low["weak"])
        self.assertEqual(["below_baseline", "below_rest"], low["weak_reasons"])
        self.assertLess(low["tests"]["vs_baseline"]["ci95"][1], 0)
        self.assertLess(low["tests"]["vs_rest"]["ci95"][1], 0)
        self.assertEqual(197, low["n"])                         # 200명 중 등급 없음 2명 · 정의 밖 코드 1명
        self.assertEqual(len(self.ids) - 197, low["tests"]["vs_rest"]["n_rest"])
        self.assertEqual((False, []), (self.rows["V2_MID"]["weak"], self.rows["V2_MID"]["weak_reasons"]))
        small = self.rows["V3_HIGH"]                                # 고른 모델이 거꾸로여도 표본 부족이면 판정하지 않는다
        self.assertEqual((True, None, "고객 50명 < 100명"), (small["small_group"], small["weak"], small["small_group_reason"]))
        self.assertIsNone(small["tests"])
        self.assertIsNotNone(small["models"]["random_forest"]["roc_auc"])   # 값은 싣는다
        minority = self.rows["V0_NONE"]
        self.assertEqual((True, "적은 쪽 클래스 5명 < 10명"), (minority["small_group"], minority["small_group_reason"]))
        self.assertEqual(("random_forest", "rule_recency", 0.05),
                         (self.res["chosen"], self.res["baseline"], self.res["rule"]["alpha"]))
        ci = self.rows["V2_MID"]["models"]["random_forest"]["roc_auc_ci95"]
        self.assertTrue(ci[0] <= self.rows["V2_MID"]["models"]["random_forest"]["roc_auc"] <= ci[1])

    def test_below_rest_alone_marks_a_group(self) -> None:
        import numpy as np

        from src.decision import churn

        # 나머지 고객보다 유의하게 낮은 고객군 — 기준선이 없으면 이 검정만 남는다
        rng = np.random.default_rng(5)
        n = 400
        y = (rng.random(n) < 0.5).astype(int)
        good = 0.2 + 0.6 * y + rng.random(n) * 0.1
        weak = 0.3 + 0.2 * y + rng.random(n) * 0.5
        tier = np.r_[["A"] * 300, ["B"] * 100]
        score = np.where(tier == "A", good, weak)
        validation = _validation(y, score, score, range(n))
        del validation["models"]["rule_recency"]
        import pandas as pd

        res = churn.group_performance(validation, pd.DataFrame({"g": tier}, index=[str(i) for i in range(n)]),
                                      {"g": {"A": "a", "B": "b"}}, population="합성", groups_source="합성")
        rows = {row["group"]: row for row in res["axes"]["g"]}
        self.assertIsNone(res["baseline"])
        self.assertEqual(["below_rest"], rows["B"]["weak_reasons"])
        self.assertIsNone(rows["B"]["tests"]["vs_baseline"])
        self.assertIs(False, rows["A"]["weak"])


@unittest.skipUnless(HAVE_ML, SKIP_REASON)
class TestDeLongAndAlpha(unittest.TestCase):
    def test_delong_matches_the_definition(self) -> None:
        """DeLong(1988) 분산 · 공분산을 정의(양성 × 음성 비교 행렬)대로 직접 계산한 값과 대조한다."""
        import numpy as np
        from sklearn.metrics import roc_auc_score

        from src.decision.churn import delong

        rng = np.random.default_rng(11)
        y = (rng.random(60) < 0.4).astype(int)
        a = np.round(y * 0.5 + rng.random(60), 1)               # 반올림 — 동점(0.5)을 일부러 만든다
        b = np.round(y * 0.2 + rng.random(60), 1)
        aucs, cov = delong(y, [a, b])
        x_pos, x_neg = y == 1, y == 0
        m, n = int(x_pos.sum()), int(x_neg.sum())

        def psi(s):
            d = s[x_pos][:, None] - s[x_neg][None, :]
            return (d > 0) + 0.5 * (d == 0)

        V10 = [psi(s).mean(axis=1) for s in (a, b)]
        V01 = [psi(s).mean(axis=0) for s in (a, b)]
        want = np.cov(np.vstack(V10)) / m + np.cov(np.vstack(V01)) / n
        np.testing.assert_allclose(want, cov)
        self.assertAlmostEqual(roc_auc_score(y, a), aucs[0])
        self.assertAlmostEqual(roc_auc_score(y, b), aucs[1])
        self.assertIsNone(delong(np.array([1, 0, 0, 0]), [np.arange(4.0)]))     # 양성 1명 — 분산을 못 낸다

    def test_alpha_is_the_project_ab_alpha(self) -> None:
        from src.decision import ab_test, churn

        self.assertEqual(ab_test.ALPHA, churn.GROUP_TEST_ALPHA)


@unittest.skipUnless(HAVE_ML, SKIP_REASON)
class TestTierHypotheses(unittest.TestCase):
    """결과 전에 등록한 가설(DR-303)을 실행 결과로 평가하는 규칙."""

    @staticmethod
    def row(group, small=False, below_base=None, below_rest=None, n=300):
        tests = None if small else {
            "vs_baseline": None if below_base is None else {"diff": -0.1 if below_base else 0.01,
                                                            "ci95": [-0.2, -0.01] if below_base else [-0.05, 0.07],
                                                            "below": below_base},
            "vs_rest": None if below_rest is None else {"diff": -0.08 if below_rest else 0.0,
                                                        "ci95": [-0.12, -0.03] if below_rest else [-0.04, 0.04],
                                                        "below": below_rest, "n_rest": 900}}
        return {"group": group, "n": n, "small_group": small, "small_group_reason": "고객 50명 < 100명" if small else None,
                "tests": tests}

    def test_results(self) -> None:
        from src.decision.churn import TIER_HYPOTHESES, evaluate_tier_hypotheses

        axes = {"value_tier": [self.row("V1_LOW", below_base=False, below_rest=False),
                               self.row("V2_MID", below_base=True, below_rest=False)],
                "signup_tier": [self.row("NEW", below_base=False, below_rest=True), self.row("EXISTING", below_base=False, below_rest=False)],
                "frequency_tier": [self.row("F1_ONCE", small=True, n=50)]}
        got = {h["id"]: h for h in evaluate_tier_hypotheses(axes)}
        self.assertEqual([h["id"] for h in TIER_HYPOTHESES], list(got))
        self.assertEqual(("not_supported", ["value_tier=V2_MID"]),
                         (got["H-ML010-1"]["result"], got["H-ML010-1"]["evidence"]["below_baseline"]))
        self.assertEqual(4, got["H-ML010-1"]["evidence"]["n_groups_judged"])
        self.assertEqual(("supported", [-0.12, -0.03]), (got["H-ML010-2"]["result"], got["H-ML010-2"]["evidence"]["ci95"]))
        self.assertEqual(("undetermined", 50), (got["H-ML010-3"]["result"], got["H-ML010-3"]["evidence"]["n"]))
        for h in got.values():                                   # 가설마다 이유와 평가 규칙을 함께 싣는다
            self.assertTrue(h["why"] and h["evaluation"] and h["statement"])

    def test_no_judged_group_is_undetermined_not_supported(self) -> None:
        from src.decision.churn import evaluate_tier_hypotheses

        got = {h["id"]: h["result"] for h in evaluate_tier_hypotheses({"value_tier": [self.row("V1_LOW", small=True)]})}
        self.assertEqual({"H-ML010-1": "undetermined", "H-ML010-2": "undetermined", "H-ML010-3": "undetermined"}, got)
        flat = {"value_tier": [self.row("V1_LOW", below_base=False, below_rest=False)],
                "signup_tier": [self.row("NEW", below_base=False, below_rest=False)]}
        got = {h["id"]: h["result"] for h in evaluate_tier_hypotheses(flat)}
        self.assertEqual(("supported", "not_supported"), (got["H-ML010-1"], got["H-ML010-2"]))


@unittest.skipUnless(HAVE_ML, SKIP_REASON)
class TestValidationPredictions(unittest.TestCase):
    """실제 ``evaluate_churn_models`` — Validation 예측은 ``keep_predictions`` 일 때만, 결과 블록 밖에 따로 나온다."""

    @classmethod
    def setUpClass(cls) -> None:
        from src.decision import churn
        from tests.test_churn_tuning import SMALL_TUNING
        from tests.test_decision_persistence import _data

        X, t, y, _ = _data(71, n=800)
        prior_X, _, prior_y, _ = _data(72, n=800)
        cls.X, cls.y = X.loc[t == "T0"], y.loc[t == "T0"]
        with mock.patch.object(churn, "TUNING", SMALL_TUNING):
            cls.kept = churn.evaluate_churn_models(cls.X, cls.y, seed=4, prior=(prior_X, prior_y), keep_predictions=True)
            cls.plain = churn.evaluate_churn_models(cls.X, cls.y, seed=4, prior=(prior_X, prior_y))
            cls.no_prior = churn.evaluate_churn_models(cls.X, cls.y, seed=4, keep_predictions=True)

    def test_predictions_are_kept_apart_from_the_result(self) -> None:
        self.assertNotIn("_validation", self.plain)
        self.assertNotIn("_validation", self.no_prior)          # 시간 순서 검증이 없으면 낼 Validation 예측도 없다
        for result in (self.kept, self.plain):
            for m in result["models"]:
                self.assertNotIn("_predictions", m["temporal_validation"])
        validation = self.kept["_validation"]
        json.dumps({k: v for k, v in self.kept.items() if k != "_validation"})
        self.assertEqual(self.kept["best_proposed"], validation["chosen"])
        self.assertEqual([str(c) for c in self.X.index], list(validation["y"].index))
        self.assertEqual({m["name"] for m in self.kept["models"]}, set(validation["models"]))
        self.assertIs(False, validation["models"]["rule_recency"]["probability"])

    def test_overall_group_metrics_reproduce_the_temporal_validation(self) -> None:
        import pandas as pd

        from src.decision import churn

        validation = self.kept["_validation"]
        res = churn.group_performance(validation, pd.DataFrame(index=pd.Index([], dtype=object)), {},
                                      population="합성", groups_source="없음")
        models = {m["name"]: m["temporal_validation"] for m in self.kept["models"]}
        for name, tv in models.items():
            self.assertAlmostEqual(tv["roc_auc"], res["overall"][name]["roc_auc"])
            self.assertEqual(tv["report"]["confusion_matrix"], res["overall"][name]["confusion_matrix"])
            self.assertEqual([t["capture"] for t in tv["report"]["top"]],
                             [t["capture"] for t in res["overall"][name]["top"]])
        self.assertEqual(len(validation["y"]), res["n_without_group"])


@unittest.skipUnless(HAVE_ML, SKIP_REASON)
class TestTierPerformance(unittest.TestCase):
    def setUp(self) -> None:
        import numpy as np
        import pandas as pd

        rng = np.random.default_rng(9)
        n = 300
        self.ids = [f"c{i:03d}" for i in range(n)]
        y = (rng.random(n) < 0.3).astype(int)
        self.validation = _validation(y, 0.2 + 0.5 * y + rng.random(n) * 0.4, rng.random(n), self.ids)
        self.roster = pd.DataFrame({
            "customer_id": self.ids + ["extra"], "origin": "t1", "role": ["validation"] * (n - 3) + ["excluded"] * 3 + ["validation"],
            "value_tier": rng.choice(["V1_LOW", "V2_MID"], n + 1), "frequency_tier": "F2_RARE", "signup_tier": "EXISTING",
            "category_tier": "UNKNOWN"})
        self.roster = self.roster.drop(index=[0])                 # c000 은 명부에 없다

    def test_roster_roles_are_checked_and_all_axes_reported(self) -> None:
        from src.decision import churn
        from src.decision.observed_tiers import TIER_COLUMNS, TIER_VERSION

        res = churn.tier_performance(self.validation, self.roster)
        self.assertEqual("ok", res["status"])
        self.assertEqual(list(TIER_COLUMNS), list(res["axes"]))
        self.assertEqual({"n_not_in_roster": 1, "n_role_not_validation": 3}, res["roster_check"])
        self.assertEqual((300, 4), (res["n"], res["n_without_group"]))    # 역할이 다른 3명 + 명부에 없는 1명
        self.assertEqual(TIER_VERSION, res["tier_version"])
        self.assertEqual("가치 등급", res["axis_names"]["value_tier"])
        self.assertEqual(["H-ML010-1", "H-ML010-2", "H-ML010-3"], [h["id"] for h in res["hypotheses"]])
        freq = {row["group"]: row["n"] for row in res["axes"]["frequency_tier"]}
        self.assertEqual(296, freq["F2_RARE"])
        json.dumps(res)

    def test_withheld_until_frequency_bands_are_final(self) -> None:
        from src.decision import churn, observed_tiers

        outside = {"outside": ["F4_FREQUENT"], "range": [0.02, 0.6], "shares": {"F4_FREQUENT": 0.01}}
        res = churn.tier_performance(self.validation, self.roster, outside)
        self.assertEqual("withheld", res["status"])
        self.assertIn("F4_FREQUENT", res["reason"])
        self.assertNotIn("axes", res)                            # 구간을 고칠 수 있는 동안 등급별 성능을 내지 않는다
        self.assertEqual("ok", churn.tier_performance(self.validation, self.roster, {**outside, "outside": []})["status"])
        with mock.patch.object(observed_tiers, "FREQUENCY_BANDS_FINAL", True):
            self.assertEqual("ok", churn.tier_performance(self.validation, self.roster, outside)["status"])

    def test_tiers_from_a_real_roster(self) -> None:
        """#218 명부(build_split_roster)가 만든 t1 행을 그대로 읽는다."""
        import numpy as np

        from src.decision import churn
        from tests.test_feature_split_roster import SIGNUPS, _cohorts, _events

        from src.decision.split_roster import build_split_roster

        roster, record, _ = build_split_roster(_events(), SIGNUPS, cohorts=_cohorts(), order_items=None,
                                               observation_complete=True)
        t1 = roster[roster["origin"] == "t1"]
        ids = list(t1.loc[t1["role"] == "validation", "customer_id"])
        y = np.arange(len(ids)) % 2
        res = churn.tier_performance(_validation(y, y * 0.8 + 0.1, y, ids), t1, record["origins"]["t1"]["frequency_band_check"])
        if res["status"] == "withheld":                         # 아주 작은 합성 명부는 점검 범위를 벗어날 수 있다
            self.assertTrue(record["origins"]["t1"]["frequency_band_check"]["outside"])
            return
        self.assertEqual((len(ids), 0), (res["n"], res["n_without_group"]))
        for axis, rows in res["axes"].items():
            got = {row["group"]: row["n"] for row in rows if row["n"]}
            want = t1.loc[t1["role"] == "validation", axis].value_counts().to_dict()
            self.assertEqual(want, got)


@unittest.skipUnless(HAVE_ML, SKIP_REASON)
class TestRunSprintWiring(unittest.TestCase):
    """run_sprint 는 import 하지 않는다 — 함수만 AST 로 떼어 실행하고, 호출 순서는 AST 로 본다."""

    def parts(self):
        from tests.test_feature_split_roster import _run_sprint_parts

        return _run_sprint_parts("DECISION_API", "NotRun", "decision_fn", "churn_tier_performance")

    def test_statuses(self) -> None:
        import numpy as np
        import pandas as pd

        fn = self.parts()["churn_tier_performance"]
        self.assertEqual({"status": "not_run", "reason": "불러온 모델 — 이 실행에서 시간 순서 검증을 하지 않았다"},
                         fn({"churn_validation_reason": "불러온 모델 — 이 실행에서 시간 순서 검증을 하지 않았다"}, {}))
        ids = [f"c{i}" for i in range(120)]
        y = np.arange(120) % 2
        validation = _validation(y, y * 0.7 + 0.1, y, ids)
        self.assertEqual("not_run", fn({"churn_validation": validation}, {})["status"])          # 명부 없음
        roster = pd.DataFrame({"customer_id": ids, "origin": "t2", "role": "test", "value_tier": "V1_LOW",
                               "frequency_tier": "F1_ONCE", "signup_tier": "NEW", "category_tier": "NONE"})
        self.assertIn("t1 행이 없다", fn({"churn_validation": validation, "split_roster": roster}, {})["reason"])
        roster["origin"], roster["role"] = "t1", "validation"
        record = {"origins": {"t1": {"frequency_band_check": {"outside": ["F4_FREQUENT"], "range": [0.02, 0.6]}}}}
        self.assertEqual("withheld", fn({"churn_validation": validation, "split_roster": roster}, record)["status"])
        ok = fn({"churn_validation": validation, "split_roster": roster}, {"origins": {"t1": {}}})
        self.assertEqual(("ok", 120), (ok["status"], ok["n_grouped"]))

    def test_predictions_are_popped_before_churn_eval_and_tiers_follow_the_roster(self) -> None:
        from tests.test_feature_split_roster import RUN_SPRINT

        tree = ast.parse(RUN_SPRINT.read_text(encoding="utf-8"))
        runner = next(fn for fn in tree.body if isinstance(fn, ast.FunctionDef)
                      and any(isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
                              and n.func.id == "churn_tier_performance" for n in ast.walk(fn)))
        src = {ast.unparse(n): n.lineno for n in ast.walk(runner) if isinstance(n, ast.Call)}
        pop = next(line for text, line in src.items() if text.startswith("evaluation.pop('_validation'"))
        update = src["churn_eval.update(evaluation)"]
        self.assertLess(pop, update)                            # 고객별 점수가 churn_eval(결과 파일)에 들어가지 않는다
        roster_calls = [line for text, line in src.items() if text.startswith("prepare_split_roster(")]
        tiers = next(line for text, line in src.items() if text.startswith("churn_tier_performance("))
        self.assertLess(max(roster_calls), tiers)


class TestCliTierLines(unittest.TestCase):
    def test_lines(self) -> None:
        from src import main as cli

        row = lambda group, auc, n, small=False, weak=None: {   # noqa: E731
            "group": group, "n": n, "small_group": small, "weak": weak,
            "models": {"random_forest": {"roc_auc": auc}, "rule_recency": {"roc_auc": 0.6}}}
        churn = {"by_tier": {
            "status": "ok", "chosen": "random_forest", "baseline": "rule_recency",
            "overall": {"random_forest": {"roc_auc": 0.78}, "rule_recency": {"roc_auc": 0.7}},
            "axes": {"value_tier": [row("V1_LOW", 0.8, 900, weak=False), row("V2_MID", 0.69, 500, weak=True),
                                    row("UNKNOWN", None, 0, small=True)]},
            "axis_names": {"value_tier": "가치 등급"}, "rule": {"alpha": 0.05},
            "hypotheses": [{"id": "H-ML010-1", "result": "not_supported"}, {"id": "H-ML010-2", "result": "undetermined"}],
            "n_without_group": 3, "roster_check": {"n_not_in_roster": 1, "n_role_not_validation": 2}}}
        lines = cli.churn_tier_lines(churn, fmt)
        self.assertIn("등급별 ROC-AUC (ML-010 · t1 Validation · random_forest) — 전체 0.780 · 기준선 rule_recency 0.700",
                      lines[0])
        self.assertIn("가치 등급  V1_LOW 0.800(n 900) · !V2_MID 0.690(n 500) · UNKNOWN —(n 0 표본 부족)", lines[1])
        self.assertIn("나머지 고객보다 ROC-AUC 가 유의하게 낮음(DeLong 95%, 표본 부족 제외)", lines[2])
        self.assertEqual("               가설(결과 전 등록, DR-303) H-ML010-1 지지되지 않음 · H-ML010-2 판정 불가", lines[3])
        self.assertIn("등급 없는 Validation 고객 3명(명부에 없음 1 · 역할이 validation 아님 2)", lines[4])
        self.assertEqual([], cli.churn_tier_lines({}, fmt))
        withheld = cli.churn_tier_lines({"by_tier": {"status": "withheld", "reason": "구간 점검"}}, fmt)
        self.assertEqual(["             등급별 지표(ML-010) 보류 — 구간 점검"], withheld)
        self.assertIn("없음 — 불러온 모델", cli.churn_tier_lines(
            {"by_tier": {"status": "not_run", "reason": "불러온 모델"}}, fmt)[0])


if __name__ == "__main__":
    unittest.main()
