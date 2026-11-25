"""scripts/realism_public.py — 공개판에 정답 · 생성 이탈률 · 숨은 값 · 로컬 경로가 들어가지 않는다."""
import copy
import importlib.util
import json
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location("realism_public", REPO / "scripts" / "realism_public.py")
rp = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(rp)

# 커밋된 공개판의 키 경로. 바뀌면 이 테스트가 깨진다 — 새 키가 공개해도 되는 값인지 보고 갱신한다.
COMMITTED_PATHS = """
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
""".split("\n")


def _paths(obj, prefix=""):
    if isinstance(obj, dict):
        for k, v in obj.items():
            yield from _paths(v, f"{prefix}.{k}" if prefix else k)
    elif isinstance(obj, list):
        for v in obj:
            yield from _paths(v, prefix + "[]")
    else:
        yield prefix


def _report():
    metrics = [{"id": f"F{i}", "name": f"m{i}", "verdict": "pass", "secret": 1,
                "synthetic": {"median": 7.0}} for i in range(1, 18)]
    return {"generated_at": "t", "source": {"events": "/local/path", "random_seed": "42", "guardrail": True},
            "rules": {"bands_from": "x", "extra": "y"}, "summary": {}, "metrics": metrics}


class RealismPublicTest(unittest.TestCase):
    def test_only_observational_metrics_and_keys(self):
        public = rp.make_public(_report())
        self.assertEqual([m["id"] for m in public["metrics"]], [f"F{i}" for i in (*range(1, 12), 13)])
        self.assertTrue(all("secret" not in m for m in public["metrics"]))
        self.assertEqual(public["source"], {"random_seed": "42"})
        self.assertEqual(public["rules"], {"bands_from": "x"})
        self.assertEqual(public["summary"]["pass"], 12)

    def test_refuses(self):
        cases = {
            "missing": lambda r: r.update(metrics=[m for m in r["metrics"] if m["id"] != "F5"]),
            "duplicate": lambda r: r["metrics"].append(dict(r["metrics"][0])),
            "no_data": lambda r: r["metrics"][2].update(verdict="no_data"),
            "confirm seed": lambda r: r["source"].update(random_seed="49"),
            "nested persona": lambda r: r["metrics"][0]["synthetic"].update(by_persona={"vip_loyal": 1}),
            "nested arm": lambda r: r["metrics"][0]["synthetic"].update(lift={"T3": 1}),
            "local path": lambda r: r["metrics"][0].update(note="/Users/x/realism_report.json"),
            "exception note": lambda r: r["metrics"][0].update(note="KeyError: 'x'"),
        }
        for name, mutate in cases.items():
            report = copy.deepcopy(_report())
            mutate(report)
            with self.subTest(name), self.assertRaises(ValueError):
                rp.make_public(report)

    def test_committed_file(self):
        public = json.loads((REPO / "docs" / "research" / "realism_public.json").read_text(encoding="utf-8"))
        self.assertEqual(sorted(set(_paths(public))), [p for p in COMMITTED_PATHS if p])
        self.assertEqual([m["id"] for m in public["metrics"]], list(rp.PUBLIC_IDS))
        self.assertFalse([s for s in rp._strings(public) if rp.FORBIDDEN.search(s)])


if __name__ == "__main__":
    unittest.main()
