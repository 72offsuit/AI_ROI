from __future__ import annotations

import errno
import gzip
import json
import os
import stat
import sys
import unittest
from datetime import timedelta
from pathlib import Path
from unittest import mock

from src.measurement import sink as sk
from src.simulator import api
from tests.test_simulator_support import (
    SimulatorCase,
    digest_chain_breaks,
    event_digest,
    part_formats,
    reseal_run_records,
    rewrite_gzip_lines,
    root_digest,
)


def _flaky_manifest(failures: int):
    original = sk.EventSink.manifest
    state = {"calls": 0}

    def manifest(sink: sk.EventSink) -> dict[str, object]:
        state["calls"] += 1
        if state["calls"] <= failures:
            raise OSError(28, "No space left on device")
        return original(sink)

    return manifest


class TestPartialWriteFailsClosed(SimulatorCase):
    def reference(self, days: int) -> str:
        root = self.start(customers=25)
        api.advance(days)
        return root_digest(root)

    def test_retry_after_partial_write_is_refused_and_never_duplicates(self) -> None:
        root = self.start(customers=25)
        api.advance(5)
        with mock.patch.object(sk.EventSink, "manifest", _flaky_manifest(1)):
            with self.assertRaises(api.SimulatorError) as caught:
                api.advance(5)
            self.assertIsInstance(caught.exception.__cause__, OSError)
            with self.assertRaises(api.OutputRootError):
                api.advance(5)
        self.assertEqual("broken", sk.verify_lineage(root).verification)
        ids = [r["event_id"] for r in sk.read_events(root)]
        self.assertEqual(len(ids), len(set(ids)), "재시도가 이벤트를 다시 썼다")

    def test_recovery_goes_through_a_new_root_and_keeps_the_full_history(self) -> None:
        expected = self.reference(10)
        root = self.start(customers=25)
        api.advance(5)
        with mock.patch.object(sk.EventSink, "manifest", _flaky_manifest(1)):
            with self.assertRaises(api.SimulatorError):
                api.advance(5)
        last_good = api.save_state()
        with self.assertRaises(api.OutputRootError):
            api.load_state(last_good, root, hidden_root=self.hidden)
        api.load_state(last_good, self.fresh_root("recovered"), hidden_root=self.hidden)
        summary = api.advance(5)
        self.assertEqual(expected, event_digest(api.events(summary.end)))

    def test_sidecar_failure_blocks_the_next_write_without_leaking_hidden_paths(self) -> None:
        self.start(customers=5)
        api.advance(2)
        error = PermissionError(13, "Permission denied", str(self.hidden / "runs" / "x.json"))
        with mock.patch("src.simulator._internal.storage.write_sidecar", side_effect=error):
            with self.assertRaises(api.SimulatorError) as caught:
                api.advance(2)
        self.assertNotIn(str(self.hidden), str(caught.exception))
        self.assertIs(error, caught.exception.__cause__)
        with self.assertRaises(api.OutputRootError):
            api.advance(1)

    def test_failed_state_save_keeps_the_previous_file(self) -> None:
        self.start(customers=5)
        api.advance(2)
        saved = api.save_state()
        before = self.state_bytes(saved)
        error = PermissionError(13, "Permission denied", str(self.hidden / "states"))
        replace = mock.patch("src.simulator._internal.storage.os.replace", side_effect=error)
        with replace, self.assertRaises(api.SimulatorError) as caught:
            api.save_state()
        api.advance(1)
        with replace, self.assertRaises(api.SimulatorError):
            api.save_state()
        self.assertNotIn(str(self.hidden), str(caught.exception))
        self.assertEqual(before, self.state_bytes(saved))
        names = sorted(p.name for p in (self.hidden / "states").iterdir())
        self.assertEqual([f"{saved}.json"], names, "임시 파일이나 새 상태가 남았다")

    def test_window_end_beyond_session_id_range_is_refused(self) -> None:
        root = self.start(customers=2)
        with self.assertRaises(ValueError):
            api.advance(100_000_000)
        self.assertFalse(root.exists())


class TestDirectoryFsync(SimulatorCase):
    def save_with_directory_fsync_error(self, code: int) -> str:
        real = os.fsync

        def fsync(handle: int) -> None:
            if stat.S_ISDIR(os.fstat(handle).st_mode):
                raise OSError(code, os.strerror(code))
            real(handle)

        with mock.patch("src.simulator._internal.storage.os.fsync", fsync):
            return api.save_state()

    def test_unsupported_directory_fsync_is_not_a_failure(self) -> None:
        for code in (errno.EINVAL, errno.ENOTSUP, errno.EBADF):
            with self.subTest(errno=errno.errorcode[code]):
                self.start(seed=code, customers=3)
                saved = self.save_with_directory_fsync_error(code)
                self.assertTrue((self.hidden / "states" / f"{saved}.json").is_file())

    def test_other_directory_fsync_errors_still_fail(self) -> None:
        self.start(customers=3)
        with self.assertRaises(api.SimulatorError) as caught:
            self.save_with_directory_fsync_error(errno.EIO)
        self.assertEqual(errno.EIO, caught.exception.__cause__.errno)


class TestEmptyRootOrigin(SimulatorCase):
    def test_duplicate_histories_resolve_to_the_smallest_verified_run(self) -> None:
        control_root = self.start(seed=3, customers=10)
        api.advance(10)
        control_state = api.save_state()
        api.load_state(control_state, self.fresh_root("control"), hidden_root=self.hidden)
        control = api.advance(5)
        control_events = list(api.events(control.end))

        twin = self.start(seed=3, customers=10)
        twin_run = api.advance(10).run_id
        state = api.save_state()
        self.assertEqual(control_state, state)
        first_run = sk.run_records(control_root)[0]["run_id"]
        api.load_state(state, self.fresh_root("resumed"), hidden_root=self.hidden)
        resumed = api.advance(5)
        self.assertEqual(min(first_run, twin_run), self.sidecar(resumed.run_id)["parent_run_id"])
        self.assertEqual(event_digest(control_events), event_digest(api.events(resumed.end)))
        self.assertEqual(len(control_events), len(list(api.events(resumed.end))))
        self.assertTrue(twin.exists())

    def test_unverifiable_candidates_are_refused(self) -> None:
        roots = []
        for _ in range(2):
            roots.append(self.start(seed=3, customers=6))
            api.advance(4)
        state = api.save_state()
        for root in roots:
            (root / sk.RUNS_DIR_NAME).rename(root / "runs-moved")
        with self.assertRaises(api.OutputRootError):
            api.load_state(state, self.fresh_root("x"), hidden_root=self.hidden)

    def test_state_without_any_lineage_is_refused_unless_it_is_the_start(self) -> None:
        self.start(seed=4, customers=6)
        start_state = api.save_state()
        api.advance(4)
        later_state = api.save_state()
        (self.hidden / "runs").rename(self.hidden / "runs-moved")
        with self.assertRaises(api.OutputRootError):
            api.load_state(later_state, self.fresh_root("x"), hidden_root=self.hidden)
        api.load_state(start_state, self.fresh_root("start"), hidden_root=self.hidden)
        summary = api.advance(2)
        self.assertIsNone(self.sidecar(summary.run_id)["parent_run_id"])


class TestTreatmentIsRecordedInLineage(SimulatorCase):
    def test_d9_branch_with_treatment_keeps_the_digest_chain(self) -> None:
        self.start(customers=8)
        api.advance(3)
        snap = api.snapshot()
        api.restore(snap, output_root=self.fresh_root("branch"))
        api.apply_treatment({"C00000001": "T1", "C00000003": "T0"})
        branch = api.advance(3)
        record = self.sidecar(branch.run_id)
        self.assertEqual([], digest_chain_breaks(self.hidden, branch.run_id))
        self.assertEqual(1, len(record["mutations"]))
        mutation = record["mutations"][0]
        self.assertEqual("apply_treatment", mutation["kind"])
        self.assertEqual({"C00000001": "T1", "C00000003": "T0"}, mutation["assignments"])
        self.assertNotEqual(mutation["before_digest"], mutation["after_digest"])
        api.events(branch.end)

    def test_a_tampered_digest_chain_is_refused(self) -> None:
        self.start(customers=8)
        api.advance(3)
        snap = api.snapshot()
        api.restore(snap, output_root=self.fresh_root("branch"))
        api.apply_treatment({"C00000001": "T1"})
        branch = api.advance(3)
        saved = api.save_state()
        path = self.hidden / "runs" / f"{branch.run_id}.json"
        record = json.loads(path.read_text(encoding="ascii"))
        record["mutations"] = []
        path.write_text(json.dumps(record), encoding="ascii")
        with self.assertRaises(api.OutputRootError):
            api.events(branch.end)
        with self.assertRaises(api.OutputRootError):
            api.load_state(saved, self.fresh_root("x"), hidden_root=self.hidden)

    def test_snapshot_carries_unrecorded_treatment(self) -> None:
        self.start(customers=8)
        api.advance(3)
        api.apply_treatment({"C00000002": "T2"})
        snap = api.snapshot()
        api.restore(snap, output_root=self.fresh_root("branch"))
        branch = api.advance(2)
        self.assertEqual(1, len(self.sidecar(branch.run_id)["mutations"]))
        self.assertEqual([], digest_chain_breaks(self.hidden, branch.run_id))

    def test_saved_treatment_survives_load_into_new_and_same_root(self) -> None:
        root = self.start(customers=8)
        first = api.advance(3)
        api.apply_treatment({"C00000002": "T4"})
        treated = api.save_state()
        derivations = sorted((self.hidden / "derivations").iterdir())
        self.assertEqual(1, len(derivations))

        api.load_state(treated, self.fresh_root("new"), hidden_root=self.hidden)
        moved = api.advance(2)
        record = self.sidecar(moved.run_id)
        self.assertEqual(first.run_id, record["parent_run_id"])
        self.assertEqual(1, len(record["mutations"]))
        self.assertEqual([], digest_chain_breaks(self.hidden, moved.run_id))
        self.assertGreater(len(list(api.events(moved.end))), moved.event_count)

        api.load_state(treated, root, hidden_root=self.hidden)
        same = api.advance(2)
        self.assertEqual(first.run_id, self.sidecar(same.run_id)["parent_run_id"])
        self.assertEqual([], digest_chain_breaks(self.hidden, same.run_id))
        self.assertEqual("ok", sk.verify_lineage(root).verification)


class TestEventsRefusePartialHistory(SimulatorCase):
    def test_missing_partition_raises_instead_of_returning_less(self) -> None:
        root = self.start(customers=10)
        summary = api.advance(5)
        sorted((root / "events").rglob("part-*"))[1].unlink()
        with self.assertRaises(api.OutputRootError):
            list(api.events(summary.end))
        with self.assertRaises(api.OutputRootError):
            api.metrics(summary.start, summary.end)

    def test_rows_removed_from_a_claimed_partition_raise(self) -> None:
        with mock.patch.object(sk, "parquet_available", lambda: False):
            root = self.start(customers=10)
            summary = api.advance(5)
            part = sorted((root / "events").rglob("part-*"))[1]
            rewrite_gzip_lines(part, lambda index: index >= 3)
            with self.assertRaises(api.OutputRootError):
                api.events(summary.end)
            with self.assertRaises(api.OutputRootError):
                api.metrics(summary.start, summary.end)

    def test_truncated_gzip_raises_a_contract_error(self) -> None:
        with mock.patch.object(sk, "parquet_available", lambda: False):
            root = self.start(customers=10)
            summary = api.advance(5)
            part = sorted((root / "events").rglob("part-*"))[1]
            data = part.read_bytes()
            part.write_bytes(data[: len(data) // 2])
            with self.assertRaises(api.OutputRootError):
                list(api.events(summary.end))
            reseal_run_records(root)
            with self.assertRaises(api.OutputRootError):
                list(api.events(summary.end))
            reseal_run_records(root, self.hidden)
            with self.assertRaises(api.OutputRootError) as caught:
                list(api.events(summary.end))
            self.assertIsInstance(caught.exception.__cause__, EOFError)

    def test_row_count_must_match_the_lineage_record(self) -> None:
        self.start(customers=10)
        summary = api.advance(5)
        path = self.hidden / "runs" / f"{summary.run_id}.json"
        record = json.loads(path.read_text(encoding="ascii"))
        record["event_count"] += 1
        path.write_text(json.dumps(record), encoding="ascii")
        with self.assertRaises(api.OutputRootError):
            list(api.events(summary.end))


class TestSidecarIsTheIntegrityBaseline(SimulatorCase):
    def two_runs(self) -> tuple[Path, api.RunSummary, api.RunSummary]:
        with mock.patch.object(sk, "parquet_available", lambda: False):
            root = self.start(seed=3, customers=8)
            first = api.advance(2)
            second = api.advance(4)
        return root, first, second

    def run_record(self, root: Path, run_id: str) -> Path:
        return root / sk.RUNS_DIR_NAME / f"run-{run_id}.json"

    def test_resealed_run_record_after_a_row_swap_is_refused(self) -> None:
        root, first, second = self.two_runs()
        parts = sorted((root / "events").rglob("part-*"))
        sizes = {part: len(gzip.decompress(part.read_bytes()).splitlines()) for part in parts}
        part = max(parts, key=lambda candidate: (sizes[candidate], candidate.as_posix()))
        with gzip.open(part, "rt", encoding="utf-8") as handle:
            lines = [line for line in handle if line.strip()]
        self.assertGreater(len(lines), 1)
        self.assertNotEqual(lines[0], lines[-1])
        lines[-1] = lines[0]
        with gzip.open(part, "wt", encoding="utf-8") as handle:
            handle.writelines(lines)
        reseal_run_records(root)
        self.assertEqual("ok", sk.verify_lineage(root).verification)
        with self.assertRaises(api.OutputRootError):
            api.events(second.end)
        with self.assertRaises(api.OutputRootError):
            api.metrics(first.start, second.end)

    def test_resealed_run_record_claiming_another_runs_files_is_refused(self) -> None:
        root, first, second = self.two_runs()
        claimed = json.loads(self.run_record(root, first.run_id).read_text(encoding="utf-8"))
        path = self.run_record(root, second.run_id)
        forged = json.loads(path.read_text(encoding="utf-8"))
        forged["files"] = claimed["files"]
        path.write_text(json.dumps(forged), encoding="utf-8")
        reseal_run_records(root)
        with self.assertRaises(api.OutputRootError):
            api.events(second.end)

    def test_two_members_claiming_one_file_is_refused_even_when_the_sidecar_agrees(self) -> None:
        root, first, second = self.two_runs()
        claimed = json.loads(self.run_record(root, first.run_id).read_text(encoding="utf-8"))
        path = self.run_record(root, second.run_id)
        forged = json.loads(path.read_text(encoding="utf-8"))
        forged.update(files=claimed["files"], sha256=claimed["sha256"], rows=claimed["rows"])
        path.write_text(json.dumps(forged), encoding="utf-8")
        sidecar = self.hidden / "runs" / f"{second.run_id}.json"
        lineage = json.loads(sidecar.read_text(encoding="ascii"))
        lineage.update(files=claimed["files"], sha256=claimed["sha256"],
                       rows=claimed["rows"], event_count=claimed["rows"])
        sidecar.write_text(json.dumps(lineage), encoding="ascii")
        with self.assertRaisesRegex(api.OutputRootError, "같은 파티션"):
            api.events(second.end)

    def test_sidecar_without_the_baseline_fields_is_refused(self) -> None:
        for field in ("files", "sha256", "rows"):
            with self.subTest(field=field):
                _, _, second = self.two_runs()
                sidecar = self.hidden / "runs" / f"{second.run_id}.json"
                lineage = json.loads(sidecar.read_text(encoding="ascii"))
                del lineage[field]
                sidecar.write_text(json.dumps(lineage), encoding="ascii")
                with self.assertRaises(api.OutputRootError):
                    api.events(second.end)

    def test_advance_refuses_a_root_whose_claimed_bytes_changed(self) -> None:
        root = self.start(customers=8)
        api.advance(3)
        part = sorted((root / "events").rglob("part-*"))[0]
        data = bytearray(part.read_bytes())
        data[len(data) // 2] ^= 0x01
        part.write_bytes(bytes(data))
        self.assertEqual("ok", sk.verify_lineage(root).verification)
        before = sorted(p.as_posix() for p in root.rglob("*"))
        with self.assertRaises(api.OutputRootError):
            api.advance(1)
        self.assertEqual(before, sorted(p.as_posix() for p in root.rglob("*")))


class TestAncestorReadsOnlyClaimedFiles(SimulatorCase):
    def test_foreign_sink_run_in_an_ancestor_root_does_not_leak(self) -> None:
        ancestor = self.start(customers=10)
        api.advance(5)
        snap = api.snapshot()
        api.restore(snap, output_root=self.fresh_root("branch"))
        summary = api.advance(2)
        before = [r["event_id"] for r in api.events(summary.end)]
        foreign = dict(next(iter(api.events(summary.end))))
        foreign["event_id"] = "00000000-0000-4000-8000-000000000000"
        foreign["timestamp"] = "2025-01-01T12:00:00.000+09:00"
        with sk.EventSink(ancestor) as sink:
            sink.write_events([foreign])
        self.assertEqual("ok", sk.verify_lineage(ancestor).verification)
        after = [r["event_id"] for r in api.events(summary.end)]
        self.assertEqual(before, after)
        self.assertEqual(len(before), api.metrics(summary.start - timedelta(days=5), summary.end)["events_total"].value)

    def test_unclaimed_file_inside_the_window_is_neither_read_nor_fatal(self) -> None:
        root = self.start(customers=10)
        summary = api.advance(5)
        before = event_digest(api.events(summary.end))
        part = sorted((root / "events").rglob("part-*"))[0]
        (part.parent / part.name.replace("part-0000", "part-0001")).write_bytes(part.read_bytes())
        self.assertEqual(before, event_digest(api.events(summary.end)))

    def test_recovery_after_a_torn_orphan_matches_the_continuous_run(self) -> None:
        reference = self.start(customers=12)
        api.advance(10)
        expected = root_digest(reference)
        root = self.start(customers=12)
        first = api.advance(5)
        last_good = api.save_state()
        fmt = part_formats(root).pop()
        torn = root / "events" / "date=2025-01-06" / f"part-0000.{fmt}"
        torn.parent.mkdir(parents=True)
        torn.write_bytes(b"\x00" * 4)
        self.assertEqual("broken", sk.verify_lineage(root).verification)
        with self.assertRaises(api.OutputRootError):
            api.advance(5)
        api.load_state(last_good, self.fresh_root("recovered"), hidden_root=self.hidden)
        summary = api.advance(5)
        self.assertEqual(first.run_id, self.sidecar(summary.run_id)["parent_run_id"])
        self.assertEqual(expected, event_digest(api.events(summary.end)))


def _pretend_parquet(root: Path, hidden: Path) -> None:
    renames: dict[str, str] = {}
    for path in sorted((root / "events").rglob("part-*")):
        target = path.with_name(path.name.split(".", 1)[0] + ".parquet")
        path.rename(target)
        renames[path.relative_to(root).as_posix()] = target.relative_to(root).as_posix()
    for record_path in sorted((root / sk.RUNS_DIR_NAME).glob("run-*.json")) + [root / "manifest.json"]:
        record = json.loads(record_path.read_text(encoding="utf-8"))
        record["format"] = "parquet"
        record["files"] = [renames.get(name, name) for name in record["files"]]
        record_path.write_text(json.dumps(record), encoding="utf-8")
    reseal_run_records(root, hidden)
    for sidecar in sorted((hidden / "runs").glob("*.json")):
        record = json.loads(sidecar.read_text(encoding="ascii"))
        if record["output_root"] == str(root.resolve()):
            record["sink_format"] = "parquet"
            sidecar.write_text(json.dumps(record), encoding="ascii")


class TestRootFormatIsLocked(SimulatorCase):
    def test_first_write_fixes_the_format_for_later_runtimes(self) -> None:
        with mock.patch.object(sk, "parquet_available", lambda: False):
            root = self.start(customers=6)
            api.advance(2)
        self.assertEqual({"jsonl.gz"}, part_formats(root))
        with mock.patch.object(sk, "parquet_available", lambda: True):
            api.advance(2)
            state = api.save_state()
            api.load_state(state, root, hidden_root=self.hidden)
            api.advance(1)
        self.assertEqual({"jsonl.gz"}, part_formats(root))
        self.assertEqual("ok", sk.verify_lineage(root).verification)

    def test_runtime_without_the_format_is_refused_before_writing(self) -> None:
        with mock.patch.object(sk, "parquet_available", lambda: False):
            root = self.start(customers=6)
            summary = api.advance(2)
            state = api.save_state()
            _pretend_parquet(root, self.hidden)
            before = sorted(p.as_posix() for p in root.rglob("*"))
            with self.assertRaisesRegex(api.SinkFormatError, "이어 쓸 출력 루트"):
                api.advance(1)
            with self.assertRaises(api.SinkFormatError):
                api.events(summary.end)
            with self.assertRaises(api.SinkFormatError):
                api.metrics(summary.start, summary.end)
            with self.assertRaises(api.SinkFormatError):
                api.load_state(state, root, hidden_root=self.hidden)
            self.assertEqual(before, sorted(p.as_posix() for p in root.rglob("*")))

    def test_mixed_formats_in_one_root_are_refused(self) -> None:
        with mock.patch.object(sk, "parquet_available", lambda: False):
            root = self.start(customers=6)
            api.advance(2)
        part = sorted((root / "events").rglob("part-*"))[0]
        part.rename(part.with_name("part-0000.parquet"))
        with self.assertRaises(api.SimulatorError):
            api.advance(1)

    def test_unreadable_ancestor_format_is_refused_before_a_new_root_is_used(self) -> None:
        with mock.patch.object(sk, "parquet_available", lambda: False):
            root = self.start(customers=6)
            api.advance(2)
            snap = api.snapshot()
            state = api.save_state()
            _pretend_parquet(root, self.hidden)
            branch, resumed = self.fresh_root("branch"), self.fresh_root("resumed")
            with self.assertRaisesRegex(api.SinkFormatError, "계보") as caught:
                api.restore(snap, output_root=branch)
            self.assertNotIn(str(self.hidden), str(caught.exception))
            with self.assertRaisesRegex(api.SinkFormatError, "계보"):
                api.load_state(state, resumed, hidden_root=self.hidden)
            self.assertFalse(branch.exists())
            self.assertFalse(resumed.exists())
            with self.assertRaises(api.SinkFormatError):
                api.advance(1)

    @unittest.skipUnless(sk.parquet_available(), "실제 parquet 루트를 만들려면 pyarrow 가 필요하다")
    def test_real_parquet_root_without_pyarrow_raises_contract_errors(self) -> None:
        root = self.start(customers=6)
        summary = api.advance(2)
        self.assertEqual({"parquet"}, part_formats(root))
        snap = api.snapshot()
        state = api.save_state()
        hidden_pyarrow = {"pyarrow": None, "pyarrow.parquet": None}
        with mock.patch.dict(sys.modules, hidden_pyarrow):
            with self.assertRaises(api.SinkFormatError):
                api.advance(1)
            with self.assertRaises(api.SinkFormatError):
                list(api.events(summary.end))
            branch, resumed = self.fresh_root("branch"), self.fresh_root("resumed")
            with self.assertRaises(api.SinkFormatError):
                api.restore(snap, output_root=branch)
            with self.assertRaises(api.SinkFormatError):
                api.load_state(state, resumed, hidden_root=self.hidden)
            self.assertFalse(branch.exists() or resumed.exists())
        self.assertEqual({"parquet"}, part_formats(root))


if __name__ == "__main__":
    unittest.main()
