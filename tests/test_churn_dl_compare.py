"""#218 Validation 선택·공통 Test 형식의 독립 합성 반례."""
from dataclasses import replace
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

BASE=all(importlib.util.find_spec(x) is not None for x in ('numpy','pandas','sklearn','yaml'))


@unittest.skipUnless(BASE,'BLOCKED: numpy/pandas/sklearn/PyYAML required')
class TestDLCommonComparison(unittest.TestCase):
    def setUp(self):
        import pandas as pd
        from src.decision.churn_dl_compare import ComparisonProtocol
        self.p=ComparisonProtocol('synthetic-protocol-v1','contract-fixture','simulator','synthetic',
            'tests:test_churn_dl_compare',('T1','T2'),('V1','V2','V3','V4'),('E1','E2','E3','E4'))
        self.yv=pd.Series([0,1,0,1],index=self.p.validation_ids)
        self.ml=pd.Series([.1,.8,.2,.9],index=self.p.validation_ids)
        self.dl=pd.Series([.3,.6,.4,.7],index=self.p.validation_ids)
        self.yt=pd.Series([0,1,1,0],index=self.p.test_ids)
        self.mt=pd.Series([.2,.8,.7,.1],index=self.p.test_ids)
        self.dt=pd.Series([.3,.7,.8,.2],index=self.p.test_ids)

    def select(self,**kwargs):
        from src.decision.churn_dl_compare import select_ensemble
        return select_ensemble(self.p,self.yv,self.ml,self.dl,alpha_grid=(0.,.5,1.),**kwargs)

    def test_validation_selects_endpoint_without_forcing_improvement(self):
        s=self.select()
        self.assertEqual(0.,s.alpha)
        self.assertEqual(3,len(s.candidates))

    def test_equal_predictions_prefer_simpler_ml(self):
        from src.decision.churn_dl_compare import select_ensemble
        s=select_ensemble(self.p,self.yv,self.ml,self.ml,alpha_grid=(1.,.5,0.))
        self.assertEqual(0.,s.alpha)

    def test_test_labels_are_not_selection_arguments(self):
        with self.assertRaises(TypeError):self.select(test_labels=self.yt)

    def test_misordered_predictions_align_by_id(self):
        from src.decision.churn_dl_compare import select_ensemble
        s=select_ensemble(self.p,self.yv.iloc[::-1],self.ml.iloc[::-1],self.dl.iloc[::-1],alpha_grid=(0.,.5,1.))
        self.assertEqual(self.select(),s)

    def test_missing_duplicate_and_extra_prediction_ids_refused(self):
        import pandas as pd
        from src.decision.churn_dl_compare import select_ensemble
        for bad in (self.ml.iloc[:-1],pd.concat([self.ml,self.ml.iloc[:1]]),self.ml.rename(index={'V1':'other'})):
            with self.subTest(index=bad.index.tolist()),self.assertRaises(ValueError):
                select_ensemble(self.p,self.yv,bad,self.dl)

    def test_nonfinite_and_out_of_range_probabilities_refused(self):
        from src.decision.churn_dl_compare import select_ensemble
        for value in (float('nan'),float('inf'),-.1,1.1):
            bad=self.ml.copy();bad.iloc[0]=value
            with self.subTest(value=value),self.assertRaises(ValueError):select_ensemble(self.p,self.yv,bad,self.dl)

    def test_source_formal_and_overlapping_protocols_refused(self):
        for changes in ({'source':'commerce'},{'purpose':'formal'},{'test_ids':('T1','E2')},
                        {'validation_ids':('V1','V1')},{'evidence_ref':''}):
            with self.subTest(changes=changes),self.assertRaises(ValueError):replace(self.p,**changes)

    def test_same_test_hashes_and_no_formal_claim(self):
        from src.decision.churn_dl_compare import evaluate_common_test
        with tempfile.TemporaryDirectory() as d:
            r=evaluate_common_test(self.p,self.select(),self.yt,self.mt,self.dt,directory=Path(d)/'run')
            self.assertEqual(1,len({m['test_ids_sha256'] for m in r['models']}))
            self.assertFalse(r['formal_evaluation'])
            self.assertFalse(r['mixing_used'])
            self.assertFalse(r['final_holdout_used'])
            self.assertEqual('completed',json.loads((Path(d)/'run/test_access.json').read_text())['status'])

    def test_test_label_changes_never_change_frozen_selection(self):
        from src.decision.churn_dl_compare import evaluate_common_test
        s=self.select()
        with tempfile.TemporaryDirectory() as d:
            a=evaluate_common_test(self.p,s,self.yt,self.mt,self.dt,directory=Path(d)/'a')
            b=evaluate_common_test(self.p,s,1-self.yt,self.mt,self.dt,directory=Path(d)/'b')
            self.assertEqual(a['selection'],b['selection'])
            self.assertNotEqual(a['models'][0]['metrics'],b['models'][0]['metrics'])

    def test_second_use_of_same_output_directory_refused(self):
        from src.decision.churn_dl_compare import evaluate_common_test
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'r';s=self.select()
            evaluate_common_test(self.p,s,self.yt,self.mt,self.dt,directory=p)
            with self.assertRaises(FileExistsError):evaluate_common_test(self.p,s,self.yt,self.mt,self.dt,directory=p)

    def test_protocol_mismatch_refused(self):
        from src.decision.churn_dl_compare import evaluate_common_test
        with tempfile.TemporaryDirectory() as d,self.assertRaises(ValueError):
            evaluate_common_test(replace(self.p,dataset_version='another-run'),self.select(),
                                 self.yt,self.mt,self.dt,directory=Path(d)/'r')

    def test_missing_or_one_class_test_labels_refused(self):
        from src.decision.churn_dl_compare import evaluate_common_test
        for labels in (self.yt.iloc[:-1],self.yt*0,self.yt.astype(float).where(self.yt.index!='E1')):
            with self.subTest(labels=labels.tolist()),tempfile.TemporaryDirectory() as d,self.assertRaises(ValueError):
                evaluate_common_test(self.p,self.select(),labels,self.mt,self.dt,directory=Path(d)/'r')


if __name__=='__main__':unittest.main()
