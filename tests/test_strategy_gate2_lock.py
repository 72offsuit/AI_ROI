"""GATE 2 Baseline Freeze 기록 · S1 일수 단위 (#170 · DR-170-gate2-lock).

- G1: S1 입력 ``days_since_last_purchase`` 가 Eligible 과 같은 KST 날짜 차다(run_sprint 는 AST 로 떼어 실행 — import 하지 않는다).
- G2: 봉인 대상 이름이 저장소에 모두 있고, 지문은 함수 본문 · 상수 값의 변경을 잡는다.
- G3 · G4: 임시 git 저장소에서 조건 하나라도 미충족이면 기록하지 않고, 사람이 아닌 서명 · 덮어쓰기를 거부하며, ``verify`` 가 변경을 잡는다.
"""

from __future__ import annotations

import ast
import json
import math
import shutil
import subprocess
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Mapping

from src.orchestration import gate2_lock as g

REPO_ROOT = Path(__file__).resolve().parent.parent
RUN_SPRINT = REPO_ROOT / "src" / "orchestration" / "run_sprint.py"
STRATEGIES = REPO_ROOT / "src" / "decision" / "strategies.py"
KST = timezone(timedelta(hours=9), "KST")

try:
    import pandas as pd  # noqa: F401
    HAVE_PANDAS = True
except ImportError:  # pragma: no cover
    HAVE_PANDAS = False

try:
    import yaml  # noqa: F401
    HAVE_YAML = True
except ImportError:  # pragma: no cover
    HAVE_YAML = False

HAVE_GIT = shutil.which("git") is not None


def _run_sprint_parts(*names: str) -> dict[str, Any]:
    """run_sprint 의 최상위 정의 몇 개만 AST 로 떼어 실행한다(시뮬레이터 API 를 import 하지 않는다)."""
    tree = ast.parse(RUN_SPRINT.read_text(encoding="utf-8"))
    nodes = []
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.ClassDef)):
            defined = {node.name}
        elif isinstance(node, ast.Assign):
            defined = {t.id for t in node.targets if isinstance(t, ast.Name)}
        else:
            continue
        if defined & set(names):
            nodes.append(node)
    namespace: dict[str, Any] = {"Any": Any, "Mapping": Mapping, "datetime": datetime, "timedelta": timedelta,
                                 "timezone": timezone}
    exec(compile(ast.Module(body=nodes, type_ignores=[]), str(RUN_SPRINT), "exec"), namespace)
    missing = set(names) - set(namespace)
    if missing:
        raise AssertionError(f"run_sprint 에 없다: {sorted(missing)}")
    return namespace


@unittest.skipUnless(HAVE_PANDAS, "pandas 없음")
class S1DaysUnitTests(unittest.TestCase):
    """G1 — 하한 쪽 하루(t2 − 28일 날짜의 구매)가 더는 빠지지 않는다. 상한 쪽은 그대로다."""

    def setUp(self) -> None:
        self.rs = _run_sprint_parts("KST", "NotRun", "_pd", "_timestamps", "_kst_dates", "s1_inputs",
                                    "S1_DAYS_DEFINITION")

    def _inputs(self, t2: datetime, purchases: dict[str, datetime]):
        import pandas as pd

        events = pd.DataFrame([{"customer_id": cid, "timestamp": ts, "event_type": "purchase", "order_id": f"O-{cid}",
                                "event_id": f"E-{cid}"} for cid, ts in purchases.items()])
        population = pd.Index(sorted(purchases) + ["NONE"], name="customer_id")
        flags = pd.Series(True, index=population)
        return self.rs["s1_inputs"](events, t2, population, flags)["days_since_last_purchase"]

    def test_days_are_kst_date_differences(self) -> None:
        t2 = datetime(2026, 3, 1, tzinfo=KST)
        days = self._inputs(t2, {
            "D28": datetime(2026, 2, 1, 15, 0, tzinfo=KST),   # t2 − 28일 날짜 오후 — 시각 차로는 27.375
            "D90": datetime(2025, 12, 1, 10, 0, tzinfo=KST),  # t2 − 90일 날짜
            "D91": datetime(2025, 11, 30, 23, 0, tzinfo=KST),  # t2 − 91일 날짜 밤 — 시각 차로는 90.04
        })
        self.assertEqual(28.0, days["D28"])
        self.assertEqual(90.0, days["D90"])
        self.assertEqual(91.0, days["D91"])
        self.assertTrue(math.isnan(days["NONE"]))  # 주문 없음 — 0 이 아니다

    def test_s1_rule_picks_the_boundary_dates(self) -> None:
        from src.decision.strategies import plan_S1

        t2 = datetime(2026, 3, 1, tzinfo=KST)
        days = self._inputs(t2, {"D28": datetime(2026, 2, 1, 15, 0, tzinfo=KST),
                                 "D90": datetime(2025, 12, 1, 10, 0, tzinfo=KST),
                                 "D91": datetime(2025, 11, 30, 23, 0, tzinfo=KST)})
        self.assertEqual({"D90": "T3", "D28": "T3"}, plan_S1({"days_since_last_purchase": days.dropna()}))

    def test_utc_timestamps_use_the_kst_date(self) -> None:
        t2 = datetime(2026, 3, 1, tzinfo=KST)
        # UTC 2026-01-31 16:00 = KST 2026-02-01 01:00 → t2 − 28일 날짜
        days = self._inputs(t2, {"U": datetime(2026, 1, 31, 16, 0, tzinfo=timezone.utc)})
        self.assertEqual(28.0, days["U"])

    def test_definition_is_recorded(self) -> None:
        self.assertIn("날짜", self.rs["S1_DAYS_DEFINITION"])
        source = RUN_SPRINT.read_text(encoding="utf-8")
        self.assertIn('"days_definition": S1_DAYS_DEFINITION', source)


class LockedNameTests(unittest.TestCase):
    """G2 — 봉인 대상이 저장소에 모두 있고, 지문이 바뀌어야 할 때만 바뀐다."""

    def test_every_locked_name_resolves(self) -> None:
        rows = g.fingerprints(g.worktree_reader(REPO_ROOT))
        self.assertEqual(len(g.LOCKED_NAMES), len(rows))
        self.assertEqual([], [(r["name"], r.get("reason")) for r in rows if r["sha256"] is None])

    def test_s2_to_s6_are_not_locked(self) -> None:
        names = {item.name for item in g.LOCKED_NAMES}
        for planner in ("plan", "plan_S2", "plan_S3", "plan_S4", "plan_S5", "plan_S6", "_fill"):
            self.assertNotIn(planner, names)  # GATE 3 에서 바꿀 수 있다(PRD §84)

    def test_function_fingerprint_follows_the_text(self) -> None:
        item = g.LockedName("baseline_rule", "x.py", "f")
        one = g.fingerprint("def f(x):\n    return x + 1\n", item)
        self.assertEqual("source", one["kind"])
        self.assertEqual(one, g.fingerprint("# 주석\n\ndef f(x):\n    return x + 1\n", item))  # 바깥 주석은 무관
        self.assertNotEqual(one, g.fingerprint("def f(x):\n    return x + 2\n", item))
        self.assertNotEqual(one, g.fingerprint('def f(x):\n    """문서."""\n    return x + 1\n', item))

    def test_literal_fingerprint_follows_the_value(self) -> None:
        item = g.LockedName("baseline_rule", "x.py", "RULE")
        one = g.fingerprint("RULE = {'a': 1, 'b': (2, 3)}\n", item)
        self.assertEqual("value", one["kind"])
        self.assertEqual(one, g.fingerprint("RULE = {\n    'b': (2, 3),  # 순서 · 주석\n    'a': 1,\n}\n", item))
        self.assertNotEqual(one, g.fingerprint("RULE = {'a': 1, 'b': (2, 4)}\n", item))

    def test_keyed_fingerprint_ignores_other_entries(self) -> None:
        item = g.LockedName("baseline_rule", "x.py", "REQUIRED", "S1")
        one = g.fingerprint("REQUIRED = {'S1': ('days',), 'S2': ('churn',)}\n", item)
        self.assertEqual(one, g.fingerprint("REQUIRED = {'S1': ('days',), 'S2': ('cate',)}\n", item))
        self.assertNotEqual(one, g.fingerprint("REQUIRED = {'S1': ('days', 'x'), 'S2': ('churn',)}\n", item))
        with self.assertRaises(LookupError):
            g.fingerprint("REQUIRED = {'S2': ()}\n", item)

    def test_missing_name_is_reported_not_hashed(self) -> None:
        rows = g.fingerprints(lambda relative: "x = 1\n")
        self.assertTrue(all(r["sha256"] is None and r["reason"] for r in rows))

    def test_record_is_lead_only(self) -> None:
        data = json.loads((REPO_ROOT / "docs" / "team_boundaries.json").read_text(encoding="utf-8"))
        self.assertIn(g.LOCK_RECORD.as_posix(), data["lead_only"]["paths"])

    def test_c_rule_source_marker_matches_resolve_budget(self) -> None:
        """B-8 은 ``budget.source`` 가 'C_rule' 로 시작하는지로 명시 예산과 가른다 — 두 모듈의 계약."""
        rs = _run_sprint_parts("C_RULE_DEFINITION", "resolve_budget")
        planned = rs["resolve_budget"](None, {"planned_cost_krw": 7030.0}, None)
        explicit = rs["resolve_budget"](5000, {"planned_cost_krw": 7030.0}, None)
        self.assertTrue(planned["source"].startswith("C_rule"))
        self.assertFalse(explicit["source"].startswith("C_rule"))

    def test_rule_code_still_matches_the_pre_ai_tag(self) -> None:
        """DR-145 · #170 10/22 — 규칙 코드는 태그 gate2-s1-rule(ce05a66)과 같다. 태그를 받지 않은 체크아웃이면 건너뛴다."""
        if not HAVE_GIT or g.resolve_commit(REPO_ROOT, g.S1_RULE_TAG) is None:
            self.skipTest("태그 gate2-s1-rule 이 이 체크아웃에 없다")
        rows = [r for r in g.fingerprints(g.worktree_reader(REPO_ROOT)) if r["group"] == "baseline_rule"]
        names = g.tag_comparison(REPO_ROOT, rows)["names"]
        for name in ("S1_RULE", "plan_S0", "s1_eligibility", "plan_S1"):
            self.assertEqual("same", names[name], name)


def _git(root: Path, *args: str) -> str:
    done = subprocess.run(["git", "-C", str(root), "-c", "user.name=gate2-test",
                           "-c", "user.email=gate2-test@example.invalid", *args],
                          check=True, capture_output=True, text=True)
    return done.stdout.strip()


GATE1_FULL_TEXT = "declaration: FULL_FREEZE\nlocked_at: '2026-11-26T10:00:00.000+09:00'\nlocked_by: tester\n"


@unittest.skipUnless(HAVE_GIT and HAVE_YAML, "git 또는 PyYAML 없음")
class RecordTests(unittest.TestCase):
    """G3 · G4 — 임시 저장소(실제 strategies.py · run_sprint.py 사본)와 가짜 결과 폴더."""

    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.root = self.tmp / "repo"
        for source, target in ((STRATEGIES, "src/decision/strategies.py"), (RUN_SPRINT, "src/orchestration/run_sprint.py")):
            (self.root / target).parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, self.root / target)
        (self.root / "config").mkdir()
        (self.root / "config" / "gate1_lock.yaml").write_text(GATE1_FULL_TEXT, encoding="utf-8")
        _git(self.root, "init", "-q")
        _git(self.root, "add", ".")
        _git(self.root, "commit", "-q", "-m", "base")
        _git(self.root, "tag", g.S1_RULE_TAG)
        self.commit = _git(self.root, "rev-parse", "HEAD")
        self.run_dir = self.tmp / "run"
        self.run_dir.mkdir()
        self.write_run()

    def write_run(self, *, arms: Mapping[str, int] | None = None, provenance: Mapping[str, Any] | None = None,
                  s1_status: str = "ok", budget: Mapping[str, Any] | None = None,
                  invariance: str | None = "same") -> None:
        meta = {
            "run_id": "gate2-test", "num_customers": 50_000, "profile": "reference",
            "versions": {"customer_seed": 42},
            "timeline": {"t2": "2026-03-01T00:00:00+09:00", "end": "2026-04-12T00:00:00+09:00"},
            "provenance": {"repo_commit": self.commit, "repo_worktree_dirty": False, "require_clean": True,
                           "repo_changed_during_run": False, "simulator_commit": "f" * 40, **(provenance or {})},
            "rct": {"arm_counts": dict(arms or {"T0": 12_000, "T1": 3_000, "T2": 3_000, "T3": 3_000, "T4": 3_000})},
            "stages": [{"name": "strategy_S0", "status": "ok"}, {"name": "strategy_S1", "status": "failed"},
                       {"name": "strategy_S1", "status": s1_status}],
            "budget": dict(budget or {"status": "ok", "c_rule_planned_krw": 28_823_000.0,
                                      "planning_budget_krw": 28_823_000.0, "c_rule_definition": "C_rule = ...",
                                      "source": "C_rule = S1(상한 없음) 배정의 계획 비용 합"}),
            "planning_costs_krw": {"T0": 0.0, "T3": 7_030.0},
        }
        comparison = {"strategy_details": {
            "S0": {"n_assigned": 0, "n_targeted": 0, "treatment_counts": {}, "planned_cost_krw": 0.0},
            "S1": {"n_assigned": 4_100, "n_targeted": 4_100, "treatment_counts": {"T3": 4_100},
                   "planned_cost_krw": 28_823_000.0,
                   "measured_economics": {"status": "ok", "metrics": {
                       "revenue": {"status": "ok", "value": 1_000.0},
                       "contribution_profit": {"status": "not_computable", "value": None}}}},
        }}
        (self.run_dir / "run_meta.json").write_text(json.dumps(meta), encoding="utf-8")
        (self.run_dir / "strategy_comparison.json").write_text(json.dumps(comparison), encoding="utf-8")
        target = self.run_dir / "branch_invariance.json"
        if invariance is None:
            target.unlink(missing_ok=True)
        else:
            target.write_text(json.dumps({"status": "ok", "result": invariance, "branches": ["S0", "S1"],
                                          "groups": {"non_eligible": {"n_customers": 10, "by_branch": {
                                              "S0": {"n_differing_vs_reference": 0},
                                              "S1": {"n_differing_vs_reference": 0 if invariance == "same" else 1}}}}}),
                              encoding="utf-8")

    def unmet(self) -> dict[str, bool | None]:
        return {c.id: c.met for c in g.collect(self.run_dir, self.commit, self.root)["checks"] if c.met is not True}

    def record(self, name: str = "광진") -> dict[str, Any]:
        return g.record(self.run_dir, expected=self.commit, locked_by=name, root=self.root,
                        now=datetime(2026, 11, 28, 10, 0, tzinfo=KST))

    def test_all_conditions_met_writes_and_verifies(self) -> None:
        self.assertEqual({}, self.unmet())
        payload = self.record()
        self.assertEqual("광진", payload["locked_by"])
        self.assertEqual(28_823_000.0, payload["budget_cap"]["c_rule_krw"])
        self.assertEqual(4_100, payload["baseline_results"]["S1"]["n_assigned"])
        self.assertEqual({"revenue": 1_000.0, "contribution_profit": None},
                         payload["baseline_results"]["S1"]["measured_economics"]["values"])
        self.assertEqual("same", payload["baseline_rule"]["tag"]["names"]["plan_S1"])
        self.assertEqual("run", payload["run"]["results_dir_name"])  # 절대 경로를 남기지 않는다
        self.assertTrue((self.root / g.LOCK_RECORD).exists())
        self.assertEqual("match", g.verify(self.root)["status"])

    def test_verify_catches_a_changed_rule(self) -> None:
        self.record()
        path = self.root / "src" / "decision" / "strategies.py"
        path.write_text(path.read_text(encoding="utf-8").replace('"min_lifetime_order_count": 2',
                                                                  '"min_lifetime_order_count": 3'), encoding="utf-8")
        result = g.verify(self.root)
        self.assertEqual("mismatch", result["status"])
        self.assertEqual(["S1_RULE"], result["mismatched"])

    def test_verify_without_record_is_not_started(self) -> None:
        self.assertEqual("not_started", g.verify(self.root)["status"])

    def test_refuses_agents_and_blank_names(self) -> None:
        for name in ("agent", " Claude ", "", "codex"):
            with self.subTest(name=name), self.assertRaises(g.Gate2LockViolation):
                self.record(name)
        self.assertFalse((self.root / g.LOCK_RECORD).exists())

    def test_refuses_to_overwrite_a_seal(self) -> None:
        self.record()
        with self.assertRaises(g.Gate2LockViolation):
            self.record()

    def _refused(self, check_id: str, expected: bool | None) -> None:
        self.assertEqual(expected, self.unmet().get(check_id, True), self.unmet())
        with self.assertRaises(g.Gate2LockViolation):
            self.record()
        self.assertFalse((self.root / g.LOCK_RECORD).exists())

    def test_b1_partial_gate1_is_refused(self) -> None:
        (self.root / "config" / "gate1_lock.yaml").write_text(
            GATE1_FULL_TEXT.replace("FULL_FREEZE", "PARTIAL_FREEZE"), encoding="utf-8")
        _git(self.root, "commit", "-q", "-am", "partial")
        self.commit = _git(self.root, "rev-parse", "HEAD")
        self.write_run()
        self._refused("B-1", False)

    def test_b2_other_commit_is_refused(self) -> None:
        (self.root / "README.md").write_text("x\n", encoding="utf-8")
        _git(self.root, "add", "README.md")
        _git(self.root, "commit", "-q", "-m", "later")
        checks = {c.id: c.met for c in g.collect(self.run_dir, "HEAD", self.root)["checks"]}
        self.assertIs(False, checks["B-2"])  # 실행 커밋(base) ≠ 지정한 커밋(later)
        checks = {c.id: c.met for c in g.collect(self.run_dir, "no-such-ref", self.root)["checks"]}
        self.assertIsNone(checks["B-2"])  # 지정한 커밋을 찾지 못하면 확인하지 못한 것이다

    def test_b3_to_b5_provenance(self) -> None:
        for patch, check_id in (({"require_clean": False}, "B-3"), ({"repo_worktree_dirty": True}, "B-3"),
                                ({"repo_changed_during_run": True}, "B-4"), ({"null_reason": "git 실패"}, "B-5")):
            with self.subTest(patch=patch):
                self.write_run(provenance=patch)
                self._refused(check_id, False)

    def test_b6_scale_below_fr05(self) -> None:
        self.write_run(arms={"T0": 9_999, "T1": 3_000, "T2": 3_000, "T3": 3_000, "T4": 3_000})
        self._refused("B-6", False)

    def test_b7_latest_s1_status_counts(self) -> None:
        self.write_run(s1_status="not_run")
        self._refused("B-7", False)

    def test_b8_explicit_budget_is_not_c_rule(self) -> None:
        self.write_run(budget={"status": "ok", "c_rule_planned_krw": None, "planning_budget_krw": 5_000.0,
                               "source": "--budget-krw 인자 — 탐색용"})
        self._refused("B-8", False)

    def test_b9_missing_or_differing_invariance(self) -> None:
        self.write_run(invariance=None)
        self._refused("B-9", None)
        self.write_run(invariance="differs")
        self._refused("B-9", False)

    def test_b10_worktree_differs_from_the_run_commit(self) -> None:
        path = self.root / "src" / "orchestration" / "run_sprint.py"
        path.write_text(path.read_text(encoding="utf-8").replace("ELIGIBLE_MIN_TENURE_DAYS = 60",
                                                                  "ELIGIBLE_MIN_TENURE_DAYS = 30"), encoding="utf-8")
        self._refused("B-10", False)

    def test_check_command_does_not_write(self) -> None:
        collected = g.collect(self.run_dir, self.commit, self.root)
        preview = g.build_record(collected, locked_by=None, now=None)
        self.assertIsNone(preview["locked_by"])
        self.assertIsNone(preview["locked_at"])
        self.assertFalse((self.root / g.LOCK_RECORD).exists())


if __name__ == "__main__":
    unittest.main()
