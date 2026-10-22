#!/usr/bin/env python3
"""compute_reference_stats.py — 공개 실데이터셋 기준 통계(stylized facts) 계산.

사용 예 (다운로드 폴더 밖에서, -I 로 실행):
  python -I compute_reference_stats.py \
      --uci        <online_retail_II.xlsx 또는 변환 캐시 .parquet> \
      --hillstrom  <hillstorm_no_indices.csv.gz> \
      --lenta      <lenta_dataset.csv.gz> \
      --x5-dir     <uplift_train.csv.gz, clients.csv.gz, purchases.csv.gz 가 있는 폴더> \
      --cache-dir  <중간 캐시 폴더> \
      --out-dir    <산출 폴더>

산출:
  <out-dir>/reference_stats.json
  <out-dir>/reference_stats.md
  <out-dir>/uplift_benchmarks/{hillstrom,lenta,x5}.parquet

모든 수치는 입력 파일에서 계산된 값이다(하드코딩된 수치 없음).
"""
from __future__ import annotations

import argparse
import warnings
import datetime as dt
import json
import math
import time
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats

warnings.simplefilter("ignore", pd.errors.PerformanceWarning)

QS = [0.05, 0.10, 0.25, 0.50, 0.75, 0.90, 0.95, 0.99]
Z95 = stats.norm.ppf(0.975)
MIN_ARM_N = 200  # 세그먼트 ATE 계산 시 처치/통제 각각 최소 표본

# UCI: 상품이 아닌 관리/수수료/조정 코드 (배송비 POST/DOT/C2 는 주문금액의 일부로 보고 유지)
UCI_ADMIN_CODES = {"AMAZONFEE", "BANK CHARGES", "B", "M", "m", "ADJUST", "ADJUST2",
                   "TEST001", "TEST002", "CRUK", "D", "S"}


# ----------------------------------------------------------------------------- helpers
_T0 = time.time()


def stamp(msg):
    print(f"  [{time.time() - _T0:7.1f}s] {msg}", flush=True)


def r(x, nd=4):
    if x is None:
        return None
    x = float(x)
    if not np.isfinite(x):
        return None
    return round(x, nd)


def M(value, unit, definition, n=None, **extra):
    d = {"value": value, "unit": unit, "definition": definition}
    if n is not None:
        d["n"] = int(n)
    d.update(extra)
    return d


def qdict(x):
    x = np.asarray(x, float)
    d = {"mean": r(x.mean()), "std": r(x.std(ddof=1)) if len(x) > 1 else None}
    for q in QS:
        d[f"p{int(round(q * 100)):02d}"] = r(np.quantile(x, q))
    d["max"] = r(x.max())
    return d


def gini(x):
    x = np.sort(np.asarray(x, float))
    n = len(x)
    if n == 0 or x.sum() <= 0:
        return None
    cum = np.cumsum(x)
    return (n + 1 - 2 * (cum.sum() / cum[-1])) / n


def top_share(x, p):
    x = np.sort(np.asarray(x, float))[::-1]
    k = max(1, int(math.ceil(p * len(x))))
    return x[:k].sum() / x.sum()


def fit_dists(x):
    """양수 표본에 lognormal / gamma (loc=0) MLE 적합 + KS 적합도."""
    x = np.asarray(x, float)
    x = x[x > 0]
    s, _, scale = stats.lognorm.fit(x, floc=0)
    ks_ln = stats.kstest(x, "lognorm", args=(s, 0, scale))
    a, _, th = stats.gamma.fit(x, floc=0)
    ks_g = stats.kstest(x, "gamma", args=(a, 0, th))
    return {
        "n": int(len(x)),
        "lognormal": {"mu": r(math.log(scale)), "sigma": r(s), "implied_median": r(scale),
                      "implied_mean": r(scale * math.exp(s * s / 2)),
                      "ks_D": r(ks_ln.statistic), "ks_p": float(ks_ln.pvalue)},
        "gamma": {"shape_k": r(a), "scale_theta": r(th), "implied_mean": r(a * th),
                  "ks_D": r(ks_g.statistic), "ks_p": float(ks_g.pvalue)},
        "better_fit_by_ks_D": "lognormal" if ks_ln.statistic < ks_g.statistic else "gamma",
        "note": "MLE(loc=0 고정). 표본이 크면 KS p값은 거의 항상 ~0 이므로 D 통계량으로 상대 비교.",
    }


# ----------------------------------------------------------------------------- transaction stats
def transaction_stats(orders: pd.DataFrame, *, currency: str, churn_L=(30, 90), churn_N=(30, 60, 90),
                      t_step_days=14, order_def: str):
    """orders: 1행=1주문, 열 customer_id, ts(datetime64), value(float, >0)."""
    out = {}
    orders = orders.copy()
    orders["customer_id"] = pd.factorize(orders["customer_id"])[0]  # 정수 코드화(문자열 ID의 np.isin 성능 문제 회피)
    orders["date"] = orders["ts"].dt.normalize()
    start, end = orders["date"].min(), orders["date"].max()
    n_cust = orders["customer_id"].nunique()
    out["window"] = {"start": str(start.date()), "end": str(end.date()),
                     "days": int((end - start).days) + 1, "n_customers": int(n_cust),
                     "n_orders": int(len(orders)), "order_definition": order_def, "currency": currency}

    stamp('1) 고객당')
    # 1) 고객당 주문 수 / 재구매율
    opc = orders.groupby("customer_id").size()
    out["orders_per_customer"] = M(qdict(opc), "orders/customer",
                                   "관측창 전체 고객별 주문 수(주문 1건 이상 고객 대상)", n=n_cust)
    out["repeat_customer_rate"] = M(r((opc >= 2).mean()), "share",
                                    "관측창 내 주문 2건 이상 고객 비율", n=n_cust)
    out["share_customers_ge_k_orders"] = M({f"ge_{k}": r((opc >= k).mean()) for k in (2, 3, 5, 10, 20)},
                                           "share", "주문 k건 이상 고객 비율", n=n_cust)
    days = orders[["customer_id", "date"]].drop_duplicates().sort_values(["customer_id", "date"])
    dpc = days.groupby("customer_id").size()
    out["purchase_days_per_customer"] = M(qdict(dpc), "distinct purchase days/customer",
                                          "고객별 구매 발생 '일' 수(같은 날 복수 주문은 1회)", n=n_cust)
    out["repeat_customer_rate_by_days"] = M(r((dpc >= 2).mean()), "share",
                                            "서로 다른 2일 이상 구매 고객 비율", n=n_cust)

    stamp('2) 구매 간격')
    # 2) 구매 간격
    gaps = days.groupby("customer_id")["date"].diff().dt.days.dropna().to_numpy()
    out["inter_purchase_days"] = M(qdict(gaps), "days",
                                   "같은 고객의 연속된 서로 다른 구매일 간 간격(일, 정수 ≥1). 관측창 우측 절단 존재",
                                   n=len(gaps), n_customers=int((dpc >= 2).sum()), fits=fit_dists(gaps))
    cust_med_gap = days.assign(g=days.groupby("customer_id")["date"].diff().dt.days) \
        .dropna().groupby("customer_id")["g"].median()
    out["customer_median_inter_purchase_days"] = M(qdict(cust_med_gap), "days",
                                                   "고객별 구매간격 중앙값의 분포(2일 이상 구매 고객)",
                                                   n=len(cust_med_gap))

    stamp('3) 주문 금액')
    # 3) 주문 금액
    v = orders["value"].to_numpy(float)
    out["order_value"] = M(qdict(v), currency, "주문(1건) 금액 분포", n=len(v), fits=fit_dists(v))
    cust_aov = orders.groupby("customer_id")["value"].mean()
    out["customer_mean_order_value"] = M(qdict(cust_aov), currency, "고객별 평균 주문금액(AOV)의 분포",
                                         n=len(cust_aov))

    stamp('4) 매출 집중도')
    # 4) 매출 집중도
    rev = orders.groupby("customer_id")["value"].sum().to_numpy(float)
    out["revenue_concentration"] = M({"top1pct_share": r(top_share(rev, .01)),
                                      "top10pct_share": r(top_share(rev, .10)),
                                      "top20pct_share": r(top_share(rev, .20)),
                                      "gini": r(gini(rev))},
                                     "share / gini", "관측창 내 고객별 총매출 기준", n=len(rev))

    stamp('5a)')
    # 5a) 관측 마지막 시점 기준 무구매(recency) 비율
    last = days.groupby("customer_id")["date"].max()
    rec = (end - last).dt.days
    out["recency_at_end"] = M(qdict(rec), "days", "관측 마지막 날 - 고객 마지막 구매일", n=len(rec))
    out["inactive_share_at_end"] = M({f"no_purchase_gt_{k}d": r((rec > k).mean()) for k in (30, 60, 90)},
                                     "share", "관측 마지막 날 기준 마지막 구매가 k일 초과 경과한 고객 비율(전체 구매고객 분모)",
                                     n=len(rec))

    stamp('5b)')
    # 5b) 시점 T 기준 forward churn
    fwd = {}
    for L in churn_L:
        for N in churn_N:
            t0, t1 = start + pd.Timedelta(days=L - 1), end - pd.Timedelta(days=N)
            if t0 > t1:
                continue
            Ts = pd.date_range(t0, t1, freq=f"{t_step_days}D")
            if Ts[-1] != t1:
                Ts = Ts.append(pd.DatetimeIndex([t1]))
            rows = []
            for T in Ts:
                act = days.loc[(days["date"] > T - pd.Timedelta(days=L)) & (days["date"] <= T), "customer_id"].unique()
                fut = days.loc[(days["date"] > T) & (days["date"] <= T + pd.Timedelta(days=N)), "customer_id"].unique()
                rows.append({"T": str(T.date()), "n_active": int(len(act)),
                             "churn": r(1 - np.isin(act, fut).mean())})
            ch = np.array([x["churn"] for x in rows])
            fwd[f"L{L}_N{N}"] = {"lookback_days": L, "horizon_days": N,
                                 "mean": r(ch.mean()), "min": r(ch.min()), "max": r(ch.max()),
                                 "latest_T": rows[-1], "n_T": len(rows), "per_T": rows}
    out["forward_churn"] = M(fwd, "share",
                             "시점 T에 (T-L, T] 구매가 있던 활성 고객 중 (T, T+N] 무구매 비율. T는 t_step 간격 격자, 요약은 T 평균",
                             t_step_days=t_step_days)

    stamp('6) 구매')
    # 6) 구매(방문) 빈도: 완전한 달/주 단위
    o = orders.assign(month=orders["date"].dt.to_period("M"), week=orders["date"].dt.to_period("W-SUN"))
    full_m = [p for p in o["month"].unique() if p.start_time >= start and p.end_time.normalize() <= end]
    full_w = [p for p in o["week"].unique() if p.start_time >= start and p.end_time.normalize() <= end]
    om = o[o["month"].isin(full_m)]
    m_days = om[["customer_id", "month", "date"]].drop_duplicates().groupby(["month", "customer_id"]).size()
    ow = o[o["week"].isin(full_w)]
    w_days = ow[["customer_id", "week", "date"]].drop_duplicates().groupby(["week", "customer_id"]).size()
    # 월간 재방문(월 m 구매자 중 월 m+1 구매 비율)
    bym = {p: set(g) for p, g in om.groupby("month")["customer_id"]}
    ms = sorted(bym)
    m2m = [len(bym[a] & bym[b]) / len(bym[a]) for a, b in zip(ms[:-1], ms[1:]) if (b - a).n == 1]
    out["purchase_frequency"] = M({
        "purchase_days_per_buyer_per_month": qdict(m_days.to_numpy()),
        "purchase_days_per_buyer_per_week": qdict(w_days.to_numpy()) if len(w_days) else None,
        "month_to_month_repurchase_rate_mean": r(np.mean(m2m)) if m2m else None,
        "n_full_months": len(full_m), "n_full_weeks": len(full_w),
    }, "days/buyer, share",
        "방문 로그가 없어 '구매일 수'로 대리. 해당 기간 구매자(1일 이상) 대상 월/주별 구매일 수 분포(고객×기간 단위 관측치). "
        "month_to_month = 월 m 구매자 중 월 m+1에도 구매한 비율의 평균", n=int(len(m_days)))
    return out


# ----------------------------------------------------------------------------- uplift helpers
def ate(y, t, binary=True):
    y = np.asarray(y, float)
    t = np.asarray(t).astype(bool)
    y1, y0 = y[t], y[~t]
    n1, n0 = len(y1), len(y0)
    m1, m0 = y1.mean(), y0.mean()
    if binary:
        se = math.sqrt(m1 * (1 - m1) / n1 + m0 * (1 - m0) / n0)
    else:
        se = math.sqrt(y1.var(ddof=1) / n1 + y0.var(ddof=1) / n0)
    d = m1 - m0
    p = 2 * stats.norm.sf(abs(d / se)) if se > 0 else float("nan")
    k = 100.0 if binary else 1.0
    return {"n_treat": n1, "n_control": n0, "mean_treat": r(m1, 6), "mean_control": r(m0, 6),
            ("ate_pp" if binary else "ate"): r(d * k, 4),
            ("ci95_pp" if binary else "ci95"): [r((d - Z95 * se) * k, 4), r((d + Z95 * se) * k, 4)],
            "p_value": float(p), "relative_lift": r(d / m0, 4) if m0 > 0 else None}


def segment_ates(df, tcol, ycol, seg_cols, binary=True):
    rows = []
    for c in seg_cols:
        for lvl, g in df.groupby(c, observed=True, dropna=False):
            nt, nc = int(g[tcol].sum()), int((1 - g[tcol]).sum())
            if nt < MIN_ARM_N or nc < MIN_ARM_N:
                continue
            a = ate(g[ycol], g[tcol], binary)
            rows.append({"variable": c, "level": str(lvl), **a})
    if rows:
        q = stats.false_discovery_control([x["p_value"] for x in rows], method="bh")
        for x, qq in zip(rows, q):
            x["q_value_bh"] = float(qq)
    key = "ate_pp" if binary else "ate"
    ci = "ci95_pp" if binary else "ci95"
    neg = [x for x in rows if x[key] < 0]
    neg_sig = [x for x in neg if x[ci][1] < 0]
    neg_bh = [x for x in neg if x["q_value_bh"] < 0.05]
    worst = min(rows, key=lambda x: x[key]) if rows else None
    return {"n_segments": len(rows), "n_negative_point": len(neg), "n_negative_ci_excludes_0": len(neg_sig),
            "n_negative_bh_q_lt_0.05": len(neg_bh), "most_negative": worst,
            "negative_segments": sorted(neg, key=lambda x: x[key]), "all": rows,
            "note": f"단일 변수 세그먼트, 처치/통제 각 {MIN_ARM_N}명 이상만. q_value_bh = 같은 패밀리 내 BH 보정"}


def segment_ates_pairs(df, tcol, ycol, seg_cols, binary=True):
    """2변수 교차 세그먼트(모든 변수쌍). 한 패밀리로 BH 보정."""
    import itertools
    d = df[[tcol, ycol]].copy()
    names = []
    for a_, b_ in itertools.combinations(seg_cols, 2):
        nm = f"{a_}×{b_}"
        d[nm] = df[a_].astype(str) + " & " + df[b_].astype(str)
        names.append(nm)
    res = segment_ates(d, tcol, ycol, names, binary)
    res["note"] = res["note"] + " (2변수 교차, 모든 변수쌍)"
    res.pop("all")  # 크기 절감: 음수 세그먼트만 보존
    return res


def qbin(s, q=4, label="Q"):
    s = pd.to_numeric(s, errors="coerce")
    try:
        b = pd.qcut(s, q, duplicates="drop")
    except ValueError:
        return s.astype(str)
    return b.astype(str).where(s.notna(), "missing")


# ----------------------------------------------------------------------------- UCI
def load_uci(path: Path, cache_dir: Path):
    if path.suffix == ".parquet":
        raw = pd.read_parquet(path)
    else:
        cache = cache_dir / "uci_online_retail_ii.parquet"
        if cache.exists():
            raw = pd.read_parquet(cache)
        else:
            sheets = pd.read_excel(path, sheet_name=None, engine="openpyxl",
                                   dtype={"Invoice": str, "StockCode": str, "Description": str, "Country": str})
            raw = pd.concat([d.assign(sheet=n) for n, d in sheets.items()], ignore_index=True)
            raw.to_parquet(cache, index=False)
    return raw


def run_uci(path: Path, cache_dir: Path):
    raw = load_uci(path, cache_dir)
    log = {"raw_rows": int(len(raw))}
    raw["Invoice"] = raw["Invoice"].astype(str)
    raw["StockCode"] = raw["StockCode"].astype(str)
    s1, s2 = sorted(raw["sheet"].unique())
    # 두 시트는 2010-12-01~12-09 구간이 겹친다 → 시트2에 있는 송장은 시트1에서 제거
    inv2 = set(raw.loc[raw["sheet"] == s2, "Invoice"])
    ov = (raw["sheet"] == s1) & raw["Invoice"].isin(inv2)
    log["overlap_rows_removed_from_sheet1"] = int(ov.sum())
    df = raw[~ov].copy()
    log["rows_after_overlap"] = int(len(df))
    df = df[df["Customer ID"].notna()]
    log["rows_with_customer_id"] = int(len(df))
    df["cid"] = df["Customer ID"].astype(int)
    df["line_value"] = df["Quantity"] * df["Price"]
    admin = df["StockCode"].isin(UCI_ADMIN_CODES) | df["StockCode"].str.startswith(("gift_", "TEST"))
    # 순매출(취소 차감) — 매출 집중도 보조지표용
    net = df[~admin].groupby("cid")["line_value"].sum().clip(lower=0)
    is_cancel = df["Invoice"].str.startswith("C")
    log["cancel_rows_removed"] = int(is_cancel.sum())
    log["admin_code_rows_removed"] = int((admin & ~is_cancel).sum())
    clean = df[~is_cancel & ~admin & (df["Quantity"] > 0) & (df["Price"] > 0)]
    log["clean_rows"] = int(len(clean))
    orders = clean.groupby("Invoice").agg(customer_id=("cid", "first"), ts=("InvoiceDate", "min"),
                                          value=("line_value", "sum"), country=("Country", "first"),
                                          n_lines=("StockCode", "size")).reset_index()
    log["orders"] = int(len(orders))
    out = {"cleaning": log}
    out["transactions_full_window"] = transaction_stats(
        orders, currency="GBP", t_step_days=30,
        order_def="송장(Invoice) 1건 = 주문 1건. 취소(C*)·수량≤0·단가≤0·관리코드 제외, 고객ID 결측 제외. 금액=Σ수량×단가(GBP, 배송비 라인 포함)")
    # 12개월 고정창 고객당 주문수
    w = orders[(orders["ts"] >= "2010-12-01") & (orders["ts"] < "2011-12-01")]
    opc = w.groupby("customer_id").size()
    out["orders_per_customer_12m"] = M(qdict(opc), "orders/customer",
                                       "2010-12-01~2011-11-30 12개월 창, 해당 창 구매 고객 대상", n=len(opc),
                                       repeat_customer_rate=r((opc >= 2).mean()))
    out["revenue_concentration_net"] = M({"top10pct_share": r(top_share(net[net > 0], .1)),
                                          "top20pct_share": r(top_share(net[net > 0], .2)),
                                          "gini": r(gini(net[net > 0]))}, "share / gini",
                                         "취소를 차감한 고객별 순매출(>0 고객) 기준", n=int((net > 0).sum()))
    cust_country = orders.groupby("customer_id")["country"].first()
    out["customer_country_mix"] = M({k: r(v) for k, v in cust_country.value_counts(normalize=True).head(5).items()},
                                    "share", "고객별 첫 주문 국가 상위 5개 비중", n=len(cust_country))
    return out


# ----------------------------------------------------------------------------- Hillstrom
def run_hillstrom(path: Path, bench_dir: Path):
    df = pd.read_csv(path)
    df["treatment"] = (df["segment"] != "No E-Mail").astype("int8")
    df["treatment_arm"] = df["segment"].map({"Mens E-Mail": "mens", "Womens E-Mail": "womens", "No E-Mail": "control"})
    df["recency_bin"] = pd.cut(df["recency"], [0, 3, 6, 9, 12], labels=["1-3", "4-6", "7-9", "10-12"]).astype(str)
    df["history_quartile"] = qbin(df["history"])
    df["purchased_mens_womens"] = np.select([(df.mens == 1) & (df.womens == 1), df.mens == 1, df.womens == 1],
                                            ["both", "mens_only", "womens_only"], "neither")
    out = {"n_rows": int(len(df)), "arms": df["segment"].value_counts().to_dict(), "overall": {}, "segments": {}}
    arms = {"any_email": df,
            "mens_email": df[df["segment"].isin(["Mens E-Mail", "No E-Mail"])],
            "womens_email": df[df["segment"].isin(["Womens E-Mail", "No E-Mail"])]}
    segs = ["history_segment", "history_quartile", "recency_bin", "purchased_mens_womens", "newbie", "channel", "zip_code"]
    for an, d in arms.items():
        out["overall"][an] = {"visit": ate(d["visit"], d["treatment"]),
                              "conversion": ate(d["conversion"], d["treatment"]),
                              "spend_usd": ate(d["spend"], d["treatment"], binary=False)}
        out["segments"][an] = {"visit": segment_ates(d, "treatment", "visit", segs),
                               "conversion": segment_ates(d, "treatment", "conversion", segs)}
        out["segments_2way"] = out.get("segments_2way", {})
        out["segments_2way"][an] = {"visit": segment_ates_pairs(d, "treatment", "visit", segs),
                                    "conversion": segment_ates_pairs(d, "treatment", "conversion", segs)}
    cols = ["recency", "history_segment", "history", "mens", "womens", "zip_code", "newbie", "channel",
            "segment", "treatment_arm", "treatment", "visit", "conversion", "spend"]
    df[cols].to_parquet(bench_dir / "hillstrom.parquet", index=False)
    return out


# ----------------------------------------------------------------------------- Lenta
def run_lenta(path: Path, bench_dir: Path):
    df = pd.read_csv(path)
    n_raw = len(df)
    df["treatment"] = (df["group"] == "test").astype("int8")
    df["gender"] = df["gender"].map({"Ж": "F", "М": "M"}).fillna("unknown")
    df = df.drop(columns=["group"])
    df["age_bin"] = pd.cut(df["age"], [0, 25, 35, 45, 55, 65, 200], right=False,
                           labels=["<25", "25-34", "35-44", "45-54", "55-64", "65+"]).astype(str)
    df["children_bin"] = pd.cut(df["children"], [-1, 0, 1, 2, 1e9], labels=["0", "1", "2", "3+"]).astype(str)
    df["months_from_register_q"] = qbin(df["months_from_register"])
    df["response_sms_pos"] = (df["response_sms"].fillna(0) > 0).map({True: "past_sms_response>0", False: "0_or_missing"})
    df["response_viber_pos"] = (df["response_viber"].fillna(0) > 0).map({True: "past_viber_response>0", False: "0_or_missing"})
    chq12 = [c for c in df.columns if c.startswith("cheque_count_12m_g")]
    df["activity_12m_q"] = qbin(df[chq12].sum(axis=1))
    df["crazy_12m_pos"] = (df["crazy_purchases_cheque_count_12m"].fillna(0) > 0).map({True: ">0", False: "0_or_missing"})
    df["main_format_s"] = df["main_format"].astype("Int64").astype(str)
    segs = ["gender", "age_bin", "children_bin", "main_format_s", "months_from_register_q", "response_sms_pos",
            "response_viber_pos", "activity_12m_q", "crazy_12m_pos"]
    out = {"n_rows": int(n_raw), "overall": {"response_att": ate(df["response_att"], df["treatment"])},
           "segments": {"response_att": segment_ates(df, "treatment", "response_att", segs)},
           "segments_2way": {"response_att": segment_ates_pairs(df, "treatment", "response_att", segs)},
           "segment_definitions": {
               "activity_12m_q": "cheque_count_12m_g* (상품군별 12개월 영수증 수) 합의 사분위 — 상품군 중복 포함이므로 총 영수증 수가 아님",
               "months_from_register_q": "가입 후 경과 개월 사분위"}}
    derived = ["age_bin", "children_bin", "main_format_s", "months_from_register_q", "response_sms_pos", "response_viber_pos",
               "activity_12m_q", "crazy_12m_pos"]
    keep = [c for c in df.columns if c not in derived]
    df[keep].to_parquet(bench_dir / "lenta.parquet", index=False)
    return out


# ----------------------------------------------------------------------------- X5
def x5_transactions(x5_dir: Path, cache_dir: Path):
    cache = cache_dir / "x5_transactions.parquet"
    if not cache.exists():
        import duckdb
        con = duckdb.connect()
        src = (x5_dir / "purchases.csv.gz").as_posix()
        con.execute(f"""COPY (SELECT client_id, transaction_id, min(CAST(transaction_datetime AS TIMESTAMP)) AS ts,
            max(purchase_sum) AS purchase_sum, any_value(store_id) AS store_id, count(*) AS n_lines,
            sum(product_quantity) AS n_items, max(regular_points_spent) AS regular_points_spent,
            max(express_points_spent) AS express_points_spent, max(express_points_received) AS express_points_received
            FROM read_csv('{src}', header=true, auto_detect=true) GROUP BY client_id, transaction_id)
            TO '{cache.as_posix()}' (FORMAT PARQUET)""")
    return pd.read_parquet(cache)


def run_x5(x5_dir: Path, cache_dir: Path, bench_dir: Path):
    tx = x5_transactions(x5_dir, cache_dir)
    log = {"transactions": int(len(tx)), "nonpositive_purchase_sum": int((tx["purchase_sum"] <= 0).sum())}
    orders = tx.loc[tx["purchase_sum"] > 0, ["client_id", "ts", "purchase_sum"]].rename(
        columns={"client_id": "customer_id", "purchase_sum": "value"})
    out = {"cleaning": log}
    last = tx.groupby("client_id")["ts"].max()
    out["sample_selection_check"] = M({"min_last_purchase": str(last.min()), "max_ts": str(tx["ts"].max()),
                                       "max_recency_days": int((tx["ts"].max().normalize() - last.min().normalize()).days)},
                                      "date / days", "고객별 마지막 구매일의 최솟값 — 모든 고객이 관측 종료 직전에 구매했는지 확인",
                                      n=len(last))
    out["transactions"] = transaction_stats(
        orders, currency="RUB", churn_L=(30,), churn_N=(30, 60), t_step_days=7,
        order_def="transaction_id 1건 = 주문(장보기 1회). 금액 = purchase_sum(RUB), purchase_sum≤0 제외. 캠페인 이전 구매 이력")
    out["transactions"]["caveat"] = ("표본 선택 편향: 모든 고객이 관측 종료 전 {}일 이내에 구매(마지막 구매일 최솟값 {}). "
                                     "따라서 inactive_share_at_end·forward_churn·repeat_customer_rate 는 구조적으로 0/과소(또는 과대) 추정되어 "
                                     "이탈 기준값으로 사용 불가. 구매간격·주문금액·빈도·집중도만 참고(긴 간격은 과소대표)."
                                     ).format(out["sample_selection_check"]["value"]["max_recency_days"],
                                              out["sample_selection_check"]["value"]["min_last_purchase"])

    # 처치 효과 + 벤치마크
    train = pd.read_csv(x5_dir / "uplift_train.csv.gz")
    clients = pd.read_csv(x5_dir / "clients.csv.gz", parse_dates=["first_issue_date", "first_redeem_date"])
    ref = tx["ts"].max().normalize() + pd.Timedelta(days=1)
    g = tx.assign(date=tx["ts"].dt.normalize()).groupby("client_id")
    feat = pd.DataFrame({
        "n_tx": g.size(),
        "n_purchase_days": g["date"].nunique(),
        "total_sum": g["purchase_sum"].sum(),
        "mean_basket": g["purchase_sum"].mean(),
        "median_basket": g["purchase_sum"].median(),
        "recency_days": (ref - g["ts"].max()).dt.days,
        "tenure_days": (ref - g["ts"].min()).dt.days,
        "n_stores": g["store_id"].nunique(),
        "mean_items_per_tx": g["n_items"].mean(),
        "regular_points_spent_sum": g["regular_points_spent"].sum(),
        "express_points_spent_sum": g["express_points_spent"].sum(),
        "express_points_received_sum": g["express_points_received"].sum(),
    }).reset_index()
    d = train.merge(clients, on="client_id", how="left").merge(feat, on="client_id", how="left")
    d["first_issue_days"] = (ref - d["first_issue_date"]).dt.days
    d["first_redeem_days"] = (ref - d["first_redeem_date"]).dt.days
    d["redeemed_ever"] = d["first_redeem_date"].notna().astype("int8")
    d["age_valid"] = d["age"].between(14, 100)
    d["age_bin"] = pd.cut(d["age"].where(d["age_valid"]), [0, 25, 35, 45, 55, 65, 200], right=False,
                          labels=["<25", "25-34", "35-44", "45-54", "55-64", "65+"]).astype(str).replace("nan", "invalid")
    d["n_tx_q"] = qbin(d["n_tx"])
    d["mean_basket_q"] = qbin(d["mean_basket"])
    d["recency_bin"] = pd.cut(d["recency_days"], [0, 7, 14, 30, 60, 1e9], right=False,
                              labels=["<7", "7-13", "14-29", "30-59", "60+"]).astype(str)
    d["redeemed_ever_s"] = d["redeemed_ever"].map({1: "redeemed", 0: "never_redeemed"})
    segs = ["gender", "age_bin", "redeemed_ever_s", "n_tx_q", "mean_basket_q", "recency_bin"]
    d = d.rename(columns={"treatment_flg": "treatment"})
    out["treatment"] = {"n_rows": int(len(d)), "overall": {"target": ate(d["target"], d["treatment"])},
                        "segments": {"target": segment_ates(d, "treatment", "target", segs)},
                        "segments_2way": {"target": segment_ates_pairs(d, "treatment", "target", segs)}}
    cols = ["client_id", "age", "gender", "first_issue_days", "first_redeem_days", "redeemed_ever"] + \
           [c for c in feat.columns if c != "client_id"] + ["treatment", "target"]
    d[cols].to_parquet(bench_dir / "x5.parquet", index=False)
    return out


# ----------------------------------------------------------------------------- markdown
def fmt(x, nd=2, pct=False):
    if x is None:
        return "—"
    return f"{x * 100:.{nd}f}%" if pct else f"{x:,.{nd}f}"


def tx_table(name, t):
    w = t["window"]
    opc, ipt, ov = t["orders_per_customer"]["value"], t["inter_purchase_days"], t["order_value"]
    rc = t["revenue_concentration"]["value"]
    ina = t["inactive_share_at_end"]["value"]
    fl, fg = ipt["fits"]["lognormal"], ipt["fits"]["gamma"]
    ol = ov["fits"]["lognormal"]
    pf = t["purchase_frequency"]["value"]
    cur = w["currency"]
    L = [f"#### {name} — 관측창 {w['start']}~{w['end']} ({w['days']}일), 고객 {w['n_customers']:,}명, 주문 {w['n_orders']:,}건\n",
         "| 지표 | 값 | 정의/비고 |", "|---|---|---|",
         f"| 고객당 주문 수 평균 / 중앙 / p75 / p90 / p99 | {fmt(opc['mean'])} / {fmt(opc['p50'],0)} / {fmt(opc['p75'],0)} / {fmt(opc['p90'],0)} / {fmt(opc['p99'],0)} | 관측창 전체 |",
         f"| 재구매 고객 비율(주문 ≥2) | {fmt(t['repeat_customer_rate']['value'], 1, True)} | 서로 다른 2일 이상 기준: {fmt(t['repeat_customer_rate_by_days']['value'], 1, True)} |",
         f"| 구매 간격 중앙 / p25 / p75 / p90 (일) | {fmt(ipt['value']['p50'],0)} / {fmt(ipt['value']['p25'],0)} / {fmt(ipt['value']['p75'],0)} / {fmt(ipt['value']['p90'],0)} | 연속 구매일 간격, n={ipt['n']:,} |",
         f"| 구매 간격 lognormal 적합 | μ={fmt(fl['mu'],3)}, σ={fmt(fl['sigma'],3)}, KS D={fmt(fl['ks_D'],3)} | MLE, loc=0 |",
         f"| 구매 간격 gamma 적합 | k={fmt(fg['shape_k'],3)}, θ={fmt(fg['scale_theta'],2)}, KS D={fmt(fg['ks_D'],3)} | 더 나은 적합(KS D): {ipt['fits']['better_fit_by_ks_D']} |",
         f"| 주문금액 중앙 / 평균 ({cur}) | {fmt(ov['value']['p50'])} / {fmt(ov['value']['mean'])} | p10={fmt(ov['value']['p10'])}, p90={fmt(ov['value']['p90'])} |",
         f"| 주문금액 lognormal σ (μ) | {fmt(ol['sigma'],3)} ({fmt(ol['mu'],3)}) | KS D={fmt(ol['ks_D'],3)} |",
         f"| 매출 상위 10% / 20% 고객 비중 | {fmt(rc['top10pct_share'],1,True)} / {fmt(rc['top20pct_share'],1,True)} | 상위 1%: {fmt(rc['top1pct_share'],1,True)} |",
         f"| 고객 매출 지니계수 | {fmt(rc['gini'],3)} | |",
         f"| 관측 종료일 기준 무구매 >30 / >60 / >90일 | {fmt(ina['no_purchase_gt_30d'],1,True)} / {fmt(ina['no_purchase_gt_60d'],1,True)} / {fmt(ina['no_purchase_gt_90d'],1,True)} | 분모=관측창 내 전체 구매고객 |"]
    for k, v in t["forward_churn"]["value"].items():
        L.append(f"| forward churn {k} (T 평균 [최소~최대]) | {fmt(v['mean'],1,True)} [{fmt(v['min'],1,True)}~{fmt(v['max'],1,True)}] | "
                 f"최근 T={v['latest_T']['T']}: {fmt(v['latest_T']['churn'],1,True)} (활성 {v['latest_T']['n_active']:,}명), T {v['n_T']}개 |")
    pm, pw = pf["purchase_days_per_buyer_per_month"], pf["purchase_days_per_buyer_per_week"]
    L.append(f"| 월간 구매일 수(해당 월 구매자) 평균 / 중앙 | {fmt(pm['mean'])} / {fmt(pm['p50'],0)} | 완전한 달 {pf['n_full_months']}개 |")
    if pw:
        L.append(f"| 주간 구매일 수(해당 주 구매자) 평균 / 중앙 | {fmt(pw['mean'])} / {fmt(pw['p50'],0)} | 완전한 주 {pf['n_full_weeks']}개 |")
    L.append(f"| 월 m 구매자의 m+1월 재구매율(평균) | {fmt(pf['month_to_month_repurchase_rate_mean'],1,True)} | |")
    if t.get("caveat"):
        L.append(f"\n> ⚠️ {t['caveat']}")
    return "\n".join(L) + "\n"


def ate_row(label, a, binary=True):
    if binary:
        return (f"| {label} | {a['n_treat']:,} / {a['n_control']:,} | {fmt(a['mean_treat'],2,True)} / {fmt(a['mean_control'],2,True)} | "
                f"{a['ate_pp']:+.3f} [{a['ci95_pp'][0]:+.3f}, {a['ci95_pp'][1]:+.3f}] | {fmt(a['relative_lift'],1,True)} |")
    return (f"| {label} | {a['n_treat']:,} / {a['n_control']:,} | {a['mean_treat']:.3f} / {a['mean_control']:.3f} | "
            f"{a['ate']:+.4f} [{a['ci95'][0]:+.4f}, {a['ci95'][1]:+.4f}] (USD) | {fmt(a['relative_lift'],1,True)} |")


def seg_summary_rows(label, s):
    w = s["most_negative"]
    ws = f"{w['variable']}={w['level']}: {w['ate_pp']:+.3f}%p [{w['ci95_pp'][0]:+.3f}, {w['ci95_pp'][1]:+.3f}]" if w else "—"
    return f"| {label} | {s['n_segments']} | {s['n_negative_point']} | {s['n_negative_ci_excludes_0']} | {s['n_negative_bh_q_lt_0.05']} | {ws} |"


def write_md(res, path: Path):
    D = res["datasets"]
    L = ["# 공개 실데이터 기준 통계 (Reference stylized facts)\n",
         f"생성: {res['meta']['generated_at']} · 스크립트: `scripts/compute_reference_stats.py` · 모든 수치는 스크립트 실측값(JSON과 동일).\n",
         "## 1. 거래 데이터 stylized facts\n"]
    if "uci_online_retail_ii" in D:
        u = D["uci_online_retail_ii"]
        L.append(tx_table("UCI Online Retail II (영국 온라인 소매, GBP)", u["transactions_full_window"]))
        o12 = u["orders_per_customer_12m"]
        rn = u["revenue_concentration_net"]["value"]
        L.append(f"- 12개월 고정창(2010-12-01~2011-11-30) 고객당 주문 수: 평균 {fmt(o12['value']['mean'])}, 중앙 {fmt(o12['value']['p50'],0)}, "
                 f"재구매율 {fmt(o12['repeat_customer_rate'],1,True)} (n={o12['n']:,})")
        L.append(f"- 취소 차감 순매출 기준 집중도: 상위10% {fmt(rn['top10pct_share'],1,True)}, 상위20% {fmt(rn['top20pct_share'],1,True)}, 지니 {fmt(rn['gini'],3)}")
        L.append(f"- 고객 국가 구성(상위): " + ", ".join(f"{k} {fmt(v,1,True)}" for k, v in u["customer_country_mix"]["value"].items()))
        L.append(f"- 정제 로그: `{json.dumps(u['cleaning'], ensure_ascii=False)}`\n")
    if "x5_retailhero" in D and "transactions" in D["x5_retailhero"]:
        x = D["x5_retailhero"]
        L.append(tx_table("X5 RetailHero 구매 이력 (러시아 오프라인 식료품, RUB)", x["transactions"]))
        L.append(f"- 정제 로그: `{json.dumps(x['cleaning'], ensure_ascii=False)}`\n")

    L.append("## 2. 처치(캠페인) 효과 — 전체 ATE\n")
    L.append("ATE = 처치군 평균 − 통제군 평균, 95% CI = Wald(비율)/Welch(금액) 정규근사. 상대 lift = ATE/통제군 평균.\n")
    L.append("| 데이터셋 · 처치 · 결과 | n 처치 / 통제 | 반응률 처치 / 통제 | ATE %p [95% CI] | 상대 lift |")
    L.append("|---|---|---|---|---|")
    if "hillstrom" in D:
        for an, oo in D["hillstrom"]["overall"].items():
            L.append(ate_row(f"Hillstrom · {an} · visit", oo["visit"]))
            L.append(ate_row(f"Hillstrom · {an} · conversion", oo["conversion"]))
            L.append(ate_row(f"Hillstrom · {an} · spend", oo["spend_usd"], binary=False))
    if "lenta" in D:
        L.append(ate_row("Lenta · SMS · response_att", D["lenta"]["overall"]["response_att"]))
    if "x5_retailhero" in D and "treatment" in D["x5_retailhero"]:
        L.append(ate_row("X5 · SMS(treatment_flg) · target(구매)", D["x5_retailhero"]["treatment"]["overall"]["target"]))
    L.append("")
    L.append("## 3. 세그먼트별 ATE — 음수 세그먼트(Sleeping Dog 근거)\n")
    L.append("| 데이터셋 · 처치 · 결과 | 세그먼트 수 | ATE<0 (점추정) | ATE<0 & 95%CI 상한<0 | ATE<0 & BH q<0.05 | 가장 음수인 세그먼트 |")
    L.append("|---|---|---|---|---|---|")
    if "hillstrom" in D:
        for an, ss in D["hillstrom"]["segments"].items():
            for y, s in ss.items():
                L.append(seg_summary_rows(f"Hillstrom · {an} · {y}", s))
    if "lenta" in D:
        L.append(seg_summary_rows("Lenta · SMS · response_att", D["lenta"]["segments"]["response_att"]))
    if "x5_retailhero" in D and "treatment" in D["x5_retailhero"]:
        L.append(seg_summary_rows("X5 · SMS · target", D["x5_retailhero"]["treatment"]["segments"]["target"]))
    fams = []
    if "hillstrom" in D:
        for an, ss in D["hillstrom"]["segments_2way"].items():
            for y, s in ss.items():
                fams.append((f"Hillstrom · {an} · {y} (2변수 교차)", s))
    if "lenta" in D:
        fams.append(("Lenta · SMS · response_att (2변수 교차)", D["lenta"]["segments_2way"]["response_att"]))
    if "x5_retailhero" in D and "treatment" in D["x5_retailhero"]:
        fams.append(("X5 · SMS · target (2변수 교차)", D["x5_retailhero"]["treatment"]["segments_2way"]["target"]))
    for lab, s in fams:
        L.append(seg_summary_rows(lab, s))
    L.append("")
    L.append("### 95% CI 상한 < 0 인 음수 ATE 세그먼트 (패밀리별 ATE 오름차순 상위 8개)\n")
    L.append("| 패밀리 | 세그먼트 | n 처치 / 통제 | 반응률 처치 / 통제 | ATE %p [95% CI] | BH q |")
    L.append("|---|---|---|---|---|---|")
    single = []
    if "hillstrom" in D:
        for an, ss in D["hillstrom"]["segments"].items():
            for y, s in ss.items():
                single.append((f"Hillstrom · {an} · {y}", s))
    if "lenta" in D:
        single.append(("Lenta · response_att", D["lenta"]["segments"]["response_att"]))
    if "x5_retailhero" in D and "treatment" in D["x5_retailhero"]:
        single.append(("X5 · target", D["x5_retailhero"]["treatment"]["segments"]["target"]))
    any_row = False
    for lab, s in single + fams:
        sig = [x for x in s["negative_segments"] if x["ci95_pp"][1] < 0][:8]
        for x in sig:
            any_row = True
            L.append(f"| {lab} | {x['variable']} = {x['level']} | {x['n_treat']:,} / {x['n_control']:,} | "
                     f"{fmt(x['mean_treat'],2,True)} / {fmt(x['mean_control'],2,True)} | {x['ate_pp']:+.3f} [{x['ci95_pp'][0]:+.3f}, {x['ci95_pp'][1]:+.3f}] | {x['q_value_bh']:.3f} |")
    if not any_row:
        L.append("| (없음) | | | | | |")
    L.append("")
    path.write_text("\n".join(L) + "\n" + res.get("md_appendix", ""), encoding="utf-8")


# ----------------------------------------------------------------------------- main
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--uci", type=Path)
    ap.add_argument("--hillstrom", type=Path)
    ap.add_argument("--lenta", type=Path)
    ap.add_argument("--x5-dir", type=Path)
    ap.add_argument("--cache-dir", type=Path, required=True)
    ap.add_argument("--out-dir", type=Path, required=True)
    ap.add_argument("--md-appendix", type=Path, help="md 뒤에 붙일 정적 섹션(출처/한계/열 설명)")
    a = ap.parse_args()
    a.cache_dir.mkdir(parents=True, exist_ok=True)
    bench = a.out_dir / "uplift_benchmarks"
    bench.mkdir(parents=True, exist_ok=True)
    res = {"meta": {"generated_at": dt.datetime.now().isoformat(timespec="seconds"),
                    "script": "scripts/compute_reference_stats.py", "min_arm_n_segment": MIN_ARM_N,
                    "quantiles": QS},
           "datasets": {}, "skipped": {}}
    jobs = [("uci_online_retail_ii", a.uci, lambda: run_uci(a.uci, a.cache_dir)),
            ("hillstrom", a.hillstrom, lambda: run_hillstrom(a.hillstrom, bench)),
            ("lenta", a.lenta, lambda: run_lenta(a.lenta, bench)),
            ("x5_retailhero", a.x5_dir, lambda: run_x5(a.x5_dir, a.cache_dir, bench))]
    for name, p, fn in jobs:
        if p is None or not p.exists():
            res["skipped"][name] = "입력 경로 미지정 또는 없음"
            continue
        t = time.time()
        res["datasets"][name] = fn()
        res["datasets"][name]["_runtime_s"] = round(time.time() - t, 1)
        print(f"[ok] {name} {time.time() - t:.1f}s", flush=True)
    (a.out_dir / "reference_stats.json").write_text(json.dumps(res, ensure_ascii=False, indent=1, default=str),
                                                     encoding="utf-8")
    if a.md_appendix and a.md_appendix.exists():
        res["md_appendix"] = a.md_appendix.read_text(encoding="utf-8")
    write_md(res, a.out_dir / "reference_stats.md")
    print("wrote", a.out_dir)


if __name__ == "__main__":
    main()
