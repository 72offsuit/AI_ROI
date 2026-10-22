"""가상 A/B 분석 — SRM · z-검정 · CI · 검정력 · Holm (이슈 #145 · AB-002~005)."""

from __future__ import annotations

import unittest
from importlib.util import find_spec

DEPS = all(find_spec(m) for m in ("numpy", "pandas", "scipy"))
REASON = "BLOCKED: numpy/pandas/scipy 미설치"

if DEPS:
    import pandas as pd

    from src.decision.ab_test import analyze_ab, holm, sample_size_two_proportions


def frame(counts):
    """counts: {arm: (n, successes)} — 결정적으로 행을 깐다."""
    rows = []
    for arm, (n, x) in counts.items():
        rows += [(arm, 1)] * x + [(arm, 0)] * (n - x)
    return pd.DataFrame(rows, columns=["arm", "retained"])


@unittest.skipUnless(DEPS, REASON)
class TestAB(unittest.TestCase):
    def test_known_values(self) -> None:
        r = analyze_ab(frame({"T0": (1000, 200), "T3": (1000, 250)}), "arm", "retained")
        c = r["comparisons"]["T3"]
        self.assertAlmostEqual(0.05, c["diff"])
        # 합동 p = 0.225, se = sqrt(.225*.775*2/1000) = 0.018675 → z = 2.6774
        self.assertAlmostEqual(2.6774, c["z"], places=3)
        self.assertAlmostEqual(0.00742, c["p_value"], places=4)
        lo, hi = c["ci95"]
        self.assertLess(lo, 0.05)
        self.assertGreater(lo, 0)
        self.assertFalse(r["srm"]["srm_detected"])
        self.assertAlmostEqual(c["p_value"], c["chi_square"]["p_value"], places=6)  # 2×2 χ² ≡ z²

    def test_srm_detected(self) -> None:
        r = analyze_ab(frame({"T0": (1000, 200), "T3": (1300, 260)}), "arm", "retained")
        self.assertTrue(r["srm"]["srm_detected"])

    def test_sample_size_textbook(self) -> None:
        # p 0.20 → 0.25, α=.05 양측, 검정력 .8 → 군당 약 1,094 (정규근사 표준식)
        n = sample_size_two_proportions(0.20, 0.25)
        self.assertTrue(1080 <= n <= 1110, n)
        self.assertIsNone(sample_size_two_proportions(0.2, 0.2))

    def test_holm(self) -> None:
        adj = holm({"a": 0.01, "b": 0.04, "c": 0.03, "d": None})
        self.assertAlmostEqual(0.03, adj["a"])
        self.assertAlmostEqual(0.06, adj["c"])
        self.assertAlmostEqual(0.06, adj["b"])     # 단조 유지
        self.assertIsNone(adj["d"])

    def test_continuous_outcome_welch(self) -> None:
        import numpy as np

        rng = np.random.default_rng(0)
        df = pd.DataFrame({"arm": ["T0"] * 2000 + ["T3"] * 2000 + ["T1"] * 2000,
                           "revenue": np.concatenate([rng.gamma(2, 10000, 2000),
                                                      rng.gamma(2, 11500, 2000),
                                                      rng.gamma(2, 10000, 2000)])})
        df.loc[0, "revenue"] = np.nan
        r = analyze_ab(df, "arm", "revenue", control="T0")
        self.assertEqual("continuous", r["outcome_kind"])
        self.assertEqual(1, r["n_outcome_missing_excluded"])
        c = r["comparisons"]["T3"]
        from scipy.stats import ttest_ind

        ref = ttest_ind(df.loc[df.arm == "T3", "revenue"], df.loc[df.arm == "T0", "revenue"].dropna(),
                        equal_var=False)
        self.assertAlmostEqual(float(ref.pvalue), c["p_value"], places=10)
        self.assertLess(c["ci95"][0], c["diff"])
        self.assertIsNotNone(c["required_n_per_arm_observed_effect"])
        self.assertIn("p_value_holm", r["comparisons"]["T1"])

    def test_binary_kind_is_reported(self) -> None:
        r = analyze_ab(frame({"T0": (100, 20), "T3": (100, 30)}), "arm", "retained")
        self.assertEqual("binary", r["outcome_kind"])


if __name__ == "__main__":
    unittest.main()
