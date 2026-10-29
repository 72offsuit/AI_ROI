"""#167 — 참 효과 기록 형식 · 창 안 재배정 표시 · 사후 채점과의 키 정합 · 교환 묶음 source_commit.

- 효과 창 안에서 다시 배정하면 새 참 효과 행의 `supersedes` 가 끊긴 앞 배정(파일 · 시각 · 처치)을 가리킨다. 창이
  끝난 뒤나 앞 배정이 `T0` 이면 `null` 이다.
- 사후 채점(`src/diagnostics/report.py`)이 시뮬레이터가 실제로 쓴 참 효과 파일을 그대로 읽고, 끊긴 행을 world ·
  스냅샷 분기가 섞여도 그 파일에서만 센다(#167 리뷰).
- 교환 묶음 매니페스트의 `source_commit` 은 `src/simulator` 의 마지막 커밋(`simulator_commit` 규칙) 또는 사유가
  붙은 `null` 이다.
"""

from __future__ import annotations

import json
import subprocess
from datetime import datetime
from unittest import mock

from src.diagnostics import report
from src.simulator import api
from src.simulator.api import _REPO_ROOT
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
                {"file": self.files[0].stem, "at": self.first_at, "treatment_id": "T3", "observed_days": 10},
                second[cid]["supersedes"], cid,
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


def _cut_counts(hidden) -> dict[str, int]:
    files = sorted((hidden / "ground_truth").glob("po-*.jsonl"))
    blocks = report._with_superseded([{} for _ in files], files)
    return {path.stem: block["superseded_rows"] for path, block in zip(files, blocks)}


class TestSupersededRowsStayInTheirOwnFile(SimulatorCase):
    """리뷰 재현: 같은 숨김 영역에 다른 world · 다른 분기의 참 효과 파일이 섞여도 끊긴 행은 끊긴 파일에서만 센다."""

    def test_another_world_with_the_same_customers_and_times_is_not_counted(self) -> None:
        self.start(seed=1, customers=20, profile="small")
        api.advance(30)
        api.apply_treatment({f"C{i:08d}": "T3" for i in range(1, 6)})
        api.advance(42)
        quiet = {p.stem for p in (self.hidden / "ground_truth").glob("po-*.jsonl")}
        api.init(2, 20, "small", self.fresh_root("second"), hidden_root=self.hidden)
        api.advance(30)
        api.apply_treatment({f"C{i:08d}": "T3" for i in range(1, 6)})
        api.advance(10)
        api.apply_treatment({f"C{i:08d}": "T1" for i in range(1, 6)})
        counts = _cut_counts(self.hidden)
        self.assertEqual(3, len(counts))
        self.assertEqual({0}, {counts[stem] for stem in quiet})  # seed 1 은 재배정이 없다
        self.assertEqual([0, 5], sorted(n for stem, n in counts.items() if stem not in quiet))

    def test_a_sibling_branch_from_the_same_snapshot_is_not_counted(self) -> None:
        self.start(seed=3, customers=20, profile="small")
        api.advance(30)
        snap = api.snapshot()
        plan = {f"C{i:08d}": "T3" for i in range(1, 6)}
        api.restore(snap, output_root=self.fresh_root("branch1"))
        api.apply_treatment(plan)
        api.advance(42)
        first = {p.stem for p in (self.hidden / "ground_truth").glob("po-*.jsonl")}
        api.restore(snap, output_root=self.fresh_root("branch2"))
        api.apply_treatment({cid: "T2" for cid in plan})
        cut_stem = ({p.stem for p in (self.hidden / "ground_truth").glob("po-*.jsonl")} - first).pop()
        api.advance(10)
        api.apply_treatment({cid: "T1" for cid in plan})
        counts = _cut_counts(self.hidden)
        self.assertEqual(3, len(counts))
        self.assertEqual({0}, {counts[stem] for stem in first})  # 분기 1 은 끊기지 않았다
        self.assertEqual(5, counts[cut_stem])


class TestExchangeSourceCommit(SimulatorCase):
    def manifest(self) -> dict[str, object]:
        self.start(seed=4, customers=10, profile="small")
        api.advance(20)
        until = datetime.fromisoformat(clock.timestamp(runtime.active.world["now_ms"]))
        path = api.exchange_bundle(until)["path"]
        self.assertTrue(str(path).endswith("simulator_exchange"))
        return json.loads((runtime.active.output_root.parent / "simulator_exchange" / "manifest.json")
                          .read_text(encoding="utf-8"))

    def test_source_commit_is_the_last_commit_that_touched_the_simulator(self) -> None:
        expected = subprocess.run(
            ["git", "log", "-1", "--format=%H", "--", "src/simulator"], cwd=_REPO_ROOT,
            capture_output=True, text=True, check=False,
        ).stdout.strip()
        if not expected:
            self.skipTest("BLOCKED: git 저장소 밖에서 실행 — 커밋 대조 불가(null 경로는 아래 테스트가 본다)")
        manifest = self.manifest()
        self.assertEqual(runtime.active.world["simulator_version"], manifest["simulator_version"])
        self.assertEqual(expected, manifest["source_commit"])
        self.assertNotIn("null_reason", manifest)

    def test_without_git_the_commit_is_null_with_a_reason(self) -> None:
        with mock.patch.object(api._subprocess, "run", side_effect=OSError("git 없음")):
            manifest = self.manifest()
        self.assertIsNone(manifest["source_commit"])
        self.assertEqual({"source_commit": "PRECONDITION_MISSING"}, manifest["null_reason"])


class TestRoundDiv(SimulatorCase):
    def test_half_rounds_up_for_both_signs(self) -> None:
        cases = {(5, 2): 3, (-5, 2): -2, (7, 3): 2, (-7, 3): -2, (-1, 3): 0, (-3, 2): -1, (4, 2): 2, (-4, 2): -2}
        for (a, b), expected in cases.items():
            self.assertEqual(expected, guardrails._round_div(a, b), (a, b))

    def test_bp_is_unchanged_by_the_shared_helper(self) -> None:
        for a in range(-50, 51):
            for b in range(1, 12):
                self.assertEqual((a * 10_000 + b // 2) // b, guardrails._bp(a, b), (a, b))
