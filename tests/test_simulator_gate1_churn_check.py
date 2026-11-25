"""`scripts/gate1_churn_check.py` — 구매 간격 정의(사전 등록)와 churn 임계값 근거 판정(data_spec §5.1 ①~③).

간격 · 분위수 계산은 표준 라이브러리만 쓰므로 의존성 없이 돈다. judge 는 기준 yaml 을 읽어야 하므로 PyYAML 이
없으면 skip 한다. measure 실측은 seed 42 · 고객 40명으로 공개 API 를 실제로 돌린다(약 2초).
skip 은 통과가 아니다.
"""

from __future__ import annotations

import contextlib
import copy
import io
import json
import random
import statistics
import sys
import tempfile
import unittest
from datetime import date
from fractions import Fraction
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SCRIPTS = REPO / "scripts"
REAL_CRITERIA = REPO / "config" / "simulator_gate1_acceptance.yaml"
REAL_SIMULATOR_CONFIG = REPO / "config" / "simulator_config.yaml"

NEEDS_YAML = "BLOCKED: PyYAML 미설치 — churn 임계값 근거 판정을 검증하지 않았다(통과가 아니다)"

# 스크립트는 같은 디렉터리의 gate1_judge 를 그대로 import 한다(`python scripts/x.py` 와 같은 조건을 만든다).
# 이미 읽힌 모듈은 sys.modules 에서 그대로 쓰이므로 InputError 클래스가 한 벌로 유지된다.
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))
import gate1_churn_check as cc  # noqa: E402

try:
    import yaml  # noqa: F401

    HAVE_YAML = True
except ImportError:  # pragma: no cover - 의존성 없는 CI 잡
    HAVE_YAML = False

SEEDS = [47, 48, 49, 50, 51]
CUSTOMERS = 13000
THRESHOLDS = {"at_risk_days": 28, "no_purchase_days": 42}
REALISM_WORLD = {"profile": "reference", "days": 315, "assign_day": 180, "config": None}


def base_criteria(seeds=SEEDS, customers=CUSTOMERS) -> dict:
    """`gate1_judge.load_criteria` 가 받는 최소 기준 + `churn_threshold` · `sources.realism.world` · `a_discount`.

    블록 키는 `config/simulator_gate1_acceptance.yaml` 과 같다(실제 파일과의 대조는 `TestRealCriteria`).
    """
    return {
        "version": "gate1-acceptance-test",
        "sample": {"seeds": list(seeds), "customers": customers, "guardrail_profile": "small",
                   "guardrail_warmup_days": 180, "guardrail_full_evaluation": True},
        "verdict": {"required": {"checks": [{"fact": "F12", "name": "churn_rate", "population": "active42",
                                             "band_from": "guardrails.churn_rate_bp"}]},
                    "recorded": {"facts": ["F1"]}},
        "churn_threshold": {
            "role": "churn_evidence",
            "source": {"profile": "reference", "customers_from": "sample.customers", "days": 273,
                       "command": "PYTHONPATH=. python3.12 scripts/gate1_churn_check.py measure --seed {seed} "
                                  "--customers 13000 --out {new_dir}"},
            "interval": "간격 정의(테스트)", "quantile_method": "inclusive(테스트)",
            "comparisons": [{"threshold": "at_risk_days", "quantile": 75},
                            {"threshold": "no_purchase_days", "quantile": 90}],
            "thresholds_from": "config/simulator_config.yaml churn",
            "tolerance_ratio": 0.2, "rule": "규칙(테스트)", "on_fail": "on_fail(테스트)",
        },
        "sources": {"realism": {"world": dict(REALISM_WORLD)}},
        "a_discount": {
            "role": "assumption_check", "source": "realism",
            "unit_cost_from": "config/economic_config.yaml treatment_cost.{arm}.unit_cost_krw",
            "coupon_arms": ["T2", "T3"], "min_discounted_orders_per_arm": 1,
            "rule": "규칙(테스트)", "on_fail": "on_fail(테스트)",
        },
    }


def write_yaml_json(path: Path, data: dict) -> Path:
    # JSON 은 YAML 의 부분집합이라 쓸 때 PyYAML 이 없어도 된다(읽는 쪽은 yaml.safe_load).
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return path


def interval_report(seed: int, p75: str = "28", p90: str = "42", **override) -> dict:
    report = {"schema": cc.SCHEMA, "seed": seed, "customers": CUSTOMERS, "profile": "reference", "days": 273,
              "simulator_version": "sim-test", "source_commit": "a" * 40, "n_gaps": 1000,
              "p75": float(Fraction(p75)), "p75_exact": str(Fraction(p75)),
              "p90": float(Fraction(p90)), "p90_exact": str(Fraction(p90))}
    report.update(override)
    return report


def purchase(customer, timestamp, event_type="purchase") -> dict:
    return {"event_id": f"e-{customer}-{timestamp}", "customer_id": customer, "timestamp": timestamp,
            "event_type": event_type}


class TestIntervalDefinition(unittest.TestCase):
    def test_same_day_repeat_purchase_is_a_zero_gap(self) -> None:
        events = [purchase("C1", "2025-01-01T09:00:00.000+09:00"), purchase("C1", "2025-01-01T21:00:00.000+09:00"),
                  purchase("C1", "2025-01-04T08:00:00.000+09:00")]
        by_customer = cc.purchase_dates_by_customer(events)
        self.assertEqual([date(2025, 1, 1), date(2025, 1, 1), date(2025, 1, 4)], by_customer["C1"])
        self.assertEqual([0, 3], cc.pooled_gaps(by_customer))

    def test_dates_are_kst_calendar_days_not_elapsed_hours(self) -> None:
        # 23:30 → 다음 날 00:30 은 1 시간 차이지만 KST 달력으로 하루다.
        events = [purchase("C1", "2025-01-01T23:30:00.000+09:00"), purchase("C1", "2025-01-02T00:30:00.000+09:00")]
        self.assertEqual([1], cc.pooled_gaps(cc.purchase_dates_by_customer(events)))

    def test_unsorted_events_are_sorted_per_customer_and_pooled_across_customers(self) -> None:
        events = [purchase("C1", "2025-01-10T10:00:00.000+09:00"), purchase("C2", "2025-02-01T10:00:00.000+09:00"),
                  purchase("C1", "2025-01-01T10:00:00.000+09:00"), purchase("C2", "2025-02-15T10:00:00.000+09:00"),
                  purchase("C3", "2025-03-01T10:00:00.000+09:00")]
        self.assertEqual([9, 14], sorted(cc.pooled_gaps(cc.purchase_dates_by_customer(events))))

    def test_customer_with_one_purchase_and_other_events_contribute_no_gap(self) -> None:
        events = [purchase("C1", "2025-01-01T10:00:00.000+09:00"),
                  purchase("C1", "2025-01-03T10:00:00.000+09:00", event_type="page_view"),
                  purchase("C2", "2025-01-01T10:00:00.000+09:00"), purchase("C2", "2025-01-05T10:00:00.000+09:00")]
        by_customer = cc.purchase_dates_by_customer(events)
        self.assertEqual(1, len(by_customer["C1"]))
        self.assertEqual([4], cc.pooled_gaps(by_customer))

    def test_non_kst_unparseable_or_anonymous_purchase_is_refused_not_dropped(self) -> None:
        for bad in (purchase("C1", "2025-01-01T10:00:00.000+00:00"), purchase("C1", "어제"),
                    purchase(None, "2025-01-01T10:00:00.000+09:00")):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                cc.purchase_dates_by_customer([bad])


class TestPercentiles(unittest.TestCase):
    def test_matches_statistics_quantiles_inclusive(self) -> None:
        rng = random.Random(42)
        for size in (2, 3, 7, 100, 1001):
            gaps = [rng.randrange(0, 90) for _ in range(size)]
            cuts = statistics.quantiles(gaps, n=100, method="inclusive")
            values = cc.percentiles(gaps)
            with self.subTest(size=size):
                self.assertEqual(cuts[74], float(values[75]))
                self.assertEqual(cuts[89], float(values[90]))

    def test_matches_numpy_percentile_default(self) -> None:
        try:
            import numpy
        except ImportError:
            self.skipTest("BLOCKED: numpy 미설치 — numpy.percentile 과 대조하지 않았다(통과가 아니다)")
        rng = random.Random(43)
        gaps = [rng.randrange(0, 120) for _ in range(537)]
        values = cc.percentiles(gaps)
        self.assertEqual(float(numpy.percentile(gaps, 75)), float(values[75]))
        self.assertEqual(float(numpy.percentile(gaps, 90)), float(values[90]))

    def test_value_is_exact_so_decimal_boundaries_are_not_lost_to_float(self) -> None:
        # m=4 → P90 은 data[3] 과 data[4] 사이 0.6 지점: 33·0.4 + 34·0.6 = 33.6 = 42 × 0.8(하한 경계값 그대로).
        value = cc.percentiles([0, 0, 0, 33, 34])[90]
        self.assertEqual(Fraction(168, 5), value)
        self.assertNotEqual(Fraction(168, 5), Fraction(float(value)))   # float 로 두면 경계가 어긋난다

    def test_fewer_than_two_gaps_is_an_input_error(self) -> None:
        with self.assertRaises(cc.InputError):
            cc.percentiles([3])


@unittest.skipUnless(HAVE_YAML, NEEDS_YAML)
class JudgeCase(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.tmp = Path(self._tmp.name)
        self.criteria = base_criteria()
        self.thresholds = dict(THRESHOLDS)
        self.reports = {seed: interval_report(seed) for seed in SEEDS}

    def set_values(self, quantile: int, values: list[str]) -> None:
        for seed, value in zip(SEEDS, values):
            self.reports[seed][f"p{quantile}"] = float(Fraction(value))
            self.reports[seed][f"p{quantile}_exact"] = str(Fraction(value))

    def run_judge(self, intervals: list[str] | None = None) -> tuple[int, dict | None, str, str]:
        criteria = write_yaml_json(self.tmp / "criteria.yaml", self.criteria)
        config = write_yaml_json(self.tmp / "simulator_config.yaml",
                                 {"churn": {**self.thresholds, "no_login_days": 60}})
        if intervals is None:
            intervals = []
            for index, (seed, report) in enumerate(sorted(self.reports.items(), reverse=True)):
                # 디렉터리 이름과 seed 를 어긋나게 둔다 — 짝짓기는 파일 안의 seed 로 한다.
                directory = self.tmp / f"world{index}"
                directory.mkdir(exist_ok=True)
                (directory / cc.INTERVALS_FILE).write_text(json.dumps(report), encoding="utf-8")
                intervals.append(str(directory))
        out_json, out_md = self.tmp / "out" / "churn.json", self.tmp / "out" / "churn.md"
        argv = ["judge", "--criteria", str(criteria), "--simulator-config", str(config),
                "--intervals", *intervals, "--out-json", str(out_json), "--out-md", str(out_md)]
        stdout, stderr = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            code = cc.main(argv)
        report = json.loads(out_json.read_text(encoding="utf-8")) if out_json.exists() else None
        return code, report, stdout.getvalue(), stderr.getvalue()

    def row(self, report: dict, threshold: str) -> dict:
        return next(r for r in report["comparisons"] if r["threshold"] == threshold)

    def assert_input_error(self, fragment: str, **kwargs) -> None:
        code, report, out, err = self.run_judge(**kwargs)
        self.assertEqual(cc.EXIT_INPUT_ERROR, code, err)
        self.assertIsNone(report)
        self.assertEqual("", out)
        self.assertIn(fragment, err)


class TestChurnJudge(JudgeCase):
    def test_values_at_thresholds_are_met_and_evidence_is_freeze_ready(self) -> None:
        code, report, out, _ = self.run_judge()
        self.assertEqual(cc.EXIT_PASS, code)
        self.assertTrue(report["met"])
        self.assertIn("met=true", report["evidence"])
        self.assertIn(str(self.tmp / "criteria.yaml"), report["evidence"])
        self.assertIn(str(SEEDS), report["evidence"])
        self.assertIn("충족 (met=true)", out)
        from src.measurement import freeze

        evidence = freeze.ChurnThresholdEvidence(met=report["met"], evidence=report["evidence"])
        self.assertTrue(evidence.met)

    def test_boundaries_are_inclusive_and_exact(self) -> None:
        # 28 × (1 ± 0.2) = 22.4 · 33.6, 42 × (1 ± 0.2) = 33.6 · 50.4 — float 로는 22.4 가 22.399… 다.
        self.set_values(75, ["22.4", "33.6", "22.4", "33.6", "28"])
        self.set_values(90, ["33.6", "50.4", "33.6", "50.4", "42"])
        code, report, _, _ = self.run_judge()
        self.assertEqual(cc.EXIT_PASS, code)
        self.assertEqual(["112/5", "168/5"], self.row(report, "at_risk_days")["allowed_exact"])
        self.assertEqual({"pass"}, set(self.row(report, "at_risk_days")["seed_verdicts"].values()))

    def test_just_outside_the_boundary_is_not_met(self) -> None:
        self.set_values(75, ["22.39", "28", "28", "28", "28"])
        code, report, out, _ = self.run_judge()
        self.assertEqual(cc.EXIT_FAIL, code)
        self.assertFalse(report["met"])
        self.assertIn("met=false", report["evidence"])
        self.assertIn("미충족", out)
        self.assertEqual("on_fail(테스트)", report["verdict"]["on_fail"])

    def test_mean_inside_but_one_seed_outside_is_not_met(self) -> None:
        self.set_values(90, ["40", "40", "40", "40", "51"])   # 평균 42.2 (허용 안), 51 > 50.4
        code, report, _, _ = self.run_judge()
        self.assertEqual(cc.EXIT_FAIL, code)
        row = self.row(report, "no_purchase_days")
        self.assertEqual("pass", row["mean_verdict"])
        self.assertEqual("fail", row["seed_verdicts"]["51"])
        self.assertEqual("pass", self.row(report, "at_risk_days")["verdict"])

    def test_mean_is_exact_without_rounding(self) -> None:
        # 평균 = (33.6·4 + 33.61) / 5 = 33.602 > 33.6 이지만 seed 하나만 밖이다 — 평균도 밖으로 판정돼야 한다.
        self.set_values(75, ["33.6", "33.6", "33.6", "33.6", "33.61"])
        _, report, _, _ = self.run_judge()
        row = self.row(report, "at_risk_days")
        self.assertEqual("fail", row["mean_verdict"])
        self.assertEqual(str(Fraction("33.602")), row["mean_exact"])

    def test_thresholds_and_tolerance_come_from_their_sources(self) -> None:
        self.thresholds["at_risk_days"] = 30
        self.criteria["churn_threshold"]["tolerance_ratio"] = 0.1
        self.set_values(75, ["27", "33", "30", "30", "30"])       # 30 × (1 ± 0.1) = 27 · 33
        code, report, _, _ = self.run_judge()
        self.assertEqual(cc.EXIT_PASS, code, report)
        row = self.row(report, "at_risk_days")
        self.assertEqual(30, row["threshold_days"])
        self.assertEqual([27.0, 33.0], row["allowed"])
        self.assertEqual("1/10", report["tolerance_ratio"])

    def test_missing_seed(self) -> None:
        del self.reports[51]
        self.assert_input_error("기준 seed [51] 가 없다")

    def test_extra_seed(self) -> None:
        self.reports[52] = interval_report(52)
        self.assert_input_error("기준에 없는 seed [52]")

    def test_duplicate_seed(self) -> None:
        self.reports[50] = interval_report(51)
        self.assert_input_error("seed 51 가 중복된다")

    def test_simulator_version_differs_between_seeds(self) -> None:
        self.reports[49]["simulator_version"] = "sim-other"
        self.assert_input_error("simulator_version 가 seed 마다 다르다")

    def test_source_commit_differs_between_seeds(self) -> None:
        self.reports[49]["source_commit"] = "b" * 40
        self.assert_input_error("source_commit 가 seed 마다 다르다")

    def test_missing_simulator_version(self) -> None:
        for report in self.reports.values():
            report["simulator_version"] = None
        self.assert_input_error("simulator_version 을 확인할 수 없다")

    def test_measurement_conditions_must_match_criteria(self) -> None:
        for key, value in (("profile", "small"), ("customers", 12999), ("days", 272), ("customers", 13000.0)):
            with self.subTest(key=key, value=value):
                self.reports = {seed: interval_report(seed) for seed in SEEDS}
                self.reports[48][key] = value
                self.assert_input_error(f"{key} {value!r} ≠ 기준")

    def test_exact_value_must_agree_with_displayed_value(self) -> None:
        self.reports[47]["p75_exact"] = "29"
        self.assert_input_error("p75_exact 29 와 p75 28.0 가 다르다")

    def test_missing_exact_value(self) -> None:
        del self.reports[47]["p90_exact"]
        self.assert_input_error("p90_exact 가 분수 문자열이 아니다")

    def test_missing_threshold_in_simulator_config(self) -> None:
        del self.thresholds["no_purchase_days"]
        self.assert_input_error("churn.no_purchase_days 가 양의 정수가 아니다")

    def test_block_structure_is_validated(self) -> None:
        cases = [
            (lambda b: b.pop("tolerance_ratio"), "tolerance_ratio 가 수가 아니다"),
            (lambda b: b.update(tolerance_ratio=True), "tolerance_ratio 가 수가 아니다"),
            (lambda b: b.pop("comparisons"), "comparisons 가 비어 있다"),
            (lambda b: b["comparisons"].append({"threshold": "x", "quantile": 50}), "quantile 50 은 measure 가 내지 않는다"),
            (lambda b: b.update(role="other"), "role 이 'churn_evidence' 가 아니다"),
            (lambda b: b.pop("rule"), "churn_threshold.rule 가 비어 있지 않은 문자열이 아니다"),
            (lambda b: b["source"].update(customers_from="sample.other"), "customers_from"),
            (lambda b: b.update(thresholds_from="config/simulator_config.yaml"), "'<파일> <점 경로>' 형식이 아니다"),
        ]
        original = copy.deepcopy(self.criteria)
        for mutate, fragment in cases:
            with self.subTest(fragment=fragment):
                self.criteria = copy.deepcopy(original)
                mutate(self.criteria["churn_threshold"])
                self.assert_input_error(fragment)

    def test_missing_block(self) -> None:
        del self.criteria["churn_threshold"]
        self.assert_input_error("churn_threshold 블록이 없다")


@unittest.skipUnless(HAVE_YAML, NEEDS_YAML)
class TestRealCriteria(unittest.TestCase):
    """저장소의 기준 파일 · simulator_config 를 이 스크립트가 그대로 읽는지(블록 키가 어긋나면 여기서 잡힌다)."""

    def test_real_block_and_thresholds_load(self) -> None:
        raw = cc.gj._load_yaml(REAL_CRITERIA, "기준 파일")
        block = cc.load_churn_block(raw, REAL_CRITERIA)
        thresholds = cc.load_thresholds(block, REAL_SIMULATOR_CONFIG)
        self.assertEqual({c.threshold for c in block.comparisons}, set(thresholds))
        self.assertEqual((cc.DEFAULT_PROFILE, cc.DEFAULT_DAYS), (block.profile, block.days))
        self.assertEqual("config/simulator_config.yaml", block.thresholds_from.split()[0])


def _simulator_available() -> bool:
    try:
        sys.path.insert(0, str(REPO)) if str(REPO) not in sys.path else None
        from src.simulator import api  # noqa: F401
    except ImportError:
        return False
    return True


@unittest.skipUnless(_simulator_available(), "BLOCKED: src.simulator 를 import 하지 못했다 — measure 실측 미검증(통과가 아니다)")
class TestMeasureRealRun(unittest.TestCase):
    """공개 API 로 작은 세계를 실제로 만들어 잰다. seed 는 보정 seed 42 만 쓴다(확인 seed 47~51 은 열지 않는다)."""

    def test_measure_writes_intervals_and_refuses_existing_dir(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "warmup"
            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                code = cc.main(["measure", "--seed", "42", "--customers", "40", "--out", str(out)])
            self.assertEqual(cc.EXIT_PASS, code)
            data = json.loads((out / cc.INTERVALS_FILE).read_text(encoding="utf-8"))
            self.assertEqual((42, 40, "reference", 273), (data["seed"], data["customers"], data["profile"], data["days"]))
            self.assertTrue(isinstance(data["simulator_version"], str) and data["simulator_version"])
            self.assertGreaterEqual(data["n_gaps"], 2)
            self.assertLessEqual(data["n_customers_with_gap"], data["n_customers_with_purchase"])
            for q in (75, 90):
                self.assertEqual(float(Fraction(data[f"p{q}_exact"])), data[f"p{q}"])
            self.assertIn("중복 제거 없음", data["definition"]["interval"])

            stderr = io.StringIO()
            with contextlib.redirect_stderr(stderr):
                again = cc.main(["measure", "--seed", "42", "--customers", "40", "--out", str(out)])
            self.assertEqual(cc.EXIT_INPUT_ERROR, again)
            self.assertIn("이미 있다", stderr.getvalue())


if __name__ == "__main__":
    unittest.main()
