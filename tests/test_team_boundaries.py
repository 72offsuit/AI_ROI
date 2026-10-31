"""Enforces the C2 team boundary that `docs/team_boundaries.json` declares.

Two teams work in one repository and must not read each other's files. The
simulator team knows the answers (Hidden Trait, Potential Outcome, true CATE); the
system team has to infer them from behaviour alone. A boundary that exists only in
prose is the failure this cycle kept finding -- a declaration nobody compares
against reality. So the declaration is machine-readable and this file reads it.

What is checked here, and what is not:

  checked    the declaration is internally consistent -- no path claimed by two
             teams, no empty team, every member listed once, task prefixes distinct
  checked    a working branch does not straddle both teams (`test_branch_stays_…`).
             That is the practical guard: a PR touching `src/simulator/` and
             `src/decision/` together means someone crossed.
  NOT        whether a person *read* a file. Nothing here can see that. Reading is
             held by `src/*/AGENTS.md` and by the review that follows -- and the
             most dangerous leak was never a read anyway, it is tuning the
             simulator after seeing model results (PRD §80 Risk 1).

`tests/test_isolation.py` remains the import- and data-path guard. This file is
about **who edits what**, that one is about **what the code may touch**. Neither
replaces the other.
"""

from __future__ import annotations

import fnmatch
import json
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

REPO_ROOT = Path(__file__).resolve().parent.parent
BOUNDARIES = REPO_ROOT / "docs" / "team_boundaries.json"


def _load() -> dict:
    return json.loads(BOUNDARIES.read_text(encoding="utf-8"))


def _team_of(path: str, owned: dict[str, list[str]]) -> str | None:
    """Which team owns this path, or None when nobody claims it."""
    for team, patterns in owned.items():
        if any(fnmatch.fnmatch(path, pattern) for pattern in patterns):
            return team
    return None


def _in_ci() -> bool:
    """GitHub Actions 는 모든 잡에 `GITHUB_ACTIONS=true` 를 준다 — 워크플로가 따로 켜지 않아도 된다."""
    return os.environ.get("GITHUB_ACTIONS") == "true"


class TestDeclarationIsConsistent(unittest.TestCase):
    """선언 자체가 앞뒤가 맞는가."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.data = _load()

    def test_file_exists_and_parses(self) -> None:
        self.assertTrue(BOUNDARIES.is_file(), f"{BOUNDARIES} 가 없다")

    def test_two_teams_with_members(self) -> None:
        teams = self.data["teams"]
        self.assertEqual({"sim", "sys"}, set(teams))
        for name, team in teams.items():
            with self.subTest(team=name):
                self.assertTrue(team["members"], f"{name}: 구성원이 비어 있다")

    def test_nobody_is_on_both_teams(self) -> None:
        """한 사람이 양쪽에 있으면 경계가 그 사람 안에서 무너진다."""
        sim = set(self.data["teams"]["sim"]["members"])
        sys_ = set(self.data["teams"]["sys"]["members"])
        self.assertEqual(
            set(), sim & sys_,
            "양 팀에 동시에 속한 구성원이 있다 — 그 사람은 양쪽을 다 보게 된다",
        )

    def test_task_prefixes_are_distinct(self) -> None:
        """태스크 번호만 보고 어느 팀 일인지 알 수 있어야 한다."""
        prefixes = [team["task_prefix"] for team in self.data["teams"].values()]
        self.assertEqual(len(prefixes), len(set(prefixes)))

    def test_no_path_is_claimed_by_both_teams(self) -> None:
        """겹치는 경로가 있으면 그 파일에서 두 팀이 만난다."""
        owned = self.data["owned"]
        collisions = [
            (a, b)
            for a in owned["sim"]
            for b in owned["sys"]
            if a == b or fnmatch.fnmatch(a.rstrip("*"), b) or fnmatch.fnmatch(b.rstrip("*"), a)
        ]
        self.assertEqual([], collisions, f"두 팀이 같은 경로를 주장한다: {collisions}")

    def test_shared_paths_are_not_owned_by_a_team(self) -> None:
        """공용 계약을 한 팀이 소유하면 그 팀이 계약을 바꿀 수 있다."""
        owned = self.data["owned"]
        conflicts = [
            shared
            for shared in self.data["shared_read_only"]["paths"]
            if _team_of(shared, owned) is not None
        ]
        self.assertEqual(
            [], conflicts,
            f"공용(읽기 전용) 경로를 팀이 소유하고 있다: {conflicts}",
        )

    def test_every_rule_carries_a_reason(self) -> None:
        """사유 없는 금지는 다음 사람이 지운다."""
        for name, team in self.data["teams"].items():
            with self.subTest(team=name):
                self.assertTrue(team["must_not_read"], f"{name}: 금지 경로가 비어 있다")
                self.assertTrue(
                    team["must_not_read_why"].strip(), f"{name}: 왜 금지인지가 비어 있다"
                )
        for key in ("shared_read_only", "lead_only"):
            with self.subTest(section=key):
                self.assertTrue(self.data[key]["why"].strip())


class TestForbiddenPathsAreTheOtherTeamsOrAnswers(unittest.TestCase):
    """금지 목록이 실제 경계와 어긋나지 않는가."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.data = _load()

    def test_sim_is_blocked_from_decision_output(self) -> None:
        forbidden = self.data["teams"]["sim"]["must_not_read"]
        self.assertIn("results/**", forbidden, "시뮬레이터가 모델 결과를 보면 튜닝 유혹이 생긴다")
        self.assertIn("src/decision/**", forbidden)

    def test_sys_is_blocked_from_the_answers(self) -> None:
        forbidden = self.data["teams"]["sys"]["must_not_read"]
        for answer in ("data/hidden/**", "data/ground_truth/**", "src/simulator/**"):
            with self.subTest(path=answer):
                self.assertIn(answer, forbidden)

    def test_diagnostics_is_not_readable_by_the_system_team(self) -> None:
        """채점자는 정답지를 읽는다. 수험생이 채점자를 읽으면 같은 누수다.

        `src/diagnostics/` 는 시뮬 팀 소유이며 **두 GATE 가 닫힌 뒤에만** 착수한다
        (사용자 결정). 그 시점에는 시뮬레이터도 전략도 바꿀 수 없으므로, 채점자가
        양쪽을 보아도 손댈 것이 없다.
        """
        self.assertIn("src/diagnostics/**", self.data["teams"]["sys"]["must_not_read"])
        self.assertIn("src/diagnostics/**", self.data["owned"]["sim"])


class TestBlockedIsAFailureInCI(unittest.TestCase):
    """★ #241 — 경계를 대조하지 못하면 로컬에서는 skip, CI 에서는 **실패**다.

    CI 체크아웃이 얕아(`fetch-depth: 1`) PR 실행에 main 이 없던 동안, 아래 경계 검사는
    모든 PR 에서 BLOCKED skip 이었고 skip 은 초록이라 아무도 몰랐다. 이제 CI 는 main 을
    받으므로 거기서도 못 구했다면 설정이 깨진 것이다. 로컬은 git 이 없거나 main 을
    받지 않은 체크아웃이 정상적으로 있으니 skip 으로 둔다. 두 방향을 다 본다.
    """

    @staticmethod
    def _run_blocked(github_actions: str | None) -> unittest.TestResult:
        case = TestBranchStaysInsideOneTeam("test_branch_stays_inside_one_team")
        result = unittest.TestResult()
        with mock.patch.object(
            TestBranchStaysInsideOneTeam, "_changed_files", return_value=None
        ), mock.patch.dict(os.environ):
            os.environ.pop("GITHUB_ACTIONS", None)
            if github_actions is not None:
                os.environ["GITHUB_ACTIONS"] = github_actions
            case.run(result)
        return result

    def test_ci_turns_blocked_into_a_failure(self) -> None:
        result = self._run_blocked("true")
        self.assertEqual(0, len(result.skipped), "CI 에서 대조 못 한 경계 검사가 또 skip 됐다")
        self.assertEqual(1, len(result.failures))
        self.assertIn("#241", result.failures[0][1])

    def test_local_keeps_it_a_skip(self) -> None:
        result = self._run_blocked(None)
        self.assertEqual(0, len(result.failures))
        self.assertEqual(1, len(result.skipped))
        self.assertIn("BLOCKED", result.skipped[0][1])


class TestBranchStaysInsideOneTeam(unittest.TestCase):
    """★ 실질 가드 — 한 브랜치가 두 팀 경로를 동시에 건드리지 않는다.

    읽기는 막을 수 없지만 **쓰기는 보인다.** 두 팀 경로가 한 PR 에 섞였다면
    누군가 경계를 넘었다는 뜻이고, 그것은 리뷰 전에 잡혀야 한다.
    """

    @classmethod
    def setUpClass(cls) -> None:
        cls.data = _load()

    @staticmethod
    def _run(*args: str, root: Path = REPO_ROOT) -> str | None:
        # git 실행 파일이 아예 없으면(예: python:3.10-slim 컨테이너) FileNotFoundError 가
        # 나서 skip 이 아니라 ERROR 가 됐다 — 아래 docstring 의 "git 을 못 쓰면 None" 과
        # 어긋났다(#172 작업 중 발견, PR 본문에 기록).
        try:
            result = subprocess.run(
                ["git", *args], cwd=root, capture_output=True, text=True
            )
        except FileNotFoundError:
            return None
        return result.stdout if result.returncode == 0 else None

    @classmethod
    def _changed_files(cls, root: Path = REPO_ROOT) -> list[str] | None:
        """`main` 대비 변경 파일 — **커밋된 것 + 아직 커밋하지 않은 것 전부.**

        ★ 처음에는 `git diff base...HEAD` 만 보았고, 그것은 커밋된 변경만 센다.
          두 팀 경로를 동시에 `git add` 한 상태를 만들어 보니 **통과했다** —
          커밋 전에는 아무것도 잡지 못하는 가드였다. 로컬에서 돌려 경계를 넘었는지
          확인하는 것이 이 검사의 주 용도이므로, 그 시점에 못 잡으면 쓸모가 없다.

        git 을 못 쓰면 `None` 을 돌려주고 호출자가 skip 한다 — 대조하지 않은 것을
        통과로 적지 않는다.

        ★ `--ignore-submodules=dirty` (#172). git worktree 에 본 체크아웃의 `Plan/` 을
          복사하면 `Plan/.git` 의 상대 경로(`gitdir: ../.git/modules/Plan`)가 worktree 의
          `.git` **파일** 아래를 가리켜 깨지고, 기본 `git status` 는 서브모듈 안을 들여다보다
          `fatal`(128)로 죽는다. 그러면 이 검사는 BLOCKED skip 이 되어 **팀 경계를 한 번도
          대조하지 않은 채** 초록으로 끝났다 — 에이전트마다 `submodule.Plan.ignore=all` 을
          환경변수로 주고 돌린 이유다. `Plan/**` 은 어느 팀 소유도 아니므로(공용 읽기 전용)
          서브모듈 *안의* 변경은 이 판정에 들어갈 자리가 없다. `dirty` 는 그 안만 보지 않고
          포인터 이동은 여전히 보이게 두는 가장 좁은 단계다(`all` 은 포인터까지 숨긴다).
          `TestBoundaryCheckSurvivesBrokenSubmoduleGitdir` 가 깨진 gitdir 을 실제로 만들어 고정한다.
        """
        committed: list[str] = []
        for base in ("origin/main", "main"):
            output = cls._run("diff", "--name-only", f"{base}...HEAD", root=root)
            if output is not None:
                committed = [line for line in output.splitlines() if line.strip()]
                break
        else:
            return None

        # 인덱스와 작업 트리 — porcelain 의 경로는 3열부터, 이름 변경은 ` -> ` 뒤가 현재 이름.
        status = cls._run("status", "--porcelain", "--ignore-submodules=dirty", root=root)
        if status is None:
            return None
        pending = []
        for line in status.splitlines():
            if not line.strip():
                continue
            path = line[3:].strip()
            if " -> " in path:
                path = path.split(" -> ", 1)[1]
            pending.append(path.strip('"'))
        return sorted(set(committed) | set(pending))

    def test_branch_stays_inside_one_team(self) -> None:
        changed = self._changed_files()
        if changed is None:
            reason = (
                "BLOCKED: git 으로 main 대비 변경 목록을 얻지 못했다 — 팀 경계를 "
                "대조하지 않았다 (통과가 아니다)"
            )
            if _in_ci():
                self.fail(reason + " — CI 는 main 을 받으므로 이것은 설정 결함이다 (#241)")
            self.skipTest(reason)
        owned = self.data["owned"]
        touched = {
            team
            for team in (_team_of(path, owned) for path in changed)
            if team is not None
        }
        self.assertLessEqual(
            len(touched), 1,
            f"한 브랜치가 두 팀의 경로를 동시에 건드렸다: {sorted(touched)}\n"
            "변경 파일:\n  " + "\n  ".join(
                f"{path}  → {_team_of(path, owned)}"
                for path in changed
                if _team_of(path, owned) is not None
            ) + "\n두 팀에 걸치는 작업이 필요하면 브랜치를 나누고, 공용 계약 변경이면 "
            "양 팀 합의를 거친다.",
        )


class TestBoundaryCheckSurvivesBrokenSubmoduleGitdir(unittest.TestCase):
    """★ #172 — 깨진 `Plan` gitdir 이 경계 검사를 BLOCKED 로 만들지 않는다.

    worktree 에 본 체크아웃의 `Plan/` 을 복사하면 `Plan/.git` 이 존재하지 않는
    `../.git/modules/Plan` 을 가리킨다. 그 상태를 임시 저장소에 **실제로 만들고**
    두 방향을 본다 — ① 대조군: 기본 `git status` 가 정말 죽는다(재현이 살아 있다)
    ② `_changed_files()` 는 그래도 변경 목록을 낸다. ①이 없으면 ②의 통과는
    재현이 사라져서인지 고쳐서인지 구분되지 않는다.

    `GIT_*` 환경변수는 지운다. 우회(`GIT_CONFIG_* … submodule.Plan.ignore=all`)를 준
    채로 스위트를 돌리면 대조군이 거짓으로 통과하기 때문이다.
    """

    def setUp(self) -> None:
        if shutil.which("git") is None:
            self.skipTest("BLOCKED: git 이 없다 — 깨진 서브모듈 재현을 만들지 못했다 (통과가 아니다)")
        clean_env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
        patcher = mock.patch.dict(os.environ, clean_env, clear=True)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.root = Path(tempfile.mkdtemp(prefix="airoi-broken-submodule-"))
        self.addCleanup(shutil.rmtree, self.root, ignore_errors=True)

        def git(*args: str) -> str:
            return subprocess.run(
                ["git", "-c", "user.name=t", "-c", "user.email=t@example.invalid",
                 "-c", "commit.gpgsign=false", *args],
                cwd=self.root, capture_output=True, text=True, check=True,
            ).stdout.strip()

        git("init", "-q")
        git("symbolic-ref", "HEAD", "refs/heads/main")
        (self.root / "README.md").write_text("x\n", encoding="utf-8")
        git("add", "README.md")
        git("commit", "-q", "-m", "init")
        sha = git("rev-parse", "HEAD")
        (self.root / ".gitmodules").write_text(
            '[submodule "Plan"]\n\tpath = Plan\n\turl = https://example.invalid/Plan.git\n',
            encoding="utf-8",
        )
        git("add", ".gitmodules")
        git("update-index", "--add", "--cacheinfo", f"160000,{sha},Plan")
        git("commit", "-q", "-m", "plan submodule")
        (self.root / "Plan").mkdir()
        # 본 체크아웃에서 복사해 온 gitfile 그대로 — 여기서는 가리키는 곳이 없다.
        (self.root / "Plan" / ".git").write_text("gitdir: ../.git/modules/Plan\n", encoding="utf-8")

    def test_plain_status_really_breaks_here(self) -> None:
        """대조군 — 재현이 사라지면 아래 검사는 아무것도 증명하지 않는다."""
        result = subprocess.run(
            ["git", "status", "--porcelain"], cwd=self.root, capture_output=True, text=True
        )
        self.assertNotEqual(
            0, result.returncode,
            "깨진 Plan gitdir 에서 기본 git status 가 성공했다 — 재현 픽스처가 더는 "
            "#172 의 상태를 만들지 못한다",
        )

    def test_changed_files_still_lists_pending_changes(self) -> None:
        (self.root / "src" / "decision").mkdir(parents=True)
        (self.root / "src" / "decision" / "x.py").write_text("", encoding="utf-8")
        changed = TestBranchStaysInsideOneTeam._changed_files(self.root)
        self.assertIsNotNone(
            changed, "깨진 Plan gitdir 때문에 변경 목록을 얻지 못했다 — 경계 검사가 BLOCKED 로 빠진다"
        )
        self.assertTrue(
            any(path.startswith("src/") for path in changed or []),
            f"작업 트리의 새 파일이 변경 목록에 없다: {changed}",
        )
