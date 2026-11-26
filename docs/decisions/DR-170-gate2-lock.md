# DR-170-gate2-lock — GATE 2 봉인 기록 · S1 일수 단위 · 분기 간 대조

| | |
|---|---|
| 태스크 | 이슈 #170 (GATE 2 정식 봉인 — Rule Baseline 경로 · 예산 상한) |
| 작성 | 인성(시스템 팀 리드, 에이전트 구현) · 2026-11-26 |
| 상태 | 제안 — 광진 리뷰 뒤 확정. 봉인(서명)은 GATE 1 완전 봉인(#163) 뒤 Baseline 실행에서 광진이 한다 |
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
2. **예산 상한.** `strategies.py` 의 `planning_costs`, `run_sprint.py` 의 `C_RULE_DEFINITION` · `plan_costs` · `resolve_budget`
   지문 + Baseline 실행의 C_rule 값(`budget.c_rule_planned_krw`) ·
   처치 단가(`planning_costs_krw`) · 그 출처. 처치 단가 자체는 GATE 1 경제 파라미터 Lock 대상이라 값만 적는다.
3. **Baseline 결과.** S0 · S1 의 배정 수 · 처치 수 · 계획 비용 · 측정 계층 경제 지표(분기 창), 결과 파일(`run_meta.json` ·
   `strategy_comparison.json`) sha256, 실행 정보(run_id · repo_commit · simulator_commit · seed · 고객 수).

잠그지 않는 것: S2~S6 플래너 · `plan()` 디스패치 · 예산 배분 · What-if — GATE 3 에서 바꿀 수 있다(PRD §84).

**G3 = A.** 기록은 `config/gate2_lock.yaml`, `src/orchestration/gate2_lock.py` 의 `record()` 만 쓴다.

- CLI(RUN_DIR = Baseline 실행의 결과 폴더, TAG = 그 실행의 태그 · 커밋): `python -m src.orchestration.gate2_lock check RUN_DIR --expected-commit TAG` — 조건 · 기록 미리 보기(쓰지 않음).
  `record ... --locked-by NAME` — 기록을 쓴다. `verify` — 지금 저장소의 지문을 기록과 대조한다.
- `locked_by` 는 사람 이름이다(GATE 1 과 같은 거부 목록). **에이전트는 `record` 를 실행하지 않는다** — 서명은 광진이 한다(#170).
- `config/gate2_lock.yaml` 을 `team_boundaries.json` `lead_only` 에 넣는다(GATE 1 기록과 같은 이유).
- `verify` 상태: `not_started`(기록 없음) · `match` · `mismatch` · `unreadable`. GATE 3 동결 · GATE 4 실행 전에 돌린다.

**G4 — 봉인 조건. 모두 충족이어야 기록한다. 확인하지 못한 것(None)도 미충족이다(GATE 1 `can_lock` 과 같다).**

| ID | 조건 | 근거 |
|---|---|---|
| B-1 | 실행 커밋의 `config/gate1_lock.yaml` 이 `FULL_FREEZE` | PRD 순서 "GATE 1 봉인 → GATE 2", #170 11/13 "GATE 1 봉인 커밋에서" |
| B-2 | `provenance.repo_commit` = 지정한 커밋(태그) | #170 11/05 표 |
| B-3 | `require_clean = true` · `repo_worktree_dirty = false` | #170 11/05 표 · DR-262 |
| B-4 | `repo_changed_during_run = false` | #170 11/05 표 |
| B-5 | `provenance.null_reason` 없음 | #170 11/05 표 |
| B-6 | `rct.arm_counts` T0 ≥ 10,000 · T1~T4 합 ≥ 10,000 | DR-211 FR-05 |
| B-7 | `strategy_S0` · `strategy_S1` 단계 `ok` | PRD §83 |
| B-8 | `budget.status = ok`, 출처가 C_rule(`--budget-krw` 아님), C_rule 이 수 | DR-170 D2 · D3 |
| B-9 | 분기 간 대조(G5) = 같다 | DR-234 반증 조건 — 다르면 S0 · S1 경제 지표의 모집단이 바뀐다 |
| B-10 | 기록할 지문 = 실행 커밋의 지문(지금 저장소가 실행 커밋과 다르면 거부) | 잠그는 것은 Baseline 을 낸 코드다 |

**G5 = A.** `src/orchestration/branch_invariance.py`(`python -m src.orchestration.branch_invariance RUN_DIR`).

- 대상: (가) 비Eligible(t2) — 분기 창 이벤트가 있는 고객 중 명부(`split_roster.csv`) t2 행 밖, (나) Eligible(t2) 중 어느 분기에서도
  처치 대상이 아닌 고객(분기별 배정 파일).
- 고객별 [t2, end) 이벤트 수 · 유형별 수 · purchase 수 · purchase `order_amount` 합을 기준 분기 S0 과 다른 분기 모두에 대조한다.
  모든 분기 · 모든 고객이 같으면 `same`, 하나라도 다르면 `differs` — 그때 B-9 미충족이고 DR-234 P3 를 다시 본다(측정 계층 수치를
  Eligible 로 좁힌다).
- 결과 파일(`branch_invariance.json`)에는 고객 ID 를 넣지 않는다 — 수와 합계만. 명부 · 배정 파일 · 분기 원본 중 하나라도 없으면
  `not_run`(근사하지 않는다).

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

## 남은 불확실성

- 실행 기록(`run_meta`)에 `verify` 결과를 자동으로 싣는 것은 이번에 하지 않았다. GATE 3 동결(11/30) 전에 정한다 — 그 전까지는
  GATE 3 · 4 실행 전에 `verify` 를 돌린다.
- 분기 간 대조는 분기 원본(`branches/S0~S5/raw`)을 모두 읽는다. 5만 명 · 6분기에서 걸리는 시간은 재지 않았다.
- t2 가 KST 자정이 아닌 실행에서는 G1 의 상한 쪽도 바뀐다.
- 봉인 날짜는 GATE 1 완전 봉인(#163) 뒤다. 일정표는 봉인일이 정해진 뒤 고친다.

## 봉인 실행 뒤 기록

GATE 2 실행 뒤 여기에 적는다 — G5 결과(`same` · `differs`), B-6 `arm_counts`, `check` 결과, 서명자 · 시각 · 실행 커밋. 기록을 본 뒤
위 결정 · 조건을 고치지 않는다.
