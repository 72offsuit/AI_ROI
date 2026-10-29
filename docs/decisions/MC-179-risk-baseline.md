# MC-179-risk-baseline — Test 전용 고정 위험도 기준선

| | |
|---|---|
| 태스크 | #179 R3, 시스템 팀 |
| 작성 | 광진 작업용 Codex · 2026-10-30 |
| 커밋 | 기준 main 68759ebe11021ba0d6d482b4758a5828d4fd0e93 위 미커밋 작업. 실제 프로젝트 데이터 학습은 미실행 |
| 상태 | 합성 연결 검증용 카드. 실제 성능·운영 승인 전 |

## 무엇을 예측하나

고객의 churn 확률이다. 실제 평가 함수가 결과 결측을 제외한 뒤 만든 Train의 T0 대조군에서 retention의 반대인 1-retention을 학습한다. 처치 효과나 증분 기여이익을 예측하는 모델이 아니다.

## 어떤 결정에 쓰이나

동일한 Test에서 위험도가 높은 순으로 정렬하는 비교 기준선으로만 쓴다. 전략 선택·Validation 선택·Train 단위 성능 보고·예산 정책에 쓰지 않는다. 최소안 M의 Test 한정 수용 근거는 #179의 issuecomment-6494889527이며, 범위를 넓히면 OOF를 다시 설계한다.

## 데이터 계보

| | |
|---|---|
| 원천 | tests.test_uplift_models.synthetic(n=600, seed=17)의 시험용 합성 입력이며 시뮬레이터 생성분·커머스 실측 자료가 아님 |
| 기간 | 달력 시간·이벤트가 없는 함수 연결 시험. 실제 42일 관측 근거는 별도의 R1 시험으로 확인 |
| 고객 수 · 이벤트 수 | 고유 ID 600명, retention 결측 13명 제외 후 587명. 이벤트 입력 없음 |
| index_date (T0) | 합성 모델 시험에는 없음. 실제 파이프라인은 RunSummary와 공개 이벤트를 통해 전달 |
| Feature Cutoff | 합성 x1/x2/x3에는 시간 원천 없음. 실제 Feature는 timestamp < T0이며 이후 값을 사용하지 않음 |
| 라벨 정의 | 합성 retention의 반대인 churn. 실제 파이프라인 라벨은 KST [T0,T0+42일) 구매 관측 |

합성 수치·계보는 프로젝트의 실험 성능 근거로 사용할 수 없다. 실제 개발 데이터가 준비되면 원천 실행 ID·기간·Feature 버전·cutoff·실제 고객 수·분할 해시를 별도로 기록한다.

## 분할

| 집합 | 건수 | 비율 | churn 양성 비율 |
|---|---:|---|---|
| 외부 Train | 410 | 정제 587명 중 약 70% | 전 군 합계는 위험도 fit 모집단과 다름 |
| 실제 위험도 fit: Train∩T0 | 163 | Train의 부분집합 | 92/163. 음성 71명 |
| 위험도 Validation | 0 | 사양 선택을 하지 않음 | 해당 없음 |
| 외부 Test | 177 | 정제 587명 중 약 30% | 프로젝트 성능용으로 보고하지 않음 |

**분할 기준:** 기존 evaluate_uplift_models의 결과 결측 제거 후 처치군 층화 분할(seed=7)을 직접 공유한다. 별도의 같은 seed 재분할을 만들지 않는다. risk fit과 Test 교집합은 0명이다.

fit IDs SHA256: e99e41c861d96b7620d54f94f4d8941632e7408a2328df609398dadb6bc42cbc.
Test IDs SHA256: 40629027809a97cd0ba94eca9fcb7712db0226ab1aff347baf7e3d8519edce4b.

**Final Holdout을 무엇에 썼나:** 접근·사용하지 않았다.

**무엇에 쓰지 않았나:** Test는 사양·전처리 기준·하이퍼파라미터·임계값·전략·예산 선택에 쓰지 않았다. 이 표는 정식 60/20/20 공통 Test 또는 SPLIT 준수를 뜻하지 않는다.

## 학습

| | |
|---|---|
| 알고리즘 | 사전 고정 LogisticRegression, config의 churn.risk_baseline_model |
| 하이퍼파라미터 | C=0.5, max_iter=2000, class_weight=balanced. 평가 분할·계보의 seed=7이며 기존 LogisticRegression의 random_state=None·기본 lbfgs를 보존함 |
| 무엇으로 골랐나 | 성능으로 고르지 않음. 기존 지원 모델 중 단순한 비교 기준을 사전 고정한 구현 선택 |
| 탐색 범위·횟수 | 모델·설정 탐색 0회. 고정 사양 fit 후 합성 반례 시험에서 다시 실행 |
| 불균형 처리 | 기존 balanced 설정. 실제 프로젝트의 적합성·보정 품질은 미평가 |

Train에만 전처리 fit을 수행한다. 기존 별칭 열은 제외하고 금지 열·고객 ID 열·post_t0 열은 거부한다. 한 클래스뿐이면 factory 실행 전에 위험도 행만 not_run으로 남긴다. 전역 Churn best 모델·전체 T0 모델을 재사용하지 않는다.

## ★ 누수 점검

| 확인한 것 | 어떻게 | 결과 |
|---|---|---|
| 금지 Feature 부재 | 고정 factory의 금지 열 거부·별칭 제외 반례 | 합성 입력 시험 통과. 실제 Feature 전체 인수는 미실행 |
| Feature Cutoff 준수 | R1 경계 시험과 별도 검증 | 모델 합성 x1/x2/x3 자체로 시간 준수를 증명하지 않음 |
| 고객 단위 분할 | 실제 evaluator split의 Train∩T0 ID 감시·Test 교집합·해시 대조 | 합성 fit 163명, Test 177명, 교집합 0명 |
| Test 라벨 사용 여부 | 결측 마스크·처치·seed를 고정하고 Test 결과만 반전 | fit X·fit y·사양·Test 예측이 동일 |
| 라벨 동어반복 | 합성 수치 Feature만 사용 | 실제 데이터의 단일 Feature 누수·생성 창 인공물은 미검증 |

## 성능

| 지표 | Train | Validation | Test | 신뢰구간 |
|---|---|---|---|---|
| 실제 데이터 AUC·Qini·AUUC·확률 보정 | 미실행 | 미실행 | 미실행 | 판정 불가 |

합성 시험의 평가 함수가 점수를 계산하더라도 이는 연결·불변성 시험 결과다. 프로젝트 성능·성공 기준 달성을 주장하지 않는다. 실제 S-learner 동점 비율도 미측정이다. 합성 대표군 T0/T3의 Test 121명에서 81명이 동점 묶음에 속했다는 관측은 그 시험 입력에만 해당한다.

## 해석

위험도 순위는 구매 중단 가능성의 기준선이다. 위험도가 높은 사람이 처치 효과나 이익도 높다는 의미가 아니다. 실제 Feature 중요도·SHAP·보정 곡선은 아직 산출하지 않았으므로 해석 결과를 기입하지 않는다.

## 실패 모드

Train 대조군이 한 클래스, 고객 ID 중복·결손, 비유한 확률, factory 실패면 위험도 행만 중단하고 정상 S/T/X 평가를 유지한다. 외부 churn_p는 자기 선언 계보의 진위 검증이 불가능해 항상 위험도 not_run으로 남긴다. factory와 동시 입력해도 실행하지 않는다. 파일·쓰기 관측 실패는 앞선 R1 단계에서 라벨을 차단한다. Validation·선택·Train 보고에 위험도를 사용하거나 공통 Test 계약이 바뀌면 현재 카드만으로 진행하지 않는다. 실제 성능·분포 변화와 실행 메모리 부하는 별도 확인 대상이다.

## 재현

```bash
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 python3 -B -m unittest tests.test_uplift_models.Test179RiskConnection tests.test_churn_sprint.Test179PopulationAudit -v
```

프로젝트의 두 requirements를 설치한 Python 3.12 환경에서 실행한다. 시뮬레이터·진단 내부는 import하지 않는다.

| | |
|---|---|
| 시드 | 합성 생성 17, 평가 분할·모델 7 |
| 소요 | 개별 학습 시간·최대 메모리는 별도 측정하지 않음. 전체 검증 소요는 검증 로그에 기록 |
| 환경 | CPython 3.12.13, numpy 2.5.4, pandas 3.0.6, scikit-learn 1.9.1, scipy 1.18.1. 전체 의존성 일치는 검증 기록 참조 |
