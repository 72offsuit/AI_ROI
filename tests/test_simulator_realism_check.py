"""`scripts/research/realism_check.py` — 실현 로그 ↔ 외부 stylized fact F1~F17 계산기.

작은 합성 이벤트(측정 계약 형식)로 각 계산기가 정의대로 세는지 본다.
기준 띠(`data_grounding.md` §4)의 사본이 문서와 같은지도 대조한다 — 결과를 보고 띠를 옮기면 여기서 걸린다.

numpy·pandas 가 없으면 skip 한다(사유: BLOCKED). skip 은 통과가 아니다.
"""

from __future__ import annotations

import gzip
import importlib.util
import json
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SCRIPT = REPO / "scripts" / "research" / "realism_check.py"

try:
    import numpy  # noqa: F401
    import pandas as pd

    _spec = importlib.util.spec_from_file_location("realism_check", SCRIPT)
    rc = importlib.util.module_from_spec(_spec)
    sys.modules["realism_check"] = rc  # dataclass 가 모듈을 찾는다
    _spec.loader.exec_module(rc)
    HAVE_DEPS = True
except ImportError:  # pragma: no cover - 의존성 없는 CI 잡
    HAVE_DEPS = False

KST = timezone(timedelta(hours=9))
DAY0 = datetime(2025, 1, 1, 10, 0, tzinfo=KST)


def ev(cid: int, day: float, etype: str, **kw) -> dict:
    ts = DAY0 + timedelta(days=day)
    row = {
        "event_id": f"00000000-0000-4000-8000-{abs(hash((cid, day, etype, str(kw)))) % 10**12:012d}",
        "customer_id": f"C{cid:08d}",
        "timestamp": ts.isoformat(timespec="milliseconds"),
        "event_type": etype,
        "simulator_version": "sim-test",
        "random_seed": 7,
    }
    row.update(kw)
    return row


def buy(cid: int, day: float, amount: int = 45000, n: list[int] | None = None, session: str | None = None, **kw) -> dict:
    n = n if n is not None else [0]
    n[0] += 1
    ts = DAY0 + timedelta(days=day)
    oid = f"O{ts:%Y%m%d}-{cid % 1000:03d}{int(day * 10) % 1000:03d}"
    return ev(cid, day, "purchase", order_id=oid, order_amount=amount,
              session_id=session or f"S-C{cid:08d}-{int(ts.timestamp() * 1000)}", **kw)


def ctx_of(rows: list[dict], **kw):
    return rc.build_context(rc.normalize_events(pd.DataFrame(rows)), **kw)


@unittest.skipUnless(HAVE_DEPS, "BLOCKED: numpy/pandas 미설치")
class TestJudge(unittest.TestCase):
    def test_band_and_borderline_are_twenty_percent_of_nearest_bound(self):
        self.assertEqual(rc.judge(7, 5, 10), "pass")
        self.assertEqual(rc.judge(5, 5, 10), "pass")
        self.assertEqual(rc.judge(4.0, 5, 10), "borderline")
        self.assertEqual(rc.judge(3.9, 5, 10), "fail")
        self.assertEqual(rc.judge(12.0, 5, 10), "borderline")
        self.assertEqual(rc.judge(12.1, 5, 10), "fail")
        self.assertEqual(rc.judge(None, 5, 10), "no_data")
        self.assertEqual(rc.judge(float("nan"), 5, 10), "no_data")

    def test_open_lower_bound(self):
        self.assertEqual(rc.judge_open_lower(1.2, 1.0), "pass")
        self.assertEqual(rc.judge_open_lower(1.0, 1.0), "borderline")
        self.assertEqual(rc.judge_open_lower(0.79, 1.0), "fail")
        self.assertEqual(rc.judge_open_lower(0.0, 0.0), "fail")
        self.assertEqual(rc.judge_open_lower(0.01, 0.0), "pass")

    def test_partial_measurement_is_never_a_pass(self):
        self.assertEqual(rc.worst(["pass", "no_data"]), "no_data")
        self.assertEqual(rc.worst(["pass", "borderline"]), "borderline")
        self.assertEqual(rc.worst(["borderline", "fail", "pass"]), "fail")
        self.assertEqual(rc.worst([]), "no_data")


@unittest.skipUnless(HAVE_DEPS, "BLOCKED: numpy/pandas 미설치")
class TestBandsMatchTheDocument(unittest.TestCase):
    """§4 표의 띠가 코드 사본과 같다. 결과를 본 뒤 한쪽만 고치면 깨진다."""

    def test_band_text_appears_in_section_4(self):
        doc = (REPO / "docs" / "research" / "data_grounding.md").read_text(encoding="utf-8")
        section = doc.split("## §4", 1)[1].split("## §5", 1)[0]
        expected = {
            "F1": ["**5~10일**", "**9~15일**", "**12~20일**"], "F2": ["**0.45~0.70**"],
            "F3": ["**12~18일**", "**0.5~0.9**"], "F4": ["**2.0~3.2회**", "**38,000~55,000원**"],
            "F5": ["**0.5~1.5**"], "F6": ["**0.53~0.73**", "**0.33~0.50**"],
            "F7": ["**0.4~0.8**", "**0.5~0.8**"], "F8": ["**> 1**"], "F9": ["**50~75%**"],
            "F10": ["**0.50~0.65**"], "F11": ["**0.55~0.75**"], "F12": ["**15~25%**"],
            "F14": ["**3~6%p**"], "F16": ["**8~15%**", "±0.5%p"], "F17": ["**> 0**"],
        }
        for fid, needles in expected.items():
            row = next(line for line in section.splitlines() if line.startswith(f"| {fid} |"))
            for needle in needles:
                self.assertIn(needle, row, f"{fid}: §4 표에 {needle} 가 없다 — 띠가 바뀌었나")
        self.assertEqual(rc.BANDS["F15"], [5, 20])            # §3 사용자 결정 (a)
        self.assertEqual(rc.BANDS["F16"]["persuadable"], [11, 21])
        self.assertEqual(set(rc.SPECS), {f"F{i}" for i in range(1, 18)})
        self.assertEqual(set(rc.BANDS), set(rc.SPECS))


@unittest.skipUnless(HAVE_DEPS, "BLOCKED: numpy/pandas 미설치")
class TestGapFacts(unittest.TestCase):
    def test_clock_like_buyer_has_zero_cv_and_exact_gaps(self):
        rows = [buy(c, d) for c in (1, 2) for d in range(0, 70, 7)]  # 주 1회 시계
        ctx = ctx_of(rows)
        r1 = rc.f1(ctx)
        self.assertEqual(r1.synthetic["median"], 7.0)
        self.assertEqual(r1.synthetic["mean"], 7.0)
        self.assertEqual(r1.parts["median"], "pass")
        self.assertEqual(r1.parts["mean"], "fail")          # 7 < 9×0.8
        r2 = rc.f2(ctx)
        self.assertEqual(r2.synthetic["median_cv"], 0.0)
        self.assertEqual(r2.verdict, "fail")                 # 시계는 불규칙성이 없다

    def test_gaps_are_capped_at_30_like_instacart(self):
        rows = [buy(1, d) for d in (0, 60, 70, 80)]
        r1 = rc.f1(ctx_of(rows))
        self.assertEqual(r1.synthetic["n_gaps"], 3)
        self.assertAlmostEqual(r1.synthetic["mean"], (30 + 10 + 10) / 3, places=2)
        self.assertAlmostEqual(r1.synthetic["uncapped"]["mean"], (60 + 10 + 10) / 3, places=2)

    def test_f3_needs_three_gaps_and_reports_ln_sd(self):
        rows = [buy(1, d) for d in (0, 10, 20, 30)] + [buy(2, d) for d in (0, 20, 40, 60)] + [buy(3, d) for d in (0, 5)]
        r = rc.f3(ctx_of(rows))
        self.assertEqual(r.synthetic["n_customers"], 2)    # 고객 3 은 간격 1개
        self.assertAlmostEqual(r.synthetic["ln_sd"], abs(__import__("math").log(20 / 10)) / 2, places=3)

    def test_no_purchases_is_no_data_not_zero(self):
        rows = [ev(1, 0, "session_start", session_id="S-C00000001-1", page_type="home")]
        ctx = ctx_of(rows)
        for fn in (rc.f1, rc.f2, rc.f3, rc.f4, rc.f6, rc.f7, rc.f8, rc.f11, rc.f12, rc.f13):
            self.assertEqual(fn(ctx).verdict, "no_data", fn.__name__)


@unittest.skipUnless(HAVE_DEPS, "BLOCKED: numpy/pandas 미설치")
class TestVolumeAndValue(unittest.TestCase):
    def test_f4_rate_uses_exposure_from_first_event(self):
        rows = [ev(1, 0, "session_start", session_id="S-C00000001-1", page_type="home")]
        rows += [buy(1, d, amount=40000) for d in (1, 15, 30, 45)]
        rows += [ev(1, 59.5, "session_start", session_id="S-C00000001-2", page_type="home")]  # 관측 60일
        r = rc.f4(ctx_of(rows))
        self.assertAlmostEqual(r.synthetic["orders_per_month"], round(4 * rc.MONTH_DAYS / 60, 2))
        self.assertEqual(r.synthetic["aov_krw"], 40000)
        self.assertEqual(r.parts["aov_krw"], "pass")

    def test_f6_pareto_shares(self):
        rows = [buy(1, 0, amount=910_000)] + [buy(c, 0, amount=10_000) for c in range(2, 11)]
        r = rc.f6(ctx_of(rows))
        self.assertAlmostEqual(r.synthetic["top20"], (910_000 + 10_000) / 1_000_000, places=3)
        self.assertAlmostEqual(r.synthetic["top10"], 0.91, places=3)
        self.assertEqual(r.parts["top20"], "fail")

    def test_f7_and_f8(self):
        amounts = [36500, 41000, 42000, 43000, 30000, 60000]
        rows = [buy(c, c, amount=a) for c, a in enumerate(amounts, start=1)]
        ctx = ctx_of(rows)
        r8 = rc.f8(ctx)
        self.assertEqual((r8.synthetic["n_40000_44000"], r8.synthetic["n_36000_40000"]), (3, 1))
        self.assertEqual(r8.synthetic["ratio"], 3.0)
        self.assertEqual(r8.verdict, "pass")
        r7 = rc.f7(ctx)
        self.assertAlmostEqual(r7.synthetic["order_ln_sd"], round(float(pd.Series(amounts).map(__import__("math").log).std()), 3))

    def test_f8_without_comparison_bin_is_no_data(self):
        r = rc.f8(ctx_of([buy(1, 0, amount=41000)]))
        self.assertEqual(r.verdict, "no_data")

    def test_f5_overdispersion_gives_finite_shape(self):
        rows = [ev(c, 0, "session_start", session_id=f"S-C{c:08d}-1", page_type="home") for c in range(1, 41)]
        for c in range(1, 41):
            k = (c % 4) * 3                                  # 0·3·6·9 건 — 과대분산
            rows += [buy(c, 120 + i * 5) for i in range(k)]  # 창 [106, 190) 안
            rows.append(buy(c, 5))                            # 창 밖 구매 1건 (구매 고객)
        rows.append(ev(1, 189.5, "session_start", session_id="S-C00000001-9", page_type="home"))
        r = rc.f5(ctx_of(rows))
        self.assertNotEqual(r.verdict, "no_data")
        self.assertEqual(r.synthetic["n_customers"], 40)
        m, v = 4.5, float(pd.Series([(c % 4) * 3 for c in range(1, 41)]).var())
        self.assertAlmostEqual(r.synthetic["nbd_shape"], round(m * m / (v - m), 3))


@unittest.skipUnless(HAVE_DEPS, "BLOCKED: numpy/pandas 미설치")
class TestFunnelAndChurn(unittest.TestCase):
    def test_f9_cart_abandonment_by_session(self):
        rows = []
        for i in range(4):
            sid = f"S-C00000001-{i}"
            rows.append(ev(1, i, "add_to_cart", session_id=sid, page_type="detail", product_id="P0001",
                           category="dairy", quantity=1, unit_price=1000))
        rows.append(buy(1, 0.01, session="S-C00000001-0"))
        r = rc.f9(ctx_of(rows))
        self.assertEqual(r.synthetic["cart_abandonment_pct"], 75.0)
        self.assertEqual(r.verdict, "pass")

    def test_f9_without_any_purchase_is_no_data(self):
        rows = [ev(1, 0, "add_to_cart", session_id="S-C00000001-0", page_type="detail", product_id="P0001",
                   category="dairy", quantity=1, unit_price=1000)]
        self.assertEqual(rc.f9(ctx_of(rows)).verdict, "no_data")

    def test_f12_churn_is_eligible_without_purchase_in_42_days(self):
        rows = []
        for c in range(1, 11):
            rows.append(buy(c, 10))
            if c <= 8:                                        # 8명은 T0 뒤에도 산다
                rows += [buy(c, d) for d in range(60, 160, 20)]
        rows.append(ev(1, 159.5, "session_start", session_id="S-C00000001-9", page_type="home"))
        r = rc.f12(ctx_of(rows))
        first = r.synthetic["by_T0"][0]
        self.assertEqual(first["eligible"], 10)
        self.assertEqual(first["churn_pct"], 20.0)
        self.assertEqual(r.synthetic["churn_pct_mean"], 20.0)
        self.assertEqual(r.verdict, "pass")

    def test_f13_detects_return_after_long_gap(self):
        rows = [buy(1, d) for d in (0, 10, 70)] + [buy(2, d) for d in (0, 10, 20)]
        rows.append(ev(2, 120, "session_start", session_id="S-C00000002-9", page_type="home"))
        r = rc.f13(ctx_of(rows))
        self.assertEqual(r.synthetic["n_returned"], 1)
        self.assertEqual(r.synthetic["share_returned_after_42d_gap"], 0.5)
        self.assertEqual(r.synthetic["return_rate_among_lapsed"], 0.5)   # 고객 2 는 끝에서 100일 공백
        self.assertEqual(r.verdict, "pass")

    def test_f13_absorbing_churn_fails(self):
        rows = [buy(1, d) for d in (0, 10, 20)]
        rows.append(ev(1, 120, "session_start", session_id="S-C00000001-9", page_type="home"))
        self.assertEqual(rc.f13(ctx_of(rows)).verdict, "fail")


@unittest.skipUnless(HAVE_DEPS, "BLOCKED: numpy/pandas 미설치")
class TestExchangeFacts(unittest.TestCase):
    def test_f10_reorder_share_on_fourth_and_later_orders(self):
        orders = pd.DataFrame([
            {"order_id": f"O20250101-00000{i}", "customer_id": "C00000001",
             "ordered_at": f"2025-01-0{i + 1}T10:00:00.000+09:00"} for i in range(5)])
        lines = [("O20250101-000000", "P0001"), ("O20250101-000001", "P0002"), ("O20250101-000002", "P0003"),
                 ("O20250101-000003", "P0001"), ("O20250101-000003", "P0009"),
                 ("O20250101-000004", "P0002"), ("O20250101-000004", "P0009")]
        items = pd.DataFrame([{"order_id": o, "product_id": p} for o, p in lines])
        ctx = ctx_of([buy(1, 0)], exchange={"orders": orders, "order_items": items})
        r = rc.f10(ctx)
        self.assertEqual(r.synthetic["n_lines"], 4)
        self.assertEqual(r.synthetic["share"], 0.75)        # P0001 ✓ P0009 ✗ | P0002 ✓ P0009 ✓

    def test_f10_without_exchange_is_no_data(self):
        r = rc.f10(ctx_of([buy(1, 0)]))
        self.assertEqual(r.verdict, "no_data")
        self.assertIn("add_to_cart", r.note)

    def test_f11_new_customer_repurchase_from_signup(self):
        rows = [ev(1, 0, "session_start", session_id="S-C00000001-0", page_type="home")]
        rows += [buy(2, 40), buy(2, 50), buy(3, 40), buy(4, 30), buy(4, 31)]
        customers = pd.DataFrame([
            {"customer_id": "C00000001", "signup_date": "2024-06-01"},
            {"customer_id": "C00000002", "signup_date": "2025-02-01"},
            {"customer_id": "C00000003", "signup_date": "2025-02-01"},
            {"customer_id": "C00000004", "signup_date": "2025-01-20"},
        ])
        r = rc.f11(ctx_of(rows, exchange={"customers": customers}))
        self.assertEqual(r.synthetic["n_new_buyers"], 3)
        self.assertAlmostEqual(r.synthetic["rate"], round(2 / 3, 3))


@unittest.skipUnless(HAVE_DEPS, "BLOCKED: numpy/pandas 미설치")
class TestTreatmentFacts(unittest.TestCase):
    def setUp(self):
        self.at = pd.Timestamp(DAY0 + timedelta(days=10)).tz_convert("Asia/Seoul")
        rows, assign = [], []
        for c in range(1, 21):
            arm = "T3" if c <= 10 else "T0"
            assign.append({"customer_id": f"C{c:08d}", "treatment_id": arm, "assigned_at": self.at})
            rows.append(buy(c, 0, amount=50000))
            retained = (c <= 6) if arm == "T3" else (c <= 14)  # T3 6/10, T0 4/10
            if retained:
                if arm == "T3" and c <= 2:                      # 쿠폰 사용 2명
                    b = buy(c, 15, amount=60000, coupon_id="CPN-AAAAAA")
                    rows.append(b)
                    rows.append(ev(c, 15.001, "coupon_use", session_id=b["session_id"], order_id=b["order_id"],
                                   order_amount=60000, coupon_id="CPN-AAAAAA", campaign_id="CMP-20250111-001"))
                else:
                    rows.append(buy(c, 20, amount=50000))
        rows.append(ev(1, 59.5, "session_start", session_id="S-C00000001-9", page_type="home"))
        self.rows = rows
        self.assign = pd.DataFrame(assign)

    def test_f14_itt_from_assignment_file(self):
        r = rc.f14(ctx_of(self.rows, assignments=self.assign))
        self.assertEqual(r.synthetic["basis"], "log_itt")
        self.assertEqual(r.synthetic["retention_T3_pct"], 60.0)
        self.assertEqual(r.synthetic["retention_T0_pct"], 40.0)
        self.assertEqual(r.synthetic["ate_pp"], 20.0)
        self.assertEqual(r.verdict, "fail")

    def test_f14_falls_back_to_ground_truth_and_otherwise_no_data(self):
        r = rc.f14(ctx_of(self.rows, guardrail={"ate_bp": {"T3": 462}}))
        self.assertEqual(r.synthetic["basis"], "ground_truth")
        self.assertEqual(r.synthetic["ate_pp"], 4.62)
        self.assertEqual(r.verdict, "pass")
        self.assertEqual(rc.f14(ctx_of(self.rows)).verdict, "no_data")

    def test_f15_denominator_is_all_coupon_treated(self):
        r = rc.f15(ctx_of(self.rows, assignments=self.assign))
        self.assertEqual(r.synthetic["n_treated"], 10)
        self.assertEqual(r.synthetic["rate_pct"], 20.0)
        self.assertAlmostEqual(r.synthetic["rate_among_buyers_pct_ref"], round(100 * 2 / 6, 2))
        self.assertEqual(r.verdict, "pass")

    def test_f17_share_of_increment_outside_coupon_orders(self):
        r = rc.f17(ctx_of(self.rows, assignments=self.assign))
        # 1인당: 처치 (2×60000 + 4×50000)/10 = 32000, 미사용 20000, 통제 4×50000/10 = 20000
        self.assertEqual(r.synthetic["rev_treated_krw"], 32000)
        self.assertEqual(r.synthetic["rev_treated_non_coupon_krw"], 20000)
        self.assertEqual(r.synthetic["share_non_coupon"], 0.0)
        self.assertEqual(r.verdict, "fail")

    def test_label_window_beyond_observation_is_no_data(self):
        late = self.assign.assign(assigned_at=self.at + pd.Timedelta(days=30))
        self.assertEqual(rc.f14(ctx_of(self.rows, assignments=late)).verdict, "no_data")


@unittest.skipUnless(HAVE_DEPS, "BLOCKED: numpy/pandas 미설치")
class TestGuardrailFacts(unittest.TestCase):
    def test_identity_holds(self):
        g = {"ate": 0.05, "sleeping_dog_rate": 0.10, "persuadable_rate": 0.152}
        r = rc.f16(ctx_of([buy(1, 0)], guardrail=g))
        self.assertEqual(r.synthetic["identity_gap_pp"], 0.2)
        self.assertEqual(r.verdict, "pass")

    def test_identity_broken_fails(self):
        g = {"guardrails": {"ate": {"value": 0.05}, "sleeping_dog_rate": 0.10, "persuadable_rate": 0.20}}
        self.assertEqual(rc.f16(ctx_of([buy(1, 0)], guardrail=g)).parts["identity"], "fail")

    def test_simulator_bp_format(self):
        g = {"ate_bp": {"T3": 462}, "sleeping_dog_bp": 1100,
             "response_mix_bp": {"T3": {"positive": 1500, "neutral": 7462, "negative": 1038}}}
        r = rc.f16(ctx_of([buy(1, 0)], guardrail=g))
        self.assertEqual(r.synthetic["persuadable_pct"], 15.0)
        self.assertEqual(r.synthetic["sleeping_dog_pct"], 10.38)
        self.assertEqual(r.synthetic["population_sleeping_dog_pct_ref"], 11.0)
        self.assertEqual(r.verdict, "pass")

    def test_missing_keys_are_no_data(self):
        r = rc.f16(ctx_of([buy(1, 0)], guardrail={"ate_bp": {"T3": 462}}))
        self.assertEqual(r.verdict, "no_data")
        self.assertIn("persuadable_rate", r.note)
        self.assertEqual(rc.f16(ctx_of([buy(1, 0)])).verdict, "no_data")


@unittest.skipUnless(HAVE_DEPS, "BLOCKED: numpy/pandas 미설치")
class TestReportEndToEnd(unittest.TestCase):
    def test_cli_reads_sink_root_and_writes_dashboard_contract(self):
        rows = [buy(c, d, amount=30000 + 1000 * c) for c in range(1, 6) for d in range(0, 120, 9 + c)]
        with tempfile.TemporaryDirectory() as tmp:
            part = Path(tmp, "raw", "events", "date=2025-01-01")
            part.mkdir(parents=True)
            with gzip.open(part / "part-0000.jsonl.gz", "wt", encoding="utf-8") as fh:
                for row in rows:
                    fh.write(json.dumps(row) + "\n")
            out_json, out_md = Path(tmp, "r.json"), Path(tmp, "r.md")
            code = rc.main(["--events", str(Path(tmp, "raw")), "--out-json", str(out_json), "--out-md", str(out_md)])
            self.assertEqual(code, 0)
            rep = json.loads(out_json.read_text(encoding="utf-8"))
            md = out_md.read_text(encoding="utf-8")
        self.assertEqual(set(rep), {"generated_at", "source", "rules", "metrics", "summary"})
        for key in ("events", "n_customers", "n_orders", "span_days", "simulator_version", "random_seed"):
            self.assertIn(key, rep["source"])
        self.assertEqual(rep["source"]["n_customers"], 5)
        self.assertEqual(rep["source"]["simulator_version"], "sim-test")
        self.assertEqual([m["id"] for m in rep["metrics"]], [f"F{i}" for i in range(1, 18)])
        self.assertEqual(sum(rep["summary"].values()), 17)
        for m in rep["metrics"]:
            self.assertIn(m["verdict"], rc.VERDICTS)
            self.assertEqual(m["dashboard_verdict"], rc.DASHBOARD_VERDICT[m["verdict"]])
            self.assertIn("band", m["reference"])
            self.assertTrue(m["reference"]["source_url"].startswith("http"), m["id"])
            if m["verdict"] == "no_data":
                self.assertTrue(m["note"], f"{m['id']}: no_data 는 사유가 있어야 한다")
        for fid in ("F10", "F14", "F15", "F16", "F17"):      # 교환·배정·가드레일 없음
            self.assertEqual(next(m for m in rep["metrics"] if m["id"] == fid)["verdict"], "no_data")
        self.assertIn("| F16 |", md)
        self.assertIn("\\|P − D − ATE\\|", md)                # 표 안의 | 는 이스케이프


if __name__ == "__main__":
    unittest.main()
