# `Ecommerce_Service` 읽기 전용 갭 분석 — T1.6

**작성** 2026-09-10 · John (W1 Reverse)
**대상** `/Users/otter/72offsuit/Ecommerce_Service` @ `6b186d0` (main) · Next.js 16.3.4 / React 19.2.8 / TypeScript / SQLite(`node:sqlite`)
**제약 준수** 이 저장소는 **한 파일도 수정하지 않았다.** `git status --porcelain` → 빈 출력 (분석 전·후 모두 확인).

---

## 0. 실행한 검증 (실제 실행함)

| 명령 | 결과 | 비고 |
|---|---|---|
| `npm run lint` | **PASS** (출력 없음) | eslint 9 |
| `npm test` | **PASS — 13 files / 134 tests** (1.50초) | vitest 5. `#24`의 기록과 일치 |
| `git status --porcelain` (실행 후) | **빈 출력** | 파일 변경 0건 증명 |
| `npm run build` | **BLOCKED** | `prebuild`가 `tokens:generate`를 돌려 `src/styles/tokens.generated.css`를 **쓰고**, `next build`가 `.next/`를 만든다 → "파일 생성·수정 금지"에 저촉 |
| `npm run tokens:check` / `tokens:test` | **BLOCKED** | `#24`가 "`tokens:generate` 후 PASS"라고 기록했다. 즉 생성을 전제하는 경로라 실행하지 않았다 |
| `npm run test:e2e` | **BLOCKED** | Chromium 미설치. `npx playwright install`은 파일 생성 |

> `#24`가 기록한 5개 명령 중 **lint·test 2개를 독립 재현했고 결과가 같다.** 나머지 3개는 위 사유로 `BLOCKED`.

---

## 1. (a) PRD/SRS 요구 대비 현재 실측 대조표

정본: SRS `COM-001~005`(`SRS:434-481`) · `DATA-001`(`SRS:690-700`) · `DATA-003`(`SRS:726-750`) · PRD §12.2·§13·§14.

| 요구 | 정본 | 현재 실측 | 근거 (`Ecommerce_Service/` 기준) | 판정 |
|---|---|---|---|---|
| **카테고리 5종** | COM-001 (`fresh_food` `meal_solution` `dairy` `beverage` `household`) | `products` 테이블에 `category` 컬럼 자체가 없다 | `src/lib/server/commerce/schema.ts:9-16` | ❌ |
| **상품 30~50개** | COM-002 / PRD §12.2 | **10개** | `src/lib/server/commerce/seed-data.ts` (`sourceId` 10건) | ❌ |
| **`unit_cost`** | COM-002 | 없음 | `schema.ts:9-16`, `models.ts:1-8` | ❌ **최상위 차단점** |
| **`gross_margin`** | COM-002 | 없음 (파생 계산 근거도 없음) | 위와 동일 | ❌ |
| **`active_status`** | COM-002 | 없음 | 위와 동일 | ❌ |
| **커머스 퍼널** | COM-003 / PRD §14.1 | UI 흐름은 있음(홈→상세→장바구니→결제→완료). **관측 기록 없음** + **Search·Return Visit 구현 없음** | 라우트 5개: `src/app/(store)/{page,cart,checkout,orders/[orderId],products/[productId]}` | ⚠️ |
| **라이프사이클 퍼널** | COM-004 / PRD §14.2 | `users`가 `id`·`name`뿐. `signup_date` 없음. 주문 이력 화면도 없음 | `schema.ts:4-7`, `listOrders`가 프로덕션에서 미사용 | ❌ |
| **T0 No Treatment** | COM-005 | (해당 없음 — 기본 상태) | — | ✅ |
| **T1 Free Shipping** | COM-005 | `const shippingKrw = 0;` **하드코딩** → 무료배송이 처치가 아니라 상수 | `src/lib/server/commerce/purchase.ts:41` | ❌ |
| **T2 Fixed Coupon (30,000↑ → 3,000)** | COM-005 | 쿠폰에 `minimum_order_amount` 없음 | `schema.ts:25-35` | ❌ |
| **T3 Win-back Coupon (50,000↑ → 7,000)** | COM-005 | 최소주문금액·유효기간 둘 다 없음 | `schema.ts:25-35` | ❌ |
| **T4 Repurchase Reminder** | COM-005 | 없음. 푸시·캠페인 개념 자체 없음 | 전 저장소 grep 0건 | ❌ |
| **DATA-001 Customer Master** | `customer_id` `signup_date` `persona` `initial_state` `customer_seed` `treatment_group` + 버전 3종 | `users(id, name)` — **9개 컬럼 중 1개(customer_id 상당)만** | `schema.ts:4-7` | ❌ |
| **DATA-003 Event Log** | 22 컬럼 | **이벤트 기록 자체가 없다** (테이블·코드 0건) | `schema.ts` 전체에 events 없음 | ❌ |
| **Pretendard · 라이트 고정** | `Plan/DESIGN.md` | 적용 | `package.json:22` `pretendard@1.3.9` | ✅ |
| **디자인 토큰 파이프라인** | `Plan/DESIGN.md` | 동작 (스크립트·문서 존재) | `scripts/design-tokens.mjs`, `scripts/tokens/*`, `docs/DESIGN_TOKENS.md` | ✅ |
| **앱 품질** | — | lint PASS · 134 tests PASS (재현) | §0 | ✅ |

### 1.1 최상위 차단점 — 변함없음

**`unit_cost`가 없어 기여이익을 계산할 수 없다.**
`docs/data_spec.html` §6.3의 `Contribution_i = Revenue_i − COGS_i − 쿠폰할인 − 배송보조 − 메시지비 − 캠페인고정비/N` 에서 `COGS_i = Σ(unit_cost × quantity)` 가 산출 불가다.
→ Incremental Profit 불가 → **AI ROI 불가** → 이 프로젝트의 North Star가 성립하지 않는다.

**두 번째 차단점**: `shippingKrw = 0` 하드코딩(`purchase.ts:41`)이 T1을 무효화하고 배송 보조금을 기여이익에서 지운다.

---

## 2. (b) 기존 이슈 `#24`~`#30` 재검증

### 2.1 이슈 목록 (전부 OPEN, 담당자 없음, 작성 2026-09-10)

| # | 제목 | 라벨 |
|---|---|---|
| 24 | docs: PRD/SRS 커머스 요구사항(COM-001~005) 해소 범위 정리 (상위) | documentation |
| 25 | feat: 상품 카탈로그에 카테고리·원가·판매상태 추가와 30~50개 확대 | enhancement |
| 26 | feat: 배송비 정책 도입과 무료배송 기준 적용 | enhancement |
| 27 | feat: 쿠폰에 최소주문금액과 유효기간 조건 추가 | enhancement |
| 28 | feat: 커머스 이벤트 기록 도입 (DATA-003 스키마 준수) | enhancement |
| 29 | feat: 고객 모델에 가입일 추가와 라이프사이클 기준 확보 | enhancement |
| 30 | fix: 외부 CDN 이미지 의존 해소와 불필요 필드 정리 | enhancement |

### 2.2 `#24` 대조표 재검증 — **전 항목 여전히 정확하다**

작성(2026-09-10 13:47) 이후 `Ecommerce_Service` main에 **코드 변경이 없다.** 마지막 소스 커밋은 `39d1668`(2026-09-10 19:14, PR #21)이고 이후는 Plan 서브모듈 포인터 갱신뿐(`6b186d0`). 따라서 표가 낡을 여지가 없었고, 나는 각 행을 코드로 직접 확인했다.

| `#24`의 주장 | 내 확인 | 일치 |
|---|---|---|
| 카테고리 개념 없음 | `schema.ts:9-16`에 `category` 없음 | ✅ |
| 상품 10개 | `seed-data.ts` 10건 | ✅ |
| `unit_cost`·`gross_margin`·`active_status` 없음 | `schema.ts:9-16` | ✅ |
| 퍼널 UI 있으나 관측 기록 없음 | 이벤트 테이블·코드 0건 | ✅ |
| `signup_date` 없음 | `schema.ts:4-7` | ✅ |
| `shippingKrw = 0` 하드코딩 | **`purchase.ts:41` — 줄 번호까지 정확** | ✅ |
| 쿠폰에 조건 필드 없음 | `schema.ts:25-35` | ✅ |
| T4 없음 | grep 0건 | ✅ |
| 이벤트 로깅 없음 | 확인 | ✅ |
| Pretendard·토큰 파이프라인 ✅ | 확인 | ✅ |
| lint / 134 tests PASS | **재현함** | ✅ |
| e2e BLOCKED | 나도 BLOCKED | ✅ |

> **가정 A9 판정 재료: `#24`의 대조표는 정확하고 최신이다.** 다만 §3의 누락 갭 10건과 §4의 제거 축은 덮지 못한다.

### 2.3 커버리지 매트릭스 — 어떤 갭을 어느 이슈가 덮는가

| 갭 | 덮는 이슈 | 완전한가 |
|---|---|---|
| 카테고리 5종 · 상품 30~50 · `unit_cost` · `active_status` | `#25` | ✅ 완전 |
| 배송비 정책 · 무료배송 기준 · T1 | `#26` | ⚠️ 코드 상수만. **UI 고정 문구 미포함** (§4 R-2) |
| 쿠폰 최소주문금액 · 유효기간 · T2/T3 | `#27` | ✅ 완전 |
| 이벤트 기록 (DATA-003) | `#28` | ⚠️ **기록할 기능이 없는 이벤트를 요구**(`search`·`return_visit`) · 식별자 3종·타임존 미포함 (§3 G-1·G-2·G-4·G-7) |
| `signup_date` · 라이프사이클 | `#29` | ⚠️ 구매이력 화면 부재 미포함 (§3 G-5) |
| CDN 이미지 · `source_*` 필드 | `#30` | ⚠️ **`dummyjson-` ID prefix 미포함** (§3 G-1 / §4 R-6) |
| **T4 Repurchase Reminder** | **없음** | ❌ `#24` 표에는 ❌로 있으나 하위 이슈 미생성 (§3 G-8) |
| **주문 경제값 저장 구조** | 없음 | ❌ (§3 G-3) |
| **제거 축 전체** | **없음** | ❌ (§4) |

---

## 3. (c) 기존 이슈가 덮지 못하는 누락 갭

### G-1 · 식별자 형식 3종이 AI_ROI 계약을 위반한다 — **어느 이슈에도 없다**

AI_ROI `src/measurement/schema.py:309-319`가 정한 형식 대비:

| 필드 | AI_ROI 요구 | 커머스 현재 | 근거 |
|---|---|---|---|
| `customer_id` | `^C\d{8}$` | `test-user-1` | `seed-data.ts:97-99` — **`#29`가 다룸** |
| `product_id` | `^P\d{4}$` | `dummyjson-16` | `seed-data.ts:5` 외 10건 — **미커버** |
| `order_id` | `^O\d{8}-\d{6}$` | `randomUUID()` | `orders.ts:115` — **미커버** |
| `coupon_id` | `^CPN-[A-Z0-9]{6}$` | `fixed-3000`, `rate-10` | `seed-data.ts:103-104` — **미커버** |

`#28`의 수용 기준은 `session_id`만 언급하고, `#29`는 `customer_id`만 다룬다.
**실측: AI_ROI `validate_event()`는 이 위반을 잡지 못한다**(`check_identifier()`가 미호출 — `measurement-map.md` W-4). 즉 **양쪽 다 안 막는 구멍이다.**

### G-2 · `orders.created_at`이 UTC다 — 미커버

`orders.ts:116` `new Date().toISOString()` → `2026-09-10T14:04:03.000Z`.
AI_ROI `schema.py:29-33`은 **KST 단일 · ISO 8601 + offset · 밀리초**를 요구하고 `docs/event_schema.md:16`은 "UTC 혼재 불허"라고 적는다.
`#28`은 **이벤트** `timestamp`만 다루고 기존 `orders` 컬럼은 언급하지 않는다.
(AI_ROI 쪽도 UTC를 통과시킨다 — `measurement-map.md` W-3. 하루 밀린 파티션이 만들어진다.)

### G-3 · 주문 경제값이 저장되지 않고 **0으로 재구성된다** — 미커버 · charter 절대제약 6 저촉

`orders` 테이블 컬럼은 `id, user_id, created_at, total_krw` **뿐이다**(`schema.ts:49-54`).
`subtotal`·`discount`·`shipping`은 **쿠폰 스냅샷이 있을 때만** 복원된다(`orders.ts:56-77`):

```ts
// orders.ts:58-66  — 쿠폰이 없는 주문
return { ...record, subtotalKrw: record.totalKrw, discountKrw: 0, shippingKrw: 0, ... }
```

**쿠폰을 쓰지 않은 주문은 배송비를 무조건 0으로 채운다.** 지금은 실제로 0이라 우연히 맞지만,
`#26`이 배송비를 도입하는 순간 **쿠폰 없는 모든 주문의 배송비가 조용히 0으로 보고된다.**
이것이 charter 절대제약 6("결손을 조용히 0으로 채우지 않는다")·PRD §10.1이 금지한 패턴이다.
`#26`은 "배송비 스냅샷을 남긴다"까지만 요구하고 **`orders`에 경제 컬럼이 없다는 구조 문제**를 지적하지 않는다.

### G-4 · 검색 기능이 존재하지 않는다 — 미커버

- PRD §13 User Journey에 `Search` 포함, AI_ROI `page_type`에 `search` 포함(`schema.py:111-112`), `EventType.SEARCH` 존재(`schema.py:47`).
- `#28`은 `search` 이벤트 기록을 **수용 기준에 넣었다.**
- 그러나 커머스에 **검색 라우트·UI·서버 로직이 전혀 없다**(`src/app/(store)/` 5개 라우트에 없음, `catalog.ts:4-10`에 검색 쿼리 없음).
- → **`#28`은 발생시킬 수 없는 이벤트를 기록하라고 요구하고 있다.** Observable 지표 `search_count`(`schema.py:344`)도 영구 계산 불가로 남는다.

### G-5 · 주문 내역(구매 이력) 화면이 없다 — 미커버

- PRD §13 `Purchase History`, AI_ROI `page_type`에 `history`.
- `listOrders()`가 `orders.ts:91-98`에 **구현되어 있으나 프로덕션 코드에서 호출되지 않는다** — grep 결과 참조 전부 `*.test.ts`뿐.
- COM-004 `Repurchase` 단계를 사용자가 밟을 UI 근거가 없다.

### G-6 · 상품 목록 전용 라우트가 없다 — 미커버

`page_type=list`에 대응할 화면이 홈의 `#all-products` 앵커뿐이다(`ProductListing.tsx:7`).
`#25`가 "상품 목록에서 카테고리로 좁혀 볼 수 있다"를 요구하므로 라우트가 필요해진다.

### G-7 · 세션 개념이 없어 `session_start`·`return_visit`을 만들 수 없다 — 부분 커버

- 쿠키는 `SELECTED_USER_COOKIE`(`selection.ts:5`) 하나뿐. 세션 ID·만료·재방문 판정 없음.
- AI_ROI 계약: `session_id = S-{customer_id}-{세션시작 epoch ms}`, 무활동 30분 만료(`schema.py:35-36, 313`).
- `#28`이 `session_id` 형식은 적었으나 **세션 수명주기 구현**은 수용 기준에 없다. `return_visit` 판정 규칙도 없다.

### G-8 · **T4 Repurchase Reminder에 하위 이슈가 없다** — 미커버

`#24` 대조표에 `T4 … 없음 ❌`로 있으나 `#25`~`#30` 어디에도 해당 작업이 없다.
`#27`이 "T4는 #E-4·별도 논의"로 넘기는데 `#28`(=E-4)의 수용 기준 이벤트 목록에는 `push_sent`·`campaign_exposed`가 **빠져 있다.**
→ `campaign_exposed` · `push_sent` 는 커머스가 영원히 만들지 않는 이벤트가 된다. Observable `campaign_response_count`·`coupon_exposure_count` 계산 불가.

### G-9 · 카테고리 어휘 정본이 3자 불일치다 — 부분 커버

| 출처 | 값 |
|---|---|
| SRS COM-001 (`SRS:434-444`) | `fresh_food` `meal_solution` `dairy` `beverage` `household` |
| `AI_ROI/docs/data_spec.html` §6.1 | 신선식품 · 간편식 · 유제품 · 음료 · 생활용품 |
| `AI_ROI/src/measurement/schema.py:115` | "상품 카테고리 5종" — **열거 없음, 검증 없음** |

`#25`가 "영문 저장 + 표시명 매핑"을 제안했지만 **AI_ROI 쪽에 허용값이 없어 계약이 성립하지 않는다.**
AI_ROI 자체 테스트도 `"신선식품"`(`test_schema.py:32`)과 `"fresh_food"`(`test_sink.py:35`)로 갈리고 둘 다 통과한다.
→ **AI_ROI `#43`/`#49` 쪽에서 먼저 확정해야 할 사항이다.**

### G-10 · e2e 검증 경로가 계속 `BLOCKED`다 — 부분 커버

`#25`~`#30` 전부가 검증 계획에 `npm run test:e2e`를 넣었고 "Chromium 설치 필요"를 달아뒀다. `#24`도 BLOCKED로 기록.
CI에서 자동 실행되는 구성이 없어(워크플로 확인 필요) **모든 하위 이슈가 같은 BLOCKED를 반복 상속한다.**

---

## 4. (d) ★ 제거 대상 — 기준 환경에 있으면 안 되는 요소

> 사용자 원문: *"PRD/SRS 대비 없애야 할 것(A테스트 B테스트 UI같은)"*
> **해석 note:** "A/B 테스트(실험) UI"로 읽을 여지도 있어 먼저 확인했다 — **실험·분할·플래그성 UI는 이 저장소에 존재하지 않는다.**
> 실측: `src/`·`e2e/`·`scripts/`에서 `experiment` `ab-test` `feature-flag` `bucket` `treatment` `cohort` `flag` **매치 0건**. `variant` 매치 20건은 전부 버튼 스타일 prop(`StoreLink variant="primary"`)과 CSS `font-variant-numeric`이다.
> 반면 화면 헤더에 **「테스트 사용자 A / B / C」 전환기**가 실재한다(`seed-data.ts:97-99`, `UserMenu.tsx:48`). **후자를 가리킨 것으로 읽었다.** 아래는 두 해석을 모두 포괄한 목록이다.

### 확신 높음 — 제거·교체가 명백히 요구에 부합

| # | 대상 | 위치 | 왜 없어야 하나 |
|---|---|---|---|
| **R-1** | **테스트 사용자 전환 UI 전체** | `UserMenu.tsx`(87줄 전체) · `StoreShell.tsx:30-35`(헤더 배치) · `UserMenu.module.css` · `seed-data.ts:97-99`(`테스트 사용자 A/B/C`) · `selection.ts:5`(`commerce-test-user` 쿠키) · `CheckoutPage.tsx:106`(`<dt>테스트 사용자</dt>`) · `OrderComplete.tsx:13-14` · `app/layout.tsx:15`(메타 description) | 실제 장보기 서비스에 "사용자를 골라서 그 사람이 되는" 화면은 없다. DATA-001은 `customer_id`·`signup_date`를 가진 **고객**을 요구하지 실행 중 전환 가능한 3인 고정 테스트 계정을 요구하지 않는다. **`#29`가 "테스트 사용자 전환 방식은 유지해도 됩니다"라고 명시 → 사용자 지시와 정면 충돌. 판정 필요** |
| **R-2** | **"배송비 0원 / 무료배송" 고정 문구 7곳** | `HomeHero.tsx:36` · `StoreShell.tsx:22` · `ProductDetail.tsx:41` · `CartPage.tsx:86`(`(무료)`) · `CheckoutPage.tsx:111`(`무료배송`)·`:122`(`(무료)`) · `OrderComplete.tsx:49`(`(무료)`) | COM-005 **T1 Free Shipping을 처치로 만들려면 평소 배송비가 0이 아니어야 한다.** 이 문구들은 정책이 아니라 화면에 박힌 상수다. `#26`은 `purchase.ts:41` 코드 상수만 다루고 **UI 문구는 수용 기준에 없다** → 배송비를 도입해도 화면은 계속 "무료"라고 말한다. 테스트도 함께 고정하고 있다(`Catalog.test.tsx:95`, `PurchaseFlow.test.tsx:157,163`) |
| **R-3** | **"샘플 추천" 배지** | `ShopHome.tsx:28` `badge="샘플 추천"` (렌더: `ProductShelf.tsx:21`) | 자기가 더미임을 화면에 표시하는 라벨. 기준 환경에 남을 이유가 없다 |
| **R-4** | **`dummyjson-` 상품 ID 접두사** | `seed-data.ts:5,14,…`(10건) · `heroBanners.ts:8,16,24` · `ShopHome.tsx:14-15` + 테스트 다수 | AI_ROI `product_id ^P\d{4}$`(`schema.py:314`) 위반이며, 외부 더미 API 출처가 도메인 식별자에 박혀 있다. **`#30`은 `source_id`/`source_url` **필드**만 다루고 ID 접두사는 언급하지 않는다** (G-1과 동일 사안) |

### 확신 중간 — 제거가 타당해 보이나 사용자 확인 필요

| # | 대상 | 위치 | 논점 |
|---|---|---|---|
| **R-5** | **"모의 주문 / 구매 테스트 서비스" 문구 9곳** | `StoreShell.tsx:22,70` · `HomeHero.tsx:37` · `ProductDetail.tsx:42` · `CartPage.tsx:90` · `CheckoutPage.tsx:112,113,126`("모의 주문하기" 버튼) · `OrderComplete.tsx:22` · `app/layout.tsx:15` | **찬성:** 기준 환경은 "실제 장보기 서비스처럼 보여야" 시뮬레이터·AI가 해석 가능한 Context가 된다(PRD §12.1). "테스트 서비스"라는 자기고백은 그 전제를 깬다. **반대:** SRS §4.2가 실제 결제를 Out of Scope로 두므로 최소한의 고지는 정당하다. → **"결제 안 함"은 푸터 1곳만 남기고 구매 동선(버튼·안내)에서는 제거**를 제안 |
| **R-6** | **하드코딩된 상품 큐레이션** | `heroBanners.ts:8,16,24`(배너별 productIds) · `ShopHome.tsx:14-15`(`todayPicks`·`buyAgain`) | 상품이 30~50개로 늘면(`#25`) 이 고정 목록은 깨지거나 무의미해진다. 특히 **"다시 담고 싶은 상품"(`ShopHome.tsx:26`)은 재구매 이력 기반이어야** COM-004에 기여하는데 현재는 상수다 — 이름이 데이터에 대해 거짓말을 하고 있다 |
| **R-7** | **`source_id` / `source_url`** | `schema.ts:14-15` · `models.ts:6-7` · `catalog.ts:7` · `initialize.ts:20` | COM-002 컬럼 목록에 없다. **`#30`이 "이 Issue에서 결론을 낸다"고 이미 선언** → 중복 발행 금지. 여기서는 사용자 지시(제거 축)와 `#30`이 같은 대상을 가리킨다는 점만 기록 |

### 확신 낮음 — 판단 재료만 제시, 결정은 사용자

| # | 대상 | 위치 | 양쪽 논거 |
|---|---|---|---|
| **R-8** | **"오늘의 추천" 섹션** | `ProductRecommendations.tsx`(57줄) · `ShopHome.tsx:21` | **제거 논거:** SRS §4.2가 추천 알고리즘을 Out of Scope로 두고, 현재는 알고리즘이 아니라 하드코딩이다. **유지 논거:** `product_view`·`add_to_cart` 퍼널 진입점을 만들어 COM-003 관측에 기여한다. 실제 커머스에도 추천 슬롯은 있다 |
| **R-9** | **히어로 캐러셀 자동 전환** | `HomeHero.tsx:13,22-27,55-72` · `useHeroCarousel.ts` | **측정 관점 리스크:** 자동 전환이 사용자 의도와 무관한 화면 변경을 만든다. `page_view`를 슬라이드마다 기록하면 **세션 품질 Feature(`avg_session_duration`·`page_views_per_session`, `data_spec` §8)에 잡음이 섞인다.** 반대로 실제 커머스에 흔한 UI이기도 하다. → **최소한 "캐러셀 전환을 `page_view`로 기록하지 않는다"는 규칙이 M-3 계약에 필요하다** |

### 4.1 제거 축 요약

- **제거 대상 목록은 비어 있지 않다.** 확신 높음 4건 · 중간 3건 · 낮음 2건 = **9건.**
- **현재 어느 이슈에도 이 축이 없다.** `#30`만 `source_*` 1건을 우연히 겹쳐 다룬다.
- **R-1이 `#29`와 직접 충돌한다** — `#29` 범위 절: *"테스트 사용자 전환 방식은 유지해도 됩니다."* 사용자 지시는 그 반대다. **둘 중 하나가 갱신되어야 한다.**

---

## 5. 이 갭이 AI_ROI C1에 미치는 영향

| 커머스 갭 | 막히는 AI_ROI 작업 |
|---|---|
| `unit_cost` 없음 | `#47`(M-5 경제 규칙) — 기여이익식의 COGS 항. **charter Q2와 동일 사안** |
| `category` 없음 + 어휘 미확정(G-9) | `#43`/`#49` — `category` 허용값 Lock. `data_spec` §8 `category_share_*` Feature |
| 이벤트 기록 없음 | `#45`(M-3) 계약이 **한쪽만의 선언**으로 남는다. Sink의 `sources.commerce`가 영원히 0 |
| 검색·구매이력 화면 없음 (G-4·G-5) | Observable `search_count` 영구 계산 불가. `page_type` 8종 중 3종 미발생 |
| T4 하위 이슈 없음 (G-8) | Observable `campaign_response_count`·`coupon_exposure_count` 계산 불가 |
| 식별자 형식 (G-1) | M-6 참조 무결성 검사(`#48`)가 커머스 실측분에 적용 불가 |
| `orders` 경제 컬럼 부재 (G-3) | 배송비 도입 후 **조용한 0 채우기**가 발생 → charter 절대제약 6 위반 |

**대시보드(W5-C) 관점:** 커머스 이벤트가 0건이므로 charter §3.1③의 "출처 구분되어 보인다"는 **당분간 `commerce: 0`을 정직하게 표시하는 것**으로만 충족된다. 이것이 실패가 아니라 정확한 상태 표시임을 화면이 말해야 한다.

---

## 6. (e) 신규 이슈 초안

**발행하지 않았다.** `.agent-team/01-reverse/issue-drafts/` 에 파일로만 둔다 (AGENTS.md L1).

| 초안 | 대상 저장소 | 내용 |
|---|---|---|
| `ECOM-E7-removal-targets.md` | `Ecommerce_Service` | §4 제거 대상 9건 |
| `ECOM-E8-identifier-timezone.md` | `Ecommerce_Service` | G-1 · G-2 |
| `ECOM-E9-order-economics.md` | `Ecommerce_Service` | G-3 |
| `ECOM-E10-missing-journey.md` | `Ecommerce_Service` | G-4 · G-5 · G-6 · G-7 |
| `ECOM-E11-treatment-t4.md` | `Ecommerce_Service` | G-8 |
| `AIROI-D1-sink-defects.md` | `AI_ROI` | Sink 결함 3건 (`issue-code-audit.md` §2.4) |
| `AIROI-D2-schema-value-enforcement.md` | `AI_ROI` | 타임존·식별자·`category`/`page_type` 미강제 + G-9 어휘 확정 |

---

## 7. BLOCKED

| 항목 | 사유 |
|---|---|
| `npm run build` | `prebuild`가 `src/styles/tokens.generated.css`를 쓰고 `.next/`를 생성 — 파일 생성 금지 |
| `npm run tokens:check` · `tokens:test` | `#24` 기록상 `tokens:generate`(파일 생성) 선행 전제 |
| `npm run test:e2e` | Chromium 미설치. `playwright install`은 파일 생성 |
| 앱 실행 후 화면 확인 | `npm run dev`가 `predev`→`tokens:generate`로 파일을 쓴다. `db:init`도 SQLite 파일 생성 |
| 카테고리별 원가율 정합 확인 (`#25` 수용 기준) | 원가 데이터 자체가 없다 |
