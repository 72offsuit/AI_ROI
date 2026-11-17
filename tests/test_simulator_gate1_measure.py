"""`scripts/gate1_measure.py` — GATE 1 실측 한 번에: 사전 점검 · 명령 모양 · 실행 보호 장치 · 종료 코드 · 리허설 표시.

사전 점검과 `execute()` 보호 장치(실행 중 트리 변경 · 단계 실패 · 판정 리포트 불일치 · 내부 오류)는 임시 git 저장소와
가짜 `run_step` 으로 확인한다 — 시뮬레이터를 돌리지 않는다. 명령 모양은 저장소 기준 파일의 `sources.*` ·
`churn_threshold.source.command` 템플릿과 대조한다 — 템플릿이 문서이므로 어긋나면 여기서 잡힌다.
`TestRehearsalEndToEnd` 는 보정 seed 42~46 · 고객 200명으로 전 과정을 실제로 돌린다(약 15초, 트리 상태만 가짜).
확인 seed 47~51 은 명령 문자열 · 가짜 기록을 만들 뿐 실행하지 않는다 — `gm.main` 을 부르는 테스트는 `execute` 를
막거나(`NO_EXECUTE`) 확인 seed 가 없는지 확인한 뒤에만 넘긴다(`guarded_execute`).

PyYAML 이 없으면 skip, 실제 실행은 3.12 + 의존성 전부가 있어야 돈다. skip 은 통과가 아니다.
"""

from __future__ import annotations

import contextlib
import io
import json
import os
import shlex
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from argparse import Namespace
from pathlib import Path
from unittest import mock

from tests.test_simulator_gate1_churn_check import HAVE_YAML, base_criteria, write_yaml_json

# scripts/ 는 test_simulator_gate1_churn_check 가 sys.path 에 넣었다 — 같은 모듈 한 벌을 공유한다.
import gate1_measure as gm  # noqa: E402

REPO = Path(__file__).resolve().parents[1]
REAL_CRITERIA = REPO / "config" / "simulator_gate1_acceptance.yaml"
CONFIRMATION_SEEDS = {47, 48, 49, 50, 51}

NEEDS_YAML = "BLOCKED: PyYAML 미설치 — GATE 1 실측 계획을 검증하지 않았다(통과가 아니다)"
NEEDS_GIT = "BLOCKED: git 미설치 — 트리 점검을 검증하지 않았다(통과가 아니다)"
# main 이 사전 점검을 통과해도 실측을 시작하지 못하게 막는다 — 회귀로 공식 47~51 실행이 시작되지 않게.
NO_EXECUTE = AssertionError("실측을 시작하면 안 된다")


def _full_runtime() -> bool:
    if tuple(sys.version_info[:2]) != gm.REQUIRED_PYTHON:
        return False
    try:
        for name in gm.REQUIRED_MODULES:
            __import__(name)
    except ImportError:
        return False
    return True


FULL_RUNTIME = _full_runtime()
NEEDS_RUNTIME = "BLOCKED: 3.12 + 의존성(requirements*.txt) 미설치 — 실제 실행 경로를 검증하지 않았다(통과가 아니다)"
HAVE_GIT = shutil.which("git") is not None


def git(repo: Path, *args: str) -> str:
    return subprocess.run(["git", "-c", "user.name=test", "-c", "user.email=test@example.invalid", *args],
                          cwd=repo, check=True, capture_output=True, text=True).stdout


def args_for(default_out: Path, **override) -> Namespace:
    """prepare 에 넘길 인자. `official` 을 따로 주지 않으면 리허설 seed 가 없을 때 공식(--official)으로 본다."""
    values = {"out": str(default_out), "criteria": "config/criteria.yaml", "jobs": 5, "rehearsal_seeds": None,
              "rehearsal_customers": None, "step_timeout": 60.0, "dry_run": True}
    values.update(override)
    values.setdefault("official", values["rehearsal_seeds"] is None)
    return Namespace(**values)


@contextlib.contextmanager
def clean_tree():
    """이 저장소의 실제 HEAD 는 그대로 쓰고 작업 트리만 깨끗하다고 본다(개발 중 브랜치는 더럽다)."""
    real = gm.git_state

    def fake(repo: Path) -> dict:
        state = real(repo)
        return {"head": state["head"], "porcelain": "", "clean": True}

    with mock.patch.object(gm, "git_state", fake):
        yield


@contextlib.contextmanager
def cwd(path: Path):
    before = Path.cwd()
    os.chdir(path)
    try:
        yield
    finally:
        os.chdir(before)


def guarded_execute(prepared, *args, **kwargs):
    """확인 seed 가 계획에 없을 때만 실제 execute 로 넘긴다."""
    overlap = CONFIRMATION_SEEDS & set(prepared.plan.seeds)
    if overlap or prepared.plan.official:
        raise AssertionError(f"확인 seed {sorted(overlap)} · 공식 실행을 테스트에서 시작하면 안 된다")
    return REAL_EXECUTE(prepared, *args, **kwargs)


REAL_EXECUTE = gm.execute


def fake_judge_report(name: str, code: int) -> dict:
    report: dict = {"verdict": {"exit_code": code}}
    if name == "gate1_judge":
        report["verdict"]["failed"] = [] if code == 0 else ["ate_T3"]
    elif name == "churn_threshold":
        report.update(met=code == 0, comparisons=[], evidence="data_spec §5.1 — 가짜 근거")
    else:
        report.update(violations_total={"not_coupon_arm": 0}, per_seed={"42": {"discounted_by_arm": {"T2": 3}}})
    return report


class FakeRunner:
    """`gm.run_step` 대역 — 하위 프로세스를 돌리지 않고 기록만 만든다. 판정 단계는 리포트 JSON · MD 를 쓴다."""

    def __init__(self, *, failed: set[tuple[int | None, str]] = frozenset(), judge_codes: dict | None = None,
                 write_json: bool = True, reported_codes: dict | None = None, hook=None, raise_on: str | None = None,
                 raise_exc: BaseException | None = None, judge_status: dict | None = None):
        self.failed, self.judge_codes = failed, judge_codes or {}
        self.write_json, self.reported_codes = write_json, reported_codes or {}
        self.hook, self.raise_on = hook, raise_on
        self.raise_exc = raise_exc or RuntimeError("가짜 내부 오류")
        self.judge_status = judge_status or {}
        self.calls: list[tuple[int | None, str]] = []

    def __call__(self, step, repo, env, timeout, stop=None):
        self.calls.append((step.seed, step.name))
        if self.hook:
            self.hook(step)
        if self.raise_on in (step.name, (step.seed, step.name)):
            raise self.raise_exc
        if step.name in self.judge_status:   # 시간 초과 · 실행 오류 — 종료 코드도 리포트도 없다
            return {"name": step.name, "seed": step.seed, "argv": list(step.argv), "exit_code": None,
                    "status": self.judge_status[step.name], "duration_s": 0.0, "stdout": str(step.stdout),
                    "stderr": str(step.stderr), "outputs": dict(step.outputs), "note": None}
        code = 1 if (step.seed, step.name) in self.failed else self.judge_codes.get(step.name, 0)
        step.log_dir.mkdir(parents=True, exist_ok=True)
        if step.seed is None and code in (0, 1):
            Path(step.outputs["md"]).write_text(f"# 가짜 {step.name}\n\n기준 `{step.argv[step.argv.index('--criteria') + 1]}`\n", encoding="utf-8")
            if self.write_json:
                report = fake_judge_report(step.name, self.reported_codes.get(step.name, code))
                Path(step.outputs["json"]).write_text(json.dumps(report, ensure_ascii=False), encoding="utf-8")
        return {"name": step.name, "seed": step.seed, "argv": list(step.argv), "exit_code": code,
                "status": "ok" if code == 0 or step.seed is None else "failed", "duration_s": 0.0,
                "stdout": str(step.stdout), "stderr": str(step.stderr), "outputs": dict(step.outputs), "note": None}


class TestExitCodeMapping(unittest.TestCase):
    def test_mapping(self) -> None:
        ok = {"gate1_judge": 0, "churn_threshold": 0, "a_discount": 0}
        cases = [
            (True, ok, False, 0),
            (True, {**ok, "churn_threshold": 1}, False, 0),     # churn 미충족은 종료 코드를 바꾸지 않는다
            (True, {**ok, "gate1_judge": 1}, False, 1),
            (True, {**ok, "a_discount": 1}, False, 1),
            (True, {**ok, "churn_threshold": 2}, False, 2),
            (True, {**ok, "gate1_judge": 1, "a_discount": 3}, False, 3),
            (True, {**ok, "gate1_judge": None}, False, 3),      # 시간 초과 · 시그널
            (True, {**ok, "a_discount": -9}, False, 3),
            (False, {}, False, 2),                               # 측정 단계 실패 → 판정 안 함
            (True, {**ok, "gate1_judge": 1}, True, 2),           # 실행 중 트리 변경
            (True, {**ok, "a_discount": 3}, True, 3),
        ]
        for steps_ok, judges, changed, expected in cases:
            with self.subTest(steps_ok=steps_ok, judges=judges, changed=changed):
                self.assertEqual(expected, gm.overall_exit(steps_ok, judges, changed))

    def test_judge_report_must_confirm_its_exit_code(self) -> None:
        self.assertEqual((0, None), gm.checked_judge_code(0, {"verdict": {"exit_code": 0}}))
        self.assertEqual((2, None), gm.checked_judge_code(2, None))
        self.assertEqual(3, gm.checked_judge_code(0, None)[0])
        self.assertEqual(3, gm.checked_judge_code(1, {"verdict": {"exit_code": 0}})[0])
        self.assertEqual(3, gm.checked_judge_code(0, {"verdict": "pass"})[0])

    def test_rehearsal_title_marking(self) -> None:
        self.assertEqual(f"# {gm.REHEARSAL_TITLE} · GATE 1 판정 — 통과\n\n본문\n",
                         gm.mark_rehearsal("# GATE 1 판정 — 통과\n\n본문\n"))
        self.assertTrue(gm.mark_rehearsal("제목 없음\n").startswith(f"# {gm.REHEARSAL_TITLE}\n"))


class TestRunStep(unittest.TestCase):
    """실제 하위 프로세스(현재 인터프리터 `-c`)로 단계 기록 규칙을 본다."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.tmp = Path(self._tmp.name)

    def step(self, name: str, code: str, *, expect=(), after=None) -> gm.Step:
        return gm.Step(name, 42, (sys.executable, "-c", code), self.tmp / "logs", {}, expect=expect, after=after)

    def test_exit_zero_without_expected_output_is_missing_output(self) -> None:
        record = gm.run_step(self.step("guardrail", "pass", expect=((str(self.tmp), "report-*.json"),)),
                             self.tmp, {}, 30)
        self.assertEqual(0, record["exit_code"])
        self.assertEqual("missing_output", record["status"])
        self.assertIn("report-*.json", record["note"])

    def test_expected_output_present_is_ok(self) -> None:
        (self.tmp / "report-1.json").write_text("{}", encoding="utf-8")
        record = gm.run_step(self.step("guardrail", "pass", expect=((str(self.tmp), "report-*.json"),)),
                             self.tmp, {}, 30)
        self.assertEqual("ok", record["status"])

    def test_timeout(self) -> None:
        record = gm.run_step(self.step("world", "import time; time.sleep(30)"), self.tmp, {}, 0.5)
        self.assertEqual("timeout", record["status"])
        self.assertIsNone(record["exit_code"])

    def test_nonzero_exit_and_stderr_are_recorded(self) -> None:
        record = gm.run_step(self.step("world", "import sys; print('나쁨', file=sys.stderr); sys.exit(4)"),
                             self.tmp, dict(os.environ), 30)
        self.assertEqual(("failed", 4), (record["status"], record["exit_code"]))
        self.assertIn("나쁨", Path(record["stderr"]).read_text(encoding="utf-8"))

    def test_run_seed_skips_dependent_step_but_runs_independent_ones(self) -> None:
        sink: list = []
        records = gm.run_seed((self.step("world", "import sys; sys.exit(1)"),
                               self.step("realism", "pass", after="world"),
                               self.step("churn_measure", "pass")), self.tmp, {}, 30, sink)
        self.assertEqual(["failed", "skipped", "ok"], [r["status"] for r in records])
        self.assertEqual(records, sink)   # 단계가 끝날 때마다 manifest 쪽 목록에도 남는다

    def test_run_seed_with_stop_set_runs_nothing(self) -> None:
        stop = gm.threading.Event()
        stop.set()
        with mock.patch.object(gm, "run_step", side_effect=AssertionError("단계를 돌리면 안 된다")):
            records = gm.run_seed((self.step("guardrail", "pass"), self.step("world", "pass")), self.tmp, {}, 30,
                                  stop=stop)
        self.assertEqual([("skipped", gm.INTERRUPTED)] * 2, [(r["status"], r["note"]) for r in records])

    def test_stop_during_a_step_marks_it_interrupted_and_skips_the_rest(self) -> None:
        stop = gm.threading.Event()

        def interrupted_step(step, repo, env, timeout, *_):
            stop.set()   # 이 단계가 도는 중에 Ctrl-C 가 왔다 — 자식은 신호로 0 이 아니게 끝난다
            return {"name": step.name, "seed": step.seed, "argv": list(step.argv), "exit_code": -2,
                    "status": "failed", "duration_s": 0.1, "stdout": None, "stderr": None, "outputs": {}, "note": None}

        with mock.patch.object(gm, "run_step", interrupted_step):
            records = gm.run_seed((self.step("guardrail", "pass"), self.step("world", "pass"),
                                   self.step("churn_measure", "pass")), self.tmp, {}, 30, stop=stop)
        self.assertEqual(["interrupted", "skipped", "skipped"], [r["status"] for r in records])
        self.assertEqual({gm.INTERRUPTED}, {r["note"] for r in records})

    def test_terminate_running_sets_the_stop_flag(self) -> None:
        stop = threading.Event()
        gm.terminate_running(stop, grace_s=1)
        self.assertTrue(stop.is_set())

    def test_stop_terminates_a_registered_child_and_skips_the_rest(self) -> None:
        # 실제 _execute 경로: 자식이 _RUNNING 에 등록돼야 terminate_running 이 끝낼 수 있다.
        stop = threading.Event()
        steps = (self.step("guardrail", "import time; time.sleep(60)"), self.step("world", "pass"))
        result: dict = {}
        worker = threading.Thread(target=lambda: result.update(records=gm.run_seed(steps, self.tmp, {}, 120, stop=stop)),
                                  daemon=True)
        worker.start()
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            with gm._RUNNING_LOCK:
                procs = list(gm._RUNNING)
            if procs:
                break
            time.sleep(0.05)
        self.assertEqual(1, len(procs), "_execute 가 자식을 _RUNNING 에 등록하지 않았다")
        gm.terminate_running(stop, grace_s=5)
        worker.join(30)
        self.assertFalse(worker.is_alive())
        self.assertIsNotNone(procs[0].poll())   # 자식이 실제로 끝났다
        self.assertEqual([("interrupted", gm.INTERRUPTED), ("skipped", gm.INTERRUPTED)],
                         [(r["status"], r["note"]) for r in result["records"]])
        self.assertEqual(set(), gm._RUNNING)

    def test_child_started_after_stop_is_stopped_at_once(self) -> None:
        # 등록 직후 stop 재확인 — terminate_running 이 목록을 읽은 뒤에 띄운 자식도 남지 않는다.
        stop = threading.Event()
        stop.set()
        started = time.monotonic()
        code = gm._execute((sys.executable, "-c", "import time; time.sleep(30)"), self.tmp, {},
                           self.tmp / "o.log", self.tmp / "e.log", 20, stop)
        self.assertLess(time.monotonic() - started, 10)
        self.assertIsNotNone(code)
        self.assertNotEqual(0, code)
        self.assertEqual(set(), gm._RUNNING)

    def test_exception_while_waiting_stops_the_child(self) -> None:
        # 주 스레드에서 자식을 기다리다 Ctrl-C 를 받는 경우(판정 단계) — 자식을 끝내고 목록에서 뺀 뒤 다시 던진다.
        created: list = []

        class InterruptingPopen(subprocess.Popen):
            def __init__(self, *args, **kwargs):
                super().__init__(*args, **kwargs)
                self.interrupt_once = True
                created.append(self)

            def wait(self, timeout=None):
                if self.interrupt_once:
                    self.interrupt_once = False
                    raise KeyboardInterrupt
                return super().wait(timeout)

        def cleanup() -> None:
            for proc in created:
                if proc.poll() is None:
                    proc.kill()
                    proc.wait()

        self.addCleanup(cleanup)
        with mock.patch.object(gm.subprocess, "Popen", InterruptingPopen), self.assertRaises(KeyboardInterrupt):
            gm._execute((sys.executable, "-c", "import time; time.sleep(60)"), self.tmp, {},
                        self.tmp / "o.log", self.tmp / "e.log", 120)
        self.assertEqual(1, len(created))
        self.assertIsNotNone(created[0].poll())
        self.assertNotIn(created[0], gm._RUNNING)

    def test_terminate_running_stops_live_children(self) -> None:
        proc = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"])
        with gm._RUNNING_LOCK:
            gm._RUNNING.add(proc)
        try:
            gm.terminate_running(grace_s=5)
            self.assertIsNotNone(proc.poll())
        finally:
            with gm._RUNNING_LOCK:
                gm._RUNNING.discard(proc)
            if proc.poll() is None:
                proc.kill()
                proc.wait()


class TestSafePathImport(unittest.TestCase):
    """스크립트의 gate1_* import 가 sys.path[0](스크립트 디렉터리)에 기대지 않는다 — `python -P` 에서도 뜬다."""

    @unittest.skipIf(sys.version_info < (3, 11), "python -P 는 3.11 부터 있다 — 3.10 에서는 확인하지 않았다(통과가 아니다)")
    def test_scripts_start_under_safe_path(self) -> None:
        for script in ("gate1_churn_check.py", "gate1_discount_check.py", "gate1_measure.py"):
            with self.subTest(script=script):
                result = subprocess.run([sys.executable, "-P", f"scripts/{script}", "--help"], cwd=REPO,
                                        capture_output=True, text=True, timeout=60)
                self.assertEqual(0, result.returncode, result.stderr)


class TestNewDir(unittest.TestCase):
    def test_inside_repo_existing_and_symlinked_into_repo_are_refused(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            outside = Path(tmp) / "new"
            problems: list[str] = []
            gm.check_new_dir(outside, REPO, problems)
            self.assertEqual([], problems)

            gm.check_new_dir(REPO / "measure-out-never-created", REPO, problems)
            self.assertTrue(any("작업 트리 안" in p for p in problems), problems)

            problems = []
            gm.check_new_dir(Path(tmp), REPO, problems)
            self.assertTrue(any("이미 있다" in p for p in problems), problems)

            link = Path(tmp) / "link"
            link.symlink_to(REPO / "scripts", target_is_directory=True)
            problems = []
            gm.check_new_dir(link / "new", REPO, problems)
            self.assertTrue(any("작업 트리 안" in p for p in problems), problems)


class TestEnvironmentCheck(unittest.TestCase):
    def test_wrong_interpreter_and_missing_dependency(self) -> None:
        def importer(name: str):
            if name == "pandas":
                raise ImportError("No module named 'pandas'")
            return object()

        problems: list[str] = []
        gm.check_environment((3, 11, 9), importer, problems)
        self.assertTrue(any("3.11.9" in p for p in problems), problems)
        self.assertTrue(any(p.startswith("pandas 를 import 하지 못했다") for p in problems), problems)

        problems = []
        gm.check_environment((3, 12, 1), lambda name: object(), problems)
        self.assertEqual([], problems)

    def test_step_timeout_must_be_finite_and_positive(self) -> None:
        for value in (0, -1, float("inf"), float("nan"), True):
            with self.subTest(value=value):
                problems: list[str] = []
                gm.check_step_timeout(value, problems)
                self.assertEqual(1, len(problems))
        problems = []
        gm.check_step_timeout(0.5, problems)
        self.assertEqual([], problems)


@unittest.skipUnless(HAVE_GIT, NEEDS_GIT)
@unittest.skipUnless(HAVE_YAML, NEEDS_YAML)
class TempRepoCase(unittest.TestCase):
    """임시 git 저장소에 기준 파일을 커밋해 두고 사전 점검 · 계획 · 실행 보호 장치를 확인한다."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        root = Path(self._tmp.name)
        self.repo, self.out = root / "repo", root / "measure" / "run"
        (self.repo / "config").mkdir(parents=True)
        git(self.repo, "init", "-q")
        self.commit_criteria(base_criteria())

    def commit_criteria(self, data: dict) -> None:
        write_yaml_json(self.repo / "config" / "criteria.yaml", data)
        git(self.repo, "add", "config/criteria.yaml")
        git(self.repo, "commit", "-qm", "criteria")

    def prepare(self, **override):
        return gm.prepare(args_for(self.out, **override), repo=self.repo, cwd=self.repo, python_version=(3, 12, 0),
                          import_module=lambda name: object(), python="PY")

    def assert_refused(self, fragment: str, **override) -> None:
        with self.assertRaises(gm.InputError) as caught:
            self.prepare(**override)
        self.assertTrue(any(fragment in p for p in caught.exception.problems), caught.exception.problems)


class TestPrepareInTempRepo(TempRepoCase):
    def test_official_plan_uses_criteria_seeds_and_records_provenance(self) -> None:
        prepared = self.prepare()
        plan, pre = prepared.plan, prepared.preflight
        self.assertTrue(plan.official)
        self.assertEqual((47, 48, 49, 50, 51), plan.seeds)
        self.assertEqual("config/criteria.yaml", plan.criteria_arg)
        self.assertIsNone(prepared.criteria_text)
        self.assertEqual(git(self.repo, "rev-parse", "HEAD").strip(), pre["head"])
        self.assertEqual(pre["head"], pre["criteria"]["last_commit"])
        self.assertEqual(64, len(pre["criteria"]["sha256"]))
        self.assertTrue(pre["clean_tree"])
        self.assertEqual({"utc", "kst"}, set(pre["started_at"]))
        self.assertFalse(self.out.exists())   # 계획만 세우고 아무것도 만들지 않는다
        names = [step.name for step in plan.judge_steps]
        self.assertEqual(["gate1_judge", "churn_threshold", "a_discount"], names)
        churn_judge = plan.judge_steps[1].argv
        self.assertEqual("config/simulator_config.yaml", churn_judge[churn_judge.index("--simulator-config") + 1])
        discount = plan.judge_steps[2].argv
        self.assertEqual("config/economic_config.yaml", discount[discount.index("--economic-config") + 1])

    def test_dirty_tree_is_refused(self) -> None:
        (self.repo / "untracked.txt").write_text("x", encoding="utf-8")
        self.assert_refused("작업 트리가 깨끗하지 않다")

    def test_untracked_file_is_seen_even_if_git_config_hides_untracked_files(self) -> None:
        git(self.repo, "config", "status.showUntrackedFiles", "no")
        (self.repo / "untracked.txt").write_text("x", encoding="utf-8")
        self.assert_refused("작업 트리가 깨끗하지 않다")

    def test_modified_tracked_file_is_refused(self) -> None:
        (self.repo / "config" / "criteria.yaml").write_text(
            (self.repo / "config" / "criteria.yaml").read_text(encoding="utf-8") + "\n", encoding="utf-8")
        self.assert_refused("작업 트리가 깨끗하지 않다")

    def test_cwd_must_be_repo_root(self) -> None:
        with self.assertRaises(gm.InputError) as caught:
            gm.prepare(args_for(self.out), repo=self.repo, cwd=self.repo / "config", python_version=(3, 12, 0),
                       import_module=lambda name: object(), python="PY")
        self.assertTrue(any("저장소 루트" in p for p in caught.exception.problems))

    def test_new_dir_inside_repo_is_refused(self) -> None:
        self.assert_refused("작업 트리 안", out=str(self.repo / "out"))

    def test_step_timeout_is_validated(self) -> None:
        self.assert_refused("--step-timeout", step_timeout=float("inf"))

    def test_uncommitted_criteria_is_refused(self) -> None:
        write_yaml_json(self.repo / "config" / "other.yaml", base_criteria())
        self.assert_refused("커밋돼 있지 않다", criteria="config/other.yaml")

    def test_broken_criteria_block_is_refused_before_running(self) -> None:
        data = base_criteria()
        del data["a_discount"]["coupon_arms"]
        self.commit_criteria(data)
        self.assert_refused("coupon_arms")

    def test_churn_source_must_match_the_measure_template(self) -> None:
        data = base_criteria()
        data["churn_threshold"]["source"]["days"] = 200
        self.commit_criteria(data)
        self.assert_refused("measure 기본값")

    def test_world_config_must_match_the_run_world_template(self) -> None:
        data = base_criteria()
        data["sources"]["realism"]["world"]["config"] = "config/experiment.yaml"
        self.commit_criteria(data)
        self.assert_refused("실험 config 세계")

    def test_world_conditions_come_from_the_criteria(self) -> None:
        data = base_criteria()
        data["sources"]["realism"]["world"].update(days=300, assign_day=150)
        self.commit_criteria(data)
        argv = self.prepare(rehearsal_seeds=[42]).plan.seed_steps[42][1].argv
        self.assertEqual(("300", "150"), (argv[argv.index("--days") + 1], argv[argv.index("--assign-day") + 1]))

    def test_rehearsal_copy_replaces_seeds_version_and_marks_unofficial(self) -> None:
        prepared = self.prepare(rehearsal_seeds=[42, 43, 44, 45, 46])
        plan = prepared.plan
        self.assertFalse(plan.official)
        self.assertEqual((42, 43, 44, 45, 46), plan.seeds)
        self.assertEqual(str(self.out / gm.REHEARSAL_CRITERIA), plan.criteria_arg)
        self.assertTrue(prepared.criteria_text.startswith(f"# {gm.REHEARSAL_TITLE}"))
        copy_path = Path(self._tmp.name) / "copy.yaml"
        copy_path.write_text(prepared.criteria_text, encoding="utf-8")
        criteria = gm.gj.load_criteria(copy_path)
        self.assertEqual((42, 43, 44, 45, 46), criteria.seeds)
        self.assertEqual(13000, criteria.customers)
        self.assertEqual("gate1-acceptance-test-rehearsal", criteria.version)
        for step in plan.judge_steps:
            self.assertEqual(plan.criteria_arg, step.argv[step.argv.index("--criteria") + 1])

    def test_rehearsal_customers_override_only_with_rehearsal_seeds(self) -> None:
        prepared = self.prepare(rehearsal_seeds=[42], rehearsal_customers=200)
        self.assertEqual(200, prepared.plan.customers)
        argv = prepared.plan.seed_steps[42][0].argv
        self.assertEqual("200", argv[argv.index("--customers") + 1])
        self.assert_refused("--rehearsal-seeds 와 함께만", rehearsal_customers=200)

    def test_mode_must_be_chosen_explicitly(self) -> None:
        self.assert_refused("실행 방식을 고른다", official=False)                       # 둘 다 없음
        self.assert_refused("실행 방식을 고른다", official=True, rehearsal_seeds=[42])  # 둘 다 줌

    def test_rehearsal_must_not_open_confirmation_seeds(self) -> None:
        self.assert_refused("확인 seed", rehearsal_seeds=[42, 47])
        self.assert_refused("중복", rehearsal_seeds=[42, 42])


class TestExecuteProtections(TempRepoCase):
    """`execute()` 의 보호 장치 — 가짜 `run_step` 이라 시뮬레이터 · 판정 스크립트를 실제로 돌리지 않는다."""

    def run_execute(self, runner: FakeRunner, **override) -> dict:
        prepared = self.prepare(**{"rehearsal_seeds": [42, 43], **override})
        manifest: dict = {}
        with mock.patch.object(gm, "run_step", runner):
            gm.execute(prepared, 2, 60.0, manifest)
        self.summary = gm.render_summary(manifest, prepared.plan.new_dir)
        return manifest

    def assert_invalid(self, manifest: dict, code: int) -> None:
        self.assertEqual(code, manifest["exit_code"])
        self.assertFalse(manifest["valid"])
        for key in gm.VERDICT_KEYS:
            self.assertIsNone(manifest[key], key)
        self.assertIn("note", manifest["unbound_results"])
        self.assertTrue(self.summary.startswith(f"# 판정 무효 — 종료 {code}("), self.summary.splitlines()[0])
        self.assertIn("아래 판정은 커밋에 묶이지 않았다", self.summary.splitlines()[0])
        self.assertNotIn("필수 검사 통과", self.summary)
        self.assertNotIn("공식 판정: 예", self.summary)

    def test_valid_run_keeps_flags_and_marks_rehearsal_reports(self) -> None:
        manifest = self.run_execute(FakeRunner())
        self.assertEqual(0, manifest["exit_code"])
        self.assertTrue(manifest["valid"])
        self.assertEqual((True, True, True), (manifest["gate1_required_pass"], manifest["churn_met"],
                                              manifest["discount_pass"]))
        self.assertEqual("data_spec §5.1 — 가짜 근거", manifest["churn_evidence"])
        self.assertEqual(8, len(manifest["steps"]))
        self.assertTrue(self.summary.startswith(f"# {gm.REHEARSAL_TITLE}"))
        self.assertIn("공식 판정: 아니오(리허설)", self.summary)
        self.assertIn("seed 42: T2 3", self.summary)       # A-DISCOUNT 줄에 seed 별 할인 주문 수
        for judge in manifest["judges"]:
            md = Path(judge["outputs"]["md"]).read_text(encoding="utf-8")
            self.assertTrue(md.startswith(f"# {gm.REHEARSAL_TITLE}"), md)
            self.assertNotIn(str(self.out), md)
            report = json.loads(Path(judge["outputs"]["json"]).read_text(encoding="utf-8"))
            self.assertEqual((False, True), (report["official"], report["rehearsal"]))

    def test_official_valid_run_says_official(self) -> None:
        # 가짜 run_step 이라 확인 seed 를 실제로 돌리지 않는다 — 공식 표시 규칙만 본다.
        manifest = self.run_execute(FakeRunner(judge_codes={"gate1_judge": 1}), rehearsal_seeds=None)
        self.assertEqual(1, manifest["exit_code"])
        self.assertTrue(manifest["valid"])
        self.assertFalse(manifest["gate1_required_pass"])
        self.assertIn("공식 판정: 예", self.summary)
        self.assertTrue(self.summary.startswith("# GATE 1 실측 요약"))

    def stray_file_hook(self, step) -> None:
        if step.name == "realism":
            (self.repo / "stray.txt").write_text("x", encoding="utf-8")

    def assert_judge_outputs_marked_invalid(self, manifest: dict) -> None:
        for judge in manifest["judges"]:
            md = Path(judge["outputs"]["md"]).read_text(encoding="utf-8")
            self.assertTrue(md.startswith(f"# {gm.INVALID_TITLE} · "), md.splitlines()[0])
            report = json.loads(Path(judge["outputs"]["json"]).read_text(encoding="utf-8"))
            self.assertIs(False, report["valid"])

    def test_file_created_during_run_invalidates(self) -> None:
        manifest = self.run_execute(FakeRunner(hook=self.stray_file_hook))
        self.assertTrue(manifest["tree_changed_during_run"])
        self.assert_invalid(manifest, 2)
        self.assertIn("실행 중 작업 트리", self.summary.splitlines()[0])
        self.assertTrue(manifest["unbound_results"]["gate1_required_pass"])
        self.assert_judge_outputs_marked_invalid(manifest)

    def test_official_invalid_run_is_not_called_official(self) -> None:
        # 가짜 run_step 이라 확인 seed 를 실제로 돌리지 않는다. 판정은 통과(0)였지만 트리가 바뀌어 무효다.
        manifest = self.run_execute(FakeRunner(hook=self.stray_file_hook), rehearsal_seeds=None)
        self.assertTrue(manifest["official"])
        self.assert_invalid(manifest, 2)
        self.assertIn("공식 판정: 아니오(판정 무효)", self.summary)
        self.assertNotIn("공식 판정: 예", self.summary)
        self.assert_judge_outputs_marked_invalid(manifest)

    def test_valid_run_does_not_mark_judge_outputs_invalid(self) -> None:
        manifest = self.run_execute(FakeRunner(), rehearsal_seeds=None)
        for judge in manifest["judges"]:
            self.assertNotIn(gm.INVALID_TITLE, Path(judge["outputs"]["md"]).read_text(encoding="utf-8"))
            self.assertNotIn("valid", json.loads(Path(judge["outputs"]["json"]).read_text(encoding="utf-8")))

    def test_judge_timeout_is_named_in_the_invalid_reason(self) -> None:
        manifest = self.run_execute(FakeRunner(judge_status={"churn_threshold": "timeout"}))
        self.assert_invalid(manifest, 3)
        self.assertIn("churn_threshold timeout", self.summary.splitlines()[0])
        self.assertIn("churn_threshold timeout", manifest["invalid_reasons"])

    def test_commit_added_during_run_invalidates(self) -> None:
        def hook(step):
            if step.name == "gate1_judge":
                (self.repo / "late.txt").write_text("x", encoding="utf-8")
                git(self.repo, "add", "late.txt")
                git(self.repo, "commit", "-qm", "late")

        manifest = self.run_execute(FakeRunner(hook=hook))
        self.assertTrue(manifest["end"]["clean"])
        self.assertNotEqual(manifest["preflight"]["head"], manifest["end"]["head"])
        self.assert_invalid(manifest, 2)

    def test_unreadable_final_git_state_invalidates(self) -> None:
        prepared = self.prepare(rehearsal_seeds=[42])
        manifest: dict = {}
        with mock.patch.object(gm, "run_step", FakeRunner()), \
                mock.patch.object(gm, "git_state", side_effect=RuntimeError("git 없음")):
            gm.execute(prepared, 1, 60.0, manifest)
        self.summary = gm.render_summary(manifest, prepared.plan.new_dir)
        self.assertTrue(manifest["tree_changed_during_run"])
        self.assertIn("git 없음", manifest["end"]["error"])
        self.assert_invalid(manifest, 2)

    def test_failed_step_skips_all_judges(self) -> None:
        runner = FakeRunner(failed={(43, "guardrail")})
        manifest = self.run_execute(runner)
        self.assertEqual({"skipped"}, {j["status"] for j in manifest["judges"]})
        self.assertFalse(any(seed is None for seed, _ in runner.calls))   # 판정은 한 번도 부르지 않았다
        self.assertFalse(manifest["steps_ok"])
        self.assert_invalid(manifest, 2)
        self.assertIn("seed 43 guardrail failed", self.summary)

    def test_judge_without_report_is_an_internal_error(self) -> None:
        manifest = self.run_execute(FakeRunner(write_json=False))
        self.assertEqual({3}, {j["effective_exit_code"] for j in manifest["judges"]})
        self.assertEqual({0}, {j["exit_code"] for j in manifest["judges"]})
        self.assert_invalid(manifest, 3)

    def test_judge_exit_code_contradicting_its_report_is_an_internal_error(self) -> None:
        manifest = self.run_execute(FakeRunner(reported_codes={"a_discount": 1}))
        judge = next(j for j in manifest["judges"] if j["name"] == "a_discount")
        self.assertEqual((0, 3), (judge["exit_code"], judge["effective_exit_code"]))
        self.assertIn("verdict.exit_code", judge["note"])
        self.assert_invalid(manifest, 3)

    def test_summary_has_no_local_absolute_paths(self) -> None:
        # 실패 단계(stderr 경로 · note)와 리허설 사본 경로가 모두 실리는 경우로 본다.
        self.run_execute(FakeRunner(failed={(42, "world")}))
        for leak in {str(self.out), str(self.out.resolve()), str(Path.home()), "/Users/", "/private/",
                     self._tmp.name}:
            self.assertNotIn(leak, self.summary)
        self.assertIn("`seed-42/logs/world.stderr.log`", self.summary)
        self.assertIn("`criteria-rehearsal.yaml`", self.summary)

    def run_main_with(self, runner, jobs: str = "2", *extra: str, prepare=None) -> tuple[int, str]:
        prepared = self.prepare(rehearsal_seeds=[42, 43])
        self.prepared = prepared
        patched_prepare = mock.patch.object(gm, "prepare", side_effect=prepare) if prepare \
            else mock.patch.object(gm, "prepare", return_value=prepared)
        stderr = io.StringIO()
        with patched_prepare, mock.patch.object(gm, "run_step", runner), \
                contextlib.redirect_stderr(stderr), contextlib.redirect_stdout(io.StringIO()):
            code = gm.main(["--out", str(self.out), "--rehearsal-seeds", "42", "43", "--jobs", jobs, *extra])
        return code, stderr.getvalue()

    def test_new_dir_appearing_after_preflight_is_never_written(self) -> None:
        # 사전 점검 뒤 · 실행 전에 다른 실행이 같은 NEW_DIR 을 만들었다 — 그 디렉터리에 아무것도 쓰지 않고 3 으로 끝난다.
        marker = '{"다른 실행": true}'
        prepared = self.prepare(rehearsal_seeds=[42, 43])   # gm.prepare 를 바꿔 끼우기 전에 진짜 사전 점검을 한다

        def prepare_then_collide(args):
            self.out.mkdir(parents=True)
            (self.out / gm.MANIFEST).write_text(marker, encoding="utf-8")
            return prepared

        runner = FakeRunner()
        code, stderr = self.run_main_with(runner, prepare=prepare_then_collide)
        self.assertEqual(gm.EXIT_INTERNAL_ERROR, code)
        self.assertIn("FileExistsError", stderr)
        self.assertEqual(marker, (self.out / gm.MANIFEST).read_text(encoding="utf-8"))
        self.assertEqual([gm.MANIFEST], [p.name for p in self.out.iterdir()])   # summary · 사본 · 로그 없음
        self.assertEqual([], runner.calls)

    def test_dry_run_interrupted_while_printing_creates_nothing(self) -> None:
        runner = FakeRunner()
        with self.print_raising(KeyboardInterrupt()):
            code, _ = self.run_main_with(runner, "2", "--dry-run")
        self.assertEqual(gm.EXIT_INPUT_ERROR, code)
        self.assertFalse(self.out.exists())
        self.assertEqual([], runner.calls)

    def test_interrupted_rehearsal_judge_report_carries_both_markers_once(self) -> None:
        base = FakeRunner()

        def report_then_interrupt(step, repo, env, timeout, stop=None):
            record = base(step, repo, env, timeout, stop)   # 리포트를 다 쓴 뒤
            if step.name == "churn_threshold":
                raise KeyboardInterrupt                      # 돌아오기 전에 중단됐다
            return record

        code, _ = self.run_main_with(report_then_interrupt)
        self.assertEqual(gm.EXIT_INPUT_ERROR, code)
        judges = {step.name: step for step in self.prepared.plan.judge_steps}

        def snapshot() -> dict:
            files = {name: (Path(step.outputs["md"]).read_text(encoding="utf-8"),
                            Path(step.outputs["json"]).read_text(encoding="utf-8"))
                     for name, step in judges.items() if Path(step.outputs["md"]).exists()}
            return files

        first = snapshot()
        self.assertEqual({"gate1_judge", "churn_threshold"}, set(first))   # a_discount 는 돌지 않았다
        for name, (md, js) in first.items():
            title = md.splitlines()[0]
            self.assertEqual(1, title.count(gm.INVALID_TITLE), title)
            self.assertEqual(1, title.count(gm.REHEARSAL_TITLE), title)
            report = json.loads(js)
            self.assertEqual((False, True, False), (report["official"], report["rehearsal"], report["valid"]), name)

        # 한 번 더 정리해도(중단이 겹친 경우) 판정 리포트 · 결과는 그대로다.
        manifest = json.loads((self.out / gm.MANIFEST).read_text(encoding="utf-8"))
        before = {k: v for k, v in manifest.items() if k != "finished_at"}
        gm.write_partial_results(self.prepared, manifest, gm.EXIT_INPUT_ERROR, interrupted=gm.INTERRUPTED)
        self.assertEqual(first, snapshot())
        after = json.loads((self.out / gm.MANIFEST).read_text(encoding="utf-8"))
        self.assertEqual(before, {k: v for k, v in after.items() if k != "finished_at"})

    def test_interrupt_during_judging_leaves_invalid_partial_manifest(self) -> None:
        code, stderr = self.run_main_with(FakeRunner(raise_on="a_discount", raise_exc=KeyboardInterrupt()))
        self.assertEqual(gm.EXIT_INPUT_ERROR, code)
        self.assertIn(gm.INTERRUPTED, stderr)
        manifest = json.loads((self.out / gm.MANIFEST).read_text(encoding="utf-8"))
        self.assertEqual((2, False, gm.INTERRUPTED), (manifest["exit_code"], manifest["valid"], manifest["interrupted"]))
        self.assertIn(gm.INTERRUPTED, manifest["invalid_reasons"])
        self.assertEqual(8, len(manifest["steps"]))
        self.assertEqual(["gate1_judge", "churn_threshold"], [j["name"] for j in manifest["judges"]])
        self.assertIsNone(manifest["churn_met"])
        # 중단 전에 남은 판정 리포트에도 무효 표시가 붙는다.
        md = Path(manifest["judges"][0]["outputs"]["md"]).read_text(encoding="utf-8")
        self.assertTrue(md.startswith(f"# {gm.INVALID_TITLE}"))
        self.assert_invalid_summary(2, gm.INTERRUPTED)

    def test_interrupt_during_seed_steps_skips_the_rest(self) -> None:
        # seed 42 의 world 단계에서 Ctrl-C 가 주 스레드로 올라온다(작업 스레드의 KeyboardInterrupt 는 future.result()
        # 가 주 스레드에서 다시 던진다). seed 43 은 그동안 첫 단계를 돌고 있다 — execute 가 stop 을 세워야 끝난다.
        prepared = self.prepare(rehearsal_seeds=[42, 43])
        stop = threading.Event()
        seed43_running = threading.Event()

        def hold(step) -> None:
            if (step.seed, step.name) == (43, "guardrail"):
                seed43_running.set()
                stop.wait(10)
            elif (step.seed, step.name) == (42, "world"):
                seed43_running.wait(10)   # 43 이 첫 단계를 돌기 시작한 뒤에 중단한다(순서를 고정한다)

        runner = FakeRunner(raise_on=(42, "world"), raise_exc=KeyboardInterrupt(), hook=hold)
        manifest: dict = {}
        with mock.patch.object(gm, "run_step", runner), \
                mock.patch.object(gm, "terminate_running", wraps=gm.terminate_running) as terminate:
            with self.assertRaises(KeyboardInterrupt):
                gm.execute(prepared, 2, 60.0, manifest, stop)
        self.assertTrue(stop.is_set())
        terminate.assert_called_once_with(stop)
        seed43 = [(r["name"], r["status"], r["note"]) for r in manifest["steps"] if r["seed"] == 43]
        self.assertEqual([("guardrail", "ok", None), ("world", "skipped", gm.INTERRUPTED),
                          ("realism", "skipped", gm.INTERRUPTED), ("churn_measure", "skipped", gm.INTERRUPTED)],
                         seed43)
        self.assertEqual(["guardrail"], [r["name"] for r in manifest["steps"] if r["seed"] == 42])
        self.assertEqual([], manifest["judges"])          # 판정은 시작하지 않았다

    def assert_invalid_summary(self, code: int, reason: str) -> None:
        summary = (self.out / gm.SUMMARY).read_text(encoding="utf-8")
        self.assertTrue(summary.startswith(f"# 판정 무효 — 종료 {code}("), summary.splitlines()[0])
        self.assertIn(reason, summary.splitlines()[0])
        self.assertNotIn("공식 판정: 예", summary)

    def print_raising(self, exc: BaseException):
        """요약을 stdout 에 내는 순간(파일은 이미 정상으로 썼다) 예외가 나게 한다. stderr 출력은 그대로 둔다."""
        import builtins

        def fake_print(*args, **kwargs):
            if kwargs.get("file") is sys.stderr:
                return builtins.print(*args, **kwargs)
            raise exc

        return mock.patch.object(gm, "print", fake_print, create=True)

    def test_interrupt_after_valid_summary_rewrites_everything_invalid(self) -> None:
        with self.print_raising(KeyboardInterrupt()):
            code, _ = self.run_main_with(FakeRunner())
        self.assertEqual(gm.EXIT_INPUT_ERROR, code)
        manifest = json.loads((self.out / gm.MANIFEST).read_text(encoding="utf-8"))
        self.assertEqual((2, False), (manifest["exit_code"], manifest["valid"]))
        self.assertTrue(manifest["unbound_results"]["gate1_required_pass"])   # 덮을 때 결과를 잃지 않는다
        self.assertIsNone(manifest["gate1_required_pass"])
        self.assert_invalid_summary(2, gm.INTERRUPTED)
        for judge in manifest["judges"]:
            md = Path(judge["outputs"]["md"]).read_text(encoding="utf-8")
            self.assertTrue(md.startswith(f"# {gm.INVALID_TITLE} · {gm.REHEARSAL_TITLE}"), md.splitlines()[0])

    def test_error_after_valid_summary_rewrites_everything_invalid(self) -> None:
        with self.print_raising(RuntimeError("출력 실패")):
            code, _ = self.run_main_with(FakeRunner())
        self.assertEqual(gm.EXIT_INTERNAL_ERROR, code)
        manifest = json.loads((self.out / gm.MANIFEST).read_text(encoding="utf-8"))
        self.assertEqual((3, False), (manifest["exit_code"], manifest["valid"]))
        self.assert_invalid_summary(3, "RuntimeError: 출력 실패")

    def test_partial_rewrite_of_an_already_invalid_run_keeps_results_and_marks_once(self) -> None:
        # 트리 변경으로 이미 무효인 실행에서 요약 출력 중 중단 — 두 번 정리해도 결과 · 표시가 한 벌이다.
        with self.print_raising(KeyboardInterrupt()):
            code, _ = self.run_main_with(FakeRunner(hook=lambda step: (self.repo / "stray.txt").write_text(
                "x", encoding="utf-8") if step.name == "realism" else None))
        self.assertEqual(gm.EXIT_INPUT_ERROR, code)
        manifest = json.loads((self.out / gm.MANIFEST).read_text(encoding="utf-8"))
        self.assertTrue(manifest["unbound_results"]["gate1_required_pass"])
        md = Path(manifest["judges"][0]["outputs"]["md"]).read_text(encoding="utf-8")
        self.assertEqual(1, md.count(gm.INVALID_TITLE))
        self.assertFalse(any(j["summary"].startswith("무효(참고): 무효(참고)") for j in manifest["judges"]))

    def test_internal_error_mid_run_leaves_partial_manifest(self) -> None:
        code, stderr = self.run_main_with(FakeRunner(raise_on="churn_threshold"))
        self.assertEqual(gm.EXIT_INTERNAL_ERROR, code)
        self.assertIn("가짜 내부 오류", stderr)
        manifest = json.loads((self.out / gm.MANIFEST).read_text(encoding="utf-8"))
        self.assertEqual(3, manifest["exit_code"])
        self.assertFalse(manifest["valid"])
        self.assertEqual(8, len(manifest["steps"]))            # 그때까지 돈 단계가 남는다
        self.assertEqual(["gate1_judge"], [j["name"] for j in manifest["judges"]])
        self.assertIn("RuntimeError: 가짜 내부 오류", manifest["internal_error"])
        self.assertIsNone(manifest["gate1_required_pass"])
        self.assert_invalid_summary(3, "RuntimeError: 가짜 내부 오류")


@unittest.skipUnless(HAVE_YAML, NEEDS_YAML)
class TestCommandsMatchCriteriaTemplates(unittest.TestCase):
    """기준 파일의 명령 템플릿(문서)과 실제로 돌리는 argv 가 같다 — 둘 중 하나만 고치면 실패한다."""

    PYTHON = "/venv/bin/python3.12"

    def setUp(self) -> None:
        self.raw = gm.gj._load_yaml(REAL_CRITERIA, "기준 파일")
        self.criteria = gm.gj.load_criteria(REAL_CRITERIA)
        world = gm.dc.load_realism_world(self.raw, REAL_CRITERIA)
        self.new_dir = Path("/abs/gate1")
        self.seed = self.criteria.seeds[0]
        steps = gm.seed_steps(self.seed, self.new_dir, self.criteria.customers, self.criteria, world, self.PYTHON)
        self.steps = {step.name: step for step in steps}
        self.root = self.new_dir / f"seed-{self.seed}"

    def expand(self, template: str, **values: str) -> list[str]:
        tokens = shlex.split(template.format(seed=self.seed, **values))
        # 템플릿의 `PYTHONPATH=.` 은 orchestrator 가 환경 변수로 준다(child_env) — argv 에는 없다.
        if tokens[0] == "PYTHONPATH=.":
            tokens = tokens[1:]
        self.assertEqual("python3.12", tokens[0], template)
        return [self.PYTHON, *tokens[1:]]

    def test_guardrail_command(self) -> None:
        template = self.raw["sources"]["guardrail_report"]["command"]
        self.assertEqual(self.expand(template, new_dir=str(self.root / "guardrail")),
                         list(self.steps["guardrail"].argv))

    def test_realism_commands(self) -> None:
        world_template, realism_template = self.raw["sources"]["realism"]["commands"]
        world = str(self.root / "world")
        self.assertEqual(self.expand(world_template, new_dir=world), list(self.steps["world"].argv))
        self.assertEqual(self.expand(realism_template, new_dir=world, json=str(self.root / "realism.json")),
                         list(self.steps["realism"].argv))

    def test_churn_measure_command(self) -> None:
        template = self.raw["churn_threshold"]["source"]["command"]
        self.assertEqual(self.expand(template, new_dir=str(self.root / "warmup")),
                         list(self.steps["churn_measure"].argv))

    def test_children_get_repo_on_pythonpath(self) -> None:
        self.assertEqual(str(REPO), gm.child_env(REPO)["PYTHONPATH"])


@unittest.skipUnless(FULL_RUNTIME, NEEDS_RUNTIME)
class TestDryRunAgainstThisRepo(unittest.TestCase):
    def run_main(self, *argv: str) -> tuple[int, str, str]:
        stdout, stderr = io.StringIO(), io.StringIO()
        with cwd(REPO), contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr), \
                mock.patch.object(gm, "execute", side_effect=NO_EXECUTE):
            code = gm.main(list(argv))
        return code, stdout.getvalue(), stderr.getvalue()

    def test_dry_run_prints_plan_and_creates_nothing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp, clean_tree():
            out = Path(tmp) / "run"
            code, stdout, stderr = self.run_main("--official", "--out", str(out), "--dry-run")
            self.assertEqual(gm.EXIT_PASS, code, stderr)
            self.assertFalse(out.exists())
            self.assertIn("공식", stdout.splitlines()[0])
            self.assertIn("scripts/gate1_judge.py --criteria config/simulator_gate1_acceptance.yaml", stdout)
            self.assertEqual(5 * 4 + 3, len([l for l in stdout.splitlines() if not l.startswith("#")]))

    def test_dirty_tree_refuses_before_anything_runs(self) -> None:
        dirty = {"head": "0" * 40, "porcelain": " M config/x.yaml\n", "clean": False}
        with tempfile.TemporaryDirectory() as tmp, mock.patch.object(gm, "git_state", return_value=dirty):
            out = Path(tmp) / "run"
            code, stdout, stderr = self.run_main("--official", "--out", str(out))
            self.assertEqual(gm.EXIT_INPUT_ERROR, code)
            self.assertEqual("", stdout)
            self.assertIn("작업 트리가 깨끗하지 않다", stderr)
            self.assertFalse(out.exists())

    def test_without_a_mode_nothing_runs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp, clean_tree():
            out = Path(tmp) / "run"
            for extra in ((), ("--dry-run",)):
                with self.subTest(extra=extra):
                    code, stdout, stderr = self.run_main("--out", str(out), *extra)
                    self.assertEqual(gm.EXIT_INPUT_ERROR, code)
                    self.assertEqual("", stdout)
                    self.assertIn("실행 방식을 고른다", stderr)
                    self.assertFalse(out.exists())

    def test_both_modes_is_a_command_line_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmp, contextlib.redirect_stderr(io.StringIO()) as err, \
                mock.patch.object(gm, "execute", side_effect=NO_EXECUTE):
            with self.assertRaises(SystemExit) as caught:
                gm.main(["--official", "--rehearsal-seeds", "42", "--out", str(Path(tmp) / "run")])
        self.assertEqual(2, caught.exception.code)
        self.assertIn("not allowed with argument", err.getvalue())


@unittest.skipUnless(FULL_RUNTIME, NEEDS_RUNTIME)
class TestRehearsalEndToEnd(unittest.TestCase):
    """보정 seed 42~46 · 고객 200명으로 실측 → 판정 → manifest 까지 실제로 돈다. 값 자체는 검증 대상이 아니다
    (작은 세계라 의미 없다) — 단계 연결 · 출력 경로 · 리허설 표시 · 종료 코드 규칙만 본다."""

    def test_full_rehearsal(self) -> None:
        with tempfile.TemporaryDirectory() as tmp, clean_tree(), \
                mock.patch.object(gm, "execute", side_effect=guarded_execute):
            out = Path(tmp) / "run"
            stdout, stderr = io.StringIO(), io.StringIO()
            with cwd(REPO), contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
                code = gm.main(["--out", str(out), "--rehearsal-seeds", "42", "43", "44", "45", "46",
                                "--rehearsal-customers", "200"])
            manifest = json.loads((out / gm.MANIFEST).read_text(encoding="utf-8"))
            self.assertTrue(manifest["steps_ok"], [s for s in manifest["steps"] if s["status"] != "ok"])
            self.assertEqual(20, len(manifest["steps"]))
            self.assertFalse(manifest["official"])
            self.assertFalse(manifest["tree_changed_during_run"])
            codes = {j["name"]: j["effective_exit_code"] for j in manifest["judges"]}
            self.assertEqual({"gate1_judge", "churn_threshold", "a_discount"}, set(codes))
            self.assertTrue(set(codes.values()) <= {0, 1}, (codes, stderr.getvalue()))
            self.assertEqual(gm.overall_exit(True, codes, False), code)
            self.assertEqual(code, manifest["exit_code"])
            self.assertTrue(manifest["valid"])
            self.assertEqual(codes["churn_threshold"] == 0, manifest["churn_met"])
            self.assertIsInstance(manifest["simulator_version"], str)
            for judge in manifest["judges"]:
                first = Path(judge["outputs"]["md"]).read_text(encoding="utf-8").splitlines()[0]
                self.assertTrue(first.startswith(f"# {gm.REHEARSAL_TITLE}"), first)
                report = json.loads(Path(judge["outputs"]["json"]).read_text(encoding="utf-8"))
                self.assertFalse(report["official"])
                self.assertTrue(report["criteria"]["version"].endswith(gm.REHEARSAL_VERSION_SUFFIX))
            summary = (out / gm.SUMMARY).read_text(encoding="utf-8")
            self.assertTrue(summary.startswith(f"# {gm.REHEARSAL_TITLE}"))
            self.assertEqual(summary, stdout.getvalue())
            self.assertNotIn(str(out), summary)
            copy = gm.gj.load_criteria(out / gm.REHEARSAL_CRITERIA)
            self.assertEqual(((42, 43, 44, 45, 46), 200), (copy.seeds, copy.customers))
            self.assertIn("met=", manifest["churn_evidence"])


if __name__ == "__main__":
    unittest.main()
