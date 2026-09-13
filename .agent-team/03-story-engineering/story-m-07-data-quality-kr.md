---
story_key: M-07
epic: 범위 M — 측정 계층 (이슈 #42)
issue: "#48"
title: 데이터 품질 검증 — validate.py + 미실행을 통과로 적지 않기
status: done   # W5 Phillip 완료 — 18종 · 8개 검사 × 3축 negative control · DQ-06 이 M-01 로 BLOCKED 해소(7→8종 실행)
owner: Phillip (W5-A)
phase: "2'''"
blocked_by: ["M-01 (#53) D1-2 — strict=False 경로"]
blocks: ["M-06 게시 (data_quality_report)"]
closes_issue: false
source_hash: 85e5519b725c4840
source_files: 17
---

# M-07 · 데이터 품질 검증 (`#48`)

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
| **대상 이슈** | `#48` — OPEN (2026-09-11 라이브 확인) |
| **담당** | Phillip · W5-A |
| **Phase** | **2'''** — M-03/M-04 와 병렬 가능 |
| **차단** | **M-01 (`#53` D1-2)** — 위반 데이터를 저장하려면 `strict=False` 경로가 필요한데 **지금 크래시한다** |
| **★ 이 이슈는 C1 에서 닫히지 않는다** | 참조 무결성·재현성이 `BLOCKED`/`PRECONDITION_MISSING` 으로 남는다. **닫지 않고 열어둔다** |
| **커밋 type** | `feat` |

> ## ★ 이 스토리의 목적은 "무엇을 검사하는가"보다 **"무엇을 검사하지 않았는가를 어떻게 남기는가"** 다
> `data_spec` §9 의 항목 중 C1 에서 실행할 수 있는 것은 **절반이 안 된다.**
> **나머지를 목록에서 빼면 리포트는 초록이 되고, 검사하지 않은 것이 통과로 읽힌다.**
> `[Source: .agent-team/04-architecture/data-quality-design.md#머리말]`

---

# 2. 스토리

> **`P-팀`으로서 나는 품질 검사가 실패하면 경고가 아니라 중단이기를 원한다.**
> 왜냐하면 잘못된 데이터로 학습하면 **이후 전부 무효**이기 때문이다.
> `[Source: .agent-team/03-service-planning/user-stories.md#US-9]`

---

# 3. 인수 조건 (AC)

## AC-1 · 산출물

- [ ] `src/measurement/validate.py` 구현 — **`data_spec` §9 가 지정한 경로.** 발명하지 않는다
- [ ] 결과가 **`results/data_quality_report.json`** 에 간다 — 동일. **이동하지 않는다**
- [ ] `schemas/data_quality_report.schema.json` 을 통과한다

## AC-2 · C1 에서 실행 가능한 검사 7종

- [ ] `DQ-01` **유일성** — `event_id` 전역 유일
- [ ] `DQ-02b` **유일성(범위 축소)** — `order_id` 당 `purchase` 이벤트 정확히 1건
- [ ] `DQ-04` **시간 정합성** — 세션 내 이벤트 순서
- [ ] `DQ-07` **퍼널 정합성** — `purchase` ← 선행 `checkout_start`
- [ ] `DQ-08` **퍼널 정합성** — `coupon_use` ← 선행 `coupon_exposed`
- [ ] `DQ-10` **금액 정합성** — 음수 금액 0건
- [ ] `DQ-11` **완전성** — Key 결측 0%

## AC-3 · 실행 불가 11종을 **목록에 남긴다** ★  *(총 18종 = 실행 7 + 불가 11)*

- [ ] `DQ-02`·`DQ-03`·`DQ-05`·`DQ-09`·`DQ-12`~`DQ-16` → **`not_run` + `PRECONDITION_MISSING`**
- [ ] `DQ-06`·`DQ-17` → **`blocked` + `BLOCKED`** (해소 조건은 §4.3). ★ **픽스처는 `DQ-06` 을 `not_run`+`BLOCKED` 로 담았다 — §7.2 Q-2. 구현은 `blocked` 로 일관되게 낸다**
- [ ] **미실행 항목을 목록에서 빼지 않는다**
- [ ] `status` 가 `not_run`/`blocked`/`vacuous` 이면 **`violations` 는 `null`** — `0` 으로 적으면 통과처럼 읽힌다

## AC-4 · `gate_result` 3값 ★

- [ ] `pass` — 실행한 검사가 전부 통과했고 **실행하지 못한 검사가 없다**
- [ ] `incomplete` — 실행한 검사는 전부 통과했으나 **`not_run`·`blocked`·`vacuous` 가 하나 이상**
- [ ] `fail` — **데이터가 검사를 위반했다** → **중단** (`QualityGateFailure`, 종료 코드 2)
- [ ] **`gate_result == "pass"` 이려면 모든 검사가 `pass`** 여야 한다 — `vacuous` 하나만 있어도 `pass` 불가

## AC-5 · `vacuous` — 공허한 통과 차단 ★

- [ ] `examined_rows == 0` → `status` 가 **`pass` 일 수 없다**
- [ ] `status == "vacuous"` → `examined_rows == 0` ∧ `violations` 는 **`null`** ∧ **사유 필수**
- [ ] `status == "pass"` → `examined_rows >= 1`

## AC-6 · `scope` 필수

- [ ] **각 검사에 `scope` 가 있다** — *"이 검사가 실제로 무엇을 검사했는가"* 의 범위 한정 문구
- [ ] `examined_rows` 를 함께 낸다

## AC-7 · `spec_coverage`

- [ ] `data_spec` §9 의 **정본 항목 전부**가 `spec_items[]` 에 온다
- [ ] `unmapped_spec_items[]` — **정본에 있는데 아무 검사도 덮지 않는 항목**
- [ ] **화면이 정본 목록을 상수로 들지 않는다** — 게시물이 준다

## AC-8 · 의도적으로 깨뜨린 데이터로 검사한다 (`#48` 완료 조건)

- [ ] **실행 가능한 7개 검사 각각에 대해 위반 데이터를 만들어 `fail` 이 나오는지 확인한다**
- [ ] 그 테스트가 `tests/test_quality_checks.py` 에 있다

## AC-8b · ★ 계약 결함 3건 (리드 판정 · §7.2)

- [ ] **Q-1** — 검사 **18종**으로 구현한다 (설계 문서 본문 17 은 산술 오류)
- [ ] **Q-2** — `status: blocked` → `reason_code: BLOCKED` · `status: not_run` → `reason_code ∈ {NOT_RUN, PRECONDITION_MISSING}` 를 **스키마가 거부**한다 (M-06 T1 이 계약에 넣는다)
- [ ] **Q-3** — `reported_checks` 를 **`len(checks)` 로 산출**한다. **스키마로 표현할 수 없으므로** 게시 자기검증 + 테스트로 막는다
- [ ] ★ **픽스처 4개 규칙**(§4.15) — 18종 · `len(checks)` 산출 · 픽스처는 출력에서 · 도구 결함은 표기만
- [ ] ★ **Q-4** — **구현은 항상 18종을 낸다.** m-06 §4.14 **의도된 실패 목록에 등록**한다 (미등록이면 T5 가 회귀로 잡는다) **ID 집합 일치**(`{c.id for c in checks} == DQ_ALL_18`)를 단언한다 — **개수는 그것이 함의한다**. `commerce-connected` 의 7종을 **정답으로 삼지 않는다**
- [ ] ★ **`vacuous` → `reason_code` 금지 · `reason_detail` 필수** (Matthias 항목2)
- [ ] 셋 다 **일부러 어긋나게 만들어 실제로 거부·실패하는지 확인**한다
- [ ] `.agent-team/04-architecture/schemas/` 원본과 `examples/` 픽스처를 **고치지 않았다**

## AC-9 · 회귀 없음

- [ ] `python3 -m unittest discover -s tests` — 기준선 46건 회귀 0
- [ ] `python3 -m unittest tests.test_isolation -v` — 통과
- [ ] **의존성 설치 없이** 통과
- [ ] `python3 .agent-team/04-architecture/tools/check_ownership.py` — PASS

---

# 4. 개발 컨텍스트 (`developer_context`)

## 4.1 ★ `gate_result` 를 왜 3값으로 나누나

`data_spec` §9: *"하나라도 실패하면 파이프라인은 **중단**한다(경고로 넘어가지 않는다)."*

그대로 2값(`pass`/`fail`)으로 만들면 문제가 생긴다. **C1 에서는 검사의 절반이 실행 불가**인데:
- **`fail` 로 두면** 파이프라인이 영원히 멈춘다
- **`pass` 로 두면** 미실행이 통과가 된다

| 값 | 뜻 | 파이프라인 |
|---|---|---|
| `pass` | 실행한 검사가 전부 통과 ∧ **실행하지 못한 검사가 없다** | 진행 |
| **`incomplete`** | 실행한 검사는 전부 통과 ∧ **`not_run`·`blocked` 가 하나 이상** | **진행하되 화면·리포트에 크게 표시** |
| `fail` | **데이터가 검사를 위반했다** | **중단** |

> **`not_run` 은 데이터의 실패가 아니라 검사기의 한계다. 둘을 같은 값으로 적으면 책임 소재가 뒤바뀐다.**
> `[Source: .agent-team/04-architecture/data-quality-design.md#2]`

## 4.2 ★ `vacuous` — "검사했지만 아무것도 검사하지 않았다"

**리드가 개정 전 예시를 세어 확인한 것:**

```
examples/empty-sink/data_quality_report.json  (개정 전)
  검사 18건 중 status="pass" ∧ examined_rows==0  →  7건 (39%)
  DQ-01 · DQ-02b · DQ-04 · DQ-07 · DQ-08 · DQ-10 · DQ-11
```

**순진하게 구현하면 화면의 39% 가 초록 ✓ PASS 인데 아무것도 검사하지 않았다.**
`gate_result: incomplete` 라 **게이트 층은 정직했다. 거짓말한 것은 개별 검사 행이다.**
`scope` 가 산문으로 경고하지만 **산문은 색을 이기지 못한다.**

**→ `status` 에 `vacuous` 를 신설하고 두 층에서 강제한다:**

| 층 | 규칙 |
|---|---|
| 검사 행 | `examined_rows == 0` → `status` 가 **`pass` 일 수 없다** |
| 검사 행 | `status == "vacuous"` → `examined_rows == 0` ∧ `violations` 는 **`null`** ∧ 사유 필수 |
| 검사 행 | `status == "pass"` → `examined_rows >= 1` |
| **게이트** | `gate_result == "pass"` → **모든 검사가 `pass`** (→ `vacuous` 하나만 있어도 `pass` 불가) |

**개정 후 실측:** `empty-sink: 검사 18건 · gate=incomplete · 공허한 pass 0건 · vacuous 7건`

> **`vacuous` 는 오늘 이 저장소의 정상 상태다** — 데이터가 0행이므로.
> **화면이 그것을 실패로 그리면 안 되고, 통과로 그려도 안 된다.**
> `[Source: .agent-team/04-architecture/adr/ADR-0010-vacuous-pass.md]`

## 4.3 ★ 검사 18종 — C1 가능/불가 전수표

**불가능한 것도 전부 목록에 남는다.**

| ID | `data_spec` 항목 | 검사 | C1 | 사유 코드 |
|---|---|---|---|---|
| **DQ-01** | 유일성 | `event_id` 전역 유일 | ✅ | — |
| DQ-02 | 유일성 | `order_id` 전역 유일 | ❌ | `PRECONDITION_MISSING` — `orders` 테이블 미구현 |
| **DQ-02b** | 유일성(범위 축소) | **`order_id` 당 `purchase` 정확히 1건** | ✅ | — |
| DQ-03 | 참조 무결성 | 고아 `customer_id`·`product_id` 0건 | ❌ | `PRECONDITION_MISSING` — `customers`·`products` 미구현 |
| **DQ-04** | 시간 정합성 | 세션 내 이벤트 순서 | ✅ | — |
| DQ-05 | 시간 정합성 | `timestamp < signup_date` 0건 | ❌ | `PRECONDITION_MISSING` — `signup_date` 는 `customers` 컬럼 |
| **DQ-06** | 시간 정합성 | 모든 시각이 KST 단일 | ⚠️ | **`BLOCKED`** — 타임존 정책 미확정 (`#53` D1-3). **M-01 이 확정하면 실행 가능해진다** |
| **DQ-07** | 퍼널 정합성 | `purchase` ← 선행 `checkout_start` | ✅ | — |
| **DQ-08** | 퍼널 정합성 | `coupon_use` ← 선행 `coupon_exposed` | ✅ | — |
| DQ-09 | 금액 정합성 | `order_amount = Σ(unit_price×quantity) − discount`, 오차 0원 | ❌ | `PRECONDITION_MISSING` — **§4.4. 원리적으로 불가** |
| **DQ-10** | 금액 정합성 | 음수 금액 0건 | ✅ | — |
| **DQ-11** | 완전성 | Key 결측 0% | ✅ | — |
| DQ-12 | 완전성 | Feature 결측률 항목별 5% 미만 | ❌ | `PRECONDITION_MISSING` — `data/processed/` 미생성 · decision 소관 |
| DQ-13 | 생성 이탈률 | 15% ≤ rate ≤ 25% | ❌ | `PRECONDITION_MISSING` — 시뮬레이터 없음 |
| DQ-14 | 실험 균형 | \|SMD\| < 0.1 | ❌ | `PRECONDITION_MISSING` — `#48` 이 이미 범위 C 로 이관 |
| DQ-15 | 처치 강도 | ATE 3~6%p · 쿠폰 사용률 25~40% · Sleeping Dog 8~15% | ❌ | `PRECONDITION_MISSING` |
| DQ-16 | 4분면 분포 | Persuadables 20~30% 등 | ❌ | `PRECONDITION_MISSING` — **measurement 소관이 아니다.** Ground-truth 는 `diagnostics` 전용 |
| **DQ-17** | 재현성 | `events.parquet` SHA-256 일치 (`NFR-001`) | ⚠️ | **`BLOCKED`** — pyarrow 미설치. **M-05 도입으로 해소 가능** |

**실행 가능 7 · BLOCKED 2 · PRECONDITION_MISSING 9 = 18.**
> ⚠ `data-quality-design.md` §3 본문은 이 합을 **17** 로 적었으나 **같은 절의 표도 픽스처도 18 이다.** 본문이 산술 오류다 — §7.2 Q-1
`[Source: .agent-team/04-architecture/data-quality-design.md#3]`

> **`#48` 은 C1 에서 닫히지 않는다.** 다만 **`DQ-17` 은 M-05 의 의존성 도입으로 해소된다.**
> **8건이 아니라 7건만 남는 것과, 그 차이를 리포트가 정확히 말하는 것이 C1 의 성과다.**

## 4.4 ★ DQ-09 는 원리적으로 불가하다 — 두 겹의 장벽

### ① `discount` 필드가 없다

`schema.py` 가 `order_amount` 를 **`Σ(unit_price × quantity) − discount`** 로 정의하는데, **DATA-003 22컬럼에 `discount` 가 없다.**

실측 22컬럼: `event_id · customer_id · timestamp · event_type · session_id · session_duration · page_type · product_id · category · quantity · unit_price · order_id · order_amount · coupon_id · campaign_id · treatment_id · treatment_group · experiment_id · service_version · customer_version · simulator_version · random_seed`

### ② 품목 합계를 재구성할 수 없다

`_EVENT_RULES[PURCHASE]` 실측 — 필수 `session_id`·`page_type`·`order_id`·`order_amount`.
**`product_id`·`quantity`·`unit_price` 는 `purchase` 에서 `NOT_APPLICABLE` 이고, 값이 있으면 `validate_event()` 가 거부한다.**

→ **`purchase` 는 주문 단위 1행이다. 한 주문의 `Σ(unit_price × quantity)` 가 `events` 안에 없다.**
`add_to_cart` 로 근사하는 것은 부정확하다 — `remove_from_cart` 가 있고, 담았지만 사지 않은 품목이 있고, 결제 실패가 있다.

**→ `DQ-09` 는 `order_items` 테이블이 있어야 성립한다. C1 에서 `not_run` + `PRECONDITION_MISSING`.**

**대신 `DQ-10`(음수 0건)은 실행한다. 두 검사를 하나로 묶어 "금액 정합성 통과"로 적으면 안 된다 — 그래서 ID 를 나눴다.**

`[Source: .agent-team/04-architecture/data-quality-design.md#4]` · `[Source: .agent-team/04-architecture/api-contracts.md#8]`

## 4.15 ★★ 픽스처 결함은 **여기서 고치지 않는다** — 4개 규칙 (리드 판정 CR-2)

`tools/make_examples_connected.py` 는 **`checks` 7종과 `reported_checks: 6` 을 소스에 하드코딩**했다(453·456행 실측).
**재생성해도 같은 7종이 나온다. 버그가 도구 안에 있다.**
빠진 11종을 채우려면 `DQ-03`·`DQ-13`·`DQ-14` 각각의 `status`·`reason_code`·`examined_rows` 를 **판단**해야 하는데, **그 판단은 이 스토리가 실제 데이터로 할 판단과 같다. 두 번 저작하면 반드시 어긋난다.**

| # | 규칙 |
|---|---|
| **①** | **항상 18종을 낸다.** 실행 못 한 것은 `not_run`/`vacuous`/`blocked` 로 **목록에 남긴다. 빼지 않는다** (`AC-3`) |
| **②** | **`reported_checks` 를 상수로 적지 않는다.** `len(checks)` 로 산출한다 (`Q-3`) |
| **③** | **픽스처를 새로 만들 일이 생기면 이 모듈의 출력에서 만든다. 손으로 저작하지 않는다** |
| **④** | `make_examples_connected.py` 의 하드코딩 7종·`reported_checks: 6` 은 **W2 스냅샷의 알려진 결함**이다. **고치지 않고 결함으로 표기**한다 — m-06 §4.14 의도된 실패 목록 |

> **③이 요점이다.** 픽스처가 정본 노릇을 하는 자리가 여럿이라, **진짜 판정을 하는 코드에서 나온 것만 픽스처가 될 수 있다.**

## 4.5 ★ 알고리즘 — 25,000,000 행에서도 돌아야 한다

`data_spec` §7.1 의 예상 행 수는 `events ≈ 25,000,000` 이다. W1 실측은 4,200,000행 / 112.6MB.
**메모리로 다 올릴 수 없다. 설계를 미리 정하지 않으면 구현이 `set()` 하나로 시작하고 규모가 커질 때 터진다.**

### `DQ-01` 유일성 — 정렬 병합

```text
① 파티션마다 event_id 를 뽑아 정렬해 임시 파일에 쓴다   (파티션 하나는 메모리에 올라간다)
② heapq.merge() 로 정렬된 스트림을 병합한다            (표준 라이브러리 · 메모리 O(파티션 수))
③ 이웃한 두 값이 같으면 중복이다
```

- **표준 라이브러리만** (`heapq` · `tempfile`)
- 메모리는 파티션 하나 + 병합 힙. **전체 행 수에 비례하지 않는다**
- 임시 파일은 `tempfile.TemporaryDirectory()` — **`data/`·`results/` 를 오염시키지 않는다**

> **`set()` 에 25M UUID 를 담지 않는다.** 대략 3GB 이상이 필요하고 개발 기계에서 조용히 스왑하거나 CI 에서 죽는다.
> **"오늘 0행이라 돌아간다"는 설계가 아니다.**

### `DQ-04`·`DQ-07`·`DQ-08` — ★ 파티션 경계를 넘는다

> ⚠ **함정: 세션과 주문은 자정을 넘는다.**
> 파티션(날짜)별로 검사하면 **23:58 `checkout_start` → 00:02 `purchase` 인 정상 주문이 위반으로 잡힌다.**

```text
① 전 파티션을 스캔하며 (key, event_type, timestamp) 만 뽑는다
     DQ-04 → key = session_id
     DQ-07 → key = order_id
     DQ-08 → key = coupon_id
② key 로 정렬해 임시 파일에 쓴다 (위와 같은 방식)
③ 같은 key 의 이벤트를 모아 순서를 검사한다
```

**레코드 전체가 아니라 3개 필드만 나르므로 메모리가 작다.**

### `DQ-17` 재현성 — 무엇과 무엇을 비교하나

`NFR-001`: *"동일 seed·동일 config 로 재실행 시 `events.parquet` 의 SHA-256 이 일치한다."*
**C1 에는 재생성할 주체(시뮬레이터)가 없다.** 그래서 두 층으로 나뉜다:

| 층 | C1 | 방법 |
|---|---|---|
| **Sink 의 결정성** — 같은 입력을 두 번 쓰면 같은 바이트 | `jsonl.gz` ✅ (`test_sink.py:216-225`) / **Parquet ⚠️ `BLOCKED`** | 테스트 |
| **파이프라인 재현성** — 같은 seed 로 재생성하면 같은 데이터 | ❌ | 시뮬레이터 사이클 |

**`DQ-17` 이 검사하는 것은 첫째 층뿐이며 그 범위를 `scope` 에 적는다.**
그리고 **형식이 다르면 해시가 다르다** — 재현성 대조는 **같은 형식끼리만** 성립한다. 이것도 `scope` 에 적는다.

`[Source: .agent-team/04-architecture/data-quality-design.md#5]`

## 4.6 `scope` 는 선택 항목이 아니다

스키마가 각 검사에 **`scope` 를 필수**로 요구한다.

**예 — `DQ-01`:**
> *"저장된 `events` 파티션 전 구간. 오늘은 0행이므로 위반이 없는 것이 아니라 **검사 대상이 없다** — `examined_rows` 를 함께 읽어야 한다."*

**범위 문구가 없으면 부분 검사가 전체 검사로 읽힌다.**
`[Source: .agent-team/04-architecture/design-patterns.md#P-10]`

## 4.7 ★ `#53` 이 이 스토리의 선행이다

> `#48` 완료 조건: *"의도적으로 깨뜨린 데이터로 각 검사가 실제로 실패하는지 확인한다."*

| 검사 | 깨뜨리는 방법 |
|---|---|
| `DQ-01` | 같은 `event_id` 를 서로 다른 파티션에 하나씩 |
| `DQ-02b` | 같은 `order_id` 로 `purchase` 두 건 |
| `DQ-04` | 같은 세션에서 `purchase` 가 `session_start` 보다 이르게 |
| `DQ-07` | `checkout_start` 없는 `purchase` |
| `DQ-08` | `coupon_exposed` 없는 `coupon_use` |
| **`DQ-10`** | **음수 `order_amount`** — `validate_event()` 가 수집 시점에 막는다 → **`strict=False` 로 Sink 를 우회해 저장해야 한다** |
| **`DQ-11`** | **`customer_id` 가 `None`** — 동일 |

> ⚠ **`DQ-10`·`DQ-11` 의 위반 데이터는 `strict=False` 경로가 필요한데 그 경로가 지금 크래시한다** (`#53` D1-2).
> **→ `#53` 이 `#48` 의 선행이다.**
> `[Source: .agent-team/04-architecture/data-quality-design.md#6]`

> ⚠⚠ **M-01 이 `strict=False` 를 "거부하되 저장하지 않는다"로 고치면 이 경로가 여전히 막힌다.**
> M-01 §4.6 T-3 이 *"`strict=False` 는 '수집이 실패하지 않는다'이지 '무효 데이터를 저장한다'가 아니다"* 로 판정했다.
>
> **→ 위반 데이터를 만드는 다른 방법이 필요하다.** 셋 중 하나 (§9.3 M07-a):
> | 안 | 방법 |
> |---|---|
> | a | **파일을 직접 쓴다** — `_write_rows()`(모듈 수준 함수, `sink.py:283`)를 테스트에서 호출하거나 `jsonl.gz` 를 손으로 만든다. `validate.py` 는 파일을 읽으므로 Sink 를 우회해도 검사가 성립한다 |
> | b | `EventSink` 에 테스트 전용 우회 경로를 만든다 — **제품 코드에 테스트 전용 문을 여는 것은 피한다** |
> | c | M-01 의 `strict=False` 를 "저장한다"로 재해석 — **`MEA-003` 해석이 바뀌므로 M-01 과 합의 필요** |
>
> **a 를 권장한다.** `validate.py` 의 입력은 **저장된 파일**이지 Sink API 가 아니다.

> ### ★ a 를 고를 때 빠뜨리기 쉬운 한 줄 (Thomas 답변4)
> **테스트가 `root/events/date=YYYY-MM-DD/part-NNNN.jsonl.gz` 구조까지 만들어야 한다.**
> `read_events()` 는 `(root/"events").rglob("part-*")` 로 찾는다 — 경로가 틀리면 **조용히 0건**을 읽고, 검사는 **`vacuous`** 가 되어 **통과처럼 보이는 실패**가 된다.
> **위반 데이터를 넣었는데 `fail` 이 아니라 `vacuous` 가 나오면 경로가 틀린 것이다.** 테스트가 그것을 구분해야 한다.

**검사가 잡는지 확인하지 않은 검사는 없는 검사와 같다** — `data_spec` §17.5 가 격리 검사에 대해 같은 것을 했다(*"규칙을 일부러 어기는 파일 3개를 넣었을 때 6종 위반을 모두 보고하고 실패했다"*). **같은 규율을 품질 검사에도 적용한다.**

## 4.8 데이터가 0행일 때 — 오늘의 상태

| 검사 | 0행에서 | 왜 |
|---|---|---|
| `DQ-01` 유일성 | **`vacuous`** · `examined_rows: 0` · `violations: null` | 중복이 없는 것은 사실이지만 **검사 대상이 없다** |
| `DQ-10` 음수 금액 | **`vacuous`** · 동일 | 동일 |
| `gate_result` | **`incomplete`** | `not_run` 10 + `blocked` 1 + `vacuous` 7 = 18 (픽스처 실측) |

> ⚠ **`data-quality-design.md` §5.4 는 0행에서 `pass`(+`examined_rows: 0`)라고 적었다.**
> **그것은 `ADR-0010`(`vacuous` 신설) 이전 서술이다.** `ADR-0010` 과 개정 후 실측(`vacuous` 7건)이 정본이다.
> **`vacuous` 를 쓴다.**

## 4.9 실패 처리 — `fail` 은 중단이다

`validate.py` 는 **`QualityGateFailure` 를 던지고 종료 코드 `2`** 를 낸다.
게시는 **리포트까지만** 하고 그 뒤 단계를 진행하지 않는다.
`[Source: .agent-team/04-architecture/exceptions.md#2.1, #5]`

**단 C1 에는 "그 뒤 단계"가 없다** — orchestration 이 미가동이다. **리포트 게시까지가 이 스토리의 끝이다.**

## 4.10 함정

| # | 함정 | 왜 빠지나 | 대신 |
|---|---|---|---|
| **T-1** | 0행에서 `pass` | 위반이 0건이니까 | §4.2 — **`vacuous`.** 아무것도 검사하지 않았다 |
| **T-2** | `not_run` 에 `violations: 0` | 숫자를 채워야 할 것 같다 | **`null`.** `0` 은 "위반 0건"으로 읽히고 그것이 미실행을 통과로 만드는 가장 흔한 경로다 |
| **T-3** | 실행 불가 검사를 목록에서 뺀다 | 리포트가 깨끗해진다 | AC-3 — **빠진 검사가 사라지고, 사라진 것은 통과처럼 읽힌다** |
| **T-4** | `set()` 에 전 `event_id` 를 담는다 | 가장 짧다 | §4.5 — 25M 에서 죽는다 |
| **T-5** | 파티션(날짜)별로 세션·퍼널을 검사한다 | 파티션 단위가 자연스럽다 | ★ §4.5 — **자정을 넘는 세션이 위반으로 잡힌다** |
| **T-6** | `DQ-09` 를 `add_to_cart` 로 근사 | 값이 나온다 | §4.4 — **장바구니 ≠ 주문.** `PRECONDITION_MISSING` |
| **T-7** | `DQ-09`·`DQ-10` 을 "금액 정합성" 하나로 묶는다 | `data_spec` 이 한 항목이다 | **ID 를 나눈 이유가 이것이다.** 하나가 불가일 때 다른 하나가 묻힌다 |
| **T-8** | 임시 파일을 `data/` 나 `results/` 에 만든다 | 편하다 | **`tempfile.TemporaryDirectory()`.** 산출물 디렉터리를 오염시키지 않는다 |
| **T-9** | `gate_result` 를 2값으로 | 단순하다 | §4.1 — 요약 한 줄이 초록이 되고 **요약만 보는 사람이 대부분이다** |
| **T-10** | `DQ-02` 를 목록에서 빼고 `DQ-02b` 만 둔다 | 중복 같다 | **결정 D-25 ⑴** — 정본 항목이 사라져 `data_spec` §9 와 1:1 대응이 깨진다 |
| **T-11** | `validate.py` 가 게시까지 한다 | 한 곳에서 끝내고 싶다 | **`validate.py` 는 결과 객체만 돌려준다. 게시는 `publish.py`** (`code-structure.md` §4) |
| **T-12** | `except Exception: continue` 로 검사 하나를 건너뛴다 | 견고해 보인다 | **금지.** 예외를 사유 없이 삼키지 않는다. `blocked` 로 사유와 함께 기록한다 |

---

# 5. 작업 분해 (Tasks)

## T1 · 검사 목록 골격 (AC-3·6·7)

- [ ] **18종 전부를** 정의로 둔다 — ID · `spec_ref` · 제목 · `scope` 문구 (§7.2 Q-1)
- [ ] 실행 가능 7 / `blocked` 2 / `not_run` 9 로 분류
- [ ] `reported_checks = len(checks)` 로 낸다 (§7.2 Q-3)
- [ ] `spec_coverage.spec_items[]` — `data_spec` §9 정본 항목과 `covered_by` 매핑
- [ ] `unmapped_spec_items[]` 계산

## T2 · 실행 가능 7종 구현 (AC-2)

- [ ] `DQ-01` — 정렬 병합 (§4.5)
- [ ] `DQ-02b` — `order_id` 당 `purchase` 1건
- [ ] `DQ-04`·`DQ-07`·`DQ-08` — **파티션 경계를 넘는 키 기반 정렬** (§4.5)
- [ ] `DQ-10` — 음수 금액
- [ ] `DQ-11` — Key 결측
- [ ] 각각 `examined_rows` 를 정확히 센다

## T3 · 상태 판정 (AC-4·5)

- [ ] `examined_rows == 0` → `vacuous`
- [ ] `violations` 를 `not_run`/`blocked`/`vacuous` 에서 `null` 로
- [ ] `gate_result` 3값 산출 — **전건 `pass` 일 때만 `pass`**
- [ ] `fail` 이면 `QualityGateFailure` + 종료 코드 2

## T4 · 위반 탐지 테스트 (AC-8) ★

- [ ] `tests/test_quality_checks.py` — **7개 검사 각각에 위반 데이터**
- [ ] §4.7 의 방법 a(파일 직접 생성)로 `DQ-10`·`DQ-11` 위반 데이터 생성
- [ ] 각 검사가 실제로 `fail` 을 내는지 확인
- [ ] **위반이 없는 정상 데이터에서는 `pass` 가 나오는지도** 확인 (양방향)

## T5 · 0행 동작 테스트

- [ ] 빈 Sink 에서 7종이 **`vacuous`** 가 되는지
- [ ] `gate_result` 가 **`incomplete`**
- [ ] 공허한 `pass` 가 **0건**

## T5b · ★ 계약 결함 3건 (AC-8b)

- [ ] Q-1 — 18종 구현
- [ ] Q-2 — **M-06 에 스키마 `allOf` 2건을 요청**하고, `validate.py` 가 일관된 조합만 내는지 테스트
- [ ] Q-3 — `reported_checks = len(checks)` · 어긋난 값을 만들어 **자기검증이 거부하는지** 확인
- [ ] **의도된 계약 차이 목록**에 Q-2 를 등록 (M-06 T6)

## T6 · 게시 연결 (M-06 과)

- [ ] `validate.py` 는 **결과 객체만** 돌려준다. `publish.py` 가 `results/data_quality_report.json` 에 쓴다
- [ ] 스키마 통과 확인

## T7 · 검증 (AC-9)

- [ ] `python3 -m unittest discover -s tests` — 출력 전문 + skip 수·사유
- [ ] `python3 -m unittest tests.test_isolation -v`
- [ ] `python3 .agent-team/04-architecture/tools/check_ownership.py`

---

# 6. 파일 목록 (`file_list`)

## 6.1 이 스토리가 만드는 파일

| 파일 | 동작 |
|---|---|
| `src/measurement/validate.py` | **신설** — `data_spec` §9 지정 경로 |
| `tests/test_quality_checks.py` | **신설** |
| `.agent-team/04-architecture/tools/ownership.json` | **수정하지 않는다** — 이미 등록돼 있다(Thomas N-1). 돌려 **확인만** |

## 6.2 절대 만지지 않는 파일

```
tests/test_isolation.py · .github/workflows/isolation.yml          ← 봉인
src/simulator/** src/decision/** src/diagnostics/** src/orchestration/**
Plan/** · AGENTS.md · src/AGENTS.md · README.md
dashboard/**                                                       ← Andrew
data/hidden/** · data/ground_truth/**                              ← ★ measurement 는 참조조차 금지
../Ecommerce_Service/**
```

> ⚠ **`validate.py` 에 `data/hidden`·`data/ground_truth` 문자열을 쓰면 `test_isolation.py` 가 실패한다.**
> `DQ-16`(4분면 분포)이 Ground-truth 를 요구하지만 **measurement 소관이 아니다.** 그 사실을 `reason_detail` 에 적되 **경로 문자열을 쓰지 않는다.**

---

# 7. 테스트

## 7.1 실행 가능한 명령

```bash
python3 -m unittest discover -s tests
python3 -m unittest tests.test_quality_checks -v
python3 -m unittest tests.test_isolation -v
python3 .agent-team/04-architecture/tools/check_ownership.py
```

## 7.2 픽스처가 기대 형태를 준다

```
.agent-team/04-architecture/examples/empty-sink/data_quality_report.json
.agent-team/04-architecture/examples/commerce-connected/data_quality_report.json
```

**구조 실측:** `gate_result` · `spec_coverage{spec_items, reported_checks, unmapped_spec_items}` · `checks[]{id, spec_ref, title, status, violations, examined_rows, scope}`

**W3 가 픽스처를 직접 세어 확인한 실측 (2026-09-11):**

```
empty-sink          checks 18 · gate=incomplete · {vacuous:7, not_run:10, blocked:1}
                    ids: DQ-01 02 02b 03 04 05 06 07 08 09 10 11 12 13 14 15 16 17
                    vacuous: DQ-01 · DQ-02b · DQ-04 · DQ-07 · DQ-08 · DQ-10 · DQ-11
                    spec_coverage.spec_items 11개 · reported_checks 18 · unmapped []

commerce-connected  checks 7 · gate=fail · {pass:4, fail:1, not_run:1, blocked:1}
                    ids: DQ-01 02b 07 08 10 09 17
                    spec_coverage.spec_items 11개 · reported_checks 6 · unmapped []
```

### ★ 계약 결함 3건 — **리드 판정: 한 스토리로 묶어 고친다** (2026-09-11)

W3 이 픽스처를 세어 찾았고 **리드가 재현 확인**했다. **셋 다 이 스토리가 고친다.**

| # | 결함 | 실측 | 조치 | 수단 |
|---|---|---|---|---|
| **Q-1** | 검사 총수 **17 vs 18** | `data-quality-design.md` §3 **본문이 17**, 같은 절 **표와 픽스처가 18** | **18 로 구현.** 본문이 산술 오류 | 구현 |
| **Q-2** | **`DQ-06` 의 `status`↔`reason_code` 가 어긋난다** | 픽스처: `status: "not_run"` + `reason_code: "BLOCKED"` | **`blocked`+`BLOCKED` 로 일관되게 내고, 스키마가 어긋난 조합을 거부하게 한다** | ★ **스키마** |
| **Q-3** | **`reported_checks` 가 실제 검사 수와 다르다** | `commerce-connected`: `checks` **7건**인데 `reported_checks: 6` | **`reported_checks = len(checks)` 로 낸다** | ★ **자기검증 — 스키마 불가** |

### ★★ Q-4 — **`commerce-connected` 가 11종을 목록에서 뺐다. 정답으로 삼지 않는다** (Matthias CR-2)

```
empty-sink          checks 18  (전종)
commerce-connected  checks  7  ← DQ-02·03·04·05·06·11·12·13·14·15·16  11종 누락
```

**이것은 AC-3 *"미실행 항목을 목록에서 빼지 않는다"* · 스키마 `checks` 설명 *"목록에서 빼면 '검사하지 않았다'가 보이지 않는다"* · d-02 V5 *"게시물이 18건 전부 준다"* 와 정면 충돌한다.**

**추가로 AC-2 와도 어긋난다** — 실린 7종 중 실제 실행은 **5종**(`DQ-01`·`02b`·`07`·`08`·`10`)이고 **`DQ-04`·`DQ-11` 이 아예 없으며** AC-2 에 없는 `DQ-09`(`not_run`)·`DQ-17`(`blocked`)이 들어 있다.

> ### ★ `Q-3` 은 증상이고 이것이 원인이다
> `reported_checks = len(checks)` 만 고치면 **`7` 이 되고 11종 소실은 그대로 남는다.**
> **`reported_checks == len(checks)`** 는 *"보고한 수 = 실린 수"* 만 보장하고 *"실려야 할 것이 다 실렸다"* 는 **보장하지 않는다. 두 명제는 다르다.**
> 스키마는 `minItems: 1` 뿐이라 못 잡고, **M-06 T5 픽스처 대조 테스트가 7을 정답으로 굳힐 수 있다.**

**→ 3층 자기검증에 세 번째 명제를 넣는다:**

```python
assert len(checks) == len(DQ_ALL_18)          # ★ 실려야 할 것이 다 실렸다 — 상수를 두 번 적지 않는다
assert reported_checks == len(checks)         # 보고한 수 = 실린 수
assert {c.id for c in checks} == DQ_ALL_18    # ★ 빠진 ID 가 무엇인지 말한다
```

| 규칙 | 내용 |
|---|---|
| **구현은 항상 18종을 낸다** | 실행 못 한 것도 `not_run`/`blocked` 로 |
| ★ **`commerce-connected` 를 정답으로 삼지 않는다** | **7종은 픽스처의 결함이다.** M-06 §4.14 의 **의도된 실패 목록**에 등록한다 |
| **픽스처를 고치지 않는다** | W2 산출물 |
| **세 번째 assert 가 요점** | 수만 세면 *"어느 것이 빠졌는지"* 를 못 말한다 |
| ★ **`18` 을 리터럴로 적지 않는다** | `DQ_ALL_18` 하나가 정본이다. **`Q-3` 에서 세운 원칙**(*"상수를 두 번 적지 않는 것이 가장 싼 방어"*)을 그 검사 자신이 어기면 안 된다 |

### Q-2 — 스키마로 막는다 (표현 가능)

**계약이 이 둘을 명시적으로 갈랐다** — `BLOCKED`(환경 제약으로 **못 했다**) vs `NOT_RUN`(**안 했다**).
*"실행 안 한 것을 못 한 것으로 적으면 책임이 환경으로 넘어간다."* `[Source: .agent-team/04-architecture/api-contracts.md#4.4]`

**그런데 스키마가 이 조합을 막지 않는다** — 실측: `checks[].items.allOf` 5개 중 `status` ↔ `reason_code` 를 묶는 제약이 **없다.**

**→ `docs/contracts/.../data_quality_report.schema.json` 에 `allOf` 를 추가한다:**

```jsonc
{ "if":   { "properties": { "status": { "const": "blocked" } }, "required": ["status"] },
  "then": { "properties": { "reason_code": { "const": "BLOCKED" } } } },
{ "if":   { "properties": { "status": { "const": "not_run" } }, "required": ["status"] },
  "then": { "properties": { "reason_code": { "enum": ["NOT_RUN", "PRECONDITION_MISSING"] } } } },

```

**`vacuous` 는 다르다 — 추가가 아니라 `allOf[2]` 를 *교체*한다:**

```jsonc
// ❌ 새 allOf 로 "추가"하면 vacuous 행이 전부 실패한다 — 아래 재현 참조
// ✅ checks.items.allOf[2] 자체를 이 형태로 바꾼다
{ "$comment": "공허한 통과는 검사 대상이 0행이었다는 사실을 낸다. status 가 이미 사유이므로 reason_code 는 금지한다.",
  "if":   { "properties": { "status": { "const": "vacuous" } }, "required": ["status"] },
  "then": { "required": ["examined_rows", "reason_detail"],
            "properties": { "examined_rows": { "const": 0 }, "violations": { "type": "null" } },
            "not": { "required": ["reason_code"] } } }
```

> ### ★★ 왜 "추가"가 아니라 "교체"인가 — **W3 이 validator 로 재현했다 (2026-09-11 · jsonschema 4.26.0)**
>
> **현행 `checks.items.allOf[2]` 는 `vacuous` 에 `reason_code` 를 `required` 로 걸고 있다** (실측).
> 그 위에 *"금지"* 절을 **더하면 두 절이 동시에 참이어야 하므로 `vacuous` 행이 어느 쪽으로도 통과하지 못한다:**
>
> ```
> 현행 allOf[2]          reason_code 없음        → 거부  'reason_code' is a required property
>                        reason_code:NOT_RUN     → 통과
>
> ★ 추가만 한 경우        reason_code 없음        → 거부   (allOf[2] 가 required 라서)
>                        reason_code:NOT_RUN     → 거부   (새 절의 not 이 걸려서)
>                        ⇒ vacuous 는 무엇을 써도 실패한다. 계약이 만족 불가능해진다
>
> ★ allOf[2] 를 고친 경우 reason_code 없음        → 통과  ✅
>                        reason_code:NOT_RUN     → 거부  ✅  (의도한 대로)
> ```
>
> **`empty-sink` 의 `vacuous` 7건이 오늘의 정상 상태다.** 만족 불가능해지면 **오늘의 정상 상태를 게시할 수 없게 된다.**
> **→ M-06 T1 이 `allOf[2]` 를 *교체*한다.** `required` 목록에서 `reason_code` 를 빼고 `not` 을 더한다. **두 편집이 한 쌍이다 — 하나만 하면 위 표의 실패로 간다.**

> ### ★ `vacuous` 에 `reason_code` 를 **금지**하는 이유 (Matthias 항목2)
> **`empty-sink` 의 `vacuous` 7건이 전부 `reason_code: "NOT_RUN"` 이다** (실측).
> **"실행했는데 0행"과 "실행 안 함"이 한 행에 섞인 것** — `Q-2` 와 **똑같은 종류의 결함**이다.
> 그리고 CR-1 과 맞물려 **화면이 `("vacuous","NOT_RUN")` 자기모순 쌍을 받는다.**
>
> **`vacuous` 는 `status` 자체가 이미 "실행했으나 대상 0행"을 말한다.** 남은 `reason_code` 9종이 **전부 틀리다** — `NOT_RUN`(안 했다)·`BLOCKED`(못 했다)·`PRECONDITION_MISSING`(대상 자체가 없다) 어느 것도 맞지 않는다.
>
> **enum 에 `VACUOUS` 를 늘리지 않는다** — m-02 AC-6 의 **문자 단위 계약 대조**까지 네 스토리가 동시에 움직인다.
> **⚠ 이 제약은 기존 스키마의 `allOf[2]`(vacuous → `reason_code` required)와 충돌한다.** **M-06 이 그 항목을 *교체*한다 — 위 재현 참조. 새 절로 추가하면 계약이 만족 불가능해진다.**

> **`denominator == 0 → ok 불가` · `examined_rows == 0 → pass 불가` 와 같은 자리, 같은 패턴이다.**
> *"담지 마라는 어길 수 있지만 담을 자리가 없다는 어길 수 없다."*

### ★ Q-3 — **스키마로 표현할 수 없다.** 자기검증으로 막는다

> **JSON Schema draft 2020-12 에는 필드 값을 다른 필드의 배열 길이와 비교하는 수단이 없다.**
> `minItems`·`maxItems`·`const`·`enum` 은 전부 **자기 자리의 값**만 본다. 교차 필드 비교 키워드가 없다.
> (`$data` 는 Ajv 확장이지 표준이 아니다.)
>
> **→ `reported_checks == len(checks)` 를 스키마에 적으려고 시도하지 마십시오. 시간만 쓰고 안 됩니다.**

**대신 두 곳에서 막는다:**

| 층 | 어떻게 |
|---|---|
| **게시 시점 자기검증** (`contracts.py` · M-06) | `reported_checks != len(checks)` 면 **`ContractViolation`** → **fail closed.** 게시되지 않는다 |
| **테스트** (`tests/test_quality_checks.py`) | 등식을 단언. 일부러 어긋나게 만들어 **실제로 실패하는지** 확인 |

**그리고 애초에 어긋날 수 없게 만든다** — `reported_checks` 를 **손으로 세지 않고 `len(checks)` 로 산출한다.**
**상수를 두 번 적지 않는 것이 가장 싼 방어다.**

> **`.agent-team/04-architecture/schemas/` 원본과 `examples/` 픽스처는 고치지 않는다.** W2 산출물이다.
> **저장소에 들어갈 계약(`docs/contracts/**`)은 Phillip 소유**이므로 Q-2 수정은 **M-06 T1 이 실행한다.** 이 스토리는 **무엇을 담을지**를 정하고 **검사로 고정**한다.

## 7.3 깨뜨리면 안 되는 기존 테스트

| 테스트 | 이유 |
|---|---|
| `test_sink.py:216-225 test_same_input_gives_same_digest` | `DQ-17` 첫째 층의 기존 증거 |
| `test_sink.py:198-203` | USP-1 회귀 |
| `test_isolation.py` 6건 | `validate.py` 도 자동 검사 대상 |

---

# 8. 연속성

## 8.1 선행 스토리에서 이어받는 것

| 스토리 | 이어받는 것 |
|---|---|
| **M-01 (`#53`)** | ★ **타임존 정책** → `DQ-06` 이 `BLOCKED` 를 벗어나는지 · **`strict=False` 경로의 최종 동작** → §4.7 위반 데이터 생성 방법 |
| **M-03 (`#47`)** | `errors.py` 의 `QualityGateFailure`(종료 2) |
| **M-05 (의존성)** | ★ **`DQ-17` 이 해소됐는지** · 형식 차이가 재현성 대조에 미치는 영향 |
| **M-06 (게시)** | 게시 경로·봉투. **`validate.py` 는 결과 객체만 돌려준다** |

## 8.2 확립된 패턴

| 패턴 | 어디에 |
|---|---|
| **표준 라이브러리만** | `heapq`·`tempfile`·`json`·`gzip` |
| `read_events(root)` 로 되읽기 | `sink.py` — `validate.py` 가 이것을 쓴다 |
| 한글 독트링·메시지 | 전 파일 |
| **`scope` 처럼 "무엇을 검사했는가"를 문장으로** | `P-10` 범위 한정 문구 필수화 |

---

# 9. 완료 정의 (DoD) · 미결정 · 차단

## 9.1 DoD

- [ ] AC-1 ~ AC-9 전부 체크
- [ ] **18종이 전부 목록에 있다.** 실행 못 한 것도
- [ ] **공허한 `pass` 가 0건이다** — 0행 데이터로 확인
- [ ] **7개 검사 각각이 위반 데이터에서 실제로 실패한다**
- [ ] `DQ-06`·`DQ-17` 의 최종 상태(`blocked` 유지 / 해소)를 M-09 에 인계했다
- [ ] ★ **계약 결함 3건(Q-1·Q-2·Q-3)을 고쳤다.** Q-3 은 **스키마로 표현 불가**이므로 자기검증+테스트로 막았고 **그 사실을 PR 에 적었다**
- [ ] ★ **`#48` 을 닫지 않았다.** 미실행 항목을 `BLOCKED`·`not_run` 으로 남기고 **이슈를 열어둔다**

## 9.2 이 스토리에서 하지 않는 것

| 항목 | 왜 |
|---|---|
| 참조 무결성 (`DQ-03`·`DQ-05`) | `customers`·`products` 테이블 미구현 |
| Feature 결측률 (`DQ-12`) | `data/processed/` 미생성 · decision 소관 |
| 시뮬레이터 의존 4건 (`DQ-13`~`DQ-16`) | 시뮬레이터 없음. `DQ-16` 은 **measurement 소관도 아니다** |
| 금액 정합성 (`DQ-09`) | **원리적으로 불가** (§4.4) |
| 6개 추가 테이블 구현 | C1 범위 밖 |
| 25M 행 **실측 성능** | 데이터가 없다. **알고리즘 제약만 반영하고 측정은 시뮬레이터 사이클로** |
| 게시 | **M-06 의 `publish.py`** |

## 9.3 미결정 — 구현자가 정하고 PR 에 적는다

| # | 항목 | 선택지 |
|---|---|---|
| **M07-a** | ★ **위반 데이터 생성 방법** | **a 파일 직접 생성 (권장)** / b Sink 테스트 우회 경로 / c `strict=False` 재해석 (M-01 과 합의) — §4.7 |
| **M07-b** | ~~검사 총수~~ | ★ **해소 — 18 이다.** W3 이 픽스처를 세어 확인했고 **리드가 재현 확인**했다 (§7.2 Q-1) |
| **M07-c** | `validate.py` 함수 시그니처 | 아키텍처가 미정으로 남겼다 — *"이 문서는 검사 목록·의미·알고리즘 제약까지다"* |
| **D-24** | `gate_result` 3값 | **⑴ `pass`/`incomplete`/`fail` (권장)** ⑵ 2값 + 별도 필드 |
| **D-25** | `DQ-02` 원본을 목록에 남기는가 | **⑴ 남긴다 (권장)** ⑵ `DQ-02b` 만 |

## 9.4 차단

| # | 항목 | 성격 |
|---|---|---|
| **M-01 (`#53` D1-2)** | 위반 데이터 생성 경로 | **선행 스토리.** M07-a 로 우회 가능 |
| **M-05** | `DQ-17` 해소 여부 | 없어도 진행 가능 — `blocked` 유지 |

## 9.5 하류로 넘기는 것

| 받는 쪽 | 넘기는 것 |
|---|---|
| **M-06 (게시)** | `data_quality_report` 내용 객체 · `gate_result` · `spec_coverage` |
| **M-09 (`#49`)** | **`BLOCKED` 항목의 최종 목록** — `docs/gate1_checklist.md` 의 `BLOCKED` 절에 그대로 들어간다 · `DQ-09` 가 원리적으로 불가하다는 사실 → `EVENT_SCHEMA_v1` 의 `scope_note` |
| **d-02 (대시보드)** | V5 화면이 그릴 5상태 · `vacuous` 가 **오늘의 정상 상태**라는 사실 · `gate_result: incomplete` 에 `success` 토큰을 쓰지 않는다는 규칙 |

<!-- ════════ source_hash inputs (D3 · Matthias 항목5) ════════
     계산법: project-context-kr.md §12  ·  파일 17종
     재현:  아래 목록을 sorted() 하고 각 파일에 f"{path}\n{sha256_hex}\n" 를 이어붙여
            그 바이트열의 SHA-256 앞 16자리를 취한다. 없는 파일은 "MISSING".

     .agent-team/00-plan/charter.md
     .agent-team/00-plan/task-graph.md
     .agent-team/03-service-planning/core-features.md
     .agent-team/03-service-planning/user-stories.md
     .agent-team/04-architecture/adr/ADR-0010-vacuous-pass.md
     .agent-team/04-architecture/api-contracts.md
     .agent-team/04-architecture/build-plan.md
     .agent-team/04-architecture/code-structure.md
     .agent-team/04-architecture/data-quality-design.md
     .agent-team/04-architecture/design-patterns.md
     .agent-team/04-architecture/exceptions.md
     .agent-team/04-architecture/schemas/data_quality_report.schema.json
     AGENTS.md
     docs/GIT_WORKFLOW.md
     src/AGENTS.md
     src/measurement/schema.py
     src/measurement/sink.py

     → source_hash = 85e5519b725c4840
     ════════════════════════════════════════════════════ -->
