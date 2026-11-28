"""GATE 2 Baseline Freeze 기록 · S1 일수 단위 (#170 · DR-170-gate2-lock).

- G1: S1 입력 ``days_since_last_purchase`` 가 Eligible 과 같은 KST 날짜 차다(run_sprint 는 AST 로 떼어 실행 — import 하지 않는다).
- G2: 봉인 대상 이름이 저장소에 모두 있고, 지문은 함수 본문 · 상수 값의 변경을 잡는다.
- G3 · G4: 임시 git 저장소에서 조건 하나라도 미충족이면 기록하지 않고, 사람이 아닌 서명 · 덮어쓰기를 거부하며, ``verify`` 가 변경을 잡는다.
"""

from __future__ import annotations

import ast
import contextlib
import hashlib
import io
import json
import math
import shutil
import subprocess
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Mapping
from unittest import mock

from src.orchestration import branch_invariance as bi
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

    def test_required_measured_keys_are_run_sprint_measured_keys(self) -> None:
        """B-7 이 요구하는 실측 지표 = 실행 루프가 비교에 ``measured_<이름>`` 으로 넘기는 지표(``run_sprint.MEASURED_KEYS``)."""
        tree = ast.parse(RUN_SPRINT.read_text(encoding="utf-8"))
        values = [ast.literal_eval(node.value) for node in tree.body if isinstance(node, ast.AnnAssign)
                  and isinstance(node.target, ast.Name) and node.target.id == "MEASURED_KEYS"]
        self.assertEqual([g.REQUIRED_MEASURED], values)

    def test_run_uses_the_locked_planned_cost_function(self) -> None:
        """C_rule 합산식이 지문 밖 run() 본문에 남지 않는다 — 잠근 함수를 부른다."""
        rs = _run_sprint_parts("assignment_planned_cost")
        self.assertEqual(7_030.0 * 2 + 500.0, rs["assignment_planned_cost"]({"T3": 2, "T1": 1, "T9": 4},
                                                                           {"T3": 7_030.0, "T1": 500.0}))
        tree = ast.parse(RUN_SPRINT.read_text(encoding="utf-8"))
        run = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "run")
        calls = [ast.unparse(n) for n in ast.walk(run) if isinstance(n, ast.Call)]
        self.assertIn("assignment_planned_cost(counts, costs)", calls)
        self.assertNotIn("costs.get(t, 0) * n", ast.unparse(run))
        self.assertIn("assignment_planned_cost", {item.name for item in g.LOCKED_NAMES if item.group == "budget_cap"})

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


SIMULATOR_COMMIT = "f" * 40
ECONOMIC_TEXT = "cost_accounting:\n  message_cost_krw: 30\n"
ECONOMIC_FILE = "config/economic_config.yaml"
#: 합성 정본 두 번째 — LOCKED 항목이 정본 둘을 가리키는 반례(PR #327 2차 리뷰)에 쓴다.
SECOND_TEXT = "metrics:\n  - revenue\n"
SECOND_FILE = "config/second_canonical.yaml"
TEXTS = {ECONOMIC_FILE: ECONOMIC_TEXT, SECOND_FILE: SECOND_TEXT}


def gate1_text(declaration: str = "FULL_FREEZE", simulator_commit: str | None = SIMULATOR_COMMIT, *,
               locked: tuple[str, ...] = (ECONOMIC_FILE,), hashed: tuple[str, ...] = (ECONOMIC_FILE,),
               items: str | None = None) -> str:
    """합성 GATE 1 기록 — LOCKED 항목 하나(경제 규칙 자리)가 가리키는 정본(``locked``) · 해시를 적은 정본(``hashed``) ·
    simulator_commit. ``items`` 를 주면 항목 목록을 그 YAML 조각으로 바꾼다."""
    sim = "null" if simulator_commit is None else simulator_commit
    if items is None:
        items = ("items:\n- item: ECONOMIC_RULE_v1\n  status: LOCKED\n  owner_part: measurement\n"
                 "  scope_note: 합성\n  canonical_files:\n" + "".join(f"  - {path}\n" for path in locked))
    hashes = "".join(f"  {path}: {hashlib.sha256(TEXTS[path].encode('utf-8')).hexdigest()}\n" for path in hashed)
    return (f"declaration: {declaration}\nlocked_at: '2026-11-26T10:00:00.000+09:00'\nlocked_by: tester\n"
            f"simulator_commit: {sim}\n{items}canonical_files:\n{hashes}")


def measured(revenue: Any = 1_000.0, marketing: Any = 300.0, profit: Any = 200.0, *,
             status: str = "ok") -> dict[str, Any]:
    """분기 상세의 실측 경제 지표 — ``branch_economics`` 가 남기는 모양(값이 None 이면 not_computable)."""
    def metric(value: Any) -> dict[str, Any]:
        return {"status": "ok", "value": value} if value is not None else {"status": "unavailable", "value": None}
    return {"status": status, "metrics": {"revenue": metric(revenue), "marketing_cost": metric(marketing),
                                          "contribution_profit": metric(profit),
                                          "cogs": {"status": "not_computable", "value": None}}}


OBSERVED = {"economics_input_observation": {"status": "ok", "reason": None}}


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
        (self.root / "config" / "gate1_lock.yaml").write_text(gate1_text(), encoding="utf-8")
        (self.root / "config" / "economic_config.yaml").write_text(ECONOMIC_TEXT, encoding="utf-8")
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
                  invariance: str | None = "same", comparison_run_id: str = "gate2-test",
                  invariance_extra: Mapping[str, Any] | None = None, with_comparison: bool = True,
                  s1_detail: Mapping[str, Any] | None = None, s0_detail: Mapping[str, Any] | None = None) -> None:
        meta = {
            "run_id": "gate2-test", "num_customers": 50_000, "profile": "reference",
            "versions": {"customer_seed": 42},
            "timeline": {"t2": "2026-03-01T00:00:00+09:00", "end": "2026-04-12T00:00:00+09:00"},
            "provenance": {"repo_commit": self.commit, "repo_worktree_dirty": False, "require_clean": True,
                           "repo_changed_during_run": False, "simulator_commit": SIMULATOR_COMMIT,
                           **(provenance or {})},
            "rct": {"arm_counts": dict(arms or {"T0": 12_000, "T1": 3_000, "T2": 3_000, "T3": 3_000, "T4": 3_000})},
            "stages": [{"name": "strategy_S0", "status": "ok"}, {"name": "strategy_S1", "status": "failed"},
                       {"name": "strategy_S1", "status": s1_status}],
            "budget": dict(budget or {"status": "ok", "c_rule_planned_krw": 28_823_000.0,
                                      "planning_budget_krw": 28_823_000.0, "c_rule_definition": "C_rule = ...",
                                      "source": "C_rule = S1(상한 없음) 배정의 계획 비용 합"}),
            "planning_costs_krw": {"T0": 0.0, "T3": 7_030.0},
        }
        comparison = {"run_id": comparison_run_id, "strategy_details": {
            "S0": {"n_assigned": 0, "n_targeted": 0, "treatment_counts": {}, "planned_cost_krw": 0.0,
                   "measured_economics": measured(900.0, 0.0, 250.0), **OBSERVED, **(s0_detail or {})},
            "S1": {"n_assigned": 4_100, "n_targeted": 4_100, "treatment_counts": {"T3": 4_100},
                   "planned_cost_krw": 28_823_000.0, "measured_economics": measured(), **OBSERVED,
                   **(s1_detail or {})},
        }}
        (self.run_dir / "run_meta.json").write_text(json.dumps(meta), encoding="utf-8")
        target_comparison = self.run_dir / "strategy_comparison.json"
        if with_comparison:
            target_comparison.write_text(json.dumps(comparison), encoding="utf-8")
        else:
            target_comparison.unlink(missing_ok=True)
        target = self.run_dir / "branch_invariance.json"
        if invariance is None:
            target.unlink(missing_ok=True)
        else:
            target.write_text(json.dumps({
                "status": "ok", "result": invariance, "complete": True, "run_id": "gate2-test",
                "branches": list(bi.REQUIRED_BRANCHES), "missing_branches": {},
                "groups": {"non_eligible": {"n_customers": 10, "by_branch": {
                    "S0": {"n_differing_vs_reference": 0},
                    "S1": {"n_differing_vs_reference": 0 if invariance == "same" else 1}}}},
                **(invariance_extra or {})}), encoding="utf-8")

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
        self.assertEqual({"revenue": 1_000.0, "marketing_cost": 300.0, "contribution_profit": 200.0, "cogs": None},
                         payload["baseline_results"]["S1"]["measured_economics"]["values"])
        self.assertEqual("ok", payload["baseline_results"]["S0"]["measured_economics"]["input_observation"])
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

    def _commit(self, message: str) -> None:
        _git(self.root, "commit", "-q", "-am", message)
        self.commit = _git(self.root, "rev-parse", "HEAD")
        self.write_run()

    def test_b1_partial_gate1_is_refused(self) -> None:
        (self.root / "config" / "gate1_lock.yaml").write_text(gate1_text("PARTIAL_FREEZE"), encoding="utf-8")
        self._commit("partial")
        self._refused("B-1", False)

    def test_b1_simulator_commit_must_be_the_sealed_one(self) -> None:
        """#213 — Baseline 이 GATE 1 봉인 환경(simulator_commit)에서 나왔는가."""
        self.write_run(provenance={"simulator_commit": "e" * 40})
        self._refused("B-1", False)
        self.write_run(provenance={"simulator_commit": None})
        self._refused("B-1", False)

    def test_b1_gate1_record_without_simulator_commit(self) -> None:
        (self.root / "config" / "gate1_lock.yaml").write_text(gate1_text(simulator_commit=None), encoding="utf-8")
        self._commit("no simulator commit")
        self._refused("B-1", False)

    def test_b1_canonical_file_changed_after_the_gate1_record(self) -> None:
        """PR #327 리뷰 반례 — GATE 1 기록은 두고 기록에 든 경제 설정만 바꾼 커밋에서 실행하면 B-1 이 통과했다."""
        (self.root / "config" / "economic_config.yaml").write_text(ECONOMIC_TEXT.replace("30", "40"), encoding="utf-8")
        self._commit("economic change")
        self._refused("B-1", False)
        evidence = next(c.evidence for c in g.collect(self.run_dir, self.commit, self.root)["checks"] if c.id == "B-1")
        self.assertIn("config/economic_config.yaml", evidence)

    def _gate1(self, text: str, message: str) -> None:
        (self.root / "config" / "gate1_lock.yaml").write_text(text, encoding="utf-8")
        (self.root / SECOND_FILE).write_text(SECOND_TEXT, encoding="utf-8")
        _git(self.root, "add", ".")
        self._commit(message)

    def _b1_evidence(self) -> str:
        return next(c.evidence for c in g.collect(self.run_dir, self.commit, self.root)["checks"] if c.id == "B-1")

    def test_b1_locked_canonical_without_a_recorded_hash(self) -> None:
        """PR #327 2차 리뷰 반례 — LOCKED 항목의 정본 두 개 중 경제 설정의 해시만 기록에서 빠져도 B-1 이 통과했다
        (GATE 1 ``freeze.verify`` 는 같은 기록을 mismatch 로 본다)."""
        self._gate1(gate1_text(locked=(ECONOMIC_FILE, SECOND_FILE), hashed=(ECONOMIC_FILE, SECOND_FILE)), "both")
        self.assertEqual({}, self.unmet())
        self._gate1(gate1_text(locked=(ECONOMIC_FILE, SECOND_FILE), hashed=(SECOND_FILE,)), "one hash missing")
        self._refused("B-1", False)
        evidence = self._b1_evidence()
        self.assertIn(f"기록에 해시가 없는 정본 ['{ECONOMIC_FILE}']", evidence)
        self.assertIn("ECONOMIC_RULE_v1", evidence)

    def test_b1_gate1_items_must_name_locked_canonicals(self) -> None:
        """항목 목록이 없거나 LOCKED 정본이 하나도 없으면 무엇을 봉인했는지 대조할 수 없다 — 해시만 맞아도 통과하지 않는다."""
        for items, needle in (("", "items 가 목록이 아니다"),
                              ("items:\n- item: ECONOMIC_RULE_v1\n  status: PARTIAL\n", "LOCKED 항목이 가리키는 정본이 없다"),
                              ("items:\n- status: LOCKED\n", "item · status 가 없다")):
            with self.subTest(items=items):
                self._gate1(gate1_text(items=items), f"items {needle}")
                self._refused("B-1", False)
                self.assertIn(needle, self._b1_evidence())

    def test_b1_each_locked_item_needs_its_own_canonical_list(self) -> None:
        """PR #327 3차 리뷰 반례 — LOCKED 항목 하나의 정본 목록만 빼고 다른 항목의 정본 해시를 맞게 남기면 B-1 이 통과했다
        (``canonical_files or ()`` 가 그 항목을 조용히 건너뛰었다). GATE 1 공용 ``LockItem`` 은 LOCKED 에 비어 있지 않은
        정본 목록을 요구한다."""
        head = ("items:\n- item: ECONOMIC_RULE_v1\n  status: LOCKED\n  owner_part: measurement\n  scope_note: 합성\n"
                f"  canonical_files:\n  - {ECONOMIC_FILE}\n"
                "- item: KPI_DEFINITION_v1\n  status: LOCKED\n  owner_part: measurement\n  scope_note: 합성\n")
        hashed = (ECONOMIC_FILE, SECOND_FILE)
        self._gate1(gate1_text(hashed=hashed, items=head + f"  canonical_files:\n  - {SECOND_FILE}\n"), "both listed")
        self.assertEqual({}, self.unmet())                                    # 대조군 — 두 항목 모두 목록이 있다
        cases = {"목록 없음": ("", "canonical_files 가 비었다"),
                 "빈 목록": ("  canonical_files: []\n", "canonical_files 가 비었다"),
                 "문자열": (f"  canonical_files: {SECOND_FILE}\n", "경로 목록이 아니다"),
                 "숫자 원소": ("  canonical_files:\n  - 123\n", "경로 문자열이 아닌 값"),
                 "범위 문장 없음": (f"  canonical_files:\n  - {SECOND_FILE}\n", "scope_note 가 비었다")}
        for label, (tail, needle) in cases.items():
            with self.subTest(label=label):
                items = head + tail
                if label == "범위 문장 없음":
                    items = items.replace("KPI_DEFINITION_v1\n  status: LOCKED\n  owner_part: measurement\n  scope_note: 합성\n",
                                          "KPI_DEFINITION_v1\n  status: LOCKED\n  owner_part: measurement\n")
                self._gate1(gate1_text(hashed=hashed, items=items), f"b1 {label}")
                self._refused("B-1", False)
                evidence = self._b1_evidence()
                self.assertIn("KPI_DEFINITION_v1", evidence)
                self.assertIn(needle, evidence)
                with mock.patch.object(g, "REPO_ROOT", self.root), contextlib.redirect_stdout(io.StringIO()):
                    self.assertEqual(1, g.main(["check", str(self.run_dir), "--expected-commit", self.commit]))

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

    def test_b7_missing_result_file_fails_check_command(self) -> None:
        """PR #327 리뷰 반례 — strategy_comparison.json 이 없어도 check 가 0 을 냈다."""
        out = io.StringIO()
        with mock.patch.object(g, "REPO_ROOT", self.root), contextlib.redirect_stdout(out):
            self.assertEqual(0, g.main(["check", str(self.run_dir), "--expected-commit", self.commit]))
        self.write_run(with_comparison=False)
        self._refused("B-7", False)
        with mock.patch.object(g, "REPO_ROOT", self.root), contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(1, g.main(["check", str(self.run_dir), "--expected-commit", self.commit]))

    def test_b7_baseline_without_measured_economics(self) -> None:
        """PR #327 2차 리뷰 반례 — 교환 묶음을 못 받아 ``branch_economics`` 가 not_run 이고 S1 실측 값이 ``{}`` 여도
        check 가 0 이었다. 봉인 대상(DR-170 G2 3)에 실측 경제 지표가 있으니 비면 거부한다."""
        cases = {
            "not_run": {"measured_economics": {"status": "not_run", "reason": "sim.exchange_bundle 상태 'missing'"}},
            "값이 빔": {"measured_economics": {"status": "ok", "metrics": {}}},
            "DQ 실패": {"measured_economics": measured(status="quality_failed")},
            "기여이익 없음": {"measured_economics": measured(profit=None)},
            "관측 근거 미충족": {"economics_input_observation": {"status": "not_run", "reason": "read_complete"}},
        }
        for label, detail in cases.items():
            with self.subTest(label=label):
                self.write_run(s1_detail=detail)
                self._refused("B-7", False)
                evidence = next(c.evidence for c in g.collect(self.run_dir, self.commit, self.root)["checks"]
                                if c.id == "B-7")
                self.assertIn("S1 실측 경제 지표", evidence)
                with mock.patch.object(g, "REPO_ROOT", self.root), contextlib.redirect_stdout(io.StringIO()):
                    self.assertEqual(1, g.main(["check", str(self.run_dir), "--expected-commit", self.commit]))
        self.write_run(s0_detail={"measured_economics": measured(marketing=None)})   # 기준 S0 도 같다
        self._refused("B-7", False)

    def test_b7_result_file_from_another_run(self) -> None:
        self.write_run(comparison_run_id="SP-other")
        self._refused("B-7", False)

    def test_b8_explicit_budget_is_not_c_rule(self) -> None:
        self.write_run(budget={"status": "ok", "c_rule_planned_krw": None, "planning_budget_krw": 5_000.0,
                               "source": "--budget-krw 인자 — 탐색용"})
        self._refused("B-8", False)

    def test_b8_s1_cost_in_the_result_file_must_equal_c_rule(self) -> None:
        """PR #327 리뷰 반례 — 결과 파일의 S1 계획 비용만 바꿔도 B-8 이 통과했다."""
        self.write_run(s1_detail={"planned_cost_krw": 28_823_001.0})
        self._refused("B-8", False)
        self.write_run(s1_detail={"treatment_counts": {"T3": 4_101}})      # 배정 수 × 단가가 C_rule 과 다르다
        self._refused("B-8", False)

    def test_b9_missing_or_differing_invariance(self) -> None:
        self.write_run(invariance=None)
        self._refused("B-9", None)
        self.write_run(invariance="differs")
        self._refused("B-9", False)

    def test_b9_requires_every_branch_and_the_same_run(self) -> None:
        """PR #327 리뷰 반례 — 분기 원본이 빠지면 있는 분기만으로 same 이 됐다."""
        self.write_run(invariance_extra={"status": "incomplete", "result": None, "complete": False,
                                         "missing_branches": {"S2": "분기 원본이 없다"}})
        self._refused("B-9", False)
        # PR #327 3차 리뷰 — 분기 원본 내용이 실행 당시와 다르면(incomplete) check 도 실패로 끝난다
        self.write_run(invariance_extra={"status": "incomplete", "result": None, "complete": False,
                                         "missing_branches": {"S2": "분기 원본 내용이 실행 당시와 다르다"}})
        with mock.patch.object(g, "REPO_ROOT", self.root), contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(1, g.main(["check", str(self.run_dir), "--expected-commit", self.commit]))
        self.write_run(invariance_extra={"branches": ["S0", "S1", "S3", "S4", "S5"]})
        self._refused("B-9", False)
        self.write_run(invariance_extra={"run_id": "SP-other"})
        self._refused("B-9", False)

    def test_b10_worktree_differs_from_the_run_commit(self) -> None:
        path = self.root / "src" / "orchestration" / "run_sprint.py"
        path.write_text(path.read_text(encoding="utf-8").replace("ELIGIBLE_MIN_TENURE_DAYS = 60",
                                                                  "ELIGIBLE_MIN_TENURE_DAYS = 30"), encoding="utf-8")
        self._refused("B-10", False)

    def test_planned_cost_summation_is_locked(self) -> None:
        """PR #327 리뷰 반례 — run() 안 합산식만 바꿔 C_rule 이 달라져도 verify 가 match 였다."""
        self.record()
        path = self.root / "src" / "orchestration" / "run_sprint.py"
        text = path.read_text(encoding="utf-8")
        old = "return sum(costs.get(t, 0) * n for t, n in counts.items())"
        self.assertEqual(1, text.count(old))
        path.write_text(text.replace(old, "return sum(costs.get(t, 0) * n for t, n in counts.items()) + 10_000"),
                        encoding="utf-8")
        result = g.verify(self.root)
        self.assertEqual(("mismatch", ["assignment_planned_cost"]), (result["status"], result["mismatched"]))

    def test_verify_record_missing_a_required_name_is_mismatch(self) -> None:
        from src.measurement.config_loader import dump_yaml, load_yaml

        self.record()
        target = self.root / g.LOCK_RECORD
        loaded = dict(load_yaml(target))
        loaded["budget_cap"] = {**loaded["budget_cap"],
                                "names": [r for r in loaded["budget_cap"]["names"] if r["name"] != "resolve_budget"]}
        dump_yaml(target, loaded)
        result = g.verify(self.root)
        self.assertEqual(("mismatch", ["resolve_budget"]), (result["status"], result["not_in_record"]))

    def test_check_command_does_not_write(self) -> None:
        collected = g.collect(self.run_dir, self.commit, self.root)
        preview = g.build_record(collected, locked_by=None, now=None)
        self.assertIsNone(preview["locked_by"])
        self.assertIsNone(preview["locked_at"])
        self.assertFalse((self.root / g.LOCK_RECORD).exists())


if __name__ == "__main__":
    unittest.main()
