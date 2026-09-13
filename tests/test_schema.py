"""이벤트 스키마 검사 (SRS DATA-003, ISO-003).

측정 계층의 계약이 스스로 모순되지 않는지, 그리고 통과해서는 안 되는 것이
스키마에 섞이지 않았는지 확인한다.

실행:
    python3 -m unittest tests.test_schema -v
"""

from __future__ import annotations

import json
import re
import unittest
import uuid
from pathlib import Path

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
        "category": "fresh_food",
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

    def test_unknown_category_is_rejected(self) -> None:
        record = _base_record(sc.EventType.PRODUCT_VIEW, category="우주선")
        problems = sc.validate_event(record)
        self.assertTrue(any("category" in p for p in problems), problems)

    def test_unknown_page_type_is_rejected(self) -> None:
        record = _base_record(sc.EventType.SESSION_START, page_type="아무거나")
        problems = sc.validate_event(record)
        self.assertTrue(any("page_type" in p for p in problems), problems)

    def test_malformed_identifier_is_reported(self) -> None:
        """D2-1 — check_identifier() had no production caller before this.

        "test-user-1" is the shape Ecommerce_Service actually seeds today
        (seed-data.ts), so this is the real case, not a synthetic one.
        """
        record = _base_record(sc.EventType.PURCHASE, customer_id="test-user-1")
        problems = sc.validate_event(record)
        self.assertTrue(any("customer_id" in p for p in problems), problems)

    def test_none_identifier_is_not_a_format_violation(self) -> None:
        """Absence and malformation are different findings and must not merge.

        page_view.category/product_id are optional; a commerce record that omits them
        is incomplete (MEA-003 tolerates that) but not malformed.
        """
        record = _base_record(sc.EventType.PAGE_VIEW, product_id=None, category=None)
        problems = sc.validate_event(record)
        self.assertEqual([], [p for p in problems if "형식" in p], problems)

    def test_every_category_and_page_type_value_is_accepted(self) -> None:
        """The enums must admit exactly what the fixtures and config use."""
        for category in sc.Category:
            with self.subTest(category=category.value):
                record = _base_record(sc.EventType.PRODUCT_VIEW, category=category.value)
                self.assertEqual([], sc.validate_event(record))
        for page_type in sc.PageType:
            with self.subTest(page_type=page_type.value):
                record = _base_record(sc.EventType.SESSION_START, page_type=page_type.value)
                self.assertEqual([], sc.validate_event(record))

    def test_naive_timestamp_is_reported(self) -> None:
        """D1-3 — an offset-less timestamp does not identify an instant."""
        record = _base_record(sc.EventType.PURCHASE, timestamp="2025-10-01T23:30:00")
        problems = sc.validate_event(record)
        self.assertTrue(any("timestamp" in p for p in problems), problems)

    def test_utc_timestamp_is_accepted(self) -> None:
        """Policy ⑵ — any explicit offset is accepted; the Sink normalises to KST."""
        record = _base_record(sc.EventType.PURCHASE, timestamp="2025-10-01T23:30:00.000Z")
        self.assertEqual([], sc.validate_event(record))

    def test_unparsable_timestamp_is_left_to_the_sink(self) -> None:
        """★ The narrow path that keeps test_sink.test_unparsable_timestamp_is_reported.

        validate_event() judges the OFFSET, never the parseability. If it also rejected
        garbage, "어제" would never reach _buffer, flush() would raise nothing, and that
        Sink test — which fixes "a schema pass must not silently become a bad partition
        key" — would fail. Do not "tighten" this into a parse check.
        """
        record = _base_record(sc.EventType.PURCHASE, timestamp="어제")
        self.assertEqual(
            [], [p for p in sc.validate_event(record) if "timestamp" in p]
        )

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


class TestContractVocabulary(unittest.TestCase):
    """MetricStatus/ReasonCode must match the published contract character for character.

    The contract is canonical: it rejects violations, whereas the planning docs
    (kpi-definition-v1.md lists 7 reason codes, the contract has 9) fail silently when
    they drift. So this reads the contract and asserts the code follows it — if the two
    ever diverge, the code is what gets fixed.

    Standard library only (json + pathlib), so it runs without jsonschema installed.
    """

    #: .agent-team/ sits outside src/, following the tests/test_isolation.py convention
    #: of resolving repo-relative paths from the test file itself.
    CONTRACT = (
        Path(__file__).resolve().parents[1]
        / ".agent-team/04-architecture/schemas/common.schema.json"
    )

    def setUp(self) -> None:
        self.defs = json.loads(self.CONTRACT.read_text(encoding="utf-8"))["$defs"]

    def test_reason_code_matches_contract(self) -> None:
        self.assertEqual(
            set(self.defs["reason_code"]["enum"]),
            {code.value for code in sc.ReasonCode},
        )

    def test_metric_status_matches_contract(self) -> None:
        self.assertEqual(
            set(self.defs["metric_value"]["properties"]["status"]["enum"]),
            {status.value for status in sc.MetricStatus},
        )

    def test_nine_reason_codes_and_five_statuses(self) -> None:
        """Exact counts, so adding an enum member cannot pass unnoticed."""
        self.assertEqual(9, len(list(sc.ReasonCode)))
        self.assertEqual(5, len(list(sc.MetricStatus)))


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




# ══════════════════════════════════════════════════════════════════════════
# `docs/measurement_contract.md` ↔ 코드 대조 (이슈 #45)
#
# ## 왜 문서를 테스트하나
#
# *"계약은 검증되고 문서는 검증되지 않는다."* — 이 프로젝트가 계약을 정본으로 삼은
# 이유다. 그런데 `#45` 는 **문서**를 요구한다(커머스 구현자가 읽을 것이 필요하다).
# 그러면 그 문서는 **어긋나도 아무것도 실패하지 않는 바로 그 물건**이 된다.
#
# → 문서를 파싱해 `schema.py` 와 대조한다. 문서가 낡으면 실패한다.
#
# ## 왜 이 파일에 있나
#
# 이 검사의 모든 단언이 *"문서가 `schema.py` 와 일치하는가"* 다. 별도 파일
# (`test_measurement_contract.py`)로 두었더니 `ownership.json` 의 Phillip 소유
# 테스트 패턴(`test_schema`·`test_sink`·`test_kpi_*`·`test_publish_*` 등)에 걸리지
# 않아 `check_ownership.py` 가 **소유자 없음**으로 잡았다. **소유 경계는 W2 가 정한
# 것이고 구현자가 넓히는 것이 아니므로**, `ownership.json` 을 고치는 대신 검사
# 대상과 같은 파일로 옮겼다.
#
# ## 한계 — 적어 두지 않으면 통과가 보증으로 오해된다
#
# 마크다운 표를 정규식으로 읽으므로 **표 모양이 바뀌면 대조 대상이 조용히 줄어든다.**
# 그래서 `test_every_event_type_row_was_found` 가 **16행을 실제로 찾았는지 먼저**
# 본다 — *"검사는 돌았지만 대상 집합이 비어 있었다"* 를 막는 장치다.
# 산문의 정확성은 검사하지 않는다. 표의 **값**만 본다.
# ══════════════════════════════════════════════════════════════════════════

CONTRACT = (
    Path(__file__).resolve().parents[1] / "docs" / "measurement_contract.md"
)


def _document() -> str:
    return CONTRACT.read_text(encoding="utf-8")


def _backticked(cell: str) -> set[str]:
    """표 칸에서 `` `name` `` 들을 뽑는다. `— (Core 4 뿐)` 같은 칸은 빈 집합."""
    return set(re.findall(r"`([a-z_]+)`", cell))


def _funnel_rows() -> dict[str, tuple[set[str], set[str]]]:
    """§1 퍼널 표 → `{event_type: (필수, 선택)}`.

    `| 단계 | \\`event_type\\` | 필수 | 선택 |` 모양의 행만 읽는다. `event_type` 이
    16종 중 하나인 행으로 한정하므로 다른 표의 행이 섞이지 않는다.
    """
    known = {item.value for item in sc.EventType}
    rows: dict[str, tuple[set[str], set[str]]] = {}
    for line in _document().splitlines():
        if not line.startswith("|"):
            continue
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if len(cells) != 4:
            continue
        name = cells[1].strip("`* ")
        if name not in known:
            continue
        rows[name] = (_backticked(cells[2]), _backticked(cells[3]))
    return rows


def _section(heading: str) -> str:
    """`heading` 으로 시작하는 절의 본문. 다음 같은/상위 레벨 제목까지.

    **절 단위로 검사하기 위한 것이다.** 문서 전체를 `assertIn` 으로 훑으면
    *"어딘가 있으면 통과"* 가 되고, §1 표가 틀려도 §8 이슈 초안이 같은 값을
    담고 있으면 놓친다 — 1차 구현이 실제로 그랬다.
    """
    lines = _document().splitlines()
    level = heading.split(" ", 1)[0]
    try:
        start = next(i for i, line in enumerate(lines) if line.startswith(heading))
    except StopIteration:
        return ""
    body: list[str] = []
    for line in lines[start + 1:]:
        if re.match(r"^#{1,6} ", line) and len(line.split(" ", 1)[0]) <= len(level):
            break
        body.append(line)
    return "\n".join(body)


def _identifier_table() -> dict[str, str]:
    """§2 식별자 표 → `{필드: 정규식}`.

    ★ **필드명을 `IDENTIFIER_PATTERNS` 로 걸러내지 않는다.** 1차 구현이 그렇게
    했고, 그러면 문서가 코드에 없는 식별자(`store_id` 등)를 추가해도 파서가
    조용히 건너뛰어 **역방향 검사가 무력해진다.** negative control 에서 실제로
    잡히지 않았다.

    →  대신 **절을 한정**한다. `### 식별자 형식 9종` 안의 3칸 표만 읽으므로
       다른 표가 섞이지 않고, 그 안의 미지 필드는 그대로 드러난다.
    """
    section = _section("### 식별자 형식")
    found: dict[str, str] = {}
    for line in section.splitlines():
        if not line.startswith("|"):
            continue
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if len(cells) != 3:
            continue
        name = cells[0].strip("`* ")
        # 헤더 행(`필드`)과 구분선(`---`)을 건너뛴다. 그 밖은 전부 읽는다.
        if not re.fullmatch(r"[a-z_]+", name):
            continue
        found[name] = cells[1].strip("`* ")
    return found


class TestFunnelMapping(unittest.TestCase):
    """AC-2 — 퍼널 매핑이 `_EVENT_RULES` 와 일치한다."""

    def setUp(self) -> None:
        self.rows = _funnel_rows()

    def test_every_event_type_row_was_found(self) -> None:
        """★ **대상 집합을 먼저 본다.** 표 모양이 바뀌어 0행을 읽고도 통과하지 않게."""
        self.assertEqual(
            {item.value for item in sc.EventType}, set(self.rows),
            "§1 퍼널 표에서 16종을 다 찾지 못했다 — 표 모양이 바뀌었거나 행이 "
            "빠졌다. 찾은 것: " + str(sorted(self.rows)),
        )

    def test_required_fields_match_the_code(self) -> None:
        """문서의 "필수" 칸 = `_EVENT_RULES[e][0]`. Core 4 는 표에서 제외된다."""
        for event_type in sc.EventType:
            documented, _ = self.rows[event_type.value]
            expected = sc._EVENT_RULES[event_type][0]
            with self.subTest(event_type=event_type.value):
                self.assertEqual(
                    set(expected), documented,
                    f"{event_type.value} 의 필수 필드가 문서와 코드에서 다르다. "
                    "코드가 정본이므로 문서를 고친다",
                )

    def test_optional_fields_match_the_code(self) -> None:
        for event_type in sc.EventType:
            _, documented = self.rows[event_type.value]
            expected = sc._EVENT_RULES[event_type][1]
            with self.subTest(event_type=event_type.value):
                self.assertEqual(set(expected), documented)

    def test_core_meta_assignment_groups_are_stated(self) -> None:
        """Core 4 · Meta 4 · 배정 3 이 표 밖에 명시돼 있어야 한다."""
        document = _document()
        for name in sorted(sc.CORE_FIELDS | sc.META_FIELDS | sc._ASSIGNMENT_OPTIONAL):
            with self.subTest(field=name):
                self.assertIn(f"`{name}`", document)


class TestValueVocabularyIsQuoted(unittest.TestCase):
    """AC-3 — 값을 **인용한다.** 다시 정의하지 않는다."""

    def test_every_category_value_appears(self) -> None:
        document = _document()
        for item in sc.Category:
            with self.subTest(category=item.value):
                self.assertIn(item.value, document)

    def test_no_extra_category_value_is_invented(self) -> None:
        """★ 문서가 코드에 없는 카테고리를 만들지 않았는지 — 역방향 검사다."""
        block = re.search(
            r"### `category` 5종\s*\n+```\n(.+?)\n```", _document(), re.S
        )
        self.assertIsNotNone(block, "§2 의 category 코드블록을 찾지 못했다")
        documented = {
            token.strip() for token in block.group(1).replace("\n", " ").split("·")
        }
        self.assertEqual({item.value for item in sc.Category}, documented)

    def test_every_page_type_value_appears(self) -> None:
        block = re.search(
            r"### `page_type` 8종\s*\n+```\n(.+?)\n```", _document(), re.S
        )
        self.assertIsNotNone(block)
        documented = {
            token.strip() for token in block.group(1).replace("\n", " ").split("·")
        }
        self.assertEqual({item.value for item in sc.PageType}, documented)

    def test_identifier_patterns_match_the_code(self) -> None:
        """★ 정규식 9종을 **§2 표에서 파싱해 양방향 대조**한다.

        1차 구현은 `assertIn(f"`{pattern}`", document)` 였다. **약했다** —
        `^C\d{8}$` 가 §2 표와 §8 이슈 초안에 **두 번** 나오므로 §2 가 틀려도
        §8 이 맞으면 통과한다. `assertIn` 은 *"어딘가 있으면"* 을 보고
        *"그 자리에 맞게 있는가"* 를 보지 않는다.
        →  표를 `{필드: 정규식}` 으로 읽어 **필드별로** 대조하고, 문서가 코드에
           없는 필드를 만들지 않았는지도 함께 본다.
        """
        documented = _identifier_table()
        self.assertTrue(documented, "§2 식별자 표를 찾지 못했다 — 표 모양이 바뀌었다")
        # ← 코드에 있는 것이 문서에 정확히 있는가
        for name, pattern in sc.IDENTIFIER_PATTERNS.items():
            with self.subTest(field=name):
                self.assertIn(name, documented, f"{name} 행이 §2 표에 없다")
                if name == "event_id":
                    # UUID4 정규식은 길어 문서에 "UUID4" 로 적었다 — 명시적 예외다.
                    self.assertEqual("UUID4", documented[name])
                    continue
                self.assertEqual(
                    pattern, documented[name],
                    f"{name} 의 정규식이 문서와 코드에서 다르다. 정본은 "
                    "schema.IDENTIFIER_PATTERNS 이므로 문서를 고친다",
                )
        # → 문서가 코드에 없는 식별자를 만들지 않았는가 (역방향)
        self.assertEqual(
            set(sc.IDENTIFIER_PATTERNS), set(documented),
            "§2 표가 코드에 없는 식별자를 담고 있다",
        )

    def test_session_timeout_matches_the_code(self) -> None:
        self.assertIn(
            f"무활동 {sc.SESSION_TIMEOUT_MINUTES}분", _document()
        )

    def test_canonical_source_is_named(self) -> None:
        """★ *"정본은 코드다"* 가 문서에 적혀 있어야 한다 — 없으면 문서가 정본처럼 읽힌다."""
        document = _document()
        self.assertIn("src/measurement/schema.py", document)
        self.assertIn("정본", document)


class TestLockAuditConclusions(unittest.TestCase):
    """★ AC-7 — Lock 최종 검산. **네 공백에 전부 결론이 있어야 한다.**

    `gate1-lock-scope.md` §2.2 — *"계약 문서를 실제로 쓰는 행위가 스키마 표현력을
    검산한다."* 결론이 없으면 `#49`(GATE 1 부분 봉인)로 진행하지 않는다.
    """

    def test_derived_state_contract_sentences_are_present(self) -> None:
        """①~⑤ 다섯 문장. 특히 ④(Feature 금지)가 빠지면 안 된다."""
        document = _document()
        for needle, why in (
            ("events` 에 기록되지 않는다", "① 기록자가 보내지 않는다"),
            ("게시 시점에 계산", "② 측정 계층이 계산한다"),
            ("derived: true", "③ 저장된 사실과 구분된다"),
            ("Feature 로 쓰지 않는다", "④ ★ 라벨 동어반복 금지"),
            ("DB-012", "⑤ 대시보드가 계산하는 것이 아니다"),
        ):
            with self.subTest(sentence=why):
                self.assertIn(needle, document, f"파생 상태 계약 문장 누락: {why}")

    def test_feature_ban_states_its_reason(self) -> None:
        """★ 금지만 적으면 다음 사람이 이유를 몰라 되돌린다."""
        document = _document()
        self.assertIn("동어반복", document)
        self.assertIn("Risk 7", document)

    def test_derived_state_values_are_named(self) -> None:
        for item in sc.DerivedStateType:
            with self.subTest(state=item.value):
                self.assertIn(item.value, _document())

    def test_schema_gaps_all_have_a_conclusion(self) -> None:
        """네 공백 — 파생 상태 · shipping_subsidy · discount · customers."""
        document = _document()
        for ref in ("shipping_subsidy", "discount", "customers", "unit_cost"):
            with self.subTest(gap=ref):
                self.assertIn(ref, document)

    def test_no_go_rule_is_written(self) -> None:
        """★ *"공백이 드러나면 #49 로 진행하지 않는다"* 가 문서에 있어야 한다."""
        self.assertIn("FREEZE-003", _document())
        self.assertRegex(
            _document(), r"#49.*진행|진행.*#49",
        )

    def test_repurchase_rate_is_not_misclassified(self) -> None:
        """★ Matthias 항목4 — 근거가 있는데 없다고 말하지 않는다."""
        document = _document()
        self.assertIn("repurchase_rate", document)
        self.assertIn("막히지 않는다", document)
        self.assertIn("과대보고의 거울상", document)


class TestLimitsAreRecorded(unittest.TestCase):
    """AC-6 — 한계를 적는다. 적지 않으면 없는 것이 된다."""

    def test_four_limits_are_present(self) -> None:
        """★ **§7 절 안에서** 찾는다. 문서 전체를 훑으면 §8 초안이 같은 낱말을
        담고 있어 §7 절을 지워도 통과한다 — negative control 에서 실제로 그랬다.
        """
        limits = _section("## 7. 한계")
        self.assertTrue(limits, "§7 한계 절을 찾지 못했다")
        for needle, why in (
            ("campaign_response_count", "쿠폰 비종속 캠페인 과소계상"),
            ("캐러셀", "자동 전환을 page_view 로 찍지 않는다 (R-9)"),
            ("A-REFUND", "총매출을 순매출로 간주한다"),
            ("17.4", "정본 긴장 T-1 — results/ 접근 주체"),
        ):
            with self.subTest(limit=why):
                self.assertIn(
                    needle, limits,
                    f"§7 에서 한계 누락: {why}. 다른 절에 적어도 한계 절이 "
                    "비면 읽는 사람이 못 찾는다",
                )

    def test_limit_note_is_distinguished_from_unconfirmed(self) -> None:
        """★ 고쳐질 것과 고쳐지지 않을 것을 섞지 않는다."""
        document = _document()
        self.assertIn("limit_note", document)
        self.assertIn("영원히", document)

    def test_ingestion_gap_is_not_called_no_activity(self) -> None:
        """★ *"활동 없음"* 이라고 단정하지 않는다 — 0 채우기와 같은 잘못이다."""
        document = _document()
        self.assertIn("구분할 수 없다", document)
        self.assertNotIn("활동이 없었다", document)


class TestCommerceRequirements(unittest.TestCase):
    """AC-4 · AC-8 — 상품 참조 계약과 커머스 적용 요구."""

    def test_product_reference_fields_are_specified(self) -> None:
        document = _document()
        for field in ("product_id", "category", "selling_price", "unit_cost"):
            with self.subTest(field=field):
                self.assertIn(field, document)

    def test_null_unit_cost_is_distinguished_from_zero(self) -> None:
        """★ 원가 0원인 상품과 원가를 모르는 상품은 다르다."""
        self.assertIn("`unit_cost: null` 과 `unit_cost: 0` 은 다르다", _document())

    def test_source_discrimination_rule_is_stated(self) -> None:
        """커머스가 메타 2종을 `null` 로 둔다는 것이 명시돼야 한다."""
        document = _document()
        self.assertIn("simulator_version", document)
        self.assertIn("random_seed", document)
        self.assertIn("MEA-002", document)

    def test_issue_draft_is_marked_as_unpublished(self) -> None:
        """★ AC-8 — 초안이고 발행하지 않았다는 사실이 문서에 있어야 한다 (권한 L3)."""
        document = _document()
        self.assertIn("발행하지 않았다", document)
        self.assertIn("파일을 변경하지 않았다", document)

    def test_mapping_layer_is_refused(self) -> None:
        """★ 창구 중립성 — 측정 계층에 매핑 계층을 만들지 않는다."""
        self.assertIn("맞추는 쪽은 소스다", _document())

    def test_purchase_item_trap_is_warned(self) -> None:
        """★ 커머스 구현자가 가장 밟기 쉬운 자리를 경고한다."""
        document = _document()
        self.assertIn("주문 단위 1행", document)
        for field in sorted(
            f.name for f in sc.EVENT_FIELDS
            if sc.requirement(sc.EventType.PURCHASE, f.name)
            is sc.Requirement.NOT_APPLICABLE
        ):
            with self.subTest(field=field):
                self.assertIn(f"`{field}`", document)


class TestTimezonePolicyIsQuoted(unittest.TestCase):
    """M-01 이 확정한 정책을 인용한다. 다시 정의하지 않는다."""

    def test_policy_three_branches_are_stated(self) -> None:
        document = _document()
        self.assertIn("KST", document)
        self.assertIn("오프셋이 없는", document)
        self.assertIn("정규화", document)

    def test_precision_matches_the_code(self) -> None:
        self.assertIn("2025-10-01T09:00:00.000+09:00", _document())

    def test_dq06_link_is_explained(self) -> None:
        """★ 저장 표현 b 를 고른 이유가 적혀 있어야 한다."""
        self.assertIn("DQ-06", _document())


if __name__ == "__main__":
    unittest.main()
