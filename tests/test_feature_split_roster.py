"""#218 공통 명부(DR-218-common-roster) — 기준일별 역할 · 관측 등급 · 관측 완전성.

★ 픽스처는 이 파일 안의 작은 합성 이벤트다. 시뮬레이터를 참고하지 않았고 공개 계약만 따른다.

실행:
    python -m unittest tests.test_feature_split_roster -v
"""

from __future__ import annotations

import ast
import importlib.util
import itertools
import unittest
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

HAVE_PANDAS = all(importlib.util.find_spec(name) is not None for name in ("numpy", "pandas"))
SKIP_REASON = "BLOCKED: numpy/pandas 미설치"

KST = timezone(timedelta(hours=9))
T1 = datetime(2026, 7, 1, tzinfo=KST)
T_PRIOR = T1 - timedelta(days=42)
T2 = T1 + timedelta(days=42)
_ids = itertools.count(1)


def _event(cid: str, when: datetime, etype: str, **fields) -> dict:
    row = {"event_id": f"e{next(_ids):06d}", "customer_id": cid, "timestamp": when, "event_type": etype,
           "session_id": "s1", "order_id": None, "order_amount": None, "product_id": None, "category": None}
    row.update(fields)
    return row


def _events():
    import pandas as pd

    rows = [_event("anchor", T_PRIOR - timedelta(days=200), "session_start")]
    for i, cid in enumerate(("a", "b", "c", "d", "e", "f"), start=1):
        for k in range(i):  # 고객마다 구매 횟수가 다르다 — a 1회 … f 6회(t_prior 전)
            rows.append(_event(cid, T_PRIOR - timedelta(days=5 + 10 * k), "purchase",
                               order_id=f"o-{cid}-{k}", order_amount=1_000 * i))
    rows.append(_event("a", T1 - timedelta(days=3), "session_start"))       # t_prior 뒤 · t1 전
    rows.append(_event("a", T2 + timedelta(days=1), "purchase", order_id="o-a-late", order_amount=9_000))  # t2 뒤
    frame = pd.DataFrame(rows)
    frame["timestamp"] = pd.to_datetime(frame["timestamp"], utc=True).dt.tz_convert("Asia/Seoul")
    frame["order_amount"] = pd.array(frame["order_amount"].tolist(), dtype="Int64")
    return frame


SIGNUPS = {cid: date(2025, 1, 1) for cid in "abcdef"}
ARMS = {"a": "T0", "b": "T1", "d": "T0", "e": "T0"}


def _cohorts() -> dict:
    return {
        "t_prior": {"index_time": T_PRIOR, "label_window": (T_PRIOR, T1), "eligible": ["a", "b", "c"],
                    "labeled": ["a", "b"]},
        "t1": {"index_time": T1, "label_window": (T1, T2), "eligible": ["a", "b", "d", "e"],
               "labeled": ["a", "b", "d"], "rct_arm": ARMS},
        # t2 의 labeled 는 쓰지 않는다 — 넣어도 역할이 바뀌지 않아야 한다
        "t2": {"index_time": T2, "label_window": None, "eligible": ["a", "b", "c", "d", "f"],
               "labeled": ["f"], "rct_arm": ARMS},
    }


@unittest.skipUnless(HAVE_PANDAS, SKIP_REASON)
class SplitRosterTests(unittest.TestCase):
    def build(self, cohorts=None, **kwargs):
        from src.decision.split_roster import build_split_roster

        kwargs.setdefault("order_items", None)
        kwargs.setdefault("observation_complete", True)
        return build_split_roster(_events(), SIGNUPS, cohorts=cohorts or _cohorts(), **kwargs)

    def roles(self, roster, origin):
        part = roster[roster["origin"] == origin].set_index("customer_id")
        return part["role"].to_dict(), part["exclusion_reason"].dropna().to_dict()

    def test_roles_per_origin(self):
        roster, record, _ = self.build()
        self.assertEqual(self.roles(roster, "t_prior"),
                         ({"a": "train", "b": "train", "c": "excluded"}, {"c": "no_feature_or_label"}))
        self.assertEqual(self.roles(roster, "t1"),
                         ({"a": "validation", "b": "excluded", "d": "validation", "e": "excluded"},
                          {"b": "rct_treated", "e": "no_feature_or_label"}))
        # t2 — 처치받은 b 제외 · 학습 고객(a · b@t_prior · d) 은 기존 고객 평가 · 나머지(c · f)가 과제 Test
        self.assertEqual(self.roles(roster, "t2"),
                         ({"a": "future_existing", "b": "excluded", "c": "test", "d": "future_existing",
                           "f": "test"}, {"b": "rct_treated"}))
        self.assertEqual({"train": 2, "excluded": 1}, record["origins"]["t_prior"]["roles"])
        self.assertEqual({"rct_treated": 1}, record["origins"]["t2"]["exclusions"])

    def test_t2_roles_do_not_look_at_labels(self):
        cohorts = _cohorts()
        cohorts["t2"] = {**cohorts["t2"], "labeled": None}
        a, _, _ = self.build(cohorts)
        b, record, _ = self.build()
        self.assertEqual(self.roles(a, "t2"), self.roles(b, "t2"))
        self.assertIs(False, record["origins"]["t2"]["labels_used_for_roles"])
        self.assertIsNone(record["origins"]["t2"]["label_window"])

    def test_one_row_per_customer_and_origin_without_labels(self):
        from src.decision.split_roster import COLUMNS

        roster, record, tiers = self.build()
        self.assertEqual(list(COLUMNS), list(roster.columns))
        self.assertFalse(roster.duplicated(["customer_id", "origin"]).any())
        for forbidden in ("churn", "label", "probability", "purchases", "revenue"):
            self.assertNotIn(forbidden, roster.columns)
        self.assertEqual(3 + 4 + 5, record["n_rows"])
        self.assertEqual({"t_prior", "t1", "t2"}, set(tiers))
        self.assertEqual(["a", "b", "c"], list(tiers["t_prior"].index))   # 등급 모집단 = 그 기준일 Eligible

    def test_stratum_tiers_and_rct_arm_columns(self):
        roster, record, _ = self.build()
        prior = roster[roster["origin"] == "t_prior"].set_index("customer_id")
        self.assertEqual("F1_ONCE", prior.loc["a", "frequency_tier"])
        self.assertEqual(prior.loc["a", "value_tier"] + "|F1_ONCE", prior.loc["a", "stratum"])
        self.assertTrue(prior["rct_arm"].isna().all())                    # t_prior 는 실험 전
        t2 = roster[roster["origin"] == "t2"].set_index("customer_id")
        self.assertEqual("T0", t2.loc["a", "rct_arm"])
        self.assertTrue(pd_isna(t2.loc["f", "rct_arm"]))                  # t1 에 배정되지 않은 고객
        self.assertEqual("observed-tier-v1", record["origins"]["t1"]["tiers"]["version"])
        self.assertIn("train", record["origins"]["t_prior"]["tier_counts_by_role"])

    def test_event_counts_and_observation_flag(self):
        roster, _, _ = self.build(observation_complete=False)
        prior = roster[roster["origin"] == "t_prior"].set_index("customer_id")
        self.assertEqual(1, prior.loc["a", "n_events_before_cutoff"])     # t_prior 뒤 방문 · t2 뒤 구매는 세지 않는다
        t1 = roster[roster["origin"] == "t1"].set_index("customer_id")
        self.assertEqual(2, t1.loc["a", "n_events_before_cutoff"])
        self.assertFalse(roster["observation_complete"].any())

    def test_missing_origin_is_not_run_with_reason(self):
        cohorts = _cohorts()
        del cohorts["t_prior"]
        roster, record, _ = self.build(cohorts, not_run={"t_prior": "앞 기준일 라벨 관측 근거 미충족"})
        self.assertEqual({"status": "not_run", "reason": "앞 기준일 라벨 관측 근거 미충족"}, record["origins"]["t_prior"])
        self.assertNotIn("t_prior", set(roster["origin"]))
        # 앞 기준일이 없으면 학습 고객은 t1 validation 뿐이다 — c 는 t_prior 학습 고객이 아니었으므로 test
        self.assertEqual("test", self.roles(roster, "t2")[0]["c"])

    def test_unknown_origin_is_rejected(self):
        with self.assertRaises(ValueError):
            self.build({"t3": _cohorts()["t2"]})

    def test_frequency_band_check_uses_eligible_shares(self):
        _, record, _ = self.build()
        check = record["origins"]["t_prior"]["frequency_band_check"]
        self.assertEqual(3, check["n"])
        # a 1회 · b 2회 · c 3회 → F1 1/3 · F2 2/3(60% 초과) · F3 · F4 0
        self.assertAlmostEqual(1 / 3, check["shares"]["F1_ONCE"])
        self.assertAlmostEqual(2 / 3, check["shares"]["F2_RARE"])
        self.assertEqual(["F2_RARE", "F3_REGULAR", "F4_FREQUENT"], check["outside"])

    def test_official_test_is_a_candidate_only_from_a_complete_roster_built_before_t2_outcomes(self):
        roster, record, _ = self.build()
        self.assertEqual({"status": "candidate", "n_test": 2, "reasons": []},
                         {k: record["official_test"][k] for k in ("status", "n_test", "reasons")})
        cohorts = _cohorts()
        del cohorts["t_prior"]
        withheld = {
            "t_prior_missing": self.build(cohorts, not_run={"t_prior": "앞 기준일 not_run"}),
            "no_observation_evidence": self.build(observation_complete=False),
            "outcomes_read_first": self.build(t2_outcomes_read="S0 분기 결과 읽은 뒤 생성"),
        }
        for case, (_, rec, _) in withheld.items():
            with self.subTest(case=case):
                self.assertEqual("withheld", rec["official_test"]["status"])
                self.assertEqual(1, len(rec["official_test"]["reasons"]))
        self.assertIn("t_prior", withheld["t_prior_missing"][1]["official_test"]["reasons"][0])
        cohorts = _cohorts()
        del cohorts["t2"]
        _, rec, _ = self.build(cohorts)
        self.assertIsNone(rec["official_test"]["n_test"])

    def test_order_items_frame_from_exchange_orders(self):
        from src.decision.split_roster import order_items_frame

        item = SimpleNamespace(product_id="p1", quantity=2, unit_price=1_500)
        orders = {"o1": SimpleNamespace(items=(item,)), "o2": SimpleNamespace(items=())}
        frame = order_items_frame(orders)
        self.assertEqual([["o1", "p1", 2, 1_500]], frame.values.tolist())
        self.assertIsNone(order_items_frame(None))


RUN_SPRINT = Path(__file__).resolve().parents[1] / "src" / "orchestration" / "run_sprint.py"


def _run_sprint_parts(*names: str) -> dict:
    """run_sprint 의 최상위 정의 몇 개만 AST 로 떼어 실행한다 — 모듈 전체(시뮬레이터 API 포함)를 import 하지 않는다."""
    import importlib as _importlib
    from typing import Any, Callable, Mapping

    tree = ast.parse(RUN_SPRINT.read_text(encoding="utf-8"))
    nodes = []
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.ClassDef)):
            defined = {node.name}
        elif isinstance(node, ast.Assign):
            defined = {t.id for t in node.targets if isinstance(t, ast.Name)}
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            defined = {node.target.id}
        else:
            continue
        if defined & set(names):
            nodes.append(node)
    namespace = {"Any": Any, "Callable": Callable, "Mapping": Mapping, "importlib": _importlib,
                 "timedelta": timedelta}
    exec(compile(ast.Module(body=nodes, type_ignores=[]), str(RUN_SPRINT), "exec"), namespace)
    missing = set(names) - set(namespace)
    if missing:
        raise AssertionError(f"run_sprint 에 없다: {sorted(missing)}")
    return namespace


@unittest.skipUnless(HAVE_PANDAS, SKIP_REASON)
class RunSprintRosterOrderTests(unittest.TestCase):
    """#319 리뷰 — 기존 시간 평가에 실제로 넘기는 고객과 과제 Test 후보가 겹치지 않는다."""

    def roster(self):
        from src.decision.split_roster import build_split_roster

        return build_split_roster(_events(), SIGNUPS, cohorts=_cohorts(), order_items=None, observation_complete=True)

    def test_temporal_holdout_scope_drops_official_test_candidates(self):
        scope_fn = _run_sprint_parts("temporal_holdout_scope")["temporal_holdout_scope"]
        roster, _, _ = self.roster()
        official_test = set(roster.loc[(roster["origin"] == "t2") & (roster["role"] == "test"), "customer_id"])
        self.assertEqual({"c", "f"}, official_test)
        labeled = ["a", "b", "c", "d", "e", "f"]               # S0 분기 라벨이 있는 Feature(t2) 고객
        eligible = {"a", "b", "c", "d", "f"}
        treated = {"b"}
        in_scope, scope = scope_fn(labeled, eligible, treated, roster)
        self.assertEqual(["a", "d"], in_scope)                 # = t2 future_existing
        self.assertEqual(set(), set(in_scope) & official_test)
        self.assertEqual({"official_test_known": True, "n_excluded_official_test": 2, "n_official_test_evaluated": 0},
                         {k: scope[k] for k in ("official_test_known", "n_excluded_official_test",
                                                "n_official_test_evaluated")})
        # 명부(t2 역할)가 없으면 뺄 후보를 모른다 — 평가는 하되 그 사실을 남긴다.
        in_scope, scope = scope_fn(labeled, eligible, treated, None)
        self.assertEqual(["a", "c", "d", "f"], in_scope)
        self.assertIs(False, scope["official_test_known"])

    def test_roster_is_built_before_any_t2_outcome_and_the_holdout_uses_its_scope(self):
        tree = ast.parse(RUN_SPRINT.read_text(encoding="utf-8"))

        def stage_line(fn, name):
            for node in ast.walk(fn):
                if (isinstance(node, ast.With) and isinstance(node.items[0].context_expr, ast.Call)
                        and node.items[0].context_expr.args
                        and isinstance(node.items[0].context_expr.args[0], ast.Constant)
                        and node.items[0].context_expr.args[0].value == name):
                    return node
            return None

        runner = next(fn for fn in tree.body if isinstance(fn, ast.FunctionDef)
                      and stage_line(fn, "churn_temporal_holdout") is not None)
        calls = {}
        for node in ast.walk(runner):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                calls.setdefault(node.func.id, []).append(node)
        prepare = min(n.lineno for n in calls["prepare_split_roster"])
        self.assertLess(stage_line(runner, "scores_t2").lineno, prepare)
        # t2 분기 결과(라벨) = 기준 시각 ctx["t2"] 로 만드는 결과. t1 라벨(ctx["t1"])은 명부 입력이라 앞서도 된다.
        t2_outcomes = [n.lineno for n in calls["build_outcomes"]
                       if any(ast.unparse(arg) == "ctx['t2']" for arg in n.args)]
        self.assertTrue(t2_outcomes)
        self.assertLess(prepare, min(t2_outcomes))
        holdout = stage_line(runner, "churn_temporal_holdout")
        self.assertLess(prepare, holdout.lineno)
        inside = {n.func.id for n in ast.walk(holdout) if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)}
        self.assertIn("temporal_holdout_scope", inside)

    def test_prepare_withholds_official_test_after_t2_outcomes_were_read(self):
        import pandas as pd

        parts = _run_sprint_parts("DECISION_API", "NotRun", "decision_fn", "LABEL_WINDOW_DAYS",
                                  "prepare_split_roster")
        y_prior = pd.Series([0, 1], index=pd.Index(["a", "b"], name="customer_id"))
        y_rct = pd.DataFrame({"churn": [0, 1, 0, None]}, index=pd.Index(["a", "b", "d", "e"], name="customer_id"))
        ctx = {
            "events_t2": _events(), "signups_t1": SIGNUPS, "t1": T1, "t2": T2,
            "churn_prior": {"status": "ok", "index_time": T_PRIOR, "label_window": {"start": T_PRIOR, "end": T1},
                            "y": y_prior, "tables": {"eligible": ["a", "b", "c"]}},
            "rct_assignment": dict(ARMS), "Y_rct": y_rct, "eligible_t2": ["a", "b", "c", "d", "f"],
            "event_read_evidence": {"t2": {"status": "ok", "verified_run_ids": ["run-1"]}},
        }
        before = parts["prepare_split_roster"](dict(ctx))
        self.assertEqual(("ok", "candidate"), (before["status"], before["official_test"]["status"]))
        after = parts["prepare_split_roster"]({**ctx, "t2_outcomes_read": "S0"})
        self.assertEqual("withheld", after["official_test"]["status"])
        self.assertIn("S0", after["official_test"]["reasons"][0])


def pd_isna(value) -> bool:
    import pandas as pd

    return bool(pd.isna(value))


if __name__ == "__main__":
    unittest.main()
