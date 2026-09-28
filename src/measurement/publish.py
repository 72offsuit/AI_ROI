"""측정 산출물 게시 — `results/` 6종 + 인덱스 (T2.7).

## 이 모듈이 유일하게 아는 것

★ **출처를 아는 유일한 자리다.** `kpi.py`·`economics.py` 는 출처를 모르고, 출처별
결과가 필요하면 **분기가 아니라 입력 분할**로 얻는다 (N-3):

    by_source = partition_by_source(events)
    {"commerce":  metric(by_source.commerce),   같은 함수
     "simulator": metric(by_source.simulator)}  같은 식, 다른 입력

★ **조립을 하는 유일한 자리다.** `events` → `OrderView`·`OrderItem` 변환이 여기
있다 — 계산층을 순수 함수로 유지하려면 조립이 출처를 아는 층과 같은 곳이어야 한다.

★ **`headline_code` 순위를 구현하는 유일한 자리다.** 화면·테스트가 같은 함수를
쓴다. 화면이 순위를 정하면 화면마다 다른 최상위가 나온다 (DB-012).

## 원자성 — 부분 게시물을 남기지 않는다

    staging 에 전부 쓴다  →  자기검증  →  os.replace 로 이동  →  index.json 을 마지막에
                                              ↑ 실패하면 최종 경로에 아무것도 안 남는다

`index.json` 이 마지막인 이유: 대시보드는 그것을 진입점으로 읽는다. 먼저 쓰면
아직 없는 산출물을 가리키는 인덱스가 존재하는 순간이 생긴다.

## 종료 코드

    0  ok · partial   게시했다 (partial 도 0 이다 — 게시 자체는 성공했고 그 사실이
                      publish_result 에 담긴다. 대시보드가 숨기지 않고 표시한다)
    2  QualityGateFailure    데이터가 품질 검사를 위반했다
    3  ContractViolation     게시물이 자기 계약을 어겼다 (fail closed)
    5  ConfigError           경제 규칙 config 를 읽을 수 없다
    6  PublishError          I/O 실패
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
from collections import Counter
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Iterable, Mapping, Sequence

from src.measurement import timeparse as tp
from src.measurement import contracts as ct
from src.measurement import coverage as cov
from src.measurement import economics as ec
from src.measurement import exchange as ex
from src.measurement import freeze as fz
from src.measurement import kpi
from src.measurement import schema as sc
from src.measurement import validate as dq
from src.measurement.config_loader import (
    DEFAULT_ECONOMIC_CONFIG,
    CostAccountingConfig,
    load_economic_config,
)
from src.measurement.errors import (
    ConfigError,
    ContractViolation,
    MeasurementError,
    PublishError,
    QualityGateFailure,
)
from src.measurement.sink import (
    MANIFEST_NAME,
    REJECT_LOG_NAME,
    EventSource,
    event_source,
    latest_run_id,
    read_events,
    verify_lineage,
)

DEFAULT_SOURCE_ROOT = Path("data/raw")
DEFAULT_OUTPUT_ROOT = Path("results")
STAGING_SUFFIX = ".staging"
INDEX_NAME = "index.json"
"""인덱스 파일명. 위치는 `artifact_relative("index")` 가 정한다 (ADR-0002)."""

MEASUREMENT_SUBDIR = "measurement"
"""★ **ADR-0002** — 측정 계층 게시물은 `results/measurement/` 아래에 둔다.

이후 사이클에서 `src/decision/` 이 `results/churn_predictions.csv` 등 8종을 같은
디렉터리에 쓴다 (`data_spec` §7.5). 한 디렉터리에 섞이면 **누가 쓴 파일인지가
파일명 관례에만 의존**한다. 하위 디렉터리로 나누면 **소유 경계가 파일시스템에
드러나고** 겹침 0 이 구조로 유지된다."""

ROOT_LEVEL_ARTIFACTS = frozenset({"data_quality_report"})
"""★ **ADR-0002 의 예외 하나** — `results/data_quality_report.json` 은 루트에 둔다.

`data_spec` §9 와 이슈 `#48` 본문이 **그 경로를 명시했다.** 일관성보다 정본이
우선한다 — 경로를 바꾸면 정본 두 개가 생긴다.

두 진실이 되지 않는 이유: `index.json` 의 `artifacts[].path` 가 각 파일을 **경로로
참조**하므로 읽는 쪽이 위치를 추측하지 않는다."""

#: 관측 화면군 V1~V6 ↔ 산출물. `usp.md` §1.8 이 정의한 6화면이 키다.
VIEW_BINDINGS: Mapping[str, tuple[str, str, str]] = {
    "V1": ("수집 현황", "ingestion_report", "/ingestion"),
    "V2": ("거부 사유", "rejection_report", "/rejections"),
    "V3": ("필드 충족률", "field_coverage_report", "/coverage"),
    # ★ R-1 — `/kpi` 다. 1차 구현이 `/metrics` 로 썼고 Andrew 가 화면에서 잡았다.
    #   W2 정합 라운드에서 Jonnathan 이 James 의 라우트 이름을 채택했다
    #   (`/metrics`→`/kpi` · `/fields`→`/coverage` · `/seal`→`/freeze`) — 근거는
    #   **산출물 이름과 1:1 이라 `views.route` 가 기계가독**이라는 것이다.
    #   `examples/*/index.json` 픽스처가 `/kpi` 이고 그것이 정본이다.
    "V4": ("지표 가용성", "kpi_report", "/kpi"),
    "V5": ("데이터 품질", "data_quality_report", "/quality"),
    "V6": ("봉인 상태", "freeze_status", "/freeze"),
}


# ── 출처 분할 (N-3) ─────────────────────────────────────────────────────────

@dataclass(frozen=True, slots=True)
class SourceSplit:
    """출처별로 나눈 이벤트. **두 키가 항상 존재한다** — 0건이어도 빼지 않는다."""

    commerce: tuple[Mapping[str, object], ...]
    simulator: tuple[Mapping[str, object], ...]

    def items(self) -> tuple[tuple[str, tuple[Mapping[str, object], ...]], ...]:
        return (
            (EventSource.COMMERCE.value, self.commerce),
            (EventSource.SIMULATOR.value, self.simulator),
        )


def partition_by_source(events: Iterable[Mapping[str, object]]) -> SourceSplit:
    """`sink.event_source()` 를 쓴다. ★ **재분류하지 않는다.**

    출처 판별 규칙이 두 곳에 살면 갈라지고, 갈라지면 어느 쪽이 정본인지 알 수
    없다. `tests/test_neutrality.py test_source_classification_is_single_sourced`
    가 이 규칙을 참조하는 파일을 `schema.py`·`sink.py` 로 제한한다.
    """
    buckets: dict[str, list[Mapping[str, object]]] = {
        EventSource.COMMERCE.value: [], EventSource.SIMULATOR.value: [],
    }
    for event in events:
        buckets[event_source(event).value].append(event)
    return SourceSplit(
        commerce=tuple(buckets[EventSource.COMMERCE.value]),
        simulator=tuple(buckets[EventSource.SIMULATOR.value]),
    )


# ── events → OrderView 조립 ─────────────────────────────────────────────────

def assemble_orders(
    events: Sequence[Mapping[str, object]],
    exchange: ex.CommerceExchange | None = None,
) -> tuple[ec.OrderView, ...]:
    """`purchase` 이벤트를 `OrderView` 로 조립한다.

    `purchase` 는 주문 단위 1행이고 `product_id`·`quantity`·`unit_price` 가
    `NOT_APPLICABLE` 이다 — 값이 있으면 `validate_event()` 가 거부한다. 즉 **한
    주문의 품목을 `events` 안에서 재구성할 방법이 없다.** 품목·원가·배송비는 커머스
    교환 파일(`exchange`, 이슈 #100)이 싣고, 같은 `order_id` 인 주문에만 붙는다.

    ★ 붙이는 기준은 출처가 아니라 **`order_id` 가 교환 파일에 있는가**다. 교환
    파일에 없는 주문은 `items=()` 로 남고 `cogs()` 가 `NO_COST_BASIS` 를 낸다.

    ★ 매출은 **이벤트의** `order_amount` 다. 교환 파일의 금액으로 바꾸지 않는다 —
    둘이 같은지는 `DQ-09` 가 본다. 여기서 바꾸면 대조할 두 값이 하나가 된다.

    `add_to_cart` 로 근사하지 않는다: `remove_from_cart` 가 있고, 담았지만 사지
    않은 품목이 있고, 결제 실패가 있다. 근사하면 COGS 가 그럴듯하게 틀린다.
    """
    coupon_orders = {
        event.get("order_id")
        for event in events
        if event.get("event_type") == sc.EventType.COUPON_USE.value
    }
    known = exchange.orders if exchange is not None else {}
    orders: list[ec.OrderView] = []
    for event in events:
        if event.get("event_type") != sc.EventType.PURCHASE.value:
            continue
        order_id = event.get("order_id")
        amount = event.get("order_amount")
        if not isinstance(order_id, str) or not isinstance(amount, int):
            # 결손을 0 으로 채우지 않는다. 조립 대상이 아니면 빼고, 그 사실은
            # DQ-11(Key 결측)이 잡는다 — 여기서 조용히 보정하지 않는다.
            continue
        treatment = event.get("treatment_id")
        exchanged = known.get(order_id)
        orders.append(
            ec.OrderView(
                order_id=order_id,
                order_amount=amount,
                items=exchanged.items if exchanged else (),
                treatment_ids=(treatment,) if isinstance(treatment, str) else (),
                has_coupon_use=order_id in coupon_orders,
                discount=exchanged.discount if exchanged else None,
                shipping_fee=exchanged.shipping_fee if exchanged else None,
                shipping_charged=exchanged.shipping_charged if exchanged else None,
            )
        )
    return tuple(orders)


def assemble_campaign(
    events: Sequence[Mapping[str, object]],
    exchange: ex.CommerceExchange | None = None,
) -> ec.CampaignView:
    """`push_sent`·`coupon_use` 에서 캠페인 관측 사실을 조립한다.

    `messages_sent`(발송 건수)와 `targeted_customers`(고유 고객 수)를 나눈다 —
    EC-4. 같은 고객에게 두 번 발송하면 메시지는 2건이지만 `N_targeted` 는 1명이다.
    """
    sent = [
        event for event in events
        if event.get("event_type") == sc.EventType.PUSH_SENT.value
    ]
    campaign_ids = {
        event.get("campaign_id") for event in events
        if isinstance(event.get("campaign_id"), str)
    }
    return ec.CampaignView(
        campaign_id=sorted(campaign_ids)[0] if campaign_ids else "(캠페인 없음)",
        messages_sent=len(sent),
        targeted_customers=len({
            event.get("customer_id") for event in sent
            if isinstance(event.get("customer_id"), str)
        }),
        campaigns_run=len(campaign_ids),
        coupon_used_orders=assemble_orders(events, exchange),
    )


# ── ★ headline_code 순위 — 구현하는 유일한 자리 (AC-4c) ─────────────────────

#: 계약 `index.schema.json` 의 `headline_code` enum 나열 순서와 **같아야 한다.**
#: 아래 `_assert_priority_matches_contract()` 가 계약 파일을 읽어 대조한다 —
#: 순위를 두 곳에 적으면 갈라진다.
HEADLINE_PRIORITY: tuple[str, ...] = (
    "CONTRACT_VIOLATION",
    "FREEZE_MISMATCH",
    "QUALITY_VIOLATION",
    "REJECTED_EVENTS",
    "SINK_EMPTY",
    "CHECKS_NOT_RUN",
    "METRICS_UNAVAILABLE",
    "ALL_CLEAR",
)


def choose_headline_code(
    counts: Mapping[str, int],
    *,
    events_ingested: Mapping[str, object] | None = None,
    contract_violation: bool = False,
) -> str:
    """최상위 판정 하나. **순위는 계약이 정하고 이 함수가 구현한다.**

    화면은 코드→문구 매핑만 한다 (DB-012). 화면이 `counts` 를 다시 세면 집계 규칙이
    두 곳에 살고 화면과 리포트가 다른 숫자를 낸다.

    ★ **`SINK_EMPTY` 의 입력은 `ingestion_report.totals.events_ingested`** 다 —
    `verdict.counts` 에 수집 건수가 없다(실측). 그리고 그 지표의 `status` 가 `ok` 가
    아니면 `SINK_EMPTY` 를 고르지 않는다: **모르는 것을 0 으로 읽지 않는다.**

        >>> choose_headline_code({"rejected_events": 3}, events_ingested={"status": "ok", "value": 10})
        'REJECTED_EVENTS'
        >>> choose_headline_code({"rejected_events": 0}, events_ingested={"status": "ok", "value": 0})
        'SINK_EMPTY'
    """
    if contract_violation:
        return "CONTRACT_VIOLATION"
    # ★ 이전 판은 `lock_items_pending and freeze_mismatch` 였고 **유효하게 발동할 수
    #   있는 실측 조건이 존재한 적이 없었다** (리뷰 M4 · 보안 F8 · 이슈 #60):
    #
    #     겹1  `freeze_mismatch` 는 index 의 counts 에 채워지지 않았다. 게다가
    #          계약이 `additionalProperties: false` 로 그 키를 **금지**했다 —
    #          읽는 쪽이 계약상 존재할 수 없는 키를 보고 있었다.
    #     겹2  `lock_items_pending` 은 이름과 달리 LOCK_ITEMS 의 PENDING 수가 아니라
    #          **G-선행조건 미충족 수**이고, 16종이 전부 충족이라 실측 0 이다.
    #          겹1 만 고쳐도 오늘 경보가 뜨지 않았다.
    #
    #   봉인 불일치는 **미결 항목이 있든 없든** 알려야 한다. 오히려 전부 봉인된
    #   상태에서 불일치가 생기는 것이 더 위험하므로, 그때 침묵하는 조건은 정반대다.
    if counts.get("freeze_mismatch", 0):
        return "FREEZE_MISMATCH"
    if counts.get("quality_violations", 0):
        return "QUALITY_VIOLATION"
    if counts.get("rejected_events", 0):
        # ★ 계약이 이 경우 ALL_CLEAR 를 금지한다 (B-11 가드). 순위로도 막는다.
        return "REJECTED_EVENTS"
    if (
        events_ingested is not None
        and events_ingested.get("status") == "ok"
        and events_ingested.get("value") == 0
    ):
        return "SINK_EMPTY"
    if counts.get("checks_not_run", 0) or counts.get("checks_blocked", 0):
        return "CHECKS_NOT_RUN"
    if counts.get("metrics_unavailable", 0) or counts.get("metrics_not_run", 0):
        return "METRICS_UNAVAILABLE"
    return "ALL_CLEAR"


def headline_level(code: str) -> str:
    """`violation` > `attention` > `ok` — 배너 색의 근거."""
    if code in ("CONTRACT_VIOLATION", "FREEZE_MISMATCH", "QUALITY_VIOLATION"):
        return "violation"
    if code == "ALL_CLEAR":
        return "ok"
    return "attention"


# ── 산출물 빌더 ─────────────────────────────────────────────────────────────

def _metric(value: sc.MetricValue) -> dict[str, object]:
    return ct.metric_to_json(value)


def _split(
    split: SourceSplit, compute
) -> dict[str, object]:
    """`by_source` 두 키. ★ **`combined` 를 만들지 않는다** (계층 1·2, R-7)."""
    return {
        "by_source": {
            name: _metric(compute(events)) for name, events in split.items()
        }
    }


def _split_with_combined(
    split: SourceSplit, all_events: Sequence[Mapping[str, object]], compute
) -> dict[str, object]:
    """계층 0 전용 — **`combined` 가 허용되는 유일한 계층**이다 (R-7)."""
    payload = _split(split, compute)
    payload["combined"] = _metric(compute(all_events))
    return payload


def _source_link_state(
    events: Sequence[Mapping[str, object]],
) -> dict[str, object]:
    """출처 하나의 연결 상태.

    ★ **결정 가능한 것만 담는다.** `link_state` 는 `never_connected`(이 출처로
    수신한 이벤트가 한 건도 없다 — **정상일 수 있다**)와 `connected`(수신 이력이
    있다) 둘뿐이다.

    `stale`(멈췄다)을 enum 값으로 두지 않는다: 정지 판정 임계값이 확정되지 않았고
    C1 에서 그 상태에 도달할 수 없어 검증도 불가능하다. **도달 불가 분기를 enum 에
    넣으면 화면이 그릴 수 없는 상태를 그리려 한다.** 대신 `staleness` 가 값이 아닌
    **사유**를 준다 — 화면이 추측하지 않게.
    """
    stamps = sorted(
        str(event["timestamp"]) for event in events if event.get("timestamp")
    )
    connected = bool(events)
    return {
        "link_state": "connected" if connected else "never_connected",
        "first_event_at": stamps[0] if stamps else None,
        "last_event_at": stamps[-1] if stamps else None,
        "event_count": len(events),
        "staleness": _metric(
            sc.MetricValue.not_run(
                "마지막 수신 이후 멈춘 것인지 판정할 임계값이 확정되지 않았고, "
                "C1 에서 그 상태에 도달할 수 없어 검증도 불가능하다 — 값 대신 "
                "사유를 준다",
                reason_code=sc.ReasonCode.PARAM_UNCONFIRMED,
                unit=sc.Unit.DAYS,
            )
        ),
    }


def build_ingestion_report(
    manifest: Mapping[str, object],
    split: SourceSplit,
    partition_dates: Sequence[date],
) -> dict[str, object]:
    """V1 — 계층 0 수집 건전성."""
    def manifest_for(events: Sequence[Mapping[str, object]]) -> dict[str, object]:
        """출처별 부분 manifest. 전체 manifest 를 나누지 않고 다시 센다."""
        counts = Counter(str(e.get("event_type")) for e in events)
        # ★ 커버리지 계열도 **그 출처의 이벤트에서 다시 센다** (이슈 #99).
        #   예전에는 여기서 전체 manifest 의 값을 그대로 복사했다 — 출처를
        #   나눠 놓고 커버리지만 전체 값을 붙이는 것 자체가 어긋났고, manifest
        #   가 마지막 실행분만 담고 있어 이어붙인 데이터에서는 더 틀렸다.
        tally = cov.tally(events)
        return {
            "rows": len(events), "rejected": 0,
            "event_type_counts": dict(counts),
            "missing_fields": cov.missing_fields(tally),
            "unavailable_metrics": cov.unavailable_metrics(counts),
            "sources": {},
        }

    all_events = split.commerce + split.simulator
    observed = sorted(set(partition_dates))
    rows_by_date: dict[date, Counter[str]] = {}
    for name, events in split.items():
        for event in events:
            moment = _event_day(event)
            if moment is not None:
                rows_by_date.setdefault(moment, Counter())[name] += 1

    # ★ 관측 구간 안의 **빈 날짜도 행으로 낸다.** 빼면 공백이 화면에서 사라지고
    #   "수집이 멈춘 날"과 "그 날이 없는 것"이 같아 보인다.
    span: list[date] = []
    if observed:
        cursor = observed[0]
        while cursor <= observed[-1]:
            span.append(cursor)
            cursor += timedelta(days=1)

    return {
        "totals": {
            "events_ingested": _split_with_combined(
                split, all_events, lambda e: kpi.events_ingested(manifest_for(e))
            ),
            "events_rejected": _metric(kpi.events_rejected(manifest)),
            "rejection_rate": _metric(kpi.rejection_rate(manifest)),
            "event_type_coverage": _metric(kpi.event_type_coverage(manifest)),
            "partition_day_count": _metric(kpi.partition_day_count(partition_dates)),
            "ingestion_days_gap": _metric(kpi.ingestion_days_gap(partition_dates)),
            "unavailable_metric_count": _metric(
                kpi.unavailable_metric_count(
                    cov.unavailable_metrics(
                        Counter(str(e.get("event_type")) for e in events)
                    )
                )
            ),
            # ★ X-5 — 공백이 몇 개인지는 알고, 그것이 무엇인지는 모른다고 말한다.
            "ingestion_gap_attribution": _metric(kpi.ingestion_gap_attribution()),
        },
        # ★ 16종 전부. 0건인 타입을 목록에서 빼지 않는다.
        "by_event_type": {
            name: _split(split, lambda e, n=name: kpi.event_type_count(
                manifest_for(e))[n])
            for name in (item.value for item in sc.EventType)
        },
        "partitions": [
            {
                "date": day.isoformat(),
                "present": day in rows_by_date,
                "rows": {
                    "by_source": {
                        source: _metric(
                            sc.MetricValue.ok(
                                rows_by_date.get(day, Counter()).get(source, 0),
                                unit=sc.Unit.COUNT,
                                basis=sc.Basis(
                                    population=f"{day.isoformat()} 파티션의 이벤트",
                                    denominator_definition="분모 없음 (합계)",
                                    window=sc.Window(
                                        sc.WindowDirection.POINT_IN_TIME,
                                        label=day.isoformat(),
                                    ),
                                    observed_count=rows_by_date.get(
                                        day, Counter()).get(source, 0),
                                ),
                            )
                        )
                        for source in (
                            EventSource.COMMERCE.value, EventSource.SIMULATOR.value
                        )
                    }
                },
                "in_observed_range": True,
            }
            for day in span
        ],
        "sources": {
            name: _source_link_state(events) for name, events in split.items()
        },
    }


def _event_day(event: Mapping[str, object]) -> date | None:
    raw = event.get("timestamp")
    if isinstance(raw, datetime):
        return raw.date()
    try:
        return tp.parse_datetime(str(raw)).date()
    except (TypeError, ValueError):
        return None


#: 거부 사유 문자열 → 계약 `reason_key` enum. `validate_event()` 의 한글 메시지를
#: 기계가 읽는 키로 옮긴다.
#:
#: ★ 순서가 중요하다 — 첫 일치를 쓴다. "해당 없는 필드에 값이 있음" 이
#: "필수 필드 누락" 보다 먼저 와야 둘이 섞이지 않는다.
_REASON_KEYS: tuple[tuple[str, str, str], ...] = (
    ("알 수 없는 event_type", "UNKNOWN_EVENT_TYPE", "스키마에 없는 event_type"),
    ("통과할 수 없는 필드", "FORBIDDEN_FIELD",
     "측정 계층을 통과할 수 없는 필드 (Hidden Trait·라벨 계열)"),
    ("스키마에 없는 필드", "UNKNOWN_FIELD", "DATA-003 22컬럼 밖의 필드"),
    ("해당 없는 필드에 값이 있음", "NOT_APPLICABLE_FIELD_PRESENT",
     "이 이벤트 타입에 해당하지 않는 필드에 값이 있다"),
    ("필수 필드 누락", "MISSING_REQUIRED_FIELD", "필수 필드가 비어 있다"),
    ("0 이상이어야 한다", "NEGATIVE_AMOUNT", "금액·수량이 음수다"),
    ("식별자 형식 위반", "IDENTIFIER_FORMAT", "식별자가 규정 형식을 어겼다"),
    ("허용값이 아니다", "DISALLOWED_ENUM_VALUE", "category·page_type 허용값 밖"),
    ("오프셋이 없다", "TIMEZONE_POLICY",
     "timestamp 에 UTC 오프셋이 없어 순간을 특정할 수 없다"),
)


def classify_rejection(problem: str) -> tuple[str, str]:
    """거부 사유 한 줄 → `(reason_key, reason_label)`.

    분류되지 않으면 `OTHER` 다 — **조용히 버리지 않는다.** 새 검증이 추가되면
    `OTHER` 가 늘고, 그것이 매핑을 갱신할 신호다.
    """
    for needle, key, label in _REASON_KEYS:
        if needle in problem:
            return key, label
    return "OTHER", "위 분류에 들지 않는 사유 — _REASON_KEYS 갱신이 필요하다"


def build_rejection_report(
    manifest: Mapping[str, object], rejected: Sequence[Mapping[str, object]]
) -> dict[str, object]:
    """V2 — 거부 사유. ★ **원문을 게시하지 않는다** (AC-6).

    `samples[]` 는 `reason_key`·`event_type`·`partition_date`·`source`·
    `problems`·`offending_fields`(**필드 이름만**) 만 담는다.

    ★★ `offending_values` 를 **담지 않는다.** 계약이 키를 22컬럼으로 제한하지만,
    `rejected.jsonl` 에는 Hidden Trait 이 원문으로 남는다 — 거부된 이유가 바로 그
    필드의 존재인 경우가 있고, 그 값을 게시하면 게시물이 `ISO-003`(측정 계층을
    통과할 수 없는 값)을 우회하는 통로가 된다. **화이트리스트를 통과시키는 것보다
    아예 담지 않는 것이 안전하다** — 화면이 값을 필요로 하지 않는다.
    """
    reasons: Counter[tuple[str, str]] = Counter()
    samples: list[dict[str, object]] = []
    for entry in rejected:
        problems = [str(p) for p in (entry.get("problems") or [])]
        record = entry.get("record") or {}
        first = problems[0] if problems else "(사유 없음)"
        key, label = classify_rejection(first)
        reasons[(key, label)] += 1
        if len(samples) < 20:
            day = str(record.get("timestamp") or "")[:10]
            samples.append({
                "reason_key": key,
                "event_type": (
                    str(record.get("event_type"))
                    if record.get("event_type") is not None else None
                ),
                "partition_date": day if len(day) == 10 else None,
                "source": event_source(record).value if record else "unknown",
                "problems": problems or ["(사유 없음)"],
                # ★ 필드 **이름만**. 값은 담지 않는다 — 위 독트링 참조.
                "offending_fields": sorted(
                    name for name in record if name in sc.FIELD_INDEX
                ),
            })
    return {
        "totals": {
            "events_rejected": _metric(kpi.events_rejected(manifest)),
            "rejection_rate": _metric(kpi.rejection_rate(manifest)),
            "distinct_reasons": _metric(
                sc.MetricValue.ok(
                    len(reasons), unit=sc.Unit.COUNT,
                    basis=sc.Basis(
                        population="거부 레코드의 사유 분류",
                        denominator_definition="분모 없음 (합계)",
                        window=sc.Window(sc.WindowDirection.POINT_IN_TIME),
                        observed_count=len(rejected),
                    ),
                )
            ),
        },
        "by_reason": [
            {"reason_key": key, "reason_label": label, "count": count}
            for (key, label), count in sorted(
                reasons.items(), key=lambda kv: (-kv[1], kv[0][0])
            )
        ],
        "samples": samples,
    }


#: ★ 필드 → 그 필드가 결손일 때 계산할 수 없게 되는 지표 (`blocks_metrics`).
#:
#: **화면이 결손→영향 사슬을 추론하지 않게 게시 시점에 넣는다** (DB-012). 역방향은
#: `kpi_report.metrics[].value.blocked_by` 이고, 화면은 이 배열을 뒤집어 인덱스를
#: 만들 수 있다 — 그것은 같은 데이터의 재배열이지 새 분류가 아니다.
_BLOCKS_METRICS: Mapping[str, tuple[str, ...]] = {
    "order_amount": ("revenue", "average_order_value", "contribution_profit"),
    "order_id": ("average_order_value", "revenue"),
    "customer_id": ("churn_rate", "retention_rate", "repurchase_rate",
                    "purchase_frequency", "purchase_interval", "winback_rate"),
    "timestamp": ("churn_rate", "purchase_interval", "ingestion_days_gap"),
    "coupon_id": ("coupon_usage_count", "coupon_cost"),
    "campaign_id": ("campaign_fixed_cost", "campaign_response_count"),
    "treatment_id": ("coupon_cost", "shipping_subsidy"),
    "category": ("category_share",),
    "quantity": ("cogs",),
    "unit_price": ("cogs",),
    "session_id": ("purchase_frequency",),
}

#: ★ 계산식이 요구하는데 **컬럼 자체가 없는** 것. 결손(`missing_fields`)과 다르다 —
#: 전자는 데이터를 더 모으면 풀리고 후자는 **스키마를 바꿔야** 풀린다. 화면이 그
#: 차이를 보여줄 수 있어야 조치가 달라진다.
_SCHEMA_GAPS: tuple[dict[str, object], ...] = (
    {
        "ref": "unit_cost",
        "required_by_formula": "COGS = Σ(unit_cost × quantity)",
        "where_it_should_live": "products 테이블 또는 order_items 테이블",
        "blocks_metrics": ["cogs", "contribution_profit", "marketing_cost"],
        "reason_code": sc.ReasonCode.NO_COST_BASIS.value,
        "reason_detail": (
            "DATA-003 22컬럼에 unit_cost 가 없다. 커머스 교환 파일(order_items, "
            "#100)이 있는 주문은 주문 시점 원가로 계산하고, 없는 주문은 근거가 "
            "없다. 원가율을 곱해 추정하지 않는다 (EC-1) — 그러면 기여이익이 "
            "매출의 상수배가 되어 revenue_up_profit_down 가드레일이 발동할 수 없다"
        ),
    },
    {
        "ref": "discount",
        "required_by_formula": "order_amount = Σ(unit_price × quantity) − discount",
        "where_it_should_live": "events 22컬럼",
        "blocks_metrics": ["coupon_cost", "contribution_profit"],
        "reason_code": sc.ReasonCode.MISSING_FIELD.value,
        "reason_detail": (
            "schema.py 가 order_amount 를 이 식으로 정의하는데 discount 가 "
            "22컬럼에 없다. 커머스 교환 파일이 있는 주문은 실제 할인액을 쓰고, "
            "없으면 treatment_cost 에서 유도한다 (D-16, derived: true). 둘 다 "
            "없는 쿠폰 사용 주문이 있으면 coupon_cost 는 계산 불가다 (#108)"
        ),
    },
    {
        "ref": "shipping_fee",
        "required_by_formula": (
            "shipping_subsidy = Σ 면제된 배송비 (order_amount < 무료배송 기준 ∧ T1)"
        ),
        "where_it_should_live": "events 22컬럼",
        "blocks_metrics": ["shipping_subsidy", "contribution_profit"],
        "reason_code": sc.ReasonCode.MISSING_FIELD.value,
        "reason_detail": (
            "배송비 필드가 22컬럼에 없다. 커머스 교환 파일이 있는 주문은 "
            "shipping_fee − shipping_charged 관측값을 쓰고(#100), 없는 주문은 "
            "무료배송 기준과 T1 처치에서 유도한다 (D-3, derived: true)"
        ),
    },
    {
        "ref": "signup_date",
        "required_by_formula": "P_all(D) = {c : signup_date(c) ≤ D}",
        "where_it_should_live": "customers 테이블",
        "blocks_metrics": ["cohort_retention_rate"],
        "reason_code": sc.ReasonCode.PRECONDITION_MISSING.value,
        "reason_detail": (
            "customers 테이블이 미구현이고 signup_date 가 22컬럼에 없다. "
            "events 첫 등장일은 가입일이 아니므로 근사하지 않는다 — 이벤트는 "
            "'무언가 한 고객'만 보여주지 전체 고객 명부가 아니다. "
            "조치: Ecommerce_Service #29"
        ),
    },
    {
        "ref": "refund",
        "required_by_formula": "net_revenue = Σ order_amount − Σ refund",
        "where_it_should_live": "events 22컬럼 (event_type 또는 금액 필드)",
        "blocks_metrics": ["revenue", "contribution_profit"],
        "reason_code": sc.ReasonCode.MISSING_FIELD.value,
        "reason_detail": (
            "환불 이벤트를 담을 자리가 없다. DATA-003 이 22컬럼을, PRD §30.1 이 "
            "event_type 16종을 고정하고 둘 다 Plan/ SRS 개정을 요구한다 (권한 밖). "
            "가정 A-REFUND 로 총매출을 순매출로 간주하며 기여이익이 과대평가된다 "
            "(결정 D-2)"
        ),
    },
)


def build_field_coverage_report(
    events: Sequence[Mapping[str, object]], split: SourceSplit
) -> dict[str, object]:
    """V3 — 필드 충족률 22컬럼 + 스키마 공백.

    ★ **22컬럼 전부 낸다** (계약이 `minProperties: 22` · `maxProperties: 22`).
    한 건도 안 들어온 필드를 목록에서 빼면 *"안 들어왔다"* 가 화면에서 사라진다.
    """
    tally = cov.tally(events)
    rates = kpi.field_fill_rate(tally)
    applicable = {
        spec.name: tuple(
            item.value for item in sc.EventType
            if sc.requirement(item, spec.name) is not sc.Requirement.NOT_APPLICABLE
        )
        for spec in sc.EVENT_FIELDS
    }
    return {
        "fields": {
            spec.name: {
                "group": spec.group.value,
                "fill_rate": _split(split, lambda e, n=spec.name: rates[n]),
                "applicable_event_types": list(applicable[spec.name]),
                "blocks_metrics": list(_BLOCKS_METRICS.get(spec.name, ())),
            }
            for spec in sc.EVENT_FIELDS
        },
        "missing_fields": cov.missing_fields(tally),
        "schema_gaps": [dict(gap) for gap in _SCHEMA_GAPS],
    }


#: 지표 이름 → 계약이 요구하는 메타 `(layer, role, population, window,
#: denominator_definition, formula, definition_ref, source_events)`.
#:
#: ★ **계약의 `layer`·`population` 은 enum 이다.** `kpi.METRIC_SPECS` 의 숫자
#: 계층(0~3)과 표기가 다르므로 여기서 옮긴다 — 계약 쪽 어휘가 정본이다.
#:
#: `population` 에 `"고객"` 이라고만 쓰는 것이 R-4 위반이고, 계약이 enum 으로
#: 그것을 막는다. `repurchase_rate` 가 `P_all` 이 아니라 `orders` 인 것이
#: AC-3b 정정의 핵심이다 — 모집단이 `purchase` 이벤트에서 나온다.
_KPI_META: Mapping[str, dict[str, object]] = {
    "churn_rate": {
        "layer": "customer_kpi", "population": "P_buyer",
        "window": {"direction": "point_in_time", "label": "index_date 시점 상태"},
        "denominator_definition": "구매 이력 보유 고객 수",
        "formula": "|{c : days_since_last_purchase(c,D) ≥ no_purchase_days}| / |P_buyer(D)|",
        "definition_ref": "kpi-definition-v1.md §4",
        "source_events": ["purchase"],
    },
    "retention_rate": {
        "layer": "customer_kpi", "population": "P_buyer",
        "window": {"direction": "point_in_time", "label": "index_date 시점 상태"},
        "denominator_definition": "구매 이력 보유 고객 수 (churn_rate 와 동일 모집단)",
        "formula": "1 − churn_rate",
        "definition_ref": "kpi-definition-v1.md §4",
        "source_events": ["purchase"],
    },
    "cohort_retention_rate": {
        "layer": "customer_kpi", "population": "cohort",
        "window": {"direction": "prospective", "label": "M1/M3/M6/M12"},
        "denominator_definition": "가입월 코호트 인원",
        "formula": "코호트 m개월차 구매 ≥1건 고객 / 코호트 전체",
        "definition_ref": "kpi-definition-v1.md §4",
        "source_events": ["purchase"],
    },
    "repurchase_rate": {
        "layer": "customer_kpi", "population": "orders",
        "window": {"direction": "retrospective", "days": kpi.DEFAULT_LOOKBACK_DAYS},
        "denominator_definition": "기간 내 1회 이상 구매 고객 수",
        "formula": "|{c : purchase_count(c,[D−L,D]) ≥ 2}| / |{c : purchase_count(c,[D−L,D]) ≥ 1}|",
        "definition_ref": "kpi-definition-v1.md §4",
        "source_events": ["purchase"],
    },
    "winback_rate": {
        "layer": "customer_kpi", "population": "P_buyer",
        "window": {"direction": "retrospective", "days": kpi.DEFAULT_LOOKBACK_DAYS,
                   "label": "(D−L, D]"},
        "denominator_definition": "D−L 시점 이탈 고객 수",
        "formula": "|{c : state(c,D−L)=churn ∧ purchase ∈ (D−L,D]}| / |{c : state(c,D−L)=churn}|",
        "definition_ref": "kpi-definition-v1.md §4",
        "source_events": ["purchase"],
    },
    "purchase_frequency": {
        "layer": "customer_kpi", "population": "P_buyer",
        "window": {"direction": "retrospective", "days": kpi.DEFAULT_LOOKBACK_DAYS},
        "denominator_definition": "구매 고객 수 (주문 건수가 아니다)",
        "formula": "Σ purchase 건수 / |P_buyer(D)|",
        "definition_ref": "kpi-definition-v1.md §4",
        "source_events": ["purchase"],
    },
    "purchase_interval": {
        "layer": "customer_kpi", "population": "P_buyer",
        "window": {"direction": "retrospective", "days": kpi.DEFAULT_LOOKBACK_DAYS},
        "denominator_definition": "구매 간격이 정의되는 고객 수 (제외 인원 병기)",
        "formula": "median(고객별 median(연속 purchase 간 일수))",
        "definition_ref": "kpi-definition-v1.md §4",
        "source_events": ["purchase"],
    },
    "average_order_value": {
        "layer": "customer_kpi", "population": "orders",
        "window": {"direction": "retrospective", "days": kpi.DEFAULT_LOOKBACK_DAYS},
        "denominator_definition": "주문 건수 (★ 고객 수가 아니다)",
        "formula": "Σ order_amount / count(purchase)",
        "definition_ref": "kpi-definition-v1.md §4",
        "source_events": ["purchase"],
    },
    "churn_label": {
        "layer": "customer_kpi", "population": "P_buyer",
        "window": {"direction": "prospective", "days": kpi.LABEL_WINDOW_DAYS,
                   "label": "(T0, T0+42]"},
        "denominator_definition": "라벨 대상 고객 수",
        "formula": "churn_label_i = 1 if count(purchase | T0 < t ≤ T0+42) == 0",
        "definition_ref": "kpi-definition-v1.md §6.2",
        "source_events": ["purchase"],
    },
    "coupon_usage_count": {
        "layer": "business_kpi", "population": "events",
        "window": {"direction": "retrospective", "days": kpi.DEFAULT_LOOKBACK_DAYS},
        "denominator_definition": "분모 없음 (합계)",
        "formula": "count(coupon_use)",
        "definition_ref": "kpi-definition-v1.md §5",
        "source_events": ["coupon_use"],
    },
    "coupon_exposure_count": {
        "layer": "business_kpi", "population": "events",
        "window": {"direction": "retrospective", "days": kpi.DEFAULT_LOOKBACK_DAYS},
        "denominator_definition": "분모 없음 (합계)",
        "formula": "count(coupon_exposed)",
        "definition_ref": "kpi-definition-v1.md §5",
        "source_events": ["coupon_exposed"],
    },
    "campaign_response_count": {
        "layer": "business_kpi", "population": "events",
        "window": {"direction": "retrospective", "days": kpi.DEFAULT_LOOKBACK_DAYS},
        "denominator_definition": "분모 없음 (합계)",
        "formula": "count(coupon_clicked)",
        "definition_ref": "kpi-definition-v1.md §4.2",
        "source_events": ["campaign_exposed", "coupon_clicked", "purchase"],
    },
    "revenue": {
        "layer": "business_kpi", "population": "orders",
        "window": {"direction": "none"},
        "denominator_definition": "분모 없음 (합계)",
        "formula": "Σ order_amount",
        "definition_ref": "kpi-definition-v1.md §5",
        "source_events": ["purchase"],
    },
    "cogs": {
        "layer": "business_kpi", "population": "orders",
        "window": {"direction": "none"},
        "denominator_definition": "분모 없음 (합계)",
        "formula": "Σ (unit_cost × quantity)",
        "definition_ref": "economic-rule-v1.md §3.2 EC-1",
        "source_events": ["purchase"],
    },
    "message_cost": {
        "layer": "business_kpi", "population": "events",
        "window": {"direction": "none"},
        "denominator_definition": "분모 없음 (합계)",
        "formula": "발송 건수 × message_cost_krw",
        "definition_ref": "economic-rule-v1.md §4",
        "source_events": ["push_sent"],
    },
    "coupon_cost": {
        "layer": "business_kpi", "population": "orders",
        "window": {"direction": "none"},
        "denominator_definition": "분모 없음 (합계)",
        "formula": (
            "coupon_use 있는 주문마다: 교환 파일 discount, 없으면 "
            "Σ treatment_cost[t] for t in (처치 ∩ coupon_treatments), "
            "둘 다 없으면 계산 불가"
        ),
        "definition_ref": "economic-rule-v1.md §6 D-16",
        "source_events": ["coupon_use"],
    },
    "campaign_fixed_cost": {
        "layer": "business_kpi", "population": "not_applicable",
        "window": {"direction": "none"},
        "denominator_definition": "분모 없음 (합계)",
        "formula": "campaign_fixed_cost_krw × 캠페인 수",
        "definition_ref": "economic-rule-v1.md §4",
        "source_events": [],
    },
    "shipping_subsidy": {
        "layer": "business_kpi", "population": "orders",
        "window": {"direction": "none"},
        "denominator_definition": "분모 없음 (합계)",
        "formula": "order_amount < 무료배송 기준 ∧ T1 → shipping_fee_krw",
        "definition_ref": "economic-rule-v1.md §6 D-3",
        "source_events": ["purchase"],
    },
    "marketing_cost": {
        "layer": "business_kpi", "population": "not_applicable",
        "window": {"direction": "none"},
        "denominator_definition": "분모 없음 (합계)",
        "formula": "message_cost + coupon_cost + campaign_fixed_cost",
        "definition_ref": "economic-rule-v1.md §5",
        "source_events": ["push_sent", "coupon_use"],
    },
    "contribution_profit": {
        "layer": "business_kpi", "population": "orders",
        "window": {"direction": "none"},
        "denominator_definition": "분모 없음 (합계)",
        "formula": (
            "revenue − cogs − coupon_cost − shipping_subsidy − message_cost "
            "− campaign_fixed_cost"
        ),
        "definition_ref": "economic-rule-v1.md §3",
        "source_events": ["purchase", "push_sent", "coupon_use"],
    },
    "n_targeted": {
        "layer": "business_kpi", "population": "events",
        "window": {"direction": "none"},
        "denominator_definition": "분모 없음 (합계)",
        "formula": "push_sent 가 발생한 고유 고객 수",
        "definition_ref": "economic-rule-v1.md §4 EC-4",
        "source_events": ["push_sent"],
    },
}

#: 파생 상태 3종의 공통 메타. 이름만 다르므로 따로 적지 않는다.
_DERIVED_META: dict[str, object] = {
    "layer": "customer_kpi", "population": "P_buyer",
    "window": {"direction": "point_in_time", "label": "index_date 시점 상태"},
    "denominator_definition": "분모 없음 (합계)",
    "definition_ref": "kpi-definition-v1.md §6.1 · 리드 판정 G-8",
    "source_events": ["purchase"],
}


#: ★ R-3a — `kpi-definition-v1.md` §7 이 확정한 판정 역할.
#:
#: **결정 D-4 는 "역할 배정을 GATE 2 에서 Lock 한다"이지 "C1 에서 게시하지
#: 않는다"가 아니다.** §7 에 배정안이 있고 W2 픽스처가 role 을 담고 있으며 화면
#: 규칙 U-7 이 `[P1]` 배지를 요구한다. 1차 구현이 24종 전부 `none` 으로 내보내
#: Andrew 가 *"배지를 그릴 수 없다"* 로 잡았다.
#:
#: **Lock 되지 않았다는 사실은 `freeze_status` 의 `KPI_DEFINITION_v1.scope_note`
#: 가 말한다** — 배정을 싣는 것과 봉인하는 것은 다른 행위다.
_METRIC_ROLES: Mapping[str, str] = {
    # Primary — 실험 판정의 최종 근거. 95% CI 하한까지 요구한다
    "incremental_contribution_profit": "primary",   # P1
    "qini_coefficient": "primary",                  # P2
    # Guardrail — 위반 시 진행 불가·차단
    "churn_test_auc": "guardrail",                  # ≥ 0.78 (ML-004)
    "marketing_cost": "guardrail",                  # ≤ C_rule
    "sleeping_dog_targeting_rate": "guardrail",     # Random 대비 유의하게 낮음
    "revenue_up_profit_down": "guardrail",          # PRD §65 해석 규칙
    # Secondary — Primary 가 왜 움직였는지 설명한다. 단독으로 실험을 중단시키지
    # 않고 Primary 판정을 뒤집지 않는다 (R-13)
    "incremental_revenue": "secondary",
    "roi": "secondary",
    "ai_roi": "secondary",
    "retention_rate": "secondary",
    "repurchase_rate": "secondary",
}

#: ★ R-3b — `blocks` = 이 지표가 계산되지 않을 때 **함께 무너지는 하위 지표**.
#:
#: `metrics[].value.blocked_by` 의 **역방향**이고 `field_coverage_report`
#: `fields[f].blocks_metrics` 와 같은 방향이다. 화면이 결손→영향 사슬을 추론하지
#: 않게 게시 시점에 넣는다 (`DB-012`). W2 픽스처는 13/13 전부 담았고 1차 구현은
#: 0건이었다 — Andrew 가 잡았다.
_METRIC_BLOCKS: Mapping[str, tuple[str, ...]] = {
    "revenue": ("contribution_profit", "incremental_revenue", "roi",
                "average_order_value"),
    "cogs": ("contribution_profit", "incremental_contribution_profit"),
    "coupon_cost": ("contribution_profit", "marketing_cost"),
    "shipping_subsidy": ("contribution_profit",),
    "message_cost": ("marketing_cost", "realized_cost_per_customer"),
    "campaign_fixed_cost": ("marketing_cost",),
    "marketing_cost": ("roi", "ai_roi", "realized_cost_per_customer"),
    "contribution_profit": ("incremental_contribution_profit", "roi", "ai_roi"),
    "n_targeted": ("realized_cost_per_customer", "campaign_fixed_cost"),
    "churn_rate": ("retention_rate",),
    "incremental_contribution_profit": ("ai_net_incremental_value",),
}

#: ★ R-3c — 실험 판정 계층을 `metrics[]` 에 **싣는다.**
#:
#: 1차 구현은 `METRIC_SPECS` 분류표에만 두고 `metrics[]` 에서 빼놨다. 그러면
#: 화면이 `layer: "experiment"` 행을 하나도 못 받아 **U-7(`[P1]` 배지)을 실제
#: 게시물로 검증할 수 없다.** W2 픽스처는 experiment 2건을 담았다.
#:
#: **빼는 것이 "계산 불가"를 숨기는 것과 같다** — 목록에 없으면 "계산 못 했다"가
#: 아니라 "그런 지표가 없다"로 읽힌다.
_EXPERIMENT_METRICS: tuple[tuple[str, str, str], ...] = (
    ("incremental_contribution_profit", "NEEDS_TWO_STRATEGIES",
     "CP_strategy − CP_S1_rule. 95% CI 하한 > 0 이어야 한다"),
    ("qini_coefficient", "NEEDS_MODEL_OUTPUT",
     "Qini 곡선의 계수. Random 정책(Qini=0) 대비 유의해야 한다"),
    ("incremental_revenue", "NEEDS_TWO_STRATEGIES",
     "revenue_strategy − revenue_S1_rule"),
    ("roi", "NEEDS_TWO_STRATEGIES",
     "(incremental_contribution_profit − marketing_cost) / marketing_cost"),
    ("ai_roi", "NEEDS_TWO_STRATEGIES",
     "(incremental_profit − ai_investment_cost) / ai_investment_cost"),
    ("ai_net_incremental_value", "NEEDS_TWO_STRATEGIES",
     "incremental_contribution_profit − ai_investment_cost"),
    ("churn_test_auc", "NEEDS_MODEL_OUTPUT", "Test 홀드아웃의 ROC AUC. ≥ 0.78"),
    ("sleeping_dog_targeting_rate", "NEEDS_MODEL_OUTPUT",
     "역효과 고객(Sleeping Dog) 중 처치를 받은 비율"),
    ("auuc", "NEEDS_MODEL_OUTPUT", "Area Under Uplift Curve"),
    ("uplift_by_decile", "NEEDS_MODEL_OUTPUT", "Uplift 십분위 분포"),
    ("persuadables_ratio", "NEEDS_MODEL_OUTPUT", "Persuadables 4분면 비율"),
    ("predicted_clv", "NEEDS_MODEL_OUTPUT", "예측 CLV"),
    ("clv_mape", "NEEDS_MODEL_OUTPUT", "CLV 예측의 MAPE"),
    ("top20_precision", "NEEDS_MODEL_OUTPUT", "상위 20% 정밀도"),
)


def build_kpi_report(
    events: Sequence[Mapping[str, object]],
    split: SourceSplit,
    *,
    index_date: date,
    config: CostAccountingConfig,
    exchange: ex.CommerceExchange | None = None,
) -> dict[str, object]:
    """V4 — 지표 가용성.

    ★ **계층 1·2 에 `combined` 가 없다** (R-7). 계약 스키마가 그 키를 거부한다 —
    두 출처를 합산한 값을 기본 표시로 쓰면 커머스 0건이 시뮬레이터 값에 섞여
    출처별 실태가 사라진다.
    """
    computations = {
        "churn_rate": lambda e: kpi.churn_rate(e, index_date=index_date),
        "retention_rate": lambda e: kpi.retention_rate(e, index_date=index_date),
        "cohort_retention_rate": lambda e: kpi.cohort_retention_rate(
            e, index_date=index_date, month=1),
        "repurchase_rate": lambda e: kpi.repurchase_rate(e, index_date=index_date),
        "winback_rate": lambda e: kpi.winback_rate(e, index_date=index_date),
        "purchase_frequency": lambda e: kpi.purchase_frequency(
            e, index_date=index_date),
        "purchase_interval": lambda e: kpi.purchase_interval(
            e, index_date=index_date),
        "average_order_value": lambda e: kpi.average_order_value(
            e, index_date=index_date),
        "churn_label": lambda e: kpi.churn_label(e, index_date=index_date),
        "coupon_usage_count": lambda e: kpi.coupon_usage_count(
            e, index_date=index_date),
        "coupon_exposure_count": lambda e: kpi.coupon_exposure_count(
            e, index_date=index_date),
        "campaign_response_count": lambda e: kpi.campaign_response_count(
            e, index_date=index_date),
        "revenue": lambda e: ec.revenue(assemble_orders(e, exchange)),
        "cogs": lambda e: _sum_cogs(assemble_orders(e, exchange)),
        "message_cost": lambda e: ec.message_cost(
            assemble_campaign(e, exchange), config=config),
        "coupon_cost": lambda e: ec.coupon_cost(
            assemble_campaign(e, exchange), config=config),
        "campaign_fixed_cost": lambda e: ec.campaign_fixed_cost(
            assemble_campaign(e, exchange), config=config),
        "shipping_subsidy": lambda e: ec.shipping_subsidy(
            assemble_orders(e, exchange), config=config),
        "marketing_cost": lambda e: ec.marketing_cost(
            assemble_campaign(e, exchange), config=config),
        "contribution_profit": lambda e: ec.contribution_profit(
            assemble_orders(e, exchange), assemble_campaign(e, exchange),
            config=config),
        "n_targeted": lambda e: ec.n_targeted(assemble_campaign(e, exchange)),
    }

    metrics: list[dict[str, object]] = []
    for name, compute in computations.items():
        meta = _KPI_META[name]
        metrics.append({
            "name": name,
            "layer": meta["layer"],
            # ★ §7 이 배정한 역할을 싣는다. 배정이 없으면 none 이다 — 임의로
            #   붙이지 않는다. Lock 은 GATE 2 이고 그 사실은 freeze_status 가 말한다.
            "role": _METRIC_ROLES.get(name, "none"),
            **({"blocks": list(_METRIC_BLOCKS[name])} if name in _METRIC_BLOCKS else {}),
            "population": meta["population"],
            "window": dict(meta["window"]),  # type: ignore[arg-type]
            "denominator_definition": meta["denominator_definition"],
            "formula": meta["formula"],
            "definition_ref": meta["definition_ref"],
            "source_events": list(meta["source_events"]),  # type: ignore[arg-type]
            "value": _split(split, compute),
        })

    for state in (item.value for item in sc.DerivedStateType):
        metrics.append({
            "name": f"derived_state_count[{state}]",
            "layer": _DERIVED_META["layer"],
            "role": "none",  # 표시 전용 지표다. 실험 판정에 쓰지 않는다
            "population": _DERIVED_META["population"],
            "window": dict(_DERIVED_META["window"]),  # type: ignore[arg-type]
            "denominator_definition": _DERIVED_META["denominator_definition"],
            "definition_ref": _DERIVED_META["definition_ref"],
            "source_events": list(_DERIVED_META["source_events"]),  # type: ignore[arg-type]
            "value": {
                "by_source": {
                    name: _metric(
                        kpi.derived_state_count(list(e), index_date=index_date)[state]
                    )
                    for name, e in split.items()
                }
            },
        })

    # ★ R-3c — 실험 판정 계층. C1 에서 전부 계산 불가이고, **그래서 싣는다.**
    #   목록에 없으면 "계산 못 했다"가 "그런 지표가 없다"로 읽힌다.
    for name, reason, formula in _EXPERIMENT_METRICS:
        uncomputable = sc.MetricValue.unavailable(
            sc.ReasonCode(reason),
            "C1 에 비교 전략이 없다 — 두 전략의 차이가 정의되지 않는다"
            if reason == "NEEDS_TWO_STRATEGIES"
            else "C1 에 모델 산출물이 없다 — ML/DL 은 이 사이클의 범위 밖이다",
            unit=sc.Unit.RATIO if "rate" in name or "qini" in name or "auuc" in name
            else sc.Unit.KRW if "profit" in name or "revenue" in name or "value" in name
            else sc.Unit.RATIO,
            blocked_by=(
                sc.BlockerRef(
                    sc.BlockerKind.STRATEGY if reason == "NEEDS_TWO_STRATEGIES"
                    else sc.BlockerKind.MODEL_OUTPUT,
                    "S1_rule_based" if reason == "NEEDS_TWO_STRATEGIES"
                    else "churn_model",
                    sc.ReasonCode(reason),
                ),
            ),
        )
        metrics.append({
            "name": name,
            "layer": "experiment",
            "role": _METRIC_ROLES.get(name, "none"),
            **({"blocks": list(_METRIC_BLOCKS[name])} if name in _METRIC_BLOCKS else {}),
            "population": "test_holdout",
            "window": {"direction": "prospective", "days": kpi.LABEL_WINDOW_DAYS},
            "denominator_definition": (
                "Test 20% 최종 홀드아웃 (P1) 또는 모델 산출 대상"
            ),
            "formula": formula,
            "definition_ref": "kpi-definition-v1.md §7",
            "source_events": [],
            # ★★ 실험 판정은 **출처를 나누지 않는다.** 계약 `allOf[1]` 이
            #   `layer == "experiment"` 에 대해 `value` 를 평범한 `metric_value` 로
            #   못박는다 — `by_source` 를 담으면 거부된다.
            #
            #   근거는 MEA-002 다: **실험 결과 산출에는 시뮬레이터 생성분만 쓴다.**
            #   양쪽에 같은 계산 불가를 실으면 *"커머스에도 실험 판정이 있을 수
            #   있다"* 는 뜻이 되고, 그것이 MEA-002 가 막는 것이다.
            #
            #   1차 구현이 "계약이 두 키를 요구한다"고 잘못 읽고 by_source 를
            #   담았다 — 계약을 확인하지 않고 다른 계층의 모양을 복사했다.
            "value": _metric(uncomputable),
        })

    # summary 는 **게시된 metric_value 를 하나씩** 센다. 계층별로 value 의 모양이
    # 다르므로(계층 1·2 는 by_source 2개, 실험은 1개) 모양을 보고 순회한다 —
    # by_source 를 전제하면 실험 계층에서 KeyError 다.
    def _statuses(entry: Mapping[str, object]) -> list[str]:
        value = entry["value"]
        if isinstance(value, Mapping) and "by_source" in value:
            return [
                payload["status"]
                for payload in value["by_source"].values()  # type: ignore[union-attr]
            ]
        return [value["status"]]  # type: ignore[index]

    statuses: Counter[str] = Counter(
        status for entry in metrics for status in _statuses(entry)
    )
    return {
        "index_date": index_date.isoformat(),
        "definition_version": "kpi-definition-v1.0-draft",
        "summary": {
            "total": sum(statuses.values()),
            "ok": statuses.get("ok", 0),
            "unconfirmed": statuses.get("unconfirmed", 0),
            "unavailable": statuses.get("unavailable", 0),
            "blocked": statuses.get("blocked", 0),
            "not_run": statuses.get("not_run", 0),
        },
        "metrics": metrics,
    }


def _sum_cogs(orders: Sequence[ec.OrderView]) -> sc.MetricValue:
    """주문별 `cogs` 의 합. 하나라도 계산 불가면 합계도 계산 불가다."""
    if not orders:
        return sc.MetricValue.unavailable(
            sc.ReasonCode.NO_SOURCE_EVENT,
            "purchase 이벤트가 0건이라 매출원가를 계산할 대상이 없다",
            unit=sc.Unit.KRW,
            blocked_by=(
                sc.BlockerRef(
                    sc.BlockerKind.EVENT_TYPE, "purchase",
                    sc.ReasonCode.NO_SOURCE_EVENT,
                ),
            ),
        )
    parts = [ec.cogs(order) for order in orders]
    failed = [p for p in parts if p.status is not sc.MetricStatus.OK]
    if failed:
        return sc.MetricValue.unavailable(
            sc.ReasonCode.NO_COST_BASIS,
            f"주문 {len(parts)}건 중 {len(failed)}건의 매출원가를 계산할 수 없다 — "
            f"{failed[0].reason_detail}",
            unit=sc.Unit.KRW,
            blocked_by=failed[0].blocked_by,
        )
    return sc.MetricValue.ok(
        sum(float(p.value) for p in parts),  # type: ignore[arg-type]
        unit=sc.Unit.KRW,
        basis=sc.Basis(
            population="purchase 이벤트로 관측된 주문의 품목",
            denominator_definition="분모 없음 (합계)",
            window=sc.Window(sc.WindowDirection.NONE),
            observed_count=len(parts),
            source_event_types=("purchase",),
        ),
    )


def build_freeze_status() -> dict[str, object]:
    """V6 — 봉인 상태. ★ **`freeze.verify()` 를 부른다. 자기 판정을 하지 않는다.**

    탐지 3층(테스트 · 게시 · 화면)이 같은 함수를 쓴다는 것이 `AC-4` 이고, 이
    함수는 그 판정을 게시 형식으로 옮기는 일만 한다. `publish.py` 가 자기 사본의
    선행 조건 표를 들면 `tests/test_freeze.py` 와 판정이 갈린다.
    """
    verification = fz.verify(
        preconditions=fz.GATE1_PRECONDITIONS,
        items=fz.gate1_lock_items(),
        lock_record=fz.load_record() if fz.DEFAULT_LOCK_RECORD.exists() else None,
    )
    return fz.to_artifact(verification)


# ── 인덱스 · 판정 ───────────────────────────────────────────────────────────

def build_index(
    *,
    artifacts: Sequence[Mapping[str, object]],
    quality: Mapping[str, object],
    kpi_report: Mapping[str, object],
    ingestion: Mapping[str, object],
    freeze: Mapping[str, object],
    publish_result: str,
) -> dict[str, object]:
    """★ `verdict` 를 **게시물이 집계한다.** 화면이 세지 않는다 (DB-012).

    단순 합산도 계산이고, 집계 규칙이 두 곳에 있으면 화면과 리포트가 다른 숫자를
    낸다.
    """
    checks = quality.get("checks") or []
    summary = kpi_report.get("summary") or {}
    counts = {
        "quality_violations": sum(
            1 for c in checks if c.get("status") == "fail"),
        "checks_not_run": sum(
            1 for c in checks if c.get("status") in ("not_run", "vacuous")),
        "checks_blocked": sum(
            1 for c in checks if c.get("status") == "blocked"),
        "metrics_unavailable": int(summary.get("unavailable", 0)),
        "metrics_not_run": int(summary.get("not_run", 0)),
        "schema_gaps": 0,  # field_coverage_report 가 채운다 — 아래에서 덮어쓴다
        # ★ 이름이 세는 것과 다르다. `unlocked_items` 는 LOCK_ITEMS 의 PENDING/PARTIAL
        #   이 아니라 **G-1~G-16 선행조건 중 미충족** 목록이다(`freeze.py` 가 그렇게
        #   만들고 주석으로 명시한다). 이름을 고치는 것은 게시 계약 변경이라
        #   별도로 다루고(이슈 #60), 여기서는 계약의 description 에 무엇을 세는지
        #   적어 두었다 — 이 이름을 그대로 읽어 조건문을 잘못 쓴 것이 M4 의 겹2 다.
        "lock_items_pending": len(freeze.get("unlocked_items") or []),
        # 봉인 정본 파일이 봉인 이후 바뀐 건수. `verification == "mismatch"` 일 때만
        # 0 이 아니다 — 대조하지 않았거나(`not_run`) 기록이 없으면(`missing`) 0 이며,
        # 그 구분은 `freeze_status.verification` 이 따로 들고 있다.
        "freeze_mismatch": len(freeze.get("mismatches") or []),
        "rejected_events": _int_metric(
            (ingestion.get("totals") or {}).get("events_rejected")
        ),
    }
    headline = choose_headline_code(
        counts,
        events_ingested=(
            ((ingestion.get("totals") or {}).get("events_ingested") or {})
            .get("combined")
        ),
    )
    return {
        "publish_result": publish_result,
        "artifacts": list(artifacts),
        "views": {
            key: {"title": title, "artifact": artifact, "route": route}
            for key, (title, artifact, route) in VIEW_BINDINGS.items()
        },
        # ★ 게시물 없이 정적으로 그리는 화면. 적지 않으면 "계약에 없는 화면"과
        #   "의도적으로 정적인 화면"을 구분할 수 없다.
        "static_views": [
            {
                "route": "/triggers", "title": "트리거",
                "reason_code": sc.ReasonCode.PRECONDITION_MISSING.value,
                "reason_detail": (
                    "PRD §71 트리거 5종은 변화를 조건으로 하는데 게시물 이력이 "
                    "없어 비교 기준이 없다 — C1 작동 0종"
                ),
            }
        ],
        "verdict": {
            "level": headline_level(headline),
            "headline_code": headline,
            "headline_detail": _headline_detail(headline, counts),
            "counts": counts,
        },
    }


def _int_metric(payload: object) -> int:
    """`metric_value` 에서 정수를 꺼낸다. **계산 불가면 0 으로 읽지 않는다.**

    `counts` 는 정수 필드라 `null` 을 담을 수 없다. 그래서 계산 불가일 때 `0` 을
    쓰는데, **그 `0` 이 "거부가 없었다"로 읽히면 안 된다** — `choose_headline_code`
    가 `events_ingested.status` 를 따로 보는 이유가 이것이다.
    """
    if not isinstance(payload, Mapping):
        return 0
    value = payload.get("value")
    return int(value) if isinstance(value, (int, float)) else 0


def _headline_detail(code: str, counts: Mapping[str, int]) -> str:
    details = {
        "CONTRACT_VIOLATION": "게시물이 자기 계약을 어겼다 — 게시를 중단했다",
        "FREEZE_MISMATCH": "봉인된 대상이 봉인 이후 변경됐다",
        "QUALITY_VIOLATION": (
            f"데이터 품질 검사 {counts.get('quality_violations', 0)}건이 실패했다"
        ),
        "REJECTED_EVENTS": (
            f"수집 과정에서 {counts.get('rejected_events', 0)}건이 거부됐다"
        ),
        "SINK_EMPTY": (
            "수집된 이벤트가 0건이다 — 활동 없음과 수집 중단을 현재 데이터로 "
            "구분할 수 없다"
        ),
        "CHECKS_NOT_RUN": (
            f"품질 검사 {counts.get('checks_not_run', 0)}건이 미실행이고 "
            f"{counts.get('checks_blocked', 0)}건이 차단됐다"
        ),
        "METRICS_UNAVAILABLE": (
            f"지표 {counts.get('metrics_unavailable', 0)}건이 계산 불가이고 "
            f"{counts.get('metrics_not_run', 0)}건이 미실행이다"
        ),
        "ALL_CLEAR": "모든 검사가 통과했고 미실행·계산 불가가 없다",
    }
    return details[code]


# ── 원자적 게시 ─────────────────────────────────────────────────────────────

@dataclass
class PublishOutcome:
    run_id: str
    output_root: Path
    publish_result: str
    artifacts: list[dict[str, object]] = field(default_factory=list)

    @property
    def exit_code(self) -> int:
        """`partial` 도 **0** 이다 — 게시 자체는 성공했고 그 사실이 산출물에 담긴다."""
        return 0 if self.publish_result in ("ok", "partial") else 6


def publish(
    *,
    source_root: Path = DEFAULT_SOURCE_ROOT,
    output_root: Path = DEFAULT_OUTPUT_ROOT,
    config_path: Path = DEFAULT_ECONOMIC_CONFIG,
    exchange_root: Path | None = None,
    index_date: date | None = None,
    now: datetime | None = None,
) -> PublishOutcome:
    """`results/` 에 6종 + 인덱스를 **원자적으로** 쓴다.

    순서가 계약이다: staging 에 전부 쓰고 → 자기검증하고 → `os.replace` 로 옮기고
    → **`index.json` 을 마지막에** 쓴다. 검증이 실패하면 최종 경로에 아무것도
    남지 않는다.

    `exchange_root` 기본값은 `source_root` 의 형제 `commerce/` 다
    (`data/raw` → `data/commerce`). 없으면 교환 파일 없이 게시한다.
    """
    run_id = ct.new_run_id(now=now)
    # ★ cost_accounting 만 꺼낸다. product_generation(원가율)은 계산층으로
    #   넘기지 않는다 — 그것이 EC-9 의 타입 봉쇄이고, 여기서 전체 객체를 넘기면
    #   봉쇄가 무의미해진다.
    config = load_economic_config(config_path).cost_accounting

    manifest = _read_manifest(source_root)
    events = list(read_events(source_root)) if (source_root / "events").exists() else []
    rejected = _read_rejected(source_root)
    exchange = ex.read_exchange(exchange_root or ex.default_root(source_root))
    split = partition_by_source(events)
    partition_dates = _partition_dates(source_root)
    effective_index_date = index_date or _latest_date(partition_dates, now=now)

    # ★ 계보를 provenance 앞에서 구한다 — 아래 provenance 가 이 값을 쓴다.
    lineage = verify_lineage(source_root)

    provenance = ct.build_provenance(
        source_root=source_root,
        config_paths=[config_path],
        sink_manifest_sha256=manifest.get("sha256") if manifest else None,
    )
    provenance["lineage"] = {
        # ★ `status` 가 아니라 `verification` 이다 — `status` 로 두면 계약이
        #   이 객체를 지표로 보고 value_formatted·reason_code 를 요구한다.
        #   freeze_status.json 이 같은 이유로 같은 이름을 쓴다.
        "verification": lineage.verification,
        "detail": lineage.detail,
        "runs": lineage.runs,
        "head_run_id": latest_run_id(source_root),
    }
    notices = _notices(config)
    # ★ 계보를 게시물에 싣는다 (이슈 #99 ③). `runs/` 를 만들어 두고 산출물이
    #   말하지 않으면 아무도 보지 않고, 그러면 계보는 대조되지 않는 선언이 된다.
    if lineage.verification == "broken":
        notices.append(ct.Notice(
            "LINEAGE_BROKEN", "warning",
            f"실행 기록과 디스크가 어긋난다 — {lineage.detail}. 파티션이 밖에서 "
            "추가·삭제됐거나 실행 기록이 손상됐다. 이 데이터의 출처를 "
            "직전 실행까지 되짚을 수 없다",
            reference="issue #99",
        ))
    elif lineage.verification == "not_run":
        notices.append(ct.Notice(
            # ★ 통과가 아니다. 대조하지 않았다는 사실을 값으로 만든다.
            "LINEAGE_NOT_RUN", "assumption",
            f"{lineage.detail} — 이 데이터가 몇 번에 나눠 생성됐는지, 직전 "
            "실행이 무엇인지 알 수 없다",
            reference="issue #99",
        ))

    quality = dq.build_report(events, exchange=exchange)
    ingestion = build_ingestion_report(manifest, split, partition_dates)
    bodies: dict[str, dict[str, object]] = {
        "ingestion_report": ingestion,
        "rejection_report": build_rejection_report(manifest, rejected),
        "field_coverage_report": build_field_coverage_report(events, split),
        "kpi_report": build_kpi_report(
            events, split, index_date=effective_index_date, config=config,
            exchange=exchange,
        ),
        "data_quality_report": quality,
        "freeze_status": build_freeze_status(),
    }

    staging = output_root.with_name(output_root.name + STAGING_SUFFIX)
    _reset(staging)
    artifacts: list[dict[str, object]] = []
    failures = 0
    for name, body in bodies.items():
        payload = {
            **ct.envelope(
                name, run_id=run_id, provenance=provenance, notices=notices, now=now
            ),
            **body,
        }
        path = staging / artifact_relative(name)
        path.parent.mkdir(parents=True, exist_ok=True)
        try:
            text = ct.dump(payload)  # ★ 검증을 통과하지 못하면 문자열을 안 만든다
        except ContractViolation as error:
            failures += 1
            artifacts.append({
                "artifact": name, "path": _contract_path(output_root, name),
                "status": "failed",
                "reason_code": sc.ReasonCode.BLOCKED.value,
                "reason_detail": f"계약 자기검증 실패: {error}",
            })
            continue
        path.write_text(text, encoding="utf-8")
        artifacts.append({
            "artifact": name, "path": _contract_path(output_root, name),
            "status": "published",
            "sha256": ct.file_sha256(path),
            "bytes": path.stat().st_size,
        })

    publish_result = "ok" if failures == 0 else "partial"
    index_payload = {
        **ct.envelope(
            "index", run_id=run_id, provenance=provenance, notices=notices, now=now
        ),
        **build_index(
            artifacts=artifacts, quality=quality,
            kpi_report=bodies["kpi_report"], ingestion=ingestion,
            freeze=bodies["freeze_status"], publish_result=publish_result,
        ),
    }
    # schema_gaps 는 field_coverage_report 가 아는 값이므로 여기서 채운다.
    index_payload["verdict"]["counts"]["schema_gaps"] = len(  # type: ignore[index]
        bodies["field_coverage_report"]["schema_gaps"]  # type: ignore[index]
    )
    index_text = ct.dump(index_payload)

    # ── 이동: 최종 경로를 비우고 staging 을 옮긴다 ──────────────────────────
    try:
        output_root.mkdir(parents=True, exist_ok=True)
        (output_root / MEASUREMENT_SUBDIR).mkdir(parents=True, exist_ok=True)
        for path in sorted(staging.rglob("*.json")):
            # ★ 승격 대상도 링크면 거부한다 (이슈 #65). rglob 은 링크를 따라가므로
            #   staging 안에 심어진 링크가 이 루프에 들어올 수 있고, 그대로 옮기면
            #   링크가 results/ 안에 놓인다 — 다음 읽기가 그 링크를 따라간다.
            if path.is_symlink():
                raise PublishError(
                    f"staging 안의 산출물이 심볼릭 링크다: {path} → "
                    f"{os.readlink(path)}. 게시를 중단한다 — 옮기면 링크가 "
                    "results/ 안에 놓이고 읽는 쪽이 그것을 따라간다."
                )
            target = output_root / path.relative_to(staging)
            if target.is_symlink():
                raise PublishError(
                    f"게시 대상이 심볼릭 링크다: {target} → {os.readlink(target)}. "
                    "게시를 중단한다 — os.replace 는 링크를 대체하지만, 링크가 "
                    "거기 있다는 것 자체가 results/ 가 손대졌다는 뜻이다."
                )
            target.parent.mkdir(parents=True, exist_ok=True)
            os.replace(path, target)
        # ★ index.json 을 마지막에. 대시보드의 진입점이므로 먼저 쓰면 아직 없는
        #   산출물을 가리키는 인덱스가 존재하는 순간이 생긴다.
        #   위치는 ADR-0002 에 따라 measurement/ 아래다.
        (output_root / artifact_relative("index")).write_text(
            index_text, encoding="utf-8"
        )
    except OSError as error:
        raise PublishError(
            f"게시물을 {output_root} 로 옮길 수 없다: {error}. staging 은 "
            f"{staging} 에 남아 있으니 원인을 확인하고 다시 실행한다."
        ) from error
    finally:
        shutil.rmtree(staging, ignore_errors=True)

    return PublishOutcome(
        run_id=run_id, output_root=output_root,
        publish_result=publish_result, artifacts=artifacts,
    )


def artifact_relative(name: str) -> Path:
    """산출물 이름 → **게시 루트 기준 상대 경로** (ADR-0002).

        ingestion_report      →  measurement/ingestion_report.json
        data_quality_report   →  data_quality_report.json          ← 예외
        index                 →  measurement/index.json

        >>> artifact_relative("kpi_report").as_posix()
        'measurement/kpi_report.json'
        >>> artifact_relative("data_quality_report").as_posix()
        'data_quality_report.json'
    """
    if name in ROOT_LEVEL_ARTIFACTS:
        return Path(f"{name}.json")
    return Path(MEASUREMENT_SUBDIR) / f"{name}.json"


def _contract_path(output_root: Path, name: str) -> str:
    """계약이 요구하는 `^(results|data/processed)/` 형태의 경로.

    `SRS DB-014` 가 게시물 위치를 그 둘로 제한하고 계약이 정규식으로 강제한다.
    `--out` 이 저장소 밖(테스트의 임시 디렉터리 등)이면 절대경로가 되어 어긋나므로,
    **계약에 적는 경로는 항상 저장소 기준 상대경로**로 만든다. 실제 쓰기 경로와
    분리하는 것이 의도다 — 테스트가 임시 경로를 쓴다는 사실이 계약에 새어 들어가지
    않는다.
    """
    try:
        relative = output_root.resolve().relative_to(Path.cwd().resolve())
    except ValueError:
        relative = Path(DEFAULT_OUTPUT_ROOT)
    prefix = relative.as_posix()
    if not prefix.startswith(("results", "data/processed")):
        prefix = DEFAULT_OUTPUT_ROOT.as_posix()
    return f"{prefix}/{artifact_relative(name).as_posix()}"


def _reset(path: Path) -> None:
    """Staging 을 비운다. ★ **심볼릭 링크면 지우지 않고 거부한다** (이슈 #65 · 보안 F3).

    이 경로는 `results.staging` 으로 **완전히 예측 가능**하다. 그래서 게시 전에
    미리 만들어 둘 수 있고, 이전 판은 그것을 통과시켰다:

      - `shutil.rmtree(..., ignore_errors=True)` 는 심볼릭 링크에서 **조용히
        아무것도 하지 않는다** (rmtree 는 링크를 거부하는데 오류가 삼켜진다)
      - `mkdir(exist_ok=True)` 는 링크가 가리키는 곳이 있으면 성공한다

    결과: 게시물이 공격자 디렉터리에 쓰이고, 승격 루프가 `staging.rglob("*.json")`
    으로 훑으므로 **공격자가 심어 둔 .json 이 `results/` 로 올라간다.** 재현했다.

    ★ 예측 가능한 이름을 그대로 둔 이유. 링크를 거부하면 남는 것은 "공격자가
      링크를 심어 게시를 막는" DoS 인데, 그 공격자는 `results/` 의 부모에 쓸 수
      있다는 뜻이고 **이미 `results/` 를 지우거나 덮어쓸 수 있다.** 새 능력이
      아니다. 반면 조용한 내용 바꿔치기는 새 능력이었다. 시끄럽게 거부하는 쪽이
      낫고, 이름을 무작위로 바꾸면 실패 시 남기는 staging 이 누적된다
      (오류 메시지가 "staging 은 … 에 남아 있으니" 로 그것을 전제한다).
    """
    if path.is_symlink():
        raise PublishError(
            f"staging 경로가 심볼릭 링크다: {path} → {os.readlink(path)}. "
            "게시를 중단한다 — 이 경로는 예측 가능하므로 미리 선점될 수 있고, "
            "그대로 진행하면 게시물이 링크가 가리키는 곳에 쓰이고 그곳의 .json 이 "
            f"{path.parent} 로 승격된다. 링크를 확인하고 지운 뒤 다시 실행한다."
        )
    shutil.rmtree(path, ignore_errors=True)
    path.mkdir(parents=True, exist_ok=True)
    if path.is_symlink():
        # mkdir 과 이 검사 사이에 심어진 경우. 창이 좁지만 0 은 아니다.
        raise PublishError(
            f"staging 경로가 생성 직후 심볼릭 링크가 됐다: {path}. 게시를 중단한다."
        )


def _read_manifest(source_root: Path) -> dict[str, object]:
    """Sink manifest. 없으면 **빈 상태를 정직하게** 만든다 — 0 으로 채우는 것과 다르다.

    manifest 가 없다는 것은 Sink 를 한 번도 돌리지 않았다는 뜻이고, 그 상태의
    수집 건수는 실제로 0 이다. `unavailable_metrics` 를 Observable 전체로 채우는
    것이 그 사실의 정확한 표현이다 (빈 Sink 에서 16개 전부 계산 불가).
    """
    path = source_root / MANIFEST_NAME
    if path.exists():
        try:
            parsed = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as error:
            # ★ 여기로 오는 것은 대개 쓰다 만 파일이다 (`sink.py` 의 manifest 쓰기가
            #   원자적이지 않다). 그대로 두면 처리되지 않은 예외로 죽는데, 죽는 것
            #   자체는 옳다 — 조용히 0 으로 읽는 것보다 낫다. 다만 **왜** 죽었는지는
            #   말해야 한다 (보안 감사 F6).
            raise ContractViolation(
                f"{path}: JSON 으로 읽을 수 없다 — {error}. 쓰다 만 파일일 가능성이 "
                "높다(manifest 쓰기는 원자적이지 않다). 파일이 존재하는데 읽지 못하는 "
                "것은 '파일이 없다' 와 다르므로 기본값으로 떨어지지 않는다."
            ) from error
        # ★ 입력에도 계약을 건다. 산출물 8종은 전부 검증받는데 **모든 지표가
        #   파생되는 유일한 입력만** 무검증이었다 (리뷰 M1 · 이슈 #59).
        ct.verify_manifest_invariants(parsed, where=str(path))
        return parsed
    return {
        "rows": 0, "rejected": 0, "event_type_counts": {}, "field_coverage": {},
        "missing_fields": [], "sources": {},
        "unavailable_metrics": sorted(sc.OBSERVABLE_METRIC_SOURCES),
        "sha256": None,
    }


def _read_rejected(source_root: Path) -> list[dict[str, object]]:
    path = source_root / REJECT_LOG_NAME
    if not path.exists():
        return []
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def _partition_dates(source_root: Path) -> list[date]:
    """파티션 디렉터리에서 날짜를 읽는다. 파일 개수만큼 반복해 담지 않는다."""
    events_root = source_root / "events"
    if not events_root.exists():
        return []
    found: list[date] = []
    for directory in sorted(events_root.iterdir()):
        if not directory.is_dir() or not directory.name.startswith("date="):
            continue
        try:
            found.append(date.fromisoformat(directory.name[len("date="):]))
        except ValueError:
            continue
    return found


def _latest_date(partition_dates: Sequence[date], *, now: datetime | None) -> date:
    """기준일. 파티션이 있으면 **마지막 파티션 날짜**를 쓴다.

    ★ `date.today()` 로 떨어지는 경로를 남기지만, 그때는 파티션이 하나도 없어
    모든 지표가 `NO_SOURCE_EVENT` 다 — 기준일이 결과를 바꾸지 않는다. 데이터가
    있으면 데이터가 기준일을 정한다 (R-1 의 정신).
    """
    if partition_dates:
        return max(partition_dates)
    return (now or datetime.now(ct.KST)).astimezone(ct.KST).date()


def _notices(config: CostAccountingConfig) -> list[ct.Notice]:
    """가정을 산출물에 붙여 나른다 (P-12). **문서는 아무도 다시 열지 않는다.**"""
    notices = [
        ct.Notice(
            "INGESTION_GAP_UNDECIDABLE", "limitation",
            "이벤트가 0건인 날짜가 수집 중단인지 활동 없음인지 현재 데이터로 "
            "구분할 수 없다 — heartbeat 레코드가 없다",
            reference="api-contracts.md §5.1.2 X-5",
        ),
        ct.Notice(
            "GATE1_NOT_PASSED", "info",
            "C1 은 GATE 1 을 통과시키지 않는다. 부분 봉인만 하며 전 항목이 "
            "pending 이다",
            reference="gate1-lock-scope.md §1",
        ),
        ct.Notice(
            "CHURN_THRESHOLDS_UNCONFIRMED", "assumption",
            "이탈 임계값 28/42/60 은 가설값이다 — data_spec §5.1 확정 절차가 "
            "시뮬레이터를 요구하고 C1 에 없다. 해당 지표는 unconfirmed 로 나간다",
            reference="kpi-definition-v1.md §1.1 D-5",
        ),
    ]
    if config.assumptions.get("refund_adjusted") is False:
        notices.append(ct.Notice(
            "REFUND_NOT_ADJUSTED", "assumption",
            # ★ 오차 **방향**을 문장에 담는다. "과대평가된다" 만 적으면 읽는
            #   사람이 얼마나·어느 쪽인지 모르고, 방향을 모르면 보정도 못 한다.
            #
            # ★★ 화면에서 **접히지 않아야 한다.** 가정은 시간이 지나면 사실로
            #   읽히고, 접힌 가정은 없는 가정이다 (P-12).
            "환불·취소를 차감하지 않는다 (확정 가정 A-REFUND · 결정 D-2). "
            "revenue = Σ order_amount 이므로 총매출을 순매출로 간주하며, "
            "환불된 매출을 뺄 수 없어 contribution_profit 이 **위로 치우친다 "
            "(과대평가)**. 아래로가 아니다. "
            "실험 판정에는 영향이 없다 — MEA-002 가 실험 결과 산출에 시뮬레이터 "
            "생성분만 쓰도록 규정하고 그쪽은 환불을 생성하지 않는다.",
            reference="economic-rule-v1.md §6.4 A-REFUND · 결정 D-2 (2026-09-11)",
        ))
    if config.ai_investment.is_estimate:
        notices.append(ct.Notice(
            "AI_INVESTMENT_IS_ESTIMATE", "assumption",
            f"AI 투자 비용이 가정 기반 추정치다 — {config.ai_investment.estimate_note}",
            reference="economic-rule-v1.md §5",
        ))
    return notices


# ── CLI ─────────────────────────────────────────────────────────────────────

def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python3 -m src.measurement.publish",
        description="측정 산출물을 results/ 에 게시한다 (측정 계층 6종 + 인덱스)",
    )
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE_ROOT,
                        help="Sink 루트 (기본 data/raw)")
    parser.add_argument("--out", type=Path, default=DEFAULT_OUTPUT_ROOT,
                        help="게시 대상 (기본 results)")
    parser.add_argument("--config", type=Path, default=DEFAULT_ECONOMIC_CONFIG,
                        help="경제 규칙 config (기본 config/economic_config.yaml)")
    parser.add_argument("--exchange", type=Path, default=None,
                        help="커머스 교환 파일 루트 (기본: --source 의 형제 commerce/)")
    parser.add_argument("--index-date", type=date.fromisoformat, default=None,
                        help="지표 기준일 D (기본: 마지막 파티션 날짜)")
    parser.add_argument("--fail-on-quality", action="store_true",
                        help="품질 게이트가 fail 이면 종료 코드 2 로 중단한다")
    args = parser.parse_args(argv)

    try:
        outcome = publish(
            source_root=args.source, output_root=args.out,
            config_path=args.config, exchange_root=args.exchange,
            index_date=args.index_date,
        )
    except MeasurementError as error:
        print(f"게시 실패: {error}", file=sys.stderr)
        return error.exit_code

    print(f"run_id           {outcome.run_id}")
    print(f"publish_result   {outcome.publish_result}")
    for artifact in outcome.artifacts:
        mark = "✅" if artifact["status"] == "published" else "❌"
        print(f"  {mark} {artifact['path']}  {artifact.get('bytes', 0)} bytes")

    index = json.loads(
        (outcome.output_root / artifact_relative("index")).read_text(encoding="utf-8")
    )
    verdict = index["verdict"]
    print(f"\nverdict          {verdict['level']} · {verdict['headline_code']}")
    print(f"                 {verdict['headline_detail']}")

    if args.fail_on_quality:
        quality = json.loads(
            (outcome.output_root / artifact_relative("data_quality_report"))
            .read_text(encoding="utf-8")
        )
        try:
            dq.raise_on_fail(quality)
        except QualityGateFailure as error:
            print(f"\n품질 게이트 중단: {error}", file=sys.stderr)
            return error.exit_code
    return outcome.exit_code


if __name__ == "__main__":
    raise SystemExit(main())
