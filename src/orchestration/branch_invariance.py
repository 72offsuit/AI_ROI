"""분기 간 대조 — 처치받지 않은 고객의 분기 창 결과가 분기와 무관한가 (DR-234 P3 반증 조건 · DR-170-gate2-lock G5).

한 실행의 결과 폴더(``run_meta.json`` · 명부 ``split_roster.csv`` · 분기별 배정 파일 · 분기 원본 ``branches/S0~S5/raw``)를 읽어
두 고객군의 **고객별** [t2, end) 이벤트 수 · 유형별 수 · purchase 수 · purchase ``order_amount`` 합을 기준 분기 S0 과 다른
분기마다 대조한다.

- (가) ``non_eligible`` — 분기 창 이벤트가 있는 고객 중 Eligible(t2)(명부의 t2 행) 밖.
- (나) ``untreated_eligible`` — Eligible(t2) 중 어느 분기에서도 처치 대상이 아닌 고객.

모든 분기 · 모든 고객이 같으면 ``same``, 하나라도 다르면 ``differs``(그때 DR-234 P3 기각을 다시 본다). 명부가 없으면
``not_run``. **봉인 대상 분기(``REQUIRED_BRANCHES`` = 실행 루프의 S0~S5) 중 하나라도** 배정 파일 · 원본이 없거나 그 분기 단계가
``ok`` 가 아니면 ``incomplete`` 와 빠진 분기 · 사유다 — 있는 분기만으로 ``same`` 을 내지 않는다(PR #327 리뷰, DR-170-gate2-lock G5).
경로가 있어도 **원본이 실행 당시와 같은지** 다시 대조한다(PR #327 2차 리뷰): 결과 파일(``strategy_comparison.json``)에 남은 분기별
읽기 근거(실행 ID · 파일 · 크기 · 행 수)를 같은 실행의 기록에 맞춰 ``verify_event_run`` 으로 다시 확인하고, 읽은 뒤 파일이 바뀌지
않았는지 본다. 파티션이 하나라도 빠지거나 다르면 그 분기는 ``incomplete`` 다.
다른 값으로 근사하지 않는다. 결과에는 고객 ID 를 넣지 않는다(수와 합계만).

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
from typing import Any, Iterable, Iterator, Mapping, Sequence

KST = timezone(timedelta(hours=9), "KST")
REFERENCE_BRANCH = "S0"
#: 대조해야 하는 분기 — ``run_sprint.STRATEGIES`` 와 같다(시험이 AST 로 대조한다). S6 은 분기를 만들지 않는다(실측은 #305).
REQUIRED_BRANCHES: tuple[str, ...] = ("S0", "S1", "S2", "S3", "S4", "S5")
RESULT_FILE = "branch_invariance.json"
#: ``run_sprint.ROSTER_FILE`` 과 같은 이름(시험이 대조한다) — 무거운 실행 루프를 import 하지 않는다.
ROSTER_FILE = "split_roster.csv"
#: ``run_sprint.RESULT_FILES`` 의 ``strategy_comparison`` 결과 파일 — 분기별 읽기 근거(``event_read_evidence``)가 여기 있다.
COMPARISON_FILE = "strategy_comparison.json"
ROSTER_ORIGIN = "t2"
GROUPS = ("non_eligible", "untreated_eligible")
DEFINITION = (
    "고객별 [t2, end) 이벤트 수 · 유형별 수 · purchase 수 · purchase order_amount 합을 기준 분기 S0 과 대조한다. "
    "대상은 비Eligible(t2) 고객과 어느 분기에서도 처치 대상이 아닌 Eligible(t2) 고객(DR-234 조사 표 마지막 행)"
)


class NotRun(Exception):
    """대조에 필요한 입력이 없다."""


class Incomplete(Exception):
    """봉인 대상 분기 중 대조할 수 없는 분기가 있다 — ``missing`` = {분기: 사유}."""

    def __init__(self, missing: Mapping[str, str]) -> None:
        super().__init__("; ".join(f"{b}: {r}" for b, r in missing.items()))
        self.missing = dict(missing)


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
    statuses = branch_stage_statuses(meta)
    missing: dict[str, str] = {}
    for branch in REQUIRED_BRANCHES:
        reasons = []
        if statuses.get(branch) != "ok":
            reasons.append(f"단계 strategy_{branch} = {statuses.get(branch)!r}(ok 아님)")
        if branch not in strategy_files:
            reasons.append("run_meta 에 배정 파일 경로가 없다")
        elif not Path(str(strategy_files[branch])).exists():
            reasons.append("배정 파일이 없다")
        if branch not in raw_roots:
            reasons.append("run_meta 에 원본 경로가 없다")
        elif not Path(str(raw_roots[branch])).exists():
            reasons.append("분기 원본이 없다")
        if reasons:
            missing[branch] = " · ".join(reasons)
    roster_name = (meta.get("split_roster") or {}).get("file") or ROSTER_FILE
    return {
        "run_id": meta.get("run_id"), "start": _when(timeline["t2"]), "end": _when(timeline["end"]),
        "history_t2": (meta.get("event_read_evidence") or {}).get("t2"),
        "recorded_reads": recorded_reads(run_dir, meta.get("run_id")),
        "branches": list(REQUIRED_BRANCHES), "missing": missing,
        "raw_roots": {s: Path(str(raw_roots[s])) for s in REQUIRED_BRANCHES if s not in missing},
        "assignments": {s: Path(str(strategy_files[s])) for s in REQUIRED_BRANCHES if s not in missing},
        "roster": run_dir / str(roster_name),
        "extra_branches": sorted(set(strategy_files) - set(REQUIRED_BRANCHES)),
    }


def recorded_reads(run_dir: Path, run_id: Any) -> dict[str, Any]:
    """같은 실행의 결과 파일에 남은 분기별 읽기 근거(실행 당시 ``verify_event_run`` 결과). 없으면 분기마다 사유 문자열."""
    path = Path(run_dir) / COMPARISON_FILE
    if not path.exists():
        return {s: f"{COMPARISON_FILE} 가 없다 — 실행 당시 분기 읽기 근거를 알 수 없다" for s in REQUIRED_BRANCHES}
    comparison = _read_json(path)
    if run_id is None or comparison.get("run_id") != run_id:
        return {s: f"{COMPARISON_FILE} run_id {comparison.get('run_id')!r} ≠ run_meta {run_id!r}" for s in REQUIRED_BRANCHES}
    details = comparison.get("strategy_details") or {}
    return {s: ((details.get(s) or {}).get("event_read_evidence")
                or f"{COMPARISON_FILE} 에 이 분기의 event_read_evidence 가 없다") for s in REQUIRED_BRANCHES}


def _sizes(fingerprints: Any) -> dict[str, Any] | None:
    """``{파일: [크기, mtime_ns]}`` → ``{파일: 크기}``. mtime 은 결과 폴더를 옮기면 바뀌어 대조하지 않는다(내용은 다이제스트가 본다)."""
    if not isinstance(fingerprints, Mapping):
        return None
    out = {}
    for name, signature in fingerprints.items():
        if not isinstance(signature, (list, tuple)) or len(signature) != 2:
            return None
        out[str(name)] = signature[0]
    return out


def verify_branch_read(root: Path, recorded: Any, history: Any) -> tuple[dict[str, Any] | None, str | None]:
    """분기 원본을 실행 당시 기록과 다시 대조한다 — ``(지금의 근거, None)`` 또는 ``(None, 사유)``.

    1. 실행 당시 읽기 근거가 ``ok`` 이고 실행 ID 가 있어야 한다(없으면 그 분기는 검증된 적이 없다).
    2. 그 실행 ID 로 ``verify_event_run`` 을 다시 돌린다 — 실행 기록의 파일 목록 · 다이제스트 · 행 수와 디스크가 같은지,
       기록하지 않은 파티션이 없는지. 실행 루프(``_branch_proof``)와 같이 분기 루트만으로 먼저 보고, 안 되면 본선 t2
       읽기 근거(``run_meta.event_read_evidence.t2``)를 외부 부모로 넘긴다.
    3. 결과 파일에 남은 행 수 · 파일 수 · 파일별 크기와 지금이 같아야 한다(분기 루트의 실행 기록까지 함께 바뀐 경우).
    4. 실행 당시 내용 다이제스트(``public_stream_content`` · ``history_content``)가 있어야 한다 — 내용 대조는
       ``branch_invariance`` 가 분기 원본을 읽으면서 한다(``content_mismatch``, PR #327 3차 리뷰). 2 · 3 은 지금의 디스크와
       지금의 실행 기록이 서로 맞는지와 크기만 본다 — 같은 크기로 값만 바꾸고 실행 기록을 다시 쓰면 통과한다.
    """
    from src.decision.observation_contract import verify_event_run

    if isinstance(recorded, str):
        return None, recorded
    if not isinstance(recorded, Mapping) or recorded.get("status") != "ok" or not isinstance(recorded.get("run_id"), str):
        status = recorded.get("status") if isinstance(recorded, Mapping) else None
        return None, f"실행 당시 분기 읽기 근거가 ok 가 아니다(status={status!r})"
    if not (_is_digest(recorded.get("public_stream_content")) and _is_digest(recorded.get("history_content"))):
        return None, ("실행 당시 내용 다이제스트(public_stream_content · history_content)가 없다 — 분기 원본의 내용을 "
                      "실행 당시와 대조할 수 없다")
    run_id = recorded["run_id"]
    proof = verify_event_run(root, run_id)
    if proof.get("status") != "ok" and isinstance(history, Mapping):
        local = proof.get("reason")
        proof = verify_event_run(root, run_id, history_evidence=history)
        if proof.get("status") != "ok":
            return None, f"분기 원본 재검증 실패 — 분기 루트: {local}; 본선 history: {proof.get('reason')}"
    if proof.get("status") != "ok":
        return None, f"분기 원본 재검증 실패 — {proof.get('reason')}"
    then, now = _sizes(recorded.get("fingerprints")), _sizes(proof.get("fingerprints"))
    problems = []
    if then is None or now is None:
        problems.append("파일 지문을 읽을 수 없다")
    elif then != now:
        lost, added = sorted(set(then) - set(now)), sorted(set(now) - set(then))
        resized = sorted(n for n in set(then) & set(now) if then[n] != now[n])
        problems.append(f"실행 당시와 파일이 다르다(빠짐 {lost} · 추가 {added} · 크기 다름 {resized})")
    for key in ("raw_rows", "n_files"):
        if recorded.get(key) != proof.get(key):
            problems.append(f"{key} 실행 당시 {recorded.get(key)!r} · 지금 {proof.get(key)!r}")
    if problems:
        return None, "분기 원본이 실행 당시와 다르다 — " + " · ".join(problems)
    return proof, None


def _unchanged(root: Path, proof: Mapping[str, Any]) -> bool:
    """읽는 동안 파일이 바뀌지 않았다 — 실행 루프 ``_unchanged_files`` 와 같은 크기 · mtime 대조."""
    for name, signature in (proof.get("fingerprints") or {}).items():
        path = Path(root) / name
        if not path.is_file():
            return False
        stat = path.stat()
        if [stat.st_size, stat.st_mtime_ns] != list(signature):
            return False
    return True


def _is_digest(value: Any) -> bool:
    """``event_content_digest`` 의 모양 — ``{"rows": int, "sha256": str}``."""
    return (isinstance(value, Mapping) and isinstance(value.get("rows"), int) and not isinstance(value.get("rows"), bool)
            and isinstance(value.get("sha256"), str) and len(value["sha256"]) == 64)


def _hashed(events: Iterable[Mapping[str, Any]], hashes: list[bytes]) -> Iterator[Mapping[str, Any]]:
    """이벤트를 그대로 넘기면서 행마다 공개 22필드 내용 지문(``event_content_hash``)을 모은다 — 서명과 내용 대조가
    같은 한 번의 읽기를 쓴다(대조한 행과 센 행이 다를 틈이 없다)."""
    from src.decision.observation_contract import event_content_hash

    for event in events:
        hashes.append(event_content_hash(event))
        yield event


def history_hashes(history: Any) -> tuple[list[bytes] | None, str | None]:
    """본선 t2 원본(실행 당시 분기 읽기의 history — ``run_meta.event_read_evidence.t2.root``)의 행 지문.

    실행 루프는 분기 읽기 때 ``event_content_digest(본선 행 지문 + 분기 행 지문)`` 을 ``public_stream_content`` 로 남긴다
    (``run_sprint`` 의 통제된 분기 읽기). 그 값을 다시 내려면 본선 행 지문이 필요하다. 본선 원본은 t2 뒤로 쓰이지
    않는다(분기는 각자의 ``branches/S0~S5/raw`` 로 복원 · 진행한다).
    """
    from src.measurement import sink

    root = history.get("root") if isinstance(history, Mapping) else None
    if not isinstance(root, str) or not Path(root).is_dir():
        return None, ("본선 t2 원본 경로(run_meta.event_read_evidence.t2.root)를 알 수 없다 — 분기 내용을 실행 당시와 "
                      "대조할 수 없다")
    hashes: list[bytes] = []
    try:
        for _ in _hashed(sink.read_events(Path(root)), hashes):
            pass
    except (OSError, ValueError) as error:
        return None, f"본선 t2 원본의 내용 지문을 낼 수 없다: {type(error).__name__}: {error}"
    return hashes, None


def content_mismatch(recorded: Mapping[str, Any], history: list[bytes], branch: list[bytes]) -> str | None:
    """실행 당시 내용 다이제스트와 지금의 원본 내용을 대조한다 — 어긋나면 사유, 같으면 ``None``."""
    from src.decision.observation_contract import event_content_digest

    def show(d: Mapping[str, Any]) -> str:
        return f"{d.get('rows')}행 · sha256 {str(d.get('sha256'))[:12]}"

    then_history, now_history = recorded["history_content"], event_content_digest(history)
    if (then_history["rows"], then_history["sha256"]) != (now_history["rows"], now_history["sha256"]):
        return f"본선 history 내용이 실행 당시와 다르다(실행 당시 {show(then_history)} · 지금 {show(now_history)})"
    then, now = recorded["public_stream_content"], event_content_digest(history + branch)
    if (then["rows"], then["sha256"]) != (now["rows"], now["sha256"]):
        return f"분기 원본 내용이 실행 당시와 다르다(본선 + 분기 실행 당시 {show(then)} · 지금 {show(now)})"
    return None


def branch_stage_statuses(meta: Mapping[str, Any]) -> dict[str, Any]:
    """``run_meta.stages`` 의 분기 단계(``strategy_<S>``) 마지막 상태. 기록이 없는 분기는 빠진다."""
    out: dict[str, Any] = {}
    for stage in meta.get("stages") or []:
        name = stage.get("name") if isinstance(stage, Mapping) else None
        if isinstance(name, str) and name.startswith("strategy_"):
            out[name[len("strategy_"):]] = stage.get("status")
    return out


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

    record: dict[str, Any] = {"status": "not_run", "result": None, "complete": False, "run_id": None,
                              "reference": REFERENCE_BRANCH, "required_branches": list(REQUIRED_BRANCHES),
                              "definition": DEFINITION, "source": "DR-234 반증 조건 · DR-170-gate2-lock G5"}
    try:
        inputs = _inputs(Path(run_dir))
        record["run_id"] = inputs["run_id"]
        eligible = eligible_t2(inputs["roster"])
        if inputs["missing"]:
            raise Incomplete(inputs["missing"])
        proofs, unverified = {}, {}
        for branch in inputs["branches"]:
            proofs[branch], why = verify_branch_read(
                inputs["raw_roots"][branch], inputs["recorded_reads"].get(branch), inputs["history_t2"])
            if why is not None:
                unverified[branch] = why
        if unverified:
            raise Incomplete(unverified)
        history, why = history_hashes(inputs["history_t2"])
        if history is None:
            raise Incomplete({branch: why for branch in inputs["branches"]})
        treated: set[str] = set()
        for path in inputs["assignments"].values():
            treated |= {str(c) for c in (_read_json(path).get("assignments") or {})}
        signatures: dict[str, dict[str, tuple]] = {}
        window_stats: dict[str, dict[str, int]] = {}
        changed: dict[str, str] = {}
        for branch in inputs["branches"]:
            root = inputs["raw_roots"][branch]
            hashes: list[bytes] = []
            try:
                signatures[branch], window_stats[branch] = customer_signatures(
                    _hashed(sink.read_events(root), hashes), inputs["start"], inputs["end"])
            except ValueError as error:
                changed[branch] = f"분기 원본 행의 내용 지문을 낼 수 없다: {error}"
                continue
            if not _unchanged(root, proofs[branch]):
                raise Incomplete({branch: "읽는 도중 분기 원본 파일이 바뀌었다"})
            mismatch = content_mismatch(inputs["recorded_reads"][branch], history, hashes)
            if mismatch is not None:
                changed[branch] = mismatch
        if changed:
            raise Incomplete(changed)
    except NotRun as reason:
        return {**record, "reason": str(reason)}
    except Incomplete as gap:
        return {**record, "status": "incomplete", "complete": False, "branches": list(REQUIRED_BRANCHES),
                "missing_branches": gap.missing,
                "reason": f"봉인 대상 분기 {len(gap.missing)}개를 대조할 수 없다 — 있는 분기만으로 판정하지 않는다"}
    seen = set().union(*(set(s) for s in signatures.values()))
    groups = {"non_eligible": sorted(seen - eligible), "untreated_eligible": sorted(eligible - treated)}
    compared = compare(signatures, groups)
    return {
        **record, "status": "ok", "reason": None, **compared, "complete": True,
        "window": {"start": inputs["start"].isoformat(), "end": inputs["end"].isoformat()},
        "branches": inputs["branches"], "missing_branches": {}, "extra_branches": inputs["extra_branches"],
        "n_eligible_t2": len(eligible), "n_treated_any_branch": len(treated & eligible),
        "n_treated_outside_eligible": len(treated - eligible),
        "events_by_branch": window_stats,
        "branch_reads": {b: {"run_id": p.get("run_id"), "raw_rows": p.get("raw_rows"), "n_files": p.get("n_files"),
                             "method": p.get("method"), "content_verified": True,
                             "public_stream_content": inputs["recorded_reads"][b]["public_stream_content"]}
                         for b, p in proofs.items()},
        "history_content": inputs["recorded_reads"][inputs["branches"][0]]["history_content"],
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
        print(f"{result['status']} — {result['reason']}")
        for branch, why in (result.get("missing_branches") or {}).items():
            print(f"  {branch}: {why}")
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
