"""#303 ML-010 — AI 세그먼트(SEG-002)별 ML-009 지표(t1 시간 순서 검증, DR-303 「AI 세그먼트 축」).

  1. 세그먼트 행이 정의된 코드를 모두 싣고(n = 0 포함), 이탈 점수로 가른 세그먼트만 ``score_restricted`` 인지,
  2. 가설 H-ML010-4 평가 — 이탈 점수로 가른 세그먼트 · SEG-002 밖 라벨은 판정에 쓰지 않는지,
  3. ``SCORE_RESTRICTED_SEGMENTS`` 가 실제 ``assign_segments`` 에서 이탈 점수에 따라 갈리는 세그먼트와 같은지,
  4. run_sprint 연결(AST 로 떼어 실행 — 모듈을 import 하지 않는다): Uplift test 분할 T0 고객만 세그먼트를 받고, CLV 는
     t1 기준 시각으로 매기며, 이탈 점수는 시간 순서 검증 점수다. 호출 순서와 CLI 요약.
시뮬레이터를 쓰지 않는다 — 합성 데이터다.
"""

from __future__ import annotations

import ast
import unittest

from tests.test_churn_tier_metrics import _validation, fmt
from tests.test_feature_sprint_table import HAVE_ML, SKIP_REASON
from tests.test_feature_split_roster import HAVE_PANDAS

SEG002 = ("HV_PERSUADABLE", "HV_SURE_THING", "HV_LOST_CAUSE", "LV_PERSUADABLE", "LV_LOST_CAUSE", "NEW", "SLEEPING_DOG")


def _blocks(weak: str | None = None, per: int = 200, seed: int = 0):
    """SEG-002 7개 세그먼트 × ``per`` 명. ``weak`` 세그먼트만 고른 모델 점수가 무작위(기준선은 라벨을 그대로 따른다)."""
    import numpy as np
    import pandas as pd

    rng = np.random.RandomState(seed)
    ids, y, chosen, baseline, seg = [], [], [], [], []
    for k, code in enumerate(SEG002):
        labels = (np.arange(per) % 2).astype(int)
        good = labels * 0.6 + rng.uniform(0, 0.4, per)
        chosen += list(rng.uniform(0, 1, per) if code == weak else good)
        baseline += list(labels * 0.2 + rng.uniform(0, 0.75, per) if code != weak else labels.astype(float))
        y += list(labels)
        ids += [f"c{k}_{i}" for i in range(per)]
        seg += [code] * per
    return _validation(y, chosen, baseline, ids), pd.Series(seg, index=pd.Index(ids))


@unittest.skipUnless(HAVE_ML, SKIP_REASON)
class TestSegmentPerformance(unittest.TestCase):
    def test_rows_cover_every_code_and_only_score_split_segments_are_restricted(self) -> None:
        from src.decision import churn

        validation, seg = _blocks()
        out = churn.segment_performance(validation, seg.iloc[:-50], inputs={"n_segmented": len(seg) - 50})
        rows = out["axes"][churn.SEGMENT_AXIS]
        self.assertEqual(list(churn.SEGMENT_LABELS), [r["group"] for r in rows])            # n = 0 라벨도 싣는다
        self.assertEqual({"HV_SURE_THING", "HV_LOST_CAUSE"}, {r["group"] for r in rows if r["score_restricted"]})
        self.assertEqual((50, len(seg) - 50), (out["n_without_group"], out["n_grouped"]))   # 세그먼트 없는 고객은 전체에만
        self.assertEqual({"n_segmented": len(seg) - 50}, out["inputs"])
        self.assertIn("score_restricted", out["rule"])
        self.assertEqual({churn.SEGMENT_AXIS: "AI 세그먼트"}, out["axis_names"])

    def test_hypothesis_supported_without_weak_segment(self) -> None:
        from src.decision import churn

        out = churn.segment_performance(*_blocks())
        hyp = out["hypotheses"][0]
        self.assertEqual(("H-ML010-4", "supported"), (hyp["id"], hyp["result"]))
        self.assertEqual(5, hyp["evidence"]["n_groups_judged"])                             # 7 − 이탈 점수로 가른 2
        self.assertNotIn("HV_SURE_THING", hyp["evidence"]["groups_judged"])
        self.assertIn("같다는 증거도 아니다", hyp["reading"])                                # #325 리뷰와 같은 읽는 문구
        self.assertIn("모델 쪽으로 기울 수 있다", hyp["reading"])
        self.assertIn("Cawley", out["rule"]["selection_effect"])                           # 같은 Validation 선택 효과

    def test_weak_unrestricted_segment_is_not_supported(self) -> None:
        from src.decision import churn

        hyp = churn.segment_performance(*_blocks(weak="LV_PERSUADABLE"))["hypotheses"][0]
        self.assertEqual(("not_supported", ["LV_PERSUADABLE"]), (hyp["result"], hyp["evidence"]["below_baseline"]))
        self.assertIn("below_baseline", hyp["reading"])

    def test_weak_restricted_segment_is_shown_but_not_judged(self) -> None:
        from src.decision import churn

        out = churn.segment_performance(*_blocks(weak="HV_SURE_THING"))
        row = next(r for r in out["axes"][churn.SEGMENT_AXIS] if r["group"] == "HV_SURE_THING")
        self.assertEqual((True, True, ["below_baseline"]), (row["score_restricted"], row["weak"], row["weak_reasons"][:1]))
        self.assertEqual("supported", out["hypotheses"][0]["result"])                      # 표시는 하되 판정에 쓰지 않는다

    def test_undetermined_when_every_segment_is_small(self) -> None:
        from src.decision import churn

        hyp = churn.segment_performance(*_blocks(per=60))["hypotheses"][0]
        self.assertEqual("undetermined", hyp["result"])
        self.assertIn("100명", hyp["evidence"]["not_judged"]["NEW"])


    def test_input_gaps_and_judged_scope_are_published(self) -> None:
        """#329 리뷰 반례 — CLV 미실행 · NEW 일부 미판정이면 가치 세그먼트는 0명이다. 1/5개만 검정한 '지지'에 범위를 붙인다."""
        from src import main as cli
        from src.decision import churn

        validation, seg = _blocks()
        keep = seg.isin(["SLEEPING_DOG"])                          # CLV 가 없으면 가치 세그먼트 · NEW(일부)는 생기지 않는다
        seg = seg.where(keep, "CLV_UNKNOWN_NEAR_ZERO")
        inputs = {"clv": {"status": "not_run", "reason": "12개월 CLV 모델이 없다"},
                  "new": {"status": "partial", "n_not_judged": 300}}
        out = churn.segment_performance(validation, seg, inputs=inputs)
        hyp = out["hypotheses"][0]
        ev = hyp["evidence"]
        self.assertEqual(("supported", "1/5", ["SLEEPING_DOG"]), (hyp["result"], ev["scope"], ev["groups_judged"]))
        self.assertEqual(["HV_PERSUADABLE", "LV_PERSUADABLE", "LV_LOST_CAUSE"], ev["input_missing"])  # 표본 부족이 아니다
        self.assertIn("입력 결손 — CLV 미실행", ev["not_judged"]["LV_PERSUADABLE"])
        self.assertIn("100명", ev["not_judged"]["NEW"])          # NEW 는 일부 판정 — 0명은 표본 부족으로 남는다
        self.assertEqual(["CLV 미실행", "NEW 일부 미판정(300명)"], ev["input_gaps"])
        self.assertIn("검정한 1/5개 세그먼트(SLEEPING_DOG)", hyp["reading"])
        self.assertIn("입력 결손: CLV 미실행 · NEW 일부 미판정(300명)", hyp["reading"])
        self.assertEqual("post_hoc_validation", out["label_use"]["diagnostic"])
        lines = cli.churn_segment_lines({"by_segment": out}, fmt)
        self.assertIn("H-ML010-4 지지(1/5개 판정 · CLV 미실행 · NEW 일부 미판정(300명))", lines[3])
        self.assertIn("사후 Validation 진단", lines[4])

    def test_full_inputs_report_scope_without_gaps(self) -> None:
        from src.decision import churn

        hyp = churn.segment_performance(*_blocks(), inputs={"clv": {"status": "ok"}, "new": {"status": "ok"}})["hypotheses"][0]
        self.assertEqual(("5/5", [], []), (hyp["evidence"]["scope"], hyp["evidence"]["input_gaps"],
                                           hyp["evidence"]["input_missing"]))
        self.assertNotIn("입력 결손", hyp["reading"])


@unittest.skipUnless(HAVE_ML, SKIP_REASON)
class TestSegmentDefinitions(unittest.TestCase):
    def test_labels_are_the_assign_segments_codes(self) -> None:
        from src.decision import churn, segments

        expected = set(segments.SEGMENT_PRD_ID) | set(segments.UNKNOWN_VALUE.values()) | {segments.UNSCORED}
        self.assertEqual(expected, set(churn.SEGMENT_LABELS))
        self.assertEqual(set(segments.SEGMENT_PRD_ID), set(churn.SEG002_SEGMENTS))

    def test_judged_segments_do_not_depend_on_the_churn_score(self) -> None:
        """#329 리뷰 — 이탈 점수는 같은 t1 Validation 라벨로 튜닝했다. 그 점수를 어떻게 바꿔도 판정 대상 세그먼트의 배정은
        같고, 바뀌는 것은 이탈 점수로 가른 두 세그먼트 사이뿐이다(SEGMENT_LABEL_USE · DR-303 「라벨 사용 범위」)."""
        import numpy as np
        import pandas as pd

        from src.decision import churn, segments

        rng = np.random.RandomState(7)
        n = 2000
        ids = pd.Index([f"c{i}" for i in range(n)])
        cate = pd.DataFrame(rng.normal(0, 0.05, (n, 4)), index=ids, columns=["T1", "T2", "T3", "T4"])
        clv = pd.Series(rng.gamma(2, 50000, n), index=ids)
        is_new = pd.Series(rng.rand(n) < 0.1, index=ids)
        judged = set(churn.SEG002_SEGMENTS) - set(churn.SCORE_RESTRICTED_SEGMENTS)
        base = segments.assign_segments(pd.Series(rng.rand(n), index=ids), cate, clv, is_new=is_new)
        for other in (rng.rand(n), 1 - base.index.map(lambda c: int(c[1:]) / n).to_numpy(), np.full(n, 0.3)):
            seg = segments.assign_segments(pd.Series(other, index=ids), cate, clv, is_new=is_new)
            for code in judged:
                self.assertEqual(set(base.index[base == code]), set(seg.index[seg == code]), code)
            restricted = set(churn.SCORE_RESTRICTED_SEGMENTS)
            self.assertEqual(set(base.index[base.isin(restricted)]), set(seg.index[seg.isin(restricted)]))

    def test_score_restricted_segments_are_exactly_the_ones_split_by_churn_score(self) -> None:
        import numpy as np
        import pandas as pd

        from src.decision import churn, segments

        rng = np.random.RandomState(3)
        idx = pd.Index([f"c{i}" for i in range(2000)])
        cate = pd.DataFrame(rng.normal(0, 0.05, (2000, 4)), index=idx, columns=["T1", "T2", "T3", "T4"])
        clv = pd.Series(rng.lognormal(10, 1, 2000), index=idx)
        a = segments.assign_segments(pd.Series(rng.uniform(0, 1, 2000), index=idx), cate, clv)
        b = segments.assign_segments(pd.Series(rng.uniform(0, 1, 2000), index=idx), cate, clv)
        moved = a != b
        self.assertTrue(moved.any())
        self.assertEqual(set(churn.SCORE_RESTRICTED_SEGMENTS), set(a[moved]) | set(b[moved]))


@unittest.skipUnless(HAVE_PANDAS, SKIP_REASON)
class TestRunSprintWiring(unittest.TestCase):
    """run_sprint 는 import 하지 않는다 — 함수만 AST 로 떼어 실행하고, 호출 순서는 AST 로 본다."""

    def parts(self, calls: list):
        from tests.test_feature_split_roster import _run_sprint_parts

        ns = _run_sprint_parts("DECISION_API", "NotRun", "decision_fn", "_pd", "churn_segment_performance")
        real = ns["decision_fn"]

        def stub(key):
            if key == "predict_lifetime":
                def predict(model, events, index_time, customers=None):
                    import pandas as pd

                    calls.append(("predict_lifetime", index_time))
                    return pd.Series({f"c{i}": float(i) for i in range(400)})
                return predict
            if key == "segment_performance":
                def perf(validation, segments, *, inputs=None):
                    calls.append(("segment_performance", segments))
                    return {"status": "ok", "segments": segments, "inputs": inputs}
                return perf
            return real(key)

        ns["decision_fn"] = stub
        return ns["churn_segment_performance"]

    def ctx(self, **extra):
        import numpy as np
        import pandas as pd

        ids = [f"c{i}" for i in range(300)]                       # Validation = 탐색 RCT T0 군
        y = np.arange(300) % 2
        validation = _validation(y, y * 0.5 + np.linspace(0, 0.4, 300), y, ids)
        test_ids = [f"c{i}" for i in range(100, 400)]              # Uplift test 분할(전 군) — c100 부터
        arms = pd.Series(["T0" if i % 2 == 0 else "T3" for i in range(100, 400)], index=test_ids)
        cate = pd.DataFrame({t: np.linspace(-0.05, 0.1, 300) for t in ("T1", "T2", "T3", "T4")}, index=test_ids)
        roster = pd.DataFrame({"customer_id": ids, "origin": "t1", "role": "validation",
                               "signup_tier": ["NEW" if i % 10 == 0 else "EXISTING" for i in range(300)]})
        ctx = {"churn_validation": validation, "uplift_test": {"treatment": arms, "cate": {"t_learner": cate}},
               "clv_12m_model": object(), "events_t2": "EVENTS", "t1": "T1-TIME", "t2": "T2-TIME",
               "split_roster": roster}
        ctx.update(extra)
        return ctx

    def test_only_test_split_control_customers_get_segments_from_t1_inputs(self) -> None:
        calls: list = []
        out = self.parts(calls)(self.ctx(), "t_learner")
        self.assertEqual("ok", out["status"])
        segments = out["segments"]
        expected = [f"c{i}" for i in range(100, 300) if i % 2 == 0]   # Validation ∩ test 분할 T0
        self.assertEqual(expected, list(segments.index))
        self.assertIn(("predict_lifetime", "T1-TIME"), calls)          # CLV 는 t1 기준(t2 가 아니다)
        self.assertNotIn(("predict_lifetime", "T2-TIME"), calls)
        inputs = out["inputs"]
        self.assertEqual((300, 150, 100), (inputs["n_validation"], inputs["n_test_split_control"], inputs["n_segmented"]))
        self.assertIn("시간 순서 검증 점수", inputs["churn_score"])
        self.assertEqual(("ok", 20), (inputs["new"]["status"], inputs["new"]["n_new"]))  # c100, c110, … c290
        self.assertEqual((100, 0, 0), (inputs["new"]["n_in_roster"], inputs["new"]["n_not_judged"],
                                       inputs["new"]["n_unknown_in_roster"]))
        self.assertEqual(20, int((segments == "NEW").sum()))
        self.assertEqual("ok", inputs["clv"]["status"])
        self.assertTrue(set(inputs["thresholds"]) >= {"uplift_band", "churn_high", "clv_high"})

    def test_changing_t1_validation_scores_keeps_judged_segment_assignment(self) -> None:
        """#329 리뷰 — 실행 루프에서도 고른 모델의 Validation 점수만 바꾸면 판정 대상 세그먼트 배정이 그대로다."""
        import numpy as np

        first = self.parts([])(self.ctx(), "t_learner")
        ctx = self.ctx()
        y = np.arange(300) % 2
        ctx["churn_validation"] = _validation(y, 1 - np.linspace(0, 1, 300), y, [f"c{i}" for i in range(300)])
        second = self.parts([])(ctx, "t_learner")
        from src.decision import churn

        a, b = first["segments"], second["segments"]
        judged = set(churn.SEG002_SEGMENTS) - set(churn.SCORE_RESTRICTED_SEGMENTS)
        self.assertTrue((a[a.isin(judged)] == b[a.isin(judged)]).all())
        self.assertIn("같은 t1 Validation 라벨로 골랐다", second["inputs"]["churn_score"])
        self.assertEqual({"input_time": "t1", "model_fit_on": "Uplift train 분할 고객의 [t1, t2) 결과",
                          "own_outcome_used": False}, second["inputs"]["uplift_timing"])

    def test_without_clv_model_or_roster_value_and_new_are_not_judged(self) -> None:
        calls: list = []
        out = self.parts(calls)(self.ctx(clv_12m_model=None, split_roster=None), "t_learner")
        self.assertEqual(("not_run", "not_run"), (out["inputs"]["clv"]["status"], out["inputs"]["new"]["status"]))
        self.assertFalse({"NEW", "HV_PERSUADABLE", "LV_LOST_CAUSE"} & set(out["segments"]))
        self.assertTrue(set(out["segments"]) <= {"CLV_UNKNOWN_PERSUADABLE", "CLV_UNKNOWN_NEAR_ZERO", "SLEEPING_DOG"})

    def test_customers_missing_from_the_roster_are_counted_as_not_judged(self) -> None:
        """#326 리뷰와 같은 빈틈 — 명부 t1 validation 행이 없는 고객은 NEW 가 아닌 쪽으로 가므로 partial · 수 · 사유를 남긴다."""
        import pandas as pd

        ctx = self.ctx()
        roster = ctx["split_roster"]
        roster = roster[~roster["customer_id"].isin(["c100", "c102", "c110"])].copy()   # c110 은 NEW 였다
        roster.loc[roster["customer_id"] == "c104", "signup_tier"] = "UNKNOWN"
        roster = pd.concat([roster, pd.DataFrame({"customer_id": ["c102"], "origin": ["t1"], "role": ["train"],
                                                  "signup_tier": ["NEW"]})])        # 역할 불일치 — 판정에 쓰지 않는다
        out = self.parts([])({**ctx, "split_roster": roster}, "t_learner")
        new = out["inputs"]["new"]
        self.assertEqual(("partial", 3, 97, 1), (new["status"], new["n_not_judged"], new["n_in_roster"],
                                                 new["n_unknown_in_roster"]))
        self.assertIn("3명은 NEW 를 판정하지 않았다", new["reason"])
        self.assertEqual(18, new["n_new"])                                  # c100 · c110 이 빠졌다
        self.assertNotEqual("NEW", out["segments"]["c110"])

    def test_not_run_reasons(self) -> None:
        fn = self.parts([])
        reason = "불러온 모델 — 이 실행에서 시간 순서 검증을 하지 않았다"
        self.assertEqual({"status": "not_run", "reason": reason}, fn({"churn_validation_reason": reason}, "t_learner"))
        self.assertIn("test 분할 예측이 없다", fn(self.ctx(uplift_test=None), "t_learner")["reason"])
        self.assertIn("메타러너를 모른다", fn(self.ctx(), None)["reason"])
        self.assertIn("x_learner CATE 가 없다", fn(self.ctx(), "x_learner")["reason"])

    def test_called_after_uplift_and_roster_with_the_fitted_method(self) -> None:
        from tests.test_feature_split_roster import RUN_SPRINT

        tree = ast.parse(RUN_SPRINT.read_text(encoding="utf-8"))
        runner = next(fn for fn in tree.body if isinstance(fn, ast.FunctionDef)
                      and any(isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
                              and n.func.id == "churn_segment_performance" for n in ast.walk(fn)))
        src = {ast.unparse(n): n.lineno for n in ast.walk(runner) if isinstance(n, ast.Call)}
        call = "churn_segment_performance(ctx, uplift_eval.get('fitted_method'))"
        self.assertIn(call, src)
        pop = next(line for text, line in src.items() if text.startswith("evaluation.pop('_test'"))
        tiers = next(line for text, line in src.items() if text.startswith("churn_tier_performance("))
        self.assertLess(pop, src[call])
        self.assertLess(tiers, src[call])


class TestCliSegmentLines(unittest.TestCase):
    def test_lines(self) -> None:
        from src import main as cli

        row = lambda group, auc, n, small=False, weak=None, restricted=False: {   # noqa: E731
            "group": group, "n": n, "small_group": small, "weak": weak, "score_restricted": restricted,
            "models": {"random_forest": {"roc_auc": auc}}}
        churn = {"by_segment": {
            "status": "ok", "chosen": "random_forest", "n_grouped": 900, "n_without_group": 2100,
            "axes": {"ai_segment": [row("HV_PERSUADABLE", 0.8, 300, weak=False),
                                    row("HV_SURE_THING", 0.62, 200, weak=True, restricted=True),
                                    row("NEW", 0.7, 40, small=True), row("UNSCORED", None, 0)]},
            "hypotheses": [{"id": "H-ML010-4", "result": "supported"}]}}
        lines = cli.churn_segment_lines(churn, fmt)
        self.assertIn("세그먼트별 ROC-AUC (ML-010 · t1 Validation 중 Uplift test 분할 900명 · random_forest)", lines[0])
        self.assertEqual("               HV_PERSUADABLE 0.800(n 300) · !HV_SURE_THING* 0.620(n 200) · "
                         "NEW 0.700(n 40 표본 부족)", lines[1])
        self.assertIn("이탈 점수로 가른 세그먼트", lines[2])
        self.assertEqual("               가설(결과 전 등록, DR-303) H-ML010-4 지지", lines[3])
        self.assertIn("세그먼트 없는 Validation 고객 2100명", lines[4])
        self.assertEqual([], cli.churn_segment_lines({}, fmt))
        self.assertIn("없음 — Uplift test 분할 예측이 없다", cli.churn_segment_lines(
            {"by_segment": {"status": "not_run", "reason": "Uplift test 분할 예측이 없다"}}, fmt)[0])


if __name__ == "__main__":
    unittest.main()
