# [초안 · 미발행] feat: T4 Repurchase Reminder — 캠페인·푸시 기록의 근거를 만든다

> **저장소:** `72offsuit/Ecommerce_Service` · **상위 Issue:** #24 · **라벨 제안:** `enhancement`

## 문제와 목적

- **현재 문제:** #24의 대조표가 `T4 Repurchase Reminder … 없음 ❌` 로 기록했지만, **하위 Issue(#25~#30) 어디에도 T4 작업이 없습니다.** #27이 *"T4는 #E-4·별도 논의"* 로 넘겼는데, #28(=E-4)의 수용 기준 이벤트 목록에는 `push_sent`·`campaign_exposed`가 **빠져 있습니다.** 결과적으로 T4는 어느 Issue에도 속하지 않은 채 남았습니다.
- **작업으로 달성할 결과:** COM-005 처치 공간 5종 중 마지막 하나가 커머스에서 표현 가능해지고, 캠페인 계열 이벤트가 발생할 근거가 생깁니다.

## 요구사항 대조

| 요구 | 근거 | 현재 | 덮는 Issue |
|---|---|---|---|
| T0 No Treatment | COM-005 | 기본 상태 | — |
| T1 Free Shipping | COM-005 | `shippingKrw = 0` 하드코딩 | #26 |
| T2 Fixed Coupon | COM-005 | 최소주문금액 없음 | #27 |
| T3 Win-back Coupon | COM-005 | 최소주문금액·유효기간 없음 | #27 |
| **T4 Repurchase Reminder** | COM-005 | **캠페인·푸시 개념 자체 없음** (grep 0건) | **없음** |

### 비용 회계상 왜 중요한가

`AI_ROI/docs/data_spec.html` §6.2:

```
message_cost        =     30원 / 발송   ← 처치군 전원에게 발생 (반응 여부 무관)
campaign_fixed_cost = 100,000원 / 캠페인 ← 운영 고정비
discount_cost       =  7,000원 / 쿠폰 사용 ← 실제 사용 시에만 발생
```

*"메시지 비용은 발송 시점에 전원 발생하고, 할인 비용은 쿠폰이 실제 사용된 주문에만 발생한다. **이 구분이 없으면 '반응하지 않은 고객에게 쓴 돈'이 사라져 ROI가 과대평가된다.**"*

`push_sent`·`campaign_exposed`를 기록할 수 없으면 **발송 시점 비용을 셀 수 없습니다.**

### 영구 계산 불가가 되는 Observable 지표

`AI_ROI/src/measurement/schema.py:340-342` 기준:

- `coupon_exposure_count` ← `coupon_exposed`
- `campaign_response_count` ← `campaign_exposed` · `coupon_clicked` · `purchase`

## 범위

- 포함: 캠페인·발송 개념 도입(데이터 모델 + 노출 지점), T4 처치 표현, `campaign_id` 발급
- 제외: 실제 푸시 전송·외부 메시징 연동(SRS §4.2) · 발송 대상 선정 알고리즘(AI_ROI 소관) · 평균 구매주기 계산(AI_ROI 소관)

**MVP 축소안:** SRS COM-005는 Uplift MVP를 `Control = T0`, `Treatment = 선택된 단일 처치`로 두고, `data_spec` §6.2는 T4를 **"확장"**, T3를 **"사용"** 으로 표시합니다. → **T4를 이번 사이클에서 빼는 결정도 정당합니다.** 다만 *"빠져서 없는 것"* 과 *"빼기로 결정한 것"* 은 다르므로 이 Issue에서 결론을 남깁니다.

## 수용 기준

- [ ] 캠페인 식별자를 발급한다 — 형식은 `AI_ROI/docs/event_schema.md`의 `^CMP-\d{8}-\d{3}$`
- [ ] 고객에게 리마인더가 **노출된 사실**과 그 시각을 기록할 수 있다 (실제 전송이 아니라 서비스 내 노출로 대체 가능)
- [ ] `push_sent` · `campaign_exposed` · `coupon_exposed` · `coupon_clicked` 를 발생시킬 지점이 존재한다
- [ ] 발송 비용(전원)과 할인 비용(사용분)이 **구분 가능한 형태**로 남는다
- [ ] **또는** T4를 이번 범위에서 제외하기로 결정하고, 그 근거와 재개 조건을 문서에 남긴다

## 검증 계획

| 명령 또는 확인 절차 | 기대 결과 | 필요한 환경·제약 |
|---|---|---|
| `npm run lint`, `npm run build` | PASS | — |
| `npm test` | 캠페인 발급·노출 기록 테스트 통과 | — |
| `npm run test:e2e` | 리마인더 노출 → 쿠폰 클릭 흐름 | Chromium 설치 |
| 처치 공간 대조 | COM-005 5종 중 표현 가능 종수 | — |

## 의존성과 미결정 사항

- 선행: #27(쿠폰 조건) — T4가 쿠폰을 동반한다면 조건 필드가 먼저 필요합니다
- 선행: #28(이벤트 기록) — 기록 인프라가 있어야 캠페인 이벤트를 남길 수 있습니다
- **결정 필요: T4를 이번 사이클에 넣을지.** `data_spec` §6.2가 T4를 "확장"으로 표시하므로 **제외 결정도 정당**합니다. 다만 결정을 명시해야 합니다
- 결정 필요: 실제 푸시 없이 "서비스 내 배너 노출"로 대체할지. **대체를 제안** — SRS §4.2가 외부 연동을 Out of Scope로 둡니다
- 진행을 막는 조건: 없음
