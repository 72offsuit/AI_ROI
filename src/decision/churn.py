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

import math
import hashlib
import json
from dataclasses import dataclass, field
from typing import Callable

import numpy as np
import pandas as pd

from src.decision.config import load_model_config
from src.decision.features.sprint_table import LABEL_DEF, make_preprocessor, model_columns

BASELINES = ("rule_recency", "logistic_regression")
PROPOSED = ("random_forest", "hist_gb")
MODEL_NAMES = BASELINES + PROPOSED
#: config/model_config.yaml `churn` (#206). 값은 그 파일 한 곳에만 있다 — 여기에 숫자를 다시 쓰지 않는다.
CONFIG = load_model_config().churn
N_SPLITS = CONFIG.cv_folds
INNER_SPLITS = CONFIG.threshold_inner_folds
SHAP_SAMPLE = CONFIG.shap_sample


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


def make_model(name: str, seed: int):
    """이름 → 미학습 추정기. 대치·절단은 파이프라인 안(학습 데이터로만 fit).

    하이퍼파라미터는 ``CONFIG.models[name]``(config/model_config.yaml), ``random_state`` 는 ``seed`` 다.
    """
    from sklearn.ensemble import HistGradientBoostingClassifier, RandomForestClassifier
    from sklearn.linear_model import LogisticRegression
    from sklearn.pipeline import make_pipeline
    from sklearn.preprocessing import StandardScaler

    if name == "rule_recency":
        return RecencyRule()
    params = CONFIG.models
    if name == "logistic_regression":
        return make_pipeline(make_preprocessor(), StandardScaler(),
                             LogisticRegression(**params["logistic_regression"]))
    if name == "random_forest":
        return make_pipeline(make_preprocessor(), RandomForestClassifier(
            **params["random_forest"], random_state=seed))
    if name == "hist_gb":
        return make_pipeline(make_preprocessor(), HistGradientBoostingClassifier(
            **params["hist_gb"], random_state=seed))
    raise ValueError(f"알 수 없는 모델: {name!r} (허용: {MODEL_NAMES})")


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
#: 실측(shap 0.54.1 · sklearn 1.9): random_forest = 양성 확률(오차 ~1e-15), hist_gb = 양성 로그오즈(~1e-14).
#: 표에 없는 모델은 None — 확인하지 않은 단위를 적지 않는다.
SHAP_UNITS = {"random_forest": "probability", "hist_gb": "log_odds"}


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


# ── 평가 ────────────────────────────────────────────────────────────────────

def evaluate_churn_models(X: pd.DataFrame, y, seed: int) -> dict:
    """Baseline 2 + 제안 2 를 같은 Stratified K-Fold(``N_SPLITS``)로 평가한다. 형식은 모듈 설명 참조."""
    X, yv = _prepare(X, y)
    folds = fold_indices(yv, seed)
    models = []
    oof: dict[str, np.ndarray] = {}  # 검증 fold 예측 — 임계값 비교표 · 보정표(#215)
    for name in MODEL_NAMES:
        per_fold: dict[str, list[float]] = {"roc_auc": [], "pr_auc": [], "f1": [], "lift_at_10": [],
                                            "brier": [], "ece": []}
        thresholds = []
        oof[name] = np.full(len(yv), np.nan)
        for k, (tr, va) in enumerate(folds):
            factory = (lambda n=name, s=seed + k: make_model(n, s))
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
                per_fold[key].append(value)
        entry = {"name": name, "kind": _kind(name),
                 "cv": {key: _summary(values) for key, values in per_fold.items()},
                 "threshold": {"rule": ("학습 fold F1 최대 경과일(days)" if name == "rule_recency"
                                        else f"학습 fold 내부 {INNER_SPLITS}-fold OOF F1 최대 확률"),
                               "per_fold": [float(t) for t in thresholds]}}
        models.append(entry)

    best = max((m for m in models if m["kind"] == "proposed"),
               key=lambda m: m["cv"]["roc_auc"]["mean"] or -1)
    importance = churn_importance(X, yv, best["name"], seed)
    best_oof = oof[best["name"]]
    return {
        "label_def": LABEL_DEF, "n": int(len(yv)), "pos_rate": float(yv.mean()),
        "n_features": int(X.shape[1]), "seed": int(seed),
        "cv_scheme": f"StratifiedKFold(n_splits={len(folds)}, shuffle=True, random_state={seed})",
        "imbalance": "class_weight (balanced / balanced_subsample), rule 은 F1 임계",
        "models": models,
        "best_proposed": best["name"],
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


def _group_names(model, X: pd.DataFrame) -> list[str]:
    """전처리 후 컬럼 → 원 Feature 이름(결측 지시자는 원 Feature 로 묶는다)."""
    imputer = model[0][-1]
    names = list(X.columns)
    if getattr(imputer, "indicator_", None) is not None:
        names += [X.columns[i] for i in imputer.indicator_.features_]
    return names


def churn_importance(X: pd.DataFrame, y: np.ndarray, name: str, seed: int, top: int = 15) -> dict:
    """SHAP(Tree) 상위 Feature. 실패하면 permutation importance 로 대체하고 그 사실을 남긴다."""
    model = make_model(name, seed).fit(X, y)
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


def fit_best_churn(X: pd.DataFrame, y, seed: int, *, eval_result: dict | None = None) -> ChurnModel:
    """확정 모델 학습. `eval_result`(= `evaluate_churn_models` 결과)가 있으면 CV ROC-AUC 평균이
    가장 높은 **제안** 모델을, 없으면 `hist_gb` 를 쓴다. 임계는 학습 데이터 내부 OOF F1 최대."""
    X, yv = _prepare(X, y)
    name = eval_result["best_proposed"] if eval_result else "hist_gb"
    factory = lambda: make_model(name, seed)  # noqa: E731
    threshold = _threshold_from_train(factory, X, yv, seed)
    return ChurnModel(name=name, estimator=factory().fit(X, yv), threshold=threshold,
                      features=list(X.columns), threshold_rule=f"학습 데이터 내부 {INNER_SPLITS}-fold OOF F1 최대")


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
        metrics = _metrics(yte, predict_churn_proba(spec, Xte).to_numpy(), threshold)
    else:
        name = spec if isinstance(spec, str) else getattr(spec, "__name__", "custom")
        factory = (lambda: make_model(spec, seed)) if isinstance(spec, str) else spec
        source = "refit_on_X_train"
        Xte = Xte[list(Xtr.columns)]
        fitted = factory().fit(Xtr, ytr)
        if isinstance(fitted, RecencyRule):
            from sklearn.metrics import f1_score
            metrics = _not_probability(_metrics(yte, _score(fitted, Xte), 0.0))
            metrics["f1"] = float(f1_score(yte, (fitted._days(Xte) >= fitted.threshold_days_).astype(int),
                                           zero_division=0))
            threshold = fitted.threshold_days_
        else:
            threshold = _threshold_from_train(factory, Xtr, ytr, seed)
            metrics = _metrics(yte, _score(fitted, Xte), threshold)
    return {"name": name, "scheme": "temporal_holdout", "model_source": source,
            "n_train": int(len(ytr)), "n_test": int(len(yte)),
            "pos_rate_train": float(ytr.mean()), "pos_rate_test": float(yte.mean()),
            "threshold": float(threshold), "population_audit": temporal_population_audit(
                X_train, y_train, X_test, y_test), **metrics}
