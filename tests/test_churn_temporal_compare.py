"""#218의 공통 고객·기준일 비교와 Feature Store 인수 반례."""
from dataclasses import replace
import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

BASE = all(importlib.util.find_spec(name) for name in ('numpy', 'pandas', 'sklearn', 'yaml'))
FIT = BASE and all(importlib.util.find_spec(name) for name in ('torch', 'pyarrow', 'xgboost', 'lightgbm'))
TORCH = BASE and importlib.util.find_spec('torch') is not None
PRIOR = '2025-09-28T00:00:00+09:00'
T1 = '2025-11-09T00:00:00+09:00'
T2 = '2025-12-21T00:00:00+09:00'


def protocol(ids, *, purpose='synthetic'):
    from src.decision.churn_dl_compare import ComparisonProtocol, TemporalOrigins

    return ComparisonProtocol('temporal-example', 'fixture-v1', 'simulator', purpose, 'fixture',
                              ids, ids[::-1], ids, origins=TemporalOrigins(PRIOR, T1, T2))


def with_coverage_run(batch, run_id):
    from src.decision.churn_sequence import thaw_json

    metadata = thaw_json(batch.metadata)
    for claim in metadata['coverage']:
        claim['run_id'] = run_id
    return replace(batch, metadata=metadata)


@unittest.skipUnless(BASE, 'BLOCKED: numpy/pandas/sklearn/PyYAML required')
class TemporalComparisonTests(unittest.TestCase):
    def test_same_customers_recur_only_at_distinct_valid_origins(self):
        from src.decision.churn_dl_compare import TemporalOrigins

        p = protocol(('C1', 'C2'))
        same_times = TemporalOrigins('2025-09-27T15:00:00Z', T1, T2)
        self.assertEqual(p.digest, replace(p, origins=same_times).digest)
        with self.assertRaisesRegex(ValueError, 'unique'):
            replace(p, validation_ids=('C1', 'C1'))
        for times in ((PRIOR, '2025-09-27T15:00:00Z', T2), (PRIOR, T1, '2025-12-20T00:00:00+09:00')):
            with self.subTest(times=times), self.assertRaisesRegex(ValueError, 'label end'):
                TemporalOrigins(*times)

    def test_temporal_alpha_uses_auc_and_legacy_test_rejects_both_purposes(self):
        import pandas as pd
        from src.decision.churn_dl_compare import select_ensemble, evaluate_common_test

        ids = ('A', 'B', 'C', 'D')
        y = pd.Series([0, 0, 1, 1], index=ids)
        ml = pd.Series([.1, .6, .5, .9], index=ids)
        dl = pd.Series([.65, .66, .68, .69], index=ids)
        for purpose in ('synthetic', 'development'):
            with self.subTest(purpose=purpose), tempfile.TemporaryDirectory() as directory:
                p = protocol(ids, purpose=purpose)
                selection = select_ensemble(p, y, ml, dl, alpha_grid=(0., 1.))
                self.assertEqual(1., selection.alpha)
                self.assertEqual(((0., .25), (1., 0.)), selection.candidates)
                with self.assertRaisesRegex(ValueError, 'GATE 3'):
                    evaluate_common_test(p, selection, object(), object(), object(), directory=Path(directory) / 'test')
                self.assertEqual([], list(Path(directory).iterdir()))

    def test_float32_lstm_at_ensemble_threshold_keeps_frozen_f1(self):
        import pandas as pd
        from sklearn.metrics import f1_score
        from src.decision.churn_dl_compare import mix_probabilities, select_ensemble

        ids = tuple('ABCDEFGH')
        y = pd.Series([0, 1] * 4, index=ids)
        ml = pd.Series([.11174383872724217, .09431979101630333, .22272508923539602, .22012252382760278,
                        .362376783795935, .4067327043882867, .5412598320907659, .1944159307095046], index=ids)
        dl = pd.Series([.5573761463165283, .6717490553855896, .21966864168643951, .19347764551639557,
                        .28483662009239197, .19420646131038666, .5170237421989441, .32382121682167053],
                       index=ids, dtype='float32')
        selection = select_ensemble(protocol(ids), y, ml, dl)
        self.assertEqual(.2, selection.alpha)
        saved = mix_probabilities(ml, dl, selection.alpha)
        self.assertEqual(selection.thresholds[2], saved[1])
        self.assertAlmostEqual(8 / 11, f1_score(y, saved >= selection.thresholds[2]))

    @unittest.skipUnless(TORCH, 'BLOCKED: torch required')
    def test_refit_binds_tokens_and_coverage_but_normalizes_equivalent_origin(self):
        import pandas as pd
        from src.decision.churn_lstm import fit_lstm, refit_lstm
        from src.decision.churn_sequence import thaw_json
        from tests.test_churn_lstm import fixture, small_config

        ids = ('C1', 'C2', 'C3', 'C4')
        config = small_config(max_epochs=1)
        y = pd.Series([0, 1, 0, 1], index=ids)
        prior = fixture(ids, config=config, index_time=PRIOR)
        t1 = fixture(ids, config=config, index_time=T1)
        chosen = fit_lstm(prior, y, t1, y, config=config)
        tokens = t1.tokens.copy()
        tokens[0, 0] = 2 if tokens[0, 0] != 2 else 3
        for alternative in (replace(t1, tokens=tokens), with_coverage_run(t1, 'other-chain')):
            with self.assertRaisesRegex(ValueError, 'selection evidence'):
                refit_lstm(alternative, y, chosen)
        metadata = thaw_json(t1.metadata)
        metadata['index_time'] = pd.Timestamp(T1).tz_convert('UTC').isoformat()
        equivalent = replace(t1, metadata=metadata).reordered(ids[::-1])
        refitted = refit_lstm(equivalent, y, chosen)
        self.assertEqual(chosen.training['validation_sequence_sha256'], refitted.training['train_sequence_sha256'])

    @unittest.skipUnless(FIT, 'BLOCKED: torch/pyarrow/xgboost/lightgbm required')
    def test_feature_store_to_validation_predictions_and_t1_artifacts(self):
        import numpy as np
        import pandas as pd
        from src.decision import churn, feature_store, model_store
        from src.decision.churn_dl_compare import mix_probabilities
        from src.decision.churn_lstm import load_lstm
        from src.decision.churn_temporal_compare import TemporalInputEvidence, run_temporal_validation
        from src.decision.observation_contract import outcome_observation_status
        from src.decision.return_visit import INPUT_METADATA, check_input
        from tests.test_churn_lstm import fixture, small_config

        missing = [name for name in ('xgboost', 'lightgbm') if churn.model_unavailable(name)]
        if missing:
            self.skipTest(f'BLOCKED: native model loading unavailable: {missing}')
        rng = np.random.default_rng(218)
        ids = tuple(f'C{i:02}' for i in range(40))
        p = protocol(ids, purpose='development')
        initial = pd.Index(ids, name='customer_id')
        config = small_config(max_epochs=3, patience=2)
        prior_seq = with_coverage_run(fixture(ids, config=config, index_time=PRIOR), 'parent-run')
        t1_seq = with_coverage_run(fixture(ids, config=config, index_time=T1), 'parent-run')
        source_proof = check_input(pd.DataFrame({'simulator_version': ['fixture']}), 'experiment')
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / 'tables'
            labels = {}
            for name, origin, label_run in (('prior', PRIOR, 'parent-run'), ('t1', T1, 'child-run')):
                frame = pd.DataFrame({'recency': rng.integers(1, 100, len(ids)).astype(float),
                                      'frequency_90d': rng.integers(0, 10, len(ids)).astype(float)}, index=initial)
                y = rng.permutation(np.tile([0, 1], len(ids) // 2))
                labels[name] = pd.DataFrame({'churn': y}, index=initial).iloc[::-1]
                frame.attrs[INPUT_METADATA] = source_proof
                frame.attrs['event_read_evidence'] = {'status': 'ok', 'run_id': 'parent-run',
                                                      'verified_run_ids': ['parent-run']}
                end = pd.Timestamp(origin) + pd.Timedelta(days=42)
                observation = outcome_observation_status(origin, 42, dict(start=origin, end=end, run_id=label_run,
                    rejected=0, read_complete=True, purchase_generated=True))
                labels[name].attrs.update(index_time=origin, window_days=42,
                                          label_window_complete=True, outcome_observation=observation)
                feature_store.write_table(root, f'features_{name}', frame, feature_version='fixture', cutoff_time=origin)
                feature_store.write_table(root, f'labels_{name}', labels[name], feature_version=None,
                                          cutoff_time=origin, kind='label')
            manifest_file = root / 'manifest.json'
            records = feature_store.tables(root)
            prior_names, t1_names = ('features_prior', 'labels_prior'), ('features_t1', 'labels_t1')
            evidence = TemporalInputEvidence(p.digest, hashlib.sha256(manifest_file.read_bytes()).hexdigest(),
                ('parent-run', 'child-run'), tuple(records[n]['file_sha256'] for n in prior_names),
                tuple(records[n]['file_sha256'] for n in t1_names),
                prior_seq.model_input_sha256(), t1_seq.model_input_sha256())
            out = Path(directory) / 'comparison'
            kwargs = dict(feature_root=root, prior_tables=prior_names, t1_tables=t1_names, prior_sequences=prior_seq,
                          t1_sequences=t1_seq, directory=out, seed=42, dl_config=config, evidence=evidence)

            same_run_tokens = t1_seq.tokens.copy()
            same_run_tokens[0, 0] = 2 if same_run_tokens[0, 0] != 2 else 3
            bad_inputs = (
                ('requires approved', {'evidence': None}),
                ('common split', {'evidence': replace(evidence, protocol_digest='0' * 64)}),
                ('manifest hash', {'evidence': replace(evidence, manifest_sha256='0' * 64)}),
                ('table hash', {'evidence': replace(evidence, t1_sha256=evidence.t1_sha256[::-1])}),
                ('Feature or label runs', {'evidence': replace(evidence, run_ids=('parent-run',))}),
                ('sequence runs', {'t1_sequences': with_coverage_run(t1_seq, 'another-experiment')}),
                ('sequence hash', {'t1_sequences': replace(t1_seq, tokens=same_run_tokens)}),
                ('sequence hash', {'evidence': replace(evidence, prior_sequence_sha256=evidence.t1_sequence_sha256)}),
                ('cutoff', {'prior_tables': t1_names}),
                ('sequence customers or cutoff', {'prior_sequences': t1_seq}),
            )
            with patch.object(churn, 'evaluate_churn_models', side_effect=AssertionError('entered fit')) as fit:
                for reason, delta in bad_inputs:
                    with self.subTest(reason=reason), self.assertRaisesRegex(ValueError, reason):
                        run_temporal_validation(p, **{**kwargs, **delta})
                fit.assert_not_called()
            self.assertFalse(out.exists())

            with patch.object(feature_store, 'read_table', wraps=feature_store.read_table) as read:
                report = run_temporal_validation(p, **kwargs)
            self.assertEqual(['features_prior', 'labels_prior', 'features_t1', 'labels_t1'],
                             [call.args[1] for call in read.call_args_list])
            self.assertEqual('temporal_validation', report['selection_basis'])
            self.assertEqual('roc_auc', report['selection_metric'])
            self.assertEqual('not_run', report['test_status'])
            self.assertEqual(report['ml_candidate_auc'][report['ml_name']], report['validation_metrics']['ml']['roc_auc'])
            self.assertEqual(5, report['ml_cv'][report['ml_name']]['roc_auc']['n_folds'])
            result = pd.read_csv(out / 'results/validation_predictions.csv', float_precision='round_trip').set_index('customer_id')
            rows = pd.DataFrame(report['selection']['validation_rows'],
                                columns=['customer_id', 'label', 'ml', 'lstm']).set_index('customer_id')
            np.testing.assert_array_equal(rows['label'], labels['t1'].loc[rows.index, 'churn'])
            np.testing.assert_array_equal(result.loc[rows.index, 'ensemble'],
                mix_probabilities(rows['ml'], rows['lstm'], report['selection']['alpha']))
            self.assertEqual(PRIOR, report['validation_fit_origin'])
            self.assertEqual(T1, report['validation_score_origin'])
            self.assertEqual(evidence.manifest_sha256, report['input_evidence']['manifest_sha256'])
            stored, manifest = model_store.load_models(out / 'models', expected_feature_version='fixture')
            self.assertEqual(T1, manifest['run']['origin'])
            self.assertEqual(report['ml_name'], stored['churn'][0].name)
            fitted = load_lstm(out / 'models/lstm')
            self.assertEqual(T1, fitted.training['train_metadata']['index_time'])
            self.assertEqual([], fitted.training['validation_ids'])
            self.assertEqual(report['lstm_selected_epoch'], fitted.training['epochs_run'])
            chosen = json.loads((out / 'results/lstm_selection_log.json').read_text())
            self.assertEqual(PRIOR, chosen['train_metadata']['index_time'])
            self.assertEqual(T1, chosen['validation_metadata']['index_time'])
            self.assertEqual(max(r['validation_roc_auc'] for r in chosen['history']),
                             report['validation_metrics']['lstm']['roc_auc'])

            self.assertEqual(fitted.training['train_sequence_sha256'], report['sequence_sha256']['t1'])
            self.assertEqual(evidence.prior_sequence_sha256, report['sequence_sha256']['prior'])
            self.assertEqual(evidence.t1_sequence_sha256, report['sequence_sha256']['t1'])
