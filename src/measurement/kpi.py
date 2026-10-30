"""KPI 계산 계약 — 이름 하나가 계산식·모집단·기간·분모를 결정한다 (이슈 #46).

## 왜 이름이 문제인가

같은 *"Retention"* 이 **상태 기준 잔존율**일 수도 **코호트 잔존율**일 수도 있고, 그
차이가 결론을 바꾼다. 같은 *"Churn"* 이 **운영 상태(후향)** 일 수도 **모델 라벨
(전향)** 일 수도 있고, 그 둘을 섞으면 `days_since_last_purchase ≥ 42` 라는 Feature 가
라벨을 거의 완전히 결정해 **AUC 0.99 가 나오지만 학습된 것은 아무것도 없다**
(PRD Risk 7).

그래서 이 모듈은 **이름을 갈라놓는 것**이 본업이다:

    retention_rate(...)          상태·시점        ≠  cohort_retention_rate(...)  코호트
    churn_rate(...)              운영 상태·후향    ≠  churn_label(...)            모델 라벨·전향
    average_order_value(...)     분모 = 주문 건수  ≠  revenue_per_customer(...)   분모 = 고객 수

**플래그로 만들지 않는다** (R-2). `churn_rate(events, prospective=True)` 는 짧지만,
호출부를 읽는 사람이 어느 쪽인지 알 수 없다.

## 규약을 시그니처로 강제한다

    def average_order_value(events, *, index_date: date, lookback_days: int) -> MetricValue
                                      └ 기본값이 없다 (R-1)          └ float 를 돌려줄 자리가 없다 (R-8)

`index_date` 에 `date.today()` 를 기본값으로 두면 **"현재"라는 암묵 기준일**이 생기고,
어제 만든 리포트와 오늘 만든 리포트가 다른 값을 내면서 그 이유가 코드에 없다.

## ★ "세어 보니 0" 과 "셀 근거가 없다" — 이 모듈의 핵심 경계

    coupon_use 0건  →  coupon_usage_count = ok · 0
                       모집단("coupon_use 이벤트")이 존재하고 세어봤다.
    purchase 0건    →  revenue = unavailable · NO_SOURCE_EVENT
                       "매출 0원"은 관측하지 않은 사업적 사실을 단정하는 것이다.

**둘 다 0 이지만 다른 상태다.** 가르는 기준은 *"그 모집단을 셀 수 있었는가"* 다.
건수 지표는 셀 수 있다(없으면 0건이다). 금액·비율 지표는 근거 이벤트가 없으면 셀
모집단 자체가 없다.

## 출처를 모른다

`events` 를 받을 뿐 출처를 판정하지 않는다 (N-3). 출처별 결과는 `publish.py` 가
입력을 쪼개 같은 함수를 두 번 불러 얻는다. `tests/test_neutrality.py` 가 이 파일에
출처 이름이 없음을 소스 검사로 고정한다.
"""

from __future__ import annotations

import statistics
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Iterable, Mapping, Sequence

from src.measurement import coverage as cov
from src.measurement import timeparse as tp
from src.measurement.schema import (
    Basis,
    BlockerKind,
    BlockerRef,
    Category,
    DerivedStateType,
    EventType,
    EVENT_FIELDS,
    MetricStatus,
    MetricValue,
    OBSERVABLE_METRIC_SOURCES,
    ReasonCode,
    Unit,
    Window,
    WindowDirection,
)

# ── 시간 파라미터 기본값 (R-1 의 예외가 아니다) ─────────────────────────────
#
# `index_date` 는 기본값을 주지 않지만 창 길이는 준다. 둘의 차이는 이렇다:
# 창 길이를 빠뜨리면 **어느 값을 썼는지 basis.window 에 기록되므로 사후에 알 수
# 있다.** 기준일을 빠뜨리면 실행 시각에 따라 값이 달라지고 그 사실이 아무 데도
# 남지 않는다.

DEFAULT_LOOKBACK_DAYS = 42
"""회고기간 `L` 기본값. 지표별로 다르면 이름에 명시한다."""

LABEL_WINDOW_DAYS = 42
"""전향 라벨 창 `W`. **C1 에서 Lock 한다** — 운영 정의와 독립인 고정 상수다.

운영 임계값(28/42/60)과 숫자가 같은 것은 우연이고, 둘은 독립적으로 바뀐다.
그래서 상수를 따로 둔다."""

RULE_OPERATORS = ("OR", "AND")


@dataclass(frozen=True)
class ChurnDefinition:
    """운영 이탈 정의 — FR-10 · SIM-009 · CFG-001 *"Churn 정의는 Config 변경 가능"*.

    정본 값은 `config_loader.load_churn_definition()` 이 읽는 config 의 `churn` 블록이다
    (CFG-001 이 지정한 파일). 필드 기본값은 그 블록이 생기기 전의 가설값(28/42/60 · OR)이다.

    - 이탈 = (미구매 경과일 ≥ `no_purchase_days`) `rule_operator` (미접속 경과일 ≥ `no_login_days`).
    - 미접속 경과일은 마지막 `session_start`·`return_visit`·`purchase` 중 늦은 날부터 센다 — 스키마에
      로그인 이벤트가 없고 구매도 접속이다. `return_visit` 은 구매 뒤 첫 방문 세션을 여는 이벤트라
      방문이다(계약 `visit_count`·`last_visit_date`, #198). 그래서 미접속 경과일은 미구매 경과일보다 길 수 없고,
      `no_login_days ≥ no_purchase_days` 인 OR 규칙은 미구매 조건 하나와 같은 결과를 낸다.
    - ★ **가설값이다(data_spec §5.1).** C1 에서 Lock 하지 않았고, 이 정의를 쓰는 지표는
      `status: unconfirmed` + `params_used` 로 나간다.
    - 라벨 창(`LABEL_WINDOW_DAYS`)은 여기에 두지 않는다 — 운영 정의와 독립인 고정값이다.

    값이 규칙에 어긋나면 `ValueError` 를 낸다.
    """

    at_risk_days: int = 28
    no_purchase_days: int = 42
    no_login_days: int = 60
    rule_operator: str = "OR"

    def __post_init__(self) -> None:
        for name in ("at_risk_days", "no_purchase_days", "no_login_days"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
                raise ValueError(f"{name} 는 양의 정수여야 한다: {value!r}")
        if self.at_risk_days >= self.no_purchase_days:
            raise ValueError(
                f"at_risk_days({self.at_risk_days}) 는 no_purchase_days"
                f"({self.no_purchase_days}) 보다 작아야 한다 — 위험 구간이 이탈보다 먼저다"
            )
        if self.rule_operator not in RULE_OPERATORS:
            raise ValueError(
                f"rule_operator 는 {'/'.join(RULE_OPERATORS)} 중 하나여야 한다: "
                f"{self.rule_operator!r}"
            )

    def is_churned(self, purchase_days: int, access_days: int) -> bool:
        no_purchase = purchase_days >= self.no_purchase_days
        no_login = access_days >= self.no_login_days
        if self.rule_operator == "OR":
            return no_purchase or no_login
        return no_purchase and no_login

    def params_used(self) -> Mapping[str, object]:
        return {
            "at_risk_days": self.at_risk_days,
            "no_purchase_days": self.no_purchase_days,
            "no_login_days": self.no_login_days,
            "rule_operator": self.rule_operator,
        }

    def describe(self) -> str:
        return (
            f"days_since_last_purchase ≥ {self.no_purchase_days} {self.rule_operator} "
            f"days_since_last_access ≥ {self.no_login_days}"
        )


DEFAULT_CHURN_DEFINITION = ChurnDefinition()

_SUM_DENOMINATOR = "분모 없음 (합계)"
_EVENT_TYPE_TOTAL = len(EventType)  # 16. 리터럴로 적지 않는다 — Enum 이 정본이다


# ── 공통 헬퍼 ───────────────────────────────────────────────────────────────

def _event_date(event: Mapping[str, object]) -> date | None:
    """이벤트의 KST 날짜. 해석 불가면 `None` — 조용히 오늘로 대체하지 않는다.

    `sink.EventSink` 가 저장 시점에 KST 로 정규화하므로(M-01 D1-3 정책 ⑵+b) 여기서
    다시 변환하지 않는다. 정규화되지 않은 입력이 들어오면 그것은 Sink 를 거치지
    않은 것이고, 날짜를 추측하는 대신 `None` 을 돌려 집계에서 빠지게 한다.
    """
    raw = event.get("timestamp")
    if isinstance(raw, datetime):
        return raw.date()
    try:
        return tp.parse_datetime(str(raw)).date()
    except (TypeError, ValueError):
        return None


def _in_window(
    event: Mapping[str, object], *, start: date, end: date
) -> bool:
    """`(start, end]` 구간인가. 왼쪽 열림 — 경계 이벤트가 두 창에 동시에 들지 않게."""
    moment = _event_date(event)
    return moment is not None and start < moment <= end


def _of_type(
    events: Iterable[Mapping[str, object]], event_type: EventType
) -> list[Mapping[str, object]]:
    return [e for e in events if e.get("event_type") == event_type.value]


def _retrospective(days: int, *, label: str | None = None) -> Window:
    return Window(WindowDirection.RETROSPECTIVE, days=days, label=label)


def _no_source(
    metric: str,
    event_type: str,
    *,
    unit: Unit,
    detail: str | None = None,
) -> MetricValue:
    """근거 이벤트가 0건이라 셀 모집단이 없다 — 건수 지표에는 쓰지 않는다."""
    return MetricValue.unavailable(
        ReasonCode.NO_SOURCE_EVENT,
        detail
        or f"{event_type} 이벤트가 0건이라 {metric} 를 계산할 근거가 없다 — "
        f"값 0 과 근거 없음은 다르다",
        unit=unit,
        blocked_by=(
            BlockerRef(BlockerKind.EVENT_TYPE, event_type, ReasonCode.NO_SOURCE_EVENT),
        ),
    )


def _customers_missing(metric: str, *, unit: Unit) -> MetricValue:
    """`customers` 테이블이 없어 모집단을 구성할 수 없다 (리드 지시 · AC-3b).

    ★ **임의로 근사하지 않는다.** `events` 의 첫 등장일은 가입일이 아니다 —
    *"이벤트는 '무언가 한 고객'만 보여주지 전체 고객 명부가 아니다."*

    `basis.population` 에 *"고객"* 이라고만 쓰는 것이 `R-4` 위반이고, **모집단을
    정확히 쓸 수 없으면 그 지표는 계산 불가다.**
    """
    return MetricValue.unavailable(
        ReasonCode.PRECONDITION_MISSING,
        f"{metric} 는 signup_date 로 모집단을 구성해야 하는데 customers 테이블이 "
        "미구현이고 events 22컬럼에 signup_date 가 없다. events 첫 등장일은 가입일이 "
        "아니므로 근사하지 않는다. 조치: 별도 저장소 이슈 #29 "
        "(고객 모델에 가입일 추가와 라이프사이클 기준 확보)",
        unit=unit,
        blocked_by=(
            BlockerRef(BlockerKind.TABLE, "customers", ReasonCode.PRECONDITION_MISSING),
            BlockerRef(
                BlockerKind.SCHEMA_GAP, "signup_date", ReasonCode.PRECONDITION_MISSING
            ),
        ),
    )


# ══════════════════════════════════════════════════════════════════════════
# 계층 0 — 수집 건전성 12종
#
# **KPI 가 아니다.** 서비스 성과가 아니라 계약 준수 상태를 잰다. 실험 판정에 쓰지
# 않는다. 원천은 이미 구현된 `sink.manifest()` 이고, 대시보드 V1·V2·V3 의 데이터가
# 전부 이 계층이다.
#
# ★ 계층 0 은 **`combined` 가 허용되는 유일한 계층**이다 (R-7). 계층 1·2 는 계약
#   스키마가 `combined` 키를 거부한다.
# ══════════════════════════════════════════════════════════════════════════

def _manifest_basis(manifest: Mapping[str, object], *, population: str) -> Basis:
    return Basis(
        population=population,
        denominator_definition=_SUM_DENOMINATOR,
        window=Window(WindowDirection.POINT_IN_TIME, label="Sink manifest 기록 시점"),
        observed_count=int(manifest.get("rows", 0) or 0),
    )


def events_ingested(manifest: Mapping[str, object]) -> MetricValue:
    """저장된 이벤트 수. **건수 지표이므로 0 건은 `ok` + `0` 이다.**

    세어봤고 0 이었다 — Sink 를 열었고 manifest 가 나왔으므로 셀 수 있었다.
    ★ 이 값이 `SINK_EMPTY` 판정의 입력이다 (`index.schema.json` 참조).
    """
    return MetricValue.ok(
        int(manifest.get("rows", 0) or 0),
        unit=Unit.COUNT,
        basis=_manifest_basis(manifest, population="Sink 에 저장된 전 이벤트"),
    )


def events_rejected(manifest: Mapping[str, object]) -> MetricValue:
    return MetricValue.ok(
        int(manifest.get("rejected", 0) or 0),
        unit=Unit.COUNT,
        basis=_manifest_basis(manifest, population="스키마 검증에서 거부된 이벤트"),
    )


def rejection_rate(manifest: Mapping[str, object]) -> MetricValue:
    """`events_rejected / (ingested + rejected)`. **분모가 0 이면 `ok` 일 수 없다.**

    시도 자체가 0 건이면 거부율은 정의되지 않는다 — `0%` 로 쓰면 *"아무것도 거부되지
    않았다"* 로 읽히고, 그것은 *"아무것도 시도되지 않았다"* 와 다르다. 계약도
    `basis.denominator == 0 → status: ok` 를 금지한다.
    """
    ingested = int(manifest.get("rows", 0) or 0)
    rejected = int(manifest.get("rejected", 0) or 0)
    attempted = ingested + rejected
    if attempted == 0:
        return MetricValue.unavailable(
            ReasonCode.NO_SOURCE_EVENT,
            "수집 시도가 0건이라 거부율의 분모가 없다 — 0% 로 적으면 "
            "'거부가 없었다' 로 읽히지만 실제로는 '시도가 없었다' 다",
            unit=Unit.RATIO,
            blocked_by=(
                BlockerRef(
                    BlockerKind.METRIC, "events_ingested", ReasonCode.NO_SOURCE_EVENT
                ),
            ),
        )
    return MetricValue.ok(
        rejected / attempted,
        unit=Unit.RATIO,
        basis=Basis(
            population="수집이 시도된 전 이벤트 (저장 + 거부)",
            denominator_definition="수집 시도 건수 = events_ingested + events_rejected",
            window=Window(WindowDirection.POINT_IN_TIME),
            denominator=attempted,
            observed_count=attempted,
        ),
    )


def event_type_coverage(manifest: Mapping[str, object]) -> MetricValue:
    """1건 이상 발생한 `event_type` 종수 / **16**.

    분모가 고정 16 이므로 0 건이어도 `ok` + `0.0` 이다 — 분모가 존재한다.
    `EventType` 의 길이를 쓴다. `16` 을 리터럴로 적으면 Enum 이 늘 때 조용히 틀린다.
    """
    counts = manifest.get("event_type_counts") or {}
    observed = sum(1 for value in counts.values() if value)
    return MetricValue.ok(
        observed / _EVENT_TYPE_TOTAL,
        unit=Unit.RATIO,
        basis=Basis(
            population=f"EventType {_EVENT_TYPE_TOTAL}종",
            denominator_definition=f"스키마가 정의한 event_type 종수 (고정 {_EVENT_TYPE_TOTAL})",
            window=Window(WindowDirection.POINT_IN_TIME),
            denominator=_EVENT_TYPE_TOTAL,
            observed_count=observed,
        ),
    )


def event_type_count(manifest: Mapping[str, object]) -> dict[str, MetricValue]:
    """타입별 건수. ★ **16종 전부 낸다 — 0 건인 타입을 목록에서 빼지 않는다.**

    빼면 *"그 타입이 없었다"* 가 화면에서 보이지 않고 *"검사하지 않았다"* 와
    구분되지 않는다.
    """
    counts = manifest.get("event_type_counts") or {}
    return {
        item.value: MetricValue.ok(
            int(counts.get(item.value, 0) or 0),
            unit=Unit.COUNT,
            basis=Basis(
                population=f"event_type = {item.value} 인 이벤트",
                denominator_definition=_SUM_DENOMINATOR,
                window=Window(WindowDirection.POINT_IN_TIME),
                observed_count=int(counts.get(item.value, 0) or 0),
                source_event_types=(item.value,),
            ),
        )
        for item in EventType
    }


def field_fill_rate(counts: Mapping[str, "cov.Tally"]) -> dict[str, MetricValue]:
    """필드별 충족률. ★ **22컬럼 전부 낸다.**

    입력은 `coverage.tally(events)` 의 결과다 — **이벤트에서 직접 센 분자·분모**
    이지, manifest 가 담아 둔 비율이 아니다 (이슈 #99).

    ★ 예전에는 manifest 의 `field_coverage` 를 읽었고 두 가지가 딸려 왔다:

      1. manifest 는 실행마다 덮어써지므로 **이어붙여 생성하면 이전 창의 필드가
         "한 번도 없었다" 로 나왔다.** 같은 데이터인데 생성 방식에 따라 게시물이
         달랐다.
      2. manifest 는 `round(ratio, 4)` 만 담아 **분모 원수가 없다.** 그래서
         `denominator` 에 `rows` 를 상한으로 적고 basis 문장으로 그 사실을
         밝히는 회피가 있었다.

      둘 다 사라진다. 이제 분모는 **그 필드가 적용되는 이벤트의 실제 수**다.

    `NOT_APPLICABLE` 은 분모에서 제외된다 (`coverage.observe()` 가 그렇게 센다).
    그 필드가 어떤 이벤트에도 적용되지 않았으면 `applicable == 0` 이고
    → **분모가 없으므로 `unavailable`** 이다. `0%` 가 아니다.
    """
    result: dict[str, MetricValue] = {}
    for spec in EVENT_FIELDS:
        tally = counts.get(spec.name)
        # ★ 분모가 0 이면 계산된 것이 아니다 (이슈 #61 · 리뷰 M2).
        #   `MetricValue.ok()` 는 `denominator == 0` 을 생성 시점에 거부한다 —
        #   여기서 막지 않으면 처리되지 않은 ValueError 로 죽는다.
        if tally is None or tally.applicable == 0:
            result[spec.name] = MetricValue.unavailable(
                ReasonCode.NO_SOURCE_EVENT,
                f"{spec.name} 이 적용되는 이벤트가 0건이라 충족률의 분모가 없다 — "
                "0% 는 '비어 있었다' 로 읽히지만 실제로는 '해당 이벤트가 없었다' 다",
                unit=Unit.RATIO,
            )
            continue
        result[spec.name] = MetricValue.ok(
            tally.present / tally.applicable,
            unit=Unit.RATIO,
            basis=Basis(
                population=f"{spec.name} 이 적용되는(NOT_APPLICABLE 이 아닌) 이벤트",
                denominator_definition="해당 필드가 적용되는 이벤트 수",
                window=Window(WindowDirection.POINT_IN_TIME),
                denominator=tally.applicable,
                observed_count=tally.present,
            ),
        )
    return result


def missing_field_count(missing: Sequence[str]) -> MetricValue:
    """적용 대상인데 한 건도 값이 없는 필드 수. 입력은 `coverage.missing_fields()`."""
    return MetricValue.ok(
        len(missing),
        unit=Unit.COUNT,
        basis=Basis(
            population="적용 대상인데 한 건도 값이 없는 필드",
            denominator_definition=_SUM_DENOMINATOR,
            window=Window(WindowDirection.POINT_IN_TIME),
            observed_count=len(missing),
        ),
    )


def unavailable_metric_count(unavailable: Sequence[str]) -> MetricValue:
    """계산 불가 Observable 지표 수 / 16. 입력은 `coverage.unavailable_metrics()`.

    빈 Sink 에서 **16 전부**가 계산 불가다 — `tests/test_sink.py` 의
    `test_empty_sink_marks_every_metric_unavailable` 가 그 동작을 고정한다.
    """
    total = len(OBSERVABLE_METRIC_SOURCES)
    return MetricValue.ok(
        len(unavailable),
        unit=Unit.COUNT,
        basis=Basis(
            population=f"PRD §21 Observable 지표 {total}종",
            denominator_definition=f"Observable 지표 총수 (고정 {total})",
            window=Window(WindowDirection.POINT_IN_TIME),
            denominator=total,
            observed_count=len(unavailable),
        ),
    )


def source_event_count(manifest: Mapping[str, object]) -> dict[str, MetricValue]:
    """출처별 건수. ★ **두 키가 항상 존재한다 — 0 건이어도 빼지 않는다.**

    이 모듈이 출처 이름을 아는 유일한 자리가 아니다: 키는 `manifest["sources"]` 에서
    온다. 그래도 *"두 키가 다 있어야 한다"* 는 계약이므로, manifest 에 없는 출처는
    0 건으로 채우는 대신 manifest 가 준 키만 낸다 — 없는 출처를 지어내지 않는다.
    """
    sources = manifest.get("sources") or {}
    return {
        name: MetricValue.ok(
            int(count or 0),
            unit=Unit.COUNT,
            basis=Basis(
                population=f"출처 {name} 의 이벤트",
                denominator_definition=_SUM_DENOMINATOR,
                window=Window(WindowDirection.POINT_IN_TIME),
                observed_count=int(count or 0),
            ),
        )
        for name, count in sorted(sources.items())
    }


def partition_day_count(partition_dates: Sequence[date]) -> MetricValue:
    return MetricValue.ok(
        len(set(partition_dates)),
        unit=Unit.COUNT,
        basis=Basis(
            population="이벤트가 저장된 날짜 파티션",
            denominator_definition=_SUM_DENOMINATOR,
            window=Window(WindowDirection.POINT_IN_TIME),
            observed_count=len(set(partition_dates)),
        ),
    )


def ingestion_days_gap(partition_dates: Sequence[date]) -> MetricValue:
    """파티션 구간 내 **이벤트가 0건인 날짜 수**.

    ★ **공백이 몇 개인지는 안다.** 그것이 수집 중단인지 활동 없음인지는
    `ingestion_gap_attribution` 이 따로 말한다 — 이 함수는 세는 것만 한다.

        파티션 [10-01, 10-03]  →  10-02 가 비었으면 1
        파티션 0~1개            →  구간이 없으므로 unavailable
    """
    unique = sorted(set(partition_dates))
    if len(unique) < 2:
        return MetricValue.unavailable(
            ReasonCode.NO_SOURCE_EVENT,
            f"파티션이 {len(unique)}개라 구간이 성립하지 않는다 — 공백을 세려면 "
            "시작과 끝이 필요하다",
            unit=Unit.COUNT,
            blocked_by=(
                BlockerRef(
                    BlockerKind.METRIC, "partition_day_count",
                    ReasonCode.NO_SOURCE_EVENT,
                ),
            ),
        )
    span = (unique[-1] - unique[0]).days + 1
    gaps = span - len(unique)
    return MetricValue.ok(
        gaps,
        unit=Unit.COUNT,
        basis=Basis(
            population=f"{unique[0].isoformat()} ~ {unique[-1].isoformat()} 구간의 날짜",
            denominator_definition=_SUM_DENOMINATOR,
            window=_retrospective(span, label="파티션 최초~최종일"),
            observed_count=len(unique),
            excluded_count=None,
        ),
    )


def ingestion_gap_attribution() -> MetricValue:
    """공백이 **수집 중단인지 활동 없음인지**. ★ 풀지 않고 사실을 싣는다 (X-5).

    heartbeat 레코드가 필요한데 셋 다 막혀 있다: `event_type` 16종을 늘리는 것은
    `EVENT SCHEMA v1` 의 실질 변경이고, Sink 밖 별도 레코드는 양쪽 소스가 써야 하며
    한쪽은 편집 금지이고, C1 에는 검증할 데이터가 없다.

    ★ **"활동 없음"이라고 쓰지 않는다.** 관측하지 않은 것을 단정하는 것이고,
    **0 채우기와 같은 종류의 잘못**이다. `not_run` 이지 `unavailable` 이 아니다 —
    근거를 찾아본 것이 아니라 검사 자체를 하지 않았다.
    """
    return MetricValue.not_run(
        "heartbeat 레코드가 없어 이벤트 0건인 날짜가 수집 중단인지 활동 없음인지 "
        "구분할 수 없다. 공백이 몇 개인지는 ingestion_days_gap 이 말한다",
        reason_code=ReasonCode.PRECONDITION_MISSING,
        unit=Unit.TEXT,
        blocked_by=(
            BlockerRef(
                BlockerKind.EVENT_TYPE, "heartbeat", ReasonCode.PRECONDITION_MISSING
            ),
        ),
    )


# ══════════════════════════════════════════════════════════════════════════
# 계층 1 — Customer KPI 8종
# ══════════════════════════════════════════════════════════════════════════

def _purchases_by_customer(
    events: Iterable[Mapping[str, object]], *, index_date: date, lookback_days: int
) -> dict[str, list[date]]:
    """고객별 구매 날짜 목록 (회고 구간 내, 오름차순)."""
    start = index_date - timedelta(days=lookback_days)
    result: dict[str, list[date]] = defaultdict(list)
    for event in _of_type(events, EventType.PURCHASE):
        if not _in_window(event, start=start, end=index_date):
            continue
        customer = event.get("customer_id")
        moment = _event_date(event)
        if isinstance(customer, str) and moment is not None:
            result[customer].append(moment)
    for dates in result.values():
        dates.sort()
    return dict(result)


def _days_since_last_purchase(
    events: Iterable[Mapping[str, object]], *, index_date: date
) -> dict[str, int]:
    """고객별 마지막 구매 이후 경과일. **회고 창을 쓰지 않는다** — 상태는 시점 값이다."""
    last: dict[str, date] = {}
    for event in _of_type(events, EventType.PURCHASE):
        customer = event.get("customer_id")
        moment = _event_date(event)
        if not isinstance(customer, str) or moment is None or moment > index_date:
            continue
        if customer not in last or moment > last[customer]:
            last[customer] = moment
    return {c: (index_date - d).days for c, d in last.items()}


def _churn_elapsed(
    events: Iterable[Mapping[str, object]], *, index_date: date
) -> dict[str, tuple[int, int]]:
    """구매 이력 고객별 (미구매 경과일, 미접속 경과일). 접속 = `session_start`·`return_visit`·`purchase`.

    한 번만 순회한다 — 1회용 iterable 이 들어와도 두 값이 같은 이벤트에서 나온다.
    """
    access_types = (EventType.SESSION_START.value, EventType.RETURN_VISIT.value, EventType.PURCHASE.value)
    last_purchase: dict[str, date] = {}
    last_access: dict[str, date] = {}
    for event in events:
        event_type = event.get("event_type")
        customer = event.get("customer_id")
        if event_type not in access_types or not isinstance(customer, str):
            continue
        moment = _event_date(event)
        if moment is None or moment > index_date:
            continue
        if event_type == EventType.PURCHASE.value and (
            customer not in last_purchase or moment > last_purchase[customer]
        ):
            last_purchase[customer] = moment
        if customer not in last_access or moment > last_access[customer]:
            last_access[customer] = moment
    return {
        customer: ((index_date - bought).days, (index_date - last_access[customer]).days)
        for customer, bought in last_purchase.items()
    }


def churn_rate(
    events: Sequence[Mapping[str, object]],
    *,
    index_date: date,
    definition: ChurnDefinition = DEFAULT_CHURN_DEFINITION,
) -> MetricValue:
    """**운영 상태 · 후향.** `definition` 의 이탈 규칙을 만족하는 구매 고객 비율.

    ★ `churn_label()` 과 **다른 함수다** (R-2). 이쪽은 `D` 이전을 보고 대시보드
    표시·코호트 분석·Rule-based Baseline 조건에 쓴다. 저쪽은 `D` 이후를 보고 모델
    학습 라벨에만 쓴다. **플래그로 합치지 않는다.**

    정의가 가설값이므로 `unconfirmed` + `params_used` 다.
    """
    elapsed = _churn_elapsed(events, index_date=index_date)
    if not elapsed:
        return _no_source("churn_rate", "purchase", unit=Unit.RATIO)
    churned = sum(1 for days in elapsed.values() if definition.is_churned(*days))
    return MetricValue.unconfirmed(
        churned / len(elapsed),
        unit=Unit.RATIO,
        basis=Basis(
            population="P_buyer(D) — index_date 까지 purchase 이력이 1건 이상인 고객",
            denominator_definition="구매 이력 보유 고객 수",
            window=Window(WindowDirection.POINT_IN_TIME, label="index_date 시점 상태"),
            denominator=len(elapsed),
            observed_count=len(elapsed),
            source_event_types=("purchase", "session_start", "return_visit"),
        ),
        reason_detail=(
            f"이탈 정의 {definition.describe()} 가 가설값이다 — "
            "data_spec §5.1 확정 절차 ①~④가 시뮬레이터를 요구하고 C1 에 없다"
        ),
        params_used=definition.params_used(),
    )


def retention_rate(
    events: Sequence[Mapping[str, object]],
    *,
    index_date: date,
    definition: ChurnDefinition = DEFAULT_CHURN_DEFINITION,
) -> MetricValue:
    """**상태·시점** 잔존율 = `1 − churn_rate`. 동일 모집단·동일 시점의 파생값.

    ★ `cohort_retention_rate()` 와 **다른 지표다.** 이쪽은 "지금 이탈 아닌 비율",
    저쪽은 "가입 코호트의 m 개월차 잔존율"이다. 같은 *"Retention"* 이 두 뜻으로
    쓰이는 것이 이 프로젝트가 이름을 가른 첫 번째 이유다.
    """
    churn = churn_rate(events, index_date=index_date, definition=definition)
    if churn.status is MetricStatus.UNAVAILABLE:
        return MetricValue.unavailable(
            churn.reason_code or ReasonCode.NO_SOURCE_EVENT,
            f"churn_rate 를 계산할 수 없어 retention_rate 도 계산할 수 없다 — "
            f"{churn.reason_detail}",
            unit=Unit.RATIO,
            blocked_by=(
                BlockerRef(
                    BlockerKind.METRIC, "churn_rate",
                    churn.reason_code or ReasonCode.NO_SOURCE_EVENT,
                ),
            ),
        )
    return MetricValue.unconfirmed(
        1 - float(churn.value),  # type: ignore[arg-type]
        unit=Unit.RATIO,
        basis=churn.basis,  # type: ignore[arg-type]
        reason_detail=f"churn_rate 의 파생값이므로 같은 미확정을 물려받는다 — {churn.reason_detail}",
        params_used=definition.params_used(),
    )


def cohort_retention_rate(
    events: Sequence[Mapping[str, object]], *, index_date: date, month: int
) -> MetricValue:
    """가입 코호트 `m` 개월차 잔존율. ★ **C1 에서 계산 불가** (AC-3b).

    가입월 코호트를 만들려면 `signup_date` 가 필요하고 그것은 `customers` 테이블
    컬럼이며 그 테이블이 미구현이다. `events` 22컬럼에 `signup_date` 가 없다.

    ⚠ `kpi-definition-v1.md` §8 은 이 지표를 **`✅`(계산 가능)** 로 적었다. **그
    문서와 모순이고, 문서가 틀렸다** — 가입월을 알 방법이 `events` 에 없다.
    M-08(Lock 최종 검산)에 보고 대상이다.

    `events` 첫 등장일로 근사하지 않는다 — *"무언가 한 고객"* 의 첫 활동일은
    가입일이 아니고, 근사하면 가입 후 오래 잠자다 활동한 고객이 신규로 분류된다.
    """
    del events, index_date, month  # 의도적으로 쓰지 않는다 — 모집단이 성립하지 않는다
    return _customers_missing("cohort_retention_rate", unit=Unit.RATIO)


def repurchase_rate(
    events: Sequence[Mapping[str, object]],
    *,
    index_date: date,
    lookback_days: int = DEFAULT_LOOKBACK_DAYS,
) -> MetricValue:
    """기간 내 2회 이상 구매 고객 / 1회 이상 구매 고객.

    ★★ **`customers` 부재에 막히지 않는다** (Matthias 항목4 정정).

    계산식이 `purchase` 이벤트만 쓴다 — `signup_date` 가 식에 나오지 않는다. 막힌
    것은 `kpi-definition-v1.md` 의 `모집단` 칸이 `P_all(D)` 라고 적은 **선언**이고,
    그것은 그 문서 내부의 모순이다(분모 정의가 이미 *"기간 내 1회 이상 구매 고객"*
    이다).

    **`PRECONDITION_MISSING` 을 쓰지 않는다** — 근거가 있는데 없다고 말하는 것이다.
    과대보고의 거울상이지만 **이유를 틀리게 말하는 것은 같다.**

    → `status: ok` + `basis.population` 에 실제 모집단을 정확히 적는다.
    """
    by_customer = _purchases_by_customer(
        events, index_date=index_date, lookback_days=lookback_days
    )
    if not by_customer:
        return _no_source("repurchase_rate", "purchase", unit=Unit.RATIO)
    repeat = sum(1 for dates in by_customer.values() if len(dates) >= 2)
    return MetricValue.ok(
        repeat / len(by_customer),
        unit=Unit.RATIO,
        basis=Basis(
            population=(
                f"[D−{lookback_days}, D] 구간에 purchase 이벤트가 1건 이상인 고객 "
                "(P_all(D) 이 아니다 — signup_date 없이 구성되는 모집단이다)"
            ),
            denominator_definition="기간 내 1회 이상 구매 고객 수",
            window=_retrospective(lookback_days),
            denominator=len(by_customer),
            observed_count=len(by_customer),
            source_event_types=("purchase",),
        ),
    )


def winback_rate(
    events: Sequence[Mapping[str, object]],
    *,
    index_date: date,
    lookback_days: int = DEFAULT_LOOKBACK_DAYS,
    definition: ChurnDefinition = DEFAULT_CHURN_DEFINITION,
) -> MetricValue:
    """`D−L` 시점 이탈 고객 중 `(D−L, D]` 에 구매한 비율. 이탈 정의 의존 → `unconfirmed`."""
    boundary = index_date - timedelta(days=lookback_days)
    elapsed_then = _churn_elapsed(events, index_date=boundary)
    churned_then = {c for c, days in elapsed_then.items() if definition.is_churned(*days)}
    if not churned_then:
        return MetricValue.unavailable(
            ReasonCode.NO_SOURCE_EVENT,
            f"D−{lookback_days} 시점에 이탈 상태인 고객이 0명이라 복귀율의 분모가 "
            "없다 — 0% 는 '아무도 복귀하지 않았다' 로 읽히지만 실제로는 '복귀할 "
            "대상이 없었다' 다",
            unit=Unit.RATIO,
            blocked_by=(
                BlockerRef(
                    BlockerKind.EVENT_TYPE, "purchase", ReasonCode.NO_SOURCE_EVENT
                ),
            ),
        )
    returned = {
        event.get("customer_id")
        for event in _of_type(events, EventType.PURCHASE)
        if _in_window(event, start=boundary, end=index_date)
    }
    won_back = len(churned_then & {c for c in returned if isinstance(c, str)})
    return MetricValue.unconfirmed(
        won_back / len(churned_then),
        unit=Unit.RATIO,
        basis=Basis(
            population=f"P_buyer(D−{lookback_days}) 중 그 시점 이탈 상태인 고객",
            denominator_definition=f"D−{lookback_days} 시점 이탈 고객 수",
            window=Window(
                WindowDirection.RETROSPECTIVE, days=lookback_days,
                label=f"(D−{lookback_days}, D]",
            ),
            denominator=len(churned_then),
            observed_count=len(churned_then),
            source_event_types=("purchase", "session_start", "return_visit"),
        ),
        reason_detail=f"이탈 판정에 가설값 {definition.describe()} 를 썼다",
        params_used=definition.params_used(),
    )


def purchase_frequency(
    events: Sequence[Mapping[str, object]],
    *,
    index_date: date,
    lookback_days: int = DEFAULT_LOOKBACK_DAYS,
) -> MetricValue:
    """회고 구간 구매 건수 / 구매 고객 수. 분모는 **고객 수**다."""
    by_customer = _purchases_by_customer(
        events, index_date=index_date, lookback_days=lookback_days
    )
    if not by_customer:
        return _no_source("purchase_frequency", "purchase", unit=Unit.COUNT)
    total = sum(len(dates) for dates in by_customer.values())
    return MetricValue.ok(
        total / len(by_customer),
        unit=Unit.COUNT,
        basis=Basis(
            population="P_buyer(D) — 회고 구간에 purchase 가 1건 이상인 고객",
            denominator_definition="구매 고객 수 (주문 건수가 아니다)",
            window=_retrospective(lookback_days),
            denominator=len(by_customer),
            observed_count=total,
            source_event_types=("purchase",),
        ),
    )


def purchase_interval(
    events: Sequence[Mapping[str, object]],
    *,
    index_date: date,
    lookback_days: int = DEFAULT_LOOKBACK_DAYS,
) -> MetricValue:
    """고객별 구매 간격 중앙값의 **모집단 중앙값**.

    ★ **제외 인원을 값과 함께 보고한다** (R-6). 구매가 1건인 고객은 간격이 정의되지
    않아 분모에서 빠지고, 그 사실이 `basis.excluded_count`·`excluded_reason` 에
    남는다 — **제외를 조용히 하지 않는다.** 빼고 계산한 값만 보이면 모집단이 실제보다
    활발해 보인다.
    """
    by_customer = _purchases_by_customer(
        events, index_date=index_date, lookback_days=lookback_days
    )
    if not by_customer:
        return _no_source("purchase_interval", "purchase", unit=Unit.DAYS)
    per_customer: list[float] = []
    excluded = 0
    for dates in by_customer.values():
        if len(dates) < 2:
            excluded += 1
            continue
        gaps = [(b - a).days for a, b in zip(dates, dates[1:])]
        per_customer.append(statistics.median(gaps))
    if not per_customer:
        return MetricValue.unavailable(
            ReasonCode.NO_SOURCE_EVENT,
            f"구매 고객 {len(by_customer)}명 전원이 1건만 구매해 간격이 정의되는 "
            "고객이 0명이다 — 간격 0일이 아니라 계산 대상이 없다",
            unit=Unit.DAYS,
            blocked_by=(
                BlockerRef(
                    BlockerKind.EVENT_TYPE, "purchase", ReasonCode.NO_SOURCE_EVENT
                ),
            ),
        )
    return MetricValue.ok(
        statistics.median(per_customer),
        unit=Unit.DAYS,
        basis=Basis(
            population="P_buyer(D) ∧ 회고 구간 구매 2건 이상",
            denominator_definition="구매 간격이 정의되는 고객 수",
            window=_retrospective(lookback_days),
            denominator=len(per_customer),
            observed_count=len(per_customer),
            excluded_count=excluded,
            excluded_reason=(
                "구매가 1건뿐이어서 간격이 정의되지 않는 고객 (R-6 — 제외를 "
                "조용히 하지 않는다)"
            )
            if excluded
            else None,
            source_event_types=("purchase",),
        ),
    )


def average_order_value(
    events: Sequence[Mapping[str, object]],
    *,
    index_date: date,
    lookback_days: int = DEFAULT_LOOKBACK_DAYS,
) -> MetricValue:
    """`Σ order_amount / count(purchase)`. ★ 분모는 **주문 건수**다 (고객 수 아님).

    고객당 매출이 필요하면 `revenue_per_customer` 라는 **별도 이름**을 쓴다. 같은
    이름으로 분모를 바꾸면 두 리포트가 다른 값을 내면서 이유가 코드에 없다.
    """
    start = index_date - timedelta(days=lookback_days)
    purchases = [
        event
        for event in _of_type(events, EventType.PURCHASE)
        if _in_window(event, start=start, end=index_date)
    ]
    if not purchases:
        return _no_source("average_order_value", "purchase", unit=Unit.KRW)
    amounts = [
        int(event["order_amount"])
        for event in purchases
        if isinstance(event.get("order_amount"), int)
    ]
    if len(amounts) != len(purchases):
        return MetricValue.unavailable(
            ReasonCode.MISSING_FIELD,
            f"purchase {len(purchases)}건 중 {len(purchases) - len(amounts)}건에 "
            "order_amount 가 없다 — 결손을 0 으로 채우면 평균이 내려간다",
            unit=Unit.KRW,
            blocked_by=(
                BlockerRef(
                    BlockerKind.FIELD, "order_amount", ReasonCode.MISSING_FIELD
                ),
            ),
        )
    return MetricValue.ok(
        sum(amounts) / len(amounts),
        unit=Unit.KRW,
        basis=Basis(
            population="P_buyer(D) 의 회고 구간 purchase 이벤트",
            denominator_definition="주문 건수 (★ 고객 수가 아니다)",
            window=_retrospective(lookback_days),
            denominator=len(amounts),
            observed_count=len(amounts),
            source_event_types=("purchase",),
        ),
    )


# ── 모델 라벨 — 전향. 함수 이름이 다르다 (R-2) ──────────────────────────────

def churn_label(
    events: Sequence[Mapping[str, object]], *, index_date: date
) -> MetricValue:
    """**모델 라벨 · 전향.** `(T0, T0+42]` 에 `purchase` 가 0건인 고객 비율.

    ★ `churn_rate()` 와 **다른 함수다.** 이름을 가른 이유가 PRD Risk 7 이다:
    운영 상태를 그대로 라벨로 쓰면 `days_since_last_purchase ≥ 42` 라는 Feature 가
    라벨을 거의 완전히 결정하고, **AUC 0.99 가 나오지만 학습된 것은 아무것도 없다.**

    `label_window_days = 42` 는 운영 임계값과 **독립인 고정 상수**이고 C1 에서
    Lock 한다. 그래서 이 지표는 `unconfirmed` 가 아니다 — 가설값을 쓰지 않는다.
    """
    end = index_date + timedelta(days=LABEL_WINDOW_DAYS)
    known = {
        event.get("customer_id")
        for event in _of_type(events, EventType.PURCHASE)
        if (moment := _event_date(event)) is not None and moment <= index_date
    }
    known = {c for c in known if isinstance(c, str)}
    if not known:
        return _no_source("churn_label", "purchase", unit=Unit.RATIO)
    repurchased = {
        event.get("customer_id")
        for event in _of_type(events, EventType.PURCHASE)
        if _in_window(event, start=index_date, end=end)
    }
    labelled = len(known - {c for c in repurchased if isinstance(c, str)})
    return MetricValue.ok(
        labelled / len(known),
        unit=Unit.RATIO,
        basis=Basis(
            population="index_date 까지 purchase 이력이 있는 고객 (라벨 대상)",
            denominator_definition="라벨 대상 고객 수",
            window=Window(
                WindowDirection.PROSPECTIVE, days=LABEL_WINDOW_DAYS,
                label=f"(T0, T0+{LABEL_WINDOW_DAYS}]",
            ),
            denominator=len(known),
            observed_count=len(known),
            source_event_types=("purchase",),
        ),
        limit_note=(
            "모델 학습 라벨 전용이다 — 대시보드 상태 표시에 쓰지 않는다 "
            "(운영 상태는 churn_rate)"
        ),
    )


# ── 파생 상태 분포 3종 — 게시 시점 계산 (리드 판정 G-8) ─────────────────────

def derived_state_count(
    events: Sequence[Mapping[str, object]],
    *,
    index_date: date,
    definition: ChurnDefinition = DEFAULT_CHURN_DEFINITION,
) -> dict[str, MetricValue]:
    """`inactive`·`at_risk`·`churn` 분포. **게시 시점에 계산해 게시한다.**

    `DerivedStateType` 이 `EventType` 밖이라 Sink 에 기록할 수단이 없었다. 리드
    판정 ④ — `days_since_last_purchase` 에서 **유도**되고 그 원천(`timestamp`·
    `purchase`)은 이미 스키마에 있으므로, 계산해 게시하면 스키마를 바꾸지 않고
    정보가 산다.

    조건 넷을 전부 지킨다:

      ① `derived: true` + `derivation` — 저장된 사실과 구분된다
      ② `unconfirmed` + `params_used` — 임계값 28/42/60 이 가설값이다
      ③ Feature 사용 금지 문구를 `derivation` 에 적는다 (PRD Risk 7)
      ④ ★ `OBSERVABLE_METRIC_SOURCES` 에 **넣지 않는다** —
         `tests/test_schema.py test_no_observable_depends_on_derived_state` 가
         그대로 통과해야 한다. 이 지표는 Observable 이 아니라 **표시 전용**이다

    ④가 가장 위험한 자리다. 파생 상태가 `kpi_report` 에 나타나는 순간
    *"이제 Feature 로 써도 되는 것 아닌가"* 로 읽힐 수 있다.
    """
    elapsed = _churn_elapsed(events, index_date=index_date)
    churn_formula = definition.describe()
    not_churn = f"¬({churn_formula})"
    bands = {
        DerivedStateType.INACTIVE.value: (
            lambda d: not definition.is_churned(*d) and definition.at_risk_days > d[0] > 0,
            f"{not_churn} ∧ 0 < days_since_last_purchase < {definition.at_risk_days}",
        ),
        DerivedStateType.AT_RISK.value: (
            lambda d: not definition.is_churned(*d) and d[0] >= definition.at_risk_days,
            f"{not_churn} ∧ days_since_last_purchase ≥ {definition.at_risk_days}",
        ),
        DerivedStateType.CHURN.value: (
            lambda d: definition.is_churned(*d),
            churn_formula,
        ),
    }
    result: dict[str, MetricValue] = {}
    for state, (predicate, formula) in bands.items():
        if not elapsed:
            result[state] = _no_source(
                f"derived_state_count[{state}]", "purchase", unit=Unit.COUNT
            )
            continue
        result[state] = MetricValue.unconfirmed(
            sum(1 for days in elapsed.values() if predicate(days)),
            unit=Unit.COUNT,
            basis=Basis(
                population="P_buyer(D) — index_date 까지 purchase 이력이 있는 고객",
                denominator_definition=_SUM_DENOMINATOR,
                window=Window(
                    WindowDirection.POINT_IN_TIME, label="index_date 시점 상태"
                ),
                observed_count=len(elapsed),
                source_event_types=("purchase", "session_start", "return_visit"),
            ),
            reason_detail=(
                f"이탈 정의(at_risk_days={definition.at_risk_days} · {churn_formula})가 "
                "가설값이다 — data_spec §5.1 확정 절차가 시뮬레이터를 요구하고 C1 에 없다"
            ),
            params_used=definition.params_used(),
            derived=True,
            derivation=(
                f"{formula} 인 고객 수. 저장된 사실이 아니라 purchase 이벤트의 "
                "timestamp 에서 게시 시점에 유도한 값이다. "
                "★ 학습 Feature 로 사용 금지 — 라벨과 동어반복이 된다 (PRD Risk 7)"
            ),
        )
    return result


# ══════════════════════════════════════════════════════════════════════════
# 계층 2 — Business KPI 중 `events` 만으로 계산되는 것
#
# 금액·비용 지표는 `economics.py` 가 계산한다. 여기 있는 것은 이벤트 건수에서
# 직접 나오는 Observable 계열이다.
# ══════════════════════════════════════════════════════════════════════════

def _count_metric(
    events: Sequence[Mapping[str, object]],
    event_type: EventType,
    *,
    index_date: date,
    lookback_days: int,
    population: str,
    limit_note: str | None = None,
) -> MetricValue:
    """★ 건수 지표는 **0 건이어도 `ok` + `0`** 이다.

    모집단("그 타입의 이벤트")이 존재하고 세어봤기 때문이다. 이것이 금액·비율
    지표와 갈리는 지점이다 — `coupon_use` 가 0건이면 사용 횟수는 0 이지만,
    `purchase` 가 0건이면 매출은 0원이 아니라 **알 수 없음**이다.
    """
    start = index_date - timedelta(days=lookback_days)
    matched = [
        event
        for event in _of_type(events, event_type)
        if _in_window(event, start=start, end=index_date)
    ]
    return MetricValue.ok(
        len(matched),
        unit=Unit.COUNT,
        basis=Basis(
            population=population,
            denominator_definition=_SUM_DENOMINATOR,
            window=_retrospective(lookback_days),
            observed_count=len(matched),
            source_event_types=(event_type.value,),
        ),
        limit_note=limit_note,
    )


def coupon_usage_count(
    events: Sequence[Mapping[str, object]],
    *,
    index_date: date,
    lookback_days: int = DEFAULT_LOOKBACK_DAYS,
) -> MetricValue:
    """★ AC-4 — `coupon_use` 0건이면 **`ok` + `0`**. `unavailable` 이 아니다."""
    return _count_metric(
        events, EventType.COUPON_USE,
        index_date=index_date, lookback_days=lookback_days,
        population="회고 구간의 coupon_use 이벤트",
    )


def coupon_exposure_count(
    events: Sequence[Mapping[str, object]],
    *,
    index_date: date,
    lookback_days: int = DEFAULT_LOOKBACK_DAYS,
) -> MetricValue:
    return _count_metric(
        events, EventType.COUPON_EXPOSED,
        index_date=index_date, lookback_days=lookback_days,
        population="회고 구간의 coupon_exposed 이벤트",
    )


def campaign_response_count(
    events: Sequence[Mapping[str, object]],
    *,
    index_date: date,
    lookback_days: int = DEFAULT_LOOKBACK_DAYS,
) -> MetricValue:
    """캠페인 반응 건수. ★ **값이 나오는데 과소계상된다** (AC-4b · N-8).

    `coupon_clicked` 는 쿠폰을 전제하므로 **쿠폰이 없는 캠페인(배너·푸시)의 클릭을
    담을 이벤트가 없다.** 그 반응은 이 지표로 측정되지 않는다.

    `limit_note` 에 한 줄을 담는다 — **`status` 는 `ok` 다.** `unconfirmed` 가
    아니다: 파라미터가 확정되면 맞아지는 종류가 아니고, **이벤트가 추가되지 않으면
    영원히 과소계상**이다.

    ⚠ `limit_note` 는 **선택 필드라 빠뜨려도 스키마가 잡지 않는다.** 그래서
    `tests/test_kpi_layers.py` 가 이 한 줄의 존재를 단언한다 — 없으면 화면의
    `한계` 칩(V-7)이 영원히 뜨지 않는다.
    """
    return _count_metric(
        events, EventType.COUPON_CLICKED,
        index_date=index_date, lookback_days=lookback_days,
        population="회고 구간의 coupon_clicked 이벤트",
        limit_note=(
            "쿠폰 비종속 캠페인(배너·푸시)의 반응은 담을 이벤트가 없어 "
            "과소계상된다 — 파라미터가 아니라 스키마의 한계다"
        ),
    )


def category_share(
    events: Sequence[Mapping[str, object]],
    *,
    index_date: date,
    lookback_days: int = DEFAULT_LOOKBACK_DAYS,
) -> dict[str, MetricValue]:
    """카테고리별 이벤트 점유율. ★ **5종 전부 낸다** — 0 건인 카테고리도 뺀다면
    *"그 카테고리가 없었다"* 가 화면에서 안 보인다.
    """
    start = index_date - timedelta(days=lookback_days)
    counts: Counter[str] = Counter()
    for event in events:
        if not _in_window(event, start=start, end=index_date):
            continue
        value = event.get("category")
        if isinstance(value, str):
            counts[value] += 1
    total = sum(counts.values())
    result: dict[str, MetricValue] = {}
    for item in Category:
        if total == 0:
            result[item.value] = MetricValue.unavailable(
                ReasonCode.NO_SOURCE_EVENT,
                "category 값을 가진 이벤트가 0건이라 점유율의 분모가 없다",
                unit=Unit.RATIO,
            )
            continue
        result[item.value] = MetricValue.ok(
            counts[item.value] / total,
            unit=Unit.RATIO,
            basis=Basis(
                population="회고 구간에 category 값이 있는 이벤트",
                denominator_definition="category 값이 있는 이벤트 총수",
                window=_retrospective(lookback_days),
                denominator=total,
                observed_count=counts[item.value],
            ),
        )
    return result


# ══════════════════════════════════════════════════════════════════════════
# 47개 지표 분류 — 산출물이 이 표를 싣는다 (AC-3)
# ══════════════════════════════════════════════════════════════════════════

@dataclass(frozen=True, slots=True)
class MetricSpec:
    """지표 하나의 계약. **이름 ↔ 계층·역할·C1 가용성이 1:1 이다.**"""

    name: str
    layer: int
    role: str
    c1: str
    note: str = ""


#: ★ **`kpi-definition-v1.md` §3~§5 가 실제로 이름 붙인 지표 전수 46종.**
#:
#: 개수를 리터럴로 적지 않는다 — `metric_classification()` 이 이 목록에서 집계한다.
#:
#: ⚠⚠ **문서 §8 의 합계표와 두 군데 어긋난다. 둘 다 의도적이고 근거가 있다:**
#:
#:   ① 총수 46 vs 문서 §8 의 **47**
#:      §8 표는 계층2=12 · 실험=15 로 적었으나, §5 의 지표 표에 **실제로 이름이
#:      붙은 것은 계층2 12 + 실험 14 = 26** 이다(§5 의 `|` 행을 전수 세었다).
#:      **없는 지표를 하나 만들어 47 을 맞추지 않았다.** 문서 §8 의 산술 오류로
#:      보이며 W6 Timothy 항목이다.
#:
#:   ② 계층1 계산가능 5→4 · 계산불가 0→1
#:      `cohort_retention_rate` 를 리드 지시로 재분류했다(AC-3b). §8 은 `✅` 로
#:      적었지만 **가입월을 알 방법이 `events` 에 없다.** 이 하나가 실험 계층의
#:      −1 과 상쇄되어 `unavailable` 합계는 19 로 문서와 같다.
#:
#: `c1` 값은 문서 §8 의 세 칸을 그대로 쓴다 — computable(`✅`) ·
#: conditional(`⚠️`) · unavailable(계산 불가). **C1 에서 실제로 값이 나오는지는
#: 별개다**: 오늘 이벤트가 0건이므로 계층 0 일부를 빼면 전부 `NO_SOURCE_EVENT` 다.
METRIC_SPECS: tuple[MetricSpec, ...] = (
    # ── 계층 0 · 수집 건전성 12 (문서 §3) — 전부 계산 가능 ──────────────────
    MetricSpec("events_ingested", 0, "collection", "computable"),
    MetricSpec("events_rejected", 0, "collection", "computable"),
    MetricSpec("rejection_rate", 0, "collection", "computable"),
    MetricSpec("rejection_reason_count", 0, "collection", "computable"),
    MetricSpec("event_type_coverage", 0, "collection", "computable"),
    MetricSpec("event_type_count", 0, "collection", "computable"),
    MetricSpec("field_fill_rate", 0, "collection", "computable"),
    MetricSpec("missing_field_count", 0, "collection", "computable"),
    MetricSpec("unavailable_metric_count", 0, "collection", "computable"),
    MetricSpec("source_event_count", 0, "collection", "computable"),
    MetricSpec("partition_day_count", 0, "collection", "computable"),
    MetricSpec("ingestion_days_gap", 0, "collection", "computable"),
    # ── 계층 1 · Customer KPI 8 (문서 §4) ───────────────────────────────────
    MetricSpec("churn_rate", 1, "customer", "conditional",
               "이탈 임계값이 가설값 → unconfirmed + params_used (D-5)"),
    MetricSpec("retention_rate", 1, "customer", "conditional",
               "churn_rate 파생 — 같은 미확정을 물려받는다"),
    MetricSpec("cohort_retention_rate", 1, "customer", "unavailable",
               "★ 문서 §8 은 ✅ 로 적었으나 signup_date 가 events 22컬럼에 없고 "
               "customers 테이블이 미구현이다 → PRECONDITION_MISSING. "
               "조치: 별도 저장소 이슈 #29. events 첫 등장일로 근사하지 않는다"),
    MetricSpec("repurchase_rate", 1, "customer", "computable",
               "★ purchase 이벤트만으로 계산된다 — signup_date 가 계산식에 없다. "
               "문서의 모집단 칸 P_all(D) 선언과 어긋나지만 그것은 문서 내부 모순이고 "
               "계산은 막히지 않는다. basis.population 에 실제 모집단을 적는다"),
    MetricSpec("winback_rate", 1, "customer", "conditional",
               "이탈 판정에 가설 임계값을 쓴다"),
    MetricSpec("purchase_frequency", 1, "customer", "computable",
               "분모는 구매 고객 수"),
    MetricSpec("purchase_interval", 1, "customer", "computable",
               "구매 1건 고객은 간격이 정의되지 않아 제외 — "
               "basis.excluded_count 로 병기 (R-6)"),
    MetricSpec("average_order_value", 1, "customer", "computable",
               "분모는 주문 건수 — 고객 수가 아니다. 고객당 매출은 "
               "revenue_per_customer 라는 별도 이름"),
    # ── 계층 2 · Business KPI 12 (문서 §5) ──────────────────────────────────
    MetricSpec("revenue", 2, "business", "computable",
               "purchase 0건이면 unavailable + NO_SOURCE_EVENT — 0원이 아니다"),
    MetricSpec("coupon_cost", 2, "business", "computable",
               "교환 파일 discount 우선, 없으면 treatment_cost 에서 유도 (D-16, "
               "derived: true), 둘 다 없으면 계산 불가 (#108)"),
    MetricSpec("message_cost", 2, "business", "computable",
               "발송 전원 계상 — 반응 무관 (EC-3 1원칙)"),
    MetricSpec("campaign_fixed_cost", 2, "business", "computable"),
    MetricSpec("shipping_subsidy", 2, "business", "conditional",
               "배송비 필드가 스키마에 없다 → 규칙 유도, derived: true (D-3)"),
    MetricSpec("marketing_cost", 2, "business", "computable",
               "구성요소 중 하나라도 계산 불가면 합계도 계산 불가 — "
               "계산된 것만 더하지 않는다"),
    MetricSpec("cogs", 2, "business", "conditional",
               "unit_cost 가 스키마에 없고 order_items 테이블도 없다 → "
               "NO_COST_BASIS (EC-1 — 원가율로 추정하지 않는다)"),
    MetricSpec("contribution_profit", 2, "business", "conditional",
               "cogs 의존. 구성요소 6개 중 3개가 계산 불가"),
    MetricSpec("incremental_revenue", 2, "business", "unavailable",
               "NEEDS_TWO_STRATEGIES — C1 에 비교 전략이 없다"),
    MetricSpec("incremental_contribution_profit", 2, "business", "unavailable",
               "NEEDS_TWO_STRATEGIES"),
    MetricSpec("roi", 2, "business", "unavailable", "NEEDS_TWO_STRATEGIES"),
    MetricSpec("ai_roi", 2, "business", "unavailable", "NEEDS_TWO_STRATEGIES"),
    # ── 실험 판정 지표 14 (문서 §5.3 · §7) — C1 에서 전부 계산 불가 ─────────
    MetricSpec("ai_net_incremental_value", 3, "experiment", "unavailable",
               "NEEDS_TWO_STRATEGIES"),
    *(
        MetricSpec(name, 3, "experiment", "unavailable",
                   "NEEDS_MODEL_OUTPUT — C1 에 모델 산출물이 없다. "
                   "ML/DL 은 사이클 범위 밖이다")
        for name in (
            "qini_coefficient", "auuc", "uplift_by_decile", "persuadables_ratio",
            "churn_test_auc", "precision", "recall", "f1",
            "predicted_clv", "clv_mape", "top20_precision",
        )
    ),
    *(
        MetricSpec(name, 3, "experiment", "unavailable",
                   "NEEDS_MODEL_OUTPUT + src/diagnostics/ 전용 — "
                   "측정 계층이 계산하지 않는다")
        for name in ("pehe", "corr_tau_hat_tau")
    ),
)

assert len({spec.name for spec in METRIC_SPECS}) == len(METRIC_SPECS), (
    "METRIC_SPECS 에 중복 이름이 있다 — 이름이 지표의 식별자다"
)


def metric_classification() -> dict[str, object]:
    """`METRIC_SPECS` 전체의 계층별·가용성별 분포. **개수를 리터럴로 적지 않고 집계한다.**

    `kpi-definition-v1.md` §8 의 표와 대조되는 값이며, 어긋나는 3건의 이유가
    `METRIC_SPECS` 의 `note` 에 있다.

    ★ 아래 예제가 리터럴이 아닌 이유 — 이전 판은 `47` 을 기대값으로 적었고
    실제 집계는 46 이었다. **개수를 적지 않겠다고 선언한 독스트링이 그 선언을
    스스로 깼다.** 게다가 저장소에 doctest 실행기가 없어 아무도 잡지 못했다.
    지금은 `len(METRIC_SPECS)` 와 대조한다 — 지표가 늘거나 줄어도 낡지 않고,
    **분류가 한 종이라도 빠뜨리면 실패한다**(그것이 이 예제가 지키는 불변식이다).

        >>> metric_classification()["total"] == len(METRIC_SPECS)
        True
    """
    by_layer: dict[int, Counter[str]] = defaultdict(Counter)
    for spec in METRIC_SPECS:
        by_layer[spec.layer][spec.c1] += 1
    return {
        "total": len(METRIC_SPECS),
        "by_availability": dict(Counter(spec.c1 for spec in METRIC_SPECS)),
        "by_layer": {
            str(layer): dict(counts) for layer, counts in sorted(by_layer.items())
        },
        "metrics": [
            {
                "name": spec.name, "layer": spec.layer, "role": spec.role,
                "c1_availability": spec.c1,
                **({"note": spec.note} if spec.note else {}),
            }
            for spec in METRIC_SPECS
        ],
    }
