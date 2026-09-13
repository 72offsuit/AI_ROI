"""게시 계약 검사 — 계약 수정 4건이 **의도대로** 동작하는지 (M-06 AC-4b~AC-4e).

## 이 파일의 존재 이유 한 문단

이 사이클의 계약 수정은 전부 JSON Schema 의미론에 걸려 있고, **두 번 잘못될 뻔했다.**
한 번은 막고 있던 것을 열고(F-F), 한 번은 통과시켜야 할 것을 전부 막는다(F-E).
둘 다 *"가장 짧은 자연스러운 편집"* 에서 나왔고, **픽스처에 해당 레코드가 없어서 기존
테스트는 전부 통과한다.** 그래서 *"고쳤다"* 와 *"고친 것이 의도대로 동작한다"* 를
분리해 후자를 기계가 검사한다.

## 두 층으로 나뉜다 — 아래층은 `jsonschema` 없이도 돈다

`TestUncomputableBranchLogic` 은 **`jsonschema` skip 대상이 아니다.** `not` 은 논리
연산이므로 계약 파일에서 `allOf[2].then.not` 을 **읽어와** `all()`/`any()` 로 판정할
수 있다. 회귀 지점이 바로 거기이므로, 의존성이 없는 CI 에서도 그 방어는 검사된다.

`TestFixturesAgainstContract` 등은 `$ref` 해석·정규식 방언·오류 경로 모양이 필요해
`jsonschema` 가 있어야 하고, 없으면 **skip + 사유**를 남긴다.

실행:
    python3 -m unittest tests.test_publish_contract -v
"""

from __future__ import annotations

import json
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
CONTRACTS = REPO_ROOT / "docs" / "contracts" / "measurement-publish" / "v1"
SNAPSHOT = REPO_ROOT / ".agent-team" / "04-architecture" / "schemas"
EXAMPLES = REPO_ROOT / ".agent-team" / "04-architecture" / "examples"
BASE_URI = "https://72offsuit.local/ai-roi/measurement-publish/v1/"


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _constraint_path(error: object) -> str:
    """오류를 **어느 제약이 물었는가**로 요약한다.

    `absolute_schema_path` 전체를 쓰면 `$ref` 가 인라인 해석되어
    `properties/totals/properties/events_rejected/allOf/0/then/required` 처럼
    필드마다 다른 경로가 나온다. 그러면 22 컬럼짜리 산출물에서 항목이 22 개로
    불어나고 목록이 읽히지 않는다.

    뒤쪽 4 조각만 남기면 `allOf/0/then/required` 가 되어 **제약의 정체**가 남고
    필드 이름은 빠진다. 어느 파일인지는 목록의 키가 말해 준다.
    """
    parts = [str(part) for part in error.absolute_schema_path]  # type: ignore[attr-defined]
    return "/".join(parts[-4:])


def _jsonschema_available() -> bool:
    try:
        import jsonschema  # noqa: F401
        import referencing  # noqa: F401
    except ImportError:
        return False
    return True


NEEDS_JSONSCHEMA = (
    "BLOCKED: jsonschema/referencing 미설치 — 전체 스키마 검증을 실행하지 않았다. "
    "`pip install -r requirements-dev.txt` (D-21: dev 전용)"
)


# ── 아래층 — 의존성 없이 돈다 ───────────────────────────────────────────────

def _not_required(keys: list[str], instance: dict) -> bool:
    """`{"not": {"required": [...]}}` 의 판정.

    `required: [a, b]` 는 *"둘 다 있다"* 이므로 그 부정은 *"둘 다 있지는 않다"* 다.
    **하나만 있으면 통과한다** — 이것이 F-F 회귀의 전부다.
    """
    return not all(key in instance for key in keys)


def _not_anyof(keysets: list[list[str]], instance: dict) -> bool:
    """`{"not": {"anyOf": [{"required": [a]}, {"required": [b]}]}}` 의 판정.

    *"둘 중 하나라도 있으면 안 된다"* — 우리가 원하는 의미다.
    """
    return not any(all(key in instance for key in keys) for keys in keysets)


class TestUncomputableBranchLogic(unittest.TestCase):
    """★★ AC-4e — 계산 불가 분기의 `not` 형태. **`jsonschema` 없이도 돈다.**

    `basis` 의 유무가 *"측정됨"* 의 판별자다 (`ADR-0003`). 계산 불가에 `basis` 가
    붙으면 근거 없는 값이 근거 있는 값으로 읽힌다 — **USP-1 이 무너지는 정확한
    지점**이고, 자연스러운 한 줄 편집으로 사라진다.
    """

    def setUp(self) -> None:
        common = _load(CONTRACTS / "common.schema.json")
        clause = common["$defs"]["metric_value"]["allOf"][2]
        # 이 절이 정말 계산 불가 3종의 절인지 먼저 확인한다. allOf 순서가 바뀌면
        # 엉뚱한 절을 검사하면서 초록으로 보이게 된다.
        self.assertEqual(
            {"unavailable", "blocked", "not_run"},
            set(clause["if"]["properties"]["status"]["enum"]),
            "allOf[2] 가 계산 불가 분기가 아니다 — 절 순서가 바뀌었다",
        )
        self.not_clause = clause["then"]["not"]

    def test_contract_uses_anyof_not_a_required_array(self) -> None:
        """계약이 `anyOf` 형태인가. `required` 배열이면 즉시 실패한다."""
        self.assertIn(
            "anyOf", self.not_clause,
            '계산 불가 분기의 not 이 anyOf 가 아니다. {"required":["basis",'
            '"value_formatted"]} 로 쓰면 "둘 다 있지는 않다" 가 되어 basis 만 있는 '
            "레코드가 통과하고, W2 가 세운 basis 금지가 조용히 사라진다",
        )
        self.assertNotIn("required", self.not_clause)
        self.assertEqual(
            [["basis"], ["value_formatted"]],
            [branch["required"] for branch in self.not_clause["anyOf"]],
        )

    def test_each_forbidden_key_is_rejected_individually(self) -> None:
        """★ 네 레코드. ③이 `거부` 여야 한다 — 여기가 회귀 지점이다."""
        keysets = [branch["required"] for branch in self.not_clause["anyOf"]]
        cases = [
            ("① 둘 다 없음", {}, True),
            ("② value_formatted 있음", {"value_formatted": "0원"}, False),
            ("③ ★ basis 있음", {"basis": {"population": "P"}}, False),
            ("④ 둘 다 있음",
             {"basis": {"population": "P"}, "value_formatted": "0원"}, False),
        ]
        for label, instance, expected_pass in cases:
            with self.subTest(case=label):
                self.assertIs(
                    expected_pass, _not_anyof(keysets, instance),
                    f"{label} 의 판정이 의도와 다르다",
                )

    def test_the_wrong_form_would_let_basis_through(self) -> None:
        """틀린 형태가 ③을 통과시킨다는 사실도 함께 고정한다.

        이 단언이 없으면 `test_each_forbidden_key_is_rejected_individually` 가
        *"왜 anyOf 여야 하는지"* 를 설명하지 못한다. 둘이 짝이다.
        """
        basis_only = {"basis": {"population": "P"}}
        self.assertTrue(
            _not_required(["basis", "value_formatted"], basis_only),
            "틀린 형태가 basis 만 있는 레코드를 통과시킨다는 것이 F-F 의 내용이다",
        )
        self.assertFalse(_not_anyof([["basis"], ["value_formatted"]], basis_only))


class TestVacuousClauseIsReplacedNotAdded(unittest.TestCase):
    """★ F-E — `vacuous` 절은 **교체**됐다. 추가하면 만족 불가능해진다.

    `jsonschema` 없이 구조로 확인한다: `vacuous` 를 다루는 절이 **하나뿐**이고,
    그 하나가 `reason_code` 를 `required` 에서 빼고 `not` 으로 금지해야 한다.
    두 절이 같은 `status` 를 다루면 한쪽은 요구하고 한쪽은 금지하게 된다.
    """

    def setUp(self) -> None:
        items = _load(CONTRACTS / "data_quality_report.schema.json")
        self.clauses = items["properties"]["checks"]["items"]["allOf"]

    def _vacuous_clauses(self) -> list[dict]:
        return [
            c for c in self.clauses
            if c.get("if", {}).get("properties", {}).get("status", {}).get("const")
            == "vacuous"
        ]

    def test_exactly_one_clause_governs_vacuous(self) -> None:
        found = self._vacuous_clauses()
        self.assertEqual(
            1, len(found),
            "vacuous 를 다루는 절이 하나가 아니다. 절을 '추가' 하면 reason_code 가 "
            "있으면 새 절이 거부하고 없으면 현행 절이 거부해 vacuous 가 무엇을 써도 "
            "실패한다 — empty-sink 의 vacuous 7건이 오늘의 정상 상태인데 게시 불가가 "
            f"된다 (발견: {len(found)}개 절)",
        )

    def test_vacuous_forbids_reason_code_and_does_not_require_it(self) -> None:
        then = self._vacuous_clauses()[0]["then"]
        self.assertNotIn(
            "reason_code", then["required"],
            "vacuous 가 아직 reason_code 를 required 로 걸고 있다 — 교체가 안 됐다",
        )
        self.assertEqual({"required": ["reason_code"]}, then.get("not"))
        # status 가 이미 사유이므로 사실 쪽(0행·위반 null)은 그대로 요구한다.
        self.assertIn("examined_rows", then["required"])
        self.assertIn("reason_detail", then["required"])
        self.assertEqual(0, then["properties"]["examined_rows"]["const"])


class TestHeadlineCodeContract(unittest.TestCase):
    """AC-4b · AC-4c — `REJECTED_EVENTS` 추가와 순위의 계약화 (B-11)."""

    def setUp(self) -> None:
        self.index = _load(CONTRACTS / "index.schema.json")
        self.headline = (
            self.index["properties"]["verdict"]["properties"]["headline_code"]
        )

    def test_rejected_events_is_in_the_enum(self) -> None:
        self.assertIn("REJECTED_EVENTS", self.headline["enum"])
        self.assertEqual(8, len(self.headline["enum"]))
        self.assertEqual(
            len(self.headline["enum"]), len(set(self.headline["enum"]))
        )

    def test_snapshot_had_seven_codes(self) -> None:
        """스냅샷이 7종이었다는 사실을 고정한다 — 변경이 실재함의 증거."""
        snapshot = _load(SNAPSHOT / "index.schema.json")
        codes = snapshot["properties"]["verdict"]["properties"]["headline_code"]["enum"]
        self.assertEqual(7, len(codes))
        self.assertNotIn("REJECTED_EVENTS", codes)

    def test_priority_order_is_written_into_the_contract(self) -> None:
        """화면이 순위를 정하지 않게 계약이 순위를 적는다 (DB-012)."""
        description = self.headline["description"]
        for code in self.headline["enum"]:
            with self.subTest(code=code):
                self.assertIn(code, description, f"{code} 의 순위가 적혀 있지 않다")

    def test_rejected_events_blocks_all_clear(self) -> None:
        """`counts.rejected_events > 0` 이면 `ALL_CLEAR` 를 고를 수 없다.

        화면이 `counts` 를 다시 세는 우회를 쓰지 않는 대신 계약이 성립시킨다.
        """
        guards = [
            clause for clause in self.index.get("allOf", [])
            if "ALL_CLEAR" in json.dumps(clause)
        ]
        self.assertEqual(1, len(guards), "ALL_CLEAR 가드가 계약에 없다")
        self.assertEqual(
            {"const": "ALL_CLEAR"},
            guards[0]["then"]["properties"]["verdict"]["properties"]["headline_code"]["not"],
        )


class TestContractAdditions(unittest.TestCase):
    """AC-4b — `value_formatted`(C-1) · `limit_note`(N-8) 가 계약에 있다."""

    def setUp(self) -> None:
        self.metric_value = _load(CONTRACTS / "common.schema.json")["$defs"]["metric_value"]

    def test_value_formatted_is_declared(self) -> None:
        self.assertIn("value_formatted", self.metric_value["properties"])
        # additionalProperties:false 이므로 선언되지 않으면 게시 자체가 불가능하다.
        self.assertIs(False, self.metric_value["additionalProperties"])

    def test_value_formatted_is_required_for_both_computed_statuses(self) -> None:
        """★ `allOf[1]`(`unconfirmed`)을 빠뜨리기 쉽다 — 픽스처에 1건뿐이다."""
        for index, status in ((0, "ok"), (1, "unconfirmed")):
            clause = self.metric_value["allOf"][index]
            with self.subTest(status=status):
                self.assertEqual(
                    status, clause["if"]["properties"]["status"]["const"],
                    f"allOf[{index}] 가 {status} 분기가 아니다 — 절 순서가 바뀌었다",
                )
                self.assertIn("value_formatted", clause["then"]["required"])

    def test_limit_note_is_optional_everywhere(self) -> None:
        """조건부 필수로 만들면 `한계` 없는 지표가 전부 실패한다."""
        self.assertIn("limit_note", self.metric_value["properties"])
        for index, clause in enumerate(self.metric_value["allOf"]):
            with self.subTest(clause=index):
                self.assertNotIn("limit_note", clause["then"].get("required", []))
        # 금지 목록에도 들어가면 안 된다 — 선택 필드는 어느 분기에도 안 나온다.
        forbidden = self.metric_value["allOf"][2]["then"]["not"]["anyOf"]
        self.assertNotIn(
            ["limit_note"], [branch["required"] for branch in forbidden]
        )


class TestContractCopyDiffersOnlyAsDocumented(unittest.TestCase):
    """T6 — 사본과 스냅샷의 차이가 **changelog 에 등재된 것뿐**이다.

    바이트 일치를 요구하지 않는다(의도된 차이가 4건 있다). 대신 **등재되지 않은
    차이가 생기면 실패**하게 한다 — 두 벌이 조용히 갈라지는 것을 막는 장치다.
    """

    #: 스냅샷 대비 의도된 차이. 여기 없는 차이가 나오면 실패한다.
    #: 값은 '그 파일에서 달라져도 되는 최상위 경로' 집합이다.
    DOCUMENTED = {
        "index.schema.json": {
            "$comment",
            "properties.verdict.properties.headline_code.enum",
            "properties.verdict.properties.headline_code.description",
            "allOf",
            # 이슈 #60 — counts 에 freeze_mismatch 가 없어 FREEZE_MISMATCH 판정이
            # 계약상 도달 불가였다. 읽는 쪽이 additionalProperties:false 로 금지된
            # 키를 보고 있었다.
            "properties.verdict.properties.counts.properties.freeze_mismatch.type",
            "properties.verdict.properties.counts.properties.freeze_mismatch.minimum",
            "properties.verdict.properties.counts.properties.freeze_mismatch.description",
            "properties.verdict.properties.counts.required.8",
            # 이름이 세는 것과 다르다는 사실을 description 에 적었다. 이름 자체의
            # 정정은 호환 파괴라 별도로 다룬다.
            "properties.verdict.properties.counts.properties.lock_items_pending.description",
        },
        "common.schema.json": {
            "$comment",
            "$defs.metric_value.properties.value_formatted",
            "$defs.metric_value.properties.limit_note",
            "$defs.metric_value.allOf.0.then.required",
            "$defs.metric_value.allOf.1.then.required",
            "$defs.metric_value.allOf.2.then.not",
            "$defs.metric_value.allOf.2.$comment",
        },
        "data_quality_report.schema.json": {
            "$comment",
            "properties.checks.items.allOf.2.then.required",
            "properties.checks.items.allOf.2.then.not",
            "properties.checks.items.allOf.2.$comment",
            "properties.checks.items.allOf.5",
            "properties.checks.items.allOf.6",
        },
        "field_coverage_report.schema.json": {"$comment"},
        "freeze_status.schema.json": {
            "$comment",
            # 이슈 #60 — 대조 결과가 게시물로 나가지 않아 봉인 변조 경보가
            # 작동한 적이 없었다. verify() 는 처음부터 이 값을 들고 있었다.
            "properties.verification.type",
            "properties.verification.description",
            "properties.verification.enum.0",
            "properties.verification.enum.1",
            "properties.verification.enum.2",
            "properties.verification.enum.3",
            "properties.mismatches.type",
            "properties.mismatches.description",
            "properties.mismatches.items.type",
            "required.11",
        },
        "ingestion_report.schema.json": {"$comment"},
        "kpi_report.schema.json": {"$comment"},
        "rejection_report.schema.json": {"$comment"},
    }

    #: ★ W2 동결 스냅샷에 **없는** 계약. 조용히 늘어나는 길을 막으려고 여기에
    #: 이름과 사유를 적게 한다 — 적지 않으면 아래 테스트가 실패한다.
    #:
    #: 동결본에 소급 추가하지 않는 이유: 그것은 W2 가 무엇을 설계했는지의 기록이고,
    #: 고치면 "그때도 있었다" 가 거짓이 된다. 차이를 지우는 대신 **선언**한다.
    ADDED_AFTER_W2 = {
        "manifest.schema.json": (
            "게시의 입력(Sink manifest) 계약. W2 는 게시가 내보내는 산출물 8종만 "
            "설계했고 읽어들이는 입력에는 계약을 두지 않았다 — 그 비대칭이 리뷰 M1 의 "
            "결함이며 이슈 #59 로 닫는다."
        ),
    }

    @staticmethod
    def _flatten(node: object, prefix: str = "") -> dict[str, object]:
        """모든 잎을 `a.b.0.c` 형태의 경로로 펼친다."""
        out: dict[str, object] = {}
        if isinstance(node, dict):
            for key, value in node.items():
                out.update(
                    TestContractCopyDiffersOnlyAsDocumented._flatten(
                        value, f"{prefix}.{key}" if prefix else key
                    )
                )
        elif isinstance(node, list):
            for index, value in enumerate(node):
                out.update(
                    TestContractCopyDiffersOnlyAsDocumented._flatten(
                        value, f"{prefix}.{index}"
                    )
                )
        else:
            out[prefix] = node
        return out

    def test_every_schema_file_was_copied(self) -> None:
        """스냅샷의 것은 하나도 빠지지 않았고, 늘어난 것은 전부 선언돼 있다."""
        snapshot = {p.name for p in SNAPSHOT.glob("*.schema.json")}
        contracts = {p.name for p in CONTRACTS.glob("*.schema.json")}
        self.assertEqual(
            set(), snapshot - contracts,
            "W2 가 설계한 계약이 사라졌다 — 스냅샷에 있는데 계약 디렉터리에 없다",
        )
        self.assertEqual(
            set(self.ADDED_AFTER_W2), contracts - snapshot,
            "W2 이후 추가된 계약은 ADDED_AFTER_W2 에 사유와 함께 선언해야 한다 — "
            "조용히 늘어나는 것을 막는다",
        )

    def test_added_schemas_declare_a_reason(self) -> None:
        """선언만 하고 사유를 비워 두면 선언이 아니다."""
        for name, reason in self.ADDED_AFTER_W2.items():
            with self.subTest(schema=name):
                self.assertTrue(
                    reason.strip(),
                    f"{name}: 왜 W2 가 이 계약을 설계하지 않았는지가 비어 있다",
                )
                self.assertTrue(
                    (CONTRACTS / name).is_file(),
                    f"{name}: 선언은 있는데 파일이 없다",
                )

    def test_copies_carry_provenance_comment(self) -> None:
        """JSON 에 주석을 쓸 수 없으므로 `$comment` 로 출처를 남긴다 (N-7)."""
        for path in sorted(CONTRACTS.glob("*.schema.json")):
            with self.subTest(schema=path.name):
                comment = _load(path).get("$comment", "")
                self.assertIn(".agent-team/04-architecture/schemas", comment)
                if path.name in self.ADDED_AFTER_W2:
                    # 스냅샷에서 온 것이 아니므로 "복사본" 이라고 적을 수 없다.
                    # 대신 **스냅샷에 없다는 사실**을 같은 자리에 적게 한다.
                    self.assertIn("없는", comment)
                    continue
                self.assertIn(path.name, comment)

    def test_no_undocumented_difference(self) -> None:
        for path in sorted(CONTRACTS.glob("*.schema.json")):
            if path.name in self.ADDED_AFTER_W2:
                continue  # 대조할 스냅샷 원본이 없다 (위 테스트가 선언을 강제한다)
            allowed = self.DOCUMENTED[path.name]
            before = self._flatten(_load(SNAPSHOT / path.name))
            after = self._flatten(_load(path))
            changed = {
                key for key in set(before) | set(after)
                if before.get(key, object()) != after.get(key, object())
            }
            undocumented = sorted(
                key for key in changed
                if not any(key == a or key.startswith(a + ".") for a in allowed)
            )
            with self.subTest(schema=path.name):
                self.assertEqual(
                    [], undocumented,
                    f"{path.name} 에 changelog 에 없는 차이가 있다. 의도한 변경이면 "
                    "CHANGELOG.md 와 DOCUMENTED 에 등재하고, 아니면 되돌린다:\n"
                    + "\n".join(undocumented),
                )

    def test_snapshot_is_untouched(self) -> None:
        """`.agent-team/` 원본은 동결 스냅샷이다 — 고치지 않는다."""
        snapshot_common = _load(SNAPSHOT / "common.schema.json")["$defs"]["metric_value"]
        self.assertNotIn(
            "value_formatted", snapshot_common["properties"],
            "스냅샷을 고쳤다. W5 정본은 docs/contracts/ 이고 스냅샷은 대조 기준이다",
        )
        self.assertEqual(
            {"required": ["basis"]}, snapshot_common["allOf"][2]["then"]["not"]
        )


# ── 위층 — `jsonschema` 가 필요하다 ─────────────────────────────────────────

#: ★★ §4.14 — 픽스처가 **일부러 실패한다.** 그 실패가 계약이 물었다는 증거다.
#:
#: 모르고 보면 *"제약을 빼자"* 로 간다. 그래서 **목록의 모든 항목이 실제로 실패하는지**
#: 를 단언한다 — 통과해 버리면 제약이 안 걸린 것이다. **개수를 적지 않는다**: 항목이
#: 늘면 숫자가 어긋나고, 세지 않은 항목은 통과해도 모른다. dict 를 순회한다.
#:
#: **픽스처를 고치지 않는다.** W2 산출물이고, `commerce-connected` 의 11종 누락은
#: 그 스냅샷의 알려진 결함이다 (CR-2) — 정답으로 삼지 않는다.
INTENDED_FIXTURE_FAILURES: dict[str, dict[str, str]] = {
    "empty-sink/ingestion_report.json": {
        "required:allOf/0/then/required":
            "C-1 — 픽스처가 value_formatted 보다 먼저 만들어졌다 (metric_value 의 "
            "ok 분기). totals·by_event_type 16종·by_source 전부가 같은 원인이다",
    },
    "empty-sink/kpi_report.json": {
        "anyOf:items/properties/value/anyOf":
            "C-1 — metrics[].value 는 metric_value 와 kpi_source_split 의 anyOf 다. "
            "두 분기가 모두 value_formatted 를 요구하게 되어 anyOf 자체가 실패한다",
    },
    "empty-sink/rejection_report.json": {
        "required:allOf/0/then/required":
            "C-1 — totals 의 metric_value 에 value_formatted 가 없다",
    },
    "empty-sink/data_quality_report.json": {
        "not:allOf/2/then/not":
            "★ F-E — vacuous 7건이 reason_code:NOT_RUN 을 담고 있다. 교체된 절이 "
            "그것을 금지한다. W3 이 '7건 전부 거부' 로 예측한 그대로이며 등재 "
            "항목이므로 회귀가 아니다 (DQ-01·02b·04·07·08·10·11)",
        "enum:then/properties/reason_code/enum":
            "★ Q-2 — DQ-06 이 status:not_run + reason_code:BLOCKED 다. '안 했다' 를 "
            "'못 했다' 로 적은 조합이고, 새 제약이 정확히 그것을 거부한다",
    },
    "commerce-connected/ingestion_report.json": {
        "required:allOf/0/then/required": "C-1 — 위와 같다 (ok 분기)",
    },
    "commerce-connected/field_coverage_report.json": {
        "required:allOf/0/then/required":
            "C-1 — fields[].fill_rate 22개 전부가 value_formatted 를 갖지 않는다",
    },
    "commerce-connected/kpi_report.json": {
        "anyOf:items/properties/value/anyOf": "C-1 — 위와 같다",
        "required:allOf/0/then/required": "C-1 — ok 분기",
        "required:allOf/1/then/required":
            "★ C-1 — unconfirmed 분기. 픽스처 14파일에 unconfirmed 가 1건뿐이라 "
            "allOf[1] 을 빠뜨리면 조용히 통과한다. 이 항목이 그 자리를 지킨다",
    },
    "commerce-connected/rejection_report.json": {
        "required:allOf/0/then/required": "C-1 — totals 의 metric_value",
    },
}

ARTIFACT_SCHEMA = {
    "index.json": "index",
    "ingestion_report.json": "ingestion_report",
    "rejection_report.json": "rejection_report",
    "field_coverage_report.json": "field_coverage_report",
    "kpi_report.json": "kpi_report",
    "data_quality_report.json": "data_quality_report",
    "freeze_status.json": "freeze_status",
}


@unittest.skipUnless(_jsonschema_available(), NEEDS_JSONSCHEMA)
class TestFixturesAgainstContract(unittest.TestCase):
    """픽스처 14파일 × 수정 후 스키마 전수 (R-1 · R-2 · R-3 · R-4 를 닫는다)."""

    @classmethod
    def setUpClass(cls) -> None:
        from referencing import Registry, Resource

        resources = []
        for path in sorted(CONTRACTS.glob("*.schema.json")):
            schema = _load(path)
            resources.append((schema["$id"], Resource.from_contents(schema)))
        cls.registry = Registry().with_resources(resources)

    def _errors(self, fixture: Path, artifact: str) -> set[str]:
        """실패를 `validator:schema_path` 로 요약한다.

        구체적 인스턴스 경로(22 컬럼 각각)까지 목록화하면 항목이 수십 개가 되고
        읽히지 않는다. **무엇이 왜 실패했는가**는 이 요약으로 충분하다.
        """
        from jsonschema import Draft202012Validator

        validator = Draft202012Validator(
            {"$ref": f"{BASE_URI}{artifact}.schema.json"}, registry=self.registry
        )
        return {
            f"{error.validator}:" + _constraint_path(error)
            for error in validator.iter_errors(_load(fixture))
        }

    def _fixtures(self) -> list[tuple[str, Path, str]]:
        found = []
        for directory in sorted(EXAMPLES.iterdir()):
            if not directory.is_dir():
                continue
            for fixture in sorted(directory.glob("*.json")):
                artifact = ARTIFACT_SCHEMA.get(fixture.name)
                self.assertIsNotNone(
                    artifact, f"{fixture.name} 에 대응하는 스키마가 없다"
                )
                found.append((f"{directory.name}/{fixture.name}", fixture, artifact))
        return found

    def test_all_fourteen_fixtures_are_checked(self) -> None:
        """대상 집합을 먼저 본다 — *"남은 것 0건"* 이 범위가 좁아서 나온 0 이 아니게."""
        self.assertEqual(14, len(self._fixtures()))

    def test_fixtures_fail_only_where_intended(self) -> None:
        """의도된 실패 **밖에서는** 전부 통과한다."""
        for key, fixture, artifact in self._fixtures():
            intended = set(INTENDED_FIXTURE_FAILURES.get(key, {}))
            with self.subTest(fixture=key):
                unexpected = sorted(self._errors(fixture, artifact) - intended)
                self.assertEqual(
                    [], unexpected,
                    f"{key} 에 의도하지 않은 계약 위반이 있다. 계약 수정이 과하게 "
                    "물었거나 픽스처가 정말 어긋난 것이다 — 제약을 빼기 전에 어느 "
                    "쪽인지 먼저 판정한다:\n" + "\n".join(unexpected),
                )

    def test_every_intended_failure_actually_fails(self) -> None:
        """★★ 목록의 **모든** 항목이 실제로 실패하는지. 통과하면 제약이 안 걸렸다.

        *"실패해야 실패한다"* — 검사를 만들면 그 검사가 계기를 잡는지부터 확인한다.
        개수로 세지 않고 dict 를 순회하므로, 항목을 추가하고 구현을 빠뜨리면 잡힌다.
        """
        observed = {
            key: self._errors(fixture, artifact)
            for key, fixture, artifact in self._fixtures()
        }
        for key, expectations in INTENDED_FIXTURE_FAILURES.items():
            self.assertIn(key, observed, f"{key} 픽스처가 없다 — 목록이 낡았다")
            for reason, why in expectations.items():
                with self.subTest(fixture=key, reason=reason):
                    self.assertIn(
                        reason, observed[key],
                        f"{key} 가 '{reason}' 로 실패하지 않았다. 의도된 실패로 "
                        f"등재했는데 통과했다면 제약이 걸리지 않은 것이다.\n사유: {why}",
                    )

    def test_snapshot_accepted_every_fixture(self) -> None:
        """★ 수정 **전** 스냅샷에서는 14파일 전부 통과했음을 고정한다.

        그래서 위 실패 전부가 **이번 계약 수정이 만든 것**이고, 픽스처의 기존 결함과
        섞이지 않는다. 이 단언이 없으면 "원래 깨져 있었다"로 넘길 수 있다.
        """
        from jsonschema import Draft202012Validator
        from referencing import Registry, Resource

        resources = []
        for path in sorted(SNAPSHOT.glob("*.schema.json")):
            schema = _load(path)
            resources.append((schema["$id"], Resource.from_contents(schema)))
        registry = Registry().with_resources(resources)

        for key, fixture, artifact in self._fixtures():
            validator = Draft202012Validator(
                {"$ref": f"{BASE_URI}{artifact}.schema.json"}, registry=registry
            )
            with self.subTest(fixture=key):
                self.assertEqual(
                    [], [e.message for e in validator.iter_errors(_load(fixture))]
                )


@unittest.skipUnless(_jsonschema_available(), NEEDS_JSONSCHEMA)
class TestMetricValueBranchesWithValidator(unittest.TestCase):
    """AC-4d — 네 레코드와 `vacuous` 를 **실제 validator** 로 돌린다.

    위의 `TestUncomputableBranchLogic` 은 `not` 절만 논리로 본다. 여기서는 스키마
    전체를 태워 `$ref` 해석·`additionalProperties`·정규식까지 함께 확인한다.
    """

    BASIS = {
        "population": "P_buyer(D)",
        "denominator_definition": "분모 없음 (합계)",
        "window": {"direction": "none"},
    }

    @classmethod
    def setUpClass(cls) -> None:
        from jsonschema import Draft202012Validator
        from referencing import Registry, Resource

        resources = []
        for path in sorted(CONTRACTS.glob("*.schema.json")):
            schema = _load(path)
            resources.append((schema["$id"], Resource.from_contents(schema)))
        cls.metric_value = Draft202012Validator(
            {"$ref": f"{BASE_URI}common.schema.json#/$defs/metric_value"},
            registry=Registry().with_resources(resources),
        )
        cls.check_item = Draft202012Validator(
            {"$ref": f"{BASE_URI}data_quality_report.schema.json"
                     "#/properties/checks/items"},
            registry=Registry().with_resources(resources),
        )

    def _uncomputable(self, **extra: object) -> dict:
        return {
            "status": "unavailable", "value": None,
            "reason_code": "NO_COST_BASIS",
            "reason_detail": "주문 12건 전부 unit_cost 없음",
            **extra,
        }

    def test_basis_is_still_forbidden_on_uncomputable(self) -> None:
        """★★ 회귀 지점. *"고쳤다"* 가 아니라 *"기존 방어가 그대로다"* 를 증명한다."""
        self.assertFalse(
            self.metric_value.is_valid(self._uncomputable(basis=self.BASIS)),
            "계산 불가에 basis 가 통과한다 — 근거 없는 값이 근거 있는 값으로 읽힌다",
        )

    def test_value_formatted_is_forbidden_on_uncomputable(self) -> None:
        self.assertFalse(
            self.metric_value.is_valid(self._uncomputable(value_formatted="0원"))
        )

    def test_clean_uncomputable_passes(self) -> None:
        """제약이 과하게 물지 않았는지 — 정상 레코드는 통과해야 한다."""
        self.assertTrue(self.metric_value.is_valid(self._uncomputable()))

    def test_zero_fill_is_rejected(self) -> None:
        """`value: 0` 은 계산 불가에서 거부된다 — USP-1 의 스키마 표현."""
        self.assertFalse(
            self.metric_value.is_valid(dict(self._uncomputable(), value=0))
        )

    def test_computed_requires_value_formatted(self) -> None:
        computed = {"status": "ok", "value": 38400, "unit": "krw", "basis": self.BASIS}
        self.assertFalse(self.metric_value.is_valid(computed))
        self.assertTrue(
            self.metric_value.is_valid(dict(computed, value_formatted="38,400원"))
        )

    def test_unconfirmed_requires_value_formatted(self) -> None:
        """`allOf[1]` — 픽스처에 1건뿐이라 빠뜨리기 쉬운 자리다."""
        unconfirmed = {
            "status": "unconfirmed", "value": 2130.0, "unit": "krw_per_customer",
            "basis": self.BASIS, "reason_code": "PARAM_UNCONFIRMED",
            "reason_detail": "쿠폰 사용률이 미확정이다",
            "params_used": {"coupon_use_rate": 0.30},
        }
        self.assertFalse(self.metric_value.is_valid(unconfirmed))
        self.assertTrue(
            self.metric_value.is_valid(dict(unconfirmed, value_formatted="2,130원/인"))
        )

    def test_limit_note_is_accepted_and_optional(self) -> None:
        computed = {
            "status": "ok", "value": 1204, "unit": "count", "basis": self.BASIS,
            "value_formatted": "1,204건",
        }
        self.assertTrue(self.metric_value.is_valid(computed))
        self.assertTrue(
            self.metric_value.is_valid(
                dict(computed, limit_note="쿠폰 사용 이벤트만 센다")
            )
        )

    def _check(self, **extra: object) -> dict:
        return {
            "id": "DQ-01", "spec_ref": "data_spec §9", "title": "이벤트 스키마 일치",
            "status": "vacuous", "examined_rows": 0, "violations": None,
            "reason_detail": "검사 대상이 0행이었다", "scope": "events", **extra,
        }

    def test_vacuous_without_reason_code_passes(self) -> None:
        """★ 오늘의 정상 상태가 게시 가능해야 한다 (F-E)."""
        self.assertTrue(self.check_item.is_valid(self._check()))

    def test_vacuous_with_reason_code_is_rejected(self) -> None:
        """둘 다 확인한다 — 하나만 보면 만족 불가능해진 것을 못 잡는다."""
        self.assertFalse(
            self.check_item.is_valid(self._check(reason_code="NOT_RUN"))
        )

    def test_blocked_and_not_run_reason_codes_are_constrained(self) -> None:
        """Q-2 — 안 한 것(`not_run`)을 못 한 것(`BLOCKED`)으로 적을 수 없다."""
        cases = [
            ({"status": "blocked", "reason_code": "BLOCKED"}, True),
            ({"status": "blocked", "reason_code": "NOT_RUN"}, False),
            ({"status": "not_run", "reason_code": "NOT_RUN"}, True),
            ({"status": "not_run", "reason_code": "PRECONDITION_MISSING"}, True),
            ({"status": "not_run", "reason_code": "BLOCKED"}, False),
        ]
        for overrides, expected in cases:
            with self.subTest(**overrides):
                self.assertIs(
                    expected, self.check_item.is_valid(self._check(**overrides))
                )


if __name__ == "__main__":
    unittest.main()
