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


class TestRequiredObservationImports(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()
