"""#179: 필수 관측 검증은 선택적 모델·로더와 독립이다."""
from __future__ import annotations

import ast
import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import unittest
from datetime import timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest import mock
from uuid import UUID

ROOT = Path(__file__).resolve().parents[1]
HAVE_DATA = all(importlib.util.find_spec(name) for name in ("pandas", "numpy", "yaml"))
NEEDS_DATA = "BLOCKED: pandas/numpy/PyYAML 미설치 — DataFrame 읽기 연결 미실행"


def _isolated_probe(mode):
    """별도 프로세스에서 모델 또는 필수 패키지를 import부터 차단한다.

    공개 계약 형식의 EventSink 입력과 API 대역만 쓴다. 실제 시뮬레이터 시험이 아니다.
    """
    import contextlib
    import gzip
    import importlib.abc
    import io
    import types
    from datetime import datetime, timezone

    sys.path.insert(0, str(ROOT))
    optional = ("src.decision.data", "src.decision.features", "src.decision.churn", "src.decision.clv",
                "src.decision.uplift", "src.decision.segments", "src.decision.strategies", "src.decision.roi",
                "src.decision.ab_test", "src.decision.optimize", "sklearn", "torch", "shap")
    forbidden = ("src.simulator", "src.diagnostics")
    blocked = optional + forbidden + (("pandas", "numpy", "pyarrow") if mode == "no_packages" else ())
    attempts = []

    def matches(name, names):
        return any(name == prefix or name.startswith(prefix + ".") for prefix in names)

    class BlockImports(importlib.abc.MetaPathFinder):
        def find_spec(self, fullname, path=None, target=None):
            if matches(fullname, blocked):
                attempts.append(fullname)
                raise ModuleNotFoundError("시험에서 차단한 모듈: " + fullname, name=fullname)

    assert not any(matches(name, blocked) for name in sys.modules)
    sys.meta_path.insert(0, BlockImports())
    path = ROOT / "src/orchestration/run_sprint.py"
    tree = ast.parse(path.read_text())
    removed = [node for node in tree.body if isinstance(node, ast.ImportFrom) and node.module == "src.simulator"]
    assert len(removed) == 1, "공개 API import 위치 변경 — 경계 하네스 재검토 필요"
    tree.body = [node for node in tree.body if node not in removed]
    rs = types.ModuleType("_issue179_isolated_runner")
    rs.__file__ = str(path)
    sys.modules[rs.__name__] = rs
    exec(compile(tree, str(path), "exec"), rs.__dict__)
    on_import = list(attempts)

    from src.measurement.sink import EventSink, run_records

    kst = timezone(timedelta(hours=9))
    t0 = datetime(2025, 3, 1, tzinfo=kst)
    when = t0 - timedelta(days=5)
    row = {"event_id": str(UUID(int=1, version=4)), "customer_id": "C00000001",
           "event_type": "session_start", "timestamp": when.isoformat(), "page_type": "home",
           "session_id": f"S-C00000001-{int(when.timestamp()*1000):013d}",
           "service_version": "fixture", "customer_version": "fixture",
           "simulator_version": "fixture", "random_seed": 7}

    def write(root, run_id, rows, parent=None):
        with EventSink(root, fmt="jsonl.gz", run_id=run_id, parent_run_id=parent) as sink:
            assert sink.write_events(rows).rejected == 0

    def stage_call(label, fn):
        log, returned = rs.StageLog(), []
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            with log.stage(label):
                returned.append(fn())
        entry = log.stages[-1]
        return {"status": entry["status"], "reason": entry["reason"], "returned": len(returned)}

    out = {"attempts_on_import": on_import}
    with tempfile.TemporaryDirectory() as temp:
        base = Path(temp)
        empty, main = base / "empty", base / "main"
        write(empty, "empty", [])
        write(main, "a0", [row])
        rows = [row, {**row, "event_id": str(UUID(int=2, version=4))}]
        write(main, "a", rows[1:], parent="a0")
        if mode == "no_packages":
            rs.sim = SimpleNamespace(events=lambda until: iter(()))
            out["empty_verify"] = rs.verify_event_run(empty, "empty")["status"]
            for label, root, run_id in (("empty_read", empty, "empty"), ("filled_read", main, "a")):
                out[label] = stage_call(label, lambda: rs.EventReader().read(root, t0, run_id=run_id))
            out["observation"] = stage_call("observation", lambda: rs.outcome_observation_status(t0, 42, {}))
        else:
            api = SimpleNamespace(events=mock.Mock(return_value=iter(rows)))
            rs.sim = api
            reader = rs.EventReader()
            history = reader.read(main, t0, run_id="a")
            out["main"] = {"rows": len(history), "status": history.attrs["run_read_evidence"]["status"],
                           "source": reader.source}
            extra = {**row, "event_id": str(UUID(int=3, version=4))}
            branch = base / "branch"
            write(branch, "b", [extra], parent="a")
            api.events.return_value = iter(rows + [extra])
            frame = reader.read(branch, t0, history=history, run_id="b")
            out["branch"] = {"rows": len(frame), "status": frame.attrs["run_read_evidence"]["status"],
                             "parent": frame.attrs["run_read_evidence"]["external_parent_run_id"]}
            # 실제 모델·파일 로더 import가 차단된 프로세스에서도 복원 분기를 검증한다.
            restored = base / "restored"
            api.events.return_value = iter(rows)
            api.snapshot = lambda: "opaque-test-token"
            api.restore = lambda token, output_root: None
            def advance(days):
                write(restored, "restored", [extra])
                return SimpleNamespace(run_id="restored", start=t0, end=t0 + timedelta(days=days))
            api.advance = advance
            token = reader.snapshot(history, t0)
            reader.restore(token, output_root=restored)
            advanced = reader.advance(42)
            api.events.return_value = iter(rows + [extra])
            restored_frame = reader.read(restored, advanced.end, history=history, run_id="restored")
            restored_proof = restored_frame.attrs["run_read_evidence"]
            out["restored"] = {"rows": len(restored_frame), "status": restored_proof["status"],
                               "link": restored_proof["history_link_status"],
                               "parent": restored_proof["external_parent_run_id"]}
            out["refused"] = {}
            for label, parent in (("none", None), ("ancestor", "a0"), ("unknown", "unknown"),
                                  ("corrupt", "a"), ("unclaimed", "a")):
                root = base / label
                write(root, "bad", [extra], parent=parent)
                part = root / run_records(root)[0]["files"][0]
                if label == "corrupt":
                    content = gzip.decompress(part.read_bytes()).replace(b"session_start", b"session_starz")
                    part.write_bytes(gzip.compress(content))
                elif label == "unclaimed":
                    part.with_name("part-99999.jsonl.gz").write_bytes(part.read_bytes())
                before = api.events.call_count
                result = stage_call(label, lambda: reader.read(root, t0, history=history, run_id="bad"))
                result["events_called"] = api.events.call_count - before
                out["refused"][label] = result

            def interrupted():
                yield row
                raise OSError("시험용 읽기 중단")

            api.events.return_value = interrupted()
            out["interrupted"] = stage_call("interrupted", lambda: reader.read(main, t0, run_id="a"))
            summary = SimpleNamespace(run_id="a", start=t0, end=t0 + timedelta(days=42))
            metrics = {"events.purchase": SimpleNamespace(status="ok", reason_code=None)}
            observation = rs.outcome_observation(summary, main, metrics)
            out["observation"] = rs.outcome_observation_status(t0, 42, observation)["status"]
            # 등록된 선택적 함수 전부를 실제 조회해 모델/로더가 import될 수 없음을 확인한다.
            out["optional_refused"] = []
            for name in rs.DECISION_API:
                try:
                    rs.decision_fn(name)
                except rs.NotRun:
                    out["optional_refused"].append(name)
            out["optional_count"] = len(rs.DECISION_API)
    out["attempts"] = sorted(set(attempts))
    out["blocked_loaded"] = sorted(name for name in sys.modules if matches(name, blocked))
    out["forbidden_attempts"] = sorted(name for name in attempts if matches(name, forbidden))
    out["decision_loaded"] = sorted(name for name in sys.modules if name.startswith("src.decision"))
    return out


def _run_isolated(mode):
    result = subprocess.run([sys.executable, "-B", str(Path(__file__).resolve()), "--isolated", mode],
                            cwd=ROOT, env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
                            capture_output=True, text=True, timeout=60)
    if result.returncode:
        raise AssertionError(result.stdout + result.stderr)
    return json.loads(result.stdout)


class TestRequiredObservationImports(unittest.TestCase):
    @unittest.skipUnless(importlib.util.find_spec("yaml"),
                         "BLOCKED: PyYAML 미설치 — 러너 config 선행 조건, pandas 부재 분류 시험 미실행")
    def test_missing_packages_are_not_run_for_empty_filled_and_observation(self):
        result = _run_isolated("no_packages")
        self.assertEqual([], result["attempts_on_import"])
        self.assertEqual("ok", result["empty_verify"])
        for label in ("empty_read", "filled_read", "observation"):
            with self.subTest(label=label):
                self.assertEqual("not_run", result[label]["status"], result[label])
                self.assertEqual(0, result[label]["returned"])
                self.assertIn("pandas", result[label]["reason"])
        self.assertEqual([], result["blocked_loaded"])
        self.assertEqual([], result["forbidden_attempts"])
        self.assertEqual(["src.decision", "src.decision.config", "src.decision.observation_contract"],
                         result["decision_loaded"])

    def test_import_and_empty_run_work_without_models_or_ml_packages(self):
        script = '''
import importlib.abc, json, sys, tempfile
class BlockModels(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname.startswith(("pandas", "numpy", "sklearn", "torch", "src.decision.data",
                                "src.decision.features", "src.decision.churn", "src.decision.clv",
                                "src.decision.uplift", "src.simulator", "src.diagnostics")):
            raise AssertionError("미허용 의존 import: " + fullname)
sys.meta_path.insert(0, BlockModels())
from src.decision.observation_contract import verify_event_run
from src.measurement.sink import EventSink
with tempfile.TemporaryDirectory() as root:
    with EventSink(root, fmt="jsonl.gz", run_id="empty"):
        pass
    result = verify_event_run(root, "empty")
    print(json.dumps({"status": result["status"], "rows": result.get("raw_rows")}))
'''
        env = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1"}
        result = subprocess.run([sys.executable, "-B", "-c", script], cwd=ROOT, env=env,
                                capture_output=True, text=True, timeout=30)
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertEqual({"status": "ok", "rows": 0}, json.loads(result.stdout))

    def test_public_content_hash_keeps_null_zero_and_duplicates_distinct(self):
        from src.decision.observation_contract import event_content_hash, event_content_digest
        row = {"event_id": "fixture", "timestamp": "2026-10-22T00:00:00+09:00"}
        absent = event_content_hash(row)
        self.assertEqual(absent, event_content_hash({**row, "order_amount": None}))
        self.assertNotEqual(absent, event_content_hash({**row, "order_amount": 0}))
        self.assertEqual(absent, event_content_hash({**row, "timestamp": "2026-10-21T15:00:00Z"}))
        with self.assertRaises(ValueError): event_content_hash({**row, "order_amount": float("nan")})
        with self.assertRaises(ValueError): event_content_hash({**row, "timestamp": "2026-10-22T00:00:00"})
        self.assertNotEqual(event_content_digest([absent]), event_content_digest([absent, absent]))

    def test_contract_checks_are_not_optional_model_registry_entries(self):
        tree = ast.parse((ROOT / "src/orchestration/run_sprint.py").read_text())
        assignment = next(node for node in tree.body if isinstance(node, ast.AnnAssign)
                          and isinstance(node.target, ast.Name) and node.target.id == "DECISION_API")
        registry = ast.literal_eval(assignment.value)
        self.assertIn("load_events", registry)
        self.assertNotIn("verify_event_run", registry)
        self.assertNotIn("outcome_observation_status", registry)


@unittest.skipUnless(HAVE_DATA, NEEDS_DATA)
class TestModelIndependentEventReader(unittest.TestCase):
    def test_import_blocked_models_preserve_verified_public_stream(self):
        result = _run_isolated("models")
        self.assertEqual([], result["attempts_on_import"])
        self.assertEqual({"rows": 2, "status": "ok", "source": "src.simulator.api.events"}, result["main"])
        self.assertEqual({"rows": 3, "status": "ok", "parent": "a"}, result["branch"])
        self.assertEqual({"rows": 3, "status": "ok", "link": "ok", "parent": None}, result["restored"])
        for label, status in result["refused"].items():
            with self.subTest(label=label):
                self.assertEqual("not_run", status["status"], status)
                self.assertEqual(0, status["returned"])
                self.assertEqual(0, status["events_called"])
        self.assertEqual("not_run", result["interrupted"]["status"])
        self.assertEqual(0, result["interrupted"]["returned"])
        self.assertEqual("ok", result["observation"])
        self.assertEqual(result["optional_count"], len(result["optional_refused"]))
        self.assertEqual([], result["blocked_loaded"])
        self.assertEqual([], result["forbidden_attempts"])
        self.assertEqual(["src.decision", "src.decision.config", "src.decision.observation_contract"],
                         result["decision_loaded"])

    @classmethod
    def setUpClass(cls):
        from tests.test_feature_sprint_table import _contract_runner
        cls.runner = _contract_runner()

    @classmethod
    def tearDownClass(cls):
        sys.modules.pop(cls.runner.__name__, None)

    def rows(self):
        from tests.test_feature_sprint_table import make_events
        return [dict(row) for row in make_events(n_customers=2, days=20)[:2]]

    def write(self, root, rid, rows, parent=None):
        from src.measurement.sink import EventSink
        with EventSink(root, fmt="jsonl.gz", run_id=rid, parent_run_id=parent) as sink:
            self.assertEqual(0, sink.write_events(rows).rejected)

    def test_legacy_names_are_the_same_required_implementations(self):
        from src.decision import data, observation_contract as core
        from src.decision.features import sprint_table
        self.assertIs(data.verify_event_run, core.verify_event_run)
        self.assertIs(data._read_part, core.read_event_part)
        self.assertIs(sprint_table.outcome_observation_status, core.outcome_observation_status)

    def test_public_stream_and_observation_work_when_every_model_function_is_missing(self):
        from tests.test_feature_sprint_table import FIXTURE_T0, TestOutcomeObservationContract
        rs = self.runner
        rows = self.rows()
        api = SimpleNamespace(events=mock.Mock(return_value=iter(rows)))
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            self.write(root, "a", rows)
            with mock.patch.object(rs, "decision_fn", side_effect=rs.NotRun("선택적 모델 없음")) as optional, \
                    mock.patch.object(rs, "sim", api, create=True):
                reader = rs.EventReader()
                frame = reader.read(root, FIXTURE_T0, run_id="a")
                observation = rs.outcome_observation(
                    SimpleNamespace(run_id="a", start=FIXTURE_T0, end=FIXTURE_T0+timedelta(days=42)),
                    root, TestOutcomeObservationContract.raw_metrics())
                status = rs.outcome_observation_status(FIXTURE_T0, 42, observation)
            self.assertEqual(len(rows), len(frame))
            self.assertEqual("src.simulator.api.events", reader.source)
            self.assertEqual("ok", frame.attrs["run_read_evidence"]["status"])
            self.assertEqual("ok", status["status"])
            self.assertEqual([mock.call("load_events")], optional.call_args_list)

    def test_fallback_does_not_append_history_twice_and_still_requires_exact_parent(self):
        from tests.test_feature_sprint_table import FIXTURE_T0
        rs = self.runner
        rows = self.rows()
        extra = {**rows[0], "event_id": str(UUID(int=1, version=4))}
        api = SimpleNamespace(events=mock.Mock(side_effect=[iter(rows), iter(rows+[extra])]))
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            main, branch, wrong = root/"main", root/"branch", root/"wrong"
            self.write(main, "a", rows)
            self.write(branch, "b", [extra], parent="a")
            self.write(wrong, "c", [extra], parent=None)
            with mock.patch.object(rs, "decision_fn", side_effect=rs.NotRun("선택적 모델 없음")), \
                    mock.patch.object(rs, "sim", api, create=True):
                reader = rs.EventReader()
                history = reader.read(main, FIXTURE_T0, run_id="a")
                frame = reader.read(branch, FIXTURE_T0, history=history, run_id="b")
                self.assertEqual(len(rows)+1, len(frame))
                self.assertEqual("a", frame.attrs["run_read_evidence"]["external_parent_run_id"])
                with self.assertRaisesRegex(rs.NotRun, "HISTORY_PARENT_UNRESOLVED"):
                    reader.read(wrong, FIXTURE_T0, history=history, run_id="c")
            self.assertEqual(2, api.events.call_count)

    def test_bad_files_are_not_bypassed_by_the_stream_fallback(self):
        from tests.test_feature_sprint_table import FIXTURE_T0
        from src.measurement import sink
        rs = self.runner
        api = SimpleNamespace(events=mock.Mock())
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            self.write(root, "a", self.rows())
            part = root / sink.run_records(root)[0]["files"][0]
            part.unlink()
            with mock.patch.object(rs, "decision_fn", side_effect=rs.NotRun("선택적 모델 없음")), \
                    mock.patch.object(rs, "sim", api, create=True):
                reader = rs.EventReader()
                with self.assertRaises(rs.NotRun):
                    reader.read(root, FIXTURE_T0, run_id="a")
            api.events.assert_not_called()

    def test_partial_stream_error_does_not_return_partial_success(self):
        from tests.test_feature_sprint_table import FIXTURE_T0
        rs = self.runner
        rows = self.rows()
        def incomplete():
            yield rows[0]
            raise OSError("시험용 스트림 중간 실패")
        api = SimpleNamespace(events=mock.Mock(return_value=incomplete()))
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            self.write(root, "a", rows)
            with mock.patch.object(rs, "decision_fn", side_effect=rs.NotRun("선택적 모델 없음")), \
                    mock.patch.object(rs, "sim", api, create=True):
                with self.assertRaisesRegex(rs.NotRun, "읽기를 완료하지 못했다"):
                    rs.EventReader().read(root, FIXTURE_T0, run_id="a")

    def test_public_api_exception_shapes_record_failed_without_partial_frame(self):
        """공개 문서의 상속 모양만 사용한다. 실제 시뮬레이터 예외 내부는 읽지 않는다."""
        import contextlib
        import io
        from tests.test_feature_sprint_table import FIXTURE_T0

        class SimulatorError(Exception):
            pass

        class OutputRootError(SimulatorError):
            pass

        class SinkFormatError(SimulatorError):
            pass

        rs, rows = self.runner, self.rows()
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            self.write(root, "a", rows)
            for error_type in (OutputRootError, SinkFormatError):
                for label in ("read_events_t1", "strategy_S0"):
                    with self.subTest(error=error_type.__name__, stage=label):
                        consumed, returned = [], []

                        def interrupted():
                            consumed.append(rows[0])
                            yield rows[0]
                            raise error_type("시험용 공개 API 읽기 오류")

                        log = rs.StageLog()
                        with mock.patch.object(rs, "decision_fn", side_effect=rs.NotRun("모델 없음")), \
                                mock.patch.object(rs, "sim", SimpleNamespace(events=lambda until: interrupted()), create=True), \
                                contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                            with log.stage(label):
                                returned.append(rs.EventReader().read(root, FIXTURE_T0, run_id="a"))
                        self.assertEqual(1, len(consumed))
                        self.assertEqual([], returned)
                        self.assertEqual("failed", log.status(label))
                        self.assertIn(error_type.__name__, log.stages[-1]["reason"])

    def test_observation_value_error_stays_failed(self):
        import contextlib
        import io
        from tests.test_feature_sprint_table import FIXTURE_T0
        log = self.runner.StageLog()
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            with log.stage("observation"):
                self.runner.outcome_observation_status(FIXTURE_T0, 0, {})
        self.assertEqual("failed", log.status("observation"))
        self.assertIn("ValueError", log.stages[-1]["reason"])



@unittest.skipUnless(HAVE_DATA, NEEDS_DATA)
class TestRestoredBranchReads(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from tests.test_feature_sprint_table import _contract_runner
        cls.runner = _contract_runner()

    @classmethod
    def tearDownClass(cls):
        sys.modules.pop(cls.runner.__name__, None)

    def world(self, root, *, loader=True, parent=None, empty=False, rejected=0, ancestor_rejected=0, branch_id="b"):
        from src.decision.data import load_events
        from src.measurement.sink import EventSink
        from tests.test_feature_sprint_table import FIXTURE_T0
        import pandas as pd
        rs, t0 = self.runner, FIXTURE_T0
        past = {"event_id": str(UUID(int=100, version=4)), "customer_id": "C00000001",
                "timestamp": (t0-timedelta(days=1)).isoformat(), "event_type": "session_start",
                "page_type": "home", "session_id": f"S-C00000001-{int((t0-timedelta(days=1)).timestamp()*1000)}",
                "simulator_version": "fixture", "random_seed": 7,
                "service_version": "fixture", "customer_version": "fixture"}
        future = {**past, "event_id": str(UUID(int=101, version=4)),
                  "timestamp": (t0+timedelta(days=1)).isoformat()}
        main, branch = root/"main", root/"branch"
        rows = [] if empty else [past]
        later = [] if empty else [future]
        with EventSink(main, fmt="jsonl.gz", run_id="a") as sink:
            sink.write_events(rows)
            for _ in range(ancestor_rejected):
                sink.write_events([{**past, "event_id": "not-a-uuid"}])
        api = SimpleNamespace(snapshot=mock.Mock(return_value="opaque-token"), restore=mock.Mock(),
                              events=mock.Mock(side_effect=lambda until: iter(rows)))
        def advance(days):
            with EventSink(branch, fmt="jsonl.gz", run_id=branch_id, parent_run_id=parent) as sink:
                sink.write_events(later)
                for _ in range(rejected):
                    sink.write_events([{**future, "event_id": "not-a-uuid"}])
            api.events.side_effect = lambda until: iter(rows+later)
            return SimpleNamespace(run_id=branch_id, start=t0, end=t0+timedelta(days=days), event_count=len(later))
        api.advance = mock.Mock(side_effect=advance)
        rs.sim = api
        with mock.patch.object(rs, "decision_fn", return_value=load_events,
                               side_effect=None if loader else rs.NotRun("모델 로더 없음")):
            reader = rs.EventReader()
        history = reader.read(main, t0, run_id="a")
        token = reader.snapshot(history, t0)
        return SimpleNamespace(reader=reader, api=api, main=main, branch=branch, history=history,
                               token=token, t0=t0, rows=rows, later=later)

    def start(self, w):
        w.reader.restore(w.token, output_root=w.branch)
        return w.reader.advance(42)

    def read(self, w, summary, **kwargs):
        args = {"root": w.branch, "until": summary.end, "history": w.history, "run_id": summary.run_id}
        args.update(kwargs)
        return w.reader.read(**args)

    def test_root_local_and_explicit_parent_with_and_without_loader(self):
        for loader in (False, True):
            for parent in (None, "a"):
                for empty in (False, True):
                    with self.subTest(loader=loader, parent=parent, empty=empty), tempfile.TemporaryDirectory() as tmp:
                        w = self.world(Path(tmp), loader=loader, parent=parent, empty=empty)
                        summary = self.start(w)
                        frame = self.read(w, summary)
                        proof = frame.attrs["run_read_evidence"]
                        self.assertEqual(0 if empty else 2, len(frame))
                        self.assertEqual("ok", proof["history_link_status"])
                        self.assertEqual(parent, proof["external_parent_run_id"])
                        self.assertEqual("a", proof["history_head_run_id"])
                        self.assertEqual(["a", "b"], proof["verified_run_ids"])
                        self.assertTrue(proof["public_stream_complete"])
                        self.assertEqual(3 if not loader else 2, w.api.events.call_count)
                        self.assertNotEqual(w.token, proof["snapshot_reference"])
                        self.assertEqual(64, len(proof["snapshot_reference"]))

    def test_snapshot_rejects_unowned_or_changed_history(self):
        for mutation in ("copy", "time", "value", "evidence"):
            with self.subTest(mutation=mutation), tempfile.TemporaryDirectory() as tmp:
                w = self.world(Path(tmp))
                history, when = w.history, w.t0
                if mutation == "copy": history = history.copy()
                if mutation == "time": when += timedelta(microseconds=1)
                if mutation == "value": history.loc[0, "customer_id"] = "C00000002"
                if mutation == "evidence": history.attrs["run_read_evidence"]["rejected"] = 123
                with self.assertRaises(self.runner.NotRun):
                    w.reader.snapshot(history, when)
                self.assertEqual(1, w.api.snapshot.call_count)

    def test_bad_context_and_reuse_are_rejected(self):
        for case in ("no_advance", "wrong_root", "wrong_run", "wrong_end", "wrong_history", "start", "reuse"):
            with self.subTest(case=case), tempfile.TemporaryDirectory() as tmp:
                w = self.world(Path(tmp))
                w.reader.restore(w.token, output_root=w.branch)
                summary = (SimpleNamespace(run_id="b", end=w.t0+timedelta(days=42)) if case == "no_advance"
                           else w.reader.advance(42))
                kwargs = {}
                if case == "wrong_root": kwargs["root"] = w.main
                if case == "wrong_run": kwargs["run_id"] = "wrong"
                if case == "wrong_end": kwargs["until"] = summary.end-timedelta(microseconds=1)
                if case == "wrong_history": kwargs["history"] = w.history.copy()
                if case == "start": w.reader._active_branch["summary"]["start"] += timedelta(microseconds=1)
                if case == "reuse": self.read(w, summary)
                before = w.api.events.call_count
                with self.assertRaises(self.runner.NotRun):
                    self.read(w, summary, **kwargs)
                self.assertEqual(before, w.api.events.call_count)

    def test_failed_restore_or_advance_cannot_authorize_read(self):
        for case in ("unknown_token", "restore_failure", "advance_failure"):
            with self.subTest(case=case), tempfile.TemporaryDirectory() as tmp:
                w = self.world(Path(tmp))
                if case == "unknown_token":
                    with self.assertRaises(self.runner.NotRun): w.reader.restore("other", output_root=w.branch)
                    w.api.restore.assert_not_called()
                elif case == "restore_failure":
                    w.api.restore.side_effect = RuntimeError("fixture restore error")
                    with self.assertRaises(RuntimeError): w.reader.restore(w.token, output_root=w.branch)
                else:
                    w.reader.restore(w.token, output_root=w.branch)
                    w.api.advance.side_effect = RuntimeError("fixture advance error")
                    with self.assertRaises(RuntimeError): w.reader.advance(42)
                self.assertIsNone(w.reader._active_branch)
                with self.assertRaises(self.runner.NotRun): w.reader.advance(42)

    def test_file_and_history_tampering_is_not_bypassed(self):
        from src.measurement import sink
        for case in ("history_value", "parent_file", "parent_record", "branch_file", "unclaimed", "missing"):
            with self.subTest(case=case), tempfile.TemporaryDirectory() as tmp:
                w = self.world(Path(tmp))
                summary = self.start(w)
                root = w.main if case.startswith("parent") else w.branch
                path = root/sink.run_records(root)[0]["files"][0]
                if case == "history_value": w.history.loc[0, "customer_id"] = "C00000002"
                elif case == "parent_record":
                    record = root/"runs/run-a.json"
                    data = json.loads(record.read_text()); data["rejected"] = 1
                    record.write_text(json.dumps(data))
                elif case == "missing": path.unlink()
                elif case == "unclaimed": path.with_name("part-99999.jsonl.gz").write_bytes(path.read_bytes())
                else: path.write_bytes(path.read_bytes()+b"changed")
                with self.assertRaises(self.runner.NotRun): self.read(w, summary)
                self.assertEqual(1, w.api.events.call_count)

    def test_wrong_explicit_parent_and_duplicate_run_ids_remain_invalid(self):
        for parent in ("unknown", "b"):
            with self.subTest(parent=parent), tempfile.TemporaryDirectory() as tmp:
                w = self.world(Path(tmp), parent=parent)
                summary = self.start(w)
                with self.assertRaises(self.runner.NotRun): self.read(w, summary)
                self.assertEqual(1, w.api.events.call_count)

    def test_repeated_run_id_and_changes_during_stream_are_rejected(self):
        for case in ("duplicate_run", "parent_record", "branch_record", "history_value"):
            with self.subTest(case=case), tempfile.TemporaryDirectory() as tmp:
                w = self.world(Path(tmp), branch_id="a" if case == "duplicate_run" else "b")
                summary = self.start(w)
                if case != "duplicate_run":
                    def changing(until):
                        yield from w.rows+w.later
                        if case == "history_value":
                            w.history.loc[0, "customer_id"] = "C00000002"
                        else:
                            path = w.main/"runs/run-a.json" if case == "parent_record" else w.branch/"runs/run-b.json"
                            record = json.loads(path.read_text()); record["rejected"] = 1
                            path.write_text(json.dumps(record))
                    w.api.events.side_effect = changing
                with self.assertRaises(self.runner.NotRun): self.read(w, summary)

    def test_partial_api_failure_discards_branch_and_consumes_context(self):
        for loader in (False, True):
            with self.subTest(loader=loader), tempfile.TemporaryDirectory() as tmp:
                w = self.world(Path(tmp), loader=loader)
                summary = self.start(w)
                def incomplete(until):
                    yield w.rows[0]
                    raise RuntimeError("fixture public stream failure")
                w.api.events.side_effect = incomplete
                with self.assertRaisesRegex(RuntimeError, "public stream failure"):
                    self.read(w, summary)
                self.assertIsNone(w.reader._active_branch)
                with self.assertRaises(self.runner.NotRun): self.read(w, summary)

    def test_public_stream_must_match_expected_content_not_just_finish(self):
        for case in ("missing", "extra", "foreign", "same_id_changed", "duplicate"):
            for loader in (False, True):
                with self.subTest(case=case, loader=loader), tempfile.TemporaryDirectory() as tmp:
                    w = self.world(Path(tmp), loader=loader)
                    summary = self.start(w)
                    rows = [dict(row) for row in w.rows+w.later]
                    if case == "missing": rows.pop()
                    elif case == "extra": rows.append({**rows[0], "event_id": str(UUID(int=102, version=4))})
                    elif case == "foreign": rows[0]["customer_id"] = "C00000002"
                    elif case == "same_id_changed": rows[0]["page_type"] = "detail"
                    elif case == "duplicate": rows[1] = dict(rows[0])
                    w.api.events.side_effect = lambda until: iter(rows)
                    with self.assertRaisesRegex(self.runner.NotRun, "전량"):
                        self.read(w, summary)

    def test_snapshot_detects_different_active_world_before_making_token(self):
        with tempfile.TemporaryDirectory() as tmp:
            w = self.world(Path(tmp))
            w.api.events.side_effect = lambda until: iter([])
            with self.assertRaisesRegex(self.runner.NotRun, "활성 세계"):
                w.reader.snapshot(w.history, w.t0)
            self.assertEqual(1, w.api.snapshot.call_count)

    def test_order_and_timezone_spellings_do_not_change_content(self):
        from datetime import timezone
        from src.measurement.timeparse import parse_datetime
        with tempfile.TemporaryDirectory() as tmp:
            w = self.world(Path(tmp), loader=False)
            summary = self.start(w)
            rows = [{**row, "timestamp": parse_datetime(row["timestamp"]).astimezone(timezone.utc).isoformat()}
                    for row in reversed(w.rows+w.later)]
            w.api.events.side_effect = lambda until: iter(rows)
            proof = self.read(w, summary).attrs["run_read_evidence"]
            self.assertEqual("ok", proof["history_link_status"])
            self.assertEqual(2, proof["public_stream_content"]["rows"])

    def test_current_rejection_blocks_outcomes_and_ancestor_is_retained(self):
        from tests.test_feature_sprint_table import TestOutcomeObservationContract
        for refused in (0, 1):
            with self.subTest(rejected=refused), tempfile.TemporaryDirectory() as tmp:
                w = self.world(Path(tmp), rejected=refused, ancestor_rejected=1)
                summary = self.start(w)
                frame = self.read(w, summary)
                proof = frame.attrs["run_read_evidence"]
                self.assertEqual({"a": 1, "b": refused}, proof["run_rejections"])
                self.assertEqual(1, proof["ancestor_rejected_total"])
                observation = self.runner.outcome_observation(summary, w.branch,
                    TestOutcomeObservationContract.raw_metrics(), proof)
                status = self.runner.outcome_observation_status(w.t0, 42, observation)
                self.assertEqual("not_run" if refused else "ok", status["status"])
                if refused: self.assertIn("WRITE_REJECTED", status["reasons"])


if __name__ == "__main__":
    if len(sys.argv) == 3 and sys.argv[1] == "--isolated":
        print(json.dumps(_isolated_probe(sys.argv[2]), ensure_ascii=False))
    else:
        unittest.main()
