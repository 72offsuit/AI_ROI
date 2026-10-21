# DR-D1-feature-calculation — 명시적 시간·관측 입력의 과거 Feature 계산

| 항목 | 내용 |
|---|---|
| 태스크 | D1 · #83 |
| 작성 | Codex · 광진(kwung0206) 요청 · 2026-10-21 |
| 상태 | 제안 |
| 기준 | D1 v0.2.2 · 7d18bad5be2edb727b2cca2a38c9418fdb85a3a50fa7e9589d7705356fa97d81 |
| 범위 | 명시적 시험 정책·관측 근거의 실제 계산, 합성 검증. 운영 정책·학습·게시 승인 아님 |

## 무엇을 정하는가

F01–F30·F42를 공개 22컬럼에서 계산하고 F31–F35는 명시적 세션 사실을 받는 순수 커널로 검증한다. F36–F41은 필요한 학습/공유 결정/평생 근거가 없어 보류한다. 각 ID의 식·자료형·기간·상태는 docs/feature_dictionary.md에 전체 42행으로 남긴다. 기존 hash·로더 3모듈과 #122–#125 수정은 보존한다.

## 정하지 않으면 무엇이 막히나

이벤트 부재를 실제 0으로 오인하거나 시험용 cutoff를 운영 기본값으로 굳히게 된다. 같은 고객 문자열을 출처 간 합치거나 명부 전용 고객을 버리면 소비자 입력 모집단도 바뀐다.

## 선택지

| 안 | 장점 | 한계 |
|---|---|---|
| 명시적 정책·snapshot 범위·관측 주장과 22컬럼 검증 후 메모리 계산 | 독립 계산·정상값·거부 사유 검산 가능 | 실제 evidence 제공과 운영 cutoff는 별도 계약 대기 |
| 기존 loader에 맞춰 T0 자정 정책 자동 선택 | 연결 쉬움 | #126/SD1 선점이므로 기각 |
| 이벤트가 없는 구간을 complete로 간주 | 0 채우기 쉬움 | 관측 부재와 행동 부재를 혼동하므로 기각 |

## 조사한 것

| 근거 | 적용 |
|---|---|
| 설계 A·B·G 및 missing-policy | 42종 정의·관측 부족·3값 세션·입력 guard와 기간 선택 분리 |
| measurement.schema EVENT_FIELDS/validate_event/requirement | 공개 22컬럼·16이벤트·필수/선택·식별자·금지 열 정본. 측정 파일은 읽기 전용 |
| measurement.timeparse | 직접 fromisoformat 호출 없이 시간 파싱 재사용 |
| 최신 #83·#126 (읽기 전용) | 22컬럼·순매출·cutoff 미결정 유지 |
| 독립 재검토 첨부 a869aa76의 #122–#125 통과 및 R1–R4 | 기존 구현 보존. 새로운 계산에 all_train_rows fit·학습·재봉인 helper를 사용하지 않음 |

## 결정

**구현 전 착수 판정:** F01–F30·F42는 정의가 명확하며 명시적 시험 시간 정책·출처별 고객 관측 근거를 주입해 합성 인수한다. F31–F35는 세션 시작·완료·duration·관련 구간 완전성·필요한 순서가 입력으로 입증된 경우에만 계산 커널을 시험한다. F36–F37은 SD4/학습, F38–F40은 SD5/SD8/가입일 원천, F41은 SD3의 최초 구매부터 평생 근거 대기다. 실제 입력 인수는 모두 미실행이다.

제품 파일은 d1_feature_inputs.py(검증·정책·관측), d1_calculate.py(31종 계산·품질·출력), d1_session_kernels.py(5종 명시적 사실 집계)로 나눈다. 표준 라이브러리만 쓰며 기존 hash primitive를 재사용한다. 시험 파일은 test_feature_d1_calculation.py 및 test_feature_d1_session_kernels.py로 두고 소유 등록을 리드에게 인계한다.

시간 정책에는 비교 연산자·실제 boundary·정밀도·H 시작·시험 용도를 필수로 둔다. P1/P2/P3의 알려진 관계를 검증하지만 기본값은 없다. 이번 구현은 synthetic 용도만 수용하며 운영 적용은 #126 결정 후 별도 인수한다. 과거 기간 선택 전에 전체 입력을 guard하고 미래·중복·형식 위반은 transaction을 거부한다.

관측 주장은 source/namespace·고객·이벤트 유형·기간·상태·gaps·입력 의미 hash·제공자/계약을 명시한다. 이것은 제공된 근거의 정합성 검증이며 진실성/실제 complete 생산기가 아니다. 필요한 H 또는 고정 기간이 snapshot 범위 밖이면 INCOMPLETE_WINDOW, 근거 없음/충돌이면 OBSERVATION_UNKNOWN을 보존한다. 고정 60/90/180일 기간과 H는 서로 다른 조회 정의다. 실제 관측 불명은 관측 건수만 감사 값으로 두고 canonical null이다.

### 2026-10-21 #127·#128 구현 정정 근거와 범위

두 이슈의 원문 재현을 실행해 부분 incomplete/unknown/unsupported가 전체 complete에 가려 0으로 수용되고, 혼합·오선언·임의 source도 수용됨을 확인했다. 이는 위 제안의 관측 불명·출처 위반 처리에 어긋나는 구현 결함이다. 설계나 공유 결정의 승인 상태를 바꾸지 않는다.

#127은 요청 창과 겹치는 같은 E·이벤트 유형의 주장을 모두 검사한다. evidence와 gap은 [start,end), 요청 창만 명시적 정책에 따라 끝 포함 여부를 가진다. gap.end==요청.start는 겹치지 않고, gap.start==요청.end는 P1 포함 끝에만 겹친다. 전체 complete가 있어도 겹치는 incomplete/unknown/unsupported·gap은 사유를 남긴다. complete와 다른 상태가 공존하면 OBSERVATION_UNKNOWN, incomplete/gap은 INCOMPLETE_WINDOW, unsupported는 UNSUPPORTED_EVENT_KIND를 함께 보존한다. 단일 전체 기간 근거가 없으면 부분 complete를 union하지 않는다. incomplete 주장의 범위 자체가 겹치면, 명시한 gap이 요청 밖이어도 기존의 보수적 불완전 판정을 유지한다. 다른 E/유형/기간 밖 주장을 값 판정에 섞지 않으며 입력 identity 불일치는 계속 거부한다.

#128은 측정의 event_source() 하나를 재사용해 선언 source를 simulator/commerce로 제한하고 이벤트별 파생 출처와 대조한다. 하나라도 다르면 전체 입력을 거부한다. 합성은 TimePolicy.purpose 및 근거/fixture의 용도이고 source 예외가 아니다. 메타 둘 다 null이면 commerce, 한 필드만 있어도 현재 공개 함수가 simulator로 판별하는 의미를 그대로 따른다. 두 필드 동시 존재를 새 필수 조건으로 만들지 않는다. 이벤트 0건은 출처를 입증하지 않지만 허용 출처의 명부 행은 보존하고 complete를 자동 추론하지 않는다.

구현 전에 기록한 수정 범위는 d1_feature_inputs.py·test_feature_d1_calculation.py와 이 DR/Dictionary다. 출처 검증으로 기존 시험의 synthetic/s1/s2/other 선언이 무효가 되므로, 메타를 몰래 채우는 helper 대신 계약상 commerce 기본값과 명시적 simulator 메타를 사용한다. 관련 세션 시험도 E의 출처 문자열만 정규화하고 시작/종료·duration 의미나 커널은 바꾸지 않는다. 계산식·hash 규약·기존 로더·공유 계약은 변경하지 않는다.

정정 검증은 N12701–07(부분 근거·경계·분모·identity), N12801–04(혼합/오선언·부분 메타·E 분리·빈 명부)로 추적한다. 수정 전 잘못된 수용과 수정 후 양 환경 결과, 정상 31종 보존, 소유 미등록 및 잔여 범위는 plans/D1-feature-calculation-fixes-127-128-review-20261021.md와 별도 verification 로그에 기록한다. 이는 로컬 수정·회귀 증거이며 독립 검토·실제 입력 인수나 공유 결정 승인 기록이 아니다.

구매는 고유 order_id다. 다른 event_id로 같은 주문이 재등장하면 동일 고객·시각·금액인지 확인해 고유 주문으로 집계하고 감사 건수를 남긴다. 상충하면 거부하며 다른 주문의 동시 구매는 별개 주문·0 간격으로 보존한다. coupon_use 금액은 구매 합계에 더하거나 다시 차감하지 않는다. CV는 간격 2개 이상·모집단 표준편차다. 자연 로그 entropy, Float64 평균/비율을 사용한다. F28/F42는 보완 관계로 기록한다.

출력은 E·index_date·버전·정책·입력/근거 식별자와 canonical·품질을 분리한다. X 선택에는 F-ID allowlist만 허용한다. 라벨·적격성·배정·절대 날짜는 X가 아니다. 명부가 없으면 observed_only라고 표시하며 명부 전용 고객을 삭제하지 않는다.

## 기각한 안과 기각 사유

| 안 | 사유 |
|---|---|
| 공개 product_view의 필수 category 누락을 주문 교환 파일로 보충 | 필수값 위반을 숨기며 22컬럼 원천 확대 미승인 |
| 가입일·persona·누락을 이용한 자동 모집단 필터 | SD5/SD6/SD7 선점 |
| 무활동 시간·duration 존재로 세션 종료 추정 | SD3의 완료 근거를 대신함 |
| canonical 대치·VIP clip·전체 데이터 fit | 정의·누수 규칙 위반 |
| P1/P2 값을 기존 loader의 자정 필드로 바꿔 연결 | 시간 의미 변경. 해당 연결은 #126으로 보류 |

## 이 결정이 틀렸다면 어떻게 드러나나

독립 계산값(구매 2회·50,000원·10일 주기·9일 recency·0.9 지연)과 다르거나, 미래 입력을 필터해 성공하거나, 관측 불명/분모 0을 0으로 반환하면 실패다. source/namespace·명부 고객·여러 사유·두 창의 경계/간격·순서 불변·세션 unknown 감사 건수도 반례로 검사한다. 이전 #122–#125 시험을 두 환경 회귀에 포함한다.

## 민감도

시간 연산자·정밀도·H·관측 유형 범위가 바뀌면 결과/가용성이 달라질 수 있으므로 재현 정보에 포함한다. P1/P2/P3의 차이는 시험 결과로 기록하고 어느 안의 운영 승인도 추론하지 않는다. 값 0과 null·자료형·정의 버전 차이는 기존 의미 hash로 구분한다.

## 남은 불확실성

SD1–SD8은 미결정이다. SD4=시퀀스 요구 적합성, SD5=가입일 사용을 유지한다. #126, 시퀀스 간격 표현 F6, final_refit 등 기존 검토 범위 밖 항목을 고치지 않는다. 세션 실제 evidence 제공·운영 입력 인수·5종 이상 행동 변화/시퀀스/여정 등 전체 필수 구성은 별도 작업이다. 실행 결과·42종 상태·파일 hash는 새 plans/D1-feature-calculation-implementation-review-20261021.md와 검증 로그에 기록한다.
