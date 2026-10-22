# DR-142-diagnostics-sprint — S8 채점 지표 정의와 미봉인 실행 가드

| | |
|---|---|
| 태스크 | S8 · 에픽 #142 스프린트 1 (원 태스크 #82) |
| 작성 | Claude (S8 담당 에이전트) · 2026-10-22 |
| 상태 | 제안 |

## 무엇을 정하는가

`src/diagnostics/` 의 사후 진단 지표(Qini_oracle · Qini 달성률 · PEHE · corr(τ̂, τ) · 4분면 혼동행렬)를 **어떤 정의로** 계산하고, 두 GATE 가 봉인되기 전에 리포트 CLI 가 **실행을 어떻게 거부**하는가.

## 정하지 않으면 무엇이 막히나

- 봉인 뒤 최종 리포트의 진단 항목(data_spec §14.1 Secondary — PEHE · corr)과 Primary ② Qini 의 "oracle 대비 달성률 병기"(§14)를 낼 수 없다.
- 가드 없이 채점 코드가 먼저 생기면, 봉인 전에 누군가 실제 결과에 돌려 보고 시뮬레이터·전략을 고치는 길이 열린다(PRD §80 Risk 1, TEAM_SETUP §5 "S8 은 두 GATE 뒤").

## 선택지

| 안 | 내용 | 장점 | 단점 |
|---|---|---|---|
| A | oracle = **같은 관측 (W, Y)** 위에서 정렬 기준만 참 τ 로 바꾼 Qini. 모델 Qini 도 이 모듈이 같은 함수로 다시 잰다 | 달성률의 분자·분모가 같은 정의·같은 모집단 | decision 이 보고한 Qini 숫자와 다를 수 있다 |
| B | oracle = 잠재결과로 잰 참 이득 곡선 Στ (관측 무작위성 없음) | 표본 잡음이 없는 진짜 상한 | 모델 Qini(관측 기반)와 단위·잡음이 달라 비율이 섞인다 |
| C | 모델 Qini 를 `uplift_eval.json` 에서 그대로 가져온다 | 재계산 없음 | 정의·모집단 일치를 확인할 수 없다. 키 이름도 문서에 없다 |

가드: (가) GATE 2 기록 위치가 미정이면 **거부** · (나) 미정이면 GATE 1 만 보고 허용.

## 조사한 것

| 출처 | 무엇을 말하나 | 우리 맥락에 얼마나 맞나 |
|---|---|---|
| `docs/data_spec.html` §4.4 · §14 | 무작위 실험 Qini 와 참 CATE 기준 oracle Qini 를 비교해 개선 여지를 말한다. PEHE · corr 은 크기 오차 | 직접 요구. "같은 RCT 데이터에서 정렬만 다르게" 로 읽어 안 A |
| Radcliffe (2007) Qini 곡선 · Hill (2011) PEHE | Q(k) = Y_T(k) − Y_C(k)·N_T(k)/N_C(k), PEHE = √mean((τ̂−τ)²) | 표준 정의. 정규화(1인당)는 우리가 정했다 — 문헌마다 다르다 |
| `config/gate1_lock.yaml` · `freeze.py` | 현재 `PARTIAL_FREEZE`, `experiment_environment_v1_declared: false`, `simulator_commit: null` | GATE 1 봉인 판정 조건을 이 세 필드로 잡았다 |
| `docs/TEAM_SETUP.md` §5·§6 · `src/AGENTS.md` | GATE 2 는 D7(#89). 봉인 기록 파일 위치는 어디에도 정해져 있지 않다 | 위치 미정 → 거부(가) |
| `docs/simulator_api.md` · DR-143 | 참 효과는 `data/ground_truth/simulator/po-*.jsonl`, 고객별 T0~T4 결과. **정확한 키는 문서에 없다** | 로더 키를 `GT_KEYS` dict 로 분리 |

## 결정

- **Qini 는 안 A.** `qini_coefficient` 하나로 모델(τ̂ 정렬)과 oracle(τ 정렬)을 같은 관측 위에서 잰다. 곡선은 **점수 동률 묶음 경계에서만** 점을 찍는다 — 이진 결과의 참 τ 는 −1·0·1 뿐이라 동률이 대부분이고, 묶음 안 순서를 임의로 두면 oracle 이 입력 순서에 따라 흔들린다(시험 `test_ties_do_not_depend_on_input_order`). 면적은 사다리꼴, 값은 1인당(Q/N) 단위, 무작위선 면적을 뺀다(Random = 0).
- **달성률** = 모델 ÷ oracle, oracle ≤ 0 이면 `None` + 사유.
- **τ 의 결과변수는 Retention**(42일 창 구매 여부, §14 Primary ②): τ = Y(t) − Y(T0) 를 잠재결과에서 유도하고, 파일의 τ 는 대조(불일치 건수 기록)만 한다.
- **4분면**: 참 = 잠재결과 (Y(1), Y(0)). 예측 = τ̂ > eps → Persuadable, τ̂ < −eps → Sleeping Dog, 그 밖은 중립(τ̂ 로는 Sure Thing·Lost Cause 를 가를 수 없다). 기본 eps = 0.
- **가드는 (가).** GATE 1 = `experiment_environment_v1_declared: true` ∧ `declaration ≠ PARTIAL_FREEZE` ∧ `simulator_commit` 기록. GATE 2 = 기록 위치·형식 **미정 → 거부**. 하나라도 미봉인이면 종료 코드 3. `--allow-unsealed` 는 합성 데이터 전용이며, 그때도 저장소의 실제 `data/ground_truth/` · `results/` 아래 경로는 거부한다.

**근거:** 달성률은 비율이므로 분자·분모의 정의가 하나여야 의미가 있다(안 A). 가드는 "봉인 전에 채점을 보지 않는다" 가 이 태스크의 존재 이유이므로, 판정할 수 없는 상태(GATE 2 기록 미정)를 허용 쪽으로 읽지 않는다.

## 기각한 안과 기각 사유

| 안 | 왜 택하지 않았나 |
|---|---|
| B (Στ 이득 곡선 oracle) | 관측 Qini 와 잡음 구조가 달라 달성률이 1 을 넘거나 표본 크기에 따라 체계적으로 치우친다. 별도 지표로 추가할 수는 있으나 "달성률" 분모로는 쓰지 않는다 |
| C (보고된 Qini 재사용) | 정의·모집단 일치를 확인할 수 없고, 시뮬 팀 소유 경로에서 `src/decision/` 의 계산을 읽어 맞춰야 한다(TEAM_SETUP §2) |
| 가드 (나) GATE 1 만 확인 | GATE 2 전에는 Baseline·예산이 아직 움직일 수 있어 채점을 보고 전략을 고치는 길이 열린다 |
| 동률을 입력 순서대로 정렬 | oracle 이 행 순서에 따라 달라진다 — 재현 불가 |

## 이 결정이 틀렸다면 어떻게 드러나나

- 봉인 뒤 실제 실행에서 oracle ≤ 0 이 흔하면(표본이 작거나 ATE 가 작아 관측 Qini 가 뒤집힘) 안 A 의 분모가 불안정한 것이다 — 그때는 안 B 를 병기한다.
- 시뮬레이터의 실제 ground truth 키가 `GT_KEYS` 와 다르면 로더가 `InputError` 로 멈춘다(조용히 0 을 내지 않는다).
- D7 이 GATE 2 기록을 정했는데 이 가드가 여전히 거부하면, `gate2_status` 를 갱신하지 않은 것이다.

## 민감도

- eps(4분면 중립 폭)를 0 → 0.02 로 바꾸면 Persuadable ↔ Sleeping Dog 오분류율이 줄고 중립 칸이 는다. 값은 리포트에 `quadrant_eps` 로 함께 싣는다.
- Qini 정규화(1인당 vs 합계)는 달성률에 영향이 없다(분자·분모가 같은 배율).

## 남은 불확실성

- **필요한 산출물: 고객별 τ̂.** 현재 스프린트 결과는 세그먼트 평균 CATE 만 남기고 고객별 τ̂ 파일이 없다. 제안 형식은 결과 디렉터리의 `cate.jsonl`/`cate.csv`(`customer_id` · `cate_T1`…`cate_T4`). 없으면 각 팔은 oracle 만 계산하고 `partial` 로 남는다. 오케스트레이션(리드)이 정한다.
- τ̂ 와 ground truth 는 `customer_id` 로만 결합한다. τ̂ 가 어느 T0 시점의 예측인지(파일 이름의 T0 와 같은지)는 τ̂ 산출 형식이 정해진 뒤 결합 키에 넣는다.
- GATE 1 의 "완전 봉인" 선언 값(`declaration`)이 아직 정의되지 않아 `PARTIAL_FREEZE` 가 **아닌** 것으로 판정한다.
- 이 기록은 합성 데이터로만 검증했다. 실제 결과에는 **실행하지 않았다.**
