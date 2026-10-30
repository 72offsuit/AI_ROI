"""Python 런타임 선언 ↔ 실제 (#207, docs/decisions/DR-207-python-runtime.md).

PRD NFR-04 는 `Python >= 3.10` 이다. 이 저장소의 사실은 둘로 갈린다:

  - 측정 계층과 의존성 없는 테스트 스위트는 3.10 에서 돈다 — `python-compat.yml`
  - 전체 파이프라인의 고정 의존성(numpy 2.5.4 · scipy 1.18.1 · shap 0.54.1)은
    Requires-Python >=3.12 다 — 3.10·3.11 에서는 설치부터 안 된다

그래서 `requirements.txt` 머리에 두 줄을 선언한다 (`Supported runtime` · `Measurement-layer
floor`). 선언만 두면 아무도 대조하지 않으므로 여기서 맞댄다:

  checked   Dockerfile 런타임 이미지 · CI 3.12 잡 2종이 `Supported runtime` 과 같은 판이다
  checked   python-compat.yml 이 `Measurement-layer floor` 에서 돈다
  checked   docs/gate1_checklist.md §5.1 의 명령이 `python3` 이 아니라 `Supported runtime` 판을 부른다
            (#248 — `python3` 이 3.11 인 기기에서 ① 이 실패했다)
  checked   같은 §5.1 의 설치 후 환경이 의존성 설치 CI 가 설치하는 requirements 파일을 전부 설치하고,
            CI 게이트처럼 `미설치` 사유 skip 0건을 본다 (PR #249 리뷰 R1)
  checked   (의존성이 있으면) 고정 버전 전부의 Requires-Python 을 Dockerfile 의 정확한 판
            (예: 3.12.15)이 만족한다. 이 파일이 판정하지 못하는 절(`===` · 사전 배포판 등)은
            통과가 아니라 실패다 — 모르는 조건을 만족한다고 적지 않는다 (PR #240 리뷰 R2)
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
GATE1_CHECKLIST = REPO_ROOT / "docs" / "gate1_checklist.md"


def _gate1_section() -> str:
    """`docs/gate1_checklist.md` §5.1 본문."""
    return GATE1_CHECKLIST.read_text(encoding="utf-8").partition("### 5.1")[2].partition("\n### ")[0]


def _gate1_block(section: str) -> str:
    """§5.1 의 bash 명령 블록. 없으면 실패한다."""
    block = re.search(r"```bash\n(.*?)```", section, re.S)
    if block is None:
        raise AssertionError("gate1_checklist.md §5.1 에 bash 명령 블록이 없다")
    return block.group(1)


def _requirement_files(text: str) -> set[str]:
    return set(re.findall(r"-r\s+(requirements[\w-]*\.txt)", text))


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


#: Requires-Python 한 절. 정식 판(final release)끼리의 비교만 판정한다 — 그 밖의 형태는 `_clauses` 가 거부한다.
_CLAUSE = re.compile(r"^(~=|==|!=|<=|>=|<|>)\s*(\d+(?:\.\d+)*)(\.\*)?$")


def _clauses(spec: str) -> list[tuple[str, tuple[int, ...], bool]]:
    """`(연산자, 판, 와일드카드)` 목록. 판정하지 못하는 절이면 실패한다 — 통과로 두지 않는다."""
    out = []
    for raw in (c.strip() for c in spec.split(",") if c.strip()):
        match = _CLAUSE.match(raw)
        op = match.group(1) if match else None
        if (match is None or (match.group(3) and op not in ("==", "!="))
                or (op == "~=" and "." not in match.group(2))):
            raise AssertionError(f"Requires-Python 절 {raw!r} 은 이 검사가 판정하지 않는 형태다 — "
                                 "판정 규칙을 넓히거나 표준 버전 파서를 쓴다 (DR-207-python-runtime)")
        out.append((op, tuple(int(x) for x in match.group(2).split(".")), bool(match.group(3))))
    return out


def _cmp(a: tuple[int, ...], b: tuple[int, ...]) -> int:
    """PEP 440 처럼 짧은 쪽을 0 으로 채워 비교한다(3.12 == 3.12.0)."""
    n = max(len(a), len(b))
    a, b = a + (0,) * (n - len(a)), b + (0,) * (n - len(b))
    return (a > b) - (a < b)


def _admits(spec: str, version: tuple[int, int, int]) -> bool:
    """정식 판 `version` 이 Requires-Python `spec` 을 만족하는가."""
    for op, bound, wildcard in _clauses(spec):
        if wildcard:
            ok = version[:len(bound)] == bound
            ok = ok if op == "==" else not ok
        elif op == "~=":  # ~=X.Y.Z ≡ >=X.Y.Z, ==X.Y.*
            ok = _cmp(version, bound) >= 0 and version[:len(bound) - 1] == bound[:-1]
        else:
            c = _cmp(version, bound)
            ok = {"==": c == 0, "!=": c != 0, ">=": c >= 0, "<=": c <= 0, ">": c > 0, "<": c < 0}[op]
        if not ok:
            return False
    return True


def _lower_bound(spec: str) -> tuple[int, int] | None:
    """`spec` 을 만족하는 가장 낮은 판의 (major, minor). 조건이 없으면 None.

    절마다 하한을 따로 보지 않고 실제로 만족하는 판을 찾는다 — `>3.11` 은 3.11.1 을 허용하고
    `>=3.12,!=3.12.*` 의 하한은 3.13 이다."""
    if not _clauses(spec):
        return None
    for major in (2, 3):
        for minor in range(41):
            if any(_admits(spec, (major, minor, micro)) for micro in range(100)):
                return major, minor
    return None


def _dockerfile_python() -> tuple[int, int, int]:
    found = re.findall(r"^FROM python:(\d+)\.(\d+)\.(\d+)", DOCKERFILE.read_text(encoding="utf-8"), re.M)
    if len(found) != 1:
        raise AssertionError(f"Dockerfile 에 python:X.Y.Z 베이스가 정확히 하나여야 한다: {found}")
    major, minor, micro = (int(x) for x in found[0])
    return major, minor, micro


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

    def test_gate1_checklist_runs_the_declared_runtime(self) -> None:
        """§5.1 실행 전 확인의 python 호출이 전부 선언 런타임이다 — `python3` 의 판은 기기마다 다르다(#248)."""
        runtime = "python{}.{}".format(*_declared("Supported runtime"))
        calls = re.findall(r"^(?:!\s+)?(python[\d.]*)\s", _gate1_block(_gate1_section()), re.M)
        self.assertTrue(calls, "gate1_checklist.md §5.1 블록에 python 호출이 없다")
        self.assertEqual([runtime] * len(calls), calls,
                         f"gate1_checklist.md §5.1 의 명령이 선언 런타임({runtime})이 아닌 판을 부른다")

    def test_gate1_checklist_installs_what_the_deps_ci_installs(self) -> None:
        """§5.1 의 설치 후 환경이 의존성 설치 CI 와 같은 파일을 설치하고, 같은 `미설치` 게이트를 본다.

        `requirements.txt` 만 설치하면 계약 스키마 검증이 skip 되고도 ① 이 `OK` 다(PR #249 리뷰 R1)."""
        ci = _requirement_files((WORKFLOWS / "tests-with-deps.yml").read_text(encoding="utf-8"))
        self.assertTrue(ci, "tests-with-deps.yml 에서 설치하는 requirements 파일을 읽지 못했다")
        section = _gate1_section()
        self.assertLessEqual(ci, _requirement_files(section),
                             "gate1_checklist.md §5.1 의 설치 후 환경이 의존성 설치 CI 가 설치하는 파일을 빠뜨린다")
        gate = [line for line in _gate1_block(section).splitlines()
                if "unittest discover" in line and "미설치" in line]
        self.assertTrue(gate, "gate1_checklist.md §5.1 블록에 '미설치' 사유 skip 0건 확인이 없다 — CI 게이트와 같은 기준")


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
        """선언(major.minor)이 아니라 이미지의 정확한 판으로 본다 — `>=3.12.16` 은 3.12.15 에 설치되지 않는다."""
        runtime = _dockerfile_python()
        self.assertEqual(_declared("Supported runtime"), runtime[:2])
        broken = {name: spec for name, spec in self._requires_python().items() if not _admits(spec, runtime)}
        self.assertEqual({}, broken, f"Dockerfile 의 Python {runtime} 에서 설치되지 않는 고정 버전이 있다")

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


class TestRequiresPythonParser(unittest.TestCase):
    def test_lower_bound(self) -> None:
        self.assertEqual((3, 12), _lower_bound(">=3.12"))
        self.assertEqual((3, 11), _lower_bound(">3.11"))  # 3.11.1 이 만족한다
        self.assertEqual((3, 10), _lower_bound(">=3.8, >=3.10, !=3.11.0"))
        self.assertEqual((3, 13), _lower_bound(">=3.12,!=3.12.*"))
        self.assertEqual((3, 10), _lower_bound("~=3.10.0"))
        self.assertIsNone(_lower_bound(""))

    def test_admits_the_exact_runtime(self) -> None:
        runtime = (3, 12, 15)
        for spec in (">=3.12", ">=3.10,<3.13", "~=3.10", ">=3.12.15", ">3.11", "!=3.11.*", "==3.12.*"):
            with self.subTest(spec=spec):
                self.assertTrue(_admits(spec, runtime))
        # 앞의 셋은 PR #240 리뷰 R2 의 반례 — 이전 판정(major.minor 하한 · 상한만)은 통과시켰다
        for spec in (">=3.12,!=3.12.*", "~=3.10.0", ">=3.12.16", ">=3.10,<3.12", "<=3.12.14", "==3.12"):
            with self.subTest(spec=spec):
                self.assertFalse(_admits(spec, runtime))

    def test_unsupported_clauses_fail_instead_of_passing(self) -> None:
        for spec in ("===3.12", ">=3.12.0rc1", ">=3.*", "~=3", ">=3.12; python_version", "3.12"):
            with self.subTest(spec=spec):
                with self.assertRaises(AssertionError):
                    _admits(spec, (3, 12, 15))


if __name__ == "__main__":
    unittest.main()
