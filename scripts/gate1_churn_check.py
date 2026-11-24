"""GATE 1 churn 임계값 근거 — data_spec §5.1 ①~③ (구매 간격 분위수가 churn 임계값 근처인가).

기준은 `config/simulator_gate1_acceptance.yaml` 의 `churn_threshold` 블록이다. 임계값은 여기에 적지 않는다 —
정본은 `config/simulator_config.yaml` `churn`(블록의 `thresholds_from`)이고, 이 스크립트는 그 값을 읽어 쓴다.
결과의 `met` · `evidence` 는 `src/measurement/freeze.py` `ChurnThresholdEvidence(met=…, evidence=…)` 에 그대로 넣는다.

두 하위 명령이 있다.

measure — 처치 없는 세계 하나를 공개 API(`src.simulator.api`)로 만들어 구매 간격 분위수를 잰다.
    `scripts/research/run_world.py` 와 같은 방식으로 init → advance(--days) 하고 `apply_treatment` 는 부르지 않는다.
    간격 정의(사전 등록 — 바꾸면 기준과 어긋난다):
      - 고객별 purchase 이벤트의 KST 달력 날짜를 오름차순 정렬한다. 날짜를 중복 제거하지 않는다 — 같은 날
        재구매는 간격 0 이다(`src/measurement/kpi.py` `_purchases_by_customer` · `_event_date` 와 같은 규칙).
      - 연속한 두 날짜의 차이 (b − a).days 가 간격이다. 구매 2건 미만 고객은 간격이 없다.
      - 모든 고객의 간격을 한데 모아 `statistics.quantiles(gaps, n=100, method='inclusive')` 로 P75 · P90 을 구한다
        (= numpy.percentile 기본값, inclusive 선형 보간).
    kpi 는 해석할 수 없는 timestamp · 문자열이 아닌 customer_id 를 조용히 뺀다. 여기서는 빼지 않고 실패한다 —
    Sink 를 거친 시뮬레이터 이벤트에는 그런 것이 없어야 하고, 있으면 간격 표본이 달라진 것이다.

judge — seed 마다 measure 가 낸 `churn_intervals.json` 을 기준과 대조해 판정한다.
    비교마다(`comparisons[]`: 임계값 이름 · 분위수) seed 별 Pq 와 5 seed 평균 Pq 가 모두
    |Pq − 임계값| ≤ tolerance_ratio × 임계값(경계 포함)이면 통과다. Pq 는 measure 가 분수로 남긴 `p{q}_exact` 를
    쓰고, seed 평균도 `Fraction` 으로 반올림 없이 비교한다. 모든 비교가 통과하면 met=true.

종료 코드
    measure: 0 측정 완료 · 2 입력 오류(출력 디렉터리가 이미 있음, 인자 오류, 간격이 2개 미만)
             · 3 내부 오류(시뮬레이터 오류, 이벤트 형식 이상, 쓰기 실패)
    judge:   0 met=true · 1 met=false(판정은 끝났다) · 2 입력 오류(판정하지 않았다: seed 누락 · 중복 · 초과,
             profile · customers · days 불일치, simulator_version · source_commit 이 seed 마다 다름, 기준 블록
             키 없음, 임계값 없음) · 3 내부 오류(PyYAML 미설치, 출력 쓰기 실패 등)
    판정하지 않은 것을 통과로 적지 않는다 — 2 · 3 은 어느 쪽도 met 이 아니다.

사용
    PYTHONPATH=. python scripts/gate1_churn_check.py measure --seed 47 --customers 13000 --out <새 디렉터리> \\
        [--profile reference] [--days 273]
    python scripts/gate1_churn_check.py judge --criteria config/simulator_gate1_acceptance.yaml \\
        --simulator-config config/simulator_config.yaml --intervals <F1> ... <F5> [--out-json J] [--out-md M]
"""

from __future__ import annotations

import argparse
import json
import re
import statistics
import subprocess
import sys
from dataclasses import dataclass
from datetime import date, timedelta
from fractions import Fraction
from pathlib import Path
from typing import Any, Iterable, Mapping

# 같은 디렉터리의 gate1_* 스크립트를 import 한다. sys.path[0] 에 기대지 않는다 — `python -P` · PYTHONSAFEPATH 나
# 다른 cwd 에서 불러도 찾도록 이 파일의 디렉터리를 직접 넣는다. PyYAML 은 gate1_judge 가 쓸 때만 import 한다.
_SCRIPTS_DIR = str(Path(__file__).resolve().parent)
if _SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, _SCRIPTS_DIR)

import gate1_judge as gj  # noqa: E402
from gate1_judge import EXIT_FAIL, EXIT_INPUT_ERROR, EXIT_INTERNAL_ERROR, EXIT_PASS, InputError  # noqa: E402

REPO = Path(__file__).resolve().parents[1]
DEFAULT_CRITERIA = REPO / "config" / "simulator_gate1_acceptance.yaml"
DEFAULT_SIMULATOR_CONFIG = REPO / "config" / "simulator_config.yaml"



INTERVALS_FILE = "churn_intervals.json"
SCHEMA = "gate1-churn-intervals/v1"
DEFAULT_PROFILE = "reference"
DEFAULT_DAYS = 273
QUANTILES = (75, 90)
KST_OFFSET = timedelta(hours=9)

INTERVAL_DEFINITION = (
    "같은 고객의 purchase 이벤트 KST 달력 날짜를 오름차순 정렬(중복 제거 없음 — 같은 날 재구매는 0 일)한 뒤 "
    "연속한 두 날짜의 차이 (b − a).days. 구매 2건 미만 고객은 간격이 없다. 모든 고객의 간격을 한데 모은다"
)
QUANTILE_DEFINITION = "statistics.quantiles(gaps, n=100, method='inclusive') (= numpy.percentile 기본값)"

CHURN_BLOCK = "churn_threshold"
CHURN_ROLE = "churn_evidence"
CHURN_TEXT_KEYS = ("interval", "quantile_method", "thresholds_from", "rule", "on_fail")
# customers 는 sample.customers 하나에서만 온다 — 다른 출처를 가리키면 이 스크립트는 읽을 수 없다.
CUSTOMERS_FROM = "sample.customers"


# ── measure ───────────────────────────────────────────────────────────────────

def _ensure_repo_on_path() -> None:
    # `python scripts/gate1_churn_check.py` 로 부르면 sys.path[0] 이 scripts/ 라 `src` 를 못 찾는다.
    if str(REPO) not in sys.path:
        sys.path.insert(0, str(REPO))


def purchase_dates_by_customer(events: Iterable[Mapping[str, Any]]) -> dict[str, list[date]]:
    """고객별 purchase KST 날짜(오름차순, 중복 유지). 해석할 수 없는 이벤트가 있으면 `ValueError`."""
    _ensure_repo_on_path()
    from src.measurement import timeparse

    by_customer: dict[str, list[date]] = {}
    for event in events:
        if event.get("event_type") != "purchase":
            continue
        customer, raw = event.get("customer_id"), event.get("timestamp")
        if not isinstance(customer, str) or not customer:
            raise ValueError(f"purchase 이벤트의 customer_id 가 문자열이 아니다: {event.get('event_id')!r}")
        try:
            moment = timeparse.parse_datetime(str(raw))
        except (TypeError, ValueError) as exc:
            raise ValueError(f"purchase 이벤트 timestamp 를 해석하지 못했다: {raw!r}") from exc
        # Sink 가 KST 로 정규화한다는 전제로 .date() 를 KST 날짜로 쓴다 — 전제가 깨졌으면 날짜가 하루 밀린다.
        if moment.utcoffset() != KST_OFFSET:
            raise ValueError(f"purchase 이벤트 timestamp 가 KST(+09:00)가 아니다: {raw!r}")
        by_customer.setdefault(customer, []).append(moment.date())
    for dates in by_customer.values():
        dates.sort()
    return by_customer


def pooled_gaps(dates_by_customer: Mapping[str, list[date]]) -> list[int]:
    """모든 고객의 연속 구매 간격(일)을 한데 모은다. 같은 날 재구매는 0 이다."""
    gaps: list[int] = []
    for dates in dates_by_customer.values():
        ordered = sorted(dates)
        gaps.extend((b - a).days for a, b in zip(ordered, ordered[1:]))
    return gaps


def percentiles(gaps: list[int], quantiles: Iterable[int] = QUANTILES) -> dict[int, Fraction]:
    """inclusive 선형 보간 분위수를 분수로 정확히 구한다. 간격이 2개 미만이면 `InputError`.

    `statistics.quantiles(n=100, method='inclusive')` 와 같은 식((a·(100−δ) + b·δ) / 100)을 정수로 계산한다.
    float 로 두면 22.4 가 22.399999… 가 되어 경계값(28 × 0.8 = 22.4)이 밖으로 판정된다 — 경계 포함 규칙이 깨진다.
    같은 값인지는 `measure` 가 statistics.quantiles 결과와 대조한다.
    """
    if len(gaps) < 2:
        raise InputError([f"구매 간격이 {len(gaps)}개다 — 분위수를 내려면 2개 이상이 필요하다(고객 수를 늘린다)"])
    data = sorted(gaps)
    m = len(data) - 1
    values: dict[int, Fraction] = {}
    for q in quantiles:
        j, delta = divmod(q * m, 100)
        values[q] = Fraction(data[j] * (100 - delta) + data[j + 1] * delta, 100)
    return values


def simulator_commit(repo: Path = REPO) -> str | None:
    """`src/simulator` 를 마지막으로 바꾼 커밋 — `src/simulator/api.py` `_source_commit` 과 같은 규칙. 모르면 None."""
    try:
        result = subprocess.run(["git", "log", "-1", "--format=%H", "--", "src/simulator"], cwd=repo,
                                capture_output=True, text=True, timeout=10, check=False)
    except (OSError, subprocess.SubprocessError):
        return None
    commit = result.stdout.strip()
    return commit if result.returncode == 0 and re.fullmatch(r"[0-9a-f]{40}", commit) else None


def measure(seed: int, customers: int, profile: str, days: int, out: Path) -> dict[str, Any]:
    """처치 없는 세계를 만들어 구매 간격 분위수를 재고 `out/churn_intervals.json` 을 쓴다."""
    if out.exists():
        raise InputError([f"출력 디렉터리 {out} 가 이미 있다 — 새 디렉터리를 준다(이전 측정을 덮지 않는다)"])
    if customers <= 0 or days <= 0:
        raise InputError([f"--customers {customers} · --days {days} 는 양의 정수여야 한다"])
    _ensure_repo_on_path()
    from src.simulator import api

    out.mkdir(parents=True, exist_ok=False)
    try:
        api.init(seed, customers, profile, str(out / "raw" / "main"), hidden_root=str(out / "hidden"))
    except (TypeError, ValueError) as exc:
        raise InputError([f"세계를 만들지 못했다(인자 오류): {exc}"]) from exc
    end = api.advance(days).end
    # 전 이벤트를 목록으로 들지 않는다 — 고객 40명 273일이 약 1.7만 건이라 13,000명이면 수백만 건이고 seed 5개가
    # 동시에 돈다. 한 번 훑으며 purchase 만 남긴다.
    # 반복 도중 예외가 나면 여기서 끝나 아무것도 쓰지 않는다(api.events — 전량을 받은 뒤에만 쓴다).
    versions: set[Any] = set()
    seeds: set[Any] = set()
    events: list[dict[str, Any]] = []
    for event in api.events(end):
        versions.add(event.get("simulator_version"))
        seeds.add(event.get("random_seed"))
        if event.get("event_type") == "purchase":
            events.append(event)
    if len(versions) != 1 or not isinstance(next(iter(versions)), str):
        raise RuntimeError(f"이벤트의 simulator_version 이 하나가 아니다: {sorted(map(repr, versions))}")
    if seeds != {seed}:
        raise RuntimeError(f"이벤트의 random_seed {sorted(map(repr, seeds))} 가 --seed {seed} 와 다르다")

    by_customer = purchase_dates_by_customer(events)
    gaps = pooled_gaps(by_customer)
    values = percentiles(gaps)
    cuts = statistics.quantiles(gaps, n=100, method="inclusive")
    if any(float(values[q]) != cuts[q - 1] for q in QUANTILES):
        raise RuntimeError(f"분위수 계산이 statistics.quantiles 와 다르다: {values} · {[cuts[q - 1] for q in QUANTILES]}")
    result = {
        "schema": SCHEMA,
        "seed": seed, "customers": customers, "profile": profile, "days": days,
        "events_until": end.isoformat(),
        "simulator_version": next(iter(versions)),
        "source_commit": simulator_commit(),
        "n_purchases": sum(len(d) for d in by_customer.values()),
        "n_customers_with_purchase": len(by_customer),
        "n_customers_with_gap": sum(1 for d in by_customer.values() if len(d) >= 2),
        "n_gaps": len(gaps),
        **{f"p{q}": float(values[q]) for q in QUANTILES},
        # 판정은 이 정확한 값으로 한다(float 는 사람이 읽는 값).
        **{f"p{q}_exact": str(values[q]) for q in QUANTILES},
        "definition": {"interval": INTERVAL_DEFINITION, "quantile_method": QUANTILE_DEFINITION},
    }
    gj.write_outputs([(out / INTERVALS_FILE,
                       json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False) + "\n")])
    return result


# ── judge — 기준 ──────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class Comparison:
    threshold: str   # simulator_config churn 아래 키
    quantile: int


@dataclass(frozen=True)
class ChurnBlock:
    profile: str
    days: int
    comparisons: tuple[Comparison, ...]
    thresholds_from: str
    thresholds_key_path: str   # thresholds_from 의 두 번째 토큰 — 임계값 config 안의 점 경로
    tolerance_ratio: Fraction
    texts: dict[str, str]


def split_source_ref(text: Any, label: str, problems: list[str]) -> tuple[str, str] | None:
    """`"<파일> <점 경로>"` 형식의 출처 표기를 (파일, 점 경로)로 나눈다."""
    parts = text.split() if isinstance(text, str) else []
    if len(parts) != 2:
        problems.append(f"{label} 가 '<파일> <점 경로>' 형식이 아니다: {text!r}")
        return None
    return parts[0], parts[1]


def resolve_key_path(node: Any, key_path: str) -> Any:
    for part in key_path.split("."):
        node = node.get(part) if isinstance(node, dict) else None
    return node


def load_churn_block(raw: Any, path: Path) -> ChurnBlock:
    """기준 yaml 의 `churn_threshold` 블록을 읽는다. 키가 없거나 형식이 다르면 `InputError`."""
    block = raw.get(CHURN_BLOCK) if isinstance(raw, dict) else None
    if not isinstance(block, dict):
        raise InputError([f"기준 파일 {path}: {CHURN_BLOCK} 블록이 없다"])
    problems: list[str] = []
    label = f"기준 파일 {path}: {CHURN_BLOCK}"
    if block.get("role") != CHURN_ROLE:
        problems.append(f"{label}.role 이 {CHURN_ROLE!r} 가 아니다: {block.get('role')!r}")
    for key in CHURN_TEXT_KEYS:
        if not (isinstance(block.get(key), str) and block[key].strip()):
            problems.append(f"{label}.{key} 가 비어 있지 않은 문자열이 아니다")

    source = block.get("source")
    profile = days = None
    if not isinstance(source, dict):
        problems.append(f"{label}.source 가 없다")
    else:
        profile, days = source.get("profile"), source.get("days")
        if not (isinstance(profile, str) and profile):
            problems.append(f"{label}.source.profile 이 비어 있지 않은 문자열이 아니다")
        if not (gj._is_int(days) and days > 0):
            problems.append(f"{label}.source.days 가 양의 정수가 아니다")
        if source.get("customers_from") != CUSTOMERS_FROM:
            problems.append(f"{label}.source.customers_from 이 {CUSTOMERS_FROM!r} 가 아니다: "
                            f"{source.get('customers_from')!r}")

    comparisons: list[Comparison] = []
    items = block.get("comparisons")
    if not (isinstance(items, list) and items):
        problems.append(f"{label}.comparisons 가 비어 있다")
        items = []
    for item in items:
        threshold = item.get("threshold") if isinstance(item, dict) else None
        quantile = item.get("quantile") if isinstance(item, dict) else None
        if not (isinstance(threshold, str) and threshold and gj._is_int(quantile) and 0 < quantile < 100):
            problems.append(f"{label}.comparisons 항목 {item!r} 은 threshold(문자열) · quantile(1~99 정수)이 아니다")
            continue
        if quantile not in QUANTILES:
            # measure 가 내지 않는 분위수다 — 측정 파일에 값이 없으므로 판정할 수 없다.
            problems.append(f"{label}.comparisons quantile {quantile} 은 measure 가 내지 않는다({list(QUANTILES)})")
            continue
        comparisons.append(Comparison(threshold, quantile))
    if len({c.threshold for c in comparisons}) != len(comparisons):
        problems.append(f"{label}.comparisons 의 threshold 가 중복된다")

    ref = split_source_ref(block.get("thresholds_from"), f"{label}.thresholds_from", problems)
    tolerance_raw = block.get("tolerance_ratio")
    tolerance = None
    if isinstance(tolerance_raw, (int, float)) and not isinstance(tolerance_raw, bool):
        # yaml 의 0.2 는 float 다. 쓰인 십진 문자열 그대로 분수로 바꿔 0.2000000000000000111 같은 이진 오차를 없앤다.
        tolerance = Fraction(str(tolerance_raw))
        if not 0 <= tolerance < 1:
            problems.append(f"{label}.tolerance_ratio {tolerance_raw!r} 가 [0, 1) 밖이다")
    else:
        problems.append(f"{label}.tolerance_ratio 가 수가 아니다: {tolerance_raw!r}")

    if problems:
        raise InputError(problems)
    return ChurnBlock(
        profile=profile, days=days, comparisons=tuple(comparisons), thresholds_from=block["thresholds_from"],
        thresholds_key_path=ref[1], tolerance_ratio=tolerance,
        texts={key: block[key] for key in CHURN_TEXT_KEYS},
    )


def load_thresholds(block: ChurnBlock, config_path: Path) -> dict[str, int]:
    """임계값 정본(simulator_config 의 `thresholds_from` 경로)에서 비교마다 임계값(일)을 읽는다."""
    config = gj._load_yaml(config_path, "시뮬레이터 config")
    node = resolve_key_path(config, block.thresholds_key_path)
    problems: list[str] = []
    if not isinstance(node, dict):
        raise InputError([f"시뮬레이터 config {config_path}: {block.thresholds_key_path} 블록이 없다"])
    thresholds: dict[str, int] = {}
    for comparison in block.comparisons:
        value = node.get(comparison.threshold)
        if not (gj._is_int(value) and value > 0):
            problems.append(f"시뮬레이터 config {config_path}: {block.thresholds_key_path}.{comparison.threshold} "
                            f"가 양의 정수가 아니다: {value!r}")
            continue
        thresholds[comparison.threshold] = value
    if problems:
        raise InputError(problems)
    return thresholds


# ── judge — 입력 · 판정 ───────────────────────────────────────────────────────

def intervals_seed(report: dict[str, Any]) -> int | None:
    seed = report.get("seed")
    return seed if gj._is_int(seed) else None


def check_measurement_conditions(
    block: ChurnBlock, customers: int, intervals: dict[int, tuple[Path, dict[str, Any]]], problems: list[str]
) -> None:
    """측정 파일이 기준의 조건(profile · customers · days)으로 잰 것이고 분위수 값이 있는지 본다."""
    expected = {"profile": block.profile, "customers": customers, "days": block.days}
    for seed, (path, report) in sorted(intervals.items()):
        for key, want in expected.items():
            got = report.get(key)
            if got != want or type(got) is not type(want):
                problems.append(f"churn 간격 {path}: {key} {got!r} ≠ 기준 {want!r}")
        for comparison in block.comparisons:
            try:
                exact_value(report, comparison.quantile)
            except ValueError as exc:
                problems.append(f"churn 간격 {path} (seed {seed}): {exc}")


def exact_value(report: dict[str, Any], quantile: int) -> Fraction:
    """측정 파일의 `p{q}_exact`(분수 문자열). `p{q}`(float)와 같은 값이 아니면 `ValueError`."""
    shown, exact = report.get(f"p{quantile}"), report.get(f"p{quantile}_exact")
    if not gj._is_finite_number(shown):
        raise ValueError(f"p{quantile} 가 유한한 수가 아니다 ({shown!r})")
    try:
        value = Fraction(exact) if isinstance(exact, str) else None
    except (ValueError, ZeroDivisionError):
        value = None
    if value is None:
        raise ValueError(f"p{quantile}_exact 가 분수 문자열이 아니다 ({exact!r})")
    if float(value) != shown:
        raise ValueError(f"p{quantile}_exact {exact} 와 p{quantile} {shown!r} 가 다르다")
    return value


def judge_comparison(comparison: Comparison, threshold: int, tolerance: Fraction,
                     values: dict[int, Fraction]) -> dict[str, Any]:
    """비교 하나 — seed 별 Pq 와 seed 평균 Pq 가 모두 |Pq − 임계값| ≤ tolerance × 임계값(경계 포함)이면 pass."""
    allowed = tolerance * threshold

    def within(value: Fraction) -> bool:
        return abs(value - threshold) <= allowed

    seed_verdicts = {seed: "pass" if within(v) else "fail" for seed, v in values.items()}
    mean = sum(values.values(), Fraction(0)) / len(values)
    mean_verdict = "pass" if within(mean) else "fail"
    reasons: list[str] = []
    lo, hi = threshold - allowed, threshold + allowed
    if mean_verdict == "fail":
        reasons.append(f"seed 평균 P{comparison.quantile} {float(mean):.6g} 가 [{float(lo):.6g}, {float(hi):.6g}] 밖이다")
    outside = sorted(seed for seed, v in seed_verdicts.items() if v == "fail")
    if outside:
        reasons.append(f"seed {outside} 의 P{comparison.quantile} 가 허용 폭 밖이다")
    passed = mean_verdict == "pass" and not outside
    return {
        "threshold": comparison.threshold, "threshold_days": threshold, "quantile": comparison.quantile,
        "allowed": [float(lo), float(hi)], "allowed_exact": [str(lo), str(hi)],
        "values": {seed: float(v) for seed, v in values.items()},
        "values_exact": {seed: str(v) for seed, v in values.items()}, "seed_verdicts": seed_verdicts,
        "mean": float(mean), "mean_exact": str(mean), "mean_verdict": mean_verdict,
        "verdict": "pass" if passed else "fail", "reasons": reasons,
    }


def _same_across_seeds(intervals: dict[int, tuple[Path, dict[str, Any]]], key: str, problems: list[str]) -> Any:
    values = {repr(report.get(key)) for _, report in intervals.values()}
    if len(values) > 1:
        # 봉인할 커밋 하나에서 잰 값만 함께 판정한다(DR-208) — 섞였으면 평균이 어느 판의 값도 아니다.
        problems.append(f"churn 간격의 {key} 가 seed 마다 다르다: {sorted(values)}")
        return None
    return next(iter(intervals.values()))[1].get(key) if intervals else None


def evaluate(criteria, block: ChurnBlock, thresholds: dict[str, int], interval_paths: list[str],
             thresholds_file: str) -> dict[str, Any]:
    """측정 파일을 기준과 대조해 판정 리포트를 만든다. 입력이 기준과 맞지 않으면 `InputError`."""
    problems: list[str] = []
    files = gj.collect_files(interval_paths, INTERVALS_FILE, "churn 간격", problems)
    intervals = gj.pair_by_seed(files, "churn 간격", intervals_seed, criteria.seeds, problems)
    if problems:
        raise InputError(problems)
    version = _same_across_seeds(intervals, "simulator_version", problems)
    commit = _same_across_seeds(intervals, "source_commit", problems)
    if not problems and not (isinstance(version, str) and version):
        problems.append(f"churn 간격의 simulator_version 을 확인할 수 없다({version!r}) — 판정하지 않는다")
    check_measurement_conditions(block, criteria.customers, intervals, problems)
    if problems:
        raise InputError(problems)

    rows = [
        judge_comparison(c, thresholds[c.threshold], block.tolerance_ratio,
                         {seed: exact_value(intervals[seed][1], c.quantile) for seed in criteria.seeds})
        for c in block.comparisons
    ]
    met = all(row["verdict"] == "pass" for row in rows)
    report = {
        "criteria": {"path": criteria.path, "version": criteria.version, "block": CHURN_BLOCK},
        "seeds": list(criteria.seeds), "customers": criteria.customers,
        "source": {"profile": block.profile, "days": block.days},
        "simulator_version": version, "source_commit": commit,
        "thresholds": {"from": block.thresholds_from, "file": thresholds_file, "values": thresholds},
        "tolerance_ratio": str(block.tolerance_ratio),
        "definition": {"interval": block.texts["interval"], "quantile_method": block.texts["quantile_method"],
                       "rule": block.texts["rule"]},
        "inputs": {seed: str(path) for seed, (path, _) in sorted(intervals.items())},
        "n_gaps": {seed: data.get("n_gaps") for seed, (_, data) in sorted(intervals.items())},
        "comparisons": rows,
        "met": met,
    }
    report["evidence"] = evidence_line(report)
    report["verdict"] = {"met": met, "exit_code": EXIT_PASS if met else EXIT_FAIL,
                         "on_fail": None if met else block.texts["on_fail"]}
    return report


def evidence_line(report: dict[str, Any]) -> str:
    """`freeze.ChurnThresholdEvidence.evidence` 에 넣을 한 줄 — 기준 경로 · seed · 분위수 평균 · 판정."""
    parts = [
        f"P{row['quantile']} 평균 {row['mean']:.6g}일 vs {row['threshold']} {row['threshold_days']}일 "
        f"(허용 [{row['allowed'][0]:.6g}, {row['allowed'][1]:.6g}], {row['verdict']})"
        for row in report["comparisons"]
    ]
    return (f"data_spec §5.1 ①~③ — 기준 {report['criteria']['path']} {CHURN_BLOCK} · seed {report['seeds']} × "
            f"{report['customers']}명 {report['source']['profile']} {report['source']['days']}일 · "
            f"{report['simulator_version']} · " + " · ".join(parts)
            + f" · met={'true' if report['met'] else 'false'}")


def render_md(report: dict[str, Any]) -> str:
    seeds = report["seeds"]
    head = "충족 (met=true)" if report["met"] else "미충족 (met=false)"
    lines = [
        f"# GATE 1 churn 임계값 근거 (data_spec §5.1 ①~③) — {head}",
        "",
        f"- 기준: `{report['criteria']['path']}` ({report['criteria']['version']}) `{CHURN_BLOCK}`",
        f"- seed {seeds} × {report['customers']}명 · profile {report['source']['profile']} · "
        f"{report['source']['days']}일 · 처치 없음 · simulator_version {report['simulator_version']} · "
        f"source_commit {report['source_commit']}",
        f"- 임계값 정본: `{report['thresholds']['file']}` ({report['thresholds']['from']}) · 허용 폭 ±{report['tolerance_ratio']} × 임계값(경계 포함)",
        f"- 간격: {report['definition']['interval']}",
        f"- 분위수: {report['definition']['quantile_method']}",
        "",
        "| 임계값 | 분위수 | 허용 범위(일) | " + " | ".join(f"seed {s}" for s in seeds) + " | 평균 | 판정 |",
        "|---|---|---|" + "---|" * len(seeds) + "---|---|",
    ]
    for row in report["comparisons"]:
        cells = [f"{row['values'][s]:.6g} ({row['seed_verdicts'][s]})" for s in seeds]
        lines.append(
            f"| {row['threshold']} = {row['threshold_days']}일 | P{row['quantile']} | "
            f"[{row['allowed'][0]:.6g}, {row['allowed'][1]:.6g}] | " + " | ".join(cells)
            + f" | {row['mean']:.6g} ({row['mean_verdict']}) | **{row['verdict']}** |")
    reasons = [f"- {row['threshold']}: {'; '.join(row['reasons'])}" for row in report["comparisons"] if row["reasons"]]
    if reasons:
        lines += [""] + reasons
    lines += ["", f"evidence: `{report['evidence']}`"]
    if not report["met"]:
        lines += ["", f"on_fail: {report['verdict']['on_fail']}"]
    return "\n".join(lines) + "\n"


# ── CLI ───────────────────────────────────────────────────────────────────────

def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="GATE 1 churn 임계값 근거(data_spec §5.1 ①~③) — measure 로 재고 judge 로 판정한다")
    commands = parser.add_subparsers(dest="command", required=True)
    m = commands.add_parser("measure", help="처치 없는 세계의 구매 간격 P75 · P90 을 잰다")
    m.add_argument("--seed", type=int, required=True)
    m.add_argument("--customers", type=int, required=True)
    m.add_argument("--out", required=True, help="새 디렉터리(이미 있으면 거부)")
    m.add_argument("--profile", default=DEFAULT_PROFILE)
    m.add_argument("--days", type=int, default=DEFAULT_DAYS)
    j = commands.add_parser("judge", help="seed 별 측정 파일을 기준과 대조해 판정한다 — 0 met · 1 not met · 2 · 3")
    j.add_argument("--criteria", default=str(DEFAULT_CRITERIA))
    j.add_argument("--simulator-config", default=str(DEFAULT_SIMULATOR_CONFIG), help="임계값 정본")
    j.add_argument("--intervals", nargs="+", required=True,
                   help=f"measure 가 낸 {INTERVALS_FILE} 또는 그것이 든 디렉터리 — seed 마다 하나")
    j.add_argument("--out-json")
    j.add_argument("--out-md")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.command == "measure":
            result = measure(args.seed, args.customers, args.profile, args.days, Path(args.out))
            print(json.dumps({k: result[k] for k in ("seed", "n_gaps", "p75", "p90", "simulator_version")},
                             ensure_ascii=False))
            return EXIT_PASS
        return _judge(args)
    except InputError as exc:
        print("입력 오류 — 측정 · 판정하지 않았다(met 이 아니다):", file=sys.stderr)
        for problem in exc.problems:
            print(f"  - {problem}", file=sys.stderr)
        return EXIT_INPUT_ERROR
    except Exception as exc:  # noqa: BLE001 — 판정 결과(0 · 1)와 섞이지 않게 예상 밖 예외를 3 으로 모은다
        print(f"내부 오류 — 측정 · 판정하지 않았거나 남기지 못했다(met 이 아니다): {type(exc).__name__}: {exc}",
              file=sys.stderr)
        return EXIT_INTERNAL_ERROR


def _judge(args: argparse.Namespace) -> int:
    outputs = [(Path(path), kind) for path, kind in ((args.out_md, "md"), (args.out_json, "json")) if path]
    if len(outputs) == 2 and outputs[0][0].resolve() == outputs[1][0].resolve():
        raise InputError([f"--out-md 와 --out-json 이 같은 경로다: {args.out_md}"])
    criteria_path = Path(args.criteria)
    criteria = gj.load_criteria(criteria_path)
    block = load_churn_block(gj._load_yaml(criteria_path, "기준 파일"), criteria_path)
    thresholds = load_thresholds(block, Path(args.simulator_config))
    report = evaluate(criteria, block, thresholds, args.intervals, str(args.simulator_config))
    text = render_md(report)
    payload = json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False) + "\n"
    gj.write_outputs([(path, text if kind == "md" else payload) for path, kind in outputs])
    print(text, end="")
    return report["verdict"]["exit_code"]


if __name__ == "__main__":
    sys.exit(main())
