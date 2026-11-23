"""관측 등급 — ANA-008 · ML-010 이 함께 쓰는 고객 등급 (#221 · #303, DR-221-observed-tiers).

통신사가 골드 · 실버 같은 등급별로 이탈률을 보듯, **관측할 수 있는 값만으로** 고객을 네 축으로 나눈다.
숨은 Persona 라벨 · 시뮬레이터 내부 · 이탈 라벨 · 모델 점수는 쓰지 않는다.

| 축 | 열 | 근거 값 | 구간 |
|---|---|---|---|
| 가치 등급 | ``value_tier`` | ``spend_180d`` — 창 안 주문 금액 합 | 등급 모집단 구매 고객의 50 · 80 분위수 → 하위 50% · 중위 30% · 상위 20% |
| 구매 횟수 | ``frequency_tier`` | ``orders_180d`` — 창 안 주문 수 | 1회 · 2~4회 · 5~12회 · 13회 이상 |
| 가입 시기 | ``signup_tier`` | ``tenure_days`` — T0 날짜 − 가입일(KST) | 180일 미만 신규 · 이상 기존 |
| 주 구매 상품군 | ``category_tier`` | 창 안 품목 금액이 가장 큰 상품군(비중 ``main_category_share``) | 5종, 금액이 같으면 ``Category`` 순서 |

- 창은 ``[T0 − 180일, T0)`` 다(`sprint_table` 창과 같은 규약). 창 안 주문이 없으면 가치 ``V0_NONE`` ·
  횟수 ``F0_NONE`` · 상품군 ``NONE`` 이다 — 관측된 0 이다.
- 근거가 결손이면 ``UNKNOWN`` 이고 사유를 attrs 에 남긴다. 다른 값으로 메우지 않는다.
- 주문은 ``purchase`` 이벤트이고 같은 ``order_id`` 는 1건이다(`sprint_table._orders` 와 같은 규칙).
- 가입일은 교환 묶음 고객 명부, 품목은 교환 묶음 ``order_items``, 상품 → 상품군은 T0 미만 이벤트의
  ``product_id`` · ``category`` 다(교환 계약 v1 · 이벤트 스키마 — 공개 계약만).

## 결과 전 고정
창 · 분위수 · 횟수 구간 · 신규 기준 · 동률 순서는 등급별 이탈률 · 성능을 보기 **전에** 정했다(DR-221).
결과를 보고 바꾸려면 새 결정 기록을 쓰고 두 판을 함께 싣는다. 가치 경계(분위수)는 **기준일마다** 그
기준일의 등급 모집단으로 다시 잰다 — 그 기준일 이전 자료만 쓰고, 실제 경계 금액을 attrs 에 남긴다.

## 모집단
호출자가 ``population`` 으로 준다. 공통 입력(#218 명부 · ML-010 · ANA-008 · DL 비교)은 기준일별
Eligible 고객이다(DR-221). 분위수도 이 모집단으로 잰다 — 모집단 밖 고객은 경계를 바꾸지 않는다.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import numpy as np
import pandas as pd

from src.measurement.schema import TIMEZONE, Category
from src.decision.features.sprint_table import _clean, _orders, to_index_time

TIER_VERSION = "observed-tier-v1"
DECISION = "docs/decisions/DR-221-observed-tiers.md"

#: 창 길이(일). 가치 · 횟수 · 상품군이 같은 창을 쓴다.
WINDOW_DAYS = 180
#: 가치 등급 경계 — 하위 50% · 중위 30% · 상위 20%. 상위 20% 는 AI 세그먼트의 고가치 경계
#: (config/model_config.yaml segmentation.clv_high_q = 0.8)와 같은 뜻이다.
VALUE_QUANTILES: tuple[float, float] = (0.5, 0.8)
QUANTILE_METHOD = "linear"
#: (최소, 최대(None = 상한 없음), 코드). 180일 ÷ 횟수 = 평균 간격 — 4회 이하는 45일 이상(이탈 기준 42일보다 김),
#: 13회 이상은 14일 미만(2주에 한 번보다 잦음).
FREQUENCY_BANDS: tuple[tuple[int, int | None, str], ...] = (
    (1, 1, "F1_ONCE"), (2, 4, "F2_RARE"), (5, 12, "F3_REGULAR"), (13, None, "F4_FREQUENT"),
)
#: 가입 후 이 일수 미만이면 신규. 창 길이와 같다 — 기존 고객은 창 전체가 가입 뒤라 금액 · 횟수를 그대로 비교할 수 있다.
NEW_CUSTOMER_DAYS = 180
#: 상품군 동률 순서 = 측정 계층 ``Category`` 정의 순서.
CATEGORY_ORDER: tuple[str, ...] = tuple(item.value for item in Category)
#: 고객군 지표의 표본 부족 기준(ANA-008 · ML-010) — 값은 싣되 비교 · 판정에 쓰지 않는다.
MIN_GROUP_CUSTOMERS = 100
MIN_GROUP_MINORITY = 10

UNKNOWN = "UNKNOWN"
TIER_COLUMNS: tuple[str, ...] = ("value_tier", "frequency_tier", "signup_tier", "category_tier")
BASIS_COLUMNS: tuple[str, ...] = ("spend_180d", "orders_180d", "tenure_days", "main_category_share")

#: 코드 → 뜻(보고서 · CSV 머리말용). 화면 표시명은 대시보드가 정한다.
TIER_LABELS: dict[str, dict[str, str]] = {
    "value_tier": {"V0_NONE": "180일 구매 없음", "V1_LOW": "하위 50%", "V2_MID": "중위 30%",
                   "V3_HIGH": "상위 20%", UNKNOWN: "판정 불가(금액 결손)"},
    "frequency_tier": {"F0_NONE": "0회", "F1_ONCE": "1회", "F2_RARE": "2~4회", "F3_REGULAR": "5~12회",
                       "F4_FREQUENT": "13회 이상"},
    "signup_tier": {"NEW": "신규(가입 180일 미만)", "EXISTING": "기존(가입 180일 이상)",
                    UNKNOWN: "판정 불가(가입일 없음)"},
    "category_tier": {**{code: code for code in CATEGORY_ORDER}, "NONE": "180일 구매 없음",
                      UNKNOWN: "판정 불가(품목 · 상품군 없음)"},
}


def product_categories_from_events(events: pd.DataFrame, index_time) -> pd.Series:
    """T0 미만 이벤트의 ``product_id`` → ``category``. 한 상품이 두 상품군으로 나오면 그 상품은 빼고 수를 attrs 에 남긴다."""
    t0 = to_index_time(index_time)
    frame = _clean(events)
    rows = frame.loc[frame["timestamp"] < t0, ["product_id", "category"]].dropna()
    rows = rows.astype(str).drop_duplicates()
    kinds = rows.groupby("product_id")["category"].nunique()
    conflicting = kinds[kinds > 1].index
    mapping = rows[~rows["product_id"].isin(conflicting)].set_index("product_id")["category"].sort_index()
    mapping.attrs["conflicting_products"] = int(len(conflicting))
    return mapping


def _signup_day(value: Any):
    if value is None or (not isinstance(value, str) and pd.isna(value)):
        return None
    return pd.Timestamp(value).date()


def _category_tiers(orders: pd.DataFrame, ids: pd.Index, order_items: Any,
                    mapping: pd.Series) -> tuple[pd.Series, pd.Series, dict[str, int]]:
    """창 안 주문의 품목 금액(수량 × 단가)을 상품군별로 더해 가장 큰 상품군과 그 비중을 낸다."""
    keys = orders[["customer_id", "_order_key"]].rename(columns={"_order_key": "order_id"})
    items = pd.DataFrame(order_items)
    missing = [c for c in ("order_id", "product_id", "quantity", "unit_price") if c not in items.columns]
    if missing:
        raise ValueError(f"order_items 에 열이 없다: {missing}")
    items = items[["order_id", "product_id", "quantity", "unit_price"]].astype({"order_id": str, "product_id": str})
    items = items.merge(keys, on="order_id", how="inner")
    items["category"] = items["product_id"].map(mapping)
    items["_amount"] = items["quantity"].astype(float) * items["unit_price"].astype(float)

    per = (items.dropna(subset=["category"]).groupby(["customer_id", "category"])["_amount"].sum()
           .unstack(fill_value=0.0))
    ordered = [c for c in CATEGORY_ORDER if c in per.columns]
    per = per.reindex(columns=ordered + sorted(set(per.columns) - set(ordered)))
    total = per.sum(axis=1)
    per, total = per[total > 0], total[total > 0]

    category = pd.Series(UNKNOWN, index=ids, dtype=object)
    share = pd.Series(np.nan, index=ids, dtype=float)
    if len(per):
        category.loc[per.index] = per.idxmax(axis=1).to_numpy()   # 동률이면 앞 열 = CATEGORY_ORDER
        share.loc[per.index] = (per.max(axis=1) / total).to_numpy()
    window_orders = set(keys["order_id"])
    audit = {
        "n_window_orders": len(window_orders),
        "n_window_orders_without_items": len(window_orders - set(items["order_id"])),
        "n_items": int(len(items)),
        "n_items_unmapped": int(items["category"].isna().sum()),
        "n_conflicting_products": int(mapping.attrs.get("conflicting_products", 0)),
    }
    return category, share, audit


def observed_tiers(events: pd.DataFrame, index_time, population, signups: Mapping[str, Any], *,
                   order_items: Any = None, product_categories: Mapping[str, str] | pd.Series | None = None,
                   ) -> pd.DataFrame:
    """``population`` 고객의 관측 등급. index = customer_id(정렬), 열 = ``BASIS_COLUMNS`` + ``TIER_COLUMNS``.

    - ``events``: 측정 계층 이벤트 frame(`data.load_events` 형식, timestamp tz-aware). T0 미만만 쓴다.
    - ``signups``: customer_id → 가입일(date · 'YYYY-MM-DD'). 교환 묶음 고객 명부.
    - ``order_items``: 교환 묶음 품목(열 order_id · product_id · quantity · unit_price). 없으면 상품군은
      구매 고객 전원 ``UNKNOWN`` — 장바구니 · 조회로 근사하지 않는다.
    - ``product_categories``: 상품 → 상품군. 없으면 ``product_categories_from_events`` 로 만든다.
    반환 frame 의 ``attrs["observed_tiers"]`` 에 규칙 · 경계 금액 · 등급별 수 · 결손 사유가 있다.
    """
    t0 = to_index_time(index_time)
    if isinstance(population, pd.Series) and population.dtype == bool:
        raise TypeError("population 은 customer_id 목록이다 — Eligible 플래그 Series 면 참인 index 를 넘긴다")
    ids = pd.Index(sorted({str(c) for c in population}), name="customer_id")
    frame = _clean(events)
    before = frame[frame["timestamp"] < t0]
    data_start = before["timestamp"].min() if len(before) else None
    window_start = t0 - pd.Timedelta(days=WINDOW_DAYS)

    orders = _orders(before[before["customer_id"].isin(ids)])
    orders = orders[orders["timestamp"] >= window_start]
    n_orders = orders.groupby("customer_id").size().reindex(ids, fill_value=0).astype(int)
    amount_missing = orders["_amount"].isna().groupby(orders["customer_id"]).any().reindex(ids, fill_value=False)
    spend = orders.groupby("customer_id")["_amount"].sum(min_count=1).reindex(ids).astype(float)
    spend = spend.where(~amount_missing.astype(bool)).where(n_orders > 0, 0.0)

    # 가치 — 창 안 주문이 있고 금액을 아는 모집단 고객으로 분위수를 잰다.
    basis = spend[(n_orders > 0) & spend.notna()]
    value = pd.Series(UNKNOWN, index=ids, dtype=object)
    value[n_orders == 0] = "V0_NONE"
    bounds = None
    if len(basis):
        p50, p80 = (float(v) for v in np.quantile(basis.to_numpy(dtype=float), VALUE_QUANTILES,
                                                  method=QUANTILE_METHOD))
        value.loc[basis.index] = np.where(basis >= p80, "V3_HIGH", np.where(basis >= p50, "V2_MID", "V1_LOW"))
        bounds = {"p50": p50, "p80": p80}

    frequency = pd.Series("F0_NONE", index=ids, dtype=object)
    for low, high, code in FREQUENCY_BANDS:
        frequency[(n_orders >= low) & (n_orders <= (np.inf if high is None else high))] = code

    t0_day = t0.tz_convert(TIMEZONE).date()
    signup_days = [_signup_day(signups.get(cid)) for cid in ids]
    tenure = pd.Series([np.nan if d is None else float((t0_day - d).days) for d in signup_days],
                       index=ids, dtype=float)
    signup = pd.Series(UNKNOWN, index=ids, dtype=object)
    signup[(tenure >= 0) & (tenure < NEW_CUSTOMER_DAYS)] = "NEW"
    signup[tenure >= NEW_CUSTOMER_DAYS] = "EXISTING"

    reasons: dict[str, str] = {}
    if order_items is None:
        category = pd.Series(UNKNOWN, index=ids, dtype=object)
        share = pd.Series(np.nan, index=ids, dtype=float)
        item_audit: dict[str, int] | None = None
        reasons["category_tier"] = "NO_ORDER_ITEMS: 교환 묶음 품목이 없다 — 장바구니 · 조회로 근사하지 않는다"
    else:
        mapping = (product_categories_from_events(events, t0) if product_categories is None
                   else pd.Series(product_categories, dtype=object))
        category, share, item_audit = _category_tiers(orders, ids, order_items, mapping)
        if ((category == UNKNOWN) & (n_orders > 0)).any():
            reasons["category_tier"] = "NO_KNOWN_ITEMS: 창 안 주문에 상품군을 아는 품목이 없다"
    category[n_orders == 0] = "NONE"
    if (value == UNKNOWN).any():
        reasons["value_tier"] = "AMOUNT_MISSING: 창 안 주문 금액 결손"
    if (signup == UNKNOWN).any():
        reasons["signup_tier"] = "SIGNUP_MISSING · SIGNUP_AFTER_CUTOFF: 가입일이 명부에 없거나 T0 날짜보다 늦다"

    out = pd.DataFrame({
        "spend_180d": spend, "orders_180d": n_orders, "tenure_days": tenure, "main_category_share": share,
        "value_tier": value, "frequency_tier": frequency, "signup_tier": signup, "category_tier": category,
    }, index=ids)
    out.attrs["observed_tiers"] = {
        "version": TIER_VERSION,
        "decision": DECISION,
        "index_time": t0.isoformat(),
        "window": {"start": window_start.isoformat(), "end": t0.isoformat(), "days": WINDOW_DAYS,
                   "semantics": "[T0 − 180일, T0)"},
        "data_start": None if data_start is None else data_start.isoformat(),
        "window_complete": bool(data_start is not None and data_start <= window_start),
        "value_quantiles": list(VALUE_QUANTILES),
        "quantile_method": QUANTILE_METHOD,
        "value_boundaries_krw": bounds,
        "n_value_basis": int(len(basis)),
        "frequency_bands": [[low, high, code] for low, high, code in FREQUENCY_BANDS],
        "new_customer_days": NEW_CUSTOMER_DAYS,
        "category_order": list(CATEGORY_ORDER),
        "n_population": int(len(ids)),
        "counts": {col: {str(k): int(v) for k, v in out[col].value_counts().sort_index().items()}
                   for col in TIER_COLUMNS},
        "signup": {"n_missing": int(sum(d is None for d in signup_days)), "n_after_cutoff": int((tenure < 0).sum())},
        "items": item_audit,
        "unknown_reasons": reasons,
    }
    return out


def small_group(n: int, positives: int | None = None) -> bool:
    """고객군 지표의 표본 부족(DR-221) — 고객 100명 미만이거나, 라벨이 있으면 적은 쪽 클래스가 10명 미만.

    표본 부족 고객군도 지표 값과 수를 싣는다. 비교 · 판정 · 적용 범위 결정(ML-010)에 쓰지 않을 뿐이다.
    결과를 보고 등급을 합치거나 다시 나누지 않는다.
    """
    if n < MIN_GROUP_CUSTOMERS:
        return True
    if positives is None:
        return False
    return min(positives, n - positives) < MIN_GROUP_MINORITY
