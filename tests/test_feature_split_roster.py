"""#218 공통 명부(DR-218-common-roster) — 기준일별 역할 · 관측 등급 · 관측 완전성.

★ 픽스처는 이 파일 안의 작은 합성 이벤트다. 시뮬레이터를 참고하지 않았고 공개 계약만 따른다.

실행:
    python -m unittest tests.test_feature_split_roster -v
"""

from __future__ import annotations

import importlib.util
import itertools
import unittest
from datetime import date, datetime, timedelta, timezone
from types import SimpleNamespace

HAVE_PANDAS = all(importlib.util.find_spec(name) is not None for name in ("numpy", "pandas"))
SKIP_REASON = "BLOCKED: numpy/pandas 미설치"

KST = timezone(timedelta(hours=9))
T1 = datetime(2026, 7, 1, tzinfo=KST)
T_PRIOR = T1 - timedelta(days=42)
T2 = T1 + timedelta(days=42)
_ids = itertools.count(1)


def _event(cid: str, when: datetime, etype: str, **fields) -> dict:
    row = {"event_id": f"e{next(_ids):06d}", "customer_id": cid, "timestamp": when, "event_type": etype,
           "session_id": "s1", "order_id": None, "order_amount": None, "product_id": None, "category": None}
    row.update(fields)
    return row


def _events():
    import pandas as pd

    rows = [_event("anchor", T_PRIOR - timedelta(days=200), "session_start")]
    for i, cid in enumerate(("a", "b", "c", "d", "e", "f"), start=1):
        for k in range(i):  # 고객마다 구매 횟수가 다르다 — a 1회 … f 6회(t_prior 전)
            rows.append(_event(cid, T_PRIOR - timedelta(days=5 + 10 * k), "purchase",
                               order_id=f"o-{cid}-{k}", order_amount=1_000 * i))
    rows.append(_event("a", T1 - timedelta(days=3), "session_start"))       # t_prior 뒤 · t1 전
    rows.append(_event("a", T2 + timedelta(days=1), "purchase", order_id="o-a-late", order_amount=9_000))  # t2 뒤
    frame = pd.DataFrame(rows)
    frame["timestamp"] = pd.to_datetime(frame["timestamp"], utc=True).dt.tz_convert("Asia/Seoul")
    frame["order_amount"] = pd.array(frame["order_amount"].tolist(), dtype="Int64")
    return frame


SIGNUPS = {cid: date(2025, 1, 1) for cid in "abcdef"}
ARMS = {"a": "T0", "b": "T1", "d": "T0", "e": "T0"}


def _cohorts() -> dict:
    return {
        "t_prior": {"index_time": T_PRIOR, "label_window": (T_PRIOR, T1), "eligible": ["a", "b", "c"],
                    "labeled": ["a", "b"]},
        "t1": {"index_time": T1, "label_window": (T1, T2), "eligible": ["a", "b", "d", "e"],
               "labeled": ["a", "b", "d"], "rct_arm": ARMS},
        # t2 의 labeled 는 쓰지 않는다 — 넣어도 역할이 바뀌지 않아야 한다
        "t2": {"index_time": T2, "label_window": None, "eligible": ["a", "b", "c", "d", "f"],
               "labeled": ["f"], "rct_arm": ARMS},
    }


@unittest.skipUnless(HAVE_PANDAS, SKIP_REASON)
class SplitRosterTests(unittest.TestCase):
    def build(self, cohorts=None, **kwargs):
        from src.decision.split_roster import build_split_roster

        kwargs.setdefault("order_items", None)
        kwargs.setdefault("observation_complete", True)
        return build_split_roster(_events(), SIGNUPS, cohorts=cohorts or _cohorts(), **kwargs)

    def roles(self, roster, origin):
        part = roster[roster["origin"] == origin].set_index("customer_id")
        return part["role"].to_dict(), part["exclusion_reason"].dropna().to_dict()

    def test_roles_per_origin(self):
        roster, record, _ = self.build()
        self.assertEqual(self.roles(roster, "t_prior"),
                         ({"a": "train", "b": "train", "c": "excluded"}, {"c": "no_feature_or_label"}))
        self.assertEqual(self.roles(roster, "t1"),
                         ({"a": "validation", "b": "excluded", "d": "validation", "e": "excluded"},
                          {"b": "rct_treated", "e": "no_feature_or_label"}))
        # t2 — 처치받은 b 제외 · 학습 고객(a · b@t_prior · d) 은 기존 고객 평가 · 나머지(c · f)가 과제 Test
        self.assertEqual(self.roles(roster, "t2"),
                         ({"a": "future_existing", "b": "excluded", "c": "test", "d": "future_existing",
                           "f": "test"}, {"b": "rct_treated"}))
        self.assertEqual({"train": 2, "excluded": 1}, record["origins"]["t_prior"]["roles"])
        self.assertEqual({"rct_treated": 1}, record["origins"]["t2"]["exclusions"])

    def test_t2_roles_do_not_look_at_labels(self):
        cohorts = _cohorts()
        cohorts["t2"] = {**cohorts["t2"], "labeled": None}
        a, _, _ = self.build(cohorts)
        b, record, _ = self.build()
        self.assertEqual(self.roles(a, "t2"), self.roles(b, "t2"))
        self.assertIs(False, record["origins"]["t2"]["labels_used_for_roles"])
        self.assertIsNone(record["origins"]["t2"]["label_window"])

    def test_one_row_per_customer_and_origin_without_labels(self):
        from src.decision.split_roster import COLUMNS

        roster, record, tiers = self.build()
        self.assertEqual(list(COLUMNS), list(roster.columns))
        self.assertFalse(roster.duplicated(["customer_id", "origin"]).any())
        for forbidden in ("churn", "label", "probability", "purchases", "revenue"):
            self.assertNotIn(forbidden, roster.columns)
        self.assertEqual(3 + 4 + 5, record["n_rows"])
        self.assertEqual({"t_prior", "t1", "t2"}, set(tiers))
        self.assertEqual(["a", "b", "c"], list(tiers["t_prior"].index))   # 등급 모집단 = 그 기준일 Eligible

    def test_stratum_tiers_and_rct_arm_columns(self):
        roster, record, _ = self.build()
        prior = roster[roster["origin"] == "t_prior"].set_index("customer_id")
        self.assertEqual("F1_ONCE", prior.loc["a", "frequency_tier"])
        self.assertEqual(prior.loc["a", "value_tier"] + "|F1_ONCE", prior.loc["a", "stratum"])
        self.assertTrue(prior["rct_arm"].isna().all())                    # t_prior 는 실험 전
        t2 = roster[roster["origin"] == "t2"].set_index("customer_id")
        self.assertEqual("T0", t2.loc["a", "rct_arm"])
        self.assertTrue(pd_isna(t2.loc["f", "rct_arm"]))                  # t1 에 배정되지 않은 고객
        self.assertEqual("observed-tier-v1", record["origins"]["t1"]["tiers"]["version"])
        self.assertIn("train", record["origins"]["t_prior"]["tier_counts_by_role"])

    def test_event_counts_and_observation_flag(self):
        roster, _, _ = self.build(observation_complete=False)
        prior = roster[roster["origin"] == "t_prior"].set_index("customer_id")
        self.assertEqual(1, prior.loc["a", "n_events_before_cutoff"])     # t_prior 뒤 방문 · t2 뒤 구매는 세지 않는다
        t1 = roster[roster["origin"] == "t1"].set_index("customer_id")
        self.assertEqual(2, t1.loc["a", "n_events_before_cutoff"])
        self.assertFalse(roster["observation_complete"].any())

    def test_missing_origin_is_not_run_with_reason(self):
        cohorts = _cohorts()
        del cohorts["t_prior"]
        roster, record, _ = self.build(cohorts, not_run={"t_prior": "앞 기준일 라벨 관측 근거 미충족"})
        self.assertEqual({"status": "not_run", "reason": "앞 기준일 라벨 관측 근거 미충족"}, record["origins"]["t_prior"])
        self.assertNotIn("t_prior", set(roster["origin"]))
        # 앞 기준일이 없으면 학습 고객은 t1 validation 뿐이다 — c 는 t_prior 학습 고객이 아니었으므로 test
        self.assertEqual("test", self.roles(roster, "t2")[0]["c"])

    def test_unknown_origin_is_rejected(self):
        with self.assertRaises(ValueError):
            self.build({"t3": _cohorts()["t2"]})

    def test_frequency_band_check_uses_eligible_shares(self):
        _, record, _ = self.build()
        check = record["origins"]["t_prior"]["frequency_band_check"]
        self.assertEqual(3, check["n"])
        # a 1회 · b 2회 · c 3회 → F1 1/3 · F2 2/3(60% 초과) · F3 · F4 0
        self.assertAlmostEqual(1 / 3, check["shares"]["F1_ONCE"])
        self.assertAlmostEqual(2 / 3, check["shares"]["F2_RARE"])
        self.assertEqual(["F2_RARE", "F3_REGULAR", "F4_FREQUENT"], check["outside"])

    def test_order_items_frame_from_exchange_orders(self):
        from src.decision.split_roster import order_items_frame

        item = SimpleNamespace(product_id="p1", quantity=2, unit_price=1_500)
        orders = {"o1": SimpleNamespace(items=(item,)), "o2": SimpleNamespace(items=())}
        frame = order_items_frame(orders)
        self.assertEqual([["o1", "p1", 2, 1_500]], frame.values.tolist())
        self.assertIsNone(order_items_frame(None))


def pd_isna(value) -> bool:
    import pandas as pd

    return bool(pd.isna(value))


if __name__ == "__main__":
    unittest.main()
