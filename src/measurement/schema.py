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
from typing import Mapping

# ── 전역 규약 ───────────────────────────────────────────────────────────────

SCHEMA_VERSION = "event-schema-v1.0-draft"
"""GATE 1에서 `event-schema-v1.0` 으로 Lock한다 (PRD §22, SRS FREEZE-001).
Lock 이후 변경하면 이미 생성된 데이터와 학습 결과가 전부 무효가 된다."""

TIMEZONE = "Asia/Seoul"
"""저장되는 모든 timestamp는 KST 단일 타임존이다.

Policy (decided in M-01/#53 D1-3, option ⑵+b — this is the enforced behaviour, not
an aspiration):

    입력   어떤 오프셋이든 받는다 (`+09:00` · `Z` · `-05:00` 모두 통과)
    거부   오프셋이 없는 timestamp — 순간을 특정할 수 없으므로 추측하지 않는다
    저장   `EventSink` 가 KST 표기로 정규화해 쓴다 (`sink.py _normalize_timestamp`)

왜 UTC 를 거부하지 않는가: `Ecommerce_Service` 가 UTC 로 기록하고 있고
(`src/lib/server/commerce/orders.ts`), 전량 거부하면 MEA-003(부분 소스 관용)과 충돌한다.
왜 저장 시 정규화하는가: 원문을 그대로 두면 저장된 값은 UTC 인데 파티션 날짜는 KST 가
되어 `DQ-06`("모든 시각이 KST 단일")이 **자기 저장물에 대해** 실패한다.

★ `validate_event()` 는 오프셋의 유무만 본다. **파싱 가능성은 검사하지 않는다** —
`_partition_key` 가 계속 던져야 하기 때문이다. `validate_event` 참조."""

TIMESTAMP_PRECISION = "milliseconds"
"""ISO 8601 + offset, 밀리초 정밀도. 예: 2025-10-01T09:00:00.000+09:00"""

_TIMESTAMP_WITH_OFFSET = re.compile(
    r"^\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:?\d{2})$"
)
_TIMESTAMP_WITHOUT_OFFSET = re.compile(
    r"^\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}(?::\d{2})?(?:\.\d+)?$"
)
"""ISO 8601 모양을 먼저 알아보고 **그런 다음** 오프셋을 요구하는 두 패턴.

한 패턴으로 "오프셋이 붙은 ISO 8601 이어야 한다"를 강제하면 `"어제"` 같은 아무 문자열도
위반으로 걸린다. 그러면 그 레코드가 수집 시점에 거부되어 `_buffer` 에 들어가지 않고,
`flush()` 가 아무 예외도 던지지 않아 `tests/test_sink.py` 의
`test_unparsable_timestamp_is_reported`(스키마를 통과해도 파티션 키를 못 만들면 조용히
넘기지 않는다)가 깨진다.

그래서 판정은 셋으로 나뉜다:
  - `_TIMESTAMP_WITH_OFFSET` 일치     → 통과
  - `_TIMESTAMP_WITHOUT_OFFSET` 일치  → 오프셋 누락으로 보고
  - 둘 다 불일치                       → **타임존 문제가 아니다.** 아무것도 보고하지 않고
                                        `sink._normalize_timestamp` 가 던지게 둔다"""

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


class Category(str, Enum):
    """상품 카테고리 5종. 영문 코드가 정본이다 (M-02/#54 가 확정).

    3자 불일치를 이렇게 정리했다:
      - SRS `COM-001` (`Plan/…SRS_v2.0.md:434-444`) — 영문 코드. **정본**
      - `docs/data_spec.html` §6.1 — 신선식품·간편식·유제품·음료·생활용품.
        표 가독성을 위한 **표기**로 보고, 값으로 쓰지 않는다
      - `src/measurement/schema.py` — 열거가 없었다. 그래서 `"신선식품"` 과
        `"fresh_food"` 가 **양쪽 테스트에서 동시에 통과**하고 있었다

    영문을 고른 이유 둘: `data_spec` §8 의 CLV Feature 이름이 영문이고
    (`category_share_fresh`), `config/economic_config.yaml` 의 카테고리 키가 같은
    어휘를 써야 한다.

    **표시명 매핑은 UI 책임이다.** 측정 계층은 코드만 안다 — 창구가 표시 어휘를
    알면 화면을 따라 계약이 흔들린다.
    """

    FRESH_FOOD = "fresh_food"
    MEAL_SOLUTION = "meal_solution"
    DAIRY = "dairy"
    BEVERAGE = "beverage"
    HOUSEHOLD = "household"


class PageType(str, Enum):
    """페이지 유형 8종.

    `EVENT_FIELDS` 의 `page_type` 설명 문자열이 유일한 출처였고, 다른 문서에 8종
    열거가 없다. 그 문자열을 그대로 정본으로 승격한다.
    """

    HOME = "home"
    LIST = "list"
    SEARCH = "search"
    DETAIL = "detail"
    CART = "cart"
    CHECKOUT = "checkout"
    COMPLETE = "complete"
    HISTORY = "history"


_CATEGORICAL_VALUES: dict[str, frozenset[str]] = {
    "category": frozenset(item.value for item in Category),
    "page_type": frozenset(item.value for item in PageType),
}
"""값 수준 강제 대상. `validate_event()` 가 **값이 있는 필드에만** 적용한다.

`treatment_group`(`control`/`treatment`)도 같은 종류의 열거 공백이지만 `#54` 수용
기준이 `category`·`page_type` 둘만 지목했으므로 넣지 않았다. 남은 공백으로
`.agent-team/08-impl-notes/backend.md` 에 기록했다."""


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

    ★ **출처를 모른다. 계속 모르게 둔다.** `if source == COMMERCE: skip` 같은 분기를
    넣으면 창구가 한쪽 편을 드는 것이 된다 — 계약은 하나고 맞추는 쪽이 소스다.
    커머스 실측분이 형식 위반으로 전량 거부되는 문제는 `EventSink(strict=False)`
    관용 모드가 받는다. 계약을 느슨하게 해서 받지 않는다.

    **결손과 형식 위반을 섞지 않는다.** 값이 `None` 인 것은 결손이고 필수 필드 검사만
    본다. 허용값·식별자·타임존 검사는 **값이 있는 필드에만** 적용한다.
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
        allowed = _CATEGORICAL_VALUES.get(name)
        if allowed is not None and value not in allowed:
            problems.append(
                f"{name} 허용값이 아니다 — {value!r} (허용: {sorted(allowed)})"
            )
        if isinstance(value, str) and not check_identifier(name, value):
            problems.append(
                f"{name} 식별자 형식 위반 — {value!r} "
                f"(기대: {IDENTIFIER_PATTERNS[name]})"
            )

    problems.extend(_timestamp_problems(record.get("timestamp")))

    for name in ("quantity", "unit_price", "order_amount", "session_duration"):
        value = record.get(name)
        if isinstance(value, int) and value < 0:
            problems.append(f"{name} 은 0 이상이어야 한다 (발견: {value})")

    return problems


def _timestamp_problems(timestamp: object) -> list[str]:
    """오프셋의 유무만 판정한다. **파싱 가능성은 판정하지 않는다.**

    세 경우로 갈린다 — 왜 이렇게 좁은지는 `TIMEZONE` 독트링과
    `_TIMESTAMP_WITHOUT_OFFSET` 주석에 있다.

        "2025-10-01T09:00:00.000+09:00"  → []            통과
        "2025-10-01T23:30:00.000Z"       → []            통과 (Sink 가 KST 로 정규화)
        "2025-10-01T23:30:00"            → ["…오프셋…"]  거부
        "어제"                            → []            여기서는 통과. flush() 가 던진다
    """
    if not isinstance(timestamp, str):
        return []  # datetime 객체는 tzinfo 로 판정한다 — sink._normalize_timestamp 의 몫
    if _TIMESTAMP_WITH_OFFSET.fullmatch(timestamp):
        return []
    if _TIMESTAMP_WITHOUT_OFFSET.fullmatch(timestamp):
        return [
            f"timestamp 에 UTC 오프셋이 없다 — {timestamp!r}. "
            f"순간을 특정할 수 없으므로 오프셋을 붙여 기록한다 (예: +09:00)"
        ]
    return []


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


# ── 게시물 어휘 — 지표 상태와 사유 코드 ─────────────────────────────────────
#
# `kpi.py` 와 `economics.py` 가 둘 다 이 어휘를 쓴다. 한쪽에 두면 다른 쪽이 그쪽을
# import 해야 하고 계산층 사이에 불필요한 의존이 생긴다. `schema.py` 는 이미 계약
# 어휘의 정본이고 아무것도 import 하지 않으므로 순환이 생길 수 없다 (결정 D-18).
#
# ★ 값 문자열은 `.agent-team/04-architecture/schemas/common.schema.json` 과
#   **문자 단위로** 같아야 한다. `tests/test_schema.py TestContractVocabulary` 가
#   계약 파일을 읽어 대조하므로, 계약이 바뀌면 테스트가 실패로 알려준다.

class MetricStatus(str, Enum):
    """지표 하나의 상태 5종 — `common.schema.json#/$defs/metric_value.properties.status`.

    `unavailable` 과 `not_run` 의 차이가 이 프로젝트의 요점이다:
    전자는 "계산하려 했으나 근거가 없다", 후자는 "계산을 시도하지 않았다".
    둘을 합치면 관측하지 않은 것을 관측했다고 말하게 된다.
    """

    OK = "ok"
    UNCONFIRMED = "unconfirmed"
    UNAVAILABLE = "unavailable"
    BLOCKED = "blocked"
    NOT_RUN = "not_run"


class ReasonCode(str, Enum):
    """계산 불가·미확정 사유 9종 — `common.schema.json#/$defs/reason_code`.

    기획 문서(`kpi-definition-v1.md` §2.4)는 7종을 적었고 계약은 9종이다
    (`NOT_RUN` · `PRECONDITION_MISSING` 추가). **계약이 정본이다** — 계약은 위반을
    거부하고 문서는 어긋나도 아무것도 실패하지 않는다.

    대소문자가 `MetricStatus` 와 섞이는 것은 오타가 아니다. 계약이
    `status` 는 소문자, `reason_code` 는 대문자로 정의한다.
    """

    NO_SOURCE_EVENT = "NO_SOURCE_EVENT"
    MISSING_FIELD = "MISSING_FIELD"
    NO_COST_BASIS = "NO_COST_BASIS"
    NEEDS_TWO_STRATEGIES = "NEEDS_TWO_STRATEGIES"
    NEEDS_MODEL_OUTPUT = "NEEDS_MODEL_OUTPUT"
    PARAM_UNCONFIRMED = "PARAM_UNCONFIRMED"
    BLOCKED = "BLOCKED"
    NOT_RUN = "NOT_RUN"
    PRECONDITION_MISSING = "PRECONDITION_MISSING"


class Unit(str, Enum):
    """지표 단위 8종 — `common.schema.json#/$defs/unit`.

    장식이 아니라 **필수 입력**이다. `contracts.py` 가 `(status, unit, value)` 만으로
    `value_formatted` 를 만들기 때문에, `unit` 이 없으면 그 함수가 성립하지 않는다.
    """

    COUNT = "count"
    KRW = "krw"
    KRW_PER_CUSTOMER = "krw_per_customer"
    RATIO = "ratio"
    DAYS = "days"
    PERCENTAGE_POINT = "percentage_point"
    TEXT = "text"
    DATETIME = "datetime"


class BlockerKind(str, Enum):
    """원인의 종류 9종 — `common.schema.json#/$defs/blocker_ref.properties.kind`.

    `field`(22컬럼 중 하나가 비었다)와 `schema_gap`(계산식이 요구하는 컬럼이 스키마에
    아예 없다)을 구분하는 것이 요점이다. 전자는 데이터를 더 모으면 풀리고 후자는
    스키마를 바꿔야 풀린다 — 화면이 그 차이를 보여줄 수 있어야 한다.
    """

    FIELD = "field"
    SCHEMA_GAP = "schema_gap"
    EVENT_TYPE = "event_type"
    METRIC = "metric"
    TABLE = "table"
    MODEL_OUTPUT = "model_output"
    STRATEGY = "strategy"
    PARAMETER = "parameter"
    DEPENDENCY = "dependency"


class WindowDirection(str, Enum):
    """관측 창의 방향 — `basis.window.direction`.

    `R-2` 가 요구하는 구분이다: 기준일 D **이후**를 보는 지표와 D **이전**을 보는
    지표를 같은 이름으로 쓰지 않는다.
    """

    RETROSPECTIVE = "retrospective"
    PROSPECTIVE = "prospective"
    POINT_IN_TIME = "point_in_time"
    NONE = "none"


@dataclass(frozen=True, slots=True)
class Window:
    direction: WindowDirection
    days: int | None = None
    label: str | None = None

    def __post_init__(self) -> None:
        if self.days is not None and self.days < 1:
            raise ValueError(f"window.days 는 1 이상이어야 한다 (받음: {self.days})")


@dataclass(frozen=True, slots=True)
class Basis:
    """이 값이 **무엇을 세어** 나온 값인가 — `common.schema.json#/$defs/basis`.

    ★ **기준의 유무가 "측정된 0"과 "값 없음"을 가른다.** 계산된 값에는 반드시 있고,
    계산 불가에는 있을 수 없다. 화면은 글리프가 아니라 이 객체의 존재로 두 상태를
    판별한다 — 그래서 `MetricValue.__post_init__` 이 양방향으로 강제한다.

    `population` 에 "고객"이라고만 쓰지 않는다 (`R-4`). `P_buyer(D)` 처럼 누가
    모집단인지 특정한다. 합계·건수 지표는 `denominator=None` +
    `denominator_definition="분모 없음 (합계)"` 로 적는다 — 분모가 없다는 사실도
    기록되어야 한다.
    """

    population: str
    denominator_definition: str
    window: Window
    denominator: float | None = None
    observed_count: int | None = None
    excluded_count: int | None = None
    excluded_reason: str | None = None
    source_event_types: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        # 계약이 minLength 1 을 건다. 빈 문자열은 "적었다"가 아니라 "안 적었다"다.
        if not self.population.strip():
            raise ValueError("basis.population 이 비었다 — 모집단을 특정해 적는다 (R-4)")
        if not self.denominator_definition.strip():
            raise ValueError(
                "basis.denominator_definition 이 비었다 — 분모가 없으면 "
                "'분모 없음 (합계)' 라고 적는다"
            )
        if self.observed_count is not None and self.observed_count < 0:
            raise ValueError(f"basis.observed_count 가 음수다: {self.observed_count}")
        if self.excluded_count is not None and self.excluded_count < 0:
            raise ValueError(f"basis.excluded_count 가 음수다: {self.excluded_count}")
        # R-6 — 제외를 조용히 하지 않는다. 제외했으면 왜 제외했는지 함께 있어야 한다.
        if self.excluded_count and not (self.excluded_reason or "").strip():
            raise ValueError(
                f"basis.excluded_count={self.excluded_count} 인데 excluded_reason 이 없다 — "
                "제외를 조용히 하지 않는다 (R-6)"
            )


@dataclass(frozen=True, slots=True)
class BlockerRef:
    """이 지표를 계산할 수 없게 만든 원인 하나 — `common.schema.json#/$defs/blocker_ref`.

    화면이 결손→영향 사슬을 **추론하지 않게** 한다 (`DB-012`). 추론하게 두면 화면이
    계산 규칙을 알아야 하고, 그러면 규칙이 두 곳에 살면서 갈라진다.
    """

    kind: BlockerKind
    ref: str
    reason_code: ReasonCode

    def __post_init__(self) -> None:
        if not self.ref.strip():
            raise ValueError("blocker_ref.ref 가 비었다 — 원인의 식별자를 적는다")


_COMPUTED_STATUSES = frozenset({MetricStatus.OK, MetricStatus.UNCONFIRMED})
_UNCOMPUTED_STATUSES = frozenset(
    {MetricStatus.UNAVAILABLE, MetricStatus.BLOCKED, MetricStatus.NOT_RUN}
)


@dataclass(frozen=True, slots=True)
class MetricValue:
    """지표 하나의 값 **또는** 계산 불가 상태 — `common.schema.json#/$defs/metric_value`.

    ★ **USP-1 의 기계 표현이다.** `float` 를 돌려주는 계산 함수를 두지 않는 이유가
    이것이다 — 반환 타입에 `0.0` 을 돌려줄 자리가 없으면 결손이 0 으로 채워질 수 없다.

    `__post_init__` 이 계약의 불변식을 **생성 시점에** 강제한다. 잘못된
    `MetricValue` 를 만들 수 있으면 그것이 게시 시점까지 살아남고, 그때 터지는
    예외는 원인에서 멀리 떨어진 자리에서 터진다. 계산한 사람이 `unit` 과 `basis` 를
    아는 유일한 사람이고, 첫 자리에서 잡는 것이 가장 싸다.

    **`value_formatted` 는 여기 없다.** `contracts.py` 가 직렬화 시점에
    `(status, unit, value)` 로 만든다 — 호출자마다 포맷하면 한 곳만 빠뜨려도 화면이
    `undefined` 를 받고 그 자리에 `?? 0` 이 생긴다. `limit_note` 는 반대로 필드다:
    `unit` 에서 유도할 수 없는, 그 지표를 계산한 사람만 아는 사실이기 때문이다.

        >>> MetricValue.unavailable(ReasonCode.NO_COST_BASIS, "주문 12건 전부 unit_cost 없음").value is None
        True
    """

    status: MetricStatus
    value: float | str | None = None
    unit: Unit | None = None
    basis: Basis | None = None
    reason_code: ReasonCode | None = None
    reason_detail: str | None = None
    blocked_by: tuple[BlockerRef, ...] = ()
    derived: bool = False
    derivation: str | None = None
    params_used: Mapping[str, object] | None = None
    ci95: tuple[float, float] | None = None
    limit_note: str | None = None
    """정밀도 한계 한 줄. 예: "쿠폰 사용 이벤트만 센다 — 노출 후 미사용은 세지 않는다".

    화면의 `한계` 칩이 이 값을 읽는다. 계약에는 없는 확장 필드이므로
    `contracts.py` 가 게시 형식으로 옮길 때 계약의 `additionalProperties: false` 를
    어기지 않도록 처리한다."""

    def __post_init__(self) -> None:
        if self.status in _COMPUTED_STATUSES:
            self._check_computed()
        elif self.status in _UNCOMPUTED_STATUSES:
            self._check_uncomputed()
        else:  # pragma: no cover - MetricStatus 가 5종이라 도달할 수 없다
            raise ValueError(f"알 수 없는 status: {self.status!r}")

        # derived → derivation 필수. 유도값이 저장된 사실처럼 보이면 안 된다.
        if self.derived and not (self.derivation or "").strip():
            raise ValueError(
                "derived=True 인데 derivation 이 없다 — 규칙에서 유도한 값은 "
                "그 계산식을 함께 싣는다 (저장된 사실과 구분되어야 한다)"
            )

    def _check_computed(self) -> None:
        """`ok`·`unconfirmed` — 값·단위·기준이 있고, 없으면 만들 수 없게 막는다."""
        if self.value is None:
            raise ValueError(
                f"status={self.status.value} 인데 value 가 None 이다 — "
                "계산했다면 값이 있어야 하고, 없다면 unavailable 이다"
            )
        if self.unit is None:
            raise ValueError(
                f"status={self.status.value} 인데 unit 이 없다 — unit 은 표시용 장식이 "
                "아니라 value_formatted 의 필수 입력이다"
            )
        if self.basis is None:
            raise ValueError(
                f"status={self.status.value} 인데 basis 가 없다 — 기준의 유무가 "
                "'측정된 0'과 '값 없음'을 가른다"
            )
        if self.status is MetricStatus.OK and self.reason_code is not None:
            raise ValueError(
                f"status=ok 인데 reason_code={self.reason_code.value} 가 있다 — "
                "계산된 값에는 계산 불가 사유가 붙지 않는다"
            )
        if self.status is MetricStatus.UNCONFIRMED:
            if self.reason_code is not ReasonCode.PARAM_UNCONFIRMED:
                raise ValueError(
                    "status=unconfirmed 는 reason_code=PARAM_UNCONFIRMED 여야 한다 "
                    f"(받음: {self.reason_code})"
                )
            if not (self.reason_detail or "").strip():
                raise ValueError("status=unconfirmed 인데 reason_detail 이 없다")
            if not self.params_used:
                raise ValueError(
                    "status=unconfirmed 인데 params_used 가 비었다 — 어떤 미확정 "
                    "파라미터를 썼는지 밝히지 않으면 값을 믿을 근거가 없다 (R-10)"
                )
        # 비율 지표는 분모를 함께 낸다. 분모 없는 비율은 검산할 수 없다.
        if self.unit is Unit.RATIO and self.basis.denominator is None:
            raise ValueError(
                "unit=ratio 인데 basis.denominator 가 없다 — 비율은 분모를 함께 낸다"
            )
        # ★ 0/0 을 0 으로 표시하는 경로를 막는다. 분모가 0 이면 "측정된 0"이 아니다.
        if self.status is MetricStatus.OK and self.basis.denominator == 0:
            raise ValueError(
                "basis.denominator=0 인데 status=ok 다 — 분모가 0 이면 계산된 것이 "
                "아니다. unavailable 로 내고 사유를 적는다"
            )

    def _check_uncomputed(self) -> None:
        """`unavailable`·`blocked`·`not_run` — `value` 는 반드시 `None`, `basis` 는 금지."""
        if self.value is not None:
            raise ValueError(
                f"status={self.status.value} 인데 value={self.value!r} 가 있다 — "
                "계산 불가에 0 이나 추정값을 넣지 않는다"
            )
        if self.basis is not None:
            raise ValueError(
                f"status={self.status.value} 인데 basis 가 있다 — 계산 불가는 "
                "기준을 가질 수 없다. 그 유무가 '측정된 0'과 구분되는 지점이다"
            )
        if self.reason_code is None:
            raise ValueError(f"status={self.status.value} 인데 reason_code 가 없다")
        if not (self.reason_detail or "").strip():
            raise ValueError(
                f"status={self.status.value} 인데 reason_detail 이 없다 — 화면의 둘째 "
                "줄이다. 근거 수치를 담는다 (예: '주문 1,204건 중 1,204건에 unit_cost 없음')"
            )

    # ── 생성 헬퍼 ───────────────────────────────────────────────────────
    # 상태별로 필요한 인자가 다르므로 팩토리를 나눈다. 호출자가 status 를 직접 넘기며
    # 인자를 빠뜨리는 것보다, 이름이 요구 인자를 강제하는 쪽이 실수가 적다.

    @classmethod
    def ok(
        cls,
        value: float | str,
        *,
        unit: Unit,
        basis: Basis,
        derived: bool = False,
        derivation: str | None = None,
        ci95: tuple[float, float] | None = None,
        limit_note: str | None = None,
    ) -> MetricValue:
        return cls(
            status=MetricStatus.OK,
            value=value,
            unit=unit,
            basis=basis,
            derived=derived,
            derivation=derivation,
            ci95=ci95,
            limit_note=limit_note,
        )

    @classmethod
    def unconfirmed(
        cls,
        value: float | str,
        *,
        unit: Unit,
        basis: Basis,
        reason_detail: str,
        params_used: Mapping[str, object],
        derived: bool = False,
        derivation: str | None = None,
        limit_note: str | None = None,
    ) -> MetricValue:
        return cls(
            status=MetricStatus.UNCONFIRMED,
            value=value,
            unit=unit,
            basis=basis,
            reason_code=ReasonCode.PARAM_UNCONFIRMED,
            reason_detail=reason_detail,
            params_used=params_used,
            derived=derived,
            derivation=derivation,
            limit_note=limit_note,
        )

    @classmethod
    def unavailable(
        cls,
        reason_code: ReasonCode,
        reason_detail: str,
        *,
        unit: Unit | None = None,
        blocked_by: tuple[BlockerRef, ...] = (),
        limit_note: str | None = None,
    ) -> MetricValue:
        """근거가 없어 계산하지 못했다. **`unit` 은 남겨도 된다** — 계약이 허용한다.

        `not_run` 과 다르다: 이쪽은 계산을 시도했고 근거가 없다는 것을 확인했다.
        """
        return cls(
            status=MetricStatus.UNAVAILABLE,
            unit=unit,
            reason_code=reason_code,
            reason_detail=reason_detail,
            blocked_by=blocked_by,
            limit_note=limit_note,
        )

    @classmethod
    def blocked(
        cls,
        reason_detail: str,
        *,
        unit: Unit | None = None,
        blocked_by: tuple[BlockerRef, ...] = (),
        limit_note: str | None = None,
    ) -> MetricValue:
        """환경 제약으로 실행하지 못했다 — **선언된** 실행 불가.

        예: pyarrow 미설치로 Parquet 재현성 검사를 돌리지 못했다. 누군가 그것을
        알고 기록했다는 점이 `not_run` 과 다르다.
        """
        return cls(
            status=MetricStatus.BLOCKED,
            unit=unit,
            reason_code=ReasonCode.BLOCKED,
            reason_detail=reason_detail,
            blocked_by=blocked_by,
            limit_note=limit_note,
        )

    @classmethod
    def not_run(
        cls,
        reason_detail: str,
        *,
        reason_code: ReasonCode = ReasonCode.NOT_RUN,
        unit: Unit | None = None,
        blocked_by: tuple[BlockerRef, ...] = (),
        limit_note: str | None = None,
    ) -> MetricValue:
        """실행하지 않았다 — 아무도 선언하지 않은 공백.

        **이것을 `unavailable` 로 바꾸지 않는다.** "근거가 없다"고 말하려면 근거를
        찾아봤어야 한다. 안 돌린 것을 못 구한 것으로 적는 것이 이 프로젝트가 막는
        실패 양식이다. 선행 산출물 자체가 없으면
        `reason_code=PRECONDITION_MISSING` 을 쓴다.
        """
        return cls(
            status=MetricStatus.NOT_RUN,
            unit=unit,
            reason_code=reason_code,
            reason_detail=reason_detail,
            blocked_by=blocked_by,
            limit_note=limit_note,
        )


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
