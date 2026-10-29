"""#194 — 가드레일 판정 모집단(DR-194, 역할별 분리).

이탈률은 ① 직전 42일 구매 고객, 처치 지표(ATE · 쿠폰 · 4분면)는 ② data_spec §4.1 eligible 로 판정한다.
결과 JSON 최상위 값이 판정값이고, 판정하지 않는 쪽은 `role: 참고` 검사로 남는다.
"""

from __future__ import annotations

import contextlib
import io
import json

import src.simulator.__main__ as cli
from tests.test_simulator_support import SimulatorCase

TREATMENT_KEYS = ("ate_bp", "ate_net_profit_krw", "coupon_use_bp", "potential_outcome_quadrants", "response_mix_bp")


class TestGuardrailPopulations(SimulatorCase):
    def setUp(self) -> None:
        super().setUp()
        self.out = io.StringIO()
        with contextlib.redirect_stdout(self.out):
            code = cli.main([
                "guardrails", "--seed", "2", "--customers", "150", "--warmup-days", "90",
                "--output-root", str(self.fresh_root("guardrails")), "--hidden-root", str(self.hidden),
            ])
        self.assertEqual(cli.EXIT_OK, code)
        root = self.hidden / "ground_truth" / "guardrails"
        (path,) = sorted(root.glob("guardrails-*.json"))
        self.report = json.loads(path.read_text(encoding="utf-8"))
        self.outcome_files = sorted(p.name for p in root.glob("*-potential-outcomes-*.jsonl"))

    def test_top_level_judges_churn_on_active42_and_treatment_on_eligible(self) -> None:
        report = self.report
        self.assertEqual(report["active42"]["churn_rate_bp"], report["churn_rate_bp"])
        for key in TREATMENT_KEYS:
            self.assertEqual(report["eligible_spec41"][key], report[key], key)
        # 블록의 처치 지표 키가 하나도 빠짐없이 최상위에 있다(손으로 고른 목록에 기대지 않는다).
        treatment_keys = set(report["eligible_spec41"]) - {"customers", "evaluated_customers", "churn_rate_bp"}
        self.assertTrue(set(TREATMENT_KEYS) <= treatment_keys)
        for key in treatment_keys:
            self.assertEqual(report["eligible_spec41"][key], report[key], key)
        self.assertEqual(report["active_customers"], report["active42"]["customers"])
        self.assertEqual(report["eligible_customers"], report["eligible_spec41"]["customers"])

    def test_each_check_is_judged_on_exactly_one_population(self) -> None:
        checks = {c["name"]: c for c in self.report["checks"]}
        judged = {name for name, c in checks.items() if c["role"] == "판정"}
        self.assertIn("churn_rate", judged)
        for arm in ("T1", "T2", "T3", "T4"):
            for prefix in ("ate", "sleeping_dog", "persuadable", "identity"):
                self.assertIn(f"{prefix}_{arm}", judged)
                self.assertEqual("참고", checks[f"active42_{prefix}_{arm}"]["role"])
        self.assertEqual("참고", checks["spec41_churn_rate"]["role"])
        self.assertNotIn("active42_churn_rate", checks)
        self.assertFalse({n for n in judged if n.startswith(("active42_", "spec41_"))})
        quadrant = self.report["potential_outcome_quadrants"]["T3"]
        self.assertEqual(quadrant["ate_bp"], checks["ate_T3"]["value_bp"])
        self.assertEqual(self.report["churn_rate_bp"], checks["churn_rate"]["value_bp"])

    def test_both_populations_keep_their_counterfactual_rows_and_the_table_shows_roles(self) -> None:
        self.assertEqual(2, len(self.outcome_files))
        self.assertTrue(any(name.endswith("-active42.jsonl") for name in self.outcome_files))
        self.assertTrue(any(name.endswith("-eligible_spec41.jsonl") for name in self.outcome_files))
        text = self.out.getvalue()
        self.assertIn("§4.1 eligible", text)
        self.assertIn("판정", text)
        self.assertIn("참고", text)
