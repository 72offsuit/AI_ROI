"""Runs the doctests that live in `src/measurement/*.py` docstrings.

Why this file exists (issue #59, review finding M10): the modules carried 18
doctest examples and **nothing executed them**. One of the 18 had been failing
since it was written -- `metric_classification()` claimed `47` where the real
count was 46 -- and no gate caught it, because `unittest discover` does not pick
up doctests on its own.

That is the same shape as the other findings in #59: a declaration exists
(`>>> f()` promises a value) and nothing compares it against reality.

★ The module list is DISCOVERED, never hardcoded. Writing the list by hand would
  repeat the very defect this file closes -- a new module with a doctest would
  silently stay unchecked, and the file would still look green.

★ ISO-005: `isolation.yml` installs no dependencies, so every module imported
  here must import with the standard library alone. All ten currently do. A
  module that grows a hard dependency is reported as a skip with its reason
  rather than crashing the isolation job -- an unimportable module is a fact to
  record, not a reason to paint the whole suite red. It is never reported as a
  pass.
"""

from __future__ import annotations

import doctest
import importlib
import unittest
from pathlib import Path

#: `src/measurement/` -- the only package that currently carries doctests.
#: Kept as a path rather than a module list so new modules are picked up for free.
PACKAGE_DIR = Path(__file__).resolve().parent.parent / "src" / "measurement"
PACKAGE = "src.measurement"


def _module_names() -> list[str]:
    """Every module in the package, `__init__` excluded, sorted for stable output."""
    return sorted(
        path.stem
        for path in PACKAGE_DIR.glob("*.py")
        if path.stem != "__init__"
    )


class TestDoctestDiscovery(unittest.TestCase):
    """Guards the discovery itself.

    Without this, a broken glob would scan zero modules, find zero failures and
    report success -- "the thing being checked is narrower than the claim", which
    showed up three separate times during implementation.
    """

    def test_package_directory_exists(self) -> None:
        self.assertTrue(
            PACKAGE_DIR.is_dir(),
            f"{PACKAGE_DIR} 가 없다 — 경로가 바뀌면 이 파일이 아무것도 검사하지 않는다",
        )

    def test_discovery_finds_modules(self) -> None:
        names = _module_names()
        self.assertGreater(
            len(names), 0,
            "모듈을 하나도 찾지 못했다 — 0 개를 검사하고 통과하는 것이 이 파일이 막으려는 실패다",
        )

    def test_discovery_finds_examples(self) -> None:
        """At least one example must exist somewhere, or the runner is inert."""
        total = 0
        for name in _module_names():
            try:
                module = importlib.import_module(f"{PACKAGE}.{name}")
            except ImportError:
                continue
            total += sum(len(t.examples) for t in doctest.DocTestFinder().find(module))
        self.assertGreater(
            total, 0,
            "예제를 하나도 찾지 못했다 — 실행기는 도는데 검사 대상이 0 개인 상태다",
        )


class TestUnimportableModulesAreReported(unittest.TestCase):
    """An import failure is recorded, never silently dropped."""

    def test_every_module_imports_or_is_named(self) -> None:
        blocked: list[str] = []
        for name in _module_names():
            try:
                importlib.import_module(f"{PACKAGE}.{name}")
            except ImportError as error:
                blocked.append(f"{name}: {error}")
        if blocked:
            self.skipTest(
                "BLOCKED: 의존성이 없어 import 하지 못한 모듈이 있다 — "
                "doctest 를 실행하지 않았다 (통과가 아니다): " + " · ".join(blocked)
            )


def load_tests(loader, tests, ignore):  # noqa: ARG001 - unittest protocol
    """Adds one DocTestSuite per module that actually carries examples.

    `DocTestSuite` raises `ValueError` for a module with no examples, so modules
    are filtered by example count first rather than catching the error -- the
    distinction matters: "no examples" is normal, "import failed" is not, and
    they must not collapse into the same silent skip.
    """
    for name in _module_names():
        try:
            module = importlib.import_module(f"{PACKAGE}.{name}")
        except ImportError:
            # Reported by TestUnimportableModulesAreReported above as a skip with
            # its reason. Adding a failing suite here would make the isolation
            # job red for a dependency reason, which ISO-005 exists to prevent.
            continue
        if not any(t.examples for t in doctest.DocTestFinder().find(module)):
            continue
        tests.addTests(doctest.DocTestSuite(module))
    return tests
