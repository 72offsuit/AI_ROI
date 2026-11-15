"""의사결정·실험 설정 로더 — ``config/model_config.yaml`` · ``config/experiment_config.yaml`` (이슈 #206).

SRS CFG-002 · CFG-003 · CQ-003("Path / Threshold / Hyperparameter / Budget 하드코딩 금지"), PRD NFR-06.

규칙
  - **스키마를 여기 선언하고 파일을 그것과 정확히 맞춰 읽는다.** 모르는 키 · 빠진 키 · 타입 · 범위가
    어긋나면 ``DecisionConfigError`` 로 멈춘다. 모르는 키를 무시하면 오타(``cv_fold``)가 조용히 버려지고
    코드는 다른 값으로 도는데 사람은 바꿨다고 믿는다 — 그래서 거부한다.
  - **값은 config 파일 한 곳에만 있다.** 이 모듈에도, 읽는 모듈에도 기본값을 두지 않는다. 두 벌이면
    어긋난다. #206 이전 코드 상수와 같은 값인지는 ``tests/test_decision_config.py`` 가 고정한다.
  - YAML 은 ``src.measurement.config_loader.load_yaml`` 로만 읽는다 — PyYAML 접점을 한 곳에 둔다
    (``tests/test_neutrality.py`` · ``yaml.safe_load`` 만). 이 모듈은 표준 라이브러리만 import 한다.
  - bool 은 int 가 아니다(``True == 1`` 이지만 ``cv_folds: true`` 는 거부). float 칸의 정수(``1``)는
    float 로 받는다.

한계 — PyYAML 은 **중복 키를 마지막 값으로 덮는다**(``cv_folds: 5`` 다음 줄 ``cv_folds: 3`` 은 3).
``load_yaml`` 을 거쳐 읽으므로 여기서는 잡지 못한다. 리뷰가 본다.

읽는 곳 (#206 시점)
  model_config       src/decision/churn.py · clv.py · segments.py
  experiment_config  src/orchestration/run_sprint.py (실행 기본값 · 탐색 RCT) · src/decision/ab_test.py
"""

from __future__ import annotations

import functools
import math
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Any, Mapping

from src.measurement.errors import ConfigError

REPO_ROOT = Path(__file__).resolve().parents[2]
MODEL_CONFIG = REPO_ROOT / "config" / "model_config.yaml"
EXPERIMENT_CONFIG = REPO_ROOT / "config" / "experiment_config.yaml"
SCHEMA_VERSION = 1


class DecisionConfigError(ConfigError):
    """모델·실험 config 를 읽을 수 없거나 스키마와 다르다. 폴백하지 않는다(종료 코드 5)."""


# ── 스키마 ───────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class Rule:
    """잎 값 하나의 규칙. ``kind`` 는 int · float · bool · choice · text."""

    kind: str
    lo: float | None = None
    hi: float | None = None
    lo_open: bool = False
    hi_open: bool = False
    also: tuple[Any, ...] = ()       # 범위 밖이어도 받는 값 (n_jobs = -1)
    choices: tuple[str, ...] = ()
    item: "Rule | None" = None       # kind == "list" 일 때 각 원소의 규칙 (#215 튜닝 격자)

    def describe(self) -> str:
        if self.kind == "list":
            return f"비어 있지 않은 목록, 원소는 {self.item.describe()}, 중복 없음"
        if self.kind == "choice":
            return f"다음 중 하나: {list(self.choices)}"
        if self.kind in ("bool", "text"):
            return {"bool": "true / false", "text": "비어 있지 않은 문자열"}[self.kind]
        left = "(" if self.lo_open else "["
        right = ")" if self.hi_open else "]"
        lo = "-∞" if self.lo is None else self.lo
        hi = "+∞" if self.hi is None else self.hi
        extra = f" 또는 {list(self.also)}" if self.also else ""
        return f"{self.kind} {left}{lo}, {hi}{right}{extra}"

    def check(self, value: Any) -> Any:
        """통과하면 정규화한 값(float 칸의 int → float), 아니면 ``ValueError``(사유)."""
        if self.kind == "list":
            if not isinstance(value, (list, tuple)) or not value:  # YAML 은 list, 코드로 만든 설정은 tuple 일 수 있다
                raise ValueError("비어 있지 않은 목록이어야 한다")
            checked = tuple(self.item.check(v) for v in value)
            if len(set(checked)) != len(checked):
                raise ValueError("목록에 같은 값이 두 번 있다")
            return checked
        if self.kind == "bool":
            if type(value) is not bool:
                raise ValueError("bool 이어야 한다")
            return value
        if self.kind == "choice":
            if not isinstance(value, str) or value not in self.choices:
                raise ValueError("허용 값이 아니다")
            return value
        if self.kind == "text":
            if not isinstance(value, str) or not value.strip():
                raise ValueError("비어 있지 않은 문자열이어야 한다")
            return value
        if isinstance(value, bool):  # bool 은 int 의 하위형이다 — 숫자로 받지 않는다
            raise ValueError("bool 은 숫자가 아니다")
        if self.kind == "int":
            if type(value) is not int:
                raise ValueError("정수여야 한다")
        elif self.kind == "float":
            if not isinstance(value, (int, float)):
                raise ValueError("숫자여야 한다")
            value = float(value)
            if not math.isfinite(value):
                raise ValueError("유한한 수여야 한다")
        else:  # pragma: no cover — 스키마 선언 오류
            raise TypeError(f"알 수 없는 규칙 종류: {self.kind}")
        if value in self.also:
            return value
        if self.lo is not None and (value < self.lo or (self.lo_open and value == self.lo)):
            raise ValueError("범위 밖이다")
        if self.hi is not None and (value > self.hi or (self.hi_open and value == self.hi)):
            raise ValueError("범위 밖이다")
        return value


def _int(lo: int | None = None, hi: int | None = None, also: tuple[int, ...] = ()) -> Rule:
    return Rule("int", lo=lo, hi=hi, also=also)


def _float(lo: float | None = None, hi: float | None = None, *, lo_open: bool = False,
           hi_open: bool = False) -> Rule:
    return Rule("float", lo=lo, hi=hi, lo_open=lo_open, hi_open=hi_open)


_BOOL = Rule("bool")
_TEXT = Rule("text")
_QUANTILE = _float(0.0, 1.0, lo_open=True, hi_open=True)
_PROBABILITY = _float(0.0, 1.0, lo_open=True, hi_open=True)


def _choice(*values: str) -> Rule:
    return Rule("choice", choices=values)


def _list(item: Rule) -> Rule:
    """튜닝 격자 한 축 — 비어 있지 않고 중복 없는 목록. 원소마다 ``item`` 규칙을 지킨다(#215)."""
    return Rule("list", item=item)


#: config/model_config.yaml. 하이퍼파라미터 키는 sklearn 생성자 인자 이름 그대로다(그대로 ``**`` 로 넘긴다).
#: 새 키를 받으려면 여기에 먼저 선언한다 — 선언 없는 키는 거부된다.
MODEL_SCHEMA: Mapping[str, Any] = {
    "schema_version": _int(SCHEMA_VERSION, SCHEMA_VERSION),
    "churn": {
        "risk_baseline_model": _choice("logistic_regression", "random_forest", "hist_gb"),
        "cv_folds": _int(2),
        "threshold_inner_folds": _int(2),
        "shap_sample": _int(1),
        "models": {
            "logistic_regression": {
                "C": _float(0.0, lo_open=True),
                "max_iter": _int(1),
                "class_weight": _choice("balanced"),
            },
            "random_forest": {
                "n_estimators": _int(1),
                "min_samples_leaf": _int(1),
                "class_weight": _choice("balanced", "balanced_subsample"),
                "n_jobs": _int(1, also=(-1,)),
            },
            "hist_gb": {
                "learning_rate": _float(0.0, 1.0, lo_open=True),
                "max_iter": _int(1),
                "max_leaf_nodes": _int(2),
                "l2_regularization": _float(0.0),
                "class_weight": _choice("balanced"),
                "early_stopping": _BOOL,
            },
            # #215 — FR-14. 키는 xgboost · lightgbm 의 sklearn 생성자 인자 이름 그대로다.
            "xgboost": {
                "n_estimators": _int(1),
                "learning_rate": _float(0.0, 1.0, lo_open=True),
                "max_depth": _int(1),
                "subsample": _float(0.0, 1.0, lo_open=True),
                "colsample_bytree": _float(0.0, 1.0, lo_open=True),
                "reg_lambda": _float(0.0),
                "tree_method": _choice("hist"),
                "n_jobs": _int(1, also=(-1,)),
            },
            "lightgbm": {
                "n_estimators": _int(1),
                "learning_rate": _float(0.0, 1.0, lo_open=True),
                "num_leaves": _int(2),
                "min_child_samples": _int(1),
                "subsample": _float(0.0, 1.0, lo_open=True),
                "subsample_freq": _int(0),
                "colsample_bytree": _float(0.0, 1.0, lo_open=True),
                "reg_lambda": _float(0.0),
                "class_weight": _choice("balanced"),
                "deterministic": _BOOL,
                "force_row_wise": _BOOL,
                "n_jobs": _int(1, also=(-1,)),
                "verbose": _int(-1),
            },
        },
        # #215 — Validation 튜닝(Grid). 각 축의 후보를 곱한 조합을 검증 데이터로만 비교한다(시험 · 홀드아웃 미사용).
        "tuning": {
            "enabled": _BOOL,
            "metric": _choice("roc_auc", "pr_auc"),
            "grids": {
                "random_forest": {"min_samples_leaf": _list(_int(1)), "n_estimators": _list(_int(1))},
                "hist_gb": {"learning_rate": _list(_float(0.0, 1.0, lo_open=True)),
                            "max_leaf_nodes": _list(_int(2))},
                "xgboost": {"max_depth": _list(_int(1)),
                            "learning_rate": _list(_float(0.0, 1.0, lo_open=True))},
                "lightgbm": {"num_leaves": _list(_int(2)),
                             "learning_rate": _list(_float(0.0, 1.0, lo_open=True))},
            },
        },
    },
    "clv": {
        "cv_folds": _int(2),
        "hist_gb": {
            "loss": _choice("poisson", "squared_error", "absolute_error", "gamma"),
            "learning_rate": _float(0.0, 1.0, lo_open=True),
            "max_iter": _int(1),
            "max_leaf_nodes": _int(2),
            "l2_regularization": _float(0.0),
            "min_samples_leaf": _int(1),
            "early_stopping": _BOOL,
        },
        # #217 2부 — 12개월 CLV(BG/NBD + Gamma-Gamma)
        "lifetime": {
            "horizon_months": _int(1),
            "annual_discount_rate": _float(0.0, 1.0, hi_open=True),
            "discount_sensitivity": _list(_float(0.0, lo_open=True)),
            "high_value_share": _float(0.0, 1.0, lo_open=True, hi_open=True),
        },
    },
    # #217 3부 — Uplift 메타러너. DR-206 이 미룬 상수 4개 + Validation 규제 튜닝(DR-217-uplift-tuning)
    "uplift": {
        "min_arm_n": _int(2),
        "primary_arm": _choice("T1", "T2", "T3", "T4"),
        "validation_size": _float(0.0, 1.0, lo_open=True, hi_open=True),
        "base_learner": {
            "max_iter": _int(1),
            "learning_rate": _float(0.0, 1.0, lo_open=True),
            "max_depth": _int(1),
            "min_samples_leaf": _int(1),
            "l2_regularization": _float(0.0),
        },
        "tuning": {
            "enabled": _BOOL,
            "metric": _choice("qini"),
            "grid": {"max_depth": _list(_int(1)), "min_samples_leaf": _list(_int(1))},
        },
    },
    "segmentation": {
        "clv_high_q": _QUANTILE,
        "churn_high_q": _QUANTILE,
        "uplift_band_q": _QUANTILE,
    },
}

#: config/experiment_config.yaml.
EXPERIMENT_SCHEMA: Mapping[str, Any] = {
    "schema_version": _int(SCHEMA_VERSION, SCHEMA_VERSION),
    "run": {
        "num_customers": _int(1),
        "profile": _TEXT,
        "warmup_days": _int(1),
    },
    "holdout": {
        "development_seed": _int(0),
    },
    "rct": {
        "control_share": _PROBABILITY,
    },
    "ab_test": {
        "alpha": _PROBABILITY,
        "target_power": _PROBABILITY,
        "srm_p_threshold": _PROBABILITY,
    },
}


def _fail(source: str, message: str) -> DecisionConfigError:
    return DecisionConfigError(f"{source}: {message}")


def validate(raw: Any, schema: Mapping[str, Any], source: str, where: str = "") -> dict[str, Any]:
    """``raw`` 를 ``schema`` 와 정확히 맞춘다. 통과하면 정규화한 dict, 아니면 ``DecisionConfigError``.

    오류 메시지는 셋을 담는다 — 어느 키가 · 왜 · 무엇을 하면 되는가.
    """
    label = where or "(최상위)"
    if not isinstance(raw, Mapping):
        raise _fail(source, f"{label} 는 `키: 값` 매핑이어야 한다 (읽은 타입: {type(raw).__name__})")
    unknown = sorted(str(k) for k in raw if k not in schema)
    if unknown:
        raise _fail(
            source,
            f"{label} 에 모르는 키가 있다: {unknown} — 오타라면 그 값은 아무 데도 쓰이지 않는다(조용한 무시를 "
            f"막으려고 거부한다). 허용 키: {sorted(schema)}. 새 설정이면 src/decision/config.py 스키마에 먼저 "
            "선언한다",
        )
    missing = sorted(k for k in schema if k not in raw)
    if missing:
        raise _fail(
            source,
            f"{label} 에 필수 키가 없다: {missing} — 기본값으로 대체하지 않는다(값은 config 한 곳에만 있다). "
            "그 키를 추가한다",
        )
    out: dict[str, Any] = {}
    for key, rule in schema.items():
        path = f"{where}.{key}" if where else key
        if isinstance(rule, Mapping):
            out[key] = validate(raw[key], rule, source, path)
            continue
        try:
            out[key] = rule.check(raw[key])
        except ValueError as reason:
            raise _fail(
                source,
                f"{path} = {raw[key]!r} — {reason}. 허용: {rule.describe()}",
            ) from None
    return out


def _frozen(mapping: Mapping[str, Any]) -> Mapping[str, Any]:
    return MappingProxyType({k: _frozen(v) if isinstance(v, Mapping) else v for k, v in mapping.items()})


def _read(path: Path, label: str) -> Mapping[str, Any]:
    if not path.is_file():
        raise _fail(
            str(path),
            f"{label} 파일이 없다 — 기본값으로 돌지 않는다(값은 이 파일 한 곳에만 있다). 저장소 루트의 "
            f"config/ 에 있어야 한다",
        )
    from src.measurement.config_loader import load_yaml  # PyYAML 의 유일한 접점

    try:
        return load_yaml(path)
    except ConfigError as error:  # PyYAML 미설치 · 최상위가 매핑 아님
        raise DecisionConfigError(str(error)) from error
    except Exception as error:  # noqa: BLE001 — yaml.YAMLError 를 여기서 이름으로 잡지 않는다(접점 하나)
        raise _fail(
            str(path), f"YAML 로 해석할 수 없다: {type(error).__name__}: {error} — 들여쓰기 · 콜론을 확인한다",
        ) from error


# ── 설정 객체 ────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class ChurnConfig:
    risk_baseline_model: str
    cv_folds: int
    threshold_inner_folds: int
    shap_sample: int
    #: 모델 이름 → sklearn 생성자 인자(읽기 전용). random_state 는 실행 seed 에서 온다.
    models: Mapping[str, Mapping[str, Any]]
    #: #215 — {enabled, metric, grids: {모델: {인자: (후보, …)}}}. 검증 데이터로만 고른다.
    tuning: Mapping[str, Any]


@dataclass(frozen=True)
class ClvConfig:
    cv_folds: int
    hist_gb: Mapping[str, Any]
    #: #217 — {horizon_months, annual_discount_rate, discount_sensitivity, high_value_share}
    lifetime: Mapping[str, Any]


@dataclass(frozen=True)
class UpliftConfig:
    min_arm_n: int
    primary_arm: str
    validation_size: float
    #: HistGradientBoostingRegressor 인자(읽기 전용) — 튜닝 격자의 현행값. random_state 는 seed 에서 온다.
    base_learner: Mapping[str, Any]
    #: #217 3부 — {enabled, metric, grid: {인자: (후보, …)}}. Validation Qini 로만 고른다.
    tuning: Mapping[str, Any]


@dataclass(frozen=True)
class ModelConfig:
    path: Path
    churn: ChurnConfig
    clv: ClvConfig
    uplift: UpliftConfig
    #: segments.DEFAULT_THRESHOLDS 의 키와 같다.
    segmentation: Mapping[str, float]


@dataclass(frozen=True)
class RunDefaults:
    num_customers: int
    profile: str
    #: ``profile`` 로 돌 때의 warmup(= t1 일수). 다른 프로파일에는 쓰지 않는다 — ``run_sprint.resolve_warmup``.
    warmup_days: int


@dataclass(frozen=True)
class HoldoutConfig:
    development_seed: int


@dataclass(frozen=True)
class RctConfig:
    control_share: float


@dataclass(frozen=True)
class AbTestConfig:
    alpha: float
    target_power: float
    srm_p_threshold: float


@dataclass(frozen=True)
class ExperimentConfig:
    path: Path
    run: RunDefaults
    holdout: HoldoutConfig
    rct: RctConfig
    ab_test: AbTestConfig


def model_config_from(raw: Any, source: str = "<model_config>", path: Path = MODEL_CONFIG) -> ModelConfig:
    """매핑 → ``ModelConfig``. 파일 없이 검증할 때 쓴다(테스트 · 의존성 없는 환경)."""
    v = validate(raw, MODEL_SCHEMA, source)
    churn, clv = v["churn"], v["clv"]
    return ModelConfig(
        path=path,
        churn=ChurnConfig(
            risk_baseline_model=churn["risk_baseline_model"],
            cv_folds=churn["cv_folds"],
            threshold_inner_folds=churn["threshold_inner_folds"],
            shap_sample=churn["shap_sample"],
            models=_frozen(churn["models"]),
            tuning=_frozen(churn["tuning"]),
        ),
        clv=ClvConfig(cv_folds=clv["cv_folds"], hist_gb=_frozen(clv["hist_gb"]), lifetime=_frozen(clv["lifetime"])),
        uplift=UpliftConfig(min_arm_n=v["uplift"]["min_arm_n"], primary_arm=v["uplift"]["primary_arm"],
                            validation_size=v["uplift"]["validation_size"],
                            base_learner=_frozen(v["uplift"]["base_learner"]), tuning=_frozen(v["uplift"]["tuning"])),
        segmentation=_frozen(v["segmentation"]),
    )


def experiment_config_from(raw: Any, source: str = "<experiment_config>",
                           path: Path = EXPERIMENT_CONFIG) -> ExperimentConfig:
    """매핑 → ``ExperimentConfig``."""
    v = validate(raw, EXPERIMENT_SCHEMA, source)
    return ExperimentConfig(
        path=path,
        run=RunDefaults(**v["run"]),
        holdout=HoldoutConfig(**v["holdout"]),
        rct=RctConfig(**v["rct"]),
        ab_test=AbTestConfig(**v["ab_test"]),
    )


@functools.lru_cache(maxsize=8)
def load_model_config(path: Path = MODEL_CONFIG) -> ModelConfig:
    """``config/model_config.yaml`` 을 읽어 검증한다. 같은 경로는 한 번만 읽는다(프로세스 수명)."""
    path = Path(path)
    return model_config_from(_read(path, "모델 config"), str(path), path)


@functools.lru_cache(maxsize=8)
def load_experiment_config(path: Path = EXPERIMENT_CONFIG) -> ExperimentConfig:
    """``config/experiment_config.yaml`` 을 읽어 검증한다. 같은 경로는 한 번만 읽는다(프로세스 수명)."""
    path = Path(path)
    return experiment_config_from(_read(path, "실험 config"), str(path), path)
