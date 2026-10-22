"""Synthetic W0 I03 binding, never operational provider admission.

The caller fixes every FilePin required for this request, separately from bytes
inventory. All required pins must be verified. No paths are opened.
Evidence JSON bodies equal the record excluding ``provider`` (synthetic profile).
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import date
import hashlib
import re

from src.measurement.schema import check_identifier
from .d1_feature_inputs import EVENT_TYPES, Entity, EventBatch, ObservationClaim, TimePolicy, timestamp
from .d1_raw_sequence import OrderClaim
from .d1_serialization import require, semantic_hash, strict_json, tlv

PROFILE = "d1-synthetic-evidence/1-proposed"
DIRECTION = "0ddb68ca2e862ce43d98f3b2ef2468b4f6cd84053a8ab220b2a0a107b746513d"
MEDIA = {"application/json", "application/x-ndjson", "application/vnd.apache.parquet", "application/octet-stream"}


def closed(value, fields, name):
    require(type(value) is dict and set(value) == set(fields.split()), f"{name}: closed fields required")


def digest(value):
    require(type(value) is str and re.fullmatch(r"[0-9a-f]{64}", value) is not None, "invalid SHA256")
    return value


def text(value):
    require(type(value) is str and bool(value), "nonempty text required")
    return value


def file_pin(pin):
    closed(pin, "path file_sha256 media_type bytes", "FilePin")
    path = text(pin["path"])
    require(not path.startswith("/") and "\\" not in path and
            all(p not in ("", ".", "..") for p in path.split("/")), "unsafe relative FilePin path")
    digest(pin["file_sha256"])
    require(pin["media_type"] in MEDIA, "unsupported FilePin media type")
    require(type(pin["bytes"]) is int and 0 <= pin["bytes"] < 2**63, "invalid FilePin byte count")
    return pin


def _period(value):
    closed(value, "start end_exclusive", "Period")
    start, end = timestamp(value["start"]), timestamp(value["end_exclusive"])
    require(start < end, "invalid evidence period")
    return start, end


def _entity(value, batch):
    closed(value, "entity_namespace source customer_id", "Entity")
    entity = Entity(**value)
    require(entity in batch.entities, "evidence source/namespace/customer mismatch")
    return entity


def _needed(batch, policy, index_date):
    window = policy.window(index_date, None)
    groups = defaultdict(lambda: defaultdict(list))
    for event in batch.events:
        if window.contains(event["timestamp"]):
            groups[Entity(batch.entity_namespace, batch.source, event["customer_id"])][event["timestamp"]].append(event)
    needed = {}
    for entity, by_time in groups.items():
        count = 0
        for at in sorted(by_time, reverse=True):
            group = by_time[at]
            if len(group) > 1:
                needed[entity, at] = {e["event_id"] for e in group}
            count += len(group)
            if count >= 30:
                break
    return needed


def _provider_meaning(p):
    return {k: (timestamp(v) if k == "available_as_of" and v is not None else v)
            for k, v in p.items() if k not in ("agreement_record", "evidence_record")}


def _meaning(record):
    """Typed, closed logical projection; physical pins cannot enter indirectly."""
    result = {}
    for k, v in record.items():
        if k in ("events_ref", "roster_ref", "production_evidence_refs", "delivery_evidence_ref", "request_id"):
            continue
        if k == "provider":
            result[k] = _provider_meaning(v)
        elif k in ("period", "requested_period"):
            result[k] = list(_period(v))
        elif k == "gaps":
            result[k] = sorted((list(_period(g)) for g in v), key=tlv)
        elif k in ("at", "upper_exclusive"):
            result[k] = timestamp(v)
        elif k == "event_types":
            result[k] = sorted(v)
        elif k == "ordinals":
            result[k] = sorted(v, key=tlv)
        else:
            result[k] = v
    return result


def evidence_hashes(payload, *, batch, policy, index_date):
    """Sealing helper, not a validator. verify_evidence checks all inputs/pins."""
    needed = _needed(batch, policy, index_date)
    orders = [_meaning(c) for c in payload["ordering"]
              if (Entity(**c["entity"]), timestamp(c["at"])) in needed]
    ordering = semantic_hash("d1-w0-order", dict(profile=PROFILE, claims=sorted(orders, key=tlv)))
    observation = semantic_hash("d1-w0-observation", dict(profile=PROFILE,
        input_value_sha256=batch.input_value_sha256,
        policy=policy.record(),
        production=sorted((_meaning(c) for c in payload["production"]), key=tlv),
        delivery=_meaning(payload["delivery"]), reception=_meaning(payload["reception"])))
    return observation, ordering


@dataclass(frozen=True)
class VerifiedEvidence:
    batch: EventBatch
    policy: TimePolicy
    index_date: date
    observation_claims: tuple[ObservationClaim, ...]
    order_claims: tuple[OrderClaim, ...]
    observation_value_sha256: str
    ordering_value_sha256: str
    verified_files: tuple[dict, ...]
    admission: str = "BLOCKED_ADMISSION"


def verify_evidence(envelope, *, batch: EventBatch, policy: TimePolicy, index_date: date,
                    expected_files: dict, artifacts: dict) -> VerifiedEvidence:
    """Reject identity/pin errors; represent unproven completeness as unknown.

    expected_files is the independently fixed, complete required path-to-FilePin
    set for this request, not inventory. Unrelated artifacts may remain unused.
    Neither Expected nor the envelope is rewritten to match submitted references.
    """
    closed(envelope, "contract_id contract_version purpose authorization payload", "I03")
    require(envelope["contract_id"] == "I03" and envelope["contract_version"] == "d1-w0-input/1-proposed",
            "unsupported I03 contract")
    require(envelope["purpose"] == "synthetic", "actual input admission excluded: #126/G1/provider evidence")
    require(type(batch) is EventBatch and type(policy) is TimePolicy, "explicit batch/policy required")
    batch.guard(policy, index_date)
    auth = envelope["authorization"]
    closed(auth, "direction_decision_sha256 technical_profile_status shared_contract_status provider_agreements_status approval_records", "Authorization")
    require(auth["direction_decision_sha256"] == DIRECTION and
            auth["technical_profile_status"] in ("proposed", "approved") and
            auth["shared_contract_status"] in ("not_adopted", "adopted") and
            auth["provider_agreements_status"] in ("pending", "accepted"), "authorization shape mismatch")
    p = envelope["payload"]
    closed(p, "source entity_namespace input_value_sha256 production ordering delivery reception observation_profile fu1_profile fu2_profile fu3_profile ordering_value_sha256 observation_value_sha256", "I03 payload")
    require((p["source"], p["entity_namespace"], p["input_value_sha256"]) ==
            (batch.source, batch.entity_namespace, batch.input_value_sha256), "I03 input identity mismatch")
    require((p["observation_profile"], p["fu1_profile"], p["fu2_profile"], p["fu3_profile"]) ==
            ("H_all_16_event_types_conservative", "unused_order_claim_identity_only",
             "duplicate_or_conflicting_tie_is_UNKNOWN", "no_union_of_partial_claims"), "unsupported evidence profiles")
    for v in (p["production"], p["ordering"], auth["approval_records"]):
        require(type(v) is list, "evidence lists required")
    verified = {}

    def pin_bytes(pin, media=None):
        file_pin(pin)
        path = pin["path"]
        require(path in expected_files and expected_files[path] == pin, "external FilePin mismatch")
        data = artifacts.get(path)
        require(type(data) is bytes and len(data) == pin["bytes"] and
                hashlib.sha256(data).hexdigest() == pin["file_sha256"], "artifact byte/hash mismatch")
        require(media is None or pin["media_type"] == media, "artifact media type mismatch")
        verified[path] = dict(pin)
        return data

    for ref in auth["approval_records"]:
        pin_bytes(ref)
    producer_roles = {"S4"} if batch.source == "simulator" else {"commerce_exporter"}

    def provider(record, roles):
        pv = record["provider"]
        closed(pv, "provider_role provider_account agreement_status agreement_record evidence_record input_value_sha256 available_as_of assertion_version", "ProviderEvidence")
        require(pv["provider_role"] in roles, "evidence provider role mismatch")
        require(pv["input_value_sha256"] == batch.input_value_sha256, "provider input identity mismatch")
        require(pv["agreement_status"] in ("synthetic_fixture", "pending", "accepted"), "agreement status")
        require(pv["provider_account"] is None or type(pv["provider_account"]) is str and bool(pv["provider_account"]), "provider account")
        text(pv["assertion_version"])
        available = None if pv["available_as_of"] is None else timestamp(pv["available_as_of"])
        if pv["agreement_record"] is not None:
            pin_bytes(pv["agreement_record"])
        ref = pv["evidence_record"]
        if ref is not None:
            body = strict_json(pin_bytes(ref, "application/json"))
            require(tlv(body) == tlv({k: v for k, v in record.items() if k != "provider"}), "synthetic evidence body mismatch")
        # File existence proves binding, not operational truth or approval.
        return ref is not None and available is not None and policy.permits(available)

    observations = []
    production_refs = []
    encoded = []
    for c in p["production"]:
        closed(c, "entity event_types period state gaps input_value_sha256 provider capability", "Observation")
        entity = _entity(c["entity"], batch)
        require(c["input_value_sha256"] == batch.input_value_sha256, "observation input identity mismatch")
        require(type(c["event_types"]) is list and bool(c["event_types"]) and
                all(type(t) is str for t in c["event_types"]) and len(set(c["event_types"])) == len(c["event_types"]) and
                set(c["event_types"]) <= EVENT_TYPES, "observation event types")
        require(c["capability"] in ("event_capture", "session_universe", "lifetime_funnel", "lifetime_purchases"), "observation capability")
        require(type(c["gaps"]) is list and len({tlv(g) for g in c["gaps"]}) == len(c["gaps"]), "duplicate/invalid gaps")
        start, end = _period(c["period"])
        gaps = tuple(_period(g) for g in c["gaps"])
        require(c["state"] in ("complete", "incomplete", "unknown", "unsupported") and
                all(start <= a < b <= end for a, b in gaps) and not (c["state"] == "complete" and gaps), "invalid observation state/gaps")
        usable = provider(c, producer_roles)
        ref = c["provider"]["evidence_record"]
        if ref is not None:
            production_refs.append(ref)
        encoded.append(tlv(_meaning(c)))
        if c["capability"] == "event_capture":
            observations.append(ObservationClaim(entity, frozenset(c["event_types"]), start, end,
                c["state"] if usable else "unknown", gaps, "synthetic-bound-provider",
                c["provider"]["provider_role"], PROFILE, batch.input_value_sha256,
                ref["path"] if ref else "synthetic-missing-production-evidence"))
    require(len(set(encoded)) == len(encoded), "duplicate observation evidence")

    delivery, reception = p["delivery"], p["reception"]
    closed(delivery, "requested_period upper_exclusive state preserves_order preserves_precision failure_reason provider", "Delivery")
    ds, de = _period(delivery["requested_period"])
    upper = timestamp(delivery["upper_exclusive"])
    require(ds < upper <= de, "delivery upper bound outside requested period")
    require(delivery["state"] in ("complete", "incomplete", "unknown"), "delivery state")
    for name in ("preserves_order", "preserves_precision"):
        require(delivery[name] is None or type(delivery[name]) is bool, "delivery preservation must be boolean/null")
    require(delivery["failure_reason"] is None or type(delivery["failure_reason"]) is str and bool(delivery["failure_reason"]), "failure reason")
    delivery_usable = provider(delivery, {"S1", "commerce_exporter"})
    closed(reception, "request_id state events_ref roster_ref production_evidence_refs delivery_evidence_ref input_value_sha256 provider", "Reception")
    text(reception["request_id"])
    require(reception["state"] in ("complete", "incomplete", "unknown"), "reception state")
    require(reception["input_value_sha256"] == batch.input_value_sha256, "reception input identity mismatch")
    require(type(reception["production_evidence_refs"]) is list and
            sorted(reception["production_evidence_refs"], key=tlv) == sorted(production_refs, key=tlv), "production evidence links mismatch")
    require(reception["delivery_evidence_ref"] == delivery["provider"]["evidence_record"], "delivery evidence link mismatch")
    received = strict_json(pin_bytes(reception["roster_ref"], "application/json")) if reception["roster_ref"] is not None else None
    require(received is None or type(received) is list, "roster file must be a customer list")
    events = pin_bytes(reception["events_ref"], "application/x-ndjson")
    records = [strict_json(line) for line in events.splitlines() if line.strip()]
    rebuilt = EventBatch(source=batch.source, entity_namespace=batch.entity_namespace, start=batch.start,
                         records=records, roster=received)
    require(rebuilt.input_value_sha256 == batch.input_value_sha256, "received artifact input identity mismatch")
    reception_usable = provider(reception, {"D9"})
    window = policy.window(index_date, None)
    covers = ds <= window.start and (upper > window.end if window.end_inclusive else upper >= window.end)
    transport_state = "complete"
    if not covers or "incomplete" in (delivery["state"], reception["state"]):
        transport_state = "incomplete"
    if not delivery_usable or not reception_usable or "unknown" in (delivery["state"], reception["state"]) or delivery["preserves_precision"] is not True:
        transport_state = "unknown"
    if transport_state != "complete":
        # Negative evidence spans H; production completeness cannot override transport loss.
        for entity in batch.entities:
            observations.append(ObservationClaim(entity, EVENT_TYPES, window.start,
                window.end if not window.end_inclusive else de, transport_state, (),
                "synthetic-transport", "D9", PROFILE, batch.input_value_sha256, "synthetic-transport-state"))

    needed = _needed(batch, policy, index_date)
    candidates = defaultdict(list)
    for c in p["ordering"]:
        closed(c, "entity at ordinals input_value_sha256 provider unused_claim_policy selected_tie_policy", "OrderClaim")
        entity, at = _entity(c["entity"], batch), timestamp(c["at"])
        policy.check_precision(at)
        require(policy.permits(at) and c["input_value_sha256"] == batch.input_value_sha256, "order input/time identity mismatch")
        require(c["unused_claim_policy"] == "identity_only_no_event_existence_check" and
                c["selected_tie_policy"] == "one_claim_full_tie_unique_ordinals", "order policy mismatch")
        require(type(c["ordinals"]) is list and bool(c["ordinals"]), "order ordinal entries required")
        entries = []
        for item in c["ordinals"]:
            closed(item, "event_id ordinal", "Ordinal")
            require(type(item["event_id"]) is str and check_identifier("event_id", item["event_id"]), "invalid order event ID")
            require(type(item["ordinal"]) is int and 0 <= item["ordinal"] < 2**63, "invalid ordinal")
            entries.append((item["event_id"], item["ordinal"]))
        usable = provider(c, {"S1", "commerce_exporter"})
        if (entity, at) in needed:
            good = (usable and delivery["preserves_order"] is True and
                    len({e[0] for e in entries}) == len(entries) == len({e[1] for e in entries}) and
                    {e[0] for e in entries} == needed[entity, at])
            candidates[entity, at].append((c, entries, good))
    orders = []
    for (entity, at), group in candidates.items():
        if len(group) == 1 and group[0][2]:
            c, entries, _ = group[0]
            orders.append(OrderClaim(entity, at, tuple(entries), batch.input_value_sha256,
                "synthetic-bound-provider", "d1-order-fixture/1", c["provider"]["evidence_record"]["path"], "synthetic"))
    observation_hash, order_hash = evidence_hashes(p, batch=batch, policy=policy, index_date=index_date)
    require(p["observation_value_sha256"] == observation_hash, "observation semantic hash mismatch")
    require(p["ordering_value_sha256"] == order_hash, "ordering semantic hash mismatch")
    require(set(verified) == set(expected_files), "required external FilePins not verified: " +
            ", ".join(sorted(set(expected_files) - set(verified))))
    return VerifiedEvidence(batch, policy, index_date, tuple(observations), tuple(orders), observation_hash,
                            order_hash, tuple(verified[k] for k in sorted(verified)))
