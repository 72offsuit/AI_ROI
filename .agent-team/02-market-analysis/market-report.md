# 시장 조사 리포트 — T1.8 ~ T1.10

**작성** Caleb (W1 Discovery) · 2026-09-11
**범위** GA4·Amplitude·Mixpanel·PostHog·Segment의 이벤트 스키마 관례(T1.8) · 결손/데이터 품질 표시 관례(T1.9) · 리텐션 KPI 표준(T1.10)
**용도** M-4(KPI 정의, `#46`) 확정 입력 · W2 Jonnathan 대시보드 설계 입력

> 모든 수치·인용에 출처 URL과 확인 날짜(2026-09-11)를 표기한다. 확인하지 못한 항목은 "확인 불가"로 명시한다.

---

## T1.8 — 이벤트 스키마 설계 관례 대조

### 1. 도구별 관례 요약

| 도구 | 표준 이벤트 목록 | 개수 | 세션 정의 | 식별자 규칙 | 출처 |
|---|---|---|---|---|---|
| **GA4** | 고정 목록 있음 (Google 권장 이커머스 이벤트) | 핵심 퍼널 6종(`view_item`·`add_to_cart`·`begin_checkout`·`add_shipping_info`·`add_payment_info`·`purchase`) + 확장 8종(`view_item_list`·`select_item`·`add_to_wishlist`·`remove_from_cart`·`view_cart`·`refund`·`view_promotion`·`select_promotion`) = **14종** | 무활동 **30분 기본값**, 5분~7시간55분 조정 가능 | `item_id` 또는 `item_name` 필수, `transaction_id`는 주문당 유일 | [GA4 Ecommerce Events](https://www.tagada.io/blog/ga-4-ecommerce-events)(2026-09-11 확인) · [GA4 Session](https://support.google.com/analytics/answer/12798876?hl=en)(2026-09-11 확인) |
| **Amplitude** | 고정 목록 없음 — 거버넌스 프레임워크만 권고 | — | 문서에서 확인 불가 | 없음. `Category_Action_Label` 네이밍 규약과 과거형 동사(`Played`, `Completed`) 권고만 존재 | [Amplitude Event Taxonomy](https://amplitude.com/blog/event-taxonomy)(2026-09-11 확인) |
| **Mixpanel** | 고정 목록 없음 — 네이밍 컨벤션만 권고 | — | 문서에서 확인 불가 | `(Object)(Verb)` snake_case 권고(예: `song_played`). Event Name·Timestamp·Distinct ID 3요소가 필수 | [Mixpanel Tracking Strategy](https://docs.mixpanel.com/guides/plan/tracking-strategy)(2026-09-11 확인) |
| **Segment (V2 Ecommerce Spec)** | 고정 목록 있음 | **26종** (browsing 3·promotion 2·ordering 11·coupon 4·wishlist 3·sharing 2·review 1) | 스펙 자체에는 세션 개념 없음 (Segment는 이벤트 파이프라인이지 세션화 도구가 아님) | `product_id`·`order_id`·`cart_id` 등 필드 단위 식별자만 규정, 정규식 규칙은 없음 | [Segment V2 Ecommerce Spec](https://segment-docs.netlify.app/docs/connections/spec/ecommerce/v2/)(2026-09-11 확인, 미러 페이지로 조회 — 공식 `segment.com` 경로는 403으로 직접 조회 실패) |
| **PostHog** | 고정 목록 있음 (Segment V2를 사실상 그대로 채택) | **28종** (Segment와 거의 동일 + 세부 차이) | 무활동 **30분 기본값**, 최대 세션 길이 24시간. `$session_id`를 자동 부여 | 자체 세션 트래킹에 의존, 별도 정규식 없음 | [PostHog Ecommerce Events](https://posthog.com/docs/data/event-spec/ecommerce-events)(2026-09-11 확인) · [PostHog Sessions](https://posthog.com/docs/data/sessions)(2026-09-11 확인) |

**핵심 관찰:**
- **표준 이벤트 "목록"이 있는 도구는 GA4·Segment·PostHog뿐**이다. Amplitude·Mixpanel은 목록이 아니라 네이밍 거버넌스(택소노미 헌장)를 판다 — 이 두 도구는 "몇 개가 맞는가"의 벤치마크로 쓸 수 없다.
- **세션 무활동 타임아웃 30분**은 GA4·PostHog 양쪽에서 기본값으로 확인된다. 우리 스키마의 `SESSION_TIMEOUT_MINUTES = 30`(`src/measurement/schema.py:35`)은 업계 기본값과 **정확히 일치**한다.
- Segment/PostHog는 26~28개 이벤트를 **행위 단위로 세분화**한다(`view_cart`·`select_item`·`add_to_wishlist`를 별도 이벤트로). GA4는 우리와 비슷하게 14개로 더 적다.

### 2. 우리 스키마(16종)와의 대조 및 판정

`docs/event_schema.md`·`src/measurement/schema.py`의 `EventType` 16종:
`session_start · page_view · search · product_view · return_visit · add_to_cart · remove_from_cart · checkout_start · purchase · campaign_exposed · push_sent · coupon_exposed · coupon_clicked · coupon_use · review · cs_contact`

| 비교 축 | 판정 | 근거 |
|---|---|---|
| **이벤트 개수 자체** | **적정 — GA4(14)와 Segment/PostHog(26~28) 사이, GA4 쪽에 더 가깝다** | 순수 개수 비교로는 과하지도 부족하지도 않다. |
| **설계 방식** | **다르다 — 이벤트 증식 대신 필드 분기** | Segment/PostHog는 `view_cart`·`view_item_list`·`select_item`을 별도 이벤트로 만들지만, 우리는 `page_view` + `page_type`(home/list/search/detail/cart/…) 필드로 그 구분을 흡수한다. 이벤트 수만 보면 적어 보이지만 **표현 가능한 상태 공간은 비슷하거나 더 넓다**(`page_type` 8종 × 여러 이벤트 조합). 과부족 판정에서 이 설계 차이를 개수와 별도로 밝혀둔다. |
| **주문 라이프사이클 — 환불/취소** | **부족 — 확인된 갭** | GA4(`refund`)·Segment(`Order Refunded`·`Order Cancelled`)·PostHog(동일) 모두 환불·취소를 표준 이벤트로 갖는다. 우리 스키마에는 `purchase`만 있고 환불·취소 이벤트가 없다. 반복구매 그로서리는 배송 문제로 인한 부분/전체 환불이 실제로 발생하는 도메인이므로, 이 갭은 **기여이익(Contribution Margin) 계산의 정확도에 직접 영향**을 준다(환불된 매출을 순매출에서 빼지 못하면 AI ROI가 과대평가된다). M-5 경제 규칙 설계(W2 Joshua T2.4)에 입력할 사항으로 플래그한다.
| **프로모션/캠페인 클릭 — 쿠폰과 분리** | **경미한 부족** | Segment/PostHog는 `Promotion Viewed`/`Promotion Clicked`를 쿠폰과 별개로 갖는다(쿠폰 없는 배너·추천 캠페인 클릭 추적용). 우리는 `campaign_exposed`(노출)는 있으나 쿠폰이 없는 캠페인의 "클릭"을 담을 이벤트가 없다 — `coupon_clicked`는 쿠폰 전제다. 쿠폰 없는 푸시/배너 캠페인의 반응률을 측정할 수 없다. |
| **위시리스트** | **부족 아님 — 도메인상 불필요할 가능성이 높음(확인 불가)** | 반복구매 그로서리에서 위시리스트 사용률이 낮다는 것은 업계 정설이지만, 이를 뒷받침하는 정량 자료를 이번 조사에서 찾지 못했다 — **확인 불가**. 다만 Segment/PostHog가 3개 이벤트를 할애한다는 점은 참조 가치가 있다. |
| **마케팅/실험 배정 필드 노출** (`treatment_id`·`treatment_group`·`experiment_id`, 메타 4종) | **업계 관례에 없음 — 그러나 결함 아님** | GA4/Segment/PostHog 어디에도 처치군 배정이나 시뮬레이터 버전 같은 필드는 없다. 이들은 실제 서비스 분석 도구이지 **인과 추론 시뮬레이터의 계약**이 아니기 때문이다. 우리 도메인(PRD §21 Observable/Hidden 분리, SRS NFR-002)에 특화된 필드이므로 "과함"이 아니라 **정당한 도메인 확장**으로 판정한다. |

**T1.8 결론:** 이벤트 개수(16)는 업계 범위 안에 있고 세션 정의(30분)는 정확히 일치한다. **실질적 갭은 개수가 아니라 종류다** — 환불/취소 이벤트 부재가 가장 중요한 갭(경제 규칙 계산에 직결), 쿠폰-비종속 프로모션 클릭 이벤트 부재가 경미한 갭이다. 위시리스트 부재는 도메인상 타당해 보이나 확인 불가.

---

## T1.9 — 데이터 품질·결손 표시 관례

우리 프로젝트의 원칙(PRD §10.1, charter 절대 제약 6): **"결손을 조용히 0으로 채우지 않는다. 계산 불가는 계산 불가로 표시한다."** 이를 실제로 구현한 사례를 조사했다.

### 1. 확인된 구체적 패턴

| 패턴 | 사례 | 구체 동작 | 출처 |
|---|---|---|---|
| **임계치 미만 → 행 자체를 숨기고 경고 아이콘 표시** | **GA4 Data Thresholding** | 특정 세그먼트의 사용자 수가 임계치(보통 50명 미만) 미만이면 해당 행을 **0으로 채우지 않고 아예 숨기며**, 오렌지색 경고 아이콘 + "Data thresholding applied" 문구를 리포트 상단에 띄운다. 리포트가 "샘플링 없이 100% 데이터 기반"이라고 표시되어도 이 경고는 별도로 뜬다. 임계치는 사용자가 조정할 수 없다. | [Google 공식: About data thresholds](https://support.google.com/analytics/answer/9383630?hl=en)(2026-09-11 확인) |
| **표본 부족 → "미결정" 상태를 승/패와 분리** | **A/B 테스트 대시보드 일반 관례 (Optimizely 등)** | 표본 부족으로 유의성에 도달하지 못한 경우, 이를 "0% 효과"나 "패배"로 표시하지 않고 **"유의하지 않음/미결정(inconclusive)"** 이라는 제3의 상태로 분리한다. 표본 부족과 "실제 효과가 없음"을 구분해야 한다는 것이 핵심 권고다. | [Optimizely: Why is my experiment failing to reach statistical significance](https://support.optimizely.com/hc/en-us/articles/4410289593869)(2026-09-11 확인) |
| **null(결측)과 0(참 값)을 시각·서술적으로 분리** | 데이터 품질 대시보드 일반 관례 | "빈칸/NA는 결측, 0은 참 값"으로 표기 체계를 고정하고 일관되게 쓸 것을 권고. 결측률을 "컬럼 X의 null 비율 5%"처럼 기술 지표로만 두지 않고 "고객 레코드 5%에 지역 정보 결측 → 대시보드 3개에 영향"처럼 **비즈니스 영향과 연결**해 서술할 것을 권고. | [DQOps: How to Make a Data Quality Dashboard](https://dqops.com/how-to-make-a-data-quality-dashboard/)(2026-09-11 확인) |
| **일반 BI 툴의 최소 대응 — "No Data to Display"** | ServiceNow·IBM API Connect·Amazon QuickSight 등 범용 BI | 데이터가 없으면 차트를 비우거나 "No Data to Display" 메시지로 대체한다 — 0으로 채우는 안티패턴은 피하지만, GA4처럼 **원인(임계치 미만/집계 실패/설정 오류)을 구분해 보여주지는 않는** 최소 수준의 구현이다. | [ServiceNow Community](https://www.servicenow.com/community/platform-analytics-forum/pa-dashboard-visualization-column-showing-no-data-to-display/m-p/1204549)(2026-09-11 확인) 등 (2026-09-11 확인) |

### 2. W2 Jonnathan 대시보드 설계에 대한 권고 패턴

1. **"0"과 "계산 불가"를 서로 다른 시각 상태로 강제 분리한다.** GA4의 오렌지 경고 아이콘 패턴을 참조 — 값이 있는 0(측정됐고 실제로 0)과 값이 없는 0(이벤트 자체가 없거나 표본 부족)을 절대 같은 숫자 "0"으로 렌더링하지 않는다.
2. **원인을 인라인으로 노출한다.** GA4는 경고 아이콘에 원인 설명 링크를 붙인다. 우리 대시보드도 "계산 불가" 상태에 마우스오버 또는 인접 텍스트로 "표본 부족(n<X)" / "필수 이벤트 미수신" / "봉인 전 스키마 버전" 등 구체 사유를 붙여야 한다.
3. **불확실 상태를 "긍정/부정"과 별개의 제3의 색·아이콘으로 표시한다.** A/B 테스트 대시보드의 "inconclusive" 관례를 KPI·Uplift류 지표(향후 사이클)에 적용할 근거로 남긴다. C1에서는 데이터 품질 지표(M-6)에 우선 적용.
4. **결손을 숫자 지표(null 비율)로만 끝내지 않고 영향받는 하위 지표를 명시한다.** 예: "이벤트 수신 결손 3% → `average_order_value` 계산에 영향" 형태로 연결.

**확인 불가:** GA4·A/B 테스트 대시보드 이외에 Amplitude·Mixpanel·PostHog가 자사 프로덕트 대시보드에서 결손을 어떻게 시각적으로 표시하는지는 이번 조사에서 스크린샷·공식 문서 수준으로 확인하지 못했다. 위 3사가 결손을 어떻게 표시하는지는 **확인 불가**로 남긴다.

---

## T1.10 — 리텐션 KPI 표준 정의 교차검증

### 1. Primary / Guardrail / Secondary 프레임워크

| 계층 | 정의 | 특성 | 출처 |
|---|---|---|---|
| **Primary** | 실험/전략이 성공했는지를 판정하는 단 하나의 지표. 가설을 직접 검증한다 | 실험 설계 시 사전에 1개로 고정 | [Statsig: What are guardrail metrics](https://www.statsig.com/blog/what-are-guardrail-metrics-in-ab-tests)(2026-09-11 확인) |
| **Guardrail** | 의도치 않은 부작용을 잡는 안전장치. 엄격한 임계값을 가지며, 임계값을 넘으면 실험 자체를 중단시킨다 ("bad win" 방지) | Primary가 개선돼도 Guardrail이 무너지면 실패로 판정 | 상동 |
| **Secondary** | Primary가 왜 움직였는지 맥락을 주는 3~5개 보조 지표. 단독으로 실험을 중단시키지 않으며 Primary 판정을 뒤집지 않는다 | 메커니즘 설명용 | [Mixpanel: Guardrail metrics](https://mixpanel.com/blog/guardrail-metrics/)(2026-09-11 확인) |

이 3계층 구조는 업계에서 이미 표준화된 어휘다. PRD §66이 요구하는 "Primary/Guardrail/Secondary 고정"은 임의 발명이 아니라 **A/B 테스트·실험 설계 분야의 정설**을 그대로 차용한 것으로 확인된다.

이 프로젝트 맥락에 적용하면(제안 — M-4 확정은 W2 Joshua 소관):
- **Primary 후보**: Incremental Profit / AI ROI (Rule-based Baseline 대비) — PRD가 이미 이것을 핵심으로 지목
- **Guardrail 후보**: 기여이익률(Contribution Margin) 훼손 방지, 쿠폰/Treatment 예산 초과 방지, CS Contact 급증 방지
- **Secondary 후보**: 쿠폰 사용률, 캠페인 반응률, 세션 빈도, Repeat Purchase Rate — Primary가 왜 움직였는지 설명하는 메커니즘 지표

### 2. RFM (Recency·Frequency·Monetary)

소매·그로서리 세그멘테이션의 표준 기법으로 재확인된다. Recency(최근성)·Frequency(빈도)·Monetary(구매액) 3축으로 고객을 나눈다. **소매/이커머스에서는 구매가 빈번하므로 Recency·Frequency에 가중치가 실린다**는 것이 확인된 관례다.

출처: [Braze: Understanding RFM Segmentation](https://www.braze.com/resources/articles/rfm-segmentation)(2026-09-11 확인) · [Optimove: RFM Segmentation](https://www.optimove.com/resources/learning-center/rfm-segmentation)(2026-09-11 확인)

### 3. Contribution Margin (기여이익)

**정의**: `기여이익 = 순매출 − 변동비`. 변동비에는 변동 COGS(매입원가), 물류/배송, 결제수수료, 마케팅/처치 비용이 포함된다. 2026년 기준 건강한 이커머스 기여이익률은 **CAC 차감 후 최소 20%, 지속가능 브랜드는 20~25%+** 로 언급된다.

출처: [ConnectBooks: Contribution Margin for Ecommerce](https://www.connectbooks.com/blog-posts/contribution-margin)(2026-09-11 확인) · [Wayflyer: Contribution Margin Formula](https://wayflyer.com/blog/contribution-margin-over-revenue)(2026-09-11 확인)

**이 프로젝트에 대한 직접 함의**: 기여이익 계산에는 **변동 COGS(=`unit_cost`)가 필수**다. charter가 이미 지적했듯 `Ecommerce_Service`에 `unit_cost`가 없다(이슈 `#24`). 업계 표준 공식 자체가 `unit_cost` 없이는 성립하지 않음을 이번 조사가 재확인했다 — **이는 W2 Joshua T2.4(경제 규칙 v1)의 미해결 항목 Q2를 뒷받침하는 근거 자료**다.

### 4. 그로서리/반복구매 업종 Churn 정의 — 집중 조사

구독 서비스와 달리 명시적 해지 이벤트가 없는 반복구매 그로서리에서 Churn을 어떻게 정의하는지, **4가지 관례**를 확인했다.

| 방법 | 정의 | 장단점 | 출처 |
|---|---|---|---|
| **① 고정 윈도우 (Fixed Window)** | "N일 무구매 = 이탈". 그로서리/배달 업종에서 **30/45/60일**이 관행적으로 쓰인다 | 구현이 가장 쉽지만, 논문·블로그 모두 "직관(gut feeling)에 기반한 임의 값"이라고 자인한다 | [Factspan: Shopper Churn Analysis for a Grocery Delivery Giant](https://factspan.medium.com/shopper-churn-analysis-for-a-grocery-delivery-giant-ea4e29c17c63)(2026-09-11 확인, "45일 무주문") · [Medium: Optimal Churn Period](https://medium.com/@smi.ghotbi/defining-the-optimal-churn-period-a-data-driven-approach-for-platforms-2404894090d2)(2026-09-11 확인, "30일 무구매 관행 및 그 한계") |
| **② 구매 주기 상대적 배수 (Cycle-Relative Multiple)** | 이탈 = 고객(또는 세그먼트)의 **평균 재구매 주기 × 1.5** 를 초과한 무활동. 예: 90일 주기 고객은 135일 무활동 시 이탈 위험 | 페르소나·세그먼트별 구매 주기가 다른 반복구매 업종에 더 적합. 다만 "1.5배"라는 계수 자체의 근거는 확인 불가 — 실무 휴리스틱으로 인용됨 | [Opensend: Churn Rate Statistics](https://www.opensend.com/post/churn-rate-ecommerce)(2026-09-11 확인) |
| **③ 재구매 확률 반감점 (Probability-Decay Threshold)** | 월별 코호트로 "재구매 확률"을 추적하고, 이 확률이 **최초 재구매율의 50%(또는 사용자 정의 비율)로 떨어지는 시점**을 이탈로 정의 | 그로서리처럼 자연 재구매율이 높은 업종에 적합하나, 계산에 코호트별 시계열 데이터가 필요해 구현 비용이 ①②보다 높다 | [Adobe Commerce BI: Analyzing Repeat Probability Decay and Churn](https://experienceleague.adobe.com/en/docs/commerce-business-intelligence/mbi/analyze/performance/repeat-decay-churn)(2026-09-11 확인) |
| **④ 생존분석 기반 데이터 주도 결정 (Survival Analysis)** | 고정 윈도우 대신 생존분석으로 "최적 이탈 판정 시점"을 데이터로부터 도출 | 가장 엄밀하나 구현·해석 난이도가 가장 높음 | [Medium: Defining the Optimal Churn Period](https://medium.com/@smi.ghotbi/defining-the-optimal-churn-period-a-data-driven-approach-for-platforms-2404894090d2)(2026-09-11 확인) |

또한 그로서리 카테고리는 재구매 의향이 특히 높다는 정량 지표도 확인된다: **그로서리 카테고리는 65%의 재구매 의향(repeat purchase intent)을 보이며, 그로서리·소모품 카테고리가 럭셔리·고가 카테고리보다 훨씬 강한 반복구매 행태를 보인다**는 서술이 확인된다.

출처: [Opensend: 7 Churn Rate Statistics For eCommerce Stores](https://www.opensend.com/post/churn-rate-ecommerce)(2026-09-11 확인)

### 5. M-4 입력 — 그로서리 Churn 정의 권고안

우리 스키마(`docs/event_schema.md` "파생 상태 이벤트")는 이미 **①고정 윈도우 방식**을 채택했다: `at_risk = 마지막 구매 후 28~41일`, `churn = 42일 이상`. 이는 업계 조사에서 확인된 그로서리/배달 업종 관행 범위(30~60일)의 **상단 근처에 위치**하며, 관행 자체와 배치되지 않는다.

**권고:**
1. **GATE 1 봉인 시점(C1)에는 현행 고정 42일 윈도우를 그대로 유지한다.** 조사된 4가지 방법 중 가장 구현 비용이 낮고, 업계 관행 범위 안에 있다는 근거가 있다.
2. **단, 이 42일이 "업계 관행"이지 "이 도메인에 최적"이라는 뜻은 아니라는 점을 M-4 문서에 명시한다.** PRD가 여러 페르소나(구매 주기가 서로 다른 고객군)를 전제하므로, 고정 글로벌 윈도우는 구매 주기가 짧은 페르소나에는 너무 관대하고 긴 페르소나에는 너무 엄격할 수 있다.
3. **향후 사이클(시뮬레이터 가동 이후)에서 ②구매 주기 상대적 배수 방식으로 재검증할 것을 다음 사이클 인계 사항에 남긴다.** 시뮬레이터가 페르소나별 실제 `purchase_interval` 분포를 생성하기 전까지는 ②·③·④ 방식을 적용할 데이터가 없으므로 **C1에서 판정할 수 없다** — 이는 범위 밖이 아니라 **선후 관계상 불가능**이다.
4. **`base_churn_propensity` 같은 Hidden Trait와 혼동하지 않는다.** 위 4가지는 모두 **관측 가능한 이벤트로부터 계산하는 라벨/상태 정의**이며, 시뮬레이터가 아는 "진짜 이탈 성향"과는 별개다. 이 구분은 `src/measurement/schema.py`가 이미 정확히 지키고 있다(파생 상태 이벤트는 Feature 사용 금지로 명시).

---

## 확인 불가 항목 전체 목록 (T1.8~T1.10)

- Amplitude·Mixpanel·PostHog가 자사 프로덕트 대시보드에서 결손을 어떻게 시각적으로 표시하는지 (T1.9)
- 그로서리에서 위시리스트 기능 사용률이 낮다는 것을 뒷받침하는 정량 자료 (T1.8)
- "구매 주기 × 1.5배" 계수의 최초 근거/도출 방법 (T1.10 방법 ②)
- Segment 공식 문서(`segment.com`) 직접 조회 — 403으로 차단되어 커뮤니티 미러 페이지로 대체 조회함 (T1.8, 내용은 PostHog 스펙과 상호 검증되어 신뢰도 높음)
