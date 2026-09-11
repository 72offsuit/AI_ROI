"""경제 규칙 계산 — `ECONOMIC RULE v1` (이슈 #47).

## 이 모듈이 모르는 것이 이 모듈의 설계다

**출처를 모른다.** 두 출처의 이름이 이 파일에 문자열로도 등장하지 않는다. 출처별
결과가 필요하면 **분기가 아니라 입력 분할**로 얻는다 — `publish.py` 가 이벤트를
출처별로 쪼개 같은 함수를 두 번 호출하고, 결과를 출처별 키에 담는다. 같은 함수,
같은 식, 다른 입력.

출처로 분기하면 오늘의 요구는 가장 짧게 충족되지만, **한쪽이 나중에 `unit_cost` 를
넣어도 코드가 계속 거부한다.** 창구가 한쪽의 구현 상태를 알면 계약이 아니게 된다.

**원가율을 모른다** (EC-9). `CostAccountingConfig` 에 원가율 계열 속성이 아예 없으므로
타입 수준에서 접근 경로가 없다. 원가는 **저장된 `unit_cost`** 로만 계산한다 (EC-1):

    원가율 → unit_cost 생성 → 저장 → Σ(unit_cost × qty)   ✅ 기록을 읽는다
    order_amount × 원가율 → COGS                          ❌ 기록 없는 곳에 값을 만든다

후자를 하면 `contribution_profit` 이 `revenue` 의 상수배가 되어 두 값이 같은 정보만
담고, `revenue_up_profit_down` 가드레일이 원리적으로 발동할 수 없다. **가드레일이
죽는다.**

**I/O 를 모른다.** `open`·`Path`·`json`·`yaml` 을 import 하지 않는다. 순수 함수이므로
config 도 dataclass 로 받는다 — 그래서 `tests/test_economics.py` 가 PyYAML 없이
전부 돈다 (A7 사슬의 첫 고리).

위 셋을 `tests/test_neutrality.py` 가 **소스 검사로** 고정한다. 값 검사로는 "오늘
우연히 맞다"만 보이지만, 소스 검사는 다음 사람이 분기를 넣는 순간 실패한다.

## 반환 타입이 전부 `MetricValue` 다

`-> int` 를 돌려주는 함수를 두지 않는다. 그러면 원가 근거가 없을 때 `0` 을 돌려줄
자리가 생기고, `0` 은 기여이익 = 매출을 만든다. `MetricValue` 에는 그 자리가 없다.

## C1 의 실제 동작 — 미리 알아둘 것

`purchase` 는 주문 단위 1행이고 `unit_cost` 컬럼이 스키마에 없다. 그래서 C1 에서
`OrderView.items` 는 **두 출처 모두 비어 있고** `cogs` 는 항상 `NO_COST_BASIS` 를
낸다. 그것이 결함이 아니라 USP-1 대표 장면의 실제 내용이다.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from src.measurement.config_loader import CostAccountingConfig
from src.measurement.schema import (
    Basis,
    BlockerKind,
    BlockerRef,
    MetricStatus,
    MetricValue,
    ReasonCode,
    Unit,
    Window,
    WindowDirection,
)

_NO_WINDOW = Window(WindowDirection.NONE)
_SUM_DENOMINATOR = "분모 없음 (합계)"
"""합계·건수 지표의 `denominator_definition`.

"분모가 없다"를 빈 문자열로 표현하지 않는다. 빈 값은 "분모를 안 적었다"와
구분되지 않고, 계약이 `minLength: 1` 로 그것을 막는다."""


# ── 입력 자료구조 — 이 모듈이 스스로 정의한다 ───────────────────────────────
#
# 이벤트 dict·manifest·파일을 받지 않는다. 순수 함수를 유지하려면 입력이 이미
# 조립된 값이어야 하고, **조립은 publish.py 가 한다** — 이벤트를 OrderView 로
# 바꾸는 일은 출처를 아는 유일한 자리와 같은 층이다.

@dataclass(frozen=True, slots=True)
class OrderItem:
    product_id: str
    quantity: int
    unit_price: int
    unit_cost: int | None = None
    """★ `None` 이면 원가 근거가 없다 → `NO_COST_BASIS`.

    `0` 으로 채우지 않는다. 원가 0 원인 상품과 원가를 모르는 상품은 다르다."""


@dataclass(frozen=True, slots=True)
class OrderView:
    """`economics.py` 가 이해하는 주문 하나.

    `items=()` 와 `unit_cost=None` 을 구분한다:
      - `items=()`            품목 자체를 모른다 (C1 의 정상 상태 — purchase 는 주문 1행)
      - `unit_cost=None`      품목은 아는데 원가를 모른다
    `reason_detail` 이 둘을 다르게 쓴다. 같은 `NO_COST_BASIS` 라도 해소 방법이
    다르기 때문이다 — 전자는 테이블이 필요하고 후자는 컬럼이 필요하다.
    """

    order_id: str
    order_amount: int
    items: tuple[OrderItem, ...] = ()
    treatment_ids: tuple[str, ...] = ()
    has_coupon_use: bool = False


@dataclass(frozen=True, slots=True)
class CampaignView:
    """비용 계상에 필요한 캠페인 한 건의 관측 사실.

    `messages_sent` 와 `targeted_customers` 를 나눈 이유는 EC-4 다. 같은 고객에게
    두 번 발송하면 메시지는 2건이지만 `N_targeted` 는 1명이다.
    """

    campaign_id: str
    messages_sent: int = 0
    targeted_customers: int = 0
    campaigns_run: int = 1
    coupon_used_orders: tuple[OrderView, ...] = field(default_factory=tuple)


# ── EC-2 · 원가 근거 ────────────────────────────────────────────────────────

def has_cost_basis(order: OrderView) -> bool:
    """이 주문의 **모든** 품목에 `unit_cost` 가 있는가.

    ★ 판정 기준이 출처가 아니라 근거다. 이 함수가 `order.source` 를 보지 않는다는
    사실이 EC-2 전체다:

        커머스가 unit_cost 를 넣으면       → 자동으로 계산된다 (코드 수정 없이)
        시뮬레이터가 원가 없는 상품을 만들면 → 계산을 거부한다 (올바르게)

    품목이 비어 있으면 `False` 다. "빈 목록의 모든 원소가 조건을 만족한다"는
    공허참이지만, 여기서 그것을 참으로 쓰면 **품목을 모르는 주문의 COGS 가 0 원**이
    되어 이익이 매출과 같아진다. C1 에서 이 경로가 정상 경로다.

        >>> has_cost_basis(OrderView("O1", 1000))                        # items 없음
        False
        >>> has_cost_basis(OrderView("O1", 1000, (OrderItem("P1", 1, 1000, None),)))
        False
        >>> has_cost_basis(OrderView("O1", 1000, (OrderItem("P1", 1, 1000, 780),)))
        True
    """
    if not order.items:
        return False
    return all(item.unit_cost is not None for item in order.items)


def cogs(order: OrderView) -> MetricValue:
    """매출원가 = Σ(`unit_cost` × `quantity`). 근거가 없으면 **계산 불가**다.

    `0` 도, 원가율로 추정한 값도 돌려주지 않는다 (EC-1).
    """
    if not order.items:
        return MetricValue.unavailable(
            ReasonCode.NO_COST_BASIS,
            f"주문 {order.order_id} 의 품목을 알 수 없다 — purchase 이벤트는 주문 "
            "단위 1행이고 order_items 테이블이 없어 품목을 재구성할 수 없다",
            unit=Unit.KRW,
            blocked_by=(
                BlockerRef(BlockerKind.TABLE, "order_items", ReasonCode.NO_COST_BASIS),
            ),
        )
    missing = [item.product_id for item in order.items if item.unit_cost is None]
    if missing:
        return MetricValue.unavailable(
            ReasonCode.NO_COST_BASIS,
            f"주문 {order.order_id} 의 품목 {len(order.items)}건 중 {len(missing)}건에 "
            f"unit_cost 가 없다 (예: {missing[0]})",
            unit=Unit.KRW,
            blocked_by=(
                BlockerRef(
                    BlockerKind.SCHEMA_GAP, "unit_cost", ReasonCode.NO_COST_BASIS
                ),
            ),
        )
    total = sum(item.unit_cost * item.quantity for item in order.items)  # type: ignore[operator]
    return MetricValue.ok(
        total,
        unit=Unit.KRW,
        basis=Basis(
            population=f"주문 {order.order_id} 의 품목",
            denominator_definition=_SUM_DENOMINATOR,
            window=_NO_WINDOW,
            observed_count=len(order.items),
            source_event_types=("purchase",),
        ),
    )


def revenue(orders: tuple[OrderView, ...]) -> MetricValue:
    """매출 = Σ `order_amount`. **원가 유무와 무관하게 계산된다.**

    ★★ 가르는 기준은 **합이 0 인가**가 아니라 **근거 이벤트가 있는가**다.

        주문 0건                  → unavailable · NO_SOURCE_EVENT   근거가 없다
        주문 1건, order_amount=0  → ok · 0                          세어봤고 0 이었다

    전자에 `0` 을 쓰면 **"아무도 사지 않았다"는 사업적 사실을 관측하지 않고 단정하는
    것**이 된다. 오늘 두 출처 모두 이벤트를 한 건도 기록하지 않으므로(별도 저장소
    이슈 `#28` 미착수) 실제로는 "매출 0원"이 아니라 "매출을 알 수 없음"이다. 그 둘을
    합치면 대시보드가 0원을 사업 성과로 표시한다.

    후자는 다르다 — `purchase` 를 1건 관측했고 금액이 0 이었다. `observed_count=1`
    이 그 증거를 싣는다.

    ⚠ **m-03 과 m-04 가 어긋났던 자리다.** m-03 은 이 경우를 규정하지 않았고 1차
    구현이 `ok`+0 을 냈다. m-04 `AC-4`·`T-6` 이 `unavailable`+`NO_SOURCE_EVENT` 를
    명시하므로 그쪽을 따랐다 — **m-04 가 이 경계의 정본이다.**

    A-REFUND 가정: 환불·취소를 차감하지 않으므로 총매출을 순매출로 간주한다.
    환불이 발생하는 환경에서는 과대평가된다 — `notices` 로 함께 게시한다.
    """
    if not orders:
        return MetricValue.unavailable(
            ReasonCode.NO_SOURCE_EVENT,
            "purchase 이벤트가 0건이라 매출을 계산할 근거가 없다 — 매출 0원과 "
            "근거 없음은 다르다",
            unit=Unit.KRW,
            blocked_by=(
                BlockerRef(
                    BlockerKind.EVENT_TYPE, "purchase", ReasonCode.NO_SOURCE_EVENT
                ),
            ),
        )
    total = sum(order.order_amount for order in orders)
    return MetricValue.ok(
        total,
        unit=Unit.KRW,
        basis=Basis(
            population="purchase 이벤트로 관측된 주문",
            denominator_definition=_SUM_DENOMINATOR,
            window=_NO_WINDOW,
            observed_count=len(orders),
            source_event_types=("purchase",),
        ),
        limit_note="환불·취소를 차감하지 않는다 (가정 A-REFUND) — 총매출이다",
    )


# ── EC-3 · 발생주의 3원칙 ───────────────────────────────────────────────────

def message_cost(
    campaign: CampaignView, *, config: CostAccountingConfig
) -> MetricValue:
    """메시지 비용 = 발송 건수 × 단가. **발송 시점에 처치군 전원.**

    반응 여부를 묻지 않는다. 역효과 고객(Sleeping Dog)에게 쓴 비용도 계상한다 —
    지우면 ROI 가 과대평가되고, 그것이 이 프로젝트가 측정하려는 바로 그 값이다.
    """
    return MetricValue.ok(
        campaign.messages_sent * config.message_cost_krw,
        unit=Unit.KRW,
        basis=Basis(
            population=f"캠페인 {campaign.campaign_id} 의 push_sent 이벤트",
            denominator_definition=_SUM_DENOMINATOR,
            window=_NO_WINDOW,
            observed_count=campaign.messages_sent,
            source_event_types=("push_sent",),
        ),
        limit_note="반응 여부와 무관하게 발송 전원에게 계상한다 (EC-3 1원칙)",
    )


def coupon_cost(
    campaign: CampaignView, *, config: CostAccountingConfig
) -> MetricValue:
    """할인 비용. **쿠폰이 실제 사용된 주문에만** 계상한다 (EC-3 2원칙).

    최소주문금액 미달로 쿠폰이 쓰이지 않으면 이 비용은 `0` 이 아니라 **발생하지
    않는다.** 그 경우 `message_cost` 만 남는다 — 둘의 차이가 캠페인 효율의 실질이다.

    `discount` 필드가 스키마에 없으므로 `treatment_cost` 에서 유도한다 (D-16).
    유도값이므로 `derived=True` + `derivation` 을 함께 싣는다 — 저장된 사실과
    구분되어야 한다.
    """
    coupon_treatments = set(config.coupon_treatments)
    total = 0
    for order in campaign.coupon_used_orders:
        if not order.has_coupon_use:
            # coupon_use 이벤트가 없으면 발생하지 않았다. 0 을 더하는 것과 다르다.
            continue
        for treatment_id in order.treatment_ids:
            if treatment_id not in coupon_treatments:
                continue
            if treatment_id not in config.treatment_cost:
                # config 에 없는 처치를 0 원으로 읽지 않는다. `.get(k, 0)` 을 쓰면
                # "설정이 빠졌다"가 "공짜다"로 조용히 바뀐다.
                return MetricValue.unavailable(
                    ReasonCode.PRECONDITION_MISSING,
                    f"주문 {order.order_id} 에 적용된 처치 {treatment_id} 의 단가가 "
                    "경제 규칙 config 에 없다 — 0 원으로 간주하지 않는다",
                    unit=Unit.KRW,
                    blocked_by=(
                        BlockerRef(
                            BlockerKind.PARAMETER,
                            f"treatment_cost.{treatment_id}",
                            ReasonCode.PRECONDITION_MISSING,
                        ),
                    ),
                )
            total += config.treatment_cost[treatment_id]
    used = sum(1 for order in campaign.coupon_used_orders if order.has_coupon_use)
    return MetricValue.ok(
        total,
        unit=Unit.KRW,
        basis=Basis(
            population=f"캠페인 {campaign.campaign_id} 의 coupon_use 이벤트가 있는 주문",
            denominator_definition=_SUM_DENOMINATOR,
            window=_NO_WINDOW,
            observed_count=used,
            excluded_count=len(campaign.coupon_used_orders) - used,
            excluded_reason=(
                "coupon_use 이벤트가 없어 할인이 발생하지 않은 주문 "
                "(최소주문금액 미달 등)"
            )
            if len(campaign.coupon_used_orders) - used
            else None,
            source_event_types=("coupon_use",),
        ),
        derived=True,
        derivation=(
            "Σ treatment_cost[t].unit_cost_krw for t in (order.treatment_ids ∩ "
            "coupon_treatments), coupon_use 이벤트가 있는 주문에 한해 (D-16 유도 규칙)"
        ),
        limit_note="discount 필드가 스키마에 없어 처치 단가에서 유도한 값이다",
    )


def shipping_subsidy(
    orders: tuple[OrderView, ...], *, config: CostAccountingConfig
) -> MetricValue:
    """배송비 보조. `order_amount < 무료배송 기준` ∧ `T1` 적용 → 배송비 (D-3 유도)."""
    eligible = [
        order
        for order in orders
        if order.order_amount < config.free_shipping_threshold_krw
        and "T1" in order.treatment_ids
    ]
    return MetricValue.ok(
        len(eligible) * config.shipping_fee_krw,
        unit=Unit.KRW,
        basis=Basis(
            population="T1(무료배송) 처치가 적용된 무료배송 기준 미달 주문",
            denominator_definition=_SUM_DENOMINATOR,
            window=_NO_WINDOW,
            observed_count=len(eligible),
            excluded_count=len(orders) - len(eligible),
            excluded_reason="무료배송 기준 이상이거나 T1 처치가 아닌 주문"
            if len(orders) - len(eligible)
            else None,
            source_event_types=("purchase",),
        ),
        derived=True,
        derivation=(
            f"order_amount < {config.free_shipping_threshold_krw} ∧ T1 ∈ treatment_ids "
            f"→ {config.shipping_fee_krw}원 (D-3 유도 규칙)"
        ),
        limit_note="shipping_subsidy 필드가 스키마에 없어 규칙에서 유도한 값이다",
    )


# ── EC-4 · N_targeted ───────────────────────────────────────────────────────

def n_targeted(campaign: CampaignView) -> MetricValue:
    """`push_sent` 가 발생한 **고유 고객 수**.

    배정된 처치군 전체가 아니고 반응한 고객 수도 아니다. 발송 실패·제외 고객이
    캠페인 고정비를 나눠 갖지 않게 하는 정의다.
    """
    return MetricValue.ok(
        campaign.targeted_customers,
        unit=Unit.COUNT,
        basis=Basis(
            population=f"캠페인 {campaign.campaign_id} 에서 push_sent 가 발생한 고유 고객",
            denominator_definition=_SUM_DENOMINATOR,
            window=_NO_WINDOW,
            observed_count=campaign.targeted_customers,
            source_event_types=("push_sent",),
        ),
    )


def campaign_fixed_cost(
    campaign: CampaignView, *, config: CostAccountingConfig
) -> MetricValue:
    """캠페인 운영 고정비 총액. 고객당 배분은 `campaign_fixed_cost_per_customer`."""
    return MetricValue.ok(
        campaign.campaigns_run * config.campaign_fixed_cost_krw,
        unit=Unit.KRW,
        basis=Basis(
            population="실행된 캠페인",
            denominator_definition=_SUM_DENOMINATOR,
            window=_NO_WINDOW,
            observed_count=campaign.campaigns_run,
        ),
    )


def campaign_fixed_cost_per_customer(
    campaign: CampaignView, *, config: CostAccountingConfig
) -> MetricValue:
    """고정비 ÷ `N_targeted`. ★ `N_targeted == 0` 이면 **나누지 않는다.**

    오늘이 정확히 0 건이다 (이벤트가 없다). 0 으로 나눠 `inf` 를 만들거나 `0` 으로
    떨어뜨리면 그 값이 게시물까지 간다. 계약도 `basis.denominator == 0` 일 때
    `status: ok` 를 금지한다.
    """
    total = campaign.campaigns_run * config.campaign_fixed_cost_krw
    if campaign.targeted_customers == 0:
        return MetricValue.unavailable(
            ReasonCode.NO_SOURCE_EVENT,
            f"N_targeted 가 0 이라 고객당 고정비를 계산할 수 없다 — 캠페인 고정비 "
            f"{total:,}원은 캠페인 단위로 남는다 (push_sent 이벤트 0건)",
            unit=Unit.KRW_PER_CUSTOMER,
            blocked_by=(
                BlockerRef(
                    BlockerKind.EVENT_TYPE, "push_sent", ReasonCode.NO_SOURCE_EVENT
                ),
            ),
        )
    return MetricValue.ok(
        total / campaign.targeted_customers,
        unit=Unit.KRW_PER_CUSTOMER,
        basis=Basis(
            population="push_sent 가 발생한 고유 고객",
            denominator_definition="N_targeted — push_sent 가 발생한 고유 고객 수",
            window=_NO_WINDOW,
            denominator=campaign.targeted_customers,
            observed_count=campaign.targeted_customers,
            source_event_types=("push_sent",),
        ),
    )


# ── EC-5 · 계획값 ≠ 실현값 ──────────────────────────────────────────────────
#
# 이름을 나누는 것이 이 규칙의 전부다. 같은 이름을 쓰면 기대 비용이 실현 비용 집계에
# 섞이고, 그 뒤로는 어느 쪽인지 알 수 없다.

def expected_cost_per_customer(
    *, config: CostAccountingConfig, coupon_use_rate: float, treatment_id: str
) -> MetricValue:
    """**계획값.** 기대 비용 = 메시지 단가 + 사용률 × 쿠폰 단가.

    `coupon_use_rate` 가 미확정 파라미터이므로 `unconfirmed` 다 — 값을 내되 어떤
    파라미터를 썼는지 함께 싣는다. C1 에는 실측 사용률이 없다(시뮬레이터 미가동).

    **이 값을 실현 비용 집계에 쓰지 않는다** (EC-5).
    """
    if treatment_id not in config.treatment_cost:
        return MetricValue.unavailable(
            ReasonCode.PRECONDITION_MISSING,
            f"처치 {treatment_id} 의 단가가 경제 규칙 config 에 없다 — 기대 비용을 "
            "계산할 수 없다",
            unit=Unit.KRW_PER_CUSTOMER,
            blocked_by=(
                BlockerRef(
                    BlockerKind.PARAMETER,
                    f"treatment_cost.{treatment_id}",
                    ReasonCode.PRECONDITION_MISSING,
                ),
            ),
        )
    coupon_unit = config.treatment_cost[treatment_id]
    return MetricValue.unconfirmed(
        config.message_cost_krw + coupon_use_rate * coupon_unit,
        unit=Unit.KRW_PER_CUSTOMER,
        basis=Basis(
            population=f"{treatment_id} 처치 대상 고객 1명 (계획 기준)",
            denominator_definition="고객 1명당 — 실측 집계가 아니라 계획 단가다",
            window=Window(WindowDirection.PROSPECTIVE),
            denominator=1,
        ),
        reason_detail=(
            f"쿠폰 사용률 {coupon_use_rate} 이 미확정 가정값이다 — 실측에는 "
            "시뮬레이터 실행이 필요하고 C1 에 없다"
        ),
        params_used={"coupon_use_rate": coupon_use_rate, "treatment_id": treatment_id},
    )


def realized_cost_per_customer(
    campaign: CampaignView, *, config: CostAccountingConfig
) -> MetricValue:
    """**실현값.** 실제 발생한 마케팅 비용 ÷ `N_targeted`."""
    total = marketing_cost(campaign, config=config)
    if total.status is not MetricStatus.OK:
        return MetricValue.unavailable(
            ReasonCode.BLOCKED,
            f"마케팅 비용을 계산할 수 없어 고객당 실현 비용도 계산할 수 없다 — "
            f"{total.reason_detail}",
            unit=Unit.KRW_PER_CUSTOMER,
            blocked_by=(
                BlockerRef(BlockerKind.METRIC, "marketing_cost", ReasonCode.BLOCKED),
            ),
        )
    if campaign.targeted_customers == 0:
        return MetricValue.unavailable(
            ReasonCode.NO_SOURCE_EVENT,
            "N_targeted 가 0 이라 고객당 실현 비용을 계산할 수 없다 "
            "(push_sent 이벤트 0건)",
            unit=Unit.KRW_PER_CUSTOMER,
            blocked_by=(
                BlockerRef(
                    BlockerKind.EVENT_TYPE, "push_sent", ReasonCode.NO_SOURCE_EVENT
                ),
            ),
        )
    return MetricValue.ok(
        float(total.value) / campaign.targeted_customers,  # type: ignore[arg-type]
        unit=Unit.KRW_PER_CUSTOMER,
        basis=Basis(
            population="push_sent 가 발생한 고유 고객",
            denominator_definition="N_targeted — push_sent 가 발생한 고유 고객 수",
            window=Window(WindowDirection.RETROSPECTIVE),
            denominator=campaign.targeted_customers,
            observed_count=campaign.targeted_customers,
            source_event_types=("push_sent", "coupon_use"),
        ),
    )


# ── 합성 지표 ───────────────────────────────────────────────────────────────

def marketing_cost(
    campaign: CampaignView, *, config: CostAccountingConfig
) -> MetricValue:
    """마케팅 비용 = 메시지 + 쿠폰 + 캠페인 고정비.

    구성 요소 중 하나라도 계산 불가면 합계도 계산 불가다. 계산된 것만 더하면
    **부분 합계가 전체 합계처럼 보인다** — 그것이 결손 은폐다.
    """
    parts = {
        "message_cost": message_cost(campaign, config=config),
        "coupon_cost": coupon_cost(campaign, config=config),
        "campaign_fixed_cost": campaign_fixed_cost(campaign, config=config),
    }
    return _sum_or_unavailable(
        parts,
        unit=Unit.KRW,
        population=f"캠페인 {campaign.campaign_id} 의 마케팅 비용 구성요소",
        source_event_types=("push_sent", "coupon_use"),
    )


def contribution_profit(
    orders: tuple[OrderView, ...],
    campaign: CampaignView,
    *,
    config: CostAccountingConfig,
) -> MetricValue:
    """기여이익 = 매출 − COGS − 쿠폰 − 배송보조 − 메시지 − 캠페인 고정비.

    `data_spec` §6.3 의 여섯 항목 중 **셋이 오늘 계산 불가**다:

        revenue          ← order_amount   ✅
        cogs             ← unit_cost      ❌ 스키마에 없다
        coupon_cost      ← discount       △ 규칙 유도 (D-16)
        shipping_subsidy ← 배송비          △ 규칙 유도 (D-3)
        message_cost     ← push_sent      ✅
        campaign_fixed   ← 캠페인 수       ✅

    그래서 이 함수는 C1 에서 **거의 항상 `unavailable`** 이다. `blocked_by` 가 실제
    원인을 담으므로 화면이 결손→영향 사슬을 추론하지 않는다 (DB-012).

    ★ `blocked_by` 에는 **직접 원인만** 담는다. 전이 사슬(원인의 원인)은
    `publish.py` 가 조립한다 (`ADR-0009`) — 계산층이 전체 그래프를 알면 계산층마다
    같은 그래프를 다시 만들게 된다.
    """
    cogs_total = _sum_or_unavailable(
        {order.order_id: cogs(order) for order in orders},
        unit=Unit.KRW,
        population="주문별 매출원가",
        source_event_types=("purchase",),
    ) if orders else MetricValue.unavailable(
        ReasonCode.NO_SOURCE_EVENT,
        "주문이 0건이라 매출원가를 계산할 대상이 없다 (purchase 이벤트 0건)",
        unit=Unit.KRW,
        blocked_by=(
            BlockerRef(BlockerKind.EVENT_TYPE, "purchase", ReasonCode.NO_SOURCE_EVENT),
        ),
    )

    components = {
        "revenue": revenue(orders),
        "cogs": cogs_total,
        "coupon_cost": coupon_cost(campaign, config=config),
        "shipping_subsidy": shipping_subsidy(orders, config=config),
        "message_cost": message_cost(campaign, config=config),
        "campaign_fixed_cost": campaign_fixed_cost(campaign, config=config),
    }
    unavailable = {
        name: value
        for name, value in components.items()
        if value.status is not MetricStatus.OK
    }
    if unavailable:
        return MetricValue.unavailable(
            ReasonCode.NO_COST_BASIS
            if "cogs" in unavailable
            else ReasonCode.MISSING_FIELD,
            "기여이익 구성요소 "
            f"{len(components)}개 중 {len(unavailable)}개를 계산할 수 없다 "
            f"({', '.join(sorted(unavailable))}) — 계산된 항목만 더하면 부분 합계가 "
            "전체처럼 보인다",
            unit=Unit.KRW,
            blocked_by=tuple(
                BlockerRef(BlockerKind.METRIC, name, value.reason_code or ReasonCode.BLOCKED)
                for name, value in sorted(unavailable.items())
            ),
        )
    total = (
        float(components["revenue"].value)  # type: ignore[arg-type]
        - float(components["cogs"].value)  # type: ignore[arg-type]
        - float(components["coupon_cost"].value)  # type: ignore[arg-type]
        - float(components["shipping_subsidy"].value)  # type: ignore[arg-type]
        - float(components["message_cost"].value)  # type: ignore[arg-type]
        - float(components["campaign_fixed_cost"].value)  # type: ignore[arg-type]
    )
    return MetricValue.ok(
        total,
        unit=Unit.KRW,
        basis=Basis(
            population="purchase 이벤트로 관측된 주문과 그 캠페인 비용",
            denominator_definition=_SUM_DENOMINATOR,
            window=_NO_WINDOW,
            observed_count=len(orders),
            source_event_types=("purchase", "push_sent", "coupon_use"),
        ),
        limit_note="환불을 차감하지 않는다 (A-REFUND) — 과대평가 방향의 편향이다",
    )


def ai_investment_cost(
    *, config: CostAccountingConfig, campaign_days: int
) -> MetricValue:
    """캠페인 기간에 귀속되는 AI 비용 = 월 상각액 × (기간/30).

    값 자체가 **가정 기반 추정치**다 (인건비·상각기간에 외부 출처가 없다). 그래서
    `unconfirmed` 로 낸다 — 값을 내되 그것이 확정값이 아님을 계약이 나른다.
    """
    monthly = config.ai_investment.monthly_amortized_krw()
    return MetricValue.unconfirmed(
        monthly * (campaign_days / 30),
        unit=Unit.KRW,
        basis=Basis(
            population=f"캠페인 {campaign_days}일 기간",
            denominator_definition=_SUM_DENOMINATOR,
            window=Window(WindowDirection.RETROSPECTIVE, days=campaign_days),
        ),
        reason_detail=(
            f"AI 투자 비용이 가정 기반 추정치다 — {config.ai_investment.estimate_note}"
        ),
        params_used={
            "model_development_cost_krw": (
                config.ai_investment.model_development_cost_krw
            ),
            "amortization_months": config.ai_investment.amortization_months,
            "campaign_days": campaign_days,
        },
    )


def ai_roi(
    *, incremental_profit: MetricValue, investment: MetricValue
) -> MetricValue:
    """AI ROI = (증분이익 − 투자) / 투자.

    C1 에서는 항상 계산 불가다 — 증분이익에 **두 전략의 비교**가 필요하고
    (`NEEDS_TWO_STRATEGIES`) C1 에는 전략이 없다. **그래도 정의해 둔다:**
    정의는 결과보다 먼저 있어야 하고, 나중에 급히 정의하면 결과에 맞춰 정의된다.
    """
    for name, value in (("incremental_profit", incremental_profit), ("investment", investment)):
        if value.status not in (MetricStatus.OK, MetricStatus.UNCONFIRMED):
            return MetricValue.unavailable(
                value.reason_code or ReasonCode.BLOCKED,
                f"AI ROI 의 입력 {name} 을 계산할 수 없다 — {value.reason_detail}",
                unit=Unit.RATIO,
                blocked_by=(
                    BlockerRef(
                        BlockerKind.METRIC, name, value.reason_code or ReasonCode.BLOCKED
                    ),
                ),
            )
    denominator = float(investment.value)  # type: ignore[arg-type]
    if denominator == 0:
        return MetricValue.unavailable(
            ReasonCode.NO_SOURCE_EVENT,
            "AI 투자 비용이 0 이라 ROI 의 분모가 없다",
            unit=Unit.RATIO,
            blocked_by=(
                BlockerRef(
                    BlockerKind.METRIC, "investment", ReasonCode.NO_SOURCE_EVENT
                ),
            ),
        )
    return MetricValue.unconfirmed(
        (float(incremental_profit.value) - denominator) / denominator,  # type: ignore[arg-type]
        unit=Unit.RATIO,
        basis=Basis(
            population="AI 투자 대비 증분이익",
            denominator_definition="AI 투자 비용 (원)",
            window=Window(WindowDirection.RETROSPECTIVE),
            denominator=denominator,
        ),
        reason_detail="AI 투자 비용이 가정 기반 추정치이므로 ROI 도 미확정이다",
        params_used={"investment_krw": denominator},
    )


# ── EC-7 · ROI 해석 규칙 ────────────────────────────────────────────────────

@dataclass(frozen=True, slots=True)
class StrategyOutcome:
    """`revenue_up_profit_down` 판정에 필요한 전략 하나의 결과."""

    name: str
    revenue: MetricValue
    contribution_profit: MetricValue


def revenue_up_profit_down(
    strategy: StrategyOutcome, baseline: StrategyOutcome
) -> MetricValue:
    """매출은 올랐는데 기여이익은 내려갔는가 (PRD §65 가드레일).

    ★ **`bool` 을 돌려주지 않는다.** 네 입력 중 하나라도 계산 불가면 판정도 계산
    불가다. `False` 를 돌려주면 *"가드레일 통과"* 로 읽히고, 확인하지 않은 것이
    안전하다고 보고된다 — 가드레일의 유일한 실패 양식이다.

    C1 에서는 거의 항상 `NEEDS_TWO_STRATEGIES` 다. 비교할 전략이 없다.
    """
    inputs = {
        f"{strategy.name}.revenue": strategy.revenue,
        f"{strategy.name}.contribution_profit": strategy.contribution_profit,
        f"{baseline.name}.revenue": baseline.revenue,
        f"{baseline.name}.contribution_profit": baseline.contribution_profit,
    }
    uncomputable = {
        name: value
        for name, value in inputs.items()
        if value.status not in (MetricStatus.OK, MetricStatus.UNCONFIRMED)
    }
    if uncomputable:
        return MetricValue.unavailable(
            ReasonCode.NEEDS_TWO_STRATEGIES,
            f"입력 4개 중 {len(uncomputable)}개를 계산할 수 없어 판정할 수 없다 "
            f"({', '.join(sorted(uncomputable))}) — 판정 불가를 '가드레일 통과'로 "
            "바꾸지 않는다",
            unit=Unit.TEXT,
            blocked_by=tuple(
                BlockerRef(
                    BlockerKind.METRIC, name, value.reason_code or ReasonCode.BLOCKED
                )
                for name, value in sorted(uncomputable.items())
            ),
        )
    triggered = (
        float(strategy.revenue.value) > float(baseline.revenue.value)  # type: ignore[arg-type]
        and float(strategy.contribution_profit.value)  # type: ignore[arg-type]
        < float(baseline.contribution_profit.value)  # type: ignore[arg-type]
    )
    return MetricValue.ok(
        "true" if triggered else "false",
        unit=Unit.TEXT,
        basis=Basis(
            population=f"전략 {strategy.name} 과 기준 {baseline.name} 의 비교",
            denominator_definition=_SUM_DENOMINATOR,
            window=Window(WindowDirection.RETROSPECTIVE),
            observed_count=2,
        ),
        limit_note=(
            "매출 증가와 이익 감소가 동시에 참인지만 본다 — 원인은 판정하지 않는다"
        ),
    )


# ── 내부 헬퍼 ───────────────────────────────────────────────────────────────

def _sum_or_unavailable(
    parts: dict[str, MetricValue],
    *,
    unit: Unit,
    population: str,
    source_event_types: tuple[str, ...] = (),
) -> MetricValue:
    """전부 `ok` 면 합계를, 하나라도 아니면 계산 불가를 돌려준다.

    **계산된 것만 더하지 않는다.** 부분 합계는 전체 합계와 같은 모양이라 화면에서
    구분되지 않고, 그것이 가장 조용한 결손 은폐다.

        >>> _sum_or_unavailable({}, unit=Unit.KRW, population="없음").value
        0
    """
    failed = {
        name: value for name, value in parts.items() if value.status is not MetricStatus.OK
    }
    if failed:
        first = sorted(failed)[0]
        return MetricValue.unavailable(
            failed[first].reason_code or ReasonCode.BLOCKED,
            f"구성요소 {len(parts)}개 중 {len(failed)}개를 계산할 수 없다 "
            f"({', '.join(sorted(failed))}) — 첫 사유: {failed[first].reason_detail}",
            unit=unit,
            blocked_by=tuple(
                BlockerRef(
                    BlockerKind.METRIC, name, value.reason_code or ReasonCode.BLOCKED
                )
                for name, value in sorted(failed.items())
            ),
        )
    return MetricValue.ok(
        sum(float(value.value) for value in parts.values()),  # type: ignore[arg-type]
        unit=unit,
        basis=Basis(
            population=population,
            denominator_definition=_SUM_DENOMINATOR,
            window=_NO_WINDOW,
            observed_count=len(parts),
            source_event_types=source_event_types,
        ),
    )
