# DR-206-main-cli-config — main CLI 를 디스패처로 두고, 모델·실험 상수를 config 로 옮긴다

| | |
|---|---|
| 태스크 | 이슈 #206 (부모 #184 의 스프린트 2 범위 · SRS SYS-004 · CFG-002 · CFG-003 · CQ-003 · PRD §73 · NFR-06) |
| 작성 | 시스템 팀 리드(인성) 구현 에이전트 · 2026-10-23 |
| 상태 | 확정 — 모델 저장 · Feature Store · NFR-01 버전 기록은 다음 스프린트(#184 잔여) |

## 무엇을 정하는가

1. `python src/main.py --mode train / uplift / optimize --budget KRW / evaluate / full` 이 **무엇을 실행하고,
   무엇을 입력으로 받고, 어디에 무엇을 쓰는가.** 모델을 저장하지 않는 지금 구조에서 모드 사이에 무엇을 넘기는가.
2. 코드 상수(하이퍼파라미터 · 세그먼트 경계 · RCT 배정 비율 · α/검정력 · 개발 seed)를 config 로 옮기는 방식 —
   파일 모양 · 로더 · 검증 규칙 · 코드가 그 값을 읽는 자리.
3. 이번에 **옮기지 않는 상수**와 그 이유.

## 정하지 않으면 무엇이 막히나

- SRS SYS-004 [MUST] 의 명령 형태가 없다 — 지금은 `python -m src.orchestration.run_sprint` 하나로 전 구간을 돈다.
  스프린트 3 의 `main.py --mode train`(docs/sprint_plan.md) · GATE 2 Baseline 저장 · 패키징이 이 진입점에 걸린다.
- CQ-003 [MUST] "Threshold / Hyperparameter 하드코딩 금지" 위반이 남는다. 하이퍼파라미터를 바꾸려면 코드를
  고쳐야 하고, 바꾼 사실이 실행 기록(`run_meta.provenance.config_sha256`)에 남지 않는다.
- 다음 스프린트의 모델 저장(ML-008)이 "어떤 설정으로 학습한 모델인가" 를 적으려면 설정이 파일로 있어야 한다.

## 선택지

**A. CLI 구조**

| 안 | 내용 | 장점 | 단점 |
|---|---|---|---|
| A1 | `run()` 은 그대로 두고, 모드 = **실행할 단계 이름 집합**. 나머지 단계는 기존 `not_run` 경로로 건너뛴다 | 로직 복제 0. 결과 JSON 7종이 모드와 무관하게 같은 모양 — 대시보드 · 기존 테스트가 그대로 읽는다. `run_sprint.py` 변경이 작다(이번 주 #179 와 충돌 최소) | 단계 이름(문자열)에 묶인다 — 이름이 바뀌면 모드가 그 단계를 놓친다 |
| A2 | `run()` 을 단계 함수(train · score · optimize · compare)로 쪼개고 main 이 이어 부른다 | 구조가 명시적 | `run_sprint.py` 대수술 — #179(홀드아웃 · churn_p · event_outcomes)와 같은 주에 정면 충돌. 동작 동일성 증명 부담 |
| A3 | 모드마다 별도 파이프라인을 main.py 에 새로 쓴다 | run_sprint 무변경 | 실행 루프 로직 복제 — 이슈가 금지. 두 벌은 어긋난다 |

**B. 모드 사이에 넘기는 것**

| 안 | 내용 | 장점 | 단점 |
|---|---|---|---|
| B1 | **넘기지 않는다.** 모든 모드가 같은 seed 로 시뮬레이션부터 다시 돌고 다시 학습한다. 재현성이 넘김을 대신한다 | 새 영속 형식 0 — 다음 스프린트의 모델 저장 설계를 미리 묶지 않는다 | 시간(uplift 가 train 을 다시 한다). 다른 프로세스가 학습한 모델을 평가할 수 없다 |
| B2 | 이번에 pickle 로 모델·Feature 를 저장하고 다음 모드가 읽는다 | 모드가 진짜로 이어진다 | #206 범위 밖(모델 저장은 #184 잔여 · ML-008 메타데이터 · 버전 기록과 함께 설계해야 한다). 메타데이터 없는 pickle 은 "어떤 모델인가" 를 말하지 못한다 |

**C. config 를 읽는 자리**

| 안 | 내용 | 장점 | 단점 |
|---|---|---|---|
| C1 | 모듈 import 때 한 번 읽어 **기존 상수 이름에 묶는다**(`churn.N_SPLITS = CONFIG.cv_folds`) | 기존 이름 · `override_attr`(`--cv-folds`) · 테스트가 그대로 동작. 잘못된 config 는 import 에서 즉시 멈춘다 | 프로세스 도중 config 를 바꿔도 반영되지 않는다(CLI 에는 무관) |
| C2 | 호출할 때마다 읽는다 | 실행 중 변경 반영 | 상수 이름이 사라져 `override_attr` · 기존 테스트가 깨진다. 실패가 단계 안으로 숨어 run_meta 작성 경로까지 번진다 |
| C3 | 함수 인자로 주입(오케스트레이션이 넘긴다) | 순수 | 호출 지점 전부(run_sprint · 테스트 가짜 모듈 시그니처)를 바꿔야 한다 — 충돌 |

**D. 검증**

| 안 | 내용 | 장점 | 단점 |
|---|---|---|---|
| D1 | 스키마를 코드(`src/decision/config.py`)에 선언 — 모르는 키 · 빠진 키 · 타입(bool≠int) · 범위 거부. 표준 라이브러리만 | 의존성 없는 CI 에서도 스키마 테스트가 돈다. 오타 키가 조용히 버려지지 않는다 | 스키마 확장은 코드 수정 |
| D2 | `jsonschema` | 표준 형식 | `requirements-dev.txt` 전용 의존성 — 런타임 경로에 쓸 수 없다 |
| D3 | 모르는 키는 경고만 | 관대 | 오타가 기본값으로 돌아 사람은 바꿨다고 믿는다 — 이 저장소가 막는 실패 양식 |

## 조사한 것

| 출처 | 무엇을 말하나 | 우리 맥락에 얼마나 맞나 |
|---|---|---|
| PRD §73 Main CLI | `--mode train` → models/ + AUC-ROC · SHAP 그림, `uplift` → Customer Uplift Score · 4분면 CSV, `optimize --budget` → 세그먼트 예산 배분 · 기대 ROI | 명령 형태는 그대로 맞췄다. **models/ 저장과 SHAP 그림(png)은 아직 없다** — 그렇게 적는다(아래 결정 3) |
| SRS SYS-004 · CFG-002 · CFG-003 · CQ-003 · PRD NFR-06 | train/uplift/optimize 필수, evaluate/monitor/full 권장. config 4종 예시. CFG-002·003 의 키 다수가 `TBD` | `TBD` 키(split 비율 · dl · tuning_method · uplift.treatment_id · final_holdout_seed)는 **읽는 코드가 없어** 넣지 않았다 — 넣으면 읽히지 않는 값이 된다(`tests/test_config_no_dead_values.py` 가 막는 결함 #63 M8 과 같은 모양). 키 이름은 SRS 를 따랐다(`cv_folds` · `alpha` · `target_power` · `holdout.development_seed`) |
| `src/orchestration/run_sprint.py` (main d9a3902) | 25 단계가 `log.stage(name, requires=...)` 로 이미 나뉘고, 본문 첫 줄 `skip_if_not_run` 이 테스트로 강제된다 | 안 A1 이 이 구조를 그대로 쓴다. 바꾼 것은 `StageLog`(실행 범위) · `SprintConfig`(stages · scope · capture) · config 를 읽는 상수 4 곳 · 상태 전달 2 줄 |
| `src/measurement/config_loader.py` · `tests/test_neutrality.py` | `import yaml` 은 config_loader 한 곳 · `safe_load` 만 | 새 로더도 `load_yaml` 만 쓴다. 이 모듈은 yaml 을 import 하지 않는다 |
| PyYAML 6.0.3 실측 | `safe_load("cv_folds: 5\ncv_folds: 3")` → `{'cv_folds': 3}` — **중복 키를 오류 없이 덮는다** | 로더가 잡지 못한다. 남은 불확실성에 적는다(경제 규칙 config 도 같은 처지다) |
| 동작 동일성 실측 — main d9a3902 의 `run_sprint`(seed 42 · 2,000명 · small) vs 이 브랜치 `--mode train` · `optimize` · `evaluate` · `full` 같은 인자 | 실행마다 다른 키(run_id · 시각 · 단계 상태)와 범위 밖 키를 빼면 `uplift_eval` · `clv_eval` · `strategy_comparison` · `ab_test` 는 **같다.** `train` 의 `churn_eval` 은 비트 단위로 같다. `full` 은 `churn_eval` random_forest 임계 3 곳 · `segments` 평균 이탈확률 1 곳이 **마지막 자리(상대 1e-16)** 만 다르다. `optimize --budget` 에 기준 실행의 C_rule 을 주면 배분이 기준 실행 What-if 100% 행과 같다(대상 수 · 처치 구성 · 계획 지출 · 기대 ROI 일치 — 수치는 두 팀이 읽는 이 기록에 적지 않는다) | config 이전이 동작을 바꾸지 않았다는 직접 증거이자, 안 B1 의 "같은 seed 면 같은 모델" 주장의 근거 — 단 아래 행의 한계가 있다 |
| 마지막 자리 차이의 원인 실측 — 합성 2,000×40 · RandomForest(n_estimators 300, n_jobs=-1) | 학습된 트리는 n_jobs 1 · -1 에서 **같다.** `predict_proba` 는 병렬 합산 순서 때문에 순차 결과와 15/15 회 비트가 다르다(최대 2.2e-16). full 실측은 세 실행을 동시에 돌려 스레드 순서가 달라진 경우다 | 이 브랜치가 만든 차이가 아니다(기존 `n_jobs=-1`). 순위 · 배정 · 전략 결과에는 영향이 없었지만 "같은 seed 면 비트 단위로 같다" 는 **보장하지 않는다** |
| 외부 문헌 | CLI 모드 분할 · config 스키마 방식에 대해 이 프로젝트 맥락에 맞는 외부 근거를 찾지 않았다 | **근거 없음.** 이 결정은 저장소 내부 제약(로직 복제 금지 · 같은 주 충돌 · 의존성 없는 CI)에서 나왔다 |

## 결정

**A1 · B1 · C1 · D1.**

1. **모드 = `run()` 의 단계 집합** (`src/main.py` `MODES`). 범위 밖 단계는 시도하지 않고 `not_run`
   ("실행 범위 밖이다(--mode train)")으로 적힌다. 결과 JSON 7종은 모드와 무관하게 같은 모양이다.

   | 모드 | 실행 단계 | 입력 | main.py 가 더 쓰는 것 |
   |---|---|---|---|
   | `train` | warmup → 탐색 RCT → Feature(t1) · outcomes → churn · uplift · clv 학습·교차검증 (11 단계) | seed · 고객 수 · 프로파일 · model_config | — (`churn_eval` · `uplift_eval` · `clv_eval`) |
   | `uplift` | train + Feature(t2) · 점수 · 세그먼트 | 같음 | `uplift_scores.csv` — 고객별 churn_p · clv · CATE T1~T4 · uplift_score · uplift_arm · 4분면 · 세그먼트 |
   | `optimize` | uplift + What-if | 같음 + `--budget`(필수) | `uplift_scores.csv` · `budget_allocation.json` — `strategies.plan("S5")` 배정을 세그먼트별로 집계, 기대 ROI 는 What-if 100% 행. **분기 시뮬레이션은 하지 않는다**(계획 단계) |
   | `evaluate` | train + 탐색 RCT A/B + Feature(t2) · 스냅샷 · S0(무처치) 분기 · 시간 홀드아웃 | 같음 | — (`ab_test` · `churn_eval.temporal_holdout`). S1~S5 비교는 `full` |
   | `full` | 전 구간 25 단계 (`run_sprint` 와 같다) | 같음 + `--budget`(선택, S2~S5 예산) | 두 파일 모두 |

   공통 출력: `RESULTS_ROOT/sprint-v0/RUN_ID/` 의 JSON 7종 + `main_cli.json`(모드 · 실행 단계 · 산출물 상태 ·
   config SHA-256) + `latest`. `RESULTS_ROOT` 기본은 `full` 만 `results/`(대시보드가 읽는 곳)이고 나머지는
   `results/cli/MODE/` — **부분 실행이 대시보드의 latest 를 덮지 않게 한다.** 시뮬레이터 출력 기본은 `data/sprint/RUN_ID/`.
   종료 코드: 0 전부 ok · 1 실패 · 2 인자 오류 · 3 범위 안 not_run · 5 config 오류.
2. **모드 사이에 넘기는 것은 없다.** 같은 seed · 고객 수 · 프로파일 · config SHA-256 이면 같은 세계 · 같은 모델이다
   (위 실측). main 의 산출물 CSV · 배분은 run() 의 결과와 **대조 장치**를 함께 낸다 —
   `consistent_with_segments_json`(CSV 세그먼트 수 = segments 단계) · `consistent_with_allocation`(S5 배정 = What-if 100% 행).
3. **저장하지 않는 것을 숨기지 않는다** — `models/`(ML-008) · `data/processed/`(FS-001/002) · SHAP 그림을
   `--help` 와 `main_cli.json.not_persisted` 에 적는다.
4. **config 2 종** — `config/model_config.yaml`(churn 4 모델 하이퍼파라미터 · cv_folds 5 · 내부 fold 3 · SHAP 표본 500 ·
   CLV 회귀기 · CLV fold 5 · 세그먼트 분위수 0.8/0.5/0.6), `config/experiment_config.yaml`(실행 기본값 20,000명 ·
   reference · 개발 seed 42 · RCT 대조군 0.5 · 모집단 90일 · α 0.05 · 검정력 0.8 · SRM p 0.001).
   **기본값은 #206 이전 코드 상수와 같다.** 로더 `src/decision/config.py`, 읽는 곳 churn · clv · segments · ab_test ·
   run_sprint. `tests/test_decision_config.py` 가 (1) 스키마 거부 (2) 파일 값 = #206 이전 상수 (3) `make_model` 이
   만든 추정기의 `get_params()` = #206 이전 코드가 문자 그대로 만들던 추정기 (4) 그 자리에 숫자 리터럴이 다시
   박히지 않음(AST, 음성 대조 포함)을 고정한다.

**근거:** 이슈가 "기존 모듈 호출 · 로직 복제 금지 · run_sprint 수정 최소" 를 요구하고, run() 이 이미 단계 단위로
나뉘어 있다(A1). 모델 저장은 메타데이터 · 버전 기록과 함께 설계할 다음 스프린트 일이다(B1). 기존 상수 이름을 살려야
`--cv-folds` 덮어쓰기와 기존 테스트가 그대로 돈다(C1). 오타 키가 조용히 버려지는 것은 이 저장소가 반복해서 막아 온
"선언과 실제가 어긋난 채 아무도 대조하지 않는" 결함이다(D1).

## 기각한 안과 기각 사유

| 안 | 왜 택하지 않았나 |
|---|---|
| A2 run() 분해 | 같은 주 #179 가 run_sprint 의 홀드아웃 · churn_p · event_outcomes 를 고친다. 분해는 그 전부와 충돌하고, 동작 동일성을 다시 증명해야 한다. 모드가 단계 집합으로 표현되는 지금, 분해가 사는 것이 없다 |
| A3 모드별 별도 파이프라인 | 실행 루프 복제. 이슈가 명시적으로 금지 |
| B2 이번에 pickle 저장 | #206 범위 밖. 메타데이터(학습 데이터 계보 · config 해시 · 버전) 없이 저장하면 "무슨 모델인가" 를 답할 수 없는 파일이 생기고, 다음 스프린트의 ML-008 설계를 그 형식에 묶는다 |
| C2 호출 시 지연 읽기 | `N_SPLITS` 같은 상수 이름이 사라져 `--cv-folds`(`override_attr`)가 깨진다. config 오류가 단계 실패로 숨어 run_meta 작성 중 `decision_available` 에서 터질 수 있다 |
| C3 인자 주입 | 가짜 의사결정 모듈(테스트) 시그니처까지 전부 바꿔야 한다 — 이번 주 충돌면이 커진다 |
| D2 jsonschema | dev 전용 의존성. 런타임 로더에 쓸 수 없다 |
| D3 모르는 키 경고 | 경고는 읽히지 않는다. 오타가 기본값으로 도는 순간 config 분리의 의미가 사라진다 |
| `evaluate` 에 S1~S5 비교까지 | 그러면 `full` 과 같아진다. 모델 평가(교차검증 + 시간 홀드아웃 + A/B)와 전략 비교를 나눠, evaluate 는 분기 1 개(S0)만 시뮬레이션한다 |
| 모든 모드가 `results/` 에 쓰기 | train 한 번이 대시보드의 latest 를 전략 비교 없는 실행으로 바꾼다 |

## 이 결정이 틀렸다면 어떻게 드러나나

- **config 이전이 동작을 바꿨다면** — 같은 seed · 고객 수 · 프로파일로 main 이전 판과 이 판을 돌린 결과 JSON 이
  다르다(이 PR 에서 대조했다 — RF 확률 마지막 자리 외에는 같았다). 단위 수준에서는 `test_churn_estimators_match_pre_206_construction` 이 실패한다.
- **config 가 실제로 읽히지 않는다면(죽은 값)** — `test_changing_config_changes_the_estimator` 가 실패한다.
- **모드의 단계 집합이 틀렸다면** — 선택한 단계가 `선행 단계가 ok 가 아니다` 로 not_run 이 되고 종료 코드 3,
  `TestModesEndToEnd.test_selected_stages_ok_and_the_rest_out_of_scope` 가 실패한다. run_sprint 의 단계 이름이 바뀌면
  `main_cli.json stages.unknown_selected` 와 종료 코드 1 로 드러난다.
- **"같은 seed 면 같은 모델" 이 틀렸다면** — 같은 입력의 두 모드 실행에서 `churn_eval.models[].cv` 가 다르다.
  (시뮬레이터나 sklearn 이 비결정적이 되는 변경이 들어오면 여기서 깨진다.) 마지막 자리(상대 1e-16) 차이는 RF
  `n_jobs=-1` 의 기존 성질로 이미 관측된다 — 그보다 큰 차이가 나거나 순위 · 배정이 달라지면 이 결정이 틀린 것이다.

## 민감도

config **값**은 바꾸지 않았으므로 모델 성능에 대한 민감도는 이 결정에 없다(값을 바꾸는 것은 별도 결정 · 별도 DR).
설계의 민감도는 **실행 시간**이다. 2,000명 · small 실측: `train` 69.8초(단독 실행), `full` 110.7초(main d9a3902 run_sprint 단독 실행 · 전략 분기 6 개 포함).
모드가 학습을 다시 하므로 reference 20,000명에서는 uplift · optimize 가 train 시간을 그대로 다시 쓴다 —
모델 저장(#184 잔여)이 들어오면 이 비용이 사라지는 구조다.

## 남은 불확실성

**옮기지 않은 상수 (다음 스프린트 · 사유)**

| 상수 | 자리 | 옮기지 않은 이유 |
|---|---|---|
| Uplift 기저 학습기 `BASE_LEARNER` · `MIN_ARM_N` · `VALIDATION_SIZE` · `DEFAULT_PRIMARY_ARM` | `uplift.py` | 같은 주 #179 가 같은 파일(Qini)을 고친다 — 충돌 회피. #179 병합 뒤 옮긴다 |
| label window 42일 · 프로파일 warmup 표 | `run_sprint.py` · `sprint_table.py` | data_spec §2.2 가 고정한 값이고 라벨 정의(`LABEL_DEF`)와 묶여 있다 — 바꾸면 라벨이 바뀐다. sprint_table 은 #179 범위 |
| S1 eligible(60일 · 1회 · 14일) · `S1_RULE` · C_rule 설계 추정 | `run_sprint.py` · `strategies.py` | GATE 2 봉인 대상(기준선 · 예산 상한). 봉인과 함께 정한다 · `strategies.py` 이익 경로는 #169 범위 |
| Churn DL 하이퍼파라미터 | `churn_dl.py` | 실행 루프가 부르지 않는다(스프린트 판) |
| 모니터링 PSI 임계 | `monitoring.py` | `--mode monitor` 와 함께(이번 범위 밖) |

**그 밖**

- `--mode monitor`(SRS 권장)는 없다.
- `models/` 저장 · Feature Store · NFR-01 버전 기록 — #184 잔여. Final Holdout(GATE 4) seed 도 그때 정한다
  (개발 seed 와 달라야 한다).
- PyYAML 이 중복 키를 덮는 것을 로더가 잡지 못한다 — 측정 계층 `load_yaml` 공용 문제라 그쪽에서 다룰 일이다.
- RandomForest `n_jobs=-1` 의 `predict_proba` 는 실행마다 마지막 자리가 다를 수 있다(위 실측). 비트 재현이 필요하면
  `n_jobs: 1`(느려진다)이 답이지만 그것은 Churn 모델 담당의 결정이라 값을 바꾸지 않았다.
- `src/main.py` 는 `src/AGENTS.md` 의 파트 표에 없다(src 최상위 진입점). import 경계는
  `tests/test_orchestration_main_cli.py` 가 AST 로 고정한다(시뮬레이터 · 진단 금지, 최상위는 표준 라이브러리만).
