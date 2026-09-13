"""`contracts.py` 검사 — 봉투 · `value_formatted` · fail-closed 자기검증 (M-06 T2).

파일명이 `test_publish_envelope.py` 인 이유: `ownership.json` 이 Phillip 소유
테스트를 `tests/test_publish_*.py` 로 규정하고 `test_contracts.py` 는 그 패턴에
걸리지 않는다. **`ownership.json` 을 고치는 대신 파일명을 규약에 맞춘다** —
소유 경계는 W2 가 정한 것이고 구현자가 넓히는 것이 아니다.

**표준 라이브러리만 쓴다.** `jsonschema` 없이 전부 돈다 — 게시 시점 자기검증이
의존성 없이 동작해야 하기 때문이고(D-21), 그 사실 자체가 검사 대상이다.

★ 이 파일이 지키는 것 둘:

  1. **`value_formatted` 가 `(status, unit, value)` 만으로 결정된다.** 호출자가
     넘기지 않으므로 한 곳만 빠뜨릴 자리가 없다 — 그것이 `?? 0` 을 막는 구조다.
  2. **계약 위반이면 문자열을 만들지 않는다** (fail closed). 위반한 게시물을
     내보내는 것보다 아무것도 내보내지 않는 것이 낫다.

실행:
    python3 -m unittest tests.test_publish_envelope -v
"""

from __future__ import annotations

import json
import re
import unittest
from datetime import datetime, timedelta, timezone

from src.measurement import contracts as ct
from src.measurement import schema as sc
from src.measurement.errors import ContractViolation

#: 계약 정규식을 여기 다시 적지 않고 계약 파일에서 읽어온다. 두 번 적으면 갈라진다.
_COMMON = json.loads(
    (ct.Path(__file__).resolve().parents[1]
     / "docs/contracts/measurement-publish/v1/common.schema.json").read_text(
        encoding="utf-8")
)["$defs"]

BASIS = sc.Basis(
    population="P_buyer(D)",
    denominator_definition="분모 없음 (합계)",
    window=sc.Window(sc.WindowDirection.NONE),
    observed_count=0,
)


class TestRunIdAndTimestamp(unittest.TestCase):
    """계약 정규식을 **계약 파일에서 읽어** 대조한다."""

    def test_run_id_matches_contract_pattern(self) -> None:
        pattern = _COMMON["run_id"]["pattern"]
        for _ in range(20):  # 난수 부분이 항상 8 hex 인지 반복 확인
            self.assertRegex(ct.new_run_id(), pattern)

    def test_run_id_uses_kst_not_utc(self) -> None:
        """UTC 로 찍으면 자정 근처에서 날짜가 하루 어긋난다."""
        # KST 로 2026-09-12 00:30 인 순간 (UTC 로는 09-11 15:30)
        moment = datetime(2026, 9, 11, 15, 30, tzinfo=timezone.utc)
        self.assertTrue(ct.new_run_id(now=moment).startswith("MR-20260912-0030"))

    def test_generated_at_matches_contract_and_rejects_z(self) -> None:
        pattern = _COMMON["kst_timestamp"]["pattern"]
        self.assertRegex(ct.kst_now(), pattern)
        # 계약이 'Z' 표기를 거부한다는 사실을 함께 고정한다 — W1 W-8 의 재발 방지.
        self.assertIsNone(re.fullmatch(pattern, "2026-09-11T04:58:02.000Z"))

    def test_generated_at_always_has_milliseconds(self) -> None:
        """자릿수가 흔들리면 같은 데이터가 다른 바이트를 낸다 (NFR-001)."""
        exact_second = datetime(2026, 9, 11, 13, 58, 2, 0, tzinfo=ct.KST)
        self.assertEqual("2026-09-11T13:58:02.000+09:00", ct.kst_now(now=exact_second))

    def test_offset_input_is_converted_not_relabelled(self) -> None:
        """다른 오프셋으로 들어온 시각을 KST 로 **변환**한다. 라벨만 바꾸지 않는다."""
        new_york = datetime(2026, 9, 11, 0, 58, 2, tzinfo=timezone(timedelta(hours=-4)))
        self.assertEqual("2026-09-11T13:58:02.000+09:00", ct.kst_now(now=new_york))


class TestValueFormatted(unittest.TestCase):
    """★ §4.16.1 의 `unit` 별 포맷 규칙 8종이 정본이다."""

    OK = sc.MetricStatus.OK

    def test_every_unit_has_a_format_rule(self) -> None:
        """`Unit` 에 값을 추가하고 규칙을 빠뜨리면 여기서 걸린다."""
        sample = {
            sc.Unit.KRW: 1, sc.Unit.KRW_PER_CUSTOMER: 1, sc.Unit.COUNT: 1,
            sc.Unit.RATIO: 0.5, sc.Unit.PERCENTAGE_POINT: 1.0, sc.Unit.DAYS: 1,
            sc.Unit.TEXT: "x", sc.Unit.DATETIME: "2026-09-11T13:58:02.000+09:00",
        }
        self.assertEqual(set(sc.Unit), set(sample), "Unit 이 늘었는데 표본이 없다")
        for unit, value in sample.items():
            with self.subTest(unit=unit.value):
                self.assertTrue(ct.format_value(self.OK, unit, value))

    def test_format_rules(self) -> None:
        cases = [
            (sc.Unit.KRW, 38400, "38,400원"),
            (sc.Unit.KRW, 0, "0원"),
            (sc.Unit.KRW, 1234567, "1,234,567원"),
            (sc.Unit.KRW_PER_CUSTOMER, 2130, "2,130원/인"),
            (sc.Unit.COUNT, 1204, "1,204건"),
            (sc.Unit.DAYS, 42, "42일"),
            (sc.Unit.RATIO, 0.1834, "18.3%"),
            (sc.Unit.PERCENTAGE_POINT, 3.2, "+3.2%p"),
            (sc.Unit.PERCENTAGE_POINT, -3.2, "-3.2%p"),
            (sc.Unit.TEXT, "true", "true"),
        ]
        for unit, value, expected in cases:
            with self.subTest(unit=unit.value, value=value):
                self.assertEqual(expected, ct.format_value(self.OK, unit, value))

    def test_krw_has_no_decimals(self) -> None:
        """원 단위에 소수점이 남으면 금액으로 읽히지 않는다."""
        self.assertEqual("38,400원", ct.format_value(self.OK, sc.Unit.KRW, 38400.4))
        self.assertEqual("38,401원", ct.format_value(self.OK, sc.Unit.KRW, 38400.6))

    def test_ratio_multiplication_happens_once(self) -> None:
        """★ 화면이 다시 ×100 하지 않도록 여기서 끝낸다."""
        self.assertEqual("18.3%", ct.format_value(self.OK, sc.Unit.RATIO, 0.1834))
        self.assertEqual("100.0%", ct.format_value(self.OK, sc.Unit.RATIO, 1.0))
        self.assertEqual("0.0%", ct.format_value(self.OK, sc.Unit.RATIO, 0.0))

    def test_percentage_point_keeps_the_sign(self) -> None:
        """`+3.2%p` 와 `3.2%p` 는 다른 주장이다."""
        self.assertTrue(
            ct.format_value(self.OK, sc.Unit.PERCENTAGE_POINT, 3.2).startswith("+")
        )

    def test_datetime_is_rendered_in_kst(self) -> None:
        utc = "2026-09-11T04:58:02+00:00"
        self.assertEqual(
            "2026-09-11 13:58", ct.format_value(self.OK, sc.Unit.DATETIME, utc)
        )

    def test_uncomputable_statuses_get_no_formatted_value(self) -> None:
        """계약이 계산 불가 3종에 `value_formatted` 를 **금지**한다."""
        for status in (sc.MetricStatus.UNAVAILABLE, sc.MetricStatus.BLOCKED,
                       sc.MetricStatus.NOT_RUN):
            with self.subTest(status=status.value):
                self.assertIsNone(ct.format_value(status, sc.Unit.KRW, None))

    def test_missing_unit_raises_instead_of_guessing(self) -> None:
        """`unit` 이 없으면 빈 문자열을 쓰지 않고 멈춘다.

        빈 문자열을 쓰면 계약의 `minLength: 1` 에 걸려 게시 시점에 터지는데, 그
        자리는 원인에서 멀다. 여기서 끊는 것이 가장 싸다.
        """
        with self.assertRaises(ContractViolation):
            ct.format_value(self.OK, None, 38400)

    def test_formatting_does_not_depend_on_locale(self) -> None:
        """로케일 함수를 쓰지 않는다 — 환경마다 다르면 재현성이 깨진다."""
        import locale

        original = locale.setlocale(locale.LC_ALL)
        try:
            for candidate in ("C", "de_DE.UTF-8", "en_US.UTF-8"):
                try:
                    locale.setlocale(locale.LC_ALL, candidate)
                except locale.Error:
                    continue  # 그 로케일이 없는 기계다 — 건너뛴다
                with self.subTest(locale=candidate):
                    self.assertEqual(
                        "1,234,567원",
                        ct.format_value(self.OK, sc.Unit.KRW, 1234567),
                    )
        finally:
            locale.setlocale(locale.LC_ALL, original)


class TestMetricSerialization(unittest.TestCase):
    def test_computed_metric_carries_formatted_value(self) -> None:
        metric = sc.MetricValue.ok(38400, unit=sc.Unit.KRW, basis=BASIS)
        payload = ct.metric_to_json(metric)
        self.assertEqual("38,400원", payload["value_formatted"])
        self.assertEqual(38400, payload["value"], "원값은 그대로 유지한다")
        self.assertIn("basis", payload)

    def test_uncomputable_metric_omits_basis_and_formatted_keys(self) -> None:
        """★ `"basis": null` 을 내보내지 않는다 — 계약의 `not` 은 **키의 존재**를 본다."""
        metric = sc.MetricValue.unavailable(
            sc.ReasonCode.NO_COST_BASIS, "주문 12건 전부 unit_cost 없음",
            unit=sc.Unit.KRW,
        )
        payload = ct.metric_to_json(metric)
        self.assertNotIn("basis", payload)
        self.assertNotIn("value_formatted", payload)
        self.assertIsNone(payload["value"])
        self.assertIn("value", payload, "value 는 null 로라도 있어야 한다 (required)")

    def test_metric_value_dataclass_has_no_value_formatted_field(self) -> None:
        """★ 생성 주체가 하나임을 구조로 고정한다 (리드 판정 ⇥₂).

        필드가 있으면 호출자가 넘길 수 있고, 넘길 수 있으면 한 곳에서 빠뜨린다.
        """
        self.assertNotIn("value_formatted", sc.MetricValue.__dataclass_fields__)
        self.assertIn("limit_note", sc.MetricValue.__dataclass_fields__)

    def test_limit_note_is_passed_through(self) -> None:
        """`limit_note` 는 호출자가 넘긴다 — `unit` 에서 유도할 수 없다."""
        metric = sc.MetricValue.ok(
            1204, unit=sc.Unit.COUNT, basis=BASIS,
            limit_note="쿠폰 사용 이벤트만 센다",
        )
        self.assertEqual(
            "쿠폰 사용 이벤트만 센다", ct.metric_to_json(metric)["limit_note"]
        )

    def test_derived_metric_carries_its_derivation(self) -> None:
        metric = sc.MetricValue.ok(
            7000, unit=sc.Unit.KRW, basis=BASIS,
            derived=True, derivation="Σ treatment_cost[t] for coupon treatments",
        )
        payload = ct.metric_to_json(metric)
        self.assertIs(True, payload["derived"])
        self.assertTrue(payload["derivation"])

    def test_blocked_by_chain_is_serialised(self) -> None:
        metric = sc.MetricValue.unavailable(
            sc.ReasonCode.NO_COST_BASIS, "원가 근거 없음",
            blocked_by=(
                sc.BlockerRef(sc.BlockerKind.SCHEMA_GAP, "unit_cost",
                              sc.ReasonCode.NO_COST_BASIS),
            ),
        )
        chain = ct.metric_to_json(metric)["blocked_by"]
        self.assertEqual(
            [{"kind": "schema_gap", "ref": "unit_cost",
              "reason_code": "NO_COST_BASIS"}], chain,
        )


class TestEnvelope(unittest.TestCase):
    def test_envelope_has_every_required_key(self) -> None:
        run_id = ct.new_run_id()
        payload = ct.envelope(
            "index", run_id=run_id,
            provenance=ct.build_provenance(source_root="data/raw"),
        )
        for key in _COMMON["envelope"]["required"]:
            with self.subTest(key=key):
                self.assertIn(key, payload)
        self.assertEqual("measurement-publish/v1", payload["contract_version"])
        self.assertEqual("Asia/Seoul", payload["timezone"])

    def test_unknown_artifact_name_is_rejected(self) -> None:
        with self.assertRaises(ContractViolation):
            ct.envelope("not_an_artifact", run_id=ct.new_run_id(), provenance={})

    def test_artifact_names_match_contract_enum(self) -> None:
        self.assertEqual(set(_COMMON["artifact_name"]["enum"]), ct.ARTIFACT_NAMES)

    def test_notices_carry_assumptions_into_the_artifact(self) -> None:
        """가정은 문서가 아니라 산출물에 붙는다 (P-12)."""
        notice = ct.Notice(
            "REFUND_NOT_ADJUSTED", "assumption",
            "환불·취소를 차감하지 않는다 — 기여이익이 과대평가된다",
            reference="economic-rule-v1.md §6.4 A-REFUND",
        )
        payload = ct.envelope(
            "kpi_report", run_id=ct.new_run_id(), provenance={}, notices=[notice],
        )
        self.assertEqual(
            {"code": "REFUND_NOT_ADJUSTED", "level": "assumption",
             "message": "환불·취소를 차감하지 않는다 — 기여이익이 과대평가된다",
             "reference": "economic-rule-v1.md §6.4 A-REFUND"},
            payload["notices"][0],
        )
        self.assertRegex(notice.code, _COMMON["notice"]["properties"]["code"]["pattern"])


class TestProvenance(unittest.TestCase):
    def test_null_fields_carry_a_reason(self) -> None:
        """★ `null` 에 사유가 없으면 "0 으로 채운 것"과 구분되지 않는다."""
        provenance = ct.build_provenance(source_root="data/raw")
        self.assertIsNone(provenance["simulator_commit"])
        self.assertIn("simulator_commit", provenance["null_reason"])
        self.assertIsNone(provenance["data_version"])
        self.assertIn("data_version", provenance["null_reason"])

    def test_simulator_commit_is_never_invented(self) -> None:
        """C1 에 시뮬레이터가 없다. 빈 문자열이나 0 으로 채우지 않는다."""
        provenance = ct.build_provenance(source_root="data/raw")
        self.assertNotEqual("", provenance["simulator_commit"])
        self.assertNotEqual(0, provenance["simulator_commit"])

    def test_config_hash_is_none_when_file_absent(self) -> None:
        missing = ct.Path("config/does_not_exist.yaml")
        provenance = ct.build_provenance(source_root="data/raw", config_paths=[missing])
        self.assertIsNone(provenance["config_hashes"][str(missing)])

    def test_config_hash_is_recorded_when_present(self) -> None:
        real = ct.Path("config/economic_config.yaml")
        provenance = ct.build_provenance(source_root="data/raw", config_paths=[real])
        self.assertEqual(64, len(provenance["config_hashes"][str(real)]))

    def test_schema_version_comes_from_code(self) -> None:
        self.assertEqual(
            sc.SCHEMA_VERSION,
            ct.build_provenance(source_root="x")["schema_version"],
        )


class TestFailClosed(unittest.TestCase):
    """★ 계약을 어긴 게시물은 **문자열조차 만들지 않는다**."""

    def _uncomputable(self, **extra: object) -> dict:
        return {"status": "unavailable", "value": None,
                "reason_code": "NO_COST_BASIS", "reason_detail": "d", **extra}

    def test_zero_fill_is_blocked(self) -> None:
        with self.assertRaises(ContractViolation) as caught:
            ct.dump({"m": dict(self._uncomputable(), value=0)})
        self.assertIn("USP-1", str(caught.exception))

    def test_basis_on_uncomputable_is_blocked(self) -> None:
        with self.assertRaises(ContractViolation):
            ct.dump({"m": self._uncomputable(basis={"population": "P"})})

    def test_formatted_on_uncomputable_is_blocked(self) -> None:
        with self.assertRaises(ContractViolation):
            ct.dump({"m": self._uncomputable(value_formatted="0원")})

    def test_missing_formatted_on_computed_is_blocked(self) -> None:
        with self.assertRaises(ContractViolation):
            ct.dump({"m": {"status": "ok", "value": 1, "unit": "krw",
                           "basis": {"population": "P"}}})

    def test_zero_denominator_with_ok_is_blocked(self) -> None:
        with self.assertRaises(ContractViolation):
            ct.dump({"m": {"status": "ok", "value": 0, "unit": "ratio",
                           "value_formatted": "0.0%",
                           "basis": {"population": "P", "denominator": 0}}})

    def test_derived_without_derivation_is_blocked(self) -> None:
        with self.assertRaises(ContractViolation):
            ct.dump({"m": {"status": "ok", "value": 1, "unit": "krw",
                           "value_formatted": "1원", "derived": True,
                           "basis": {"population": "P"}}})

    def test_violation_is_found_at_any_depth(self) -> None:
        """산출물마다 `metric_value` 의 깊이가 다르므로 경로를 손으로 적지 않는다."""
        nested = {"totals": {"by_source": {"commerce": [self._uncomputable(value=0)]}}}
        with self.assertRaises(ContractViolation) as caught:
            ct.dump(nested)
        self.assertIn("commerce", str(caught.exception))

    def test_valid_payload_serialises(self) -> None:
        payload = {
            "metric": ct.metric_to_json(
                sc.MetricValue.ok(38400, unit=sc.Unit.KRW, basis=BASIS)
            ),
            "uncomputable": ct.metric_to_json(
                sc.MetricValue.unavailable(sc.ReasonCode.NO_SOURCE_EVENT, "0건")
            ),
        }
        text = ct.dump(payload)
        self.assertEqual(payload, json.loads(text))

    def test_dump_is_byte_stable(self) -> None:
        """같은 내용 → 같은 바이트. `NFR-001` 해시 대조의 전제다."""
        payload = {"b": 1, "a": ct.metric_to_json(
            sc.MetricValue.ok(1, unit=sc.Unit.COUNT, basis=BASIS))}
        self.assertEqual(ct.dump(payload), ct.dump(dict(reversed(payload.items()))))


if __name__ == "__main__":
    unittest.main()
