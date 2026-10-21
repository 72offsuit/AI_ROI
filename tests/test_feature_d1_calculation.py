"""Contract-shaped synthetic inputs and independently enumerated expected values."""

from dataclasses import replace
from datetime import date, datetime, timedelta, timezone
import math
import random
import unittest

from src.measurement.schema import EVENT_FIELDS, EventType, required_fields, validate_event
from src.measurement.sink import event_source
from src.decision.features.d1_calculate import CORE_IDS, calculate_features,core_feature_schema
from src.decision.features.d1_feature_inputs import (
    EVENT_TYPES, Entity, EventBatch, ObservationClaim, TimePolicy, timestamp,
)
from src.decision.features.d1_serialization import D1ContractError, semantic_hash
from src.decision.features.d1_semantics import table_hash,schema_body

INDEX = date(2026,10,20)
ORIGIN = "2026-10-20T00:00:00+09:00"
START = "2026-01-01T00:00:00+09:00"
CUSTOMER = "C00000001"


def policy(operator="lt",boundary=ORIGIN,precision="us",history_start=START,purpose="synthetic"):
    return TimePolicy("explicit-fixture-policy",boundary,operator,precision,history_start,purpose)


def event(kind,at="2026-10-02T00:00:00+09:00",number=1,customer=CUSTOMER,**changes):
    record = {field.name:None for field in EVENT_FIELDS}
    record.update(event_id=f"{number:08x}-0000-4000-8000-000000000000",customer_id=customer,
                  timestamp=at,event_type=kind)
    defaults = dict(session_id=f"S-{customer}-{1760000000000+number}",page_type="home",product_id="P0001",
                    category="fresh_food",quantity=1,unit_price=1000,order_id=f"O20261001-{number:06d}",
                    order_amount=100,coupon_id="CPN-A1B2C3",campaign_id="CMP-20261001-001")
    for name in required_fields(EventType(kind)):
        if name not in ("event_id","customer_id","timestamp","event_type"): record[name]=defaults[name]
    record.update(changes)
    return record


def batch(records,roster=(CUSTOMER,),source="commerce",namespace="fixture",start=START):
    # Default event() has null simulator metadata. Never rewrite records to match a declaration.
    return EventBatch(source=source,entity_namespace=namespace,start=start,records=records,roster=roster)


def claims_for(source,state="complete",types=EVENT_TYPES,start=START,end=ORIGIN,gaps=()):
    return tuple(ObservationClaim(entity,frozenset(types),start,end,state,gaps,"fixture-provider","synthetic",
                                  "fixture-observation/1",source.input_value_sha256,"explicit-fixture-proof")
                 for entity in source.entities)


def run(records,*,roster=(CUSTOMER,),time_policy=None,observed=True,state="complete"):
    source=batch(records,roster)
    return calculate_features([source],index_date=INDEX,policy=time_policy or policy(),
        observation_claims=claims_for(source,state) if observed else (),generated_at=timestamp(ORIGIN))


def quality(output,fid,customer=CUSTOMER):
    return next(row for row in output.quality_rows if row["feature_id"]==fid and row["customer_id"]==customer)


class CalculationTests(unittest.TestCase):
    def test_CALC01_two_purchase_independent_golden_example(self):
        result=run([event("purchase","2026-10-01T00:00:00+09:00",1,order_amount=20000),
                    event("purchase","2026-10-11T00:00:00+09:00",2,order_amount=30000)])
        row=result.feature_rows[0]
        for fid,wanted in {"F01":9.0,"F02":2,"F03":50000,"F04":25000.0,"F05":10.0,"F07":0.9}.items():
            self.assertEqual(row[fid],wanted,fid)
        self.assertIsNone(row["F06"])
        self.assertIn("INSUFFICIENT_PURCHASE_INTERVALS",quality(result,"F06")["reasons"])

    def mixed_events(self):
        records=[event("purchase",at,n,order_amount=amount) for n,at,amount in [
            (1,"2026-08-10T00:00:00+09:00",10000),(2,"2026-08-20T00:00:00+09:00",20000),
            (3,"2026-10-01T00:00:00+09:00",20000),(4,"2026-10-11T00:00:00+09:00",30000)]]
        sid="S-C00000001-1760000000010"
        entries=[("session_start","2026-10-02T06:00:00+09:00",dict(session_id=sid)),
                 ("return_visit","2026-10-02T06:00:00+09:00",dict(session_id=sid)),
                 ("session_start","2026-10-13T00:00:00+09:00",{}),
                 ("page_view","2026-10-02T06:00:00+09:00",{}),
                 ("page_view","2026-10-02T18:00:00+09:00",{}),
                 ("product_view","2026-10-02T06:00:00+09:00",{}),
                 ("product_view","2026-10-02T18:00:00+09:00",{}),
                 ("product_view","2026-10-02T00:00:00+09:00",dict(product_id="P0002",category="dairy")),
                 ("search","2026-10-02T06:00:00+09:00",{}),
                 ("add_to_cart","2026-10-02T18:00:00+09:00",{}),
                 ("remove_from_cart","2026-10-02T00:00:00+09:00",{}),
                 ("checkout_start","2026-10-02T00:00:00+09:00",dict(order_id="O20261002-000001")),
                 ("checkout_start","2026-10-02T00:00:00+09:00",dict(order_id="O20261002-000001")),
                 ("cs_contact","2026-10-02T00:00:00+09:00",{}),
                 ("review","2026-10-02T00:00:00+09:00",{}),
                 ("coupon_exposed","2026-10-02T00:00:00+09:00",{}),
                 ("coupon_exposed","2026-10-02T00:00:00+09:00",{}),
                 ("coupon_use","2026-10-11T00:00:00+09:00",dict(order_id="O20261001-000004",order_amount=30000)),
                 ("coupon_use","2026-10-11T00:00:00+09:00",dict(order_id="O20261001-000004",order_amount=30000)),
                 ("campaign_exposed","2026-10-02T00:00:00+09:00",{})]
        records += [event(kind,at,n,**change) for n,(kind,at,change) in enumerate(entries,10)]
        return records

    def test_CALC02_all_31_defined_event_features_have_literal_normal_values(self):
        records=self.mixed_events()
        for record in records:self.assertEqual(validate_event(record),[])
        result=run(records);row=result.feature_rows[0]
        expected={"F01":9,"F02":4,"F03":80000,"F04":20000,"F05":62/3,"F06":16*math.sqrt(2)/31,
            "F07":27/62,"F08":2,"F09":7,"F10":4,"F11":2,"F12":3,"F13":2,"F14":1,"F15":1,
            "F16":1,"F17":1,"F18":1,"F19":1,"F20":2,"F21":1,"F22":18,
            "F23":-(2/3*math.log(2/3)+1/3*math.log(1/3)),"F24":2/3,"F25":1,"F26":2/30,
            "F27":0,"F28":0.75,"F29":5/21,"F30":3/21,"F42":0.25}
        self.assertEqual(set(expected),set(CORE_IDS))
        for fid,wanted in expected.items():
            self.assertAlmostEqual(row[fid],wanted,msg=fid)
            self.assertEqual(quality(result,fid)["availability"],"available")
            self.assertEqual(quality(result,fid)["reasons"],[])
        self.assertEqual(len([key for key in row if key.startswith("F")]),42)
        self.assertEqual(row["F28"]+row["F42"],1)

    def test_CALC03_zero_one_two_three_and_simultaneous_orders(self):
        for count in range(4):
            with self.subTest(count=count):
                output=run([event("purchase",f"2026-10-{1+n*5:02d}T00:00:00+09:00",n+1) for n in range(count)])
                row=output.feature_rows[0]
                self.assertEqual(row["F02"],count)
                self.assertEqual(row["F03"],count*100)
                self.assertEqual(row["F05"],5.0 if count>=2 else None)
                self.assertEqual(row["F06"],0.0 if count>=3 else None)
        same=run([event("purchase",number=n) for n in (1,2,3)])
        self.assertEqual(same.feature_rows[0]["F02"],3)
        self.assertEqual(same.feature_rows[0]["F05"],0)
        for fid in ("F06","F07"):
            self.assertIsNone(same.feature_rows[0][fid]);self.assertIn("ZERO_DENOMINATOR",quality(same,fid)["reasons"])

    def test_CALC04_coupon_order_and_repeated_purchase_are_not_double_revenue(self):
        purchase=event("purchase",number=1,order_amount=20000,coupon_id="CPN-A1B2C3")
        duplicate=dict(purchase,event_id=event("purchase",number=2)["event_id"])
        coupon=event("coupon_use",number=3,order_id=purchase["order_id"],order_amount=20000)
        output=run([purchase,duplicate,coupon]);row=output.feature_rows[0]
        self.assertEqual((row["F02"],row["F03"],row["F04"],row["F21"]),(1,20000,20000,1))
        self.assertEqual(quality(output,"F02")["audit_counts"],{"observed_events":2,"observed_units":1})
        for change in (dict(order_amount=999),dict(timestamp="2026-10-03T00:00:00+09:00")):
            with self.subTest(change=change),self.assertRaisesRegex(D1ContractError,"conflicting purchase order"):
                run([purchase,dict(duplicate,**change)])

    def test_CALC05_previous_recent_boundaries_and_internal_intervals(self):
        events=[event("purchase",at,n) for n,at in enumerate([
            "2026-08-01T00:00:00+09:00","2026-08-21T00:00:00+09:00",
            "2026-09-10T00:00:00+09:00","2026-09-20T00:00:00+09:00"],1)]
        result=run(events)
        self.assertEqual(result.feature_rows[0]["F27"],-10)
        # 8/21 -> 9/10 crosses the 45-day boundary and is not assigned to either side.
        self.assertEqual(quality(result,"F27")["audit_counts"]["recent_observed_intervals"],1)
        self.assertEqual(quality(result,"F27")["audit_counts"]["previous_observed_intervals"],1)
        output=run([event("session_start","2026-09-22T00:00:00+09:00",1),
                    event("session_start","2026-10-06T00:00:00+09:00",2)])
        self.assertEqual(output.feature_rows[0]["F25"],1)
        output=run([event("purchase","2026-08-21T00:00:00+09:00",1),
                    event("purchase","2026-09-20T00:00:00+09:00",2)])
        self.assertEqual(output.feature_rows[0]["F26"],0)

    def test_CALC06_policy_P1_P2_P3_boundaries_and_future_guard(self):
        boundary="2026-10-19T23:59:59+09:00"
        cases=[(policy("le",boundary),"2026-10-19T23:59:58.999999+09:00",True),
               (policy("le",boundary),boundary,True),(policy("lt",boundary),boundary,False),
               (policy("lt",boundary),"2026-10-19T23:59:58.999999+09:00",True),
               (policy("lt",boundary),"2026-10-19T23:59:59.000001+09:00",False),
               (policy("le",boundary),"2026-10-19T23:59:59.000001+09:00",False),
               (policy(),"2026-10-19T23:59:59.999999+09:00",True),(policy(),ORIGIN,False)]
        for time_policy,at,accepted in cases:
            with self.subTest(at=at,op=time_policy.operator):
                if accepted:self.assertEqual(run([event("purchase",at)],time_policy=time_policy).feature_rows[0]["F02"],1)
                else:
                    with self.assertRaisesRegex(D1ContractError,"forbidden-time event"):
                        run([event("purchase",at)],time_policy=time_policy)
        with self.assertRaisesRegex(D1ContractError,"explicit time policy"):
            calculate_features([batch([])],index_date=INDEX)
        with self.assertRaisesRegex(D1ContractError,"inconsistent"):
            run([],time_policy=policy("le",ORIGIN))
        with self.assertRaisesRegex(D1ContractError,"operational cutoff unresolved"):
            policy(purpose="approved")

    def test_CALC07_timezone_equivalence_and_precision_rejection(self):
        first=run([event("purchase","2026-10-01T00:00:00+09:00")])
        second=run([event("purchase","2026-09-30T15:00:00Z")])
        self.assertEqual(first.typed_core_rows(),second.typed_core_rows())
        self.assertEqual(first.reproducibility,second.reproducibility)
        for at,message in [("2026-10-01T00:00:00","UTC 오프셋"),
                           ("2026-10-01T00:00:00.1234567Z","fractional digits")]:
            with self.subTest(at=at),self.assertRaisesRegex(D1ContractError,message): run([event("purchase",at)])
        with self.assertRaisesRegex(D1ContractError,"millisecond grid"):
            run([event("purchase","2026-10-01T00:00:00.000001+09:00")],time_policy=policy(precision="ms"))

    def test_CALC08_complete_empty_unknown_and_roster_only_customers(self):
        complete=run([],roster=(CUSTOMER,"C00000002"))
        self.assertEqual(len(complete.feature_rows),2)
        for row in complete.feature_rows:
            self.assertEqual(row["F02"],0);self.assertEqual(row["F03"],0);self.assertIsNone(row["F01"])
            self.assertIsNone(row["F04"])
        unknown=run([],observed=False)
        self.assertTrue(all(unknown.feature_rows[0][fid] is None for fid in CORE_IDS))
        self.assertEqual(quality(unknown,"F04")["denominator"],None)
        self.assertNotIn("ZERO_DENOMINATOR",quality(unknown,"F04")["reasons"])
        partial=run([event("purchase")],observed=False)
        self.assertIsNone(partial.feature_rows[0]["F02"])
        self.assertEqual(quality(partial,"F02")["audit_counts"]["observed_units"],1)

    def test_CALC09_source_namespace_and_observed_only_population(self):
        sources=[batch([event("purchase")],source="commerce",namespace="n1"),
                 batch([event("purchase",simulator_version="sim-fixture",random_seed=7)],source="simulator",namespace="n1"),
                 batch([],source="commerce",namespace="n2")]
        result=calculate_features(sources,index_date=INDEX,policy=policy(),
                                  observation_claims=tuple(c for source in sources for c in claims_for(source)))
        self.assertEqual(len(result.feature_rows),3)
        observed=calculate_features([batch([event("purchase")],roster=None)],index_date=INDEX,policy=policy())
        self.assertEqual(observed.reproducibility[0]["population_scope"],"observed_only")
        with self.assertRaisesRegex(D1ContractError,"duplicate source/namespace"):
            calculate_features([sources[0],sources[0]],index_date=INDEX,policy=policy())
        with self.assertRaisesRegex(D1ContractError,"outside transaction"):
            calculate_features([sources[0]],index_date=INDEX,policy=policy(),observation_claims=claims_for(sources[1]))

    def test_CALC10_zero_numerator_positive_zero_unknown_denominator(self):
        past=[event("session_start","2026-09-25T00:00:00+09:00",1),
              event("session_start","2026-09-26T00:00:00+09:00",2)]
        output=run(past)
        self.assertEqual(output.feature_rows[0]["F25"],0)
        self.assertEqual(quality(output,"F25")["denominator"],2)
        self.assertIn("ZERO_DENOMINATOR",quality(run([]),"F25")["reasons"])
        self.assertNotIn("ZERO_DENOMINATOR",quality(run([],observed=False),"F25")["reasons"])

    def test_CALC11_decrease_negative_change_and_unobserved_comparison_window(self):
        purchases=[event("purchase","2026-09-01T00:00:00+09:00",n) for n in (1,2,3)]
        self.assertEqual(run(purchases).feature_rows[0]["F26"],-0.1)
        source=batch(purchases)
        recent=claims_for(source,start="2026-09-20T00:00:00+09:00")
        output=calculate_features([source],index_date=INDEX,policy=policy(),observation_claims=recent)
        self.assertIsNone(output.feature_rows[0]["F26"])
        self.assertIn("OBSERVATION_UNKNOWN",quality(output,"F26")["reasons"])

    def test_CALC12_weekday_weekend_and_KST_date_boundary(self):
        for at,weekday,weekend in [("2026-10-02T12:00:00+09:00",1,0),
                                  ("2026-10-03T12:00:00+09:00",0,1),
                                  ("2026-10-02T15:00:00Z",0,1)]:
            with self.subTest(at=at):
                row=run([event("purchase",at)]).feature_rows[0]
                self.assertEqual((row["F28"],row["F42"]),(weekday,weekend))
        row=run([]).feature_rows[0];self.assertIsNone(row["F28"]);self.assertIsNone(row["F42"])

    def test_CALC13_category_entropy_and_legal_optional_missing(self):
        single=run([event("product_view")]).feature_rows[0]
        self.assertEqual((single["F23"],single["F24"]),(0,1))
        multiple=run([event("product_view",number=1),event("product_view",number=2,category="dairy")]).feature_rows[0]
        self.assertAlmostEqual(multiple["F23"],math.log(2));self.assertEqual(multiple["F24"],0.5)
        optional=run([event("page_view",category=None,product_id=None,session_duration=None)]).feature_rows[0]
        self.assertEqual(optional["F11"],1)
        with self.assertRaisesRegex(D1ContractError,"필수 필드 누락"):
            run([event("product_view",category=None)])

    def test_CALC14_input_order_invariance_and_legacy_typed_hash_compatibility(self):
        events=self.mixed_events();first=run(events)
        random.Random(42).shuffle(events);second=run(events)
        self.assertEqual(first.typed_core_rows(),second.typed_core_rows())
        self.assertEqual(first.reproducibility,second.reproducibility)
        schema=core_feature_schema()
        self.assertEqual(schema["feature_order"],list(CORE_IDS))
        sh=semantic_hash("schema",schema_body(schema))
        ph=first.reproducibility[0]["policy_value_sha256"]
        self.assertEqual(table_hash("features",first.typed_core_rows(),sh,ph),
                         table_hash("features",second.typed_core_rows(),sh,ph))
        # No quality/sequence adapter or full loader acceptance is claimed by this projection.

    def test_CALC15_duplicates_invalid_required_types_and_forbidden_fields(self):
        original=event("purchase")
        with self.assertRaisesRegex(D1ContractError,"duplicate event_id"):run([original,dict(original)])
        for changes,message in [(dict(customer_id=None),"필수 필드 누락"),(dict(order_amount=float("nan")),"invalid integer"),
                                (dict(order_amount=True),"invalid integer"),(dict(order_amount=-1),"0 이상"),
                                (dict(persona="VIP"),"non-22-column"),(dict(value_post_t0=1),"non-22-column"),
                                (dict(source="other"),"non-22-column")]:
            with self.subTest(changes=changes),self.assertRaisesRegex(D1ContractError,message):run([dict(original,**changes)])
        with self.assertRaisesRegex(D1ContractError,"session/customer"):
            run([event("session_start",session_id="S-C00000002-1760000000000")])

    def test_CALC16_raw_assignment_metadata_is_not_X_and_deferred_columns_not_counted(self):
        result=run([event("purchase",treatment_id="T3",treatment_group="treatment",experiment_id="EXP-20261001-01")])
        view=result.learning_view(["F02","F03"])
        self.assertEqual(view["X"],[{"F02":1,"F03":100}])
        self.assertEqual(view["keys"][0]["customer_id"],CUSTOMER)
        for name in ("customer_id","index_date","treatment_id","persona","value_post_t0","F36","F38","F41"):
            with self.subTest(name=name),self.assertRaisesRegex(D1ContractError,"forbidden"):
                result.learning_view([name])
        self.assertEqual(len(CORE_IDS),31)
        self.assertTrue(all(result.feature_rows[0][f"F{n:02d}"] is None for n in range(31,42)))

    def test_CALC17_VIP_amount_preserved_and_overflow_explicit(self):
        self.assertEqual(run([event("purchase",order_amount=9_000_000_000_000)]).feature_rows[0]["F03"],9_000_000_000_000)
        with self.assertRaisesRegex(D1ContractError,"Int64 overflow"):
            run([event("purchase",number=n,order_amount=2**63-1) for n in (1,2)])

    def test_CALC18_observation_identity_scope_conflict_gap_and_multiple_reasons(self):
        source=batch([])
        good=claims_for(source)
        bad=replace(good[0],input_value_sha256="0"*64)
        with self.assertRaisesRegex(D1ContractError,"input identity"):
            calculate_features([source],index_date=INDEX,policy=policy(),observation_claims=(bad,))
        incomplete=claims_for(source,state="incomplete",gaps=(("2026-10-01T00:00:00Z","2026-10-02T00:00:00Z"),))
        output=calculate_features([source],index_date=INDEX,policy=policy(),observation_claims=good+incomplete)
        self.assertEqual(set(quality(output,"F02")["reasons"]),{"OBSERVATION_UNKNOWN","INCOMPLETE_WINDOW"})
        unsupported=run([],state="unsupported")
        self.assertIn("UNSUPPORTED_EVENT_KIND",quality(unsupported,"F02")["reasons"])
        short_start="2026-09-01T00:00:00+09:00"
        short=batch([],start=short_start)
        output=calculate_features([short],index_date=INDEX,policy=policy(history_start=short_start),
                                  observation_claims=claims_for(short))
        self.assertIn("INCOMPLETE_WINDOW",quality(output,"F02")["reasons"])
        self.assertIsNone(output.feature_rows[0]["F02"])

    def test_CALC19_input_copies_and_transaction_guard(self):
        record=event("purchase");source=batch([record]);record["order_amount"]=999
        exposed=source.events;exposed[0]["order_amount"]=777
        output=calculate_features([source],index_date=INDEX,policy=policy(),observation_claims=claims_for(source))
        self.assertEqual(output.feature_rows[0]["F03"],100)
        future=batch([event("purchase",ORIGIN)],source="commerce",namespace="future")
        with self.assertRaisesRegex(D1ContractError,"forbidden-time event"):
            calculate_features([source,future],index_date=INDEX,policy=policy())

    def test_CALC20_old_window_events_are_selected_normally_not_input_errors(self):
        boundary=timestamp(ORIGIN)-timedelta(days=90)
        output=run([event("purchase",boundary.isoformat(),1),
                    event("purchase",(boundary-timedelta(microseconds=1)).isoformat(),2)])
        self.assertEqual(output.feature_rows[0]["F02"],1)
        self.assertEqual(output.feature_rows[0]["F01"],90)
        self.assertAlmostEqual(output.feature_rows[0]["F05"],1/86400/1_000_000)
        for days,kind,fid in ((60,"page_view","F11"),(180,"review","F19")):
            boundary=timestamp(ORIGIN)-timedelta(days=days)
            output=run([event(kind,boundary.isoformat(),1),event(kind,(boundary-timedelta(microseconds=1)).isoformat(),2)])
            self.assertEqual(output.feature_rows[0][fid],1)

    def test_CALC21_activity_hour_boundaries(self):
        events=[event("page_view",f"2026-10-01T{hour}+09:00",n) for n,hour in enumerate(
            ("05:59:59","06:00:00","11:59:59","12:00:00","17:59:59","18:00:00","23:59:59"),1)]
        row=run(events).feature_rows[0]
        self.assertEqual(row["F29"],2/7)
        self.assertEqual(row["F30"],2/7)


class ObservationOverlapTests(unittest.TestCase):
    """#127: full-scope positive evidence cannot hide overlapping negative evidence."""

    def calculate(self, source, claims, time_policy=None):
        return calculate_features([source],index_date=INDEX,policy=time_policy or policy(),
                                  observation_claims=tuple(claims))

    def test_N12701_full_complete_does_not_hide_partial_negative_claims(self):
        expected={"incomplete":{"OBSERVATION_UNKNOWN","INCOMPLETE_WINDOW"},
                  "unknown":{"OBSERVATION_UNKNOWN"},
                  "unsupported":{"OBSERVATION_UNKNOWN","UNSUPPORTED_EVENT_KIND"}}
        for state,reasons in expected.items():
            with self.subTest(state=state):
                source=batch([],source="commerce");complete=claims_for(source)[0]
                partial=replace(complete,start="2026-10-01T00:00:00+09:00",
                    end="2026-10-03T00:00:00+09:00",state=state,evidence_ref="partial-"+state,
                    gaps=(("2026-10-01T00:00:00+09:00","2026-10-02T00:00:00+09:00"),)
                    if state=="incomplete" else ())
                output=self.calculate(source,(complete,partial));q=quality(output,"F02")
                self.assertIsNone(output.feature_rows[0]["F02"])
                self.assertEqual(q["availability"],"unavailable")
                self.assertEqual(set(q["reasons"]),reasons)
                self.assertEqual(q["audit_counts"],{"observed_events":0,"observed_units":0})
                self.assertIn(partial.evidence_ref,q["evidence_refs"])

    def test_N12702_observed_events_stay_auditable_while_all_31_values_are_unavailable(self):
        source=batch([event("purchase")],source="commerce");complete=claims_for(source)[0]
        partial=replace(complete,start="2026-10-01T00:00:00+09:00",end="2026-10-03T00:00:00+09:00",
                        state="unknown",evidence_ref="overlapping-unknown-with-gap",
                        gaps=(("2026-10-01T00:00:00+09:00","2026-10-02T00:00:00+09:00"),))
        output=self.calculate(source,(complete,partial))
        self.assertTrue(all(output.feature_rows[0][fid] is None for fid in CORE_IDS))
        self.assertEqual(quality(output,"F02")["audit_counts"],{"observed_events":1,"observed_units":1})
        self.assertEqual(set(quality(output,"F02")["reasons"]),{"OBSERVATION_UNKNOWN","INCOMPLETE_WINDOW"})
        self.assertIsNone(quality(output,"F04")["denominator"])
        self.assertNotIn("ZERO_DENOMINATOR",quality(output,"F04")["reasons"])

    def test_N12703_other_customer_type_and_outside_claims_do_not_contaminate_value(self):
        for variant in ("customer","event_type","before","after"):
            with self.subTest(variant=variant):
                source=batch([],source="commerce",roster=(CUSTOMER,"C00000002"))
                complete=claims_for(source)
                partial=replace(complete[0],start="2026-10-01T00:00:00+09:00",
                    end="2026-10-03T00:00:00+09:00",state="incomplete",evidence_ref="isolated-"+variant)
                if variant=="customer":partial=replace(partial,entity=complete[1].entity)
                if variant=="event_type":partial=replace(partial,event_types=frozenset({"page_view"}))
                if variant=="before":partial=replace(partial,start="2026-07-21T00:00:00+09:00",end="2026-07-22T00:00:00+09:00")
                if variant=="after":partial=replace(partial,start=ORIGIN,end="2026-10-21T00:00:00+09:00")
                output=self.calculate(source,(*complete,partial))
                self.assertEqual(output.feature_rows[0]["F02"],0)
                self.assertEqual(quality(output,"F02")["reasons"],[])
                if variant=="customer":self.assertIsNone(output.feature_rows[1]["F02"])
                if variant=="event_type":self.assertIsNone(output.feature_rows[0]["F11"])

    def test_N12704_half_open_gaps_and_P1_P2_P3_inclusive_end_in_KST_and_UTC(self):
        for name,time_policy in (("P1",policy("le","2026-10-19T23:59:59+09:00")),
                                 ("P2",policy("lt","2026-10-19T23:59:59+09:00")),("P3",policy())):
            window=time_policy.window(INDEX,90);tick=timedelta(microseconds=1)
            cases=[("ends_at_start",window.start-tick,window.start,False),
                   ("starts_at_start",window.start,window.start+tick,True),
                   ("ends_at_end",window.end-tick,window.end,True),
                   ("starts_at_end",window.end,window.end+tick,name=="P1"),
                   ("after_end",window.end+tick,window.end+2*tick,False)]
            for utc in (False,True):
                for label,start,end,overlaps in cases:
                    with self.subTest(policy=name,utc=utc,gap=label):
                        zone=timezone.utc if utc else timezone(timedelta(hours=9))
                        start,end=(at.astimezone(zone).isoformat() for at in (start,end))
                        source=batch([],source="commerce");complete=claims_for(source)[0]
                        partial=replace(complete,start=start,end=end,state="incomplete",gaps=((start,end),),
                                        evidence_ref="boundary-gap")
                        output=self.calculate(source,(complete,partial),time_policy)
                        self.assertEqual(output.feature_rows[0]["F02"],None if overlaps else 0)
                        self.assertEqual(set(quality(output,"F02")["reasons"]),
                                         {"OBSERVATION_UNKNOWN","INCOMPLETE_WINDOW"} if overlaps else set())

    def test_N12705_partial_complete_is_not_unioned_and_zero_requires_full_evidence(self):
        source=batch([],source="commerce");whole=claims_for(source)[0]
        for claims,wanted,reasons in [((whole,),0,set()),((),None,{"OBSERVATION_UNKNOWN"}),
            ((replace(whole,end="2026-09-01T00:00:00+09:00",evidence_ref="first-half"),
              replace(whole,start="2026-09-01T00:00:00+09:00",evidence_ref="second-half")),None,
             {"OBSERVATION_UNKNOWN","INCOMPLETE_WINDOW"})]:
            with self.subTest(refs=[c.evidence_ref for c in claims]):
                output=self.calculate(source,claims)
                self.assertEqual(output.feature_rows[0]["F02"],wanted)
                self.assertEqual(set(quality(output,"F02")["reasons"]),reasons)

    def test_N12706_overlapping_incomplete_scope_is_conservative_even_if_listed_gap_is_outside(self):
        source=batch([],source="commerce");whole=claims_for(source)[0]
        incomplete=replace(whole,state="incomplete",evidence_ref="incomplete-broad-scope",
                           gaps=(("2026-07-01T00:00:00+09:00","2026-07-02T00:00:00+09:00"),))
        output=self.calculate(source,(whole,incomplete))
        self.assertIsNone(output.feature_rows[0]["F02"])
        self.assertEqual(set(quality(output,"F02")["reasons"]),{"OBSERVATION_UNKNOWN","INCOMPLETE_WINDOW"})

    def test_N12707_partial_evidence_identity_mismatches_are_still_input_errors(self):
        source=batch([],source="commerce");whole=claims_for(source)[0]
        partial=replace(whole,start="2026-10-01T00:00:00+09:00",end="2026-10-02T00:00:00+09:00",
                        state="unknown",evidence_ref="wrong-pin")
        for bad,message in [(replace(partial,input_value_sha256="0"*64),"input identity mismatch"),
            (replace(partial,entity=replace(partial.entity,source="simulator")),"outside transaction"),
            (replace(partial,entity=replace(partial.entity,entity_namespace="other")),"outside transaction")]:
            with self.subTest(message=message),self.assertRaisesRegex(D1ContractError,message):
                self.calculate(source,(whole,bad))


class SourceValidationTests(unittest.TestCase):
    """#128: synthetic purpose never overrides the public event provenance rule."""

    def test_N12801_mixed_misdeclared_and_noncontract_sources_reject_whole_batch(self):
        for name,declared,kinds in [("mixed-as-simulator","simulator",("commerce","simulator")),
            ("mixed-as-commerce","commerce",("commerce","simulator")),
            ("commerce-as-simulator","simulator",("commerce",)),
            ("simulator-as-commerce","commerce",("simulator",))]:
            with self.subTest(case=name):
                records=[event("purchase",number=n,**(dict(simulator_version="sim-fixture",random_seed=7)
                         if kind=="simulator" else {})) for n,kind in enumerate(kinds,1)]
                unchanged=[dict(record) for record in records]
                with self.assertRaisesRegex(D1ContractError,"event source mismatch"):
                    source=batch(records,source=declared)
                    calculate_features([source],index_date=INDEX,policy=policy(),observation_claims=claims_for(source))
                self.assertEqual(records,unchanged)
        for declared in ("synthetic","s1","other","",None):
            for empty in (False,True):
                with self.subTest(invalid_source=declared,empty=empty),self.assertRaisesRegex(
                        D1ContractError,"unsupported contract source"):
                    batch([] if empty else [event("purchase")],source=declared)

    def test_N12802_normal_and_single_meta_field_follow_public_event_source(self):
        cases=[("commerce",None,None),("simulator","sim-fixture",7),
               ("simulator","sim-fixture",None),("simulator",None,0)]
        for declared,version,seed in cases:
            with self.subTest(source=declared,version=version,seed=seed):
                record=event("purchase",simulator_version=version,random_seed=seed);unchanged=dict(record)
                self.assertEqual(event_source(record).value,declared)
                source=batch([record],source=declared)
                output=calculate_features([source],index_date=INDEX,policy=policy(),observation_claims=claims_for(source))
                self.assertEqual(record,unchanged)
                self.assertEqual((output.feature_rows[0]["source"],output.feature_rows[0]["F02"],
                                  output.feature_rows[0]["F03"]),(declared,1,100))
                self.assertEqual(output.reproducibility[0]["source"],declared)
                self.assertEqual(output.reproducibility[0]["policy"]["purpose"],"synthetic")

    def test_N12803_same_customer_id_from_two_sources_and_namespaces_stays_separate(self):
        sources=[batch([event("purchase",order_amount=100)],source="commerce",namespace="n1"),
                 batch([event("purchase",order_amount=300,simulator_version="sim-fixture",random_seed=7)],
                       source="simulator",namespace="n1"),
                 batch([event("purchase",order_amount=400)],source="commerce",namespace="n2")]
        output=calculate_features(sources,index_date=INDEX,policy=policy(),
                                  observation_claims=tuple(c for source in sources for c in claims_for(source)))
        actual={(row["source"],row["entity_namespace"],row["customer_id"]):row["F03"] for row in output.feature_rows}
        self.assertEqual(actual,{("commerce","n1",CUSTOMER):100,("simulator","n1",CUSTOMER):300,
                                 ("commerce","n2",CUSTOMER):400})
        self.assertEqual(len({r["input_value_sha256"] for r in output.reproducibility}),3)
        self.assertEqual(len(output.learning_view(["F02"])["keys"]),3)

    def test_N12804_empty_contract_batches_preserve_roster_without_inventing_observation(self):
        for declared in ("commerce","simulator"):
            with self.subTest(source=declared):
                source=batch([],source=declared,roster=(CUSTOMER,"C00000002"))
                empty=calculate_features([source],index_date=INDEX,policy=policy())
                self.assertEqual(len(empty.feature_rows),2)
                self.assertTrue(all(row["F02"] is None for row in empty.feature_rows))
                complete=calculate_features([source],index_date=INDEX,policy=policy(),observation_claims=claims_for(source))
                self.assertTrue(all(row["F02"]==0 and row["source"]==declared for row in complete.feature_rows))
                self.assertEqual(complete.reproducibility[0]["population_scope"],"explicit_roster")


class FollowupObservationTests(unittest.TestCase):
    def test_REG01_gap_boundary_is_independent_of_wider_unknown_claim_scope(self):
        for name,tp in (("P1",policy("le","2026-10-19T23:59:59+09:00")),
                        ("P2",policy("lt","2026-10-19T23:59:59+09:00")),("P3",policy())):
            window=tp.window(INDEX,90);tick=timedelta(microseconds=1)
            cases=[("end_at_start",window.start-tick,window.start,False),
                   ("start_at_start",window.start,window.start+tick,True),
                   ("end_at_end",window.end-tick,window.end,True),
                   ("start_at_end",window.end,window.end+tick,name=="P1"),
                   ("after_end",window.end+tick,window.end+2*tick,False)]
            for zone in (timezone.utc,timezone(timedelta(hours=9))):
                for label,start,end,intersects in cases:
                    with self.subTest(policy=name,gap=label,zone=zone):
                        source=batch([]);whole=claims_for(source)[0]
                        broad=replace(whole,state="unknown",end="2026-10-21T00:00:00+09:00",
                            gaps=((start.astimezone(zone).isoformat(),end.astimezone(zone).isoformat()),),
                            evidence_ref="wide-claim-narrow-gap")
                        result=calculate_features([source],index_date=INDEX,policy=tp,observation_claims=(whole,broad))
                        q=quality(result,"F02")
                        self.assertIsNone(result.feature_rows[0]["F02"])
                        self.assertEqual(set(q["reasons"]),{"OBSERVATION_UNKNOWN","INCOMPLETE_WINDOW"}
                                         if intersects else {"OBSERVATION_UNKNOWN"})
                        self.assertIn(broad.evidence_ref,q["evidence_refs"])

    def test_REG02_unobserved_activity_type_propagates_to_multi_type_features(self):
        for event_type,unavailable in (("search",True),("purchase",True),("campaign_exposed",False)):
            with self.subTest(event_type=event_type):
                source=batch([event("page_view","2026-10-02T06:00:00+09:00",1),
                              event("product_view","2026-10-03T18:00:00+09:00",2)])
                whole=claims_for(source)[0]
                partial=replace(whole,event_types=frozenset({event_type}),state="incomplete",
                    start="2026-10-01T00:00:00+09:00",end="2026-10-04T00:00:00+09:00",evidence_ref="type-gap")
                result=calculate_features([source],index_date=INDEX,policy=policy(),observation_claims=(whole,partial))
                for fid,normal in (("F10",2),("F29",0.5),("F30",0.5)):
                    self.assertEqual(result.feature_rows[0][fid],None if unavailable else normal)
                    self.assertEqual(quality(result,fid)["audit_counts"]["observed_events"],2)
                    self.assertEqual(set(quality(result,fid)["reasons"]),
                                     {"OBSERVATION_UNKNOWN","INCOMPLETE_WINDOW"} if unavailable else set())

    def test_REG03_multi_type_observation_uses_each_features_own_period(self):
        source=batch([event("page_view","2026-10-02T06:00:00+09:00")]);whole=claims_for(source)[0]
        older=replace(whole,event_types=frozenset({"search"}),state="unknown",
                      start="2026-09-01T00:00:00+09:00",end="2026-09-02T00:00:00+09:00",evidence_ref="older-search")
        result=calculate_features([source],index_date=INDEX,policy=policy(),observation_claims=(whole,older))
        self.assertEqual(result.feature_rows[0]["F10"],1)
        self.assertIsNone(result.feature_rows[0]["F29"])
        self.assertEqual(quality(result,"F29")["reasons"],["OBSERVATION_UNKNOWN"])
