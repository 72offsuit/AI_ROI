# MC-215-churn-ml — Churn 모델 비교판 (rule · LR · RF · HGB · XGBoost · LightGBM, 튜닝 · 시간 순서 검증)

| | |
|---|---|
| 태스크 | 이슈 #215 (SRS FR-14 · ML-005 · ML-006 · FR-16) |
| 작성 | 시스템 팀 리드(인성) 구현 에이전트 · 2026-11-13 |
| 커밋 | `feat/215-churn-tuning` 의 첫 커밋(이 카드와 같은 커밋). 동결 모델의 커밋은 GATE 3 실행 기록 `run_meta.provenance.repo_commit` |

> 이 카드는 **구성 · 고르는 규칙 · 누수 점검**을 기록한다. 실제 성능 수치는 실행 결과 파일(`churn_eval.json`)에만 있다 —
> 이 문서는 두 팀이 함께 읽는 위치라 모델 성능을 적지 않는다(시뮬레이터 팀은 결과를 보지 않는다).

## 무엇을 예측하나

고객별 **이탈 확률**(0~1) — 기준 시각 T0 이후 42일 동안 한 번도 사지 않을 확률. 이진 판정(`predicted_label`)은 F1 최대 임계(1부 `DR-215-churn-evaluation.md`).

## 어떤 결정에 쓰이나

전략 S2(이탈 확률 순서로 예산까지 쿠폰) · S3(이탈 확률 × 쿠폰 효과) 의 고객 순서, 세그먼트 4분면의 위험 축, 대시보드 위험 분포 · Target List(SHAP Local 로 "왜 이 고객인가"). 임계는 지출을 정하지 않는다 — 대상 수는 예산이 정한다.

## 데이터 계보

| | |
|---|---|
| 원천 | 시뮬레이터 공개 API 이벤트(측정 계층 계약) — 이 저장소 실행 루프가 읽는다. 시뮬레이터 내부 · 정답 파일은 읽지 않는다 |
| 기간 | 워밍업(기본 312일) → t1 → 탐색 RCT 42일 → t2 |
| 고객 수 · 이벤트 수 | 실행 기록 `run_meta.rct` · `churn_eval.n` (실행마다 다르다) |
| `index_date` (T0) | 학습 = t1, 시간 순서 검증의 앞 기준일 = t1 − 42일, 시간 홀드아웃 = t2 |
| Feature Cutoff | T0 미만(`timestamp < T0`, D1 `[·, T0)`) |
| 라벨 정의 | T0 이후 42일 무구매 = 1. 앞 기준일 라벨 창 [t1−42, t1) 은 워밍업 안(처치 없음) |

## 분할

| | 건수 | 비율 | 양성 비율 |
|---|---|---|---|
| Train | t1 Eligible ∩ RCT T0 군(`churn_eval.n`) | 실행마다 | `churn_eval.pos_rate` |
| Validation | 시간 순서: 앞 기준일 Eligible 로 학습 → Train 고객으로 평가(`prior_origin.n`). 보조: Train 안 5겹 교차검증 | 실행마다 | `models[].temporal_validation.pos_rate_*` |
| Test | 시간 홀드아웃 — Eligible(t2) ∩ t1 무처치, S0 분기 42일(`temporal_holdout.n_test`) | 실행마다 | `temporal_holdout.pos_rate_test` |

**분할 기준:** 시간 기준. 앞 기준일 → t1 → t2 순서로 학습 · 검증 · 시험. 같은 고객이 여러 기준일에 다시 나올 수 있다 — 고객이 아니라 **시점**으로 나눈 것이고, 실제 운영(과거 고객으로 학습 → 같은 고객의 미래 예측)과 같은 방향이다. `temporal_population_audit` 이 겹침 수를 적는다.
**Final Holdout 을 무엇에 썼나:** 쓰지 않았다 — GATE 4(#226)에서 동결 모델을 새 seed 에 1회 적용한다(#214 `--load-models`).
**무엇에 쓰지 않았나:** 시간 홀드아웃(t2)과 Final Holdout 을 하이퍼파라미터 선택 · 임계값 선택 · 모델 선택 · 전략 선택 · 예산 정책에 **쓰지 않았다**. 튜닝 · 모델 선택은 Validation(시간 순서 검증)만 봤다.

## 학습

| | |
|---|---|
| 알고리즘 | 기준선: 최근 구매 경과일 규칙 · 로지스틱 회귀. 제안: 랜덤 포레스트 · HistGradientBoosting · XGBoost 3.4.1 · LightGBM 4.7.0 — 모두 같은 전처리(분위 절단 · 중앙값 대치 + 결측 지시자) 안에서 |
| 하이퍼파라미터 | `config/model_config.yaml churn.models` 기본값 위에 튜닝 값(`churn_eval.best_params`)을 덮는다 |
| **무엇으로 골랐나** | Validation — 앞 기준일 학습 → t1 평가 ROC-AUC. 없으면 t1 안 3겹 교차검증(`selection_basis` 에 적힌다). Test 를 보며 조정하지 않았다 |
| 탐색 범위·횟수 | Grid `churn.tuning.grids` — RF 3 · HGB 6 · XGBoost 6 · LightGBM 4 조합(19회). 격자 전체 점수를 `models[].tuning.grid` 에 남긴다 |
| 불균형 처리 | LR · RF · HGB · LightGBM 은 class_weight(balanced), XGBoost 는 가중 없음(이탈 비율 50% 안팎). 확률이 실제보다 높게 나올 수 있어 보정 지표(Brier · ECE)를 함께 낸다 |

## ★ 누수 점검

| 확인한 것 | 어떻게 | 결과 |
|---|---|---|
| 금지 Feature 부재 (`treatment_*` · `experiment_id` · 파생 상태 · persona) | `sprint_table` 이 읽지 않는 필드 목록 · `make_risk_model_factory` 의 금지 Feature 검사 · `tests/test_isolation.py` | 통과(기존 검사 유지) |
| Feature Cutoff 준수 | 세 기준일 모두 같은 `build_feature_table(events, T0)` — T0 미만만 | 통과(구조상) |
| 고객 단위 분할 | 시점 분할이라 고객이 겹칠 수 있다 — 의도된 설계, 겹침 수를 audit 에 기록 | 해당 없음(시점 분할) |
| 라벨 동어반복 (라벨을 거의 결정하는 단일 Feature) | 기준선 규칙(경과일 하나)의 점수를 함께 보고한다 — 제안 모델이 규칙과 거의 같으면 의심한다 | 실행마다 비교(`models[]`) |
| 튜닝 · 선택의 시험 데이터 사용 | `tune_model` · `selection_score` 는 Validation 만 받는다. 시간 홀드아웃은 확정 모델 1회 평가 | 통과(`tests/test_churn_tuning.py`) |

## 성능

| 지표 | Train | Validation | Test | 신뢰구간 |
|---|---|---|---|---|
| ROC-AUC · PR-AUC · F1 · Lift@10 · Brier · ECE (6 모델) | 미산출 — 이 카드에 싣지 않음 | 실행 결과 `churn_eval.models[].temporal_validation` · `cv` | 실행 결과 `churn_eval.temporal_holdout` | 판정 불가 — 한 번 실행. seed 반복(#220)으로 낸다 |

실제 수치는 GATE 3 동결 실행의 `churn_eval.json` 에 있다(시스템 팀 열람). 합성 데이터 시험(`tests/test_churn_tuning.py`)은 규칙 검증용이라 성능 근거가 아니다.

## 해석

상위 Feature 는 확정 모델의 SHAP(1부: `shap_summary.png` · `shap_top` · 고객별 `shap_local`)으로 본다. 최근 구매 경과일 · 구매 빈도 같은 행동 Feature 가 위에 오는 것이 자연스럽고, 설명할 수 없는 Feature 가 맨 위에 오면 누수부터 의심한다.

## 실패 모드

- 앞 기준일과 t1 의 고객 구성이 크게 다르면(신규 유입 급증 등) 시간 순서 검증이 대표성을 잃는다 — 시간 홀드아웃과 함께 본다.
- 보정이 크게 어긋나면(높은 ECE) 확률 값 자체를 쓰는 계산(S4 기대 이익)이 치우친다 — 순서만 쓰는 S2 는 영향이 작다.
- 시뮬레이터 판이 바뀌면(GATE 1 재봉인) 처음부터 다시 학습한다(FREEZE-003). Feature 소스가 바뀌면 저장 모델을 불러오지 않는다(#214 feature_version 대조).

## 재현

```bash
pip install -r requirements.txt
python src/main.py --mode train --seed 42            # 튜닝 · 시간 순서 검증 · 확정 모델 → models/{run_id}/
python -m unittest tests.test_churn_tuning tests.test_churn_evaluation tests.test_churn_sprint
```
