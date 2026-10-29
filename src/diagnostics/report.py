"""S8 사후 진단 리포트 CLI — 두 GATE 봉인 뒤에만 실제 결과에 돈다.

    python -m src.diagnostics.report --ground-truth DIR --results DIR --out JSON [--allow-unsealed]

실행 가드 (DR-142-diagnostics-sprint):

- **GATE 1** — ``config/gate1_lock.yaml`` 이 ``experiment_environment_v1_declared: true`` 이고
  ``declaration`` 이 ``PARTIAL_FREEZE`` 가 아니며 ``simulator_commit`` 이 기록돼 있어야 봉인으로 본다.
- **GATE 2** — 봉인 기록의 **위치·형식이 아직 정해지지 않았다**(D7 #89). 미정은 거부다.
  D7 이 기록을 정하면 ``gate2_status`` 를 그 기록을 읽도록 고친다.
- 둘 중 하나라도 봉인되지 않았으면 종료 코드 ``EXIT_REFUSED`` 로 거부하고 사유를 출력한다.
- ``--allow-unsealed`` 는 **합성 데이터 시험 전용**이다. 이때도 저장소의 실제
  ``data/ground_truth/`` · ``results/`` 아래 경로는 거부한다.

이 리포트는 orchestration 이 부르지 않는다. 리포트 생성 단계에서 독립 실행한다.
결과를 모델·전략 개선에 쓰지 않는다 (`src/diagnostics/AGENTS.md`).
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from pathlib import Path
from typing import Any, Mapping, Sequence

REPO_ROOT = Path(__file__).resolve().parents[2]
GATE1_LOCK = REPO_ROOT / "config" / "gate1_lock.yaml"
#: GATE 2 봉인 기록 위치 — **미정**(D7 #89). None 이면 거부한다.
GATE2_RECORD: Path | None = None
REAL_GROUND_TRUTH = REPO_ROOT / "data" / "ground_truth"
REAL_RESULTS = REPO_ROOT / "results"

EXIT_OK = 0
EXIT_REFUSED = 3
EXIT_INPUT_ERROR = 4

ARMS = ("T1", "T2", "T3", "T4")
CONTROL_ARM = "T0"

#: Ground truth 한 줄(고객 1명)의 키 — ``docs/simulator_api.md`` 「참 효과 기록 형식」 이 정본이다(#167).
#: 시뮬레이터 판의 실제 키와 다르면 이 dict 만 고친다.
#:   outcomes[팔][purchased|revenue|contribution_profit|marketing_cost], tau_purchase[팔] (선택)
GT_KEYS: dict[str, str] = {
    "customer_id": "customer_id",
    "assigned": "assigned",
    "outcomes": "outcomes",
    "purchased": "purchased",
    "revenue": "revenue",
    "contribution_profit": "contribution_profit",
    "marketing_cost": "marketing_cost",
    "tau": "tau_purchase",
}

#: 고객별 τ̂ 파일 — **현재 스프린트 결과에 없다**(필요한 산출물). 형식 제안:
#: ``<results>/cate.jsonl`` 또는 ``cate.csv``, 열 ``customer_id`` · ``cate_T1`` … ``cate_T4``.
CATE_FILES = ("cate.jsonl", "cate.csv")
CATE_KEYS: dict[str, str] = {"customer_id": "customer_id", "arm_prefix": "cate_"}

PO_NAME = re.compile(r"^po-(?P<world>W-[^-]+|[^-]+)-(?P<t0>[^-]+)-(?P<state>[^-]+)-(?P<assignment>.+)$")


class InputError(Exception):
    """입력 파일이 없거나 형식이 맞지 않는다."""


# ---------------------------------------------------------------------------
# 봉인 가드
# ---------------------------------------------------------------------------

def gate1_status(lock_path: Path = GATE1_LOCK) -> dict[str, Any]:
    if not lock_path.is_file():
        return {"sealed": False, "reasons": [f"GATE 1 기록이 없다: {lock_path}"]}
    try:
        import yaml
    except ImportError:
        return {"sealed": False, "reasons": ["BLOCKED: PyYAML 미설치 — GATE 1 기록을 읽을 수 없다"]}
    try:
        record = yaml.safe_load(lock_path.read_text(encoding="utf-8")) or {}
    except (OSError, yaml.YAMLError) as exc:
        return {"sealed": False, "reasons": [f"GATE 1 기록을 읽지 못했다: {exc}"]}
    reasons: list[str] = []
    if record.get("experiment_environment_v1_declared") is not True:
        reasons.append("GATE 1: EXPERIMENT_ENVIRONMENT_v1 미선언")
    if record.get("declaration") in (None, "PARTIAL_FREEZE"):
        reasons.append(f"GATE 1: declaration={record.get('declaration')!r} (부분 봉인)")
    if not record.get("simulator_commit"):
        reasons.append("GATE 1: simulator_commit 미기록")
    return {"sealed": not reasons, "reasons": reasons,
            "declaration": record.get("declaration"),
            "simulator_commit": record.get("simulator_commit")}


def gate2_status(record_path: Path | None = GATE2_RECORD) -> dict[str, Any]:
    if record_path is None:
        return {"sealed": False,
                "reasons": ["GATE 2: 봉인 기록의 위치·형식이 정해지지 않았다(D7 #89) — 미정은 거부"]}
    # 위치가 정해져도 형식 판독은 D7 이 정한 뒤 구현한다. 그 전까지는 존재만으로 봉인으로 보지 않는다.
    return {"sealed": False,
            "reasons": [f"GATE 2: 기록 형식 판독이 구현되지 않았다({record_path}) — 거부"]}


def _inside(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False


def guard(ground_truth: Path, results: Path, allow_unsealed: bool,
          lock_path: Path = GATE1_LOCK, gate2_record: Path | None = GATE2_RECORD) -> dict[str, Any]:
    """실행 허가 판정. ``allowed`` 가 False 면 실행하지 않는다."""
    g1 = gate1_status(lock_path)
    g2 = gate2_status(gate2_record)
    sealed = g1["sealed"] and g2["sealed"]
    out = {"gate1": g1, "gate2": g2, "sealed": sealed, "allow_unsealed": allow_unsealed}
    if sealed:
        return {**out, "allowed": True, "reasons": []}
    if not allow_unsealed:
        return {**out, "allowed": False, "reasons": g1["reasons"] + g2["reasons"]}
    real = [str(p) for p, root in ((ground_truth, REAL_GROUND_TRUTH), (results, REAL_RESULTS))
            if _inside(p, root)]
    if real:
        return {**out, "allowed": False,
                "reasons": [f"--allow-unsealed 는 합성 데이터 전용이다 — 실제 경로 거부: {real}"]}
    return {**out, "allowed": True,
            "reasons": ["미봉인 상태에서 --allow-unsealed 로 실행 — 합성 데이터 시험 전용"]}


# ---------------------------------------------------------------------------
# 입력
# ---------------------------------------------------------------------------

def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open(encoding="utf-8") as fh:
        for lineno, line in enumerate(fh, 1):
            if not line.strip():
                continue
            try:
                row = json.loads(line)
            except ValueError as exc:
                raise InputError(f"{path}:{lineno}: JSON 이 아니다 ({exc})") from exc
            if not isinstance(row, dict):
                raise InputError(f"{path}:{lineno}: 객체가 아니다")
            rows.append(row)
    return rows


def ground_truth_files(root: Path) -> list[Path]:
    """``root`` 또는 ``root/simulator`` 의 ``po-*.jsonl``."""
    files = sorted(root.glob("po-*.jsonl")) or sorted((root / "simulator").glob("po-*.jsonl"))
    if not files:
        raise InputError(f"ground truth 파일(po-*.jsonl)이 없다: {root}")
    return files


def parse_truth_row(row: Mapping[str, Any], keys: Mapping[str, str] = GT_KEYS) -> dict[str, Any]:
    """고객 1명 → {customer_id, assigned, y0, y1[팔], tau[팔], tau_source}.

    τ 는 **잠재 구매 여부의 차** Y(t) − Y(T0) 로 유도한다(§14 Qini 결과변수 = Retention).
    파일에 τ 가 있으면 대조만 하고, 결과(outcomes)가 없을 때만 그것을 쓴다.
    """
    try:
        cid = str(row[keys["customer_id"]])
        assigned = str(row[keys["assigned"]])
    except KeyError as exc:
        raise InputError(f"ground truth 행에 키가 없다: {exc} (GT_KEYS 확인)") from exc
    outcomes = row.get(keys["outcomes"])
    file_tau = row.get(keys["tau"]) or {}
    y: dict[str, int] = {}
    if isinstance(outcomes, Mapping):
        for arm, outcome in outcomes.items():
            if isinstance(outcome, Mapping) and keys["purchased"] in outcome:
                y[str(arm)] = int(bool(outcome[keys["purchased"]]))
    tau: dict[str, float] = {}
    mismatch: list[str] = []
    source = "outcomes"
    if CONTROL_ARM in y:
        for arm in ARMS:
            if arm in y:
                tau[arm] = float(y[arm] - y[CONTROL_ARM])
                if arm in file_tau and float(file_tau[arm]) != tau[arm]:
                    mismatch.append(arm)
    elif isinstance(file_tau, Mapping) and file_tau:
        source = "file_tau"
        tau = {str(a): float(v) for a, v in file_tau.items() if str(a) in ARMS}
    return {"customer_id": cid, "assigned": assigned, "y": y, "tau": tau,
            "tau_source": source, "tau_mismatch": mismatch}


def load_cate(results: Path, keys: Mapping[str, str] = CATE_KEYS) -> dict[str, dict[str, float]] | None:
    """고객별 τ̂ — 없으면 None (필요한 산출물)."""
    prefix = keys["arm_prefix"]
    for name in CATE_FILES:
        path = results / name
        if not path.is_file():
            continue
        if name.endswith(".jsonl"):
            rows = _read_jsonl(path)
        else:
            with path.open(encoding="utf-8", newline="") as fh:
                rows = list(csv.DictReader(fh))
        cate: dict[str, dict[str, float]] = {}
        for row in rows:
            cid = str(row[keys["customer_id"]])
            cate[cid] = {arm: float(row[prefix + arm]) for arm in ARMS
                         if row.get(prefix + arm) not in (None, "")}
        return cate
    return None


# ---------------------------------------------------------------------------
# 채점
# ---------------------------------------------------------------------------

def score_file(path: Path, cate: Mapping[str, Mapping[str, float]] | None,
               eps: float = 0.0) -> dict[str, Any]:
    from src.diagnostics import scoring

    match = PO_NAME.match(path.stem)
    parsed = [parse_truth_row(r) for r in _read_jsonl(path)]
    block: dict[str, Any] = {
        "file": path.name,
        "name": match.groupdict() if match else None,
        "n": len(parsed),
        "tau_source": sorted({p["tau_source"] for p in parsed}),
        "tau_file_mismatch": sum(1 for p in parsed if p["tau_mismatch"]),
        "arms": {},
    }
    for arm in ARMS:
        # 이 팔과 대조군(T0)에 배정된 고객만 — 관측 Y = Y(배정 팔).
        pop = [p for p in parsed if p["assigned"] in (arm, CONTROL_ARM)
               and arm in p["tau"] and p["assigned"] in p["y"]]
        if not pop:
            block["arms"][arm] = {"status": "not_run", "reason": "이 팔·대조군 배정 고객이 없다"}
            continue
        w = [1 if p["assigned"] == arm else 0 for p in pop]
        y_obs = [p["y"][p["assigned"]] for p in pop]
        tau = [p["tau"][arm] for p in pop]
        quads = [scoring.quadrant_of(p["y"][arm], p["y"][CONTROL_ARM]) for p in pop]
        arm_block: dict[str, Any] = {"n": len(pop), "n_treated": sum(w)}
        if sum(w) == 0 or sum(w) == len(w):
            arm_block.update(status="not_run", reason="처치군 또는 대조군이 비었다 — Qini 불가")
            block["arms"][arm] = arm_block
            continue
        arm_block["qini_oracle"] = scoring.qini_oracle(tau, w, y_obs)
        if cate is None:
            arm_block.update(status="partial",
                             reason="필요한 산출물: 고객별 τ̂ (cate.jsonl / cate.csv) — 결과에 없다")
        else:
            have = [i for i, p in enumerate(pop) if arm in cate.get(p["customer_id"], {})]
            if len(have) < len(pop):
                arm_block["tau_hat_missing"] = len(pop) - len(have)
            if not have:
                arm_block.update(status="partial", reason=f"τ̂ 에 {arm} 열이 없다")
            else:
                sub = lambda xs: [xs[i] for i in have]  # noqa: E731
                tau_hat = [cate[pop[i]["customer_id"]][arm] for i in have]
                arm_block.update(scoring.score_arm(tau_hat, sub(tau), sub(w), sub(y_obs),
                                                   sub(quads), eps))
                arm_block["status"] = "ok"
        block["arms"][arm] = arm_block
    return block


def build_report(ground_truth: Path, results: Path, guard_result: Mapping[str, Any],
                 eps: float = 0.0) -> dict[str, Any]:
    cate = load_cate(results)
    files = ground_truth_files(ground_truth)
    return {
        "report": "s8-diagnostics/v0",
        "sealed": guard_result["sealed"],
        "allow_unsealed": guard_result["allow_unsealed"],
        "guard_reasons": list(guard_result["reasons"]),
        "use_restriction": "사후 진단 전용 — 모델·Feature·Threshold·전략·예산 개선에 쓰지 않는다",
        "inputs": {"ground_truth": str(ground_truth), "results": str(results),
                   "tau_hat": "present" if cate is not None else "missing",
                   "uplift_eval_present": (results / "uplift_eval.json").is_file()},
        "outcome": "retention — 효과 창 42일 안 구매 여부 Y, τ = Y(t) − Y(T0)",
        "quadrant_eps": eps,
        "files": _with_superseded([score_file(p, cate, eps) for p in files], files),
    }


def _with_superseded(blocks: list[dict[str, Any]], files: list[Path]) -> list[dict[str, Any]]:
    """효과 창 안에서 다시 배정돼 관측이 끊긴 행 수를 파일마다 싣는다(#167).

    나중 파일의 ``supersedes.file`` 이 끊긴 배정의 파일 이름(확장자 없이)을, 그 행의 고객이 끊긴 고객을 가리킨다.
    고객 ID 와 배정 시각은 world · 스냅샷 분기 사이에서 겹치므로 파일 이름까지 맞아야 센다(#167 리뷰). 그 행의
    참 효과는 "더 배정하지 않았을 때" 의 값이다. 채점에서 뺄지는 DR-S8 이 정한다 — 여기서는 세기만 한다.
    """
    cut: set[tuple[str, str]] = set()
    for path in files:
        for row in _read_jsonl(path):
            prior = row.get("supersedes")
            if isinstance(prior, Mapping) and prior.get("file"):
                cut.add((str(prior["file"]), str(row.get(GT_KEYS["customer_id"]))))
    for block, path in zip(blocks, files):
        block["superseded_rows"] = sum(
            1 for row in _read_jsonl(path) if (path.stem, str(row.get(GT_KEYS["customer_id"]))) in cut
        )
    return blocks


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m src.diagnostics.report",
                                     description="S8 사후 진단 — 두 GATE 봉인 뒤에만 실행")
    parser.add_argument("--ground-truth", required=True, type=Path)
    parser.add_argument("--results", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--allow-unsealed", action="store_true",
                        help="합성 데이터 시험 전용. 실제 data/ground_truth·results 경로는 여전히 거부")
    parser.add_argument("--quadrant-eps", type=float, default=0.0)
    args = parser.parse_args(argv)

    decision = guard(args.ground_truth, args.results, args.allow_unsealed)
    if not decision["allowed"]:
        print("S8 실행 거부:", file=sys.stderr)
        for reason in decision["reasons"]:
            print(f"  - {reason}", file=sys.stderr)
        return EXIT_REFUSED
    for reason in decision["reasons"]:
        print(f"경고: {reason}", file=sys.stderr)
    try:
        report = build_report(args.ground_truth, args.results, decision, args.quadrant_eps)
    except InputError as exc:
        print(f"입력 오류: {exc}", file=sys.stderr)
        return EXIT_INPUT_ERROR
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
                        encoding="utf-8")
    print(f"S8 리포트: {args.out}")
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
