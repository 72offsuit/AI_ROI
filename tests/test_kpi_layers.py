"""KPI 계산 계약 검사 — 계층 0·1·2 + 47종 분류 (이슈 #46).

**표준 라이브러리만 쓴다.** `kpi.py` 가 순수 함수이므로 픽스처 파일이 필요 없다.

★ 이 파일이 지키는 것 셋:

  1. **"세어 보니 0" 과 "셀 근거가 없다" 를 가른다** (AC-4). 둘 다 0 이지만 다른
     상태이고, 후자를 전자로 읽으면 잘못된 결론이 조용히 만들어진다.
  2. **이름이 갈라져 있다** (R-2). `churn_rate`/`churn_label`,
     `retention_rate`/`cohort_retention_rate` 가 다른 함수다.
  3. **`limit_note` 가 실제로 실린다** (AC-4b). 선택 필드라 빠뜨려도 스키마가
     잡지 않는다 — 없으면 화면의 `한계` 칩이 영원히 뜨지 않는다.

실행:
    python3 -m unittest tests.test_kpi_layers -v
"""

from __future__ import annotations

import unittest
import uuid
from datetime import date, timedelta

from src.measurement import coverage as cov
from src.measurement import kpi
from src.measurement.schema import (
    DerivedStateType,
    EventType,
    EVENT_FIELDS,
    MetricStatus,
    OBSERVABLE_METRIC_SOURCES,
    ReasonCode,
    Unit,
)

INDEX_DATE = date(2025, 11, 12)


def purchase(customer: str, day: date, amount: int = 47000) -> dict[str, object]:
    return {
        "event_id": str(uuid.uuid4()),
        "customer_id": customer,
        "timestamp": f"{day.isoformat()}T09:00:00.000+09:00",
        "event_type": EventType.PURCHASE.value,
        "session_id": f"S-{customer}-1759276800000",
        "page_type": "complete",
        "order_id": "O20251001-000123",
        "order_amount": amount,
    }


def event_of(event_type: EventType, customer: str, day: date) -> dict[str, object]:
    return {
        "event_id": str(uuid.uuid4()),
        "customer_id": customer,
        "timestamp": f"{day.isoformat()}T09:00:00.000+09:00",
        "event_type": event_type.value,
    }


def manifest(**overrides: object) -> dict[str, object]:
    """`sink.manifest()` 와 같은 모양의 최소 픽스처."""
    base: dict[str, object] = {
        "rows": 0, "rejected": 0, "event_type_counts": {},
        "field_coverage": {}, "missing_fields": [], "sources": {},
        "unavailable_metrics": sorted(OBSERVABLE_METRIC_SOURCES),
    }
    base.update(overrides)
    return base


# ══════════════════════════════════════════════════════════════════════════
# ★ AC-4 — 이 프로젝트의 핵심 경계
# ══════════════════════════════════════════════════════════════════════════

class TestMeasuredZeroVersusNoBasis(unittest.TestCase):
    """★★ "세어 보니 0" 과 "셀 근거가 없다" 를 가른다.

    가르는 기준은 **그 모집단을 셀 수 있었는가**다:
      - 건수 지표는 셀 수 있다 (없으면 0건이다)            → ok + 0
      - 금액·비율 지표는 근거가 없으면 셀 모집단이 없다      → unavailable
    """

    def test_zero_coupon_use_is_a_measured_zero(self) -> None:
        """AC-4 · T-5 — `coupon_use` 0건이면 **`ok` + `0`**."""
        result = kpi.coupon_usage_count([], index_date=INDEX_DATE)
        self.assertIs(MetricStatus.OK, result.status)
        self.assertEqual(0, result.value)
        self.assertEqual(0, result.basis.observed_count)  # type: ignore[union-attr]
        self.assertIsNotNone(result.basis, "측정된 0 에는 기준이 있다")

    def test_zero_purchase_is_not_zero_aov(self) -> None:
        """AC-4 · T-6 — `purchase` 0건이면 **`unavailable`**. 0원이 아니다."""
        result = kpi.average_order_value([], index_date=INDEX_DATE)
        self.assertIs(MetricStatus.UNAVAILABLE, result.status)
        self.assertIsNone(result.value)
        self.assertIs(ReasonCode.NO_SOURCE_EVENT, result.reason_code)
        self.assertIsNone(result.basis, "계산 불가는 기준을 가질 수 없다")

    def test_zero_denominator_ratio_is_never_ok(self) -> None:
        """AC-4 — 분모가 0 인 비율은 `ok` 일 수 없다. 계약도 스키마로 거부한다."""
        result = kpi.rejection_rate(manifest(rows=0, rejected=0))
        self.assertIsNot(MetricStatus.OK, result.status)
        self.assertIsNone(result.value)

    def test_events_ingested_zero_is_ok_because_sink_was_readable(self) -> None:
        """manifest 를 열었으므로 셀 수 있었다 — 0 은 측정값이다."""
        result = kpi.events_ingested(manifest(rows=0))
        self.assertIs(MetricStatus.OK, result.status)
        self.assertEqual(0, result.value)

    def test_missing_field_coverage_is_unavailable_not_zero_percent(self) -> None:
        """필드가 적용되는 이벤트가 0건이면 분모가 없다 — `0%` 가 아니다."""
        rates = kpi.field_fill_rate(cov.new_tally())
        self.assertEqual(len(EVENT_FIELDS), len(rates), "22컬럼 전부 낸다")
        for name, metric in rates.items():
            with self.subTest(field=name):
                self.assertIs(MetricStatus.UNAVAILABLE, metric.status)
                self.assertIsNone(metric.value)


class TestNamesAreSeparated(unittest.TestCase):
    """R-2 — 전향/후향, 상태/코호트를 같은 이름으로 쓰지 않는다."""

    def test_churn_rate_and_churn_label_are_distinct_functions(self) -> None:
        """플래그가 아니라 **다른 함수**다. PRD Risk 7 (Label Leakage)."""
        self.assertIsNot(kpi.churn_rate, kpi.churn_label)
        # 같은 함수에 방향 플래그가 있으면 안 된다.
        for func in (kpi.churn_rate, kpi.churn_label):
            with self.subTest(func=func.__name__):
                self.assertNotIn("prospective", func.__code__.co_varnames)
                self.assertNotIn("retrospective", func.__code__.co_varnames)

    def test_churn_rate_is_retrospective_and_label_is_prospective(self) -> None:
        """방향이 `basis.window.direction` 에 기록된다."""
        events = [purchase("C00000001", INDEX_DATE - timedelta(days=5))]
        rate = kpi.churn_rate(events, index_date=INDEX_DATE)
        label = kpi.churn_label(events, index_date=INDEX_DATE)
        self.assertEqual("point_in_time", rate.basis.window.direction.value)  # type: ignore[union-attr]
        self.assertEqual("prospective", label.basis.window.direction.value)  # type: ignore[union-attr]

    def test_retention_and_cohort_retention_are_distinct(self) -> None:
        self.assertIsNot(kpi.retention_rate, kpi.cohort_retention_rate)

    def test_average_order_value_denominator_is_orders_not_customers(self) -> None:
        """★ 같은 고객의 주문 2건 → 분모 2 (고객 수 1 이 아니다)."""
        events = [
            purchase("C00000001", INDEX_DATE - timedelta(days=1), 10000),
            purchase("C00000001", INDEX_DATE - timedelta(days=2), 20000),
        ]
        result = kpi.average_order_value(events, index_date=INDEX_DATE)
        self.assertEqual(15000, result.value, "주문 건수로 나눈다")
        self.assertEqual(2, result.basis.denominator)  # type: ignore[union-attr]
        self.assertIn("주문 건수", result.basis.denominator_definition)  # type: ignore[union-attr]


class TestSignatureEnforcesConventions(unittest.TestCase):
    """AC-2 — 규약을 시그니처로 강제한다."""

    METRIC_FUNCTIONS = (
        kpi.churn_rate, kpi.retention_rate, kpi.repurchase_rate,
        kpi.winback_rate, kpi.purchase_frequency, kpi.purchase_interval,
        kpi.average_order_value, kpi.churn_label, kpi.coupon_usage_count,
        kpi.coupon_exposure_count, kpi.campaign_response_count,
    )

    def test_index_date_has_no_default(self) -> None:
        """★ R-1 — `date.today()` 기본값이 있으면 실행 시각에 따라 값이 달라진다."""
        import inspect

        for func in self.METRIC_FUNCTIONS:
            with self.subTest(func=func.__name__):
                parameter = inspect.signature(func).parameters["index_date"]
                self.assertIs(
                    inspect.Parameter.empty, parameter.default,
                    f"{func.__name__}.index_date 에 기본값이 있다 — "
                    "'현재'라는 암묵 기준일이 생긴다",
                )
                self.assertIs(
                    inspect.Parameter.KEYWORD_ONLY, parameter.kind,
                    "위치 인자로 받으면 호출부에서 무엇인지 안 보인다",
                )

    def test_every_metric_returns_metric_value(self) -> None:
        """★ R-8 — `float` 를 돌려주는 함수가 없다. `0.0` 을 돌려줄 자리가 없다."""
        from src.measurement.schema import MetricValue

        for func in self.METRIC_FUNCTIONS:
            with self.subTest(func=func.__name__):
                self.assertIsInstance(
                    func([], index_date=INDEX_DATE), MetricValue
                )


class TestCustomersTableAbsence(unittest.TestCase):
    """AC-3b — 모집단이 성립하지 않는 지표를 재분류한다 (리드 지시)."""

    def test_cohort_retention_is_precondition_missing(self) -> None:
        """`signup_date` 가 없다. **`events` 첫 등장일로 근사하지 않는다.**"""
        events = [purchase("C00000001", INDEX_DATE - timedelta(days=5))]
        result = kpi.cohort_retention_rate(events, index_date=INDEX_DATE, month=1)
        self.assertIs(MetricStatus.UNAVAILABLE, result.status)
        self.assertIs(ReasonCode.PRECONDITION_MISSING, result.reason_code)
        self.assertIn(
            "customers", [ref.ref for ref in result.blocked_by],
            "막은 원인이 customers 테이블임을 화면이 알 수 있어야 한다 (DB-012)",
        )

    def test_cohort_retention_names_the_remedy_issue(self) -> None:
        """조치 줄에 `Ecommerce_Service #29` 가 있어야 한다 — 막힌 것을 여는 방법."""
        result = kpi.cohort_retention_rate([], index_date=INDEX_DATE, month=1)
        self.assertIn("#29", result.reason_detail or "")

    def test_repurchase_rate_is_not_precondition_missing(self) -> None:
        """★★ Matthias 항목4 — `repurchase_rate` 는 여기 들어가지 않는다.

        계산식이 `purchase` 만 쓴다. `PRECONDITION_MISSING` 은 *"근거가 없다"* 는
        뜻인데 **근거는 있다.** 과대보고의 거울상이지만 **이유를 틀리게 말하는
        것은 같다.**
        """
        events = [
            purchase("C00000001", INDEX_DATE - timedelta(days=1)),
            purchase("C00000001", INDEX_DATE - timedelta(days=10)),
            purchase("C00000002", INDEX_DATE - timedelta(days=3)),
        ]
        result = kpi.repurchase_rate(events, index_date=INDEX_DATE)
        self.assertIs(MetricStatus.OK, result.status)
        self.assertEqual(0.5, result.value, "2명 중 1명이 2회 이상 구매")

    def test_repurchase_rate_population_is_stated_precisely(self) -> None:
        """R-4 — "고객" 이라고만 쓰지 않는다. `P_all(D)` 도 아니라고 밝힌다."""
        events = [purchase("C00000001", INDEX_DATE - timedelta(days=1))]
        basis = kpi.repurchase_rate(events, index_date=INDEX_DATE).basis
        self.assertIn("purchase 이벤트가 1건 이상", basis.population)  # type: ignore[union-attr]
        self.assertIn("P_all(D) 이 아니다", basis.population)  # type: ignore[union-attr]


class TestUnconfirmedThresholds(unittest.TestCase):
    """D-5 — 임계값 28/42/60 은 가설값이다. Lock 하지 않는다."""

    def test_churn_rate_is_unconfirmed_with_params(self) -> None:
        events = [purchase("C00000001", INDEX_DATE - timedelta(days=50))]
        result = kpi.churn_rate(events, index_date=INDEX_DATE)
        self.assertIs(MetricStatus.UNCONFIRMED, result.status)
        self.assertIs(ReasonCode.PARAM_UNCONFIRMED, result.reason_code)
        self.assertIn("no_purchase_days", result.params_used or {})
        self.assertEqual(1.0, result.value, "50일 경과 → 이탈")

    def test_retention_inherits_the_same_uncertainty(self) -> None:
        """파생값이 원지표보다 확실해질 수 없다."""
        events = [purchase("C00000001", INDEX_DATE - timedelta(days=50))]
        result = kpi.retention_rate(events, index_date=INDEX_DATE)
        self.assertIs(MetricStatus.UNCONFIRMED, result.status)
        self.assertEqual(0.0, result.value)

    def test_label_window_is_locked_so_label_is_not_unconfirmed(self) -> None:
        """★ `label_window_days = 42` 는 C1 에서 Lock 한다 — 가설값이 아니다."""
        events = [purchase("C00000001", INDEX_DATE - timedelta(days=5))]
        result = kpi.churn_label(events, index_date=INDEX_DATE)
        self.assertIs(MetricStatus.OK, result.status)
        self.assertIsNone(result.reason_code)


class TestChurnDefinition(unittest.TestCase):
    """FR-10 · SIM-009 — 이탈 정의(임계값 · rule_operator)를 바꾸면 지표가 그 정의를 따른다."""

    AND = kpi.ChurnDefinition(rule_operator="AND")
    SHORT_LOGIN_OR = kpi.ChurnDefinition(no_login_days=30)

    def _lapsed_buyer_still_visiting(self) -> list[dict[str, object]]:
        # 50일 전 구매 뒤 10일 전에도 접속 — 미구매 조건만 만족한다.
        return [
            purchase("C00000001", INDEX_DATE - timedelta(days=50)),
            event_of(EventType.SESSION_START, "C00000001", INDEX_DATE - timedelta(days=10)),
        ]

    def test_default_or_rule_matches_purchase_only_threshold(self) -> None:
        # 마지막 접속은 마지막 구매보다 이를 수 없어 기본 OR(42/60)은 미구매 조건 하나와 같다.
        result = kpi.churn_rate(self._lapsed_buyer_still_visiting(), index_date=INDEX_DATE)
        self.assertEqual(1.0, result.value)
        self.assertEqual(kpi.ChurnDefinition(), kpi.DEFAULT_CHURN_DEFINITION)
        self.assertEqual(
            {"at_risk_days": 28, "no_purchase_days": 42, "no_login_days": 60, "rule_operator": "OR"},
            dict(result.params_used or {}),
        )

    def test_and_rule_requires_both_conditions(self) -> None:
        events = self._lapsed_buyer_still_visiting()
        self.assertEqual(0.0, kpi.churn_rate(events, index_date=INDEX_DATE, definition=self.AND).value)
        gone = [purchase("C00000002", INDEX_DATE - timedelta(days=70))]
        self.assertEqual(1.0, kpi.churn_rate(gone, index_date=INDEX_DATE, definition=self.AND).value)

    def test_or_rule_with_short_login_threshold_catches_absent_recent_buyer(self) -> None:
        # 35일 전 구매·32일 전 마지막 접속: 미구매 42일 전이지만 미접속 30일은 넘었다.
        events = [
            purchase("C00000001", INDEX_DATE - timedelta(days=35)),
            event_of(EventType.SESSION_START, "C00000001", INDEX_DATE - timedelta(days=32)),
        ]
        self.assertEqual(0.0, kpi.churn_rate(events, index_date=INDEX_DATE).value)
        self.assertEqual(
            1.0, kpi.churn_rate(events, index_date=INDEX_DATE, definition=self.SHORT_LOGIN_OR).value
        )

    def test_retention_and_winback_follow_the_definition(self) -> None:
        events = self._lapsed_buyer_still_visiting()
        self.assertEqual(
            1.0, kpi.retention_rate(events, index_date=INDEX_DATE, definition=self.AND).value
        )
        # 100일 전 구매 → D−42 시점 58일 경과(이탈), 그 뒤 5일 전 재구매.
        winback = [
            purchase("C00000003", INDEX_DATE - timedelta(days=100)),
            purchase("C00000003", INDEX_DATE - timedelta(days=5)),
        ]
        self.assertEqual(1.0, kpi.winback_rate(winback, index_date=INDEX_DATE).value)
        late_login = kpi.ChurnDefinition(no_login_days=90, rule_operator="AND")
        self.assertIs(
            MetricStatus.UNAVAILABLE,
            kpi.winback_rate(winback, index_date=INDEX_DATE, definition=late_login).status,
            "AND·미접속 90일이면 D−42 시점 이탈 고객이 없다",
        )

    def test_derived_states_partition_buyers_under_and_rule(self) -> None:
        events = self._lapsed_buyer_still_visiting() + [
            purchase("C00000002", INDEX_DATE - timedelta(days=70)),
            purchase("C00000004", INDEX_DATE - timedelta(days=5)),
        ]
        result = kpi.derived_state_count(events, index_date=INDEX_DATE, definition=self.AND)
        # C1 은 미구매 50일이지만 접속 10일이라 AND 에서 이탈이 아니고 위험 구간이다.
        self.assertEqual((1, 1, 1), (
            result["inactive"].value, result["at_risk"].value, result["churn"].value,
        ))
        self.assertEqual("AND", (result["churn"].params_used or {})["rule_operator"])

    def test_invalid_definitions_are_rejected(self) -> None:
        for kwargs in (
            {"rule_operator": "XOR"},
            {"at_risk_days": 42},
            {"no_login_days": 0},
            {"no_purchase_days": True},
        ):
            with self.subTest(**kwargs), self.assertRaises(ValueError):
                kpi.ChurnDefinition(**kwargs)  # type: ignore[arg-type]

    def test_one_shot_iterable_gives_the_same_result(self) -> None:
        events = self._lapsed_buyer_still_visiting()
        self.assertEqual(
            kpi.churn_rate(events, index_date=INDEX_DATE, definition=self.AND).value,
            kpi.churn_rate(iter(events), index_date=INDEX_DATE, definition=self.AND).value,  # type: ignore[arg-type]
        )


class TestExclusionIsReported(unittest.TestCase):
    """R-6 — 분모에서 제외한 고객을 값과 함께 보고한다."""

    def test_purchase_interval_reports_excluded_customers(self) -> None:
        """구매 1건 고객은 간격이 정의되지 않아 제외되고, 그 수가 남는다."""
        events = [
            purchase("C00000001", INDEX_DATE - timedelta(days=1)),
            purchase("C00000001", INDEX_DATE - timedelta(days=11)),
            purchase("C00000002", INDEX_DATE - timedelta(days=3)),  # 1건 → 제외
        ]
        result = kpi.purchase_interval(events, index_date=INDEX_DATE)
        self.assertIs(MetricStatus.OK, result.status)
        self.assertEqual(10, result.value)
        self.assertEqual(1, result.basis.excluded_count)  # type: ignore[union-attr]
        self.assertTrue(result.basis.excluded_reason)  # type: ignore[union-attr]

    def test_all_single_purchase_customers_give_unavailable(self) -> None:
        """전원이 1건이면 간격 0일이 아니라 계산 대상이 없다."""
        events = [purchase("C00000001", INDEX_DATE - timedelta(days=3))]
        result = kpi.purchase_interval(events, index_date=INDEX_DATE)
        self.assertIs(MetricStatus.UNAVAILABLE, result.status)
        self.assertIsNone(result.value)


class TestLimitNote(unittest.TestCase):
    """★ AC-4b — 정밀도 한계를 데이터에 남긴다 (N-8).

    `limit_note` 는 **선택 필드라 빠뜨려도 스키마가 잡지 않는다.** 이 테스트가
    없으면 화면의 `한계` 칩(V-7)이 영원히 뜨지 않는 것을 아무도 모른다.
    """

    def test_campaign_response_count_carries_its_limit(self) -> None:
        events = [
            event_of(EventType.COUPON_CLICKED, "C00000001", INDEX_DATE - timedelta(days=1))
        ]
        result = kpi.campaign_response_count(events, index_date=INDEX_DATE)
        self.assertIs(MetricStatus.OK, result.status, "값은 나온다")
        self.assertTrue(result.limit_note, "한계 한 줄이 없으면 V-7 칩이 안 뜬다")
        self.assertIn("과소계상", result.limit_note or "")

    def test_limit_note_is_not_unconfirmed(self) -> None:
        """★ `status` 는 `ok` 다. 파라미터로 맞아지는 종류가 아니다.

        `unconfirmed` 는 파라미터가 확정되면 값이 맞아진다. **한계는 이벤트가
        추가되지 않으면 영원히 과소계상**이다. 둘을 섞으면 고쳐질 것과 고쳐지지
        않을 것이 같아 보인다.
        """
        events = [
            event_of(EventType.COUPON_CLICKED, "C00000001", INDEX_DATE - timedelta(days=1))
        ]
        result = kpi.campaign_response_count(events, index_date=INDEX_DATE)
        self.assertIsNot(MetricStatus.UNCONFIRMED, result.status)
        self.assertIsNone(result.params_used)


class TestDerivedStateDistribution(unittest.TestCase):
    """리드 판정 G-8 — 파생 상태를 게시 시점에 계산한다. 조건 넷을 전부 지킨다."""

    def _events(self) -> list[dict[str, object]]:
        return [
            purchase("C00000001", INDEX_DATE - timedelta(days=5)),   # inactive
            purchase("C00000002", INDEX_DATE - timedelta(days=30)),  # at_risk
            purchase("C00000003", INDEX_DATE - timedelta(days=60)),  # churn
        ]

    def test_three_states_are_counted(self) -> None:
        result = kpi.derived_state_count(self._events(), index_date=INDEX_DATE)
        self.assertEqual(
            {item.value for item in DerivedStateType}, set(result)
        )
        self.assertEqual(1, result["inactive"].value)
        self.assertEqual(1, result["at_risk"].value)
        self.assertEqual(1, result["churn"].value)

    def test_condition_1_derived_with_derivation(self) -> None:
        """① 저장된 사실과 구분되어야 한다."""
        for state, metric in kpi.derived_state_count(
            self._events(), index_date=INDEX_DATE
        ).items():
            with self.subTest(state=state):
                self.assertIs(True, metric.derived)
                self.assertTrue(metric.derivation)

    def test_condition_2_unconfirmed_with_params(self) -> None:
        """② 임계값이 가설값이다."""
        for state, metric in kpi.derived_state_count(
            self._events(), index_date=INDEX_DATE
        ).items():
            with self.subTest(state=state):
                self.assertIs(MetricStatus.UNCONFIRMED, metric.status)
                self.assertIn("at_risk_days", metric.params_used or {})

    def test_condition_3_feature_ban_is_written_into_the_data(self) -> None:
        """③ *"Feature 로 쓰지 말라"* 가 `derivation` 에 있어야 한다 (PRD Risk 7)."""
        for state, metric in kpi.derived_state_count(
            self._events(), index_date=INDEX_DATE
        ).items():
            with self.subTest(state=state):
                self.assertIn("Feature", metric.derivation or "")
                self.assertIn("금지", metric.derivation or "")

    def test_condition_4_derived_states_stay_out_of_observables(self) -> None:
        """★★ ④ 가장 위험한 자리 — Observable 16개가 파생 상태에 의존하지 않는다.

        파생 상태가 `kpi_report` 에 나타나는 순간 *"이제 Feature 로 써도 되는 것
        아닌가"* 로 읽힐 수 있다. `tests/test_schema.py` 의
        `test_no_observable_depends_on_derived_state` 와 짝이다.
        """
        derived = {item.value for item in DerivedStateType}
        for metric, sources in OBSERVABLE_METRIC_SOURCES.items():
            with self.subTest(metric=metric):
                self.assertEqual(set(), set(sources) & derived)
        # 분포 지표 이름 자체도 Observable 목록에 없어야 한다.
        for state in derived:
            self.assertNotIn(f"derived_state_count[{state}]", OBSERVABLE_METRIC_SOURCES)


class TestIngestionGap(unittest.TestCase):
    """X-5 — 공백은 세고, 그것이 무엇인지는 모른다고 말한다."""

    def test_gap_is_counted(self) -> None:
        dates = [date(2025, 10, 1), date(2025, 10, 3)]
        result = kpi.ingestion_days_gap(dates)
        self.assertIs(MetricStatus.OK, result.status)
        self.assertEqual(1, result.value, "10-02 가 비었다")

    def test_single_partition_has_no_span(self) -> None:
        result = kpi.ingestion_days_gap([date(2025, 10, 1)])
        self.assertIs(MetricStatus.UNAVAILABLE, result.status)

    def test_attribution_is_not_run_and_never_claims_no_activity(self) -> None:
        """★ *"활동 없음"* 이라고 쓰지 않는다 — 0 채우기와 같은 종류의 잘못이다."""
        result = kpi.ingestion_gap_attribution()
        self.assertIs(MetricStatus.NOT_RUN, result.status)
        self.assertIs(ReasonCode.PRECONDITION_MISSING, result.reason_code)
        self.assertIn("구분할 수 없다", result.reason_detail or "")
        # 단정하는 문구가 없어야 한다.
        self.assertNotIn("활동이 없었다", result.reason_detail or "")


class TestLayerZeroCompleteness(unittest.TestCase):
    """계층 0 은 목록에서 항목을 빼지 않는다 — 빼면 "없었다"가 안 보인다."""

    def test_event_type_count_lists_all_sixteen(self) -> None:
        result = kpi.event_type_count(manifest(event_type_counts={"purchase": 3}))
        self.assertEqual({item.value for item in EventType}, set(result))
        self.assertEqual(3, result["purchase"].value)
        self.assertEqual(0, result["search"].value, "0 건도 목록에 남는다")

    def test_event_type_coverage_denominator_is_the_enum_length(self) -> None:
        result = kpi.event_type_coverage(manifest(event_type_counts={"purchase": 1}))
        self.assertEqual(len(EventType), result.basis.denominator)  # type: ignore[union-attr]
        self.assertAlmostEqual(1 / len(EventType), float(result.value))  # type: ignore[arg-type]

    def test_empty_sink_reports_every_observable_unavailable(self) -> None:
        """USP-1 회귀 — 빈 Sink 에서 Observable 16개 전부가 계산 불가다."""
        result = kpi.unavailable_metric_count(cov.unavailable_metrics({}))
        self.assertEqual(len(OBSERVABLE_METRIC_SOURCES), result.value)
        self.assertEqual(len(OBSERVABLE_METRIC_SOURCES), result.basis.denominator)  # type: ignore[union-attr]


class TestMetricClassification(unittest.TestCase):
    """AC-3 — 지표 분류가 산출물에 실린다. **개수를 리터럴로 적지 않는다.**"""

    def setUp(self) -> None:
        self.classification = kpi.metric_classification()

    def test_names_are_unique(self) -> None:
        names = [m["name"] for m in self.classification["metrics"]]
        self.assertEqual(len(names), len(set(names)), "이름이 지표의 식별자다")

    def test_layer_counts_match_the_document(self) -> None:
        """계층별 개수는 `kpi-definition-v1.md` §8 과 **일치한다** (실험 계층 제외)."""
        by_layer = {
            layer: sum(counts.values())
            for layer, counts in self.classification["by_layer"].items()
        }
        self.assertEqual(12, by_layer["0"], "계층 0 수집 건전성")
        self.assertEqual(8, by_layer["1"], "계층 1 Customer KPI")
        self.assertEqual(12, by_layer["2"], "계층 2 Business KPI")

    def test_experiment_tier_is_fourteen_not_fifteen(self) -> None:
        """★ 문서 §8 은 15 라고 적었으나 §5 가 이름 붙인 것은 14 다.

        **없는 지표를 하나 만들어 숫자를 맞추지 않았다.** 문서 §8 의 산술 오류로
        보이며 W6 Timothy 항목이다 — 같은 종류의 불일치가 AI 비용 산술에도 있다.
        """
        by_layer = {
            layer: sum(counts.values())
            for layer, counts in self.classification["by_layer"].items()
        }
        self.assertEqual(14, by_layer["3"])
        self.assertEqual(46, self.classification["total"])

    def test_every_experiment_metric_is_unavailable_in_c1(self) -> None:
        for metric in self.classification["metrics"]:
            if metric["layer"] == 3:
                with self.subTest(metric=metric["name"]):
                    self.assertEqual("unavailable", metric["c1_availability"])

    def test_every_layer_zero_metric_is_computable(self) -> None:
        for metric in self.classification["metrics"]:
            if metric["layer"] == 0:
                with self.subTest(metric=metric["name"]):
                    self.assertEqual("computable", metric["c1_availability"])

    def test_reclassified_metrics_carry_their_reason(self) -> None:
        """★ 문서와 어긋나는 재분류에는 이유가 붙어 있어야 한다."""
        notes = {m["name"]: m.get("note", "") for m in self.classification["metrics"]}
        self.assertIn("signup_date", notes["cohort_retention_rate"])
        self.assertIn("#29", notes["cohort_retention_rate"])
        self.assertIn("문서 내부 모순", notes["repurchase_rate"])

    def test_unavailable_total_matches_the_document(self) -> None:
        """계산 불가 19 는 문서와 일치한다 — 두 델타가 상쇄된다.

        실험 계층 −1(문서의 유령 지표)과 계층 1 +1(`cohort_retention_rate`
        재분류)이 서로 상쇄되어 합계가 같아진다. **우연이므로 적어 둔다.**
        """
        self.assertEqual(19, self.classification["by_availability"]["unavailable"])
        self.assertEqual(6, self.classification["by_availability"]["conditional"])


if __name__ == "__main__":
    unittest.main()
