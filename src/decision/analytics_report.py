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
import os
import shutil
import tempfile
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


def _publish(out_dir: Path, payloads: dict[str, dict[str, Any]], header: dict[str, Any]) -> dict[str, Path]:
    """전부 계산·직렬화한 뒤 교체한다. 교체 오류는 이미 교체한 파일을 복원한다."""
    out_dir.mkdir(parents=True, exist_ok=True)
    paths = {name: out_dir / f"{name}.json" for name in payloads}
    stage = Path(tempfile.mkdtemp(prefix=".analytics-report-", dir=out_dir))
    keep_backups = False
    try:
        backups = {}
        for name, path in paths.items():
            if path.is_symlink() or (path.exists() and not path.is_file()):
                raise ValueError(f"report destination is not a regular file: {path}")
            _write(stage / f"{name}.json", payloads[name], header)
            if path.exists():
                backup = stage / f"{name}.previous"
                shutil.copy2(path, backup)
                backups[name] = backup
        published = []
        try:
            for name, path in paths.items():
                os.replace(stage / f"{name}.json", path)
                published.append(name)
        except OSError as publish_error:
            restore_errors = []
            for name in reversed(published):
                try:
                    if name in backups:
                        os.replace(backups[name], paths[name])
                    else:
                        paths[name].unlink()
                except OSError as restore_error:
                    restore_errors.append(restore_error)
            if restore_errors:
                keep_backups = True
                raise OSError(f"report replacement and restoration failed; recovery files retained at {stage}") from publish_error
            raise
    finally:
        if not keep_backups:
            shutil.rmtree(stage)
    return paths


def run(events_root: Path, index_times: list[str], out_dir: Path) -> dict[str, Path]:
    from src.decision.analytics import cohort_retention, funnel
    from src.decision.data import load_events
    from src.decision.features.sprint_table import build_feature_table, observation_columns, to_index_time
    from src.decision.monitoring import (DEFAULT_THRESHOLDS, LEVEL_ALERT, LEVEL_WARNING, alerts,
                                         drift_to_records, feature_drift)
    from src.decision.return_visit import input_metadata

    if len(index_times) != 2:
        raise SystemExit("--index-times 는 t1,t2 두 개다")
    t1, t2 = (to_index_time(t) for t in index_times)
    if not t1 < t2:
        raise SystemExit(f"t1 < t2 여야 한다: {t1} / {t2}")
    events = load_events(events_root)
    header = {"sprint": SPRINT, "sealed": False, "generated_at": kst_now()}
    metadata = input_metadata(events)
    mixed = len(metadata["groups"]) > 1
    source = {"events_root": str(events_root), "n_events": int(len(events)),
              "n_customers": None if mixed else int(events["customer_id"].nunique()),
              "duplicate_event_ids": events.attrs.get("duplicate_event_ids"),
              "observed_start": events["timestamp"].min().isoformat() if len(events) else None,
              "observed_end": events["timestamp"].max().isoformat() if len(events) else None,
              "purpose": "observation", "return_visit_input": metadata}
    if mixed:
        # 출처별로 다시 호출한다. 같은 ID의 서로 다른 고객을 합산하지 않는다.
        reason = "mixed event sources: use separate source inputs for observation reports"
        payloads = {name: {"source": source, "status": "not_run", "reason": reason}
                    for name in ("funnel", "cohort", "drift")}
        payloads["drift"].update(features={}, threshold_exceeded=[], alerts=[], performance_over_time=[],
                                 performance_over_time_status={"status": "not_run", "reason": reason})
        return _publish(out_dir, payloads, header)

    payloads = {
        "funnel": {"source": source, "overall": funnel(events), "t1_to_t2": funnel(events, t1, t2)},
        "cohort": {"source": source, **cohort_retention(events, "M")},
    }
    X1 = build_feature_table(events, t1, purpose="observation")
    X2 = build_feature_table(events, t2, purpose="observation")
    cols = [c for c in observation_columns(X1) if c in X2.columns]
    drift = feature_drift(X1[cols], X2[cols])
    alert_list = alerts(drift, None, DEFAULT_THRESHOLDS)
    exceeded = [f for f, lvl in drift["level"].items() if lvl in (LEVEL_WARNING, LEVEL_ALERT)]
    empty_population = len(X1) == 0 or len(X2) == 0
    payloads["drift"] = {
        "source": source,
        "status": "not_run" if empty_population else "ok",
        "reason": "reference or current feature population is empty" if empty_population else None,
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
    }
    return _publish(out_dir, payloads, header)


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
