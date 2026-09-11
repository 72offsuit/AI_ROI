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


class TestRewriteSameRoot(SinkTestCase):
    """D1-1 — a second Sink over the same root must append, not overwrite.

    The simulator writes by calling advance() repeatedly, each time with a fresh
    EventSink over the same root (SIM-012 split invariance). Part numbering therefore
    cannot live only in instance state: it has to be recovered from the directory.
    """

    def test_second_run_does_not_overwrite_the_first(self) -> None:
        first = [simulator_event(day=1) for _ in range(2)]
        second = [simulator_event(day=1) for _ in range(3)]
        with sk.EventSink(self.root) as s:
            s.write_events(first)
        with sk.EventSink(self.root) as s:
            s.write_events(second)
        self.assertEqual(5, len(list(sk.read_events(self.root))))

    def test_second_run_creates_a_new_part_file(self) -> None:
        for _ in range(2):
            with sk.EventSink(self.root) as s:
                s.write_events([simulator_event(day=1)])
        parts = sorted(p.name for p in (self.root / "events" / "date=2025-10-01").iterdir())
        self.assertEqual(2, len(parts), parts)
        self.assertTrue(parts[0].startswith("part-0000"), parts)
        self.assertTrue(parts[1].startswith("part-0001"), parts)

    def test_part_numbering_uses_max_not_count(self) -> None:
        """A deleted middle part must not make the next write reuse a live number.

        Counting files would yield 1 here and clobber part-0001; taking max+1 yields 2.
        """
        with sk.EventSink(self.root, chunk_rows=1) as s:
            s.write_events([simulator_event(day=1) for _ in range(2)])
        directory = self.root / "events" / "date=2025-10-01"
        next(iter(sorted(directory.iterdir()))).unlink()  # remove part-0000
        with sk.EventSink(self.root) as s:
            s.write_events([simulator_event(day=1)])
        names = sorted(p.name.split(".", 1)[0] for p in directory.iterdir())
        self.assertEqual(["part-0001", "part-0002"], names)


class TestTimezonePolicy(SinkTestCase):
    """D1-3 — policy ⑵+b: accept any offset, normalise to KST on write.

    Commerce records in UTC (Ecommerce_Service orders.ts), so rejecting non-KST offsets
    would collide with MEA-003 (tolerate partial sources). Instead both the stored
    timestamp and the partition date come from one parse, so they cannot disagree.
    """

    def test_utc_input_partitions_by_kst_date(self) -> None:
        with sk.EventSink(self.root) as s:
            s.write_events([simulator_event(timestamp="2025-10-01T23:30:00.000Z")])
        dates = sorted(p.name for p in (self.root / "events").iterdir())
        self.assertEqual(["date=2025-10-02"], dates)

    def test_utc_input_is_stored_as_kst(self) -> None:
        """Option b — the persisted value is rewritten, not just the partition path.

        Option a (keep the raw UTC string) would make DQ-06 "every timestamp is KST"
        fail against our own output, and re-deriving the date on read would give 10-01
        while the partition says 10-02.
        """
        with sk.EventSink(self.root) as s:
            s.write_events([simulator_event(timestamp="2025-10-01T23:30:00.000Z")])
        recovered = list(sk.read_events(self.root))
        self.assertEqual("2025-10-02T08:30:00.000+09:00", recovered[0]["timestamp"])

    def test_kst_input_is_unchanged(self) -> None:
        with sk.EventSink(self.root) as s:
            s.write_events([simulator_event(timestamp="2025-10-01T09:00:00.000+09:00")])
        recovered = list(sk.read_events(self.root))
        self.assertEqual("2025-10-01T09:00:00.000+09:00", recovered[0]["timestamp"])

    def test_naive_timestamp_is_rejected(self) -> None:
        """No offset means the instant is unknown; guessing one would invent data."""
        with sk.EventSink(self.root) as s:
            result = s.write_events([simulator_event(timestamp="2025-10-01T23:30:00")])
        self.assertEqual(1, result.rejected)
        self.assertEqual([], list(sk.read_events(self.root)))

    def test_manifest_created_at_is_kst(self) -> None:
        with sk.EventSink(self.root) as s:
            s.write_events([simulator_event()])
        manifest = json.loads((self.root / sk.MANIFEST_NAME).read_text(encoding="utf-8"))
        self.assertTrue(
            manifest["created_at"].endswith("+09:00"), manifest["created_at"]
        )


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


class TestTolerantModeSurvival(SinkTestCase):
    """D1-2 — strict=False must not crash, whatever the record looks like.

    MEA-003 requires that an incomplete source cannot kill ingestion. Previously
    _observe() called EventType(record["event_type"]) unconditionally, so a bad or
    absent event_type raised out of write_events() and the whole batch was lost.
    """

    def test_non_strict_survives_unknown_event_type(self) -> None:
        record = simulator_event(sc.EventType.SESSION_START)
        record["event_type"] = "teleport"
        with sk.EventSink(self.root, strict=False) as s:
            result = s.write_events([record])
        self.assertEqual(1, result.rejected)

    def test_non_strict_survives_missing_event_type(self) -> None:
        record = simulator_event(sc.EventType.SESSION_START)
        del record["event_type"]
        with sk.EventSink(self.root, strict=False) as s:
            result = s.write_events([record])
        self.assertEqual(1, result.rejected)

    def test_unobservable_records_are_logged_with_reason(self) -> None:
        """Rejected is not the same as forgotten — the reason has to survive."""
        broken = simulator_event(sc.EventType.SESSION_START)
        broken["event_type"] = "teleport"
        missing = simulator_event(sc.EventType.SESSION_START)
        del missing["event_type"]
        with sk.EventSink(self.root, strict=False) as s:
            s.write_events([broken, missing])
        entries = [
            json.loads(line)
            for line in (self.root / sk.REJECT_LOG_NAME)
            .read_text(encoding="utf-8")
            .splitlines()
        ]
        self.assertEqual(2, len(entries))
        for entry in entries:
            self.assertTrue(entry["problems"], entry)
            self.assertIn("event_type", entry["problems"][0])

    def test_unobservable_records_are_not_stored(self) -> None:
        """strict=False means "ingestion survives", not "store invalid data".

        A record with no valid event_type has no coverage row and no requirement
        matrix, so there is nothing meaningful to store or report about it.
        """
        record = simulator_event(sc.EventType.SESSION_START)
        record["event_type"] = "teleport"
        with sk.EventSink(self.root, strict=False) as s:
            s.write_events([record])
        self.assertEqual([], list(sk.read_events(self.root)))


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


@unittest.skipUnless(
    sk.parquet_available(),
    "BLOCKED: pyarrow 미설치 — Parquet 경로를 검증하지 않았다 (DQ-17)",
)
class TestParquetPath(SinkTestCase):
    """B-1 해소 — Parquet 저장 경로를 실제로 실행한다 (M-05 AC-4).

    기준선 46건은 전부 `jsonl.gz` 경로만 밟았다. 두 형식이 다른 결과를 낸다면
    **`jsonl.gz` 로 확인한 46건은 Parquet 환경에서 보증되지 않는다.**

    ★ skip 은 통과가 아니다. 이 클래스가 skip 되면 `DQ-17` 이 여전히
    `blocked` 이고, 그 사실이 게시물과 `docs/gate1_checklist.md` 에 남는다.
    """

    def test_parquet_roundtrip(self) -> None:
        """22 컬럼이 왕복 후 값·타입 보존. ★ `None` 이 `0`·`""` 으로 바뀌지 않는다.

        `_write_parquet` 은 `[row.get(name) for row in rows]` 로 컬럼을 만든다.
        어떤 컬럼이 전부 `None` 이면 pyarrow 가 타입을 추론할 수 없어 `null` 타입
        컬럼이 되는데, 그때 값이 보존되는지가 이 테스트의 요점이다.

        **결손 은폐가 저장 계층에서 일어날 수 있는 자리다** — `None` 이 `0` 이나
        `""` 으로 바뀌면 그것이 곧 0 채우기고, 계산층이 아무리 정직해도 소용없다.
        """
        record = commerce_event(sc.EventType.PAGE_VIEW, category=None)
        with sk.EventSink(self.root, fmt="parquet") as s:
            result = s.write_events([record])
        self.assertEqual(1, result.accepted)

        recovered = list(sk.read_events(self.root))
        self.assertEqual(1, len(recovered))
        row = recovered[0]
        # 전부 None 인 컬럼(simulator_version·random_seed·category)이 살아 있어야 한다.
        for name in ("simulator_version", "random_seed", "category"):
            with self.subTest(column=name):
                self.assertIsNone(row[name], f"{name} 의 None 이 보존되지 않았다")
                self.assertNotEqual(0, row[name])
                self.assertNotEqual("", row[name])
        # 값이 있는 컬럼은 값과 타입이 함께 보존되어야 한다.
        self.assertEqual(record["event_id"], row["event_id"])
        self.assertEqual("page_view", row["event_type"])
        self.assertIsInstance(row["event_id"], str)

    def test_parquet_preserves_all_22_columns(self) -> None:
        """DATA-003 22 컬럼이 하나도 사라지지 않는다."""
        with sk.EventSink(self.root, fmt="parquet") as s:
            s.write_events([simulator_event()])
        recovered = list(sk.read_events(self.root))
        self.assertEqual(set(sc.FIELD_INDEX), set(recovered[0]))
        self.assertEqual(22, len(recovered[0]))

    def test_parquet_digest_reproducible(self) -> None:
        """NFR-001 — 같은 입력 2회 → 같은 SHA-256.

        이것이 성립하지 않으면 `events.parquet` 해시 대조가 무의미하고,
        `requirements.txt` 가 pyarrow 를 `==` 로 고정하는 이유가 사라진다.
        """
        records = [simulator_event(day=1), simulator_event(day=2)]
        digests = []
        for _ in range(2):
            with tempfile.TemporaryDirectory() as tmp:
                with sk.EventSink(tmp, fmt="parquet") as s:
                    s.write_events(records)
                digests.append(s.manifest()["sha256"])
        self.assertEqual(digests[0], digests[1])

    def test_format_auto_selects_parquet(self) -> None:
        self.assertIs(sk.SinkFormat.PARQUET, sk.resolve_format("auto"))

    def _read_both_formats(
        self, records: list[dict[str, object]]
    ) -> dict[str, list[dict[str, object]]]:
        by_format: dict[str, list[dict[str, object]]] = {}
        for fmt in ("jsonl.gz", "parquet"):
            with tempfile.TemporaryDirectory() as tmp:
                with sk.EventSink(tmp, fmt=fmt) as s:
                    s.write_events(records)
                by_format[fmt] = sorted(
                    sk.read_events(tmp), key=lambda r: str(r["event_id"])
                )
        return by_format

    def test_jsonl_and_parquet_agree(self) -> None:
        """★ 같은 레코드를 두 형식으로 쓰고 되읽어 **같은 값**을 얻는다.

        M-05 의 핵심 테스트다. 두 형식이 값에서 갈라지면 형식에 따라 다른 값이
        게시되고, 그것은 환경에 따라 다른 진실이 만들어진다는 뜻이다.

        ★ **"같음"의 기준을 22 컬럼 전체의 값으로 잡는다** — dict 상등이 아니다.
        두 형식은 **없는 필드의 표현이 구조적으로 다르다**(아래
        `test_absent_field_representation_differs_by_format` 가 그것을 명시한다).
        시스템이 실제로 의존하는 불변식은 `record.get(name) is None` 이고, 그
        기준에서 둘은 같아야 한다. 그래서 여기서도 그 기준으로 비교한다.

        이 테스트를 처음 dict 상등으로 썼을 때 실패했고, **실패가 옳았다** — 차이가
        실재했다. 확인해 보니 값 불일치는 0 건이고 구조 차이만 있었다. 그래서
        비교 기준을 시스템의 접근 방식에 맞추고, 구조 차이는 숨기지 않고 별도
        테스트로 드러냈다.
        """
        records = [
            simulator_event(day=1),
            commerce_event(sc.EventType.PAGE_VIEW, day=2, category=None),
            simulator_event(sc.EventType.PURCHASE, day=2),
        ]
        by_format = self._read_both_formats(records)
        self.assertEqual(
            len(by_format["jsonl.gz"]), len(by_format["parquet"]), "행 수가 다르다"
        )
        for jsonl_row, parquet_row in zip(
            by_format["jsonl.gz"], by_format["parquet"]
        ):
            for name in sc.FIELD_INDEX:
                with self.subTest(event=jsonl_row["event_id"], column=name):
                    self.assertEqual(
                        jsonl_row.get(name), parquet_row.get(name),
                        f"{name} 의 값이 형식에 따라 다르다 — jsonl.gz 로 확인한 "
                        "기준선이 Parquet 환경에서 보증되지 않는다",
                    )

    def test_absent_field_representation_differs_by_format(self) -> None:
        """두 형식의 **구조** 차이를 명시한다 — 숨기면 나중에 결함으로 오해된다.

            jsonl.gz  없는 필드를 **키째로 생략**한다      (7 키)
            parquet   없는 필드를 **명시적 null 로** 담는다 (22 키)

        Parquet 은 컬럼 지향이라 스키마가 고정이고, 행마다 컬럼을 빼는 표현이
        없다. 둘 다 "이 필드는 없다"의 올바른 표현이며 `.get(name) is None` 에서
        구분되지 않는다.

        ★ 그러나 **키 개수를 세는 검사는 형식에 따라 다른 답을 얻는다.** 결손
        집계를 `len(row)` 로 하면 Parquet 환경에서 조용히 틀린다 — 결손은
        `sc.FIELD_INDEX` 를 순회해 `.get()` 으로 판정해야 한다.

        jsonl.gz 를 22 컬럼으로 맞추지 않은 이유: 레코드마다 null 키 15 개가
        늘어 압축 후 크기가 눈에 띄게 커지고(벤치 바이트 게이트가 ±1% 다), 얻는
        의미가 없다.
        """
        records = [commerce_event(sc.EventType.PAGE_VIEW, category=None)]
        by_format = self._read_both_formats(records)
        jsonl_row, parquet_row = by_format["jsonl.gz"][0], by_format["parquet"][0]

        self.assertLess(len(jsonl_row), len(parquet_row))
        self.assertEqual(22, len(parquet_row))
        # 생략된 키는 전부 Parquet 에서 null 이다 — 값이 생기지 않았다.
        for name in set(parquet_row) - set(jsonl_row):
            with self.subTest(column=name):
                self.assertIsNone(parquet_row[name])
        # ★ 공유 키에서는 값 불일치가 0 건이어야 한다. 그것이 진짜 불변식이다.
        self.assertEqual(
            {}, {
                name: (jsonl_row[name], parquet_row[name])
                for name in set(jsonl_row) & set(parquet_row)
                if jsonl_row[name] != parquet_row[name]
            },
        )

    def test_manifest_records_the_format_used(self) -> None:
        """형식이 환경에 따라 갈리므로, 무엇으로 썼는지가 기록되어야 한다.

        재현성 대조는 **같은 형식끼리만** 성립한다. 개발자 A 가 Parquet, B 가
        `jsonl.gz` 를 만들면 해시가 다른 것이 정상이고, 그 차이를 결함으로 읽지
        않으려면 형식이 산출물에 남아 있어야 한다.
        """
        with sk.EventSink(self.root, fmt="parquet") as s:
            s.write_events([simulator_event()])
        manifest = json.loads((self.root / sk.MANIFEST_NAME).read_text(encoding="utf-8"))
        self.assertEqual("parquet", manifest["format"])


if __name__ == "__main__":
    unittest.main()
