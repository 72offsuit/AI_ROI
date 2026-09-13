---
story_key: M-08
epic: 범위 M — 측정 계층 (이슈 #42)
issue: "#45"
title: 서비스 UI ↔ 시뮬레이터 공통 기록 계약 (M-3) — Lock 최종 검산
status: done   # W5 Phillip 완료 — AC-1~9. 표현력 공백 4건 전부 결론 있음(차단 0) · 문서↔코드 대조 테스트 negative control 8/8
owner: Phillip (W5-B)
phase: 3
blocked_by: ["M-02 (#54)", "G-8 파생 상태 기록 경로", "G-9 shipping_subsidy", "G-16 discount"]
blocks: ["M-09 (#49)"]
source_hash: 82ffbab104b22402
source_files: 17
---

# M-08 · 기록 계약 문서화 (`#45`) — **Lock 최종 검산**

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
| **대상 이슈** | `#45` — OPEN (2026-09-11 라이브 확인) |
| **담당** | Phillip · W5-B |
| **Phase** | **3** — Phase 1·2 완료 후 |
| **산출** | **`docs/measurement_contract.md`** — ★ 이슈 본문이 **언더스코어**로 지정했다 (리드 판정 B-1) |
| **차단하는 것** | **M-09 (`#49`)** — Lock 의 최종 검산이다 |
| **커밋 type** | `docs` |

> ## ★ 이 스토리는 문서 작성이 아니다 — **검산이다**
> M-3 기록 계약은 스키마에서 파생되는 문서이므로 **형식상 Lock 의 선행이 아니다.**
> 그러나 **계약 문서를 실제로 쓰는 행위가 스키마의 표현력을 검산한다.**
>
> **W1·W2 가 발견한 공백들이 이 검산에서만 드러난다:**
> | 공백 | 계약 문서를 쓸 때 드러나는 방식 |
> |---|---|
> | **파생 상태 기록 경로 부재** (D-7) | *"`at_risk` 상태를 어떻게 기록하는가"* 를 쓰려는 순간 **답이 없음이 드러난다** |
> | **`shipping_subsidy` 필드 부재** (D-3) | *"배송 보조를 어떤 필드로 기록하는가"* 를 쓰려는 순간 |
> | **`discount` 필드 부재** (D-16) | *"할인액을 어떤 필드로 기록하는가"* 를 쓰려는 순간 |
>
> **Lock 이후에 이것을 발견하면 `FREEZE-003` 전량 재실행이다.**
> **→ Phase 3 에서 공백이 드러나면 Phase 4(`#49`)로 진행하지 않는다. 멈추고 보고한다.**
> `[Source: .agent-team/03-service-planning/gate1-lock-scope.md#2.2]`

---

# 2. 스토리

> **`P-커머스`**(`Ecommerce_Service` 구현자)**로서 나는 문서 하나만 보고 어떤 이벤트를 어떤 필드·어떤 값으로 기록할지 알고 싶다.**
> 왜냐하면 지금은 SRS·`data_spec`·`event_schema.md`·코드가 서로 다른 말을 하고, **어느 것이 정본인지 알 수 없기** 때문이다.
> `[Source: .agent-team/03-service-planning/user-stories.md#US-15]`

---

# 3. 인수 조건 (AC)

## AC-1 · 자족성 (`#45` 완료 조건)

- [ ] **`docs/measurement_contract.md` 하나로 커머스 퍼널 전 단계**의 이벤트·필드 매핑을 알 수 있다
- [ ] **서비스 UI 담당자가 이 문서만 보고** 어떤 이벤트를 어떤 필드로 기록할지 알 수 있다
- [ ] 시뮬레이터가 생성한 이벤트와 커머스가 생성한 이벤트를 **구분 없이 같은 파이프라인에 넣을 수 있다**

## AC-2 · 퍼널 매핑

- [ ] `Visit → Product View → Add To Cart → Checkout Start → Purchase → Return Visit → Repurchase` 의 이벤트 매핑
- [ ] 각 단계에 **필수 필드 / 선택 필드 / 해당 없음**이 명시된다

## AC-3 · 값 규약을 **인용한다. 다시 정의하지 않는다** ★

- [ ] **`#54`(M-02)가 확정한 허용값과 식별자 형식을 인용한다**
- [ ] `category` 5종 · `page_type` 8종 · 식별자 정규식 9종
- [ ] **계약 문서가 값을 다시 정의하지 않는다** — 정본은 `schema.py` 이고 문서는 인용한다

## AC-4 · 상품 참조 계약

- [ ] `product_id, category, selling_price, unit_cost` 의 형식
- [ ] `Ecommerce_Service` 카탈로그 스냅샷 포맷

## AC-5 · 버전 규칙

- [ ] `service_version` 표기와 호환성 규칙

## AC-6 · 한계를 적는다 ★

- [ ] **`campaign_response_count` 의 정밀도 한계** — 쿠폰 비종속 캠페인 클릭 이벤트가 없다
- [ ] **캐러셀 자동 전환을 `page_view` 로 기록하지 않는다**는 규칙 (W1 R-9 · 세션 품질 지표 오염 방지)
- [ ] **가정 `A-REFUND`** — 총매출을 순매출로 간주한다
- [ ] **정본 긴장 T-1** — `data_spec` §17.4 가 `results/` 접근 주체에 measurement 를 넣지 않았으나 §9 는 쓰기를 규정한다

## AC-7 · ★ Lock 최종 검산 결과

- [ ] **표현력 공백에 대한 결론**이 있다 — 파생 상태 기록 경로(**리드 판정 ④**) · `shipping_subsidy` · `discount`
- [ ] ★ **파생 상태가 `events` 에 기록되지 않고 게시 시점에 계산된다**는 계약 문장이 있다
- [ ] ★ **Feature 로 쓰지 않는다**는 문장과 그 근거(라벨 동어반복)가 있다
- [ ] **`customers` 테이블 부재**가 모집단 정의에 미치는 영향 (M-04 인계)
- [ ] **공백이 드러나면 `#49` 로 진행하지 않는다**는 판정이 문서에 있다

## AC-8 · 커머스 적용

- [ ] `Ecommerce_Service` 적용 범위를 **별도 저장소 이슈 초안**으로 남긴다 — **발행하지 않는다**
- [ ] `Ecommerce_Service` **파일 변경 0건**

## AC-9 · 회귀 없음

- [ ] `python3 -m unittest discover -s tests` — 기준선 46건 회귀 0
- [ ] `python3 .agent-team/04-architecture/tools/check_ownership.py` — PASS

---

# 4. 개발 컨텍스트 (`developer_context`)

## 4.1 파일명 — **`docs/measurement_contract.md`** (언더스코어)

| 출처 | 표기 |
|---|---|
| `task-graph.md` §4 | `docs/measurement-contract.md` (하이픈) |
| **이슈 `#45` 본문** | **`docs/measurement_contract.md`** (언더스코어) |
| `core-features.md` | 언더스코어 |

**리드 판정 B-1/B-2: 이슈 본문 표기를 채택한다.** *"이슈가 작업 정의의 정본이고, `task-graph` 를 수정했으며 이슈는 건드리지 않았다."*
`[Source: .agent-team/_state/wave-log.md#리드-판정-6건]`

## 4.2 커머스 퍼널 ↔ `event_type` 매핑 — 실측 기반

`schema.py` 의 `EventType` 16종과 `_EVENT_RULES` 를 그대로 옮긴 것이다. **문서가 새 규칙을 만들지 않는다.**

| 퍼널 단계 | `event_type` | 필수 필드 (Core 4 + 아래) | 선택 |
|---|---|---|---|
| Visit | `session_start` | `session_id` · `page_type` | `session_duration` |
| — | `page_view` | `session_id` · `page_type` | `product_id` · `category` · `session_duration` |
| — | `search` | `session_id` · `page_type` | `category` · `session_duration` |
| **Product View** | `product_view` | `session_id` · `page_type` · `product_id` · `category` | `unit_price` · `session_duration` |
| **Return Visit** | `return_visit` | `session_id` · `page_type` | `session_duration` |
| **Add To Cart** | `add_to_cart` | `session_id` · `page_type` · `product_id` · `category` · `quantity` · `unit_price` | `session_duration` |
| — | `remove_from_cart` | 동일 | `session_duration` |
| **Checkout Start** | `checkout_start` | `session_id` · `page_type` · `order_id` · `order_amount` | `coupon_id` · `session_duration` |
| **Purchase** | `purchase` | `session_id` · `page_type` · `order_id` · `order_amount` | `coupon_id` · `campaign_id` · `session_duration` |
| 마케팅 | `campaign_exposed` | `campaign_id` | `session_id` · `coupon_id` · `page_type` |
| 마케팅 | `push_sent` | `campaign_id` | `coupon_id` |
| 마케팅 | `coupon_exposed` | `coupon_id` · `campaign_id` | `session_id` · `page_type` |
| 마케팅 | `coupon_clicked` | `coupon_id` · `campaign_id` · `session_id` | `page_type` · `session_duration` |
| 마케팅 | `coupon_use` | `coupon_id` · `campaign_id` · `session_id` · `order_id` · `order_amount` | `page_type` · `session_duration` |
| 부수 | `review` | `session_id` · `product_id` · `category` | `order_id` · `page_type` · `session_duration` |
| 부수 | `cs_contact` | `customer_id` | `session_id` · `order_id` · `product_id` · `category` · `page_type` |

**Core 4 (항상 필수):** `event_id` · `customer_id` · `timestamp` · `event_type`
**Meta 4 (항상 선택):** `service_version` · `customer_version` · `simulator_version` · `random_seed`
**배정 3 (어디서나 선택):** `treatment_id` · `treatment_group` · `experiment_id`

`[Source: src/measurement/schema.py#_EVENT_RULES, CORE_FIELDS, META_FIELDS, _ASSIGNMENT_OPTIONAL]`

> **W3 이 이 표를 실행으로 검증했다 (2026-09-11)** — `schema.requirement()` 와 `_EVENT_RULES` 를 순회해 16종 전부를 출력하고 위 표와 대조했다. **일치한다.**
> 재현:
> ```bash
> python3 -c "import sys; sys.path.insert(0,'.'); from src.measurement import schema as sc; \
>   [print(e.value, sorted(sc._EVENT_RULES[e][0]), sorted(sc._EVENT_RULES[e][1])) for e in sc.EventType]"
> ```
> **그래도 문서에 옮길 때 다시 확인한다.** 표를 손으로 옮기는 동안 스키마가 바뀔 수 있다 — `#54`(M-02)가 같은 파일을 고친다.

> ★ **`_EVENT_RULES` 에 없는 필드는 자동으로 `NOT_APPLICABLE` 이고, 값이 있으면 거부된다.**
> `push_sent` 에 `product_id` 를 붙이면 위반이다. **부재로 화이트리스트가 동작한다** (`P-8`).

### ⚠ `purchase` 는 주문 단위 1행이다

**`product_id`·`quantity`·`unit_price` 는 `purchase` 에서 `NOT_APPLICABLE`** 이다. 값이 있으면 거부된다.
**→ 한 주문의 품목 내역을 `events` 만으로 재구성할 수 없다.** `order_items` 테이블이 필요하고 그것은 미구현이다.
**이 사실을 계약 문서에 적는다** — 커머스 구현자가 품목을 `purchase` 에 넣으려다 거부당한다.

## 4.3 출처 판별 — 별도 플래그가 없다

```python
# src/measurement/sink.py
def event_source(record) -> EventSource:
    """`simulator_version` · `random_seed` 가 모두 없으면 커머스 실측분이다."""
    if record.get("simulator_version") is None and record.get("random_seed") is None:
        return EventSource.COMMERCE
    return EventSource.SIMULATOR
```

**`MEA-002` 를 별도 플래그 컬럼 없이 스키마에서 파생한다** → 기록자가 출처를 위조할 여지가 적다.

> ⚠ `data_spec` §7.2 는 메타 4종을 `Nullable = N` 으로 적었다(W1 D-1). **코드가 옳다** — null 을 출처 판별에 쓰는 것이 `MEA-002` 다. **`data_spec` 이 낡았다.**
> **이 불일치를 계약 문서에 적는다.** `[Source: .agent-team/04-architecture/data-model-erd.md#2.2]`

**→ 커머스는 `simulator_version`·`random_seed` 를 `null` 로 둔다.** 계약 문서가 이것을 명시해야 한다.

## 4.4 ★ 값 규약 — 인용하되 다시 정의하지 않는다

**M-02(`#54`)가 확정한 것:**

| 항목 | 값 |
|---|---|
| `category` 5종 | `fresh_food` · `meal_solution` · `dairy` · `beverage` · `household` |
| `page_type` 8종 | `home` · `list` · `search` · `detail` · `cart` · `checkout` · `complete` · `history` |
| 식별자 9종 | `customer_id` `^C\d{8}$` · `session_id` `^S-C\d{8}-\d{13}$` · `order_id` `^O\d{8}-\d{6}$` · `product_id` `^P\d{4}$` · `coupon_id` `^CPN-[A-Z0-9]{6}$` · `campaign_id` `^CMP-\d{8}-\d{3}$` · `treatment_id` `^T[0-4]$` · `experiment_id` `^EXP-\d{8}-\d{2}$` · `event_id` UUID4 |
| 세션 만료 | 무활동 **30분** → 새 `session_id` |
| 타임존 | **KST 단일** — M-01 이 확정한 정책을 인용한다 |

> **정본은 `src/measurement/schema.py` 다. 계약 문서는 인용한다.**
> **값을 문서에 다시 적으면 두 벌이 되고 언젠가 갈라진다.** 가능하면 `docs/event_schema.md`(생성 문서)를 링크로 참조하고, 인용이 필요하면 **"정본: `schema.py`" 를 함께 적는다.**

### ★ 커머스의 현재 식별자가 전부 형식 위반이다

| 커머스 실측 | 형식 |
|---|---|
| `test-user-1` (`seed-data.ts:97`) | `^C\d{8}$` 위반 |
| `dummyjson-16` (`seed-data.ts:5`) | `^P\d{4}$` 위반 |
| `randomUUID()` (`orders.ts:115`) | `^O\d{8}-\d{6}$` 위반 |

> **맞추는 쪽은 소스다.** *"측정 계층에 '커머스는 이런 ID 를 쓴다'는 지식이 들어가면 **창구가 한쪽 편을 드는 것**이 된다. 계약은 하나여야 하고, 맞추는 쪽은 소스다."*
> `[Source: gh issue #54#미확정]`
>
> **→ 계약 문서는 "커머스가 기록 시점에 변환한다"를 명시하고, 그 요구를 별도 저장소 이슈 초안으로 남긴다.**
> **측정 계층에 매핑 계층을 만들지 않는다.**

## 4.5 ★★ Lock 최종 검산 — 표현력 공백 4건

### ① 파생 상태 기록 경로 (W1 D-7) — ★ **리드가 판정했다 (2026-09-11). 검산이 아니라 확인이다**

**문제였던 것:** PRD §30.2 · `data_spec` §7.3 이 *"기록은 하되 Feature 금지"* 를 요구하는데, **`DerivedStateType`(`inactive`·`at_risk`·`churn`)이 `EventType` 밖이라 Sink 에 기록할 수단 자체가 없다.**

```python
src/measurement/schema.py
class DerivedStateType(str, Enum):     # ← EventType 과 별도 Enum
    INACTIVE = "inactive"; AT_RISK = "at_risk"; CHURN = "churn"

tests/test_schema.py:49-53   test_derived_states_are_not_raw_events   # 교집합 없음을 강제
```

> ### ★ 리드 판정 — **④ 게시 시점 계산** (선택지 4개 중)
>
> | 선택지 | 판정 |
> |---|---|
> | ① `EventType` 16 → 19 | **불가.** `test_schema.py:45-47` 이 `assertEqual` 로 고정한 16종을 바꾸는 것 = **`EVENT SCHEMA v1` 실질 변경. 우리는 지금 그걸 Lock 하려는 중이다** |
> | ② 별도 테이블 | **C1 범위 밖.** 6테이블 미구현 |
> | ③ 기록 안 하고 한계로 Lock | **정보가 사라진다** |
> | **④ 게시 시점 계산** | ★ **채택** |
>
> **근거:** `at_risk`·`churn` 은 `days_since_last_purchase` 에서 **유도되는 값**이고 그 원천(`timestamp`·`purchase`)은 **이미 스키마에 있다.**
> **계산해서 게시하면 스키마를 바꾸지 않고도 정보가 살아난다.**
>
> **D-16(`discount` 유도 규칙)과 같은 형태다** — *"규칙으로 덮을 수 있는 것을 가정으로 덮으면 **할 수 있는데 안 한 것**이다."*

### 이 문서가 적을 것 — 판정이 아니라 **계약 문장**

| # | 적을 것 |
|---|---|
| ① | **파생 상태는 `events` 에 기록되지 않는다.** 기록자(커머스·시뮬레이터)는 **파생 상태를 보내지 않는다** — 보내면 `validate_event()` 가 거부한다 |
| ② | **측정 계층이 게시 시점에 계산한다.** 계산식과 임계값(가설값 28/42/60)을 적는다 |
| ③ | ★ **산출물에 `derived: true` + `derivation` 이 붙는다** — 저장된 사실과 구분된다 |
| ④ | ★ **Feature 로 쓰지 않는다** — 라벨과 동어반복이 된다 (PRD Risk 7 Churn Label Leakage). **대시보드 표시와 코호트 분석 전용** |
| ⑤ | **`DB-012` 위반이 아니다** — 계산하는 쪽은 `measurement` 이고 **대시보드가 아니다** |

**④가 가장 위험한 자리다.** 파생 상태가 게시물에 나타나는 순간 *"이제 Feature 로 써도 되는 것 아닌가"* 로 읽힐 수 있다.
**`tests/test_schema.py:188-196 test_no_observable_depends_on_derived_state` 가 그대로 통과해야 한다** — 이 문서가 그 사실을 적는다.

**구현 분담:** 지표 정의는 **M-04**, 게시 형식은 **M-06 §4.13**. **이 문서는 계약 문장만** 적는다.

### ② `shipping_subsidy` 필드 부재 (D-3)

기여이익식이 빼는 항목인데 **DATA-003 22컬럼에 배송비 필드가 없다.**

| 대상 | 처리 |
|---|---|
| 시뮬레이터 생성분 | **규칙 유도 가능** — `order_amount < 40,000` ∧ `treatment_id = T1` → 3,000원. **저장된 사실이 아니라 규칙에서 유도한 값** → `derived: true` |
| 커머스 실측분 | **`MISSING_FIELD`** — `shippingKrw = 0` 하드코딩(`purchase.ts:41`)이고 주문에 배송비를 저장하지 않는다 |

### ③ `discount` 필드 부재 (D-16) — **리드가 차단이 아니라고 판정**

> **리드 판정:** *"차단되는 것은 필드의 부재가 아니라 **결정의 부재**다. `G-16` 의 충족 조건은 '필드를 추가한다'가 아니라 **'유도 규칙을 `ECONOMIC RULE v1` 에 넣는다'** 이다."*

**M-03 이 그 조항을 넣었다. 이 문서는 그것을 인용하고, 커머스에게 요구할 것을 적는다:**

```
discount(order) := Σ  treatment_cost[t]  for t in {order 에 적용된 처치 중 쿠폰 계열}
                   단 그 주문에 coupon_use 이벤트가 있을 때만 (EC-3 발생주의 2원칙)
                   최소주문금액 미달로 미사용이면 0 이 아니라 발생하지 않는다
```

> **진짜 차단은 유도 규칙을 안 정한 채 Lock 하는 것이다** — 다음 사이클이 임의로 정하면 Lock 이후 변경이고 `FREEZE-003` 전량 재실행이다.
> `[Source: .agent-team/04-architecture/gate1-freeze-procedure.md#3.2]`

### ④ ★ `customers` 테이블 부재 — **M-04 가 새로 짚은 것**

`P_all(D)` 는 `signup_date ≤ D` 로 정의되는데 **`signup_date` 는 `customers` 컬럼이고 그 테이블이 미구현이다.**
`events` 22컬럼에 `signup_date` 가 없다.

**영향:** `repurchase_rate`(모집단 `P_all`) · `cohort_retention_rate[m]`(**가입월 코호트**) · `P_eligible` 를 쓰는 모든 지표.

> **`kpi-definition-v1.md` §8 은 `cohort_retention_rate` 를 `✅`(계산 가능)로 표시했으나 가입월을 알 방법이 `events` 에 없다.**
> **→ 이 검산이 그것을 드러낸다. 계약 문서에 적고 `#49` 로 넘긴다.**

## 4.6 함정

| # | 함정 | 왜 빠지나 | 대신 |
|---|---|---|---|
| **T-1** | 값 규약을 문서에 다시 적는다 | 자족적 문서를 만들려니까 | §4.4 — **정본은 코드다.** 인용하고 정본 위치를 밝힌다 |
| **T-2** | 공백을 "이후 사이클에서" 로 넘기고 `#49` 로 진행 | 문서가 완성돼 보인다 | ★ **§1 — 공백이 드러나면 멈추고 보고한다** |
| **T-3** | 파생 상태 기록 경로를 임의로 정한다 | 결론을 내야 하니까 | §4.5① — **선택지와 비용을 적고 리드 판정을 받는다** |
| **T-4** | 커머스 식별자에 맞춰 형식을 느슨하게 한다 | 커머스가 전부 위반이라 | §4.4 — **창구 중립성.** 맞추는 쪽은 소스다 |
| **T-5** | `Ecommerce_Service` 를 고친다 | 계약을 지키게 하려고 | **별도 저장소 · 편집 금지.** 이슈 초안만 |
| **T-6** | 별도 저장소 이슈를 발행한다 | 초안까지 썼으니까 | **L3 권한.** 사용자 명시 지시 후 |
| **T-7** | `data_spec` §7.2 Nullable 표기를 따른다 | 정본이니까 | §4.3 — **코드가 옳고 `data_spec` 이 낡았다.** 불일치를 적는다 |
| **T-8** | 품목 내역을 `purchase` 에 넣으라고 적는다 | 자연스러워 보인다 | §4.2 — **`NOT_APPLICABLE` 이라 거부된다** |

---

# 5. 작업 분해 (Tasks)

## T1 · 퍼널 매핑 (AC-2)

- [ ] §4.2 표를 문서로 옮긴다 — **`schema.py` 에서 확인하며 쓴다.** 기억으로 쓰지 않는다
- [ ] `purchase` 가 주문 단위 1행임을 명시 (§4.2 ⚠)
- [ ] `NOT_APPLICABLE` 화이트리스트 동작 설명

## T2 · 값 규약 인용 (AC-3)

- [ ] §4.4 표를 **정본 위치와 함께** 적는다
- [ ] 커머스 식별자 위반 3건과 **"맞추는 쪽은 소스"** 원칙
- [ ] M-01 이 확정한 **타임존 정책**을 인용

## T3 · 출처 판별 (AC-1)

- [ ] §4.3 — 커머스는 `simulator_version`·`random_seed` 를 `null` 로 둔다
- [ ] `data_spec` §7.2 Nullable 불일치 기록

## T4 · 상품 참조 계약 (AC-4)

- [ ] `product_id, category, selling_price, unit_cost` 형식
- [ ] 카탈로그 스냅샷 포맷 — **`unit_cost` 가 필수임을 명시.** 없으면 `NO_COST_BASIS`

## T5 · 버전 규칙 (AC-5)

- [ ] `service_version` 표기 · 호환성 규칙
- [ ] `SCHEMA_VERSION` = `event-schema-v1.0-draft` → GATE 1 에서 `event-schema-v1.0` 으로 Lock

## T6 · ★ Lock 최종 검산 (AC-7)

- [ ] §4.5 ① ~ ④ 각각에 **결론 또는 "리드 판정 필요"** 를 적는다
- [ ] **결론이 나지 않는 공백이 있으면 `#49` 로 진행하지 않는다**는 판정을 문서 머리에 적는다
- [ ] `docs/gate1_checklist.md`(M-09)로 넘길 항목 목록

## T7 · 한계 (AC-6)

- [ ] `campaign_response_count` 정밀도 한계
- [ ] **캐러셀 자동 전환을 `page_view` 로 기록하지 않는다**
- [ ] 가정 `A-REFUND`
- [ ] 정본 긴장 T-1 (`data_spec` §17.4 vs §9)

## T8 · 커머스 이슈 초안 (AC-8)

- [ ] 별도 저장소 이슈 **초안**을 `.agent-team/` 아래에 남긴다 — **발행하지 않는다**
- [ ] 내용: 식별자 형식 · `unit_cost` · `category` 어휘 · 타임존 · 이벤트 기록 구현
- [ ] `git -C ../Ecommerce_Service status --porcelain` 빈 출력 확인

## T9 · 검증 (AC-9)

- [ ] `python3 -m unittest discover -s tests`
- [ ] `python3 scripts/gen_event_schema_doc.py | diff - docs/event_schema.md` — 문서와 코드 일치 확인
- [ ] `python3 .agent-team/04-architecture/tools/check_ownership.py`

---

# 6. 파일 목록 (`file_list`)

## 6.1 이 스토리가 만드는 파일

| 파일 | 동작 |
|---|---|
| `docs/measurement_contract.md` | **신설** — 언더스코어 |
| `.agent-team/03-story-engineering/` 아래 커머스 이슈 초안 | **신설 — 발행하지 않는다** |
| `.agent-team/04-architecture/tools/ownership.json` | **수정하지 않는다** — 이미 등록돼 있다(Thomas N-1). 돌려 **확인만** |

## 6.2 절대 만지지 않는 파일

```
tests/test_isolation.py · .github/workflows/isolation.yml          ← 봉인
docs/event_schema.md                                               ← 생성 문서. 손으로 고치지 않는다
src/simulator/** src/decision/** src/diagnostics/** src/orchestration/**
Plan/** · AGENTS.md · src/AGENTS.md · README.md
dashboard/**                                                       ← Andrew
../Ecommerce_Service/**                                            ← ★ 읽기만. 변경 0건
```

---

# 7. 테스트

## 7.1 실행 가능한 명령

```bash
python3 -m unittest discover -s tests
python3 scripts/gen_event_schema_doc.py | diff - docs/event_schema.md    # 차이 없음
python3 .agent-team/04-architecture/tools/check_ownership.py
git -C ../Ecommerce_Service status --porcelain                          # 빈 출력
```

## 7.2 문서를 어떻게 검증하나

**문서는 테스트로 검증하기 어렵다.** 대신:

| 방법 | 무엇을 확인 |
|---|---|
| `gen_event_schema_doc.py` diff | `docs/event_schema.md` ↔ `schema.py` 일치 (W1 이 IDENTICAL 확인) |
| **문서에 적힌 값을 `schema.py` 에서 직접 확인** | 퍼널 표 · 허용값 · 식별자 정규식 |
| **자족성 시험** | *"서비스 UI 담당자가 이 문서만 보고 기록할 수 있는가"* — **다른 문서를 열어야 하면 실패다** |

> **선택 — 계약 문서의 표를 `schema.py` 에서 대조하는 테스트를 둘 수 있다.**
> `gen_event_schema_doc.py` 를 확장해 퍼널 매핑까지 생성하면 **문서와 코드가 구조적으로 어긋날 수 없다** (`P-13`).
> **비용이 있으므로 구현자가 판단한다** (§9.3 M08-b).

---

# 8. 연속성

## 8.1 선행 스토리에서 이어받는 것

| 스토리 | 이어받는 것 |
|---|---|
| **M-02 (`#54`)** | ★ **확정된 허용값·식별자 형식** — 이 문서가 **인용**한다 · 커머스 매핑 요구사항 |
| **M-01 (`#53`)** | ★ **타임존 정책** — 커머스에게 요구할 표기 |
| **M-03 (`#47`)** | 상품 참조 계약의 `unit_cost` 필수성 · **D-16 유도 규칙 문장** · 가정 `A-REFUND` |
| **M-04 (`#46`)** | ★ **`customers` 부재 발견**(§4.5④) · `campaign_response_count` 정밀도 한계 · **파생 상태 기록 경로 결정 요구** |
| **M-06 (게시)** | 정본 긴장 T-1 문장 |
| **M-07 (`#48`)** | `DQ-09` 가 원리적으로 불가하다는 사실 |

## 8.2 확립된 패턴

| 패턴 | 어디에 |
|---|---|
| **문서는 코드에서 생성된다** | `docs/event_schema.md` ← `gen_event_schema_doc.py`. W1 이 diff 0 확인 |
| 한글 문서 | 전 `docs/` |
| **정본을 밝히고 인용한다** | `AGENTS.md` → `Plan/docs/GIT_WORKFLOW_CORE.md` |

---

# 9. 완료 정의 (DoD) · 미결정 · 차단

## 9.1 DoD

- [ ] AC-1 ~ AC-9 전부 체크
- [ ] **자족성 시험을 실제로 했다** — 다른 문서를 열지 않고 기록 가능한지
- [ ] §4.5 의 공백 4건 각각에 **결론 또는 "리드 판정 필요"** 가 적혔다
- [ ] **결론이 나지 않은 공백이 있으면 `#49` 로 진행하지 않는다는 판정**이 문서에 있다
- [ ] `Ecommerce_Service` **변경 0건** — `git status` 로 증명
- [ ] 이슈를 **발행하지 않았다** (초안만)
- [ ] `#45` 를 **닫지 않았다**

## 9.2 이 스토리에서 하지 않는 것

| 항목 | 왜 |
|---|---|
| `Ecommerce_Service` 구현 | **별도 저장소.** 이 저장소에서 하지 않는다 |
| 이슈 발행 | **L3 권한** |
| 매핑 계층 구현 | *"맞추는 쪽은 소스"* |
| 스키마 변경 | 파생 상태 3종 추가는 `EVENT SCHEMA v1` 실질 변경 |
| 6테이블 구현 | C1 범위 밖 |
| 실제 연동 (파일 스냅샷 vs API) | `#45` 미확정 — *"서비스 진행 상황에 따라 결정"* |

## 9.3 미결정 — 구현자가 정하고 PR 에 적는다

| # | 항목 | 선택지 |
|---|---|---|
| **M08-a** | 값 규약을 **인용 vs 전재** | 링크 인용(권장) / 표를 전재하되 정본 위치 명시 |
| **M08-b** | 퍼널 매핑을 **생성 문서로 만드나** | 손으로 씀 / `gen_event_schema_doc.py` 확장 — **후자가 구조적으로 안전하나 비용이 있다** |
| **M08-c** | 커머스 이슈 초안의 분할 | 한 건 / 항목별 여러 건 |

## 9.4 ★ 차단 — 리드 판정이 필요하다

| # | 항목 | 성격 |
|---|---|---|
| ~~**G-8**~~ | ★ **해소 (리드 판정 2026-09-11)** — **④ 게시 시점 계산.** §4.5① · M-04 정의 · M-06 §4.13 게시 |
| **G-9 (`shipping_subsidy`)** | 사용자 결정 **D-3**. ⑴ 규칙 유도 권장 |
| **G-16 (`discount`)** | 사용자 결정 **D-16**. **리드가 차단이 아니라고 판정** — 유도 규칙을 넣으면 진행 |
| **`customers` 부재 (§4.5④)** | **새로 드러난 것.** `#49` Lock 범위 한정 문구에 들어가야 한다 |

> ### ★ 이 스토리의 판정이 `#49` 를 막을 수 있다
> **`gate1-lock-scope.md` §2.3:** *"Phase 3 에서 공백이 드러나면 Phase 4 로 진행하지 않는다. 멈추고 보고한다."*
> **그것이 이 스토리의 존재 이유다.** 문서를 완성하는 것이 목표가 아니라 **공백을 드러내는 것**이 목표다.

## 9.5 하류로 넘기는 것

| 받는 쪽 | 넘기는 것 |
|---|---|
| **M-09 (`#49`)** | ★ **Lock 최종 검산 결과** — 진행 가능 여부 · 선행 조건 `G-8`·`G-9`·`G-16` 충족 상태 · `EVENT_SCHEMA_v1` 의 `scope_note` 에 들어갈 한정 문구(`customers` 부재 · `order_items` 부재 · `DQ-09` 불가) |
| **사용자·리드** | 커머스 이슈 초안 (발행 승인 대기) · G-8 선택지와 비용 |
| **다음 사이클 시뮬레이터** | 무엇을 어떤 스키마로 기록해야 하는지 — **이 문서가 그 답이다** |

<!-- ════════ source_hash inputs (D3 · Matthias 항목5) ════════
     계산법: project-context-kr.md §12  ·  파일 17종
     재현:  아래 목록을 sorted() 하고 각 파일에 f"{path}\n{sha256_hex}\n" 를 이어붙여
            그 바이트열의 SHA-256 앞 16자리를 취한다. 없는 파일은 "MISSING".

     .agent-team/00-plan/charter.md
     .agent-team/00-plan/task-graph.md
     .agent-team/03-service-planning/gate1-lock-scope.md
     .agent-team/03-service-planning/kpi-definition-v1.md
     .agent-team/03-service-planning/user-stories.md
     .agent-team/04-architecture/api-contracts.md
     .agent-team/04-architecture/build-plan.md
     .agent-team/04-architecture/code-structure.md
     .agent-team/04-architecture/data-model-erd.md
     .agent-team/04-architecture/design-patterns.md
     .agent-team/04-architecture/exceptions.md
     .agent-team/04-architecture/gate1-freeze-procedure.md
     AGENTS.md
     docs/GIT_WORKFLOW.md
     docs/event_schema.md
     src/AGENTS.md
     src/measurement/schema.py

     → source_hash = 82ffbab104b22402
     ════════════════════════════════════════════════════ -->
