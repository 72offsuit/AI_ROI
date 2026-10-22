"""생성 데이터 유의미성 검증 — 실현 이벤트 로그 ↔ 외부 stylized fact F1~F17.

`docs/research/data_grounding.md` §4 의 표를 그대로 코드로 옮긴다.

원칙 (§4)
- "유의미하다"를 모수로 증명하지 않는다. **실현 이벤트 로그에서 집계한 값**이 외부
  실데이터의 stylized fact 를 재현하는지로 본다.
- 통과 띠는 §4 표 그대로다. 결과를 본 뒤 바꾸지 않는다 (`BANDS` 는 문서의 사본이다).
- AI 성능 지표(AUC·Qini 등)는 넣지 않는다. `results/`·`src/decision/` 을 읽지 않는다.
- 외부 쪽 집계(`scripts/research/instacart_stats.py`·`cj_stats.py`·`cj_label.py`)와
  **같은 정의**로 우리 로그를 센다 — 정의 차이가 거짓 불일치를 만들지 않게.
- 계산할 수 없으면 `no_data` 와 사유를 남긴다. 0 이나 pass 로 채우지 않는다.

판정
- `pass`       — 띠 안
- `borderline` — 띠 밖이지만 가까운 경계값의 ±20% 이내 (예: 띠 [5, 10] 이면 4 ≤ v < 5, 10 < v ≤ 12)
- `fail`       — 그 밖
- `no_data`    — 로그에 필요한 이벤트·필드가 없다(사유 포함). 항목이 여러 값을 판정하면
                 **모든 값이 계산돼야** 판정한다 — 일부만 재고 pass 라고 말하지 않는다.

입력
- `--events`      Sink 루트 (`<root>/events/date=*/part-*`, parquet · jsonl.gz · jsonl)
- `--exchange`    (선택) 교환 묶음 디렉터리 — `customers`·`orders`·`order_items` (F10·F11)
- `--assignments` (선택) 처치 배정 기록 JSON — `apply_treatment` 를 부른 쪽이 남긴다 (F14·F15·F17)
                  `[{"assigned_at": "<ISO8601+오프셋>", "assignments": {"C00000001": "T3", …}}, …]`
                  없으면 이벤트의 `treatment_id` 태그로 추정하고 그 사실과 한계를 note 에 적는다.
- `--guardrail`   (선택) 시뮬레이터 가드레일 리포트 JSON — ground truth 값 (F16, F14 보조)
                  두 형식을 읽는다. ① 시뮬레이터 `python -m src.simulator guardrails` 출력(만분율):
                  `ate_bp.T3` · `response_mix_bp.T3.{positive,negative}` · `sleeping_dog_bp`.
                  ② 0~1 소수: `ate` · `sleeping_dog_rate` · `persuadable_rate`
                  (최상위 또는 `guardrails`/`metrics` 아래, 값 또는 `{"value": …}`). 키가 없으면 no_data.

사용
    python scripts/research/realism_check.py --events <sink_root> \
        [--exchange <dir>] [--assignments <json>] [--guardrail <json>] \
        --out-json realism.json --out-md realism.md
"""

from __future__ import annotations

import argparse
import gzip
import json
import math
import sys
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable

import numpy as np
import pandas as pd

KST = timezone(timedelta(hours=9))
TZ = "Asia/Seoul"
REPO = Path(__file__).resolve().parents[2]
SOURCES_JSON = REPO / "docs" / "research" / "sources.json"

GAP_CAP_DAYS = 30            # Instacart days_since_prior_order 는 30 에서 절단된다
CHURN_DAYS = 42              # PRD §28 이탈 정의
COUPON_VALID_DAYS = 14       # T3 "유효 14일" (economic_config). T2 는 config 에 유효기간이 없어 같은 값을 쓴다
MONTH_DAYS = 365.25 / 12
BORDERLINE_FRACTION = 0.20

EVENT_COLUMNS = [
    "customer_id", "timestamp", "event_type", "session_id", "order_id",
    "order_amount", "coupon_id", "campaign_id", "treatment_id",
    "treatment_group", "experiment_id", "simulator_version", "random_seed",
]

VERDICTS = ("pass", "borderline", "fail", "no_data")
DASHBOARD_VERDICT = {
    "pass": "consistent",
    "borderline": "deviates",
    "fail": "deviates",
    "no_data": "no_reference",
}


# ── 기준값 — data_grounding.md §4 표의 사본. 결과를 본 뒤 바꾸지 않는다 ─────────────

@dataclass(frozen=True)
class Spec:
    id: str
    name: str
    unit: str
    dataset: str
    reference_value: Any
    sources: tuple[str, ...]
    band_text: str


SPECS: dict[str, Spec] = {s.id: s for s in [
    Spec("F1", "구매 간격 분포 (주문 단위, 30일 절단)", "일", "Instacart 2017",
         {"median": 7, "mean": 11.1, "p75": 15, "share_gap_7": 0.0997},
         ("S01",), "중앙값 5~10 · 평균 9~15 · p75 12~20"),
    Spec("F2", "고객 안 간격 불규칙성 (간격 CV 중앙값)", "CV", "Instacart 2017",
         0.571, ("S01",), "0.45~0.70"),
    Spec("F3", "고객별 평균 구매 주기의 퍼짐", "일 · ln-sd", "Instacart 2017 · Complete Journey · 오픈서베이",
         {"median": 15.0, "ln_sd": {"Instacart": 0.527, "Complete Journey": 0.89}},
         ("S01", "S02", "S20", "S21"), "중앙값 12~18일 · ln-sd 0.5~0.9"),
    Spec("F4", "월 구매 빈도 · 객단가 자릿수", "회/월 · 원", "오픈서베이 2023·2025 (컬리 이용자)",
         {"orders_per_month": [2.5, 2.66], "aov_krw": 44800},
         ("S20", "S21"), "월 2.0~3.2회 · 객단가 38,000~55,000원"),
    Spec("F5", "구매율 이질성 (12주 주문 수 NBD shape)", "Gamma shape", "Complete Journey 2.0",
         {"Complete Journey": 0.82, "Instacart(상한)": 1.72}, ("S02", "S01"), "0.5~1.5"),
    Spec("F6", "Pareto 집중 (매출 상위 고객 비중)", "비율", "Complete Journey 2.0 · Instacart · 문헌",
         {"top20": {"CJ": 0.545, "Instacart(주문)": 0.526, "McCarthy&Winer": 0.67, "KSW": 0.73},
          "top10": {"CJ": 0.350}},
         ("S02", "S01", "S08", "S09"), "상위 20% 0.53~0.73 · 상위 10% 0.33~0.50"),
    Spec("F7", "객단가 분포 (로그정규·오른쪽 꼬리)", "ln-sd · CV", "Complete Journey 2.0",
         {"order_ln_sd($20+)": 0.59, "customer_mean_aov_cv": 0.65}, ("S02",),
         "주문 금액 ln-sd 0.4~0.8 · 고객 평균 객단가 CV 0.5~0.8"),
    Spec("F8", "무료배송 임계값(40,000원) 바로 위 몰림", "밀도비", "Lewis 2006 · Lewis·Singh·Fay 2006 · UPS",
         "방향(> 1). 52% 가 기준을 맞추려 상품 추가", ("S15", "S16", "S14"), "> 1"),
    Spec("F9", "장바구니 이탈률", "%", "Baymard · Stripe(식료품)",
         {"grocery": 50.03, "all": 70.22}, ("S03", "S07", "S04"), "50~75%"),
    Spec("F10", "상품 재주문 비중", "비율", "Instacart 2017", 0.599, ("S01",), "0.50~0.65"),
    Spec("F11", "신규 고객 재구매율 (첫 구매 후 365일 안 2번째 구매)", "비율", "컬리 2019~2021 (보도)",
         {"2019": 0.612, "2020": 0.652, "2021": 0.75}, ("S30",), "0.55~0.75"),
    Spec("F12", "생성 이탈률 (42일 무구매)", "%", "Complete Journey 2.0 (42일 라벨)",
         {"활성 가구 전체": [10.7, 13.1], "최근 구매 14일+ 전": [28.6, 31.8]},
         ("S02",), "가드레일 15~25%"),
    Spec("F13", "일시 공백 뒤 복귀 (42일+ 공백 후 재구매)", "비율", "Complete Journey 2.0",
         {"1년간 42일+ 공백 뒤 복귀 가구": 0.435, "주": "자주 사는 가구 선발 표본이라 상한"},
         ("S02",), "> 0"),
    Spec("F14", "처치 효과 크기 ATE (T3 vs T0, 42일 유지율 차)", "%p", "X5 · Lenta · 통신사 실험",
         {"X5(구매)": 3.32, "통신사(유지)": 5.0, "상대 효과": "+5.5%~+7.4%"},
         ("S43", "S44", "S48"), "3~6%p"),
    Spec("F15", "쿠폰 사용률 (T2·T3 처치군 전체 중 유효기간 내 사용)", "%",
         "Complete Journey 2.0 · NCH/Inmar", {"CJ 캠페인당": 12.0, "외부 범위": [0.6, 16.6]},
         ("S02", "S53"), "5~20%"),
    Spec("F16", "반응 이질성 (Sleeping Dog · Persuadable · 항등식)", "%", "Hillstrom · 통신사 · 항등식",
         {"Sleeping Dog": "10~20%(Hillstrom), ≤25%(통신사)", "항등식": "P − D = ATE"},
         ("S41", "S46", "S47", "S48"), "D 8~15% · P 11~21% · |P − D − ATE| ≤ 0.5%p"),
    Spec("F17", "처치 효과가 쿠폰 사용 밖에서도 생긴다 (증분 매출 중 쿠폰 미사용 몫)", "비율",
         "Sahni·Zou·Chintagunta 2017 · Venkatesan & Farris 2012", {"외부": [0.60, 0.90]},
         ("S51", "S52"), "> 0"),
]}


# ── 판정 ─────────────────────────────────────────────────────────────────────

def judge(value: float | None, lo: float | None, hi: float | None) -> str:
    """띠 [lo, hi] 판정. `None` 경계는 열린 쪽이다. 경계 = 가까운 경계값의 ±20%."""
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return "no_data"
    v = float(value)
    if (lo is None or v >= lo) and (hi is None or v <= hi):
        return "pass"
    if lo is not None and v < lo and v >= lo - BORDERLINE_FRACTION * abs(lo):
        return "borderline"
    if hi is not None and v > hi and v <= hi + BORDERLINE_FRACTION * abs(hi):
        return "borderline"
    return "fail"


def judge_open_lower(value: float | None, lo: float) -> str:
    """`> lo` (lo 자체는 통과가 아니다)."""
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return "no_data"
    v = float(value)
    if v > lo:
        return "pass"
    if lo != 0 and v >= lo - BORDERLINE_FRACTION * abs(lo):
        return "borderline"
    return "fail"


def worst(verdicts: list[str]) -> str:
    """여러 값의 종합. 하나라도 계산 못 했으면 no_data — 일부만 재고 통과라 하지 않는다."""
    if not verdicts or "no_data" in verdicts:
        return "no_data"
    for v in ("fail", "borderline"):
        if v in verdicts:
            return v
    return "pass"


@dataclass
class Result:
    synthetic: Any
    verdict: str
    note: str
    parts: dict[str, str] = field(default_factory=dict)


def no_data(reason: str, synthetic: Any = None) -> Result:
    return Result(synthetic, "no_data", reason)


def _r(x: float | None, nd: int = 3) -> float | None:
    if x is None:
        return None
    x = float(x)
    if math.isnan(x) or math.isinf(x):
        return None
    return round(x, nd)


# ── 입력 ─────────────────────────────────────────────────────────────────────

def _read_part(path: Path) -> pd.DataFrame:
    name = path.name
    if name.endswith(".parquet"):
        import pyarrow.parquet as pq

        schema_names = pq.read_schema(path).names
        cols = [c for c in EVENT_COLUMNS if c in schema_names]
        return pq.read_table(path, columns=cols).to_pandas()
    if name.endswith(".jsonl.gz") or name.endswith(".gz"):
        with gzip.open(path, "rt", encoding="utf-8") as fh:
            rows = [json.loads(line) for line in fh if line.strip()]
    elif name.endswith(".jsonl"):
        with path.open(encoding="utf-8") as fh:
            rows = [json.loads(line) for line in fh if line.strip()]
    else:
        return pd.DataFrame(columns=EVENT_COLUMNS)
    return pd.DataFrame.from_records(rows)


def load_events(root: Path | str) -> pd.DataFrame:
    """Sink 루트의 이벤트 전량. 필요한 열만 남기고 timestamp 를 KST 로 맞춘다."""
    root = Path(root)
    parts = sorted((root / "events").rglob("part-*"))
    frames = [_read_part(p) for p in parts]
    frames = [f for f in frames if len(f)]
    if not frames:
        return normalize_events(pd.DataFrame(columns=EVENT_COLUMNS))
    return normalize_events(pd.concat(frames, ignore_index=True))


def normalize_events(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    for c in EVENT_COLUMNS:
        if c not in df.columns:
            df[c] = None
    df = df[EVENT_COLUMNS]
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True, format="ISO8601").dt.tz_convert(TZ)
    df["order_amount"] = pd.to_numeric(df["order_amount"], errors="coerce")
    df["date"] = df["timestamp"].dt.tz_localize(None).dt.normalize()
    return df.sort_values(["timestamp"], kind="stable").reset_index(drop=True)


def _read_jsonl(path: Path) -> pd.DataFrame | None:
    if not path.exists():
        return None
    with path.open(encoding="utf-8") as fh:
        return pd.DataFrame.from_records([json.loads(l) for l in fh if l.strip()])


def load_exchange(directory: Path | str | None) -> dict[str, pd.DataFrame] | None:
    if directory is None:
        return None
    d = Path(directory)
    if not d.is_dir():
        return None
    out = {}
    for name in ("customers", "orders", "order_items"):
        frame = _read_jsonl(d / f"{name}.jsonl")
        if frame is not None:
            out[name] = frame
    manifest = d / "manifest.json"
    if manifest.exists():
        out["manifest"] = json.loads(manifest.read_text(encoding="utf-8"))
    return out or None


def load_assignments(path: Path | str | None) -> pd.DataFrame | None:
    """`[{"assigned_at": iso, "assignments": {cid: tid}}]` → (customer_id, treatment_id, assigned_at)."""
    if path is None:
        return None
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if isinstance(data, dict):
        data = data.get("batches", [data])
    rows = []
    for batch in data:
        at = pd.Timestamp(batch["assigned_at"]).tz_convert(TZ)
        for cid, tid in batch["assignments"].items():
            rows.append({"customer_id": cid, "treatment_id": tid, "assigned_at": at})
    return pd.DataFrame(rows, columns=["customer_id", "treatment_id", "assigned_at"])


def assignments_from_events(ev: pd.DataFrame) -> pd.DataFrame | None:
    """이벤트 `treatment_id` 태그로 배정을 추정한다.

    배정 시각 = 같은 실험(experiment_id, 없으면 campaign_id)의 태그 이벤트 중 가장 이른 시각.
    ★ 한계: 배정 뒤 아무 이벤트도 남기지 않은 고객(특히 통제군의 침묵 고객)은 빠진다.
    """
    tagged = ev[ev["treatment_id"].notna()]
    if tagged.empty:
        return None
    key = tagged["experiment_id"].fillna(tagged["campaign_id"]).fillna("_single")
    tagged = tagged.assign(_exp=key)
    start = tagged.groupby("_exp")["timestamp"].min().rename("assigned_at")
    pairs = tagged.groupby(["_exp", "customer_id"])["treatment_id"].first().reset_index()
    pairs = pairs.merge(start, left_on="_exp", right_index=True)
    return pairs[["customer_id", "treatment_id", "assigned_at"]]


GUARDRAIL_KEYS = {
    "ate": ("ate", "ATE", "ate_t3"),
    "sleeping_dog_rate": ("sleeping_dog_rate", "sleeping_dog", "sleeping_dogs"),
    "persuadable_rate": ("persuadable_rate", "persuadable", "persuadables"),
}


def _bp_value(guard: dict, name: str) -> float | None:
    """시뮬레이터 `python -m src.simulator guardrails` 출력(만분율 bp) 형식.

    `ate_bp.T3` · `response_mix_bp.T3.{positive,negative}` 를 같은 모집단(활성 고객, T3)의 값으로 읽는다
    — 항등식 P − D = ATE 는 같은 모집단·같은 처치에서만 뜻이 있다.
    """
    def frac(v: object) -> float | None:
        return v / 10_000 if isinstance(v, (int, float)) and not isinstance(v, bool) else None
    if name == "ate" and isinstance(guard.get("ate_bp"), dict):
        return frac(guard["ate_bp"].get("T3"))
    mix = guard.get("response_mix_bp", {}).get("T3") if isinstance(guard.get("response_mix_bp"), dict) else None
    if isinstance(mix, dict):
        if name == "sleeping_dog_rate":
            return frac(mix.get("negative"))
        if name == "persuadable_rate":
            return frac(mix.get("positive"))
    return None


def guardrail_value(guard: dict | None, name: str) -> float | None:
    if not guard:
        return None
    bp = _bp_value(guard, name)
    if bp is not None:
        return bp
    scopes = [guard] + [guard[k] for k in ("guardrails", "metrics", "ground_truth") if isinstance(guard.get(k), dict)]
    for scope in scopes:
        for key in GUARDRAIL_KEYS[name]:
            if key in scope:
                v = scope[key]
                if isinstance(v, dict):
                    v = v.get("value")
                if isinstance(v, (int, float)) and not isinstance(v, bool):
                    return float(v)
    return None


# ── 문맥 ─────────────────────────────────────────────────────────────────────

@dataclass
class Context:
    ev: pd.DataFrame
    orders: pd.DataFrame
    start: pd.Timestamp          # 관측 첫날 (KST 날짜, tz-naive)
    end: pd.Timestamp            # 관측 끝 (배타, 마지막 날 + 1)
    exchange: dict | None = None
    assignments: pd.DataFrame | None = None
    assignment_basis: str = "none"
    guardrail: dict | None = None

    @property
    def span_days(self) -> int:
        return int((self.end - self.start).days)


def build_context(ev: pd.DataFrame, *, exchange=None, assignments=None, guardrail=None) -> Context:
    if "date" not in ev.columns:
        ev = normalize_events(ev)
    purchases = ev[ev["event_type"] == "purchase"].copy()
    has_id = purchases["order_id"].notna()
    purchases = pd.concat([
        purchases[has_id].drop_duplicates("order_id", keep="first"),
        purchases[~has_id],
    ]).sort_values("timestamp", kind="stable")
    orders = purchases[["customer_id", "order_id", "timestamp", "date", "order_amount", "session_id", "coupon_id"]]
    orders = orders.reset_index(drop=True)
    if len(ev):
        start = ev["date"].min()
        end = ev["date"].max() + pd.Timedelta(days=1)
    else:
        start = end = pd.Timestamp("1970-01-01")
    basis = "none"
    if assignments is not None and len(assignments):
        basis = "assignments_file"
    else:
        assignments = assignments_from_events(ev) if len(ev) else None
        if assignments is not None and len(assignments):
            basis = "events_tag"
    return Context(ev, orders, start, end, exchange, assignments, basis, guardrail)


def order_gaps(orders: pd.DataFrame, *, distinct_days: bool = False) -> pd.DataFrame:
    """고객별 연속 주문 간격(달력일). Instacart 는 같은 날 재주문을 0 으로 센다(distinct_days=False).
    Complete Journey 는 장보기 날짜를 중복 제거한 뒤 센다(distinct_days=True)."""
    o = orders[["customer_id", "date"]]
    if distinct_days:
        o = o.drop_duplicates()
    o = o.sort_values(["customer_id", "date"], kind="stable")
    gap = o.groupby("customer_id")["date"].diff().dt.days
    return o.assign(gap=gap)


def _lower_q(values: np.ndarray, p: float) -> float:
    """instacart_stats.py 의 `gaps[int(p*(n-1))]` 와 같은 분위수."""
    s = np.sort(values)
    return float(s[int(p * (len(s) - 1))])


def _first_seen(ctx: Context) -> pd.Series:
    return ctx.ev.groupby("customer_id")["date"].min()


# ── F1~F17 ──────────────────────────────────────────────────────────────────

def f1(ctx: Context) -> Result:
    g = order_gaps(ctx.orders)["gap"].dropna().to_numpy()
    if len(g) == 0:
        return no_data("purchase 이벤트가 없거나 고객당 주문이 1건뿐이라 간격을 잴 수 없다")
    gc = np.minimum(g, GAP_CAP_DAYS)
    med, mean, p75 = _lower_q(gc, .5), float(gc.mean()), _lower_q(gc, .75)
    hist = {k: float((gc == k).mean()) for k in range(0, GAP_CAP_DAYS + 1)}
    peak7 = hist[7] > hist[6] and hist[7] > hist[8]
    parts = {"median": judge(med, 5, 10), "mean": judge(mean, 9, 15), "p75": judge(p75, 12, 20)}
    syn = {
        "median": _r(med, 2), "mean": _r(mean, 2), "p75": _r(p75, 2), "p90": _r(_lower_q(gc, .9), 2),
        "share_gap_7": _r(hist[7], 4), "peak_at_7": bool(peak7),
        "uncapped": {"median": _r(_lower_q(g, .5), 2), "mean": _r(g.mean(), 2), "p95": _r(_lower_q(g, .95), 2)},
        "n_gaps": int(len(g)),
    }
    note = ("Instacart 와 같게 30일에서 절단해 판정한다(절단 전 값은 uncapped). "
            f"7일 피크 {'있음' if peak7 else '없음'}(가점 항목, 판정에 쓰지 않음).")
    return Result(syn, worst(list(parts.values())), note, parts)


def f2(ctx: Context) -> Result:
    gaps = order_gaps(ctx.orders).dropna(subset=["gap"])
    gaps = gaps.assign(gap=np.minimum(gaps["gap"], GAP_CAP_DAYS))
    grp = gaps.groupby("customer_id")["gap"]
    stats = pd.DataFrame({"n": grp.size(), "mu": grp.mean(), "sd": grp.std(ddof=0)})
    stats = stats[(stats["n"] >= 5) & (stats["mu"] > 0)]
    if stats.empty:
        return no_data("간격 5개 이상(주문 6회 이상)인 고객이 없다 — Instacart 집계와 같은 표본 조건")
    cv = np.sort((stats["sd"] / stats["mu"]).to_numpy())
    med = float(cv[len(cv) // 2])
    return Result({"median_cv": _r(med), "n_customers": int(len(cv))}, judge(med, 0.45, 0.70),
                  "간격 5개 이상 고객의 고객 안 간격 CV(모표준편차/평균) 중앙값. 30일 절단(Instacart 와 같음). "
                  "지수분포면 1.0, 시계면 0.")


def f3(ctx: Context) -> Result:
    gaps = order_gaps(ctx.orders).dropna(subset=["gap"])
    if gaps.empty:
        return no_data("간격을 잴 주문이 없다")
    def summarize(series: pd.Series) -> tuple[float, float, int] | None:
        grp = series.groupby(gaps["customer_id"])
        um = grp.mean()[grp.size() >= 3].to_numpy()
        if len(um) == 0:
            return None
        s = np.sort(um)
        lnsd = float(np.std(np.log(np.maximum(s, 0.5))))
        return float(s[int(.5 * len(s))]), lnsd, int(len(s))
    capped = summarize(np.minimum(gaps["gap"], GAP_CAP_DAYS))
    raw = summarize(gaps["gap"])
    if capped is None:
        return no_data("간격 3개 이상인 고객이 없다 — Instacart 집계와 같은 표본 조건")
    med, lnsd, n = capped
    parts = {"median": judge(med, 12, 18), "ln_sd": judge(lnsd, 0.5, 0.9)}
    syn = {"median": _r(med, 2), "ln_sd": _r(lnsd), "n_customers": n,
           "uncapped": {"median": _r(raw[0], 2), "ln_sd": _r(raw[1])} if raw else None}
    return Result(syn, worst(list(parts.values())), "간격 3개 이상 고객의 고객별 평균 간격(30일 절단, Instacart 정의). "
                  "절단 전 값은 uncapped(Complete Journey 0.89 는 절단 없음).", parts)


def f4(ctx: Context) -> Result:
    o = ctx.orders
    if o.empty:
        return no_data("purchase 이벤트가 없다")
    amounts = o["order_amount"].dropna()
    first = _first_seen(ctx)
    exposure_start = first.clip(lower=ctx.start)
    exposure = (ctx.end - exposure_start).dt.days
    counts = o.groupby("customer_id").size()
    active = counts.index[counts.index.isin(exposure.index)]
    exp = exposure.loc[active]
    keep = exp >= 28
    rate = (counts.loc[active][keep] * MONTH_DAYS / exp[keep])
    if rate.empty:
        return no_data("관측 노출 28일 이상인 구매 고객이 없다", {"aov_mean_krw": _r(amounts.mean(), 0) if len(amounts) else None})
    if amounts.empty:
        return no_data("purchase 의 order_amount 가 비어 있다", {"orders_per_month": _r(rate.mean(), 2)})
    opm, aov = float(rate.mean()), float(amounts.mean())
    parts = {"orders_per_month": judge(opm, 2.0, 3.2), "aov_krw": judge(aov, 38000, 55000)}
    syn = {"orders_per_month": _r(opm, 2), "orders_per_month_median": _r(rate.median(), 2),
           "aov_krw": _r(aov, 0), "aov_median_krw": _r(amounts.median(), 0),
           "n_customers": int(len(rate)), "n_orders": int(len(amounts))}
    return Result(syn, worst(list(parts.values())), "구매 고객(1회 이상)의 월 주문 수 = 주문 수 ÷ 노출 기간(첫 이벤트~관측 끝, 28일 미만 제외) × 30.44일. "
                  "객단가는 purchase.order_amount(할인 후·배송비 제외) 평균.", parts)


def f5(ctx: Context) -> Result:
    if ctx.span_days < 84:
        return no_data(f"관측 기간 {ctx.span_days}일 < 12주(84일)")
    o = ctx.orders
    if o.empty:
        return no_data("purchase 이벤트가 없다")
    w0 = ctx.end - pd.Timedelta(days=84)
    first = _first_seen(ctx)
    buyers = set(o["customer_id"])
    cohort = [c for c in first.index[first < w0] if c in buyers]
    if len(cohort) < 2:
        return no_data("12주 창 이전부터 관측된 구매 고객이 2명 미만이다")
    win = o[(o["date"] >= w0) & (o["date"] < ctx.end)]
    counts = win.groupby("customer_id").size().reindex(cohort, fill_value=0).to_numpy(dtype=float)
    m, v = counts.mean(), counts.var(ddof=1)
    r = m * m / (v - m) if v > m else float("inf")
    # Complete Journey 식 보조값: 전 기간 주당 주문 수의 (평균/표준편차)²
    weeks = ctx.span_days / 7
    tp = o.groupby("customer_id").size() / weeks
    cj_shape = (tp.mean() / tp.std()) ** 2 if tp.std() > 0 else float("inf")
    syn = {"nbd_shape": _r(r), "mean_12w": _r(m, 2), "var_to_mean": _r(v / m if m > 0 else float("nan"), 2),
           "cj_style_shape_full_span": _r(cj_shape), "n_customers": len(cohort)}
    if math.isinf(r):
        return Result(syn, "fail", "12주 주문 수의 분산이 평균 이하(과소분산) — 구매율 이질성이 없다는 뜻이다.")
    return Result(syn, judge(r, 0.5, 1.5), "마지막 12주 창, 창 이전부터 관측된 구매 고객(0건 포함). "
                  "NBD 적률 추정 r = m²/(v − m) (Poisson 잡음 보정). cj_style 은 cj_stats.py 와 같은 (평균/표준편차)² 보조값.")


def f6(ctx: Context) -> Result:
    o = ctx.orders.dropna(subset=["order_amount"])
    if o.empty:
        return no_data("order_amount 가 있는 purchase 가 없다")
    w0 = max(ctx.start, ctx.end - pd.Timedelta(days=365))
    s = o[o["date"] >= w0].groupby("customer_id")["order_amount"].sum().sort_values(ascending=False)
    if len(s) < 10 or s.sum() <= 0:
        return no_data("구매 고객이 10명 미만이다")
    top20 = float(s.iloc[: int(.2 * len(s))].sum() / s.sum())
    top10 = float(s.iloc[: int(.1 * len(s))].sum() / s.sum())
    parts = {"top20": judge(top20, 0.53, 0.73), "top10": judge(top10, 0.33, 0.50)}
    window = (ctx.end - w0).days
    return Result({"top20": _r(top20), "top10": _r(top10), "n_customers": int(len(s)), "window_days": int(window)},
                  worst(list(parts.values())),
                  f"관측 {window}일(최대 365일) 매출, 구매 고객만(cj_stats.py 와 같은 정의)."
                  + (" 1년 미만 창 — 기간이 짧으면 집중도가 높게 나온다." if window < 365 else ""), parts)


def f7(ctx: Context) -> Result:
    a = ctx.orders.dropna(subset=["order_amount"])
    a = a[a["order_amount"] > 0]
    if len(a) < 2:
        return no_data("양수 order_amount 를 가진 purchase 가 2건 미만이다")
    lnsd = float(np.log(a["order_amount"]).std())
    hmean = a.groupby("customer_id")["order_amount"].mean()
    if len(hmean) < 2:
        return no_data("구매 고객이 2명 미만이다", {"order_ln_sd": _r(lnsd)})
    cv = float(hmean.std() / hmean.mean())
    parts = {"order_ln_sd": judge(lnsd, 0.4, 0.8), "customer_mean_aov_cv": judge(cv, 0.5, 0.8)}
    return Result({"order_ln_sd": _r(lnsd), "customer_mean_aov_cv": _r(cv), "n_orders": int(len(a))},
                  worst(list(parts.values())), "pandas 표본표준편차(ddof=1), cj_stats.py 와 같다.", parts)


def f8(ctx: Context) -> Result:
    a = ctx.orders["order_amount"].dropna()
    if a.empty:
        return no_data("order_amount 가 있는 purchase 가 없다")
    above = int(((a >= 40000) & (a < 44000)).sum())
    below = int(((a >= 36000) & (a < 40000)).sum())
    syn = {"ratio": None, "n_40000_44000": above, "n_36000_40000": below}
    if below == 0:
        return no_data("비교 구간 [36,000, 40,000) 의 주문이 0건이라 비율을 정의할 수 없다", syn)
    ratio = above / below
    syn["ratio"] = _r(ratio)
    return Result(syn, judge_open_lower(ratio, 1.0),
                  "구간 폭이 같으므로 밀도비 = 건수비. 금액은 purchase.order_amount(할인 후). "
                  "무료배송 판정이 할인 전 금액이면 몰림이 할인 폭만큼 흐려진다.")


def f9(ctx: Context) -> Result:
    ev = ctx.ev
    atc = set(ev.loc[(ev["event_type"] == "add_to_cart") & ev["session_id"].notna(), "session_id"])
    if not atc:
        return no_data("session_id 가 있는 add_to_cart 이벤트가 없다")
    if not (ev["event_type"] == "purchase").any():
        return no_data("purchase 이벤트가 로그에 한 건도 없다 — 생성기가 구매를 만들지 않으면 이탈률 100% 는 측정값이 아니다",
                       {"n_cart_sessions": len(atc)})
    bought = set(ev.loc[(ev["event_type"] == "purchase") & ev["session_id"].notna(), "session_id"])
    abandon = 100 * (1 - len(atc & bought) / len(atc))
    sessions = set(ev.loc[ev["session_id"].notna(), "session_id"])
    syn = {"cart_abandonment_pct": _r(abandon, 2),
           "session_to_purchase_pct": _r(100 * len(bought & sessions) / len(sessions), 2),
           "session_add_to_cart_pct": _r(100 * len(atc) / len(sessions), 2),
           "n_sessions": len(sessions), "n_cart_sessions": len(atc)}
    return Result(syn, judge(abandon, 50, 75),
                  "장바구니 이탈률 = 1 − (add_to_cart 와 purchase 가 함께 있는 세션 ÷ add_to_cart 세션). 판정은 이 값만. "
                  "세션→구매 전환(참고 3~8%)은 '방문 = 세션'일 때만 비교 대상이라 판정에 넣지 않는다(§3-4 미정).",
                  {"cart_abandonment": judge(abandon, 50, 75)})


def f10(ctx: Context) -> Result:
    ex = ctx.exchange or {}
    if "orders" not in ex or "order_items" not in ex:
        return no_data("교환 묶음(orders·order_items)이 없다. purchase 이벤트에는 품목이 없고 add_to_cart 근사는 계약이 금지한다(commerce-exchange §0)")
    orders = ex["orders"][["order_id", "customer_id", "ordered_at"]].copy()
    orders["ordered_at"] = pd.to_datetime(orders["ordered_at"], utc=True, format="ISO8601")
    orders = orders.sort_values(["customer_id", "ordered_at", "order_id"], kind="stable")
    orders["order_number"] = orders.groupby("customer_id").cumcount() + 1
    items = ex["order_items"][["order_id", "product_id"]].merge(orders, on="order_id")
    if items.empty:
        return no_data("교환 묶음의 품목이 주문과 결합되지 않는다")
    items = items.sort_values(["customer_id", "ordered_at", "order_id"], kind="stable")
    seen: dict[str, set] = {}
    flags = []
    cur_order, pending = None, []
    for row in items.itertuples(index=False):
        if row.order_id != cur_order:
            if cur_order is not None:
                seen.setdefault(prev_cust, set()).update(pending)
            cur_order, pending, prev_cust = row.order_id, [], row.customer_id
        flags.append(row.product_id in seen.get(row.customer_id, set()))
        pending.append(row.product_id)
    items = items.assign(reordered=flags)
    main = items[items["order_number"] >= 4]
    any_prior = items[items["order_number"] >= 2]
    if main.empty:
        return no_data("4번째 이후 주문(Instacart train 과 같은 조건)이 없다",
                       {"share_non_first_orders": _r(any_prior["reordered"].mean()) if len(any_prior) else None})
    share = float(main["reordered"].mean())
    return Result({"share": _r(share), "share_non_first_orders": _r(any_prior["reordered"].mean()),
                   "n_lines": int(len(main))}, judge(share, 0.50, 0.65),
                  "주문 품목 중 그 고객이 이전 주문에서 산 상품의 비율. Instacart train 이 4번째 이후 주문이라 같은 조건으로 판정.")


def f11(ctx: Context) -> Result:
    o = ctx.orders
    if o.empty:
        return no_data("purchase 이벤트가 없다")
    ex = ctx.exchange or {}
    if "customers" in ex and "signup_date" in ex["customers"].columns:
        signup = pd.to_datetime(ex["customers"].set_index("customer_id")["signup_date"])
        new = set(signup.index[signup > ctx.start])
        basis = "교환 묶음 customers.signup_date > 관측 첫날"
    else:
        first = _first_seen(ctx)
        new = set(first.index[first >= ctx.start + pd.Timedelta(days=14)])
        basis = "추정 — 교환 묶음이 없어 '첫 이벤트가 관측 시작 14일 이후'인 고객을 신규로 본다"
    if not new:
        return no_data(f"신규 고객을 식별할 수 없다({basis})")
    on = o[o["customer_id"].isin(new)].sort_values(["customer_id", "timestamp"], kind="stable")
    if on.empty:
        return no_data(f"신규 고객 중 구매자가 없다({basis})")
    g = on.groupby("customer_id")["date"]
    first_buy = g.min()
    second = g.apply(lambda s: s.iloc[1] if len(s) >= 2 else pd.NaT)
    within = (second.notna()) & ((second - first_buy).dt.days <= 365)
    rate = float(within.mean())
    follow = (ctx.end - first_buy).dt.days
    return Result({"rate": _r(rate), "n_new_buyers": int(len(first_buy)),
                   "followup_days_median": _r(follow.median(), 0)}, judge(rate, 0.55, 0.75),
                  f"신규 기준: {basis}. 관측 끝에서 잘린 추적(중앙 {int(follow.median())}일)이라 컬리의 '같은 해' 재구매율처럼 하한 쪽이다.")


def f12(ctx: Context) -> Result:
    o = ctx.orders
    if o.empty:
        return no_data("purchase 이벤트가 없다")
    treated: set = set()
    if ctx.assignments is not None and len(ctx.assignments):
        treated = set(ctx.assignments.loc[ctx.assignments["treatment_id"] != "T0", "customer_id"])
    o = o[~o["customer_id"].isin(treated)]
    t0s = []
    t = ctx.start + pd.Timedelta(days=56)
    last = ctx.end - pd.Timedelta(days=CHURN_DAYS)
    while t <= last:
        t0s.append(t)
        t += pd.Timedelta(days=30)
    if not t0s:
        return no_data(f"관측 {ctx.span_days}일 — 사전 창 56일 + 라벨 창 42일(98일)이 안 된다")
    rows = []
    for T0 in t0s:
        lb = min(180, (T0 - ctx.start).days)
        pre = o[(o["date"] < T0) & (o["date"] >= T0 - pd.Timedelta(days=lb))]
        elig = set(pre["customer_id"])
        if not elig:
            continue
        post = set(o[(o["date"] >= T0) & (o["date"] < T0 + pd.Timedelta(days=CHURN_DAYS))]["customer_id"])
        lastbuy = pre.groupby("customer_id")["date"].max()
        e14 = set(lastbuy.index[(T0 - lastbuy).dt.days >= 14])
        e42 = set(lastbuy.index[(T0 - lastbuy).dt.days < CHURN_DAYS])
        rows.append({"T0": str(T0.date()), "lookback_days": lb, "eligible": len(elig),
                     "churn_pct": round(100 * (1 - len(elig & post) / len(elig)), 2),
                     "churn14_pct": round(100 * (1 - len(e14 & post) / len(e14)), 2) if e14 else None,
                     "churn_active42_pct": round(100 * (1 - len(e42 & post) / len(e42)), 2) if e42 else None})
    if not rows:
        return no_data("어느 T0 에도 사전 창 구매 고객이 없다")
    mean = float(np.mean([r["churn_pct"] for r in rows]))
    c14 = [r["churn14_pct"] for r in rows if r["churn14_pct"] is not None]
    c42 = [r["churn_active42_pct"] for r in rows if r["churn_active42_pct"] is not None]
    return Result({"churn_pct_mean": _r(mean, 2), "churn14_pct_mean": _r(np.mean(c14), 2) if c14 else None,
                   "churn_active42_pct_mean_ref": _r(np.mean(c42), 2) if c42 else None,
                   "by_T0": rows}, judge(mean, 15, 25),
                  "cj_label.py 와 같은 정의: T0 이전 최대 180일(관측이 짧으면 그만큼) 구매 고객 중 [T0, T0+42일) 무구매 비율, "
                  "30일 간격 여러 T0 평균. 비-T0 처치 고객은 제외. churn14 = 마지막 구매가 14일 이상 전인 부분집합(외부 28.6~31.8%). "
                  "churn_active42 = 최근 42일 안 구매 고객만(시뮬레이터 guardrails 의 활성 정의) — 참고값, 판정에 쓰지 않는다. "
                  "Eligible 정의가 PRD 에 고정돼 있지 않아 외부 집계(cj_label.py)와 같은 180일 정의로 판정한다.")


def f13(ctx: Context) -> Result:
    o = ctx.orders
    if o.empty:
        return no_data("purchase 이벤트가 없다")
    if ctx.span_days < CHURN_DAYS * 2:
        return no_data(f"관측 {ctx.span_days}일 — 42일 공백과 그 뒤 복귀를 볼 수 없다")
    w0 = max(ctx.start, ctx.end - pd.Timedelta(days=365))
    g = order_gaps(o[o["date"] >= w0], distinct_days=True)
    maxgap = g.groupby("customer_id")["gap"].max()
    returned = maxgap >= CHURN_DAYS
    share = float(returned.mean())
    lastbuy = g.groupby("customer_id")["date"].max()
    trailing = (ctx.end - lastbuy).dt.days >= CHURN_DAYS
    ever_lapsed = returned | trailing
    ret_among = float(returned[ever_lapsed].mean()) if ever_lapsed.any() else None
    syn = {"share_returned_after_42d_gap": _r(share, 4), "n_returned": int(returned.sum()),
           "n_customers": int(len(maxgap)), "return_rate_among_lapsed": _r(ret_among, 4)}
    return Result(syn, judge_open_lower(share, 0.0),
                  "cj_stats.py 와 같은 정의: 구매 날짜(중복 제거) 사이 공백이 42일 이상이었던 고객 비율 = 공백 뒤 돌아온 고객. "
                  "0 이면 이탈이 흡수 상태다(PRD Risk 2). CJ 43.5% 는 선발 표본이라 상한 참고.")


def _assignment_note(ctx: Context) -> str:
    if ctx.assignment_basis == "assignments_file":
        return "배정 근거: --assignments (apply_treatment 기록)."
    return ("배정 근거: 이벤트 treatment_id 태그로 추정. ★ 배정 뒤 이벤트가 없는 고객(특히 통제군 침묵 고객)이 빠져 "
            "통제군 유지율이 높게 잡힐 수 있다 — --assignments 로 다시 재야 한다.")


def _units(ctx: Context, window_days: int) -> pd.DataFrame | None:
    a = ctx.assignments
    if a is None or a.empty:
        return None
    a = a.copy()
    a["assigned_at"] = pd.to_datetime(a["assigned_at"])
    ends = a["assigned_at"] + pd.Timedelta(days=window_days)
    end_ts = pd.Timestamp(ctx.end).tz_localize(TZ)
    return a[ends <= end_ts].reset_index(drop=True)


def _events_in_window(ev: pd.DataFrame, units: pd.DataFrame, days: int, types: tuple[str, ...]) -> pd.DataFrame:
    sub = ev[ev["event_type"].isin(types)][["customer_id", "timestamp", "event_type", "order_id", "order_amount", "coupon_id"]]
    m = units.reset_index().rename(columns={"index": "unit"}).merge(sub, on="customer_id")
    lo = m["assigned_at"]
    return m[(m["timestamp"] >= lo) & (m["timestamp"] < lo + pd.Timedelta(days=days))]


def _ate_from_logs(ctx: Context) -> tuple[dict | None, str]:
    units = _units(ctx, CHURN_DAYS)
    if units is None:
        return None, "처치 배정 기록이 없다(--assignments 없음, 이벤트에 treatment_id 태그 없음)"
    units = units[units["treatment_id"].isin(["T0", "T3"])]
    if units.empty or units["treatment_id"].nunique() < 2:
        return None, "42일 라벨 창이 관측 안에 끝나는 T0·T3 배정이 두 군 모두에 있지 않다"
    hit = _events_in_window(ctx.ev, units, CHURN_DAYS, ("purchase",))
    retained = units.index.isin(hit["unit"].unique())
    units = units.assign(retained=retained)
    rate = units.groupby("treatment_id")["retained"].agg(["mean", "size"])
    p3, p0 = float(rate.loc["T3", "mean"]), float(rate.loc["T0", "mean"])
    n3, n0 = int(rate.loc["T3", "size"]), int(rate.loc["T0", "size"])
    se = math.sqrt(p3 * (1 - p3) / n3 + p0 * (1 - p0) / n0) if n3 and n0 else float("nan")
    return {"ate_pp": _r(100 * (p3 - p0), 2), "ci95_pp": [_r(100 * (p3 - p0 - 1.96 * se), 2), _r(100 * (p3 - p0 + 1.96 * se), 2)],
            "retention_T3_pct": _r(100 * p3, 2), "retention_T0_pct": _r(100 * p0, 2),
            "relative_effect_pct": _r(100 * (p3 / p0 - 1), 2) if p0 > 0 else None,
            "n_T3": n3, "n_T0": n0}, ""


def f14(ctx: Context) -> Result:
    obs, reason = _ate_from_logs(ctx)
    gt = guardrail_value(ctx.guardrail, "ate")
    if obs is not None:
        syn = dict(obs, basis="log_itt", ground_truth_ate_pp=_r(100 * gt, 2) if gt is not None else None)
        return Result(syn, judge(obs["ate_pp"], 3, 6),
                      "T3 vs T0, 배정 시각부터 42일 안 구매 여부(ITT). " + _assignment_note(ctx))
    if gt is not None:
        return Result({"ate_pp": _r(100 * gt, 2), "basis": "ground_truth"}, judge(100 * gt, 3, 6),
                      f"로그로 ITT 를 잴 수 없어({reason}) 시뮬레이터 가드레일 리포트의 ground truth ATE 로 판정했다.")
    return no_data(reason + "; 가드레일 리포트에도 ate 가 없다")


def f15(ctx: Context) -> Result:
    units = _units(ctx, COUPON_VALID_DAYS)
    if units is None:
        return no_data("처치 배정 기록이 없다(--assignments 없음, 이벤트에 treatment_id 태그 없음)")
    units = units[units["treatment_id"].isin(["T2", "T3"])]
    if units.empty:
        return no_data("유효기간(14일)이 관측 안에 끝나는 T2·T3 배정이 없다")
    hit = _events_in_window(ctx.ev, units, COUPON_VALID_DAYS, ("coupon_use", "purchase"))
    used = units.index.isin(hit.loc[hit["event_type"] == "coupon_use", "unit"].unique())
    bought = units.index.isin(hit.loc[hit["event_type"] == "purchase", "unit"].unique())
    rate = 100 * float(used.mean())
    among_buyers = 100 * float(used[bought].mean()) if bought.any() else None
    by_t = {t: _r(100 * float(used[units["treatment_id"] == t].mean()), 2) for t in sorted(units["treatment_id"].unique())}
    return Result({"rate_pct": _r(rate, 2), "by_treatment_pct": by_t, "rate_among_buyers_pct_ref": _r(among_buyers, 2),
                   "n_treated": int(len(units))}, judge(rate, 5, 20),
                  "분모 = 쿠폰 처치군(T2·T3) 전체, 분자 = 배정 후 14일 안 coupon_use (§3-1 결정 (a)). "
                  "'처치군 중 구매자' 분모 값은 참고. T2 유효기간은 config 에 없어 14일로 쟀다. " + _assignment_note(ctx))


def f16(ctx: Context) -> Result:
    d = guardrail_value(ctx.guardrail, "sleeping_dog_rate")
    p = guardrail_value(ctx.guardrail, "persuadable_rate")
    ate = guardrail_value(ctx.guardrail, "ate")
    syn = {"sleeping_dog_pct": _r(100 * d, 2) if d is not None else None,
           "persuadable_pct": _r(100 * p, 2) if p is not None else None,
           "ate_pp": _r(100 * ate, 2) if ate is not None else None, "identity_gap_pp": None}
    if ctx.guardrail is None:
        return no_data("가드레일 리포트(--guardrail)가 없다 — 4분면 유형은 ground truth 에만 있다", syn)
    missing = [k for k, v in (("sleeping_dog_rate", d), ("persuadable_rate", p), ("ate", ate)) if v is None]
    if missing:
        return no_data("가드레일 리포트에 키가 없다: " + ", ".join(missing), syn)
    gap = 100 * (p - d - ate)
    syn["identity_gap_pp"] = _r(gap, 3)
    pop = ctx.guardrail.get("sleeping_dog_bp") if isinstance(ctx.guardrail, dict) else None
    basis = ""
    if isinstance(ctx.guardrail.get("response_mix_bp"), dict):
        syn["population_sleeping_dog_pct_ref"] = _r(pop / 100, 2) if isinstance(pop, (int, float)) else None
        basis = (" 시뮬레이터 guardrails 출력(bp)에서 T3 의 반응 유형 positive/negative 와 ate_bp.T3(같은 활성 고객 모집단)을 읽었다."
                 " 반응 '성향' 유형이 잠재결과 4분면(처치 때만 구매 / 처치 때만 미구매)과 같은 정의가 아니면 항등식은 성립하지 않는다 —"
                 " 그 경우 실패는 정의 불일치를 뜻한다. 전 고객 Sleeping Dog(sleeping_dog_bp)은 참고값.")
    parts = {"sleeping_dog": judge(100 * d, 8, 15), "persuadable": judge(100 * p, 11, 21),
             "identity": "pass" if abs(gap) <= 0.5 else "fail"}
    return Result(syn, worst(list(parts.values())), "ground truth 유형 비율. 항등식 P − D = ATE 를 ±0.5%p 로 검사." + basis, parts)


def f17(ctx: Context) -> Result:
    units = _units(ctx, CHURN_DAYS)
    if units is None:
        return no_data("처치 배정 기록이 없다(--assignments 없음, 이벤트에 treatment_id 태그 없음)")
    treated = units[units["treatment_id"].isin(["T2", "T3"])]
    control = units[units["treatment_id"] == "T0"]
    if treated.empty or control.empty:
        return no_data("42일 창이 관측 안에 끝나는 쿠폰 처치군·통제군이 둘 다 있지 않다")
    units = pd.concat([treated, control]).reset_index(drop=True)
    hit = _events_in_window(ctx.ev, units, CHURN_DAYS, ("purchase", "coupon_use"))
    coupon_orders = set(hit.loc[(hit["event_type"] == "coupon_use") & hit["order_id"].notna(), "order_id"])
    buys = hit[hit["event_type"] == "purchase"].drop_duplicates(["unit", "order_id"])
    buys = buys.assign(coupon=buys["order_id"].isin(coupon_orders) | buys["coupon_id"].notna())
    rev = buys.groupby("unit")["order_amount"].sum().reindex(units.index, fill_value=0)
    rev_nc = buys[~buys["coupon"]].groupby("unit")["order_amount"].sum().reindex(units.index, fill_value=0)
    is_t = units["treatment_id"] != "T0"
    r_t, r_c = float(rev[is_t].mean()), float(rev[~is_t].mean())
    r_t_nc = float(rev_nc[is_t].mean())
    inc = r_t - r_c
    syn = {"share_non_coupon": None, "incremental_rev_per_customer_krw": _r(inc, 0),
           "rev_treated_krw": _r(r_t, 0), "rev_treated_non_coupon_krw": _r(r_t_nc, 0), "rev_control_krw": _r(r_c, 0),
           "n_treated": int(is_t.sum()), "n_control": int((~is_t).sum())}
    if inc <= 0:
        return no_data("처치군의 1인당 매출 증분이 0 이하라 '증분 중 쿠폰 미사용 몫'이 정의되지 않는다", syn)
    share = (r_t_nc - r_c) / inc
    syn["share_non_coupon"] = _r(share)
    return Result(syn, judge_open_lower(share, 0.0),
                  "Sahni 2017 정의: (처치군 쿠폰 미사용 주문 매출 − 통제군 매출) ÷ (처치군 매출 − 통제군 매출), 1인당·배정 후 42일. "
                  + _assignment_note(ctx))


CALCULATORS: dict[str, Callable[[Context], Result]] = {
    "F1": f1, "F2": f2, "F3": f3, "F4": f4, "F5": f5, "F6": f6, "F7": f7, "F8": f8, "F9": f9,
    "F10": f10, "F11": f11, "F12": f12, "F13": f13, "F14": f14, "F15": f15, "F16": f16, "F17": f17,
}


# ── 리포트 ───────────────────────────────────────────────────────────────────

BANDS: dict[str, Any] = {
    "F1": {"median": [5, 10], "mean": [9, 15], "p75": [12, 20]},
    "F2": [0.45, 0.70],
    "F3": {"median": [12, 18], "ln_sd": [0.5, 0.9]},
    "F4": {"orders_per_month": [2.0, 3.2], "aov_krw": [38000, 55000]},
    "F5": [0.5, 1.5],
    "F6": {"top20": [0.53, 0.73], "top10": [0.33, 0.50]},
    "F7": {"order_ln_sd": [0.4, 0.8], "customer_mean_aov_cv": [0.5, 0.8]},
    "F8": [1.0, None],
    "F9": [50, 75],
    "F10": [0.50, 0.65],
    "F11": [0.55, 0.75],
    "F12": [15, 25],
    "F13": [0.0, None],
    "F14": [3, 6],
    "F15": [5, 20],
    "F16": {"sleeping_dog": [8, 15], "persuadable": [11, 21], "identity_abs_gap_pp": [0, 0.5]},
    "F17": [0.0, None],
}


def load_sources() -> dict[str, str]:
    try:
        data = json.loads(SOURCES_JSON.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return {s["id"]: s.get("url", "").split(" ; ")[0].strip() for s in data if "id" in s}


def _uniq(series: pd.Series) -> Any:
    vals = sorted({str(v) for v in series.dropna().unique()})
    if not vals:
        return None
    return vals[0] if len(vals) == 1 else vals


def lineage_status(root: Path | None) -> str | None:
    if root is None:
        return None
    try:
        sys.path.insert(0, str(REPO))
        from src.measurement.sink import verify_lineage  # 공유 읽기 전용 계약

        result = verify_lineage(root)
        return f"{result.verification}: {result.detail}"
    except Exception as exc:  # 계보 검증은 보조 정보다 — 실패 사유만 남긴다
        return f"unverified: {type(exc).__name__}"


def build_report(ctx: Context, *, events_root: str | None = None, lineage: str | None = None) -> dict:
    sources = load_sources()
    metrics = []
    for fid, spec in SPECS.items():
        try:
            res = CALCULATORS[fid](ctx)
        except Exception as exc:  # 계산기 결함을 pass 로 숨기지 않는다
            res = Result(None, "no_data", f"계산 오류: {type(exc).__name__}: {exc}")
        metrics.append({
            "id": fid, "name": spec.name, "unit": spec.unit, "synthetic": res.synthetic,
            "reference": {"dataset": spec.dataset, "value": spec.reference_value, "band": BANDS[fid],
                          "band_text": spec.band_text, "source_ids": list(spec.sources),
                          "source_url": sources.get(spec.sources[0])},
            "verdict": res.verdict, "dashboard_verdict": DASHBOARD_VERDICT[res.verdict],
            "parts": res.parts or None, "note": res.note,
        })
    summary = {v: sum(1 for m in metrics if m["verdict"] == v) for v in VERDICTS}
    ev = ctx.ev
    return {
        "generated_at": datetime.now(KST).isoformat(timespec="seconds"),
        "source": {
            "events": events_root, "lineage": lineage,
            "n_customers": int(ev["customer_id"].nunique()), "n_events": int(len(ev)),
            "n_orders": int(len(ctx.orders)), "span_days": ctx.span_days,
            "start": str(ctx.start.date()) if len(ev) else None,
            "end_exclusive": str(ctx.end.date()) if len(ev) else None,
            "simulator_version": _uniq(ev["simulator_version"]), "random_seed": _uniq(ev["random_seed"]),
            "exchange": bool(ctx.exchange), "assignment_basis": ctx.assignment_basis,
            "guardrail": ctx.guardrail is not None,
        },
        "rules": {
            "bands_from": "docs/research/data_grounding.md §4 (GATE 1 전 고정, 결과를 보고 바꾸지 않는다)",
            "borderline": "띠 밖이지만 가까운 경계값의 ±20% 이내",
            "multi_part": "여러 값을 판정하는 항목은 모든 값이 계산돼야 판정한다(가장 나쁜 판정을 따른다)",
            "excluded": "AI 성능 지표(AUC·Qini 등)는 넣지 않는다",
        },
        "metrics": metrics,
        "summary": summary,
    }


def _na(v: Any) -> str:
    return "—" if v is None else str(v)


def _won(v: Any) -> str:
    return "—" if v is None else f"{int(round(v)):,}"


def _cell(text: str) -> str:
    return str(text).replace("|", "\\|")


def _fmt_syn(m: dict) -> str:
    s = m["synthetic"]
    fid = m["id"]
    if s is None:
        return "—"
    pick = {
        "F1": lambda s: f"중앙 {s['median']} · 평균 {s['mean']} · p75 {s['p75']}",
        "F2": lambda s: f"{s['median_cv']}",
        "F3": lambda s: f"중앙 {s['median']}일 · ln-sd {s['ln_sd']}",
        "F4": lambda s: f"월 {s.get('orders_per_month')}회 · {_won(s.get('aov_krw'))}원",
        "F5": lambda s: f"{s.get('nbd_shape')}",
        "F6": lambda s: f"상위20% {s['top20']} · 상위10% {s['top10']}",
        "F7": lambda s: f"ln-sd {s.get('order_ln_sd')} · CV {s.get('customer_mean_aov_cv')}",
        "F8": lambda s: f"{s.get('ratio')} ({s.get('n_40000_44000')}/{s.get('n_36000_40000')})",
        "F9": lambda s: f"{s['cart_abandonment_pct']}%",
        "F10": lambda s: f"{s.get('share')}",
        "F11": lambda s: f"{s['rate']} (n={s['n_new_buyers']})",
        "F12": lambda s: f"{s['churn_pct_mean']}%",
        "F13": lambda s: f"{s['share_returned_after_42d_gap']} (n={s['n_returned']})",
        "F14": lambda s: f"{s['ate_pp']}%p ({s.get('basis')})",
        "F15": lambda s: f"{s['rate_pct']}%",
        "F16": lambda s: f"D {_na(s['sleeping_dog_pct'])}% · P {_na(s['persuadable_pct'])}% · 항등식 차 {_na(s['identity_gap_pp'])}%p",
        "F17": lambda s: f"{s.get('share_non_coupon')}",
    }[fid]
    try:
        return pick(s)
    except (KeyError, TypeError):
        return "—"


VERDICT_LABEL = {"pass": "✅ 통과", "borderline": "🟡 경계", "fail": "❌ 실패", "no_data": "⬜ 데이터 없음"}


def render_md(report: dict) -> str:
    src = report["source"]
    sm = report["summary"]
    lines = [
        "# 생성 데이터 유의미성 검증 — 외부 stylized fact F1~F17", "",
        f"- 생성: {report['generated_at']} · 이벤트 루트: `{src['events']}`",
        f"- 고객 {src['n_customers']:,}명 · 주문 {src['n_orders']:,}건 · 관측 {src['span_days']}일"
        f" · simulator_version `{src['simulator_version']}` · seed `{src['random_seed']}`",
        f"- 교환 묶음: {'있음' if src['exchange'] else '없음'} · 배정 근거: {src['assignment_basis']} · 가드레일 리포트: {'있음' if src['guardrail'] else '없음'}",
        f"- 기준 띠: {report['rules']['bands_from']} · 경계 = {report['rules']['borderline']}", "",
        f"**한 줄 요약.** 17개 중 통과 {sm['pass']} · 경계 {sm['borderline']} · 실패 {sm['fail']} · 데이터 없음 {sm['no_data']}"
        f" — 계산 가능한 {17 - sm['no_data']}개 중 {sm['pass']}개가 외부 실데이터 띠 안이다.", "",
        "| # | 항목 | 우리 값 | 기준 띠 | 출처 | 판정 |",
        "|---|---|---|---|---|---|",
    ]
    for m in report["metrics"]:
        ref = m["reference"]
        url = ref["source_url"]
        srcs = f"[{ref['dataset']}]({url})" if url else ref["dataset"]
        lines.append(f"| {m['id']} | {_cell(m['name'])} | {_cell(_fmt_syn(m))} | {_cell(ref['band_text'])} | {srcs} | {VERDICT_LABEL[m['verdict']]} |")
    lines += ["", "## 항목별 메모", ""]
    for m in report["metrics"]:
        lines.append(f"- **{m['id']}** ({m['verdict']}) {m['note']}")
    lines.append("")
    return "\n".join(lines)


def run(events: str, *, exchange: str | None = None, assignments: str | None = None,
        guardrail: str | None = None) -> dict:
    ev = load_events(events)
    guard = json.loads(Path(guardrail).read_text(encoding="utf-8")) if guardrail else None
    ctx = build_context(ev, exchange=load_exchange(exchange), assignments=load_assignments(assignments), guardrail=guard)
    return build_report(ctx, events_root=str(events), lineage=lineage_status(Path(events)))


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--events", required=True, help="Sink 루트 (<root>/events/date=*/part-*)")
    ap.add_argument("--exchange", help="교환 묶음 디렉터리 (customers·orders·order_items)")
    ap.add_argument("--assignments", help="처치 배정 기록 JSON")
    ap.add_argument("--guardrail", help="시뮬레이터 가드레일 리포트 JSON (ground truth)")
    ap.add_argument("--out-json", help="결과 JSON 경로")
    ap.add_argument("--out-md", help="발표용 Markdown 경로")
    args = ap.parse_args(argv)
    report = run(args.events, exchange=args.exchange, assignments=args.assignments, guardrail=args.guardrail)
    text = json.dumps(report, ensure_ascii=False, indent=2, default=str)
    if args.out_json:
        Path(args.out_json).write_text(text + "\n", encoding="utf-8")
    if args.out_md:
        Path(args.out_md).write_text(render_md(report), encoding="utf-8")
    if not args.out_json and not args.out_md:
        print(text)
    print(json.dumps(report["summary"], ensure_ascii=False), file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
