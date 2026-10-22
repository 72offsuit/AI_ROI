"""W0 SequenceRow projection and standalone Parquet bytes, not a bundle loader."""

from __future__ import annotations

from dataclasses import dataclass
from copy import deepcopy
from datetime import date
import hashlib
from io import BytesIO

from .d1_evidence import VerifiedEvidence, closed, digest, file_pin
from .d1_feature_inputs import Entity, check_claims, timestamp
from .d1_raw_sequence import RawSequenceOutput, SEQUENCE_VERSION as RAW_VERSION, TOKEN_VERSION, TOKEN_VOCABULARY
from .d1_serialization import require, semantic_hash, tlv

VERSION = "d1-sequence-file/2-proposed"
DICTIONARY_HASH = "78a1b90abca0144978982a8f2f2e31259796f2e6d6ef031bdff501faa8aa625f"
require(semantic_hash("d1-w0-token-dictionary", dict(token_version=TOKEN_VERSION,
    entries=[dict(id=i, token=t) for i, t in enumerate(TOKEN_VOCABULARY)])) == DICTIONARY_HASH,
    "fixed token dictionary mismatch")
FIELDS = ("entity_namespace source customer_id index_date sequence_version token_version "
          "token_dictionary_semantic_hash state length tokens mask relative_gap_ms gap_mask reasons "
          "order_evidence_refs observation_value_sha256 input_value_sha256")
UNKNOWN_REASONS = {"OBSERVATION_UNKNOWN", "INCOMPLETE_WINDOW", "UNSUPPORTED_EVENT_KIND",
                   "AMBIGUOUS_EVENT_ORDER", "CONTRACT_UNRESOLVED"}


def _key(row):
    return (row["entity_namespace"], row["source"], row["customer_id"], row["index_date"])


def _contexts(contexts):
    require(type(contexts) is tuple and all(type(c) is VerifiedEvidence for c in contexts), "verified evidence contexts required")
    result = {}
    for c in contexts:
        require(c.admission == "BLOCKED_ADMISSION", "synthetic context required")
        k = c.batch.entity_namespace, c.batch.source, c.index_date
        require(k not in result, "duplicate sequence evidence context")
        result[k] = c
    return result


def _logical_contexts(contexts):
    return sorted([dict(entity_namespace=c.batch.entity_namespace, source=c.batch.source,
        index_date=c.index_date, input_value_sha256=c.batch.input_value_sha256,
        observation_value_sha256=c.observation_value_sha256, ordering_value_sha256=c.ordering_value_sha256,
        policy=c.policy.record()) for c in _contexts(contexts).values()], key=tlv)


def validate_sequence_rows(rows, *, contexts):
    """Check logical values and physical evidence links independently of value hash."""
    require(type(rows) is list, "sequence row list required")
    by_context = _contexts(contexts)
    expected = {(e.entity_namespace, e.source, e.customer_id, c.index_date)
                for c in contexts for e in c.batch.entities}
    seen = set()
    for row in rows:
        closed(row, FIELDS, "SequenceRow")
        require(type(row["index_date"]) is date, "sequence index_date must be typed date")
        entity = Entity(row["entity_namespace"], row["source"], row["customer_id"])
        k = _key(row)
        require(k in expected and k not in seen, "sequence key set/duplicate mismatch")
        seen.add(k)
        context = by_context[entity.entity_namespace, entity.source, row["index_date"]]
        require((row["sequence_version"], row["token_version"], row["token_dictionary_semantic_hash"]) ==
                (VERSION, TOKEN_VERSION, DICTIONARY_HASH), "sequence version/dictionary mismatch")
        require(row["input_value_sha256"] == context.batch.input_value_sha256 and
                row["observation_value_sha256"] == context.observation_value_sha256, "sequence evidence/input mismatch")
        digest(row["input_value_sha256"]); digest(row["observation_value_sha256"])
        refs = row["order_evidence_refs"]
        require(type(refs) is list, "order evidence FilePins required")
        allowed = {o.evidence_ref for o in context.order_claims if o.entity == entity}
        pins = {p["path"]: p for p in context.verified_files}
        for ref in refs:
            file_pin(ref)
            require(ref["path"] in allowed and pins.get(ref["path"]) == ref, "exact order evidence pin mismatch")
        require(len({r["path"] for r in refs}) == len(refs), "duplicate order evidence pin")
        require({r["path"] for r in refs} == allowed, "required order evidence links missing")
        reasons = row["reasons"]
        require(type(reasons) is list and all(type(r) is str for r in reasons) and
                len(set(reasons)) == len(reasons), "unique sequence reasons required")
        channels = [row[k] for k in ("tokens", "mask", "relative_gap_ms", "gap_mask")]
        if row["state"] == "UNKNOWN":
            require(row["length"] is None and all(c is None for c in channels) and
                    bool(reasons) and set(reasons) <= UNKNOWN_REASONS, "UNKNOWN requires null channels and unavailable reasons")
            continue
        require(row["state"] in ("VALID", "EMPTY_COMPLETE"), "sequence state")
        length = row["length"]
        require(type(length) is int and 0 <= length <= 30 and
                all(type(c) is list and len(c) == 30 for c in channels), "sequence channel length")
        tokens, mask, gaps, gap_mask = channels
        require(all(type(t) is str and t in TOKEN_VOCABULARY for t in tokens), "unknown token")
        require(all(type(v) is bool for v in mask + gap_mask), "boolean masks required")
        require(all(v is None or type(v) is int and 0 <= v < 2**63 for v in gaps), "nullable Int64 gaps required")
        padding = 30 - length
        require(tokens[:padding] == ["PAD"]*padding and "PAD" not in tokens[padding:] and
                mask == [False]*padding+[True]*length, "left PAD/mask mismatch")
        require(gaps[:min(padding+1, 30)] == [None]*min(padding+1, 30) and
                all(type(g) is int for g in gaps[padding+1:]) and
                gap_mask == [False]*min(padding+1, 30)+[True]*max(length-1, 0), "first/PAD null versus real zero gap mismatch")
        require((row["state"] == "VALID" and length > 0 and not reasons) or
                (row["state"] == "EMPTY_COMPLETE" and length == 0 and reasons == ["NO_SEQUENCE_INFORMATION"]),
                "sequence state/length/reasons mismatch")
    require(seen == expected, "sequence customer rows missing")
    return rows


def adapt_sequences(raw: RawSequenceOutput, *, contexts: tuple[VerifiedEvidence, ...]):
    """Project existing raw output; retain its full audit separately in raw."""
    require(type(raw) is RawSequenceOutput and raw.token_vocabulary == TOKEN_VOCABULARY, "raw sequence dictionary mismatch")
    by_context = _contexts(contexts)
    expected_repro = []
    for c in contexts:
        from src.measurement.schema import SCHEMA_VERSION

        claims = check_claims(c.batch, c.observation_claims)
        expected_repro.append(dict(source=c.batch.source, entity_namespace=c.batch.entity_namespace,
            sequence_version=RAW_VERSION, token_version=TOKEN_VERSION, event_contract_version=SCHEMA_VERSION,
            input_value_sha256=c.batch.input_value_sha256, policy=c.policy.record(),
            policy_value_sha256=semantic_hash("d1-calculation-policy", c.policy.record()),
            evidence_value_sha256=semantic_hash("d1-calculation-evidence", [x.record() for x in claims]),
            order_claims_value_sha256=semantic_hash("d1-synthetic-order-claims", sorted((x.record() for x in c.order_claims), key=tlv)),
            population_scope=c.batch.population_scope))
    require(sorted(raw.reproducibility, key=tlv) == sorted(expected_repro, key=tlv), "raw reproducibility/evidence mismatch")
    rows = []
    for original in raw.rows:
        k = original["entity_namespace"], original["source"], original["index_date"]
        require(k in by_context, "raw context mismatch")
        c = by_context[k]
        require(original["feature_cutoff_time"] == c.policy.boundary and original["sequence_version"] == RAW_VERSION and
                original["token_version"] == TOKEN_VERSION, "raw cutoff/version mismatch")
        tokens = original["tokens"]
        require(tokens is None or type(tokens) is list and all(type(t) is int and 0 <= t < len(TOKEN_VOCABULARY) for t in tokens), "raw numeric token invalid")
        pins = {p["path"]: p for p in c.verified_files}
        require(all(ref in pins for ref in original["order_evidence_refs"]), "raw order evidence missing")
        row = {k: original[k] for k in ("entity_namespace", "source", "customer_id", "index_date", "state", "length",
                                        "mask", "relative_gap_ms", "gap_mask", "reasons")}
        row.update(sequence_version=VERSION, token_version=TOKEN_VERSION, token_dictionary_semantic_hash=DICTIONARY_HASH,
            tokens=None if tokens is None else [TOKEN_VOCABULARY[t] for t in tokens],
            order_evidence_refs=[dict(pins[r]) for r in original["order_evidence_refs"]],
            observation_value_sha256=c.observation_value_sha256, input_value_sha256=c.batch.input_value_sha256)
        rows.append(deepcopy(row))
    validate_sequence_rows(rows, contexts=contexts)
    return rows


def sequence_value_hash(rows, *, contexts):
    validate_sequence_rows(rows, contexts=contexts)
    logical = [{k: (sorted(v) if k == "reasons" else v) for k, v in row.items()
                if k != "order_evidence_refs"} for row in rows]
    return semantic_hash("d1-w0-sequence-file", dict(version=VERSION,
        contexts=_logical_contexts(contexts), rows=sorted(logical, key=lambda r: tlv(list(_key(r))))))


def numeric_tokens(rows, *, contexts):
    validate_sequence_rows(rows, contexts=contexts)
    return {tuple(_key(r)): None if r["tokens"] is None else [TOKEN_VOCABULARY.index(t) for t in r["tokens"]] for r in rows}


def _arrow():
    # Import only at the actual Parquet boundary; standard-library validation stays usable.
    import pyarrow as pa
    import pyarrow.parquet as pq
    return pa, pq


def _schema(pa):
    def array(dtype, nullable=False):
        return pa.list_(pa.field("element", dtype, nullable=nullable))
    pin = pa.struct([pa.field("path", pa.string(), False), pa.field("file_sha256", pa.string(), False),
                     pa.field("media_type", pa.string(), False), pa.field("bytes", pa.int64(), False)])
    fields = []
    types = dict(index_date=pa.date32(), length=pa.int64(), tokens=array(pa.string()),
        mask=array(pa.bool_()), relative_gap_ms=array(pa.int64(), True), gap_mask=array(pa.bool_()),
        reasons=array(pa.string()), order_evidence_refs=array(pin))
    for name in FIELDS.split():
        fields.append(pa.field(name, types.get(name, pa.string()), name in ("length", "tokens", "mask", "relative_gap_ms", "gap_mask")))
    return pa.schema(fields)


@dataclass(frozen=True)
class SequenceFile:
    data: bytes
    file_sha256: str
    value_sha256: str


def encode_sequence_file(rows, *, contexts, compression="snappy", generated_at=None):
    value_hash = sequence_value_hash(rows, contexts=contexts)
    pa, pq = _arrow()
    metadata = {b"sequence_version": VERSION.encode(), b"token_dictionary_semantic_hash": DICTIONARY_HASH.encode(),
                b"value_sha256": value_hash.encode()}
    if generated_at is not None:
        metadata[b"generated_at"] = timestamp(generated_at).isoformat().encode()
    schema = _schema(pa).with_metadata(metadata)
    table = pa.Table.from_pylist(rows, schema=schema)
    buffer = BytesIO()
    pq.write_table(table, buffer, compression=compression)
    data = buffer.getvalue()
    return SequenceFile(data, hashlib.sha256(data).hexdigest(), value_hash)


def decode_sequence_file(data, *, contexts, expected_file_sha256, expected_value_sha256):
    digest(expected_file_sha256); digest(expected_value_sha256)
    require(type(data) is bytes and hashlib.sha256(data).hexdigest() == expected_file_sha256, "exact sequence file hash mismatch")
    pa, pq = _arrow()
    table = pq.read_table(BytesIO(data))
    require(table.schema.remove_metadata().equals(_schema(pa)), "sequence Parquet dtype/schema mismatch")
    meta = table.schema.metadata or {}
    require(set(meta) in ({b"sequence_version", b"token_dictionary_semantic_hash", b"value_sha256"},
                         {b"sequence_version", b"token_dictionary_semantic_hash", b"value_sha256", b"generated_at"}) and
            meta[b"sequence_version"] == VERSION.encode() and meta[b"token_dictionary_semantic_hash"] == DICTIONARY_HASH.encode(), "sequence file metadata mismatch")
    if b"generated_at" in meta:
        timestamp(meta[b"generated_at"].decode("utf-8"))
    rows = table.to_pylist()
    actual = sequence_value_hash(rows, contexts=contexts)
    require(actual == expected_value_sha256 and meta[b"value_sha256"] == actual.encode(), "sequence value hash mismatch")
    return rows
