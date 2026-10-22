"""S8 채점 지표 — Ground-truth 대비 사후 진단 (data_spec §4.4 · §14.1).

★ 이 모듈의 결과를 모델·Feature·Threshold·전략·예산 개선에 쓰지 않는다
  (`src/diagnostics/AGENTS.md`). 두 GATE 봉인 뒤 리포트 단계에서만 돈다.

지표:

- ``qini_coefficient`` — 관측 (treatment, y) 를 점수 내림차순으로 정렬한 Qini 곡선과
  무작위선 사이 면적. 모델 Qini 와 oracle Qini 를 **같은 정의·같은 모집단**으로 재기 위해
  둘 다 이 함수 하나로 계산한다.
- ``qini_oracle`` — 참 CATE(τ) 로 정렬했을 때의 Qini (§4.4 "이론적 최대").
- ``qini_attainment`` — 모델 Qini ÷ oracle. 분모 ≤ 0 이면 계산 불가(None + 사유).
- ``pehe`` — √mean((τ̂ − τ)²).
- ``corr_tau`` — Pearson · Spearman. 분산 0 이면 계산 불가.
- ``quadrant_confusion`` — 4분면 혼동행렬과 Persuadable ↔ Sleeping Dog 오분류율.

계산 불가는 0 이 아니다 — 값 ``None`` 과 ``reason`` 을 함께 낸다.
"""

from __future__ import annotations

from typing import Any, Sequence

import numpy as np
from scipy.stats import rankdata

PERSUADABLE = "persuadable"
SURE_THING = "sure_thing"
LOST_CAUSE = "lost_cause"
SLEEPING_DOG = "sleeping_dog"
#: τ̂ 하나로는 Sure Thing 과 Lost Cause 를 가를 수 없다(둘 다 τ = 0). 예측 쪽에서는 한 칸으로 묶는다.
NEUTRAL = "neutral"

TRUE_QUADRANTS = (PERSUADABLE, SURE_THING, LOST_CAUSE, SLEEPING_DOG)
PRED_QUADRANTS = (PERSUADABLE, SURE_THING, LOST_CAUSE, SLEEPING_DOG, NEUTRAL)


def _vec(values: Any, name: str) -> np.ndarray:
    arr = np.asarray(values, dtype=float).reshape(-1)
    if not np.all(np.isfinite(arr)):
        raise ValueError(f"{name} 에 유한하지 않은 값이 있다")
    return arr


def _same_length(**arrays: np.ndarray) -> int:
    lengths = {k: len(v) for k, v in arrays.items()}
    if len(set(lengths.values())) != 1:
        raise ValueError(f"길이가 다르다: {lengths}")
    return next(iter(lengths.values()))


def quadrant_of(y1: int, y0: int) -> str:
    """잠재결과 (Y(1), Y(0)) → 4분면 (data_spec §4.3)."""
    if y1 and not y0:
        return PERSUADABLE
    if y1 and y0:
        return SURE_THING
    if not y1 and not y0:
        return LOST_CAUSE
    return SLEEPING_DOG


# ---------------------------------------------------------------------------
# Qini
# ---------------------------------------------------------------------------

def qini_curve(score: Any, treatment: Any, y: Any) -> dict[str, np.ndarray]:
    """Qini 곡선 (Radcliffe 2007) — 점수 동률 묶음 경계에서만 점을 찍는다.

    ``Q(k) = Y_T(k) − Y_C(k) · N_T(k) / N_C(k)`` (상위 k 명 안의 처치군 결과 합 −
    대조군 결과 합을 처치군 크기로 환산). ``N_C(k) = 0`` 이면 대조군 항을 0 으로 둔다.

    동률을 한 묶음으로 처리하는 이유: 참 τ 는 이진 결과에서 −1·0·1 뿐이라 동률이 대부분이다.
    묶음 안 순서를 임의로 정하면 oracle 이 정렬 우연에 따라 흔들린다. 묶음 경계에서만 점을 찍고
    사이를 선형으로 이으면(사다리꼴 면적) 묶음 안 무작위 순서의 기대값과 같은 모양이 된다.

    반환: ``x`` (0~1, 모집단 비율) · ``q`` (1인당 단위로 나눈 Q(k)/N).
    """
    s = _vec(score, "score")
    w = _vec(treatment, "treatment")
    out = _vec(y, "y")
    n = _same_length(score=s, treatment=w, y=out)
    if n == 0:
        raise ValueError("빈 모집단")
    if not np.all(np.isin(w, (0.0, 1.0))):
        raise ValueError("treatment 는 0/1 이어야 한다")
    order = np.argsort(-s, kind="mergesort")
    s, w, out = s[order], w[order], out[order]
    n_t = np.cumsum(w)
    n_c = np.cumsum(1.0 - w)
    y_t = np.cumsum(out * w)
    y_c = np.cumsum(out * (1.0 - w))
    with np.errstate(divide="ignore", invalid="ignore"):
        scaled_c = np.where(n_c > 0, y_c * n_t / np.where(n_c > 0, n_c, 1.0), 0.0)
    q = y_t - scaled_c
    # 동률 묶음의 마지막 위치만 남긴다.
    last_of_group = np.r_[s[1:] != s[:-1], True]
    k = np.flatnonzero(last_of_group) + 1
    x = np.r_[0.0, k / n]
    qv = np.r_[0.0, q[last_of_group] / n]
    return {"x": x, "q": qv}


def qini_coefficient(score: Any, treatment: Any, y: Any) -> float:
    """Qini 곡선과 무작위선((0,0)→(1, Q(N)/N)) 사이 면적. Random 정책 = 0."""
    curve = qini_curve(score, treatment, y)
    x, q = curve["x"], curve["q"]
    area = float(np.sum((x[1:] - x[:-1]) * (q[1:] + q[:-1]) / 2.0))
    random_area = float(q[-1]) / 2.0
    return area - random_area


def qini_oracle(true_tau: Any, treatment: Any, y: Any) -> float:
    """참 CATE 로 정렬했을 때의 Qini — §4.4 의 "이론적 최대 Qini".

    모델 Qini 와 **같은 관측 (treatment, y)** 위에서 정렬 기준만 τ 로 바꾼다. 그래야 달성률의
    분모와 분자가 같은 정의·같은 모집단이다.
    """
    return qini_coefficient(true_tau, treatment, y)


def qini_attainment(model_qini: float | None, oracle: float | None) -> dict[str, Any]:
    """모델 Qini ÷ oracle. 분모 ≤ 0 이면 계산 불가.

    oracle ≤ 0 은 "참 τ 로 정렬해도 무작위보다 낫지 않다" — 이 모집단에서 순위로 얻을 것이
    없거나 표본이 작아 관측 Qini 가 뒤집혔다는 뜻이다. 그 비율은 의미가 없으므로 내지 않는다.
    """
    if model_qini is None or oracle is None:
        return {"value": None, "reason": "모델 Qini 또는 oracle 이 없다"}
    if not (np.isfinite(model_qini) and np.isfinite(oracle)):
        return {"value": None, "reason": "모델 Qini 또는 oracle 이 유한하지 않다"}
    if oracle <= 0:
        return {"value": None,
                "reason": f"oracle Qini 가 0 이하({oracle:.6g}) — 분모가 없어 달성률을 계산하지 않는다"}
    return {"value": float(model_qini) / float(oracle), "reason": None}


# ---------------------------------------------------------------------------
# CATE 크기 오차
# ---------------------------------------------------------------------------

def pehe(tau_hat: Any, tau_true: Any) -> float:
    """PEHE = √mean((τ̂ − τ)²) (Hill 2011). Qini 와 달리 순위가 아니라 크기를 본다."""
    a = _vec(tau_hat, "tau_hat")
    b = _vec(tau_true, "tau_true")
    if _same_length(tau_hat=a, tau_true=b) == 0:
        raise ValueError("빈 모집단")
    return float(np.sqrt(np.mean((a - b) ** 2)))


def _pearson(a: np.ndarray, b: np.ndarray) -> float:
    a = a - a.mean()
    b = b - b.mean()
    return float(np.sum(a * b) / np.sqrt(np.sum(a * a) * np.sum(b * b)))


def corr_tau(tau_hat: Any, tau_true: Any) -> dict[str, Any]:
    """corr(τ̂, τ) — Pearson 과 Spearman(평균 순위, 동률 허용).

    한쪽이라도 분산 0 이면 상관이 정의되지 않으므로 둘 다 None + 사유.
    """
    a = _vec(tau_hat, "tau_hat")
    b = _vec(tau_true, "tau_true")
    n = _same_length(tau_hat=a, tau_true=b)
    if n < 2:
        return {"pearson": None, "spearman": None, "n": n, "reason": "표본이 2 미만"}
    if np.ptp(a) == 0 or np.ptp(b) == 0:
        return {"pearson": None, "spearman": None, "n": n,
                "reason": "τ̂ 또는 τ 의 분산이 0 — 상관이 정의되지 않는다"}
    return {"pearson": _pearson(a, b),
            "spearman": _pearson(rankdata(a), rankdata(b)),
            "n": n, "reason": None}


# ---------------------------------------------------------------------------
# 4분면
# ---------------------------------------------------------------------------

def predicted_quadrant(tau_hat: float, eps: float = 0.0) -> str:
    """τ̂ → 예측 4분면. τ̂ > eps 는 Persuadable, τ̂ < −eps 는 Sleeping Dog, 나머지는 중립."""
    if tau_hat > eps:
        return PERSUADABLE
    if tau_hat < -eps:
        return SLEEPING_DOG
    return NEUTRAL


def quadrant_confusion(pred: Sequence[Any], true_quadrant: Sequence[str],
                       eps: float = 0.0) -> dict[str, Any]:
    """4분면 혼동행렬. ``pred`` 는 4분면 이름이거나 τ̂ 숫자(→ ``predicted_quadrant``).

    핵심 비율 (분모 0 이면 None):
      - ``persuadable_as_sleeping_dog`` = P(예측 SD | 참 Persuadable)
      - ``sleeping_dog_as_persuadable`` = P(예측 Persuadable | 참 SD) — 역효과 고객을 타게팅하는 오류
    """
    if len(pred) != len(true_quadrant):
        raise ValueError(f"길이가 다르다: pred={len(pred)} true={len(true_quadrant)}")
    labels: list[str] = []
    for p in pred:
        if isinstance(p, str):
            if p not in PRED_QUADRANTS:
                raise ValueError(f"알 수 없는 예측 4분면: {p!r}")
            labels.append(p)
        else:
            labels.append(predicted_quadrant(float(p), eps))
    for t in true_quadrant:
        if t not in TRUE_QUADRANTS:
            raise ValueError(f"알 수 없는 참 4분면: {t!r}")
    matrix = {t: {p: 0 for p in PRED_QUADRANTS} for t in TRUE_QUADRANTS}
    for t, p in zip(true_quadrant, labels):
        matrix[t][p] += 1

    def rate(true_q: str, pred_q: str) -> float | None:
        total = sum(matrix[true_q].values())
        return matrix[true_q][pred_q] / total if total else None

    return {
        "matrix": matrix,  # matrix[참][예측]
        "n": len(labels),
        "eps": eps,
        "persuadable_as_sleeping_dog": rate(PERSUADABLE, SLEEPING_DOG),
        "sleeping_dog_as_persuadable": rate(SLEEPING_DOG, PERSUADABLE),
        "true_share": {t: (sum(matrix[t].values()) / len(labels) if labels else None)
                       for t in TRUE_QUADRANTS},
    }


def score_arm(tau_hat: Any, tau_true: Any, treatment: Any, y: Any,
              true_quadrants: Sequence[str], eps: float = 0.0) -> dict[str, Any]:
    """한 처치 팔의 지표 묶음 — 같은 모집단·같은 순서의 배열을 받는다."""
    model = qini_coefficient(tau_hat, treatment, y)
    oracle = qini_oracle(tau_true, treatment, y)
    return {
        "n": int(len(np.asarray(tau_true))),
        "qini_model": model,
        "qini_oracle": oracle,
        "qini_attainment": qini_attainment(model, oracle),
        "pehe": pehe(tau_hat, tau_true),
        "corr_tau": corr_tau(tau_hat, tau_true),
        "quadrant_confusion": quadrant_confusion(list(np.asarray(tau_hat, dtype=float)),
                                                 list(true_quadrants), eps),
    }

