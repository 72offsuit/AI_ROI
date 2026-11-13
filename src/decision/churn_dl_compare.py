"""#218 로컬 준비: Validation 전용 가중치 선택과 같은 고객의 시험 비교.

분할을 생성하지 않는다. 승인된 공개 분할표를 나중에 이 인터페이스에 연결한다.
현재 지원 목적은 합성/개발 검증이며 GATE 2 정식 비교·Final Holdout 진입점이 아니다.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
import math
from numbers import Real
from pathlib import Path

import numpy as np
import pandas as pd

from src.decision.churn_sequence import (
    SequenceContractError, align_binary_labels, id_hash, validate_ids, load_dl_config, bound_value_hash,
)
from src.decision.churn_artifacts import atomic_artifact_directory, claim_evaluation

# #287: 수치 비교 규약이다. Test에서 고르는 하이퍼파라미터가 아니다.
ALPHA_TIE_ATOL = 1e-12


@dataclass(frozen=True)
class ComparisonProtocol:
    protocol_id: str
    dataset_version: str
    source: str
    purpose: str
    evidence_ref: str
    train_ids: tuple[str, ...]
    validation_ids: tuple[str, ...]
    test_ids: tuple[str, ...]

    def __post_init__(self):
        for key in ('train_ids', 'validation_ids', 'test_ids'):
            object.__setattr__(self, key, validate_ids(getattr(self, key)))
        self.validate()

    def validate(self):
        for value in (self.protocol_id, self.dataset_version, self.evidence_ref):
            if not isinstance(value, str) or not value.strip():
                raise SequenceContractError('comparison protocol needs version and public evidence reference')
        if self.source != 'simulator' or self.purpose not in ('synthetic', 'development'):
            raise SequenceContractError('only simulator synthetic/development comparison is supported before formal contract')
        groups = [validate_ids(x) for x in (self.train_ids, self.validation_ids, self.test_ids)]
        if any(not isinstance(getattr(self, k), tuple) for k in ('train_ids', 'validation_ids', 'test_ids')):
            raise SequenceContractError('protocol ID collections must be immutable tuples')
        if any(not x for x in groups) or any(set(groups[i]) & set(groups[j]) for i in range(3) for j in range(i)):
            raise SequenceContractError('Train/Validation/Test must be non-empty disjoint customer sets')

    @property
    def digest(self):
        self.validate()
        data = asdict(self)
        for key in ('train_ids', 'validation_ids', 'test_ids'):
            data[key] = sorted(data[key])
        return hashlib.sha256(json.dumps(data, ensure_ascii=False, sort_keys=True,
            separators=(',', ':')).encode()).hexdigest()


def _probabilities(scores, ids):
    if not isinstance(scores, pd.Series) or not scores.index.is_unique or set(scores.index) != set(ids):
        raise SequenceContractError('prediction IDs must exactly match the common customer set')
    if (not pd.api.types.is_numeric_dtype(scores.dtype) or pd.api.types.is_bool_dtype(scores.dtype)
            or pd.api.types.is_complex_dtype(scores.dtype)):
        raise SequenceContractError('probabilities require a real numeric dtype, not strings or boolean labels')
    values = scores.loc[list(ids)].to_numpy(dtype=float, na_value=np.nan)
    if not np.isfinite(values).all() or np.any(values < 0) or np.any(values > 1):
        raise SequenceContractError('probabilities must be finite and inside [0,1]')
    return values


@dataclass(frozen=True)
class FrozenSelection:
    protocol_digest: str
    alpha: float
    # ML, DL, ensemble 순서. mutable dict 대신 고정 tuple로 보관한다.
    thresholds: tuple[float, float, float]
    validation_ids_sha256: str
    validation_label_sha256: str
    candidates: tuple[tuple[float, float], ...]
    validation_rows: tuple[tuple[str, float, float, float], ...]
    validation_ml_sha256: str
    validation_dl_sha256: str
    tie_atol: float = ALPHA_TIE_ATOL

    def __post_init__(self):
        object.__setattr__(self, 'thresholds', tuple(self.thresholds))
        object.__setattr__(self, 'candidates', tuple(tuple(row) for row in self.candidates))
        object.__setattr__(self, 'validation_rows', tuple(tuple(row) for row in self.validation_rows))

    def validate(self, protocol):
        protocol.validate()
        if self.protocol_digest != protocol.digest or self.validation_ids_sha256 != id_hash(protocol.validation_ids):
            raise SequenceContractError('selection and common split protocol differ')
        if self.tie_atol != ALPHA_TIE_ATOL or not self.validation_rows:
            raise SequenceContractError('unsupported selection tolerance or missing Validation snapshot')
        if (isinstance(self.alpha, bool) or not isinstance(self.alpha, Real) or not math.isfinite(self.alpha)
                or not 0 <= self.alpha <= 1 or len(self.thresholds) != 3
                or any(isinstance(x, bool) or not isinstance(x, Real) or not math.isfinite(x)
                       or not 0 <= x <= 1 for x in self.thresholds)):
            raise SequenceContractError('invalid frozen alpha or thresholds')
        if any(len(row) != 4 for row in self.validation_rows):
            raise SequenceContractError('invalid Validation evidence row')
        ids = validate_ids(row[0] for row in self.validation_rows)
        if ids != tuple(sorted(protocol.validation_ids)):
            raise SequenceContractError('Validation snapshot customers/order mismatch')
        values = [row[1:] for row in self.validation_rows]
        if any(isinstance(x, bool) or not isinstance(x, Real) or not math.isfinite(x) for row in values for x in row):
            raise SequenceContractError('non-numeric or incomplete Validation snapshot')
        labels, ml, dl = (np.asarray([row[i] for row in values]) for i in range(3))
        y = align_binary_labels(pd.Series(labels, index=ids), ids, require_two_classes=True)
        ml = _probabilities(pd.Series(ml, index=ids), ids)
        dl = _probabilities(pd.Series(dl, index=ids), ids)
        if (self.validation_label_sha256 != bound_value_hash(ids, y)
                or self.validation_ml_sha256 != bound_value_hash(ids, ml)
                or self.validation_dl_sha256 != bound_value_hash(ids, dl)):
            raise SequenceContractError('Validation snapshot fingerprint mismatch')
        if not self.candidates or any(len(row) != 2 for row in self.candidates):
            raise SequenceContractError('missing or malformed selection candidates')
        if any(isinstance(loss, bool) or not isinstance(loss, Real) or not math.isfinite(loss) or loss < 0
               for _, loss in self.candidates):
            raise SequenceContractError('invalid candidate loss')
        grid = _alpha_grid(row[0] for row in self.candidates)
        if tuple(row[0] for row in self.candidates) != grid:
            raise SequenceContractError('selection candidates must be sorted')
        rows, alpha, thresholds = _selection_components(y, ml, dl, grid)
        if self.candidates != rows or self.alpha != alpha or self.thresholds != thresholds:
            raise SequenceContractError('selection candidates/alpha/thresholds contradict Validation evidence')


def _alpha_grid(values):
    grid = tuple(values)
    if (not grid or any(isinstance(x, bool) or not isinstance(x, Real)
                        or not math.isfinite(x) or not 0 <= x <= 1 for x in grid)
            or len(set(grid)) != len(grid) or 0.0 not in grid or 1.0 not in grid):
        raise SequenceContractError('alpha grid must include endpoints and finite unique [0,1] values')
    return tuple(sorted(float(x) for x in grid))


def _selection_components(y, ml, dl, grid):
    from sklearn.metrics import log_loss
    from src.decision.churn import _best_f1_threshold
    rows = tuple((alpha, float(log_loss(y, (1-alpha)*ml + alpha*dl, labels=[0, 1]))) for alpha in grid)
    best = min(loss for _, loss in rows)
    alpha = min(a for a, loss in rows if loss <= best + ALPHA_TIE_ATOL)
    thresholds = tuple(float(_best_f1_threshold(y, p)) for p in (ml, dl, (1-alpha)*ml + alpha*dl))
    return rows, alpha, thresholds


def select_ensemble(protocol: ComparisonProtocol, validation_labels,
                    ml_validation, dl_validation, *, alpha_grid=None):
    """Test 라벨·예측 인자가 없다. 낮은 log loss, 동점은 작은 DL 가중치."""
    protocol.validate()
    grid = _alpha_grid(load_dl_config().alpha_grid if alpha_grid is None else alpha_grid)
    ids = tuple(sorted(protocol.validation_ids))
    y = align_binary_labels(validation_labels, ids, require_two_classes=True)
    ml = _probabilities(ml_validation, ids)
    dl = _probabilities(dl_validation, ids)
    rows, alpha, thresholds = _selection_components(y, ml, dl, grid)
    evidence = tuple((cid, float(a), float(b), float(c)) for cid, a, b, c in zip(ids, y, ml, dl))
    selection = FrozenSelection(protocol.digest, alpha, thresholds, id_hash(ids),
        bound_value_hash(ids, y), rows, evidence, bound_value_hash(ids, ml), bound_value_hash(ids, dl))
    selection.validate(protocol)
    return selection


def evaluate_common_test(protocol: ComparisonProtocol, selection: FrozenSelection,
                         test_labels, ml_test, dl_test, *, directory):
    """선택 예약 후 Test를 읽고 완성 결과만 게시한다. 예약 범위는 이 목적지에 한정된다."""
    from src.decision.churn import _metrics

    protocol.validate()
    selection.validate(protocol)
    ids = protocol.test_ids
    directory = Path(directory)
    selection_snapshot = asdict(selection)
    selection_hash = hashlib.sha256(json.dumps(selection_snapshot, sort_keys=True,
        ensure_ascii=False, allow_nan=False, separators=(',', ':')).encode()).hexdigest()
    declaration = {'protocol_digest': protocol.digest, 'test_ids_sha256': id_hash(ids),
                   'test_order_sha256': id_hash(ids, ordered=True), 'status': 'completed',
                   'selection_sha256': selection_hash,
                   'scope': 'one destination claim; not a global Test access audit'}
    claim = claim_evaluation(directory, {'status': 'claimed_before_test_read',
        'selection': selection_snapshot, 'selection_sha256': selection_hash,
        'notice': 'immutable access reservation, not completion status; retained after failure'})
    y = align_binary_labels(test_labels, ids, require_two_classes=True)
    ml = _probabilities(ml_test, ids)
    dl = _probabilities(dl_test, ids)
    with atomic_artifact_directory(directory) as staging:
        scores = (ml, dl, (1-selection.alpha)*ml + selection.alpha*dl)
        models = []
        for name, probability, threshold in zip(('ml', 'lstm', 'ensemble'), scores, selection.thresholds):
            metrics = _metrics(y, probability, threshold)
            models.append({'name': name, 'n': len(ids), 'test_ids_sha256': id_hash(ids),
                           'test_order_sha256': id_hash(ids, ordered=True), 'threshold': threshold,
                           'metrics': {k: float(v) if math.isfinite(v) else None for k, v in metrics.items()}})
        report = {'status': 'ok', 'purpose': protocol.purpose, 'source': protocol.source,
                  'formal_evaluation': False, 'dataset_version': protocol.dataset_version,
                  'protocol_digest': protocol.digest, 'models': models, 'alpha': selection.alpha,
                  'alpha_selected_using': f'Validation log loss; absolute tolerance {ALPHA_TIE_ATOL:g}, then smaller alpha',
                  'selection': selection_snapshot, 'selection_sha256': selection_hash,
                  'test_label_sha256': bound_value_hash(ids, y), 'label_hash_method': 'sorted-id-value-json-v1',
                  'selection_integrity': 'recomputed from frozen Validation data; not producer authentication',
                  'access_claim': claim.name,
                  'mixing_used': 0 < selection.alpha < 1, 'final_holdout_used': False,
                  'split_scope': 'customer disjointness checked; temporal/label-window contract still requires #215',
                  'prediction_provenance': 'caller-provided predictions, not authenticated training lineage'}
        (staging / 'comparison.json').write_text(json.dumps(report, ensure_ascii=False, allow_nan=False, indent=2), encoding='utf-8')
        (staging / 'test_access.json').write_text(json.dumps(declaration, ensure_ascii=False, indent=2), encoding='utf-8')
    return report
