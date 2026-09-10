# 신규 이슈 초안 — **발행하지 않음**

W1 John(Reverse)이 T1.6(e)로 작성한 **초안**이다. AGENTS.md L1 권한상 에이전트는 이슈를 만들지 않는다.
사용자가 "이슈 만들어"를 명시한 뒤에만 발행한다.

| 파일 | 대상 저장소 | 다루는 갭 | 발행 전 필요한 결정 |
|---|---|---|---|
| `ECOM-E7-removal-targets.md` | `Ecommerce_Service` | 제거 대상 9건 | **`#29`의 "테스트 사용자 전환 유지 가능" 문장과 충돌 — 사용자 판정 필수** |
| `ECOM-E8-identifier-timezone.md` | `Ecommerce_Service` | 식별자 형식 3종 · `created_at` UTC | AI_ROI 식별자 형식이 GATE 1에서 확정된 뒤 발행하는 편이 안전 |
| `ECOM-E9-order-economics.md` | `Ecommerce_Service` | 주문 경제값 미저장 · 조용한 0 채우기 | `#26`에 흡수할지 별건으로 낼지 |
| `ECOM-E10-missing-journey.md` | `Ecommerce_Service` | 검색 · 구매이력 · 목록 라우트 · 세션 | 범위가 크다. 4건으로 쪼갤지 |
| `ECOM-E11-treatment-t4.md` | `Ecommerce_Service` | T4 Repurchase Reminder 하위 이슈 부재 | T4를 MVP에서 뺄지(확장 처치) |
| `AIROI-D1-sink-defects.md` | `AI_ROI` | Sink 결함 3건 (덮어쓰기·크래시·타임존) | 없음 — 결함이므로 바로 낼 수 있다 |
| `AIROI-D2-schema-value-enforcement.md` | `AI_ROI` | 값 수준 강제 부재 + 카테고리 어휘 확정 | `#43`·`#49`에 흡수할지 별건으로 낼지 |

**우선순위 제안**

1. `AIROI-D1` — 실행으로 재현된 데이터 소실·크래시. 가장 급하다
2. `AIROI-D2` — `#45`(M-3) 계약 문서의 전제. 카테고리 어휘가 없으면 커머스에 무엇을 요구할지 못 적는다
3. `ECOM-E7` — 사용자가 직접 지시한 축. 단 `#29` 충돌 해소 후
4. 나머지 — `#25`~`#30` 착수 담당이 정해진 뒤
