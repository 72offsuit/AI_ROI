"""모델·실험 config 로더와 '옮겼을 뿐 동작은 그대로다'의 고정 (이슈 #206 · SRS CFG-002/003 · CQ-003).

세 겹으로 본다. 하나만 있으면 구멍이 남는다.

  1. 스키마 — 모르는 키 · 빠진 키 · 타입 · 범위를 거부한다. dict 로 검증하므로 **의존성 없이 돈다.**
  2. 동일성 — 저장소의 config 값이 #206 이전 코드 상수와 같다(``PRE_206_*``, PyYAML 필요).
     ★ 값을 바꾸면 여기가 실패한다. 실패가 정상이다 — 바꾸는 것은 결정이므로 DR 을 쓰고 이 기준값을
       함께 고친다. 조용히 기준값만 고치면 '동작이 바뀌지 않았다'는 보증이 사라진다.
  3. 배선 — 코드가 실제로 config 값을 쓴다(numpy·pandas·sklearn 필요). ``make_model`` 이 만든 추정기의
     ``get_params()`` 가 #206 이전 코드가 **문자 그대로** 만들던 추정기와 같고, config 를 바꾸면 따라 바뀐다.
     AST 검사는 그 자리에 숫자가 다시 박히지 않게 한다(의존성 없이).

실행:
    python3 -m unittest tests.test_decision_config -v
"""

from __future__ import annotations

import ast
import copy
import dataclasses
import importlib.util
import inspect
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from src.decision import config as dc
from src.measurement import config_loader as cl
from src.measurement.errors import ConfigError

REPO_ROOT = Path(__file__).resolve().parents[1]
HAVE_ML = all(importlib.util.find_spec(m) is not None for m in ("numpy", "pandas", "sklearn", "scipy"))
NEEDS_YAML = "BLOCKED: PyYAML 미설치 — config 파일 대조를 하지 않았다(통과가 아니다)"
NEEDS_ML = "BLOCKED: numpy/pandas/scikit-learn/scipy 미설치 — 배선 대조를 하지 않았다(통과가 아니다)"

#: #206 이전 코드 상수 — churn.py(N_SPLITS · INNER_SPLITS · SHAP_SAMPLE · make_model 인자) ·
#: clv.py(fit_clv 인자 · evaluate_clv n_splits) · segments.py(DEFAULT_THRESHOLDS). origin/main d9a3902 에서 옮겨 적었다.
PRE_206_MODEL = {
    "schema_version": 1,
    "churn": {
        "cv_folds": 5,
        "threshold_inner_folds": 3,
        "shap_sample": 500,
        "models": {
            "logistic_regression": {"C": 0.5, "max_iter": 2000, "class_weight": "balanced"},
            "random_forest": {"n_estimators": 300, "min_samples_leaf": 3,
                              "class_weight": "balanced_subsample", "n_jobs": -1},
            "hist_gb": {"learning_rate": 0.05, "max_iter": 300, "max_leaf_nodes": 15,
                        "l2_regularization": 1.0, "class_weight": "balanced", "early_stopping": False},
        },
    },
    "clv": {
        "cv_folds": 5,
        "hist_gb": {"loss": "poisson", "learning_rate": 0.05, "max_iter": 200, "max_leaf_nodes": 15,
                    "l2_regularization": 1.0, "min_samples_leaf": 20, "early_stopping": False},
    },
    "segmentation": {"clv_high_q": 0.8, "churn_high_q": 0.5, "uplift_band_q": 0.6},
}

# #179는 기존 모델 수치를 그대로 두고 사전 고정 위험도 기준선 이름만 추가한다.
MODEL_NOW = copy.deepcopy(PRE_206_MODEL)
MODEL_NOW["churn"]["risk_baseline_model"] = "logistic_regression"

#: #206 이전 — run_sprint.py(RCT_CONTROL_SHARE · DEFAULT_ACTIVE_DAYS · --seed/--customers/--profile 기본값) ·
#: ab_test.py(alpha · power · SRM threshold 기본값).
PRE_206_EXPERIMENT = {
    "schema_version": 1,
    "run": {"num_customers": 20000, "profile": "reference"},
    "holdout": {"development_seed": 42},
    "rct": {"control_share": 0.5, "active_days": 90},
    "ab_test": {"alpha": 0.05, "target_power": 0.8, "srm_p_threshold": 0.001},
}
#: 지금 판 — #206 값에서
#:   · `rct.active_days` 를 없앴다(#234 · DR-234: RCT 모집단은 설정값이 아니라 data_spec §4.1 Eligible 정본 정의다).
#:   · 실험 규모를 DR-234 규모 A 로 바꿨다(#211 · DR-211): 고객 20,000 → 50,000명, `run.warmup_days` 312 신설
#:     (총 396일 = 13개월). 나머지 값은 #206 이전과 같다.
EXPERIMENT_NOW = copy.deepcopy(PRE_206_EXPERIMENT)
del EXPERIMENT_NOW["rct"]["active_days"]
EXPERIMENT_NOW["run"] = {"num_customers": 50000, "profile": "reference", "warmup_days": 312}


def _model(**patch) -> dict:
    raw = copy.deepcopy(MODEL_NOW)
    for dotted, value in patch.items():
        *head, leaf = dotted.split("__")
        node = raw
        for key in head:
            node = node[key]
        if value is _DELETE:
            del node[leaf]
        else:
            node[leaf] = value
    return raw


_DELETE = object()


class TestSchema(unittest.TestCase):
    """스키마 — 의존성 없이 돈다."""

    def test_pre_206_values_pass_unchanged(self) -> None:
        self.assertEqual(MODEL_NOW, dc.validate(MODEL_NOW, dc.MODEL_SCHEMA, "t"))
        self.assertEqual(EXPERIMENT_NOW, dc.validate(EXPERIMENT_NOW, dc.EXPERIMENT_SCHEMA, "t"))

    def test_risk_baseline_must_be_explicit_and_predeclared(self):
        with self.assertRaises(dc.DecisionConfigError):
            dc.model_config_from(PRE_206_MODEL)
        for name in ("best", "rule_recency", True, None):
            with self.subTest(name=name), self.assertRaises(dc.DecisionConfigError):
                dc.model_config_from(_model(churn__risk_baseline_model=name))
        self.assertEqual("logistic_regression", dc.model_config_from(MODEL_NOW).churn.risk_baseline_model)

    def test_removed_active_days_is_rejected_not_ignored(self) -> None:
        """#234 — 옛 설정 파일의 `active_days` 가 조용히 무시되면 그 값이 아직 쓰인다고 믿게 된다.

        지금 판에 옛 키 하나만 되살려 시험한다 — #206 판 전체를 넣으면 그 뒤에 생긴 필수 키(#211
        `run.warmup_days`)의 누락이 먼저 잡혀 이 검사가 무엇을 막는지 흐려진다.
        """
        raw = copy.deepcopy(EXPERIMENT_NOW)
        raw["rct"]["active_days"] = PRE_206_EXPERIMENT["rct"]["active_days"]
        with self.assertRaises(dc.DecisionConfigError) as caught:
            dc.validate(raw, dc.EXPERIMENT_SCHEMA, "t")
        self.assertIn("active_days", str(caught.exception))

    def test_unknown_keys_are_rejected_at_every_level(self) -> None:
        cases = {
            "최상위": _model(extra=1),
            "섹션": _model(churn__cv_fold=5),                      # 오타 — 조용히 버려지면 기본값이 쓰인다
            "모델": _model(churn__models__xgboost={"n_estimators": 3}),
            "하이퍼파라미터": _model(churn__models__hist_gb__max_depth=3),
        }
        for label, raw in cases.items():
            with self.subTest(label), self.assertRaises(dc.DecisionConfigError) as caught:
                dc.validate(raw, dc.MODEL_SCHEMA, "model.yaml")
            self.assertIn("모르는 키", str(caught.exception))
            self.assertIn("model.yaml", str(caught.exception))
        with self.assertRaises(dc.DecisionConfigError) as caught:
            dc.validate(_model(churn__cv_fold=5), dc.MODEL_SCHEMA, "model.yaml")
        self.assertIn("cv_fold", str(caught.exception))

    def test_missing_keys_are_rejected(self) -> None:
        with self.assertRaises(dc.DecisionConfigError) as caught:
            dc.validate(_model(churn__shap_sample=_DELETE), dc.MODEL_SCHEMA, "t")
        self.assertIn("shap_sample", str(caught.exception))
        raw = copy.deepcopy(EXPERIMENT_NOW)
        del raw["ab_test"]
        with self.assertRaises(dc.DecisionConfigError):
            dc.validate(raw, dc.EXPERIMENT_SCHEMA, "t")

    def test_types_and_ranges(self) -> None:
        bad = {
            "bool 은 int 가 아니다": _model(churn__cv_folds=True),
            "5.0 은 int 가 아니다": _model(churn__cv_folds=5.0),
            "fold 1": _model(churn__cv_folds=1),
            "문자열 숫자": _model(churn__models__logistic_regression__C="0.5"),
            "C 0": _model(churn__models__logistic_regression__C=0),
            "분위수 1.0": _model(segmentation__clv_high_q=1.0),
            "n_jobs 0": _model(churn__models__random_forest__n_jobs=0),
            "class_weight": _model(churn__models__random_forest__class_weight="auto"),
            "early_stopping 'no'": _model(churn__models__hist_gb__early_stopping="no"),
            "schema_version 2": _model(schema_version=2),
            "섹션이 매핑이 아니다": _model(churn=[5, 3]),
            "nan": _model(clv__hist_gb__learning_rate=float("nan")),
        }
        for label, raw in bad.items():
            with self.subTest(label), self.assertRaises(dc.DecisionConfigError):
                dc.validate(raw, dc.MODEL_SCHEMA, "t")
        experiment_bad = {
            "control_share 0": ("rct", "control_share", 0),
            "alpha 1.5": ("ab_test", "alpha", 1.5),
            "seed -1": ("holdout", "development_seed", -1),
            "빈 프로파일": ("run", "profile", " "),
            "warmup 0": ("run", "warmup_days", 0),
            "warmup 문자열": ("run", "warmup_days", "312"),
        }
        for label, (section, key, value) in experiment_bad.items():
            raw = copy.deepcopy(EXPERIMENT_NOW)
            raw[section][key] = value
            with self.subTest(label), self.assertRaises(dc.DecisionConfigError):
                dc.validate(raw, dc.EXPERIMENT_SCHEMA, "t")

    def test_accepted_edge_values(self) -> None:
        out = dc.validate(_model(churn__models__hist_gb__l2_regularization=1), dc.MODEL_SCHEMA, "t")
        value = out["churn"]["models"]["hist_gb"]["l2_regularization"]
        self.assertIsInstance(value, float)  # float 칸의 정수는 float 로 받는다
        self.assertEqual(-1, dc.validate(MODEL_NOW, dc.MODEL_SCHEMA, "t")["churn"]["models"]
                         ["random_forest"]["n_jobs"])

    def test_error_is_a_config_error_with_exit_code_5(self) -> None:
        self.assertTrue(issubclass(dc.DecisionConfigError, ConfigError))
        self.assertEqual(5, dc.DecisionConfigError.exit_code)

    def test_built_objects_are_read_only(self) -> None:
        built = dc.model_config_from(MODEL_NOW)
        with self.assertRaises(TypeError):
            built.churn.models["hist_gb"]["max_iter"] = 1  # type: ignore[index]
        with self.assertRaises(dataclasses.FrozenInstanceError):
            built.churn.cv_folds = 3  # type: ignore[misc]


@unittest.skipUnless(cl.yaml_available(), NEEDS_YAML)
class TestRepositoryFiles(unittest.TestCase):
    """동일성 — 저장소의 config 가 #206 이전 코드 상수와 같다."""

    def test_model_config_equals_pre_206_constants(self) -> None:
        raw = cl.load_yaml(dc.MODEL_CONFIG)
        checked = dc.validate(raw, dc.MODEL_SCHEMA, str(dc.MODEL_CONFIG))
        self.assertEqual(MODEL_NOW, checked)
        previous = copy.deepcopy(checked)
        del previous["churn"]["risk_baseline_model"]
        self.assertEqual(PRE_206_MODEL, previous)

    def test_experiment_config_equals_pre_206_constants(self) -> None:
        raw = cl.load_yaml(dc.EXPERIMENT_CONFIG)
        self.assertEqual(EXPERIMENT_NOW, dc.validate(raw, dc.EXPERIMENT_SCHEMA, str(dc.EXPERIMENT_CONFIG)))

    def test_loaders_return_typed_objects_and_cache(self) -> None:
        model = dc.load_model_config()
        self.assertIs(model, dc.load_model_config())
        self.assertEqual(5, model.churn.cv_folds)
        self.assertEqual(0.6, model.segmentation["uplift_band_q"])
        experiment = dc.load_experiment_config()
        self.assertEqual(42, experiment.holdout.development_seed)
        self.assertEqual(0.5, experiment.rct.control_share)

    def test_file_errors_name_the_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            cases = {
                "없는 파일": base / "absent.yaml",
                "YAML 문법": base / "broken.yaml",
                "최상위 목록": base / "list.yaml",
                "모르는 키": base / "typo.yaml",
            }
            (base / "broken.yaml").write_text("churn: [1, 2\n", encoding="utf-8")
            (base / "list.yaml").write_text("- 1\n- 2\n", encoding="utf-8")
            text = dc.MODEL_CONFIG.read_text(encoding="utf-8").replace("  cv_folds: 5\n", "  cv_fold: 5\n", 1)
            self.assertIn("  cv_fold: 5\n", text)  # 오타 하나 — 무시되면 기본값이 쓰인다
            (base / "typo.yaml").write_text(text, encoding="utf-8")
            for label, path in cases.items():
                with self.subTest(label), self.assertRaises(dc.DecisionConfigError) as caught:
                    dc.load_model_config(path)
                self.assertIn(path.name, str(caught.exception))

    def test_missing_pyyaml_stops_instead_of_guessing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "model.yaml"
            path.write_text(dc.MODEL_CONFIG.read_text(encoding="utf-8"), encoding="utf-8")
            with mock.patch.object(cl, "yaml_available", return_value=False), \
                    self.assertRaises(dc.DecisionConfigError) as caught:
                dc.load_model_config(path)
        self.assertIn("PyYAML", str(caught.exception))


def _function(tree: ast.AST, name: str) -> ast.FunctionDef:
    return next(n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == name)


def _source(relative: str) -> ast.AST:
    return ast.parse((REPO_ROOT / relative).read_text(encoding="utf-8"))


def literal_hyperparameters(tree: ast.AST, function: str) -> list[str]:
    """``function`` 안에서 추정기(…Classifier · …Regressor · …Regression)에 상수로 넘긴 인자."""
    return [
        f"{kw.lineno} {kw.arg}={kw.value.value!r}"
        for node in ast.walk(_function(tree, function)) if isinstance(node, ast.Call)
        and getattr(node.func, "id", "").endswith(("Classifier", "Regressor", "Regression"))
        for kw in node.keywords if isinstance(kw.value, ast.Constant)
    ]


class TestNoConstantsWhereConfigIsRead(unittest.TestCase):
    """값이 config 한 곳에만 있다 — 읽는 자리에 숫자가 다시 박히지 않는다(AST · 의존성 없이)."""

    def test_estimator_constructors_take_no_literal_hyperparameters(self) -> None:
        for relative, name in (("src/decision/churn.py", "make_model"), ("src/decision/clv.py", "fit_clv")):
            with self.subTest(relative):
                self.assertEqual([], literal_hyperparameters(_source(relative), name),
                                 "하이퍼파라미터는 config/model_config.yaml 에서 온다")

    def test_scan_catches_a_planted_literal(self) -> None:
        """음성 대조 — 스캐너가 아무것도 못 잡으면 위 검사는 늘 통과한다."""
        planted = ast.parse(
            "def make_model(name, seed):\n"
            "    return RandomForestClassifier(**params, n_estimators=300, random_state=seed)\n")
        self.assertEqual(["2 n_estimators=300"], literal_hyperparameters(planted, "make_model"))

    def test_module_constants_are_read_from_config(self) -> None:
        expected = {
            "src/decision/churn.py": ("N_SPLITS", "INNER_SPLITS", "SHAP_SAMPLE"),
            "src/decision/segments.py": ("DEFAULT_THRESHOLDS",),
            "src/decision/ab_test.py": ("ALPHA", "POWER", "SRM_THRESHOLD"),
            "src/orchestration/run_sprint.py": ("RCT_CONTROL_SHARE",),
        }
        for relative, names in expected.items():
            tree = _source(relative)
            for name in names:
                assigned = [n.value for n in ast.walk(tree) if isinstance(n, (ast.Assign, ast.AnnAssign))
                            and any(getattr(t, "id", None) == name
                                    for t in (n.targets if isinstance(n, ast.Assign) else [n.target]))]
                with self.subTest(f"{relative}:{name}"):
                    self.assertEqual(1, len(assigned))
                    self.assertNotIsInstance(assigned[0], (ast.Constant, ast.Dict), "config 에서 읽어야 한다")

    def test_ab_test_defaults_are_names_not_numbers(self) -> None:
        tree = _source("src/decision/ab_test.py")
        for name in ("analyze_ab", "sample_size_two_proportions", "achieved_power", "srm_check",
                     "sample_size_two_means"):
            fn = _function(tree, name)
            args = fn.args.args[len(fn.args.args) - len(fn.args.defaults):] + fn.args.kwonlyargs
            defaults = list(fn.args.defaults) + [d for d in fn.args.kw_defaults if d is not None]
            numeric = [a.arg for a, d in zip(args, defaults)
                       if isinstance(d, ast.Constant) and isinstance(d.value, float)]
            with self.subTest(name):
                self.assertEqual([], numeric, "α · 검정력 · SRM 임계는 config/experiment_config.yaml 에서 온다")


@unittest.skipUnless(HAVE_ML and cl.yaml_available(), NEEDS_ML)
class TestCodeUsesConfig(unittest.TestCase):
    """배선 — #206 이전 코드가 만들던 것과 같은 추정기 · 같은 기본값이고, config 를 바꾸면 따라 바뀐다."""

    def test_churn_estimators_match_pre_206_construction(self) -> None:
        from sklearn.ensemble import HistGradientBoostingClassifier, RandomForestClassifier
        from sklearn.linear_model import LogisticRegression

        from src.decision import churn

        seed = 7
        before = {  # #206 이전 make_model 의 인자 그대로
            "logistic_regression": LogisticRegression(class_weight="balanced", max_iter=2000, C=0.5),
            "random_forest": RandomForestClassifier(n_estimators=300, min_samples_leaf=3,
                                                    class_weight="balanced_subsample", n_jobs=-1,
                                                    random_state=seed),
            "hist_gb": HistGradientBoostingClassifier(learning_rate=0.05, max_iter=300, max_leaf_nodes=15,
                                                      l2_regularization=1.0, class_weight="balanced",
                                                      early_stopping=False, random_state=seed),
        }
        steps = {"logistic_regression": 3, "random_forest": 2, "hist_gb": 2}
        for name, estimator in before.items():
            with self.subTest(name):
                built = churn.make_model(name, seed)
                self.assertEqual(steps[name], len(built.steps))
                self.assertIs(type(estimator), type(built[-1]))
                self.assertEqual(estimator.get_params(), built[-1].get_params())
        self.assertEqual((5, 3, 500), (churn.N_SPLITS, churn.INNER_SPLITS, churn.SHAP_SAMPLE))

    def test_changing_config_changes_the_estimator(self) -> None:
        from src.decision import churn

        models = {k: dict(v) for k, v in churn.CONFIG.models.items()}
        models["random_forest"]["n_estimators"] = 7
        changed = dataclasses.replace(churn.CONFIG, models=models)
        with mock.patch.object(churn, "CONFIG", changed):
            self.assertEqual(7, churn.make_model("random_forest", 0)[-1].n_estimators)
        self.assertEqual(300, churn.make_model("random_forest", 0)[-1].n_estimators)

    def test_clv_estimator_and_folds_match_pre_206(self) -> None:
        import numpy as np
        import pandas as pd
        from sklearn.ensemble import HistGradientBoostingRegressor

        from src.decision import clv

        rng = np.random.default_rng(0)
        X = pd.DataFrame({"a": rng.random(60), "b": rng.random(60)},
                         index=[f"C{i:08d}" for i in range(60)])
        model = clv.fit_clv(X, pd.Series(rng.poisson(3, 60).astype(float), index=X.index), seed=5)
        before = HistGradientBoostingRegressor(loss="poisson", learning_rate=0.05, max_iter=200, max_leaf_nodes=15,
                                               l2_regularization=1.0, min_samples_leaf=20, early_stopping=False,
                                               random_state=5)
        self.assertEqual(before.get_params(), model[-1].get_params())
        self.assertEqual(5, inspect.signature(clv.evaluate_clv).parameters["n_splits"].default)

    def test_segment_thresholds_and_ab_defaults(self) -> None:
        from src.decision import ab_test, segments

        self.assertEqual({"clv_high_q": 0.8, "churn_high_q": 0.5, "uplift_band_q": 0.6}, segments.DEFAULT_THRESHOLDS)
        params = inspect.signature(ab_test.analyze_ab).parameters
        self.assertEqual((0.05, 0.8), (params["alpha"].default, params["power"].default))
        self.assertEqual(0.001, inspect.signature(ab_test.srm_check).parameters["threshold"].default)
        self.assertEqual(0.05, inspect.signature(ab_test.achieved_power).parameters["alpha"].default)

    def test_run_sprint_reads_experiment_config(self) -> None:
        # 이 검사는 설정 배선만 본다. 실제 시뮬레이터 import가 필요하지 않다.
        import sys
        from tests.test_feature_sprint_table import _contract_runner
        rs = _contract_runner()
        try:
            self.assertEqual(0.5, rs.RCT_CONTROL_SHARE)
            args = rs.build_parser().parse_args(["--out", "x"])
            self.assertEqual((42, 50000, "reference", None),
                             (args.seed, args.customers, args.profile, args.warmup_days))
            self.assertFalse(hasattr(args, "active_days"), "#234 에서 없앤 RCT 모집단 창이 CLI 에 남아 있다")
            assignment = rs.rct_assign([f"C{i:08d}" for i in range(80)], 42)
            self.assertEqual(40, sum(1 for t in assignment.values() if t == "T0"))
        finally:
            sys.modules.pop(rs.__name__, None)

    def test_warmup_resolution_and_experiment_scale(self) -> None:
        """#211 · DR-211 — config warmup 은 config 프로파일에만 붙고, 실험 규모가 DR-234 규모 A 다."""
        import sys
        from tests.test_feature_sprint_table import _contract_runner
        rs = _contract_runner()
        try:
            warmup, basis = rs.resolve_warmup("reference", None)
            self.assertEqual(312, warmup)
            self.assertIn("run.warmup_days", basis)
            # 다른 프로파일은 그 프로파일의 권장값 — small 스모크가 312일을 돌지 않는다.
            self.assertEqual((180, "data_spec §2.2 프로파일 권장값"), rs.resolve_warmup("small", None))
            self.assertEqual((90, "data_spec §2.2 프로파일 권장값"), rs.resolve_warmup("smoke", None))
            # 인자가 언제나 이긴다(config 프로파일이어도).
            self.assertEqual((60, "--warmup-days 인자"), rs.resolve_warmup("small", 60))
            self.assertEqual((273, "--warmup-days 인자"), rs.resolve_warmup("reference", 273))
            # 권장값을 모르는 프로파일은 추측하지 않는다 — run() 이 warmup 단계에서 not_run.
            self.assertIsNone(rs.resolve_warmup("no-such-profile", None)[0])

            # DR-234 규모 A: 50,000명 · t1 = Day 312 · 총 396일(warmup + RCT 42 + 분기 42) = 13개월.
            run = rs.EXPERIMENT.run
            self.assertEqual((50000, 312), (run.num_customers, run.warmup_days))
            self.assertEqual(396, run.warmup_days + 2 * rs.LABEL_WINDOW_DAYS)
            # control_share 0.5 가 min(T, C) 를 가장 크게 만든다(DR-234 기각 표) — 바꾸면 규모를 다시 계산한다.
            self.assertEqual(0.5, rs.RCT_CONTROL_SHARE)
        finally:
            sys.modules.pop(rs.__name__, None)


if __name__ == "__main__":
    unittest.main()
