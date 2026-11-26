"""#219 2부 — test 분할 보고(십분위표 UP-005 · 메타러너 CATE 차이 UP-008 · H-SEG-2) · Persuadables 특성(UP-006) ·
비용을 뺀 우선순위(SEG-004 확장, S4 와 같은 정의). 규칙은 DR-219-segments 「2부 결정」.

시뮬레이터를 쓰지 않는다 — 합성 데이터다. run_sprint 는 import 하지 않는다(AST 로 떼어 실행).
"""

from __future__ import annotations

import ast
import json
import math
import unittest
from importlib.util import find_spec
from unittest import mock

DEPS = all(find_spec(m) for m in ("numpy", "pandas", "scipy", "sklearn"))
REASON = "BLOCKED: numpy/pandas/scipy/scikit-learn 미설치"


def fake_test(n=4000, seed=0, persuadable_effect=0.2, rest_effect=0.0, sd_effect=0.0, share_sd=0.05):
    """``_test`` 와 같은 모양. 실측 효과를 정해 둔 세 집단(P · 나머지 R · SD)을 깐다.

    R(고객의 60% 이상)의 CATE 는 정확히 0 이라 |uplift| 60% 분위수 = 0 → '≈0 띠' 반폭 0 이 되어, 4분면이 집단과 그대로 맞는다.
    """
    import numpy as np
    import pandas as pd

    assert 0.70 - share_sd >= 0.60
    rng = np.random.default_rng(seed)
    ids = pd.Index([f"C{i:05d}" for i in range(n)])
    group = rng.choice(["P", "R", "SD"], n, p=[0.30, 0.70 - share_sd, share_sd])
    base = {"P": 0.5, "R": 0.0, "SD": -0.5}
    u = np.array([base[g] for g in group]) + np.where(group == "R", 0.0, rng.normal(0, 0.01, n))
    cate = pd.DataFrame({"T1": u, "T2": u - 0.1, "T3": u - 0.05, "T4": np.nan}, index=ids)
    arms = pd.Series(rng.choice(["T0", "T1", "T2", "T3", "T4"], n), index=ids)
    effect = np.array([{"P": persuadable_effect, "R": rest_effect, "SD": sd_effect}[g] for g in group])
    p = 0.5 + np.where(arms.to_numpy() != "T0", effect, 0.0)
    y = pd.Series((rng.random(n) < p).astype(float), index=ids)
    other = cate.copy() * 0.5 + rng.normal(0, 0.05, (n, 4))
    return {"treatment": arms, "y": y, "cate": {"t_learner": cate, "x_learner": other, "s_learner": cate * -1},
            "primary_arm": "T3", "best_method": "t_learner"}, group


@unittest.skipUnless(DEPS, REASON)
class TestDeciles(unittest.TestCase):
    def test_rows_equal_the_hand_computed_split(self) -> None:
        import numpy as np
        import pandas as pd

        from src.decision.uplift_report import uplift_deciles

        test, _ = fake_test(n=2000)
        res = uplift_deciles(test, "t_learner")
        sel = test["treatment"].isin(["T0", "T3"])
        score = test["cate"]["t_learner"]["T3"][sel]
        frame = pd.DataFrame({"s": score, "cid": score.index, "t": test["treatment"][sel] == "T3",
                              "y": test["y"][sel]}).sort_values(["s", "cid"], ascending=[False, True], kind="mergesort")
        blocks = np.array_split(np.arange(len(frame)), 10)
        self.assertEqual([len(b) for b in blocks], [r["n"] for r in res["rows"]])
        first = frame.iloc[blocks[0]]
        want = first.loc[first["t"], "y"].mean() - first.loc[~first["t"], "y"].mean()
        self.assertAlmostEqual(want, res["rows"][0]["effect"])
        self.assertAlmostEqual(first["s"].mean(), res["rows"][0]["mean_predicted_uplift"])
        lo, hi = res["rows"][0]["uplift_ci95"]
        self.assertLess(lo, res["rows"][0]["effect"])
        self.assertGreater(hi, res["rows"][0]["effect"])
        self.assertEqual(("T3", int(sel.sum()), 0), (res["arm"], res["n"], res["n_excluded_unscored"]))
        json.dumps(res)


@unittest.skipUnless(DEPS, REASON)
class TestLearnerAgreement(unittest.TestCase):
    def test_identical_and_reversed(self) -> None:
        from src.decision.uplift_report import learner_agreement

        test, _ = fake_test(n=1000)
        pairs = {(p["a"], p["b"]): p for p in learner_agreement(test)["pairs"]}
        self.assertEqual({("s_learner", "t_learner"), ("s_learner", "x_learner"), ("t_learner", "x_learner")}, set(pairs))
        self.assertAlmostEqual(-1.0, pairs[("s_learner", "t_learner")]["spearman"])   # s = −t
        self.assertEqual(0.0, pairs[("s_learner", "t_learner")]["top_overlap"])
        self.assertGreater(pairs[("t_learner", "x_learner")]["spearman"], 0.5)


@unittest.skipUnless(DEPS, REASON)
class TestQuadrantValidation(unittest.TestCase):
    """H-SEG-2 — DR-219-segments 「2부 결정」의 규칙 그대로."""

    def test_supported_when_persuadables_respond(self) -> None:
        import numpy as np

        from src.decision.uplift_report import quadrant_validation

        test, group = fake_test(persuadable_effect=0.25)
        h = quadrant_validation(test, "t_learner")
        self.assertEqual(("H-SEG-2", "supported"), (h["id"], h["result"]))
        ev = h["evidence"]
        self.assertGreater(ev["ci95"][0], 0)
        # 실측 효과 = 고객군 안 처치(T1~T4) − 대조(T0) 유지율. Wald 구간은 네 칸 이항 분산의 합.
        y, t = test["y"].to_numpy(), test["treatment"].to_numpy() != "T0"
        p = ev["persuadables"]
        mask = np.isin(np.arange(len(y)), np.where(group == "P")[0])
        self.assertEqual(int(mask.sum()), p["n_treated"] + p["n_control"])     # 4분면 Persuadables = 집단 P
        self.assertAlmostEqual(y[mask & t].mean() - y[mask & ~t].mean(), p["effect"])
        self.assertEqual(0.0, ev["uplift_band"])
        var = sum(r * (1 - r) / n for r, n in ((p["rate_treated"], p["n_treated"]), (p["rate_control"], p["n_control"]),
                                                (ev["rest"]["rate_treated"], ev["rest"]["n_treated"]),
                                                (ev["rest"]["rate_control"], ev["rest"]["n_control"])))
        self.assertAlmostEqual(ev["diff"] - 1.959964 * math.sqrt(var), ev["ci95"][0], places=5)
        self.assertEqual(0.05, ev["alpha"])

    def test_not_supported_without_difference_or_with_responding_sleeping_dogs(self) -> None:
        from src.decision.uplift_report import quadrant_validation

        test, _ = fake_test(persuadable_effect=0.0, seed=1)
        self.assertEqual("not_supported", quadrant_validation(test, "t_learner")["result"])
        test, _ = fake_test(n=8000, persuadable_effect=0.25, sd_effect=0.3, share_sd=0.10, seed=2)  # SD 대조 ≥ 100명
        h = quadrant_validation(test, "t_learner")
        self.assertEqual("supported", h["evidence"]["persuadables_result"])
        self.assertEqual("contradicted", h["evidence"]["sleeping_dogs"]["result"])
        self.assertEqual("not_supported", h["result"])           # ② 반증이면 지지되지 않음

    def test_small_cells_are_undetermined(self) -> None:
        from src.decision.uplift_report import quadrant_validation

        test, _ = fake_test(n=300, persuadable_effect=0.25)
        h = quadrant_validation(test, "t_learner")
        self.assertEqual("undetermined", h["result"])
        self.assertIn("100명 미만", h["evidence"]["reason"])
        self.assertEqual("undetermined", h["evidence"]["sleeping_dogs"]["result"])

    def test_report_bundle_and_unknown_method(self) -> None:
        from src.decision.uplift_report import uplift_report

        test, _ = fake_test(n=1500)
        report = uplift_report(test, "t_learner")
        self.assertEqual(("ok", "t_learner", "T3"), (report["status"], report["method"], report["primary_arm"]))
        self.assertEqual("H-SEG-2", report["quadrant_validation"]["id"])
        json.dumps(report)
        with self.assertRaises(ValueError):
            uplift_report(test, "r_learner")


@unittest.skipUnless(DEPS, REASON)
class TestKeepPredictions(unittest.TestCase):
    def test_test_split_is_kept_apart(self) -> None:
        from src.decision import uplift
        from tests.test_uplift_models import synthetic

        X, t, y, _ = synthetic(n=1200)
        off = {**dict(uplift.TUNING), "enabled": False}
        with mock.patch.object(uplift, "TUNING", off):
            plain = uplift.evaluate_uplift_models(X, t, y, seed=0, methods=("t_learner", "x_learner"))
            kept = uplift.evaluate_uplift_models(X, t, y, seed=0, methods=("t_learner", "x_learner"),
                                                 keep_predictions=True)
        self.assertNotIn("_test", plain)
        test = kept.pop("_test")
        json.dumps(kept)
        self.assertEqual(kept["evaluation_split"]["test_customer_ids"], list(test["treatment"].index))
        self.assertEqual({"t_learner", "x_learner"}, set(test["cate"]))
        self.assertEqual((kept["primary_arm"], kept["best_method"]), (test["primary_arm"], test["best_method"]))
        self.assertEqual(list(test["treatment"].index), list(test["cate"]["t_learner"].index))


@unittest.skipUnless(DEPS, REASON)
class TestProfileAndNetValue(unittest.TestCase):
    def test_persuadables_profile_smd(self) -> None:
        import numpy as np
        import pandas as pd

        from src.decision.segments import persuadables_profile

        ids = pd.Index([f"C{i}" for i in range(200)])
        quad = pd.Series(["Persuadables"] * 80 + ["Sure Things"] * 100 + ["UNSCORED"] * 20, index=ids)
        rng = np.random.default_rng(4)
        feats = pd.DataFrame({"recency": np.r_[rng.normal(10, 2, 80), rng.normal(20, 2, 120)],
                              "noise": rng.normal(0, 1, 200), "label": ["x"] * 200}, index=ids)
        feats.iloc[:8, 1] = np.nan
        tiers = pd.DataFrame({"signup_tier": ["NEW"] * 40 + ["EXISTING"] * 160}, index=ids)
        res = persuadables_profile(quad, feats, tiers)
        self.assertEqual((80, 100), (res["n_persuadables"], res["n_rest"]))     # UNSCORED 는 빠진다
        self.assertEqual(["recency", "noise"], [r["feature"] for r in res["features"]])   # 숫자 열만, |SMD| 순
        a, b = feats["recency"].iloc[:80], feats["recency"].iloc[80:180]
        want = (a.mean() - b.mean()) / math.sqrt((a.var(ddof=1) + b.var(ddof=1)) / 2)
        self.assertAlmostEqual(want, res["features"][0]["smd"])
        self.assertAlmostEqual(0.1, res["features"][1]["missing_persuadables"])
        shares = {r["group"]: r for r in res["tiers"]["signup_tier"]}
        self.assertAlmostEqual(0.5, shares["NEW"]["share_persuadables"])
        self.assertAlmostEqual(0.0, shares["NEW"]["share_rest"])
        json.dumps(res)

    def test_net_value_is_the_s4_definition(self) -> None:
        import numpy as np
        import pandas as pd

        from src.decision.segments import expected_net_value
        from src.decision.strategies import plan_S4

        rng = np.random.default_rng(6)
        ids = pd.Index([f"C{i:04d}" for i in range(300)])
        cate = pd.DataFrame(rng.normal(0.01, 0.03, (300, 4)), index=ids, columns=["T1", "T2", "T3", "T4"])
        clv = pd.Series(rng.gamma(2, 60000, 300), index=ids)
        costs = {"T0": 0.0, "T1": 500.0, "T2": 1500.0, "T3": 3000.0, "T4": 800.0}
        net = expected_net_value(cate, clv, 0.25, costs)
        chosen = plan_S4({"cate": cate, "clv": clv, "margin_rate": 0.25}, 10 ** 12, costs)
        positive = net[net["expected_net_value_krw"] > 0]
        self.assertEqual(dict(chosen), dict(positive["net_arm"]))          # S4 가 고른 고객 · 처치 = 양수인 고객 · net_arm
        cid = ids[0]
        want = max(cate.loc[cid, t] * clv[cid] * 0.25 - costs[t] for t in ("T1", "T2", "T3", "T4"))
        self.assertAlmostEqual(want, net.loc[cid, "expected_net_value_krw"])
        self.assertTrue(expected_net_value(cate, clv, None, costs)["expected_net_value_krw"].isna().all())  # #217


@unittest.skipUnless(DEPS, REASON)
class TestRunSprintWiring(unittest.TestCase):
    def parts(self):
        from tests.test_feature_split_roster import _run_sprint_parts

        return _run_sprint_parts("DECISION_API", "NotRun", "decision_fn", "uplift_test_report", "segment_hypotheses")

    def test_report_statuses_and_hypotheses(self) -> None:
        parts = self.parts()
        fn = parts["uplift_test_report"]
        self.assertIn("불러온 모델", fn({}, "t_learner", loaded=True)["reason"])
        self.assertIn("keep_predictions", fn({}, "t_learner", loaded=False)["reason"])
        test, _ = fake_test(n=1500)
        self.assertEqual("not_run", fn({"uplift_test": test}, None, loaded=False)["status"])
        self.assertEqual("failed", fn({"uplift_test": test}, "r_learner", loaded=False)["status"])
        report = fn({"uplift_test": test}, "t_learner", loaded=False)
        self.assertEqual("ok", report["status"])
        record = {"new_segment": {"hypotheses": [{"id": "H-SEG-1", "result": "supported"}]}}
        got = parts["segment_hypotheses"](record, {"uplift_test_report": report})
        self.assertEqual([("H-SEG-1", "supported"), ("H-SEG-2", report["quadrant_validation"]["result"])],
                         [(h["id"], h["result"]) for h in got])
        missing = parts["segment_hypotheses"]({"new_segment": {"status": "not_run", "reason": "명부가 없다"}},
                                              {"uplift_test_report": {"status": "not_run", "reason": "불러온 모델"}})
        self.assertEqual([("H-SEG-1", "undetermined"), ("H-SEG-2", "undetermined")],
                         [(h["id"], h["result"]) for h in missing])
        self.assertEqual("불러온 모델", missing[1]["evidence"]["reason"])

    def test_test_predictions_are_popped_before_uplift_eval(self) -> None:
        from tests.test_feature_split_roster import RUN_SPRINT

        tree = ast.parse(RUN_SPRINT.read_text(encoding="utf-8"))
        lines = {ast.unparse(n): n.lineno for n in ast.walk(tree) if isinstance(n, ast.Call)}
        pop = next(line for text, line in lines.items() if text.startswith("evaluation.pop('_test'"))
        self.assertLess(pop, lines["uplift_eval.update(evaluation)"])


class TestCliLines(unittest.TestCase):
    def test_uplift_test_lines(self) -> None:
        from src import main as cli

        def fmt(value, digits=3):
            return "—" if value is None else (f"{value:.{digits}f}" if isinstance(value, float) else str(value))

        uplift = {"test_report": {"status": "ok", "deciles": {"method": "t_learner", "arm": "T3",
                                                               "rows": [{"effect": 0.05}, {"effect": None}]},
                                  "learner_agreement": {"pairs": [{"a": "s_learner", "b": "t_learner", "spearman": 0.61}]}}}
        lines = cli.uplift_test_lines(uplift, fmt)
        self.assertEqual("             십분위 실측 uplift(t_learner · T3, 1→10구간) 0.050 · — — test 분할, 보고만", lines[0])
        self.assertEqual("             메타러너 CATE 순위상관 s_learner/t_learner 0.61", lines[1])
        self.assertEqual([], cli.uplift_test_lines({}, fmt))
        self.assertIn("없음 — 불러온 모델", cli.uplift_test_lines(
            {"test_report": {"status": "not_run", "reason": "불러온 모델"}}, fmt)[0])


if __name__ == "__main__":
    unittest.main()
