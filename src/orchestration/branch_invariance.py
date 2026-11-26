"""분기 간 대조 — 처치받지 않은 고객의 분기 창 결과가 분기와 무관한가 (DR-234 P3 반증 조건 · DR-170-gate2-lock G5).

한 실행의 결과 폴더(``run_meta.json`` · 명부 ``split_roster.csv`` · 분기별 배정 파일 · 분기 원본 ``branches/<S>/raw``)를 읽어
두 고객군의 **고객별** [t2, end) 이벤트 수 · 유형별 수 · purchase 수 · purchase ``order_amount`` 합을 기준 분기 S0 과 다른
분기마다 대조한다.

- (가) ``non_eligible`` — 분기 창 이벤트가 있는 고객 중 Eligible(t2)(명부의 t2 행) 밖.
- (나) ``untreated_eligible`` — Eligible(t2) 중 어느 분기에서도 처치 대상이 아닌 고객.

모든 분기 · 모든 고객이 같으면 ``same``, 하나라도 다르면 ``differs``(그때 DR-234 P3 기각을 다시 본다). 명부 · 배정 파일 ·
분기 원본 중 하나라도 없으면 ``not_run`` — 다른 값으로 근사하지 않는다. 결과에는 고객 ID 를 넣지 않는다(수와 합계만).

    python -m src.orchestration.branch_invariance <결과 폴더> [--out 경로]
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import sys
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

KST = timezone(timedelta(hours=9), "KST")
REFERENCE_BRANCH = "S0"
RESULT_FILE = "branch_invariance.json"
#: ``run_sprint.ROSTER_FILE`` 과 같은 이름(시험이 대조한다) — 무거운 실행 루프를 import 하지 않는다.
ROSTER_FILE = "split_roster.csv"
ROSTER_ORIGIN = "t2"
GROUPS = ("non_eligible", "untreated_eligible")
DEFINITION = (
    "고객별 [t2, end) 이벤트 수 · 유형별 수 · purchase 수 · purchase order_amount 합을 기준 분기 S0 과 대조한다. "
    "대상은 비Eligible(t2) 고객과 어느 분기에서도 처치 대상이 아닌 Eligible(t2) 고객(DR-234 조사 표 마지막 행)"
)


class NotRun(Exception):
    """대조에 필요한 입력이 없다."""


def _when(value: Any) -> datetime:
    from src.measurement.timeparse import parse_datetime

    moment = value if isinstance(value, datetime) else parse_datetime(str(value))
    return moment if moment.tzinfo is not None else moment.replace(tzinfo=KST)


def _amount(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def customer_signatures(events: Iterable[Mapping[str, Any]], start: datetime,
                        end: datetime) -> tuple[dict[str, tuple], dict[str, int]]:
    """이벤트 → 고객별 서명 ``(이벤트 수, 유형별 수, purchase 수, order_amount 합, 금액 결손 수)``. 창 [start, end) 만 센다."""
    types: dict[str, Counter] = {}
    revenue: dict[str, float] = {}
    missing_amount: Counter = Counter()
    stats = {"n_events_read": 0, "n_outside_window": 0}
    for event in events:
        stats["n_events_read"] += 1
        moment = _when(event["timestamp"])
        if not (start <= moment < end):
            stats["n_outside_window"] += 1
            continue
        cid = str(event["customer_id"])
        kind = str(event["event_type"])
        types.setdefault(cid, Counter())[kind] += 1
        if kind == "purchase":
            amount = _amount(event.get("order_amount"))
            if amount is None:
                missing_amount[cid] += 1
            else:
                revenue[cid] = revenue.get(cid, 0.0) + amount
    signatures = {
        cid: (sum(counts.values()), tuple(sorted(counts.items())), counts.get("purchase", 0),
              round(revenue.get(cid, 0.0), 6), missing_amount.get(cid, 0))
        for cid, counts in types.items()
    }
    return signatures, stats


EMPTY_SIGNATURE: tuple = (0, (), 0, 0.0, 0)


def _read_json(path: Path) -> Mapping[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def eligible_t2(roster: Path) -> set[str]:
    """명부의 t2 행 = Eligible(t2) 고객(``split_roster.build`` 이 t2 Eligible 고객으로 행을 만든다)."""
    if not roster.exists():
        raise NotRun(f"명부 {roster.name} 가 없다 — Eligible(t2) 를 다시 판정하지 않는다")
    with roster.open(encoding="utf-8", newline="") as handle:
        rows = [row for row in csv.DictReader(handle) if row.get("origin") == ROSTER_ORIGIN]
    if not rows:
        raise NotRun(f"명부에 {ROSTER_ORIGIN} 행이 없다 — Eligible(t2) 를 알 수 없다")
    return {str(row["customer_id"]) for row in rows}


def _inputs(run_dir: Path) -> dict[str, Any]:
    meta_path = run_dir / "run_meta.json"
    if not meta_path.exists():
        raise NotRun(f"{meta_path} 가 없다")
    meta = _read_json(meta_path)
    timeline = meta.get("timeline") or {}
    if not timeline.get("t2") or not timeline.get("end"):
        raise NotRun("run_meta.timeline 에 t2 · end 가 없다 — 분기 창을 알 수 없다")
    raw_roots = meta.get("raw_roots") or {}
    strategy_files = (meta.get("assignment_files") or {}).get("strategies") or {}
    branches = [s for s in sorted(strategy_files) if s in raw_roots and Path(str(raw_roots[s])).exists()]
    if REFERENCE_BRANCH not in branches:
        raise NotRun(f"기준 분기 {REFERENCE_BRANCH} 의 배정 파일 또는 원본이 없다")
    if len(branches) < 2:
        raise NotRun("대조할 분기가 둘 이상 없다")
    roster_name = (meta.get("split_roster") or {}).get("file") or ROSTER_FILE
    return {
        "start": _when(timeline["t2"]), "end": _when(timeline["end"]), "branches": branches,
        "raw_roots": {s: Path(str(raw_roots[s])) for s in branches},
        "assignments": {s: Path(str(strategy_files[s])) for s in branches},
        "roster": run_dir / str(roster_name),
        "skipped_branches": sorted(set(strategy_files) - set(branches)),
    }


def compare(signatures: Mapping[str, Mapping[str, tuple]], groups: Mapping[str, Sequence[str]],
            reference: str = REFERENCE_BRANCH) -> dict[str, Any]:
    """분기별 서명 → 고객군별 · 분기별 다른 고객 수와 합계. ``result`` = same · differs."""
    out: dict[str, Any] = {}
    differs = False
    base = signatures[reference]
    for group, members in groups.items():
        by_branch = {}
        for branch, sigs in signatures.items():
            seen = [sigs.get(cid, EMPTY_SIGNATURE) for cid in members]
            n_diff = 0 if branch == reference else sum(
                1 for cid, sig in zip(members, seen) if sig != base.get(cid, EMPTY_SIGNATURE))
            differs |= n_diff > 0
            by_branch[branch] = {
                "n_differing_vs_reference": n_diff,
                "n_customers_with_events": sum(1 for sig in seen if sig[0] > 0),
                "events": sum(sig[0] for sig in seen),
                "purchases": sum(sig[2] for sig in seen),
                "revenue_krw": round(sum(sig[3] for sig in seen), 6),
                "purchases_missing_amount": sum(sig[4] for sig in seen),
            }
        out[group] = {"n_customers": len(members), "by_branch": by_branch}
    return {"result": "differs" if differs else "same", "groups": out}


def branch_invariance(run_dir: Path) -> dict[str, Any]:
    """결과 폴더 하나의 분기 간 대조. 입력이 없으면 ``status: not_run`` 과 사유."""
    from src.measurement import sink

    record: dict[str, Any] = {"status": "not_run", "result": None, "reference": REFERENCE_BRANCH,
                              "definition": DEFINITION, "source": "DR-234 반증 조건 · DR-170-gate2-lock G5"}
    try:
        inputs = _inputs(Path(run_dir))
        eligible = eligible_t2(inputs["roster"])
        treated: set[str] = set()
        for branch, path in inputs["assignments"].items():
            if not path.exists():
                raise NotRun(f"{branch} 배정 파일이 없다")
            treated |= {str(c) for c in (_read_json(path).get("assignments") or {})}
    except NotRun as reason:
        return {**record, "reason": str(reason)}
    signatures: dict[str, dict[str, tuple]] = {}
    window_stats: dict[str, dict[str, int]] = {}
    for branch in inputs["branches"]:
        signatures[branch], window_stats[branch] = customer_signatures(
            sink.read_events(inputs["raw_roots"][branch]), inputs["start"], inputs["end"])
    seen = set().union(*(set(s) for s in signatures.values()))
    groups = {"non_eligible": sorted(seen - eligible), "untreated_eligible": sorted(eligible - treated)}
    compared = compare(signatures, groups)
    return {
        **record, "status": "ok", "reason": None, **compared,
        "window": {"start": inputs["start"].isoformat(), "end": inputs["end"].isoformat()},
        "branches": inputs["branches"], "skipped_branches": inputs["skipped_branches"],
        "n_eligible_t2": len(eligible), "n_treated_any_branch": len(treated & eligible),
        "n_treated_outside_eligible": len(treated - eligible),
        "events_by_branch": window_stats,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("run_dir", type=Path, help="결과 폴더(run_meta.json 이 있는 곳)")
    parser.add_argument("--out", type=Path, default=None, help=f"기본: <결과 폴더>/{RESULT_FILE}")
    args = parser.parse_args(argv)
    result = branch_invariance(args.run_dir)
    out = args.out or args.run_dir / RESULT_FILE
    out.write_text(json.dumps(result, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    if result["status"] != "ok":
        print(f"not_run — {result['reason']}")
        return 2
    lines = [f"{result['result']} — 기준 {REFERENCE_BRANCH}, 분기 {', '.join(result['branches'])}"]
    for group in GROUPS:
        info = result["groups"][group]
        diffs = {b: v["n_differing_vs_reference"] for b, v in info["by_branch"].items() if b != REFERENCE_BRANCH}
        lines.append(f"  {group}: {info['n_customers']}명, 다른 고객 수 {diffs}")
    lines.append(f"기록: {out}")
    print("\n".join(lines))
    return 0 if result["result"] == "same" else 1


if __name__ == "__main__":
    sys.exit(main())
