import hashlib
import unittest
from datetime import date

from src.decision.features.d1_serialization import (
    D1ContractError, Float32, Float64, calendar_date, canonical_set, file_sha256,
    instant, semantic_hash, strict_json, tlv,
)


class SerializationTests(unittest.TestCase):
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
