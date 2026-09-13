---
story_key: M-03
epic: 범위 M — 측정 계층 (이슈 #42)
issue: "#47"
title: 경제 규칙 v1 — economic_config.yaml + economics.py + 창구 중립성 테스트
status: done   # W5 Phillip 완료 — AC-1~9 전부. test_neutrality 8건 negative control 확인
owner: Phillip (W5-A)
phase: 2
blocked_by: ["M-02 (#54) — Category 어휘"]
blocks: ["M-06 (게시)", "M-09 (#49)"]
user_decisions_required: ["D-1", "D-2", "D-16"]
source_hash: 55894406a021293f
source_files: 18
---

# M-03 · 경제 규칙 v1 (`#47`)

> **이 파일만 읽고 구현한다.** 인용에는 전부 `[Source: 경로#절]` 을 붙였다.

---

# 0. 작업 전 — 매번 확인하는 3줄 *(task-graph §3 T3.2)*

| # | 절대 제약 | 어기면 |
|---|---|---|
| **①** | **git·이슈 권한은 L1(제안만)이다.** commit·push 는 사용자가 **"커밋해"/"푸시해"** 를, 이슈 생성·수정·PR 은 **"이슈 만들어"/"PR 올려"** 를 명시한 뒤에만. **승격을 스스로 추론하지 않는다.** merge · Issue close · 브랜치 삭제 · `push --force` · `reset --hard` · `rebase` 는 **항상 개별 승인**. `main` 직접 커밋 금지 · `git add -A` 금지(경로 명시) · `git add Plan` 금지 | 사용자 결정을 대신한 것이 된다 |
| **②** | **`Ecommerce_Service` 파일 변경 0건.** 별도 저장소이고 사용자가 명시적으로 제외했다. **읽기는 허용**된다. 편집이 필요해지면 **멈추고 보고한다** | charter §5 위반 |
| **③** | **결손을 0 으로 채우지 않는다.** 명시적으로 기록하고 의존 지표는 **계산 불가로 표시**한다. **미실행 검증을 통과로 표시하지 않는다** — 실행 불가는 `BLOCKED` 로 **이유와 함께** | ★ **이 프로젝트의 USP-1 이 끝난다** |

`[Source: AGENTS.md#반드시-지킬-것]` · `[Source: docs/GIT_WORKFLOW.md#6]` · `[Source: .agent-team/00-plan/charter.md#6.1]` · `[Source: .agent-team/00-plan/task-graph.md#3 W3]`

---

# 1. 메타

| | |
|---|---|
| **대상 이슈** | `#47` — OPEN (2026-09-11 라이브 확인) |
| **담당** | Phillip · W5-A |
| **Phase** | **2** — `#46`(M-04)과 병렬 |
| **차단** | **사용자 결정 D-1 · D-2** (§9.4) · M-02 의 `Category` 어휘 |
| **차단하는 것** | M-06(게시) · M-09(`#49` Lock 대상 `ECONOMIC RULE v1`) |
| **커밋 type** | `feat` |

> ## ★ 이 스토리 한 줄
> **원가율을 곱해 COGS 를 추정하지 않는다. 가르는 기준은 출처가 아니라 원가 근거의 유무다.**
> 이 두 문장을 코드가 **어길 수 없게** 만드는 것이 작업의 전부다.

---

# 2. 스토리

> **`P-리드`**(사이클 리드)**로서 나는 원가가 없는 주문에 기여이익 숫자가 붙지 않기를 원한다.**
> 왜냐하면 `MEA-003` 이 *"원가가 없으면 기여이익이 계산되지 않는데 이를 0으로 채우면 이익이 매출과 같아져 잘못된 결론이 조용히 만들어진다"* 고 경고했고, **원가율로 추정하면 `revenue_up_profit_down` 가드레일이 원리적으로 작동할 수 없게** 되기 때문이다.
> `[Source: .agent-team/03-service-planning/user-stories.md#US-7]`

> **`P-AI`**(다음 사이클 decision 개발자)**로서 나는 발송 비용이 반응 여부와 무관하게 전원 계상되기를 원한다.**
> 왜냐하면 이 구분이 없으면 *"반응하지 않은 고객에게 쓴 돈"* 이 사라져 **ROI 가 과대평가되기** 때문이다.
> `[Source: .agent-team/03-service-planning/user-stories.md#US-8]`

---

# 3. 인수 조건 (AC)

## AC-1 · `config/economic_config.yaml` — 6블록

- [ ] `product_margin` — 카테고리 5종의 원가율·기여마진율·가격 중앙값·구매빈도 가중·pool 수
- [ ] `treatment_cost` — T0~T4 단위 비용·조건·발생 시점
- [ ] `cost_accounting` — `message_cost` · `campaign_fixed_cost` · `discount_cost` · `N_targeted` 정의
- [ ] `shipping` — 배송비 3,000원 · 무료배송 기준 40,000원
- [ ] `ai_investment` — 개발·컴퓨트·운영·모니터링·상각 12개월
- [ ] `assumptions` — `refund_adjusted: false` 등 명시 가정
- [ ] **카테고리 키가 `Category` Enum 과 같은 어휘를 쓴다** (M-02 확정 · US-2 인수조건 4)
- [ ] **AI 투자비용이 가정 기반 추정치임을 주석에 남긴다** (인건비 400만원/월 등에 외부 출처가 없다)

## AC-2 · `EC-1`·`EC-2` — 원가 근거 규칙 ★

- [ ] `cogs`·`contribution_profit` 이 **저장된 `unit_cost` 로만** 계산된다
- [ ] 원가 근거가 없는 주문에 **`NO_COST_BASIS`** 로 계산 불가가 반환된다 — `0` 도, 추정값도 아니다
- [ ] 판정 기준이 **`has_cost_basis(order)`** 이고 **출처(`source`)를 묻지 않는다**
- [ ] `revenue` 는 원가 유무와 무관하게 계산된다

## AC-3 · 창구 중립성 — **검사 가능해야 한다** ★

- [ ] **`src/measurement/economics.py` 에 `commerce`·`simulator` 문자열이 없다**
- [ ] **`economics.py` 가 `product_margin` 원가율을 참조하지 않는다** (`cost_rate`·`margin_rate`·`product_margin` 식별자·문자열 0건)
- [ ] `economics.py` 가 `open`·`Path`·`json`·`csv`·`gzip` 을 import 하지 않는다 (순수 함수)
- [ ] 위 셋을 **`tests/test_neutrality.py` 가 소스 검사로 고정한다**

## AC-4 · `EC-3` 발생주의 3원칙

- [ ] `message_cost` 가 **발송 시점에 처치군 전원**에게 계상된다 (`push_sent` 기준, **반응 무관**)
- [ ] `discount_cost` 가 **쿠폰이 실제 사용된 주문에만** 계상된다 (`coupon_use` 기준)
- [ ] 최소주문금액 미달로 쿠폰이 미사용된 경우 **메시지 비용만 발생**하고 할인 비용은 발생하지 않는다
- [ ] **역효과 고객(Sleeping Dog)에게 쓴 비용도 계상**된다 — 지우지 않는다

## AC-5 · `EC-4` `N_targeted`

- [ ] `N_targeted` = **실제로 메시지가 발송된 고객 수**(`push_sent` 발생 고객 수)로 정의된다
- [ ] **배정된 처치군 전체가 아니다** · **반응한 고객 수가 아니다**
- [ ] `N_targeted == 0` 이면 **나눗셈을 하지 않고** 캠페인 단위 비용으로 남긴다

## AC-6 · `EC-5` 계획값 ≠ 실현값

- [ ] `expected_cost_per_customer`(계획)와 `realized_cost_per_customer`(실현)가 **다른 이름**이다
- [ ] 기대 비용(`30 + 0.30 × 7,000 ≈ 2,130원`)을 **실현 비용 집계에 쓰지 않는다**

## AC-7 · `EC-7` ROI 해석 규칙

- [ ] `revenue_up_profit_down(strategy, baseline)` 판정이 구현된다
- [ ] `revenue(s) > revenue(b) AND contribution_profit(s) < contribution_profit(b)` 이면 **참**
- [ ] 두 값 중 하나라도 계산 불가면 **판정도 계산 불가**다 — `False` 를 돌려주지 않는다 (§4.7)

## AC-8 · 하드코딩 0건

- [ ] **코드에 하드코딩된 금액이 0건**이다 (`#47` 완료 조건)
- [ ] 모든 비용 항목이 config 에 있다

## AC-9 · 회귀 없음

- [ ] `python3 -m unittest discover -s tests` — 기준선 46건 회귀 0
- [ ] `python3 -m unittest tests.test_isolation -v` — 통과
- [ ] **PyYAML 없이도 `tests/test_economics.py` 가 전부 돈다** (§4.8)
- [ ] `python3 .agent-team/04-architecture/tools/check_ownership.py` — PASS

---

# 4. 개발 컨텍스트 (`developer_context`)

## 4.1 ★ EC-1 — 왜 원가율을 곱하면 안 되는가 (제1원리)

**원가율은 생성 파라미터이지 추정 파라미터가 아니다.**

`data_spec` §6.1 이 규정하는 것은 *"시뮬레이터가 240개 상품 pool 을 만들 때 카테고리별로 이 원가율을 적용해 `unit_cost` 를 정한다"* 이다. 그 결과가 `data/raw/products.parquet` 에 **고정 저장**된다.
COGS 계산은 그 **저장된 값**을 읽는다 — `COGS_i = Σ(unit_cost × quantity)_i`.

| 방향 | 무엇인가 | 정당한가 |
|---|---|---|
| 원가율 → `unit_cost` 생성 → 저장 → `Σ(unit_cost × qty)` | **생성** — 사실을 만들고 기록한 뒤 그 기록을 읽는다 | ✅ |
| `order_amount` × 원가율 → COGS | **추정** — 기록이 없는 곳에 값을 만들어 넣는다 | ❌ |

> **0 으로 채우는 것과 74% 로 채우는 것은 같은 종류의 잘못이다.**
> 0 은 이익 = 매출을 만들고, **74% 는 모든 주문의 마진율이 정확히 26% 인 세계를 만든다. 후자가 더 그럴듯해서 더 위험하다.**

**결정적 부수 효과:** 추정 COGS 로 계산한 기여이익은 `order_amount` 의 **상수배**다. 그러면 `contribution_profit` 은 `revenue` 와 **완전히 같은 정보만 담고**, PRD §65 의 해석 규칙(`revenue_up_profit_down`)이 **원리적으로 발동할 수 없게 된다. 가드레일이 죽는다.**

`[Source: .agent-team/03-service-planning/economic-rule-v1.md#3.2]`

## 4.2 ★ EC-2 — 가르는 기준은 출처가 아니라 근거다

```
has_cost_basis(order)  :=  주문의 모든 품목에 unit_cost 값이 존재한다

cogs(order)  =  Σ (unit_cost × quantity)        if  has_cost_basis(order)
             =  계산 불가 · NO_COST_BASIS       otherwise
```

**출처를 묻지 않는다.**

| | 출처 기준 (`source == COMMERCE`) | **근거 기준 (`has_cost_basis`)** |
|---|---|---|
| 커머스가 `unit_cost` 를 넣으면 | **여전히 계산 거부** — 코드를 고쳐야 한다 | **자동으로 계산됨** |
| 시뮬레이터가 원가 없는 상품을 만들면 | **잘못 계산됨** (출처가 시뮬레이터라서) | **계산 거부 — 올바르다** |
| 측정 계층이 아는 것 | 커머스의 구현 상태 | **자기 계약뿐** |

`[Source: .agent-team/03-service-planning/economic-rule-v1.md#3.3]` · `[Source: .agent-team/04-architecture/adr/ADR-0007-blind-calculation.md]`

**결과는 같다** — 오늘 커머스에는 원가가 없으므로 `NO_COST_BASIS` 가 나온다. **그러나 이유가 다르고 그 차이가 미래를 가른다.**

## 4.3 확정 값 — config 에 넣을 것

### `product_margin` (5종) — `economics.py` 는 **읽지 않는다**

| key | 표시명 | `cost_rate` | `margin_rate` | `median_price_krw` | `frequency_weight` | `pool_size` |
|---|---|---|---|---|---|---|
| `fresh_food` | 신선식품 | 0.78 | 0.22 | 8900 | 0.32 | 70 |
| `meal_solution` | 간편식 | 0.70 | 0.30 | 6500 | 0.24 | 55 |
| `dairy` | 유제품 | 0.75 | 0.25 | 4200 | 0.18 | 35 |
| `beverage` | 음료 | 0.68 | 0.32 | 3500 | 0.14 | 40 |
| `household` | 생활용품 | 0.72 | 0.28 | 12000 | 0.12 | 40 |

**가중평균 기여마진율 26.0% · 총 240개.** 가격 분포는 카테고리별 `LogNormal(ln median, σ = 0.35)`.
`[Source: .agent-team/03-service-planning/economic-rule-v1.md#2]`

> **업계 대조:** 26.0% 는 조사된 건강한 이커머스 범위(CAC 차감 후 최소 20%, 지속가능 브랜드 20~25%+)의 **상단**에 있다. 범위를 벗어나지 않으므로 **값을 조정할 근거가 없다.**

### `treatment_cost` (T0~T4)

| ID | Treatment | 조건 | 단위 비용 | **발생 시점** | MVP |
|---|---|---|---|---|---|
| `T0` | No Treatment (Control) | — | **0원** | — | 사용 |
| `T1` | Free Shipping | 40,000원 미만 주문 배송비 면제 | **3,000원** | **주문 발생 시** | 확장 |
| `T2` | Fixed Coupon | 30,000원 이상 → 3,000원 할인 | **3,000원** | **쿠폰 사용 시** | 확장 |
| `T3` | Strong Win-back Coupon | 50,000원 이상 → 7,000원 할인, 유효 14일 | **7,000원** | **쿠폰 사용 시** | **사용** |
| `T4` | Repurchase Reminder | 평균 구매주기 기반 푸시 | **30원** | **발송 시** | 확장 |

`[Source: .agent-team/03-service-planning/economic-rule-v1.md#4.1]`

### `cost_accounting`

```
message_cost        =      30원 / 발송     ← 처치군 전원. 반응 여부 무관
campaign_fixed_cost = 100,000원 / 캠페인   ← 운영 고정비
discount_cost       =   7,000원 / 쿠폰 사용 ← 실제 사용된 주문에만
N_targeted          = push_sent 발생 고객 수
```

### `shipping`

```
shipping_fee_krw            = 3000
free_shipping_threshold_krw = 40000
```

### `ai_investment`

| 항목 | 금액 | 산정 근거 |
|---|---|---|
| Model Development Cost | **12,000,000원** | ML/DL 개발 2인 × 1.5개월 (인건비 400만원/월) |
| Compute Cost | **600,000원** | 학습·시뮬레이션 CPU 인스턴스 1.5개월 |
| Model Operating Cost | **300,000원 / 월** | 배치 스코어링 + 대시보드 호스팅 |
| Monitoring Cost | **200,000원 / 월** | Drift 감시 + 알림 운영 |
| 상각 기간 | **12개월** | 개발·초기 Compute 를 12개월 균등 상각 |
| **캠페인 1회(42일) 귀속 AI Cost** | **≈ 2,020,000원** | `(12,600,000 / 12 + 500,000) × (42/30)` |

`[Source: .agent-team/03-service-planning/economic-rule-v1.md#5]`

> ⚠ **값 자체가 가정 기반 추정치다.** 인건비 400만원/월·상각 12개월에 **외부 출처가 없다.** `[Source: .agent-team/03-service-planning/economic-rule-v1.md#5]`
> **가정임을 config 주석에 남기는 것까지가 C1 이다** (AC-1).

### `assumptions`

```yaml
assumptions:
  refund_adjusted: false      # A-REFUND — 총매출을 순매출로 간주한다
```

## 4.4 ★ 가정 `A-REFUND` — 반드시 config 와 산출물에 남는다

> *"이 규칙 하에서 `revenue = Σ order_amount` 이며 환불·취소를 차감하지 않는다. 즉 **총매출을 순매출로 간주한다.** 환불이 발생하는 환경에서는 `contribution_profit` 이 **과대평가**된다."*
> `[Source: .agent-team/03-service-planning/economic-rule-v1.md#6.4]`

**왜 환불 이벤트를 추가하지 않는가** — 추가할 수 없다:

| 장벽 | 근거 |
|---|---|
| **컬럼을 늘릴 수 없다** | `DATA-003` 이 **정확히 22개**를 규정하고 `tests/test_schema.py:61-72` 가 `assertEqual` 로 고정한다. 컬럼 추가 = SRS 변경 = `Plan/` 수정 = **권한 밖** |
| **음수 금액으로 우회할 수 없다** | `validate_event()` 가 음수 금액 4종을 거부한다 |
| **`event_type` 만 추가하는 것도 스키마 변경** | `tests/test_schema.py:45-47` 이 정확히 16종을 고정 |

**→ `refund_adjusted: false` 플래그를 config 에 두고, 게시물 `notices` 로 나른다.** 가정은 시간이 지나면 사실로 읽히므로 **문서가 아니라 산출물에 붙인다** `[Source: .agent-team/04-architecture/design-patterns.md#P-12]`.

## 4.5 ★ EC-9 — 구조로 막는다. 규율로 막지 않는다

`config_loader.load_economic_config()` 가 **용도별로 분리된 객체**를 돌려준다.

```python
@dataclass(frozen=True, slots=True)
class CostAccountingConfig:          # ← economics.py 가 받는 것
    treatment_cost: Mapping[str, int]
    message_cost_krw: int
    campaign_fixed_cost_krw: int
    shipping_fee_krw: int
    free_shipping_threshold_krw: int
    ai_investment: AiInvestmentConfig
    assumptions: Mapping[str, object]      # refund_adjusted: False 등

@dataclass(frozen=True, slots=True)
class ProductGenerationConfig:       # ← 시뮬레이터(이후 사이클)가 받는 것
    categories: Mapping[str, CategorySpec]   # cost_rate 는 여기에만 있다
```

> **`economics.py` 의 함수 시그니처에 `ProductGenerationConfig` 가 등장하지 않는다. 원가율을 손에 넣을 방법이 타입 수준에서 없다.**
> `[Source: .agent-team/04-architecture/code-structure.md#3 N-2]` · `[Source: .agent-team/04-architecture/design-patterns.md#P-5]`

**`product_margin` 이 config 에 있는 이유는 `ECONOMIC RULE v1` Lock 대상이라서**이지 measurement 가 쓰기 위해서가 아니다. 소비자는 이후 사이클의 시뮬레이터다.

## 4.6 ★ N-3 — 출처별 결과는 **분기가 아니라 입력 분할**

```python
# ❌ 금지 — 이 한 줄에서 창구가 커머스의 구현 상태를 알게 된다
if event_source(record) is EventSource.COMMERCE:
    return unavailable("NO_COST_BASIS")

# ✅ publish.py (M-06) 가 출처를 아는 유일한 자리다
by_source = partition_by_source(events)
{
  "commerce":  economics.contribution_profit(by_source.commerce,  config=cfg),
  "simulator": economics.contribution_profit(by_source.simulator, config=cfg),
}
```

**`economics.py` 는 자기가 어느 출처의 데이터를 받았는지 모른다.** 같은 함수, 같은 식, 다른 입력.
`[Source: .agent-team/04-architecture/adr/ADR-0007-blind-calculation.md]` · `[Source: .agent-team/04-architecture/code-structure.md#3 N-3]`

## 4.7 ★ 반환 타입이 `MetricValue` 다 — `float` 를 돌려주는 함수를 두지 않는다

```python
# ❌ 예외로 만들면 호출자가 try/except 로 감싸고, 그러다 except: return 0 이 생긴다
def cogs(order) -> int:
    if not has_cost_basis(order):
        raise NoCostBasisError(...)

# ✅ 값으로 만들면 계산 불가가 그대로 게시물까지 간다
def cogs(order) -> MetricValue:
    if not has_cost_basis(order):
        return MetricValue.unavailable(
            ReasonCode.NO_COST_BASIS,
            "주문 품목에 unit_cost 값이 없다.")
    return MetricValue.ok(sum(i["unit_cost"] * i["quantity"] for i in order["items"]), unit="krw", basis=...)
```

`[Source: .agent-team/04-architecture/exceptions.md#1.1]` · `[Source: .agent-team/04-architecture/adr/ADR-0003-metric-value-shape.md]`

> **판정 기준:** *"이것이 화면에 표시되어야 하는가?"* → 표시되어야 하면 **값**이다. 실행을 계속할 수 없으면 **예외**다.

### `MetricValue` 를 여기서 정의한다

M-02 가 `MetricStatus`·`ReasonCode` **Enum 2개만** 놓았다. **`MetricValue`·`Basis` dataclass 는 이 스토리가 만든다** — 처음 실제로 쓰는 곳이 여기다.

**계약이 강제하는 불변식을 dataclass 가 그대로 담아야 한다** `[Source: .agent-team/04-architecture/schemas/common.schema.json#$defs.metric_value]`:

| 규칙 | 강제 |
|---|---|
| `status` 가 `ok`·`unconfirmed` → **`basis` 필수** | 생성자에서 검사 |
| ★ `status` 가 `ok`·`unconfirmed` → **`unit` 필수** | 생성자에서 검사. 계약 `allOf[0]`·`allOf[1]` 이 이미 `required` 로 걸고 있다 (실측) |
| `status` 가 `unavailable`·`blocked`·`not_run` → **`value` 는 `None`** · **`basis` 금지** | 생성자에서 검사 |
| 계산 불가 → `reason_code` + `reason_detail` **필수** | 동일 |
| `unconfirmed` → `params_used` 필수 · `reason_code == PARAM_UNCONFIRMED` | 동일 |
| `unit == "ratio"` + 계산됨 → `basis.denominator` 필수 | 동일 |
| **`basis.denominator == 0` → `status` 가 `ok` 일 수 없다** | 동일 |
| `derived: true` → `derivation` 필수 | 동일 |
| ★ **`status` 가 `ok`·`unconfirmed` → `value_formatted` 필수 / 계산 불가 3종 → 금지** | **여기가 아니다 — 아래 참조** |
| ★ `limit_note` | **선택 필드.** 호출자가 넘긴다 |

**`__post_init__` 에서 위반이면 예외를 던진다.** 잘못된 `MetricValue` 를 만들 수 있으면 게시 시점까지 살아남는다.

> ### ★ `unit` 은 표시용 장식이 아니라 **필수 입력**이다 (Thomas regate 2)
>
> `value_formatted` 를 **`contracts.py` 가 `(status, unit, value)` 로** 만든다 (§4.16.1). 세 값이 있으면 결정되는 **순수 함수**다.
> **`unit` 이 없으면 그 함수가 성립하지 않는다.**
>
> ```
> unit 없는 MetricValue 생성  →  직렬화가 value_formatted 를 못 만든다
>                             →  게시물이 자기 계약(ok → value_formatted required)을 어긴다
>                             →  게시 시점 자기검증(§4.11)에서 터진다 — 원인에서 멀리 떨어진 자리다
> ```
>
> **`__post_init__` 이 첫 자리에서 사슬을 끊는다.** 계산한 사람이 `unit` 을 아는 유일한 사람이고, 그 순간에 잡는 것이 가장 싸다.

### ★★ `value_formatted` 는 **dataclass 필드가 아니다** (Thomas C-1 · 리드 판정 2026-09-11)

계약에 `value_formatted` 가 추가된다 — `ok`·`unconfirmed` 필수 / 계산 불가 3종 금지. **`basis` 와 정확히 같은 패턴이다** (`[Source: .agent-team/03-story-engineering/story-m-06-publish-kr.md#4.16]`).

**그런데 이 필드를 `MetricValue` 가 들고 다니지 않는다. `contracts.py` 가 직렬화 시점에 `unit` + `value` 로 만든다** (리드 판정 ⑵ · `[Source: .agent-team/03-story-engineering/story-m-06-publish-kr.md#4.16.1]`).

| | 이유 |
|---|---|
| ⇥₁ `MetricValue.ok()` 호출자가 포맷해 넘긴다 | ❌ 호출 지점마다 달라지고 **한 곳만 빠뜨리면 화면이 `undefined` 를 받는다.** 그 자리에 `?? 0` 이 생긴다 |
| **⇥₂ 직렬화 시점에 한 곳에서** | ★ **채택.** 빠뜨릴 자리가 없다. **`economics.py`·`kpi.py` 는 표시 규칙을 모른다** — 창구 중립성과 같은 방향 |

> **★ 그래서 이 스토리가 하지 않는 것이 무엇인지 분명히 한다.**
> `economics.py` 는 `value_formatted` 를 **만들지도, 알지도 않는다.** `unit` 을 정확히 넣는 것이 이 스토리의 몫이고, 포맷은 `unit` 에서 나온다.
> **`unit` 을 빠뜨리면 `value_formatted` 를 만들 수 없다** — `unit` 은 표시용 장식이 아니라 **필수 입력**이다.

**`limit_note` 는 반대다 — dataclass 필드로 둔다.**

```python
limit_note: str | None = None   # 선택. "쿠폰 사용 이벤트만 센다" 같은 정밀도 한계 한 줄
```

`unit` 에서 유도할 수 없는, **지표별 사실**이기 때문이다. 화면의 `한계` 칩이 이 값을 읽는다 (`[Source: .agent-team/03-story-engineering/story-m-06-publish-kr.md#4.17]`).

| 필드 | 누가 만드나 | 왜 |
|---|---|---|
| `value_formatted` | **`contracts.py` 직렬화** | `unit` + `value` 로 기계적으로 나온다 |
| `limit_note` | **호출자 (`kpi.py`·`economics.py`)** | 그 지표를 계산한 사람만 아는 한계다 |

### `Basis` 필드 (계약 `$defs.basis`)

```
population              필수 · minLength 1   모집단. "고객"이라고만 쓰지 않는다 (R-4)
denominator_definition  필수 · minLength 1   분모의 문장. 합계는 "분모 없음 (합계)"
denominator             number | null        합계·건수는 null
observed_count          integer | null       실제로 검사·집계한 레코드 수
window                  필수 { direction, days?, label? }
                        direction ∈ retrospective | prospective | point_in_time | none
excluded_count          제외 대상 수 (R-6 — 제외를 조용히 하지 않는다)
excluded_reason         제외 사유
source_event_types      근거 이벤트 종류
```

## 4.7b ★★ `economics.py` 의 **입력 자료구조** — 이 스토리가 정의한다 (Thomas C-5)

**§4.7 의 `cogs(order)` 예시가 `order["items"][i]["unit_cost"]` 를 순회한다. 그런데 그 `order` 가 무엇인지 어디에도 없었다.**

**실측:**
```
data-model-erd.md §1.1   orders · order_items · products  →  전부 ❌ 미구현
EVENT_FIELDS 22종         unit_cost 없음 · purchase 는 주문 단위 1행
                          product_id·quantity·unit_price 는 purchase 에서 NOT_APPLICABLE
```

**→ C1 에 `order["items"]` 를 채울 원천이 없다.** §4.10 표의 *"시뮬레이터 ✅ `products.parquet`"* 도 **C1 에서는 거짓**이다 — 시뮬레이터가 미가동이다.

### 확정 — `economics.py` 는 **순수 함수**이므로 자기 입력 타입을 스스로 정의한다

```python
@dataclass(frozen=True, slots=True)
class OrderItem:
    product_id: str
    quantity: int
    unit_price: int
    unit_cost: int | None       # ★ None 이면 원가 근거 없음 → NO_COST_BASIS

@dataclass(frozen=True, slots=True)
class OrderView:
    order_id: str
    order_amount: int
    items: tuple[OrderItem, ...]    # ★ C1 에서는 비어 있는 것이 정상이다
    treatment_ids: tuple[str, ...] = ()
    has_coupon_use: bool = False
```

| 규칙 | 내용 |
|---|---|
| **`economics.py` 는 이 타입만 받는다** | 이벤트 dict·manifest·파일을 받지 않는다. **순수 함수 유지** |
| ★ **조립은 `publish.py`(M-06)가 한다** | `events` → `OrderView` 변환이 **출처를 아는 유일한 자리**와 같은 층이다 |
| ★ **`items` 가 비면 `has_cost_basis` 가 False** | **C1 의 정상 경로다.** `purchase` 는 주문 단위 1행이라 품목을 재구성할 수 없다 → `cogs` 가 `NO_COST_BASIS` 를 낸다 |
| **`unit_cost: None` 과 `items: ()` 를 구분한다** | 전자는 *"품목은 아는데 원가를 모른다"*, 후자는 *"품목 자체를 모른다"*. **`reason_detail` 이 둘을 다르게 쓴다** |

> **§4.10 표를 이렇게 읽는다:** *"시뮬레이터 생성분 ✅"* 는 **이후 사이클**의 이야기다.
> **C1 에서는 두 출처 모두 `items` 가 비어 `NO_COST_BASIS` 가 나온다.** 그것이 USP-1 대표 장면의 실제 내용이다.

## 4.8 ★ 의존성 봉쇄 — `economics.py` 는 PyYAML 을 모른다

```
config_loader.py   ← PyYAML 의 유일한 접점 (I/O 다)
economics.py       ← dict / dataclass 를 인자로 받는다. YAML 을 읽지 않는다
```

**→ `tests/test_economics.py` 는 PyYAML 없이 전부 돈다.** A7 사슬의 첫 고리가 여기서 끊긴다.
`[Source: .agent-team/04-architecture/dependency-plan.md#2.1]`

**`config_loader.py` 는 이 스토리가 만든다.** 보안 규약:

```python
# ✅ 이것만 쓴다 — CVE-2026-24009 (yaml.FullLoader 를 통한 RCE) 회피
data = yaml.safe_load(path.read_text(encoding="utf-8"))

# ❌ 금지
yaml.load(text)                            # 구버전에서 unsafe
yaml.load(text, Loader=yaml.FullLoader)    # CVE-2026-24009 경로
yaml.unsafe_load(text)
```

> **YAML 파서를 자체 구현하지 않는다.** *"부분 구현 파서는 조용히 다른 값을 읽는다. 경제 규칙 config 를 잘못 읽으면 기여이익이 조용히 틀린다 — 이 프로젝트가 막으려는 실패 양식 그 자체다."*
> **PyYAML 이 없으면 `ConfigError` 로 멈춘다.** 폴백하지 않는다.
> `[Source: .agent-team/04-architecture/exceptions.md#4]`

**`test_config_loader.py` 는 PyYAML 이 없으면 skip 한다** — 사유를 남긴다:

```python
@unittest.skipUnless(config_loader.yaml_available(),
                     "BLOCKED: PyYAML 미설치 — config 로딩 경로를 검증하지 않았다")
```

## 4.9 ★ EC-7 판정에서 `False` 를 돌려주지 않는다

```python
# ❌ 계산 불가를 "가드레일 통과"로 만든다
def revenue_up_profit_down(s, b) -> bool:
    return s.revenue > b.revenue and s.profit < b.profit    # profit 이 None 이면?

# ✅ 판정도 MetricValue 다
def revenue_up_profit_down(s, b) -> MetricValue:
    if any(v.status is not MetricStatus.OK for v in (s.revenue, b.revenue, s.profit, b.profit)):
        return MetricValue.unavailable(ReasonCode.NO_COST_BASIS, "...", blocked_by=[...])
    ...
```

**C1 에서 이 함수는 거의 항상 계산 불가다** — 비교할 전략이 없다(`NEEDS_TWO_STRATEGIES`).
**그래도 구현한다** — `#47` 완료 조건이 요구하고, *"정의는 결과보다 먼저 있어야 한다"* `[Source: .agent-team/03-service-planning/kpi-definition-v1.md#5.3]`.

## 4.10 스키마 공백 3건 — `contribution_profit` 이 오늘 어디서도 나오지 않는 이유

```
data_spec §6.3 기여이익식
  = revenue − cogs − coupon_cost − shipping_subsidy − message_cost − campaign_fixed_cost/N

     revenue          ← order_amount        ✅ 있다
     cogs             ← unit_cost           ❌ 커머스에 없다     (Ecommerce #24)
     coupon_cost      ← discount            ❌ 스키마에 없다     (D-16)
     shipping_subsidy ← 배송비               ❌ 스키마에 없다     (D-3)
     message_cost     ← push_sent 건수      ✅ 있다
     campaign_fixed   ← 캠페인 수 · N        ✅ 있다
```

**여섯 항목 중 셋이 계산 불가다.** `[Source: .agent-team/04-architecture/data-model-erd.md#5.1]`

**셋 다 필드 추가가 `Plan/` 수정을 요구하므로 권한 밖이다.** 처리 방침:

| 공백 | 시뮬레이터 생성분 | 커머스 실측분 | 결정 |
|---|---|---|---|
| `unit_cost` | ✅ `products.parquet` 에서 | ❌ `NO_COST_BASIS` | `EC-1`·`EC-2` |
| **`discount`** | ✅ **규칙 유도** — `coupon_use` + `treatment_cost[T3]` · `derived: true` | ❌ `MISSING_FIELD` | **D-16** |
| `shipping_fee` | ✅ 규칙 유도 — `order_amount < 40,000` ∧ `treatment_id = T1` → 3,000원 · `derived: true` | ❌ `MISSING_FIELD` | **D-3** |

### D-16 의 유도 규칙 — `ECONOMIC RULE v1` 에 **조항으로 넣는다**

```
discount(order) := Σ  treatment_cost[t]  for t in {order 에 적용된 처치 중 쿠폰 계열}
                   단 그 주문에 coupon_use 이벤트가 있을 때만 (EC-3 발생주의 2원칙)
                   최소주문금액 미달로 미사용이면 0 이 아니라 발생하지 않는다
```

`[Source: .agent-team/04-architecture/gate1-freeze-procedure.md#3.2]`

> **리드 판정 (D-16):** *"차단되는 것은 필드의 부재가 아니라 **결정의 부재**다. `G-16` 의 충족 조건은 '필드를 추가한다'가 아니라 **'유도 규칙을 `ECONOMIC RULE v1` 에 넣는다'** 이다."*
> **→ 이 스토리가 그 조항을 config 또는 `economics.py` 독트링에 넣는다.**
> **진짜 차단은 유도 규칙을 안 정한 채 Lock 하는 것이다** — 다음 사이클이 임의로 정하면 Lock 이후 변경이라 `FREEZE-003` 전량 재실행.

**`derived: true` 는 반드시 `derivation` 문자열을 동반한다** (계약 강제). 저장된 사실이 아님이 화면에서 구분되어야 한다.

## 4.11 함정

| # | 함정 | 왜 빠지나 | 대신 |
|---|---|---|---|
| **T-1** | `cogs = order_amount * cfg.cost_rate` | 원가율이 config 에 있으니까. **숫자가 나오고 화면이 채워진다** | §4.1 — `EC-1` 위반. **가드레일이 죽는다** |
| **T-2** | `if source == COMMERCE: return unavailable(...)` | 오늘 요구를 가장 짧게 충족한다 | §4.2 — `EC-2` 위반 |
| **T-3** | `economics.py` 에서 `yaml.safe_load()` 호출 | config 를 읽어야 하니까 | §4.8 — `config_loader.py` 만 PyYAML 을 본다 |
| **T-4** | `CostAccountingConfig` 에 `categories` 를 넣는다 | 한 객체가 편하다 | §4.5 — **타입으로 막는 것이 설계다** |
| **T-5** | `def cogs(...) -> float` | 자연스럽다 | §4.7 — **`0.0` 을 돌려줄 방법이 타입에 없어야 한다** |
| **T-6** | `N_targeted` 를 처치군 배정 인원으로 센다 | 배정 정보가 이벤트에 있다 | §AC-5 — **발송된 고객 수**다. 발송 실패·제외 고객은 고정비를 나눠 갖지 않는다 |
| **T-7** | `campaign_fixed_cost / N_targeted` 를 `N=0` 에서 그냥 계산 | 0 건일 일이 없어 보인다 | **오늘이 정확히 0 건이다.** 나누지 않고 캠페인 단위로 남긴다 |
| **T-8** | 기대 비용 2,130원을 실현 비용에 쓴다 | `data_spec` §6.2 에 적혀 있다 | `EC-5` — **계획값이다.** 이름을 나눈다 |
| **T-9** | `revenue_up_profit_down` 이 `bool` 을 돌려준다 | 판정이니까 | §4.9 — 계산 불가를 통과로 만든다 |
| **T-10** | 하드코딩 금액을 "테스트 픽스처니까" 남긴다 | 테스트는 config 를 안 읽어도 되니까 | AC-8 은 **제품 코드** 기준이다. 테스트 픽스처는 허용하되 **`economics.py` 에는 0건** |

---

# 5. 작업 분해 (Tasks)

## T1 · `errors.py` (선행)

- [ ] `src/measurement/errors.py` 신설 — 표준 라이브러리만, **아무것도 import 하지 않는 잎 노드**
- [ ] 계층: `MeasurementError` → `ContractError`(`SchemaError`·`PartitionKeyError`·`ContractViolation`) · `GateError`(`QualityGateFailure`·`FreezeViolation`) · `ConfigError` · `PublishError` · `DependencyMissing`
- [ ] 메시지 규약 — **`① 무엇이 · ② 왜 · ③ 무엇을 하면 되는가`** 셋을 담는다 (`NFR-006`)
- [ ] `sink.py:277-279` 의 `ValueError` → `PartitionKeyError` 승격 (M-01 이 넘긴 항목)

`[Source: .agent-team/04-architecture/exceptions.md#2, #6, #10]`

## T2 · `MetricValue`·`Basis` (§4.7)

- [ ] dataclass 정의 + `__post_init__` 불변식 검사 7건
- [ ] 생성 헬퍼 — `MetricValue.ok(...)` · `.unconfirmed(...)` · `.unavailable(...)` · `.blocked(...)` · `.not_run(...)`
- [ ] `BlockerRef` dataclass — `kind`(9종) · `ref` · `reason_code`
- [ ] `schema.py` 에 정의 (M-02 가 놓은 `MetricStatus`·`ReasonCode` 옆) — **소유가 확정됐다. M-04 와 합의하지 않는다**

## T3 · `config/economic_config.yaml` (AC-1)

- [ ] 6블록 작성 (§4.3 값 그대로)
- [ ] 카테고리 키가 `Category` Enum 어휘와 같은지 확인
- [ ] AI 투자비용에 **가정 주석**
- [ ] `assumptions.refund_adjusted: false`
- [ ] **D-16 유도 규칙 조항** 포함 (§4.10)

## T4 · `config_loader.py` (§4.8)

- [ ] `yaml.safe_load()` 만 사용
- [ ] `yaml_available()` guarded 함수
- [ ] **용도별 분리 반환** — `CostAccountingConfig` · `ProductGenerationConfig`
- [ ] 부재·파싱 실패·필수 키 누락 → `ConfigError` (종료 코드 5)

## T5 · `economics.py` (AC-2·4·5·6·7)

- [ ] ★ `OrderItem`·`OrderView` dataclass (§4.7b) — **`economics.py` 가 자기 입력 타입을 정의한다**
- [ ] `has_cost_basis(order: OrderView) -> bool` — `items` 가 비면 **False**
- [ ] `cogs(order) -> MetricValue`
- [ ] `revenue(orders) -> MetricValue`
- [ ] `coupon_cost(...)` · `message_cost(...)` · `campaign_fixed_cost(...)` · `shipping_subsidy(...)` — `derived` 처리 포함
- [ ] `marketing_cost(...)` = `message_cost + coupon_cost + campaign_fixed_cost`
- [ ] `contribution_profit(...) -> MetricValue` + `blocked_by` 사슬
- [ ] `n_targeted(...)` (EC-4, 0 처리)
- [ ] `expected_cost_per_customer` / `realized_cost_per_customer` (EC-5)
- [ ] `revenue_up_profit_down(...) -> MetricValue` (EC-7)
- [ ] `ai_investment_cost(...)` · `ai_roi(...)` — C1 에서는 `NEEDS_TWO_STRATEGIES`

## T6 · `tests/test_neutrality.py` (AC-3) ★

**표준 라이브러리(`ast`·`pathlib`)만 쓴다.** `test_isolation.py` 가 봉인이므로 **별도 파일로 만든다.**

| 테스트 | 검사 | 규칙 |
|---|---|---|
| `test_economics_has_no_source_literal` | `economics.py` 문자열 상수에 `commerce`·`simulator` 없음 | **N-1** (`EC-2`) |
| `test_economics_does_not_read_cost_rate` | `economics.py` 에 `cost_rate`·`margin_rate`·`product_margin` 식별자·문자열 없음 | **N-2** (`EC-9`) |
| `test_pure_layer_has_no_io` | `economics.py` 가 `open`·`Path`·`json`·`csv`·`gzip`·`yaml` 을 import 하지 않음 | **L-2** |
| `test_source_classification_is_single_sourced` | `simulator_version`+`random_seed` 를 함께 참조하는 파일이 `schema.py`·`sink.py` 뿐 | **N-4** |
| `test_yaml_import_is_contained` | `import yaml` 이 `config_loader.py` 한 파일에만 | **A7-6** |
| `test_no_hardcoded_krw_in_economics` | `economics.py` 의 숫자 리터럴에 금액이 없음 (0·1 등 구조적 상수 제외) | **AC-8** |

`[Source: .agent-team/04-architecture/code-structure.md#6.1]`

> **왜 소스 검사인가:** 값 검사로는 *"오늘 우연히 맞다"* 만 보인다. **소스 검사는 다음 사람이 분기를 넣는 순간 실패한다.**
> `test_isolation.py` 가 import 를 AST 로 검사하는 것과 같은 방식이고 같은 이유다 `[Source: .agent-team/04-architecture/design-patterns.md#P-7]`.
>
> **한계를 먼저 적는다** — 상대 import · 동적 import · f-string 경로를 못 잡는다. **한계를 적지 않은 검사는 통과가 보증으로 오해된다.** 테스트 모듈 독트링에 남긴다.
>
> ### ★ 두 검사가 **짝**이라는 사실을 적는다 (Thomas 답변1)
> `test_economics_has_no_source_literal` 은 **문자열 상수만** 본다. 그래서 이런 우회를 **못 잡는다**:
> ```python
> if record.get("simulator_version") is not None:   # ← 'commerce'·'simulator' 문자열이 안 나온다
>     return unavailable(...)                        #    그런데 출처로 분기하고 있다
> ```
> **그 우회를 잡는 것이 `test_source_classification_is_single_sourced`** 다 — `simulator_version`·`random_seed` 를 함께 참조하는 파일을 `schema.py`·`sink.py` 로 제한한다.
> **둘 중 하나만 있으면 구멍이 남는다.** 테스트 모듈 독트링에 **"이 둘은 짝이다"** 를 적는다.

## T7 · `tests/test_economics.py`

- [ ] `has_cost_basis` — 전 품목에 `unit_cost` 있음/일부 없음/전부 없음
- [ ] `cogs` 가 원가 없는 주문에 **`NO_COST_BASIS` 를 돌려준다**
- [ ] ★ **`cogs` 가 `0` 을 돌려주지 않는다** — `value is None` 단언
- [ ] `contribution_profit` 의 `blocked_by` 사슬이 실제 원인을 담는다
- [ ] `message_cost` 가 반응 무관 전원 계상 · `discount_cost` 가 사용분만
- [ ] 최소주문금액 미달 → 메시지 비용만
- [ ] `N_targeted == 0` → 나눗셈 없음
- [ ] `revenue_up_profit_down` 이 입력이 계산 불가일 때 `False` 가 아니라 계산 불가
- [ ] **PyYAML 없이 전부 통과** (AC-9)

## T8 · `tests/test_config_loader.py`

- [ ] PyYAML 없으면 **skip + 사유** (§4.8)
- [ ] `CostAccountingConfig` 에 `cost_rate` 계열 속성이 **없다**는 단언 ← 타입 봉쇄의 회귀 테스트
- [ ] 필수 키 누락 → `ConfigError`, 메시지에 파일 경로·해결 방법 포함

## T9 · 검증 (AC-9)

- [ ] `python3 -m unittest discover -s tests` — 출력 전문 + **skip 수와 사유**
- [ ] `python3 -m unittest tests.test_isolation -v`
- [ ] `python3 .agent-team/04-architecture/tools/check_ownership.py` — **`planned` 에 이미 등록돼 있다.** 추가하지 말고 돌려 확인만 (Thomas N-1)
- [ ] `git -C ../Ecommerce_Service status --porcelain` 빈 출력

---

# 6. 파일 목록 (`file_list`)

## 6.1 이 스토리가 만드는 파일

| 파일 | 동작 |
|---|---|
| `src/measurement/errors.py` | **신설** |
| `src/measurement/economics.py` | **신설** — 순수 함수 |
| `src/measurement/config_loader.py` | **신설** — PyYAML 의 유일한 접점 |
| `config/economic_config.yaml` | **신설** — 6블록 |
| `tests/test_neutrality.py` | **신설** — 소스 검사 6건 |
| `tests/test_economics.py` | **신설** |
| `tests/test_config_loader.py` | **신설** |
| `src/measurement/schema.py` | **조건부 수정** — `MetricValue` 를 여기 둘 경우 |
| `src/measurement/sink.py` | **수정** — `ValueError` → `PartitionKeyError` |
| `.agent-team/04-architecture/tools/ownership.json` | **수정하지 않는다** — `planned` 63건에 **이미 전부 등록돼 있다**(Thomas N-1 확인). `check_ownership.py` 를 **돌려 확인만** 한다 |

## 6.2 절대 만지지 않는 파일

```
tests/test_isolation.py · .github/workflows/isolation.yml          ← 봉인
src/simulator/** src/decision/** src/diagnostics/** src/orchestration/**
Plan/**                                                            ← 서브모듈
AGENTS.md · src/AGENTS.md · src/*/AGENTS.md · src/*/CLAUDE.md · README.md
dashboard/**                                                       ← Andrew
../Ecommerce_Service/**                                            ← 읽기만
```

---

# 7. 테스트

## 7.1 실행 가능한 명령

```bash
python3 -m unittest discover -s tests
python3 -m unittest tests.test_neutrality -v      # ★ 창구 중립성
python3 -m unittest tests.test_economics -v
python3 -m unittest tests.test_isolation -v
python3 .agent-team/04-architecture/tools/check_ownership.py
```

**PyYAML 은 저장소 환경에 없다** (2026-09-11 실측). `test_config_loader` 는 skip 되고 **그 사실을 PR 에 적는다.**

## 7.2 ★ `test_neutrality.py` 를 어떻게 쓰나 — 참고 구현

`tests/test_isolation.py` 의 헬퍼가 그대로 쓸 수 있는 형태다. **복사해 쓰되 봉인 파일을 수정하지 않는다.**

```python
# tests/test_isolation.py 에 있는 것 — 같은 방식으로 새 파일에 쓴다
def _string_constants(tree: ast.AST) -> list[tuple[str, int]]:
    return [(node.value, node.lineno)
            for node in ast.walk(tree)
            if isinstance(node, ast.Constant) and isinstance(node.value, str)]

def _imported_modules(tree: ast.AST) -> list[tuple[str, int]]: ...
```

**식별자까지 잡으려면** `ast.Name`·`ast.Attribute` 도 순회해야 한다 — `cost_rate` 는 속성 접근으로 올 수 있다:

```python
for node in ast.walk(tree):
    if isinstance(node, ast.Attribute) and node.attr in BANNED:
        ...
    if isinstance(node, ast.Name) and node.id in BANNED:
        ...
```

## 7.3 깨뜨리면 안 되는 기존 테스트

| 테스트 | 이유 |
|---|---|
| `test_isolation.py` 6건 전부 | **새 파일도 자동으로 검사 대상**이다 (`SRC_ROOT.rglob("*.py")`) |
| `test_sink.py:198-203 test_empty_sink_marks_every_metric_unavailable` | USP-1 회귀 테스트 |
| `test_schema.py:45-47`·`61-72` | 16종·22컬럼 `assertEqual` |

---

# 8. 연속성

## 8.1 선행 스토리에서 이어받는 것

| 스토리 | 이어받는 것 |
|---|---|
| **M-02 (`#54`)** | `Category` Enum 5종 → **config 의 `product_margin` 키가 같은 어휘** · `MetricStatus` 5종 · `ReasonCode` 9종. **다시 정의하지 않는다** |
| **M-01 (`#53`)** | `sink.py:277-279` 의 `ValueError` 위치 → `PartitionKeyError` 승격 대상 |

**M-02 가 끝나지 않았으면 `Category` 어휘가 미확정이다.** 그 경우 config 의 카테고리 키를 §4.3 표의 영문 코드로 쓰고 **M-02 확정 후 대조한다** — 어긋나면 그때 고친다.

## 8.2 확립된 패턴

| 패턴 | 어디에 |
|---|---|
| **`@dataclass(frozen=True, slots=True)`** | `schema.py FieldSpec` — 새 dataclass 도 같게 |
| **모듈 상수 뒤 `"""독트링"""` — 왜 그런지를 적는다** | `schema.py` 전역 규약 |
| **한글 메시지·독트링** | 전 파일 |
| **선택 의존성 guarded** | `sink.py:52-56 parquet_available()` → `config_loader.yaml_available()` 도 같게 |
| **`from src.measurement import schema as sc`** | `sink.py:41` — 같은 alias 관례 |

## 8.3 M-04 와 병렬이다 — 겹치는 지점

**M-04(`#46` KPI)도 `MetricValue` 를 쓴다.** 둘이 각자 정의하면 갈라진다.

> **먼저 착수하는 쪽이 `MetricValue`·`Basis`·`BlockerRef` 를 만들고, 나중 쪽은 import 한다.**
> **어느 쪽이 먼저인지 PR 본문에 적는다.** 두 스토리가 같은 타입을 두 번 정의하면 리뷰에서 잡는다.

---

# 9. 완료 정의 (DoD) · 미결정 · 차단

## 9.1 DoD

- [ ] AC-1 ~ AC-9 전부 체크
- [ ] **`test_neutrality.py` 6건이 통과하고, 일부러 위반을 넣었을 때 실패하는 것을 확인했다**
- [ ] `economics.py` 에 하드코딩 금액 0건 · 출처 문자열 0건 · 원가율 참조 0건
- [ ] D-16 유도 규칙이 **`ECONOMIC RULE v1` 에 조항으로** 들어갔다
- [ ] `assumptions.refund_adjusted: false` 가 config 에 있다
- [ ] AI 투자비용이 **가정임이 주석에** 있다
- [ ] PR 본문에 `project-context-kr.md` §9 체크리스트
- [ ] `#47` 을 **닫지 않았다**

## 9.2 이 스토리에서 하지 않는 것

| 항목 | 왜 |
|---|---|
| `C_rule` · 예산 상한 `B` | **GATE 2 확정 항목** `[Source: .agent-team/03-service-planning/kpi-definition-v1.md#7.2]` |
| `incremental_*` 계산 | 두 전략이 필요하다 — `NEEDS_TWO_STRATEGIES` |
| 쿠폰 사용률 30% 실측 | 시뮬레이터 필요 |
| 환불 이벤트 추가 | **권한 밖** (§4.4) |
| `shipping_subsidy` 저장 필드 추가 | 동일 — 규칙 유도값으로만 |
| 게시 (`results/`) | **M-06 의 몫** |
| 출처 분할 | **M-06 의 `publish.py` 가 유일한 조립 지점** (§4.6) |

## 9.3 미결정 — 구현자가 정하고 PR 에 적는다

| # | 항목 | 선택지 |
|---|---|---|
| ~~**M03-a**~~ | ~~`MetricValue`·`Basis` 위치~~ | ★ **확정 — 이 스토리가 소유한다.** ⑴ `schema.py`(M-02 가 놓은 Enum 옆). **M-04 는 import 한다.** §8.3 |
| **M03-b** | `blocked_by` 사슬 생성 위치 | ⑴ `economics.py` 가 자기 사슬을 담는다 ⑵ `publish.py` 가 조립한다 — **`ADR-0009` 는 `publish.py` 가 계산한다고 적었다.** 계산층은 자기 직접 원인만 담는 편이 단순하다 |
| **M03-c** | `test_neutrality.py` 의 금액 리터럴 검사 범위 | 어디까지를 "금액"으로 볼지 — 오탐을 줄이되 **오탐은 안전한 방향의 실패**다 |

## 9.4 ★ 차단 — 사용자 결정 2건

**아래가 확정되기 전에는 구현을 시작할 수 있으나 Lock 대상 값이 흔들린다.**

| # | 항목 | 선택지 | W2 추천 |
|---|---|---|---|
| **D-1** | 원가 근거 없는 주문의 COGS 처리 | ⑴ **계산 불가 표시** (`EC-1`·`EC-2`) ⑵ 원가율로 추정하고 추정임을 표시 ⑶ 0 으로 채움 | **⑴.** ⑵는 `MEA-003` *"추정값을 만들어내지 않는다"* 와 정면 충돌하고 `EC-7` 가드레일을 죽인다. ⑶은 charter 절대제약 6 위반 |
| **D-2** | 환불/취소 이벤트를 GATE 1 이전에 추가하는가 | ⑴ **추가하지 않고 가정 `A-REFUND` 로 Lock** ⑵ `Plan/` SRS DATA-003 개정 후 추가 ⑶ Lock 연기 | **⑴.** 실험 판정은 시뮬레이터 생성분만 쓰고 추가는 권한 밖 `Plan/` 개정을 요구한다. **단 지금이 추가 비용이 가장 싼 시점이라는 사실은 명시한다** — 현실성을 중시하면 ⑵도 정당하다 |

`[Source: .agent-team/03-service-planning/economic-rule-v1.md#10]`

> **이 스토리는 ⑴을 전제로 쓰였다.** 사용자가 다르게 판단하면 §4.1·§4.4 를 다시 읽고 AC 를 고친다.
> **D-2 를 ⑵로 정하면 이 스토리의 범위를 벗어난다** — `Plan/` 개정은 이 팀의 권한 밖이고, 스키마 변경이 M-02 로 되돌아간다.

**D-16** (`discount` 처리)은 리드가 **차단이 아니라고 판정**했다 (§4.10). 유도 규칙을 넣으면 진행한다.

## 9.5 하류로 넘기는 것

| 받는 스토리 | 넘기는 것 |
|---|---|
| **M-04 (`#46`)** | `MetricValue`·`Basis`·`BlockerRef` (먼저 만든 쪽이 소유) · `errors.py` |
| **M-06 (게시)** | `CostAccountingConfig` · `contribution_profit` 의 `blocked_by` 사슬 · `assumptions` → `notices` 로 나를 값 |
| **M-07 (`#48`)** | `errors.py` 의 `QualityGateFailure`(종료 2) |
| **M-08 (`#45`)** | 상품 참조 계약 형식 (`product_id, category, selling_price, unit_cost`) · D-16 유도 규칙 문장 |
| **M-09 (`#49`)** | Lock 대상 정본 파일 — `config/economic_config.yaml` · `src/measurement/economics.py` · 선행 조건 **`G-12`**·**`G-16`** 충족 증거 |
| **d-02 (대시보드)** | **USP-1 대표 장면** — `revenue` 는 `ok`, `contribution_profit` 은 `unavailable`+`NO_COST_BASIS` 가 **파이프라인에서** 나온다는 사실 |

<!-- ════════ source_hash inputs (D3 · Matthias 항목5) ════════
     계산법: project-context-kr.md §12  ·  파일 18종
     재현:  아래 목록을 sorted() 하고 각 파일에 f"{path}\n{sha256_hex}\n" 를 이어붙여
            그 바이트열의 SHA-256 앞 16자리를 취한다. 없는 파일은 "MISSING".

     .agent-team/00-plan/charter.md
     .agent-team/00-plan/task-graph.md
     .agent-team/03-service-planning/economic-rule-v1.md
     .agent-team/03-service-planning/kpi-definition-v1.md
     .agent-team/03-service-planning/user-stories.md
     .agent-team/04-architecture/adr/ADR-0003-metric-value-shape.md
     .agent-team/04-architecture/adr/ADR-0007-blind-calculation.md
     .agent-team/04-architecture/adr/ADR-0008-basis-required.md
     .agent-team/04-architecture/build-plan.md
     .agent-team/04-architecture/code-structure.md
     .agent-team/04-architecture/dependency-plan.md
     .agent-team/04-architecture/design-patterns.md
     .agent-team/04-architecture/exceptions.md
     .agent-team/04-architecture/schemas/common.schema.json
     AGENTS.md
     docs/GIT_WORKFLOW.md
     src/AGENTS.md
     src/measurement/schema.py

     → source_hash = 55894406a021293f
     ════════════════════════════════════════════════════ -->
