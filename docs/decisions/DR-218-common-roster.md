# DR-218-common-roster — 기준일별 공통 명부: (고객, 기준일) 역할 · 과제 Test 구성 · 저장 위치

| | |
|---|---|
| 태스크 | 리드 · #218 공통 분할 입력 (Sprint 5, `docs/sprint_plan.md` §5 "명부 · 입력 11/25") · PRD §43.1 · SRS SPLIT-001 · SPLIT-004 |
| 작성 | 인성(Danto7632, 에이전트 작성) · 2026-11-24 |
| 상태 | 리드 결정(2026-11-24) — 광진 리뷰(11/24) 반영: 명부를 t2 분기 결과 전에 확정 · 기존 시간 평가에서 과제 Test 후보 제외 · 과제 Test 후보 상태 · 재동결 규칙. 명부로 계산한 성능은 아직 없다 |

## 무엇을 정하는가

ML · LSTM 비교(#317) · 고객군 성능(#303 ML-010) · 등급별 이탈률(#221 ANA-008) · 과제 Test 가 함께 쓰는 **기준일별 고객 명부**의 행 단위 · 역할 정의 · 제외 사유 · 층화 키 · 저장 위치. 구현은 `src/decision/split_roster.py`(`split-roster-v1`)와 `run_sprint` 의 `prepare_split_roster` · `write_split_roster`.

## 정하지 않으면 무엇이 막히나

- #317 이 "11/25 정식 공통 명부 · `t_prior` · `t1` Feature Store · 고객별 관측 근거"를 기다린다. 지금 Feature Store 에는 t1 · t2 만 있고 앞 기준일(t_prior) 표가 없다.
- 과제 Test 를 "학습 고객을 뺀 t2 고객"으로 정했지만(Plan#6 · SPLIT-001) 누가 학습 고객인지를 실행 산출물로 적은 곳이 없다. GATE 3 뒤 1회 평가 때 정하면 결과를 보고 고르는 셈이 된다.
- ML-010 · ANA-008 이 같은 고객 · 같은 등급을 쓰려면 기준일마다 등급(DR-221)이 한 번만 계산돼 저장돼야 한다.

## 선택지

| 결정 | 안 | 내용 | 장점 | 단점 |
|---|---|---|---|---|
| 행 범위 | **A** | 기준일별 Eligible 전원 + 역할 · 제외 사유 | 제외된 고객과 그 이유 · 등급 분포가 보인다 | 행이 많다 |
| | B | 역할이 있는 고객만 | 작다 | 누가 왜 빠졌는지 다른 파일을 봐야 한다 |
| 과제 Test | **A** | Eligible(t2) ∩ t1 실험 무처치 ∩ train · validation 고객이 아님 | SPLIT-001 "최종 모델 학습 고객 제외" 그대로 | 표본이 작을 수 있다 |
| | B | t1 validation(최종 재학습) 고객만 제외 | 표본이 크다 | 앞 기준일 학습 고객이 Test 에 남는다 — 같은 고객의 과거를 학습한 모델로 평가 |
| | C | Eligible(t2) ∩ 무처치 전원 | 지금 `churn_temporal_holdout` 모집단과 같다 | 기존 고객의 미래 시점 평가(DR-179)이지 고객 분리 Test 가 아니다 |
| t2 역할의 라벨 | **A** | 라벨을 보지 않고 정한다 | Test 라벨을 GATE 3 전에 열지 않는다 | 라벨이 없는 Test 고객이 평가 때 빠질 수 있다 |
| | B | 라벨 있는 고객만 test | 평가 표본이 바로 확정된다 | 동결 전에 Test 라벨(S0 분기 결과)을 읽는다 |
| 저장 | **A** | 결과 폴더 `split_roster.csv` + `run_meta.split_roster` 요약, Feature Store 에 t_prior Feature · 라벨과 기준일별 등급 표 | 소비처가 실행 결과와 Feature 표를 지문으로 대조할 수 있다 | 파일이 하나 는다 |
| | B | Feature Store 에만 | 한곳에 모인다 | `--feature-store-root` 없이 돈 실행에는 명부가 없다 |

## 조사한 것

| 출처 | 무엇을 말하나 | 우리 맥락에 얼마나 맞나 |
|---|---|---|
| PRD §43.1 · SRS SPLIT-001 · SPLIT-004(Plan#6) | Train = t1 · 무처치 42일 라벨, Validation = t_prior 학습 → t1 평가, Test = t2 · 무처치 분기 · **최종 모델 학습 고객 제외** · GATE 3 동결 뒤 1회. 고객이 겹치는 t2 평가는 DR-179 로 따로 | 역할 정의의 직접 근거 |
| #218 공통 분할 답변(2026-11-23) | "한 모델의 학습 표본과 평가 표본에 같은 (고객, 기준일) 쌍이 들어가지 않는다" · 명부 필드(역할 · 기준일 · cutoff · 라벨 창 · 데이터 버전 · 해시 · 관측 완전성) · 라벨 값 · 예측값은 넣지 않는다 | 행 단위 · 열 구성 |
| #317 `churn_temporal_compare.py`(광진, 승인 head `054c437`) | Feature Store 에서 (Feature, 라벨) 표 쌍을 기준일별로 읽고 `feature_cutoff_time` · `kind` · 라벨 attrs(`outcome_observation` · `label_window_complete` · `window_days` · `index_time`) · Feature attrs(`event_read_evidence` · 입력 메타데이터)를 대조한다. Train · Validation · Test 고객 목록과 기준일을 받고, 기준일이 있으면 Test 가 Train · Validation 고객과 겹칠 때 거부한다 | 저장할 표 이름 · 지문 · 속성. t_prior 표는 `run_sprint` 가 이미 만드는 표를 그대로 저장한다(속성 포함) |
| `run_sprint` 모집단(이 결정 전) | t1 학습 = Eligible(t1) 중 RCT T0 · Feature · 라벨, 시간 홀드아웃 = Eligible(t2) ∩ t1 무처치(T0 · 미배정) — 명부보다 **먼저** 돌아 과제 Test 후보의 t2 라벨까지 평가했다(#319 리뷰) | 명부 t1 · t2 정의의 출발점. 홀드아웃 범위와 실행 순서는 아래에서 고친다 |
| DR-221-observed-tiers | 기준일별 Eligible 에 관측 등급, 층화 키 가치 × 횟수 | 명부의 등급 열 · `stratum` |

## 결정

**행 = (customer_id, origin).** 기준일(`t_prior` · `t1` · `t2`)마다 그 기준일 Eligible 고객 전원을 싣고 `role` · `exclusion_reason` 을 적는다. 라벨 값 · 예측값은 싣지 않는다. 같은 (고객, 기준일)이 두 행이면 만들지 않고 멈춘다.

| 기준일 | 역할 | 정의 |
|---|---|---|
| t_prior | `train` | Feature · [t_prior, t1) 라벨이 있는 고객 |
| t1 | `validation` | 탐색 RCT T0 · Feature · [t1, t1+42) 라벨이 있는 고객(시간 순서 검증의 평가 · 최종 재학습) |
| t2 | `test` | t1 실험 무처치(T0 · 미배정)이고 train · validation 고객이 아닌 고객 — 과제 Test(ML-004) |
| t2 | `future_existing` | t1 실험 무처치인 train · validation 고객 — 기존 고객의 미래 시점 평가(DR-179), ML-004 에 쓰지 않는다 |
| 모두 | `excluded` | `rct_treated`(t1 에서 T1~T4) · `no_feature_or_label` |

- **t2 역할은 라벨을 보지 않고 정한다.** t2 라벨은 Feature Store 에도 저장하지 않는다 — GATE 3 동결 뒤 1회 평가 때 연다. 그때 라벨이 없는 test 고객은 수와 사유를 함께 적는다.
- 열: `customer_id` · `origin` · `role` · `exclusion_reason` · `rct_arm` · `observation_complete` · `n_events_before_cutoff` · 등급 4열 · `stratum`(가치 × 횟수) · 등급 근거 값 4열.
- `observation_complete` = 그 실행이 t2 까지 이벤트를 빠짐없이 읽었다는 근거(`event_read_evidence.t2.status = ok`). 거짓이면 `n_events_before_cutoff` 의 0 은 관측 불명이다.
- **저장:** 결과 폴더 `split_roster.csv`(파일 지문 포함), `run_meta.split_roster`(정의 · 기준일별 기준 시각 · 라벨 창 · 역할 · 제외 수 · 등급 경계 · 역할별 등급 분포 · 횟수 구간 점검 · Feature Store 표 지문 · 읽은 실행 ID). Feature Store 에 `features_t_prior` · `labels_t_prior`(앞 기준일 단계가 만든 표 그대로) · `observed_tiers_t_prior` · `observed_tiers_t1` · `observed_tiers_t2` 를 더한다.
- 데이터 버전 = 실행(`run_id`)이다 — 실행 머리말 · `run_meta` 의 시뮬레이터 판 · seed · 커밋과 함께 읽는다.
- 앞 기준일 단계가 not_run 이면 명부의 t_prior 만 not_run 이고, 그때 Test 는 t1 validation 고객만 뺀다 — 요약에 그 사유가 남고 과제 Test 후보는 `withheld` 다(아래). 정식 실행에서는 세 기준일이 모두 ok 여야 #317 에 넘긴다.
- **결과 단계가 아니다.** 명부 계산이 실패해도 다른 결과 파일은 그대로 쓰고 사유를 `run_meta.split_roster` 에 남긴다.

**실행 순서와 과제 Test 후보(2026-11-24 #319 리뷰 반영).**
- **명부는 t2 분기 결과를 읽기 전에 확정한다** — `run_sprint` 의 `scores_t2` 바로 뒤(`prepare_split_roster`). 전략 단계가 분기 결과(t2 라벨)를 읽는 것은 그 뒤다.
- **기존 시간 평가(`churn_temporal_holdout`)는 과제 Test 후보를 빼고 돈다** — 범위 = Eligible(t2) ∩ t1 실험 무처치 − 명부 t2 `test` = 기존 고객의 미래 시점 평가(DR-179, 명부 `future_existing`). 실제 평가 함수에 넘기는 고객을 `temporal_holdout_scope` 가 정하고, 뺀 수 · 평가된 후보 수(항상 0)를 `churn_eval.temporal_holdout.official_test_scope` 와 `run_meta.split_roster.official_test.temporal_holdout` 에 남긴다. 명부에 t2 역할이 없는 실행(`--mode evaluate` 등)은 뺄 후보를 모르므로 `official_test_known = false` 로 남긴다.
- **과제 Test 후보 상태 `official_test.status`.** `candidate` = 세 기준일이 모두 ok · t2 까지 관측 근거 ok · t2 분기 결과를 읽기 전에 만든 명부. 하나라도 아니면 `withheld` 와 사유 — 그 명부의 `test` 역할은 개발용이고 과제 Test 로 인수하지 않는다. 앞 단계 중단으로 명부를 `finally` 에서 늦게 만들었는데 그 전에 분기 결과를 읽었다면 `withheld` 다.
- **전략 분기 집계는 그대로 둔다.** S0~S5 분기의 이탈률 · 매출 집계(DR-234 — 모집단 Eligible(t2))는 모델 점수와 라벨을 맞춰 보는 평가가 아니라 전략 실험의 집계라 범위를 줄이지 않는다. 다만 S0 집계에 과제 Test 후보의 무처치 결과가 고객군 전체 비율로 섞인다는 것을 남긴다 — 모델 선택 · 임계값 · 앙상블 가중치에는 쓰지 않는다.

**과제 Test 동결 · 재동결(#218 회신에서 약속한 규칙).**
- GATE 3 에서 정식 seed 실행의 `candidate` 명부 하나를 동결한다 — `split_roster.csv` 지문 · `run_id` · seed · 시뮬레이터 판을 GATE 3 기록에 적는다. 그 seed 로 앞서 돈 실행이 있으면 그 실행들도 모두 `official_test_known = true` 여야 한다(아니면 그 seed 의 Test 후보 라벨이 이미 평가에 들어간 것이라 새 seed 를 쓴다).
- 동결한 Test 는 선택 동결 뒤 **1회** 평가한다. 그 결과를 보고 모델 · 임계값 · 전처리를 바꾸면 그 Test 는 "이미 본 Test" 라 독립 평가로 보고하지 않는다 — 바꾼 모델은 **새 seed 실행의 `candidate` 명부로 GATE 3 재동결**한 뒤 다시 1회 평가하고, 두 결과를 함께 적는다.
- Final Holdout(GATE 4)은 별도 seed 라 이 명부와 무관하다.

**근거:** 역할 정의는 Plan#6 에서 이미 정한 SPLIT-001 · 004 를 실행 산출물로 옮긴 것이다. Test 를 A 로 정한 것은 "최종 모델 학습 고객"에 앞 기준일 학습 고객도 들어가기 때문이다 — 하이퍼파라미터 · 앙상블 가중치를 그 고객으로 골랐다.

## 기각한 안과 기각 사유

| 안 | 왜 택하지 않았나 |
|---|---|
| 행 범위 B | 제외 사유 · 등급 분포를 보려면 Eligible 전원이 필요하다(DR-221 분포 점검의 분모가 Eligible 이다) |
| Test B | 앞 기준일에서 학습에 쓴 고객의 t2 시점이 Test 에 남아, 고객 분리라고 부를 수 없다 |
| Test C | 이미 `churn_temporal_holdout` 이 내는 평가다. ML-004 와 섞지 않고 `future_existing` 역할로 따로 둔다 |
| t2 라벨 B | GATE 3 전에 Test 라벨을 읽게 된다. 라벨 유무로 Test 고객을 고르는 것도 결과 의존이다 |
| 저장 B | Feature Store 저장은 선택(`--feature-store-root`)이라 명부가 없는 실행이 생긴다 |
| 명부에 라벨 · 예측값 포함 | 명부가 평가 파일이 되어 Test 라벨이 동결 전에 퍼진다 |
| 명부를 결과 단계 뒤에 만들고 "평가됨"만 표시 | 같은 실행 안에서 과제 Test 후보의 라벨이 개발용 지표에 이미 섞인다 — 표시로는 되돌릴 수 없다 |
| 명부 전용 실행 모드를 따로 둔다 | 실행이 두 번 필요하고, 같은 seed 의 다른 실행이 Test 후보 라벨을 평가하는 경로가 그대로 남는다. 한 실행 안에서 순서를 고정하고 평가 범위를 줄이는 편이 확인하기 쉽다 |

## 이 결정이 틀렸다면 어떻게 드러나나

- **Test 표본이 너무 작다:** 정식 실행에서 `test` 가 100명 미만이거나(라벨을 연 뒤) 적은 쪽 클래스가 10명 미만 → SRS SPLIT-004 대로 "판정 불가"와 사유를 적는다. 정의를 결과 뒤에 넓히지 않는다 — 넓히려면 GATE 3 전에 새 결정으로.
- **명부와 학습 단계가 어긋난다:** `t1` `validation` 수가 `churn_eval.n`(T0 학습 표본, 표본 상한 적용 전)과 다르다 → 명부 입력(라벨 있는 고객 판정)이 학습 단계와 다른 것이다.
- **상품군 입력이 비었다:** `t2` 묶음 품목이 없으면 모든 구매 고객의 `category_tier` 가 `UNKNOWN` 이다 → `inputs.order_items` 가 비어 있는지 본다.
- **#317 인수가 실패한다:** Feature Store 표의 속성 · 지문이 #317 의 대조와 다르면 그 차이를 이 기록에 추가 결정으로 적고 고친다.
- **과제 Test 후보가 평가에 새어 들었다:** `official_test.temporal_holdout.n_official_test_evaluated` 가 0 이 아니거나, 정식 실행의 `official_test.status` 가 `withheld` 다 → 그 실행의 명부를 과제 Test 로 쓰지 않고 원인(순서 · 입력)을 고친 뒤 새 seed 로 다시 만든다.

## 민감도

정의 선택이라 수치 모수가 없다. Test 크기는 "t1 에 Eligible 이 아니던 t2 Eligible 고객" 수에 달려 있고, 가입 시기 분포와 Eligible 기준(가입 60일 · 구매 1건 · 마지막 구매 14일)에 민감하다. 이 값들은 이미 봉인 대상이거나 확정이라 이 결정으로 바꾸지 않는다.

## 남은 불확실성

- **정식 실행 전이다.** 이 코드는 합성 입력 단위 시험과 CI 통합 시험으로만 확인했다. 첫 실행에서 기준일별 역할 수 · Test 크기 · 등급 분포(DR-221 횟수 구간 점검)를 본다 — 라벨 · 점수 없이.
- **LSTM 시퀀스는 명부에 없다.** #317 이 같은 실행의 관측 이벤트에서 만든다. 명부는 그 고객 · 기준일과 관측 완전성만 준다.
- **기존 시간 평가 표본이 줄어든다.** 과제 Test 후보를 빼면 시간 홀드아웃은 앞 기준일 · t1 에서 학습 · 검증에 쓴 고객의 t2 시점만 남는다. 개발 실행의 홀드아웃 지표는 이 결정 전과 바로 비교하지 않는다.
- **t1 묶음 대신 t2 묶음 품목을 쓴다.** t_prior · t1 등급의 상품군도 t2 묶음에서 그 창의 주문만 골라 쓴다 — 주문 ID 로 고르므로 기준일 뒤 주문은 들어가지 않는다(DR-221 의 창 규칙).
