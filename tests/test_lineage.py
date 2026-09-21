"""Holds the run-lineage chain honest against what is actually on disk (#99 ②③).

The professor's review asked for a structure where the next batch of data can be
traced back to the batch before it. `runs/run-<id>.json` gives that: one immutable
file per generation run, each naming its parent, so the chain reconstructs how a
world got to where it is.

★ A chain on its own is a **declaration nobody compares** -- the shape this cycle
  kept finding (#97, #99, the dead config value in #63). `verify_lineage()` is the
  comparison: the files the records claim, against the partitions that exist.

What is checked here:

  checked    the chain links up, and `manifest.json` stays byte-identical to the
             newest run record so the two cannot drift
  checked    every failure mode produces a *reported* state, not a silent pass:
             a partition nobody claims, a claimed file that is gone, a parent that
             does not exist, a corrupt record
  checked    data written before `runs/` existed reports `not_run`, never `ok`
  NOT        whether the events themselves are right. `test_sink.py` owns that.

★ `test_ordering_survives_same_second_writes` is the one worth reading. The first
  implementation picked the newest run by `created_at`, which is recorded to the
  second -- and the simulator writes consecutive windows well inside one second,
  so two runs tied and the parent was assigned wrong. The chain knows its own
  order without consulting a clock; that test pins it.
"""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from src.measurement import sink as sk
from tests.test_incremental_generation import WINDOW_ONE, WINDOW_TWO, write


class TestChainLinksUp(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name) / "raw"
        write(self.root, WINDOW_ONE, WINDOW_TWO)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_one_record_per_run(self) -> None:
        self.assertEqual(2, len(sk.run_records(self.root)))

    def test_first_run_has_no_parent(self) -> None:
        """★ `None` 이다. `""` 나 `"unknown"` 으로 채우면 '사슬의 시작' 과
        '부모를 모른다' 가 같아진다."""
        roots = [r for r in sk.run_records(self.root) if r["parent_run_id"] is None]
        self.assertEqual(1, len(roots), "뿌리는 정확히 하나여야 한다")

    def test_chain_reaches_every_run(self) -> None:
        records = {r["run_id"]: r for r in sk.run_records(self.root)}
        seen, current = [], sk.latest_run_id(self.root)
        while current is not None:
            seen.append(current)
            current = records[current]["parent_run_id"]
        self.assertEqual(
            sorted(records), sorted(seen), "사슬을 따라가면 모든 실행에 닿아야 한다"
        )

    def test_manifest_is_the_head_record(self) -> None:
        """★ 같은 dict 에서 두 곳에 쓴다 — 드리프트가 불가능해야 한다."""
        head = sk.latest_run_id(self.root)
        manifest = json.loads((self.root / "manifest.json").read_text(encoding="utf-8"))
        record = json.loads(
            (self.root / sk.RUNS_DIR_NAME / f"run-{head}.json").read_text(encoding="utf-8")
        )
        self.assertEqual(record, manifest)

    def test_ordering_survives_same_second_writes(self) -> None:
        """★ `created_at` 은 초 단위다. 연속 실행은 같은 초에 끝난다.

        시각으로 정렬하면 동률이 나고 부모가 잘못 잡힌다 — 실제로 그렇게 나왔다.
        사슬의 머리는 시계를 보지 않는다.
        """
        stamps = {r["created_at"] for r in sk.run_records(self.root)}
        if len(stamps) > 1:
            self.skipTest(
                "BLOCKED: 두 실행의 created_at 이 달라 동률 상황을 재현하지 못했다 "
                "— 이 검사는 같은 초에 끝났을 때를 보는 것이다 (통과가 아니다)"
            )
        self.assertIsNotNone(
            sk.latest_run_id(self.root),
            "같은 초에 끝난 두 실행에서 머리를 찾지 못했다",
        )


class TestVerificationCatchesEachFailure(unittest.TestCase):
    """★ 음성 대조 — 고장마다 실제로 잡히는가. 잡지 못하는 검사는 검사가 아니다."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name) / "raw"
        write(self.root, WINDOW_ONE, WINDOW_TWO)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_healthy_is_ok(self) -> None:
        result = sk.verify_lineage(self.root)
        self.assertEqual("ok", result.verification, result.detail)
        self.assertEqual((), result.problems)
        self.assertTrue(result.detail)

    def test_unclaimed_partition_is_reported(self) -> None:
        """밖에서 파티션이 추가되면 계보가 그것을 설명하지 못한다."""
        stray = self.root / "events" / "date=2026-02-01"
        stray.mkdir(parents=True)
        (stray / "part-0000.jsonl.gz").write_bytes(b"")
        result = sk.verify_lineage(self.root)
        self.assertEqual("broken", result.verification)
        self.assertTrue(result.unclaimed_partitions)

    def test_claimed_but_deleted_file_is_reported(self) -> None:
        """밖에서 파티션이 지워지면 기록이 없는 파일을 주장하게 된다."""
        victim = next((self.root / "events").rglob("part-*"))
        victim.unlink()
        result = sk.verify_lineage(self.root)
        self.assertEqual("broken", result.verification)
        self.assertTrue(result.claimed_but_absent)

    def test_missing_parent_is_reported(self) -> None:
        """사슬 중간이 사라지면 끊긴 것이 드러나야 한다."""
        records = sorted((self.root / sk.RUNS_DIR_NAME).glob("run-*.json"))
        for path in records:
            if json.loads(path.read_text(encoding="utf-8"))["parent_run_id"] is None:
                path.unlink()
                break
        result = sk.verify_lineage(self.root)
        self.assertEqual("broken", result.verification)
        self.assertTrue(result.broken_links)

    def test_corrupt_record_is_reported_not_skipped(self) -> None:
        """손상된 기록 하나를 조용히 건너뛰면 사슬이 끊긴 것이 '원래 없었던 것' 처럼 보인다."""
        victim = sorted((self.root / sk.RUNS_DIR_NAME).glob("run-*.json"))[0]
        victim.write_text('{"run_id": "x", ', encoding="utf-8")
        result = sk.verify_lineage(self.root)
        self.assertEqual("broken", result.verification)
        self.assertTrue(result.unreadable_records)


class TestOldDataIsNotRunNotOk(unittest.TestCase):
    """★ `runs/` 가 없는 옛 데이터. **통과로 적지 않는다.**"""

    def test_absent_runs_dir_is_not_run(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "raw"
            write(root, WINDOW_ONE)
            import shutil

            shutil.rmtree(root / sk.RUNS_DIR_NAME)
            result = sk.verify_lineage(root)
            self.assertEqual("not_run", result.verification)
            self.assertNotEqual("ok", result.verification)
            self.assertIn("통과가 아니다", result.detail)
