"""Pins the commerce exchange contract v1 and what we do with and without it (issue #100).

`purchase` is one row per order, and `product_id`/`quantity`/`unit_price` are
`NOT_APPLICABLE` on it -- `validate_event()` refuses them. So an order's line items
cannot be reconstructed from events. The commerce exchange bundle (`data/commerce/`,
produced by `Ecommerce_Service` `npm run exchange:export`) carries the items, the
order-time cost snapshot, the discount and the shipping amounts.

What this file covers:

  schemas    the four schemas are valid draft 2020-12, **refuse counterexamples**,
             use the event id formats, and agree with the stdlib loader's field table
  loader     absent -> `None` (not an empty bundle); malformed -> the whole bundle
             is refused, because reading part of it makes a partial sum look whole
  DQ-09      `not_run` without the bundle; with it, every exchange order must have
             items, satisfy the amount equation, and match its purchase event
  end to end the real commerce sample (tests/fixtures/commerce_exchange_v1/) goes
             through `EventSink` and `publish()` and reproduces the commerce side's
             own COGS and contribution

★ The distinction `not_run` vs violation still matters. "we did not compare" and
  "we compared and it was fine" must never collapse into one value.
"""

from __future__ import annotations

import json
import shutil
import tempfile
import unittest
from datetime import date
from pathlib import Path

from src.measurement import economics as ec
from src.measurement import exchange as ex
from src.measurement import publish as pub
from src.measurement import schema as sc
from src.measurement import validate as dq
from src.measurement.config_loader import yaml_available
from src.measurement.errors import ExchangeContractError
from src.measurement.kpi import MetricStatus
from src.measurement.sink import EventSink
from tests.test_economics import fixture_config

REPO_ROOT = Path(__file__).resolve().parent.parent
CONTRACT = REPO_ROOT / "docs" / "contracts" / "commerce-exchange" / "v1"
SAMPLE = Path(__file__).resolve().parent / "fixtures" / "commerce_exchange_v1"
SCHEMAS = ("customers", "catalog", "orders", "order_items")


def _jsonschema_available() -> bool:
    try:
        import jsonschema  # noqa: F401
    except ImportError:
        return False
    return True


NEEDS_JSONSCHEMA = (
    "BLOCKED: jsonschema 미설치 — 반례를 실제 validator 로 태우지 않았다. "
    "`pip install -r requirements-dev.txt`"
)
NEEDS_YAML = (
    "BLOCKED: PyYAML 미설치 — publish() 가 경제 규칙 config 를 읽어야 해서 "
    "종단 경로를 검증하지 않았다"
)


def load(name: str) -> dict:
    return json.loads((CONTRACT / f"{name}.schema.json").read_text(encoding="utf-8"))


def sample_rows(name: str) -> list[dict]:
    path = SAMPLE / "exchange" / f"{name}.jsonl"
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def copy_sample(target: Path) -> Path:
    shutil.copytree(SAMPLE / "exchange", target)
    return target


def rewrite(root: Path, name: str, rows: list[dict], *, keep_manifest: bool = False) -> None:
    (root / f"{name}.jsonl").write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows),
        encoding="utf-8",
    )
    if keep_manifest:
        return
    manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
    manifest["files"][f"{name}.jsonl"] = len(rows)
    (root / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")


class TempDirTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)

    def tearDown(self) -> None:
        self._tmp.cleanup()


# ── 스키마 ──────────────────────────────────────────────────────────────────

class TestTheContractIsAgreed(unittest.TestCase):
    def test_all_four_schemas_and_the_readme(self) -> None:
        self.assertTrue(CONTRACT.is_dir(), f"{CONTRACT} 가 없다")
        self.assertTrue((CONTRACT / "README.md").is_file())
        for name in SCHEMAS:
            with self.subTest(schema=name):
                self.assertTrue((CONTRACT / f"{name}.schema.json").is_file())

    def test_every_schema_names_the_agreement_and_the_producer(self) -> None:
        """파일 하나만 열어 본 사람도 합의 근거와 생산자를 알 수 있어야 한다."""
        for name in SCHEMAS:
            with self.subTest(schema=name):
                comment = load(name).get("$comment", "")
                self.assertIn("합의", comment)
                self.assertIn("#100", comment)
                self.assertIn("exchange:export", comment)
                self.assertNotIn("초안", comment)
                self.assertIn("/v1/", load(name)["$id"])

    def test_no_schema_accepts_unknown_fields(self) -> None:
        for name in SCHEMAS:
            with self.subTest(schema=name):
                self.assertIs(False, load(name).get("additionalProperties"))

    def test_loader_field_table_matches_the_schemas(self) -> None:
        """★ 런타임 로더는 jsonschema 없이 돈다. 필드 표가 두 벌이면 갈라진다.

        스키마의 `required` 가 로더의 필수 필드이고, 나머지 `properties` 가
        로더의 선택 필드여야 한다.
        """
        for name in SCHEMAS:
            with self.subTest(schema=name):
                schema = load(name)
                self.assertEqual(set(schema["required"]), set(ex.FIELDS[name]))
                self.assertEqual(
                    set(schema["properties"]) - set(schema["required"]),
                    set(ex._OPTIONAL.get(name, {})),
                )


class TestIdFormatsMatchTheEventContract(unittest.TestCase):
    """★ 결합이 실제로 성립하려면 형식이 같아야 한다 — `schema.py` 가 GATE 1 정본이다."""

    def test_order_id_pattern_is_the_event_pattern(self) -> None:
        for name in ("orders", "order_items"):
            with self.subTest(schema=name):
                self.assertEqual(
                    sc.IDENTIFIER_PATTERNS["order_id"],
                    load(name)["properties"]["order_id"]["pattern"],
                )

    def test_product_id_pattern_is_the_event_pattern(self) -> None:
        for name in ("catalog", "order_items"):
            with self.subTest(schema=name):
                self.assertEqual(
                    sc.IDENTIFIER_PATTERNS["product_id"],
                    load(name)["properties"]["product_id"]["pattern"],
                )

    def test_customer_id_pattern_is_the_event_pattern(self) -> None:
        for name in ("orders", "customers"):
            with self.subTest(schema=name):
                self.assertEqual(
                    sc.IDENTIFIER_PATTERNS["customer_id"],
                    load(name)["properties"]["customer_id"]["pattern"],
                )


class TestRequiredAmounts(unittest.TestCase):
    def test_discount_and_shipping_are_required(self) -> None:
        """`discount` 없이는 `DQ-09` 가 성립하지 않고, 배송비 둘 없이는 배송보조가
        규칙 유도(A-SHIPPING)로 돌아간다."""
        required = load("orders")["required"]
        for field in ("discount", "shipping_fee", "shipping_charged"):
            with self.subTest(field=field):
                self.assertIn(field, required)

    def test_unit_cost_is_required_but_nullable(self) -> None:
        """키 누락은 위반이고 `null` 은 "원가를 모른다"는 측정값이다. 0 으로 채우지 않는다."""
        items = load("order_items")
        self.assertIn("unit_cost", items["required"])
        self.assertIn("null", items["properties"]["unit_cost"]["type"])

    def test_catalog_uses_the_commerce_field_names(self) -> None:
        """커머스가 #43 에서 먼저 내보내던 `selling_price`·`snapshot_at` 에 맞췄다."""
        catalog = load("catalog")
        self.assertIn("selling_price", catalog["required"])
        self.assertIn("snapshot_at", catalog["required"])
        self.assertNotIn("unit_price", catalog["properties"])


@unittest.skipUnless(_jsonschema_available(), NEEDS_JSONSCHEMA)
class TestSchemasRefuseCounterexamples(unittest.TestCase):
    """★ 통과하는 예제가 아니라 **반례가 거부되는지**를 본다."""

    def _validator(self, name: str):
        import jsonschema

        return jsonschema.Draft202012Validator(load(name))

    VALID_ITEM = {
        "order_id": "O00000001-000001", "line_no": 1, "product_id": "P0001",
        "quantity": 1, "unit_price": 8900, "unit_cost": 6900,
    }

    def test_the_real_commerce_sample_passes(self) -> None:
        """★ 이것이 실패하면 아래 반례 검사가 전부 무의미하다 — 실제 산출물이다."""
        for name in SCHEMAS:
            validator = self._validator(name)
            for row in sample_rows(name):
                with self.subTest(schema=name, row=row):
                    validator.validate(row)

    def test_wrong_order_id_shape_is_refused(self) -> None:
        import jsonschema

        with self.assertRaises(jsonschema.ValidationError):
            self._validator("order_items").validate(
                {**self.VALID_ITEM, "order_id": "O00000001"}
            )

    def test_unknown_field_is_refused(self) -> None:
        import jsonschema

        with self.assertRaises(jsonschema.ValidationError):
            self._validator("order_items").validate({**self.VALID_ITEM, "margin_rate": 0.22})

    def test_missing_unit_cost_key_is_refused(self) -> None:
        import jsonschema

        bad = {k: v for k, v in self.VALID_ITEM.items() if k != "unit_cost"}
        with self.assertRaises(jsonschema.ValidationError):
            self._validator("order_items").validate(bad)

    def test_null_unit_cost_is_accepted(self) -> None:
        self._validator("order_items").validate({**self.VALID_ITEM, "unit_cost": None})

    def test_negative_amount_is_refused(self) -> None:
        import jsonschema

        with self.assertRaises(jsonschema.ValidationError):
            self._validator("order_items").validate({**self.VALID_ITEM, "unit_price": -1})

    def test_naive_timestamp_is_refused(self) -> None:
        import jsonschema

        order = {**sample_rows("orders")[0], "ordered_at": "2026-01-01T10:00:00.000"}
        with self.assertRaises(jsonschema.ValidationError):
            self._validator("orders").validate(order)


# ── 로더 ────────────────────────────────────────────────────────────────────

class TestReadExchange(TempDirTest):
    def test_absent_is_none_not_an_empty_bundle(self) -> None:
        """★ 빈 묶음은 "주문 0건"이라는 측정값이 된다. 없는 것과 다르다."""
        self.assertIsNone(ex.read_exchange(self.tmp / "commerce"))

    def test_default_root_is_the_sibling_of_the_sink(self) -> None:
        self.assertEqual(Path("data/commerce"), ex.default_root(Path("data/raw")))

    def test_the_real_sample_is_read_and_grouped_by_order(self) -> None:
        bundle = ex.read_exchange(SAMPLE / "exchange")
        assert bundle is not None
        self.assertEqual(len(sample_rows("orders")), len(bundle.orders))
        self.assertEqual(
            len(sample_rows("order_items")),
            sum(len(order.items) for order in bundle.orders.values()),
        )
        for order in bundle.orders.values():
            with self.subTest(order=order.order_id):
                self.assertTrue(order.items)
                self.assertTrue(all(item.unit_cost is not None for item in order.items))

    def test_row_count_disagreeing_with_manifest_is_refused(self) -> None:
        """잘린 파일을 받아들이면 COGS 가 일부 주문의 합계인데 전체처럼 보인다."""
        root = copy_sample(self.tmp / "commerce")
        rewrite(root, "order_items", sample_rows("order_items")[:-1], keep_manifest=True)
        with self.assertRaises(ExchangeContractError):
            ex.read_exchange(root)

    def test_missing_manifest_is_refused(self) -> None:
        root = copy_sample(self.tmp / "commerce")
        (root / "manifest.json").unlink()
        with self.assertRaises(ExchangeContractError):
            ex.read_exchange(root)

    def test_other_contract_version_is_refused(self) -> None:
        root = copy_sample(self.tmp / "commerce")
        manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
        manifest["contract"] = "commerce-exchange/v2"
        (root / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
        with self.assertRaises(ExchangeContractError):
            ex.read_exchange(root)

    def test_zero_filled_cost_key_missing_is_refused(self) -> None:
        root = copy_sample(self.tmp / "commerce")
        rows = sample_rows("order_items")
        del rows[0]["unit_cost"]
        rewrite(root, "order_items", rows)
        with self.assertRaises(ExchangeContractError):
            ex.read_exchange(root)

    def test_bool_is_not_an_amount(self) -> None:
        """`True` 는 파이썬에서 `int` 다. 금액 자리에 들어오면 1원으로 읽힌다."""
        root = copy_sample(self.tmp / "commerce")
        rows = sample_rows("orders")
        rows[0]["discount"] = True
        rewrite(root, "orders", rows)
        with self.assertRaises(ExchangeContractError):
            ex.read_exchange(root)

    def test_item_of_an_unknown_order_is_refused(self) -> None:
        root = copy_sample(self.tmp / "commerce")
        rows = sample_rows("order_items")
        rows[0]["order_id"] = "O19990101-000001"
        rewrite(root, "order_items", rows)
        with self.assertRaises(ExchangeContractError):
            ex.read_exchange(root)

    def test_order_without_items_is_read_not_refused(self) -> None:
        """품목 없는 주문은 형식 위반이 아니라 `DQ-09` 위반이다 — 판정은 검사가 한다."""
        root = copy_sample(self.tmp / "commerce")
        orders = sample_rows("orders")
        rewrite(root, "order_items", [
            row for row in sample_rows("order_items")
            if row["order_id"] != orders[0]["order_id"]
        ])
        bundle = ex.read_exchange(root)
        assert bundle is not None
        self.assertEqual((), bundle.orders[orders[0]["order_id"]].items)


# ── DQ-09 ───────────────────────────────────────────────────────────────────

def sample_events() -> list[dict]:
    path = SAMPLE / "events.jsonl"
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def dq09(
    events: list[dict],
    exchange: ex.CommerceExchange | None,
    scope: list[dict] | None = None,
) -> dict:
    """`scope` 를 생략하면 `events` 전체가 커머스 이벤트라고 본다 — 이 파일의 표본이 그렇다."""
    report = dq.build_report(
        events, exchange=exchange, exchange_scope=events if scope is None else scope,
    )
    found = [c for c in report["checks"] if c["id"] == "DQ-09"]
    assert len(found) == 1, "DQ-09 를 찾지 못했다"
    return found[0]


def simulator_purchase(order_id: str, order_amount: int) -> dict:
    return {
        "event_id": "00000000-0000-4000-8000-0000000000aa",
        "customer_id": "C99999999", "session_id": "S-C99999999-1790581397887",
        "timestamp": "2026-09-28T16:43:17.890+09:00", "event_type": "purchase",
        "page_type": "complete", "order_id": order_id, "order_amount": order_amount,
        "simulator_version": "sim-1.0", "random_seed": 42,
    }


class TestAmountEquationScope(unittest.TestCase):
    """★★ #116 — 대조할 상대가 없는 것을 위반으로 적지 않는다."""

    def setUp(self) -> None:
        exchange = ex.read_exchange(SAMPLE / "exchange")
        assert exchange is not None
        self.exchange = exchange

    def test_simulator_only_data_is_not_run_not_a_violation(self) -> None:
        """수정 전에는 교환 파일 주문 전부가 "purchase 이벤트가 없다" 로 fail 이었다."""
        events = [simulator_purchase("O20251001-000001", 47_000)]
        split = pub.partition_by_source(events)
        self.assertEqual((), split.commerce)
        report = dq.build_report(events, exchange=self.exchange, exchange_scope=split.commerce)
        check = next(c for c in report["checks"] if c["id"] == "DQ-09")
        self.assertEqual("not_run", check["status"], check)
        self.assertIn("커머스", check["reason_detail"])

    @unittest.skipUnless(yaml_available(), NEEDS_YAML)
    def test_simulator_only_publish_does_not_fail_the_gate(self) -> None:
        """#116 재현 그대로 — 시뮬레이터 이벤트만 쓰고 옆에 교환 파일을 둔다."""
        from tests.test_publish_pipeline import simulator_event

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            shutil.copytree(SAMPLE / "exchange", root / "commerce")
            with EventSink(root / "raw") as sink:
                sink.write_events([
                    simulator_event(sc.EventType.SESSION_START, day=1),
                    simulator_event(sc.EventType.CHECKOUT_START, day=1,
                                    order_id="O20251001-000001"),
                    simulator_event(sc.EventType.PURCHASE, day=1,
                                    order_id="O20251001-000001"),
                ])
            pub.publish(
                source_root=root / "raw", output_root=root / "results",
                config_path=REPO_ROOT / "config/economic_config.yaml",
                index_date=date(2025, 10, 1),
            )
            quality = json.loads(
                (root / "results" / pub.artifact_relative("data_quality_report"))
                .read_text(encoding="utf-8")
            )
        check = next(c for c in quality["checks"] if c["id"] == "DQ-09")
        self.assertEqual("not_run", check["status"], check)
        self.assertNotEqual("fail", quality["gate_result"], quality["checks"])

    def test_colliding_simulator_order_id_is_not_compared(self) -> None:
        """시뮬레이터 주문이 커머스와 같은 order_id 를 써도 그 금액을 대조하지 않는다."""
        commerce = sample_events()
        order_id = sample_rows("orders")[0]["order_id"]
        events = [*commerce, simulator_purchase(order_id, 1)]
        split = pub.partition_by_source(events)
        check = next(
            c for c in dq.build_report(
                events, exchange=self.exchange, exchange_scope=split.commerce,
            )["checks"] if c["id"] == "DQ-09"
        )
        self.assertEqual("pass", check["status"], check)

    def test_missing_scope_is_not_run(self) -> None:
        report = dq.build_report(sample_events(), exchange=self.exchange)
        check = next(c for c in report["checks"] if c["id"] == "DQ-09")
        self.assertEqual("not_run", check["status"])


class TestAmountEquation(TempDirTest):
    def test_without_the_bundle_it_is_not_run(self) -> None:
        """★ 오늘의 기본 상태. 대조하지 않은 것을 통과나 위반으로 적으면 둘 다 거짓말이다."""
        check = dq09(sample_events(), None)
        self.assertEqual("not_run", check["status"])
        self.assertEqual("PRECONDITION_MISSING", check["reason_code"])
        self.assertIn("order_items", check["reason_detail"])

    def test_the_real_sample_passes(self) -> None:
        check = dq09(sample_events(), ex.read_exchange(SAMPLE / "exchange"))
        self.assertEqual("pass", check["status"], check)
        self.assertEqual(len(sample_rows("orders")), check["examined_rows"])
        self.assertEqual(0, check["violations"])

    def test_pre_discount_event_amount_is_a_violation(self) -> None:
        """★★ #106 의 모양 그대로다. 교환 파일 안에서는 등식이 맞아도 이벤트가
        할인 전 금액을 말하면 위반이어야 한다 — 이것을 못 잡으면 매출이 과대다."""
        exchange = ex.read_exchange(SAMPLE / "exchange")
        assert exchange is not None
        discounted = next(o for o in exchange.orders.values() if o.discount > 0)
        events = [
            {**e, "order_amount": e["order_amount"] + discounted.discount}
            if e.get("event_type") == "purchase" and e.get("order_id") == discounted.order_id
            else e
            for e in sample_events()
        ]
        check = dq09(events, exchange)
        self.assertEqual("fail", check["status"])
        self.assertEqual(1, check["violations"])
        self.assertIn(discounted.order_id, check["samples"][0]["detail"])

    def test_order_without_items_is_a_violation(self) -> None:
        root = copy_sample(self.tmp / "commerce")
        first = sample_rows("orders")[0]["order_id"]
        rewrite(root, "order_items", [
            row for row in sample_rows("order_items") if row["order_id"] != first
        ])
        check = dq09(sample_events(), ex.read_exchange(root))
        self.assertEqual("fail", check["status"])
        self.assertIn("품목이 없다", check["samples"][0]["detail"])

    def test_equation_broken_inside_the_bundle_is_a_violation(self) -> None:
        root = copy_sample(self.tmp / "commerce")
        orders = sample_rows("orders")
        orders[0]["discount"] += 1
        rewrite(root, "orders", orders)
        check = dq09(sample_events(), ex.read_exchange(root))
        self.assertEqual("fail", check["status"])

    def test_order_without_purchase_event_is_a_violation(self) -> None:
        """커머스 구매 이벤트가 있는데 **한 주문의 것만** 빠졌다 — 두 출처가 어긋난다.

        구매 이벤트가 **하나도** 없으면 대조할 상대가 없는 것이라 `not_run` 이다(#116).
        """
        exchange = ex.read_exchange(SAMPLE / "exchange")
        missing = sample_rows("orders")[0]["order_id"]
        events = [
            e for e in sample_events()
            if not (e.get("event_type") == "purchase" and e.get("order_id") == missing)
        ]
        check = dq09(events, exchange)
        self.assertEqual("fail", check["status"])
        self.assertEqual(1, check["violations"])
        self.assertIn("purchase 이벤트가 없다", check["samples"][0]["detail"])

    def test_no_commerce_purchase_at_all_is_not_run(self) -> None:
        exchange = ex.read_exchange(SAMPLE / "exchange")
        events = [e for e in sample_events() if e.get("event_type") != "purchase"]
        self.assertEqual("not_run", dq09(events, exchange)["status"])


# ── 경제 계산 ───────────────────────────────────────────────────────────────

class TestEconomicsWithTheBundle(unittest.TestCase):
    def setUp(self) -> None:
        exchange = ex.read_exchange(SAMPLE / "exchange")
        assert exchange is not None
        self.orders = pub.assemble_orders(sample_events(), exchange)
        self.commerce = json.loads((SAMPLE / "contribution.json").read_text(encoding="utf-8"))

    def test_cogs_reproduces_the_commerce_report(self) -> None:
        """수용 기준 ② — Σ(unit_cost × quantity) 가 커머스가 계산한 COGS 와 같다."""
        cogs = pub._sum_cogs(self.orders)
        self.assertIs(MetricStatus.OK, cogs.status, cogs.reason_detail)
        self.assertEqual(self.commerce["cogsKrw"], cogs.value)

    def test_net_and_gross_revenue_give_the_same_margin(self) -> None:
        """★ DR-101 — 순매출(AI_ROI)과 총매출(커머스) 표시는 같은 이익을 내야 한다.

        이벤트 금액이 할인 전이면(#106) 이 등식이 할인액만큼 어긋난다.
        """
        revenue = ec.revenue(self.orders).value
        cogs = pub._sum_cogs(self.orders).value
        shipping = ec.shipping_subsidy(self.orders, config=fixture_config()).value
        commerce_margin = (
            self.commerce["revenueKrw"] - self.commerce["cogsKrw"]
            - self.commerce["couponDiscountKrw"] - self.commerce["shippingSubsidyKrw"]
        )
        self.assertEqual(commerce_margin, revenue - cogs - shipping)

    def test_shipping_is_observed_not_derived(self) -> None:
        subsidy = ec.shipping_subsidy(self.orders, config=fixture_config())
        self.assertFalse(subsidy.derived, subsidy.derivation)
        self.assertEqual(self.commerce["shippingSubsidyKrw"], subsidy.value)

    def test_orders_without_the_bundle_keep_the_rule(self) -> None:
        """교환 파일에 없는 주문은 여전히 D-3 규칙이다 — 판정 기준은 값이 있는가다."""
        subsidy = ec.shipping_subsidy(
            pub.assemble_orders(sample_events(), None), config=fixture_config()
        )
        self.assertTrue(subsidy.derived)

    def test_observed_subsidy_is_fee_minus_charged(self) -> None:
        orders = (
            ec.OrderView("O1", 30_000, shipping_fee=3000, shipping_charged=0),
            ec.OrderView("O2", 50_000, shipping_fee=3000, shipping_charged=3000),
        )
        subsidy = ec.shipping_subsidy(orders, config=fixture_config())
        self.assertEqual(3000, subsidy.value)
        self.assertFalse(subsidy.derived)

    def test_mixed_observed_and_derived_is_marked_derived(self) -> None:
        """관측과 유도가 섞인 합계를 관측값처럼 보이게 하지 않는다."""
        orders = (
            ec.OrderView("O1", 30_000, shipping_fee=3000, shipping_charged=0),
            ec.OrderView("O2", 10_000, treatment_ids=("T1",)),
        )
        subsidy = ec.shipping_subsidy(orders, config=fixture_config())
        self.assertTrue(subsidy.derived)
        self.assertIn("관측 1건", subsidy.derivation or "")

    def test_cogs_without_items_is_unavailable_and_names_the_table(self) -> None:
        result = ec.cogs(ec.OrderView(order_id="O00000001-000001", order_amount=8900))
        self.assertIs(MetricStatus.UNAVAILABLE, result.status)
        self.assertIsNone(result.value, "계산 불가에 값이 붙으면 0 채우기와 같다")
        self.assertIn(
            "order_items",
            " ".join(str(b.ref) for b in (result.blocked_by or ())) + result.reason_detail,
        )

    def test_items_absent_and_cost_absent_are_different(self) -> None:
        """★ 해소 방법이 다르다 — 전자는 테이블이, 후자는 컬럼이 필요하다."""
        no_items = ec.cogs(ec.OrderView(order_id="O00000001-000001", order_amount=8900))
        no_cost = ec.cogs(ec.OrderView(
            order_id="O00000002-000001", order_amount=8900,
            items=(ec.OrderItem("P0001", 1, 8900, unit_cost=None),),
        ))
        self.assertIs(MetricStatus.UNAVAILABLE, no_items.status)
        self.assertIs(MetricStatus.UNAVAILABLE, no_cost.status)
        self.assertNotEqual(no_items.reason_detail, no_cost.reason_detail)


# ── 종단 ────────────────────────────────────────────────────────────────────

@unittest.skipUnless(yaml_available(), NEEDS_YAML)
class TestEndToEndWithTheRealCommerceSample(unittest.TestCase):
    """★★ 수용 기준 ⑤ — 커머스가 실제로 내보낸 이벤트와 교환 파일을 파이프라인에 넣는다.

    이벤트는 `EventSink` 로 쓰고 교환 파일은 `data/commerce` 자리(`raw` 의 형제)에
    둔다. `publish()` 가 기본 경로에서 스스로 찾는지까지 본다.
    """

    @classmethod
    def setUpClass(cls) -> None:
        cls._tmp = tempfile.TemporaryDirectory()
        root = Path(cls._tmp.name)
        shutil.copytree(SAMPLE / "exchange", root / "commerce")
        with EventSink(root / "raw") as sink:
            result = sink.write_events(sample_events())
        cls.rejected = result.rejected
        cls.outcome = pub.publish(
            source_root=root / "raw", output_root=root / "results",
            config_path=REPO_ROOT / "config/economic_config.yaml",
            index_date=date.fromisoformat(sample_events()[0]["timestamp"][:10]),
        )
        cls.kpi = json.loads(
            (root / "results" / pub.artifact_relative("kpi_report")).read_text(encoding="utf-8")
        )
        cls.quality = json.loads(
            (root / "results" / pub.artifact_relative("data_quality_report"))
            .read_text(encoding="utf-8")
        )
        cls.commerce = json.loads((SAMPLE / "contribution.json").read_text(encoding="utf-8"))

    @classmethod
    def tearDownClass(cls) -> None:
        cls._tmp.cleanup()

    def metric(self, name: str) -> dict:
        entry = next(m for m in self.kpi["metrics"] if m["name"] == name)
        return entry["value"]["by_source"]["commerce"]

    def test_every_artifact_passed_its_own_contract(self) -> None:
        self.assertEqual("ok", self.outcome.publish_result, self.outcome.artifacts)

    def test_commerce_events_are_all_accepted(self) -> None:
        self.assertEqual(0, self.rejected)

    def test_dq09_runs_and_passes(self) -> None:
        check = next(c for c in self.quality["checks"] if c["id"] == "DQ-09")
        self.assertEqual("pass", check["status"], check)

    def test_roster_checks_run_on_the_commerce_split(self) -> None:
        """#110 — publish 가 커머스 출처 이벤트만 명부 대조에 넘긴다."""
        for check_id in ("DQ-02", "DQ-03", "DQ-05"):
            with self.subTest(check=check_id):
                check = next(c for c in self.quality["checks"] if c["id"] == check_id)
                self.assertEqual("pass", check["status"], check)
                self.assertGreater(check["examined_rows"], 0)

    def test_cogs_is_published_and_matches_commerce(self) -> None:
        cogs = self.metric("cogs")
        self.assertEqual("ok", cogs["status"], cogs)
        self.assertEqual(self.commerce["cogsKrw"], cogs["value"])

    def test_revenue_is_net_of_discount(self) -> None:
        self.assertEqual(
            self.commerce["revenueKrw"] - self.commerce["couponDiscountKrw"],
            self.metric("revenue")["value"],
        )

    def test_coupon_cost_is_the_actual_discount(self) -> None:
        """#108 — 커머스 쿠폰에는 처치 ID 가 없다. 0 원이 아니라 실제 할인액이다."""
        coupon = self.metric("coupon_cost")
        self.assertEqual("ok", coupon["status"], coupon)
        self.assertEqual(self.commerce["couponDiscountKrw"], coupon["value"])

    def test_contribution_profit_is_computed(self) -> None:
        """수용 기준 ③ — 품목이 있으면 빈 `items` 대체 없이 기여이익이 계산된다."""
        self.assertEqual("ok", self.metric("contribution_profit")["status"])
