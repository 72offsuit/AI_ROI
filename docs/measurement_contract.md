# 측정 기록 계약 — `MEASUREMENT CONTRACT v1`

> **이 문서 하나로 커머스 퍼널 전 단계의 이벤트·필드 매핑을 알 수 있다.**
> 서비스 UI 담당자는 다른 문서를 열지 않고 여기까지만 읽으면 된다.

**대상 이슈** `#45` · **작성** Phillip (Role 8 · W5-A) · 2026-09-11 · 사이클 **C1**
**정본** `src/measurement/schema.py` — **이 문서는 인용한다. 값을 다시 정의하지 않는다.**

---

## 0. 이 문서의 지위 — 먼저 읽을 세 줄

| # | |
|---|---|
| **①** | **정본은 코드다.** `src/measurement/schema.py` 가 규칙을 정하고 이 문서는 그것을 읽기 쉽게 옮긴다. 어긋나면 **코드가 맞다** — `tests/test_measurement_contract.py` 가 이 문서의 표를 코드와 대조해 어긋나면 실패한다 |
| **②** | **값을 문서에 다시 적으면 두 벌이 되고 언젠가 갈라진다.** 그래서 허용값·정규식은 인용 표시(`정본: schema.py`)와 함께 적었다 |
| **③** | **시뮬레이터가 만든 이벤트와 커머스가 만든 이벤트를 구분 없이 같은 파이프라인에 넣는다.** 출처 플래그 컬럼이 없다 (§3) |

**왜 이 문서가 필요한가:** 지금 SRS · `docs/data_spec.html` · `docs/event_schema.md` · 코드가 서로 다른 말을 하고, **어느 것이 정본인지 알 수 없다.** 이 문서가 그 질문에 답한다.

---

## 1. 퍼널 ↔ `event_type` 매핑

**Core 4 (항상 필수)** `event_id` · `customer_id` · `timestamp` · `event_type`
**Meta 4 (항상 선택)** `service_version` · `customer_version` · `simulator_version` · `random_seed`
**배정 3 (어디서나 선택)** `treatment_id` · `treatment_group` · `experiment_id`

아래 "필수"는 **Core 4 에 더해지는 것**이다.

| 퍼널 단계 | `event_type` | 필수 (Core 4 + 아래) | 선택 |
|---|---|---|---|
| **Visit** | `session_start` | `page_type` · `session_id` | `session_duration` |
| — | `page_view` | `page_type` · `session_id` | `category` · `product_id` · `session_duration` |
| — | `search` | `page_type` · `session_id` | `category` · `session_duration` |
| **Product View** | `product_view` | `category` · `page_type` · `product_id` · `session_id` | `session_duration` · `unit_price` |
| **Return Visit** | `return_visit` | `page_type` · `session_id` | `session_duration` |
| **Add To Cart** | `add_to_cart` | `category` · `page_type` · `product_id` · `quantity` · `session_id` · `unit_price` | `session_duration` |
| — | `remove_from_cart` | `category` · `page_type` · `product_id` · `quantity` · `session_id` · `unit_price` | `session_duration` |
| **Checkout Start** | `checkout_start` | `order_amount` · `order_id` · `page_type` · `session_id` | `coupon_id` · `session_duration` |
| **Purchase** | `purchase` | `order_amount` · `order_id` · `page_type` · `session_id` | `campaign_id` · `coupon_id` · `session_duration` |
| 마케팅 | `campaign_exposed` | `campaign_id` | `coupon_id` · `page_type` · `session_id` |
| 마케팅 | `push_sent` | `campaign_id` | `coupon_id` |
| 마케팅 | `coupon_exposed` | `campaign_id` · `coupon_id` | `page_type` · `session_id` |
| 마케팅 | `coupon_clicked` | `campaign_id` · `coupon_id` · `session_id` | `page_type` · `session_duration` |
| 마케팅 | `coupon_use` | `campaign_id` · `coupon_id` · `order_amount` · `order_id` · `session_id` | `page_type` · `session_duration` |
| 부수 | `review` | `category` · `product_id` · `session_id` | `order_id` · `page_type` · `session_duration` |
| 부수 | `cs_contact` | `customer_id` | `category` · `order_id` · `page_type` · `product_id` · `session_id` |

**Repurchase** 는 별도 `event_type` 이 아니다 — 같은 고객의 두 번째 이후 `purchase` 다. 재구매율은 게시 시점에 계산한다 (`kpi.repurchase_rate`).

> ### ★ `return_visit` 은 **구매 뒤 첫 방문 세션**을 연다 — `session_start` 와 함께가 아니라 **대신**이다 (#256 · DR-256)
> - 고객의 마지막 `purchase` 뒤 **처음 시작하는 세션**은 `return_visit` 으로 연다. 그 세션에는 `session_start` 를 **남기지 않는다.**
> - 다른 세션 — 구매 이력이 없는 고객의 세션, 구매 뒤 두 번째 이후 세션 — 은 `session_start` 로 연다.
> - 그래서 세션은 `session_start` · `return_visit` 중 **하나**로 시작한다. 방문(세션) 수는 두 이벤트를 합쳐 세거나 `session_id` 고유 개수로 센다 — 둘은 같다. **`session_start` 만 세면 재방문 세션이 빠진다.**
> - 근거: `docs/data_spec.html` §3.4 ④(#198). 두 생산자 — 커머스 · 시뮬레이터 — 가 이 정의로 기록한다.

> ### ★ 표에 없는 필드는 **금지**다 (`NOT_APPLICABLE`)
> 화이트리스트가 **부재로 동작한다.** `push_sent` 에 `product_id` 를 붙이면 `validate_event()` 가 거부한다:
> ```
> push_sent: 해당 없는 필드에 값이 있음 — product_id
> ```
> **"넣어도 무시된다"가 아니라 "넣으면 거부된다"** 다. 쓸 데 없는 필드를 습관으로 채우면 레코드가 전부 버려진다.

### ⚠ `purchase` 는 **주문 단위 1행**이다 — 품목을 넣지 마십시오

`purchase` 에서 **`product_id` · `category` · `quantity` · `unit_price` 가 `NOT_APPLICABLE`** 이다. 값이 있으면 거부된다.

**커머스 구현자가 가장 밟기 쉬운 자리다** — 주문 품목을 `purchase` 에 담으려다 레코드 전체가 거부된다. 품목은 `add_to_cart` 에 있다.

**대가:** 한 주문의 `Σ(unit_price × quantity)` 를 `events` 만으로 재구성할 수 없다. 품목·주문 시점 원가·할인·배송비는 **커머스 교환 파일**(`data/commerce/`, 계약 `docs/contracts/commerce-exchange/v1/`, 이슈 `#100`)이 싣는다. 결과:

| 지표 | 교환 파일이 있는 주문 | 교환 파일이 없는 주문 |
|---|---|---|
| `cogs` (매출원가) | `Σ(order_items.unit_cost × quantity)` — 주문 시점 원가 | **`NO_COST_BASIS`** — 원가율을 곱해 추정하지 않는다 (§6.2) |
| `contribution_profit` | 계산된다 | **계산 불가** — `cogs` 의존 |
| `DQ-09` (금액 등식 검사) | 실행된다 — 품목 합계 − 할인 = 교환 파일 금액 = 이벤트 금액 | **`not_run` · `PRECONDITION_MISSING`** — 대조할 품목 합계가 없다 |

---

## 2. 값 규약 — **인용이다. 정본은 코드다**

**정본** `src/measurement/schema.py` · **생성 문서** `docs/event_schema.md`(재생성으로 코드와 일치 보장)

### `category` 5종

```
fresh_food · meal_solution · dairy · beverage · household
```

**영문 코드가 정본이다** (SRS `COM-001`). `docs/data_spec.html` §6.1 의 한글(신선식품·간편식·유제품·음료·생활용품)은 **표 가독성을 위한 표기**이며 값으로 쓰지 않는다. **표시명 매핑은 UI 책임**이다 — 측정 계층은 코드만 안다.

### `page_type` 8종

```
home · list · search · detail · cart · checkout · complete · history
```

### 식별자 형식 9종

| 필드 | 정규식 | 예 |
|---|---|---|
| `event_id` | UUID4 | `3f2a1b4c-5d6e-4f70-8912-a3b4c5d6e7f8` |
| `customer_id` | `^C\d{8}$` | `C00012345` |
| `session_id` | `^S-C\d{8}-\d{13}$` | `S-C00012345-1759276800000` |
| `order_id` | `^O\d{8}-\d{6}$` | `O20251001-000123` |
| `product_id` | `^P\d{4}$` | `P0042` |
| `coupon_id` | `^CPN-[A-Z0-9]{6}$` | `CPN-A1B2C3` |
| `campaign_id` | `^CMP-\d{8}-\d{3}$` | `CMP-20251001-001` |
| `treatment_id` | `^T[0-4]$` | `T3` |
| `experiment_id` | `^EXP-\d{8}-\d{2}$` | `EXP-20251001-01` |

`session_id` 는 `S-{customer_id}-{세션 시작 epoch ms}` 이며 **무활동 30분**이면 만료되고 다음 활동은 새 `session_id` 를 받는다.

> ### ★★ 커머스의 현재 식별자가 전부 형식 위반이다 — **맞추는 쪽은 소스다**
>
> | 커머스 실측 | 형식 |
> |---|---|
> | `test-user-1` (`seed-data.ts:97`) | `^C\d{8}$` 위반 |
> | `dummyjson-16` (`seed-data.ts:5`) | `^P\d{4}$` 위반 |
> | `randomUUID()` (`orders.ts:115`) | `^O\d{8}-\d{6}$` 위반 |
>
> **→ 커머스가 기록 시점에 변환한다.** 측정 계층에 매핑 계층을 만들지 않는다.
>
> **왜:** 측정 계층에 *"커머스는 이런 ID 를 쓴다"* 는 지식이 들어가면 **창구가 한쪽 편을 드는 것**이 된다. 계약은 하나여야 한다. `validate_event()` 는 출처를 모르고, 계속 모르게 둔다 — `tests/test_neutrality.py` 가 그것을 소스 검사로 고정한다.
>
> **안전판:** `EventSink(strict=False)` 관용 모드가 있다. 형식 위반 레코드를 `rejected.jsonl` 에 사유와 함께 남기되 **수집은 죽지 않는다** (`MEA-003`). 전량 거부되더라도 파이프라인이 멈추지 않는다.
>
> 적용 요구는 §8 의 이슈 초안에 있다.

### 타임존 — **KST 단일. 입력은 관용, 저장은 정규화**

| | |
|---|---|
| **입력** | 오프셋이 붙은 **어떤 표기든** 받는다 (`+09:00` · `Z` · `-05:00`) |
| **거부** | **오프셋이 없는 timestamp** — 순간을 특정할 수 없으므로 추측하지 않는다 |
| **저장** | `EventSink` 가 **KST 로 정규화**해 쓴다. 파티션 날짜도 같은 파싱에서 나온다 |

```
"2025-10-01T23:30:00.000Z"       →  저장 "2025-10-02T08:30:00.000+09:00" · 파티션 date=2025-10-02
"2025-10-01T09:00:00.000+09:00"  →  그대로
"2025-10-01T23:30:00"            →  거부 (오프셋 없음)
```

**정밀도** ISO 8601 + offset, **밀리초**. `2025-10-01T09:00:00.000+09:00`

> **왜 UTC 를 거부하지 않는가:** 커머스가 UTC 로 기록하고 있고(`orders.ts:116`), 전량 거부하면 `MEA-003`(부분 소스 관용)과 충돌한다.
> **왜 저장 시 정규화하는가:** 원문을 그대로 두면 저장된 값은 UTC 인데 파티션 날짜는 KST 가 되어 **`DQ-06`("모든 시각이 KST 단일")이 자기 저장물에 대해 실패한다.**

---

## 3. 출처 판별 — **별도 플래그 컬럼이 없다**

```python
# src/measurement/sink.py
def event_source(record) -> EventSource:
    """`simulator_version` · `random_seed` 가 모두 없으면 커머스 실측분이다."""
```

**`MEA-002` 를 별도 플래그 없이 스키마에서 파생한다** → 기록자가 출처를 위조할 여지가 적다.

**→ 커머스는 `simulator_version` · `random_seed` 를 `null` 로 둔다** (또는 키를 생략한다. 둘은 같게 취급된다).

> ⚠ **`docs/data_spec.html` §7.2 가 메타 4종을 `Nullable = N` 으로 적었다. 그 문서가 낡았다.**
> `null` 을 출처 판별에 쓰는 것이 `MEA-002` 의 구현이므로 **코드가 옳다.** (W1 D-1 · `data-model-erd.md` §2.2)

---

## 4. 상품 참조 계약

측정 계층이 원가를 계산하려면 **저장된 `unit_cost`** 가 필요하다 (§6.2 `EC-1`). ★ **COGS 의 원천은 주문 시점 원가 스냅샷(`order_items.unit_cost`)이고, 카탈로그는 참고용이다** — 원가는 시간에 따라 변하므로 과거 주문을 현재 카탈로그 원가로 계산하면 상품마다 방향이 다른 오차가 생긴다. 둘 다 커머스 교환 파일로 온다 (`docs/contracts/commerce-exchange/v1/` §3).

| 필드 | 형식 | 의미 |
|---|---|---|
| `product_id` | `^P\d{4}$` | 상품 식별자. `events` 의 `product_id` 와 같은 어휘 |
| `category` | `category` 5종 | §2 의 값. 다른 어휘를 쓰면 카테고리 지표가 갈라진다 |
| `selling_price` | `int` (원, 0 이상) | 판매가. `events.unit_price` 의 원천 |
| `unit_cost` | `int` (원, 0 이상) **또는 `null`** | ★ 원가. **`null` 이면 `NO_COST_BASIS`** — `0` 으로 채우지 않는다 |

### ★ `unit_cost: null` 과 `unit_cost: 0` 은 다르다

**원가 0 원인 상품**(사은품)과 **원가를 모르는 상품**은 전혀 다른 상태다. `0` 으로 채우면 기여이익이 매출과 같아지고, 그 잘못된 결론이 조용히 만들어진다.

### 카탈로그 스냅샷 포맷

`Ecommerce_Service` 가 시점 스냅샷을 낸다. **가격이 바뀌면 과거 주문의 원가가 달라지므로 스냅샷에 시점이 있어야 한다.**

```jsonl
{"snapshot_at":"2025-10-01T00:00:00.000+09:00","product_id":"P0042","category":"fresh_food","selling_price":8900,"unit_cost":6942}
{"snapshot_at":"2025-10-01T00:00:00.000+09:00","product_id":"P0043","category":"dairy","selling_price":4200,"unit_cost":null}
```

이 스냅샷은 교환 파일 `catalog.jsonl` 이다. 교환 파일이 없으면 `cogs` 가 `NO_COST_BASIS` 다 — **결함이 아니라 정직한 상태**다.

---

## 5. 버전 규칙

| 필드 | 표기 | 누가 채우나 |
|---|---|---|
| `service_version` | `svc-{major}.{minor}` — 예 `svc-1.0` | 커머스 |
| `customer_version` | `cust-{major}.{minor}` | 커머스·시뮬레이터 |
| `simulator_version` | `sim-{major}.{minor}` | 시뮬레이터만. **커머스는 `null`** |
| `random_seed` | `int` | 시뮬레이터만. **커머스는 `null`** |

### 호환성 규칙

| 변경 | 버전 | 영향 |
|---|---|---|
| 선택 필드에 값을 채우기 시작 | **minor** | 없다. 충족률이 올라간다 |
| 새 `page_type`·`category` 값 | **major** | ★ `validate_event()` 가 거부한다. **스키마 Enum 을 먼저 고쳐야 한다** |
| 필수 필드 추가 | **major** | `EVENT SCHEMA v1` 실질 변경 → `FREEZE-003` |
| `event_type` 추가 | **major** | 동일. 16종이 `assertEqual` 로 고정돼 있다 |

**`schema_version`** 은 이벤트 필드가 아니라 `manifest.json` 과 게시물 `provenance` 에 실린다. 현재 `event-schema-v1.0-draft` 이고 GATE 1 에서 `event-schema-v1.0` 으로 Lock 한다.

---

## 6. ★ Lock 최종 검산 — 표현력 공백 4건

> **이 절이 `#45` 의 실질이다.** `gate1-lock-scope.md` §2.2: *"계약 문서를 실제로 쓰는 행위가 스키마 표현력을 검산한다."*
> **Lock 이후에 공백을 발견하면 `FREEZE-003` 전량 재실행이다.**

### 판정 — **네 공백 모두 결론이 있다. `#49` 로 진행 가능하다**

| # | 공백 | 결론 | 차단? |
|---|---|---|---|
| ① | 파생 상태 기록 경로 | **게시 시점 계산** (리드 판정 ④) | **아니다** |
| ② | `shipping_subsidy` 필드 부재 | 교환 파일 관측값 우선, 없으면 **규칙 유도 + `derived: true`** (D-3 · `#100`) | **아니다** |
| ③ | `discount` 필드 부재 | 교환 파일 관측값 우선, 없으면 **규칙 유도 + `derived: true`** (D-16 · `#108`) | **아니다** |
| ④ | `customers` 테이블 부재 | **`PRECONDITION_MISSING` 재분류** | **아니다** — 단 §6.4 조건부 |

**넷 다 "필드를 추가한다"가 아니라 "규칙을 정한다"로 풀렸다.** ②③은 이후 커머스 교환 파일(`#100`)이 실제 값을 싣게 되어, 값이 있는 주문은 규칙 대신 관측값을 쓴다 — 이벤트 스키마는 여전히 바뀌지 않았다. 진짜 차단은 규칙을 안 정한 채 Lock 하는 것이다 — 다음 사이클이 임의로 정하면 Lock 이후 변경이다.

---

### 6.1 파생 상태 — **`events` 에 기록하지 않는다** (계약 문장)

`inactive` · `at_risk` · `churn` 은 `DerivedStateType` 이고 **`EventType` 16종 밖**이다. `tests/test_schema.py test_derived_states_are_not_raw_events` 가 교집합 0 을 강제한다.

| # | 계약 문장 |
|---|---|
| **①** | **파생 상태는 `events` 에 기록되지 않는다.** 기록자(커머스·시뮬레이터)는 **보내지 않는다** — 보내면 `validate_event()` 가 `알 수 없는 event_type` 으로 거부한다 |
| **②** | **측정 계층이 게시 시점에 계산한다.** `days_since_last_purchase` 에서 유도하고, 그 원천(`timestamp`·`purchase`)은 **이미 스키마에 있다** |
| **③** | 산출물에 **`derived: true` + `derivation`**(계산식)이 붙는다 — **저장된 사실과 구분된다** |
| **④** | ★ **Feature 로 쓰지 않는다.** 라벨과 동어반복이 되어 `days_since_last_purchase ≥ 42` 라는 Feature 가 라벨을 거의 완전히 결정한다 — **AUC 0.99 가 나오지만 학습된 것은 아무것도 없다** (PRD Risk 7). **대시보드 표시와 코호트 분석 전용** |
| **⑤** | **`DB-012` 위반이 아니다** — 계산하는 쪽은 `measurement` 이고 **대시보드가 아니다** |

**임계값** `at_risk_days = 28` · `no_purchase_days = 42` · `no_login_days = 60` — ★ **가설값이고 C1 에서 Lock 하지 않는다.** 해당 지표는 `status: unconfirmed` + `params_used` 로 나간다 (결정 D-5).

> **④가 가장 위험한 자리다.** 파생 상태가 게시물에 나타나는 순간 *"이제 Feature 로 써도 되는 것 아닌가"* 로 읽힐 수 있다.
> **`tests/test_schema.py test_no_observable_depends_on_derived_state` 가 그대로 통과해야 한다** — Observable 16개가 파생 상태에 의존하지 않는다. `tests/test_kpi_layers.py test_condition_4_derived_states_stay_out_of_observables` 가 짝이다.

**구현 위치** 지표 정의 `kpi.derived_state_count` · 게시 형식 `publish.build_kpi_report`.

---

### 6.2 매출원가 — **원가율을 곱하지 않는다** (`EC-1`)

```
COGS = Σ (unit_cost × quantity)        ← 저장된 값을 읽는다      ✅
COGS = order_amount × 원가율            ← 기록 없는 곳에 값을 만든다  ❌
```

**0 으로 채우는 것과 74% 로 채우는 것은 같은 종류의 잘못이고, 74% 가 더 그럴듯해서 더 위험하다.**

추정 COGS 로 계산한 기여이익은 `order_amount` 의 **상수배**다. 그러면 `contribution_profit` 이 `revenue` 와 **완전히 같은 정보만 담고**, PRD §65 의 `revenue_up_profit_down` 가드레일이 **원리적으로 발동할 수 없다. 가드레일이 죽는다.**

**가르는 기준은 출처가 아니라 근거다** (`EC-2`):

```
has_cost_basis(order) := 주문의 모든 품목에 unit_cost 값이 존재한다
```

| | 출처 기준 (`if source == COMMERCE`) | **근거 기준 (채택)** |
|---|---|---|
| 커머스가 `unit_cost` 를 넣으면 | **여전히 거부** — 코드를 고쳐야 한다 | **자동으로 계산됨** |
| 시뮬레이터가 원가 없는 상품을 만들면 | **잘못 계산됨** | **거부 — 올바르다** |

`config/economic_config.yaml` 의 `product_margin`(원가율)은 **`ECONOMIC RULE v1` Lock 대상**이라서 있는 것이고 measurement 가 쓰기 위해서가 아니다. 소비자는 이후 사이클의 시뮬레이터다 — `CostAccountingConfig` 에 그 속성이 **타입 수준에서 없다** (`EC-9`).

---

### 6.3 `discount` · `shipping_subsidy` — 관측값 우선, 없으면 유도 규칙 (D-16 · D-3)

**둘 다 DATA-003 22컬럼에 없다.** 필드 추가는 `Plan/` SRS 개정을 요구하고 그것은 이 팀의 권한 밖이다. 그래서 **이벤트 밖에서** 온다:

```
주문마다 (기준은 출처가 아니라 값이 있는가 — EC-2):
  교환 파일에 값이 있다   → 관측값     discount · shipping_fee − shipping_charged   (#100 · #108)
  없다                    → 아래 유도 규칙                                           derived: true
  쿠폰을 썼는데 할인도 쿠폰 처치도 없다 → coupon_cost 계산 불가 (0 원이 아니다)       (#108)
관측과 유도가 섞인 합계는 derived: true 로 싣는다
```

> **리드 판정 (D-16):** *"차단되는 것은 필드의 부재가 아니라 **결정의 부재**다. `G-16` 의 충족 조건은 '필드를 추가한다'가 아니라 **'유도 규칙을 `ECONOMIC RULE v1` 에 넣는다'** 이다."*

```
discount(order) := Σ treatment_cost[t].unit_cost_krw
                     for t in (order 에 적용된 처치 ∩ coupon_treatments)
                   단 그 주문에 coupon_use 이벤트가 있을 때만 (EC-3 발생주의 2원칙)
                   최소주문금액 미달로 미사용이면 0 이 아니라 발생하지 않는다

shipping_subsidy(order) := shipping_fee_krw
                   if order_amount < free_shipping_threshold_krw ∧ T1 ∈ treatment_ids
```

**두 규칙은 `config/economic_config.yaml` 의 `assumptions` 에 조항으로 있다.** 유도값이므로 산출물에 **`derived: true` + `derivation`** 이 붙는다.

| 대상 | 처리 |
|---|---|
| 시뮬레이터 생성분 | 규칙 유도가 정확하다 — 처치를 시뮬레이터가 배정하므로 |
| 커머스 실측분 (교환 파일 있음) | **관측값.** 커머스는 주문마다 할인·정책 배송비·실제 배송비를 저장하고(`Ecommerce_Service` #36 · #42) 교환 파일로 낸다(#51) |
| 커머스 실측분 (교환 파일 없음) | 커머스 주문에는 처치 ID 가 없어 유도가 성립하지 않는다 — 배송보조는 계상되지 않고(과소), 쿠폰을 쓴 주문이 있으면 `coupon_cost` 는 **계산 불가**다 |

결정: `docs/decisions/DR-108-coupon-cost-basis.md` · 계약: `docs/contracts/commerce-exchange/v1/` §5

---

### 6.4 ★ `customers` 테이블 부재 — 모집단이 성립하지 않는 지표

`P_all(D)` 는 `signup_date ≤ D` 로 정의되는데 **`signup_date` 는 `customers` 컬럼이고 그 테이블이 미구현**이다. `events` 22컬럼에 `signup_date` 가 없다.

> *"이벤트는 '무언가 한 고객'만 보여주지 **전체 고객 명부가 아니다**."*

| 지표 | 판정 |
|---|---|
| `cohort_retention_rate[m]` | **`unavailable` + `PRECONDITION_MISSING`** · `blocked_by: [{kind:"table", ref:"customers"}]` |
| `P_eligible` 계열 | 동일 |
| **`repurchase_rate`** | ★ **막히지 않는다 — `ok`** |

### ★ `repurchase_rate` 를 `PRECONDITION_MISSING` 으로 적지 않는 이유

계산식이 `purchase` 이벤트만 쓴다 — **`signup_date` 가 식에 나오지 않는다.**

```
|{c : purchase_count(c,[D−L,D]) ≥ 2}| / |{c : purchase_count(c,[D−L,D]) ≥ 1}|
```

분모 정의가 이미 *"기간 내 1회 이상 구매 고객"* 이다. 막힌 것은 `kpi-definition-v1.md` 의 `모집단` 칸이 `P_all(D)` 라고 적은 **선언**이고, 그것은 **그 문서 내부의 모순**이다.

**`PRECONDITION_MISSING` 은 *"근거가 없다"* 는 뜻인데 근거는 있다. 과대보고의 거울상이지만 이유를 틀리게 말하는 것은 같다.**

→ `status: ok` + `basis.population` 에 실제 모집단을 정확히 적는다:
```
"[D−42, D] 구간에 purchase 이벤트가 1건 이상인 고객 (P_all(D) 이 아니다 — signup_date 없이 구성되는 모집단이다)"
```

**조건부 판정:** `cohort_retention_rate` 의 계산 불가는 **Lock 을 막지 않는다** — 그 지표를 `PRECONDITION_MISSING` 으로 게시하는 것이 정직한 상태이고, 계산 계약 자체는 확정됐다. 다만 **`kpi-definition-v1.md` §8 이 이 지표를 `✅`(계산 가능)로 적은 것은 틀렸다** — 그 문서가 갱신되어야 한다 (W6 항목).

**조치** 별도 저장소 이슈 `#29` — *"feat: 고객 모델에 가입일 추가와 라이프사이클 기준 확보"* (OPEN).

---

## 7. 한계 — 적지 않으면 없는 것이 된다

### 7.1 `campaign_response_count` 의 정밀도 한계

`coupon_clicked` 는 **쿠폰을 전제한다.** 쿠폰이 없는 캠페인(배너·푸시)의 클릭을 담을 이벤트가 없다.

**→ 쿠폰 비종속 캠페인의 반응은 이 지표로 측정되지 않는다. 과소계상이다.**

| | |
|---|---|
| `status` | **`ok`** — 값은 나온다 |
| `limit_note` | *"쿠폰 비종속 캠페인(배너·푸시)의 반응은 담을 이벤트가 없어 과소계상된다"* |
| `unconfirmed` 와 다른 점 | `unconfirmed` 는 파라미터가 확정되면 값이 맞아진다. **한계는 이벤트가 추가되지 않으면 영원히 과소계상**이다 |

화면 규칙 `V-7` 이 이 값을 읽어 `한계` 칩을 붙인다.

### 7.2 캐러셀 자동 전환을 `page_view` 로 기록하지 않는다

**사용자가 보지 않은 화면이 `page_view` 로 찍히면 세션 품질 지표가 오염된다** — 체류시간·페이지뷰 수가 사용자 행동과 무관하게 부풀고, 그 값이 이탈 예측 Feature 로 들어간다.

**→ 자동 전환·무한 스크롤 자동 로드·프리페치는 `page_view` 가 아니다.** 사용자의 명시적 행동만 기록한다. (W1 `R-9`)

### 7.2-b 매출 기준 — **순매출** (이슈 `#101` · 2026-09-21)

`order_amount` 는 계약상 `Σ(unit_price × quantity) − discount` 이므로 **할인이 이미 빠진 금액**이다. 따라서:

```
revenue             = Σ order_amount                       할인 후
contribution_profit = revenue − COGS − 배송보조 − 메시지 − 캠페인 고정비
                      ★ 쿠폰 할인을 다시 빼지 않는다
marketing_cost      = 쿠폰 + 메시지 + 캠페인 고정비          ROI 분모 — 유지
```

**왜 이 기준인가.** 총매출 기준(매출에 할인을 되돌리고 비용으로 한 번 빼기)도 **같은 기여이익을 낸다** — `15,700 − 11,000 − 1,570 = 14,130 − 11,000 = 3,130`. 단 **같은 할인액을 쓸 때만** 그렇다. 유도 할인(`D-16` · `T2`=3,000 · `T3`=7,000)은 커머스 실제 할인(예 1,570)과 어긋나므로, 순매출은 `order_amount` 안의 **실제 할인**을 쓰고 가정 `A-DISCOUNT` 가 기여이익에서 빠진다.

★ 이 기준은 **커머스 이벤트가 `order_amount` 를 실제로 할인 후 금액으로 싣는다**는 사실에 기댄다. 처음 확정할 때 확인하지 않았고 사실이 아니었다(커머스가 할인 전 소계를 싣고 있었다 — `#106`). 커머스가 고쳤고(`Ecommerce_Service` #52), `DQ-09` 가 이벤트와 교환 파일의 금액을 주문마다 대조한다. 실제 커머스 산출물에서 두 기준의 기여이익이 같음을 `tests/test_commerce_exchange_contract.py` 가 확인한다.

**쿠폰이 분모에 남는 것은 중복이 아니다.** 분자(이익)와 분모(지출)는 다른 것이고, 할인의 이익 영향은 이미 매출 감소로 들어가 있다. 양쪽에서 빼면 ROI 가 과대평가된다.

> ⚠ 커머스 `#24` 는 **총매출 기준**(할인 전 소계 · 할인 1회 차감)으로 표시한다. **수치는 같고 리포트의 줄 구성만 다르다.** 양쪽 문서가 각자 기준을 명시한다.

근거: `docs/decisions/DR-101-revenue-basis.md` · 강제: `tests/test_revenue_basis.py`

### 7.3 가정 `A-REFUND` — 총매출을 순매출로 간주한다

`revenue = Σ order_amount` 이며 **환불·취소를 차감하지 않는다.** 환불이 발생하는 환경에서 `contribution_profit` 은 **과대평가**된다.

**왜 환불 이벤트를 추가하지 않는가** — 추가할 수 없다:

| 장벽 | 근거 |
|---|---|
| 컬럼을 늘릴 수 없다 | `DATA-003` 이 정확히 22개를 규정하고 `tests/test_schema.py` 가 `assertEqual` 로 고정 |
| 음수 금액으로 우회할 수 없다 | `validate_event()` 가 음수 금액 4종을 거부한다 |
| `event_type` 만 추가하는 것도 스키마 변경 | 16종 고정 |

셋 다 `Plan/` SRS 개정을 요구한다 → **권한 밖.** `config` 의 `assumptions.refund_adjusted: false` 로 두고 게시물 `notices` 의 `REFUND_NOT_ADJUSTED` 로 나른다 (결정 D-2).

> **가정은 시간이 지나면 사실로 읽힌다.** 그래서 문서가 아니라 **산출물에 붙여** 나른다 — 문서는 아무도 다시 열지 않는다.

### 7.4 수집 0건의 "중단 vs 활동 없음" — 구분할 수 없다

heartbeat 레코드가 없어 **이벤트가 0건인 날짜가 수집 중단인지 활동 없음인지 구분할 수 없다.**

```
ingestion_days_gap              ok        공백이 몇 개인지는 안다
ingestion_gap_attribution       not_run   그것이 무엇인지는 모른다
```

**"활동 없음"이라고 쓰지 않는다.** 관측하지 않은 것을 단정하는 것이고 **0 채우기와 같은 종류의 잘못**이다. 게시물 `notices` 의 `INGESTION_GAP_UNDECIDABLE` 이 이 사실을 나른다.

### 7.5 정본 긴장 `T-1` — `results/` 접근 주체

| 출처 | 말하는 것 |
|---|---|
| `docs/data_spec.html` §17.4 | `results/` 접근 주체에 **`measurement` 를 넣지 않았다** (`decision`·`orchestration` 만) |
| `docs/data_spec.html` §9 | 데이터 품질 리포트를 **`results/` 에 쓰라고 규정한다** |

**두 문장이 충돌한다.** §9 를 따랐다 — `src/measurement/publish.py` 가 `results/` 에 쓴다.

**근거:** §17.4 의 목적은 **격리**(시뮬레이터가 모델 성능을 보지 못하게)이고, `measurement` 는 그 격리의 대상이 아니라 **창구**다. 측정 계층이 자기 산출물을 쓰는 것은 격리 위반이 아니다. `ADR-0002` 가 `results/` 하위 배치를 확정했고 `tests/test_isolation.py` 가 통과한다.

**→ `data_spec` §17.4 의 접근 주체 목록에 `measurement`(쓰기)를 추가해야 한다** (W6 항목).

---

## 8. `Ecommerce_Service` 적용 — **이슈 초안. 발행하지 않았다** (커머스가 따로 이행함)

> ★ **이 초안은 이행됐다** (2026-09-28 확인). 이벤트 기록은 커머스 `#28`, 가입일은 `#29`, 원가·할인·배송비는 `#42`·`#51`(교환 파일)로 들어왔다. 아래 본문은 **당시 초안 원문**이며 현재 상태를 말하지 않는다 — 특히 "선행 의존"의 이슈 상태와 "영구히 `NO_COST_BASIS`" 문장은 지난 사실이다.

**이 저장소는 `Ecommerce_Service` 파일을 변경하지 않았다.** 아래는 초안이며 **발행은 사용자 승인 사항**이다 (권한 L3).

<details>
<summary><strong>이슈 초안 — <code>feat: 측정 기록 계약 v1 적용 (이벤트 기록 시작)</code></strong></summary>

### 배경

`AI_ROI` 저장소가 `MEASUREMENT CONTRACT v1`(`docs/measurement_contract.md`)을 확정했다. 현재 커머스는 **이벤트를 한 건도 기록하지 않으며**, 기록을 시작하려면 아래 셋이 필요하다.

### 1. 식별자 변환 — 기록 시점에

| 현재 | 요구 | 예 |
|---|---|---|
| `test-user-1` | `^C\d{8}$` | `C00000001` |
| `dummyjson-16` | `^P\d{4}$` | `P0016` |
| `randomUUID()` (주문) | `^O\d{8}-\d{6}$` | `O20251001-000123` |

**측정 계층에 매핑 계층을 두지 않는다** — 계약은 하나이고 맞추는 쪽이 소스다. 변환하지 않으면 전 레코드가 `IDENTIFIER_FORMAT` 으로 거부된다(관용 모드에서는 수집은 계속되고 `rejected.jsonl` 에 남는다).

### 2. 이벤트 기록 — 퍼널 7단계

`docs/measurement_contract.md` §1 의 매핑을 따른다. 주의할 것 둘:

- ★ **`purchase` 에 품목(`product_id`·`quantity`·`unit_price`)을 넣지 않는다** — `NOT_APPLICABLE` 이고 거부된다. 품목은 `add_to_cart` 에 있다
- ★ **`simulator_version`·`random_seed` 를 `null` 로 둔다** — 이것이 출처 판별의 근거다 (`MEA-002`)
- **캐러셀 자동 전환을 `page_view` 로 찍지 않는다** (§7.2)

### 3. 타임존

오프셋을 붙여 기록한다. 현재 UTC(`orders.ts:116`)로 기록하는데 **그대로도 된다** — 측정 계층이 저장 시 KST 로 정규화한다. **오프셋이 없는 표기만 거부된다.**

### 선행 의존

- **`#29`**(OPEN) — *"feat: 고객 모델에 가입일 추가와 라이프사이클 기준 확보"*. `signup_date` 가 없으면 `cohort_retention_rate` 와 `P_eligible` 계열이 계산 불가로 남는다
- **`#24`** — 상품 원가(`unit_cost`). 없으면 `cogs`·`contribution_profit` 이 영구히 `NO_COST_BASIS` 다
- **`#28`** — 이벤트 기록 착수

### 완료 조건

```bash
# AI_ROI 저장소에서
python3 -m src.measurement.publish
# → results/index.json 의 verdict 가 SINK_EMPTY 가 아니어야 한다
```

</details>

---

## 9. 검증 — 이 문서가 코드와 일치하는가

```bash
# ① 이 문서의 표가 schema.py 와 일치하는지 (자동 대조)
python3 -m unittest tests.test_measurement_contract -v

# ② 전체
python3 -m unittest discover -s tests

# ③ 생성 문서와 코드 일치
python3 scripts/gen_event_schema_doc.py | diff - docs/event_schema.md
```

**`tests/test_measurement_contract.py` 가 이 문서를 파싱해 `schema.py` 와 대조한다.** 문서가 낡으면 테스트가 실패한다 — *"문서는 검증되지 않는다"* 를 깨는 유일한 방법이다.

---

## 10. 이 계약이 Lock 되면

**`EVENT SCHEMA v1` Lock 범위는 `events` 테이블에 한정된다** (결정 D-8). 나머지 6개 테이블(`customers`·`products`·`orders`·`order_items`·`campaigns`·`treatments`)은 이 Lock 의 대상이 아니다. 그중 `customers`·`products`·`orders`·`order_items` 의 **교환 형식**은 별도 계약 `docs/contracts/commerce-exchange/v1/`(`#100`)이 정한다 — `campaigns`·`treatments` 는 여전히 미정의다.

Lock 이후 아래를 바꾸면 `FREEZE-003` — **버전 상향 + 전 데이터 재생성 + Baseline 부터 전 전략 재실행**:

```
event_type 16종 · EVENT_FIELDS 22컬럼 · 이벤트별 필수/선택 매트릭스
category 5종 · page_type 8종 · 식별자 정규식 9종 · 타임존 정책
```

**Lock 되지 않는 것:** 이탈 임계값 28/42/60 (가설값 · 결정 D-5) · KPI 역할 배정(Primary/Guardrail/Secondary — GATE 2 · 결정 D-4).

**현재 상태는 `results/freeze_status.json` 이 준다.** `overall: not_started` 이고 **C1 은 GATE 1 을 통과시키지 않는다** — 부분 봉인만 한다.
