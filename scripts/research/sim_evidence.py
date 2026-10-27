"""시뮬레이터 이탈·퍼널 기제 증거 (#183 ⑥) — 실현 로그만으로 잰다.

닫힌 #78·#79 가 요구한 증거 다섯 가지를 한 번에 낸다.

1. 창 연속 이탈률(래칫) — 30일 간격 여러 T0 의 라벨 이탈률이 띠 안에서 안정한가, T0 가 늦을수록 오르는가.
2. 이력 길이별 위험도 — 직전 구매 횟수·가입 경과일 구간별 이탈률이 다른가(긴 이력 ≠ 짧은 이력).
3. 회복 사례 — 42일 이상 공백 뒤 다시 산 고객의 수·공백 분포·예시.
4. `days_since_last_purchase` 단일 변수 설명력 — 구간별 이탈률과 AUC(#79: 너무 높으면 기제가 단순하다).
5. 퍼널 단계별 전환 — 세션 → 상품 조회 → 담기 → 결제 시작 → 구매, 외부 벤치마크와 나란히.

★ 시뮬레이터 정답 데이터의 **단일 변수** 설명력이다. 모델 성능이 아니며 `results/`·모델 리포트를 읽지 않는다.
  AUC 를 근거로 시뮬레이터를 고칠지는 사람이 정한다(사용자 결정 2026-10-28, DR-183).

모집단·라벨은 `realism_check.f12` 와 같다 — data_spec §4.1 eligible(T0 − 가입일 ≥ 60일 ∧ T0 이전 구매 ≥ 1 ∧
마지막 구매 ≥ 14일 전), 라벨 = (T0, T0+42일] 무구매, 비-T0 처치 고객 제외.

사용
    python scripts/research/sim_evidence.py --events <sink_root> --exchange <dir> --assignments <json> \
        --out-json evidence.json --out-md evidence.md
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

_HERE = Path(__file__).resolve().parent
_spec = importlib.util.spec_from_file_location("realism_check", _HERE / "realism_check.py")
rc = importlib.util.module_from_spec(_spec)
sys.modules["realism_check"] = rc  # dataclass 가 모듈을 찾는다
_spec.loader.exec_module(rc)

CHURN_DAYS = rc.CHURN_DAYS
DSL_BINS = [14, 21, 28, 42, 60, 90, 10_000]
ORDER_BINS = [1, 2, 5, 10, 10_000]
TENURE_BINS = [60, 120, 240, 10_000]
STRATA_BINS = [14, 42, 90, 10_000]
# data_grounding.md §2.5 — 비교용. 판정하지 않는다(세션 정의가 §3-4 에서 미정).
FUNNEL_BENCHMARKS = {
    "session_to_add_to_cart_pct": "6.04%(전 업종) · F&B 11~13%",
    "cart_abandonment_pct": "식료품 50.03% · 전 업종 70.22%",
    "session_to_purchase_pct": "F&B 4.56% · 전 업종 2.68%",
}


def _t0s(ctx) -> list[pd.Timestamp]:
    """`realism_check.f12` 와 같은 T0 — 관측 시작 + 56일부터 30일 간격, 라벨 창 42일이 관측 안에 끝나는 것까지."""
    out, t0 = [], ctx.start + pd.Timedelta(days=56)
    while t0 <= ctx.end - pd.Timedelta(days=CHURN_DAYS):
        out.append(t0)
        t0 += pd.Timedelta(days=30)
    return out


def _untreated_orders(ctx) -> pd.DataFrame:
    o = ctx.orders
    if ctx.assignments is not None and len(ctx.assignments):
        treated = set(ctx.assignments.loc[ctx.assignments["treatment_id"] != "T0", "customer_id"])
        o = o[~o["customer_id"].isin(treated)]
    return o


def _panel(ctx) -> pd.DataFrame:
    """T0 × §4.1 eligible 고객 행. 열: T0 · customer_id · dsl · prior_orders · tenure · observed_signup · churned.

    `observed_signup` = 관측 시작 뒤 가입(시뮬레이터의 관측 중 가입 고객 — 재구매 게이트 대상).
    """
    o = _untreated_orders(ctx)
    signup, _ = rc._signup_dates(ctx)
    rows = []
    for t0 in _t0s(ctx):
        t0_ts = pd.Timestamp(t0).tz_localize(rc.TZ)
        before = o[o["date"] < t0]
        g = before.groupby("customer_id")["date"]
        last, count = g.max(), g.size()
        dsl = (t0 - last).dt.days
        tenure = (t0 - signup.reindex(last.index)).dt.days
        eligible = last.index[(tenure >= 60) & (dsl >= 14)]
        post = set(o[(o["timestamp"] > t0_ts) & (o["timestamp"] <= t0_ts + pd.Timedelta(days=CHURN_DAYS))]["customer_id"])
        rows.append(pd.DataFrame({
            "T0": str(t0.date()), "customer_id": eligible, "dsl": dsl.loc[eligible].to_numpy(),
            "prior_orders": count.loc[eligible].to_numpy(), "tenure": tenure.loc[eligible].to_numpy(),
            "observed_signup": (signup.reindex(eligible) > ctx.start).to_numpy(),
            "churned": [c not in post for c in eligible],
        }))
    return pd.concat(rows, ignore_index=True) if rows else pd.DataFrame()


def _pct(x: pd.Series) -> float:
    return round(100 * float(x.mean()), 2)


def auc(score: np.ndarray, positive: np.ndarray) -> float | None:
    """Mann–Whitney 순위 AUC — `score` 가 클수록 양성(이탈)일 확률. 동점은 평균 순위."""
    positive = np.asarray(positive, dtype=bool)
    n_pos, n_neg = int(positive.sum()), int((~positive).sum())
    if n_pos == 0 or n_neg == 0:
        return None
    ranks = pd.Series(score).rank(method="average").to_numpy()
    return round(float((ranks[positive].sum() - n_pos * (n_pos + 1) / 2) / (n_pos * n_neg)), 4)


def _series(by: pd.DataFrame) -> dict:
    by = by.dropna(subset=["mean"])  # 모집단이 0명인 T0 는 계열에서 뺀다
    if by.empty:
        return {"by_T0": [], "min_pct": None, "max_pct": None, "slope_pct_per_30d": None, "in_band_15_25": []}
    rates = (100 * by["mean"]).round(2).tolist()
    slope = float(np.polyfit(range(len(rates)), rates, 1)[0]) if len(rates) >= 2 else None
    return {"by_T0": [{"T0": t, "churn_pct": r, "n": int(n)} for t, r, n in zip(by["T0"], rates, by["size"])],
            "min_pct": min(rates), "max_pct": max(rates), "slope_pct_per_30d": round(slope, 3) if slope is not None else None,
            "in_band_15_25": [15 <= r <= 25 for r in rates]}


def _active42(ctx) -> pd.DataFrame:
    """직전 42일 구매 고객의 T0 별 라벨 이탈 — `realism_check.f12` 참고값 `churn_active42_pct` 와 같은 정의.

    모집단 = 마지막 구매가 T0 전 42일 미만(T0 − 41일 ~ T0 − 1일)인 고객, 라벨 = [T0, T0+42일) 날짜에 구매 없음.
    정식 가드레일(`src.simulator guardrails`)과 모집단 이름은 같지만 처치 고객 제외·다중 T0 라 값은 다르다.
    """
    o = _untreated_orders(ctx)
    rows = []
    for t0 in _t0s(ctx):
        recent = set(o[(o["date"] < t0) & (o["date"] > t0 - pd.Timedelta(days=CHURN_DAYS))]["customer_id"])
        post = set(o[(o["date"] >= t0) & (o["date"] < t0 + pd.Timedelta(days=CHURN_DAYS))]["customer_id"])
        rows.append({"T0": str(t0.date()), "mean": (len(recent - post) / len(recent)) if recent else np.nan,
                     "size": len(recent)})
    return pd.DataFrame(rows, columns=["T0", "mean", "size"])


def _stratified(panel: pd.DataFrame) -> list[dict]:
    """경과일 구간을 고정한 T0 별 이탈률과 구간 비중 — 구간 안 이탈률이 평탄하고 비중만 바뀌면 래칫이 아니라 구성 효과다."""
    cut = pd.cut(panel["dsl"], bins=STRATA_BINS, right=False)
    rows = []
    for (t0, bucket), g in panel.groupby(["T0", cut], observed=True)["churned"]:
        rows.append({"T0": t0, "dsl_bucket": str(bucket), "churn_pct": _pct(g), "n": int(len(g)),
                     "share_pct": round(100 * len(g) / int((panel["T0"] == t0).sum()), 1)})
    return rows


def decompose(panel: pd.DataFrame) -> dict | None:
    """첫 T0 → 마지막 T0 이탈률 변화를 경과일 구간 안 변화(첫 T0 비중으로 가중)와 나머지(구간 비중 변화)로 나눈다."""
    t0s = sorted(panel["T0"].unique())
    if len(t0s) < 2:
        return None
    cut = pd.cut(panel["dsl"], bins=STRATA_BINS, right=False)

    def parts(t0):
        mask = panel["T0"] == t0
        return panel[mask].groupby(cut[mask], observed=True)["churned"].mean(), cut[mask].value_counts(normalize=True)

    (r0, s0), (r1, _) = parts(t0s[0]), parts(t0s[-1])
    total = 100 * (panel.loc[panel["T0"] == t0s[-1], "churned"].mean() - panel.loc[panel["T0"] == t0s[0], "churned"].mean())
    within = 100 * sum((r1[k] - r0[k]) * s0[k] for k in r0.index if k in r1.index)
    return {"from_T0": t0s[0], "to_T0": t0s[-1], "total_pp": round(float(total), 2),
            "within_bucket_pp": round(float(within), 2), "composition_pp": round(float(total - within), 2)}


def _by_signup(panel: pd.DataFrame) -> list[dict]:
    """경과일 구간 × 관측 중 가입 여부 — 구간 안 상승이 어느 고객군에서 오는지."""
    cut = pd.cut(panel["dsl"], bins=STRATA_BINS, right=False)
    return [{"T0": t0, "dsl_bucket": str(b), "observed_signup": bool(new), "churn_pct": _pct(g), "n": int(len(g))}
            for (t0, b, new), g in panel.groupby(["T0", cut, "observed_signup"], observed=True)["churned"]]


def ratchet(panel: pd.DataFrame, ctx) -> dict:
    """정본 §4.1 eligible 계열 · 가드레일 모집단 계열 · 경과일 층화·분해 — 오르는 원인이 hazard 누적인지 구성인지 가른다."""
    spec41 = panel.groupby("T0")["churned"].agg(["mean", "size"]).reset_index()
    return {"spec41_eligible": _series(spec41), "active42": _series(_active42(ctx)),
            "spec41_by_dsl": _stratified(panel), "decomposition": decompose(panel),
            "spec41_by_dsl_and_signup": _by_signup(panel)}


def by_history(panel: pd.DataFrame) -> dict:
    out = {}
    for name, col, bins in (("prior_orders", "prior_orders", ORDER_BINS), ("tenure_days", "tenure", TENURE_BINS)):
        cut = pd.cut(panel[col], bins=bins, right=False)
        g = panel.groupby(cut, observed=True)["churned"]
        out[name] = [{"bucket": str(b), "churn_pct": _pct(s), "n": int(len(s))} for b, s in g]
    return out


def single_variable(panel: pd.DataFrame) -> dict:
    cut = pd.cut(panel["dsl"], bins=DSL_BINS, right=False)
    table = [{"dsl_bucket": str(b), "churn_pct": _pct(s), "n": int(len(s))}
             for b, s in panel.groupby(cut, observed=True)["churned"]]
    per_t0 = {t: auc(g["dsl"].to_numpy(), g["churned"].to_numpy()) for t, g in panel.groupby("T0")}
    return {"pooled_auc": auc(panel["dsl"].to_numpy(), panel["churned"].to_numpy()),
            "auc_by_T0": per_t0, "churn_by_dsl": table}


def recovery(ctx, examples: int = 5) -> dict:
    """42일+ 공백 뒤 재구매 — 처치 고객을 **포함한** 전체 구매 고객 기준(F13 과 같다). 처치 회복 가산이 섞인다."""
    gaps = rc.order_gaps(ctx.orders, distinct_days=True)
    long = gaps[gaps["gap"] >= CHURN_DAYS]
    buyers = ctx.orders["customer_id"].nunique()
    sample = long.sort_values(["gap", "customer_id"], ascending=[False, True]).head(examples)
    return {"customers_returned_after_42d_gap": int(long["customer_id"].nunique()), "buyers": int(buyers),
            "share_pct": round(100 * long["customer_id"].nunique() / buyers, 2) if buyers else None,
            "gap_days_median": float(long["gap"].median()) if len(long) else None,
            "gap_days_p90": float(long["gap"].quantile(.9)) if len(long) else None,
            "examples": [{"customer_id": r.customer_id, "returned_on": str(r.date.date()), "gap_days": int(r.gap)}
                         for r in sample.itertuples()]}


def funnel(ctx) -> dict:
    ev = ctx.ev[ctx.ev["session_id"].notna()]
    stages = ["session_start", "product_view", "add_to_cart", "checkout_start", "purchase"]
    sessions = {s: set(ev.loc[ev["event_type"] == s, "session_id"]) for s in stages}
    base = len(set(ev["session_id"]))
    rows, prev = [], base
    for s in stages[1:]:
        n = len(sessions[s])
        rows.append({"stage": s, "sessions": n, "from_session_pct": round(100 * n / base, 2) if base else None,
                     "from_previous_pct": round(100 * n / prev, 2) if prev else None})
        prev = n
    atc = sessions["add_to_cart"]
    return {"sessions": base, "stages": rows,
            "cart_abandonment_pct": round(100 * (1 - len(atc & sessions["purchase"]) / len(atc)), 2) if atc else None,
            "benchmarks": FUNNEL_BENCHMARKS}


def build(ctx) -> dict:
    if not _t0s(ctx):
        return {"error": f"관측 {ctx.span_days}일 — 사전 창 56일 + 라벨 창 42일이 안 된다"}
    panel = _panel(ctx)
    if panel.empty:
        return {"error": "어느 T0 에도 §4.1 eligible 고객이 없다 — 처치 고객 제외 뒤 가입 60일·마지막 구매 14일 전 조건을 채운 고객이 0명"}
    return {"population": "data_spec §4.1 eligible · 라벨 (T0, T0+42] 무구매 · 30일 간격 T0 · 비-T0 처치 제외 (회복 절은 전체 구매 고객)",
            "n_rows": int(len(panel)), "ratchet": ratchet(panel, ctx), "history": by_history(panel),
            "single_variable_dsl": single_variable(panel), "recovery": recovery(ctx), "funnel": funnel(ctx)}


def render_md(report: dict) -> str:
    if "error" in report:
        return f"# 시뮬레이터 기제 증거\n\n{report['error']}\n"
    r, h, s, rec, f = (report[k] for k in ("ratchet", "history", "single_variable_dsl", "recovery", "funnel"))
    lines = ["# 시뮬레이터 기제 증거 (#183 ⑥)", "", f"모집단: {report['population']} · 행 {report['n_rows']:,}", "",
             "## 1. 창 연속 이탈률", "", "| T0 | §4.1 eligible % | n | 직전 42일 구매 고객 % | n |", "|---|---|---|---|---|"]
    a, b = r["spec41_eligible"], r["active42"]
    # 두 계열의 T0 집합이 다를 수 있다(§4.1 eligible 이 0명인 이른 T0 는 빠진다) — T0 로 맞춘다.
    left, right = ({x["T0"]: x for x in s["by_T0"]} for s in (a, b))
    cell = lambda row: f"{row['churn_pct']} | {row['n']:,}" if row else "— | —"
    lines += [f"| {t} | {cell(left.get(t))} | {cell(right.get(t))} |" for t in sorted(set(left) | set(right))]
    lines += ["", f"§4.1 eligible 범위 {a['min_pct']}~{a['max_pct']}% · 기울기 {a['slope_pct_per_30d']}%p/30일 · "
              f"직전 42일 구매 고객 범위 {b['min_pct']}~{b['max_pct']}% · 기울기 {b['slope_pct_per_30d']}%p/30일", "",
              "경과일 구간 고정(§4.1 eligible) — 이탈률 % (구간 비중 %)", ""]
    strata = sorted({x["dsl_bucket"] for x in r["spec41_by_dsl"]}, key=lambda v: int(v[1:].split(",")[0]))
    cells = {(x["T0"], x["dsl_bucket"]): f"{x['churn_pct']} ({x['share_pct']})" for x in r["spec41_by_dsl"]}
    lines += ["| T0 | " + " | ".join(strata) + " |", "|---" * (len(strata) + 1) + "|"]
    lines += [f"| {t['T0']} | " + " | ".join(cells.get((t["T0"], k), "—") for k in strata) + " |" for t in a["by_T0"]]
    d = r["decomposition"]
    if d:
        lines += ["", f"분해({d['from_T0']} → {d['to_T0']}): 전체 {d['total_pp']}%p = 구간 안 {d['within_bucket_pp']}%p "
                  f"+ 구간 비중 {d['composition_pp']}%p", ""]
    lines += ["경과일 구간 × 관측 중 가입 — 이탈률 % (n)", "", "| T0 | 구간 | 기존 고객 | 관측 중 가입 |", "|---|---|---|---|"]
    split = {(x["T0"], x["dsl_bucket"], x["observed_signup"]): f"{x['churn_pct']} ({x['n']:,})" for x in r["spec41_by_dsl_and_signup"]}
    for t in a["by_T0"]:
        for k in strata:
            lines.append(f"| {t['T0']} | {k} | {split.get((t['T0'], k, False), '—')} | {split.get((t['T0'], k, True), '—')} |")
    lines += ["", "## 2. 이력 길이별 이탈률", ""]
    for name, rows in h.items():
        lines += [f"**{name}**", "", "| 구간 | 이탈률 % | n |", "|---|---|---|"]
        lines += [f"| {x['bucket']} | {x['churn_pct']} | {x['n']:,} |" for x in rows] + [""]
    lines += ["## 3. 회복 사례", "",
              f"42일+ 공백 뒤 재구매 고객 {rec['customers_returned_after_42d_gap']:,}명 / 구매 고객 {rec['buyers']:,}명 "
              f"({rec['share_pct']}%) · 공백 중앙 {rec['gap_days_median']}일 · p90 {rec['gap_days_p90']}일", ""]
    lines += [f"- {x['customer_id']} — {x['returned_on']} 복귀, 공백 {x['gap_days']}일" for x in rec["examples"]]
    lines += ["", "## 4. days_since_last_purchase 단일 변수 설명력", "",
              f"합산 AUC {s['pooled_auc']} (T0 별: " + ", ".join(f"{k} {v}" for k, v in s["auc_by_T0"].items()) + ")", "",
              "| 경과일 구간 | 이탈률 % | n |", "|---|---|---|"]
    lines += [f"| {x['dsl_bucket']} | {x['churn_pct']} | {x['n']:,} |" for x in s["churn_by_dsl"]]
    lines += ["", "## 5. 퍼널", "", f"세션 {f['sessions']:,} · 장바구니 이탈 {f['cart_abandonment_pct']}%", "",
              "| 단계 | 세션 | 세션 대비 % | 직전 단계 대비 % |", "|---|---|---|---|"]
    lines += [f"| {x['stage']} | {x['sessions']:,} | {x['from_session_pct']} | {x['from_previous_pct']} |" for x in f["stages"]]
    lines += ["", "외부 비교(판정 안 함): " + " · ".join(f"{k} {v}" for k, v in f["benchmarks"].items()), ""]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--events", required=True)
    ap.add_argument("--exchange")
    ap.add_argument("--assignments")
    ap.add_argument("--out-json")
    ap.add_argument("--out-md")
    args = ap.parse_args(argv)
    ctx = rc.build_context(rc.load_events(args.events), exchange=rc.load_exchange(args.exchange),
                           assignments=rc.load_assignments(args.assignments))
    report = build(ctx)
    if args.out_json:
        Path(args.out_json).write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
    md = render_md(report)
    if args.out_md:
        Path(args.out_md).write_text(md, encoding="utf-8")
    print(md)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
