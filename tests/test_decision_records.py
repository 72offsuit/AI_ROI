"""Keeps decision records from being empty templates (docs/DECISION_RECORDS.md).

The project's worst possible outcome is something that works while nobody can say
why: personas set to six because the PRD said six, an AUC of 0.82 nobody can
defend, a Final Holdout that quietly got used for threshold selection. Decision
records exist to make those answerable, and a record that is a copied template
with `<...>` still in it answers nothing while looking like it does.

What is checked here, and what is not:

  checked    both templates exist, and each one still declares the sections it
             promises -- a template that loses a section stops asking for it
  checked    every record carries the required sections for its kind
  checked    no unfilled `<...>` placeholder survives in a real record
  checked    filenames follow DR-/MC- so the kind is knowable without opening it
  NOT        whether the reasoning is any good. A machine cannot read the quality
             of a justification; review does that. This file only guarantees that
             nobody finished with the blanks still blank.

★ Placeholder detection is the point of this file, so it is the part most worth
  getting exactly right. It must not fire on prose that legitimately contains an
  angle bracket (`<=`, `a < b`, an HTML comment, a URL in angle brackets), and it
  must still fire on a real leftover. `test_placeholder_scan_*` pins both
  directions -- a scanner that never fires would let every empty record through
  while this suite stayed green.
"""

from __future__ import annotations

import re
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DECISIONS = REPO_ROOT / "docs" / "decisions"
GUIDE = REPO_ROOT / "docs" / "DECISION_RECORDS.md"

DESIGN_TEMPLATE = DECISIONS / "_TEMPLATE_design.md"
MODEL_TEMPLATE = DECISIONS / "_TEMPLATE_model.md"

#: 설계 결정 기록이 반드시 묻는 것. ★ "기각한 안" 과 "이 결정이 틀렸다면" 이 핵심이다 --
#: 택한 이유만 있는 문서는 다른 안을 검토하지 않은 것과 구분되지 않는다.
DESIGN_SECTIONS = (
    "무엇을 정하는가",
    "정하지 않으면 무엇이 막히나",
    "선택지",
    "조사한 것",
    "결정",
    "기각한 안과 기각 사유",
    "이 결정이 틀렸다면 어떻게 드러나나",
    "민감도",
    "남은 불확실성",
)

#: 모델 카드가 반드시 묻는 것. ★ "누수 점검" 과 "실패 모드" 가 핵심이다.
MODEL_SECTIONS = (
    "무엇을 예측하나",
    "어떤 결정에 쓰이나",
    "데이터 계보",
    "분할",
    "학습",
    "누수 점검",
    "성능",
    "해석",
    "실패 모드",
    "재현",
)

#: `<...>` 중에서 **채우지 않은 자리**만 잡는다. 산문의 `<=` · `a < b` · HTML 주석 ·
#: 꺾쇠 URL 은 잡지 않는다 -- 거짓 양성이 나면 사람들이 검사를 꺼 버린다.
_PLACEHOLDER = re.compile(r"<(?![=!/\s])(?!https?://)[^<>\n]{0,80}>")


def _strip_html_comments(text: str) -> str:
    return re.sub(r"<!--.*?-->", "", text, flags=re.DOTALL)


def placeholders(text: str) -> list[str]:
    """채우지 않은 `<...>` 자리. 주석 안은 세지 않는다 (템플릿 사용법이 거기 있다)."""
    return _PLACEHOLDER.findall(_strip_html_comments(text))


def records() -> list[Path]:
    """실제 기록만. `_` 로 시작하는 템플릿은 제외한다."""
    if not DECISIONS.is_dir():
        return []
    return sorted(p for p in DECISIONS.glob("*.md") if not p.name.startswith("_"))


class TestTheSystemItselfExists(unittest.TestCase):
    """제도가 없으면 기록을 요구할 수 없다."""

    def test_guide_exists(self) -> None:
        self.assertTrue(GUIDE.is_file(), f"{GUIDE} 가 없다")

    def test_both_templates_exist(self) -> None:
        for template in (DESIGN_TEMPLATE, MODEL_TEMPLATE):
            with self.subTest(template=template.name):
                self.assertTrue(template.is_file(), f"{template} 가 없다")

    def test_design_template_asks_every_required_section(self) -> None:
        """★ 템플릿에서 섹션이 빠지면 **그때부터 아무도 그것을 묻지 않는다.**"""
        text = DESIGN_TEMPLATE.read_text(encoding="utf-8")
        for section in DESIGN_SECTIONS:
            with self.subTest(section=section):
                self.assertIn(section, text)

    def test_model_template_asks_every_required_section(self) -> None:
        text = MODEL_TEMPLATE.read_text(encoding="utf-8")
        for section in MODEL_SECTIONS:
            with self.subTest(section=section):
                self.assertIn(section, text)

    def test_model_template_asks_what_holdout_was_not_used_for(self) -> None:
        """★ 모델 카드에서 가장 중요한 한 칸.

        "무엇에 썼나" 만 물으면 튜닝에 쓴 사람이 쓴 용도만 적고 넘어간다.
        **쓰지 않은 것**을 명시적으로 묻어야 그 구분이 기록에 남는다.
        """
        text = MODEL_TEMPLATE.read_text(encoding="utf-8")
        self.assertIn("무엇에 쓰지 않았나", text)

    def test_guide_points_at_the_templates(self) -> None:
        text = GUIDE.read_text(encoding="utf-8")
        for name in ("_TEMPLATE_design.md", "_TEMPLATE_model.md"):
            with self.subTest(name=name):
                self.assertIn(name, text)


class TestEachRecordIsFilledIn(unittest.TestCase):
    """기록이 생기기 시작하면 여기서 검사한다.

    ★ 기록이 아직 하나도 없는 것은 **실패가 아니다** -- C2 착수 전이 그 상태다.
      없는 것을 실패로 만들면 착수 자체가 빨개지고, 그러면 검사를 끄게 된다.
    """

    def test_filenames_declare_their_kind(self) -> None:
        bad = [p.name for p in records() if not re.match(r"^(DR|MC)-", p.name)]
        self.assertEqual(
            [], bad,
            "결정 기록은 DR-(설계) 또는 MC-(모델 카드) 로 시작한다. 열어 보지 않고 "
            f"종류를 알 수 있어야 한다: {bad}",
        )

    def test_required_sections_are_present(self) -> None:
        missing: list[str] = []
        for path in records():
            text = path.read_text(encoding="utf-8")
            required = MODEL_SECTIONS if path.name.startswith("MC-") else DESIGN_SECTIONS
            for section in required:
                if section not in text:
                    missing.append(f"{path.name}: '{section}'")
        self.assertEqual([], missing, f"빠진 섹션이 있다: {missing}")

    def test_no_unfilled_placeholders(self) -> None:
        """★ 템플릿만 복사하고 채우지 않은 것을 잡는다.

        빈 칸이 남은 기록은 **아무것도 답하지 않으면서 답한 것처럼 보인다** --
        그것이 이 제도가 막으려던 바로 그 상태다.
        """
        leftovers: list[str] = []
        for path in records():
            found = placeholders(path.read_text(encoding="utf-8"))
            if found:
                leftovers.append(f"{path.name}: {found[:5]}")
        self.assertEqual(
            [], leftovers,
            f"채우지 않은 자리가 남아 있다: {leftovers}",
        )

    def test_task_id_is_in_the_body(self) -> None:
        """어느 태스크의 결정인지 본문에서 알 수 있어야 한다."""
        for path in records():
            task = path.name.split("-")[1] if "-" in path.name else ""
            with self.subTest(record=path.name):
                self.assertRegex(
                    task, r"^[SD]\d+$",
                    f"{path.name}: 파일 이름에 태스크 번호(S3 · D7 등)가 없다",
                )
                self.assertIn(
                    task, path.read_text(encoding="utf-8"),
                    f"{path.name}: 본문에 태스크 번호 {task} 가 없다",
                )


class TestPlaceholderScanWorksBothWays(unittest.TestCase):
    """★ 음성·양성 대조 -- 스캐너가 이 파일 전체의 값을 결정한다."""

    def test_scan_finds_a_real_placeholder(self) -> None:
        self.assertTrue(placeholders("작성 | <이름> · <YYYY-MM-DD>"))
        self.assertTrue(placeholders("## 결정\n\n<무엇으로 정했는가>"))

    def test_scan_ignores_comparison_operators(self) -> None:
        """`<=` 나 `a < b` 에서 울리면 사람들이 검사를 꺼 버린다."""
        self.assertEqual([], placeholders("임계값 <= 0.35 이고 a < b 이면 제외한다"))

    def test_scan_ignores_html_comments(self) -> None:
        """템플릿 사용법이 주석 안에 있다 — 거기서 울리면 모든 기록이 실패한다."""
        self.assertEqual([], placeholders("<!-- 복사해서 <이름>.md 로 저장한다 -->\n본문"))

    def test_scan_ignores_angle_bracketed_urls(self) -> None:
        self.assertEqual([], placeholders("출처 <https://example.org/paper>"))

    def test_templates_themselves_are_full_of_placeholders(self) -> None:
        """★ 템플릿에서조차 안 잡히면 스캐너가 고장난 것이다."""
        for template in (DESIGN_TEMPLATE, MODEL_TEMPLATE):
            with self.subTest(template=template.name):
                self.assertTrue(
                    placeholders(template.read_text(encoding="utf-8")),
                    f"{template.name}: 템플릿의 빈 자리를 찾지 못했다 — 스캐너가 고장났다",
                )
