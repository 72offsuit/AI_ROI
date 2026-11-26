"""Uplift test 분할 보고 — 십분위표(SRS UP-005) · 메타러너 CATE 차이(UP-008) · 4분면 검증 H-SEG-2 (#219 2부).

입력은 ``evaluate_uplift_models(keep_predictions=True)`` 의 ``_test`` 다 — 탐색 RCT 의 test 분할(메타러너 · 규제 선택과
학습에 쓰지 않은 고객)에 대한 메타러너별 CATE · 처치 · 결과(유지 = 1 − 이탈). **보고만 한다** — 선택 · 튜닝 · 4분면
경계를 이 결과로 바꾸지 않는다(DR-217-uplift-tuning, DR-219-segments 「2부 결정」).

구간은 A/B 분석과 같은 Wald(비합동 표준오차) · 같은 유의수준이고, 칸마다 고객 100명(DR-221 표본 부족 고객 수 기준)이
안 되면 그 칸의 판정을 하지 않는다.
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


def _effect(y: np.ndarray, treated: np.ndarray, mask: np.ndarray) -> dict[str, Any]:
    """고객군(mask) 안 처치 − 대조의 결과 평균 차이와 그 분산. 한쪽이 비면 None."""
    yt, yc = y[mask & treated], y[mask & ~treated]
    out: dict[str, Any] = {"n_treated": int(len(yt)), "n_control": int(len(yc)),
                           "rate_treated": None, "rate_control": None, "effect": None, "var": None}
    if len(yt) and len(yc):
        mt, vt = _mean_and_var(yt)
        mc, vc = _mean_and_var(yc)
        out.update(rate_treated=mt, rate_control=mc, effect=mt - mc, var=vt + vc)
    return out


def _interval(estimate: float, var: float, alpha: float) -> list[float]:
    half = _z(alpha) * math.sqrt(max(var, 0.0))
    return [estimate - half, estimate + half]


def _public(effect: Mapping[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in effect.items() if k != "var"}


def uplift_deciles(test: Mapping[str, Any], method: str, arm: str | None = None,
                   alpha: float | None = None) -> dict[str, Any]:
    """UP-005 — 대표 처치군 CATE 내림차순 10구간의 실측 uplift(처치 − 대조, Wald 95% 구간) · 평균 예측 uplift.

    T0 · 대표 처치군 고객만 쓴다(Qini · 선택과 같은 기준, DR-217). 같은 수로 나누고(순위 기준), 동점은 customer_id 순서다.
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
        enough = eff["n_treated"] >= 2 and eff["n_control"] >= 2
        rows.append({"decile": rank, "n": int(len(part)), **_public(eff),
                     "uplift_ci95": _interval(eff["effect"], eff["var"], alpha) if enough else None,
                     "mean_predicted_uplift": float(part["score"].mean()) if len(part) else None})
    return {"method": method, "arm": arm, "n": int(len(frame)),
            "n_excluded_unscored": int((t.isin([CONTROL, arm]) & score.isna()).sum()), "alpha": alpha,
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


def quadrant_validation(test: Mapping[str, Any], method: str, thresholds: Mapping[str, float] | None = None,
                        alpha: float | None = None) -> dict[str, Any]:
    """H-SEG-2 평가(DR-219-segments 「2부 결정」의 규칙 그대로) — 결과를 보고 규칙을 바꾸지 않는다."""
    alpha = _alpha(alpha)
    floor = _min_cell()
    cfg = {**DEFAULT_THRESHOLDS, **(thresholds or {})}
    t = test["treatment"]
    y = test["y"].astype(float).reindex(t.index).to_numpy()
    u = uplift_score(test["cate"][method]).reindex(t.index).astype(float)
    valid = u.notna().to_numpy()
    band = float(u[valid].abs().quantile(cfg["uplift_band_q"])) if valid.any() else None
    treated = (t != CONTROL).to_numpy()
    hyp = dict(SEGMENT_HYPOTHESES[1])
    if band is None:
        return {**hyp, "result": "undetermined", "evidence": {"reason": "test 분할에 CATE 가 없다", "method": method}}
    pers = valid & (u.to_numpy() > band)
    sleeping = valid & (u.to_numpy() < -band)
    rest = valid & ~pers
    eff_p, eff_r, eff_sd = _effect(y, treated, pers), _effect(y, treated, rest), _effect(y, treated, sleeping)
    cells = {"persuadables_treated": eff_p["n_treated"], "persuadables_control": eff_p["n_control"],
             "rest_treated": eff_r["n_treated"], "rest_control": eff_r["n_control"]}
    evidence: dict[str, Any] = {"method": method, "uplift_band_q": cfg["uplift_band_q"], "uplift_band": band,
                                "alpha": alpha, "min_cell": floor, "cells": cells,
                                "persuadables": _public(eff_p), "rest": _public(eff_r)}
    sd_cells_ok = min(eff_sd["n_treated"], eff_sd["n_control"]) >= floor
    if sd_cells_ok:
        sd_ci = _interval(eff_sd["effect"], eff_sd["var"], alpha)
        evidence["sleeping_dogs"] = {**_public(eff_sd), "ci95": sd_ci,
                                     "result": "contradicted" if sd_ci[0] > 0 else "not_contradicted"}
    else:
        evidence["sleeping_dogs"] = {**_public(eff_sd), "ci95": None, "result": "undetermined",
                                     "reason": f"처치 · 대조 중 {floor}명 미만인 칸이 있다"}
    if min(cells.values()) < floor:
        small = [k for k, v in cells.items() if v < floor]
        evidence["reason"] = f"{floor}명 미만인 칸: {', '.join(small)}"
        return {**hyp, "result": "undetermined", "evidence": evidence}
    diff = eff_p["effect"] - eff_r["effect"]
    ci = _interval(diff, eff_p["var"] + eff_r["var"], alpha)
    evidence.update(diff=diff, ci95=ci, persuadables_result="supported" if ci[0] > 0 else "not_supported")
    contradicted = evidence["sleeping_dogs"]["result"] == "contradicted"
    result = "supported" if ci[0] > 0 and not contradicted else "not_supported"
    return {**hyp, "result": result, "evidence": evidence}


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
