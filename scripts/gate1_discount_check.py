"""GATE 1 가정 A-DISCOUNT 실측 — 시뮬레이터 주문의 할인액이 처치 단가와 정확히 같은가.

기준은 `config/simulator_gate1_acceptance.yaml` 의 `a_discount` 블록이다. 단가는 여기에 적지 않는다 —
정본은 `config/economic_config.yaml` `treatment_cost.{arm}.unit_cost_krw`(블록의 `unit_cost_from`)다.

입력은 seed 마다 `scripts/research/run_world.py` 출력 디렉터리 하나다(GATE 1 realism 세계를 그대로 쓴다).
  - `meta.json`                          — seed · customers · profile · days · assign_day · config
                                           (기준 `sample.customers` · `sources.realism.world` 와 같아야 한다)
  - `assignments.json`                   — `assigned_at` · `assignments{customer_id: arm}`
  - `raw/simulator_exchange/orders.jsonl` — `order_id` · `customer_id` · `ordered_at` · `discount`

규칙(seed 마다): ⓪ `coupon_arms` 의 팔마다 할인 주문이 `min_discounted_orders_per_arm` 건 이상이고(할인 주문이
없으면 확인한 것이 없다 — 0 건 통과를 막는다), discount > 0 인 주문은 전부
  ① `coupon_arms` 에 배정된 고객의 주문이고(위반 `not_coupon_arm` — 미배정 · 다른 팔),
  ② `ordered_at ≥ assigned_at` 이고(위반 `before_assignment`),
  ③ discount 가 그 고객 팔의 단가와 같아야 한다(위반 `wrong_amount` — ① 을 지킨 주문만 따진다).
한 주문이 여러 위반에 해당하면 종류마다 센다. 모든 seed 에서 ⓪ 을 채우고 위반이 0 건이면 통과다.
orders.jsonl 은 seed 당 수십 MB 라 한 줄씩 읽는다.

종료 코드
    0  모든 seed 가 팔별 최소 할인 주문 수를 채우고 위반 0 건
    1  최소 할인 주문 수 미달 또는 위반이 한 건 이상(판정은 끝났다)
    2  입력 오류 — 판정하지 않았다: seed 누락 · 중복 · 초과, customers · 세계 조건(profile · days · assign_day
       · config) 불일치, 파일 없음 · JSON 깨짐,
       주문 필드 형식 이상(discount 가 수가 아님, 시각에 시간대 없음), 기준 블록 키 없음, 단가 없음
    3  내부 오류 — PyYAML 미설치, 출력 쓰기 실패 등
    판정하지 않은 것을 통과로 적지 않는다 — 2 · 3 은 어느 쪽도 통과가 아니다.

사용
    python scripts/gate1_discount_check.py --criteria config/simulator_gate1_acceptance.yaml \\
        --economic-config config/economic_config.yaml --worlds <D1> ... <D5> [--out-json J] [--out-md M]
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

# 같은 디렉터리의 gate1_* 스크립트를 import 한다. sys.path[0] 에 기대지 않는다 — `python -P` · PYTHONSAFEPATH 나
# 다른 cwd 에서 불러도 찾도록 이 파일의 디렉터리를 직접 넣는다. PyYAML 은 gate1_judge 가 쓸 때만 import 한다.
_SCRIPTS_DIR = str(Path(__file__).resolve().parent)
if _SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, _SCRIPTS_DIR)

import gate1_churn_check as cc  # noqa: E402
import gate1_judge as gj  # noqa: E402
from gate1_judge import EXIT_FAIL, EXIT_INPUT_ERROR, EXIT_INTERNAL_ERROR, EXIT_PASS, InputError  # noqa: E402

REPO = Path(__file__).resolve().parents[1]
DEFAULT_CRITERIA = REPO / "config" / "simulator_gate1_acceptance.yaml"
DEFAULT_ECONOMIC_CONFIG = REPO / "config" / "economic_config.yaml"



DISCOUNT_BLOCK = "a_discount"
DISCOUNT_ROLE = "assumption_check"
DISCOUNT_TEXT_KEYS = ("source", "unit_cost_from", "rule", "on_fail")
ARM_PLACEHOLDER = "{arm}"
VIOLATION_KINDS = ("not_coupon_arm", "before_assignment", "wrong_amount")
UNASSIGNED = "unassigned"
EXAMPLES_PER_KIND = 5

META_FILE = "meta.json"
ASSIGNMENTS_FILE = "assignments.json"
ORDERS_FILE = Path("raw") / "simulator_exchange" / "orders.jsonl"


# ── 기준 ─────────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class DiscountBlock:
    coupon_arms: tuple[str, ...]
    min_discounted_orders_per_arm: int
    unit_cost_from: str
    unit_cost_key_template: str   # unit_cost_from 의 두 번째 토큰 — `{arm}` 이 든 점 경로
    texts: dict[str, str]


def load_discount_block(raw: Any, path: Path) -> DiscountBlock:
    """기준 yaml 의 `a_discount` 블록을 읽는다. 키가 없거나 형식이 다르면 `InputError`."""
    block = raw.get(DISCOUNT_BLOCK) if isinstance(raw, dict) else None
    if not isinstance(block, dict):
        raise InputError([f"기준 파일 {path}: {DISCOUNT_BLOCK} 블록이 없다"])
    problems: list[str] = []
    label = f"기준 파일 {path}: {DISCOUNT_BLOCK}"
    if block.get("role") != DISCOUNT_ROLE:
        problems.append(f"{label}.role 이 {DISCOUNT_ROLE!r} 가 아니다: {block.get('role')!r}")
    for key in DISCOUNT_TEXT_KEYS:
        if not (isinstance(block.get(key), str) and block[key].strip()):
            problems.append(f"{label}.{key} 가 비어 있지 않은 문자열이 아니다")
    arms = block.get("coupon_arms")
    if not (isinstance(arms, list) and arms and all(isinstance(a, str) and a for a in arms)):
        problems.append(f"{label}.coupon_arms 가 비어 있지 않은 문자열 목록이 아니다")
        arms = []
    elif len(set(arms)) != len(arms):
        problems.append(f"{label}.coupon_arms 에 중복이 있다 {arms}")
    minimum = block.get("min_discounted_orders_per_arm")
    if not (gj._is_int(minimum) and minimum > 0):
        problems.append(f"{label}.min_discounted_orders_per_arm 이 양의 정수가 아니다: {minimum!r}")
    ref = cc.split_source_ref(block.get("unit_cost_from"), f"{label}.unit_cost_from", problems)
    if ref is not None and ARM_PLACEHOLDER not in ref[1]:
        problems.append(f"{label}.unit_cost_from 의 경로에 {ARM_PLACEHOLDER} 가 없다: {ref[1]!r}")
    if problems:
        raise InputError(problems)
    return DiscountBlock(coupon_arms=tuple(arms), min_discounted_orders_per_arm=minimum,
                         unit_cost_from=block["unit_cost_from"],
                         unit_cost_key_template=ref[1], texts={k: block[k] for k in DISCOUNT_TEXT_KEYS})


@dataclass(frozen=True)
class RealismWorld:
    """기준 `sources.realism.world` — run_world 세계 조건. A-DISCOUNT 와 orchestrator 가 함께 읽는다."""
    profile: str
    days: int
    assign_day: int
    config: str | None

    def as_meta(self) -> dict[str, Any]:
        return {"profile": self.profile, "days": self.days, "assign_day": self.assign_day, "config": self.config}


def load_realism_world(raw: Any, path: Path) -> RealismWorld:
    """기준 yaml 의 `sources.realism.world` 를 읽는다. 키가 없거나 형식이 다르면 `InputError`.

    `config` 는 키가 있어야 한다(null 은 정본 생성 설정) — 빠진 것을 null 로 메우면 실험 config 세계를 놓친다.
    """
    sources = raw.get("sources") if isinstance(raw, dict) else None
    realism = sources.get("realism") if isinstance(sources, dict) else None
    world = realism.get("world") if isinstance(realism, dict) else None
    label = f"기준 파일 {path}: sources.realism.world"
    if not isinstance(world, dict):
        raise InputError([f"{label} 블록이 없다"])
    problems: list[str] = []
    if not (isinstance(world.get("profile"), str) and world["profile"]):
        problems.append(f"{label}.profile 이 비어 있지 않은 문자열이 아니다")
    for key in ("days", "assign_day"):
        if not (gj._is_int(world.get(key)) and world[key] > 0):
            problems.append(f"{label}.{key} 가 양의 정수가 아니다: {world.get(key)!r}")
    if "config" not in world or not (world["config"] is None or isinstance(world["config"], str)):
        problems.append(f"{label}.config 가 없거나 null · 문자열이 아니다")
    if not problems and not world["assign_day"] < world["days"]:
        problems.append(f"{label}: assign_day {world['assign_day']} 가 days {world['days']} 보다 작지 않다")
    if problems:
        raise InputError(problems)
    return RealismWorld(world["profile"], world["days"], world["assign_day"], world["config"])


def load_unit_costs(block: DiscountBlock, config_path: Path) -> dict[str, int]:
    """쿠폰 팔마다 경제 config 의 단가(원)를 읽는다. 양의 정수가 아니면 `InputError`."""
    config = gj._load_yaml(config_path, "경제 config")
    problems: list[str] = []
    costs: dict[str, int] = {}
    for arm in block.coupon_arms:
        key_path = block.unit_cost_key_template.replace(ARM_PLACEHOLDER, arm)
        value = cc.resolve_key_path(config, key_path)
        if not (gj._is_int(value) and value > 0):
            problems.append(f"경제 config {config_path}: {key_path} 가 양의 정수가 아니다: {value!r}")
            continue
        costs[arm] = value
    if problems:
        raise InputError(problems)
    return costs


# ── 입력 ─────────────────────────────────────────────────────────────────────

def _aware(raw: Any, label: str) -> datetime:
    cc._ensure_repo_on_path()
    from src.measurement import timeparse

    try:
        moment = timeparse.parse_datetime(str(raw)) if isinstance(raw, str) else None
    except ValueError:
        moment = None
    # 시간대 없는 시각은 배정 시각과 비교할 수 없다(naive 와 aware 비교는 예외, 추측하면 경계가 9시간 밀린다).
    if moment is None or moment.utcoffset() is None:
        raise InputError([f"{label}: 시간대가 있는 ISO 시각이 아니다 ({raw!r})"])
    return moment


def _read_assignments(path: Path) -> tuple[datetime, dict[str, str]]:
    problems: list[str] = []
    data = gj._read_json(path, "배정 기록", problems)
    if problems:
        raise InputError(problems)
    assigned_at = _aware(data.get("assigned_at"), f"배정 기록 {path} assigned_at")
    assignments = data.get("assignments")
    if not (isinstance(assignments, dict)
            and all(isinstance(k, str) and isinstance(v, str) for k, v in assignments.items())):
        raise InputError([f"배정 기록 {path}: assignments 가 {{customer_id: arm}} 문자열 객체가 아니다"])
    return assigned_at, assignments


def _discount(value: Any, label: str) -> int | float:
    if not (isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value) and value >= 0):
        raise InputError([f"{label}: discount 가 0 이상의 유한한 수가 아니다 ({value!r})"])
    return value


def scan_world(world: Path, unit_costs: dict[str, int], minimum: int) -> dict[str, Any]:
    """세계 하나의 주문을 한 줄씩 읽어 할인 주문을 규칙과 대조한다. `unit_costs` 의 키가 쿠폰 팔이다."""
    assigned_at, assignments = _read_assignments(world / ASSIGNMENTS_FILE)
    orders_path = world / ORDERS_FILE
    total = discounted = 0
    by_arm: dict[str, int] = {}
    violations = {kind: 0 for kind in VIOLATION_KINDS}
    not_coupon_by_arm: dict[str, int] = {}
    examples: dict[str, list[dict[str, Any]]] = {kind: [] for kind in VIOLATION_KINDS}
    violating_orders = 0
    try:
        handle = orders_path.open(encoding="utf-8")
    except OSError as exc:
        raise InputError([f"주문 파일 {orders_path} 를 열지 못했다: {type(exc).__name__}: {exc}"]) from exc
    with handle:
        for lineno, line in enumerate(handle, 1):
            if not line.strip():
                continue
            where = f"주문 파일 {orders_path}:{lineno}"
            try:
                order = json.loads(line, parse_float=gj._reject_nonfinite, parse_constant=gj._reject_nonfinite)
            except ValueError as exc:
                raise InputError([f"{where}: JSON 으로 읽지 못했다: {exc}"]) from exc
            if not isinstance(order, dict):
                raise InputError([f"{where}: 객체가 아니다"])
            total += 1
            discount = _discount(order.get("discount"), where)
            if discount == 0:
                continue
            discounted += 1
            customer = order.get("customer_id")
            if not isinstance(customer, str):
                raise InputError([f"{where}: customer_id 가 문자열이 아니다"])
            arm = assignments.get(customer, UNASSIGNED)
            by_arm[arm] = by_arm.get(arm, 0) + 1
            ordered_at = _aware(order.get("ordered_at"), f"{where} ordered_at")
            kinds = []
            if arm not in unit_costs:
                kinds.append("not_coupon_arm")
                not_coupon_by_arm[arm] = not_coupon_by_arm.get(arm, 0) + 1
            elif discount != unit_costs[arm]:
                kinds.append("wrong_amount")
            if ordered_at < assigned_at:
                kinds.append("before_assignment")
            if kinds:
                violating_orders += 1
            for kind in kinds:
                violations[kind] += 1
                if len(examples[kind]) < EXAMPLES_PER_KIND:
                    examples[kind].append({"order_id": order.get("order_id"), "customer_id": customer, "arm": arm,
                                           "discount": discount, "ordered_at": order.get("ordered_at")})
    shortages = [{"arm": arm, "discounted_orders": by_arm.get(arm, 0), "minimum": minimum}
                 for arm in unit_costs if by_arm.get(arm, 0) < minimum]
    reasons = [f"{s['arm']} 할인 주문 {s['discounted_orders']}건 < 최소 {minimum}건 — 이 팔은 확인한 것이 없다"
               for s in shortages]
    if violating_orders:
        reasons.append(f"위반 주문 {violating_orders}건")
    return {
        "world": str(world), "assigned_at": assigned_at.isoformat(), "assigned_customers": len(assignments),
        "orders": total, "discounted_orders": discounted, "discounted_by_arm": dict(sorted(by_arm.items())),
        "violations": violations, "not_coupon_arm_by_arm": dict(sorted(not_coupon_by_arm.items())),
        "violating_orders": violating_orders, "examples": examples, "shortages": shortages, "reasons": reasons,
        "verdict": "pass" if not reasons else "fail",
    }


def _meta_seed(report: dict[str, Any]) -> int | None:
    seed = report.get("seed")
    return seed if gj._is_int(seed) else None


def evaluate(criteria, block: DiscountBlock, world_conditions: RealismWorld, unit_costs: dict[str, int],
             world_paths: list[str], economic_file: str) -> dict[str, Any]:
    """세계마다 할인 주문을 대조해 판정 리포트를 만든다. 입력이 기준과 맞지 않으면 `InputError`."""
    problems: list[str] = []
    metas: list[Path] = []
    for raw in world_paths:
        world = Path(raw)
        for required in (META_FILE, ASSIGNMENTS_FILE, ORDERS_FILE):
            if not (world / required).is_file():
                problems.append(f"세계 {world} 에 {required} 가 없다")
        metas.append(world / META_FILE)
    if problems:
        raise InputError(problems)
    worlds = gj.pair_by_seed(metas, "세계 meta", _meta_seed, criteria.seeds, problems)
    expected = {"customers": criteria.customers, **world_conditions.as_meta()}
    for seed, (path, meta) in sorted(worlds.items()):
        for key, want in expected.items():
            # bool 은 int 의 하위형이라 타입도 본다. 키가 없으면 None 과 같아 보이므로 따로 거부한다.
            if key not in meta or meta[key] != want or type(meta[key]) is not type(want):
                problems.append(f"세계 meta {path}: {key} {meta.get(key, '(없음)')!r} ≠ 기준 {want!r}")
    # 묶음 수십 MB 를 읽기 전에 seed · 조건부터 맞춘다.
    if problems:
        raise InputError(problems)

    seeds = {seed: scan_world(path.parent, unit_costs, block.min_discounted_orders_per_arm)
             for seed, (path, _) in sorted(worlds.items())}
    passed = all(row["verdict"] == "pass" for row in seeds.values())
    totals = {kind: sum(row["violations"][kind] for row in seeds.values()) for kind in VIOLATION_KINDS}
    return {
        "criteria": {"path": criteria.path, "version": criteria.version, "block": DISCOUNT_BLOCK},
        "seeds": list(criteria.seeds), "customers": criteria.customers,
        "unit_costs": {"from": block.unit_cost_from, "file": economic_file, "values": unit_costs},
        "coupon_arms": list(block.coupon_arms),
        "min_discounted_orders_per_arm": block.min_discounted_orders_per_arm,
        "world_conditions": world_conditions.as_meta(),
        "rule": block.texts["rule"],
        "per_seed": seeds,
        "violations_total": totals,
        "passed": passed,
        "verdict": {"passed": passed, "exit_code": EXIT_PASS if passed else EXIT_FAIL,
                    "on_fail": None if passed else block.texts["on_fail"]},
    }


def render_md(report: dict[str, Any]) -> str:
    head = "통과" if report["passed"] else "실패"
    costs = ", ".join(f"{arm} {cost}원" for arm, cost in report["unit_costs"]["values"].items())
    lines = [
        f"# GATE 1 가정 A-DISCOUNT — {head}",
        "",
        f"- 기준: `{report['criteria']['path']}` ({report['criteria']['version']}) `{DISCOUNT_BLOCK}`",
        f"- seed {report['seeds']} × {report['customers']}명 · 단가 정본 `{report['unit_costs']['file']}` "
        f"({report['unit_costs']['from']}): {costs}",
        f"- 규칙: {report['rule']}",
        "",
        f"- 팔별 최소 할인 주문: {report['min_discounted_orders_per_arm']}건 · 세계 조건 {report['world_conditions']}",
        "",
        "| seed | 주문 | 할인 주문 | 팔별 할인 주문 | 미배정 · 다른 팔 | 배정 전 | 금액 불일치 | 판정 |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for seed, row in report["per_seed"].items():
        arms = ", ".join(f"{arm} {n}" for arm, n in row["discounted_by_arm"].items()) or "—"
        v = row["violations"]
        lines.append(f"| {seed} | {row['orders']} | {row['discounted_orders']} | {arms} | {v['not_coupon_arm']} | "
                     f"{v['before_assignment']} | {v['wrong_amount']} | **{row['verdict']}** |")
    if not report["passed"]:
        lines += [""] + [f"- seed {seed}: {'; '.join(row['reasons'])}"
                         for seed, row in report["per_seed"].items() if row["reasons"]]
        lines += ["", "위반 예시(종류마다 최대 5건):"]
        for seed, row in report["per_seed"].items():
            for kind, items in row["examples"].items():
                for item in items:
                    lines.append(f"- seed {seed} {kind}: {json.dumps(item, ensure_ascii=False)}")
        lines += ["", f"on_fail: {report['verdict']['on_fail']}"]
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="GATE 1 가정 A-DISCOUNT — 종료 코드 0 통과 · 1 위반 있음 · 2 입력 오류 · 3 내부 오류")
    parser.add_argument("--criteria", default=str(DEFAULT_CRITERIA))
    parser.add_argument("--economic-config", default=str(DEFAULT_ECONOMIC_CONFIG), help="처치 단가 정본")
    parser.add_argument("--worlds", nargs="+", required=True, help="run_world.py 출력 디렉터리 — seed 마다 하나")
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
    except Exception as exc:  # noqa: BLE001 — 판정 결과(0 · 1)와 섞이지 않게 예상 밖 예외를 3 으로 모은다
        print(f"내부 오류 — 판정하지 않았거나 남기지 못했다(통과가 아니다): {type(exc).__name__}: {exc}",
              file=sys.stderr)
        return EXIT_INTERNAL_ERROR


def _run(args: argparse.Namespace) -> int:
    outputs = [(Path(path), kind) for path, kind in ((args.out_md, "md"), (args.out_json, "json")) if path]
    if len(outputs) == 2 and outputs[0][0].resolve() == outputs[1][0].resolve():
        raise InputError([f"--out-md 와 --out-json 이 같은 경로다: {args.out_md}"])
    criteria_path = Path(args.criteria)
    criteria = gj.load_criteria(criteria_path)
    raw = gj._load_yaml(criteria_path, "기준 파일")
    block = load_discount_block(raw, criteria_path)
    world_conditions = load_realism_world(raw, criteria_path)
    unit_costs = load_unit_costs(block, Path(args.economic_config))
    report = evaluate(criteria, block, world_conditions, unit_costs, args.worlds, str(args.economic_config))
    text = render_md(report)
    payload = json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False) + "\n"
    gj.write_outputs([(path, text if kind == "md" else payload) for path, kind in outputs])
    print(text, end="")
    return report["verdict"]["exit_code"]


if __name__ == "__main__":
    sys.exit(main())
