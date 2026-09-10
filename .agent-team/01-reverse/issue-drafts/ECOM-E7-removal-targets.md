# [발행됨 → Ecommerce_Service#32] refactor: 기준 환경에 남으면 안 되는 테스트성 UI·문구·식별자 정리

> **발행 완료 (2026-09-11):** https://github.com/72offsuit/Ecommerce_Service/issues/32 · 상위 Issue: #24 · label: `enhancement`
> **✅ 선행 결정 해소 (2026-09-11):** 사용자가 **"테스트 사용자 전환 UI는 제거 대상 맞다"** 로 판정했다.
> `#29`의 *"테스트 사용자 전환 방식은 유지해도 됩니다"* 문장은 **철회**되었고, `#29` 본문에 「결정 기록」으로 명시됐다.
> → 아래 **1번 항목의 차단이 풀렸다.** 이 초안은 발행 가능 상태다.

## 문제와 목적

- **현재 문제:** 이 서비스는 PRD §12.1이 말한 *"Simulator와 AI Experiment가 해석 가능한 서비스 Context"* 여야 합니다. 그런데 화면 곳곳에 **자기가 테스트·모의임을 선언하는 요소**와 **정책이 아니라 상수로 박힌 값**이 남아 있습니다. 이것들은 ⑴ 처치(Treatment)를 무의미하게 만들고 ⑵ 기록될 이벤트의 의미를 왜곡하며 ⑶ 상품이 30~50개로 늘면(#25) 깨집니다.
- **작업으로 달성할 결과:** 커머스가 "테스트 화면"이 아니라 **측정 가능한 기준 환경**이 됩니다.

## 검증 결과 (2026-09-10, 읽기 전용 분석)

| 명령 | 결과 |
|---|---|
| `npm run lint` | PASS |
| `npm test` | PASS — 13 files / 134 tests |
| `npm run build` · `tokens:check` · `test:e2e` | **BLOCKED** (파일 생성·Chromium 미설치) |

이 Issue의 변경은 **테스트를 함께 고쳐야 합니다** — 아래 문구들이 테스트에 고정되어 있습니다.

## 제거·교체 대상

### 1. 테스트 사용자 전환 UI (**결정 완료 — 제거 확정**)

| 위치 | 내용 |
|---|---|
| `src/components/storefront/UserMenu.tsx` (전체) | 헤더의 사용자 전환 드롭다운 |
| `src/components/storefront/StoreShell.tsx:30-35` | 헤더 배치 |
| `src/lib/server/commerce/seed-data.ts:97-99` | `테스트 사용자 A` · `B` · `C` |
| `src/lib/server/commerce/selection.ts:5` | 쿠키 이름 `commerce-test-user` |
| `src/components/storefront/CheckoutPage.tsx:106` | `<dt>테스트 사용자</dt>` |
| `src/components/storefront/OrderComplete.tsx:13-14` | "선택한 사용자의 화면으로 이동하고 있습니다." |
| `src/app/layout.tsx:15` | 메타 description "테스트 사용자를 선택하고…" |
| `src/components/storefront/StoreShell.test.tsx:42,56,57,67,69,82` | 위 UI를 고정하는 테스트 |

**근거:** SRS DATA-001은 `customer_id`·`signup_date`를 가진 **고객**을 요구하지, 실행 중 서로 전환 가능한 3인 고정 계정을 요구하지 않습니다. 실제 장보기 서비스에 "사용자를 골라 그 사람이 되는" 화면은 없습니다.

**#29와의 관계 (해소됨):** #29의 해당 문장은 2026-09-11 사용자 판정으로 **철회**되었고, #29 본문에 「결정 기록」과 함께 *"고객 모델이 테스트 사용자 전환 UI에 의존하지 않는다"* 수용 기준이 추가됐습니다. 이 Issue가 전환 UI를 제거해도 #29와 모순되지 않습니다.

### 2. "배송비 0원 / 무료배송" 고정 문구 (7곳)

| 위치 | 내용 |
|---|---|
| `src/components/storefront/HomeHero.tsx:36` | `<li>배송비 0원</li>` |
| `src/components/storefront/StoreShell.tsx:22` | `배송비 0원 · 모의 주문` |
| `src/components/storefront/ProductDetail.tsx:41` | `<dt>배송비</dt><dd>0원</dd>` |
| `src/components/storefront/CartPage.tsx:86` | `{formatWon(cart.shippingKrw)} (무료)` |
| `src/components/storefront/CheckoutPage.tsx:111` | `<dd>무료배송</dd>` |
| `src/components/storefront/CheckoutPage.tsx:122` | `(무료)` |
| `src/components/storefront/OrderComplete.tsx:49` | `(무료)` |
| 테스트 | `Catalog.test.tsx:95`, `PurchaseFlow.test.tsx:157,163` |

**근거:** COM-005 **T1 Free Shipping을 처치로 만들려면 평소 배송비가 0이 아니어야** 합니다. #26이 `purchase.ts:41`의 코드 상수를 다루지만 **UI 문구는 수용 기준에 없습니다** — 배송비를 도입해도 화면은 계속 "무료"라고 말하게 됩니다.

### 3. "샘플 추천" 배지

`src/components/storefront/ShopHome.tsx:28` `badge="샘플 추천"` (렌더 `ProductShelf.tsx:21`).
자기가 더미임을 화면에 표시하는 라벨입니다.

### 4. `dummyjson-` 상품 ID 접두사

`src/lib/server/commerce/seed-data.ts` 10건 · `heroBanners.ts:8,16,24` · `ShopHome.tsx:14-15` + 테스트 다수.

**근거:** AI_ROI `src/measurement/schema.py:314`가 `product_id` 를 `^P\d{4}$` 로 규정합니다. 외부 더미 API 출처가 도메인 식별자에 박혀 있습니다. **#30은 `source_id`/`source_url` 필드만 다루고 ID 접두사는 언급하지 않습니다.**

### 5. "모의 주문 / 구매 테스트 서비스" 문구 (9곳) — **범위 결정 필요**

`StoreShell.tsx:22,70` · `HomeHero.tsx:37` · `ProductDetail.tsx:42` · `CartPage.tsx:90` · `CheckoutPage.tsx:112,113,126`(버튼 "모의 주문하기") · `OrderComplete.tsx:22` · `app/layout.tsx:15`.

**제안:** SRS §4.2가 실제 결제를 Out of Scope로 두므로 최소한의 고지는 정당합니다. **푸터 1곳만 남기고 구매 동선(버튼 라벨·단계 안내)에서는 제거**하는 쪽을 제안합니다.

### 6. 하드코딩된 상품 큐레이션 — **#25 이후로 미룰 수 있음**

`heroBanners.ts:8,16,24` · `ShopHome.tsx:14-15`.
특히 `"다시 담고 싶은 상품"`(`ShopHome.tsx:26`)은 **재구매 이력 기반이어야** COM-004에 기여하는데 현재는 상수입니다 — 이름이 데이터에 대해 사실과 다른 말을 합니다.

### 7. 판단 유보 항목 (이 Issue에서 결론만 남김)

| 대상 | 논점 |
|---|---|
| `ProductRecommendations.tsx` "오늘의 추천" | 추천 알고리즘은 SRS §4.2 Out of Scope. 다만 `product_view`·`add_to_cart` 퍼널 진입점 역할은 유효 |
| 히어로 캐러셀 자동 전환 (`HomeHero.tsx:13,22-27,55-72`, `useHeroCarousel.ts`) | 자동 전환을 `page_view`로 기록하면 세션 품질 Feature(`avg_session_duration`·`page_views_per_session`)에 잡음이 섞인다. **최소한 "캐러셀 전환은 `page_view`로 기록하지 않는다"는 규칙이 AI_ROI #45(M-3) 계약에 필요** |
| `source_id` / `source_url` | **#30이 이미 "이 Issue에서 결론을 낸다"고 선언 — 여기서 중복 처리하지 않음** |

## 범위

- 포함: 위 1~6의 제거·교체와 해당 테스트 수정, 7의 결론 기록
- 제외: 배송비 **정책** 도입(#26) · 카탈로그 확장(#25) · 이미지 자산 전략(#30) · 이벤트 기록(#28)

## 수용 기준

- [ ] 화면 어디에도 "테스트 사용자"·"샘플"이라는 표시가 남지 않는다
- [ ] 배송비 표기가 **정책 값을 읽어** 표시된다. 코드·마크업에 `0원`·`무료`가 고정되어 있지 않다
- [ ] `product_id`가 AI_ROI `^P\d{4}$`를 만족하거나, **다르다면 매핑 규칙을 문서화**한다
- [ ] "모의 주문" 고지의 최종 위치와 문구를 결정하고 근거를 남긴다
- [ ] 상품 큐레이션이 상품 목록 변경에 깨지지 않는다 (하드코딩 ID 제거 또는 데이터 기반)
- [ ] 7번 두 항목의 유지/제거를 **결정하고 근거를 남긴다.** 판단 없이 남겨두지 않는다
- [ ] 기존 134개 테스트가 갱신 후 전부 통과한다

## 검증 계획

| 명령 또는 확인 절차 | 기대 결과 | 필요한 환경·제약 |
|---|---|---|
| `npm run lint`, `npm run build` | PASS | — |
| `npm test` | 갱신 후 전건 통과 | 문구 고정 테스트 수정 필요 |
| `npm run test:e2e` | 헤더·구매 동선 확인 | Chromium 설치 |
| 문구 grep | `테스트 사용자` · `샘플` · `배송비 0원` 매치 0건 | — |

## 의존성과 미결정 사항

- ~~선행 결정: #29의 "테스트 사용자 전환 유지" 문장~~ → **해소 (2026-09-11).** #29에서 철회 완료, 1번 진행 가능
- #26(배송비 정책)과 **함께 처리하는 편이 효율적**입니다 — 2번은 #26이 도입하는 값을 표시하는 일입니다
- 4번은 #25(카탈로그 확장)에서 시드를 새로 쓸 때 함께 하면 비용이 거의 0입니다
- 진행을 막는 조건: **없음** (선행 결정 해소됨)
