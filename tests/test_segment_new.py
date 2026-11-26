"""#219 1부 — AI 세그먼트 NEW 연결 · 4분면 분포 · 쏠림 기록 · 가설 H-SEG-1 · SEG-005 표(DR-219-segments).

  1. NEW = 명부 가입 시기 ``signup_tier = NEW``(DR-221) — ``UNKNOWN`` 은 NEW 가 아니다,
  2. 4분면 분포가 ``assign_quadrants`` 와 같고 실제 경계값을 싣는지,
  3. 쏠림 기록(NEW 고객의 원래 세그먼트)과 결과 전 등록한 가설 H-SEG-1 의 평가 규칙,
  4. ``segments_6plus.csv`` 열 · 우선순위(uplift × CLV) · 결손,
  5. run_sprint 연결(AST 로 떼어 실행 — 모듈을 import 하지 않는다)과 CLI 산출물이 같은 NEW 입력을 쓰는지.
시뮬레이터를 쓰지 않는다 — 합성 데이터다.
"""

from __future__ import annotations

import inspect
import math
import tempfile
import unittest
from importlib.util import find_spec
from pathlib import Path

DEPS = all(find_spec(m) for m in ("numpy", "pandas", "scipy"))
REASON = "BLOCKED: numpy/pandas/scipy 미설치"


def synthetic(n=2000, new_share=0.2, new_clv_factor=1.0, seed=1):
    import numpy as np
    import pandas as pd

    rng = np.random.default_rng(seed)
    ids = pd.Index([f"C{i:05d}" for i in range(n)])
    churn = pd.Series(rng.random(n), index=ids)
    cate = pd.DataFrame({"T1": rng.normal(0, .05, n), "T2": rng.normal(0, .05, n), "T3": rng.normal(.01, .05, n),
                         "T4": np.nan}, index=ids)
    clv = pd.Series(rng.gamma(2, 50000, n), index=ids)
    tier = pd.Series(rng.choice(["NEW", "EXISTING", "UNKNOWN"], n, p=[new_share, 0.95 - new_share, 0.05]), index=ids)
    clv[tier.to_numpy() == "NEW"] *= new_clv_factor
    return churn, cate, clv, tier


@unittest.skipUnless(DEPS, REASON)
class TestNewSegment(unittest.TestCase):
    def test_signup_tier_maps_to_new_and_unknown_is_not_new(self) -> None:
        import pandas as pd

        from src.decision.segments import assign_segments, is_new_from_signup_tier

        tier = pd.Series(["NEW", "EXISTING", "UNKNOWN", None], index=pd.Index([1, 2, 3, 4]))
        flags = is_new_from_signup_tier(tier)
        self.assertEqual(["1", "2", "3", "4"], list(flags.index))         # 명부의 customer_id 는 문자열
        self.assertEqual([True, False, None, None], list(flags))
        churn, cate, clv, tier = synthetic()
        seg = assign_segments(churn, cate, clv, is_new=is_new_from_signup_tier(tier))
        self.assertEqual(set(tier.index[tier == "NEW"]), set(seg.index[seg == "NEW"]))
        self.assertFalse((seg[tier == "UNKNOWN"] == "NEW").any())

    def test_quadrant_summary_matches_assign_quadrants(self) -> None:
        from src.decision import segments as sg

        churn, cate, clv, _ = synthetic()
        u = sg.uplift_score(cate)
        summary = sg.quadrant_summary(u, churn)
        want = sg.assign_quadrants(u, churn).value_counts().to_dict()
        self.assertEqual({k: v for k, v in want.items()}, {k: v for k, v in summary["counts"].items() if v})
        self.assertEqual(len(churn), sum(summary["counts"].values()))
        self.assertAlmostEqual(float(u.abs().quantile(sg.DEFAULT_THRESHOLDS["uplift_band_q"])),
                               summary["values"]["uplift_band"])
        self.assertEqual(sg.DEFAULT_THRESHOLDS["churn_high_q"], summary["quantiles"]["churn_high_q"])

    def test_shift_records_where_new_customers_came_from(self) -> None:
        from src.decision import segments as sg

        churn, cate, clv, tier = synthetic()
        flags = sg.is_new_from_signup_tier(tier)
        shift = sg.new_segment_shift(churn, cate, clv, flags)
        base = sg.assign_segments(churn, cate, clv)
        want = base[tier == "NEW"].value_counts().to_dict()
        self.assertEqual(want, shift["underlying_of_new"])
        self.assertEqual(base[tier == "EXISTING"].value_counts().to_dict(), shift["existing"])
        self.assertEqual((int((tier == "NEW").sum()), int((tier == "EXISTING").sum()), int((tier == "UNKNOWN").sum())),
                         (shift["n_new"], shift["n_existing"], shift["n_signup_unknown"]))
        self.assertEqual(["H-SEG-1", "H-SEG-2"], [h["id"] for h in shift["hypotheses"]])
        self.assertEqual("not_evaluated", shift["hypotheses"][1]["result"])   # 2부에서 평가

    def test_h_seg_1_rule(self) -> None:
        from src.decision import ab_test
        from src.decision import segments as sg

        churn, cate, clv, tier = synthetic(new_clv_factor=0.3)       # 신규의 CLV 를 낮춘 데이터 — 쏠림이 있다
        h = sg.new_segment_shift(churn, cate, clv, sg.is_new_from_signup_tier(tier))["hypotheses"][0]
        self.assertEqual("supported", h["result"])
        ev = h["evidence"]
        self.assertEqual(ab_test.ALPHA, ev["alpha"])                  # A/B 분석과 같은 유의수준
        self.assertGreater(ev["ci95"][0], 0)
        self.assertGreater(ev["share_new"], 0.97)                    # 강한 쏠림이어도 판정한다(적은 쪽 10명 기준을 쓰지 않는다)

        churn, cate, clv, tier = synthetic(seed=2)                   # 신규 · 기존 CLV 분포가 같은 데이터
        h = sg.new_segment_shift(churn, cate, clv, sg.is_new_from_signup_tier(tier))["hypotheses"][0]
        self.assertEqual("not_supported", h["result"])
        self.assertLessEqual(h["evidence"]["ci95"][0], 0)

        churn, cate, clv, tier = synthetic(new_share=0.02, seed=3)   # 신규 약 40명 — 표본 부족
        h = sg.new_segment_shift(churn, cate, clv, sg.is_new_from_signup_tier(tier))["hypotheses"][0]
        self.assertEqual("undetermined", h["result"])
        self.assertIn("표본 부족", h["evidence"]["reason"])

    def test_newcombe_interval_matches_the_published_example(self) -> None:
        """Newcombe(1998) Table II 의 예 56/70 − 48/80: 방법 10(hybrid score) 95% 구간 0.0524 ~ 0.3339."""
        from src.decision.segments import _two_proportions

        got = _two_proportions(56, 70, 48, 80, 0.05)
        self.assertAlmostEqual(0.2, got["diff"])
        self.assertAlmostEqual(0.0524, got["ci95"][0], places=4)
        self.assertAlmostEqual(0.3339, got["ci95"][1], places=4)
        # 한쪽 비율 1(100/100) — Wald 는 그쪽 분산을 0 으로 봐 구간이 좁아진다. score 구간은 그쪽 불확실성도 넣는다.
        extreme = _two_proportions(100, 100, 50, 100, 0.05)
        wald_lower = 0.5 - 1.959964 * math.sqrt(0.5 * 0.5 / 100)
        self.assertLess(extreme["ci95"][0], wald_lower)
        self.assertGreater(extreme["ci95"][0], 0)

    def test_segment_table(self) -> None:
        import numpy as np

        from src.decision import segments as sg

        churn, cate, clv, tier = synthetic(n=300)
        clv.iloc[:5] = np.nan
        seg = sg.assign_segments(churn, cate, clv, is_new=sg.is_new_from_signup_tier(tier))
        table = sg.segment_table(churn, cate, clv, seg, tier)
        for column in ("customer_id", "segment", "churn_probability", "uplift_score", "predicted_clv_12m",
                       "priority_score"):                              # SRS SEG-005 필수 열
            self.assertIn(column, table.columns)
        self.assertEqual(list(sg.SEGMENT_TABLE_COLUMNS), list(table.columns))
        self.assertEqual(sorted(table["customer_id"]), list(table["customer_id"]))
        row = table.set_index("customer_id")
        cid = churn.index[10]
        self.assertAlmostEqual(sg.uplift_score(cate)[cid] * clv[cid], row.loc[cid, "priority_score"])
        self.assertEqual(sg.assign_quadrants(sg.uplift_score(cate), churn)[cid], row.loc[cid, "quadrant"])
        self.assertEqual(cate.loc[cid].astype(float).idxmax(), row.loc[cid, "uplift_arm"])
        self.assertTrue(row.loc[churn.index[:5], "priority_score"].isna().all())   # CLV 결손 → 비움(0 아님)
        self.assertEqual(seg.map(sg.SEGMENT_PRD_ID)[cid], row.loc[cid, "segment_prd_id"])


@unittest.skipUnless(DEPS, REASON)
class TestReviewFixes(unittest.TestCase):
    """#326 리뷰 반례."""

    def test_new_survives_when_every_cate_is_missing(self) -> None:
        import numpy as np
        import pandas as pd

        from src.decision import segments as sg

        churn, cate, clv, tier = synthetic(n=200)
        empty = cate.assign(T1=np.nan, T2=np.nan, T3=np.nan, T4=np.nan)
        seg = sg.assign_segments(churn, empty, clv, is_new=sg.is_new_from_signup_tier(tier))
        self.assertEqual(set(tier.index[tier == "NEW"]), set(seg.index[seg == "NEW"]))   # 가입 시기만으로 NEW
        self.assertTrue((seg[tier != "NEW"] == sg.UNSCORED).all())                         # 나머지는 점수 결손
        self.assertIn("uplift_band", seg.attrs["thresholds"])
        self.assertFalse((sg.assign_segments(churn, empty, clv) == "NEW").any())

    def test_signup_tiers_is_the_observed_tiers_definition(self) -> None:
        import pandas as pd

        from src.decision import observed_tiers as ot

        t2 = "2026-03-01T00:00:00+09:00"
        signups = {"a": "2025-09-03", "b": "2025-09-02", "c": "2026-03-02", "d": None}   # 179 · 180 · 기준일 뒤 · 모름
        got = ot.signup_tiers(signups, t2, ["a", "b", "c", "d", "e"])
        self.assertEqual({"a": "NEW", "b": "EXISTING", "c": ot.UNKNOWN, "d": ot.UNKNOWN, "e": ot.UNKNOWN}, got.to_dict())
        self.assertEqual(180, ot.NEW_CUSTOMER_DAYS)
        from tests.test_feature_observed_tiers import Fixture

        frame = ot.observed_tiers(Fixture().events(), t2, list("abcd"), signups)   # 같은 정의 — 구매가 없어도 가입 등급은 같다
        self.assertEqual(frame["signup_tier"].to_dict(), got.reindex(list("abcd")).to_dict())


@unittest.skipUnless(DEPS, REASON)
class TestRunSprintSegments(unittest.TestCase):
    """run_sprint 는 import 하지 않는다 — 함수만 AST 로 떼어 실행한다."""

    def parts(self):
        from tests.test_feature_split_roster import _run_sprint_parts

        parts = _run_sprint_parts("DECISION_API", "NotRun", "decision_fn", "_pd", "new_customer_flags",
                                  "segments_with_new", "SEGMENTS_FILE", "segments_file")
        parts.update(inspect=inspect, Path=Path)
        return parts

    def roster(self, tier):
        import pandas as pd

        return pd.DataFrame({"customer_id": list(tier.index), "origin": "t2", "role": "test",
                             "signup_tier": list(tier)})

    def test_new_customer_flags(self) -> None:
        fn = self.parts()["new_customer_flags"]
        self.assertEqual("not_run", fn({})[2]["status"])
        _, _, _, tier = synthetic(n=50)
        roster = self.roster(tier)
        roster["origin"] = "t1"
        self.assertIn("t2 행이 없다", fn({"split_roster": roster})[2]["reason"])
        flags, signup, record, source = fn({"split_roster": self.roster(tier)}, tier.index)
        self.assertEqual(("ok", 50, 50, 0), (record["status"], record["n_scored"], record["n_in_roster"],
                                             record["n_outside_roster"]))
        self.assertEqual(int((tier == "NEW").sum()), int(flags.eq(True).sum()))
        self.assertEqual({"roster"}, set(source))

    def test_scored_customers_outside_the_roster(self) -> None:
        """#326 리뷰 — 명부(Eligible(t2)) 밖 점수 고객은 같은 정의로 정하고, 가입일 명부가 없으면 판정 안 함을 드러낸다."""
        import pandas as pd

        fn = self.parts()["new_customer_flags"]
        tier = pd.Series(["NEW", "EXISTING"], index=pd.Index(["A", "B"]))
        scored = pd.Index(["A", "B", "C", "D"])                          # C · D 는 명부 밖
        signups = {"C": "2026-02-20", "D": "2025-01-01"}                   # t2 기준 9일 · 400일 넘게
        ctx = {"split_roster": self.roster(tier), "signups_t2": signups, "t2": "2026-03-01T00:00:00+09:00"}
        flags, signup, record, source = fn(ctx, scored)
        self.assertEqual({"A": "NEW", "B": "EXISTING", "C": "NEW", "D": "EXISTING"}, signup.reindex(scored).to_dict())
        self.assertEqual({"A": "roster", "B": "roster", "C": "signups_t2", "D": "signups_t2"},
                         source.reindex(scored).to_dict())
        self.assertEqual(("ok", 2, 2, 1, 1), (record["status"], record["n_outside_roster"],
                                              record["n_outside_roster_judged"], record["n_new_in_roster"],
                                              record["n_new_outside_roster"]))
        # 가입일 명부가 없으면 명부 밖 고객은 판정하지 않는다 — partial · 수 · 사유
        flags, signup, record, source = fn({"split_roster": self.roster(tier)}, scored)
        self.assertEqual(("partial", 2), (record["status"], record["n_not_judged"]))
        self.assertIn("명부 밖 점수 고객 2명", record["reason"])
        self.assertTrue(signup.reindex(scored)[["C", "D"]].isna().all())
        self.assertTrue(source.reindex(scored)[["C", "D"]].isna().all())  # 명부의 UNKNOWN 과 구분된다
        # 명부가 없어도 가입일 명부가 있으면 전원을 같은 정의로 정한다
        flags, signup, record, source = fn({"signups_t2": signups, "t2": ctx["t2"]}, pd.Index(["C", "D"]))
        self.assertEqual(("ok", 0, 2), (record["status"], record["n_in_roster"], record["n_outside_roster_judged"]))

    def test_segments_with_new_and_file(self) -> None:
        import pandas as pd

        parts = self.parts()
        churn, cate, clv, tier = synthetic(n=400)
        scores = {"churn_p": churn, "cate": cate, "clv": clv}
        ctx = {"split_roster": self.roster(tier), "scores": scores}
        seg, record = parts["segments_with_new"](scores, ctx)
        self.assertEqual(set(tier.index[tier == "NEW"]), set(seg.index[seg == "NEW"]))
        self.assertEqual(("ok", "ok", "ok"), (record["new_input"]["status"], record["quadrants"]["status"],
                                              record["new_segment"]["status"]))
        self.assertIs(ctx["segments_t2"], seg)
        with tempfile.TemporaryDirectory() as tmp:
            extra: dict = {}
            out = parts["segments_file"](Path(tmp) / "artifacts" / "segments_6plus.csv", ctx, extra)
            self.assertEqual(("ok", 400), (out["status"], out["rows"]))
            table = pd.read_csv(extra["segments_6plus.csv"])
            self.assertEqual((seg == "NEW").sum(), (table["segment"] == "NEW").sum())
        # 명부가 없으면 NEW 를 판정하지 않고 사유를 남긴다 — 다른 기준으로 메우지 않는다
        seg, record = parts["segments_with_new"](scores, {"scores": scores})
        self.assertFalse((seg == "NEW").any())
        self.assertEqual(("not_run", "not_run"), (record["new_input"]["status"], record["new_segment"]["status"]))
        self.assertEqual("ok", record["quadrants"]["status"])
        self.assertEqual("not_run", parts["segments_file"](Path("unused.csv"), {}, {})["status"])

    def test_stage_uses_the_helper_and_the_file_is_written(self) -> None:
        import ast

        from tests.test_feature_split_roster import RUN_SPRINT

        tree = ast.parse(RUN_SPRINT.read_text(encoding="utf-8"))
        calls = {ast.unparse(n.func) for n in ast.walk(tree) if isinstance(n, ast.Call)}
        self.assertIn("segments_with_new", calls)
        self.assertIn("segments_file", calls)
        # segments 단계 안에서 assign_segments 를 따로 부르지 않는다(NEW 입력을 빠뜨리지 않게)
        stage = next(n for n in ast.walk(tree) if isinstance(n, ast.With)
                     and "log.stage('segments'" in ast.unparse(n.items[0].context_expr))
        inside = ast.unparse(stage)
        self.assertNotIn("decision_fn('assign_segments')", inside)


@unittest.skipUnless(DEPS, REASON)
class TestCliUsesTheSameNewInput(unittest.TestCase):
    def test_uplift_table_segments_equal_run_segments(self) -> None:
        from src import main as cli
        from src.decision import segments as sg

        churn, cate, clv, tier = synthetic(n=300)
        flags = sg.is_new_from_signup_tier(tier)
        scores = {"churn_p": churn, "cate": cate, "clv": clv}
        table = cli.uplift_table(scores, flags)
        run = sg.assign_segments(churn, cate, clv, is_new=flags)
        self.assertEqual(run.reindex(table.index).tolist(), table["segment"].tolist())
        self.assertIn("NEW", set(table["segment"]))
        self.assertNotIn("NEW", set(cli.uplift_table(scores)["segment"]))      # 입력이 없으면 예전과 같다


class TestCliSegmentLines(unittest.TestCase):
    def test_lines(self) -> None:
        from src import main as cli

        segments = {"segments": [{"name": "HV_PERSUADABLE", "n": 10}, {"name": "NEW", "n": 4}],
                    "new_input": {"status": "ok"},
                    "new_segment": {"hypotheses": [{"id": "H-SEG-1", "result": "supported"},
                                                   {"id": "H-SEG-2", "result": "not_evaluated"}]}}
        self.assertEqual(["  segments   HV_PERSUADABLE 10 · NEW 4",
                          "             가설(결과 전 등록, DR-219-segments) H-SEG-1 지지 · H-SEG-2 평가 전(2부)"],
                         cli.segment_lines(segments))
        lines = cli.segment_lines({"segments": [], "new_input": {"status": "not_run", "reason": "명부가 없다"}})
        self.assertEqual(["  segments   —", "             ! NEW 판정 안 함 — 명부가 없다"], lines)
        scope = {"status": "partial", "reason": "t2 가입일 명부가 없다", "n_scored": 10, "n_in_roster": 7,
                 "n_outside_roster": 3, "n_outside_roster_judged": 0, "n_new_in_roster": 2, "n_new_outside_roster": 0,
                 "n_unknown_in_roster": 1, "n_unknown_outside_roster": 0}
        lines = cli.segment_lines({"segments": [], "new_input": scope})
        self.assertIn("NEW 판정 범위 — 점수 고객 10명(명부 7명 · 명부 밖 3명 중 판정 0명)", lines[1])
        self.assertEqual("             ! NEW 일부만 판정 — t2 가입일 명부가 없다", lines[2])


if __name__ == "__main__":
    unittest.main()
