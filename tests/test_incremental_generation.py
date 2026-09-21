"""The same events, generated in one pass or several, must publish the same facts.

Issue #99, raised from the commerce side and by the project's academic reviewer:
regenerating produced what looked like a brand-new world, so incremental data
collection was not meaningful. Underneath that was a concrete defect.

`EventSink` appends across instances on purpose -- its docstring says so, because
the simulator calls `advance()` repeatedly and writes each window with a fresh
sink. The **events** append correctly. `data/raw/manifest.json` does not: it is
rewritten each time, so after a second window it describes only that window. And
`publish` read field coverage back out of it.

The result was reproducible and specific: generate an `add_to_cart` in window one
and a `page_view` in window two, and the published report claimed `category` and
`product_id` had **never arrived** -- while sitting in an earlier partition.

★ The fix was not a better side-record. `publish` already reads every event, so
  it now counts coverage from them (`src/measurement/coverage.py`). This file is
  the regression test, and it is written as an **equality between two generation
  methods** rather than as an assertion about internals: any future change that
  reintroduces a write-time summary in the read path fails here, whatever shape
  it takes.

★ `test_the_comparison_can_fail` is what keeps that honest. An equality test
  between two publishes would also pass if both sides were broken in the same
  way, or if the fixture were too thin to exercise the difference. It builds the
  old behaviour by hand and confirms this fixture actually distinguishes it.
"""

from __future__ import annotations

import json
import tempfile
import unittest
import uuid
from pathlib import Path

from src.measurement import coverage as cov
from src.measurement.sink import EventSink

CUSTOMER = "C00000001"


def event(day: int, event_type: str, **extra: object) -> dict[str, object]:
    """계약을 만족하는 최소 이벤트. `session_id` 는 `S-C########-<13자리>` 형식이다."""
    millis = 1767225600000 + day * 86400000
    return {
        "event_id": str(uuid.uuid4()),
        "customer_id": CUSTOMER,
        "session_id": f"S-{CUSTOMER}-{millis}",
        "timestamp": f"2026-01-{day:02d}T10:00:00.000+09:00",
        "event_type": event_type,
        **extra,
    }


#: 1차 창 — 장바구니에 담는다. `category`·`product_id`·`quantity`·`unit_price` 가 실린다.
WINDOW_ONE = [
    event(1, "add_to_cart", category="fresh_food", page_type="cart",
          product_id="P0001", quantity=1, unit_price=8900),
]
#: 2차 창 — 둘러보기만 한다. 위 네 필드가 **하나도 실리지 않는다.**
#:   그래서 마지막 실행분만 보는 판본은 네 필드를 "한 번도 없었다" 로 적었다.
WINDOW_TWO = [event(3, "page_view", page_type="home")]


def write(root: Path, *windows: list[dict[str, object]]) -> None:
    """창마다 **새 `EventSink`** 로 기록한다 — 시뮬레이터의 `advance()` 반복과 같은 모양."""
    for window in windows:
        with EventSink(root) as sink:
            result = sink.write_events(window)
            assert result.rejected == 0, result.problems


class TestGenerationMethodDoesNotChangeTheFacts(unittest.TestCase):
    """★ 한 번에 생성 ≡ 나눠 생성."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        root = Path(self._tmp.name)
        self.one_pass = root / "one"
        self.split = root / "split"
        write(self.one_pass, WINDOW_ONE + WINDOW_TWO)
        write(self.split, WINDOW_ONE, WINDOW_TWO)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    @staticmethod
    def _events(root: Path) -> list[dict[str, object]]:
        from src.measurement.sink import read_events

        return list(read_events(root))

    def test_both_hold_the_same_events(self) -> None:
        """전제 — 이벤트 자체는 이미 제대로 이어붙는다. 문제는 그다음이었다."""
        self.assertEqual(
            len(WINDOW_ONE) + len(WINDOW_TWO), len(self._events(self.one_pass))
        )
        self.assertEqual(
            len(self._events(self.one_pass)), len(self._events(self.split))
        )

    def test_missing_fields_are_identical(self) -> None:
        """★ 이 결함이 드러난 자리. `category`·`product_id` 가 사라졌었다."""
        one = cov.missing_fields(cov.tally(self._events(self.one_pass)))
        split = cov.missing_fields(cov.tally(self._events(self.split)))
        self.assertEqual(
            one, split,
            "같은 데이터인데 생성 방식에 따라 '없었다' 는 필드가 다르다",
        )

    def test_the_cart_fields_are_not_reported_missing(self) -> None:
        """구체적으로 무엇이 틀렸었는지 고정한다 — 동일성만 보면 둘 다 틀려도 통과한다."""
        missing = cov.missing_fields(cov.tally(self._events(self.split)))
        for field in ("category", "product_id", "quantity", "unit_price"):
            with self.subTest(field=field):
                self.assertNotIn(
                    field, missing,
                    f"{field} 는 1차 창의 add_to_cart 에 실렸다 — 디스크에 있는데 "
                    "'한 번도 없었다' 고 말하고 있다",
                )

    def test_coverage_tallies_are_identical(self) -> None:
        one = cov.tally(self._events(self.one_pass))
        split = cov.tally(self._events(self.split))
        self.assertEqual(
            {k: (v.present, v.applicable) for k, v in one.items()},
            {k: (v.present, v.applicable) for k, v in split.items()},
        )


class TestTheComparisonCanFail(unittest.TestCase):
    """★ 음성 대조 — 이 픽스처가 옛 동작을 실제로 구분하는가."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.split = Path(self._tmp.name) / "split"
        write(self.split, WINDOW_ONE, WINDOW_TWO)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_last_run_manifest_still_shows_the_old_wrong_answer(self) -> None:
        """manifest 는 여전히 **마지막 실행분**을 담는다. 그것이 이 파일의 전제다.

        manifest 를 고치지 않았다 — 고칠 필요가 없다. 그것은 '이 실행이 무엇을
        했나' 라는 **사실**이고, 틀린 것은 그것을 데이터셋 설명으로 읽은 쪽이었다.
        여기서 그 사실을 고정해 두면, 누군가 다시 manifest 를 읽기 경로에 끌어다
        쓰는 순간 위 테스트가 실패한다.
        """
        manifest = json.loads((self.split / "manifest.json").read_text(encoding="utf-8"))
        self.assertIn(
            "category", manifest.get("missing_fields") or [],
            "manifest 가 마지막 실행분만 담는다는 전제가 깨졌다 — 이 파일의 "
            "음성 대조가 무의미해진다",
        )

    def test_fixture_would_expose_a_regression(self) -> None:
        """옛 경로(마지막 실행분)와 새 경로(전 이벤트)가 **실제로 다른 답**을 낸다."""
        from src.measurement.sink import read_events

        old = sorted(
            json.loads((self.split / "manifest.json").read_text(encoding="utf-8"))
            .get("missing_fields") or []
        )
        new = cov.missing_fields(cov.tally(read_events(self.split)))
        self.assertNotEqual(
            old, new,
            "두 경로가 같은 답을 내면 이 픽스처로는 회귀를 잡을 수 없다 — "
            "창을 나눈 효과가 드러나는 이벤트를 넣어야 한다",
        )

def _yaml_available() -> bool:
    try:
        import yaml  # noqa: F401
    except ImportError:
        return False
    return True


NEEDS_YAML = (
    "BLOCKED: PyYAML 미설치 — 게시 경로를 실제로 태우지 않았다. "
    "`pip install -r requirements.txt` (with-deps 잡이 이 대조를 수행한다)"
)


@unittest.skipUnless(_yaml_available(), NEEDS_YAML)
class TestPublishedArtifactsAreIdentical(unittest.TestCase):
    """★★ 결함이 실제로 있던 경로 — `publish` 를 통과시켜 대조한다.

    처음 이 파일을 썼을 때는 `coverage.tally()` 만 직접 불러 비교했다. 그것은
    **새로 만든 모듈을 검사할 뿐 결함이 있던 자리를 지나가지 않는다.** 확인해
    보니 `publish` 를 옛 동작으로 되돌려도 이 파일이 **전부 통과했다** —
    회귀 테스트처럼 보이지만 아니었다.

    여기서는 게시물을 실제로 만들어 비교한다. `build_field_coverage_report` 가
    다시 manifest 를 읽는 순간 이 클래스가 실패한다.
    """

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        root = Path(self._tmp.name)
        self.one_pass_out = root / "out-one"
        self.split_out = root / "out-split"
        one_src, split_src = root / "one", root / "split"
        write(one_src, WINDOW_ONE + WINDOW_TWO)
        write(split_src, WINDOW_ONE, WINDOW_TWO)

        from src.measurement.publish import publish

        config = Path(__file__).resolve().parent.parent / "config" / "economic_config.yaml"
        for source, out in ((one_src, self.one_pass_out), (split_src, self.split_out)):
            publish(source_root=source, output_root=out, config_path=config)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def _coverage_report(self, out: Path) -> dict:
        path = out / "measurement" / "field_coverage_report.json"
        return json.loads(path.read_text(encoding="utf-8"))

    def test_published_missing_fields_are_identical(self) -> None:
        """★ 같은 데이터인데 생성 방식에 따라 게시물이 달랐다 — 그 자리."""
        one = self._coverage_report(self.one_pass_out)["missing_fields"]
        split = self._coverage_report(self.split_out)["missing_fields"]
        self.assertEqual(
            one, split,
            "한 번에 생성한 게시물과 나눠 생성한 게시물의 '없었던 필드' 가 다르다",
        )

    def test_published_cart_fields_are_not_missing(self) -> None:
        """동일성만 보면 **둘 다 틀려도** 통과한다. 무엇이 맞는 답인지도 고정한다."""
        missing = self._coverage_report(self.split_out)["missing_fields"]
        for field in ("category", "product_id", "quantity", "unit_price"):
            with self.subTest(field=field):
                self.assertNotIn(field, missing)

    def test_published_field_rates_are_identical(self) -> None:
        one = self._coverage_report(self.one_pass_out)["fields"]
        split = self._coverage_report(self.split_out)["fields"]
        self.assertEqual(sorted(one), sorted(split), "22컬럼 목록이 다르다")
        for name in one:
            with self.subTest(field=name):
                self.assertEqual(
                    one[name].get("coverage"), split[name].get("coverage"),
                    f"{name} 의 충족률이 생성 방식에 따라 다르다",
                )
