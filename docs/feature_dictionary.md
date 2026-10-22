# D1 Feature Dictionary — 계산 구현 초안

상태: 제안 · 2026-10-21 · 광진(kwung0206) 승인 범위의 로컬 구현
기준 설계: D1 v0.2.2, SHA-256 7d18bad5be2edb727b2cca2a38c9418fdb85a3a50fa7e9589d7705356fa97d81.

이 문서는 42개 이름/출력과 실제 구현을 구분한다. 이벤트 계산은 F01–F30·F42의 31종이다. F31–F35는 명시적 합성 세션 사실의 계산 커널 5종이며 자동 이벤트→세션 연결은 보류다. F36–F41 6종은 미구현/결정 대기다. 어떤 항목도 실제 시뮬레이터/커머스 입력 인수를 완료하지 않았다. 상수 null 출력은 계산 완료 수에 포함하지 않는다.

## 공통 정의·입력·품질

- E=(source, entity_namespace, customer_id), K=(E,index_date). 명부가 주어지면 무발생 고객도 보존한다. 명부가 없으면 observed_only이며 전체 고객 모집단이라고 부르지 않는다.
- EventBatch의 source는 simulator/commerce만 허용하고, 측정 계층 sink.event_source()의 이벤트별 파생 출처와 대조한다(#128). 혼합·오선언은 일부 행 제외 대신 입력 전체 거부다. simulator_version·random_seed 둘 다 null이면 commerce, 한 필드만 있어도 현재 공개 규칙상 simulator다. 두 필드 동시 존재를 새 필수 조건으로 만들지 않는다. 합성 시험 목적은 TimePolicy.purpose=synthetic이며 source 예외가 아니다. 빈 묶음의 허용 출처 선언은 명부 키를 보존하지만 실제 출처나 완전 관측의 증명은 아니다. 이 검증은 EventBatch를 사용하는 이벤트 계산·원시 시퀀스에 적용된다. 별도 SessionFact 커널은 E/input pin 동일성을 대조할 뿐 원시 이벤트 메타에서 출처를 파생하지 않으며 실제 세션 제공 계약도 미정이다.
- 이벤트는 measurement.schema의 공개 22컬럼·16유형만 받는다. treatment_id 등 계약상 배정 메타데이터는 수신할 수 있으나 X 선택은 F-ID allowlist만 허용한다. 상품 교환 파일·가입일·라벨·persona는 원천을 확대하지 않는다.
- 최근 d일=[T0-d일,T0), 직전 d일=[T0-2d일,T0-d일), 각각 명시한 cutoff 허용 집합과 교차한다. H는 TimePolicy.history_start부터의 명시적 조회 범위이며 lifetime이 아니다. KST 달력/요일/시각, UTC 정규화 경과시간을 쓴다.
- TimePolicy의 ID·boundary·operator·precision·H·purpose가 필수다. 기본값 없이 P1/P2/P3 합성 비교를 지원한다. purpose=synthetic만 허용한다. 운영 시간 의미는 #126/SD1·SD2 미결정이다. 금지 시각 입력은 계산 전에 전량 거부하고, guard 통과 후의 과거 기간 선택과 구분한다.
- 모든 수치 canonical은 nullable이다. 건수/원 금액은 Int64, 평균/비율/경과일은 Float64. F04 객단가는 평균이므로 Float64다. 실제 큰 값은 보존하고 clip·대치·전체 데이터 fit을 하지 않는다.
- M0 완전 관측에서만 건수/합계 0. M1 기준 이벤트 부재는 NO_SOURCE_EVENT. M2 필요한 간격 부족은 INSUFFICIENT_PURCHASE_INTERVALS. M3 확인된 분모 0은 ZERO_DENOMINATOR. M4 두 기간의 복수 사유를 합쳐 변화값 null. M5 세션 근거/종료/필요 사실 불명은 null. M6 미학습은 TRANSFORM_NOT_FITTED. M7 계약/평생 이력은 CONTRACT_UNRESOLVED 또는 NO_LIFETIME_COVERAGE.
- 관측 근거는 고객·출처·입력 의미 hash·provider/role/contract/ref·이벤트 유형·[start,end)·상태·gaps를 명시한다. 파일/행 존재로 complete를 생성하지 않는다. 없거나 충돌하면 OBSERVATION_UNKNOWN, 미지원이면 UNSUPPORTED_EVENT_KIND, 기간 부족/불완전 주장이면 INCOMPLETE_WINDOW. 하나의 주장으로 필요한 전체 기간을 덮지 못하는 경우 자동으로 여러 주장을 합쳐 complete로 만들지 않는다. 실제 SD3 제공 계약은 미정이다.
- #127: 단일 전체 기간 근거의 존재와 별도로, 같은 E/유형의 요청 창에 겹치는 주장·gap을 모두 판정한다. 전체 complete가 있어도 부분 incomplete/unknown/unsupported는 null과 사유·참조를 보존한다. 서로 다른 상태 공존은 OBSERVATION_UNKNOWN이며 gap/incomplete·unsupported 사유를 함께 둔다. evidence와 gap은 [start,end)다. gap.end==요청.start는 비겹침, gap.start==요청.end는 P1 포함 끝에서만 겹침이다. incomplete 주장의 범위가 겹치면 나열된 gap이 요청 밖이어도 기존 보수적 불완전 판정을 유지한다. 다른 고객/유형/기간 밖 주장은 값 판정에 섞지 않는다. N12701–07과 N12801–04가 해당 반례·대조군이다.
- quality에는 availability, 복수 reasons, observed_events/observed_units/간격 등 감사 건수, 필요한 기간/이벤트 유형, evidence_refs, 알려진 numerator/denominator를 둔다. 관측 결손의 실제 분모를 관측 후보 0으로 대체하지 않는다.
- O1 정수/비음수/유한성 및 Int64 범위. O2 정의된 비율은 [0,1]. O3 음의 변화량 허용. O4 시간/간격 비음수. O5 미결정 표현/범주에 임의 차원·라벨을 부여하지 않는다.
- L1 미래/기간 혼합. L2 미래 세션 종료/순서 추정. L3 fold 밖 fit/객체 혼합. L4 미승인 원천/배정/라벨. L5 H를 평생 이력으로 오인.
- purchase는 고유 order_id 기준이다. 같은 주문의 반복 레코드는 고객·시각·금액이 같을 때만 한 주문으로 집계하며 상충은 거부한다. 같은 event_id는 내용과 관계없이 거부한다. 다른 주문의 동시 구매는 간격 0을 보존한다. order_amount는 할인 후이며 coupon_use를 구매 합계에 더하거나 쿠폰을 재차 차감하지 않는다.
- CV는 90일 안 구매의 내부 간격 2개 이상, 모집단 표준편차/평균이다. 간격 1개만 필요한 F05와 다르다. 45일 경계를 가로지르는 간격은 F27 어느 창에도 넣지 않는다. entropy는 자연 로그(nats)다.
- A는 16종에서 campaign_exposed·push_sent·coupon_exposed를 제외한 13종이다. F42는 정식 출력이며 유효할 때 F28+F42=1. 독립 정보 증가가 아니다. F04/F07도 조합 Feature다.

## F01–F42 정의와 착수/지원 상태

모든 이벤트 커널의 공통 함수는 src/decision/features/d1_calculate.py의 calculate_features → _calculate다. 테스트의 CALC02는 아래 이벤트 31종 모두에 독립 기대값을 가진 정상 사례다. 세션 커널은 d1_session_kernels.calculate_session_kernels다.

각 행은 다음 공통 필수 입력을 포함한다. 원시 이벤트는 event_id·customer_id·timestamp·event_type와 측정 계약의 해당 유형별 필수 필드를 만족해야 한다. source·entity_namespace·snapshot start·고객 명부 여부·index_date·명시적 TimePolicy·필요 기간/이벤트 유형의 ObservationClaim은 별도 메타데이터다. 관측 근거가 없으면 관련 값은 null이며, 원시 이벤트의 필수값 누락은 입력 거부다.

| Feature | 계산에 직접 필요한 공개 값 |
|---|---|
| F01–F07·F26–F28·F42 | purchase의 timestamp·order_id, F03/F04에는 order_amount 추가 |
| F08·F09·F25 | session_start/return_visit의 timestamp·session_id |
| F10·F29·F30 | A의 event_type·timestamp |
| F11·F12·F14–F16·F18–F20 | 해당 event_type·timestamp·event_id; 유형별 필수값은 별도 계약 검증 |
| F13 | product_view의 product_id·timestamp |
| F17·F21 | checkout_start/coupon_use의 order_id·timestamp |
| F22 | campaign_exposed의 timestamp |
| F23·F24 | product_view의 category·timestamp |
| F31–F35 | 별도 SessionFact의 고객/출처·session_id·시작·완료/종료 근거·입력 pin·evidence_ref와 해당 duration/page_views/선행 행동/전환 3값, 모집단 완전성. 실제 제공 계약 미정 |
| F36–F41 | 아래 행의 미승인 표현·학습 객체·가입/여정·전체 이력. 이번 입력으로 대체하지 않음 |

| ID / 이름 | 정의·식 · 단위 | 기간·원천 / 필수 입력 | 타입 | 결측·이상치 | 사업 의미·누수 | 구현 함수·검증 | 지원·공유 의존 |
|---|---|---|---|---|---|---|---|
| F01 recency | (T0-last_purchase)/86400 · days | H·purchase | Float64 | M1 / O4 | 구매 공백 / L1·L5 | _calculate / CALC02·CALC01·03·04 | 이벤트 계산 구현·합성 검증. 운영 #126/SD1·SD2/SD3 대기; 실제 입력 미실행 |
| F02 frequency_90d | count(distinct order_id) · orders | 90일·purchase | Int64 | M0 / O1 | 구매 빈도 / L1 | _calculate / CALC02·CALC01·03·04 | 이벤트 계산 구현·합성 검증. 운영 #126/SD1·SD2/SD3 대기; 실제 입력 미실행 |
| F03 monetary_90d | sum(net order_amount per unique order) · KRW | 90일·purchase | Int64 | M0 / O1 | 할인 후 구매액 / L1 | _calculate / CALC02·CALC01·03·04 | 이벤트 계산 구현·합성 검증. 운영 #126/SD1·SD2/SD3 대기; 실제 입력 미실행 |
| F04 aov_90d | F03/F02 · KRW/order | 90일·purchase | Float64 | M3 / O1 | 객단가 / L1 | _calculate / CALC02·CALC01·03·04 | 이벤트 계산 구현·합성 검증. 운영 #126/SD1·SD2/SD3 대기; 실제 입력 미실행 |
| F05 avg_purchase_interval | mean(adjacent unique purchase gaps) · days | H·purchase | Float64 | M2, 간격 1개 이상 / O4 | 구매 주기 / L1·L5 | _calculate / CALC02·CALC01·03·04 | 이벤트 계산 구현·합성 검증. 운영 #126/SD1·SD2/SD3 대기; 실제 입력 미실행 |
| F06 purchase_interval_cv_90d | population_sd(gaps)/mean(gaps); >=2 gaps · ratio | 90일·purchase | Float64 | M2, 간격 2개 이상 및 M3 / O4 | 주기 불규칙성 / L1 | _calculate / CALC02·CALC01·03·04 | 이벤트 계산 구현·합성 검증. 운영 #126/SD1·SD2/SD3 대기; 실제 입력 미실행 |
| F07 purchase_cycle_anomaly | F01/F05 · ratio | H·purchase | Float64 | M2·M3 / O4 | 평소 주기 대비 지연 / L1·L5 | _calculate / CALC02·CALC01·03·04 | 이벤트 계산 구현·합성 검증. 운영 #126/SD1·SD2/SD3 대기; 실제 입력 미실행 |
| F08 visit_count_60d | count(distinct session_id) · sessions | 60일·해당 이벤트 | Int64 | M0 / O1 | 방문 빈도 / L1 | _calculate / CALC02 | 이벤트 계산 구현·합성 검증. 운영 #126/SD1·SD2/SD3 대기; 실제 입력 미실행 |
| F09 visit_recency | (T0-last_visit)/86400 · days | H·session_start·return_visit | Float64 | M1 / O4 | 방문 공백 / L1 | _calculate / CALC02 | 이벤트 계산 구현·합성 검증. 운영 #126/SD1·SD2/SD3 대기; 실제 입력 미실행 |
| F10 active_days_30d | count(distinct KST activity date) · days | 30일·A | Int64 | M0 / O1 | 활동 지속성 / L1 | _calculate / CALC02 | 이벤트 계산 구현·합성 검증. 운영 #126/SD1·SD2/SD3 대기; 실제 입력 미실행 |
| F11 page_view_count_60d | count(page_view) · events | 60일·page_view | Int64 | M0 / O1 | 탐색량 / L1 | _calculate / CALC02 | 이벤트 계산 구현·합성 검증. 운영 #126/SD1·SD2/SD3 대기; 실제 입력 미실행 |
| F12 product_view_count_60d | count(product_view) · events | 60일·product_view | Int64 | M0 / O1 | 상품 관심 / L1 | _calculate / CALC02 | 이벤트 계산 구현·합성 검증. 운영 #126/SD1·SD2/SD3 대기; 실제 입력 미실행 |
| F13 distinct_viewed_products_180d | count(distinct product_id) · products | 180일·product_view | Int64 | M0 / O1 | 관심 상품 폭 / L1 | _calculate / CALC02 | 이벤트 계산 구현·합성 검증. 운영 #126/SD1·SD2/SD3 대기; 실제 입력 미실행 |
| F14 search_count_60d | count(search) · events | 60일·search | Int64 | M0 / O1 | 능동 탐색 / L1 | _calculate / CALC02 | 이벤트 계산 구현·합성 검증. 운영 #126/SD1·SD2/SD3 대기; 실제 입력 미실행 |
| F15 add_to_cart_count_60d | count(add_to_cart) · events | 60일·add_to_cart | Int64 | M0 / O1 | 구매 의도 / L1 | _calculate / CALC02 | 이벤트 계산 구현·합성 검증. 운영 #126/SD1·SD2/SD3 대기; 실제 입력 미실행 |
| F16 remove_from_cart_count_60d | count(remove_from_cart) · events | 60일·remove_from_cart | Int64 | M0 / O1 | 장바구니 조정 / L1 | _calculate / CALC02 | 이벤트 계산 구현·합성 검증. 운영 #126/SD1·SD2/SD3 대기; 실제 입력 미실행 |
| F17 checkout_count_60d | count(distinct order_id) · orders | 60일·checkout_start | Int64 | M0 / O1 | 결제 진입 / L1 | _calculate / CALC02 | 이벤트 계산 구현·합성 검증. 운영 #126/SD1·SD2/SD3 대기; 실제 입력 미실행 |
| F18 cs_contact_count_60d | count(cs_contact) · events | 60일·cs_contact | Int64 | M0 / O1 | 문의 빈도 / L1 | _calculate / CALC02 | 이벤트 계산 구현·합성 검증. 운영 #126/SD1·SD2/SD3 대기; 실제 입력 미실행 |
| F19 review_count_180d | count(review) · events | 180일·review | Int64 | M0 / O1 | 구매 후 참여 / L1 | _calculate / CALC02 | 이벤트 계산 구현·합성 검증. 운영 #126/SD1·SD2/SD3 대기; 실제 입력 미실행 |
| F20 coupon_exposure_count_180d | count(coupon_exposed) · events | 180일·coupon_exposed | Int64 | M0 / O1 | 과거 쿠폰 접점 / L1·L4 | _calculate / CALC02 | 이벤트 계산 구현·합성 검증. 운영 #126/SD1·SD2/SD3 대기; 실제 입력 미실행 |
| F21 coupon_used_order_count_180d | count(distinct order_id) · orders | 180일·coupon_use | Int64 | M0 / O1 | 과거 쿠폰 이용 / L1·L4 | _calculate / CALC02 | 이벤트 계산 구현·합성 검증. 운영 #126/SD1·SD2/SD3 대기; 실제 입력 미실행 |
| F22 days_since_last_campaign_180d | (T0-last_campaign)/86400 · days | 180일·campaign_exposed | Float64 | M1 / O4 | 과거 캠페인 접점 공백 / L1·L4 | _calculate / CALC02 | 이벤트 계산 구현·합성 검증. 운영 #126/SD1·SD2/SD3 대기; 실제 입력 미실행 |
| F23 category_entropy_180d | -sum(p*ln(p)) · nats | 180일·product_view | Float64 | M3 / O1 | 관심 카테고리 다양성 / L1 | _calculate / CALC02·CALC13 | 이벤트 계산 구현·합성 검증. 운영 #126/SD1·SD2/SD3 대기; 실제 입력 미실행 |
| F24 dominant_category_share_180d | max(category count)/product_view count · ratio | 180일·product_view | Float64 | M3 / O2 | 관심 집중도 / L1 | _calculate / CALC02·CALC13 | 이벤트 계산 구현·합성 검증. 운영 #126/SD1·SD2/SD3 대기; 실제 입력 미실행 |
| F25 visit_count_change_2w | recent14 visits/previous14 visits · ratio | 14+14일·방문 이벤트 | Float64 | M3·M4 / O1 | 방문 증감 비율, 1이면 동일 / L1 | _calculate / CALC02·CALC05·10·11 | 이벤트 계산 구현·합성 검증. 운영 #126/SD1·SD2/SD3 대기; 실제 입력 미실행 |
| F26 purchase_frequency_change | (recent30 orders-previous30 orders)/30 · orders/day | 30+30일·purchase | Float64 | M4 / O3 | 일평균 구매 빈도 변화 / L1 | _calculate / CALC02·CALC05·10·11 | 이벤트 계산 구현·합성 검증. 운영 #126/SD1·SD2/SD3 대기; 실제 입력 미실행 |
| F27 purchase_interval_change | mean(recent45 internal gaps)-mean(previous45 internal gaps) · days | 45+45일·purchase | Float64 | M2·M4 / O3 | 구매 주기 변화 / L1 | _calculate / CALC02·CALC05·10·11 | 이벤트 계산 구현·합성 검증. 운영 #126/SD1·SD2/SD3 대기; 실제 입력 미실행 |
| F28 weekday_purchase_ratio | KST weekday orders/all orders · ratio | 90일·purchase | Float64 | M3 / O2 | 평일 구매 성향 / L1 | _calculate / CALC02·CALC12·21 | 이벤트 계산 구현·합성 검증. 운영 #126/SD1·SD2/SD3 대기; 실제 입력 미실행 |
| F29 morning_activity_ratio | 06<=KST hour<12 activity/all activity · ratio | 90일·A | Float64 | M3 / O2 | 오전 활동 성향 / L1 | _calculate / CALC02·CALC12·21 | 이벤트 계산 구현·합성 검증. 운영 #126/SD1·SD2/SD3 대기; 실제 입력 미실행 |
| F30 evening_activity_ratio | 18<=KST hour<24 activity/all activity · ratio | 90일·A | Float64 | M3 / O2 | 저녁 활동 성향 / L1 | _calculate / CALC02·CALC12·21 | 이벤트 계산 구현·합성 검증. 운영 #126/SD1·SD2/SD3 대기; 실제 입력 미실행 |
| F31 avg_session_duration | mean(completed session duration) · seconds | 시작 기준 60일·세션 이벤트 | Float64 | M5, 일부 duration 누락 시 null / O4 | 세션 체류 / L1·L2 | calculate_session_kernels / SESS01–12 | 합성 사실 커널 구현·검증. 이벤트 연결 보류(SD3 실제 시작/종료·duration·순서 제공자); 실제 입력 미실행 |
| F32 page_views_per_session | completed session page_views/completed sessions · views/session | 시작 기준 60일·세션 이벤트 | Float64 | M3·M5 / O1 | 세션 탐색 깊이 / L1·L2 | calculate_session_kernels / SESS01–12 | 합성 사실 커널 구현·검증. 이벤트 연결 보류(SD3 실제 시작/종료·duration·순서 제공자); 실제 입력 미실행 |
| F33 search_to_purchase_conversion | search conversion true/(true+false); unknown -> null · ratio | 시작 기준 60일·search·purchase | Float64 | M3·M5 / O2 | 검색 후 구매 전환 / L1·L2 | calculate_session_kernels / SESS01–12 | 합성 사실 커널 구현·검증. 이벤트 연결 보류(SD3 실제 시작/종료·duration·순서 제공자); 실제 입력 미실행 |
| F34 session_duration_change | recent14 duration mean-previous14 duration mean · seconds | 14+14일·세션 이벤트 | Float64 | M4·M5 / O3 | 체류 변화 / L1·L2 | calculate_session_kernels / SESS01–12 | 합성 사실 커널 구현·검증. 이벤트 연결 보류(SD3 실제 시작/종료·duration·순서 제공자); 실제 입력 미실행 |
| F35 cart_conversion_change | recent30 cart conversion-previous30 cart conversion · ratio difference | 30+30일·add_to_cart·purchase | Float64 | M3·M4·M5 / O3, 범위 [−1,1] | 구매 의도 실현 변화 / L1·L2 | calculate_session_kernels / SESS01–12 | 합성 사실 커널 구현·검증. 이벤트 연결 보류(SD3 실제 시작/종료·duration·순서 제공자); 실제 입력 미실행 |
| F36 recent_event_sequence_embedding | 최근 30이벤트의 유형·간격·mask를 사용하는 Train-fitted 표현 · vector | H·16종 이벤트, 최종 30개 및 선택 경계 순서 근거 | VectorFloat32 | M6 / O5 | 행동 순서 표현 / L1·L3 | 원시 입력만 generate_raw_sequences / SEQ01–18. 학습 Feature 미구현 | 보류: SD4 표현 적합성·Train 학습 승인/객체 필요. 리드·D3 결정. 원시 생성·기존 opaque 객체 시험은 실제 학습 아님 |
| F37 behavior_pattern_cluster_id | Train-fitted cluster(F36) · category | F36 | Category | M6 / O5 | 행동 패턴 유형 / L3 | 미구현 / 실제 계산 미실행 | 보류: SD4 표현 적합성·Train 학습 승인/객체 필요. 리드·D3 결정. 기존 opaque 객체 시험은 실제 학습 아님 |
| F38 current_journey_stage | approved public journey state table · category | 가입 이후 보장 이력·관련 이벤트 | Category | M7 / O5 | 여정 도달 단계 / L4·L5 | 미구현 / 실제 계산 미실행 | 보류: SD5 가입일 원천·SD8 여정 규칙·SD3 이력. 리드/입력 계약/D2–D5 결정 및 계약 근거 필요 |
| F39 days_in_current_stage | (T0-stage entry)/86400 · days | F38·진입 이벤트 | Float64 | M7 / O4 | 단계 체류 / L4·L5 | 미구현 / 실제 계산 미실행 | 보류: SD5 가입일 원천·SD8 여정 규칙·SD3 이력. 리드/입력 계약/D2–D5 결정 및 계약 근거 필요 |
| F40 days_signup_to_first_purchase | KST first purchase date-KST signup date · days | signup_date·첫 purchase | Int64 | M7 / O4 | 최초 전환 소요일 / L4·L5 | 미구현 / 실제 계산 미실행 | 보류: SD5 가입일 원천·SD8 여정 규칙·SD3 이력. 리드/입력 계약/D2–D5 결정 및 계약 근거 필요 |
| F41 repurchase_count | max(lifetime unique purchases-1,0) · orders | 보장된 가입 이후 또는 최초 구매 이후 전체 이력 | Int64 | M7 / O1 | 재구매 경험 / L5 | 미구현 / 실제 계산 미실행 | 보류: SD3 최초 구매부터 평생 전체 이력의 실제 제공 근거 필요. H를 lifetime으로 대체하지 않음 |
| F42 weekend_purchase_ratio | KST weekend orders/all orders · ratio | 90일·purchase | Float64 | M3 / O2 | 주말 구매 성향 / L1 | _calculate / CALC02·CALC12·21 | 이벤트 계산 구현·합성 검증. 운영 #126/SD1·SD2/SD3 대기; 실제 입력 미실행 |

## 구현·품질 및 연결 경계

원천/기간 검증은 d1_feature_inputs.EventBatch·TimePolicy·ObservationClaim, 구매/빈도/간격은 _Customer 및 _calculate, 변화 결합은 combine, 소비자 메타데이터 분리는 FeatureOutput.learning_view가 담당한다. quality 행과 재현 정보에는 입력·정책·근거 의미 hash 및 Feature/이벤트 계약 버전이 있다. 기존 TLV/typed/table_hash primitive를 재사용하며 새 입력/정책의 domain은 계산 단계 식별자다. 기존 raw_bundle/view/loader 계약을 변경하지 않는다.

core_feature_schema()는 실제 이벤트 계산 31종만 순서가 고정된 nullable 스키마로 반환한다. 미구현 벡터의 차원·범주를 가정하지 않는다. typed_core_rows()와 이 스키마를 사용한 CALC14는 기존 table_hash에 대한 타입·순서 호환 검사이며 전체 raw bundle을 구성하거나 게시하지 않는다.

세션 사실은 원시 이벤트 계산 원천을 확장하는 운영 계약이 아니다. 후보 시작·완료/진행/unknown·관련 구간 관측·duration·page_views·선행 행동/전환의 true/false/unknown·입력 identity·근거 ref를 명시한 합성 커널 입력이다. 실제 공개 이벤트에서 그 사실을 생산하는 어댑터는 제공 계약 대기다. 따라서 calculate_features의 F31–F35는 CONTRACT_UNRESOLVED이며 커널 별도 결과와 혼동하지 않는다.

F33/F35는 n_true, n_false, n_unknown_outcome, n_unknown_membership, n_no_antecedent, n_open_excluded, observed_denominator를 보존한다. unknown이 남으면 canonical·확정 numerator/denominator는 null이다. 미판정 후보를 버리고 분모를 줄이지 않는다. 알려진 진행 세션만 정의상 제외한다. F31은 일부 duration이 빠져도 관측된 것만 평균내지 않는다. F32의 page_views는 필요한 구간 관측이 complete여야 한다.

기존 로더의 T0 자정 제약(#126)과 시퀀스 간격 null 표현(F6)이 남아 있어 전체 파일 bundle 연결은 미실행/보류다. 시간 필드를 바꾸거나 masked 0으로 바꾸어 통과시키지 않는다. 검증한 연결은 기존 typed/TLV/테이블 hash의 수치 타입 투영까지이며, 이것을 load_bundle 인수로 표현하지 않는다.

## 전체 인수에 남은 조건

실제 SD3 근거와 운영 SD1/SD2 정책, 세션 이벤트 어댑터, SD4/학습 시퀀스 2종, SD5/SD8 여정·가입일, F41 평생 근거가 남아 있다. 행동 변화는 이번 이벤트 기반 3종(F25–F27)뿐이며 SRS의 5종 이상을 충족했다고 하지 않는다. 세션 변화 커널 2종을 실제 이벤트 Feature로 인수한 것도 아니다. 실제 입력 결측률·SD7 분모/예외·소비자 split·인수·소유 등록·독립 검토는 별도다. 계산 이름 수·출력 42열·이벤트 계산 31종·조건부 커널 5종을 구분한다.

## 후속 구현: 학습 전 원시 시퀀스

d1_raw_sequence.generate_raw_sequences는 d1-raw-sequence/1-proposed의 인메모리 원시 표현만 만든다. 고정 사전은 PAD=0, add_to_cart부터 session_start까지 설계 C의16종=1–16이다. H의16종 완전 관측을 확인하며 최근30개를 과거→최근, 왼쪽 PAD로 둔다. 순서는 선택된 그룹과30번째 경계의 전체 동시각 묶음까지만 검사한다. 오래된 tie 때문에 차단하거나 event_id/입력 행 순서로 tie를 해소하지 않는다.

현재 순서 주입은 E·timestamp·event_id/ordinal·입력 hash·provider/contract/ref에 결합된 합성 OrderClaim뿐이다. 실제 SD3 제공 계약 승인이 아니다. 필요한 tie에 근거가 없거나 전체 묶음을 설명하지 못하면 UNKNOWN/AMBIGUOUS_EVENT_ORDER다. 정수 ms로 정확히 표현되지 않는 선택 간격은 UNKNOWN/CONTRACT_UNRESOLVED와 SUBMILLISECOND_GAP_REPRESENTATION으로 해당 행만 보류한다. 반올림하지 않는다.

VALID와 EMPTY_COMPLETE는30칸 tokens/mask/relative_gap_ms/gap_mask를 가진다. 첫 실제 이벤트와 PAD gap은 null/false, 확정된 동시각 gap은0/true다. EMPTY_COMPLETE는 길이0과 NO_SEQUENCE_INFORMATION, 관측 불명 UNKNOWN은 length/배열 null과 관측 사유로 구분하고 고객을 보존한다. 기존 FeatureOutput의 F36/F37 미학습 값/사유는 별개이며 원시 생성으로 갱신하지 않는다. SEQ01–18은 합성 구조·경계 검증이고 FE-006의 학습 Feature2종이나 실제 입력 인수가 아니다. nullable gap/cutoff 문제를 남긴 전체 로더 연결과 파일 게시는 계속 보류다.

## 후속 구현: 명시적 모집단의 원시 품질 집계

d1_quality_summary.aggregate_raw_quality는 caller_supplied_K 목록과 명시적 F-ID 목록에서 raw null/available 수·분모·결측률·사유별 건수를 반환한다. 같은 호출에서는 명시한 K 행 수를 각 Feature의 분모로 쓰며, source/namespace/index_date를 합치지 않는다. 별도의 E 수도 반환한다. Feature별 U_f가 다르면 별도 명시적 호출로 구분한다. 미구현 Feature를 포함해 요청 목록을 그대로 남기고 canonical/quality/모집단 행 누락·중복·가용성 모순은 입력 오류다.

분모0은 rate=null·ZERO_DENOMINATOR다. 사유별 건수 합계는 분모보다 클 수 있다. 예외/행 제거0, short-history 조정 미적용, official_verdict=null이며 SD6/SD7 공식 모집단·분할·예외·5% 합격을 정하지 않는다. QUAL01–13은 합성 검증이다. 이 요약은 출처·학습 객체·정식 계보를 검증하는 로더나 실제 원시 결측률 인수를 대신하지 않는다.

## 2026-10-22 합성 근거·원시 시퀀스 파일 연결

SD1–SD8 및 Q1–Q5의 사용자 방향 선택은 유지한다. 위 과거의 대기 표시는 당시 기록이며 방향 선택 자체를 다시 미결정으로 되돌리지 않는다. #126의 공통 cutoff 계약 반영, 실제 G1·제공자 근거·인수, 학습 실행·소비자 인수는 여전히 별도다.

`d1_evidence.verify_evidence`는 W0 I03 synthetic의 생산·전달·수신을 각각 검증한다. 외부 Expected FilePin과 제공된 bytes를 확인하고 공개 이벤트/고객 projection으로 EventBatch identity를 재구성한다. 파일 경로를 탐색하지 않는다. 합성 JSON 근거 본문은 해당 record의 provider 제외 본문으로 고정하며 운영 제공 계약을 대신하지 않는다. 부분 전달/수신·정밀도 손실·누락/시점 미충족 근거는 관측 unknown/incomplete로 전파한다. 필요한 최근30개/선택 경계 tie만 full-tie 고유 ordinal을 요구하며 불필요한 과거 tie의 실제 이벤트 존재까지 검사하지 않는다. 다른 capability를 event_capture로 간주하지 않는다. admission은 항상 BLOCKED_ADMISSION이고 operational 요청은 거부한다.

`d1_sequence_file.adapt_sequences`는 검증된 근거 context와 기존 RawSequenceOutput의 재현 정보를 대조해 `d1-sequence-file/2-proposed` SequenceRow로 투영한다. 숫자 토큰과 고정 문자열 사전 간 변환은 명시적이며 UNKNOWN의 length/배열 null·완전 관측 빈 입력·첫/PAD gap null과 실제0을 보존한다. 원시 감사/선택 event_id는 원래 RawSequenceOutput에 남는다. 파일은 모든 감사 필드를 보관하는 전체 원시 bundle이 아니다.

`encode_sequence_file`/`decode_sequence_file`은 실제 Parquet bytes와 typed 값의 hash를 구분한다. nullable Int64 gap, string token, Bool mask, date32의 실제 dtype을 검사한다. 의미 hash는 typed 행·입력/관측/필요 순서 의미·명시 정책을 포함하고 생성 시각·압축·물리 행 순서·근거 파일 포장을 제외한다. reader는 별도의 정확한 파일 SHA256과 필요한 근거 FilePin을 계속 요구한다. legacy load_bundle의 cutoff/UNKNOWN 표현·전체 Store/CURRENT는 수정하지 않는다. 원시 파일 투영으로 F36/F37 학습 또는 FE-006 전체 충족을 주장하지 않는다.

관련 결정: `docs/decisions/DR-D1-w1-evidence-sequence-file.md`. 합성 검증과 실제 입력 인수를 구분하며 소유 등록·독립 검토는 후속이다.
