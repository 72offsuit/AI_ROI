"""realism_check 내부 리포트 → 관측 통계만 담은 공개판 `docs/research/realism_public.json` (#163).

내부 리포트(`realism_report.json`, 시스템 팀 must_not_read)에는 처치 효과 실측과 참 4분면(F14~F17)이 들어 있다.
공개판은 관측 이벤트로만 잰 F1~F13 을 허용 목록으로 골라 옮긴다. 허용 목록에 없는 항목 · 키는 버린다
(새 항목이 생겨도 저절로 공개되지 않는다). 숫자는 고치지 않고 그대로 옮긴다.

사용
    python3.12 scripts/realism_public.py <내부 realism_report.json> [--out docs/research/realism_public.json]
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
DEFAULT_OUT = REPO / "docs" / "research" / "realism_public.json"

# 관측 이벤트로만 재는 항목. F14~F17 은 처치 효과 · 4분면(정답)이라 넣지 않는다.
PUBLIC_IDS = tuple(f"F{i}" for i in range(1, 14))
METRIC_KEYS = ("id", "name", "unit", "synthetic", "reference", "verdict", "dashboard_verdict", "parts", "note")
SOURCE_KEYS = ("simulator_version", "random_seed", "n_customers", "n_events", "n_orders",
               "span_days", "start", "end_exclusive")
VERDICTS = ("pass", "borderline", "fail", "no_data")
# 공개판만 보는 사람이 오해하지 않게 붙이는 설명. 판정 · 숫자는 바꾸지 않는다.
GATE1_NOTES = {
    "F12": "GATE 1 판정에 쓰지 않는 참고 항목이다. 이 값은 data_spec §4.1 eligible(마지막 구매 14일+ 전 포함) 모집단이라 "
           "이탈이 높게 잡힌다. GATE 1 이탈률 판정은 T0 전 42일 안에 구매한 고객 모집단으로 따로 한다(DR-208).",
}


def make_public(report: dict) -> dict:
    by_id = {m.get("id"): m for m in report.get("metrics", [])}
    missing = [i for i in PUBLIC_IDS if i not in by_id]
    if missing:
        raise ValueError(f"내부 리포트에 {missing} 가 없다 — 공개판을 만들지 않는다")
    metrics = [{k: by_id[i][k] for k in METRIC_KEYS if k in by_id[i]} for i in PUBLIC_IDS]
    for m in metrics:
        if m["id"] in GATE1_NOTES:
            m["gate1_note"] = GATE1_NOTES[m["id"]]
    source = report.get("source", {})
    return {
        "generated_at": report.get("generated_at"),
        "scope": "관측 이벤트로 잰 F1~F13 만 담는다. 처치 효과 · 고객군(Persona) · 숨은 값은 담지 않는다(#163). "
                 "통과 띠는 docs/research/data_grounding.md §4.",
        "source": {k: source[k] for k in SOURCE_KEYS if k in source},
        "rules": report.get("rules"),
        "summary": {v: sum(1 for m in metrics if m.get("verdict") == v) for v in VERDICTS},
        "metrics": metrics,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("report", type=Path)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args(argv)
    public = make_public(json.loads(args.report.read_text(encoding="utf-8")))
    args.out.write_text(json.dumps(public, ensure_ascii=False, indent=1, allow_nan=False) + "\n", encoding="utf-8")
    print(f"{args.out}: {public['summary']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
