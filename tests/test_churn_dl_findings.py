"""#283~#288: #218 독립 검수에서 재현한 결함의 회귀 시험. 합성 입력만 사용한다."""
from dataclasses import replace
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

BASE = all(importlib.util.find_spec(x) is not None for x in ('numpy', 'pandas', 'sklearn', 'yaml'))
TORCH = importlib.util.find_spec('torch') is not None


@unittest.skipUnless(BASE, 'BLOCKED: numpy/pandas/sklearn/PyYAML required')
class TestDLReviewInputFindings(unittest.TestCase):
    def test_283_invalid_event_customer_keys_are_rejected_before_join(self):
        from tests.test_churn_lstm import fixture
        for key in (1, None, '', ' C1', 'C1 '):
            row = dict(customer_id=key, event_id='E', timestamp='2026-10-21T12:00:00+09:00',
                       event_type='purchase', simulator_version='fixture', random_seed=0)
            with self.subTest(key=key), self.assertRaises(ValueError):
                fixture(('C1',), records=[row])

    def test_283_legitimate_subset_and_zero_history_are_retained_and_audited(self):
        from tests.test_churn_lstm import fixture
        rows = [dict(customer_id='OTHER', event_id='E', timestamp='2026-10-21T12:00:00+09:00',
                     event_type='purchase', simulator_version='fixture', random_seed=0)]
        b = fixture(('C1',), records=rows)
        b.validate(for_model=True)
        self.assertEqual([1], b.tokens[0, :b.lengths[0]].tolist())
        self.assertEqual(1, b.metadata['rows_outside_population'])
        self.assertEqual(1, b.metadata['customers_with_no_window_events'])

    def test_284_unknown_ready_escalation_is_rejected(self):
        import numpy as np
        from tests.test_churn_lstm import fixture
        b = fixture(('C1', 'C2'), status='unknown')
        with self.assertRaises(ValueError):
            replace(b, ready=np.ones(2, bool), reasons=(None, None)).validate(for_model=True)

    def test_284_commerce_top_level_relabelling_is_rejected(self):
        from tests.test_churn_lstm import fixture
        c = fixture(('C1',), source='commerce')
        with self.assertRaises(ValueError):
            replace(c, metadata={**c.metadata, 'source': 'simulator', 'purpose': 'experiment'}).validate(for_model=True)

    def test_284_metadata_is_recursively_immutable(self):
        from tests.test_churn_lstm import fixture
        b = fixture(('C1',))
        with self.assertRaises(TypeError):
            b.metadata['source'] = 'commerce'
        with self.assertRaises(TypeError):
            b.metadata['coverage'][0]['status'] = 'unknown'
        with self.assertRaises(ValueError):
            b.tokens[0, 0] = 0
        with self.assertRaises(ValueError):b.tokens.setflags(write=True)

    def test_284_mutating_constructor_inputs_does_not_mutate_batch(self):
        from tests.test_churn_lstm import fixture
        from src.decision.churn_sequence import thaw_json
        b = fixture(('C1',))
        metadata = thaw_json(b.metadata)
        tokens = b.tokens.copy()
        clone = replace(b, metadata=metadata, tokens=tokens)
        metadata['coverage'][0]['status'] = 'unknown'
        tokens[0, 0] = 0
        clone.validate(for_model=True)
        self.assertEqual('complete', clone.metadata['coverage'][0]['status'])

    def test_284_coverage_order_and_secondary_hash_mismatch_are_rejected(self):
        from tests.test_churn_lstm import fixture
        from src.decision.churn_sequence import thaw_json
        b = fixture(('C1', 'C2'))
        for key, value in [('ids_sha256', 'wrong'), ('max_events', 1000)]:
            with self.subTest(key=key), self.assertRaises(ValueError):
                replace(b, metadata={**b.metadata, key: value}).validate(for_model=True)
        md = thaw_json(b.metadata)
        md['coverage'].reverse()
        with self.assertRaises(ValueError):replace(b, metadata=md).validate(for_model=True)

    def test_284_exact_utc_t0_event_is_excluded(self):
        from tests.test_churn_lstm import fixture
        row = dict(customer_id='C1', event_id='E', timestamp='2026-10-21T15:00:00Z',
                   event_type='purchase', simulator_version='fixture', random_seed=0)
        b = fixture(('C1',), records=[row])
        self.assertEqual([1], b.tokens[0, :b.lengths[0]].tolist())

    def test_283_audit_counts_partition_scoped_input_without_changing_it(self):
        from tests.test_churn_lstm import fixture
        rows = [dict(customer_id=cid,event_id=f'E{i}',timestamp=at,event_type='search',
                     simulator_version='fixture',random_seed=0)
                for i,(cid,at) in enumerate([('OTHER','2026-10-21T12:00:00+09:00'),
                     ('C1','2026-10-19T23:59:59+09:00'),('C1','2026-10-21T12:00:00+09:00'),
                     ('C1','2026-10-21T15:00:00Z')])]
        before = json.dumps(rows,sort_keys=True)
        b = fixture(('C1',),records=rows)
        self.assertEqual([4,1,1,1,1],[b.metadata[k] for k in ('rows_input','rows_outside_population',
            'rows_before_window','rows_in_window','rows_at_or_after_t0')])
        self.assertEqual(before,json.dumps(rows,sort_keys=True))

    def test_optional_torch_import_guard_runs_without_torch(self):
        script = '''
import importlib.abc,sys
class BlockTorch(importlib.abc.MetaPathFinder):
 def find_spec(self,name,*a,**k):
  if name=='torch' or name.startswith('torch.'):
   raise ModuleNotFoundError('torch intentionally unavailable')
sys.meta_path.insert(0,BlockTorch())
import src.decision.churn_sequence,src.decision.churn_lstm,src.decision.churn_dl_compare
assert 'torch' not in sys.modules
'''
        subprocess.run([sys.executable, '-B', '-c', script], cwd=Path(__file__).resolve().parents[1],
                       capture_output=True, text=True, check=True)


@unittest.skipUnless(BASE, 'BLOCKED: numpy/pandas/sklearn/PyYAML required')
class TestDLReviewComparisonFindings(unittest.TestCase):
    def setUp(self):
        from tests.test_churn_dl_compare import TestDLCommonComparison
        self.f = TestDLCommonComparison()
        self.f.setUp()

    def test_285_mutable_caller_lists_do_not_change_protocol(self):
        ids = list(self.f.p.test_ids)
        p = replace(self.f.p, test_ids=ids)
        ids.append('V1')
        self.assertIsInstance(p.test_ids, tuple)
        self.assertNotIn('V1', p.test_ids)

    def test_285_entrypoints_revalidate_disjointness(self):
        from src.decision.churn_dl_compare import select_ensemble, evaluate_common_test
        p = replace(self.f.p)
        s = self.f.select()
        object.__setattr__(p, 'test_ids', (*p.test_ids, 'V1'))
        with self.assertRaises(ValueError):select_ensemble(p, self.f.yv, self.f.ml, self.f.dl)
        with tempfile.TemporaryDirectory() as d, self.assertRaises(ValueError):
            evaluate_common_test(p, s, self.f.yt, self.f.mt, self.f.dt, directory=Path(d)/'out')

    def test_286_changed_alpha_empty_candidates_losses_and_thresholds_are_rejected(self):
        from src.decision.churn_dl_compare import evaluate_common_test
        s = self.f.select()
        variants = [dict(alpha=.5), dict(candidates=()), dict(thresholds=(.123, .234, .345)),
                    dict(candidates=tuple((a, loss+1) for a, loss in s.candidates)),
                    dict(validation_label_sha256='wrong')]
        for changes in variants:
            with self.subTest(changes=changes), tempfile.TemporaryDirectory() as d, self.assertRaises(ValueError):
                evaluate_common_test(self.f.p, replace(s, **changes), self.f.yt, self.f.mt, self.f.dt,
                                     directory=Path(d)/'out')

    def test_286_labels_are_hashed_with_customer_ids(self):
        from src.decision.churn_sequence import bound_value_hash
        a = bound_value_hash(('C1','C2'), [0.,1.])
        self.assertNotEqual(a, bound_value_hash(('V1','V2'), [0.,1.]))
        self.assertEqual(a, bound_value_hash(('C2','C1'), [1.,0.]))

    def test_286_snapshot_prediction_tampering_is_rejected(self):
        from src.decision.churn_dl_compare import evaluate_common_test
        s = self.f.select()
        rows = [list(row) for row in s.validation_rows]
        rows[0][2] = .99
        with tempfile.TemporaryDirectory() as d,self.assertRaises(ValueError):
            evaluate_common_test(self.f.p,replace(s,validation_rows=rows),self.f.yt,self.f.mt,self.f.dt,
                                 directory=Path(d)/'out')

    def test_286_json_roundtrip_keeps_selection_evidence_valid(self):
        from dataclasses import asdict
        from src.decision.churn_dl_compare import FrozenSelection
        s = self.f.select()
        restored = FrozenSelection(**json.loads(json.dumps(asdict(s))))
        restored.validate(self.f.p)
        self.assertEqual(s,restored)

    def test_286_selection_is_recorded_before_test_label_read(self):
        from src.decision import churn_dl_compare as module
        from src.decision.churn_artifacts import evaluation_claim_path
        original = module.align_binary_labels
        with tempfile.TemporaryDirectory() as d:
            directory = Path(d)/'out'
            def check(labels, ids, **kw):
                if tuple(ids) == tuple(self.f.p.test_ids):
                    claim = json.loads(evaluation_claim_path(directory).read_text(encoding='utf-8'))
                    self.assertEqual(self.f.select().alpha, claim['selection']['alpha'])
                return original(labels, ids, **kw)
            with patch.object(module, 'align_binary_labels', check):
                module.evaluate_common_test(self.f.p, self.f.select(), self.f.yt, self.f.mt, self.f.dt,
                                            directory=directory)

    def test_287_identical_predictions_respect_tie_rule(self):
        import numpy as np
        import pandas as pd
        from src.decision.churn_dl_compare import ComparisonProtocol, select_ensemble
        rng = np.random.default_rng(0)
        values = rng.uniform(.01, .99, 200)
        labels = (rng.uniform(size=200) < values).astype(float)
        labels[:2] = [0,1]
        ids = tuple(f'V{i}' for i in range(200))
        p = ComparisonProtocol('rounding','fixture','simulator','synthetic','fixture',('T1','T2'),ids,('E1','E2'))
        series = pd.Series(values,index=ids)
        s = select_ensemble(p,pd.Series(labels,index=ids),series,series,alpha_grid=[i/10 for i in range(11)])
        self.assertEqual(0., s.alpha)

    def test_287_real_validation_gain_is_not_suppressed(self):
        from src.decision.churn_dl_compare import select_ensemble
        better = self.f.yv.astype(float)*.98+.01
        s = select_ensemble(self.f.p,self.f.yv,self.f.ml,better,alpha_grid=(0.,.5,1.))
        self.assertEqual(1., s.alpha)

    def test_288_write_failure_never_publishes_ok_result_and_claim_blocks_retry(self):
        from src.decision.churn_dl_compare import evaluate_common_test
        from src.decision.churn_artifacts import evaluation_claim_path
        original = Path.write_text
        def fail(path, content, *args, **kw):
            if path.name == 'test_access.json' and json.loads(content).get('status') == 'completed':
                raise OSError('injected completion write failure')
            return original(path, content, *args, **kw)
        with tempfile.TemporaryDirectory() as d:
            directory = Path(d)/'out'
            with patch.object(Path, 'write_text', fail), self.assertRaises(OSError):
                evaluate_common_test(self.f.p,self.f.select(),self.f.yt,self.f.mt,self.f.dt,directory=directory)
            self.assertFalse(directory.exists())
            self.assertTrue(evaluation_claim_path(directory).is_file())
            with self.assertRaises(FileExistsError):
                evaluate_common_test(self.f.p,self.f.select(),self.f.yt,self.f.mt,self.f.dt,directory=directory)

    def test_288_publish_failure_leaves_no_final_result(self):
        from src.decision.churn_dl_compare import evaluate_common_test
        from src.decision.churn_artifacts import evaluation_claim_path
        with tempfile.TemporaryDirectory() as d:
            target = Path(d)/'out'
            with patch('src.decision.churn_artifacts.os.rename',side_effect=OSError('injected publish error')):
                with self.assertRaises(OSError):
                    evaluate_common_test(self.f.p,self.f.select(),self.f.yt,self.f.mt,self.f.dt,directory=target)
            self.assertFalse(target.exists())
            self.assertTrue(evaluation_claim_path(target).exists())
            self.assertFalse(list(Path(d).glob('*.publish.lock')))

    def test_288_existing_directory_and_files_are_preserved(self):
        from src.decision.churn_dl_compare import evaluate_common_test
        with tempfile.TemporaryDirectory() as d:
            target = Path(d)/'out';target.mkdir()
            sentinel = target/'user.txt';sentinel.write_text('keep',encoding='utf-8')
            with self.assertRaises(FileExistsError):
                evaluate_common_test(self.f.p,self.f.select(),self.f.yt,self.f.mt,self.f.dt,directory=target)
            self.assertEqual('keep',sentinel.read_text(encoding='utf-8'))

    def test_286_test_data_change_does_not_enter_selection_computation(self):
        from src.decision import churn_dl_compare as module
        original = module.align_binary_labels
        seen = []
        def check(labels, ids, **kw):
            seen.append(tuple(ids))
            self.assertEqual(set(self.f.p.validation_ids),set(ids))
            return original(labels, ids, **kw)
        with patch.object(module, 'align_binary_labels', check):
            selection = module.select_ensemble(self.f.p,self.f.yv,self.f.ml,self.f.dl)
        self.assertTrue(seen)
        self.assertNotIn(tuple(self.f.p.test_ids), seen)


@unittest.skipUnless(BASE and TORCH, 'BLOCKED: numpy/pandas/sklearn/PyYAML and torch required')
class TestDLReviewStorageFindings(unittest.TestCase):
    def test_284_actual_fit_refuses_unknown_and_commerce_escalation(self):
        import pandas as pd
        import numpy as np
        from tests.test_churn_lstm import fixture,small_config
        from src.decision.churn_lstm import fit_lstm
        cfg = small_config(max_epochs=1)
        val = fixture(('V1','V2'),config=cfg)
        yval = pd.Series([0,1],index=val.ids)
        unknown = fixture(('T1','T2'),status='unknown',config=cfg)
        bad = replace(unknown,ready=np.ones(2,bool),reasons=(None,None))
        with self.assertRaises(ValueError):fit_lstm(bad,pd.Series([0,1],index=bad.ids),val,yval,config=cfg)
        commerce = fixture(('T1','T2'),source='commerce',config=cfg)
        bad = replace(commerce,metadata={**commerce.metadata,'source':'simulator','purpose':'experiment'})
        with self.assertRaises(ValueError):fit_lstm(bad,pd.Series([0,1],index=bad.ids),val,yval,config=cfg)

    def test_288_failed_model_save_is_not_visible_and_can_retry(self):
        import pandas as pd
        from tests.test_churn_lstm import fixture, small_config
        from src.decision.churn_lstm import fit_lstm, save_lstm, load_lstm
        cfg = small_config(max_epochs=1)
        train,val = fixture(('T1','T2'),config=cfg),fixture(('V1','V2'),config=cfg)
        model = fit_lstm(train,pd.Series([0,1],index=train.ids),val,pd.Series([0,1],index=val.ids),config=cfg)
        original = Path.write_text
        def fail(path, text, *args, **kw):
            if path.name == 'dl_training_log.json':raise OSError('injected log failure')
            return original(path,text,*args,**kw)
        with tempfile.TemporaryDirectory() as d:
            directory = Path(d)/'model'
            with patch.object(Path,'write_text',fail),self.assertRaises(OSError):save_lstm(model,directory)
            self.assertFalse(directory.exists())
            save_lstm(model,directory)
            self.assertEqual(1,load_lstm(directory).training['epochs_run'])


if __name__ == '__main__':unittest.main()
