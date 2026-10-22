<!-- 이슈 #144 (에픽 #142) 스프린트 1 모델 카드 초안. 리드 지시 파일명은 MC-churn-sprint.md 였으나
     tests/test_decision_records.py 가 파일명 두 번째 토큰을 태스크/이슈 번호로 요구해 MC-144-… 로 바꿨다. -->

# MC-144-churn-sprint — Churn 스프린트 1 (rule · LR · RF · HGB)

| | |
|---|---|
| 태스크 | 이슈 #144 (에픽 #142, D2 선행 스프린트) |
| 작성 | Claude (시스템 팀 에이전트) · 2026-10-22 |
| 커밋 | `d38de97` (feat/sprint1-predict, 평가 코드 시점) |

> ★ **이 카드의 모든 수치는 픽스처 기준이며 실제 결과가 아니다.** 픽스처는
> `tests/test_feature_sprint_table.py::make_events` 의 소형 합성 생성기(고객 300)이고, 시뮬레이터
> 코드를 참고하지 않았다. 실제 시뮬레이터 데이터 평가는 **미실행**이다(Phase 2 에서 오케스트레이션이 공급).

## 무엇을 예측하나

고객별 **이탈 확률** `churn_proba ∈ [0,1]` — T0(`index_time`) 이후 42일 안에 구매가 0 회일 확률.
`rule_recency` 는 확률이 아니라 마지막 구매 후 경과일의 학습 데이터 ECDF 순위 점수다.

## 어떤 결정에 쓰이나

리텐션 처치 대상 선별의 1 차 입력(이탈 위험 상위 고객). 처치 효과(Uplift)·CLV 와 결합하는 것은
D4·D7 이후이며 이 스프린트에서는 **선별 결정에 아직 쓰이지 않는다** — 발표용 평가 방법 제시가 목적이다.

## 데이터 계보

| | |
|---|---|
| 원천 | 합성 픽스처 `make_events(n_customers=300, days=240, seed=7)` — 측정 계약 22 컬럼·식별자 형식 준수 |
| 기간 | 2026-01-01 06:12 ~ 2026-08-28 23:57 KST |
| 고객 수 · 이벤트 수 | 300 · 85,009 |
| `index_date` (T0) | 2026-07-01 00:00 KST |
| Feature Cutoff | T0 − 1일 23:59:59 (구현: `timestamp < T0`) |
| 라벨 정의 | `churn = 1` ⇔ `[T0, T0+42일)` 구매 0 회. 관측이 창 끝까지 닿지 않으면 `build_outcomes` 가 거부 |

모집단은 T0 이전 관측 이벤트가 1 건 이상인 고객(`observed_only`). 양성 비율 0.38.

## 분할

| | 건수 | 비율 | 양성 비율 |
|---|---|---|---|
| Train | 240 (fold 당) | 80% | 0.38 (층화) |
| Validation | 60 (fold 당) | 20% | 0.38 (층화) |
| Test | 300 (시간 홀드아웃: T0−42일로 학습 → T0 고객 평가) | — | 학습 0.28 / 시험 0.38 |

**분할 기준:** 교차검증은 고객 단위 Stratified 5-Fold(무작위, seed=7). 고객 1 명 = 1 행이라 같은 고객이
한 fold 안에서 양쪽에 걸치지 않는다. 시간 홀드아웃은 같은 고객의 **다른 시점**이다 — 학습 라벨 창
`[T0−42, T0)` 이 시험 Feature cutoff(T0) 에서 끝나므로 미래 정보가 넘어가지 않는다.

**Final Holdout 을 무엇에 썼나:** 쓰지 않았다. 픽스처에는 Final Holdout 이 없다. 시간 홀드아웃 값은 형식 확인용 1 회 실행이다.

**무엇에 쓰지 않았나:** 하이퍼파라미터 선택 · 임계값 선택 · 모델 선택 · 전략 선택 · 예산 정책 — 전부
시험/홀드아웃을 쓰지 않았다. F1 임계는 학습 fold 내부 3-fold OOF 에서, 모델 선택(`best_proposed`)은 CV 평균
ROC-AUC 로 했다. ★ CV 로 모델을 고른 뒤 같은 CV 수치를 보고하므로 **선택된 모델의 CV 수치는 낙관 편향**이 있다.

## 학습

| | |
|---|---|
| 알고리즘 | baseline: `rule_recency`(경과일 임계) · `logistic_regression` / proposed: `random_forest` · `hist_gb` |
| 하이퍼파라미터 | LR C=0.5 · RF 300 trees, min_samples_leaf=3 · HGB lr=0.05, 300 iter, 15 leaves, l2=1.0 |
| **무엇으로 골랐나** | 고르지 않았다 — 일반적 기본값을 한 번 정했고 픽스처 성능을 보며 바꾸지 않았다 |
| 탐색 범위·횟수 | 0 회 (탐색 없음) |
| 불균형 처리 | `class_weight=balanced`(LR·HGB) · `balanced_subsample`(RF), 판정은 F1 최대 임계. 리샘플링 없음 |

전처리(`make_preprocessor`): 학습 fold 분위 1%·99% 절단 → 중앙값 대치 + 결측 지시자. 학습 fold 로만 fit.

## ★ 누수 점검

| 확인한 것 | 어떻게 | 결과 |
|---|---|---|
| 금지 Feature 부재 (`treatment_*` · `experiment_id` · 파생 상태 · persona) | `test_forbidden_inputs_are_ignored`: 배정 필드·`churn` 이벤트를 넣어도 테이블 동일 | 통과 |
| Feature Cutoff 준수 | `test_no_future_leakage`: T0 이후 이벤트를 지워도 테이블 동일. GRU 시퀀스도 같은 검사 | 통과 |
| 고객 단위 분할 | 1 고객 1 행, `StratifiedKFold` 행 단위 = 고객 단위 | 통과 |
| 라벨 동어반복 (라벨을 거의 결정하는 단일 Feature) | `recency` 단독 규칙의 CV ROC-AUC 0.724 — 라벨을 결정하지 않는다 | 해당 없음(픽스처 기준) |

## 성능

픽스처 기준, 실제 결과 아님. Stratified 5-Fold mean ± std (seed=7).

| 지표 | Train | Validation | Test | 신뢰구간 |
|---|---|---|---|---|
| ROC-AUC rule_recency (baseline) | 미산출 | 0.724 ± 0.093 | 0.725 (시간 홀드아웃) | 판정 불가 (n=300) |
| ROC-AUC logistic_regression (baseline) | 미산출 | 0.788 ± 0.008 | 0.778 | 판정 불가 |
| ROC-AUC random_forest (proposed) | 미산출 | 0.817 ± 0.052 | 미실행 | 판정 불가 |
| ROC-AUC hist_gb (proposed) | 미산출 | 0.820 ± 0.029 | 0.774 | 판정 불가 |
| PR-AUC rule / LR / RF / HGB | 미산출 | 0.641 / 0.752 / 0.788 / 0.774 | — | 판정 불가 |
| F1 rule / LR / RF / HGB | 미산출 | 0.584 / 0.620 / 0.690 / 0.682 | 0.591 / 0.639 / — / 0.661 | 판정 불가 |
| Lift@10% rule / LR / RF / HGB | 미산출 | 2.02 / 2.46 / 2.55 / 2.55 | 2.02 / 2.37 / — / 2.19 | 판정 불가 |

fold 5 개 · 고객 300 명이라 제안 모델과 LR 의 차이(0.03 내외)가 std 안에 있다 — **우열은 판정 불가**다.
GRU(`churn_dl.py`, 같은 fold)는 고객 300 픽스처 1 회 실행에서 ROC-AUC 평균 0.819 였다(torch 설치 환경, 선택 의존성).

## 해석

SHAP(TreeExplainer, hist_gb) 상위: `page_view_count_60d` · `monetary_90d` · `visit_recency` ·
`morning_activity_ratio` · `distinct_viewed_products_180d`. 최근 활동량·금액이 위에 오는 것은 말이 된다.
`morning_activity_ratio` 가 4 위인 것은 픽스처 생성기가 시간대를 고객과 무관하게 뽑으므로 **설명할 수 없다** —
고객 300 명 표본의 잡음으로 보며, 실제 데이터에서 다시 보아야 한다.

## 실패 모드

- 관측 기간이 180일보다 짧으면 180일 창 Feature 가 불완전하다 → `attrs["incomplete_windows"]` 를 먼저 본다.
- 신규 고객(구매 이력 없음)은 `recency`·간격 Feature 가 NaN → 대치값+지시자로만 판단한다. 신규 고객군 성능은 따로 재야 한다.
- 이탈 정의(42일)·쿠폰 운영 방식이 바뀌면 재학습한다. 시점이 다른 데이터에서 양성 비율이 0.28 → 0.38 로 움직였듯 확률 보정은 시점마다 다시 본다.
- D1 정본 Feature(`calculate_features`)와 값이 다를 수 있다 — 정합은 #150.

## 재현

```bash
pip install -r requirements.txt -r requirements-ml.txt
python -m unittest tests.test_feature_sprint_table tests.test_churn_sprint tests.test_clv_sprint -v
# 카드 수치: make_events(300) → build_feature_table/build_outcomes(T0=2026-07-01) → evaluate_churn_models(seed=7)
```

| | |
|---|---|
| 시드 | 7 (픽스처·CV·모델) |
| 소요 | 카드 수치 전체(CV 4 모델 + 시간 홀드아웃 3 + CLV) 약 96 초, Apple Silicon |
| 환경 | Python 3.12 · numpy 2.5.4 · pandas 3.0.6 · scikit-learn 1.9.1 · scipy 1.18.1 · shap 0.54.1 · torch 2.14.1 |
