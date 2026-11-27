"""Churn 예측 — Baseline 2 종 vs 제안 2 종 평가 (스프린트 1, 이슈 #144).

  baseline  `rule_recency`         마지막 구매 후 경과일 ≥ 임계 → 이탈. 임계는 학습 데이터에서만
            `logistic_regression`  대치·절단·표준화 + 로지스틱 (class_weight=balanced)
  proposed  `random_forest`        (class_weight=balanced_subsample)
            `hist_gb`              HistGradientBoosting (class_weight=balanced)

평가: Stratified K-Fold(``config/model_config.yaml`` churn.cv_folds, 기본 5). fold 마다 ROC-AUC · PR-AUC ·
F1 · Lift@10% 를 구해 mean/std. 하이퍼파라미터 · fold 수도 그 파일에서 온다(#206).
  - **F1 임계는 학습 fold 에서만 정한다** — 학습 fold 내부 OOF(churn.threshold_inner_folds, 기본 3) 확률에서
    F1 최대 임계.
    (학습 fold 의 in-sample 확률로 정하면 숲 모형은 과신해 임계가 무의미해진다.)
  - 대치·이상치 절단(`make_preprocessor`)은 파이프라인 안에서 학습 fold 로만 fit 한다.
  - Lift@10% = 검증 fold 상위 10% 의 이탈률 / 검증 fold 이탈률.

★ 이 모듈은 Test/Holdout 을 보지 않는다. 시간 홀드아웃은 `evaluate_temporal_holdout` 이
  **확정 모델 1 회 평가** 용으로 따로 있다 — 그 결과로 모델을 고치면 Holdout 이 아니다.
"""

from __future__ import annotations

import functools
import math
import hashlib
import json
from dataclasses import dataclass, field
from typing import Any, Callable, Mapping

import numpy as np
import pandas as pd

from src.decision.config import load_model_config
from src.decision.features.sprint_table import LABEL_DEF, make_preprocessor, model_columns

BASELINES = ("rule_recency", "logistic_regression")
#: #215 — XGBoost · LightGBM 추가(SRS FR-14). 모두 같은 전처리 파이프라인 안에서 학습한다.
PROPOSED = ("random_forest", "hist_gb", "xgboost", "lightgbm")
MODEL_NAMES = BASELINES + PROPOSED
#: config/model_config.yaml `churn` (#206). 값은 그 파일 한 곳에만 있다 — 여기에 숫자를 다시 쓰지 않는다.
CONFIG = load_model_config().churn
N_SPLITS = CONFIG.cv_folds
INNER_SPLITS = CONFIG.threshold_inner_folds
SHAP_SAMPLE = CONFIG.shap_sample
#: OpenMP 스레드 상한(#215) — `uplift.py` 와 같은 이유: 작은 모델을 여러 번 학습할 때 스레드 경합으로 몇 배씩
#: 느려진다(uplift 2,500건 27 s → 3.5 s 실측, churn 은 hist_gb 1회 학습 750행 5 s). 결과 값은 스레드 수와 무관하다.
N_THREADS: int | None = 1


def _limited_threads(fn):
    """학습 · 평가 진입점을 OpenMP 스레드 상한 안에서 돌린다. threadpoolctl 은 scikit-learn 의 필수 의존성이다."""
    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        from threadpoolctl import threadpool_limits

        with threadpool_limits(limits=N_THREADS, user_api="openmp"):
            return fn(*args, **kwargs)
    return wrapper


# ── 모델 ────────────────────────────────────────────────────────────────────

class RecencyRule:
    """`recency`(마지막 구매 후 경과일) 하나만 보는 규칙 기준선.

    구매 이력이 없으면(NaN) "가장 오래 전" 으로 본다 — 학습 데이터 최대값보다 크게 둔다.
    점수는 학습 데이터 경험분포(ECDF)로 [0,1] 에 단조 사상한다(순위만 의미가 있다).
    이진 판정 임계는 `fit` 이 학습 데이터에서 F1 최대인 경과일로 정한다(`threshold_days_`).
    """

    feature = "recency"

    def __init__(self) -> None:
        self.threshold_days_: float | None = None
        self.reference_: np.ndarray | None = None
        self.fill_: float | None = None

    def _days(self, X: pd.DataFrame) -> np.ndarray:
        days = np.asarray(X[self.feature], dtype=float)
        return np.where(np.isnan(days), self.fill_, days)

    def fit(self, X: pd.DataFrame, y) -> RecencyRule:
        raw = np.asarray(X[self.feature], dtype=float)
        finite = raw[~np.isnan(raw)]
        self.fill_ = (float(finite.max()) if finite.size else 0.0) + 1.0
        days = self._days(X)
        self.reference_ = np.sort(days)
        self.threshold_days_ = _best_f1_threshold(np.asarray(y), days)
        return self

    def predict_proba(self, X: pd.DataFrame) -> np.ndarray:
        days = self._days(X)
        p = np.searchsorted(self.reference_, days, side="right") / len(self.reference_)
        return np.column_stack([1 - p, p])


def make_model(name: str, seed: int, overrides: Mapping[str, Any] | None = None):
    """이름 → 미학습 추정기. 대치·절단은 파이프라인 안(학습 데이터로만 fit).

    하이퍼파라미터는 ``CONFIG.models[name]``(config/model_config.yaml), ``random_state`` 는 ``seed`` 다.
    ``overrides`` 는 Validation 튜닝이 고른 값(#215) — config 격자 안의 값만 들어온다.
    """
    from sklearn.ensemble import HistGradientBoostingClassifier, RandomForestClassifier
    from sklearn.linear_model import LogisticRegression
    from sklearn.pipeline import make_pipeline
    from sklearn.preprocessing import StandardScaler

    if name == "rule_recency":
        return RecencyRule()
    if name not in CONFIG.models:
        raise ValueError(f"알 수 없는 모델: {name!r} (허용: {MODEL_NAMES})")
    params = {**CONFIG.models[name], **(overrides or {})}
    if name == "logistic_regression":
        return make_pipeline(make_preprocessor(), StandardScaler(), LogisticRegression(**params))
    if name == "random_forest":
        return make_pipeline(make_preprocessor(), RandomForestClassifier(**params, random_state=seed))
    if name == "hist_gb":
        return make_pipeline(make_preprocessor(), HistGradientBoostingClassifier(**params, random_state=seed))
    if name == "xgboost":
        from xgboost import XGBClassifier

        return make_pipeline(make_preprocessor(), XGBClassifier(**params, random_state=seed))
    if name == "lightgbm":
        from lightgbm import LGBMClassifier

        return make_pipeline(make_preprocessor(), LGBMClassifier(**params, random_state=seed))
    raise ValueError(f"알 수 없는 모델: {name!r} (허용: {MODEL_NAMES})")


#: 별도 패키지가 필요한 모델 → import 이름 (#215). 설치돼 있지 않으면 그 모델만 비교에서 빠지고 사유가 남는다.
OPTIONAL_PACKAGES = {"xgboost": "xgboost", "lightgbm": "lightgbm"}


def model_unavailable(name: str) -> str | None:
    """모델을 만들 수 없는 사유 — 있으면 문자열, 없으면 None. 조용히 건너뛰지 않고 결과에 적는다.

    ① 패키지 미설치(``find_spec``)뿐 아니라 ② **설치됐지만 불러오지 못함**도 사유다 — 예: macOS 에 OpenMP 런타임
    (libomp)이 없으면 ``import xgboost`` 는 ``XGBoostError``, ``import lightgbm`` 은 ``OSError`` 로 실패한다(PR #281
    리뷰 R1). **import 시점의 실패만** 환경 사유로 분류한다 — 학습 · 예측 중 오류는 삼키지 않고 그대로 올라간다.
    """
    import importlib
    import importlib.util

    package = OPTIONAL_PACKAGES.get(name)
    if not package:
        return None
    if importlib.util.find_spec(package) is None:
        return f"{package} 미설치 — pip install -r requirements.txt (requirements.txt 에 고정돼 있다)"
    try:
        importlib.import_module(package)
    except Exception as error:  # 공유 라이브러리 로드 실패 등 — import 시점만(위 docstring)
        return (f"{package} 를 불러오지 못한다({type(error).__name__}: {error}) — 설치는 됐다. "
                "macOS 는 OpenMP 런타임이 필요하다: brew install libomp")[:400]
    return None


def _kind(name: str) -> str:
    return "baseline" if name in BASELINES else "proposed"


def make_risk_model_factory(seed: int = 0):
    """#179 M: 설정으로 사전 고정한 미학습 모델. 평가 결과·최종 Churn 모델을 받지 않는다."""
    name = CONFIG.risk_baseline_model
    def factory():
        from src.measurement.schema import FEATURE_FORBIDDEN_FIELDS, FORBIDDEN_FIELD_NAMES, FEATURE_FORBIDDEN_EVENT_TYPES
        class RiskEstimator:
            def fit(self, X, y):
                forbidden = (FEATURE_FORBIDDEN_FIELDS | FORBIDDEN_FIELD_NAMES | FEATURE_FORBIDDEN_EVENT_TYPES
                             | {"customer_id", "index_date", "timestamp", "label", "retention"})
                if (not X.columns.is_unique or any(c in forbidden or str(c).endswith("_post_t0") for c in X.columns)):
                    raise ValueError("위험도 입력에 금지·정답·중복 Feature가 있다")
                self.columns_ = model_columns(X)
                self.estimator_ = make_model(name, seed)
                self.estimator_.fit(X[self.columns_], y)
                self.classes_ = self.estimator_.classes_
                return self
            def predict_proba(self, X):
                return self.estimator_.predict_proba(X[self.columns_])
        return RiskEstimator()
    factory.specification = {"name": name, "parameters": dict(CONFIG.models[name]),
                             "seed": seed, "selection": "predeclared_config_no_data_selection",
                             "feature_policy": "exclude_aliases_reject_forbidden_and_post_t0"}
    return factory


def temporal_population_audit(X_train, y_train, X_test, y_test, *,
                              training_treatment=None, evaluation_prior_treatment=None) -> dict:
    """실제 입력의 고객·결손·구성 감사. 새 분할을 만들거나 고객을 사후 재선정하지 않는다."""
    def cohort(X, y, treatment):
        values = y["churn"] if isinstance(y, pd.DataFrame) else y
        values = values.reindex(X.index) if isinstance(values, pd.Series) else pd.Series(values, index=X.index)
        good = values.notna()
        ids = X.index[good]
        if not X.index.is_unique or X.index.hasnans:
            raise ValueError("모집단 감사의 고객 ID는 고유하고 결손이 없어야 한다")
        digest = hashlib.sha256(json.dumps(sorted(map(str, ids)), ensure_ascii=False, separators=(",", ":")).encode()).hexdigest()
        groups = treatment.reindex(ids) if isinstance(treatment, pd.Series) else None
        return {"n_input": len(X), "n_labeled": len(ids), "n_label_missing": int((~good).sum()),
                "ids_sha256": digest, "n_rows_with_feature_missing": int(X.loc[ids].isna().any(axis=1).sum()),
                "feature_missing_cells": {str(k): int(v) for k, v in X.loc[ids].isna().sum().items() if v},
                "label_counts": {str(k): int(v) for k, v in values[good].value_counts().items()},
                "treatment_counts": None if groups is None else {str(k): int(v) for k, v in groups.value_counts().items()},
                "n_prior_assignment_missing": None if groups is None else int(groups.isna().sum())}, ids
    train, train_ids = cohort(X_train, y_train, training_treatment)
    test, test_ids = cohort(X_test, y_test, evaluation_prior_treatment)
    return {"training_and_selection": train, "future_evaluation": test,
            "intersection_n": len(train_ids.intersection(test_ids)),
            "evaluation_not_in_training_n": len(test_ids.difference(train_ids)),
            "reporting_scope": "기존 고객의 미래 시점 성능",
            "split_compliance": "not_established_by_this_audit",
            "training_population": "실제 학습·선택 입력(현재 runner: Eligible(t1)의 RCT T0군·표본 제한 후)",
            "evaluation_population": "Feature(t2) 고객의 S0 관측 라벨 — Eligible(t2) 집계와 별개"}


# ── 지표 ────────────────────────────────────────────────────────────────────

def _best_f1_threshold(y: np.ndarray, score: np.ndarray) -> float:
    """F1 최대 임계(점수 ≥ 임계 → 1). 양성이 없으면 +inf (아무도 양성으로 찍지 않는다)."""
    y = np.asarray(y).astype(int)
    if y.sum() == 0:
        return math.inf
    order = np.argsort(-score, kind="mergesort")
    s, t = score[order], y[order]
    tp = np.cumsum(t)
    k = np.arange(1, len(t) + 1)
    f1 = 2 * tp / (k + t.sum())
    # 같은 점수 묶음의 마지막 위치에서만 자를 수 있다
    last_of_tie = np.r_[s[1:] != s[:-1], True]
    f1 = np.where(last_of_tie, f1, -1)
    best = int(np.argmax(f1))
    return float(s[best])


def lift_at(y: np.ndarray, score: np.ndarray, frac: float = 0.10) -> float:
    y = np.asarray(y).astype(int)
    base = y.mean()
    if base == 0:
        return float("nan")
    k = max(1, int(math.ceil(len(y) * frac)))
    top = np.argsort(-score, kind="mergesort")[:k]
    return float(y[top].mean() / base)


def capture_at(y: np.ndarray, score: np.ndarray, frac: float = 0.10) -> float:
    """포착률 — 점수 상위 ``frac`` 고객이 전체 이탈자 중 몇 %를 담나(SRS ML-009). 이탈자가 없으면 NaN."""
    y = np.asarray(y).astype(int)
    positives = int(y.sum())
    if positives == 0:
        return float("nan")
    k = max(1, int(math.ceil(len(y) * frac)))
    top = np.argsort(-np.asarray(score, dtype=float), kind="mergesort")[:k]
    return float(y[top].sum() / positives)


#: SRS ML-009 — 상위 리프트 · 포착률을 내는 대상 비율.
TOP_SHARES = (0.10, 0.20, 0.30)


def classification_report(y, score, predicted=None, *, threshold: float | None = None,
                          threshold_unit: str = "probability", probability: bool = True) -> dict:
    """SRS ML-009 — 혼동행렬(운영 임계) · 상위 10/20/30% 리프트 · 포착률 · 확률 분포(구간별 고객 수).

    ``predicted`` 가 없으면 ``score >= threshold`` 로 판정한다. 규칙 기준선처럼 점수가 확률이 아니면
    ``probability=False`` — 확률 분포를 싣지 않는다(None). 리프트 · 포착률은 점수 **순서**만 쓴다.
    """
    y = np.asarray(y).astype(int)
    s = np.asarray(score, dtype=float)
    if predicted is None:
        if threshold is None:
            raise ValueError("predicted 또는 threshold 가 필요하다")
        predicted = s >= threshold
    pred = np.asarray(predicted).astype(bool)
    tp = int((pred & (y == 1)).sum())
    fp = int((pred & (y == 0)).sum())
    fn = int((~pred & (y == 1)).sum())
    tn = int((~pred & (y == 0)).sum())
    top = [{"share": share, "n_top": max(1, int(math.ceil(len(y) * share))) if len(y) else 0,
            "lift": lift_at(y, s, share) if len(y) else float("nan"),
            "capture": capture_at(y, s, share) if len(y) else float("nan")} for share in TOP_SHARES]
    distribution = ([{"low": row["low"], "high": row["high"], "n": row["n"]} for row in calibration(y, s)["bins"]]
                    if probability else None)
    return {"n": int(len(y)), "positives": int(y.sum()),
            "threshold": None if threshold is None else float(threshold), "threshold_unit": threshold_unit,
            "confusion_matrix": {"tp": tp, "fp": fp, "fn": fn, "tn": tn},
            "top": top, "probability_distribution": distribution,
            "probability_note": None if probability else "규칙 기준선의 점수는 확률이 아니다 — 확률 분포를 싣지 않는다"}


#: 보정(calibration) 표 · ECE 의 확률 구간 수 — [0, 0.1), [0.1, 0.2), … 등간격 (#215).
CALIBRATION_BINS = 10
#: 임계값 비교표의 "상위 비율" 행 — 마케팅이 한 번에 감당할 수 있는 대상 비율의 예시 (#215).
THRESHOLD_TOP_SHARES = (0.10, 0.20, 0.30)
#: 임계값 비교표의 "재현율 목표" 행 — 이탈자 중 이 비율 이상을 잡는 가장 높은 임계 (#215).
THRESHOLD_RECALL_TARGET = 0.80


def calibration(y, score, bins: int = CALIBRATION_BINS) -> dict:
    """예측 확률이 실제 비율과 맞는가 (#215, 멘토 피드백 — ROC-AUC 만으로는 채택 근거가 부족하다).

    ROC-AUC 는 **순서**만 본다. 확률 0.8 이라고 말한 고객 중 실제로 80% 가 이탈하는지는 보지 않는다.
      - ``brier`` = 평균 (확률 − 실제)². 0 이 완벽.
      - ``ece`` = 구간별 |평균 확률 − 실제 비율| 을 고객 수로 가중 평균(Expected Calibration Error).
      - ``bins`` = 구간마다 고객 수 · 평균 확률 · 실제 이탈률. 고객이 없는 구간은 None (0 으로 채우지 않는다).
    """
    y = np.asarray(y, dtype=float)
    p = np.clip(np.asarray(score, dtype=float), 0.0, 1.0)
    if not len(y):
        return {"brier": float("nan"), "ece": float("nan"), "bins": []}
    edges = np.linspace(0.0, 1.0, bins + 1)
    index = np.clip(np.searchsorted(edges, p, side="right") - 1, 0, bins - 1)
    rows, ece = [], 0.0
    for b in range(bins):
        mask = index == b
        n = int(mask.sum())
        row = {"low": float(edges[b]), "high": float(edges[b + 1]), "n": n, "mean_pred": None, "observed": None}
        if n:
            row["mean_pred"], row["observed"] = float(p[mask].mean()), float(y[mask].mean())
            ece += n / len(y) * abs(row["mean_pred"] - row["observed"])
        rows.append(row)
    return {"brier": float(np.mean((p - y) ** 2)), "ece": float(ece), "bins": rows}


def threshold_table(y, score) -> list[dict]:
    """임계값 비교표 (#215) — 같은 점수를 어디서 자르느냐에 따라 정밀도 · 재현율 · 대상 비율이 어떻게 바뀌나.

    행: F1 최대(기본 — ``predicted_label`` 에 쓰는 규칙) · 확률 0.5 · 상위 10/20/30% · 재현율 80%.
    **학습 데이터 안의 검증 예측(OOF)** 으로만 계산한다 — 시험 데이터로 임계를 고르지 않는다.

    열은 SRS ML-006 최소 비교 항목 ``threshold · precision · recall · f1 · target_count · expected_campaign_cost``
    (+ ``flagged_share``). ``target_count`` 는 **넘긴 점수의 모집단**(실행 루프: 학습 T0 군 CV OOF)에서 임계 이상인
    고객 수 — t2 캠페인 대상 수가 아니다. ``expected_campaign_cost`` 는 None — 이 표에는 처치 · 단가 근거가 없다
    (0 이나 임의 단가로 채우지 않는다, #280 리뷰 R2). 사유는 ``THRESHOLD_COLUMNS_NOTE``.
    """
    y = np.asarray(y).astype(int)
    s = np.asarray(score, dtype=float)
    positives = int(y.sum())

    def row(rule: str, threshold: float) -> dict:
        flagged = s >= threshold
        tp = int((flagged & (y == 1)).sum())
        n_flagged = int(flagged.sum())
        precision = tp / n_flagged if n_flagged else float("nan")
        recall = tp / positives if positives else float("nan")
        f1 = (2 * precision * recall / (precision + recall)
              if n_flagged and positives and (precision + recall) > 0 else 0.0)
        return {"rule": rule, "threshold": float(threshold), "flagged_share": n_flagged / len(y) if len(y) else None,
                "precision": precision, "recall": recall, "f1": float(f1),
                "target_count": n_flagged, "expected_campaign_cost": None}

    rows = [row("f1_max", _best_f1_threshold(y, s)), row("probability_0.5", 0.5)]
    for share in THRESHOLD_TOP_SHARES:
        rows.append(row(f"top_{round(share * 100)}pct", float(np.quantile(s, 1 - share)) if len(s) else math.inf))
    if positives:
        order = np.argsort(-s, kind="mergesort")
        reached = np.flatnonzero(np.cumsum(y[order]) >= THRESHOLD_RECALL_TARGET * positives)
        rows.append(row(f"recall_{round(THRESHOLD_RECALL_TARGET * 100)}", float(s[order][reached[0]])))
    return rows


#: 임계 선택 근거 — churn_eval 과 DR-215 에 같은 문장을 싣는다.
THRESHOLD_SELECTION = {
    "selected": "f1_max",
    "reason": ("이탈 확률의 이진 판정(predicted_label)은 보고 · 위험 분포 표시에만 쓴다. 실제로 누구에게 쿠폰을 "
               "보낼지는 전략(S2~S5)이 예산 안에서 점수 순서로 정하므로, 임계가 지출을 바꾸지 않는다. 그래서 "
               "정밀도와 재현율을 함께 보는 F1 최대를 기본으로 두고, 마케팅 수용량(상위 비율) · 놓치면 안 되는 "
               "비율(재현율 목표)에 따른 대안을 이 표로 함께 낸다"),
    "basis": "학습 데이터 교차검증의 검증 fold 예측(OOF) — 시험 · 홀드아웃 데이터 미사용",
}

#: 임계값표의 대상 수 · 비용 열 설명과 SRS ML-006 충족 범위(#280 리뷰 R2) — churn_eval.threshold_table 에 싣는다.
THRESHOLD_COLUMNS_NOTE = {
    "target_count_population": ("넘긴 학습 데이터(실행 루프: 탐색 RCT T0 군)의 교차검증 OOF 에서 임계 이상인 고객 수 — "
                                "t2 캠페인 대상 수가 아니다"),
    "expected_campaign_cost": ("null — 이 표에는 처치 · 단가 근거가 없다. 누구에게 어떤 처치를 줄지는 전략(S2~S5)이 예산 "
                               "안에서 정하고, 그 계획 비용은 측정 계층 단가로 strategy_comparison 에 계산된다. 0 이나 "
                               "임의 단가로 채우지 않는다"),
    "srs_ml006": ("부분 충족 — threshold · precision · recall · f1 · target_count 는 채우고 expected_campaign_cost 는 null"
                  "(위 사유). 남은 범위: 임계별 비용은 처치 · 단가가 정해지는 전략 단계(S2 계획 비용)와 연결할 때 채운다"),
}

#: TreeExplainer 기본 출력(model_output="raw")의 단위 — 기여 합 + 기대값이 무엇을 복원하나(#280 리뷰 N2).
#: 실측(shap 0.54.1 · sklearn 1.9 · xgboost 3.4.1 · lightgbm 4.7.0): random_forest = 양성 확률(오차 ~1e-15),
#: hist_gb · lightgbm = 양성 로그오즈(~1e-14), xgboost = 양성 로그오즈(float32 — ~3e-6).
#: 표에 없는 모델은 None — 확인하지 않은 단위를 적지 않는다.
SHAP_UNITS = {"random_forest": "probability", "hist_gb": "log_odds", "xgboost": "log_odds", "lightgbm": "log_odds"}


def shap_unit(name: str) -> str | None:
    """SHAP 기여값의 단위(``SHAP_UNITS``) — 크기를 해석하는 화면이 모델마다 다르게 읽어야 한다."""
    return SHAP_UNITS.get(name)


def _metrics(y: np.ndarray, score: np.ndarray, threshold: float) -> dict[str, float]:
    from sklearn.metrics import average_precision_score, f1_score, roc_auc_score

    y = np.asarray(y).astype(int)
    two_class = 0 < y.sum() < len(y)
    cal = calibration(y, score)
    return {
        "roc_auc": float(roc_auc_score(y, score)) if two_class else float("nan"),
        "pr_auc": float(average_precision_score(y, score)) if two_class else float("nan"),
        "f1": float(f1_score(y, (score >= threshold).astype(int), zero_division=0)),
        "lift_at_10": lift_at(y, score, 0.10),
        # SRS ML-009 — 상위 20 · 30% 리프트와 상위 10/20/30% 포착률(#303)
        "lift_at_20": lift_at(y, score, 0.20),
        "lift_at_30": lift_at(y, score, 0.30),
        "capture_at_10": capture_at(y, score, 0.10),
        "capture_at_20": capture_at(y, score, 0.20),
        "capture_at_30": capture_at(y, score, 0.30),
        "brier": cal["brier"],
        "ece": cal["ece"],
    }


def _not_probability(metrics: dict[str, float]) -> dict[str, float]:
    """규칙 기준선의 점수는 순위(경험분포)라 확률이 아니다 — 보정 지표를 매기지 않는다(None 으로 남는다)."""
    return {**metrics, "brier": float("nan"), "ece": float("nan")}


def _summary(values: list[float]) -> dict[str, float | None]:
    arr = np.asarray(values, dtype=float)
    arr = arr[~np.isnan(arr)]
    if not arr.size:
        return {"mean": None, "std": None, "n_folds": 0}
    return {"mean": float(arr.mean()), "std": float(arr.std(ddof=0)), "n_folds": int(arr.size)}


def _score(model, X: pd.DataFrame) -> np.ndarray:
    return np.asarray(model.predict_proba(X))[:, 1]


def _threshold_from_train(factory: Callable[[], object], X: pd.DataFrame, y: np.ndarray,
                          seed: int) -> float:
    """학습 데이터 내부 OOF 확률로 F1 임계를 정한다. 검증·시험 데이터는 보지 않는다."""
    from sklearn.model_selection import StratifiedKFold

    n_inner = min(INNER_SPLITS, int(np.bincount(y, minlength=2).min()))
    if n_inner < 2:
        model = factory().fit(X, y)
        return _best_f1_threshold(y, _score(model, X))
    oof = np.empty(len(y), dtype=float)
    for tr, va in StratifiedKFold(n_inner, shuffle=True, random_state=seed).split(X, y):
        model = factory().fit(X.iloc[tr], y[tr])
        oof[va] = _score(model, X.iloc[va])
    return _best_f1_threshold(y, oof)


def _prepare(X: pd.DataFrame, y) -> tuple[pd.DataFrame, np.ndarray]:
    if isinstance(y, pd.DataFrame):
        y = y["churn"]
    y = pd.Series(y).reindex(X.index) if isinstance(y, pd.Series) else pd.Series(np.asarray(y), index=X.index)
    if y.isna().any():
        raise ValueError(f"라벨 결손 {int(y.isna().sum())} 건 — X 와 y 의 고객이 어긋난다")
    values = y.astype(int).to_numpy()
    if not set(np.unique(values)) <= {0, 1}:
        raise ValueError("churn 라벨은 0/1 이어야 한다")
    return X[model_columns(X)].astype(float), values


def fold_indices(y: np.ndarray, seed: int) -> list[tuple[np.ndarray, np.ndarray]]:
    """ML·DL 이 **같은 fold** 를 쓰도록 하나로 둔다 (PRD §43 동일 Test Population)."""
    from sklearn.model_selection import StratifiedKFold

    minority = int(np.bincount(y, minlength=2).min())
    n_splits = min(N_SPLITS, minority)
    if n_splits < 2:
        raise ValueError(f"소수 클래스가 {minority} 건이라 층화 교차검증을 할 수 없다")
    splitter = StratifiedKFold(n_splits, shuffle=True, random_state=seed)
    return list(splitter.split(np.zeros(len(y)), y))


# ── Validation 튜닝 · 시간 순서 검증 (#215) ─────────────────────────────────

#: config/model_config.yaml `churn.tuning` — {enabled, metric, grids}.
TUNING = CONFIG.tuning


def _score_fn(metric: str):
    from sklearn.metrics import average_precision_score, roc_auc_score

    return roc_auc_score if metric == "roc_auc" else average_precision_score


def inner_folds(y: np.ndarray) -> int:
    """내부 교차검증 fold 수 — ``INNER_SPLITS`` 와 소수 클래스 수 중 작은 쪽(임계 선택과 같은 규칙). 2 미만이면 불가."""
    return min(INNER_SPLITS, int(np.bincount(np.asarray(y).astype(int), minlength=2).min()))


def _validation_score(name: str, overrides: Mapping[str, Any], X: pd.DataFrame, y: np.ndarray, seed: int,
                      prior: tuple[pd.DataFrame, np.ndarray] | None, metric: str) -> float | None:
    """한 조합의 **검증** 점수 — 유한한 값이 없으면 None(계산 불가). 시험 · 홀드아웃은 보지 않는다.

    ``prior`` 가 있으면 시간 순서 검증 — 앞 기준일 데이터로 학습하고 (X, y)(t1 학습 모집단)로 잰다.
    없으면 (X, y) 안의 ``inner_folds(y)``-fold 교차검증(소수 클래스 수로 제한) 중 **유한한 fold 점수의 평균**.
    한 클래스 fold · NaN 은 평균에 넣지 않는다(PR #281 리뷰 R2).
    """
    score = _score_fn(metric)
    if prior is not None:
        Xp, yp = prior
        if len(np.unique(y)) < 2:
            return None
        model = make_model(name, seed, overrides).fit(Xp, yp)
        value = float(score(y, _score(model, X[list(Xp.columns)])))
        return value if math.isfinite(value) else None
    from sklearn.model_selection import StratifiedKFold

    folds = inner_folds(y)
    if folds < 2:
        return None
    values = []
    for tr, va in StratifiedKFold(folds, shuffle=True, random_state=seed).split(X, y):
        if len(np.unique(y[va])) < 2 or len(np.unique(y[tr])) < 2:
            continue
        model = make_model(name, seed, overrides).fit(X.iloc[tr], y[tr])
        value = float(score(y[va], _score(model, X.iloc[va])))
        if math.isfinite(value):
            values.append(value)
    return float(np.mean(values)) if values else None


def tune_model(name: str, X: pd.DataFrame, y: np.ndarray, seed: int,
               prior: tuple[pd.DataFrame, np.ndarray] | None = None) -> dict:
    """Grid 튜닝 (#215, ML-005) — config 격자의 모든 조합을 검증 점수로 비교해 가장 높은 조합을 고른다.

    같은 점수면 격자에 먼저 적힌 조합을 고른다(재현성). 격자 전체 점수를 남긴다 — 고른 값만 남기면
    "다른 값은 해 보지 않았다"와 구분되지 않는다.
    """
    import itertools

    grid = (TUNING.get("grids") or {}).get(name)
    if not TUNING.get("enabled") or not grid:
        return {"status": "not_run", "reason": "튜닝이 꺼져 있거나 이 모델의 격자가 없다 — config 기본값", "params": {}}
    keys = list(grid)
    folds = None if prior is not None else inner_folds(y)
    basis = "temporal_validation" if prior is not None else f"inner_cv_{folds}fold"
    rows = []
    for combo in itertools.product(*(grid[k] for k in keys)):
        overrides = dict(zip(keys, combo))
        rows.append({"params": overrides,
                     "score": _validation_score(name, overrides, X, y, seed, prior, TUNING["metric"])})
    valid = [i for i, row in enumerate(rows) if row["score"] is not None]
    common = {"metric": TUNING["metric"], "basis": basis, "n_folds": folds, "grid": rows,
              "n_invalid": len(rows) - len(valid)}
    if not valid:  # PR #281 리뷰 R2 — 유효한 검증 없이 첫 후보를 고르지 않는다
        reason = (f"유효한 검증 점수가 없다(소수 클래스 {int(np.bincount(np.asarray(y).astype(int), minlength=2).min())}명"
                  f" · fold {folds})" if prior is None else "유효한 검증 점수가 없다(검증 데이터가 한 클래스 등)")
        return {"status": "not_run", "reason": reason + " — config 기본값을 쓴다", "params": {},
                "used_defaults": True, **common}
    best = max(valid, key=lambda i: (rows[i]["score"], -i))
    return {"status": "ok", "params": rows[best]["params"], "used_defaults": False, **common}


def temporal_validation(name: str, overrides: Mapping[str, Any] | None, X: pd.DataFrame, y: np.ndarray,
                        seed: int, prior: tuple[pd.DataFrame, np.ndarray]) -> dict:
    """시간 순서 검증 (#215, 멘토 피드백) — 앞 기준일(t1 − 42일) 데이터로 학습, t1 학습 모집단으로 평가.

    두 기준일 모두 처치 전 · 같은 Eligible 정의다. 임계도 앞 기준일 학습 데이터 안에서만 정한다.
    """
    Xp, yp = prior
    Xv = X[list(Xp.columns)]
    factory = (lambda: make_model(name, seed, overrides))
    model = factory().fit(Xp, yp)
    score = _score(model, Xv)
    if name == "rule_recency":
        from sklearn.metrics import f1_score

        predicted = model._days(Xv) >= model.threshold_days_
        metrics = _not_probability(_metrics(y, score, 0.0))
        metrics["f1"] = float(f1_score(y, predicted.astype(int), zero_division=0))
        report = classification_report(y, score, predicted, threshold=model.threshold_days_, threshold_unit="days",
                                       probability=False)
    else:
        threshold = _threshold_from_train(factory, Xp, yp, seed)
        metrics = _metrics(y, score, threshold)
        report = classification_report(y, score, threshold=threshold)
        predicted = score >= threshold
    return {"scheme": "temporal_validation", "n_train": int(len(yp)), "n_valid": int(len(y)),
            "pos_rate_train": float(np.mean(yp)), "pos_rate_valid": float(np.mean(y)), **metrics,
            "report": report,  # SRS ML-009 — 앞 기준일 학습 임계로 t1 에서 판정
            # #303 ML-010 — 고객별 점수 · 판정. evaluate_churn_models 가 떼어 낸다(결과 파일에 고객별 값을 싣지 않는다).
            "_predictions": {"score": np.asarray(score, dtype=float), "predicted": np.asarray(predicted, dtype=bool),
                             "probability": name != "rule_recency"}}


#: #303 · DR-303-model-selection — 이탈 모델 선택 규칙. GATE 3 전에 고정한다(결과를 보고 바꾸지 않는다).
SELECTION_RULE: dict[str, str] = {
    "primary": "시간 순서 검증 ROC-AUC — 앞 기준일(t_prior) 데이터로 학습해 t1 학습 모집단에서 평가, 제안 모델 중 최댓값",
    "tie_break": "같은 점수면 후보 순서(random_forest → hist_gb → xgboost → lightgbm)가 앞선 모델",
    "secondary": "상위 20% 리프트 · 보정(ECE · Brier) — 같은 데이터에서 함께 싣고 선택을 바꾸지 않는다",
    "fallback": "앞 기준일 데이터가 없으면 무작위 교차검증 평균 — 개발 실행용, 정식 선택(GATE 3)에는 쓰지 않는다",
    "not_used": "무작위 교차검증(시간 순서 검증이 있을 때는 참고) · 시간 홀드아웃(t2) · 과제 Test · Final Holdout",
    "official": "정식(official) = 시간 순서 검증 · ROC-AUC 로 고른 실행뿐 — 다른 설정 지표(PR-AUC 등)나 무작위 CV 로 고른 실행은 개발용",
    "decision": "docs/decisions/DR-303-model-selection.md",
}
METRIC_LABELS = {"roc_auc": "ROC-AUC", "pr_auc": "PR-AUC", "f1": "F1"}
#: DR-303 정식 선택 지표. 설정(``tuning.metric``)이 다른 지표를 허용해도 그 실행은 정식 선택이 아니다(#320 리뷰).
OFFICIAL_METRIC = "roc_auc"
OFFICIAL_CRITERION = "시간 순서 검증 ROC-AUC(DR-303)"


def _finite(value: Any) -> float | None:
    if value is None:
        return None
    value = float(value)
    return None if math.isnan(value) else value


def selection_record(models: list[dict], basis: str, metric: str, chosen: str, n_folds: int) -> dict:
    """#303 ML-011 — 고른 기준과 후보별 **선택 점수**를 무작위 교차검증 점수와 나눠 싣는다.

    ``selection_score`` 는 선택에 쓴 점수(시간 순서 검증, 없으면 무작위 CV 평균)이고 ``random_cv_score`` 는 참고다.
    ``rank`` 는 제안 모델 안에서 선택 점수 순위(동점은 후보 순서 — ``max`` 가 고르는 순서와 같다). 기준선은 순위가 없다.
    보조 지표(상위 20% 리프트 · ECE · Brier)는 선택과 같은 데이터에서 싣고 선택을 바꾸지 않는다.
    ``official`` 은 시간 순서 검증 **그리고** ROC-AUC 일 때만 참이다 — 아니면 ``official_reason`` 에 왜 아닌지 적는다.
    무작위 CV 로 고른 실행은 무작위 CV 점수가 곧 선택 점수라 ``reference_label`` 이 없다.
    """
    def on_basis(model: dict, key: str) -> float | None:
        if basis == "temporal_validation":
            return _finite((model.get("temporal_validation") or {}).get(key))
        return _finite(((model.get("cv") or {}).get(key) or {}).get("mean"))

    rows = [{"name": m["name"], "kind": m["kind"], "eligible": m["kind"] == "proposed",
             "selection_score": on_basis(m, metric),
             "lift_at_20": on_basis(m, "lift_at_20"), "ece": on_basis(m, "ece"), "brier": on_basis(m, "brier"),
             "random_cv_score": _finite(((m.get("cv") or {}).get(metric) or {}).get("mean")),
             "chosen": m["name"] == chosen, "rank": None} for m in models]
    ranked = sorted((r for r in rows if r["eligible"] and r["selection_score"] is not None),
                    key=lambda r: -r["selection_score"])   # 안정 정렬 — 동점은 후보 순서
    for rank, row in enumerate(ranked, start=1):
        row["rank"] = rank
    label = METRIC_LABELS.get(metric, metric)
    temporal = basis == "temporal_validation"
    official = temporal and metric == OFFICIAL_METRIC
    if official:
        reason = None
    elif not temporal:
        reason = "앞 기준일 데이터가 없어 무작위 교차검증 평균으로 골랐다 — 개발 실행용"
    else:
        reason = f"설정 지표 {label} 로 골랐다 — 정식 기준은 {OFFICIAL_CRITERION}"
    return {
        "rule": dict(SELECTION_RULE),
        "basis": basis, "metric": metric, "official": official,
        "official_reason": reason, "official_criterion": OFFICIAL_CRITERION,
        "basis_label": (f"시간 순서 검증 {label}(t_prior 학습 → t1 평가)"
                        + ("" if metric == OFFICIAL_METRIC else " — 설정 지표, 정식 기준(ROC-AUC) 아님") if temporal else
                        f"무작위 {n_folds}-Fold 교차검증 {label} 평균 — 앞 기준일 데이터 없음(개발 실행용)"),
        "reference_label": (f"무작위 {n_folds}-Fold 교차검증 {label} 평균 — 참고, 선택에 쓰지 않음" if temporal else None),
        "chosen": chosen,
        "chosen_score": next((r["selection_score"] for r in rows if r["chosen"]), None),
        "candidates": rows,
    }


# ── 평가 ────────────────────────────────────────────────────────────────────

@_limited_threads
def evaluate_churn_models(X: pd.DataFrame, y, seed: int, *, prior: tuple[pd.DataFrame, Any] | None = None,
                          keep_predictions: bool = False) -> dict:
    """Baseline 2 + 제안 4 를 같은 Stratified K-Fold(``N_SPLITS``)로 평가한다. 형식은 모듈 설명 참조.

    #215 — 제안 모델은 먼저 Validation 튜닝(``tune_model``)을 거친다. ``prior``(앞 기준일 Feature · 라벨)가
    오면 튜닝 · 모델 선택을 **시간 순서 검증**으로 하고, 없으면 무작위 교차검증으로 고른다(그 사실을 적는다).

    #303 ML-010 — ``keep_predictions`` 이고 시간 순서 검증을 했으면 후보별 고객 점수 · 판정을 ``_validation`` 에
    담는다(``group_performance`` 입력). JSON 이 아니다 — 호출자가 결과 파일에 싣기 전에 떼어 낸다.
    """
    X, yv = _prepare(X, y)
    prior_data: tuple[pd.DataFrame, np.ndarray] | None = None
    prior_status: dict[str, Any] = {"status": "not_run", "reason": "앞 기준일 데이터를 받지 않았다"}
    if prior is not None:
        Xp, yp = _prepare(*prior)
        if 0 < int(yp.sum()) < len(yp):
            prior_data = (Xp, yp)
            prior_status = {"status": "ok", "n": int(len(yp)), "pos_rate": float(yp.mean())}
        else:
            prior_status = {"status": "not_run", "reason": "앞 기준일 라벨이 한 값뿐이다 — 시간 순서 검증 불가"}
    unavailable = {name: why for name in MODEL_NAMES if (why := model_unavailable(name))}
    usable = [name for name in MODEL_NAMES if name not in unavailable]
    tuning = {name: tune_model(name, X, yv, seed, prior_data) for name in PROPOSED if name in usable}
    overrides = {name: tuning[name]["params"] for name in tuning}
    folds = fold_indices(yv, seed)
    models = []
    oof: dict[str, np.ndarray] = {}  # 검증 fold 예측 — 임계값 비교표 · 보정표(#215)
    predictions: dict[str, dict[str, Any]] = {}  # 시간 순서 검증의 고객별 점수 · 판정(#303 ML-010)
    for name in usable:
        per_fold: dict[str, list[float]] = {}   # 키는 _metrics 의 지표 이름(ML-009 #303 포함)
        thresholds = []
        oof[name] = np.full(len(yv), np.nan)
        for k, (tr, va) in enumerate(folds):
            factory = (lambda n=name, s=seed + k: make_model(n, s, overrides.get(n)))
            model = factory().fit(X.iloc[tr], yv[tr])
            if name == "rule_recency":
                # 규칙의 판정 임계는 경과일 그 자체(학습 fold 에서 F1 최대)
                threshold = None
                pred_days = model._days(X.iloc[va])
                score = _score(model, X.iloc[va])
                metrics = _not_probability(_metrics(yv[va], score, 0.0))
                from sklearn.metrics import f1_score
                metrics["f1"] = float(f1_score(
                    yv[va], (pred_days >= model.threshold_days_).astype(int), zero_division=0))
                thresholds.append(model.threshold_days_)
            else:
                threshold = _threshold_from_train(factory, X.iloc[tr], yv[tr], seed + k)
                score = _score(model, X.iloc[va])
                metrics = _metrics(yv[va], score, threshold)
                thresholds.append(threshold)
            oof[name][va] = score
            for key, value in metrics.items():
                per_fold.setdefault(key, []).append(value)
        entry = {"name": name, "kind": _kind(name),
                 "cv": {key: _summary(values) for key, values in per_fold.items()},
                 "threshold": {"rule": ("학습 fold F1 최대 경과일(days)" if name == "rule_recency"
                                        else f"학습 fold 내부 {INNER_SPLITS}-fold OOF F1 최대 확률"),
                               "per_fold": [float(t) for t in thresholds]}}
        if name in tuning:  # #215 — 튜닝한 값과 격자 전체 점수
            entry["params"] = dict(overrides[name])
            entry["tuning"] = tuning[name]
        if prior_data is not None:  # #215 — 시간 순서 검증
            entry["temporal_validation"] = temporal_validation(name, overrides.get(name), X, yv, seed, prior_data)
            predictions[name] = entry["temporal_validation"].pop("_predictions")
        models.append(entry)

    # #215 — 고르는 기준: 시간 순서 검증이 있으면 그 점수, 없으면 무작위 교차검증 평균(튜닝 지표와 같은 지표).
    metric = TUNING.get("metric", "roc_auc")
    basis = "temporal_validation" if prior_data is not None else "random_cv"

    def selection_score(m: dict) -> float:
        value = m["temporal_validation"].get(metric) if basis == "temporal_validation" else m["cv"][metric]["mean"]
        return -1.0 if value is None or (isinstance(value, float) and math.isnan(value)) else float(value)

    best = max((m for m in models if m["kind"] == "proposed"), key=selection_score)
    importance = churn_importance(X, yv, best["name"], seed, overrides.get(best["name"]))
    best_oof = oof[best["name"]]
    # #303 ML-009 — 고른 모델의 혼동행렬 · 상위 리프트 · 포착률 · 확률 분포를 **선택에 쓴 데이터**에서 낸다.
    if basis == "temporal_validation":
        chosen_report = {"basis": basis, **best["temporal_validation"]["report"],
                         "note": "앞 기준일 학습 모델을 t1 에서 평가 — 임계는 앞 기준일 학습 데이터 내부 OOF F1 최대"}
    else:
        chosen_report = {"basis": basis, **classification_report(yv, best_oof, threshold=_best_f1_threshold(yv, best_oof)),
                         "note": "바깥 CV 검증 예측(OOF) — 임계는 같은 OOF 의 F1 최대(표시용, threshold_table 과 같은 규칙)"}
    result = {
        "label_def": LABEL_DEF, "n": int(len(yv)), "pos_rate": float(yv.mean()),
        "n_features": int(X.shape[1]), "seed": int(seed),
        "cv_scheme": f"StratifiedKFold(n_splits={len(folds)}, shuffle=True, random_state={seed})",
        "imbalance": "class_weight (balanced / balanced_subsample), rule 은 F1 임계",
        "models": models,
        "best_proposed": best["name"],
        # #215 — 확정 모델의 튜닝 값과 고른 기준. fit_best_churn 이 같은 값으로 학습한다.
        "best_params": dict(overrides.get(best["name"]) or {}),
        "models_unavailable": [{"name": n, "reason": why} for n, why in unavailable.items()],
        "selection_basis": basis,
        "selection_metric": metric,
        # #303 ML-011 — 고른 기준 · 후보별 선택 점수를 무작위 CV 점수와 나눠 싣는다(CLI · 대시보드가 이 블록을 읽는다)
        "selection": selection_record(models, basis, metric, best["name"], len(folds)),
        "selection_report": chosen_report,
        "temporal_validation_data": prior_status,
        "selection_note": ("시간 순서 검증(앞 기준일 학습 → t1 학습 모집단 평가)으로 튜닝 · 선택했다. 같은 t1 데이터의 "
                           "무작위 교차검증 점수는 선택에 쓰인 데이터라 낙관적이다 — 학습에 안 쓴 성능은 시간 홀드아웃(t2)"
                           if basis == "temporal_validation" else
                           "앞 기준일 데이터가 없어 무작위 교차검증으로 튜닝 · 선택했다 — 같은 데이터의 교차검증 점수는 "
                           "낙관적이다. 학습에 안 쓴 성능은 시간 홀드아웃(t2)"),
        "shap_top": importance["top"],
        "importance_method": importance["method"],
        "importance_model": best["name"],
        "importance_note": importance["note"],
        # #215 — 고른 모델 **종류**(best_proposed)의 바깥 CV 검증 fold 예측으로 만든 표. 시험 데이터를 보지 않는다.
        # 배치 객체의 임계는 fit_best_churn 이 전체 학습 데이터 내부 OOF 로 따로 정한다(#280 리뷰 R1 — 근거가 다르다).
        "threshold_table": {"model": best["name"], "rows": threshold_table(yv, best_oof), **THRESHOLD_SELECTION,
                            "basis_model": (f"{best['name']} 종류의 바깥 {len(folds)}-fold CV 검증 예측(OOF) — 배치 "
                                            f"객체의 임계는 fit_best_churn 이 전체 학습 데이터 내부 {INNER_SPLITS}-fold "
                                            "OOF 로 따로 정한다(같은 F1 최대 규칙, 다른 OOF — 값이 다를 수 있다)"),
                            **THRESHOLD_COLUMNS_NOTE},
        "calibration": {"model": best["name"], "basis": THRESHOLD_SELECTION["basis"],
                        "class_weight_note": "class_weight 로 양성 가중을 했으므로 확률이 실제 비율보다 높게 "
                                             "나올 수 있다 — 순서(ROC-AUC)와 별개로 본다",
                        **calibration(yv, best_oof)},
    }
    if keep_predictions and predictions:
        index = X.index.map(str)
        result["_validation"] = {
            "y": pd.Series(yv, index=index, name="churn"), "chosen": best["name"],
            "models": {name: {"score": pd.Series(p["score"], index=index), "predicted": pd.Series(p["predicted"], index=index),
                              "probability": p["probability"]} for name, p in predictions.items()},
        }
    return result


#: #303 ML-010 · DR-303 — 약한 고객군 판정의 유의수준(양측). 프로젝트의 다른 통계 판정인 A/B 분석
#: (``config/experiment_config.yaml`` ``ab_test.alpha``)과 같은 값이다 — 시험이 두 값이 같은지 본다.
GROUP_TEST_ALPHA = 0.05
#: 고객군마다 고른 모델과 나란히 보는 기준선. S1 규칙(그리고 같은 고객 · 같은 순서를 쓰는 S6)이 고객을 줄 세우는
#: 신호(마지막 구매 후 경과일 내림차순, ``strategies.S1_RULE``)와 같은 신호만 쓰는 후보다 — "모델이 맞지 않는
#: 고객군은 규칙으로"(PRD §38.2)의 비교 상대.
GROUP_BASELINE = "rule_recency"
#: 관측 등급 축의 이름(CLI · 보고서). 코드 → 뜻은 ``observed_tiers.TIER_LABELS``.
TIER_AXIS_NAMES: dict[str, str] = {"value_tier": "가치 등급", "frequency_tier": "구매 횟수",
                                   "signup_tier": "가입 시기", "category_tier": "주 구매 상품군"}


def _z(alpha: float) -> float:
    from scipy.stats import norm

    return float(norm.ppf(1 - alpha / 2))


def delong(y, scores: list) -> tuple[np.ndarray, np.ndarray] | None:
    """DeLong(1988) — 같은 고객에 대한 점수 여러 개의 ROC-AUC 와 그 공분산 행렬(비모수).

    양성 · 음성이 각각 2명 이상이어야 한다(아니면 None). 순위는 중간 순위(동점 0.5)라 AUC 가 ``roc_auc_score`` 와 같다.
    """
    from scipy.stats import rankdata

    y = np.asarray(y).astype(int)
    pos, neg = y == 1, y == 0
    m, n = int(pos.sum()), int(neg.sum())
    if m < 2 or n < 2:
        return None
    v10, v01 = [], []
    for score in scores:
        s = np.asarray(score, dtype=float)
        x, z = s[pos], s[neg]
        ranks = rankdata(np.concatenate([x, z]))
        v10.append((ranks[:m] - rankdata(x)) / n)          # 양성마다: 그보다 낮은 음성 비율(동점 0.5)
        v01.append(1.0 - (ranks[m:] - rankdata(z)) / m)    # 음성마다: 그보다 높은 양성 비율(동점 0.5)
    aucs = np.array([v.mean() for v in v10])
    cov = np.atleast_2d(np.cov(np.vstack(v10))) / m + np.atleast_2d(np.cov(np.vstack(v01))) / n
    return aucs, cov


def _diff_test(diff: float, var: float, alpha: float) -> dict[str, Any]:
    half = _z(alpha) * math.sqrt(max(var, 0.0))
    return {"diff": float(diff), "ci95": [float(diff - half), float(diff + half)], "below": bool(diff + half < 0)}


def _group_metrics(y, score, predicted, probability: bool) -> dict[str, Any]:
    """한 고객군 · 한 모델의 ML-009 지표. 계산할 수 없는 값은 None 이다 — 0 으로 채우지 않는다.

    판정(``predicted``)은 전체 Validation 과 같은 임계(앞 기준일 학습 데이터 안에서 정한 값)다 — 고객군마다 다시
    정하면 Validation 으로 임계를 맞추는 셈이고, 운영에서도 임계는 하나다. ROC-AUC 95% 구간은 DeLong.
    """
    from sklearn.metrics import average_precision_score, roc_auc_score

    y = np.asarray(y).astype(int)
    s = np.asarray(score, dtype=float)
    pred = np.asarray(predicted).astype(bool)
    n, positives = int(len(y)), int(y.sum())
    two_class = 0 < positives < n
    tp = int((pred & (y == 1)).sum())
    fp = int((pred & (y == 0)).sum())
    fn = int((~pred & (y == 1)).sum())
    tn = int((~pred & (y == 0)).sum())
    cal = calibration(y, s) if probability and n else None
    dl = delong(y, [s])
    ci = None
    if dl is not None:
        half = _z(GROUP_TEST_ALPHA) * math.sqrt(max(float(dl[1][0, 0]), 0.0))
        ci = [max(0.0, float(dl[0][0] - half)), min(1.0, float(dl[0][0] + half))]
    return {
        "n": n, "positives": positives, "pos_rate": positives / n if n else None,
        "roc_auc": float(roc_auc_score(y, s)) if two_class else None,
        "roc_auc_ci95": ci,
        "pr_auc": float(average_precision_score(y, s)) if two_class else None,
        "confusion_matrix": {"tp": tp, "fp": fp, "fn": fn, "tn": tn},
        "precision": tp / (tp + fp) if tp + fp else None,
        "recall": tp / positives if positives else None,
        "f1": 2 * tp / (2 * tp + fp + fn) if 2 * tp + fp + fn else None,
        "top": [{"share": share, "n_top": max(1, int(math.ceil(n * share))) if n else 0,
                 "lift": _finite(lift_at(y, s, share)) if n else None,
                 "capture": _finite(capture_at(y, s, share)) if n else None} for share in TOP_SHARES],
        "brier": _finite(cal["brier"]) if cal else None,
        "ece": _finite(cal["ece"]) if cal else None,
        "probability_distribution": ([{"low": b["low"], "high": b["high"], "n": b["n"]} for b in cal["bins"]]
                                     if cal else None),
    }


def group_performance(validation: Mapping[str, Any], groups: pd.DataFrame, axes: Mapping[str, Mapping[str, str]], *,
                      population: str, groups_source: str) -> dict[str, Any]:
    """SRS ML-010 · PRD §38.2 — 고객군마다 후보별 ML-009 지표. **시간 순서 검증(Validation) 예측만** 쓴다.

    - ``validation``: ``evaluate_churn_models(keep_predictions=True)`` 의 ``_validation`` — 라벨 · 고른 모델 · 후보별
      고객 점수와 판정(index = customer_id 문자열).
    - ``groups``: index = customer_id, 열 = ``axes`` 의 축. 이미 정한 고객군을 읽기만 한다(다시 나누지 않는다).
    - ``axes``: 축 → {코드: 뜻}. 코드 순서대로 싣고, 고객이 없는 코드도 n = 0 으로 싣는다. 뜻에 없는 코드가 나오면
      뒤에 붙인다 — 어떤 고객군도 빼지 않는다.

    **약한 고객군**(표본 부족이 아닌 고객군만, DR-303): 고른 모델의 ROC-AUC 가 ① 같은 고객의 기준선
    (``GROUP_BASELINE``)보다 유의하게 낮거나(짝지은 DeLong 차이의 95% 구간 상한 < 0, ``below_baseline``) ② 그 고객군
    밖 나머지 고객보다 유의하게 낮다(독립 두 표본 DeLong 차이의 95% 구간 상한 < 0, ``below_rest``). 고객군 수만큼 검정을
    하지만 다중 비교 보정은 하지 않는다 — 표시는 살펴볼 후보를 숨기지 않으려는 것이고(PRD §38.2) 적용 범위 결정이
    아니다. 모델 적용 범위는 여기서 정하지 않는다 — Validation 에서만 정한다. Test · Final Holdout 은 쓰지 않는다.
    """
    from src.decision.observed_tiers import MIN_GROUP_CUSTOMERS, MIN_GROUP_MINORITY, small_group

    y = pd.Series(validation["y"]).astype(int)
    y.index = y.index.map(str)
    models = validation["models"]
    chosen = validation["chosen"]
    baseline = GROUP_BASELINE if GROUP_BASELINE in models else None
    frame = groups.copy()
    frame.index = frame.index.map(str)
    frame = frame[~frame.index.duplicated(keep=False)].reindex(y.index)
    grouped = frame.notna().any(axis=1) if len(frame.columns) else pd.Series(False, index=y.index)
    yv = y.to_numpy()
    scores = {name: m["score"].reindex(y.index).to_numpy(dtype=float) for name, m in models.items()}
    predicted = {name: m["predicted"].reindex(y.index).to_numpy() for name, m in models.items()}

    def measure(idx: np.ndarray) -> dict[str, dict[str, Any]]:
        return {name: _group_metrics(yv[idx], scores[name][idx], predicted[name][idx], m["probability"])
                for name, m in models.items()}

    def small_reason(n: int, positives: int) -> str | None:
        if n < MIN_GROUP_CUSTOMERS:
            return f"고객 {n}명 < {MIN_GROUP_CUSTOMERS}명"
        if small_group(n, positives):
            return f"적은 쪽 클래스 {min(positives, n - positives)}명 < {MIN_GROUP_MINORITY}명"
        return None

    def tests(idx: np.ndarray, rest_mask: np.ndarray) -> dict[str, Any]:
        """``rest_mask`` = 같은 축에서 고객군이 정해진 다른 고객(#325 리뷰) — 고객군이 없는 고객은 비교군에 넣지 않는다."""
        n_rest, rest_positives = int(rest_mask.sum()), int(yv[rest_mask].sum())
        out: dict[str, Any] = {"vs_baseline": None, "vs_rest": None, "n_rest": n_rest, "vs_rest_reason": None}
        if baseline is not None:
            paired = delong(yv[idx], [scores[chosen][idx], scores[baseline][idx]])
            if paired is not None:
                aucs, cov = paired
                out["vs_baseline"] = _diff_test(aucs[0] - aucs[1], cov[0, 0] + cov[1, 1] - 2 * cov[0, 1],
                                                GROUP_TEST_ALPHA)
        rest_small = small_reason(n_rest, rest_positives)
        if rest_small is not None:  # 비교군도 표본 부족 기준을 지킨다(DR-221) — 검정하지 않고 사유를 남긴다
            out["vs_rest_reason"] = f"나머지 고객 표본 부족 — {rest_small}"
            return out
        inside, rest = delong(yv[idx], [scores[chosen][idx]]), delong(yv[rest_mask], [scores[chosen][rest_mask]])
        if inside is None or rest is None:
            out["vs_rest_reason"] = "검정 불가 — 한 클래스뿐인 쪽이 있다"
            return out
        out["vs_rest"] = {**_diff_test(inside[0][0] - rest[0][0], inside[1][0, 0] + rest[1][0, 0], GROUP_TEST_ALPHA),
                          "n_rest": n_rest}
        return out

    overall = measure(np.ones(len(yv), dtype=bool))
    out_axes: dict[str, list[dict[str, Any]]] = {}
    for axis, labels in axes.items():
        values = frame[axis] if axis in frame.columns else pd.Series(None, index=y.index, dtype=object)
        codes = list(labels) + sorted({str(v) for v in values.dropna()} - set(labels))
        in_axis = values.notna().to_numpy()
        rows = []
        for code in codes:
            idx = values.astype(object).eq(code).fillna(False).astype(bool).to_numpy()
            n, positives = int(idx.sum()), int(yv[idx].sum())
            small = small_group(n, positives)
            reason = small_reason(n, positives)
            weak: bool | None = None
            weak_reasons: list[str] = []
            checks = None
            if not small:
                checks = tests(idx, in_axis & ~idx)
                done = [key for key in ("vs_baseline", "vs_rest") if checks[key] is not None]
                weak_reasons = [{"vs_baseline": "below_baseline", "vs_rest": "below_rest"}[key]
                                for key in done if checks[key]["below"]]
                weak = bool(weak_reasons) if done else None
            rows.append({"group": code, "label": labels.get(code), "n": n, "positives": positives,
                         "small_group": small, "small_group_reason": reason, "weak": weak,
                         "weak_reasons": weak_reasons, "tests": checks, "models": measure(idx)})
        out_axes[axis] = rows
    return {
        "status": "ok", "basis": "temporal_validation", "population": population, "groups_source": groups_source,
        "chosen": chosen, "baseline": baseline, "models": list(models),
        "n": int(len(y)), "n_grouped": int(grouped.sum()), "n_without_group": int((~grouped).sum()),
        "overall": overall, "axes": out_axes,
        "rule": {
            "small_group": (f"고객 {MIN_GROUP_CUSTOMERS}명 미만이거나 적은 쪽 클래스 {MIN_GROUP_MINORITY}명 미만 — 값은 싣고 "
                            "약한 고객군 판정 · 비교에 쓰지 않는다(DR-221)"),
            "weak_group": (f"표본 부족이 아닌 고객군에서 {chosen} 의 ROC-AUC 가 같은 고객의 {baseline or '기준선(없음)'} 보다"
                           "(below_baseline, 짝지은 DeLong) 또는 나머지 고객보다(below_rest, 독립 DeLong) 유의하게 낮다 — "
                           f"차이의 {1 - GROUP_TEST_ALPHA:.0%} 구간 상한 < 0. 다중 비교 보정 없음 — 표시만 하고 적용 범위는 "
                           "정하지 않는다"),
            "rest": ("나머지 고객 = 같은 축에서 고객군이 정해진 다른 고객(고객군이 없는 고객 — 명부 밖 · 역할 불일치 · 그 축 결손 — "
                     "은 전체 지표에만 넣고 비교군에 넣지 않는다). 나머지에도 표본 부족 기준을 적용하고, 부족하면 검정하지 않고 "
                     "vs_rest_reason 에 사유를 남긴다"),
            "selection_effect": ("고른 모델은 같은 t1 Validation 의 ROC-AUC 로 골랐다 — 같은 데이터에서 평가한 성능은 낙관적으로 "
                                 "치우칠 수 있다(Cawley & Talbot 2010). 기준선과의 비교(below_baseline)는 모델에 유리한 쪽으로 기운다"),
            "alpha": GROUP_TEST_ALPHA, "test": "DeLong(1988) ROC-AUC 분산 · 공분산",
            "threshold": "전체 Validation 과 같은 임계(앞 기준일 학습 데이터 안에서 정함)",
            "decision": "docs/decisions/DR-303-model-selection.md",
        },
        "note": ("Validation(시간 순서 검증 — 앞 기준일 학습 → t1 평가)에서만 냈다. Test · Final Holdout 이 아니다. "
                 "모델 적용 범위를 고객군으로 제한할지는 이 표로 Validation 에서만 정한다(PRD §38.2)"),
    }


#: #303 ML-010 — 고객군별 성능의 가설(DR-303). 근거 자료가 없어 결과 전에 가설로 세우고, 실행마다 같은 규칙으로 평가한다.
#: 평가 결과: supported(지지) · not_supported(지지되지 않음) · undetermined(판정 불가 — 표본 부족 · 검정 불가).
TIER_HYPOTHESES: tuple[dict[str, str], ...] = (
    {"id": "H-ML010-1",
     "statement": "고른 모델은 표본 부족이 아닌 어느 관측 등급에서도 규칙 기준선보다 ROC-AUC 가 유의하게 낮지 않다",
     "why": "PRD §38.2 의 '잘 맞는 고객군에만 모델' 선택지가 필요한지 — 등급별 성능은 아무도 계산한 적이 없다(DR-221 노출 기록)",
     "evaluation": "below_baseline 등급이 없으면 지지, 있으면 지지되지 않음(그 등급 목록), 판정한 등급이 없으면 판정 불가"},
    {"id": "H-ML010-2",
     "statement": "신규 가입 고객(signup_tier NEW)에서 고른 모델의 ROC-AUC 가 나머지 고객보다 유의하게 낮다",
     "why": "가입 180일 미만은 Feature 창(180일)이 다 차지 않아 금액 · 횟수 근거가 짧다(DR-221 가입 시기 근거)",
     "evaluation": "NEW 가 below_rest 면 지지, 검정했으나 아니면 지지되지 않음(같다는 증거는 아니다), 표본 부족이면 판정 불가"},
    {"id": "H-ML010-3",
     "statement": "180일 창 안 구매 1회 고객(frequency_tier F1_ONCE)에서 고른 모델의 ROC-AUC 가 나머지 고객보다 유의하게 낮다",
     "why": "구매가 한 번이면 창 안에서 구매 간격 · 반복을 관측할 수 없다",
     "evaluation": "F1_ONCE 가 below_rest 면 지지, 검정했으나 아니면 지지되지 않음(같다는 증거는 아니다), 표본 부족이면 판정 불가"},
)


#: 결과를 읽는 문구(#325 리뷰) — "지지"가 같음 · 우월의 증거로 읽히지 않게 한다. 규칙은 바꾸지 않는다.
TIER_READINGS: dict[str, dict[str, str]] = {
    "H-ML010-1": {
        "supported": ("검정 가능한 등급에서 기준선 대비 유의한 열세가 관측되지 않음 — 같다는 증거는 아니고, 같은 Validation 에서 "
                      "모델을 골라 모델에 유리한 쪽으로 치우칠 수 있다"),
        "not_supported": "기준선보다 유의하게 낮은 등급이 있다(evidence.below_baseline)",
        "undetermined": "검정 가능한 등급이 없다 — 표본 부족 · 검정 불가",
    },
    "H-ML010-2": {
        "supported": "신규 가입 고객의 ROC-AUC 가 같은 축의 나머지 고객보다 유의하게 낮다",
        "not_supported": "유의하게 낮다는 근거가 부족하다 — 같다는 증거는 아니다",
        "undetermined": "판정 불가 — 고객군 또는 나머지 고객의 표본 부족 · 검정 불가(evidence.reason)",
    },
    "H-ML010-3": {
        "supported": "구매 1회 고객의 ROC-AUC 가 같은 축의 나머지 고객보다 유의하게 낮다",
        "not_supported": "유의하게 낮다는 근거가 부족하다 — 같다는 증거는 아니다",
        "undetermined": "판정 불가 — 고객군 또는 나머지 고객의 표본 부족 · 검정 불가(evidence.reason)",
    },
}


def evaluate_tier_hypotheses(axes: Mapping[str, list[Mapping[str, Any]]]) -> list[dict[str, Any]]:
    """``TIER_HYPOTHESES`` 를 이 실행의 등급별 결과로 평가한다 — 규칙은 결과 전에 고정했다(DR-303)."""
    rows = {(axis, row["group"]): row for axis, items in axes.items() for row in items}
    judged = [(axis, row) for (axis, _), row in rows.items() if (row.get("tests") or {}).get("vs_baseline")]
    below = [f"{axis}={row['group']}" for axis, row in judged if row["tests"]["vs_baseline"]["below"]]
    out = []
    for hyp in TIER_HYPOTHESES:
        if hyp["id"] == "H-ML010-1":
            result = "undetermined" if not judged else ("not_supported" if below else "supported")
            evidence = {"n_groups_judged": len(judged), "below_baseline": below}
        else:
            key = ("signup_tier", "NEW") if hyp["id"] == "H-ML010-2" else ("frequency_tier", "F1_ONCE")
            row = rows.get(key) or {}
            checks = row.get("tests") or {}
            test = checks.get("vs_rest")
            if row.get("small_group", True) or test is None:
                result = "undetermined"
                evidence = {"group": f"{key[0]}={key[1]}", "n": row.get("n"), "n_rest": checks.get("n_rest"),
                            "reason": (row.get("small_group_reason") or checks.get("vs_rest_reason")
                                       or "검정 불가(한 클래스뿐인 쪽이 있다)")}
            else:
                result = "supported" if test["below"] else "not_supported"
                evidence = {"group": f"{key[0]}={key[1]}", "n": row["n"], "n_rest": test.get("n_rest"),
                            "diff_vs_rest": test["diff"], "ci95": test["ci95"]}
        out.append({**hyp, "result": result, "reading": TIER_READINGS[hyp["id"]][result], "evidence": evidence})
    return out


def tier_performance(validation: Mapping[str, Any], roster_t1: pd.DataFrame,
                     frequency_check: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """#303 ML-010 — 관측 등급(DR-221)별 ML-009 지표. 등급은 #218 명부의 t1 행을 그대로 읽는다(다시 계산하지 않는다).

    ``roster_t1``: 명부의 ``origin == "t1"`` 행(``customer_id`` · ``role`` · 등급 열). Validation 고객의 명부 역할이
    ``validation`` 이 아니거나 명부에 없으면 그 수를 남긴다 — 그런 고객은 등급 없이 전체 지표에만 들어간다.

    ``frequency_check``: 명부 요약의 t1 ``frequency_band_check``. 구매 횟수 구간이 아직 확정 전
    (``observed_tiers.FREQUENCY_BANDS_FINAL`` 거짓)인데 점검 범위를 벗어났으면 지표를 내지 않는다(``withheld``) —
    DR-221 은 그때 등급별 성능을 보기 **전에** 구간을 한 번 고칠 수 있게 했다.
    """
    from src.decision.observed_tiers import FREQUENCY_BANDS_FINAL, TIER_COLUMNS, TIER_LABELS, TIER_VERSION

    if not FREQUENCY_BANDS_FINAL and isinstance(frequency_check, Mapping) and frequency_check.get("outside"):
        return {"status": "withheld", "tier_version": TIER_VERSION, "frequency_band_check": dict(frequency_check),
                "reason": (f"DR-221 구매 횟수 구간 점검 — {', '.join(map(str, frequency_check['outside']))} 가 t1 Eligible 의 "
                           f"{frequency_check.get('range')} 밖이다. 구간을 확정(FREQUENCY_BANDS_FINAL)하기 전에는 등급별 "
                           "성능을 내지 않는다 — 분포만 보고 구간을 고칠지 먼저 정한다")}
    rows = roster_t1.copy()
    rows["customer_id"] = rows["customer_id"].map(str)
    rows = rows.set_index("customer_id")
    ids = pd.Series(validation["y"]).index.map(str)
    roles = rows["role"].reindex(ids)
    mismatch = roles.notna() & (roles != "validation")
    tiers = rows.loc[rows["role"] == "validation", list(TIER_COLUMNS)]
    result = group_performance(validation, tiers, {axis: TIER_LABELS[axis] for axis in TIER_COLUMNS},
                               population="t1 시간 순서 검증 모집단(탐색 RCT T0 군 — 앞 기준일 학습 모델로 평가)",
                               groups_source="#218 명부 t1 validation 행의 관측 등급(DR-221)")
    return {**result, "tier_version": TIER_VERSION, "axis_names": dict(TIER_AXIS_NAMES),
            "roster_check": {"n_not_in_roster": int(roles.isna().sum()), "n_role_not_validation": int(mismatch.sum())},
            "hypotheses": evaluate_tier_hypotheses(result["axes"])}


# ── #303 ML-010 AI 세그먼트 축(SEG-002, DR-303 「AI 세그먼트 축」) ─────────────────────────────

SEGMENT_AXIS = "ai_segment"
#: AI 세그먼트 코드 → 뜻(``segments.assign_segments`` 의 출력). PRD §20 S1~S6 · Sleeping Dogs 뒤에 가치를 모를 때 ·
#: 점수 결손 라벨을 둔다 — 어떤 고객군도 빼지 않는다(SRS ML-010).
SEGMENT_LABELS: dict[str, str] = {
    "HV_PERSUADABLE": "고가치 · 설득 가능(S1)", "HV_SURE_THING": "고가치 · 그냥 둬도 유지(S2)",
    "HV_LOST_CAUSE": "고가치 · 반응 없음(S3)", "LV_PERSUADABLE": "저가치 · 설득 가능(S4)",
    "LV_LOST_CAUSE": "저가치 · 반응 없음(S5)", "NEW": "신규 가입(S6)", "SLEEPING_DOG": "처치 역효과(Sleeping Dogs)",
    "CLV_UNKNOWN_PERSUADABLE": "가치 모름 · 설득 가능", "CLV_UNKNOWN_NEAR_ZERO": "가치 모름 · 반응 ≈ 0",
    "UNSCORED": "점수 결손 — 판정 불가",
}
#: SRS SEG-002 세그먼트(가설 판정 대상). 가치 모름 · 점수 결손 라벨은 싣지만 판정하지 않는다.
SEG002_SEGMENTS: tuple[str, ...] = ("HV_PERSUADABLE", "HV_SURE_THING", "HV_LOST_CAUSE", "LV_PERSUADABLE",
                                    "LV_LOST_CAUSE", "NEW", "SLEEPING_DOG")
#: 고른 모델의 이탈 점수로 가른 세그먼트 — ``assign_segments`` 는 고가치 · |uplift| ≤ 띠 고객을 이탈 점수 분위수로
#: 둘로 나눈다. 그 안에서는 점수 범위가 잘려 그 모델의 ROC-AUC 가 구조적으로 낮아진다(같은 고객의 기준선과 짝지어도
#: 고른 모델 쪽만 잘린다). 값 · 검정은 싣고 표시하되 가설 판정에 쓰지 않는다(DR-303).
SCORE_RESTRICTED_SEGMENTS: tuple[str, ...] = ("HV_SURE_THING", "HV_LOST_CAUSE")

#: 결과 전에 등록한 가설(DR-303 「AI 세그먼트 축」). 평가 결과 표기는 ``TIER_HYPOTHESES`` 와 같다.
SEGMENT_HYPOTHESES: tuple[dict[str, str], ...] = (
    {"id": "H-ML010-4",
     "statement": ("고른 모델은 표본 부족이 아니고 이탈 점수로 가르지 않은 어느 AI 세그먼트(SEG-002)에서도 규칙 기준선보다 "
                   "ROC-AUC 가 유의하게 낮지 않다"),
     "why": ("혼합 전략(PRD §61.1 · S6, #305)이 세그먼트마다 규칙과 AI 중 무엇을 쓸지 정하려면 세그먼트별로 모델이 규칙보다 "
             "나은지 알아야 한다 — 세그먼트별 이탈 성능은 계산한 적이 없다"),
     "evaluation": ("below_baseline 세그먼트가 없으면 지지, 있으면 지지되지 않음(그 세그먼트 목록), 판정한 세그먼트가 없으면 "
                    "판정 불가. 이탈 점수로 가른 세그먼트(HV_SURE_THING · HV_LOST_CAUSE)와 SEG-002 밖 라벨은 판정에 쓰지 않는다")},
)


#: 결과를 읽는 문구 — H-ML010-1 과 같은 이유(#325 리뷰): "지지"가 같음 · 우월의 증거로 읽히지 않게 한다. 규칙은 그대로다.
SEGMENT_READINGS: dict[str, str] = {
    "supported": ("판정한 세그먼트에서 기준선 대비 유의한 열세가 관측되지 않음 — 같다는 증거는 아니고, 같은 Validation 에서 "
                  "모델을 골라 모델에 유리한 쪽으로 치우칠 수 있다(rule.selection_effect). 이탈 점수로 가른 세그먼트는 판단 밖이다"),
    "not_supported": "기준선보다 유의하게 낮은 세그먼트가 있다(evidence.below_baseline)",
    "undetermined": "판정한 세그먼트가 없다 — 표본 부족 · 검정 불가(evidence.not_judged)",
}


def evaluate_segment_hypotheses(rows: list[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """``SEGMENT_HYPOTHESES`` 를 이 실행의 세그먼트별 결과로 평가한다 — 규칙은 결과 전에 고정했다(DR-303)."""
    eligible = [r for r in rows if r.get("group") in SEG002_SEGMENTS and r["group"] not in SCORE_RESTRICTED_SEGMENTS]
    judged = [r for r in eligible if (r.get("tests") or {}).get("vs_baseline")]
    below = [r["group"] for r in judged if r["tests"]["vs_baseline"]["below"]]
    result = "undetermined" if not judged else ("not_supported" if below else "supported")
    evidence = {"n_groups_judged": len(judged), "groups_judged": [r["group"] for r in judged], "below_baseline": below,
                "not_judged": {r["group"]: (r.get("small_group_reason") or "검정 불가(한 클래스뿐인 쪽이 있다)")
                               for r in eligible if r not in judged},
                "excluded_score_restricted": list(SCORE_RESTRICTED_SEGMENTS)}
    return [{**SEGMENT_HYPOTHESES[0], "result": result, "reading": SEGMENT_READINGS[result], "evidence": evidence}]


def segment_performance(validation: Mapping[str, Any], segments: pd.Series, *,
                        inputs: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """#303 ML-010 — AI 세그먼트(SEG-002)별 ML-009 지표. 등급 축과 같은 ``group_performance`` · 같은 규칙이다.

    ``segments``: index = customer_id, 값 = ``assign_segments`` 코드. 실행 루프가 t1 라벨을 쓰지 않은 t1 입력으로
    매긴다(DR-303 「AI 세그먼트 축」 — 고객은 Validation 중 탐색 RCT test 분할 T0 고객). 세그먼트가 없는 Validation
    고객은 수를 남기고 전체 지표에만 들어간다. ``inputs`` 는 세그먼트 입력의 출처 · 수 · 경계값 기록이다.

    이탈 점수로 가른 세그먼트(``SCORE_RESTRICTED_SEGMENTS``)는 ``score_restricted`` 로 표시한다 — 약한 고객군 표시 ·
    검정은 그대로 싣지만 점수 범위가 잘린 결과라 가설 판정에 쓰지 않는다.
    """
    groups = pd.DataFrame({SEGMENT_AXIS: pd.Series(segments, dtype=object)})
    result = group_performance(
        validation, groups, {SEGMENT_AXIS: SEGMENT_LABELS},
        population="t1 시간 순서 검증 모집단(탐색 RCT T0 군 — 앞 기준일 학습 모델로 평가)",
        groups_source="t1 입력(t1 라벨을 쓰지 않은 값)으로 매긴 AI 세그먼트 — 탐색 RCT test 분할 T0 고객(DR-303)")
    rows = result["axes"][SEGMENT_AXIS]
    for row in rows:
        row["score_restricted"] = row["group"] in SCORE_RESTRICTED_SEGMENTS
    rule = {**result["rule"], "score_restricted": (
        f"{' · '.join(SCORE_RESTRICTED_SEGMENTS)} 는 고른 모델의 이탈 점수로 가른 고객군이다 — 점수 범위가 잘려 그 모델의 "
        "ROC-AUC 가 구조적으로 낮다. 값 · 검정은 싣고 가설 판정에 쓰지 않는다")}
    return {**result, "rule": rule, "axis_names": {SEGMENT_AXIS: "AI 세그먼트"}, "inputs": dict(inputs or {}),
            "hypotheses": evaluate_segment_hypotheses(rows)}


def _group_names(model, X: pd.DataFrame) -> list[str]:
    """전처리 후 컬럼 → 원 Feature 이름(결측 지시자는 원 Feature 로 묶는다)."""
    imputer = model[0][-1]
    names = list(X.columns)
    if getattr(imputer, "indicator_", None) is not None:
        names += [X.columns[i] for i in imputer.indicator_.features_]
    return names


def churn_importance(X: pd.DataFrame, y: np.ndarray, name: str, seed: int,
                     overrides: Mapping[str, Any] | None = None, top: int = 15) -> dict:
    """SHAP(Tree) 상위 Feature. 실패하면 permutation importance 로 대체하고 그 사실을 남긴다."""
    model = make_model(name, seed, overrides).fit(X, y)
    sample = X.sample(min(SHAP_SAMPLE, len(X)), random_state=seed)
    try:
        import shap

        Z = model[:-1].transform(sample)
        values = shap.TreeExplainer(model[-1]).shap_values(Z)
        values = np.asarray(values)
        if values.ndim == 3:  # (n, p, classes)
            values = values[:, :, 1]
        elif isinstance(values, list):
            values = np.asarray(values[1])
        groups = _group_names(model, X)
        frame = pd.DataFrame(values, columns=range(values.shape[1]))
        grouped = frame.T.groupby(np.asarray(groups)).sum().T  # 같은 Feature 의 지시자 합산
        mean_abs = grouped.abs().mean().sort_values(ascending=False)
        method, note = "shap", f"TreeExplainer · {name} · 전체 데이터 적합 후 표본 {len(sample)}"
    except Exception as error:  # noqa: BLE001 — 실패 사유를 결과에 남긴다
        from sklearn.inspection import permutation_importance

        result = permutation_importance(model, sample, y[X.index.get_indexer(sample.index)],
                                        scoring="roc_auc", n_repeats=5, random_state=seed)
        mean_abs = pd.Series(result.importances_mean, index=X.columns).sort_values(ascending=False)
        method = "permutation"
        note = f"SHAP 실패로 대체: {type(error).__name__}: {error}"[:300]
    return {"method": method, "note": note,
            "top": [{"feature": str(k), "mean_abs": float(v)} for k, v in mean_abs.head(top).items()]}


#: 고객별 설명(SHAP Local)에 싣는 Feature 수 · 고객 수 상한 (#215).
SHAP_LOCAL_TOP = 3
SHAP_LOCAL_CUSTOMERS = 200


def _tree_shap(model: "ChurnModel", X: pd.DataFrame) -> pd.DataFrame:
    """확정 모델(`ChurnModel`)의 고객별 SHAP 값 — 원 Feature 이름으로 묶는다(결측 지시자는 원 Feature 에 합산).

    값은 이탈(양성) 쪽 기여이고 **단위는 모델마다 다르다** — ``SHAP_UNITS``(RF 는 확률, HistGB 는 로그오즈).
    다시 학습하지 않는다 — 배치될 모델 그 자체를 설명한다.
    """
    import shap

    pipe = model.estimator
    Xm = X[model.features].astype(float)
    values = shap.TreeExplainer(pipe[-1]).shap_values(pipe[:-1].transform(Xm))
    if isinstance(values, list):
        values = values[1]
    values = np.asarray(values)
    if values.ndim == 3:  # (n, p, classes)
        values = values[:, :, 1]
    groups = np.asarray(_group_names(pipe, Xm))
    frame = pd.DataFrame(values, index=X.index)
    return frame.T.groupby(groups).sum().T


def explain_local(model: "ChurnModel", X: pd.DataFrame, *, top: int = SHAP_LOCAL_TOP) -> list[dict]:
    """SHAP Local (FR-16, #215) — 고객마다 이탈 확률을 가장 크게 움직인 Feature ``top`` 개와 방향.

    ``direction`` 이 ``raises_risk`` 면 그 Feature 값이 이 고객의 이탈 위험을 높였다는 뜻이다. Feature 값이
    결측이면 None 그대로 싣는다(0 으로 채우지 않는다).
    """
    grouped = _tree_shap(model, X)
    proba = predict_churn_proba(model, X)
    rows = []
    for cid, contrib in grouped.iterrows():
        order = contrib.abs().sort_values(ascending=False).index[:top]
        rows.append({
            "customer_id": str(cid), "churn_proba": float(proba.loc[cid]),
            "top": [{"feature": str(f), "shap": float(contrib[f]),
                     "value": (None if pd.isna(X.at[cid, f]) else float(X.at[cid, f])) if f in X.columns else None,
                     "direction": "raises_risk" if contrib[f] > 0 else "lowers_risk"} for f in order],
        })
    return rows


def explain_top_risk(model: "ChurnModel", X: pd.DataFrame, *, candidates=None,
                     n: int = SHAP_LOCAL_CUSTOMERS, top: int = SHAP_LOCAL_TOP) -> dict:
    """이탈 확률 상위 ``n`` 명의 SHAP Local — 대시보드 Target List 의 "왜 이 고객인가" (#215).

    ``candidates`` 가 있으면(예: Eligible) 그 안에서만 고른다. ``None`` 이면(후보를 정하지 않음) ``X`` 전체에서 고르고
    그렇게 적는다. **후보가 비면(빈 목록 · X 와 교집합 0) 넓히지 않고 빈 결과**다 — Eligible 밖 고객을 설명하지 않는다
    (#280 리뷰 N1). ``shap_unit`` 은 기여값의 단위(``SHAP_UNITS``).
    """
    if candidates is None:
        pool, scope = X.index, "all_scored"
    else:
        pool, scope = X.index.intersection(pd.Index(list(candidates))), "candidates"
    head = {"population": scope, "n_pool": int(len(pool)), "top_features": int(top), "model": model.name,
            "shap_unit": shap_unit(model.name)}
    if not len(pool):
        return {**head, "n": 0, "rows": [], "note": "후보가 비어 있다 — 전체 고객으로 넓히지 않는다"}
    proba = predict_churn_proba(model, X.loc[pool])
    chosen = proba.sort_values(ascending=False, kind="mergesort").index[:n]
    return {**head, "n": int(len(chosen)), "rows": explain_local(model, X.loc[chosen], top=top)}


def write_shap_summary(model: "ChurnModel", X: pd.DataFrame, path, *, seed: int,
                       sample: int = SHAP_SAMPLE, max_display: int = 15) -> dict:
    """``shap_summary.png`` (SRS · FR-16, #215) — 확정 모델의 SHAP 요약 그림(beeswarm)을 ``path`` 에 쓴다."""
    import matplotlib

    matplotlib.use("Agg")  # 화면 없이 그린다(CI · Docker)
    import matplotlib.pyplot as plt
    import shap
    from pathlib import Path

    picked = X.sample(min(sample, len(X)), random_state=seed)
    grouped = _tree_shap(model, picked)
    features = picked.reindex(columns=grouped.columns).astype(float)
    shap.summary_plot(grouped.to_numpy(), features, feature_names=list(grouped.columns),
                      max_display=max_display, show=False)
    plt.title(f"Churn SHAP summary — {model.name} (n={len(picked)})")
    plt.tight_layout()
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    plt.savefig(target, dpi=150)
    plt.close("all")
    return {"status": "ok", "file": target.name, "model": model.name, "n_sample": int(len(picked)),
            "max_display": int(max_display), "method": "TreeExplainer · 확정 모델(재학습 없음)",
            "shap_unit": shap_unit(model.name)}


# ── 학습·예측 ───────────────────────────────────────────────────────────────

@dataclass
class ChurnModel:
    name: str
    estimator: object
    threshold: float
    features: list[str] = field(default_factory=list)
    threshold_rule: str = ""
    #: #215 — Validation 튜닝이 고른 하이퍼파라미터(config 기본값 위에 덮은 것). 비어 있으면 config 기본값.
    params: dict = field(default_factory=dict)


@_limited_threads
def fit_best_churn(X: pd.DataFrame, y, seed: int, *, eval_result: dict | None = None) -> ChurnModel:
    """확정 모델 학습. `eval_result`(= `evaluate_churn_models` 결과)가 있으면 그것이 고른 **제안** 모델
    (`best_proposed` — 시간 순서 검증 또는 CV 기준, `selection_basis`)을 튜닝 값(`best_params`)으로, 없으면
    `hist_gb` 기본값을 쓴다. 임계는 학습 데이터 내부 OOF F1 최대."""
    X, yv = _prepare(X, y)
    name = eval_result["best_proposed"] if eval_result else "hist_gb"
    params = dict((eval_result or {}).get("best_params") or {})  # #215 — 튜닝이 고른 값으로 학습
    factory = lambda: make_model(name, seed, params)  # noqa: E731
    threshold = _threshold_from_train(factory, X, yv, seed)
    return ChurnModel(name=name, estimator=factory().fit(X, yv), threshold=threshold,
                      features=list(X.columns), threshold_rule=f"학습 데이터 내부 {INNER_SPLITS}-fold OOF F1 최대",
                      params=params)


def predict_churn_proba(model: ChurnModel, X: pd.DataFrame) -> pd.Series:
    missing = [c for c in model.features if c not in X.columns]
    if missing:
        raise ValueError(f"학습 때 있던 Feature 가 없다: {missing[:5]}…")
    proba = _score(model.estimator, X[model.features].astype(float))
    return pd.Series(proba, index=X.index, name="churn_proba")


def evaluate_fitted_churn(model: ChurnModel, X: pd.DataFrame, y) -> dict:
    """저장해 둔 **학습된** 모델을 새 데이터로 **평가만** 한다 (#214 — GATE 4 Final Holdout 전제).

    다시 학습하지 않고, 임계도 그 모델이 학습 데이터에서 정한 값을 그대로 쓴다. 이 데이터로 아무것도
    고르지 않는다(모델 · 임계 · Feature 모두 저장된 그대로). 학습 때 있던 Feature 가 없으면 멈춘다.
    """
    if not isinstance(model, ChurnModel):
        raise TypeError(f"ChurnModel 이 아니다: {type(model).__name__}")
    Xp, yv = _prepare(X, y)
    score = predict_churn_proba(model, Xp).to_numpy()
    return {"name": model.name, "scheme": "fitted_model_evaluation", "model_source": "loaded (재학습 없음)",
            "n": int(len(yv)), "pos_rate": float(yv.mean()) if len(yv) else float("nan"),
            "threshold": float(model.threshold), "threshold_rule": model.threshold_rule,
            **_metrics(yv, score, model.threshold)}


@_limited_threads
def evaluate_temporal_holdout(model_factory=None, X_train: pd.DataFrame | None = None, y_train=None,
                              X_test: pd.DataFrame | None = None, y_test=None, *, model=None,
                              seed: int = 0) -> dict:
    """앞 시점으로 학습 → 뒤 시점 고객으로 **1 회** 평가. 시험 데이터로 아무것도 고르지 않는다.

    모델을 주는 방법은 셋이고, 이름 바인딩(#154 `call_by_name`)과 위치 호출을 둘 다 받는다:
      - `model` = `fit_best_churn` 이 돌려준 **학습된** `ChurnModel` → 다시 학습하지 않고 그대로 평가한다
        (`X_train` 으로 학습된 모델이어야 한다 — 호출자 책임. 임계도 그 모델의 학습 OOF 임계).
        `model` 과 `model_factory` 가 함께 오면 `model` 을 쓴다 — 배치될 모델 그 자체를 평가한다.
      - `model_factory` = `MODEL_NAMES` 의 이름, 또는 인자 없는 호출 가능 객체(미학습 추정기 반환)
        → `X_train` 으로 학습하고 임계는 학습 데이터 내부 OOF 에서 정한다.
      - `model` 에 이름·호출 가능 객체를 줘도 `model_factory` 와 같이 다룬다.
    """
    if X_train is None or y_train is None or X_test is None or y_test is None:
        raise ValueError("X_train · y_train · X_test · y_test 가 모두 필요하다")
    spec = model if model is not None else model_factory
    if spec is None:
        raise ValueError("model 또는 model_factory 가 필요하다")
    Xtr, ytr = _prepare(X_train, y_train)
    Xte, yte = _prepare(X_test, y_test)

    if isinstance(spec, ChurnModel):
        name, source = spec.name, "given_fitted_model (재학습 없음)"
        threshold = spec.threshold
        score = predict_churn_proba(spec, Xte).to_numpy()
        metrics = _metrics(yte, score, threshold)
        report = classification_report(yte, score, threshold=threshold)
    else:
        name = spec if isinstance(spec, str) else getattr(spec, "__name__", "custom")
        factory = (lambda: make_model(spec, seed)) if isinstance(spec, str) else spec
        source = "refit_on_X_train"
        Xte = Xte[list(Xtr.columns)]
        fitted = factory().fit(Xtr, ytr)
        score = _score(fitted, Xte)
        if isinstance(fitted, RecencyRule):
            from sklearn.metrics import f1_score
            predicted = fitted._days(Xte) >= fitted.threshold_days_
            metrics = _not_probability(_metrics(yte, score, 0.0))
            metrics["f1"] = float(f1_score(yte, predicted.astype(int), zero_division=0))
            threshold = fitted.threshold_days_
            report = classification_report(yte, score, predicted, threshold=threshold, threshold_unit="days",
                                           probability=False)
        else:
            threshold = _threshold_from_train(factory, Xtr, ytr, seed)
            metrics = _metrics(yte, score, threshold)
            report = classification_report(yte, score, threshold=threshold)
    return {"name": name, "scheme": "temporal_holdout", "model_source": source,
            "n_train": int(len(ytr)), "n_test": int(len(yte)),
            "pos_rate_train": float(ytr.mean()), "pos_rate_test": float(yte.mean()),
            "threshold": float(threshold), "population_audit": temporal_population_audit(
                X_train, y_train, X_test, y_test), **metrics,
            "report": report}  # SRS ML-009 (#303)
