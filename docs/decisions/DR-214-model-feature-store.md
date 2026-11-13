# DR-214-model-feature-store — 모델 · Feature 를 파일로 남기고, 다른 seed 실행이 다시 학습 없이 불러와 평가한다

| | |
|---|---|
| 태스크 | 이슈 #214 (SRS ML-008 · FS-001 · FS-002 · PRD NFR-01, 부모 #184 잔여 · DR-206 이 미룬 것) |
| 작성 | 시스템 팀 리드(인성) 구현 에이전트 · 2026-11-13 |
| 상태 | 확정 |

## 무엇을 정하는가

1. 학습한 Churn · Uplift · CLV 모델을 **어디에, 어떤 형식으로, 어떤 메타데이터와 함께** 남기는가(ML-008).
2. Feature 를 어디에 남기고 행마다 무엇을 붙이는가(FS-001 · FS-002).
3. NFR-01 의 버전 8종(service · simulator · customer_seed · random_seed · feature · model · strategy · experiment)을 무엇으로 재는가.
4. 저장한 모델을 **다른 seed 데이터에 다시 학습 없이** 적용하는 경로(이슈 완료 조건 · GATE 4 Final Holdout 전제).

## 정하지 않으면 무엇이 막히나

GATE 4 Final Holdout(#226)은 **동결한 모델을 새 seed 에 한 번** 적용하는 것이다. 지금은 프로세스가 끝나면 모델이
사라지고(DR-206 B2 기각 · `main.py` `NOT_PERSISTED`), 모든 실행이 다시 학습하므로 "동결한 모델"이 존재하지 않는다.
GATE 3 모델 동결(11/27)도 저장된 모델이 있어야 무엇을 동결했는지 말할 수 있다.

## 선택지

| 안 | 내용 | 장점 | 단점 |
|---|---|---|---|
| A | pickle(표준 라이브러리) + 종류별 JSON 메타데이터 + SHA-256 대조, 실행마다 `models/{run_id}/` | 추가 의존성 없음. 우리 모델 객체(데이터클래스 + sklearn)를 그대로 담는다. 메타데이터로 "어떤 모델인가"를 말한다 | pickle 은 불러올 때 코드를 실행한다 → 이 저장소가 쓴 파일만, 해시 대조 뒤에 연다. sklearn 판이 다르면 경고 |
| B | joblib | 큰 numpy 배열에 효율적 | 내부가 pickle 이라 A 의 위험이 같다. 이득(크기)은 우리 모델 규모에서 작다 |
| C | skops · ONNX 같은 안전 형식 | 불러올 때 코드 실행이 없다 | 의존성 추가. `ChurnModel` · `UpliftModel` 같은 우리 데이터클래스와 사용자 정의 변환기를 그대로 담지 못해 변환 계층이 필요하다 — 스프린트 기한 안에 검증 불가 |
| D | 저장하지 않고 같은 seed 로 다시 학습(현행) | 바꿀 것 없음 | GATE 4 를 할 수 없다. 재학습 결과가 같다는 것은 seed 재현성에 기댈 뿐, 동결의 증거가 아니다 |

Feature: parquet(pandas · pyarrow, 이미 requirements) + `manifest.json`. CSV 는 dtype 과 결측(NaN)을 잃는다.

## 조사한 것

| 출처 | 무엇을 말하나 | 우리 맥락에 얼마나 맞나 |
|---|---|---|
| SRS ML-008 (`Plan/AI_Customer_Retention_ROI_SRS_v2.0.md`) | `models/churn_xgboost_v1.pkl` 같은 파일 + `model_version · dataset_version · feature_version · parameters · cv_score · test_score · created_at` | 형식(pkl)과 메타데이터 키를 그대로 따랐다. 파일 이름은 실행 폴더 안의 `churn.pkl` 로 두고 버전은 메타데이터에 적는다 — 실행 단위로 묶어야 "같이 학습된 세 모델"이 보존된다 |
| SRS FS-001 · FS-002 | File-based Feature Store 권장, 행 메타 `customer_id · feature_version · feature_cutoff_time · generated_at` | 그대로 따랐다. cutoff 는 우리 Feature 규칙(T0 **미만** 이벤트)과 맞게 "미만"이라고 manifest 에 적는다 |
| PRD NFR-01 (`Plan/AI_Retention_ROI_PRD_v2.md`) | 버전 8종 기록 | 4종(service = 저장소 커밋 · simulator_version · seed 둘)은 이미 실행 기록에 있다. 나머지를 `src/decision/versions.py` 로 정했다 |
| Python 문서 `pickle` 경고 | 신뢰하지 않는 데이터를 unpickle 하지 말 것 | 그래서 메타데이터의 SHA-256 과 바이트가 같을 때만 연다. 남이 건넨 파일을 여는 경로는 만들지 않았다 |
| 저장소 코드 대조(이번 작업) | `make_preprocessor` 안의 지역 클래스 `QuantileClipper` 때문에 Churn · CLV 파이프라인이 **pickle 되지 않는다** (`Can't pickle local object`) | 결함으로 기록하고 고쳤다 — 아래 "결정" 4 |

## 결정

1. **모델 = 안 A.** `src/decision/model_store.py`. `{models_root}/{run_id}/{kind}.pkl` + `{kind}.json` + `manifest.json`.
   - 메타데이터: ML-008 7개 키 + `sha256 · bytes · libraries(python · numpy · pandas · sklearn · scipy) · score_notes · run_id · method · training_rows`.
   - `model_version = {kind}-{method}-{run_id}`, `dataset_version = rct-t1-{학습 데이터 지문 12자리}`.
   - `cv_score` = 그 실행의 학습 데이터 안 검증(Churn 교차검증 평균 · Uplift 검증 분할 Qini · CLV OOF). `test_score` = 학습 · 선택에 쓰지 않은 데이터(Churn 시간 홀드아웃 · Uplift RCT test 분할). CLV 는 아직 없어서 null 과 사유. **Final Holdout 점수는 여기에 쓰지 않는다.**
   - 같은 폴더에 다시 쓰지 않는다(덮어쓰기 거부). 불러올 때 SHA-256 이 다르면 거부.
2. **Feature = parquet.** `src/decision/feature_store.py`. `{feature_store_root}/{run_id}/features_t1 · labels_t1 · features_t2.parquet`, 행마다 FS-002 4열, manifest 에 모양 · 지문 · attrs. 다시 읽으면 값 · 결측 · attrs 가 그대로다(재방문 입력 메타데이터가 attrs 에 있어 모델 입력 검사에 필요).
3. **NFR-01 = 소스 해시.** `src/decision/versions.py` — feature(`sprint_table.py` · `return_visit.py`) · strategy(`strategies.py` · `optimize.py`) · experiment(`config/experiment_config.yaml`) 버전은 정의 파일 바이트의 SHA-256 앞 12자리. `run_meta.versions` 에 8개 키를 모두 싣고 모르는 값은 null.
4. **결함 수정 — `QuantileClipper` 를 모듈 이름으로 등록.** 계산은 그대로 두고, 클래스를 한 번만 만들어 `sprint_table.QuantileClipper` 로 보이게 했다(PEP 562 `__getattr__`). sklearn import 는 여전히 지연이라 의존성 없는 격리 CI 에서도 모듈을 import 할 수 있다. 파이프라인 단계 이름(`quantileclipper`)도 같다.
5. **다시 학습 없이 평가.** `--load-models {models_root}/{run_id}` 이면 churn · uplift · clv 단계가 학습 대신 불러오고, `evaluate_fitted_churn · evaluate_fitted_uplift · evaluate_fitted_clv` 로 이 실행의 데이터에 **평가만** 한다(임계 · 방법 · Feature 모두 저장된 그대로). 시뮬레이션 **전에** 불러와 확인하고, 없거나 바뀌었거나 저장 당시 feature_version 이 지금 코드와 다르면 종료 코드 6 으로 멈춘다. 일부 종류만 있으면 없는 종류는 학습하지 않고 not_run 이다(섞지 않는다).
6. **기본값.** `src/main.py` 는 기본으로 저장한다(`models/` · `data/processed/`, 둘 다 .gitignore). `--no-persist` 로 끈다. `run_sprint` 모듈 CLI 와 `SprintConfig` 는 기본이 "저장 안 함"이라 기존 호출의 동작이 같다. 저장을 요청했는데 실패하면 종료 코드 1 — 조용히 넘어가지 않는다.

**근거:** 완료 조건(다른 seed 데이터에 불러 평가만)을 의존성 추가 없이 만족하는 안은 A 뿐이다. 소스 해시는 Feature 정의가 바뀐 뒤 같은 이름의 다른 입력을 조용히 넣는 것("틀린 같음")을 막는다.

## 기각한 안과 기각 사유

| 안 | 왜 택하지 않았나 |
|---|---|
| B joblib | pickle 과 같은 위험이고, 우리 규모에서 크기 이득이 작다. 새 직접 의존성을 늘릴 이유가 없다 |
| C skops · ONNX | 사용자 정의 변환기 · 데이터클래스 변환 계층이 필요해 기한(11/18) 안에 검증할 수 없다. GATE 4 전에 형식을 바꿀 이유가 생기면 이 DR 을 다시 연다 |
| D 다시 학습(현행) | 동결의 증거가 아니다 — GATE 4 의 정의를 만족하지 못한다 |
| 손으로 올리는 버전 번호(`FEATURE_VERSION = "v2"`) | 코드를 고치고 번호를 안 올리면 같은 이름의 다른 Feature 가 된다. 소스 해시는 주석만 고쳐도 바뀌는 대가를 치르지만, 그 경우는 다시 학습하면 되고 반대 경우는 조용히 틀린다 |
| `make_preprocessor` 를 모듈 최상위 sklearn import 로 바꾸기 | `import src.decision.features.sprint_table` 만으로 sklearn 이 필요해져 의존성 없는 격리 CI 가 깨진다 |
| `--load-models` 때 없는 모델 종류는 새로 학습 | 불러온 모델과 새로 학습한 모델이 한 실행에 섞이면 "동결한 모델로 평가했다"고 말할 수 없다 |

## 이 결정이 틀렸다면 어떻게 드러나나

- 같은 저장 폴더를 불러온 두 실행이 같은 seed 에서 다른 점수를 낸다 → 저장이 모델을 온전히 담지 못한 것이다(`tests/test_decision_persistence.py` 가 다른 프로세스에서 같은 예측을 확인한다).
- GATE 4 실행이 `feature_version` 불일치로 멈춘다 → GATE 3 동결 뒤에 Feature 소스가 바뀐 것이다. 이것은 결정이 틀린 것이 아니라 결정이 막아야 할 일을 막은 것이다.
- sklearn 판이 다른 환경에서 불러올 때 경고가 나거나 예측이 다르다 → `libraries` 메타데이터로 원인을 찾고, 같은 판(requirements 고정)으로 다시 돈다.

## 민감도

- 저장 크기: 랜덤 포레스트는 학습 표본 수 · 나무 수에 비례해 커진다(5만 명 규모에서 수십~수백 MB 예상, 실측은 다음 full 실행). `models/` 는 커밋하지 않으므로 저장소 크기에는 영향이 없다.
- 소스 해시 범위를 ±한 파일 바꾸면 버전이 바뀌는 빈도만 달라진다 — 모델 값에는 영향이 없다.

## 남은 불확실성

- **로컬 BLOCKED:** 실제 시뮬레이터로 도는 오케스트레이션 테스트(`tests/test_orchestration_*`)는 시스템 팀 로컬에서 돌리지 않는다(시뮬레이터 코드 실행 금지). 저장 → 다른 seed 불러오기 종단 경로는 `tests/test_orchestration_main_cli.py` 에 추가했고 **CI 에서 확인**한다. 로컬에서는 시뮬레이터를 빈 가짜로 바꿔 보조 함수만 확인했다.
- 5만 명 full 실행의 실제 저장 크기 · 시간은 다음 full 실행에서 잰다.
- CLV 의 `test_score` 는 아직 없다(학습에 안 쓴 데이터 평가가 없다) — #217 에서 채운다.
- 대시보드는 불러온 실행의 `churn_eval` 에 `models`(교차검증 표)가 없다는 것을 아직 모른다 — 불러온 실행은 `fitted_evaluation` 을 싣는다. GATE 4 결과 화면은 #226 · #228 에서 정한다.
