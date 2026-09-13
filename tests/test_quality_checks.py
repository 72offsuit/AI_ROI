"""데이터 품질 검증 검사 (이슈 #48).

★★ **AC-8 — 의도적으로 깨뜨린 데이터로 검사한다.**

*"검사를 만들면 그 검사가 계기를 잡는지부터 확인한다."* 실행 가능한 검사 각각에
**위반 데이터를 만들어 `fail` 이 나오는지** 확인하고, 동시에 **정상 데이터에서
`pass` 가 나오는지**도 확인한다. 한쪽만 보면:

  - 실패만 보면 → 항상 `fail` 하는 검사를 통과시킨다
  - 통과만 보면 → 아무것도 안 잡는 검사를 통과시킨다

그리고 **0행일 때 `vacuous` 인지** 를 함께 본다 — 세 번째 축이다. 공허한 `pass` 가
`ADR-0010` 의 계기였다.

실행:
    python3 -m unittest tests.test_quality_checks -v
"""

from __future__ import annotations

import unittest
import uuid

from src.measurement import validate as v
from src.measurement.errors import QualityGateFailure
from src.measurement.schema import EventType


def event(
    event_type: EventType = EventType.SESSION_START,
    *,
    at: str = "2025-10-01T09:00:00.000+09:00",
    **overrides: object,
) -> dict[str, object]:
    """KST 로 정규화된, 스키마를 만족하는 최소 레코드."""
    record: dict[str, object] = {
        "event_id": str(uuid.uuid4()),
        "customer_id": "C00012345",
        "timestamp": at,
        "event_type": event_type.value,
        "session_id": "S-C00012345-1759276800000",
        "page_type": "home",
    }
    record.update(overrides)
    return record


def purchase(**overrides: object) -> dict[str, object]:
    base = event(
        EventType.PURCHASE, page_type="complete",
        order_id="O20251001-000123", order_amount=47000,
    )
    base.update(overrides)
    return base


class TestDefinitionIsCanonical(unittest.TestCase):
    """Q-1 · Q-4 — 18종이 하나의 정본에서 나온다."""

    def test_eighteen_checks_are_defined(self) -> None:
        """본문의 17 이 아니라 **18** 이다 — 표와 픽스처가 18 이다."""
        self.assertEqual(18, len(v.DQ_ALL))

    def test_ids_are_unique(self) -> None:
        self.assertEqual(len(v.DQ_IDS), len(set(v.DQ_IDS)))

    def test_every_spec_has_a_scope(self) -> None:
        """AC-6 — *"이 검사가 실제로 무엇을 검사했는가"* 가 비어 있으면 안 된다."""
        for spec in v.DQ_ALL:
            with self.subTest(check=spec.id):
                self.assertTrue(spec.scope.strip())

    def test_unrunnable_checks_explain_themselves(self) -> None:
        """실행 못 하는 검사는 **왜** 못 하는지를 담는다."""
        for spec in v.DQ_ALL:
            if spec.c1 != "runnable":
                with self.subTest(check=spec.id):
                    self.assertTrue(spec.reason.strip(), f"{spec.id} 에 사유가 없다")


class TestAlwaysEighteen(unittest.TestCase):
    """★ AC-3 · Q-4 — 항상 18종을 낸다. 실행 못 한 것도 목록에 남는다."""

    def test_empty_events_still_report_eighteen(self) -> None:
        report = v.build_report([])
        self.assertEqual(18, len(report["checks"]))

    def test_reported_checks_equals_len_checks(self) -> None:
        """Q-3 — 상수로 적지 않는다. 픽스처가 7건에 6 을 적었다."""
        report = v.build_report([])
        self.assertEqual(
            len(report["checks"]), report["spec_coverage"]["reported_checks"]
        )

    def test_id_set_matches_the_definition(self) -> None:
        """★ 수만 세면 **어느 것이 빠졌는지** 못 말한다 (Q-4 세 번째 명제)."""
        report = v.build_report([])
        self.assertEqual(
            set(v.DQ_IDS), {check["id"] for check in report["checks"]}
        )

    def test_dropping_a_check_is_caught(self) -> None:
        """★ 자기검증이 실제로 무는지 확인한다 — 목록에서 하나 빼 본다."""
        checks = v.run_all([])
        with self.assertRaises(QualityGateFailure) as caught:
            v._verify_report_invariants(checks[:-1])
        self.assertIn("17", str(caught.exception))

    def test_missing_id_is_named_not_just_counted(self) -> None:
        """빠진 ID 를 **이름으로** 말한다. 개수만으로는 고칠 수 없다."""
        checks = list(v.run_all([]))
        removed = checks.pop(3)
        checks.append(checks[0])  # 수는 18 로 맞추고 ID 만 어긋나게 한다
        with self.assertRaises(QualityGateFailure) as caught:
            v._verify_report_invariants(checks)
        self.assertIn(removed.id, str(caught.exception))


class TestVacuousIsNotPass(unittest.TestCase):
    """★★ AC-5 — 공허한 통과를 세 겹으로 막는다 (`ADR-0010`)."""

    def test_zero_rows_gives_vacuous_not_pass(self) -> None:
        report = v.build_report([])
        runnable = [
            check for check in report["checks"]
            if v.DQ_INDEX[check["id"]].c1 == "runnable"
        ]
        self.assertTrue(runnable)
        for check in runnable:
            with self.subTest(check=check["id"]):
                self.assertEqual("vacuous", check["status"])

    def test_pass_with_zero_examined_rows_cannot_be_constructed(self) -> None:
        """생성자가 막는다 — 잘못된 결과를 만들 수 있으면 게시까지 살아남는다."""
        with self.assertRaises(ValueError) as caught:
            v.CheckResult(
                id="DQ-01", spec_ref="유일성", title="t", status="pass",
                scope="s", examined_rows=0, violations=0,
            )
        self.assertIn("vacuous", str(caught.exception))

    def test_vacuous_forbids_reason_code(self) -> None:
        """계약이 금지한다 (F-E 교체분) — `status` 가 이미 사유다."""
        with self.assertRaises(ValueError):
            v.CheckResult(
                id="DQ-01", spec_ref="유일성", title="t", status="vacuous",
                scope="s", examined_rows=0, violations=None,
                reason_code="NOT_RUN", reason_detail="d",
            )

    def test_vacuous_requires_a_reason_detail(self) -> None:
        with self.assertRaises(ValueError):
            v.CheckResult(
                id="DQ-01", spec_ref="유일성", title="t", status="vacuous",
                scope="s", examined_rows=0, violations=None,
            )

    def test_unrun_checks_have_null_violations(self) -> None:
        """★ `0` 으로 적으면 통과처럼 읽힌다."""
        for status in ("not_run", "blocked", "vacuous"):
            with self.subTest(status=status):
                with self.assertRaises(ValueError):
                    v.CheckResult(
                        id="DQ-01", spec_ref="유일성", title="t", status=status,
                        scope="s", examined_rows=0, violations=0,
                        reason_code="NOT_RUN", reason_detail="d",
                    )


class TestGateResult(unittest.TestCase):
    """AC-4 — 3값. `vacuous` 하나만 있어도 `pass` 가 아니다."""

    def _result(self, status: str, check_id: str = "DQ-01") -> v.CheckResult:
        if status == "pass":
            return v.CheckResult(
                id=check_id, spec_ref="유일성", title="t", status="pass",
                scope="s", examined_rows=5, violations=0,
            )
        if status == "fail":
            return v.CheckResult(
                id=check_id, spec_ref="유일성", title="t", status="fail",
                scope="s", examined_rows=5, violations=2,
            )
        return v.CheckResult(
            id=check_id, spec_ref="유일성", title="t", status=status,
            scope="s", examined_rows=0, violations=None,
            reason_code=None if status == "vacuous" else "NOT_RUN",
            reason_detail="사유",
        )

    def test_all_pass_is_pass(self) -> None:
        self.assertEqual("pass", v.gate_result([self._result("pass")]))

    def test_any_fail_is_fail(self) -> None:
        self.assertEqual(
            "fail", v.gate_result([self._result("pass"), self._result("fail")])
        )

    def test_one_vacuous_blocks_pass(self) -> None:
        """★ 여기가 요점이다. 실행분이 전부 통과해도 `pass` 가 아니다."""
        self.assertEqual(
            "incomplete",
            v.gate_result([self._result("pass"), self._result("vacuous")]),
        )

    def test_not_run_blocks_pass(self) -> None:
        self.assertEqual(
            "incomplete",
            v.gate_result([self._result("pass"), self._result("not_run")]),
        )

    def test_fail_wins_over_incomplete(self) -> None:
        """데이터의 실패가 검사기의 한계보다 우선한다."""
        self.assertEqual(
            "fail",
            v.gate_result([self._result("not_run"), self._result("fail")]),
        )

    def test_empty_events_give_incomplete_not_pass(self) -> None:
        """오늘 이 저장소의 정상 상태다."""
        self.assertEqual("incomplete", v.build_report([])["gate_result"])

    def test_raise_on_fail_stops_the_pipeline(self) -> None:
        """`data_spec` §9 — 경고로 넘어가지 않는다."""
        report = {
            "gate_result": "fail",
            "checks": [{"id": "DQ-10", "status": "fail"}],
        }
        with self.assertRaises(QualityGateFailure) as caught:
            v.raise_on_fail(report)
        self.assertIn("DQ-10", str(caught.exception))
        self.assertEqual(2, caught.exception.exit_code)

    def test_incomplete_does_not_stop_the_pipeline(self) -> None:
        """★ 검사기의 한계로 멈추면 C1 에서 파이프라인이 영원히 안 돈다."""
        v.raise_on_fail(v.build_report([]))  # 예외가 없어야 한다


# ══════════════════════════════════════════════════════════════════════════
# ★★ AC-8 — 8개 실행 가능 검사 각각을 세 축으로 확인한다
#           ① 정상 → pass   ② 위반 → fail   ③ 0행 → vacuous
# ══════════════════════════════════════════════════════════════════════════

class TestRunnableChecksCatchViolations(unittest.TestCase):

    def _assert_three_axes(
        self,
        runner,
        *,
        clean: list[dict[str, object]],
        broken: list[dict[str, object]],
        check_id: str,
    ) -> None:
        with self.subTest(check=check_id, axis="정상 → pass"):
            result = runner(clean)
            self.assertEqual("pass", result.status, result.reason_detail)
            self.assertEqual(0, result.violations)
            self.assertGreater(result.examined_rows, 0)
        with self.subTest(check=check_id, axis="위반 → fail"):
            result = runner(broken)
            self.assertEqual("fail", result.status)
            self.assertGreater(result.violations or 0, 0)
            self.assertTrue(result.samples, "위반 표본이 없으면 고칠 수 없다")
        with self.subTest(check=check_id, axis="0행 → vacuous"):
            result = runner([])
            self.assertEqual("vacuous", result.status)
            self.assertIsNone(result.violations)

    def test_dq01_event_id_uniqueness(self) -> None:
        clean = [event(), event()]
        duplicated = event()
        broken = [duplicated, dict(duplicated)]
        self._assert_three_axes(
            v.check_event_id_unique, clean=clean, broken=broken, check_id="DQ-01"
        )

    def test_dq02b_one_purchase_per_order(self) -> None:
        clean = [purchase(order_id="O20251001-000001"),
                 purchase(order_id="O20251001-000002")]
        broken = [purchase(order_id="O20251001-000001"),
                  purchase(order_id="O20251001-000001")]
        self._assert_three_axes(
            v.check_order_id_single_purchase,
            clean=clean, broken=broken, check_id="DQ-02b",
        )

    def test_dq04_session_event_order(self) -> None:
        clean = [
            event(at="2025-10-01T09:00:00.000+09:00"),
            event(at="2025-10-01T09:05:00.000+09:00"),
        ]
        broken = [
            event(at="2025-10-01T09:05:00.000+09:00"),
            event(at="2025-10-01T09:00:00.000+09:00"),  # 뒤로 간다
        ]
        self._assert_three_axes(
            v.check_session_order, clean=clean, broken=broken, check_id="DQ-04"
        )

    def test_dq06_timezone_is_kst_only(self) -> None:
        """★ M-01 이 `BLOCKED` 를 푼 검사다. Sink 의 약속을 자기 저장물에 확인한다."""
        clean = [event(at="2025-10-01T09:00:00.000+09:00")]
        broken = [event(at="2025-10-01T00:00:00.000Z")]  # 정규화되지 않은 UTC
        self._assert_three_axes(
            v.check_timezone_single, clean=clean, broken=broken, check_id="DQ-06"
        )

    def test_dq07_purchase_needs_checkout_start(self) -> None:
        clean = [
            event(EventType.CHECKOUT_START, at="2025-10-01T09:00:00.000+09:00",
                  page_type="checkout", order_id="O20251001-000001",
                  order_amount=47000),
            purchase(at="2025-10-01T09:05:00.000+09:00",
                     order_id="O20251001-000001"),
        ]
        broken = [purchase(at="2025-10-01T09:05:00.000+09:00")]  # 선행이 없다
        self._assert_three_axes(
            v.check_purchase_funnel, clean=clean, broken=broken, check_id="DQ-07"
        )

    def test_dq07_checkout_after_purchase_is_not_a_predecessor(self) -> None:
        """★ 같은 세션에 있어도 **뒤**에 있으면 선행이 아니다.

        존재만 보면 순서가 뒤바뀐 데이터를 통과시킨다.
        """
        events = [
            purchase(at="2025-10-01T09:00:00.000+09:00",
                     order_id="O20251001-000001"),
            event(EventType.CHECKOUT_START, at="2025-10-01T09:05:00.000+09:00",
                  page_type="checkout", order_id="O20251001-000001",
                  order_amount=47000),
        ]
        self.assertEqual("fail", v.check_purchase_funnel(events).status)

    def test_dq08_coupon_use_needs_exposure(self) -> None:
        clean = [
            event(EventType.COUPON_EXPOSED, at="2025-10-01T09:00:00.000+09:00",
                  coupon_id="CPN-A1B2C3", campaign_id="CMP-20251001-001"),
            event(EventType.COUPON_USE, at="2025-10-01T09:05:00.000+09:00",
                  coupon_id="CPN-A1B2C3", campaign_id="CMP-20251001-001",
                  order_id="O20251001-000001", order_amount=47000),
        ]
        broken = [
            event(EventType.COUPON_USE, at="2025-10-01T09:05:00.000+09:00",
                  coupon_id="CPN-A1B2C3", campaign_id="CMP-20251001-001",
                  order_id="O20251001-000001", order_amount=47000),
        ]
        self._assert_three_axes(
            v.check_coupon_funnel, clean=clean, broken=broken, check_id="DQ-08"
        )

    def test_dq10_no_negative_amounts(self) -> None:
        clean = [purchase(order_amount=47000)]
        broken = [purchase(order_amount=-1)]
        self._assert_three_axes(
            v.check_no_negative_amounts,
            clean=clean, broken=broken, check_id="DQ-10",
        )

    def test_dq11_key_completeness(self) -> None:
        clean = [purchase()]
        missing = purchase()
        del missing["order_amount"]
        self._assert_three_axes(
            v.check_key_completeness,
            clean=clean, broken=[missing], check_id="DQ-11",
        )

    def test_dq11_catches_absent_event_type(self) -> None:
        """`event_type` 자체가 없는 것은 Key 결측의 극단이다 — 건너뛰지 않는다."""
        broken = purchase()
        del broken["event_type"]
        result = v.check_key_completeness([broken])
        self.assertEqual("fail", result.status)
        self.assertEqual(1, result.examined_rows, "세지도 않고 넘기면 안 된다")


class TestDq17Reproducibility(unittest.TestCase):
    """DQ-17 — 환경으로 `blocked` 와 실행이 갈린다."""

    def test_blocked_without_pyarrow(self) -> None:
        from src.measurement.sink import parquet_available

        result = v.check_parquet_reproducible()
        if parquet_available():
            # 설치 환경에서도 해시를 안 넘기면 blocked 다 — pass 로 적지 않는다.
            self.assertEqual("blocked", result.status)
            self.assertIn("해시", result.reason_detail or "")
        else:
            self.assertEqual("blocked", result.status)
            self.assertEqual("BLOCKED", result.reason_code)
            self.assertIn("pyarrow", result.reason_detail or "")

    def test_matching_digests_pass(self) -> None:
        from src.measurement.sink import parquet_available

        if not parquet_available():
            self.skipTest("BLOCKED: pyarrow 미설치 — 실행 경로를 검증하지 않았다")
        result = v.check_parquet_reproducible(digests=["a" * 64, "a" * 64])
        self.assertEqual("pass", result.status)

    def test_differing_digests_fail(self) -> None:
        from src.measurement.sink import parquet_available

        if not parquet_available():
            self.skipTest("BLOCKED: pyarrow 미설치 — 실행 경로를 검증하지 않았다")
        result = v.check_parquet_reproducible(digests=["a" * 64, "b" * 64])
        self.assertEqual("fail", result.status)


class TestSpecCoverage(unittest.TestCase):
    """AC-7 — 화면이 정본 목록을 상수로 들지 않는다. 게시물이 준다."""

    def test_spec_items_are_reported(self) -> None:
        coverage = v.build_report([])["spec_coverage"]
        self.assertEqual(11, len(coverage["spec_items"]), coverage["spec_items"])

    def test_every_spec_item_names_its_checks(self) -> None:
        """항목마다 어느 DQ 가 덮는지 밝힌다 — 화면이 추론하지 않는다."""
        for entry in v.build_report([])["spec_coverage"]["spec_items"]:
            with self.subTest(item=entry["spec_ref"]):
                self.assertTrue(entry["covered_by"])
                self.assertIn(entry["worst_status"], v.CHECK_STATUSES)

    def test_nothing_is_unmapped_because_all_eighteen_are_defined(self) -> None:
        """★ `unmapped` = **검사가 아예 정의되지 않은** 항목이다.

        실행 여부는 `worst_status` 가 말한다. 둘을 섞으면 "검사를 안 만들었다"와
        "만들었지만 대상이 0행이었다"가 같아 보이고, 조치가 완전히 다르다.
        """
        coverage = v.build_report([])["spec_coverage"]
        self.assertEqual([], coverage["unmapped_spec_items"])

    def test_worst_status_reflects_the_weakest_check(self) -> None:
        """★ 한 항목을 여러 검사가 나눠 덮으면 **가장 나쁜 것**이 그 항목의 상태다.

        "금액 정합성" 은 DQ-09(not_run)와 DQ-10(실행)이 나눠 덮는다. DQ-10 이
        통과해도 항목 전체가 통과한 것은 아니다 — 금액 등식은 검사하지 못했다.
        """
        events = [purchase(order_amount=47000)]
        coverage = v.build_report(events)["spec_coverage"]
        amounts = next(
            e for e in coverage["spec_items"] if e["spec_ref"] == "금액 정합성"
        )
        self.assertEqual(["DQ-09", "DQ-10"], amounts["covered_by"])
        self.assertEqual("not_run", amounts["worst_status"])

        uniqueness = next(
            e for e in coverage["spec_items"] if e["spec_ref"] == "유일성"
        )
        self.assertEqual(["DQ-01", "DQ-02", "DQ-02b"], uniqueness["covered_by"])

    def test_two_checks_share_one_spec_item(self) -> None:
        """`DQ-02`/`DQ-02b` 와 `DQ-09`/`DQ-10` 이 항목을 나눠 덮는다."""
        self.assertEqual(
            v.DQ_INDEX["DQ-02"].spec_item, v.DQ_INDEX["DQ-02b"].spec_item
        )
        self.assertEqual(
            v.DQ_INDEX["DQ-09"].spec_item, v.DQ_INDEX["DQ-10"].spec_item
        )


class TestReportAgainstContract(unittest.TestCase):
    """게시물이 수정된 계약을 통과하는지 — `jsonschema` 가 있으면 실제로 검증한다."""

    def test_report_shape_matches_contract(self) -> None:
        try:
            from jsonschema import Draft202012Validator
            from referencing import Registry, Resource
        except ImportError:
            self.skipTest(
                "BLOCKED: jsonschema 미설치 — 품질 리포트의 계약 적합성을 "
                "검증하지 않았다"
            )
        import json
        from pathlib import Path

        contracts = (
            Path(__file__).resolve().parents[1]
            / "docs/contracts/measurement-publish/v1"
        )
        resources = []
        for path in sorted(contracts.glob("*.schema.json")):
            schema = json.loads(path.read_text(encoding="utf-8"))
            resources.append((schema["$id"], Resource.from_contents(schema)))
        registry = Registry().with_resources(resources)
        body = v.build_report([])
        validator = Draft202012Validator(
            {"$ref": "https://72offsuit.local/ai-roi/measurement-publish/v1/"
                     "data_quality_report.schema.json#/properties/checks"},
            registry=registry,
        )
        errors = [
            f"{'/'.join(str(p) for p in e.absolute_path)}: {e.message}"
            for e in validator.iter_errors(body["checks"])
        ]
        self.assertEqual(
            [], errors,
            "★ 우리 구현이 낸 18종이 수정된 계약을 통과하지 못한다. 픽스처의 "
            "vacuous 7건은 reason_code 를 담아 거부되지만, 우리 출력은 담지 "
            "않으므로 통과해야 한다:\n" + "\n".join(errors),
        )


if __name__ == "__main__":
    unittest.main()
