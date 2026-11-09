"""게시 파이프라인 — 조립 · 순위 · 원자성 · 보안 (M-06 T3·T4·T7·T8).

★ **J-1 — 대표 장면 fixture 는 손으로 쓴 JSON 이 아니라 실제 파이프라인 산출물이다.**
`TestRepresentativeScene` 이 `EventSink` 로 실제 이벤트를 쓰고 `publish()` 를 돌려
나온 게시물을 검사한다. 손으로 쓴 기대값을 두면 구현과 기대가 함께 틀릴 수 있다.

`PyYAML` 이 없으면 `publish()` 경로가 `ConfigError` 로 멈추므로 그 테스트들은
**skip + 사유**를 남긴다 — 조립·순위·보안 함수는 순수 함수라 의존성 없이 돈다.

실행:
    python3 -m unittest tests.test_publish_pipeline -v
"""

from __future__ import annotations

import contextlib
import io
import json
import tempfile
import unittest
import uuid
from datetime import date, datetime, timedelta
from pathlib import Path

from src.measurement import publish as pub
from src.measurement import schema as sc
from src.measurement.config_loader import yaml_available
from src.measurement.sink import EventSink

REPO_ROOT = Path(__file__).resolve().parents[1]
NEEDS_YAML = (
    "BLOCKED: PyYAML 미설치 — publish() 가 경제 규칙 config 를 읽어야 하고 "
    "자체 파서로 폴백하지 않으므로 게시 경로를 검증하지 않았다"
)


def simulator_event(
    event_type: sc.EventType = sc.EventType.SESSION_START,
    *, day: int = 1, **overrides: object,
) -> dict[str, object]:
    record: dict[str, object] = {
        "event_id": str(uuid.uuid4()),
        "customer_id": "C00012345",
        "timestamp": f"2025-10-{day:02d}T09:00:00.000+09:00",
        "event_type": event_type.value,
        "simulator_version": "sim-1.0",
        "random_seed": 42,
    }
    filler: dict[str, object] = {
        "session_id": "S-C00012345-1759276800000", "page_type": "home",
        "product_id": "P0042", "category": "fresh_food", "quantity": 1,
        "unit_price": 8900, "order_id": "O20251001-000123",
        "order_amount": 47000, "coupon_id": "CPN-A1B2C3",
        "campaign_id": "CMP-20251001-001",
    }
    for name in sc.required_fields(event_type) - sc.CORE_FIELDS:
        record[name] = filler[name]
    record.update(overrides)
    return record


def commerce_event(*args: object, **overrides: object) -> dict[str, object]:
    record = simulator_event(*args, **overrides)  # type: ignore[arg-type]
    record.pop("simulator_version", None)
    record.pop("random_seed", None)
    return record


# ── 출처 분할 · 조립 (의존성 없이 돈다) ─────────────────────────────────────

class TestSourcePartition(unittest.TestCase):
    """N-3 — 출처별 결과는 분기가 아니라 입력 분할로 얻는다."""

    def test_both_keys_exist_even_when_empty(self) -> None:
        """★ 0건이어도 빼지 않는다 — 빼면 그 출처가 화면에서 사라진다."""
        split = pub.partition_by_source([])
        self.assertEqual((), split.commerce)
        self.assertEqual((), split.simulator)
        self.assertEqual(
            {"commerce", "simulator"}, {name for name, _ in split.items()}
        )

    def test_split_uses_sink_classification(self) -> None:
        split = pub.partition_by_source(
            [simulator_event(), commerce_event(), commerce_event()]
        )
        self.assertEqual(1, len(split.simulator))
        self.assertEqual(2, len(split.commerce))

    def test_publish_is_the_only_module_naming_sources(self) -> None:
        """계산층은 출처를 모른다 — `test_neutrality.py` 와 짝이다."""
        for module in ("economics.py", "kpi.py"):
            source = (REPO_ROOT / "src" / "measurement" / module).read_text(
                encoding="utf-8")
            with self.subTest(module=module):
                self.assertNotIn("commerce", source.lower())


class TestOrderAssembly(unittest.TestCase):
    """m-03 §4.7b — 조립은 출처를 아는 층에서 한다."""

    def test_items_are_always_empty_in_c1(self) -> None:
        """★ C1 의 정상 경로다. `purchase` 는 주문 단위 1행이다."""
        orders = pub.assemble_orders([simulator_event(sc.EventType.PURCHASE)])
        self.assertEqual(1, len(orders))
        self.assertEqual((), orders[0].items)

    def test_assembled_order_yields_no_cost_basis(self) -> None:
        """조립 결과가 `NO_COST_BASIS` 를 내는 것이 USP-1 대표 장면의 내용이다."""
        from src.measurement import economics as ec

        orders = pub.assemble_orders([simulator_event(sc.EventType.PURCHASE)])
        self.assertFalse(ec.has_cost_basis(orders[0]))
        self.assertIs(sc.MetricStatus.UNAVAILABLE, ec.cogs(orders[0]).status)

    def test_order_without_amount_is_not_assembled(self) -> None:
        """★ 결손을 0 으로 채우지 않는다. 조립하지 않고 DQ-11 이 잡게 둔다."""
        broken = simulator_event(sc.EventType.PURCHASE)
        del broken["order_amount"]
        self.assertEqual((), pub.assemble_orders([broken]))

    def test_coupon_use_marks_the_order(self) -> None:
        """EC-3 2원칙 — 쿠폰이 실제 사용된 주문만 할인 비용을 진다."""
        order_id = "O20251001-000123"
        orders = pub.assemble_orders([
            simulator_event(sc.EventType.PURCHASE, order_id=order_id),
            simulator_event(sc.EventType.COUPON_USE, order_id=order_id),
        ])
        self.assertTrue(orders[0].has_coupon_use)

    def test_campaign_separates_sends_from_customers(self) -> None:
        """EC-4 — 같은 고객에게 두 번 발송하면 메시지 2건, `N_targeted` 1명."""
        campaign = pub.assemble_campaign([
            simulator_event(sc.EventType.PUSH_SENT),
            simulator_event(sc.EventType.PUSH_SENT),
        ])
        self.assertEqual(2, campaign.messages_sent)
        self.assertEqual(1, campaign.targeted_customers)


# ── ★ headline_code 순위 (AC-4c) ────────────────────────────────────────────

class TestHeadlinePriority(unittest.TestCase):
    """★ 순위를 **기계가 검사한다.** enum 소속 검사로는 순위를 못 잡는다."""

    EMPTY = {
        "quality_violations": 0, "checks_not_run": 0, "checks_blocked": 0,
        "metrics_unavailable": 0, "metrics_not_run": 0, "schema_gaps": 0,
        "lock_items_pending": 0, "rejected_events": 0,
    }

    def test_priority_list_matches_the_contract_enum_order(self) -> None:
        """★ 순위를 두 곳에 적으면 갈라진다. 계약 파일에서 읽어 대조한다."""
        schema = json.loads(
            (REPO_ROOT / "docs/contracts/measurement-publish/v1"
             / "index.schema.json").read_text(encoding="utf-8")
        )
        enum = schema["properties"]["verdict"]["properties"]["headline_code"]["enum"]
        self.assertEqual(list(pub.HEADLINE_PRIORITY), enum)

    def test_all_clear_when_nothing_is_wrong(self) -> None:
        self.assertEqual(
            "ALL_CLEAR",
            pub.choose_headline_code(
                self.EMPTY, events_ingested={"status": "ok", "value": 10}
            ),
        )

    def test_every_code_is_reachable(self) -> None:
        """★ 표본 밖 8종 전부를 `counts` 를 지어내 통과시킨다.

        도달할 수 없는 코드가 enum 에 있으면 화면이 그릴 수 없는 상태를 그린다.
        """
        cases = {
            "CONTRACT_VIOLATION": (dict(self.EMPTY), {"contract_violation": True}),
            "FREEZE_MISMATCH": (
                dict(self.EMPTY, lock_items_pending=1, freeze_mismatch=1), {}),
            "QUALITY_VIOLATION": (dict(self.EMPTY, quality_violations=1), {}),
            "REJECTED_EVENTS": (dict(self.EMPTY, rejected_events=3), {}),
            "SINK_EMPTY": (
                dict(self.EMPTY),
                {"events_ingested": {"status": "ok", "value": 0}}),
            "CHECKS_NOT_RUN": (dict(self.EMPTY, checks_not_run=2), {}),
            "METRICS_UNAVAILABLE": (dict(self.EMPTY, metrics_unavailable=5), {}),
            "ALL_CLEAR": (
                dict(self.EMPTY),
                {"events_ingested": {"status": "ok", "value": 10}}),
        }
        self.assertEqual(
            set(pub.HEADLINE_PRIORITY), set(cases), "도달 검사에 빠진 코드가 있다"
        )
        for expected, (counts, extra) in cases.items():
            with self.subTest(code=expected):
                self.assertEqual(
                    expected, pub.choose_headline_code(counts, **extra)
                )

    def test_rejected_events_outranks_sink_empty(self) -> None:
        """거부가 있으면 수집 0건보다 먼저 말한다 — 순위가 실제로 동작한다."""
        self.assertEqual(
            "REJECTED_EVENTS",
            pub.choose_headline_code(
                dict(self.EMPTY, rejected_events=1),
                events_ingested={"status": "ok", "value": 0},
            ),
        )

    def test_rejected_events_can_never_be_all_clear(self) -> None:
        """★ B-11 — 계약이 금지하고 순위도 막는다. 두 겹이다."""
        self.assertNotEqual(
            "ALL_CLEAR",
            pub.choose_headline_code(dict(self.EMPTY, rejected_events=1)),
        )

    def test_unknown_ingestion_status_does_not_read_as_zero(self) -> None:
        """★★ **모르는 것을 0 으로 읽지 않는다.**

        `events_ingested.status` 가 `ok` 가 아니면 `SINK_EMPTY` 를 고르지 않는다.
        계산 불가인 수집 건수를 0 으로 읽으면 *"수집이 0건이었다"* 고 단정하게 된다.
        """
        self.assertNotEqual(
            "SINK_EMPTY",
            pub.choose_headline_code(
                dict(self.EMPTY),
                events_ingested={"status": "unavailable", "value": None},
            ),
        )

    def test_level_follows_the_code(self) -> None:
        self.assertEqual("violation", pub.headline_level("QUALITY_VIOLATION"))
        self.assertEqual("attention", pub.headline_level("SINK_EMPTY"))
        self.assertEqual("ok", pub.headline_level("ALL_CLEAR"))

    def test_every_code_has_a_detail_sentence(self) -> None:
        """화면 둘째 줄이 비면 사용자가 무엇을 할지 모른다."""
        for code in pub.HEADLINE_PRIORITY:
            with self.subTest(code=code):
                self.assertTrue(pub._headline_detail(code, self.EMPTY).strip())


# ── ★ 보안 — 거부 레코드 원문을 게시하지 않는다 (AC-6) ──────────────────────

class TestRejectionSecurity(unittest.TestCase):
    """★★ `rejected.jsonl` 에는 Hidden Trait 이 **원문으로** 남는다."""

    def test_forbidden_field_values_never_reach_the_artifact(self) -> None:
        """★ 일부러 금지 필드가 담긴 거부 레코드를 만들어 값의 부재를 확인한다.

        거부된 이유가 바로 그 필드의 존재인 경우가 있다. 그 값을 게시하면
        게시물이 `ISO-003`(측정 계층을 통과할 수 없는 값)을 우회하는 통로가 된다.
        """
        leaked = simulator_event()
        leaked["coupon_sensitivity"] = 0.85  # Hidden Trait — 통과할 수 없는 필드
        rejected = [{
            "record": leaked,
            "problems": ["측정 계층을 통과할 수 없는 필드: ['coupon_sensitivity']"],
        }]
        report = pub.build_rejection_report({"rows": 0, "rejected": 1}, rejected)
        serialised = json.dumps(report, ensure_ascii=False)

        # 값이 없어야 한다. 필드 **이름**은 problems 에 남는다 — 그것이 사유다.
        self.assertNotIn("0.85", serialised, "Hidden Trait 값이 게시물에 새어나갔다")
        self.assertNotIn("offending_values", serialised)
        # 이름만 담는 offending_fields 는 22컬럼으로 제한된다.
        for sample in report["samples"]:
            for name in sample["offending_fields"]:
                with self.subTest(field=name):
                    self.assertIn(name, sc.FIELD_INDEX)

    def test_offending_fields_excludes_unknown_columns(self) -> None:
        """금지 필드 이름 자체도 `offending_fields` 에 오지 않는다 — 22컬럼만."""
        leaked = simulator_event()
        leaked["tau"] = 1.0
        report = pub.build_rejection_report(
            {"rows": 0, "rejected": 1},
            [{"record": leaked, "problems": ["측정 계층을 통과할 수 없는 필드: ['tau']"]}],
        )
        self.assertNotIn("tau", report["samples"][0]["offending_fields"])

    def test_reason_keys_are_from_the_contract_enum(self) -> None:
        schema = json.loads(
            (REPO_ROOT / "docs/contracts/measurement-publish/v1"
             / "rejection_report.schema.json").read_text(encoding="utf-8")
        )
        allowed = set(
            schema["properties"]["by_reason"]["items"]["properties"]
            ["reason_key"]["enum"]
        )
        for _, key, _ in pub._REASON_KEYS:
            with self.subTest(key=key):
                self.assertIn(key, allowed)
        self.assertIn("OTHER", allowed)

    def test_unclassified_reason_becomes_other_not_dropped(self) -> None:
        """★ 조용히 버리지 않는다. `OTHER` 가 늘면 매핑 갱신 신호다."""
        key, label = pub.classify_rejection("아무도 예상하지 못한 새 사유")
        self.assertEqual("OTHER", key)
        self.assertTrue(label)

    def test_every_validate_event_message_is_classified(self) -> None:
        """★ `validate_event()` 가 내는 실제 메시지가 전부 분류되는지.

        분류 표를 손으로 적었으므로 실제 메시지와 어긋날 수 있다 — 실물로 본다.
        """
        samples = [
            sc.validate_event({"event_type": "teleport"}),
            sc.validate_event({**simulator_event(), "coupon_sensitivity": 0.5}),
            sc.validate_event({**simulator_event(), "category": "우주선"}),
            sc.validate_event({**simulator_event(), "customer_id": "test-user-1"}),
            sc.validate_event(
                {**simulator_event(), "timestamp": "2025-10-01T23:30:00"}),
            sc.validate_event({**simulator_event(sc.EventType.PUSH_SENT),
                               "product_id": "P0001"}),
            sc.validate_event({**simulator_event(sc.EventType.PURCHASE),
                               "order_amount": -1}),
        ]
        unclassified = []
        for problems in samples:
            self.assertTrue(problems, "위반 표본이 통과했다")
            key, _ = pub.classify_rejection(problems[0])
            if key == "OTHER":
                unclassified.append(problems[0])
        self.assertEqual(
            [], unclassified,
            "validate_event() 의 메시지가 분류되지 않는다 — _REASON_KEYS 갱신이 "
            "필요하다:\n" + "\n".join(unclassified),
        )


# ── 게시 실행 (PyYAML 필요) ─────────────────────────────────────────────────

@unittest.skipUnless(yaml_available(), NEEDS_YAML)
class TestPublishAtomicity(unittest.TestCase):
    """T7 — 원자성. 부분 게시물을 남기지 않는다."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.out = Path(self._tmp.name) / "results"
        self.source = Path(self._tmp.name) / "raw"

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_publish_writes_seven_artifacts(self) -> None:
        outcome = pub.publish(
            source_root=self.source, output_root=self.out,
            config_path=REPO_ROOT / "config/economic_config.yaml",
        )
        self.assertEqual("ok", outcome.publish_result)
        self.assertEqual(0, outcome.exit_code)
        # ★ rglob 이다. ADR-0002 로 6종이 measurement/ 아래로 내려갔고,
        #   glob("*.json") 은 루트의 data_quality_report.json 하나만 본다 —
        #   1차 구현이 그랬고 **대상 집합이 조용히 1로 줄어도 통과**했다.
        written = {
            path.relative_to(self.out).as_posix() for path in self.out.rglob("*.json")
        }
        self.assertEqual(7, len(written), written)
        self.assertIn("measurement/index.json", written)

    def test_staging_directory_is_removed(self) -> None:
        pub.publish(
            source_root=self.source, output_root=self.out,
            config_path=REPO_ROOT / "config/economic_config.yaml",
        )
        staging = self.out.with_name(self.out.name + pub.STAGING_SUFFIX)
        self.assertFalse(staging.exists(), "staging 이 남으면 다음 실행이 섞인다")

    def test_index_is_written_last(self) -> None:
        """★ 대시보드의 진입점이므로 마지막이어야 한다.

        먼저 쓰면 아직 없는 산출물을 가리키는 인덱스가 존재하는 순간이 생긴다.
        mtime 으로 본다 — 같은 초에 끝나면 `>=` 다.
        """
        pub.publish(
            source_root=self.source, output_root=self.out,
            config_path=REPO_ROOT / "config/economic_config.yaml",
        )
        index_mtime = (
            self.out / pub.artifact_relative("index")
        ).stat().st_mtime
        for path in self.out.rglob("*.json"):
            if path.name == pub.INDEX_NAME:
                continue
            with self.subTest(artifact=path.name):
                self.assertGreaterEqual(index_mtime, path.stat().st_mtime)

    def test_missing_config_leaves_nothing_behind(self) -> None:
        """★ 검증 전 실패 시 최종 경로에 아무것도 남지 않는다."""
        from src.measurement.errors import ConfigError

        with self.assertRaises(ConfigError):
            pub.publish(
                source_root=self.source, output_root=self.out,
                config_path=Path("config/does_not_exist.yaml"),
            )
        self.assertFalse(list(self.out.rglob("*.json")) if self.out.exists() else [])

    def test_run_id_is_shared_by_every_artifact(self) -> None:
        """★ 대시보드는 `run_id` 가 다르면 값을 섞어 표시하지 않는다."""
        outcome = pub.publish(
            source_root=self.source, output_root=self.out,
            config_path=REPO_ROOT / "config/economic_config.yaml",
        )
        ids = {
            json.loads(path.read_text(encoding="utf-8"))["run_id"]
            for path in self.out.rglob("*.json")
        }
        self.assertEqual({outcome.run_id}, ids)


@unittest.skipUnless(yaml_available(), NEEDS_YAML)
class TestArtifactLayout(unittest.TestCase):
    """★★ ADR-0002 — 게시물은 `results/measurement/` 아래, 예외 하나.

    1차 구현이 **전부 루트에** 넣었다. Andrew 의 리더가 원래
    `results/measurement/index.json` 을 찾았는데 그가 **내 잘못된 출력에 맞춰
    코드를 고쳤다** — 생산자를 정본으로 본 판단 자체는 합리적이었지만, 이 경우
    생산자가 ADR 을 어기고 있었다.

    **→ 계약·ADR·픽스처가 정본이고 생산자가 그것을 따른다.** 이 테스트가 그것을
    고정한다: `artifacts[].path` 를 W2 픽스처와 **문자 단위로** 대조한다.
    """

    EXPECTED = {
        "measurement/ingestion_report.json",
        "measurement/rejection_report.json",
        "measurement/field_coverage_report.json",
        "measurement/kpi_report.json",
        "measurement/freeze_status.json",
        "measurement/index.json",
        # ★ 예외 — data_spec §9 와 이슈 #48 본문이 이 경로를 명시했다.
        #   일관성보다 정본이 우선한다.
        "data_quality_report.json",
    }

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.out = Path(self._tmp.name) / "results"
        pub.publish(
            source_root=Path(self._tmp.name) / "raw", output_root=self.out,
            config_path=REPO_ROOT / "config/economic_config.yaml",
        )

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_layout_matches_adr_0002(self) -> None:
        written = {
            path.relative_to(self.out).as_posix()
            for path in self.out.rglob("*.json")
        }
        self.assertEqual(self.EXPECTED, written)

    def test_data_quality_report_stays_at_the_root(self) -> None:
        """★ 이 예외를 없애면 `data_spec` §9 와 정본이 둘이 된다."""
        self.assertTrue((self.out / "data_quality_report.json").exists())
        self.assertFalse(
            (self.out / "measurement" / "data_quality_report.json").exists()
        )

    def test_artifact_paths_match_the_w2_fixture(self) -> None:
        """★★ 픽스처와 **문자 단위로** 대조한다 — Andrew 가 읽는 값이다."""
        fixture = json.loads(
            (REPO_ROOT / ".agent-team/04-architecture/examples/empty-sink"
             / "index.json").read_text(encoding="utf-8")
        )
        mine = json.loads(
            (self.out / pub.artifact_relative("index")).read_text(encoding="utf-8")
        )
        self.assertEqual(
            {a["artifact"]: a["path"] for a in fixture["artifacts"]},
            {a["artifact"]: a["path"] for a in mine["artifacts"]},
        )

    def test_view_routes_match_the_w2_fixture(self) -> None:
        """★ R-1 — `V4` 가 `/kpi` 다. 1차 구현이 `/metrics` 였다."""
        fixture = json.loads(
            (REPO_ROOT / ".agent-team/04-architecture/examples/empty-sink"
             / "index.json").read_text(encoding="utf-8")
        )
        mine = json.loads(
            (self.out / pub.artifact_relative("index")).read_text(encoding="utf-8")
        )
        self.assertEqual(
            {k: v["route"] for k, v in fixture["views"].items()},
            {k: v["route"] for k, v in mine["views"].items()},
        )
        self.assertEqual("/kpi", mine["views"]["V4"]["route"])

    def test_artifact_relative_is_the_single_source_of_layout(self) -> None:
        """배치 규칙이 한 함수에만 있다 — 두 곳에 적으면 갈라진다."""
        self.assertEqual(
            "measurement/kpi_report.json",
            pub.artifact_relative("kpi_report").as_posix(),
        )
        self.assertEqual(
            "data_quality_report.json",
            pub.artifact_relative("data_quality_report").as_posix(),
        )


@unittest.skipUnless(yaml_available(), NEEDS_YAML)
class TestRepresentativeScene(unittest.TestCase):
    """★★ J-1 — fixture 는 **실제 파이프라인 산출물**이다. 손으로 쓰지 않는다.

    `EventSink` 로 진짜 이벤트를 쓰고 `publish()` 를 돌린다. 손으로 쓴 기대값을
    두면 구현과 기대가 함께 틀릴 수 있고, 그때 테스트는 초록이다.
    """

    @classmethod
    def setUpClass(cls) -> None:
        cls._tmp = tempfile.TemporaryDirectory()
        root = Path(cls._tmp.name)
        cls.source = root / "raw"
        cls.out = root / "results"

        # 두 출처에서 실제 이벤트를 쓴다. 커머스는 메타 4종이 없다.
        #
        # ★ order_id 를 출처별로 나눈 이유: 1차 픽스처가 두 purchase 에 같은
        #   order_id 를 써서 DQ-02b(order_id 당 purchase 1건)가 **정당하게
        #   fail** 했다. 검사가 맞고 픽스처가 틀렸던 것이다. 대표 장면은 현실적인
        #   정상 데이터여야 하므로 분리하고, fail 경로는
        #   TestQualityGateFailsEndToEnd 가 따로 본다.
        with EventSink(cls.source) as sink:
            sink.write_events([
                simulator_event(sc.EventType.SESSION_START, day=1),
                simulator_event(sc.EventType.CHECKOUT_START, day=1,
                                order_id="O20251001-000001"),
                simulator_event(sc.EventType.PURCHASE, day=1,
                                order_id="O20251001-000001"),
                commerce_event(sc.EventType.SESSION_START, day=2),
                commerce_event(sc.EventType.PURCHASE, day=2,
                               order_id="O20251002-000002"),
                # 일부러 거부되는 레코드 — 거부 리포트가 비어 있지 않게 한다.
                simulator_event(sc.EventType.PURCHASE, day=2,
                                order_id="O20251002-000003", order_amount=-1),
            ])
        cls.outcome = pub.publish(
            source_root=cls.source, output_root=cls.out,
            config_path=REPO_ROOT / "config/economic_config.yaml",
            index_date=date(2025, 10, 2),
        )
        cls.artifacts = {
            path.stem if path.name != "index.json" else "index":
                json.loads(path.read_text(encoding="utf-8"))
            for path in cls.out.rglob("*.json")
        }

    @classmethod
    def tearDownClass(cls) -> None:
        cls._tmp.cleanup()

    def test_pipeline_ran_and_published(self) -> None:
        self.assertEqual("ok", self.outcome.publish_result)
        self.assertEqual(7, len(self.artifacts))

    def test_both_sources_appear_with_real_counts(self) -> None:
        sources = self.artifacts["ingestion_report"]["sources"]
        self.assertEqual("connected", sources["simulator"]["link_state"])
        self.assertEqual("connected", sources["commerce"]["link_state"])
        self.assertEqual(2, sources["commerce"]["event_count"])

    def test_rejected_record_is_reported_and_not_stored(self) -> None:
        """음수 금액 레코드가 거부되고 그 사유가 게시물에 남는다."""
        totals = self.artifacts["rejection_report"]["totals"]
        self.assertEqual(1, totals["events_rejected"]["value"])
        keys = {
            entry["reason_key"]
            for entry in self.artifacts["rejection_report"]["by_reason"]
        }
        self.assertIn("NEGATIVE_AMOUNT", keys)

    def test_headline_is_rejected_events_not_all_clear(self) -> None:
        """★ 거부가 1건 있으므로 `ALL_CLEAR` 가 될 수 없다 (B-11)."""
        verdict = self.artifacts["index"]["verdict"]
        self.assertEqual("REJECTED_EVENTS", verdict["headline_code"])
        self.assertEqual(1, verdict["counts"]["rejected_events"])

    def test_revenue_is_computed_but_profit_is_not(self) -> None:
        """★★ USP-1 대표 장면 — 매출은 나오고 기여이익은 계산 불가다.

        `revenue` 는 `order_amount` 로 계산되고, `cogs` 는 `unit_cost` 가 없어
        `NO_COST_BASIS` 다. 그래서 `contribution_profit` 도 계산 불가다.
        **0 원이 아니라 계산 불가**인 것이 이 프로젝트의 요점이다.
        """
        # ★ 실험 계층은 `value` 가 평범한 metric_value 다 (계약 allOf[1] ·
        #   MEA-002). by_source 를 전제하면 KeyError 다 — 계층별로 모양이 다르다.
        metrics = {
            entry["name"]: entry["value"]["by_source"]
            for entry in self.artifacts["kpi_report"]["metrics"]
            if "by_source" in entry["value"]
        }
        revenue = metrics["revenue"]["simulator"]
        self.assertEqual("ok", revenue["status"])
        self.assertEqual(47000, revenue["value"])
        self.assertEqual("47,000원", revenue["value_formatted"])

        profit = metrics["contribution_profit"]["simulator"]
        self.assertEqual("unavailable", profit["status"])
        self.assertIsNone(profit["value"])
        self.assertNotIn("basis", profit)
        self.assertNotIn("value_formatted", profit)
        self.assertIn("cogs", [ref["ref"] for ref in profit["blocked_by"]])

    def test_experiment_metrics_are_not_split_by_source(self) -> None:
        """★★ MEA-002 — 실험 판정은 출처를 나누지 않는다.

        계약 `allOf[1]` 이 `layer == "experiment"` 에 대해 `value` 를 평범한
        `metric_value` 로 못박는다. 양쪽에 같은 계산 불가를 실으면 *"커머스에도
        실험 판정이 있을 수 있다"* 는 뜻이 되고 그것이 MEA-002 가 막는 것이다.

        1차 구현이 다른 계층의 모양을 복사해 `by_source` 를 담았고 **계약이
        28건으로 거부했다** — 계약을 확인하지 않고 모양을 베낀 자리다.
        """
        experiment = [
            entry for entry in self.artifacts["kpi_report"]["metrics"]
            if entry["layer"] == "experiment"
        ]
        self.assertTrue(experiment, "실험 계층이 게시물에 없다 — U-7 을 검증할 수 없다")
        for entry in experiment:
            with self.subTest(metric=entry["name"]):
                self.assertNotIn("by_source", entry["value"])
                self.assertIn("status", entry["value"])
                self.assertEqual("unavailable", entry["value"]["status"])

    def test_primary_and_guardrail_roles_are_published(self) -> None:
        """★ R-3 — 화면 U-7 이 `[P1]` 배지를 그릴 수 있어야 한다.

        1차 구현이 24종 전부 `role: "none"` 을 내보내 Andrew 가 *"배지를 그릴 수
        없다"* 로 잡았다. **D-4 는 "역할 배정을 GATE 2 에서 Lock 한다"이지 "C1 에서
        게시하지 않는다"가 아니다** — `kpi-definition-v1.md` §7 에 배정안이 있다.
        """
        roles = {
            entry["name"]: entry["role"]
            for entry in self.artifacts["kpi_report"]["metrics"]
        }
        self.assertEqual("primary", roles.get("incremental_contribution_profit"))
        self.assertEqual("primary", roles.get("qini_coefficient"))
        self.assertEqual("guardrail", roles.get("marketing_cost"))
        self.assertEqual("guardrail", roles.get("churn_test_auc"))

    def test_blocks_is_the_reverse_of_blocked_by(self) -> None:
        """★ R-3 — `blocks` 가 실린다. 화면이 사슬을 추론하지 않는다 (DB-012).

        W2 픽스처는 13/13 전부 담았고 1차 구현은 0건이었다.
        """
        by_name = {
            entry["name"]: entry
            for entry in self.artifacts["kpi_report"]["metrics"]
        }
        self.assertIn("contribution_profit", by_name["cogs"]["blocks"])
        self.assertIn("contribution_profit", by_name["revenue"]["blocks"])
        # 역방향이 실제로 맞물리는지 — cogs 가 막으면 profit 의 blocked_by 에 cogs 가 있다
        profit = by_name["contribution_profit"]["value"]["by_source"]["simulator"]
        self.assertIn("cogs", [ref["ref"] for ref in profit["blocked_by"]])

    def test_no_uncomputable_metric_carries_a_zero(self) -> None:
        """★ 게시물 전체를 훑어 0 채우기가 0건임을 확인한다."""
        offenders: list[str] = []

        def walk(node: object, path: str = "$") -> None:
            if isinstance(node, dict):
                if node.get("status") in ("unavailable", "blocked", "not_run"):
                    if node.get("value") is not None:
                        offenders.append(f"{path} value={node['value']!r}")
                    if "basis" in node:
                        offenders.append(f"{path} basis 존재")
                for key, value in node.items():
                    walk(value, f"{path}.{key}")
            elif isinstance(node, list):
                for index, value in enumerate(node):
                    walk(value, f"{path}[{index}]")

        for name, payload in self.artifacts.items():
            walk(payload, name)
        self.assertEqual([], offenders, "\n".join(offenders))

    def test_every_computed_metric_has_a_formatted_value(self) -> None:
        """★ Andrew 의 화면이 직접 읽는 필드다. 하나라도 빠지면 `undefined` 다."""
        missing: list[str] = []

        def walk(node: object, path: str = "$") -> None:
            if isinstance(node, dict):
                if node.get("status") in ("ok", "unconfirmed"):
                    if "value_formatted" not in node:
                        missing.append(path)
                for key, value in node.items():
                    walk(value, f"{path}.{key}")
            elif isinstance(node, list):
                for index, value in enumerate(node):
                    walk(value, f"{path}[{index}]")

        for name, payload in self.artifacts.items():
            walk(payload, name)
        self.assertEqual([], missing, "\n".join(missing))

    def test_quality_gate_is_incomplete_not_fail(self) -> None:
        """★ 음수 금액 레코드는 **Sink 가 거부해 저장되지 않는다.**

        즉 품질 검사가 보는 데이터에는 위반이 없다. 그래서 `incomplete` 다 —
        거부는 **수집 층**이 잡았고 품질 층은 **저장물**을 본다. **두 층이 다른
        것을 본다**는 사실이 여기서 드러난다: 거부 1건이 있어도 품질 게이트는
        통과 가능하고, 그 거부는 rejection_report 가 말한다.
        """
        self.assertEqual(
            "incomplete", self.artifacts["data_quality_report"]["gate_result"]
        )

    def test_dq06_now_passes_because_sink_normalised_to_kst(self) -> None:
        """★ M-01 이 푼 검사가 실제 저장물에서 통과한다.

        정책 ⑵-a(원문 보존)를 골랐다면 이 검사가 자기 저장물에서 실패했다.
        """
        checks = {
            check["id"]: check
            for check in self.artifacts["data_quality_report"]["checks"]
        }
        self.assertEqual("pass", checks["DQ-06"]["status"])
        self.assertEqual(0, checks["DQ-06"]["violations"])
        self.assertGreater(checks["DQ-06"]["examined_rows"], 0)

    def test_all_eighteen_checks_are_present(self) -> None:
        from src.measurement import validate as dq

        checks = self.artifacts["data_quality_report"]["checks"]
        self.assertEqual(set(dq.DQ_IDS), {check["id"] for check in checks})

    def test_index_date_comes_from_the_data(self) -> None:
        self.assertEqual("2025-10-02", self.artifacts["kpi_report"]["index_date"])

    def test_provenance_records_config_hash_and_commit(self) -> None:
        provenance = self.artifacts["index"]["provenance"]
        self.assertEqual(sc.SCHEMA_VERSION, provenance["schema_version"])
        self.assertIsNone(
            provenance["simulator_commit"], "C1 에 시뮬레이터가 없다"
        )
        self.assertIn("simulator_commit", provenance["null_reason"])
        hashes = provenance["config_hashes"]
        self.assertTrue(
            any(value and len(str(value)) == 64 for value in hashes.values()),
            "config 해시가 기록되지 않았다 — 어떤 값으로 계산했는지 알 수 없다",
        )

    def test_notices_carry_the_assumptions(self) -> None:
        """가정은 문서가 아니라 산출물에 붙는다 (P-12)."""
        codes = {
            notice["code"] for notice in self.artifacts["kpi_report"]["notices"]
        }
        for expected in (
            "REFUND_NOT_ADJUSTED", "CHURN_THRESHOLDS_UNCONFIRMED",
            "INGESTION_GAP_UNDECIDABLE", "GATE1_NOT_PASSED",
        ):
            with self.subTest(code=expected):
                self.assertIn(expected, codes)

    def test_freeze_reports_unmet_preconditions_honestly(self) -> None:
        """★ 봉인하지 않은 상태가 초록으로 보이지 않는다.

        ⚠ 1차 작성 때 `G-15`(Lock 기록 절차)를 `met=False` 로 단언했는데 **M-09 가
        그 절차를 만들어 `True` 가 됐다.** 테스트가 자기 웨이브의 진행으로 낡은
        것이므로, 개별 G 를 박아 넣지 않고 **`freeze.py` 를 정본으로 대조한다** —
        정본이 하나면 낡을 자리가 없다.
        """
        from src.measurement import freeze as fz

        freeze = self.artifacts["freeze_status"]
        # ★ `overall` 을 상수로 박지 않는다. Lock 을 실행하면 not_started →
        #   partial 이 되고, 내 진행으로 내 테스트가 낡는다 (G-15 때와 같은 실수).
        #   `freeze.verify()` 를 정본으로 대조한다.
        record = fz.load_record()
        expected_verification = fz.verify(
            preconditions=fz.GATE1_PRECONDITIONS, items=fz.gate1_lock_items(record),
            lock_record=record,
        )
        self.assertEqual(expected_verification.overall, freeze["overall"])
        self.assertIn(freeze["overall"], ("not_started", "partial"),
                      "C1 에서 도달 가능한 최대치는 partial 이다")

        unmet = {item["id"]: item["met"] for item in freeze["unlocked_items"]}
        expected = {
            item.id: item.met
            for item in fz.GATE1_PRECONDITIONS if item.met is not True
        }
        self.assertEqual(expected, unmet)
        # ★ 그리고 `None` 이 게시물까지 살아가는지는 별개로 본다 — 화면이
        #   "확인하지 않았다" 와 "미충족" 을 구분하려면 null 이 보존돼야 한다.
        for gate_id, met in unmet.items():
            with self.subTest(gate=gate_id):
                self.assertIn(met, (False, None))


@unittest.skipUnless(yaml_available(), NEEDS_YAML)
class TestChurnDefinitionReachesThePublication(unittest.TestCase):
    """#183 ① — `churn_config_path`·`--churn-config` 의 정의가 지표·알림까지 전달된다.

    기본 정의(OR·42/60)와 다른 결과가 나오는 장면이어야 전달 누락이 잡힌다: 45일 전에
    사고 21일 전에 접속한 고객은 OR 에서 이탈, AND 에서 이탈 아님이다.
    """

    INDEX = date(2025, 11, 15)
    AND_RULE = {"at_risk_days": 28, "no_purchase_days": 42, "no_login_days": 60, "rule_operator": "AND"}

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        with EventSink(self.root / "raw") as sink:
            sink.write_events([
                simulator_event(sc.EventType.PURCHASE, day=1, order_id="O20251001-000001"),
                simulator_event(sc.EventType.SESSION_START, day=25),
            ])
        self.and_config = self.root / "churn_and.yaml"
        self.and_config.write_text(json.dumps({"churn": self.AND_RULE}), encoding="utf-8")

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def _kpi_report(self, out: Path) -> dict:
        return json.loads(next(out.rglob("kpi_report.json")).read_text(encoding="utf-8"))

    def _simulator(self, report: dict, name: str) -> dict:
        metric = next(m for m in report["metrics"] if m["name"] == name)
        return metric["value"]["by_source"]["simulator"]

    def _assert_and_rule(self, report: dict) -> None:
        churn = self._simulator(report, "churn_rate")
        self.assertEqual(0.0, churn["value"])
        self.assertEqual("AND", churn["params_used"]["rule_operator"])
        self.assertEqual(1.0, self._simulator(report, "retention_rate")["value"])
        derived = self._simulator(report, "derived_state_count[churn]")
        self.assertEqual((0, "AND"), (derived["value"], derived["params_used"]["rule_operator"]))
        notice = next(n for n in report["notices"] if n["code"] == "CHURN_THRESHOLDS_UNCONFIRMED")
        self.assertIn(" AND ", notice["message"])

    def test_default_definition_counts_the_lapsed_buyer_as_churned(self) -> None:
        pub.publish(source_root=self.root / "raw", output_root=self.root / "default",
                    config_path=REPO_ROOT / "config/economic_config.yaml", index_date=self.INDEX)
        self.assertEqual(1.0, self._simulator(self._kpi_report(self.root / "default"), "churn_rate")["value"])

    def test_churn_config_path_reaches_every_dependent_metric_and_notice(self) -> None:
        pub.publish(source_root=self.root / "raw", output_root=self.root / "and",
                    config_path=REPO_ROOT / "config/economic_config.yaml",
                    churn_config_path=self.and_config, index_date=self.INDEX)
        self._assert_and_rule(self._kpi_report(self.root / "and"))

    def test_cli_flag_reaches_the_publication(self) -> None:
        with contextlib.redirect_stdout(io.StringIO()):
            code = pub.main([
                "--source", str(self.root / "raw"), "--out", str(self.root / "cli"),
                "--config", str(REPO_ROOT / "config/economic_config.yaml"),
                "--churn-config", str(self.and_config), "--index-date", self.INDEX.isoformat(),
            ])
        self.assertEqual(0, code)
        self._assert_and_rule(self._kpi_report(self.root / "cli"))


@unittest.skipUnless(yaml_available(), NEEDS_YAML)
class TestPublishedArtifactsAgainstContract(unittest.TestCase):
    """★★ 실제 게시물이 **수정된 계약을 통과한다** — 이것이 T1 의 최종 증거다."""

    def test_every_artifact_validates(self) -> None:
        try:
            from jsonschema import Draft202012Validator
            from referencing import Registry, Resource
        except ImportError:
            self.skipTest(
                "BLOCKED: jsonschema 미설치 — 게시물의 계약 적합성을 검증하지 않았다"
            )
        contracts = REPO_ROOT / "docs/contracts/measurement-publish/v1"
        base = "https://72offsuit.local/ai-roi/measurement-publish/v1/"
        resources = []
        for path in sorted(contracts.glob("*.schema.json")):
            schema = json.loads(path.read_text(encoding="utf-8"))
            resources.append((schema["$id"], Resource.from_contents(schema)))
        registry = Registry().with_resources(resources)

        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "results"
            pub.publish(
                source_root=Path(tmp) / "raw", output_root=out,
                config_path=REPO_ROOT / "config/economic_config.yaml",
            )
            for path in sorted(out.rglob("*.json")):
                name = "index" if path.name == "index.json" else path.stem
                validator = Draft202012Validator(
                    {"$ref": f"{base}{name}.schema.json"}, registry=registry
                )
                errors = [
                    f"{'/'.join(str(p) for p in e.absolute_path)}: {e.message}"
                    for e in validator.iter_errors(
                        json.loads(path.read_text(encoding="utf-8"))
                    )
                ]
                with self.subTest(artifact=path.name):
                    self.assertEqual([], errors, "\n".join(errors[:5]))


if __name__ == "__main__":
    unittest.main()
