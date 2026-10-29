"""스프린트 1 CLV(미래 매출) 평가 (이슈 #144). 픽스처 기준 — 실제 결과 아님.

실행:
    python -m unittest tests.test_clv_sprint -v
"""

from __future__ import annotations

import unittest

from tests.test_feature_sprint_table import FIXTURE_T0, HAVE_ML, SKIP_REASON, make_events, fixture_observation


@unittest.skipUnless(HAVE_ML, SKIP_REASON)
class TestCLV(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        import pandas as pd

        from src.decision.data import _coerce
        from src.decision.features.sprint_table import build_feature_table, build_outcomes

        events = _coerce(pd.DataFrame.from_records(make_events(n_customers=160)))
        cls.X = build_feature_table(events, FIXTURE_T0)
        cls.y = build_outcomes(events, FIXTURE_T0, observation=fixture_observation())

    def test_eval_contract(self) -> None:
        from src.decision.clv import evaluate_clv

        out = evaluate_clv(self.X, self.y["revenue"], horizon_days=42, seed=5)
        self.assertEqual(42, out["horizon_days"])
        self.assertEqual(len(self.X), out["n"])
        self.assertEqual(["historical_avg", "hist_gb"], [m["name"] for m in out["models"]])
        self.assertEqual(["baseline", "proposed"], [m["kind"] for m in out["models"]])
        for m in out["models"]:
            for key in ("mae", "rmse", "spearman", "top20_hit"):
                self.assertIsInstance(m[key], float)
            self.assertGreaterEqual(m["rmse"], m["mae"])
            self.assertTrue(0.0 <= m["top20_hit"] <= 1.0)

    def test_missing_target_is_excluded_and_counted(self) -> None:
        import numpy as np

        from src.decision.clv import evaluate_clv

        target = self.y["revenue"].copy()
        target.iloc[:7] = np.nan
        out = evaluate_clv(self.X, target, horizon_days=42, seed=5)
        self.assertEqual(7, out["n_excluded_missing_target"])
        self.assertEqual(len(self.X) - 7, out["n"])

    def test_fit_predict_nonnegative(self) -> None:
        from src.decision.clv import fit_clv, predict_clv

        model = fit_clv(self.X, self.y["revenue"], seed=5)
        pred = predict_clv(model, self.X)
        self.assertEqual(list(self.X.index), list(pred.index))
        self.assertTrue((pred >= 0).all())

    def test_top_hit(self) -> None:
        import numpy as np

        from src.decision.clv import top_hit

        a = np.arange(10.0)
        self.assertEqual(1.0, top_hit(a, a))
        self.assertEqual(0.0, top_hit(a, -a))


if __name__ == "__main__":
    unittest.main()
