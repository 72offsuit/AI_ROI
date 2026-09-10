"""파트 격리 규칙 검사.

시뮬레이터(출제자)와 의사결정 시스템(수험생)이 서로를 참조하지 못하게 강제한다.
gitignore와 달리 이 검사는 위반 시 실패하므로 실제 방어선이 된다.

규칙의 근거: Plan/AI_Retention_ROI_PRD_v2.md §10 · §21 · §80,
Plan/AI_Customer_Retention_ROI_SRS_v2.0.md ISO-001~005, docs/data_spec.html §17

실행:
    python3 -m unittest tests.test_isolation -v
"""

from __future__ import annotations

import ast
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"

# ── 모듈이 import할 수 없는 대상 ─────────────────────────────────────────────
FORBIDDEN_IMPORTS: dict[str, tuple[str, ...]] = {
    "src.decision": ("src.simulator", "src.diagnostics"),
    "src.simulator": ("src.decision", "src.diagnostics"),
    "src.measurement": ("src.simulator", "src.decision", "src.diagnostics"),
    "src.orchestration": ("src.simulator._internal", "src.diagnostics"),
}

# ── 모듈이 참조할 수 없는 데이터 경로 ───────────────────────────────────────
FORBIDDEN_PATHS: dict[str, tuple[str, ...]] = {
    "src.decision": ("data/hidden", "data/ground_truth"),
    "src.measurement": ("data/hidden", "data/ground_truth"),
    "src.orchestration": ("data/hidden", "data/ground_truth"),
    "src.simulator": ("results/",),
}

# ── 어떤 모듈도 import해서는 안 되는 대상 ───────────────────────────────────
NEVER_IMPORTED = "src.diagnostics"


def _module_name(path: Path) -> str:
    """레포 루트 기준 파일 경로를 점 표기 모듈명으로 바꾼다."""
    rel = path.relative_to(REPO_ROOT).with_suffix("")
    parts = list(rel.parts)
    if parts[-1] == "__init__":
        parts.pop()
    return ".".join(parts)


def _iter_source_files():
    if not SRC_ROOT.is_dir():
        return
    for path in sorted(SRC_ROOT.rglob("*.py")):
        yield path, _module_name(path)


def _imported_modules(tree: ast.AST) -> list[tuple[str, int]]:
    """(import된 모듈 경로, 줄 번호) 목록. 상대 import는 절대 경로로 정규화하지 않는다."""
    found: list[tuple[str, int]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                found.append((alias.name, node.lineno))
        elif isinstance(node, ast.ImportFrom):
            if node.level == 0 and node.module:
                found.append((node.module, node.lineno))
    return found


def _string_constants(tree: ast.AST) -> list[tuple[str, int]]:
    return [
        (node.value, node.lineno)
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant) and isinstance(node.value, str)
    ]


def _under(module: str, package: str) -> bool:
    return module == package or module.startswith(package + ".")


class TestPartIsolation(unittest.TestCase):
    """파트 간 import 경계."""

    def test_forbidden_imports(self) -> None:
        violations: list[str] = []
        for path, module in _iter_source_files():
            owner = next(
                (pkg for pkg in FORBIDDEN_IMPORTS if _under(module, pkg)), None
            )
            if owner is None:
                continue
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            for imported, lineno in _imported_modules(tree):
                for banned in FORBIDDEN_IMPORTS[owner]:
                    if _under(imported, banned):
                        violations.append(
                            f"{path.relative_to(REPO_ROOT)}:{lineno} "
                            f"— {owner} 는 {banned} 를 import할 수 없다 (발견: {imported})"
                        )
        self.assertEqual([], violations, "\n" + "\n".join(violations))

    def test_diagnostics_is_never_imported(self) -> None:
        """진단 모듈은 어디에서도 import되지 않는다. 리포트 단계에서 독립 실행한다."""
        violations: list[str] = []
        for path, module in _iter_source_files():
            if _under(module, NEVER_IMPORTED):
                continue
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            for imported, lineno in _imported_modules(tree):
                if _under(imported, NEVER_IMPORTED):
                    violations.append(
                        f"{path.relative_to(REPO_ROOT)}:{lineno} "
                        f"— {NEVER_IMPORTED} 는 어떤 모듈도 import할 수 없다"
                    )
        self.assertEqual([], violations, "\n" + "\n".join(violations))


class TestDataPathIsolation(unittest.TestCase):
    """민감 데이터 경로 참조 경계."""

    def test_forbidden_data_paths(self) -> None:
        violations: list[str] = []
        for path, module in _iter_source_files():
            owner = next(
                (pkg for pkg in FORBIDDEN_PATHS if _under(module, pkg)), None
            )
            if owner is None:
                continue
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            for text, lineno in _string_constants(tree):
                for banned in FORBIDDEN_PATHS[owner]:
                    if banned in text:
                        violations.append(
                            f"{path.relative_to(REPO_ROOT)}:{lineno} "
                            f"— {owner} 는 '{banned}' 경로를 참조할 수 없다 (발견: {text!r})"
                        )
        self.assertEqual([], violations, "\n" + "\n".join(violations))


class TestPartLayout(unittest.TestCase):
    """파트 디렉터리와 지침 파일이 제자리에 있는지."""

    REQUIRED_DIRS = (
        "src/measurement",
        "src/simulator",
        "src/simulator/_internal",
        "src/decision",
        "src/diagnostics",
        "src/orchestration",
    )

    def test_part_directories_exist(self) -> None:
        missing = [d for d in self.REQUIRED_DIRS if not (REPO_ROOT / d).is_dir()]
        self.assertEqual([], missing, f"파트 디렉터리 누락: {missing}")

    def test_each_part_has_agent_guides(self) -> None:
        """Codex와 Claude 양쪽이 읽도록 AGENTS.md와 CLAUDE.md를 함께 둔다."""
        missing: list[str] = []
        for d in ("src", *self.REQUIRED_DIRS):
            for guide in ("AGENTS.md", "CLAUDE.md"):
                target = REPO_ROOT / d / guide
                if not target.is_file():
                    missing.append(f"{d}/{guide}")
        self.assertEqual([], missing, f"지침 파일 누락: {missing}")

    def test_claude_md_delegates_to_agents_md(self) -> None:
        """CLAUDE.md는 내용을 복제하지 않고 AGENTS.md를 import한다."""
        offenders: list[str] = []
        for d in ("src", *self.REQUIRED_DIRS):
            target = REPO_ROOT / d / "CLAUDE.md"
            if target.is_file() and "@AGENTS.md" not in target.read_text(encoding="utf-8"):
                offenders.append(f"{d}/CLAUDE.md")
        self.assertEqual([], offenders, f"@AGENTS.md import 누락: {offenders}")


if __name__ == "__main__":
    unittest.main()
