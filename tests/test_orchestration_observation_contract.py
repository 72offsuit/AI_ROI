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


if __name__ == "__main__":
    if len(sys.argv) == 3 and sys.argv[1] == "--isolated":
        print(json.dumps(_isolated_probe(sys.argv[2]), ensure_ascii=False))
    else:
        unittest.main()
