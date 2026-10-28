"""#167 — 참 효과 기록 형식 · 창 안 재배정 표시 · 사후 채점과의 키 정합 · 교환 묶음 source_commit.

- 효과 창 안에서 다시 배정하면 새 참 효과 행의 `supersedes` 가 끊긴 앞 배정을 가리킨다. 창이 끝난 뒤나
  앞 배정이 `T0` 이면 `null` 이다.
- 사후 채점(`src/diagnostics/report.py`)이 시뮬레이터가 실제로 쓴 참 효과 파일을 그대로 읽는다.
- 교환 묶음 매니페스트의 `source_commit` 은 커밋(40자 16진) 또는 사유가 붙은 `null` 이다.
"""

from __future__ import annotations

import json
import re
from datetime import datetime

from src.diagnostics import report
from src.simulator import api
from src.simulator._internal import clock, guardrails, runtime
from tests.test_simulator_support import SimulatorCase


def _rows(path) -> list[dict[str, object]]:
    return [json.loads(line) for line in path.read_text(encoding="ascii").splitlines()]


class TestSupersedes(SimulatorCase):
    def setUp(self) -> None:
        super().setUp()
        self.start(seed=12, customers=20, profile="small")
        api.advance(30)
        api.apply_treatment({f"C{i:08d}": "T3" for i in range(1, 11)} | {"C00000011": "T0"})
        self.first_at = clock.timestamp(runtime.active.world["now_ms"])
        api.advance(10)
        api.apply_treatment({f"C{i:08d}": "T1" for i in range(1, 6)} | {"C00000011": "T2", "C00000015": "T4"})
        api.advance(42)
        api.apply_treatment({f"C{i:08d}": "T2" for i in range(1, 3)})
        self.files = sorted((self.hidden / "ground_truth").glob("po-*.jsonl"))

    def test_reassignment_inside_the_window_points_at_the_cut_assignment(self) -> None:
        self.assertEqual(3, len(self.files))
        second = {r["customer_id"]: r for r in _rows(self.files[1])}
        for cid in (f"C{i:08d}" for i in range(1, 6)):
            self.assertEqual(
                {"at": self.first_at, "treatment_id": "T3", "observed_days": 10}, second[cid]["supersedes"], cid
            )
        self.assertIsNone(second["C00000011"]["supersedes"])  # 앞 배정이 T0 — 끊긴 효과가 없다
        self.assertIsNone(second["C00000015"]["supersedes"])  # 처음 배정
        self.assertTrue(all(r["supersedes"] is None for r in _rows(self.files[0])))
        # advance(42) 뒤 재배정은 창(끝 배타) 밖이다
        self.assertTrue(all(r["supersedes"] is None for r in _rows(self.files[2])))

    def test_diagnostics_reads_the_real_rows_and_counts_cut_ones(self) -> None:
        for path in self.files:
            self.assertTrue(report.PO_NAME.match(path.stem).group("world").startswith("W-"), path.name)
            for row in _rows(path):
                parsed = report.parse_truth_row(row)
                self.assertEqual(row["assigned"], parsed["assigned"])
                self.assertEqual("outcomes", parsed["tau_source"])
                self.assertEqual([], parsed["tau_mismatch"])
        blocks = report._with_superseded([{} for _ in self.files], self.files)
        self.assertEqual([5, 0, 0], [b["superseded_rows"] for b in blocks])


class TestExchangeSourceCommit(SimulatorCase):
    def test_source_commit_is_a_commit_or_a_null_with_reason(self) -> None:
        self.start(seed=4, customers=10, profile="small")
        api.advance(20)
        until = datetime.fromisoformat(clock.timestamp(runtime.active.world["now_ms"]))
        path = api.exchange_bundle(until)["path"]
        manifest = json.loads((runtime.active.output_root.parent / "simulator_exchange" / "manifest.json")
                              .read_text(encoding="utf-8"))
        self.assertTrue(str(path).endswith("simulator_exchange"))
        self.assertEqual(runtime.active.world["simulator_version"], manifest["simulator_version"])
        commit = manifest["source_commit"]
        if commit is None:
            self.assertEqual({"source_commit": "PRECONDITION_MISSING"}, manifest["null_reason"])
        else:
            self.assertRegex(commit, re.compile(r"^[0-9a-f]{40}$"))
            self.assertNotIn("null_reason", manifest)


class TestRoundDiv(SimulatorCase):
    def test_half_rounds_up_for_both_signs(self) -> None:
        cases = {(5, 2): 3, (-5, 2): -2, (7, 3): 2, (-7, 3): -2, (-1, 3): 0, (-3, 2): -1, (4, 2): 2, (-4, 2): -2}
        for (a, b), expected in cases.items():
            self.assertEqual(expected, guardrails._round_div(a, b), (a, b))

    def test_bp_is_unchanged_by_the_shared_helper(self) -> None:
        for a in range(-50, 51):
            for b in range(1, 12):
                self.assertEqual((a * 10_000 + b // 2) // b, guardrails._bp(a, b), (a, b))
