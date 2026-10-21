"""Pre-fit, in-memory sequences; no model, publication or legacy-loader adapter."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime, timezone
import re

from src.measurement.schema import SCHEMA_VERSION, check_identifier
from .d1_calculate import FEATURE_VERSION
from .d1_feature_inputs import (
    EVENT_TYPES, Entity, EventBatch, ObservationClaim, TimePolicy,
    check_claims, observation_reasons, timestamp,
)
from .d1_semantics import key
from .d1_serialization import require, semantic_hash, tlv

SEQUENCE_VERSION = "d1-raw-sequence/1-proposed"
TOKEN_VERSION = "d1-sequence-tokens/1"
TOKEN_VOCABULARY = (
    "PAD", "add_to_cart", "campaign_exposed", "checkout_start", "coupon_clicked",
    "coupon_exposed", "coupon_use", "cs_contact", "page_view", "product_view",
    "purchase", "push_sent", "remove_from_cart", "return_visit", "review", "search", "session_start",
)
TOKEN_IDS = {token: number for number, token in enumerate(TOKEN_VOCABULARY)}
require(frozenset(TOKEN_VOCABULARY[1:]) == EVENT_TYPES, "sequence vocabulary/public schema mismatch")


@dataclass(frozen=True)
class OrderClaim:
    """Explicit synthetic evidence, not an approved production ordering contract."""

    entity: Entity
    at: str | datetime
    ordinals: tuple[tuple[str, int], ...]
    input_value_sha256: str
    provider: str
    contract_version: str
    evidence_ref: str
    purpose: str

    def __post_init__(self):
        require(type(self.entity) is Entity, "order claim entity required")
        object.__setattr__(self, "at", timestamp(self.at))
        require(self.purpose == "synthetic" and self.contract_version == "d1-order-fixture/1",
                "actual order provider contract unresolved: SD3")
        require(type(self.ordinals) is tuple and bool(self.ordinals), "explicit ordinal entries required")
        for item in self.ordinals:
            require(type(item) is tuple and len(item) == 2, "invalid ordinal entry")
            event_id, ordinal = item
            require(type(event_id) is str and check_identifier("event_id", event_id), "invalid order event ID")
            require(type(ordinal) is int and 0 <= ordinal < 2**63, "invalid ordinal")
        require(len({item[0] for item in self.ordinals}) == len(self.ordinals), "duplicate order event ID")
        require(len({item[1] for item in self.ordinals}) == len(self.ordinals), "duplicate ordinal")
        require(type(self.input_value_sha256) is str and
                bool(re.fullmatch(r"[0-9a-f]{64}", self.input_value_sha256)), "order input identity required")
        require(all(type(value) is str and value for value in (self.provider, self.evidence_ref)),
                "order provider/reference required")

    def record(self):
        return dict(entity=self.entity.record(), at=self.at,
                    ordinals=[list(item) for item in sorted(self.ordinals, key=lambda item: item[1])],
                    input_value_sha256=self.input_value_sha256, provider=self.provider,
                    contract_version=self.contract_version, evidence_ref=self.evidence_ref, purpose=self.purpose)


@dataclass(frozen=True)
class RawSequenceOutput:
    rows: list[dict]
    reproducibility: list[dict]
    token_vocabulary: tuple[str, ...] = TOKEN_VOCABULARY


def _selection(events, claims):
    groups = defaultdict(list)
    for event in events:
        groups[event["timestamp"]].append(event)
    needed, count = [], 0
    for at in sorted(groups, reverse=True):
        needed.append((at, groups[at]))
        count += len(groups[at])
        if count >= 30:
            break
    reasons, refs, ordered = set(), [], []
    for at, group in reversed(needed):
        if len(group) == 1:
            ordered.extend(group)
            continue
        applicable = [claim for claim in claims if claim.at == at]
        if len(applicable) != 1 or {item[0] for item in applicable[0].ordinals} != {
                event["event_id"] for event in group}:
            reasons.add("AMBIGUOUS_EVENT_ORDER")
            continue
        proof = applicable[0]
        ordinal = dict(proof.ordinals)
        ordered.extend(sorted(group, key=lambda event: ordinal[event["event_id"]]))
        refs.append(proof.evidence_ref)
    audit = dict(observed_events=len(events), observed_candidates=min(30, len(events)),
                 needed_order_groups=sum(len(group) > 1 for _, group in needed),
                 selection_boundary_group_events=len(needed[-1][1]) if needed else 0,
                 events_older_than_selection_groups=len(events)-count)
    # Never fill a selection with arbitrary members of an unresolved tie.
    return ordered[-30:] if not reasons else [], reasons, tuple(sorted(set(refs))), audit


def generate_raw_sequences(batches: list[EventBatch], *, index_date: date, policy: TimePolicy | None = None,
                           observation_claims: tuple[ObservationClaim, ...] = (),
                           order_claims: tuple[OrderClaim, ...] = (),
                           generated_at: str | datetime | None = None) -> RawSequenceOutput:
    require(type(policy) is TimePolicy, "explicit time policy required; #126 unresolved")
    require(type(batches) is list and all(type(batch) is EventBatch for batch in batches), "explicit source batches required")
    require(all(type(claim) is ObservationClaim for claim in observation_claims), "invalid observation claim type")
    require(all(type(claim) is OrderClaim for claim in order_claims), "invalid order claim type")
    snapshots = {(batch.source, batch.entity_namespace): batch for batch in batches}
    require(len(snapshots) == len(batches), "duplicate source/namespace snapshot in transaction")
    entities = {entity for batch in batches for entity in batch.entities}
    require(all(claim.entity in entities for claim in (*observation_claims, *order_claims)),
            "evidence source/customer outside transaction")
    checked = []
    for batch in batches:
        batch.guard(policy, index_date)
        relevant = tuple(claim for claim in observation_claims if
                         (claim.entity.source, claim.entity.entity_namespace) == (batch.source, batch.entity_namespace))
        checked.append(check_claims(batch, relevant))
    for claim in order_claims:
        batch = snapshots[(claim.entity.source, claim.entity.entity_namespace)]
        require(claim.input_value_sha256 == batch.input_value_sha256, "order input identity mismatch")
        policy.check_precision(claim.at)
        require(policy.permits(claim.at), "forbidden-time order claim")
    generated_at = timestamp(datetime.now(timezone.utc) if generated_at is None else generated_at)
    window = policy.window(index_date, None)
    rows, reproducibility = [], []
    for batch, observations in zip(batches, checked):
        batch_orders = tuple(claim for claim in order_claims if
                             (claim.entity.source, claim.entity.entity_namespace) == (batch.source, batch.entity_namespace))
        reproducibility.append(dict(source=batch.source, entity_namespace=batch.entity_namespace,
            sequence_version=SEQUENCE_VERSION, token_version=TOKEN_VERSION, event_contract_version=SCHEMA_VERSION,
            input_value_sha256=batch.input_value_sha256, policy=policy.record(),
            policy_value_sha256=semantic_hash("d1-calculation-policy", policy.record()),
            evidence_value_sha256=semantic_hash("d1-calculation-evidence", [claim.record() for claim in observations]),
            order_claims_value_sha256=semantic_hash("d1-synthetic-order-claims",
                sorted((claim.record() for claim in batch_orders), key=tlv)), population_scope=batch.population_scope))
        for entity in batch.entities:
            events = [event for event in batch.events if event["customer_id"] == entity.customer_id and
                      window.contains(event["timestamp"])]
            claims = tuple(claim for claim in batch_orders if claim.entity == entity)
            selected, reasons, order_refs, audit = _selection(events, claims)
            reasons.update(observation_reasons(batch, entity, EVENT_TYPES, window, observations))
            gaps, details = [None], []
            for first, second in zip(selected, selected[1:]):
                delta = second["timestamp"]-first["timestamp"]
                micros = (delta.days*86400+delta.seconds)*1_000_000+delta.microseconds
                if micros % 1000:
                    reasons.add("CONTRACT_UNRESOLVED")
                    details.append("SUBMILLISECOND_GAP_REPRESENTATION")
                else:
                    gaps.append(micros//1000)
            state, length, tokens, mask, relative_gap_ms, gap_mask = "UNKNOWN", None, None, None, None, None
            if not reasons:
                length = len(selected)
                state = "VALID" if length else "EMPTY_COMPLETE"
                padding = 30-length
                tokens = [0]*padding+[TOKEN_IDS[event["event_type"]] for event in selected]
                mask = [False]*padding+[True]*length
                relative_gap_ms = [None]*padding+(gaps if length else [])
                gap_mask = [False]*padding+([False]+[True]*(length-1) if length else [])
                if not length:
                    reasons.add("NO_SEQUENCE_INFORMATION")
            rows.append(dict(**entity.record(), index_date=index_date, feature_version=FEATURE_VERSION,
                sequence_version=SEQUENCE_VERSION, token_version=TOKEN_VERSION, feature_cutoff_time=policy.boundary,
                generated_at=generated_at, state=state, length=length, tokens=tokens, mask=mask,
                relative_gap_ms=relative_gap_ms, gap_mask=gap_mask, reasons=sorted(reasons),
                selected_event_ids=[event["event_id"] for event in selected] if state == "VALID" else [],
                order_evidence_refs=list(order_refs), observation_evidence_refs=sorted({claim.evidence_ref
                    for claim in observations if claim.entity == entity and window.overlaps(claim.start, claim.end)}),
                required_window=window.record(), audit_counts=audit, blocking_details=sorted(set(details))))
    return RawSequenceOutput(sorted(rows, key=lambda row: tlv(key(row))),
                             sorted(reproducibility, key=lambda row: (row["source"], row["entity_namespace"])))
