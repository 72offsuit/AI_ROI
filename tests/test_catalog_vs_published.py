"""Compares the metric catalogue against what actually reaches a published artifact.

Why this file exists (issue #59, review finding M7): `METRIC_SPECS` declares each
metric's C1 availability, and **nothing checked that declaration against reality**.
Three metrics declared `"computable"` reached no artifact at all -- two had working
functions nobody called, one had no function whatsoever -- and one metric was
published while being absent from the catalogue entirely. The catalogue was wrong
in **both directions** and every test was green.

★ The point of this file is not to have zero gaps. It is that **no gap is silent**.
  A known gap belongs in `DECLARED_GAPS` with the reason it is still open; a new one
  fails the run. That is the same shape as the "third value" discipline the rest of
  the codebase applies to metric values (`vacuous`, `met: null`, `not_run`) -- here
  it is applied to the catalogue's own declarations.

★ Detection looks at BOTH a string literal and a function call. An earlier manual
  pass grepped only for `"name"` and wrongly reported `event_type_count` and
  `field_fill_rate` as unpublished -- they are published through
  `kpi.field_fill_rate(manifest)`, a call, not a literal. Checking one form only
  reproduces the very class of defect this file closes.
"""

from __future__ import annotations

import re
import unittest
from pathlib import Path

from src.measurement import kpi
from src.measurement import publish

PUBLISH_SOURCE = (
    Path(__file__).resolve().parent.parent / "src" / "measurement" / "publish.py"
).read_text(encoding="utf-8")


def _reaches_publication(name: str) -> bool:
    """True when `publish.py` mentions the metric as a literal **or** calls it."""
    if f'"{name}"' in PUBLISH_SOURCE or f"'{name}'" in PUBLISH_SOURCE:
        return True
    return bool(re.search(rf"\bkpi\.{re.escape(name)}\b|\b{re.escape(name)}\s*\(", PUBLISH_SOURCE))


class TestCatalogueDeclarationsMatchReality(unittest.TestCase):
    """`METRIC_SPECS` 가 `"computable"` 이라고 선언한 것이 실제로 계산·게시되는가."""

    #: ★ 선언은 있는데 게시물에 도달하지 않는 지표. **비워 두는 것이 목표가 아니라
    #: 조용히 늘지 않는 것이 목표다.** 여기 없는 새 공백이 생기면 이 테스트가 실패한다.
    #:
    #: 넷 다 이슈 #59 에서 발견됐고, 해소는 게시물 계약 변경(대시보드 영향)을
    #: 동반하므로 별도 판단으로 남겼다 — 이 테스트가 그 판단을 잊지 않게 한다.
    DECLARED_GAPS = {
        "missing_field_count": (
            "kpi.missing_field_count() 는 정상 동작하는데 publish.py 가 호출하지 않는다. "
            "같은 정보가 field_coverage_report.missing_fields 에 배열로는 나가고 있어 "
            "지표 행으로 추가하려면 계약 변경이 필요하다."
        ),
        "source_event_count": (
            "kpi.source_event_count() 는 정상 동작하는데 publish.py 가 호출하지 않는다. "
            "같은 정보가 ingestion_report.sources 로는 나가고 있다."
        ),
        "rejection_reason_count": (
            "구현 자체가 없다. 카탈로그가 'computable' 이라고 선언한 것 중 유일하게 "
            "함수도 없는 항목이다. 같은 정보가 rejection_report.by_reason 으로는 나간다."
        ),
    }

    #: ★ 반대 방향 — 게시되는데 카탈로그에 없는 이름. 카탈로그로 "무슨 지표가 있나" 를
    #: 감사하면 이 지표를 놓친다. 즉 **카탈로그는 정본이 아니며 양방향으로 어긋난다.**
    PUBLISHED_BUT_UNCATALOGUED = {
        "sleeping_dog_targeting_rate": (
            "publish._EXPERIMENT_METRICS 와 _METRIC_ROLES(guardrail) 에는 있는데 "
            "METRIC_SPECS 에 없다. 카탈로그에 더하면 총수가 47 이 되어 "
            "kpi-definition-v1.md §8 의 '47종'(계층3 을 15 로 잘못 센 결과)과 "
            "우연히 같아진다 — 서로 다른 이유로 같은 숫자가 되면 다음 사람이 "
            "문서 오류가 고쳐진 것으로 오해한다. 문서 정정과 함께 처리한다."
        ),
    }

    def test_computable_metrics_reach_an_artifact(self) -> None:
        """`"computable"` 선언은 구현과 게시로 뒷받침돼야 한다."""
        undeclared: list[str] = []
        for spec in kpi.METRIC_SPECS:
            if spec.c1 != "computable":
                continue
            if _reaches_publication(spec.name):
                continue
            if spec.name in self.DECLARED_GAPS:
                continue
            undeclared.append(spec.name)
        self.assertEqual(
            [], sorted(undeclared),
            "카탈로그가 'computable' 이라고 선언했는데 게시물에 도달하지 않는다. "
            "해소하거나 DECLARED_GAPS 에 사유와 함께 선언하라 — 선언하지 않은 공백은 "
            "다음 사람이 '계산되는 지표' 로 읽는다",
        )

    def test_declared_gaps_are_still_gaps(self) -> None:
        """공백이 메워지면 선언을 지운다. 낡은 선언도 거짓말이다."""
        stale = [name for name in self.DECLARED_GAPS if _reaches_publication(name)]
        self.assertEqual(
            [], sorted(stale),
            "DECLARED_GAPS 에 있는데 실제로는 게시되고 있다 — 선언을 지워라",
        )

    def test_declared_gaps_have_reasons(self) -> None:
        for name, reason in self.DECLARED_GAPS.items():
            with self.subTest(metric=name):
                self.assertTrue(reason.strip(), f"{name}: 왜 아직 공백인지가 비어 있다")

    def test_declared_gaps_exist_in_catalogue(self) -> None:
        """없는 지표를 공백으로 선언해 두면 선언이 썩는다."""
        names = {spec.name for spec in kpi.METRIC_SPECS}
        for name in self.DECLARED_GAPS:
            with self.subTest(metric=name):
                self.assertIn(
                    name, names,
                    f"{name}: DECLARED_GAPS 에 있는데 METRIC_SPECS 에 없다",
                )


class TestPublishedMetricsAreCatalogued(unittest.TestCase):
    """게시되는 이름이 카탈로그에 있는가 — 반대 방향."""

    def test_experiment_metrics_are_in_the_catalogue(self) -> None:
        catalogue = {spec.name for spec in kpi.METRIC_SPECS}
        published = {entry[0] for entry in publish._EXPERIMENT_METRICS}
        declared = set(
            TestCatalogueDeclarationsMatchReality.PUBLISHED_BUT_UNCATALOGUED
        )
        orphans = published - catalogue - declared
        self.assertEqual(
            set(), orphans,
            "화면에 나오는데 카탈로그 어디에도 없는 지표다. 카탈로그가 정본이 아니라는 "
            "뜻이므로 카탈로그에 더하거나 PUBLISHED_BUT_UNCATALOGUED 에 선언하라",
        )

    def test_declared_orphans_are_still_orphans(self) -> None:
        catalogue = {spec.name for spec in kpi.METRIC_SPECS}
        stale = [
            name
            for name in TestCatalogueDeclarationsMatchReality.PUBLISHED_BUT_UNCATALOGUED
            if name in catalogue
        ]
        self.assertEqual(
            [], sorted(stale),
            "PUBLISHED_BUT_UNCATALOGUED 에 있는데 카탈로그에 들어와 있다 — 선언을 지워라",
        )


class TestDetectionItselfWorks(unittest.TestCase):
    """검사 대상이 0 개인 채로 통과하는 것을 막는다.

    "검사 대상이 주장보다 좁다" 는 이 구현에서 세 번 나타난 패턴이다.
    """

    def test_catalogue_is_not_empty(self) -> None:
        self.assertGreater(len(kpi.METRIC_SPECS), 0)

    def test_publish_source_was_read(self) -> None:
        self.assertGreater(
            len(PUBLISH_SOURCE), 1000,
            "publish.py 를 읽지 못했다 — 빈 문자열을 훑으면 모든 지표가 '미게시' 가 된다",
        )

    def test_detection_finds_both_forms(self) -> None:
        """리터럴과 함수 호출 **양쪽** 다 잡는지 — 한쪽만 보면 오탐이 난다."""
        self.assertTrue(
            _reaches_publication("events_ingested"), "리터럴 형태를 놓쳤다"
        )
        self.assertTrue(
            _reaches_publication("field_fill_rate"), "함수 호출 형태를 놓쳤다"
        )
        self.assertFalse(
            _reaches_publication("definitely_not_a_metric_name_xyz"),
            "아무 이름이나 참을 내면 검사가 무의미하다",
        )
