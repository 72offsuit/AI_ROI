"""realism_check 내부 리포트 → 관측 통계만 담은 공개판 `docs/research/realism_public.json` (#163).

내부 리포트(`realism_report.json`, 시스템 팀 must_not_read)에는 처치 효과 실측 · 참 4분면(F14~F17)과
모집단 · T0 별 생성 이탈률(F12)이 들어 있다. 공개판은 관측 이벤트로 잰 F1~F11 · F13 만 옮긴다.
숫자는 고치지 않는다.

거르는 방식
- 항목은 허용 목록(PUBLIC_IDS), 항목 · `source` · `rules` 의 최상위 키도 허용 목록으로 고른다.
- 그 아래(`synthetic` · `reference` · `parts`)는 통째로 옮기므로, 대신 결과 전체에서 금지 문자열(Persona ·
  처치군 T1~T4 · 숨은 영역 · 로컬 경로)을 찾아 하나라도 있으면 **공개판을 만들지 않는다**.
- 판정이 `no_data` 이거나 모르는 값인 항목, 중복 id, 확인 seed(47~51) 리포트도 거부한다.
- 새 하위 키가 생기면 금지 문자열에 안 걸리는 한 따라 나간다. 그래서 테스트가 커밋된 공개판의 키 경로를
  고정한다 — 키가 바뀌면 테스트가 깨지고, 사람이 보고 갱신한다.

사용
    python3.12 scripts/realism_public.py <내부 realism_report.json> [--out docs/research/realism_public.json]
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
DEFAULT_OUT = REPO / "docs" / "research" / "realism_public.json"

# F12 는 모집단 · T0 별 생성 이탈률이라, F14~F17 은 처치 효과 · 4분면(정답)이라 넣지 않는다(#163 11/13 분류).
PUBLIC_IDS = tuple(f"F{i}" for i in (*range(1, 12), 13))
METRIC_KEYS = ("id", "name", "unit", "synthetic", "reference", "verdict", "dashboard_verdict", "parts", "note")
SOURCE_KEYS = ("simulator_version", "random_seed", "n_customers", "n_events", "n_orders",
               "span_days", "start", "end_exclusive")
RULE_KEYS = ("bands_from", "borderline", "multi_part", "excluded")
PUBLISHABLE = ("pass", "borderline", "fail")
CONFIRM_SEEDS = range(47, 52)  # 확인 seed 는 봉인 실측 전용이다 — 공개판 재료로 쓰지 않는다
FORBIDDEN = re.compile(
    r"persona|vip_loyal|price_sensitive|churn_progressing|new_customer|\bloyal\b|\bexplorer\b"
    r"|\bT[1-4]\b|treat|tau|hidden|ground_truth|sleeping|persuadable"
    r"|/Users/|/home/|/private/|/tmp/|[A-Za-z]:\\\\|Traceback|Error\b",
    re.IGNORECASE,
)


def _strings(obj):
    if isinstance(obj, dict):
        for k, v in obj.items():
            yield str(k)
            yield from _strings(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from _strings(v)
    elif isinstance(obj, str):
        yield obj


def make_public(report: dict) -> dict:
    ids = [m.get("id") for m in report.get("metrics", [])]
    if len(ids) != len(set(ids)):
        raise ValueError("내부 리포트에 중복 id 가 있다 — 공개판을 만들지 않는다")
    by_id = {m.get("id"): m for m in report.get("metrics", [])}
    missing = [i for i in PUBLIC_IDS if i not in by_id]
    if missing:
        raise ValueError(f"내부 리포트에 {missing} 가 없다 — 공개판을 만들지 않는다")
    unpublishable = [i for i in PUBLIC_IDS if by_id[i].get("verdict") not in PUBLISHABLE]
    if unpublishable:
        raise ValueError(f"{unpublishable} 판정이 no_data 이거나 알 수 없다 — 공개판을 만들지 않는다")
    source = report.get("source", {})
    if str(source.get("random_seed", "")).isdigit() and int(source["random_seed"]) in CONFIRM_SEEDS:
        raise ValueError("확인 seed(47~51) 리포트다 — 공개판을 만들지 않는다")
    metrics = [{k: by_id[i][k] for k in METRIC_KEYS if k in by_id[i]} for i in PUBLIC_IDS]
    rules = report.get("rules") or {}
    public = {
        "generated_at": report.get("generated_at"),
        "scope": "관측 이벤트로 잰 F1~F11 · F13 만 담는다. 처치 효과 · 고객군별 값 · 숨은 값 · 생성 이탈률은 "
                 "담지 않는다(#163). 통과 띠는 docs/research/data_grounding.md §4.",
        "source": {k: source[k] for k in SOURCE_KEYS if k in source},
        "rules": {k: rules[k] for k in RULE_KEYS if k in rules},
        "summary": {v: sum(1 for m in metrics if m["verdict"] == v) for v in PUBLISHABLE},
        "metrics": metrics,
    }
    hits = sorted({h.group() for s in _strings(public) for h in [FORBIDDEN.search(s)] if h})
    if hits:
        raise ValueError(f"금지 문자열 {hits} 가 있다 — 공개판을 만들지 않는다")
    return public


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
