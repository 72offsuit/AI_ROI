"""#218: 공개 사건 토큰과 고객별 관측 상태. torch 없이 import할 수 있다.

관측 근거는 호출자가 공개 검증기 결과에서 인수한다. 이 모듈이 evidence_ref의
진실성을 인증하지 않는다. 부분 관측 고객을 조용히 삭제하거나 0활동으로 만들지 않는다.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import math
from pathlib import Path
import re
from collections.abc import Mapping
from types import MappingProxyType

import numpy as np
import pandas as pd

from src.decision.observation_contract import normalize_index_time
from src.decision.return_visit import check_input
from src.measurement.schema import EventType, FEATURE_FORBIDDEN_EVENT_TYPES
from src.measurement.timeparse import parse_datetime

PAD = 0
NO_HISTORY = 1
TOKEN_VOCAB = {name: i + 2 for i, name in enumerate(sorted(e.value for e in EventType))}
DEFAULT_CONFIG = Path(__file__).resolve().parents[2] / 'config' / 'decision_dl.yaml'


class SequenceContractError(ValueError):
    """선택적 DL 입력 또는 저장 계약 위반."""


def id_hash(ids, *, ordered=False):
    values = list(ids)
    return hashlib.sha256(json.dumps(values if ordered else sorted(values),
        ensure_ascii=False, separators=(',', ':')).encode()).hexdigest()


def validate_ids(ids):
    if isinstance(ids, (str, bytes)):
        raise SequenceContractError('customer IDs must be a collection, not a scalar string')
    values = tuple(ids)
    if any(not isinstance(x, str) or not x or x != x.strip() for x in values) or len(set(values)) != len(values):
        raise SequenceContractError('customer IDs must be unique non-empty strings without surrounding whitespace')
    return values


def bound_value_hash(ids, values):
    """고객과 값을 결합한 순서 불변 지문. 제공자 인증이나 학습 사실의 증명은 아니다."""
    ids = validate_ids(ids)
    values = tuple(values)
    if len(ids) != len(values):
        raise SequenceContractError('ID/value lengths differ')
    rows = sorted((cid, 0.0 if float(v) == 0 else float(v)) for cid, v in zip(ids, values))
    return hashlib.sha256(json.dumps(rows, ensure_ascii=False, allow_nan=False,
                                    separators=(',', ':')).encode()).hexdigest()


def freeze_json(value):
    if isinstance(value, Mapping):
        return MappingProxyType({k: freeze_json(v) for k, v in value.items()})
    if isinstance(value, (list, tuple)):
        return tuple(freeze_json(v) for v in value)
    if value is None or isinstance(value, (str, bool, int, float)):
        return value
    raise SequenceContractError('metadata must contain JSON-compatible values')


def thaw_json(value):
    if isinstance(value, Mapping):
        return {k: thaw_json(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [thaw_json(v) for v in value]
    return value


def event_time(value):
    # 공개 계약의 파서를 사용하며 pandas Timestamp의 ns를 몰래 절삭하지 않는다.
    if pd.isna(value):
        raise SequenceContractError('timestamp is missing')
    if isinstance(value, str):
        fraction = re.search(r'\.(\d+)', value)
        if fraction and len(fraction[1]) > 6:
            raise SequenceContractError('sub-microsecond timestamps require an explicit precision contract')
        stamp = pd.Timestamp(parse_datetime(value))
    else:
        stamp = pd.Timestamp(value)
    if stamp.tzinfo is None or stamp.nanosecond:
        raise SequenceContractError('event timestamp requires timezone and supported precision')
    return stamp.tz_convert('Asia/Seoul')


@dataclass(frozen=True)
class DLConfig:
    lookback_days: int
    max_events: int
    embedding_dim: int
    hidden_dim: int
    dropout: float
    max_epochs: int
    patience: int
    min_delta: float
    batch_size: int
    learning_rate: float
    seed: int
    cpu_threads: int
    alpha_grid: tuple[float, ...]

    def __post_init__(self):
        for name in ('lookback_days', 'max_events', 'embedding_dim', 'hidden_dim',
                     'max_epochs', 'patience', 'batch_size', 'cpu_threads'):
            value = getattr(self, name)
            if type(value) is not int or value <= 0:
                raise SequenceContractError(f'{name} must be a positive integer')
        if type(self.seed) is not int or not 0 <= self.seed < 2**32:
            raise SequenceContractError('seed must be an unsigned 32-bit integer')
        for name in ('dropout', 'min_delta', 'learning_rate'):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
                raise SequenceContractError(f'{name} must be finite numeric')
        if not 0 <= self.dropout < 1 or self.min_delta < 0 or self.learning_rate <= 0:
            raise SequenceContractError('invalid dropout, min_delta or learning_rate')
        if (not self.alpha_grid or len(set(self.alpha_grid)) != len(self.alpha_grid)
                or any(isinstance(x, bool) or not isinstance(x, (int, float))
                       or not math.isfinite(x) or not 0 <= x <= 1 for x in self.alpha_grid)
                or 0.0 not in self.alpha_grid or 1.0 not in self.alpha_grid):
            raise SequenceContractError('alpha_grid must contain unique finite [0,1] values and both endpoints')


def load_dl_config(path=DEFAULT_CONFIG):
    import yaml
    class UniqueLoader(yaml.SafeLoader):
        pass

    def unique_mapping(loader, node, deep=False):
        result = {}
        for key_node, value_node in node.value:
            key = loader.construct_object(key_node, deep=deep)
            if key in result:
                raise SequenceContractError(f'duplicate DL config key: {key}')
            result[key] = loader.construct_object(value_node, deep=deep)
        return result

    UniqueLoader.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, unique_mapping)
    document = yaml.load(Path(path).read_text(encoding='utf-8'), Loader=UniqueLoader)
    fields = {'sequence': {'lookback_days', 'max_events'},
              'lstm': {'embedding_dim', 'hidden_dim', 'dropout'},
              'training': {'max_epochs', 'patience', 'min_delta', 'batch_size', 'learning_rate', 'seed', 'cpu_threads'},
              'comparison': {'alpha_grid'}}
    if not isinstance(document, dict) or set(document) != {'schema_version', *fields}:
        raise SequenceContractError('DL config sections do not match schema')
    if type(document['schema_version']) is not int or document['schema_version'] != 1:
        raise SequenceContractError('unsupported DL config schema_version')
    flat = {}
    for section, expected in fields.items():
        value = document[section]
        if not isinstance(value, dict) or set(value) != expected:
            raise SequenceContractError(f'invalid DL config section {section}')
        flat.update(value)
    if not isinstance(flat['alpha_grid'], list):
        raise SequenceContractError('alpha_grid must be a list')
    flat['alpha_grid'] = tuple(flat['alpha_grid'])
    return DLConfig(**flat)


@dataclass(frozen=True)
class SequenceCoverage:
    start: object
    end: object
    status: str
    source: str
    run_id: str
    evidence_ref: str

    def __post_init__(self):
        if self.status not in ('complete', 'incomplete', 'unknown') or self.source not in ('simulator', 'commerce'):
            raise SequenceContractError('invalid coverage status/source')
        if any(not isinstance(x, str) or not x.strip() for x in (self.run_id, self.evidence_ref)):
            raise SequenceContractError('coverage requires run_id and evidence_ref')
        if event_time(self.start) >= event_time(self.end):
            raise SequenceContractError('coverage start must precede end')


@dataclass(frozen=True)
class SequenceBatch:
    ids: tuple[str, ...]
    tokens: np.ndarray
    lengths: np.ndarray
    ready: np.ndarray
    reasons: tuple[str | None, ...]
    metadata: Mapping

    def __post_init__(self):
        object.__setattr__(self, 'ids', validate_ids(self.ids))
        object.__setattr__(self, 'reasons', tuple(self.reasons))
        for name in ('tokens', 'lengths', 'ready'):
            value = getattr(self, name)
            if not isinstance(value, np.ndarray):
                raise SequenceContractError('sequence arrays must be numpy arrays')
            if value.dtype.hasobject:
                raise SequenceContractError('sequence arrays cannot contain Python objects')
            clone = np.frombuffer(value.tobytes(order='C'), dtype=value.dtype).reshape(value.shape)
            object.__setattr__(self, name, clone)
        if not isinstance(self.metadata, Mapping):
            raise SequenceContractError('sequence metadata must be a mapping')
        object.__setattr__(self, 'metadata', freeze_json(self.metadata))

    def reordered(self, ids):
        """같은 고객의 순서만 바꾸며 근거·배열·순서 지문을 함께 옮긴다."""
        self.validate()
        ids = validate_ids(ids)
        if set(ids) != set(self.ids):
            raise SequenceContractError('reordering cannot change the customer population')
        by_id = {cid: i for i, cid in enumerate(self.ids)}
        positions = [by_id[cid] for cid in ids]
        metadata = thaw_json(self.metadata)
        metadata['coverage'] = [metadata['coverage'][i] for i in positions]
        metadata['ids_order_sha256'] = id_hash(ids, ordered=True)
        return SequenceBatch(ids, self.tokens[positions], self.lengths[positions], self.ready[positions],
                             tuple(self.reasons[i] for i in positions), metadata)

    def validate(self, *, for_model=False):
        validate_ids(self.ids)
        n = len(self.ids)
        if (not isinstance(self.tokens, np.ndarray) or self.tokens.ndim != 2
                or self.tokens.shape[0] != n or self.tokens.shape[1] < 1
                or self.tokens.dtype != np.int64 or self.lengths.dtype != np.int64
                or self.lengths.shape != (n,) or self.ready.shape != (n,)
                or self.ready.dtype != bool or len(self.reasons) != n):
            raise SequenceContractError('sequence shapes or dtypes do not match customer rows')
        if np.any(self.tokens < 0) or np.any(self.tokens >= len(TOKEN_VOCAB) + 2):
            raise SequenceContractError('token outside fixed public vocabulary')
        if np.any(self.lengths < 0) or np.any(self.lengths > self.tokens.shape[1]):
            raise SequenceContractError('invalid sequence lengths')
        mask = np.arange(self.tokens.shape[1])[None, :] < self.lengths[:, None]
        if np.any(self.tokens[~mask] != PAD) or np.any(self.tokens[mask] == PAD):
            raise SequenceContractError('padding and sequence lengths disagree')
        for i in range(n):
            active = self.tokens[i, :self.lengths[i]]
            if NO_HISTORY in active and (len(active) != 1 or not self.ready[i]):
                raise SequenceContractError('NO_HISTORY is only a complete observed empty history')
            if bool(self.ready[i]) != (self.reasons[i] is None):
                raise SequenceContractError('readiness/reason mismatch')
        if self.metadata.get('ids_order_sha256') != id_hash(self.ids, ordered=True):
            raise SequenceContractError('customer ordering metadata mismatch')
        if self.metadata.get('ids_sha256') != id_hash(self.ids):
            raise SequenceContractError('customer set metadata mismatch')
        if type(self.metadata.get('max_events')) is not int or self.metadata['max_events'] != self.tokens.shape[1]:
            raise SequenceContractError('sequence width metadata mismatch')
        try:
            start = normalize_index_time(self.metadata['window_start'])
            end = normalize_index_time(self.metadata['window_end_exclusive'])
            index_time = normalize_index_time(self.metadata['index_time'])
            claims = self.metadata['coverage']
            inputs = self.metadata['input_metadata']
            purpose = self.metadata['purpose']
            source = self.metadata['source']
        except (KeyError, TypeError) as exc:
            raise SequenceContractError('sequence evidence metadata missing') from exc
        if not start < end or end != index_time or purpose not in ('experiment', 'observation'):
            raise SequenceContractError('invalid sequence window or purpose')
        if not isinstance(claims, tuple) or len(claims) != n:
            raise SequenceContractError('coverage must have one ordered record per customer')
        claimed_sources = set()
        for i, (cid, claim) in enumerate(zip(self.ids, claims)):
            if (not isinstance(claim, Mapping) or claim.get('customer_id') != cid
                    or claim.get('status') not in ('complete', 'incomplete', 'unknown')
                    or claim.get('source') not in ('simulator', 'commerce')
                    or not {'start', 'end'} <= set(claim)
                    or any(not isinstance(claim.get(k), str) or not claim[k].strip() for k in ('run_id', 'ref'))):
                raise SequenceContractError('invalid or misordered coverage record')
            claim_start, claim_end = event_time(claim['start']), event_time(claim['end'])
            if not claim_start < claim_end:
                raise SequenceContractError('invalid coverage window')
            expected = claim['status'] == 'complete' and claim_start <= start and claim_end >= end
            expected_reason = None if expected else 'OBSERVATION_UNCONFIRMED'
            if bool(self.ready[i]) != expected or self.reasons[i] != expected_reason:
                raise SequenceContractError('ready/reasons contradict coverage evidence')
            claimed_sources.add(claim['source'])
        expected_source = next(iter(claimed_sources)) if len(claimed_sources) == 1 else None
        if len(claimed_sources) > 1 or source != expected_source:
            raise SequenceContractError('sequence source contradicts coverage')
        if not isinstance(inputs, Mapping) or inputs.get('purpose') != purpose:
            raise SequenceContractError('nested input purpose mismatch')
        groups = inputs.get('groups')
        if not isinstance(groups, tuple) or len(groups) > 1:
            raise SequenceContractError('invalid nested source groups')
        if any(not isinstance(g, Mapping) or g.get('source') != source for g in groups):
            raise SequenceContractError('nested event source mismatch')
        expected_allowed = source == 'simulator' if groups else None
        if inputs.get('experiment_source_allowed') is not expected_allowed:
            raise SequenceContractError('nested experiment source flag mismatch')
        if for_model and (not n or not self.ready.all() or np.any(self.lengths == 0)
                          or self.metadata.get('purpose') != 'experiment'
                          or self.metadata.get('source') != 'simulator'):
            raise SequenceContractError('model requires non-empty complete simulator histories; no silent exclusions')


def build_event_sequences(events, customers, index_time, *, coverage: Mapping[str, SequenceCoverage],
                          config: DLConfig | None = None, purpose='experiment'):
    config = load_dl_config() if config is None else config
    ids = validate_ids(customers)
    t0 = normalize_index_time(index_time)
    if pd.isna(t0):
        raise SequenceContractError('index_time is missing')
    start = t0 - pd.Timedelta(days=config.lookback_days)
    required = {'customer_id', 'event_id', 'timestamp', 'event_type'}
    if not required <= set(events.columns):
        raise SequenceContractError('events missing required sequence columns')
    if not events['customer_id'].map(lambda x: isinstance(x, str) and bool(x) and x == x.strip()).all():
        raise SequenceContractError('event customer IDs must be non-empty strings without surrounding whitespace')
    if set(coverage) != set(ids) or any(not isinstance(v, SequenceCoverage) for v in coverage.values()):
        raise SequenceContractError('one explicit coverage record is required per customer')
    # 입력 행을 바꾸지 않는다. 범위 밖 고객·미래 행은 토큰/출처 판정에 사용하지 않는다.
    frame = events.loc[events['customer_id'].isin(ids)].copy()
    outside_population = len(events) - len(frame)
    frame['timestamp'] = frame['timestamp'].map(event_time)
    before_window = int((frame['timestamp'] < start).sum())
    after_cutoff = int((frame['timestamp'] >= t0).sum())
    frame = frame[(frame['timestamp'] >= start) & (frame['timestamp'] < t0)]
    window_customers = set(frame['customer_id'])
    metadata = check_input(frame, purpose)
    sources = {v.source for v in coverage.values()}
    if len(sources) > 1:
        raise SequenceContractError('coverage sources must be separated')
    source = next(iter(sources)) if sources else None
    actual_sources = {g['source'] for g in metadata['groups']}
    if actual_sources and actual_sources != sources:
        raise SequenceContractError('coverage source does not match event source')
    if purpose == 'experiment' and source == 'commerce':
        raise SequenceContractError('commerce coverage is observation-only')
    if frame['event_id'].isna().any() or frame['event_id'].duplicated().any():
        raise SequenceContractError('missing/duplicate event IDs in sequence window')
    if not frame['event_id'].map(lambda x: isinstance(x, str) and bool(x.strip())).all():
        raise SequenceContractError('event IDs must be non-empty strings')
    known = set(TOKEN_VOCAB) | set(FEATURE_FORBIDDEN_EVENT_TYPES)
    if not frame['event_type'].isin(known).all():
        raise SequenceContractError('event_type outside public contract')
    derived = frame['event_type'].isin(FEATURE_FORBIDDEN_EVENT_TYPES)
    excluded = int(derived.sum())
    frame = frame.loc[~derived].sort_values(['customer_id', 'timestamp', 'event_id'], kind='mergesort')
    grouped = {cid: g['event_type'].tolist() for cid, g in frame.groupby('customer_id', sort=False)}
    tokens = np.zeros((len(ids), config.max_events), dtype=np.int64)
    lengths = np.zeros(len(ids), dtype=np.int64)
    ready = np.zeros(len(ids), dtype=bool)
    reasons = []
    evidence = []
    truncated = 0
    for i, cid in enumerate(ids):
        claim = coverage[cid]
        complete = (claim.status == 'complete' and event_time(claim.start) <= start
                    and event_time(claim.end) >= t0)
        reasons.append(None if complete else 'OBSERVATION_UNCONFIRMED')
        ready[i] = complete
        history = grouped.get(cid, [])
        truncated += max(0, len(history) - config.max_events)
        encoded = [TOKEN_VOCAB[x] for x in history[-config.max_events:]]
        if not encoded and complete:
            encoded = [NO_HISTORY]
        lengths[i] = len(encoded)
        tokens[i, :len(encoded)] = encoded
        evidence.append({'customer_id': cid, 'run_id': claim.run_id, 'ref': claim.evidence_ref, 'source': claim.source,
                         'status': claim.status, 'start': event_time(claim.start).isoformat(),
                         'end': event_time(claim.end).isoformat()})
    batch = SequenceBatch(ids, tokens, lengths, ready, tuple(reasons), {
        'version': 'event-tokens-v1', 'purpose': purpose, 'source': source,
        'index_time': t0.isoformat(), 'window_start': start.isoformat(), 'window_end_exclusive': t0.isoformat(),
        'max_events': config.max_events, 'vocabulary': dict(TOKEN_VOCAB),
        'ids_sha256': id_hash(ids), 'ids_order_sha256': id_hash(ids, ordered=True),
        'derived_events_excluded': excluded, 'events_truncated': truncated,
        'rows_input': len(events), 'rows_outside_population': outside_population,
        'rows_before_window': before_window, 'rows_at_or_after_t0': after_cutoff,
        'rows_in_window': int(sum(g['event_rows'] for g in metadata['groups'])),
        'customers_with_no_window_events': len(set(ids) - window_customers),
        'input_metadata': metadata, 'coverage': evidence,
        'coverage_verification': 'caller-provided public evidence; not independently authenticated',
    })
    batch.validate()
    return batch


def align_binary_labels(labels, ids, *, require_two_classes=False):
    if not isinstance(labels, pd.Series) or not labels.index.is_unique or set(labels.index) != set(ids):
        raise SequenceContractError('labels must be an ID-indexed Series with exactly matching customers')
    values = labels.loc[list(ids)].to_numpy()
    if pd.isna(values).any() or not np.isin(values, [0, 1]).all():
        raise SequenceContractError('labels must be complete binary values; missing labels are not zero')
    result = values.astype(np.float32)
    if require_two_classes and len(np.unique(result)) != 2:
        raise SequenceContractError('training/validation requires two classes')
    return result
