"""모델 모니터링 — Feature 드리프트(PSI·KS) · 성능 추이 · 경보 (스프린트 1 D12, 이슈 #94 · SRS MON-001~004).

입력은 두 시점의 Feature 테이블(`sprint_table.build_feature_table` 의 결과)과 시점별 (y, p)다.
시뮬레이터 내부·숨김 영역은 모른다.

PSI 규칙:
  - 구간은 **기준(expected) 분포의 분위수**로 정한다(기본 10 분위). 같은 분위 경계가 겹치면
    합친다(이산 값·0 이 많은 횟수 Feature). 기준 최솟값 아래·최댓값 위 값도 각자 구간에 들어간다.
  - **결손(NaN)은 별도 구간이다.** 0 으로 채우지 않는다 — 결손률이 바뀌는 것 자체가 드리프트다.
  - 비율이 0 인 구간은 ``EPS`` 로 바닥을 깐다(ln 0 회피). 이 값이 PSI 를 키우는 쪽이라 보수적이다.
  - 수치가 아닌 열은 범주 값마다 구간을 둔다.

등급(업계 관행 — 근거 문헌 없음, 스프린트 가정): PSI < 0.1 안정 · 0.1 ≤ PSI < 0.25 주의 · ≥ 0.25 경보.
값을 낼 수 없으면 ``계산 불가`` 다(통과가 아니다).
"""

from __future__ import annotations

import math
from typing import Any, Iterable, Mapping

import numpy as np
import pandas as pd

EPS = 1e-4
PSI_WARNING = 0.10
PSI_ALERT = 0.25
LEVEL_STABLE, LEVEL_WARNING, LEVEL_ALERT, LEVEL_NA = "안정", "주의", "경보", "계산 불가"

DEFAULT_THRESHOLDS: dict[str, float] = {
    "psi_warning": PSI_WARNING,
    "psi_alert": PSI_ALERT,
    # 기준 시점 대비 하락폭(절대값). 근거 문헌 없음 — 스프린트 가정.
    "roc_auc_drop": 0.05,
    "pr_auc_drop": 0.05,
    "brier_rise": 0.02,
}


def _proportions(codes: np.ndarray, n_bins: int) -> np.ndarray:
    counts = np.bincount(codes, minlength=n_bins).astype(float)
    total = counts.sum()
    return counts / total if total else counts


def _numeric_codes(expected: np.ndarray, actual: np.ndarray, bins: int) -> tuple[np.ndarray, np.ndarray, int]:
    """기준 분위수 구간 코드. 마지막 코드는 결손 구간이다."""
    finite = expected[~np.isnan(expected)]
    if finite.size:
        inner = np.quantile(finite, np.linspace(0, 1, bins + 1)[1:-1])
        below = np.nextafter(finite.min(), -np.inf)  # 기준 최솟값 미만 구간
        cuts = np.unique(np.concatenate([[below], inner, [finite.max()]]))
    else:
        cuts = np.array([])
    n_value_bins = len(cuts) + 1
    missing = n_value_bins

    def code(x: np.ndarray) -> np.ndarray:
        out = np.searchsorted(cuts, x, side="left")  # (c_{i-1}, c_i] → i
        return np.where(np.isnan(x), missing, out)

    return code(expected), code(actual), n_value_bins + 1


def _categorical_codes(expected: pd.Series, actual: pd.Series) -> tuple[np.ndarray, np.ndarray, int]:
    values = pd.Index(pd.concat([expected, actual]).dropna().astype(str).unique())
    missing = len(values)

    def code(s: pd.Series) -> np.ndarray:
        idx = values.get_indexer(s.astype(object).where(s.notna(), None).map(
            lambda v: None if v is None else str(v)))
        return np.where(s.isna().to_numpy(), missing, idx)

    return code(expected), code(actual), missing + 1


def psi(expected, actual, bins: int = 10) -> float:
    """Population Stability Index. 어느 한쪽 표본이 비어 있으면 ``nan``(계산 불가)."""
    e = pd.Series(expected)
    a = pd.Series(actual)
    if len(e) == 0 or len(a) == 0:
        return math.nan
    numeric = pd.api.types.is_numeric_dtype(e.dtype) and pd.api.types.is_numeric_dtype(a.dtype) \
        and not pd.api.types.is_bool_dtype(e.dtype)
    if numeric:
        ec, ac, n = _numeric_codes(e.astype(float).to_numpy(), a.astype(float).to_numpy(), bins)
    else:
        ec, ac, n = _categorical_codes(e, a)
    pe = np.clip(_proportions(ec, n), EPS, None)
    pa = np.clip(_proportions(ac, n), EPS, None)
    return float(np.sum((pa - pe) * np.log(pa / pe)))


def psi_level(value: float | None, warning: float = PSI_WARNING, alert: float = PSI_ALERT) -> str:
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return LEVEL_NA
    if value >= alert:
        return LEVEL_ALERT
    if value >= warning:
        return LEVEL_WARNING
    return LEVEL_STABLE


def _ks(e: pd.Series, a: pd.Series) -> tuple[float | None, float | None]:
    try:
        from scipy.stats import ks_2samp
    except ImportError:  # scipy 없으면 KS 는 계산 불가 — PSI 만 낸다
        return None, None
    if not (pd.api.types.is_numeric_dtype(e.dtype) and pd.api.types.is_numeric_dtype(a.dtype)):
        return None, None
    e, a = e.dropna().astype(float), a.dropna().astype(float)
    if len(e) == 0 or len(a) == 0:
        return None, None
    res = ks_2samp(e.to_numpy(), a.to_numpy())
    return float(res.statistic), float(res.pvalue)


def feature_drift(X_ref: pd.DataFrame, X_cur: pd.DataFrame, bins: int = 10, *,
                  columns: Iterable[str] | None = None,
                  warning: float = PSI_WARNING, alert: float = PSI_ALERT) -> pd.DataFrame:
    """Feature 별 PSI·KS·결손률·등급. 한쪽에만 있는 열은 ``계산 불가`` 행으로 남긴다(빠뜨리지 않는다)."""
    cols = list(columns) if columns is not None else list(dict.fromkeys([*X_ref.columns, *X_cur.columns]))
    rows: list[dict[str, Any]] = []
    for col in cols:
        row: dict[str, Any] = {"feature": col, "n_ref": int(len(X_ref)), "n_cur": int(len(X_cur))}
        if col not in X_ref.columns or col not in X_cur.columns:
            side = "ref" if col not in X_ref.columns else "cur"
            row.update(psi=None, level=LEVEL_NA, reason=f"열 없음({side})", ks_stat=None, ks_pvalue=None,
                       missing_ref=None, missing_cur=None)
            rows.append(row)
            continue
        e, a = X_ref[col], X_cur[col]
        value = psi(e, a, bins)
        ks_stat, ks_p = _ks(e, a)
        row.update(
            psi=None if math.isnan(value) else value,
            level=psi_level(value, warning, alert),
            reason=None if not math.isnan(value) else "표본 없음",
            ks_stat=ks_stat, ks_pvalue=ks_p,
            missing_ref=float(e.isna().mean()) if len(e) else None,
            missing_cur=float(a.isna().mean()) if len(a) else None,
        )
        rows.append(row)
    frame = pd.DataFrame(rows, columns=["feature", "psi", "level", "reason", "ks_stat", "ks_pvalue",
                                        "missing_ref", "missing_cur", "n_ref", "n_cur"])
    return frame.set_index("feature")


def _one_period(y: np.ndarray, p: np.ndarray, threshold: float | None) -> dict[str, Any]:
    from sklearn.metrics import average_precision_score, brier_score_loss, roc_auc_score

    mask = ~(np.isnan(y) | np.isnan(p))
    y, p = y[mask].astype(int), p[mask]
    row: dict[str, Any] = {"n": int(len(y)), "n_dropped_missing": int((~mask).sum()),
                           "n_pos": int(y.sum()) if len(y) else 0}
    row["prevalence"] = float(y.mean()) if len(y) else None
    if len(y) == 0:
        row.update(roc_auc=None, pr_auc=None, brier=None, status="계산 불가 — 표본 없음")
    elif len(np.unique(y)) < 2:
        row.update(roc_auc=None, pr_auc=None, brier=float(brier_score_loss(y, p, pos_label=1)),
                   status="계산 불가 — 단일 클래스(AUC 정의 안 됨)")
    else:
        row.update(roc_auc=float(roc_auc_score(y, p)), pr_auc=float(average_precision_score(y, p)),
                   brier=float(brier_score_loss(y, p)), status="ok")
    if threshold is None:
        row.update(threshold=None, precision=None, recall=None)
    else:
        pred = p >= threshold
        tp = int((pred & (y == 1)).sum())
        row.update(threshold=float(threshold),
                   precision=None if pred.sum() == 0 else tp / int(pred.sum()),
                   recall=None if y.sum() == 0 else tp / int(y.sum()))
    return row


def performance_trend(by_time: Mapping[str, tuple[Any, Any]] | pd.DataFrame, *,
                      threshold: float | None = None, time_col: str = "time",
                      y_col: str = "y", p_col: str = "p") -> pd.DataFrame:
    """시점별 ROC-AUC · PR-AUC · Brier(보정) · (임계값이 있으면) Precision·Recall.

    입력: ``{시점: (y, p)}`` 또는 ``time``·``y``·``p`` 열의 DataFrame. 시점 순서는 입력 순서다
    (dict) 또는 정렬 순서(DataFrame). 단일 클래스 시점의 AUC 는 ``None`` 이다(0.5 로 채우지 않는다).
    임계값은 학습에서 정한 값을 넘긴다 — 여기서 고르지 않는다(Test 로 임계값을 고르면 누수다).
    """
    if isinstance(by_time, pd.DataFrame):
        items = [(str(t), (g[y_col].to_numpy(), g[p_col].to_numpy()))
                 for t, g in by_time.groupby(time_col, sort=True)]
    else:
        items = [(str(t), v) for t, v in by_time.items()]
    rows = []
    for t, (y, p) in items:
        row = _one_period(np.asarray(y, dtype=float), np.asarray(p, dtype=float), threshold)
        rows.append({"time": t, **row})
    return pd.DataFrame(rows).set_index("time") if rows else pd.DataFrame(
        columns=["n", "roc_auc", "pr_auc", "brier"]).rename_axis("time")


def _finite(v: Any) -> float | None:
    if v is None:
        return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return None if math.isnan(f) else f


def alerts(drift_df: pd.DataFrame | None, trend: pd.DataFrame | None,
           thresholds: Mapping[str, float] | None = None) -> list[dict[str, Any]]:
    """경보 목록 (MON-003). 드리프트: Feature PSI 가 주의/경보 기준 이상. 성능: **첫 시점 대비**
    ROC-AUC·PR-AUC 하락폭 또는 Brier 상승폭이 기준 이상. 값이 없는 시점은 비교하지 않는다
    (경보 없음 ≠ 정상 — 계산 불가 시점은 ``performance_not_evaluable`` 경보로 남긴다).
    """
    th = {**DEFAULT_THRESHOLDS, **(thresholds or {})}
    out: list[dict[str, Any]] = []
    if drift_df is not None and len(drift_df):
        for feature, row in drift_df.iterrows():
            value = _finite(row.get("psi"))
            if value is None or value < th["psi_warning"]:
                continue
            severe = value >= th["psi_alert"]
            out.append({
                "type": "drift", "feature": str(feature), "metric": "psi", "value": value,
                "severity": LEVEL_ALERT if severe else LEVEL_WARNING,
                "threshold": th["psi_alert"] if severe else th["psi_warning"],
                "message": f"{feature} PSI {value:.3f} ≥ {th['psi_alert'] if severe else th['psi_warning']}",
            })
    if trend is not None and len(trend):
        ref_time = trend.index[0]
        ref = trend.iloc[0]
        rules = (("roc_auc", "roc_auc_drop", -1), ("pr_auc", "pr_auc_drop", -1), ("brier", "brier_rise", +1))
        for t, row in trend.iloc[1:].iterrows():
            for metric, key, sign in rules:
                base, cur = _finite(ref.get(metric)), _finite(row.get(metric))
                if base is None or cur is None:
                    if metric == "roc_auc":
                        out.append({"type": "performance_not_evaluable", "time": str(t), "metric": metric,
                                    "reference_time": str(ref_time), "severity": LEVEL_NA,
                                    "message": f"{t} {metric} 비교 불가 — 값 결손"})
                    continue
                delta = (cur - base) * sign  # 양수 = 나빠짐
                if delta >= th[key]:
                    out.append({
                        "type": "performance", "time": str(t), "metric": metric, "value": cur,
                        "reference_time": str(ref_time), "reference_value": base,
                        "change": cur - base, "threshold": th[key], "severity": LEVEL_ALERT,
                        "message": f"{metric} {base:.3f} → {cur:.3f} (기준 {th[key]})",
                    })
    return out


def drift_to_records(drift_df: pd.DataFrame) -> dict[str, dict[str, Any]]:
    """MON-004 ``features`` 꼴(``{feature: {...}}``). NaN 은 ``None``."""
    out: dict[str, dict[str, Any]] = {}
    for feature, row in drift_df.iterrows():
        out[str(feature)] = {k: (None if isinstance(v, float) and math.isnan(v) else v)
                             for k, v in row.to_dict().items()}
    return out
