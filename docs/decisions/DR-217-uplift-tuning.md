# DR-217-uplift-tuning — Uplift 기저 학습기 규제를 실행 데이터의 Validation Qini 로 고른다 (사전 고정)

| | |
|---|---|
| 태스크 | 이슈 #217 3부 (부모 #171) — Uplift HistGB 규제를 실데이터 Validation 으로 · Lenta 실행 · Hillstrom 재검. DR-206 이 미룬 Uplift 상수 4개의 config 이전 |
| 작성 | 시스템 팀 리드(인성) 구현 에이전트 · 2026-11-14 |
| 상태 | **사전 고정(결과 전)** — 이 절의 격자 · 선택 규칙 · 외부 검증 설정은 어떤 튜닝 · 외부 검증 결과도 보기 전에 커밋했다. 결과는 아래 「결과」 절에 덧붙이고, 위 내용을 바꾸면 그 사실과 사유를 함께 적는다 |

## 이 기록을 먼저 고정하는 이유 — 작성 세션의 경계 노출

2026-11-14 이 작업을 시작하며 작성 에이전트의 저장소 검색(`git grep`)에 금지 문서의 줄 일부가 출력됐다(`DR-194-population.md` · `DR-196-sleeping-dog-path.md` · `data_grounding.md` §2 — 생성 모수와 시뮬레이터 쪽 처치 효과 값의 종류, 값은 옮겨 적지 않는다. 기록: #163 코멘트 2026-11-14). 그 정보는 처치 효과 이질성과 직접 관련이 있다.

그래서 이 3부는 **사람(작성자)의 판단이 결과에 끼어들 자리를 없앤다.**
- 격자 · 선택 규칙 · 외부 데이터의 처치 · 결과 · 특성 정의를 결과를 보기 전에 이 문서로 고정한다.
- 선택은 규칙이 자동으로 한다. 특성(Feature) · 메타러너 구조 · 분할은 바꾸지 않는다 — 규제 강도만 고른다.
- 노출 정보는 어떤 코드 · 설정 · 판단에도 쓰지 않는다. 리뷰 광진.

## 무엇을 정하는가

1. Uplift 메타러너(S/T/X)의 기저 학습기(HistGradientBoostingRegressor) 규제를 어떻게 정할 것인가. 지금 값(깊이 3 · 잎 최소 80 · L2 3 · 학습률 0.03 · 200 회)은 **테스트용 합성 3,000 건**에서 고른 값이다(DR-145).
2. 그 절차가 실데이터에서 어떤지 무엇으로 보일 것인가(Lenta 첫 실행 · Hillstrom 재검).
3. DR-206 이 "#179 병합 뒤 옮긴다"고 미룬 Uplift 상수 4개(`BASE_LEARNER` · `MIN_ARM_N` · `VALIDATION_SIZE` · `DEFAULT_PRIMARY_ARM`)를 config 로 옮긴다.

## 정하지 않으면 무엇이 막히나

- S3 · S4 · S5 의 대상 선정이 쓰는 고객별 τ̂ 이 합성 3,000 건에서 고른 규제로 나온다 — 50K 실행의 처치군 크기(수천 명)에 맞는지 확인한 적이 없다.
- GATE 3(11/27 모델 동결) 뒤에는 규제를 바꿀 수 없다. Final Holdout(GATE 4)은 동결한 모델을 불러와 채점한다.
- Lenta 실행 · Hillstrom 재검이 없으면 "실데이터에서 Uplift 모델이 무작위보다 나은가"에 Sprint 1 보고(고정 하이퍼파라미터) 말고는 근거가 없다.

## 조사한 것

| 출처 | 무엇을 말하나 | 우리 맥락에 얼마나 맞나 |
|---|---|---|
| DR-145 · `uplift.py` 주석 | 현행 규제는 테스트 합성 3,000 건에서 3 안을 비교해 골랐다. 더 약한 규제(잎 15 · 최소 20)는 그 데이터에서 T-learner Qini 가 음수까지 떨어졌다 | 규제가 Qini 를 크게 흔든다는 근거 — 그러나 고른 데이터가 프로젝트 데이터가 아니다 |
| DR-206 「옮기지 않은 상수」 | Uplift 상수 4개는 #179 와 충돌을 피하려 config 이전을 미뤘다 | 이번에 옮긴다 |
| DR-215-churn-tuning(#215) | Churn 은 Validation 만으로 격자 튜닝, Test 는 보고만 | 같은 원칙 · 같은 config 형태(`tuning.enabled · grid`)를 따른다 |
| `docs/sprint1_report.md` 외부 검증 | 고정 하이퍼파라미터로 X5 Qini 0.0114, Hillstrom 이메일 · 방문 Qini 0.004~0.005, 남성 메일 · 구매 전환은 무작위보다 낫다고 말할 수 없음 | 재검의 비교 기준 — 같은 처치 · 결과로 다시 잰다 |
| `docs/research/raw_uplift.md` | Hillstrom 방문율 18.28 · 15.14 · 10.62%, Lenta 응답률 11.01 · 10.26% — 원자료 직접 집계 | 내려받은 파일의 무결성 확인 기준 |
| Künzel et al. (2019) | X-learner 는 처치군 크기가 불균형할 때 T-learner 보다 낫다 | 메타러너 후보는 지금 그대로(T · X) |

## 선택지

| 안 | 내용 | 장점 | 단점 |
|---|---|---|---|
| A | 실행마다 탐색 RCT 의 train 안 Validation(25%) Qini 로 **(메타러너 × 규제 격자)** 를 함께 고른다 | 그 실행의 데이터 크기 · 잡음에 맞춘다. Test 를 보지 않는다(지금 메타러너 선택과 같은 분할) | 후보가 늘어 학습 시간이 는다. Validation 한 분할의 잡음으로 고를 수 있다 |
| B | 외부 데이터(Lenta)로 한 번 고른 값을 고정 | 실행이 빠르다 | 데이터 크기 · 결과 기저율이 다른 곳에서 고른 값이다 |
| C | 지금 값 유지 | 변경 없음 | 합성 3,000 건에서 고른 값 — 이슈가 지적한 그대로 |

## 사전 고정 — 결정

**안 A.** 값은 `config/model_config.yaml` `uplift` 에만 둔다.

```yaml
uplift:
  min_arm_n: 30              # 지금 MIN_ARM_N 그대로
  primary_arm: T3            # PRD §15.1 — 지금 DEFAULT_PRIMARY_ARM 그대로
  validation_size: 0.25      # 지금 VALIDATION_SIZE 그대로
  base_learner:              # 지금 BASE_LEARNER 그대로(= 격자의 현행값)
    max_iter: 200
    learning_rate: 0.03
    max_depth: 3
    min_samples_leaf: 80
    l2_regularization: 3.0
  tuning:
    enabled: true
    metric: qini
    grid:                    # base_learner 위에 덮어쓰는 축 — 곱집합 6 개
      max_depth: [2, 3]
      min_samples_leaf: [40, 80, 200]
```

**후보와 순서.** 후보 = 제안 메타러너(`t_learner` · `x_learner`, 이 순서) × 규제 설정. 규제 설정 순서는 **현행값(base_learner 그대로)이 첫째**, 나머지는 격자 곱집합을 축 이름 순 · 값 순으로(현행값과 같은 조합은 한 번만). `s_learner` 는 지금처럼 Baseline 이고 선택 후보가 아니다.

**선택 규칙.**
1. 분할은 지금 그대로 — 탐색 RCT 를 train/test 70/30(처치군 층화, `seed`), train 을 다시 fit/Validation 75/25(`seed + 1`).
2. 후보마다 fit 분할로 학습, Validation 의 대표 처치군(T3; 외부 데이터는 T1) Qini 를 잰다.
3. Validation Qini 최대인 (메타러너, 규제)를 고른다. **같으면 후보 순서가 앞선 것**(현행값 · t_learner 쪽). 계산 불가(None) 후보는 고르지 않는다. 모두 계산 불가면 지금처럼 `best_method = None`.
4. Test 분할은 선택에 쓰지 않는다. Test 의 모델 행(random · 위험도 · S/T/X)은 **고른 규제**로 학습해 보고한다. 비교용으로 고른 메타러너의 **현행값 규제** Test 지표를 함께 보고만 한다(선택에 쓰지 않는다).
5. 최종 모델(전체 탐색 RCT 재학습)은 고른 메타러너와 고른 규제로 학습하고, 모델 객체에 그 규제를 남긴다(`UpliftModel.base_learner`).
6. `tuning.enabled: false` 이면 현행값 하나만 — 지금 동작과 같다.

**외부 검증(사전 고정).** `evaluate_on_benchmark` 에 같은 절차(같은 격자 · 같은 규칙)를 그대로 쓴다. 하이퍼파라미터를 결과를 보고 바꾸지 않는다.

| 데이터 | 처치 | 결과 | 특성 | seed |
|---|---|---|---|---|
| Hillstrom (scikit-uplift 미러 `hillstorm_no_indices.csv.gz`) | 메일 발송(남 · 여) vs `No E-Mail` | `visit` | 원자료 공변량 8개 그대로: `recency · history_segment · history · mens · womens · zip_code · newbie · channel` | 0 · 1 · 2 |
| Hillstrom (같은 파일) | `Mens E-Mail` vs `No E-Mail` | `conversion` | 같은 8개 | 0 · 1 · 2 |
| Lenta (`lenta_dataset.csv.gz`) | `group` = `test` vs `control` | `response_att` | `group` · `response_att` 를 뺀 원자료 열 전부, 가공 없음 | 0 |

- Hillstrom 두 행은 Sprint 1 보고(고정 하이퍼파라미터)와 같은 처치 · 결과 — 재검이다.
- 내려받은 파일은 저장소 밖(scratchpad)에 두고 커밋하지 않는다. 결과(집계 지표 JSON)만 `docs/research/computed/` 에 남긴다.
- Hillstrom 무결성 확인: 행 수 64,000 · 처치군별 방문율이 `raw_uplift.md` 표(18.28 · 15.14 · 10.62%)와 같아야 실행한다.
- Lenta 무결성 확인: 처치 · 대조 응답률이 `raw_uplift.md` 표(11.01 · 10.26%)와 같아야 실행한다.

**보고할 것(결과 절).** 데이터마다 Validation 격자 점수 전부, 고른 (메타러너, 규제), Test Qini · AUUC · uplift@10/30 — 고른 규제와 현행값 규제 나란히, 학습 시간. 해석 규칙도 미리 정한다: 고른 규제의 Test Qini 가 현행값보다 낮은 데이터가 있으면 그대로 적는다(Validation 한 분할 선택의 잡음 한계) — 그것을 보고 격자나 규칙을 바꾸지 않는다.

## 기각한 안과 기각 사유

| 안 | 왜 택하지 않았나 |
|---|---|
| B(외부에서 한 번 고정) | 외부 데이터는 결과 정의 · 규모가 다르다 — 그곳의 최적이 우리 실행의 최적이라는 근거가 없다. 외부는 절차의 검증에 쓴다 |
| C(현행 유지) | 이슈 #217 이 지적한 합성 데이터 기반 값 그대로다 |
| 더 큰 격자 · 학습률 축 | 후보가 늘수록 Validation 한 분할에서 운으로 이기는 후보가 생긴다(선택 잡음). 규제 강도 두 축만 둔다 |
| 반복 분할 평균으로 선택 | 학습 시간이 분할 수만큼 는다. 지금 메타러너 선택과 같은 한 분할을 유지한다 — 한계로 적는다 |

## 이 결정이 틀렸다면 어떻게 드러나나

- 외부 데이터에서 고른 규제의 Test Qini 가 현행값보다 일관되게 낮다 → Validation 한 분할 선택이 잡음을 고르고 있다.
- 실행마다 고른 규제가 크게 흔들린다(같은 세계 · 다른 seed) → 같은 해석.
- uplift 단계 시간이 실행 예산을 넘는다 → `tuning.enabled: false` 로 현행값만 쓰고 기록한다.

## 민감도

- 해당 없음 — 외부 데이터 Hillstrom 은 seed 3 개로 선택의 흔들림을 본다.

## 남은 불확실성

- 노출 정보가 이 문서의 격자 설계에 영향을 줬는지는 작성자가 스스로 증명할 수 없다. 격자는 규제 강도(깊이 · 잎 최소 크기) 두 축이고 특성 · 고객군 정의를 건드리지 않는다는 점, 그리고 리뷰어(광진)의 확인으로 갈음한다.

## 결과

(외부 검증 · 실행 결과는 여기에 덧붙인다 — 사전 고정 커밋 뒤)
