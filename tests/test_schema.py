"""이벤트 스키마 검사 (SRS DATA-003, ISO-003).

측정 계층의 계약이 스스로 모순되지 않는지, 그리고 통과해서는 안 되는 것이
스키마에 섞이지 않았는지 확인한다.

실행:
    python3 -m unittest tests.test_schema -v
"""

from __future__ import annotations

import unittest
import uuid

from src.measurement import schema as sc


def _base_record(event_type: sc.EventType, **overrides: object) -> dict[str, object]:
    """필수 필드를 채운 최소 레코드."""
    record: dict[str, object] = {
        "event_id": str(uuid.uuid4()),
        "customer_id": "C00012345",
        "timestamp": "2025-10-01T09:00:00.000+09:00",
        "event_type": event_type.value,
    }
    filler: dict[str, object] = {
        "session_id": "S-C00012345-1759276800000",
        "page_type": "home",
        "product_id": "P0042",
        "category": "신선식품",
        "quantity": 2,
        "unit_price": 8900,
        "order_id": "O20251001-000123",
        "order_amount": 47000,
        "coupon_id": "CPN-A1B2C3",
        "campaign_id": "CMP-20251001-001",
    }
    for name in sc.required_fields(event_type) - sc.CORE_FIELDS:
        record[name] = filler[name]
    record.update(overrides)
    return record


class TestEventTypes(unittest.TestCase):
    def test_sixteen_raw_event_types(self) -> None:
        """PRD §30.1 표준 16종. SRS SIM-006의 최소 8종을 상회한다."""
        self.assertEqual(16, len(list(sc.EventType)))

    def test_derived_states_are_not_raw_events(self) -> None:
        raw = {e.value for e in sc.EventType}
        derived = {e.value for e in sc.DerivedStateType}
        self.assertEqual(set(), raw & derived)
        self.assertEqual(derived, set(sc.FEATURE_FORBIDDEN_EVENT_TYPES))

    def test_every_event_type_has_rules(self) -> None:
        missing = [e.value for e in sc.EventType if e not in sc._EVENT_RULES]
        self.assertEqual([], missing, f"필수/선택 규칙 누락: {missing}")


class TestFieldSpec(unittest.TestCase):
    def test_data_003_columns_present(self) -> None:
        """SRS DATA-003이 요구한 컬럼이 모두 있는지."""
        expected = {
            "event_id", "customer_id", "timestamp", "event_type", "session_id",
            "product_id", "category", "quantity", "unit_price",
            "order_id", "order_amount", "coupon_id", "campaign_id",
            "treatment_id", "treatment_group", "experiment_id",
            "session_duration", "page_type",
            "service_version", "customer_version", "simulator_version",
            "random_seed",
        }
        self.assertEqual(expected, set(sc.FIELD_INDEX))

    def test_field_names_are_unique(self) -> None:
        names = [f.name for f in sc.EVENT_FIELDS]
        self.assertEqual(len(names), len(set(names)))

    def test_no_forbidden_field_leaked_into_schema(self) -> None:
        """Hidden Trait·τ·Potential Outcome·persona 는 이 계층을 통과할 수 없다."""
        leaked = set(sc.FIELD_INDEX) & sc.FORBIDDEN_FIELD_NAMES
        self.assertEqual(set(), leaked, f"금지 필드가 스키마에 있음: {sorted(leaked)}")

    def test_rules_only_reference_known_fields(self) -> None:
        problems: list[str] = []
        for event_type, (required, optional) in sc._EVENT_RULES.items():
            for name in required | optional:
                if name not in sc.FIELD_INDEX:
                    problems.append(f"{event_type.value}: 알 수 없는 필드 {name}")
        self.assertEqual([], problems, "\n".join(problems))

    def test_required_and_optional_do_not_overlap(self) -> None:
        overlaps: list[str] = []
        for event_type, (required, optional) in sc._EVENT_RULES.items():
            both = required & optional
            if both:
                overlaps.append(f"{event_type.value}: {sorted(both)}")
        self.assertEqual([], overlaps, "\n".join(overlaps))


class TestValidateEvent(unittest.TestCase):
    def test_minimal_records_pass_for_every_event_type(self) -> None:
        for event_type in sc.EventType:
            with self.subTest(event_type=event_type.value):
                self.assertEqual([], sc.validate_event(_base_record(event_type)))

    def test_missing_required_field_is_reported(self) -> None:
        record = _base_record(sc.EventType.PURCHASE)
        del record["order_amount"]
        problems = sc.validate_event(record)
        self.assertTrue(any("order_amount" in p for p in problems), problems)

    def test_not_applicable_field_is_reported(self) -> None:
        """push_sent 에 상품 정보가 붙으면 계약 위반이다."""
        record = _base_record(sc.EventType.PUSH_SENT, product_id="P0001")
        problems = sc.validate_event(record)
        self.assertTrue(any("product_id" in p for p in problems), problems)

    def test_hidden_trait_is_rejected(self) -> None:
        record = _base_record(sc.EventType.PURCHASE, coupon_sensitivity=0.85)
        problems = sc.validate_event(record)
        self.assertTrue(
            any("통과할 수 없는 필드" in p for p in problems), problems
        )

    def test_negative_amount_is_rejected(self) -> None:
        record = _base_record(sc.EventType.PURCHASE, order_amount=-1)
        problems = sc.validate_event(record)
        self.assertTrue(any("0 이상" in p for p in problems), problems)

    def test_unknown_event_type_is_rejected(self) -> None:
        problems = sc.validate_event({"event_type": "teleport"})
        self.assertEqual(1, len(problems))
        self.assertIn("알 수 없는 event_type", problems[0])

    def test_assignment_fields_are_optional_everywhere(self) -> None:
        record = _base_record(
            sc.EventType.PURCHASE,
            treatment_id="T3", treatment_group="treatment",
            experiment_id="EXP-20251001-01",
        )
        self.assertEqual([], sc.validate_event(record))


class TestIdentifiers(unittest.TestCase):
    def test_valid_identifiers(self) -> None:
        cases = {
            "customer_id": "C00012345",
            "session_id": "S-C00012345-1759276800000",
            "order_id": "O20251001-000123",
            "product_id": "P0042",
            "coupon_id": "CPN-A1B2C3",
            "campaign_id": "CMP-20251001-001",
            "treatment_id": "T3",
            "experiment_id": "EXP-20251001-01",
            "event_id": str(uuid.uuid4()),
        }
        for name, value in cases.items():
            with self.subTest(field=name):
                self.assertTrue(sc.check_identifier(name, value))

    def test_invalid_identifiers(self) -> None:
        cases = {
            "customer_id": "12345",
            "session_id": "C00012345",
            "order_id": "O-2025-123",
            "treatment_id": "T9",
            "event_id": "not-a-uuid",
        }
        for name, value in cases.items():
            with self.subTest(field=name):
                self.assertFalse(sc.check_identifier(name, value))


class TestObservableCoverage(unittest.TestCase):
    def test_all_sixteen_observables_are_derivable(self) -> None:
        """PRD §21 Observable 16개가 이 스키마만으로 계산 가능해야 한다."""
        self.assertEqual(16, len(sc.OBSERVABLE_METRIC_SOURCES))

    def test_sources_reference_real_event_types(self) -> None:
        known = {e.value for e in sc.EventType}
        problems: list[str] = []
        for metric, sources in sc.OBSERVABLE_METRIC_SOURCES.items():
            for source in sources:
                if source not in known:
                    problems.append(f"{metric}: 알 수 없는 이벤트 {source}")
        self.assertEqual([], problems, "\n".join(problems))

    def test_no_observable_depends_on_derived_state(self) -> None:
        """파생 상태(churn 등)에 의존하는 지표가 있으면 라벨 누수다."""
        problems = [
            f"{metric} → {source}"
            for metric, sources in sc.OBSERVABLE_METRIC_SOURCES.items()
            for source in sources
            if source in sc.FEATURE_FORBIDDEN_EVENT_TYPES
        ]
        self.assertEqual([], problems, "\n".join(problems))


if __name__ == "__main__":
    unittest.main()
