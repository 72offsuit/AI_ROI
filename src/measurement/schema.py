"""이벤트 스키마 — 측정 계층의 계약 (SRS DATA-003, PRD §30-31).

실제 서비스 UI와 시뮬레이터가 **같은 스키마로 같은 Sink에 기록**한다.
어떤 필드를 통과시킬지 판단하는 기준은 하나다:

    실제 커머스 서비스에서 로그로 남을 수 있는가?

남을 수 없는 것(Hidden Trait, 처치 효과 τ, Potential Outcome, persona 라벨)은
이 계층을 통과하지 않는다. `FORBIDDEN_FIELD_NAMES` 참조.

표준 라이브러리만 사용한다:
  - 의존성 매니페스트가 아직 없고 CI에 설치 단계가 없다 (SRS ISO-005)
  - `src.measurement` 는 아무것도 import 하지 않는다 (SRS ISO-002)
pyarrow / pydantic 스키마로의 변환은 [M-2] Event Sink 에서 어댑터로 추가한다.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum

# ── 전역 규약 ───────────────────────────────────────────────────────────────

SCHEMA_VERSION = "event-schema-v1.0-draft"
"""GATE 1에서 `event-schema-v1.0` 으로 Lock한다 (PRD §22, SRS FREEZE-001).
Lock 이후 변경하면 이미 생성된 데이터와 학습 결과가 전부 무효가 된다."""

TIMEZONE = "Asia/Seoul"
"""모든 timestamp는 KST 단일 타임존이다. UTC 혼재를 허용하지 않는다."""

TIMESTAMP_PRECISION = "milliseconds"
"""ISO 8601 + offset, 밀리초 정밀도. 예: 2025-10-01T09:00:00.000+09:00"""

SESSION_TIMEOUT_MINUTES = 30
"""무활동 30분이면 세션이 만료된다. 다음 활동은 새 session_id를 받는다."""


# ── 이벤트 종류 ─────────────────────────────────────────────────────────────

class EventType(str, Enum):
    """관측 가능한 원본 이벤트 16종 (PRD §30.1, SRS SIM-006 최소 8종 상회)."""

    # 세션·탐색
    SESSION_START = "session_start"
    PAGE_VIEW = "page_view"
    SEARCH = "search"
    PRODUCT_VIEW = "product_view"
    RETURN_VISIT = "return_visit"
    # 구매 퍼널
    ADD_TO_CART = "add_to_cart"
    REMOVE_FROM_CART = "remove_from_cart"
    CHECKOUT_START = "checkout_start"
    PURCHASE = "purchase"
    # 마케팅
    CAMPAIGN_EXPOSED = "campaign_exposed"
    PUSH_SENT = "push_sent"
    COUPON_EXPOSED = "coupon_exposed"
    COUPON_CLICKED = "coupon_clicked"
    COUPON_USE = "coupon_use"
    # 부수
    REVIEW = "review"
    CS_CONTACT = "cs_contact"


class DerivedStateType(str, Enum):
    """파생 상태 이벤트 (PRD §30.2).

    기록은 하되 **학습 Feature로 사용하지 않는다** — 라벨과 동어반복이 된다
    (SRS NFR-002, docs/data_spec.html §5 · §8). 대시보드 표시와 코호트 분석 전용.
    """

    INACTIVE = "inactive"
    AT_RISK = "at_risk"
    CHURN = "churn"


FEATURE_FORBIDDEN_EVENT_TYPES = frozenset(e.value for e in DerivedStateType)
"""Feature 계산에 사용해서는 안 되는 event_type."""


# ── 필드 정의 ───────────────────────────────────────────────────────────────

class FieldGroup(str, Enum):
    CORE = "core"
    SESSION = "session"
    PRODUCT = "product"
    ORDER = "order"
    MARKETING = "marketing"
    META = "meta"


@dataclass(frozen=True, slots=True)
class FieldSpec:
    name: str
    dtype: str
    group: FieldGroup
    description: str


EVENT_FIELDS: tuple[FieldSpec, ...] = (
    # Core — 모든 이벤트에 필수
    FieldSpec("event_id", "string", FieldGroup.CORE, "이벤트 고유 ID (UUID4)"),
    FieldSpec("customer_id", "string", FieldGroup.CORE, "고객 ID"),
    FieldSpec("timestamp", "datetime[ms]", FieldGroup.CORE, "발생 시각 (KST)"),
    FieldSpec("event_type", "category", FieldGroup.CORE, "EventType 16종"),
    # Session
    FieldSpec("session_id", "string", FieldGroup.SESSION, "세션 식별자"),
    FieldSpec("session_duration", "int", FieldGroup.SESSION,
              "세션 체류시간(초). 세션의 **마지막 이벤트에만** 기록한다"),
    FieldSpec("page_type", "category", FieldGroup.SESSION,
              "home / list / search / detail / cart / checkout / complete / history"),
    # Product
    FieldSpec("product_id", "string", FieldGroup.PRODUCT, "상품 ID"),
    FieldSpec("category", "category", FieldGroup.PRODUCT, "상품 카테고리 5종"),
    FieldSpec("quantity", "int", FieldGroup.PRODUCT, "수량 (1 이상)"),
    FieldSpec("unit_price", "int", FieldGroup.PRODUCT, "단가 (원, 0 이상)"),
    # Order
    FieldSpec("order_id", "string", FieldGroup.ORDER, "주문 ID"),
    FieldSpec("order_amount", "int", FieldGroup.ORDER,
              "주문 금액(원) = Σ(unit_price × quantity) − discount"),
    # Marketing
    FieldSpec("coupon_id", "string", FieldGroup.MARKETING, "쿠폰 ID"),
    FieldSpec("campaign_id", "string", FieldGroup.MARKETING, "캠페인 ID"),
    FieldSpec("treatment_id", "string", FieldGroup.MARKETING, "처치 ID (T0~T4)"),
    FieldSpec("treatment_group", "category", FieldGroup.MARKETING,
              "control / treatment. **Feature 사용 금지** (SRS NFR-002)"),
    FieldSpec("experiment_id", "string", FieldGroup.MARKETING,
              "실험 ID. **Feature 사용 금지**"),
    # Meta — 모든 이벤트에 필수 (재현성, SRS NFR-001 · SIM-011)
    FieldSpec("service_version", "string", FieldGroup.META, "서비스 버전"),
    FieldSpec("customer_version", "string", FieldGroup.META, "고객 정의 버전"),
    FieldSpec("simulator_version", "string", FieldGroup.META,
              "시뮬레이터 버전. 서비스 UI 기록 시에는 null"),
    FieldSpec("random_seed", "int", FieldGroup.META,
              "생성 seed. 서비스 UI 기록 시에는 null"),
)

FIELD_INDEX: dict[str, FieldSpec] = {f.name: f for f in EVENT_FIELDS}

CORE_FIELDS = frozenset(f.name for f in EVENT_FIELDS if f.group is FieldGroup.CORE)
META_FIELDS = frozenset(f.name for f in EVENT_FIELDS if f.group is FieldGroup.META)

FEATURE_FORBIDDEN_FIELDS = frozenset({
    "treatment_group", "treatment_id", "experiment_id",
})
"""배정 정보는 기록하되 Feature에 넣지 않는다 (docs/data_spec.html §8)."""

FORBIDDEN_FIELD_NAMES = frozenset({
    # Hidden Trait (PRD §18) — 실제 서비스에서 알 수 없는 값
    "base_visit_frequency", "base_purchase_probability", "purchase_cycle",
    "price_sensitivity", "coupon_sensitivity", "shipping_fee_sensitivity",
    "brand_loyalty", "marketing_responsiveness", "marketing_fatigue",
    "base_churn_propensity", "cart_abandonment_propensity",
    "search_propensity", "review_propensity", "cs_contact_propensity",
    # 생성용 라벨과 정답
    "persona", "tau", "true_tau", "true_uplift",
    "y_control", "y_treatment", "quadrant",
})
"""이 계층을 통과해서는 안 되는 필드 이름 (SRS ISO-003, PRD §21).
`tests/test_schema.py` 가 스키마에 이 이름이 없는지 검사한다."""


# ── 이벤트별 필수 / 선택 필드 ───────────────────────────────────────────────

class Requirement(str, Enum):
    REQUIRED = "required"
    OPTIONAL = "optional"
    NOT_APPLICABLE = "n/a"


_R = Requirement

# (필수 필드, 선택 필드). Core·Meta 는 전 이벤트 공통이므로 생략한다.
# 여기 없는 필드는 자동으로 NOT_APPLICABLE 이 된다.
_EVENT_RULES: dict[EventType, tuple[frozenset[str], frozenset[str]]] = {
    EventType.SESSION_START: (
        frozenset({"session_id", "page_type"}),
        frozenset({"session_duration"}),
    ),
    EventType.PAGE_VIEW: (
        frozenset({"session_id", "page_type"}),
        frozenset({"product_id", "category", "session_duration"}),
    ),
    EventType.SEARCH: (
        frozenset({"session_id", "page_type"}),
        frozenset({"category", "session_duration"}),
    ),
    EventType.PRODUCT_VIEW: (
        frozenset({"session_id", "page_type", "product_id", "category"}),
        frozenset({"unit_price", "session_duration"}),
    ),
    EventType.RETURN_VISIT: (
        frozenset({"session_id", "page_type"}),
        frozenset({"session_duration"}),
    ),
    EventType.ADD_TO_CART: (
        frozenset({"session_id", "page_type", "product_id", "category",
                   "quantity", "unit_price"}),
        frozenset({"session_duration"}),
    ),
    EventType.REMOVE_FROM_CART: (
        frozenset({"session_id", "page_type", "product_id", "category",
                   "quantity", "unit_price"}),
        frozenset({"session_duration"}),
    ),
    EventType.CHECKOUT_START: (
        frozenset({"session_id", "page_type", "order_id", "order_amount"}),
        frozenset({"coupon_id", "session_duration"}),
    ),
    EventType.PURCHASE: (
        frozenset({"session_id", "page_type", "order_id", "order_amount"}),
        frozenset({"coupon_id", "campaign_id", "session_duration"}),
    ),
    EventType.CAMPAIGN_EXPOSED: (
        frozenset({"campaign_id"}),
        frozenset({"session_id", "coupon_id", "page_type"}),
    ),
    EventType.PUSH_SENT: (
        frozenset({"campaign_id"}),
        frozenset({"coupon_id"}),
    ),
    EventType.COUPON_EXPOSED: (
        frozenset({"coupon_id", "campaign_id"}),
        frozenset({"session_id", "page_type"}),
    ),
    EventType.COUPON_CLICKED: (
        frozenset({"coupon_id", "campaign_id", "session_id"}),
        frozenset({"page_type", "session_duration"}),
    ),
    EventType.COUPON_USE: (
        frozenset({"coupon_id", "campaign_id", "session_id",
                   "order_id", "order_amount"}),
        frozenset({"page_type", "session_duration"}),
    ),
    EventType.REVIEW: (
        frozenset({"session_id", "product_id", "category"}),
        frozenset({"order_id", "page_type", "session_duration"}),
    ),
    EventType.CS_CONTACT: (
        frozenset({"customer_id"}),
        frozenset({"session_id", "order_id", "product_id", "category",
                   "page_type"}),
    ),
}

# 배정 정보는 실험 기간 중 모든 이벤트에 선택적으로 붙는다.
_ASSIGNMENT_OPTIONAL = frozenset({"treatment_id", "treatment_group", "experiment_id"})


def requirement(event_type: EventType, field_name: str) -> Requirement:
    """이 이벤트에서 해당 필드가 필수인지 선택인지 해당 없는지."""
    if field_name not in FIELD_INDEX:
        raise KeyError(f"스키마에 없는 필드: {field_name}")
    if field_name in CORE_FIELDS or field_name in META_FIELDS:
        return _R.REQUIRED if field_name in CORE_FIELDS else _R.OPTIONAL
    required, optional = _EVENT_RULES[event_type]
    if field_name in required:
        return _R.REQUIRED
    if field_name in optional or field_name in _ASSIGNMENT_OPTIONAL:
        return _R.OPTIONAL
    return _R.NOT_APPLICABLE


def required_fields(event_type: EventType) -> frozenset[str]:
    return CORE_FIELDS | _EVENT_RULES[event_type][0]


def validate_event(record: dict[str, object]) -> list[str]:
    """이벤트 한 건을 검사하고 위반 목록을 돌려준다. 빈 리스트면 통과.

    Event Sink([M-2])와 데이터 품질 검증([M-6])이 이 함수를 쓴다.
    """
    problems: list[str] = []

    raw_type = record.get("event_type")
    try:
        event_type = EventType(raw_type)
    except ValueError:
        return [f"알 수 없는 event_type: {raw_type!r}"]

    unknown = set(record) - set(FIELD_INDEX)
    if unknown:
        problems.append(f"스키마에 없는 필드: {sorted(unknown)}")
    leaked = set(record) & FORBIDDEN_FIELD_NAMES
    if leaked:
        problems.append(f"측정 계층을 통과할 수 없는 필드: {sorted(leaked)}")

    for name in sorted(required_fields(event_type)):
        if record.get(name) is None:
            problems.append(f"{event_type.value}: 필수 필드 누락 — {name}")

    for name, value in record.items():
        if value is None or name not in FIELD_INDEX:
            continue
        if requirement(event_type, name) is _R.NOT_APPLICABLE:
            problems.append(f"{event_type.value}: 해당 없는 필드에 값이 있음 — {name}")

    for name in ("quantity", "unit_price", "order_amount", "session_duration"):
        value = record.get(name)
        if isinstance(value, int) and value < 0:
            problems.append(f"{name} 은 0 이상이어야 한다 (발견: {value})")

    return problems


# ── 식별자 규칙 ─────────────────────────────────────────────────────────────

IDENTIFIER_PATTERNS: dict[str, str] = {
    "event_id": r"^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$",
    "customer_id": r"^C\d{8}$",
    "session_id": r"^S-C\d{8}-\d{13}$",
    "order_id": r"^O\d{8}-\d{6}$",
    "product_id": r"^P\d{4}$",
    "coupon_id": r"^CPN-[A-Z0-9]{6}$",
    "campaign_id": r"^CMP-\d{8}-\d{3}$",
    "treatment_id": r"^T[0-4]$",
    "experiment_id": r"^EXP-\d{8}-\d{2}$",
}
"""식별자 형식. `session_id` 는 `S-{customer_id}-{세션 시작 epoch ms}` 이며
무활동 `SESSION_TIMEOUT_MINUTES` 분이면 만료되고 새 id를 받는다."""


def check_identifier(field_name: str, value: str) -> bool:
    pattern = IDENTIFIER_PATTERNS.get(field_name)
    return True if pattern is None else bool(re.fullmatch(pattern, value))


# ── PRD §21 Observable 지표 ↔ 이벤트 매핑 ───────────────────────────────────

OBSERVABLE_METRIC_SOURCES: dict[str, tuple[str, ...]] = {
    "last_visit_date": ("session_start", "return_visit"),
    "last_purchase_date": ("purchase",),
    "visit_count": ("session_start", "return_visit"),
    "purchase_count": ("purchase",),
    "purchase_interval": ("purchase",),
    "average_order_value": ("purchase",),
    "cumulative_revenue": ("purchase",),
    "cart_abandonment_count": ("add_to_cart", "checkout_start", "purchase"),
    "coupon_exposure_count": ("coupon_exposed",),
    "coupon_usage_count": ("coupon_use",),
    "campaign_response_count": ("campaign_exposed", "coupon_clicked", "purchase"),
    "session_duration": ("session_start", "page_view", "product_view"),
    "page_views": ("page_view",),
    "search_count": ("search",),
    "cs_contact_count": ("cs_contact",),
    "review_count": ("review",),
}
"""PRD §21이 AI 입력으로 허용한 Observable 16개 지표를 어떤 이벤트로 계산하는지.
`tests/test_schema.py` 가 16개 전부 계산 가능한지 검사한다."""
