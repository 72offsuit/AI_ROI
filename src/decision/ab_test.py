"""가상 A/B 분석 — 이슈 #145 (P1 · SRS AB-001~005 · PRD §56~58).

``analyze_ab(df, arm_col, outcome_col, control="T0")`` 가 다음을 낸다.

* SRM(Sample Ratio Mismatch) — 기대 배정 비율 대비 카이제곱 적합도 검정.
* 처치군별 vs 대조군 — 비율 차, 95% CI(비합동 SE), 두 비율 z-검정(합동 SE), 2×2 카이제곱.
* 다중 비교 — Holm 보정 p-value.
* 검정력 — 관측 효과에서 달성 검정력, 그리고 그 효과를 α·검정력 목표로 검출하는
  군당 최소 표본(정규근사). ``mde`` 를 주면 그 효과 기준으로도 낸다.

결과 종류는 값으로 판정하고 결과 dict 의 ``outcome_kind`` 에 적는다.

* **이진**(값 ⊆ {0,1}: 유지·구매) — 위의 비율 검정.
* **연속**(매출 등) — 평균 차, Welch t-검정과 Welch 자유도 95% CI, 정규근사 검정력·최소 표본.
  매출은 0 이 많고 꼬리가 길어 정규근사가 느리게 수렴한다 — 표본이 작으면 CI 를 믿지 않는다.

결과 결측 행은 제외하고 건수를 남긴다(0 으로 채우지 않는다). scipy 는 함수 안에서 import 한다.
"""

from __future__ import annotations

import math
from typing import Any, Mapping


def _z(q: float) -> float:
    from scipy.stats import norm

    return float(norm.ppf(q))


def sample_size_two_proportions(p_c: float, p_t: float, alpha: float = 0.05, power: float = 0.8) -> int | None:
    """양측 두 비율 검정의 군당 최소 표본(등배정, 정규근사). 효과 0 이면 None(정의 불가)."""
    if p_t == p_c:
        return None
    za, zb = _z(1 - alpha / 2), _z(power)
    pbar = (p_c + p_t) / 2
    num = (za * math.sqrt(2 * pbar * (1 - pbar)) + zb * math.sqrt(p_c * (1 - p_c) + p_t * (1 - p_t))) ** 2
    return int(math.ceil(num / (p_t - p_c) ** 2))


def achieved_power(p_c: float, p_t: float, n_c: int, n_t: int, alpha: float = 0.05) -> float | None:
    """관측된 두 비율·표본에서의 양측 검정력(정규근사)."""
    from scipy.stats import norm

    if n_c <= 0 or n_t <= 0:
        return None
    se = math.sqrt(p_c * (1 - p_c) / n_c + p_t * (1 - p_t) / n_t)
    if se == 0:
        return None
    za = _z(1 - alpha / 2)
    d = abs(p_t - p_c) / se
    return float(norm.cdf(d - za) + norm.cdf(-d - za))


def holm(pvalues: Mapping[str, float | None]) -> dict[str, float | None]:
    """Holm–Bonferroni 보정. None(계산 불가)은 보정 대상에서 빼고 None 으로 둔다."""
    items = sorted(((p, k) for k, p in pvalues.items() if p is not None), key=lambda t: (t[0], t[1]))
    m = len(items)
    out: dict[str, float | None] = {k: None for k in pvalues}
    running = 0.0
    for i, (p, k) in enumerate(items):
        adj = min(1.0, (m - i) * p)
        running = max(running, adj)
        out[k] = running
    return out


def srm_check(counts: Mapping[str, int], expected_ratio: Mapping[str, float] | None = None,
              threshold: float = 0.001) -> dict[str, Any]:
    """SRM 카이제곱 적합도. ``expected_ratio`` 가 없으면 균등 배정을 가정한다(그 사실을 기록)."""
    from scipy.stats import chisquare

    arms = sorted(counts)
    n = sum(counts[a] for a in arms)
    if expected_ratio is None:
        ratio = {a: 1 / len(arms) for a in arms}
        assumed = "equal"
    else:
        tot = sum(expected_ratio[a] for a in arms)
        ratio = {a: expected_ratio[a] / tot for a in arms}
        assumed = "given"
    if len(arms) < 2:
        return {"status": "계산 불가 — 군 1개", "p_value": None}
    stat, p = chisquare([counts[a] for a in arms], [n * ratio[a] for a in arms])
    return {"chi2": float(stat), "p_value": float(p), "expected_ratio": ratio,
            "expected_ratio_source": assumed, "srm_detected": bool(p < threshold),
            "threshold": threshold}


def sample_size_two_means(sd_c: float, sd_t: float, delta: float, alpha: float = 0.05,
                          power: float = 0.8) -> int | None:
    """양측 평균 차 검정의 군당 최소 표본(등배정, 정규근사). 효과 0 이면 None."""
    if delta == 0:
        return None
    za, zb = _z(1 - alpha / 2), _z(power)
    return int(math.ceil((za + zb) ** 2 * (sd_c ** 2 + sd_t ** 2) / delta ** 2))


def _compare_means(y_t, y_c, alpha: float, power: float, mde: float | None) -> dict[str, Any]:
    from scipy.stats import norm, t as tdist

    n_t, n_c = len(y_t), len(y_c)
    if n_t < 2 or n_c < 2:
        return {"n_control": n_c, "n_treatment": n_t, "status": "계산 불가 — 표본 2 미만",
                "diff": None, "ci95": None, "p_value": None}
    m_t, m_c = float(y_t.mean()), float(y_c.mean())
    v_t, v_c = float(y_t.var(ddof=1)), float(y_c.var(ddof=1))
    diff = m_t - m_c
    se = math.sqrt(v_t / n_t + v_c / n_c)
    out: dict[str, Any] = {"n_control": n_c, "n_treatment": n_t, "mean_control": m_c,
                           "mean_treatment": m_t, "diff": diff,
                           "relative_lift": (diff / m_c) if m_c != 0 else None}
    if se == 0:
        out.update({"t": None, "df": None, "p_value": None, "ci95": None, "achieved_power": None,
                    "status": "계산 불가 — 분산 0"})
    else:
        df_w = (v_t / n_t + v_c / n_c) ** 2 / ((v_t / n_t) ** 2 / (n_t - 1) + (v_c / n_c) ** 2 / (n_c - 1))
        tstat = diff / se
        q = float(tdist.ppf(1 - alpha / 2, df_w))
        za = _z(1 - alpha / 2)
        d = abs(diff) / se
        out.update({"t": tstat, "df": df_w, "p_value": float(2 * tdist.sf(abs(tstat), df_w)),
                    "ci95": [diff - q * se, diff + q * se],
                    "achieved_power": float(norm.cdf(d - za) + norm.cdf(-d - za))})
    sd_t, sd_c = math.sqrt(v_t), math.sqrt(v_c)
    out["required_n_per_arm_observed_effect"] = sample_size_two_means(sd_c, sd_t, diff, alpha, power)
    out["required_n_per_arm_mde"] = (sample_size_two_means(sd_c, sd_t, mde, alpha, power)
                                     if mde is not None else None)
    return out


def analyze_ab(df, arm_col: str, outcome_col: str, control: str = "T0", alpha: float = 0.05,
               power: float = 0.8, expected_ratio: Mapping[str, float] | None = None,
               mde: float | None = None) -> dict[str, Any]:
    """처치군 각각을 ``control`` 과 비교한다. ``df`` 는 pandas DataFrame. 이진·연속 결과 모두."""
    from scipy.stats import chi2_contingency, norm

    data = df[[arm_col, outcome_col]]
    n_missing = int(data[outcome_col].isna().sum())
    data = data.dropna(subset=[outcome_col])
    vals = set(data[outcome_col].astype(float).unique())
    binary = vals <= {0.0, 1.0}
    arms_all = sorted(data[arm_col].astype(str).unique())
    if control not in arms_all:
        raise ValueError(f"대조군 {control} 이 없다")
    data = data.assign(_arm=data[arm_col].astype(str), _y=data[outcome_col].astype(float))
    if not binary:
        groups = {a: data.loc[data["_arm"] == a, "_y"].to_numpy() for a in arms_all}
        comps = {a: _compare_means(groups[a], groups[control], alpha, power, mde)
                 for a in arms_all if a != control}
        adj = holm({a: c.get("p_value") for a, c in comps.items()})
        for a in comps:
            comps[a]["p_value_holm"] = adj[a]
            comps[a]["significant_holm"] = (adj[a] < alpha) if adj[a] is not None else None
        counts = {a: int(len(groups[a])) for a in arms_all}
        return {
            "outcome": outcome_col, "outcome_kind": "continuous",
            "n": int(sum(counts.values())), "n_outcome_missing_excluded": n_missing,
            "arms": counts, "control": control, "alpha": alpha, "power_target": power, "mde": mde,
            "srm": srm_check(counts, expected_ratio), "comparisons": comps,
            "test_method": "Welch t-test · 95% CI (Welch df) · Holm adjusted · power by normal approx",
        }
    g = data.groupby("_arm")["_y"]
    n = g.size().to_dict()
    x = g.sum().to_dict()
    rate = {a: x[a] / n[a] for a in n}

    za = _z(1 - alpha / 2)
    comps: dict[str, dict[str, Any]] = {}
    raw_p: dict[str, float | None] = {}
    for a in arms_all:
        if a == control:
            continue
        p_c, p_t, n_c, n_t = rate[control], rate[a], n[control], n[a]
        diff = p_t - p_c
        se_u = math.sqrt(p_c * (1 - p_c) / n_c + p_t * (1 - p_t) / n_t)
        pool = (x[a] + x[control]) / (n_t + n_c)
        se_p = math.sqrt(pool * (1 - pool) * (1 / n_t + 1 / n_c))
        if se_p == 0:
            z, p = None, None
        else:
            z = diff / se_p
            p = float(2 * (1 - norm.cdf(abs(z))))
        table = [[x[a], n_t - x[a]], [x[control], n_c - x[control]]]
        try:
            chi2, p_chi, _, _ = chi2_contingency(table, correction=False)
            chi = {"chi2": float(chi2), "p_value": float(p_chi)}
        except ValueError:
            chi = {"chi2": None, "p_value": None, "status": "계산 불가 — 기대도수 0"}
        raw_p[a] = p
        comps[a] = {
            "n_control": int(n_c), "n_treatment": int(n_t),
            "rate_control": p_c, "rate_treatment": p_t,
            "diff": diff, "ci95": [diff - za * se_u, diff + za * se_u],
            "relative_lift": (diff / p_c) if p_c > 0 else None,
            "z": z, "p_value": p, "chi_square": chi,
            "achieved_power": achieved_power(p_c, p_t, n_c, n_t, alpha),
            "required_n_per_arm_observed_effect": sample_size_two_proportions(p_c, p_t, alpha, power),
            "required_n_per_arm_mde": (sample_size_two_proportions(p_c, min(1.0, max(0.0, p_c + mde)), alpha, power)
                                       if mde is not None else None),
        }
    adj = holm(raw_p)
    for a in comps:
        comps[a]["p_value_holm"] = adj[a]
        comps[a]["significant_holm"] = (adj[a] < alpha) if adj[a] is not None else None
    return {
        "outcome": outcome_col, "outcome_kind": "binary",
        "n": int(sum(n.values())), "n_outcome_missing_excluded": n_missing,
        "arms": {a: int(n[a]) for a in arms_all}, "control": control,
        "alpha": alpha, "power_target": power, "mde": mde,
        "srm": srm_check({a: int(n[a]) for a in arms_all}, expected_ratio),
        "comparisons": comps,
        "test_method": "two-proportion z-test (pooled SE) · 95% CI unpooled · Holm adjusted",
    }
