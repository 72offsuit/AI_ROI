"""코호트 · 퍼널 · 세그먼트 ROI — 합성 이벤트로 정답 대조 (스프린트 1 D11, 에픽 #142)."""

from __future__ import annotations

import contextlib
import io
import json
import tempfile
import unittest
from importlib.util import find_spec
from pathlib import Path

DEPS = all(find_spec(m) for m in ("numpy", "pandas", "sklearn"))
REASON = "BLOCKED: numpy/pandas/scikit-learn 미설치"

if DEPS:
    import pandas as pd

    from src.decision.analytics import cohort_retention, funnel, roi_by_segment


def ev(rows):
    """rows: (customer_id, 'YYYY-MM-DD HH:MM', event_type) — KST."""
    frame = pd.DataFrame(rows, columns=["customer_id", "timestamp", "event_type"])
    frame["timestamp"] = pd.to_datetime(frame["timestamp"]).dt.tz_localize("Asia/Seoul")
    return frame


@unittest.skipUnless(DEPS, REASON)
class TestFunnel(unittest.TestCase):
    def setUp(self) -> None:
        self.events = ev([
            # a: 전 단계 순서대로 → 구매까지
            ("a", "2026-01-01 10:00", "session_start"), ("a", "2026-01-01 10:01", "product_view"),
            ("a", "2026-01-01 10:02", "add_to_cart"), ("a", "2026-01-01 10:03", "checkout_start"),
            ("a", "2026-01-01 10:04", "purchase"),
            # b: 장바구니까지
            ("b", "2026-01-02 10:00", "session_start"), ("b", "2026-01-02 10:01", "product_view"),
            ("b", "2026-01-02 10:02", "add_to_cart"),
            # c: 방문만
            ("c", "2026-01-03 10:00", "session_start"),
            # d: 방문 전에 상품조회(순서 위반) → 순서 퍼널에서는 방문에서 멈춘다
            ("d", "2026-01-04 09:00", "product_view"), ("d", "2026-01-04 10:00", "session_start"),
            # e: 창 밖
            ("e", "2026-02-10 10:00", "session_start"), ("e", "2026-02-10 10:01", "product_view"),
        ])

    def test_counts_and_rates(self) -> None:
        r = funnel(self.events, "2026-01-01", "2026-02-01")
        steps = {s["step"]: s for s in r["steps"]}
        self.assertEqual([4, 2, 2, 1, 1], [s["n"] for s in r["steps"]])
        self.assertEqual(3, steps["product_view"]["n_any"])  # 순서 무시 도달 a·b·d
        self.assertIsNone(steps["visit"]["step_conversion"])
        self.assertAlmostEqual(0.5, steps["product_view"]["step_conversion"])
        self.assertAlmostEqual(0.5, steps["product_view"]["drop_off"])
        self.assertAlmostEqual(0.5, steps["checkout_start"]["step_conversion"])
        self.assertAlmostEqual(0.25, steps["purchase"]["overall_conversion"])
        self.assertEqual(4, r["n_customers_in_window"])

    def test_zero_denominator_is_none(self) -> None:
        r = funnel(self.events, "2025-01-01", "2025-02-01")
        self.assertTrue(all(s["n"] == 0 for s in r["steps"]))
        self.assertTrue(all(s["overall_conversion"] is None for s in r["steps"]))
        self.assertTrue(all(s["step_conversion"] is None for s in r["steps"]))


def _repurchase_journey(cid: str, opener: tuple[str, ...]) -> list[tuple[str, str, str]]:
    """1일차 세션에서 첫 구매, 10일차 세션에서 재구매. 10일차 세션을 여는 이벤트만 `opener` 로 바꾼다."""
    rows = [(cid, "2026-01-01 10:00", "session_start"), (cid, "2026-01-01 10:01", "product_view"),
            (cid, "2026-01-01 10:02", "add_to_cart"), (cid, "2026-01-01 10:03", "checkout_start"),
            (cid, "2026-01-01 10:04", "purchase")]
    rows += [(cid, "2026-01-10 10:00", event_type) for event_type in opener]
    rows += [(cid, "2026-01-10 10:01", "product_view"), (cid, "2026-01-10 10:02", "add_to_cart"),
             (cid, "2026-01-10 10:03", "checkout_start"), (cid, "2026-01-10 10:04", "purchase")]
    return rows


@unittest.skipUnless(DEPS, REASON)
class TestFunnelReturnVisit(unittest.TestCase):
    """#255 — 방문 단계는 `session_start ∪ return_visit` 이다.

    출처마다 `return_visit` 의 뜻이 다르다(#256). 시뮬레이터(#252)는 구매 뒤 첫 방문 세션을 `session_start`
    **대신** `return_visit` 으로 열고, 커머스는 이전 세션이 있는 고객의 새 세션마다 둘을 **함께** 남긴다.
    어느 쪽이든 창 안의 재구매 여정이 빠지지 않고, 함께 남긴 쪽도 방문을 두 번 세지 않아야 한다.
    """

    WINDOW = ("2026-01-05", "2026-01-20")  # 10일차 재구매 세션만 들어가는 창

    def setUp(self) -> None:
        self.sim = ev(_repurchase_journey("sim", ("return_visit",)))
        self.commerce = ev(_repurchase_journey("commerce", ("session_start", "return_visit")))
        self.both = pd.concat([self.sim, self.commerce], ignore_index=True)

    def test_session_opened_by_return_visit_is_counted(self) -> None:
        """#255 재현 — 고치기 전에는 시뮬레이터 방식 고객이 방문 단계부터 0 이었다."""
        r = funnel(self.sim, *self.WINDOW)
        self.assertEqual([1, 1, 1, 1, 1], [s["n"] for s in r["steps"]])

    def test_both_sources_are_counted_in_window(self) -> None:
        r = funnel(self.both, *self.WINDOW)
        self.assertEqual([2, 2, 2, 2, 2], [s["n"] for s in r["steps"]])
        self.assertEqual([2, 2, 2, 2, 2], [s["n_any"] for s in r["steps"]])
        self.assertAlmostEqual(1.0, r["steps"][-1]["overall_conversion"])

    def test_session_start_with_return_visit_is_one_visit(self) -> None:
        """커머스 방식 — 한 세션에 두 이벤트가 있어도 방문 단계는 고객별 첫 시각 하나다."""
        r = funnel(self.commerce, *self.WINDOW)
        visit = r["steps"][0]
        self.assertEqual((1, 1), (visit["n"], visit["n_any"]))
        self.assertEqual([1, 1, 1, 1, 1], [s["n"] for s in r["steps"]])
        self.assertAlmostEqual(1.0, r["steps"][1]["step_conversion"])

    def test_whole_range_is_unchanged(self) -> None:
        """관측 전 구간은 두 고객 모두 첫 세션이 `session_start` 라 고치기 전과 같다."""
        r = funnel(self.both)
        self.assertEqual([2, 2, 2, 2, 2], [s["n"] for s in r["steps"]])

    def test_step_rows_list_their_event_types(self) -> None:
        """`funnel.json` 단계 행은 그 단계로 세는 이벤트 유형을 목록으로 싣는다 — 단일 유형도 목록이다."""
        r = funnel(self.both, *self.WINDOW)
        self.assertEqual(["session_start", "return_visit"], r["steps"][0]["event_types"])
        self.assertEqual([["product_view"], ["add_to_cart"], ["checkout_start"], ["purchase"]],
                         [s["event_types"] for s in r["steps"][1:]])
        json.dumps(r)  # 직렬화 가능해야 한다(analytics_report 가 그대로 쓴다)

    def test_string_event_type_is_rejected(self) -> None:
        """예전 형식(문자열 하나)을 넘기면 글자 단위로 쪼개져 조용히 0 이 된다 — 그 대신 거부한다."""
        with self.assertRaises(TypeError):
            funnel(self.both, steps=(("visit", "session_start"),))


@unittest.skipUnless(DEPS, REASON)
class TestCohort(unittest.TestCase):
    def test_retention_and_right_censoring(self) -> None:
        events = ev([
            # 1월 코호트 4명: a 는 2월·3월, b 는 2월, c 는 4월, d 는 없음
            ("a", "2026-01-05 10:00", "purchase"), ("a", "2026-02-05 10:00", "purchase"),
            ("a", "2026-03-05 10:00", "purchase"),
            ("b", "2026-01-06 10:00", "purchase"), ("b", "2026-02-06 10:00", "purchase"),
            ("c", "2026-01-07 10:00", "purchase"), ("c", "2026-04-07 10:00", "purchase"),
            ("d", "2026-01-08 10:00", "purchase"),
            # 2월 코호트 2명: e 는 3월
            ("e", "2026-02-10 10:00", "purchase"), ("e", "2026-03-10 10:00", "purchase"),
            ("f", "2026-02-11 10:00", "purchase"),
            # 관측 끝 = 4월 30일 (세션 이벤트)
            ("z", "2026-04-30 23:00", "session_start"),
        ])
        r = cohort_retention(events, "M")
        jan, feb = r["cohorts"][0], r["cohorts"][1]
        self.assertEqual(("2026-01", 4), (jan["cohort"], jan["size"]))
        self.assertAlmostEqual(0.5, jan["retention"]["1"])   # a·b
        self.assertAlmostEqual(0.25, jan["retention"]["2"])  # a
        self.assertIsNone(jan["retention"]["4"])  # 5월 — 관측 안 끝남, 0 이 아니다
        # 4월은 관측 끝(4/30 23:00)이 기간 끝(5/1 00:00) 전이라 아직 미완 → None
        self.assertIsNone(jan["retention"]["3"])
        self.assertAlmostEqual(0.5, feb["retention"]["1"])   # e
        self.assertTrue(jan["left_censored_cohort"])
        self.assertFalse(feb["left_censored_cohort"])
        # ANA-001 M1 = 코호트 크기 가중 평균 (4·0.5 + 2·0.5)/6
        self.assertAlmostEqual(0.5, r["ana001"]["M1"])
        self.assertIsNone(r["ana001"]["M6"])
        self.assertIsNone(r["ana001"]["M12"])

    def test_observed_end_closes_period(self) -> None:
        events = ev([("a", "2026-01-05 10:00", "purchase"), ("b", "2026-01-06 10:00", "purchase"),
                     ("b", "2026-02-06 10:00", "purchase")])
        # 기본 관측 끝 = 마지막 이벤트(2/6) → 2월은 미완 → None
        self.assertIsNone(cohort_retention(events, "M")["cohorts"][0]["retention"]["1"])
        # 관측 끝을 3/1 00:00 으로 주면 2월이 닫힌다(기간 끝 == 관측 끝)
        r = cohort_retention(events, "M", observed_end="2026-03-01 00:00")
        self.assertAlmostEqual(0.5, r["cohorts"][0]["retention"]["1"])
        self.assertIsNone(r["cohorts"][0]["retention"]["2"])

    def test_no_purchase_is_not_computable(self) -> None:
        r = cohort_retention(ev([("a", "2026-01-01 10:00", "session_start")]))
        self.assertTrue(r["status"].startswith("계산 불가"))
        self.assertEqual({"M1": None, "M3": None, "M6": None, "M12": None}, r["ana001"])


@unittest.skipUnless(DEPS, REASON)
class TestRoiBySegment(unittest.TestCase):
    def test_missing_is_not_computable(self) -> None:
        self.assertEqual("계산 불가", roi_by_segment(None)["status"])
        r = roi_by_segment({"VIP": {"S3": {"contribution_profit": 10, "marketing_cost": 5}}})
        self.assertEqual("계산 불가", r["segments"]["VIP"]["status"])

    def test_matches_roi_module(self) -> None:
        r = roi_by_segment({"VIP": {
            "S1": {"contribution_profit": 100.0, "marketing_cost": 10.0},
            "S3": {"contribution_profit": 130.0, "marketing_cost": 20.0},
        }})
        row = r["segments"]["VIP"]["strategies"]["S3"]
        self.assertAlmostEqual(30.0, row["incremental_profit_vs_S1"])
        self.assertAlmostEqual(3.0, row["roi"])


@unittest.skipUnless(DEPS, REASON)
class TestReportCli(unittest.TestCase):
    def test_cli_writes_three_files_with_header(self) -> None:
        from src.decision.analytics_report import main

        rows = []
        for i in range(40):
            cid = f"c{i:02d}"
            for day in (3, 20, 45, 70):
                rows += [(cid, f"2026-01-01 10:{i % 50:02d}", "session_start")] if day == 3 else []
                stamp = (pd.Timestamp("2026-01-01") + pd.Timedelta(days=day + i % 5)).strftime("%Y-%m-%d 11:00")
                rows += [(cid, stamp, "session_start"), (cid, stamp.replace("11:00", "11:01"), "product_view")]
                if (i + day) % 3 == 0:
                    rows += [(cid, stamp.replace("11:00", "11:02"), "add_to_cart"),
                             (cid, stamp.replace("11:00", "11:03"), "checkout_start"),
                             (cid, stamp.replace("11:00", "11:04"), "purchase")]
        frame = ev(rows)
        frame.insert(0, "event_id", [f"e{k:05d}" for k in range(len(frame))])
        frame["timestamp"] = frame["timestamp"].map(lambda t: t.isoformat())
        frame["order_amount"] = [10000 if t == "purchase" else None for t in frame["event_type"]]
        frame["order_id"] = [f"o{k}" if t == "purchase" else None for k, t in enumerate(frame["event_type"])]
        with tempfile.TemporaryDirectory() as tmp:
            part = Path(tmp) / "events" / "date=2026-01-01"
            part.mkdir(parents=True)
            with open(part / "part-0000.jsonl", "w", encoding="utf-8") as fh:
                for rec in frame.to_dict("records"):
                    fh.write(json.dumps({k: v for k, v in rec.items() if v is not None and v == v}) + "\n")
            out = Path(tmp) / "out"
            with contextlib.redirect_stdout(io.StringIO()):
                code = main(["--events", tmp, "--index-times", "2026-02-01,2026-03-15", "--out-dir", str(out)])
            self.assertEqual(0, code)
            for name in ("funnel", "cohort", "drift"):
                body = json.loads((out / f"{name}.json").read_text(encoding="utf-8"))
                self.assertEqual("sprint-v0", body["sprint"])
                self.assertIs(False, body["sealed"])
                self.assertIn("+09:00", body["generated_at"])
            drift = json.loads((out / "drift.json").read_text(encoding="utf-8"))
            for key in ("drift_method", "features", "threshold_exceeded", "performance_over_time", "alerts"):
                self.assertIn(key, drift)  # MON-004 최소 구조
            self.assertEqual("not_run", drift["performance_over_time_status"]["status"])


if __name__ == "__main__":
    unittest.main()
