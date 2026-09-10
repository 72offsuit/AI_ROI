"""Event Sink 검사 (SRS PIPE-002, MEA-001~003).

실행:
    python3 -m unittest tests.test_sink -v
"""

from __future__ import annotations

import json
import tempfile
import unittest
import uuid
from pathlib import Path

from src.measurement import schema as sc
from src.measurement import sink as sk


def simulator_event(event_type: sc.EventType = sc.EventType.SESSION_START,
                    day: int = 1, **overrides: object) -> dict[str, object]:
    record: dict[str, object] = {
        "event_id": str(uuid.uuid4()),
        "customer_id": "C00012345",
        "timestamp": f"2025-10-{day:02d}T09:00:00.000+09:00",
        "event_type": event_type.value,
        "simulator_version": "sim-1.0",
        "random_seed": 42,
    }
    filler: dict[str, object] = {
        "session_id": "S-C00012345-1759276800000",
        "page_type": "home",
        "product_id": "P0042",
        "category": "fresh_food",
        "quantity": 1,
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


def commerce_event(*args: object, **overrides: object) -> dict[str, object]:
    """커머스 실측분 — `simulator_version` · `random_seed` 가 없다."""
    record = simulator_event(*args, **overrides)  # type: ignore[arg-type]
    record.pop("simulator_version", None)
    record.pop("random_seed", None)
    return record


class SinkTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)

    def tearDown(self) -> None:
        self._tmp.cleanup()


class TestFormatResolution(SinkTestCase):
    def test_auto_falls_back_without_pyarrow(self) -> None:
        expected = sk.SinkFormat.PARQUET if sk.parquet_available() else sk.SinkFormat.JSONL_GZ
        self.assertIs(expected, sk.resolve_format("auto"))

    def test_parquet_request_without_pyarrow_raises(self) -> None:
        if sk.parquet_available():
            self.skipTest("pyarrow 가 설치되어 있어 이 경로를 탈 수 없다")
        with self.assertRaises(RuntimeError):
            sk.resolve_format("parquet")

    def test_jsonl_and_csv_always_available(self) -> None:
        for fmt in ("jsonl", "jsonl.gz", "csv"):
            with self.subTest(fmt=fmt):
                self.assertEqual(sk.SinkFormat(fmt), sk.resolve_format(fmt))


class TestRoundTrip(SinkTestCase):
    def test_written_events_are_readable(self) -> None:
        records = [simulator_event(day=d) for d in (1, 1, 2)]
        with sk.EventSink(self.root) as s:
            result = s.write_events(records)
        self.assertEqual(3, result.accepted)
        self.assertEqual(0, result.rejected)
        self.assertTrue(result)
        recovered = list(sk.read_events(self.root))
        self.assertEqual(3, len(recovered))
        self.assertEqual(
            {r["event_id"] for r in records}, {r["event_id"] for r in recovered}
        )

    def test_partitioned_by_date(self) -> None:
        with sk.EventSink(self.root) as s:
            s.write_events([simulator_event(day=1), simulator_event(day=2)])
        dates = sorted(p.name for p in (self.root / "events").iterdir())
        self.assertEqual(["date=2025-10-01", "date=2025-10-02"], dates)

    def test_csv_round_trip(self) -> None:
        with sk.EventSink(self.root, fmt="csv") as s:
            s.write_events([simulator_event()])
        recovered = list(sk.read_events(self.root))
        self.assertEqual(1, len(recovered))
        self.assertEqual("session_start", recovered[0]["event_type"])

    def test_unparsable_timestamp_is_reported(self) -> None:
        """스키마는 통과해도 파티션 키를 못 만들면 조용히 넘기지 않는다."""
        s = sk.EventSink(self.root)
        s.write_events([simulator_event(timestamp="어제")])
        with self.assertRaises(ValueError) as caught:
            s.flush()
        self.assertIn("timestamp", str(caught.exception))


class TestSchemaEnforcement(SinkTestCase):
    def test_invalid_record_is_rejected(self) -> None:
        bad = simulator_event(sc.EventType.PURCHASE)
        del bad["order_amount"]
        with sk.EventSink(self.root) as s:
            result = s.write_events([bad])
        self.assertEqual(0, result.accepted)
        self.assertEqual(1, result.rejected)
        self.assertFalse(result)
        self.assertEqual([], list(sk.read_events(self.root)))

    def test_rejected_records_are_logged_with_reason(self) -> None:
        with sk.EventSink(self.root) as s:
            s.write_events([{"event_type": "teleport"}])
        entries = [
            json.loads(line)
            for line in (self.root / sk.REJECT_LOG_NAME).read_text(encoding="utf-8").splitlines()
        ]
        self.assertEqual(1, len(entries))
        self.assertIn("알 수 없는 event_type", entries[0]["problems"][0])

    def test_hidden_trait_never_reaches_storage(self) -> None:
        leaky = simulator_event(coupon_sensitivity=0.85)
        with sk.EventSink(self.root) as s:
            result = s.write_events([leaky])
        self.assertEqual(1, result.rejected)
        self.assertEqual([], list(sk.read_events(self.root)))

    def test_non_strict_keeps_record_but_still_reports(self) -> None:
        bad = simulator_event(sc.EventType.PURCHASE)
        del bad["order_amount"]
        with sk.EventSink(self.root, strict=False) as s:
            result = s.write_events([bad])
        self.assertEqual(1, result.accepted)
        self.assertEqual(1, result.rejected)
        self.assertEqual(1, len(list(sk.read_events(self.root))))


class TestSourceDistinction(SinkTestCase):
    """MEA-002 — 시뮬레이터 생성분과 커머스 실측분을 구분한다."""

    def test_event_source_classification(self) -> None:
        self.assertIs(sk.EventSource.SIMULATOR, sk.event_source(simulator_event()))
        self.assertIs(sk.EventSource.COMMERCE, sk.event_source(commerce_event()))

    def test_manifest_counts_both_sources(self) -> None:
        with sk.EventSink(self.root) as s:
            s.write_events([simulator_event(), simulator_event(), commerce_event()])
        manifest = json.loads((self.root / sk.MANIFEST_NAME).read_text(encoding="utf-8"))
        self.assertEqual({"simulator": 2, "commerce": 1}, manifest["sources"])


class TestPartialSourceTolerance(SinkTestCase):
    """MEA-003 — 없는 필드를 0으로 채우지 않고 결손을 기록한다."""

    def test_missing_optional_field_is_not_filled(self) -> None:
        """page_view 의 category 는 선택 필드다. 비어 있으면 비운 채 저장한다."""
        with sk.EventSink(self.root) as s:
            s.write_events([commerce_event(sc.EventType.PAGE_VIEW, category=None)])
        recovered = list(sk.read_events(self.root))
        self.assertEqual(1, len(recovered))
        self.assertIsNone(recovered[0].get("category"))
        self.assertNotIn("category", {k for k, v in recovered[0].items() if v == 0})

    def test_missing_field_is_reported_in_manifest(self) -> None:
        with sk.EventSink(self.root) as s:
            s.write_events([commerce_event(sc.EventType.SESSION_START)])
        manifest = s.manifest()
        self.assertIn("simulator_version", manifest["missing_fields"])
        self.assertEqual(0.0, manifest["field_coverage"]["simulator_version"])
        self.assertEqual(1.0, manifest["field_coverage"]["session_id"])

    def test_unavailable_metrics_are_listed(self) -> None:
        """구매 이벤트가 없으면 구매 기반 지표를 계산할 수 없다."""
        with sk.EventSink(self.root) as s:
            s.write_events([simulator_event(event_type=sc.EventType.SESSION_START)])
        unavailable = s.unavailable_metrics()
        for metric in ("purchase_count", "cumulative_revenue", "average_order_value"):
            self.assertIn(metric, unavailable)
        self.assertNotIn("visit_count", unavailable)

    def test_empty_sink_marks_every_metric_unavailable(self) -> None:
        with sk.EventSink(self.root) as s:
            pass
        self.assertEqual(
            sorted(sc.OBSERVABLE_METRIC_SOURCES), s.unavailable_metrics()
        )


class TestManifest(SinkTestCase):
    def test_manifest_records_schema_and_digest(self) -> None:
        with sk.EventSink(self.root) as s:
            s.write_events([simulator_event()])
        manifest = json.loads((self.root / sk.MANIFEST_NAME).read_text(encoding="utf-8"))
        self.assertEqual(sc.SCHEMA_VERSION, manifest["schema_version"])
        self.assertEqual(sc.TIMEZONE, manifest["timezone"])
        self.assertEqual(1, manifest["rows"])
        self.assertEqual(64, len(manifest["sha256"]))

    def test_same_input_gives_same_digest(self) -> None:
        """NFR-001 재현성 — 같은 입력이면 같은 해시."""
        records = [simulator_event(day=1), simulator_event(day=2)]
        digests = []
        for _ in range(2):
            with tempfile.TemporaryDirectory() as tmp:
                with sk.EventSink(tmp) as s:
                    s.write_events(records)
                digests.append(s.manifest()["sha256"])
        self.assertEqual(digests[0], digests[1])

    def test_chunking_creates_multiple_parts(self) -> None:
        with sk.EventSink(self.root, chunk_rows=2) as s:
            s.write_events([simulator_event() for _ in range(5)])
        parts = sorted((self.root / "events" / "date=2025-10-01").iterdir())
        self.assertGreaterEqual(len(parts), 2)
        self.assertEqual(5, len(list(sk.read_events(self.root))))


if __name__ == "__main__":
    unittest.main()
