# [초안 · 미발행] feat: PRD §13 User Journey의 빠진 단계 — 검색·구매이력·상품목록·세션

> **저장소:** `72offsuit/Ecommerce_Service` · **상위 Issue:** #24 · **라벨 제안:** `enhancement`
> **범위가 큽니다.** 4건으로 쪼개는 편이 나을 수 있습니다(§범위 참조).

## 문제와 목적

- **현재 문제:** #28이 커머스에 `search`·`return_visit`을 포함한 12종 이벤트 기록을 요구합니다. 그런데 **그 이벤트를 발생시킬 기능이 존재하지 않습니다.** 검색 화면이 없고, 구매 이력 화면이 없고, 세션 개념이 없습니다. 지금 상태로 #28을 착수하면 **영원히 0건인 이벤트 타입**이 생깁니다.
- **작업으로 달성할 결과:** PRD §13 User Journey와 §14.1 Commerce Funnel이 화면으로 완결되어, 기록할 것이 실제로 발생합니다.

## 요구사항 대조 (2026-09-10 실측)

현재 라우트는 5개입니다 — `src/app/(store)/{page, cart, checkout, orders/[orderId], products/[productId]}`.

| PRD §13 단계 | AI_ROI `page_type` | 커머스 현재 | 판정 |
|---|---|---|---|
| Home | `home` | `src/app/(store)/page.tsx` | ✅ |
| Product List | `list` | **전용 라우트 없음** — 홈의 `#all-products` 앵커뿐 (`ProductListing.tsx:7`) | ❌ |
| **Search** | `search` | **기능 자체가 없음** — 라우트·UI·`catalog.ts` 쿼리 전부 없음 | ❌ |
| Product Detail | `detail` | `products/[productId]/page.tsx` | ✅ |
| Add To Cart → Cart | `cart` | `cart/page.tsx` | ✅ |
| Checkout | `checkout` | `checkout/page.tsx` | ✅ |
| Purchase Complete | `complete` | `orders/[orderId]/page.tsx` | ✅ |
| **Purchase History** | `history` | **화면 없음.** `listOrders()`(`orders.ts:91-98`)는 구현돼 있으나 **테스트에서만 호출**된다 | ❌ |
| Return / Repurchase | (`return_visit`) | **세션·재방문 판정 없음.** 쿠키는 `SELECTED_USER_COOKIE` 하나 (`selection.ts:5`) | ❌ |

### 영향

| 빠진 것 | 영구 계산 불가가 되는 AI_ROI Observable 지표 |
|---|---|
| 검색 | `search_count` (`AI_ROI/src/measurement/schema.py:344`) |
| 세션·재방문 | `visit_count` · `last_visit_date` · `session_duration` (`schema.py:332-334, 343`) |
| 구매 이력 화면 | COM-004 `Repurchase` 단계의 UI 근거 |

`page_type` 8종 중 **3종(`list`·`search`·`history`)이 발생하지 않습니다.**

## 범위

포함 (**4건으로 분리 가능**):

1. **검색** — 검색 입력·결과 화면·`catalog.ts` 조회. `page_type=search`
2. **구매 이력** — `/orders` 목록 라우트. 이미 있는 `listOrders()` 사용. `page_type=history`
3. **상품 목록 라우트** — `page_type=list`. #25의 카테고리 필터가 얹힐 자리
4. **세션** — `session_id` 발급·무활동 30분 만료·재방문 판정

제외: 이벤트 **기록** 자체(#28) · 검색 랭킹/추천 알고리즘(SRS §4.2 Out of Scope) · 실제 인증

## 수용 기준

- [ ] 상품명으로 검색해 결과를 볼 수 있다. 결과 없음 상태가 명확히 표시된다
- [ ] `/orders`에서 자신의 주문 이력을 최신순으로 볼 수 있고, 각 주문 상세로 이동할 수 있다
- [ ] 상품 목록 전용 라우트가 있고, 홈의 앵커가 아니라 URL로 도달할 수 있다
- [ ] `session_id`가 `S-{customer_id}-{세션시작 epoch ms}` 형식으로 발급되고 **무활동 30분이면 만료**되어 새 id를 받는다 (`AI_ROI/docs/event_schema.md:107-108`)
- [ ] 만료 후 재방문을 판정할 수 있다 (`return_visit`의 근거)
- [ ] 네 단계 전부 `page_type` 값과 1:1로 대응되며 그 매핑이 문서에 남는다

## 검증 계획

| 명령 또는 확인 절차 | 기대 결과 | 필요한 환경·제약 |
|---|---|---|
| `npm run lint`, `npm run build` | PASS | — |
| `npm test` | 검색 조회·주문 이력·세션 만료 경계 테스트 통과 | 세션 만료는 시간 주입 필요 |
| `npm run test:e2e` | 홈→검색→상세→담기→결제→완료→이력 완주 | Chromium 설치 |
| `page_type` 대조 | 8종 중 발생 가능 종수가 8/8 | — |

## 의존성과 미결정 사항

- **#28의 선행 조건입니다.** 이것 없이 #28을 착수하면 발생하지 않는 이벤트를 기록하는 코드를 쓰게 됩니다
- #25(카탈로그 확장)와 함께 하면 검색·목록·카테고리 필터를 한 번에 설계할 수 있습니다
- 결정 필요: 4건을 한 Issue로 둘지 쪼갤지. **쪼개는 쪽을 제안** — 세션(4)은 성격이 다르고 #28과 가장 밀접합니다
- 결정 필요: 세션 저장 위치(쿠키 vs 서버). 무활동 만료 판정에 마지막 활동 시각이 필요합니다
- 진행을 막는 조건: 없음
