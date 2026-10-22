"""PSI · 드리프트 · 성능 추이 · 경보 — 합성 분포로 정답 대조 (스프린트 1 D12, 에픽 #142)."""

from __future__ import annotations

import math
import unittest
from importlib.util import find_spec

DEPS = all(find_spec(m) for m in ("numpy", "pandas", "sklearn"))
REASON = "BLOCKED: numpy/pandas/scikit-learn 미설치"

if DEPS:
    import numpy as np
    import pandas as pd

    from src.decision.monitoring import (LEVEL_ALERT, LEVEL_NA, LEVEL_STABLE, LEVEL_WARNING, alerts,
                                         feature_drift, performance_trend, psi, psi_level)


@unittest.skipUnless(DEPS, REASON)
class TestPsi(unittest.TestCase):
    def setUp(self) -> None:
        self.rng = np.random.default_rng(7)

    def test_same_distribution_near_zero(self) -> None:
        a, b = self.rng.normal(0, 1, 20000), self.rng.normal(0, 1, 20000)
        self.assertLess(psi(a, b), 0.01)
        self.assertAlmostEqual(0.0, psi(a, a), places=12)

    def test_shifted_distribution_large(self) -> None:
        a, b = self.rng.normal(0, 1, 20000), self.rng.normal(1, 1, 20000)
        self.assertGreater(psi(a, b), 0.25)
        small = psi(a, self.rng.normal(0.3, 1, 20000))
        self.assertGreater(small, 0.05)
        self.assertLess(small, psi(a, b))  # 이동이 클수록 크다

    def test_known_value_two_bins(self) -> None:
        # 기준 0/1 반반 → 실제 0 이 80 %. 구간: (<0) (0] (0,1] (>1) 결손. 앞·뒤·결손은 EPS 바닥.
        e = np.array([0.0] * 50 + [1.0] * 50)
        a = np.array([0.0] * 80 + [1.0] * 20)
        expect = (0.8 - 0.5) * math.log(0.8 / 0.5) + (0.2 - 0.5) * math.log(0.2 / 0.5)
        self.assertAlmostEqual(expect, psi(e, a), places=6)

    def test_missing_is_its_own_bin(self) -> None:
        base = self.rng.normal(0, 1, 10000)
        cur = base.copy()
        cur[:3000] = np.nan  # 값 분포는 그대로, 결손률만 0 → 30 %
        self.assertGreater(psi(base, cur), 0.25)
        both = base.copy()
        both[:3000] = np.nan
        self.assertLess(psi(both, both), 1e-12)  # 결손이 같으면 드리프트 아님

    def test_out_of_range_detected(self) -> None:
        const = np.zeros(1000)
        self.assertGreater(psi(const, const - 1), 0.25)  # 기준 최솟값 아래로 이동
        self.assertGreater(psi(const, const + 1), 0.25)  # 기준 최댓값 위로 이동

    def test_empty_is_nan(self) -> None:
        self.assertTrue(math.isnan(psi([], [1.0, 2.0])))
        self.assertEqual(LEVEL_NA, psi_level(math.nan))

    def test_categorical(self) -> None:
        e = pd.Series(["a"] * 50 + ["b"] * 50)
        self.assertLess(psi(e, e), 1e-12)
        self.assertGreater(psi(e, pd.Series(["a"] * 90 + ["b"] * 10)), 0.25)

    def test_levels(self) -> None:
        self.assertEqual(LEVEL_STABLE, psi_level(0.05))
        self.assertEqual(LEVEL_WARNING, psi_level(0.1))
        self.assertEqual(LEVEL_WARNING, psi_level(0.2))
        self.assertEqual(LEVEL_ALERT, psi_level(0.25))


@unittest.skipUnless(DEPS, REASON)
class TestFeatureDrift(unittest.TestCase):
    def test_table(self) -> None:
        rng = np.random.default_rng(1)
        ref = pd.DataFrame({"stable": rng.normal(0, 1, 5000), "moved": rng.normal(0, 1, 5000),
                            "only_ref": rng.normal(0, 1, 5000)})
        cur = pd.DataFrame({"stable": rng.normal(0, 1, 5000), "moved": rng.normal(2, 1, 5000)})
        d = feature_drift(ref, cur)
        self.assertEqual(LEVEL_STABLE, d.loc["stable", "level"])
        self.assertEqual(LEVEL_ALERT, d.loc["moved", "level"])
        self.assertEqual(LEVEL_NA, d.loc["only_ref", "level"])  # 빠뜨리지 않고 계산 불가로 남긴다
        self.assertTrue(pd.isna(d.loc["only_ref", "psi"]))  # 0 이 아니다
        self.assertGreater(d.loc["moved", "ks_stat"], 0.5)
        a = alerts(d, None)
        self.assertEqual(["moved"], [x["feature"] for x in a])
        self.assertEqual(LEVEL_ALERT, a[0]["severity"])


@unittest.skipUnless(DEPS, REASON)
class TestPerformanceTrend(unittest.TestCase):
    def test_trend_and_alerts(self) -> None:
        y = np.array([0, 0, 1, 1] * 50)
        good = np.where(y == 1, 0.8, 0.2).astype(float)
        noisy = np.array([0.6, 0.4, 0.4, 0.6] * 50)  # AUC 0.5
        trend = performance_trend({"t1": (y, good), "t2": (y, noisy), "t3": (np.zeros(10), np.full(10, 0.3))},
                                  threshold=0.5)
        self.assertAlmostEqual(1.0, trend.loc["t1", "roc_auc"])
        self.assertAlmostEqual(0.5, trend.loc["t2", "roc_auc"])
        self.assertAlmostEqual(0.04, trend.loc["t1", "brier"])
        self.assertAlmostEqual(1.0, trend.loc["t1", "precision"])
        self.assertAlmostEqual(0.5, trend.loc["t2", "recall"])
        self.assertTrue(pd.isna(trend.loc["t3", "roc_auc"]))  # 단일 클래스 — 0.5 로 채우지 않는다
        a = alerts(None, trend)
        perf = {(x["time"], x["metric"]) for x in a if x["type"] == "performance"}
        self.assertIn(("t2", "roc_auc"), perf)
        self.assertIn(("t2", "brier"), perf)
        self.assertIn(("t3", "roc_auc"), {(x["time"], x["metric"]) for x in a
                                          if x["type"] == "performance_not_evaluable"})

    def test_dataframe_input_and_no_threshold(self) -> None:
        frame = pd.DataFrame({"time": ["a"] * 4 + ["b"] * 4, "y": [0, 1, 0, 1] * 2,
                              "p": [0.1, 0.9, 0.2, 0.8, 0.9, 0.1, 0.8, 0.2]})
        trend = performance_trend(frame)
        self.assertAlmostEqual(1.0, trend.loc["a", "roc_auc"])
        self.assertAlmostEqual(0.0, trend.loc["b", "roc_auc"])
        self.assertTrue(pd.isna(trend.loc["a", "precision"]))  # 임계값을 여기서 고르지 않는다


if __name__ == "__main__":
    unittest.main()
