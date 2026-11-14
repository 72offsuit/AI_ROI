"""#218 합성 계약·학습·저장 반례. 실제 시뮬레이터/정답지를 사용하지 않는다."""
from __future__ import annotations

from dataclasses import replace
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

BASE = all(importlib.util.find_spec(x) is not None for x in ('numpy', 'pandas', 'yaml'))
TORCH = importlib.util.find_spec('torch') is not None
REPO = Path(__file__).resolve().parents[1]


def small_config(**changes):
    from src.decision.churn_sequence import load_dl_config
    cfg = replace(load_dl_config(), lookback_days=2, max_events=4, embedding_dim=4,
                  hidden_dim=4, dropout=0.0, max_epochs=5, patience=2, batch_size=4,
                  learning_rate=0.01, cpu_threads=1)
    return replace(cfg, **changes)


def fixture(ids, *, status='complete', source='simulator', config=None, records=None):
    import pandas as pd
    from src.decision.churn_sequence import SequenceCoverage, build_event_sequences
    config = small_config() if config is None else config
    t0 = pd.Timestamp('2026-10-22T00:00:00+09:00')
    if records is None:
        records = [{'customer_id': cid, 'event_id': f'{cid}-{j}',
                    'timestamp': t0 - pd.Timedelta(hours=4-j),
                    'event_type': 'purchase' if j == 1 else 'product_view',
                    'simulator_version': 'public-contract-fixture' if source == 'simulator' else None,
                    'random_seed': 7 if source == 'simulator' else None}
                   for i, cid in enumerate(ids) for j in range(1 + i % 3)]
    events = pd.DataFrame.from_records(records, columns=['customer_id', 'event_id', 'timestamp',
        'event_type', 'simulator_version', 'random_seed'])
    evidence = {cid: SequenceCoverage(t0 - pd.Timedelta(days=config.lookback_days), t0,
        status, source, 'fixture-run', 'tests:test_churn_lstm.fixture') for cid in ids}
    return build_event_sequences(events, ids, t0, coverage=evidence, config=config,
                                 purpose='experiment' if source == 'simulator' else 'observation')


@unittest.skipUnless(BASE, 'BLOCKED: numpy/pandas/PyYAML required')
class TestChurnSequenceContract(unittest.TestCase):
    def test_config_load_and_unknown_key(self):
        from src.decision.churn_sequence import load_dl_config, DEFAULT_CONFIG
        self.assertEqual(128, load_dl_config().max_events)
        with tempfile.TemporaryDirectory() as d:
            p = Path(d)/'bad.yaml'
            p.write_text(DEFAULT_CONFIG.read_text() + '\nunknown: 1\n')
            with self.assertRaises(ValueError):load_dl_config(p)

    def test_config_rejects_invalid_ranges_and_types(self):
        for changes in ({'max_events': True}, {'max_epochs': 0}, {'learning_rate': float('nan')},
                        {'dropout': 1.}, {'patience': -1}, {'seed': -1}, {'cpu_threads': 0},
                        {'alpha_grid': (0., .5)}, {'alpha_grid': (0., 0., 1.)}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):small_config(**changes)

    def test_duplicate_yaml_keys_refused(self):
        from src.decision.churn_sequence import load_dl_config,DEFAULT_CONFIG
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'bad.yaml'
            p.write_text(DEFAULT_CONFIG.read_text().replace('  max_events: 128','  max_events: 128\n  max_events: 64'))
            with self.assertRaises(ValueError):load_dl_config(p)

    def test_customer_order_and_padding_are_explicit(self):
        from src.decision.churn_sequence import id_hash
        batch = fixture(('C2','C1'))
        self.assertEqual(('C2','C1'),batch.ids)
        self.assertEqual(id_hash(batch.ids,ordered=True),batch.metadata['ids_order_sha256'])
        self.assertEqual([1,2],batch.lengths.tolist())
        batch.validate(for_model=True)

    def test_duplicate_and_missing_customer_ids_refused(self):
        for ids in (('C1','C1'), ('C1',''), ('C1',None)):
            with self.subTest(ids=ids), self.assertRaises(ValueError):fixture(ids)

    def test_complete_zero_events_has_different_token_than_padding(self):
        from src.decision.churn_sequence import NO_HISTORY
        b=fixture(('C1',),records=[])
        self.assertEqual(NO_HISTORY,b.tokens[0,0])
        self.assertEqual(1,b.lengths[0])
        self.assertTrue(b.ready[0])
        b.validate(for_model=True)

    def test_unknown_zero_events_is_not_known_no_history(self):
        b=fixture(('C1',),records=[],status='unknown')
        self.assertEqual(0,b.lengths[0])
        self.assertFalse(b.ready[0])
        self.assertEqual('OBSERVATION_UNCONFIRMED',b.reasons[0])
        with self.assertRaises(ValueError):b.validate(for_model=True)

    def test_incomplete_input_is_retained_but_not_trainable(self):
        b=fixture(('C1','C2'),status='incomplete')
        self.assertEqual(2,len(b.ids))
        with self.assertRaises(ValueError):b.validate(for_model=True)

    def test_naive_and_submicrosecond_event_time_refused(self):
        from src.decision.churn_sequence import event_time
        for value in ('2026-10-21T20:00:00', '2026-10-21T20:00:00.1234567+09:00',None):
            with self.subTest(value=value), self.assertRaises(ValueError):event_time(value)

    def test_boundary_timezone_sort_and_truncation(self):
        import pandas as pd
        from src.decision.churn_sequence import SequenceCoverage,build_event_sequences,TOKEN_VOCAB
        t0=pd.Timestamp('2026-10-22T00:00:00+09:00')
        config=small_config(max_events=2)
        rows=[('before','2026-10-19T23:59:59.999999+09:00','search'),
              ('start','2026-10-20T00:00:00+09:00','search'),
              ('middle','2026-10-21T10:00:00+09:00','product_view'),
              ('last','2026-10-21T14:59:59.999999Z','purchase'),
              ('at','2026-10-22T00:00:00+09:00','coupon_use')]
        events=pd.DataFrame([dict(customer_id='C1',event_id=e,timestamp=t,event_type=k,
            simulator_version='fixture',random_seed=0) for e,t,k in rows[::-1]])
        cov={'C1':SequenceCoverage('2026-10-20T00:00:00+09:00',t0,'complete','simulator','fixture','fixture:coverage')}
        b=build_event_sequences(events,('C1',),t0,coverage=cov,config=config)
        self.assertEqual([TOKEN_VOCAB['product_view'],TOKEN_VOCAB['purchase']],b.tokens[0].tolist())
        self.assertEqual(1,b.metadata['events_truncated'])

    def test_derived_states_and_assignment_fields_do_not_become_tokens(self):
        from src.decision.churn_sequence import NO_HISTORY
        b=fixture(('C1',),records=[dict(customer_id='C1',event_id='derived',
            timestamp='2026-10-21T12:00:00+09:00',event_type='churn',simulator_version='fixture',random_seed=0)])
        self.assertEqual(NO_HISTORY,b.tokens[0,0])
        self.assertEqual(1,b.metadata['derived_events_excluded'])

    def test_assignment_persona_and_post_t0_columns_are_not_embedded(self):
        import pandas as pd
        import numpy as np
        from src.decision.churn_sequence import SequenceCoverage,build_event_sequences
        t0=pd.Timestamp('2026-10-22T00:00:00+09:00')
        frame=pd.DataFrame([dict(customer_id='C1',event_id='E1',timestamp=t0-pd.Timedelta(hours=1),
            event_type='search',simulator_version='f',random_seed=0)])
        cov={'C1':SequenceCoverage(t0-pd.Timedelta(days=2),t0,'complete','simulator','f','fixture')}
        baseline=build_event_sequences(frame,('C1',),t0,coverage=cov,config=small_config())
        altered=build_event_sequences(frame.assign(persona='not-an-input',treatment_group='T4',
            experiment_id='RCT',spend_post_t0=100000),('C1',),t0,coverage=cov,config=small_config())
        np.testing.assert_array_equal(baseline.tokens,altered.tokens)
        self.assertEqual(baseline.metadata,altered.metadata)

    def test_short_coverage_and_missing_customer_evidence_not_accepted(self):
        import pandas as pd
        from src.decision.churn_sequence import SequenceCoverage,build_event_sequences
        t0=pd.Timestamp('2026-10-22T00:00:00+09:00')
        empty=pd.DataFrame(columns=['customer_id','event_id','event_type','timestamp'])
        cov={'C1':SequenceCoverage(t0-pd.Timedelta(days=1),t0,'complete','simulator','f','fixture')}
        b=build_event_sequences(empty,('C1',),t0,coverage=cov,config=small_config())
        self.assertFalse(b.ready[0])
        self.assertEqual(0,b.lengths[0])
        with self.assertRaises(ValueError):build_event_sequences(empty,('C1','C2'),t0,coverage=cov,config=small_config())

    def test_duplicate_event_ids_and_unknown_events_refused(self):
        base=dict(customer_id='C1',event_id='E1',timestamp='2026-10-21T12:00:00+09:00',
                  event_type='search',simulator_version='fixture',random_seed=7)
        for rows in ([base,base], [{**base,'event_type':'future_label'}], [{**base,'event_id':None}]):
            with self.subTest(rows=rows), self.assertRaises(ValueError):fixture(('C1',),records=rows)

    def test_mixed_and_wrong_source_refused_and_original_unchanged(self):
        import pandas as pd
        from src.decision.churn_sequence import SequenceCoverage,build_event_sequences
        t0=pd.Timestamp('2026-10-22T00:00:00+09:00')
        rows=[dict(customer_id='C1',event_id='E1',timestamp=t0-pd.Timedelta(hours=1),event_type='search',simulator_version='f'),
              dict(customer_id='C1',event_id='E2',timestamp=t0-pd.Timedelta(hours=2),event_type='search',simulator_version=None)]
        frame=pd.DataFrame(rows); old=frame.copy(deep=True)
        cov={'C1':SequenceCoverage(t0-pd.Timedelta(days=2),t0,'complete','simulator','f','f:1')}
        with self.assertRaises(ValueError):build_event_sequences(frame,('C1',),t0,coverage=cov,config=small_config())
        pd.testing.assert_frame_equal(frame,old)
        with self.assertRaises(ValueError):build_event_sequences(frame.iloc[1:],('C1',),t0,coverage=cov,config=small_config())

    def test_commerce_observation_cannot_enter_model(self):
        batch=fixture(('C1',),source='commerce')
        self.assertEqual('commerce',batch.metadata['source'])
        with self.assertRaises(ValueError):batch.validate(for_model=True)

    def test_coverage_and_padding_contradictions_refused(self):
        import numpy as np
        batch=fixture(('C1',))
        bad=batch.tokens.copy();bad[0,-1]=2
        with self.assertRaises(ValueError):replace(batch,tokens=bad).validate()
        with self.assertRaises(ValueError):replace(batch,lengths=np.array([99],dtype=np.int64)).validate()
        with self.assertRaises(ValueError):replace(batch,metadata={**batch.metadata,'ids_order_sha256':'wrong'}).validate()

    def test_missing_or_nonbinary_labels_are_not_zero(self):
        import pandas as pd
        from src.decision.churn_sequence import align_binary_labels
        for values in ([0,None],[0,pd.NA],[0,float('nan')],[0,2]):
            with self.subTest(values=values),self.assertRaises(ValueError):
                align_binary_labels(pd.Series(values,index=['C1','C2']),('C1','C2'))

    def test_empty_population_preserved_not_trainable(self):
        b=fixture((),records=[])
        self.assertEqual((0,4),b.tokens.shape)
        with self.assertRaises(ValueError):b.validate(for_model=True)


@unittest.skipUnless(BASE and TORCH, 'BLOCKED: numpy/pandas/PyYAML and optional torch required')
class TestChurnLSTMTraining(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import pandas as pd
        from src.decision.churn_lstm import fit_lstm
        cls.config=small_config(max_epochs=6,min_delta=10.0,patience=2)
        cls.train=fixture(tuple(f'T{i}' for i in range(8)),config=cls.config)
        cls.val=fixture(tuple(f'V{i}' for i in range(4)),config=cls.config)
        cls.ytrain=pd.Series([0,1]*4,index=cls.train.ids)
        cls.yval=pd.Series([0,1]*2,index=cls.val.ids)
        cls.model=fit_lstm(cls.train,cls.ytrain,cls.val,cls.yval,config=cls.config)

    def test_early_stopping_and_best_weights_are_really_restored(self):
        info=self.model.training
        self.assertTrue(info['stopped_early'])
        self.assertEqual(3,info['epochs_run'])
        self.assertEqual(1,info['best_epoch'])
        self.assertAlmostEqual(info['best_validation_loss'],info['restored_validation_loss'],places=7)
        self.assertEqual(0,info['test_accesses_during_fit'])
        self.assertEqual(3,len(info['history']))

    def test_stopping_controller_improvement_resets_patience(self):
        from src.decision.churn_lstm import EarlyStop
        s=EarlyStop(2,.01)
        self.assertEqual((True,False),s.update(1.,1))
        self.assertEqual((False,False),s.update(.999,2))
        self.assertEqual((True,False),s.update(.8,3))
        self.assertEqual((False,False),s.update(.81,4))
        self.assertEqual((False,True),s.update(.82,5))
        with self.assertRaises(ValueError):s.update(float('nan'),6)

    def test_seed_repeat_and_global_rng_threads_preserved(self):
        import torch
        from src.decision.churn_lstm import fit_lstm,predict_lstm
        torch.manual_seed(123)
        before=torch.random.get_rng_state().clone();threads=torch.get_num_threads()
        fitted=fit_lstm(self.train,self.ytrain,self.val,self.yval,config=self.config)
        self.assertTrue(torch.equal(before,torch.random.get_rng_state()))
        self.assertEqual(threads,torch.get_num_threads())
        self.assertEqual(self.model.training['history'],fitted.training['history'])
        for key,value in self.model.network.state_dict().items():
            self.assertTrue(torch.equal(value,fitted.network.state_dict()[key]))

    def test_overlap_one_class_and_unknown_input_refused(self):
        from src.decision.churn_lstm import fit_lstm
        with self.assertRaises(ValueError):fit_lstm(self.train,self.ytrain,self.train,self.ytrain,config=self.config)
        with self.assertRaises(ValueError):fit_lstm(self.train,self.ytrain*0,self.val,self.yval,config=self.config)
        bad=replace(self.val,ready=self.val.ready*False,reasons=tuple('UNKNOWN' for _ in self.val.ids))
        with self.assertRaises(ValueError):fit_lstm(self.train,self.ytrain,bad,self.yval,config=self.config)

    def test_predict_customer_order_and_finite_probabilities(self):
        import numpy as np
        from src.decision.churn_lstm import predict_lstm
        scores=predict_lstm(self.model,self.val)
        rev=self.val.reordered(self.val.ids[::-1])
        np.testing.assert_allclose(scores.loc[list(rev.ids)],predict_lstm(self.model,rev),atol=1e-7)
        self.assertTrue(scores.between(0,1).all())

    def test_save_load_and_overwrite_refusal(self):
        import numpy as np
        from src.decision.churn_lstm import save_lstm,load_lstm,predict_lstm
        with tempfile.TemporaryDirectory() as d:
            folder=Path(d)/'model'
            manifest=save_lstm(self.model,folder)
            loaded=load_lstm(folder)
            np.testing.assert_array_equal(predict_lstm(self.model,self.val),predict_lstm(loaded,self.val))
            self.assertTrue((folder/'dl_training_log.json').is_file())
            self.assertIn('churn_lstm.pt',manifest['files'])
            with self.assertRaises(FileExistsError):save_lstm(self.model,folder)

    def test_checkpoint_tampering_refused(self):
        from src.decision.churn_lstm import save_lstm,load_lstm
        for name in ('churn_lstm.pt','dl_training_log.json','dl_training_curve.csv'):
            with self.subTest(name=name), tempfile.TemporaryDirectory() as d:
                folder=Path(d)/'model';save_lstm(self.model,folder)
                p=folder/name;p.write_bytes(p.read_bytes()+b' ')
                with self.assertRaises(ValueError):load_lstm(folder)

    def test_load_predictions_in_separate_process_without_fit(self):
        import numpy as np
        from src.decision.churn_lstm import save_lstm,predict_lstm
        with tempfile.TemporaryDirectory() as d:
            folder=Path(d)/'model';save_lstm(self.model,folder)
            script='''
import json,sys
from tests.test_churn_lstm import small_config,fixture
from src.decision.churn_lstm import load_lstm,predict_lstm
model=load_lstm(sys.argv[1])
b=fixture(tuple('V'+str(i) for i in range(4)),config=model.config)
print(json.dumps(predict_lstm(model,b).tolist()))
'''
            cp=subprocess.run([sys.executable,'-B','-c',script,str(folder)],cwd=REPO,text=True,capture_output=True,check=True)
            np.testing.assert_array_equal(predict_lstm(self.model,self.val),json.loads(cp.stdout))

    def test_optional_torch_is_not_imported_by_modules(self):
        script='''
import importlib.abc,sys
class Guard(importlib.abc.MetaPathFinder):
 def find_spec(self,name,*a,**k):
  if name=='torch' or name.startswith('torch.'):
   raise AssertionError('eager torch import')
sys.meta_path.insert(0,Guard())
import src.decision.churn_sequence, src.decision.churn_lstm, src.decision.churn_dl_compare
assert 'torch' not in sys.modules
'''
        subprocess.run([sys.executable,'-B','-c',script],cwd=REPO,capture_output=True,text=True,check=True)


if __name__=='__main__':unittest.main()
