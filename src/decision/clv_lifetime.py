"""12개월 CLV — BG/NBD + Gamma-Gamma (SRS CLV-001~005, #217 2부).

## 왜 확률 모형인가
우리 실험은 t2 이후 42일만 관측한다. 12개월 뒤 실제 매출로 지도학습 모델을 학습할 데이터가 실행 안에 없다.
SRS CLV-001 이 허용하는 BG/NBD + Gamma-Gamma 는 **구매 이력만으로** 미래 구매 횟수와 건당 금액을 외삽한다
(Fader, Hardie & Lee 2005 · Fader & Hardie 2013). 정답 라벨이 필요 없다.

## 정의
- 구매 = `purchase` 이벤트를 주문 단위로(``sprint_table._orders`` 와 같은 규칙), 하루에 여러 주문이면 **하루 1회 거래**로
  묶는다(BG/NBD 의 시간 단위 = 일). 그날 금액은 주문 금액의 합.
- 요약(``rfm_summary``): ``frequency`` = 거래일 수 − 1(반복 거래), ``recency`` = 마지막 − 첫 거래일(일),
  ``T`` = 기준 시각 − 첫 거래일(일), ``monetary_value`` = **반복 거래**의 평균 금액(첫 거래 제외, Gamma-Gamma 관례).
  금액이 결손인 거래가 있으면 그 고객의 ``monetary_value`` 는 NaN — 0 으로 채우지 않는다.
- 기준 시각 **미만** 이벤트만 쓴다(Feature Cutoff 와 같다).

## 12개월 · 할인 · 이익
``CLV_12m = Σ_{m=1..12} E[구매 수, 월 m] × E[건당 금액] / (1 + 연 할인율)^(m/12)`` — 월말 현금흐름 가정(#203 광진 조사 P3 식).
E[구매 수, 월 m] 은 BG/NBD 조건부 기대값의 누적 차이(이미 이탈 가능성을 반영 — 생존확률을 다시 곱하지 않는다).
결과는 **매출** 현재가치다. 이익(기여이익)은 전략이 ``margin_rate`` 를 곱한다(``strategies._value``, DR-217) — 곱하는 곳을
한 곳으로 둔다.

## 추정 불가
기준 시각 전 구매가 없는 고객은 이 모형으로 예측하지 않는다(NaN, 수를 남긴다). 금액 결손 고객은 Gamma-Gamma 를 학습에서
빼고, 예측 때는 모집단 평균 금액(E[M])을 쓴다 — 그 수도 남긴다.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Mapping

import numpy as np
import pandas as pd

DAYS_PER_MONTH = 365.25 / 12
MODEL_NAME = "bgnbd_gamma_gamma"


# ── 거래 요약 ────────────────────────────────────────────────────────────────

def _local_cut(stamps: pd.Series, at: pd.Timestamp) -> pd.Timestamp:
    """이벤트 시각열과 비교할 수 있게 기준 시각을 맞춘다(tz 없는 시각열이면 KST 로 풀어 tz 를 뗀다)."""
    if stamps.dt.tz is None and at.tzinfo is not None:
        return at.tz_convert("Asia/Seoul").tz_localize(None)
    return at


def _daily_purchases(events: pd.DataFrame, end, start=None) -> pd.DataFrame:
    """``[start, end)`` 의 구매를 **KST 날짜당 1 거래**로 묶는다 — ``customer_id · _day · amount · n``.

    주문 단위는 ``sprint_table._orders`` 와 같은 규칙. 그날 금액은 주문 금액 합(하나라도 결손이면 NaN), ``n`` 은 주문 수.
    """
    from src.decision.features.sprint_table import _clean, _orders, to_index_time

    frame = _clean(events)
    stamps = pd.to_datetime(frame["timestamp"])
    keep = stamps < _local_cut(stamps, to_index_time(end))
    if start is not None:
        keep &= stamps >= _local_cut(stamps, to_index_time(start))
    orders = _orders(frame.loc[keep])
    if orders.empty:
        return pd.DataFrame(columns=["customer_id", "_day", "amount", "n"])
    ts = pd.to_datetime(orders["timestamp"])
    local = ts.dt.tz_convert("Asia/Seoul") if ts.dt.tz is not None else ts
    orders = orders.assign(_day=local.dt.normalize().dt.tz_localize(None) if local.dt.tz is not None else local.dt.normalize())
    return orders.groupby(["customer_id", "_day"]).agg(amount=("_amount", lambda v: v.sum(min_count=len(v))),
                                                       n=("_order_key", "size")).reset_index()


def rfm_summary(events: pd.DataFrame, index_time) -> pd.DataFrame:
    """고객별 ``frequency · recency · T · monetary_value · n_orders`` — 기준 시각 미만 구매만."""
    from src.decision.features.sprint_table import to_index_time

    t0 = to_index_time(index_time)
    daily = _daily_purchases(events, t0)
    if daily.empty:
        return pd.DataFrame(columns=["frequency", "recency", "T", "monetary_value", "n_orders"]).rename_axis("customer_id")
    index_day = t0.tz_convert("Asia/Seoul").normalize().tz_localize(None) if t0.tzinfo is not None else t0.normalize()
    rows = {}
    for cid, g in daily.groupby("customer_id", sort=True):
        g = g.sort_values("_day")
        first, last = g["_day"].iloc[0], g["_day"].iloc[-1]
        repeat = g["amount"].iloc[1:]  # 반복 거래가 없거나 하나라도 금액 결손이면 NaN
        monetary = float(repeat.mean()) if len(repeat) and repeat.notna().all() else float("nan")
        rows[cid] = {"frequency": float(len(g) - 1), "recency": float((last - first).days),
                     "T": float((index_day - first).days), "monetary_value": monetary, "n_orders": int(g["n"].sum())}
    out = pd.DataFrame.from_dict(rows, orient="index")
    out.index.name = "customer_id"
    return out


# ── BG/NBD ───────────────────────────────────────────────────────────────────

def _bgnbd_ll(params: np.ndarray, x: np.ndarray, tx: np.ndarray, T: np.ndarray) -> float:
    from scipy.special import betaln, gammaln

    r, alpha, a, b = np.exp(params)
    a1 = gammaln(r + x) - gammaln(r) + r * np.log(alpha)
    a2 = betaln(a, b + x) - betaln(a, b)
    a3 = -(r + x) * np.log(alpha + T)
    with np.errstate(divide="ignore", invalid="ignore"):
        a4 = np.where(x > 0, np.log(a) - np.log(np.maximum(b + x - 1, 1e-12)) - (r + x) * np.log(alpha + tx), -np.inf)
    ll = a1 + a2 + np.logaddexp(a3, a4)
    return -float(np.sum(ll))


def fit_bgnbd(summary: pd.DataFrame) -> dict[str, Any]:
    """BG/NBD 최대우도(Fader, Hardie & Lee 2005 식 (6)). 모수는 로그 공간에서 찾는다(양수 보장)."""
    from scipy.optimize import minimize

    x, tx, T = (summary[c].to_numpy(dtype=float) for c in ("frequency", "recency", "T"))
    keep = np.isfinite(x) & np.isfinite(tx) & np.isfinite(T) & (T > 0)
    x, tx, T = x[keep], tx[keep], T[keep]
    if len(x) < 10:
        raise ValueError(f"BG/NBD 를 학습할 고객이 너무 적다({len(x)}명)")
    start = np.log([1.0, max(float(np.mean(T)), 1.0), 1.0, 1.0])
    best = None
    for scale in (1.0, 0.1, 10.0):  # 초기값을 바꿔 국소 해를 피한다 — 가장 높은 우도를 고른다
        res = minimize(_bgnbd_ll, start + np.log([1, scale, 1, 1]), args=(x, tx, T), method="Nelder-Mead",
                       options={"maxiter": 4000, "xatol": 1e-8, "fatol": 1e-8})
        if best is None or res.fun < best.fun:
            best = res
    r, alpha, a, b = (float(v) for v in np.exp(best.x))
    return {"r": r, "alpha": alpha, "a": a, "b": b, "log_likelihood": -float(best.fun),
            "converged": bool(best.success), "n": int(len(x))}


#: 기대 거래 수의 p 적분에 쓰는 Gauss 구적 노드 수(PR #293 리뷰 R1). 피적분 함수 (1 − (1 + c·p)^−k) / p 는
#: [0, 1] 에서 해석적이라 노드 수에 지수적으로 수렴한다(c = t / (α + T) 가 수백이어도 1e-7 안팎).
QUAD_NODES = 192


def _beta_nodes(a: float, shape_b: float, n: int = QUAD_NODES) -> tuple[np.ndarray, np.ndarray]:
    """Beta(a, shape_b) 에 대한 n 점 Gauss 구적 — 노드 p 와 **처음부터 합이 1인** 가중치.

    Jacobi 다항식(가중 (1 − z)^α (1 + z)^β, α = shape_b − 1 · β = a − 1, p = (1 + z) / 2)의 세 항 점화식으로 대칭
    삼중대각 행렬을 만들고 고유값(노드) · 고유벡터 첫 성분의 제곱(가중치)을 얻는다(Golub–Welsch). ``scipy.special.
    roots_jacobi`` 는 정규화 전 총 가중치 2^{α+β+1} · B(α+1, β+1) 를 곱해 돌려줘 shape_b 가 1,000 을 넘으면 넘친다
    (inf → 정규화하면 NaN, PR #293 2차 리뷰). 여기서는 그 상수를 아예 만들지 않는다.
    """
    from scipy.linalg import eigh_tridiagonal

    al, be = float(shape_b) - 1.0, float(a) - 1.0
    k = np.arange(1, n, dtype=float)
    diag = np.empty(n)
    diag[0] = (be - al) / (al + be + 2.0)
    s = 2.0 * k + al + be
    diag[1:] = (be - al) * (be + al) / (s * (s + 2.0))
    off2 = np.empty(n - 1)
    # k = 1 은 (k + α + β) / (2k + α + β − 1) = 1 로 약분한 식만 쓴다 — 일반식을 먼저 계산하면 α + β + 1 = 0(a + b + x = 1)
    # 에서 0/0 경고가 난다(PR #293 3차 리뷰 P3). 일반식은 k ≥ 2 에만.
    off2[0] = 4.0 * (1.0 + al) * (1.0 + be) / ((2.0 + al + be) ** 2 * (3.0 + al + be))
    k2, s2 = k[1:], s[1:]
    off2[1:] = 4.0 * k2 * (k2 + al) * (k2 + be) * (k2 + al + be) / (s2 * s2 * (s2 + 1.0) * (s2 - 1.0))
    z, vectors = eigh_tridiagonal(diag, np.sqrt(off2))
    weights = vectors[0] ** 2
    return (z + 1.0) / 2.0, weights / weights.sum()


def expected_purchases(bg: Mapping[str, float], t: float | np.ndarray, x: np.ndarray, tx: np.ndarray,
                       T: np.ndarray) -> np.ndarray:
    """E[Y(t) | x, t_x, T] — 앞으로 t 일 동안 기대 거래 수. **모든 r, α, a, b > 0** 에서 정의된다.

    E = P(살아 있음 | x, t_x, T) · E_{p ~ Beta(a, b+x)}[ (1 − ((α+T) / (α+T+p·t))^{r+x}) / p ].
    살아 있다는 조건에서 λ ~ Gamma(r+x, α+T) · p ~ Beta(a, b+x) 가 독립이고, λ · p 가 주어지면 기대 거래 수는
    (1 − e^{−λpt}) / p 다(Fader, Hardie & Lee 2005 식 (8)). 같은 논문 식 (10)의 닫힌 식은 E[1/p] 를 따로 꺼내 a > 1 을
    요구하고 a = 1 에서 0 × ∞ 가 되지만, 1/p 와 괄호를 함께 적분하면 p → 0 에서 유한하다(저자들의 2022 정정 노트
    §2–3). 그래서 p 적분을 Beta 가중 Gauss 구적(``_beta_nodes`` — 정규화된 가중치를 직접 얻어 큰 b 에서도 넘치지
    않는다)으로 잰다. P(살아 있음) = 1 / (1 + [x > 0] · a / (b + x − 1) · ((α+T) / (α+t_x))^{r+x}).

    **계산 실패는 NaN 으로 돌려주지 않는다** — 결과에 비유한 값이 있으면 ``FloatingPointError``. NaN 은 "구매 이력이
    없어 예측하지 않는 고객"(``predict_lifetime``)에만 쓴다(PR #293 2차 리뷰).
    """
    r, alpha, a, b = (float(bg[key]) for key in ("r", "alpha", "a", "b"))
    if not all(math.isfinite(v) and v > 0 for v in (r, alpha, a, b)):
        raise ValueError(f"BG/NBD 모수는 모두 유한한 양수여야 한다: r={r}, alpha={alpha}, a={a}, b={b}")
    x, tx, T = (np.asarray(v, dtype=float) for v in (x, tx, T))
    t = np.broadcast_to(np.asarray(t, dtype=float), x.shape)
    k = r + x
    c = t / (alpha + T)
    integral = np.empty(x.shape, dtype=float)
    for xv in np.unique(x):
        sel = x == xv
        p, w = _beta_nodes(a, b + xv)
        g = -np.expm1(-k[sel][:, None] * np.log1p(c[sel][:, None] * p[None, :])) / p[None, :]
        integral[sel] = g @ w
    with np.errstate(over="ignore"):
        odds = np.where(x > 0, a / np.maximum(b + x - 1.0, 1e-300) * np.exp(k * (np.log(alpha + T) - np.log(alpha + tx))),
                        0.0)
    out = integral / (1.0 + odds)
    if not np.isfinite(out).all():
        bad = int((~np.isfinite(out)).sum())
        raise FloatingPointError(f"BG/NBD 기대 거래 수 계산 실패 {bad}건(비유한) — 모수 r={r:.4g} alpha={alpha:.4g} "
                                 f"a={a:.4g} b={b:.4g}, t 최대 {float(np.max(t)) if t.size else 0:.4g}")
    return out


# ── Gamma-Gamma ──────────────────────────────────────────────────────────────

def _gg_ll(params: np.ndarray, x: np.ndarray, m: np.ndarray) -> float:
    from scipy.special import gammaln

    p, q, v = np.exp(params)
    ll = (gammaln(p * x + q) - gammaln(p * x) - gammaln(q) + q * np.log(v)
          + (p * x - 1) * np.log(m) + p * x * np.log(x) - (p * x + q) * np.log(x * m + v))
    return -float(np.sum(ll))


def fit_gamma_gamma(summary: pd.DataFrame) -> dict[str, Any]:
    """Gamma-Gamma 최대우도(Fader & Hardie 2013) — 반복 거래가 있고 금액이 양수인 고객만."""
    from scipy.optimize import minimize

    x = summary["frequency"].to_numpy(dtype=float)
    m = summary["monetary_value"].to_numpy(dtype=float)
    keep = (x > 0) & np.isfinite(m) & (m > 0)
    x, m = x[keep], m[keep]
    if len(x) < 10:
        raise ValueError(f"Gamma-Gamma 를 학습할 반복 구매 고객이 너무 적다({len(x)}명)")
    res = minimize(_gg_ll, np.log([1.0, 2.0, max(float(np.mean(m)), 1.0)]), args=(x, m), method="Nelder-Mead",
                   options={"maxiter": 4000, "xatol": 1e-8, "fatol": 1e-8})
    p, q, v = (float(val) for val in np.exp(res.x))
    return {"p": p, "q": q, "v": v, "log_likelihood": -float(res.fun), "converged": bool(res.success),
            "n": int(len(x))}


def expected_monetary(gg: Mapping[str, float], x: np.ndarray, m: np.ndarray) -> np.ndarray:
    """E[건당 금액 | x, m̄] — 반복 거래가 없거나 금액 결손이면 모집단 평균 E[M] = p·v/(q−1)."""
    p, q, v = gg["p"], gg["q"], gg["v"]
    if q <= 1:
        raise ValueError("Gamma-Gamma 모수 q ≤ 1 — 기대 금액이 정의되지 않는다")
    x = np.asarray(x, dtype=float)
    m = np.asarray(m, dtype=float)
    population = p * v / (q - 1)
    usable = (x > 0) & np.isfinite(m)
    with np.errstate(invalid="ignore"):
        cond = (p * (v + x * m)) / (p * x + q - 1)
    return np.where(usable, cond, population)


# ── 모델 · 예측 ──────────────────────────────────────────────────────────────

@dataclass
class LifetimeModel:
    """학습한 두 모형의 모수와 설정 — #214 모델 저장으로 동결된다."""
    bgnbd: dict[str, Any]
    gamma_gamma: dict[str, Any]
    fitted_at: str
    horizon_months: int
    annual_discount_rate: float
    n_customers: int
    name: str = MODEL_NAME
    notes: dict[str, Any] = field(default_factory=dict)


def fit_lifetime(events: pd.DataFrame, index_time, *, horizon_months: int, annual_discount_rate: float) -> LifetimeModel:
    """기준 시각 **미만** 구매 이력으로 두 모형을 학습한다. 실행 루프는 t1(처치 전)에서 부른다."""
    import hashlib

    summary = rfm_summary(events, index_time)
    bg = fit_bgnbd(summary)
    gg = fit_gamma_gamma(summary)
    digest = hashlib.sha256(pd.util.hash_pandas_object(summary, index=True).to_numpy().tobytes()).hexdigest()
    return LifetimeModel(bgnbd=bg, gamma_gamma=gg, fitted_at=pd.Timestamp(index_time).isoformat(),
                         horizon_months=int(horizon_months), annual_discount_rate=float(annual_discount_rate),
                         n_customers=int(len(summary)),
                         notes={"summary_sha256": digest,
                                "n_repeat_buyers": int((summary["frequency"] > 0).sum()),
                                "n_monetary_missing": int((summary["frequency"] > 0).sum()
                                                          - summary["monetary_value"].notna().sum())})


def clv_from_summary(model: LifetimeModel, summary: pd.DataFrame, *, annual_discount_rate: float | None = None,
                     horizon_months: int | None = None) -> pd.DataFrame:
    """요약 → 고객별 ``expected_purchases_12m · expected_monetary · clv_12m``(할인 매출 현재가치)."""
    rate = model.annual_discount_rate if annual_discount_rate is None else float(annual_discount_rate)
    months = model.horizon_months if horizon_months is None else int(horizon_months)
    x, tx, T = (summary[c].to_numpy(dtype=float) for c in ("frequency", "recency", "T"))
    m = summary["monetary_value"].to_numpy(dtype=float)
    spend = expected_monetary(model.gamma_gamma, x, m)
    cumulative = [np.zeros(len(x))] + [expected_purchases(model.bgnbd, k * DAYS_PER_MONTH, x, tx, T)
                                       for k in range(1, months + 1)]
    value = np.zeros(len(x))
    for k in range(1, months + 1):
        value += (cumulative[k] - cumulative[k - 1]) * spend / (1 + rate) ** (k / 12)
    return pd.DataFrame({"expected_purchases": cumulative[months], "expected_monetary": spend, "clv_12m": value},
                        index=summary.index)


def predict_lifetime(model: LifetimeModel, events: pd.DataFrame, index_time, customers=None) -> pd.Series:
    """기준 시각의 12개월 할인 매출 CLV. ``customers`` 를 주면 그 순서로, 구매 이력이 없는 고객은 NaN."""
    summary = rfm_summary(events, index_time)
    clv = clv_from_summary(model, summary)["clv_12m"]
    if customers is not None:
        clv = clv.reindex(pd.Index(list(customers)))
    return clv.rename("clv_12m")


def evaluate_lifetime(model: LifetimeModel, events: pd.DataFrame, index_time, actual: pd.DataFrame, *,
                      window_days: int, high_value_share: float, sensitivity: tuple[float, ...] = ()) -> dict[str, Any]:
    """CLV-004 — 관측 가능한 창(``window_days``)의 예측 구매 수 · 매출과 실제를 비교하고, 할인율 민감도를 낸다.

    민감도의 ``high_value_overlap`` 은 상위 ``high_value_share``(CLV-003, config) 고객이 할인율을 바꿔도 같은 비율이다.

    ``actual`` 은 ``build_outcomes`` 의 ``purchases`` · ``revenue``(그 창의 실제, 고객 index). 12개월 실제는 실행 안에
    없다 — 최종 실행의 연장 관측(#217 2b)에서 같은 함수를 365일로 부른다.
    """
    from scipy.stats import spearmanr

    from src.decision.features.sprint_table import to_index_time

    summary = rfm_summary(events, index_time)
    common = summary.index.intersection(actual.index)
    s = summary.loc[common]
    x, tx, T = (s[c].to_numpy(dtype=float) for c in ("frequency", "recency", "T"))
    pred_n = expected_purchases(model.bgnbd, float(window_days), x, tx, T)
    pred_rev = pred_n * expected_monetary(model.gamma_gamma, x, s["monetary_value"].to_numpy(dtype=float))
    # 구매 수는 모형과 같은 단위(KST 날짜당 1 거래 = 구매일 수)로 센다 — actual 의 주문 수와 다르다(PR #293 리뷰 N1).
    # 관측 완결성은 actual 이 정한다: actual.purchases 가 NaN 이면 그 고객은 비교에서 뺀다(0 으로 채우지 않는다).
    t0 = to_index_time(index_time)
    window = _daily_purchases(events, t0 + pd.Timedelta(days=int(window_days)), start=t0)
    days = window.groupby("customer_id").size() if not window.empty else pd.Series(dtype=float)
    observed = actual.loc[common, "purchases"].to_numpy(dtype=float)
    ok_n = np.isfinite(observed)
    act_n = np.where(ok_n, days.reindex(common, fill_value=0).to_numpy(dtype=float), np.nan)
    act_rev = actual.loc[common, "revenue"].to_numpy(dtype=float)
    ok = np.isfinite(act_rev)

    def corr(a, b):
        return float(spearmanr(a, b).statistic) if len(a) > 2 and np.std(a) > 0 and np.std(b) > 0 else None

    out: dict[str, Any] = {
        "window_days": int(window_days), "n": int(len(common)), "n_revenue_missing": int((~ok).sum()),
        "n_purchases_missing": int((~ok_n).sum()),
        "purchases": {"unit": "구매일 수(KST 날짜당 1 거래 — 모형과 같은 단위, 주문 수가 아니다)",
                      "predicted_mean": float(pred_n[ok_n].mean()) if ok_n.any() else None,
                      "actual_mean": float(act_n[ok_n].mean()) if ok_n.any() else None,
                      "actual_orders_mean": float(observed[ok_n].mean()) if ok_n.any() else None,
                      "mae": float(np.mean(np.abs(pred_n[ok_n] - act_n[ok_n]))) if ok_n.any() else None,
                      "spearman": corr(pred_n[ok_n], act_n[ok_n])},
        # 비교할 실제 매출이 한 건도 없으면 합계도 null — 빈 합 0 을 측정값처럼 남기지 않는다(PR #293 리뷰 R2)
        "revenue": {"predicted_total": float(pred_rev[ok].sum()) if ok.any() else None,
                    "actual_total": float(act_rev[ok].sum()) if ok.any() else None,
                    "mae": float(np.mean(np.abs(pred_rev[ok] - act_rev[ok]))) if ok.any() else None,
                    "spearman": corr(pred_rev[ok], act_rev[ok]),
                    **({} if ok.any() else {"reason": "비교할 실제 매출이 없다(전부 관측 미완료) — 합계 · 오차 계산 불가"})},

        "note": "관측 가능한 창의 예측 · 실제 비교 — 12개월 실제가 아니다(그것은 최종 실행 연장 관측)",
    }
    if sensitivity:
        base = clv_from_summary(model, summary)["clv_12m"]
        top = set(base.sort_values(ascending=False).index[: max(1, int(math.ceil(len(base) * high_value_share)))])
        rows = []
        for factor in sensitivity:
            rate = model.annual_discount_rate * float(factor)
            alt = clv_from_summary(model, summary, annual_discount_rate=rate)["clv_12m"]
            alt_top = set(alt.sort_values(ascending=False).index[: len(top)])
            rows.append({"factor": float(factor), "annual_discount_rate": rate, "total_clv": float(alt.sum()),
                         "total_vs_base": float(alt.sum() / base.sum()) if base.sum() else None,
                         "high_value_overlap": len(top & alt_top) / len(top) if top else None})
        out["discount_sensitivity"] = {"base_rate": model.annual_discount_rate, "base_total_clv": float(base.sum()),
                                       "rows": rows}
    return out


def clv_table(clv: pd.Series, *, model_version: str, high_value_share: float) -> pd.DataFrame:
    """CLV-005 ``clv_predictions.csv`` 행 — ``customer_id · clv_model_version · predicted_clv_12m · clv_percentile ·
    high_value_flag``(CLV-003 상위 ``high_value_share`` — config 0.2). 예측이 없는 고객은 값 · 백분위 · 플래그를 비운다
    (0 으로 채우지 않는다)."""
    frame = pd.DataFrame({"customer_id": clv.index.astype(str), "clv_model_version": model_version,
                          "predicted_clv_12m": clv.to_numpy(dtype=float)})
    known = frame["predicted_clv_12m"].notna()
    pct = frame.loc[known, "predicted_clv_12m"].rank(pct=True, method="average")
    frame["clv_percentile"] = pct.reindex(frame.index)
    cutoff = 1 - high_value_share
    frame["high_value_flag"] = pd.Series(pd.NA, index=frame.index, dtype="boolean")
    frame.loc[known, "high_value_flag"] = (pct > cutoff).to_numpy()
    return frame
