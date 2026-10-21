import hashlib
import unittest
from datetime import date, datetime, timedelta, timezone
from unittest.mock import patch

from src.decision.features.d1_serialization import (
    D1ContractError, Float32, Float64, calendar_date, canonical_set, file_sha256,
    instant, semantic_hash, strict_json, tlv,
)


class SerializationTests(unittest.TestCase):
    def test_131_F1_both_parsers_receive_exact_six_digit_fraction(self):
        from src.decision.features.d1_feature_inputs import timestamp
        from src.measurement.timeparse import parse_datetime

        for fn, module in ((instant, "d1_serialization"), (timestamp, "d1_feature_inputs")):
            for fraction in ("", ".1", ".12", ".123", ".1234", ".12345", ".123456"):
                value = "1970-01-01T00:00:00"+fraction+"Z"
                expected = "1970-01-01T00:00:00"+(fraction.ljust(7, "0") if fraction else "")+"Z"
                with self.subTest(fn=fn.__name__, fraction=fraction), patch(
                        f"src.decision.features.{module}.parse_datetime", wraps=parse_datetime) as parser:
                    fn(value)
                    parser.assert_called_once_with(expected)

    def test_131_F2_F3_bad_components_rejected_before_shared_parser(self):
        from src.decision.features.d1_feature_inputs import timestamp

        values = ["2026-10-20T00:00:00"+offset for offset in
                  ("+09:60", "+01:99", "+24:00", "-24:00", "-00:60")]
        values += ["2026-10-20T"+clock+"+09:00" for clock in
                   ("24:00:00", "25:00:00", "23:60:00", "23:59:60")]
        for fn, module in ((instant, "d1_serialization"), (timestamp, "d1_feature_inputs")):
            for value in values:
                with self.subTest(fn=fn.__name__, value=value), patch(
                        f"src.decision.features.{module}.parse_datetime") as parser:
                    with self.assertRaises(D1ContractError): fn(value)
                    parser.assert_not_called()

    def test_131_calendar_syntax_and_excess_precision_rejected_at_both_entries(self):
        from src.decision.features.d1_feature_inputs import timestamp

        values = ("2026-02-29T00:00:00Z", "2026-13-01T00:00:00Z", "2026-04-31T00:00:00Z",
                  "2026-10-20T00:00:00", "2026-10-20 00:00:00Z", "2026-10-20T00:00:00z",
                  "2026-10-20T00:00:00.1234567Z", "2026-10-20T00:00:00.Z",
                  "2026-10-20T00:00:00+0900", "2026-10-20T00:00:00+9:00")
        for fn in (instant, timestamp):
            for value in values:
                with self.subTest(fn=fn.__name__, value=value), self.assertRaises(D1ContractError): fn(value)

    def test_131_both_entries_match_independent_epoch_literals(self):
        from src.decision.features.d1_feature_inputs import timestamp

        for fn in (instant, timestamp):
            for suffix in ("Z", "+00:00"):
                self.assertEqual(tlv(fn("1970-01-01T00:00:00.1"+suffix)).hex(),
                                 "07000000000000000800000000000186a0")
            self.assertEqual(tlv(fn("1970-01-01T00:00:00.1Z")),
                             tlv(fn("1970-01-01T00:00:00.100000Z")))
            self.assertEqual(tlv(fn("1970-01-01T09:00:00.000001+09:00")).hex(),
                             "0700000000000000080000000000000001")
            self.assertEqual(tlv(fn("1969-12-31T19:00:00.000001-05:00")).hex(),
                             "0700000000000000080000000000000001")
            self.assertNotEqual(tlv(fn("1970-01-01T00:00:00.000001Z")),
                                tlv(fn("1970-01-01T00:00:00.000002Z")))

    def test_131_datetime_type_awareness_and_calculation_UTC_errors_preserved(self):
        from src.decision.features.d1_feature_inputs import timestamp

        class DerivedDatetime(datetime):
            pass

        value = datetime(1970, 1, 1, 9, tzinfo=timezone(timedelta(hours=9)))
        for fn in (instant, timestamp):
            self.assertEqual(fn(value), datetime(1970, 1, 1, tzinfo=timezone.utc))
            for invalid in (None, 1, datetime(1970, 1, 1)):
                with self.subTest(fn=fn.__name__, invalid=invalid), self.assertRaises(D1ContractError):
                    fn(invalid)
        derived = DerivedDatetime(1970, 1, 1, tzinfo=timezone.utc)
        self.assertEqual(instant(derived), value)
        with self.assertRaises(D1ContractError): timestamp(derived)
        for value in ("0001-01-01T00:00:00+09:00", "9999-12-31T23:59:59-01:00"):
            with self.assertRaisesRegex(D1ContractError, "timestamp outside supported UTC range"):
                timestamp(value)

    def test_independent_golden_frames(self):
        # Literal wire bytes from the design's tag/BE-length/payload rules.
        cases = [(None, "000000000000000000"), (False, "01000000000000000100"),
                 (True, "01000000000000000101"), (1, "0200000000000000080000000000000001"),
                 (-1, "020000000000000008ffffffffffffffff"),
                 (Float32(1.5), "0400000000000000043fc00000"),
                 (Float64(1.5), "0300000000000000083ff8000000000000"),
                 ("한", "050000000000000003ed959c"),
                 (date(1970, 1, 1), "06000000000000000a313937302d30312d3031"),
                 (instant("1970-01-01T00:00:00Z"), "0700000000000000080000000000000000"),
                 (b"\x00\xff", "0a000000000000000200ff"),
                 ([None, True], "08000000000000001300000000000000000001000000000000000101"),
                 ({"z": None, "a": True}, "09000000000000002705000000000000000161010000000000000001010500000000000000017a000000000000000000")]
        for value, expected in cases:
            with self.subTest(value=value): self.assertEqual(tlv(value).hex(), expected)
        self.assertEqual(file_sha256(b"abc"), "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad")

    def test_domain_envelope_independent_bytes(self):
        # Assemble independently using literal tags; no call to tlv for the reference.
        def frame(tag, payload): return bytes([tag]) + len(payload).to_bytes(8, "big") + payload
        def string(value): return frame(5, value.encode())
        body = frame(9, string("body") + frame(0, b"") + string("domain") + string("golden") +
                     string("serialization") + string("d1-semantic/2-proposed"))
        golden = "9089d2f2bf6a03358b956c1bd9ef35770e8bd21f24e7e214cf6b30b82d47326f"
        self.assertEqual(hashlib.sha256(body).hexdigest(), golden)
        self.assertEqual(semantic_hash("golden", None), golden)

    def test_types_time_and_order(self):
        self.assertEqual(tlv(-0.0), tlv(0.0))
        self.assertEqual(tlv(Float32(-0.0)), tlv(Float32(0.0)))
        self.assertEqual(tlv(instant("2026-10-20T00:00:00+09:00")), tlv(instant("2026-10-19T15:00:00Z")))
        self.assertNotEqual(tlv(None), tlv(0))
        self.assertNotEqual(tlv(0), tlv(0.0))
        self.assertNotEqual(tlv(Float32(0.0)), tlv(Float64(0.0)))
        self.assertNotEqual(tlv([1, 2]), tlv([2, 1]))
        self.assertEqual(tlv({"한": 1, "a": 2}), tlv({"a": 2, "한": 1}))
        self.assertNotEqual(tlv("é"), tlv("e\u0301"))
        self.assertEqual(calendar_date("2026-10-20"), date(2026, 10, 20))

    def test_invalid_values_rejected(self):
        cases = [lambda: tlv(2**63), lambda: tlv(float("nan")), lambda: tlv(float("inf")),
                 lambda: tlv(Float32(1e40)), lambda: tlv(Float64(10**400)),
                 lambda: tlv("\ud800"), lambda: tlv({1: 2}),
                 lambda: canonical_set([1, 1]), lambda: instant("2026-10-20T00:00:00"),
                 lambda: instant("2026-10-20T00:00:00.1234567Z"),
                 lambda: strict_json(b'{"a":1,"a":2}'), lambda: strict_json(b'"\xff"'),
                 lambda: strict_json(b'{"a":1e999}'), lambda: strict_json(b'{"a":NaN}'),
                 lambda: strict_json(b'"\\ud800"')]
        for case in cases:
            with self.subTest(case=case), self.assertRaises(D1ContractError): case()

    def test_HL03_invalid_offset_components_and_syntax_rejected(self):
        for suffix in ("+09:60", "+01:99", "-00:60", "+24:00", "-24:00", "+99:00",
                       "+9:00", "+0900", "+09:0", "++09:00", "Z+09:00", ""):
            with self.subTest(suffix=suffix), self.assertRaises(D1ContractError):
                instant("2026-10-20T00:00:00" + suffix)

    def test_HL03_valid_offsets_and_microsecond_literal_payloads(self):
        for value in ("1970-01-01T09:00:00+09:00", "1969-12-31T19:00:00-05:00",
                      "1970-01-01T23:59:00+23:59", "1969-12-31T00:01:00-23:59",
                      "1970-01-01T00:00:00+00:00", "1970-01-01T00:00:00Z"):
            with self.subTest(value=value):
                self.assertEqual(tlv(instant(value)).hex(), "0700000000000000080000000000000000")
        for digits, micros in (("1", 100000), ("12", 120000), ("123", 123000),
                               ("1234", 123400), ("12345", 123450), ("123456", 123456)):
            self.assertEqual(tlv(instant(f"1970-01-01T00:00:00.{digits}Z"))[-8:],
                             micros.to_bytes(8, "big", signed=True))
        self.assertEqual(tlv(instant("1970-01-01T00:00:00.000001Z")).hex(),
                         "0700000000000000080000000000000001")
        self.assertNotEqual(tlv(instant("1970-01-01T00:00:00.123456Z")),
                            tlv(instant("1970-01-01T00:00:00.123455Z")))

    def test_HL04_underflow_and_direct_signed_zero_use_literal_positive_zero(self):
        hashes = set()
        for value in (-1e-50, 1e-50, -0.0, 0.0):
            with self.subTest(value=value):
                self.assertEqual(tlv(Float32(value)).hex(), "04000000000000000400000000")
                hashes.add(semantic_hash("float32-underflow", Float32(value)))
        self.assertEqual(len(hashes), 1)
        self.assertNotEqual(tlv(Float64(-1e-50)), tlv(Float64(0.0)))

    def test_HL04_representable_nonzero_and_dtype_are_preserved(self):
        for value, payload in ((1.5, "3fc00000"), (-1.5, "bfc00000"),
                               (2**-149, "00000001"), (-2**-149, "80000001")):
            self.assertEqual(tlv(Float32(value)).hex(), "040000000000000004" + payload)
        self.assertNotEqual(tlv(Float32(0.0)), tlv(Float64(0.0)))
        for value in (float("nan"), float("inf"), -float("inf"), 1e40, -1e40):
            with self.subTest(value=value), self.assertRaises(D1ContractError):
                tlv(Float32(value))
