# [발행됨 → AI_ROI#54] fix: 스키마가 값 수준을 강제하지 않는다 — 식별자·`category`·`page_type`

> **발행 완료 (2026-09-11):** https://github.com/72offsuit/AI_ROI/issues/54 · **관련:** #43 (M-1) · #45 (M-3) · #49 (M-7) · **라벨 제안:** `kind/decision`, `scope/M-measurement`

## 배경

측정 계층은 **커머스와 시뮬레이터 양쪽의 계약**입니다(`src/AGENTS.md`). 계약이 성립하려면 *"어떤 값을 써야 하는가"* 에 답할 수 있어야 합니다.
현재 `schema.py`는 **필드의 존재 여부**는 엄격히 강제하지만 **값**은 전혀 검사하지 않습니다.

## 문제

### D2-1 · `check_identifier()`가 어디에서도 호출되지 않는다

`schema.py:309-326`이 식별자 정규식 9종과 검사 함수를 정의합니다. 그러나 `validate_event()`도 `EventSink`도 이 함수를 부르지 않습니다.

실행 확인:

```python
validate_event({... "customer_id": "test-user-1", "session_id": "whatever" ...})
#   → []                     (통과. 그대로 저장된다)
check_identifier("customer_id", "test-user-1")
#   → False                  (형식 위반은 맞다 — 아무도 묻지 않을 뿐)
```

**커머스의 현재 식별자가 정확히 이 형태입니다** — `test-user-1`(`Ecommerce_Service/src/lib/server/commerce/seed-data.ts:97`), `dummyjson-16`(`seed-data.ts:5`), `randomUUID()`(`orders.ts:115`).

### D2-2 · `category`·`page_type` 허용값이 코드에 없다 — 자체 테스트끼리 어휘가 다르다

| 위치 | 값 |
|---|---|
| `schema.py:115` | `"상품 카테고리 5종"` — **설명 문자열뿐, 열거 없음** |
| `schema.py:111-112` | `"home / list / search / detail / cart / checkout / complete / history"` — **설명 문자열뿐** |
| `tests/test_schema.py:32` | `"category": "신선식품"` (한글) |
| `tests/test_sink.py:35` | `"category": "fresh_food"` (영문) |

**두 테스트가 서로 다른 어휘를 쓰는데 둘 다 통과합니다.** 임의값도 통과합니다:

```python
validate_event({... "page_type": "아무거나" ...})   # → []
validate_event({... "category": "우주선" ...})       # → []
```

### D2-3 · 카테고리 어휘의 정본이 3자 불일치다

| 출처 | 값 |
|---|---|
| SRS COM-001 (`Plan/AI_Customer_Retention_ROI_SRS_v2.0.md:434-444`) | `fresh_food` `meal_solution` `dairy` `beverage` `household` |
| `docs/data_spec.html` §6.1 | 신선식품 · 간편식 · 유제품 · 음료 · 생활용품 |
| `src/measurement/schema.py:115` | 열거 없음 |

`Ecommerce_Service` #25가 *"영문 저장 + 표시명 매핑"* 을 제안했지만, **AI_ROI에 허용값이 없어 계약이 성립하지 않습니다.** 커머스 구현자가 어느 어휘를 쓸지 정본에서 확인할 수 없습니다.

## 왜 지금인가

- **#45(M-3)** 기록 계약 문서가 이것 없이는 *"category를 기록하라"* 이상을 쓸 수 없습니다.
- **#48(M-6)** 참조 무결성 검사가 식별자 형식 없이는 커머스 실측분에 적용되지 않습니다.
- **#49(M-7)** GATE 1이 `EVENT SCHEMA v1`을 Lock합니다. **Lock 이후에는 바꿀 수 없습니다** — 값 규약이 빠진 채 Lock되면 되돌릴 수 없습니다.
- `data_spec.html` §8이 `category_share_fresh` 외 4개를 CLV Feature로 요구합니다. 어휘가 흔들리면 Feature가 흔들립니다.

## 수용 기준

- [ ] `category` 허용값 5종을 **Enum으로 정의**하고 `validate_event()`가 검사한다. 어휘(영문/한글)를 확정하고 근거를 남긴다
- [ ] `page_type` 허용값 8종을 Enum으로 정의하고 검사한다
- [ ] `validate_event()`가 `check_identifier()`를 호출해 형식 위반을 보고한다
- [ ] `tests/test_schema.py`와 `tests/test_sink.py`가 **같은 어휘**를 쓴다
- [ ] 허용값 밖의 값이 거부되는 테스트를 추가한다
- [ ] `docs/event_schema.md`가 재생성되어 허용값 표를 포함한다 (`python3 scripts/gen_event_schema_doc.py`)
- [ ] `docs/data_spec.html` §6.1과 SRS COM-001의 어휘 차이에 대한 결론을 남긴다 (어느 쪽을 정본으로 삼는가)
- [ ] `python3 -m unittest discover -s tests` 기준선 46건에서 회귀 0

## 미확정 — 결정이 필요한 사항

| 항목 | 선택지 | 제안 |
|---|---|---|
| 카테고리 어휘 | 영문 코드 / 한글 | **영문 코드.** SRS COM-001이 정본이고 `data_spec` §6.1은 표 가독성을 위한 표기로 보임. 표시명 매핑은 UI 책임 |
| 식별자 형식 위반 처리 | 거부 / 경고만 | **거부.** 단 MEA-003(부분 소스 관용)과 충돌하지 않도록, **커머스 실측분에는 매핑 계층을 두는 쪽**을 #45 계약에 명시 |
| 매핑 책임 위치 | 커머스가 변환 / 측정 계층이 변환 | **커머스가 기록 시점에 변환.** 측정 계층이 소스별 예외를 알면 창구 중립성이 깨진다 |

> 마지막 항목이 중요합니다 — 측정 계층에 "커머스는 이런 ID를 쓴다"는 지식이 들어가면 **창구가 한쪽 편을 드는 것**이 됩니다(`src/AGENTS.md`). 계약은 하나여야 하고, 맞추는 쪽은 소스입니다.

## 검증 계획

| 명령 또는 확인 절차 | 기대 결과 | 필요한 환경·제약 |
|---|---|---|
| `python3 -m unittest discover -s tests -v` | 신규 테스트 포함 전건 통과 | 표준 라이브러리만 |
| `python3 scripts/gen_event_schema_doc.py \| diff - docs/event_schema.md` | 차이 없음 | — |
| 임의값 거부 확인 | `page_type="아무거나"` · `category="우주선"` 거부 | — |
| 식별자 위반 확인 | `customer_id="test-user-1"` 거부 또는 보고 | — |

## 의존성

- **#49(M-7) GATE 1 Lock 이전에 끝나야 합니다.**
- **#45(M-3)의 선행 조건**입니다 — 계약 문서가 이 값들을 인용합니다
- `Ecommerce_Service` #25·#28·`ECOM-E8` 초안이 이 결정을 기다립니다
