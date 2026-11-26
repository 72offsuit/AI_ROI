"""GATE 2 — Baseline Freeze 봉인 기록 (PRD §83 · SRS GATE 2 · BASE-003, DR-170-gate2-lock).

잠그는 것(G2):

1. **Baseline 규칙** — S1 대상을 정하는 이름(``LOCKED_NAMES`` 의 ``baseline_rule``)의 지문.
2. **예산 상한** — C_rule 정의 · 계산 이름(``budget_cap``)의 지문과 Baseline 실행의 C_rule 값 · 처치 단가.
3. **Baseline 결과** — S0 · S1 의 배정 · 계획 비용 · 측정 계층 경제 지표, 결과 파일 sha256.

지문: 함수는 소스 구간 그대로의 sha256(한 글자라도 바뀌면 다르다 — GATE 1 의 파일 해시와 같은 엄격함), 리터럴 상수는
값의 정규 JSON sha256. 파일 전체가 아니라 이름 단위인 것은 같은 파일에 GATE 3 에서 바꿀 수 있는 코드(S2~S6 · 예산 배분,
PRD §84)가 함께 있어서다.

기록(``config/gate2_lock.yaml``)은 ``record()`` 만 쓴다. ``locked_by`` 는 **사람 이름**이고(GATE 1 ``freeze.build_record`` 와
같은 거부 목록 + 에이전트 이름), 봉인 조건(G4 · ``collect``)이 하나라도 충족이 아니면 — 확인하지 못한 것(None)도 — 쓰지
않는다. **에이전트는 ``record`` 를 실행하지 않는다**(#170 — 서명은 사람).

    python -m src.orchestration.gate2_lock check  <결과 폴더> --expected-commit <태그|커밋> [--json]
    python -m src.orchestration.gate2_lock record <결과 폴더> --expected-commit <태그|커밋> --locked-by <이름>
    python -m src.orchestration.gate2_lock verify
"""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
import math
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Mapping

REPO_ROOT = Path(__file__).resolve().parents[2]
KST = timezone(timedelta(hours=9), "KST")
LOCK_RECORD = Path("config/gate2_lock.yaml")
LOCK_RECORD_VERSION = "gate2-lock/v1"
GATE1_RECORD = Path("config/gate1_lock.yaml")
GATE1_FULL = "FULL_FREEZE"
#: S1 규칙 코드를 AI 결과 전에 고정한 증거(``ce05a66``, #170 10/22 · DR-145).
S1_RULE_TAG = "gate2-s1-rule"
#: DR-211 FR-05 — T0 ≥ 10,000 · T1~T4 합 ≥ 10,000.
MIN_ARM_CUSTOMERS = 10_000
CONTROL_ARM = "T0"
TREATED_ARMS = ("T1", "T2", "T3", "T4")
BASELINE_STRATEGIES = ("S0", "S1")
HASHED_RESULT_FILES = ("run_meta.json", "strategy_comparison.json", "branch_invariance.json")
#: GATE 1 ``freeze.build_record`` 의 거부 목록 + 에이전트 이름.
NOT_HUMAN = frozenset({"agent", "unknown", "n/a", "-", "claude", "codex"})
RELEASE_PROCEDURE = (
    "봉인한 이름 · C_rule 을 바꾸려면 사용자 승인 뒤 기록 판을 올리고 Baseline(S0 · S1)부터 전 전략을 다시 실행한다. "
    "이 파일을 손으로 고치는 것으로 대체되지 않는다(DR-170-gate2-lock G3)."
)

STRATEGIES_PY = "src/decision/strategies.py"
RUN_SPRINT_PY = "src/orchestration/run_sprint.py"


class Gate2LockViolation(Exception):
    """봉인 조건 미충족 · 사람이 아닌 서명 — 기록을 쓰지 않는다."""


@dataclass(frozen=True)
class LockedName:
    group: str
    file: str
    name: str
    key: str | None = None

    @property
    def label(self) -> str:
        return f'{self.name}["{self.key}"]' if self.key is not None else self.name


def _names(group: str, file: str, *names: str) -> tuple[LockedName, ...]:
    return tuple(LockedName(group, file, name) for name in names)


#: 봉인 대상 이름(DR-170-gate2-lock G2). S2~S6 · ``plan()`` 디스패치 · 예산 배분은 GATE 3 에서 바꿀 수 있어 넣지 않는다.
LOCKED_NAMES: tuple[LockedName, ...] = (
    *_names("baseline_rule", STRATEGIES_PY, "S1_RULE", "plan_S0", "s1_eligibility", "plan_S1",
            "within_eligible", "_missing", "_as_mapping"),
    LockedName("baseline_rule", STRATEGIES_PY, "REQUIRED_SCORES", "S1"),
    *_names("baseline_rule", RUN_SPRINT_PY, "ELIGIBLE_MIN_TENURE_DAYS", "ELIGIBLE_MIN_ORDERS",
            "ELIGIBLE_MIN_DAYS_SINCE_PURCHASE", "_timestamps", "_kst_dates", "eligibility", "s1_inputs"),
    *_names("budget_cap", STRATEGIES_PY, "planning_costs"),
    *_names("budget_cap", RUN_SPRINT_PY, "C_RULE_DEFINITION", "plan_costs", "assignment_planned_cost", "resolve_budget"),
)


# ── 지문 ──────────────────────────────────────────────────────────────────


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def fingerprint(source: str, item: LockedName) -> dict[str, str]:
    """최상위 이름 하나의 지문. 같은 이름이 여러 번 정의되면 마지막 것(실행 시 남는 것)이다. 없으면 LookupError."""
    found: dict[str, str] | None = None
    for node in ast.parse(source).body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            if node.name == item.name:
                if item.key is not None:
                    raise LookupError(f"{item.label} — 함수 · 클래스에는 항목을 고를 수 없다")
                found = {"kind": "source", "sha256": _sha256(ast.get_source_segment(source, node) or "")}
            continue
        if isinstance(node, ast.Assign):
            targets, value = [t.id for t in node.targets if isinstance(t, ast.Name)], node.value
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name) and node.value is not None:
            targets, value = [node.target.id], node.value
        else:
            continue
        if item.name not in targets:
            continue
        try:
            literal = ast.literal_eval(value)
        except (ValueError, SyntaxError):
            if item.key is not None:
                raise LookupError(f"{item.label} — 리터럴이 아니라 항목을 고를 수 없다") from None
            found = {"kind": "source", "sha256": _sha256(ast.get_source_segment(source, node) or "")}
            continue
        if item.key is not None:
            if not isinstance(literal, Mapping) or item.key not in literal:
                raise LookupError(f"{item.label} — 그 항목이 없다")
            literal = literal[item.key]
        try:
            text = json.dumps(literal, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        except TypeError:
            found = {"kind": "source", "sha256": _sha256(ast.get_source_segment(source, node) or "")}
        else:
            found = {"kind": "value", "sha256": _sha256(text)}
    if found is None:
        raise LookupError(f"{item.file} 에 {item.name} 이 없다")
    return found


def fingerprints(read: Callable[[str], str | None]) -> list[dict[str, Any]]:
    """``LOCKED_NAMES`` 전부의 지문. 읽지 못하거나 이름이 없으면 ``sha256: None`` 과 사유."""
    cache: dict[str, str | None] = {}
    rows = []
    for item in LOCKED_NAMES:
        if item.file not in cache:
            cache[item.file] = read(item.file)
        row: dict[str, Any] = {"group": item.group, "file": item.file, "name": item.label}
        source = cache[item.file]
        if source is None:
            row.update(kind=None, sha256=None, reason="파일을 읽지 못했다")
        else:
            try:
                row.update(fingerprint(source, item))
            except (LookupError, SyntaxError) as error:
                row.update(kind=None, sha256=None, reason=str(error))
        rows.append(row)
    return rows


def _git(root: Path, *args: str) -> str | None:
    try:
        done = subprocess.run(["git", "-C", str(root), *args], capture_output=True, text=True,
                              encoding="utf-8", check=False)
    except OSError:
        return None
    return done.stdout if done.returncode == 0 else None


def _git_bytes(root: Path, *args: str) -> bytes | None:
    """``git show`` 원본 바이트 — 해시는 디코딩 전 바이트로 낸다(GATE 1 ``freeze.file_sha256`` 과 같은 값)."""
    try:
        done = subprocess.run(["git", "-C", str(root), *args], capture_output=True, check=False)
    except OSError:
        return None
    return done.stdout if done.returncode == 0 else None


def gate1_canonical_at(root: Path, commit: str, gate1: Mapping[str, Any]) -> list[dict[str, Any]]:
    """GATE 1 기록의 ``canonical_files`` 를 **실행 커밋**의 파일과 대조한다 — 해시는 ``freeze.file_sha256`` 그대로.

    파일 내용은 출력하지 않는다(경로 · 해시만). 기록에 정본이 없으면 빈 목록이다(그때 B-1 은 미충족).
    """
    from src.measurement.freeze import file_sha256

    recorded = gate1.get("canonical_files")
    if not isinstance(recorded, Mapping):
        return []
    rows = []
    with tempfile.TemporaryDirectory() as folder:
        scratch = Path(folder) / "canonical"
        for relative, expected in recorded.items():
            data = _git_bytes(root, "show", f"{commit}:{relative}")
            actual = None
            if data is not None:
                scratch.write_bytes(data)
                actual = file_sha256(scratch)
            rows.append({"path": str(relative), "recorded": None if expected is None else str(expected),
                         "at_run_commit": actual})
    return rows


def worktree_reader(root: Path) -> Callable[[str], str | None]:
    def read(relative: str) -> str | None:
        path = Path(root) / relative
        return path.read_text(encoding="utf-8") if path.exists() else None
    return read


def revision_reader(root: Path, revision: str) -> Callable[[str], str | None]:
    def read(relative: str) -> str | None:
        return _git(root, "show", f"{revision}:{relative}")
    return read


def resolve_commit(root: Path, revision: str) -> str | None:
    out = _git(root, "rev-parse", "--verify", "--quiet", f"{revision}^{{commit}}")
    return out.strip() if out else None


def tag_comparison(root: Path, rows: list[dict[str, Any]]) -> dict[str, Any]:
    """기록할 지문이 태그 ``gate2-s1-rule`` 의 같은 이름과 같은지 — 사실만(조건이 아니다, DR-170-gate2-lock G2)."""
    commit = resolve_commit(root, S1_RULE_TAG)
    if commit is None:
        return {"tag": S1_RULE_TAG, "commit": None, "reason": "태그를 찾지 못했다", "names": {}}
    at_tag = {(r["file"], r["name"]): r.get("sha256") for r in fingerprints(revision_reader(root, commit))}
    names = {}
    for row in rows:
        then = at_tag.get((row["file"], row["name"]))
        names[row["name"]] = "absent" if then is None else ("same" if then == row.get("sha256") else "differs")
    return {"tag": S1_RULE_TAG, "commit": commit, "names": names}


# ── 봉인 조건(G4) ───────────────────────────────────────────────────────────


@dataclass(frozen=True)
class Check:
    id: str
    title: str
    met: bool | None
    evidence: str

    def to_json(self) -> dict[str, Any]:
        return {"id": self.id, "title": self.title, "met": self.met, "evidence": self.evidence}


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None


def _load_yaml_text(text: str) -> Mapping[str, Any] | None:
    from src.measurement.config_loader import load_yaml

    with tempfile.TemporaryDirectory() as folder:
        path = Path(folder) / "record.yaml"
        path.write_text(text, encoding="utf-8")
        loaded = load_yaml(path)
    return loaded if isinstance(loaded, Mapping) else None


def _stage_status(meta: Mapping[str, Any], name: str) -> str | None:
    status = None
    for stage in meta.get("stages") or []:
        if isinstance(stage, Mapping) and stage.get("name") == name:
            status = stage.get("status")
    return status


def _number(value: Any) -> float | None:
    return float(value) if isinstance(value, (int, float)) and not isinstance(value, bool) \
        and math.isfinite(float(value)) else None


def _gate1_check(gate1: Mapping[str, Any] | None, canonical: list[dict[str, Any]] | None,
                 run_commit: str | None, run_simulator: Any) -> Check:
    """B-1 — 실행 환경이 GATE 1 봉인과 같다: FULL_FREEZE 선언 · 기록의 simulator_commit = 실행의 simulator_commit ·
    기록의 정본 파일 해시 = 실행 커밋의 파일 해시(#213 · PR #327 리뷰)."""
    title = "실행 환경 = GATE 1 봉인(FULL_FREEZE · simulator_commit · 정본 해시, 실행 커밋 기준)"
    if gate1 is None:
        return Check("B-1", title, None, f"실행 커밋 {str(run_commit)[:12]} 의 {GATE1_RECORD.as_posix()} 를 읽지 못했다")
    declaration = gate1.get("declaration")
    sealed_sim = gate1.get("simulator_commit")
    rows = canonical or []
    broken = [r["path"] for r in rows if r["recorded"] is None or r["at_run_commit"] != r["recorded"]]
    problems = []
    if declaration != GATE1_FULL:
        problems.append(f"declaration={declaration!r}")
    if not sealed_sim or not run_simulator:
        problems.append(f"simulator_commit 없음(기록 {sealed_sim!r} · 실행 {run_simulator!r})")
    elif sealed_sim != run_simulator:
        problems.append(f"simulator_commit 다름(기록 {str(sealed_sim)[:12]} · 실행 {str(run_simulator)[:12]})")
    if not rows:
        problems.append("기록에 정본 파일(canonical_files)이 없다")
    if broken:
        problems.append(f"실행 커밋에서 해시가 다른 정본 {broken}")
    evidence = (f"실행 커밋 {str(run_commit)[:12]} · declaration={declaration!r} · simulator_commit "
                f"{str(sealed_sim)[:12]}={str(run_simulator)[:12]} · 정본 {len(rows) - len(broken)}/{len(rows)} 일치")
    return Check("B-1", title, not problems, evidence if not problems else f"{evidence} — {' · '.join(problems)}")


def _baseline_check(meta: Mapping[str, Any], comparison: Mapping[str, Any] | None) -> Check:
    """B-7 — S0 · S1 분기 ok, 같은 실행의 ``strategy_comparison.json`` 에 S0 · S1 상세(배정 수 · 계획 비용)가 있다."""
    title = "S0 · S1 분기 ok · 같은 실행의 결과 파일에 S0 · S1 상세"
    statuses = {s: _stage_status(meta, f"strategy_{s}") for s in BASELINE_STRATEGIES}
    stage_text = " · ".join(f"strategy_{s}={v!r}" for s, v in statuses.items())
    if comparison is None:
        return Check("B-7", title, False, f"{stage_text} · strategy_comparison.json 이 없다")
    details = comparison.get("strategy_details") or {}
    lacking = [s for s in BASELINE_STRATEGIES
               if not isinstance(details.get(s), Mapping) or not isinstance(details[s].get("n_assigned"), int)
               or _number(details[s].get("planned_cost_krw")) is None]
    same_run = comparison.get("run_id") is not None and comparison.get("run_id") == meta.get("run_id")
    problems = []
    if any(v is None for v in statuses.values()):
        met: bool | None = None
    else:
        met = all(v == "ok" for v in statuses.values())
    if lacking:
        problems.append(f"배정 수 · 계획 비용이 없는 상세 {lacking}")
    if not same_run:
        problems.append(f"run_id 다름(결과 파일 {comparison.get('run_id')!r} · run_meta {meta.get('run_id')!r})")
    if problems:
        met = False
    return Check("B-7", title, met, stage_text + (f" — {' · '.join(problems)}" if problems else ""))


def _c_rule_check(meta: Mapping[str, Any], comparison: Mapping[str, Any] | None) -> Check:
    """B-8 — C_rule 이 S1 계획 비용에서 왔고(``--budget-krw`` 아님), 기록할 값 = 결과 파일의 S1 계획 비용
    = S1 처치별 배정 수 × 처치 단가(``planning_costs_krw``) 합(PR #327 리뷰 — run_meta 예산 필드끼리만 대조하지 않는다)."""
    title = "C_rule = S1 계획 비용(결과 파일 · 배정 수 × 단가와 일치, --budget-krw 아님)"
    budget = meta.get("budget") or {}
    if not budget:
        return Check("B-8", title, None, "run_meta.budget 이 없다")
    c_rule, planning = _number(budget.get("c_rule_planned_krw")), _number(budget.get("planning_budget_krw"))
    from_c_rule = str(budget.get("source") or "").startswith("C_rule")
    s1 = ((comparison or {}).get("strategy_details") or {}).get(BASELINE_STRATEGIES[1]) or {}
    s1_planned = _number(s1.get("planned_cost_krw"))
    unit = meta.get("planning_costs_krw") if isinstance(meta.get("planning_costs_krw"), Mapping) else {}
    counts = s1.get("treatment_counts") if isinstance(s1.get("treatment_counts"), Mapping) else None
    recomputed = None
    if counts is not None and all(_number(unit.get(t)) is not None for t, n in counts.items() if n):
        recomputed = float(sum(_number(unit.get(t)) * int(n) for t, n in counts.items() if n))
    problems = []
    if budget.get("status") != "ok" or not from_c_rule:
        problems.append(f"status={budget.get('status')!r} · 출처 C_rule={from_c_rule}")
    if c_rule is None or planning is None or abs(planning - max(c_rule, 0.0)) > 1e-6:
        problems.append(f"c_rule_planned_krw={budget.get('c_rule_planned_krw')!r} · planning_budget_krw={planning!r}")
    if s1_planned is None or c_rule is None or abs(s1_planned - c_rule) > 1e-6:
        problems.append(f"결과 파일 S1 계획 비용 {s1_planned!r} ≠ C_rule {c_rule!r}")
    if recomputed is None or c_rule is None or abs(recomputed - c_rule) > 1e-6:
        problems.append(f"S1 배정 수 × 처치 단가 합 {recomputed!r} ≠ C_rule {c_rule!r}")
    evidence = (f"C_rule={c_rule!r} · 결과 파일 S1={s1_planned!r} · 배정 수 × 단가={recomputed!r} · "
                f"출처 C_rule={from_c_rule}")
    return Check("B-8", title, not problems, evidence if not problems else f"{evidence} — {' · '.join(problems)}")


def _invariance_check(meta: Mapping[str, Any], invariance: Mapping[str, Any] | None) -> Check:
    """B-9 — 같은 실행의 분기 간 대조가 봉인 대상 분기 전부(``REQUIRED_BRANCHES``)를 대조했고 ``same``."""
    from src.orchestration.branch_invariance import REQUIRED_BRANCHES

    title = f"분기 간 대조 = same, 분기 {'·'.join(REQUIRED_BRANCHES)} 전부(DR-234 반증 조건)"
    if invariance is None:
        return Check("B-9", title, None, "branch_invariance.json 없음")
    result, status = invariance.get("result"), invariance.get("status")
    compared = set(invariance.get("branches") or []) if status == "ok" else set()
    missing = sorted(set(REQUIRED_BRANCHES) - compared)
    same_run = invariance.get("run_id") is not None and invariance.get("run_id") == meta.get("run_id")
    evidence = (f"status={status!r} · result={result!r} · complete={invariance.get('complete')!r} · "
                f"빠진 분기={invariance.get('missing_branches') or missing} · run_id={invariance.get('run_id')!r}")
    if status == "not_run":
        return Check("B-9", title, None, f"{evidence} · {invariance.get('reason') or ''}")
    met = (status == "ok" and result == "same" and invariance.get("complete") is True and not missing and same_run)
    if not same_run:
        evidence += f" — run_meta run_id {meta.get('run_id')!r} 와 다르다"
    return Check("B-9", title, met, evidence)


def _checks(meta: Mapping[str, Any] | None, invariance: Mapping[str, Any] | None, gate1: Mapping[str, Any] | None,
            run_commit: str | None, expected_sha: str | None, expected: str,
            at_run: list[dict[str, Any]] | None, current: list[dict[str, Any]],
            comparison: Mapping[str, Any] | None = None,
            gate1_canonical: list[dict[str, Any]] | None = None) -> list[Check]:
    meta = meta or {}
    prov = meta.get("provenance") or {}
    checks = [_gate1_check(gate1, gate1_canonical, run_commit, prov.get("simulator_commit"))]

    checks.append(Check("B-2", "실행 커밋 = 지정한 커밋",
                        None if run_commit is None or expected_sha is None else run_commit == expected_sha,
                        f"repo_commit={run_commit!r} · {expected}={expected_sha!r}"))

    clean, dirty = prov.get("require_clean"), prov.get("repo_worktree_dirty")
    checks.append(Check("B-3", "깨끗한 시작(--require-clean · 커밋 전 변경 없음)",
                        None if clean is None or dirty is None else (clean is True and dirty is False),
                        f"require_clean={clean!r} · repo_worktree_dirty={dirty!r}"))

    changed = prov.get("repo_changed_during_run")
    checks.append(Check("B-4", "실행 중 저장소 변경 없음",
                        None if changed is None else changed is False, f"repo_changed_during_run={changed!r}"))

    checks.append(Check("B-5", "저장소 상태 조회 실패 없음",
                        None if not prov else "null_reason" not in prov,
                        f"null_reason={prov.get('null_reason')!r}"))

    arms = (meta.get("rct") or {}).get("arm_counts")
    if isinstance(arms, Mapping) and arms:
        control = int(arms.get(CONTROL_ARM) or 0)
        treated = sum(int(arms.get(arm) or 0) for arm in TREATED_ARMS)
        scale = Check("B-6", f"규모 FR-05 — T0 ≥ {MIN_ARM_CUSTOMERS:,} · T1~T4 합 ≥ {MIN_ARM_CUSTOMERS:,}",
                      control >= MIN_ARM_CUSTOMERS and treated >= MIN_ARM_CUSTOMERS,
                      f"T0={control:,} · T1~T4 합={treated:,}")
    else:
        scale = Check("B-6", f"규모 FR-05 — T0 ≥ {MIN_ARM_CUSTOMERS:,} · T1~T4 합 ≥ {MIN_ARM_CUSTOMERS:,}", None,
                      "rct.arm_counts 가 없다")
    checks.append(scale)

    checks.append(_baseline_check(meta, comparison))
    checks.append(_c_rule_check(meta, comparison))
    checks.append(_invariance_check(meta, invariance))

    if at_run is None:
        names = Check("B-10", "기록할 지문 = 실행 커밋의 지문 = 지금 저장소", None, "실행 커밋을 모른다")
    else:
        now = {(r["file"], r["name"]): r.get("sha256") for r in current}
        broken = [r["name"] for r in at_run if r.get("sha256") is None or now.get((r["file"], r["name"])) is None]
        differ = [r["name"] for r in at_run
                  if r["name"] not in broken and now.get((r["file"], r["name"])) != r.get("sha256")]
        names = Check("B-10", "기록할 지문 = 실행 커밋의 지문 = 지금 저장소", not broken and not differ,
                      f"지문을 낼 수 없는 이름 {broken} · 실행 커밋과 다른 이름 {differ}")
    checks.append(names)
    return checks


def collect(run_dir: Path, expected: str, root: Path | None = None) -> dict[str, Any]:
    """결과 폴더 · 저장소에서 봉인 조건과 기록 재료를 모은다. 아무것도 쓰지 않는다."""
    run_dir = Path(run_dir)
    root = Path(root) if root is not None else REPO_ROOT
    meta = _read_json(run_dir / "run_meta.json")
    comparison = _read_json(run_dir / "strategy_comparison.json")
    invariance = _read_json(run_dir / "branch_invariance.json")
    run_commit = ((meta or {}).get("provenance") or {}).get("repo_commit")
    expected_sha = resolve_commit(root, expected)
    at_run = fingerprints(revision_reader(root, run_commit)) if run_commit else None
    current = fingerprints(worktree_reader(root))
    gate1_text = _git(root, "show", f"{run_commit}:{GATE1_RECORD.as_posix()}") if run_commit else None
    gate1 = _load_yaml_text(gate1_text) if gate1_text else None
    canonical = gate1_canonical_at(root, run_commit, gate1) if gate1 is not None and run_commit else None
    return {
        "run_dir": run_dir, "expected": expected, "expected_sha": expected_sha, "root": Path(root),
        "meta": meta, "comparison": comparison, "invariance": invariance, "run_commit": run_commit,
        "at_run": at_run, "current": current, "gate1": gate1, "gate1_text": gate1_text,
        "gate1_canonical": canonical,
        "checks": _checks(meta, invariance, gate1, run_commit, expected_sha, expected, at_run, current,
                          comparison, canonical),
    }


# ── 기록 ──────────────────────────────────────────────────────────────────


def _file_sha256(path: Path) -> str | None:
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.exists() else None


def _baseline_entry(entry: Mapping[str, Any] | None) -> dict[str, Any]:
    entry = entry or {}
    economics = entry.get("measured_economics") or {}
    metrics = economics.get("metrics") or {}
    return {
        "n_assigned": entry.get("n_assigned"), "n_targeted": entry.get("n_targeted"),
        "treatment_counts": entry.get("treatment_counts"), "planned_cost_krw": entry.get("planned_cost_krw"),
        "budget_krw": entry.get("budget_krw"),
        "measured_economics": {
            "status": economics.get("status"),
            "values": {k: (m.get("value") if isinstance(m, Mapping) and m.get("status") == "ok" else None)
                       for k, m in metrics.items()},
        },
    }


def build_record(collected: Mapping[str, Any], *, locked_by: str | None, now: datetime | None) -> dict[str, Any]:
    """기록 본문. ``locked_by`` 가 None 이면 미리 보기(``check``)다 — 서명 · 시각이 비어 있다."""
    meta = collected["meta"] or {}
    prov = meta.get("provenance") or {}
    budget = meta.get("budget") or {}
    details = (collected["comparison"] or {}).get("strategy_details") or {}
    invariance = collected["invariance"] or {}
    rows = collected["at_run"] or []
    gate1 = collected["gate1"] or {}
    versions = meta.get("versions") or {}
    return {
        "lock_record_version": LOCK_RECORD_VERSION,
        "gate": "GATE_2",
        "locked_at": None if now is None else now.isoformat(timespec="milliseconds"),
        "locked_by": locked_by,
        "decision_record": "docs/decisions/DR-170-gate2-lock.md",
        "run": {
            "run_id": meta.get("run_id"), "results_dir_name": collected["run_dir"].name,
            "repo_commit": collected["run_commit"],
            "expected": {"ref": collected["expected"], "commit": collected["expected_sha"]},
            "simulator_commit": prov.get("simulator_commit"), "simulator_version": meta.get("simulator_version"),
            "customer_seed": versions.get("customer_seed"), "num_customers": meta.get("num_customers"),
            "profile": meta.get("profile"), "timeline": meta.get("timeline"),
            "arm_counts": (meta.get("rct") or {}).get("arm_counts"),
        },
        "gate1_lock": {
            "declaration": gate1.get("declaration"), "locked_at": gate1.get("locked_at"),
            "locked_by": gate1.get("locked_by"), "simulator_commit": gate1.get("simulator_commit"),
            "sha256": None if not collected["gate1_text"] else _sha256(collected["gate1_text"]),
            "canonical_files_at_run_commit": collected.get("gate1_canonical"),
        },
        "baseline_rule": {
            "names": [r for r in rows if r["group"] == "baseline_rule"],
            "tag": tag_comparison(collected["root"], [r for r in rows if r["group"] == "baseline_rule"])
            if rows else None,
        },
        "budget_cap": {
            "names": [r for r in rows if r["group"] == "budget_cap"],
            "c_rule_krw": budget.get("c_rule_planned_krw"), "c_rule_definition": budget.get("c_rule_definition"),
            "source": budget.get("source"), "planning_costs_krw": meta.get("planning_costs_krw"),
            "planning_costs_source": meta.get("planning_costs_source"),
        },
        "baseline_results": {
            **{s: _baseline_entry(details.get(s)) for s in BASELINE_STRATEGIES},
            "files": {name: _file_sha256(collected["run_dir"] / name) for name in HASHED_RESULT_FILES},
        },
        "branch_invariance": {
            "status": invariance.get("status"), "result": invariance.get("result"),
            "complete": invariance.get("complete"), "run_id": invariance.get("run_id"),
            "branches": invariance.get("branches"), "missing_branches": invariance.get("missing_branches"),
            "groups": {g: {"n_customers": v.get("n_customers"),
                           "n_differing": {b: x.get("n_differing_vs_reference")
                                           for b, x in (v.get("by_branch") or {}).items()}}
                       for g, v in (invariance.get("groups") or {}).items()},
        },
        "checks": [check.to_json() for check in collected["checks"]],
        "release_procedure": RELEASE_PROCEDURE,
    }


def _human(locked_by: str | None) -> str:
    name = (locked_by or "").strip()
    if not name or name.lower() in NOT_HUMAN:
        raise Gate2LockViolation(f"locked_by={locked_by!r} 는 사람 이름이 아니다 — 봉인은 책임 소재가 있는 서명이다")
    return name


def record(run_dir: Path, *, expected: str, locked_by: str, now: datetime | None = None,
           root: Path | None = None, path: Path = LOCK_RECORD) -> dict[str, Any]:
    """봉인 기록을 쓴다. 조건(G4)이 하나라도 충족(True)이 아니거나 기록이 이미 있으면 ``Gate2LockViolation`` — 아무것도
    쓰지 않는다(이미 있는 봉인을 덮어쓰면 해제 절차 없이 Baseline 을 바꾸는 것이다)."""
    from src.measurement.config_loader import dump_yaml

    name = _human(locked_by)
    root = Path(root) if root is not None else REPO_ROOT
    if (root / path).exists():
        raise Gate2LockViolation(f"{path.as_posix()} 가 이미 있다 — 덮어쓰지 않는다. {RELEASE_PROCEDURE}")
    collected = collect(run_dir, expected, root)
    unmet = [c for c in collected["checks"] if c.met is not True]
    if unmet:
        raise Gate2LockViolation(
            "봉인 조건이 충족되지 않아 기록하지 않는다:\n"
            + "\n".join(f"  {c.id} ({'미충족' if c.met is False else '확인하지 못했다'}) {c.title} — {c.evidence}"
                        for c in unmet))
    payload = build_record(collected, locked_by=name, now=now or datetime.now(KST))
    absent = [n for n, digest in payload["baseline_results"]["files"].items() if digest is None]
    if absent:
        raise Gate2LockViolation(f"결과 파일 해시를 낼 수 없다 {absent} — 기록하지 않는다")
    dump_yaml(root / path, payload, header=(
        "# GATE 2 Lock 기록. **사람이 손으로 쓰지 않는다** — src/orchestration/gate2_lock.record() 가 쓴다.\n"
        "# 손으로 고치면 verify 가 mismatch 를 낸다. 해제 절차는 release_procedure(DR-170-gate2-lock)."))
    return payload


def verify(root: Path | None = None, path: Path = LOCK_RECORD) -> dict[str, Any]:
    """지금 저장소의 지문을 기록과 대조한다 — ``not_started`` · ``match`` · ``mismatch`` · ``unreadable``."""
    root = Path(root) if root is not None else REPO_ROOT
    target = root / path
    if not target.exists():
        return {"status": "not_started", "reason": f"{path.as_posix()} 가 없다 — GATE 2 를 봉인하지 않았다", "names": []}
    try:
        from src.measurement.config_loader import load_yaml

        loaded = load_yaml(target)
        recorded = [*loaded["baseline_rule"]["names"], *loaded["budget_cap"]["names"]]
    except Exception as error:  # noqa: BLE001 — 읽지 못한 기록을 '봉인 없음' 으로 떨어뜨리지 않는다
        return {"status": "unreadable", "reason": f"{type(error).__name__}: {error}", "names": []}
    current = {(r["file"], r["name"]): r for r in fingerprints(worktree_reader(root))}
    rows = []
    for row in recorded:
        now = current.get((row["file"], row["name"])) or {}
        same = row.get("sha256") is not None and now.get("sha256") == row.get("sha256")
        rows.append({"file": row["file"], "name": row["name"], "state": "match" if same else "mismatch",
                     "recorded": row.get("sha256"), "current": now.get("sha256"), "reason": now.get("reason")})
    recorded_keys = {(r["file"], r["name"]) for r in recorded}
    absent = sorted(n for (f, n) in current if (f, n) not in recorded_keys)
    # 필수 이름이 기록에 없으면 대조하지 않은 것이다 — match 로 내지 않는다(PR #327 리뷰).
    return {
        "status": "match" if rows and not absent and all(r["state"] == "match" for r in rows) else "mismatch",
        "locked_at": loaded.get("locked_at"), "locked_by": loaded.get("locked_by"),
        "run_commit": (loaded.get("run") or {}).get("repo_commit"),
        "names": rows, "mismatched": [r["name"] for r in rows if r["state"] != "match"],
        "not_in_record": absent,
    }


# ── CLI ───────────────────────────────────────────────────────────────────


def _print_checks(checks: list[Check]) -> None:
    mark = {True: "충족", False: "미충족", None: "확인 못 함"}
    for check in checks:
        print(f"{check.id} [{mark[check.met]}] {check.title} — {check.evidence}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="GATE 2 Baseline Freeze 기록 (DR-170-gate2-lock)")
    sub = parser.add_subparsers(dest="command", required=True)
    for command in ("check", "record"):
        one = sub.add_parser(command)
        one.add_argument("run_dir", type=Path, help="Baseline 실행의 결과 폴더(run_meta.json · branch_invariance.json)")
        one.add_argument("--expected-commit", required=True, help="Baseline 을 돌린 태그 또는 커밋")
        if command == "check":
            one.add_argument("--json", action="store_true", help="기록 미리 보기 전체를 JSON 으로 출력")
        else:
            one.add_argument("--locked-by", required=True, help="서명하는 사람의 이름(에이전트 불가)")
    sub.add_parser("verify")
    args = parser.parse_args(argv)

    if args.command == "verify":
        result = verify()
        print(json.dumps(result, ensure_ascii=False, indent=1))
        return {"match": 0, "mismatch": 1}.get(result["status"], 2)
    if args.command == "check":
        collected = collect(args.run_dir, args.expected_commit)
        _print_checks(collected["checks"])
        if args.json:
            print(json.dumps(build_record(collected, locked_by=None, now=None), ensure_ascii=False, indent=1,
                             default=str))
        return 0 if all(c.met is True for c in collected["checks"]) else 1
    try:
        payload = record(args.run_dir, expected=args.expected_commit, locked_by=args.locked_by)
    except Gate2LockViolation as error:
        print(error, file=sys.stderr)
        return 1
    print(f"기록했다: {LOCK_RECORD.as_posix()} — {payload['locked_by']} · {payload['locked_at']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
