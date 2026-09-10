# 이벤트 스키마 — 측정 계층 계약

> 정본은 `src/measurement/schema.py` (`SCHEMA_VERSION = "event-schema-v1.0-draft"`).
> 이 문서의 표는 그 모듈에서 생성했다. 스키마를 바꾸면 이 문서도 다시 생성한다.
>
> 근거: SRS DATA-003 · SIM-006 · ISO-003, PRD §21 · §30-31, `docs/data_spec.html` §7

실제 서비스 UI와 시뮬레이터가 **같은 스키마로 같은 Sink에 기록**한다.
어떤 필드를 통과시킬지 판단하는 기준은 하나다 — **실제 커머스 서비스에서 로그로 남을 수 있는가.**

## 전역 규약

| 항목 | 값 |
|---|---|
| 스키마 버전 | `event-schema-v1.0-draft` — GATE 1에서 `event-schema-v1.0`으로 Lock |
| 타임존 | `Asia/Seoul` 단일. UTC 혼재 불허 |
| timestamp 정밀도 | milliseconds. ISO 8601 + offset (`2025-10-01T09:00:00.000+09:00`) |
| 세션 만료 | 무활동 30분 |

## 필드

| 필드 | 타입 | 그룹 | 설명 |
|---|---|---|---|
| `event_id` | `string` | core | 이벤트 고유 ID (UUID4) |
| `customer_id` | `string` | core | 고객 ID |
| `timestamp` | `datetime[ms]` | core | 발생 시각 (KST) |
| `event_type` | `category` | core | EventType 16종 |
| `session_id` | `string` | session | 세션 식별자 |
| `session_duration` | `int` | session | 세션 체류시간(초). 세션의 **마지막 이벤트에만** 기록한다 |
| `page_type` | `category` | session | home / list / search / detail / cart / checkout / complete / history |
| `product_id` | `string` | product | 상품 ID |
| `category` | `category` | product | 상품 카테고리 5종 |
| `quantity` | `int` | product | 수량 (1 이상) |
| `unit_price` | `int` | product | 단가 (원, 0 이상) |
| `order_id` | `string` | order | 주문 ID |
| `order_amount` | `int` | order | 주문 금액(원) = Σ(unit_price × quantity) − discount |
| `coupon_id` | `string` | marketing | 쿠폰 ID |
| `campaign_id` | `string` | marketing | 캠페인 ID |
| `treatment_id` | `string` | marketing | 처치 ID (T0~T4) |
| `treatment_group` | `category` | marketing | control / treatment. **Feature 사용 금지** (SRS NFR-002) |
| `experiment_id` | `string` | marketing | 실험 ID. **Feature 사용 금지** |
| `service_version` | `string` | meta | 서비스 버전 |
| `customer_version` | `string` | meta | 고객 정의 버전 |
| `simulator_version` | `string` | meta | 시뮬레이터 버전. 서비스 UI 기록 시에는 null |
| `random_seed` | `int` | meta | 생성 seed. 서비스 UI 기록 시에는 null |

`event_id`·`customer_id`·`timestamp`·`event_type`는 **모든 이벤트에 필수**다.
메타 4종(`service_version`·`customer_version`·`simulator_version`·`random_seed`)은
재현성(SRS NFR-001 · SIM-011)을 위해 기록하며, 서비스 UI가 기록할 때는
`simulator_version`·`random_seed`가 null이다.

## 이벤트별 필수 / 선택 필드

● 필수 · ○ 선택 · — 해당 없음. Core 4종과 Meta 4종은 공통이므로 표에서 제외했다.

| event_type | `session_id` | `session_duration` | `page_type` | `product_id` | `category` | `quantity` | `unit_price` | `order_id` | `order_amount` | `coupon_id` | `campaign_id` | `treatment_id` | `treatment_group` | `experiment_id` |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| `session_start` | ● | ○ | ● | — | — | — | — | — | — | — | — | ○ | ○ | ○ |
| `page_view` | ● | ○ | ● | ○ | ○ | — | — | — | — | — | — | ○ | ○ | ○ |
| `search` | ● | ○ | ● | — | ○ | — | — | — | — | — | — | ○ | ○ | ○ |
| `product_view` | ● | ○ | ● | ● | ● | — | ○ | — | — | — | — | ○ | ○ | ○ |
| `return_visit` | ● | ○ | ● | — | — | — | — | — | — | — | — | ○ | ○ | ○ |
| `add_to_cart` | ● | ○ | ● | ● | ● | ● | ● | — | — | — | — | ○ | ○ | ○ |
| `remove_from_cart` | ● | ○ | ● | ● | ● | ● | ● | — | — | — | — | ○ | ○ | ○ |
| `checkout_start` | ● | ○ | ● | — | — | — | — | ● | ● | ○ | — | ○ | ○ | ○ |
| `purchase` | ● | ○ | ● | — | — | — | — | ● | ● | ○ | ○ | ○ | ○ | ○ |
| `campaign_exposed` | ○ | — | ○ | — | — | — | — | — | — | ○ | ● | ○ | ○ | ○ |
| `push_sent` | — | — | — | — | — | — | — | — | — | ○ | ● | ○ | ○ | ○ |
| `coupon_exposed` | ○ | — | ○ | — | — | — | — | — | — | ● | ● | ○ | ○ | ○ |
| `coupon_clicked` | ● | ○ | ○ | — | — | — | — | — | — | ● | ● | ○ | ○ | ○ |
| `coupon_use` | ● | ○ | ○ | — | — | — | — | ● | ● | ● | ● | ○ | ○ | ○ |
| `review` | ● | ○ | ○ | ● | ● | — | — | ○ | — | — | — | ○ | ○ | ○ |
| `cs_contact` | ○ | — | ○ | ○ | ○ | — | — | ○ | — | — | — | ○ | ○ | ○ |

**`session_duration` 기록 규칙** — 세션 시작 시점에는 값을 알 수 없다.
세션의 **마지막 이벤트에만** 기록한다. 이미 기록한 레코드를 나중에 갱신하지 않는다(append-only).

**배정 필드** — `treatment_id`·`treatment_group`·`experiment_id`는 실험 기간 중
모든 이벤트에 선택적으로 붙는다. 기록은 하되 **Feature로 사용하지 않는다**(SRS NFR-002).

## 파생 상태 이벤트

| 상태 | 의미 |
|---|---|
| `inactive` | 활동이 끊긴 상태 |
| `at_risk` | 마지막 구매 후 28~41일 |
| `churn` | 마지막 구매 후 42일 이상 |

기록은 하되 **학습 Feature로 사용하지 않는다.** 라벨과 동어반복이 되어 AUC가
비현실적으로 높아진다(PRD §80 Risk 7). 대시보드 표시와 코호트 분석 전용이다.
모델 라벨은 전향적 42일 window로 따로 정의한다(`docs/data_spec.html` §5).

## 식별자 형식

| 필드 | 정규식 | 예 |
|---|---|---|
| `event_id` | `^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$` | `3f2a1b4c-5d6e-4f70-8912-a3b4c5d6e7f8` |
| `customer_id` | `^C\d{8}$` | `C00012345` |
| `session_id` | `^S-C\d{8}-\d{13}$` | `S-C00012345-1759276800000` |
| `order_id` | `^O\d{8}-\d{6}$` | `O20251001-000123` |
| `product_id` | `^P\d{4}$` | `P0042` |
| `coupon_id` | `^CPN-[A-Z0-9]{6}$` | `CPN-A1B2C3` |
| `campaign_id` | `^CMP-\d{8}-\d{3}$` | `CMP-20251001-001` |
| `treatment_id` | `^T[0-4]$` | `T3` |
| `experiment_id` | `^EXP-\d{8}-\d{2}$` | `EXP-20251001-01` |

`session_id`는 `S-{customer_id}-{세션 시작 epoch ms}` 형식이며,
무활동 30분이면 만료되고 다음 활동은 새 id를 받는다.

## 이 계층을 통과할 수 없는 필드

실제 서비스에서 알 수 없는 값이다. `validate_event()`가 거부하고
`tests/test_schema.py`가 스키마 자체에 섞이지 않았는지 검사한다.

```
base_churn_propensity
base_purchase_probability
base_visit_frequency
brand_loyalty
cart_abandonment_propensity
coupon_sensitivity
cs_contact_propensity
marketing_fatigue
marketing_responsiveness
persona
price_sensitivity
purchase_cycle
quadrant
review_propensity
search_propensity
shipping_fee_sensitivity
tau
true_tau
true_uplift
y_control
y_treatment
```

## Observable 지표 ↔ 이벤트 매핑

PRD §21이 AI 입력으로 허용한 16개 지표를 이 스키마만으로 계산할 수 있어야 한다.

| Observable 지표 | 계산에 쓰는 이벤트 |
|---|---|
| `last_visit_date` | `session_start` · `return_visit` |
| `last_purchase_date` | `purchase` |
| `visit_count` | `session_start` · `return_visit` |
| `purchase_count` | `purchase` |
| `purchase_interval` | `purchase` |
| `average_order_value` | `purchase` |
| `cumulative_revenue` | `purchase` |
| `cart_abandonment_count` | `add_to_cart` · `checkout_start` · `purchase` |
| `coupon_exposure_count` | `coupon_exposed` |
| `coupon_usage_count` | `coupon_use` |
| `campaign_response_count` | `campaign_exposed` · `coupon_clicked` · `purchase` |
| `session_duration` | `session_start` · `page_view` · `product_view` |
| `page_views` | `page_view` |
| `search_count` | `search` |
| `cs_contact_count` | `cs_contact` |
| `review_count` | `review` |

`cart_abandonment_count`는 `add_to_cart`가 있고 같은 세션에
`purchase`가 없는 경우로 계산한다. `campaign_response_count`는
`campaign_exposed` 이후 반응 관찰기간 내 `coupon_clicked` 또는 `purchase`로 계산한다.

## 사용법

```python
from src.measurement.schema import EventType, validate_event

problems = validate_event(record)   # 빈 리스트면 통과
if problems:
    raise ValueError(problems)
```

Event Sink([M-2])와 데이터 품질 검증([M-6])이 이 함수를 사용한다.

## 이 문서 다시 만들기

```bash
python3 scripts/gen_event_schema_doc.py > docs/event_schema.md
```
