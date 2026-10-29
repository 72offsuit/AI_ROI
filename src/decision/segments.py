"""AI 세그먼트(PRD §20 S1~S6 + Sleeping Dog) · Uplift 4분면 · 우선순위 점수 — 이슈 #145.

SRS SEG-001~004 · UP-004. 순수 함수이며 임계는 **분위수 기반**이다(데이터 단위에 무관).
분위수 경계는 ``config/model_config.yaml`` segmentation 에서 읽는다(#206).

입력 규약:
  ``churn_p``  — 고객별 이탈 확률(높을수록 위험).
  ``cate``     — ``predict_cate`` 결과(T1~T4, **클수록 좋은 결과**: 구매·유지·이익 증가).
                 DataFrame 이면 고객별 **가장 큰 처치 효과**를 uplift 로 쓴다(NaN 열 무시).
  ``clv``      — 예측 CLV. None 이면 가치 축은 **계산 불가** — 0 으로 채우지 않는다.

PRD 세그먼트 번호(S1~S6)는 전략 ID(S0~S5)와 겹치므로 코드는 서술형 이름을 쓰고
``SEGMENT_PRD_ID`` 로 대응시킨다.
"""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from src.decision.config import load_model_config

#: 분위수 경계 — config/model_config.yaml `segmentation` (#206). 값과 각 값의 뜻은 그 파일 한 곳에만 있다
#: (clv_high_q · churn_high_q · uplift_band_q). 호출자는 ``thresholds=`` 로 덮어쓸 수 있다.
DEFAULT_THRESHOLDS: dict[str, float] = dict(load_model_config().segmentation)

SEGMENT_PRD_ID = {
    "HV_PERSUADABLE": "S1", "HV_SURE_THING": "S2", "HV_LOST_CAUSE": "S3",
    "LV_PERSUADABLE": "S4", "LV_LOST_CAUSE": "S5", "NEW": "S6",
    "SLEEPING_DOG": "SD",   # SRS SEG-002 권장 — 별도 세그먼트
}
#: 가치 축(CLV)을 계산할 수 없을 때의 라벨. 가치 판단 없이 반응 축만 남긴다.
UNKNOWN_VALUE = {"persuadable": "CLV_UNKNOWN_PERSUADABLE", "near_zero": "CLV_UNKNOWN_NEAR_ZERO"}
UNSCORED = "UNSCORED"   # 필요한 점수가 결손이라 판정 불가


def uplift_score(cate: pd.DataFrame | pd.Series) -> pd.Series:
    """CATE 표 → 고객별 uplift(가장 큰 처치 효과). 모든 열이 NaN 이면 NaN."""
    if isinstance(cate, pd.Series):
        return cate.astype(float)
    return cate.astype(float).max(axis=1, skipna=True)


def _thresholds(churn_p: pd.Series, uplift: pd.Series, clv: pd.Series | None,
                cfg: dict[str, float]) -> dict[str, float | None]:
    band = float(uplift.abs().quantile(cfg["uplift_band_q"])) if uplift.notna().any() else None
    return {
        "uplift_band": band,
        "churn_high": float(churn_p.quantile(cfg["churn_high_q"])) if churn_p.notna().any() else None,
        "clv_high": float(clv.quantile(cfg["clv_high_q"])) if clv is not None and clv.notna().any() else None,
    }


def assign_quadrants(uplift: pd.Series, churn_p: pd.Series,
                     thresholds: dict[str, float] | None = None) -> pd.Series:
    """Uplift 4분면 (SRS UP-004). Persuadables · Sure Things · Lost Causes · Sleeping Dogs.

    uplift > +band → Persuadables / uplift < −band → Sleeping Dogs /
    |uplift| ≤ band 이면 이탈 위험 고 → Lost Causes, 저 → Sure Things.
    """
    cfg = {**DEFAULT_THRESHOLDS, **(thresholds or {})}
    uplift = uplift.astype(float)
    churn_p = churn_p.reindex(uplift.index).astype(float)
    th = _thresholds(churn_p, uplift, None, cfg)
    band, ch = th["uplift_band"], th["churn_high"]
    out = pd.Series(UNSCORED, index=uplift.index, dtype=object)
    if band is None:
        return out
    out[uplift > band] = "Persuadables"
    out[uplift < -band] = "Sleeping Dogs"
    mid = uplift.abs() <= band
    if ch is not None:
        out[mid & (churn_p >= ch)] = "Lost Causes"
        out[mid & (churn_p < ch)] = "Sure Things"
    return out


def assign_segments(churn_p: pd.Series, cate: pd.DataFrame | pd.Series, clv: pd.Series | None = None,
                    is_new: pd.Series | None = None,
                    thresholds: dict[str, float] | None = None) -> pd.Series:
    """PRD §20 세그먼트. 반환 index 는 ``churn_p`` 의 index.

    판정 순서: NEW(``is_new`` 참) → SLEEPING_DOG(uplift < −band) → 가치 축.
      HV(CLV ≥ 상위 20%) · uplift > band          → HV_PERSUADABLE (S1)
      HV · |uplift| ≤ band · 위험 저               → HV_SURE_THING  (S2)
      HV · |uplift| ≤ band · 위험 고               → HV_LOST_CAUSE  (S3)
      LV · uplift > band                           → LV_PERSUADABLE (S4)
      LV · |uplift| ≤ band                         → LV_LOST_CAUSE  (S5)
    PRD S1 은 '위험 고' 도 요구하지만 HV·설득가능·위험 저 고객이 어느 세그먼트에도 속하지
    않게 되므로 S1 에 넣는다(DR-145). ``is_new`` 가 없으면 NEW 는 판정하지 않는다.
    CLV 가 없으면 가치 축 대신 ``CLV_UNKNOWN_*`` 라벨을 준다.
    """
    cfg = {**DEFAULT_THRESHOLDS, **(thresholds or {})}
    idx = churn_p.index
    churn_p = churn_p.astype(float)
    u = uplift_score(cate).reindex(idx)
    v = clv.reindex(idx).astype(float) if clv is not None else None
    th = _thresholds(churn_p, u, v, cfg)
    band, ch, hv = th["uplift_band"], th["churn_high"], th["clv_high"]

    out = pd.Series(UNSCORED, index=idx, dtype=object)
    if band is None:
        return out
    pos = u > band
    neg = u < -band
    mid = u.abs() <= band
    risk_hi = churn_p >= ch if ch is not None else pd.Series(False, index=idx)
    risk_known = churn_p.notna()

    if v is None or hv is None:
        out[pos] = UNKNOWN_VALUE["persuadable"]
        out[mid] = UNKNOWN_VALUE["near_zero"]
    else:
        known = v.notna()
        high = known & (v >= hv)
        low = known & (v < hv)
        out[high & pos] = "HV_PERSUADABLE"
        out[high & mid & risk_known & ~risk_hi] = "HV_SURE_THING"
        out[high & mid & risk_known & risk_hi] = "HV_LOST_CAUSE"
        out[low & pos] = "LV_PERSUADABLE"
        out[low & mid] = "LV_LOST_CAUSE"
        out[~known & pos] = UNKNOWN_VALUE["persuadable"]
        out[~known & mid] = UNKNOWN_VALUE["near_zero"]
    out[neg] = "SLEEPING_DOG"
    if is_new is not None:
        out[is_new.reindex(idx).eq(True)] = "NEW"   # 참으로 알려진 고객만 — 결손은 NEW 로 보지 않는다
    out.attrs["thresholds"] = th
    return out


def priority_score(cate: pd.DataFrame | pd.Series, clv: pd.Series | None,
                   cost: float | pd.Series | None = None) -> pd.Series:
    """SRS SEG-004. 기본 ``uplift × CLV``, ``cost`` 가 있으면 ``uplift × CLV − cost``.

    CLV 가 없으면 전부 NaN(계산 불가)이다 — uplift 만으로 대체하지 않는다.
    """
    u = uplift_score(cate)
    if clv is None:
        return pd.Series(np.nan, index=u.index, name="priority_score")
    s = u * clv.reindex(u.index).astype(float)
    if cost is not None:
        s = s - (cost.reindex(u.index).astype(float) if isinstance(cost, pd.Series) else float(cost))
    return s.rename("priority_score")


def segment_stats(segments: pd.Series, churn_p: pd.Series, cate: pd.DataFrame | pd.Series,
                  clv: pd.Series | None = None) -> list[dict[str, Any]]:
    """SRS SEG-003 — 세그먼트별 고객 수·비율·평균 CLV·평균 이탈확률·평균 uplift."""
    u = uplift_score(cate).reindex(segments.index)
    df = pd.DataFrame({"segment": segments, "churn_p": churn_p.reindex(segments.index), "uplift": u})
    df["clv"] = clv.reindex(segments.index) if clv is not None else np.nan
    n = len(df)
    rows = []
    for seg, g in df.groupby("segment", sort=True):
        rows.append({
            "segment": seg, "prd_id": SEGMENT_PRD_ID.get(seg),
            "customer_count": int(len(g)), "ratio": len(g) / n if n else None,
            "average_clv": float(g["clv"].mean()) if g["clv"].notna().any() else None,
            "average_churn_probability": float(g["churn_p"].mean()) if g["churn_p"].notna().any() else None,
            "average_uplift": float(g["uplift"].mean()) if g["uplift"].notna().any() else None,
        })
    return rows
