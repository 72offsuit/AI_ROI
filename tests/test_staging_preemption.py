"""Holds the staging hijack closed (issue #65, security finding F3, CVSS 5.1).

The staging directory is `results.staging` -- **fully predictable**, so it can be
created before a publish run. The previous code let that through:

  `shutil.rmtree(..., ignore_errors=True)` does nothing to a symlink (rmtree
  refuses links, and the error was swallowed), and `mkdir(exist_ok=True)` succeeds
  because the link's target exists. The link survived `_reset()` untouched.

Two things then went wrong, and the second is the worse one:

  1. everything the publish run wrote landed in the attacker's directory
  2. the promotion loop walks `staging.rglob("*.json")`, so **any `.json` the
     attacker had planted there was moved into `results/`** -- arbitrary content
     promoted into the directory the dashboard reads

★ Every case here is built on disk and run. Asserting that `_reset` contains the
  word `is_symlink` would pass even with the check in a place it cannot fire.

★ The predictable name is kept on purpose, and `test_refusal_is_loud` pins why:
  refusing leaves a denial of service, but an attacker who can plant that link can
  already delete or overwrite `results/` -- that is not a new capability. Silent
  content substitution was. A loud refusal is the better trade, and a randomised
  name would accumulate leftover staging directories, which the failure path
  deliberately preserves for debugging.
"""

from __future__ import annotations

import pathlib
import tempfile
import unittest

from src.measurement import publish
from src.measurement.errors import PublishError


class TestStagingRefusesAPreemptedPath(unittest.TestCase):
    """선점된 staging 을 만나면 조용히 쓰지 않고 멈춘다."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = pathlib.Path(self._tmp.name)
        self.out = self.root / "results"
        self.attacker = self.root / "attacker"
        self.attacker.mkdir()
        self.staging = self.out.with_name(self.out.name + publish.STAGING_SUFFIX)
        self.staging.parent.mkdir(parents=True, exist_ok=True)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_symlink_to_directory_is_refused(self) -> None:
        """★ 재현했던 바로 그 경로."""
        self.staging.symlink_to(self.attacker, target_is_directory=True)
        with self.assertRaises(PublishError) as caught:
            publish._reset(self.staging)
        self.assertIn("심볼릭 링크", str(caught.exception))

    def test_attacker_files_survive_the_refusal(self) -> None:
        """거부가 공격자 디렉터리를 지우지 않는다.

        `rmtree` 를 그냥 돌리면 링크를 따라가 남의 디렉터리를 지울 수 있다 —
        방어가 파괴적이 되면 그것대로 결함이다.
        """
        planted = self.attacker / "planted.json"
        planted.write_text('{"ATTACKER":"file"}', encoding="utf-8")
        self.staging.symlink_to(self.attacker, target_is_directory=True)
        with self.assertRaises(PublishError):
            publish._reset(self.staging)
        self.assertTrue(planted.exists(), "거부하면서 링크 너머를 지웠다")

    def test_symlink_to_file_is_refused(self) -> None:
        """디렉터리가 아니어도 링크는 링크다."""
        decoy = self.root / "decoy.json"
        decoy.write_text("{}", encoding="utf-8")
        self.staging.symlink_to(decoy)
        with self.assertRaises(PublishError):
            publish._reset(self.staging)

    def test_broken_symlink_is_refused(self) -> None:
        """가리키는 곳이 없어도 거부한다 — 나중에 만들어 둘 수 있다."""
        self.staging.symlink_to(self.root / "does-not-exist")
        with self.assertRaises(PublishError):
            publish._reset(self.staging)

    def test_error_names_the_target(self) -> None:
        """무엇을 가리키는지 말하지 않으면 읽는 사람이 원인을 못 찾는다."""
        self.staging.symlink_to(self.attacker, target_is_directory=True)
        with self.assertRaises(PublishError) as caught:
            publish._reset(self.staging)
        self.assertIn("attacker", str(caught.exception))

    def test_refusal_is_loud(self) -> None:
        """★ 거부는 예외다. 조용히 건너뛰면 이전과 같은 상태가 된다.

        `PublishError` 는 `MeasurementError` 계열이므로 `main()` 의 핸들러가
        종료 코드로 옮긴다 — 처리되지 않은 트레이스백으로 끝나지 않는다.
        """
        from src.measurement.errors import MeasurementError

        self.staging.symlink_to(self.attacker, target_is_directory=True)
        with self.assertRaises(MeasurementError):
            publish._reset(self.staging)


class TestNormalStagingStillWorks(unittest.TestCase):
    """★ 거짓 양성 — 방어가 정상 게시를 막으면 그것도 결함이다."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.staging = pathlib.Path(self._tmp.name) / "results.staging"

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_creates_when_absent(self) -> None:
        publish._reset(self.staging)
        self.assertTrue(self.staging.is_dir())
        self.assertFalse(self.staging.is_symlink())

    def test_empties_an_existing_directory(self) -> None:
        publish._reset(self.staging)
        (self.staging / "stale.json").write_text("{}", encoding="utf-8")
        publish._reset(self.staging)
        self.assertTrue(self.staging.is_dir())
        self.assertFalse(
            (self.staging / "stale.json").exists(),
            "이전 실행의 산출물이 남으면 이번 run_id 와 섞인다",
        )

    def test_repeated_resets_are_stable(self) -> None:
        for _ in range(3):
            publish._reset(self.staging)
        self.assertTrue(self.staging.is_dir())


class TestPromotionRefusesLinks(unittest.TestCase):
    """승격 루프가 링크를 results/ 로 옮기지 않는다.

    `rglob` 은 링크를 따라가므로 staging 안에 심어진 링크가 루프에 들어올 수
    있고, 그대로 옮기면 **링크가 results/ 안에 놓인다** — 그다음 읽기가 그것을
    따라간다. `paths.ts` 가 대시보드 쪽에서 막는 것과 같은 종류이며(이슈 #64),
    이쪽은 게시 쪽이다.
    """

    def test_publish_source_checks_both_sides(self) -> None:
        """소스에 두 방향 검사가 있는지 — 승격 루프는 전체 게시 실행이 필요해
        단위로 태우기 어렵다. 그래서 **검사의 존재**만 여기서 보고, 실제 거부는
        위 `_reset` 테스트가 실행으로 증명한다. 이 구분을 흐리지 않는다."""
        import inspect

        source = inspect.getsource(publish.publish)
        self.assertIn(
            "path.is_symlink()", source,
            "승격 대상이 링크인지 보지 않으면 링크가 results/ 로 옮겨진다",
        )
        self.assertIn(
            "target.is_symlink()", source,
            "게시 대상이 링크면 results/ 가 이미 손대졌다는 뜻이다",
        )
