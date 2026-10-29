"""`scripts/research/sim_evidence.py` — #183 ⑥ 기제 증거 계산기.

작은 합성 이벤트로 각 계산이 정의대로 세는지 본다. numpy·pandas 가 없으면 skip 한다(사유: BLOCKED).
"""

from __future__ import annotations

import importlib.util
import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SCRIPT = REPO / "scripts" / "research" / "sim_evidence.py"

try:
    import numpy as np
    import pandas as pd

    _spec = importlib.util.spec_from_file_location("sim_evidence", SCRIPT)
    se = importlib.util.module_from_spec(_spec)
    sys.modules["sim_evidence"] = se
    _spec.loader.exec_module(se)
    rc = se.rc
    HAVE_DEPS = True
except ImportError:  # pragma: no cover - 의존성 없는 CI 잡
    HAVE_DEPS = False

KST = timezone(timedelta(hours=9))
DAY0 = datetime(2025, 1, 1, 10, 0, tzinfo=KST)


def ev(cid: int, day: float, etype: str, session: str | None = None, **kw) -> dict:
    ts = DAY0 + timedelta(days=day)
    row = {"event_id": f"E-{cid}-{day}-{etype}", "customer_id": f"C{cid:08d}",
           "timestamp": ts.isoformat(timespec="milliseconds"), "event_type": etype,
           "session_id": session or f"S-C{cid:08d}-{int(ts.timestamp() * 1000)}",
           "simulator_version": "sim-test", "random_seed": 7}
    row.update(kw)
    return row


def buy(cid: int, day: float) -> dict:
    ts = DAY0 + timedelta(days=day)
    return ev(cid, day, "purchase", order_id=f"O{ts:%Y%m%d}-{cid:03d}{int(day):03d}", order_amount=40000)


def ctx_of(rows: list[dict]):
    return rc.build_context(rc.normalize_events(pd.DataFrame(rows)))


@unittest.skipUnless(HAVE_DEPS, "BLOCKED: numpy/pandas 미설치")
class TestAuc(unittest.TestCase):
    def test_perfect_reversed_and_tied_scores(self):
        positive = np.array([True, True, False, False])
        self.assertEqual(se.auc(np.array([9, 8, 2, 1]), positive), 1.0)
        self.assertEqual(se.auc(np.array([1, 2, 8, 9]), positive), 0.0)
        self.assertEqual(se.auc(np.array([5, 5, 5, 5]), positive), 0.5)

    def test_single_class_is_none_not_a_number(self):
        self.assertIsNone(se.auc(np.array([1, 2]), np.array([True, True])))


@unittest.skipUnless(HAVE_DEPS, "BLOCKED: numpy/pandas 미설치")
class TestRecoveryAndFunnel(unittest.TestCase):
    def test_return_after_42_day_gap_is_a_recovery_case(self):
        rows = [buy(1, 0), buy(1, 50), buy(2, 0), buy(2, 30)]
        r = se.recovery(ctx_of(rows))
        self.assertEqual((r["customers_returned_after_42d_gap"], r["buyers"]), (1, 2))
        self.assertEqual(r["examples"][0], {"customer_id": "C00000001", "returned_on": "2025-02-20", "gap_days": 50})

    def test_funnel_counts_sessions_reaching_each_stage(self):
        rows = []
        for i, stages in enumerate((["product_view", "add_to_cart", "checkout_start"], ["product_view"], [])):
            s = f"S-{i}"
            rows.append(ev(1, i, "session_start", session=s))
            rows += [ev(1, i + 0.01 * k, stage, session=s) for k, stage in enumerate(stages, 1)]
        rows.append(ev(1, 0.05, "purchase", session="S-0", order_id="O20250101-001000", order_amount=40000))
        f = se.funnel(ctx_of(rows))
        self.assertEqual(f["sessions"], 3)
        self.assertEqual([x["sessions"] for x in f["stages"]], [2, 1, 1, 1])
        self.assertEqual(f["cart_abandonment_pct"], 0.0)


@unittest.skipUnless(HAVE_DEPS, "BLOCKED: numpy/pandas 미설치")
class TestPanel(unittest.TestCase):
    def test_label_and_days_since_last_purchase_at_each_t0(self):
        # 관측 0~200일, T0 = 56·86·116일. 고객 1 은 0일에 사고 끝, 고객 2 는 30일·70일에 산다.
        rows = [buy(1, 0), buy(2, 30), buy(2, 70), ev(3, 199.5, "session_start")]
        panel = se._panel(ctx_of(rows))
        # 가입일 대리값 = 첫 이벤트라 56일 T0 에는 아무도 가입 60일을 채우지 못한다.
        self.assertNotIn("2025-02-26", set(panel["T0"]))
        # 86일 T0: 고객 2 는 가입 56일이라 §4.1 eligible 밖이다.
        second = panel[panel["T0"] == "2025-03-28"].set_index("customer_id")
        self.assertEqual(list(second.index), ["C00000001"])
        self.assertEqual(int(second.loc["C00000001", "dsl"]), 86)
        self.assertTrue(bool(second.loc["C00000001", "churned"]))
        # 116일 T0: 고객 2 는 마지막 구매 46일 전, 그 뒤 구매가 없어 이탈.
        third = panel[panel["T0"] == "2025-04-27"].set_index("customer_id")
        self.assertEqual(int(third.loc["C00000002", "dsl"]), 46)
        self.assertTrue(bool(third.loc["C00000002", "churned"]))


    def test_stratified_ratchet_separates_composition_from_hazard(self):
        # 두 T0 모두 [14,42) 구간 이탈률 0%, [90,∞) 구간 100% — 비중만 달라 전체 평균이 오른다.
        panel = pd.DataFrame({
            "T0": ["a", "a", "a", "b", "b", "b"], "dsl": [20, 30, 100, 20, 100, 120],
            "churned": [False, False, True, False, True, True],
        })
        rows = {(r["T0"], r["dsl_bucket"]): r for r in se._stratified(panel)}
        self.assertEqual(rows[("a", "[14, 42)")]["churn_pct"], 0.0)
        self.assertEqual(rows[("b", "[90, 10000)")]["churn_pct"], 100.0)
        self.assertEqual((rows[("a", "[90, 10000)")]["share_pct"], rows[("b", "[90, 10000)")]["share_pct"]), (33.3, 66.7))


    def test_ratchet_table_aligns_series_by_t0(self):
        report = {"population": "x", "n_rows": 1, "history": {}, "recovery": {
            "customers_returned_after_42d_gap": 0, "buyers": 0, "share_pct": None, "gap_days_median": None,
            "gap_days_p90": None, "examples": []},
            "single_variable_dsl": {"pooled_auc": None, "auc_by_T0": {}, "churn_by_dsl": []},
            "funnel": {"sessions": 0, "cart_abandonment_pct": None, "stages": [], "benchmarks": {}},
            "ratchet": {
                "spec41_eligible": {"by_T0": [{"T0": "2025-03-28", "churn_pct": 30.0, "n": 10}],
                                    "min_pct": 30.0, "max_pct": 30.0, "slope_pct_per_30d": None},
                "active42": {"by_T0": [{"T0": "2025-02-26", "churn_pct": 11.0, "n": 5},
                                       {"T0": "2025-03-28", "churn_pct": 12.0, "n": 6}],
                             "min_pct": 11.0, "max_pct": 12.0, "slope_pct_per_30d": 1.0},
                "spec41_by_dsl": [], "decomposition": None, "spec41_by_dsl_and_signup": []}}
        md = se.render_md(report)
        self.assertIn("| 2025-02-26 | — | — | 11.0 | 5 |", md)
        self.assertIn("| 2025-03-28 | 30.0 | 10 | 12.0 | 6 |", md)


    def test_decomposition_splits_within_bucket_and_composition(self):
        # a: [14,42) 2명 이탈 0 · [90,∞) 1명 이탈 → 33.3%. b: [14,42) 1명 이탈 → 구간 안 변화 1.0 × 비중 2/3.
        panel = pd.DataFrame({
            "T0": ["a", "a", "a", "b", "b", "b"], "dsl": [20, 30, 100, 20, 100, 120],
            "churned": [False, False, True, True, True, True],
        })
        d = se.decompose(panel)
        self.assertEqual((d["total_pp"], d["within_bucket_pp"]), (66.67, 66.67))
        self.assertEqual(d["composition_pp"], 0.0)


@unittest.skipUnless(HAVE_DEPS, "BLOCKED: numpy/pandas 미설치")
class TestSameDefinitionsAsRealismCheck(unittest.TestCase):
    """docstring·증거 문서가 "f12 와 같다" 고 적는 두 계열을 f12 계산과 대조한다 — 한쪽만 고치면 여기서 갈라진다."""

    @classmethod
    def setUpClass(cls):
        rows = []
        patterns = {
            1: range(0, 300, 10),          # 꾸준히 산다
            2: range(0, 101, 15),          # 100일 뒤 끊긴다
            3: (0, 70, 150, 230),          # 긴 공백 뒤 복귀
            4: range(80, 300, 20),         # 늦게 시작
            5: (5,),                       # 한 번만
            6: (0, 41, 83, 125, 167),      # 42일 경계 근처 간격
            7: (30, 45, 200),
        }
        for cid, days in patterns.items():
            rows += [buy(cid, d) for d in days]
        rows.append(ev(9, 299.5, "session_start"))  # 관측 300일
        cls.ctx = ctx_of(rows)
        cls.f12 = {r["T0"]: r for r in rc.f12(cls.ctx).synthetic["by_T0"]}

    def test_spec41_series_matches_f12(self):
        panel = se._panel(self.ctx)
        ours = (100 * panel.groupby("T0")["churned"].mean()).round(2).to_dict()
        theirs = {t: r["churn_spec41_pct"] for t, r in self.f12.items() if r["churn_spec41_pct"] is not None}
        self.assertTrue(theirs)
        self.assertEqual(ours, theirs)

    def test_active42_series_matches_f12_reference(self):
        ours = {x["T0"]: x["churn_pct"] for x in se._series(se._active42(self.ctx))["by_T0"]}
        theirs = {t: r["churn_active42_pct"] for t, r in self.f12.items() if r["churn_active42_pct"] is not None}
        self.assertTrue(theirs)
        self.assertEqual(ours, theirs)


@unittest.skipUnless(HAVE_DEPS, "BLOCKED: numpy/pandas 미설치")
class TestEmptyPopulations(unittest.TestCase):
    def test_series_drops_t0_without_population(self):
        by = pd.DataFrame({"T0": ["a", "b", "c"], "mean": [0.2, np.nan, 0.3], "size": [5, 0, 5]})
        out = se._series(by)
        self.assertEqual([x["T0"] for x in out["by_T0"]], ["a", "c"])
        self.assertEqual((out["min_pct"], out["max_pct"]), (20.0, 30.0))
        self.assertIsNone(se._series(by.iloc[[1]])["min_pct"])

    def test_no_eligible_customer_is_named_as_such(self):
        # 관측 0~200일이라 T0(56·86·116·146일)는 있지만, 유일한 구매 고객이 150일에 처음 나타나 어느 T0 에도 eligible 이 아니다.
        rows = [ev(3, 0, "session_start"), buy(1, 150), ev(2, 199.5, "session_start")]
        report = se.build(ctx_of(rows))
        self.assertIn("eligible 고객이 없다", report["error"])

    def test_too_short_observation_is_named_as_such(self):
        report = se.build(ctx_of([buy(1, 0), ev(2, 50.5, "session_start")]))
        self.assertIn("사전 창 56일", report["error"])


if __name__ == "__main__":
    unittest.main()
