"""realism_check 내부 리포트 → 관측 통계만 담은 공개판 `docs/research/realism_public.json` (#163).

내부 리포트(`realism_report.json`, 시스템 팀 must_not_read)에는 처치 효과 실측 · 참 4분면(F14~F17)과
모집단 · T0 별 생성 이탈률(F12)이 들어 있다. 공개판은 관측 이벤트로 잰 F1~F11 · F13 만 옮긴다.
숫자는 고치지 않는다.

거르는 방식
- 항목은 허용 목록(PUBLIC_IDS), 항목 · `source` · `rules` 의 최상위 키도 허용 목록으로 고른다.
- 그 아래(`synthetic` · `reference` · `parts`)는 키 경로 허용 목록(ALLOWED_PATHS)에 있는 것만 받는다. 목록 밖
  경로가 하나라도 생기면 **파일을 쓰기 전에** 거부한다 — 사람이 보고 목록을 갱신한다.
- 결과 전체(scope 문구 제외)에서 금지 문자열(Persona · 처치군 T1~T4 · 숨은 영역 · 로컬 경로)을 찾아 하나라도
  있으면 거부한다.
- 판정이 `no_data` 이거나 모르는 값인 항목, verdict 와 맞지 않는 dashboard_verdict, 중복 id 도 거부한다.
- seed 는 정수 하나로 읽히고 확인 seed(47~51)가 아닐 때만 진행한다(목록 · 소수 · 공백 · 없음은 거부).

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
DASHBOARD = {"pass": "consistent", "borderline": "deviates", "fail": "deviates"}  # realism_check.DASHBOARD_VERDICT
CONFIRM_SEEDS = range(47, 52)  # 확인 seed 는 봉인 실측 전용이다 — 공개판 재료로 쓰지 않는다
FORBIDDEN = re.compile(
    r"persona|vip_loyal|price_sensitive|churn_progressing|new_customer|\bloyal\b|\bexplorer\b"
    r"|(?<![A-Za-z0-9])T[1-4](?![0-9])|treat|tau|hidden|ground_truth|sleeping|persuadable|uplift"
    r"|페르소나|고객군|처치|숨은|정답|업리프트|설득|슬리핑"
    r"|/Users/|/home/|/private/|/tmp/|~/|results/|data/|[A-Za-z]:\\|Traceback|Error\b",
    re.IGNORECASE,
)
# 공개판 키 경로 허용 목록. 목록 밖 경로가 생기면 쓰기 전에 거부한다 — 공개해도 되는 값인지 보고 갱신한다.
ALLOWED_PATHS = frozenset(p for p in """
generated_at
metrics[].dashboard_verdict
metrics[].id
metrics[].name
metrics[].note
metrics[].parts
metrics[].parts.aov_krw
metrics[].parts.cart_abandonment
metrics[].parts.customer_mean_aov_cv
metrics[].parts.ln_sd
metrics[].parts.mean
metrics[].parts.median
metrics[].parts.order_ln_sd
metrics[].parts.orders_per_month
metrics[].parts.p75
metrics[].parts.top10
metrics[].parts.top20
metrics[].reference.band.aov_krw[]
metrics[].reference.band.customer_mean_aov_cv[]
metrics[].reference.band.ln_sd[]
metrics[].reference.band.mean[]
metrics[].reference.band.median[]
metrics[].reference.band.order_ln_sd[]
metrics[].reference.band.orders_per_month[]
metrics[].reference.band.p75[]
metrics[].reference.band.top10[]
metrics[].reference.band.top20[]
metrics[].reference.band[]
metrics[].reference.band_text
metrics[].reference.dataset
metrics[].reference.source_ids[]
metrics[].reference.source_url
metrics[].reference.value
metrics[].reference.value.1년간 42일+ 공백 뒤 복귀 가구
metrics[].reference.value.2019
metrics[].reference.value.2020
metrics[].reference.value.2021
metrics[].reference.value.Complete Journey
metrics[].reference.value.Instacart(상한)
metrics[].reference.value.all
metrics[].reference.value.aov_krw
metrics[].reference.value.customer_mean_aov_cv
metrics[].reference.value.grocery
metrics[].reference.value.ln_sd.Complete Journey
metrics[].reference.value.ln_sd.Instacart
metrics[].reference.value.mean
metrics[].reference.value.median
metrics[].reference.value.order_ln_sd($20+)
metrics[].reference.value.orders_per_month[]
metrics[].reference.value.p75
metrics[].reference.value.share_gap_7
metrics[].reference.value.top10.CJ
metrics[].reference.value.top20.CJ
metrics[].reference.value.top20.Instacart(주문)
metrics[].reference.value.top20.KSW
metrics[].reference.value.top20.McCarthy&Winer
metrics[].reference.value.주
metrics[].synthetic.aov_krw
metrics[].synthetic.aov_median_krw
metrics[].synthetic.cart_abandonment_pct
metrics[].synthetic.cj_style_shape_full_span
metrics[].synthetic.customer_mean_aov_cv
metrics[].synthetic.followup_days_median
metrics[].synthetic.ln_sd
metrics[].synthetic.mean
metrics[].synthetic.mean_12w
metrics[].synthetic.median
metrics[].synthetic.median_cv
metrics[].synthetic.n_36000_40000
metrics[].synthetic.n_40000_44000
metrics[].synthetic.n_cart_sessions
metrics[].synthetic.n_customers
metrics[].synthetic.n_customers_exposure
metrics[].synthetic.n_gaps
metrics[].synthetic.n_lines
metrics[].synthetic.n_new_buyers
metrics[].synthetic.n_orders
metrics[].synthetic.n_returned
metrics[].synthetic.n_sessions
metrics[].synthetic.nbd_shape
metrics[].synthetic.order_ln_sd
metrics[].synthetic.orders_per_month
metrics[].synthetic.orders_per_month_exposure
metrics[].synthetic.orders_per_month_median
metrics[].synthetic.p75
metrics[].synthetic.p90
metrics[].synthetic.peak_at_7
metrics[].synthetic.rate
metrics[].synthetic.ratio
metrics[].synthetic.return_rate_among_lapsed
metrics[].synthetic.session_add_to_cart_pct
metrics[].synthetic.session_to_purchase_pct
metrics[].synthetic.share
metrics[].synthetic.share_gap_7
metrics[].synthetic.share_non_first_orders
metrics[].synthetic.share_returned_after_42d_gap
metrics[].synthetic.top10
metrics[].synthetic.top20
metrics[].synthetic.uncapped.ln_sd
metrics[].synthetic.uncapped.mean
metrics[].synthetic.uncapped.median
metrics[].synthetic.uncapped.p95
metrics[].synthetic.var_to_mean
metrics[].synthetic.window_days
metrics[].unit
metrics[].verdict
rules.bands_from
rules.borderline
rules.excluded
rules.multi_part
scope
source.end_exclusive
source.n_customers
source.n_events
source.n_orders
source.random_seed
source.simulator_version
source.span_days
source.start
summary.borderline
summary.fail
summary.pass
""".split("\n") if p)


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


def _paths(obj, prefix=""):
    if isinstance(obj, dict):
        for k, v in obj.items():
            yield from _paths(v, f"{prefix}.{k}" if prefix else str(k))
    elif isinstance(obj, list):
        for v in obj:
            yield from _paths(v, prefix + "[]")
    else:
        yield prefix


def _seed_ok(seed) -> bool:
    if isinstance(seed, bool):
        return False
    if isinstance(seed, str) and seed.isascii() and seed.isdigit():
        seed = int(seed)
    return isinstance(seed, int) and seed not in CONFIRM_SEEDS


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
    mismatched = [i for i in PUBLIC_IDS if by_id[i].get("dashboard_verdict") != DASHBOARD[by_id[i]["verdict"]]]
    if mismatched:
        raise ValueError(f"{mismatched} dashboard_verdict 가 판정과 맞지 않는다 — 공개판을 만들지 않는다")
    source = report.get("source") or {}
    if not _seed_ok(source.get("random_seed")):
        raise ValueError("seed 가 정수 하나가 아니거나 확인 seed(47~51)다 — 공개판을 만들지 않는다")
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
    unknown = sorted(set(_paths(public)) - ALLOWED_PATHS)
    if unknown:
        raise ValueError(f"허용 목록 밖 키 경로 {unknown} — 공개판을 만들지 않는다")
    scanned = {k: v for k, v in public.items() if k != "scope"}  # scope 는 이 스크립트의 고정 문구다
    hits = sorted({h.group() for s in _strings(scanned) for h in [FORBIDDEN.search(s)] if h})
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
