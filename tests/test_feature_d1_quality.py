"""Explicit-population counts, not inferred eligibility or an official gate."""

from copy import deepcopy
from dataclasses import replace
from datetime import date
import random
import unittest

from src.decision.features.d1_calculate import FeatureOutput, calculate_features
from src.decision.features.d1_quality_summary import aggregate_raw_quality
from src.decision.features.d1_serialization import D1ContractError
from tests.test_feature_d1_calculation import CUSTOMER, INDEX, ORIGIN, batch, claims_for, event, policy


def population(customers=(CUSTOMER,),source="commerce",namespace="fixture",index_date=INDEX):
    return [dict(entity_namespace=namespace,source=source,customer_id=customer,index_date=index_date) for customer in customers]


def mixed_output():
    source=batch([event("purchase",customer=CUSTOMER)],roster=(CUSTOMER,"C00000002","C00000003"))
    return calculate_features([source],index_date=INDEX,policy=policy(),observation_claims=claims_for(source)[:2],generated_at=ORIGIN)


class RawQualityTests(unittest.TestCase):
    def test_QUAL01_explicit_roster_counts_known_zero_and_unknown_separately(self):
        output=mixed_output();cohort=population((CUSTOMER,"C00000002","C00000003"))
        result=aggregate_raw_quality(output,population=cohort,feature_ids=["F02","F03","F36"])
        self.assertEqual((result["population_count"],result["entity_count"]),(3,3))
        frequency,money,embedding=result["summaries"]
        for item in (frequency,money):
            self.assertEqual((item["denominator"],item["missing_count"],item["available_count"]),(3,1,2))
            self.assertEqual(item["missing_rate"],1/3);self.assertEqual(item["reason_counts"],{"OBSERVATION_UNKNOWN":1})
        self.assertEqual((embedding["denominator"],embedding["missing_count"]),(3,3))
        self.assertEqual(embedding["reason_counts"],{"TRANSFORM_NOT_FITTED":3})
        self.assertIsNone(result["official_verdict"]);self.assertEqual(result["excluded_count"],0)

    def test_QUAL02_multiple_reasons_can_sum_above_population(self):
        source=batch([],roster=(CUSTOMER,"C00000002"));whole=claims_for(source)
        incomplete=replace(whole[0],state="incomplete",evidence_ref="incomplete")
        unsupported=replace(whole[1],state="unsupported",evidence_ref="unsupported")
        output=calculate_features([source],index_date=INDEX,policy=policy(),observation_claims=(*whole,incomplete,unsupported))
        item=aggregate_raw_quality(output,population=population((CUSTOMER,"C00000002")),feature_ids=["F02"])["summaries"][0]
        self.assertEqual((item["denominator"],item["missing_count"]),(2,2))
        self.assertEqual(item["reason_counts"],{"INCOMPLETE_WINDOW":1,"OBSERVATION_UNKNOWN":2,"UNSUPPORTED_EVENT_KIND":1})
        self.assertEqual(sum(item["reason_counts"].values()),4)

    def test_QUAL03_requested_population_and_feature_order_are_preserved_without_mutation(self):
        output=mixed_output();before=deepcopy(output)
        result=aggregate_raw_quality(output,population=population(),feature_ids=["F36","F02"])
        self.assertEqual(result["feature_ids"],["F36","F02"])
        self.assertEqual([row["missing_count"] for row in result["summaries"]],[1,0])
        self.assertEqual(result["summaries"][1]["missing_rate"],0)
        self.assertEqual(output,before)

    def test_QUAL04_zero_population_is_unavailable_not_zero_percent(self):
        result=aggregate_raw_quality(FeatureOutput([],[],[]),population=[],feature_ids=["F02","F36"])
        self.assertEqual(result["population_count"],0)
        for item in result["summaries"]:
            self.assertEqual((item["denominator"],item["missing_count"],item["available_count"]),(0,0,0))
            self.assertIsNone(item["missing_rate"]);self.assertEqual(item["reasons"],["ZERO_DENOMINATOR"])
            self.assertEqual(item["status"],"unavailable");self.assertIsNone(item["official_verdict"])

    def test_QUAL05_duplicates_and_population_metadata_are_input_errors(self):
        for variant,message in (("population","duplicate population K"),("canonical","duplicate canonical K"),
                                ("quality","duplicate quality K/Feature"),("metadata","only explicit K")):
            output=mixed_output();cohort=population()
            if variant=="population":cohort+=deepcopy(cohort)
            if variant=="canonical":output.feature_rows.append(deepcopy(output.feature_rows[0]))
            if variant=="quality":output.quality_rows.append(deepcopy(output.quality_rows[0]))
            if variant=="metadata":cohort[0]["eligible"]=True
            with self.subTest(variant=variant),self.assertRaisesRegex(D1ContractError,message):
                aggregate_raw_quality(output,population=cohort,feature_ids=["F02"])

    def test_QUAL06_missing_population_rows_columns_and_quality_are_not_silently_excluded(self):
        for variant,message in (("row","missing canonical row"),("column","column missing"),("quality","missing quality row")):
            output=mixed_output()
            if variant=="row":output.feature_rows.pop(0)
            if variant=="column":del output.feature_rows[0]["F02"]
            if variant=="quality":output=replace(output,quality_rows=[r for r in output.quality_rows if not(r["customer_id"]==CUSTOMER and r["feature_id"]=="F02")])
            with self.subTest(variant=variant),self.assertRaisesRegex(D1ContractError,message):
                aggregate_raw_quality(output,population=population(),feature_ids=["F02"])

    def test_QUAL07_availability_reasons_and_nonfinite_inputs_must_be_consistent(self):
        for variant,message in (("null-available","availability mismatch"),("nonnull-unavailable","availability mismatch"),
            ("nonnull-reason","availability mismatch"),("null-no-reason","availability mismatch"),
            ("duplicate-reason","unique nonempty"),("empty-code","unique nonempty"),("nan","nonfinite")):
            output=mixed_output();row=output.feature_rows[0]
            q=next(r for r in output.quality_rows if r["customer_id"]==CUSTOMER and r["feature_id"]=="F02")
            if variant=="null-available":row["F02"]=None
            if variant=="nonnull-unavailable":q.update(availability="unavailable",reasons=["OBSERVATION_UNKNOWN"])
            if variant=="nonnull-reason":q["reasons"]=["OBSERVATION_UNKNOWN"]
            if variant=="null-no-reason":row["F02"]=None;q["availability"]="unavailable"
            if variant=="duplicate-reason":q["reasons"]=["OBSERVATION_UNKNOWN"]*2
            if variant=="empty-code":q["reasons"]=[""]
            if variant=="nan":row["F02"]=float("nan")
            with self.subTest(variant=variant),self.assertRaisesRegex(D1ContractError,message):
                aggregate_raw_quality(output,population=population(),feature_ids=["F02"])

    def test_QUAL08_source_namespace_and_multiple_index_dates_are_distinct_K_rows(self):
        sources=[batch([event("purchase")],source="commerce",namespace="n1"),
                 batch([event("purchase",simulator_version="sim-fixture",random_seed=7)],source="simulator",namespace="n1"),
                 batch([event("purchase")],source="commerce",namespace="n2")]
        first=calculate_features(sources,index_date=INDEX,policy=policy(),
                                 observation_claims=tuple(c for s in sources for c in claims_for(s)))
        earlier=date(2026,10,19)
        second=calculate_features([sources[0]],index_date=earlier,policy=policy(boundary="2026-10-19T00:00:00+09:00"),
                                  observation_claims=claims_for(sources[0]))
        output=FeatureOutput(first.feature_rows+second.feature_rows,first.quality_rows+second.quality_rows,[])
        cohort=population(source="commerce",namespace="n1")+population(source="simulator",namespace="n1")+population(namespace="n2")+population(namespace="n1",index_date=earlier)
        result=aggregate_raw_quality(output,population=cohort,feature_ids=["F36"])
        self.assertEqual((result["population_count"],result["entity_count"]),(4,3))
        self.assertEqual(result["summaries"][0]["missing_count"],4)
        self.assertEqual(result["pending_decisions"],["SD6","SD7"])

    def test_QUAL09_input_order_does_not_change_counts_or_population_identity(self):
        output=mixed_output();cohort=population((CUSTOMER,"C00000002","C00000003"))
        first=aggregate_raw_quality(output,population=cohort,feature_ids=["F02","F36"])
        random.Random(7).shuffle(output.feature_rows);random.Random(8).shuffle(output.quality_rows);cohort.reverse()
        self.assertEqual(first,aggregate_raw_quality(output,population=cohort,feature_ids=["F02","F36"]))

    def test_QUAL10_all_42_requested_features_including_deferred_columns_remain(self):
        source=batch([]);output=calculate_features([source],index_date=INDEX,policy=policy(),observation_claims=claims_for(source))
        ids=[f"F{n:02d}" for n in range(1,43)]
        result=aggregate_raw_quality(output,population=population(),feature_ids=ids)
        self.assertEqual(result["feature_ids"],ids);self.assertEqual(len(result["summaries"]),42)
        self.assertTrue(all(row["denominator"]==1 and row["missing_count"]==1 for row in result["summaries"][30:41]))
        self.assertTrue(all(row["official_verdict"] is None for row in result["summaries"]))

    def test_QUAL11_invalid_feature_lists_and_unknown_population_keys_are_rejected(self):
        for ids in ([],["F02","F02"],["F43"],["customer_id"]):
            with self.subTest(ids=ids),self.assertRaises(D1ContractError):
                aggregate_raw_quality(mixed_output(),population=population(),feature_ids=ids)
        with self.assertRaisesRegex(D1ContractError,"missing canonical row"):
            aggregate_raw_quality(mixed_output(),population=population(("C00000009",)),feature_ids=["F02"])

    def test_QUAL12_calendar_key_normalization_does_not_mutate_caller_population(self):
        output=mixed_output();cohort=population(index_date="2026-10-20");before=deepcopy(cohort)
        first=aggregate_raw_quality(output,population=cohort,feature_ids=["F02"])
        self.assertEqual(first,aggregate_raw_quality(output,population=population(),feature_ids=["F02"]))
        self.assertEqual(cohort,before);self.assertEqual(first["short_history_adjustment"],"not_applied")

    def test_QUAL13_malformed_canonical_container_and_quality_feature_ID_are_input_errors(self):
        with self.assertRaisesRegex(D1ContractError,"row lists required"):
            aggregate_raw_quality(FeatureOutput(None,[],[]),population=population(),feature_ids=["F02"])
        output=mixed_output();output.quality_rows[0]["feature_id"]=[]
        with self.assertRaisesRegex(D1ContractError,"invalid quality Feature ID"):
            aggregate_raw_quality(output,population=population(),feature_ids=["F02"])
