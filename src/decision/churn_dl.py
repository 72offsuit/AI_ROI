"""Churn DL — 일별 활동 시퀀스 GRU + Early Stopping (스프린트 1 P1, 이슈 #144).

입력: T0 직전 `lookback_days` 일의 일별 이벤트 수(채널 = 관측 이벤트 종류 묶음), log1p.
모델: GRU(hidden 32) → 마지막 상태 → 선형 → logit. BCEWithLogits(pos_weight=음/양 비)로 불균형 처리.
Early Stopping: 학습 fold 안에서 층화 20% 를 검증으로 떼어 검증 loss 가 `patience` 에폭 동안
좋아지지 않으면 멈추고 최선 가중치로 되돌린다. **검증 fold(평가용)는 학습·멈춤에 쓰지 않는다.**

평가 fold 는 `churn.fold_indices` 와 같다 — ML 과 같은 고객·같은 fold (PRD §43).

torch 는 **선택 의존성**이다 (`requirements-ml.txt`, CI 비대상). 이 모듈은 torch 없이도
import 되고, 학습 함수를 부를 때만 torch 를 요구한다.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from src.decision.features.sprint_table import _clean, to_index_time

CHANNELS: tuple[tuple[str, frozenset[str]], ...] = (
    ("visit", frozenset({"session_start", "return_visit"})),
    ("page_view", frozenset({"page_view"})),
    ("product_view", frozenset({"product_view"})),
    ("search", frozenset({"search"})),
    ("cart", frozenset({"add_to_cart", "remove_from_cart"})),
    ("checkout", frozenset({"checkout_start"})),
    ("purchase", frozenset({"purchase"})),
    ("coupon", frozenset({"coupon_exposed", "coupon_clicked", "coupon_use"})),
    ("campaign", frozenset({"campaign_exposed", "push_sent"})),
    ("service", frozenset({"review", "cs_contact"})),
)


def build_daily_sequences(events: pd.DataFrame, index_time, customers, lookback_days: int = 56) -> np.ndarray:
    """(n_customers, lookback_days, n_channels) float32. T0 이전 이벤트만, 마지막 축이 T0 직전 날."""
    t0 = to_index_time(index_time)
    ids = pd.Index(customers)
    frame = _clean(events)
    start = t0 - pd.Timedelta(days=lookback_days)
    frame = frame[(frame["timestamp"] >= start) & (frame["timestamp"] < t0) & frame["customer_id"].isin(ids)]
    out = np.zeros((len(ids), lookback_days, len(CHANNELS)), dtype=np.float32)
    if len(frame):
        day = ((frame["timestamp"] - start).dt.total_seconds() // 86400).astype(int).clip(0, lookback_days - 1)
        row = ids.get_indexer(frame["customer_id"])
        for c, (_, types) in enumerate(CHANNELS):
            mask = frame["event_type"].isin(types).to_numpy()
            np.add.at(out, (row[mask], day.to_numpy()[mask], c), 1.0)
    return np.log1p(out)


def _make_net(n_channels: int, hidden: int):
    import torch
    from torch import nn

    class GRUChurn(nn.Module):
        def __init__(self):
            super().__init__()
            self.gru = nn.GRU(n_channels, hidden, batch_first=True)
            self.head = nn.Sequential(nn.Dropout(0.2), nn.Linear(hidden, 1))

        def forward(self, x):
            _, h = self.gru(x)
            return self.head(h[-1]).squeeze(-1)

    return GRUChurn(), torch


def fit_gru(seqs: np.ndarray, y: np.ndarray, seed: int, *, hidden: int = 32, max_epochs: int = 60,
            patience: int = 6, batch_size: int = 64, lr: float = 3e-3) -> tuple[object, dict]:
    """학습 데이터 안에서 층화 20% 를 Early Stopping 검증으로 쓴다."""
    from sklearn.model_selection import train_test_split

    net, torch = _make_net(seqs.shape[2], hidden)
    torch.manual_seed(seed)
    tr, va = train_test_split(np.arange(len(y)), test_size=0.2, stratify=y, random_state=seed)
    xt, yt = torch.tensor(seqs[tr]), torch.tensor(y[tr], dtype=torch.float32)
    xv, yv = torch.tensor(seqs[va]), torch.tensor(y[va], dtype=torch.float32)
    pos = max(float(yt.sum()), 1.0)
    loss_fn = torch.nn.BCEWithLogitsLoss(pos_weight=torch.tensor((len(yt) - pos) / pos))
    opt = torch.optim.Adam(net.parameters(), lr=lr)
    gen = torch.Generator().manual_seed(seed)
    best, best_state, bad, epochs = float("inf"), None, 0, 0
    for epoch in range(max_epochs):
        net.train()
        for idx in torch.randperm(len(yt), generator=gen).split(batch_size):
            opt.zero_grad()
            loss_fn(net(xt[idx]), yt[idx]).backward()
            opt.step()
        net.eval()
        with torch.no_grad():
            val = float(loss_fn(net(xv), yv))
        epochs = epoch + 1
        if val < best - 1e-4:
            best, bad = val, 0
            best_state = {k: v.clone() for k, v in net.state_dict().items()}
        else:
            bad += 1
            if bad >= patience:
                break
    if best_state is not None:
        net.load_state_dict(best_state)
    net.eval()
    return net, {"epochs_run": epochs, "best_val_loss": best, "stopped_early": epochs < max_epochs}


def predict_gru(net, seqs: np.ndarray) -> np.ndarray:
    import torch

    with torch.no_grad():
        return torch.sigmoid(net(torch.tensor(seqs))).numpy()


def evaluate_churn_gru(seqs: np.ndarray, y, seed: int) -> dict:
    """`evaluate_churn_models` 의 `models[]` 항목과 같은 모양을 돌려준다 (그 목록에 붙일 수 있다)."""
    from src.decision.churn import _best_f1_threshold, _metrics, _summary, fold_indices

    yv = np.asarray(y).astype(int)
    per_fold: dict[str, list[float]] = {"roc_auc": [], "pr_auc": [], "f1": [], "lift_at_10": []}
    runs = []
    for k, (tr, va) in enumerate(fold_indices(yv, seed)):
        net, info = fit_gru(seqs[tr], yv[tr], seed + k)
        # 임계: 학습 fold 의 Early Stopping 검증 부분이 아니라 학습 fold 전체 확률에서 F1 최대
        threshold = _best_f1_threshold(yv[tr], predict_gru(net, seqs[tr]))
        for key, value in _metrics(yv[va], predict_gru(net, seqs[va]), threshold).items():
            per_fold[key].append(value)
        runs.append(info)
    return {"name": "gru_daily", "kind": "proposed_dl",
            "cv": {key: _summary(values) for key, values in per_fold.items()},
            "input": f"일별 이벤트 수 {seqs.shape[1]}일 × {seqs.shape[2]}채널 (log1p)",
            "early_stopping": runs}
