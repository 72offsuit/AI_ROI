"""#262 — 실행 기록(`run_meta.provenance`)이 시스템 쪽 커밋 전 변경을 남기는가, `--require-clean` 이 시작 전에 멈추는가.

예전 `provenance()` 는 실행이 **끝날 때** 한 번 쟀고 dirty 여부는 `src/simulator` 만 봤다. 그래서 #211 확인 실행
(`SP-20261103-114303-75f731f8`)은 커밋 전 #211 변경으로 돌았는데도 `repo_commit` 이 `02648e9` 로만 남았다.

시뮬레이터를 돌리지 않는다. 저장소 상태 · 출처 기록은 `src/orchestration/provenance.py`(표준 라이브러리만)에
있어 ML 의존성 없이 돈다(#264). `run()` · CLI 검사만 시뮬레이터 import 를 뺀 하네스(`_contract_runner`)로
`run_sprint` 를 불러온다. git 은 테스트마다 만드는 임시 저장소에서 돈다(`provenance.REPO_ROOT` 를 바꾼다).
"""

from __future__ import annotations

import ast
import importlib.util
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from src.measurement import config_loader as cl
from src.orchestration import provenance as pv

REPO_ROOT = Path(__file__).resolve().parents[1]
HAVE_ML = all(importlib.util.find_spec(m) is not None for m in ("numpy", "pandas", "sklearn", "scipy"))
HAVE_GIT = shutil.which("git") is not None
SKIP_REASON = "BLOCKED: numpy/pandas/scikit-learn/scipy · PyYAML · git 중 하나가 없어 run_sprint 를 불러올 수 없다"


def _git(root: Path, *args: str) -> str:
    command = ["git", "-c", "user.name=t", "-c", "user.email=t@example.invalid", "-c", "commit.gpgsign=false", *args]
    return subprocess.run(command, cwd=root, check=True, capture_output=True, text=True).stdout.strip()


class _TempRepo:
    """테스트마다 임시 git 저장소를 만들고 `provenance.REPO_ROOT` 를 그쪽으로 돌린다."""

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        base = Path(self.tmp.name)
        self.root = base / "repo"
        self.root.mkdir()
        # 임시 폴더 위쪽의 다른 저장소를 git 이 찾아 올라가지 않게 한다.
        env = mock.patch.dict(os.environ, {"GIT_CEILING_DIRECTORIES": str(base)})
        env.start()
        self.addCleanup(env.stop)
        _git(self.root, "init", "-q")
        (self.root / ".gitignore").write_text("results/\n", encoding="utf-8")
        (self.root / "config").mkdir()
        (self.root / "config" / "experiment_config.yaml").write_text("run: {}\n", encoding="utf-8")
        (self.root / "src" / "decision").mkdir(parents=True)
        (self.root / "src" / "decision" / "rule.py").write_text("X = 1\n", encoding="utf-8")
        _git(self.root, "add", ".")
        _git(self.root, "commit", "-q", "-m", "init")
        self.head = _git(self.root, "rev-parse", "HEAD")
        self.set_root(self.root)

    def set_root(self, root: Path) -> None:
        patcher = mock.patch.object(pv, "REPO_ROOT", root)
        patcher.start()
        self.addCleanup(patcher.stop)

    def write(self, relative: str, text: str = "x\n") -> None:
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")


@unittest.skipUnless(HAVE_GIT, "BLOCKED: git 이 없다")
class TestRepoProvenance(_TempRepo, unittest.TestCase):
    """저장소 상태 · `--require-clean` 검사 · 출처 기록. ML · PyYAML 없이 돈다(#264)."""

    # ── repo_state ──────────────────────────────────────────────────────────

    def test_clean_repo(self) -> None:
        state = pv.repo_state()
        self.assertEqual((self.head, False, []), (state["head"], state["dirty"], state["paths"]))
        self.assertFalse(state["simulator_dirty"])
        self.assertEqual({"experiment_config.yaml"}, set(state["config_sha256"]))
        pv.check_clean(state)  # 던지지 않는다

    def test_tracked_untracked_and_staged_changes_are_listed_ignored_files_are_not(self) -> None:
        self.write("src/decision/rule.py", "X = 2\n")             # 추적 파일 수정
        self.write("src/decision/새 규칙.py")                      # .gitignore 밖 새 파일 — 공백 · 한글 이름
        self.write("src/orchestration/staged.py")
        _git(self.root, "add", "src/orchestration/staged.py")     # 스테이징만 한 새 파일
        self.write("results/sprint-v0/run_meta.json")             # .gitignore — 실행 산출물
        state = pv.repo_state()
        self.assertTrue(state["dirty"])
        self.assertEqual(
            ["src/decision/rule.py", "src/decision/새 규칙.py", "src/orchestration/staged.py"], state["paths"]
        )
        self.assertFalse(state["simulator_dirty"])

    def test_rename_lists_both_paths(self) -> None:
        _git(self.root, "mv", "src/decision/rule.py", "src/decision/rule2.py")
        self.assertEqual(["src/decision/rule.py", "src/decision/rule2.py"], pv.repo_state()["paths"])

    def test_simulator_flag_is_derived_from_the_same_paths(self) -> None:
        self.write("src/simulator/new_module.py")
        state = pv.repo_state()
        self.assertTrue(state["simulator_dirty"])
        self.assertEqual(["src/simulator/new_module.py"], state["paths"])

    def test_without_git_nothing_is_assumed_clean(self) -> None:
        plain = Path(self.tmp.name) / "plain"
        (plain / "config").mkdir(parents=True)
        self.set_root(plain)
        state = pv.repo_state()
        self.assertEqual((None, None, None, None), (state["head"], state["dirty"], state["paths"], state["simulator_dirty"]))
        with self.assertRaisesRegex(pv.DirtyRepoError, "읽지 못했다"):
            pv.check_clean(state)
        record = pv.provenance(state)
        self.assertIsNone(record["repo_worktree_dirty"])
        self.assertIsNone(record["repo_changed_during_run"])
        self.assertIn("null_reason", record)

    # ── check_clean ─────────────────────────────────────────────────────────

    def test_check_clean_refuses_and_names_the_paths(self) -> None:
        self.write("src/decision/rule.py", "X = 2\n")
        with self.assertRaises(pv.DirtyRepoError) as caught:
            pv.check_clean(pv.repo_state())
        self.assertIn("src/decision/rule.py", str(caught.exception))
        self.assertEqual(4, caught.exception.exit_code)

    # ── provenance ──────────────────────────────────────────────────────────

    def test_records_start_state_even_if_head_and_config_change_during_run(self) -> None:
        start = pv.repo_state()
        self.write("src/decision/rule.py", "X = 2\n")
        _git(self.root, "commit", "-q", "-am", "실행 중 커밋")
        self.write("config/experiment_config.yaml", "run: {num_customers: 1}\n")
        record = pv.provenance(start, require_clean=True)
        self.assertEqual(self.head, record["repo_commit"], "실행 중 커밋이 이 실행의 커밋으로 적혔다")
        self.assertFalse(record["repo_worktree_dirty"])
        self.assertEqual(start["config_sha256"], record["config_sha256"])
        self.assertTrue(record["require_clean"])
        self.assertTrue(record["repo_changed_during_run"])
        changes = "\n".join(record["repo_changes_during_run"])
        self.assertIn(f"HEAD {self.head[:7]}", changes)
        self.assertIn("config/experiment_config.yaml", changes)
        self.assertIn("생겼다", changes)
        self.assertNotIn("null_reason", record)

    def test_dirty_run_is_recorded_and_unchanged_run_says_so(self) -> None:
        self.write("src/decision/rule.py", "X = 2\n")
        start = pv.repo_state()
        record = pv.provenance(start)
        self.assertEqual(self.head, record["repo_commit"])
        self.assertTrue(record["repo_worktree_dirty"])
        self.assertEqual(["src/decision/rule.py"], record["repo_dirty_paths"])
        self.assertEqual(1, record["repo_dirty_path_count"])
        self.assertFalse(record["require_clean"])
        self.assertEqual((False, []), (record["repo_changed_during_run"], record["repo_changes_during_run"]))

    def test_path_list_is_capped_but_count_is_not(self) -> None:
        for i in range(5):
            self.write(f"src/decision/new_{i}.py")
        with mock.patch.object(pv, "DIRTY_PATHS_LIMIT", 3):
            record = pv.provenance(pv.repo_state())
        self.assertEqual(["src/decision/new_0.py", "src/decision/new_1.py", "src/decision/new_2.py"],
                         record["repo_dirty_paths"])
        self.assertEqual(5, record["repo_dirty_path_count"])


class TestGitOutputIsReadAsUtf8Bytes(unittest.TestCase):
    """#264 — git 출력을 로캘 텍스트로 읽지 않는다. git 이 없어도 돈다(출력을 대역으로 준다).

    예전 `_git` 은 `text=True` 였다. CP949 로캘의 한글 경로 · 비 UTF-8 바이트 경로에서 `UnicodeDecodeError` 가
    그대로 올라가 시작 검사가 기록 / 종료 4 로 가지 못했고, 끝의 `provenance()` 가 `finally` 안이라 결과 쓰기까지
    막았다. 이름 속 CR 은 줄바꿈 변환으로 LF 가 되어 기록됐다(PR #263 리뷰 재현).
    """

    HEAD = "0123456789abcdef0123456789abcdef01234567"

    def fake_git(self, status: bytes):
        def run(command, **kwargs):
            args = command[1:]
            out = status if args[:1] == ["status"] else f"{self.HEAD}\n".encode()
            return subprocess.CompletedProcess(command, 0, stdout=out, stderr=b"")
        return run

    def state_with(self, status: bytes) -> dict:
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "config").mkdir()
            with mock.patch.object(pv, "REPO_ROOT", Path(tmp)), \
                    mock.patch.object(pv.subprocess, "run", side_effect=self.fake_git(status)):
                return pv.repo_state()

    def test_git_is_called_in_bytes_mode(self) -> None:
        with mock.patch.object(pv.subprocess, "run", side_effect=self.fake_git(b"")) as run:
            pv._git("status", "--porcelain=v1", "-z", strip=False)
        kwargs = run.call_args.kwargs
        for text_option in ("text", "encoding", "errors", "universal_newlines"):
            self.assertNotIn(text_option, kwargs, f"{text_option} 를 넘기면 로캘 · 줄바꿈 변환이 다시 들어온다")

    def test_undecodable_path_is_unknown_not_an_exception(self) -> None:
        state = self.state_with(b"?? src/decision/\xff\xfe.py\0")
        self.assertEqual((None, None, None), (state["dirty"], state["paths"], state["simulator_dirty"]))
        with self.assertRaisesRegex(pv.DirtyRepoError, "읽지 못했다") as caught:
            pv.check_clean(state)                           # --require-clean → 시작 전 종료 4
        self.assertEqual(4, caught.exception.exit_code)
        with mock.patch.object(pv.subprocess, "run", side_effect=self.fake_git(b"?? src/decision/\xff\xfe.py\0")):
            record = pv.provenance(state)                   # 기본 실행 → 기록은 남고 사유가 붙는다
        self.assertIsNone(record["repo_worktree_dirty"])
        self.assertIn("null_reason", record)

    def test_carriage_return_in_a_name_is_kept(self) -> None:
        state = self.state_with(b"?? src/decision/a\rb.py\0")
        self.assertEqual(["src/decision/a\rb.py"], state["paths"])

    def test_utf8_korean_path_is_read_whatever_the_locale(self) -> None:
        name = "src/decision/새 규칙.py"
        state = self.state_with(b"?? " + name.encode("utf-8") + b"\0")
        self.assertEqual([name], state["paths"])
        self.assertEqual(self.HEAD, state["head"])


@unittest.skipUnless(HAVE_ML and HAVE_GIT and cl.yaml_available(), SKIP_REASON)
class TestRunProvenance(_TempRepo, unittest.TestCase):
    """`run()` 과 `run_sprint` CLI 가 시뮬레이션 전에 멈추는가 — 실행 루프를 불러와야 해서 의존성이 든다."""

    @classmethod
    def setUpClass(cls) -> None:
        from tests.test_feature_sprint_table import _contract_runner

        cls.rs = _contract_runner()

    @classmethod
    def tearDownClass(cls) -> None:
        sys.modules.pop(cls.rs.__name__, None)

    def setUp(self) -> None:
        super().setUp()
        patcher = mock.patch.object(self.rs, "REPO_ROOT", self.root)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_run_sprint_uses_the_provenance_module(self) -> None:
        # 하네스가 불러온 run_sprint 와 이 파일이 같은 함수를 본다 — 위 순수 검사가 실행 루프의 검사다.
        self.assertIs(pv.repo_state, self.rs.repo_state)
        self.assertIs(pv.DirtyRepoError, self.rs.DirtyRepoError)

    def test_run_refuses_before_simulating(self) -> None:
        self.write("src/decision/rule.py", "X = 2\n")
        out, results = Path(self.tmp.name) / "out", Path(self.tmp.name) / "results"
        config = self.rs.SprintConfig(seed=1, num_customers=10, profile="smoke", out=out, results_root=results,
                                      require_clean=True)
        with self.assertRaises(self.rs.DirtyRepoError):
            self.rs.run(config)
        self.assertFalse(out.exists() or results.exists(), "멈춘 실행이 출력 폴더를 만들었다")

    def test_run_sprint_cli_flag_and_exit_code(self) -> None:
        self.assertFalse(self.rs.build_parser().parse_args(["--out", "x"]).require_clean)
        self.write("src/decision/rule.py", "X = 2\n")
        results = Path(self.tmp.name) / "results"
        with mock.patch("sys.stderr"), mock.patch("sys.stdout"):
            code = self.rs.main(["--out", str(Path(self.tmp.name) / "out"), "--results-root", str(results),
                                 "--require-clean"])
        self.assertEqual(4, code)
        self.assertFalse(results.exists())


class TestMainCliPassesTheFlag(unittest.TestCase):
    """`src/main.py` 도 같은 옵션을 받아 실행 루프로 넘긴다. 실제 실행 루프는 불러오지 않는다(시뮬레이터 import)."""

    def test_parser_accepts_flag(self) -> None:
        from src import main as cli

        self.assertFalse(cli.build_parser().parse_args(["--mode", "full"]).require_clean)
        self.assertTrue(cli.build_parser().parse_args(["--mode", "full", "--require-clean"]).require_clean)

    def test_main_passes_flag_to_sprint_config(self) -> None:
        tree = ast.parse((REPO_ROOT / "src" / "main.py").read_text(encoding="utf-8"))
        calls = [n for n in ast.walk(tree) if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
                 and n.func.attr == "SprintConfig"]
        self.assertEqual(1, len(calls))
        keywords = {k.arg: ast.unparse(k.value) for k in calls[0].keywords}
        self.assertEqual("args.require_clean", keywords.get("require_clean"))


if __name__ == "__main__":
    unittest.main()
