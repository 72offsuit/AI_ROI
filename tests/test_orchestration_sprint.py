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
import shutil
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
    "src.decision.optimize",
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
                evaluate_temporal_holdout=self.evaluate_temporal_holdout, N_SPLITS=5,
            ),
            "src.decision.clv": module(
                "src.decision.clv", fit_clv=self.fit_clv, predict_clv=self.predict_clv,
                evaluate_clv=self.evaluate_clv,
            ),
            "src.decision.uplift": module(
                "src.decision.uplift", fit_uplift=self.fit_uplift, predict_cate=self.predict_cate,
                evaluate_uplift_models=self.evaluate_uplift_models,
            ),
            "src.decision.segments": module("src.decision.segments", assign_segments=self.assign_segments,
                                            segment_stats=self.segment_stats),
            "src.decision.optimize": module("src.decision.optimize", what_if=self.what_if,
                                            what_if_budgets=self.what_if_budgets),
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
        folds = getattr(sys.modules.get("src.decision.churn"), "N_SPLITS", None)
        self.calls.append(("evaluate_churn_models", {"n": len(y), "seed": seed, "folds": folds}))
        return {"label_def": "fake", "n": int(len(y)), "pos_rate": float(y.mean()),
                "models": [{"name": "fake", "kind": "proposed", "cv": {"roc_auc": {"mean": None, "std": None}}}],
                "best_proposed": "fake"}

    def fit_best_churn(self, X, y, seed, *, eval_result=None):
        self.calls.append(("fit_best_churn", {"eval_result": eval_result is not None}))
        return {"kind": "fake-churn"}

    def predict_churn_proba(self, model, X):
        return (1.0 / (1.0 + X["n_events"])).rename("churn_p")

    def evaluate_temporal_holdout(self, model_factory, X_train, y_train, X_test, y_test, *, seed=0):
        self.calls.append(("evaluate_temporal_holdout", {"factory": model_factory, "n": len(y_test)}))
        return {"name": model_factory, "scheme": "temporal_holdout", "n_test": int(len(y_test)), "roc_auc": 0.5}

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
    def segment_stats(self, segments, churn_p, cate, clv=None):
        return [{"segment": seg, "prd_id": None, "customer_count": int((segments == seg).sum()),
                 "ratio": float((segments == seg).mean()), "average_clv": None,
                 "average_churn_probability": float(churn_p[segments == seg].mean()), "average_uplift": None}
                for seg in sorted(segments.unique())]

    def what_if_budgets(self, base_budget_krw, ratios=(0.5, 1.0, 2.0)):
        return [base_budget_krw * r for r in ratios]

    def what_if(self, budgets, expected_gain, cost, expected_conversion=None, expected_revenue=None,
                objective="net"):
        self.calls.append(("what_if", {"budgets": list(budgets), "columns": list(expected_gain.columns)}))
        return [{"budget_krw": b, "target_count": 0} for b in budgets]

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
        return {"id": metrics["id"], "name": metrics.get("name"), "n_targeted": metrics["n_targeted"],
                "revenue": metrics["revenue_krw"], "marketing_cost": None, "contribution_profit": None,
                "churn_rate": metrics["churn_rate"], "roi": None,
                "incremental_profit_vs_S1": None,
                "incremental_revenue_krw": metrics["revenue_krw"] - baseline_metrics["revenue_krw"]}

    def analyze_ab(self, df, arm_col, outcome_col, control="T0", expected_ratio=None):
        self.calls.append(("analyze_ab", {"outcome": outcome_col, "control": control,
                                          "expected_ratio": expected_ratio}))
        arms = {a: int((df[arm_col] == a).sum()) for a in sorted(df[arm_col].unique())}
        return {"outcome": outcome_col, "arms": arms, "control": control, "alpha": 0.05, "power_target": 0.8,
                "mde": None, "srm": {"chi2": 0.1, "p_value": 0.9, "srm_detected": False},
                "comparisons": {a: {"rate_control": 0.5, "rate_treatment": 0.5, "diff": 0.0, "ci95": [-0.1, 0.1],
                                    "p_value": 1.0, "p_value_holm": 1.0, "achieved_power": 0.05}
                                for a in arms if a != control}}


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
            entry = comparison["strategy_details"][strategy]
            self.assertEqual(len(self.fake.plans[strategy]), entry["n_assigned"])
            self.assertIn("summary", entry)
            self.assertEqual("ok", entry["sim_metrics"]["events_total"]["status"])
        self.assertEqual(0, comparison["strategy_details"]["S1"]["summary"]["incremental_revenue_krw"])
        # 대시보드 StrategyComparison — S0~S5 순서의 행 목록, 숫자 예산, 창 끝
        self.assertEqual(list(rs.STRATEGIES), [row["id"] for row in comparison["strategies"]])
        self.assertTrue(all(row["status"] == "ok" for row in comparison["strategies"]))
        self.assertIsInstance(comparison["budget_krw"], float)
        self.assertIsNotNone(comparison["window"]["end"])

    def test_s1_runs_unbounded_and_its_cost_is_the_ai_budget(self) -> None:
        plans = {c[1]["strategy"]: c[1] for c in self.fake.calls if c[0] == "plan"}
        self.assertIsNone(plans["S1"]["budget"])
        for key in ("days_since_last_purchase", "lifetime_order_count", "eligible"):
            self.assertIn(key, plans["S1"]["keys"])
        comparison = _read(self.run_dir, "strategy_comparison")
        s1 = comparison["strategy_details"]["S1"]
        self.assertGreater(s1["n_targeted"], 0, "가짜 주문으로 S1 대상이 생겨야 한다")
        self.assertEqual(s1["n_targeted"] * 7030, s1["planned_cost_krw"])
        budget = comparison["budget"]
        self.assertIn("C_rule", budget["source"])
        self.assertEqual(s1["planned_cost_krw"], budget["planning_budget_krw"])
        for strategy in ("S2", "S3", "S4", "S5"):
            self.assertEqual(budget["planning_budget_krw"], plans[strategy]["budget"], strategy)
        self.assertEqual({"lifetime_order_count": "applied", "eligible": "applied"},
                         s1["s1_eligibility"]["conditions"])

    def test_roi_metrics_use_candidate_keys_without_filling(self) -> None:
        s0 = _read(self.run_dir, "strategy_comparison")["strategy_details"]["S0"]["metrics"]
        for key in ("id", "n_targeted", "treatment_mix", "sim_revenue", "sim_marketing_cost",
                    "sim_contribution_profit", "sim_churn_rate", "revenue_krw", "churn_rate",
                    "planned_treatment_cost_krw", "measured_revenue", "measured_marketing_cost",
                    "measured_contribution_profit"):
            self.assertIn(key, s0)
        self.assertIsNone(s0["sim_marketing_cost"])  # 측정 계층이 만들지 않으면 None — 0 이 아니다

    # #169 — 실측 기여이익 ------------------------------------------------------
    def _economics(self, strategy: str) -> dict:
        return _read(self.run_dir, "strategy_comparison")["strategy_details"][strategy]["measured_economics"]

    def test_every_branch_has_its_own_bundle_and_measured_profit(self) -> None:
        details = _read(self.run_dir, "strategy_comparison")["strategy_details"]
        for strategy in rs.STRATEGIES:
            record = details[strategy]["measured_economics"]
            self.assertEqual("ok", record["status"], strategy)
            self.assertEqual((self.base / "out" / "branches" / strategy / "simulator_exchange").resolve(),
                             Path(record["bundle_root"]).resolve(), strategy)
            self.assertEqual("ok", record["bundle"]["status"], strategy)
            self.assertEqual(0, record["n_commerce_events_excluded"], strategy)
            for name in ("revenue", "cogs", "marketing_cost", "contribution_profit"):
                self.assertEqual("ok", record["metrics"][name]["status"], f"{strategy}.{name}")
            metrics = details[strategy]["metrics"]
            self.assertEqual(record["metrics"]["contribution_profit"]["value"], metrics["measured_contribution_profit"])
            self.assertEqual(record["metrics"]["revenue"]["value"], metrics["measured_revenue"])
            self.assertEqual(record["metrics"]["marketing_cost"]["value"], metrics["measured_marketing_cost"])
            # COGS 를 뺐다 — 기여이익 < 매출
            self.assertLess(metrics["measured_contribution_profit"], metrics["measured_revenue"], strategy)

    def test_profit_is_not_a_constant_multiple_of_revenue(self) -> None:
        """EC-1 — COGS 가 원가율 곱이면 분기마다 기여이익률이 같아진다."""
        details = _read(self.run_dir, "strategy_comparison")["strategy_details"]
        ratios = {round(d["metrics"]["measured_contribution_profit"] / d["metrics"]["measured_revenue"], 12)
                  for d in details.values()}
        self.assertGreater(len(ratios), 1)

    def test_event_filter_matches_full_events(self) -> None:
        """경제 지표 조립이 읽지 않는 이벤트만 거른다 — 전량으로 낸 값과 같아야 한다."""
        index_date = datetime(2025, 5, 1).date()
        for strategy in rs.STRATEGIES:
            record = self._economics(strategy)
            raw, bundle = Path(record["raw_root"]), Path(record["bundle_root"])
            full = list(sink.read_events(raw))
            filtered = rs.measured_economics(raw, bundle, index_date)
            everything = rs.measured_economics(raw, bundle, index_date, events=full)
            self.assertEqual(everything["metrics"], filtered["metrics"], strategy)
            self.assertLess(filtered["n_events_read"], len(full), strategy)

    def test_real_roi_uses_measured_profit_without_fallback(self) -> None:
        """정상 실행(묶음 있음)에서는 대체 계산이 발동하지 않는다."""
        from src.decision import roi

        details = _read(self.run_dir, "strategy_comparison")["strategy_details"]
        base = details["S1"]["metrics"]
        for strategy in rs.STRATEGIES:
            row = roi.summarize_strategy(details[strategy]["metrics"], base)
            self.assertEqual("ok", row["incremental_profit_status"], strategy)
            self.assertEqual("measured_contribution_profit", row["incremental_profit_basis"], strategy)
            self.assertIsInstance(row["incremental_profit_vs_S1"], float, strategy)
            self.assertIsNone(row["directional_revenue_minus_marketing_vs_S1"], strategy)
            for flag in ("PROFIT_FALLBACK_REVENUE_BASED", "CONTRIBUTION_PROFIT_MISSING",
                         "MARKETING_COST_PLANNED_NOT_REALIZED", "REVENUE_UP_PROFIT_DOWN_NOT_RUN"):
                self.assertNotIn(flag, row["flags"], strategy)
            self.assertEqual("ok", row["guardrails"]["revenue_up_profit_down"]["status"], strategy)

    def test_missing_bundle_makes_profit_not_computable(self) -> None:
        """묶음이 없으면 측정 계층이 NO_COST_BASIS 를 내고, 증분이익은 계산 불가로 나간다."""
        from src.decision import roi

        record = self._economics("S2")
        missing = rs.measured_economics(Path(record["raw_root"]), self.base / "없는-묶음", datetime(2025, 5, 1).date())
        self.assertEqual("not_run", missing["bundle"]["status"])
        self.assertEqual("ok", missing["metrics"]["revenue"]["status"])
        self.assertEqual("unavailable", missing["metrics"]["contribution_profit"]["status"])
        self.assertEqual("NO_COST_BASIS", missing["metrics"]["contribution_profit"]["reason_code"])
        details = _read(self.run_dir, "strategy_comparison")["strategy_details"]
        ai = dict(details["S2"]["metrics"])
        for key in rs.MEASURED_KEYS:
            ai[f"measured_{key}"] = rs.measured_value({"status": "ok", **missing}, key)
        self.assertIsNone(ai["measured_contribution_profit"])
        row = roi.summarize_strategy(ai, details["S1"]["metrics"], ai_investment_cost=1_000.0)
        self.assertIsNone(row["incremental_profit_vs_S1"])
        self.assertIn("전략 쪽 contribution_profit 결손", row["incremental_profit_status"])
        self.assertIsNone(row["roi"])
        self.assertNotEqual("ok", row["roi_status"])
        self.assertNotEqual("ok", row["ai_roi_status"])
        self.assertIsNotNone(row["directional_revenue_minus_marketing_vs_S1"])  # 별도 필드에만
        self.assertIn("PROFIT_FALLBACK_REVENUE_BASED", row["flags"])
        self.assertEqual("not_run", row["guardrails"]["revenue_up_profit_down"]["status"])

    # #237 R1 — 분기 창 금액 대조(DQ-09) ---------------------------------------------
    def test_every_branch_runs_window_amount_check(self) -> None:
        """정상 실행에서 분기 창 DQ-09 가 실제로 대조하고(0행이 아니다) 통과한다."""
        for strategy in rs.STRATEGIES:
            check = self._economics(strategy)["amount_check"]
            self.assertEqual("pass", check["status"], strategy)
            self.assertGreater(check["examined_rows"], 0, strategy)
            self.assertEqual(0, check["violations"], strategy)
            self.assertEqual(check["n_window_purchase_orders"], check["examined_rows"], strategy)
            self.assertEqual(0, check["n_window_orders_missing_from_bundle"], strategy)
            self.assertEqual(rs.WINDOW_AMOUNT_CHECK_GAP, check["not_detected"], strategy)

    def test_full_bundle_against_window_events_is_a_false_violation(self) -> None:
        """대조군 — 묶음을 좁히지 않으면 창 이전 주문이 전부 "purchase 없음" 위반이 된다(실제 묶음)."""
        from src.measurement import exchange as ex
        from src.measurement import publish as mp
        from src.measurement import validate
        from src.measurement.sink import EventSource

        record = self._economics("S2")
        bundle = ex.read_exchange(Path(record["bundle_root"]), EventSource.SIMULATOR)
        events = mp.partition_by_source(rs.economic_events(Path(record["raw_root"]))).simulator
        self.assertGreater(record["amount_check"]["n_bundle_orders_outside_window"], 0)
        self.assertEqual("fail", validate.check_amount_equation([(bundle, events)]).status)
        self.assertEqual("pass", rs.window_amount_check(bundle, events)["status"])

    def _branch_with(self, bundle_root: Path, events: list[dict]) -> dict:
        """``branch_economics`` 를 실제 측정 경로로 — 묶음 위치와 읽을 이벤트만 바꾼다."""
        with mock.patch.object(rs.sim, "exchange_bundle", return_value={"status": "ok", "path": str(bundle_root)}), \
                mock.patch.object(rs, "economic_events", return_value=events):
            return rs.branch_economics(Path("unused"), datetime(2025, 5, 1, tzinfo=KST))

    def _assert_blocks_official_values(self, branch: dict) -> None:
        from src.decision import roi

        self.assertEqual("quality_failed", branch["status"])
        self.assertIn("DQ-09", branch["reason"])
        self.assertEqual("fail", branch["amount_check"]["status"])
        self.assertTrue(branch["amount_check"]["samples"])  # 근거가 산출물에 남는다
        # 측정 계층만 보면 기여이익은 ok 다 — 이 경로가 #237 R1 이 막는 것이다
        self.assertEqual("ok", branch["metrics"]["contribution_profit"]["status"])
        details = _read(self.run_dir, "strategy_comparison")["strategy_details"]
        ai = dict(details["S2"]["metrics"])
        for key in rs.MEASURED_KEYS:
            ai[f"measured_{key}"] = rs.measured_value(branch, key)
            self.assertIsNone(ai[f"measured_{key}"], key)
        row = roi.summarize_strategy(ai, details["S1"]["metrics"], ai_investment_cost=1_000.0)
        self.assertIsNone(row["incremental_profit_vs_S1"])
        self.assertNotEqual("ok", row["incremental_profit_status"])
        self.assertIsNone(row["roi"])
        self.assertNotEqual("ok", row["roi_status"])
        self.assertNotEqual("ok", row["ai_roi_status"])
        self.assertNotEqual("ok", row["guardrails"]["revenue_up_profit_down"]["status"])

    def test_event_amount_conflict_blocks_official_values(self) -> None:
        """이벤트 ↔ 묶음 금액 충돌 — 그 분기의 정식 기여이익 · 증분이익 · ROI · 가드레일이 계산 불가다."""
        record = self._economics("S2")
        events = [dict(e) for e in rs.economic_events(Path(record["raw_root"]))]
        purchase = next(e for e in events if e.get("event_type") == "purchase")
        purchase["order_amount"] = int(purchase["order_amount"]) + 200_000
        branch = self._branch_with(Path(record["bundle_root"]), events)
        self._assert_blocks_official_values(branch)
        self.assertEqual(1, branch["amount_check"]["violations"])
        self.assertIn(f"{purchase['order_id']}: 이벤트", branch["amount_check"]["samples"][0])

    def test_bundle_internal_conflict_blocks_official_values(self) -> None:
        """묶음 내부 등식 충돌(품목 − 할인 ≠ 주문 금액) — 같은 차단."""
        record = self._economics("S2")
        events = [dict(e) for e in rs.economic_events(Path(record["raw_root"]))]
        order_id = next(str(e["order_id"]) for e in events if e.get("event_type") == "purchase")
        with tempfile.TemporaryDirectory() as tmp:
            bundle_root = Path(tmp) / "simulator_exchange"
            shutil.copytree(record["bundle_root"], bundle_root)
            orders = bundle_root / "orders.jsonl"
            rows = [json.loads(line) for line in orders.read_text(encoding="utf-8").splitlines() if line.strip()]
            for row in rows:
                if row["order_id"] == order_id:
                    row["order_amount"] -= 10_000
            orders.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows), encoding="utf-8")
            branch = self._branch_with(bundle_root, events)
        self._assert_blocks_official_values(branch)
        self.assertEqual(1, branch["amount_check"]["violations"])
        self.assertIn(f"{order_id}: 교환 파일", branch["amount_check"]["samples"][0])

    def test_quality_failure_blocks_only_its_branch_and_s1_blocks_every_increment(self) -> None:
        """한 전략만 실패하면 그 행만, 기준선 S1 이 실패하면 S2~S5 증분이익이 모두 계산 불가다."""
        from src.decision import roi

        details = _read(self.run_dir, "strategy_comparison")["strategy_details"]

        def failed(strategy: str) -> dict:
            record = {**details[strategy]["measured_economics"], "status": "quality_failed"}
            return {**details[strategy]["metrics"],
                    **{f"measured_{key}": rs.measured_value(record, key) for key in rs.MEASURED_KEYS}}

        base = details["S1"]["metrics"]
        self.assertIsNone(roi.summarize_strategy(failed("S2"), base)["incremental_profit_vs_S1"])
        for strategy in ("S3", "S4", "S5"):
            row = roi.summarize_strategy(details[strategy]["metrics"], base)
            self.assertEqual("ok", row["incremental_profit_status"], strategy)
        for strategy in ("S2", "S3", "S4", "S5"):
            row = roi.summarize_strategy(details[strategy]["metrics"], failed("S1"))
            self.assertIsNone(row["incremental_profit_vs_S1"], strategy)
            self.assertIn("기준선 쪽 contribution_profit 결손", row["incremental_profit_status"], strategy)

    def test_dashboard_shapes(self) -> None:
        churn = _read(self.run_dir, "churn_eval")
        self.assertIsInstance(churn["models"], list)  # 평가 결과가 최상위에 펼쳐진다
        self.assertEqual({"roc_auc": 0.5}, churn["models"][0]["temporal_holdout"])
        self.assertEqual("fake", [c[1]["factory"] for c in self.fake.calls if c[0] == "evaluate_temporal_holdout"][0])
        ab = _read(self.run_dir, "ab_test")
        self.assertEqual({"chi2", "p", "ok"}, set(ab["srm"]))
        self.assertEqual(["T0", "T1", "T2", "T3", "T4"], [a["arm"] for a in ab["arms"]])
        ratio = [c[1]["expected_ratio"] for c in self.fake.calls if c[0] == "analyze_ab"][0]
        self.assertEqual(0.5, ratio["T0"])  # 설계 비율로 SRM 을 검사한다
        segments = _read(self.run_dir, "segments")["segments"]
        self.assertTrue(all({"id", "name", "n", "share", "avg_churn_p"} <= set(row) for row in segments))
        meta = _read(self.run_dir, "run_meta")
        self.assertEqual(SMALL["num_customers"], meta["N"])
        self.assertIsInstance(meta["simulator_version"], str)
        self.assertEqual("ok", meta["margin_rate"]["status"])
        self.assertEqual(3, len(_read(self.run_dir, "strategy_comparison")["what_if"]["rows"]))

    def test_rct_and_strategy_assignment_files(self) -> None:
        meta = _read(self.run_dir, "run_meta")
        rct_path = Path(meta["assignment_files"]["rct"])
        self.assertEqual(self.base / "out" / "assignments", rct_path.parent)
        self.assertRegex(rct_path.name, r"^T0-\d{8}\.json$")
        rct = json.loads(rct_path.read_text(encoding="utf-8"))
        self.assertEqual(meta["timeline"]["t1"], rct["assigned_at"])
        self.assertTrue(rct["assigned_at"].endswith("+09:00"))
        self.assertEqual(meta["rct"]["n_eligible"], len(rct["assignments"]))  # 통제군 포함 전원
        self.assertEqual(set(rs.RCT_ARMS), set(rct["assignments"].values()))
        for strategy in rs.STRATEGIES:
            path = Path(meta["assignment_files"]["strategies"][strategy])
            self.assertEqual(self.base / "out" / "assignments" / "strategies", path.parent)
            payload = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(self.fake.plans[strategy], payload["assignments"])
            self.assertEqual(meta["timeline"]["t2"], payload["assigned_at"])
        self.assertIsNone(meta["churn_options"]["cv_folds"])
        churn = _read(self.run_dir, "churn_eval")
        self.assertFalse(churn["training_sample"]["applied"])  # 옵션이 없으면 동작이 그대로다
        self.assertEqual(5, [c[1]["folds"] for c in self.fake.calls if c[0] == "evaluate_churn_models"][0])

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
        self.assertEqual(0, _read(self.run_dir, "strategy_comparison")["strategy_details"]["S0"]["n_targeted"])

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
            s0 = _read(run_dir, "strategy_comparison")["strategy_details"]["S0"]
            self.assertEqual("not_run", s0["event_outcomes"]["status"])
            self.assertNotIn("revenue_krw", s0["metrics"])
            # 시뮬레이터가 아직 만들지 않는 지표는 0 이 아니라 null 이다
            self.assertIsNone(s0["metrics"]["sim_revenue"])
            # 측정 계층 호출은 의사결정 모듈과 무관하게 돈다 (#169)
            self.assertEqual("ok", s0["measured_economics"]["status"])
            self.assertIn("status", s0["measured_economics"]["metrics"]["contribution_profit"])
            # purchase 생성 여부는 시뮬레이터 판에 따라 다르다(sim-0.3 은 만들지 않고 sim-0.4 부터 만든다).
            # 판에 기대지 않고, 값이 bool 이며 판단 근거(events.purchase 상태)를 남기는지만 본다
            self.assertIsInstance(meta["purchase_generated"]["value"], bool)
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
class TestWindowAmountCheck(unittest.TestCase):
    """#237 R1 — 분기 창 DQ-09 의 합성 반례. 실제 묶음 경로는 ``TestSprintWithFakeDecision`` 이 본다."""

    @staticmethod
    def _bundle(**orders: tuple[int, int, int]) -> object:
        """``order_id=(품목 단가, 할인, 주문 금액)`` — 품목 1줄 · 수량 1."""
        from src.measurement import economics as ec
        from src.measurement import exchange as ex
        from src.measurement.sink import EventSource

        return ex.ExchangeBundle(
            source=EventSource.SIMULATOR, root=Path("unused"), manifest={},
            generated_at=datetime(2025, 5, 1, tzinfo=KST), signup_dates={}, product_ids=frozenset({"p1"}),
            orders={order_id: ex.ExchangeOrder(
                order_id=order_id, customer_id="c1", order_amount=amount, discount=discount,
                shipping_fee=0, shipping_charged=0,
                items=(ec.OrderItem(product_id="p1", quantity=1, unit_price=price, unit_cost=price // 2),),
            ) for order_id, (price, discount, amount) in orders.items()},
        )

    @staticmethod
    def _purchase(order_id: str, amount: int, *, simulator: bool = True) -> dict:
        event = {"event_type": "purchase", "order_id": order_id, "order_amount": amount}
        if simulator:
            event.update(simulator_version="test", random_seed=1)
        return event

    def test_normal_orders_with_discount_pass(self) -> None:
        bundle = self._bundle(o1=(100_000, 0, 100_000), o2=(100_000, 10_000, 90_000))
        check = rs.window_amount_check(bundle, [self._purchase("o1", 100_000), self._purchase("o2", 90_000)])
        self.assertEqual("pass", check["status"])
        self.assertEqual(2, check["examined_rows"])
        self.assertEqual(0, check["violations"])

    def test_orders_before_the_window_are_left_out(self) -> None:
        from src.measurement import validate

        bundle = self._bundle(old=(50_000, 0, 50_000), o1=(100_000, 0, 100_000))
        events = [self._purchase("o1", 100_000)]
        check = rs.window_amount_check(bundle, events)
        self.assertEqual("pass", check["status"])
        self.assertEqual(1, check["examined_rows"])
        self.assertEqual(1, check["n_bundle_orders_outside_window"])
        self.assertEqual("fail", validate.check_amount_equation([(bundle, events)]).status)  # 대조군

    def test_event_and_bundle_conflict_fails(self) -> None:
        check = rs.window_amount_check(self._bundle(o1=(100_000, 0, 100_000)), [self._purchase("o1", 300_000)])
        self.assertEqual("fail", check["status"])
        self.assertEqual(1, check["violations"])
        self.assertIn("o1: 이벤트 300000 ≠ 교환 파일 100000", check["samples"][0])

    def test_bundle_internal_conflict_fails(self) -> None:
        check = rs.window_amount_check(self._bundle(o1=(100_000, 0, 90_000)), [self._purchase("o1", 90_000)])
        self.assertEqual("fail", check["status"])
        self.assertIn("o1: 교환 파일 90000 ≠ 품목 100000 − 할인 0", check["samples"][0])

    def test_commerce_event_with_the_same_order_id_is_not_compared(self) -> None:
        """출처 분리가 필수다 — 같은 주문 ID 의 커머스 이벤트를 넘기면 거짓 위반이 난다."""
        from src.measurement import publish as mp

        bundle = self._bundle(o1=(100_000, 0, 100_000))
        events = [self._purchase("o1", 100_000), self._purchase("o1", 300_000, simulator=False)]
        split = mp.partition_by_source(events)
        self.assertEqual("pass", rs.window_amount_check(bundle, split.simulator)["status"])
        self.assertEqual("fail", rs.window_amount_check(bundle, split.commerce)["status"])  # 대조군

    def test_nothing_to_compare_is_not_run_not_pass(self) -> None:
        bundle = self._bundle(o1=(100_000, 0, 100_000))
        empty = rs.window_amount_check(bundle, [])
        self.assertEqual("not_run", empty["status"])
        self.assertIsNone(empty["violations"])
        self.assertIn("purchase 가 없다", empty["reason_detail"])
        missing = rs.window_amount_check(bundle, [self._purchase("o9", 100_000)])
        self.assertEqual("not_run", missing["status"])
        self.assertEqual(1, missing["n_window_orders_missing_from_bundle"])
        self.assertIn("NO_COST_BASIS", missing["reason_detail"])

    def test_branch_economics_propagates_fail_but_keeps_evidence(self) -> None:
        end = datetime(2025, 5, 1, tzinfo=KST)
        ok_metrics = {key: {"status": "ok", "value": 1.0} for key in rs.MEASURED_KEYS}
        for status, expected in (("fail", "quality_failed"), ("pass", "ok"), ("not_run", "ok")):
            economics = {"amount_check": {"status": status, "reason_detail": "1행 중 1행이 위반했다"},
                         "metrics": ok_metrics}
            with mock.patch.object(rs.sim, "exchange_bundle", return_value={"status": "ok", "path": "x"}), \
                    mock.patch.object(rs, "measured_economics", return_value=economics):
                record = rs.branch_economics(Path("unused"), end)
            self.assertEqual(expected, record["status"], status)
            self.assertEqual(ok_metrics, record["metrics"], status)  # 값은 근거로 남는다
            for key in rs.MEASURED_KEYS:
                self.assertEqual(None if status == "fail" else 1.0, rs.measured_value(record, key), status)


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
        s1 = {"planned_cost_krw": 70_300.0, "metrics": {"sim_marketing_cost": 150_000.0}}
        explicit = rs.resolve_budget(500_000, s1, basis, 2000)
        self.assertEqual(500_000, explicit["planning_budget_krw"])  # --budget-krw 는 plan 예산 그대로
        planned = rs.resolve_budget(None, s1, basis, 2000)
        self.assertEqual(70_300, planned["planning_budget_krw"])  # C_rule = S1 계획 비용 합
        self.assertEqual(150_000, planned["s1_realized_marketing_cost_krw"])  # 실측은 참고로만
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

    def test_override_attr_restores_and_reports(self) -> None:
        module = types.ModuleType("fake_mod")
        module.N_SPLITS = 5
        with mock.patch.dict(sys.modules, {"fake_mod": module}):
            with rs.override_attr("fake_mod", "N_SPLITS", 3) as record:
                self.assertEqual(3, module.N_SPLITS)
            self.assertEqual(5, module.N_SPLITS)
            self.assertEqual({"applied": True, "default": 5, "requested": 3}, {k: record[k] for k in ("applied", "default", "requested")})
            with rs.override_attr("fake_mod", "N_SPLITS", None) as record:
                self.assertFalse(record["applied"])
            with rs.override_attr("fake_mod", "MISSING", 3) as record:
                self.assertFalse(record["applied"])
                self.assertFalse(hasattr(module, "MISSING"))

    def test_stratified_cap_keeps_class_ratio(self) -> None:
        y = pd.Series([1] * 200 + [0] * 800, index=[f"C{i:08d}" for i in range(1000)])
        X = pd.DataFrame({"a": range(1000)}, index=y.index)
        Xs, ys, record = rs.stratified_cap(X, y, 100, seed=1)
        self.assertTrue(record["applied"])
        self.assertEqual(100, len(ys))
        self.assertAlmostEqual(0.2, ys.mean(), places=2)
        self.assertEqual(list(ys.index), list(Xs.index))
        self.assertEqual(list(ys.index), list(rs.stratified_cap(X, y, 100, seed=1)[1].index))
        same = rs.stratified_cap(X, y, None, seed=1)
        self.assertIs(X, same[0])
        self.assertFalse(same[2]["applied"])

    def test_branch_economics_failure_is_recorded_not_zero(self) -> None:
        """묶음을 못 받으면 분기는 계속하고 기여이익은 None 이다 (#169)."""
        end = datetime(2025, 5, 1, tzinfo=KST)
        with mock.patch.object(rs.sim, "exchange_bundle", side_effect=sim.SimulatorError("no orders")), _quiet():
            record = rs.branch_economics(Path("unused"), end)
        self.assertEqual("failed", record["status"])
        self.assertIn("no orders", record["reason"])
        for key in rs.MEASURED_KEYS:
            self.assertIsNone(rs.measured_value(record, key))
        with mock.patch.object(rs.sim, "exchange_bundle", return_value={"status": "empty"}):
            self.assertEqual("not_run", rs.branch_economics(Path("unused"), end)["status"])
        self.assertIsNone(rs.measured_value({"status": "ok", "metrics": {
            "contribution_profit": {"status": "unavailable", "value": None}}}, "contribution_profit"))
        self.assertEqual(0, rs.measured_value({"status": "ok", "metrics": {
            "contribution_profit": {"status": "ok", "value": 0}}}, "contribution_profit"))  # 측정된 0

    def test_branch_roots_have_separate_parents(self) -> None:
        out = Path("/x")
        parents = {rs.branch_raw_root(out, s).parent for s in rs.STRATEGIES}
        self.assertEqual(len(rs.STRATEGIES), len(parents))
        self.assertEqual("raw", rs.branch_raw_root(out, "S1").name)

    def test_decision_fn_reports_missing_module(self) -> None:
        with mock.patch.dict(sys.modules, {"src.decision.churn": None}):
            with self.assertRaises(rs.NotRun) as caught:
                rs.decision_fn("fit_best_churn")
        self.assertIn("src.decision.churn", str(caught.exception))


if __name__ == "__main__":
    unittest.main()
