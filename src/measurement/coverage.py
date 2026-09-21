"""Counts which contract fields actually arrived, from events alone (issue #99).

Field coverage used to be computed once, at write time, and recorded in
`data/raw/manifest.json`. `publish` then read that record back and reported it as
a fact about the dataset. Two things were wrong with that, and the second only
shows up when data is generated in more than one pass:

  1. the manifest is rewritten by every `EventSink`, so after an append it
     describes **the last run**, not the data on disk
  2. it stores `round(ratio, 4)` -- a derived, lossy number. Two runs' ratios
     **cannot be recombined**: 1/2 and 500/1000 are both `0.5`

So the same events, generated in two windows instead of one, published a claim
that `category` and `product_id` had **never arrived** -- while sitting in an
earlier partition. That is the defect the professor's review pointed at: a
regeneration that looks like a fresh world because nothing carries across.

★ The fix is not a better side-record. `publish` already reads every event
  (`events = list(read_events(...))`), so the information is in hand; copying a
  stale summary instead was the mistake. This module computes the tally from
  events, and `publish` uses it.

★ Why this module exists at all, rather than the counting living in `sink.py`
  where it did before: **two call sites, one rule.** `EventSink` accumulates as
  it writes, `publish` counts a batch it already holds. If each kept its own copy
  of "is this field applicable to this event type, and is it present", the two
  would drift, and the drift would be invisible -- both would look right in
  isolation. `observe()` is the single per-record step; both go through it.

★ Why a new file rather than adding to `schema.py`: `schema.py` is a GATE 1
  canonical file, and touching it means re-recording the seal (a human
  signature). This module sits below everything and imports only the schema, the
  same placement `timeparse.py` uses for the same reason.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Mapping

from src.measurement import schema as sc


@dataclass
class Tally:
    """`present / applicable` 의 **분자와 분모를 따로** 들고 있다.

    ★ 비율이 아니라 두 수를 보관하는 것이 이 타입의 요점이다. 비율은 합칠 수
      없고, 분모를 버리면 "0건 중 0건" 과 "1000건 중 0건" 이 같은 값이 된다.
      전자는 **계산 불가**, 후자는 **비어 있음** 이다.
    """

    present: int = 0
    applicable: int = 0

    @property
    def ratio(self) -> float:
        """★ `applicable == 0` 이면 비율이 성립하지 않는다. 호출 전에 확인한다.

        여기서 `0.0` 을 돌려주지 않는다 — 그러면 '셀 대상이 없었다' 가
        '전부 비어 있었다' 로 둔갑한다. `MetricValue.ok()` 가 `denominator == 0`
        을 생성 시점에 거부하는 것과 같은 규율이다.
        """
        if self.applicable == 0:
            raise ValueError(
                "applicable == 0 이라 충족률이 성립하지 않는다. 0% 로 적으면 "
                "'비어 있었다' 로 읽히지만 실제로는 '셀 대상이 없었다' 다"
            )
        return self.present / self.applicable


def new_tally() -> dict[str, Tally]:
    """22컬럼 전부를 키로 가진 빈 집계.

    한 건도 안 들어온 필드를 **키에서 빼지 않는다.** 빼면 '안 들어왔다' 가
    목록에서 사라지고, 계약이 요구하는 22컬럼도 채워지지 않는다.
    """
    return {spec.name: Tally() for spec in sc.EVENT_FIELDS}


def observe(record: Mapping[str, object], into: dict[str, Tally]) -> None:
    """레코드 한 건을 집계에 반영한다. **이 저장소에서 규칙이 사는 유일한 자리다.**

    호출부는 `record["event_type"]` 이 유효함을 보장한다 (`sink` 는
    `_is_observable()` 로, `publish` 는 저장된 이벤트만 읽으므로 이미 검증을
    통과했다). 여기서 `record.get("event_type", "unknown")` 같은 방어를 넣지
    않는다 — 그러면 스키마에 없는 가짜 종류가 집계에 생기고, 거부됐어야 할
    레코드가 통계에 섞인 채 조용히 도는 쪽이 크래시보다 나쁘다.
    """
    event_type = sc.EventType(record["event_type"])
    for name, tally in into.items():
        if sc.requirement(event_type, name) is sc.Requirement.NOT_APPLICABLE:
            continue
        tally.applicable += 1
        if record.get(name) is not None:
            tally.present += 1


def tally(events: Iterable[Mapping[str, object]]) -> dict[str, Tally]:
    """이벤트 묶음의 필드 충족 집계. `publish` 가 쓰는 입구다."""
    result = new_tally()
    for record in events:
        observe(record, result)
    return result


def missing_fields(counts: Mapping[str, Tally]) -> list[str]:
    """적용 대상인데 **한 건도** 값이 없는 필드.

    ★ `applicable == 0` 은 여기 들어오지 않는다. 해당 이벤트가 하나도 없었던
      필드는 '비어 있다' 가 아니라 '물어볼 자리가 없었다' 이고, 둘을 같은
      목록에 담으면 읽는 사람이 구분할 수 없다.
    """
    return sorted(
        name for name, item in counts.items()
        if item.applicable > 0 and item.present == 0
    )


def unavailable_metrics(event_type_counts: Mapping[str, int]) -> list[str]:
    """근거 이벤트가 하나도 들어오지 않아 계산할 수 없는 Observable 지표.

    MEA-003 — 추정값을 만들어내지 않고 계산 불가로 표시한다.
    """
    return sorted(
        metric
        for metric, sources in sc.OBSERVABLE_METRIC_SOURCES.items()
        if not any(event_type_counts.get(source, 0) for source in sources)
    )


def event_type_counts(events: Iterable[Mapping[str, object]]) -> dict[str, int]:
    """`event_type` 별 건수. `unavailable_metrics()` 의 입력이다."""
    counts: dict[str, int] = {}
    for record in events:
        key = sc.EventType(record["event_type"]).value
        counts[key] = counts.get(key, 0) + 1
    return counts
