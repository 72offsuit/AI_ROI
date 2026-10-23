"""Python 런타임 선언 ↔ 실제 (#207, docs/decisions/DR-207-python-runtime.md).

PRD NFR-04 는 `Python >= 3.10` 이다. 이 저장소의 사실은 둘로 갈린다:

  - 측정 계층과 의존성 없는 테스트 스위트는 3.10 에서 돈다 — `python-compat.yml`
  - 전체 파이프라인의 고정 의존성(numpy 2.5.4 · scipy 1.18.1 · shap 0.54.1)은
    Requires-Python >=3.12 다 — 3.10·3.11 에서는 설치부터 안 된다

그래서 `requirements.txt` 머리에 두 줄을 선언한다 (`Supported runtime` · `Measurement-layer
floor`). 선언만 두면 아무도 대조하지 않으므로 여기서 맞댄다:

  checked   Dockerfile 런타임 이미지 · CI 3.12 잡 2종이 `Supported runtime` 과 같은 판이다
  checked   python-compat.yml 이 `Measurement-layer floor` 에서 돈다
  checked   (의존성이 있으면) 고정 버전 전부의 Requires-Python 을 선언 런타임이 만족한다
  checked   (의존성이 있으면) 선언 런타임이 실제로 필요한 최소 판이다 — 고정 의존성이
            더 낮은 판을 허용하게 바뀌면 "3.12 가 필요하다" 는 선언의 근거가 사라진 것이다
  NOT       PRD 원문(`Plan/` 은 private 이라 CI 에 없다). 하한 3.10 은 DR 이 PRD 를 인용한다
"""

from __future__ import annotations

import re
import unittest
from importlib import metadata
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
REQUIREMENTS = REPO_ROOT / "requirements.txt"
REQUIREMENTS_DEV = REPO_ROOT / "requirements-dev.txt"
DOCKERFILE = REPO_ROOT / "Dockerfile"
WORKFLOWS = REPO_ROOT / ".github" / "workflows"


def _declared(label: str) -> tuple[int, int]:
    found = re.findall(rf"^# {re.escape(label)}: Python (\d+)\.(\d+)\s*$",
                       REQUIREMENTS.read_text(encoding="utf-8"), re.M)
    if len(found) != 1:
        raise AssertionError(f"requirements.txt 에 '# {label}: Python X.Y' 가 정확히 한 줄 있어야 한다: {found}")
    return int(found[0][0]), int(found[0][1])


def _workflow_python(name: str) -> tuple[int, int]:
    text = (WORKFLOWS / name).read_text(encoding="utf-8")
    found = re.findall(r"python-version:\s*['\"]?(\d+)\.(\d+)['\"]?", text)
    if len(found) != 1:
        raise AssertionError(f"{name}: python-version 이 정확히 하나여야 한다: {found}")
    return int(found[0][0]), int(found[0][1])


def _pins() -> list[tuple[str, str]]:
    pins = []
    for path in (REQUIREMENTS, REQUIREMENTS_DEV):
        for line in path.read_text(encoding="utf-8").splitlines():
            match = re.match(r"^([A-Za-z0-9_.\-]+)==([^\s#;]+)", line)
            if match:
                pins.append((match.group(1), match.group(2)))
    return pins


def _lower_bound(spec: str) -> tuple[int, int] | None:
    """Requires-Python 의 하한 (major, minor). `>=3.12` · `>3.11` · `~=3.10` 만 하한으로 본다."""
    bounds = []
    for clause in (c.strip() for c in spec.split(",") if c.strip()):
        match = re.match(r"^(>=|>|~=)\s*(\d+)\.(\d+)", clause)
        if match:
            major, minor = int(match.group(2)), int(match.group(3))
            bounds.append((major, minor + 1) if match.group(1) == ">" else (major, minor))
    return max(bounds) if bounds else None


def _upper_ok(spec: str, runtime: tuple[int, int]) -> bool:
    """`<3.13` · `<=3.12` 같은 상한을 런타임이 넘지 않는가."""
    for clause in (c.strip() for c in spec.split(",") if c.strip()):
        match = re.match(r"^(<=|<)\s*(\d+)\.(\d+)", clause)
        if match:
            bound = (int(match.group(2)), int(match.group(3)))
            if (match.group(1) == "<" and not runtime < bound) or (match.group(1) == "<=" and not runtime <= bound):
                return False
    return True


class TestDeclarationMatchesWhereItRuns(unittest.TestCase):
    def test_dockerfile_runtime_is_the_declared_runtime(self) -> None:
        runtime = _declared("Supported runtime")
        found = re.findall(r"^FROM python:(\d+)\.(\d+)", DOCKERFILE.read_text(encoding="utf-8"), re.M)
        self.assertEqual([runtime], [(int(a), int(b)) for a, b in found],
                         "Dockerfile 의 python 베이스 이미지가 선언 런타임과 다르다")

    def test_ci_full_suite_jobs_run_the_declared_runtime(self) -> None:
        runtime = _declared("Supported runtime")
        for name in ("isolation.yml", "tests-with-deps.yml"):
            with self.subTest(workflow=name):
                self.assertEqual(runtime, _workflow_python(name))

    def test_compat_job_runs_the_declared_floor(self) -> None:
        floor = _declared("Measurement-layer floor")
        self.assertEqual(floor, _workflow_python("python-compat.yml"))
        self.assertLessEqual(floor, _declared("Supported runtime"))
        self.assertGreaterEqual(floor, (3, 10), "PRD NFR-04 의 하한(3.10)보다 높은 판을 하한이라 적었다")


class TestPinsAgreeWithTheDeclaredRuntime(unittest.TestCase):
    """설치된 패키지의 메타데이터와 대조한다. 없으면 BLOCKED skip — 대조하지 않은 것을 통과로 적지 않는다."""

    def _requires_python(self) -> dict[str, str]:
        specs = {}
        for name, version in _pins():
            try:
                installed = metadata.version(name)
            except metadata.PackageNotFoundError:
                self.skipTest(f"BLOCKED: {name} 미설치 — Requires-Python 대조를 하지 않았다")
            if installed != version:
                self.skipTest(f"BLOCKED: {name} {installed} 설치됨(고정 {version}) — 고정 판과 대조하지 않았다")
            specs[name] = metadata.metadata(name).get("Requires-Python") or ""
        return specs

    def test_every_pin_installs_on_the_declared_runtime(self) -> None:
        runtime = _declared("Supported runtime")
        broken = {name: spec for name, spec in self._requires_python().items()
                  if ((_lower_bound(spec) or (0, 0)) > runtime) or not _upper_ok(spec, runtime)}
        self.assertEqual({}, broken, f"선언 런타임 {runtime} 에서 설치되지 않는 고정 버전이 있다")

    def test_the_declared_runtime_is_actually_needed(self) -> None:
        """★ "전체 파이프라인은 3.12" 의 근거는 고정 의존성의 하한이다. 그 근거가 사라지면 선언을 다시 본다."""
        runtime = _declared("Supported runtime")
        specs = self._requires_python()
        highest = max((b for b in map(_lower_bound, specs.values()) if b), default=None)
        self.assertEqual(
            runtime, highest,
            f"고정 의존성의 Requires-Python 하한 최댓값은 {highest} 인데 선언은 {runtime} 다 — "
            "requirements.txt 머리 주석과 DR-207-python-runtime 을 다시 본다. "
            f"하한: { {n: s for n, s in specs.items() if s} }",
        )


class TestLowerBoundParser(unittest.TestCase):
    def test_forms(self) -> None:
        self.assertEqual((3, 12), _lower_bound(">=3.12"))
        self.assertEqual((3, 12), _lower_bound(">3.11"))
        self.assertEqual((3, 10), _lower_bound(">=3.8, >=3.10, !=3.11.0"))
        self.assertIsNone(_lower_bound(""))
        self.assertTrue(_upper_ok(">=3.10,<3.13", (3, 12)))
        self.assertFalse(_upper_ok(">=3.10,<3.12", (3, 12)))


if __name__ == "__main__":
    unittest.main()
