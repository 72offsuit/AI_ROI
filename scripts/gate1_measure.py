"""GATE 1 실측 · 판정 한 번에 — 깨끗한 체크아웃에서 확인 seed 를 재고 세 판정을 돌려 결과를 커밋에 묶는다.

리드가 봉인 날 이 명령 하나로 재고 판정하며, 리뷰어는 같은 명령으로 재현한다. 판정 규칙은 여기에 없다 —
`scripts/gate1_judge.py`(필수 · 기록 검사), `scripts/gate1_churn_check.py judge`(churn 임계값 근거, data_spec §5.1
①~③), `scripts/gate1_discount_check.py`(가정 A-DISCOUNT)가 기준 파일 `config/simulator_gate1_acceptance.yaml` 로 판정한다.

순서
  1. 사전 점검(하나라도 어긋나면 아무것도 돌리지 않고 2): 인터프리터 3.12 · 의존성 import · cwd 가 저장소 루트 ·
     `git status --porcelain --untracked-files=normal` 이 비어 있음(결과를 커밋 하나에 묶으려고 더러운 트리를
     거부한다) · NEW_DIR 이 없고 저장소 작업 트리 밖(실행 중 트리를 더럽히지 않게) · 기준 파일이 저장소 안에서
     커밋돼 있고 블록이 읽힘 · --step-timeout 이 유한한 양수. HEAD · simulator_commit · 기준 파일의 마지막 커밋과
     sha256 · 플랫폼 · 시작 시각(UTC · KST)을 남긴다.
  2. seed 마다(최대 --jobs 개 동시, 하위 프로세스 · cwd 저장소 루트 · PYTHONPATH 저장소 루트):
     a. `-m src.simulator guardrails`(--hidden-root 필수 — 기본값이면 가드레일 리포트가 이전 실행분과 섞인다)
     b. `scripts/research/run_world.py` → `scripts/research/realism_check.py`
     c. `scripts/gate1_churn_check.py measure`
     명령 모양은 기준 파일 `sources.*.command(s)` · `churn_threshold.source.command` 템플릿과 같다
     (`tests/test_simulator_gate1_measure.py` 가 대조한다). 값은 기준 파일 `sample.*` · `sources.realism.world` ·
     `churn_threshold.source` 에서 읽는다.
  3. 판정 세 개 → `NEW_DIR/judges/`. 판정이 0 · 1 로 끝났는데 JSON 리포트가 없거나 리포트의 종료 코드와 다르면
     그 판정은 3 으로 본다. 끝나면 `git status` · HEAD 를 다시 보고 바뀌었거나 읽지 못하면
     `tree_changed_during_run: true` 로 2.
  4. `NEW_DIR/measure_manifest.json`(사전 점검 기록 · 모든 명령 argv · 종료 코드 · 소요 시간 · 출력 경로 · 판정
     종료 코드 · official · valid) 과 `NEW_DIR/summary.md`(봉인 PR 본문에 붙이는 판정표 — 로컬 절대 경로를 싣지 않는다)를
     함께 쓴다. 중단 · 예상 밖 예외로 끝나도(요약을 쓴 뒤라도) 그때까지 돈 단계를 담은 manifest 와 판정 무효
     summary.md 를 다시 쓰고 판정 리포트에 무효 표시를 붙인다 — manifest · summary · 판정 리포트가 늘 같은 말을 한다.

판정 무효 — 종료 코드가 2 · 3 이면 manifest `valid: false` 이고 summary.md 첫 줄이 "판정 무효 — 종료 <n>(<이유>)" 다.
그때 통과 여부 플래그(`gate1_required_pass` · `churn_met` · `discount_pass` · `churn_evidence`)는 최상위에서 비우고
`unbound_results` 아래에만 남긴다 — 커밋에 묶이지 않은 결과를 판정처럼 읽지 않게. 판정 리포트도 MD 제목에
"판정 무효 — 커밋에 묶이지 않았다", JSON 에 `valid: false` 를 붙인다.

실행 방식은 명시해야 한다 — 공식은 `--official`, 리허설은 `--rehearsal-seeds …`(둘 중 하나만, `--dry-run` 도 같다).
둘 다 없으면 아무것도 돌리지 않고 2 다. 실수로 공식 seed 를 여는 것을 막는다.

중단(Ctrl-C) — 돌던 하위 프로세스를 끝내고 남은 단계를 "중단" 으로 건너뛴 기록을 담아 manifest · summary.md 를
판정 무효(2)로 남긴다.

리허설 — `--rehearsal-seeds 42 43 44 45 46` 이면 기준 파일 사본(`NEW_DIR/criteria-rehearsal.yaml`, `sample.seeds` 교체,
`version` 에 `-rehearsal`)으로 판정하고 manifest · 판정 JSON 에 `official: false`, 모든 리포트 제목에 "리허설 — 공식 판정
아님" 을 붙인다. 확인 seed(기준 `sample.seeds`)와 겹치면 거부한다 — 확인 seed 를 봉인 전에 열지 않는다.
`--rehearsal-customers N` 은 사본의 `sample.customers` 도 바꾼다(빠른 연습용, 리허설에서만).

종료 코드 (심각한 쪽이 이긴다: 3 > 2 > 1 > 0)
    0  gate1_judge 필수 검사 통과 ∧ A-DISCOUNT 통과. churn 임계값 근거 미충족(met=false)은 종료 코드를 바꾸지
       않고 manifest `churn_met: false` 로 남긴다(기준 on_fail — CHURN_DEFINITION_v1 이 PARTIAL 로 남을 뿐이다).
    1  gate1_judge 필수 검사 실패(gate1_judge 1) 또는 A-DISCOUNT 실패(discount 1). 판정은 끝났다.
    2  판정 무효 — 사전 점검 실패(--official · --rehearsal-seeds 를 고르지 않음 포함), seed 단계 실패(0 이 아닌
       종료 · 시간 초과 · 기대 출력 없음), 어느 판정의 입력 오류(2), 실행 중 트리 · HEAD 변경(또는 다시 읽지 못함),
       사용자 중단(Ctrl-C), 명령줄 인자 오류(--official 과 --rehearsal-seeds 를 함께 줌 포함).
    3  판정 무효 — 어느 판정의 내부 오류(3) · 예상 밖 종료 코드 · 리포트 없음 · 리포트와 다른 종료 코드,
       이 스크립트의 예상 밖 예외.
    판정하지 않은 것을 통과로 적지 않는다 — 2 · 3 은 어느 쪽도 통과가 아니다.

사용 (저장소 루트에서)
    python3.12 scripts/gate1_measure.py --official --out <저장소 밖 새 디렉터리> \\
        [--criteria config/simulator_gate1_acceptance.yaml] [--jobs 5] [--dry-run]
    python3.12 scripts/gate1_measure.py --rehearsal-seeds 42 43 44 45 46 --out <저장소 밖 새 디렉터리> [--dry-run]
"""

from __future__ import annotations

import argparse
import concurrent.futures
import hashlib
import importlib
import importlib.metadata
import json
import math
import os
import platform
import shlex
import subprocess
import sys
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable

# 같은 디렉터리의 gate1_* 스크립트를 import 한다. sys.path[0] 에 기대지 않는다 — `python -P` · PYTHONSAFEPATH 나
# 다른 cwd 에서 불러도 찾도록 이 파일의 디렉터리를 직접 넣는다. PyYAML 은 gate1_judge 가 쓸 때만 import 한다.
_SCRIPTS_DIR = str(Path(__file__).resolve().parent)
if _SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, _SCRIPTS_DIR)

import gate1_churn_check as cc  # noqa: E402
import gate1_discount_check as dc  # noqa: E402
import gate1_judge as gj  # noqa: E402
from gate1_judge import EXIT_FAIL, EXIT_INPUT_ERROR, EXIT_INTERNAL_ERROR, EXIT_PASS, InputError  # noqa: E402

REPO = Path(__file__).resolve().parents[1]
DEFAULT_CRITERIA = "config/simulator_gate1_acceptance.yaml"
# gate1_judge 의 가드레일 띠 정본(gate1_judge 기본값과 같다). churn 임계값 · 단가 config 는 기준 블록이 가리키는 파일을 쓴다.
GUARDRAIL_BANDS_CONFIG = "config/simulator_config.yaml"

# 기준 파일 `environment` 와 requirements.txt 머리의 전체 파이프라인 런타임(#207).
REQUIRED_PYTHON = (3, 12)
# import 이름 → 배포 이름(버전 기록용).
REQUIRED_MODULES = {"yaml": "PyYAML", "numpy": "numpy", "pandas": "pandas", "pyarrow": "pyarrow",
                    "jsonschema": "jsonschema", "referencing": "referencing"}

DEFAULT_STEP_TIMEOUT_S = 6 * 3600
KST = timezone(timedelta(hours=9))
REHEARSAL_TITLE = "리허설 — 공식 판정 아님"
REHEARSAL_CRITERIA = "criteria-rehearsal.yaml"
REHEARSAL_VERSION_SUFFIX = "-rehearsal"
NEW_DIR_TOKEN = "<NEW_DIR>"
MANIFEST = "measure_manifest.json"
SUMMARY = "summary.md"
SEED_STEP_ORDER = ("guardrail", "world", "realism", "churn_measure")
# 통과 여부 플래그 — 판정 무효면 최상위에서 비우고 unbound_results 아래로 옮긴다.
VERDICT_KEYS = ("gate1_required_pass", "churn_met", "discount_pass", "churn_evidence")
INVALID_TITLE = "판정 무효 — 커밋에 묶이지 않았다"
INTERRUPTED = "사용자 중단"
PICK_MODE = ("실행 방식을 고른다 — 공식 실측은 --official, 리허설은 --rehearsal-seeds <seed…>"
             " (둘 중 하나만. --dry-run 도 같다)")


# ── 계획 ─────────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class Step:
    name: str
    seed: int | None
    argv: tuple[str, ...]
    log_dir: Path
    outputs: dict[str, str]
    # 성공(0) 뒤 정확히 하나씩 있어야 하는 출력 (디렉터리, glob). 없으면 단계 실패다.
    expect: tuple[tuple[str, str], ...] = ()
    after: str | None = None   # 같은 seed 안에서 먼저 성공해야 하는 단계

    @property
    def stdout(self) -> Path:
        return self.log_dir / f"{self.name}.stdout.log"

    @property
    def stderr(self) -> Path:
        return self.log_dir / f"{self.name}.stderr.log"


@dataclass(frozen=True)
class Plan:
    new_dir: Path
    official: bool
    criteria_arg: str            # 판정 argv 에 넣는 기준 파일 경로
    rehearsal_criteria: Path | None
    seeds: tuple[int, ...]
    customers: int
    seed_steps: dict[int, tuple[Step, ...]]
    judge_steps: tuple[Step, ...]


def seed_steps(seed: int, new_dir: Path, customers: int, criteria, world_conditions,
               python: str) -> tuple[Step, ...]:
    """seed 하나의 측정 명령. 모양은 기준 파일 템플릿과 같아야 한다(테스트가 대조)."""
    root = new_dir / f"seed-{seed}"
    logs = root / "logs"
    guardrail, world, warmup = root / "guardrail", root / "world", root / "warmup"
    realism = root / "realism.json"
    guardrail_reports = guardrail / "hidden" / "ground_truth" / "guardrails"
    return (
        Step("guardrail", seed, (
            python, "-m", "src.simulator", "guardrails", "--seed", str(seed), "--customers", str(customers),
            "--profile", criteria.guardrail_profile, "--warmup-days", str(criteria.guardrail_warmup_days),
            "--output-root", str(guardrail / "out"), "--hidden-root", str(guardrail / "hidden"),
        ), logs, {"guardrail_reports": str(guardrail_reports)},
            # 가드레일 CLI 는 리포트를 `<hidden-root>/ground_truth/guardrails/guardrails-*.json` 에 쓴다.
            expect=((str(guardrail_reports), gj.GUARDRAIL_GLOB),)),
        Step("world", seed, (
            python, "scripts/research/run_world.py", "--seed", str(seed), "--customers", str(customers),
            "--out", str(world), "--profile", world_conditions.profile, "--days", str(world_conditions.days),
            "--assign-day", str(world_conditions.assign_day),
        ), logs, {"world": str(world)},
            expect=((str(world), dc.META_FILE), (str(world), dc.ASSIGNMENTS_FILE),
                    (str(world / dc.ORDERS_FILE.parent), dc.ORDERS_FILE.name))),
        Step("realism", seed, (
            python, "scripts/research/realism_check.py", "--events", str(world / "raw" / "main"),
            "--exchange", str(world / "raw" / "simulator_exchange"), "--assignments", str(world / dc.ASSIGNMENTS_FILE),
            "--out-json", str(realism),
        ), logs, {"realism": str(realism)}, expect=((str(root), realism.name),), after="world"),
        Step("churn_measure", seed, (
            python, "scripts/gate1_churn_check.py", "measure", "--seed", str(seed), "--customers", str(customers),
            "--out", str(warmup),
        ), logs, {"churn_intervals": str(warmup / cc.INTERVALS_FILE)}, expect=((str(warmup), cc.INTERVALS_FILE),)),
    )


def judge_steps(plan_seeds: dict[int, tuple[Step, ...]], new_dir: Path, criteria_arg: str,
                churn_config: str, economic_config: str, python: str) -> tuple[Step, ...]:
    judges = new_dir / "judges"

    def outputs(seed: int, key: str) -> str:
        return next(s.outputs[key] for s in plan_seeds[seed] if key in s.outputs)

    seeds = sorted(plan_seeds)
    paths = {name: (str(judges / f"{name}.json"), str(judges / f"{name}.md"))
             for name in ("gate1_judge", "churn_threshold", "a_discount")}
    return (
        Step("gate1_judge", None, (
            python, "scripts/gate1_judge.py", "--criteria", criteria_arg, "--simulator-config", GUARDRAIL_BANDS_CONFIG,
            "--guardrail", *(outputs(s, "guardrail_reports") for s in seeds),
            "--realism", *(outputs(s, "realism") for s in seeds),
            "--out-json", paths["gate1_judge"][0], "--out-md", paths["gate1_judge"][1],
        ), judges, {"json": paths["gate1_judge"][0], "md": paths["gate1_judge"][1]}),
        Step("churn_threshold", None, (
            python, "scripts/gate1_churn_check.py", "judge", "--criteria", criteria_arg,
            "--simulator-config", churn_config, "--intervals", *(outputs(s, "churn_intervals") for s in seeds),
            "--out-json", paths["churn_threshold"][0], "--out-md", paths["churn_threshold"][1],
        ), judges, {"json": paths["churn_threshold"][0], "md": paths["churn_threshold"][1]}),
        Step("a_discount", None, (
            python, "scripts/gate1_discount_check.py", "--criteria", criteria_arg,
            "--economic-config", economic_config, "--worlds", *(outputs(s, "world") for s in seeds),
            "--out-json", paths["a_discount"][0], "--out-md", paths["a_discount"][1],
        ), judges, {"json": paths["a_discount"][0], "md": paths["a_discount"][1]}),
    )


# ── 사전 점검 ─────────────────────────────────────────────────────────────────

def _git(repo: Path, *args: str) -> str:
    result = subprocess.run(["git", *args], cwd=repo, capture_output=True, text=True, timeout=30, check=False)
    if result.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} 실패({result.returncode}): {result.stderr.strip()}")
    return result.stdout


def git_state(repo: Path) -> dict[str, Any]:
    """HEAD 와 `git status --porcelain` — 실행 전후를 비교해 결과가 한 커밋에 묶였는지 본다.

    `--untracked-files=normal` 을 명시한다 — 사용자 git 설정(status.showUntrackedFiles=no)이 새 파일을 숨기지 않게.
    """
    porcelain = _git(repo, "status", "--porcelain", "--untracked-files=normal")
    return {"head": _git(repo, "rev-parse", "HEAD").strip(), "porcelain": porcelain,
            "clean": porcelain.strip() == ""}


def _now() -> dict[str, str]:
    moment = datetime.now(timezone.utc)
    return {"utc": moment.isoformat(timespec="seconds"), "kst": moment.astimezone(KST).isoformat(timespec="seconds")}


def check_new_dir(new_dir: Path, repo: Path, problems: list[str]) -> None:
    """NEW_DIR 은 없어야 하고 저장소 작업 트리 밖이어야 한다(심볼릭 링크를 풀어 비교한다)."""
    resolved = new_dir.resolve()
    if new_dir.exists() or resolved.exists():
        problems.append(f"--out {new_dir} 가 이미 있다 — 새 디렉터리를 준다(이전 실측을 덮지 않는다)")
    if resolved == repo.resolve() or resolved.is_relative_to(repo.resolve()):
        problems.append(f"--out {new_dir} 가 저장소 작업 트리 안이다 — 실행 중 트리가 더러워진다. 저장소 밖을 준다")


def check_environment(python_version: tuple[int, ...], import_module: Callable[[str], Any],
                      problems: list[str]) -> dict[str, str | None]:
    """인터프리터 버전과 의존성 import. 버전 기록을 돌려준다."""
    if tuple(python_version[:2]) != REQUIRED_PYTHON:
        problems.append(f"인터프리터가 {'.'.join(map(str, python_version[:3]))} 다 — "
                        f"{'.'.join(map(str, REQUIRED_PYTHON))} 로 실행한다(기준 파일 environment)")
    versions: dict[str, str | None] = {}
    for name, distribution in REQUIRED_MODULES.items():
        try:
            import_module(name)
        except ImportError as exc:
            problems.append(f"{name} 를 import 하지 못했다({exc}) — pip install -r requirements.txt -r requirements-dev.txt")
            continue
        try:
            versions[distribution] = importlib.metadata.version(distribution)
        except importlib.metadata.PackageNotFoundError:
            versions[distribution] = None
    return versions


def check_repo(repo: Path, cwd: Path, problems: list[str]) -> dict[str, Any] | None:
    """cwd 가 저장소 루트이고 트리가 깨끗한지. 깨끗하지 않으면 바뀐 경로 일부를 보여준다."""
    if cwd.resolve() != repo.resolve():
        problems.append(f"cwd {cwd} 가 저장소 루트 {repo} 가 아니다 — 저장소 루트에서 실행한다")
    try:
        top = Path(_git(repo, "rev-parse", "--show-toplevel").strip()).resolve()
        state = git_state(repo)
    except (OSError, RuntimeError, subprocess.SubprocessError) as exc:
        problems.append(f"git 상태를 읽지 못했다: {exc}")
        return None
    if top != repo.resolve():
        problems.append(f"{repo} 가 git 작업 트리 루트({top})가 아니다")
    if not state["clean"]:
        changed = state["porcelain"].splitlines()
        problems.append(f"작업 트리가 깨끗하지 않다(git status --porcelain {len(changed)}줄) — 커밋하거나 치운 뒤 "
                        f"실행한다: {changed[:5]}")
    return state


def check_step_timeout(value: Any, problems: list[str]) -> None:
    # argparse type=float 는 inf · nan 도 받는다 — 시간 제한이 없는 것과 같아 멈춘 단계가 영원히 남는다.
    if not (isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value) and value > 0):
        problems.append(f"--step-timeout {value!r} 는 유한한 양수(초)여야 한다")


def _criteria_record(path: Path, repo: Path, problems: list[str]) -> dict[str, Any]:
    record: dict[str, Any] = {"path": str(path)}
    if not path.is_file():
        problems.append(f"기준 파일 {path} 가 없다")
        return record
    record["sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
    resolved = path.resolve()
    if not resolved.is_relative_to(repo.resolve()):
        problems.append(f"기준 파일 {path} 가 저장소 밖이다 — 커밋에 묶을 수 없다")
        return record
    relative = resolved.relative_to(repo.resolve()).as_posix()
    record["path"] = relative
    try:
        commit = _git(repo, "log", "-1", "--format=%H", "--", relative).strip()
    except (OSError, RuntimeError, subprocess.SubprocessError) as exc:
        problems.append(f"기준 파일의 커밋을 읽지 못했다: {exc}")
        return record
    if not commit:
        problems.append(f"기준 파일 {relative} 가 커밋돼 있지 않다")
    record["last_commit"] = commit or None
    return record


@dataclass
class Prepared:
    plan: Plan
    preflight: dict[str, Any]
    repo: Path
    criteria_text: str | None = None   # 리허설 사본 내용(공식이면 None)


def _parse_rehearsal(args: argparse.Namespace, official_seeds: tuple[int, ...], problems: list[str]) -> None:
    seeds = args.rehearsal_seeds
    official = bool(getattr(args, "official", False))
    # argparse 가 둘을 함께 주는 것을 막지만, prepare 를 직접 부르는 경로도 같은 규칙을 지키게 여기서도 본다.
    if official == (seeds is not None):
        problems.append(PICK_MODE)
    if seeds is None:
        if args.rehearsal_customers is not None:
            problems.append("--rehearsal-customers 는 --rehearsal-seeds 와 함께만 쓴다")
        return
    if len(set(seeds)) != len(seeds):
        problems.append(f"--rehearsal-seeds 에 중복이 있다 {seeds}")
    overlap = sorted(set(seeds) & set(official_seeds))
    if overlap:
        problems.append(f"--rehearsal-seeds {overlap} 가 확인 seed(기준 sample.seeds)다 — 리허설로 열지 않는다")
    if args.rehearsal_customers is not None and args.rehearsal_customers <= 0:
        problems.append("--rehearsal-customers 는 양의 정수여야 한다")


def rehearsal_criteria_text(raw: dict[str, Any], seeds: list[int], customers: int | None, source: str,
                            commit: str | None) -> str:
    """기준 파일 사본 — `sample.seeds`(와 선택적으로 `sample.customers`)를 바꾸고 `version` 에 리허설 표시를 붙인다.

    판정 스크립트는 기준 `version` 을 리포트(JSON · MD)에 싣는다 — 그래서 리허설 리포트가 공식 판처럼 보이지 않는다.
    주석은 남지 않는다.
    """
    import yaml

    copy = json.loads(json.dumps(raw))   # 깊은 복사 — yaml 이 낸 기본형만 있다
    copy["version"] = f"{copy.get('version') or 'unversioned'}{REHEARSAL_VERSION_SUFFIX}"
    copy["sample"]["seeds"] = list(seeds)
    if customers is not None:
        copy["sample"]["customers"] = customers
    head = (f"# {REHEARSAL_TITLE}. 원본 {source} @ {commit} 의 sample.seeds 를 {list(seeds)}"
            + (f", sample.customers 를 {customers}" if customers is not None else "")
            + " 로 바꾼 사본이다. 봉인 판정에 쓰지 않는다.\n")
    return head + yaml.safe_dump(copy, allow_unicode=True, sort_keys=False)


def prepare(args: argparse.Namespace, *, repo: Path = REPO, cwd: Path | None = None,
            python_version: tuple[int, ...] = tuple(sys.version_info),
            import_module: Callable[[str], Any] = importlib.import_module, python: str = sys.executable) -> Prepared:
    """사전 점검을 모두 하고 계획을 세운다. 하나라도 어긋나면 모든 문제를 모아 `InputError`."""
    problems: list[str] = []
    started = _now()
    new_dir = Path(args.out).expanduser()
    if not new_dir.is_absolute():
        new_dir = (cwd or Path.cwd()) / new_dir
    check_new_dir(new_dir, repo, problems)
    if args.jobs < 1:
        problems.append("--jobs 는 1 이상이어야 한다")
    check_step_timeout(args.step_timeout, problems)
    versions = check_environment(python_version, import_module, problems)
    state = check_repo(repo, cwd or Path.cwd(), problems)
    criteria_path = Path(args.criteria)
    if not criteria_path.is_absolute():
        criteria_path = repo / criteria_path
    criteria_record = _criteria_record(criteria_path, repo, problems)
    if problems and not criteria_path.is_file():
        raise InputError(problems)

    # 기준 파일 구조는 실행 전에 전부 확인한다 — 몇 시간 잰 뒤에 블록 오타로 판정이 2 가 되지 않게.
    try:
        criteria = gj.load_criteria(criteria_path)
        raw = gj._load_yaml(criteria_path, "기준 파일")
        churn = cc.load_churn_block(raw, criteria_path)
        discount = dc.load_discount_block(raw, criteria_path)
        world_conditions = dc.load_realism_world(raw, criteria_path)
    except InputError as exc:
        raise InputError(problems + exc.problems) from exc
    except gj.MissingDependencyError as exc:
        # 의존성 누락은 위 check_environment 가 이미 적었다 — 사전 점검 실패(2)로 모아 끝낸다.
        raise InputError(problems + [str(exc)]) from exc
    # 명령 템플릿에 없는 인자는 넘기지 않는다(churn measure 는 --profile · --days, run_world 는 --config 가 없다).
    # 기준이 템플릿과 다른 값을 요구하면 템플릿대로 잰 결과가 판정에서 어긋나므로 실행 전에 멈춘다.
    if (churn.profile, churn.days) != (cc.DEFAULT_PROFILE, cc.DEFAULT_DAYS):
        problems.append(f"기준 churn_threshold.source (profile {churn.profile!r}, days {churn.days}) 가 measure 기본값 "
                        f"({cc.DEFAULT_PROFILE!r}, {cc.DEFAULT_DAYS}) 과 다르다 — 명령 템플릿과 함께 고친다")
    if world_conditions.config is not None:
        problems.append(f"기준 sources.realism.world.config {world_conditions.config!r} — 실험 config 세계는 명령 "
                        "템플릿에 --config 가 없어 잴 수 없다. 템플릿과 함께 고친다")
    churn_config = cc.split_source_ref(churn.thresholds_from, "churn_threshold.thresholds_from", problems)
    economic_config = cc.split_source_ref(discount.unit_cost_from, "a_discount.unit_cost_from", problems)
    _parse_rehearsal(args, criteria.seeds, problems)
    if problems:
        raise InputError(problems)

    official = args.rehearsal_seeds is None
    seeds = criteria.seeds if official else tuple(args.rehearsal_seeds)
    customers = criteria.customers if args.rehearsal_customers is None else args.rehearsal_customers
    rehearsal_path = None if official else new_dir / REHEARSAL_CRITERIA
    criteria_text = None if official else rehearsal_criteria_text(
        raw, list(seeds), args.rehearsal_customers, criteria_record["path"], criteria_record.get("last_commit"))
    criteria_arg = criteria_record["path"] if official else str(rehearsal_path)

    steps = {seed: seed_steps(seed, new_dir, customers, criteria, world_conditions, python) for seed in seeds}
    plan = Plan(
        new_dir=new_dir, official=official, criteria_arg=criteria_arg, rehearsal_criteria=rehearsal_path,
        seeds=tuple(seeds), customers=customers, seed_steps=steps,
        judge_steps=judge_steps(steps, new_dir, criteria_arg, churn_config[0], economic_config[0], python),
    )
    preflight = {
        "started_at": started,
        "python": {"version": platform.python_version(), "executable": python, "implementation":
                   platform.python_implementation()},
        "platform": platform.platform(),
        "dependencies": versions,
        "repo": str(repo),
        "head": state["head"],
        "clean_tree": state["clean"],
        "simulator_commit": cc.simulator_commit(repo),
        "criteria": criteria_record,
        "criteria_version": criteria.version,
        "criteria_pending": criteria.pending,
        "argv": list(getattr(args, "argv_record", [])),
    }
    return Prepared(plan=plan, preflight=preflight, repo=repo, criteria_text=criteria_text)


# ── 실행 ─────────────────────────────────────────────────────────────────────

def child_env(repo: Path) -> dict[str, str]:
    env = dict(os.environ)
    env["PYTHONPATH"] = str(repo)
    return env


# 돌고 있는 하위 프로세스 — 중단(Ctrl-C) 때 끝내려고 모은다.
_RUNNING: set[subprocess.Popen] = set()
_RUNNING_LOCK = threading.Lock()


def _execute(argv: tuple[str, ...], repo: Path, env: dict[str, str], stdout: Path, stderr: Path,
             timeout: float | None, stop: threading.Event | None = None) -> int | None:
    """명령 하나를 돌린다. 시간 초과면 프로세스를 죽이고 None. `stop` 이 이미 서 있으면 띄운 즉시 끝낸다."""
    with stdout.open("w", encoding="utf-8") as out, stderr.open("w", encoding="utf-8") as err:
        proc = subprocess.Popen(list(argv), cwd=repo, env=env, stdin=subprocess.DEVNULL, stdout=out, stderr=err)
        # 등록과 멈춤 확인을 같은 잠금 안에서 한다 — terminate_running 도 이 잠금 안에서 stop 을 세우고 목록을
        # 읽으므로, 그 사이에 띄운 프로세스는 목록에 잡히거나 여기서 stop 을 보게 된다(둘 다 놓치는 틈이 없다).
        with _RUNNING_LOCK:
            _RUNNING.add(proc)
            stopped = stop is not None and stop.is_set()
        try:
            if stopped:
                _stop_process(proc)
                return proc.wait()
            return proc.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()
            return None
        except BaseException:
            # 주 스레드에서 Ctrl-C 를 받으면(판정 단계) 아래 finally 가 목록에서 빼기 전에 자식을 끝낸다.
            _stop_process(proc)
            raise
        finally:
            with _RUNNING_LOCK:
                _RUNNING.discard(proc)


def terminate_running(stop: threading.Event | None = None, grace_s: float = 10.0) -> None:
    """`stop` 을 세우고 돌고 있는 하위 프로세스를 끝낸다(SIGTERM, 유예 뒤 SIGKILL). 터미널 Ctrl-C 는 이미 자식에게도
    가지만, 부모에게만 신호가 온 경우(kill -INT)에도 자식이 남지 않게 한다."""
    with _RUNNING_LOCK:
        if stop is not None:
            stop.set()
        procs = [proc for proc in _RUNNING if proc.poll() is None]
    for proc in procs:
        proc.terminate()   # 먼저 모두에게 알리고 기다린다 — 하나씩 기다리면 유예가 프로세스 수만큼 늘어난다
    deadline = time.monotonic() + grace_s
    for proc in procs:
        try:
            proc.wait(timeout=max(0.0, deadline - time.monotonic()))
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()


def _stop_process(proc: subprocess.Popen, grace_s: float = 10.0) -> None:
    if proc.poll() is not None:
        return
    proc.terminate()
    try:
        proc.wait(timeout=grace_s)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait()


def run_step(step: Step, repo: Path, env: dict[str, str], timeout: float | None,
             stop: threading.Event | None = None) -> dict[str, Any]:
    step.log_dir.mkdir(parents=True, exist_ok=True)
    started = time.monotonic()
    try:
        code = _execute(step.argv, repo, env, step.stdout, step.stderr, timeout, stop)
        status = "ok" if code == 0 else ("timeout" if code is None else "failed")
        note = None
    except OSError as exc:
        code, status, note = None, "error", f"{type(exc).__name__}: {exc}"
    record = {
        "name": step.name, "seed": step.seed, "argv": list(step.argv), "exit_code": code, "status": status,
        "duration_s": round(time.monotonic() - started, 3), "stdout": str(step.stdout), "stderr": str(step.stderr),
        "outputs": dict(step.outputs), "note": note,
    }
    if status == "ok":
        missing = [f"{directory}/{pattern}" for directory, pattern in step.expect
                   if len([p for p in Path(directory).glob(pattern) if p.is_file()]) != 1]
        if missing:
            record["status"] = "missing_output"
            record["note"] = f"기대 출력이 정확히 하나가 아니다: {missing}"
    return record


def _skipped(step: Step, note: str) -> dict[str, Any]:
    return {"name": step.name, "seed": step.seed, "argv": list(step.argv), "exit_code": None, "status": "skipped",
            "duration_s": 0.0, "stdout": None, "stderr": None, "outputs": dict(step.outputs), "note": note}


def run_seed(steps: tuple[Step, ...], repo: Path, env: dict[str, str], timeout: float | None,
             sink: list[dict[str, Any]] | None = None, stop: threading.Event | None = None) -> list[dict[str, Any]]:
    """seed 하나의 단계를 순서대로 돌린다. 한 단계가 실패해도 그것에 기대지 않는 단계는 돌린다(진단용).

    `sink` 에는 단계가 끝날 때마다 기록을 넣는다 — 다른 seed 가 예외로 끝나도 이미 돈 단계가 manifest 에 남게.
    (list.append 는 CPython 에서 원자적이라 스레드 사이에 잠금 없이 쓴다.) `stop` 이 서 있으면 남은 단계를
    "중단" 으로 건너뛰고, 중단 중에 0 이 아니게 끝난 단계는 `interrupted` 로 적는다.
    """
    records: dict[str, dict[str, Any]] = {}
    for step in steps:
        if stop is not None and stop.is_set():
            record = _skipped(step, INTERRUPTED)
        elif step.after and records[step.after]["status"] != "ok":
            record = _skipped(step, f"{step.after} 실패로 건너뛰었다")
        else:
            record = run_step(step, repo, env, timeout, stop)
            if stop is not None and stop.is_set() and record["status"] != "ok":
                record.update(status="interrupted", note=INTERRUPTED)
        records[step.name] = record
        if sink is not None:
            sink.append(record)
    return list(records.values())


def overall_exit(steps_ok: bool, judges: dict[str, int | None], tree_changed: bool) -> int:
    """종료 코드 규칙(모듈 docstring). 심각한 쪽이 이긴다: 3 > 2 > 1 > 0."""
    codes = [EXIT_PASS]
    if not steps_ok or tree_changed:
        codes.append(EXIT_INPUT_ERROR)
    for name, code in judges.items():
        if code in (EXIT_INPUT_ERROR, EXIT_INTERNAL_ERROR):
            codes.append(code)
        elif code == EXIT_FAIL and name != "churn_threshold":
            codes.append(EXIT_FAIL)
        elif code not in (EXIT_PASS, EXIT_FAIL):
            codes.append(EXIT_INTERNAL_ERROR)   # 시간 초과 · 시그널 종료 등
    return max(codes)


def mark_title(text: str, title: str) -> str:
    """MD 첫 제목 앞에 `title` 을 붙인다. 제목이 없으면 제목 줄을 새로 단다.

    첫 줄에 이미 `title` 이 있으면 그대로 둔다 — 리허설 · 무효 표시가 어떤 순서로 몇 번 붙어도 각각 한 번씩만 남는다.
    """
    lines = text.splitlines(keepends=True)
    if lines and title in lines[0]:
        return text
    if lines and lines[0].startswith("# "):
        return f"# {title} · {lines[0][2:]}" + "".join(lines[1:])
    return f"# {title}\n\n{text}"


def mark_rehearsal(text: str) -> str:
    return mark_title(text, REHEARSAL_TITLE)


def strip_new_dir(text: str, new_dir: Path) -> str:
    """NEW_DIR 의 절대 경로(심볼릭 링크를 푼 것 포함)를 `<NEW_DIR>` 로 바꾼다 — PR 에 붙일 글에 로컬 경로를 싣지 않는다."""
    for form in sorted({str(new_dir), str(new_dir.resolve())}, key=len, reverse=True):
        text = text.replace(form, NEW_DIR_TOKEN)
    return text


def _read_report(path: str) -> dict[str, Any] | None:
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def judge_summary(name: str, code: int | None, report: dict[str, Any] | None) -> str:
    if code not in (EXIT_PASS, EXIT_FAIL) or report is None:
        meaning = {EXIT_INPUT_ERROR: "입력 오류 — 판정하지 않음", EXIT_INTERNAL_ERROR: "내부 오류 — 판정하지 않음"}
        return meaning.get(code, f"판정하지 않음(종료 {code})")
    if name == "gate1_judge":
        failed = report.get("verdict", {}).get("failed") or []
        return "필수 검사 통과" if code == EXIT_PASS else f"필수 검사 실패: {', '.join(failed)}"
    if name == "churn_threshold":
        means = " · ".join(f"P{r['quantile']} 평균 {r['mean']:.6g}일 vs {r['threshold']} {r['threshold_days']}일 "
                           f"({r['verdict']})" for r in report.get("comparisons", []))
        return f"met={'true' if report.get('met') else 'false'} — {means}"
    totals = report.get("violations_total", {})
    counts = "; ".join(f"seed {seed}: " + (", ".join(f"{arm} {n}" for arm, n in row.get("discounted_by_arm", {}).items())
                                           or "할인 주문 0건")
                       for seed, row in report.get("per_seed", {}).items())
    head = "통과 — 위반 0건" if code == EXIT_PASS else "실패 — " + ", ".join(f"{k} {v}" for k, v in totals.items())
    shortages = [f"seed {seed} {s['arm']} {s['discounted_orders']}건"
                 for seed, row in report.get("per_seed", {}).items() for s in row.get("shortages", [])]
    if shortages:
        head += f", 할인 주문 최소 미달 {', '.join(shortages)}"
    return f"{head} · 팔별 할인 주문 {counts}"


def checked_judge_code(code: int | None, report: dict[str, Any] | None) -> tuple[int | None, str | None]:
    """판정이 0 · 1 로 끝났으면 리포트가 그 결과를 실제로 남겼는지 대조한다. 어긋나면 3(내부 오류)."""
    if code not in (EXIT_PASS, EXIT_FAIL):
        return code, None
    if report is None:
        return EXIT_INTERNAL_ERROR, f"종료 {code} 인데 JSON 리포트가 없거나 읽히지 않는다 — 3 으로 본다"
    reported = report.get("verdict", {}).get("exit_code") if isinstance(report.get("verdict"), dict) else None
    if reported != code:
        return EXIT_INTERNAL_ERROR, f"종료 {code} 인데 리포트 verdict.exit_code 가 {reported!r} 다 — 3 으로 본다"
    return code, None


def invalid_reasons(manifest: dict[str, Any]) -> list[str]:
    """판정 무효(종료 2 · 3)의 이유 — summary 첫 줄과 manifest 에 싣는다."""
    reasons: list[str] = []
    failed = [f"seed {s['seed']} {s['name']} {s['status']}" for s in manifest.get("steps", []) if s["status"] != "ok"]
    if failed:
        reasons.append("측정 단계 실패: " + ", ".join(failed))
    for judge in manifest.get("judges", []):
        if judge.get("status") == "skipped":
            continue
        code = judge.get("effective_exit_code")
        if judge.get("status") in ("timeout", "error", "interrupted"):
            reasons.append(f"{judge['name']} {judge['status']}")   # 종료 코드가 없다 — 상태를 그대로 적는다
        elif code not in (EXIT_PASS, EXIT_FAIL):
            reasons.append(f"{judge['name']} 종료 {code}")
    if manifest.get("tree_changed_during_run"):
        reasons.append("실행 중 작업 트리 · HEAD 변경 또는 확인 불가")
    if manifest.get("interrupted"):
        reasons.append(INTERRUPTED)
    if manifest.get("internal_error"):
        reasons.append(f"내부 오류 {manifest['internal_error']}")
    return reasons or [f"종료 {manifest.get('exit_code')}"]


def _rel(path: str | None, new_dir: Path) -> str:
    if not path:
        return "—"
    return strip_new_dir(path, new_dir).replace(f"{NEW_DIR_TOKEN}/", "")


def render_summary(manifest: dict[str, Any], new_dir: Path) -> str:
    """봉인 PR 본문에 붙이는 요약. 경로는 NEW_DIR 기준 상대 경로로만 싣는다."""
    pre = manifest["preflight"]
    valid = manifest.get("valid", False)
    end = manifest.get("end") or {}
    lines: list[str] = []
    if not valid:
        lines += [f"# 판정 무효 — 종료 {manifest['exit_code']}({'; '.join(invalid_reasons(manifest))}). "
                  "아래 판정은 커밋에 묶이지 않았다", ""]
    title = "GATE 1 실측 요약" if manifest["official"] else f"{REHEARSAL_TITLE} · GATE 1 실측 요약"
    official = ("예" if manifest["official"] and valid
                else "아니오(리허설)" if not manifest["official"] else "아니오(판정 무효)")
    lines += [
        f"{'#' if valid else '##'} {title}",
        "",
        f"- 공식 판정: {official} · 종료 코드 **{manifest['exit_code']}**",
        f"- HEAD `{pre['head']}` · simulator_commit `{pre['simulator_commit']}` · simulator_version "
        f"`{manifest.get('simulator_version')}`",
        f"- 기준 `{pre['criteria']['path']}` @ `{pre['criteria'].get('last_commit')}` · sha256 "
        f"`{pre['criteria'].get('sha256')}` · {pre['criteria_version']}"
        + (f" · 판정에 쓴 사본 `{_rel(manifest['criteria_used'], new_dir)}`" if not manifest["official"] else ""),
        f"- 깨끗한 트리: 시작 {pre['clean_tree']} · 끝 {end.get('clean')} · 실행 중 변경 "
        f"{manifest.get('tree_changed_during_run')}",
        f"- seed {manifest['seeds']} × {manifest['customers']}명 · Python {pre['python']['version']} · {pre['platform']}",
        f"- 시작 {pre['started_at']['kst']} · 끝 {(manifest.get('finished_at') or {}).get('kst')}",
        "",
        "| 판정 | 종료 코드 | 결과 | 리포트 |",
        "|---|---|---|---|",
    ]
    for judge in manifest["judges"]:
        result = judge.get("summary", "—") if valid else "판정 무효 — 결과를 판정으로 읽지 않는다(리포트 참고)"
        lines.append(f"| {judge['name']} | {judge.get('effective_exit_code')} | {result} | "
                     f"`{_rel(judge['outputs'].get('md'), new_dir)}` |")
    if valid:
        lines += ["", f"- churn_met: {manifest.get('churn_met')} · discount_pass: {manifest.get('discount_pass')} · "
                  f"gate1_required_pass: {manifest.get('gate1_required_pass')}"]
    else:
        lines += ["", "- 통과 여부 플래그: 판정 무효라 비웠다(manifest `unbound_results` 에만 남는다)"]
    notes = [j for j in manifest["judges"] if j.get("note")]
    if notes:
        lines += [""] + [f"- {j['name']}: {_rel(j['note'], new_dir)}" for j in notes]
    failed = [s for s in manifest["steps"] if s["status"] != "ok"]
    if failed:
        lines += ["", "실패한 측정 단계:"]
        lines += [f"- seed {s['seed']} {s['name']}: {s['status']} (종료 {s['exit_code']}) "
                  f"{_rel(s.get('note'), new_dir) if s.get('note') else ''} — `{_rel(s['stderr'], new_dir)}`"
                  for s in failed]
    # 위에서 상대 경로로 바꾸지 못한 NEW_DIR 경로가 남아도 싣지 않는다.
    return strip_new_dir("\n".join(lines) + "\n", new_dir)


def _simulator_version(steps: list[dict[str, Any]]) -> str | list[str] | None:
    """측정 출력이 기록한 simulator_version(가드레일 · churn 측정). 하나가 아니면 목록 그대로 남긴다."""
    versions: set[str] = set()
    for step in steps:
        if step["status"] != "ok":
            continue
        if step["name"] == "churn_measure":
            report = _read_report(step["outputs"]["churn_intervals"])
        elif step["name"] == "guardrail":
            found = sorted(Path(step["outputs"]["guardrail_reports"]).glob(gj.GUARDRAIL_GLOB))
            report = _read_report(str(found[0])) if found else None
        else:
            continue
        if report and isinstance(report.get("simulator_version"), str):
            versions.add(report["simulator_version"])
    if not versions:
        return None
    return next(iter(versions)) if len(versions) == 1 else sorted(versions)


def _rewrite_judge_outputs(step: Step, new_dir: Path, title: str, fields: dict[str, Any]) -> None:
    """판정 리포트에 표시를 붙인다 — MD 제목 앞에 `title`, NEW_DIR 절대 경로 제거, JSON 에 `fields`.
    MD · JSON 은 둘 다 쓰거나 둘 다 안 쓴다(없는 파일은 건너뛴다)."""
    md, js = Path(step.outputs["md"]), Path(step.outputs["json"])
    outputs: list[tuple[Path, str]] = []
    if md.is_file():
        outputs.append((md, strip_new_dir(mark_title(md.read_text(encoding="utf-8"), title), new_dir)))
    report = _read_report(str(js))
    if report is not None:
        report.update(fields)
        outputs.append((js, json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False) + "\n"))
    if outputs:
        gj.write_outputs(outputs)


def _mark_rehearsal_outputs(step: Step, new_dir: Path) -> None:
    _rewrite_judge_outputs(step, new_dir, REHEARSAL_TITLE, {"official": False, "rehearsal": True})


def mark_invalid_outputs(prepared: Prepared) -> None:
    """판정 무효 — 이미 남은 판정 리포트에도 무효 표시를 붙여 리포트만 따로 읽혀도 판정처럼 보이지 않게 한다."""
    for step in prepared.plan.judge_steps:
        _rewrite_judge_outputs(step, prepared.plan.new_dir, INVALID_TITLE, {"valid": False})


def _step_key(record: dict[str, Any], seeds: tuple[int, ...]) -> tuple[int, int]:
    name = record["name"]
    return seeds.index(record["seed"]), SEED_STEP_ORDER.index(name) if name in SEED_STEP_ORDER else len(SEED_STEP_ORDER)


def execute(prepared: Prepared, jobs: int, timeout: float | None, manifest: dict[str, Any],
            stop: threading.Event | None = None) -> dict[str, Any]:
    """계획을 실행하며 호출자가 준 `manifest` 를 채운다(파일 쓰기는 호출자가). 예외로 끝나도 그때까지의 기록이 남는다.

    Ctrl-C(`KeyboardInterrupt`)가 오면 `stop` 을 세워 남은 단계를 건너뛰게 하고, 돌던 하위 프로세스를 끝낸 뒤
    (스레드 풀이 그 단계들을 기다린다) 예외를 다시 던진다 — manifest 를 쓰는 것은 호출자(main)다.
    """
    stop = stop or threading.Event()
    plan, repo = prepared.plan, prepared.repo
    # 디렉터리를 먼저 만든다 — 만들지 못했으면(다른 실행이 만듦) manifest 가 비어 있어 main 이 그 디렉터리에 쓰지 않는다.
    plan.new_dir.mkdir(parents=True, exist_ok=False)
    manifest.update({
        "schema": "gate1-measure-manifest/v1", "official": plan.official, "valid": False,
        "preflight": prepared.preflight, "criteria_used": plan.criteria_arg, "seeds": list(plan.seeds),
        "customers": plan.customers, "jobs": jobs, "step_timeout_s": timeout, "cwd": str(repo),
        "env": {"PYTHONPATH": str(repo)}, "steps": [], "judges": [],
    })
    if prepared.criteria_text is not None:
        gj.write_outputs([(plan.rehearsal_criteria, prepared.criteria_text)])
    env = child_env(repo)
    with concurrent.futures.ThreadPoolExecutor(max_workers=jobs) as pool:
        try:
            futures = [pool.submit(run_seed, plan.seed_steps[seed], repo, env, timeout, manifest["steps"], stop)
                       for seed in plan.seeds]
            for future in futures:
                future.result()
        except KeyboardInterrupt:
            # 풀을 빠져나가기 전에(= 실행 중 단계를 기다리기 전에) 멈춤을 알리고 자식을 끝낸다.
            terminate_running(stop)
            raise
    manifest["steps"].sort(key=lambda record: _step_key(record, plan.seeds))
    steps_ok = all(s["status"] == "ok" for s in manifest["steps"])
    manifest["simulator_version"] = _simulator_version(manifest["steps"])

    judge_codes: dict[str, int | None] = {}
    results: dict[str, Any] = {"churn_evidence": None}
    for step in plan.judge_steps:
        if stop.is_set():
            raise KeyboardInterrupt
        if not steps_ok:
            manifest["judges"].append({"name": step.name, "seed": None, "argv": list(step.argv), "exit_code": None,
                                       "effective_exit_code": None, "status": "skipped",
                                       "outputs": dict(step.outputs), "summary": "측정 단계 실패로 돌리지 않음",
                                       "note": None})
            continue
        record = run_step(step, repo, env, timeout, stop)
        manifest["judges"].append(record)
        report = _read_report(step.outputs["json"]) if record["exit_code"] in (EXIT_PASS, EXIT_FAIL) else None
        effective, note = checked_judge_code(record["exit_code"], report)
        record["effective_exit_code"] = effective
        if note:
            record["note"] = note
            report = None
        record["summary"] = judge_summary(step.name, effective, report)
        judge_codes[step.name] = effective
        if report is not None and step.name == "churn_threshold":
            results["churn_evidence"] = report.get("evidence")
        if not plan.official:
            _mark_rehearsal_outputs(step, plan.new_dir)

    for key, name in (("gate1_required_pass", "gate1_judge"), ("churn_met", "churn_threshold"),
                      ("discount_pass", "a_discount")):
        # 판정하지 않았으면(2 · 3 · 건너뜀) None — False(판정했고 실패)와 구별한다.
        code = judge_codes.get(name)
        results[key] = None if code not in (EXIT_PASS, EXIT_FAIL) else code == EXIT_PASS

    try:
        end = git_state(repo)
        manifest["end"] = {"head": end["head"], "clean": end["clean"], "porcelain": end["porcelain"]}
        tree_changed = end["head"] != prepared.preflight["head"] or not end["clean"]
    except (OSError, RuntimeError, subprocess.SubprocessError) as exc:
        # 끝 상태를 확인하지 못하면 결과가 그 커밋에 묶였다고 말할 수 없다 — 바뀐 것과 같이 무효(2)로 본다.
        manifest["end"] = {"head": None, "clean": None, "error": f"{type(exc).__name__}: {exc}"}
        tree_changed = True
    manifest["tree_changed_during_run"] = tree_changed
    manifest["steps_ok"] = steps_ok
    manifest["finished_at"] = _now()
    manifest["exit_code"] = overall_exit(steps_ok, judge_codes, tree_changed)
    finalize_validity(manifest, results)
    if not manifest["valid"]:
        mark_invalid_outputs(prepared)
    return manifest


def finalize_validity(manifest: dict[str, Any], results: dict[str, Any]) -> None:
    """종료 코드로 판정 유효 여부를 정하고 통과 여부 플래그를 그에 맞는 자리에 둔다."""
    valid = manifest.get("exit_code") in (EXIT_PASS, EXIT_FAIL)
    manifest["valid"] = valid
    if valid:
        manifest.update(results)
        return
    manifest.update({key: None for key in VERDICT_KEYS})
    manifest["invalid_reasons"] = invalid_reasons(manifest)
    manifest["unbound_results"] = {**results, "note": "판정 무효 — 이 값들은 커밋에 묶이지 않았다. 판정으로 쓰지 않는다"}
    for judge in manifest.get("judges", []):
        if judge.get("summary") and not judge["summary"].startswith("무효(참고):"):
            judge["summary"] = f"무효(참고): {judge['summary']}"


def write_results(new_dir: Path, manifest: dict[str, Any]) -> str:
    """manifest 와 summary 를 함께 쓴다(둘 다 쓰거나 하나도 바꾸지 않는다)."""
    summary = render_summary(manifest, new_dir)
    payload = json.dumps(manifest, ensure_ascii=False, indent=2, allow_nan=False, default=str) + "\n"
    gj.write_outputs([(new_dir / MANIFEST, payload), (new_dir / SUMMARY, summary)])
    return summary


def render_dry_run(prepared: Prepared) -> str:
    plan = prepared.plan
    lines = [f"# GATE 1 실측 계획 ({'공식' if plan.official else REHEARSAL_TITLE}) — 실행하지 않았다(--dry-run)",
             f"# cwd {prepared.repo} · PYTHONPATH={prepared.repo} · NEW_DIR {plan.new_dir}",
             f"# HEAD {prepared.preflight['head']} · simulator_commit {prepared.preflight['simulator_commit']} · "
             f"기준 {prepared.preflight['criteria']['path']} @ {prepared.preflight['criteria'].get('last_commit')}"]
    if plan.rehearsal_criteria is not None:
        lines.append(f"# 기준 사본을 {plan.rehearsal_criteria} 에 쓴다 (sample.seeds={list(plan.seeds)})")
    for seed in plan.seeds:
        lines += [shlex.join(step.argv) for step in plan.seed_steps[seed]]
    lines += [shlex.join(step.argv) for step in plan.judge_steps]
    return "\n".join(lines) + "\n"


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="GATE 1 실측 · 판정 한 번에 — 종료 코드 0 통과 · 1 필수 실패 또는 A-DISCOUNT 실패 · "
                    "2 판정 무효(사전 점검 · 단계 · 입력 오류 · 트리 변경) · 3 판정 무효(내부 오류)")
    parser.add_argument("--out", required=True, help="저장소 밖의 새 디렉터리(이미 있으면 거부)")
    parser.add_argument("--criteria", default=DEFAULT_CRITERIA)
    parser.add_argument("--jobs", type=int, default=5, help="동시에 재는 seed 수")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--official", action="store_true",
                      help="공식 실측 — 기준 sample.seeds(확인 seed)로 재고 판정한다")
    mode.add_argument("--rehearsal-seeds", type=int, nargs="+", default=None,
                      help="리허설 seed — 기준 사본으로 판정하고 official=false (확인 seed 는 거부)")
    parser.add_argument("--rehearsal-customers", type=int, default=None,
                        help="리허설 사본의 sample.customers (빠른 연습용, --rehearsal-seeds 와 함께만)")
    parser.add_argument("--step-timeout", type=float, default=DEFAULT_STEP_TIMEOUT_S,
                        help=f"명령 하나의 시간 제한(초, 기본 {DEFAULT_STEP_TIMEOUT_S}) — 넘으면 단계 실패(2)")
    parser.add_argument("--dry-run", action="store_true", help="사전 점검 뒤 계획한 명령만 출력하고 실행하지 않는다")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    args.argv_record = [sys.executable, str(Path(__file__)), *(sys.argv[1:] if argv is None else argv)]
    manifest: dict[str, Any] = {}
    prepared: Prepared | None = None
    stop = threading.Event()
    try:
        prepared = prepare(args)
        if args.dry_run:
            print(render_dry_run(prepared), end="")
            return EXIT_PASS
        execute(prepared, args.jobs, args.step_timeout, manifest, stop)
        summary = write_results(prepared.plan.new_dir, manifest)
        print(summary, end="")
        return manifest["exit_code"]
    except InputError as exc:
        print("사전 점검 · 입력 오류 — 실측 · 판정하지 않았다(통과가 아니다):", file=sys.stderr)
        for problem in exc.problems:
            print(f"  - {problem}", file=sys.stderr)
        return EXIT_INPUT_ERROR
    except KeyboardInterrupt:
        terminate_running(stop)
        print(f"{INTERRUPTED} — 실측 · 판정을 끝내지 못했다(판정 무효, 통과가 아니다)", file=sys.stderr)
        # manifest 가 비어 있으면 execute 가 NEW_DIR 을 만들기 전이다 — 남의 디렉터리에 쓰지 않는다.
        if prepared is not None and manifest:
            write_partial_results(prepared, manifest, EXIT_INPUT_ERROR, interrupted=INTERRUPTED)
        return EXIT_INPUT_ERROR
    except Exception as exc:  # noqa: BLE001 — 판정 결과(0 · 1)와 섞이지 않게 예상 밖 예외를 3 으로 모은다
        print(f"내부 오류 — 실측 · 판정을 끝내지 못했다(통과가 아니다): {type(exc).__name__}: {exc}", file=sys.stderr)
        if prepared is not None and manifest:
            write_partial_results(prepared, manifest, EXIT_INTERNAL_ERROR,
                                  internal_error=f"{type(exc).__name__}: {exc}")
        return EXIT_INTERNAL_ERROR


def write_partial_results(prepared: Prepared, manifest: dict[str, Any], exit_code: int, **cause: str) -> None:
    """중단 · 예상 밖 예외 — 그때까지 돈 단계를 담은 manifest 와 summary.md 를 판정 무효로 함께 다시 쓰고, 이미 남은
    판정 리포트에도 무효 표시를 붙인다. 정상 요약을 이미 쓴 뒤(출력 중 중단 등)라도 덮어 무효로 맞춘다.
    `cause` 는 `interrupted` 또는 `internal_error`."""
    plan = prepared.plan
    manifest.setdefault("official", plan.official)
    manifest.setdefault("preflight", prepared.preflight)
    manifest.setdefault("criteria_used", plan.criteria_arg)
    manifest.setdefault("seeds", list(plan.seeds))
    manifest.setdefault("customers", plan.customers)
    manifest.setdefault("steps", [])
    manifest.setdefault("judges", [])
    manifest.update(exit_code=exit_code, finished_at=_now(), **cause)
    manifest["steps"] = sorted(manifest["steps"], key=lambda record: _step_key(record, plan.seeds))
    # 이미 무효로 정리된 manifest 면 결과는 unbound_results 에 있다 — 최상위의 빈 값으로 덮지 않는다.
    previous = manifest.get("unbound_results") or {key: manifest.get(key) for key in VERDICT_KEYS}
    finalize_validity(manifest, {key: previous.get(key) for key in VERDICT_KEYS})
    try:
        if not plan.official:
            # 리포트를 쓰고 돌아오지 못한 판정(중단 · 예외)은 리허설 표시도 받지 못했다 — 여기서 먼저 붙인다.
            for step in plan.judge_steps:
                _mark_rehearsal_outputs(step, plan.new_dir)
        mark_invalid_outputs(prepared)
        write_results(plan.new_dir, manifest)
    except Exception:  # noqa: BLE001 — 원래 오류를 가리지 않는다(종료 코드와 stderr 가 이미 알린다)
        try:
            # 요약을 만들지 못해도 manifest 만큼은 남긴다.
            gj.write_outputs([(plan.new_dir / MANIFEST,
                               json.dumps(manifest, ensure_ascii=False, indent=2, default=str) + "\n")])
        except Exception:  # noqa: BLE001
            pass


if __name__ == "__main__":
    sys.exit(main())
