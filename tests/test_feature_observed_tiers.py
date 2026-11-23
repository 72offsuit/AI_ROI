"""관측 등급(#221 · #303, DR-221-observed-tiers) — 창 · 경계 · 결손 · 누수.

★ 픽스처는 이 파일 안의 작은 합성 이벤트다. 시뮬레이터를 참고하지 않았고 공개 계약
  (`src/measurement/schema.py` 의 필드 · 상품군, 교환 계약 v1 의 품목 열)만 따른다.

실행:
    python -m unittest tests.test_feature_observed_tiers -v
"""

from __future__ import annotations

import importlib.util
import itertools
import unittest
from datetime import date, datetime, timedelta, timezone

HAVE_PANDAS = all(importlib.util.find_spec(name) is not None for name in ("numpy", "pandas"))
SKIP_REASON = "BLOCKED: numpy/pandas 미설치"

KST = timezone(timedelta(hours=9))
T0 = datetime(2026, 7, 1, tzinfo=KST)
DATA_START = T0 - timedelta(days=200)
_ids = itertools.count(1)


def event(cid: str, when: datetime, etype: str, **fields) -> dict:
    row = {"event_id": f"e{next(_ids):06d}", "customer_id": cid, "timestamp": when, "event_type": etype,
           "session_id": "s1", "order_id": None, "order_amount": None, "product_id": None, "category": None}
    row.update(fields)
    return row


class Fixture:
    """이벤트 · 품목 · 가입일을 모은다. 모든 고객은 DATA_START 에 방문 1건이 있다(관측 시작)."""

    def __init__(self) -> None:
        self.rows: list[dict] = [event("c_anchor", DATA_START, "session_start")]
        self.items: list[dict] = []
        self.signups: dict[str, date] = {}

    def visit(self, cid: str, days_before: float) -> None:
        self.rows.append(event(cid, T0 - timedelta(days=days_before), "session_start"))

    def buy(self, cid: str, days_before: float | None = None, amount: int | None = 10_000, *,
            when: datetime | None = None, items: tuple[tuple[str, int, int], ...] = ()) -> str:
        order_id = f"o{next(_ids):06d}"
        stamp = when if when is not None else T0 - timedelta(days=days_before)
        self.rows.append(event(cid, stamp, "purchase", order_id=order_id, order_amount=amount))
        for line, (product, quantity, price) in enumerate(items, start=1):
            self.items.append({"order_id": order_id, "line_no": line, "product_id": product,
                               "quantity": quantity, "unit_price": price})
        return order_id

    def view(self, product: str, category: str, days_before: float = 190) -> None:
        self.rows.append(event("c_anchor", T0 - timedelta(days=days_before), "product_view",
                               product_id=product, category=category))

    def events(self):
        import pandas as pd

        frame = pd.DataFrame(self.rows)
        frame["timestamp"] = pd.to_datetime(frame["timestamp"], utc=True).dt.tz_convert("Asia/Seoul")
        frame["order_amount"] = pd.array(frame["order_amount"].tolist(), dtype="Int64")
        return frame

    def order_items(self):
        import pandas as pd

        return pd.DataFrame(self.items, columns=["order_id", "line_no", "product_id", "quantity", "unit_price"])


@unittest.skipUnless(HAVE_PANDAS, SKIP_REASON)
class ObservedTierTests(unittest.TestCase):
    def tiers(self, fx: Fixture, population, **kwargs):
        from src.decision.observed_tiers import observed_tiers

        signups = kwargs.pop("signups", None)
        if signups is None:
            signups = {cid: date(2025, 1, 1) for cid in population}
        return observed_tiers(fx.events(), T0, population, signups, **kwargs)

    def test_window_is_the_180_days_before_t0(self):
        fx = Fixture()
        start = T0 - timedelta(days=180)
        fx.buy("c1", when=start)                              # 창 시작 — 들어간다
        fx.buy("c1", when=start - timedelta(seconds=1))       # 창 앞 — 빠진다
        fx.buy("c1", when=T0 - timedelta(seconds=1))          # T0 직전 — 들어간다
        fx.buy("c1", when=T0)                                 # T0 — 빠진다
        out = self.tiers(fx, ["c1"])
        self.assertEqual(out.loc["c1", "orders_180d"], 2)
        self.assertEqual(out.loc["c1", "spend_180d"], 20_000.0)
        meta = out.attrs["observed_tiers"]
        self.assertEqual(meta["window"]["days"], 180)
        self.assertTrue(meta["window_complete"])

    def test_value_tiers_split_at_the_50th_and_80th_percentile_of_purchasers(self):
        fx = Fixture()
        customers = [f"c{i:02d}" for i in range(1, 11)]
        for i, cid in enumerate(customers, start=1):
            fx.buy(cid, 30, amount=1_000 * i)
        fx.buy("c_old", 200, amount=99_000)      # 창 밖 구매만 — 창 안 0건
        fx.buy("c_missing", 30, amount=None)     # 금액 결손
        out = self.tiers(fx, customers + ["c_old", "c_missing"])
        meta = out.attrs["observed_tiers"]
        # 1,000 … 10,000 의 선형 보간 50 · 80 분위수
        self.assertEqual(meta["value_boundaries_krw"], {"p50": 5_500.0, "p80": 8_200.0})
        self.assertEqual(meta["n_value_basis"], 10)
        expected = ["V1_LOW"] * 5 + ["V2_MID"] * 3 + ["V3_HIGH"] * 2
        self.assertEqual(out.loc[customers, "value_tier"].tolist(), expected)
        self.assertEqual(out.loc["c_old", "value_tier"], "V0_NONE")
        self.assertEqual(out.loc["c_old", "spend_180d"], 0.0)
        self.assertEqual(out.loc["c_missing", "value_tier"], "UNKNOWN")
        self.assertTrue(out["spend_180d"].isna()["c_missing"])
        self.assertIn("AMOUNT_MISSING", meta["unknown_reasons"]["value_tier"])

    def test_boundaries_come_from_the_population_only(self):
        fx = Fixture()
        customers = [f"c{i:02d}" for i in range(1, 11)]
        for i, cid in enumerate(customers, start=1):
            fx.buy(cid, 30, amount=1_000 * i)
        fx.buy("outsider", 30, amount=1_000_000)
        inside = self.tiers(fx, customers)
        self.assertNotIn("outsider", inside.index)
        self.assertEqual(inside.attrs["observed_tiers"]["value_boundaries_krw"], {"p50": 5_500.0, "p80": 8_200.0})

    def test_eligible_flags_are_not_a_population(self):
        import pandas as pd

        fx = Fixture()
        fx.buy("c1", 20)
        with self.assertRaises(TypeError):
            self.tiers(fx, pd.Series({"c1": True, "c2": False}), signups={"c1": date(2025, 1, 1)})

    def test_frequency_bands(self):
        fx = Fixture()
        counts = {"n0": 0, "n1": 1, "n2": 2, "n4": 4, "n5": 5, "n12": 12, "n13": 13}
        for cid, n in counts.items():
            fx.visit(cid, 10)
            for k in range(n):
                fx.buy(cid, 1 + k * 13)
        out = self.tiers(fx, list(counts))
        self.assertEqual(out["frequency_tier"].to_dict(), {
            "n0": "F0_NONE", "n1": "F1_ONCE", "n2": "F2_RARE", "n4": "F2_RARE",
            "n5": "F3_REGULAR", "n12": "F3_REGULAR", "n13": "F4_FREQUENT"})
        self.assertEqual(out.loc["n0", "category_tier"], "NONE")

    def test_duplicate_purchase_events_of_one_order_count_once(self):
        fx = Fixture()
        order_id = fx.buy("c1", 20, amount=5_000)
        fx.rows.append(event("c1", T0 - timedelta(days=20), "purchase", order_id=order_id, order_amount=5_000))
        out = self.tiers(fx, ["c1"])
        self.assertEqual(out.loc["c1", "orders_180d"], 1)
        self.assertEqual(out.loc["c1", "spend_180d"], 5_000.0)

    def test_signup_tier_uses_kst_date_difference(self):
        fx = Fixture()
        for cid in ("new", "old", "missing", "future"):
            fx.buy(cid, 20)
        t0_day = date(2026, 7, 1)
        signups = {"new": t0_day - timedelta(days=179), "old": (t0_day - timedelta(days=180)).isoformat(),
                   "future": t0_day + timedelta(days=1)}
        out = self.tiers(fx, ["new", "old", "missing", "future"], signups=signups)
        self.assertEqual(out["signup_tier"].to_dict(),
                         {"future": "UNKNOWN", "missing": "UNKNOWN", "new": "NEW", "old": "EXISTING"})
        self.assertEqual(out.loc["new", "tenure_days"], 179.0)
        meta = out.attrs["observed_tiers"]
        self.assertEqual(meta["signup"], {"n_missing": 1, "n_after_cutoff": 1})

    def test_main_category_is_the_largest_item_amount_with_fixed_tie_order(self):
        fx = Fixture()
        for product, category in (("p_fresh", "fresh_food"), ("p_meal", "meal_solution"),
                                  ("p_dairy", "dairy"), ("p_bev", "beverage")):
            fx.view(product, category)
        fx.buy("mostly_dairy", 10, items=(("p_fresh", 1, 3_000), ("p_dairy", 2, 2_500)))
        fx.buy("mostly_dairy", 300, items=(("p_fresh", 10, 9_000),))           # 창 밖 — 세지 않는다
        fx.buy("tie", 10, items=(("p_bev", 1, 2_000), ("p_meal", 2, 1_000)))   # 동률 — Category 순서가 앞인 meal_solution
        fx.buy("unmapped", 10, items=(("p_unknown", 1, 1_000),))
        fx.buy("no_items", 10)
        fx.visit("no_orders", 5)
        population = ["mostly_dairy", "tie", "unmapped", "no_items", "no_orders"]
        out = self.tiers(fx, population, order_items=fx.order_items())
        self.assertEqual(out["category_tier"].to_dict(), {
            "mostly_dairy": "dairy", "no_items": "UNKNOWN", "no_orders": "NONE", "tie": "meal_solution",
            "unmapped": "UNKNOWN"})
        self.assertAlmostEqual(out.loc["mostly_dairy", "main_category_share"], 5_000 / 8_000)
        self.assertAlmostEqual(out.loc["tie", "main_category_share"], 0.5)
        meta = out.attrs["observed_tiers"]
        self.assertEqual(meta["items"]["n_window_orders_without_items"], 1)
        self.assertEqual(meta["items"]["n_items_unmapped"], 1)
        self.assertIn("NO_KNOWN_ITEMS", meta["unknown_reasons"]["category_tier"])

    def test_without_order_items_category_is_unknown_not_approximated(self):
        fx = Fixture()
        fx.view("p_fresh", "fresh_food")
        fx.rows.append(event("buyer", T0 - timedelta(days=10), "add_to_cart", product_id="p_fresh",
                             category="fresh_food"))
        fx.buy("buyer", 10)
        fx.visit("browser", 5)
        out = self.tiers(fx, ["buyer", "browser"])
        self.assertEqual(out.loc["buyer", "category_tier"], "UNKNOWN")
        self.assertEqual(out.loc["browser", "category_tier"], "NONE")
        meta = out.attrs["observed_tiers"]
        self.assertIsNone(meta["items"])
        self.assertIn("NO_ORDER_ITEMS", meta["unknown_reasons"]["category_tier"])

    def test_product_seen_in_two_categories_is_dropped(self):
        from src.decision.observed_tiers import product_categories_from_events

        fx = Fixture()
        fx.view("p_x", "dairy")
        fx.view("p_x", "beverage", days_before=150)
        fx.view("p_y", "household")
        fx.view("p_late", "dairy", days_before=0)  # T0 시각 — 쓰지 않는다
        mapping = product_categories_from_events(fx.events(), T0)
        self.assertEqual(mapping.to_dict(), {"p_y": "household"})
        self.assertEqual(mapping.attrs["conflicting_products"], 1)

    def test_events_at_or_after_t0_change_nothing(self):
        import pandas as pd

        fx = Fixture()
        fx.view("p_fresh", "fresh_food")
        for i, cid in enumerate(("a", "b", "c", "d"), start=1):
            fx.buy(cid, 10 * i, amount=2_000 * i, items=(("p_fresh", i, 2_000),))
        population = ["a", "b", "c", "d"]
        before = self.tiers(fx, population, order_items=fx.order_items())
        for cid in population:
            fx.buy(cid, when=T0 + timedelta(days=3), amount=500_000, items=(("p_fresh", 50, 10_000),))
        fx.view("p_fresh", "dairy", days_before=-1)
        fx.rows.append(event("a", T0 + timedelta(days=1), "churn"))
        after = self.tiers(fx, population, order_items=fx.order_items())
        pd.testing.assert_frame_equal(before, after)
        self.assertEqual(before.attrs["observed_tiers"]["value_boundaries_krw"],
                         after.attrs["observed_tiers"]["value_boundaries_krw"])

    def test_derived_status_events_and_assignment_fields_are_ignored(self):
        fx = Fixture()
        fx.buy("c1", 20)
        fx.rows.append(event("c1", T0 - timedelta(days=5), "churn", order_id="o_fake", order_amount=1))
        for row in fx.rows:
            row["treatment_group"] = "treatment"
        out = self.tiers(fx, ["c1"])
        self.assertEqual(out.loc["c1", "orders_180d"], 1)
        self.assertNotIn("treatment_group", out.columns)

    def test_short_history_marks_the_window_incomplete(self):
        fx = Fixture()
        fx.rows = [event("c1", T0 - timedelta(days=100), "session_start")]
        fx.buy("c1", 50)
        out = self.tiers(fx, ["c1"])
        self.assertFalse(out.attrs["observed_tiers"]["window_complete"])

    def test_columns_and_rule_record(self):
        from src.decision import observed_tiers as ot

        fx = Fixture()
        fx.buy("c1", 20)
        out = self.tiers(fx, ["c1"])
        self.assertEqual(tuple(out.columns), ot.BASIS_COLUMNS + ot.TIER_COLUMNS)
        meta = out.attrs["observed_tiers"]
        self.assertEqual(meta["version"], "observed-tier-v1")
        self.assertEqual(meta["value_quantiles"], [0.5, 0.8])
        self.assertEqual(meta["new_customer_days"], 180)
        self.assertEqual(meta["category_order"], ["fresh_food", "meal_solution", "dairy", "beverage", "household"])
        for column in ot.TIER_COLUMNS:
            self.assertTrue(set(out[column]) <= set(ot.TIER_LABELS[column]), column)


class SmallGroupTests(unittest.TestCase):
    @unittest.skipUnless(HAVE_PANDAS, SKIP_REASON)
    def test_small_group_rule(self):
        from src.decision.observed_tiers import small_group

        self.assertTrue(small_group(99))
        self.assertFalse(small_group(100))
        self.assertTrue(small_group(500, positives=9))
        self.assertTrue(small_group(500, positives=491))
        self.assertFalse(small_group(500, positives=10))


if __name__ == "__main__":
    unittest.main()
