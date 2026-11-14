"""GATE 1 판정 — 기준 파일로 확인 seed 실측을 판정하고, 범위 밖이면 실패로 끝난다.

기준은 `config/simulator_gate1_acceptance.yaml`(근거 `docs/decisions/DR-208-gate1-acceptance-criteria.md`)이다.
이 스크립트는 띠를 정하지 않는다 — 가드레일 띠는 `config/simulator_config.yaml` `guardrails`, F 항목 띠는
realism JSON 의 `reference.band`(= `scripts/research/realism_check.py` `BANDS`)를 읽어 쓴다.

- 필수 검사(`verdict.required`): 가드레일 리포트(`python -m src.simulator guardrails` 의 `guardrails-*.json`)
  `checks[]` 중 `role: 판정`. 크기 띠는 seed 평균이 띠 안 ∧ 각 seed 가 pass · borderline,
  `quadrant_consistency_*` 는 각 seed |gap| ≤ abs_max_bp. 하나라도 못 맞추면 종료 코드 1.
  가드레일 리포트의 `role: 판정` 값은 이탈률이 ① `active42`, 처치 지표가 ② `eligible_spec41` 모집단이다(DR-194).
  기준 `checks[].population` 이 그 조합이 아니면 이 스크립트는 판정할 수 없으므로 입력 오류다(모집단 전환은 지원하지 않는다).
- 기록 검사(`verdict.recorded`): realism JSON(`realism_check.py --out-json`) `metrics[]`. seed 평균을
  realism_check 규칙으로 판정해 싣기만 한다 — 종료 코드에 영향이 없다.
- 참고(`reference_only`): 판정하지 않고 평균값만 싣는다.
- 기준 `pending` 이 있어도 종료 코드는 바뀌지 않는다(정책 확인 대기). 판정표 머리에 ★ 로, `--out-json` 의
  `criteria.pending` 에 값 그대로 싣는다.

종료 코드
    0  필수 검사 모두 통과
    1  필수 검사 하나 이상 실패(판정은 끝났다)
    2  입력 오류 — 판정하지 않았다. 입력이 기준과 맞지 않는다: seed 누락 · 중복 · 초과, 검사 이름 없음,
       띠 불일치, 모집단 조합 불가, 실측 조건(`sample.guardrail_*`) 불일치 · 키 없음, simulator_version 불일치
       · 확인 불가, JSON 깨짐 · Infinity · NaN, 명령줄 인자 오류(argparse 도 2 로 끝난다).
    3  내부 오류 — 판정하지 않았거나 판정을 남기지 못했다. 위로 분류되지 않은 예외(PyYAML 미설치, 출력 파일
       쓰기 실패, 스크립트 결함 등). 입력을 고쳐서 풀리는 문제가 아니므로 2 와 나눈다. 출력 파일은 전부 쓰거나
       하나도 바꾸지 않고(`write_outputs`), stdout 판정표는 파일을 다 쓴 뒤에만 낸다.
    판정하지 않은 것을 통과로 적지 않는다 — 2 · 3 은 어느 쪽도 통과가 아니다.

realism_check.py 는 pandas 가 있어야 import 되므로 판정 함수(`judge` · `judge_open_lower` · `worst`)를
여기 다시 둔다. 둘이 같은지는 `tests/test_simulator_gate1_judge.py` 가 대조한다.

사용
    python scripts/gate1_judge.py --guardrail <dir|json>... --realism <dir|json>... \\
        [--criteria config/simulator_gate1_acceptance.yaml] [--simulator-config config/simulator_config.yaml] \\
        [--out-json judge.json] [--out-md judge.md]
"""

from __future__ import annotations

import argparse
import json
import math
import os
import sys
import tempfile
from dataclasses import dataclass
from fractions import Fraction
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]
DEFAULT_CRITERIA = REPO / "config" / "simulator_gate1_acceptance.yaml"
DEFAULT_SIMULATOR_CONFIG = REPO / "config" / "simulator_config.yaml"

EXIT_PASS = 0
EXIT_FAIL = 1
EXIT_INPUT_ERROR = 2
EXIT_INTERNAL_ERROR = 3

JUDGED_ROLE = "판정"
GUARDRAIL_GLOB = "guardrails-*.json"
REALISM_GLOB = "*.json"

BORDERLINE_FRACTION = 0.20

# 가드레일 리포트가 `role: 판정` 값을 재는 모집단(src/simulator/_internal/guardrails.py · DR-194). 기준의 정본이
# 아니라 이 스크립트가 읽을 수 있는 입력의 모양이다 — 기준이 다른 조합을 요구하면 판정하지 않고 멈춘다.
CHURN_CHECK = "churn_rate"
CHURN_POPULATION = "active42"
TREATMENT_POPULATION = "eligible_spec41"
# 리포트의 모집단 블록 → 전수 평가 대조에 쓰는 최상위 모집단 크기 키.
POPULATION_SIZE_KEYS = {CHURN_POPULATION: "active_customers", TREATMENT_POPULATION: "eligible_customers"}
PASSING_SEED_VERDICTS = ("pass", "borderline")

# realism `reference.band` 의 키 → `synthetic` 의 키. 띠가 [lo, hi] 하나인 항목은 band 키가 None 이다.
# realism_check 의 F 계산기가 판정에 넣는 값과 같은 키다(같은 파일의 f1~f17). 계산기가 키를 바꾸면
# 여기서 매핑이 끊겨 no_data 로 보인다 — 조용히 다른 값을 판정하지 않는다.
SYNTHETIC_KEYS: dict[str, dict[str | None, str]] = {
    "F1": {"median": "median", "mean": "mean", "p75": "p75"},
    "F2": {None: "median_cv"},
    "F3": {"median": "median", "ln_sd": "ln_sd"},
    "F4": {"orders_per_month": "orders_per_month", "aov_krw": "aov_krw"},
    "F5": {None: "nbd_shape"},
    "F6": {"top20": "top20", "top10": "top10"},
    "F7": {"order_ln_sd": "order_ln_sd", "customer_mean_aov_cv": "customer_mean_aov_cv"},
    "F8": {None: "ratio"},
    "F9": {None: "cart_abandonment_pct"},
    "F10": {None: "share"},
    "F11": {None: "rate"},
    "F13": {None: "share_returned_after_42d_gap"},
    "F17": {None: "share_non_coupon"},
}

# 참고 행으로 싣는 realism 항목(DR-208 — 1회 배정 세계라 보정 조건과 달라 판정하지 않는다).
REFERENCE_REALISM_KEYS: dict[str, tuple[str, ...]] = {
    "F12": ("churn_pct_mean",),
    "F14": ("ate_pp",),
    "F15": ("rate_pct",),
    "F16": ("sleeping_dog_pct", "persuadable_pct", "identity_gap_pp"),
}


class MissingDependencyError(Exception):
    """실행 환경에 필요한 패키지가 없다(종료 코드 3 — 입력을 고쳐서 풀리지 않는다)."""


class InputError(Exception):
    """입력이 기준과 맞지 않아 판정할 수 없다(종료 코드 2)."""

    def __init__(self, problems: list[str]) -> None:
        super().__init__("\n".join(problems))
        self.problems = problems


# ── 판정 규칙 — realism_check.py 의 judge · judge_open_lower · worst 와 같은 정의 ─────────────

def _missing(value: Any) -> bool:
    return value is None or (isinstance(value, float) and math.isnan(value))


def judge(value: float | None, lo: float | None, hi: float | None) -> str:
    """띠 [lo, hi] 판정(경계값 포함, `None` 경계는 열린 쪽). 띠 밖이지만 가까운 경계값의 ±20% 이내면 borderline."""
    if _missing(value):
        return "no_data"
    v = float(value)
    if (lo is None or v >= lo) and (hi is None or v <= hi):
        return "pass"
    if lo is not None and v < lo and v >= lo - BORDERLINE_FRACTION * abs(lo):
        return "borderline"
    if hi is not None and v > hi and v <= hi + BORDERLINE_FRACTION * abs(hi):
        return "borderline"
    return "fail"


def judge_open_lower(value: float | None, lo: float) -> str:
    """`> lo` 판정(lo 자체는 통과가 아니다). realism_check 가 F8 · F13 · F17 에 쓰는 규칙."""
    if _missing(value):
        return "no_data"
    v = float(value)
    if v > lo:
        return "pass"
    if lo != 0 and v >= lo - BORDERLINE_FRACTION * abs(lo):
        return "borderline"
    return "fail"


def worst(verdicts: list[str]) -> str:
    """여러 값의 종합. 하나라도 계산하지 못했으면 no_data."""
    if not verdicts or "no_data" in verdicts:
        return "no_data"
    for verdict in ("fail", "borderline"):
        if verdict in verdicts:
            return verdict
    return "pass"


def _is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _is_finite_number(value: Any) -> bool:
    return _is_number(value) and math.isfinite(value)


def _is_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def judged_population(check_name: str) -> str:
    """가드레일 리포트가 이 `role: 판정` 검사를 재는 모집단."""
    return CHURN_POPULATION if check_name == CHURN_CHECK else TREATMENT_POPULATION


# ── 기준 ─────────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class RequiredCheck:
    name: str
    fact: str
    population: str            # judged_population(name) 과 같음을 load_criteria 가 보장한다
    band_from: str | None      # 크기 띠 검사 — simulator_config 의 띠 경로
    abs_max_bp: int | None     # 4분면 일관성 검사 — 각 seed |값| 상한


@dataclass(frozen=True)
class Criteria:
    path: str
    version: str | None
    pending: str | None
    seeds: tuple[int, ...]
    customers: int
    guardrail_profile: str
    guardrail_warmup_days: int
    guardrail_full_evaluation: bool
    required: tuple[RequiredCheck, ...]
    recorded: tuple[str, ...]


def load_criteria(path: Path) -> Criteria:
    """기준 yaml 을 읽는다. 구조가 기대와 다르면 `InputError`."""
    raw = _load_yaml(path, "기준 파일")
    problems: list[str] = []
    sample = raw.get("sample") if isinstance(raw, dict) else None
    verdict = raw.get("verdict") if isinstance(raw, dict) else None
    if not isinstance(sample, dict) or not isinstance(verdict, dict):
        raise InputError([f"기준 파일 {path}: sample · verdict 블록이 없다"])

    seeds = sample.get("seeds")
    if not (isinstance(seeds, list) and seeds and all(isinstance(s, int) and not isinstance(s, bool) for s in seeds)):
        problems.append(f"기준 파일 {path}: sample.seeds 가 정수 목록이 아니다")
        seeds = []
    elif len(set(seeds)) != len(seeds):
        problems.append(f"기준 파일 {path}: sample.seeds 에 중복이 있다 {seeds}")
    customers = sample.get("customers")
    if not (isinstance(customers, int) and not isinstance(customers, bool) and customers > 0):
        problems.append(f"기준 파일 {path}: sample.customers 가 양의 정수가 아니다")
        customers = 0
    # 가드레일 리포트 실측 조건 — 정본은 기준 파일 한 곳이다. 없으면 기본값으로 메우지 않는다.
    profile = sample.get("guardrail_profile")
    if not (isinstance(profile, str) and profile):
        problems.append(f"기준 파일 {path}: sample.guardrail_profile 이 비어 있지 않은 문자열이 아니다")
    warmup_days = sample.get("guardrail_warmup_days")
    if not (_is_int(warmup_days) and warmup_days >= 0):
        problems.append(f"기준 파일 {path}: sample.guardrail_warmup_days 가 0 이상의 정수가 아니다")
    full_evaluation = sample.get("guardrail_full_evaluation")
    if not isinstance(full_evaluation, bool):
        problems.append(f"기준 파일 {path}: sample.guardrail_full_evaluation 이 true · false 가 아니다")

    required: list[RequiredCheck] = []
    checks = (verdict.get("required") or {}).get("checks") if isinstance(verdict.get("required"), dict) else None
    if not isinstance(checks, list) or not checks:
        problems.append(f"기준 파일 {path}: verdict.required.checks 가 비어 있다")
        checks = []
    for item in checks:
        name = item.get("name") if isinstance(item, dict) else None
        if not isinstance(name, str):
            problems.append(f"기준 파일 {path}: 이름 없는 필수 검사 {item!r}")
            continue
        band_from, abs_max = item.get("band_from"), item.get("abs_max_bp")
        # 크기 띠와 일관성 한계 중 정확히 하나만 있어야 어느 규칙으로 판정할지 정해진다.
        if (band_from is None) == (abs_max is None):
            problems.append(f"기준 파일 {path}: 필수 검사 {name} 에 band_from · abs_max_bp 중 정확히 하나가 있어야 한다")
            continue
        if band_from is not None and not isinstance(band_from, str):
            problems.append(f"기준 파일 {path}: 필수 검사 {name} 의 band_from 이 문자열이 아니다")
            continue
        if abs_max is not None and not (_is_finite_number(abs_max) and abs_max >= 0):
            problems.append(f"기준 파일 {path}: 필수 검사 {name} 의 abs_max_bp 가 0 이상의 수가 아니다")
            continue
        population, expected = item.get("population"), judged_population(name)
        if population != expected:
            # 리드가 모집단을 바꾸면 조용히 옛 모집단 값으로 판정하지 않는다 — 전환 지원은 리드 결정 뒤 별도 작업.
            problems.append(
                f"기준 파일 {path}: 필수 검사 {name} 의 population {population!r} 는 이 스크립트가 판정할 수 없다 "
                f"— 가드레일 리포트의 role {JUDGED_ROLE} 값은 {expected} 모집단이다(DR-194)"
            )
            continue
        required.append(RequiredCheck(name, str(item.get("fact", "")), population, band_from, abs_max))
    if len({c.name for c in required}) != len(required):
        problems.append(f"기준 파일 {path}: 필수 검사 이름이 중복된다")

    recorded = (verdict.get("recorded") or {}).get("facts") if isinstance(verdict.get("recorded"), dict) else None
    if not (isinstance(recorded, list) and all(isinstance(f, str) for f in recorded)):
        problems.append(f"기준 파일 {path}: verdict.recorded.facts 가 문자열 목록이 아니다")
        recorded = []

    if problems:
        raise InputError(problems)
    return Criteria(
        path=str(path), version=raw.get("version"), pending=raw.get("pending"),
        seeds=tuple(seeds), customers=customers, guardrail_profile=profile, guardrail_warmup_days=warmup_days,
        guardrail_full_evaluation=full_evaluation, required=tuple(required), recorded=tuple(recorded),
    )


def load_bands(criteria: Criteria, config_path: Path) -> dict[str, tuple[float, float]]:
    """필수 크기 띠 검사마다 simulator_config 의 띠(`band_from` 경로)를 읽는다."""
    config = _load_yaml(config_path, "시뮬레이터 config")
    problems: list[str] = []
    bands: dict[str, tuple[float, float]] = {}
    for check in criteria.required:
        if check.band_from is None:
            continue
        node: Any = config
        for part in check.band_from.split("."):
            node = node.get(part) if isinstance(node, dict) else None
        if not (isinstance(node, list) and len(node) == 2 and all(_is_number(x) for x in node) and node[0] <= node[1]):
            problems.append(f"시뮬레이터 config {config_path}: {check.band_from} 가 [lo, hi] 띠가 아니다 ({check.name})")
            continue
        bands[check.name] = (node[0], node[1])
    if problems:
        raise InputError(problems)
    return bands


# ── 입력 JSON ────────────────────────────────────────────────────────────────

def _load_yaml(path: Path, label: str) -> Any:
    # 모듈 최상위에서 import 하면 PyYAML 이 없을 때 ModuleNotFoundError 가 main 밖에서 나 종료 1(필수 실패와
    # 같은 값)이 된다. 여기서 import 해 main 의 내부 오류(3) 경로로 보낸다.
    try:
        import yaml
    except ImportError as exc:
        raise MissingDependencyError(
            "PyYAML 미설치 — `pip install -r requirements.txt` 뒤 다시 실행한다"
        ) from exc
    try:
        return yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        raise InputError([f"{label} {path} 를 읽지 못했다: {type(exc).__name__}: {exc}"]) from exc


def collect_files(paths: list[str], pattern: str, label: str, problems: list[str]) -> list[Path]:
    """파일은 그대로, 디렉터리는 `pattern` 에 맞는 파일(하위 디렉터리 제외)로 펼친다."""
    found: list[Path] = []
    for raw in paths:
        path = Path(raw)
        if path.is_dir():
            matched = sorted(p for p in path.glob(pattern) if p.is_file())
            if not matched:
                problems.append(f"{label} 디렉터리 {path} 에 {pattern} 파일이 없다")
            found.extend(matched)
        elif path.is_file():
            found.append(path)
        else:
            problems.append(f"{label} 입력 {path} 가 없다")
    return found


def _reject_nonfinite(text: str) -> float:
    """`json.loads` 의 수 훅. NaN · Infinity 와 1e999 처럼 inf 로 넘치는 수를 거부한다.

    두 생성기(가드레일 · realism_check)는 그런 값을 내지 않으므로(realism 의 `_r` 는 None 으로 바꾼다) 나왔다면
    입력이 손상된 것이다. 받아들이면 inf 가 띠 밖 값으로 판정돼 필수 실패(1)와 섞인다.
    """
    value = float(text)
    if not math.isfinite(value):
        raise ValueError(f"유한한 수가 아니다: {text}")
    return value


def _read_json(path: Path, label: str, problems: list[str]) -> dict[str, Any] | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"), parse_float=_reject_nonfinite,
                          parse_constant=_reject_nonfinite)
    except (OSError, ValueError) as exc:
        problems.append(f"{label} {path} 를 JSON 으로 읽지 못했다: {type(exc).__name__}: {exc}")
        return None
    if not isinstance(data, dict):
        problems.append(f"{label} {path} 의 최상위가 객체가 아니다")
        return None
    return data


def guardrail_seed(report: dict[str, Any]) -> int | None:
    """가드레일 리포트의 seed — CLI 가 최상위 `seed` 에 정수로 싣는다."""
    seed = report.get("seed")
    return seed if isinstance(seed, int) and not isinstance(seed, bool) else None


def realism_seed(report: dict[str, Any]) -> int | None:
    """realism JSON 의 seed — `source.random_seed`. realism_check 는 이벤트의 seed 가 하나면 문자열 하나,
    여러 개면 목록으로 싣는다. 목록(세계가 섞인 입력)은 짝지을 수 없으므로 None 이다."""
    source = report.get("source")
    seed = source.get("random_seed") if isinstance(source, dict) else None
    if isinstance(seed, int) and not isinstance(seed, bool):
        return seed
    if isinstance(seed, str):
        text = seed.strip()
        if text.lstrip("-").isdigit():
            return int(text)
    return None


def pair_by_seed(
    paths: list[Path], label: str, seed_of, expected: tuple[int, ...], problems: list[str]
) -> dict[int, tuple[Path, dict[str, Any]]]:
    """seed → (경로, 리포트). 기준 seed 집합과 정확히 같아야 한다 — 누락 · 초과 · 중복은 입력 오류다."""
    by_seed: dict[int, tuple[Path, dict[str, Any]]] = {}
    for path in paths:
        report = _read_json(path, label, problems)
        if report is None:
            continue
        seed = seed_of(report)
        if seed is None:
            problems.append(f"{label} {path} 에서 seed 를 읽지 못했다")
            continue
        if seed in by_seed:
            problems.append(f"{label} seed {seed} 가 중복된다: {by_seed[seed][0]} · {path}")
            continue
        by_seed[seed] = (path, report)
    missing = sorted(set(expected) - set(by_seed))
    extra = sorted(set(by_seed) - set(expected))
    if missing:
        problems.append(f"{label} 에 기준 seed {missing} 가 없다")
    if extra:
        problems.append(f"{label} 에 기준에 없는 seed {extra} 가 있다")
    return by_seed


def _single_value(reports: dict[int, tuple[Path, dict[str, Any]]], label: str, read, field: str,
                  problems: list[str]) -> Any:
    """모든 seed 가 같은 값을 갖는지 본다(봉인할 커밋 하나에서 잰다 — DR-208)."""
    values = {repr(read(report)) for _, report in reports.values()}
    if len(values) > 1:
        problems.append(f"{label} 의 {field} 가 seed 마다 다르다: {sorted(values)}")
        return None
    return read(next(iter(reports.values()))[1]) if reports else None


def check_run_conditions(
    criteria: Criteria, guardrails: dict[int, tuple[Path, dict[str, Any]]], problems: list[str]
) -> None:
    """가드레일 리포트가 기준의 실측 조건으로 잰 것인지 대조한다 — 어긋나거나 키가 없으면 입력 오류.

    고객 수 · profile · warmup_days 는 CLI 가 리포트 최상위에 싣는 값이다(`src/simulator/__main__.py`).
    전수 평가(`--sample` 없음)는 모집단 블록의 `evaluated_customers` 가 모집단 크기와 같은지로 본다 —
    표본 평가 리포트는 같은 seed 라도 다른 값이 나온다.
    """
    expected = {"customers": criteria.customers, "profile": criteria.guardrail_profile,
                "warmup_days": criteria.guardrail_warmup_days}
    for _, (path, report) in sorted(guardrails.items()):
        for key, want in expected.items():
            got = report.get(key)
            # bool 은 int 의 하위형이라 True == 1 을 막으려고 타입도 본다.
            if got != want or type(got) is not type(want):
                problems.append(f"가드레일 {path}: {key} {got!r} ≠ 기준 {want!r}")
        if not criteria.guardrail_full_evaluation:
            continue
        for block, size_key in POPULATION_SIZE_KEYS.items():
            node = report.get(block)
            evaluated = node.get("evaluated_customers") if isinstance(node, dict) else None
            size = report.get(size_key)
            if not (_is_int(evaluated) and _is_int(size) and evaluated == size):
                problems.append(
                    f"가드레일 {path}: {block}.evaluated_customers {evaluated!r} ≠ {size_key} {size!r} "
                    "— 기준은 전수 평가(guardrail_full_evaluation)다"
                )


def required_checks_by_seed(
    criteria: Criteria, bands: dict[str, tuple[float, float]],
    guardrails: dict[int, tuple[Path, dict[str, Any]]], problems: list[str],
) -> dict[str, dict[int, dict[str, Any]]]:
    """필수 검사 이름 → seed → 가드레일 `checks[]` 항목(`role: 판정`). 이름 누락 · 중복 · 띠 불일치는 입력 오류."""
    found: dict[str, dict[int, dict[str, Any]]] = {c.name: {} for c in criteria.required}
    for seed, (path, report) in sorted(guardrails.items()):
        checks = report.get("checks")
        if not isinstance(checks, list):
            problems.append(f"가드레일 {path}: checks 목록이 없다")
            continue
        for rule in criteria.required:
            hits = [c for c in checks if isinstance(c, dict) and c.get("name") == rule.name and c.get("role") == JUDGED_ROLE]
            if len(hits) != 1:
                problems.append(
                    f"가드레일 {path} (seed {seed}): role {JUDGED_ROLE} 검사 {rule.name} 가 "
                    f"{'없다' if not hits else f'{len(hits)}개다'}"
                )
                continue
            check = hits[0]
            value = check.get("value_bp")
            if value is not None and not _is_finite_number(value):
                problems.append(f"가드레일 {path} (seed {seed}): {rule.name} 의 value_bp 가 유한한 수가 아니다 ({value!r})")
                continue
            if rule.band_from is not None:
                range_bp = check.get("range_bp")
                expected = list(bands[rule.name])
                if not (isinstance(range_bp, list) and range_bp == expected):
                    problems.append(
                        f"가드레일 {path} (seed {seed}): {rule.name} 의 range_bp {range_bp!r} 가 "
                        f"simulator_config {rule.band_from} {expected} 와 다르다"
                    )
                    continue
            found[rule.name][seed] = check
    return found


def recorded_metrics_by_seed(
    criteria: Criteria, realism: dict[int, tuple[Path, dict[str, Any]]], problems: list[str]
) -> dict[str, dict[int, dict[str, Any]]]:
    """F id → seed → realism `metrics[]` 항목. 기록 항목이 없거나 seed 마다 띠가 다르면 입력 오류."""
    by_fact: dict[str, dict[int, dict[str, Any]]] = {}
    for seed, (path, report) in sorted(realism.items()):
        metrics = report.get("metrics")
        if not isinstance(metrics, list):
            problems.append(f"realism {path}: metrics 목록이 없다")
            continue
        by_id: dict[str, dict[str, Any]] = {}
        for metric in metrics:
            if isinstance(metric, dict) and isinstance(metric.get("id"), str):
                if metric["id"] in by_id:
                    problems.append(f"realism {path}: {metric['id']} 가 중복된다")
                by_id[metric["id"]] = metric
        for fact, metric in by_id.items():
            by_fact.setdefault(fact, {})[seed] = metric
        for fact in criteria.recorded:
            metric = by_id.get(fact)
            if metric is None:
                problems.append(f"realism {path} (seed {seed}): 기록 검사 {fact} 가 없다")
            elif not (isinstance(metric.get("reference"), dict) and "band" in metric["reference"]):
                problems.append(f"realism {path} (seed {seed}): {fact} 에 reference.band 가 없다")
    for fact in criteria.recorded:
        bands = {json.dumps(m.get("reference", {}).get("band"), sort_keys=True)
                 for m in by_fact.get(fact, {}).values() if isinstance(m.get("reference"), dict)}
        if len(bands) > 1:
            problems.append(f"realism {fact} 의 reference.band 가 seed 마다 다르다: {sorted(bands)}")
    return by_fact


# ── 판정 ─────────────────────────────────────────────────────────────────────

def _mean_fraction(values: list[float]) -> Fraction:
    # 반올림 없이 비교하려고 분수로 평균한다 — 600.2bp 가 600 으로 보이지 않게(DR-208).
    return sum((Fraction(v) for v in values), Fraction(0)) / len(values)


def judge_band_check(rule: RequiredCheck, band: tuple[float, float], checks: dict[int, dict[str, Any]]) -> dict[str, Any]:
    """크기 띠 필수 검사 — seed 평균이 띠 안(경계 포함) ∧ 각 seed 가 pass · borderline."""
    lo, hi = band
    values = {seed: check.get("value_bp") for seed, check in checks.items()}
    seed_verdicts = {
        seed: "no_data" if checks[seed].get("status") == "not_run" or value is None else judge(value, lo, hi)
        for seed, value in values.items()
    }
    reasons: list[str] = []
    if any(v == "no_data" for v in seed_verdicts.values()):
        mean, mean_verdict = None, "no_data"
        reasons.append("값 없는 seed(not_run · None)가 있다 — 실패로 본다")
    else:
        mean = _mean_fraction([float(v) for v in values.values()])
        mean_verdict = "pass" if lo <= mean <= hi else "fail"
        if mean_verdict == "fail":
            reasons.append(f"5 seed 평균 {_fmt_number(mean)}bp 가 띠 [{lo}, {hi}] 밖이다")
    outside = sorted(s for s, v in seed_verdicts.items() if v == "fail")
    if outside:
        reasons.append(f"seed {outside} 가 경계(±20%) 밖이다")
    passed = mean_verdict == "pass" and all(v in PASSING_SEED_VERDICTS for v in seed_verdicts.values())
    return {
        "name": rule.name, "fact": rule.fact, "population": rule.population, "kind": "band",
        "band_bp": [lo, hi], "band_from": rule.band_from,
        "values_bp": values, "seed_verdicts": seed_verdicts,
        "mean_bp": None if mean is None else float(mean), "mean_verdict": mean_verdict,
        "verdict": "pass" if passed else "fail", "reasons": reasons,
    }


def judge_consistency_check(rule: RequiredCheck, checks: dict[int, dict[str, Any]]) -> dict[str, Any]:
    """4분면 일관성 필수 검사 — 각 seed |gap| ≤ abs_max_bp. 부호 있는 평균은 +60 · −60 을 상쇄하므로 쓰지 않는다."""
    limit = rule.abs_max_bp
    values = {seed: check.get("value_bp") for seed, check in checks.items()}
    seed_verdicts = {
        seed: "no_data" if checks[seed].get("status") == "not_run" or value is None
        else ("pass" if abs(value) <= limit else "fail")
        for seed, value in values.items()
    }
    reasons: list[str] = []
    bad = sorted(s for s, v in seed_verdicts.items() if v != "pass")
    if bad:
        reasons.append(f"seed {bad} 의 |값| 이 {limit}bp 를 넘거나 값이 없다")
    present = [abs(v) for v in values.values() if v is not None]
    return {
        "name": rule.name, "fact": rule.fact, "population": rule.population, "kind": "consistency",
        "abs_max_bp": limit,
        "values_bp": values, "seed_verdicts": seed_verdicts,
        "max_abs_bp": max(present) if present else None,
        "verdict": "pass" if not bad else "fail", "reasons": reasons,
    }


def judge_recorded(fact: str, metrics: dict[int, dict[str, Any]]) -> dict[str, Any]:
    """기록 검사 한 항목 — band 키마다 synthetic 값을 seed 평균해 realism_check 규칙으로 판정한다."""
    band = next(iter(metrics.values()))["reference"]["band"]
    mapping = SYNTHETIC_KEYS.get(fact, {})
    keys: list[str | None] = list(band) if isinstance(band, dict) else [None]
    parts: list[dict[str, Any]] = []
    for key in keys:
        limits = band[key] if key is not None else band
        synthetic_key = mapping.get(key)
        part: dict[str, Any] = {"key": key, "synthetic_key": synthetic_key, "band": limits,
                                "values": {}, "mean": None, "verdict": "no_data", "note": None}
        parts.append(part)
        if synthetic_key is None:
            part["note"] = f"band 키 {key!r} 를 synthetic 키로 매핑하지 못했다(SYNTHETIC_KEYS)"
            continue
        if not (isinstance(limits, list) and len(limits) == 2 and all(x is None or _is_number(x) for x in limits)):
            part["note"] = f"띠 형식을 알 수 없다 {limits!r}"
            continue
        values = {}
        for seed, metric in sorted(metrics.items()):
            synthetic = metric.get("synthetic")
            values[seed] = synthetic.get(synthetic_key) if isinstance(synthetic, dict) else None
        part["values"] = values
        missing = sorted(s for s, v in values.items() if not _is_finite_number(v))
        if missing:
            # 값이 없어도 realism_check 가 그 seed 를 fail 로 판정했으면 fail 이다. F5 과소분산이 그렇다 — r = inf 를
            # nbd_shape=None 으로 싣고 verdict fail 을 낸다. no_data 로 적으면 판정된 실패를 감춘다.
            failed = [s for s in missing if metrics[s].get("verdict") == "fail"]
            if failed:
                part["verdict"] = "fail"
                part["note"] = (f"seed {failed} 의 {synthetic_key} 값이 없고 realism 판정이 fail 이다 — fail 로 본다"
                                f" (realism note: {metrics[failed[0]].get('note')})")
            else:
                part["note"] = f"seed {missing} 의 {synthetic_key} 값이 없다"
            continue
        mean = math.fsum(values.values()) / len(values)
        lo, hi = limits
        part["mean"] = mean
        part["verdict"] = judge_open_lower(mean, lo) if hi is None and lo is not None else judge(mean, lo, hi)
    return {
        "fact": fact, "band": band, "parts": parts, "verdict": worst([p["verdict"] for p in parts]),
        "seed_verdicts_reported": {seed: m.get("verdict") for seed, m in sorted(metrics.items())},
    }


def _reference_rows(
    required_names: set[str], guardrails: dict[int, tuple[Path, dict[str, Any]]],
    metrics: dict[str, dict[int, dict[str, Any]]], seeds: tuple[int, ...],
) -> dict[str, list[dict[str, Any]]]:
    """판정하지 않는 값 — 가드레일의 필수 외 검사와 realism F12 · F14 · F15 · F16 의 seed 평균."""
    names: list[str] = []
    for _, report in (guardrails[s] for s in sorted(guardrails)):
        for check in report.get("checks", []):
            if isinstance(check, dict) and check.get("name") not in required_names and check.get("name") not in names:
                names.append(check["name"])
    guardrail_rows = []
    for name in names:
        values: dict[int, Any] = {}
        role = None
        for seed, (_, report) in sorted(guardrails.items()):
            hit = next((c for c in report.get("checks", []) if isinstance(c, dict) and c.get("name") == name), None)
            values[seed] = hit.get("value_bp") if hit else None
            role = role or (hit.get("role") if hit else None)
        nums = [v for v in values.values() if _is_finite_number(v)]
        guardrail_rows.append({
            "name": name, "role": role, "values_bp": values,
            "mean_bp": float(_mean_fraction(nums)) if len(nums) == len(seeds) else None,
        })
    realism_rows = []
    for fact, keys in REFERENCE_REALISM_KEYS.items():
        by_seed = metrics.get(fact, {})
        for key in keys:
            values = {}
            for seed in seeds:
                synthetic = by_seed.get(seed, {}).get("synthetic")
                values[seed] = synthetic.get(key) if isinstance(synthetic, dict) else None
            nums = [v for v in values.values() if _is_finite_number(v)]
            realism_rows.append({
                "fact": fact, "key": key, "values": values,
                "mean": math.fsum(nums) / len(nums) if len(nums) == len(seeds) else None,
            })
    return {"guardrail": guardrail_rows, "realism": realism_rows}


def check_versions(guardrail_version: Any, realism_version: Any, problems: list[str]) -> None:
    """두 출처가 같은 시뮬레이터 버전에서 쟀는지 본다. 버전을 모르면 같다고 가정하지 않는다.

    realism_check 는 이벤트에 버전이 여럿이면 목록으로 싣는다 — 문자열 하나가 아니면 확인할 수 없는 것으로 본다.
    """
    if not (isinstance(guardrail_version, str) and guardrail_version
            and isinstance(realism_version, str) and realism_version):
        problems.append(
            f"simulator_version 을 확인할 수 없다 (가드레일 {guardrail_version!r} · realism {realism_version!r})"
            " — 판정하지 않는다"
        )
    elif guardrail_version != realism_version:
        problems.append(
            f"simulator_version 이 출처마다 다르다: 가드레일 {guardrail_version!r} · realism {realism_version!r}"
        )


def evaluate(
    criteria: Criteria, bands: dict[str, tuple[float, float]], guardrail_paths: list[str], realism_paths: list[str]
) -> dict[str, Any]:
    """입력을 기준과 대조하고 판정 리포트를 만든다. 입력이 기준과 맞지 않으면 `InputError`."""
    problems: list[str] = []
    guardrail_files = collect_files(guardrail_paths, GUARDRAIL_GLOB, "가드레일", problems)
    realism_files = collect_files(realism_paths, REALISM_GLOB, "realism", problems)
    guardrails = pair_by_seed(guardrail_files, "가드레일", guardrail_seed, criteria.seeds, problems)
    realism = pair_by_seed(realism_files, "realism", realism_seed, criteria.seeds, problems)
    if problems:
        raise InputError(problems)

    guardrail_version = _single_value(guardrails, "가드레일", lambda r: r.get("simulator_version"),
                                      "simulator_version", problems)
    realism_version = _single_value(realism, "realism", lambda r: (r.get("source") or {}).get("simulator_version"),
                                    "source.simulator_version", problems)
    if not problems:
        check_versions(guardrail_version, realism_version, problems)
    check_run_conditions(criteria, guardrails, problems)
    checks = required_checks_by_seed(criteria, bands, guardrails, problems)
    metrics = recorded_metrics_by_seed(criteria, realism, problems)
    if problems:
        raise InputError(problems)

    required = [
        judge_band_check(rule, bands[rule.name], checks[rule.name]) if rule.band_from is not None
        else judge_consistency_check(rule, checks[rule.name])
        for rule in criteria.required
    ]
    recorded = [judge_recorded(fact, metrics[fact]) for fact in criteria.recorded]
    failed = [r["name"] for r in required if r["verdict"] != "pass"]
    return {
        "criteria": {"path": criteria.path, "version": criteria.version, "pending": criteria.pending},
        "seeds": list(criteria.seeds),
        "customers": criteria.customers,
        "guardrail_conditions": {"profile": criteria.guardrail_profile,
                                 "warmup_days": criteria.guardrail_warmup_days,
                                 "full_evaluation": criteria.guardrail_full_evaluation},
        "inputs": {
            "guardrail": {seed: str(path) for seed, (path, _) in sorted(guardrails.items())},
            "realism": {seed: str(path) for seed, (path, _) in sorted(realism.items())},
        },
        "simulator_version": {"guardrail": guardrail_version, "realism": realism_version},
        "required": required,
        "recorded": recorded,
        "reference": _reference_rows({r.name for r in criteria.required}, guardrails, metrics, criteria.seeds),
        "verdict": {
            "required_pass": not failed, "failed": failed,
            "exit_code": EXIT_PASS if not failed else EXIT_FAIL,
        },
    }


# ── 출력 ─────────────────────────────────────────────────────────────────────

def _fmt_number(value: Any) -> str:
    if value is None:
        return "—"
    if isinstance(value, (Fraction, float)):
        return f"{float(value):.6g}"
    return str(value)


def _fmt_band(band: Any) -> str:
    if isinstance(band, list) and len(band) == 2:
        lo, hi = band
        if hi is None:
            return f"> {_fmt_number(lo)}"
        return f"[{_fmt_number(lo)}, {_fmt_number(hi)}]"
    return json.dumps(band, ensure_ascii=False)


def render_md(report: dict[str, Any]) -> str:
    """판정표(Markdown). stdout 과 `--out-md` 가 같은 내용이다."""
    seeds = report["seeds"]
    verdict = report["verdict"]
    head = "통과" if verdict["required_pass"] else f"불통과 — 실패 {', '.join(verdict['failed'])}"
    lines = [
        f"# GATE 1 판정 — 필수 검사 {head}",
        "",
        f"- 기준: `{report['criteria']['path']}` ({report['criteria']['version']})",
        f"- seed {seeds} × {report['customers']}명 · simulator_version 가드레일 "
        f"{report['simulator_version']['guardrail']} · realism {report['simulator_version']['realism']}",
        f"- 가드레일 실측 조건: profile {report['guardrail_conditions']['profile']} · warmup "
        f"{report['guardrail_conditions']['warmup_days']}일 · 전수 평가 {report['guardrail_conditions']['full_evaluation']}",
    ]
    if report["criteria"]["pending"]:
        lines.append(f"- ★ 기준 파일 pending: `{report['criteria']['pending']}` — 확정 전 기준이다")
    lines += ["", "## 필수 검사 (가드레일 리포트 · 종료 코드에 반영)", "",
              "| 검사 | F | 모집단 | 기준 | " + " | ".join(f"seed {s}" for s in seeds) + " | 평균 · 최대 | 판정 |",
              "|---|---|---|---|" + "---|" * len(seeds) + "---|---|"]
    for row in report["required"]:
        cells = [f"{_fmt_number(row['values_bp'][s])} ({row['seed_verdicts'][s]})" for s in seeds]
        if row["kind"] == "band":
            rule = f"평균 {_fmt_band(row['band_bp'])}bp · 각 seed ±20%"
            summary = f"평균 {_fmt_number(row['mean_bp'])}"
        else:
            rule = f"각 seed \\|값\\| ≤ {row['abs_max_bp']}bp"
            summary = f"최대 \\|값\\| {_fmt_number(row['max_abs_bp'])}"
        lines.append(f"| {row['name']} | {row['fact']} | {row['population']} | {rule} | " + " | ".join(cells)
                     + f" | {summary} | **{row['verdict']}** |")
    reasons = [f"- {row['name']}: {'; '.join(row['reasons'])}" for row in report["required"] if row["reasons"]]
    if reasons:
        lines += [""] + reasons

    lines += ["", "## 기록 검사 (realism · 종료 코드와 무관)", "",
              "| F | 값 | 띠 | 5 seed 평균 | 판정 | 항목 종합 | seed별 realism 판정 |", "|---|---|---|---|---|---|---|"]
    for item in report["recorded"]:
        reported = ", ".join(f"{s}:{v}" for s, v in item["seed_verdicts_reported"].items())
        for part in item["parts"]:
            label = part["synthetic_key"] or (part["key"] if part["key"] is not None else "—")
            note = f" ({part['note']})" if part["note"] else ""
            lines.append(f"| {item['fact']} | {label} | {_fmt_band(part['band'])} | {_fmt_number(part['mean'])} | "
                         f"{part['verdict']}{note} | {item['verdict']} | {reported} |")

    lines += ["", "## 참고 (판정하지 않음)", "", "| 출처 | 항목 | 구분 | 5 seed 평균 |", "|---|---|---|---|"]
    for row in report["reference"]["guardrail"]:
        lines.append(f"| 가드레일 | {row['name']} | {row['role']} | {_fmt_number(row['mean_bp'])}bp |")
    for row in report["reference"]["realism"]:
        lines.append(f"| realism | {row['fact']} {row['key']} | — | {_fmt_number(row['mean'])} |")
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="GATE 1 판정 — 종료 코드 0 필수 통과 · 1 필수 실패 · 2 입력 오류(판정 안 함) · "
                    "3 내부 오류(출력 쓰기 실패 등, 판정 안 함 또는 남기지 못함)")
    parser.add_argument("--criteria", default=str(DEFAULT_CRITERIA), help="기준 yaml (기본 config/simulator_gate1_acceptance.yaml)")
    parser.add_argument("--simulator-config", default=str(DEFAULT_SIMULATOR_CONFIG),
                        help="가드레일 띠 정본 (기본 config/simulator_config.yaml)")
    parser.add_argument("--guardrail", nargs="+", required=True,
                        help=f"가드레일 리포트 JSON 또는 그것이 든 디렉터리({GUARDRAIL_GLOB}) — seed 마다 하나")
    parser.add_argument("--realism", nargs="+", required=True,
                        help=f"realism_check --out-json 결과 또는 그것이 든 디렉터리({REALISM_GLOB}) — seed 마다 하나")
    parser.add_argument("--out-json")
    parser.add_argument("--out-md")
    args = parser.parse_args(argv)

    try:
        return _run(args)
    except InputError as exc:
        print("입력 오류 — 판정하지 않았다(통과가 아니다):", file=sys.stderr)
        for problem in exc.problems:
            print(f"  - {problem}", file=sys.stderr)
        return EXIT_INPUT_ERROR
    except Exception as exc:  # noqa: BLE001 — 필수 실패(1)와 섞이지 않게 모든 예상 밖 예외를 3 으로 모은다
        print(f"내부 오류 — 판정하지 않았거나 판정을 남기지 못했다(통과가 아니다): {type(exc).__name__}: {exc}",
              file=sys.stderr)
        return EXIT_INTERNAL_ERROR


def _run(args: argparse.Namespace) -> int:
    """판정하고 출력한다. 출력 파일을 모두 쓴 뒤에만 stdout 에 판정표를 내고 판정 종료 코드(0 · 1)를 돌려준다."""
    outputs = [(Path(path), kind) for path, kind in ((args.out_md, "md"), (args.out_json, "json")) if path]
    if len(outputs) == 2 and outputs[0][0].resolve() == outputs[1][0].resolve():
        raise InputError([f"--out-md 와 --out-json 이 같은 경로다: {args.out_md}"])
    criteria = load_criteria(Path(args.criteria))
    bands = load_bands(criteria, Path(args.simulator_config))
    report = evaluate(criteria, bands, args.guardrail, args.realism)
    text = render_md(report)
    # allow_nan=False — 비표준 JSON 이 새면 아무것도 쓰기 전에 3 으로 끝난다.
    payload = json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False) + "\n"
    write_outputs([(path, text if kind == "md" else payload) for path, kind in outputs])
    # 파일을 다 남긴 뒤에 출력한다 — 쓰기에 실패했는데 stdout 에 "필수 검사 통과" 판정표가 남지 않게.
    print(text, end="")
    return report["verdict"]["exit_code"]


def write_outputs(outputs: list[tuple[Path, str]]) -> None:
    """출력 파일을 전부 쓰거나 하나도 바꾸지 않는다.

    1) 각 파일을 대상과 같은 디렉터리의 임시 파일에 쓴다(같은 파일 시스템이라 `os.replace` 가 원자적이다).
    2) 대상마다 기존 파일을 백업 이름으로 옮기고 임시 파일을 대상 이름으로 바꾼다.
    중간에 실패하면 이번 실행이 쓴 임시 · 대상 파일을 지우고 백업을 원래 이름으로 되돌린 뒤 예외를 다시 던진다.

    원래 경로에 있던 이전 파일은 실패 시 그대로 둔다(삭제하지 않는다). 이전 실행의 판정 기록일 수 있고, 그것을
    지울지는 이 실행이 정할 일이 아니다 — 이번 실행이 남기지 못했다는 사실은 종료 코드 3 과 stderr 가 알린다.
    `mkdir` 로 새로 만든 상위 디렉터리는 실패해도 남는다(빈 디렉터리).
    """
    staged: list[tuple[Path, Path]] = []          # (임시 파일, 대상)
    committed: list[tuple[Path, Path | None]] = []  # (대상, 백업 — 기존 파일이 없었으면 None)
    try:
        for target, content in outputs:
            target.parent.mkdir(parents=True, exist_ok=True)
            if target.is_dir():
                # 디렉터리에 os.replace 하면 플랫폼마다 다르게 실패한다 — 바꾸기 전에 막는다.
                raise IsADirectoryError(f"출력 경로가 디렉터리다: {target}")
            fd, tmp = tempfile.mkstemp(dir=target.parent, prefix=f".{target.name}.", suffix=".tmp")
            staged.append((Path(tmp), target))
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                handle.write(content)
        for tmp, target in staged:
            backup = None
            if target.exists():
                fd, name = tempfile.mkstemp(dir=target.parent, prefix=f".{target.name}.", suffix=".bak")
                os.close(fd)
                backup = Path(name)
                try:
                    os.replace(target, backup)
                except BaseException:
                    # 아직 committed 에 넣기 전이다 — 빈 자리표시 파일로 원본을 덮어 되돌리지 않게 여기서 지운다.
                    backup.unlink(missing_ok=True)
                    raise
            committed.append((target, backup))
            os.replace(tmp, target)
    except BaseException:
        for target, backup in reversed(committed):
            if backup is not None:
                os.replace(backup, target)
            else:
                target.unlink(missing_ok=True)
        for tmp, _ in staged:
            tmp.unlink(missing_ok=True)
        raise
    for _, backup in committed:
        if backup is not None:
            backup.unlink(missing_ok=True)


if __name__ == "__main__":
    sys.exit(main())
