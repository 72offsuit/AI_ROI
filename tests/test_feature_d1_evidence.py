"""Synthetic producer/transporter/receiver binding; no actual-data acceptance."""

from copy import deepcopy
from datetime import timedelta
import hashlib
import json
import unittest

from src.decision.features.d1_evidence import DIRECTION, evidence_hashes, verify_evidence
from src.decision.features.d1_raw_sequence import generate_raw_sequences
from src.decision.features.d1_serialization import D1ContractError
from src.decision.features.d1_feature_inputs import EVENT_TYPES, timestamp
from tests.test_feature_d1_calculation import CUSTOMER, INDEX, ORIGIN, START, batch, event, policy


def json_bytes(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()


class SyntheticEvidenceFixture:
    """Caller Expected is separate and never rewritten by verify_evidence."""

    def __init__(self, records=None, roster=(CUSTOMER,), source="commerce", namespace="fixture"):
        self.batch = batch([event("page_view")] if records is None else records, roster=roster, source=source, namespace=namespace)
        self.policy = policy()
        self.artifacts, self.expected = {}, {}
        ih = self.batch.input_value_sha256

        def provider(role):
            return dict(provider_role=role, provider_account="explicit-fixture-account", agreement_status="synthetic_fixture",
                agreement_record=None, evidence_record=None, input_value_sha256=ih,
                available_as_of="2026-10-19T23:00:00+09:00", assertion_version="synthetic-body-binding/1")

        self.provider = provider
        self.envelope = dict(contract_id="I03", contract_version="d1-w0-input/1-proposed", purpose="synthetic",
            authorization=dict(direction_decision_sha256=DIRECTION, technical_profile_status="proposed",
                shared_contract_status="not_adopted", provider_agreements_status="pending", approval_records=[]),
            payload=dict(source=self.batch.source, entity_namespace=self.batch.entity_namespace, input_value_sha256=ih,
                production=[dict(entity=e.record(), event_types=sorted(EVENT_TYPES),
                    period=dict(start=START, end_exclusive=ORIGIN), state="complete", gaps=[], input_value_sha256=ih,
                    provider=provider("S4" if source == "simulator" else "commerce_exporter"), capability="event_capture") for e in self.batch.entities],
                ordering=[], delivery=dict(requested_period=dict(start=START, end_exclusive=ORIGIN), upper_exclusive=ORIGIN,
                    state="complete", preserves_order=True, preserves_precision=True, failure_reason=None, provider=provider("S1")),
                reception=dict(request_id="synthetic-1", state="complete", events_ref=None, roster_ref=None,
                    production_evidence_refs=[], delivery_evidence_ref=None, input_value_sha256=ih, provider=provider("D9")),
                observation_profile="H_all_16_event_types_conservative", fu1_profile="unused_order_claim_identity_only",
                fu2_profile="duplicate_or_conflicting_tie_is_UNKNOWN", fu3_profile="no_union_of_partial_claims",
                ordering_value_sha256="", observation_value_sha256=""))
        self.seal()

    @property
    def payload(self):
        return self.envelope["payload"]

    def pin(self, path, data, media="application/json"):
        pin = dict(path=path, file_sha256=hashlib.sha256(data).hexdigest(), media_type=media, bytes=len(data))
        self.artifacts[path] = data
        self.expected[path] = dict(pin)
        return pin

    def add_order(self, records, entries=None):
        self.payload["ordering"].append(dict(entity=self.batch.entities[0].record(), at=records[0]["timestamp"],
            ordinals=entries if entries is not None else [dict(event_id=r["event_id"], ordinal=i) for i, r in enumerate(records)],
            input_value_sha256=self.batch.input_value_sha256, provider=self.provider("S1"),
            unused_claim_policy="identity_only_no_event_existence_check", selected_tie_policy="one_claim_full_tie_unique_ordinals"))

    def hashes(self):
        obs, order = evidence_hashes(self.payload, batch=self.batch, policy=self.policy, index_date=INDEX)
        self.payload.update(observation_value_sha256=obs, ordering_value_sha256=order)

    def seal(self, prefix="fixture", reverse_events=False):
        """Prepare a new request before freezing Expected; retain artifact inventory."""
        self.expected = {}
        p = self.payload
        for name in ("production", "ordering"):
            for i, record in enumerate(p[name]):
                body = {k: v for k, v in record.items() if k != "provider"}
                record["provider"]["evidence_record"] = self.pin(f"{prefix}/{name}-{i}.json", json_bytes(body))
        delivery = p["delivery"]
        delivery["provider"]["evidence_record"] = self.pin(f"{prefix}/delivery.json", json_bytes({k: v for k, v in delivery.items() if k != "provider"}))
        reception = p["reception"]
        records = [dict(e, timestamp=e["timestamp"].isoformat()) for e in self.batch.events]
        if reverse_events:
            records.reverse()
        reception["events_ref"] = self.pin(f"{prefix}/events.jsonl", b"".join(json_bytes(e)+b"\n" for e in records), "application/x-ndjson")
        reception["roster_ref"] = (self.pin(f"{prefix}/roster.json", json_bytes([e.customer_id for e in self.batch.entities]))
                                    if self.batch.population_scope == "explicit_roster" else None)
        reception["production_evidence_refs"] = [c["provider"]["evidence_record"] for c in p["production"] if c["provider"]["evidence_record"] is not None]
        reception["delivery_evidence_ref"] = delivery["provider"]["evidence_record"]
        reception["provider"]["evidence_record"] = self.pin(f"{prefix}/reception.json", json_bytes({k: v for k, v in reception.items() if k != "provider"}))
        self.hashes()

    def verify(self):
        return verify_evidence(self.envelope, batch=self.batch, policy=self.policy, index_date=INDEX,
                               expected_files=self.expected, artifacts=self.artifacts)

    def raw(self):
        c = self.verify()
        return generate_raw_sequences([c.batch], index_date=INDEX, policy=c.policy,
            observation_claims=c.observation_claims, order_claims=c.order_claims, generated_at=ORIGIN), c


class EvidenceTests(unittest.TestCase):
    def test_bound_complete_synthetic_path_is_available_but_admission_BLOCKED(self):
        f = SyntheticEvidenceFixture()
        raw, context = f.raw()
        self.assertEqual(raw.rows[0]["state"], "VALID")
        self.assertEqual(context.admission, "BLOCKED_ADMISSION")
        self.assertEqual(len(context.verified_files), 5)

    def test_operational_envelope_rejected_even_with_accepted_declarations(self):
        f = SyntheticEvidenceFixture()
        f.envelope["purpose"] = "operational"
        f.envelope["authorization"].update(technical_profile_status="approved", shared_contract_status="adopted", provider_agreements_status="accepted")
        with self.assertRaisesRegex(D1ContractError, "actual input admission excluded"):
            f.verify()

    def test_source_customer_and_provider_identity_rejected_after_resealing(self):
        for target in ("source", "customer", "provider", "input"):
            f = SyntheticEvidenceFixture()
            c = f.payload["production"][0]
            if target == "source": c["entity"]["source"] = "simulator"
            if target == "customer": c["entity"]["customer_id"] = "C00000002"
            if target == "provider": c["provider"]["provider_role"] = "D1"
            if target == "input": c["input_value_sha256"] = "a"*64
            f.seal()
            with self.subTest(target=target), self.assertRaisesRegex(D1ContractError, "identity mismatch|customer mismatch|role mismatch"):
                f.verify()

    def test_external_pin_cannot_be_replaced_by_self_declaration(self):
        f = SyntheticEvidenceFixture()
        pin = f.payload["reception"]["events_ref"]
        pin["file_sha256"] = "b"*64
        with self.assertRaisesRegex(D1ContractError, "external FilePin mismatch"):
            f.verify()

    def test_artifact_bytes_must_match_external_pin(self):
        f = SyntheticEvidenceFixture()
        path = f.payload["reception"]["events_ref"]["path"]
        f.artifacts[path] += b" "
        with self.assertRaisesRegex(D1ContractError, "artifact byte/hash mismatch"):
            f.verify()

    def test_resealed_wrong_received_values_rejected_at_input_reconstruction(self):
        f = SyntheticEvidenceFixture()
        record = event("search")
        f.payload["reception"]["events_ref"] = f.pin("fixture/other-events.jsonl", json_bytes(record)+b"\n", "application/x-ndjson")
        with self.assertRaisesRegex(D1ContractError, "received artifact input identity mismatch"):
            f.verify()

    def test_resealed_wrong_evidence_body_rejected_at_binding(self):
        f = SyntheticEvidenceFixture()
        c = f.payload["production"][0]
        wrong = {k: v for k, v in c.items() if k != "provider"}
        wrong["state"] = "unknown"
        c["provider"]["evidence_record"] = f.pin("fixture/production-0.json", json_bytes(wrong))
        with self.assertRaisesRegex(D1ContractError, "synthetic evidence body mismatch"):
            f.verify()

    def test_delivery_and_reception_loss_propagate_despite_complete_production(self):
        for stage in ("delivery", "reception"):
            for state in ("incomplete", "unknown"):
                f = SyntheticEvidenceFixture()
                f.payload[stage]["state"] = state
                f.seal()
                raw, _ = f.raw()
                with self.subTest(stage=stage, state=state):
                    self.assertEqual(raw.rows[0]["state"], "UNKNOWN")
                    self.assertIn("INCOMPLETE_WINDOW" if state == "incomplete" else "OBSERVATION_UNKNOWN", raw.rows[0]["reasons"])

    def test_precision_loss_or_missing_provider_evidence_is_unknown(self):
        for target in ("precision", "production", "late-provider"):
            f = SyntheticEvidenceFixture()
            if target == "precision":
                f.payload["delivery"]["preserves_precision"] = False
                f.seal()
            else:
                c = f.payload["production"][0]
                if target == "production":
                    # Prepare a request with no required provider proof. This is
                    # before caller Expected is frozen, not an omission attack.
                    unrequired = c["provider"]["evidence_record"]["path"]
                    c["provider"]["evidence_record"] = None
                    f.payload["reception"]["production_evidence_refs"] = []
                    r = f.payload["reception"]
                    r["provider"]["evidence_record"] = f.pin("fixture/reception.json", json_bytes({k:v for k,v in r.items() if k != "provider"}))
                    f.expected.pop(unrequired)
                    self.assertIn(unrequired, f.artifacts)
                else:
                    c["provider"]["available_as_of"] = ORIGIN
                f.hashes()
            raw, _ = f.raw()
            self.assertEqual(raw.rows[0]["state"], "UNKNOWN", target)

    def test_narrow_delivery_upper_bound_does_not_claim_complete_H(self):
        f = SyntheticEvidenceFixture()
        f.payload["delivery"]["upper_exclusive"] = "2026-10-10T00:00:00+09:00"
        f.seal()
        raw, _ = f.raw()
        self.assertIn("INCOMPLETE_WINDOW", raw.rows[0]["reasons"])

    def test_partial_complete_production_claims_are_not_unioned(self):
        f = SyntheticEvidenceFixture()
        first = f.payload["production"][0]
        second = deepcopy(first)
        first["period"]["end_exclusive"] = "2026-10-01T00:00:00+09:00"
        second["period"]["start"] = first["period"]["end_exclusive"]
        f.payload["production"].append(second)
        f.seal()
        self.assertEqual(f.raw()[0].rows[0]["state"], "UNKNOWN")

    def test_gap_itself_is_checked_and_propagates(self):
        f = SyntheticEvidenceFixture()
        c = f.payload["production"][0]
        c["state"] = "incomplete"
        c["gaps"] = [dict(start="2026-10-01T00:00:00+09:00", end_exclusive="2026-10-03T00:00:00+09:00")]
        f.seal()
        self.assertIn("INCOMPLETE_WINDOW", f.raw()[0].rows[0]["reasons"])
        c["gaps"][0]["end_exclusive"] = "2026-10-21T00:00:00+09:00"
        f.seal()
        with self.assertRaisesRegex(D1ContractError, "invalid observation state/gaps"):
            f.verify()

    def test_needed_tie_requires_one_full_unique_order_proof(self):
        records = [event("search", number=2), event("page_view", number=1)]
        for variant in ("normal", "duplicate", "partial", "ordinal", "absent", "order-loss"):
            f = SyntheticEvidenceFixture(records)
            if variant != "absent": f.add_order(records)
            if variant == "duplicate": f.add_order(records)
            if variant == "partial": f.payload["ordering"][0]["ordinals"].pop()
            if variant == "ordinal": f.payload["ordering"][0]["ordinals"][1]["ordinal"] = 0
            if variant == "order-loss": f.payload["delivery"]["preserves_order"] = False
            f.seal()
            raw, c = f.raw()
            with self.subTest(variant=variant):
                self.assertEqual(raw.rows[0]["state"], "VALID" if variant == "normal" else "UNKNOWN")
                if variant == "normal":
                    self.assertEqual(raw.rows[0]["tokens"][-2:], [15,8])
                    self.assertEqual(raw.rows[0]["relative_gap_ms"][-1], 0)
                else:
                    self.assertIn("AMBIGUOUS_EVENT_ORDER", raw.rows[0]["reasons"])
                    self.assertFalse(c.order_claims)

    def test_old_unused_order_does_not_expand_event_existence_checks(self):
        start = timestamp("2026-10-01T00:00:00+09:00")
        old = [event("search", start.isoformat(), 1), event("page_view", start.isoformat(), 2)]
        newer = [event("page_view", (start+timedelta(seconds=n)).isoformat(), 100+n) for n in range(1,32)]
        f = SyntheticEvidenceFixture(old+newer)
        before = f.payload["ordering_value_sha256"]
        f.add_order(old, entries=[dict(event_id=event("search", number=999)["event_id"], ordinal=0)])
        f.seal()
        raw, c = f.raw()
        self.assertEqual(raw.rows[0]["state"], "VALID")
        self.assertEqual(c.ordering_value_sha256, before)
        self.assertFalse(c.order_claims)

    def test_physical_republication_does_not_enter_meaning_indirectly(self):
        records = [event("search", number=2), event("page_view", number=1)]
        f = SyntheticEvidenceFixture(records)
        f.add_order(records); f.seal()
        a = f.verify()
        f.payload["reception"]["request_id"] = "new-physical-reception"
        f.seal(prefix="republished", reverse_events=True)
        b = f.verify()
        self.assertEqual((a.observation_value_sha256,a.ordering_value_sha256), (b.observation_value_sha256,b.ordering_value_sha256))
        self.assertNotEqual(a.verified_files,b.verified_files)

    def test_semantic_mutation_requires_recomputed_meaning_pin(self):
        f = SyntheticEvidenceFixture()
        before = f.payload["observation_value_sha256"]
        f.payload["delivery"]["state"] = "incomplete"; f.seal()
        f.payload["observation_value_sha256"] = before
        with self.assertRaisesRegex(D1ContractError, "observation semantic hash mismatch"):
            f.verify()

    def test_received_future_event_rejected_without_extraction_filtering(self):
        f = SyntheticEvidenceFixture([event("page_view", ORIGIN)])
        with self.assertRaisesRegex(D1ContractError, "forbidden-time event"):
            f.verify()

    def test_unsafe_paths_and_extra_fields_rejected(self):
        f = SyntheticEvidenceFixture()
        f.payload["reception"]["events_ref"]["path"] = "../forbidden"
        with self.assertRaisesRegex(D1ContractError, "unsafe relative"):
            f.verify()
        f = SyntheticEvidenceFixture()
        f.payload["extra"] = 1
        with self.assertRaisesRegex(D1ContractError, "closed fields"):
            f.verify()

    def test_simulator_public_events_use_S4_role_without_reading_private_sources(self):
        f = SyntheticEvidenceFixture([event("page_view", simulator_version="synthetic-fixture", random_seed=7)],
                                     source="simulator", namespace="sim-fixture")
        raw, _ = f.raw()
        self.assertEqual(raw.rows[0]["state"], "VALID")
        f.payload["production"][0]["provider"]["provider_role"] = "commerce_exporter"
        f.seal()
        with self.assertRaisesRegex(D1ContractError, "provider role mismatch"):
            f.verify()

    def test_selection_boundary_tie_requires_discarded_members_as_well(self):
        at = timestamp("2026-10-01T00:00:00+09:00")
        tied = [event(kind, at.isoformat(), i) for i, kind in enumerate(("purchase", "search", "product_view"), 1)]
        newer = [event("page_view", (at+timedelta(seconds=n)).isoformat(), 100+n) for n in range(1,29)]
        for full in (False, True):
            f = SyntheticEvidenceFixture(tied+newer)
            f.add_order(tied if full else tied[-2:]); f.seal()
            raw, _ = f.raw()
            self.assertEqual(raw.rows[0]["state"], "VALID" if full else "UNKNOWN")
            if full:
                self.assertEqual(raw.rows[0]["selected_event_ids"], [r["event_id"] for r in tied[-2:]+newer])

    def test_other_capability_is_not_event_capture_evidence(self):
        f = SyntheticEvidenceFixture()
        f.payload["production"][0]["capability"] = "lifetime_purchases"
        f.seal()
        raw, c = f.raw()
        self.assertFalse(c.observation_claims)
        self.assertEqual(raw.rows[0]["state"], "UNKNOWN")


class RequiredPinTests(unittest.TestCase):
    """#138: freeze the whole required set before changing a submitted envelope."""

    def conflicting(self):
        records = [event("search", number=2), event("page_view", number=1)]
        f = SyntheticEvidenceFixture(records)
        f.add_order(records)
        f.add_order(records, entries=[dict(event_id=r["event_id"], ordinal=i)
                                     for i, r in enumerate(reversed(records))])
        f.seal()
        return f

    def verify_unchanged(self, f, envelope, expected, artifacts):
        before = deepcopy((envelope, expected, artifacts))
        try:
            return verify_evidence(envelope, batch=f.batch, policy=f.policy, index_date=INDEX,
                                   expected_files=expected, artifacts=artifacts)
        finally:
            self.assertEqual((envelope, expected, artifacts), before)

    def test_138_all_conflicting_required_proofs_keep_UNKNOWN(self):
        for reverse in (False, True):
            f = self.conflicting()
            envelope, expected, artifacts = deepcopy((f.envelope, f.expected, f.artifacts))
            if reverse:
                envelope["payload"]["ordering"].reverse()
            c = self.verify_unchanged(f, envelope, expected, artifacts)
            raw = generate_raw_sequences([c.batch], index_date=INDEX, policy=c.policy,
                observation_claims=c.observation_claims, order_claims=c.order_claims, generated_at=ORIGIN)
            self.assertEqual((raw.rows[0]["state"], raw.rows[0]["reasons"]),
                             ("UNKNOWN", ["AMBIGUOUS_EVENT_ORDER"]))
            self.assertFalse(c.order_claims)
            self.assertEqual({pin["path"] for pin in c.verified_files}, set(expected))

    def test_138_omitting_either_conflicting_proof_is_rejected_after_hash_reseal(self):
        for omitted in (0, 1):
            f = self.conflicting()
            envelope, expected, artifacts = deepcopy((f.envelope, f.expected, f.artifacts))
            p = envelope["payload"]
            removed = p["ordering"].pop(omitted)["provider"]["evidence_record"]["path"]
            self.assertIn(removed, expected)
            self.assertIn(removed, artifacts)
            p["ordering_value_sha256"] = evidence_hashes(p, batch=f.batch, policy=f.policy, index_date=INDEX)[1]
            self.assertNotEqual(p["ordering_value_sha256"], f.payload["ordering_value_sha256"])
            with self.subTest(omitted=omitted), self.assertRaisesRegex(
                    D1ContractError, "required external FilePins not verified: ") as caught:
                self.verify_unchanged(f, envelope, expected, artifacts)
            self.assertEqual(str(caught.exception), "required external FilePins not verified: " + removed)

    def test_138_valid_unreferenced_required_pin_is_rejected(self):
        f = SyntheticEvidenceFixture()
        extra = f.pin("fixture/required-unsubmitted.json", json_bytes(dict(required=True)))
        envelope, expected, artifacts = deepcopy((f.envelope, f.expected, f.artifacts))
        with self.assertRaisesRegex(D1ContractError,
                "required external FilePins not verified: ") as caught:
            self.verify_unchanged(f, envelope, expected, artifacts)
        self.assertEqual(str(caught.exception), "required external FilePins not verified: " + extra["path"])

    def test_138_fixed_order_provider_pin_cannot_be_downgraded_to_absence(self):
        f = SyntheticEvidenceFixture([event("search", number=2), event("page_view", number=1)])
        f.add_order([event("search", number=2), event("page_view", number=1)]); f.seal()
        envelope, expected, artifacts = deepcopy((f.envelope, f.expected, f.artifacts))
        proof = envelope["payload"]["ordering"][0]["provider"]
        missing = proof["evidence_record"]["path"]
        proof["evidence_record"] = None
        envelope["payload"]["ordering_value_sha256"] = evidence_hashes(
            envelope["payload"], batch=f.batch, policy=f.policy, index_date=INDEX)[1]
        with self.assertRaisesRegex(D1ContractError,
                "required external FilePins not verified: ") as caught:
            self.verify_unchanged(f, envelope, expected, artifacts)
        self.assertEqual(str(caught.exception), "required external FilePins not verified: " + missing)

    def test_138_existing_pin_bytes_identity_rejections_do_not_mutate_inputs(self):
        for error in ("external FilePin mismatch", "artifact byte/hash mismatch", "I03 input identity mismatch"):
            f = SyntheticEvidenceFixture()
            envelope, expected, artifacts = deepcopy((f.envelope, f.expected, f.artifacts))
            pin = envelope["payload"]["reception"]["events_ref"]
            if error == "external FilePin mismatch":
                pin["file_sha256"] = "b"*64
            elif error == "artifact byte/hash mismatch":
                artifacts[pin["path"]] += b" "
            else:
                envelope["payload"]["input_value_sha256"] = "a"*64
            with self.subTest(error=error), self.assertRaisesRegex(D1ContractError, error):
                self.verify_unchanged(f, envelope, expected, artifacts)

    def test_138_single_full_order_preserves_values_and_input_objects(self):
        records = [event("search", number=2), event("page_view", number=1)]
        f = SyntheticEvidenceFixture(records); f.add_order(records); f.seal()
        envelope, expected, artifacts = deepcopy((f.envelope, f.expected, f.artifacts))
        c = self.verify_unchanged(f, envelope, expected, artifacts)
        raw = generate_raw_sequences([c.batch], index_date=INDEX, policy=c.policy,
            observation_claims=c.observation_claims, order_claims=c.order_claims, generated_at=ORIGIN)
        self.assertEqual((raw.rows[0]["state"], raw.rows[0]["reasons"]), ("VALID", []))
        self.assertEqual(raw.rows[0]["tokens"], [0]*28+[15, 8])
        self.assertEqual(raw.rows[0]["relative_gap_ms"], [None]*29+[0])
        self.assertEqual(c.admission, "BLOCKED_ADMISSION")

    def test_138_pin_order_repeated_references_and_unrelated_inventory_are_allowed(self):
        f = SyntheticEvidenceFixture()
        envelope, expected, artifacts = deepcopy((f.envelope, f.expected, f.artifacts))
        production = deepcopy(envelope["payload"]["production"][0]["provider"]["evidence_record"])
        delivery = deepcopy(envelope["payload"]["delivery"]["provider"]["evidence_record"])
        envelope["authorization"]["approval_records"] = [production, delivery, deepcopy(production)]
        expected = dict(reversed(list(expected.items())))
        artifacts["inventory/unrelated.bin"] = b"not a required file"
        c = self.verify_unchanged(f, envelope, expected, artifacts)
        self.assertEqual({pin["path"] for pin in c.verified_files}, set(expected))
        self.assertEqual(len(c.verified_files), len(expected))
        self.assertEqual(c.observation_value_sha256, f.payload["observation_value_sha256"])

    def test_138_new_request_preparation_replaces_required_set_keeps_inventory(self):
        f = SyntheticEvidenceFixture(roster=(CUSTOMER, "C00000002", "C00000003"))
        old_expected = deepcopy(f.expected)
        f.payload["production"] = f.payload["production"][:1]
        f.seal(prefix="new-request")
        self.assertTrue(set(old_expected) <= set(f.artifacts))
        self.assertTrue(set(old_expected).isdisjoint(f.expected))
        self.assertTrue(all(p.startswith("new-request/") for p in f.expected))
        raw, c = f.raw()
        self.assertEqual([row["state"] for row in raw.rows], ["VALID", "UNKNOWN", "UNKNOWN"])
        self.assertEqual({pin["path"] for pin in c.verified_files}, set(f.expected))
