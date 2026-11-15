"""Uplift(CATE) 모델과 평가 — 이슈 #145 (D4 의 스프린트 판, UP-002·003·005).

순수 함수다. 입력은 ``X``(고객 × Feature, index = customer_id), ``treatment``(``T0``~``T4``
문자열), ``y``(창 내 구매=1 같은 이진 결과 또는 이익 같은 연속 결과)이다. 데이터 출처
(시뮬레이터·커머스·공개 벤치마크)와 무관하다. **시뮬레이터 코드·정답지를 보지 않는다.**

메타러너 3종 — 기저 학습기는 sklearn ``HistGradientBoostingRegressor``(결측 자체 처리):

* ``s_learner`` (Baseline) — 처치 원-핫을 Feature 로 넣은 단일 모델. 트리가 처치 변수를
  무시하면 CATE 가 0 으로 수축하는 알려진 편향이 있어 비교 기준으로 둔다.
* ``t_learner`` (제안) — 처치군마다 따로 학습, ``μ_t(x) − μ_0(x)``.
* ``x_learner`` (제안) — Künzel et al. (2019). 성향점수는 **무작위 배정**(SRS SIM-010
  기본값)을 전제로 표본 비율 상수를 쓴다. 관측 데이터에 쓰면 이 전제가 깨진다.

Qini·AUUC 는 직접 구현한다(외부 uplift 패키지 금지). 정의는 ``qini_curve`` docstring.

처치군 표본이 ``MIN_ARM_N`` 보다 적으면 그 열의 CATE 는 **NaN(계산 불가)** 이다 — 0 이 아니다.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Mapping
import hashlib
import itertools
import json

import numpy as np
import pandas as pd

from src.decision.config import load_model_config

#: config/model_config.yaml ``uplift`` — DR-206 이 미룬 상수 4개를 #217 3부에서 옮겼다(값은 그대로).
CONFIG = load_model_config().uplift

CONTROL = "T0"
TREATED = ("T1", "T2", "T3", "T4")
ARMS = (CONTROL, *TREATED)
METHODS = ("s_learner", "t_learner", "x_learner")
METHOD_KIND = {"s_learner": "baseline", "t_learner": "proposed", "x_learner": "proposed"}
#: 처치군(또는 대조군) 최소 표본. 이보다 적으면 그 처치의 CATE 는 계산 불가.
MIN_ARM_N = CONFIG.min_arm_n
#: 학습·예측 시 OpenMP 스레드 수. None 이면 제한하지 않는다.
N_THREADS: int | None = 1
#: Qini 곡선 점 개수 상한(대시보드 페이로드 크기).
CURVE_POINTS = 50
METRIC_VERSION = "tied-endpoints-v1"
TOPK_VERSION = "fractional-boundary-v1"
#: PRD §15.1 — Uplift MVP 는 T0 vs T3 이진 처치. 평가의 대표 처치군 기본값.
DEFAULT_PRIMARY_ARM = CONFIG.primary_arm
#: numpy 2.0 에서 trapz → trapezoid 로 이름이 바뀌었다. 고정 버전이 정해지기 전이라 둘 다 받는다.
_trapezoid = getattr(np, "trapezoid", None) or np.trapz


# ── 전처리 ───────────────────────────────────────────────────────────────────

def _prep_X(X: pd.DataFrame, columns: list[str] | None = None) -> pd.DataFrame:
    """범주형은 원-핫, 숫자형은 float. 결측(NaN)은 그대로 둔다 — HistGB 가 처리한다.

    원-핫의 0 은 "그 범주가 아니다" 라는 관측값이지 결손 대체가 아니다.
    """
    if not isinstance(X, pd.DataFrame):
        raise TypeError("X 는 pandas DataFrame 이어야 한다")
    cat = [c for c in X.columns if not pd.api.types.is_numeric_dtype(X[c]) or pd.api.types.is_bool_dtype(X[c])]
    num = X.drop(columns=cat).astype(float)
    if cat:
        dummies = pd.get_dummies(X[cat].astype("string"), prefix=cat, dtype=float)
        # 결측 범주는 원-핫 전부 0 이 되지 않도록 NaN 으로 되돌린다.
        for c in cat:
            miss = X[c].isna()
            if miss.any():
                cols = [d for d in dummies.columns if d.startswith(f"{c}_")]
                dummies.loc[miss, cols] = np.nan
        out = pd.concat([num, dummies], axis=1)
    else:
        out = num
    if columns is not None:
        missing = [c for c in columns if c not in out.columns and not any(c.startswith(f"{k}_") for k in cat)]
        if missing:
            raise KeyError(f"예측 X 에 학습 Feature 가 없다: {missing[:5]}")
        out = out.reindex(columns=columns, fill_value=0.0)
    return out


def _check_inputs(X: pd.DataFrame, treatment: pd.Series, y: pd.Series):
    """검증 후 ``(X, treatment, y, n_outcome_missing)``.

    결과(y) 결측 행은 **제외하고 건수를 돌려준다** — 0 으로 채우지 않는다. 결과를 모르는
    고객은 처치 효과의 증거가 아니다. X 의 결측(NaN)은 그대로 둔다(HistGB 가 처리).
    """
    if len(X) != len(treatment) or len(X) != len(y):
        raise ValueError("X · treatment · y 길이가 다르다")
    if not X.index.is_unique or X.index.hasnans:
        raise ValueError("공통 평가 입력의 고객 ID는 중복·결손이 없어야 한다")
    treatment = pd.Series(treatment).set_axis(X.index).astype(str)
    y = pd.Series(y).set_axis(X.index).astype(float)
    if np.isinf(y.to_numpy()).any():
        raise ValueError("평가 결과에 비유한 값이 있다")
    bad = sorted(set(treatment) - set(ARMS))
    if bad:
        raise ValueError(f"알 수 없는 처치 값: {bad[:5]} (T0~T4 만 허용)")
    keep = y.notna().to_numpy()
    n_missing = int((~keep).sum())
    if n_missing:
        X, treatment, y = X[keep], treatment[keep], y[keep]
    if (treatment == CONTROL).sum() < MIN_ARM_N:
        raise ValueError(f"대조군(T0) 표본이 {MIN_ARM_N} 미만이다 — CATE 를 계산할 수 없다")
    return X, treatment, y, n_missing


#: 기저 학습기 설정(현행값 = 튜닝 격자의 첫 후보). 처치군마다 따로 학습하므로 군당 표본이 수백 건이어도
#: 버티도록 얕고 강하게 규제한다. 이 값은 **테스트 합성 데이터**에서 골랐다(DR-145) — #217 3부부터 실행마다
#: Validation Qini 로 ``TUNING`` 격자에서 다시 고른다(DR-217-uplift-tuning). 값은 config 한 곳에만 있다.
BASE_LEARNER = dict(CONFIG.base_learner)
#: config ``uplift.tuning`` — {enabled, metric, grid: {인자: (후보, …)}}. 결과 전에 고정했다.
TUNING = CONFIG.tuning


def _regressor(seed: int, params: Mapping[str, Any]):
    from sklearn.ensemble import HistGradientBoostingRegressor

    return HistGradientBoostingRegressor(random_state=seed, **params)


def regularization_candidates(base: Mapping[str, Any] | None = None,
                              tuning: Mapping[str, Any] | None = None) -> list[dict[str, Any]]:
    """규제 후보 목록 — **현행값(base) 이 첫째**, 이어서 격자 곱집합(축 이름 순 · 값은 오름차순). 중복은 한 번만.

    값 순서는 config 배열 순서가 아니라 **오름차순으로 정렬**한다 — 동점이면 앞선 후보가 이기므로 순서가 규약이다
    (PR #294 리뷰 4 · DR-217-uplift-tuning 구현 명확화 2). ``tuning.enabled`` 가 거짓이면 현행값 하나뿐이다.
    """
    base = dict(BASE_LEARNER if base is None else base)
    tuning = TUNING if tuning is None else tuning
    out = [base]
    if tuning.get("enabled"):
        grid = tuning["grid"]
        keys = sorted(grid)
        for values in itertools.product(*(tuple(sorted(grid[k])) for k in keys)):
            cand = {**base, **dict(zip(keys, values))}
            if cand not in out:
                out.append(cand)
    return out


def screen_features(Xp: pd.DataFrame) -> dict[str, list[str]]:
    """학습에 쓸 수 없는 열 — **값이 전부 NaN** 이거나 **결측 없이 한 값뿐(상수)** 인 열.

    전부 NaN 인 열은 sklearn 1.9 HistGB 의 비닝에서 ``ValueError: window shape cannot be
    larger than input array shape`` 로 학습을 멈춘다(스프린트 통합 스모크에서 발견).
    상수 열은 정보가 없다. 둘 다 **제외하고 목록을 남긴다** — 0 으로 채우지 않는다.
    '한 값 + 결측' 열은 결측 여부 자체가 정보이므로 남긴다.
    """
    all_nan = [c for c in Xp.columns if Xp[c].isna().all()]
    constant = [c for c in Xp.columns
                if c not in all_nan and not Xp[c].isna().any() and Xp[c].nunique() <= 1]
    return {"all_nan": all_nan, "constant": constant}


@dataclass
class _SubModel:
    """기저 학습기 1 개 + 그것이 실제로 쓴 열. 열이 하나도 없으면 학습 표본의 평균을 낸다."""
    cols: list[str]
    est: Any = None
    const: float | None = None
    dropped: list[str] = field(default_factory=list)

    def predict(self, Xdf: pd.DataFrame) -> np.ndarray:
        if self.est is None:
            return np.full(len(Xdf), self.const, dtype=float)
        return self.est.predict(Xdf[self.cols])


def _fit_sub(seed: int, Xdf: pd.DataFrame, y: np.ndarray, params: Mapping[str, Any]) -> _SubModel:
    """부분 표본(처치군 하나 등)에서도 전부 NaN·상수 열을 다시 걸러 학습한다.

    전체 학습셋에서는 값이 있어도 **한 처치군 안에서만** 전부 NaN 인 열이 같은 오류를 낸다."""
    scr = screen_features(Xdf)
    drop = set(scr["all_nan"]) | set(scr["constant"])
    cols = [c for c in Xdf.columns if c not in drop]
    if not cols:
        return _SubModel(cols=[], const=float(np.mean(y)), dropped=sorted(drop))
    return _SubModel(cols=cols, est=_regressor(seed, params).fit(Xdf[cols], y), dropped=sorted(drop))


# ── 모델 ─────────────────────────────────────────────────────────────────────

@dataclass
class UpliftModel:
    method: str
    columns: list[str]
    arms: list[str]                       # CATE 를 계산할 수 있는 처치군
    models: dict[str, Any] = field(default_factory=dict)
    propensity: dict[str, float] = field(default_factory=dict)
    n_by_arm: dict[str, int] = field(default_factory=dict)
    n_outcome_missing_excluded: int = 0
    #: 학습셋 전체에서 제외한 열(``screen_features``). ``columns`` 에는 들어 있지 않다.
    dropped_features: dict[str, list[str]] = field(default_factory=dict)
    #: 하위 모델(처치군별 등)에서 **추가로** 제외한 열 — 부분 표본에서만 전부 NaN·상수인 열.
    submodel_dropped: dict[str, list[str]] = field(default_factory=dict)
    #: #217 3부 — 학습에 쓴 기저 학습기 인자. #217 3부 전에 저장한 객체에는 없다(``getattr(…, None)``).
    base_learner: dict[str, Any] = field(default_factory=dict)


def _threads():
    """OpenMP 스레드 상한. 작은 모델을 여러 개 학습할 때 스레드 경합으로 8 배 가까이
    느려지는 것을 측정했다(합성 2,500 건 테스트 27 s → 3.5 s). threadpoolctl 은
    scikit-learn 의 필수 의존성이다."""
    from threadpoolctl import threadpool_limits

    return threadpool_limits(limits=N_THREADS, user_api="openmp")


def fit_uplift(X: pd.DataFrame, treatment: pd.Series, y: pd.Series,
               method: str = "t_learner", seed: int = 0, params: Mapping[str, Any] | None = None) -> UpliftModel:
    """메타러너를 학습한다. ``method`` ∈ ``METHODS``. ``params`` 는 기저 학습기 인자 전체(없으면 현행값 ``BASE_LEARNER``)
    — 실행 루프는 ``evaluate_uplift_models`` 가 Validation 으로 고른 값을 넘긴다."""
    with _threads():
        return _fit_uplift(X, treatment, y, method, seed, dict(BASE_LEARNER if params is None else params))


def _fit_uplift(X: pd.DataFrame, treatment: pd.Series, y: pd.Series,
                method: str, seed: int, params: dict[str, Any]) -> UpliftModel:
    if method not in METHODS:
        raise ValueError(f"method 는 {METHODS} 중 하나다: {method!r}")
    X, treatment, y, n_missing = _check_inputs(X, treatment, y)
    Xp = _prep_X(X)
    screened = screen_features(Xp)
    drop = set(screened["all_nan"]) | set(screened["constant"])
    Xp = Xp[[c for c in Xp.columns if c not in drop]]
    n_by_arm = {a: int((treatment == a).sum()) for a in ARMS}
    arms = [a for a in TREATED if n_by_arm[a] >= MIN_ARM_N]
    model = UpliftModel(method=method, columns=list(Xp.columns), arms=arms, n_by_arm=n_by_arm,
                        n_outcome_missing_excluded=n_missing, dropped_features=screened, base_learner=dict(params))
    ctrl = (treatment == CONTROL).to_numpy()

    def sub(name: str, seed_: int, Xdf: pd.DataFrame, target: np.ndarray) -> _SubModel:
        m = _fit_sub(seed_, Xdf, target, params)
        if m.dropped:
            model.submodel_dropped[name] = m.dropped
        model.models[name] = m
        return m

    if method == "s_learner":
        use = treatment.isin([CONTROL, *arms]).to_numpy()
        sub("s", seed, _with_arm_onehot(Xp[use], treatment[use], arms), y[use].to_numpy())
        return model

    mu0 = sub(CONTROL, seed, Xp[ctrl], y[ctrl].to_numpy())
    for i, a in enumerate(arms):
        ta = (treatment == a).to_numpy()
        mu_t = sub(a, seed + i + 1, Xp[ta], y[ta].to_numpy())
        if method == "x_learner":
            d_t = y[ta].to_numpy() - mu0.predict(Xp[ta])          # 처치군의 대체 효과
            d_c = mu_t.predict(Xp[ctrl]) - y[ctrl].to_numpy()     # 대조군의 대체 효과
            sub(f"tau_t:{a}", seed + 100 + i, Xp[ta], d_t)
            sub(f"tau_c:{a}", seed + 200 + i, Xp[ctrl], d_c)
            model.propensity[a] = n_by_arm[a] / (n_by_arm[a] + n_by_arm[CONTROL])
    return model


def _with_arm_onehot(Xp: pd.DataFrame, treatment: pd.Series, arms: list[str]) -> pd.DataFrame:
    out = Xp.copy()
    for a in arms:
        out[f"__arm_{a}"] = (treatment.to_numpy() == a).astype(float)
    return out


def predict_cate(model: UpliftModel, X: pd.DataFrame) -> pd.DataFrame:
    """고객별 CATE(각 처치 vs T0). 열은 항상 T1~T4, 학습 불가 처치군은 NaN."""
    with _threads():
        return _predict_cate(model, X)


def _predict_cate(model: UpliftModel, X: pd.DataFrame) -> pd.DataFrame:
    # 학습 때 쓴 열 집합(model.columns — 제외 열 빠짐)으로 맞춘다. 하위 모델은 그중 자기 열만 쓴다.
    Xp = _prep_X(X, model.columns)
    out = pd.DataFrame(np.nan, index=X.index, columns=list(TREATED))
    if model.method == "s_learner":
        m = model.models["s"]
        base = m.predict(_with_arm_onehot(Xp, pd.Series([CONTROL] * len(Xp)), model.arms))
        for a in model.arms:
            out[a] = m.predict(_with_arm_onehot(Xp, pd.Series([a] * len(Xp)), model.arms)) - base
        return out
    mu0 = model.models[CONTROL].predict(Xp)
    for a in model.arms:
        if model.method == "t_learner":
            out[a] = model.models[a].predict(Xp) - mu0
        else:
            g = model.propensity[a]
            out[a] = g * model.models[f"tau_c:{a}"].predict(Xp) + (1 - g) * model.models[f"tau_t:{a}"].predict(Xp)
    return out


# ── 평가 지표 ────────────────────────────────────────────────────────────────

def _sorted_cumsums(score: np.ndarray, treated: np.ndarray, y: np.ndarray):
    order = np.argsort(-score, kind="mergesort")
    t = treated[order].astype(float)
    yy = y[order]
    n_t = np.cumsum(t)
    n_c = np.cumsum(1 - t)
    y_t = np.cumsum(yy * t)
    y_c = np.cumsum(yy * (1 - t))
    ends = np.flatnonzero(np.r_[score[order][1:] != score[order][:-1], True])
    return n_t[ends], n_c[ends], y_t[ends], y_c[ends], ends + 1


def _metric_inputs(score, treated, y):
    score, raw_t, y = np.asarray(score, dtype=float), np.asarray(treated), np.asarray(y, dtype=float)
    if any(a.ndim != 1 for a in (score, raw_t, y)) or not (len(score) == len(raw_t) == len(y)):
        raise ValueError("점수·처치·결과는 같은 길이의 1차원 배열이어야 한다")
    if not np.isfinite(score).all() or not np.isfinite(y).all() or not np.isin(raw_t, [0, 1]).all():
        raise ValueError("점수·결과는 유한해야 하며 처치는 이진이어야 한다")
    return score, raw_t.astype(bool), y


def score_ties(score) -> dict[str, Any]:
    values = np.asarray(score, dtype=float)
    _, counts = np.unique(values, return_counts=True)
    n = len(values)
    return {"n": n, "n_unique_scores": len(counts),
            "n_tied_customers": int(counts[counts > 1].sum()),
            "tied_customer_fraction": float(counts[counts > 1].sum() / n) if n else None,
            "duplicate_score_fraction": float((n - len(counts)) / n) if n else None,
            "largest_tie": int(counts.max()) if n else 0}


def qini_curve(score, treated, y, points: int = CURVE_POINTS) -> dict[str, Any]:
    """Qini 곡선(Radcliffe 2007)과 계수.

    점수 내림차순 상위 k 명에서
      ``gain(k) = Y_t(k) − Y_c(k) · N_t(k) / N_c(k)`` (N_c(k)=0 이면 0),
    를 처치군 전체 크기 ``N_T`` 로 나눈 값을 x = k/N 에 대해 그린다. 단위는
    "처치군 1인당 증분 결과" 다. **Qini 계수 = 모델 곡선 아래 넓이 − 무작위 직선
    (0,0)→(1, gain(N)/N_T) 아래 넓이** (사다리꼴 적분). 0 이면 무작위 타깃팅과 같다.

    AUUC 는 uplift 곡선 ``u(k) = (Ȳ_t(k) − Ȳ_c(k)) · k/N`` 아래 넓이다(상위 k 명의 평균 처치
    효과 × 도달 비율). 무작위 타깃팅의 기대값은 전체 ATE/2 다.

    #179 tied-endpoints-v1: k는 동점 묶음 끝점만 사용한다. 면적과 표시 곡선의 정의가 같고,
    무작위 동점 순서의 기댓값을 계산하는 규약은 아니다. 무동점 값은 이전 정의와 같다.
    """
    score, treated, y = _metric_inputs(score, treated, y)
    if type(points) is not int or points < 2:
        raise ValueError("표시 점 수는 2 이상의 정수여야 한다")
    n = len(score)
    N_T, N_C = treated.sum(), (~treated).sum()
    if n == 0 or N_T == 0 or N_C == 0:
        raise ValueError("처치군·대조군이 모두 있어야 Qini 를 계산한다")
    n_t, n_c, y_t, y_c, ends = _sorted_cumsums(score, treated, y)
    with np.errstate(divide="ignore", invalid="ignore"):
        gain = np.where(n_c > 0, y_t - y_c * n_t / np.where(n_c > 0, n_c, 1), 0.0) / N_T
        mean_t = np.where(n_t > 0, y_t / np.where(n_t > 0, n_t, 1), np.nan)
        mean_c = np.where(n_c > 0, y_c / np.where(n_c > 0, n_c, 1), np.nan)
    x = ends / n
    xs = np.concatenate([[0.0], x])
    gs = np.concatenate([[0.0], gain])
    uplift = np.nan_to_num((mean_t - mean_c) * x, nan=0.0)   # 한쪽 군이 없는 앞부분은 정의상 증분 0
    us = np.concatenate([[0.0], uplift])
    area_model = float(_trapezoid(gs, xs))
    area_random = float(gs[-1] / 2.0)
    idx = np.unique(np.round(np.linspace(0, len(xs) - 1, min(points, len(xs)))).astype(int))
    curve = [[round(float(xs[i]), 4), round(float(gs[i]), 6)] for i in idx]
    return {
        "qini": area_model - area_random,
        "auuc": float(_trapezoid(us, xs)),
        "curve": curve,
        "metric_version": METRIC_VERSION,
        "score_ties": score_ties(score),
    }


def uplift_at_k(score, treated, y, fraction: float) -> float | None:
    """경계 동점에 비례 가중한 상위 k의 평균 차. 무작위 추출 평균 비율과는 다르다."""
    return uplift_at_k_details(score, treated, y, fraction)["value"]


def uplift_at_k_details(score, treated, y, fraction: float) -> dict[str, Any]:
    score, treated, y = _metric_inputs(score, treated, y)
    if not np.isfinite(fraction) or not 0 < fraction <= 1 or not len(score):
        raise ValueError("Top-k 비율은 (0,1]이고 표본이 있어야 한다")
    k = max(1, int(round(len(score) * fraction)))
    boundary = np.partition(score, len(score) - k)[len(score) - k]
    above, ties = score > boundary, score == boundary
    weight = (k - int(above.sum())) / int(ties.sum())
    weights = above.astype(float) + ties * weight
    nt, nc = float(weights[treated].sum()), float(weights[~treated].sum())
    value = (float(np.dot(weights[treated], y[treated]) / nt - np.dot(weights[~treated], y[~treated]) / nc)
             if nt > 0 and nc > 0 else None)
    return {"value": value, "version": TOPK_VERSION, "nominal_k": k, "effective_k": float(weights.sum()),
            "effective_fraction": float(weights.sum() / len(score)), "boundary_score": float(boundary),
            "boundary_n": int(ties.sum()), "boundary_weight": weight, "weight_treated": nt,
            "weight_control": nc, "status": "ok" if value is not None else "not_run"}


def ate_with_ci(y_t, y_c, z: float = 1.959963984540054) -> dict[str, Any]:
    """평균 차와 Welch 정규근사 95% CI. 무작위 배정 전제."""
    y_t = np.asarray(y_t, dtype=float)
    y_c = np.asarray(y_c, dtype=float)
    if len(y_t) < 2 or len(y_c) < 2:
        return {"value": None, "ci95": None, "n_t": int(len(y_t)), "n_c": int(len(y_c)),
                "status": "계산 불가 — 표본 2 미만"}
    diff = float(y_t.mean() - y_c.mean())
    se = float(np.sqrt(y_t.var(ddof=1) / len(y_t) + y_c.var(ddof=1) / len(y_c)))
    return {"value": diff, "ci95": [diff - z * se, diff + z * se], "se": se,
            "n_t": int(len(y_t)), "n_c": int(len(y_c))}


# ── 비교 평가 ────────────────────────────────────────────────────────────────

def _score_row(name: str, kind: str, score, treated, y, curve: bool) -> dict[str, Any]:
    q = qini_curve(score, treated, y)
    top = {key: uplift_at_k_details(score, treated, y, frac) for key, frac in (("10", 0.10), ("30", 0.30))}
    row = {"name": name, "kind": kind, "qini": q["qini"], "auuc": q["auuc"],
           "uplift_at_k": {key: info["value"] for key, info in top.items()},
           "uplift_at_k_details": top, "metric_version": METRIC_VERSION, "score_ties": q["score_ties"]}
    if curve:
        row["qini_curve"] = q["curve"]
    return row


def evaluate_fitted_uplift(model: UpliftModel, X: pd.DataFrame, treatment: pd.Series, y: pd.Series) -> dict[str, Any]:
    """저장해 둔 **학습된** 메타러너를 새 무작위 실험 데이터로 **평가만** 한다 (#214 — GATE 4 전제).

    다시 학습하지 않는다. 처치군마다 (그 처치 + T0) 고객으로 Qini · AUUC · uplift@k 를 내고, 무작위 배정
    전제의 ATE 를 함께 싣는다. 결과 결측 고객은 빼고 건수를 남긴다(0 으로 채우지 않는다).
    """
    if not isinstance(model, UpliftModel):
        raise TypeError(f"UpliftModel 이 아니다: {type(model).__name__}")
    t = pd.Series(treatment).reindex(X.index)
    yv = pd.Series(y).reindex(X.index).astype(float)
    keep = (yv.notna() & t.notna()).to_numpy()
    Xk, tk, yk = X.loc[keep], t[keep].to_numpy(), yv[keep].to_numpy()
    cate = predict_cate(model, Xk)
    by_arm: list[dict[str, Any]] = []
    ate: dict[str, Any] = {}
    for arm in model.arms:
        mask = np.isin(tk, [CONTROL, arm])
        n_t, n_c = int((tk == arm).sum()), int((tk == CONTROL).sum())
        if n_t < MIN_ARM_N or n_c < MIN_ARM_N:
            by_arm.append({"arm": arm, "status": "not_run",
                           "reason": f"표본 부족 — {arm} {n_t}명 · {CONTROL} {n_c}명 (최소 {MIN_ARM_N})"})
            continue
        treated = (tk[mask] == arm).astype(int)
        score, outcome = cate[arm].to_numpy()[mask], yk[mask]
        row = _score_row(model.method, "loaded", score, treated, outcome, curve=False)
        by_arm.append({"arm": arm, "status": "ok", "n": int(mask.sum()), **row})
        ate[arm] = ate_with_ci(outcome[treated == 1], outcome[treated == 0])
    return {"method": model.method, "scheme": "fitted_model_evaluation", "model_source": "loaded (재학습 없음)",
            "n": int(keep.sum()), "n_outcome_missing_excluded": int((~keep).sum()),
            "metric_version": METRIC_VERSION, "by_arm": by_arm, "ate": ate}


def _id_hash(index) -> str:
    return hashlib.sha256(json.dumps(sorted(map(str, index)), ensure_ascii=False,
                                     separators=(",", ":")).encode()).hexdigest()


def _risk_predictions(X_tr, t_tr, y_tr, X_te, churn_p, factory):
    """실제 정제·분할 뒤의 입력만 받는다. Test 결과는 인자 자체에 없다 (#179 M)."""
    fit_ids = X_tr.index[t_tr == CONTROL]
    audit = {"status": "not_run", "protocol": "train-controls-to-test-v1",
             "fit_n": len(fit_ids), "fit_ids_sha256": _id_hash(fit_ids),
             "test_n": len(X_te), "test_ids_sha256": _id_hash(X_te.index),
             "fit_test_intersection_n": len(fit_ids.intersection(X_te.index)),
             "model_spec": getattr(factory, "specification", None),
             "external_predictions_supported": False, "lineage_verification": "not_verified"}
    try:
        if churn_p is not None and factory is not None:
            raise ValueError("churn_p와 risk_model_factory 동시 입력 — factory를 실행하지 않는다")
        if churn_p is None and factory is None:
            raise ValueError("churn_p 또는 risk_model_factory가 주어지지 않았다")
        if churn_p is not None:
            raise ValueError("외부 위험도 계보는 자기 선언만으로 검증할 수 없어 비활성화했다 — risk_model_factory 필요")
        if factory is not None:
            target = 1.0 - y_tr.loc[fit_ids]
            if len(target) < 2 or not np.isfinite(target).all() or set(target.unique()) != {0.0, 1.0}:
                raise ValueError("위험도 Train∩T0에 유한 이진 라벨 두 클래스가 필요하다")
            if audit["fit_test_intersection_n"]:
                raise ValueError("위험도 학습 고객과 Test가 겹친다")
            estimator = factory()
            estimator.fit(X_tr.loc[fit_ids].copy(), target.copy())
            classes = np.asarray(estimator.classes_)
            if set(classes.tolist()) != {0, 1}:
                raise ValueError("위험도 모델의 클래스가 이진 churn이 아니다")
            proba = np.asarray(estimator.predict_proba(X_te.copy()), dtype=float)
            if proba.shape != (len(X_te), 2):
                raise ValueError("위험도 predict_proba의 행·클래스 수가 다르다")
            if (not np.isfinite(proba).all() or not ((proba >= 0) & (proba <= 1)).all()
                    or not np.allclose(proba.sum(axis=1), 1.0)):
                raise ValueError("위험도 확률 행렬이 유한한 확률 분포가 아니다")
            cp = pd.Series(proba[:, int(np.flatnonzero(classes == 1)[0])], index=X_te.index)
        if cp.isna().any() or not np.isfinite(cp).all() or not cp.between(0, 1).all():
            raise ValueError("위험도 필수 Test ID 누락·결손·비유한 값·[0,1] 밖 확률")
        audit.update(status="ok", reason=None, lineage_verification="fit_observed_in_evaluator")
        return cp, audit
    except Exception as error:  # 위험도 기준선만 격리하고 정상 S/T/X 평가를 유지한다
        audit["reason"] = f"{type(error).__name__}: {error}"
        return None, audit


def evaluate_uplift_models(X: pd.DataFrame, treatment: pd.Series, y: pd.Series, seed: int = 0,
                           churn_p: pd.Series | None = None, test_size: float = 0.3,
                           methods: tuple[str, ...] = METHODS,
                           primary_arm: str | None = None, *,
                           risk_model_factory: Callable[[], object] | None = None) -> dict[str, Any]:
    """train/test 분할 → 메타러너 학습 → test 에서 Qini·AUUC·uplift@k 비교.

    Baseline 정책:
      * ``random`` — 무작위 타깃팅의 **해석적 기대값**(Qini 0, AUUC = ATE/2, uplift@k = 전체 차).
        난수 한 번의 우연을 기준선으로 삼지 않기 위함이다.
      * ``churn_risk_targeting`` — 실제 Train∩T0만 fit한 사전 고정 factory를 우선 사용한다.
        외부 churn_p의 자기 선언 계보로 학습 사실을 검증할 수 없어 외부 점수 경로는 비활성화했다.
        factory가 없거나 외부 점수가 함께 주어지면 위험도 행만 not_run이다.
      * ``s_learner`` — Baseline 메타러너.
    대표 처치군(``primary_arm``, 기본 T3 · 없으면 표본 최다 처치군)에서 모델 행을 내고,
    처치군별 결과는 ``by_arm`` 에 둔다. 처치군별 ATE·95% CI 는 **전체 표본**에서 낸다.

    ``best_method`` — 제안 모델 중 **Validation**(train 안에서 다시 떼어 낸 25%) Qini 가 가장
    높은 것. Test 성능으로 고르지 않는다(src/decision/AGENTS.md — Test 를 보며 고르면 그것이
    과적합이다). Test 지표는 고른 뒤 보고만 한다.
    """
    X, treatment, y, n_missing = _check_inputs(X, treatment, y)
    arms_n = {a: int((treatment == a).sum()) for a in ARMS}
    usable = [a for a in TREATED if arms_n[a] >= MIN_ARM_N]
    if not usable:
        raise ValueError(f"표본 {MIN_ARM_N} 이상인 처치군이 없다")
    if primary_arm is None:
        primary_arm = DEFAULT_PRIMARY_ARM if DEFAULT_PRIMARY_ARM in usable else max(usable, key=lambda a: arms_n[a])
    if primary_arm not in usable:
        raise ValueError(f"대표 처치군 {primary_arm} 의 표본이 부족하다")

    binary = bool(set(np.unique(y.to_numpy())) <= {0.0, 1.0})
    ate = {a: ate_with_ci(y[treatment == a], y[treatment == CONTROL]) for a in TREATED}

    # 층화 분할 — 표본 1 개뿐인 처치군이 있으면 층화가 불가능하므로 단순 무작위로 내린다(기록).
    stratified = min(arms_n[a] for a in ARMS if arms_n[a] > 0) >= 2
    idx_tr, idx_te = _split(treatment, test_size, seed, stratified)
    X_tr, X_te = X.iloc[idx_tr], X.iloc[idx_te]
    t_tr, t_te = treatment.iloc[idx_tr], treatment.iloc[idx_te]
    y_tr, y_te = y.iloc[idx_tr], y.iloc[idx_te]
    risk, risk_audit = _risk_predictions(X_tr, t_tr, y_tr, X_te, churn_p, risk_model_factory)

    selection = _select_method(X_tr, t_tr, y_tr, methods, primary_arm, seed, stratified)
    # Test 의 모델 행은 Validation 으로 고른 규제로 학습한다(고르지 못했으면 현행값).
    chosen = selection.get("base_learner") or dict(BASE_LEARNER)

    cates: dict[str, pd.DataFrame] = {}
    fitted: dict[str, UpliftModel] = {}
    for m in methods:
        fitted[m] = fit_uplift(X_tr, t_tr, y_tr, method=m, seed=seed, params=chosen)
        cates[m] = predict_cate(fitted[m], X_te)

    def rows_for(arm: str, curve: bool) -> list[dict[str, Any]]:
        sel = t_te.isin([CONTROL, arm]).to_numpy()
        tr = (t_te[sel] == arm).to_numpy()
        yy = y_te[sel].to_numpy()
        overall = float(yy[tr].mean() - yy[~tr].mean())
        rows = [{"name": "random", "kind": "baseline", "method": "analytic_expectation",
                 "qini": 0.0, "auuc": overall / 2.0,
                 "uplift_at_k": {"10": overall, "30": overall}}]
        if risk is None:
            rows.append({"name": "churn_risk_targeting", "kind": "baseline", "status": "not_run",
                         "reason": risk_audit["reason"], "qini": None, "auuc": None})
        else:
            cp = risk.reindex(X_te.index[sel])
            rows.append({**_score_row("churn_risk_targeting", "baseline", cp.to_numpy(), tr, yy, curve),
                         "status": "ok"})
        for m in methods:
            sc = cates[m][arm].to_numpy()[sel]
            rows.append(_score_row(m, METHOD_KIND[m], sc, tr, yy, curve))
        return rows

    # 보고만 — 고른 메타러너를 현행값 규제로 학습했을 때의 Test 지표(선택에 쓰지 않는다, DR-217-uplift-tuning)
    best_m = selection.get("best_method")
    if best_m is None or selection.get("base_learner_is_current"):
        current_row = None
    else:
        current = predict_cate(fit_uplift(X_tr, t_tr, y_tr, method=best_m, seed=seed, params=BASE_LEARNER), X_te)
        sel_p = t_te.isin([CONTROL, primary_arm]).to_numpy()
        current_row = _score_row(f"{best_m}@current", METHOD_KIND[best_m], current[primary_arm].to_numpy()[sel_p],
                                 (t_te[sel_p] == primary_arm).to_numpy(), y_te[sel_p].to_numpy(), False)
    # PR #294 리뷰 3 — "고르는 데 성공했나"와 "실제로 쓴 규제"를 나눠 적는다. 고르지 못하면 현행값으로 학습한다.
    selected = selection.get("base_learner") is not None
    tuning_report = {
        "selection_ok": selected,
        "selection_reason": None if selected else (selection.get("reason") or "유효한 Validation Qini 가 없다 — 현행값을 쓴다"),
        "chosen_base_learner": selection.get("base_learner"), "chosen_is_current": bool(selection.get("base_learner_is_current")),
        "used_base_learner": chosen, "used_is_current": chosen == dict(BASE_LEARNER),
        "current_base_learner": dict(BASE_LEARNER),
        "test_current_regularization": current_row,
        "note": "Test 는 선택에 쓰지 않았다 — 고른 규제의 Test 지표는 models 의 해당 행, 현행값은 위 행(보고만)",
    }

    by_arm = {}
    for a in usable:
        sel_n = int(t_te.isin([CONTROL, a]).sum())
        by_arm[a] = {"n_test": sel_n,
                     "models": [{k: v for k, v in r.items() if k != "qini_curve"} for r in rows_for(a, False)]}
    return {
        "best_method": selection["best_method"],
        "best_method_selection": selection,
        "base_learner": chosen,
        "tuning_report": tuning_report,
        "n": int(len(X)), "n_train": int(len(idx_tr)), "n_test": int(len(idx_te)),
        "n_outcome_missing_excluded": n_missing,
        "risk_baseline": risk_audit,
        "evaluation_split": {"train_customer_ids": X_tr.index.tolist(), "test_customer_ids": X_te.index.tolist(),
                             "train_ids_sha256": _id_hash(X_tr.index), "test_ids_sha256": _id_hash(X_te.index),
                             "created_after_outcome_missing_filter": True},
        "metric_version": METRIC_VERSION,
        "feature_screening": {
            "rule": "학습셋에서 전부 NaN 이거나 결측 없는 상수인 열은 제외(0 으로 채우지 않음)",
            "train_dropped": screen_features(_prep_X(X_tr)),
            "submodel_extra_dropped": {m: fitted[m].submodel_dropped for m in methods
                                       if fitted[m].submodel_dropped},
        },
        "seed": seed, "test_size": test_size, "split": "stratified_by_arm" if stratified else "random",
        "outcome_kind": "binary" if binary else "continuous",
        "arms": arms_n, "primary_arm": primary_arm,
        "not_evaluable_arms": [a for a in TREATED if a not in usable],
        "ate": ate,
        "models": rows_for(primary_arm, True),
        "by_arm": by_arm,
        "definitions": {
            "qini": "area(model gain curve) − area(random line); gain per treated customer",
            "auuc": "area under (Ȳ_t(k) − Ȳ_c(k))·k/N",
            "uplift_at_k": "fractional-boundary-v1: weighted Ȳ_t − Ȳ_c; not a random tie-order expectation",
            "ties": "tied-endpoints-v1: areas and displayed curves use the same tied-group endpoints",
            "ate_ci": "Welch normal approximation, full sample",
        },
    }


def _split(treatment: pd.Series, test_size: float, seed: int, stratified: bool):
    from sklearn.model_selection import train_test_split

    return train_test_split(np.arange(len(treatment)), test_size=test_size, random_state=seed,
                            stratify=treatment.to_numpy() if stratified else None)


#: best_method · 규제 선택용 Validation 비율(train 안에서). config ``uplift.validation_size``.
VALIDATION_SIZE = CONFIG.validation_size


def _select_method(X_tr, t_tr, y_tr, methods, primary_arm: str, seed: int, stratified: bool,
                   configs: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    """train 을 다시 나눠 Validation Qini 로 **(제안 메타러너, 기저 학습기 규제)** 를 함께 고른다(DR-217-uplift-tuning).

    후보 순서 = 규제 후보 순(``regularization_candidates`` — 현행값 먼저) 안에서 메타러너 순(t · x).
    Validation Qini 최대, **동점은 앞선 후보**(현행값 · t_learner 쪽). 계산 불가(None) 후보는 고르지 않는다.
    Test 는 보지 않는다. 제안 모델이 없으면 전체 후보.
    """
    configs = regularization_candidates() if configs is None else [dict(c) for c in configs]
    candidates = [m for m in methods if METHOD_KIND[m] == "proposed"] or list(methods)
    if not candidates:
        return {"best_method": None, "status": "not_run", "reason": "후보 모델이 없다"}
    counts = t_tr.value_counts()
    strat = stratified and int(counts.min()) >= 2
    i_fit, i_val = _split(t_tr, VALIDATION_SIZE, seed + 1, strat)
    t_val = t_tr.iloc[i_val]
    sel = t_val.isin([CONTROL, primary_arm]).to_numpy()
    tr = (t_val[sel] == primary_arm).to_numpy()
    yy = y_tr.iloc[i_val].to_numpy()[sel]
    grid: list[dict[str, Any]] = []
    reasons: dict[str, str] = {}
    for config_id, params in enumerate(configs):
        for m in candidates:
            try:
                model = fit_uplift(X_tr.iloc[i_fit], t_tr.iloc[i_fit], y_tr.iloc[i_fit], method=m, seed=seed,
                                   params=params)
                cate = predict_cate(model, X_tr.iloc[i_val])[primary_arm].to_numpy()[sel]
                qini = qini_curve(cate, tr, yy)["qini"] if not np.isnan(cate).any() else None
            except ValueError as error:          # 처치군·대조군 부족 등 — 그 후보만 계산 불가
                qini = None
                reasons[f"{m}@{config_id}"] = str(error)
            grid.append({"config_id": config_id, "method": m, "qini": qini})
    valid = [i for i, row in enumerate(grid) if row["qini"] is not None]
    best = grid[max(valid, key=lambda i: (grid[i]["qini"], -i))] if valid else None
    shown = best["config_id"] if best else 0
    return {"best_method": best["method"] if best else None,
            "base_learner": dict(configs[best["config_id"]]) if best else None,
            "base_learner_is_current": bool(best) and best["config_id"] == 0,
            "basis": (f"validation Qini (train 의 {VALIDATION_SIZE:.0%}), arm {primary_arm} — 메타러너 × 규제를 함께, "
                      "동점은 앞선 후보(현행값 먼저) · DR-217-uplift-tuning"),
            "candidates": candidates,
            #: 고른 규제(없으면 현행값)에서 메타러너별 Validation Qini — 격자 전체는 ``tuning.grid``
            "validation_qini": {row["method"]: row["qini"] for row in grid if row["config_id"] == shown},
            "tuning": {"enabled": len(configs) > 1, "metric": "qini", "configs": configs, "grid": grid,
                       "reasons": reasons},
            "n_validation": int(sel.sum())}


def evaluate_on_benchmark(df: pd.DataFrame, feature_cols: list[str], treatment_col: str,
                          outcome_col: str, control_value: Any = None, treatment_value: Any = None,
                          seed: int = 0, methods: tuple[str, ...] = METHODS) -> dict[str, Any]:
    """공개 데이터(Hillstrom · Lenta 등) 외부 검증 — **이진 처치**.

    ``control_value`` 행이 T0, ``treatment_value`` 행이 T1 이 된다. ``treatment_value`` 가
    None 이면 대조가 아닌 모든 행을 T1 으로 묶는다(예: Hillstrom 의 남/여 메일 → 메일 발송).
    ``control_value`` 가 None 이면 0 · "control" · "No E-Mail" 순으로 찾는다.
    """
    col = df[treatment_col]
    if control_value is None:
        for cand in (0, "control", "No E-Mail"):
            if (col == cand).any():
                control_value = cand
                break
        else:
            raise ValueError("대조군 값을 찾지 못했다 — control_value 를 지정하라")
    is_c = col == control_value
    is_t = (~is_c) if treatment_value is None else (col == treatment_value)
    keep = (is_c | is_t) & df[outcome_col].notna()
    sub = df.loc[keep]
    treatment = pd.Series(np.where(is_c[keep], CONTROL, "T1"), index=sub.index)
    out = evaluate_uplift_models(sub[feature_cols], treatment, sub[outcome_col].astype(float),
                                 seed=seed, methods=methods, primary_arm="T1")
    out["benchmark"] = {"treatment_col": treatment_col, "outcome_col": outcome_col,
                        "control_value": str(control_value),
                        "treatment_value": "all_non_control" if treatment_value is None else str(treatment_value),
                        "n_dropped_outcome_missing": int((~df[outcome_col].notna()).sum())}
    return out
