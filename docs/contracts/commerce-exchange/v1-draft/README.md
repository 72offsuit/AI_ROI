# 커머스 교환 파일 계약 — **v1 초안**

> ⚠ **초안이다. 커머스와 합의되지 않았다.** 이슈 [`#100`](https://github.com/72offsuit/AI_ROI/issues/100) 의 수용 기준 ①이 합의를 요구하며, 이 문서가 그 **제안**이다. 합의 전까지 이 계약에 맞춰 데이터를 만들지 않는다.
>
> 이슈 본문이 *"GATE 1 Lock 전에는 현재 계약을 초안으로 표시하고 변경 시 양쪽 검사를 갱신한다"* 고 초안 단계를 이미 전제한다.

---

## 0. 왜 필요한가

`purchase` 이벤트는 **주문 단위 1행**이고 `product_id`·`quantity`·`unit_price` 가 `NOT_APPLICABLE` 이다 — 값이 있으면 `validate_event()` 가 거부한다. 즉 **한 주문의 품목을 이벤트 안에서 재구성할 방법이 없다.**

그래서 두 가지가 막혀 있다:

| | 무엇이 막혔나 | 현재 상태 |
|---|---|---|
| **COGS** | `Σ(unit_cost × quantity)` 를 계산할 원가 근거가 없다 | `cogs()` → `NO_COST_BASIS` · `contribution_profit` → `unavailable` |
| **DQ-09** | `order_amount = Σ(unit_price × quantity) − discount` 를 대조할 수 없다 | `not_run` · `PRECONDITION_MISSING` |

`DQ-09` 는 **두 겹**이다. 품목뿐 아니라 **`discount` 필드도 이벤트 스키마 22컬럼에 없다.** 그래서 교환 파일이 둘 다 실어야 한다.

> ★ `add_to_cart` 로 근사하지 않는다. `remove_from_cart` 가 있고, 담았지만 사지 않은 품목이 있고, 결제 실패가 있다. **근사하면 COGS 가 그럴듯하게 틀린다** — 틀린 줄 모르는 채로.

## 1. 무엇을 바꾸지 않는가

**이벤트 계약은 그대로다.** `purchase` 에 품목 필드를 추가하지 않는다.

`src/measurement/schema.py` 는 **GATE 1 정본 4종 중 하나**이고, 건드리면 봉인 재기록(사람 서명)이 필요하다. 그리고 `DATA-003` 22컬럼·`event_type` 16종은 `tests/test_schema.py` 가 `assertEqual` 로 고정한다 — 변경은 `Plan/` SRS 개정을 요구하며 이 팀의 권한 밖이다.

**비이벤트 교환 파일**로 가는 이유가 그것이다.

---

## 2. 배치와 형식

```
data/commerce/
  manifest.json      이 묶음이 무엇이고 언제 어디서 왔는가
  customers.jsonl
  catalog.jsonl
  orders.jsonl
  order_items.jsonl
```

- **JSONL** (한 줄에 객체 하나, UTF-8). 사람이 눈으로 확인할 수 있고 스트리밍으로 읽힌다
- 시각은 **KST 오프셋을 명시한 RFC 3339** (`2026-01-01T10:00:00.000+09:00`). 이벤트와 같은 규약이다
- 금액은 **원 단위 정수**. 부동소수를 쓰지 않는다 — 0.1 을 세 번 더하면 0.30000000000000004 다

## 3. ★ 주문 시점 원가 (order-time cost snapshot)

이 계약에서 가장 중요한 결정이다.

```
order_items.unit_cost   ← 그 주문이 일어난 시점의 원가. COGS 는 이 값만 쓴다
catalog.unit_cost       ← 현재 원가. 참고용이며 COGS 에 쓰지 않는다
```

**원가는 시간에 따라 변한다.** 3개월 전 주문의 COGS 를 오늘의 카탈로그 원가로 계산하면, 원가가 오른 상품은 이익이 과소평가되고 내린 상품은 과대평가된다. 그 오차는 **상품별로 방향이 달라** 총합에서 상쇄되지도 않는다.

`unit_price` 도 같다 — 할인·가격 변동이 있으므로 주문 시점 값을 싣는다.

> 커머스가 주문 시점 원가를 보관하지 않는다면 **그 사실이 이 계약의 가장 중요한 논의 대상**이다. 카탈로그 현재가로 대체하는 것은 선택지가 아니라 **다른 지표를 만드는 것**이고, 그렇게 하려면 그 사실이 산출물에 실려야 한다.

## 4. ID 결합 규칙

```
orders.order_id        ↔  purchase 이벤트의 order_id       ^O\d{8}-\d{6}$
orders.customer_id     ↔  이벤트의 customer_id             ^C\d{8}$
order_items.order_id   →  orders.order_id
order_items.product_id →  catalog.product_id
customers.customer_id  ↔  이벤트의 customer_id
```

**앞의 두 형식은 협상 대상이 아니다.** `src/measurement/schema.py` 가 이미 정규식으로 고정하고 있고 그것은 GATE 1 정본이다. 커머스의 내부 id 가 다른 형식이면 **교환 파일에서 이 형식으로 변환해 내보낸다.**

## 5. ★ 없을 때·부족할 때 — 무엇을 하는가

이 절이 이슈 `#100` 수용 기준 ④다. **여기서 0 으로 채우지 않는다.**

| 상황 | 판정 | 왜 |
|---|---|---|
| `data/commerce/` 자체가 없다 | `DQ-09` `not_run` · `PRECONDITION_MISSING`<br>`cogs()` `NO_COST_BASIS` (blocked_by `table:order_items`) | **오늘의 상태다.** 대조하지 않은 것이지 위반이 아니다 |
| 교환 파일은 있는데 **어떤 주문에 품목이 없다** | `DQ-09` **위반** (그 주문) | 계약이 모든 주문의 품목을 약속했다. 없으면 약속이 깨진 것이고 `not_run` 이 아니다 |
| 품목은 있는데 `unit_cost` 가 `null` | 그 주문만 `NO_COST_BASIS` (blocked_by `field:unit_cost`) | **품목을 모르는 것과 원가를 모르는 것은 다르다.** `OrderItem` 이 이미 그 둘을 나눈다 — 해소 방법이 다르기 때문이다(테이블이 필요하다 vs 컬럼이 필요하다) |
| 품목·원가 다 있는데 **등식이 안 맞는다** | `DQ-09` **위반** | 이벤트의 `order_amount` 와 교환 파일의 합계가 어긋난다 — 둘 중 하나가 틀렸고, 어느 쪽인지는 사람이 본다 |
| 주문이 교환 파일에만 있고 이벤트에 없다 (또는 반대) | `DQ-03` 참조 무결성 위반 | 고아 레코드다 |

> ★ **`not_run` 과 `위반` 을 가르는 것이 이 표의 요점이다.** 둘을 같은 값으로 적으면 *"대조하지 않았다"* 가 *"대조했고 문제없다"* 로 읽히거나 그 반대가 된다. 이 저장소가 `vacuous` · `met: null` · `verification: not_run` 을 두는 것과 같은 규율이다.

## 6. 금액 등식 (`DQ-09`)

```
order_amount  ==  Σ(unit_price × quantity)  −  discount
   ↑ 이벤트                ↑ 교환 파일            ↑ 교환 파일
```

**두 출처를 맞대는 대조 장치다.** 한 출처 안에서만 계산하면 그 출처가 스스로 일관되기만 하면 통과한다 — 이 검사의 값어치는 **이벤트와 교환 파일이 같은 주문을 같게 말하는지** 보는 데 있다.

`order_amount` 는 **할인 후** 금액이다 (`schema.py`, 그리고 순매출 기준 — `docs/decisions/DR-101-revenue-basis.md`). 등식이 `− discount` 인 이유가 그것이다.

> ★ 그래서 **`discount` 는 "있으면 좋은 것" 이 아니라 필수다.** `#100` 초기 논의에서 선택 사항으로 적었던 것을 정정한다 — `DQ-09` 가 그것 없이는 성립하지 않는다.

## 7. 이 계약이 여는 것

```
주문 시점 원가  →  COGS 계산 가능  →  contribution_profit 계산 가능
                                    →  revenue_up_profit_down 가드레일이 발동 가능
discount       →  DQ-09 실행 가능
               →  ROI 분모의 쿠폰 금액이 유도값(D-16)에서 실측으로
```

`docs/measurement_contract.md` 는 *"추정 COGS 로 계산한 기여이익은 `order_amount` 의 **상수배**라 그 가드레일이 **원리적으로 발동할 수 없다**"* 고 적어 두었다. 이 계약이 그 문장을 지운다.

## 8. 합의가 필요한 것 — 커머스에 묻는다

1. **주문 시점 원가를 보관하는가?** (§3) 아니라면 무엇이 가능한가
2. **`discount` 를 주문 단위로 낼 수 있는가?** 품목 단위 할인이 있다면 어떻게 배분하는가
3. `order_id`·`customer_id` 를 위 형식으로 변환해 내보낼 수 있는가 (§4)
4. 배송비를 낼 수 있는가 — **이 초안에 넣지 않았다.** 넣으면 가정 `A-SHIPPING`(규칙 유도)이 해소되지만, 읽는 곳 없는 필드를 먼저 만들지 않는다 (`#63`). 필요가 확인되면 그때 추가한다
5. 묶음의 기준 시각과 갱신 주기 — 증분인가 전량인가

## 9. 강제

| | |
|---|---|
| 스키마 형식 | `tests/test_commerce_exchange_contract.py` |
| 없을 때의 거동 | 같은 파일 (수용 기준 ④) |
| 실제 소비 · COGS 배선 | **아직 없다.** 합의 후 (`#100` B 조각) |
