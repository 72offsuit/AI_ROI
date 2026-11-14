"""#218: CPU 토큰 LSTM. Test 입력 없이 Train/Validation으로만 학습·중단한다.

torch는 함수 안에서만 import한다. 전체 공통 분할·오케스트레이션 연결은 별도 인수 단계다.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
import csv
import hashlib
import json
import math
from pathlib import Path
import platform
import time

import numpy as np
import pandas as pd

from src.decision.churn_sequence import (
    DLConfig, SequenceBatch, SequenceContractError, TOKEN_VOCAB,
    align_binary_labels, id_hash, load_dl_config, thaw_json, bound_value_hash,
)
from src.decision.churn_artifacts import atomic_artifact_directory


def _make_network(config):
    import torch
    from torch import nn
    from torch.nn.utils.rnn import pack_padded_sequence

    class EventLSTM(nn.Module):
        def __init__(self):
            super().__init__()
            self.embedding = nn.Embedding(len(TOKEN_VOCAB) + 2, config.embedding_dim, padding_idx=0)
            self.lstm = nn.LSTM(config.embedding_dim, config.hidden_dim, batch_first=True)
            self.head = nn.Sequential(nn.Dropout(config.dropout), nn.Linear(config.hidden_dim, 1))

        def forward(self, tokens, lengths):
            packed = pack_padded_sequence(self.embedding(tokens), lengths.cpu(),
                                          batch_first=True, enforce_sorted=False)
            _, (hidden, _) = self.lstm(packed)
            return self.head(hidden[-1]).squeeze(-1)

    return EventLSTM(), torch


@dataclass
class EarlyStop:
    patience: int
    min_delta: float
    best: float = math.inf
    bad_epochs: int = 0
    best_epoch: int = 0

    def update(self, loss, epoch):
        if not math.isfinite(loss):
            raise SequenceContractError('non-finite validation loss')
        improved = loss < self.best - self.min_delta
        if improved:
            self.best, self.bad_epochs, self.best_epoch = float(loss), 0, epoch
        else:
            self.bad_epochs += 1
        return improved, self.bad_epochs >= self.patience


@dataclass
class FittedLSTM:
    network: object
    config: DLConfig
    training: dict


def _compatible(batch, config):
    batch.validate(for_model=True)
    if (batch.tokens.shape[1] != config.max_events or batch.metadata.get('vocabulary') != TOKEN_VOCAB
            or batch.metadata.get('version') != 'event-tokens-v1'):
        raise SequenceContractError('sequence vocabulary/length/version differs from model config')
    start = pd.Timestamp(batch.metadata['window_start'])
    end = pd.Timestamp(batch.metadata['window_end_exclusive'])
    if end - start != pd.Timedelta(days=config.lookback_days):
        raise SequenceContractError('sequence lookback differs from model config')


def _tensor_batches(net, batch, batch_size, torch):
    chunks = []
    net.eval()
    with torch.no_grad():
        for start in range(0, len(batch.ids), batch_size):
            x = torch.tensor(batch.tokens[start:start + batch_size], dtype=torch.long)
            lengths = torch.tensor(batch.lengths[start:start + batch_size], dtype=torch.long)
            chunks.append(net(x, lengths))
    return torch.cat(chunks)


def fit_lstm(train: SequenceBatch, train_labels: pd.Series,
             validation: SequenceBatch, validation_labels: pd.Series, *, config=None):
    config = load_dl_config() if config is None else config
    _compatible(train, config)
    _compatible(validation, config)
    if set(train.ids).intersection(validation.ids):
        raise SequenceContractError('Train and Validation customers overlap')
    y_train = align_binary_labels(train_labels, train.ids, require_two_classes=True)
    y_val = align_binary_labels(validation_labels, validation.ids, require_two_classes=True)
    import torch
    # 복원 가능한 설정만 남기고 호출자의 전역 RNG/thread 설정을 복구한다.
    old_threads = torch.get_num_threads()
    start_wall, start_cpu = time.perf_counter(), time.process_time()
    with torch.random.fork_rng(devices=[]):
        try:
            torch.set_num_threads(config.cpu_threads)
            torch.manual_seed(config.seed)  # 모델 생성보다 먼저
            net, _ = _make_network(config)
            optimizer = torch.optim.Adam(net.parameters(), lr=config.learning_rate)
            loss_fn = torch.nn.BCEWithLogitsLoss()
            labels_t = torch.tensor(y_train)
            labels_v = torch.tensor(y_val)
            x = torch.tensor(train.tokens, dtype=torch.long)
            lengths = torch.tensor(train.lengths, dtype=torch.long)
            generator = torch.Generator(device='cpu').manual_seed(config.seed)
            stopping = EarlyStop(config.patience, config.min_delta)
            best_state, logs = None, []
            stopped_early = False
            for epoch in range(1, config.max_epochs + 1):
                net.train()
                total = 0.0
                for indices in torch.randperm(len(train.ids), generator=generator).split(config.batch_size):
                    optimizer.zero_grad()
                    loss = loss_fn(net(x[indices], lengths[indices]), labels_t[indices])
                    if not torch.isfinite(loss):
                        raise SequenceContractError('non-finite training loss')
                    loss.backward()
                    optimizer.step()
                    total += float(loss.detach()) * len(indices)
                val_loss = float(loss_fn(_tensor_batches(net, validation, config.batch_size, torch), labels_v))
                improved, stop = stopping.update(val_loss, epoch)
                if improved:
                    best_state = {k: v.detach().clone() for k, v in net.state_dict().items()}
                logs.append({'epoch': epoch, 'train_loss': total / len(train.ids),
                             'validation_loss': val_loss, 'improved': bool(improved)})
                if stop:
                    stopped_early = epoch < config.max_epochs
                    break
            if best_state is None:
                raise SequenceContractError('training produced no usable checkpoint')
            net.load_state_dict(best_state)
            net.eval()
            restored_loss = float(loss_fn(_tensor_batches(net, validation, config.batch_size, torch), labels_v))
        finally:
            torch.set_num_threads(old_threads)
    return FittedLSTM(net, config, {
        'version': 'lstm-event-v1', 'device': 'cpu', 'seed': config.seed,
        'python': platform.python_version(), 'torch': torch.__version__,
        'epochs_run': len(logs), 'best_epoch': stopping.best_epoch,
        'best_validation_loss': stopping.best, 'restored_validation_loss': restored_loss,
        'stopped_early': stopped_early, 'stop_reason': 'patience' if len(logs) < config.max_epochs else 'max_epochs',
        'history': logs, 'wall_seconds': time.perf_counter() - start_wall,
        'cpu_seconds': time.process_time() - start_cpu,
        'train_ids': list(train.ids), 'validation_ids': list(validation.ids),
        'train_ids_sha256': id_hash(train.ids), 'validation_ids_sha256': id_hash(validation.ids),
        'train_metadata': thaw_json(train.metadata), 'validation_metadata': thaw_json(validation.metadata),
        'label_sha256': bound_value_hash(train.ids, y_train),
        'validation_label_sha256': bound_value_hash(validation.ids, y_val),
        'label_hash_method': 'sorted-id-value-json-v1',
        'split_scope': 'caller-provided customer-disjoint Train/Validation; temporal compliance not established',
        'test_accesses_during_fit': 0, 'final_holdout_used': False,
    })


def predict_lstm(model: FittedLSTM, batch: SequenceBatch):
    _compatible(batch, model.config)
    import torch
    previous = torch.get_num_threads()
    try:
        torch.set_num_threads(model.config.cpu_threads)
        scores = torch.sigmoid(_tensor_batches(model.network, batch, model.config.batch_size, torch)).numpy()
    finally:
        torch.set_num_threads(previous)
    if not np.isfinite(scores).all():
        raise SequenceContractError('non-finite LSTM predictions')
    return pd.Series(scores, index=pd.Index(batch.ids, name='customer_id'), name='churn_probability')


def _digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def save_lstm(model: FittedLSTM, directory):
    """신뢰하는 로컬 학습 결과를 완성한 뒤 새 폴더에 게시한다."""
    with atomic_artifact_directory(directory) as staging:
        return _write_model_artifacts(model, staging)


def _write_model_artifacts(model, directory):
    import torch
    # 모델 객체 자체(지역 클래스)는 pickle하지 않는다.
    config_data = asdict(model.config)
    config_data['alpha_grid'] = list(config_data['alpha_grid'])
    checkpoint = {'version': 'lstm-event-v1', 'config': config_data,
                  'vocabulary': dict(TOKEN_VOCAB), 'state_dict': model.network.state_dict()}
    path = directory / 'churn_lstm.pt'
    torch.save(checkpoint, path)
    log = directory / 'dl_training_log.json'
    log.write_text(json.dumps(model.training, ensure_ascii=False, allow_nan=False, indent=2), encoding='utf-8')
    curve = directory / 'dl_training_curve.csv'
    with curve.open('w', newline='', encoding='utf-8') as stream:
        writer = csv.DictWriter(stream, fieldnames=['epoch', 'train_loss', 'validation_loss', 'improved'])
        writer.writeheader()
        writer.writerows(model.training['history'])
    manifest = {'version': 'lstm-event-v1', 'config': config_data, 'vocabulary': dict(TOKEN_VOCAB),
                'files': {p.name: {'sha256': _digest(p), 'bytes': p.stat().st_size} for p in (path, log, curve)},
                'notice': 'local integrity check, not producer authentication; trusted local artifacts only'}
    (directory / 'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, allow_nan=False, indent=2), encoding='utf-8')
    return manifest


def load_lstm(directory):
    import torch
    directory = Path(directory)
    manifest = json.loads((directory / 'manifest.json').read_text(encoding='utf-8'))
    if manifest.get('version') != 'lstm-event-v1' or manifest.get('vocabulary') != TOKEN_VOCAB:
        raise SequenceContractError('unsupported model version or vocabulary')
    expected_files = ('churn_lstm.pt', 'dl_training_log.json', 'dl_training_curve.csv')
    if set(manifest.get('files', {})) != set(expected_files):
        raise SequenceContractError('checkpoint file roles do not match expected files')
    for name in expected_files:
        path = directory / name
        record = manifest['files'][name]
        if path.is_symlink() or path.stat().st_size != record['bytes'] or _digest(path) != record['sha256']:
            raise SequenceContractError('checkpoint bytes or hash mismatch')
    checkpoint = torch.load(directory / 'churn_lstm.pt', map_location='cpu', weights_only=True)
    if (checkpoint.get('version') != manifest['version'] or checkpoint.get('vocabulary') != TOKEN_VOCAB
            or checkpoint.get('config') != manifest.get('config')):
        raise SequenceContractError('checkpoint/manifest mismatch')
    raw = dict(checkpoint['config'])
    raw['alpha_grid'] = tuple(raw['alpha_grid'])
    config = DLConfig(**raw)
    with torch.random.fork_rng(devices=[]):
        net, _ = _make_network(config)
    net.load_state_dict(checkpoint['state_dict'], strict=True)
    net.eval()
    training = json.loads((directory / 'dl_training_log.json').read_text(encoding='utf-8'))
    return FittedLSTM(net, config, training)
