# DR-D1-hash-loader — D1 1차 의미 hash와 명시적 묶음 검증

| 항목 | 내용 |
|---|---|
| 태스크 | D1 · #83 |
| 작성 | Codex · 광진(kwung0206) 요청 · 2026-10-20 |
| 상태 | 제안 |
| 구현 승인 | hash·직렬화·정확한 연결 로더·합성 검증만. 공유 결정·운영 게시·학습은 제외 |
| 기준 | D1 v0.2.2, SHA-256 7d18bad5be2edb727b2cca2a38c9418fdb85a3a50fa7e9589d7705356fa97d81 |
| 브랜치 기준 | main fa698d2f649cb1197cb3d6bba00b097197b2d0df → feat/d1-hash-loader |

## 무엇을 정하는가

승인 설계 D·E.1–E.8과 부록 A를 구현한다. 논리 값·계산 의미와 정확한 파일/계보를 분리하고, 명시적으로 선택한 검토용 묶음만 검증한다. 실제 Feature 계산이나 모델 실행은 하지 않는다.

## 정하지 않으면 무엇이 막히나

재게시 메타데이터가 학습 결과의 의미 hash에 간접 유입되거나, 의미값이 같다는 이유로 잘못된 정확한 부모·split·객체가 수용될 수 있다.

## 선택지

| 안 | 장점 | 한계 |
|---|---|---|
| 표준 라이브러리 TLV + 명시적 의미 투영 + Parquet 검증 | 의존성·타입·정확한 연결을 분리해 시험 가능 | Parquet 연결에는 기존 pyarrow 필요 |
| 전 JSON 바이트를 의미 hash로 사용 | 간단함 | 발행 시각·배치의 간접 의존성 때문에 기각 |
| 객체 상태를 추출해 수학적 동등성 판정 | 다른 직렬화 간 동등성 가능 | 승인 범위를 넘고 범용 상태 추출 근거가 없어 기각 |

## 조사한 것

| 근거 | 적용 |
|---|---|
| plans/D1-design-v0.2.2-review-20261020.md 전체 1,316행 및 동일 hash 재확인 | TLV·허용 투영·객체 동일성·정확한 로더·V08/V10 기준 |
| README·AGENTS·TEAM_SETUP·DECISION_RECORDS·Git 규약·파트 지침 | 시스템 경계·L1 Git 제한·소유 등록 인계 |
| #83의 최신 본문·댓글 | 22컬럼 원천 및 전체 Feature 완료는 이번 부분 구현과 분리 |
| src/measurement/timeparse.py | 기존 파서를 재사용. 직접 datetime.fromisoformat 호출 금지 |
| requirements.txt·requirements-dev.txt | 기존 고정 의존성만 프로젝트 전용 Python 3.12 환경에 설치 |

## 결정

아래 신규 D1 전용 파일로 나눈다. 다른 담당자의 파일이나 공유 소유표를 수정하지 않는다.

| 파일 | 설계 | 시험 |
|---|---|---|
| src/decision/features/d1_serialization.py | E.1 | tests/test_feature_d1_serialization.py |
| src/decision/features/d1_semantics.py | E.2–E.6·E.8 | tests/test_feature_d1_semantics.py |
| src/decision/features/d1_loader.py | E.7·F의 읽기 제약 | tests/test_feature_d1_loader.py |
| tests/test_feature_d1_fixtures.py | 실제 Parquet·메타데이터·불변 합성 객체 바이트 | 다른 세 테스트에서만 사용. 모델 학습 아님 |

**근거:** 의미 hash는 d1-semantic/2-proposed TLV envelope를 사용한다. Float32/Float64는 구분하며 UTC 순간은 정수 microseconds다. 입력 문자의 소수부가 6자리를 넘으면 기존 파서가 정밀도를 축소하기 전에 거부한다.

묶음 파일은 features/quality/sequence Parquet와 UTF-8 JSON 메타데이터다. JSON으로 Parquet를 대체하지 않는다. D1 내부 검토용 manifest의 contract는 d1-features/0.2.2-proposed, descriptor는 d1-view-descriptor/1-proposed다. split·schema·policy·객체 형식의 기대 버전/의미 hash는 호출자가 명시한다. 합성 fixture의 버전과 정책은 시험 조건이며 공유 계약이나 SD 결정을 확정하지 않는다.

스키마의 실제 자료형에 따라 값에 TLV 타입을 부여한다. 의미 집합은 canonical key로 정렬하고 중복을 거부하며, 토큰·Feature·벡터·전처리 단계의 순서는 유지한다. generated_at·경로·물리 부모 hash는 의미 투영에서 제외한다. opaque 객체 바이트 hash와 고정 fit 사실은 설계의 보수적 동일성대로 포함한다.

로더는 외부 Expected 입력으로 정확한 최종 manifest·부모·split·descriptor·객체/메타데이터 hash와 의미 context를 고정한다. 실제 파일·배정·Train 입력에서 다시 검산한다. 동결 객체를 실행하거나 역직렬화하지 않는다. 중간 fit 입력이 필요한 역할은 명시적인 Parquet 입력과 upstream 연결을 검증한다. CURRENT 탐색·자동 대체·부분 결과 반환은 구현하지 않는다.

첫 연결은 비감독 encoder → cluster와 명시적 미학습 상태를 지원한다. encoder의 fit 입력은 실제 학습 부모의 선택 Train 행과 대조한다. cluster의 중간 입력은 정확한 파일·Train 범위·선행 encoder로 고정하며 자신의 F37 결과를 입력으로 허용하지 않는다. encoder가 그 중간 값을 실제로 계산했는지 증명하는 실행 재현은 모델 실행을 승인하지 않은 이번 범위 밖이다. 감독 변환의 target 계약은 지원을 추정하지 않고 명시적으로 거부한다.

논리 VectorFloat32[d]의 물리 저장은 Parquet Float32 list이며 매 non-null 벡터의 차원을 검사한다. pyarrow 25.0.1에서 null fixed-size-list Parquet round trip이 ArrowInvalid를 발생시켜 이 저장 표현을 택했다. null을 0벡터로 바꾸지 않는다. claim_indices는 canonical 관측 주장 목록의 위치이며 파일 ID를 의미 입력으로 쓰지 않는다. 행 키는 KEY 필드의 TLV map 바이트순이다. fit scope의 실제 K/E는 명시적 선택 규칙과 실제 nonempty 시퀀스에 의해 해소한다.

검토용 파일 필드의 구체적 형식은 test_feature_d1_fixtures의 생성 예시로 재현할 수 있다. 공개 계약 확장이 아니며 합성 묶음의 3개 Feature(F02·F36·F37)만으로 전체 Feature 인수를 주장하지 않는다. 로더는 호출 시 읽은 각 파일의 검증된 바이트를 캐시하며 파일 전체 묶음의 OS snapshot·동시 writer·전원 장애 내구성을 보장하지 않는다.

기존 C2 팀 경계상 제품·테스트는 시스템 영역이다. W5 소유표의 새 테스트 4개 등록은 리드에게 인계한다. 표를 수정하거나 소유 검사 통과를 주장하지 않는다.

### 2026-10-21 · #122–#125 결함 수정

독립 검토 원문과 GitHub #122–#126의 최신 본문·상태·댓글을 읽기 전용으로 대조했다. 수정 전 제품 파일 hash는 검토 버전과 같다. 다음 변경은 #122–#125의 로컬 결함 수정이며, TLV/hash 규약·정상 입력 의미 식별자·공유 결정 상태를 바꾸지 않는다.

| 이슈 | 원인과 수정 | 반증·회귀 |
|---|---|---|
| #122 | fixture의 pyarrow 최상위 import 제거. Parquet 시험만 `미설치` 사유로 guard하고 순수 직렬화·scope 시험은 무의존 실행 | 수정 전 3모듈 import ERROR 재현. 설치/무의존 두 환경의 전체 수집·회귀를 분리 기록 |
| #123 | 학습 raw의 실제 멤버십을 확인하기 전에 교집합으로 Train을 줄임. 선언 Train 존재를 먼저 검사하고 선택 scope와 실제 fit 입력을 각각 대조 | Train={a,c}, Test={b}, 변환 B={a,b,c}, 학습 A′={a,b}, fit={a}의 전체 재봉인 반례. 정상 3고객·완전 관측 빈 Train의 nonempty 선택·별도 A/B 추적 유지 |
| #124 | upstream이 있으면 원시 보존 영역 대조 생략. 모든 단계의 원시 Feature·sequence·원시 quality를 선택 Train 부모와 대조 | cluster F02=999·sequence·quality 감사 건수를 각각 재봉인해 의도한 보존 검사에서 거부. F36/F37 파생 영역과 자기 F37 금지 규칙은 분리 |
| #125 | UNKNOWN에 대한 출력/사유 검사 누락. F36/F37은 null·unavailable이며 관측/순서 원인이 필요 | F36만·F37만·둘 다 non-null 및 잘못된 사유를 전체 재봉인. EMPTY_COMPLETE·VALID·미학습 객체 정상/거부 경로 대조 |

UNKNOWN의 원인은 기존 제안 어휘 OBSERVATION_UNKNOWN·AMBIGUOUS_EVENT_ORDER·INCOMPLETE_WINDOW·UNSUPPORTED_EVENT_KIND·CONTRACT_UNRESOLVED 중 하나 이상이다. NO_SEQUENCE_INFORMATION은 완전 관측 빈 시퀀스에 사용하며 UNKNOWN에 혼합하지 않는다. TRANSFORM_NOT_FITTED만으로 UNKNOWN의 원인을 대신할 수 없다. 값을 생성하거나 사유를 자동 보완하지 않고 불일치를 거부한다.

회귀 fixture는 실제 Parquet·관측 주장·split·fit 입력·binding·view·출력 의미 hash와 정확한 pin을 명시적으로 재계산한다. 재봉인 helper는 입력 값·행을 고치지 않으며 context 사실은 유지하고, scope 재선언은 해당 반례에서만 명시한다. T1은 실제 split 요청 불일치, T2는 객체 context 사실, T3는 source/namespace 검사까지 도달하도록 보강했다. T4–T6은 해결을 주장하지 않는다.

이번 기록: plans/D1-hash-loader-fixes-122-125-review-20261021.md 및 plans/D1-hash-loader-fixes-122-125-verification-20261021.log. 이전 보고서·로그는 당시 실행 증거로 보존한다. 기존 파일명과 신규 시험 4개의 소유 등록 인계 경로는 그대로다.

### 2026-10-21 · HL-01–HL-04 / #129–#132 수정 결정과 검증 계획

기준 HEAD는 feat/d1-hash-loader의 5f4d6872862e74d5413060c7b48d8db71ab2163c다. 위 최초 구현 및 #122–#125 실행 기록은 당시 사실로 보존한다. 최신 #83·#122–#132의 본문·댓글과 승인 설계 SHA를 다시 확인했다. 이번에는 로컬 코드·기존 시험·이 기록만 수정하며 커밋·푸시·GitHub 쓰기·학습은 하지 않는다.

| 이슈 | 선택할 입력·출력 규칙 | 대안·기각 사유 | 반증 조건 |
|---|---|---|---|
| #131 HL-03 | 문자열의 숫자 오프셋은 시 00–23, 분 00–59를 공용 parse_datetime 호출 전에 검사. Z와 1–6자리 소수부 및 UTC microseconds 유지 | 파서의 오프셋 정규화에 맡기면 잘못된 분을 다른 순간으로 수용 | +09:60·+01:99 수용, 정상 양/음 오프셋 오판정, 1µs 소실 |
| #132 HL-04 | IEEE 변환으로 얻은 최종 Float32/Float64가 0이면 양의 0 payload로 정규화 | 변환 전 검사만 유지하면 음수 underflow를 놓침. epsilon 절삭은 비영 값 소실 | ±underflow/±0의 TLV·hash 불일치, 최소 subnormal 소실, Parquet 왕복 불일치 |
| #129 HL-01 | relative_gap_ms는 Parquet list(Int64)의 nullable 원소. PAD·첫 실제 위치는 null/false, 후속 실제 위치는 비음수 정수/true | masked 저장 0은 이 경계에서 필요 없고 논리 결손과 실측 동시각 0을 혼동. 별도 변환 파일은 범위 밖 | 첫 유효 간격·PAD 간격·후속 null 수용 또는 정상 동시각 0 거부 |
| #130 HL-02 | ordering/session_completion은 문자열 explicit 또는 아래 닫힌 객체만 지원. 발행 시각을 제거한 동일 문자열 explicit로 투영 | 임의 객체 허용·시각 전부 제거는 미지원 의미를 숨김 | 단순 발행 정보가 raw→view→결과에 전파, 이용 가능성 as_of 변경 누락, 미지원 필드 수용 |

ordering/session_completion의 지원 객체는 필수 rule="explicit", 선택 asserted_at·assessed_at뿐이다. 선택 시각도 instant로 유효성을 검사하지만 의미에서는 제외한다. 두 표현은 기존 문자열 explicit와 같은 의미다. 이 표시는 합성·명시 근거의 기존 제한된 어휘이며 실제 순서·세션 종료를 인증하지 않는다. 다른 문자열·rule·키·중첩 객체·null은 명시적으로 거부한다. 종료시각·마지막 이벤트·ordinal 목록 등의 세부 구조는 승인 자료만으로 닫힌 계약을 확정할 수 없어 이번에 지원하지 않는다. availability_basis의 as_of/rule과 claim의 기간·상태·gaps 등 실제 계산 근거는 기존대로 의미에 남는다. 발행 시각을 계산 기준으로 쓰려면 이 선택 필드에 숨기지 않고 승인된 이용 가능성 계약에 표현해야 한다.

UNKNOWN의 기존 고정 배열 표현과 #125의 null 출력/원인 검사는 보존한다. 원시 생성기의 UNKNOWN은 length·배열 전체가 null인 메모리 표현이므로 기존 고정 배열 로더와의 전체 연결은 여전히 보류다. 정상 원소 null 간격의 소비 경계만 이번에 맞춘다. 토큰 숫자→문자열 변환·Store·모델 학습·실제 입력 인수를 추가하지 않는다.

**표현·버전·호환성:** 승인된 d1-semantic/2-proposed의 TLV tag/domain/IEEE·null 규칙과 기존 독립 literal golden은 유지한다. 이는 새 hash 규약 채택이 아니라 v0.2.2 C·E.1·E.2에 어긋난 구현을 고치는 것이다. bundle/view/descriptor 버전명도 유지한다. 이전 masked-zero 시퀀스·가짜 첫 간격·미지원 근거 구조는 더 이상 수용하지 않으며 자동 변환/과거 hash fallback은 없다. 기존 결함을 가진 산출물은 승인된 논리 표현으로 원천에서 다시 만들고 raw·fit-input·binding·view·결과 hash 및 정확한 파일 pin을 모두 새로 검증해야 한다. 음수 underflow의 잘못된 hash와 발행 메타가 섞인 hash도 재계산 대상이다. 올바른 Float64·표현 가능한 비영 Float32·기존 explicit 근거·독립 primitive golden은 바꾸지 않는다. 향후 지원 의미/필드를 추가하면 별도 계약·의미 버전 검토가 필요하다.

검증은 먼저 네 잘못된 동작과 정상 묶음을 현재 코드에서 재현하고, 독립 literal·관계 기대값·정합 재봉인 공격을 기존 시험 모듈에 보존한다. 공격 묶음 작성 중에만 잘못된 간격을 hash할 수 있는 독립 투영을 사용하고 실제 load 시에는 원래 제품 검증을 복원한다. 외부 Expected 고정 거부와 정확한 부모·파일·객체 pin 검사를 계속 실행한다. 실행 결과는 새 plans 보고서·로그에 기록하며 기존 실행 결과를 덮어쓰지 않는다.

실제 로컬 검증: 새 반례를 추가한 수정 전 시험은 73개에서 FAIL 29건(하위 사례 포함)·ERROR 1건으로 결함을 드러냈다. 최종 hash/로더 74 PASS, 계산·세션·시퀀스·품질 78 PASS, 경계·DR 39 PASS다. CPython 3.12.13의 의존성 환경 전체는 947개 중 944 PASS·3 SKIP, 무의존 환경은 785 PASS·162 SKIP이며 두 환경 모두 FAIL·ERROR 0이다. 소유 검사는 기존 미등록 10건으로 FAIL, Python 3.10은 실행기 부재로 BLOCKED다. 이는 합성 로컬 회귀 결과이며 실제 입력·모델 학습·BATHOS/출하 게이트 통과가 아니다. 상세 명령·사유·파일 hash는 plans/D1-hash-loader-fixes-129-132-review-20261021.md와 D1-hash-loader-fixes-129-132-verification-20261021.log에 보존한다.

**현재 선택 상태:** plans/D1-SD1-SD8-decisions-20261021.md와 D1-Q1-Q5-approved-directions-20261021.md에서 광진의 방향 선택은 완료됐다. 아래 과거 절의 "미결정"은 작성 당시 기록이다. P3·G1 우선·분담 근거·D1 SVD+KMeans/D3 DL·가입일 용도 분리·D2 공통 분할·원시/공식 품질 분리·최고 여정, 고객/시간 분리와 Train 그룹 5-Fold, 개발 d=8/k=8/n_init=10, 종료−시작 duration 방향을 되돌리지 않는다. 공유 시간 계약 #126·제공자 수락·실제 정밀도/완전성·구체 seed·정식 계약 이관은 별도다. 이번 네 결함 외 final_refit/fold_id=null·전체 연결·CURRENT 게시·실제 인수는 보류하며 다른 지적을 함께 해결했다고 하지 않는다.

### 2026-10-21 · #131 추가 F-1–F-3 — 두 시간 진입점의 문자열 검증

현재 작업 트리의 HL 수정 위에 추가한다. #131 최신 본문 전체·댓글(추가 범위 포함), 독립 재검토 원문 및 기존 보고서·로그를 확인했다. 아래 결정은 코드 수정 전에 기록하며 앞선 실행 결과를 이번 추가 수정의 결과로 바꾸지 않는다.

| 대안 | 선택·근거 | 한계/반증 조건 |
|---|---|---|
| 두 함수에 범위 검사·소수부 처리를 각각 복제 | 기각. 이번 F-2처럼 다시 갈라질 수 있음 | 한쪽만 비정상 입력 수용 |
| timestamp 전체를 instant에 위임 | 기각. 기존 datetime의 정확한 타입 검사·UTC 범위 오류 처리가 달라짐 | 기존 datetime/오류 계약 회귀 |
| d1_serialization의 작은 문자열 정규화 함수를 두 진입점에서 재사용 | 선택. 추가 파일 없이 ASCII 형식·구성값·소수부 한 벌을 사용하고 각 함수의 datetime 처리·파서 예외·UTC 처리는 유지 | 파서 호출 전에 범위 위반을 못 막거나 소수부를 절삭하면 실패 |
| 버전별 skip·최소 버전 상향·공용 측정 파서 수정 | 기각. 승인 범위 및 최소 지원 선언을 우회 | 3.10 미실행을 PASS로 표시하거나 공유 코드 변경 |

입력 문자열은 ASCII YYYY-MM-DDTHH:MM:SS, 선택 소수부 1–6자리, 필수 Z 또는 ±HH:MM이다. 시각의 시는 00–23, 분/초는 00–59, 오프셋 시는 00–23·분은 00–59로 파서 호출 전에 검사한다. 소수부는 6자리로 오른쪽 0 채움만 하며 수치를 바꾸지 않는다. 7자리·오프셋 부재·다른 문법은 거부하고 달력 날짜 유효성은 기존 parse_datetime으로 확인한다. datetime.fromisoformat 직접 호출은 추가하지 않는다.

근거: [Python 3.10 공식 datetime.fromisoformat 문서](https://docs.python.org/3.10/library/datetime.html#datetime.datetime.fromisoformat)는 초 소수부를 .fff[fff] 형태로 설명한다. 이는 파서에 6자리를 전달할 근거이며 실제 3.10 실행 증거가 아니다. 현재 timestamp는 이미 6자리 채움을 하지만 오프셋 범위를 검사하지 않고, instant는 오프셋만 검사하고 채움이 없다. 3.14.6에서는 두 함수가 T24:00:00을 다음날로 수용하는 것도 수정 전에 직접 재현했다. P3에서 잘못된 +09:60 이벤트가 cutoff 이전으로 바뀌어 계산되는 반례를 같은 입력으로 재시험한다.

검증 범위는 두 진입점과 EventBatch 이벤트/start, TimePolicy boundary/history_start, ObservationClaim start/end/gaps, OrderClaim.at, 계산·원시 시퀀스 generated_at의 실제 경로다. 독립 epoch microseconds/TLV, 파서에 전달된 정확한 정규화 문자열, 정상 cutoff 직전/경계/이후를 대조한다. 파서 인자 검사는 3.10 런타임 실행을 대신하지 않는다. 기존 #129 null 간격·#130 의미 투영/정확한 pin·#132 Float32 및 #122–#128 회귀는 보존한다. 정상 순간·TLV·의미 hash와 버전은 바꾸지 않는다.

기록 정정은 이전 보고서 끝에 추가 정정 링크를 남기고 새 plans/D1-time-validation-fixes-131-F1-F3-review-20261021.md 및 대응 verification 로그에 모은다. 앞선 “1–6자리 유지”는 3.12 실행 근거였으며 최소 버전 인수 완료가 아니었다. 이전 73개 중간 시험에는 최종 74개 중 생성기/Parquet 채널 대조 1개가 없었다. 정상 fixture의 실제 R/V와 독립 검토 원시 로그의 252 대 251 집계 차이를 별도로 확인하며 과거 원문·로그는 삭제하지 않는다.

SD·Q 선택은 유지한다. #126 공유 시간 계약·final_refit·실제 입력·학습·전체 Store·CURRENT·소유 등록·Python 3.10 실제 실행은 별도 확인 사항이고 이번 수정으로 승인하지 않는다.

추가 수정의 실제 실행: 3.12.13과 3.14.6에서 동일한 재현 입력을 수정 전/후 비교했다. 두 버전의 관련 16개 시험은 수정 전 FAIL 30건(하위 사례 포함), 수정 후 16 PASS다. F-1의 파서 전달 문자열 검사도 포함되며 3.10 실행 결과는 아니다. 최종 3.12 의존성 환경은 hash/로더 79 PASS, 계산·세션·시퀀스·품질 81 PASS, 전체 955개 중 952 PASS·3 SKIP·FAIL/ERROR 0이다. 무의존 3.12 전체는 793 PASS·162 SKIP·FAIL/ERROR 0이다. 무의존 3.14의 D1 7모듈은 100 PASS·60 SKIP·FAIL/ERROR 0이며 전체 저장소 실행으로 확대하지 않는다. 소유 미등록 10건 FAIL과 3.10 BLOCKED는 남는다.

독립 검토 원시 로그 30_probe_full.log(SHA-256 94485896fcb9877d20fbc0e72bdfa18d8c3c41671bddbc0e442ca9a62d690585)를 재집계했다. HL01/02/03/04의 PASS는 52/91/56/52로 합 251이고, 별도 RESIDUAL 1 PASS를 합친 값이 252다. 별도 SIDE-TS 2 PASS·4 FAIL까지 포함한 원시 로그 전체를 252/252 PASS로 표시하지 않는다. 과거 로그 재집계이며 이번 시험 실행 수가 아니다. 현재 정상 fixture의 R=eb256f17f08acbd09e4f257d2cbe397e5f1117a0c5ec2a140df34494d4e82724, V=f0817f8f5c6f4450139469273f5be15446cab42b42e9586cd85d8138bb62f38c는 이번 시간 정규화 추가 수정에서도 유지됨을 실제 로더로 확인했다.

### 2026-10-22 · #133 X-1 — instant의 UTC 범위 오류

착수 HEAD는 0426b95cce098c04651a5712f561eac7d3457582다. 이전 HL·#131 F-1–F-3의 9개 파일은 이 커밋에 포함됐으며, 위 과거 “미커밋” 설명은 작성 당시 기록이다. 현재 #133·#134 본문/댓글과 독립 재검토 X-1/X-2를 대조했다. 수정 전 3.12.13·3.14.6에서 범위 초과 문자열과 aware datetime 각 2개가 instant에서는 OverflowError, timestamp에서는 원인 OverflowError를 가진 D1ContractError가 됨을 확인했다. 입력 자체는 두 경우 모두 거부된다.

| 대안 | 판단·근거 | 반증 조건 |
|---|---|---|
| instant의 UTC 변환 한 호출에서 OverflowError만 D1ContractError로 연결 | 선택. 실제 UTC 범위 초과만 명시적 계약 오류로 보고하고 원인 예외를 유지 | 범위 초과가 OverflowError로 유출되거나 원인 사슬이 사라짐 |
| 전체 함수에서 Exception/ValueError까지 포괄 변환 | 기각. 달력 오류·다른 실제 결함까지 UTC 범위 문제로 숨길 수 있음 | 무효 달력과 UTC 변환 초과가 구분되지 않거나 RuntimeError가 계약 오류로 바뀜 |
| timestamp에 위임하거나 날짜/순간을 유효 범위로 보정 | 기각. 기존 datetime subclass 정책을 바꾸거나 다른 값을 만들어 수용 | 기존 타입 처리 차이·정상 순간·TLV가 달라짐 |

instant의 마지막 astimezone 호출만 try/except OverflowError로 감싸고 `raise D1ContractError("timestamp outside supported UTC range") from exc`로 원인을 잇는다. 문자열 파서·형식·정밀도·datetime 허용 판단은 그대로다. timestamp·측정 파서·공개 계약은 수정하지 않는다. #134 날짜 문자열 입력은 별도 제안/선택 전까지 현행 동작을 유지한다.

반례는 문자열/aware datetime의 하한·상한 UTC 초과, evidence_body의 claim·gap·as_of·발행 시각 경로를 포함한다. 정상 UTC 최솟값/최댓값과 ±23:59 오프셋, 독립 epoch microseconds/TLV, 달력 자체의 오류, 비관련 예외 전파를 대조한다. 기존 정상 fixture R/S/V와 의미 hash·기존 HL 회귀를 유지한다. 이번 수정은 오류 타입과 원인 사슬만 바꾸므로 TLV/hash/계약 버전은 바꾸지 않는다.

실행 기록은 새 plans/D1-utc-range-date-policy-review-20261022.md 및 대응 verification 로그에 남긴다. 기존 보고서·로그·SD/Q 선택은 보존한다. 검증 후 #133 코드·시험·이 기록과 #134 제안 문서를 현재 브랜치의 별도 커밋으로 나누며 plans·사용자 변경은 제외한다. 커밋은 독립 재검토·이슈 종료·출하 승인이 아니고 푸시는 금지다. #126·실제 입력·final_refit·모델·Store·CURRENT·소유 등록·3.10 실제 검증은 별도다.

실제 검증: 3.12.13·3.14.6의 신규 5개 시험은 수정 전 ERROR 12건(하위 사례 포함)으로 UTC 예외 유출을 확인했고 수정 후 5 PASS다. 최종 3.12 의존성 hash/로더 84 PASS, 계산·세션·시퀀스·품질 81 PASS, 전체 960개 중 957 PASS·3 SKIP·FAIL/ERROR 0이다. 무의존 3.12 전체는 798 PASS·162 SKIP·FAIL/ERROR 0, 무의존 3.14 D1 7모듈은 105 PASS·60 SKIP·FAIL/ERROR 0이다. 정상 fixture R/S/V와 세 테이블 의미 hash는 시작 기준과 같다. 소유 검사 미등록 10건 FAIL과 3.10 실행기 부재 BLOCKED는 남는다. calendar_date 소스와 ASCII·아랍·전각·혼합 날짜의 기존 동작은 바꾸지 않았다. #134 제안은 별도 DR-D1-date-input-policy.md에 기록하며 선택 대기다.

### 2026-10-22 · #134 — A안 승인 후 날짜 입력 guard

위 #133 절의 calendar_date 미변경·#134 선택 대기는 당시 기록이다. 이후 광진이 A안을 명시적으로 승인해 날짜 문자열을 ASCII YYYY-MM-DD로 제한한다. 선택·B-1 Unicode DB 의존성·호환성·실행 기록의 정본은 [DR-D1-date-input-policy.md](DR-D1-date-input-policy.md)다. 로컬 입력 정책은 d1-date-input/1-ascii이며 새 manifest 필드를 추가하지 않는다. 정상 date/tag 06·의미 투영이 같으므로 d1-semantic/2-proposed와 정상 R/S/V를 유지하고, 정확한 파일·부모·split·객체 pin은 완화하지 않는다. #133 UTC 범위 처리와 #131 시간 정규화는 변경하지 않는다. 공유 계약 수락·실제 입력 인수·#126·소유 등록·3.10 검증 완료를 뜻하지 않는다.

## 기각한 안과 기각 사유

| 안 | 사유 |
|---|---|
| descriptor/split 파일 hash를 의미 view에 포함 | 생성 시각·압축 변경의 간접 전파 |
| 메타데이터 파일 전체를 객체 의미로 사용 | 정확한 부모·발행 정보가 의미 계열에 유입 |
| 같은 seed·설정으로 객체 동일성 인정 | 동일 바이트와 fit 범위가 입증되지 않음 |
| 선언 hash만 대조 | 실제 파일·키·Train 배정·객체 연결의 반례를 놓침 |
| 최신 디렉터리·CURRENT 자동 선택 | 이번 승인 범위를 넘고 잘못된 부모 대체 가능 |

## 이 결정이 틀렸다면 어떻게 드러나나

V08 재게시 조건에서 의미 hash가 변하거나 null/0·타입이 같게 hash되면 실패다. V10에서 정확한 부모·객체·Train 범위·upstream 불일치가 수용되면 실패다. 테스트는 고정 직렬화 바이트/hash와 독립 반례를 포함한다. 실제 실행 결과는 별도 검토 보고서에 기록하며 미실행을 통과로 쓰지 않는다.

## 민감도

숫자 오차 허용 범위를 도입하지 않는다. 의미 field/domain/타입/순서를 바꾸면 새 의미 버전이 필요하다. 파일 포장 변경은 정확한 파일 hash를 바꾸며 의미 투영만 같으면 값 hash는 유지된다. 객체 재직렬화는 이 불변 조건의 예외이며 새로운 바이트 입력이다.

## 남은 불확실성

SD1–SD8은 그대로 미결정이다. SD4는 시퀀스 요구 적합성, SD5는 가입일 사용이다. 실제 모델·실제 입력·운영 게시·공식 결측률·통계 보정은 미구현/미검증 범위다. 소유 등록과 독립 검토가 남으며 D1 전체 완료나 출하 게이트 통과를 뜻하지 않는다.

#126은 미해결 결정 이슈다. 현재 로더는 정책의 operator/boundary와 별개로 feature_cutoff_time을 index_date 당일 KST 자정에 고정하는 제약이 남아 있다. 이는 승인된 SD1 정책이 아니며 이번에 코드·필드 의미·오류 문구를 변경하거나 P1/P2/P3를 채택하지 않았다. 운영 시간 인수의 제한으로 보고한다. 독립 검토 F6–F10(간격 표현, final_refit 지원, 시간 파싱/3.10, ZoneInfo 환경, primitive/설정 투영 경계)은 이번 수정 범위 밖이며 별도 검토가 남는다.
