"""스프린트 1 Feature 테이블 — 벡터화(pandas) 판본 (이슈 #144, 에픽 #142).

## D1 `calculate_features` 를 감싸지 않은 이유 (15 분 판단, PR 본문에 같은 내용)

`d1_calculate.calculate_features` 는 **정본 계산기**이고 이 모듈은 그것을 대체하지
않는다. 다만 스프린트 학습 루프에 바로 감쌀 수 없었다:

  1. `_Customer.__init__` 가 고객마다 `batch.events`(전체 이벤트 dict 복사)를 훑는다 —
     O(고객 × 이벤트). 수천 고객 × 수십만 이벤트에서 학습 1 회가 분 단위를 넘는다.
  2. `ObservationClaim` 이 없으면 모든 창이 `OBSERVATION_UNKNOWN` 으로 **전부 null** 이다.
     관측 주장(claim)을 누가 어떤 근거로 내는지는 #126 미결이라 여기서 지어낼 수 없다.
  3. `EventBatch.guard` 는 cutoff 이후 이벤트가 하나라도 있으면 입력 전체를 거부한다 —
     라벨 창을 함께 담은 원천 frame 을 그대로 줄 수 없다(사전 절단 필요).

그래서 **D1 Feature ID·공개 이름·창 경계(`[T0-(d+o), T0-o)`)를 그대로 따르는**
벡터화 테이블을 만들었다. 차이는 `SPRINT_FEATURES` 의 `d1_diff` 와 아래에 적는다.
정합 작업은 #150 이 한다.

## 규율
  - **T0(`index_time`) 이전 이벤트만 쓴다** (`timestamp < T0`, D1 `[…, T0)`).
  - 파생 상태 이벤트(`churn`·`at_risk`·`inactive`)와 배정 필드
    (`treatment_group`·`treatment_id`·`experiment_id`)는 읽지 않는다.
  - **결손을 0 으로 채우지 않는다.** 분모가 0 이거나 근거 이벤트가 없으면 NaN 이고,
    사유는 `frame.attrs["nan_reasons"]` 에 있다. 대치(impute)·이상치 절단은 **학습 fold
    에서 fit** 해야 누수가 없으므로 `make_preprocessor()` 가 모델 파이프라인 안에서 한다.
  - 창이 관측 시작보다 앞으로 뻗으면(데이터가 그 창을 다 덮지 못하면) 값은 계산하되
    `frame.attrs["incomplete_windows"]` 에 그 Feature 를 적는다 — 통과로 보이지 않게.
  - 모집단: T0 이전에 관측 이벤트가 1 건 이상 있는 고객(`observed_only`).
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from src.measurement.schema import TIMEZONE, EventType

EVENT_TYPES = frozenset(item.value for item in EventType)
VISITS = frozenset({"session_start", "return_visit"})
MARKETING_ONLY = frozenset({"campaign_exposed", "push_sent", "coupon_exposed"})
ACTIVITY = EVENT_TYPES - MARKETING_ONLY  # D1 ACTIVITY 와 같은 정의
FORBIDDEN_COLUMNS = ("treatment_group", "treatment_id", "experiment_id")

LABEL_DEF = "index 이후 42일 무구매"


@dataclass(frozen=True)
class SprintFeature:
    name: str
    d1_id: str | None  # None 이면 스프린트 전용(D1 사전에 없음)
    group: str
    d1_diff: str = ""


#: 순서가 곧 컬럼 순서다. `d1_id` 가 있으면 이름은 D1 `DEFINITIONS` 의 공개 이름과 같다
#: (`tests/test_feature_sprint_table.py` 가 대조한다).
SPRINT_FEATURES: tuple[SprintFeature, ...] = (
    # ── RFM ─────────────────────────────────────────────────────────────
    SprintFeature("recency", "F01", "rfm"),
    SprintFeature("frequency_90d", "F02", "rfm"),
    SprintFeature("monetary_90d", "F03", "rfm",
                  "주문 금액 결손 시 D1 은 계산 불가, 스프린트는 그 주문을 합에서 빼고 NaN 아님"),
    SprintFeature("aov_90d", "F04", "rfm"),
    SprintFeature("avg_purchase_interval", "F05", "rfm",
                  "이력 시작=관측 시작(D1 은 H 창 + 관측 주장 필요)"),
    SprintFeature("purchase_interval_cv_90d", "F06", "rfm"),
    SprintFeature("purchase_cycle_anomaly", "F07", "rfm"),
    SprintFeature("frequency_observed", None, "rfm", "D1 F41 은 NO_LIFETIME_COVERAGE 로 보류"),
    SprintFeature("monetary_observed", None, "rfm"),
    SprintFeature("tenure_days", None, "rfm", "첫 관측 이벤트 후 경과일(가입일 아님)"),
    # ── 방문·활동 ───────────────────────────────────────────────────────
    SprintFeature("visit_count_60d", "F08", "activity"),
    SprintFeature("visit_recency", "F09", "activity"),
    SprintFeature("active_days_30d", "F10", "activity"),
    SprintFeature("return_visit_count_60d", None, "activity"),
    SprintFeature("push_sent_count_60d", None, "marketing"),
    # ── 탐색·퍼널 ───────────────────────────────────────────────────────
    SprintFeature("page_view_count_60d", "F11", "funnel"),
    SprintFeature("product_view_count_60d", "F12", "funnel"),
    SprintFeature("distinct_viewed_products_180d", "F13", "funnel"),
    SprintFeature("search_count_60d", "F14", "funnel"),
    SprintFeature("add_to_cart_count_60d", "F15", "funnel"),
    SprintFeature("remove_from_cart_count_60d", "F16", "funnel"),
    SprintFeature("checkout_count_60d", "F17", "funnel"),
    SprintFeature("view_to_cart_rate_60d", None, "funnel"),
    SprintFeature("cart_to_purchase_rate_60d", None, "funnel"),
    SprintFeature("checkout_to_purchase_rate_60d", None, "funnel"),
    # ── 부수 ─────────────────────────────────────────────────────────────
    SprintFeature("cs_contact_count_60d", "F18", "service"),
    SprintFeature("review_count_180d", "F19", "service"),
    # ── 쿠폰·캠페인 반응 이력 ───────────────────────────────────────────
    SprintFeature("coupon_exposure_count_180d", "F20", "marketing"),
    SprintFeature("coupon_used_order_count_180d", "F21", "marketing"),
    SprintFeature("days_since_last_campaign_180d", "F22", "marketing"),
    SprintFeature("coupon_click_count_180d", None, "marketing"),
    SprintFeature("coupon_click_rate_180d", None, "marketing"),
    SprintFeature("coupon_use_order_share_180d", None, "marketing"),
    SprintFeature("campaign_exposure_count_180d", None, "marketing"),
    # ── 카테고리 ─────────────────────────────────────────────────────────
    SprintFeature("category_entropy_180d", "F23", "category"),
    SprintFeature("dominant_category_share_180d", "F24", "category"),
    # ── 최근 vs 이전 기간 변화 ─────────────────────────────────────────
    SprintFeature("visit_count_change_2w", "F25", "change"),
    SprintFeature("purchase_frequency_change", "F26", "change"),
    SprintFeature("purchase_interval_change", "F27", "change"),
    SprintFeature("visit_count_change_30d", None, "change"),
    SprintFeature("monetary_change_30d", None, "change"),
    SprintFeature("active_days_change_2w", None, "change"),
    # ── 시간대 ───────────────────────────────────────────────────────────
    SprintFeature("weekday_purchase_ratio", "F28", "time"),
    SprintFeature("morning_activity_ratio", "F29", "time"),
    SprintFeature("evening_activity_ratio", "F30", "time"),
    SprintFeature("weekend_purchase_ratio", "F42", "time"),
    # ── 세션 품질 ───────────────────────────────────────────────────────
    SprintFeature("avg_session_duration", "F31", "session",
                  "D1 은 완결 세션 사실(#126) 필요, 스프린트는 session_duration 값이 있는 세션 평균"),
    SprintFeature("page_views_per_session", "F32", "session", "분모=창 안에 이벤트가 있는 세션"),
    SprintFeature("search_to_purchase_conversion", "F33", "session",
                  "검색 세션 중 같은 세션 구매 비율(D1 의 unknown 판정 없음)"),
    SprintFeature("session_duration_change", "F34", "session"),
    SprintFeature("cart_conversion_change", "F35", "session",
                  "장바구니 세션 중 같은 세션 구매 비율의 30d 차"),
)
FEATURE_NAMES: tuple[str, ...] = tuple(f.name for f in SPRINT_FEATURES)


def to_index_time(index_time) -> pd.Timestamp:
    """T0. tz 가 없으면 스키마 단일 타임존(KST)으로 해석한다 — 이벤트가 아니라 설정값이다."""
    stamp = pd.Timestamp(index_time)
    if stamp.tzinfo is None:
        stamp = stamp.tz_localize(TIMEZONE)
    return stamp.tz_convert(TIMEZONE)


def _clean(events: pd.DataFrame) -> pd.DataFrame:
    """관측 원본 이벤트만. 파생 상태·미지의 event_type 은 버리고 배정 필드는 떼어 낸다."""
    frame = events[events["event_type"].isin(EVENT_TYPES)]
    return frame.drop(columns=[c for c in FORBIDDEN_COLUMNS if c in frame.columns])


def population(events: pd.DataFrame, index_time) -> pd.Index:
    """T0 이전에 관측 이벤트가 1 건 이상 있는 고객 (`observed_only`)."""
    t0 = to_index_time(index_time)
    frame = _clean(events)
    ids = frame.loc[frame["timestamp"] < t0, "customer_id"].dropna().unique()
    return pd.Index(sorted(ids), name="customer_id")


def _orders(frame: pd.DataFrame) -> pd.DataFrame:
    """purchase 이벤트를 주문 단위로. order_id 가 없으면 event_id 를 주문 키로 쓴다."""
    purchases = frame[frame["event_type"] == "purchase"].copy()
    purchases["_order_key"] = purchases["order_id"].where(
        purchases["order_id"].notna(), "evt:" + purchases["event_id"].astype(str))
    purchases = purchases.sort_values(["customer_id", "timestamp", "event_id"], kind="mergesort")
    purchases = purchases.drop_duplicates(subset=["customer_id", "_order_key"], keep="first")
    purchases["_amount"] = purchases["order_amount"].astype("Float64").astype(float)
    return purchases


class _Builder:
    def __init__(self, events: pd.DataFrame, t0: pd.Timestamp, ids: pd.Index):
        frame = _clean(events)
        frame = frame[(frame["timestamp"] < t0) & frame["customer_id"].isin(ids)].copy()
        frame["_age"] = (t0 - frame["timestamp"]).dt.total_seconds() / 86400.0
        frame["_kst_date"] = frame["timestamp"].dt.tz_convert(TIMEZONE).dt.normalize()
        self.frame, self.t0, self.ids = frame, t0, ids
        self.orders = _orders(frame)
        self.data_start_age = float(frame["_age"].max()) if len(frame) else 0.0
        self.incomplete: list[str] = []
        self.reasons: dict[str, str] = {}

    # 창 [T0-(d+o), T0-o) ⇔ age ∈ (o, d+o]
    @staticmethod
    def _in(frame: pd.DataFrame, days: float | None, offset: float = 0) -> pd.DataFrame:
        if days is None:
            return frame
        return frame[(frame["_age"] > offset) & (frame["_age"] <= days + offset)]

    def _note_window(self, name: str, days: float | None, offset: float = 0) -> None:
        if days is not None and days + offset > self.data_start_age + 1e-9:
            if name not in self.incomplete:
                self.incomplete.append(name)

    def _full(self, series: pd.Series) -> pd.Series:
        return series.reindex(self.ids)

    def count(self, types, days, offset=0, unique=None, *, name=None) -> pd.Series:
        """관측 모집단 안의 빈도. 창 안에 이벤트가 없으면 **관측된 0** 이다(결손 아님)."""
        if name:
            self._note_window(name, days, offset)
        rows = self._in(self.frame[self.frame["event_type"].isin(types)], days, offset)
        if unique is not None:
            rows = rows.dropna(subset=[unique])
            counts = rows.groupby("customer_id")[unique].nunique()
        else:
            counts = rows.groupby("customer_id").size()
        return self._full(counts).fillna(0).astype(float)

    def order_count(self, days, offset=0) -> pd.Series:
        rows = self._in(self.orders, days, offset)
        return self._full(rows.groupby("customer_id").size()).fillna(0).astype(float)

    def order_sum(self, days, offset=0) -> pd.Series:
        rows = self._in(self.orders, days, offset).dropna(subset=["_amount"])
        return self._full(rows.groupby("customer_id")["_amount"].sum()).fillna(0).astype(float)

    def recency(self, types, days=None) -> pd.Series:
        rows = self._in(self.frame[self.frame["event_type"].isin(types)], days)
        return self._full(rows.groupby("customer_id")["_age"].min())

    def gap_mean_std(self, days=None, offset=0) -> tuple[pd.Series, pd.Series, pd.Series]:
        rows = self._in(self.orders, days, offset).sort_values(["customer_id", "timestamp"])
        gaps = rows.groupby("customer_id")["timestamp"].diff().dt.total_seconds() / 86400.0
        gaps = pd.DataFrame({"customer_id": rows["customer_id"], "gap": gaps}).dropna()
        grouped = gaps.groupby("customer_id")["gap"]
        return (self._full(grouped.mean()), self._full(grouped.std(ddof=0)),
                self._full(grouped.size()).fillna(0))

    def sessions(self, days, offset=0) -> pd.DataFrame:
        rows = self._in(self.frame.dropna(subset=["session_id"]), days, offset)
        typ = rows["event_type"]
        rows = rows.assign(
            _pv=(typ == "page_view"), _search=(typ == "search"),
            _cart=(typ == "add_to_cart"), _buy=(typ == "purchase"),
            _dur=rows["session_duration"].astype("Float64").astype(float))
        return rows.groupby(["customer_id", "session_id"]).agg(
            pv=("_pv", "sum"), search=("_search", "max"), cart=("_cart", "max"),
            buy=("_buy", "max"), dur=("_dur", "max")).reset_index()


def _ratio(num: pd.Series, den: pd.Series) -> pd.Series:
    """분모 0 은 NaN (ZERO_DENOMINATOR). 0 으로 채우지 않는다."""
    return (num / den.where(den != 0)).astype(float)


def build_feature_table(events: pd.DataFrame, index_time) -> pd.DataFrame:
    """index=customer_id, 컬럼=`FEATURE_NAMES`(전부 float). T0 이전 이벤트만 쓴다.

    `attrs`: `index_time`·`nan_reasons`(Feature→NaN 사유)·`incomplete_windows`
    (관측 시작보다 앞으로 뻗은 창을 쓴 Feature)·`population_scope`.
    """
    t0 = to_index_time(index_time)
    ids = population(events, t0)
    b = _Builder(events, t0, ids)
    out: dict[str, pd.Series] = {}
    R = b.reasons

    # RFM
    purchase = frozenset({"purchase"})
    out["recency"] = b._full(b.orders.groupby("customer_id")["_age"].min())
    R["recency"] = "NO_SOURCE_EVENT: 관측 구매 없음"
    b._note_window("frequency_90d", 90)
    out["frequency_90d"] = b.order_count(90)
    b._note_window("monetary_90d", 90)
    out["monetary_90d"] = b.order_sum(90)
    out["aov_90d"] = _ratio(out["monetary_90d"], out["frequency_90d"])
    R["aov_90d"] = "ZERO_DENOMINATOR: 90일 주문 0"
    mean_all, _, _ = b.gap_mean_std()
    out["avg_purchase_interval"] = mean_all
    R["avg_purchase_interval"] = "INSUFFICIENT_PURCHASE_INTERVALS: 관측 주문 < 2"
    mean90, std90, n90 = b.gap_mean_std(90)
    out["purchase_interval_cv_90d"] = _ratio(std90, mean90).where(n90 >= 2)
    R["purchase_interval_cv_90d"] = "INSUFFICIENT_PURCHASE_INTERVALS: 90일 간격 < 2 또는 평균 0"
    out["purchase_cycle_anomaly"] = _ratio(out["recency"], out["avg_purchase_interval"])
    R["purchase_cycle_anomaly"] = "F01 또는 F05 결손 / 평균 간격 0"
    out["frequency_observed"] = b.order_count(None)
    out["monetary_observed"] = b.order_sum(None)
    out["tenure_days"] = b._full(b.frame.groupby("customer_id")["_age"].max())

    # 방문·활동
    out["visit_count_60d"] = b.count(VISITS, 60, unique="session_id", name="visit_count_60d")
    out["visit_recency"] = b.recency(VISITS)
    R["visit_recency"] = "NO_SOURCE_EVENT: 관측 방문 없음"
    b._note_window("active_days_30d", 30)
    act30 = b._in(b.frame[b.frame["event_type"].isin(ACTIVITY)], 30)
    out["active_days_30d"] = b._full(
        act30.groupby("customer_id")["_kst_date"].nunique()).fillna(0).astype(float)
    out["return_visit_count_60d"] = b.count({"return_visit"}, 60, name="return_visit_count_60d")
    out["push_sent_count_60d"] = b.count({"push_sent"}, 60, name="push_sent_count_60d")

    # 탐색·퍼널
    for name, typ, days, unique in [
        ("page_view_count_60d", "page_view", 60, None),
        ("product_view_count_60d", "product_view", 60, None),
        ("distinct_viewed_products_180d", "product_view", 180, "product_id"),
        ("search_count_60d", "search", 60, None),
        ("add_to_cart_count_60d", "add_to_cart", 60, None),
        ("remove_from_cart_count_60d", "remove_from_cart", 60, None),
        ("checkout_count_60d", "checkout_start", 60, "order_id"),
        ("cs_contact_count_60d", "cs_contact", 60, None),
        ("review_count_180d", "review", 180, None),
        ("coupon_exposure_count_180d", "coupon_exposed", 180, None),
        ("coupon_used_order_count_180d", "coupon_use", 180, "order_id"),
        ("coupon_click_count_180d", "coupon_clicked", 180, None),
        ("campaign_exposure_count_180d", "campaign_exposed", 180, None),
    ]:
        out[name] = b.count({typ}, days, unique=unique, name=name)
    orders60 = b.order_count(60)
    out["view_to_cart_rate_60d"] = _ratio(out["add_to_cart_count_60d"], out["product_view_count_60d"])
    R["view_to_cart_rate_60d"] = "ZERO_DENOMINATOR: 60일 product_view 0"
    out["cart_to_purchase_rate_60d"] = _ratio(orders60, out["add_to_cart_count_60d"])
    R["cart_to_purchase_rate_60d"] = "ZERO_DENOMINATOR: 60일 add_to_cart 0"
    out["checkout_to_purchase_rate_60d"] = _ratio(orders60, out["checkout_count_60d"])
    R["checkout_to_purchase_rate_60d"] = "ZERO_DENOMINATOR: 60일 checkout 0"

    # 쿠폰·캠페인
    out["days_since_last_campaign_180d"] = b.recency({"campaign_exposed"}, 180)
    R["days_since_last_campaign_180d"] = "NO_SOURCE_EVENT: 180일 캠페인 노출 없음"
    out["coupon_click_rate_180d"] = _ratio(out["coupon_click_count_180d"], out["coupon_exposure_count_180d"])
    R["coupon_click_rate_180d"] = "ZERO_DENOMINATOR: 180일 쿠폰 노출 0"
    orders180 = b.order_count(180)
    out["coupon_use_order_share_180d"] = _ratio(out["coupon_used_order_count_180d"], orders180)
    R["coupon_use_order_share_180d"] = "ZERO_DENOMINATOR: 180일 주문 0"

    # 카테고리 (product_view 180d)
    b._note_window("category_entropy_180d", 180)
    b._note_window("dominant_category_share_180d", 180)
    views = b._in(b.frame[(b.frame["event_type"] == "product_view")], 180).dropna(subset=["category"])
    cat = views.groupby(["customer_id", "category"]).size()
    share = cat / cat.groupby(level=0).transform("sum")
    out["category_entropy_180d"] = b._full((-(share * np.log(share))).groupby(level=0).sum())
    out["dominant_category_share_180d"] = b._full(share.groupby(level=0).max())
    R["category_entropy_180d"] = R["dominant_category_share_180d"] = "ZERO_DENOMINATOR: 180일 카테고리 있는 product_view 0"

    # 변화
    v_recent = b.count(VISITS, 14, unique="session_id", name="visit_count_change_2w")
    v_prev = b.count(VISITS, 14, 14, unique="session_id", name="visit_count_change_2w")
    out["visit_count_change_2w"] = _ratio(v_recent, v_prev)
    R["visit_count_change_2w"] = "ZERO_DENOMINATOR: 이전 14일 방문 0"
    b._note_window("purchase_frequency_change", 30, 30)
    out["purchase_frequency_change"] = (b.order_count(30) - b.order_count(30, 30)) / 30.0
    b._note_window("purchase_interval_change", 45, 45)
    m_recent, _, _ = b.gap_mean_std(45)
    m_prev, _, _ = b.gap_mean_std(45, 45)
    out["purchase_interval_change"] = m_recent - m_prev
    R["purchase_interval_change"] = "INSUFFICIENT_PURCHASE_INTERVALS: 최근·이전 45일 중 간격 없음"
    out["visit_count_change_30d"] = _ratio(
        b.count(VISITS, 30, unique="session_id", name="visit_count_change_30d"),
        b.count(VISITS, 30, 30, unique="session_id", name="visit_count_change_30d"))
    R["visit_count_change_30d"] = "ZERO_DENOMINATOR: 이전 30일 방문 0"
    b._note_window("monetary_change_30d", 30, 30)
    out["monetary_change_30d"] = b.order_sum(30) - b.order_sum(30, 30)
    b._note_window("active_days_change_2w", 14, 14)
    act = b.frame[b.frame["event_type"].isin(ACTIVITY)]

    def _active_days(days, offset):
        rows = b._in(act, days, offset)
        return b._full(rows.groupby("customer_id")["_kst_date"].nunique()).fillna(0).astype(float)

    out["active_days_change_2w"] = _active_days(14, 0) - _active_days(14, 14)

    # 시간대 (KST)
    b._note_window("weekday_purchase_ratio", 90)
    o90 = b._in(b.orders, 90)
    wd = o90["timestamp"].dt.weekday
    n_o90 = b._full(o90.groupby("customer_id").size()).fillna(0)
    out["weekday_purchase_ratio"] = _ratio(
        b._full((wd < 5).groupby(o90["customer_id"]).sum()).fillna(0), n_o90)
    out["weekend_purchase_ratio"] = _ratio(
        b._full((wd >= 5).groupby(o90["customer_id"]).sum()).fillna(0), n_o90)
    R["weekday_purchase_ratio"] = R["weekend_purchase_ratio"] = "ZERO_DENOMINATOR: 90일 주문 0"
    a90 = b._in(act, 90)
    hour = a90["timestamp"].dt.hour
    n_a90 = b._full(a90.groupby("customer_id").size()).fillna(0)
    out["morning_activity_ratio"] = _ratio(
        b._full(((hour >= 6) & (hour < 12)).groupby(a90["customer_id"]).sum()).fillna(0), n_a90)
    out["evening_activity_ratio"] = _ratio(
        b._full((hour >= 18).groupby(a90["customer_id"]).sum()).fillna(0), n_a90)
    R["morning_activity_ratio"] = R["evening_activity_ratio"] = "ZERO_DENOMINATOR: 90일 활동 0"
    for name in ("weekend_purchase_ratio", "morning_activity_ratio", "evening_activity_ratio"):
        b._note_window(name, 90)

    # 세션 품질
    for name, days in [("avg_session_duration", 60), ("page_views_per_session", 60),
                       ("search_to_purchase_conversion", 60), ("session_duration_change", 28),
                       ("cart_conversion_change", 60)]:
        b._note_window(name, days)
    s60 = b.sessions(60)
    g60 = s60.groupby("customer_id")
    out["avg_session_duration"] = b._full(g60["dur"].mean())
    R["avg_session_duration"] = "NO_SOURCE_EVENT: 60일 session_duration 기록 없음"
    out["page_views_per_session"] = _ratio(b._full(g60["pv"].sum()).fillna(0),
                                           b._full(g60.size()).fillna(0))
    R["page_views_per_session"] = "ZERO_DENOMINATOR: 60일 세션 0"
    searched = s60[s60["search"]]
    out["search_to_purchase_conversion"] = b._full(
        searched.groupby("customer_id")["buy"].mean().astype(float))
    R["search_to_purchase_conversion"] = "ZERO_DENOMINATOR: 60일 검색 세션 0"
    d_recent = b._full(b.sessions(14).groupby("customer_id")["dur"].mean())
    d_prev = b._full(b.sessions(14, 14).groupby("customer_id")["dur"].mean())
    out["session_duration_change"] = d_recent - d_prev
    R["session_duration_change"] = "NO_SOURCE_EVENT: 최근·이전 14일 중 세션 시간 없음"

    def _cart_conv(days, offset):
        s = b.sessions(days, offset)
        carted = s[s["cart"]]
        return b._full(carted.groupby("customer_id")["buy"].mean().astype(float))

    out["cart_conversion_change"] = _cart_conv(30, 0) - _cart_conv(30, 30)
    R["cart_conversion_change"] = "ZERO_DENOMINATOR: 최근·이전 30일 중 장바구니 세션 0"

    table = pd.DataFrame({name: out[name].astype(float) for name in FEATURE_NAMES}, index=ids)
    table.index.name = "customer_id"
    table = table.replace([np.inf, -np.inf], np.nan)
    table.attrs.update(
        index_time=t0.isoformat(),
        nan_reasons={k: v for k, v in R.items() if table[k].isna().any()},
        incomplete_windows=sorted(b.incomplete),
        population_scope="observed_only",
        label_def=LABEL_DEF,
    )
    return table


def build_outcomes(events: pd.DataFrame, index_time, window_days: int = 42, *,
                   allow_incomplete: bool = False) -> pd.DataFrame:
    """index=customer_id(=`population`), 컬럼 `churn`·`purchases`·`revenue`.

    라벨 창은 `[T0, T0 + window_days)`. `churn = 1` ⇔ 창 안 구매 0 회.
    `purchases`·`revenue` 의 0 은 **관측된 0** 이다(창 안에 주문이 없었다).
    주문 금액이 결손인 주문이 있는 고객의 `revenue` 는 NaN 이다(0 으로 채우지 않는다).

    관측 데이터가 라벨 창 끝까지 닿지 않으면 라벨이 검열(censoring)되어 이탈이 부풀려진다.
    그 경우 `ValueError` 를 던진다 — `allow_incomplete=True` 면 `attrs` 에 표시만 한다.
    """
    t0 = to_index_time(index_time)
    end = t0 + pd.Timedelta(days=window_days)
    ids = population(events, t0)
    frame = _clean(events)
    data_end = frame["timestamp"].max() if len(frame) else None
    complete = data_end is not None and data_end >= end - pd.Timedelta(days=1)
    if not complete and not allow_incomplete:
        raise ValueError(
            f"라벨 창이 관측 범위를 넘는다: 창 끝 {end.isoformat()} > 마지막 이벤트 "
            f"{None if data_end is None else data_end.isoformat()}")
    future = frame[(frame["timestamp"] >= t0) & (frame["timestamp"] < end)
                   & frame["customer_id"].isin(ids)]
    orders = _orders(future)
    grouped = orders.groupby("customer_id")
    purchases = grouped.size().reindex(ids).fillna(0).astype(int)
    revenue = grouped["_amount"].sum(min_count=1).reindex(ids)
    has_missing_amount = grouped["_amount"].apply(lambda s: s.isna().any()).reindex(ids).fillna(False)
    revenue = revenue.where(purchases > 0, 0.0).where(~has_missing_amount.astype(bool))
    out = pd.DataFrame({"churn": (purchases == 0).astype(int), "purchases": purchases,
                        "revenue": revenue.astype(float)}, index=ids)
    out.index.name = "customer_id"
    out.attrs.update(label_def=f"index 이후 {window_days}일 무구매", window_days=window_days,
                     index_time=t0.isoformat(), label_window_complete=bool(complete))
    return out


def make_preprocessor(clip_quantiles: tuple[float, float] = (0.01, 0.99)):
    """결측·이상치 처리 — **학습 fold 에서만 fit** 한다 (sklearn transformer).

    순서: 분위수 절단(학습 분위 1%·99%) → 중앙값 대치 + 결측 지시자 컬럼.
    지시자를 남기는 이유: "값이 없다" 자체가 신호다(예: 구매 이력 없음 → recency NaN).
    """
    from sklearn.base import BaseEstimator, TransformerMixin
    from sklearn.impute import SimpleImputer
    from sklearn.pipeline import make_pipeline

    class QuantileClipper(BaseEstimator, TransformerMixin):
        def __init__(self, low=0.01, high=0.99):
            self.low, self.high = low, high

        def fit(self, X, y=None):
            arr = np.asarray(X, dtype=float)
            with np.errstate(all="ignore"):
                self.lo_ = np.nanquantile(arr, self.low, axis=0) if arr.size else np.array([])
                self.hi_ = np.nanquantile(arr, self.high, axis=0) if arr.size else np.array([])
            return self

        def transform(self, X):
            arr = np.asarray(X, dtype=float)
            lo = np.where(np.isnan(self.lo_), -np.inf, self.lo_)
            hi = np.where(np.isnan(self.hi_), np.inf, self.hi_)
            return np.where(np.isnan(arr), np.nan, np.clip(arr, lo, hi))

    return make_pipeline(
        QuantileClipper(*clip_quantiles),
        SimpleImputer(strategy="median", add_indicator=True, keep_empty_features=True),
    )
