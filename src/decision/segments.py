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

import math
from typing import Any, Mapping

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


# ── #219 · DR-219-segments — NEW 연결 · 4분면 분포 · 쏠림 기록 · 가설 · SEG-005 표 ──────────────────

#: AI 세그먼트 NEW(PRD §20 S6 — 수치 정의 없음)의 판정 = 관측 등급 가입 시기(DR-221 ``signup_tier``): 기준일 KST 날짜 −
#: 가입일 < 180일. ANA-008 · ML-010 · #218 명부와 같은 한 정의다(DR-221 남은 불확실성 — #219 에서 정한다).
NEW_SEGMENT_SOURCE = "observed_tiers.signup_tier = NEW (DR-221 — 가입 180일 미만)"
#: 가치 축으로 배정된 세그먼트. 쏠림 · 가설 H-SEG-1 의 분모다.
HIGH_VALUE = ("HV_PERSUADABLE", "HV_SURE_THING", "HV_LOST_CAUSE")
LOW_VALUE = ("LV_PERSUADABLE", "LV_LOST_CAUSE")
#: 고객 세그먼트 표(SRS SEG-005 필수 열 + 판정 근거 열). 결손은 빈 칸 — 0 으로 채우지 않는다.
SEGMENT_TABLE_COLUMNS: tuple[str, ...] = (
    "customer_id", "segment", "segment_prd_id", "quadrant", "churn_probability", "uplift_score", "uplift_arm",
    "predicted_clv_12m", "priority_score", "expected_net_value_krw", "net_arm", "signup_tier",
)
#: 비용을 뺀 우선순위의 처치 후보 — S4 전략과 같다(``strategies.TREATMENTS``).
NET_TREATMENTS: tuple[str, ...] = ("T1", "T2", "T3", "T4")


def is_new_from_signup_tier(signup_tier: pd.Series) -> pd.Series:
    """가입 시기 등급 → NEW 여부. ``NEW`` 참 · ``EXISTING`` 거짓 · ``UNKNOWN`` · 결손은 None(NEW 로 보지 않는다).

    index = customer_id(문자열). 판정을 다시 계산하지 않는다 — 명부(#218)가 계산한 등급을 읽는다(DR-221).
    """
    flags = pd.Series([None] * len(signup_tier), index=signup_tier.index.map(str), dtype=object)
    values = signup_tier.astype(object).to_numpy()
    flags[values == "NEW"] = True
    flags[values == "EXISTING"] = False
    return flags


def quadrant_summary(uplift: pd.Series, churn_p: pd.Series, thresholds: dict[str, float] | None = None) -> dict[str, Any]:
    """UP-004 4분면의 고객 수 · 비율과 실제 경계값(분위수 → 이 실행의 값). 경계 분위수의 출처는 config 한 곳이다."""
    cfg = {**DEFAULT_THRESHOLDS, **(thresholds or {})}
    quadrants = assign_quadrants(uplift, churn_p, cfg)
    th = _thresholds(churn_p.reindex(uplift.index).astype(float), uplift.astype(float), None, cfg)
    n = int(len(quadrants))
    order = ("Persuadables", "Sure Things", "Lost Causes", "Sleeping Dogs", UNSCORED)
    counts = {name: int((quadrants == name).sum()) for name in order}
    return {
        "counts": counts, "shares": {k: (v / n if n else None) for k, v in counts.items()}, "n": n,
        "quantiles": {"uplift_band_q": cfg["uplift_band_q"], "churn_high_q": cfg["churn_high_q"]},
        "values": {"uplift_band": th["uplift_band"], "churn_high": th["churn_high"]},
        "config": "config/model_config.yaml segmentation(DR-145 · DR-219-segments)",
    }


def _wilson(x: int, n: int, z: float) -> tuple[float, float]:
    p = x / n
    centre = (p + z * z / (2 * n)) / (1 + z * z / n)
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / (1 + z * z / n)
    return centre - half, centre + half


def _two_proportions(x1: int, n1: int, x2: int, n2: int, alpha: float) -> dict[str, Any]:
    """비율 차이(1 − 2)와 Newcombe(1998) 하이브리드 score 구간(Wilson 구간 두 개를 합친다).

    A/B 분석은 Wald 구간이지만 여기서는 쓰지 않는다 — 쏠림이 강할수록 비율이 0 · 1 에 가까워지고, 그때 Wald 구간은
    실제 포함 확률이 명목보다 낮다(Newcombe 1998). 유의수준은 A/B 분석과 같은 값을 쓴다.
    """
    from scipy.stats import norm

    z = float(norm.ppf(1 - alpha / 2))
    p1, p2 = x1 / n1, x2 / n2
    l1, u1 = _wilson(x1, n1, z)
    l2, u2 = _wilson(x2, n2, z)
    diff = p1 - p2
    return {"share_new": p1, "share_existing": p2, "diff": diff,
            "ci": [diff - math.sqrt((p1 - l1) ** 2 + (u2 - p2) ** 2), diff + math.sqrt((u1 - p1) ** 2 + (p2 - l2) ** 2)],
            "ci_level": round(1 - alpha, 10), "method": "Newcombe(1998) hybrid score interval"}


#: 결과 전에 등록한 가설(DR-219-segments). 근거 자료로 정할 수 없는 기대라 가설로 두고 실행마다 같은 규칙으로 평가한다.
#: 결과: supported(지지) · not_supported(지지되지 않음) · undetermined(판정 불가) · not_evaluated(평가 구현 전).
SEGMENT_HYPOTHESES: tuple[dict[str, str], ...] = (
    {"id": "H-SEG-1",
     "statement": "신규 고객(NEW)은 NEW 로 떼지 않으면 기존 고객보다 저가치(LV) 세그먼트로 쏠린다",
     "why": ("가입 180일 미만은 Feature 창(180일)이 다 차지 않아 금액 · 횟수가 낮게 잡힌다(DR-221). 다만 12개월 CLV(BG/NBD)는 "
             "관측 기간을 모형에 넣으므로 실제로 낮게 잡히는지는 알 수 없다 — 그래서 가설이다"),
     "evaluation": ("가치 축으로 배정된 고객 중 LV 비율 차이(NEW − 기존)의 95% 구간(Newcombe score) 하한 > 0 이면 지지, "
                    "아니면 지지되지 않음. 어느 쪽이든 가치 축 배정 고객이 100명 미만(DR-221 고객 수 기준)이면 판정 불가")},
    {"id": "H-SEG-2",
     "statement": "예측 Persuadables 의 실측 처치 효과(탐색 RCT test 분할)는 나머지 고객보다 크고, 예측 Sleeping Dogs 의 실측 효과는 0 이하다",
     "why": "4분면 '≈0 띠' 경계(|uplift| 60% 분위수, DR-145)는 분위수 방식만 근거가 있고 0.6 이라는 값의 근거는 없다",
     "evaluation": "2부(#219 메타러너 · 십분위표)에서 RCT test 분할로 평가 — 평가 규칙은 2부 PR 전에 이 문서에 고정한다"},
)


def new_segment_shift(churn_p: pd.Series, cate: pd.DataFrame | pd.Series, clv: pd.Series | None, is_new: pd.Series,
                      thresholds: dict[str, float] | None = None, alpha: float | None = None) -> dict[str, Any]:
    """NEW 판정이 세그먼트 분포를 얼마나 옮기나(쏠림 기록) + 가설 H-SEG-1 평가.

    NEW 가 먼저 판정되므로(``assign_segments``) NEW 고객은 원래 세그먼트에서 빠진다. NEW 를 빼고 배정했을 때 NEW 고객이
    어느 세그먼트였을지(``underlying_of_new``)와 기존 고객의 분포(``existing``)를 나란히 싣는다 — 판정 없이 사실만.
    """
    from src.decision.ab_test import ALPHA
    from src.decision.observed_tiers import MIN_GROUP_CUSTOMERS

    alpha = ALPHA if alpha is None else alpha
    idx = churn_p.index
    base = assign_segments(churn_p, cate, clv, is_new=None, thresholds=thresholds)
    flags = is_new.reindex(idx.map(str))
    flags.index = idx
    new = flags.eq(True).fillna(False).astype(bool)
    existing = flags.eq(False).fillna(False).astype(bool)

    def counts(mask: pd.Series) -> dict[str, int]:
        return {str(k): int(v) for k, v in base[mask].value_counts().sort_index().items()}

    def value_share(mask: pd.Series) -> tuple[int, int]:
        seg = base[mask]
        n_value = int(seg.isin(HIGH_VALUE + LOW_VALUE).sum())
        return int(seg.isin(LOW_VALUE).sum()), n_value

    lv_new, n_new_value = value_share(new)
    lv_old, n_old_value = value_share(existing)
    hyp = dict(SEGMENT_HYPOTHESES[0])
    # 표본 부족 = 고객 수 기준만(DR-221 100명). 적은 쪽 10명 기준은 쓰지 않는다 — 그 기준은 정규근사(Wald)용이고, score 구간은
    # 비율이 0 · 1 에 가까워도(강한 쏠림) 쓸 수 있다. 쏠림이 강할수록 판정 불가가 되면 가설을 평가하지 못한다.
    small = [name for name, n in (("NEW", n_new_value), ("기존", n_old_value)) if n < MIN_GROUP_CUSTOMERS]
    if small:
        hyp.update(result="undetermined", evidence={"reason": f"표본 부족(가치 축 배정 고객 {MIN_GROUP_CUSTOMERS}명 미만): {', '.join(small)}",
                                                    "n_value_new": n_new_value, "n_value_existing": n_old_value})
    else:
        test = _two_proportions(lv_new, n_new_value, lv_old, n_old_value, alpha)
        supported = test["ci"][0] > 0
        # #326 리뷰 — 지지되지 않음은 차이를 지지할 근거가 부족하다는 뜻이다(반증이 아니다). 구간은 한 실행의 공통 점수 ·
        # 분위수 경계로 나눈 고객 안의 비교라, 경계 추정의 불확실성까지 담은 실행 간 구간이 아니다 — 이 실행에 조건부인 근사다.
        hyp.update(result="supported" if supported else "not_supported",
                   not_supported_kind=None if supported else "insufficient_evidence",
                   evidence={**test, "n_value_new": n_new_value, "n_value_existing": n_old_value, "alpha": alpha,
                             "interval_note": ("이 실행의 점수 · 분위수 경계에 조건부인 근사 — 경계 추정의 불확실성은 "
                                               "담지 않는다")})
    return {
        "rule": NEW_SEGMENT_SOURCE,
        "n_new": int(new.sum()), "n_existing": int(existing.sum()),
        "n_signup_unknown": int((~new & ~existing).sum()),
        "underlying_of_new": counts(new), "existing": counts(existing),
        "note": ("underlying_of_new = NEW 를 판정하지 않았다면 NEW 고객이 들어갔을 세그먼트(같은 점수 · 같은 경계). "
                 "가입일을 모르는 고객은 NEW 로 보지 않는다"),
        "hypotheses": [hyp],   # H-SEG-2 는 test 분할에서 평가한다(uplift_report.quadrant_validation)
    }


def expected_net_value(cate: pd.DataFrame, clv: pd.Series | None, margin_rate: float | None,
                       costs: Mapping[str, Any] | None) -> pd.DataFrame:
    """SEG-004 프로젝트 확장 — 처치 t 중 최대(CATE_t × CLV × margin_rate − cost_t)와 그 처치(DR-219-segments 2부).

    S4 전략(``strategies.plan_S4``)과 같은 정의 · 같은 계획 비용이다. ``margin_rate`` · ``costs`` · CLV 중 하나라도 없으면
    비운다 — 매출 CLV 를 이익으로 쓰지 않는다(#217). 열: ``expected_net_value_krw`` · ``net_arm``.
    """
    idx = cate.index
    out = pd.DataFrame({"expected_net_value_krw": np.nan, "net_arm": None}, index=idx)
    out["net_arm"] = out["net_arm"].astype(object)
    if clv is None or margin_rate is None or not costs:
        return out
    frame = cate[[t for t in NET_TREATMENTS if t in cate.columns]].astype(float)
    value = clv.reindex(idx).astype(float) * float(margin_rate)
    net = frame.mul(value, axis=0) - pd.Series({t: float(costs[t]) for t in frame.columns})
    known = net.notna().any(axis=1)
    out.loc[known, "expected_net_value_krw"] = net[known].max(axis=1)
    out.loc[known, "net_arm"] = net[known].idxmax(axis=1)
    return out


def persuadables_profile(quadrants: pd.Series, features: pd.DataFrame,
                         tiers: pd.DataFrame | None = None) -> dict[str, Any]:
    """SRS UP-006 — Persuadables 대 나머지(4분면이 매겨진 고객)의 관측 Feature 차이(DR-219-segments 2부).

    Feature 마다 두 집단의 평균 · 결손 비율 · 표준화 평균차(SMD = 평균 차 ÷ √((분산₁ + 분산₂)/2), Austin 2009)를 내고
    |SMD| 내림차순으로 싣는다. 판정 기준값은 쓰지 않는다. 관측 등급(``tiers`` — #218 명부 t2 행, Eligible(t2)만)이 있으면
    축마다 등급 비율도 나란히 싣는다. 비율의 분모는 **명부에 있는 고객**이다 — 명부 밖 고객은 ``coverage`` 에 따로 세고
    명부가 매긴 ``UNKNOWN`` 등급과 섞지 않는다(2026-11-26 광진 리뷰, PR #328).
    """
    scored = quadrants[quadrants != UNSCORED]
    pers = scored.index[scored == "Persuadables"]
    rest = scored.index[scored != "Persuadables"]
    rows = []
    for col in features.columns:
        series = features[col]
        if not pd.api.types.is_numeric_dtype(series):
            continue
        a, b = series.reindex(pers).astype(float), series.reindex(rest).astype(float)
        va, vb = a.dropna(), b.dropna()
        smd = None
        if len(va) >= 2 and len(vb) >= 2:
            pooled = math.sqrt((float(va.var(ddof=1)) + float(vb.var(ddof=1))) / 2)
            smd = (float(va.mean()) - float(vb.mean())) / pooled if pooled > 0 else None
        rows.append({"feature": str(col), "mean_persuadables": float(va.mean()) if len(va) else None,
                     "mean_rest": float(vb.mean()) if len(vb) else None,
                     "missing_persuadables": float(a.isna().mean()) if len(a) else None,
                     "missing_rest": float(b.isna().mean()) if len(b) else None, "smd": smd})
    rows.sort(key=lambda r: (r["smd"] is None, -abs(r["smd"] or 0.0), r["feature"]))
    tier_rows: dict[str, Any] = {}
    if tiers is not None:
        frame = tiers.copy()
        frame.index = frame.index.map(str)
        frame = frame[~frame.index.duplicated(keep=False)]
        members = {"persuadables": pers.map(str), "rest": rest.map(str)}
        for col in frame.columns:
            values, coverage = {}, {}
            for name, ids in members.items():
                inside = ids.isin(frame.index)
                vals = frame[col].reindex(ids[inside])
                values[name] = vals
                coverage[name] = {"n_total": int(len(ids)), "n_in_roster": int(inside.sum()),
                                  "n_not_in_roster": int((~inside).sum()),
                                  "n_roster_unknown": int((vals.astype(object) == "UNKNOWN").sum()),
                                  "n_missing_in_roster": int(vals.isna().sum())}
            codes = sorted({str(v) for v in pd.concat(list(values.values())).dropna()})
            rows_out = []
            for code in codes:
                row: dict[str, Any] = {"group": code}
                for name, vals in values.items():
                    count = int((vals.astype(object) == code).sum())
                    denom = coverage[name]["n_in_roster"]
                    row[f"n_{name}"] = count
                    row[f"share_{name}"] = count / denom if denom else None
                rows_out.append(row)
            tier_rows[str(col)] = {"denominator": "명부(#218 t2 행 — Eligible(t2))에 있는 고객 — 명부 밖 고객은 coverage 에만",
                                   "coverage": coverage, "rows": rows_out}
    return {"n_persuadables": int(len(pers)), "n_rest": int(len(rest)), "features": rows, "tiers": tier_rows,
            "measure": "SMD = (평균 Persuadables − 평균 나머지) ÷ √((분산₁ + 분산₂)/2) — Austin(2009). 판정 기준값 없음",
            "note": "관측 Feature(t2 Feature 표)만 쓴다(PRD §21). 원인이 아니라 차이다 — 그 Feature 가 반응을 만든다는 뜻이 아니다"}


def segment_table(churn_p: pd.Series, cate: pd.DataFrame | pd.Series, clv: pd.Series | None,
                  segments: pd.Series, signup_tier: pd.Series | None = None,
                  thresholds: dict[str, float] | None = None, margin_rate: float | None = None,
                  costs: Mapping[str, Any] | None = None) -> pd.DataFrame:
    """SRS SEG-005 고객 세그먼트 표(+ 4분면 · 우선순위 근거 열). 점수는 받은 그대로 옮기고, 결손은 비워 둔다.

    ``priority_score`` = 과제 기본 ``uplift × CLV``(SEG-004). ``expected_net_value_krw`` · ``net_arm`` = 프로젝트 확장
    (S4 와 같은 정의 — ``expected_net_value``). ``margin_rate`` · ``costs`` 가 없으면 확장 열은 비운다.
    """
    idx = churn_p.index
    uplift = uplift_score(cate).reindex(idx)
    if isinstance(cate, pd.DataFrame):
        frame = cate.reindex(idx).astype(float)
        known = frame.notna().any(axis=1)
        arm = pd.Series(None, index=idx, dtype=object)
        arm[known] = frame[known].idxmax(axis=1)
    else:
        arm = pd.Series(None, index=idx, dtype=object)
    table = pd.DataFrame({
        "customer_id": idx.map(str),
        "segment": segments.reindex(idx).to_numpy(),
        "segment_prd_id": segments.reindex(idx).map(SEGMENT_PRD_ID).to_numpy(),
        "quadrant": assign_quadrants(uplift, churn_p, thresholds).reindex(idx).to_numpy(),
        "churn_probability": churn_p.astype(float).to_numpy(),
        "uplift_score": uplift.to_numpy(),
        "uplift_arm": arm.to_numpy(),
        "predicted_clv_12m": (clv.reindex(idx).astype(float).to_numpy() if clv is not None else np.nan),
        "priority_score": priority_score(cate, clv).reindex(idx).to_numpy(),
        **({k: v.to_numpy() for k, v in expected_net_value(cate.reindex(idx), clv, margin_rate, costs).items()}
           if isinstance(cate, pd.DataFrame) else {"expected_net_value_krw": np.nan, "net_arm": None}),
        "signup_tier": (signup_tier.reindex(idx.map(str)).to_numpy() if signup_tier is not None else None),
    })
    return table[list(SEGMENT_TABLE_COLUMNS)].sort_values("customer_id", kind="mergesort").reset_index(drop=True)
