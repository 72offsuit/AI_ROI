# 컴포넌트 명세 — 관측 화면군 (C1)

**작성** Jonnathan (Role 7 · Chief Designer) · 2026-09-11
**토큰** `state-tokens.css`(제안) · 생성 토큰 `--ds-*`(`Plan/DESIGN.md` 유래) · 전략 `token-strategy.md`
**상태 정의** `../missing-state-spec.md` §4.2 — 여기서 재정의하지 않는다

> ### ⚠ 개정 (2026-09-11, 계약 수신 후) — **컴포넌트 8개**
> **`C-8 NoticeBar` 신설** (계약 R-8: *"`notices`를 화면에 표시한다. 가정을 숨기지 않는다"*). 내 설계에 없었다.
> `C-2 StateChip`의 `blocked` → **`gap`** 개명 · **`env_blocked`** 추가. 대조 전문은 [`../contract-reconciliation.md`](../contract-reconciliation.md).

> 컴포넌트는 **8개뿐이다.** 관측 화면군 6화면 전부가 이 7개의 조합이다.
> 적게 유지하는 이유: 상태 어휘가 **모든 컴포넌트에서 동일하게** 동작해야 한다. 컴포넌트가 늘면 같은 상태가 곳마다 다르게 보인다.

---

# C-1 · `MetricCell` — 지표 한 칸 (가장 중요)

모든 숫자가 이것을 거친다. 상태 8종을 전부 처리하는 **유일한** 컴포넌트다.

## 해부 — 4슬롯 고정

```
┌──────────────────────────────────────────┐
│ ① 지표명          text-label-md          │
│ ② 값 슬롯         text-metric / -table-number   ← 숫자 또는 —
│ ③ 상태 슬롯       칩 + 사유 + 사유 코드   ← 상시 표시 (V-9)
│ ④ 근거 슬롯       기준 / 영향 / 조치      text-caption
└──────────────────────────────────────────┘
```

| 슬롯 | `available` | 계산 불가 5종 |
|---|---|---|
| ② 값 | 숫자 · `--obs-value-ink` | `—` · `--obs-absent-ink` · **같은 타이포 토큰** (V-1) |
| ③ 상태 | 칩 없음 | 글리프 + 문구 + 사유 코드 |
| ④ 근거 | **기준 필수** (V-2) | 영향 사슬 + 조치 (V-8) |

## 입력 계약

```
MetricCell {
  name              string                 // ① 지표명
  state             'available' | 'provisional' | 'planned'
                  | 'unconnected' | 'blocked' | 'not_run' | 'violation'
  value?            string                 // ② 게시물이 포맷한 문자열. 화면이 포맷하지 않는다
  basis?            string                 // ④ 분모·모집단·기간 — state=available 이면 필수
  reason?           ReasonCode             // ③ 7종 사유 코드 — 문구가 아니라 코드
  reasonDetail?     string                 // ③ 둘째 줄
  paramsUsed?       Record<string,string>  // ③ provisional 전용 (R-10)
  derived?          boolean                // `유도값` 칩
  limitNote?        string                 // `한계` 칩 (V-7)
  affects?          ImpactChain[]          // ④ 영향 사슬 (2홉)
  action?           string                 // ④ 조치 — blocked·not_run·violation 이면 필수
  source?           'commerce' | 'simulator' | 'combined'
  scale             'metric' | 'table-number'
}
```

> **`value`를 문자열로 받는 이유 — `DB-012`다.** 숫자를 받으면 화면이 통화·소수·천단위·단위를 결정하게 되고, 그것은 **표시 규칙의 계산**이다. `Plan/DESIGN.md`도 *"소수 자릿수·반올림·할인 계산은 도메인 규칙으로 정하고 **디자인에서 새로 계산하지 않는다**"* 고 규정한다. 게시물이 `"38,400원"`을 준다.

## 자기 검사 — 3건 (V-3)

컴포넌트가 입력의 계약 위반을 화면에 드러낸다. **판정이 아니라 필수 필드 존재 검사이므로 `DB-012` 위반이 아니다.**

| 조건 | 렌더 |
|---|---|
| `state='available'` 이고 `basis`가 없다 | 값 + `✕ 계약 위반` + `기준 미표기 — 분모를 확인할 수 없습니다` |
| `state ∈ {blocked, not_run, violation}` 이고 `action`이 없다 | 값/`—` + `조치 미정` (**빈칸으로 두지 않는다**, V-8) |
| `state ≠ 'available'` 인데 `value`에 숫자가 들어왔다 | `—`로 렌더하고 `✕ 계약 위반 · 계산 불가 상태에 값이 왔습니다` |

> 셋째 행이 **0 채우기를 잡는 최종 방어선**이다. 측정 계층이 `state='unavailable'`과 `value='0'`을 같이 보내면 화면이 거부한다.

## 금지

| 금지 | 근거 |
|---|---|
| `state ≠ available`에서 값 슬롯에 숫자·`0`·`N/A`·`null`·빈칸 | V-1 · §3.1 |
| `—`를 값보다 작게·흐리게(`text-muted`) | **V-1 — 이 설계의 핵심** |
| 사유를 호버·툴팁·접기로만 제공 | V-9 |
| `basis` 없는 `available` 렌더 | V-3 |
| 증감 화살표·스파크라인 | V-11 |

---

# C-2 · `StateChip` — 상태 칩

```
[글리프] [문구]          예: ⚠ 계산 불가 · 원가 근거 없음
```

| 상태 | 계약 `(status, reason_code)` | 글리프 | ink / 배경 / 테두리 |
|---|---|---|---|
| `provisional` | `unconfirmed` | **◐** | `--obs-provisional-*` · **실선 윤곽** 1px |
| `planned` | `unavailable` + `NEEDS_*`·`PRECONDITION_MISSING` | **·** | `--obs-planned-*` · 채움 |
| `unconnected` | `unavailable` + `NO_SOURCE_EVENT` | **○** | `--obs-unconnected-*` · 채움 |
| **`gap`** | `unavailable` + `NO_COST_BASIS`·`MISSING_FIELD` | **⚠** | `--obs-gap-*` · 채움 |
| **`env_blocked`** | **`blocked`** + `BLOCKED` | **⊘** | `--obs-envblocked-*` · **점선 윤곽** 1px |
| `not_run` | `not_run` + `NOT_RUN` | **?** | `--obs-notrun-*` · 실선 윤곽 1px |
| `violation` | (화면 자기 검사) | **✕** | `--obs-violation-*` · 채움 |
| `ok` | (게이트 `pass`) | **✓** | `--obs-ok-*` · 채움 |

> **상태는 계약에서 파생된다. 화면이 새로 판정하지 않는다** — `(status, reason_code)` → 시각 상태는 순수 매핑이다 (`DB-012`).

형태: `--obs-chip-radius`(= `rounded.full`, DESIGN.md *"작은 상태 배지"*) · `text-caption` · 아이콘 16px(밀도 높은 표) / 20px(카드).

| 규칙 | 내용 |
|---|---|
| **글리프 생략 금지** | `gap`·`env_blocked`·`provisional`이 같은 `warning` 색이다. 값 슬롯(숫자/`—`) + 선 종류(채움/실선/점선) + 글리프 3중으로 갈리며, **글리프가 없으면 흑백·축소에서 `gap`/`env_blocked` 구분 불가** |
| **접근 가능한 이름 필수** | 글리프는 장식이 아니다. `aria-label`에 문구 전문 (`Plan/DESIGN.md`) |
| 줄바꿈 | 200% 확대 시 칩이 줄바꿈한다. **고정 높이로 자르지 않는다** |
| 색 단독 금지 | 글리프 + 문구 + 색 3중 (`Plan/DESIGN.md`) |

## 보조 칩 — 상태 칩과 **같이** 쓸 수 있다

| 칩 | 문구 | ink | 언제 |
|---|---|---|---|
| `유도값` | `유도값` | `--obs-derived-ink` | `derived: true` — 저장된 사실이 아니라 규칙 유도 (D-3 ⑴) |
| `한계` | `한계 · <내용>` | `--obs-limit-ink` | 값은 나오나 정밀도 한계 (V-7 · `campaign_response_count`) |
| `합산` | `· 합산` | `--obs-combined-ink` | 출처 합산 (R-7 / S-3). **이름에도 붙인다** |
| `표본 데이터` | `표본 데이터` | `--obs-fixture-*` · 채움 | fixture 렌더 (`ui-spec.md` §5.2 ⑴). **타협 불가** |
| **`공허한 통과`** | `공허한 통과 · 검사 대상 0행` | `--obs-vacuous-*` | **규칙 V-12** — `pass` ∧ `examined_rows==0`. **`✓`도 초록도 쓰지 않는다** |

> **`한계`와 `provisional`을 혼동하지 않는다.** `provisional`은 파라미터가 확정되면 값이 맞아진다. `한계`는 **이벤트가 추가되지 않으면 영원히 과소계상**이다. 다른 칩이어야 한다.

---

# C-3 · `SourceColumns` — 출처 2열

```
┌─────────────────────────┬─────────────────────────┐
│ ◼ 커머스 실측            │ ◇ 시뮬레이터 생성         │
│ [ConnectionState]       │ [ConnectionState]       │
│ [MetricCell …]          │ [MetricCell …]          │
└─────────────────────────┴─────────────────────────┘
```

| 규칙 | 내용 |
|---|---|
| **S-1 순서 불변** | 왼쪽 커머스 / 오른쪽 시뮬레이터. 세로 적층 시 커머스 위. **정렬·필터로 바뀌지 않는다** |
| **S-2 배지** | `◼ 실측` / `◇ 생성` — 글리프 + 문구, `--obs-source-ink`, **배경 없음** |
| **S-6 접기 금지** | 빈 열도 전폭 유지. 빈 커머스 열이 보여야 프로젝트 실제 상태가 보인다 |
| 폭 | 1:1 고정. 건수에 따라 폭을 바꾸지 않는다 |
| 적층 | 1024px 미만 세로 (`Plan/DESIGN.md` 대시보드 반응형) |
| 각주 | 출처 파생 근거 한 줄 (US-12 인수조건 3) |

## `ConnectionState` — 연결 상태 3종

| 상태 | 칩 | 문구 | C1 |
|---|---|---|---|
| `never_connected` | `unconnected` ○ | `아직 연결되지 않음` | **커머스·시뮬레이터 양쪽** |
| `connected` | `ok` ✓ | `수신 중` | 없음 |
| `stale` | `blocked` ⚠ | `수신 정지` | 없음 — **검증 불가** (M-3) |

`never_connected`에 `error`·`warning`을 쓰지 않는다 (**S-4**). 2026-09-11 현재 이것이 정상이다.

---

# C-4 · `VerdictBanner` — 판정 배너 (첫 화면)

```
[글리프] [판정 문구]                                    [이동 링크]
         [판정 근거 — 수치와 대상]
```

| 규칙 | 내용 |
|---|---|
| **F-1 정확히 하나** | 우선순위 7단계 중 최상위 하나만 (`ux-flow-map.md` §1.1) |
| **F-2 "정상" 조건** | 순위 1~6이 전부 비어 있을 때만 `ok` |
| **F-3 0건은 경고가 아니다** | `수집된 이벤트 0건`은 `unconnected`(info). `error`·`warning` 금지 |
| 근거 수치 | 문구에 **건수와 대상**을 포함. `문제가 있습니다` 같은 내용 없는 문구 금지 |
| 이동 | 해당 화면으로 가는 링크 동반 |
| 집계 주체 | **게시물이 집계해 준다** (`DB-012`). 화면이 세면 경계 위반 — 미확정 X-1 |
| 형태 | 전폭 · `rounded.lg` · 상태 배경 + ink · 글리프 20px |

---

# C-5 · `ImpactChain` — 결손 → 영향 사슬

```
⚠ unit_cost 미수신                              조치: Ecommerce #24
  → cogs · contribution_profit                  계산 불가
  → incremental_contribution_profit  [P1]       성립 불가
```

| 규칙 | 내용 |
|---|---|
| **2홉 제한** | 초과분은 `→ …` + 화면 링크. 3홉 이상은 읽히지 않는다 |
| **`[P1]`·`[G1]` 배지** | Primary·Guardrail이면 필수. `--obs-impact-*` 윤곽. **이 배지가 존재 이유다** |
| 정렬 | Primary·Guardrail 먼저 → `blocked` → `unconnected` → `planned` |
| 양방향 | V3는 결손→영향, V4는 영향←결손. **같은 데이터의 두 방향** (V-5.3) |
| 조치 | 필수 (V-8). 없으면 `조치 미정` |
| 데이터 | **게시물의 `affected_metrics` 인접 관계 필요.** 없으면 이 컴포넌트를 만들 수 없다 — 화면이 추론하면 `DB-012` 위반 |

---

# C-6 · `CoverageTable` — 표 (16종 매트릭스 · 필드 · 지표 · 품질 · Lock)

| 규칙 | 근거 |
|---|---|
| 텍스트 좌 · 수치 우(`tnum`) · 행 높이 44px | `Plan/DESIGN.md` |
| 좁아지면 **해당 영역만** 가로 스크롤. **열 숨김 금지** | `Plan/DESIGN.md` — *"중요 열을 임의로 숨기지 않습니다"* |
| 0건 행·결손 행을 **남긴다** | **V-0** |
| 정렬 기본값 | **고정 순서**(스키마·정본 표 순서). 건수 내림차순을 기본으로 쓰지 않는다 — 0건이 아래로 밀린다 |
| 결손 우선 정렬 | V3만 예외 — 충족률 오름차순(결손이 위) |
| 비율 셀 | **분모 동반** (V-2). 분모 0이면 `—` + `분모 0건` (V-4) |
| 각 셀 | `MetricCell` (`scale='table-number'`) |
| 구분선 | `colors.border` 1px. `Plan/DESIGN.md` — *"입력 가능 여부를 이 색만으로 표시하지 않음"* |

---

# C-8 · `NoticeBar` — 명시 가정·한계 (신설)

계약 **R-8**: *"`notices`를 화면에 표시한다. 가정을 숨기지 않는다."*
근거가 이 설계의 원칙과 같은 종류다 — **가정은 시간이 지나면 사실로 읽힌다.** 0을 채우지 않는 것과 같은 규율이다.

```
⚠ REFUND_NOT_ADJUSTED
  revenue 는 총매출이며 환불·취소를 차감하지 않습니다. 환불이 발생하는 환경에서는
  contribution_profit 이 과대평가됩니다.
  근거: economic-rule-v1.md §6 가정 A-REFUND
```

## 입력 계약

```
NoticeBar { notices: [{ code, level: 'assumption'|'limitation', message, reference? }] }
```

| `level` | 시각 상태 | 글리프 |
|---|---|---|
| `assumption` | `--obs-notice-assumption-*` (info) | **○** |
| `limitation` | `--obs-notice-limitation-*` (warning) | **⚠** |

| 규칙 | 내용 |
|---|---|
| 배치 | 해당 화면 상단, 판정 배너 **아래** · 사이클 고지와 **같은 층** |
| **접지 않는다** | **V-0.** "더 보기"·accordion·기본 필터 금지 |
| `code` 표시 | 사람이 읽는 `message`와 **함께** 코드 원문도 쓴다 — 추적 가능성 |
| `reference` | 함께 렌더한다 (`economic-rule-v1.md §6` 등) |
| **토스트·모달 금지** | `Plan/DESIGN.md`: *"성공 안내는 순간적인 토스트만으로 전달하지 않습니다"*. 가정 고지는 더더욱 |
| 개수 0건 | 컴포넌트를 렌더하지 않는다. **"가정 없음"이라고 쓰지 않는다** — 가정이 없다는 주장이 된다 |

**C1에서 항상 보이는 것:** `SINK_EMPTY`(limitation) · `REFUND_NOT_ADJUSTED`(assumption) · `CHURN_THRESHOLD_UNCONFIRMED`(assumption) · `GATE1_NOT_PASSED`(limitation).

---

# C-7 · `IngestionTimeline` — 수집 타임라인

| 요소 | 명세 |
|---|---|
| 형태 | **막대.** 선 차트를 쓰지 않는다 — 결손 구간에서 이어야 하고, 이으면 없는 값을 만든다 (V-5) |
| 계열 | 출처별 **두 줄** 분리. 한 줄에 겹치면 합산으로 읽힌다 |
| 색 | `--obs-chart-series`(= `primary`) 단일 계열. 10색 팔레트 배분 금지 |
| y축 | 0에서 시작 |
| **0건 날짜** | **막대 없음.** 1px 점선 윤곽 빈 슬롯 + baseline 틱 (`--obs-chart-gap-ink`) |
| **0건 날짜 문구** | `수집 0건 · 활동 없음과 수집 중단을 현재 데이터로 구분할 수 없습니다` (**V-6**) |
| 데이터 0건 | 축·슬롯을 그리지 않는다. `—` + `기준: 파티션 0개` |
| 레이블 | 축 레이블·데이터 표 병행 (`Plan/DESIGN.md` — *"차트는 레이블·선 모양을 병행"*) |
| 증감 | **없다** (V-11) |

> **"활동 없음"이라고 쓰지 않는다.** 관측하지 않은 것을 단정하는 것은 0 채우기와 같은 종류의 잘못이다 (V-6).

---

# 공통 — 상호작용·접근성

| 항목 | 명세 | 근거 |
|---|---|---|
| 포커스 | `focus` 2px 외곽선 + 2px 간격. 호버와 독립 | `Plan/DESIGN.md` |
| 비활성 (사이드바 결과 8항목) | `button-disabled` 색 + **실제 비활성 동작** + **사유 문구** | `Plan/DESIGN.md` · `ux-flow-map.md` §2.2 |
| 전환 | 120ms ease-out. `prefers-reduced-motion`에서 제거 | `Plan/DESIGN.md` |
| 스켈레톤 | **실제 데이터 요청이 있을 때만.** 파일 읽기는 즉시 끝난다 — 남용하지 않는다 | `Plan/DESIGN.md` |
| 글리프 접근성 | 전부 `aria-label`. 아이콘 단독 전달 금지 | `Plan/DESIGN.md` |
| 200% 확대 | 겹침·잘림·조작 불가 없음. 칩 줄바꿈, 고정 높이 금지 | `Plan/DESIGN.md` |
| 새로고침 | 수동 버튼 1개(`button-secondary`). 자동 폴링 없음 | `DB-011` |

---

# 만들지 않는 컴포넌트

| 없음 | 근거 |
|---|---|
| 이벤트 행 목록·검색·필터 | `usp.md` §1.7 A5 — 이벤트 브라우저는 C1 범위 밖 |
| 기간 필터·날짜 선택 | 단일 스냅샷. 기간 축이 없다 |
| 임계 입력·경보 토글 | `ui-spec.md` §7.3 — 작동하지 않는 컨트롤을 두지 않는다 |
| 증감 배지·스파크라인·델타 | V-11 |
| 다크 모드 토글 | `Plan/DESIGN.md` 라이트 고정 |
| 빈 상태 일러스트 | 이벤트 0건을 빈 상태로 **대체하지 않는다** (`ux-flow-map.md` §4.3) |
| 토스트 | `Plan/DESIGN.md` — *"성공 안내는 순간적인 토스트만으로 전달하지 않습니다"* |
