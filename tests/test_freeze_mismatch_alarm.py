"""Locks down the seal-tamper alarm that never worked (issue #60, findings M4/M5/F8).

`FREEZE_MISMATCH` means "a sealed canonical file changed after the lock". It is the
most severe headline the publish contract can emit -- `headline_level()` maps it to
`violation`. It had **never been able to fire**, for two independent reasons:

  layer 1  `build_index` did not fill `freeze_mismatch`, and the contract actively
           forbade the key (`counts` is `additionalProperties: false`). The reader
           was looking at a key the contract made impossible.
  layer 2  the condition ANDed it with `lock_items_pending`, which despite its name
           counts **unmet G-preconditions**, not pending LOCK_ITEMS. All sixteen are
           met, so it measured 0 -- and fixing layer 1 alone still produced no alarm.

★ Fixing one layer would have looked like success. That is what these tests are for:
  the "obvious fix" case (`freeze_mismatch` set, no pending items) is asserted
  explicitly, because that is the case a partial fix silently leaves broken.

★ The root cause behind both layers was a broken wire, not a wrong number: `verify()`
  always held the comparison result, and it never reached the artifact. Half of these
  tests assert the wire, not the condition.
"""

from __future__ import annotations

import unittest

from src.measurement import freeze as fz
from src.measurement.errors import ConfigError
from src.measurement.publish import build_freeze_status, choose_headline_code


class TestAlarmFiresWhenSealsDoNotMatch(unittest.TestCase):
    """세 시나리오 — 이전 판은 셋 중 하나에서만 작동했다."""

    def test_fires_when_items_are_still_pending(self) -> None:
        """부분 봉인 중에 불일치가 생긴 경우. 이전 판도 여기까지는 됐다."""
        self.assertEqual(
            "FREEZE_MISMATCH",
            choose_headline_code({"freeze_mismatch": 1, "lock_items_pending": 2}),
        )

    def test_fires_when_everything_is_locked(self) -> None:
        """★ 완전 봉인 상태에서의 불일치 — 이전 판이 침묵하던 자리.

        선행 조건이 전부 충족되면 `lock_items_pending` 이 0 이 되고, AND 조건이
        경보를 삼켰다. **봉인이 가장 중요해지는 시점에 정확히 침묵했다.**
        """
        self.assertEqual(
            "FREEZE_MISMATCH",
            choose_headline_code({"freeze_mismatch": 1, "lock_items_pending": 0}),
        )

    def test_fires_under_todays_actual_counts(self) -> None:
        """★ "명백한 수정" 만으로는 오늘도 뜨지 않았다.

        실제 게시물의 counts(`lock_items_pending == 0`, 검사 미실행 다수)에
        불일치만 얹은 상태. 누락 키만 채우는 수정을 했다면 `CHECKS_NOT_RUN` 이
        나왔고, 고친 사람은 동작을 확인하지 못한 채 닫았을 것이다.
        """
        self.assertEqual(
            "FREEZE_MISMATCH",
            choose_headline_code({
                "freeze_mismatch": 1,
                "lock_items_pending": 0,
                "checks_not_run": 17,
                "checks_blocked": 1,
                "metrics_unavailable": 44,
                "schema_gaps": 5,
            }),
        )

    def test_silent_when_seals_match(self) -> None:
        """경보가 항상 울리면 경보가 아니다."""
        self.assertNotEqual(
            "FREEZE_MISMATCH",
            choose_headline_code({"freeze_mismatch": 0, "lock_items_pending": 0}),
        )

    def test_outranks_every_lesser_headline(self) -> None:
        """봉인 변조는 품질·거부·미실행보다 앞선다. 계약 위반만이 위다."""
        loud = {
            "freeze_mismatch": 1, "quality_violations": 9, "rejected_events": 9,
            "checks_not_run": 9, "metrics_unavailable": 9,
        }
        self.assertEqual("FREEZE_MISMATCH", choose_headline_code(loud))
        self.assertEqual(
            "CONTRACT_VIOLATION",
            choose_headline_code(loud, contract_violation=True),
            "계약 위반은 봉인 변조보다 앞선다 — 게시물 자체를 믿을 수 없기 때문이다",
        )


class TestComparisonResultReachesTheArtifact(unittest.TestCase):
    """배선 — 판정이 만들어지는 자리에서 읽는 자리까지 실제로 흐르는가."""

    def test_artifact_carries_verification(self) -> None:
        artifact = build_freeze_status()
        self.assertIn(
            "verification", artifact,
            "대조 결과가 게시물에 없으면 index 가 freeze_mismatch 를 셀 방법이 없다",
        )
        self.assertIn(
            artifact["verification"], ("match", "mismatch", "missing", "not_run"),
        )

    def test_artifact_carries_mismatches(self) -> None:
        artifact = build_freeze_status()
        self.assertIn("mismatches", artifact)
        self.assertIsInstance(artifact["mismatches"], list)

    def test_not_run_is_not_reported_as_match(self) -> None:
        """대조하지 않은 것을 일치로 적지 않는다 — 세 번째 값."""
        unreadable = fz.verify(
            preconditions=fz.GATE1_PRECONDITIONS,
            items=fz.gate1_lock_items(),
            lock_record=fz.RECORD_UNREADABLE,
        )
        self.assertEqual("not_run", unreadable.verification)
        self.assertEqual((), unreadable.mismatches)

    def test_absent_record_is_missing_not_match(self) -> None:
        absent = fz.verify(
            preconditions=fz.GATE1_PRECONDITIONS,
            items=fz.gate1_lock_items(),
            lock_record=None,
        )
        self.assertEqual("missing", absent.verification)


class TestCorruptedLockRecordFailsWithItsOwnMessage(unittest.TestCase):
    """M5 — 방어 코드가 `NameError` 로 죽던 자리.

    발동 조건이 곧 변조 시나리오다: `canonical_files` 가 매핑이 아니라는 것은
    봉인 기록을 손으로 고쳐 구조가 깨졌다는 뜻이고, `FREEZE-003` 이 *"손으로
    고치는 것으로 대체되지 않는다"* 고 선언한 바로 그 방어선이다.

    검증 우회는 원래도 없었다(두 예외 모두 `verify()` 를 중단시킨다). 문제는
    **진단**이었다 — 의도된 메시지가 사라지고 종료 코드가 5 가 아닌 1 이 되어
    "종료 코드로 원인 분기" 가 무의미해졌다.
    """

    def test_raises_config_error_not_name_error(self) -> None:
        broken = {"canonical_files": "매핑이 아니다", "locked_by": "x", "items": []}
        with self.assertRaises(ConfigError) as caught:
            fz.verify(
                preconditions=fz.GATE1_PRECONDITIONS,
                items=fz.gate1_lock_items(),
                lock_record=broken,
            )
        self.assertIn("canonical_files", str(caught.exception))

    def test_config_error_is_importable_from_freeze(self) -> None:
        """미임포트가 원인이었으므로 이름 자체를 단언한다."""
        self.assertTrue(
            hasattr(fz, "ConfigError"),
            "freeze.py 가 ConfigError 를 import 하지 않으면 466행이 NameError 를 던진다",
        )

    def test_no_undefined_names_remain(self) -> None:
        """★ 같은 부류가 더 있는지 모듈 전체를 훑는다.

        `ConfigError` 는 셋 중 하나였다. 나머지 둘(`_FREEZE_ITEMS` ·
        `_GATE1_PRECONDITIONS`)은 M-09 이전 판본의 죽은 `build_freeze_status()`
        안에 있었고 그 함수째 제거했다 — 같은 이름의 두 번째 구현이 남아 있으면
        누군가 그것을 불러 탐지 3층의 판정이 갈린다(AC-4).
        """
        import ast
        import builtins
        from pathlib import Path

        source = Path(fz.__file__).read_text(encoding="utf-8")
        tree = ast.parse(source)
        defined = set(dir(builtins)) | {"__name__", "__file__", "__doc__"}
        for node in ast.walk(tree):
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                for alias in node.names:
                    defined.add((alias.asname or alias.name).split(".")[0])
            elif isinstance(node, (ast.FunctionDef, ast.ClassDef)):
                defined.add(node.name)
            elif isinstance(node, ast.Name) and isinstance(node.ctx, ast.Store):
                defined.add(node.id)
            elif isinstance(node, ast.arg):
                defined.add(node.arg)
        undefined = sorted({
            node.id
            for node in ast.walk(tree)
            if isinstance(node, ast.Name)
            and isinstance(node.ctx, ast.Load)
            and node.id not in defined
        })
        self.assertEqual(
            [], undefined,
            "freeze.py 에 정의되지 않은 이름이 있다 — 그 경로를 타면 NameError 다",
        )
