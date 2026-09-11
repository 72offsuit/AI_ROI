"""`config_loader.py` 검사 — YAML 로딩과 **타입 봉쇄** (이슈 #47 AC-1 · EC-9).

★ **PyYAML 이 없으면 로딩 테스트가 skip 된다.** skip 은 통과가 아니다 —
`unittest` 가 exit 0 을 내므로 사유 없이 넘기면 검증하지 않은 것이 검증한 것처럼
보인다. 각 skip 에 `BLOCKED:` 사유를 붙이고, PR 에 skip 수와 사유를 함께 적는다.

**타입 봉쇄 검사(`TestTypeContainment`)는 skip 되지 않는다.** dataclass 속성의
유무는 PyYAML 과 무관하고, 그것이 EC-9 의 회귀 테스트이므로 항상 돌아야 한다.

실행:
    python3 -m unittest tests.test_config_loader -v
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from src.measurement import config_loader as cl
from src.measurement.errors import ConfigError

REPO_ROOT = Path(__file__).resolve().parents[1]
REAL_CONFIG = REPO_ROOT / "config" / "economic_config.yaml"

NEEDS_YAML = "BLOCKED: PyYAML 미설치 — config 로딩 경로를 검증하지 않았다"


class TestTypeContainment(unittest.TestCase):
    """EC-9 — `economics.py` 가 받는 객체에 원가율이 **없다**.

    이것이 "규율이 아니라 구조로 막는다"의 회귀 테스트다. 누군가 편의를 위해
    `CostAccountingConfig` 에 카테고리를 합치면 여기서 실패한다.
    """

    def test_cost_accounting_has_no_cost_rate_attribute(self) -> None:
        fields = set(cl.CostAccountingConfig.__dataclass_fields__)
        leaked = fields & {"categories", "product_margin", "cost_rate", "margin_rate"}
        self.assertEqual(
            set(), leaked,
            "CostAccountingConfig 에 원가율 계열 필드가 있다. economics.py 가 그것을 "
            f"읽을 수 있게 되면 EC-1(추정 COGS)로 가는 문이 열린다: {sorted(leaked)}",
        )

    def test_cost_rate_lives_only_in_product_generation(self) -> None:
        self.assertIn("cost_rate", cl.CategorySpec.__dataclass_fields__)
        self.assertIn("categories", cl.ProductGenerationConfig.__dataclass_fields__)

    def test_two_configs_are_not_merged(self) -> None:
        """`EconomicConfig` 가 두 조각을 **따로** 들고 있다. 합쳐 주지 않는다."""
        fields = set(cl.EconomicConfig.__dataclass_fields__)
        self.assertEqual({"version", "cost_accounting", "product_generation"}, fields)


class TestGuardedImport(unittest.TestCase):
    def test_yaml_available_reports_reality(self) -> None:
        """`sink.parquet_available()` 과 같은 guarded 패턴이다."""
        try:
            import yaml  # noqa: F401
        except ImportError:
            self.assertFalse(cl.yaml_available())
        else:
            self.assertTrue(cl.yaml_available())

    def test_loading_without_yaml_raises_config_error(self) -> None:
        """PyYAML 이 없으면 **자체 파서로 폴백하지 않고** 멈춘다.

        부분 구현 파서는 조용히 다른 값을 읽고, 경제 규칙에서 그것은 기여이익이
        조용히 틀리는 결과가 된다.
        """
        if cl.yaml_available():
            self.skipTest("PyYAML 이 설치되어 있어 이 경로를 탈 수 없다")
        with self.assertRaises(ConfigError) as caught:
            cl.load_economic_config(REAL_CONFIG)
        self.assertIn("PyYAML", str(caught.exception))


@unittest.skipUnless(cl.yaml_available(), NEEDS_YAML)
class TestLoadRealConfig(unittest.TestCase):
    """저장소의 실제 `config/economic_config.yaml` 을 읽는다."""

    def setUp(self) -> None:
        self.config = cl.load_economic_config(REAL_CONFIG)

    def test_version_is_present(self) -> None:
        self.assertTrue(self.config.version)

    def test_category_keys_match_schema_enum(self) -> None:
        """US-2 인수조건 4 — config 키가 `Category` Enum 과 같은 어휘다.

        어긋나면 시뮬레이터가 만든 카테고리와 계약이 받는 카테고리가 달라지고,
        그 불일치는 데이터가 쌓인 뒤에 드러난다.
        """
        from src.measurement.schema import Category

        self.assertEqual(
            {item.value for item in Category},
            set(self.config.product_generation.categories),
        )

    def test_five_treatments_with_occurrence_points(self) -> None:
        self.assertEqual(
            {"T0", "T1", "T2", "T3", "T4"}, set(self.config.cost_accounting.treatment_cost)
        )
        # occurs_at 이 EC-3 발생주의의 핵심이다 — 같은 금액이라도 시점이 다르다.
        self.assertEqual(
            "coupon_used", self.config.cost_accounting.treatment_occurs_at["T3"]
        )
        self.assertEqual(
            "message_sent", self.config.cost_accounting.treatment_occurs_at["T4"]
        )

    def test_refund_assumption_is_recorded_as_false(self) -> None:
        """A-REFUND — 가정이 config 에 있어야 게시물 notices 로 나를 수 있다."""
        self.assertIs(False, self.config.cost_accounting.assumptions["refund_adjusted"])

    def test_ai_investment_is_marked_as_estimate(self) -> None:
        """AC-1 — AI 투자비용이 가정 기반 추정치임이 데이터에 남는다.

        주석만으로는 부족하다. 코드가 읽을 수 있어야 게시물이 그 사실을 나른다.
        """
        investment = self.config.cost_accounting.ai_investment
        self.assertIs(True, investment.is_estimate)
        self.assertTrue(investment.estimate_note.strip())

    def test_frequency_weights_sum_to_one(self) -> None:
        categories = self.config.product_generation.categories.values()
        self.assertAlmostEqual(
            1.0, sum(c.frequency_weight for c in categories), places=6,
            msg="빈도 가중 합이 1 이 아니다",
        )

    def test_weighted_contribution_margin_is_26_percent(self) -> None:
        """`economic-rule-v1.md` §2 의 "가중평균 기여마진율 26.0%" 를 검산한다.

        ★ **가중 기준이 매출이다** — 빈도가 아니다. 이 구분을 실행으로 확인했다:

            빈도 가중  Σ(margin × frequency)                        = 26.58%
            매출 가중  Σ(margin × price × freq) / Σ(price × freq)   = 26.00%  ← 문서값

        1차 구현에서 빈도 가중으로 짰다가 26.58% 가 나왔고, 문서가 틀렸다고
        판단할 뻔했다. 문서가 맞다 — 혼합 기여마진율은 매출 가중이 경제적으로
        옳은 정의이기도 하다(단가가 높은 카테고리가 마진 총액에 더 기여한다).
        **가중 기준을 적지 않은 요약값은 검산할 때 두 답을 준다.**
        """
        categories = self.config.product_generation.categories.values()
        revenue_weight = sum(c.median_price_krw * c.frequency_weight for c in categories)
        weighted = (
            sum(
                c.margin_rate * c.median_price_krw * c.frequency_weight
                for c in categories
            )
            / revenue_weight
        )
        self.assertAlmostEqual(0.260, weighted, places=3)

    def test_pool_size_totals_240(self) -> None:
        total = sum(c.pool_size for c in self.config.product_generation.categories.values())
        self.assertEqual(240, total)

    def test_cost_and_margin_rates_sum_to_one(self) -> None:
        for key, spec in self.config.product_generation.categories.items():
            with self.subTest(category=key):
                self.assertAlmostEqual(1.0, spec.cost_rate + spec.margin_rate, places=6)


@unittest.skipUnless(cl.yaml_available(), NEEDS_YAML)
class TestConfigErrors(unittest.TestCase):
    """부재·파싱 실패·필수 키 누락이 전부 `ConfigError` 다. 기본값으로 채우지 않는다."""

    def _write(self, text: str) -> Path:
        tmp = tempfile.NamedTemporaryFile(
            "w", suffix=".yaml", delete=False, encoding="utf-8"
        )
        tmp.write(text)
        tmp.close()
        self.addCleanup(lambda: Path(tmp.name).unlink(missing_ok=True))
        return Path(tmp.name)

    def test_missing_file_names_the_path_and_the_fix(self) -> None:
        """NFR-006 — 메시지가 무엇이·왜·무엇을 하면 되는가 셋을 담는다."""
        missing = REPO_ROOT / "config" / "does_not_exist.yaml"
        with self.assertRaises(ConfigError) as caught:
            cl.load_economic_config(missing)
        message = str(caught.exception)
        self.assertIn("does_not_exist.yaml", message, "무엇이 — 경로")
        self.assertIn("계산할 수 없다", message, "왜 — 영향")
        self.assertIn("확인", message, "무엇을 하면 되는가")

    def test_unparsable_yaml_raises(self) -> None:
        path = self._write("version: [unclosed\n")
        with self.assertRaises(ConfigError):
            cl.load_economic_config(path)

    def test_missing_required_key_raises_and_lists_present_keys(self) -> None:
        """기본값으로 대체하지 않는다 — 결손을 조용히 0 으로 채우는 것과 같다."""
        path = self._write("version: v1\ntreatment_cost: {}\n")
        with self.assertRaises(ConfigError) as caught:
            cl.load_economic_config(path)
        self.assertIn("필수 키", str(caught.exception))

    def test_non_mapping_root_raises(self) -> None:
        path = self._write("- just\n- a\n- list\n")
        with self.assertRaises(ConfigError):
            cl.load_economic_config(path)

    def test_zero_amortization_does_not_divide(self) -> None:
        """상각 월수 0 을 0 이나 inf 로 흘려보내지 않는다."""
        investment = cl.AiInvestmentConfig(
            model_development_cost_krw=1, compute_cost_krw=1,
            model_operating_cost_krw_per_month=1, monitoring_cost_krw_per_month=1,
            amortization_months=0, is_estimate=True, estimate_note="x",
        )
        with self.assertRaises(ConfigError):
            investment.monthly_amortized_krw()


if __name__ == "__main__":
    unittest.main()
