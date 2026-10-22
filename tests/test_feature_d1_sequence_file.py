"""Exact Parquet bytes, typed logical values, null and evidence counterexamples."""

from copy import deepcopy
from datetime import date
from importlib.util import find_spec
from io import BytesIO
import hashlib
import unittest
from unittest.mock import patch

from src.decision.features.d1_evidence import evidence_hashes, verify_evidence
from src.decision.features.d1_raw_sequence import generate_raw_sequences
from src.decision.features.d1_sequence_file import (
    DICTIONARY_HASH, VERSION, adapt_sequences, decode_sequence_file, encode_sequence_file,
    numeric_tokens, sequence_value_hash, validate_sequence_rows,
)
from src.decision.features.d1_serialization import D1ContractError
from tests.test_feature_d1_evidence import SyntheticEvidenceFixture
from tests.test_feature_d1_calculation import INDEX, ORIGIN, event

ARROW = find_spec("pyarrow") is not None


def three_states():
    records = [event("search", number=2), event("page_view", number=1)]
    f = SyntheticEvidenceFixture(records, roster=("C00000001", "C00000002", "C00000003"))
    f.payload["production"] = f.payload["production"][:2]
    f.add_order(records); f.seal()
    raw, context = f.raw()
    return f, raw, (context,)


class SequenceProjectionTests(unittest.TestCase):
    def test_138_missing_required_proof_stops_pipeline_before_raw_and_adapter(self):
        records = [event("search", number=2), event("page_view", number=1)]

        def pipeline(f, envelope, expected, artifacts):
            context = verify_evidence(envelope, batch=f.batch, policy=f.policy, index_date=INDEX,
                                      expected_files=expected, artifacts=artifacts)
            raw = generate_raw_sequences([context.batch], index_date=INDEX, policy=context.policy,
                observation_claims=context.observation_claims, order_claims=context.order_claims, generated_at=ORIGIN)
            return adapt_sequences(raw, contexts=(context,))

        for count in (1, 2):
            f = SyntheticEvidenceFixture(records); f.add_order(records)
            if count == 2:
                f.add_order(records, entries=[dict(event_id=r["event_id"], ordinal=i)
                                             for i, r in enumerate(reversed(records))])
            f.seal()
            envelope, expected, artifacts = deepcopy((f.envelope, f.expected, f.artifacts))
            with patch(__name__+".generate_raw_sequences", wraps=generate_raw_sequences) as raw_call:
                rows = pipeline(f, envelope, expected, artifacts)
                raw_call.assert_called_once()
                self.assertEqual(rows[0]["state"], "VALID" if count == 1 else "UNKNOWN")
            if count == 2:
                envelope["payload"]["ordering"].pop(0)
                envelope["payload"]["ordering_value_sha256"] = evidence_hashes(
                    envelope["payload"], batch=f.batch, policy=f.policy, index_date=INDEX)[1]
                with patch(__name__+".generate_raw_sequences", wraps=generate_raw_sequences) as raw_call:
                    with self.assertRaisesRegex(D1ContractError, "required external FilePins not verified"):
                        pipeline(f, envelope, expected, artifacts)
                    raw_call.assert_not_called()

    def test_literal_tokens_three_states_and_exact_zero_vs_null(self):
        _, raw, contexts = three_states()
        rows = adapt_sequences(raw, contexts=contexts)
        self.assertEqual([r["state"] for r in rows], ["VALID", "EMPTY_COMPLETE", "UNKNOWN"])
        self.assertEqual(rows[0]["tokens"], ["PAD"]*28+["search", "page_view"])
        self.assertEqual(rows[0]["relative_gap_ms"], [None]*29+[0])
        self.assertEqual(rows[0]["gap_mask"], [False]*29+[True])
        self.assertEqual(rows[1]["tokens"], ["PAD"]*30)
        self.assertEqual(rows[1]["reasons"], ["NO_SEQUENCE_INFORMATION"])
        self.assertEqual(rows[2]["reasons"], ["OBSERVATION_UNKNOWN"])
        for name in ("length", "tokens", "mask", "relative_gap_ms", "gap_mask"):
            self.assertIsNone(rows[2][name])
        for row in rows:
            self.assertEqual(row["sequence_version"], VERSION)
            self.assertEqual(row["token_dictionary_semantic_hash"], DICTIONARY_HASH)
        channels = numeric_tokens(rows, contexts=contexts)
        self.assertEqual(channels[tuple(("fixture", "commerce", "C00000001", INDEX))], [0]*28+[15,8])
        self.assertIsNone(channels[tuple(("fixture", "commerce", "C00000003", INDEX))])

    def test_adapter_keeps_original_raw_audit_and_no_shared_mutable_channels(self):
        _, raw, contexts = three_states()
        before = deepcopy(raw)
        rows = adapt_sequences(raw, contexts=contexts)
        rows[0]["mask"][0] = True
        self.assertEqual(raw, before)
        self.assertIn("selected_event_ids", raw.rows[0])
        self.assertIn("audit_counts", raw.rows[0])

    def test_physical_republication_generated_at_and_order_are_meaning_invariant(self):
        f, raw, contexts = three_states()
        rows = adapt_sequences(raw, contexts=contexts)
        value = sequence_value_hash(rows, contexts=contexts)
        raw.rows.reverse()
        for row in raw.rows:
            row["generated_at"] = "2026-10-22T01:00:00+09:00"
        self.assertEqual(value, sequence_value_hash(adapt_sequences(raw, contexts=contexts), contexts=contexts))
        f.payload["reception"]["request_id"] = "republication-only"
        f.seal(prefix="new", reverse_events=True)
        new_raw, new_context = f.raw()
        new_rows = adapt_sequences(new_raw, contexts=(new_context,))
        self.assertEqual(value, sequence_value_hash(new_rows, contexts=(new_context,)))
        self.assertNotEqual(rows[0]["order_evidence_refs"], new_rows[0]["order_evidence_refs"])
        with self.assertRaisesRegex(D1ContractError, "exact order evidence pin mismatch"):
            validate_sequence_rows(rows, contexts=(new_context,))

    def test_changed_logical_token_or_real_gap_changes_value_hash(self):
        _, raw, contexts = three_states()
        rows = adapt_sequences(raw, contexts=contexts)
        before = sequence_value_hash(rows, contexts=contexts)
        for name, value in (("tokens", "purchase"), ("relative_gap_ms", 1)):
            changed = deepcopy(rows); changed[0][name][-1] = value
            self.assertNotEqual(before, sequence_value_hash(changed, contexts=contexts))

    def test_invalid_null_zero_dtype_and_masks_are_rejected(self):
        _, raw, contexts = three_states()
        rows = adapt_sequences(raw, contexts=contexts)
        for name, position, value in (("relative_gap_ms",28,0), ("relative_gap_ms",29,None),
            ("relative_gap_ms",29,0.0), ("relative_gap_ms",29,True), ("relative_gap_ms",29,2**63),
            ("mask",28,1), ("gap_mask",29,False), ("tokens",29,"VIEW")):
            changed = deepcopy(rows); changed[0][name][position] = value
            with self.subTest(name=name, position=position, value=value), self.assertRaises(D1ContractError):
                sequence_value_hash(changed, contexts=contexts)

    def test_unknown_cannot_be_filled_and_empty_cannot_be_relabelled(self):
        _, raw, contexts = three_states()
        rows = adapt_sequences(raw, contexts=contexts)
        for field, value in (("tokens",["PAD"]*30), ("length",0), ("reasons",["NO_SEQUENCE_INFORMATION"])):
            changed=deepcopy(rows);changed[2][field]=value
            with self.subTest(field=field), self.assertRaisesRegex(D1ContractError,"UNKNOWN requires"):
                validate_sequence_rows(changed, contexts=contexts)
        rows[1]["state"]="VALID"
        with self.assertRaisesRegex(D1ContractError,"state/length/reasons"):
            validate_sequence_rows(rows,contexts=contexts)

    def test_required_customer_keys_and_typed_dates_are_preserved(self):
        _, raw, contexts = three_states()
        rows = adapt_sequences(raw, contexts=contexts)
        for changed in (rows[:-1], rows+[deepcopy(rows[0])]):
            with self.assertRaisesRegex(D1ContractError,"key set|rows missing"):
                validate_sequence_rows(changed,contexts=contexts)
        rows[0]["index_date"]="2026-10-20"
        with self.assertRaisesRegex(D1ContractError,"typed date"):
            validate_sequence_rows(rows,contexts=contexts)

    def test_raw_input_version_evidence_and_required_order_pin_are_strict(self):
        _, raw, contexts = three_states()
        altered=deepcopy(raw);altered.reproducibility[0]["input_value_sha256"]="a"*64
        with self.assertRaisesRegex(D1ContractError,"reproducibility/evidence"):
            adapt_sequences(altered,contexts=contexts)
        altered=deepcopy(raw);altered.rows[0]["tokens"][-1]=True
        with self.assertRaisesRegex(D1ContractError,"numeric token invalid"):
            adapt_sequences(altered,contexts=contexts)
        rows=adapt_sequences(raw,contexts=contexts);rows[0]["order_evidence_refs"]=[]
        with self.assertRaisesRegex(D1ContractError,"required order evidence links missing"):
            validate_sequence_rows(rows,contexts=contexts)

    def test_submillisecond_gap_remains_unknown_not_rounded(self):
        f=SyntheticEvidenceFixture([event("search","2026-10-01T00:00:00+09:00",1),
            event("page_view","2026-10-01T00:00:00.000001+09:00",2)])
        raw,c=f.raw();rows=adapt_sequences(raw,contexts=(c,))
        self.assertEqual(rows[0]["state"],"UNKNOWN")
        self.assertIsNone(rows[0]["relative_gap_ms"])
        self.assertEqual(rows[0]["reasons"],["CONTRACT_UNRESOLVED"])


@unittest.skipUnless(ARROW,"pyarrow 미설치: 실제 Parquet 파일 시험만 skip")
class SequenceParquetTests(unittest.TestCase):
    def setUp(self):
        _,raw,self.contexts=three_states()
        self.rows=adapt_sequences(raw,contexts=self.contexts)

    def decode(self, artifact):
        return decode_sequence_file(artifact.data,contexts=self.contexts,
            expected_file_sha256=artifact.file_sha256,expected_value_sha256=artifact.value_sha256)

    def test_actual_Parquet_round_trip_three_states_types_and_numeric_channels(self):
        import pyarrow as pa
        import pyarrow.parquet as pq

        artifact=encode_sequence_file(self.rows,contexts=self.contexts)
        restored=self.decode(artifact)
        self.assertEqual(restored,self.rows)
        self.assertEqual(numeric_tokens(restored,contexts=self.contexts),numeric_tokens(self.rows,contexts=self.contexts))
        schema=pq.read_schema(BytesIO(artifact.data))
        self.assertEqual(schema.field("relative_gap_ms").type.value_type,pa.int64())
        self.assertTrue(schema.field("relative_gap_ms").type.value_field.nullable)
        self.assertEqual(schema.field("tokens").type.value_type,pa.string())
        self.assertEqual(schema.field("mask").type.value_type,pa.bool_())
        self.assertEqual(schema.field("index_date").type,pa.date32())
        self.assertIs(type(restored[0]["index_date"]),date)

    def test_generated_at_compression_and_physical_order_change_only_file_hash(self):
        a=encode_sequence_file(self.rows,contexts=self.contexts,compression=None,generated_at=ORIGIN)
        b=encode_sequence_file(list(reversed(self.rows)),contexts=self.contexts,compression="gzip",
            generated_at="2026-10-22T00:00:00+09:00")
        self.assertEqual(a.value_sha256,b.value_sha256)
        self.assertNotEqual(a.file_sha256,b.file_sha256)
        self.decode(a);self.decode(b)
        with self.assertRaisesRegex(D1ContractError,"exact sequence file hash mismatch"):
            decode_sequence_file(b.data,contexts=self.contexts,expected_file_sha256=a.file_sha256,
                                 expected_value_sha256=a.value_sha256)

    def test_resealed_wrong_dtype_fails_dtype_check_not_hash(self):
        import pyarrow as pa
        import pyarrow.parquet as pq

        artifact=encode_sequence_file(self.rows,contexts=self.contexts)
        table=pq.read_table(BytesIO(artifact.data))
        position=table.schema.get_field_index("relative_gap_ms")
        field=pa.field("relative_gap_ms",pa.list_(pa.field("element",pa.float64(),True)),True)
        table=table.set_column(position,field,table.column(position).cast(field.type))
        buffer=BytesIO();pq.write_table(table,buffer);data=buffer.getvalue()
        with self.assertRaisesRegex(D1ContractError,"Parquet dtype/schema mismatch"):
            decode_sequence_file(data,contexts=self.contexts,expected_file_sha256=hashlib.sha256(data).hexdigest(),
                                 expected_value_sha256=artifact.value_sha256)

    def test_resealed_changed_value_rejected_against_independent_expected(self):
        artifact=encode_sequence_file(self.rows,contexts=self.contexts)
        changed=deepcopy(self.rows);changed[0]["tokens"][-1]="purchase"
        other=encode_sequence_file(changed,contexts=self.contexts)
        with self.assertRaisesRegex(D1ContractError,"sequence value hash mismatch"):
            decode_sequence_file(other.data,contexts=self.contexts,expected_file_sha256=other.file_sha256,
                                 expected_value_sha256=artifact.value_sha256)

    def test_missing_exact_evidence_link_rejected_even_when_file_is_resealed(self):
        import pyarrow as pa
        import pyarrow.parquet as pq

        artifact=encode_sequence_file(self.rows,contexts=self.contexts)
        table=pq.read_table(BytesIO(artifact.data));rows=deepcopy(self.rows)
        rows[0]["order_evidence_refs"]=[]
        buffer=BytesIO();pq.write_table(pa.Table.from_pylist(rows,schema=table.schema),buffer);data=buffer.getvalue()
        with self.assertRaisesRegex(D1ContractError,"required order evidence links missing"):
            decode_sequence_file(data,contexts=self.contexts,expected_file_sha256=hashlib.sha256(data).hexdigest(),
                                 expected_value_sha256=artifact.value_sha256)
