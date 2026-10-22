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
from typing import Any

import numpy as np
import pandas as pd

CONTROL = "T0"
TREATED = ("T1", "T2", "T3", "T4")
ARMS = (CONTROL, *TREATED)
METHODS = ("s_learner", "t_learner", "x_learner")
METHOD_KIND = {"s_learner": "baseline", "t_learner": "proposed", "x_learner": "proposed"}
#: 처치군(또는 대조군) 최소 표본. 이보다 적으면 그 처치의 CATE 는 계산 불가.
MIN_ARM_N = 30
#: Qini 곡선 점 개수 상한(대시보드 페이로드 크기).
CURVE_POINTS = 50
#: PRD §15.1 — Uplift MVP 는 T0 vs T3 이진 처치. 평가의 대표 처치군 기본값.
DEFAULT_PRIMARY_ARM = "T3"
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


def _check_inputs(X: pd.DataFrame, treatment: pd.Series, y: pd.Series) -> tuple[pd.Series, pd.Series]:
    treatment = pd.Series(treatment).astype(str)
    y = pd.Series(y).astype(float)
    if len(X) != len(treatment) or len(X) != len(y):
        raise ValueError("X · treatment · y 길이가 다르다")
    bad = sorted(set(treatment) - set(ARMS))
    if bad:
        raise ValueError(f"알 수 없는 처치 값: {bad[:5]} (T0~T4 만 허용)")
    if y.isna().any():
        raise ValueError("y 에 결측이 있다 — 결과를 0 으로 채우지 않는다. 결측 행을 먼저 제외하라")
    if (treatment == CONTROL).sum() < MIN_ARM_N:
        raise ValueError(f"대조군(T0) 표본이 {MIN_ARM_N} 미만이다 — CATE 를 계산할 수 없다")
    return treatment.set_axis(X.index), y.set_axis(X.index)


def _regressor(seed: int):
    from sklearn.ensemble import HistGradientBoostingRegressor

    return HistGradientBoostingRegressor(
        max_iter=150, learning_rate=0.08, max_leaf_nodes=15,
        min_samples_leaf=20, l2_regularization=1.0, random_state=seed,
    )


# ── 모델 ─────────────────────────────────────────────────────────────────────

@dataclass
class UpliftModel:
    method: str
    columns: list[str]
    arms: list[str]                       # CATE 를 계산할 수 있는 처치군
    models: dict[str, Any] = field(default_factory=dict)
    propensity: dict[str, float] = field(default_factory=dict)
    n_by_arm: dict[str, int] = field(default_factory=dict)


def fit_uplift(X: pd.DataFrame, treatment: pd.Series, y: pd.Series,
               method: str = "t_learner", seed: int = 0) -> UpliftModel:
    """메타러너를 학습한다. ``method`` ∈ ``METHODS``."""
    if method not in METHODS:
        raise ValueError(f"method 는 {METHODS} 중 하나다: {method!r}")
    treatment, y = _check_inputs(X, treatment, y)
    Xp = _prep_X(X)
    n_by_arm = {a: int((treatment == a).sum()) for a in ARMS}
    arms = [a for a in TREATED if n_by_arm[a] >= MIN_ARM_N]
    model = UpliftModel(method=method, columns=list(Xp.columns), arms=arms, n_by_arm=n_by_arm)
    ctrl = (treatment == CONTROL).to_numpy()

    if method == "s_learner":
        use = treatment.isin([CONTROL, *arms]).to_numpy()
        Xs = _with_arm_onehot(Xp[use], treatment[use], arms)
        m = _regressor(seed)
        m.fit(Xs, y[use].to_numpy())
        model.models["s"] = m
        return model

    mu0 = _regressor(seed).fit(Xp[ctrl], y[ctrl].to_numpy())
    model.models[CONTROL] = mu0
    for i, a in enumerate(arms):
        ta = (treatment == a).to_numpy()
        mu_t = _regressor(seed + i + 1).fit(Xp[ta], y[ta].to_numpy())
        model.models[a] = mu_t
        if method == "x_learner":
            d_t = y[ta].to_numpy() - mu0.predict(Xp[ta])          # 처치군의 대체 효과
            d_c = mu_t.predict(Xp[ctrl]) - y[ctrl].to_numpy()     # 대조군의 대체 효과
            model.models[f"tau_t:{a}"] = _regressor(seed + 100 + i).fit(Xp[ta], d_t)
            model.models[f"tau_c:{a}"] = _regressor(seed + 200 + i).fit(Xp[ctrl], d_c)
            model.propensity[a] = n_by_arm[a] / (n_by_arm[a] + n_by_arm[CONTROL])
    return model


def _with_arm_onehot(Xp: pd.DataFrame, treatment: pd.Series, arms: list[str]) -> pd.DataFrame:
    out = Xp.copy()
    for a in arms:
        out[f"__arm_{a}"] = (treatment.to_numpy() == a).astype(float)
    return out


def predict_cate(model: UpliftModel, X: pd.DataFrame) -> pd.DataFrame:
    """고객별 CATE(각 처치 vs T0). 열은 항상 T1~T4, 학습 불가 처치군은 NaN."""
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
    order = np.argsort(-score, kind="mergesort")       # 안정 정렬 — 동률은 입력 순서
    t = treated[order].astype(float)
    yy = y[order]
    n_t = np.cumsum(t)
    n_c = np.cumsum(1 - t)
    y_t = np.cumsum(yy * t)
    y_c = np.cumsum(yy * (1 - t))
    return n_t, n_c, y_t, y_c


def qini_curve(score, treated, y, points: int = CURVE_POINTS) -> dict[str, Any]:
    """Qini 곡선(Radcliffe 2007)과 계수.

    점수 내림차순 상위 k 명에서
      ``gain(k) = Y_t(k) − Y_c(k) · N_t(k) / N_c(k)`` (N_c(k)=0 이면 0),
    를 처치군 전체 크기 ``N_T`` 로 나눈 값을 x = k/N 에 대해 그린다. 단위는
    "처치군 1인당 증분 결과" 다. **Qini 계수 = 모델 곡선 아래 넓이 − 무작위 직선
    (0,0)→(1, gain(N)/N_T) 아래 넓이** (사다리꼴 적분). 0 이면 무작위 타깃팅과 같다.

    AUUC 는 uplift 곡선 ``u(k) = (Ȳ_t(k) − Ȳ_c(k)) · k/N`` 아래 넓이다(상위 k 명의 평균 처치
    효과 × 도달 비율). 무작위 타깃팅의 기대값은 전체 ATE/2 다.
    """
    score = np.asarray(score, dtype=float)
    treated = np.asarray(treated, dtype=bool)
    y = np.asarray(y, dtype=float)
    if np.isnan(score).any():
        raise ValueError("점수에 NaN 이 있다 — 계산 불가 처치군을 평가에 넣지 않는다")
    n = len(score)
    N_T, N_C = treated.sum(), (~treated).sum()
    if n == 0 or N_T == 0 or N_C == 0:
        raise ValueError("처치군·대조군이 모두 있어야 Qini 를 계산한다")
    n_t, n_c, y_t, y_c = _sorted_cumsums(score, treated, y)
    with np.errstate(divide="ignore", invalid="ignore"):
        gain = np.where(n_c > 0, y_t - y_c * n_t / np.where(n_c > 0, n_c, 1), 0.0) / N_T
        mean_t = np.where(n_t > 0, y_t / np.where(n_t > 0, n_t, 1), np.nan)
        mean_c = np.where(n_c > 0, y_c / np.where(n_c > 0, n_c, 1), np.nan)
    x = np.arange(1, n + 1) / n
    xs = np.concatenate([[0.0], x])
    gs = np.concatenate([[0.0], gain])
    uplift = np.nan_to_num((mean_t - mean_c) * x, nan=0.0)   # 한쪽 군이 없는 앞부분은 정의상 증분 0
    us = np.concatenate([[0.0], uplift])
    area_model = float(_trapezoid(gs, xs))
    area_random = float(gs[-1] / 2.0)
    idx = np.unique(np.round(np.linspace(0, n, points)).astype(int))
    curve = [[round(float(xs[i]), 4), round(float(gs[i]), 6)] for i in idx]
    return {
        "qini": area_model - area_random,
        "auuc": float(_trapezoid(us, xs)),
        "curve": curve,
    }


def uplift_at_k(score, treated, y, fraction: float) -> float | None:
    """상위 ``fraction`` 고객 안의 ``Ȳ_t − Ȳ_c``. 한쪽 군이 비면 None(계산 불가)."""
    score = np.asarray(score, dtype=float)
    treated = np.asarray(treated, dtype=bool)
    y = np.asarray(y, dtype=float)
    k = max(1, int(round(len(score) * fraction)))
    top = np.argsort(-score, kind="mergesort")[:k]
    t, yy = treated[top], y[top]
    if t.sum() == 0 or (~t).sum() == 0:
        return None
    return float(yy[t].mean() - yy[~t].mean())


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
    row = {"name": name, "kind": kind, "qini": q["qini"], "auuc": q["auuc"],
           "uplift_at_k": {"10": uplift_at_k(score, treated, y, 0.10),
                           "30": uplift_at_k(score, treated, y, 0.30)}}
    if curve:
        row["qini_curve"] = q["curve"]
    return row


def evaluate_uplift_models(X: pd.DataFrame, treatment: pd.Series, y: pd.Series, seed: int = 0,
                           churn_p: pd.Series | None = None, test_size: float = 0.3,
                           methods: tuple[str, ...] = METHODS,
                           primary_arm: str | None = None) -> dict[str, Any]:
    """train/test 분할 → 메타러너 학습 → test 에서 Qini·AUUC·uplift@k 비교.

    Baseline 정책:
      * ``random`` — 무작위 타깃팅의 **해석적 기대값**(Qini 0, AUUC = ATE/2, uplift@k = 전체 차).
        난수 한 번의 우연을 기준선으로 삼지 않기 위함이다.
      * ``churn_risk_targeting`` — ``churn_p`` 상위부터 타깃팅. 주어지지 않으면 ``not_run``.
      * ``s_learner`` — Baseline 메타러너.
    대표 처치군(``primary_arm``, 기본 T3 · 없으면 표본 최다 처치군)에서 모델 행을 내고,
    처치군별 결과는 ``by_arm`` 에 둔다. 처치군별 ATE·95% CI 는 **전체 표본**에서 낸다.
    """
    from sklearn.model_selection import train_test_split

    treatment, y = _check_inputs(X, treatment, y)
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

    idx_tr, idx_te = train_test_split(np.arange(len(X)), test_size=test_size,
                                      random_state=seed, stratify=treatment.to_numpy())
    X_tr, X_te = X.iloc[idx_tr], X.iloc[idx_te]
    t_tr, t_te = treatment.iloc[idx_tr], treatment.iloc[idx_te]
    y_tr, y_te = y.iloc[idx_tr], y.iloc[idx_te]

    cates: dict[str, pd.DataFrame] = {}
    for m in methods:
        cates[m] = predict_cate(fit_uplift(X_tr, t_tr, y_tr, method=m, seed=seed), X_te)

    def rows_for(arm: str, curve: bool) -> list[dict[str, Any]]:
        sel = t_te.isin([CONTROL, arm]).to_numpy()
        tr = (t_te[sel] == arm).to_numpy()
        yy = y_te[sel].to_numpy()
        overall = float(yy[tr].mean() - yy[~tr].mean())
        rows = [{"name": "random", "kind": "baseline", "method": "analytic_expectation",
                 "qini": 0.0, "auuc": overall / 2.0,
                 "uplift_at_k": {"10": overall, "30": overall}}]
        if churn_p is None:
            rows.append({"name": "churn_risk_targeting", "kind": "baseline", "status": "not_run",
                         "reason": "churn_p 가 주어지지 않았다", "qini": None, "auuc": None})
        else:
            cp = pd.Series(churn_p).reindex(X_te.index[sel])
            if cp.isna().any():
                rows.append({"name": "churn_risk_targeting", "kind": "baseline", "status": "not_run",
                             "reason": f"churn_p 결측 {int(cp.isna().sum())}건", "qini": None, "auuc": None})
            else:
                rows.append(_score_row("churn_risk_targeting", "baseline", cp.to_numpy(), tr, yy, curve))
        for m in methods:
            sc = cates[m][arm].to_numpy()[sel]
            rows.append(_score_row(m, METHOD_KIND[m], sc, tr, yy, curve))
        return rows

    by_arm = {}
    for a in usable:
        sel_n = int(t_te.isin([CONTROL, a]).sum())
        by_arm[a] = {"n_test": sel_n,
                     "models": [{k: v for k, v in r.items() if k != "qini_curve"} for r in rows_for(a, False)]}
    return {
        "n": int(len(X)), "n_train": int(len(idx_tr)), "n_test": int(len(idx_te)),
        "seed": seed, "test_size": test_size,
        "outcome_kind": "binary" if binary else "continuous",
        "arms": arms_n, "primary_arm": primary_arm,
        "not_evaluable_arms": [a for a in TREATED if a not in usable],
        "ate": ate,
        "models": rows_for(primary_arm, True),
        "by_arm": by_arm,
        "definitions": {
            "qini": "area(model gain curve) − area(random line); gain per treated customer",
            "auuc": "area under (Ȳ_t(k) − Ȳ_c(k))·k/N",
            "uplift_at_k": "Ȳ_t − Ȳ_c within top k% by score (None if an arm is empty)",
            "ate_ci": "Welch normal approximation, full sample",
        },
    }


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
