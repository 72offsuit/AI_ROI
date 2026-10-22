"""코호트 · 퍼널 · 세그먼트 ROI 분석 — 스프린트 1 D11 (이슈 #93, 에픽 #142 · SRS ANA-001·006 · ROI-003~006).

입력은 `src.decision.data.load_events` 가 돌려주는 **관측 이벤트 DataFrame**
(`customer_id`·`timestamp`·`event_type` …) 또는 오케스트레이션 결과 JSON 의 집계다.
시뮬레이터 내부·숨김 영역은 모른다.

규율:
  - **결손을 0 으로 채우지 않는다.** 분모가 0 이면 비율은 `None` 이고 사유를 함께 싣는다.
  - **관측되지 않은 기간은 0 이 아니라 `None` 이다.** 코호트의 경과 기간이 데이터 끝을
    넘으면(우측 절단) 재구매율을 계산하지 않는다 — 0 % 로 보이면 이탈로 오독된다.
  - 파생 상태 이벤트(`churn`·`at_risk`·`inactive`)와 배정 필드는 읽지 않는다.

SRS 와의 차이 (숨기지 않는다):
  - ANA-001 은 **가입월** 코호트를 요구하지만 관측 이벤트 16 종에 가입(signup) 이벤트가 없다.
    그래서 **첫 구매 기간**을 코호트로 쓴다(`cohort_basis="first_purchase"`). 가입 시점이
    계약에 들어오면 바꾼다.
  - ANA-006 의 Signup → First Purchase → Repurchase → Loyal → Churn 여정 퍼널은 가입 이벤트와
    이탈 라벨 정의가 필요해 이 판에서 계산하지 않는다. 여기의 `funnel` 은 **세션 구매 퍼널**
    (방문 → 상품조회 → 장바구니 → 결제시작 → 구매)이다.
"""

from __future__ import annotations

from typing import Any, Mapping, Sequence

import pandas as pd

from src.measurement.schema import TIMEZONE

#: 퍼널 단계. 순서가 곧 단계 순서다. 방문은 `session_start` 만 센다(`return_visit` 은
#: 같은 방문의 재진입 표지라 단계 시작점으로 쓰면 이중 계산된다).
FUNNEL_STEPS: tuple[tuple[str, str], ...] = (
    ("visit", "session_start"),
    ("product_view", "product_view"),
    ("add_to_cart", "add_to_cart"),
    ("checkout_start", "checkout_start"),
    ("purchase", "purchase"),
)
#: ANA-001 이 요구하는 경과 기간(월).
ANA001_OFFSETS = (1, 3, 6, 12)


def _ts(value) -> pd.Timestamp | None:
    if value is None:
        return None
    stamp = pd.Timestamp(value)
    if stamp.tzinfo is None:
        stamp = stamp.tz_localize(TIMEZONE)
    return stamp.tz_convert(TIMEZONE)


def _as_kst(series: pd.Series) -> pd.Series:
    """tz-aware 면 KST 로, naive 면 KST 로 해석한다(설정값 해석 — `sprint_table.to_index_time` 과 같은 규칙)."""
    ts = pd.to_datetime(series)
    if ts.dt.tz is None:
        return ts.dt.tz_localize(TIMEZONE)
    return ts.dt.tz_convert(TIMEZONE)


def _window(events: pd.DataFrame, start, end) -> pd.DataFrame:
    frame = events[["customer_id", "timestamp", "event_type"]].dropna(subset=["customer_id", "timestamp"])
    frame = frame.assign(timestamp=_as_kst(frame["timestamp"]))
    lo, hi = _ts(start), _ts(end)
    if lo is not None:
        frame = frame[frame["timestamp"] >= lo]
    if hi is not None:
        frame = frame[frame["timestamp"] < hi]
    return frame


def _rate(num: int, den: int) -> float | None:
    return None if den == 0 else num / den


def funnel(events: pd.DataFrame, start=None, end=None, *,
           steps: Sequence[tuple[str, str]] = FUNNEL_STEPS) -> dict[str, Any]:
    """`[start, end)` 창의 구매 퍼널 — 단계별 고객 수와 전환율.

    **순서 퍼널**이다: 고객이 k 단계에 도달한 시각은 (k−1) 단계 도달 시각 **이후(같은 시각 포함)**
    첫 k 단계 이벤트 시각이다. 장바구니 없이 구매만 있는 고객은 구매 단계에 들어가지 않는다.
    순서를 따지지 않은 도달 수(`n_any`)도 함께 싣는다 — 둘의 차이가 크면 이벤트 순서나
    누락을 의심한다.

    반환: ``{"window", "n_customers_in_window", "steps": [{step, event_type, n, n_any,
    step_conversion, overall_conversion, drop_off}]}``. 분모가 0 이면 비율은 ``None`` 이다.
    """
    frame = _window(events, start, end)
    reached: pd.Series | None = None  # customer_id → 직전 단계 도달 시각
    rows: list[dict[str, Any]] = []
    first_n: int | None = None
    prev_n: int | None = None
    for name, event_type in steps:
        hits = frame.loc[frame["event_type"] == event_type, ["customer_id", "timestamp"]]
        n_any = int(hits["customer_id"].nunique())
        if reached is None:
            reached = hits.groupby("customer_id")["timestamp"].min()
        else:
            prev = reached.rename("t_prev").reset_index()
            joined = hits.merge(prev, on="customer_id", how="inner")
            joined = joined[joined["timestamp"] >= joined["t_prev"]]
            reached = joined.groupby("customer_id")["timestamp"].min()
        n = int(len(reached))
        if first_n is None:
            first_n = n
        step_conv = _rate(n, prev_n) if prev_n is not None else None
        rows.append({
            "step": name, "event_type": event_type, "n": n, "n_any": n_any,
            "step_conversion": step_conv,
            "overall_conversion": _rate(n, first_n),
            "drop_off": None if step_conv is None else 1.0 - step_conv,
        })
        prev_n = n
    return {
        "window": {"start": None if start is None else _ts(start).isoformat(),
                   "end": None if end is None else _ts(end).isoformat()},
        "definition": "순서 퍼널 — k 단계 도달 = (k−1) 단계 도달 시각 이후 첫 k 단계 이벤트",
        "n_customers_in_window": int(frame["customer_id"].nunique()),
        "steps": rows,
    }


def _period_bounds(period: pd.Period) -> tuple[pd.Timestamp, pd.Timestamp]:
    lo = period.start_time.tz_localize(TIMEZONE)
    hi = (period + 1).start_time.tz_localize(TIMEZONE)
    return lo, hi


def cohort_retention(events: pd.DataFrame, freq: str = "M", *, observed_end=None,
                     max_offset: int | None = None) -> dict[str, Any]:
    """첫 구매 기간 코호트 × 경과 기간 재구매율 표.

    - 코호트: 고객의 첫 `purchase` 가 속한 기간(`freq`, 기본 월 · KST 달력).
    - ``retention[m]`` (m ≥ 1): 코호트 고객 중 (코호트 + m) 기간에 `purchase` 가 1 건 이상인 비율.
    - 그 기간의 끝이 ``observed_end``(기본: 이벤트의 마지막 시각) 보다 뒤면 **관측이 끝나지 않은
      기간**이므로 ``None`` 이다(우측 절단). 0 이 아니다.
    - 관측 시작 이전에 구매가 있었는지는 알 수 없다 — 첫 관측 기간 코호트에는 기존 고객이
      섞인다(`left_censored_cohort`).

    반환: ``{"freq", "cohort_basis", "observed_end", "cohorts": [{cohort, size, retention:{m: r|None}}],
    "ana001": {Mm: 코호트 크기 가중 평균 | None}}``.
    """
    frame = events.loc[events["event_type"] == "purchase", ["customer_id", "timestamp"]]
    frame = frame.dropna(subset=["customer_id", "timestamp"])
    end = _ts(observed_end)
    if end is None:
        all_ts = events["timestamp"].dropna()
        end = _as_kst(all_ts).max() if len(all_ts) else None
    out: dict[str, Any] = {
        "freq": freq, "cohort_basis": "first_purchase",
        "definition": "retention[m] = 코호트 고객 중 (코호트+m) 기간 구매 고객 비율. 관측이 끝나지 않은 기간은 null",
        "observed_end": None if end is None else end.isoformat(),
        "cohorts": [], "ana001": {},
    }
    if frame.empty or end is None:
        out["status"] = "계산 불가 — 관측 구매 없음"
        out["ana001"] = {f"M{m}": None for m in ANA001_OFFSETS}
        return out
    ts = _as_kst(frame["timestamp"]).dt.tz_localize(None)
    period = ts.dt.to_period(freq)
    frame = pd.DataFrame({"customer_id": frame["customer_id"].to_numpy(), "period": period.to_numpy()})
    first = frame.groupby("customer_id")["period"].min().rename("cohort")
    frame = frame.join(first, on="customer_id")
    frame["offset"] = (frame["period"] - frame["cohort"]).map(lambda d: d.n)
    active = frame.drop_duplicates(["customer_id", "offset"])
    first_period = first.min()
    last_offset = int(frame["offset"].max())
    if max_offset is None:
        max_offset = max(last_offset, max(ANA001_OFFSETS) if freq.upper().startswith("M") else last_offset)
    weighted: dict[int, list[tuple[int, float]]] = {}
    for cohort, size in first.value_counts().sort_index().items():
        members = active[active["cohort"] == cohort]
        counts = members.groupby("offset")["customer_id"].nunique()
        retention: dict[str, float | None] = {}
        for m in range(1, max_offset + 1):
            _, hi = _period_bounds(cohort + m)
            if hi > end:
                retention[str(m)] = None
                continue
            # 관측이 끝난 기간에 구매가 없으면 그것은 결손이 아니라 관측된 0 건이다.
            n_active = int(counts[m]) if m in counts.index else 0
            r = n_active / int(size)
            retention[str(m)] = r
            weighted.setdefault(m, []).append((int(size), r))
        out["cohorts"].append({
            "cohort": str(cohort), "size": int(size), "retention": retention,
            "left_censored_cohort": bool(cohort == first_period),
        })
    if freq.upper().startswith("M"):
        for m in ANA001_OFFSETS:
            pairs = weighted.get(m)
            if not pairs:
                out["ana001"][f"M{m}"] = None
            else:
                total = sum(n for n, _ in pairs)
                out["ana001"][f"M{m}"] = sum(n * r for n, r in pairs) / total
    else:
        out["ana001_status"] = "계산 불가 — ANA-001 은 월 단위(freq='M')"
    out["status"] = "ok"
    return out


def roi_by_segment(by_segment: Mapping[str, Mapping[str, Mapping[str, Any]]] | None,
                   baseline_id: str = "S1", ai_investment_cost: float | None = None) -> dict[str, Any]:
    """세그먼트별 증분이익·ROI 요약 (ROI-003·005·006).

    ``by_segment``: ``{segment: {strategy_id: metrics}}`` — 전략 실행 결과를 세그먼트로 나눈 집계.
    계산은 `src.decision.roi.summarize_strategy` 를 **그대로** 쓴다(정의가 두 벌이면 어긋난다).
    세그먼트 결과가 없거나 기준 전략(S1) 집계가 없으면 그 세그먼트는 **계산 불가**다.
    """
    from .roi import summarize_strategy

    if not by_segment:
        return {"status": "계산 불가",
                "reason": "세그먼트별 전략 집계가 없다 — 실행 루프가 세그먼트 단위 결과를 내지 않았다",
                "segments": {}}
    segments: dict[str, Any] = {}
    for segment, per_strategy in by_segment.items():
        base = per_strategy.get(baseline_id) if per_strategy else None
        if base is None:
            segments[str(segment)] = {"status": "계산 불가", "reason": f"기준 전략 {baseline_id} 집계 없음"}
            continue
        rows = {sid: summarize_strategy({"id": sid, **m}, base, ai_investment_cost)
                for sid, m in per_strategy.items()}
        segments[str(segment)] = {"status": "ok", "baseline": baseline_id, "strategies": rows}
    any_ok = any(v.get("status") == "ok" for v in segments.values())
    return {"status": "ok" if any_ok else "계산 불가", "segments": segments}
