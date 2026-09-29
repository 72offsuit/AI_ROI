"""Pins DQ-02 · DQ-03 · DQ-05 against the commerce exchange roster (issue #110).

The exchange bundle (`data/commerce/`) carries the commerce **roster** -- customers
with their signup date, and the catalog. Three data_spec §9 checks were `not_run`
because no roster existed; now they run when the bundle is there.

Decisions (DR-110):

  scope     only events the roster is responsible for -- the commerce split, chosen
            by `publish.py`. The roster is commerce-only; comparing simulator events
            against it would make every one of them an orphan
  snapshot  events after `manifest.generated_at` are not compared and the count is
            carried in `reason_detail` -- the roster never promised to know them
  DQ-05     date granularity (signup_date is a KST date). An event earlier on the
            signup day is not caught; the scope text says so
  DQ-02     runs; the loader already refuses a bundle with a duplicate order_id,
            so a loaded roster passes with the order count examined
"""

from __future__ import annotations

import json
import unittest
from pathlib import Path

from src.measurement import exchange as ex
from src.measurement import publish as pub
from src.measurement import validate as dq
from src.measurement.sink import EventSource

SAMPLE = Path(__file__).resolve().parent / "fixtures" / "commerce_exchange_v1"

def read_commerce(root: Path) -> ex.ExchangeBundle | None:
    return ex.read_exchange(root, EventSource.COMMERCE)



def sample_events() -> list[dict]:
    return [
        json.loads(line)
        for line in (SAMPLE / "events.jsonl").read_text(encoding="utf-8").splitlines()
    ]


def check(report: dict, check_id: str) -> dict:
    found = [c for c in report["checks"] if c["id"] == check_id]
    assert len(found) == 1, f"{check_id} 를 찾지 못했다"
    return found[0]


class RosterTest(unittest.TestCase):
    def setUp(self) -> None:
        exchange = read_commerce(SAMPLE / "exchange")
        assert exchange is not None
        self.exchange = exchange
        self.events = sample_events()

    def report(self, events: list[dict], scope: list[dict] | None = None) -> dict:
        return dq.build_report(
            events, exchanges=[(self.exchange, events if scope is None else scope)],
        )


class TestWithoutTheRoster(unittest.TestCase):
    def test_no_bundle_means_not_run_with_a_true_reason(self) -> None:
        """★ 사유가 사실이어야 한다 — "테이블 미구현"이 아니라 "교환 파일이 없다"."""
        report = dq.build_report(sample_events())
        for check_id in ("DQ-02", "DQ-03", "DQ-05"):
            with self.subTest(check=check_id):
                row = check(report, check_id)
                self.assertEqual("not_run", row["status"])
                self.assertEqual("PRECONDITION_MISSING", row["reason_code"])
                self.assertIn("교환 파일", row["reason_detail"])
                self.assertNotIn("미구현", row["reason_detail"])



class TestTheRealSample(RosterTest):
    def test_all_three_pass(self) -> None:
        report = self.report(self.events)
        self.assertEqual(
            {"status": "pass", "examined_rows": len(self.exchange.orders), "violations": 0},
            {k: check(report, "DQ-02")[k] for k in ("status", "examined_rows", "violations")},
        )
        for check_id in ("DQ-03", "DQ-05"):
            with self.subTest(check=check_id):
                row = check(report, check_id)
                self.assertEqual("pass", row["status"], row)
                self.assertGreater(row["examined_rows"], 0)

    def test_publish_scopes_to_the_commerce_split(self) -> None:
        """★ 시뮬레이터 이벤트는 명부가 없어도 고아가 아니다 — 범위 밖이다."""
        simulator = {
            **self.events[0], "event_id": "00000000-0000-4000-8000-000000000001",
            "customer_id": "C99999999", "simulator_version": "sim-1.0", "random_seed": 42,
        }
        events = [*self.events, simulator]
        split = pub.partition_by_source(events)
        self.assertIn(simulator, split.simulator)
        report = dq.build_report(events, exchanges=[(self.exchange, split.commerce)])
        self.assertEqual("pass", check(report, "DQ-03")["status"])


class TestOrphans(RosterTest):
    def test_unknown_customer_is_an_orphan(self) -> None:
        events = [{**self.events[0], "customer_id": "C99999999"}, *self.events[1:]]
        row = check(self.report(events), "DQ-03")
        self.assertEqual("fail", row["status"])
        self.assertEqual(1, row["violations"])
        self.assertIn("C99999999", row["samples"][0]["detail"])

    def product_event(self, product_id: str, suffix: str) -> dict:
        """표본은 구매 흐름만 담아 상품 이벤트가 없다 — 명부의 상품 쪽을 직접 태운다."""
        return {
            **self.events[0], "event_id": f"00000000-0000-4000-8000-00000000000{suffix}",
            "event_type": "product_view", "page_type": "detail",
            "product_id": product_id, "category": "fresh_food", "unit_price": 3900,
        }

    def test_known_product_passes(self) -> None:
        """★ 거짓 양성 — 명부에 있는 상품이 고아로 잡히면 결합 규칙이 틀린 것이다."""
        known = sorted(self.exchange.product_ids)[0]
        row = check(self.report([*self.events, self.product_event(known, "1")]), "DQ-03")
        self.assertEqual("pass", row["status"], row)

    def test_unknown_product_is_an_orphan(self) -> None:
        row = check(self.report([*self.events, self.product_event("P9999", "2")]), "DQ-03")
        self.assertEqual("fail", row["status"])
        self.assertEqual(1, row["violations"])
        self.assertIn("P9999", row["samples"][0]["detail"])

    def test_event_after_the_snapshot_is_skipped_and_counted(self) -> None:
        """★ 스냅샷 이후 고객은 명부가 모른다. 위반도 통과도 아니고, 건수를 남긴다."""
        later = {
            **self.events[0], "customer_id": "C99999999",
            "timestamp": "2099-01-01T00:00:00.000+09:00",
        }
        row = check(self.report([*self.events, later]), "DQ-03")
        self.assertEqual("pass", row["status"], row)
        self.assertEqual(len(self.events), row["examined_rows"])
        self.assertIn("이후 이벤트 1건", row["reason_detail"])

    def test_only_later_events_is_vacuous_not_pass(self) -> None:
        later = {
            **self.events[0], "customer_id": "C99999999",
            "timestamp": "2099-01-01T00:00:00.000+09:00",
        }
        row = check(self.report([later]), "DQ-03")
        self.assertEqual("vacuous", row["status"])
        self.assertIn("이후 이벤트 1건", row["reason_detail"])


class TestBeforeSignup(RosterTest):
    def signup_of(self, event: dict) -> str:
        return self.exchange.signup_dates[event["customer_id"]].isoformat()

    def test_event_on_an_earlier_day_is_a_violation(self) -> None:
        first = self.events[0]
        earlier = f"{int(self.signup_of(first)[:4]) - 1}{self.signup_of(first)[4:]}T12:00:00.000+09:00"
        events = [{**first, "timestamp": earlier}, *self.events[1:]]
        row = check(self.report(events), "DQ-05")
        self.assertEqual("fail", row["status"])
        self.assertIn(first["customer_id"], row["samples"][0]["detail"])

    def test_earlier_on_the_signup_day_is_not_caught(self) -> None:
        """★ 한계를 고정한다 — 가입일이 날짜 단위라 당일 00:00:01 이벤트도 통과한다.

        이 테스트가 실패한다면 계약이 가입 시각을 싣게 된 것이다. 그때는 scope
        문구와 DR-110 을 함께 고친다.
        """
        first = self.events[0]
        same_day = f"{self.signup_of(first)}T00:00:01.000+09:00"
        events = [{**first, "timestamp": same_day}, *self.events[1:]]
        row = check(self.report(events), "DQ-05")
        self.assertEqual("pass", row["status"])
        self.assertIn("가입 당일", row["scope"])

    def test_utc_timestamps_are_compared_as_kst_dates(self) -> None:
        """UTC 15:00 전날은 KST 로 가입일 당일 00:00 이다 — 위반이 아니다."""
        first = self.events[0]
        signup = self.exchange.signup_dates[first["customer_id"]]
        from datetime import timedelta
        utc_prev = (signup - timedelta(days=1)).isoformat() + "T15:00:00.000+00:00"
        events = [{**first, "timestamp": utc_prev}, *self.events[1:]]
        self.assertEqual("pass", check(self.report(events), "DQ-05")["status"])


class TestRosterIntegrity(unittest.TestCase):
    """명부 자체의 중복은 로더가 막는다 — 중복 명부로 대조하면 결과가 무의미하다."""

    def _copy(self, tmp: Path) -> Path:
        import shutil
        return Path(shutil.copytree(SAMPLE / "exchange", tmp / "commerce"))

    def _rewrite(self, root: Path, name: str, rows: list[dict]) -> None:
        (root / f"{name}.jsonl").write_text(
            "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8"
        )
        manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
        manifest["files"][f"{name}.jsonl"] = len(rows)
        (root / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")

    def _rows(self, name: str) -> list[dict]:
        text = (SAMPLE / "exchange" / f"{name}.jsonl").read_text(encoding="utf-8")
        return [json.loads(line) for line in text.splitlines()]

    def test_duplicate_customer_is_refused(self) -> None:
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            root = self._copy(Path(tmp))
            rows = self._rows("customers")
            self._rewrite(root, "customers", [*rows, rows[0]])
            with self.assertRaises(ex.ExchangeContractError):
                read_commerce(root)

    def test_duplicate_product_is_refused(self) -> None:
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            root = self._copy(Path(tmp))
            rows = self._rows("catalog")
            self._rewrite(root, "catalog", [*rows, rows[0]])
            with self.assertRaises(ex.ExchangeContractError):
                read_commerce(root)

    def test_missing_generated_at_is_refused(self) -> None:
        """명부가 언제까지를 책임지는지 모르면 스냅샷 이후를 가를 수 없다."""
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            root = self._copy(Path(tmp))
            manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
            del manifest["generated_at"]
            (root / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
            with self.assertRaises(ex.ExchangeContractError):
                read_commerce(root)
