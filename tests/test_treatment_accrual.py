"""Compares the declared accrual moment against what the code actually accrues on.

Issue #97. `config/economic_config.yaml` says, per treatment, *when* its cost is
incurred -- `occurs_at`. EC-3 calls that the core of accrual accounting: the same
3,000 won is incurred at order time for `T1` and at coupon-use time for `T2`, and
if the coupon is never used that cost is **not zero, it does not happen.**

Two things were wrong, and the second is the one this file exists for:

  1. the declared values were `order_placed` · `coupon_used` · `message_sent`,
     and **none of the three is an `event_type`.** The schema has `purchase`,
     `coupon_use`, `push_sent`. The intent was readable, but anyone wiring
     anything off those names would look for events that do not exist.
  2. **nothing compared the declaration to the implementation.** `economics.py`
     implements the same rule structurally -- `coupon_used_orders`,
     `has_coupon_use`, counting `push_sent` -- and never reads `occurs_at`. Change
     the config from `coupon_use` to `purchase` and no computation changes: the
     config would simply be lying.

(1) is now refused at load time by `config_loader._checked_occurs_at`. (2) is this
file. Neither replaces the other -- a real event name can still be the wrong one.

★ The mapping treatment → accruing function lives here, in the test, rather than
  in the config. Putting it in the config would add a field that nothing reads,
  which is the defect issue #63 closed. And making `economics.py` read `occurs_at`
  to drive a branch would be an abstraction nobody asked for: there are five
  treatments and the accrual rule is not expected to vary. What was missing was
  never indirection, it was a comparison.

★ `test_every_treatment_is_mapped` is what keeps the mapping honest. A sixth
  treatment added to the config with no entry here would otherwise be silently
  unchecked -- the declaration would go back to being unverified for that one.
"""

from __future__ import annotations

import ast
import unittest
from pathlib import Path

from src.measurement import schema as sc
from src.measurement.config_loader import NO_ACCRUAL

REPO_ROOT = Path(__file__).resolve().parent.parent
ECONOMICS = REPO_ROOT / "src" / "measurement" / "economics.py"
CONFIG = REPO_ROOT / "config" / "economic_config.yaml"

#: 처치 → 그 비용을 계상하는 `economics.py` 함수.
#:
#: 이 표가 곧 "무엇이 무엇을 계상하는가" 의 선언이다. 근거는 처치의 성격이다:
#:   T0  무처치 — 계상하지 않는다
#:   T1  Free Shipping  → 배송보조 (주문이 나야 면제가 발생한다)
#:   T2  Fixed Coupon   → 할인 (쿠폰이 **사용돼야** 발생한다)
#:   T3  Strong Coupon  → 할인 (같음)
#:   T4  Reminder Push  → 발송 비용 (반응과 무관하게 발송 시점에 전원)
ACCRUES_VIA: dict[str, str | None] = {
    "T0": None,
    "T1": "shipping_subsidy",
    "T2": "coupon_cost",
    "T3": "coupon_cost",
    "T4": "message_cost",
}


def _source_event_types() -> dict[str, tuple[str, ...]]:
    """`economics.py` 의 함수별 `source_event_types=` 를 소스에서 읽는다.

    ★ 호출해서 얻지 않고 AST 로 읽는다. 호출하려면 캠페인·주문 픽스처를 지어
      내야 하고, 그러면 **픽스처가 답을 정하게 된다.** 여기서 묻는 것은
      "이 함수가 무엇을 근거로 계상한다고 **선언**하는가" 이고, 그 선언은
      소스에 있다.
    """
    text = ECONOMICS.read_text(encoding="utf-8")
    found: dict[str, tuple[str, ...]] = {}
    for node in ast.walk(ast.parse(text)):
        if not isinstance(node, ast.FunctionDef):
            continue
        for sub in ast.walk(node):
            if isinstance(sub, ast.keyword) and sub.arg == "source_event_types":
                try:
                    value = ast.literal_eval(sub.value)
                except ValueError:
                    continue
                found.setdefault(node.name, tuple(value))
                break
    return found


def _declared_occurs_at() -> dict[str, str]:
    """config 의 `treatment_cost.*.occurs_at`. PyYAML 없이 읽는다.

    이 검사는 의존성 0 잡에서도 돌아야 한다 — 어휘가 어긋나는 것은 YAML
    파서가 있든 없든 똑같이 결함이다.
    """
    result: dict[str, str] = {}
    treatment: str | None = None
    in_block = False
    for line in CONFIG.read_text(encoding="utf-8").splitlines():
        if line.startswith("treatment_cost:"):
            in_block = True
            continue
        # ★ 주석·빈 줄에서 끊지 않는다. 처음에는 "들여쓰기 없는 줄" 이면
        #   전부 블록의 끝으로 보았고, config 의 `# 쿠폰 계열 처치 …` 주석이
        #   바로 그것이라 **그 아래 처치가 조용히 잘렸다.** 음성 대조를 하다
        #   발견했다 — 잘린 것이 통과로 보였다.
        if in_block and line and not line[0].isspace() and not line.lstrip().startswith("#"):
            break
        if not in_block:
            continue
        stripped = line.strip()
        if line.startswith("  ") and not line.startswith("    ") and stripped.endswith(":"):
            treatment = stripped[:-1]
        elif stripped.startswith("occurs_at:") and treatment:
            result[treatment] = stripped.split(":", 1)[1].strip()
    return result


class TestDeclaredMomentsAreRealEvents(unittest.TestCase):
    """① 선언된 이름이 실재하는 `event_type` 인가."""

    def test_every_occurs_at_is_an_event_type(self) -> None:
        names = {event.value for event in sc.EventType}
        offenders = [
            f"{treatment}: {moment}"
            for treatment, moment in _declared_occurs_at().items()
            if moment != NO_ACCRUAL and moment not in names
        ]
        self.assertEqual(
            [], offenders,
            "event_type 에 없는 이름으로 발생 시점을 적었다. 이름만 그럴듯하면 "
            f"그 이벤트를 찾는 코드가 아무것도 찾지 못한다: {offenders}",
        )

    def test_the_parser_agrees_with_the_real_loader(self) -> None:
        """★ 손으로 쓴 파서를 **PyYAML 판독과 대조한다.**

        처음에는 `len == 5` 를 단언했다. 그것은 개수를 박아 둔 것이라 처치가
        하나 늘면 엉뚱한 곳에서 실패하고, **파서가 잘못 읽어도 다섯 개만
        읽으면 통과한다.** 실제로 주석 줄에서 블록이 잘리는 버그가 있었다.

        PyYAML 이 없으면 대조하지 않았다고 적는다 — 통과로 적지 않는다.
        """
        declared = _declared_occurs_at()
        self.assertTrue(declared, "파서가 아무것도 읽지 못했다 — 검사가 비어 있다")
        try:
            import yaml  # noqa: F401
        except ImportError:
            self.skipTest(
                "BLOCKED: PyYAML 미설치 — 손 파서를 실제 판독과 대조하지 "
                "않았다 (with-deps 잡이 이 대조를 수행한다)"
            )
        from src.measurement.config_loader import load_economic_config

        loaded = load_economic_config(CONFIG).cost_accounting.treatment_occurs_at
        self.assertEqual(
            dict(loaded), declared,
            "손으로 쓴 파서가 실제 판독과 다르게 읽는다",
        )

    def test_only_t0_has_no_accrual(self) -> None:
        """`none` 은 무처치에만 쓴다 — 다른 처치에 붙으면 비용이 사라진다."""
        declared = _declared_occurs_at()
        self.assertEqual(
            {"T0"}, {t for t, m in declared.items() if m == NO_ACCRUAL}
        )


class TestDeclarationMatchesImplementation(unittest.TestCase):
    """★★ ② 이 파일의 본체 — 선언과 구현을 맞댄다."""

    def setUp(self) -> None:
        self.declared = _declared_occurs_at()
        self.sources = _source_event_types()

    def test_every_treatment_is_mapped(self) -> None:
        """★ 처치가 늘면 대조표도 늘어야 한다. 아니면 그 처치만 조용히 검사 밖이 된다."""
        self.assertEqual(
            set(self.declared), set(ACCRUES_VIA),
            "config 의 처치와 대조표가 어긋난다 — 새 처치를 추가했다면 "
            "그것이 무엇으로 계상되는지도 함께 적는다",
        )

    def test_each_declared_moment_matches_the_accruing_function(self) -> None:
        mismatches: list[str] = []
        for treatment, function in ACCRUES_VIA.items():
            moment = self.declared[treatment]
            if function is None:
                if moment != NO_ACCRUAL:
                    mismatches.append(
                        f"{treatment}: 계상 함수가 없는데 occurs_at={moment}"
                    )
                continue
            actual = self.sources.get(function)
            if actual is None:
                mismatches.append(
                    f"{treatment}: {function}() 이 source_event_types 를 선언하지 않는다"
                )
            elif (moment,) != actual:
                mismatches.append(
                    f"{treatment}: config 는 {moment!r} 라 하고 "
                    f"{function}() 은 {actual} 에 계상한다"
                )
        self.assertEqual(
            [], mismatches,
            "발생 시점 선언과 실제 계상 근거가 어긋난다. config 를 고쳐도 계산은 "
            f"달라지지 않으므로, 어긋난 채로 두면 config 가 거짓말을 한다: {mismatches}",
        )

    def test_the_ast_reader_actually_found_sources(self) -> None:
        """★ 음성 대조 — 읽지 못하면 위 검사가 전부 공허하다."""
        for function in ("coupon_cost", "message_cost", "shipping_subsidy"):
            with self.subTest(function=function):
                self.assertIn(function, self.sources)
