"""코호트 · 퍼널 · 드리프트 리포트 CLI (스프린트 1 D11·D12, 에픽 #142).

    python -m src.decision.analytics_report --events <Sink 루트> --index-times <t1>,<t2> --out-dir <dir>

읽는 것은 **관측 이벤트(Sink 출력)뿐**이다. 쓰는 것:

  - ``funnel.json``  — 관측 전 구간과 ``[t1, t2)`` 의 구매 퍼널 (`analytics.funnel`)
  - ``cohort.json``  — 첫 구매 월 코호트 × 경과 월 재구매율 (`analytics.cohort_retention`)
  - ``drift.json``   — t1 대비 t2 Feature PSI·KS (`monitoring.feature_drift`), MON-004 최소 구조

각 JSON 최상위에 ``sprint``·``sealed``·``generated_at`` 을 둔다. 성능 추이는 이 CLI 가 모델을
학습하지 않으므로 ``not_run`` 이다(통과가 아니다).
"""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from typing import Any

from src.measurement.contracts import kst_now

SPRINT = "sprint-v0"


def _jsonable(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(k): _jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(v) for v in value]
    if hasattr(value, "item") and not isinstance(value, (str, bytes)):
        try:
            value = value.item()
        except (AttributeError, ValueError):
            pass
    if isinstance(value, float) and (math.isnan(value) or math.isinf(value)):
        return None
    return value


def _write(path: Path, payload: dict[str, Any], header: dict[str, Any]) -> None:
    body = {**header, **payload}
    path.write_text(json.dumps(_jsonable(body), ensure_ascii=False, indent=2, allow_nan=False) + "\n",
                    encoding="utf-8")


def run(events_root: Path, index_times: list[str], out_dir: Path) -> dict[str, Path]:
    from src.decision.analytics import cohort_retention, funnel
    from src.decision.data import load_events
    from src.decision.features.sprint_table import build_feature_table, model_columns, to_index_time
    from src.decision.monitoring import (DEFAULT_THRESHOLDS, LEVEL_ALERT, LEVEL_WARNING, alerts,
                                         drift_to_records, feature_drift)

    if len(index_times) != 2:
        raise SystemExit("--index-times 는 t1,t2 두 개다")
    t1, t2 = (to_index_time(t) for t in index_times)
    if not t1 < t2:
        raise SystemExit(f"t1 < t2 여야 한다: {t1} / {t2}")
    out_dir.mkdir(parents=True, exist_ok=True)
    events = load_events(events_root)
    header = {"sprint": SPRINT, "sealed": False, "generated_at": kst_now()}
    source = {"events_root": str(events_root), "n_events": int(len(events)),
              "n_customers": int(events["customer_id"].nunique()),
              "duplicate_event_ids": events.attrs.get("duplicate_event_ids"),
              "observed_start": events["timestamp"].min().isoformat() if len(events) else None,
              "observed_end": events["timestamp"].max().isoformat() if len(events) else None}
    paths: dict[str, Path] = {}

    paths["funnel"] = out_dir / "funnel.json"
    _write(paths["funnel"], {"source": source, "overall": funnel(events),
                             "t1_to_t2": funnel(events, t1, t2)}, header)

    paths["cohort"] = out_dir / "cohort.json"
    _write(paths["cohort"], {"source": source, **cohort_retention(events, "M")}, header)

    X1 = build_feature_table(events, t1)
    X2 = build_feature_table(events, t2)
    cols = [c for c in model_columns(X1) if c in X2.columns]
    drift = feature_drift(X1[cols], X2[cols])
    alert_list = alerts(drift, None, DEFAULT_THRESHOLDS)
    exceeded = [f for f, lvl in drift["level"].items() if lvl in (LEVEL_WARNING, LEVEL_ALERT)]
    paths["drift"] = out_dir / "drift.json"
    _write(paths["drift"], {
        "source": source,
        "reference_time": t1.isoformat(), "current_time": t2.isoformat(),
        "n_reference": int(len(X1)), "n_current": int(len(X2)),
        "drift_method": "PSI",
        "secondary_method": "KS (scipy.stats.ks_2samp, 결손 제외)",
        "psi_bins": "기준(t1) 분위수 10 구간 + 범위 밖 2 + 결손 1",
        "thresholds": DEFAULT_THRESHOLDS,
        "level_counts": {str(k): int(v) for k, v in drift["level"].value_counts().items()},
        "features": drift_to_records(drift),
        "threshold_exceeded": exceeded,
        "performance_over_time": [],
        "performance_over_time_status": {"status": "not_run",
                                         "reason": "이 CLI 는 모델을 학습하지 않는다 — 시점별 (y, p) 입력 필요"},
        "alerts": alert_list,
        "incomplete_windows": {"reference": X1.attrs.get("incomplete_windows"),
                               "current": X2.attrs.get("incomplete_windows")},
    }, header)
    return paths


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m src.decision.analytics_report",
                                     description="코호트·퍼널·Feature 드리프트 리포트 (관측 이벤트만 읽는다)")
    parser.add_argument("--events", type=Path, required=True, help="Sink 출력 루트 (<root>/events/date=…)")
    parser.add_argument("--index-times", required=True, help="t1,t2 (ISO 8601, tz 없으면 KST)")
    parser.add_argument("--out-dir", type=Path, required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    times = [t.strip() for t in args.index_times.split(",") if t.strip()]
    paths = run(args.events, times, args.out_dir)
    for name, path in paths.items():
        print(f"{name}: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
