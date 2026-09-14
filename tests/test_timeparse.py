"""Pins the RFC 3339 `Z` handling that the declared runtime could not parse.

Issue #62, review finding M3: the SRS declares `Target Runtime: Python 3.10+`,
but `datetime.fromisoformat()` did not accept a trailing `Z` until 3.11
(bpo-35829), and five call sites handed it `Z`-suffixed values straight from the
contract. CI pins 3.12, so nothing ever compared the declaration to reality.

★ On this interpreter the fix cannot be proven by parsing alone -- 3.11+ accepts
  `Z` with or without normalisation, so `parse_datetime("…Z")` passes either way.
  Two things carry the proof instead:

    1. `normalize_utc_suffix` is a pure string function, asserted directly. It is
       version-independent, so it says what the code does rather than what this
       interpreter tolerates.
    2. `.github/workflows/python-compat.yml` runs the suite on 3.10 itself. That
       is the end-to-end proof, and it is the reason the workflow exists: without
       it the fix regresses silently the moment someone writes `fromisoformat`
       again.

★ `test_no_module_parses_timestamps_directly` is the guard that keeps (2) honest.
  A new direct call would pass every test here while reopening the defect, and
  the 3.10 job would only catch it if that path happened to see a `Z`.
"""

from __future__ import annotations

import ast
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from src.measurement import timeparse as tp

MEASUREMENT = Path(__file__).resolve().parent.parent / "src" / "measurement"


class TestNormalizeUtcSuffix(unittest.TestCase):
    """순수 문자열 변환 — 인터프리터 버전과 무관하게 동작을 말한다."""

    def test_trailing_z_becomes_offset(self) -> None:
        self.assertEqual(
            "2025-10-01T23:30:00.000+00:00",
            tp.normalize_utc_suffix("2025-10-01T23:30:00.000Z"),
        )

    def test_existing_offset_is_untouched(self) -> None:
        value = "2025-10-01T09:00:00.000+09:00"
        self.assertEqual(value, tp.normalize_utc_suffix(value))

    def test_naive_timestamp_is_untouched(self) -> None:
        """오프셋이 없는 것은 그대로 둔다 — 거부는 호출자의 몫이다.

        `sink._normalize_timestamp()` 가 `tzinfo is None` 을 보고 거부한다.
        여기서 오프셋을 지어 붙이면 **순간을 특정할 수 없는 값에 UTC 를
        발명하는 것**이 된다.
        """
        value = "2025-10-01T23:30:00"
        self.assertEqual(value, tp.normalize_utc_suffix(value))

    def test_bare_z_is_not_a_timestamp(self) -> None:
        """`Z` 한 글자를 `+00:00` 으로 바꾸면 파싱 불가가 파싱 가능이 된다."""
        self.assertEqual("Z", tp.normalize_utc_suffix("Z"))

    def test_z_elsewhere_is_not_a_utc_marker(self) -> None:
        """끝이 아닌 `Z` 는 UTC 표시가 아니므로 고치지 않는다 — 여전히 실패해야 한다."""
        value = "2025-10-01TZ23:30:00"
        self.assertEqual(value, tp.normalize_utc_suffix(value))
        with self.assertRaises(ValueError):
            tp.parse_datetime(value)


class TestParseDatetime(unittest.TestCase):
    def test_z_suffix_parses_as_utc(self) -> None:
        moment = tp.parse_datetime("2025-10-01T23:30:00.000Z")
        self.assertEqual(timezone.utc, moment.tzinfo)
        self.assertEqual(timedelta(0), moment.utcoffset())

    def test_offset_form_is_equivalent(self) -> None:
        """`Z` 와 `+00:00` 이 같은 순간을 낸다 — 정규화가 값을 바꾸지 않는다."""
        self.assertEqual(
            tp.parse_datetime("2025-10-01T23:30:00.000Z"),
            tp.parse_datetime("2025-10-01T23:30:00.000+00:00"),
        )

    def test_unparseable_still_raises(self) -> None:
        """ValueError 를 삼키지 않는다.

        호출자가 '파싱 불가' 와 '파싱은 됐으나 오프셋 없음' 을 가른다.
        여기서 잡아 None 을 돌려주면 그 구분이 사라진다.
        """
        with self.assertRaises(ValueError):
            tp.parse_datetime("어제")

    def test_naive_still_parses(self) -> None:
        """오프셋 없는 값도 파싱은 된다 — 거부는 호출자가 한다."""
        moment = tp.parse_datetime("2025-10-01T23:30:00")
        self.assertIsNone(moment.tzinfo)


class TestNoModuleParsesTimestampsDirectly(unittest.TestCase):
    """★ 직접 호출이 다시 들어오면 수정이 조용히 우회된다."""

    #: `date.fromisoformat` 은 대상이 아니다. 3.10 에서도 `YYYY-MM-DD` 정확
    #: 형식만 받고 이 저장소가 넘기는 값이 정확히 그것이라 안전하다. `Z` 가
    #: 끼어들 자리가 없다.
    ALLOWED_IN = {"timeparse.py"}

    def test_no_direct_datetime_fromisoformat(self) -> None:
        offenders: list[str] = []
        scanned = 0
        for path in sorted(MEASUREMENT.glob("*.py")):
            if path.name in self.ALLOWED_IN:
                continue
            scanned += 1
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if not isinstance(node, ast.Attribute):
                    continue
                if node.attr != "fromisoformat":
                    continue
                owner = node.value
                # `datetime.fromisoformat` 만 잡는다. `date.fromisoformat` 은 안전하다.
                if isinstance(owner, ast.Name) and owner.id == "datetime":
                    offenders.append(f"{path.name}:{node.lineno}")
        self.assertGreater(scanned, 0, "모듈을 하나도 훑지 못했다 — 검사가 비어 있다")
        self.assertEqual(
            [], offenders,
            "datetime.fromisoformat 을 직접 부르는 곳이 있다. `Z` 접미사가 "
            "3.11 미만에서 ValueError 가 되므로 timeparse.parse_datetime 을 쓴다",
        )

    def test_scan_would_catch_a_direct_call(self) -> None:
        """검사가 실제로 잡는지 — 스캐너가 아무것도 못 잡으면 위 테스트는 무의미하다."""
        sample = ast.parse("import datetime\nx = datetime.fromisoformat('a')\n")
        found = [
            node for node in ast.walk(sample)
            if isinstance(node, ast.Attribute)
            and node.attr == "fromisoformat"
            and isinstance(node.value, ast.Name)
            and node.value.id == "datetime"
        ]
        self.assertEqual(1, len(found), "스캐너가 직접 호출을 인식하지 못한다")


class TestBehavesLikePython310(unittest.TestCase):
    """★ 3.10 인터프리터가 없어도 그 동작을 여기서 재현한다.

    `.github/workflows/python-compat.yml` 이 진짜 3.10 에서 전체 스위트를
    돌리는 것이 최종 증거다. 이 테스트는 그 잡이 없는 로컬에서도 **왜 수정이
    필요한지**를 실행으로 보여 준다 — 문서 근거만 남기지 않는다.
    """

    def test_normalized_value_parses_under_310_rules(self) -> None:
        """3.10 의 `fromisoformat` 은 `Z` 를 거부한다. 정규화하면 통과한다."""
        def fromisoformat_310(value: str) -> datetime:
            if value.endswith("Z"):
                raise ValueError(f"Invalid isoformat string: {value!r}")
            return datetime.fromisoformat(value)

        raw = "2025-10-01T23:30:00.000Z"
        with self.assertRaises(ValueError, msg="에뮬레이션이 동작하지 않으면 이 테스트는 무의미하다"):
            fromisoformat_310(raw)
        moment = fromisoformat_310(tp.normalize_utc_suffix(raw))
        self.assertEqual(timedelta(0), moment.utcoffset())
