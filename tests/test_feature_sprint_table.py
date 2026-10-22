"""스프린트 1 Feature 테이블·로더 (이슈 #144).

★ 픽스처는 **이 파일 안의 소형 합성 생성기**다. 시뮬레이터 코드를 참고하지 않았고,
  공개 계약(`src/measurement/schema.py` 의 필드·식별자 형식)만 따른다. 여기서 나온
  지표는 "픽스처 기준, 실제 결과 아님" 이다.

실행:
    python -m unittest tests.test_feature_sprint_table -v
"""

from __future__ import annotations

import importlib.util
import tempfile
import unittest
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

HAVE_ML = all(importlib.util.find_spec(name) is not None
              for name in ("numpy", "pandas", "sklearn"))
SKIP_REASON = "BLOCKED: numpy/pandas/scikit-learn 미설치"

KST = timezone(timedelta(hours=9))
FIXTURE_START = datetime(2026, 1, 1, tzinfo=KST)
FIXTURE_T0 = datetime(2026, 7, 1, tzinfo=KST)  # 시작 + 181일
FIXTURE_DAYS = 240                              # T0 + 59일까지 → 42일 라벨 창을 덮는다
CATEGORIES = ("fresh_food", "meal_solution", "dairy", "beverage", "household")


def make_events(n_customers: int = 300, days: int = FIXTURE_DAYS, seed: int = 7) -> list[dict]:
    """계약 형식의 합성 이벤트. 고객마다 방문 성향이 있고 일부는 시간이 갈수록 줄어든다.

    정답 구조를 숨기려는 생성기가 아니다 — 파이프라인이 끝까지 도는지와 신호가 있을 때
    모델이 우연 이상을 내는지만 본다.
    """
    import numpy as np

    rng = np.random.default_rng(seed)
    events: list[dict] = []
    order_seq = 0

    def eid() -> str:
        return str(uuid.UUID(int=int(rng.integers(0, 2**63)) << 64 | int(rng.integers(0, 2**63)), version=4))

    def emit(cid, at, etype, sid=None, **fields):
        row = {"event_id": eid(), "customer_id": cid,
               "timestamp": at.isoformat(timespec="milliseconds"), "event_type": etype,
               "service_version": "fixture-1", "customer_version": "fixture-1",
               "simulator_version": "fixture-sprint", "random_seed": seed}
        if sid is not None:
            row["session_id"] = sid
        row.update({k: v for k, v in fields.items() if v is not None})
        events.append(row)
        return row

    for i in range(n_customers):
        cid = f"C{i + 1:08d}"
        base = rng.uniform(0.03, 0.35)
        buy = rng.uniform(0.15, 0.6)
        decay_start = rng.uniform(60, 260) if rng.random() < 0.45 else None
        fav = rng.choice(CATEGORIES)
        coupon_lover = rng.random() < 0.3
        for day in range(days):
            p = base
            if decay_start is not None and day > decay_start:
                p = base * np.exp(-(day - decay_start) / 20.0)
            if rng.random() < 0.02:
                at = FIXTURE_START + timedelta(days=day, hours=int(rng.integers(8, 22)))
                emit(cid, at, "campaign_exposed", campaign_id=f"CMP-{at:%Y%m%d}-001")
                if rng.random() < 0.6:
                    emit(cid, at, "coupon_exposed", campaign_id=f"CMP-{at:%Y%m%d}-001",
                         coupon_id="CPN-A00001")
            if rng.random() >= p:
                continue
            at = FIXTURE_START + timedelta(days=day, hours=int(rng.integers(6, 24)),
                                           minutes=int(rng.integers(0, 60)))
            sid = f"S-{cid}-{int(at.timestamp() * 1000):013d}"
            emit(cid, at, "return_visit" if rng.random() < 0.3 else "session_start", sid,
                 page_type="home")
            step = 0

            def tick():
                nonlocal step
                step += 1
                return at + timedelta(seconds=20 * step)

            for _ in range(int(rng.integers(1, 5))):
                emit(cid, tick(), "page_view", sid, page_type="list")
            if rng.random() < 0.4:
                emit(cid, tick(), "search", sid, page_type="search")
            cat = fav if rng.random() < 0.7 else rng.choice(CATEGORIES)
            pid = f"P{int(rng.integers(0, 300)):04d}"
            emit(cid, tick(), "product_view", sid, page_type="detail", category=str(cat), product_id=pid)
            last = None
            if rng.random() < buy:
                price = int(rng.integers(20, 300)) * 100
                qty = int(rng.integers(1, 4))
                emit(cid, tick(), "add_to_cart", sid, page_type="detail", category=str(cat),
                     product_id=pid, quantity=qty, unit_price=price)
                if rng.random() < 0.75:
                    order_seq += 1
                    oid = f"O{(at.year * 10000 + at.month * 100 + at.day):08d}-{order_seq % 1_000_000:06d}"
                    amount = price * qty
                    emit(cid, tick(), "checkout_start", sid, page_type="checkout",
                         order_id=oid, order_amount=amount)
                    if coupon_lover and rng.random() < 0.5:
                        emit(cid, tick(), "coupon_use", sid, page_type="complete", order_id=oid,
                             order_amount=amount, coupon_id="CPN-A00001",
                             campaign_id=f"CMP-{at:%Y%m%d}-001")
                    last = emit(cid, tick(), "purchase", sid, page_type="complete",
                                order_id=oid, order_amount=amount)
            if last is None:
                last = emit(cid, tick(), "page_view", sid, page_type="list")
            last["session_duration"] = 20 * step
    return events


def write_sink(records: list[dict], root: Path, fmt: str = "jsonl.gz") -> Path:
    from src.measurement.sink import EventSink

    with EventSink(root, fmt=fmt) as sink:
        result = sink.write_events(records)
    if result.rejected:
        raise AssertionError(f"픽스처가 계약을 어겼다: {result.rejected} 건")
    return root


@unittest.skipUnless(HAVE_ML, SKIP_REASON)
class TestLoadEvents(unittest.TestCase):
    def test_roundtrip_jsonl_and_parquet(self) -> None:
        from src.decision.data import EVENT_COLUMNS, load_events

        records = make_events(n_customers=8, days=20)
        fmts = ["jsonl.gz"]
        if importlib.util.find_spec("pyarrow") is not None:
            fmts.append("parquet")
        for fmt in fmts:
            with self.subTest(fmt=fmt), tempfile.TemporaryDirectory() as tmp:
                write_sink(records, Path(tmp), fmt)
                frame = load_events(tmp)
                self.assertEqual(EVENT_COLUMNS, list(frame.columns))
                self.assertEqual(22, len(frame.columns))
                self.assertEqual(len(records), len(frame))
                self.assertIsNotNone(frame["timestamp"].dt.tz)
                self.assertEqual("Int64", str(frame["order_amount"].dtype))
                # 결손은 결손이다 — 0 이나 "nan" 문자열로 바뀌지 않는다
                self.assertTrue(frame.loc[frame["event_type"] == "page_view", "order_amount"].isna().all())
                self.assertFalse((frame["coupon_id"].dropna() == "nan").any())
                self.assertTrue(frame["timestamp"].is_monotonic_increasing)

    def test_missing_root_is_an_error_not_empty(self) -> None:
        from src.decision.data import load_events

        with tempfile.TemporaryDirectory() as tmp, self.assertRaises(FileNotFoundError):
            load_events(tmp)


@unittest.skipUnless(HAVE_ML, SKIP_REASON)
class TestSprintFeatureTable(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        import pandas as pd

        from src.decision.data import _coerce

        cls.events = _coerce(pd.DataFrame.from_records(make_events(n_customers=120)))

    def test_at_least_30_numeric_features(self) -> None:
        from src.decision.features.sprint_table import FEATURE_NAMES, build_feature_table

        table = build_feature_table(self.events, FIXTURE_T0)
        self.assertGreaterEqual(len(FEATURE_NAMES), 30)
        self.assertEqual(list(FEATURE_NAMES), list(table.columns))
        self.assertTrue(all(str(t) == "float64" for t in table.dtypes))
        self.assertEqual("customer_id", table.index.name)
        self.assertTrue(table.index.is_unique)

    def test_names_follow_d1_dictionary(self) -> None:
        """D1 Feature ID 를 단 컬럼은 이름이 D1 `DEFINITIONS` 의 공개 이름과 같다."""
        from src.decision.features.d1_calculate import DEFINITIONS
        from src.decision.features.sprint_table import SPRINT_FEATURES

        d1 = {row[0]: row[1] for row in DEFINITIONS}
        mismatched = [(f.d1_id, f.name, d1.get(f.d1_id)) for f in SPRINT_FEATURES
                      if f.d1_id is not None and d1.get(f.d1_id) != f.name]
        self.assertEqual([], mismatched)

    def test_no_future_leakage(self) -> None:
        """T0 이후 이벤트를 바꿔도 Feature 는 한 칸도 바뀌지 않는다."""
        import pandas as pd

        from src.decision.features.sprint_table import build_feature_table

        t0 = pd.Timestamp(FIXTURE_T0)
        base = build_feature_table(self.events, t0)
        past_only = self.events[self.events["timestamp"] < t0]
        trimmed = build_feature_table(past_only, t0)
        pd.testing.assert_frame_equal(base, trimmed)

    def test_forbidden_inputs_are_ignored(self) -> None:
        import pandas as pd

        from src.decision.features.sprint_table import build_feature_table

        noisy = self.events.copy()
        noisy["treatment_group"] = "treatment"
        noisy["experiment_id"] = "EXP-20260101-01"
        derived = noisy.iloc[:50].copy()
        derived["event_type"] = "churn"
        noisy = pd.concat([noisy, derived], ignore_index=True)
        pd.testing.assert_frame_equal(build_feature_table(self.events, FIXTURE_T0),
                                      build_feature_table(noisy, FIXTURE_T0))

    def test_missing_is_nan_with_reason_not_zero(self) -> None:
        import pandas as pd

        from src.decision.features.sprint_table import build_feature_table

        t0 = pd.Timestamp(FIXTURE_T0)
        # 구매 이벤트를 모두 지운 고객 하나 → recency·aov 는 NaN 이고 사유가 있다
        victim = self.events["customer_id"].iloc[0]
        events = self.events[~((self.events["customer_id"] == victim)
                               & self.events["event_type"].isin(["purchase"]))]
        table = build_feature_table(events, t0)
        self.assertTrue(pd.isna(table.loc[victim, "recency"]))
        self.assertTrue(pd.isna(table.loc[victim, "aov_90d"]))
        self.assertEqual(0.0, table.loc[victim, "frequency_90d"])  # 관측된 0
        self.assertIn("recency", table.attrs["nan_reasons"])

    def test_hand_computed_values(self) -> None:
        import pandas as pd

        from src.decision.data import _coerce
        from src.decision.features.sprint_table import build_feature_table

        cid = "C00000001"
        t0 = datetime(2026, 7, 1, tzinfo=KST)

        def ev(days_before, etype, n, **kw):
            at = t0 - timedelta(days=days_before)
            row = {"event_id": str(uuid.UUID(int=n, version=4)), "customer_id": cid,
                   "timestamp": at.isoformat(timespec="milliseconds"), "event_type": etype,
                   "session_id": f"S-{cid}-{int(at.timestamp() * 1000):013d}"}
            row.update(kw)
            return row

        rows = [ev(200, "session_start", 1, page_type="home"),
                ev(100, "purchase", 2, order_id="O20260101-000001", order_amount=1000, page_type="complete"),
                ev(40, "purchase", 3, order_id="O20260101-000002", order_amount=3000, page_type="complete"),
                ev(10, "purchase", 4, order_id="O20260101-000003", order_amount=2000, page_type="complete"),
                ev(10, "purchase", 5, order_id="O20260101-000003", order_amount=2000, page_type="complete"),
                ev(-3, "purchase", 6, order_id="O20260101-000004", order_amount=9000, page_type="complete")]
        table = build_feature_table(_coerce(pd.DataFrame.from_records(rows)), t0)
        row = table.loc[cid]
        self.assertAlmostEqual(10.0, row["recency"])
        self.assertEqual(2.0, row["frequency_90d"])        # 중복 주문은 1 건, 미래 주문 제외
        self.assertEqual(5000.0, row["monetary_90d"])
        self.assertEqual(2500.0, row["aov_90d"])
        self.assertAlmostEqual(45.0, row["avg_purchase_interval"])  # (60 + 30) / 2
        self.assertAlmostEqual(10.0 / 45.0, row["purchase_cycle_anomaly"])
        self.assertEqual(3.0, row["frequency_observed"])
        self.assertAlmostEqual(200.0, row["tenure_days"])
        self.assertTrue(pd.isna(row["purchase_interval_cv_90d"]))  # 90일 간격 1 개뿐

    def test_missing_order_amount_is_nan_not_dropped(self) -> None:
        """금액 결손 주문을 합에서 조용히 빼면 매출이 적게 보인다 — NaN 으로 드러낸다."""
        import pandas as pd

        from src.decision.features.sprint_table import build_feature_table

        t0 = pd.Timestamp(FIXTURE_T0)
        events = self.events.copy()
        past_buy = events.index[(events["event_type"] == "purchase") & (events["timestamp"] < t0)
                               & (events["timestamp"] >= t0 - pd.Timedelta(days=30))]
        victim = events.loc[past_buy[0], "customer_id"]
        events.loc[past_buy[0], "order_amount"] = pd.NA
        table = build_feature_table(events, t0)
        self.assertTrue(pd.isna(table.loc[victim, "monetary_90d"]))
        self.assertTrue(pd.isna(table.loc[victim, "monetary_observed"]))
        self.assertGreaterEqual(table.loc[victim, "frequency_90d"], 1.0)  # 빈도는 그대로 계산된다
        self.assertIn("monetary_90d", table.attrs["nan_reasons"])

    def test_outcomes_label_window(self) -> None:
        import pandas as pd

        from src.decision.features.sprint_table import build_feature_table, build_outcomes

        y = build_outcomes(self.events, FIXTURE_T0)
        X = build_feature_table(self.events, FIXTURE_T0)
        self.assertEqual(list(X.index), list(y.index))
        self.assertEqual({"churn", "purchases", "revenue"}, set(y.columns))
        self.assertTrue(((y["churn"] == 1) == (y["purchases"] == 0)).all())
        self.assertTrue(0.0 < y["churn"].mean() < 1.0)
        # 관측이 라벨 창 끝까지 닿지 않으면 조용히 라벨을 만들지 않는다
        late = pd.Timestamp(FIXTURE_T0) + pd.Timedelta(days=40)
        with self.assertRaises(ValueError):
            build_outcomes(self.events, late)
        flagged = build_outcomes(self.events, late, allow_incomplete=True)
        self.assertFalse(flagged.attrs["label_window_complete"])


if __name__ == "__main__":
    unittest.main()
