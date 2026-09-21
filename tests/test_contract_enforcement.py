"""Holds the two enforcement gaps closed (issue #61, review findings M2 and M6).

Both were the same shape: a rule existed **somewhere** and was not applied **here**.

  M2  `rejection_rate()` returns `unavailable` when its denominator is 0, and the
      contract forbids `denominator == 0` with `status: ok`. `field_fill_rate()`
      had neither guard -- so instead of a wrong value it raised an unhandled
      `ValueError` from `MetricValue.ok()`. The seal caught the bad value; nothing
      caught the crash.

  M6  Three artifacts pinned how *many* entries they carry and never what those
      entries are. Sixteen keys of any name passed. Nine identical lock items
      passed. The count was checked; the content was not.

★ The M6 tests build the counterexamples and run them through the real validator.
  Asserting that a schema *contains* `propertyNames` would pass even if the
  keyword sat somewhere it had no effect -- which is how the original defect
  survived review in the first place.
"""

from __future__ import annotations

import copy
import json
import unittest
from pathlib import Path

from src.measurement import coverage as cov
from src.measurement import kpi
from src.measurement.schema import MetricStatus

REPO_ROOT = Path(__file__).resolve().parent.parent
CONTRACTS = REPO_ROOT / "docs" / "contracts" / "measurement-publish" / "v1"
EXAMPLE = REPO_ROOT / ".agent-team" / "04-architecture" / "examples" / "commerce-connected"
BASE_URI = "https://72offsuit.local/ai-roi/measurement-publish/v1/"


def _jsonschema_available() -> bool:
    try:
        import jsonschema  # noqa: F401
        import referencing  # noqa: F401
    except ImportError:
        return False
    return True


NEEDS_JSONSCHEMA = (
    "BLOCKED: jsonschema/referencing 미설치 — 반례를 실제 validator 로 태우지 "
    "않았다. `pip install -r requirements-dev.txt` (D-21: dev 전용)"
)


class TestFieldFillRateHandlesAnEmptyDenominator(unittest.TestCase):
    """M2 — 분모가 0 이면 계산된 것이 아니다."""

    def test_zero_applicable_is_unavailable(self) -> None:
        """이전에는 `MetricValue.ok()` 가 ValueError 를 던지며 죽었다.

        ★ 이슈 #99 이후 입력이 manifest 의 비율에서 **이벤트에서 센 분자·분모**
          로 바뀌었다. 원래 이 테스트가 재현하던 상황(manifest 가 coverage 를
          담았는데 rows 가 0)은 이제 **만들어질 수 없다** — 커버리지가
          이벤트에서 나오므로 `applicable > 0` 이면 이벤트가 있었다는 뜻이다.
          모순된 manifest 라는 입력 자체가 사라졌다. 남은 실제 경우는
          `applicable == 0` 이고, 그것이 여기서 검사하는 것이다.
        """
        result = kpi.field_fill_rate({"event_id": cov.Tally(present=0, applicable=0)})
        metric = result["event_id"]
        self.assertEqual(MetricStatus.UNAVAILABLE, metric.status)
        self.assertIsNone(metric.value, "계산 불가에 값이 붙으면 0 채우기와 같다")
        self.assertIsNone(metric.basis, "계산 불가에 기준이 붙으면 근거 있게 읽힌다")

    def test_normal_path_still_computes(self) -> None:
        """가드가 정상 경로를 삼키지 않는다."""
        metric = kpi.field_fill_rate(
            {"event_id": cov.Tally(present=10, applicable=10)}
        )["event_id"]
        self.assertEqual(MetricStatus.OK, metric.status)
        self.assertEqual(1.0, metric.value)
        # ★ 분모가 **그 필드가 적용되는 이벤트의 실제 수**다. 예전에는 manifest 가
        #   분모 원수를 담지 않아 `rows` 를 상한으로 적었다 (이슈 #99 가 없앴다).
        self.assertEqual(10, metric.basis.denominator)
        self.assertEqual(10, metric.basis.observed_count)

    def test_absent_field_is_still_unavailable(self) -> None:
        """기존 동작 — 집계에 키가 아예 없으면 분모 자체가 없다."""
        metric = kpi.field_fill_rate({})["event_id"]
        self.assertEqual(MetricStatus.UNAVAILABLE, metric.status)

    def test_every_ratio_function_handles_an_empty_denominator(self) -> None:
        """★ 같은 공백이 다른 비율 함수에 남아 있지 않은지 전수로 본다.

        grep 으로는 못 잡는다 — 처음에 정규식으로 훑었을 때 `field_fill_rate` 를
        "가드 있음" 으로 잘못 판정했다. **호출해서 확인한다.**
        """
        import inspect
        from datetime import date

        manifest = {
            "rows": 0, "rejected": 0, "field_coverage": {"event_id": 1.0},
            "event_type_counts": {}, "sources": {},
        }
        crashed: list[str] = []
        checked = 0
        for name in sorted(dir(kpi)):
            function = getattr(kpi, name)
            if name.startswith("_") or not inspect.isfunction(function):
                continue
            if "Unit.RATIO" not in inspect.getsource(function):
                continue
            parameters = inspect.signature(function).parameters
            kwargs = {}
            for parameter, spec in parameters.items():
                if parameter == "manifest":
                    kwargs[parameter] = manifest
                elif parameter == "counts":
                    # 분모가 0 인 경우 = 전 필드 applicable 0 (이슈 #99)
                    kwargs[parameter] = cov.new_tally()
                elif parameter == "events":
                    kwargs[parameter] = []
                elif parameter == "index_date":
                    kwargs[parameter] = date(2026, 9, 14)
                elif spec.default is inspect.Parameter.empty:
                    kwargs[parameter] = []
            checked += 1
            try:
                function(**kwargs)
            except ValueError as error:
                crashed.append(f"{name}: {error}")
        self.assertGreater(checked, 0, "비율 함수를 하나도 찾지 못했다 — 검사가 비어 있다")
        self.assertEqual(
            [], crashed,
            "분모가 0 일 때 예외로 죽는 비율 함수가 있다. 계산 불가로 돌려주어야 한다",
        )


@unittest.skipUnless(_jsonschema_available(), NEEDS_JSONSCHEMA)
class TestSchemasCheckNamesNotJustCounts(unittest.TestCase):
    """M6 — 개수만 세던 세 곳에 이름·고유성이 걸렸는지 **반례로** 확인한다."""

    @classmethod
    def setUpClass(cls) -> None:
        from referencing import Registry, Resource

        resources = []
        for path in sorted(CONTRACTS.glob("*.schema.json")):
            schema = json.loads(path.read_text(encoding="utf-8"))
            resources.append((schema["$id"], Resource.from_contents(schema)))
        cls.registry = Registry().with_resources(resources)

    def _new_errors(self, artifact: str, mutate) -> set[str]:
        """변형이 **새로** 만든 오류만 — 픽스처의 기존 결함과 섞이지 않게."""
        from jsonschema import Draft202012Validator

        validator = Draft202012Validator(
            {"$ref": f"{BASE_URI}{artifact}.schema.json"}, registry=self.registry
        )
        document = json.loads((EXAMPLE / f"{artifact}.json").read_text(encoding="utf-8"))
        before = {(e.validator, e.message) for e in validator.iter_errors(document)}
        mutate(document)
        after = {(e.validator, e.message) for e in validator.iter_errors(document)}
        return {message for _, message in after - before}

    @staticmethod
    def _rename_one_key(container: str):
        def mutate(document: dict) -> None:
            key = next(iter(document[container]))
            document[container]["오타_" + key] = document[container].pop(key)
        return mutate

    def test_event_type_name_typo_is_rejected(self) -> None:
        """개수는 16 그대로, 이름 하나만 오타."""
        errors = self._new_errors("ingestion_report", self._rename_one_key("by_event_type"))
        self.assertTrue(
            any("오타_" in message for message in errors),
            "event_type 이름이 바뀌었는데 스키마가 잡지 못했다 — 개수만 세고 있다",
        )

    def test_field_name_typo_is_rejected(self) -> None:
        """개수는 22 그대로, DATA-003 컬럼명 하나만 오타."""
        errors = self._new_errors("field_coverage_report", self._rename_one_key("fields"))
        self.assertTrue(
            any("오타_" in message for message in errors),
            "22컬럼 중 하나의 이름이 바뀌었는데 잡지 못했다",
        )

    def test_duplicated_lock_items_are_rejected(self) -> None:
        """개수는 9 그대로, 전부 같은 항목.

        `uniqueItems` 로는 못 잡는 경우도 함께 막힌다 — `status` 만 다른 중복은
        객체가 서로 달라 `uniqueItems` 를 통과한다.
        """
        def mutate(document: dict) -> None:
            document["items"] = [
                copy.deepcopy(document["items"][0]) for _ in document["items"]
            ]
        errors = self._new_errors("freeze_status", mutate)
        self.assertTrue(errors, "Lock 9종이 전부 같은 항목인데 잡지 못했다")

    def test_missing_lock_item_is_rejected(self) -> None:
        """누락도 잡는다 — 비둘기집의 반대 방향."""
        def mutate(document: dict) -> None:
            document["items"] = document["items"][:-1] + [
                copy.deepcopy(document["items"][0])
            ]
        errors = self._new_errors("freeze_status", mutate)
        self.assertTrue(errors, "Lock 항목 하나가 빠지고 다른 것이 중복됐는데 잡지 못했다")

    def test_untouched_fixtures_stay_valid(self) -> None:
        """★ 거짓 양성 — 엄격해진 스키마가 멀쩡한 게시물을 거부하면 안 된다."""
        for artifact in ("ingestion_report", "field_coverage_report", "freeze_status"):
            with self.subTest(artifact=artifact):
                self.assertEqual(
                    set(), self._new_errors(artifact, lambda document: None),
                    "변형하지 않았는데 새 오류가 생겼다",
                )
