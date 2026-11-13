"""12개월 CLV — BG/NBD + Gamma-Gamma (#217 2부). 합성 데이터 기준 — 실제 결과 아님.

실행:
    python -m unittest tests.test_clv_lifetime -v
"""

from __future__ import annotations

import importlib.util
import pickle
import unittest

HAVE_DEPS = all(importlib.util.find_spec(name) is not None for name in ("numpy", "pandas", "scipy"))
SKIP_REASON = "BLOCKED: numpy/pandas/scipy 미설치"

TRUE_BG = {"r": 0.8, "alpha": 20.0, "a": 1.5, "b": 3.0}
TRUE_GG = {"p": 4.0, "q": 3.5, "v": 30000.0}  # E[M] = p·v/(q−1) = 48,000


def _event(cid, ts, order, amount, *, event_type="purchase", event_id=None):
    return {"customer_id": cid, "event_type": event_type, "event_id": event_id or f"e-{order}",
            "order_id": order, "order_amount": amount, "timestamp": ts}


def _simulate_summary(n, seed, T_max=365.0):
    """BG/NBD 생성 과정 그대로(연속 시간) — 첫 거래 시각 0, 반복 거래 뒤에만 이탈."""
    import numpy as np
    import pandas as pd

    rng = np.random.default_rng(seed)
    rows = []
    for i in range(n):
        lam = rng.gamma(TRUE_BG["r"], 1 / TRUE_BG["alpha"])
        p = rng.beta(TRUE_BG["a"], TRUE_BG["b"])
        T = rng.uniform(T_max / 2, T_max)
        t, x, tx = 0.0, 0, 0.0
        while True:
            t += rng.exponential(1 / lam)
            if t >= T:
                break
            x, tx = x + 1, t
            if rng.random() < p:
                break
        rows.append({"frequency": float(x), "recency": tx, "T": T, "monetary_value": float("nan")})
    return pd.DataFrame(rows, index=pd.Index([f"S{i:05d}" for i in range(n)], name="customer_id"))


def _simulate_events(n, seed, start, days):
    """같은 과정을 구매 이벤트로 — 금액은 Gamma-Gamma(고객별 ν ~ Gamma(q, v), 건당 ~ Gamma(p, ν))."""
    import numpy as np
    import pandas as pd

    rng = np.random.default_rng(seed)
    rows, oid = [], 0
    for i in range(n):
        lam = rng.gamma(TRUE_BG["r"], 1 / TRUE_BG["alpha"])
        p = rng.beta(TRUE_BG["a"], TRUE_BG["b"])
        nu = rng.gamma(TRUE_GG["q"], 1 / TRUE_GG["v"])
        t, first = rng.uniform(0, days / 6), True
        while t < days:
            oid += 1
            rows.append(_event(f"C{i:05d}", start + pd.Timedelta(days=t), f"o{oid}", float(rng.gamma(TRUE_GG["p"], 1 / nu))))
            if not first and rng.random() < p:
                break
            first = False
            t += rng.exponential(1 / lam)
    return pd.DataFrame(rows)


@unittest.skipUnless(HAVE_DEPS, SKIP_REASON)
class TestRfmSummary(unittest.TestCase):
    def test_hand_example(self) -> None:
        import math

        import pandas as pd

        from src.decision.clv_lifetime import rfm_summary

        kst = "Asia/Seoul"
        t = lambda s: pd.Timestamp(s, tz=kst)  # noqa: E731
        events = pd.DataFrame([
            # A: 1/3 두 주문(00:30 KST 는 UTC 로 전날 — KST 날짜로 묶여야 한다) → 하루 1 거래
            _event("A", t("2026-01-03 00:30"), "o1", 1000.0),
            _event("A", t("2026-01-03 15:00"), "o2", 500.0),
            _event("A", t("2026-01-10 12:00"), "o3", 4000.0),
            _event("A", t("2026-01-22 23:30"), "o4", 8000.0),
            _event("A", t("2026-01-22 23:31"), "o4", 8000.0, event_id="dup"),  # 같은 주문 중복 이벤트
            _event("A", t("2026-01-25 10:00"), None, None, event_type="add_to_cart", event_id="cart"),
            # B: 반복 거래 금액 결손 → monetary NaN(0 이 아니다)
            _event("B", t("2026-01-05 10:00"), "o5", 2000.0),
            _event("B", t("2026-01-20 10:00"), "o6", None),
            # C: 기준 시각과 같은 시각의 구매만 — 기준 시각 '미만' 규칙으로 빠진다
            _event("C", t("2026-02-01 00:00"), "o7", 3000.0),
            # D: 한 번만 구매 → frequency 0
            _event("D", t("2026-01-30 10:00"), "o8", 7000.0),
        ])
        summary = rfm_summary(events, t("2026-02-01 00:00"))

        self.assertEqual(["A", "B", "D"], list(summary.index))
        a = summary.loc["A"]
        self.assertEqual((2.0, 19.0, 29.0, 6000.0, 4), (a["frequency"], a["recency"], a["T"], a["monetary_value"],
                                                        int(a["n_orders"])))
        self.assertEqual(1.0, summary.loc["B", "frequency"])
        self.assertTrue(math.isnan(summary.loc["B", "monetary_value"]))
        self.assertEqual((0.0, 0.0, 2.0), tuple(summary.loc["D", ["frequency", "recency", "T"]]))
        self.assertTrue(math.isnan(summary.loc["D", "monetary_value"]))

    def test_no_purchases_gives_empty_frame_with_columns(self) -> None:
        import pandas as pd

        from src.decision.clv_lifetime import rfm_summary

        ts = pd.Timestamp("2026-01-05", tz="Asia/Seoul")
        events = pd.DataFrame([_event("A", ts, None, None, event_type="add_to_cart")])
        out = rfm_summary(events, pd.Timestamp("2026-02-01", tz="Asia/Seoul"))
        self.assertEqual(0, len(out))
        self.assertEqual(["frequency", "recency", "T", "monetary_value", "n_orders"], list(out.columns))


@unittest.skipUnless(HAVE_DEPS, SKIP_REASON)
class TestModels(unittest.TestCase):
    def test_bgnbd_recovers_known_population(self) -> None:
        from src.decision.clv_lifetime import expected_purchases, fit_bgnbd

        train = _simulate_summary(3000, seed=11)
        bg = fit_bgnbd(train)
        self.assertTrue(bg["converged"])
        self.assertEqual(3000, bg["n"])
        # 모수 하나하나보다 그것이 뜻하는 양 — 평균 구매율 r/α 와 이탈 확률 a/(a+b)
        self.assertAlmostEqual(TRUE_BG["r"] / TRUE_BG["alpha"], bg["r"] / bg["alpha"], delta=0.01)
        self.assertAlmostEqual(TRUE_BG["a"] / (TRUE_BG["a"] + TRUE_BG["b"]), bg["a"] / (bg["a"] + bg["b"]), delta=0.08)
        # 학습한 모형의 기대 구매 수가 참 모수의 기대 구매 수와 거의 같다
        x, tx, T = (train[c].to_numpy() for c in ("frequency", "recency", "T"))
        fitted = expected_purchases(bg, 180.0, x, tx, T).sum()
        truth = expected_purchases(TRUE_BG, 180.0, x, tx, T).sum()
        self.assertLess(abs(fitted / truth - 1), 0.1)

    def test_expected_purchases_shape(self) -> None:
        import numpy as np

        from src.decision.clv_lifetime import expected_purchases

        x, tx, T = np.array([3.0, 3.0, 0.0]), np.array([95.0, 10.0, 0.0]), np.array([100.0, 100.0, 100.0])
        self.assertTrue(np.allclose(0.0, expected_purchases(TRUE_BG, 0.0, x, tx, T)))
        short, long = expected_purchases(TRUE_BG, 30.0, x, tx, T), expected_purchases(TRUE_BG, 365.0, x, tx, T)
        self.assertTrue((long > short).all())
        # 같은 구매 수라도 최근에 산 고객이 더 살아 있을 가능성이 높다
        self.assertGreater(long[0], long[1])
        with self.assertRaises(ValueError):
            expected_purchases({**TRUE_BG, "a": 0.9}, 30.0, x, tx, T)

    def test_gamma_gamma_population_fallback_and_shrinkage(self) -> None:
        import numpy as np
        import pandas as pd

        from src.decision.clv_lifetime import expected_monetary, fit_gamma_gamma

        population = TRUE_GG["p"] * TRUE_GG["v"] / (TRUE_GG["q"] - 1)
        out = expected_monetary(TRUE_GG, np.array([0.0, 2.0, 2.0, 500.0]), np.array([np.nan, np.nan, 90000.0, 90000.0]))
        self.assertAlmostEqual(population, out[0])  # 반복 거래 없음
        self.assertAlmostEqual(population, out[1])  # 금액 결손
        self.assertTrue(population < out[2] < 90000.0)  # 관측 평균 쪽으로 당겨지되 모집단 쪽으로 줄어든다
        self.assertAlmostEqual(90000.0, out[3], delta=1000.0)  # 거래가 많으면 관측 평균에 수렴
        with self.assertRaises(ValueError):
            expected_monetary({**TRUE_GG, "q": 1.0}, np.array([1.0]), np.array([1.0]))

        rng = np.random.default_rng(5)
        n = 2000
        x = rng.integers(1, 8, size=n).astype(float)
        nu = rng.gamma(TRUE_GG["q"], 1 / TRUE_GG["v"], size=n)
        m = np.array([rng.gamma(TRUE_GG["p"], 1 / nu_i, size=int(k)).mean() for nu_i, k in zip(nu, x)])
        gg = fit_gamma_gamma(pd.DataFrame({"frequency": x, "monetary_value": m}))
        fitted_pop = gg["p"] * gg["v"] / (gg["q"] - 1)
        self.assertLess(abs(fitted_pop / population - 1), 0.1)

    def test_too_few_customers_is_refused(self) -> None:
        import pandas as pd

        from src.decision.clv_lifetime import fit_bgnbd, fit_gamma_gamma

        tiny = pd.DataFrame({"frequency": [1.0] * 5, "recency": [3.0] * 5, "T": [10.0] * 5, "monetary_value": [1.0] * 5})
        with self.assertRaises(ValueError):
            fit_bgnbd(tiny)
        with self.assertRaises(ValueError):
            fit_gamma_gamma(tiny)


@unittest.skipUnless(HAVE_DEPS, SKIP_REASON)
class TestLifetimeEndToEnd(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        import pandas as pd

        from src.decision.clv_lifetime import fit_lifetime

        cls.start = pd.Timestamp("2025-01-01", tz="Asia/Seoul")
        cls.events = _simulate_events(1200, seed=3, start=cls.start, days=420)
        cls.t1 = cls.start + pd.Timedelta(days=312)
        cls.t2 = cls.t1 + pd.Timedelta(days=42)
        cls.model = fit_lifetime(cls.events, cls.t1, horizon_months=12, annual_discount_rate=0.12)

    def test_fit_reads_only_events_before_index_time(self) -> None:
        from src.decision.clv_lifetime import fit_lifetime

        before = self.events[self.events["timestamp"] < self.t1]
        again = fit_lifetime(before, self.t1, horizon_months=12, annual_discount_rate=0.12)
        self.assertEqual(self.model.notes["summary_sha256"], again.notes["summary_sha256"])
        self.assertEqual(self.model.bgnbd, again.bgnbd)
        self.assertEqual((12, 0.12, "bgnbd_gamma_gamma"),
                         (self.model.horizon_months, self.model.annual_discount_rate, self.model.name))
        self.assertGreater(self.model.notes["n_repeat_buyers"], 0)
        self.assertEqual(0, self.model.notes["n_monetary_missing"])

    def test_discounting(self) -> None:
        import numpy as np

        from src.decision.clv_lifetime import DAYS_PER_MONTH, clv_from_summary, expected_purchases, rfm_summary

        summary = rfm_summary(self.events, self.t2)
        none, base, high = (clv_from_summary(self.model, summary, annual_discount_rate=r)["clv_12m"]
                            for r in (0.0, 0.12, 0.24))
        self.assertTrue(((none >= base) & (base >= high)).all())
        self.assertTrue((none > base).any())
        # 할인율 0 이면 12개월 기대 구매 수 × 기대 금액 그대로
        x, tx, T = (summary[c].to_numpy() for c in ("frequency", "recency", "T"))
        frame = clv_from_summary(self.model, summary, annual_discount_rate=0.0)
        n12 = expected_purchases(self.model.bgnbd, 12 * DAYS_PER_MONTH, x, tx, T)
        self.assertTrue(np.allclose(none.to_numpy(), n12 * frame["expected_monetary"].to_numpy()))
        # 12개월 할인 매출은 월말 할인 상한(1/(1+r)^(1/12))과 하한(1/(1+r)) 사이
        self.assertTrue(((base <= none / 1.12 ** (1 / 12) + 1e-6) & (base >= none / 1.12 - 1e-6)).all())

    def test_predict_reindexes_and_leaves_new_customers_empty(self) -> None:
        import math

        from src.decision.clv_lifetime import predict_lifetime

        ids = sorted(self.events.loc[self.events["timestamp"] < self.t2, "customer_id"].unique())[:5] + ["NEW"]
        clv = predict_lifetime(self.model, self.events, self.t2, customers=ids)
        self.assertEqual(ids, list(clv.index))
        self.assertEqual("clv_12m", clv.name)
        self.assertTrue(math.isnan(clv["NEW"]))
        self.assertTrue((clv.iloc[:5] > 0).all())

    def test_evaluate_window_and_sensitivity(self) -> None:
        import pandas as pd

        from src.decision.clv_lifetime import evaluate_lifetime

        window = self.events[(self.events["timestamp"] >= self.t1) & (self.events["timestamp"] < self.t2)]
        ids = sorted(self.events.loc[self.events["timestamp"] < self.t1, "customer_id"].unique())
        actual = pd.DataFrame({
            "purchases": window.groupby("customer_id")["order_id"].nunique().reindex(ids, fill_value=0).astype(float),
            "revenue": window.groupby("customer_id")["order_amount"].sum().reindex(ids, fill_value=0.0)})
        out = evaluate_lifetime(self.model, self.events, self.t1, actual, window_days=42, high_value_share=0.2,
                                sensitivity=(0.8, 1.2))
        self.assertEqual((42, len(ids), 0, 0),
                         (out["window_days"], out["n"], out["n_revenue_missing"], out["n_purchases_missing"]))
        self.assertEqual({"predicted_mean", "actual_mean", "mae", "spearman"}, set(out["purchases"]))
        self.assertEqual({"predicted_total", "actual_total", "mae", "spearman"}, set(out["revenue"]))
        # 같은 생성 과정이므로 42일 매출 합이 크게 어긋나지 않는다(합성 데이터 기준 점검일 뿐)
        self.assertLess(abs(out["revenue"]["predicted_total"] / out["revenue"]["actual_total"] - 1), 0.25)
        self.assertGreater(out["revenue"]["spearman"], 0.2)
        rows = out["discount_sensitivity"]["rows"]
        self.assertEqual([0.8, 1.2], [r["factor"] for r in rows])
        self.assertAlmostEqual(0.12 * 0.8, rows[0]["annual_discount_rate"])
        self.assertGreater(rows[0]["total_vs_base"], 1.0)
        self.assertLess(rows[1]["total_vs_base"], 1.0)
        for r in rows:
            self.assertTrue(0.0 <= r["high_value_overlap"] <= 1.0)

    def test_evaluate_without_sensitivity_has_no_block(self) -> None:
        import pandas as pd

        from src.decision.clv_lifetime import evaluate_lifetime

        ids = sorted(self.events.loc[self.events["timestamp"] < self.t1, "customer_id"].unique())[:50]
        actual = pd.DataFrame({"purchases": [0.0] * 40 + [float("nan")] * 10, "revenue": float("nan")}, index=ids)
        out = evaluate_lifetime(self.model, self.events, self.t1, actual, window_days=42, high_value_share=0.2)
        self.assertNotIn("discount_sensitivity", out)
        self.assertEqual((50, 10), (out["n_revenue_missing"], out["n_purchases_missing"]))
        self.assertIsNone(out["revenue"]["mae"])
        self.assertEqual(0.0, out["purchases"]["actual_mean"])  # 결손 10명은 빼고 40명으로
        self.assertGreater(out["purchases"]["mae"], 0.0)

    def test_model_pickles(self) -> None:
        clone = pickle.loads(pickle.dumps(self.model))
        self.assertEqual(self.model, clone)


@unittest.skipUnless(HAVE_DEPS, SKIP_REASON)
class TestClvTable(unittest.TestCase):
    def test_columns_flags_and_missing(self) -> None:
        import pandas as pd

        from src.decision.clv_lifetime import clv_table

        clv = pd.Series([float(v) for v in range(1, 11)] + [float("nan")],
                        index=[f"C{i}" for i in range(10)] + ["NEW"])
        frame = clv_table(clv, model_version="clv_12m-x", high_value_share=0.2)
        self.assertEqual(["customer_id", "clv_model_version", "predicted_clv_12m", "clv_percentile", "high_value_flag"],
                         list(frame.columns))
        self.assertEqual({"clv_12m-x"}, set(frame["clv_model_version"]))
        flagged = frame.loc[frame["high_value_flag"] == True, "customer_id"].tolist()  # noqa: E712 — nullable boolean
        self.assertEqual(["C8", "C9"], flagged)
        new = frame.set_index("customer_id").loc["NEW"]
        self.assertTrue(pd.isna(new["predicted_clv_12m"]) and pd.isna(new["clv_percentile"])
                        and pd.isna(new["high_value_flag"]))
        self.assertAlmostEqual(1.0, frame["clv_percentile"].max())


if __name__ == "__main__":
    unittest.main()
