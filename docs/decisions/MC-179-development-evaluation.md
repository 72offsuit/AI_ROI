# MC-179-development-evaluation — N2 연결 이후 실제 개발 평가

| | |
|---|---|
| 태스크 | #179 R1~R6 · PR #251 |
| 작성 | 광진 작업용 Codex · 2026-10-30 |
| 커밋 | cdc9233b65da379907a7c1427be161f917cb546a 위 N2 미커밋 구현으로 실행. 아래 소스 SHA-256 고정 |
| 상태 | 최초 개발 실행 기록. 30d69ae의 Claude 독립 검수는 차단0·비차단5. 아래 해석 보완 후 동일 조건 재실행을 계획함. 정식 대규모 평가·운영 승인 전 |

## 무엇을 예측하나

Churn은 향후 42일 무구매 확률, Uplift는 처치별 retention 차이, CLV는 이번 연결에서 42일 매출이다. CLV 12개월 가치나 Churn 확률을 처치 효과로 해석하지 않는다. Test 위험도 비교 기준은 실제 Train∩T0에서만 학습한 고정 LogisticRegression이다.

## 어떤 결정에 쓰이나

#179의 관측·분할 감사·Test 기준선·동점·결손 처리와 S0~S5 연결이 실제 생성 입력에서도 작동하는지 확인한다. 기존 모델·전략·예산 정책을 실행한 개발 검사다. Test 수치로 정책을 바꾸지 않았으며 GATE2·정식 SRS 모델 구성을 승인하는 자료가 아니다.

## 데이터 계보

| | |
|---|---|
| 원천 | simulator 공개 API, seed42, customers2000, profile small. 커머스·숨김 상태·정답 데이터 미사용 |
| 실행 | SP-179-N2-DEV42. 본선 warmup SR-20261030-061142-c97bebbe, RCT SR-20261030-061159-020c61bb |
| 기간 | 시작 2025-01-01, t1 2025-06-30, t2 2025-08-11, 미래 종료 2025-09-22. 모두 KST 00:00 |
| 고객 수 · 이벤트 수 | 요청 2,000명. t1 RCT 적격 883명, t2 Feature 1,968명, 전략 평가 적격 896명. t2까지 원시 이벤트 748,545건 |
| index_date (T0) | 학습 입력 t1, 미래 점수 t2 |
| Feature Cutoff | 현재 sprint 구현의 timestamp < index_date. 기존 초 단위 표현에 대한 새 공용 결정은 하지 않음 |
| 라벨 정의 | [index_date,index_date+42일) 무구매. 같은 RunSummary 창·파일·출처·현재 실행 rejected=0 근거 확인 |

본선 및 S0~S5의 읽기 근거는 모두 ok다. 여섯 분기의 실제 external_parent_run_id는 None으로 보존했다. 같은 스냅샷 호출과 history 내용 지문, 검증한 본선+분기 파일 내용과 공개 events 전량의 일치를 확인했다. 공통 history SHA-256은 b93874d5bb6c32ca19a4c67c714a639e1afadf4df06cc0ab81ebb89645e0c192다.

## 분할

| 집합 | 건수 | 비율 | 양성 비율 |
|---|---:|---|---|
| Churn 학습·선택 | 442 | t1 RCT T0 | 210/442 = 0.475113 |
| Churn 내부 CV | 5-Fold | 각 검증 약 20% | fold별 수치는 결과에서 별도 미게시 |
| Churn 미래 평가 | 1,968 | t2 Feature 모집단 | 710/1,968 = 0.360772 |
| Uplift Train | 618 | 정제 883명 중 약 70% | 전체 처치군 합계는 위험도 fit 모집단과 다름 |
| Uplift Test | 265 | 정제 883명 중 약 30% | 개별 군별 결과 파일 참조 |
| 실제 위험도 fit | 309 | 위 Train∩T0 | 두 클래스 사전 검사 통과, 비율은 별도 집계하지 않음 |
| CLV OOF | 883 | 5-Fold | 연속값이므로 해당 없음 |

**분할 기준:** Churn 내부는 StratifiedKFold, Uplift는 실제 결과 결측 제거 후 처치군 층화 분할을 직접 공유한다. 위험도 fit와 Test 교집합은 0명이며 Test 해시도 evaluator와 같다. 위험도 별도 Validation·후보 탐색은 없다. Uplift 방법 선택은 Train 내부 25% Validation(대표 T3 비교 97명)에서 수행했다.

Churn 학습과 미래 평가에는 고객 442명이 겹친다. 따라서 기존 고객의 미래 시점 진단이며 독립적인 새 고객 성능 또는 정식 공통 60/20/20 분할 D 충족이 아니다.

- 실제 Uplift Train IDs SHA-256: 0e03c70bc65e13cdfdeba8836cd3534f50b3011b784aece41f3c4724b4ff8783
- Test IDs SHA-256: ce8596718d36eccbe72d967df44654ac9ee14133981a92e5215fae9f73f861d6
- 위험도 fit IDs SHA-256: ba4b83dcb17b3836c4403ab960dce0c53d5b8c5c44d9b4dc5464eacf5b981d5a

**Final Holdout을 무엇에 썼나:** 접근·사용하지 않았다. temporal_holdout 필드 이름은 위 기존 고객 미래 평가를 뜻하며 Final Holdout과 다르다.

**무엇에 쓰지 않았나:** Test·Final Holdout으로 Feature·모델 사양·임계값·전략·예산을 변경하지 않았다. 이번 실행 결과를 본 뒤 재튜닝하거나 더 좋은 seed를 고르지 않았다.

## 학습

| | |
|---|---|
| 알고리즘 | 기존 Churn rule_recency·LogisticRegression·RandomForest·HistGB, Uplift S/T/X, CLV historical_avg·HistGB |
| 하이퍼파라미터 | config/model_config.yaml 기존 값 그대로. LR C=.5/max_iter=2000/balanced, RF 300/min_leaf3/balanced_subsample/n_jobs=-1, HistGB .05/300/15/L2=1/balanced |
| 무엇으로 골랐나 | Churn 내부 CV로 RF 선택. Uplift Train 내부 Validation의 T/X Qini가 모두 0.020310으로 같아 기존 순서의 T 선택. 위험도 사양은 사전 고정 |
| 탐색 범위·횟수 | 고정 개발 실행 1회. 별도 하이퍼파라미터 탐색 0회, CV5·내부 임계 OOF3 유지, 학습 표본 제한 없음 |
| 불균형 처리 | 기존 balanced·balanced_subsample. rule은 학습 fold F1 임계 |
| 전처리 | 학습 fold에서 1%/99% 분위 절단·중앙값 대치·결측 지시자. 원시 결측·감사 수는 보존 |

이 Churn 후보 목록은 현재 sprint의 구현이다. SRS의 XGBoost/LightGBM/CatBoost 필수 비교를 이번에 새로 구현하거나 대체 승인한 것이 아니다.

## ★ 누수 점검

| 확인한 것 | 어떻게 | 결과 |
|---|---|---|
| 금지 Feature 부재 | 기존 명시 열 선택, 위험도 factory 금지 열·별칭 반례 회귀 | 검사 통과. persona·처치 배정·미래 열을 학습용으로 새로 허용하지 않음 |
| Feature Cutoff 준수 | 공개 이벤트·기존 Feature 경계 검사와 같은 RunSummary 관측 창 | 관측/파일 근거 ok. 전체 Feature 요구 재감사 완료를 뜻하지 않음 |
| 고객 단위 분할 | 실제 split과 위험도 fit/Test 해시·교집합 대조 | 위험도 교집합0. Churn 미래 교집합442 공개 |
| Test 라벨 사용 | 반전 불변성 회귀, 고정 위험도 사양과 공유 split | 합성 반례 통과. 실제 실행 기록은 학습309/Test265 |
| 라벨 동어반복 | 기존 미래 관측 라벨, CV·미래 수치 확인 | AUC>0.95 없음. 단일 Feature별 전면 누수 연구는 이번 범위 밖 |

## 성능

| 지표 | Train | Validation/CV | Test·미래 평가 | 신뢰구간 |
|---|---|---|---|---|
| Churn rule ROC-AUC | 미보고 | 0.756602 ± fold SD 0.036716 | 미실행 | 미산출 |
| Churn LR ROC-AUC | 미보고 | 0.789146 ± 0.021347 | 미실행 | 미산출 |
| Churn RF ROC-AUC | 미보고 | 0.801841 ± 0.028676 | 기존 고객 미래 0.875272 | 미산출 |
| Churn HistGB ROC-AUC | 미보고 | 0.781371 ± 0.025555 | 미실행 | 미산출 |
| Churn RF PR-AUC | 미보고 | 0.813283 | 기존 고객 미래 0.795757 | 미산출 |
| 위험도 기준선 Qini | 미보고 | 선택 안 함 | T0/T3 166명: 0.021460 | 미산출 |
| S-learner Qini | 미보고 | 미보고 | 0.000000 | 미산출 |
| T/X-learner Qini | 미보고 | 양쪽 0.020310 | 양쪽 0.043936 | 미산출 |
| CLV historical_avg Spearman | 미보고 | 5-Fold OOF 0.458062 | 별도 Test 없음 | 미산출 |
| CLV HistGB Spearman | 미보고 | 5-Fold OOF 0.493233 | 별도 Test 없음 | 미산출 |

fold SD는 신뢰구간이 아니다. 소표본 단일 seed이므로 우월성·유의성 판정을 하지 않는다. CLV HistGB의 MAE 44,192원이 기준선 42,230원보다 크고, Top20 hit도 0.519774 대 0.570621로 낮다. 순위 상관 개선만으로 전체 우월성을 주장하지 않는다.

실제 S-learner는 대표 Test 166명 전원이 같은 점수다(고유 점수1, largest_tie166). tied-endpoints-v1에서 Qini0, Top10/30은 fractional-boundary-v1로 각각 약 0.095010이다. T/X는 155고유점수, 동점 고객16명(9.6386%), 최대 묶음7명이다. 동점을 풀기 위한 ID 정렬·임의 흔들기·시뮬레이터 변경을 하지 않았다.

S0~S5는 모두 896명 결과를 완전히 관측했다. S1 대비 측정 증분이익은 S2 863,960원, S3 981,677원, S4/S5 981,857원이다. 이 단일 실행의 측정치이며 전략 우월성 확정이 아니다. 추가 마케팅비가 양수가 아니므로 마케팅 ROI는 null, AI 투자비 미지정으로 AI ROI도 null이다. 계획상 기대 ROI와 실현 ROI를 혼동하지 않는다.

## 해석

RF SHAP 상위는 visit_recency, add_to_cart_count_60d, cart_conversion_change, active_days_30d, session_duration_change다. 학습442명 전체에 맞춘 모델 해석이며 인과 효과·독립 Test 설명 검증은 아니다. 상관 Feature와 결측 지시자의 영향이 있어 중요도만으로 원인이나 새 정책을 정하지 않는다.

### 독립 검수 NB-A: 이 규모의 Uplift 해석 제한

기저 학습기 src/decision/uplift.py의 min_samples_leaf=80은 이번 실행 이전의 설정이다. 실제 평가 Train의 처치군은 T1=78명, T2~T4=77명으로, 두 잎을 만드는 데 필요한 최소 160명보다 작다. 이후 전체 RCT로 전략용 T-learner를 적합할 때도 T1=111명, T2~T4=110명이라 같은 제약이 남는다. 처리군 모델은 고객별 반응 차이를 나누지 못하고 상수 예측을 낸다. S-learner의 처치 지시 변수도 군당 표본 부족으로 분할에 쓰이지 못하므로 이번 전원 동점은 구조적으로 설명된다.

T-learner의 처치별 점수는 이 조건에서 상수 c_a − 대조군 예측 μ0(x)다. 고객 순위는 대조군 결과 모델의 역순이며 처치 간 점수 차이도 고객에 따라 달라지지 않는다. 이번 T/X는 모든 처치군의 Qini·AUUC가 같고 대표 Validation 값도 같았다. X가 일반적으로 T와 같은 알고리즘이라는 뜻은 아니다. 이 실행과 검토용 합성 입력에서 같은 순위가 나타난 것이다.

실제 uplift_scores.csv의 1,968명은 모두 uplift_arm=T4다. T1/T2/T3 점수에서 T4 점수를 뺀 값의 고객 간 변화폭은 각각 약 1.11e-16/2.22e-16/2.22e-16으로 부동소수점 수준이다. 따라서 T/X Qini 0.043936과 위험도 기준선 0.021460의 비교를 고객별 처치 효과 학습의 우월성으로 해석하지 않는다. S3~S5는 이 실행에서 공통 위험 순위와 T4 추천에 예산·CLV 등의 기존 선정 규칙을 적용한 결과다. 세 전략의 선정 인원·계획 전체가 같다는 주장은 아니다.

이번 실행은 #179의 관측·연결·평가 규칙 확인에 사용한다. Uplift의 실질적인 개인별 효과 학습 성과, D4 완료, 처치 정책 우월성의 근거로 사용하지 않는다. 모델 설정은 변경하지 않는다. 표본 크기 대비 leaf 하한·처치군별 학습 가능 조건·Validation 계획은 D4 #86에 연결해 담당자와 결정할 후속 범위다. Test 결과를 보고 leaf를 낮추는 튜닝은 하지 않는다.

## 실패 모드

- 실제 전처리에서 All-NaN slice 경고72건이 발생했다. t1 학습의 days_since_last_campaign_180d·coupon_click_rate_180d·search_to_purchase_conversion은 442명 전부 결측이다. 기존 QuantileClipper는 빈 분위수를 무한 경계로 처리하고 SimpleImputer는 keep_empty_features를 사용한다. 모델 입력의 기술적 대치가 실제 관측0·라벨0·원가0이라는 의미는 아니다. 이번에 결측 원천이나 대치 정책을 변경하지 않았다.
- 소규모 입력·미래 고객 중복·42일 CLV·성능 CI 미산출 때문에 정식 배포 근거로 사용할 수 없다. 규모 증가 시 전체 공개 스트림 내용 지문과 반복 검증의 시간·메모리 비용이 증가한다. 최대 메모리는 미측정이다.
- parent None 자체를 자동 승인하지 않는다. 임의 history·파일 변조·공개 스트림 차이·중간 예외는 거부한다. 프로세스 밖 snapshot 인수와 동시 세계 조작은 지원 범위 밖이다.
- N3 조상 거부의 Feature·Eligible·S1 차단 정책은 기존처럼 감사만 한다. 새 팀 합의를 받은 것으로 표시하지 않는다.
- 최초 run_meta.provenance.repo_commit는 cdc9233이지만 실제 실행은 그 위 미커밋 N2 코드다. 위 소스 해시와 preflight가 30d69ae의 코드에 대응함을 별도로 확인했다. 최초 게시물만으로 clean cdc9233 실행이라고 해석하면 안 된다. 깨끗한 커밋에서 동일 조건을 재실행해 별도 계보를 남기며 기존 결과 파일의 commit 값을 사후 수정하지 않는다.

## 독립 검수 이후 동일 조건 재실행 계획

2026-10-30 사용자 지시에 따라 문서·docstring 보완을 먼저 커밋하고, 추적/미추적 작업트리가 비어 있는 것을 확인한 뒤 한 번 재실행한다. run-id와 출력 폴더만 새로 지정하고 seed42·2,000명·small·CV5·표본 제한 없음·기존 설정·Python 환경·스레드 환경은 유지한다. 이는 재현성·계보 확인이며 추가 seed 탐색·Test 튜닝이 아니다. 동일 개발 Test를 다시 산출·조회한 사실을 기록한다. Final Holdout은 사용하지 않는다.

사전에 고정할 대조: 모델 및 경제 수치의 절대/상대 허용차 1e-12, 고객 ID/분할/배정/건수/상태는 정확한 일치. 시각·생성 실행 ID·출력 경로·소요 시간·파일 mtime·스냅샷 참조처럼 실행별로 달라지는 값은 별도 계보 차이로 보존한다. 결과 바이트가 같다고 가정하거나 임의의 불일치를 삭제하지 않는다. 제품 로직·설정과 실행 전후 작업트리·해시도 대조한다. 결과가 다르면 재튜닝 없이 차이를 보고한다. 재실행 결과는 완료 후 별도 절에 추가한다.

## 재현

Python3.12의 requirements.txt·requirements-dev.txt 설치 환경에서, 아직 없는 새 출력 폴더와 run-id를 사용한다.

```bash
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 python3 -B src/main.py \
  --mode full --seed 42 --customers 2000 --profile small \
  --run-id SP-179-N2-DEV42 \
  --out /tmp/ai-roi179-n2-development-20261030/data \
  --results-root /tmp/ai-roi179-n2-development-20261030/results
```

| | |
|---|---|
| 시드 | 42, 단일 실행 |
| 소요 | CLI 기록127.4초, /usr/bin/time의 real127.65초. Churn8.395초, Uplift1.877초, CLV0.853초 |
| 환경 | CPython3.12.13, numpy2.5.4, pandas3.0.6, scikit-learn1.9.1, scipy1.18.1, shap0.54.1, pyarrow25.0.1, PyYAML6.0.3, jsonschema4.26.0, referencing0.37.0. torch 없음 |
| 프로세스 상태 | CLI exit_code0·25단계ok. 외부 time -l은 kern.clockrate 접근 제한으로 exit1. 최대 RSS는 BLOCKED이며 0으로 쓰지 않음 |
| 학습 소스 | run_sprint.py SHA-256 3ef5dec791b2fbcc6f33090046b6ea19c8002deba8ed74ceace2814f40a1e154 |
| 필수 검증 소스 | observation_contract.py SHA-256 6ee8989cac3cd17ef7883955cdea2497bc33c4c2b57b2e88fae1d758f9bda294 |
| 모델 설정 | model_config.yaml SHA-256 05ff366d8eb7a459e8e029081d63e7bf8d9fcaf9d10b05f5b5a95f13d16c8ff0 |

생성 결과는 커밋하지 않는다. 로컬 검토 패키지 plans/issue179_n2_evaluation_20261030_v08의 preflight.json·evaluation_summary.json·result_hashes.json·evaluation_outputs/와 실행 로그에 결과·소스 해시와 18개 대조의 실제 결과를 보존한다. 검토자는 같은 파일을 직접 대조해야 하며 이 카드가 독립 검수 승인을 대신하지 않는다.
