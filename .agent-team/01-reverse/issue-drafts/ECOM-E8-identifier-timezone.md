# [초안 · 미발행] fix: 식별자 형식과 시각 표기를 측정 계층 계약에 맞춘다

> **저장소:** `72offsuit/Ecommerce_Service` · **상위 Issue:** #24 · **라벨 제안:** `enhancement`

## 문제와 목적

- **현재 문제:** AI_ROI 측정 계층(`src/measurement/schema.py:309-319`)이 식별자 정규식 9종과 타임존 규약(KST 단일 · ISO 8601 + offset · 밀리초, `schema.py:29-33`)을 정본으로 확정했습니다. 커머스의 현재 값은 **4종 중 4종이 모두 이 형식을 벗어납니다.** 기존 Issue는 이 중 `session_id`(#28)와 `customer_id`(#29)만 다룹니다 — **`product_id`·`order_id`·`coupon_id`와 시각 표기는 어느 Issue에도 없습니다.**
- **작업으로 달성할 결과:** 커머스가 만든 레코드가 AI_ROI의 `validate_event()`·참조 무결성 검사(#48)를 그대로 통과합니다.

## 요구사항 대조 (2026-09-10 실측)

| 필드 | AI_ROI 요구 | 커머스 현재 | 근거 | 덮는 Issue |
|---|---|---|---|---|
| `customer_id` | `^C\d{8}$` | `test-user-1` | `src/lib/server/commerce/seed-data.ts:97-99` | #29 |
| `session_id` | `^S-C\d{8}-\d{13}$` | 세션 개념 자체 없음 | `selection.ts:5` (쿠키 1종뿐) | #28 (형식만) |
| **`product_id`** | `^P\d{4}$` | `dummyjson-16` | `seed-data.ts:5` 외 10건 | **없음** |
| **`order_id`** | `^O\d{8}-\d{6}$` | `randomUUID()` | `src/lib/server/commerce/orders.ts:115` | **없음** |
| **`coupon_id`** | `^CPN-[A-Z0-9]{6}$` | `fixed-3000` · `rate-10` | `seed-data.ts:103-104` | **없음** |
| **주문 시각** | KST · ISO 8601 **+ offset** · ms | `new Date().toISOString()` → `…Z` (UTC) | `orders.ts:116` | **없음** |

### 왜 지금 중요한가

AI_ROI 쪽 `validate_event()`는 **이 위반을 잡지 못합니다** — `check_identifier()`(`schema.py:324-326`)가 어디에서도 호출되지 않습니다(AI_ROI 별건으로 기록). 즉 **양쪽 모두 막지 않는 구멍**이고, 잘못된 식별자가 그대로 저장된 뒤에야 드러납니다.

시각 표기는 더 조용합니다. UTC `2026-09-10T23:30:00.000Z` 는 KST로 다음 날 08:30인데, AI_ROI 파티션 키는 `2026-09-10`을 만듭니다(실행 확인). **코호트·`purchase_interval`·리텐션이 하루씩 밀립니다.**

## 범위

- 포함: `products`·`orders`·`coupons` 식별자 형식 정합(또는 매핑 규칙 문서화), 주문 시각 표기 정합
- 제외: 이벤트 기록 자체(#28) · 고객 스키마 확장(#29) · 카탈로그 확장(#25)

## 수용 기준

- [ ] `product_id`·`order_id`·`coupon_id`가 AI_ROI `docs/event_schema.md`의 형식을 만족한다. **또는** 매핑 규칙(커머스 내부 ID ↔ 계약 ID)을 문서화하고 변환 지점을 한 곳에 둔다
- [ ] 주문·이벤트의 모든 시각이 **KST 오프셋(`+09:00`)을 포함**하고 밀리초 정밀도를 갖는다. UTC `Z` 표기가 남지 않는다
- [ ] 기존 주문 데이터와의 호환(마이그레이션 또는 재초기화) 방침을 명시한다
- [ ] 형식 검증을 테스트로 고정한다 — 정규식 위반 시 실패

## 검증 계획

| 명령 또는 확인 절차 | 기대 결과 | 필요한 환경·제약 |
|---|---|---|
| `npm run lint`, `npm run build` | PASS | — |
| `npm test` | 식별자 형식·시각 표기 테스트 추가 후 통과 | — |
| 형식 대조 | 저장된 식별자가 `AI_ROI/docs/event_schema.md` 정규식과 일치 | — |
| 시각 대조 | `created_at` 문자열에 `+09:00` 포함 · `Z` 0건 | — |

## 의존성과 미결정 사항

- **AI_ROI 쪽 식별자 형식이 아직 임의값입니다.** AI_ROI #43 코멘트가 *"근거 문서에 규정이 없어 임의로 정한 값"* 이라고 자인했고 #49(GATE 1)에서 Lock 예정입니다. → **Lock 이후에 착수하는 편이 재작업이 없습니다**
- 결정 필요: 커머스 내부 ID를 바꿀지, 내부는 두고 **기록 시점에만 변환**할지. 후자가 기존 주문 호환에 유리합니다
- 진행을 막는 조건: 없음 (다만 위 Lock 대기 권장)
