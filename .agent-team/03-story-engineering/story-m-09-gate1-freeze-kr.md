---
story_key: M-09
epic: 범위 M — 측정 계층 (이슈 #42)
issue: "#49"
title: GATE 1 Freeze 절차 + 부분 봉인 — freeze.py · gate1_checklist.md · gate1_lock.yaml
status: done   # W5 Phillip 완료 — AC-1~7. D-2 결정으로 G-10 닫고 GATE 1 부분 봉인 실행(PARTIAL_FREEZE · LOCKED 0종 · locked_by=Danto7632). 탐지 3층 일치
owner: Phillip (W5-B)
phase: 4
blocked_by: ["M-01", "M-02", "M-03", "M-04", "M-06", "M-07", "M-08 (Lock 최종 검산)"]
blocks: []
user_decisions_required: ["D-2", "D-3", "D-4", "D-7", "D-8", "D-26"]
source_hash: a20dd972916f0565
source_files: 17
---

# M-09 · GATE 1 Freeze 절차 + 부분 봉인 (`#49`)

> **이 파일만 읽고 구현한다.** 인용에는 전부 `[Source: 경로#절]` 을 붙였다.

---

# 0. 작업 전 — 매번 확인하는 3줄 *(task-graph §3 T3.2)*

| # | 절대 제약 | 어기면 |
|---|---|---|
| **①** | **git·이슈 권한은 L1(제안만)이다.** commit·push 는 사용자가 **"커밋해"/"푸시해"** 를, 이슈 생성·수정·PR 은 **"이슈 만들어"/"PR 올려"** 를 명시한 뒤에만. **승격을 스스로 추론하지 않는다.** merge · Issue close · 브랜치 삭제 · `push --force` · `reset --hard` · `rebase` 는 **항상 개별 승인**. `main` 직접 커밋 금지 · `git add -A` 금지(경로 명시) · `git add Plan` 금지 | 사용자 결정을 대신한 것이 된다 |
| **②** | **`Ecommerce_Service` 파일 변경 0건.** 별도 저장소이고 사용자가 명시적으로 제외했다. **읽기는 허용**된다. 편집이 필요해지면 **멈추고 보고한다** | charter §5 위반 |
| **③** | **결손을 0 으로 채우지 않는다.** 명시적으로 기록하고 의존 지표는 **계산 불가로 표시**한다. **미실행 검증을 통과로 표시하지 않는다** — 실행 불가는 `BLOCKED` 로 **이유와 함께** | ★ **이 프로젝트의 USP-1 이 끝난다** |

`[Source: AGENTS.md#반드시-지킬-것]` · `[Source: docs/GIT_WORKFLOW.md#6]` · `[Source: .agent-team/00-plan/charter.md#6.1]` · `[Source: .agent-team/00-plan/task-graph.md#3 W3]`

---

# 1. 메타

| | |
|---|---|
| **대상 이슈** | `#49` — OPEN (2026-09-11 라이브 확인) |
| **담당** | Phillip · W5-B |
| **Phase** | **4 — 마지막** |
| **차단** | 앞의 모든 스토리 + 사용자 결정 **D-2·D-3·D-4·D-7·D-8** |
| **커밋 type** | `docs` (체크리스트) + `feat` (`freeze.py`) — **분리 권장** |

> ## ★★ C1 은 GATE 1 을 **통과시키지 않는다**
> `#49` 본문이 스스로 못박았다:
> - *"나머지 Lock 항목(Persona·Hidden Trait·행동 규칙·Churn 정의·Treatment 반응)은 **범위 B/C 완료 후 추가**한다는 점 명시"*
> - *"미확정(나중에): **GATE 1 전체 통과 선언은 범위 B·C 완료 후**"*
>
> **C1 이 하는 것은 부분 봉인(Partial Freeze)이다:**
> ① 측정 계층이 소유한 Lock 대상을 봉인한다
> ② 나머지 항목을 **"봉인 대기"로 명시적으로 기록**한다
> ③ **`EXPERIMENT_ENVIRONMENT_v1` 선언(PRD §82)을 하지 않는다**
>
> **"GATE 1 통과"라고 적지 않는다. 어디에도.**
> `[Source: .agent-team/03-service-planning/gate1-lock-scope.md#1]` · `[Source: .agent-team/04-architecture/gate1-freeze-procedure.md#6]`

---

# 2. 스토리

> **`P-리드`**(사이클 리드)**로서 나는 누가 언제 무엇을 어느 범위까지 Lock 했는지 추적하고 싶다.**
> 왜냐하면 **부분 Lock 은 시간이 지나면 "전체를 Lock 했다"로 읽히기** 때문이다.
> `[Source: .agent-team/03-service-planning/user-stories.md#US-16]`

> **`P-팀`으로서 나는 Lock 버튼을 누르기 전에 무엇을 확인해야 하는지 목록으로 갖고 싶다.**
> 왜냐하면 Lock 이후의 변경 비용이 **전 데이터 재생성 + 전 전략 재실행**이기 때문이다.
> `[Source: .agent-team/03-service-planning/user-stories.md#US-17]`

---

# 3. 인수 조건 (AC)

## AC-1 · 산출물 — 사람용과 기계용을 **나눈다**

- [ ] **`docs/gate1_checklist.md`** — 절차·선행 조건·범위 한정 문구·해제 절차 (`#49` 지정 이름 · 언더스코어)
- [ ] **`config/gate1_lock.yaml`** — Lock 기록 (해시·커밋·KST 시각·주체·9종 항목). **커밋한다**
- [ ] `src/measurement/freeze.py` — 기록 작성 · 해시 대조
- [ ] `tests/test_freeze.py`

> **왜 나누나:** 체크리스트만 있으면 사람이 읽고 넘어간다. 기계 기록만 있으면 왜 그렇게 정했는지가 사라진다.
> **해시 대조는 사람이 할 수 없고, 판단은 기계가 할 수 없다.**

## AC-2 · Lock 기록의 필수 항목

- [ ] `declaration: PARTIAL_FREEZE` — **`FULL_FREEZE` 가 아니다**
- [ ] `experiment_environment_v1_declared: false`
- [ ] `locked_at` **KST**(`+09:00`) · `locked_by`(사람 이름) · `repo_commit`
- [ ] `simulator_commit: null` + `simulator_commit_null_reason: PRECONDITION_MISSING` — ★ **`""`·`"unknown"`·`"0"` 으로 채우지 않는다**
- [ ] **PRD §22 Lock 9종 전부**가 항목으로 존재한다 (Lock 하지 않는 것도)
- [ ] `PARTIAL` 인 항목에 **`scope_note` 필수**
- [ ] 정본 파일 경로 + **SHA-256**
- [ ] `blocked:` 블록 — 검사하지 못한 것
- [ ] `release_procedure` — `FREEZE-003`

## AC-3 · 체크리스트 (`docs/gate1_checklist.md`)

- [ ] 선행 조건 **G-1 ~ G-16** 이 있고 각 항목에 현재 상태·증거가 기록된다
- [ ] **하나라도 미충족이면 Lock 하지 않는다**는 규칙이 명시된다
- [ ] Lock 전 조건이 **아닌** 것이 구분되어 있다 — **조건을 부풀리지 않는다**
- [ ] 항목별 상태가 **`LOCKED` / `PARTIAL` / `PENDING` / `BLOCKED` / `OUT_OF_SCOPE`** 로 기록된다
- [ ] **미봉인 5종과 사유**가 기록된다
- [ ] **`BLOCKED` 항목이 사유와 함께** 기록된다
- [ ] **`EXPERIMENT_ENVIRONMENT_v1` 선언을 하지 않는다**는 사실이 명시된다
- [ ] `python3 -m unittest discover -s tests` 전건 통과가 조건에 포함된다
- [ ] `python3 scripts/gen_event_schema_doc.py` 출력이 `docs/event_schema.md` 와 일치함이 조건에 포함된다

## AC-4 · 탐지 3층 ★

- [ ] **1층** `tests/test_freeze.py` — **실패한다.** 경고가 아니다
- [ ] **2층** `publish.py` 게시 시점 대조 → `freeze_status.json`
- [ ] **3층** 대시보드 V6
- [ ] **세 층이 같은 함수를 쓴다** — `freeze.verify(lock_record) -> FreezeVerification`. 판정이 갈리지 않는다

## AC-5 · ★ Lock 기록이 없을 때 조용히 통과하지 않는다

- [ ] `test_locked_files_unchanged` 가 **skip 하지 않는다.** `overall == "not_started"` 임을 **단언**한다
- [ ] 그 상태가 **대시보드 V6 에 `not_started` 로 표시**된다
- [ ] `test_simulator_commit_is_null_with_reason` — `""`·`"unknown"`·`"0"` 이면 **실패**
- [ ] `test_no_full_freeze_in_c1` — `declaration != "FULL_FREEZE"` ∧ `experiment_environment_v1_declared == false`
- [ ] `test_partial_lock_has_scope_note` — `PARTIAL` 항목에 `scope_note` 가 비어 있지 않다

## AC-6 · 게시 (`freeze_status.json`)

- [ ] Lock **9종 전부** (`minItems: 9`, `maxItems: 9`)
- [ ] 각 항목에 **`scope_note` 필수**
- [ ] `verification` **4값** — `match`/`mismatch`/`missing`/**`not_run`**. **대조를 실행하지 않았으면 `not_run` 이고 통과가 아니다**
- [ ] `overall` 의 **C1 도달 가능 최대치는 `partial`**
- [ ] **불일치일 때 게시를 막지 않는다** — `notices` 에 `level: "failure"` (§4.6)

## AC-7 · 회귀 없음

- [ ] `python3 -m unittest discover -s tests` — 기준선 46건 회귀 0
- [ ] `python3 -m unittest tests.test_isolation -v` — 통과
- [ ] `python3 .agent-team/04-architecture/tools/check_ownership.py` — PASS

---

# 4. 개발 컨텍스트 (`developer_context`)

## 4.1 ★ PRD §22 Lock 9종 — C1 가능/불가 분류

| # | Lock 항목 | C1 | 소유 파트 |
|---|---|---|---|
| 1 | `SERVICE v1` | ❌ **불가** | 커머스 |
| 2 | `CUSTOMER PERSONA v1` | ❌ **불가** | simulator |
| 3 | `HIDDEN TRAIT RULE v1` | ❌ **불가** | simulator |
| 4 | `BEHAVIOR RULE v1` | ❌ **불가** | simulator |
| 5 | `ECONOMIC RULE v1` | ✅ **조건부 가능** | **measurement** |
| 6 | `CHURN DEFINITION v1` | ⚠️ **부분 가능** | measurement + simulator |
| 7 | `TREATMENT RESPONSE v1` | ❌ **불가** | simulator |
| 8 | `EVENT SCHEMA v1` | ✅ **조건부 가능** | **measurement** |
| 9 | `KPI DEFINITION v1` | ⚠️ **부분 가능** | **measurement** |

**Lock 불가 5종 · 부분/조건부 4종 · 완전 Lock 0종.**
**측정 계층이 소유한 4종이 정확히 "부분/조건부 가능"에 대응한다** — 우연이 아니라 범위의 결과다.
`[Source: .agent-team/03-service-planning/gate1-lock-scope.md#4]`

### `EVENT SCHEMA v1` — 범위를 **좁혀서** Lock

| Lock 한다 | Lock 하지 않는다 |
|---|---|
| `events` 테이블 **22개 컬럼** | **나머지 6개 테이블** — `customers`·`orders`·`order_items`·`products`·`marketing_actions`·`assignment` |
| `event_type` **16종** | 저장 형식(Parquet) 검증 — **`BLOCKED`** |
| 이벤트별 Nullable 매트릭스 (16×15) | |
| **식별자 정규식 9종** — G-3 충족 후 | |
| **`category` 5종 · `page_type` 8종** — G-1·G-2·G-4 후 | |
| **타임존 정책** — G-5 후 | |
| 금지 필드 25종 | |
| Observable 16개 지표 ↔ 이벤트 매핑 | |
| **파생 상태 기록 경로** — G-8 후 | |

> **6테이블을 제외하는 이유:** `data_spec` §7.1 이 요구하지만 **`sink.py` 는 `events` 만 구현했다. 정의되지 않은 것을 Lock 할 수 없다.**
> **→ 체크리스트에 "`EVENT SCHEMA v1` 의 Lock 범위는 `events` 테이블에 한정된다"를 명시한다.**
> **나중에 "스키마를 Lock 했다"는 문장이 6테이블까지 덮는 것으로 읽히면 안 된다.**

### `KPI DEFINITION v1` — 정본 충돌을 두 층으로 분해

| GATE 1 에서 Lock | GATE 2 에서 Lock |
|---|---|
| **계산 계약** — 이름 ↔ 계산식·모집단·기간·분모 1:1 | **판정 역할 배정** — 어느 지표가 Primary 인가 |
| 공통 규약 R-1~R-14 | `C_rule` · 예산 상한 `B` |
| 이름 충돌 분리 | Primary 임계 기준 |
| 계산 불가 사유 코드 | |

**PRD §22 는 GATE 1, `data_spec` §14 는 GATE 2 라고 적었다.** 두 정본이 어긋난다.
**`Plan/` 수정은 권한 밖이므로 고치지 않고, 충돌하지 않는 해석을 쓴다** — **결정 D-4**.

> **이 분해는 두 정본을 모두 만족한다.** GATE 1 은 *"같은 이름의 다른 계산"* 을 막고, GATE 2 는 *"결과를 본 뒤 유리한 지표를 고르는 것"* 을 막는다. **막으려는 대상이 서로 다르므로 두 Lock 은 충돌하지 않는다.**

### `CHURN DEFINITION v1` — 방식만 Lock

| Lock 한다 | Lock 하지 않는다 |
|---|---|
| **판정 방식** — 고정 윈도우 · `rule_operator: OR` | `at_risk_days` = 28 (**가설값**) |
| **운영 상태(후향)와 모델 라벨(전향)의 분리** | `no_purchase_days` = 42 (**가설값**) |
| **`label_window_days = 42`** | `no_login_days` = 60 (**가설값**) |

> ⚠ **`data_spec` §15.3 은 GATE 1 확정 항목에 "Churn 임계값"을 넣었다.**
> **모순이 아니다** — 정본은 **GATE 1 전체 통과**를 전제하고, **C1 은 GATE 1 을 통과시키지 않는다.** 임계값은 범위 C(시뮬레이터) 완료 시점에 나머지 항목과 함께 확정된다.

### ⚠ Treatment **비용** ≠ Treatment **반응**

| | 속하는 Lock | C1 |
|---|---|---|
| **비용** (T0~T4 단위 비용) | `ECONOMIC RULE v1` | **Lock 한다** |
| **반응** (`τ_i`, `treat_boost_i(t)`, 4분면) | `TREATMENT RESPONSE v1` | **Lock 하지 않는다** |

**둘을 섞으면 시뮬레이터 파라미터를 측정 계층이 봉인하는 셈이 되어 창구 중립성이 깨진다.**

## 4.2 선행 조건 G-1 ~ G-16 — **하나라도 미충족이면 Lock 하지 않는다**

**2026-09-11 기준 상태.** W5 진행에 따라 갱신된다.

| # | 조건 | W2 시점 | 충족시키는 스토리 |
|---|---|---|---|
| G-1 | `category` 5종 Enum + `validate_event()` 검사 | ❌ | **M-02** |
| G-2 | `page_type` 8종 동일 | ❌ | **M-02** |
| G-3 | `validate_event()` 가 `check_identifier()` 호출 | ❌ **호출부 0건** | **M-02** |
| G-4 | 카테고리 어휘 정본 확정 | ❌ **3자 불일치** | **M-02** |
| G-5 | **타임존 정책 확정·강제** | ❌ | **M-01** |
| G-6 | 동일 root 재기록 시 파티션 보존 | ❌ **데이터 소실형** | **M-01** |
| G-7 | `strict=False` 가 예외를 던지지 않음 | ❌ | **M-01** |
| G-8 | **파생 상태 기록 경로 결정** | ★ **판정됨 (리드 2026-09-11)** — ④ 게시 시점 계산 | **M-08**(계약 문장) · **M-04**(정의) · **M-06**(게시) |
| G-9 | `shipping_subsidy` 처리 방침 | ❌ | **D-3 (사용자)** |
| G-10 | 환불/취소 이벤트 포함 여부 | ❌ | **D-2 (사용자)** |
| G-11 | KPI 계산 계약 확정 | ⚠️ 확정안 | **M-04** |
| G-12 | 경제 규칙 확정 | ⚠️ 확정안 | **M-03** |
| G-13 | `docs/event_schema.md` ↔ 코드 일치 | ✅ **W1 실행 확인 (diff 0)** | 유지 |
| G-14 | `discover -s tests` 전건 통과 | ✅ **W1·W3 실행 확인 (46건 OK)** | 유지 |
| G-15 | Lock 시점 커밋 SHA·config 해시 기록 절차 | ❌ | **이 스토리** |
| **G-16** | **`discount` 유도 규칙을 `ECONOMIC RULE v1` 에 넣는다** | ❌ | **M-03** |

**W2 시점 충족 2 / 미충족 12 / 확정안 대기 2 → 오늘 Lock 할 수 없다.**
`[Source: .agent-team/04-architecture/gate1-freeze-procedure.md#3]`

### Lock **이전**에 결정되지 않아도 되는 것 — **조건을 부풀리지 않는다**

| 항목 | 왜 조건이 아닌가 |
|---|---|
| Parquet 경로 검증 (`B-1`) | **저장 형식**의 문제이지 **스키마 계약**의 문제가 아니다. 단 `#44` 완료 조건이므로 이슈 종결과는 별개 |
| `write_batch()` 미구현 | 인터페이스 편의. 계약이 아니다 |
| manifest 재현 메타 | Lock 절차 자체가 요구하므로 **G-15 에 흡수** |
| 6개 추가 테이블 | §4.1 에서 **Lock 대상에서 제외**로 판정 |
| `data_spec` §9 금액 정합성(`DQ-09`) | **저장 구조의 문제이지 스키마 계약의 문제가 아니다.** 단 `not_run` + `PRECONDITION_MISSING` 으로 남긴다 |

## 4.3 `config/gate1_lock.yaml` — 구조

```yaml
# GATE 1 Lock 기록. 사람이 손으로 쓰지 않는다 — freeze.py 가 쓴다.
# 이 파일을 손으로 고치면 tests/test_freeze.py 가 실패한다.
lock_record_version: "gate1-lock/v1"
gate: GATE_1

declaration: PARTIAL_FREEZE          # ★ FULL_FREEZE 가 아니다
experiment_environment_v1_declared: false
declaration_note: >
  C1 은 GATE 1 을 통과시키지 않는다. 측정 계층이 소유한 항목만 부분 봉인하고
  나머지는 봉인 대기로 남긴다. EXPERIMENT_ENVIRONMENT_v1 을 선언하지 않는다.

locked_at: "2026-__-__T__:__:__.___+09:00"   # ★ KST
locked_by: "<사람 이름>"
repo_commit: "<git rev-parse HEAD>"

simulator_commit: null                       # ★ null. "" 나 "unknown" 으로 채우지 않는다
simulator_commit_null_reason: PRECONDITION_MISSING
simulator_commit_note: >
  C1 에 src/simulator/ 가 없다. 시뮬레이터 도입 시 이 값을 채우고
  lock_record_version 을 올린다.

items:                                       # PRD §22 의 9종 전부
  - item: EVENT_SCHEMA_v1
    status: PARTIAL                          # LOCKED | PARTIAL | PENDING | BLOCKED | OUT_OF_SCOPE
    owner_part: measurement
    scope_note: >
      Lock 범위는 events 테이블에 한정한다. customers·orders·order_items·products·
      marketing_actions·assignment 6개 테이블은 정의되지 않았으며 이 Lock 이 덮지 않는다.
      저장 형식(Parquet) 검증은 BLOCKED 로 별도 기록한다.
      order_amount 의 정의식이 참조하는 discount 는 22컬럼에 없다. 금액 정합성 검사는
      order_items 테이블 없이는 성립하지 않으며 이 Lock 이 그 검사의 통과를 뜻하지 않는다.
      파생 상태(inactive·at_risk·churn)는 events 에 기록되지 않는다. 측정 계층이 게시
      시점에 계산하며 Feature 로 쓰지 않는다 (리드 판정 2026-09-11).
    canonical_files:
      - path: src/measurement/schema.py
        sha256: "<64 hex>"
      - path: docs/event_schema.md
        sha256: "<64 hex>"
    preconditions: [G-1, G-2, G-3, G-4, G-5, G-8]
    # G-8 은 리드 판정(2026-09-11)으로 해소됐다 — 파생 상태는 events 에 기록하지 않고
    # 게시 시점에 계산한다. scope_note 에 그 사실을 적는다.

  - item: KPI_DEFINITION_v1
    status: PARTIAL
    owner_part: measurement
    scope_note: >
      계산 계약(지표 이름 ↔ 계산식·모집단·기간·분모)만 Lock 한다.
      판정 역할 배정·C_rule·예산 상한 B 는 GATE 2 대상이다.
      customers 테이블 부재로 P_all·P_eligible·가입월 코호트가 events 만으로 성립하지 않는다.
    canonical_files:
      - path: src/measurement/kpi.py
        sha256: "<64 hex>"

  - item: ECONOMIC_RULE_v1
    status: PARTIAL
    owner_part: measurement
    scope_note: >
      원가율·Treatment 단위 비용·비용 회계 3원칙·N_targeted 정의·기여이익식·
      원가 근거 규칙 EC-1·EC-2·AI 투자비용·가정 A-REFUND·ROI 해석 규칙 EC-7·
      discount 유도 규칙을 Lock 한다.
      C_rule·예산 상한 B·쿠폰 사용률 30% 가정은 Lock 하지 않는다.
    canonical_files:
      - path: config/economic_config.yaml
        sha256: "<64 hex>"
      - path: src/measurement/economics.py
        sha256: "<64 hex>"

  - item: CHURN_DEFINITION_v1
    status: PARTIAL
    owner_part: measurement
    scope_note: >
      판정 방식(고정 윈도우 · rule_operator OR)과 운영 상태/모델 라벨의 분리,
      label_window_days = 42 를 Lock 한다.
      임계값 at_risk_days=28 · no_purchase_days=42 · no_login_days=60 은 가설값이며
      Lock 하지 않는다 — 확정 절차(data_spec §5.1 ①~④)가 전부 시뮬레이터를 요구한다.

  - item: SERVICE_v1            # 이하 5종은 PENDING/OUT_OF_SCOPE 로 사유와 함께
  - item: CUSTOMER_PERSONA_v1
  - item: HIDDEN_TRAIT_RULE_v1
  - item: BEHAVIOR_RULE_v1
  - item: TREATMENT_RESPONSE_v1

blocked:
  - id: PARQUET_REPRODUCIBILITY
    reason: "pyarrow 미설치로 events.parquet SHA-256 재현성(NFR-001)을 검증하지 못했다."
    resolves_when: "의존성 도입 후 tests-with-deps 잡에서 실행된다."
  - id: DASHBOARD_ISOLATION
    reason: "격리 검사가 dashboard/ 를 보지 않는다(test_isolation.py 는 src/**/*.py 만 순회)."
    resolves_when: "tests/test_dashboard_isolation.py 도입 시. W6 Matthias + 사용자 승인."

release_procedure: >
  버전 상향 → 데이터 재생성 → Baseline 부터 전 전략 재실행.
  해제는 이 파일을 지우는 것이 아니라 새 lock_record_version 으로 다시 기록하는 것이다.
```

`[Source: .agent-team/04-architecture/gate1-freeze-procedure.md#2]`

### 설계 판단 5

| 판단 | 근거 |
|---|---|
| **9종 전부를 항목으로 둔다** (Lock 안 하는 것도) | 무엇이 열려 있는지가 봉인만큼 중요하다. 빼면 **"9종 중 4종 봉인"이 "봉인 완료"로 읽힌다** |
| **`scope_note` 가 필수다** | 부분 Lock 은 문장이 짧아지면 한정이 사라진다 |
| **`declaration: PARTIAL_FREEZE`** | `FULL_FREEZE` 라는 값을 쓸 수 있게 두되 **C1 에서는 쓰지 않는다.** 값이 스스로 범위를 말한다 |
| **`simulator_commit: null` + 사유** | `ISO-006` 이 요구하는 필드를 **없애지 않고** null 로 둔다. 없애면 잊고, `0`/`""` 로 채우면 **대조가 조용히 성공한다** |
| **`blocked:` 블록이 별도로 있다** | 검사하지 못한 것을 Lock 기록에 남긴다 |

## 4.4 ★ 해시 대상 — 무엇을 봉인하나

| 항목 | 정본 파일 | 왜 이 파일인가 |
|---|---|---|
| `EVENT_SCHEMA_v1` | `src/measurement/schema.py` · `docs/event_schema.md` | 문서는 스키마에서 **생성**되므로 둘이 함께 바뀌어야 정상이다. **둘 다 해시하면 한쪽만 바뀐 상태가 잡힌다** |
| `KPI_DEFINITION_v1` | `src/measurement/kpi.py` | 계산 계약이 코드에 있다 |
| `ECONOMIC_RULE_v1` | `config/economic_config.yaml` · `src/measurement/economics.py` | `data_spec` §15.2 가 *"config 4종의 SHA-256"* 을 요구한다. **값(config)과 규칙(코드)을 함께 봉인** |
| `CHURN_DEFINITION_v1` | (별도 파일 없음 — `kpi.py` 안) | 임계값이 `simulator_config.yaml` 로 가는데 그 파일이 C1 에 없다. **파일이 없으므로 해시하지 않고 `scope_note` 로만** |

**바이트 그대로 해시한다. 정규화하지 않는다** — 줄바꿈이 바뀐 것도 바뀐 것이다. **`FREEZE-003` 의 대가가 큰 만큼 판정은 엄격해야 한다.**

> ⚠ **해시 대상에 테스트 파일을 넣지 않는다.**
> `tests/test_schema.py` 가 바뀌면 계약이 아니라 **검사가** 바뀐 것이고, 그것은 (약화가 아닌 한) 정상적인 활동이다.
> **대신 검사 약화는 다른 장치로 막는다** — `test_schema.py` 의 `assertEqual`(16종·22컬럼)이 그것이다.

## 4.5 ★★ 탐지 3층 — `#49` 의 두 번째 질문

```text
1층  tests/test_freeze.py        ← 커밋 전·CI 에서. 가장 빠르다
2층  publish.py 의 게시 시점 대조  ← 게시물에 결과를 담는다
3층  대시보드 V6                  ← 사람이 화면에서 본다
```

**세 층이 같은 함수를 쓴다** — `freeze.verify(lock_record) -> FreezeVerification`. **판정이 갈리지 않는다.**

### 1층 — 테스트가 **실패한다**

`data_spec` §9 의 규율(*"경고로 넘어가지 않는다"*)을 봉인에도 적용한다.

| 테스트 | 검사 | **Lock 기록이 없을 때** |
|---|---|---|
| `test_locked_files_unchanged` | 기록된 해시 == 현재 해시 | ★ **skip 하지 않는다.** `overall == "not_started"` 임을 **단언**한다 |
| `test_lock_record_is_wellformed` | 스키마·KST 시각·9종 전부 존재 | skip (파일 없음) |
| `test_partial_lock_has_scope_note` | `PARTIAL` 항목에 `scope_note` 가 비어 있지 않다 | skip |
| `test_no_full_freeze_in_c1` | `declaration != "FULL_FREEZE"` ∧ `experiment_environment_v1_declared == false` | skip |
| `test_simulator_commit_is_null_with_reason` | `null` 이면 사유가 있다. `""`·`"unknown"`·`"0"` 이면 **실패** | skip |

> ### ★ Lock 기록이 없을 때 조용히 통과하지 않는다
> **가장 흔한 함정:** `if not lock_file.exists(): return` — **봉인하지 않은 상태가 초록으로 보인다.**
> **대신 `freeze_status.overall == "not_started"` 를 단언한다.** 미봉인은 미봉인으로 보이고, 테스트는 정직하게 통과한다.
> **그리고 그 상태가 대시보드 V6 에 `not_started` 로 표시된다.**
> `[Source: .agent-team/04-architecture/gate1-freeze-procedure.md#4.2]`

### 2층 — 게시 시점 대조

| 결과 | `verification` | 게시 | 화면 |
|---|---|---|---|
| 일치 | `match` | 정상 | 정상 |
| **불일치** | `mismatch` | **게시하되 `notices` 에 `level: "failure"`** | **명시적 실패로 표시** |
| 파일 없음 | `missing` | 동일 | 동일 |
| **대조 안 함** | `not_run` | 정상 | **`match` 와 다른 시각 상태** |

## 4.6 ★ 불일치일 때 게시를 막지 않는다 — 결정 D-27

> **막으면 화면이 비고, 사람은 왜 비었는지 모른다.**
> **봉인이 깨진 사실이야말로 화면에 나와야 하는 정보다.**
> `data_spec` §9 의 *"경고로 넘어가지 않는다"* 는 **파이프라인 진행**에 대한 규칙이고, 여기서 막아야 하는 것은 **그 데이터로 실험을 계속하는 것**이지 사실을 보여주는 것이 아니다.
> **실험 실행(이후 사이클 `orchestration`)은 `mismatch` 에서 중단한다. C1 에는 그 실행이 없다.**
> `[Source: .agent-team/04-architecture/gate1-freeze-procedure.md#4.3]`

**예외 하나:** `freeze.verify` 를 **검증 명령**으로 직접 부르면 `FreezeViolation` 을 던지고 **종료 코드 3**. 게시 경로에서만 잡는다.

## 4.7 ★ 이 3층이 막지 **못하는** 것 — 정직하게 적는다

> **가장 위험한 누수 — "결과를 본 뒤 시뮬레이터를 고치는 것"(PRD §80 Risk 1) — 은 해시 대조로 막을 수 없다.**
> **해시는 "바뀌었다"를 알려줄 뿐 "왜 바꿨는지"를 모른다. 성능이 나쁘다는 이유로 고치고 Lock 기록을 다시 쓰면 대조는 통과한다.**
>
> 막는 것은 절차와 사람의 규율이다:
> - `FREEZE-002` — 결과를 이유로 고치지 않는다
> - `FREEZE-003` — 고쳤으면 Baseline 부터 전부 재실행한다
> - **`locked_by` 와 `locked_at` 이 기록에 남는다** — 다시 Lock 한 사실 자체는 지워지지 않는다
> - **`git log config/gate1_lock.yaml` 이 재봉인 이력을 보존한다** ← **이 파일을 `.gitignore` 에 넣지 않는 이유**
>
> **★ 이 한계를 `docs/gate1_checklist.md` 에 적는다. 막지 못하는 것을 막는다고 적지 않는다.**

## 4.8 Lock 실행 절차 — 사람이 하는 일

```text
Phase 1 (병렬)  M-01 (#53) ∥ M-02 (#54)         → G-1 ~ G-7 충족
Phase 2 (병렬)  M-04 (#46) ∥ M-03 (#47)         → G-11 · G-12 · G-16 충족
Phase 3         M-08 (#45)  ★ Lock 최종 검산    → G-8 · G-9 가 여기서 드러난다
                ⚠ 표현력 공백이 드러나면 Phase 4 로 가지 않는다. 멈추고 보고한다
Phase 4         M-09 (#49) — 아래 6단계

  ① docs/gate1_checklist.md 로 G-1~G-16 을 하나씩 확인하고 증거를 적는다
  ② 미충족이 남아 있으면 그 항목은 PARTIAL/PENDING 으로 두고, 없는 척하지 않는다
  ③ python3 -m src.measurement.freeze record --by "<이름>"   ← config/gate1_lock.yaml 을 쓴다
  ④ python3 -m unittest tests.test_freeze -v                 ← 대조가 통과하는지 확인
  ⑤ 게시 → 대시보드 V6 에서 화면으로 확인
  ⑥ config/gate1_lock.yaml 을 커밋한다  ★ 커밋해야 다음 사람이 대조할 수 있다
```

> ⚠ **③⑥ 의 명령과 커밋은 사용자 지시 후에만 실행한다** (L1).
> **③ 의 `freeze record` 명령은 아직 존재하지 않는다. 이 스토리가 만든다.**

## 4.9 C1 이 도달하는 상태 — 미리 적어 둔다

| 항목 | C1 종료 시 |
|---|---|
| `declaration` | **`PARTIAL_FREEZE`** |
| `experiment_environment_v1_declared` | **`false`** |
| `overall` (V6) | **`partial`** (D-7 승인 시) 또는 **`not_started`** (미승인 시) |
| Lock 9종 | **LOCKED 0 · PARTIAL 최대 4 · PENDING/OUT_OF_SCOPE 5** |
| `blocked[]` | **최소 2건** (Parquet 재현성 · 대시보드 격리 검사) |
| `simulator_commit` | **`null` + 사유** |

**"GATE 1 통과"라고 적지 않는다. 어디에도.**

## 4.10 함정

| # | 함정 | 왜 빠지나 | 대신 |
|---|---|---|---|
| **T-1** | `if not lock_file.exists(): return` | 파일이 없으면 검사할 게 없으니까 | ★ §4.5 — **미봉인이 초록으로 보인다.** `not_started` 를 단언한다 |
| **T-2** | `simulator_commit: ""` 또는 `"unknown"` | `null` 이 어색하다 | **대조가 조용히 성공한다.** `null` + 사유 |
| **T-3** | Lock 안 하는 5종을 `items` 에서 뺀다 | 목록이 짧아진다 | **"9종 중 4종"이 "봉인 완료"로 읽힌다** |
| **T-4** | `scope_note` 를 생략하거나 짧게 | 반복이라 | **문장이 짧아지면 한정이 사라진다.** 6개월 뒤 6테이블까지 덮는 것으로 읽힌다 |
| **T-5** | 해시를 정규화(공백·줄바꿈)해 계산 | 오탐을 줄이려고 | **바이트 그대로.** 줄바꿈이 바뀐 것도 바뀐 것이다 |
| **T-6** | 테스트 파일을 해시 대상에 넣는다 | 계약의 일부 같다 | §4.4 — **검사가 바뀌는 것은 정상 활동이다** |
| **T-7** | `mismatch` 에서 게시를 막는다 | 안전해 보인다 | §4.6 — **봉인이 깨진 사실을 화면에서 지운다** |
| **T-8** | `config/gate1_lock.yaml` 을 `.gitignore` 에 | 생성물이니까 | ★ §4.7 — **커밋해야 `git log` 가 재봉인 이력을 보존한다** |
| **T-9** | "GATE 1 통과"라고 적는다 | 작업이 끝났으니까 | ★ §1 — **부분 봉인이다.** 어디에도 적지 않는다 |
| **T-10** | 미충족 조건을 "사실상 충족"으로 적는다 | Lock 을 진행하고 싶다 | **미실행을 통과로 표시하지 않는다.** 하나라도 미충족이면 Lock 하지 않는다 |
| **T-11** | 3층이 각자 판정 로직을 갖는다 | 각 층이 독립적이라 | AC-4 — **같은 함수를 쓴다.** 판정이 갈리면 어느 쪽이 맞는지 아무도 모른다 |
| **T-12** | 해시 대조를 실행 안 하고 `match` | 파일이 안 바뀐 게 명백해서 | **`not_run` 이다.** 통과가 아니다 |

---

# 5. 작업 분해 (Tasks)

## T1 · `freeze.py`

- [ ] `freeze.verify(lock_record) -> FreezeVerification` — **3층이 공유하는 단일 판정 함수**
- [ ] `freeze.record(by: str) -> None` — `config/gate1_lock.yaml` 작성
- [ ] 해시 계산 — **바이트 그대로**
- [ ] `locked_at` **KST**
- [ ] `repo_commit` — `git rev-parse HEAD`
- [ ] CLI — `python3 -m src.measurement.freeze record --by "<이름>"` · `verify`
- [ ] `FreezeViolation` (M-03 의 `errors.py`) · 종료 코드 3

## T2 · `config/gate1_lock.yaml` 골격

- [ ] §4.3 구조 — 9종 전부 · `scope_note` · `blocked[]` · `release_procedure`
- [ ] **`freeze record` 가 쓴다.** 손으로 쓰지 않는다
- [ ] `.gitignore` 에 넣지 **않는다** (§4.7)

## T3 · `docs/gate1_checklist.md`

- [ ] G-1 ~ G-16 표 + 각 항목의 **현재 상태와 증거**
- [ ] **하나라도 미충족이면 Lock 하지 않는다**는 규칙
- [ ] Lock 전 조건이 **아닌** 것 구분 (§4.2)
- [ ] Lock 9종 분류 + 미봉인 5종 사유
- [ ] `BLOCKED` 항목 — M-05·M-07 이 넘긴 것
- [ ] **`EXPERIMENT_ENVIRONMENT_v1` 선언을 하지 않는다**
- [ ] `FREEZE-003` 해제 절차
- [ ] ★ **§4.7 의 "막지 못하는 것"** — 해시 대조가 "왜 바꿨는지"를 모른다는 한계
- [ ] ★ **`DASHBOARD_NOT_ISOLATION_CHECKED`** — 격리 검사가 `dashboard/` 를 보지 않는다 (D-22 미도입 시)
- [ ] ★ **`DB-013` 부분 충족** — 빈 상태 안내가 실행 가능한 명령을 주지 못한다 (d-01 인계)

## T4 · `tests/test_freeze.py`

- [ ] §4.5 의 5개 테스트
- [ ] ★ `test_locked_files_unchanged` 가 **파일 부재 시 skip 하지 않고 `not_started` 를 단언**
- [ ] 해시 불일치를 인위적으로 만들어 **실제로 실패하는지** 확인

## T5 · 게시 연동 (M-06 과)

- [ ] `publish.py` 가 `freeze.verify()` 를 호출해 `freeze_status.json` 생성
- [ ] `mismatch` 여도 **게시한다** + `notices` `level: "failure"`
- [ ] `overall` 이 **`partial` 을 넘지 않는다**

## T6 · Lock 실행 (D-7 승인 시에만)

- [ ] §4.8 6단계
- [ ] ③⑥ 은 **사용자 지시 후에만**
- [ ] 미충족 조건이 남아 있으면 **Lock 하지 않고 체크리스트만 남긴다**

## T7 · 검증 (AC-7)

- [ ] `python3 -m unittest discover -s tests` — 출력 전문
- [ ] `python3 -m unittest tests.test_freeze -v`
- [ ] `python3 -m unittest tests.test_isolation -v`
- [ ] `python3 scripts/gen_event_schema_doc.py | diff - docs/event_schema.md` (G-13)
- [ ] `python3 .agent-team/04-architecture/tools/check_ownership.py`

---

# 6. 파일 목록 (`file_list`)

## 6.1 이 스토리가 만드는 파일

| 파일 | 동작 |
|---|---|
| `src/measurement/freeze.py` | **신설** |
| `config/gate1_lock.yaml` | **신설 — 커밋한다** |
| `docs/gate1_checklist.md` | **신설** — 언더스코어 (`#49` 지정) |
| `tests/test_freeze.py` | **신설** |
| `.agent-team/04-architecture/tools/ownership.json` | **수정하지 않는다** — 이미 등록돼 있다(Thomas N-1). 돌려 **확인만** |

> **`config/gate1_lock.yaml` 은 SRS §31 이 열거한 `config/` 4파일에 없는 5번째다.**
> **구조 확장이며 리드 인지가 필요하다** (결정 D-26). 근거와 대안은 `ADR-0005`.

## 6.2 절대 만지지 않는 파일

```
tests/test_isolation.py · .github/workflows/isolation.yml          ← 봉인
src/simulator/** src/decision/** src/diagnostics/** src/orchestration/**
Plan/** · AGENTS.md · src/AGENTS.md · README.md
dashboard/**                                                       ← Andrew
../Ecommerce_Service/**
```

---

# 7. 테스트

## 7.1 실행 가능한 명령

```bash
python3 -m unittest discover -s tests
python3 -m unittest tests.test_freeze -v
python3 -m unittest tests.test_isolation -v
python3 scripts/gen_event_schema_doc.py | diff - docs/event_schema.md
python3 .agent-team/04-architecture/tools/check_ownership.py

# ★ 이 스토리가 신설하는 명령 — 그 전에는 존재하지 않는다
python3 -m src.measurement.freeze record --by "<이름>"
python3 -m src.measurement.freeze verify
```

> **`freeze record` 는 2026-09-11 현재 실행할 수 없다.** 이 스토리가 만든다.
> **실행은 사용자 지시 후** (L1 — 파일을 쓰고 커밋해야 한다).

## 7.2 픽스처

`.agent-team/04-architecture/examples/*/freeze_status.json`

**구조 실측:** `gate` · `overall` · `lock_record{path, sha256, locked_at, locked_by, repo_commit, simulator_commit}` · `items[]{item, status, owner_part, scope_note, reason_code, reason_detail}` · `unlocked_items[]{id, title, met, evidence}`

**`empty-sink` 기대:** `overall: "not_started"` · `lock_items_pending: 9`
**`commerce-connected` 기대:** `overall: "violated"` (해시 불일치 시나리오)

## 7.3 깨뜨리면 안 되는 기존 테스트

| 테스트 | 이유 |
|---|---|
| `test_schema.py:45-47`·`61-72` | **16종·22컬럼 `assertEqual`** — 검사 약화를 막는 유일한 장치 (§4.4) |
| `test_isolation.py` 6건 | `freeze.py` 도 자동 검사 대상 |
| `test_sink.py:198-203` | USP-1 회귀 |

---

# 8. 연속성

## 8.1 선행 스토리에서 이어받는 것

| 스토리 | 이어받는 것 |
|---|---|
| **M-01** | G-5·G-6·G-7 충족 증거 · 타임존 정책 |
| **M-02** | G-1·G-2·G-3·G-4 충족 증거 · Lock 대상 `schema.py` |
| **M-03** | G-12·G-16 · Lock 대상 `economic_config.yaml`·`economics.py` · `errors.py`(`FreezeViolation`) |
| **M-04** | G-11 · Lock 대상 `kpi.py` · D-4 해석 결과 · **`customers` 부재** → `KPI_DEFINITION_v1` `scope_note` |
| **M-05** | `BLOCKED` 항목 `PARQUET_REPRODUCIBILITY` 최종 상태 |
| **M-06** | `provenance.config_hashes` 수집 방법 · `freeze_status` 게시 경로 |
| **M-07** | `BLOCKED` 항목 목록 · `DQ-09` 불가 → `EVENT_SCHEMA_v1` `scope_note` |
| **M-08** | ★ **Lock 최종 검산 결과 — 진행 가능 여부** · `scope_note` 한정 문구 |
| **d-01** | `DASHBOARD_NOT_ISOLATION_CHECKED` · `DB-013` 부분 충족 |

## 8.2 확립된 패턴

| 패턴 | 어디에 |
|---|---|
| **`.gitignore` 에 넣지 않는 것** | `config/` — 봉인 대상 config 는 커밋한다 |
| KST 시각 | `schema.py TIMEZONE` · 게시 계약 `generated_at` |
| **한계를 먼저 적는다** | `design-patterns.md P-7` — *"한계를 적지 않은 검사는 통과가 보증으로 오해된다"* |

---

# 9. 완료 정의 (DoD) · 미결정 · 차단

## 9.1 DoD

- [ ] AC-1 ~ AC-7 전부 체크
- [ ] **"GATE 1 통과"라는 문장이 어디에도 없다** — 문서·PR·코드 주석·게시물
- [ ] `experiment_environment_v1_declared: false`
- [ ] **Lock 9종 전부가 기록에 있다** — 하지 않는 5종도
- [ ] **`PARTIAL` 항목에 `scope_note` 가 있고, 그것이 범위를 실제로 한정한다**
- [ ] ★ **§4.7 "막지 못하는 것"이 체크리스트에 적혔다**
- [ ] **해시 불일치를 인위적으로 만들어 테스트가 실제로 실패하는 것을 확인했다**
- [ ] **Lock 기록이 없을 때 테스트가 skip 하지 않고 `not_started` 를 단언한다**
- [ ] D-7 미승인이면 **Lock 을 실행하지 않고** 체크리스트·절차만 남겼다
- [ ] `#49` 를 **닫지 않았다**

## 9.2 이 스토리에서 하지 않는 것

| 항목 | 왜 |
|---|---|
| **`EXPERIMENT_ENVIRONMENT_v1` 선언** | ★ **범위 B·C 완료 후** (`#49` 본문) |
| GATE 2·3·4 절차 | C1 범위 밖 |
| 6개 추가 테이블 스키마 | C1 범위 밖. `#44` 후속 |
| 시뮬레이터 파라미터 Lock | **창구 중립성** — Treatment **반응**은 simulator 소유 |
| 이탈 임계값 확정 | `data_spec` §5.1 절차가 시뮬레이터를 요구한다 |
| 재봉인 시 이력 보존 구조 | `git log` 로 충분하다고 본다. 필요해지면 `lock_history[]` — `lock_record_version` 이 여지를 남겼다 |

## 9.3 미결정 — 구현자가 정하고 PR 에 적는다

| # | 항목 | 선택지 |
|---|---|---|
| **M09-a** | `docs/gate1_checklist.md` 의 구체 서식 | 아키텍처가 미정으로 남겼다 — *"Phillip T5.7 소관"* |
| **M09-b** | `freeze.py` 가 PyYAML 을 직접 쓰나 | ⑴ `config_loader.py` 를 통한다 **(권장 — 의존성 봉쇄 A7-6)** ⑵ 직접 — **⑵는 `import yaml` 이 두 파일이 되어 `test_neutrality` 가 실패한다** |
| **M09-c** | `verify` 를 CLI 하위 명령으로 둘지 | `record` / `verify` 두 하위 명령 (권장) |

## 9.4 차단

| # | 항목 | 성격 | W2 추천 |
|---|---|---|---|
| **M-08 검산 결과** | **선행 스토리.** 공백이 드러나면 **진행하지 않는다** | — |
| **D-7** | **C1 에서 부분 Lock 을 실행하는가** | ⑴ **G-1~G-16 충족 후 실행** ⑵ 절차 문서만 만들고 Lock 은 시뮬레이터 사이클에 일괄 | **⑴.** 측정 계층이 먼저 확정되어야 시뮬레이터가 측정되는 행동만 만든다. 미루면 그 순서가 무의미해진다 |
| **D-8** | `EVENT SCHEMA v1` Lock 범위를 `events` 로 한정 | ⑴ **한정** ⑵ 6테이블 정의 후 함께 | **⑴.** ⑵는 6테이블 구현을 C1 범위에 끌어들인다 |
| **D-4** | KPI Lock 시점 정본 충돌 | ⑴ **계산 계약=GATE 1 / 역할 배정=GATE 2** ⑵ 전부 GATE 1 ⑶ 전부 GATE 2 | **⑴** |
| **D-2** | 환불 이벤트 (G-10) | ⑴ **가정 `A-REFUND` 로 Lock** ⑵ `Plan/` 개정 후 추가 | **⑴** |
| **D-3** | `shipping_subsidy` (G-9) | ⑴ **규칙 유도값** ⑵ 필드 추가 | **⑴** |
| **D-26** | `gate1_lock.yaml` 위치 | ⑴ **`config/`** (5번째 파일) ⑵ `docs/` ⑶ 체크리스트에 임베드 | **⑴.** ⑶은 사람 문서와 기계 기록을 섞어 둘 다 나빠진다 |
| **D-27** | `mismatch` 에서 게시를 막는가 | ⑴ **게시하고 실패로 표시** ⑵ 막는다 | **⑴** |
| ~~**G-8**~~ | ~~파생 상태 기록 경로~~ | ★ **해소** — 리드 판정 ④ 게시 시점 계산 | — |

`[Source: .agent-team/03-service-planning/gate1-lock-scope.md#7]` · `[Source: .agent-team/04-architecture/gate1-freeze-procedure.md#7]`

## 9.5 하류로 넘기는 것

| 받는 쪽 | 넘기는 것 |
|---|---|
| **d-02 (대시보드)** | `freeze_status.json` 실제 형태 · `overall: "not_started"` 가 **오늘의 정상 상태**라는 사실 · `not_run` 을 `match` 와 같은 색으로 그리지 않는다 |
| **W6 Matthias** | 체크리스트의 `BLOCKED` 항목 — **검증 대상이자 한계 목록** |
| **다음 사이클** | Lock 대기 5종 · `simulator_commit` 을 채울 시점 · `lock_record_version` 상향 규칙 |
| **리드** | **부분 Lock 실행 여부 판정 요청** (D-7) · G-8 판정 결과 반영본 |

<!-- ════════ source_hash inputs (D3 · Matthias 항목5) ════════
     계산법: project-context-kr.md §12  ·  파일 17종
     재현:  아래 목록을 sorted() 하고 각 파일에 f"{path}\n{sha256_hex}\n" 를 이어붙여
            그 바이트열의 SHA-256 앞 16자리를 취한다. 없는 파일은 "MISSING".

     .agent-team/00-plan/charter.md
     .agent-team/00-plan/task-graph.md
     .agent-team/03-service-planning/economic-rule-v1.md
     .agent-team/03-service-planning/gate1-lock-scope.md
     .agent-team/03-service-planning/kpi-definition-v1.md
     .agent-team/03-service-planning/user-stories.md
     .agent-team/04-architecture/adr/ADR-0005-gate1-lock-record.md
     .agent-team/04-architecture/build-plan.md
     .agent-team/04-architecture/code-structure.md
     .agent-team/04-architecture/design-patterns.md
     .agent-team/04-architecture/exceptions.md
     .agent-team/04-architecture/gate1-freeze-procedure.md
     .agent-team/04-architecture/schemas/freeze_status.schema.json
     AGENTS.md
     docs/GIT_WORKFLOW.md
     src/AGENTS.md
     src/measurement/schema.py

     → source_hash = a20dd972916f0565
     ════════════════════════════════════════════════════ -->
