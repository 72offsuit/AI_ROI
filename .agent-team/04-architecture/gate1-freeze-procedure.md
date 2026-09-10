# GATE 1 Freeze 절차 설계 (T2.11 · M-7 / `#49`)

**작성** James (Role 4 · Architect) · 2026-09-11 · 사이클 C1
**입력** Joshua `gate1-lock-scope.md` — **C1 은 GATE 1 을 통과시키지 않는다. 부분 봉인만 한다**
**정본 근거** PRD §22 · SRS `FREEZE-001`~`003` · `ISO-006` · `docs/data_spec.html` §15.2·§15.3 · 이슈 `#49`

> `#49` 가 묻는 것은 둘이다 — **무엇을 어떻게 Lock 하는가**, 그리고 **깨졌을 때 어떻게 아는가**.
> Joshua 가 첫째를 판정했다(Lock 불가 5종 · 부분/조건부 4종 · 완전 Lock 0종). **이 문서는 둘째를 설계한다.**

---

# 1. 산출물 둘 — 사람용과 기계용을 나눈다

| | 파일 | 용도 | 소유 |
|---|---|---|---|
| 사람 | **`docs/gate1_checklist.md`** | 절차·선행 조건·범위 한정 문구·해제 절차. `#49` 가 지정한 이름 | Phillip (W5-B) |
| 기계 | **`config/gate1_lock.yaml`** | Lock 기록. 해시·커밋·시각·주체 | Phillip (W5-B) |
| 검증 | `src/measurement/freeze.py` | 기록 작성 · 해시 대조 | Phillip (W5-A/B) |
| 화면 | `results/measurement/freeze_status.json` → **V6** | 대조 결과 | 게시 (`publish.py`) |
| 테스트 | `tests/test_freeze.py` | **깨지면 실패한다** | Phillip |

**왜 나누는가:** 체크리스트만 있으면 사람이 읽고 넘어간다. 기계 기록만 있으면 왜 그렇게 정했는지가 사라진다.
**해시 대조는 사람이 할 수 없고, 판단은 기계가 할 수 없다.**

`config/gate1_lock.yaml` 은 SRS §31 이 열거한 `config/` 4파일에 없는 **5번째**다 — 근거와 대안은 `adr/ADR-0005-gate1-lock-record.md`.

---

# 2. `config/gate1_lock.yaml` — 구조

```yaml
# GATE 1 Lock 기록. 사람이 손으로 쓰지 않는다 — freeze.py 가 쓴다.
# 이 파일을 손으로 고치면 tests/test_freeze.py 가 실패한다.
lock_record_version: "gate1-lock/v1"
gate: GATE_1

# ── 이 Lock 이 무엇인지 ──────────────────────────────────
declaration: PARTIAL_FREEZE          # ★ FULL_FREEZE 가 아니다
experiment_environment_v1_declared: false
declaration_note: >
  C1 은 GATE 1 을 통과시키지 않는다. 측정 계층이 소유한 항목만 부분 봉인하고
  나머지는 봉인 대기로 남긴다. EXPERIMENT_ENVIRONMENT_v1 을 선언하지 않는다.

# ── 언제·누가 ────────────────────────────────────────
locked_at: "2026-09-__T__:__:__.___+09:00"   # ★ KST. sink.manifest 의 UTC 실수를 반복하지 않는다
locked_by: "<사람 이름>"                       # #49 — 누가 Lock 했는지 추적 가능해야 한다
repo_commit: "<git rev-parse HEAD>"

# ── ISO-006 · FREEZE-003 대조용 ──────────────────────────
simulator_commit: null                       # ★ null 이다. "" 나 "unknown" 으로 채우지 않는다
simulator_commit_null_reason: PRECONDITION_MISSING
simulator_commit_note: >
  C1 에 src/simulator/ 가 없다. 시뮬레이터 도입 시 이 값을 채우고 lock_record_version 을 올린다.

# ── Lock 항목 (PRD §22 의 9종 전부가 온다) ──────────────────
items:
  - item: EVENT_SCHEMA_v1
    status: PARTIAL                          # LOCKED | PARTIAL | PENDING | BLOCKED | OUT_OF_SCOPE
    owner_part: measurement
    scope_note: >
      Lock 범위는 events 테이블에 한정한다. customers·orders·order_items·products·
      marketing_actions·assignment 6개 테이블은 정의되지 않았으며 이 Lock 이 덮지 않는다.
      저장 형식(Parquet) 검증은 BLOCKED 로 별도 기록한다.
    canonical_files:
      - path: src/measurement/schema.py
        sha256: "<64 hex>"
      - path: docs/event_schema.md
        sha256: "<64 hex>"
    preconditions: [G-1, G-2, G-3, G-4, G-5]

  - item: KPI_DEFINITION_v1
    status: PARTIAL
    owner_part: measurement
    scope_note: >
      계산 계약(지표 이름 ↔ 계산식·모집단·기간·분모)만 Lock 한다.
      판정 역할 배정(어느 지표가 Primary 인가)·C_rule·예산 상한 B 는 GATE 2 대상이다.
    canonical_files:
      - path: src/measurement/kpi.py
        sha256: "<64 hex>"

  - item: ECONOMIC_RULE_v1
    status: PARTIAL
    owner_part: measurement
    scope_note: >
      원가율·Treatment 단위 비용·비용 회계 3원칙·N_targeted 정의·기여이익식·
      원가 근거 규칙 EC-1·EC-2·AI 투자비용·가정 A-REFUND·ROI 해석 규칙 EC-7 을 Lock 한다.
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
      임계값 at_risk_days=28 · no_purchase_days=42 · no_login_days=60 은 가설값이며 Lock 하지 않는다
      — 확정 절차(data_spec §5.1 ①~④)가 전부 시뮬레이터를 요구한다.

  - item: SERVICE_v1            # 이하 5종은 PENDING/OUT_OF_SCOPE 로 사유와 함께 남는다
  - item: CUSTOMER_PERSONA_v1
  - item: HIDDEN_TRAIT_RULE_v1
  - item: BEHAVIOR_RULE_v1
  - item: TREATMENT_RESPONSE_v1

# ── 검사하지 못한 것 ────────────────────────────────────
blocked:
  - id: PARQUET_REPRODUCIBILITY
    reason: "pyarrow 미설치로 events.parquet SHA-256 재현성(NFR-001)을 검증하지 못했다."
    resolves_when: "의존성 도입 후 tests-with-deps 잡에서 실행된다."
  - id: DASHBOARD_ISOLATION
    reason: "격리 검사가 dashboard/ 를 보지 않는다(test_isolation.py 는 src/**/*.py 만 순회)."
    resolves_when: "tests/test_dashboard_isolation.py 도입 시. W6 Matthias + 사용자 승인."

# ── FREEZE-003 해제 절차 ────────────────────────────────
release_procedure: >
  버전 상향 → 데이터 재생성 → Baseline 부터 전 전략 재실행.
  해제는 이 파일을 지우는 것이 아니라 새 lock_record_version 으로 다시 기록하는 것이다.
```

## 2.1 설계 판단 다섯

| 판단 | 근거 |
|---|---|
| **9종 전부를 항목으로 둔다** (Lock 안 하는 것도) | 무엇이 아직 열려 있는지가 봉인만큼 중요하다. 빼면 "9종 중 4종을 봉인" 이 "봉인 완료"로 읽힌다 |
| **`scope_note` 가 필수다** | 부분 Lock 은 문장이 짧아지면 한정이 사라진다. `gate1-lock-scope.md` §5 |
| **`declaration: PARTIAL_FREEZE`** | `FULL_FREEZE` 라는 값을 쓸 수 있게 두되 **C1 에서는 쓰지 않는다.** 값이 스스로 범위를 말한다 |
| **`simulator_commit: null` + 사유** | `ISO-006` 이 요구하는 필드를 **없애지 않고 null 로 둔다.** 없애면 나중에 잊고, 0/""로 채우면 대조가 조용히 성공한다 |
| **`blocked:` 블록이 별도로 있다** | 검사하지 못한 것을 Lock 기록에 남긴다. AGENTS.md — 미실행을 통과로 적지 않는다 |

## 2.2 해시 대상 — 무엇을 봉인하는가

| 항목 | 정본 파일 | 왜 이 파일인가 |
|---|---|---|
| `EVENT_SCHEMA_v1` | `src/measurement/schema.py` · `docs/event_schema.md` | 문서는 스키마에서 **생성**되므로(`gen_event_schema_doc.py`) 둘이 함께 바뀌어야 정상이다. **둘 다 해시하면 한쪽만 바뀐 상태가 잡힌다** |
| `KPI_DEFINITION_v1` | `src/measurement/kpi.py` | 계산 계약이 코드에 있다 |
| `ECONOMIC_RULE_v1` | `config/economic_config.yaml` · `src/measurement/economics.py` | `data_spec` §15.2 가 *"config 4종의 SHA-256"* 을 요구한다. 값(config)과 규칙(코드)을 함께 봉인한다 |
| `CHURN_DEFINITION_v1` | (별도 파일 없음 — `kpi.py` 안) | 임계값이 `simulator_config.yaml` 로 가는데 그 파일이 C1 에 없다. **파일이 없으므로 해시하지 않고 `scope_note` 로만 남긴다** |

**바이트 그대로 해시한다.** 정규화하지 않는다 — 줄바꿈이 바뀐 것도 바뀐 것이다. `FREEZE-003` 의 대가가 큰 만큼 판정은 엄격해야 한다.

> ⚠ **해시 대상에 테스트 파일을 넣지 않는다.** `tests/test_schema.py` 가 바뀌면 계약이 아니라 **검사가** 바뀐 것이고, 그것은 (약화가 아닌 한) 정상적인 활동이다.
> 대신 **검사 약화는 다른 장치로 막는다** — `test_schema.py:45-47, 61-72` 의 `assertEqual`(16종·22컬럼)이 그것이다.

---

# 3. 선행 조건 — G-1~G-16

Joshua 의 G-1~G-15 를 그대로 쓰고 **G-16 을 추가 제안**한다.

| # | 조건 | 상태 (2026-09-11) |
|---|---|---|
| G-1 | `category` 5종 Enum + `validate_event()` 검사 | ❌ `#54` |
| G-2 | `page_type` 8종 동일 | ❌ `#54` |
| G-3 | `validate_event()` 가 `check_identifier()` 호출 | ❌ **호출부 0건** |
| G-4 | 카테고리 어휘 정본 확정 | ❌ 3자 불일치 |
| G-5 | 타임존 정책 확정·강제 | ❌ `#53` D1-3 |
| G-6 | 동일 root 재기록 시 파티션 보존 | ❌ `#53` D1-1 — **데이터 소실형** |
| G-7 | `strict=False` 가 예외를 던지지 않음 | ❌ `#53` D1-2 |
| G-8 | 파생 상태 기록 경로 결정 | ❌ 설계 공백 (W1 D-7) |
| G-9 | `shipping_subsidy` 처리 방침 | ❌ 결정 D-3 |
| G-10 | 환불/취소 이벤트 포함 여부 | ❌ 결정 D-2 |
| G-11 | KPI 계산 계약 확정 | ⚠️ 확정안 있음 |
| G-12 | 경제 규칙 확정 | ⚠️ 확정안 있음 |
| G-13 | `docs/event_schema.md` ↔ 코드 일치 | ✅ **W1 실행 확인 (diff 0)** |
| G-14 | `discover -s tests` 전건 통과 | ✅ **W1 실행 확인 (46건)** |
| G-15 | Lock 시점 커밋 SHA·config 해시 기록 절차 | ❌ 이 문서가 설계, 구현은 W5-B |
| **G-16** | **`discount` 유도 규칙을 `ECONOMIC RULE v1` 에 넣는다** ← **신규 제안** | ❌ **결정 D-16** · **차단 조건 아님** (§3.2) |

**충족 2 / 미충족 12 / 확정안 대기 2 → 오늘 Lock 할 수 없다.**

## 3.1 G-16 을 추가하는 이유

G-9(`shipping_subsidy`)와 **같은 종류의 공백**이고, 영향은 더 크다.
`discount` 가 없으면 `coupon_cost` 가 계산 불가이고, `coupon_cost` 는 `marketing_cost` 의 구성요소이며, **`marketing_cost ≤ C_rule` 은 Guardrail 이다**(`kpi-definition-v1.md` §7.2).
Lock 이후에 발견하면 `FREEZE-003` — 데이터 재생성 + 전 전략 재실행이다. **지금이 결정 비용이 가장 싼 시점이다.**

리드가 재현으로 확인한 것: `docs/event_schema.md:36` 이 `order_amount = Σ(unit_price × quantity) − discount` 라고 적는데 **`discount` 가 22컬럼에 없다.**
`shipping_subsidy` 는 *"계산할 필드가 없다"* 이지만 이것은 **정본이 자기 정의 안에서 존재하지 않는 필드를 참조하는 내부 모순**이다.

## 3.2 ★ G-16 은 Lock 차단 조건인가 — 판정

> ### 판정: **차단 조건이 아니다. 단 "유도 규칙을 Lock 시점에 확정한다"는 조건부다.**
> **차단되는 것은 필드의 부재가 아니라 결정의 부재다.**

### 왜 D-2(환불)와 같은 취급이 아닌가

Joshua 는 D-2 를 *"가정 `A-REFUND` 로 Lock 가능"* 으로 판정했다. **`discount` 는 그것과 다르다.**

| | D-2 환불 | **D-16 `discount`** |
|---|---|---|
| 시뮬레이터 생성분에 그 사건이 존재하나 | **아니오.** 시뮬레이터는 환불을 생성하지 않는다 | **예.** `coupon_use` 를 생성하고 T3 할인을 적용한다 |
| 유도 가능한가 | **아니오.** 유도할 원천이 없다 | **예.** `coupon_use` + `economic_config.treatment_cost[T3] = 7,000원` |
| 유도의 성격 | — | **추정이 아니라 재구성이다.** 시뮬레이터가 config 값을 적용하므로 **정확하다** |
| 남는 것 | 가정 하나 (`A-REFUND`) | **규칙 하나** — Lock 대상 |
| 실험 판정 영향 | 없다 (환불 없는 세계의 정확한 값) | **있다.** `coupon_cost → marketing_cost` 가 Guardrail 이다 |

**핵심 차이:** 환불은 **가정으로 덮을 수밖에 없고**, `discount` 는 **규칙으로 덮을 수 있다.**
규칙으로 덮을 수 있는 것을 가정으로 덮으면, 그것은 *"할 수 있는데 안 한 것"* 이다.

### 그래서 무엇을 Lock 하나

> **`ECONOMIC RULE v1` 에 유도 규칙을 명시적 조항으로 넣고 함께 Lock 한다.**
>
> ```
> discount(order) := Σ  treatment_cost[t]  for t in {order 에 적용된 처치 중 쿠폰 계열}
>                    단 그 주문에 coupon_use 이벤트가 있을 때만 (EC-3 발생주의 2원칙)
>                    최소주문금액 미달로 미사용이면 0 이 아니라 발생하지 않는다
> ```
>
> 산출물에는 **`derived: true` + `derivation`** 이 붙는다 — 저장된 사실이 아님이 화면에서 구분된다.

| 대상 | `coupon_cost` |
|---|---|
| 시뮬레이터 생성분 | ✅ **규칙 유도.** `derived: true` |
| 커머스 실측분 | ❌ `MISSING_FIELD` — 커머스는 할인액을 저장하지 않는다 |
| `data_spec` §9 금액 정합성 검사 | ❌ `PRECONDITION_MISSING` — `order_items` 필요 (§3.3) |

### 그리고 Lock 범위 한정 문구에 이것을 적는다

`EVENT_SCHEMA_v1` 의 `scope_note` 에 한 문장이 더 들어간다:

> *"`order_amount` 의 정의식이 참조하는 `discount` 는 22컬럼에 없다. 금액 정합성 검사(`data_spec` §9)는 `order_items` 테이블 없이는 성립하지 않으며 이 Lock 이 그 검사의 통과를 뜻하지 않는다."*

### 진짜 차단 조건 — 하나

> **유도 규칙을 정하지 않은 채 Lock 하면 차단이다.**
> 그러면 다음 사이클이 유도 규칙을 임의로 정하게 되고, **그것이 Lock 이후 변경**이다 — `FREEZE-003` 전량 재실행.
> **G-16 의 충족 조건은 "필드를 추가한다"가 아니라 "유도 규칙을 `ECONOMIC RULE v1` 에 넣는다"이다.**

### 사용자가 ⑵(SRS 개정)를 고르면

`Plan/` 에 `discount` 컬럼을 추가하면 유도가 필요 없어지고 금액 정합성 검사의 절반이 살아난다(품목 합계는 여전히 `order_items` 필요).
**그 비용이 가장 싼 시점은 지금이다.** 다만 그것은 이 팀의 권한 밖이므로 **⑴로도 Lock 이 성립한다는 것이 이 판정의 요지다.**

## 3.3 `data_spec` §9 금액 정합성은 Lock 과 무관하다

`order_amount = Σ(unit_price × quantity) − discount` 의 **검산**은 `order_items` 테이블을 요구한다(`purchase` 는 주문 단위 1행이고 품목 3필드가 `NOT_APPLICABLE` 이다).
이것은 **저장 구조의 문제이지 스키마 계약의 문제가 아니다** — `EVENT SCHEMA v1` Lock 범위가 `events` 한정인 것과 같은 이유로 Lock 을 막지 않는다.
**단 `docs/gate1_checklist.md` 에 `not_run` + `PRECONDITION_MISSING` 으로 남긴다.**

---

# 4. ★ 깨졌을 때 어떻게 아는가 — `#49` 의 두 번째 질문

Joshua 가 기획 관점의 요구 넷을 남겼다(`gate1-lock-scope.md` §5.1). **설계는 여기다.**

## 4.1 탐지 3층

```text
1층  tests/test_freeze.py        ← 커밋 전·CI 에서. 가장 빠르다
2층  publish.py 의 게시 시점 대조  ← 게시물에 결과를 담는다
3층  대시보드 V6                  ← 사람이 화면에서 본다 (charter §2.2-3 "화면으로 증명한다")
```

**세 층이 같은 함수를 쓴다** — `freeze.verify(lock_record) -> FreezeVerification`. 판정이 갈리지 않는다.

## 4.2 1층 — `tests/test_freeze.py` 가 **실패**한다

`data_spec` §9 의 규율(*"경고로 넘어가지 않는다"*)을 봉인에도 적용한다. **경고가 아니라 실패다.**

| 테스트 | 검사 | Lock 기록이 없을 때 |
|---|---|---|
| `test_locked_files_unchanged` | 기록된 해시 == 현재 해시 | **skip 하지 않는다.** `overall == "not_started"` 임을 단언한다 |
| `test_lock_record_is_wellformed` | 스키마·KST 시각·9종 전부 존재 | skip (파일 없음) |
| `test_partial_lock_has_scope_note` | `PARTIAL` 인 항목에 `scope_note` 가 비어 있지 않다 | skip |
| `test_no_full_freeze_in_c1` | `declaration != "FULL_FREEZE"` · `experiment_environment_v1_declared == false` | skip |
| `test_simulator_commit_is_null_with_reason` | `null` 이면 사유가 있다. `""`·`"unknown"`·`"0"` 이면 **실패** | skip |

> ### ★ Lock 기록이 없을 때 조용히 통과하지 않는다
> 가장 흔한 함정: `if not lock_file.exists(): return` — **봉인하지 않은 상태가 초록으로 보인다.**
> 대신 **`freeze_status.overall == "not_started"` 를 단언한다.** 미봉인은 미봉인으로 보이고, 테스트는 정직하게 통과한다.
> 그리고 그 상태가 **대시보드 V6 에 `not_started` 로 표시된다.**

## 4.3 2층 — 게시 시점 대조

`publish.py` 가 `freeze.verify()` 를 호출해 `freeze_status.json` 을 만든다.

| 결과 | `verification` | 게시 | 화면 |
|---|---|---|---|
| 일치 | `match` | 정상 | 정상 |
| **불일치** | `mismatch` | **게시하되 `notices` 에 `level: "failure"`** | **명시적 실패로 표시** |
| 파일 없음 | `missing` | 동일 | 동일 |
| **대조 안 함** | `not_run` | 정상 | **`match` 와 다른 시각 상태** |

> **불일치일 때 게시를 막지 않는 이유:** 막으면 화면이 비고, 사람은 **왜 비었는지 모른다.**
> 봉인이 깨진 사실이야말로 화면에 나와야 하는 정보다. `data_spec` §9 의 *"경고로 넘어가지 않는다"* 는 **파이프라인 진행**에 대한 규칙이고, 여기서 막아야 하는 것은 **그 데이터로 실험을 계속하는 것**이지 사실을 보여주는 것이 아니다.
> **실험 실행(이후 사이클 `orchestration`)은 `mismatch` 에서 중단한다.** C1 에는 그 실행이 없다.

## 4.4 3층 — 대시보드 V6

`freeze_status.json` 을 그린다. 표시 요구:

- **`not_run` 을 `match` 와 같은 색으로 그리지 않는다** (`api-contracts.md` R-5)
- `scope_note` 를 **접어 두지 않고** 보인다 — 부분 Lock 의 범위가 보이지 않으면 전체 Lock 으로 읽힌다
- `blocked[]` 를 표시한다
- `overall: "not_started"` 는 **경고가 아니라 사실**로 그린다. 오늘의 정상 상태다

## 4.5 이 3층이 막지 **못하는** 것 — 정직하게

> **가장 위험한 누수 — "결과를 본 뒤 시뮬레이터를 고치는 것"(PRD §80 Risk 1) — 은 해시 대조로 막을 수 없다.**
> 해시는 **바뀌었다**를 알려줄 뿐 **왜 바꿨는지**를 모른다. 성능이 나쁘다는 이유로 고치고 Lock 기록을 다시 쓰면 대조는 통과한다.
>
> 막는 것은 절차와 사람의 규율이다:
> - `FREEZE-002` — 결과를 이유로 고치지 않는다
> - `FREEZE-003` — 고쳤으면 Baseline 부터 전부 재실행한다
> - **`locked_by` 와 `locked_at` 이 기록에 남는다** — 다시 Lock 한 사실 자체는 지워지지 않는다
> - `git log config/gate1_lock.yaml` 이 재봉인 이력을 보존한다 ← **이 파일을 `.gitignore` 에 넣지 않는 이유**
>
> **이 한계를 `docs/gate1_checklist.md` 에 적는다.** 막지 못하는 것을 막는다고 적지 않는다.

---

# 5. Lock 실행 절차 — 사람이 하는 일

`gate1-lock-scope.md` §2.3 의 Phase 순서를 실행 절차로 옮긴 것이다.

```text
Phase 1 (병렬)  #53 Sink 결함 3건 ∥ #54 스키마 값 수준 강제
                  → G-1 ~ G-7 충족
Phase 2 (병렬)  #46 KPI 정의 v1 ∥ #47 경제 규칙 v1 + config
                  → G-11 · G-12 충족
Phase 3         #45 M-3 기록 계약 문서   ★ Lock 최종 검산
                  → G-8 · G-9 · G-16 이 여기서 드러난다
                  ⚠ 표현력 공백이 드러나면 Phase 4 로 가지 않는다. 멈추고 보고한다
Phase 4         #49 M-7 — 아래 6단계

  ① docs/gate1_checklist.md 로 G-1~G-16 을 하나씩 확인하고 증거를 적는다
  ② 미충족이 남아 있으면 그 항목은 PARTIAL/PENDING 으로 두고, 없는 척하지 않는다
  ③ python3 -m src.measurement.freeze record --by "<이름>"   ← config/gate1_lock.yaml 을 쓴다
  ④ python3 -m unittest tests.test_freeze -v                 ← 대조가 통과하는지 확인
  ⑤ 게시 → 대시보드 V6 에서 화면으로 확인 (charter §2.2-3)
  ⑥ config/gate1_lock.yaml 을 커밋한다  ★ 커밋해야 다음 사람이 대조할 수 있다
```

> ⚠ **③⑥ 의 명령과 커밋은 사용자 지시 후에만 실행한다** (AGENTS.md L1).
> ③ 의 `freeze record` 명령은 **아직 존재하지 않는다.** W5-B 에서 만든다.

---

# 6. C1 이 도달하는 상태 — 미리 적어 둔다

| 항목 | C1 종료 시 |
|---|---|
| `declaration` | `PARTIAL_FREEZE` |
| `experiment_environment_v1_declared` | **`false`** |
| `overall` (V6) | `partial` (D-7 승인 시) 또는 `not_started` (미승인 시) |
| Lock 9종 | LOCKED **0** · PARTIAL 최대 4 · PENDING/OUT_OF_SCOPE 5 |
| `blocked[]` | 최소 2건 (Parquet 재현성 · 대시보드 격리 검사) |
| `simulator_commit` | `null` + 사유 |

**"GATE 1 통과"라고 적지 않는다. 어디에도.**

---

# 7. 결정이 필요한 항목

| # | 항목 | 선택지 | 추천 |
|---|---|---|---|
| **D-26** | `config/gate1_lock.yaml` 위치 | ⑴ `config/` (5번째 파일) ⑵ `docs/gate1_lock.yaml` ⑶ `docs/gate1_checklist.md` 안에 임베드 | **⑴.** 봉인 대상 config 옆에 두는 것이 자연스럽고 `data_spec` §15.2 의 `data_version.yaml` 선례와 형태가 같다. ⑶은 사람 문서와 기계 기록을 섞어 둘 다 나빠진다 |
| **D-27** | `mismatch` 에서 게시를 막는가 | ⑴ 게시하고 실패로 표시 ⑵ 게시를 막는다 | **⑴.** §4.3. ⑵는 봉인이 깨진 사실을 화면에서 지운다 |

*D-7(부분 Lock 실행 여부) · D-8(EVENT SCHEMA 범위)은 `gate1-lock-scope.md` §7 에 있다. D-16(`discount`)은 `api-contracts.md` §9.*

---

# 8. 미정으로 남긴 것

| 항목 | 왜 |
|---|---|
| `docs/gate1_checklist.md` 의 구체 서식 | `#49` 산출물. **Phillip T5.7 소관** |
| Lock 주체의 이름 | 사람이 정한다 |
| GATE 2·3·4 절차 | C1 범위 밖 |
| `EXPERIMENT_ENVIRONMENT_v1` 선언 시점 | 범위 B·C 완료 후 (`#49` 본문) |
| 재봉인 시 이전 기록 보존 방식 | `git log` 로 충분하다고 보나, 이력이 리포트에 필요해지면 `lock_history[]` 를 추가할 수 있게 `lock_record_version` 을 두었다 |
