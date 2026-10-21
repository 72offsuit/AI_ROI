"""Synthetic facts exercise fixed session formulas, not an SD3 event adapter."""

from dataclasses import replace
from datetime import date
import unittest

from src.decision.features.d1_feature_inputs import Entity,TimePolicy
from src.decision.features.d1_session_kernels import SessionFact,calculate_session_kernels
from src.decision.features.d1_serialization import D1ContractError

ENTITY=Entity("fixture","commerce","C00000001")
POLICY=TimePolicy("explicit-session-fixture","2026-10-20T00:00:00+09:00","lt","us",
                  "2026-01-01T00:00:00+09:00","synthetic")
INPUT="1"*64


def fact(number,at="2026-10-10T00:00:00+09:00",*,converted=True,**changes):
    values=dict(entity=ENTITY,session_id=f"S-C00000001-{1760000000000+number}",started_at=at,ended_at=at,
        completion="complete",observation_complete=True,duration_seconds=20,page_views=2,
        search_present=True,search_converted=converted,cart_present=True,cart_converted=converted,
        input_value_sha256=INPUT,evidence_ref=f"synthetic-verified-session-{number}")
    values.update(changes)
    return SessionFact(**values)


def calculate(facts,population=True):
    return calculate_session_kernels(facts,entity=ENTITY,index_date=date(2026,10,20),policy=POLICY,
                                     population_complete=population,input_value_sha256=INPUT)


class SessionKernelTests(unittest.TestCase):
    def test_SESS01_mean_page_depth_search_conversion_and_duration_change(self):
        result=calculate([fact(1,duration_seconds=10,page_views=2),fact(2,converted=False,duration_seconds=30,page_views=4),
                          fact(3,"2026-09-30T00:00:00+09:00",converted=False,duration_seconds=40,page_views=3)])
        self.assertEqual(result["F31"].value,80/3)
        self.assertEqual(result["F32"].value,3)
        self.assertEqual(result["F33"].value,1/3)
        self.assertEqual(result["F34"].value,-20)

    def test_SESS02_three_valued_conversion_keeps_unknown_audit_denominator(self):
        known=[fact(1),fact(2,converted=False)]
        result=calculate(known)["F33"]
        self.assertEqual((result.value,result.numerator,result.denominator),(0.5,1,2))
        unknown=calculate(known+[fact(3,converted=None)])["F33"]
        self.assertIsNone(unknown.value);self.assertIsNone(unknown.numerator);self.assertIsNone(unknown.denominator)
        self.assertEqual(unknown.audit_counts["n_true"],1)
        self.assertEqual(unknown.audit_counts["n_false"],1)
        self.assertEqual(unknown.audit_counts["n_unknown_outcome"],1)
        self.assertEqual(unknown.audit_counts["observed_denominator"],3)

    def test_SESS03_cart_conversion_change_and_period_audits(self):
        recent=[fact(1),fact(2,converted=False)]
        previous=[fact(n,"2026-09-01T00:00:00+09:00",converted=n==3) for n in (3,4,5,6)]
        result=calculate(recent+previous)["F35"]
        self.assertEqual(result.value,0.25)
        unknown=calculate(recent+previous+[fact(7,converted=None)])["F35"]
        self.assertIsNone(unknown.value)
        self.assertEqual(unknown.audit_counts["recent_n_unknown_outcome"],1)
        self.assertEqual(unknown.audit_counts["recent_observed_denominator"],3)
        self.assertEqual(unknown.audit_counts["previous_observed_denominator"],4)

    def test_SESS04_unknown_membership_is_not_dropped(self):
        cases=[fact(2,started_at=None),fact(2,completion="unknown",ended_at=None),
               fact(2,search_present=None,search_converted=None)]
        for unknown in cases:
            with self.subTest(unknown=unknown):
                result=calculate([fact(1),unknown])["F33"]
                self.assertIsNone(result.value)
                self.assertEqual(result.audit_counts["n_unknown_membership"],1)
                self.assertEqual(result.audit_counts["n_true"],1)

    def test_SESS05_open_sessions_are_explicitly_excluded(self):
        result=calculate([fact(1),fact(2,completion="open",ended_at=None)])["F33"]
        self.assertEqual(result.value,1)
        self.assertEqual(result.audit_counts["n_open_excluded"],1)

    def test_SESS06_missing_optional_duration_is_null_not_zero_or_partial_mean(self):
        result=calculate([fact(1),fact(2,duration_seconds=None)])
        self.assertIsNone(result["F31"].value)
        self.assertIn("MISSING_DURATION",result["F31"].reasons)
        self.assertEqual(result["F31"].audit_counts["missing_duration_seconds"],1)
        self.assertEqual(result["F32"].value,2)

    def test_SESS07_no_antecedent_zero_denominator_and_true_zero_conversion(self):
        no=calculate([fact(1,search_present=False,search_converted=False)])["F33"]
        self.assertIsNone(no.value);self.assertEqual(no.reasons,("ZERO_DENOMINATOR",))
        self.assertEqual(no.audit_counts["n_no_antecedent"],1)
        zero=calculate([fact(1,converted=False)])["F33"]
        self.assertEqual(zero.value,0)
        self.assertEqual(zero.denominator,1)

    def test_SESS08_unknown_population_and_incomplete_observation_not_measured_zero(self):
        for population,reason in ((None,"OBSERVATION_UNKNOWN"),(False,"INCOMPLETE_WINDOW")):
            result=calculate([],population)["F33"]
            self.assertIsNone(result.value)
            self.assertIn(reason,result.reasons)
            self.assertNotIn("ZERO_DENOMINATOR",result.reasons)
        result=calculate([fact(1,observation_complete=None,page_views=None)])["F32"]
        self.assertIsNone(result.value)
        self.assertIn("OBSERVATION_UNKNOWN",result.reasons)

    def test_SESS09_contradictory_or_future_facts_rejected(self):
        for changes,message in [(dict(ended_at=None),"end proof"),
                                (dict(observation_complete=False,converted=False),"absence needs complete"),
                                (dict(duration_seconds=-1),"invalid session scalar"),
                                (dict(search_present=False,search_converted=True),"requires known antecedent")]:
            with self.subTest(changes=changes),self.assertRaisesRegex(D1ContractError,message): fact(1,**changes)
        with self.assertRaisesRegex(D1ContractError,"future session fact"):
            calculate([fact(1,"2026-10-20T00:00:00+09:00")])

    def test_SESS10_duplicate_source_identity_and_input_pins_rejected(self):
        with self.assertRaisesRegex(D1ContractError,"duplicate session fact"):calculate([fact(1),fact(1)])
        with self.assertRaisesRegex(D1ContractError,"input identity mismatch"):
            calculate([fact(1,input_value_sha256="2"*64)])
        with self.assertRaisesRegex(D1ContractError,"source/namespace/customer"):
            calculate([fact(1,entity=Entity("other","commerce","C00000001"))])

    def test_SESS11_start_membership_and_comparison_boundary(self):
        facts=[fact(1,"2026-09-22T00:00:00+09:00",duration_seconds=40),
               fact(2,"2026-10-06T00:00:00+09:00",duration_seconds=10)]
        self.assertEqual(calculate(facts)["F34"].value,-30)
        self.assertEqual(calculate(list(reversed(facts))),calculate(facts))

    def test_SESS12_empty_completed_population_does_not_create_zero_average(self):
        result=calculate([])
        for fid in ("F31","F32","F33"):
            self.assertIsNone(result[fid].value)
            self.assertIn("ZERO_DENOMINATOR",result[fid].reasons)
