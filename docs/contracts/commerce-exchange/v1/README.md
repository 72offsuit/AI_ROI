# 교환 파일 계약 — **v1** (커머스 · 시뮬레이터)

> **합의됨** — 2026-09-28, 이슈 [`#100`](https://github.com/72offsuit/AI_ROI/issues/100) · [`Ecommerce_Service #51`](https://github.com/72offsuit/Ecommerce_Service/issues/51). 금액 기준은 [`#106`](https://github.com/72offsuit/AI_ROI/issues/106)에서 정했다. 시뮬레이터도 같은 계약을 쓴다 — [`#117`](https://github.com/72offsuit/AI_ROI/issues/117) (2026-09-29).
>
> 생산자: `Ecommerce_Service` `npm run exchange:export -- <디렉터리>` (커머스 쪽 설명은 그 저장소 `docs/AI_ROI_EXCHANGE.md`) · 시뮬레이터(`src/simulator/`, §11).
> 소비자: `src/measurement/exchange.py` → `publish.assemble_orders()` · `validate` 의 `DQ-02`·`03`·`05`·`09`.
>
> 디렉터리 이름(`commerce-exchange`)은 처음 커머스용으로 만들어진 흔적이다. 계약은 두 출처 공용이다.

---

## 0. 왜 필요한가

`purchase` 이벤트는 **주문 단위 1행**이고 `product_id`·`quantity`·`unit_price` 가 `NOT_APPLICABLE` 이다 — 값이 있으면 `validate_event()` 가 거부한다. 즉 **한 주문의 품목을 이벤트 안에서 재구성할 방법이 없다.** 그리고 `discount` 필드는 이벤트 스키마 22컬럼에 없다.

그래서 교환 파일 없이는 두 가지가 막힌다:

| | 무엇이 막히나 | 교환 파일이 없을 때 |
|---|---|---|
| **COGS** | `Σ(unit_cost × quantity)` 를 계산할 원가 근거가 없다 | `cogs()` → `NO_COST_BASIS` · `contribution_profit` → `unavailable` |
| **DQ-09** | `order_amount = Σ(unit_price × quantity) − discount` 를 대조할 수 없다 | `not_run` · `PRECONDITION_MISSING` |

> ★ `add_to_cart` 로 근사하지 않는다. `remove_from_cart` 가 있고, 담았지만 사지 않은 품목이 있고, 결제 실패가 있다. **근사하면 COGS 가 그럴듯하게 틀린다** — 틀린 줄 모르는 채로.

## 1. 무엇을 바꾸지 않는가

**이벤트 계약은 그대로다.** `purchase` 에 품목 필드를 추가하지 않는다.

`src/measurement/schema.py` 는 **GATE 1 정본 4종 중 하나**이고, 건드리면 봉인 재기록(사람 서명)이 필요하다. `DATA-003` 22컬럼·`event_type` 16종은 `tests/test_schema.py` 가 `assertEqual` 로 고정한다 — 변경은 `Plan/` SRS 개정을 요구한다. **비이벤트 교환 파일**로 가는 이유가 그것이다.

## 2. 배치와 형식

```
data/commerce/            ← 커머스 묶음. Sink 루트(data/raw)의 형제. publish --exchange 로 바꿀 수 있다
data/simulator_exchange/  ← 시뮬레이터 묶음. 같은 형식. publish --simulator-exchange 로 바꿀 수 있다
  manifest.json           이 묶음이 무엇이고 언제 어디서 왔는가
  customers.jsonl
  catalog.jsonl
  orders.jsonl
  order_items.jsonl
```

★ **묶음은 자기 출처의 이벤트에만 붙는다.** 두 출처의 `order_id` 형식이 같으므로(`^O\d{8}-\d{6}$`) 같은 ID 가 양쪽에 있을 수 있다 — 그래도 커머스 묶음의 품목은 커머스 주문에만, 시뮬레이터 묶음의 품목은 시뮬레이터 주문에만 붙는다(#117).

- **JSONL** (한 줄에 객체 하나, UTF-8)
- 시각은 **KST 오프셋을 명시한 RFC 3339** (`2026-01-01T10:00:00.000+09:00`). 이벤트와 같은 규약이다
- 금액은 **원 단위 정수**. 부동소수를 쓰지 않는다
- 갱신은 **전량 스냅샷**이다(`manifest.mode = "full"`). 증분은 필요가 확인되면 v2 에서 다룬다

`manifest.json`:

| 필드 | 뜻 |
|---|---|
| `contract` | `"commerce-exchange/v1"`. 다르면 묶음 전체를 거부한다 |
| `source` | ★ **필수.** 커머스 `"Ecommerce_Service"` · 시뮬레이터 `"simulator"`. 놓인 자리의 출처와 다르면 묶음 전체를 거부한다 — 다른 출처의 품목이 붙는다 |
| `source_commit` | 생산 코드의 커밋 (시뮬레이터는 `simulator_commit` 과 같은 값) |
| `generated_at` | 묶음을 만든 시각 (KST) |
| `mode` | `"full"` |
| `files` | 파일별 행 수. **실제 행 수와 다르면 묶음 전체를 거부한다** — 잘린 파일을 읽으면 COGS 가 일부 주문의 합계인데 전체처럼 보인다 |

## 3. ★ 주문 시점 원가 (order-time cost snapshot)

```
order_items.unit_cost   ← 그 주문이 일어난 시점의 원가. COGS 는 이것만 쓴다
catalog.unit_cost       ← 현재 원가. 참고용이며 COGS 에 쓰지 않는다
```

**원가는 시간에 따라 변한다.** 3개월 전 주문의 COGS 를 오늘의 카탈로그 원가로 계산하면, 원가가 오른 상품은 이익이 과소평가되고 내린 상품은 과대평가된다. 그 오차는 **상품별로 방향이 달라** 총합에서 상쇄되지도 않는다. `unit_price` 도 같다 — 주문 시점 값을 싣는다.

커머스는 `order_items.unit_cost_krw` 를 주문 시점에 NOT NULL 로 저장한다(#42). 상품 원가를 바꿔도 과거 주문의 값이 변하지 않는 것을 양쪽 테스트가 확인한다.

## 4. 파일별 필드

| 파일 | 필드 | 비고 |
|---|---|---|
| `customers` | `customer_id` · `signup_date` | 가입일은 `YYYY-MM-DD` (KST) |
| `catalog` | `snapshot_at` · `product_id` · `category` · `selling_price` · `unit_cost` · (`name`) | 필드명은 커머스가 먼저 내보내던 `catalog:export`(#43)에 맞췄다 |
| `orders` | `order_id` · `customer_id` · `ordered_at` · `order_amount` · `discount` · `shipping_fee` · `shipping_charged` | 아래 §5 |
| `order_items` | `order_id` · `line_no` · `product_id` · `quantity` · `unit_price` · `unit_cost` | `(order_id, line_no)` 유일. 순번은 재실행해도 같다 |

## 5. 금액의 뜻

| 필드 | 뜻 |
|---|---|
| `order_amount` | **할인 후 상품 합계. 배송비 제외.** 같은 주문의 `purchase` 이벤트 `order_amount` 와 같은 값이다 (#106) |
| `discount` | 쿠폰 할인액. 할인이 없으면 `0` — 결손이 아니라 "할인 0원"이라는 측정값이다. `coupon_cost`(ROI 분모)가 처치 단가 유도보다 먼저 쓴다 (#108) |
| `shipping_fee` | 주문 시점 정책 배송비 — 무료배송이 아니었다면 받았을 금액 |
| `shipping_charged` | 실제로 받은 배송비 |

- **배송보조 = `shipping_fee − shipping_charged`.** 교환 파일이 있는 주문은 이 관측값을 쓰고, 없는 주문만 D-3 규칙(가정 `A-SHIPPING`)으로 유도한다. 섞이면 `derived: true` 로 싣는다.
- **매출은 이벤트의 `order_amount` 다.** 교환 파일의 금액으로 바꾸지 않는다 — 둘이 같은지를 `DQ-09` 가 본다.
- 커머스의 기여이익 리포트(`economics:report`)는 총매출 표시(매출 − COGS − 할인 − …)이고 AI_ROI 는 순매출 표시(매출 − COGS − …)다. **같은 주문에서 같은 값을 낸다** — `tests/test_commerce_exchange_contract.py` 가 실제 커머스 산출물로 확인한다 (`DR-101`).

## 6. ID 결합 규칙

```
orders.order_id        ↔  purchase 이벤트의 order_id       ^O\d{8}-\d{6}$
orders.customer_id     ↔  이벤트의 customer_id             ^C\d{8}$
order_items.order_id   →  orders.order_id
order_items.product_id →  catalog.product_id                ^P\d{4}$
customers.customer_id  ↔  이벤트의 customer_id
```

**이 형식은 협상 대상이 아니다.** `src/measurement/schema.py` 가 정규식으로 고정하고 있고 그것은 GATE 1 정본이다. 커머스는 내부 ID 를 이벤트 기록에 쓰는 매핑으로 변환해 내보낸다.

## 7. `DQ-09` — 무엇을 대조하는가

교환 파일의 **주문마다** 셋을 본다. 하나라도 어긋나면 그 주문이 위반이다.

| | 조건 | 어긋나면 |
|---|---|---|
| ① | 품목이 1줄 이상 있다 | 계약이 모든 주문의 품목을 약속했다 |
| ② | `order_amount = Σ(unit_price × quantity) − discount` | 교환 파일이 스스로 모순이다 |
| ③ | 같은 `order_id` 의 `purchase` 이벤트가 있고 그 `order_amount` 가 ②와 같다 | **두 출처가 같은 주문을 다르게 말한다** |

★ ③이 이 검사의 값어치다. 한 출처 안에서만 계산하면 그 출처가 스스로 일관되기만 하면 통과한다. 커머스 이벤트가 할인 전 금액을 싣고 있던 것(#106)은 ②로는 안 보이고 ③으로만 보인다.

③의 `purchase` 는 **그 묶음과 같은 출처의 이벤트에서만** 찾는다(#116 · #117) — `publish` 가 출처별로 짝지어 넘긴다. 어떤 묶음에 같은 출처의 `purchase` 가 한 건도 없으면(예: 시뮬레이터 전용 데이터 옆에 커머스 묶음만 있을 때) 그 묶음은 대조할 상대가 없으므로 대조하지 않고 사유에 남긴다 — 위반이 아니다. 모든 묶음이 그렇다면 `not_run` 이다. 두 출처가 같은 `order_id` 를 써도 다른 출처의 금액과 대조하지 않는다. 위반 사례에는 `[커머스]`·`[시뮬레이터]` 로 출처가 붙는다.

## 8. 없을 때·부족할 때

**0 으로 채우지 않는다.**

| 상황 | 판정 |
|---|---|
| `data/commerce/` 자체가 없다 | `DQ-09` `not_run` · `PRECONDITION_MISSING`, `cogs()` `NO_COST_BASIS` (blocked_by `table:order_items`) — 대조하지 않은 것이지 위반이 아니다 |
| 형식 위반 · 매니페스트 행 수 불일치 · 계약 판 불일치 · 모르는 주문의 품목 | 묶음 전체 거부 (`ExchangeContractError`, 종료 코드 3) |
| 어떤 주문에 품목이 없다 | `DQ-09` 위반 (그 주문) |
| 품목은 있는데 `unit_cost` 가 `null` | 그 주문만 `NO_COST_BASIS` (blocked_by `field:unit_cost`) — 품목을 모르는 것과 원가를 모르는 것은 해소 방법이 다르다 |
| 이벤트에는 있는데 교환 파일에 없는 주문 | 그 주문의 `cogs()` `NO_COST_BASIS` — 품목이 붙지 않는다 |

## 9. 명부 대조 — `DQ-02` · `DQ-03` · `DQ-05` (#110)

`customers.jsonl`·`catalog.jsonl`·`orders.jsonl` 은 **그 출처의 명부**다. 묶음이 하나라도 있으면 세 검사가 실행되고, 없으면 `not_run` 이다. 각 명부는 **같은 출처의 이벤트와만** 대조한다.

| 검사 | 무엇을 | 범위 |
|---|---|---|
| `DQ-02` | `order_id` 전역 유일 | `orders.jsonl` 전 행. 중복이 있으면 로더가 묶음 전체를 거부하므로, 읽힌 묶음은 통과한 것이다 |
| `DQ-03` | 고아 `customer_id`·`product_id` | **같은 출처 이벤트만** — 묶음이 없는 출처의 이벤트는 대상이 아니다. 출처는 `publish.py` 가 나눠 넘긴다 |
| `DQ-05` | 가입일 이전 이벤트 | 명부에 있는 고객의 같은 출처 이벤트. **KST 날짜 단위** — 가입 당일 가입 시각 이전의 이벤트는 잡지 못한다 |

- **명부는 `manifest.generated_at` 까지를 책임진다.** 그 뒤의 이벤트는 대조하지 않고 건수를 `reason_detail` 에 싣는다 — 스냅샷 이후 가입한 고객이 거짓 고아가 되지 않게 한다. 위반도 통과도 아니다
- 로더는 `customers` 의 중복 `customer_id`, `catalog` 의 중복 `product_id`, `generated_at` 이 없는 매니페스트를 거부한다

결정: `docs/decisions/DR-110-roster-checks.md`

## 10. 강제

| | |
|---|---|
| 스키마 형식 · 반례 거부 · 로더 필드 표 일치 | `tests/test_commerce_exchange_contract.py` |
| 로더 거부 규칙 | 같은 파일 `TestReadExchange` |
| `DQ-09` | 같은 파일 `TestAmountEquation` |
| 실제 커머스 산출물 종단 (`EventSink` → `publish()`) | 같은 파일 `TestEndToEndWithTheRealCommerceSample` · 픽스처 `tests/fixtures/commerce_exchange_v1/` |
| 명부 대조 `DQ-02`·`DQ-03`·`DQ-05` | `tests/test_roster_checks.py` |
| 출처별 묶음 — 자리 거부 · 짝짓기 · 두 출처 종단 | `tests/test_exchange_sources.py` |

## 11. 시뮬레이터가 지킬 것 (#117 · `docs/decisions/DR-117-simulator-exchange.md`)

| | 규칙 | 왜 |
|---|---|---|
| 위치·표지 | `data/simulator_exchange/`, `manifest.source = "simulator"` | 커머스 자리에 놓이면 거부된다 |
| `order_amount` | 할인 후 · 배송비 제외 — **같은 주문의 `purchase` 이벤트와 같은 값** | `DQ-09` ③이 대조한다 |
| 카탈로그 | 정본 설정 `config/economic_config.yaml` 의 `product_margin`(카테고리별 원가율 · 중앙가격 · 풀 크기)으로 **생성** | 봉인된 경제 규칙이 이 용도로 정의돼 있다. 원가율은 커머스 카탈로그와 같다 |
| `order_items.unit_cost` | 주문 시점의 원가 — 카탈로그 원가를 그대로 싣되, 주문 뒤에 원가가 바뀌어도 과거 주문 값은 바꾸지 않는다 | COGS 는 이 값만 쓴다(§3) |
| `discount` | 쿠폰 처치 단가 그대로 — `T2` 3,000원(30,000원 이상) · `T3` 7,000원(50,000원 이상) | 봉인 기록의 가정 `A-DISCOUNT` 가 이것을 전제한다. 다르게 하려면 먼저 리드와 정한다 |
| `shipping_fee` · `shipping_charged` | **커머스 정책을 따른다** — 할인 전 상품 합계 40,000원 이상이면 일반 무료배송, `T1` 은 그 미만 주문의 배송비 면제. `shipping_fee` 는 정책 배송비(3,000원), `shipping_charged` 는 실제로 받은 금액 | 커머스와 같은 환경. 측정 계층의 유도 규칙(D-3)은 묶음이 없는 주문의 대체 규칙으로만 남는다 |
| `customers.signup_date` | 가상 고객의 가입일 (KST 날짜) | `DQ-05`·`DQ-03` 이 시뮬레이터 이벤트에도 돈다 |
| ID | 이벤트와 같은 값 — `customer_id`·`order_id`·`product_id` | 결합 규칙(§6) |
| 숨김 정보 | 싣지 않는다 — Hidden Trait·처치 반응·참 CATE 는 묶음 어디에도 없다 | 원가·가격·할인·배송비는 실제 커머스도 아는 **관측 가능한 값**이라 흘러도 된다. 숨김 정보는 `data/hidden/`·`data/ground_truth/` 에만 |

묶음 생성 시점·주기(창마다 전량인가)는 시뮬레이터 팀이 `S1`(#75)·`S4`(#78)에서 정한다 — 계약은 `mode: "full"` 전량 스냅샷을 전제한다.
