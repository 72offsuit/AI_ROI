# DR-170-gate2-lock — GATE 2 봉인 기록 · S1 일수 단위 · 분기 간 대조

| | |
|---|---|
| 태스크 | 이슈 #170 (GATE 2 정식 봉인 — Rule Baseline 경로 · 예산 상한) |
| 작성 | 인성(시스템 팀 리드, 에이전트 구현) · 2026-11-26 |
| 상태 | 제안 — 광진 리뷰(PR #327, 11/26 · 11/27 2차 · 11/28 3차) 반영(아래 「리뷰 반영」). 재리뷰 뒤 확정. 봉인(서명)은 GATE 1 완전 봉인(#163) 뒤 Baseline 실행에서 광진이 한다 |
| 관련 | DR-170-c-rule-budget(C_rule) · DR-145-strategy-sprint(S1 규칙) · DR-234-population-experiment-scale(Eligible · P3) · DR-211-experiment-scale-config(FR-05) |

## 무엇을 정하는가

1. **G1** S1 규칙 입력 `days_since_last_purchase` 의 단위 — 시각 차(소수 일)인가, KST 날짜 차인가(DR-234 남은 불확실성).
2. **G2** GATE 2 가 무엇을 잠그나 — Baseline 규칙의 범위, 예산 상한, Baseline 결과.
3. **G3** 봉인 기록의 형식 · 쓰는 방법 · 서명.
4. **G4** 봉인 전에 모두 충족해야 하는 조건.
5. **G5** 50,000명 분기 간 대조(DR-234 P3 반증 조건)의 방법과 판정.

## 정하지 않으면 무엇이 막히나

GATE 2(PRD §83 · SRS GATE 2, v3.0)는 S0 · S1 을 실행해 결과를 저장한 뒤 Baseline Rule 을 잠근다. 그런데 저장소에 잠그는 장치가
없다 — `src/measurement/freeze.py` 는 GATE 1 전용(`gate1-lock/v1`)이고 `gate2_lock` 은 일정표(`docs/sprint_plan.md`)에만 이름이
있다. 무엇을 잠갔는지 기록이 없으면 "AI 결과를 본 뒤 Baseline Rule 을 바꾸지 않았다"(SRS BASE-003)를 GATE 3 · 4 에서 확인할 수
없다. S1 일수 단위는 DR-234 가 "봉인 전에 정한다"고 미뤘다 — 봉인 뒤에 바꾸면 Baseline 부터 다시 돌려야 한다.

## 선택지

| 결정 | 안 | 내용 |
|---|---|---|
| G1 | A | 시각 차(소수 일) 유지 |
| G1 | B | KST 날짜 차(t2 날짜 − 마지막 구매 날짜) — Eligible 과 같은 단위 |
| G2 | A | 파일 전체(`strategies.py` · `run_sprint.py`) 해시 |
| G2 | B | S1 대상 · 예산 상한을 정하는 이름(함수 · 상수)만 지문 + C_rule 값 + S0 · S1 결과 |
| G2 | C | 태그 `gate2-s1-rule`(`ce05a66`)만 |
| G3 | A | GATE 1 처럼 코드가 쓰는 YAML + 사람 서명 |
| G3 | B | 사람이 쓰는 문서(DR 표) |
| G5 | A | DR-234 방법 그대로 — 고객별 이벤트 수 · 유형별 수 · purchase 수 · 매출이 모든 분기에서 같은가 |
| G5 | B | 분기별 합계만 비교 |

## 조사한 것

| 출처 | 무엇을 말하나 | 우리 맥락에 얼마나 맞나 |
|---|---|---|
| PRD §83 · SRS GATE 2 (v3.0) | S0 · S1 을 실행하고 결과를 저장한 뒤 Baseline Rule 을 잠근다 | 잠그는 대상 = Baseline Rule + 결과. 무엇을 "Rule" 로 볼지는 적혀 있지 않다 |
| SRS BASE-002 · PRD §60 (v3.0 확정 표기) | "마지막 구매 후 28~90일 · 주문 2회 이상 → T3, 마지막 구매가 오래된 순서". 정본은 `strategies.py` `S1_RULE` 과 DR-145, GATE 2 에서 잠근다 | 규칙 값의 정본이 있다. 일수를 시각으로 셀지 날짜로 셀지는 적혀 있지 않다 |
| SRS BASE-003 | AI 결과를 본 뒤 Baseline Rule 을 바꾸지 않는다 | G1 을 결과와 무관하게 정해야 하는 이유 |
| PRD §84 · SRS GATE 3 | GATE 3 에서 바꿀 수 있는 것 — Feature · Model · Threshold · Uplift · CLV · Priority · Treatment Policy · Budget Policy | `strategies.py` · `run_sprint.py` 에 GATE 3 에서 바뀌는 코드(S2~S6 · 예산 배분)가 함께 있다 |
| DR-234 결정 · 기각 표 | Eligible 일수 = KST 날짜 차(정의가 "가입일" · "마지막 구매일"). 시각 차는 T0 − 14일 날짜의 구매를 모두 13.x 일로 봐 정의보다 하루 좁았다. 남은 불확실성: S1 일수는 아직 시각 차 — 봉인 전에 정한다 | G1 의 직접 근거. 같은 저장소의 같은 종류의 정의다 |
| DR-234 조사 표 마지막 행 · 반증 조건 | 분기 간 대조(2,000명 · small 1회, 스크래치 스크립트): 비Eligible · 어느 전략도 처치하지 않은 Eligible 고객의 분기 창 결과가 6분기에서 같았다. 다르면 P3 기각을 다시 본다 | G5 방법. 스크립트가 저장소에 없다 |
| DR-211 FR-05 | T0 ≥ 10,000 · T1~T4 합 ≥ 10,000 | G4 규모 조건 |
| #170 11/05 코멘트(PR #261 · #263 리뷰) | Baseline 으로 쓸 조건 — 규모 · 실행 커밋 = 태그 · 깨끗한 시작 · 실행 중 변경 없음 · 저장소 조회 실패 없음 | G4 |
| #170 10/22 코멘트 · DR-145 | `ce05a66`(태그 `gate2-s1-rule`)은 규칙 코드(`S1_RULE` · `plan_S1` · `plan_S0` · `s1_eligibility`)를 AI 결과 전에 고정한 증거. 대상자 입력(`s1_inputs` · eligible)은 뒤에 추가돼 선행 고정이라 쓰지 않는다 | G1 은 선행 고정 대상이 아닌 입력 계산만 바꾼다. G2 는 태그와 같은지를 사실로만 남긴다 |
| DR-170-c-rule-budget | C_rule = S1 계획 비용 합. 값의 Lock 은 GATE 2 봉인 실행의 일 | G2 예산 상한 |
| `src/measurement/freeze.py` (GATE 1) | 기록은 코드(`record()`)만 쓰고 `locked_by` 는 사람 이름("agent" 등 거부). 정본 파일 sha256. 선행 조건이 하나라도 미충족이거나 **확인하지 않았으면** 거부. 손으로 고치면 해시 대조가 실패 | G3 · G4 형식 — 같은 프로젝트의 봉인 방식을 따른다 |
| `docs/team_boundaries.json` `lead_only` | `config/gate1_lock.yaml` 은 "봉인 기록"이라 리드 전용 | `config/gate2_lock.yaml` 도 같은 이유 |

## 결정

**G1 = B. S1 일수 = KST 날짜 차(t2 날짜 − 마지막 구매 날짜).** 구현: `run_sprint.s1_inputs`(Eligible 의 `eligibility` 와 같은 계산).

- 근거: DR-234 가 Eligible 에서 시각 차를 버린 이유가 그대로다. 정의가 날짜("마지막 구매 후 N일")이고, 시각 차는 하한 쪽 하루를
  뺀다. S1 은 Eligible 안에서만 고르므로(DR-234 P2) 시각 차를 두면 한 고객의 "마지막 구매 후 일수"가 조건마다 다른 단위가 된다.
- 규칙 값(28 · 90일 · 2회 · T3 · 순서)과 `S1_RULE` · `plan_S1` 은 바꾸지 않는다 — 태그와의 본문 대조가 그대로다. 바뀌는 것은
  오케스트레이션의 입력 계산이고, 10/22 기록대로 그것은 선행 고정 대상이 아니었다.
- 영향(정의상): t2 가 KST 자정이면 하한 쪽에 t2 − 28일 날짜에 산 고객이 새로 들어오고(시각 차로는 27.x 일), 상한 쪽(t2 − 90일
  날짜)은 두 방식이 같다. 순서는 규칙 그대로(일수 내림차순, 동률은 customer_id 오름차순)인데 날짜 단위라 동률이 늘어난다. 순서는
  예산이 S1 전원보다 작을 때(S6 의 작은 예산 · What-if)만 배정을 바꾸고, S1 자체는 상한 없음이라 영향이 없다.
- 범위: S1 이 쓰는 값은 실행 루프가 `s1_inputs` 로 덮어쓴 것 하나다. 모델 Feature `recency`(와 그 별칭 열)는 모델 입력이라
  이 결정 밖이고 S1 에 쓰이지 않는다. CLI(`src/main.py`)는 S1 을 계획하지 않는다(S5 예산 배분만).

**G2 = B. 잠그는 것은 세 묶음이다.**

1. **Baseline 규칙 — S1 대상을 정하는 이름.** `strategies.py` 의 `S1_RULE` · `plan_S0` · `s1_eligibility` · `plan_S1` ·
   `within_eligible` · `_missing` · `_as_mapping` · `REQUIRED_SCORES["S1"]`, `run_sprint.py` 의 `ELIGIBLE_MIN_TENURE_DAYS` ·
   `ELIGIBLE_MIN_ORDERS` · `ELIGIBLE_MIN_DAYS_SINCE_PURCHASE` · `_timestamps` · `_kst_dates` · `eligibility` · `s1_inputs`.
   - 지문: 함수는 소스 구간 그대로의 sha256(문서 문자열 · 안쪽 주석 포함 — 한 글자라도 바뀌면 다르다. GATE 1 의 파일 해시와 같은
     엄격함), 리터럴 상수는 값의 정규 JSON sha256(값이 같으면 같다 — 상수는 값이 곧 동작이다).
   - 태그 `gate2-s1-rule` 과의 대조: 태그에 있는 이름(`S1_RULE` · `plan_S0` · `s1_eligibility` · `plan_S1` 등)이 같은지를
     사실로만 적는다. 같아야 한다는 조건은 두지 않는다 — 10/22 기록이 고정했다고 쓴 범위가 규칙 코드뿐이기 때문이다.
     2026-11-26 대조: `S1_RULE` · `plan_S0` · `s1_eligibility` · `plan_S1` · `_missing` · `_as_mapping` 이 태그와 같다. 나머지는
     태그에 없다(뒤에 추가된 입력 계산 · 상수).
2. **예산 상한.** `strategies.py` 의 `planning_costs`, `run_sprint.py` 의 `C_RULE_DEFINITION` · `plan_costs` ·
   `assignment_planned_cost`(처치별 배정 수 × 고객당 계획 비용 합 — S1 이면 C_rule) · `resolve_budget` 지문(모두 20개 이름)
   + Baseline 실행의 C_rule 값(`budget.c_rule_planned_krw`) ·
   처치 단가(`planning_costs_krw`) · 그 출처. 처치 단가 자체는 GATE 1 경제 파라미터 Lock 대상이라 값만 적는다.
3. **Baseline 결과.** S0 · S1 의 배정 수 · 처치 수 · 계획 비용 · 측정 계층 경제 지표(분기 창), 결과 파일(`run_meta.json` ·
   `strategy_comparison.json`) sha256, 실행 정보(run_id · repo_commit · simulator_commit · seed · 고객 수).
   - 실측 경제 지표 중 **반드시 있어야 하는 것** = `revenue` · `marketing_cost` · `contribution_profit`(`gate2_lock.REQUIRED_MEASURED`
     = `run_sprint.MEASURED_KEYS`, 시험이 대조). 근거: 실행 루프가 이 셋을 `measured_revenue` · `measured_marketing_cost` · `measured_contribution_profit` 으로 비교(`roi.summarize_strategy`)에
     넘기고 비교는 이 값을 가장 먼저 쓴다(`roi.CANDIDATES`). 하나라도 없으면 비교는 시뮬레이터 값이나 계획 비용으로 내려가고, 그러면
     잠근 Baseline 이 측정 계층 실측이 아니다. 나머지 지표(cogs 등)는 상태 그대로 기록만 한다.
   - 허용 상태: 분기의 정식 경제 입력 관측(`economics_input_observation`)이 `ok`, `measured_economics.status` 가 `ok`, 세 지표 각각
     `ok` 이고 유한한 수. `not_run`(교환 묶음 · 읽기 근거 없음) · `failed` · `quality_failed`(분기 창 DQ-09 · DQ-02b 실패 — 값은 남아도
     실행 루프의 `measured_value` 가 꺼내지 않는다, #237) 는 봉인하지 않는다(B-7).

잠그지 않는 것: S2~S6 플래너 · `plan()` 디스패치 · 예산 배분 · What-if — GATE 3 에서 바꿀 수 있다(PRD §84).

**G3 = A.** 기록은 `config/gate2_lock.yaml`, `src/orchestration/gate2_lock.py` 의 `record()` 만 쓴다.

- CLI(RUN_DIR = Baseline 실행의 결과 폴더, TAG = 그 실행의 태그 · 커밋): `python -m src.orchestration.gate2_lock check RUN_DIR --expected-commit TAG` — 조건 · 기록 미리 보기(쓰지 않음). 조건이 하나라도 충족이 아니면 종료 코드 1.
  `record ... --locked-by NAME` — 기록을 쓴다. `verify` — 지금 저장소의 지문을 기록과 대조한다.
- `locked_by` 는 사람 이름이다(GATE 1 과 같은 거부 목록). **에이전트는 `record` 를 실행하지 않는다** — 서명은 광진이 한다(#170).
- `config/gate2_lock.yaml` 을 `team_boundaries.json` `lead_only` 에 넣는다(GATE 1 기록과 같은 이유).
- `verify` 상태: `not_started`(기록 없음) · `match` · `mismatch` · `unreadable`. 지금 잠그는 이름이 기록에 없으면(`not_in_record`)
  대조하지 않은 것이라 `mismatch` 다. GATE 3 동결 · GATE 4 실행 전에 돌린다.

**G4 — 봉인 조건. 모두 충족이어야 기록한다. 확인하지 못한 것(None)도 미충족이다(GATE 1 `can_lock` 과 같다).**

| ID | 조건 | 근거 |
|---|---|---|
| B-1 | 실행 환경 = GATE 1 봉인: 실행 커밋의 `config/gate1_lock.yaml` 이 `FULL_FREEZE`, 기록의 `simulator_commit` = 실행 `provenance.simulator_commit`(어느 쪽이든 없으면 미충족), `LOCKED` 항목마다 GATE 1 공용 계약 `freeze.LockItem` 이 서고(비어 있지 않은 정본 목록 — 경로 문자열 — 과 범위 문장, 아니면 미충족 · 근거에 항목 이름), 그 정본이 **모두** 기록에 해시가 있고(`freeze.verify` 의 "LOCKED 항목의 정본인데 기록에 해시가 없다"와 같은 판정, 항목 목록이 없거나 LOCKED 정본이 없어도 미충족), 기록의 정본 파일(`canonical_files`) 해시 = **실행 커밋**의 그 파일 해시(`freeze.file_sha256`) | PRD 순서 "GATE 1 봉인 → GATE 2", #170 11/13 "GATE 1 봉인 커밋에서", #213 "S0 · S1 Baseline 결과가 GATE 1 봉인 환경(`simulator_commit`)에서 나왔는지" |
| B-2 | `provenance.repo_commit` = 지정한 커밋(태그) | #170 11/05 표 |
| B-3 | `require_clean = true` · `repo_worktree_dirty = false` | #170 11/05 표 · DR-262 |
| B-4 | `repo_changed_during_run = false` | #170 11/05 표 |
| B-5 | `provenance.null_reason` 없음 | #170 11/05 표 |
| B-6 | `rct.arm_counts` T0 ≥ 10,000 · T1~T4 합 ≥ 10,000 | DR-211 FR-05 |
| B-7 | `strategy_S0` · `strategy_S1` 단계 `ok`, 같은 실행(`run_id`)의 `strategy_comparison.json` 이 있고 S0 · S1 상세에 배정 수 · 계획 비용이 있으며, S0 · S1 모두 실측 경제 지표 3종이 허용 상태(G2 3)다 | PRD §83 "S0 · S1 을 실행하고 결과를 저장" · G2 3(잠그는 결과에 실측 경제 지표가 있다) — 측정이 빠진 Baseline 을 잠그면 S1 대비 증분이익의 기준선이 비어 있다 |
| B-8 | `budget.status = ok`, 출처가 C_rule(`--budget-krw` 아님), C_rule = 결과 파일의 S1 계획 비용 = S1 처치별 배정 수 × 처치 단가(`planning_costs_krw`) 합 | DR-170 D2 · D3 — 기록할 C_rule 이 실제 S1 배정에서 나왔는지 원천끼리 대조한다 |
| B-9 | 같은 실행의 분기 간 대조(G5)가 봉인 대상 분기 S0~S5 를 **모두** 대조했고(`complete`) 결과가 같다 | DR-234 반증 조건(6분기) — 다르면 S0 · S1 경제 지표의 모집단이 바뀐다. 빠진 분기가 있으면 판정할 수 없다 |
| B-10 | 기록할 지문 = 실행 커밋의 지문(지금 저장소가 실행 커밋과 다르면 거부) | 잠그는 것은 Baseline 을 낸 코드다 |

**G5 = A.** `src/orchestration/branch_invariance.py`(`python -m src.orchestration.branch_invariance RUN_DIR`).

- 대상: (가) 비Eligible(t2) — 분기 창 이벤트가 있는 고객 중 명부(`split_roster.csv`) t2 행 밖, (나) Eligible(t2) 중 어느 분기에서도
  처치 대상이 아닌 고객(분기별 배정 파일).
- 고객별 [t2, end) 이벤트 수 · 유형별 수 · purchase 수 · purchase `order_amount` 합을 기준 분기 S0 과 다른 분기 모두에 대조한다.
  모든 분기 · 모든 고객이 같으면 `same`, 하나라도 다르면 `differs` — 그때 B-9 미충족이고 DR-234 P3 를 다시 본다(측정 계층 수치를
  Eligible 로 좁힌다).
- 대조할 분기 = 실행 루프가 만드는 분기 전부(`run_sprint.STRATEGIES` = S0~S5, 시험이 대조). S6 은 분기를 만들지 않는다(분기 실측은
  #305). 하나라도 단계가 `ok` 가 아니거나 배정 파일 · 원본이 없으면 `incomplete` 와 빠진 분기 · 사유 — 있는 분기만으로 `same` 을 내지
  않는다. 명부가 없으면 `not_run`. 결과에 `run_id` 를 싣는다(B-9 가 같은 실행인지 대조).
- **원본이 실행 당시와 같은지 다시 대조한다.** 경로가 있다는 것만으로는 파티션이 빠졌는지 모른다. 분기마다:
  1. 같은 실행의 `strategy_comparison.json` 에 남은 분기 읽기 근거(`event_read_evidence`, 실행 당시 `verify_event_run` 결과)가
     `ok` 이고 실행 ID 가 있어야 한다.
  2. 그 실행 ID 로 `verify_event_run` 을 다시 돌린다 — 실행 기록의 파일 목록 · 다이제스트 · 행 수와 디스크가 같은지, 기록하지
     않은 파티션이 없는지. 실행 루프(`_branch_proof`)처럼 분기 루트만으로 먼저 보고, 안 되면 본선 t2 읽기 근거를 외부 부모로 넘긴다.
  3. 결과 파일에 남은 행 수 · 파일 수 · 파일별 크기가 지금과 같아야 한다(분기 루트의 실행 기록까지 함께 바뀐 경우를 잡는다).
     mtime 은 결과 폴더를 옮기면 바뀌므로 대조하지 않는다 — 내용은 2의 다이제스트가 본다.
  4. 읽은 뒤 파일 크기 · mtime 이 재검증 때와 같아야 한다(실행 루프 `_unchanged_files` 와 같다).
  5. **내용이 실행 당시와 같아야 한다(3차 리뷰).** 실행 루프의 통제된 분기 읽기는 이미 내용 근거를 남긴다 —
     `public_stream_content` = `event_content_digest(본선 t2 행 지문 + 분기 행 지문)`, `history_content` = 본선 t2 행 지문의
     다이제스트(공개 22필드 `event_content_hash`, 행 순서 무관 · 중복 유지). 대조할 때 본선 t2 원본(`event_read_evidence.t2.root`)과
     분기 원본을 같은 함수로 다시 해시해 둘 다 같아야 한다. 분기 행 지문은 서명을 만드는 **같은 한 번의 읽기**에서 낸다(대조한 행과
     센 행이 다를 틈이 없다). 근거가 없거나(통제된 분기 읽기가 아닌 읽기) 본선 원본 경로를 모르면 대조할 수 없으므로 `incomplete`.
     2 · 3 만으로는 지금의 디스크와 지금의 실행 기록이 서로 맞는지 · 크기만 본다 — 같은 크기로 값만 바꾸고 실행 기록을 다시 쓰면
     통과했다. 새 해시를 결과에 더 남기지 않고 이미 있는 근거를 쓴 이유: 실행 루프가 분기 읽기를 받아들일 때 쓴 바로 그 값이라
     기준이 둘이 되지 않고, 결과 파일 형식을 바꾸지 않는다. 본선 원본은 t2 뒤로 쓰이지 않는다(분기는 각자 `branches/S0~S5/raw` 로
     복원 · 진행한다) — 그래서 본선 다이제스트를 다시 낼 수 있다.
  하나라도 어긋나면 그 분기는 `incomplete` 다. 근거: `src/decision/observation_contract.verify_event_run` 이 실험 입력 검증의 단일
  구현이고(#179), 실행 루프도 같은 함수로 분기 읽기를 받아들였다 — 대조 때 다른 기준을 쓰면 실행 때 받아들인 원본과 대조한 원본이
  다를 수 있다.
- 결과 파일(`branch_invariance.json`)에는 고객 ID 를 넣지 않는다 — 수와 합계만. 근사하지 않는다.

## 기각한 안과 기각 사유

| 안 | 왜 택하지 않았나 |
|---|---|
| G1 A 시각 차 유지 | 정의보다 하루 좁고 Eligible 과 단위가 갈린다(DR-234 와 같은 이유). "봉인 대상이라 바꾸지 않는다"(DR-234 당시 사유)는 봉인 전인 지금은 성립하지 않는다 |
| G2 A 파일 전체 해시 | GATE 3 에서 바꿀 수 있는 S2~S6 · 예산 배분 코드가 같은 파일에 있다 — GATE 3 작업마다 봉인이 깨져 대조가 의미를 잃는다 |
| G2 C 태그만 | 태그는 규칙 코드의 선행 고정 증거다. 입력 계산(`s1_inputs` · `eligibility`) · C_rule 값 · 결과를 담지 않는다 |
| G3 B 사람이 쓰는 문서 | 손으로 옮기면 값이 틀려도 모른다 — GATE 1 이 코드 기록을 택한 이유와 같다 |
| G5 B 합계만 | 고객 사이의 증감이 상쇄되면 같아 보인다. DR-234 는 고객별로 대조했다 |
| 분기 간 대조를 참고로만(봉인 조건에서 뺀다) | 다르면 측정 계층 수치의 모집단이 바뀌어 S0 · S1 경제 지표가 달라진다 — 그 결과를 잠글 수 없다 |
| 지문을 실행 뒤 지금 저장소에서 계산 | 실행과 서명 사이에 다른 PR 이 들어오면 Baseline 을 내지 않은 코드를 잠그게 된다(B-10) |

## 노출 기록

- S1 · AI 비교 결과는 개발 실행(11/16 사전 실행 CLI 요약, 11/17 시연 실행 대시보드 — DR-170-c-rule-budget 「노출 기록」)에서 봤다.
  **일수 단위별 S1 결과나 비교는 어느 실행에서도 내 보지 않았다.** G1 은 정의(DR-234 와 같은 해석)만으로 정했다.

## 이 결정이 틀렸다면 어떻게 드러나나

- **G1:** PRD §60 의 "마지막 구매 후 28~90일"을 시각 기준으로 읽어야 할 근거(예: 실제 캠페인 도구의 판정 방식 자료)가 나오면 틀렸다.
  봉인 전이면 고치고, 봉인 뒤면 해제 절차(사용자 승인 · Baseline 재실행)를 탄다.
- **G2 범위가 좁았다:** GATE 3 · 4 실행의 S1 배정 수가 같은 seed · 같은 판의 Baseline 과 다른데 `verify` 가 `match` 면, 잠그지 않은
  코드가 S1 대상을 바꾼 것이다. 그 이름을 더하고 기록 판을 올린다.
- **G2 범위가 넓었다:** GATE 3 작업이 잠근 이름을 고쳐야 하면(예: Eligible 정의 결함) 넓었던 것이다. 그때도 조용히 고치지 않고
  해제 절차를 탄다.
- **G5:** 5만 명에서 `differs` 면 DR-234 P3 기각이 틀렸다(DR-234 반증 조건).
- **B-6:** `arm_counts` 가 미달이면 DR-211 비율 가정이 틀렸다 — DR-211 대로 고객 수를 다시 계산한다.

## 민감도

- **G1 하한 하루:** 날짜 기준 28~90일은 63일, 시각 기준은 사실상 62일이다. 마지막 구매일이 구간 안에 고르게 퍼져 있다고 가정한
  산술로 S1 대상이 약 1/62 ≈ 1.6% 늘고 C_rule 도 같은 비율로 는다(실측 아님). AI 예산도 C_rule 이라 같은 비율로 움직인다
  (DR-170-c-rule-budget 민감도와 같은 구조).
- **G2 지문 방식:** 잠근 함수의 문서 문자열이나 주석만 고쳐도 `mismatch` 다. 봉인 뒤 그 이름을 손대지 않는 것이 규칙이라 엄격한
  쪽을 택했다.
- **B-6 10,000:** FR-05 고정값이다.

## 리뷰 반영(2026-11-26, PR #327 광진 리뷰 — `166e71e` 에서 찾은 반례)

| 리뷰 | 반례 | 바꾼 것 |
|---|---|---|
| B-9 는 봉인 대상 분기가 모두 확인된 경우에만 | 6분기 중 다른 S2 의 원본을 빼면 `differs` 가 `same` 이 됐다. 미실행 분기는 건너뛴 목록에도 없었다 | G5 · B-9 — 필수 분기(S0~S5) · 단계 `ok` · `complete` · 같은 `run_id` |
| B-1 은 실제 실행 환경이 GATE 1 봉인과 일치하는지 | GATE 1 기록을 둔 채 기록에 든 경제 설정만 바꾼 커밋에서 B-1 이 통과했다 | B-1 — `simulator_commit` 대조 · 정본 해시를 실행 커밋 기준으로 |
| Baseline 결과 파일과 C_rule 원천 | `strategy_comparison.json` 이 없어도 `check` 가 0 이었고, 결과 파일의 S1 계획 비용만 바꿔도 B-8 이 통과했다 | B-7 · B-8 — 결과 파일 · S0 · S1 상세 · C_rule 원천 대조, 기록 시 결과 파일 해시가 없으면 거부 |
| 지문이 실제 합산식과 필수 이름 전체를 | `run()` 안 합산식만 바꿔 C_rule 이 21,090원에서 31,090원이 돼도 B-10 · `verify` 가 통과했다. 기록에서 이름 하나를 빼도 `verify` 가 `match` 였다 | 합산식을 `assignment_planned_cost` 로 떼어 잠근다(S2~S6 범위는 그대로). 필수 이름이 기록에 없으면 `mismatch` |

### 2차(2026-11-27, `04e0a34` 에서 찾은 반례)

| 리뷰 | 반례 | 바꾼 것 |
|---|---|---|
| 분기 원본은 존재 여부와 함께 실제 파티션의 완전성까지 | 단계 · 원본 경로가 모두 살아 있는 채 S2 에서 비Eligible 고객의 차이가 든 파티션 하나만 빼면 `differs` 가 `same` · `complete` 가 됐고 `check` 가 0 이었다 | G5 — 결과 파일의 분기 읽기 근거 · `verify_event_run` 재검증 · 파일 목록 · 크기 · 행 수 대조, 어긋나면 `incomplete`(B-9 미충족) |
| B-1 은 GATE 1 LOCKED 항목이 요구하는 해시도 모두 | LOCKED 항목의 정본 둘 중 경제 설정의 해시 하나만 기록에서 빠진 GATE 1 기록에서 `freeze.verify` 는 `mismatch` 였는데 B-1 은 통과했다 | B-1 — 대조 대상 = 기록의 `canonical_files` ∪ LOCKED 항목의 정본, 기록에 해시가 없으면 미충족. 항목 목록이 없거나 LOCKED 정본이 없어도 미충족 |
| 실측 경제 지표가 생성되지 않은 Baseline 을 B-7 에서 | 교환 묶음을 받지 못해 `branch_economics` 가 `not_run` 이고 S1 실측 값이 `{}` 여도 `check` 가 0 이었다 | G2 3 · B-7 — 필수 지표 3종 · 허용 상태를 정하고 S0 · S1 모두 검사 |

### 3차(2026-11-28, `0199c80` 에서 찾은 반례)

| 리뷰 | 반례 | 바꾼 것 |
|---|---|---|
| B-9 는 원본의 **내용**을 실행 당시 근거와 대조 | S2 주문액만 12,500원 → 12,000원으로 바꾼 같은 크기의 파티션과 그 내용에 맞춘 실행 기록을 두니, 실행 당시 `strategy_comparison.json` 을 그대로 두었는데도 `differs` 가 `same` 이 되고 `check` 가 0 이었다 | G5 5 — 실행 당시 `public_stream_content` · `history_content` 를 본선 · 분기 원본에서 다시 계산해 대조, 어긋나거나 근거 · 본선 경로가 없으면 `incomplete`(B-9 미충족) |
| B-1 은 LOCKED 항목마다 정본 목록을 | 한 LOCKED 항목의 목록만 빼고 다른 항목의 정본과 일치하는 해시를 남기면 B-1 이 통과했다(`canonical_files or ()` 가 그 항목을 건너뛰었다) | B-1 — LOCKED 항목마다 `freeze.LockItem` 을 세운다: 목록 없음 · 빈 목록 · 문자열 · 경로가 아닌 원소 · 범위 문장 없음이면 미충족(항목 이름) |

결과(실측)를 보고 바꾼 것이 아니다 — 합성 반례로 드러난 검사의 빈틈이다. 각 반례는 시험(`tests/test_strategy_gate2_lock.py` ·
`tests/test_strategy_branch_invariance.py`)으로 남겼다.

## 남은 불확실성

- 실행 기록(`run_meta`)에 `verify` 결과를 자동으로 싣는 것은 이번에 하지 않았다. GATE 3 동결(11/30) 전에 정한다 — 그 전까지는
  GATE 3 · 4 실행 전에 `verify` 를 돌린다.
- 분기 간 대조는 분기 원본(`branches/S0~S5/raw`)을 모두 읽는다. 2차 리뷰 뒤로는 읽기 전에 `verify_event_run` 이 파티션을 한 번 더
  전부 읽는다(행 수 · 다이제스트). 3차 리뷰 뒤로는 본선 t2 원본도 한 번 읽어 행 지문을 낸다(분기 행 지문은 서명과 같은 읽기).
  5만 명 · 6분기에서 걸리는 시간은 재지 않았다.
- **가설 H-B7(결과 전, 2026-11-27):** 5만 명 Baseline 실행에서 S0 · S1 모두 필수 실측 지표 3종이 `ok` 로 나온다. 근거는 코드
  경로뿐이다 — 교환 묶음이 `ok` 이고 분기 창 품질 검사가 통과하면 `branch_economics` 가 `ok` 를 낸다. 처치가 없는 S0 의
  `marketing_cost` 는 코드상 `ok`(0원)다 — 구성 요소 셋(`economics.message_cost` = 발송 수 × 단가, `coupon_cost` = 쿠폰이 쓰인
  주문만 합산, `campaign_fixed_cost` = 실행 캠페인 수 × 고정비)이 해당 이벤트 0건이면 모두 `ok` 0 을 낸다. 예외는 `coupon_use` 가
  있는데 실제 할인액도 쿠폰 처치 ID 도 없는 주문으로, 그때 `coupon_cost` 가 계산 불가(#108)가 되어 B-7 이 막는다 — S0 세계에 그런
  주문이 생기는지는 실측으로 확인하지 않았다. 광진 3차 리뷰(11/28)가 공용 측정 함수에 정상 무처치 합성 입력을 넣어 실측
  마케팅비 `ok` 0원과 B-7 통과를 확인했다 — 코드 경로의 근거이고 5만 명 실측은 아니다. **평가:** Baseline 실행 뒤 `check` 의 B-7 근거 줄. 하나라도
  `ok` 가 아니면 먼저 원인(교환 묶음 · DQ)을 고친다. 구조적으로 `ok` 가 될 수 없는 지표로 드러나면 그 사실과 근거를 여기 적고 리뷰를
  받은 뒤 필수 목록을 고친다 — 지표 값이 아니라 상태만 보고 정한다.
- B-1 은 GATE 1 기록의 LOCKED 정본 해시가 빠짐없이 있는지까지 본다. 기록 전체의 불변식(9종 · 선언 유도 · 서명 증거)은 다시 보지
  않는다 — 그것은 GATE 1 `freeze.verify`(`gate1_lock_items`)의 몫이고, 봉인 전 GATE 1 `verify` 가 `match` 인지 함께 확인한다.
- t2 가 KST 자정이 아닌 실행에서는 G1 의 상한 쪽도 바뀐다.
- 봉인 날짜는 GATE 1 완전 봉인(#163) 뒤다. 일정표는 봉인일이 정해진 뒤 고친다.

## 봉인 실행 뒤 기록

GATE 2 실행 뒤 여기에 적는다 — G5 결과(`same` · `differs`), B-6 `arm_counts`, `check` 결과, 서명자 · 시각 · 실행 커밋. 기록을 본 뒤
위 결정 · 조건을 고치지 않는다.
