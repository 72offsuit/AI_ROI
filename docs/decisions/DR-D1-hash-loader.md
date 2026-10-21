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
