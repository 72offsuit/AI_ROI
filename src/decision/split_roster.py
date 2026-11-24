"""#218 공통 명부 — 기준일(t_prior · t1 · t2)별 고객 역할 · 관측 등급 · 관측 완전성 (DR-218-common-roster).

ML · LSTM 비교(#317) · 고객군 성능(#303 ML-010) · 등급별 이탈률(#221 ANA-008) · 과제 Test 가 **같은 명부**를 쓴다.
한 행 = (고객, 기준일). 라벨 값 · 예측값은 싣지 않는다.

| 기준일 | 역할 | 정의 |
|---|---|---|
| t_prior | ``train`` | Eligible(t_prior) 중 Feature · 라벨([t_prior, t1))이 있는 고객 — 시간 순서 검증의 학습 |
| t1 | ``validation`` | Eligible(t1) 중 탐색 RCT 무처치(T0) · Feature · 라벨이 있는 고객 — 시간 순서 검증의 평가 · 최종 재학습 |
| t2 | ``test`` | Eligible(t2) 중 t1 실험 무처치이고 train · validation 고객이 **아닌** 고객 — 과제 Test(ML-004), GATE 3 동결 뒤 1회 |
| t2 | ``future_existing`` | Eligible(t2) 중 t1 실험 무처치인 train · validation 고객 — 기존 고객의 미래 시점 평가(DR-179), ML-004 에 쓰지 않는다 |
| 모두 | ``excluded`` | 사유 ``exclusion_reason``(``rct_treated`` · ``no_feature_or_label``) |

- t2 역할은 **라벨을 보지 않고** 정한다(``labeled`` 를 받지 않는다). Test 라벨은 GATE 3 동결 뒤에만 연다.
- 규칙: 한 모델의 학습 표본과 평가 표본에 같은 (고객, 기준일) 쌍이 들어가지 않는다. 기준일이 다르면 같은 고객이
  여러 행에 나오는 것은 설계대로다(#218 답변).
- 층화 키 ``stratum`` = ``value_tier`` × ``frequency_tier``(DR-221). ``UNKNOWN`` 도 한 층이다.
- ``observation_complete`` = 그 기준일까지 이벤트를 빠짐없이 읽었다는 실행 근거가 있다. 거짓이면 ``n_events_before_cutoff``
  의 0 은 "관측된 0" 이 아니라 "관측 불명" 이다.
"""

from __future__ import annotations

from collections.abc import Collection, Mapping, Sequence
from typing import Any

import pandas as pd

from src.decision.features.sprint_table import _clean, to_index_time
from src.decision.observed_tiers import BASIS_COLUMNS, TIER_COLUMNS, observed_tiers

ROSTER_VERSION = "split-roster-v1"
DECISION = "docs/decisions/DR-218-common-roster.md"
ORIGINS: tuple[str, ...] = ("t_prior", "t1", "t2")
CONTROL_ARM = "T0"

ROLES: dict[str, str] = {
    "train": "t_prior — 시간 순서 검증의 학습(Feature · [t_prior, t1) 라벨)",
    "validation": "t1 — 시간 순서 검증의 평가 · 최종 재학습(탐색 RCT 무처치 T0)",
    "test": "t2 — 과제 Test(ML-004): t1 실험 무처치 · train · validation 고객 제외, GATE 3 동결 뒤 1회",
    "future_existing": "t2 — 기존 고객의 미래 시점 평가(DR-179): t1 실험 무처치 train · validation 고객, ML-004 판정에 쓰지 않는다",
    "excluded": "어느 역할에도 넣지 않는다 — exclusion_reason",
}
EXCLUSIONS: dict[str, str] = {
    "rct_treated": "t1 탐색 실험에서 처치(T1~T4)를 받았다 — 무처치 라벨이 아니다",
    "no_feature_or_label": "Feature 또는 라벨이 없다(라벨 관측 불충분 · Feature 모집단 밖)",
}
COLUMNS: tuple[str, ...] = (
    "customer_id", "origin", "role", "exclusion_reason", "rct_arm", "observation_complete",
    "n_events_before_cutoff", *TIER_COLUMNS, "stratum", *BASIS_COLUMNS,
)
#: DR-221 "한 번의 예외" 점검 — F1~F4 중 하나가 Eligible 의 이 범위를 벗어나면 결과 전에 한 번 고칠 수 있다.
FREQUENCY_CHECK_RANGE: tuple[float, float] = (0.02, 0.60)
FREQUENCY_CHECK_CODES: tuple[str, ...] = ("F1_ONCE", "F2_RARE", "F3_REGULAR", "F4_FREQUENT")


def order_items_frame(orders: Mapping[str, Any] | None) -> pd.DataFrame | None:
    """교환 묶음 주문(``ExchangeBundle.orders``) → 품목 표(order_id · product_id · quantity · unit_price). 없으면 None."""
    if orders is None:
        return None
    rows = [(str(order_id), str(item.product_id), int(item.quantity), int(item.unit_price))
            for order_id, order in orders.items() for item in getattr(order, "items", ())]
    return pd.DataFrame(rows, columns=["order_id", "product_id", "quantity", "unit_price"])


def event_counts(events: pd.DataFrame, index_time, customers: Sequence[str]) -> pd.Series:
    """고객별 T0 미만 관측 이벤트 수(파생 상태 · 미지의 유형 제외). 없으면 0 — 관측 완전성과 함께 읽는다."""
    t0 = to_index_time(index_time)
    frame = _clean(events)
    ids = pd.Index(sorted({str(c) for c in customers}), name="customer_id")
    counts = frame.loc[(frame["timestamp"] < t0) & frame["customer_id"].isin(ids)].groupby("customer_id").size()
    return counts.reindex(ids, fill_value=0).astype(int)


def _roles(origin: str, ids: pd.Index, cohort: Mapping[str, Any],
           fit_customers: set[str]) -> tuple[pd.Series, pd.Series, pd.Series]:
    arm_map = cohort.get("rct_arm") or {}
    arms = pd.Series([arm_map.get(cid) for cid in ids], index=ids, dtype=object)
    role = pd.Series("excluded", index=ids, dtype=object)
    reason = pd.Series(None, index=ids, dtype=object)
    labeled = {str(c) for c in (cohort.get("labeled") or ())}
    has = pd.Series([cid in labeled for cid in ids], index=ids, dtype=bool)
    if origin == "t_prior":
        role[has] = "train"
        reason[~has] = "no_feature_or_label"
        return role, reason, pd.Series(None, index=ids, dtype=object)
    treated = arms.notna() & (arms != CONTROL_ARM)
    reason[treated] = "rct_treated"
    if origin == "t1":
        role[~treated & has] = "validation"
        reason[~treated & ~has] = "no_feature_or_label"
        return role, reason, arms
    fit = pd.Series([cid in fit_customers for cid in ids], index=ids, dtype=bool)
    role[~treated & fit] = "future_existing"
    role[~treated & ~fit] = "test"
    return role, reason, arms


def _frequency_check(tiers: pd.DataFrame) -> dict[str, Any]:
    n = len(tiers)
    shares = {code: (float((tiers["frequency_tier"] == code).sum()) / n if n else None)
              for code in FREQUENCY_CHECK_CODES}
    low, high = FREQUENCY_CHECK_RANGE
    outside = [code for code, s in shares.items() if s is not None and not (low <= s <= high)]
    return {"denominator": "Eligible", "n": n, "shares": shares, "range": [low, high], "outside": outside,
            "rule": "DR-221 한 번의 예외 — 라벨 · 점수 없이 분포만 보고, 벗어나면 결과 전에 한 번만 구간을 고친다"}


def build_split_roster(events: pd.DataFrame, signups: Mapping[str, Any], *, cohorts: Mapping[str, Mapping[str, Any]],
                       order_items: pd.DataFrame | None, observation_complete: bool,
                       not_run: Mapping[str, str] | None = None,
                       ) -> tuple[pd.DataFrame, dict[str, Any], dict[str, pd.DataFrame]]:
    """기준일별 명부 · 요약 · 관측 등급 표.

    ``cohorts[origin]`` = ``{"index_time", "label_window": (start, end) | None, "eligible": [...],
    "labeled": [...] | None, "rct_arm": {customer_id: arm} | None}``. 빠진 기준일은 ``not_run[origin]`` 사유와 함께
    요약에 ``not_run`` 으로 남는다. t2 의 ``labeled`` 는 쓰지 않는다(라벨을 보지 않고 역할을 정한다).
    """
    unknown = set(cohorts) - set(ORIGINS)
    if unknown:
        raise ValueError(f"모르는 기준일: {sorted(unknown)}")
    frames: list[pd.DataFrame] = []
    tiers_by_origin: dict[str, pd.DataFrame] = {}
    summary: dict[str, Any] = {}
    fit_customers: set[str] = set()
    for origin in ORIGINS:
        cohort = cohorts.get(origin)
        if cohort is None:
            summary[origin] = {"status": "not_run",
                               "reason": (not_run or {}).get(origin, "이 기준일의 입력이 없다")}
            continue
        t0 = to_index_time(cohort["index_time"])
        tiers = observed_tiers(events, t0, cohort["eligible"], signups, order_items=order_items)
        ids = tiers.index
        role, reason, arms = _roles(origin, ids, cohort, fit_customers)
        if origin in ("t_prior", "t1"):
            fit_customers |= set(ids[role.isin(("train", "validation"))])
        frame = tiers.copy()
        frame.attrs = {}
        frame["stratum"] = frame["value_tier"] + "|" + frame["frequency_tier"]
        frame["role"] = role
        frame["exclusion_reason"] = reason
        frame["rct_arm"] = arms
        frame["observation_complete"] = bool(observation_complete)
        frame["n_events_before_cutoff"] = event_counts(events, t0, ids)
        frame["origin"] = origin
        frame = frame.reset_index()[list(COLUMNS)]
        frames.append(frame)
        tiers_by_origin[origin] = tiers
        window = cohort.get("label_window")
        meta = tiers.attrs["observed_tiers"]
        summary[origin] = {
            "status": "ok",
            "index_time": t0.isoformat(),
            "feature_cutoff": f"< {t0.isoformat()}",
            "label_window": (None if window is None else
                             {"start": to_index_time(window[0]).isoformat(), "end": to_index_time(window[1]).isoformat()}),
            "labels_used_for_roles": origin != "t2",
            "n_eligible": int(len(ids)),
            "roles": {k: int(v) for k, v in role.value_counts().sort_index().items()},
            "exclusions": {k: int(v) for k, v in reason.dropna().value_counts().sort_index().items()},
            "observation_complete": bool(observation_complete),
            "tiers": {k: meta[k] for k in ("version", "window", "window_complete", "value_boundaries_krw",
                                           "n_value_basis", "counts", "unknown_reasons", "items", "signup")},
            "tier_counts_by_role": {
                r: {col: {str(k): int(v) for k, v in tiers.loc[role == r, col].value_counts().sort_index().items()}
                    for col in TIER_COLUMNS}
                for r in sorted(set(role))},
            "frequency_band_check": _frequency_check(tiers),
        }
    roster = (pd.concat(frames, ignore_index=True) if frames
              else pd.DataFrame(columns=list(COLUMNS)))
    duplicated = int(roster.duplicated(["customer_id", "origin"]).sum())
    if duplicated:
        raise ValueError(f"(고객, 기준일) 행이 {duplicated}개 겹친다")
    record = {
        "version": ROSTER_VERSION,
        "decision": DECISION,
        "tier_decision": "docs/decisions/DR-221-observed-tiers.md",
        "row": "(customer_id, origin) — 라벨 값 · 예측값은 싣지 않는다",
        "roles": dict(ROLES),
        "exclusions": dict(EXCLUSIONS),
        "stratum": "value_tier|frequency_tier (DR-221) — UNKNOWN 도 한 층",
        "pair_rule": "한 모델의 학습 표본과 평가 표본에 같은 (customer_id, origin) 쌍이 들어가지 않는다",
        "n_rows": int(len(roster)),
        "origins": summary,
    }
    return roster, record, tiers_by_origin
