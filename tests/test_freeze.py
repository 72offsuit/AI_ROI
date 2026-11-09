"""GATE 1 부분 봉인 검사 — 탐지 1층 (이슈 #49).

## ★★ 이 파일의 유일한 실패 양식

```python
def test_locked_files_unchanged(self):
    if not lock_file.exists():
        return                      # ← 봉인하지 않은 상태가 초록으로 보인다
```

**`AC-5` 가 이것을 금지한다.** Lock 기록이 없는 것은 *"통과"* 가 아니라
`not_started` 이고, 그것을 **단언**해야 한다. `skipTest` 도 쓰지 않는다 — skip 은
`unittest` 가 exit 0 으로 내므로 사유 없이 넘기면 검증하지 않은 것이 검증한 것처럼
보인다.

## 탐지 3층 중 1층이다 — **경고가 아니라 실패한다**

    1층  이 파일           → freeze.verify()
    2층  publish.py        → 같은 함수 → freeze_status.json
    3층  대시보드 V6        → 그 게시물

**세 층이 같은 함수를 쓴다는 것을 이 파일이 확인한다** (`test_three_layers_agree`).
각자 판정하면 갈리고, 갈리면 어느 쪽이 정본인지 알 수 없다.

실행:
    python3 -m unittest tests.test_freeze -v
"""

from __future__ import annotations

import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

from src.measurement import freeze as fz
from src.measurement.config_loader import yaml_available
from src.measurement.errors import ConfigError, FreezeViolation
from src.measurement.publish import build_freeze_status
from src.measurement.sink import KST

REPO_ROOT = Path(__file__).resolve().parents[1]


def lock_items(**overrides: str) -> tuple[fz.LockItem, ...]:
    """Lock 9종 픽스처. `overrides` 로 특정 항목의 status 를 바꾼다.

    LOCKED 항목은 정본 파일 없이 만들 수 없으므로(#163) 실재하는 파일 하나를 붙인다.
    """
    return tuple(
        fz.LockItem(
            item=item,
            status=overrides.get(item, "PARTIAL"),
            owner_part="measurement",
            scope_note="범위 한정 문구",
            canonical_files=(
                ("config/economic_config.yaml",)
                if overrides.get(item) == "LOCKED" else ()
            ),
        )
        for item in fz.LOCK_ITEMS
    )


class TestRecordedAssumptionsMatchTheCode(unittest.TestCase):
    """★ 기록된 가정과 `freeze.gate1_assumptions()` 가 어긋나지 않는다.

    이 가정들은 예전에 **기록 안에만** 있었고, 봉인을 실행하는 사람이 손으로
    넘겼다. `docs/gate1_checklist.md` §5.2 의 호출 예시에 `assumptions=` 가
    아예 없었으므로, 이슈 #63 이 요구한 **재기록을 절차대로 실행하면
    `assumptions: []` 가 조용히 만들어졌을 것이다** — 그리고 대조하는 것이
    없으니 아무도 몰랐을 것이다.

    가정을 잃은 봉인 기록은 *"전부 확인했다"* 로 읽힌다. 봉인은 그렇게 주장하지
    않는다. 그래서 정본을 코드로 옮기고 여기서 대조한다.
    """

    def test_record_carries_exactly_the_declared_assumptions(self) -> None:
        record = fz.load_record()
        if record is None:
            self.skipTest("BLOCKED: Lock 기록이 없다 — 대조하지 않았다 (통과가 아니다)")
        if record is fz.RECORD_UNREADABLE:
            self.skipTest(
                "BLOCKED: PyYAML 이 없어 기록을 읽지 못했다 — 대조하지 않았다. "
                "with-deps 잡이 이 대조를 수행한다"
            )
        self.assertEqual(
            [dict(a) for a in fz.gate1_assumptions()],
            [dict(a) for a in record.get("assumptions") or []],
            "봉인 기록의 가정과 코드의 가정이 다르다. 기록을 손으로 고쳤거나, "
            "재기록에 assumptions= 를 넘기지 않았다",
        )

    def test_every_assumption_states_its_error_direction(self) -> None:
        """방향 없는 가정은 *"불확실하다"* 까지만 말하고 **어느 쪽으로 틀렸는지**를
        말하지 않는다. 결정을 바꾸는 것은 후자다."""
        for assumption in fz.gate1_assumptions():
            with self.subTest(assumption=assumption["id"]):
                self.assertTrue(str(assumption.get("error_direction", "")).strip())

    def test_assumptions_are_not_empty(self) -> None:
        """★ 빈 목록이 통과하면 이 파일 전체가 무의미하다."""
        self.assertTrue(fz.gate1_assumptions())


class TestNotStartedIsAsserted(unittest.TestCase):
    """★★ AC-5 — Lock 기록이 없을 때 **조용히 통과하지 않는다**."""

    def test_locked_files_unchanged(self) -> None:
        """★ 이 테스트는 **skip 하지 않는다.** 없는 상태를 단언한다.

        `if not lock_file.exists(): return` 이 이 사이클이 지목한 가장 위험한
        다섯 줄 중 하나다 — 봉인하지 않은 상태가 초록으로 보인다.
        """
        record = fz.load_record()
        verification = fz.verify(
            preconditions=fz.GATE1_PRECONDITIONS,
            items=fz.gate1_lock_items(record),
            lock_record=record,
        )
        # ★ 세 경우 전부 **단언**한다. 어느 것도 skip 하지 않는다.
        if record is None:
            self.assertEqual(
                "not_started", verification.overall,
                "Lock 기록이 없는 것은 통과가 아니라 not_started 다",
            )
            self.assertEqual("missing", verification.verification)
        elif record is fz.RECORD_UNREADABLE:
            # ★★ 기록은 있으나 PyYAML 이 없어 대조하지 못했다.
            #
            # **이것이 `isolation.yml`(의존성 0)의 정상 상태다.** 예외로 터지면
            # 격리 CI 가 격리와 무관한 이유로 빨개지고(A7 이 막으려는 실패 양식),
            # 조용히 통과하면 봉인하지 않은 것이 초록으로 보인다.
            # → `not_run` 으로 **값으로** 만든다. 해시 대조는 with-deps 잡이 한다.
            self.assertEqual("not_run", verification.verification)
            self.assertNotEqual(
                "match", verification.verification,
                "대조하지 않은 것을 일치로 적지 않는다",
            )
            self.assertIn("미실행", verification.detail)
        else:
            # 읽을 수 있으면 해시 대조가 실제로 돌아야 한다.
            self.assertIn(verification.verification, ("match", "mismatch"))
            self.assertEqual(
                [], list(verification.mismatches),
                "봉인된 정본 파일이 봉인 이후 변경됐다 (FREEZE-003)",
            )
        self.assertTrue(verification.detail, "왜 그 상태인지가 비어 있으면 안 된다")

    def test_unreadable_record_is_not_the_same_as_absent(self) -> None:
        """★ *"파일이 없다"* 와 *"읽을 수 없다"* 를 가른다.

        후자를 `None` 으로 떨어뜨리면 기록이 실재하는데 *"봉인을 시작하지
        않았다"* 가 되어 **거짓말**이 된다. 셋째 값이 필요한 세 번째 자리다
        (`vacuous` · 계산 불가 · `met: null` 과 같은 원칙).
        """
        absent = fz.verify(
            preconditions=fz.GATE1_PRECONDITIONS, items=lock_items(),
            lock_record=None,
        )
        unreadable = fz.verify(
            preconditions=fz.GATE1_PRECONDITIONS, items=lock_items(),
            lock_record=fz.RECORD_UNREADABLE,
        )
        self.assertEqual("missing", absent.verification)
        self.assertEqual("not_run", unreadable.verification)
        self.assertNotEqual(absent.overall, unreadable.overall)
        self.assertEqual("not_started", absent.overall)
        self.assertEqual("partial", unreadable.overall)

    def test_unreadable_record_does_not_raise(self) -> None:
        """★★ A7 — 격리 CI 가 **격리와 무관한 이유로** 깨지지 않는다.

        Lock 기록이 생긴 순간부터 `isolation.yml` 이 영구 실패하면, 그것이
        *"의존성 도입 후에도 격리 검사가 유지된다"* 는 가정 A7 을 무너뜨린다.
        """
        if fz.DEFAULT_LOCK_RECORD.exists():
            fz.load_record()  # 예외가 없어야 한다

    def test_missing_and_not_run_are_different_states(self) -> None:
        """★ *"기록이 없음을 확인했다"* 와 *"확인하지 않았다"* 는 다르다."""
        self.assertIn("missing", fz.VERIFICATION_STATES)
        self.assertIn("not_run", fz.VERIFICATION_STATES)
        self.assertNotEqual("missing", "not_run")

    def test_overall_reaches_not_started_without_a_record(self) -> None:
        verification = fz.verify(
            preconditions=fz.GATE1_PRECONDITIONS, items=lock_items(),
            lock_record=None,
        )
        self.assertEqual("not_started", verification.overall)


class TestC1DoesNotPassGate1(unittest.TestCase):
    """★ AC-5 — C1 은 GATE 1 을 통과시키지 않는다."""

    def test_no_full_freeze_in_c1(self) -> None:
        """LOCKED 가 없으면 `declaration` 은 `PARTIAL_FREEZE` 다 — FULL 은 항목에서만 유도된다 (#163)."""
        record = fz.build_record(
            locked_by="Phillip", items=lock_items(), canonical_files=[],
            repo_commit="abc123", now=datetime.now(KST),
        )
        self.assertEqual("PARTIAL_FREEZE", record["declaration"])
        self.assertNotEqual("FULL_FREEZE", record["declaration"])
        self.assertIs(False, record["experiment_environment_v1_declared"])

    def test_declaration_is_not_parameterised(self) -> None:
        """★ `FULL_FREEZE` 를 인자로 받지 않는다 — 받으면 누군가 전달한다."""
        import inspect

        parameters = inspect.signature(fz.build_record).parameters
        self.assertNotIn("declaration", parameters)
        self.assertNotIn("experiment_environment_v1_declared", parameters)

    def test_sealed_requires_a_reason(self) -> None:
        """C1 도달 가능 최대치는 `partial` 이다. `sealed` 는 근거 없이 못 만든다."""
        with self.assertRaises(ValueError):
            fz.FreezeVerification(
                overall="sealed", verification="match", lock_record={},
                items=lock_items(), unmet=(),
            )

    def test_partial_is_reachable_and_sealed_is_not_by_accident(self) -> None:
        """전 항목이 `LOCKED` 가 아니면 `partial` 이다."""
        verification = fz.verify(
            preconditions=[fz.Precondition("G-1", "x", True)],
            items=lock_items(), lock_record={"canonical_files": {}},
        )
        self.assertEqual("partial", verification.overall)


class TestSimulatorCommitIsNull(unittest.TestCase):
    """★ AC-5 — `""`·`"unknown"`·`"0"` 으로 채우면 안 된다."""

    def test_simulator_commit_is_null_with_reason(self) -> None:
        record = fz.build_record(
            locked_by="Phillip", items=lock_items(), canonical_files=[],
            repo_commit="abc123", now=datetime.now(KST),
        )
        self.assertIsNone(record["simulator_commit"], "C1 에 시뮬레이터가 없다")
        self.assertEqual(
            "PRECONDITION_MISSING", record["simulator_commit_null_reason"],
            "null 에 사유가 없으면 '0 으로 채운 것'과 구분되지 않는다",
        )

    def test_placeholder_values_are_not_used(self) -> None:
        """★ 빈 문자열·`unknown`·`0` 은 *"확인했고 이 값이다"* 가 되어버린다."""
        record = fz.build_record(
            locked_by="Phillip", items=lock_items(), canonical_files=[],
            repo_commit="abc123", now=datetime.now(KST),
        )
        for placeholder in ("", "unknown", "0", "n/a", "-", "none"):
            with self.subTest(placeholder=placeholder):
                self.assertNotEqual(placeholder, record["simulator_commit"])

    def test_missing_repo_commit_also_carries_a_reason(self) -> None:
        record = fz.build_record(
            locked_by="Phillip", items=lock_items(), canonical_files=[],
            repo_commit=None, now=datetime.now(KST),
        )
        self.assertIsNone(record["repo_commit"])
        self.assertIn("repo_commit_null_reason", record)

    def test_missing_canonical_file_hashes_to_none(self) -> None:
        """정본 파일이 없으면 `None` — `"0"*64` 로 채우지 않는다."""
        self.assertIsNone(fz.file_sha256(Path("config/does_not_exist.yaml")))

    def test_existing_canonical_file_hashes(self) -> None:
        digest = fz.file_sha256(REPO_ROOT / "config" / "economic_config.yaml")
        self.assertIsNotNone(digest)
        self.assertEqual(64, len(digest or ""))


class TestPartialLockHasScopeNote(unittest.TestCase):
    """★ AC-5 — 부분 Lock 은 범위를 문장으로 남긴다."""

    def test_partial_lock_has_scope_note(self) -> None:
        for item in fz.gate1_lock_items():
            if item.status in ("PARTIAL", "LOCKED"):
                with self.subTest(item=item.item):
                    self.assertTrue(item.scope_note.strip())

    def test_empty_scope_note_cannot_be_constructed(self) -> None:
        """★ 생성자가 막는다 — 만들 수 있으면 게시까지 살아남는다."""
        for status in ("PARTIAL", "LOCKED"):
            with self.subTest(status=status):
                with self.assertRaises(ValueError) as caught:
                    fz.LockItem("EVENT_SCHEMA_v1", status, "measurement", "  ")
                self.assertIn("전체를 Lock 한 것으로 읽힌다", str(caught.exception))

    def test_out_of_scope_may_omit_scope_note(self) -> None:
        """다른 파트 소관은 범위 문구가 필요 없다 — 우리가 봉인하지 않는다."""
        fz.LockItem("SERVICE_v1", "OUT_OF_SCOPE", "commerce", "")

    def test_unknown_lock_item_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            fz.LockItem("MADE_UP_v1", "PENDING", "measurement", "x")


class TestNineLockItems(unittest.TestCase):
    """AC-6 — Lock 9종 전부. **빼면 '봉인 대상이 아니다'와 '잊었다'가 같아진다.**"""

    def test_exactly_nine_items(self) -> None:
        self.assertEqual(9, len(fz.LOCK_ITEMS))
        self.assertEqual(9, len(fz.gate1_lock_items()))

    def test_item_ids_match_prd_22(self) -> None:
        self.assertEqual(
            set(fz.LOCK_ITEMS), {item.item for item in fz.gate1_lock_items()}
        )

    def test_c1_locks_nothing_completely(self) -> None:
        """★ **완전 Lock 0종.** `gate1-lock-scope.md` §4 의 분류다."""
        statuses = [item.status for item in fz.gate1_lock_items()]
        self.assertEqual(0, statuses.count("LOCKED"), "C1 은 완전 Lock 을 하지 않는다")
        self.assertEqual(5, statuses.count("OUT_OF_SCOPE"), "다른 파트 소관 5종")
        self.assertEqual(4, statuses.count("PARTIAL") + statuses.count("PENDING"))

    def test_measurement_owns_exactly_four(self) -> None:
        """★ 측정 계층 소유 4종이 "부분/조건부 가능" 에 정확히 대응한다.

        우연이 아니라 범위의 결과다 — 우리가 봉인할 수 있는 것만 봉인 대기다.
        """
        owned = [
            item.item for item in fz.gate1_lock_items()
            if item.owner_part == "measurement"
        ]
        self.assertEqual(
            {"EVENT_SCHEMA_v1", "ECONOMIC_RULE_v1", "CHURN_DEFINITION_v1",
             "KPI_DEFINITION_v1"},
            set(owned),
        )

    def test_other_parts_are_out_of_scope_not_pending(self) -> None:
        """★ 남의 소관을 `PENDING` 으로 적으면 우리가 안 한 것처럼 보인다."""
        for item in fz.gate1_lock_items():
            if item.owner_part != "measurement":
                with self.subTest(item=item.item):
                    self.assertEqual("OUT_OF_SCOPE", item.status)


class TestPreconditions(unittest.TestCase):
    """AC-3 — G-1~G-16. **하나라도 미충족이면 Lock 하지 않는다.**"""

    def test_sixteen_preconditions(self) -> None:
        self.assertEqual(16, len(fz.GATE1_PRECONDITIONS))

    def test_ids_are_g1_to_g16(self) -> None:
        self.assertEqual(
            {f"G-{n}" for n in range(1, 17)},
            {item.id for item in fz.GATE1_PRECONDITIONS},
        )

    def test_every_precondition_has_evidence(self) -> None:
        """★ 충족이든 미충족이든 **왜 그렇게 판정했는지**가 있어야 한다."""
        for item in fz.GATE1_PRECONDITIONS:
            with self.subTest(gate=item.id):
                self.assertTrue(
                    item.evidence.strip(),
                    f"{item.id} 의 판정 근거가 비었다 — 근거 없는 충족은 주장이다",
                )

    def test_unverified_is_not_recorded_as_unmet(self) -> None:
        """★★ `met is None`(확인하지 않았다)과 `False`(확인했고 미충족)를 나눈다.

        확인하지 않은 것을 미충족으로 적으면 **우리가 확인했다는 주장**이 되고,
        충족으로 적으면 **미실행을 통과로 표시**하는 것이 된다. 셋째 값이 필요하다.
        """
        unverified = [
            item for item in fz.GATE1_PRECONDITIONS if item.met is None
        ]
        for item in unverified:
            with self.subTest(gate=item.id):
                self.assertIsNot(False, item.met)
                self.assertIn(
                    "확인하지 않았다", item.evidence,
                    f"{item.id} 가 met=None 인데 그 사실이 근거에 없다",
                )

    def test_can_lock_is_blocked_by_unverified_too(self) -> None:
        """★ `None` 도 Lock 을 막는다 — 확인하지 않은 것은 충족이 아니다."""
        verification = fz.verify(
            preconditions=[
                fz.Precondition("G-1", "충족", True, "e"),
                fz.Precondition("G-10", "확인하지 않았다", None, "e"),
            ],
            items=lock_items(), lock_record=None,
        )
        self.assertFalse(verification.can_lock)
        self.assertEqual(["G-10"], [item.id for item in verification.unmet])

    def test_record_refuses_when_a_precondition_is_unmet(self) -> None:
        """★★ Lock 을 **실행**하려면 16종 전부 `True` 여야 한다."""
        verification = fz.verify(
            preconditions=fz.GATE1_PRECONDITIONS,
            items=fz.gate1_lock_items(), lock_record=None,
        )
        if verification.can_lock:
            self.skipTest(
                "선행 조건이 전부 충족됐다 — 거부 경로를 탈 수 없다. "
                "그 자체가 좋은 신호이며 Lock 실행이 가능하다는 뜻이다"
            )
        with self.assertRaises(FreezeViolation) as caught:
            fz.record(
                verification, locked_by="Phillip", canonical_files=[],
                repo_commit="abc123", now=datetime.now(KST),
            )
        message = str(caught.exception)
        self.assertIn("선행 조건", message)
        self.assertIn("FREEZE-003", message)
        for item in verification.unmet:
            with self.subTest(gate=item.id):
                self.assertIn(item.id, message, "무엇이 막았는지 이름으로 말한다")


class TestLockedByIsAPerson(unittest.TestCase):
    """봉인은 책임 소재가 있는 행위다."""

    def test_placeholder_names_are_refused(self) -> None:
        for name in ("", "   ", "agent", "unknown", "n/a", "-", "AGENT"):
            with self.subTest(locked_by=name):
                with self.assertRaises(FreezeViolation):
                    fz.build_record(
                        locked_by=name, items=lock_items(), canonical_files=[],
                        repo_commit="abc", now=datetime.now(KST),
                    )

    def test_a_real_name_is_accepted_and_trimmed(self) -> None:
        record = fz.build_record(
            locked_by="  Phillip  ", items=lock_items(), canonical_files=[],
            repo_commit="abc", now=datetime.now(KST),
        )
        self.assertEqual("Phillip", record["locked_by"])


class TestTimestampIsKst(unittest.TestCase):
    def test_locked_at_is_kst(self) -> None:
        record = fz.build_record(
            locked_by="Phillip", items=lock_items(), canonical_files=[],
            repo_commit="abc", now=datetime(2026, 9, 11, 13, 58, 2, tzinfo=KST),
        )
        self.assertTrue(str(record["locked_at"]).endswith("+09:00"))
        self.assertEqual("2026-09-11T13:58:02.000+09:00", record["locked_at"])

    def test_utc_input_is_converted_not_relabelled(self) -> None:
        record = fz.build_record(
            locked_by="Phillip", items=lock_items(), canonical_files=[],
            repo_commit="abc",
            now=datetime(2026, 9, 11, 4, 58, 2, tzinfo=timezone.utc).astimezone(KST),
        )
        self.assertEqual("2026-09-11T13:58:02.000+09:00", record["locked_at"])


class TestHashMismatchIsDetected(unittest.TestCase):
    """★ 봉인 이후 변경을 **실패로** 잡는다. 경고가 아니다."""

    def test_mismatch_sets_violated(self) -> None:
        verification = fz.verify(
            preconditions=[fz.Precondition("G-1", "x", True, "e")],
            items=lock_items(),
            lock_record={
                "canonical_files": {"config/economic_config.yaml": "0" * 64}
            },
            repo_root=REPO_ROOT,
        )
        self.assertEqual("violated", verification.overall)
        self.assertEqual("mismatch", verification.verification)
        self.assertEqual(1, len(verification.mismatches))
        self.assertIn("FREEZE-003", verification.detail)

    def test_match_sets_partial(self) -> None:
        target = REPO_ROOT / "config" / "economic_config.yaml"
        verification = fz.verify(
            preconditions=[fz.Precondition("G-1", "x", True, "e")],
            items=lock_items(),
            lock_record={
                "canonical_files": {
                    "config/economic_config.yaml": fz.file_sha256(target)
                }
            },
            repo_root=REPO_ROOT,
        )
        self.assertEqual("match", verification.verification)
        self.assertEqual((), verification.mismatches)

    def test_deleted_canonical_file_is_a_mismatch(self) -> None:
        """★ 파일이 사라진 것도 불일치다 — *"해시를 못 구했다"* 로 넘기지 않는다."""
        verification = fz.verify(
            preconditions=[fz.Precondition("G-1", "x", True, "e")],
            items=lock_items(),
            lock_record={"canonical_files": {"config/gone.yaml": "a" * 64}},
            repo_root=REPO_ROOT,
        )
        self.assertEqual("mismatch", verification.verification)
        self.assertIn("파일 없음", verification.mismatches[0])


class TestThreeLayersAgree(unittest.TestCase):
    """★★ AC-4 — 탐지 3층이 **같은 함수**를 쓴다. 판정이 갈리지 않는다."""

    def test_publish_delegates_to_verify(self) -> None:
        """2층(게시)이 자기 판정을 하지 않고 `freeze.verify()` 를 부른다."""
        source = (
            REPO_ROOT / "src" / "measurement" / "publish.py"
        ).read_text(encoding="utf-8")
        self.assertIn("fz.verify(", source)
        self.assertIn("fz.to_artifact(", source)
        # publish 가 자기 사본의 선행 조건 표를 들고 있으면 갈린다.
        self.assertNotIn("_GATE1_ROWS", source)
        self.assertNotIn("_LOCK_ROWS", source)

    def test_artifact_matches_the_verification(self) -> None:
        """게시물이 판정을 **그대로** 옮긴다 — 옮기는 동안 바꾸지 않는다."""
        verification = fz.verify(
            preconditions=fz.GATE1_PRECONDITIONS,
            items=fz.gate1_lock_items(), lock_record=None,
        )
        artifact = fz.to_artifact(verification)
        self.assertEqual(verification.overall, artifact["overall"])
        self.assertEqual(9, len(artifact["items"]))
        self.assertEqual(
            [item.id for item in verification.unmet],
            [entry["id"] for entry in artifact["unlocked_items"]],
        )

    def test_artifact_keeps_met_none_distinct_from_false(self) -> None:
        """★ 게시물까지 `null` 이 살아가야 화면이 두 상태를 구분할 수 있다."""
        artifact = fz.to_artifact(
            fz.verify(
                preconditions=[
                    fz.Precondition("G-10", "확인하지 않았다", None, "e"),
                    fz.Precondition("G-15", "미충족", False, "e"),
                ],
                items=lock_items(), lock_record=None,
            )
        )
        by_id = {entry["id"]: entry["met"] for entry in artifact["unlocked_items"]}
        self.assertIsNone(by_id["G-10"])
        self.assertIs(False, by_id["G-15"])

    def test_lock_record_is_null_when_absent(self) -> None:
        """★ 없는 Lock 을 있는 것처럼 적지 않는다."""
        artifact = fz.to_artifact(
            fz.verify(
                preconditions=fz.GATE1_PRECONDITIONS,
                items=fz.gate1_lock_items(), lock_record=None,
            )
        )
        self.assertIsNone(artifact["lock_record"])


class TestChecklistDocument(unittest.TestCase):
    """AC-3 — `docs/gate1_checklist.md` 가 코드와 일치한다."""

    CHECKLIST = REPO_ROOT / "docs" / "gate1_checklist.md"

    def setUp(self) -> None:
        self.assertTrue(self.CHECKLIST.exists(), "gate1_checklist.md 가 없다")
        self.document = self.CHECKLIST.read_text(encoding="utf-8")

    def test_every_precondition_is_listed(self) -> None:
        for item in fz.GATE1_PRECONDITIONS:
            with self.subTest(gate=item.id):
                self.assertIn(item.id, self.document)

    def test_every_lock_item_is_listed(self) -> None:
        for item in fz.LOCK_ITEMS:
            with self.subTest(item=item):
                self.assertIn(item, self.document)

    def test_no_lock_rule_is_stated(self) -> None:
        """★ *"하나라도 미충족이면 Lock 하지 않는다"* 가 있어야 한다."""
        self.assertIn("하나라도 미충족이면", self.document)

    def test_experiment_environment_declaration_is_refused(self) -> None:
        self.assertIn("EXPERIMENT_ENVIRONMENT_v1", self.document)
        self.assertIn("선언하지 않는다", self.document)

    def test_verification_commands_are_conditions(self) -> None:
        self.assertIn("unittest discover -s tests", self.document)
        self.assertIn("gen_event_schema_doc.py", self.document)

    def test_non_conditions_are_separated(self) -> None:
        """★ 조건을 부풀리지 않는다 — Lock 전 조건이 **아닌** 것이 구분돼 있다."""
        self.assertIn("조건이 아닌", self.document)

    def test_unsealed_five_are_recorded(self) -> None:
        """미봉인 5종과 사유."""
        self.assertIn("미봉인", self.document)
        for item in fz.LOCK_ITEMS:
            if any(
                entry.item == item and entry.owner_part != "measurement"
                for entry in fz.gate1_lock_items()
            ):
                with self.subTest(item=item):
                    self.assertIn(item, self.document)

    def test_current_state_matches_the_code(self) -> None:
        """★ 문서가 적은 충족 수가 실제 판정과 같은가 — 낡으면 실패한다."""
        met = sum(1 for item in fz.GATE1_PRECONDITIONS if item.met is True)
        unmet = len(fz.GATE1_PRECONDITIONS) - met
        self.assertIn(
            f"충족 {met}", self.document,
            f"문서의 충족 수가 실제({met})와 다르다 — freeze.py 가 정본이다",
        )
        self.assertIn(f"미충족 {unmet}", self.document)



# ── #163 — 시뮬레이터 Lock 5종을 증거로 LOCKED 기록 ─────────────────────────

SIM_COMMIT = "0123456789abcdef0123456789abcdef01234567"
SIMULATOR_FOUR = (
    "CUSTOMER_PERSONA_v1", "HIDDEN_TRAIT_RULE_v1", "BEHAVIOR_RULE_v1",
    "TREATMENT_RESPONSE_v1",
)
CHURN = "CHURN_DEFINITION_v1"
SIMULATOR_CONFIG = "config/simulator_config.yaml"
MEASUREMENT_CANONICAL = [
    Path("src/measurement/schema.py"),
    Path("config/economic_config.yaml"),
    Path("docs/event_schema.md"),
    Path("docs/measurement_contract.md"),
]
NEEDS_YAML = (
    "BLOCKED: PyYAML 미설치 — Lock 기록을 쓰고 읽지 못해 서명 경로를 검증하지 않았다"
)


def churn_met() -> fz.ChurnThresholdEvidence:
    return fz.ChurnThresholdEvidence(
        met=True, evidence="docs/research/churn_threshold_check.md — §5.1 ①~④ 충족",
    )


def statuses(items: object) -> dict[str, str]:
    return {item.item: item.status for item in items}  # type: ignore[attr-defined]


def ready() -> fz.FreezeVerification:
    """선행 조건만 보는 서명 전 판정. 테스트는 서명 경로를 실제 기록 없이 탄다."""
    return fz.verify(
        preconditions=fz.GATE1_PRECONDITIONS, items=fz.gate1_lock_items(),
        lock_record=None,
    )


class TestSigningItemsFollowEvidence(unittest.TestCase):
    """★ 서명 시점의 항목 상태는 **증거**가 정한다. 증거 없이 LOCKED 가 되지 않는다."""

    def test_without_evidence_the_code_defaults_are_signed(self) -> None:
        self.assertEqual(fz.gate1_lock_items(), fz.lock_items_at_signing())

    def test_simulator_commit_locks_the_four_simulator_items(self) -> None:
        signed = statuses(fz.lock_items_at_signing(simulator_commit=SIM_COMMIT))
        for item in SIMULATOR_FOUR:
            with self.subTest(item=item):
                self.assertEqual("LOCKED", signed[item])
        self.assertEqual("PARTIAL", signed[CHURN], "§5.1 증거 없이 CHURN 을 올리지 않는다")

    def test_unmet_churn_evidence_keeps_churn_partial(self) -> None:
        unmet = fz.ChurnThresholdEvidence(met=False, evidence="④ 이탈률 27% — 범위 밖")
        signed = statuses(fz.lock_items_at_signing(
            simulator_commit=SIM_COMMIT, churn_evidence=unmet,
        ))
        self.assertEqual("PARTIAL", signed[CHURN])

    def test_full_evidence_locks_all_five(self) -> None:
        signed = fz.lock_items_at_signing(
            simulator_commit=SIM_COMMIT, churn_evidence=churn_met(),
        )
        for item in signed:
            if item.item in (*SIMULATOR_FOUR, CHURN):
                with self.subTest(item=item.item):
                    self.assertEqual("LOCKED", item.status)
                    self.assertEqual((SIMULATOR_CONFIG,), item.canonical_files)
                    self.assertTrue(item.scope_note.strip())

    def test_measurement_items_are_not_touched(self) -> None:
        """측정 3종 · SERVICE 는 이번 결정 밖이다 — 증거가 있어도 기본값 그대로다."""
        defaults = statuses(fz.gate1_lock_items())
        signed = statuses(fz.lock_items_at_signing(
            simulator_commit=SIM_COMMIT, churn_evidence=churn_met(),
        ))
        for item in ("SERVICE_v1", "EVENT_SCHEMA_v1", "ECONOMIC_RULE_v1", "KPI_DEFINITION_v1"):
            with self.subTest(item=item):
                self.assertEqual(defaults[item], signed[item])

    def test_met_churn_evidence_without_simulator_commit_is_refused(self) -> None:
        """④ 는 시뮬레이터 재생성 결과다. 어느 시뮬레이터인지 없으면 증거가 아니다."""
        with self.assertRaises(FreezeViolation) as caught:
            fz.lock_items_at_signing(churn_evidence=churn_met())
        self.assertIn("simulator_commit", str(caught.exception))

    def test_placeholder_simulator_commits_are_refused(self) -> None:
        for bad in ("", "unknown", "0", "abc123", SIM_COMMIT.upper(), SIM_COMMIT[:-1]):
            with self.subTest(simulator_commit=bad):
                with self.assertRaises(FreezeViolation):
                    fz.lock_items_at_signing(simulator_commit=bad)

    def test_churn_evidence_needs_a_reason(self) -> None:
        for met in (True, False):
            with self.subTest(met=met):
                with self.assertRaises(ValueError):
                    fz.ChurnThresholdEvidence(met=met, evidence="  ")

    def test_locked_item_without_canonical_files_cannot_be_constructed(self) -> None:
        """계약이 LOCKED 항목에 정본 파일을 요구한다 — 만들 수 있으면 게시까지 살아남는다."""
        with self.assertRaises(ValueError):
            fz.LockItem("BEHAVIOR_RULE_v1", "LOCKED", "simulator", "범위")

    def test_build_record_refuses_simulator_lock_without_commit(self) -> None:
        """기록 작성기도 같은 불변식을 지킨다 — `lock_items_at_signing()` 을 거치지 않아도."""
        items = fz.lock_items_at_signing(simulator_commit=SIM_COMMIT)
        with self.assertRaises(FreezeViolation):
            fz.build_record(
                locked_by="Phillip", items=items, canonical_files=[],
                repo_commit="abc", now=datetime.now(KST), simulator_commit=None,
            )

    def test_build_record_refuses_churn_lock_without_met_evidence(self) -> None:
        items = fz.lock_items_at_signing(
            simulator_commit=SIM_COMMIT, churn_evidence=churn_met(),
        )
        with self.assertRaises(FreezeViolation):
            fz.build_record(
                locked_by="Phillip", items=items, canonical_files=[],
                repo_commit="abc", now=datetime.now(KST),
                simulator_commit=SIM_COMMIT, churn_evidence=None,
            )


@unittest.skipUnless(yaml_available(), NEEDS_YAML)
class TestRecordWritesEvidence(unittest.TestCase):
    """`record()` 가 증거를 받아 기록에 남긴다. ★ 임시 경로에만 쓴다."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.path = Path(self._tmp.name) / "gate1_lock.yaml"

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def _sign(self, verification: fz.FreezeVerification | None = None, **evidence: object):
        return fz.record(
            verification or ready(), locked_by="Phillip",
            canonical_files=MEASUREMENT_CANONICAL, repo_commit="a" * 40,
            now=datetime(2026, 11, 9, 10, 0, tzinfo=KST), path=self.path,
            assumptions=fz.gate1_assumptions(), **evidence,
        )

    def test_full_evidence_records_five_locked_with_hash_and_commit(self) -> None:
        payload = self._sign(simulator_commit=SIM_COMMIT, churn_evidence=churn_met())
        written = fz.load_record(self.path)
        self.assertEqual(payload, dict(written))
        by_item = {entry["item"]: entry for entry in written["items"]}
        for item in (*SIMULATOR_FOUR, CHURN):
            with self.subTest(item=item):
                self.assertEqual("LOCKED", by_item[item]["status"])
                self.assertEqual([SIMULATOR_CONFIG], by_item[item]["canonical_files"])
        self.assertEqual(
            fz.file_sha256(REPO_ROOT / SIMULATOR_CONFIG),
            written["canonical_files"][SIMULATOR_CONFIG],
        )
        self.assertEqual(SIM_COMMIT, written["simulator_commit"])
        self.assertNotIn("simulator_commit_null_reason", written)
        self.assertEqual(
            {"met": True, "evidence": churn_met().evidence},
            dict(written["churn_threshold_evidence"]),
        )

    def test_without_evidence_nothing_simulator_side_is_locked(self) -> None:
        written = self._sign()
        signed = {entry["item"]: entry["status"] for entry in written["items"]}
        for item in SIMULATOR_FOUR:
            with self.subTest(item=item):
                self.assertEqual("OUT_OF_SCOPE", signed[item])
        self.assertEqual("PARTIAL", signed[CHURN])
        self.assertIsNone(written["simulator_commit"])
        self.assertNotIn(SIMULATOR_CONFIG, written["canonical_files"])

    def test_stale_locked_items_are_not_carried_over(self) -> None:
        """★ 이전 기록이 LOCKED 여도 이번 서명에 증거가 없으면 LOCKED 로 남기지 않는다.

        verification.items 를 이어 쓰면 simulator_commit 이 null 인 기록에 LOCKED
        시뮬레이터 항목이 남는다 — 무엇으로 봉인했는지 모르는 봉인이다.
        """
        stale = fz.verify(
            preconditions=fz.GATE1_PRECONDITIONS,
            items=fz.lock_items_at_signing(
                simulator_commit=SIM_COMMIT, churn_evidence=churn_met(),
            ),
            lock_record=None,
        )
        written = self._sign(stale)
        self.assertNotIn("LOCKED", {entry["status"] for entry in written["items"]})

    def _assert_reseal_reproduces(self, current: object) -> None:
        """기록에 적힌 증거로 다시 서명하면 같은 항목 · 선언 · 증거가 나온다."""
        simulator_commit, churn_evidence = fz.recorded_signing_evidence(current)
        written = self._sign(simulator_commit=simulator_commit, churn_evidence=churn_evidence)
        self.assertEqual(
            [dict(entry) for entry in current["items"]],
            [dict(entry) for entry in written["items"]],
        )
        for key in ("declaration", "experiment_environment_v1_declared", "simulator_commit"):
            with self.subTest(key=key):
                self.assertEqual(current[key], written[key])
        self.assertEqual(
            current.get("churn_threshold_evidence"), written.get("churn_threshold_evidence"),
        )

    def test_resealing_with_the_recorded_evidence_reproduces_the_current_record(self) -> None:
        """지금 기록이 서명 전(LOCKED 0종)이든 서명 후(5종 LOCKED)든 성립한다.

        서명 전 기록은 증거가 없으므로 증거 없는 재서명과 같다 — #163 전 동작 보존.
        """
        current = fz.load_record()
        if current is None:
            self.skipTest("BLOCKED: Lock 기록이 없다 — 대조하지 않았다 (통과가 아니다)")
        self._assert_reseal_reproduces(current)

    def test_reseal_parity_holds_for_a_five_locked_record(self) -> None:
        """회귀 — 정상 서명한 5종 LOCKED 기록에서도 위 대조가 통과한다.

        처음 판은 "현재 기록 = 코드 기본값" 을 단언해, §5.2 절차대로 서명하는 순간
        CI 가 빨개졌다 (#163 리뷰 중요-1).
        """
        self._sign(simulator_commit=SIM_COMMIT, churn_evidence=churn_met())
        self._assert_reseal_reproduces(fz.load_record(self.path))

class TestDeclarationIsDerived(unittest.TestCase):
    """declaration 은 인자가 아니라 항목에서 유도한다 — SERVICE_v1 을 뺀 8종 전부 LOCKED 일 때만 FULL."""

    def _record(self, items, **evidence):
        return fz.build_record(
            locked_by="Phillip", items=items, canonical_files=[],
            repo_commit="abc", now=datetime.now(KST), **evidence,
        )

    def test_full_evidence_today_is_still_partial(self) -> None:
        """측정 3종이 LOCKED 가 아니므로 5종을 올려도 PARTIAL 이다."""
        record = self._record(
            fz.lock_items_at_signing(simulator_commit=SIM_COMMIT, churn_evidence=churn_met()),
            simulator_commit=SIM_COMMIT, churn_evidence=churn_met(),
        )
        self.assertEqual("PARTIAL_FREEZE", record["declaration"])
        self.assertIs(False, record["experiment_environment_v1_declared"])

    def test_every_item_but_service_locked_is_full(self) -> None:
        overrides = {item: "LOCKED" for item in fz.LOCK_ITEMS if item != "SERVICE_v1"}
        record = self._record(
            lock_items(SERVICE_v1="OUT_OF_SCOPE", **overrides),
            simulator_commit=SIM_COMMIT, churn_evidence=churn_met(),
        )
        self.assertEqual("FULL_FREEZE", record["declaration"])
        self.assertIs(True, record["experiment_environment_v1_declared"])

    def test_one_unlocked_item_keeps_partial(self) -> None:
        overrides = {
            item: "LOCKED" for item in fz.LOCK_ITEMS
            if item not in ("SERVICE_v1", "KPI_DEFINITION_v1")
        }
        record = self._record(
            lock_items(**overrides), simulator_commit=SIM_COMMIT,
            churn_evidence=churn_met(),
        )
        self.assertEqual("PARTIAL_FREEZE", record["declaration"])
        self.assertIs(False, record["experiment_environment_v1_declared"])

    def test_verify_seals_under_the_same_rule(self) -> None:
        """게시 overall 과 기록 declaration 이 같은 규칙을 쓴다 — 갈리면 화면과 기록이 다르다."""
        overrides = {item: "LOCKED" for item in fz.LOCK_ITEMS if item != "SERVICE_v1"}
        verification = fz.verify(
            preconditions=[fz.Precondition("G-1", "x", True, "e")],
            items=lock_items(SERVICE_v1="OUT_OF_SCOPE", **overrides),
            lock_record={"canonical_files": {
                "config/economic_config.yaml":
                    fz.file_sha256(REPO_ROOT / "config/economic_config.yaml"),
            }},
            repo_root=REPO_ROOT,
        )
        self.assertEqual("match", verification.verification)
        self.assertEqual("sealed", verification.overall)


class TestItemsComeFromTheSignedRecord(unittest.TestCase):
    """★★ AC-4 — verify · 게시 · 테스트가 쓰는 항목 목록이 같은 함수에서 나온다."""

    def _record(self) -> dict[str, object]:
        items = fz.lock_items_at_signing(
            simulator_commit=SIM_COMMIT, churn_evidence=churn_met(),
        )
        return fz.build_record(
            locked_by="Phillip", items=items, canonical_files=MEASUREMENT_CANONICAL,
            repo_commit="a" * 40, now=datetime(2026, 11, 9, 10, 0, tzinfo=KST),
            simulator_commit=SIM_COMMIT, churn_evidence=churn_met(),
        )

    def test_record_statuses_are_used(self) -> None:
        items = fz.gate1_lock_items(self._record())
        signed = statuses(items)
        for item in (*SIMULATOR_FOUR, CHURN):
            with self.subTest(item=item):
                self.assertEqual("LOCKED", signed[item])
        self.assertEqual(
            fz.lock_items_at_signing(simulator_commit=SIM_COMMIT, churn_evidence=churn_met()),
            items,
        )

    def test_without_a_readable_record_the_code_defaults_are_used(self) -> None:
        for record in (None, fz.RECORD_UNREADABLE):
            with self.subTest(record=record):
                self.assertEqual(fz.gate1_lock_items(), fz.gate1_lock_items(record))

    def test_malformed_record_items_raise_config_error(self) -> None:
        good = self._record()
        cases = {
            "missing": {**good, "items": good["items"][:-1]},
            "duplicated": {**good, "items": [*good["items"][:-1], good["items"][0]]},
            "unknown_status": {
                **good,
                "items": [{**good["items"][0], "status": "SORT_OF_LOCKED"},
                          *good["items"][1:]],
            },
            "not_a_list": {**good, "items": "items"},
            "locked_without_files": {
                **good,
                "items": [
                    {k: v for k, v in entry.items() if k != "canonical_files"}
                    for entry in good["items"]
                ],
            },
        }
        for name, broken in cases.items():
            with self.subTest(case=name):
                with self.assertRaises(ConfigError):
                    fz.gate1_lock_items(broken)

    def test_locked_items_carry_per_file_verification(self) -> None:
        artifact = fz.to_artifact(fz.verify(
            preconditions=fz.GATE1_PRECONDITIONS,
            items=fz.gate1_lock_items(self._record()), lock_record=self._record(),
            repo_root=REPO_ROOT,
        ))
        current = fz.file_sha256(REPO_ROOT / SIMULATOR_CONFIG)
        for entry in artifact["items"]:
            if entry["status"] == "LOCKED":
                with self.subTest(item=entry["item"]):
                    self.assertEqual(
                        [{"path": SIMULATOR_CONFIG, "locked_sha256": current,
                          "current_sha256": current, "verification": "match"}],
                        entry["canonical_files"],
                    )
                    self.assertNotIn("reason_detail", entry)

    def test_changed_simulator_config_is_a_per_item_mismatch(self) -> None:
        record = self._record()
        record["canonical_files"] = {**record["canonical_files"], SIMULATOR_CONFIG: "0" * 64}
        verification = fz.verify(
            preconditions=fz.GATE1_PRECONDITIONS, items=fz.gate1_lock_items(record),
            lock_record=record, repo_root=REPO_ROOT,
        )
        self.assertEqual("violated", verification.overall)
        artifact = fz.to_artifact(verification)
        locked = [entry for entry in artifact["items"] if entry["status"] == "LOCKED"]
        self.assertEqual(5, len(locked))
        for entry in locked:
            with self.subTest(item=entry["item"]):
                self.assertEqual("mismatch", entry["canonical_files"][0]["verification"])

    def test_locked_file_absent_from_the_record_is_a_mismatch(self) -> None:
        """LOCKED 항목의 정본 해시가 기록에 없으면 대조할 것이 없다 — 일치가 아니다."""
        record = self._record()
        record["canonical_files"] = {
            path: digest for path, digest in record["canonical_files"].items()
            if path != SIMULATOR_CONFIG
        }
        verification = fz.verify(
            preconditions=fz.GATE1_PRECONDITIONS, items=fz.gate1_lock_items(record),
            lock_record=record, repo_root=REPO_ROOT,
        )
        self.assertEqual("mismatch", verification.verification)

    def test_publish_reads_items_from_the_record(self) -> None:
        source = (REPO_ROOT / "src" / "measurement" / "publish.py").read_text(encoding="utf-8")
        self.assertIn("fz.gate1_lock_items(record)", source)


@unittest.skipUnless(yaml_available(), NEEDS_YAML)
class TestPublicationFollowsTheSignedRecord(unittest.TestCase):
    """게시(2층)가 서명 기록의 상태를 싣는다. ★ 실제 기록 파일은 건드리지 않는다."""

    def _assert_publication_follows_recorded_evidence(
        self, record: object, path: Path,
    ) -> None:
        """게시 항목 = 기록에 적힌 증거로 다시 계산한 서명 항목."""
        simulator_commit, churn_evidence = fz.recorded_signing_evidence(record)
        expected = fz.lock_items_at_signing(
            simulator_commit=simulator_commit, churn_evidence=churn_evidence,
        )
        self.assertEqual(expected, fz.gate1_lock_items(record))
        expected_artifact = fz.to_artifact(fz.verify(
            preconditions=fz.GATE1_PRECONDITIONS, items=expected,
            lock_record=record, lock_record_path=path,
        ))
        with mock.patch.object(fz, "DEFAULT_LOCK_RECORD", path):
            self.assertEqual(expected_artifact, build_freeze_status())

    def test_current_record_publishes_the_items_its_evidence_signs(self) -> None:
        """#163 전후 게시 결과 불변 — 증거 없는 기록이면 코드 기본값과 같다."""
        record = fz.load_record()
        if record is None:
            self.skipTest("BLOCKED: Lock 기록이 없다 — 대조하지 않았다 (통과가 아니다)")
        self._assert_publication_follows_recorded_evidence(record, fz.DEFAULT_LOCK_RECORD)
        if fz.recorded_signing_evidence(record) == (None, None):
            self.assertEqual(fz.gate1_lock_items(), fz.gate1_lock_items(record))

    def test_publication_parity_holds_for_a_five_locked_record(self) -> None:
        """회귀 — 정상 서명한 5종 LOCKED 기록을 주입해도 위 대조가 통과한다 (리뷰 중요-1)."""
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "gate1_lock.yaml"
            fz.record(
                ready(), locked_by="Phillip", canonical_files=MEASUREMENT_CANONICAL,
                repo_commit="a" * 40, now=datetime(2026, 11, 9, 10, 0, tzinfo=KST),
                path=path, assumptions=fz.gate1_assumptions(),
                simulator_commit=SIM_COMMIT, churn_evidence=churn_met(),
            )
            record = fz.load_record(path)
            self.assertEqual(5, sum(1 for e in record["items"] if e["status"] == "LOCKED"))
            self._assert_publication_follows_recorded_evidence(record, path)

    def test_signed_record_reaches_the_publication(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "gate1_lock.yaml"
            fz.record(
                ready(), locked_by="Phillip", canonical_files=MEASUREMENT_CANONICAL,
                repo_commit="a" * 40, now=datetime(2026, 11, 9, 10, 0, tzinfo=KST),
                path=path, assumptions=fz.gate1_assumptions(),
                simulator_commit=SIM_COMMIT, churn_evidence=churn_met(),
            )
            with mock.patch.object(fz, "DEFAULT_LOCK_RECORD", path):
                artifact = build_freeze_status()
        published = {entry["item"]: entry["status"] for entry in artifact["items"]}
        for item in (*SIMULATOR_FOUR, CHURN):
            with self.subTest(item=item):
                self.assertEqual("LOCKED", published[item])
        self.assertEqual("match", artifact["verification"])
        self.assertEqual("partial", artifact["overall"])
        self.assertEqual(SIM_COMMIT, artifact["lock_record"]["simulator_commit"])

    def test_locked_publication_passes_the_contract(self) -> None:
        try:
            from jsonschema import Draft202012Validator
            from referencing import Registry, Resource
        except ImportError:
            self.skipTest(
                "BLOCKED: jsonschema 미설치 — LOCKED 게시물의 계약 적합성을 검증하지 않았다"
            )
        import json

        from src.measurement import publish as pub

        contracts = REPO_ROOT / "docs/contracts/measurement-publish/v1"
        base = "https://72offsuit.local/ai-roi/measurement-publish/v1/"
        registry = Registry().with_resources(
            (schema["$id"], Resource.from_contents(schema))
            for schema in (
                json.loads(p.read_text(encoding="utf-8"))
                for p in sorted(contracts.glob("*.schema.json"))
            )
        )
        validator = Draft202012Validator(
            {"$ref": f"{base}freeze_status.schema.json"}, registry=registry
        )
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "gate1_lock.yaml"
            fz.record(
                ready(), locked_by="Phillip", canonical_files=MEASUREMENT_CANONICAL,
                repo_commit="a" * 40, now=datetime(2026, 11, 9, 10, 0, tzinfo=KST),
                path=path, assumptions=fz.gate1_assumptions(),
                simulator_commit=SIM_COMMIT, churn_evidence=churn_met(),
            )
            out = Path(tmp) / "results"
            with mock.patch.object(fz, "DEFAULT_LOCK_RECORD", path):
                pub.publish(
                    source_root=Path(tmp) / "raw", output_root=out,
                    config_path=REPO_ROOT / "config/economic_config.yaml",
                )
            document = json.loads(
                (out / "measurement" / "freeze_status.json").read_text(encoding="utf-8")
            )
        self.assertEqual(
            5, sum(1 for entry in document["items"] if entry["status"] == "LOCKED"),
            "LOCKED 항목이 게시물에 없으면 계약의 LOCKED 분기를 검사하지 않은 것이다",
        )
        errors = [
            f"{'/'.join(str(p) for p in error.absolute_path)}: {error.message}"
            for error in validator.iter_errors(document)
        ]
        self.assertEqual([], errors, "\n".join(errors[:5]))



class TestRecordedInvariantsAreChecked(unittest.TestCase):
    """★ 읽기 경로도 쓰기 경로와 **같은 규칙**으로 기록을 검사한다 (리뷰 중요-2).

    구조만 보면 yaml 을 손으로 고쳐 LOCKED 를 만든 기록이 게시물에 LOCKED 로 실리고,
    선언과 항목이 어긋난 기록에서 verify() 가 sealed 를 낸다.
    """

    NOW = datetime(2026, 11, 9, 10, 0, tzinfo=KST)

    def _signed(self) -> dict[str, object]:
        return fz.build_record(
            locked_by="Phillip",
            items=fz.lock_items_at_signing(simulator_commit=SIM_COMMIT, churn_evidence=churn_met()),
            canonical_files=MEASUREMENT_CANONICAL, repo_commit="a" * 40, now=self.NOW,
            simulator_commit=SIM_COMMIT, churn_evidence=churn_met(),
        )

    def _unsigned(self) -> dict[str, object]:
        return fz.build_record(
            locked_by="Phillip", items=fz.lock_items_at_signing(),
            canonical_files=MEASUREMENT_CANONICAL, repo_commit="a" * 40, now=self.NOW,
        )

    def _full(self) -> dict[str, object]:
        overrides = {item: "LOCKED" for item in fz.LOCK_ITEMS if item != "SERVICE_v1"}
        return fz.build_record(
            locked_by="Phillip", items=lock_items(SERVICE_v1="OUT_OF_SCOPE", **overrides),
            canonical_files=[], repo_commit="a" * 40, now=self.NOW,
            simulator_commit=SIM_COMMIT, churn_evidence=churn_met(),
        )

    def assertRejected(self, record: dict[str, object]) -> None:
        with self.assertRaises(ConfigError):
            fz.gate1_lock_items(record)

    def test_well_formed_records_pass(self) -> None:
        for name, record in (
            ("unsigned", self._unsigned()), ("signed", self._signed()), ("full", self._full()),
        ):
            with self.subTest(record=name):
                self.assertEqual(9, len(fz.gate1_lock_items(record)))

    def test_current_lock_record_passes(self) -> None:
        record = fz.load_record()
        if record is None or record is fz.RECORD_UNREADABLE:
            self.skipTest(
                "BLOCKED: Lock 기록이 없거나 PyYAML 이 없어 읽지 못했다 — 대조하지 않았다"
            )
        self.assertEqual(9, len(fz.gate1_lock_items(record)))

    def test_locked_simulator_items_without_simulator_commit_are_rejected(self) -> None:
        self.assertRejected({**self._signed(), "simulator_commit": None})

    def test_placeholder_simulator_commit_is_rejected(self) -> None:
        for bad in ("unknown", "", 0, SIM_COMMIT[:7]):
            with self.subTest(simulator_commit=bad):
                self.assertRejected({**self._signed(), "simulator_commit": bad})

    def test_locked_churn_without_met_evidence_is_rejected(self) -> None:
        signed = self._signed()
        without = {k: v for k, v in signed.items() if k != "churn_threshold_evidence"}
        cases = {
            "absent": without,
            "null": {**signed, "churn_threshold_evidence": None},
            "unmet": {**signed, "churn_threshold_evidence": {"met": False, "evidence": "x"}},
        }
        for name, record in cases.items():
            with self.subTest(case=name):
                self.assertRejected(record)

    def test_malformed_churn_evidence_is_a_config_error(self) -> None:
        """형식이 틀린 증거가 AttributeError · TypeError 로 새지 않는다."""
        for bad in (
            "yes", ["met"], {"met": "true", "evidence": "x"}, {"met": True},
            {"evidence": "x"}, {"met": True, "evidence": 3}, {"met": True, "evidence": " "},
        ):
            with self.subTest(churn_threshold_evidence=bad):
                self.assertRejected({**self._signed(), "churn_threshold_evidence": bad})

    def test_hand_promoted_items_are_rejected(self) -> None:
        """서명 전 기록을 손으로 고쳐 LOCKED + 정본 해시를 넣어도 증거가 없으면 거부한다."""
        record = self._unsigned()
        record["items"] = [
            {**entry, "status": "LOCKED", "canonical_files": [SIMULATOR_CONFIG]}
            if entry["item"] in ("CUSTOMER_PERSONA_v1", CHURN) else entry
            for entry in record["items"]
        ]
        record["canonical_files"] = {
            **record["canonical_files"],
            SIMULATOR_CONFIG: fz.file_sha256(REPO_ROOT / SIMULATOR_CONFIG),
        }
        self.assertRejected(record)

    def test_declaration_must_match_the_items(self) -> None:
        cases = {
            "partial_record_claims_full": {**self._signed(), "declaration": "FULL_FREEZE"},
            "partial_record_declares_environment":
                {**self._signed(), "experiment_environment_v1_declared": True},
            "full_record_claims_partial": {**self._full(), "declaration": "PARTIAL_FREEZE"},
            "full_record_withholds_environment":
                {**self._full(), "experiment_environment_v1_declared": False},
            "declared_flag_not_bool": {**self._signed(), "experiment_environment_v1_declared": "false"},
            "declaration_missing":
                {k: v for k, v in self._signed().items() if k != "declaration"},
        }
        for name, record in cases.items():
            with self.subTest(case=name):
                self.assertRejected(record)

    def test_verify_cannot_seal_a_record_whose_declaration_disagrees(self) -> None:
        """측정 3종까지 손으로 LOCKED 로 고치고 선언은 PARTIAL 로 둔 기록 — sealed 로 가지 않는다."""
        record = {**self._full(), "declaration": "PARTIAL_FREEZE",
                  "experiment_environment_v1_declared": False}
        with self.assertRaises(ConfigError):
            fz.verify(
                preconditions=fz.GATE1_PRECONDITIONS, items=fz.gate1_lock_items(record),
                lock_record=record, repo_root=REPO_ROOT,
            )

    def test_recorded_signing_evidence_round_trips(self) -> None:
        self.assertEqual((SIM_COMMIT, churn_met()), fz.recorded_signing_evidence(self._signed()))
        self.assertEqual((None, None), fz.recorded_signing_evidence(self._unsigned()))


if __name__ == "__main__":
    unittest.main()
