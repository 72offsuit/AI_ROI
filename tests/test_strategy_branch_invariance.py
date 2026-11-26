"""분기 간 대조 — DR-234 P3 반증 조건 (#170 · DR-170-gate2-lock G5).

가짜 결과 폴더(run_meta · 명부 · 분기별 배정 파일 · 분기 원본 이벤트)로 대조 규칙을 확인한다. 표준 라이브러리만 쓴다.
"""

from __future__ import annotations

import ast
import contextlib
import csv
import io
import json
import shutil
import tempfile
import unittest
from pathlib import Path
from typing import Any

from src.orchestration import branch_invariance as bi

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


class BranchInvarianceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.run_dir = self.tmp / "results" / "run"
        self.run_dir.mkdir(parents=True)

    def write(self, events_by_branch: dict[str, list[dict[str, Any]]], assignments: dict[str, dict[str, str]],
              roster_t2: list[str] = ("E1", "E2"), with_roster: bool = True) -> None:
        raw_roots, files = {}, {}
        for branch, events in events_by_branch.items():
            root = self.tmp / "out" / "branches" / branch / "raw"
            (root / "events").mkdir(parents=True)
            (root / "events" / "part-00000.jsonl").write_text(
                "".join(json.dumps(e) + "\n" for e in events), encoding="utf-8")
            raw_roots[branch] = str(root)
            path = self.tmp / "out" / "assignments" / "strategies" / f"{branch}.json"
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps({"assigned_at": T2, "assignments": assignments.get(branch, {})}),
                            encoding="utf-8")
            files[branch] = str(path)
        meta = {"timeline": {"t2": T2, "end": END}, "raw_roots": {"main": "x", **raw_roots},
                "assignment_files": {"strategies": files}, "split_roster": {"file": bi.ROSTER_FILE}}
        (self.run_dir / "run_meta.json").write_text(json.dumps(meta), encoding="utf-8")
        if with_roster:
            with (self.run_dir / bi.ROSTER_FILE).open("w", encoding="utf-8", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=["customer_id", "origin", "role"])
                writer.writeheader()
                writer.writerow({"customer_id": "N1", "origin": "t1", "role": "train"})  # t1 행은 Eligible(t2) 가 아니다
                for cid in roster_t2:
                    writer.writerow({"customer_id": cid, "origin": "t2", "role": "test_candidate"})

    def test_same_when_only_treated_customers_change(self) -> None:
        treated_extra = _event("E2", "2026-03-07T12:00:00+09:00", "purchase", 30_000)
        self.write({"S0": BASE_EVENTS, "S1": [*BASE_EVENTS, treated_extra], "S2": BASE_EVENTS},
                   {"S1": {"E2": "T3"}})
        result = bi.branch_invariance(self.run_dir)
        self.assertEqual(("ok", "same"), (result["status"], result["result"]), result)
        self.assertEqual(["S0", "S1", "S2"], result["branches"])
        self.assertEqual(1, result["groups"]["non_eligible"]["n_customers"])        # N1
        self.assertEqual(1, result["groups"]["untreated_eligible"]["n_customers"])  # E1 (E2 는 S1 이 처치)
        s0 = result["groups"]["non_eligible"]["by_branch"]["S0"]
        self.assertEqual({"events": 2, "purchases": 1, "revenue_krw": 12_000.0}, {k: s0[k] for k in ("events", "purchases", "revenue_krw")})
        self.assertEqual(1, result["events_by_branch"]["S0"]["n_outside_window"])

    def test_differs_when_an_untreated_customer_changes(self) -> None:
        changed = [*BASE_EVENTS[:1], _event("N1", "2026-03-02T10:05:00+09:00", "purchase", 12_500), *BASE_EVENTS[2:]]
        self.write({"S0": BASE_EVENTS, "S1": BASE_EVENTS, "S2": changed}, {})
        result = bi.branch_invariance(self.run_dir)
        self.assertEqual("differs", result["result"])
        by_branch = result["groups"]["non_eligible"]["by_branch"]
        self.assertEqual((0, 1), (by_branch["S1"]["n_differing_vs_reference"], by_branch["S2"]["n_differing_vs_reference"]))

    def test_a_missing_event_counts_as_a_difference(self) -> None:
        self.write({"S0": BASE_EVENTS, "S1": [e for e in BASE_EVENTS if e["customer_id"] != "E1"]}, {})
        result = bi.branch_invariance(self.run_dir)
        self.assertEqual("differs", result["result"])
        self.assertEqual(1, result["groups"]["untreated_eligible"]["by_branch"]["S1"]["n_differing_vs_reference"])

    def test_event_type_mix_is_compared_not_only_totals(self) -> None:
        swapped = [_event("E1", "2026-03-05T09:00:00+09:00", "search") if e["customer_id"] == "E1" else e
                   for e in BASE_EVENTS]
        self.write({"S0": BASE_EVENTS, "S1": swapped}, {})
        self.assertEqual("differs", bi.branch_invariance(self.run_dir)["result"])

    def test_not_run_without_the_roster(self) -> None:
        self.write({"S0": BASE_EVENTS, "S1": BASE_EVENTS}, {}, with_roster=False)
        result = bi.branch_invariance(self.run_dir)
        self.assertEqual(("not_run", None), (result["status"], result["result"]))
        self.assertIn("명부", result["reason"])

    def test_not_run_without_the_reference_branch(self) -> None:
        self.write({"S1": BASE_EVENTS, "S2": BASE_EVENTS}, {})
        result = bi.branch_invariance(self.run_dir)
        self.assertEqual("not_run", result["status"])
        self.assertIn("S0", result["reason"])

    def test_output_has_no_customer_ids(self) -> None:
        self.write({"S0": BASE_EVENTS, "S1": BASE_EVENTS}, {"S1": {"E2": "T3"}})
        text = json.dumps(bi.branch_invariance(self.run_dir))
        for cid in ("N1", "E1", "E2"):
            self.assertNotIn(f'"{cid}"', text)

    def test_cli_writes_the_result_and_exit_code(self) -> None:
        self.write({"S0": BASE_EVENTS, "S1": BASE_EVENTS}, {})
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(0, bi.main([str(self.run_dir)]))
        saved = json.loads((self.run_dir / bi.RESULT_FILE).read_text(encoding="utf-8"))
        self.assertEqual("same", saved["result"])
        (self.run_dir / bi.ROSTER_FILE).unlink()
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(2, bi.main([str(self.run_dir)]))

    def test_roster_file_name_matches_run_sprint(self) -> None:
        tree = ast.parse(RUN_SPRINT.read_text(encoding="utf-8"))
        values = [node.value.value for node in tree.body if isinstance(node, ast.Assign)
                  and any(isinstance(t, ast.Name) and t.id == "ROSTER_FILE" for t in node.targets)]
        self.assertEqual([bi.ROSTER_FILE], values)


if __name__ == "__main__":
    unittest.main()
