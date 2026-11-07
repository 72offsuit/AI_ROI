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


def fixture_observation():
    """make_events의 명시적 합성 생성 범위. 이벤트 최댓값에서 추정하지 않는다."""
    return {"start": FIXTURE_START, "end": FIXTURE_START + timedelta(days=FIXTURE_DAYS),
            "run_id": "fixture-sprint", "rejected": 0, "purchase_generated": True, "read_complete": True}


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
        from src.decision.features.sprint_table import (
            FEATURE_NAMES, TABLE_COLUMNS, build_feature_table, model_columns)

        table = build_feature_table(self.events, FIXTURE_T0)
        self.assertGreaterEqual(len(FEATURE_NAMES), 30)
        self.assertEqual(list(TABLE_COLUMNS), list(table.columns))
        self.assertEqual(list(FEATURE_NAMES), model_columns(table))
        self.assertTrue(all(str(t) == "float64" for t in table.dtypes))
        self.assertEqual("customer_id", table.index.name)
        self.assertTrue(table.index.is_unique)

    def test_s1_alias_column_matches_recency(self) -> None:
        """오케스트레이션(#154) S1 규칙이 쓰는 이름. 값은 recency 와 같고 구매 이력이 없으면 NaN."""
        import pandas as pd

        from src.decision.features.sprint_table import build_feature_table

        table = build_feature_table(self.events, FIXTURE_T0)
        pd.testing.assert_series_equal(table["recency"], table["days_since_last_purchase"],
                                       check_names=False)
        no_orders = table["frequency_observed"] == 0
        self.assertTrue(table.loc[no_orders, "days_since_last_purchase"].isna().all())
        self.assertTrue(table.loc[~no_orders, "days_since_last_purchase"].notna().all())

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
        # 메타가 없는 수작업 행은 공개 출처 규칙상 commerce다. 산술 대조 목적으로만 계산한다.
        table = build_feature_table(_coerce(pd.DataFrame.from_records(rows)), t0, purpose="observation")
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

        y = build_outcomes(self.events, FIXTURE_T0, observation=fixture_observation())
        X = build_feature_table(self.events, FIXTURE_T0)
        self.assertEqual(list(X.index), list(y.index))
        self.assertEqual({"churn", "purchases", "revenue"}, set(y.columns))
        self.assertTrue(((y["churn"] == 1) == (y["purchases"] == 0)).all())
        self.assertTrue(0.0 < y["churn"].mean() < 1.0)
        # 관측이 라벨 창 끝까지 닿지 않으면 조용히 라벨을 만들지 않는다
        late = pd.Timestamp(FIXTURE_T0) + pd.Timedelta(days=40)
        with self.assertRaises(ValueError):
            build_outcomes(self.events, late, observation=fixture_observation())
        flagged = build_outcomes(self.events, late, observation=fixture_observation(), allow_incomplete=True)
        self.assertFalse(flagged.attrs["label_window_complete"])
        self.assertTrue(flagged.isna().all().all())


def _contract_runner():
    """시스템 소스만 로드한다. 시뮬레이터 import 1개를 제거하고 독립 가짜 공개 API를 주입한다.

    실제 시뮬레이터/E2E 시험이 아니다. run()과 decision의 실제 연결을 검사한다.
    """
    import ast
    import builtins
    import sys
    import types

    path = Path(__file__).resolve().parents[1] / "src/orchestration/run_sprint.py"
    tree = ast.parse(path.read_text(encoding="utf-8"))
    removed = [n for n in tree.body if isinstance(n, ast.ImportFrom) and n.module == "src.simulator"]
    if len(removed) != 1:
        raise AssertionError("공개 API import 위치가 바뀌었다 — 독립 하네스 재검토 필요")
    tree.body = [n for n in tree.body if n not in removed]
    original = builtins.__import__

    def guarded(name, *args, **kwargs):
        if name.startswith(("src.simulator", "src.diagnostics")):
            raise AssertionError("금지 모듈 import 시도")
        return original(name, *args, **kwargs)

    module = types.ModuleType("_issue179_contract_runner")
    module.__file__ = str(path)
    module.__dict__["__builtins__"] = {**vars(builtins), "__import__": guarded}
    sys.modules[module.__name__] = module  # dataclass가 자기 모듈을 찾는 데 필요
    exec(compile(tree, str(path), "exec"), module.__dict__)
    return module


@unittest.skipUnless(HAVE_ML, SKIP_REASON)
class TestOutcomeObservationContract(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.runner = _contract_runner()

    @classmethod
    def tearDownClass(cls):
        import sys
        sys.modules.pop(cls.runner.__name__, None)

    def setUp(self):
        import pandas as pd
        self.t0 = pd.Timestamp(FIXTURE_T0)
        self.end = self.t0 + pd.Timedelta(days=42)
        self.evidence = {"start": self.t0, "end": self.end, "run_id": "fixture-179",
                         "rejected": 0, "purchase_generated": True, "read_complete": True}
        self.rows = [{"customer_id": f"C{i:08d}", "event_type": "page_view", "event_id": str(i),
                      "timestamp": self.t0 - pd.Timedelta(days=1), "order_id": None, "order_amount": None}
                     for i in (1, 2)]

    def frame(self, purchases=()):
        import pandas as pd
        rows = self.rows + [{"customer_id": "C00000001", "event_type": "purchase",
                            "event_id": f"p{i}", "timestamp": at, "order_id": f"o{i}", "order_amount": amount}
                           for i, (at, amount) in enumerate(purchases)]
        return pd.DataFrame(rows)

    def outcomes(self, events=None, **changes):
        from src.decision.features.sprint_table import build_outcomes
        return build_outcomes(self.frame() if events is None else events, self.t0,
                              observation={**self.evidence, **changes}, allow_incomplete=True)

    def test_quiet_complete_window_is_observed_zero(self):
        from src.decision.features.sprint_table import summarize_outcomes
        out = self.outcomes()
        self.assertEqual([1, 1], out.churn.tolist())
        summary = summarize_outcomes(out, out.index)
        self.assertEqual(0, summary["revenue_krw"])
        self.assertEqual(0, summary["purchases"])
        self.assertEqual(1, summary["churn_rate"])
        self.assertEqual("ok", summary["field_observation"]["revenue"]["status"])

    def test_half_open_purchase_boundaries_and_utc_equivalence(self):
        import pandas as pd
        events = self.frame([(self.t0 - pd.Timedelta(microseconds=1), 100), (self.t0, 200),
                             (self.end - pd.Timedelta(microseconds=1), 300), (self.end, 400)])
        out = self.outcomes(events)
        self.assertEqual(500, out.loc["C00000001", "revenue"])
        self.assertEqual(2, out.loc["C00000001", "purchases"])
        utc = self.outcomes(events, start=self.t0.tz_convert("UTC"), end=self.end.tz_convert("UTC"))
        pd.testing.assert_frame_equal(out, utc)

    def test_observation_bounds_not_last_event_decide_completion(self):
        import pandas as pd
        for changes, complete in [({"start": self.t0 + pd.Timedelta(microseconds=1)}, False),
                                  ({"end": self.end - pd.Timedelta(microseconds=1)}, False),
                                  ({"end": self.end}, True),
                                  ({"end": self.end + pd.Timedelta(microseconds=1)}, True),
                                  ({"start": self.t0.tz_localize(None)}, False)]:
            with self.subTest(changes=changes):
                out = self.outcomes(**changes)
                self.assertEqual(complete, out.attrs["label_window_complete"])
                self.assertEqual(not complete, out.isna().all().all())

    def test_missing_proof_strict_raises_diagnostic_has_no_labels(self):
        from src.decision.features.sprint_table import build_outcomes
        with self.assertRaisesRegex(ValueError, "관측 근거"):
            build_outcomes(self.frame([(self.end, 100)]), self.t0)
        out = build_outcomes(self.frame(), self.t0, allow_incomplete=True)
        self.assertTrue(out.isna().all().all())

    def test_rejection_and_unknown_proof_suppress_both_labels(self):
        for changes in ({"rejected": 1}, {"rejected": None}, {"rejected": -1}, {"rejected": False},
                        {"run_id": None}, {"purchase_generated": False}, {"purchase_generated": None}):
            with self.subTest(changes=changes):
                out = self.outcomes(self.frame([(self.t0, 12000)]), **changes)
                self.assertTrue(out.isna().all().all())
                self.assertEqual("not_run", out.attrs["outcome_observation"]["status"])

    def test_partial_amount_invalid_and_missing_row_are_not_totals(self):
        import numpy as np
        from src.decision.features.sprint_table import summarize_outcomes
        for amount in (None, np.nan, np.inf):
            with self.subTest(amount=amount):
                out = self.outcomes(self.frame([(self.t0, 12000), (self.t0 + timedelta(days=1), amount)]))
                summary = summarize_outcomes(out, out.index)
                self.assertIsNone(summary["revenue_krw"])
                self.assertEqual(0.5, summary["churn_rate"])
                self.assertEqual(2, summary["purchases"])
        out = self.outcomes(self.frame([(self.t0, 12000)]))
        summary = summarize_outcomes(out, [*out.index, "C00000003"])
        self.assertEqual(1, summary["n_outcome_missing"])
        self.assertIsNone(summary["revenue_krw"])
        self.assertEqual(12000, summary["observed_revenue_sum_krw"])
        self.assertIsNone(summary["churn_rate"])

    def test_field_masks_empty_population_and_evidence_required(self):
        import numpy as np
        from src.decision.features.sprint_table import summarize_outcomes
        out = self.outcomes(self.frame([(self.t0, 12000)]))
        out.loc["C00000002", "churn"] = np.nan
        summary = summarize_outcomes(out, out.index)
        self.assertIsNone(summary["churn_rate"])
        self.assertEqual(12000, summary["revenue_krw"])
        self.assertEqual(1, summary["field_observation"]["churn"]["n_missing"])
        out.loc["C00000001", "revenue"] = np.inf
        self.assertEqual(1, summarize_outcomes(out, out.index)["field_observation"]["revenue"]["n_invalid"])
        self.assertIsNone(summarize_outcomes(out, [])["revenue_krw"])
        out.attrs.clear()
        self.assertIsNone(summarize_outcomes(out, out.index)["purchases"])

    def test_same_run_record_missing_corrupt_duplicate_and_wrong_id(self):
        import json
        from types import SimpleNamespace
        from unittest import mock
        from src.measurement import sink
        summary = SimpleNamespace(run_id="fixture-179", start=self.t0, end=self.end)
        for records in ([], [{"run_id": "other", "rejected": 0}],
                        [{"run_id": "fixture-179", "unreadable": "bad JSON"}],
                        [{"run_id": "fixture-179"}], [{"run_id": "fixture-179", "rejected": False}],
                        [{"run_id": "fixture-179", "rejected": 0}] * 2):
            with self.subTest(records=records), mock.patch.object(sink, "run_records", return_value=records):
                self.assertIsNone(self.runner.outcome_observation(summary, Path("unused"), None)["rejected"])
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "runs").mkdir()
            file = root / "runs/run-fixture-179.json"
            file.write_text("{", encoding="utf-8")
            self.assertIsNone(self.runner.outcome_observation(summary, root, None)["rejected"])
            file.write_text(json.dumps({"run_id": "fixture-179", "rejected": 0}), encoding="utf-8")
            self.assertEqual(0, self.runner.outcome_observation(summary, root, None)["rejected"])

    def test_strict_sink_hides_rejected_purchase_from_field_coverage(self):
        import pandas as pd
        from types import SimpleNamespace
        from src.decision.data import _coerce
        from src.decision.features.sprint_table import build_outcomes
        from src.measurement import sink
        records = make_events(n_customers=2)
        valid = next(dict(r) for r in records if r["event_type"] == "purchase")
        valid.update(timestamp=(self.t0 + timedelta(days=1)).isoformat(), order_amount=12000)
        invalid = {**valid, "event_id": str(uuid.uuid4()), "order_id": "O00000002-999999"}
        invalid.pop("order_amount")
        past = dict(next(r for r in records if r["customer_id"] == valid["customer_id"]))
        with tempfile.TemporaryDirectory() as temp:
            with sink.EventSink(temp, fmt="jsonl.gz", run_id="fixture-179", strict=True) as writer:
                written = writer.write_events([past, valid, invalid])
            self.assertEqual(1, written.rejected)
            frame = _coerce(pd.DataFrame(list(sink.read_events(temp))))
            record = sink.run_records(temp)[0]
            self.assertEqual(1.0, record["field_coverage"]["order_amount"])
            evidence = self.runner.outcome_observation(
                SimpleNamespace(run_id="fixture-179", start=self.t0, end=self.end), Path(temp), self.raw_metrics())
            out = build_outcomes(frame, self.t0, observation=evidence, allow_incomplete=True)
            self.assertTrue(out.isna().all().all())
            self.assertIn("WRITE_REJECTED", out.attrs["outcome_observation"]["reasons"])

    @staticmethod
    def raw_metrics(status="ok"):
        from src.measurement import schema as sc
        if status == "ok":
            value = sc.MetricValue.ok(0, unit=sc.Unit.COUNT, basis=sc.Basis(
                population="합성 공개 API fixture", denominator_definition="분모 없음 (합계)",
                window=sc.Window(sc.WindowDirection.NONE)))
        else:
            value = sc.MetricValue(status=sc.MetricStatus.NOT_RUN,
                                   reason_code=sc.ReasonCode.PRECONDITION_MISSING,
                                   reason_detail="합성 구매 미지원")
        return {"events.purchase": value}

    def test_raw_zero_not_run_unknown_and_json_not_confused(self):
        from src.measurement import contracts
        self.assertIs(True, self.runner.purchase_generated(self.raw_metrics())[0])
        self.assertIs(False, self.runner.purchase_generated(self.raw_metrics("not_run"))[0])
        self.assertIsNone(self.runner.purchase_generated(None)[0])
        self.assertIsNone(self.runner.purchase_generated({})[0])
        encoded = {k: contracts.metric_to_json(v) for k, v in self.raw_metrics().items()}
        self.assertIsNone(self.runner.purchase_generated(encoded)[0])

    def test_ci_fake_outcomes_can_mask_integer_labels_without_importing_simulator(self):
        import ast
        import pandas as pd
        from src.decision.features.sprint_table import outcome_observation_status
        path = Path(__file__).with_name("test_orchestration_sprint.py")
        tree = ast.parse(path.read_text())
        selected = [node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == "FakeDecision"]
        self.assertEqual(1, len(selected))
        future = ast.ImportFrom(module="__future__", names=[ast.alias(name="annotations")], level=0)
        module = ast.fix_missing_locations(ast.Module(body=[future, *selected], type_ignores=[]))
        namespace = {"pd": pd, "timedelta": timedelta, "outcome_observation_status": outcome_observation_status}
        exec(compile(module, str(path), "exec"), namespace)
        fake = namespace["FakeDecision"]()
        evidence = {**self.evidence, "read_complete": False}
        result = fake.build_outcomes(self.frame(), self.t0, observation=evidence, allow_incomplete=True)
        self.assertTrue(result.isna().all().all())
        self.assertEqual("not_run", result.attrs["outcome_observation"]["status"])
        with self.assertRaises(ValueError):
            fake.build_outcomes(self.frame(), self.t0, observation=evidence)

    def test_null_propagates_to_direction_and_guards_preserves_independent_roi(self):
        import numpy as np
        from src.decision.features.sprint_table import summarize_outcomes
        from src.decision.roi import summarize_strategy
        out = self.outcomes(self.frame([(self.t0, 12000)]))
        out.loc["C00000001", "revenue"] = np.nan
        bad = {**summarize_outcomes(out, out.index), "planned_treatment_cost_krw": 150}
        good = {"revenue_krw": 10000, "planned_treatment_cost_krw": 100}
        row = summarize_strategy(bad, good)
        self.assertIsNone(row["directional_revenue_minus_marketing_vs_S1"])
        measured = {"measured_contribution_profit": 300, "measured_marketing_cost": 150}
        base = {**good, "measured_contribution_profit": 200, "measured_marketing_cost": 100}
        row = summarize_strategy({**bad, **measured}, base)
        self.assertEqual(2, row["roi"])
        self.assertIsNone(row["guardrails"]["revenue_up_profit_down"]["triggered"])
        out = self.outcomes(purchase_generated=False)
        row = summarize_strategy({**summarize_outcomes(out, out.index), **measured}, base)
        self.assertEqual(2, row["roi"])
        self.assertIsNone(row["guardrails"]["retention_up_cost_surge"]["triggered"])

    def run_fake_contract(self, *, states=None, rejected=None, read_fail=None, include_uplift=False,
                          real_margin=False, profile="smoke", warmup_days=90):
        """가짜 생성·가짜 모델과 실제 run/build_outcomes/집계/ROI를 연결한다. 실제 학습·E2E 아님.

        ``profile`` · ``warmup_days`` 는 SprintConfig 로 그대로 넘긴다. ``warmup_days=None`` 이면 run() 이
        warmup 을 스스로 고른다(#211 · ``resolve_warmup``)."""
        import contextlib
        import io
        import json
        from types import SimpleNamespace
        from unittest import mock
        import pandas as pd
        from src.decision.features import sprint_table as table
        from src.decision.data import _coerce
        from src.decision.roi import summarize_strategy
        from src.measurement import sink

        rs = self.runner
        states, rejected = states or {}, rejected or {}
        payloads, captured, frames, records, metric_calls, holdout_calls = {}, {}, {}, {}, [], []
        clock = {"now": datetime(2026, 1, 1, tzinfo=KST), "root": None, "number": 0}

        def key(root):
            return root.parent.name if root.parent.parent.name == "branches" else "main"

        def init(seed, num_customers, profile, *, output_root):
            clock["root"] = output_root

        def advance(days):
            root, start = clock["root"], clock["now"]
            end = start + timedelta(days=days)
            clock["now"] = end
            clock["number"] += 1
            rid = f"public-fixture-{clock['number']}"
            rows = []
            source_meta = {"simulator_version": "fixture-public-api", "random_seed": 7}
            for i in range(1, 41):
                rows.append({**source_meta, "customer_id": f"C{i:08d}", "event_type": "page_view", "event_id": f"e{rid}-{i}",
                             "timestamp": start + timedelta(days=1), "order_id": None, "order_amount": None})
                if days != 42 or i % 2 == 0:
                    rows.append({**source_meta, "customer_id": f"C{i:08d}", "event_type": "purchase", "event_id": f"p{rid}-{i}",
                                 "timestamp": start + timedelta(days=2), "order_id": f"o{rid}-{i}", "order_amount": 12000})
            frame = _coerce(pd.DataFrame(rows))
            frames[root] = pd.concat([frames[root], frame], ignore_index=True) if root in frames else frame
            refused = rejected.get("warmup", rejected.get(key(root), 0)) if clock["number"] == 1 else rejected.get(key(root), 0)
            records.setdefault(root, []).append({"run_id": rid, "rejected": refused})
            return SimpleNamespace(start=start, end=end, run_id=rid, event_count=len(rows))

        def snapshot():
            clock["snapshot_at"] = clock["now"]
            return "opaque-fixture-token"

        def restore(token, *, output_root):
            assert token == "opaque-fixture-token"
            clock.update(now=clock["snapshot_at"], root=output_root)

        def public_records(frame):
            # 공개 이벤트의 결손은 null이다. DataFrame의 NaN/pd.NA를 API 값으로 내보내지 않는다.
            return frame.astype(object).where(frame.notna(), None).to_dict("records")

        def events(until):
            # 공개 events 계약: 현재 분기와 본선의 과거를 전량 제공한다.
            parts = [frame for root, frame in frames.items() if key(root) == "main" or root == clock["root"]]
            all_rows = pd.concat(parts, ignore_index=True)
            yield from public_records(all_rows.loc[all_rows["timestamp"] < until])

        def metrics(start, end):
            world = key(clock["root"])
            metric_calls.append(world)
            purpose = ("main_history" if start == datetime(2026, 1, 1, tzinfo=KST) else "main_label")
            status = states.get(purpose if world == "main" else world, states.get(world, "ok"))
            captured.setdefault("metric_windows", []).append((world, start, end))
            if status == "error":
                raise RuntimeError("합성 metrics 실패")
            raw = {} if status == "unknown" else self.raw_metrics(status)
            if real_margin and world == "main":
                from src.measurement import schema as sc
                amounts = {"revenue": 10000, "contribution_profit": 3000} if purpose == "main_history" else {
                    "revenue": 1000, "contribution_profit": 50}
                raw.update({name: sc.MetricValue.ok(value, unit=sc.Unit.KRW, basis=sc.Basis(
                    population="시험용 창별 금액", denominator_definition="분모 없음 (합계)",
                    window=sc.Window(sc.WindowDirection.NONE))) for name, value in amounts.items()})
            return raw

        def temporal(model, X_train, y_train, X_test, y_test, seed=0):
            holdout_calls.append(y_test.copy())
            return {"name": "fixture", "scheme": "synthetic connection only", "n_test": len(y_test)}

        def verify(root, rid, *, history_evidence=None):
            root = next(p for p in records if p.resolve() == Path(root).resolve())
            run_rejections = {**((history_evidence or {}).get("run_rejections", {})),
                              **{r["run_id"]: r["rejected"] for r in records[root]}}
            return {"status": "not_run" if key(root) == read_fail and rid != "public-fixture-1" else "ok",
                    "reason": "합성 파일 읽기 실패" if key(root) == read_fail else None,
                    "run_id": rid, "root": str(root.resolve()), "rejected": run_rejections[rid],
                    "verified_run_ids": sorted(run_rejections), "run_rejections": run_rejections,
                    "chain_rejected_total": sum(run_rejections.values()),
                    "ancestor_rejected_total": sum(v for k, v in run_rejections.items() if k != rid),
                    "ancestor_rejection_policy": "audit_only_no_new_feature_or_s1_gate"}

        fns = {
            "load_events": lambda root: frames[root].copy(),
            "build_feature_table": table.build_feature_table, "build_outcomes": table.build_outcomes,
            "summarize_outcomes": table.summarize_outcomes,
            "evaluate_churn_models": lambda X, y, seed: {"models": [], "best_proposed": None},
            "fit_best_churn": lambda X, y, seed: SimpleNamespace(name="fixture"),
            "evaluate_temporal_holdout": temporal, "plan": lambda *args: {},
            "predict_churn_proba": lambda model, X: pd.Series(0.5, index=X.index),
            "s1_eligibility": lambda scores: {}, "summarize_strategy": summarize_strategy,
        }

        def decision(name):
            if name not in fns:
                raise rs.NotRun("합성 연결 시험 범위 밖: " + name)
            return fns[name]

        def economics(root, end):
            values = {"revenue": 20000, "marketing_cost": 100, "contribution_profit": 500}
            return {"status": "ok", "metrics": {k: {"status": "ok", "value": v} for k, v in values.items()}}

        def write(root, rid, values, extra):
            # 실제 직렬화도 대조한다. NaN을 0으로 바꾸지 않으며 JSON에는 NaN이 없어야 한다.
            payloads.update(json.loads(json.dumps(rs.to_jsonable(values), allow_nan=False)))
            return root / rid

        api = SimpleNamespace(init=init, advance=advance, apply_treatment=lambda assignments: None,
                              snapshot=snapshot, restore=restore, discard_snapshot=lambda token: None, metrics=metrics, events=events)
        selected = frozenset({"simulate_warmup", "read_events_t1", "rct_assign", "features_t1", "simulate_rct",
                              "read_events_t2", "outcomes_t1", "training_set", "churn", "features_t2", "snapshot_t2",
                              "strategy_S0", "strategy_S1", "roi_summary", "churn_temporal_holdout"})
        selected = selected | {"scores_t2"}
        from src.decision.churn import temporal_population_audit
        fns["temporal_population_audit"] = temporal_population_audit
        if include_uplift:
            from src.decision.churn import make_risk_model_factory
            def evaluate_uplift(X, treatment, y, seed=0, *, risk_model_factory=None):
                captured["uplift_factory"] = risk_model_factory
                captured["uplift_X"] = X.copy()
                captured["uplift_y"] = y.copy()
                return {"best_method": "s_learner", "models": []}
            fns.update(make_risk_model_factory=make_risk_model_factory,
                       evaluate_uplift_models=evaluate_uplift,
                       fit_uplift=lambda X, treatment, y, method, seed=0: object())
            selected = selected | {"uplift"}
        with tempfile.TemporaryDirectory() as temp, contextlib.ExitStack() as stack:
            patches = {"sim": api, "decision_fn": decision, "decision_available": lambda name: name in fns,
                                "verify_event_run": verify,
                                "branch_economics": economics,
                                "provenance": lambda *args, **kwargs: {"fixture": True},  # #262 — 시작 상태를 받는다
                                "write_results": write}
            if not real_margin:
                patches["margin_rate_basis"] = lambda raw: (None, {"status": "not_run", "reason": "범위 밖"})
            for name, value in patches.items():
                stack.enter_context(mock.patch.object(rs, name, value, create=True))
            stack.enter_context(mock.patch.object(rs, "customer_signups", return_value={
                f"C{i:08d}": datetime(2026, 1, 1, tzinfo=KST).date() for i in range(1, 41)}))
            stack.enter_context(mock.patch.object(sink, "run_records", side_effect=lambda root: records.get(root, [])))
            stack.enter_context(mock.patch.object(sink, "read_events", side_effect=lambda root: public_records(next(
                frame for path, frame in frames.items() if path.resolve() == Path(root).resolve()))))
            stack.enter_context(contextlib.redirect_stdout(io.StringIO()))
            stack.enter_context(contextlib.redirect_stderr(io.StringIO()))
            rs.run(rs.SprintConfig(seed=7, num_customers=40, profile=profile, warmup_days=warmup_days,
                                   out=Path(temp) / "out", results_root=Path(temp) / "results", stages=selected,
                                   realism_report=Path(temp) / "absent.json", capture=captured))
        return payloads, captured, metric_calls, holdout_calls

    def test_real_runner_default_profile_takes_config_warmup(self):
        """#211 · DR-211 — warmup 인자 없이 config 프로파일(reference)로 돌면 config `run.warmup_days` 312일을 쓰고
        그 출처를 run_meta 에 적는다. 다른 프로파일(smoke)은 그 프로파일 권장값이다.

        run() 의 warmup 고르기를 예전 식(인자 아니면 프로파일 권장값)으로 되돌리면 reference 가 273일이 되어
        여기서 실패한다. `resolve_warmup` 단독 검사(test_decision_config)는 run() 을 부르지 않아 그것을 못 잡는다.
        """
        cases = {
            "reference": (312, "config/experiment_config.yaml run.warmup_days"),
            "smoke": (90, "data_spec §2.2 프로파일 권장값"),
        }
        for profile, (days, basis) in cases.items():
            with self.subTest(profile=profile):
                result, _, _, _ = self.run_fake_contract(profile=profile, warmup_days=None)
                meta = result["run_meta"]
                self.assertEqual((profile, days), (meta["profile"], meta["warmup_days"]))
                self.assertIn(basis, meta["warmup_basis"])
                timeline = {k: datetime.fromisoformat(v) for k, v in meta["timeline"].items()}
                self.assertEqual(days, (timeline["t1"] - timeline["start"]).days, "t1 이 warmup 만큼 뒤가 아니다")

    def test_real_runner_uses_separate_main_windows_and_one_call_per_branch(self):
        result, captured, calls, holdout = self.run_fake_contract()
        stages = {s["name"]: s for s in result["run_meta"]["stages"]}
        self.assertEqual([], [s for s in stages.values() if s["status"] == "failed"])
        self.assertEqual("ok", stages["outcomes_t1"]["status"])
        self.assertEqual("ok", stages["churn_temporal_holdout"]["status"])
        self.assertEqual(["main", "main", "S0", "S1"], calls)
        self.assertEqual(1, len(holdout))
        self.assertEqual(40, len(holdout[0]))
        audit = result["churn_eval"]["temporal_population_audit"]
        self.assertEqual(audit["training_and_selection"]["n_labeled"], audit["intersection_n"])
        self.assertEqual(40, audit["future_evaluation"]["n_labeled"])
        self.assertEqual("not_established_by_this_audit", audit["split_compliance"])
        self.assertEqual("ok", captured["Y1"].attrs["outcome_observation"]["status"])
        for strategy in ("S0", "S1"):
            row = result["strategy_comparison"]["strategy_details"][strategy]
            self.assertIs(True, row["purchase_generated"]["value"])
            self.assertEqual(240000, row["event_outcomes"]["revenue_krw"])

    def test_real_runner_s0_unknown_stops_only_temporal_labels(self):
        for status in ("unknown", "not_run", "error"):
            with self.subTest(status=status):
                result, captured, calls, holdout = self.run_fake_contract(states={"S0": status})
                stages = {s["name"]: s for s in result["run_meta"]["stages"]}
                self.assertEqual("ok", stages["churn"]["status"])
                self.assertEqual("not_run", stages["churn_temporal_holdout"]["status"])
                self.assertEqual([], holdout)
                self.assertTrue(captured["S0_outcomes"].isna().all().all())
                rows = result["strategy_comparison"]["strategy_details"]
                self.assertIsNone(rows["S0"]["event_outcomes"]["churn_rate"])
                self.assertIsNone(rows["S0"]["event_outcomes"]["revenue_krw"])
                self.assertEqual(240000, rows["S1"]["event_outcomes"]["revenue_krw"])
                self.assertEqual(500, rows["S0"]["metrics"]["measured_contribution_profit"])
                self.assertEqual(["main", "main", "S0", "S1"], calls)

    def test_margin_uses_history_window_and_actual_margin_calculation(self):
        result, captured, calls, _ = self.run_fake_contract(real_margin=True)
        self.assertEqual(0.3, captured["scores"]["margin_rate"])
        self.assertEqual(0.3, result["run_meta"]["margin_rate"]["value"])
        windows = captured["metric_windows"]
        self.assertEqual(datetime(2026, 1, 1, tzinfo=KST), windows[0][1])
        self.assertEqual(windows[0][1] + timedelta(days=90), windows[1][1])
        self.assertEqual(windows[0][2], windows[1][2])
        self.assertEqual(timedelta(days=42), windows[1][2] - windows[1][1])
        self.assertEqual(["main", "main", "S0", "S1"], calls)
        self.assertEqual(["margin_rate", "s1_purchase_gate"], result["run_meta"]["main_metric_windows"]["history"]["uses"])

    def test_main_history_and_label_purchase_states_are_independent(self):
        for history_state, label_state in (("unknown", "ok"), ("ok", "unknown"), ("error", "ok"), ("ok", "error")):
            with self.subTest(history=history_state, label=label_state):
                result, captured, _, _ = self.run_fake_contract(states={
                    "main_history": history_state, "main_label": label_state})
                stages = {s["name"]: s for s in result["run_meta"]["stages"]}
                self.assertEqual("ok" if label_state == "ok" else "not_run", stages["outcomes_t1"]["status"])
                self.assertEqual(history_state == "ok", "eligible" in captured["scores"])
                self.assertEqual(history_state == "ok", result["run_meta"]["purchase_generated"]["value"] is True)

    def test_ancestor_rejections_reach_meta_features_and_branch_without_new_gate(self):
        result, captured, _, _ = self.run_fake_contract(rejected={"warmup": 1})
        evidence = result["run_meta"]["event_read_evidence"]["t2"]
        self.assertEqual(0, evidence["rejected"])
        self.assertEqual(1, evidence["ancestor_rejected_total"])
        for name in ("X1", "X2"):
            self.assertEqual(1, captured[name].attrs["event_read_evidence"]["chain_rejected_total"])
        self.assertIn("eligible", captured["scores"])
        self.assertEqual("ok", captured["Y1"].attrs["outcome_observation"]["status"])
        for row in result["strategy_comparison"]["strategy_details"].values():
            if "event_read_evidence" in row:
                self.assertEqual(1, row["event_read_evidence"]["ancestor_rejected_total"])

    def test_real_runner_main_unknown_and_writer_rejections_do_not_train(self):
        for kwargs in ({"states": {"main": "unknown"}}, {"rejected": {"main": 1}}):
            with self.subTest(kwargs=kwargs):
                result, captured, calls, holdout = self.run_fake_contract(**kwargs)
                stages = {s["name"]: s for s in result["run_meta"]["stages"]}
                self.assertEqual("not_run", stages["outcomes_t1"]["status"])
                self.assertEqual("not_run", stages["churn"]["status"])
                self.assertTrue(captured["Y1"].isna().all().all())
                self.assertEqual([], holdout)
                self.assertEqual("ok", stages["strategy_S0"]["status"])
                self.assertEqual("ok", stages["strategy_S1"]["status"])

    def test_real_runner_writer_rejection_blocks_same_store_economics_only(self):
        result, captured, calls, holdout = self.run_fake_contract(rejected={"S0": 1})
        self.assertEqual([], holdout)
        self.assertTrue(captured["S0_outcomes"].isna().all().all())
        rows = result["strategy_comparison"]["strategy_details"]
        self.assertIsNone(rows["S0"]["event_outcomes"]["revenue_krw"])
        self.assertEqual(240000, rows["S1"]["event_outcomes"]["revenue_krw"])
        self.assertIsNone(rows["S0"]["metrics"]["measured_contribution_profit"])
        self.assertEqual(500, rows["S0"]["measured_economics"]["metrics"]["contribution_profit"]["value"])
        self.assertEqual(500, rows["S1"]["metrics"]["measured_contribution_profit"])
        self.assertEqual("not_run", rows["S0"]["economics_input_observation"]["status"])

    def test_runner_passes_fixed_factory_separately_from_global_churn_model(self):
        result, captured, _, _ = self.run_fake_contract(include_uplift=True)
        stages = {s["name"]: s for s in result["run_meta"]["stages"]}
        self.assertEqual("ok", stages["uplift"]["status"])
        factory = captured["uplift_factory"]
        self.assertTrue(callable(factory))
        self.assertEqual("logistic_regression", factory.specification["name"])
        self.assertEqual("predeclared_config_no_data_selection", factory.specification["selection"])
        self.assertEqual(40, len(captured["uplift_X"]))
        self.assertEqual({0.0, 1.0}, set(captured["uplift_y"]))

    def test_runner_read_failure_blocks_dependent_labels_and_snapshot(self):
        result, _, calls, holdout = self.run_fake_contract(read_fail="main")
        stages = {s["name"]: s for s in result["run_meta"]["stages"]}
        self.assertEqual([], [s for s in stages.values() if s["status"] == "failed"])
        for name in ("read_events_t2", "outcomes_t1", "churn", "snapshot_t2", "strategy_S0", "strategy_S1"):
            self.assertEqual("not_run", stages[name]["status"])
        self.assertEqual([], calls)
        self.assertEqual([], holdout)

    def test_branch_read_failure_does_not_keep_formal_roi_aliases(self):
        result, captured, _, holdout = self.run_fake_contract(read_fail="S0")
        rows = result["strategy_comparison"]["strategy_details"]
        self.assertIsNone(rows["S0"]["event_outcomes"]["revenue_krw"])
        self.assertIsNone(rows["S0"]["metrics"]["measured_contribution_profit"])
        self.assertEqual("not_run", rows["S0"]["measured_economics"]["status"])
        self.assertEqual(500, rows["S1"]["metrics"]["measured_contribution_profit"])
        self.assertTrue(captured["S0_outcomes"].isna().all().all())
        self.assertEqual([], holdout)


@unittest.skipUnless(HAVE_ML, SKIP_REASON)
class Test179RunReadIntegrity(unittest.TestCase):
    @staticmethod
    def row():
        return dict(make_events(n_customers=2, days=20)[0])

    def write(self, root, rid, rows, parent=None, fmt="jsonl.gz"):
        from src.measurement.sink import EventSink
        with EventSink(root, fmt=fmt, run_id=rid, parent_run_id=parent) as sink:
            self.assertEqual(0, sink.write_events(rows).rejected)

    def test_same_run_content_and_raw_count_before_dedup(self):
        from src.decision.data import verify_event_run, load_events
        for fmt in ("jsonl.gz", "parquet"):
            if fmt == "parquet" and importlib.util.find_spec("pyarrow") is None:
                self.skipTest("BLOCKED: pyarrow 미설치 — Parquet 원시 행 대조 미실행")
            with self.subTest(fmt=fmt), tempfile.TemporaryDirectory() as temp:
                self.write(temp, "a", [self.row()], fmt=fmt)
                self.write(temp, "b", [self.row(), self.row()], parent="a", fmt=fmt)
                proof = verify_event_run(temp, "b")
                self.assertEqual("ok", proof["status"], proof)
                self.assertEqual(2, proof["raw_rows"])
                loaded = load_events(temp)
                self.assertEqual(1, len(loaded))
                self.assertEqual(2, loaded.attrs["duplicate_event_ids"])

    def test_missing_modified_unclaimed_and_outside_files_are_not_complete(self):
        import json
        from src.decision.data import verify_event_run
        for change in ("missing", "modified", "unclaimed", "outside", "rows"):
            with self.subTest(change=change), tempfile.TemporaryDirectory() as temp:
                root = Path(temp)
                self.write(root, "a", [self.row()])
                record_path = root / "runs/run-a.json"
                record = json.loads(record_path.read_text())
                part = root / record["files"][0]
                if change == "missing":part.unlink()
                elif change == "modified":part.write_bytes(part.read_bytes() + b"broken")
                elif change == "unclaimed":(part.parent / "part-9999.jsonl.gz").write_bytes(part.read_bytes())
                elif change == "outside":record["files"] = ["../outside.txt"]
                else:record["rows"] += 1
                record_path.write_text(json.dumps(record))
                self.assertEqual("not_run", verify_event_run(root, "a")["status"])

    def test_corrupt_missing_and_noninteger_metadata_is_unknown(self):
        import json
        from src.decision.data import verify_event_run
        for change in ("list", "corrupt", "missing", "bool", "negative", "cycle", "wrong_id", "commerce"):
            with self.subTest(change=change), tempfile.TemporaryDirectory() as temp:
                root = Path(temp)
                self.write(root, "a", [self.row()])
                path = root / "runs/run-a.json"
                record = json.loads(path.read_text())
                if change == "list":record = []
                elif change == "missing":record.pop("rows")
                elif change == "bool":record["rejected"] = False
                elif change == "negative":record["rejected"] = -1
                elif change == "cycle":record["parent_run_id"] = "a"
                elif change == "wrong_id":record["run_id"] = "other"
                elif change == "commerce":record["sources"] = {"commerce": record["rows"]}
                path.write_text("{" if change == "corrupt" else json.dumps(record))
                self.assertEqual("not_run", verify_event_run(root, "a")["status"])

    def test_external_parent_requires_verified_history_and_zero_run_is_zero(self):
        from types import SimpleNamespace
        from src.decision.data import verify_event_run
        from src.decision.features.sprint_table import build_outcomes
        rs = _contract_runner()
        try:
            with tempfile.TemporaryDirectory() as temp:
                root = Path(temp)
                main, branch = root / "main", root / "branch"
                self.write(main, "a", [self.row()])
                self.write(branch, "b", [], parent="a")
                self.assertEqual("not_run", verify_event_run(branch, "b")["status"])
                self.assertEqual("not_run", verify_event_run(branch, "b", known_parent_runs=["a"])["status"])
                proof = verify_event_run(branch, "b", history_evidence=verify_event_run(main, "a"))
                self.assertEqual("ok", proof["status"], proof)
                self.assertEqual(0, proof["raw_rows"])
                start, end = FIXTURE_T0, FIXTURE_T0 + timedelta(days=42)
                reader = rs.EventReader()
                history = reader.read(main, start, run_id="a")
                events = reader.read(branch, end, history=history, run_id="b")
                observed = rs.outcome_observation(SimpleNamespace(run_id="b", start=start, end=end), branch,
                    TestOutcomeObservationContract.raw_metrics(), events.attrs["run_read_evidence"])
                labels = build_outcomes(events, start, observation=observed)
                self.assertEqual([1], labels.churn.tolist())
                self.assertEqual([0], labels.purchases.tolist())
                self.assertEqual([0], labels.revenue.tolist())
        finally:
            import sys
            sys.modules.pop(rs.__name__, None)

    def test_reader_does_not_load_bad_source_or_accept_other_root_proof(self):
        from types import SimpleNamespace
        from unittest import mock
        from src.decision.data import verify_event_run
        from src.measurement import sink
        rs = _contract_runner()
        try:
            with tempfile.TemporaryDirectory() as temp:
                root = Path(temp)
                reader = rs.EventReader()
                reader._load_events = mock.Mock()
                with self.assertRaises(rs.NotRun):reader.read(root, FIXTURE_T0, run_id="absent")
                reader._load_events.assert_not_called()
                summary = SimpleNamespace(run_id="a", start=FIXTURE_T0, end=FIXTURE_T0+timedelta(days=42))
                observed = rs.outcome_observation(summary, root, None,
                    {"status": "ok", "run_id": "a", "root": str(root / "other")})
                self.assertFalse(observed["read_complete"])
                self.write(root, "a", [self.row()])
                proof = verify_event_run(root, "a")
                proof["rejected"] = 1
                self.assertFalse(rs.outcome_observation(summary, root, None, proof)["read_complete"])
                with mock.patch.object(sink, "run_records", side_effect=OSError("합성 읽기 실패")):
                    self.assertEqual("not_run", verify_event_run(root, "a")["status"])
        finally:
            import sys
            sys.modules.pop(rs.__name__, None)

    def test_branch_must_join_exact_history_head_before_loading(self):
        from unittest import mock
        from src.decision.data import verify_event_run
        rs = _contract_runner()
        try:
            with tempfile.TemporaryDirectory() as temp:
                root = Path(temp)
                main = root / "main"
                self.write(main, "warmup", [self.row()])
                self.write(main, "rct", [self.row()], parent="warmup")
                reader = rs.EventReader()
                history = reader.read(main, FIXTURE_T0, run_id="rct")
                evidence = history.attrs["run_read_evidence"]
                for i, parent in enumerate(("rct", "warmup", None, "unrelated")):
                    with self.subTest(parent=parent):
                        branch = root / str(i)
                        self.write(branch, "branch", [], parent=parent)
                        proof = verify_event_run(branch, "branch", history_evidence=evidence)
                        if parent == "rct":
                            self.assertEqual("ok", proof["status"], proof)
                            self.assertEqual("rct", proof["external_parent_run_id"])
                            self.assertEqual("ok", proof["history_link_status"])
                            self.assertEqual(len(history), len(reader.read(branch, FIXTURE_T0, history=history, run_id="branch")))
                        else:
                            self.assertEqual("not_run", proof["status"])
                            with mock.patch.object(reader, "_load_events") as loader:
                                with self.assertRaises(rs.NotRun):
                                    reader.read(branch, FIXTURE_T0, history=history, run_id="branch")
                                loader.assert_not_called()
                invalid = dict(evidence)
                invalid.pop("run_rejections")
                self.assertEqual("not_run", verify_event_run(root / "0", "branch", history_evidence=invalid)["status"])
                with self.assertRaises(rs.NotRun):
                    reader.read(root / "0", FIXTURE_T0, history=history)
        finally:
            import sys
            sys.modules.pop(rs.__name__, None)

    def test_rejected_ancestors_are_audited_and_carried_across_branch_once(self):
        from src.decision.data import verify_event_run
        from src.measurement.sink import EventSink
        rs = _contract_runner()
        try:
            with tempfile.TemporaryDirectory() as temp:
                root = Path(temp)
                main, branch = root / "main", root / "branch"
                with EventSink(main, fmt="jsonl.gz", run_id="warmup", strict=True) as sink:
                    bad = {**self.row(), "event_type": "purchase", "order_amount": None, "order_id": "refused"}
                    result = sink.write_events([self.row(), bad])
                    self.assertEqual(1, result.rejected)
                self.write(main, "rct", [self.row()], parent="warmup")
                reader = rs.EventReader()
                history = reader.read(main, FIXTURE_T0, run_id="rct")
                proof = history.attrs["run_read_evidence"]
                self.assertEqual("ok", proof["status"])
                self.assertEqual(0, proof["rejected"])
                self.assertEqual({"rct": 0, "warmup": 1}, proof["run_rejections"])
                self.assertEqual(1, proof["chain_rejected_total"])
                self.assertEqual(1, proof["ancestor_rejected_total"])
                self.write(branch, "branch", [], parent="rct")
                out = reader.read(branch, FIXTURE_T0, history=history, run_id="branch")
                chained = out.attrs["run_read_evidence"]
                self.assertEqual(1, chained["chain_rejected_total"])
                self.assertEqual(1, chained["ancestor_rejected_total"])
                self.assertEqual({"rct": 0, "warmup": 1, "branch": 0}, chained["run_rejections"])
                self.assertEqual("audit_only_no_new_feature_or_s1_gate", chained["ancestor_rejection_policy"])
        finally:
            import sys
            sys.modules.pop(rs.__name__, None)


if __name__ == "__main__":
    unittest.main()
