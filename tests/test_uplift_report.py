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


def cell_test(spec):
    """칸 수를 정해 둔 test 분할 — ``spec[군] = (처치 수, 처치 유지 수, 대조 수, 대조 유지 수)``, 군은 P · R · SD.

    CATE 는 P 0.5 · R 0 · SD −0.5 로 같고, R 이 고객의 60% 이상이어야 '≈0 띠' 반폭이 0 이 되어 4분면이 군과 그대로 맞는다.
    처치군은 T1 하나다. 결과가 정해져 있어 효과 · 구간을 손으로 셀 수 있다.
    """
    import pandas as pd

    base = {"P": 0.5, "R": 0.0, "SD": -0.5}
    arms, ys, us = [], [], []
    for g, (n_t, r_t, n_c, r_c) in spec.items():
        for n, r, arm in ((n_t, r_t, "T1"), (n_c, r_c, "T0")):
            arms += [arm] * n
            ys += [1.0] * r + [0.0] * (n - r)
            us += [base[g]] * n
    assert sum(spec["R"][i] for i in (0, 2)) >= 0.6 * len(arms)
    ids = pd.Index([f"C{i:05d}" for i in range(len(arms))])
    u = pd.Series(us, index=ids)
    return {"treatment": pd.Series(arms, index=ids), "y": pd.Series(ys, index=ids),
            "cate": {"t_learner": pd.DataFrame({"T1": u, "T2": u, "T3": u, "T4": u})}, "primary_arm": "T1"}


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
        lo, hi = res["rows"][0]["uplift_ci"]
        self.assertLess(lo, res["rows"][0]["effect"])
        self.assertGreater(hi, res["rows"][0]["effect"])
        self.assertEqual(("T3", int(sel.sum()), 0), (res["arm"], res["n"], res["n_excluded_unscored"]))
        self.assertEqual((0.95, "Newcombe(1998) hybrid score interval"), (res["ci_level"], res["ci_method"]))
        json.dumps(res)

    def test_extreme_decile_keeps_a_non_degenerate_interval(self) -> None:
        """리뷰 반례 — 처치 2/2 유지 · 대조 0/2 유지 구간. Wald 는 [+1, +1] 이었다. 수 · 점추정은 그대로 싣는다."""
        import pandas as pd

        from src.decision.segments import _two_proportions
        from src.decision.uplift_report import uplift_deciles

        ids = pd.Index([f"C{i:02d}" for i in range(40)])
        arms = pd.Series(["T3", "T3", "T0", "T0"] + ["T3", "T0"] * 18, index=ids)
        y = pd.Series([1.0, 1.0, 0.0, 0.0] + [1.0, 0.0, 0.0, 1.0] * 9, index=ids)
        score = pd.Series([1.0 - i / 100 for i in range(40)], index=ids)
        cate = pd.DataFrame({"T1": score, "T2": score, "T3": score, "T4": score})
        row = uplift_deciles({"treatment": arms, "y": y, "cate": {"t_learner": cate}, "primary_arm": "T3"},
                             "t_learner")["rows"][0]
        self.assertEqual((2, 2, 2, 0, 1.0), (row["n_treated"], row["n_control"], row["retained_treated"],
                                             row["retained_control"], row["effect"]))
        lo, hi = row["uplift_ci"]
        self.assertLess(lo, 0.6)                     # 폭 0 이 아니다
        self.assertLessEqual(hi, 1.0)
        want = _two_proportions(2, 2, 0, 2, 0.05)
        self.assertAlmostEqual(want["ci"][0], lo)


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

    def test_partially_supported_when_sleeping_dogs_cannot_be_judged(self) -> None:
        import numpy as np

        from src.decision.uplift_report import quadrant_validation

        test, group = fake_test(persuadable_effect=0.25)
        h = quadrant_validation(test, "t_learner")
        # 리뷰 반례 — ② 칸이 표본 기준 미달(SD 대조 < 100명)이면 전체를 '지지'로 올리지 않는다
        self.assertEqual(("H-SEG-2", "partially_supported", None), (h["id"], h["result"], h["not_supported_kind"]))
        self.assertEqual({"persuadables_vs_rest": "supported", "sleeping_dogs_le_zero": "undetermined"}, h["parts"])
        self.assertIsNone(h["evidence"]["sleeping_dogs"]["ci"])
        self.assertIn("< 100명", h["evidence"]["sleeping_dogs"]["reason"])
        self.assertIn("① ", h["evaluation"])
        ev = h["evidence"]
        self.assertGreater(ev["ci"][0], 0)
        self.assertEqual(0.95, ev["ci_level"])
        # 추정 대상 = 처치군을 합친 유지율 − 대조 — 처치별 수 · 가중치를 싣는다(T4 까지 관측된 처치)
        arms = ev["persuadables"]["treated_by_arm"]
        self.assertEqual(ev["persuadables"]["n_treated"], sum(arms.values()))
        self.assertAlmostEqual(1.0, sum(ev["persuadables"]["treated_weights"].values()))
        self.assertIn("가중", ev["estimand"])
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
        self.assertAlmostEqual(ev["diff"] - 1.959964 * math.sqrt(var), ev["ci"][0], places=5)
        self.assertEqual(0.05, ev["alpha"])

    def test_supported_only_when_both_claims_hold(self) -> None:
        from src.decision.uplift_report import quadrant_validation

        test, _ = fake_test(n=8000, persuadable_effect=0.25, sd_effect=-0.3, share_sd=0.10, seed=3)
        h = quadrant_validation(test, "t_learner")
        self.assertEqual(("supported", None), (h["result"], h["not_supported_kind"]))
        self.assertLessEqual(h["evidence"]["sleeping_dogs"]["ci"][1], 0)

    def test_not_supported_separates_insufficient_evidence_from_contradiction(self) -> None:
        from src.decision.uplift_report import quadrant_validation

        test, _ = fake_test(persuadable_effect=0.0, seed=1)
        h = quadrant_validation(test, "t_learner")
        self.assertEqual(("not_supported", "insufficient_evidence"), (h["result"], h["not_supported_kind"]))
        test, _ = fake_test(n=8000, persuadable_effect=0.25, sd_effect=0.3, share_sd=0.10, seed=2)  # SD 대조 ≥ 100명
        h = quadrant_validation(test, "t_learner")
        self.assertEqual("supported", h["evidence"]["persuadables_result"])
        self.assertEqual("contradicted", h["evidence"]["sleeping_dogs"]["result"])
        self.assertEqual(("not_supported", "contradicted"), (h["result"], h["not_supported_kind"]))

    def test_sleeping_dogs_interval_across_zero_is_only_partial_support(self) -> None:
        from src.decision.uplift_report import quadrant_validation

        # 리뷰 반례 — SD 실측 차이가 양수이고 구간이 0 을 걸치면 "0 이하"까지 지지했다고 읽히면 안 된다
        test, _ = fake_test(n=8000, persuadable_effect=0.25, sd_effect=0.03, share_sd=0.10, seed=5)
        h = quadrant_validation(test, "t_learner")
        sd = h["evidence"]["sleeping_dogs"]
        self.assertLess(sd["ci"][0], 0)
        self.assertGreater(sd["ci"][1], 0)
        self.assertEqual(("inconclusive", "partially_supported"), (sd["result"], h["result"]))

    def test_small_cells_are_undetermined(self) -> None:
        from src.decision.uplift_report import quadrant_validation

        test, _ = fake_test(n=300, persuadable_effect=0.25)
        h = quadrant_validation(test, "t_learner")
        self.assertEqual("undetermined", h["result"])
        self.assertIn("< 100명", h["evidence"]["reason"])
        self.assertEqual("undetermined", h["evidence"]["sleeping_dogs"]["result"])

    def test_extreme_cells_withhold_the_interval(self) -> None:
        """리뷰 반례 — 네 칸 120 · 120 · 240 · 240명, 유지율 0 · 1. Wald 는 [+1, +1] 이었다 — 구간 · 판정을 보류한다."""
        import pandas as pd

        from src.decision.uplift_report import quadrant_validation

        n = {"pt": 120, "pc": 120, "rt": 240, "rc": 240}
        arms, ys, us = [], [], []
        for key, size in n.items():
            arms += ["T1" if key.endswith("t") else "T0"] * size
            ys += [1.0 if key == "pt" else 0.0] * size
            us += [0.5 if key.startswith("p") else 0.0] * size
        ids = pd.Index([f"C{i:04d}" for i in range(len(arms))])
        u = pd.Series(us, index=ids)
        test = {"treatment": pd.Series(arms, index=ids), "y": pd.Series(ys, index=ids),
                "cate": {"t_learner": pd.DataFrame({"T1": u, "T2": u, "T3": u, "T4": u})}, "primary_arm": "T1"}
        h = quadrant_validation(test, "t_learner")
        ev = h["evidence"]
        self.assertEqual((120, 240), (ev["cells"]["persuadables_treated"], ev["cells"]["rest_control"]))
        self.assertEqual((1.0, None), (ev["diff"], ev["ci"]))        # 점추정은 싣고 구간은 보류
        self.assertEqual(("undetermined", "undetermined"), (h["parts"]["persuadables_vs_rest"], h["result"]))
        self.assertIn("적은 쪽 < 10명", ev["reason"])
        json.dumps(h)

    def test_contradiction_of_either_claim_decides_the_whole(self) -> None:
        """재리뷰 반례 — ② 반증이면 ① 이 근거 부족 · 판정 불가여도 전체가 반증이다(두 주장의 논리곱)."""
        from src import main as cli
        from src.decision.uplift_report import quadrant_validation

        sd = (400, 320, 200, 100)                         # Sleeping Dogs 효과 0.8 − 0.5 = +30%p → ② 반증
        r = (4000, 2000, 2000, 1000)
        for label, p, part1 in (("① 근거 부족", (400, 200, 200, 100), "inconclusive"),
                                ("① 판정 불가", (50, 25, 50, 25), "undetermined")):
            with self.subTest(label):
                h = quadrant_validation(cell_test({"P": p, "R": r, "SD": sd}), "t_learner")
                ev = h["evidence"]["sleeping_dogs"]
                self.assertAlmostEqual(0.30, ev["effect"])
                self.assertGreater(ev["ci"][0], 0)
                self.assertEqual({"persuadables_vs_rest": part1, "sleeping_dogs_le_zero": "contradicted"}, h["parts"])
                self.assertEqual(("not_supported", "contradicted"), (h["result"], h["not_supported_kind"]))
                self.assertEqual([{"claim": "sleeping_dogs_le_zero", "reading": "② Sleeping Dogs 효과 > 0"}],
                                 h["contradicted_by"])
                line = cli.segment_lines({"segments": [], "hypotheses": [h]})[-1]
                self.assertTrue(line.endswith("H-SEG-2 지지되지 않음(반증 — ② Sleeping Dogs 효과 > 0)"), line)
                json.dumps(h)

    def test_persuadables_interval_on_the_opposite_side_is_a_contradiction(self) -> None:
        """재리뷰 반례 — ① 구간 전체가 0 아래면 근거 부족이 아니라 반증이다. ② 미확정(작은 칸)이어도 전체가 반증."""
        from src.decision.uplift_report import quadrant_validation

        h = quadrant_validation(cell_test({"P": (400, 100, 200, 100), "R": (4000, 2000, 2000, 1000),
                                           "SD": (50, 25, 50, 25)}), "t_learner")
        ev = h["evidence"]
        self.assertLess(ev["ci"][1], 0)                    # P 효과 −25%p, 나머지 ≈ 0
        self.assertEqual({"persuadables_vs_rest": "contradicted", "sleeping_dogs_le_zero": "undetermined"}, h["parts"])
        self.assertEqual(("not_supported", "contradicted"), (h["result"], h["not_supported_kind"]))
        self.assertEqual(["persuadables_vs_rest"], [c["claim"] for c in h["contradicted_by"]])
        self.assertEqual("contradicted", ev["persuadables_result"])
        # 구간이 0 을 포함하면 반증이 아니라 미확정 → 근거 부족
        h = quadrant_validation(cell_test({"P": (400, 200, 200, 100), "R": (4000, 2000, 2000, 1000),
                                           "SD": (50, 25, 50, 25)}), "t_learner")
        self.assertLess(h["evidence"]["ci"][0], 0)
        self.assertGreater(h["evidence"]["ci"][1], 0)
        self.assertEqual(("not_supported", "insufficient_evidence", []),
                         (h["result"], h["not_supported_kind"], h["contradicted_by"]))
        self.assertEqual("inconclusive", h["parts"]["persuadables_vs_rest"])

    def test_both_claims_contradicted_are_both_listed(self) -> None:
        from src import main as cli
        from src.decision.uplift_report import quadrant_validation

        h = quadrant_validation(cell_test({"P": (400, 100, 200, 100), "R": (4000, 2000, 2000, 1000),
                                           "SD": (400, 320, 200, 100)}), "t_learner")
        self.assertEqual(["persuadables_vs_rest", "sleeping_dogs_le_zero"], [c["claim"] for c in h["contradicted_by"]])
        line = cli.segment_lines({"segments": [], "hypotheses": [h]})[-1]
        self.assertIn("(반증 — ① Persuadables 효과 ≤ 나머지 · ② Sleeping Dogs 효과 > 0)", line)

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
        shares = {r["group"]: r for r in res["tiers"]["signup_tier"]["rows"]}
        self.assertAlmostEqual(0.5, shares["NEW"]["share_persuadables"])
        self.assertAlmostEqual(0.0, shares["NEW"]["share_rest"])
        json.dumps(res)

    def test_tier_shares_use_roster_customers_and_count_the_rest_apart(self) -> None:
        """리뷰 반례 — 두 집단 각 2명, 명부에 있는 고객(1명 · 2명)이 모두 NEW. 명부 밖을 분모에 넣으면 50% 대 100%."""
        import pandas as pd

        from src.decision.segments import persuadables_profile

        ids = pd.Index(["P1", "P2", "R1", "R2", "R3"])
        quad = pd.Series(["Persuadables", "Persuadables", "Sure Things", "Lost Causes", "Sure Things"], index=ids)
        feats = pd.DataFrame({"x": [1.0, 2.0, 3.0, 4.0, 5.0]}, index=ids)
        tiers = pd.DataFrame({"signup_tier": ["NEW", "NEW", "NEW", "UNKNOWN"]}, index=pd.Index(["P1", "R1", "R2", "R3"]))
        axis = persuadables_profile(quad, feats, tiers)["tiers"]["signup_tier"]
        shares = {r["group"]: r for r in axis["rows"]}
        self.assertEqual((1.0, 2 / 3), (shares["NEW"]["share_persuadables"], shares["NEW"]["share_rest"]))
        self.assertEqual({"n_total": 2, "n_in_roster": 1, "n_not_in_roster": 1, "n_roster_unknown": 0,
                          "n_missing_in_roster": 0}, axis["coverage"]["persuadables"])
        self.assertEqual((3, 0, 1), (axis["coverage"]["rest"]["n_in_roster"], axis["coverage"]["rest"]["n_not_in_roster"],
                                     axis["coverage"]["rest"]["n_roster_unknown"]))   # 명부 UNKNOWN ≠ 명부 밖
        self.assertAlmostEqual(1 / 3, shares["UNKNOWN"]["share_rest"])

    def test_tier_part_is_not_run_without_a_roster(self) -> None:
        """재리뷰 제안 — 명부가 없으면 Feature 차이는 내고 등급 부분만 not_run 과 사유를 남긴다."""
        import pandas as pd

        from src.decision.segments import persuadables_profile

        ids = pd.Index(["P1", "P2", "R1", "R2"])
        quad = pd.Series(["Persuadables", "Persuadables", "Sure Things", "Lost Causes"], index=ids)
        feats = pd.DataFrame({"x": [1.0, 2.0, 3.0, 5.0]}, index=ids)
        for tiers, reason in ((None, "명부(#218 t2 행)가 없다"), (pd.DataFrame({"signup_tier": []}), "t2 행이 없다"),
                              (pd.DataFrame(index=ids), "등급 열이 없다")):
            res = persuadables_profile(quad, feats, tiers)
            self.assertEqual(("not_run", {}), (res["tiers_status"], res["tiers"]))
            self.assertIn(reason, res["tiers_reason"])
            self.assertEqual(["x"], [r["feature"] for r in res["features"]])
        res = persuadables_profile(quad, feats, pd.DataFrame({"signup_tier": ["NEW"] * 4}, index=ids))
        self.assertEqual("ok", res["tiers_status"])
        self.assertNotIn("tiers_reason", res)

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

        return _run_sprint_parts("DECISION_API", "NotRun", "decision_fn", "uplift_test_report", "segment_hypotheses",
                                 "net_value_status")

    def test_net_value_blank_reason(self) -> None:
        import pandas as pd

        fn = self.parts()["net_value_status"]
        table = pd.DataFrame({"expected_net_value_krw": [None, 10.0]})
        cate = pd.DataFrame({"T1": [0.1, 0.2]})
        got = fn({"cate": cate, "clv": pd.Series([1.0, 2.0])}, {"T1": 500.0}, table)
        self.assertEqual("not_run", got["status"])
        self.assertIn("margin_rate 없음", got["reason"])
        self.assertIn("처치별 계획 비용 없음", fn({"cate": cate, "clv": 1, "margin_rate": 0.3}, None, table)["reason"])
        ok = fn({"cate": cate, "clv": pd.Series([1.0, 2.0]), "margin_rate": 0.3}, {"T1": 500.0}, table)
        self.assertEqual(("ok", 1), (ok["status"], ok["n_blank"]))

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

    def test_segment_hypothesis_labels(self) -> None:
        from src import main as cli

        segments = {"segments": [], "hypotheses": [
            {"id": "H-SEG-1", "result": "not_supported", "not_supported_kind": None},
            {"id": "H-SEG-2", "result": "partially_supported", "not_supported_kind": None}]}
        self.assertTrue(cli.segment_lines(segments)[-1].endswith("H-SEG-1 지지되지 않음 · H-SEG-2 부분 지지"))
        segments["hypotheses"][1] = {"id": "H-SEG-2", "result": "not_supported", "not_supported_kind": "contradicted"}
        self.assertTrue(cli.segment_lines(segments)[-1].endswith("H-SEG-2 지지되지 않음(반증)"))


if __name__ == "__main__":
    unittest.main()
