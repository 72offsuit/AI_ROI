"""#251 P3: 실패 원인·진단값 보존. 공개 계약 합성 입력만 사용한다.

러너 전체를 import하지 않고 관련 정의와 전략 진단 블록만 AST로 추출한다.
파일·내용 검증과 StageLog는 제품 구현을 쓰며 실제 시뮬레이터 실행은 아니다.
"""
from __future__ import annotations

import ast
import contextlib
import copy
import hashlib
import importlib.util
import io
import itertools
import json
import sys
import tempfile
import time
import traceback
import types
import unittest
from pathlib import Path
from typing import Mapping
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
HAVE_DATA = all(importlib.util.find_spec(name) for name in ("pandas", "numpy"))
NEEDS_DATA = "BLOCKED: pandas/numpy 미설치 — 공개 파일 기반 진단 시험 미실행"


def _diagnostic_runner():
    from src.decision import observation_contract as core
    from src.measurement import contracts as mc

    path = ROOT / "src/orchestration/run_sprint.py"
    tree = ast.parse(path.read_text(encoding="utf-8"))
    wanted = {"NotRun", "_SkipBody", "StageLog", "EventReader", "_pd", "frame_from_stream",
              "purchase_generated", "outcome_observation", "outcome_observation_status"}
    definitions = [copy.deepcopy(node) for node in tree.body
                   if isinstance(node, (ast.ClassDef, ast.FunctionDef)) and node.name in wanted]
    assert {node.name for node in definitions} == wanted, "필수 진단 정의 위치 변경"
    module = types.ModuleType("_branch_diagnostics_fixture")
    module.__dict__.update(
        Path=Path, Mapping=Mapping, hashlib=hashlib, json=json, sys=sys, time=time, traceback=traceback,
        contextmanager=contextlib.contextmanager, _log=lambda text: None, STREAM_CHUNK=200_000,
        verify_event_run=core.verify_event_run, event_content_hash=core.event_content_hash,
        event_content_digest=core.event_content_digest, _contract_observation_status=core.outcome_observation_status,
        mc=mc, LABEL_WINDOW_DAYS=42,
    )
    prelude = ast.parse("from __future__ import annotations").body
    exec(compile(ast.Module(body=prelude + definitions, type_ignores=[]), str(path), "exec"), module.__dict__)

    def no_optional_model(name):
        raise module.NotRun("시험의 선택적 모델·로더 없음")
    module.decision_fn = no_optional_model

    # run의 실제 전략 with 블록에서 metrics 조회부터 측정 호출까지를 그대로 사용한다.
    candidates = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.With):
            continue
        starts = [i for i, child in enumerate(node.body) if isinstance(child, ast.Try)
                  and child.body and isinstance(child.body[0], ast.Assign)
                  and any(isinstance(target, ast.Name) and target.id == "raw_metrics"
                          for target in child.body[0].targets)]
        ends = [i for i, child in enumerate(node.body) if isinstance(child, ast.Assign)
                and any(isinstance(target, ast.Subscript) and isinstance(target.value, ast.Name)
                        and target.value.id == "entry" and isinstance(target.slice, ast.Constant)
                        and target.slice.value == "measured_economics" for target in child.targets)]
        if starts and ends:
            assert len(starts) == len(ends) == 1
            candidates.append(node.body[starts[0]:ends[0] + 1])
    assert len(candidates) == 1, "전략 진단 블록 위치 변경"
    function = ast.parse("def strategy_diagnostics(entry, reader, branch_root, summary, ctx):\n    pass\n").body[0]
    function.body = copy.deepcopy(candidates[0])
    program = ast.fix_missing_locations(ast.Module(body=[function], type_ignores=[]))
    exec(compile(program, str(path), "exec"), module.__dict__)
    return module


@unittest.skipUnless(HAVE_DATA, NEEDS_DATA)
class TestBranchFailureDiagnostics(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.runner = _diagnostic_runner()

    def world(self, root, **kwargs):
        from tests.test_orchestration_observation_contract import TestRestoredBranchReads
        return TestRestoredBranchReads.world(self, root, **kwargs)

    def start(self, world):
        world.reader.restore(world.token, output_root=world.branch)
        return world.reader.advance(42)

    def read(self, world, summary):
        return world.reader.read(world.branch, summary.end, history=world.history, run_id=summary.run_id)

    def raw_metrics(self):
        from tests.test_feature_sprint_table import TestOutcomeObservationContract
        from src.measurement.schema import MetricValue
        return {**TestOutcomeObservationContract.raw_metrics(),
                "unavailable_fixture": MetricValue.not_run("합성 결손 지표")}

    def run_stage(self, world, summary, *, read_error=None, metrics_error=None):
        rs = self.runner
        world.api.metrics = mock.Mock(return_value=self.raw_metrics(), side_effect=metrics_error)
        if read_error is not None:
            def interrupted(until):
                yield world.rows[0]
                raise read_error("fixture read failure")
            world.api.events.side_effect = interrupted
        entry, log = {}, rs.StageLog()
        with mock.patch.object(rs, "branch_economics", create=True,
                               return_value={"status": "ok", "fixture": True}) as measured, \
                contextlib.redirect_stderr(io.StringIO()):
            with log.stage("strategy_S0"):
                rs.strategy_diagnostics(entry, world.reader, world.branch, summary,
                                        {"t2": world.t0, "events_t2": world.history})
        return entry, log.stages[-1], measured.call_count

    def test_root_local_corruption_keeps_both_validation_reasons(self):
        from src.decision.observation_contract import verify_event_run
        from src.measurement import sink
        for parent, case in itertools.product((None, "a"), ("digest", "missing", "unclaimed", "source")):
            with self.subTest(parent=parent, case=case), tempfile.TemporaryDirectory() as temp:
                world = self.world(Path(temp), parent=parent)
                summary = self.start(world)
                record_path = world.branch / "runs/run-b.json"
                record = json.loads(record_path.read_text())
                part = world.branch / sink.run_records(world.branch)[0]["files"][0]
                if case == "digest":
                    record["sha256"] = "0" * 64
                    record_path.write_text(json.dumps(record))
                elif case == "source":
                    record["sources"] = {"commerce": record["rows"]}
                    record_path.write_text(json.dumps(record))
                elif case == "missing":
                    part.unlink()
                else:
                    part.with_name("part-99999.jsonl.gz").write_bytes(part.read_bytes())
                first = verify_event_run(world.branch, summary.run_id)
                self.assertEqual("not_run", first["status"])
                second = verify_event_run(world.branch, summary.run_id,
                                          history_evidence=world.history.attrs["run_read_evidence"])
                self.assertEqual("not_run", second["status"])
                entry, stage, calls = self.run_stage(world, summary)
                self.assertEqual("ok", stage["status"])  # 읽기 NotRun은 진단에 남기는 기존 경로
                self.assertEqual("not_run", entry["event_read_evidence"]["status"])
                self.assertEqual("not_run", entry["measured_economics"]["status"])
                self.assertEqual(0, calls)
                reason = entry["event_read_evidence"]["reason"]
                expected = ("이벤트 원시 읽기 근거 미충족: "
                            f"root-local 검증: {first.get('reason')}; history 검증: {second.get('reason')}")
                self.assertEqual(expected, reason)
                self.assertEqual(1, world.api.events.call_count)  # 파일 실패 뒤 API 우회 없음

    def test_valid_external_parent_still_resolves_first_failure(self):
        with tempfile.TemporaryDirectory() as temp:
            world = self.world(Path(temp), parent="a")
            summary = self.start(world)
            proof = self.read(world, summary).attrs["run_read_evidence"]
            self.assertEqual("ok", proof["history_link_status"])
            self.assertEqual("a", proof["external_parent_run_id"])

    def test_economic_reason_matches_only_the_three_failed_gate_flags(self):
        rs = self.runner
        keys = ("label_window_complete", "writing_complete", "read_complete")
        for flags in itertools.product((False, True), repeat=3):
            with self.subTest(flags=flags):
                status = dict(zip(keys, flags))
                # 구매 관측만 실패한 사유까지 경제 거부 사유로 복제하지 않는다.
                status.update(status="not_run", purchase_generated=False, reasons=["PURCHASE_NOT_OBSERVABLE"])
                reader = types.SimpleNamespace(read=mock.Mock(return_value=types.SimpleNamespace(attrs={})))
                entry = {}
                with mock.patch.object(rs, "sim", types.SimpleNamespace(metrics=lambda *a: self.raw_metrics()), create=True), \
                        mock.patch.object(rs, "outcome_observation", return_value={}), \
                        mock.patch.object(rs, "outcome_observation_status", return_value=status), \
                        mock.patch.object(rs, "branch_economics", create=True, return_value={"status": "ok"}) as measured:
                    rs.strategy_diagnostics(entry, reader, Path("fixture"), types.SimpleNamespace(end=None, run_id="b"),
                                            {"t2": None, "events_t2": None})
                gate = entry["economics_input_observation"]
                self.assertEqual("ok" if all(flags) else "not_run", gate["status"])
                if all(flags):
                    self.assertIsNone(gate["reason"])
                else:
                    for key, complete in zip(keys, flags):
                        self.assertEqual(not complete, key in gate["reason"], gate)
                    self.assertNotIn("PURCHASE_NOT_OBSERVABLE", gate["reason"])
                self.assertEqual(int(status["read_complete"]), measured.call_count)

    def test_public_error_shapes_preserve_metrics_and_failed_classification(self):
        class SimulatorError(Exception):
            pass
        class OutputRootError(SimulatorError):
            pass
        class SinkFormatError(SimulatorError):
            pass
        for loader in (False, True):
            for error in (OutputRootError, SinkFormatError, TypeError):
                with self.subTest(loader=loader, error=error.__name__), tempfile.TemporaryDirectory() as temp:
                    world = self.world(Path(temp), loader=loader)
                    summary = self.start(world)
                    entry, stage, calls = self.run_stage(world, summary, read_error=error)
                    self.assertEqual("failed", stage["status"])
                    self.assertIn(error.__name__, stage["reason"])
                    self.assertIn("sim_metrics", entry)
                    self.assertEqual({key: self.runner.mc.metric_to_json(value)
                                      for key, value in self.raw_metrics().items()}, entry["sim_metrics"])
                    self.assertEqual(0, entry["sim_metrics"]["events.purchase"]["value"])
                    self.assertEqual("not_run", entry["sim_metrics"]["unavailable_fixture"]["status"])
                    self.assertNotIn("measured_economics", entry)
                    self.assertEqual(0, calls)
                    self.assertIsNone(world.reader._active_branch)

    def test_value_and_io_read_errors_keep_metrics_and_block_measured_input(self):
        for error in (ValueError, OSError):
            with self.subTest(error=error.__name__), tempfile.TemporaryDirectory() as temp:
                world = self.world(Path(temp))
                summary = self.start(world)
                entry, stage, calls = self.run_stage(world, summary, read_error=error)
                self.assertEqual("ok", stage["status"])  # 읽기 NotRun을 잡고 진단을 남기는 기존 흐름
                self.assertEqual("not_run", entry["event_read_evidence"]["status"])
                self.assertIn(error.__name__, entry["event_read_evidence"]["reason"])
                self.assertEqual("not_run", entry["measured_economics"]["status"])
                self.assertIn("read_complete", entry["economics_input_observation"]["reason"])
                self.assertNotIn("writing_complete", entry["economics_input_observation"]["reason"])
                self.assertIn("events.purchase", entry["sim_metrics"])
                self.assertEqual(0, calls)

    def test_success_keeps_zero_and_missing_metrics_without_changing_economics(self):
        with tempfile.TemporaryDirectory() as temp:
            world = self.world(Path(temp))
            summary = self.start(world)
            entry, stage, calls = self.run_stage(world, summary)
            self.assertEqual("ok", stage["status"])
            self.assertEqual("ok", entry["economics_input_observation"]["status"])
            self.assertIsNone(entry["economics_input_observation"]["reason"])
            self.assertEqual(0, entry["sim_metrics"]["events.purchase"]["value"])
            self.assertIsNone(entry["sim_metrics"]["unavailable_fixture"]["value"])
            self.assertEqual({"status": "ok", "fixture": True}, entry["measured_economics"])
            self.assertEqual(1, calls)

    def test_metrics_query_failure_still_allows_independent_measurement(self):
        with tempfile.TemporaryDirectory() as temp:
            world = self.world(Path(temp))
            summary = self.start(world)
            entry, stage, calls = self.run_stage(world, summary, metrics_error=RuntimeError("fixture metrics failure"))
            self.assertEqual("ok", stage["status"])
            self.assertEqual({}, entry["sim_metrics"])
            self.assertIn("RuntimeError", entry["sim_metrics_error"])
            self.assertEqual("ok", entry["economics_input_observation"]["status"])
            self.assertEqual(1, calls)

        # 조회 성공 뒤 반환 계약을 어긴 경우에도 직렬화 전 구매 진단은 남긴다.
        invalid_metrics = (
            {"events.purchase": {"status": "ok", "value": 0}},
            {"events.purchase": types.SimpleNamespace(status="ok", value=0)},
        )
        for metrics in invalid_metrics:
            with self.subTest(metric_type=type(metrics["events.purchase"]).__name__), \
                    tempfile.TemporaryDirectory() as temp:
                world = self.world(Path(temp))
                summary = self.start(world)
                with mock.patch.object(self, "raw_metrics", return_value=metrics):
                    entry, stage, calls = self.run_stage(world, summary)
                generated, detail = self.runner.purchase_generated(metrics)
                self.assertIn("purchase_generated", entry)
                self.assertEqual({"value": generated, "detail": detail}, entry["purchase_generated"])
                self.assertEqual("failed", stage["status"])
                self.assertIn("AttributeError", stage["reason"])
                self.assertNotIn("sim_metrics", entry)
                self.assertNotIn("sim_metrics_error", entry)  # 조회 실패와 반환 계약 위반을 구분한다.
                self.assertNotIn("event_read_evidence", entry)
                self.assertNotIn("measured_economics", entry)
                self.assertEqual(0, calls)
                self.assertEqual(1, world.api.events.call_count)  # snapshot 뒤 읽기에 도달하지 못했다.


if __name__ == "__main__":
    unittest.main()
