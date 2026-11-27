"""Uplift test 분할 보고 — 십분위표(SRS UP-005) · 메타러너 CATE 차이(UP-008) · 4분면 검증 H-SEG-2 (#219 2부).

입력은 ``evaluate_uplift_models(keep_predictions=True)`` 의 ``_test`` 다 — 탐색 RCT 의 test 분할(메타러너 · 규제 선택과
학습에 쓰지 않은 고객)에 대한 메타러너별 CATE · 처치 · 결과(유지 = 1 − 이탈). **보고만 한다** — 선택 · 튜닝 · 4분면
경계를 이 결과로 바꾸지 않는다(DR-217-uplift-tuning, DR-219-segments 「2부 결정」).

유의수준은 A/B 분석과 같다. 구간 — 십분위(두 비율의 차이)는 Newcombe(1998) 하이브리드 score 구간(H-SEG-1 과 같은
``segments._two_proportions``)이라 비율이 0 · 1 이어도 폭이 0 이 되지 않는다. H-SEG-2(차이의 차이)는 score 구간을 바로
쓸 수 없어 Wald 이고, 칸마다 고객 100명 · 유지와 이탈 각각 10명(DR-221 표본 부족 기준)이 안 되면 그 부분의 구간과
판정을 보류한다(점추정 · 수는 싣는다). 2026-11-26 광진 리뷰(PR #328) 반영 — DR-219-segments 「2부 결정」.
"""

from __future__ import annotations

import math
from itertools import combinations
from typing import Any, Mapping

import numpy as np
import pandas as pd

from src.decision.segments import DEFAULT_THRESHOLDS, SEGMENT_HYPOTHESES, uplift_score

CONTROL = "T0"
#: SRS UP-005 "Uplift by Decile".
N_BINS = 10
#: 메타러너 CATE 차이의 상위 겹침 비율에 쓰는 상위 비율 — 십분위표의 맨 윗 구간과 같은 크기.
TOP_SHARE = 1 / N_BINS


def _alpha(alpha: float | None) -> float:
    from src.decision.ab_test import ALPHA

    return ALPHA if alpha is None else float(alpha)


def _min_cell() -> int:
    from src.decision.observed_tiers import MIN_GROUP_CUSTOMERS

    return MIN_GROUP_CUSTOMERS


def _min_minority() -> int:
    from src.decision.observed_tiers import MIN_GROUP_MINORITY

    return MIN_GROUP_MINORITY


def _level(alpha: float) -> float:
    return round(1 - alpha, 10)


def _z(alpha: float) -> float:
    from scipy.stats import norm

    return float(norm.ppf(1 - alpha / 2))


def _mean_and_var(values: np.ndarray) -> tuple[float, float]:
    """평균과 평균의 분산. 이진 결과는 p(1 − p)/n(A/B 분석과 같은 식), 그 밖은 표본분산/n."""
    n = len(values)
    mean = float(values.mean())
    if set(np.unique(values)) <= {0.0, 1.0}:
        return mean, mean * (1 - mean) / n
    return mean, float(values.var(ddof=1)) / n if n > 1 else float("nan")


def _binary(values: np.ndarray) -> bool:
    return set(np.unique(values)) <= {0.0, 1.0}


def _effect(y: np.ndarray, treated: np.ndarray, mask: np.ndarray) -> dict[str, Any]:
    """고객군(mask) 안 처치 − 대조의 결과 평균 차이와 그 분산. 한쪽이 비면 None.

    처치 쪽은 관측된 처치군(T1~T4)을 **합친** 것이다 — 효과는 처치별 고객 수로 가중한 처치 유지율 − 대조 유지율이다
    (처치별 수 · 가중치는 ``_arms``). 이진 결과면 유지(1) 수도 싣는다(칸 표본 기준 · 구간 계산에 쓴다).
    """
    yt, yc = y[mask & treated], y[mask & ~treated]
    binary = _binary(y[mask]) if mask.any() else True
    out: dict[str, Any] = {"n_treated": int(len(yt)), "n_control": int(len(yc)),
                           "retained_treated": int(yt.sum()) if binary else None,
                           "retained_control": int(yc.sum()) if binary else None,
                           "rate_treated": None, "rate_control": None, "effect": None, "var": None}
    if len(yt) and len(yc):
        mt, vt = _mean_and_var(yt)
        mc, vc = _mean_and_var(yc)
        out.update(rate_treated=mt, rate_control=mc, effect=mt - mc, var=vt + vc)
    return out


def _arms(t: pd.Series, mask: np.ndarray) -> dict[str, Any]:
    """고객군 안 처치군별 고객 수와 합친 처치 효과에서의 가중치(= 그 처치 고객 수 ÷ 처치 고객 수)."""
    counts = t[mask & (t != CONTROL).to_numpy()].value_counts().sort_index()
    total = int(counts.sum())
    return {"treated_by_arm": {str(k): int(v) for k, v in counts.items()},
            "treated_weights": {str(k): (int(v) / total) for k, v in counts.items()} if total else {}}


def _cell_problems(cells: Mapping[str, tuple[int, int | None]], floor: int, minority: int) -> list[str]:
    """칸 표본 기준(DR-221 표본 부족과 같은 수) — 고객 ``floor`` 명 이상, 유지 · 이탈 각각 ``minority`` 명 이상.

    ``cells``: 칸 이름 → (고객 수, 유지 수). 유지 수가 None(이진 결과 아님)이면 고객 수만 본다. 어긋난 칸의 사유 목록.
    """
    out = []
    for name, (n, retained) in cells.items():
        if n < floor:
            out.append(f"{name} 고객 {n}명 < {floor}명")
        elif retained is not None and min(retained, n - retained) < minority:
            out.append(f"{name} 유지 {retained} · 이탈 {n - retained}명 — 적은 쪽 < {minority}명")
    return out


def _newcombe(x1: int, n1: int, x2: int, n2: int, alpha: float) -> list[float]:
    """두 비율 차이(1 − 2)의 Newcombe 하이브리드 score 구간 — ``segments._two_proportions`` 를 그대로 쓴다."""
    from src.decision.segments import _two_proportions

    interval = _two_proportions(x1, n1, x2, n2, alpha)["ci"]
    return [float(interval[0]), float(interval[1])]


def _interval(estimate: float, var: float, alpha: float) -> list[float]:
    half = _z(alpha) * math.sqrt(max(var, 0.0))
    return [estimate - half, estimate + half]


def _public(effect: Mapping[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in effect.items() if k != "var"}


def uplift_deciles(test: Mapping[str, Any], method: str, arm: str | None = None,
                   alpha: float | None = None) -> dict[str, Any]:
    """UP-005 — 대표 처치군 CATE 내림차순 10구간의 실측 uplift(처치 − 대조) · 평균 예측 uplift.

    T0 · 대표 처치군 고객만 쓴다(Qini · 선택과 같은 기준, DR-217). 같은 수로 나누고(순위 기준), 동점은 customer_id 순서다.
    구간은 Newcombe 하이브리드 score(이진 결과 · 처치 · 대조 각 1명 이상일 때) — 수와 점추정은 언제나 싣는다.
    """
    alpha = _alpha(alpha)
    arm = arm or test["primary_arm"]
    t, y = test["treatment"], test["y"].astype(float)
    score = test["cate"][method][arm].reindex(t.index).astype(float)
    sel = t.isin([CONTROL, arm]) & score.notna()
    frame = pd.DataFrame({"score": score[sel], "treated": (t[sel] == arm), "y": y[sel],
                          "cid": t.index[sel].map(str)})
    frame = frame.sort_values(["score", "cid"], ascending=[False, True], kind="mergesort")
    rows = []
    for rank, block in enumerate(np.array_split(np.arange(len(frame)), N_BINS), start=1):
        part = frame.iloc[block]
        eff = _effect(part["y"].to_numpy(), part["treated"].to_numpy(), np.ones(len(part), dtype=bool))
        ci, reason = None, None
        if eff["retained_treated"] is None:
            reason = "이진 결과가 아니다 — score 구간을 낼 수 없다"
        elif eff["n_treated"] < 1 or eff["n_control"] < 1:
            reason = "처치 · 대조 중 고객이 없는 쪽이 있다"
        else:
            ci = _newcombe(eff["retained_treated"], eff["n_treated"], eff["retained_control"], eff["n_control"], alpha)
        rows.append({"decile": rank, "n": int(len(part)), **_public(eff), "uplift_ci": ci,
                     **({"uplift_ci_reason": reason} if reason else {}),
                     "mean_predicted_uplift": float(part["score"].mean()) if len(part) else None})
    return {"method": method, "arm": arm, "n": int(len(frame)),
            "n_excluded_unscored": int((t.isin([CONTROL, arm]) & score.isna()).sum()), "alpha": alpha,
            "ci_level": _level(alpha), "ci_method": "Newcombe(1998) hybrid score interval",
            "rows": rows, "order": "예측 CATE 내림차순 — 1구간이 가장 높다"}


def learner_agreement(test: Mapping[str, Any], arm: str | None = None) -> dict[str, Any]:
    """UP-008 — 메타러너 쌍별 대표 처치군 CATE 의 Spearman 순위상관과 상위 10% 겹침 비율. 판정 없이 사실만."""
    from scipy.stats import spearmanr

    arm = arm or test["primary_arm"]
    cate = {m: frame[arm].astype(float) for m, frame in test["cate"].items()}
    pairs = []
    for a, b in combinations(sorted(cate), 2):
        both = pd.DataFrame({"a": cate[a], "b": cate[b]}).dropna()
        n = int(len(both))
        k = max(1, int(math.ceil(n * TOP_SHARE))) if n else 0
        cid = both.index.map(str)
        top = {}
        for col in ("a", "b"):
            order = pd.DataFrame({"s": both[col].to_numpy(), "cid": cid}).sort_values(
                ["s", "cid"], ascending=[False, True], kind="mergesort")
            top[col] = set(order["cid"].iloc[:k])
        rho = spearmanr(both["a"], both["b"]).statistic if n >= 3 else None
        pairs.append({"a": a, "b": b, "n": n,
                      "spearman": None if rho is None or not math.isfinite(rho) else float(rho),
                      "top_share": TOP_SHARE, "top_overlap": (len(top["a"] & top["b"]) / k) if k else None})
    return {"arm": arm, "pairs": pairs}


#: H-SEG-2 평가 규칙(DR-219-segments 「2부 결정」 — 2026-11-26 · 11-27 광진 리뷰 반영, 실측 결과를 보기 전에 고쳤다).
#: 두 주장을 따로 판정하고 전체는 둘을 합친다. ``SEGMENT_HYPOTHESES`` 의 평가 문구 대신 이 문구가 결과에 실린다.
H_SEG2_EVALUATION = (
    "① Persuadables − 나머지 고객의 효과 차이(각 고객군 안 처치 − 대조 유지율, Wald) 구간 하한 > 0 이면 ① 지지, 상한 ≤ 0 이면 "
    "① 반증, 그 밖은 ① 미확정. ② Sleeping Dogs 효과 구간 상한 ≤ 0 이면 ② 지지, 하한 > 0 이면 ② 반증, 그 밖은 ② 미확정. "
    "칸(고객군 × 처치 · 대조)마다 고객 100명 이상 · 유지와 이탈 각 10명 이상이어야 그 부분을 판정한다 — 아니면 그 부분은 "
    "판정 불가(구간 보류, 수 · 점추정은 싣는다). 전체(두 주장의 논리곱): ① · ② 중 하나라도 반증 → 지지되지 않음(반증, "
    "반증된 주장을 contradicted_by 에), 그 밖에 ① 판정 불가 → 판정 불가, ① 미확정 → 지지되지 않음(근거 부족), "
    "① 지지 · ② 지지 → 지지, ① 지지 · ② 미확정 또는 판정 불가 → 부분 지지"
)
#: 반증을 읽는 말 — 결과 ``contradicted_by`` 에 주장 키와 함께 싣는다. CLI 요약은 결과 JSON 만 읽으므로(이 모듈을 import
#: 하지 않는다) 문구를 결과에 둔다.
H_SEG2_CONTRADICTION = {
    "persuadables_vs_rest": "① Persuadables 효과 ≤ 나머지",
    "sleeping_dogs_le_zero": "② Sleeping Dogs 효과 > 0",
}
#: 실측 효과가 추정하는 값 — 네 처치의 등가중 평균이 아니다(결과 결손 행은 분할 전에 빠져 처치 비율이 고르다고 보장할 수 없다).
H_SEG2_ESTIMAND = ("고객군 안 관측된 처치군(T1~T4)을 합친 유지율 − 대조(T0) 유지율 — 처치별 고객 수로 가중한 평균이다"
                   "(처치별 수 · 가중치 = treated_by_arm · treated_weights)")


def quadrant_validation(test: Mapping[str, Any], method: str, thresholds: Mapping[str, float] | None = None,
                        alpha: float | None = None) -> dict[str, Any]:
    """H-SEG-2 평가(``H_SEG2_EVALUATION`` — DR-219-segments 「2부 결정」) — 결과를 보고 규칙을 바꾸지 않는다.

    ``parts`` 에 두 주장의 판정(``persuadables_vs_rest`` · ``sleeping_dogs_le_zero`` — 각각 supported · contradicted ·
    inconclusive · undetermined)을 따로 싣고, 전체 ``result`` 는 supported · partially_supported · not_supported ·
    undetermined 다. 지지되지 않음이면 ``not_supported_kind`` 가 근거 부족(insufficient_evidence)인지 반증(contradicted)인지
    가르고, ``contradicted_by`` 에 반증된 주장(``claim`` · ``reading``)을 적는다 — 한쪽의 반증은 다른 쪽이 판정 불가 · 미확정이어도 전체 판정에
    남는다(두 주장을 모두 만족해야 하는 가설, 2026-11-27 광진 리뷰).
    """
    alpha = _alpha(alpha)
    floor, minority = _min_cell(), _min_minority()
    level = _level(alpha)
    cfg = {**DEFAULT_THRESHOLDS, **(thresholds or {})}
    t = test["treatment"]
    y = test["y"].astype(float).reindex(t.index).to_numpy()
    u = uplift_score(test["cate"][method]).reindex(t.index).astype(float)
    valid = u.notna().to_numpy()
    band = float(u[valid].abs().quantile(cfg["uplift_band_q"])) if valid.any() else None
    treated = (t != CONTROL).to_numpy()
    hyp = {**dict(SEGMENT_HYPOTHESES[1]), "evaluation": H_SEG2_EVALUATION}
    if band is None:
        return {**hyp, "result": "undetermined", "not_supported_kind": None, "contradicted_by": [],
                "parts": {"persuadables_vs_rest": "undetermined", "sleeping_dogs_le_zero": "undetermined"},
                "evidence": {"reason": "test 분할에 CATE 가 없다", "method": method}}
    pers = valid & (u.to_numpy() > band)
    sleeping = valid & (u.to_numpy() < -band)
    rest = valid & ~pers
    groups = {"persuadables": pers, "rest": rest, "sleeping_dogs": sleeping}
    eff = {name: _effect(y, treated, mask) for name, mask in groups.items()}
    public = {name: {**_public(e), **_arms(t, groups[name])} for name, e in eff.items()}

    def cells(*names: str) -> dict[str, tuple[int, int | None]]:
        out = {}
        for name in names:
            e = eff[name]
            out[f"{name}_treated"] = (e["n_treated"], e["retained_treated"])
            out[f"{name}_control"] = (e["n_control"], e["retained_control"])
        return out

    evidence: dict[str, Any] = {"method": method, "uplift_band_q": cfg["uplift_band_q"], "uplift_band": band,
                                "alpha": alpha, "ci_level": level, "min_cell": floor, "min_minority": minority,
                                "estimand": H_SEG2_ESTIMAND,
                                "cells": {k: n for k, (n, _) in cells("persuadables", "rest").items()},
                                "persuadables": public["persuadables"], "rest": public["rest"]}

    # ② Sleeping Dogs 효과 ≤ 0
    sd = eff["sleeping_dogs"]
    sd_problems = _cell_problems(cells("sleeping_dogs"), floor, minority)
    if sd_problems or sd["effect"] is None:
        part2, sd_ci = "undetermined", None
    else:
        sd_ci = _interval(sd["effect"], sd["var"], alpha)
        part2 = "supported" if sd_ci[1] <= 0 else ("contradicted" if sd_ci[0] > 0 else "inconclusive")
    evidence["sleeping_dogs"] = {**public["sleeping_dogs"], "ci": sd_ci, "result": part2,
                                 **({"reason": "; ".join(sd_problems)} if sd_problems else {})}

    # ① Persuadables − 나머지 > 0
    p_problems = _cell_problems(cells("persuadables", "rest"), floor, minority)
    diff = (eff["persuadables"]["effect"] - eff["rest"]["effect"]
            if eff["persuadables"]["effect"] is not None and eff["rest"]["effect"] is not None else None)
    evidence["diff"] = diff
    if p_problems or diff is None:
        part1, ci = "undetermined", None
        evidence["reason"] = "; ".join(p_problems) or "한 고객군의 처치 · 대조 중 빈 쪽이 있다"
    else:
        ci = _interval(diff, eff["persuadables"]["var"] + eff["rest"]["var"], alpha)
        # 반증 = 구간 전체가 주장의 여집합(차이 ≤ 0)에 있다 — ② 의 반증(하한 > 0)과 같은 규칙(2026-11-27 광진 리뷰)
        part1 = "supported" if ci[0] > 0 else ("contradicted" if ci[1] <= 0 else "inconclusive")
    evidence.update(ci=ci, persuadables_result=part1)

    parts = {"persuadables_vs_rest": part1, "sleeping_dogs_le_zero": part2}
    contradicted_by = [{"claim": name, "reading": H_SEG2_CONTRADICTION[name]}
                       for name, state in parts.items() if state == "contradicted"]
    result, kind = _combine_h_seg2(part1, part2)
    return {**hyp, "result": result, "not_supported_kind": kind, "contradicted_by": contradicted_by,
            "parts": parts, "evidence": evidence}


def _combine_h_seg2(part1: str, part2: str) -> tuple[str, str | None]:
    """H-SEG-2 전체 판정(``H_SEG2_EVALUATION``) — ① · ② 의 논리곱. 반증이 판정 불가 · 근거 부족보다 먼저다."""
    if "contradicted" in (part1, part2):
        return "not_supported", "contradicted"
    if part1 == "undetermined":
        return "undetermined", None
    if part1 == "inconclusive":
        return "not_supported", "insufficient_evidence"
    return ("supported", None) if part2 == "supported" else ("partially_supported", None)


def uplift_report(test: Mapping[str, Any], method: str) -> dict[str, Any]:
    """test 분할 보고 한 묶음 — 십분위표 · 메타러너 CATE 차이 · H-SEG-2. ``method`` = 실제로 학습에 쓴 메타러너."""
    if method not in test["cate"]:
        raise ValueError(f"test 분할에 {method} 예측이 없다 — 있는 것: {sorted(test['cate'])}")
    return {
        "status": "ok", "method": method, "primary_arm": test["primary_arm"], "n_test": int(len(test["treatment"])),
        "deciles": uplift_deciles(test, method),
        "learner_agreement": learner_agreement(test),
        "quadrant_validation": quadrant_validation(test, method),
        "note": ("탐색 RCT test 분할(메타러너 · 규제 선택과 학습에 쓰지 않은 고객)에서 보고만 했다 — 선택 · 튜닝 · 4분면 경계를 "
                 "이 결과로 바꾸지 않는다(DR-217-uplift-tuning · DR-219-segments)"),
    }
