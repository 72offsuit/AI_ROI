"""Pins the draft commerce exchange contract and what we do without it (issue #100).

`purchase` is one row per order, and `product_id`/`quantity`/`unit_price` are
`NOT_APPLICABLE` on it -- `validate_event()` refuses them. So a order's line items
cannot be reconstructed from events, and two things stay blocked: `cogs()` returns
`NO_COST_BASIS`, and `DQ-09` (`order_amount = Σ(unit_price × quantity) − discount`)
cannot run at all.

`DQ-09` is blocked twice over: the items are missing **and** `discount` is not one
of the 22 event columns. The exchange files have to carry both.

What this file covers, and what it deliberately does not:

  checked    the four schemas are valid draft 2020-12 and **refuse counterexamples**
             -- a schema that accepts everything is not a contract
  checked    the id formats match what `schema.py` already fixes, so the join can
             actually happen (those two are not negotiable; they are GATE 1 canon)
  checked    ★ what happens with no exchange files at all -- today's real state.
             `DQ-09` must be `not_run`, never a pass and never a violation
  NOT        reading the files or wiring COGS. **The contract is not agreed yet**
             (issue #100 acceptance criterion ①), and building the consumer against
             an unagreed shape is how rework happens. That is slice B.

★ The distinction `not_run` vs violation is the point of the last group. "we did
  not compare" and "we compared and it was fine" must never collapse into one
  value -- the same rule that gives this repo `vacuous`, `met: null` and
  `verification: not_run`.
"""

from __future__ import annotations

import json
import unittest
from pathlib import Path

from src.measurement import economics as ec
from src.measurement import schema as sc
from src.measurement import validate as dq
from src.measurement.kpi import MetricStatus

CONTRACT = (
    Path(__file__).resolve().parent.parent
    / "docs" / "contracts" / "commerce-exchange" / "v1-draft"
)
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


def load(name: str) -> dict:
    return json.loads((CONTRACT / f"{name}.schema.json").read_text(encoding="utf-8"))


class TestTheDraftExists(unittest.TestCase):
    def test_all_four_schemas_and_the_readme(self) -> None:
        self.assertTrue(CONTRACT.is_dir(), f"{CONTRACT} 가 없다")
        self.assertTrue((CONTRACT / "README.md").is_file())
        for name in SCHEMAS:
            with self.subTest(schema=name):
                self.assertTrue((CONTRACT / f"{name}.schema.json").is_file())

    def test_every_schema_says_it_is_a_draft(self) -> None:
        """★ 초안이라는 사실이 파일 안에 있어야 한다.

        디렉터리 이름(`v1-draft`)만으로는 파일 하나를 따로 열어 본 사람이 모른다.
        합의되지 않은 계약을 합의된 것으로 읽으면 그 데이터를 만들기 시작한다.
        """
        for name in SCHEMAS:
            with self.subTest(schema=name):
                comment = load(name).get("$comment", "")
                self.assertIn("초안", comment)
                self.assertIn("#100", comment)

    def test_no_schema_accepts_unknown_fields(self) -> None:
        """`additionalProperties: false` — 계약에 없는 필드가 조용히 들어오지 않는다."""
        for name in SCHEMAS:
            with self.subTest(schema=name):
                self.assertIs(False, load(name).get("additionalProperties"))


class TestIdFormatsMatchTheEventContract(unittest.TestCase):
    """★ 결합이 실제로 성립하려면 형식이 같아야 한다.

    `order_id`·`customer_id` 형식은 **협상 대상이 아니다.** `schema.py` 가 이미
    정규식으로 고정하고 있고 그것은 GATE 1 정본이다. 교환 파일이 다른 형식을
    쓰면 결합이 되지 않고, 그 사실은 고아 레코드(DQ-03)로만 뒤늦게 드러난다.
    """

    def _event_pattern(self, field: str) -> str:
        """정본은 `schema.IDENTIFIER_PATTERNS` 하나다.

        ★ 처음에는 `FieldSpec.pattern` 을 찾다가 없어서 `skipTest` 로 넘겼고,
          **그 상태로 두 검사가 통과처럼 보였다.** 값을 찾지 못해 건너뛴 것을
          결과로 적으면 결합이 어긋나도 아무도 모른다. 실제 상수를 쓴다.
        """
        return sc.IDENTIFIER_PATTERNS[field]

    def test_order_id_pattern_is_the_event_pattern(self) -> None:
        self.assertEqual(
            self._event_pattern("order_id"),
            load("orders")["properties"]["order_id"]["pattern"],
        )
        self.assertEqual(
            self._event_pattern("order_id"),
            load("order_items")["properties"]["order_id"]["pattern"],
        )

    def test_product_id_pattern_is_the_event_pattern(self) -> None:
        """★ 초안은 여기를 `minLength: 1` 로 느슨하게 뒀었다.

        `product_id` 도 `^P\\d{4}$` 로 고정돼 있다. 교환 파일이 다른 형식을
        쓰면 `catalog` ↔ `order_items` ↔ 이벤트 결합이 어긋나고, 그 사실은
        고아 레코드(DQ-03)로만 뒤늦게 드러난다.
        """
        pattern = self._event_pattern("product_id")
        for name in ("catalog", "order_items"):
            with self.subTest(schema=name):
                self.assertEqual(
                    pattern, load(name)["properties"]["product_id"]["pattern"]
                )

    def test_customer_id_pattern_is_the_event_pattern(self) -> None:
        pattern = self._event_pattern("customer_id")
        for name in ("orders", "customers"):
            with self.subTest(schema=name):
                self.assertEqual(
                    pattern, load(name)["properties"]["customer_id"]["pattern"]
                )


class TestDiscountIsRequiredNotOptional(unittest.TestCase):
    """★ `#100` 초기 논의에서 '있으면 좋은 것' 으로 적었던 것을 정정한다.

    순매출 기준(`#101`)에서 기여이익은 실제 할인액을 요구하지 않는다. 그래서
    선택 사항으로 적었는데, **`DQ-09` 가 그것 없이는 성립하지 않는다** —
    등식 자체에 `− discount` 가 들어간다. 필수다.
    """

    def test_discount_is_in_required(self) -> None:
        self.assertIn("discount", load("orders")["required"])

    def test_unit_cost_is_required_but_nullable(self) -> None:
        """★ 필수인데 `null` 을 받는다 — 모순이 아니라 구분이다.

        키가 없는 것은 계약 위반이고, `null` 은 *"원가를 모른다"* 는 **측정값**이다.
        `0` 으로 채우면 원가 0원인 상품과 구분이 사라진다.
        """
        items = load("order_items")
        self.assertIn("unit_cost", items["required"])
        self.assertIn("null", items["properties"]["unit_cost"]["type"])

    def test_quantity_has_no_null(self) -> None:
        """수량은 모를 수 없다 — 품목 줄이 있다는 것 자체가 샀다는 뜻이다."""
        self.assertEqual("integer", load("order_items")["properties"]["quantity"]["type"])


@unittest.skipUnless(_jsonschema_available(), NEEDS_JSONSCHEMA)
class TestSchemasRefuseCounterexamples(unittest.TestCase):
    """★ 통과하는 예제가 아니라 **반례가 거부되는지**를 본다.

    전부 통과시키는 스키마도 '검증한다' 고 말할 수 있다. 무엇을 막는지가
    계약의 내용이다.
    """

    def _validator(self, name: str):
        import jsonschema

        return jsonschema.Draft202012Validator(load(name))

    VALID_ITEM = {
        "order_id": "O00000001-000001", "line_no": 1, "product_id": "P0001",
        "quantity": 1, "unit_price": 8900, "unit_cost": 6900,
    }

    def test_the_valid_example_passes(self) -> None:
        """★ 이것이 실패하면 아래 반례 검사가 전부 무의미하다."""
        self._validator("order_items").validate(self.VALID_ITEM)

    def test_wrong_order_id_shape_is_refused(self) -> None:
        import jsonschema

        bad = {**self.VALID_ITEM, "order_id": "O00000001"}  # -000001 이 없다
        with self.assertRaises(jsonschema.ValidationError):
            self._validator("order_items").validate(bad)

    def test_unknown_field_is_refused(self) -> None:
        import jsonschema

        bad = {**self.VALID_ITEM, "margin_rate": 0.22}
        with self.assertRaises(jsonschema.ValidationError):
            self._validator("order_items").validate(bad)

    def test_missing_unit_cost_key_is_refused(self) -> None:
        """키 누락은 위반이다 — `null` 과 다르다."""
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
        """KST 오프셋이 없으면 순간을 특정할 수 없다."""
        import jsonschema

        order = {
            "order_id": "O00000001-000001", "customer_id": "C00000001",
            "ordered_at": "2026-01-01T10:00:00.000", "order_amount": 8900,
            "discount": 0,
        }
        with self.assertRaises(jsonschema.ValidationError):
            self._validator("orders").validate(order)
        self._validator("orders").validate(
            {**order, "ordered_at": "2026-01-01T10:00:00.000+09:00"}
        )


class TestBehaviourWithoutTheExchangeFiles(unittest.TestCase):
    """★★ 수용 기준 ④ — 계약이 없을 때 무엇을 말하는가. **오늘의 실제 상태다.**"""

    def test_dq09_is_not_run_not_a_pass_and_not_a_violation(self) -> None:
        report = dq.build_report([])
        checks = report.get("checks") or report.get("items") or []
        found = [c for c in checks if str(c.get("id", "")).startswith("DQ-09")]
        self.assertEqual(1, len(found), "DQ-09 를 찾지 못했다 — 검사가 비어 있다")
        check = found[0]
        self.assertEqual(
            "not_run", check["status"],
            "대조하지 않은 것을 통과나 위반으로 적으면 둘 다 거짓말이 된다",
        )
        self.assertEqual("PRECONDITION_MISSING", check["reason_code"])
        self.assertIn(
            "order_items", check["reason_detail"],
            "무엇이 있어야 성립하는지가 없으면 읽는 사람이 해소 방법을 모른다",
        )

    def test_cogs_without_items_is_unavailable_and_names_the_table(self) -> None:
        order = ec.OrderView(order_id="O00000001-000001", order_amount=8900)
        result = ec.cogs(order)
        self.assertIs(MetricStatus.UNAVAILABLE, result.status)
        self.assertIsNone(result.value, "계산 불가에 값이 붙으면 0 채우기와 같다")
        self.assertIn(
            "order_items",
            " ".join(str(b.ref) for b in (result.blocked_by or ())) + result.reason_detail,
        )

    def test_items_absent_and_cost_absent_are_different(self) -> None:
        """★ 해소 방법이 다르다 — 전자는 테이블이, 후자는 컬럼이 필요하다.

        둘을 같은 문구로 적으면 커머스가 무엇을 보내야 하는지 알 수 없다.
        """
        no_items = ec.cogs(ec.OrderView(order_id="O00000001-000001", order_amount=8900))
        no_cost = ec.cogs(ec.OrderView(
            order_id="O00000002-000001", order_amount=8900,
            items=(ec.OrderItem("P0001", 1, 8900, unit_cost=None),),
        ))
        self.assertIs(MetricStatus.UNAVAILABLE, no_items.status)
        self.assertIs(MetricStatus.UNAVAILABLE, no_cost.status)
        self.assertNotEqual(
            no_items.reason_detail, no_cost.reason_detail,
            "품목을 모르는 것과 원가를 모르는 것이 같은 문구로 나온다",
        )

    def test_cogs_computes_when_the_snapshot_is_there(self) -> None:
        """★ 거짓 양성 — 원가가 있으면 실제로 계산돼야 한다.

        계약이 오면 무엇이 열리는지를 이 테스트가 보인다.
        """
        order = ec.OrderView(
            order_id="O00000001-000001", order_amount=17_800,
            items=(
                ec.OrderItem("P0001", 2, 8900, unit_cost=6900),
                ec.OrderItem("P0002", 1, 0, unit_cost=0),
            ),
        )
        result = ec.cogs(order)
        self.assertIs(MetricStatus.OK, result.status, result.reason_detail)
        self.assertEqual(13_800.0, result.value, "Σ(unit_cost × quantity)")
