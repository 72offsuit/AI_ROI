# DR-D1-w1-evidence-sequence-file — 합성 근거 검증과 원시 시퀀스 파일 어댑터

| 항목 | 내용 |
|---|---|
| 태스크 | D1 · #83 |
| 작성 | Codex · 광진(kwung0206) 요청 · 2026-10-22 Asia/Seoul |
| 상태 | 제안 — 명시적 합성 구현 범위 승인, 운영 인수·공유 채택은 별도 |
| 기준 | feat/d1-hash-loader · e9a71c389cad415f4705b5251354f4a67e0e877c |

## 무엇을 정하는가

W0 I03의 생산·전달·수신 근거를 기존 EventBatch·ObservationClaim·OrderClaim에 연결하는 표준 라이브러리 검증기와 O01 SequenceRow의 독립 Parquet 파일 어댑터를 구현한다. 기존 제품의 계산·정상 hash·0.2.2 로더를 변경하지 않는다. #126·실제 입력 인수·모델 fit·전체 bundle writer/CURRENT는 제외한다.

## 정하지 않으면 무엇이 막히나

근거의 문자열 선언만으로 관측을 complete로 승격하거나 내부 숫자 토큰을 legacy VIEW 같은 문자열로 추정할 수 있다. UNKNOWN의 null 배열을 기존 로더에 맞추어 0/PAD로 채우지 않고 별도 명시 버전의 파일로 보존해야 한다.

## 선택지

| 안 | 장점 | 한계 |
|---|---|---|
| 독립 합성 검증기 + 명시적 시퀀스 파일 버전 | 기존 정책/수정 보존, 정상/거부를 실제 바이트로 검증 | 전체 Store와 운영 인수는 후속 |
| 기존 로더를 관대하게 바꾸기 | 빨리 연결 가능 | #126·버전·UNKNOWN 표현을 섞어 기각 |
| JSON을 Parquet 대체로 게시 | 의존성 없음 | 파일 계약을 대체하므로 기각. 실제 파일은 기존 pyarrow 사용 |

## 조사한 것

W0 패키지·세 Schema·SD/Q 선택, 기존 raw sequence/입력/직렬화/로더·후속 명세를 대조했다. 생산·전달·수신 수락은 이번에 만들지 않는다. current TimePolicy/OrderClaim은 synthetic 전용이다. 현재 원시 UNKNOWN은 length/배열 null이고 legacy loader와 차이가 있다. nullable gap 정정 #129와 시간/날짜 수정 #131/#133/#134는 보존한다. W0 I03의 형식 수용만으로 실제 입력 identity·파일·범위·기간/순서 관계는 증명되지 않는다.

## 결정

| 대상 | 입력 | 출력·책임 |
|---|---|---|
| src/decision/features/d1_evidence.py | I03 synthetic, EventBatch, 명시 TimePolicy/index_date, 호출자가 별도 고정한 FilePin과 공개 artifact bytes | 출처·고객·input·파일·역할·범위 검증. 기존 관측/순서 claim과 계산용 의미 hash. 실제 admission은 항상 BLOCKED |
| src/decision/features/d1_sequence_file.py | 기존 RawSequenceOutput와 검증된 근거 context | 고정 0–16↔문자열 사전 변환, W0 SequenceRow, Parquet bytes/file hash/value hash, 명시 Expected를 요구하는 읽기 |
| tests/test_feature_d1_evidence.py | 정상·누락·출처 혼합·잘못된 물리/의미 pin·부분 전달·순서 반례 | 실패 지점과 독립 정상 대조, 운영 목적 거부 |
| tests/test_feature_d1_sequence_file.py | VALID/EMPTY_COMPLETE/UNKNOWN·진짜0/첫gap null·파일 변조·정확한 dtype | 무의존 순수 변환 실행, Parquet만 미설치 skip, 실제 바이트 round trip |

근거 검증기는 파일시스템을 직접 탐색하지 않고 caller가 제공한 bytes와 외부 expected pin을 대조한다. synthetic JSONL 이벤트와 고객 ID projection을 재구성해 EventBatch input identity를 대조한다. 생산/전달/수신 evidence_record는 해당 record의 provider를 제외한 닫힌 본문을 담는 합성 파일 profile로 고정한다. provider 파일 refs·request ID·물리 포장 등은 계산 의미 hash에서 제외하되 정확한 파일 대조는 유지한다. 단순 합성 fixture를 accepted 운영 근거로 승격하지 않는다.

전체 생산 complete라도 전달/수신 incomplete·unknown이면 부정 관측 claim을 추가하여 기존 #127 판정에 전파한다. 필요한 선택 tie만 실제 이벤트 멤버십/순서를 대조하며 중복·불완전·상충 tie는 UNKNOWN으로 남긴다. 오래된 불필요 tie의 실제 이벤트 존재 검사를 확대하지 않는다. 부분 complete claim의 union으로 완전 관측을 만들지 않는다.

시퀀스 파일은 d1-sequence-file/2-proposed와 d1-sequence-tokens/1을 명시한다. 사전 hash는 W0 고정값을 검산한다. PAD/첫 gap=null·false, 이후 gap은 비음수 Int64·true이고 실제 동시각 0을 보존한다. EMPTY_COMPLETE와 UNKNOWN을 구분하고 명시한 전체 고객 키를 보존한다. 의미 hash는 typed SequenceRow의 논리 투영이며 generated_at·압축·행 순서·물리 evidence refs는 제외한다. input/observation 의미·상태·토큰/간격/사유는 포함한다. 같은 의미라도 reader의 외부 정확한 file pin을 완화하지 않는다.

Parquet는 string 토큰·Bool mask·nullable Int64 list를 실제 dtype으로 확인한다. optional import는 실제 파일 API 안에 둔다. 이 파일의 검증은 전체 raw bundle/학습 view/consumer 인수가 아니다. 합성 byte writer는 요청된 bytes를 반환하며 게시·CURRENT·원자적 교체를 수행하지 않는다. 원시 감사·selected_event_ids 등 전체 자료는 기존 RawSequenceOutput에 그대로 유지하고, 파일은 W0의 명시 SequenceRow 투영이다.

### 구현한 합성 profile의 정밀한 범위

Provider 역할은 생산 commerce→commerce_exporter / simulator→S4, 전달·순서→S1 또는 commerce_exporter, 수신→D9로 제한한다. 이는 이번 synthetic-body-binding profile이며 실제 담당자의 제공 수락이 아니다. evidence_record가 없거나 available_as_of가 없거나 명시 TimePolicy가 허용하는 시점이 아니면 근거를 사용할 수 없다. 해당 생산 관측/순서는 unknown으로 남긴다. available_as_of의 이 검사 역시 합성 profile에만 적용하며 운영 정책을 추가 채택하지 않는다.

새 의미 hash는 기존 d1-semantic/2-proposed TLV의 닫힌 투영이다. observation은 input·명시 policy·생산 entity/event_types/typed UTC period/gaps/state/capability·provider의 역할/계정/상태/input/typed available_as_of/assertion version·전달 범위/upper/state/보존/failure·수신 state/input/provider를 포함한다. order는 필요한 tie의 entity/typed UTC at/정렬된 event_id→Int64 ordinal·input/provider/선택 정책을 포함한다. 배열 중 순서 없는 claim/gap/ordinal은 TLV 순서로 정렬하며 중복 observation은 거부, 중복 tie claim은 UNKNOWN이다.

agreement/evidence 파일 pin·events/roster pin·수신 요청 ID·생산/전달 파일 refs는 새 의미 투영에서 제외한다. 원시 EventBatch identity는 기존의 typed/정렬된 이벤트 값·고객/출처·추출 시작으로 계산되므로 물리 JSONL 순서도 제외된다. 기존 RawSequenceOutput의 재현 hash에는 정확한 ref가 계속 들어가며, adapter는 그 재현 정보를 검증에만 사용하고 새 의미 hash의 입력으로 다시 넣지 않는다. 순서: 외부 exact pin 대조→본문/input 재구성→observation/order 의미→원시 생성 및 정확한 재현 정보 대조→typed SequenceRow/context 의미→Parquet bytes SHA256. 자기참조나 물리 hash의 간접 유입이 없다.

SequenceRow의 값 hash는 typed 행(물리 order_evidence_refs 제외) 및 entity namespace/source/index_date/input·observation/order 의미·명시 policy context를 포함한다. reader는 hash와 별도로 전체 고객 키, dtype/버전, 해당 고객의 필요한 모든 order FilePin의 정확한 집합을 확인한다. 투영 자체는 caller의 기존 원시 계산값을 연결하며 공개 이벤트로부터 토큰 계산을 독립적으로 재실행해 증명하는 로더는 아니다. 호출자는 기존 generator 출력과 별도 고정한 Expected를 사용한다. VerifiedEvidence는 같은 프로세스 안의 반환 context이며 교환 파일이나 제공자 인증서가 아니다.

### 2026-10-22 실제 검증 기록

신규42개: 의존성 환경42 PASS, 무의존32 PASS/10 SKIP(형식 Schema5·Parquet5 미설치). 전체 회귀: 의존성1008 PASS/3 SKIP, 무의존837 PASS/174 SKIP, 각각 총1011·FAIL/ERROR0. 기존 D1 174개는 의존성174 PASS·무의존112 PASS/62 SKIP로 보존됐다. 경계/DR39 PASS. 3.13/3.14 관련 D1 각각144 PASS/72 SKIP, 3.10 실행기는 없어 BLOCKED. 소유검사 FAIL은 기존 미등록10+신규 시험3이며 소유표는 변경하지 않는다. 전체 명령·실제 출력은 plans/D1-W1-evidence-sequence-verification-20261022.log. 이 검증은 합성·문서/파일 범위이며 전체 연결·공식 인수 통과가 아니다.

### 2026-10-22 · #138 N-1: 필수 외부 pin 집합 계약 (a)

위 실행 기록은 당시 결과로 보존한다. 현재 기준은 feat/d1-hash-loader / f8359c7963b5664ab9cb7b3047081f1951034e22와 미추적 W1 파일이다. #138(D1-W1-N1-20261022) 최신 본문·댓글0개를 읽었고 이슈의 원문 stdin을 수정 전에 그대로 실행했다. 모든 상충 근거를 제출하면 UNKNOWN/AMBIGUOUS_EVENT_ORDER였지만, 하나를 생략하고 ordering 선언 hash만 다시 계산하면 VALID와 미검증 fixture/ordering-0.json이 반환됐다. #127의 부정 관측, #129의 null 간격, #130의 발행 정보 의미 투영과 근본 원인이 다르다.

사용자가 선택한 **(a)**: expected_files는 이번 호출에서 반드시 검증해야 할 전체 FilePin을 제출 envelope와 독립적으로 고정한 path→FilePin 집합이다. 임의 파일 재고가 아니다. 기존 각 pin의 외부 내용·실제 bytes/크기/media type·역할/input·본문 검증을 보존하고, 성공 반환 직전에 검증한 path 집합과 expected_files의 path 집합이 정확히 일치하도록 요구한다. 누락은 required external FilePins not verified와 누락 경로를 담은 D1ContractError이며 VerifiedEvidence를 반환하지 않는다. 같은 pin의 반복 참조는 한 경로로 검산되므로 참조 횟수로 거부하지 않는다. artifacts는 별도 재고이며 무관한 bytes가 있어도 허용한다. 두 입력과 envelope를 변경하거나 Expected를 envelope에 맞춰 필터링하지 않는다.

선택 근거: 읽기 허용 범위의 실제 호출 검색에서 제품 호출처는 아직 없고 합성 fixture가 호출한다. fixture의 seal은 이전 준비의 pin을 누적하므로 정상 새 요청 준비에서 필수 집합을 새로 구성해야 한다. 이는 제출 뒤 검증기에서 Expected를 다시 만드는 동작과 구별한다. 정상 준비 단계에서 새 요청을 seal할 때 expected는 새 집합, artifacts는 재고로 유지한다. 생산 근거 없음·생산 claim 축소·prefix 재게시도 새 요청의 필수 집합으로 준비한다. 공격 시험은 준비가 끝난 독립 Expected를 deepcopy로 동결한 뒤 envelope와 선언 hash만 바꾸며 다시 seal하지 않는다. 처음부터 고정하지 않은 provider 근거의 UNKNOWN은 유지한다.

기각한 대안: (b) 수신 본문에 ordering refs를 추가하는 방식은 W0/공유 계약 변경이 필요하고, (c) 외부 의미 pin API 추가는 이번 승인 범위보다 넓다. 모든 artifacts 소비 강제, 제출에 따른 Expected 축소, 동일 순서 중복 claim의 VALID 완화도 기각한다. 새 의미 hash 규약·버전·출력 형식을 만들지 않고 현재 (a) 계약 검증만 보강한다.

반증 조건: 두 삭제 방향의 재봉인 공격 수용, 미참조 필수 pin 수용, 누락 시 후속 raw 생성 진행, 정상 단일 full 근거의 값/hash 변경, 중복·부분·부재의 UNKNOWN 변경, 반복 참조·무관 재고·새 prefix 재게시의 오거부 또는 입력 객체 변경이면 실패다. 기존 source/bytes/input 거부, 정확한 파일 연결·의미 hash 불변성도 보존해야 한다. 제품 수정 전에 이 절을 기록하며 실행 후 별도 결과를 추가한다. #126·#135–#137, SD/Q 선택·실제 제공자 수락·운영 admission·전체 loader/CURRENT·학습은 이번 수정으로 해제하지 않는다.

### #138 (a) 실제 검증·잔여 한계

N-1 전용 회귀9개는 의존성/무의존 Python3.12에서 각각9 PASS다. W0/W1 관련51개는 의존성51 PASS, 무의존41 PASS/10 SKIP(Schema5·Parquet5 미설치). 기존 D1 174개는 의존성174 PASS, 무의존112 PASS/62 SKIP다. 전체 회귀는 의존성1017 PASS/3 SKIP, 무의존846 PASS/174 SKIP이며 각각총1020·FAIL/ERROR0, 경계/DR39 PASS다. 원문 stdin은 두 환경에서 honest UNKNOWN을 유지하고 omitted가 required external FilePins not verified: fixture/ordering-0.json의 D1ContractError로 종료(exit1)했다. 이것은 반례의 의도된 단독 예외이며 unittest ERROR가 아니다. 정상 single-full/3상태 입력·관측·순서·시퀀스 의미 hash와 토큰·간격은 수정 전 snapshot과 동일하다. 소유 FAIL13은 기존 미등록 그대로이며 신규 파일 등록 항목을 추가하지 않았다. Python3.10은 실행기가 없어 BLOCKED다.

별도 관찰 FOLLOWUP-138-ROLE-REFERENCE: ordering에서 뺀 근거 FilePin을 authorization.approval_records에 옮기고 ordering 선언 hash만 재계산하면 현재 profile은 모든 pin을 검증하지만 UNKNOWN→VALID가 된다. 외부 Expected·artifacts는 그대로이며 미검증 pin은0이다. 즉 (a)의 집합 검사는 성립하나 파일이 올바른 주장 역할로 제출됐다는 보장까지는 없다. 이 경로는 승인된 단순 생략 반례와 다르며 역할별 근거 결합/신뢰 경계의 후속 검토 대상이다. (b)/(c) 전환이나 승인 파일 본문 계약 확대는 허용되지 않아 제품을 추가 수정하지 않았다. OPEN/CLOSED98개 제목·본문의 approval_records/verify_evidence/expected_files 검색에서 관련 후보는 #138뿐이고 관련 #135–#137은 다른 공동 계약이다. 모든98개 댓글까지 조사했다고 주장하지 않는다. #138에 보강할지 별도 이슈로 등록할지는 보고만 하며 GitHub 쓰기를 하지 않는다. 이 한계가 남아 있으므로 #138의 모든 근거 누락 경로가 닫혔다고 판정하지 않는다.

이번 실행 로그는 plans/D1-evidence-required-pins-138-verification-20261022.log, 수정 전 snapshot 대비 diff와 새 보고서는 같은 접두어의 산출물이다. 과거 W1 로그/보고서는 바꾸지 않는다. (a)의 로컬 구현·명시 반례 회귀를 완료했으며 전체 인수·이슈 종료는 별도다.

### 2026-10-22 · #138 R-1·T-1: 역할을 고정한 내부 Expected

착수 HEAD/origin은 b0bbca73bab09a5cd03f74ceb6f1fb6441adf16d이며 W1 파일은 추적 상태다. 위 f8359c7/미추적·실행 수치는 당시 기록으로 보존한다. 최신 #138 추가 절(2026-10-22T02:59:13Z, 댓글0)의 사용자 승인 방향과 독립 검토 원문을 대조했다. 수정 전 R-1의5슬롯×2삭제방향은 모두 VALID, 단일 근거 null 이동5건은 UNKNOWN으로 수용됐다. 같은 위협 모델의 잔여 경로이며 새 회귀가 아니다. T-1의 의도적 무예외 검증기 실험은1방향만 호출·FAIL1·ERROR1(AttributeError)이었다. 아래 계약을 제품 수정 전에 기록한다.

**승인한 내부 API:** expected_files는 정확한 dict이며 비어 있지 않은 path → {file_pin: FilePin, required_roles: [역할 문자열,...]}다. entry는 두 필드만 허용한다. key는 정확한 비어 있지 않은 str이고 안전한 file_pin.path와 같아야 한다. FilePin은 기존 닫힌4필드와 정확한 SHA256/media type/비음수 Int64 bytes 규칙을 유지한다. required_roles는 정확한 비어 있지 않은 list[str]이며 중복·미지 역할·잘못된 타입을 거부한다. 역할 순서는 의미가 없고 **모든 역할을 충족하는 AND 집합**이다. 역할 없는 옛 path→FilePin은 변환하지 않고 D1ContractError로 거부한다. 제출 내용/파일명/provider_role에서 Expected를 추론하지 않는다.

| 고정 코드 위치 | required_roles의 정확한 어휘 |
|---|---|
| authorization.approval_records의 각 ref | authorization.approval_records |
| production provider evidence_record | production.evidence_record |
| production provider agreement_record | production.agreement_record |
| ordering provider evidence_record | ordering.evidence_record |
| ordering provider agreement_record | ordering.agreement_record |
| delivery provider evidence_record | delivery.evidence_record |
| delivery provider agreement_record | delivery.agreement_record |
| reception provider evidence_record | reception.evidence_record |
| reception provider agreement_record | reception.agreement_record |
| reception.events_ref | reception.events_ref |
| reception.roster_ref(존재할 때) | reception.roster_ref |

각 pin_bytes 호출은 위 실제 코드 위치의 역할을 필수 인자로 전달한다. provider 공용 함수에도 evidence/agreement 역할을 고정 호출부에서 각각 전달하며 제출된 provider_role로 역할을 만들지 않는다. 사용한 (path,role)이 해당 외부 필수 집합에 없으면 external FilePin role mismatch로 즉시 요청 거부한다. 기존 exact pin/bytes/크기/media type·본문·고객/source/input 검사는 그대로 둔다. 성공 반환 전에 기존 전체 path 집합 검사와 새 전체 (path,role) 집합 일치를 모두 요구한다. 이미 사용한 파일이라도 다른 필수 역할이 빠지면 required external FilePin roles not verified로 거부한다. 누락 경로·역할을 정렬해 메시지에 남긴다. 반복 참조는 횟수가 아닌 집합이고 외부에서 명시한 여러 역할은 모두 요구한다. artifacts의 무관 재고는 허용한다.

Expected 모양/키/역할 오류는 Expected 식별자가 있는 D1ContractError로, 실제 pin/역할 사용 불일치는 기존 external FilePin mismatch 또는 새 role mismatch로 분리한다. FilePin media type의 잘못된 컨테이너 타입도 새 Expected 검사에서 TypeError로 새지 않도록 동일 FilePin 규칙으로 거부한다. 호출 중 envelope/Expected/artifacts를 수정하지 않는다. VerifiedEvidence.verified_files는 기존 FilePin tuple 그대로이며, 새 역할 정보/물리 pin을 input/observation/ordering/sequence 의미 hash에 넣지 않는다. I03·공유 FilePin Schema·시퀀스 consumer를 바꾸지 않는다.

대안·기각: 승인/합의 슬롯 하나만 차단하면 나머지 역할 이동이 남는다. “필수 역할 중 하나라도 사용”은 나머지 주장을 숨기므로 기각한다. D9 본문에 ordering refs를 추가하는 (b), 별도 외부 의미 hash API, envelope 기반 옛 Expected 자동 변환은 이번 승인 밖이므로 기각한다. 합성 fixture와 허용된 호출부는 명시적인 준비 단계에서 역할을 지정하고 동결 후 공격에서는 Expected를 재작성하지 않는다.

T-1은 외부 subTest 안에 assertRaises와 caught.exception 비교를 모두 둔다. 같은 실제 시험 메서드를 의도적으로 예외를 내지 않는 검증기로 실행해 두 방향이 각각 “D1ContractError not raised”로 red이고 AttributeError가0인지 검사한다. 이 제어 실험은 옛/새 Expected 형식 불일치의 앞선 오류를 사용하지 않는다. 최종 정상 검증기의 green과 구별해 기록한다.

반증 조건: 역할 이동10건/근거 null 이동5건의 수용, 역할 중 하나만으로 성공, 미지/추가/빈/중복 역할·잘못된 Expected의 수용 또는 원시 예외, 정상 여러 역할/반복 참조/무관 재고/재게시의 오거부, 입력 수정, 정상 값/hash·verified_files 형식 변경, T-1 두 번째 방향 미실행이면 실패다. 실제 입력 인수·#126·#135–#137·SD/Q 선택·공유 계약·전체 Store/loader/CURRENT·학습은 이 수정으로 해제하지 않는다. 별도 근본 원인은 추가 수정 없이 재현·보고한다.

### #138 G-1 후속 회귀·기록 보완 계획 (실행 전)

독립 재검토 b4ec4ea9 원문은 제품의 R-1·T-1 수정을 확인했지만 새 역할 검사를 제거해도 기존 evidence/sequence 시험44개가 모두 통과하는 G-1과 이번 회차 결과 기록 부재를 지적했다. 후속 착수도 b0bbca73이며 제품 SHA256 acdd8400721f27d3c48e527b24bb5a35c48b9a232531e6a491356931989d274a를 보존한다. 새 제품 설계나 agreement 인스턴스별 결합을 추가하지 않는다.

기존 시험 모듈 안에 고정 Expected/bytes를 유지한 역할 이동10건·null 이동5건, 추가 역할 즉시 거부, 필수 다중 역할의 일부만 사용했을 때 최종 집합 거부, 닫힌 Expected의 타입/역할 오류와 정상4종 agreement/승인·반복·다중 역할·순서 변경·재게시를 고정한다. 예외 타입뿐 아니라 경로와 역할을 포함한 정확한 사유를 확인한다. 정상·거부 모두 입력 불변성을 확인하고 역할 실패가 raw/adapter 이전에 발생하는 통합 반례를 둔다. 대안인 소스 문자열 존재 검사는 기각한다. 관측 가능한 결과와 오류 계약을 검사해야 방어가 빠졌을 때 실패한다.

G-1 반증 실험은 실제 제품 파일을 수정하지 않고 메모리에서 즉시 역할 검사/최종 역할 집합 검사/둘 다 제거한다. 기존 공개 VerifiedEvidence 클래스를 그대로 유지해 어댑터 타입 오류와 목표 회귀를 혼동하지 않는다. T-1은 실제 생략 시험을 무예외 검증기로 실행해 두 방향 FAIL2/ERROR0을 확인한다. 이 의도된 red와 최종 원본 suite green을 별도로 기록한다. 시험·기록만 보완하고 I-1의 같은 종류 agreement 인스턴스 교환과 I-2의 FilePin 오류 출처 표현은 정보성 한계로 남긴다. 이전 (a) 산출물은 보존하며 이번 회차의 새 보고서·로그·diff와 실행 결과를 이어 기록한다.

### #138 R-1·G-1·T-1 실제 검증 결과 (2026-10-22 후속)

제품 역할 검사의 독립 확인 뒤 미완료 회귀·기록을 마쳤다. 이번 후속은 시험2개 모듈과 이 DR만 수정했다. 제품 SHA256은 착수·최종 모두 acdd8400721f27d3c48e527b24bb5a35c48b9a232531e6a491356931989d274a다. 테스트 파일은 evidence 60443ff63debe2272a2fd2e9abac67230c3fd6e9c6a85fc72cb0b3cd90b1e237 → bf59bccc2839f5b2e9b7121a1606b840216f1fde91930ce999666db5a40b6eb5, sequence_file 1ab5ccdcc9649e2e47848fb42263b462a6074f3c72810b64b3bd570a457fbcfb → 0f60e020a978daf9215271c645ea380533d7b1f3f5fa53e329b5ad5732d9b1e6다. DR 자체 hash와 R-1 착수 이전부터의 전체 diff는 자기참조 없이 외부 보고서에 기록한다.

새 RoleExpectedTests 12개와 SequenceProjectionTests의 통합2개는 두 Python3.12.13 환경에서 각각14 PASS/FAIL0/ERROR0/SKIP0이다. 내부 사례는 이동10·null 이동5·필수 다중 역할 누락2·공유 합의의 역할 누락3·잘못된 Expected20·FilePin 경계8 등을 포함한다. 이동은 외부 Expected/bytes를 동결하고 ordering 선언 hash만 재계산했으며 정확한 external FilePin role mismatch 경로/역할에서 거부됐다. 허용된 다른 용도로 파일을 이미 검증했어도 필수 역할이 빠지면 required external FilePin roles not verified에서 거부한다. 통합 반례15건은 VerifiedEvidence를 반환하지 않아 raw/adapter 호출이0이다.

R-1 이전 제품·시험 snapshot을 메모리에서 복원해 두 환경에서 다시 실행한 결과, 역할 이동10건은 VALID·null 이동5건은 UNKNOWN으로 잘못 수용됐고 T-1 무예외 control은 호출1/FAIL1/ERROR1(AttributeError)이었다. 옛 API는 신뢰한 fixture 준비 단계에서 path→FilePin으로 고정한 뒤 사용했다. 현재 control은 두 방향을 모두 실행해 FAIL2/ERROR0이며 AttributeError가 없다. 이 의도된 red는 최종 원본 suite 실패와 구별한다.

| 검증 (실제 명령은 새 로그) | 의존성 Python3.12.13 | 무의존 Python3.12.13 |
|---|---|---|
| 새 회귀14개 | PASS14 · FAIL0 · ERROR0 · SKIP0 | PASS14 · FAIL0 · ERROR0 · SKIP0 |
| W0/W1 관련65개 | PASS65 · FAIL0 · ERROR0 · SKIP0 | PASS55 · FAIL0 · ERROR0 · SKIP10 |
| 기존 D1 174개 | PASS174 · FAIL0 · ERROR0 · SKIP0 | PASS112 · FAIL0 · ERROR0 · SKIP62 |
| 전체1034개 | PASS1031 · FAIL0 · ERROR0 · SKIP3 | PASS860 · FAIL0 · ERROR0 · SKIP174 |
| 정상6개 시나리오의 값/hash/키/토큰/gap/flat pins·입력 불변 | 동일 | 동일 |

G-1 메모리 변이는 같은 원본 context 클래스를 유지하고 evidence/sequence58개를 실행했다. 원본은 FAIL0/ERROR0, 즉시 검사 제거는 실패32건, 최종 집합 검사 제거는 실패5건, 둘 다 제거는 실패37건이며 ERROR는 모두0이다. 실패 건수에는 subTest별 실패를 센다. 두 환경에서 동일하고 무의존만 기존 Parquet5개가 SKIP다. 즉시 검사 누락은 정확한 역할 오류 계약 회귀가, 최종 검사 누락은 필수 다중 역할 누락 회귀가 검출한다. 소스 문자열 존재 시험은 추가하지 않았다. 진단 첫 실행은 context 클래스를 새로 만들어 타입 검사에 먼저 걸렸으므로 무효로 보존하고, 스크립트를 고쳐 위 유효 실험을 재실행했다. 제품 파일은 변이하지 않았다.

입력/관측/순서/SequenceRow 의미 hash와 정상 single-full·conflicting·3상태·미제공 생산·승인/4종 합의·재게시 결과를 이전 제품 snapshot과 대조해 두 환경에서 모두 같았다. single-full 시퀀스 hash b143e3cb566c574e6c6804517cea17746ae3400fb9de52b8826851a27a703145, 3상태 b67b1c90481bc48ea242c9752227ad4640ea52f11cc33fb1c10fe0a450dfccf5도 과거 고정 결과와 같았다. 물리 재게시의 exact pins는 달라지고 옛 Expected 연결은 거부한다. 역할·승인/합의 파일을 의미 hash에 새로 넣지 않았다.

내부 API 이관: SyntheticEvidenceFixture.expect_pin/pin/seal은 신뢰한 준비 단계에서 고정 역할을 지정한다. fixture.verify와 RequiredPinTests.verify_unchanged, sequence-file 통합 호출은 새 Expected를 전달하며 성공/거부 후 원본을 보존한다. 새 RoleExpectedTests 및 승인/4종 agreement 통합 시험도 같은 API를 명시한다. 읽기 허용 경로의 실제 제품 호출처는 여전히 verify_evidence 정의 외에 없으며 외부 소비자/실제 제공자 이관을 완료했다고 주장하지 않는다. I03/FilePin Schema와 VerifiedEvidence.verified_files의 기존4필드 tuple·시퀀스 소비자 제품은 변경하지 않았다.

경계/DR39 PASS, git diff --check PASS다. 전체 SKIP 사유와 무의존 Schema/Parquet 미설치를 새 로그에 보존한다. Python3.10은 PATH·프로젝트/uv/pyenv·일반 설치 위치에서 실행기를 찾지 못해 BLOCKED이며 설치하지 않았다. 소유검사는 기존13건 미등록으로 FAIL이고 신규 시험 파일은0개다. 91개 시작 snapshot 중 이번 대상3개 이외는 바이트가 같고, .gitignore·개인 요구사항·HTML·이전 plans/로그도 보존했다. HEAD/origin b0bbca73와 빈 index를 유지했다.

새 기록은 plans/D1-evidence-roles-138-review-20261022.md · plans/D1-evidence-roles-138-verification-20261022.log · plans/D1-evidence-roles-138-changes-20261022.diff다. 이전 (a) 기록을 덮어쓰지 않았다. #138 R-1·G-1·T-1의 로컬 수정·회귀 기록 보완 완료로 한정하며 독립 재검토·이슈 종료·D1 전체 인수는 별도다. I-1 같은 종류 agreement의 인스턴스별 교환은 현재 결과 영향이 없는 정보성 한계이며 향후 의미가 생기면 별도 결합 계약 검토가 필요하다. I-2 FilePin 오류 메시지의 Expected/제출 출처 미구분도 정보성 사항으로 남긴다. #126·#135–#137·SD/Q 선택·실제 입력 인수·전체 Store/loader/CURRENT·학습을 바꾸지 않았고 브랜치/스테이징/커밋/푸시/GitHub 쓰기/다른 에이전트·채팅 실행도 하지 않았다.

**근거:** SD/Q 방향을 적용하는 내부 구현이며 실제 제공자 근거 없이도 합성 정상/거부를 검증할 수 있다. 새 profile의 의미/단위/한계를 먼저 기록하고 구현한다. 설정·사용자 승인값을 새로 추론하지 않는다.

## 기각한 안과 기각 사유

| 안 | 사유 |
|---|---|
| source/pin 불일치를 unknown으로 숨기기 | 잘못된 묶음이므로 요청 거부 |
| hash 정합성으로 행동 포착 완전성 인증 | 서로 다른 사실이며 운영 admission 제외 |
| UNKNOWN을 PAD/0벡터로 보완 | 관측 불명과 완전 관측 빈 입력을 혼동 |
| event_id·행 순서로 tie 정렬 | 실제 순서 근거가 아님 |
| 레거시 묶음을 새 버전으로 자동 변환 | 기존 golden·정확한 요청을 바꾸므로 기각 |

## 이 결정이 틀렸다면 어떻게 드러나나

상충 input/출처/외부 pin 수용, 부분 전달에서 VALID 생성, 필요한 tie를 임의 선택, UNKNOWN 고객 삭제/배열 보완, null/0 혼동, 파일 dtype/버전 오류 수용, 포장 변경의 의미 hash 변동, 의미 동일성을 이유로 잘못된 파일 수용이면 실패다. 기존 #122–#134 정상/반례의 회귀도 실패다.

## 민감도

근거의 기간·유형·고객·상태·실제 순서와 토큰/간격 1개 변경은 관련 값과 의미에 영향을 준다. 파일 바이트만 변하면 정확한 file hash가 바뀐다. 정밀도 축소·추정 종료·G1 자동 대체는 없다.

## 남은 불확실성

#126·G1·실제 제공자 수락·운영 목적, 세션/가입일/평생 이력, 실제 split/학습·공식 품질·full Store/CURRENT는 별도다. Python 3.10 BLOCKED와 소유 등록은 실제 확인 후 보고한다. 신규 시험 3개는 리드 인계하며 소유표를 수정하지 않는다. 커밋·푸시·GitHub 쓰기·다른 채팅 메시지는 하지 않는다.
