"""Catches a config value that nothing reads (issue #63, review finding M8).

`cost_accounting.discount_cost_krw: 7000` sat in `config/economic_config.yaml`,
was loaded as a required field, and was **read by nothing**. Anyone opening the
config believed it drove discount accounting. It did not -- decision D-16 derives
discount from `treatment_cost` instead, so the constant was both dead and a
duplicate of `treatment_cost.T3.unit_cost_krw`. Change one and the config
contradicts itself in silence.

★ Why the obvious check would have missed it. "Is every config key loaded?" --
  `discount_cost_krw` *was* loaded, by `_require()`, which is what made it look
  alive. The gap is one step further in: **loaded into the dataclass, then never
  read by anything.** So this file walks the dataclass fields and looks for an
  attribute read of each.

★ Counting reads, not mentions. A field's declaration (`x: int`) and the kwarg
  that fills it (`x=_require(...)`) are writes; only `<expr>.x` is a read. That
  distinction is the whole test -- count the kwarg and every field is alive
  forever. It is also why `config_loader.py` is scanned rather than skipped: the
  first pass here excluded it wholesale and reported three `AiInvestmentConfig`
  fields as dead, when `monthly_amortized()` reads all three. Excluding the
  defining file looks tidy and produces false positives.

★ Why an exemption table instead of a smaller rule. Two fields legitimately have
  no production reader today, and they are not the same thing as each other.
  Writing the rule loosely enough to let them pass would let the next dead value
  through too. Each exemption states why it is there and what would retire it, and
  `test_exemptions_are_exactly_declared` fails when a new one appears -- so the
  table cannot quietly grow.

What this does NOT check: whether a value that *is* read is read **correctly**.
`treatment_occurs_at` is the live example -- the config declares when each cost
accrues, production code implements the same rule structurally, and nothing
compares the two. That is a declaration without a comparison device, the shape
this cycle kept finding, and it is recorded below rather than papered over.
"""

from __future__ import annotations

import ast
import unittest
from pathlib import Path

from src.measurement.config_loader import (
    AiInvestmentConfig,
    CostAccountingConfig,
    ProductGenerationConfig,
)

MEASUREMENT = Path(__file__).resolve().parent.parent / "src" / "measurement"

#: Fields with no production reader, and why that is not a defect *yet*.
#: The value is what would remove the entry -- an exemption with no exit is a
#: permanent hole.
EXEMPT: dict[str, str] = {
    "treatment_occurs_at": (
        "EC-3 발생 시점 선언 (T1=purchase · T2/T3=coupon_use · T4=push_sent). "
        "economics.py 는 같은 규칙을 구조로 구현하고 이 값을 읽지 않는다. "
        "★ 이슈 #97 이 **대조 장치를 붙였다** — config_loader 가 로딩 시 "
        "EventType 실재 여부를 거부하고, tests/test_treatment_accrual.py 가 "
        "economics.py 의 source_event_types 와 맞댄다. 이제 이 값은 죽은 값이 "
        "아니라 **검증되는 선언**이다. 남은 것은 생산 코드 소비자가 없다는 "
        "사실뿐이고, 그것은 오해를 낳지 않는다. "
        "해소: 계산이 이 값을 읽게 될 때 (지금 그렇게 만들면 요청받지 않은 "
        "추상화다 — 처치는 5종이고 계상 규칙이 바뀔 요구가 없다)"
    ),
    "categories": (
        "ProductGenerationConfig — 소비자가 아직 없다. 상품 pool 생성 파라미터이며 "
        "시뮬레이터(C2 태스크 S2·S3)가 읽는다. ★ economics.py 가 읽으면 EC-1 위반이다 "
        "— 원가율로 COGS 를 추정하면 contribution_profit 이 revenue 의 상수배가 되어 "
        "revenue_up_profit_down 가드레일이 원리적으로 발동할 수 없게 된다. "
        "해소: 시뮬레이터 구현이 이 값을 읽는다"
    ),
}


def _readers(name: str) -> list[str]:
    """`<expr>.name` 속성 **읽기**를 찾는다. 선언과 생성 kwarg 는 쓰기이므로 세지 않는다.

    ★ 기준은 이 함수 하나다. 본 검사와 면제표 대조가 서로 다른 기준을 쓰면
      둘이 어긋나고, 실제로 처음에 그렇게 만들어 면제표가 거짓 양성 3건을
      냈다. 두 곳이 같은 질문을 물어야 대조가 성립한다.
    """
    hits: list[str] = []
    for path in sorted(MEASUREMENT.glob("*.py")):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if isinstance(node, ast.Attribute) and node.attr == name:
                hits.append(f"{path.name}:{node.lineno}")
    return hits


class TestEveryConfigFieldIsRead(unittest.TestCase):
    """설정 필드마다 읽는 곳이 있는가."""

    CLASSES = (CostAccountingConfig, AiInvestmentConfig, ProductGenerationConfig)

    def test_no_dead_config_field(self) -> None:
        dead = []
        for cls in self.CLASSES:
            for name in cls.__dataclass_fields__:
                if name in EXEMPT:
                    continue
                if not _readers(name):
                    dead.append(f"{cls.__name__}.{name}")
        self.assertEqual(
            [], dead,
            "읽는 곳이 없는 설정 필드다. 설정 파일을 여는 사람은 이 값이 쓰인다고 "
            f"믿는다: {dead}\n지우거나, 왜 아직 소비자가 없는지 EXEMPT 에 적는다",
        )

    def test_exemptions_are_exactly_declared(self) -> None:
        """★ 면제표가 조용히 자라지 않게 한다.

        새 필드가 읽히지 않으면 위 테스트가 실패하고, 누군가 EXEMPT 에 넣어
        지나갈 수 있다. 그때 이 테스트가 **면제가 늘었다**고 말한다.
        """
        actual = {
            name
            for cls in self.CLASSES
            for name in cls.__dataclass_fields__
            if not _readers(name)
        }
        self.assertEqual(
            set(EXEMPT), actual,
            "면제 목록과 실제로 읽히지 않는 필드가 어긋난다.\n"
            f"  면제에만 있음(이제 읽힌다 → 항목을 지운다): {set(EXEMPT) - actual}\n"
            f"  실제에만 있음(새 죽은 값): {actual - set(EXEMPT)}",
        )

    def test_every_exemption_says_why(self) -> None:
        """사유 없는 면제는 다음 사람이 근거 없이 늘린다."""
        for name, why in EXEMPT.items():
            with self.subTest(field=name):
                self.assertGreater(
                    len(why.strip()), 40, f"{name}: 사유가 너무 짧다",
                )
                self.assertIn("해소", why, f"{name}: 무엇이 이 면제를 없애는지가 없다")


class TestDiscountIsDerivedNotStored(unittest.TestCase):
    """★ #63 의 회귀 — 상수를 되살리면 같은 모순이 돌아온다."""

    def test_cost_accounting_has_no_discount_constant(self) -> None:
        self.assertNotIn(
            "discount_cost_krw", CostAccountingConfig.__dataclass_fields__,
            "할인 비용은 D-16 유도 규칙이 treatment_cost 에서 구한다. 상수를 두면 "
            "T3 의 7,000원과 같은 값이 두 곳에 있게 되고, 한쪽만 고치면 config 가 "
            "스스로 모순된다",
        )

    def test_the_derivation_rule_is_still_declared(self) -> None:
        """상수를 지운 자리에 유도 규칙이 남아 있어야 한다 — 둘 다 없으면 규칙이 사라진 것이다."""
        text = (MEASUREMENT.parent.parent / "config" / "economic_config.yaml").read_text(
            encoding="utf-8"
        )
        self.assertIn("discount_derived_from_treatment: true", text)
        self.assertIn("coupon_treatments:", text)


class TestTheScanActuallyFinds(unittest.TestCase):
    """★ 음성 대조 — 스캐너가 아무것도 못 찾으면 위 테스트는 전부 공허하다."""

    def test_scan_finds_a_known_live_field(self) -> None:
        self.assertTrue(
            _readers("message_cost_krw"),
            "살아 있는 것이 확실한 필드를 못 찾았다 — 스캐너가 고장났다",
        )

    def test_scan_finds_nothing_for_the_removed_field(self) -> None:
        self.assertEqual([], _readers("discount_cost_krw"))

    def test_scan_would_catch_a_dead_field(self) -> None:
        """실제로 죽은 이름을 넣으면 0 건이 나오는가."""
        self.assertEqual([], _readers("totally_unused_field_name_xyz"))
