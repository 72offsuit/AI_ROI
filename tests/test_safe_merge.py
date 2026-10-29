"""`scripts/safe_merge.py` — 병합 전 안전장치가 실제로 막는지 (#172).

브랜치 보호를 못 켜는 저장소(private + Free)에서 병합을 막는 것은 이 스크립트 하나다.
그래서 "막아야 할 때 막는가" 를 사고 그대로의 모양으로 고정한다:

  - #141 의 실제 체크 상태(`Tests (with deps)` FAILURE · 리뷰 0건)를 넣으면 막는다
  - 아직 안 뜬 체크 · 진행 중 · SKIPPED 는 통과가 아니다
  - 승인은 작성자가 아닌 리뷰어의 **마지막 판정**으로 센다
  - 막히면 `gh pr merge` 를 **부르지 않는다** — 판정 함수가 맞아도 배선이 틀리면 소용없다
  - 필수 목록은 `pull_request` 이벤트의 필터로만 줄어든다 · 다른 워크플로우의 동명 체크가 필수
    체크를 대신하지 못한다 · 필수 목록이 비거나 못 읽으면 막는다 (PR #238 리뷰 R1~R3)
  - 우회 옵션이 생기지 않는다

`gh` 는 부르지 않는다 — `subprocess.run` 을 바꿔 끼워 PR JSON 을 주입한다.
"""

from __future__ import annotations

import importlib.util
import io
import json
import re
import subprocess
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest import mock

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPT = REPO_ROOT / "scripts" / "safe_merge.py"

_spec = importlib.util.spec_from_file_location("safe_merge", SCRIPT)
safe_merge = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(safe_merge)

HEAD = "16b2c404ea57b03c58e4d77981b31da0d2685722"
REQUIRED = [
    ("Tests", "격리 경계 + 전체 테스트"),
    ("Tests (with deps)", "의존성 설치 후 전체 테스트"),
]


def _run(workflow: str, name: str, conclusion: str | None = "SUCCESS", status: str = "COMPLETED") -> dict:
    return {"__typename": "CheckRun", "workflowName": workflow, "name": name,
            "status": status, "conclusion": conclusion}


def _review(login: str, state: str, at: str, commit: str = HEAD) -> dict:
    return {"author": {"login": login}, "state": state, "submittedAt": at, "commit": {"oid": commit}}


def _pr(**overrides) -> dict:
    base = {
        "number": 999, "title": "t", "url": "u", "state": "OPEN", "isDraft": False,
        "headRefOid": HEAD, "author": {"login": "Danto7632"}, "mergeable": "MERGEABLE",
        "statusCheckRollup": [_run(w, n) for w, n in REQUIRED],
        "reviews": [_review("kwung0206", "APPROVED", "2026-10-23T10:00:00Z")],
    }
    base.update(overrides)
    return base


class TestEvaluate(unittest.TestCase):
    def problems(self, pr: dict) -> list[str]:
        return safe_merge.evaluate(pr, REQUIRED)[1]

    def test_all_green_and_approved_passes(self) -> None:
        self.assertEqual([], self.problems(_pr()))

    def test_the_141_incident_is_blocked(self) -> None:
        """#141 이 병합될 때의 실제 상태 — 체크 하나 FAILURE, 리뷰 0건."""
        pr = _pr(
            statusCheckRollup=[_run("Tests", "격리 경계 + 전체 테스트"),
                               _run("Tests (with deps)", "의존성 설치 후 전체 테스트", "FAILURE")],
            reviews=[],
        )
        problems = self.problems(pr)
        self.assertTrue(any("FAILURE" in p for p in problems), problems)
        self.assertTrue(any("승인" in p for p in problems), problems)

    def test_a_check_that_has_not_appeared_yet_is_not_a_pass(self) -> None:
        """푸시 직후 — 보고된 것만 보면 전부 초록이다."""
        pr = _pr(statusCheckRollup=[_run("Tests", "격리 경계 + 전체 테스트")])
        self.assertTrue(any("보고되지 않았다" in p for p in self.problems(pr)))

    def test_no_checks_at_all_is_not_a_pass(self) -> None:
        problems = safe_merge.evaluate(_pr(statusCheckRollup=None), [])[1]
        self.assertTrue(any("0건" in p for p in problems), problems)

    def test_in_progress_skipped_and_neutral_are_not_passes(self) -> None:
        for status, conclusion in (("IN_PROGRESS", None), ("QUEUED", None),
                                   ("COMPLETED", "SKIPPED"), ("COMPLETED", "NEUTRAL"),
                                   ("COMPLETED", "CANCELLED")):
            with self.subTest(status=status, conclusion=conclusion):
                pr = _pr(statusCheckRollup=[_run("Tests", "격리 경계 + 전체 테스트"),
                                            _run("Tests (with deps)", "의존성 설치 후 전체 테스트",
                                                 conclusion, status)])
                self.assertTrue(self.problems(pr))

    def test_status_context_must_be_success(self) -> None:
        pending = {"__typename": "StatusContext", "context": "ext", "state": "PENDING"}
        pr = _pr(statusCheckRollup=[*_pr()["statusCheckRollup"], pending])
        self.assertTrue(any("PENDING" in p for p in self.problems(pr)))

    def test_comment_only_review_is_not_an_approval(self) -> None:
        pr = _pr(reviews=[_review("kwung0206", "COMMENTED", "2026-10-23T10:00:00Z")])
        self.assertTrue(any("승인" in p for p in self.problems(pr)))

    def test_authors_own_review_does_not_count(self) -> None:
        pr = _pr(reviews=[_review("Danto7632", "APPROVED", "2026-10-23T10:00:00Z")])
        self.assertTrue(any("승인" in p for p in self.problems(pr)))

    def test_latest_verdict_per_reviewer_wins(self) -> None:
        approved_then_changes = _pr(reviews=[
            _review("kwung0206", "APPROVED", "2026-10-23T10:00:00Z"),
            _review("kwung0206", "CHANGES_REQUESTED", "2026-10-23T11:00:00Z"),
        ])
        self.assertTrue(any("변경 요청" in p for p in self.problems(approved_then_changes)))
        changes_then_approved = _pr(reviews=[
            _review("kwung0206", "CHANGES_REQUESTED", "2026-10-23T10:00:00Z"),
            _review("kwung0206", "COMMENTED", "2026-10-23T10:30:00Z"),
            _review("kwung0206", "APPROVED", "2026-10-23T11:00:00Z"),
        ])
        self.assertEqual([], self.problems(changes_then_approved))

    def test_open_change_request_from_another_reviewer_blocks(self) -> None:
        pr = _pr(reviews=[_review("kwung0206", "APPROVED", "2026-10-23T10:00:00Z"),
                          _review("1anminJ", "CHANGES_REQUESTED", "2026-10-23T11:00:00Z")])
        self.assertTrue(any("1anminJ" in p for p in self.problems(pr)))

    def test_stale_approval_is_a_note_not_a_block(self) -> None:
        pr = _pr(reviews=[_review("kwung0206", "APPROVED", "2026-10-23T10:00:00Z", commit="a" * 40)])
        _, problems, notes = safe_merge.evaluate(pr, REQUIRED)
        self.assertEqual([], problems)
        self.assertTrue(any("aaaaaaa" in n for n in notes), notes)

    def test_same_job_name_from_another_workflow_does_not_stand_in(self) -> None:
        """R2 — 필수 잡이 미보고인데 다른 워크플로우 · 외부 상태에 같은 이름의 SUCCESS 가 있다."""
        job = "의존성 설치 후 전체 테스트"
        for stand_in in (_run("Other", job),
                         {"__typename": "StatusContext", "context": job, "state": "SUCCESS"}):
            with self.subTest(stand_in=stand_in.get("__typename")):
                pr = _pr(statusCheckRollup=[_run("Tests", "격리 경계 + 전체 테스트"), stand_in])
                self.assertTrue(any("보고되지 않았다" in p and job in p for p in self.problems(pr)),
                                self.problems(pr))

    def test_an_empty_required_list_blocks(self) -> None:
        """R3 — 보고된 체크가 전부 SUCCESS 이고 승인이 있어도, 무엇을 요구할지 모르면 막는다."""
        problems = safe_merge.evaluate(_pr(), [])[1]
        self.assertTrue(any("필수 체크 목록이 비어 있다" in p for p in problems), problems)

    def test_closed_draft_and_conflicting_are_blocked(self) -> None:
        for overrides in ({"state": "MERGED"}, {"state": "CLOSED"}, {"isDraft": True},
                          {"mergeable": "CONFLICTING"}):
            with self.subTest(**overrides):
                self.assertTrue(self.problems(_pr(**overrides)))


class TestRequiredChecksComeFromTheWorkflows(unittest.TestCase):
    def test_the_job_that_failed_in_141_is_required(self) -> None:
        """사고를 낸 잡이 필수 목록에서 빠지면 이 스크립트는 같은 사고를 다시 통과시킨다."""
        required = safe_merge.required_checks()
        self.assertIn(("Tests (with deps)", "의존성 설치 후 전체 테스트"), required)
        self.assertIn(("Tests", "격리 경계 + 전체 테스트"), required)

    def test_every_pull_request_workflow_is_required_or_excluded_with_a_reason(self) -> None:
        """PR 워크플로우는 필수이거나, 사유와 함께 뺀 것이거나 — 조용히 빠지는 것은 없다."""
        required = {w for w, _ in safe_merge.required_checks()}
        excluded = {w for w, _ in safe_merge.excluded_workflows()}
        files = [p for p in (REPO_ROOT / ".github" / "workflows").glob("*.yml")
                 if re.search(r"^\s*pull_request\s*:", p.read_text(encoding="utf-8"), re.M)]
        self.assertEqual(len(files), len(required | excluded),
                         f"워크플로우 {len(files)}개, 필수 {sorted(required)} · 제외 {sorted(excluded)}")

    def test_no_pull_request_workflow_is_excluded_today(self) -> None:
        """★ 제외가 생기면 그 워크플로우는 PR 에서 안 떠도 병합된다. 의도한 것이면 이 기대값과
        DR-172 를 함께 고친다 — 필수 목록이 줄어드는 것을 사람이 보게 한다."""
        self.assertEqual([], safe_merge.excluded_workflows())

    def test_a_push_only_path_filter_does_not_shrink_the_required_list(self) -> None:
        """R1 — 실제 워크플로우 사본의 `push:` 에만 `paths` 를 넣는다. 필수 목록이 그대로여야 한다."""
        import tempfile
        source = REPO_ROOT / ".github" / "workflows"
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            for path in source.glob("*.yml"):
                text = path.read_text(encoding="utf-8")
                if path.name == "tests-with-deps.yml":
                    patched = text.replace("  push:\n    branches: [main]\n",
                                           "  push:\n    branches: [main]\n    paths:\n      - src/**\n", 1)
                    self.assertNotEqual(text, patched, "사본에 push 필터를 넣지 못했다 — 대조군이 공허하다")
                    text = patched
                (d / path.name).write_text(text, encoding="utf-8")
            self.assertEqual(safe_merge.required_checks(), safe_merge.required_checks(d))
            self.assertEqual([], safe_merge.excluded_workflows(d))

    def test_parser_reads_job_names_and_skips_non_pr_or_path_filtered(self) -> None:
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            (d / "a.yml").write_text(
                "name: 'A'\n# pull_request 는 주석\non:\n  pull_request:\njobs:\n"
                "  one:\n    name: 첫 잡\n    steps:\n      - name: step\n  two:\n    runs-on: x\n",
                encoding="utf-8")
            (d / "b.yml").write_text("name: B\non:\n  push:\njobs:\n  x:\n    name: X\n", encoding="utf-8")
            (d / "c.yml").write_text(
                "name: C\non:\n  pull_request:\n    paths:\n      - src/**\njobs:\n  y:\n    name: Y\n",
                encoding="utf-8")
            (d / "d.yml").write_text("name: D\n# pull_request\non:\n  push:\njobs:\n  z:\n    name: Z\n",
                                     encoding="utf-8")
            (d / "e.yml").write_text(
                "name: E\non:\n  push:\n    paths-ignore: [docs/**]\n  pull_request:\n    branches: [main]\n"
                "jobs:\n  e:\n    name: 이 잡\n", encoding="utf-8")
            (d / "f.yml").write_text("name: F\non: [push, pull_request]\njobs:\n  f:\n    name: 인라인\n",
                                     encoding="utf-8")
            (d / "g.yml").write_text("name: G\non:\n  - push\n  - pull_request\njobs:\n  g:\n    name: 목록\n",
                                     encoding="utf-8")
            (d / "h.yml").write_text(
                "name: H\non:\n  pull_request:\n    paths-ignore:\n      - docs/**\njobs:\n  h:\n    name: H\n",
                encoding="utf-8")
            self.assertEqual([("A", "첫 잡"), ("A", "two"), ("E", "이 잡"), ("F", "인라인"), ("G", "목록")],
                             safe_merge.required_checks(d))
            self.assertEqual(["C", "H"], [w for w, _ in safe_merge.excluded_workflows(d)])

    def test_unreadable_definitions_raise_instead_of_shrinking(self) -> None:
        """R3 — 읽지 못한 것을 빈 목록으로 두면 필수 대조 없이 병합된다."""
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            with self.assertRaises(safe_merge.WorkflowError):
                safe_merge.required_checks(d)  # 워크플로우 없음 (sparse checkout · 스크립트만 복사)
            with self.assertRaises(safe_merge.WorkflowError):
                safe_merge.required_checks(d / "missing")
            for name, text in (
                    ("jobs-missing.yml", "name: J\non:\n  pull_request:\n"),
                    ("jobs-unreadable.yml", "name: J\non:\n  pull_request:\njobs:\n    deep:\n      name: x\n"),
                    ("inline-on.yml", "name: J\non: {pull_request: {paths: [src/**]}}\njobs:\n  j:\n    name: x\n"),
                    ("inline-event.yml", "name: J\non:\n  pull_request: {paths: [src/**]}\njobs:\n  j:\n    name: x\n")):
                with self.subTest(name=name):
                    for old in d.glob("*.yml"):
                        old.unlink()
                    (d / name).write_text(text, encoding="utf-8")
                    with self.assertRaises(safe_merge.WorkflowError):
                        safe_merge.required_checks(d)


class TestMainWiring(unittest.TestCase):
    """판정이 맞아도 배선이 틀리면 막지 못한다 — `gh pr merge` 호출 여부를 본다."""

    def _main(self, pr: dict, *argv: str) -> tuple[int, list[list[str]]]:
        calls: list[list[str]] = []

        def fake_run(cmd, *args, **kwargs):
            calls.append(list(cmd))
            if cmd[:3] == ["gh", "pr", "view"]:
                return subprocess.CompletedProcess(cmd, 0, stdout=json.dumps(pr), stderr="")
            return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

        with mock.patch.object(safe_merge.subprocess, "run", side_effect=fake_run), \
                mock.patch.object(safe_merge, "required_checks", return_value=REQUIRED), \
                redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            code = safe_merge.main([str(pr["number"]), *argv])
        return code, calls

    @staticmethod
    def _merges(calls: list[list[str]]) -> list[list[str]]:
        return [c for c in calls if c[:3] == ["gh", "pr", "merge"]]

    def test_blocked_pr_is_never_merged(self) -> None:
        code, calls = self._main(_pr(reviews=[]))
        self.assertEqual(1, code)
        self.assertEqual([], self._merges(calls))

    def test_dry_run_never_merges(self) -> None:
        code, calls = self._main(_pr(), "--dry-run")
        self.assertEqual(0, code)
        self.assertEqual([], self._merges(calls))

    def test_passing_pr_is_squash_merged_pinned_to_the_checked_head(self) -> None:
        code, calls = self._main(_pr())
        self.assertEqual(0, code)
        merges = self._merges(calls)
        self.assertEqual(1, len(merges))
        self.assertIn("--squash", merges[0])
        self.assertEqual(HEAD, merges[0][merges[0].index("--match-head-commit") + 1])
        self.assertNotIn("--admin", merges[0])

    def test_unreadable_or_empty_required_list_is_never_merged(self) -> None:
        """R3 — 배선까지: 목록을 못 읽으면 2, 빈 목록이면 1. 둘 다 `gh pr merge` 를 부르지 않는다."""
        for side_effect, expected in ((safe_merge.WorkflowError("없음"), 2), (None, 1)):
            with self.subTest(expected=expected):
                calls: list[list[str]] = []

                def fake_run(cmd, *args, **kwargs):
                    calls.append(list(cmd))
                    return subprocess.CompletedProcess(cmd, 0, stdout=json.dumps(_pr()), stderr="")

                with mock.patch.object(safe_merge.subprocess, "run", side_effect=fake_run), \
                        mock.patch.object(safe_merge, "required_checks", side_effect=side_effect,
                                          return_value=[]), \
                        redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
                    code = safe_merge.main(["999"])
                self.assertEqual(expected, code)
                self.assertEqual([], self._merges(calls))

    def test_gh_failure_is_blocked_not_passed(self) -> None:
        def failing(cmd, *args, **kwargs):
            return subprocess.CompletedProcess(cmd, 1, stdout="", stderr="boom")

        with mock.patch.object(safe_merge.subprocess, "run", side_effect=failing), \
                redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            self.assertEqual(2, safe_merge.main(["1"]))


class TestNoBypass(unittest.TestCase):
    def test_options_are_exactly_repo_and_dry_run(self) -> None:
        """★ 우회 옵션(`--admin` · `--force` · `--skip-*`)이 생기면 안전장치가 아니다."""
        options = {opt for action in safe_merge.build_parser()._actions for opt in action.option_strings}
        self.assertEqual({"-h", "--help", "--repo", "--dry-run"}, options)


if __name__ == "__main__":
    unittest.main()
