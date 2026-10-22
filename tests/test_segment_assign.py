"""세그먼트 · 4분면 · 우선순위 점수 (이슈 #145 · SEG-001~004 · UP-004)."""

from __future__ import annotations

import unittest
from importlib.util import find_spec

DEPS = all(find_spec(m) for m in ("numpy", "pandas"))
REASON = "BLOCKED: numpy/pandas/scikit-learn 미설치"

if DEPS:
    import numpy as np
    import pandas as pd

    from src.decision.segments import (
        UNKNOWN_VALUE, assign_quadrants, assign_segments, priority_score, segment_stats,
    )


def grid():
    """CLV 고/저 × uplift 양/0/음 × 위험 고/저 를 손으로 깔아 둔 표본(분위수 경계가 예측 가능).

    uplift ≈ 0 고객이 다수(2/3)라 |uplift| 의 60% 분위수 = 0 → 띠 반폭 0 이 된다.
    """
    rows = []
    i = 0
    for clv in (100.0, 1000.0):                  # 1000 = 상위
        for u in (0.3, 0.0, -0.3):
            for p in (0.1, 0.9):
                for _ in range((10 if clv == 100.0 else 3) * (4 if u == 0.0 else 1)):
                    rows.append((f"C{i:08d}", clv, u, p))
                    i += 1
    df = pd.DataFrame(rows, columns=["cid", "clv", "u", "p"]).set_index("cid")
    cate = pd.DataFrame({"T1": df["u"] / 2, "T2": np.nan, "T3": df["u"], "T4": np.nan}, index=df.index)
    return df, cate


@unittest.skipUnless(DEPS, REASON)
class TestSegments(unittest.TestCase):
    def test_all_prd_segments_appear(self) -> None:
        df, cate = grid()
        is_new = pd.Series(False, index=df.index)
        is_new.iloc[0] = True
        seg = assign_segments(df["p"], cate, df["clv"], is_new=is_new)
        got = set(seg.unique())
        for s in ("HV_PERSUADABLE", "HV_SURE_THING", "HV_LOST_CAUSE", "LV_PERSUADABLE",
                  "LV_LOST_CAUSE", "NEW", "SLEEPING_DOG"):
            self.assertIn(s, got)
        hv_pos = df.index[(df["clv"] == 1000) & (df["u"] > 0)]
        self.assertTrue((seg[hv_pos] == "HV_PERSUADABLE").all())
        self.assertTrue((seg[df.index[(df["u"] < 0)][1:]] == "SLEEPING_DOG").all())

    def test_without_clv_value_axis_is_unknown(self) -> None:
        df, cate = grid()
        seg = assign_segments(df["p"], cate, None)
        self.assertFalse(seg.str.startswith("HV_").any())
        self.assertFalse(seg.str.startswith("LV_").any())
        self.assertIn(UNKNOWN_VALUE["persuadable"], set(seg))

    def test_quadrants(self) -> None:
        df, cate = grid()
        q = assign_quadrants(df["u"], df["p"])
        self.assertEqual({"Persuadables", "Sure Things", "Lost Causes", "Sleeping Dogs"}, set(q))

    def test_priority_score(self) -> None:
        df, cate = grid()
        s = priority_score(cate, df["clv"])
        self.assertAlmostEqual(0.3 * 1000.0, s[(df["clv"] == 1000) & (df["u"] > 0)].iloc[0])
        self.assertTrue(priority_score(cate, None).isna().all())   # CLV 없으면 계산 불가
        s2 = priority_score(cate, df["clv"], cost=7030)
        self.assertAlmostEqual(300.0 - 7030, s2[(df["clv"] == 1000) & (df["u"] > 0)].iloc[0])

    def test_stats(self) -> None:
        df, cate = grid()
        seg = assign_segments(df["p"], cate, df["clv"])
        rows = segment_stats(seg, df["p"], cate, df["clv"])
        self.assertEqual(len(df), sum(r["customer_count"] for r in rows))
        self.assertAlmostEqual(1.0, sum(r["ratio"] for r in rows))


if __name__ == "__main__":
    unittest.main()
