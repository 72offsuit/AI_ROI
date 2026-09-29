"""Pins that each exchange bundle attaches only to its own source (issue #117).

The simulator now hands over order items, order-time cost, discount and shipping
through the **same** exchange contract v1 as commerce, in its own bundle
(`data/simulator_exchange/`, `manifest.source = "simulator"`). Before this, the
simulator split had no cost basis at all: `cogs` and `contribution_profit` were
`NO_COST_BASIS`, so incremental profit and AI ROI could not be computed from the
only data the experiment verdict may use (MEA-002).

What must hold, and what this file checks:

  placement  a bundle whose `manifest.source` belongs to the other source is
             refused -- otherwise commerce items would attach to simulator orders
  pairing    each bundle attaches to its own source's events only, even when both
             sources use the same `order_id` (the id formats are identical)
  end to end both sources in one `data/raw`, each with its bundle: COGS, coupon cost
             and DQ-09 are computed per source from that source's bundle
"""

from __future__ import annotations

import json
import shutil
import tempfile
import unittest
import uuid
from datetime import date
from pathlib import Path

from src.measurement import exchange as ex
from src.measurement import publish as pub
from src.measurement import validate as dq
from src.measurement.config_loader import yaml_available
from src.measurement.errors import ExchangeContractError
from src.measurement.sink import EventSink, EventSource

REPO_ROOT = Path(__file__).resolve().parent.parent
COMMERCE = Path(__file__).resolve().parent / "fixtures" / "commerce_exchange_v1"

#: 시뮬레이터 주문이 커머스 표본의 첫 주문과 **같은 order_id** 를 쓴다 — 충돌 장면이다.
COLLIDING_ORDER = json.loads(
    (COMMERCE / "exchange" / "orders.jsonl").read_text(encoding="utf-8").splitlines()[0]
)["order_id"]

# 시뮬레이터 주문 1건: P0042 × 6 = 53,400 − T3 쿠폰 7,000 = 46,400. 할인 전 합계가
# 40,000 이상이라 커머스 정책대로 일반 무료배송(정책 배송비 3,000 · 받은 배송비 0).
SIM_CUSTOMER = "C00012345"
SIM_SESSION = "S-C00012345-1759276800000"
SIM_ITEMS = [{"line_no": 1, "product_id": "P0042", "quantity": 6,
              "unit_price": 8_900, "unit_cost": 6_942}]
SIM_DISCOUNT = 7_000
SIM_AMOUNT = 6 * 8_900 - SIM_DISCOUNT
SIM_COGS = 6 * 6_942


def write_simulator_bundle(root: Path, *, source: str = "simulator") -> Path:
    root.mkdir(parents=True)
    rows = {
        "customers": [{"customer_id": SIM_CUSTOMER, "signup_date": "2025-09-01"}],
        "catalog": [{"snapshot_at": "2025-10-02T00:00:00.000+09:00", "product_id": "P0042",
                     "category": "fresh_food", "selling_price": 8_900, "unit_cost": 6_942}],
        "orders": [{"order_id": COLLIDING_ORDER, "customer_id": SIM_CUSTOMER,
                    "ordered_at": "2025-10-01T09:04:00.000+09:00", "order_amount": SIM_AMOUNT,
                    "discount": SIM_DISCOUNT, "shipping_fee": 3_000, "shipping_charged": 0}],
        "order_items": [{"order_id": COLLIDING_ORDER, **item} for item in SIM_ITEMS],
    }
    for name, items in rows.items():
        (root / f"{name}.jsonl").write_text(
            "".join(json.dumps(r) + "\n" for r in items), encoding="utf-8"
        )
    (root / "manifest.json").write_text(json.dumps({
        "contract": ex.CONTRACT_ID, "source": source, "source_commit": None,
        "generated_at": "2025-10-02T00:00:00.000+09:00", "mode": "full",
        "files": {f"{name}.jsonl": len(items) for name, items in rows.items()},
    }), encoding="utf-8")
    return root


def simulator_events() -> list[dict]:
    """계약을 지키는 시뮬레이터 구매 흐름 — 쿠폰 노출 → 결제 시작 → 쿠폰 사용 → 구매."""
    def event(event_type: str, minute: int, **fields: object) -> dict:
        return {
            "event_id": str(uuid.uuid4()), "customer_id": SIM_CUSTOMER,
            "session_id": SIM_SESSION, "event_type": event_type,
            "timestamp": f"2025-10-01T09:0{minute}:00.000+09:00",
            "simulator_version": "sim-1.0", "random_seed": 42, **fields,
        }
    coupon = {"coupon_id": "CPN-A1B2C3", "campaign_id": "CMP-20251001-001"}
    order = {"order_id": COLLIDING_ORDER, "order_amount": SIM_AMOUNT}
    return [
        event("session_start", 0, page_type="home"),
        event("coupon_exposed", 1, page_type="checkout", **coupon),
        event("checkout_start", 2, page_type="checkout", **order),
        event("coupon_use", 3, **coupon, **order),
        event("purchase", 4, page_type="complete", treatment_id="T3", **order),
    ]


def commerce_events() -> list[dict]:
    path = COMMERCE / "events.jsonl"
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


class TestPlacement(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_simulator_bundle_is_read_in_the_simulator_slot(self) -> None:
        bundle = ex.read_exchange(write_simulator_bundle(self.tmp / "s"), EventSource.SIMULATOR)
        assert bundle is not None
        self.assertIs(EventSource.SIMULATOR, bundle.source)
        self.assertEqual(SIM_AMOUNT, bundle.orders[COLLIDING_ORDER].order_amount)

    def test_simulator_bundle_in_the_commerce_slot_is_refused(self) -> None:
        with self.assertRaises(ExchangeContractError):
            ex.read_exchange(write_simulator_bundle(self.tmp / "s"), EventSource.COMMERCE)

    def test_commerce_bundle_in_the_simulator_slot_is_refused(self) -> None:
        """★ 이것을 받으면 커머스 품목이 시뮬레이터 주문에 붙는다."""
        with self.assertRaises(ExchangeContractError):
            ex.read_exchange(COMMERCE / "exchange", EventSource.SIMULATOR)

    def test_missing_source_is_refused(self) -> None:
        root = write_simulator_bundle(self.tmp / "s", source="")
        with self.assertRaises(ExchangeContractError):
            ex.read_exchange(root, EventSource.SIMULATOR)


class TestPairing(unittest.TestCase):
    """두 출처가 같은 `order_id` 를 써도 각자의 묶음만 붙는다."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        tmp = Path(self._tmp.name)
        self.sim = ex.read_exchange(write_simulator_bundle(tmp / "s"), EventSource.SIMULATOR)
        self.com = ex.read_exchange(COMMERCE / "exchange", EventSource.COMMERCE)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_each_split_gets_its_own_items(self) -> None:
        sim_orders = pub.assemble_orders(simulator_events(), self.sim)
        com_orders = pub.assemble_orders(commerce_events(), self.com)
        sim = next(o for o in sim_orders if o.order_id == COLLIDING_ORDER)
        com = next(o for o in com_orders if o.order_id == COLLIDING_ORDER)
        self.assertEqual([("P0042", 6)], [(i.product_id, i.quantity) for i in sim.items])
        self.assertNotEqual(sim.items, com.items)
        self.assertEqual(SIM_DISCOUNT, sim.discount)

    def test_dq09_compares_each_bundle_with_its_own_events(self) -> None:
        events = [*commerce_events(), *simulator_events()]
        split = pub.partition_by_source(events)
        report = dq.build_report(
            events, exchanges=[(self.com, split.commerce), (self.sim, split.simulator)],
        )
        check = next(c for c in report["checks"] if c["id"] == "DQ-09")
        self.assertEqual("pass", check["status"], check)
        self.assertEqual(len(self.com.orders) + len(self.sim.orders), check["examined_rows"])

    def test_violation_names_its_source(self) -> None:
        events = [
            {**e, "order_amount": e["order_amount"] + 1}
            if e["event_type"] == "purchase" else e
            for e in simulator_events()
        ]
        report = dq.build_report(events, exchanges=[(self.sim, events)])
        check = next(c for c in report["checks"] if c["id"] == "DQ-09")
        self.assertEqual("fail", check["status"])
        self.assertTrue(check["samples"][0]["detail"].startswith("[시뮬레이터]"))


@unittest.skipUnless(yaml_available(), "BLOCKED: PyYAML 미설치 — publish() 종단 경로를 검증하지 않았다")
class TestBothSourcesEndToEnd(unittest.TestCase):
    """★★ 두 출처가 한 `data/raw` 에 섞이고 각자 묶음이 기본 위치에 있다."""

    @classmethod
    def setUpClass(cls) -> None:
        cls._tmp = tempfile.TemporaryDirectory()
        root = Path(cls._tmp.name)
        shutil.copytree(COMMERCE / "exchange", root / "commerce")
        write_simulator_bundle(root / "simulator_exchange")
        with EventSink(root / "raw") as sink:
            result = sink.write_events([*commerce_events(), *simulator_events()])
        cls.rejected = result.rejected
        cls.outcome = pub.publish(
            source_root=root / "raw", output_root=root / "results",
            config_path=REPO_ROOT / "config/economic_config.yaml",
            index_date=date(2026, 9, 28),
        )
        read = lambda name: json.loads(  # noqa: E731
            (root / "results" / pub.artifact_relative(name)).read_text(encoding="utf-8")
        )
        cls.kpi, cls.quality = read("kpi_report"), read("data_quality_report")
        cls.commerce = json.loads((COMMERCE / "contribution.json").read_text(encoding="utf-8"))

    @classmethod
    def tearDownClass(cls) -> None:
        cls._tmp.cleanup()

    def metric(self, name: str, source: str) -> dict:
        entry = next(m for m in self.kpi["metrics"] if m["name"] == name)
        return entry["value"]["by_source"][source]

    def test_published_within_contract(self) -> None:
        self.assertEqual(0, self.rejected)
        self.assertEqual("ok", self.outcome.publish_result, self.outcome.artifacts)

    def test_simulator_cogs_is_computed_from_its_own_bundle(self) -> None:
        """#117 이전에는 여기가 `unavailable · NO_COST_BASIS` 였다."""
        cogs = self.metric("cogs", "simulator")
        self.assertEqual("ok", cogs["status"], cogs)
        self.assertEqual(SIM_COGS, cogs["value"])

    def test_commerce_cogs_is_unchanged_by_the_collision(self) -> None:
        self.assertEqual(self.commerce["cogsKrw"], self.metric("cogs", "commerce")["value"])

    def test_simulator_coupon_cost_is_the_observed_discount(self) -> None:
        coupon = self.metric("coupon_cost", "simulator")
        self.assertEqual("ok", coupon["status"], coupon)
        self.assertEqual(SIM_DISCOUNT, coupon["value"])

    def test_simulator_contribution_profit_is_computed(self) -> None:
        self.assertEqual("ok", self.metric("contribution_profit", "simulator")["status"])

    def test_quality_checks_run_on_both_sources(self) -> None:
        rows = {c["id"]: c for c in self.quality["checks"]}
        for check_id in ("DQ-02", "DQ-03", "DQ-05", "DQ-09"):
            with self.subTest(check=check_id):
                self.assertEqual("pass", rows[check_id]["status"], rows[check_id])
        commerce_orders = len(
            (COMMERCE / "exchange" / "orders.jsonl").read_text(encoding="utf-8").splitlines()
        )
        self.assertEqual(
            commerce_orders + 1, rows["DQ-09"]["examined_rows"],
            "커머스 주문 전부 + 시뮬레이터 주문 1건",
        )
