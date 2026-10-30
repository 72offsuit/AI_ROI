# DR-179-independent-read-verification — 선택적 모델과 읽기 검증 분리

> 이 문서의 N2 미해결·실제 학습 미실행 기록은 eb5fb28/cdc9233 당시 상태다. 후속 시스템 구현과 실제 개발 검증은 [DR-179-restored-branch-read](DR-179-restored-branch-read.md) 및 [MC-179-development-evaluation](MC-179-development-evaluation.md)을 따른다. 새 공유 계약 합의를 받은 것은 아니며 독립 재검수는 별도다.

| | |
|---|---|
| 태스크 | #179, PR #251의 대체 읽기 회귀 |
| 작성 | 광진 작업용 Codex · 2026-10-30 |
| 상태 | 사용자 지시에 따른 구현 선택 기록. 검증 결과는 후속 기록 참조 |

## 무엇을 정하는가

필수 읽기 검증·관측 상태 판정을 선택적 이벤트 로더와 모델 함수 등록부에서 분리한다. N2의 정확한 history 머리 연결 조건은 바꾸지 않는다.

## 정하지 않으면 무엇이 막히나

src.decision.data가 없으면 공개 events() 대체 읽기에 도달하기 전에 verify_event_run 조회가 실패한다. 관측 상태 판정도 선택적 Feature 모듈에 묶여 S0의 측정 경로까지 중단된다.

## 선택지

| 안 | 내용 | 장점 | 단점 |
|---|---|---|---|
| A | 필수 시스템 계약 클라이언트 src/decision/observation_contract.py를 직접 호출하고 기존 경로는 재노출 | 검증 한 벌, 모델·로더 없음과 독립, 공개 인터페이스 보존 | 새 필수 기반 모듈이 생김 |
| B | src/orchestration 아래로 검증을 옮기고 decision이 역참조 | 러너에서 쉽게 호출 | 하위 데이터 계층이 실행 계층을 참조하는 방향이 생김 |
| C | measurement에 새 공통 검증 추가 | 양 팀이 공유 가능 | 공용 계층 변경·양 팀 합의가 필요하며 이번 회귀에 불필요 |
| D | 모델이 없으면 읽기 검증을 생략 | 구현이 짧음 | 근거 없는 라벨·경제값을 승인하므로 금지 |
| E | 러너에 검증을 복제 | 기존 경로 유지 | 같은 규칙이 둘로 갈라져 드리프트 위험 |

## 조사한 것

| 근거 | 확인한 사실 | 적용 범위 |
|---|---|---|
| [#179 공개 계보 결정 요청](https://github.com/72offsuit/AI_ROI/issues/179#issuecomment-6506729012) | N2 계약은 합의 대기, 모델 없는 읽기 회귀는 독립 수정 | 사용자 요청 범위 |
| src/orchestration/AGENTS.md | 공개 API·decision 인터페이스만 호출하는 파트 경계 | 필수 관측 검증의 소유·호출 방향 |
| src/orchestration/run_sprint.py의 NotRun·decision_fn·StageLog.stage | 선행 조건·선택적 모듈이 없으면 not_run, 그 밖의 실행 예외는 failed | 모델 선택과 독립적인 검증 및 오류 분류 |
| src/decision/data.py | 파일·내용·원시 행 수·부모·거부 수 검증이 pandas 로더 모듈에 함께 있음 | 규칙을 옮기고 중복하지 않음 |
| src/decision/features/sprint_table.py | 관측 상태 판정과 KST 기준점 정규화가 Feature 모듈에 있음 | 로직·시간 정밀도를 보존해 분리 |
| tests/test_orchestration_sprint.py | 기존 모듈 부재 시험은 읽기·RCT·S0 경로를 보장하려 함 | 모델 불가로 검증 자체를 끄지 않음 |
| docs/simulator_api.md | events는 활성 세계의 계보를 읽으며 중간 예외가 나면 읽기 실패 | 일부 스트림으로 성공하지 않음 |

외부 새 알고리즘을 도입하지 않는 의존성 분리다. 저장소 구현·공개 계약을 직접 대조했으며 외부 성능 근거를 만들지 않는다.

## 결정

A를 적용한다. observation_contract는 선택적 ML 모듈이 아닌 필수 관측 계약 클라이언트다. measurement의 공개 자료형·실행 기록만 사용하며 시뮬레이터 API·모델 모듈을 import하지 않는다. pandas는 기존 파일 파싱·시각 판정 함수 안에서 지연 import한다. 모듈 import 자체에는 pandas가 필요하지 않다. 모델 없음과 패키지 미설치는 다르며, DataFrame 기반 전체 파이프라인의 기존 의존성은 유지한다.

read_event_part·verify_event_run·기준점 정규화·outcome_observation_status를 한 곳으로 옮긴다. CSV·JSONL·gzip·Parquet 파싱과 원시 행 수 판정의 기존 동작을 바꾸지 않는다. decision.data와 Feature 모듈은 기존 이름을 재노출해 호출자를 보존한다. 러너는 검증·관측 상태를 필수 모듈에서 직접 호출하고 load_events·학습 함수만 선택 등록부에 둔다.

파일 검증 실패 뒤 API로 바꿔 성공시키지 않는다. 로더 부재일 때만 기존 공개 events 경로를 사용하되 같은 필수 검증을 수행한다. 실제 분기 parent=None이면 N2 때문에 여전히 not_run일 수 있다. 그 결과를 이 회귀의 미수정 또는 계약 승인과 혼동하지 않는다.

**근거:** 모델이 없어도 읽기 검증은 필수이고 검증 규칙은 한 벌이어야 한다. 새로운 공용 계약·측정 계산·Feature 정의를 만들 필요가 없다.

## 기각한 안과 기각 사유

B는 계층 역참조를 피하고, C는 공용 변경을 피하기 위해 택하지 않는다. D는 검증 우회라 금지한다. E는 판정 규칙 중복 때문에 택하지 않는다. 공개 스트림의 유효성을 근거 없이 가정하는 새 영수증 형식도 이번에 만들지 않는다.

## 이 결정이 틀렸다면 어떻게 드러나나

모델 모듈을 전부 사용할 수 없게 한 시험에서 검증이 모델을 import하거나, 검증이 생략되거나, 손상 파일·잘못된 부모를 정상으로 승인한다. 스트림 중간 예외에서 일부 행을 성공으로 반환하거나 이력이 중복 결합된다. 기존/신규 인터페이스가 다른 판정을 반환하거나 시각 정밀도·파서가 바뀐다.

## 민감도

로더 있음/없음, 완전·빈·손상 파일, 정상·잘못된 부모, 중간 스트림 예외, 같은 실행·다른 실행, 모델 함수 전부 부재, KST/UTC·경계 시각을 대조한다. 같은 검증 함수를 사용한다는 객체·import 경계 시험과 공개 API의 실제 초기 읽기 경로를 확인한다.

## 남은 불확실성

N2의 None 부모 공개 계약은 합의 대기다. 실제 분기 경제값이 정상화된다고 선언하지 않는다. 실제 개발 데이터 성능·동점률·Final Holdout은 이 변경의 검증 대상이 아니다. 새 필수 모듈도 설치되지 않은 손상 배포는 기존 모델 부재와 다른 오류이며 정상으로 처리하지 않는다.

## 독립 검토 NB1~NB4의 후속 선택 (2026-10-30)

[검토 후속 기록](https://github.com/72offsuit/AI_ROI/issues/179#issuecomment-6507792065)을 근거로 사용자 승인 범위의 보완을 진행한다. N2 합의는 아직 없으므로 부모 연결 조건은 유지한다.

- NB1: 공개 계약 docs/simulator_api.md의 SimulatorError(Exception) 하위 OutputRootError·SinkFormatError가 스트림 중간에 발생하면, 받은 일부 행은 사용하지 않고 기존 StageLog의 failed 분류를 유지한다. 읽기를 시도하다 공개 API 검증이 실패한 경우라는 의미다. 이를 무조건 not_run으로 바꾸는 대안은 이번에 선택하지 않는다. 기존 OSError/ValueError 처리는 유지한다. 시험 대역은 공개 문서의 예외 상속만 구현하며 실제 시뮬레이터 내부·MRO 검증을 주장하지 않는다.
- NB2: 필수 패키지 ImportError는 선행 조건 부족이므로 러너의 _pd 및 관측 상태 호출 경계에서 NotRun으로 변환한다. 빈 실행도 이 분류를 따른다. 관측 계약 모듈 자체는 orchestration에 의존하지 않고 기존 ImportError를 전파한다. 러너는 같은 판정 함수를 직접 위임 호출하며 계산을 복제하지 않는다. 모든 예외를 잡는 대안은 실제 계산 오류까지 숨기므로 기각한다. ValueError·RuntimeError 등은 원래의 failed 분류를 유지한다.
- NB3: 별도 프로세스에서 모델·로더 10종과 sklearn·torch·shap을 import 단계부터 차단한다. 시뮬레이터 import 한 줄만 제거한 시스템 러너와 공개 API 모양의 대역으로 정상 본선·정확한 부모·이력 중복·잘못된 부모·손상/미주장 파일·중간 오류를 확인한다. 단순 decision_fn 패치와 달리 import 시도·적재도 보고한다.
- NB4: not_run의 근거는 AGENTS가 아니라 실제 NotRun·decision_fn·StageLog 구현으로 교정했다.

반증 조건은 필수 패키지 부재가 failed/ok가 되는 것, 중간 오류에서 일부 프레임이 성공으로 남는 것, 일반 실행 오류가 not_run으로 숨겨지는 것, 선택적 모델 적재 또는 N2 부모 판정 변화다. 새 반례와 기존 회귀를 실행한 뒤 결과를 별도로 기록한다.

## 최초 분리 구현·검증 기록 (2026-10-30, eb5fb28)

- 새 전용 시험 7건은 설치 환경에서 PASS7 / FAIL0 / ERROR0 / SKIP0이다. 선택적 모델 함수 전부 부재, 정상 부모의 대체 읽기, 이력 중복 방지, 잘못된 부모·손상 파일·스트림 중간 오류를 확인한다. ML 패키지와 모델 import를 막은 별도 프로세스에서도 필수 모듈 import와 빈 EventSink 실행 검증이 성공한다.
- 기존 관련 시험과 경계 검사를 묶은 11모듈 하네스는 198수집 / PASS193 / FAIL0 / ERROR0 / SKIP5다. Torch 미설치2건과 숨김 상태 사용3건은 실행하지 않았다. 금지 모듈 import 시도·적재0이다. 전체 discover 또는 전체 격리 검사 통과를 뜻하지 않는다.
- 같은 Python3.12 무의존 환경은 198수집 / PASS84 / FAIL0 / ERROR0 / SKIP114다. 패키지 없는 DataFrame 연결을 통과로 세지 않는다.
- 파서·시각 정규화·실행 검증·관측 판정 4함수의 AST를 직전 커밋과 대조했다. 문서·반환 주석·pandas 지연 import·이름 변경을 제외한 계산과 분기 로직이 일치한다. 기존 40건 관련 시험도 통과했다.
- 공개 API만 사용하는 기존 모델 부재 연결 시험에서 read_events_t1/t2, RCT, snapshot, S0 실행은 ok다. 선택적 ML 단계는 사유와 함께 not_run이다. 같은 시험의 분기 경제값 정상 기대는 N2의 HISTORY_PARENT_UNRESOLVED로 여전히 실패한다. 검사를 완화하거나 실패를 통과로 세지 않는다.
- 공개 API 기반 오케스트레이션 모듈 전체는 59건 실행 / failure7 / error14 / skip0이다. 부모 연결 차단 뒤의 경제값·시간 평가·키 기대 실패가 남는다. 서브테스트가 있으므로 PASS 수를 단순 차감하지 않는다. 실제 모델을 학습한 전체 E2E는 아니다.
- 처음 전용 시험에서 fixture ID가 UUID 계약에 맞지 않아 FAIL1이 발생했다. fixture를 수정한 뒤 7건 통과했고 초기 로그를 보존한다. 전체 오케스트레이션 시험에서는 sys.modules 가짜 주입 중 지연 Parquet 등록의 캐시가 제거돼 ArrowKeyError가 났다. 가짜 주입 전에 공개 DataFrame.to_parquet를 메모리에서 호출하도록 시험 준비만 보완한 뒤 이 오류는 사라지고, 모델 부재 시험은 N2 경제값 차단까지 진행했다. 제품 파서의 오류를 무시하지 않았다.
- 재현 명령은 python3 -m unittest tests.test_orchestration_observation_contract tests.test_feature_sprint_table -v와 python3 -m unittest tests.test_orchestration_sprint -v다. 경계 제한 하네스·환경·초기/최종 로그는 plans/issue179_independent_read_20261030_v06/ 검토 패키지에 보존한다. plans는 로컬 참고 자료이며 이 결정 기록과 제품·시험 코드는 별도 추적한다.

## NB 보완 이후 검증과 N2 범위 구분

- 전용 시험은 11건으로 늘었다. 실제 import 차단 별도 프로세스에서 정상 본선·정확한 부모의 분기·전량 읽기·실패 분류를 확인한다. 모델/로더 10모듈의 등록 함수 26개는 사용할 수 없고, 적재된 decision 모듈은 config와 observation_contract뿐이다. 이 시험은 공개 계약 모양의 대역과 측정 EventSink를 사용한다. 실제 시뮬레이터 모델 평가가 아니다.
- 최초 추가 반례에서 session_start의 page_type이 빠진 fixture 실패를 바로잡았다. 이후 제품 수정 전에는 pandas 부재 시 빈 실행 읽기와 관측 판정이 failed인 두 반례가 남았고, 러너 경계 보완 후 not_run으로 바뀌었다. 초기 실패 로그를 보존한다.
- Python3.12.13 설치 환경의 전용 시험·기존 Feature 시험은 51건 모두 통과했다. 경계 제한 11모듈 검사는 202수집 / PASS197 / FAIL0 / ERROR0 / SKIP5다. Torch 미설치2건·숨김 상태 사용3건을 통과에 포함하지 않는다. 금지 모듈 import 시도·적재는 0이다.
- 같은 버전 무의존 환경은 202수집 / PASS84 / FAIL0 / ERROR0 / SKIP118이다. 새 패키지 부재 시험도 러너의 기존 PyYAML 선행 조건이 없으면 미실행으로 표시한다. PyYAML 누락까지 pandas 분류의 성공으로 세지 않는다.
- observation_contract의 검증·판정 코드는 이번 NB 보완에서 변경하지 않았다. N2 부모 조건을 유지했으므로 이전 전체 오케스트레이션의 N2 실패를 해결했다고 주장하지 않는다. 이 보완 후 독립 검수자의 새 검토와 실제 모델 학습은 아직 실시하지 않았다.

**N2는 모든 작업의 선행 합의가 아니다.** [인성의 기존 R1 결정](https://github.com/72offsuit/AI_ROI/issues/179#issuecomment-6494889527)은 새 공통 계약 없이 RunSummary·측정 실행 기록을 사용하라고 정했다. 공개 simulator_api.md의 events는 활성 세계의 분기 이전 이력을 포함하고 파일 바이트·건수를 검증하며, 중간 예외가 나면 받은 전량을 폐기하도록 규정한다. 이 근거를 이용하는 시스템 내부 구현은 조사·설계할 수 있다. 새 공용 필드나 측정 계층 의미를 요구할 때 양 팀 합의가 필요하다.

다만 공개 스트림의 정상 종료만으로 호출자가 넘긴 임의 history·run_id와 현재 활성 세계가 같다는 증명이 생기지는 않는다. snapshot/restore/advance의 호출 연결, 해당 RunSummary, 재검증된 본선·분기 기록 및 전량 읽기를 어떻게 결속할지 반례로 확인해야 한다. 부모 None을 무조건 정상으로 바꾸거나, 파일 검증 실패를 API 경로로 우회하지 않는다. 이 설계 검토는 아직 완료되지 않았으며 현재 코드의 N2 차단 조건은 유지한다. "새 팀 합의가 반드시 있어야 모든 후속 작업을 시작한다"와 "현재 N2가 해결됐다" 모두 이번 기록의 결론이 아니다.
