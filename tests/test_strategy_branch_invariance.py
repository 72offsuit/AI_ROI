"""분기 간 대조 — DR-234 P3 반증 조건 (#170 · DR-170-gate2-lock G5).

가짜 결과 폴더(run_meta · 명부 · 분기별 배정 파일 · 분기 원본 이벤트 · 실행 기록 · 결과 파일의 분기 읽기 근거)로 대조 규칙을
확인한다. 분기 원본 재검증(``verify_event_run``)이 파티션 행 수를 pandas 로 세므로 대조 시험은 pandas 가 있을 때만 돈다.
"""

from __future__ import annotations

import ast
import contextlib
import csv
import hashlib
import io
import json
import shutil
import tempfile
import unittest
from pathlib import Path
from typing import Any

from src.orchestration import branch_invariance as bi

try:
    import pandas as pd  # noqa: F401
    HAVE_PANDAS = True
except ImportError:  # pragma: no cover
    HAVE_PANDAS = False

REPO_ROOT = Path(__file__).resolve().parent.parent
RUN_SPRINT = REPO_ROOT / "src" / "orchestration" / "run_sprint.py"
T2 = "2026-03-01T00:00:00+09:00"
END = "2026-04-12T00:00:00+09:00"


def _event(cid: str, when: str, kind: str = "page_view", amount: Any = None) -> dict[str, Any]:
    event = {"customer_id": cid, "timestamp": when, "event_type": kind}
    if kind == "purchase":
        event["order_amount"] = amount
    return event


#: 분기마다 같은 이벤트 — N1(비Eligible) · E1(Eligible, 어디서도 처치 안 됨) · E2(Eligible, S1 이 처치).
BASE_EVENTS = [
    _event("N1", "2026-03-02T10:00:00+09:00"),
    _event("N1", "2026-03-02T10:05:00+09:00", "purchase", 12_000),
    _event("E1", "2026-03-05T09:00:00+09:00"),
    _event("E2", "2026-03-06T09:00:00+09:00"),
    _event("N1", "2026-02-28T23:59:00+09:00"),  # 창 밖(t2 이전) — 세지 않는다
]


def write_run_record(root: Path, run_id: str, parent: str | None = None) -> None:
    """``EventSink.close`` 가 남기는 실행 기록과 같은 필드 · 다이제스트(파일 이름 + 바이트, 경로 정렬)로 쓴다."""
    paths = sorted((root / "events").rglob("part-*"))
    digest, rows = hashlib.sha256(), 0
    for path in paths:
        digest.update(path.name.encode())
        digest.update(path.read_bytes())
        rows += sum(1 for line in path.read_text(encoding="utf-8").splitlines() if line.strip())
    runs = root / "runs"
    runs.mkdir(parents=True, exist_ok=True)
    for old in runs.glob("run-*.json"):
        old.unlink()
    (runs / f"run-{run_id}.json").write_text(json.dumps({
        "run_id": run_id, "parent_run_id": parent, "rows": rows, "rejected": 0,
        "files": [p.relative_to(root).as_posix() for p in paths], "sha256": digest.hexdigest(),
        "sources": {"simulator": rows}}), encoding="utf-8")


#: 본선 t2 읽기 근거 — 분기 실행이 본선 history 를 외부 부모로 잇는 경우(실행 루프 ``_branch_proof``).
MAIN_HISTORY = {"status": "ok", "run_id": "SR-main", "verified_run_ids": ["SR-main"], "run_rejections": {"SR-main": 0}}


@unittest.skipUnless(HAVE_PANDAS, "pandas 없음 — 분기 원본 재검증(verify_event_run)이 행 수를 pandas 로 센다")
class BranchInvarianceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.run_dir = self.tmp / "results" / "run"
        self.run_dir.mkdir(parents=True)

    @staticmethod
    def six(**changed: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
        """봉인 대상 분기 전부(S0~S5) — 바꾼 분기만 다른 이벤트."""
        return {branch: changed.get(branch, BASE_EVENTS) for branch in bi.REQUIRED_BRANCHES}

    def raw(self, branch: str) -> Path:
        return self.tmp / "out" / "branches" / branch / "raw"

    def write(self, events_by_branch: dict[str, list[dict[str, Any]]], assignments: dict[str, dict[str, str]],
              roster_t2: list[str] = ("E1", "E2"), with_roster: bool = True,
              stage_status: dict[str, str] | None = None, parent: str | None = None,
              with_history: bool = True) -> None:
        """분기 원본은 KST 날짜별 파티션 · 실행 기록, 결과 파일에는 실행 당시의 분기 읽기 근거를 남긴다."""
        from src.decision.observation_contract import verify_event_run

        raw_roots, files, reads = {}, {}, {}
        for branch, events in events_by_branch.items():
            root = self.raw(branch)
            by_date: dict[str, list[dict[str, Any]]] = {}
            for event in events:
                by_date.setdefault(event["timestamp"][:10], []).append(event)
            for day, rows in by_date.items():
                folder = root / "events" / f"date={day}"
                folder.mkdir(parents=True, exist_ok=True)
                (folder / "part-0000.jsonl").write_text("".join(json.dumps(e) + "\n" for e in rows), encoding="utf-8")
            run_id = f"SR-{branch}"
            write_run_record(root, run_id, parent)
            reads[branch] = {**verify_event_run(root, run_id, history_evidence=MAIN_HISTORY if parent else None),
                             "branch_run_ids": [run_id]}
            raw_roots[branch] = str(root)
            path = self.tmp / "out" / "assignments" / "strategies" / f"{branch}.json"
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps({"assigned_at": T2, "assignments": assignments.get(branch, {})}),
                            encoding="utf-8")
            files[branch] = str(path)
        stages = [{"name": f"strategy_{b}", "status": (stage_status or {}).get(b, "ok")} for b in events_by_branch]
        meta = {"run_id": "SP-test", "timeline": {"t2": T2, "end": END}, "raw_roots": {"main": "x", **raw_roots},
                "assignment_files": {"strategies": files}, "split_roster": {"file": bi.ROSTER_FILE},
                "stages": stages, "event_read_evidence": {"t2": MAIN_HISTORY if with_history else None}}
        (self.run_dir / "run_meta.json").write_text(json.dumps(meta), encoding="utf-8")
        self.write_reads(reads)
        if with_roster:
            with (self.run_dir / bi.ROSTER_FILE).open("w", encoding="utf-8", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=["customer_id", "origin", "role"])
                writer.writeheader()
                writer.writerow({"customer_id": "N1", "origin": "t1", "role": "train"})  # t1 행은 Eligible(t2) 가 아니다
                for cid in roster_t2:
                    writer.writerow({"customer_id": cid, "origin": "t2", "role": "test_candidate"})

    def write_reads(self, reads: dict[str, Any], run_id: str = "SP-test") -> None:
        details = {b: {"strategy_id": b, "event_read_evidence": r} for b, r in reads.items()}
        (self.run_dir / bi.COMPARISON_FILE).write_text(
            json.dumps({"run_id": run_id, "strategy_details": details}), encoding="utf-8")

    def reads(self) -> dict[str, Any]:
        saved = json.loads((self.run_dir / bi.COMPARISON_FILE).read_text(encoding="utf-8"))
        return {b: d["event_read_evidence"] for b, d in saved["strategy_details"].items()}

    def test_same_when_only_treated_customers_change(self) -> None:
        treated_extra = _event("E2", "2026-03-07T12:00:00+09:00", "purchase", 30_000)
        self.write(self.six(S1=[*BASE_EVENTS, treated_extra]), {"S1": {"E2": "T3"}})
        result = bi.branch_invariance(self.run_dir)
        self.assertEqual(("ok", "same", True), (result["status"], result["result"], result["complete"]), result)
        self.assertEqual(list(bi.REQUIRED_BRANCHES), result["branches"])
        self.assertEqual(("SP-test", {}), (result["run_id"], result["missing_branches"]))
        self.assertEqual(1, result["groups"]["non_eligible"]["n_customers"])        # N1
        self.assertEqual(1, result["groups"]["untreated_eligible"]["n_customers"])  # E1 (E2 는 S1 이 처치)
        s0 = result["groups"]["non_eligible"]["by_branch"]["S0"]
        self.assertEqual({"events": 2, "purchases": 1, "revenue_krw": 12_000.0}, {k: s0[k] for k in ("events", "purchases", "revenue_krw")})
        self.assertEqual(1, result["events_by_branch"]["S0"]["n_outside_window"])
        self.assertEqual({"run_id": "SR-S1", "raw_rows": 6, "n_files": 5}, {  # 날짜 5개 = 파티션 5개
            k: result["branch_reads"]["S1"][k] for k in ("run_id", "raw_rows", "n_files")})

    def test_differs_when_an_untreated_customer_changes(self) -> None:
        changed = [*BASE_EVENTS[:1], _event("N1", "2026-03-02T10:05:00+09:00", "purchase", 12_500), *BASE_EVENTS[2:]]
        self.write(self.six(S2=changed), {})
        result = bi.branch_invariance(self.run_dir)
        self.assertEqual("differs", result["result"])
        by_branch = result["groups"]["non_eligible"]["by_branch"]
        self.assertEqual((0, 1), (by_branch["S1"]["n_differing_vs_reference"], by_branch["S2"]["n_differing_vs_reference"]))

    def test_a_missing_event_counts_as_a_difference(self) -> None:
        self.write(self.six(S1=[e for e in BASE_EVENTS if e["customer_id"] != "E1"]), {})
        result = bi.branch_invariance(self.run_dir)
        self.assertEqual("differs", result["result"])
        self.assertEqual(1, result["groups"]["untreated_eligible"]["by_branch"]["S1"]["n_differing_vs_reference"])

    def test_event_type_mix_is_compared_not_only_totals(self) -> None:
        swapped = [_event("E1", "2026-03-05T09:00:00+09:00", "search") if e["customer_id"] == "E1" else e
                   for e in BASE_EVENTS]
        self.write(self.six(S1=swapped), {})
        self.assertEqual("differs", bi.branch_invariance(self.run_dir)["result"])

    def test_not_run_without_the_roster(self) -> None:
        self.write(self.six(), {}, with_roster=False)
        result = bi.branch_invariance(self.run_dir)
        self.assertEqual(("not_run", None), (result["status"], result["result"]))
        self.assertIn("명부", result["reason"])

    def test_missing_reference_branch_is_incomplete(self) -> None:
        events = self.six()
        del events["S0"]
        self.write(events, {})
        result = bi.branch_invariance(self.run_dir)
        self.assertEqual(("incomplete", None, False), (result["status"], result["result"], result["complete"]))
        self.assertEqual(["S0"], list(result["missing_branches"]))

    def test_removing_a_differing_branch_is_incomplete_not_same(self) -> None:
        """PR #327 리뷰 반례 — 비Eligible 고객이 다른 S2 의 원본을 빼면 예전에는 same 이 됐다."""
        changed = [*BASE_EVENTS[:1], _event("N1", "2026-03-02T10:05:00+09:00", "purchase", 12_500), *BASE_EVENTS[2:]]
        self.write(self.six(S2=changed), {})
        self.assertEqual("differs", bi.branch_invariance(self.run_dir)["result"])
        shutil.rmtree(self.tmp / "out" / "branches" / "S2" / "raw")
        result = bi.branch_invariance(self.run_dir)
        self.assertEqual(("incomplete", None), (result["status"], result["result"]))
        self.assertIn("분기 원본이 없다", result["missing_branches"]["S2"])

    def test_removing_one_partition_is_incomplete_not_same(self) -> None:
        """PR #327 2차 리뷰 반례 — 분기 단계 · 원본 경로가 모두 살아 있는 채 S2 에서 비Eligible 고객의 차이가 든 파티션 하나만
        빼면, 여섯 분기 모두 이벤트가 남아 있어 예전에는 ``same`` · ``complete`` 였다(check 0)."""
        extra = _event("N9", "2026-03-10T08:00:00+09:00")  # S2 에만 있는 비Eligible 고객의 이벤트 — 따로 한 파티션
        self.write(self.six(S2=[*BASE_EVENTS, extra]), {})
        self.assertEqual("differs", bi.branch_invariance(self.run_dir)["result"])
        (self.raw("S2") / "events" / "date=2026-03-10" / "part-0000.jsonl").unlink()
        self.assertTrue(any(self.raw("S2").rglob("part-*")))            # S2 에도 이벤트는 남아 있다
        result = bi.branch_invariance(self.run_dir)
        self.assertEqual(("incomplete", None, False), (result["status"], result["result"], result["complete"]))
        self.assertEqual(["S2"], list(result["missing_branches"]))
        self.assertIn("분기 원본 재검증 실패", result["missing_branches"]["S2"])

    def test_rewritten_run_record_still_differs_from_the_recorded_read(self) -> None:
        """파티션을 빼면서 분기 루트의 실행 기록까지 남은 파일에 맞춰 다시 써도, 결과 파일의 실행 당시 근거와 다르다."""
        extra = _event("N9", "2026-03-10T08:00:00+09:00")
        self.write(self.six(S2=[*BASE_EVENTS, extra]), {})
        (self.raw("S2") / "events" / "date=2026-03-10" / "part-0000.jsonl").unlink()
        write_run_record(self.raw("S2"), "SR-S2")
        result = bi.branch_invariance(self.run_dir)
        self.assertEqual("incomplete", result["status"])
        self.assertIn("실행 당시와 파일이 다르다", result["missing_branches"]["S2"])
        self.assertIn("date=2026-03-10/part-0000.jsonl", result["missing_branches"]["S2"])

    def test_branch_without_a_recorded_ok_read_is_incomplete(self) -> None:
        """실행 당시 읽기 근거가 없거나 ok 가 아니면 그 분기는 검증된 적이 없다 — 결과 파일이 없으면 전 분기다."""
        self.write(self.six(), {})
        reads = self.reads()
        reads["S4"] = {"status": "not_run", "run_id": "SR-S4", "reason": "이벤트 원시 읽기 근거 미충족"}
        self.write_reads(reads)
        result = bi.branch_invariance(self.run_dir)
        self.assertEqual(["S4"], list(result["missing_branches"]))
        self.assertIn("status='not_run'", result["missing_branches"]["S4"])
        self.write_reads(self.reads(), run_id="SP-other")
        self.assertEqual(list(bi.REQUIRED_BRANCHES), list(bi.branch_invariance(self.run_dir)["missing_branches"]))
        (self.run_dir / bi.COMPARISON_FILE).unlink()
        result = bi.branch_invariance(self.run_dir)
        self.assertEqual(("incomplete", list(bi.REQUIRED_BRANCHES)), (result["status"], list(result["missing_branches"])))

    def test_branch_chained_to_the_main_history_is_verified(self) -> None:
        """분기 실행이 본선 history 머리를 부모로 잇는 경우 — 실행 루프처럼 본선 t2 읽기 근거로 외부 부모를 해소한다."""
        self.write(self.six(), {}, parent="SR-main")
        result = bi.branch_invariance(self.run_dir)
        self.assertEqual(("ok", "same"), (result["status"], result["result"]), result.get("missing_branches"))
        self.write(self.six(), {}, parent="SR-main", with_history=False)
        result = bi.branch_invariance(self.run_dir)
        self.assertEqual("incomplete", result["status"])
        self.assertIn("외부 부모", result["missing_branches"]["S0"])

    def test_branch_stage_not_ok_or_absent_is_incomplete(self) -> None:
        self.write(self.six(), {}, stage_status={"S3": "failed"})
        result = bi.branch_invariance(self.run_dir)
        self.assertEqual("incomplete", result["status"])
        self.assertIn("strategy_S3 = 'failed'", result["missing_branches"]["S3"])
        events = self.six()
        del events["S5"]                                  # 단계가 미실행이라 배정 목록에서도 빠진 분기
        self.write(events, {})
        result = bi.branch_invariance(self.run_dir)
        self.assertIn("배정 파일 경로가 없다", result["missing_branches"]["S5"])

    def test_output_has_no_customer_ids(self) -> None:
        self.write(self.six(), {"S1": {"E2": "T3"}})
        text = json.dumps(bi.branch_invariance(self.run_dir))
        for cid in ("N1", "E1", "E2"):
            self.assertNotIn(f'"{cid}"', text)

    def test_cli_writes_the_result_and_exit_code(self) -> None:
        self.write(self.six(), {})
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(0, bi.main([str(self.run_dir)]))
        saved = json.loads((self.run_dir / bi.RESULT_FILE).read_text(encoding="utf-8"))
        self.assertEqual("same", saved["result"])
        (self.run_dir / bi.ROSTER_FILE).unlink()
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(2, bi.main([str(self.run_dir)]))


class RunSprintNameTests(unittest.TestCase):
    """실행 루프와 같아야 하는 이름 — 표준 라이브러리만 쓴다."""

    def test_comparison_file_is_a_run_sprint_result_file(self) -> None:
        tree = ast.parse(RUN_SPRINT.read_text(encoding="utf-8"))
        values = [ast.literal_eval(node.value) for node in tree.body if isinstance(node, ast.AnnAssign)
                  and isinstance(node.target, ast.Name) and node.target.id == "RESULT_FILES"]
        self.assertEqual(1, len(values))
        self.assertIn(bi.COMPARISON_FILE.removesuffix(".json"), values[0])

    def test_required_branches_are_run_sprint_strategies(self) -> None:
        """봉인 대상 분기 = 실행 루프가 만드는 분기(``run_sprint.STRATEGIES``). S6 은 분기가 없다(#305)."""
        tree = ast.parse(RUN_SPRINT.read_text(encoding="utf-8"))
        values = [ast.literal_eval(node.value) for node in tree.body if isinstance(node, ast.AnnAssign)
                  and isinstance(node.target, ast.Name) and node.target.id == "STRATEGIES"]
        self.assertEqual([bi.REQUIRED_BRANCHES], values)

    def test_roster_file_name_matches_run_sprint(self) -> None:
        tree = ast.parse(RUN_SPRINT.read_text(encoding="utf-8"))
        values = [node.value.value for node in tree.body if isinstance(node, ast.Assign)
                  and any(isinstance(t, ast.Name) and t.id == "ROSTER_FILE" for t in node.targets)]
        self.assertEqual([bi.ROSTER_FILE], values)


if __name__ == "__main__":
    unittest.main()
