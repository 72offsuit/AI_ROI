---
story_key: D-02
epic: GA형 관측 대시보드 (charter §3.1③)
issue: "(이슈 없음 — charter ③ 직접)"
title: 관측 화면군 — 컴포넌트 8종 + 화면 8개 · USP-1 증명
status: done            # W5-C Andrew 2026-09-11 — AC-1~AC-13 전부 충족. AC-12 는 리드의 L1 승격(사용자 승인) 후 Playwright ^1.63.0 으로 닫았다. 상세: .agent-team/08-impl-notes/frontend.md
owner: Andrew (W5-C)
phase: "—"
blocked_by: ["d-01"]
blocks: []
user_decisions_required: []
source_hash: edb8e795ec6bf1c4
source_files: 27
---

# D-02 · 관측 화면군 (W5-C)

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
| **대상** | charter §3.1③ — 소유 이슈 없음 |
| **담당** | Andrew · W5-C |
| **선행** | **d-01** (앱 골격 · 읽기 계층 · 토큰) |
| **실제 게시물** | **M-06 이후.** 그 전까지 `.agent-team/04-architecture/examples/` 픽스처 2벌 |
| **커밋 type** | `feat` |

> ## ★★ 이 화면이 증명하는 것
> **USP-1 — "계산 불가를 계산 불가로 말하는 측정 계층"이 C1 에서 **전부** 증명할 유일한 USP 이고, 증명 수단은 화면이다.**
>
> **한 줄 요약:** **값이 없다는 사실을 값이 있는 것과 같은 크기로 쓴다.**
> 결손을 0 으로 채우지 않는 것은 절반이다. **나머지 절반은 결손을 작고 흐리게 만들어 시선에서 치우지 않는 것이다.**
> **0 으로 채우는 것과 회색으로 흐리는 것은 같은 실패다.**
> `[Source: .agent-team/07-design/missing-state-spec.md#0]`

---

# 2. 스토리

> **`P-팀`으로서 나는 대시보드를 열자마자 이벤트가 제대로 쌓이고 있는지 알고 싶다.**
> 왜냐하면 우리가 알아야 할 것은 모델 성능이 아니라 **계약 위반과 결손**이기 때문이다. `[Source: .agent-team/03-service-planning/user-stories.md#US-11]`

> **`P-리드`로서 나는 어떤 숫자가 커머스 실측이고 어떤 것이 시뮬레이터 생성인지 화면에서 알고 싶다.** `[Source: .agent-team/03-service-planning/user-stories.md#US-12]`

> **`P-팀`으로서 나는 계산할 수 없는 지표가 0 으로 표시되지 않기를 원한다.**
> 왜냐하면 **이것이 이 프로젝트가 증명하려는 것 자체**이기 때문이다. `[Source: .agent-team/03-service-planning/user-stories.md#US-13]`

> **`P-리드`로서 나는 화면의 숫자가 어느 스키마·어느 커밋·어느 config 에서 나왔는지 알고 싶다.** `[Source: .agent-team/03-service-planning/user-stories.md#US-14]`

---

# 3. 인수 조건 (AC)

## AC-1 · 화면 8개

- [ ] `/` 인덱스 — **`index.json` 하나만** 읽는다
- [ ] `/ingestion` V1 · `/rejections` V2 · `/coverage` V3 · `/kpi` V4 · `/quality` V5 · `/freeze` V6
- [ ] `/triggers` — **정적. 게시물 없음.** 계획된 부재 표
- [ ] **한 화면이 한 게시물만 읽는다.** 예외는 `/` 와 `/triggers`

## AC-2 · 컴포넌트 8종

- [ ] `MetricCell` · `StateChip` · `SourceColumns` · `VerdictBanner` · `ImpactChain` · `CoverageTable` · `IngestionTimeline` · `NoticeBar`
- [ ] **`MetricCell` 부터 만든다** — 모든 숫자가 이것을 거치고 자기 검사 3건이 여기 있다

## AC-3 · ★ 0 채우기 0건 (USP-1)

- [ ] **계산 불가 셀에 문자 `0` 이 없다** (C-1)
- [ ] `?? 0` · `|| 0` · `Number(value)` · `parseFloat(v) || 0` · `counts[k] || 0` 이 **지표 값 경로에 0건**
- [ ] **`—` 의 font-size 가 같은 카드의 값과 같다** (C-2 · 규칙 V-1)
- [ ] `—` 에 `text-muted` 를 쓰지 않는다. **`text-secondary`**
- [ ] `filter(d => d.value > 0)` 가 **0건**

## AC-4 · ★ 결손을 숨기지 않는다 (V-0)

- [ ] **16종 `event_type` 전부 렌더** (C-6)
- [ ] **22개 필드 전부 렌더**
- [ ] **Lock 9종 전부 렌더**
- [ ] **47종 지표 전부 렌더** — 계산 불가 19개도
- [ ] accordion · "더 보기" · `<details>` 기본 닫힘이 **결손 항목에 없다**
- [ ] 기본 필터가 `status === 'ok'` 가 **아니다**
- [ ] 정렬 기본값이 **고정 순서**다 (건수 내림차순 아님). **예외: V3 은 충족률 오름차순**
- [ ] 빈 커머스 열을 **접거나 축소하지 않는다**
- [ ] **이벤트 0건을 빈 상태 일러스트로 대체하지 않는다**

## AC-5 · ★ 사유 상시 표시 (V-9)

- [ ] 사유 코드 · `reason_detail` · 기준 · 영향 · 조치가 **전부 상시 표시** (C-4)
- [ ] **호버·툴팁·접기로만 제공하지 않는다** — 호버 상태는 스크린샷에 남지 않는다
- [ ] `gap`·`env_blocked`·`not_run`·`violation` 에 **조치 줄이 있다** (C-5). 없으면 **`조치 미정` 이라고 쓴다**

## AC-6 · 상태 8종 · 글리프

- [ ] 시각 상태가 **`(status, reason_code)` 의 순수 매핑**이다 (C-17 · `DB-012`)
- [ ] **모든 글리프에 `aria-label`** (C-11)
- [ ] `gap`·`env_blocked`·`provisional` 이 **값 슬롯 + 선 종류 + 글리프 3중**으로 갈린다
- [ ] `not_run` 의 값 슬롯이 **`—` 가 아니라 글자 `미실행`** — `—` 는 "없음", `미실행` 은 "모름"

## AC-7 · ★ 규칙 V-12 공허한 통과

- [ ] ★ **`status === "vacuous"` 를 `unconnected`(info)로 그린다** (C-13) — `pass ∧ examined_rows==0` 은 **스키마가 금지해 일어나지 않는다**
- [ ] **`공허한 통과 · 검사 대상 0행`** + `scope` 인라인
- [ ] **`vacuous` 의 `reason_code` 로 분기하지 않는다** — `status` 로만 (§4.2 ⚠)
- [ ] **`✓` 도 초록도 쓰지 않는다**
- [ ] **`gate_result: "incomplete"` 에 `success` 토큰을 일절 쓰지 않고 "통과"를 단독으로 쓰지 않는다** (C-14)

## AC-8 · 출처 구분

- [ ] 계층 1·2 는 **항상 출처 2열** — 왼쪽 커머스 `◼ 실측` / 오른쪽 시뮬레이터 `◇ 생성`
- [ ] **순서 불변** — 정렬·필터·적층에서 바뀌지 않는다 (C-12)
- [ ] **출처를 색이 아니라 위치로** 구분한다
- [ ] 합산 표시 시 **제목에 `· 합산` + `합산` 칩**
- [ ] **대시보드가 출처를 재분류하지 않는다**
- [ ] 출처 파생 근거 각주 — *"출처는 `simulator_version` · `random_seed` 의 null 여부에서 파생됩니다 (별도 플래그 없음)"*

## AC-9 · 증감 금지 (V-11)

- [ ] `↑`·`↓`·`+12%`·스파크라인이 **0건** (C-7)
- [ ] **슬롯도 두지 않는다** — 빈 증감 슬롯은 "변화 없음(0%)"으로 읽힌다

## AC-10 · 보안

- [ ] **V2 거부 샘플에 값이 렌더링되지 않는다** (C-15) — `offending_fields`(이름만)

## AC-11 · `notices`

- [ ] **`notices[]` 가 전부 렌더링되고 접히지 않는다** (C-16 · 계약 R-8)
- [ ] 토스트·모달을 쓰지 않는다
- [ ] `code` 원문과 `reference` 를 함께 쓴다
- [ ] **개수 0건이면 컴포넌트를 렌더하지 않는다.** *"가정 없음"이라고 쓰지 않는다**

## AC-12 · ★ USP-1 대표 장면 (리드 판정 J-1)

- [ ] `/kpi` **최상단에 고정**
- [ ] `revenue` 는 **값**, `contribution_profit` 은 **`계산 불가 · 원가 근거 없음`** 이 같은 카드·같은 행·같은 폭
- [ ] 불변식 **U-1 ~ U-10** 전부 (§4.7)
- [ ] ★ **fixture 가 실제 파이프라인 산출물이다** — 손으로 쓴 JSON 이 아니다
- [ ] ★ **`표본 데이터 — 실측이 아닙니다` 배지** — **타협 불가**
- [ ] **스크린샷으로 증명한다** — ★ **수단이 정해져 있지 않다.** T6 에서 ⑴수동/⑵자동화/⑶`BLOCKED` 를 먼저 고른다 (Matthias N-4)

## AC-13 · 회귀 없음

- [ ] `python3 -m unittest discover -s tests` — 회귀 0
- [ ] `python3 -m unittest tests.test_isolation -v` — 통과
- [ ] `python3 .agent-team/04-architecture/tools/check_ownership.py` — PASS
- [ ] `npm run tokens:check` · `npm run tokens:test` 통과
- [ ] ★ **빈 Sink 픽스처로 렌더 시 예외 없이 전부 계산 불가** (C-9)

---

# 4. 개발 컨텍스트 (`developer_context`)

## 4.1 ★★ 가장 위험한 한 줄 — 다시 적는다

**계약은 `status != "ok"` 이면 `value` 를 항상 `null` 로 준다.** 그 `null` 을 JS 관용구가 조용히 0 으로 바꾼다.

```ts
value ?? 0 · value || 0 · Number(value) · (value ?? 0).toLocaleString()
value?.toLocaleString() ?? '0' · counts[name] || 0 · parseFloat(value) || 0 · value.toFixed(1)
```

> **`(null).toLocaleString()` 이 예외를 던지므로 구현자는 예외를 막으려고 `?? 0` 을 쓴다. 그 한 줄에서 USP-1 이 끝난다.**
> **예외를 막는 올바른 방법은 분기지 기본값이 아니다.**

```ts
const EM_DASH = '—';                       // U+2014. hyphen(-) 아니다
const display = m.status === 'ok' ? m.value_formatted : EM_DASH;
```

> ### ★★ `value_formatted` 는 **오늘 계약에 없다** — M-06 이 추가한다 (Thomas C-1)
> 실측: `common.schema.json` `$defs.metric_value` 는 **11종** 프로퍼티에 `additionalProperties: false` 이고 **`value_formatted` 가 없다.** 픽스처 14파일 grep **0건**.
> **지금 그대로 쓰면 모든 `ok` 지표가 `undefined` 다.** 그러면 구현자는 `m.value.toLocaleString()` 로 가고, `null` 예외를 막으려 **`?? 0`** 을 쓴다 — **이 절이 경고한 바로 그 경로를 이 절이 연다.**
>
> **→ M-06 §4.16 이 계약에 추가한다** (`ok`·`unconfirmed` 필수 / 계산 불가 금지 — `basis` 와 같은 패턴).

> #### ★ 누가 포맷하는지 정해졌다 — **`contracts.py` 직렬화 시점** (리드 판정 2026-09-11)
> **화면도, 계산층(`kpi.py`·`economics.py`)도 아니다.** 게시물을 직렬화하는 한 자리에서 `unit` + `value` 로 만든다.
> **`unit` 별 규칙 8종이 M-06 §4.16.1 에 정본으로 있다:**
>
> | `unit` | 예 | | `unit` | 예 |
> |---|---|---|---|---|
> | `krw` | `38,400원` | | `ratio` | `18.3%` **(×100 을 화면이 다시 하지 않는다)** |
> | `krw_per_customer` | `2,130원/인` | | `percentage_point` | `+3.2%p` **(부호 유지)** |
> | `count` | `1,204건` | | `days` | `42일` |
> | `text` | 그대로 | | `datetime` | `2026-09-18 13:58` (KST) |
>
> **→ 화면은 이 문자열을 그대로 출력한다.** `toLocaleString()` 을 부르지 않는다 — 환경마다 결과가 달라 재현성이 깨진다.
> **`한계` 칩은 `limit_note`(선택 필드 · M-06 §4.17)를 읽는다.** C1 에서 실제로 채워지는 지표는 **`campaign_response_count` 하나**다 (M-04 AC-4b).
> **M-06 전에는 숫자를 그리지 말고 `계약 준비 중` 으로 두거나 M-06 을 기다린다.**
> ★ **`m.value` 를 직접 포맷하지 않는다.** 통화·소수·천단위 결정은 계산이고(`DB-012`) 그 순간 `?? 0` 이 따라온다.

**`status` 로 분기한다. `value` 의 falsy 여부로 분기하지 않는다.**
**`value === 0` 은 정직한 값이다. `0` 과 `null` 을 같은 조건으로 묶는 모든 코드가 버그다.**

### 차트 함정

| 함정 | 결과 |
|---|---|
| 데이터 배열에 `null` → 라이브러리가 **0 으로 플로팅**하거나 **선을 이어버린다** | 없는 값을 만든다 (V-5 위반) |
| `filter(d => d.value > 0)` | **0건 항목이 조용히 사라진다** (V-0 위반) |
| `partitions` 에서 `present: false` 행을 빼고 넘긴다 | **수집 공백이 화면에서 사라진다** |

**올바른 형태:** 0건 날짜는 **막대를 그리지 않고** 1px 점선 윤곽 빈 슬롯 + baseline 틱.
**선 차트를 쓰지 않는다** — 결손 구간에서 이으면 없는 값을 만들고, 끊으려면 라이브러리와 싸워야 한다. **막대를 택한 이유가 이것이다.**

`[Source: .agent-team/07-design/dashboard-agents-design-constraints.md#1]`

## 4.2 ★ 상태 8종 — `(status, reason_code)` 에서 **기계적으로 파생**된다

**화면이 새로 판정하지 않는다. 순수 매핑이다** (`DB-012`).

| 계약 `status` | `reason_code` | 시각 상태 | 글리프 | 값 슬롯 | 색 · 형태 |
|---|---|---|---|---|---|
| `ok` | — | `measured` | 없음 | **숫자** | `text` · **기준 문구 필수** |
| `unconfirmed` | `PARAM_UNCONFIRMED` | `provisional` | **◐** | **숫자** | `warning` · **실선 윤곽** + `params_used` 표시 |
| `unavailable` | `NEEDS_TWO_STRATEGIES` · `NEEDS_MODEL_OUTPUT` · `PRECONDITION_MISSING` | `planned` | **·** | `—` | `text-muted` / `surface-muted` **채움** |
| `unavailable` | `NO_SOURCE_EVENT` | `unconnected` | **○** | `—` | `info` / `info-surface` **채움** |
| `unavailable` | `NO_COST_BASIS` · `MISSING_FIELD` | **`gap`** | **⚠** | `—` | `warning` / `warning-surface` **채움** |
| `blocked` | `BLOCKED` | **`env_blocked`** | **⊘** | `—` | `warning` · **점선 윤곽** |
| `not_run` | `NOT_RUN` | `not_run` | **?** | **글자 `미실행`** | `error` · 실선 윤곽 |
| (화면 자기 검사) | — | `violation` | **✕** | 숫자 또는 `—` | `error` / `error-surface` 채움 |

`[Source: .agent-team/07-design/contract-reconciliation.md#3-③]`

### ★★ 위 표는 `metric_value` 전용이다 — **검사 상태는 별도 축이다** (Matthias CR-1)

**`data_quality_report.checks[].status` 는 `metric_value.status` 와 다른 enum 이다.** 위 표에 키가 없어 **V5 의 행이 정의되지 않은 default 로 떨어진다.**

| 계약 `checks[].status` | 시각 상태 | 글리프 | 값 슬롯 | 색 · 형태 |
|---|---|---|---|---|
| `pass` | `ok` | **✓** | `통과` | `success` / `success-surface` 채움 |
| `fail` | `violation` | **✕** | `실패 N건` | `error` / `error-surface` 채움 |
| **`vacuous`** | **`unconnected`** | **○** | **`공허한 통과`** | `info` / `info-surface` 채움. ★ **`✓` 도 초록도 쓰지 않는다** |
| `not_run` | `not_run` | **?** | **글자 `미실행`** | `error` · 실선 윤곽 |
| `blocked` | `env_blocked` | **⊘** | `—` | `warning` · 점선 윤곽 |

> ### ★ `pass ∧ examined_rows == 0` 은 **일어날 수 없다.** 조건을 `vacuous` 로 쓴다
> `ADR-0010` 이 이미 **스키마로 금지**했다 — 실측: `data_quality_report.schema.json` `checks.items.allOf[1]` = `examined_rows == 0 → status 가 pass 일 수 없다`.
> **그 조합을 조건으로 쓰는 화면 코드는 영원히 실행되지 않는다.**
>
> **`empty-sink` 실측: 18행 중 7행이 `status: "vacuous"`**(DQ-01·02b·04·07·08·10·11) · **`pass ∧ examined_rows==0` 은 0건.**
> **→ 조건을 `status === "vacuous"` 로 쓴다.** `examined_rows` 를 함께 읽어 판정하지 않는다 — **게시물이 이미 판정했다.**
>
> **`vacuous` 는 오늘 이 저장소의 정상 상태다.** **실패로 그려도 통과로 그려도 안 된다.**

> ⚠ **`vacuous` 의 `reason_code` 는 신뢰하지 않는다.** 픽스처 7건이 전부 `NOT_RUN` 인데 **"실행했는데 0행"과 "실행 안 함"이 한 행에 섞인 것**이다(Matthias 항목2).
> **M-07 이 계약에서 `vacuous` → `reason_code` 금지·`reason_detail` 필수로 고친다.** 화면은 **`status` 로만 분기하고 `reason_detail` 을 문구로 쓴다.**

### 왜 5종으로 나누나 — 제1원리

**"계산 불가" 한 상태로는 틀린다.** 47종 중 19종이 계산 불가이고, 오늘은 거의 전부가 계산 불가다.
**화면의 80% 가 같은 회색이면 읽는 사람은 전체를 배경으로 인식한다. 경고가 80% 이면 경고가 아니다.**

**7종 사유 코드는 심각도가 아니라 행위 주체로 갈린다:**

| 사유 코드 | 지금 문제인가 |
|---|---|
| `NEEDS_TWO_STRATEGIES` · `NEEDS_MODEL_OUTPUT` | **아니다 — 계획대로다** |
| `NO_SOURCE_EVENT` | **아니다 — 아직 연결 전이다** |
| `NO_COST_BASIS` · `MISSING_FIELD` | **그렇다 — 구조적 결손** |
| `BLOCKED` | **그렇다 — 해소 가능** |
| `PARAM_UNCONFIRMED` | **부분 — 값을 쓸 수 있다** |

**앞의 셋과 뒤의 셋은 읽는 사람이 해야 할 행동이 정반대다.** 앞은 "넘어가라", 뒤는 "멈추고 보라".
**같은 시각 상태를 주면 둘 중 하나는 반드시 오독되고, 실제로 오독되는 쪽은 수가 적은 쪽(조치 필요)이다.**

> **이 분해는 "0 으로 채우지 않는다"를 약화시키지 않는다. 다섯 상태 전부 값 슬롯에 숫자를 쓰지 않는다. 바뀌는 것은 주목도의 배분뿐이다.**
> `[Source: .agent-team/07-design/missing-state-spec.md#1]`

### `gap`·`env_blocked`·`provisional` 이 같은 `warning` 색인 것을 어떻게 가르나

| | 값 슬롯 | 선 | 글리프 |
|---|---|---|---|
| `gap` | `—` | **채움** (배경) | **⚠** |
| `env_blocked` | `—` | **점선 윤곽** | **⊘** |
| `provisional` | **숫자** | **실선 윤곽** | **◐** |

> **글리프를 빼면 흑백 인쇄·스크린샷 축소에서 `gap`/`env_blocked` 가 구분되지 않는다.**
> `Plan/DESIGN.md` 가 *"색상만으로 의미를 전달하지 않습니다"* 를 금지한다.

### `not_run` 이 왜 `blocked` 보다 강한가

`BLOCKED` 는 **AGENTS.md 가 승인한 보고 형식**이고 `미실행` 은 **아무도 선언하지 않은 공백**이다.
**전자는 목록에 남아 추적되지만 후자는 목록에서 사라진다. 알지 못함이 결손보다 나쁘다.**

## 4.3 ★ 어기기 쉬운 시각 규칙 — 전부 **"좋은 디자인처럼 느껴지는"** 것들

| # | 규칙 | 왜 어기고 싶어지나 |
|---|---|---|
| **V-1** | **`—` 를 작게·흐리게 만들지 않는다** | *"화면이 시끄럽다 / 결손은 부차적이니 작게"* — **가장 자주 깨질 규칙** |
| **V-0** | **결손을 숨기지·접지·기본 필터하지 않는다** | *"계산 불가 19행은 너무 길다 / 기본으로 접고 토글을"* — **UX 개선처럼 보이기 때문에 가장 위험하다** |
| — | **상태 글리프를 생략하지 않는다** | *"색으로 충분하다 / 아이콘이 번잡하다"* |
| **V-2·V-3** | **기준(basis)을 생략하지 않는다** | *"카드가 길어진다"* — 그런데 **기준이 "측정됨"의 유일한 증거다** |
| **V-9** | **사유를 호버·툴팁에 숨기지 않는다** | *"인라인이 지저분하다"* — 그런데 **호버 상태는 스크린샷에 남지 않는다** |
| **V-11** | **증감·델타·스파크라인을 만들지 않는다** | *"대시보드엔 전기 대비 증감이 있어야"* — 그런데 **비교 기준이 없다** |
| **R-7** | **"전체" 히어로 지표를 만들지 않는다** | *"대시보드라면 큰 숫자가 하나 있어야"* — 그런데 **계층 1·2 에 `combined` 가 스키마 수준에서 금지**다 |

**`—` 의 사양:** 대체한 값과 **같은 타이포그래피 토큰·같은 크기·같은 자리.** 값이 `text-metric`(2rem/700)이면 `—` 도 그렇다. 표에서는 `text-table-number` + **우측 정렬 유지.** 색은 **`text-secondary`**(#525252, 흰 배경 **7.82:1**).
**`text-muted` 를 쓰지 않는 이유:** ⑴ 흰 배경 5.33:1 로 뚜렷하게 약하고 ⑵ `Plan/DESIGN.md` 가 `text-muted` 를 *"보조 배지, 날짜 등 부가 정보"* 로 한정했다 — **결손은 부가 정보가 아니다.**

> **2rem 굵은 em dash 는 시각적으로 무겁고, 무거워야 한다.**
> `[Source: .agent-team/07-design/missing-state-spec.md#3.2]`

## 4.4 ★ 규칙 V-2 — 측정된 0 은 **근거를 같이 쓴다**

`—` 와 `0` 을 다르게 그리는 것만으로는 부족하다. **읽는 사람 입장에서 화면의 `0` 이 믿을 수 있는 0 인지 알 방법이 없다.**

```
revenue                          coupon_cost
38,400원                          0원
기준: 주문 1건                    기준: coupon_use 1,204건 중 0건
```

**`0원` + `기준: …1,204건 중 0건` 은 "세어봤고 0이었다"의 증거다. `—` 는 정의상 기준을 가질 수 없다.**
**따라서 기준의 유무가 "측정됨"의 판별자가 되고, 0 과 계산 불가의 구분이 글리프 하나에 걸리지 않는다.**

**계약이 이것을 구조로 만들었다:**
```
status 가 ok · unconfirmed             → basis 필수
status 가 unavailable/blocked/not_run → basis 금지   (not: {required: ["basis"]})
```

### 규칙 V-3 — **기준 없는 값은 우리 쪽 계약 위반으로 표시한다**

```
average_order_value
12,900원                ✕ 계약 위반
기준 미표기 — 분모를 확인할 수 없습니다
```

**대시보드가 자기 입력을 검사한다. 0 을 채운 주체가 측정 계층이어도 화면에서 드러난다.**

> **`DB-012` 위반이 아니다** — 화면은 지표를 **계산하지 않는다.** **필수 필드의 존재 여부만** 본다. 판정이 아니라 계약 검사다. 계약 R-10 이 이것을 명시했다.

### 규칙 V-4 — 분모가 0 인 비율에 `0%` 를 쓰지 않는다

`rejection_rate = events_rejected / (events_ingested + events_rejected)`. **C1 초기에 분모가 0이다. `0/0` 은 0% 가 아니다.**
→ `—` + `unconnected` + 기준 `분모 0건`. **계약이 `denominator == 0 → ok 불가` 를 스키마로 거부한다.**

### 규칙 V-6 — 수집 0건인 날짜를 "활동 없음"이라고 **단정하지 않는다**

```
2025-10-03   수집 0건
             활동 없음과 수집 중단을 현재 데이터로 구분할 수 없습니다
```

> **"활동 없음"이라고 쓰지 않는다. 관측하지 않은 것을 단정하는 것이고 0 채우기와 같은 종류의 잘못이다.**
> 게시물이 `totals.ingestion_gap_attribution` 을 `not_run` + `PRECONDITION_MISSING` 으로 준다. **화면은 그것을 그대로 쓴다.**

### 규칙 V-7 — 정밀도 한계가 기록된 지표는 값 옆에 **`한계` 칩**

`campaign_response_count` — 값은 나오나 **쿠폰 비종속 캠페인이 측정되지 않는다.**
**`provisional` 과 다르다:** `provisional` 은 파라미터가 확정되면 값이 맞아지고, **`한계` 는 이벤트가 추가되지 않으면 영원히 과소계상이다.**

### 규칙 V-10 — 첫 화면 상단에 **현재 사이클의 기대 상태**를 한 줄로

```
○ C1 관측 사이클 — 계산 불가 지표가 많은 것이 정상입니다.
  커머스 이벤트 0건(Ecommerce #28 미착수) · 시뮬레이터 미구현 · 결과 화면군은 이후 사이클입니다.
```

**`info` 계열. 경고색을 쓰지 않는다** — 정상 상태를 경고로 표시하면 실제 경고가 묻힌다.

## 4.5 컴포넌트 8종

**`MetricCell` 부터 만든다.** 모든 숫자가 이것을 거치고 자기 검사 3건이 여기 있다.

### C-1 `MetricCell` — 4슬롯 고정

```
┌──────────────────────────────────────────┐
│ ① 지표명          text-label-md          │
│ ② 값 슬롯         text-metric / -table-number   ← 숫자 또는 —
│ ③ 상태 슬롯       칩 + 사유 + 사유 코드   ← 상시 표시 (V-9)
│ ④ 근거 슬롯       기준 / 영향 / 조치      text-caption
└──────────────────────────────────────────┘
```

**입력 계약** — ★ **`value` 를 문자열로 받는다:**

> **`DB-012` 다.** 숫자를 받으면 화면이 통화·소수·천단위·단위를 결정하게 되고 그것은 **표시 규칙의 계산**이다.
> `Plan/DESIGN.md` 도 *"소수 자릿수·반올림·할인 계산은 도메인 규칙으로 정하고 **디자인에서 새로 계산하지 않는다**"*.
> **게시물이 `"38,400원"` 을 준다.**

**★ 자기 검사 3건 (V-3):**

| 조건 | 렌더 |
|---|---|
| `state='available'` 이고 `basis` 가 없다 | 값 + `✕ 계약 위반` + `기준 미표기 — 분모를 확인할 수 없습니다` |
| `state ∈ {gap, env_blocked, not_run, violation}` 이고 `action` 이 없다 | `조치 미정` (**빈칸으로 두지 않는다**, V-8) |
| ★ `state ≠ 'available'` 인데 `value` 에 숫자가 들어왔다 | **`—` 로 렌더 + `✕ 계약 위반 · 계산 불가 상태에 값이 왔습니다`** |

> **셋째 행이 0 채우기를 잡는 최종 방어선이다.** 측정 계층이 `unavailable` 과 `value: '0'` 을 같이 보내면 **화면이 거부한다.**

### C-2 `StateChip`

형태: `--obs-chip-radius`(= `rounded.full`) · `text-caption` · 아이콘 16px(밀도 높은 표) / 20px(카드).

**보조 칩 — 상태 칩과 같이 쓸 수 있다:**

| 칩 | 문구 | 언제 |
|---|---|---|
| `유도값` | `유도값` | `derived: true` — 저장된 사실이 아니라 규칙 유도 |
| `한계` | `한계 · <내용>` | V-7 |
| `합산` | `· 합산` | 출처 합산. **이름에도 붙인다** |
| **`표본 데이터`** | **`표본 데이터 — 실측이 아닙니다`** | fixture 렌더. ★ **타협 불가** |
| **`공허한 통과`** | **`공허한 통과 · 검사 대상 0행`** | **`status === "vacuous"`.** `✓` 도 초록도 쓰지 않는다 |

### C-3 `SourceColumns`

| 규칙 | 내용 |
|---|---|
| **S-1 순서 불변** | 왼쪽 커머스 / 오른쪽 시뮬레이터. **세로 적층 시 커머스 위.** 정렬·필터로 바뀌지 않는다 |
| **S-2 배지** | `◼ 실측` / `◇ 생성` — 글리프 + 문구, **배경 없음** (출처는 상태가 아니다) |
| **S-6 접기 금지** | **빈 열도 전폭 유지.** 빈 커머스 열이 보여야 프로젝트 실제 상태가 보인다. 접으면 "시뮬레이터만 있는 시스템"처럼 보인다 |
| 폭 | **1:1 고정.** 건수에 따라 폭을 바꾸지 않는다 |
| 적층 | 1024px 미만 세로 |
| 각주 | 출처 파생 근거 한 줄 (US-12 인수조건 3) |

**★ `ConnectionState` — 계약이 2값이다. `stale` 을 만들지 않는다 (결정 D-29):**

| `link_state` | 칩 | 같이 쓰는 사실 |
|---|---|---|
| `never_connected` | `unconnected` ○ **`아직 관측되지 않음`** | `첫 수신 —` · `마지막 수신 —` |
| `connected` | **칩 없음** (상태가 아니라 사실이다) | **`마지막 수신 2026-09-18 13:58 KST`** · `첫 수신 …` · `건수 …` |

> ★ **`connected` 에 `✓ 수신 중`(success)을 붙이지 않는다.**
> `connected` 는 **"지금 수신 중"과 "예전에 받았고 끊겼다"를 모두 포함한다. 2값으로는 그 판정을 할 수 없다.**
> `✓` 를 붙이면 "건강하다"로 읽히고 `⚠` 를 붙이면 "멈췄다"로 읽힌다 — **둘 다 화면이 알 수 없다.**
> **오래됐는지는 사람이 본다.** `sources[s].staleness` 가 `not_run` + `PARAM_UNCONFIRMED` 로 온다 — **판정할 수 없다는 사실 자체가 값이다.**
> `[Source: .agent-team/07-design/contract-reconciliation.md#2.4]`

### C-4 `VerdictBanner`

| 규칙 | 내용 |
|---|---|
| **F-1 정확히 하나** | 여러 개를 쌓으면 판정이 아니라 목록이 된다 |
| **F-2 "정상" 조건** | 순위 1~6 이 전부 비어 있을 때만 |
| **F-3 0건은 경고가 아니다** | `수집된 이벤트 0건` 은 `unconnected`(info). **`error`·`warning` 금지** |
| 근거 수치 | 문구에 **건수와 대상**을 포함. `문제가 있습니다` 같은 내용 없는 문구 금지 |
| **집계 주체** | ★ **게시물이 집계해 준다** (`index.verdict`). **화면이 세면 `DB-012` 위반 — 단순 합산도 계산이다** |

**`headline_code` → 문구 매핑을 화면이 한다.** 코드는 게시물이 준다.

### C-5 `ImpactChain`

```
⚠ unit_cost 미수신                              조치: Ecommerce #24
  → cogs · contribution_profit                  계산 불가
  → incremental_contribution_profit  [P1]       성립 불가
```

| 규칙 | 내용 |
|---|---|
| **2홉 제한** | 초과분은 `→ …` + 화면 링크. 3홉 이상은 읽히지 않는다 |
| **`[P1]`·`[G1]` 배지** | `metrics[].role` 이 `primary`/`guardrail` 이면 필수. ★ **이 배지가 존재 이유다** |
| 정렬 | Primary·Guardrail 먼저 → `gap` → `unconnected` → `planned` |
| 양방향 | V3 은 결손→영향, V4 는 영향←결손. **같은 데이터의 두 방향** |
| 데이터 | ★ **게시물의 `blocks_metrics`·`blocked_by` 를 쓴다. 화면이 추론하면 `DB-012` 위반** |

### C-6 `CoverageTable` · C-7 `IngestionTimeline` · C-8 `NoticeBar`

| 컴포넌트 | 핵심 규칙 |
|---|---|
| `CoverageTable` | 텍스트 좌 · 수치 우(`tnum`) · 행 높이 44px · 좁아지면 **해당 영역만** 가로 스크롤 · **열 숨김 금지** · **0건 행·결손 행을 남긴다** · **정렬 기본값은 고정 순서** |
| `IngestionTimeline` | **막대.** 선 차트 금지 · 출처별 **두 줄** 분리 · 단일 계열 색 `--obs-chart-series` · y축 0 시작 · **0건 날짜는 막대 없음 + 1px 점선 윤곽 빈 슬롯** · 축 레이블·데이터 표 병행 · **증감 없음** |
| `NoticeBar` | 판정 배너 **아래** · **접지 않는다** · `code` 원문 + `reference` · **토스트·모달 금지** · **0건이면 렌더하지 않는다** (*"가정 없음"이라고 쓰지 않는다*) |

**C1 에서 `NoticeBar` 에 항상 보이는 것:** `SINK_EMPTY`(limitation) · `REFUND_NOT_ADJUSTED`(assumption) · `CHURN_THRESHOLD_UNCONFIRMED`(assumption) · `GATE1_NOT_PASSED`(limitation).

`[Source: .agent-team/07-design/design-system/components.md]`

## 4.6 화면 8개 — 무엇을 그리나

### `/` 인덱스 — **`index.json` 하나만**

```
① 제목  →  ② 게시물 신원(provenance)  →  ③ 판정 배너(verdict)  →  ④ 사이클 고지(V-10)
→  ⑤ notices[]  →  ⑥ 화면 6개 진입 카드(views + artifacts[].status)  →  ⑦ 결손→영향  →  ⑧ 수동 새로고침
```

**`run_id` 불일치 시:** ③이 `violation` 으로 바뀌고 *"게시가 진행 중이거나 불일치"*. **6개 화면으로 들어가지 않게 막는다.**
**`index.json` 부재 시:** ⑥⑦을 그리지 않고 빈 상태 안내 하나만 (d-01 §4.7 확정 문구).

### V1 `/ingestion`

- 출처 2열 블록 + `ConnectionState`
- 수집 타임라인 — **출처별 두 줄** · 0건 날짜 빈 슬롯 + V-6 문구
- **`event_type` 16종 매트릭스 — 표. 항상 16행.** 정렬은 이름 고정 순서
- `event_type_coverage` 는 **분모가 16 고정**이므로 0건이어도 **`0 / 16`**(측정된 0). `—` 가 아니다
- 거부 요약 → `/rejections`
- 각주 — 출처 파생 근거

### V2 `/rejections`

- 요약 · 사유별 표 · **사유당 대표 샘플 최대 3건**
- ★ **`offending_fields`(필드 이름만). 값을 일절 렌더링하지 않는다**
- 거부 0건일 때 — **`0건` + 기준 `시도 N건 중 0건`.** 측정된 0이다
- 시도 0건일 때 — `—` + `unconnected` + `기준: 수집 시도 없음`

### V3 `/coverage`

- **22개 필드 전부** · 열: 필드 · 충족률 · **분모** · ◼ 커머스 · ◇ 시뮬레이터 · 상태 · **영향**
- **분모 필수** — `0% (0 / 1,204)` 형태
- 분모 0 → `—` + `기준: 적용 대상 0건` (V-4)
- 정렬: **충족률 오름차순** (결손이 위) ← V-0 의 유일한 예외
- ★ **`schema_gaps[]` 를 행으로 남긴다** — `unit_cost`·`discount`·`shipping_fee`·`refund` 4건. **표에 없으면 영원히 안 보인다**

### V4 `/kpi` ★ USP-1 대표 장면

- **최상단에 대표 장면 카드 고정** (§4.7)
- **47종 전부 렌더.** 계층별 접기 금지
- 계층 머리에 `가능 / 조건부 / 불가` 집계 — **게시물이 집계해 준다**
- 계층 1·2 는 **출처 2열.** 계층 0·실험 판정은 출처 축 없음
- 실험 판정 15종은 **한 블록으로 묶어 블록 머리에 사유를 한 번 쓰되 15행을 그대로 펼친다** — 행을 접는 것이 아니라 **문구를 모으는** 것
- `provisional` 에 **`params_used` 표시**
- `derived: true` → `유도값` 칩 · `campaign_response_count` → `한계` 칩

### V5 `/quality`

- `gate_result` **3값** — `incomplete` 는 **`gap`(warning)** · 문구 **`미완 · 통과 N / 미실행 M / 차단 K`**
- ★ **`incomplete` 에 `success` 토큰을 일절 쓰지 않고 "통과"를 단독으로 쓰지 않는다**
- 검사 행 **5상태** — `pass`/`fail`/**`vacuous`**/`not_run`/`blocked`
- ★ **V-12** — **`status === "vacuous"`** → `unconnected`(info) + **`공허한 통과 · 검사 대상 0행`.** `✓`·초록 금지. **`empty-sink` 는 18행 중 7행이 이 상태다**
- **각 검사에 `scope` 인라인**
- **`spec_coverage` 를 그린다** — `unmapped_spec_items` 가 비어 있지 않으면 **그 사실을 표시한다**
- **게시물이 주는 검사만 그린다** — 정본 목록을 화면 상수로 들지 않는다 (게시물이 18건 전부 준다)
> ### ★★ `commerce-connected` 픽스처는 **검사 7종만 담고 있고 이것은 결함이다** (리드 지시)
>
> **정본은 18종이다. 화면은 18종을 전제로 만든다.**
> **픽스처에 없는 11종이 실제 게시물에는 온다:**
>
> ```
> DQ-02 · DQ-03 · DQ-04 · DQ-05 · DQ-06 · DQ-11 · DQ-12 · DQ-13 · DQ-14 · DQ-15 · DQ-16
> ```
>
> 픽스처에 실린 7종: `DQ-01`·`DQ-02b`·`DQ-07`·`DQ-08`·`DQ-09`·`DQ-10`·`DQ-17`.
> **`empty-sink` 는 18종을 전부 담는다** — 그쪽이 정상이다.
>
> **원인:** `tools/make_examples_connected.py` 가 `checks` 7종과 `reported_checks: 6` 을 **소스에 하드코딩**했다(453·456행). **재생성해도 같은 7종이 나온다.**
>
> ★ **픽스처를 열어 7개를 세고 "7개구나" 하지 마십시오.** V5 `/quality` 는 **18행**을 그린다.
> `spec_coverage.reported_checks` 도 **믿지 않는다** — 픽스처는 `6` 인데 실린 것은 `7` 이다. **실제 게시물에서는 `len(checks)` 와 같다**(M-07 `Q-3`).

### V6 `/freeze`

- **Lock 9종 전부** · `items[].status` **5값**(+`OUT_OF_SCOPE`)
- ★ **`scope_note` 를 접어 두지 않고 보인다** — 부분 Lock 의 범위가 보이지 않으면 전체 Lock 으로 읽힌다
- `canonical_files[].verification` **4값** — ★ **`not_run` 을 `match` 와 같은 색으로 그리지 않는다**
- `overall` 4값 — **`not_started` 는 경고가 아니라 사실로 그린다. 오늘의 정상 상태다**
- **`blocked[]` 를 표시한다**
- **`EXPERIMENT_ENVIRONMENT_v1` 을 선언하지 않았다는 사실을 쓴다**
- **`PARTIAL` 인데 `scope_note` 가 없으면 `violation · 범위 한정 문구 누락`**

### V7 `/triggers` — **정적. 게시물 없음**

PRD §71 트리거 5종을 **계획된 부재 표**로 그린다. **C1 작동 0종.**

```
모니터링 트리거 (PRD §71)                                     5종 · C1 작동 0종
· Churn ↑ → Segment Analysis                          계산 불가 · 이후 사이클
  차단: 이탈 임계값 미확정 · Segment 모델 없음 · 게시물 이력 없음
· Retention ↓ → Cohort Analysis                       계산 불가 · 이후 사이클
· AI ROI < Rule Baseline → Strategy Review            계산 불가 · 비교 전략 없음
⚠ Marketing Cost ↑ → Target Threshold Review          부분 · 임계값 미확정
  marketing_cost 계산 가능 · 임계 C_rule·B 는 GATE 2 확정 항목
  차단: 게시물 이력 없음 → 증가 여부를 판정할 수 없음
· Uplift ↓ → Treatment Policy Review                  계산 불가 · 모델 산출물 없음
─────────────────────────────────────────────────────────────────────────────
공통 선행 조건: 게시물 이력 보관 — 5종 전부가 시점 간 비교를 전제합니다.
```

> **★ 5종 전부가 `↑`/`↓` 를 전제한다. 변화에는 비교 기준이 필요하고 C1 게시물은 단일 시점 스냅샷이다.**
> **→ 경보 UI·배지·알림·임계 입력·토글을 만들지 않는다. 작동하지 않는 컨트롤은 두지 않는다.**
> **`index.static_views[]` 에 이 화면이 기록되어 있다** — 1:1 불변식의 명시적 예외.
> `[Source: .agent-team/07-design/ui-spec.md#7]`

## 4.7 ★★ USP-1 대표 장면 — 불변식 U-1 ~ U-10

```
┌─────────────────────────────────────────────────────────────────────────┐
│ 주문 경제성 · 커머스 실측       [표본 데이터]  ◼ 실측   2025-09-21 14:32 KST │
├──────────────────────────────────┬──────────────────────────────────────┤
│  revenue                         │  contribution_profit                 │
│                                  │                                      │
│  38,400원                        │  —                                   │
│  ← text-metric 2rem/700 · text   │  ← text-metric 2rem/700 ·            │
│                                  │    text-secondary                    │
│  기준: 주문 1건 · order_amount    │  ⚠ 계산 불가 · 원가 근거 없음          │
│        수신                       │  NO_COST_BASIS                       │
│                                  │  unit_cost 0 / 3 품목 수신            │
│                                  │  → incremental_contribution_profit   │
│                                  │     [P1] 성립 불가                    │
│                                  │  조치: Ecommerce #24                  │
└──────────────────────────────────┴──────────────────────────────────────┘
```

| # | 불변식 | 왜 |
|---|---|---|
| **U-1** | 두 지표는 **같은 카드, 같은 행, 같은 폭(1:1 2열)** | 다른 카드/화면이면 "나란히 비교"가 성립하지 않는다 |
| **U-2** | `38,400원` 과 `—` 는 **같은 타이포그래피 토큰** · 같은 baseline | ★ **크기가 다르면 부재가 덜 중요해 보인다. 대칭이 논증이다** |
| **U-3** | `—` 는 **절대 `0원` 이 아니다** | 금지 1호 |
| **U-4** | 사유가 **인라인**으로 항상 보인다. 호버·툴팁·접기 금지 | 스크린샷 증명 |
| **U-5** | `revenue` 쪽에 **기준 문구**가 있다 | 기준의 유무가 측정됨의 판별자 |
| **U-6** | 사유 코드 **`NO_COST_BASIS` 가 원문 그대로** 보인다 | 한국어 문구는 사람용, 코드는 추적용. **둘 다 필요** |
| **U-7** | **`P1` 영향**이 보인다 | ★ **원가 필드 하나가 Primary 지표를 무너뜨린다는 것이 이 장면의 진짜 내용이다** |
| **U-8** | **조치 줄**이 있다 | 결손 표시가 고발로 끝나지 않는다 |
| **U-9** | 출처 배지 `◼ 실측` 이 카드 머리에 | `NO_COST_BASIS` 는 출처를 묻지 않고 판정되지만 읽는 사람은 어느 쪽 데이터인지 알아야 한다 |
| **U-10** | 카드가 **기본 펼침** | V-0 |

### ★★ fixture 조건 — 리드 판정 J-1

> **fixture 는 손으로 쓴 게시물 JSON 이 아니라 실제 측정 계층 파이프라인을 통과한 산출물이어야 한다.**
>
> | 방식 | 스크린샷이 증명하는 것 |
> |---|---|
> | 손으로 쓴 게시물 JSON → 화면 | **화면이 그 JSON 을 그릴 수 있다**는 것뿐 |
> | **합성 이벤트 → 실제 Sink → 실제 게시 → 화면** | **파이프라인이 실제로 계산 불가를 판정하고 게시한다**는 것 |
>
> **USP-1 은 "화면이 회색 칩을 그릴 수 있다"가 아니라 "측정 계층이 계산 불가를 계산 불가로 말한다"다. 후자만 그것을 증명한다.**
>
> - 합성인 것은 **입력**이고 **파이프라인은 진짜**다 → 배지 문구 `표본 데이터 — 실측이 아닙니다` 가 정확하다
> - **`표본 데이터` 배지는 타협 불가다.** 표본을 실측처럼 보이게 하는 것은 **이 설계가 금지하는 바로 그 행위**다
> - **게시물 JSON 을 손으로 써서 스크린샷을 찍는 지름길을 쓰지 않는다.** 그렇게 찍은 스크린샷은 **US-13 인수조건을 충족하지 않는다**
>
> **→ M-06 T8 이 이 fixture 를 만든다.** 경로와 생성 방법을 그 스토리가 인계한다.
> `[Source: .agent-team/07-design/design-handoff.md#2]`

**커머스 이벤트가 0건인 동안 (2026-09-11 현재)** — `revenue` 도 `—` 이고 사유가 `NO_SOURCE_EVENT` 다. **대표 장면은 fixture 로만 성립한다.**

## 4.8 ★ 판정 배너 — **계약이 8종과 우선순위를 준다** (B-11 해소 · 리드 판정 2026-09-11)

**문제였던 것:** `verdict.counts.rejected_events` 는 있는데 `headline_code` 7종에 **거부를 지목하는 코드가 없었다.** 품질 전건 통과 + 거부 217건이면 `ALL_CLEAR` 로 떴다.

> ### ★ 해소 — 화면 우회를 쓰지 않는다. **M-06 이 계약을 고친다**
> `docs/contracts/measurement-publish/v1/index.schema.json` 은 **Phillip 소유**다 (`check_ownership.py` 실행 확인).
> **`headline_code` 가 8종이 되고 우선순위를 계약이 정의한다.**
>
> **화면 우회는 "계약이 옳으면 필요 없는 코드"다. 그런 코드는 계약이 고쳐진 뒤에도 남아서 아무도 지우지 못한다.**

### 화면이 하는 일 — **코드 → 문구 매핑만**

| 순위 | `headline_code` | `level` | 화면 문구 예 |
|---|---|---|---|
| 1 | `CONTRACT_VIOLATION` | `violation` | `✕ 계약 위반 — 게시물이 기준을 누락했습니다` |
| 2 | `QUALITY_VIOLATION` | `violation` | `✕ 데이터 품질 위반 N건` |
| 3 | `FREEZE_MISMATCH` | `violation` | `✕ 봉인 불일치 — 정본 파일이 Lock 시점과 다릅니다` |
| **4** | **`REJECTED_EVENTS`** ← 신설 | `violation` | **`✕ 거부 N건 — 사유별 보기`** |
| 5 | `CHECKS_NOT_RUN` | `attention` | `? 데이터 품질 검사 N건 미실행 — 통과로 볼 수 없습니다` |
| 6 | `SINK_EMPTY` | `attention` | `○ 수집된 이벤트 0건 — 커머스 미연결 · 시뮬레이터 미구현` |
| 7 | `METRICS_UNAVAILABLE` | `attention` | `⚠ 계산 불가 지표 N종` |
| 8 | `ALL_CLEAR` | `ok` | `✓ 수집 중 · 계약 위반 0건 · 거부 0건` |

| 규칙 | 내용 |
|---|---|
| **화면이 순위를 정하지 않는다** | 계약이 이미 하나를 골라 준다. **화면이 다시 판정하면 두 번째 정본이 생긴다** (`DB-012` · P-4) |
| **`headline_detail` 을 반드시 렌더한다** | 코드만 보고 문구를 만들지 않는다. **근거 수치가 거기 있다** |
| **F-3 — 0건은 경고가 아니다** | `SINK_EMPTY` 는 `attention`(info 계열). **`error`·`warning` 금지.** 2026-09-11 현재 이것이 **정상 상태**다 |
| **F-2 — "정상" 조건** | `ALL_CLEAR` 는 계약이 **1~7 이 전부 비어 있을 때만** 고른다. 화면이 완화하지 않는다 |
| 이동 | 해당 화면으로 가는 링크 동반. `REJECTED_EVENTS` → `/rejections` |

> **매핑 테이블은 화면 상수로 둔다** — 계약이 **코드**를 주고 **문구는 화면이 매핑**한다.
> Jonnathan 이 사유 코드에 대해 요구한 것과 같은 원칙이다.

## 4.9 반응형 — `Plan/DESIGN.md` 규정 그대로

| 뷰포트 | 동작 |
|---|---|
| 최대 너비 | `dashboard-max` **1440px** · 중앙 정렬 |
| 사이드바 | `dashboard-sidebar` **224px** |
| 좌우 여백 | `page-gutter`(32px) · 1024px 미만 `base`(16px) |
| 출처 2열 | **1024px 미만 세로 적층.** ★ **적층 시에도 커머스 먼저** |
| 표 | 좁아지면 **해당 영역만 가로 스크롤. 열을 숨기지 않는다** |
| 지표 카드 | 컨테이너 폭 기준 4열 → 2열 → 1열 |
| **200% 확대** | 겹침·잘림·조작 불가 없음. **상태 칩은 줄바꿈하고 고정 높이로 자르지 않는다** |

> **이 다섯 줄이 "Streamlit 으로 불가능해서 Next.js 를 고른 근거"(PRD §69)와 1:1 로 대응한다.**
> **구현에서 지키지 못하면 스택 선택 근거가 사라진다.**

## 4.10 접근성

| 항목 | 명세 |
|---|---|
| 포커스 | `focus` 2px 외곽선 + 2px 간격. **호버와 독립** |
| 비활성 (사이드바 결과 8항목) | `button-disabled` 색 + **실제 비활성 동작** + **사유 문구** |
| 전환 | 120ms ease-out. **`prefers-reduced-motion` 에서 제거** |
| 스켈레톤 | **실제 데이터 요청이 있을 때만.** 파일 읽기는 즉시 끝난다 |
| **글리프 접근성** | **전부 `aria-label`.** 아이콘 단독 전달 금지 |
| 새로고침 | **수동 버튼 1개.** 자동 폴링 없음 |

**대비 실측 (WCAG · `Plan/DESIGN.md` 4.5:1 기준):** 전부 통과. **`planned` 조합이 4.89:1 로 가장 빡빡하다 — 여유 0.39. 토큰 변경 시 재검산.**

## 4.11 만들지 않는 컴포넌트

| 없음 | 근거 |
|---|---|
| 이벤트 행 목록·검색·필터 | **A5 — 이벤트 브라우저는 C1 범위 밖.** 요구가 나오면 **멈추고 보고** |
| 기간 필터·날짜 선택 | 단일 스냅샷. 기간 축이 없다 |
| 임계 입력·경보 토글 | 작동하지 않는 컨트롤을 두지 않는다 |
| 증감 배지·스파크라인·델타 | V-11 |
| 다크 모드 토글 | 라이트 고정 |
| **빈 상태 일러스트** | ★ **이벤트 0건을 빈 상태로 대체하지 않는다** |
| 토스트 | `Plan/DESIGN.md` |

## 4.12 함정

| # | 함정 | 왜 빠지나 | 대신 |
|---|---|---|---|
| **T-1** | `?? 0` | ★ **예외를 막으려고** | §4.1 |
| **T-2** | 계산 불가 19행을 접는다 | **UX 개선처럼 보인다** | V-0 — **1차 독자는 결손을 찾으러 온다** |
| **T-3** | `—` 를 작게·흐리게 | 화면이 시끄러워서 | V-1 — **0 채우기의 정중한 버전** |
| **T-4** | 사유를 툴팁에 | 인라인이 지저분해서 | V-9 — **호버는 스크린샷에 남지 않는다** |
| **T-5** | `filter(d => d.value > 0)` | 차트를 깔끔하게 | **0건 항목이 사라진다** |
| **T-6** | 선 차트를 쓴다 | 시계열이니까 | **결손 구간에서 이으면 없는 값을 만든다.** 막대를 쓴다 |
| **T-7** | 히어로 합산 지표 | 대시보드 관습 | **계층 1·2 에 `combined` 가 스키마 금지** |
| **T-8** | **`vacuous` 를 초록(통과)이나 빨강(실패)으로 그린다** | **`pass`/`fail` 두 값만 있다고 가정** — 5상태를 안 본다 | ★ §4.2 검사 상태 표. **`vacuous` 는 `unconnected`(info)** 다. 실패도 통과도 아니다 |
| **T-8b** | `status === 'vacuous' \|\| (status === 'pass' && rows === 0)` 이중 분기 | 옛 규칙을 함께 지키려고 | ★ **`status` 로만 분기한다.** 뒷항은 스키마가 금지해 **영원히 거짓**이고, `examined_rows` 를 다시 읽는 것은 **게시물이 한 판정을 화면이 반복하는 것**이다 (`DB-012`) |
| **T-9** | `not_run` 을 `—` 로 | 계산 불가니까 | **글자 `미실행`.** `—` 는 "없음", `미실행` 은 "모름" |
| **T-10** | `connected` 에 `✓ 수신 중` | 자연스러워 보인다 | §4.5 C-3 — **2값으로 할 수 없는 건강 판정** |
| **T-11** | 배너 건수를 화면이 센다 | 간단해서 | **단순 합산도 계산이다** (`DB-012`) |
| **T-12** | fixture 를 손으로 쓴 JSON 으로 | 빠르다 | ★ §4.7 — **US-13 인수조건을 충족하지 않는다** |
| **T-13** | `표본 데이터` 배지 생략 | 화면이 깔끔해서 | ★ **타협 불가.** 표본을 실측처럼 보이게 하는 행위 |
| **T-14** | 거부 샘플의 값을 그린다 | 사유를 이해하려고 | **금지 필드가 화면까지 간다** |
| **T-15** | `scope_note` 를 접는다 | 길어서 | **부분 Lock 이 전체 Lock 으로 읽힌다** |
| **T-16** | 정렬 기본을 건수 내림차순 | 관습 | **0건이 항상 아래로 밀려 숨는다.** 고정 순서 |

---

# 5. 작업 분해 (Tasks)

## T1 · 컴포넌트 8종 (AC-2)

- [ ] **`MetricCell` 먼저** — 4슬롯 · 상태 8종 · **자기 검사 3건**
- [ ] `StateChip` — 글리프 + `aria-label` + 보조 칩 5종
- [ ] `SourceColumns` + `ConnectionState`
- [ ] `VerdictBanner`
- [ ] `ImpactChain`
- [ ] `CoverageTable`
- [ ] `IngestionTimeline` — **막대. 라이브러리 선택은 §9.3**
- [ ] `NoticeBar`

## T2 · 화면 8개 (AC-1)

- [ ] `/` 인덱스 — 8블록
- [ ] V1 `/ingestion` · V2 `/rejections` · V3 `/coverage`
- [ ] **V4 `/kpi` — 대표 장면 카드 최상단 고정**
- [ ] V5 `/quality` · V6 `/freeze`
- [ ] V7 `/triggers` — 정적 계획된 부재 표

## T3 · 사이드바 (리드 판정 J-2)

- [ ] 관측 7항목 + **결과 8항목 비활성 노출**
- [ ] 비활성 항목에 **`button-disabled` 색 + 실제 비활성 동작 + 사유 문구**

## T4 · ★ USP-1 대표 장면 (AC-12)

- [ ] **M-06 이 만든 fixture 경로를 확인한다**
- [ ] U-1 ~ U-10 전부 충족
- [ ] **`표본 데이터` 배지**
- [ ] **스크린샷 촬영** — PR 에 첨부

## T5 · 검증 (AC-13)

- [ ] `grep -rn '?? 0\|\|\| 0\|Number(' dashboard/src` — 지표 값 경로 0건 확인
- [ ] `grep -rn '#[0-9A-Fa-f]\{3,6\}' dashboard/src` — 0건
- [ ] `grep -rn 'node:fs\|from "fs"' dashboard/src` — `lib/artifacts/` 안에서만
- [ ] **빈 Sink 픽스처로 전 화면 렌더** — 예외 없이 전부 계산 불가 (C-9)
- [ ] `commerce-connected` 픽스처로 전 화면 렌더
- [ ] `npm run tokens:check` · `npm run tokens:test`
- [ ] `python3 -m unittest discover -s tests` · `tests.test_isolation`
- [ ] `python3 .agent-team/04-architecture/tools/check_ownership.py`

## T6 · 스크린샷 증거

> ### ⚠ **촬영 수단을 먼저 정한다** (Matthias N-4 · W3 실측 2026-09-11)
>
> **AC-12 155행 · T5 · T6 · DoD 2행 — 다섯 자리가 스크린샷을 요구하는데 이 스토리 안에 수단이 없었다.**
> **실측했더니 "아무것도 없다"보다 나은 상황이다 — 옆 저장소에 이미 있다:**
>
> | 확인 | 결과 |
> |---|---|
> | `AI_ROI/package.json` · `node_modules` | **둘 다 없음** (파이썬 저장소다. `dashboard/` 는 d-01 이 만든다) |
> | ★ `Ecommerce_Service/node_modules/@playwright/test` | **설치됨 · `1.63.0`** (`devDependencies: "^1.63.0"`) |
> | ★ `Ecommerce_Service/playwright.config.ts` | **있음** — `baseURL http://127.0.0.1:3100` · `Desktop Chrome` 1개 프로젝트 · `webServer` 자동 기동 |
> | `Ecommerce_Service` npm script | **`"test:e2e": "playwright test"`** |
> | ★ **브라우저 바이너리** (`~/Library/Caches/ms-playwright`) | **없음** — **`npx playwright install` 미실행** |
> | `chromium`·`playwright` CLI (PATH) | **없음** |
> | Chrome · Safari.app | **있음 → 수동 촬영은 가능** |
>
> **→ 막힌 것은 도구 선택이 아니라 브라우저 다운로드 한 번이다.** 버전(`1.63.0`)과 설정 형태(`playwright.config.ts`)는 **옆 저장소에 정본이 있으므로 새로 정하지 않는다.**
> **다만 `npx playwright install` 은 네트워크 다운로드이고 `dashboard/` 에 devDependency 를 추가하는 것은 새 의존성이다 — 둘 다 L1, 사용자 결정이다.**
>
> **아래 체크박스를 무조건 체크로 두지 않는다. §7.2 가 C-2·C-11 에 보인 정직함을 여기에도 적용한다.**
>
> | 선택 | 해야 할 것 |
> |---|---|
> | ⑴ **수동 촬영** *(오늘 바로 가능)* | Chrome/Safari 로 찍는다. **촬영 목록·해상도·사람이 찍었다는 사실**을 PR 에 적는다. **자동 회귀는 없다** |
> | ⑵ **Playwright 도입** | `dashboard/package.json` 에 `@playwright/test` **`^1.63.0`**(옆 저장소와 맞춘다) + `npx playwright install chromium` + `playwright.config.ts` 를 `Ecommerce_Service` 형태로. **포트는 3001** (d-01 `next dev --port 3001`) — `Ecommerce_Service` 의 3100 과 충돌하지 않는다. **사용자 승인 필요** |
> | ⑶ **`BLOCKED`** | 사유와 함께 §9.4 에 남긴다. **AC-12·DoD 항목을 지우지 않는다** |
>
> ⚠ **`Ecommerce_Service` 를 편집해 찍지 않는다.** 그 저장소는 이 사이클에서 **읽기 전용**이다 (§0 ②).

- [ ] ★ **위 셋 중 하나를 먼저 고르고 PR 에 적는다**
- [ ] US-11 · US-12 · US-13 · US-14 인수조건이 요구하는 화면
- [ ] **빈 Sink 상태 전 화면** — *"계산 불가로 가득한 것이 정상 동작"* 의 증거
- [ ] **USP-1 대표 장면**
- [ ] `D-17` 결정에 따라 증거 사본 위치를 정한다 (`results/` 가 gitignore 될 수 있다)

---

# 6. 파일 목록 (`file_list`)

## 6.1 이 스토리가 만드는 파일 — **전부 `dashboard/` 안**

```text
dashboard/src/components/{MetricCell,StateChip,SourceColumns,VerdictBanner,
                          ImpactChain,CoverageTable,IngestionTimeline,NoticeBar}.tsx
dashboard/src/lib/format/**
dashboard/src/app/page.tsx                                    ← 본문
dashboard/src/app/(observability)/*/page.tsx                  ← 본문
```

## 6.2 절대 만지지 않는 파일

```
src/** · config/** · requirements*.txt · .gitignore · tests/**   ← Phillip · 봉인
Plan/**                             ← Plan/DESIGN.md 는 read-only 정본
../Ecommerce_Service/**             ← 읽기만
data/raw/** · data/hidden/** · data/ground_truth/**   ← ★ DB-014
.agent-team/**                      ← 읽기만
```

---

# 7. 테스트

## 7.1 실행 가능한 명령

```bash
cd dashboard
npm run dev                 # :3001
npm run tokens:check
npm run tokens:test

# 픽스처로 렌더
AIROI_RESULTS_DIR=../.agent-team/04-architecture/examples/empty-sink npm run dev
AIROI_RESULTS_DIR=../.agent-team/04-architecture/examples/commerce-connected npm run dev
```

> ### ★★ `commerce-connected` 픽스처는 **검사 7종만 담고 있고 이것은 결함이다** (리드 지시)
>
> **정본은 18종이다. 화면은 18종을 전제로 만든다.**
> **픽스처에 없는 11종이 실제 게시물에는 온다:**
>
> ```
> DQ-02 · DQ-03 · DQ-04 · DQ-05 · DQ-06 · DQ-11 · DQ-12 · DQ-13 · DQ-14 · DQ-15 · DQ-16
> ```
>
> 픽스처에 실린 7종: `DQ-01`·`DQ-02b`·`DQ-07`·`DQ-08`·`DQ-09`·`DQ-10`·`DQ-17`.
> **`empty-sink` 는 18종을 전부 담는다** — 그쪽이 정상이다.
>
> **원인:** `tools/make_examples_connected.py` 가 `checks` 7종과 `reported_checks: 6` 을 **소스에 하드코딩**했다(453·456행). **재생성해도 같은 7종이 나온다.**
>
> ★ **픽스처를 열어 7개를 세고 "7개구나" 하지 마십시오.** V5 `/quality` 는 **18행**을 그린다.
> `spec_coverage.reported_checks` 도 **믿지 않는다** — 픽스처는 `6` 인데 실린 것은 `7` 이다. **실제 게시물에서는 `len(checks)` 와 같다**(M-07 `Q-3`).

> ⚠ **픽스처 디렉터리 구조가 `results/` 배치와 다르다.**
> 픽스처는 7파일이 **한 디렉터리에** 있고, 실제 배치는 `results/data_quality_report.json` + `results/measurement/*.json` 이다.
> **`AIROI_RESULTS_DIR` 로 픽스처를 가리키면 경로가 맞지 않는다.**
> → **픽스처를 실제 배치대로 임시 복사하거나, 읽기 계층에 픽스처 모드를 두거나, M-06 의 실제 게시를 기다린다.**
> **셋 중 하나를 고르고 PR 에 적는다** (§9.3 D02-b). **픽스처 원본을 수정하지 않는다.**

**C1 은 Node 테스트 러너·lint 를 CI 에 도입하지 않는다** — 없는 게이트를 만들지 않는다.

## 7.2 W6 검증 항목 17종

| # | 명제 | 자동화 |
|---|---|---|
| C-1 | 계산 불가 셀에 문자 `0` 이 없다 | ✅ |
| C-2 | `—` 의 font-size 가 값과 같다 | ⚠️ **어렵다 — 육안** |
| C-3 | 모든 `available` 값에 기준 문구 | ✅ |
| C-4 | 사유 코드가 **호버 없이** 보인다 | ✅ |
| C-5 | 조치 줄이 있다 | ✅ |
| C-6 | `event_type` 16행 | ✅ |
| C-7 | 증감·스파크라인 0건 | ✅ |
| C-8 | hex 리터럴 0건 | ✅ |
| **C-9** | ★ **빈 게시물로 렌더 시 예외 없이 전부 계산 불가** | ✅ **USP-1 자체의 회귀 테스트** |
| C-10 | 대비 8조합 | ✅ (토큰값 계산) |
| C-11 | 상태 칩 글리프 | ✅ **구조 제약으로 자동화** — 아래 |
| C-12 | 출처 2열 순서 | ✅ |
| **C-13** | **`status:"vacuous"` 행이 초록이 아니고 `✓` 가 없다** | ✅ |
| **C-14** | **`gate_result: incomplete` 에 `success` 토큰 없음** | ✅ |
| **C-15** | **V2 거부 샘플에 값 0건** | ✅ |
| **C-16** | **`notices[]` 전부 렌더 · 접히지 않음** | ✅ |
| **C-17** | 시각 상태가 순수 매핑 (화면에 판정 분기 0건) | ✅ |

> > ### ★ C-11 을 육안에서 grep 명제로 바꾼다 (Matthias 항목1)
> **글리프 리터럴(`⚠`·`○`·`◐`·`⊘`·`?`·`✕`·`·`·`✓`)을 `StateChip` 한 파일에만 둔다.**
> 그러면 *"글리프가 다 있나"* 가 **`StateChip` 밖에 글리프 리터럴 0건 + `StateChip` 안에 상태 수만큼 존재**라는 두 grep 으로 끝난다.
> **자동화가 어렵다는 것은 설계의 성질이 아니라 배치의 결과였다.**

**C-9 가 가장 중요하다.** *"누군가 '화면이 비어 보인다'는 이유로 0 을 채우면 깨진다."*
> **`tests/test_sink.py:198-203` 과 짝이 되는 화면 쪽 검사다.**
> **C-2·C-11 은 자동화가 어렵다. 어려운 것을 통과로 적지 않는다.**
> `[Source: .agent-team/07-design/design-handoff.md#3]`

## 7.3 Thomas(W6 리뷰)가 최우선 탐색할 것

**화면 쪽 결손 은폐는 셋이다. 0 을 쓰는 것만이 아니다:**

| 은폐 방식 | 탐지 |
|---|---|
| `0` 으로 채운다 | C-1 |
| ★ **`—` 를 작게·흐리게 만든다** | C-2 — **0 채우기의 정중한 버전** |
| ★ **결손 항목을 접거나 기본 필터로 감춘다** | C-6 · 접기 컴포넌트 검색 |

## 7.4 PR 전 체크리스트

```
- [ ] `?? 0` · `|| 0` · `Number(value)` 가 지표 값 경로에 0건
- [ ] `—` 의 font-size 가 같은 카드의 값과 같다
- [ ] 모든 `status: "ok"` 값에 기준 문구가 있다
- [ ] 사유 코드가 호버 없이 보인다
- [ ] `gap`·`env_blocked`·`provisional` 에 글리프가 있고 `aria-label` 이 있다
- [ ] 접기·"더 보기"·기본 필터가 결손 항목에 없다
- [ ] event_type 16행 · 필드 22행 · Lock 9행 · 지표 47행이 전부 렌더된다
- [ ] 증감 화살표·스파크라인 0건
- [ ] hex 색 리터럴 0건
- [ ] notices[] 가 전부 보이고 접히지 않는다
- [ ] 거부 샘플에 값이 없다 (필드 이름만)
- [ ] `status: "vacuous"` 행이 **초록도 `✓` 도 아니고** `공허한 통과 · 검사 대상 0행` + `scope` 가 붙어 있다
- [ ] fixture 가 실제 파이프라인 산출물이고 `표본 데이터` 배지가 붙어 있다
```

`[Source: .agent-team/07-design/dashboard-agents-design-constraints.md#8]`

---

# 8. 연속성

## 8.1 선행 스토리에서 이어받는 것

| 스토리 | 이어받는 것 |
|---|---|
| **d-01** | 앱 골격 · 라우트 자리 · **읽기 계층 + 최소 불변식 검사** · 토큰 · 상태 토큰 · `dashboard/AGENTS.md`(DG-1~DG-19) · 빈 상태 확정 문구 |
| **M-06 (게시)** | ★ **실제 게시물 6종 + index** · **USP-1 대표 장면 fixture** · `headline_detail` 이 거부 건수를 담는다 (B-11 우회) |
| **M-04 (`#46`)** | 47종 분류표 → V4 가 그대로 옮긴다 · `한계` 칩 대상 |
| **M-07 (`#48`)** | V5 의 5상태 · **`vacuous` 가 오늘의 정상 상태** · `incomplete` 에 `success` 금지 |
| **M-09 (`#49`)** | V6 의 `overall: "not_started"` 가 **오늘의 정상 상태** |
| **M-02 (`#54`)** | 사유 코드 9종의 **정확한 문자열** — 시각 상태 매핑의 키 |

## 8.2 확립된 것 — 다시 설계하지 않는다

| 항목 | 어디에 |
|---|---|
| 상태 어휘 8종 | `missing-state-spec.md` §4.2 · `contract-reconciliation.md` §3-③ |
| 컴포넌트 8종 명세 | `design-system/components.md` |
| 상태 토큰 CSS 167줄 | `design-system/state-tokens.css` — **hex 0건 확인됨** |
| 화면별 명세 | `ui-spec.md` |
| 정보구조·동선 | `ux-flow-map.md` |
| 목업 아트보드 5종 | `design-handoff.md` §5 — **정적 목업이다.** 자간·행간 판정에 쓰지 않는다 |

## 8.3 이후 사이클이 이어받는 것

> **이후 사이클은 상태 어휘를 다시 설계하지 않는다.**
> **`NEEDS_MODEL_OUTPUT` → `available` 전환만으로 결과 화면이 켜진다.**
> **상태 어휘를 C1 에 제대로 만드는 것이 이후 사이클의 최대 절약이다.**

---

# 9. 완료 정의 (DoD) · 미결정 · 차단

## 9.1 DoD

- [ ] AC-1 ~ AC-13 전부 체크
- [ ] **§7.4 PR 전 체크리스트 13항목 전부**
- [ ] ★ **빈 Sink 픽스처로 전 화면이 예외 없이 렌더되고 전부 계산 불가다** (C-9)
- [ ] ★ **USP-1 대표 장면 스크린샷** — fixture 가 **실제 파이프라인 산출물**이고 `표본 데이터` 배지가 붙어 있다
- [ ] US-11·12·13·14 스크린샷
- [ ] ★ **위 두 항목은 T6 의 선택 ⑴·⑵·⑶ 중 하나를 고른 뒤에만 체크한다.** ⑶ 을 골랐으면 **`BLOCKED` 와 사유를 §9.4 에 적고 체크하지 않는다** — **미실행을 통과로 표시하지 않는다** (Matthias N-4)
- [ ] ★ **`headline_code` 8종 매핑을 구현했고, 화면이 순위를 정하지 않는다** (§4.8)
- [ ] **`headline_detail` 을 반드시 렌더한다**
- [ ] **C-2·C-11 을 자동화하지 못했으면 그렇게 적었다** — 어려운 것을 통과로 적지 않는다
- [ ] `dashboard/` 밖 파일 변경 0건

## 9.2 이 스토리에서 하지 않는 것

| 항목 | 왜 |
|---|---|
| `DB-003`~`DB-010` 결과 화면군 | 이후 사이클 |
| 이벤트 브라우저 | **A5.** 요구가 나오면 **멈추고 보고** |
| 실시간 갱신·자동 폴링 | `DB-011` |
| API 라우트·서버 액션 | `DB-013` |
| 증감·시계열 | V-11 — 이력 보관 계약이 없다 |
| 경보 UI·임계 입력 | §4.6 V7 |
| 다크 모드·모바일 전용·인증·다국어 | 범위 밖 |
| **화면이 `verdict` 를 다시 계산** | `DB-012` |
| **게시물 수정** | 읽기 전용 |

## 9.3 미결정 — 구현자가 정하고 PR 에 적는다

| # | 항목 | 선택지 |
|---|---|---|
| **D02-a** | **차트 라이브러리** | Jonnathan 이 미정으로 남겼다. **관측 화면군은 막대만 쓰므로 라이브러리 없이 SVG/CSS 로 가능하다.** 라이브러리를 넣으면 §4.1 의 `null` 함정을 새로 관리해야 한다 — **넣지 않는 쪽을 권장** |
| **D02-b** | **픽스처를 어떻게 읽히나** | ⑴ 실제 배치대로 임시 복사 ⑵ 읽기 계층에 픽스처 모드 ⑶ M-06 실제 게시를 기다린다 — §7.1. **픽스처 원본을 수정하지 않는다** |
| **D02-c** | 스크린샷 증거 위치 **+ 촬영 수단** | 위치는 **D-17** 결과에 종속. **수단은 T6 의 ⑴수동/⑵Playwright `^1.63.0` 도입(사용자 결정·L1)/⑶`BLOCKED`** 중 하나. **버전·설정 형태는 `Ecommerce_Service` 정본을 따르고 새로 정하지 않는다** (Matthias N-4) |
| **D02-d** | `headline_code` → 문구 매핑 테이블 위치 | 화면 상수 (계약이 코드를 주고 문구는 화면이 매핑한다) |

## 9.4 차단

| # | 항목 | 성격 |
|---|---|---|
| **d-01** | 선행 스토리 | 완료 필요 |
| **M-06** | 실제 게시물 · USP-1 fixture | **AC-12 는 M-06 없이 충족할 수 없다.** 나머지는 픽스처로 진행 가능 |
| ~~**B-11**~~ | ~~`headline_code`~~ | ★ **해소 (리드 판정)** — M-06 이 계약을 8종으로 고친다. §4.8 |
| **D-22** | `test_dashboard_isolation.py` | **W6 + 사용자 승인.** 미도입이면 DG-1~DG-8 이 사람의 규율로만 지켜진다 |
| ★ **M-06 미완 (숫자 렌더)** | **픽스처 14파일에 `value_formatted` 가 0건이다** | ★ **여기가 d-01 보다 무겁다.** 숫자를 실제로 그리는 것은 골격이 아니라 **`MetricCell` × 8화면**이고, **T5 가 `commerce-connected` 전 화면 렌더를 요구한다.** 그 픽스처에 `value_formatted` 가 없으므로 **모든 `ok` 셀이 `undefined`** 다. → M-06 전에는 숫자를 그리지 말고 `계약 준비 중` 으로 둔다 (§4.1 과 같은 판정). **`픽스처로 진행 가능` 에 숫자 렌더는 포함되지 않는다** (Matthias N-10) |
| ★ **스크린샷 촬영 수단 미정** | **AC-12·T5·T6·DoD 5자리가 요구하는데 수단이 정해져 있지 않다** | **실측(2026-09-11): `AI_ROI` 에 `package.json`·`node_modules` 없음. 단 `Ecommerce_Service` 에 `@playwright/test 1.63.0` 설치본과 `playwright.config.ts` 가 있다.** **막힌 것은 브라우저 바이너리 하나** — `~/Library/Caches/ms-playwright` 없음(`npx playwright install` 미실행). → ⑴수동 촬영(오늘 가능) / ⑵Playwright 도입(**새 의존성 + 네트워크 다운로드 · 사용자 결정 L1**) / ⑶`BLOCKED` 중 하나를 **T6 에서 먼저 고른다.** **무조건 체크박스로 두지 않는다** (Matthias N-4) |

## 9.5 하류로 넘기는 것

| 받는 쪽 | 넘기는 것 |
|---|---|
| **W6 Matthias** | §7.2 검증 명제 17종 · **C-2·C-11 이 자동화되지 않았다는 사실** |
| **W6 Thomas** | §7.3 — 화면 쪽 결손 은폐 3종 |
| **W6 Timothy** | `dashboard/AGENTS.md` 검토 · `design-rules.css` 의 본문 유래 값이 `tokens:check` 검증 범위 **밖**임을 명시 |
| **M-09 (`#49`)** | `DB-013` 부분 충족 · `DASHBOARD_NOT_ISOLATION_CHECKED` |
| **리드** | USP-1 증명 스크린샷 |
| **이후 사이클** | 상태 어휘 8종 · 컴포넌트 8종 · `inconclusive`·`stale` 예약 슬롯 (**CSS 토큰도 만들지 않았다**) |

<!-- ════════ source_hash inputs (D3 · Matthias 항목5) ════════
     계산법: project-context-kr.md §12  ·  파일 27종
     재현:  아래 목록을 sorted() 하고 각 파일에 f"{path}\n{sha256_hex}\n" 를 이어붙여
            그 바이트열의 SHA-256 앞 16자리를 취한다. 없는 파일은 "MISSING".

     .agent-team/00-plan/charter.md
     .agent-team/00-plan/task-graph.md
     .agent-team/03-service-planning/kpi-definition-v1.md
     .agent-team/03-service-planning/user-stories.md
     .agent-team/04-architecture/api-contracts.md
     .agent-team/04-architecture/build-plan.md
     .agent-team/04-architecture/code-structure.md
     .agent-team/04-architecture/dashboard-architecture.md
     .agent-team/04-architecture/design-patterns.md
     .agent-team/04-architecture/exceptions.md
     .agent-team/04-architecture/schemas/common.schema.json
     .agent-team/04-architecture/schemas/data_quality_report.schema.json
     .agent-team/04-architecture/schemas/field_coverage_report.schema.json
     .agent-team/04-architecture/schemas/freeze_status.schema.json
     .agent-team/04-architecture/schemas/index.schema.json
     .agent-team/04-architecture/schemas/ingestion_report.schema.json
     .agent-team/04-architecture/schemas/kpi_report.schema.json
     .agent-team/04-architecture/schemas/rejection_report.schema.json
     .agent-team/07-design/contract-reconciliation.md
     .agent-team/07-design/dashboard-agents-design-constraints.md
     .agent-team/07-design/design-system/components.md
     .agent-team/07-design/missing-state-spec.md
     .agent-team/07-design/ui-spec.md
     .agent-team/07-design/ux-flow-map.md
     AGENTS.md
     docs/GIT_WORKFLOW.md
     src/AGENTS.md

     → source_hash = edb8e795ec6bf1c4
     ════════════════════════════════════════════════════ -->
