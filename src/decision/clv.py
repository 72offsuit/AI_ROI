"""CLV(미래 매출) 예측 — 스프린트 1 P1 (이슈 #144).

  baseline  `historical_avg`  과거 90일 매출의 일평균 × horizon_days (학습 없음, 외삽)
  proposed  `hist_gb`         HistGradientBoostingRegressor(loss="poisson") — 0 이 많고 오른쪽 꼬리가 긴
                              비음수 매출에 맞는 손실. (log1p+제곱오차 판은 expm1 역변환에서 큰 값이
                              폭주해 CV RMSE 가 기준선의 3.5 배였다 — 픽스처 기준, 검증 fold 판단)

target 은 `build_outcomes(..., window_days=horizon_days)["revenue"]` — index 이후 창 안 순매출.
**이익(CLV)이 아니라 매출이다.** 원가·쿠폰 비용 반영은 측정 계층 경제 규칙(#101·#108)과
합쳐야 하고 스프린트 범위 밖이다.

평가: K-Fold OOF(``config/model_config.yaml`` clv.cv_folds, 기본 5) 예측으로 MAE · RMSE · Spearman ·
상위 20% 적중률(실제 상위 20% 중 예측 상위 20% 에 든 비율). 회귀기 하이퍼파라미터도 그 파일에서 온다(#206). 미래 매출 결손(NaN)·기준선 입력 결손 고객은 평가에서 빼고 각각 그 수를 남긴다.
"""

from __future__ import annotations

import math

import numpy as np
import pandas as pd

from src.decision.config import load_model_config
from src.decision.features.sprint_table import make_preprocessor, model_columns

BASELINE_FEATURE = "monetary_90d"
BASELINE_DAYS = 90
#: config/model_config.yaml `clv` (#206) — fold 수 · 회귀기 하이퍼파라미터. 값은 그 파일 한 곳에만 있다.
CONFIG = load_model_config().clv


def fit_clv(X: pd.DataFrame, future_value, *, seed: int = 0):
    from sklearn.ensemble import HistGradientBoostingRegressor
    from sklearn.pipeline import make_pipeline

    y = pd.Series(future_value).reindex(X.index).astype(float)
    keep = y.notna().to_numpy()
    if (y[keep] < 0).any():
        raise ValueError("미래 매출이 음수다 — poisson 손실 전제가 깨진다")
    model = make_pipeline(make_preprocessor(), HistGradientBoostingRegressor(
        **CONFIG.hist_gb, random_state=seed))
    features = model_columns(X)
    model.fit(X.loc[keep, features].astype(float), y[keep].to_numpy())
    model.features_ = features
    return model


def predict_clv(model, X: pd.DataFrame) -> pd.Series:
    pred = model.predict(X[model.features_].astype(float))
    return pd.Series(np.clip(pred, 0, None), index=X.index, name="clv_pred")


def baseline_clv(X: pd.DataFrame, horizon_days: int) -> pd.Series:
    """과거 90일 매출 일평균의 외삽. 학습하지 않는다."""
    return (X[BASELINE_FEATURE].astype(float) / BASELINE_DAYS * horizon_days).rename("clv_baseline")


def top_hit(actual: np.ndarray, pred: np.ndarray, frac: float = 0.2) -> float:
    k = max(1, int(math.ceil(len(actual) * frac)))
    true_top = set(np.argsort(-actual, kind="mergesort")[:k])
    pred_top = set(np.argsort(-pred, kind="mergesort")[:k])
    return len(true_top & pred_top) / k


def _scores(actual: np.ndarray, pred: np.ndarray) -> dict[str, float]:
    from scipy.stats import spearmanr

    rho = spearmanr(actual, pred).statistic if np.std(pred) > 0 and np.std(actual) > 0 else float("nan")
    return {"mae": float(np.mean(np.abs(actual - pred))),
            "rmse": float(np.sqrt(np.mean((actual - pred) ** 2))),
            "spearman": float(rho), "top20_hit": float(top_hit(actual, pred, 0.2))}


def evaluate_fitted_clv(model, X: pd.DataFrame, future_value) -> dict:
    """저장해 둔 **학습된** CLV 모델을 새 데이터로 **평가만** 한다 (#214 — GATE 4 전제). 다시 학습하지 않는다.

    미래 매출이 결손인 고객은 빼고 건수를 남긴다(0 으로 채우지 않는다).
    """
    y = pd.Series(future_value).reindex(X.index).astype(float)
    keep = y.notna().to_numpy()
    pred = predict_clv(model, X.loc[keep]).to_numpy()
    return {"name": "hist_gb", "scheme": "fitted_model_evaluation", "model_source": "loaded (재학습 없음)",
            "n": int(keep.sum()), "n_excluded_missing_target": int((~keep).sum()),
            **_scores(y[keep].to_numpy(), pred)}


def evaluate_clv(X: pd.DataFrame, future_value, *, horizon_days: int = 42, seed: int = 0,
                 n_splits: int = CONFIG.cv_folds) -> dict:
    from sklearn.model_selection import KFold

    y = pd.Series(future_value).reindex(X.index).astype(float)
    base_all = baseline_clv(X, horizon_days)
    # 두 모델을 **같은 고객**으로 비교한다. 미래 매출 결손, 또는 기준선 입력(90일 매출)이
    # 결손(금액 결손 주문)인 고객은 빼고 각각 센다 — 0 으로 채워 넣지 않는다.
    keep_target = y.notna().to_numpy()
    keep = keep_target & base_all.notna().to_numpy()
    Xk, yk = X.loc[keep], y[keep].to_numpy()
    oof = np.empty(len(yk), dtype=float)
    for tr, va in KFold(n_splits, shuffle=True, random_state=seed).split(Xk):
        model = fit_clv(Xk.iloc[tr], pd.Series(yk[tr], index=Xk.index[tr]), seed=seed)
        oof[va] = predict_clv(model, Xk.iloc[va]).to_numpy()
    base = base_all[keep].to_numpy()
    return {
        "horizon_days": int(horizon_days), "n": int(len(yk)), "n_excluded_missing_target": int((~keep_target).sum()),
        "n_excluded_baseline_unavailable": int((keep_target & ~keep).sum()),
        "target": "index 이후 horizon 창 순매출(원) — 이익 아님",
        "cv_scheme": f"KFold(n_splits={n_splits}, shuffle=True, random_state={seed}) OOF",
        "models": [
            {"name": "historical_avg", "kind": "baseline", **_scores(yk, base)},
            {"name": "hist_gb", "kind": "proposed", **_scores(yk, oof)},
        ],
    }
