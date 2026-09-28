"""데이터 품질 검증 — `data_spec` §9 의 18종 검사 (이슈 #48).

## 이 모듈이 푸는 문제 한 문단

`data_spec` §9 는 *"하나라도 실패하면 파이프라인은 **중단**한다(경고로 넘어가지
않는다)"* 고 규정한다. 그런데 **C1 에서는 검사의 절반이 실행 불가**다 — `orders`·
`customers`·`products` 테이블이 없고 시뮬레이터도 없다. 2값(`pass`/`fail`)으로
만들면 `fail` 은 파이프라인을 영원히 멈추고 `pass` 는 **미실행을 통과로** 만든다.

**`not_run` 은 데이터의 실패가 아니라 검사기의 한계다. 둘을 같은 값으로 적으면
책임 소재가 뒤바뀐다.** 그래서 `gate_result` 가 3값이다.

## ★★ `vacuous` — 이 모듈의 존재 이유

리드가 개정 전 픽스처를 세어 확인한 것:

    empty-sink  검사 18건 중 status="pass" ∧ examined_rows==0  →  7건 (39%)

**순진하게 구현하면 화면의 39% 가 초록 ✓ PASS 인데 아무것도 검사하지 않았다.**
`gate_result: incomplete` 라 게이트 층은 정직했다 — **거짓말한 것은 개별 검사 행**
이다. `scope` 가 산문으로 경고하지만 **산문은 색을 이기지 못한다.**

    examined_rows == 0  →  status 가 pass 일 수 없다
    status == vacuous   →  examined_rows == 0 ∧ violations 는 null ∧ 사유 필수
    gate_result == pass →  모든 검사가 pass (vacuous 하나만 있어도 pass 불가)

`vacuous` 는 **오늘 이 저장소의 정상 상태다** — 데이터가 0행이므로. 화면이 그것을
실패로 그려도, 통과로 그려도 안 된다.

## 항상 18종을 낸다 (Q-4 · CR-2)

실행하지 못한 검사도 **목록에 남는다.** 빼면 *"검사하지 않았다"* 가 보이지 않고
*"통과했다"* 와 구분되지 않는다. `commerce-connected` 픽스처는 7종만 담았는데
**그것은 그 스냅샷의 결함이고 정답이 아니다** — `make_examples_connected.py` 가
7종과 `reported_checks: 6` 을 소스에 하드코딩했다.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from typing import Iterable, Mapping, Sequence

from src.measurement import timeparse as tp
from src.measurement import schema as sc
from src.measurement.exchange import CommerceExchange
from src.measurement.errors import QualityGateFailure
from src.measurement.sink import KST, parquet_available

# ── 검사 상태 · 게이트 판정 ─────────────────────────────────────────────────

CHECK_STATUSES = ("pass", "fail", "vacuous", "not_run", "blocked")
"""계약 `data_quality_report.schema.json` 의 `checks[].status` 5종.

`vacuous` 가 이 목록에 있는 것이 `ADR-0010` 의 전부다."""

GATE_RESULTS = ("pass", "incomplete", "fail")


@dataclass(frozen=True, slots=True)
class CheckSpec:
    """검사 하나의 **정의**. 실행 결과가 아니다.

    `c1` 은 이 검사가 C1 에서 실행 가능한지이고, 실행 가능해도 대상이 0행이면
    결과는 `vacuous` 가 된다 — 정의와 결과는 다르다.
    """

    id: str
    spec_item: str
    title: str
    scope: str
    c1: str  # runnable · blocked · precondition_missing
    reason: str = ""


#: ★★ **18종의 유일한 정본.** `18` 을 리터럴로 적지 않는다 — 이 목록의 길이가
#: 정답이고, `reported_checks` 도 `len(checks)` 로 산출한다 (Q-3).
#:
#: ⚠ `data-quality-design.md` §3 **본문은 이 합을 17 로 적었다.** 같은 절의 표도
#: 픽스처도 18 이므로 **본문이 산술 오류다** (Q-1) — 18 로 구현한다.
#:
#: `spec_item` 은 `data_spec` §9 의 정본 항목명이다. 여러 검사가 한 항목을 나눠
#: 덮으므로(금액 정합성 = DQ-09 + DQ-10) 중복된다 — `spec_coverage()` 가 그것을
#: 집계한다.
DQ_ALL: tuple[CheckSpec, ...] = (
    CheckSpec(
        "DQ-01", "유일성", "event_id 전역 유일",
        "저장된 전 이벤트의 event_id", "runnable",
    ),
    CheckSpec(
        "DQ-02", "유일성", "order_id 전역 유일",
        "커머스 교환 파일 orders.jsonl 의 전 행. 중복이 있으면 로더가 묶음 전체를 "
        "거부하므로, 읽힌 묶음은 이 검사를 통과한 것이다 (#110)",
        "precondition_missing",
        "커머스 교환 파일(orders.jsonl)이 없어 주문 명부가 없다. events 만으로는 "
        "주문 명부를 알 수 없다 — DQ-02b 가 events 안의 범위 축소판을 본다",
    ),
    CheckSpec(
        # spec_item 은 data_spec §9 의 **정본 항목명**이므로 DQ-02 와 같다 —
        # DQ-02b 는 새 항목이 아니라 같은 항목의 범위 축소판이다. 범위 축소는
        # title·scope 가 말한다. 별도 항목으로 세면 spec_items 가 12 가 되어
        # 정본(11개)과 어긋난다.
        "DQ-02b", "유일성", "order_id 당 purchase 이벤트 정확히 1건 (범위 축소)",
        "purchase 이벤트의 order_id", "runnable",
    ),
    CheckSpec(
        "DQ-03", "참조 무결성", "고아 customer_id·product_id 0건",
        "커머스 출처 이벤트의 customer_id·product_id 와 교환 파일 명부"
        "(customers·catalog)의 대조. 명부 생성 시각(manifest.generated_at) 이후 "
        "이벤트는 대조하지 않는다. 시뮬레이터 이벤트는 대조할 명부가 없어 대상이 "
        "아니다 (#110)",
        "precondition_missing",
        "커머스 교환 파일(customers·catalog)이 없어 대조할 명부가 없다",
    ),
    CheckSpec(
        "DQ-04", "시간 정합성", "세션 내 이벤트 순서",
        "session_id 가 있는 이벤트의 세션별 timestamp 단조성", "runnable",
    ),
    CheckSpec(
        "DQ-05", "시간 정합성", "timestamp < signup_date 0건",
        "커머스 출처 이벤트 중 명부에 있는 고객의 이벤트 — KST 날짜가 가입일보다 "
        "앞서는가. 가입일이 날짜 단위라 가입 당일 가입 시각 이전의 이벤트는 잡지 "
        "못한다. 명부 생성 시각 이후 이벤트는 대조하지 않는다 (#110)",
        "precondition_missing",
        "커머스 교환 파일(customers.signup_date)이 없어 가입일을 모른다",
    ),
    CheckSpec(
        "DQ-06", "시간 정합성", "모든 시각이 KST 단일",
        "저장된 전 이벤트의 timestamp 오프셋", "runnable",
        # ★ M-01(#53 D1-3)이 타임존 정책을 확정해 BLOCKED 를 벗어난 검사다.
        #   정책: 오프셋이 붙은 어떤 표기든 받아 저장 시 KST 로 정규화한다.
        #   그래서 저장물의 timestamp 는 전부 +09:00 여야 하고, 이 검사가
        #   Sink 가 그 약속을 지켰는지 자기 저장물에 대해 확인한다.
    ),
    CheckSpec(
        "DQ-07", "퍼널 정합성", "purchase ← 선행 checkout_start",
        "purchase 이벤트와 같은 세션의 선행 checkout_start", "runnable",
    ),
    CheckSpec(
        "DQ-08", "퍼널 정합성", "coupon_use ← 선행 coupon_exposed",
        "coupon_use 이벤트와 같은 쿠폰의 선행 coupon_exposed", "runnable",
    ),
    CheckSpec(
        "DQ-09", "금액 정합성", "order_amount = Σ(unit_price×quantity) − discount",
        "커머스 교환 파일의 주문 — purchase 이벤트 금액과 품목 합계·할인의 대조",
        "precondition_missing",
        # 이벤트만으로는 두 겹으로 막힌다: discount 가 DATA-003 22컬럼에 없고,
        # purchase 는 주문 단위 1행이라 품목 합계를 재구성할 수 없다. 둘 다
        # 커머스 교환 파일(#100)이 싣는다. 교환 파일이 없으면 이 사유로 not_run 이다.
        # add_to_cart 로 근사하지 않는다: remove_from_cart 가 있고, 담았지만 사지
        # 않은 품목이 있고, 결제 실패가 있다.
        "discount 필드가 없고 purchase 가 주문 단위 1행이라 품목 합계를 "
        "재구성할 수 없다. order_items 가 있는 커머스 교환 파일(data/commerce/)이 "
        "있어야 성립한다",
    ),
    CheckSpec(
        "DQ-10", "금액 정합성", "음수 금액 0건",
        "quantity·unit_price·order_amount·session_duration 의 부호", "runnable",
    ),
    CheckSpec(
        "DQ-11", "완전성", "Key 결측 0%",
        "이벤트별 필수 필드(Core 4종 + 타입별 필수)의 결손", "runnable",
    ),
    CheckSpec(
        "DQ-12", "완전성", "Feature 결측률 항목별 5% 미만",
        "data/processed/ 의 Feature 테이블", "precondition_missing",
        "data/processed/ 가 미생성이고 Feature 생성은 decision 소관이다",
    ),
    CheckSpec(
        "DQ-13", "생성 이탈률", "15% ≤ 생성 이탈률 ≤ 25%",
        "시뮬레이터가 생성한 고객의 이탈 분포", "precondition_missing",
        "시뮬레이터가 미가동이라 생성 이탈률이 존재하지 않는다",
    ),
    CheckSpec(
        "DQ-14", "실험 균형", "|SMD| < 0.1",
        "처치군·대조군의 공변량 표준화 평균차", "precondition_missing",
        "실험 배정이 없다. 이슈 #48 이 이미 범위 C 로 이관했다",
    ),
    CheckSpec(
        "DQ-15", "처치 강도", "ATE 3~6%p · 쿠폰 사용률 25~40% · Sleeping Dog 8~15%",
        "처치 반응의 크기 분포", "precondition_missing",
        "시뮬레이터가 미가동이라 처치 반응이 존재하지 않는다",
    ),
    CheckSpec(
        "DQ-16", "4분면 분포", "Persuadables 20~30% 등",
        "Ground-truth 기반 고객 4분면 분포", "precondition_missing",
        # ★ measurement 소관이 아니다. Ground-truth 는 diagnostics 전용이고,
        #   이 계층이 그것을 읽으면 격리 규칙(ISO-003) 위반이다.
        "Ground-truth 는 diagnostics 전용이라 측정 계층이 읽을 수 없다 "
        "(격리 규칙). 시뮬레이터도 미가동이다",
    ),
    CheckSpec(
        "DQ-17", "재현성", "events.parquet SHA-256 일치 (NFR-001)",
        "같은 입력으로 두 번 쓴 Parquet 파일의 해시", "conditional",
        "pyarrow 가 설치되어 있으면 실행한다. 저장소 기본 환경에는 없다 "
        "(M-05 가 requirements.txt 에 넣었으나 CI 격리 잡은 설치하지 않는다)",
    ),
)

DQ_IDS = tuple(spec.id for spec in DQ_ALL)
DQ_INDEX: Mapping[str, CheckSpec] = {spec.id: spec for spec in DQ_ALL}

assert len(DQ_IDS) == len(set(DQ_IDS)), "DQ 검사 ID 가 중복이다"
assert len(DQ_ALL) == 18, (
    "검사 정의가 18종이 아니다. data-quality-design.md §3 의 표와 픽스처가 18 이고 "
    f"본문의 17 은 산술 오류다 (현재: {len(DQ_ALL)})"
)


@dataclass(frozen=True, slots=True)
class CheckResult:
    """검사 하나의 **결과**.

    `violations` 가 `int | None` 인 것이 요점이다. 실행하지 않은 검사에 `0` 을
    적으면 **통과처럼 읽힌다** — 계약이 `not_run`/`blocked`/`vacuous` 에서
    `violations: null` 을 강제한다.
    """

    id: str
    spec_ref: str
    title: str
    status: str
    scope: str
    examined_rows: int
    violations: int | None = None
    reason_code: str | None = None
    reason_detail: str | None = None
    samples: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.status not in CHECK_STATUSES:
            raise ValueError(f"{self.id}: 알 수 없는 status {self.status!r}")
        # ★ AC-5 — 세 겹의 강제. 하나라도 빠지면 공허한 통과가 살아난다.
        if self.examined_rows == 0 and self.status == "pass":
            raise ValueError(
                f"{self.id}: examined_rows=0 인데 status=pass 다. 아무것도 검사하지 "
                "않고 초록으로 표시하는 경로다 — vacuous 를 쓴다 (ADR-0010)"
            )
        if self.status == "pass" and self.examined_rows < 1:
            raise ValueError(f"{self.id}: status=pass 인데 examined_rows < 1 이다")
        if self.status in ("not_run", "blocked", "vacuous"):
            if self.violations is not None:
                raise ValueError(
                    f"{self.id}: status={self.status} 인데 violations="
                    f"{self.violations} 다. 0 으로 적으면 통과처럼 읽힌다 — null 이다"
                )
            if not (self.reason_detail or "").strip():
                raise ValueError(f"{self.id}: status={self.status} 인데 사유가 없다")
        if self.status == "vacuous":
            if self.examined_rows != 0:
                raise ValueError(
                    f"{self.id}: vacuous 인데 examined_rows={self.examined_rows} 다"
                )
            # ★ 계약이 vacuous 에 reason_code 를 **금지**한다 (F-E 교체분).
            #   status 가 이미 사유이므로 중복이다.
            if self.reason_code is not None:
                raise ValueError(
                    f"{self.id}: vacuous 인데 reason_code={self.reason_code!r} 가 "
                    "있다. status 가 이미 사유이므로 계약이 금지한다"
                )
        elif self.status in ("not_run", "blocked") and not self.reason_code:
            raise ValueError(f"{self.id}: status={self.status} 인데 reason_code 가 없다")

    def to_json(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "id": self.id, "spec_ref": self.spec_ref, "title": self.title,
            "status": self.status, "scope": self.scope,
            "examined_rows": self.examined_rows, "violations": self.violations,
        }
        if self.reason_code:
            payload["reason_code"] = self.reason_code
        if self.reason_detail:
            payload["reason_detail"] = self.reason_detail
        if self.samples:
            # 계약 `checks[].samples` 는 객체 목록이다 — 문자열로 내보내면 게시물이
            # 자기 계약을 어기고 화면의 `sample.detail` 이 빈 칸이 된다 (#113).
            payload["samples"] = [{"detail": sample} for sample in self.samples]
        return payload


def _outcome(
    spec: CheckSpec, *, examined: int, violations: int, samples: Sequence[str] = ()
) -> CheckResult:
    """실행한 검사의 결과를 만든다. **0행이면 `vacuous`** — `pass` 가 아니다."""
    if examined == 0:
        return CheckResult(
            id=spec.id, spec_ref=spec.spec_item, title=spec.title,
            status="vacuous", scope=spec.scope, examined_rows=0,
            violations=None,
            reason_detail=(
                f"검사 대상이 0행이었다 — {spec.scope} 에 해당하는 이벤트가 없다. "
                "통과가 아니라 검사하지 않은 것과 같다"
            ),
        )
    return CheckResult(
        id=spec.id, spec_ref=spec.spec_item, title=spec.title,
        status="fail" if violations else "pass",
        scope=spec.scope, examined_rows=examined, violations=violations,
        samples=tuple(samples[:5]),  # 표본은 5건까지 — 원문을 게시하지 않는다
        reason_detail=(
            f"{examined}행 중 {violations}행이 위반했다" if violations else None
        ),
    )


def _not_run(spec: CheckSpec) -> CheckResult:
    return CheckResult(
        id=spec.id, spec_ref=spec.spec_item, title=spec.title,
        status="not_run", scope=spec.scope, examined_rows=0, violations=None,
        reason_code=sc.ReasonCode.PRECONDITION_MISSING.value,
        reason_detail=spec.reason,
    )


def _blocked(spec: CheckSpec, detail: str | None = None) -> CheckResult:
    return CheckResult(
        id=spec.id, spec_ref=spec.spec_item, title=spec.title,
        status="blocked", scope=spec.scope, examined_rows=0, violations=None,
        reason_code=sc.ReasonCode.BLOCKED.value,
        reason_detail=detail or spec.reason,
    )


# ── 실행 가능한 검사 ────────────────────────────────────────────────────────
#
# 전부 `events` 시퀀스를 받는 순수 함수다. 출처를 묻지 않는다.

def check_event_id_unique(events: Sequence[Mapping[str, object]]) -> CheckResult:
    """`DQ-01` — `event_id` 전역 유일."""
    # ponytail: Counter over the whole sequence holds every event_id in memory.
    # data_spec §7.1 projects events ≈ 25,000,000, which this will not survive.
    # Upgrade path is already designed: per-partition sort to tempfiles, then
    # heapq.merge() over the sorted streams and compare neighbours (stdlib only,
    # memory O(partition count)). Trigger: when publish.py starts reading
    # partitions as a stream instead of materialising a list, or when a real
    # ingest run exceeds what bench_sink.py 20000 30 (4.2M rows) uses.
    ids = [e.get("event_id") for e in events if e.get("event_id") is not None]
    duplicates = [key for key, count in Counter(ids).items() if count > 1]
    return _outcome(
        DQ_INDEX["DQ-01"], examined=len(ids), violations=len(duplicates),
        samples=[str(key) for key in duplicates],
    )


def check_order_id_single_purchase(
    events: Sequence[Mapping[str, object]],
) -> CheckResult:
    """`DQ-02b` — `order_id` 당 `purchase` 정확히 1건.

    `DQ-02`(전역 유일)의 **범위 축소판**이다. `orders` 테이블이 없어 주문 명부를
    대조할 수 없지만, *"같은 주문에 구매 이벤트가 두 번 찍히지 않았다"* 는
    `events` 안에서 확인된다. **두 검사를 하나로 묶지 않는다** — ID 를 나눈 이유다.
    """
    order_ids = [
        e.get("order_id")
        for e in events
        if e.get("event_type") == sc.EventType.PURCHASE.value
        and e.get("order_id") is not None
    ]
    duplicates = [key for key, count in Counter(order_ids).items() if count > 1]
    return _outcome(
        DQ_INDEX["DQ-02b"], examined=len(order_ids), violations=len(duplicates),
        samples=[str(key) for key in duplicates],
    )


def check_amount_equation(
    events: Sequence[Mapping[str, object]],
    exchange: CommerceExchange | None,
) -> CheckResult:
    """`DQ-09` — 이벤트와 교환 파일이 **같은 주문을 같게 말하는가.**

    교환 파일의 주문마다 셋을 본다. 하나라도 어긋나면 그 주문이 위반이다:

        ① 품목이 1줄 이상 있다          없으면 계약이 약속한 것이 없다
        ② order_amount = Σ(unit_price × quantity) − discount   (교환 파일 안)
        ③ 같은 order_id 의 purchase 이벤트가 있고 그 order_amount 가 ②와 같다

    ③이 이 검사의 값어치다. 한 출처 안에서만 계산하면 그 출처가 스스로
    일관되기만 하면 통과한다. 이벤트의 금액 기준이 어긋났던 것(#106)은 ②로는
    안 보이고 ③으로만 보인다.

    교환 파일이 없으면 `not_run` 이다 — 대조하지 않은 것이지 위반이 아니다.
    """
    spec = DQ_INDEX["DQ-09"]
    if exchange is None:
        return _not_run(spec)
    purchases: dict[object, object] = {
        e.get("order_id"): e.get("order_amount")
        for e in events
        if e.get("event_type") == sc.EventType.PURCHASE.value
    }
    samples: list[str] = []
    for order_id, order in sorted(exchange.orders.items()):
        if not order.items:
            samples.append(f"{order_id}: 품목이 없다")
            continue
        items_total = sum(item.unit_price * item.quantity for item in order.items)
        if order.order_amount != items_total - order.discount:
            samples.append(
                f"{order_id}: 교환 파일 {order.order_amount} ≠ "
                f"품목 {items_total} − 할인 {order.discount}"
            )
        elif order_id not in purchases:
            samples.append(f"{order_id}: purchase 이벤트가 없다")
        elif purchases[order_id] != order.order_amount:
            samples.append(
                f"{order_id}: 이벤트 {purchases[order_id]} ≠ 교환 파일 {order.order_amount}"
            )
    return _outcome(
        spec, examined=len(exchange.orders), violations=len(samples), samples=samples,
    )


def _not_scoped(spec: CheckSpec) -> CheckResult:
    return CheckResult(
        id=spec.id, spec_ref=spec.spec_item, title=spec.title,
        status="not_run", scope=spec.scope, examined_rows=0, violations=None,
        reason_code=sc.ReasonCode.PRECONDITION_MISSING.value,
        reason_detail=(
            "교환 파일은 있지만 명부가 책임지는 이벤트 범위(exchange_scope)가 "
            "주어지지 않았다 — 전체 이벤트와 대조하면 다른 출처가 전부 고아가 된다"
        ),
    )


def _with_note(result: CheckResult, note: str | None) -> CheckResult:
    """대조에서 뺀 것이 있으면 그 사실을 사유에 싣는다. 통과여도 싣는다."""
    if not note:
        return result
    detail = f"{result.reason_detail} · {note}" if result.reason_detail else note
    return CheckResult(
        id=result.id, spec_ref=result.spec_ref, title=result.title,
        status=result.status, scope=result.scope,
        examined_rows=result.examined_rows, violations=result.violations,
        reason_code=result.reason_code, reason_detail=detail, samples=result.samples,
    )


def _within_snapshot(
    events: Sequence[Mapping[str, object]], exchange: CommerceExchange,
) -> tuple[list[Mapping[str, object]], str | None]:
    """명부 생성 시각 이후 이벤트를 뺀다. 시각을 읽을 수 없는 이벤트는 남긴다 —
    스냅샷 이후라고 증명할 수 없으면 대조한다."""
    kept: list[Mapping[str, object]] = []
    later = 0
    for event in events:
        moment = _parse(event.get("timestamp"))
        if moment is not None and moment.tzinfo is not None and moment > exchange.generated_at:
            later += 1
            continue
        kept.append(event)
    note = (
        f"명부 생성 시각({exchange.generated_at.isoformat()}) 이후 이벤트 {later}건은 "
        "명부가 책임지지 않아 대조하지 않았다 — 위반도 통과도 아니다"
        if later else None
    )
    return kept, note


def check_order_id_global_unique(exchange: CommerceExchange | None) -> CheckResult:
    """`DQ-02` — 교환 파일 주문 명부의 `order_id` 전역 유일.

    ★ 중복 방어는 로더(`exchange.read_exchange`)에 있다. 중복이 있으면 묶음 전체를
    거부하므로 여기까지 온 명부는 유일하다. 그래도 `not_run` 이 아니라 검사한 주문
    수와 함께 `pass` 로 게시한다 — 명부가 있고 유일함이 확인된 것은 사실이다.
    """
    spec = DQ_INDEX["DQ-02"]
    if exchange is None:
        return _not_run(spec)
    return _outcome(spec, examined=len(exchange.orders), violations=0)


def check_roster_references(
    exchange: CommerceExchange | None,
    exchange_scope: Sequence[Mapping[str, object]] | None,
) -> CheckResult:
    """`DQ-03` — 고아 `customer_id`·`product_id` 0건.

    대조 대상은 **명부가 책임지는 이벤트**(`exchange_scope`)뿐이다. 교환 파일은
    커머스 전용 명부라, 전체 이벤트와 대조하면 시뮬레이터 이벤트가 전부 고아가
    된다. 어느 이벤트가 그 범위인지는 출처를 아는 `publish.py` 가 정한다 — 이
    모듈은 출처를 묻지 않는다.
    """
    spec = DQ_INDEX["DQ-03"]
    if exchange is None:
        return _not_run(spec)
    if exchange_scope is None:
        return _not_scoped(spec)
    events, note = _within_snapshot(exchange_scope, exchange)
    examined = 0
    samples: list[str] = []
    for event in events:
        customer_id = event.get("customer_id")
        product_id = event.get("product_id")
        if customer_id is None and product_id is None:
            continue
        examined += 1
        missing = []
        if customer_id is not None and customer_id not in exchange.signup_dates:
            missing.append(f"customer_id {customer_id}")
        if product_id is not None and product_id not in exchange.product_ids:
            missing.append(f"product_id {product_id}")
        if missing:
            samples.append(f"{event.get('event_id')}: {' · '.join(missing)} 가 명부에 없다")
    return _with_note(
        _outcome(spec, examined=examined, violations=len(samples), samples=samples), note,
    )


def check_before_signup(
    exchange: CommerceExchange | None,
    exchange_scope: Sequence[Mapping[str, object]] | None,
) -> CheckResult:
    """`DQ-05` — 가입일 이전 이벤트 0건.

    가입일이 날짜(KST)라 **날짜 단위**로 비교한다. 가입 당일 가입 시각 이전의
    이벤트는 잡지 못한다 — 그 한계는 `scope` 가 말한다. 명부에 없는 고객의
    이벤트는 가입일을 모르므로 여기서 세지 않는다(`DQ-03` 이 그것을 본다).
    """
    spec = DQ_INDEX["DQ-05"]
    if exchange is None:
        return _not_run(spec)
    if exchange_scope is None:
        return _not_scoped(spec)
    events, note = _within_snapshot(exchange_scope, exchange)
    examined = 0
    samples: list[str] = []
    for event in events:
        signup = exchange.signup_dates.get(event.get("customer_id"))  # type: ignore[arg-type]
        moment = _parse(event.get("timestamp"))
        if signup is None or moment is None or moment.tzinfo is None:
            continue
        examined += 1
        day = moment.astimezone(KST).date()
        if day < signup:
            samples.append(
                f"{event.get('event_id')}: {day.isoformat()} 이벤트가 가입일 "
                f"{signup.isoformat()} 보다 앞선다 ({event.get('customer_id')})"
            )
    return _with_note(
        _outcome(spec, examined=examined, violations=len(samples), samples=samples), note,
    )


def _parse(value: object) -> datetime | None:
    if isinstance(value, datetime):
        return value
    try:
        return tp.parse_datetime(str(value))
    except (TypeError, ValueError):
        return None


def check_session_order(events: Sequence[Mapping[str, object]]) -> CheckResult:
    """`DQ-04` — 세션 내 이벤트 순서.

    같은 `session_id` 안에서 `timestamp` 가 뒤로 가는 이벤트를 센다. 파일에 기록된
    **순서**를 기준으로 보고 정렬하지 않는다 — 정렬하면 검사가 항상 통과한다.
    """
    by_session: dict[str, list[datetime]] = defaultdict(list)
    examined = 0
    for event in events:
        session = event.get("session_id")
        moment = _parse(event.get("timestamp"))
        if isinstance(session, str) and moment is not None:
            by_session[session].append(moment)
            examined += 1
    offenders = [
        session
        for session, moments in by_session.items()
        if any(b < a for a, b in zip(moments, moments[1:]))
    ]
    return _outcome(
        DQ_INDEX["DQ-04"], examined=examined, violations=len(offenders),
        samples=offenders,
    )


def check_timezone_single(events: Sequence[Mapping[str, object]]) -> CheckResult:
    """`DQ-06` — 모든 시각이 KST 단일. ★ **M-01 이 `BLOCKED` 를 풀었다.**

    타임존 정책(`#53` D1-3)이 미확정이라 실행할 수 없던 검사다. M-01 이 확정했다:
    입력은 어떤 오프셋이든 받고 **저장 시 KST 로 정규화**한다. 그래서 저장물의
    `timestamp` 는 전부 `+09:00` 이어야 하고, 이 검사가 **Sink 가 자기 약속을
    지켰는지 자기 저장물에 대해** 확인한다.

    ★ 정책을 ⑵-a(원문 보존)로 골랐다면 이 검사는 **자기 저장물에서 실패**했다.
    그것이 저장 표현 b 를 고른 이유다.
    """
    examined = 0
    offenders: list[str] = []
    for event in events:
        moment = _parse(event.get("timestamp"))
        if moment is None:
            continue
        examined += 1
        offset = moment.utcoffset()
        if offset is None or offset.total_seconds() != 9 * 3600:
            offenders.append(str(event.get("event_id") or event.get("timestamp")))
    return _outcome(
        DQ_INDEX["DQ-06"], examined=examined, violations=len(offenders),
        samples=offenders,
    )


def _precedes(
    events: Sequence[Mapping[str, object]],
    *,
    later: sc.EventType,
    earlier: sc.EventType,
    key: str,
) -> tuple[int, list[str]]:
    """`later` 이벤트마다 같은 `key` 값의 선행 `earlier` 가 있는지.

    시각 비교까지 한다 — 같은 세션에 `checkout_start` 가 있어도 그것이
    `purchase` **뒤**라면 선행이 아니다.
    """
    earliest: dict[object, datetime] = {}
    for event in events:
        if event.get("event_type") != earlier.value:
            continue
        moment = _parse(event.get("timestamp"))
        group = event.get(key)
        if moment is None or group is None:
            continue
        if group not in earliest or moment < earliest[group]:
            earliest[group] = moment

    examined = 0
    offenders: list[str] = []
    for event in events:
        if event.get("event_type") != later.value:
            continue
        moment = _parse(event.get("timestamp"))
        group = event.get(key)
        if moment is None or group is None:
            continue
        examined += 1
        first = earliest.get(group)
        if first is None or first > moment:
            offenders.append(str(event.get("event_id") or group))
    return examined, offenders


def check_purchase_funnel(events: Sequence[Mapping[str, object]]) -> CheckResult:
    """`DQ-07` — `purchase` 앞에 같은 세션의 `checkout_start` 가 있다."""
    examined, offenders = _precedes(
        events, later=sc.EventType.PURCHASE,
        earlier=sc.EventType.CHECKOUT_START, key="session_id",
    )
    return _outcome(
        DQ_INDEX["DQ-07"], examined=examined, violations=len(offenders),
        samples=offenders,
    )


def check_coupon_funnel(events: Sequence[Mapping[str, object]]) -> CheckResult:
    """`DQ-08` — `coupon_use` 앞에 같은 쿠폰의 `coupon_exposed` 가 있다."""
    examined, offenders = _precedes(
        events, later=sc.EventType.COUPON_USE,
        earlier=sc.EventType.COUPON_EXPOSED, key="coupon_id",
    )
    return _outcome(
        DQ_INDEX["DQ-08"], examined=examined, violations=len(offenders),
        samples=offenders,
    )


_AMOUNT_FIELDS = ("quantity", "unit_price", "order_amount", "session_duration")


def check_no_negative_amounts(events: Sequence[Mapping[str, object]]) -> CheckResult:
    """`DQ-10` — 음수 금액 0건.

    `DQ-09`(금액 등식)와 **묶지 않는다.** 등식은 원리적으로 검사 불가인데 부호는
    확인된다. 하나로 묶어 *"금액 정합성 통과"* 로 적으면 확인하지 않은 것이
    확인된 것으로 읽힌다 — 그래서 ID 를 나눴다.
    """
    examined = 0
    offenders: list[str] = []
    for event in events:
        values = [
            event[name] for name in _AMOUNT_FIELDS
            if isinstance(event.get(name), int)
        ]
        if not values:
            continue
        examined += 1
        if any(value < 0 for value in values):
            offenders.append(str(event.get("event_id")))
    return _outcome(
        DQ_INDEX["DQ-10"], examined=examined, violations=len(offenders),
        samples=offenders,
    )


def check_key_completeness(events: Sequence[Mapping[str, object]]) -> CheckResult:
    """`DQ-11` — Key 결측 0%.

    `schema.required_fields()` 를 쓴다 — 이벤트 타입별 필수 필드가 다르므로
    Core 4종만 보면 절반을 놓친다. **결손 판정 규칙을 두 번 적지 않는다.**
    """
    examined = 0
    offenders: list[str] = []
    for event in events:
        try:
            event_type = sc.EventType(event.get("event_type"))
        except ValueError:
            # event_type 자체가 없으면 Key 결측의 극단이다. 건너뛰지 않는다.
            examined += 1
            offenders.append(str(event.get("event_id") or "<event_type 없음>"))
            continue
        examined += 1
        if any(
            event.get(name) is None for name in sc.required_fields(event_type)
        ):
            offenders.append(str(event.get("event_id")))
    return _outcome(
        DQ_INDEX["DQ-11"], examined=examined, violations=len(offenders),
        samples=offenders,
    )


def check_parquet_reproducible(
    *, digests: Sequence[str] | None = None
) -> CheckResult:
    """`DQ-17` — 같은 입력 2회 → 같은 SHA-256 (`NFR-001`).

    ★ **`blocked` 와 실행을 환경으로 가른다.** pyarrow 가 없으면 이 경로를 밟을 수
    없고, 그 사실이 `blocked` + `BLOCKED` 로 남는다 — **`pass` 로 적지 않는다.**

    M-05 가 pyarrow 를 `requirements.txt` 에 넣었으나 격리 CI 잡은 의존성을
    설치하지 않으므로(ISO-005) 저장소 기본 환경에서는 계속 `blocked` 다.
    `tests/test_sink.py TestParquetPath` 가 설치 환경에서 이 경로를 실제로 밟는다.
    """
    spec = DQ_INDEX["DQ-17"]
    if not parquet_available():
        return _blocked(
            spec,
            "pyarrow 가 설치되어 있지 않아 Parquet 재현성을 검증하지 않았다. "
            "requirements.txt 에 pyarrow==25.0.1 이 있으나 격리 CI 잡은 의존성을 "
            "설치하지 않는다 (ISO-005). 해소: pip install -r requirements.txt 후 "
            "tests.test_sink.TestParquetPath 실행",
        )
    if digests is None:
        return _blocked(
            spec,
            "pyarrow 는 있으나 대조할 해시가 전달되지 않았다 — 게시 호출부가 "
            "같은 입력을 두 번 써서 두 해시를 넘겨야 한다",
        )
    unique = set(digests)
    return _outcome(
        spec, examined=len(digests), violations=0 if len(unique) <= 1 else 1,
        samples=sorted(unique),
    )


# ── 게이트 판정 · 리포트 ────────────────────────────────────────────────────

def gate_result(checks: Sequence[CheckResult]) -> str:
    """`pass` · `incomplete` · `fail` 셋 중 하나.

    | 값 | 조건 | 파이프라인 |
    |---|---|---|
    | `fail` | **데이터가 검사를 위반했다** | **중단** |
    | `incomplete` | 실행분은 전부 통과 ∧ `not_run`·`blocked`·`vacuous` 가 1개 이상 | 진행 + 크게 표시 |
    | `pass` | **모든** 검사가 `pass` | 진행 |

    ★ `pass` 의 조건이 *"실행한 것이 전부 통과"* 가 아니라 **"모든 검사가 `pass`"**
    다. `vacuous` 하나만 있어도 `pass` 가 아니다 — 그 하나가 39% 였던 것이
    `ADR-0010` 의 계기다.
    """
    if not checks:
        raise ValueError("검사 결과가 비었다 — 18종을 항상 낸다")
    if any(check.status == "fail" for check in checks):
        return "fail"
    if all(check.status == "pass" for check in checks):
        return "pass"
    return "incomplete"


#: 검사 상태의 나쁜 순서. `worst_status` 를 고를 때 쓴다 — 한 항목을 여러 검사가
#: 나눠 덮으면 **가장 나쁜 것**이 그 항목의 상태다. 하나가 통과했다고 항목이
#: 통과한 것이 아니다.
_STATUS_SEVERITY = {"fail": 0, "blocked": 1, "not_run": 2, "vacuous": 3, "pass": 4}


def spec_coverage(checks: Sequence[CheckResult]) -> dict[str, object]:
    """`data_spec` §9 정본 항목의 덮임 상태.

    ★ **화면이 정본 목록을 상수로 들지 않는다** — 게시물이 준다 (AC-7). 화면이
    들면 정본이 두 벌이 되고, 게시물이 주는 것만 그리면 빠진 검사가 사라진다 —
    **사라진 것은 통과처럼 읽힌다.**

    항목마다 `covered_by`(어느 DQ 가 덮는가)와 `worst_status`(그중 가장 나쁜 상태)
    를 함께 낸다. 한 항목을 여러 검사가 나눠 덮으므로(금액 정합성 = DQ-09 +
    DQ-10) **하나가 통과했다고 항목이 통과한 것이 아니다.**

    `reported_checks` 를 **`len(checks)` 로 산출한다** (Q-3). 상수로 적으면 실린
    수와 어긋나고, 실제로 픽스처가 `7` 건에 `6` 을 적었다.
    """
    by_item: dict[str, list[CheckResult]] = defaultdict(list)
    for check in checks:
        by_item[DQ_INDEX[check.id].spec_item].append(check)

    spec_items = [
        {
            "spec_ref": item,
            "covered_by": sorted(check.id for check in results),
            "worst_status": min(
                (check.status for check in results),
                key=lambda status: _STATUS_SEVERITY[status],
            ),
        }
        for item, results in sorted(by_item.items())
    ]
    return {
        "spec_items": spec_items,
        "reported_checks": len(checks),
        # ★ "매핑되지 않은" = **아무 검사도 정의되지 않은** 항목이다 (AC-7).
        #
        #   실행 여부는 `worst_status` 가 이미 말한다 — 둘을 섞으면 "검사를 아예
        #   안 만들었다"와 "만들었지만 대상이 0행이었다"가 같아 보이고, 조치가
        #   완전히 다르다(검사를 구현해야 하는가 vs 데이터를 모아야 하는가).
        #
        #   1차 구현이 `worst_status not in (pass, fail)` 로 썼다가 "금액 정합성"
        #   이 DQ-10 통과에도 unmapped 로 나왔다 — 덮여 있는데 안 덮였다고 말한 것이다.
        "unmapped_spec_items": [
            entry["spec_ref"] for entry in spec_items if not entry["covered_by"]
        ],
    }


def run_all(
    events: Sequence[Mapping[str, object]],
    *,
    parquet_digests: Sequence[str] | None = None,
    exchange: CommerceExchange | None = None,
    exchange_scope: Sequence[Mapping[str, object]] | None = None,
) -> list[CheckResult]:
    """★ **항상 18종을 낸다.** 실행 못 한 것도 목록에 남는다 (AC-3 · Q-4).

    빼면 *"검사하지 않았다"* 가 보이지 않고 *"통과했다"* 와 구분되지 않는다.
    `commerce-connected` 픽스처가 7종만 담은 것은 그 스냅샷의 결함이다.
    """
    runners = {
        "DQ-01": lambda: check_event_id_unique(events),
        "DQ-02": lambda: check_order_id_global_unique(exchange),
        "DQ-03": lambda: check_roster_references(exchange, exchange_scope),
        "DQ-05": lambda: check_before_signup(exchange, exchange_scope),
        "DQ-02b": lambda: check_order_id_single_purchase(events),
        "DQ-04": lambda: check_session_order(events),
        "DQ-06": lambda: check_timezone_single(events),
        "DQ-07": lambda: check_purchase_funnel(events),
        "DQ-08": lambda: check_coupon_funnel(events),
        "DQ-09": lambda: check_amount_equation(events, exchange),
        "DQ-10": lambda: check_no_negative_amounts(events),
        "DQ-11": lambda: check_key_completeness(events),
        "DQ-17": lambda: check_parquet_reproducible(digests=parquet_digests),
    }
    results = [
        runners[spec.id]() if spec.id in runners else _not_run(spec)
        for spec in DQ_ALL
    ]
    _verify_report_invariants(results)
    return results


def _verify_report_invariants(checks: Sequence[CheckResult]) -> None:
    """★★ 3층 자기검증 (Q-3 · Q-4). **스키마로 표현할 수 없는 것들이다.**

    draft 2020-12 에 교차 필드·배열 길이 비교 키워드가 없다(`$data` 는 Ajv 확장
    이지 표준이 아니다). 그래서 스키마에 적으려 시도하지 않고 여기서 막는다.

        ① len(checks) == len(DQ_ALL)      실려야 할 것이 다 실렸다
        ② reported_checks == len(checks)  보고한 수 = 실린 수
        ③ {c.id} == set(DQ_IDS)           ★ 빠진 ID 가 무엇인지 말한다

    ★ ③이 요점이다. ①②는 *"수가 맞다"* 만 말하고 **어느 것이 빠졌는지 못 말한다.**
    `reported_checks == len(checks)` 는 *"보고한 수 = 실린 수"* 만 보장하고
    *"실려야 할 것이 다 실렸다"* 는 **보장하지 않는다 — 두 명제는 다르다.**

    `18` 을 리터럴로 적지 않는다. `DQ_ALL` 하나가 정본이다 — Q-3 에서 세운 원칙
    (*"상수를 두 번 적지 않는 것이 가장 싼 방어"*)을 그 검사 자신이 어기면 안 된다.
    """
    if len(checks) != len(DQ_ALL):
        raise QualityGateFailure(
            f"검사 {len(checks)}건을 냈으나 정의는 {len(DQ_ALL)}종이다. 실행하지 "
            "못한 검사를 목록에서 빼면 '검사하지 않았다'가 '통과했다'와 구분되지 "
            "않는다 (AC-3)"
        )
    reported = spec_coverage(checks)["reported_checks"]
    if reported != len(checks):
        raise QualityGateFailure(
            f"reported_checks={reported} 인데 실린 검사는 {len(checks)}건이다 — "
            "len(checks) 로 산출해 상수를 두 번 적지 않는다 (Q-3)"
        )
    missing = sorted(set(DQ_IDS) - {check.id for check in checks})
    if missing:
        raise QualityGateFailure(
            f"검사 목록에서 빠진 ID: {missing} — 수는 맞아도 어느 것이 빠졌는지 "
            "말해야 한다 (Q-4)"
        )


def build_report(
    events: Sequence[Mapping[str, object]],
    *,
    parquet_digests: Sequence[str] | None = None,
    exchange: CommerceExchange | None = None,
    exchange_scope: Sequence[Mapping[str, object]] | None = None,
) -> dict[str, object]:
    """`results/data_quality_report.json` 의 본문 (봉투는 `contracts.envelope`).

    **`gate_result == "fail"` 일 때 예외를 던지지 않는다** — 리포트는 만들어져야
    한다. 파이프라인 중단은 호출자(`publish.py`)가 `raise_on_fail()` 로 한다.
    실패 사실을 담은 리포트를 게시하지 못하면 **무엇이 실패했는지 화면이 모른다.**
    """
    checks = run_all(
        events, parquet_digests=parquet_digests,
        exchange=exchange, exchange_scope=exchange_scope,
    )
    return {
        "gate_result": gate_result(checks),
        "spec_coverage": spec_coverage(checks),
        "checks": [check.to_json() for check in checks],
    }


def raise_on_fail(report: Mapping[str, object]) -> None:
    """`gate_result == "fail"` 이면 중단한다 (`QualityGateFailure`, 종료 코드 2).

    `data_spec` §9: *"하나라도 실패하면 파이프라인은 중단한다(경고로 넘어가지
    않는다)."* **`incomplete` 로는 멈추지 않는다** — 그것은 데이터의 실패가 아니라
    검사기의 한계이고, 멈추면 C1 에서 파이프라인이 영원히 돌지 않는다.
    """
    if report.get("gate_result") != "fail":
        return
    failed = [
        check["id"]
        for check in report.get("checks", [])  # type: ignore[union-attr]
        if check.get("status") == "fail"
    ]
    raise QualityGateFailure(
        f"데이터 품질 검사가 실패했다: {', '.join(failed)}. data_spec §9 는 "
        "하나라도 실패하면 파이프라인을 중단하라고 규정한다 — 경고로 넘어가지 "
        "않는다. results/data_quality_report.json 의 해당 검사 행을 본다."
    )
