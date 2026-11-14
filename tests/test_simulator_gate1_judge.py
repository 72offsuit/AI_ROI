"""`scripts/gate1_judge.py` — GATE 1 판정이 범위 밖이면 실패(1), 입력이 기준과 어긋나면 입력 오류(2),
예상 밖 오류면 내부 오류(3)로 끝나는지.

기준 yaml 과 simulator_config 띠는 테스트 안의 픽스처다(기준 파일은 #275 로 따로 병합된다).
가드레일 리포트는 가짜 JSON 이고, realism JSON 은 저장소의 예시 출력 `docs/research/realism_report.json`
을 seed 마다 복사해 쓴다. 그 예시는 지금 realism_check 로 다시 만든 것이 아니므로(옛 simulator_version),
예시 기반 매핑 테스트는 "저장소 예시 출력 구조 기준" 이다. 현재 realism_check 계산기가 내는 synthetic 키와의
대조는 `TestSyntheticKeysMatchRealismCalculators` 가 최소 이벤트로 계산기를 실제로 돌려서 한다.
`TestAgainstRealGuardrailReport` 는 실제 `guardrails` CLI 출력으로 검사 이름(`quadrant_consistency_*`)을 대조한다.

PyYAML 이 없으면 skip, realism_check 대조는 numpy · pandas 가 없으면 skip 한다. skip 은 통과가 아니다.
"""

from __future__ import annotations

import contextlib
import copy
import importlib.util
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

REPO = Path(__file__).resolve().parents[1]
SCRIPT = REPO / "scripts" / "gate1_judge.py"
REALISM_SCRIPT = REPO / "scripts" / "research" / "realism_check.py"
EXAMPLE_REALISM = REPO / "docs" / "research" / "realism_report.json"

NEEDS_YAML = "BLOCKED: PyYAML 미설치 — GATE 1 판정을 검증하지 않았다(통과가 아니다)"
NEEDS_PANDAS = "BLOCKED: numpy/pandas 미설치 — realism_check.judge 와 대조하지 않았다(통과가 아니다)"
NEEDS_PANDAS_CALC = "BLOCKED: numpy/pandas 미설치 — realism_check 계산기의 synthetic 키와 대조하지 않았다(통과가 아니다)"

try:
    import yaml

    _spec = importlib.util.spec_from_file_location("gate1_judge", SCRIPT)
    gj = importlib.util.module_from_spec(_spec)
    sys.modules["gate1_judge"] = gj  # dataclass 가 모듈을 찾는다
    _spec.loader.exec_module(gj)
    HAVE_YAML = True
except ImportError:  # pragma: no cover - 의존성 없는 CI 잡
    HAVE_YAML = False

try:
    import numpy  # noqa: F401
    import pandas  # noqa: F401

    if "realism_check" in sys.modules:
        rc = sys.modules["realism_check"]
    else:
        _rspec = importlib.util.spec_from_file_location("realism_check", REALISM_SCRIPT)
        rc = importlib.util.module_from_spec(_rspec)
        sys.modules["realism_check"] = rc
        _rspec.loader.exec_module(rc)
    HAVE_PANDAS = True
except ImportError:  # pragma: no cover - 의존성 없는 CI 잡
    HAVE_PANDAS = False

SEEDS = [47, 48, 49, 50, 51]
CUSTOMERS = 13000
BANDS = {
    "churn_rate_bp": [1500, 2500], "ate_bp": [300, 600], "coupon_use_bp": [500, 2000],
    "sleeping_dog_bp": [800, 1500], "persuadable_bp": [1100, 2100],
}
BAND_CHECKS = {
    "churn_rate": ("F12", "churn_rate_bp", 2000),
    "ate_T3": ("F14", "ate_bp", 450),
    "coupon_use_T2": ("F15", "coupon_use_bp", 1100),
    "coupon_use_T3": ("F15", "coupon_use_bp", 700),
    "sleeping_dog_T3": ("F16", "sleeping_dog_bp", 1000),
    "persuadable_T3": ("F16", "persuadable_bp", 1500),
}
CONSISTENCY_CHECKS = [f"quadrant_consistency_T{k}" for k in range(1, 5)]
RECORDED = ["F1", "F2", "F3", "F4", "F5", "F6", "F7", "F8", "F9", "F10", "F11", "F13", "F17"]


PROFILE = "small"
WARMUP_DAYS = 180
ACTIVE_CUSTOMERS, ELIGIBLE_CUSTOMERS = 6100, 5300


def criteria_fixture(seeds=SEEDS, customers=CUSTOMERS, profile=PROFILE, warmup_days=WARMUP_DAYS) -> dict:
    """`config/simulator_gate1_acceptance.yaml`(#275)과 같은 구조 — 스크립트가 읽는 키만 채운다."""
    checks = [{"fact": fact, "name": name,
               "population": "active42" if name == "churn_rate" else "eligible_spec41",
               "band_from": f"guardrails.{key}"}
              for name, (fact, key, _) in BAND_CHECKS.items()]
    checks += [{"fact": "F16", "name": name, "population": "eligible_spec41", "abs_max_bp": 50}
               for name in CONSISTENCY_CHECKS]
    return {
        "version": "gate1-acceptance-v1", "fixed_before_measurement": True,
        "pending": "lead_confirmation_treatment_population",
        "sample": {"seeds": list(seeds), "customers": customers, "guardrail_profile": profile,
                   "guardrail_warmup_days": warmup_days, "guardrail_full_evaluation": True},
        "verdict": {"required": {"source": "guardrail_report", "checks": checks},
                    "recorded": {"source": "realism", "facts": list(RECORDED)},
                    "reference_only": ["…"]},
    }


def guardrail_report(seed: int, values: dict | None = None, *, customers=CUSTOMERS) -> dict:
    """가드레일 CLI 출력 모양(`checks[]` 의 name · value_bp · range_bp · status · role, 모집단 블록, 실행 조건)."""
    values = values or {}
    checks = []
    for name, (_, key, default) in BAND_CHECKS.items():
        value = values.get(name, default)
        lo, hi = BANDS[key]
        checks.append({"name": name, "value_bp": value, "range_bp": [lo, hi],
                       "status": "not_run" if value is None else ("pass" if lo <= value <= hi else "fail"),
                       "role": "판정"})
    for arm in ("T1", "T2", "T4"):
        checks.append({"name": f"ate_{arm}", "value_bp": 350, "range_bp": [300, 600], "status": "pass", "role": "판정"})
    for name in CONSISTENCY_CHECKS:
        value = values.get(name, 0)
        checks.append({"name": name, "value_bp": value, "range_bp": [-50, 50],
                       "status": "not_run" if value is None else ("pass" if abs(value) <= 50 else "fail"),
                       "role": "판정"})
    checks.append({"name": "active42_quadrant_consistency_T3", "value_bp": 0, "range_bp": [-50, 50],
                   "status": "pass", "role": "참고"})
    checks.append({"name": "spec41_churn_rate", "value_bp": 4000, "range_bp": [1500, 2500],
                   "status": "fail", "role": "참고"})
    return {"seed": seed, "customers": customers, "profile": PROFILE, "warmup_days": WARMUP_DAYS,
            "simulator_version": "sim-test",
            "active_customers": ACTIVE_CUSTOMERS, "eligible_customers": ELIGIBLE_CUSTOMERS,
            "active42": {"customers": ACTIVE_CUSTOMERS, "evaluated_customers": ACTIVE_CUSTOMERS},
            "eligible_spec41": {"customers": ELIGIBLE_CUSTOMERS, "evaluated_customers": ELIGIBLE_CUSTOMERS},
            "checks": checks}


def realism_report(seed: int) -> dict:
    report = json.loads(EXAMPLE_REALISM.read_text(encoding="utf-8"))
    report["source"]["random_seed"] = str(seed)
    report["source"]["simulator_version"] = "sim-test"
    return report


def metric(report: dict, fact: str) -> dict:
    return next(m for m in report["metrics"] if m["id"] == fact)


@unittest.skipUnless(HAVE_YAML, NEEDS_YAML)
class JudgeCase(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.tmp = Path(self._tmp.name)
        self.criteria = criteria_fixture()
        self.bands = copy.deepcopy(BANDS)
        self.guardrails = {seed: guardrail_report(seed) for seed in SEEDS}
        self.realism = {seed: realism_report(seed) for seed in SEEDS}

    def set_values(self, name: str, values: list) -> None:
        for seed, value in zip(SEEDS, values):
            check = next(c for c in self.guardrails[seed]["checks"] if c["name"] == name)
            check["value_bp"] = value
            if value is None:
                check["status"] = "not_run"

    def write_inputs(self) -> tuple[Path, Path, Path, Path]:
        criteria = self.tmp / "criteria.yaml"
        criteria.write_text(yaml.safe_dump(self.criteria, allow_unicode=True), encoding="utf-8")
        config = self.tmp / "simulator_config.yaml"
        config.write_text(json.dumps({"guardrails": {"note": "fixture", **self.bands}}), encoding="utf-8")
        guard_dir, realism_dir = self.tmp / "guard", self.tmp / "realism"
        guard_dir.mkdir(exist_ok=True)
        realism_dir.mkdir(exist_ok=True)
        # 파일 이름과 seed 를 일부러 어긋나게 둔다 — 짝짓기는 JSON 안의 seed 로 해야 한다.
        for index, (seed, report) in enumerate(sorted(self.guardrails.items(), reverse=True)):
            (guard_dir / f"guardrails-world{index}-d180.json").write_text(json.dumps(report), encoding="utf-8")
        for index, (seed, report) in enumerate(sorted(self.realism.items())):
            (realism_dir / f"realism-{index}.json").write_text(json.dumps(report), encoding="utf-8")
        return criteria, config, guard_dir, realism_dir

    def run_judge(self, *extra: str, guardrail=None, realism=None, rewrite=True) -> tuple[int, dict | None, str, str]:
        # rewrite=False 는 테스트가 손으로 고친 입력 파일을 덮어쓰지 않으려고 쓴다.
        if rewrite:
            criteria, config, guard_dir, realism_dir = self.write_inputs()
        else:
            criteria, config = self.tmp / "criteria.yaml", self.tmp / "simulator_config.yaml"
            guard_dir, realism_dir = self.tmp / "guard", self.tmp / "realism"
        out_json = self.tmp / "out" / "judge.json"
        argv = ["--criteria", str(criteria), "--simulator-config", str(config),
                "--guardrail", *(guardrail or [str(guard_dir)]), "--realism", *(realism or [str(realism_dir)]),
                "--out-json", str(out_json), *extra]
        stdout, stderr = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            code = gj.main(argv)
        report = json.loads(out_json.read_text(encoding="utf-8")) if out_json.exists() else None
        return code, report, stdout.getvalue(), stderr.getvalue()

    def required(self, report: dict, name: str) -> dict:
        return next(r for r in report["required"] if r["name"] == name)

    def recorded(self, report: dict, fact: str) -> dict:
        return next(r for r in report["recorded"] if r["fact"] == fact)

    def criteria_check(self, name: str) -> dict:
        return next(c for c in self.criteria["verdict"]["required"]["checks"] if c["name"] == name)

    def assert_input_error(self, fragment: str, **kwargs) -> None:
        code, report, out, err = self.run_judge(**kwargs)
        self.assertEqual(gj.EXIT_INPUT_ERROR, code, err)
        self.assertIsNone(report)  # 판정하지 않았으면 판정표도 남기지 않는다
        self.assertEqual("", out)
        self.assertIn(fragment, err)


class TestRequiredChecks(JudgeCase):
    def test_all_required_checks_pass_exits_zero(self) -> None:
        code, report, out, _ = self.run_judge()
        self.assertEqual(gj.EXIT_PASS, code)
        self.assertTrue(report["verdict"]["required_pass"])
        self.assertEqual([], report["verdict"]["failed"])
        self.assertEqual(len(BAND_CHECKS) + len(CONSISTENCY_CHECKS), len(report["required"]))
        self.assertIn("필수 검사 통과", out)

    def test_mean_outside_band_fails_even_when_every_seed_is_borderline(self) -> None:
        self.set_values("ate_T3", [650] * 5)
        code, report, _, _ = self.run_judge()
        self.assertEqual(gj.EXIT_FAIL, code)
        row = self.required(report, "ate_T3")
        self.assertEqual({"borderline"}, set(row["seed_verdicts"].values()))
        self.assertEqual("fail", row["mean_verdict"])
        self.assertEqual(["ate_T3"], report["verdict"]["failed"])

    def test_one_seed_beyond_borderline_fails_even_when_mean_is_inside(self) -> None:
        self.set_values("ate_T3", [450, 450, 450, 450, 750])  # 평균 510 · 750 > 720(600 × 1.2)
        code, report, _, _ = self.run_judge()
        self.assertEqual(gj.EXIT_FAIL, code)
        row = self.required(report, "ate_T3")
        self.assertEqual("pass", row["mean_verdict"])
        self.assertEqual("fail", row["seed_verdicts"]["51"])

    def test_borderline_seed_is_allowed_when_mean_is_inside(self) -> None:
        self.set_values("ate_T3", [400, 400, 400, 400, 720])  # 720 은 상한 경계값 그대로
        code, report, _, _ = self.run_judge()
        self.assertEqual(gj.EXIT_PASS, code)
        self.assertEqual("borderline", self.required(report, "ate_T3")["seed_verdicts"]["51"])

    def test_mean_is_compared_without_rounding(self) -> None:
        self.set_values("ate_T3", [600, 600, 600, 600, 601])  # 평균 600.2bp — 반올림하면 600 으로 통과한다
        code, report, _, _ = self.run_judge()
        self.assertEqual(gj.EXIT_FAIL, code)
        self.assertAlmostEqual(600.2, self.required(report, "ate_T3")["mean_bp"])

    def test_band_edges_are_inclusive(self) -> None:
        self.set_values("ate_T3", [600] * 5)
        self.set_values("churn_rate", [1500] * 5)
        code, _, _, _ = self.run_judge()
        self.assertEqual(gj.EXIT_PASS, code)

    def test_consistency_uses_absolute_value_per_seed_so_opposite_signs_do_not_cancel(self) -> None:
        self.set_values("quadrant_consistency_T2", [60, -60, 0, 0, 0])  # 부호 있는 평균은 0
        code, report, _, _ = self.run_judge()
        self.assertEqual(gj.EXIT_FAIL, code)
        row = self.required(report, "quadrant_consistency_T2")
        self.assertEqual("fail", row["seed_verdicts"]["47"])
        self.assertEqual("fail", row["seed_verdicts"]["48"])
        self.assertEqual(60, row["max_abs_bp"])

    def test_consistency_limit_is_inclusive_and_has_no_borderline(self) -> None:
        self.set_values("quadrant_consistency_T1", [50, -50, 0, 0, 0])
        self.assertEqual(gj.EXIT_PASS, self.run_judge()[0])
        self.set_values("quadrant_consistency_T1", [51, 0, 0, 0, 0])  # 크기 띠라면 ±20% 경계로 통과했을 값
        self.assertEqual(gj.EXIT_FAIL, self.run_judge()[0])

    def test_not_run_or_missing_value_is_a_failure_not_a_pass(self) -> None:
        self.set_values("coupon_use_T2", [1100, 1100, None, 1100, 1100])
        code, report, _, _ = self.run_judge()
        self.assertEqual(gj.EXIT_FAIL, code)
        row = self.required(report, "coupon_use_T2")
        self.assertEqual("no_data", row["seed_verdicts"]["49"])
        self.assertIsNone(row["mean_bp"])
        self.set_values("coupon_use_T2", [1100] * 5)
        self.set_values("quadrant_consistency_T3", [0, 0, 0, 0, None])
        self.assertEqual(gj.EXIT_FAIL, self.run_judge()[0])

    def test_reference_checks_are_listed_but_never_judged(self) -> None:
        code, report, out, _ = self.run_judge()
        self.assertEqual(gj.EXIT_PASS, code)  # spec41_churn_rate(참고)는 띠 밖이지만 종료 코드에 들지 않는다
        names = {row["name"] for row in report["reference"]["guardrail"]}
        self.assertTrue({"spec41_churn_rate", "active42_quadrant_consistency_T3", "ate_T1"} <= names)
        self.assertEqual({"F12", "F14", "F15", "F16"}, {row["fact"] for row in report["reference"]["realism"]})
        self.assertIn("참고 (판정하지 않음)", out)


class TestInputErrors(JudgeCase):

    def test_missing_guardrail_seed(self) -> None:
        del self.guardrails[50]
        self.assert_input_error("기준 seed [50] 가 없다")

    def test_missing_realism_seed(self) -> None:
        del self.realism[47]
        self.assert_input_error("realism 에 기준 seed [47] 가 없다")

    def test_extra_seed(self) -> None:
        self.guardrails[52] = guardrail_report(52)
        self.assert_input_error("기준에 없는 seed [52]")

    def test_duplicate_seed(self) -> None:
        criteria, config, guard_dir, realism_dir = self.write_inputs()
        twin = self.tmp / "twin.json"
        twin.write_text(json.dumps(guardrail_report(48)), encoding="utf-8")
        self.assert_input_error("seed 48 가 중복된다", guardrail=[str(guard_dir), str(twin)])

    def test_mixed_seed_realism_cannot_be_paired(self) -> None:
        self.realism[49]["source"]["random_seed"] = ["49", "50"]
        self.assert_input_error("seed 를 읽지 못했다")

    def test_missing_required_check_name(self) -> None:
        checks = self.guardrails[49]["checks"]
        self.guardrails[49]["checks"] = [c for c in checks if c["name"] != "quadrant_consistency_T4"]
        self.assert_input_error("quadrant_consistency_T4 가 없다")

    def test_pre_rename_report_is_an_input_error(self) -> None:
        # 이름 정정(identity_* → quadrant_consistency_*) 전 리포트를 넣으면 판정하지 않는다.
        for report in self.guardrails.values():
            for check in report["checks"]:
                check["name"] = check["name"].replace("quadrant_consistency_", "identity_")
        self.assert_input_error("quadrant_consistency_T1 가 없다")

    def test_required_check_only_as_reference_role_is_missing(self) -> None:
        for check in self.guardrails[47]["checks"]:
            if check["name"] == "churn_rate":
                check["role"] = "참고"
        self.assert_input_error("검사 churn_rate 가 없다")

    def test_range_bp_differs_from_simulator_config(self) -> None:
        self.bands["ate_bp"] = [300, 650]
        self.assert_input_error("simulator_config guardrails.ate_bp [300, 650] 와 다르다")

    def test_customers_differs_from_criteria(self) -> None:
        self.guardrails[51]["customers"] = 20000
        self.assert_input_error("customers 20000 ≠ 기준 13000")

    def test_simulator_version_differs_between_seeds(self) -> None:
        self.guardrails[51]["simulator_version"] = "sim-other"
        self.assert_input_error("simulator_version 가 seed 마다 다르다")

    def test_broken_json(self) -> None:
        broken = self.tmp / "broken.json"
        broken.write_text("{not json", encoding="utf-8")
        self.assert_input_error("JSON 으로 읽지 못했다", realism=[str(self.tmp / "realism"), str(broken)])

    def test_recorded_fact_missing_from_realism(self) -> None:
        self.realism[48]["metrics"] = [m for m in self.realism[48]["metrics"] if m["id"] != "F10"]
        self.assert_input_error("기록 검사 F10 가 없다")

    def test_realism_band_differs_between_seeds(self) -> None:
        metric(self.realism[48], "F2")["reference"]["band"] = [0.4, 0.7]
        self.assert_input_error("F2 의 reference.band 가 seed 마다 다르다")

    def test_missing_criteria_file(self) -> None:
        stderr = io.StringIO()
        with contextlib.redirect_stderr(stderr), contextlib.redirect_stdout(io.StringIO()):
            code = gj.main(["--criteria", str(self.tmp / "absent.yaml"), "--guardrail", str(self.tmp),
                            "--realism", str(self.tmp)])
        self.assertEqual(gj.EXIT_INPUT_ERROR, code)
        self.assertIn("기준 파일", stderr.getvalue())

    def test_empty_input_directory(self) -> None:
        empty = self.tmp / "empty"
        empty.mkdir()
        self.assert_input_error("guardrails-*.json 파일이 없다", guardrail=[str(empty)])


class TestCriteriaPopulation(JudgeCase):
    """기준 `checks[].population` 이 가드레일 리포트의 `role: 판정` 모집단과 다르면 판정하지 않는다(DR-194)."""

    def test_churn_rate_on_treatment_population_is_refused(self) -> None:
        self.criteria_check("churn_rate")["population"] = "eligible_spec41"
        self.assert_input_error("churn_rate 의 population 'eligible_spec41' 는 이 스크립트가 판정할 수 없다")

    def test_treatment_check_on_active_population_is_refused(self) -> None:
        self.criteria_check("ate_T3")["population"] = "active42"
        self.assert_input_error("ate_T3 의 population 'active42' 는 이 스크립트가 판정할 수 없다")

    def test_missing_population_is_refused(self) -> None:
        del self.criteria_check("quadrant_consistency_T1")["population"]
        self.assert_input_error("quadrant_consistency_T1 의 population None 는 이 스크립트가 판정할 수 없다")

    def test_population_is_carried_into_the_report(self) -> None:
        code, report, _, _ = self.run_judge()
        self.assertEqual(gj.EXIT_PASS, code)
        self.assertEqual("active42", self.required(report, "churn_rate")["population"])
        self.assertEqual("eligible_spec41", self.required(report, "ate_T3")["population"])


class TestGuardrailRunConditions(JudgeCase):
    """가드레일 리포트가 기준의 실측 조건(profile · warmup_days · 전수 평가)으로 잰 것인지 대조한다."""

    def test_profile_differs_from_criteria(self) -> None:
        self.guardrails[48]["profile"] = "reference"
        self.assert_input_error("profile 'reference' ≠ 기준 'small'")

    def test_warmup_days_differs_from_criteria(self) -> None:
        self.guardrails[50]["warmup_days"] = 90
        self.assert_input_error("warmup_days 90 ≠ 기준 180")

    def test_report_without_run_condition_keys(self) -> None:
        del self.guardrails[47]["profile"]
        del self.guardrails[47]["warmup_days"]
        self.assert_input_error("profile None ≠ 기준 'small'")

    def test_sampled_treatment_population_is_not_a_full_evaluation(self) -> None:
        self.guardrails[49]["eligible_spec41"]["evaluated_customers"] = 1000  # --sample 1000
        self.assert_input_error("eligible_spec41.evaluated_customers 1000 ≠ eligible_customers 5300")

    def test_sampled_churn_population_is_not_a_full_evaluation(self) -> None:
        self.guardrails[51]["active42"]["evaluated_customers"] = 1000
        self.assert_input_error("active42.evaluated_customers 1000 ≠ active_customers 6100")

    def test_missing_population_block(self) -> None:
        del self.guardrails[51]["active42"]
        self.assert_input_error("active42.evaluated_customers None ≠ active_customers 6100")

    def test_sampled_report_is_accepted_when_criteria_do_not_require_full_evaluation(self) -> None:
        self.criteria["sample"]["guardrail_full_evaluation"] = False
        self.guardrails[49]["eligible_spec41"]["evaluated_customers"] = 1000
        self.assertEqual(gj.EXIT_PASS, self.run_judge()[0])

    def test_criteria_without_run_condition_keys(self) -> None:
        # 정본은 기준 파일이다 — 스크립트가 기본값을 상수로 대신하지 않는다.
        for key in ("guardrail_profile", "guardrail_warmup_days", "guardrail_full_evaluation"):
            with self.subTest(key=key):
                self.criteria = criteria_fixture()
                del self.criteria["sample"][key]
                self.assert_input_error(f"sample.{key}")

    def test_criteria_full_evaluation_must_be_a_boolean(self) -> None:
        self.criteria["sample"]["guardrail_full_evaluation"] = "yes"
        self.assert_input_error("sample.guardrail_full_evaluation")


class TestNonFiniteValues(JudgeCase):
    """Infinity · NaN 은 두 생성기가 내지 않는 값이다 — 필수 실패(1)가 아니라 입력 오류(2)다."""

    def test_infinite_required_value(self) -> None:
        self.set_values("ate_T3", [450, 450, float("inf"), 450, 450])
        self.assert_input_error("유한한 수가 아니다: Infinity")

    def test_nan_required_value(self) -> None:
        self.set_values("quadrant_consistency_T2", [0, float("nan"), 0, 0, 0])
        self.assert_input_error("유한한 수가 아니다: NaN")

    def test_overflowing_number_literal(self) -> None:
        # json 은 1e999 를 parse_constant 없이 float('inf') 로 읽는다.
        self.write_inputs()
        path = next((self.tmp / "guard").glob("*.json"))
        path.write_text(path.read_text(encoding="utf-8").replace('"value_bp": 450', '"value_bp": 1e999', 1),
                        encoding="utf-8")
        code, _, _, err = self.run_judge(guardrail=[str(path.parent)], rewrite=False)
        self.assertEqual(gj.EXIT_INPUT_ERROR, code, err)
        self.assertIn("유한한 수가 아니다: 1e999", err)

    def test_nan_in_reference_guardrail_value(self) -> None:
        check = next(c for c in self.guardrails[47]["checks"] if c["name"] == "spec41_churn_rate")
        check["value_bp"] = float("nan")
        self.assert_input_error("유한한 수가 아니다: NaN")

    def test_infinite_realism_value(self) -> None:
        metric(self.realism[50], "F12")["synthetic"]["churn_pct_mean"] = float("inf")
        self.assert_input_error("유한한 수가 아니다: Infinity")

    def test_value_bp_finite_check_without_json(self) -> None:
        # JSON 을 거치지 않고 리포트 dict 를 넘겨도 required_checks_by_seed 가 막는다.
        problems: list[str] = []
        criteria_path = self.write_inputs()[0]
        criteria = gj.load_criteria(criteria_path)
        self.set_values("ate_T3", [450, 450, float("inf"), 450, 450])
        reports = {seed: (Path(f"g{seed}.json"), report) for seed, report in self.guardrails.items()}
        bands = {name: tuple(BANDS[key]) for name, (_, key, _) in BAND_CHECKS.items()}
        gj.required_checks_by_seed(criteria, bands, reports, problems)
        self.assertTrue(any("ate_T3 의 value_bp 가 유한한 수가 아니다" in p for p in problems), problems)


class TestSimulatorVersion(JudgeCase):
    def test_versions_differ_between_sources(self) -> None:
        for report in self.realism.values():
            report["source"]["simulator_version"] = "sim-other"
        self.assert_input_error("simulator_version 이 출처마다 다르다: 가드레일 'sim-test' · realism 'sim-other'")

    def test_realism_version_missing(self) -> None:
        for report in self.realism.values():
            report["source"]["simulator_version"] = None
        self.assert_input_error("simulator_version 을 확인할 수 없다")

    def test_guardrail_version_missing(self) -> None:
        for report in self.guardrails.values():
            del report["simulator_version"]
        self.assert_input_error("simulator_version 을 확인할 수 없다")

    def test_mixed_version_realism_is_unverifiable(self) -> None:
        # realism_check 는 이벤트 버전이 여럿이면 목록으로 싣는다.
        for report in self.realism.values():
            report["source"]["simulator_version"] = ["sim-test", "sim-old"]
        self.assert_input_error("simulator_version 을 확인할 수 없다")


class TestInternalErrors(JudgeCase):
    """예상 밖 예외는 필수 실패(1) · 입력 오류(2)와 구분되는 종료 코드 3 이다."""

    def test_output_write_failure_is_an_internal_error(self) -> None:
        blocked = self.tmp / "is_a_directory.md"
        blocked.mkdir()
        code, _, _, err = self.run_judge("--out-md", str(blocked))
        self.assertEqual(gj.EXIT_INTERNAL_ERROR, code)
        self.assertNotIn(code, (gj.EXIT_PASS, gj.EXIT_FAIL, gj.EXIT_INPUT_ERROR))
        self.assertIn("내부 오류", err)
        self.assertIn("IsADirectoryError", err)
        self.assertFalse((self.tmp / "out" / "judge.json").exists())  # 다른 출력도 남기지 않는다

    def leftovers(self, *dirs: Path) -> list[str]:
        return sorted(p.name for d in dirs if d.is_dir() for p in d.iterdir() if p.suffix in (".tmp", ".bak"))

    def test_json_write_failure_leaves_no_markdown_and_no_stdout(self) -> None:
        # 회귀: md 를 먼저 쓰고 json 에서 실패하면 "필수 검사 통과" 판정표가 md 와 stdout 에 남은 채 3 으로 끝났다.
        out_md, blocked = self.tmp / "md" / "judge.md", self.tmp / "json_dir"
        blocked.mkdir()
        code, _, out, err = self.run_judge("--out-md", str(out_md), "--out-json", str(blocked))
        self.assertEqual(gj.EXIT_INTERNAL_ERROR, code)
        self.assertFalse(out_md.exists())
        self.assertEqual([], list(blocked.iterdir()))
        self.assertEqual([], self.leftovers(out_md.parent, self.tmp))
        self.assertEqual("", out)
        self.assertIn("판정을 남기지 못했다(통과가 아니다)", err)

    def test_previous_output_files_are_left_untouched_when_writing_fails(self) -> None:
        out_md, blocked = self.tmp / "md" / "judge.md", self.tmp / "json_dir"
        out_md.parent.mkdir()
        out_md.write_text("OLD", encoding="utf-8")
        blocked.mkdir()
        code, _, _, _ = self.run_judge("--out-md", str(out_md), "--out-json", str(blocked))
        self.assertEqual(gj.EXIT_INTERNAL_ERROR, code)
        self.assertEqual("OLD", out_md.read_text(encoding="utf-8"))
        self.assertEqual([], self.leftovers(out_md.parent))

    def test_failure_while_renaming_rolls_back_the_file_already_replaced(self) -> None:
        # 임시 파일을 다 쓴 뒤 두 번째 rename 에서 실패하는 경우 — 첫 번째 대상은 이전 내용으로 되돌아가야 한다.
        out_md, out_json = self.tmp / "o" / "judge.md", self.tmp / "o" / "judge.json"
        out_md.parent.mkdir()
        out_md.write_text("OLD-MD", encoding="utf-8")
        out_json.write_text("OLD-JSON", encoding="utf-8")
        real_replace = gj.os.replace

        def flaky_replace(src, dst):
            if str(src).endswith(".tmp") and Path(dst) == out_json:
                raise OSError("simulated rename failure")
            return real_replace(src, dst)

        with mock.patch.object(gj.os, "replace", side_effect=flaky_replace):
            code, _, out, err = self.run_judge("--out-md", str(out_md), "--out-json", str(out_json))
        self.assertEqual(gj.EXIT_INTERNAL_ERROR, code)
        self.assertIn("simulated rename failure", err)
        self.assertEqual("", out)
        self.assertEqual("OLD-MD", out_md.read_text(encoding="utf-8"))
        self.assertEqual("OLD-JSON", out_json.read_text(encoding="utf-8"))
        self.assertEqual([], self.leftovers(out_md.parent))

    def test_successful_run_replaces_previous_outputs_without_leftovers(self) -> None:
        out_md, out_json = self.tmp / "o" / "judge.md", self.tmp / "o" / "judge.json"
        out_md.parent.mkdir()
        out_md.write_text("OLD-MD", encoding="utf-8")
        code, report, out, _ = self.run_judge("--out-md", str(out_md), "--out-json", str(out_json))
        self.assertEqual(gj.EXIT_PASS, code)
        self.assertEqual(out, out_md.read_text(encoding="utf-8"))
        self.assertTrue(json.loads(out_json.read_text(encoding="utf-8"))["verdict"]["required_pass"])
        self.assertEqual([], self.leftovers(out_md.parent))

    def test_same_path_for_both_outputs_is_an_input_error(self) -> None:
        same = self.tmp / "same.out"
        code, _, out, err = self.run_judge("--out-md", str(same), "--out-json", str(same))
        self.assertEqual(gj.EXIT_INPUT_ERROR, code)
        self.assertFalse(same.exists())
        self.assertEqual("", out)
        self.assertIn("--out-md 와 --out-json 이 같은 경로다", err)

    def test_unexpected_exception_while_judging_is_an_internal_error(self) -> None:
        with mock.patch.object(gj, "judge_recorded", side_effect=RuntimeError("boom")):
            code, report, _, err = self.run_judge()
        self.assertEqual(gj.EXIT_INTERNAL_ERROR, code)
        self.assertIsNone(report)
        self.assertIn("RuntimeError: boom", err)


class TestRecordedChecks(JudgeCase):
    def test_example_realism_output_maps_every_recorded_band_key(self) -> None:
        """매핑 표가 저장소 예시 출력(`docs/research/realism_report.json`) 구조와 맞는다 — 예시는 기록 항목 값이 모두 있다.

        예시는 옛 실행의 출력이라 현재 계산기와의 대조가 아니다(그것은 TestSyntheticKeysMatchRealismCalculators).
        """
        _, report, _, _ = self.run_judge()
        for item in report["recorded"]:
            for part in item["parts"]:
                self.assertIsNotNone(part["synthetic_key"], (item["fact"], part["key"]))
                self.assertNotEqual("no_data", part["verdict"], (item["fact"], part))

    def test_recorded_mean_reproduces_realism_verdict_for_identical_seeds(self) -> None:
        # 5 seed 가 같은 값이면 평균 = 그 값이므로 realism_check 가 그 리포트에 적은 판정과 같아야 한다.
        _, report, _, _ = self.run_judge()
        for item in report["recorded"]:
            reported = metric(self.realism[47], item["fact"])["verdict"]
            self.assertEqual(reported, item["verdict"], item["fact"])

    def test_recorded_failure_does_not_change_exit_code(self) -> None:
        for report in self.realism.values():
            metric(report, "F2")["synthetic"]["median_cv"] = 0.1
        code, report, out, _ = self.run_judge()
        self.assertEqual(gj.EXIT_PASS, code)
        self.assertEqual("fail", self.recorded(report, "F2")["verdict"])
        self.assertIn("| F2 | median_cv |", out)

    def test_recorded_uses_mean_of_seeds(self) -> None:
        for seed, value in zip(SEEDS, [0.40, 0.40, 0.50, 0.50, 0.50]):  # 평균 0.46 — 띠 [0.45, 0.70] 안
            metric(self.realism[seed], "F2")["synthetic"]["median_cv"] = value
        _, report, _, _ = self.run_judge()
        part = self.recorded(report, "F2")["parts"][0]
        self.assertAlmostEqual(0.46, part["mean"])
        self.assertEqual("pass", part["verdict"])

    def test_open_lower_band_excludes_its_bound(self) -> None:
        for report in self.realism.values():
            metric(report, "F13")["synthetic"]["share_returned_after_42d_gap"] = 0.0
            metric(report, "F8")["synthetic"]["ratio"] = 1.0
        _, report, _, _ = self.run_judge()
        self.assertEqual("fail", self.recorded(report, "F13")["verdict"])  # judge(0, 0, None) 였다면 pass
        self.assertEqual("borderline", self.recorded(report, "F8")["verdict"])

    def test_unmappable_band_key_is_no_data(self) -> None:
        for report in self.realism.values():
            metric(report, "F9")["reference"]["band"] = {"cart_abandonment": [50, 75]}
        code, report, _, _ = self.run_judge()
        self.assertEqual(gj.EXIT_PASS, code)
        item = self.recorded(report, "F9")
        self.assertEqual("no_data", item["verdict"])
        self.assertIn("매핑하지 못했다", item["parts"][0]["note"])

    def test_missing_synthetic_value_in_one_seed_is_no_data(self) -> None:
        metric(self.realism[50], "F5")["synthetic"]["nbd_shape"] = None
        metric(self.realism[50], "F5")["verdict"] = "no_data"  # realism_check 가 계산하지 못한 경우의 모양
        _, report, _, _ = self.run_judge()
        item = self.recorded(report, "F5")
        self.assertEqual("no_data", item["verdict"])
        self.assertIn("seed [50]", item["parts"][0]["note"])

    def test_missing_value_that_realism_judged_fail_is_a_fail_not_no_data(self) -> None:
        # F5 과소분산: realism_check 는 r = inf 를 nbd_shape=None 으로 싣고 verdict 를 fail 로 낸다.
        under = metric(self.realism[49], "F5")
        under["synthetic"]["nbd_shape"] = None
        under["verdict"] = "fail"
        under["note"] = "12주 주문 수의 분산이 평균 이하(과소분산) — 구매율 이질성이 없다는 뜻이다."
        code, report, out, _ = self.run_judge()
        self.assertEqual(gj.EXIT_PASS, code)  # 기록 검사라 종료 코드는 그대로
        item = self.recorded(report, "F5")
        self.assertEqual("fail", item["verdict"])
        part = item["parts"][0]
        self.assertEqual("fail", part["verdict"])
        self.assertIsNone(part["mean"])
        self.assertIn("seed [49]", part["note"])
        self.assertIn("과소분산", part["note"])
        self.assertIn("| F5 | nbd_shape |", out)

    def test_multi_part_item_takes_the_worst_part(self) -> None:
        for report in self.realism.values():
            metric(report, "F1")["synthetic"]["p75"] = 23.0  # 띠 [12, 20] · 경계 24 이내
        _, report, _, _ = self.run_judge()
        item = self.recorded(report, "F1")
        self.assertEqual("borderline", item["verdict"])
        self.assertEqual({"median": "pass", "mean": "pass", "p75": "borderline"},
                         {p["key"]: p["verdict"] for p in item["parts"]})


class TestOutputs(JudgeCase):
    def test_markdown_file_matches_stdout(self) -> None:
        out_md = self.tmp / "md" / "judge.md"
        code, _, out, _ = self.run_judge("--out-md", str(out_md))
        self.assertEqual(gj.EXIT_PASS, code)
        self.assertEqual(out, out_md.read_text(encoding="utf-8"))
        self.assertIn("pending", out)  # 기준이 확정 전이면 표에 드러난다

    def test_pending_is_flagged_in_the_header_and_carried_verbatim_in_json(self) -> None:
        # 정책(pending 이어도 종료 0)은 리드 확인 대기 — 바꾸지 않고, 드러나게만 한다.
        code, report, out, _ = self.run_judge()
        self.assertEqual(gj.EXIT_PASS, code)
        self.assertEqual("lead_confirmation_treatment_population", report["criteria"]["pending"])
        head = out.split("## 필수 검사")[0]
        self.assertIn("★ 기준 파일 pending: `lead_confirmation_treatment_population`", head)

    def test_without_pending_the_json_says_null_and_no_star(self) -> None:
        del self.criteria["pending"]
        code, report, out, _ = self.run_judge()
        self.assertEqual(gj.EXIT_PASS, code)
        self.assertIn("pending", report["criteria"])
        self.assertIsNone(report["criteria"]["pending"])
        self.assertNotIn("★", out)

    def test_json_output_is_strict_json(self) -> None:
        _, _, _, _ = self.run_judge()
        text = (self.tmp / "out" / "judge.json").read_text(encoding="utf-8")
        json.loads(text, parse_constant=lambda name: self.fail(f"비표준 JSON 상수 {name}"))

    def test_inputs_are_paired_by_seed_in_the_json_not_by_file_name(self) -> None:
        _, report, _, _ = self.run_judge()
        for seed, path in report["inputs"]["guardrail"].items():
            self.assertEqual(int(seed), json.loads(Path(path).read_text(encoding="utf-8"))["seed"])
        for seed, path in report["inputs"]["realism"].items():
            source = json.loads(Path(path).read_text(encoding="utf-8"))["source"]
            self.assertEqual(seed, source["random_seed"])


class TestMissingPyYAML(unittest.TestCase):
    """PyYAML 이 없으면 필수 실패(1)와 같은 값이 아니라 내부 오류(3)로 끝난다 — 의존성 없이 돈다(skip 없음)."""

    def test_missing_pyyaml_exits_with_internal_error(self) -> None:
        import subprocess

        # sys.modules["yaml"] = None 이면 `import yaml` 이 ImportError 를 낸다 — 설치 여부와 무관하게 미설치를 흉내 낸다.
        code = (
            "import runpy, sys; sys.modules['yaml'] = None; "
            f"sys.argv = ['gate1_judge.py', '--guardrail', 'absent', '--realism', 'absent']; "
            f"runpy.run_path({str(SCRIPT)!r}, run_name='__main__')"
        )
        done = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, timeout=60)
        self.assertEqual(3, done.returncode, done.stderr)
        self.assertIn("PyYAML 미설치", done.stderr)
        self.assertIn("통과가 아니다", done.stderr)
        self.assertEqual("", done.stdout)


@unittest.skipUnless(HAVE_YAML, NEEDS_YAML)
class TestCriteriaPathsResolveInRealConfig(unittest.TestCase):
    def test_band_from_paths_exist_in_simulator_config(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        criteria_path = Path(tmp.name) / "criteria.yaml"
        criteria_path.write_text(yaml.safe_dump(criteria_fixture(), allow_unicode=True), encoding="utf-8")
        criteria = gj.load_criteria(criteria_path)
        bands = gj.load_bands(criteria, gj.DEFAULT_SIMULATOR_CONFIG)
        self.assertEqual(set(BAND_CHECKS), set(bands))
        self.assertEqual((500, 2000), bands["coupon_use_T2"])


@unittest.skipUnless(HAVE_YAML and HAVE_PANDAS, NEEDS_PANDAS if HAVE_YAML else NEEDS_YAML)
class TestJudgeMatchesRealismCheck(unittest.TestCase):
    """판정 함수를 다시 구현했으므로 realism_check 원본과 같은 결과인지 경계 근처 값으로 대조한다."""

    BANDS = [(5, 10), (0.45, 0.70), (300, 600), (-50, 50), (0, 0.5), (None, 10), (5, None), (0, None)]

    def values(self, lo, hi) -> list:
        points = [None, float("nan"), 0, 0.0, -1, 1e9]
        for bound in (lo, hi):
            if bound is None:
                continue
            delta = 0.2 * abs(bound)
            points += [bound, bound - 1e-9, bound + 1e-9, bound - delta, bound + delta,
                       bound - delta - 1e-9, bound + delta + 1e-9, bound * 0.9, bound * 1.1]
        return points

    def test_judge(self) -> None:
        for lo, hi in self.BANDS:
            for value in self.values(lo, hi):
                self.assertEqual(rc.judge(value, lo, hi), gj.judge(value, lo, hi), (value, lo, hi))

    def test_judge_open_lower(self) -> None:
        for lo in (1.0, 0.0, 5, -2):
            for value in self.values(lo, None):
                self.assertEqual(rc.judge_open_lower(value, lo), gj.judge_open_lower(value, lo), (value, lo))

    def test_worst(self) -> None:
        cases = [[], ["pass"], ["pass", "borderline"], ["borderline", "fail"], ["fail", "no_data"], ["pass", "pass"]]
        for verdicts in cases:
            self.assertEqual(rc.worst(verdicts), gj.worst(verdicts), verdicts)

    def test_open_band_rule_matches_bands_table(self) -> None:
        # 한쪽 열린 띠를 judge_open_lower 로 판정하는 규칙이 realism_check BANDS 의 열린 띠와 같은 항목에 걸린다.
        open_lower = {fid for fid, band in rc.BANDS.items() if isinstance(band, list) and band[1] is None}
        self.assertEqual({"F8", "F13", "F17"}, open_lower)
        recorded_band_keys = {
            fid: (set(band) if isinstance(band, dict) else {None})
            for fid, band in rc.BANDS.items() if fid in gj.SYNTHETIC_KEYS
        }
        for fid, keys in recorded_band_keys.items():
            self.assertEqual(keys, set(gj.SYNTHETIC_KEYS[fid]), fid)


def minimal_world() -> dict:
    """realism_check 계산기가 모두 synthetic 을 만드는 데 필요한 최소 입력(이벤트 · 교환 묶음 · 배정 · 4분면).

    값의 현실성은 보지 않는다 — 계산기가 no_data 로 빠지기 전에 synthetic 딕셔너리를 만드는 경로에 들어가게만 한다.
    고객 40명(그중 10명은 관측 시작 30일 뒤 가입한 신규) · 315일 · 주문마다 add_to_cart + purchase 세션,
    세 번에 한 번 장바구니만 남긴 세션, 180일째 T0 · T2 · T3 배정과 쿠폰 사용.
    """
    start = pandas.Timestamp("2025-01-01", tz=rc.TZ)
    stamp = lambda day, hour=12: (start + pandas.Timedelta(days=day, hours=hour)).isoformat()
    events, orders, items, customers = [], [], [], []
    arm_of = {}
    assign_day = 180
    for i in range(40):
        cid = f"c{i:02d}"
        new = i >= 30
        customers.append({"customer_id": cid, "signup_date": "2025-01-31" if new else "2024-06-01"})
        arm_of[cid] = ("T0", "T2", "T3")[i % 3]
        gap = 3 + (i % 10) * 2
        day, k = (31 + i % 7) if new else i % 7, 0
        coupon_spent = False
        while day < 315:
            oid, sid = f"o{i:02d}-{k}", f"s{i:02d}-{k}"
            amount = 30000 + (i * 7919 + k * 104729) % 30000
            events.append({"customer_id": cid, "timestamp": stamp(day, 10), "event_type": "add_to_cart", "session_id": sid})
            events.append({"customer_id": cid, "timestamp": stamp(day, 11), "event_type": "purchase", "session_id": sid,
                           "order_id": oid, "order_amount": amount})
            if day >= assign_day and arm_of[cid] != "T0" and not coupon_spent:
                events.append({"customer_id": cid, "timestamp": stamp(day, 11), "event_type": "coupon_use",
                               "session_id": sid, "order_id": oid, "coupon_id": f"cp-{cid}"})
                coupon_spent = True
            if k % 3 == 0:
                events.append({"customer_id": cid, "timestamp": stamp(day, 20), "event_type": "add_to_cart",
                               "session_id": f"{sid}-abandoned"})
            orders.append({"order_id": oid, "customer_id": cid, "ordered_at": stamp(day, 11)})
            items += [{"order_id": oid, "product_id": f"p{(i + k) % 3}"}, {"order_id": oid, "product_id": f"p{k % 5}"}]
            day, k = day + gap, k + 1
    events.append({"customer_id": "c00", "timestamp": stamp(0, 1), "event_type": "page_view", "session_id": "edge-a"})
    events.append({"customer_id": "c00", "timestamp": stamp(314, 23), "event_type": "page_view", "session_id": "edge-b"})
    assignments = pandas.DataFrame(
        [{"customer_id": cid, "treatment_id": arm, "assigned_at": start + pandas.Timedelta(days=assign_day)}
         for cid, arm in arm_of.items()],
        columns=["customer_id", "treatment_id", "assigned_at"],
    )
    exchange = {"orders": pandas.DataFrame(orders), "order_items": pandas.DataFrame(items),
                "customers": pandas.DataFrame(customers)}
    quadrants = {"T3": {"persuadable_bp": 1500, "sleeping_dog_bp": 1000, "sure_thing_bp": 5000,
                        "lost_cause_bp": 2500, "ate_bp": 500}}
    return {"events": pandas.DataFrame(events), "exchange": exchange, "assignments": assignments,
            "guardrail": {"potential_outcome_quadrants": quadrants}}


@unittest.skipUnless(HAVE_YAML and HAVE_PANDAS, NEEDS_PANDAS_CALC if HAVE_YAML else NEEDS_YAML)
class TestSyntheticKeysMatchRealismCalculators(unittest.TestCase):
    """판정 스크립트가 읽는 synthetic 키가 현재 realism_check 계산기(`CALCULATORS`)가 내는 키와 같다.

    저장소 예시 JSON 은 옛 실행 출력이라 계산기가 키 이름을 바꿔도 예시 기반 테스트는 통과한다 — 여기서 실제로 돌려 막는다.
    """

    @classmethod
    def setUpClass(cls) -> None:
        world = minimal_world()
        ctx = rc.build_context(world["events"], exchange=world["exchange"], assignments=world["assignments"],
                               guardrail=world["guardrail"])
        cls.results = {fid: rc.CALCULATORS[fid](ctx) for fid in rc.CALCULATORS}

    def synthetic(self, fid: str) -> dict:
        result = self.results[fid]
        self.assertIsInstance(result.synthetic, dict, (fid, result.verdict, result.note))
        return result.synthetic

    def test_recorded_mapping_keys_are_emitted_by_the_calculators(self) -> None:
        for fid, mapping in gj.SYNTHETIC_KEYS.items():
            with self.subTest(fact=fid):
                emitted = self.synthetic(fid)
                for synthetic_key in mapping.values():
                    self.assertIn(synthetic_key, emitted)

    def test_reference_keys_are_emitted_by_the_calculators(self) -> None:
        for fid, keys in gj.REFERENCE_REALISM_KEYS.items():
            with self.subTest(fact=fid):
                emitted = self.synthetic(fid)
                for key in keys:
                    self.assertIn(key, emitted)

    def test_every_recorded_fact_is_a_calculator(self) -> None:
        self.assertLessEqual(set(RECORDED), set(rc.CALCULATORS))
        self.assertEqual(set(RECORDED), set(gj.SYNTHETIC_KEYS))


@unittest.skipUnless(HAVE_YAML, NEEDS_YAML)
class TestAgainstRealGuardrailReport(JudgeCase):
    """실제 `guardrails` CLI 출력이 판정 입력으로 받아들여진다 — 검사 이름 · 필드 · seed 키 · 실행 조건 키가 맞는지."""

    def run_cli(self, *extra: str) -> Path:
        import src.simulator.__main__ as cli

        hidden = self.tmp / "hidden"
        with contextlib.redirect_stdout(io.StringIO()):
            code = cli.main([
                "guardrails", "--seed", "2", "--customers", "150", "--warmup-days", "90",
                "--output-root", str(self.tmp / "world"), "--hidden-root", str(hidden), *extra,
            ])
        self.assertEqual(cli.EXIT_OK, code)
        guard_dir = hidden / "ground_truth" / "guardrails"
        version = json.loads(next(guard_dir.glob(gj.GUARDRAIL_GLOB)).read_text(encoding="utf-8"))["simulator_version"]
        # --profile 을 주지 않았으므로 CLI 기본값(small)이다.
        self.criteria = criteria_fixture(seeds=[2], customers=150, profile="small", warmup_days=90)
        self.realism = {2: realism_report(2)}
        self.realism[2]["source"]["simulator_version"] = version
        return guard_dir

    def test_cli_report_is_accepted_and_carries_quadrant_consistency_names(self) -> None:
        guard_dir = self.run_cli()
        code, report, _, err = self.run_judge(guardrail=[str(guard_dir)])
        self.assertIn(code, (gj.EXIT_PASS, gj.EXIT_FAIL), err)
        for name in CONSISTENCY_CHECKS:
            self.assertEqual("pass", self.required(report, name)["verdict"])  # 구조적으로 0

    def test_cli_sampled_report_is_refused_under_full_evaluation(self) -> None:
        guard_dir = self.run_cli("--sample", "5")
        self.assert_input_error("evaluated_customers 5 ≠", guardrail=[str(guard_dir)])
