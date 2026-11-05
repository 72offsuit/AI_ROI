# DR-211-experiment-scale-config — 실험 규모(DR-234 규모 A)를 실행 기본값으로 넣고 warmup 을 config 프로파일에 묶는다

| | |
|---|---|
| 태스크 | 리드 · #211 (Sprint 3, 규모 결정은 DR-234) |
| 작성 | 인성(Danto7632, 에이전트 구현) · 2026-11-03 |
| 상태 | 확정(설정 반영) · 규모 확인 실행 통과(2026-11-03, `SP-20261103-114303-75f731f8`) — 아래 "확인 실행" |

## 무엇을 정하는가

DR-234 가 정한 실험 규모(고객 50,000명 · t1 = Day 312 · 총 396일)를 `config/experiment_config.yaml` 에 **어떤 키로, 어떤 우선순위로** 넣는가. 특히 warmup(t1 일수)을 config 에 두면 다른 프로파일(스모크 `small` 등) 실행에는 어떻게 적용되는가.

## 정하지 않으면 무엇이 막히나

- **GATE 2 Baseline(#170 · 상세 #212).** 인자 없이 돈 기본 실행이 지금은 20,000명 · warmup 273일(총 357일)이라 FR-05 · FR-03 둘 다 미달이다(DR-234 조사 표의 #192 행). Baseline 은 봉인 대상이라 규모가 정해진 기본 실행으로 돌아야 한다.
- **실행 기록의 출처.** `run_meta.warmup_basis` 는 지금 "`--warmup-days` 인자" 아니면 "프로파일 권장값" 두 가지뿐이라, config 값으로 돈 실행의 출처를 잘못 적게 된다.

## 선택지

| 안 | 내용 | 장점 | 단점 |
|---|---|---|---|
| A | `run.warmup_days` 를 config 에 두고 **config `run.profile` 로 돌 때만** 쓴다. 우선순위는 인자 → config(같은 프로파일) → 프로파일 권장값 | 기본 실행이 규모 A 그대로 돈다. `--profile small` 스모크는 180일 그대로다 | 같은 키가 프로파일에 따라 쓰이기도 하고 안 쓰이기도 한다 — 규칙을 한 함수와 도움말에 적어야 한다 |
| B | `run.warmup_days` 를 모든 실행의 기본 warmup 으로 쓴다 | 규칙이 단순하다 | `--profile small` 스모크도 312 + 84 = 396일을 돈다 — 총 일수가 small 264 → 396일(1.5배), smoke 174 → 396일(≈ 2.28배)이다. 실제 시간 비율은 재지 않았다. 기본 실행에서 프로파일 권장값 표가 사라진다 |
| C | 프로파일을 `long`(warmup 365)으로 바꾼다 | config 키를 늘리지 않는다 | DR-234 가 이미 기각했다 — 13개월보다 1.8개월 길어 시간만 늘고, 시뮬레이터 프리셋의 다른 성질은 시스템 팀이 모른다 |
| D | config 는 고객 수만 바꾸고 warmup 은 실행 명령에 `--warmup-days 312` 로 준다 | 코드 변경이 가장 작다 | 인자를 빠뜨린 실행이 조용히 273일로 돈다. 값은 config 한 곳에만 둔다는 원칙(#206)과 어긋난다 |

## 조사한 것

| 출처 | 무엇을 말하나 | 우리 맥락에 얼마나 맞나 |
|---|---|---|
| `docs/decisions/DR-234-population-experiment-scale.md` 결정 · 기각 표 | 규모 A(50,000명 · Day 312 · 396일), t1 만 필요하면 `--warmup-days` 로 충분(C 기각), control_share 0.5 유지 | 값과 기각 사유를 그대로 옮긴다. 이 기록은 규모를 다시 정하지 않는다 |
| `run_sprint.PROFILE_WARMUP_DAYS` · `docs/data_spec.html` §2.2 | 권장 warmup — reference 273 · small 180 · smoke 90 | 권장값 표는 그대로 둔다. 기본 실행만 312 다 |
| 테스트 · CLI 사용처(`git grep`, main `02648e9`) | 실행을 도는 테스트는 모두 `--profile smoke` 이거나 `--warmup-days` · `SprintConfig(warmup_days=…)` 를 명시한다. `profile="reference"` 로 warmup 없이 도는 테스트는 없다 | A 로 바꿔도 기존 테스트의 시간축이 바뀌지 않는다 |
| `src/main.py` · `run_sprint` CLI | 두 진입점 모두 `run.num_customers` · `run.profile` 을 기본으로 읽고, warmup 은 `SprintConfig.warmup_days` 로 넘긴다 | 우선순위를 `run()` 안의 한 함수(`resolve_warmup`)에 두면 두 진입점이 같이 따른다 |

## 결정

**A.**

- config: `run.num_customers: 50000` · `run.profile: reference` · `run.warmup_days: 312`(신설 — 필수 키, 정수 ≥ 1).
- `run_sprint.resolve_warmup(profile, warmup_days)` — ① `--warmup-days` 인자 → ② `profile` 이 config `run.profile` 과 같으면 `run.warmup_days` → ③ `PROFILE_WARMUP_DAYS`. 고른 출처를 `run_meta.warmup_basis` 에 문장으로 싣는다. 권장값을 모르는 프로파일이면 추측하지 않고 warmup 단계가 `not_run` 이다(예전과 같다).
- 두 CLI(`src/main.py` · `run_sprint`)의 `--warmup-days` 도움말에 같은 규칙을 적는다.
- 테스트로 고정하는 것:
  - `tests/test_decision_config.py` — 기준값 50,000 · 312, 우선순위 6경우, "총 396일 = warmup + RCT 42 + 분기 42". config 프로파일을 small · 77일로 바꾸면 small → 77 · reference → 273 인지도 본다(②가 `"reference"` 라는 이름에 박히지 않았는지).
  - `tests/test_feature_sprint_table.py` — 가짜 공개 API 로 `run()` 을 끝까지 돌려, warmup 인자 없는 reference 실행의 `run_meta` 가 312일 · config 출처 · t1 = start + 312일이고 smoke 는 90일 · 권장값 출처인지 본다(`run()` 이 `resolve_warmup` 을 실제로 쓰는지).

**근거:** 기본 실행이 곧 GATE 2 Baseline 실행이므로 규모는 실행 인자가 아니라 config 에 있어야 한다(D 기각). 스모크는 개발 반복용이라 시간축이 바뀌면 안 된다(B 기각). 규모 값 자체는 DR-234 가 정했다 — 이 기록은 그 값을 어디에, 어떤 우선순위로 두는지만 정한다.

## 기각한 안과 기각 사유

| 안 | 왜 택하지 않았나 |
|---|---|
| B 모든 실행의 기본 | 스모크의 warmup 이 312일로 늘어 총 일수가 small 1.5배(264 → 396일) · smoke ≈ 2.28배(174 → 396일)가 된다 — 개발 반복(DR-234 민감도: "개발 반복은 small")이 느려진다. 실제 시간 비율은 재지 않았다(RCT · 분기 42일씩은 그대로라 일수 비율과 같다고 볼 수 없다). 프로파일 권장값이 기본 실행 밖에서도 가려진다 |
| C `long` 프로파일 | DR-234 의 기각 사유 그대로다 |
| D 실행 인자로만 | 인자를 빠뜨리면 조용히 규모 미달 실행이 된다 — GATE 2 Baseline 을 잘못 돌릴 길을 남긴다 |

## 이 결정이 틀렸다면 어떻게 드러나나

- 확인 실행의 `run_meta.warmup_days` 가 312 가 아니거나 `warmup_basis` 가 config 문장이 아니면 배선이 틀렸다.
- 다른 프로파일 실행의 `warmup_basis` 가 "data_spec §2.2 프로파일 권장값" 이 아니면 ②가 새고 있다.
- 규모(DR-234 반증 조건): `arm_counts` 에서 T0 < 10,000 이거나 T1~T4 합 < 10,000 이면 비율 가정이 틀렸다. 그때 고객 수를 20,000 / r 로 다시 계산해 이 config 를 고친다.

## 민감도

- `run.warmup_days` ±20%(250~374일) — DR-234 민감도 그대로다. 250 이면 총 334일로 FR-03(12개월)부터 미달이고, 374 면 요구는 같고 시간만 ≈ +10% 늘어난다.
- `run.num_customers` ±20%(40,000~60,000명) — Eligible 비율 r = 0.45 에서 T · C 각 ≈ 9,000~13,500명이다. 40,000명이면 미달이다. 확인 실행에서 잰 r ≈ 0.519 로는 각 ≈ 10,400~15,600명이라 40,000명도 겨우 넘는다(최소 ≈ 38,600명). 다만 r 은 봉인 전 시뮬레이터 변경으로 달라질 수 있어 50,000 을 유지한다.

## 확인 실행

DR-234 결정대로 `arm_counts` 로 T · C ≥ 1만을 확인하고 실행 시간을 기록한다.

- **방법:** 인자 없이(`--out` · `--results-root` · `--run-id` 만) 돈 기본 실행 1회. 사람(인성)이 돌린다 — 시스템 팀 에이전트는 시뮬레이터 코드를 돌리지 않는다. 에이전트는 결과 폴더의 `run_meta.json` 에서 `rct`(Eligible 수 · 조건별 탈락 수 · `arm_counts`) · `warmup_days` · `warmup_basis` · `timeline` · 단계별 시간만 읽는다.
- **실행:** 2026-11-03 11:43~13:52 KST, 인성이 로컬(36GB 메모리 Mac)에서 돌렸다. run_id `SP-20261103-114303-75f731f8`, 종료 코드 0, 25단계 모두 `ok` 였다. 코드는 main `02648e9` 에 이 PR 의 커밋 전 변경을 얹은 것이다. `experiment_config.yaml` sha256 은 `4f93c792…` 로 이 PR 커밋 `128e615` 의 파일과 같다(리뷰 보완에서 주석만 고쳐 지금 파일의 해시는 다르고, 값은 같다). `simulator_commit` 은 `79c6214`(`simulator_worktree_dirty: false`)다.
- **결과: 통과.**

| 확인 항목 | 기준 | 실측 | 판정 |
|---|---|---|---|
| 고객 수 · 프로파일 | 50,000 · reference | `num_customers` 50,000 · `profile` reference | 통과 |
| warmup · 출처 | 312 · config 문장 | `warmup_days` 312, `warmup_basis` "config/experiment_config.yaml run.warmup_days (프로파일 reference · DR-234 실험 규모)" | 통과 |
| 시간축 | t1 = Day 312, 총 396일(13개월) | start 2025-01-01, t1 2025-11-09, t2 2025-12-21, end 2026-02-01(끝 미포함, 마지막 날 2026-01-31) → 312 + 42 + 42 = 396일 | 통과 |
| FR-05 대조군 | T0 ≥ 10,000 | `arm_counts.T0` 12,978 | 통과(+30%) |
| FR-05 처치군 | T1~T4 합 ≥ 10,000 | 3,245 + 3,245 + 3,245 + 3,244 = 12,979 | 통과(+30%) |

- **Eligible:** t1 이전 이벤트에 관측된 고객은 49,988명(`n_population`)이고 Eligible 은 25,957명이다. 비율 r = 25,957 / 50,000 ≈ **0.519** 로, DR-234 의 가정 0.45 보다 높다. 조건별 탈락 수는 가입 60일 미만 325명, 구매 이력 없음 3,894명, 최근 14일 안 구매 19,981명이다. 한 고객이 여러 조건에 걸리면 각 조건에 따로 세므로, 합 24,200명이 실제 탈락 24,031명보다 많다. 특성이나 결과가 없어 빠진 고객은 0명(`n_dropped_without_features_or_outcome`)이다.
- **실행 시간: 7,775초(2시간 9분 35초)이고, 단계 합은 7,768.6초다.** DR-234 가 어림한 ≈ 25분은 시뮬레이터 시간만 셌고, 실측도 20.9분으로 비슷하다. 전체 시간의 64% 는 분기 실행이다.

| 묶음 | 단계 | 초 | 비중 |
|---|---|---|---|
| 분기 6개 | `strategy_S0`~`S5`(각 796~893초, 차례로 실행) | 4,989.5 | 64% |
| 시뮬레이터 | `simulate_warmup` 1,038.3 · `simulate_rct` 214.1 | 1,252.4 | 16% |
| t2 스냅샷 | `snapshot_t2` | 555.6 | 7% |
| 이벤트 읽기 | `read_events_t1` 191.6 · `read_events_t2` 359.3 | 550.9 | 7% |
| 배정 · 특성 · 모델 · 집계 | 나머지 15단계(가장 긴 것은 `churn` 138.3) | 420.2 | 5% |

- **자원:** 실행 중 메모리를 한 번 쟀다. 84분 무렵(`strategy_S2` 중) RSS 6.8GB였고, 최댓값은 재지 않았다. 출력 크기는 시뮬레이터 출력 6.0GB, 결과 폴더 0.97MB다.
- **하지 않은 것 — 분기 간 대조.** DR-234 는 측정 계층 지표를 Eligible 로 좁히지 않은 결정(P3 기각)의 근거인 분기 간 대조를 small 실행 1회(2,000명)로만 했고, 50,000명에서도 같은지 #211 실행에서 확인하라고 남겼다(DR-234 남은 불확실성). 이번 확인 실행에서는 하지 않았다. 대조는 분기마다 공개 이벤트를 읽어야 하는데, 이번에 에이전트는 `run_meta.json` 만 읽었다. GATE 2 Baseline 실행(#170)의 출력으로 같은 대조를 하도록 넘긴다. 그때까지 P3 기각의 근거는 small 1회 그대로다.

## 남은 불확실성

- **실행 시간 · 메모리 · 디스크(확인 실행으로 잼).** 기본 실행 한 번이 ≈ 2시간 10분, 디스크 ≈ 6GB 다. GATE 2 Baseline(#170) 일정은 이 시간을 기준으로 잡는다. FREEZE-003 으로 봉인 뒤 다시 돌려야 하면 그때마다 2시간이 넘게 든다. 시간을 줄이려면 차례로 도는 분기 6개(83분)를 손봐야 하지만, 이 기록의 범위가 아니다. 메모리 최댓값은 재지 않았다.
- **출처 기록의 빈칸.** `provenance()` 는 `src/simulator` 경로만 dirty 여부를 본다. 그래서 시스템 쪽 커밋 전 변경으로 돈 실행도 `repo_commit` 만 적힌다. 이번 확인 실행은 `02648e9` 로 적혔지만 실제로는 커밋 전 #211 변경이 얹혀 있었다. config 변경은 `config_sha256` 으로 드러나지만 코드 변경은 드러나지 않는다. 봉인 실행에 문제가 될 수 있어 #262 로 다룬다(PR #263 — 실행 시작 때 저장소 전체의 커밋 전 변경을 적고, 봉인 실행은 `--require-clean` 으로 시작 전에 막는다). 이 PR 은 고치지 않는다.
- **Day 312 의 Eligible 비율.** DR-234 남은 불확실성 그대로다. 봉인 전 시뮬레이터 변경(#256 등)으로 달라질 수 있어, GATE 2 Baseline 실행(#170)의 `arm_counts` 로 다시 확인한다.
- **50,000명 규모의 분기 간 대조.** 위 "하지 않은 것". #170 Baseline 출력에서 비Eligible 고객의 분기 창 결과가 분기마다 다르면 DR-234 P3 기각을 다시 본다(DR-234 반증 조건).
- **`docs/data_spec.html` §2.2 의 reference warmup 273 은 그대로다.** 공용 문서(`shared_read_only`)라 이 PR 에서 고치지 않았다. 기본 실행이 312 를 쓴다는 사실은 config 와 이 기록에만 있다 — 필요하면 양 팀 합의로 data_spec 에 적는다.
- **로컬 검증 범위.** 로컬(Python 3.12.4)에서 `tests.test_decision_config` · `tests.test_feature_sprint_table` · `tests.test_isolation` · `tests.test_team_boundaries` · `tests.test_decision_records` 108건을 돌렸다(OK · skip 0). 실행 루프 쪽은 시뮬레이터 import 를 뺀 하네스(`tests/test_feature_sprint_table._contract_runner`)와 그 위의 가짜 공개 API 실행으로 확인했다 — 실제 시뮬레이터 · 엔진은 돌지 않는다. 실행 루프 통합 테스트(`test_orchestration_*`)는 로컬에서 돌리지 않았다 — CI 가 돈다.
