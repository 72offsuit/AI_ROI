"""`src/main.py` — main CLI 디스패처 (이슈 #206 · SRS SYS-004 · PRD §73).

  의존성 없이   ``python src/main.py --help`` 가 **스크립트로** 돈다 · 모드별 단계 집합 · ``--budget`` 규칙 ·
               종료 코드 · main.py 가 시뮬레이터 · 진단을 import 하지 않는다(AST)
  의존성 있으면 실제 시뮬레이터 소규모 세계 + 학습 모델만 가짜(``tests/test_orchestration_sprint.FakeDecision``)
               + **진짜** segments · strategies · optimize 로 다섯 모드를 끝까지 돌린다. 모드마다 실행한 단계가 전부
               ok 이고, 범위 밖 단계는 not_run 과 사유이며, 모드별 산출물이 run() 의 결과와 맞는지 대조한다.

실행:
    python3 -m unittest tests.test_orchestration_main_cli -v
"""

from __future__ import annotations

import ast
import contextlib
import csv
import importlib
import importlib.util
import io
import json
import math
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from src import main as cli

REPO_ROOT = Path(__file__).resolve().parents[1]
MAIN = REPO_ROOT / "src" / "main.py"
_DEPS = all(importlib.util.find_spec(m) is not None for m in ("numpy", "pandas", "sklearn", "yaml"))
_SKIP = "BLOCKED: numpy/pandas/scikit-learn/PyYAML 미설치 — 모드 종단 실행을 하지 않았다(통과가 아니다)"

if _DEPS:
    from src.orchestration import run_sprint as rs
    from tests.test_orchestration_sprint import FakeDecision, _quiet

    class _Fake(FakeDecision):
        """CLV 를 크게 — 기대 증분가치가 계획 비용을 넘는 고객이 생겨 S5 배정이 0 명이 아니게 한다.
        #217 2부부터 S4 · S5 의 가치는 12개월 CLV(``predict_lifetime``)다."""

        CLV_UNIT = 1_000_000.0

# warmup 60일 — RCT 모집단이 Eligible(가입 ≥ 60일)이라 45일이면 0명이다(test_orchestration_sprint.SMALL · DR-234).
SMALL = ["--seed", "7", "--customers", "240", "--profile", "smoke", "--warmup-days", "60"]
BUDGET = 100_000
STDLIB_TOP = {"__future__", "argparse", "hashlib", "importlib", "json", "math", "shutil", "sys", "textwrap",
              "time", "dataclasses", "datetime", "pathlib", "typing"}


def _read(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


class TestCliWithoutDependencies(unittest.TestCase):
    """의존성 없이 — 인자 · 모드 정의 · 종료 코드 · import 경계."""

    def test_help_runs_as_a_script_from_anywhere(self) -> None:
        """PRD §73 의 명령 형태 `python src/main.py` — sys.path[0] 이 src/ 여도 import 가 된다."""
        with tempfile.TemporaryDirectory() as tmp:
            done = subprocess.run([sys.executable, str(MAIN), "--help"], cwd=tmp, capture_output=True,
                                  text=True, timeout=60)
        self.assertEqual(0, done.returncode, done.stderr)
        for word in (*cli.MODES, cli.UPLIFT_SCORES, cli.BUDGET_ALLOCATION, cli.MANIFEST,
                     "config/model_config.yaml", "config/experiment_config.yaml", "results/cli/<mode>/",
                     "data/sprint/<run_id>/", "--budget"):
            self.assertIn(word, done.stdout, word)

    def test_help_runs_as_a_module(self) -> None:
        done = subprocess.run([sys.executable, "-m", "src.main", "--help"], cwd=REPO_ROOT,
                              capture_output=True, text=True, timeout=60)
        self.assertEqual(0, done.returncode, done.stderr)

    def test_budget_rules(self) -> None:
        cases = (["--mode", "optimize"], ["--mode", "train", "--budget", "5"],
                 ["--mode", "uplift", "--budget", "5"], ["--mode", "optimize", "--budget", "0"],
                 ["--mode", "monitor"])
        for argv in cases:
            with self.subTest(argv), contextlib.redirect_stderr(io.StringIO()), \
                    self.assertRaises(SystemExit) as caught:
                cli.main(argv)
            self.assertEqual(2, caught.exception.code)

    def test_mode_stage_sets(self) -> None:
        modes = cli.MODES
        self.assertEqual(["train", "uplift", "optimize", "evaluate", "full"], list(modes))
        self.assertIsNone(modes["full"].stages)
        self.assertLess(modes["train"].stages, modes["uplift"].stages)
        self.assertLess(modes["uplift"].stages, modes["optimize"].stages)
        self.assertLess(modes["train"].stages, modes["evaluate"].stages)
        self.assertNotIn("strategy_S5", modes["optimize"].stages)  # 계획 단계 — 분기 시뮬레이션 없음
        for mode in modes.values():
            if mode.stages is not None:
                self.assertIn("simulate_warmup", mode.stages, mode.name)
        self.assertEqual("required", modes["optimize"].budget)

    def test_imports_stay_inside_the_boundary(self) -> None:
        """main.py 는 시뮬레이터 · 진단을 import 하지 않는다. 최상위 import 는 표준 라이브러리뿐(--help 무의존)."""
        tree = ast.parse(MAIN.read_text(encoding="utf-8"))
        modules: list[str] = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                modules += [a.name for a in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module:
                modules.append(node.module)
        modules += [n.value for n in ast.walk(tree) if isinstance(n, ast.Constant) and isinstance(n.value, str)
                    and n.value.startswith("src.")]
        banned = [m for m in modules if m.startswith(("src.simulator", "src.diagnostics"))]
        self.assertEqual([], banned)
        outside = [m for m in modules if m.startswith("src.")
                   and not m.startswith(("src.decision", "src.orchestration", "src.measurement"))]
        self.assertEqual([], outside)
        top = [(a.name if isinstance(node, ast.Import) else node.module).split(".")[0]
               for node in tree.body if isinstance(node, (ast.Import, ast.ImportFrom))
               for a in (node.names if isinstance(node, ast.Import) else [None])]
        self.assertEqual(set(), set(top) - STDLIB_TOP - {"src"})
        from_src = [node.module for node in tree.body if isinstance(node, ast.ImportFrom)
                    and (node.module or "").startswith("src")]
        self.assertEqual(["src.measurement.errors"], from_src)

    def test_stage_report_separates_scope_and_exit_codes(self) -> None:
        mode = cli.Mode("x", "", frozenset({"a", "b", "c"}), (), "rejected")
        stages = [
            {"name": "a", "status": "ok", "reason": None},
            {"name": "b", "status": "not_run", "reason": "라벨이 한 값뿐"},
            {"name": "d", "status": "not_run", "reason": "실행 범위 밖이다(--mode x)"},
        ]
        report = cli.stage_report(mode, stages)
        self.assertEqual(["a"], report["ok"])
        self.assertEqual(["b"], [s["name"] for s in report["not_run_in_scope"]])
        self.assertEqual(["d"], report["out_of_scope"])
        self.assertEqual(["c"], report["unknown_selected"])           # 이름이 바뀐 단계 → 1
        self.assertEqual(1, cli.exit_code(report, {}))
        report["unknown_selected"] = []
        self.assertEqual(cli.NOT_RUN_EXIT, cli.exit_code(report, {}))
        report["not_run_in_scope"] = []
        self.assertEqual(0, cli.exit_code(report, {"f": {"status": "ok"}}))
        self.assertEqual(cli.NOT_RUN_EXIT, cli.exit_code(report, {"f": {"status": "not_run"}}))
        self.assertEqual(1, cli.exit_code(report, {"f": {"status": "failed"}}))
        self.assertNotEqual(2, cli.NOT_RUN_EXIT)  # 2 는 argparse 인자 오류

    def test_artifact_without_scores_is_not_run_not_empty(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            for name in (cli.UPLIFT_SCORES, cli.BUDGET_ALLOCATION):
                result = cli.write_artifact(name, Path(tmp), {"scores": {"cate": None}})
                with self.subTest(name):
                    self.assertEqual("not_run", result["status"])
                    self.assertIn("점수가 없다", result["reason"])
                    self.assertFalse((Path(tmp) / name).exists())


@unittest.skipUnless(_DEPS, _SKIP)
class TestStageScope(unittest.TestCase):
    def test_out_of_scope_stage_is_skipped_with_reason(self) -> None:
        log = rs.StageLog(frozenset({"a"}), "--mode x")
        with _quiet():
            with log.stage("b", requires=("a",)):
                rs.skip_if_not_run(log, "b")
                self.fail("범위 밖 단계의 본문이 돌았다")
        self.assertEqual("not_run", log.status("b"))
        self.assertIn("--mode x", log.stages[-1]["reason"])

    def test_out_of_scope_body_without_skip_guard_raises(self) -> None:
        log = rs.StageLog(frozenset({"a"}), "--mode x")
        with _quiet(), self.assertRaises(RuntimeError):
            with log.stage("unguarded"):
                pass

    def test_default_log_runs_everything(self) -> None:
        log = rs.StageLog()
        with _quiet():
            with log.stage("anything"):
                pass
        self.assertEqual("ok", log.status("anything"))


@unittest.skipUnless(_DEPS, _SKIP)
class TestModesEndToEnd(unittest.TestCase):
    """실제 시뮬레이터 + 가짜 학습 모델 + 진짜 segments · strategies · optimize 로 다섯 모드를 돌린다."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.tmp = tempfile.TemporaryDirectory()
        base = Path(cls.tmp.name)
        real = {name: importlib.import_module(name)
                for name in ("src.decision.segments", "src.decision.strategies", "src.decision.optimize")}
        cls.runs: dict[str, tuple[int, Path]] = {}
        for mode in cli.MODES:
            # #214 — main.py 는 기본으로 저장한다. 저장소의 models/ · data/processed/ 를 더럽히지 않게 임시 폴더로 보낸다.
            argv = ["--mode", mode, *SMALL, "--out", str(base / mode / "out"),
                    "--results-root", str(base / mode / "res"), "--run-id", f"SP-test-{mode}",
                    "--models-root", str(base / mode / "models"),
                    "--feature-store-root", str(base / mode / "processed")]
            if mode == "optimize":
                argv += ["--budget", str(BUDGET)]
            modules = {**_Fake().modules(), **real}
            generated = mock.patch.object(rs, "purchase_generated", return_value=(True, "test: 가짜 로더가 만든다"))
            with mock.patch.dict(sys.modules, modules), generated, _quiet():
                code = cli.main(argv)
            cls.runs[mode] = (code, base / mode / "res" / "sprint-v0" / f"SP-test-{mode}")

    @classmethod
    def tearDownClass(cls) -> None:
        cls.tmp.cleanup()

    def test_every_mode_exits_zero_and_writes_the_seven_results(self) -> None:
        for mode, (code, run_dir) in self.runs.items():
            with self.subTest(mode):
                self.assertEqual(0, code)
                for name in rs.RESULT_FILES:
                    self.assertTrue((run_dir / f"{name}.json").is_file(), name)
                manifest = _read(run_dir / cli.MANIFEST)
                self.assertEqual(mode, manifest["mode"])
                self.assertEqual(0, manifest["exit_code"])
                self.assertEqual([], manifest["stages"]["unknown_selected"])
                self.assertEqual(sorted(cli.MODES[mode].writes), sorted(manifest["outputs"]["files"]))
                self.assertFalse(manifest["inputs"]["reads_previous_runs"])

    def test_selected_stages_ok_and_the_rest_out_of_scope(self) -> None:
        all_names = [s["name"] for s in _read(self.runs["full"][1] / "run_meta.json")["stages"]]
        for mode, (_, run_dir) in self.runs.items():
            selected = cli.MODES[mode].stages
            with self.subTest(mode):
                if selected is not None:
                    self.assertLessEqual(selected, set(all_names), "모드가 없는 단계 이름을 고른다")
                for stage in _read(run_dir / "run_meta.json")["stages"]:
                    if selected is None or stage["name"] in selected:
                        self.assertEqual("ok", stage["status"], stage)
                    else:
                        self.assertEqual("not_run", stage["status"], stage)
                        self.assertIn(f"--mode {mode}", stage["reason"])

    def test_train_saves_models_and_features_with_nfr01_versions(self) -> None:
        """#214 — ML-008 모델 · FS-001/002 Feature 저장과 NFR-01 8개 키."""
        _, run_dir = self.runs["train"]
        persisted = _read(run_dir / cli.MANIFEST)["outputs"]["persisted"]
        self.assertEqual("ok", persisted["status"], persisted)
        for kind in ("churn", "uplift", "clv", "clv_12m"):
            record = persisted["models"]["models"][kind]
            self.assertEqual("ok", record["status"], kind)
            self.assertTrue(Path(record["file"]).is_file(), kind)
            meta = _read(Path(record["file"]).with_suffix(".json"))
            for key in ("model_version", "dataset_version", "feature_version", "parameters", "cv_score",
                        "test_score", "created_at", "sha256"):
                self.assertIn(key, meta, f"{kind}.{key}")
        self.assertEqual("ok", persisted["features"]["tables"]["features_t1"]["status"])
        self.assertEqual("ok", persisted["features"]["tables"]["labels_t1"]["status"])
        versions = _read(run_dir / "run_meta.json")["versions"]
        for key in ("service_version", "simulator_version", "customer_seed", "random_seed", "feature_version",
                    "model_version", "strategy_version", "experiment_version"):
            self.assertIn(key, versions)
        self.assertEqual({"churn", "uplift", "clv", "clv_12m"}, set(versions["model_version"]))

    def test_another_seed_loads_saved_models_without_refitting(self) -> None:
        """#214 완료 조건 — 저장한 모델을 다른 seed 실행이 다시 학습하지 않고 불러와 평가만 한다(GATE 4 전제)."""
        _, train_dir = self.runs["train"]
        models_dir = _read(train_dir / cli.MANIFEST)["outputs"]["persisted"]["models"]["root"]
        base = Path(self.tmp.name) / "load"
        fake = _Fake()
        argv = ["--mode", "train", "--seed", "8", *SMALL[2:], "--out", str(base / "out"),
                "--results-root", str(base / "res"), "--run-id", "SP-test-load", "--no-persist",
                "--load-models", models_dir]
        generated = mock.patch.object(rs, "purchase_generated", return_value=(True, "test: 가짜 로더가 만든다"))
        modules = fake.modules()
        # PR #279 리뷰 N2 — 평가 함수가 없으면 단계가 not_run 이다. 정상 경로를 보려면 평가 함수를 준다.
        modules["src.decision.churn"].evaluate_fitted_churn = lambda model, X, y: {"n": int(len(y))}
        modules["src.decision.uplift"].evaluate_fitted_uplift = lambda model, X, t, y: {"n": int(len(y))}
        modules["src.decision.clv"].evaluate_fitted_clv = lambda model, X, v: {"n": int(len(v))}
        with mock.patch.dict(sys.modules, modules), generated, _quiet():
            code = cli.main(argv)
        run_dir = base / "res" / "sprint-v0" / "SP-test-load"
        self.assertEqual(0, code)
        refits = [name for name, _ in fake.calls
                  if name in ("fit_best_churn", "fit_uplift", "evaluate_churn_models", "evaluate_uplift_models",
                              "fit_lifetime")]
        self.assertEqual([], refits, "불러온 실행이 다시 학습 · 선택했다")
        for name in ("churn_eval", "uplift_eval", "clv_eval"):
            payload = _read(run_dir / f"{name}.json")
            self.assertEqual("ok", payload["status"], name)
            self.assertTrue(payload["model_source"].startswith("loaded"), name)
            self.assertEqual("SP-test-train", payload["trained_run"], name)
        lifetime = _read(run_dir / "clv_eval.json")["clv_12m"]  # #217 2부 — 12개월 CLV 도 불러와 검증만
        self.assertEqual("ok", lifetime["status"], lifetime)
        self.assertTrue(lifetime["model_source"].startswith("loaded"))
        self.assertEqual("SP-test-train", lifetime["trained_run"])
        manifest = _read(run_dir / cli.MANIFEST)
        self.assertIs(True, manifest["inputs"]["reads_previous_runs"])
        self.assertEqual("not_requested", manifest["outputs"]["persisted"]["status"])

    def test_unknown_current_feature_version_stops_before_loading(self) -> None:
        """PR #279 리뷰 R2 — 지금 코드의 feature_version 을 잴 수 없으면(None) 대조를 건너뛰지 않고 시작 전에 멈춘다."""
        _, train_dir = self.runs["train"]
        models_dir = _read(train_dir / cli.MANIFEST)["outputs"]["persisted"]["models"]["root"]
        base = Path(self.tmp.name) / "noversion"
        argv = ["--mode", "train", *SMALL, "--out", str(base / "out"), "--results-root", str(base / "res"),
                "--no-persist", "--load-models", models_dir]
        err = io.StringIO()
        with mock.patch("src.decision.versions.feature_version", return_value=None), _quiet(), \
                contextlib.redirect_stderr(err):
            code = cli.main(argv)
        self.assertEqual(cli.EXIT_MODEL_LOAD, code)
        self.assertIn("feature_version", err.getvalue())
        self.assertFalse((base / "out").exists(), "멈춘 실행이 시뮬레이터 출력을 만들었다")

    def test_missing_model_folder_stops_before_simulating(self) -> None:
        base = Path(self.tmp.name) / "missing"
        argv = ["--mode", "train", *SMALL, "--out", str(base / "out"), "--results-root", str(base / "res"),
                "--no-persist", "--load-models", str(base / "nope")]
        with _quiet(), contextlib.redirect_stderr(io.StringIO()):
            code = cli.main(argv)
        self.assertEqual(cli.EXIT_MODEL_LOAD, code)
        self.assertFalse((base / "out").exists(), "멈춘 실행이 시뮬레이터 출력을 만들었다")

    def test_full_writes_cate_file_in_the_s8_contract(self) -> None:
        """#217 · DR-S8 결정 1 — 고객별 τ̂ ``cate.jsonl`` 은 정해진 열만, t1 · t2 두 기준 시각, 계산 불가는 null."""
        _, run_dir = self.runs["full"]
        record = _read(run_dir / "uplift_eval.json")["cate_file"]
        self.assertEqual("ok", record["status"], record)
        self.assertEqual({"t1", "t2"}, set(record["rows"]))
        self.assertIs(True, record["in_sample_t1"])  # 같은 실행에서 학습했다 — 채점은 Final Holdout 파일로
        rows = [json.loads(line) for line in (run_dir / "cate.jsonl").read_text(encoding="utf-8").splitlines()]
        self.assertEqual(sum(record["rows"].values()), len(rows))
        for row in rows:
            self.assertEqual(["customer_id", "t0", "cate_T1", "cate_T2", "cate_T3", "cate_T4"], list(row))
        timeline = _read(run_dir / "run_meta.json")["timeline"]
        self.assertEqual({timeline["t1"], timeline["t2"]}, {row["t0"] for row in rows})

    def test_train_trains_and_scores_nothing(self) -> None:
        _, run_dir = self.runs["train"]
        for name in ("churn_eval", "uplift_eval", "clv_eval"):
            self.assertEqual("ok", _read(run_dir / f"{name}.json")["status"], name)
        self.assertEqual("not_run", _read(run_dir / "segments.json")["status"])
        self.assertFalse((run_dir / cli.UPLIFT_SCORES).exists())

    def test_uplift_csv_matches_the_segments_stage(self) -> None:
        _, run_dir = self.runs["uplift"]
        manifest = _read(run_dir / cli.MANIFEST)["outputs"]["files"][cli.UPLIFT_SCORES]
        self.assertEqual("ok", manifest["status"])
        self.assertIs(True, manifest["consistent_with_segments_json"])
        with (run_dir / cli.UPLIFT_SCORES).open(encoding="utf-8") as handle:
            rows = list(csv.DictReader(handle))
        self.assertEqual(_read(run_dir / "segments.json")["n"], len(rows))
        self.assertEqual(["customer_id", "churn_p", "clv", "cate_T1", "cate_T2", "cate_T3", "cate_T4",
                          "uplift_score", "uplift_arm", "quadrant", "segment", "segment_prd_id"], list(rows[0]))
        for row in rows:
            cate = {t: float(row[f"cate_{t}"]) for t in ("T1", "T2", "T3", "T4")}
            self.assertTrue(math.isclose(max(cate.values()), float(row["uplift_score"])))
            self.assertEqual(max(cate, key=cate.get), row["uplift_arm"])

    def test_optimize_allocates_within_budget_and_matches_what_if(self) -> None:
        _, run_dir = self.runs["optimize"]
        allocation = _read(run_dir / cli.BUDGET_ALLOCATION)
        self.assertEqual(float(BUDGET), allocation["budget_krw"])
        totals = allocation["totals"]
        self.assertGreater(totals["n_targeted"], 0)
        self.assertLessEqual(totals["planned_spend_krw"], BUDGET)
        self.assertTrue(math.isclose(totals["planned_spend_krw"],
                                     sum(r["planned_spend_krw"] for r in allocation["segments"])))
        self.assertEqual(totals["n_customers"], sum(r["n_customers"] for r in allocation["segments"]))
        self.assertEqual("ok", allocation["expected"]["status"])
        self.assertIs(True, allocation["expected"]["consistent_with_allocation"])
        stages = {s["name"]: s for s in _read(run_dir / "run_meta.json")["stages"]}
        self.assertEqual("not_run", stages["strategy_S5"]["status"])  # 계획만 — 분기 시뮬레이션 없음
        self.assertIn("--budget-krw", _read(run_dir / "strategy_comparison.json")["budget"]["source"])

    def test_evaluate_runs_holdout_and_ab_without_strategy_comparison(self) -> None:
        _, run_dir = self.runs["evaluate"]
        self.assertIn("temporal_holdout", _read(run_dir / "churn_eval.json"))
        self.assertEqual("ok", _read(run_dir / "ab_test.json")["status"])
        stages = {s["name"]: s["status"] for s in _read(run_dir / "run_meta.json")["stages"]}
        self.assertEqual("ok", stages["strategy_S0"])
        self.assertEqual("not_run", stages["strategy_S1"])

    def test_full_runs_every_stage_and_both_artifacts(self) -> None:
        _, run_dir = self.runs["full"]
        files = _read(run_dir / cli.MANIFEST)["outputs"]["files"]
        self.assertEqual({"ok"}, {f["status"] for f in files.values()})
        self.assertEqual(_read(run_dir / "strategy_comparison.json")["budget_krw"],
                         _read(run_dir / cli.BUDGET_ALLOCATION)["budget_krw"])


if __name__ == "__main__":
    unittest.main()
