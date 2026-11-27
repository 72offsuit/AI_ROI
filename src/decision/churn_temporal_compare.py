"""#218 시간 순서 검증과 t1 재학습. 공개 명부와 관측 근거는 생산자가 제공한다."""
from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
import math
from pathlib import Path
import re

import numpy as np
import pandas as pd

from src.decision import churn, feature_store, model_store
from src.decision.churn_artifacts import atomic_artifact_directory
from src.decision.churn_dl_compare import LABEL_WINDOW, ComparisonProtocol, mix_probabilities, select_ensemble
from src.decision.churn_lstm import fit_lstm, predict_lstm, refit_lstm, save_lstm
from src.decision.churn_sequence import (
    SequenceBatch, SequenceContractError, align_binary_labels, event_time, id_hash, validate_ids,
)
from src.decision.features.sprint_table import TABLE_COLUMNS, model_columns
from src.decision.return_visit import INPUT_METADATA


@dataclass(frozen=True)
class TemporalInputEvidence:
    """인수에서 검증한 공통 실행과 저장 파일의 고정값. 생산자를 인증하지 않는다."""

    protocol_digest: str
    manifest_sha256: str
    run_ids: tuple[str, ...]
    prior_sha256: tuple[str, str]  # Feature, label 순서
    t1_sha256: tuple[str, str]
    prior_sequence_sha256: str
    t1_sequence_sha256: str

    def __post_init__(self):
        object.__setattr__(self, 'run_ids', validate_ids(self.run_ids))
        if not self.run_ids:
            raise SequenceContractError('approved event run lineage is empty')
        for name in ('prior_sha256', 't1_sha256'):
            pair = tuple(getattr(self, name))
            if len(pair) != 2:
                raise SequenceContractError('each cohort requires Feature and label file hashes')
            object.__setattr__(self, name, pair)
        for value in (self.protocol_digest, self.manifest_sha256, *self.prior_sha256, *self.t1_sha256,
                      self.prior_sequence_sha256, self.t1_sequence_sha256):
            if not isinstance(value, str) or re.fullmatch(r'[a-f0-9]{64}', value) is None:
                raise SequenceContractError('approved evidence requires SHA-256 digests')


def _check_store_manifest(root, evidence):
    if evidence is not None:
        digest = hashlib.sha256((Path(root) / feature_store.MANIFEST).read_bytes()).hexdigest()
        if digest != evidence.manifest_sha256:
            raise SequenceContractError('Feature Store manifest hash differs from approved evidence')


def _read_store_cohort(root, names, records, ids, origin, *, pins=None, run_ids=None):
    feature_name, label_name = names
    frames = []
    for i, (name, kind) in enumerate(((feature_name, 'feature'), (label_name, 'label'))):
        record = records.get(name)
        if (record is None or record.get('kind') != kind
                or event_time(record.get('feature_cutoff_time')) != event_time(origin)):
            raise SequenceContractError(f'{name}: Feature Store role or cutoff does not match the split')
        if record.get('file') != f'{name}.parquet' or not Path(name).name == name:
            raise SequenceContractError(f'{name}: invalid Feature Store file role')
        if pins is not None and record.get('file_sha256') != pins[i]:
            raise SequenceContractError(f'{name}: table hash differs from approved evidence')
        frame = feature_store.read_table(root, name)
        if not frame.index.is_unique or not set(ids) <= set(frame.index):
            raise SequenceContractError(f'{name}: missing or duplicate manifest customers')
        frames.append(frame.loc[list(ids)])
    X, outcomes = frames
    if run_ids is not None:
        feature_evidence = X.attrs.get(INPUT_METADATA, {})
        label_evidence = outcomes.attrs.get('outcome_observation', {})
        if (feature_evidence.get('experiment_source_allowed') is not True
                or label_evidence.get('status') != 'ok'
                or outcomes.attrs.get('label_window_complete') is not True
                or outcomes.attrs.get('window_days') != LABEL_WINDOW.days
                or event_time(outcomes.attrs.get('index_time')) != event_time(origin)
                or event_time(label_evidence.get('window_start')) != event_time(origin)
                or event_time(label_evidence.get('window_end')) != event_time(origin) + LABEL_WINDOW):
            raise SequenceContractError('simulator source or complete label window evidence is missing')
        read_evidence = X.attrs.get('event_read_evidence') or {}
        verified_ids = set(validate_ids(read_evidence.get('verified_run_ids', ())))
        if (read_evidence.get('status') != 'ok' or read_evidence.get('run_id') not in verified_ids
                or not verified_ids <= run_ids or label_evidence.get('run_id') not in run_ids):
            raise SequenceContractError('Feature or label runs differ from approved event lineage')
    if 'churn' not in outcomes or not outcomes.columns.is_unique:
        raise SequenceContractError(f'{label_name}: churn label column missing or ambiguous')
    if not X.columns.is_unique or not set(X.columns) <= set(TABLE_COLUMNS):
        raise SequenceContractError(f'{feature_name}: unexpected or duplicate Feature columns')
    columns = model_columns(X)
    if not columns:
        raise SequenceContractError(f'{feature_name}: no model Features')
    y = outcomes['churn']
    labels = align_binary_labels(y, ids, require_two_classes=True)
    return X[columns].astype(float), y, labels


def _check_sequences(batch, ids, origin, *, run_ids=None, sequence_pin=None):
    batch.validate(for_model=True)
    if set(batch.ids) != set(ids) or event_time(batch.metadata['index_time']) != event_time(origin):
        raise SequenceContractError('sequence customers or cutoff do not match the common split')
    if run_ids is not None and not {claim['run_id'] for claim in batch.metadata['coverage']} <= run_ids:
        raise SequenceContractError('sequence runs differ from approved event lineage')
    if sequence_pin is not None and batch.model_input_sha256() != sequence_pin:
        raise SequenceContractError('sequence hash differs from approved evidence')
    return batch if batch.ids == ids else batch.reordered(ids)


def _summary(y, scores, threshold):
    probability = scores.to_numpy() if isinstance(scores, pd.Series) else scores
    return {**churn._metrics(y, probability, threshold), 'lift_at_20': churn.lift_at(y, probability, .2),
            'calibration': churn.calibration(y, probability)['bins']}


@churn._limited_threads
def run_temporal_validation(protocol: ComparisonProtocol, *, feature_root: Path,
                            prior_tables: tuple[str, str], t1_tables: tuple[str, str],
                            prior_sequences: SequenceBatch, t1_sequences: SequenceBatch,
                            directory: Path, seed: int, dl_config=None,
                            evidence: TemporalInputEvidence | None = None):
    """같은 표본으로 ML과 DL을 비교하고 t1 모델을 저장한다. Test 인자는 받지 않는다.

    호출자는 검증된 인수 자료에서 protocol·시퀀스·evidence를 만든다. 이 함수는 실제 읽은 자료와
    승인 지문·계보의 일치를 확인한다. synthetic은 합성 연결 시험에 쓰는 별도 목적이다.
    """
    protocol.validate()
    if protocol.origins is None:
        raise SequenceContractError('common temporal origins required')
    if evidence is None and protocol.purpose != 'synthetic':
        raise SequenceContractError('development comparison requires approved temporal input evidence')
    if evidence is not None and (not isinstance(evidence, TemporalInputEvidence)
                                 or evidence.protocol_digest != protocol.digest):
        raise SequenceContractError('input evidence does not match the common split')
    _check_store_manifest(feature_root, evidence)
    records = feature_store.tables(feature_root)
    runs = set(evidence.run_ids) if evidence is not None else None
    xp, prior_labels, yp = _read_store_cohort(feature_root, prior_tables, records,
                                              protocol.train_ids, protocol.origins.prior,
                                              pins=evidence.prior_sha256 if evidence else None, run_ids=runs)
    x1, t1_labels, y1 = _read_store_cohort(feature_root, t1_tables, records,
                                          protocol.validation_ids, protocol.origins.t1,
                                          pins=evidence.t1_sha256 if evidence else None, run_ids=runs)
    _check_store_manifest(feature_root, evidence)
    feature_version = records[t1_tables[0]].get('feature_version')
    if (not isinstance(feature_version, str) or not feature_version.strip()
            or records[prior_tables[0]].get('feature_version') != feature_version
            or set(xp.columns) != set(x1.columns)):
        raise SequenceContractError('t_prior and t1 must have the same Feature version and columns')
    x1 = x1[list(xp.columns)]
    prior = _check_sequences(prior_sequences, protocol.train_ids, protocol.origins.prior, run_ids=runs,
                             sequence_pin=evidence.prior_sequence_sha256 if evidence else None)
    t1 = _check_sequences(t1_sequences, protocol.validation_ids, protocol.origins.t1, run_ids=runs,
                          sequence_pin=evidence.t1_sequence_sha256 if evidence else None)
    if int(np.bincount(y1.astype(int), minlength=2).min()) < churn.N_SPLITS:
        raise SequenceContractError('t1 needs both classes for the required 5-Fold report')
    missing = {name: reason for name in ('xgboost', 'lightgbm') if (reason := churn.model_unavailable(name))}
    if missing:
        raise SequenceContractError(f'required ML models unavailable: {missing}')

    directory = Path(directory)
    with atomic_artifact_directory(directory) as staging:
        ml_evaluation = churn.evaluate_churn_models(x1, t1_labels, seed, prior=(xp, prior_labels))
        if (ml_evaluation['selection_basis'], ml_evaluation['selection_metric']) != ('temporal_validation', 'roc_auc'):
            raise SequenceContractError('ML selection must use temporal validation ROC-AUC')
        ml_name, params = ml_evaluation['best_proposed'], ml_evaluation['best_params']
        ml_prior = churn.make_model(ml_name, seed, params).fit(xp, yp)
        dl_prior = fit_lstm(prior, prior_labels, t1, t1_labels, config=dl_config)
        ml = pd.Series(churn._score(ml_prior, x1), index=x1.index, name='churn_probability')
        dl = predict_lstm(dl_prior, t1).loc[x1.index]
        selection = select_ensemble(protocol, t1_labels, ml, dl, alpha_grid=dl_prior.config.alpha_grid)
        validated = pd.DataFrame(selection.validation_rows,
                                 columns=['customer_id', 'label', 'ml', 'lstm']).set_index('customer_id')
        predictions = validated[['ml', 'lstm']].copy()
        predictions['ensemble'] = mix_probabilities(predictions['ml'], predictions['lstm'], selection.alpha)
        scores = {name: _summary(validated['label'].to_numpy(), predictions[name], threshold)
                  for name, threshold in zip(predictions.columns, selection.thresholds)}
        candidate_auc = {m['name']: m['temporal_validation']['roc_auc'] for m in ml_evaluation['models']}
        if (not math.isclose(scores['ml']['roc_auc'], candidate_auc[ml_name], rel_tol=0, abs_tol=1e-12)
                or candidate_auc[ml_name] != max(candidate_auc[n] for n in churn.PROPOSED if n in candidate_auc)):
            raise SequenceContractError('persisted ML selection score differs from temporal candidate ranking')
        # 프로젝트 누수 조사 기준은 실제 입력에 적용한다. 합성 양성 제어는 예외다.
        if protocol.purpose != 'synthetic' and max(
                *candidate_auc.values(), *(s['roc_auc'] for s in scores.values())) > .95:
            raise SequenceContractError('Validation ROC-AUC > 0.95; investigate leakage before refit')

        ml_final = churn.ChurnModel(ml_name, churn.make_model(ml_name, seed, params).fit(x1, y1),
                                    selection.thresholds[0], list(x1.columns), 'temporal validation F1', params)
        dl_final = refit_lstm(t1, t1_labels, dl_prior)
        model_root = staging / 'models'
        run = {'protocol_digest': protocol.digest, 'dataset_version': protocol.dataset_version,
               'feature_version': feature_version, 'origin': protocol.origins.t1,
               'fit_ids_sha256': id_hash(protocol.validation_ids),
               'fit_order_sha256': id_hash(protocol.validation_ids, ordered=True),
               'input_evidence': asdict(evidence) if evidence is not None else None,
               'sequence_sha256': {'prior': dl_prior.training['train_sequence_sha256'],
                                   't1': dl_final.training['train_sequence_sha256']}}
        ml_meta = model_store.save_model(model_root, 'churn', ml_final, model_version='218-temporal-v1',
                                          dataset_version=protocol.dataset_version, feature_version=feature_version,
                                          cv_score=next(m['cv'] for m in ml_evaluation['models'] if m['name'] == ml_name),
                                          score_notes={'test_score': 'GATE 3 이후 평가'}, extra=run)
        model_store.write_manifest(model_root, {'churn': ml_meta}, run)
        save_lstm(dl_final, model_root / 'lstm')

        results = staging / 'results'
        results.mkdir()
        predictions.loc[x1.index].to_csv(results / 'validation_predictions.csv')
        (results / 'lstm_selection_log.json').write_text(
            json.dumps(dl_prior.training, ensure_ascii=False, allow_nan=False, indent=2), encoding='utf-8')
        report = {'purpose': protocol.purpose, 'protocol': asdict(protocol), **run,
                  'selection_basis': 'temporal_validation', 'selection_metric': 'roc_auc',
                  'validation_fit_origin': protocol.origins.prior, 'validation_score_origin': protocol.origins.t1,
                  'threshold_source': 'prior-fit predictions at t1',
                  'ensemble_candidate_loss': '1 - roc_auc', 'ml_name': ml_name, 'ml_params': params,
                  'ml_seed': seed, 'lstm_selected_epoch': dl_prior.training['best_epoch'],
                  'prior_order_sha256': id_hash(protocol.train_ids, ordered=True),
                  'validation_metrics': scores, 'selection': asdict(selection),
                  'ml_candidate_auc': candidate_auc,
                  'ml_grid': {m['name']: m['tuning'] for m in ml_evaluation['models'] if 'tuning' in m},
                  'ml_cv': {m['name']: m['cv'] for m in ml_evaluation['models']},
                  'feature_table_sha256': {name: records[name]['file_sha256'] for name in (*prior_tables, *t1_tables)},
                  'test_status': 'not_run', 'final_holdout_status': 'not_run',
                  'model_manifests': {path.relative_to(staging).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
                                      for path in (model_root / 'manifest.json', model_root / 'lstm/manifest.json')}}
        (results / 'validation_comparison.json').write_text(
            json.dumps(report, ensure_ascii=False, allow_nan=False, indent=2), encoding='utf-8')
    return report
