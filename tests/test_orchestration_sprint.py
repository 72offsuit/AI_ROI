"""스프린트 v0 실행 루프 (`src/orchestration/run_sprint.py`, 이슈 #146).

실제 시뮬레이터 api 로 소규모 세계를 돌리고, 의사결정 모듈은 합의된 시그니처의 **가짜 구현**을
`sys.modules` 에 주입해 흐름을 검증한다. 가짜는 정답을 맞히려는 것이 아니라 오케스트레이션이
무엇을 언제 넘기는지(Feature cutoff · 모집단 · 예산 · 같은 스냅샷)를 기록한다.

    python3 -m unittest tests.test_orchestration_sprint -v
"""

from __future__ import annotations

import ast
import contextlib
import importlib.util
import io
import json
import math
import sys
import tempfile
import types
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

_DEPS = all(importlib.util.find_spec(name) is not None for name in ("numpy", "pandas"))
_SKIP_REASON = "BLOCKED: numpy/pandas/scikit-learn 미설치"

if _DEPS:
    import pandas as pd

    from src.measurement import sink
    from src.orchestration import run_sprint as rs
    from src.simulator import api as sim

DECISION_MODULES = (
    "src.decision.data",
    "src.decision.features.sprint_table",
    "src.decision.churn",
    "src.decision.clv",
    "src.decision.uplift",
    "src.decision.segments",
    "src.decision.strategies",
    "src.decision.roi",
    "src.decision.ab_test",
)
KST = timezone(timedelta(hours=9))

# 소규모 세계 — smoke 프로파일, warmup 을 줄여 테스트 시간을 수 초로 둔다.
# smoke 의 달력 시작 2025-01-01 → t1 = 2025-02-15, t2 = 2025-03-29.
SMALL = {"seed": 7, "num_customers": 240, "profile": "smoke", "warmup_days": 45, "active_days": 30}
# sim-0.3 은 purchase 를 만들지 않는다. 가짜 로더가 이 시각 이전 add_to_cart 를 주문으로 바꿔
# S1 경로(마지막 구매 28~90일 · 주문 2회 이상)를 탈 고객을 만든다 — t2 보다 32일 앞이다.
FAKE_PURCHASE_BEFORE = datetime(2025, 2, 25, tzinfo=timezone(timedelta(hours=9)))


class FakeDecision:
    """합의된 시그니처의 가짜 의사결정 모듈 묶음. 호출을 기록한다."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, dict]] = []
        self.cutoff_violations: list[str] = []
        self.plans: dict[str, dict[str, str]] = {}

    def modules(self) -> dict[str, types.ModuleType]:
        def module(name: str, **fns) -> types.ModuleType:
            mod = types.ModuleType(name)
            for key, fn in fns.items():
                setattr(mod, key, fn)
            return mod

        return {
            "src.decision.data": module("src.decision.data", load_events=self.load_events),
            "src.decision.features.sprint_table": module(
                "src.decision.features.sprint_table",
                build_feature_table=self.build_feature_table, build_outcomes=self.build_outcomes,
            ),
            "src.decision.churn": module(
                "src.decision.churn",
                evaluate_churn_models=self.evaluate_churn_models, fit_best_churn=self.fit_best_churn,
                predict_churn_proba=self.predict_churn_proba,
                evaluate_temporal_holdout=self.evaluate_temporal_holdout,
            ),
            "src.decision.clv": module(
                "src.decision.clv", fit_clv=self.fit_clv, predict_clv=self.predict_clv,
                evaluate_clv=self.evaluate_clv,
            ),
            "src.decision.uplift": module(
                "src.decision.uplift", fit_uplift=self.fit_uplift, predict_cate=self.predict_cate,
                evaluate_uplift_models=self.evaluate_uplift_models,
            ),
            "src.decision.segments": module("src.decision.segments", assign_segments=self.assign_segments),
            "src.decision.strategies": module(
                "src.decision.strategies", plan=self.plan, planning_costs=self.planning_costs,
                s1_eligibility=self.s1_eligibility,
            ),
            "src.decision.roi": module("src.decision.roi", summarize_strategy=self.summarize_strategy),
            "src.decision.ab_test": module("src.decision.ab_test", analyze_ab=self.analyze_ab),
        }

    # data ------------------------------------------------------------------
    def load_events(self, raw_root):
        self.calls.append(("load_events", {"root": str(raw_root)}))
        frame = pd.DataFrame.from_records(list(sink.read_events(raw_root)))
        frame["timestamp"] = pd.to_datetime(frame["timestamp"], format="ISO8601")
        as_order = (frame["event_type"] == "add_to_cart") & (frame["timestamp"] < FAKE_PURCHASE_BEFORE)
        frame.loc[as_order, "event_type"] = "purchase"
        frame.loc[as_order, "order_amount"] = 30000
        return frame

    # features --------------------------------------------------------------
    def build_feature_table(self, events, index_time):
        latest = events["timestamp"].max()
        if latest >= index_time:
            self.cutoff_violations.append(f"{latest} >= {index_time}")
        self.calls.append(("build_feature_table", {"index_time": index_time, "n": len(events)}))
        grouped = events.groupby("customer_id")
        table = pd.DataFrame({
            "n_events": grouped.size().astype(float),
            "n_carts": grouped["event_type"].apply(lambda s: float((s == "add_to_cart").sum())),
        })
        last = grouped["timestamp"].max()
        table["days_since_last_purchase"] = (index_time - last).dt.days.astype(float)
        return table.sort_index()

    def build_outcomes(self, events, index_time, window_days=42):
        self.calls.append(("build_outcomes", {"index_time": index_time, "window_days": window_days}))
        before = events.loc[events["timestamp"] < index_time, "customer_id"].unique()
        window = events[(events["timestamp"] >= index_time)
                        & (events["timestamp"] < index_time + timedelta(days=window_days))]
        counts = window.groupby("customer_id").size().reindex(sorted(before), fill_value=0)
        carts = window[window["event_type"] == "add_to_cart"].groupby("customer_id").size()
        carts = carts.reindex(counts.index, fill_value=0)
        churn = (counts < counts.median()).astype(int)
        return pd.DataFrame({"churn": churn, "purchases": carts.astype(float),
                             "revenue": carts.astype(float) * 1000.0})

    # churn -----------------------------------------------------------------
    def evaluate_churn_models(self, X, y, seed):
        self.calls.append(("evaluate_churn_models", {"n": len(y), "seed": seed}))
        return {"models": {"fake": {"auc": None}}, "best_model": "fake"}

    def fit_best_churn(self, X, y, seed):
        return {"kind": "fake-churn"}

    def predict_churn_proba(self, model, X):
        return (1.0 / (1.0 + X["n_events"])).rename("churn_p")

    def evaluate_temporal_holdout(self, model, X_test, y_test):
        self.calls.append(("evaluate_temporal_holdout", {"n": len(y_test)}))
        return {"n": int(len(y_test))}

    # clv -------------------------------------------------------------------
    def fit_clv(self, X, future_value):
        return {"kind": "fake-clv"}

    def predict_clv(self, model, X):
        return (X["n_carts"] * 1000.0).rename("clv")

    def evaluate_clv(self, X, future_value, seed):
        return {"n": int(len(future_value))}

    # uplift ----------------------------------------------------------------
    def evaluate_uplift_models(self, X, treatment, y, seed):
        self.calls.append(("evaluate_uplift_models", {"arms": sorted(set(treatment))}))
        return {"best_method": "fake_t_learner", "qini": None}

    def fit_uplift(self, X, treatment, y, method):
        self.calls.append(("fit_uplift", {"method": method}))
        return {"kind": "fake-uplift"}

    def predict_cate(self, model, X):
        base = X["n_carts"] / (1.0 + X["n_events"])
        return pd.DataFrame({t: base * (i + 1) * 0.01 for i, t in enumerate(("T1", "T2", "T3", "T4"))})

    # segments · strategies · roi · ab --------------------------------------
    def assign_segments(self, churn_p, cate, clv):
        return pd.Series(["high" if p > churn_p.median() else "low" for p in churn_p], index=churn_p.index)

    def planning_costs(self, treatment_cost, message_cost_krw):
        return {t: float(treatment_cost[t]) + float(message_cost_krw) for t in ("T1", "T2", "T3", "T4")}

    def s1_eligibility(self, scores):
        return {"conditions": {k: "applied" if k in scores else "not_run"
                               for k in ("lifetime_order_count", "eligible")}}

    def plan(self, strategy_id, scores, budget_krw, costs):
        self.calls.append(("plan", {"strategy": strategy_id, "budget": budget_krw, "costs": dict(costs or {}),
                                    "keys": sorted(scores)}))
        if strategy_id == "S0":
            result: dict[str, str] = {}
        elif strategy_id == "S1":
            days, orders, ok = (scores["days_since_last_purchase"], scores["lifetime_order_count"],
                                scores["eligible"])
            picked = days[(days >= 28) & (days <= 90) & (orders >= 2) & ok]
            result = {cid: "T3" for cid in picked.index}
        else:
            key = {"S1": "days_since_last_purchase", "S2": "churn_p"}.get(strategy_id, "clv")
            ranked = scores[key].sort_values(ascending=False)
            k = min(len(ranked), int(budget_krw // costs["T3"]))
            result = {cid: "T3" for cid in ranked.index[:k]}
        self.plans[strategy_id] = result
        return result

    def summarize_strategy(self, metrics, baseline_metrics):
        return {"incremental_revenue_krw": metrics["revenue"] - baseline_metrics["revenue"]}

    def analyze_ab(self, df, arm_col, outcome_col, control="T0"):
        self.calls.append(("analyze_ab", {"outcome": outcome_col, "control": control}))
        return {"n": int(len(df)), "arms": sorted(df[arm_col].unique().tolist())}


def _quiet():
    """진행 로그(stdout)와 실패 단계의 traceback(stderr)을 테스트 출력에서 숨긴다."""
    stack = contextlib.ExitStack()
    stack.enter_context(contextlib.redirect_stdout(io.StringIO()))
    stack.enter_context(contextlib.redirect_stderr(io.StringIO()))
    return stack


def _read(run_dir: Path, name: str) -> dict:
    return json.loads((run_dir / f"{name}.json").read_text(encoding="utf-8"))


@unittest.skipUnless(_DEPS, _SKIP_REASON)
class TestSprintWithFakeDecision(unittest.TestCase):
    """실제 시뮬레이터 + 가짜 의사결정 모듈로 전 구간이 돈다."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.tmp = tempfile.TemporaryDirectory()
        base = Path(cls.tmp.name)
        cls.fake = FakeDecision()
        realism = base / "realism_report.json"
        realism.write_text('{"note": "test"}', encoding="utf-8")
        config = rs.SprintConfig(out=base / "out", results_root=base / "results", run_id="SP-test-fake",
                                 realism_report=realism, **SMALL)
        generated = mock.patch.object(rs, "purchase_generated", return_value=(True, "test: 가짜 로더가 만든다"))
        with mock.patch.dict(sys.modules, cls.fake.modules()), generated, _quiet():
            cls.run_dir = rs.run(config)
        cls.base = base

    @classmethod
    def tearDownClass(cls) -> None:
        cls.tmp.cleanup()

    def test_writes_seven_results_with_header_and_latest(self) -> None:
        for name in rs.RESULT_FILES:
            payload = _read(self.run_dir, name)
            self.assertEqual("sprint-v0", payload["sprint"], name)
            self.assertIs(False, payload["sealed"], name)
            self.assertEqual("SP-test-fake", payload["run_id"], name)
            self.assertIn("generated_at", payload, name)
        latest = self.base / "results" / "sprint-v0" / "latest"
        self.assertEqual(_read(self.run_dir, "run_meta"), _read(latest, "run_meta"))

    def test_every_stage_ok(self) -> None:
        stages = _read(self.run_dir, "run_meta")["stages"]
        bad = [s for s in stages if s["status"] != "ok"]
        self.assertEqual([], bad)
        names = [s["name"] for s in stages]
        for strategy in rs.STRATEGIES:
            self.assertIn(f"strategy_{strategy}", names)

    def test_features_never_see_events_at_or_after_index_time(self) -> None:
        self.assertEqual([], self.fake.cutoff_violations)
        index_times = [c[1]["index_time"] for c in self.fake.calls if c[0] == "build_feature_table"]
        meta = _read(self.run_dir, "run_meta")
        self.assertEqual([meta["timeline"]["t1"], meta["timeline"]["t2"]], [t.isoformat() for t in index_times])

    def test_rct_arms_follow_design(self) -> None:
        rct = _read(self.run_dir, "run_meta")["rct"]
        counts = rct["arm_counts"]
        total = sum(counts.values())
        self.assertEqual(rct["n_eligible"], total)
        self.assertLessEqual(abs(counts["T0"] - total / 2), 1)
        for arm in ("T1", "T2", "T3", "T4"):
            self.assertLessEqual(abs(counts[arm] - total / 8), 1)
        arms = [c[1]["arms"] for c in self.fake.calls if c[0] == "evaluate_uplift_models"]
        self.assertEqual([["T0", "T1", "T2", "T3", "T4"]], arms)

    def test_churn_trains_on_control_only(self) -> None:
        churn = _read(self.run_dir, "churn_eval")
        rct = _read(self.run_dir, "run_meta")["rct"]
        self.assertEqual("ok", churn["status"])
        self.assertEqual(churn["n"], [c[1]["n"] for c in self.fake.calls if c[0] == "evaluate_churn_models"][0])
        self.assertLessEqual(churn["n"], rct["arm_counts"]["T0"])
        self.assertIn("temporal_holdout", churn)

    def test_all_strategies_branch_from_one_snapshot_with_budget(self) -> None:
        meta = _read(self.run_dir, "run_meta")
        protocol = meta["strategy_comparison_protocol"]
        self.assertTrue(protocol["single_snapshot_token"])
        self.assertEqual(list(rs.STRATEGIES), protocol["strategies_restored_from_it"])
        plans = {c[1]["strategy"]: c[1] for c in self.fake.calls if c[0] == "plan"}
        self.assertEqual(list(rs.STRATEGIES), list(plans))
        self.assertEqual(7030, plans["S1"]["costs"]["T3"])  # planning_costs = 단가 + 메시지
        comparison = _read(self.run_dir, "strategy_comparison")
        self.assertEqual("S1", comparison["baseline"])
        for strategy in rs.STRATEGIES:
            entry = comparison["strategies"][strategy]
            self.assertEqual(len(self.fake.plans[strategy]), entry["n_assigned"])
            self.assertIn("summary", entry)
            self.assertEqual("ok", entry["sim_metrics"]["events_total"]["status"])
        self.assertEqual(0, comparison["strategies"]["S1"]["summary"]["incremental_revenue_krw"])

    def test_s1_runs_unbounded_and_its_cost_is_the_ai_budget(self) -> None:
        plans = {c[1]["strategy"]: c[1] for c in self.fake.calls if c[0] == "plan"}
        self.assertIsNone(plans["S1"]["budget"])
        for key in ("days_since_last_purchase", "lifetime_order_count", "eligible"):
            self.assertIn(key, plans["S1"]["keys"])
        comparison = _read(self.run_dir, "strategy_comparison")
        s1 = comparison["strategies"]["S1"]
        self.assertGreater(s1["n_targeted"], 0, "가짜 주문으로 S1 대상이 생겨야 한다")
        self.assertEqual(s1["n_targeted"] * 7030, s1["planned_cost_krw"])
        budget = comparison["budget"]
        self.assertIn("S1 계획 비용", budget["source"])  # sim-0.3 은 marketing_cost 를 만들지 않는다
        self.assertEqual(s1["planned_cost_krw"], budget["planning_budget_krw"])
        for strategy in ("S2", "S3", "S4", "S5"):
            self.assertEqual(budget["planning_budget_krw"], plans[strategy]["budget"], strategy)
        self.assertEqual({"lifetime_order_count": "applied", "eligible": "applied"},
                         s1["s1_eligibility"]["conditions"])

    def test_roi_metrics_use_contract_keys_without_filling(self) -> None:
        s0 = _read(self.run_dir, "strategy_comparison")["strategies"]["S0"]["metrics"]
        for key in ("id", "n_targeted", "treatment_mix", "revenue", "marketing_cost",
                    "contribution_profit", "churn_rate"):
            self.assertIn(key, s0)
        self.assertIsNone(s0["marketing_cost"])  # 측정 계층이 만들지 않으면 None — 계획 비용으로 대신하지 않는다
        self.assertEqual("events", s0["metric_sources"]["churn_rate"])

    def test_realism_report_is_copied_next_to_results(self) -> None:
        meta = _read(self.run_dir, "run_meta")
        self.assertEqual("ok", meta["realism_report"]["status"])
        latest = self.base / "results" / "sprint-v0" / "latest"
        self.assertEqual({"note": "test"}, json.loads((latest / "realism_report.json").read_text(encoding="utf-8")))

    def test_branch_roots_are_separate_and_s0_untreated(self) -> None:
        roots = _read(self.run_dir, "run_meta")["raw_roots"]
        self.assertEqual(len(set(roots.values())), len(roots))
        for strategy in rs.STRATEGIES:
            self.assertTrue((Path(roots[strategy]) / "events").is_dir(), strategy)
        self.assertEqual(0, _read(self.run_dir, "strategy_comparison")["strategies"]["S0"]["n_targeted"])

    def test_primary_event_path_is_decision_loader(self) -> None:
        meta = _read(self.run_dir, "run_meta")
        self.assertEqual("src.decision.data.load_events", meta["event_source"])
        self.assertTrue(meta["simulator_version"])  # 이벤트 메타에서 관측한 값 — 비어 있지 않다
        self.assertEqual([SMALL["seed"]], meta["random_seed_observed"])


@unittest.skipUnless(_DEPS, _SKIP_REASON)
class TestSprintWithoutDecision(unittest.TestCase):
    """의사결정 모듈이 하나도 없으면 시뮬레이터 단계만 돌고 나머지는 사유와 함께 not_run 이다."""

    def test_missing_modules_are_not_run_not_zero(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            blocked = {name: None for name in DECISION_MODULES}
            argv = ["--seed", "3", "--customers", "120", "--profile", "smoke", "--warmup-days", "30",
                    "--active-days", "20", "--out", str(base / "out"), "--results-root", str(base / "res"),
                    "--run-id", "SP-test-none"]
            argv += ["--realism-report", str(base / "없는-realism.json")]
            with mock.patch.dict(sys.modules, blocked), _quiet():
                code = rs.main(argv)
            self.assertEqual(0, code)
            run_dir = base / "res" / "sprint-v0" / "SP-test-none"
            meta = _read(run_dir, "run_meta")
            status = {s["name"]: s for s in meta["stages"]}
            for name in ("simulate_warmup", "read_events_t1", "rct_assign", "simulate_rct",
                         "read_events_t2", "snapshot_t2", "strategy_S0"):
                self.assertEqual("ok", status[name]["status"], name)
            for name in ("features_t1", "churn", "uplift", "clv", "ab_test", "strategy_S1", "roi_summary"):
                self.assertEqual("not_run", status[name]["status"], name)
                self.assertTrue(status[name]["reason"], name)
            self.assertEqual("src.simulator.api.events", meta["event_source"])
            s0 = _read(run_dir, "strategy_comparison")["strategies"]["S0"]
            self.assertEqual("not_run", s0["event_outcomes"]["status"])
            self.assertNotIn("event_revenue_krw", s0["metrics"])
            # 시뮬레이터가 아직 만들지 않는 지표는 0 이 아니라 null 이다
            self.assertIsNone(s0["metrics"]["revenue"])
            # purchase 를 만들지 않는 판 — S1 입력을 계산하지 않고 사유를 남긴다
            self.assertFalse(meta["purchase_generated"]["value"])
            self.assertIn("events.purchase", meta["purchase_generated"]["detail"])
            self.assertEqual("not_run", meta["realism_report"]["status"])
            self.assertFalse((run_dir / "realism_report.json").exists())
            self.assertIn("설계 추정", _read(run_dir, "strategy_comparison")["budget"]["source"])


@unittest.skipUnless(_DEPS, _SKIP_REASON)
class TestSprintSimulatorFailure(unittest.TestCase):
    def test_init_failure_is_recorded_and_results_still_written(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            config = rs.SprintConfig(seed=1, num_customers=10, profile="smoke", out=base / "out",
                                     results_root=base / "res", run_id="SP-test-fail")
            with mock.patch.object(rs.sim, "init", side_effect=sim.SimulatorError("boom")), \
                    mock.patch.dict(sys.modules, {name: None for name in DECISION_MODULES}), _quiet():
                run_dir = rs.run(config)
            status = {s["name"]: s for s in _read(run_dir, "run_meta")["stages"]}
            self.assertEqual("failed", status["simulate_warmup"]["status"])
            self.assertIn("boom", status["simulate_warmup"]["reason"])
            self.assertEqual("not_run", status["simulate_rct"]["status"])
            self.assertEqual("not_run", status["strategy_S0"]["status"])
            for name in rs.RESULT_FILES:
                self.assertTrue((run_dir / f"{name}.json").is_file(), name)


@unittest.skipUnless(_DEPS, _SKIP_REASON)
class TestHelpers(unittest.TestCase):
    def test_rct_assign_is_deterministic_and_order_free(self) -> None:
        ids = [f"C{i:08d}" for i in range(1, 801)]
        first = rs.rct_assign(ids, 42)
        self.assertEqual(first, rs.rct_assign(list(reversed(ids)), 42))
        self.assertNotEqual(first, rs.rct_assign(ids, 43))
        counts = {arm: list(first.values()).count(arm) for arm in rs.RCT_ARMS}
        self.assertEqual({"T0": 400, "T1": 100, "T2": 100, "T3": 100, "T4": 100}, counts)

    def test_budget_priority(self) -> None:
        basis = rs.CostBasis({"T0": 0, "T3": 7000}, 30, 100_000)
        s1 = {"planned_cost_krw": 70_300.0, "metrics": {"marketing_cost": None}}
        explicit = rs.resolve_budget(500_000, s1, basis, 2000)
        self.assertEqual((500_000, 400_000), (explicit["budget_total_krw"], explicit["planning_budget_krw"]))
        actual = rs.resolve_budget(None, {**s1, "metrics": {"marketing_cost": 150_000.0}}, basis, 2000)
        self.assertEqual(50_000, actual["planning_budget_krw"])
        self.assertIn("실측", actual["source"])
        planned = rs.resolve_budget(None, s1, basis, 2000)
        self.assertEqual(70_300, planned["planning_budget_krw"])
        fallback = rs.resolve_budget(None, None, basis, 26_000)
        self.assertEqual(8_833_000 - 100_000, fallback["planning_budget_krw"])
        self.assertIn("설계 추정", fallback["source"])

    def test_s1_inputs_from_events(self) -> None:
        t2 = datetime(2025, 4, 1, tzinfo=KST)

        def ev(cid, days_before, kind, order=None):
            return {"customer_id": cid, "timestamp": t2 - timedelta(days=days_before), "event_type": kind,
                    "order_id": order, "event_id": f"{cid}-{days_before}-{kind}"}

        events = pd.DataFrame([
            ev("C1", 100, "session_start"), ev("C1", 50, "purchase", "O1"), ev("C1", 40, "purchase", "O2"),
            ev("C1", 40, "purchase", "O2"),  # 같은 주문 중복 — 1건
            ev("C2", 30, "session_start"), ev("C2", 20, "purchase", "O3"),
            ev("C3", 5, "page_view"), ev("C3", -1, "purchase", "O4"),  # index 이후 — 세지 않는다
        ])
        population = pd.Index(["C1", "C2", "C3"], name="customer_id")
        out = rs.s1_inputs(events, t2, population)
        self.assertEqual([2.0, 1.0, 0.0], out["lifetime_order_count"].tolist())
        self.assertAlmostEqual(40.0, out["days_since_last_purchase"]["C1"])
        self.assertTrue(math.isnan(out["days_since_last_purchase"]["C3"]))  # 주문 없음 — 0 이 아니다
        # C1: 첫 관측 100일 · 주문 2 · 40일 → eligible. C2: 첫 관측 30일 < 60. C3: 주문 없음.
        self.assertEqual([True, False, False], out["eligible"].tolist())

    def test_default_budget_scales_design_estimate(self) -> None:
        self.assertEqual(8_833_000, rs.default_budget_krw(26_000))
        self.assertEqual(round(8_833_000 * 20_000 / 26_000), rs.default_budget_krw(20_000))

    def test_profile_warmup_table(self) -> None:
        self.assertEqual(273, rs.PROFILE_WARMUP_DAYS["reference"])
        self.assertEqual(180, rs.PROFILE_WARMUP_DAYS["small"])

    def test_jsonable_turns_nan_into_null_not_zero(self) -> None:
        import numpy as np

        payload = rs.to_jsonable({"a": float("nan"), "b": np.float64("inf"), "c": np.int64(3),
                                  "d": pd.Series([1.0, math.nan], index=["x", "y"]),
                                  "e": datetime(2025, 1, 1, tzinfo=KST)})
        self.assertEqual({"a": None, "b": None, "c": 3, "d": {"x": 1.0, "y": None},
                          "e": "2025-01-01T00:00:00+09:00"}, payload)

    def test_call_by_name_refuses_to_guess(self) -> None:
        def needs(model, X_test, mystery):
            return "called"

        with self.assertRaises(rs.NotRun) as caught:
            rs.call_by_name(needs, {"model": 1, "X_test": 2})
        self.assertIn("mystery", str(caught.exception))
        self.assertEqual("called", rs.call_by_name(needs, {"model": 1, "X_test": 2, "mystery": 3, "extra": 4}))

    def test_stream_frame_is_chunk_invariant(self) -> None:
        records = [{"customer_id": f"C{i:08d}", "timestamp": f"2025-01-01T00:00:{i % 60:02d}.000+09:00",
                    "event_type": "page_view"} for i in range(25)]
        whole = rs.frame_from_stream(iter(records))
        with mock.patch.object(rs, "STREAM_CHUNK", 7):
            chunked = rs.frame_from_stream(iter(records))
        pd.testing.assert_frame_equal(whole, chunked)
        self.assertIsNotNone(whole["timestamp"].dt.tz)
        self.assertEqual(0, len(rs.frame_from_stream(iter([]))))

    def test_every_guarded_stage_body_starts_with_skip(self) -> None:
        """`requires` 를 둔 단계 본문은 첫 줄이 `skip_if_not_run` 이어야 선행 실패 시 실행되지 않는다."""
        tree = ast.parse(Path(rs.__file__).read_text(encoding="utf-8"))
        offenders, guarded = [], 0
        for node in ast.walk(tree):
            if not isinstance(node, ast.With):
                continue
            call = node.items[0].context_expr
            if not (isinstance(call, ast.Call) and isinstance(call.func, ast.Attribute)
                    and call.func.attr == "stage" and any(k.arg == "requires" for k in call.keywords)):
                continue
            guarded += 1
            first = node.body[0]
            if not (isinstance(first, ast.Expr) and isinstance(first.value, ast.Call)
                    and getattr(first.value.func, "id", None) == "skip_if_not_run"):
                offenders.append(node.lineno)
        self.assertGreater(guarded, 10)
        self.assertEqual([], offenders)

    def test_decision_fn_reports_missing_module(self) -> None:
        with mock.patch.dict(sys.modules, {"src.decision.churn": None}):
            with self.assertRaises(rs.NotRun) as caught:
                rs.decision_fn("fit_best_churn")
        self.assertIn("src.decision.churn", str(caught.exception))


if __name__ == "__main__":
    unittest.main()
