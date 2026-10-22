"""Independent pre-fit sequence values and selection/evidence counterexamples."""

from dataclasses import replace
from datetime import timedelta
import unittest

from src.decision.features.d1_raw_sequence import TOKEN_VOCABULARY, OrderClaim, generate_raw_sequences
from src.decision.features.d1_feature_inputs import Entity, timestamp
from src.decision.features.d1_serialization import D1ContractError
from tests.test_feature_d1_calculation import CUSTOMER, INDEX, ORIGIN, batch, claims_for, event, policy


def make_sequence(source, *, observed=True, observations=None, orders=(), time_policy=None):
    return generate_raw_sequences([source],index_date=INDEX,policy=time_policy or policy(),
        observation_claims=claims_for(source) if observations is None and observed else tuple(observations or ()),
        order_claims=tuple(orders),generated_at=ORIGIN)


def order(source, records, *, ref="explicit-synthetic-order", ordinals=None):
    return OrderClaim(entity=source.entities[0],at=records[0]["timestamp"],
        ordinals=tuple((record["event_id"],n) for n,record in enumerate(records)) if ordinals is None else ordinals,
        input_value_sha256=source.input_value_sha256,provider="fixture-provider",contract_version="d1-order-fixture/1",
        evidence_ref=ref,purpose="synthetic")


class RawSequenceTests(unittest.TestCase):
    def test_SEQ01_fixed_dictionary_has_independent_literal_tokens(self):
        kinds=("add_to_cart","campaign_exposed","checkout_start","coupon_clicked","coupon_exposed","coupon_use",
               "cs_contact","page_view","product_view","purchase","push_sent","remove_from_cart",
               "return_visit","review","search","session_start")
        records=[event(kind,f"2026-10-01T00:00:{n:02d}+09:00",n+1) for n,kind in enumerate(kinds)]
        output=make_sequence(batch(records));row=output.rows[0]
        self.assertEqual(TOKEN_VOCABULARY,("PAD",*kinds))
        self.assertEqual(row["tokens"],[0]*14+list(range(1,17)))
        self.assertEqual(row["mask"],[False]*14+[True]*16)
        self.assertEqual(row["relative_gap_ms"],[None]*15+[1000]*15)
        self.assertEqual((row["state"],row["length"],row["reasons"]),("VALID",16,[]))

    def test_SEQ02_chronology_padding_gaps_and_physical_order_invariance(self):
        records=[event("page_view","2026-10-01T12:00:00+09:00",30),
                 event("purchase","2026-10-01T12:00:01.250+09:00",1),
                 event("search","2026-10-01T12:00:02+09:00",9)]
        first=make_sequence(batch(records));second=make_sequence(batch(list(reversed(records))))
        self.assertEqual(first,second);row=first.rows[0]
        self.assertEqual(row["tokens"],[0]*27+[8,10,15])
        self.assertEqual(row["relative_gap_ms"],[None]*28+[1250,750])
        self.assertEqual(row["gap_mask"],[False]*28+[True,True])
        self.assertEqual(row["selected_event_ids"],[record["event_id"] for record in records])

    def test_SEQ03_latest_30_first_gap_does_not_reference_discarded_event(self):
        at=timestamp("2026-10-01T00:00:00+09:00")
        records=[event("page_view",(at+timedelta(seconds=n)).isoformat(),100-n) for n in range(35)]
        row=make_sequence(batch(records)).rows[0]
        self.assertEqual(row["selected_event_ids"],[record["event_id"] for record in records[5:]])
        self.assertEqual(row["tokens"],[8]*30);self.assertEqual(row["relative_gap_ms"],[None]+[1000]*29)
        self.assertEqual(row["gap_mask"],[False]+[True]*29)

    def test_SEQ04_simultaneous_events_need_order_even_if_IDs_or_rows_are_ordered(self):
        records=[event("search",number=2),event("page_view",number=1)]
        for supplied in (records,list(reversed(records))):
            with self.subTest(ids=[r["event_id"] for r in supplied]):
                row=make_sequence(batch(supplied)).rows[0]
                self.assertEqual(row["state"],"UNKNOWN");self.assertEqual(row["reasons"],["AMBIGUOUS_EVENT_ORDER"])
                self.assertIsNone(row["length"])
                for field in ("tokens","mask","relative_gap_ms","gap_mask"):self.assertIsNone(row[field])
                self.assertEqual(row["selected_event_ids"],[])

    def test_SEQ05_explicit_order_proves_real_zero_gap_and_beats_event_ID(self):
        records=[event("search","2026-10-01T00:00:00.000001+09:00",2),
                 event("page_view","2026-10-01T00:00:00.000001+09:00",1)]
        source=batch(records);proof=order(source,records,ordinals=((records[0]["event_id"],40),(records[1]["event_id"],80)))
        row=make_sequence(source,orders=(proof,)).rows[0]
        self.assertEqual(row["state"],"VALID");self.assertEqual(row["tokens"],[0]*28+[15,8])
        self.assertEqual(row["relative_gap_ms"],[None]*29+[0])
        self.assertEqual(row["gap_mask"],[False]*29+[True])
        self.assertEqual(row["order_evidence_refs"],[proof.evidence_ref])

    def boundary_case(self):
        at=timestamp("2026-10-01T00:00:00+09:00")
        tied=[event(kind,at.isoformat(),n) for n,kind in enumerate(("purchase","search","product_view"),1)]
        newer=[event("page_view",(at+timedelta(seconds=n)).isoformat(),100+n) for n in range(1,29)]
        return tied,newer,batch(tied+newer)

    def test_SEQ06_selection_boundary_requires_the_whole_tied_group(self):
        tied,newer,source=self.boundary_case()
        self.assertEqual(make_sequence(source).rows[0]["state"],"UNKNOWN")
        row=make_sequence(source,orders=(order(source,tied),)).rows[0]
        self.assertEqual(row["state"],"VALID")
        self.assertEqual(row["selected_event_ids"],[r["event_id"] for r in tied[1:]+newer])
        self.assertEqual(row["tokens"],[15,9]+[8]*28)
        self.assertEqual(row["relative_gap_ms"],[None,0]+[1000]*28)
        self.assertEqual(row["audit_counts"]["selection_boundary_group_events"],3)

    def test_SEQ07_proof_for_only_selected_boundary_members_is_insufficient(self):
        tied,_,source=self.boundary_case()
        row=make_sequence(source,orders=(order(source,tied[1:]),)).rows[0]
        self.assertEqual((row["state"],row["reasons"]),("UNKNOWN",["AMBIGUOUS_EVENT_ORDER"]))

    def test_SEQ08_old_tie_and_irrelevant_old_order_semantics_do_not_block_selection(self):
        at=timestamp("2026-10-01T00:00:00+09:00")
        old=[event("search",at.isoformat(),1),event("page_view",at.isoformat(),2)]
        newer=[event("page_view",(at+timedelta(seconds=n)).isoformat(),100+n) for n in range(1,32)]
        source=batch(old+newer)
        # A well-formed, pinned but incomplete old group claim is outside needed ordering scope.
        outputs=[make_sequence(source),make_sequence(source,orders=(order(source,old[:1]),))]
        for out in outputs:
            row=out.rows[0];self.assertEqual(row["state"],"VALID")
            self.assertEqual(row["selected_event_ids"],[r["event_id"] for r in newer[1:]])
            self.assertEqual(row["audit_counts"]["needed_order_groups"],0)
            self.assertEqual(row["audit_counts"]["events_older_than_selection_groups"],3)

    def test_SEQ09_empty_complete_is_not_unknown_and_preserves_roster_rows(self):
        source=batch([],roster=(CUSTOMER,"C00000002"));whole=claims_for(source)
        output=make_sequence(source,observations=(whole[0],))
        empty,unknown=output.rows
        self.assertEqual((empty["state"],empty["length"],empty["reasons"]),("EMPTY_COMPLETE",0,["NO_SEQUENCE_INFORMATION"]))
        self.assertEqual(empty["tokens"],[0]*30);self.assertEqual(empty["mask"],[False]*30)
        self.assertEqual(empty["relative_gap_ms"],[None]*30);self.assertEqual(empty["gap_mask"],[False]*30)
        self.assertEqual(unknown["state"],"UNKNOWN");self.assertIsNone(unknown["length"])
        self.assertEqual(unknown["reasons"],["OBSERVATION_UNKNOWN"])

    def test_SEQ10_all_16_types_need_observation_even_when_not_observed(self):
        source=batch([event("page_view")]);whole=claims_for(source)[0]
        for state,code in (("incomplete","INCOMPLETE_WINDOW"),("unsupported","UNSUPPORTED_EVENT_KIND")):
            partial=replace(whole,event_types=frozenset({"push_sent"}),state=state,
                start="2026-10-01T00:00:00+09:00",end="2026-10-03T00:00:00+09:00",evidence_ref="missing-kind")
            row=make_sequence(source,observations=(whole,partial)).rows[0]
            self.assertEqual(row["state"],"UNKNOWN");self.assertIn(code,row["reasons"])

    def test_SEQ11_actual_source_namespace_keys_are_preserved(self):
        sources=[batch([event("page_view")],source="commerce",namespace="n1"),
                 batch([event("search",simulator_version="sim-fixture",random_seed=7)],source="simulator",namespace="n1")]
        output=generate_raw_sequences(sources,index_date=INDEX,policy=policy(),
            observation_claims=tuple(c for source in sources for c in claims_for(source)),generated_at=ORIGIN)
        self.assertEqual({(row["source"],row["customer_id"],row["tokens"][-1]) for row in output.rows},
                         {("commerce",CUSTOMER,8),("simulator",CUSTOMER,15)})

    def test_SEQ12_existing_batch_policy_observation_and_source_guards_are_reused(self):
        source=batch([event("page_view")]);whole=claims_for(source)[0]
        with self.assertRaisesRegex(D1ContractError,"explicit time policy"):
            generate_raw_sequences([source],index_date=INDEX)
        with self.assertRaisesRegex(D1ContractError,"input identity mismatch"):
            make_sequence(source,observations=(replace(whole,input_value_sha256="0"*64),))
        with self.assertRaisesRegex(D1ContractError,"outside transaction"):
            make_sequence(source,observations=(replace(whole,entity=Entity("other","commerce",CUSTOMER)),))
        with self.assertRaisesRegex(D1ContractError,"duplicate source/namespace"):
            generate_raw_sequences([source,source],index_date=INDEX,policy=policy())
        with self.assertRaisesRegex(D1ContractError,"event source mismatch"):
            make_sequence(batch([event("page_view")],source="simulator"))
        with self.assertRaisesRegex(D1ContractError,"forbidden-time event"):
            make_sequence(batch([event("page_view",ORIGIN)]))
        with self.assertRaisesRegex(D1ContractError,"duplicate event_id"):
            make_sequence(batch([event("page_view"),event("page_view")]))

    def test_SEQ13_submillisecond_gap_is_not_rounded_and_old_gaps_are_outside_scope(self):
        at=timestamp("2026-10-01T00:00:00+09:00")
        old=[event("page_view",at.isoformat(),1),event("search",(at+timedelta(microseconds=1)).isoformat(),2)]
        row=make_sequence(batch(old)).rows[0]
        self.assertEqual((row["state"],row["reasons"]),("UNKNOWN",["CONTRACT_UNRESOLVED"]))
        self.assertEqual(row["blocking_details"],["SUBMILLISECOND_GAP_REPRESENTATION"])
        self.assertIsNone(row["relative_gap_ms"])
        newer=[event("page_view",(at+timedelta(seconds=n)).isoformat(),100+n) for n in range(1,31)]
        self.assertEqual(make_sequence(batch(old+newer)).rows[0]["state"],"VALID")
        with self.assertRaisesRegex(D1ContractError,"millisecond grid"):
            make_sequence(batch(old),time_policy=policy(precision="ms"))

    def test_SEQ14_H_selection_is_distinct_from_global_input_validation(self):
        source=batch([event("page_view","2026-08-01T00:00:00+09:00")])
        row=make_sequence(source,time_policy=policy(history_start="2026-09-01T00:00:00+09:00")).rows[0]
        self.assertEqual(row["state"],"EMPTY_COMPLETE")
        self.assertEqual(row["audit_counts"]["observed_events"],0)

    def test_SEQ15_order_evidence_pins_scope_conflicts_and_timezone(self):
        records=[event("search",number=2),event("page_view",number=1)];source=batch(records);proof=order(source,records)
        utc=replace(proof,at="2026-10-01T15:00:00Z",ordinals=tuple(reversed(proof.ordinals)))
        self.assertEqual(make_sequence(source,orders=(proof,)),make_sequence(source,orders=(utc,)))
        for bad,message in ((replace(proof,input_value_sha256="0"*64),"order input identity mismatch"),
            (replace(proof,entity=Entity("other","commerce",CUSTOMER)),"outside transaction"),
            (replace(proof,at=ORIGIN),"forbidden-time order claim")):
            with self.subTest(message=message),self.assertRaisesRegex(D1ContractError,message):
                make_sequence(source,orders=(bad,))
        row=make_sequence(source,orders=(proof,replace(proof,evidence_ref="second-provider"))).rows[0]
        self.assertEqual(row["reasons"],["AMBIGUOUS_EVENT_ORDER"])
        with self.assertRaisesRegex(D1ContractError,"duplicate ordinal"):
            replace(proof,ordinals=tuple((r["event_id"],0) for r in records))
        with self.assertRaisesRegex(D1ContractError,"actual order provider contract unresolved"):
            replace(proof,purpose="production")

    def test_SEQ16_sequence_generation_does_not_mutate_inputs_or_produce_model_features(self):
        records=[event("page_view")];source=batch(records);before=source.events
        row=make_sequence(source).rows[0]
        self.assertEqual(source.events,before);self.assertEqual(records[0]["simulator_version"],None)
        self.assertNotIn("F36",row);self.assertNotIn("F37",row)

    def test_SEQ17_explicit_cutoff_policies_are_not_replaced_by_a_sequence_default(self):
        cutoff="2026-10-19T23:59:59+09:00"
        for tp,at,accepted in ((policy("le",cutoff),cutoff,True),(policy("lt",cutoff),cutoff,False),
                               (policy(),"2026-10-19T23:59:59.999999+09:00",True),(policy(),ORIGIN,False)):
            with self.subTest(operator=tp.operator,boundary=tp.boundary,at=at):
                source=batch([event("page_view",at)])
                if accepted:self.assertEqual(make_sequence(source,time_policy=tp).rows[0]["state"],"VALID")
                else:
                    with self.assertRaisesRegex(D1ContractError,"forbidden-time event"):
                        make_sequence(source,time_policy=tp)

    def test_SEQ18_evidence_end_is_exclusive_while_P1_request_end_is_inclusive(self):
        cutoff="2026-10-19T23:59:59+09:00";source=batch([event("page_view")])
        claim=replace(claims_for(source)[0],end=cutoff)
        p1=make_sequence(source,time_policy=policy("le",cutoff),observations=(claim,)).rows[0]
        p2=make_sequence(source,time_policy=policy("lt",cutoff),observations=(claim,)).rows[0]
        self.assertEqual((p1["state"],p1["reasons"]),("UNKNOWN",["INCOMPLETE_WINDOW","OBSERVATION_UNKNOWN"]))
        self.assertEqual((p2["state"],p2["reasons"]),("VALID",[]))
