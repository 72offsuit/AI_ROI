# 게시물 계약 ↔ UX Flow 대조 — 협업 불변식 정합 결과

**작성** Jonnathan (Role 7) · 2026-09-11 · 사이클 **C1**
**대상** James `04-architecture/api-contracts.md` (T2.7) · `schemas/*.schema.json` · `examples/empty-sink/` 7건
**대조 방식** 내 `ux-flow-map.md` §5.1 요구 14행 + 추가 요청 4건(Y-1~Y-4) ↔ 계약 본문·스키마·예시를 줄 단위로 대조. **예시 7건을 읽어 실제 값 형태를 확인했다.**

> ### 2차 개정 (2026-09-11, 계약 개정 1 수신 후) — **요청 3건이 전부 해소됐다**
>
> | 1차 요청 | 계약 개정 1 |
> |---|---|
> | **`blocks_metrics`** 결손→영향 | **충족 · 요청보다 넓다.** 양방향 — `fields[f].affected_metrics` · `schema_gaps[].affected_metrics` · `metrics[].value.blocked_by`(**`kind` 9종**) · `metrics[].blocks` |
> | **`index.json.verdict`** 판정 집계 | **충족.** `level` 3값 · `headline_code` **7종** · `counts` 8개. 문구는 화면이 매핑 |
> | 출처 **`link_state`** | **조건부 충족.** `sources[s].state` **2값**(`never_observed`/`observed`) — **`stale`을 뺐다.** §2.4에서 수용 판단 |
> | Y-1 스키마 공백 목록 | **충족.** `schema_gaps[]` 4건 (`unit_cost`·**`discount`**·`shipping_fee`·`refund`) |
> | Y-2 품질 검사 정본 목록 | **충족.** `spec_coverage.spec_items[]` + `unmapped_spec_items[]` |
>
> **그리고 계약이 내 설계의 핵심을 구조로 만들었다 — §1.3.**
> **남은 미해결은 X-5(수집 공백 구분) 하나뿐이고, 그것은 계약으로 풀 수 없는 것이다.** 새로 발견한 빈틈 1건은 §2.5.

> **1차 결론 (기록) — 17개 요청 중 13개 충족, 3개 미해결, 1개 양보.** 화면 쪽 변경 6건은 §3에 있다.

---

# 1. 충족된 것 — 내가 요청한 것보다 강한 것 포함

| 내 요청 | 계약 | 비고 |
|---|---|---|
| `state` 4값 이상, **`not_run`을 `unavailable`과 합치지 말 것** | `status` **5값** — `ok`·`unconfirmed`·`unavailable`·`blocked`·`not_run` | **내 요구보다 강하다.** `blocked`(환경 제약)와 `not_run`(안 했다)를 계약이 직접 가른다 |
| `reason` 7종 **코드로** | 7종 + `NOT_RUN` · `PRECONDITION_MISSING` **제안** | 내 §1.4가 "사유 코드가 없다"로 남긴 공백을 `NOT_RUN`이 채운다. **계약이 9종으로 확정 — D-15 해소** |
| `reason_detail` | 계산 불가에 **필수** (스키마 강제) | — |
| `derived: true` | `derivation`(유도 규칙) **필수** | 내 요청보다 강하다 — 유도 규칙 자체가 온다 |
| `params_used` | `unconfirmed` → `params` **필수** | — |
| **기준(basis)** | `denominator` · `population` · `window` · `denominator_definition` · `formula` · `definition_ref` | **훨씬 강하다.** 정의와 값이 같은 자리에 온다 |
| 0건 `event_type`도 키 | `minProperties: 16` **스키마 강제** | 규칙 **V-0**이 스키마로 강제된다 |
| 22개 필드 전부 | `minProperties: 22` · `maxProperties: 22` | 동일 |
| 일자별 **날짜 목록** | `partitions[]` + `present: false` | 동일 |
| 출처별 두 키 항상 존재 | `by_source.{commerce,simulator}` — 0건이어도 키 유지 | 동일 |
| 합산 금지 | KPI 계층 `combined` **스키마 거부** | 내 R-7/S-3이 스키마로 강제된다 |
| `PARTIAL` 범위 한정 문구 (Y-3) | `scope_note` **필수** (Lock 9종 전부) | — |
| 게시물 스키마 버전 | `contract_version` + **불일치 시 렌더 거부**(R-6) · `run_id` 대조 | 내 요청보다 강하다 |
| 생성 명령 (B-4) | **아직 존재하지 않음을 계약이 명시** + *"게시가 필요하다"* 안내로만 쓰라는 지침 | **차단이 해소된 게 아니라 정직하게 고정됐다.** 아래 §3-⑥ |
| 품질 검사 정본 목록 (Y-2) | 18건이 게시물에 전부 온다 (`not_run` 포함) | **화면이 상수 목록을 들 필요가 없어졌다.** 내 ui-spec §6.1 우려 해소 |

## 1.3 ★ 계약 개정 1이 내 설계를 **구조로** 만든 것 — `basis` 양방향 강제

내가 규칙 V-2·V-3으로 **화면 규율**로 적은 것을 James가 **스키마 제약**으로 올렸다.

```
status 가 ok · unconfirmed             → basis 필수
status 가 unavailable/blocked/not_run → basis 금지   (not: {required: ["basis"]})
```

**두 번째 줄이 결정적이다.** 계산 불가에는 `basis`를 **붙일 수 없다.** 그래서:

> **`—`는 정의상 기준을 가질 수 없다** — 내가 V-2에서 *"기준의 유무가 측정됨의 판별자"* 라고 쓴 것이 **구조적 사실**이 됐다. 화면의 판별이 관례가 아니라 스키마에서 나온다.

실행 확인(James):
```
거부됨 ✅ ★ 계산된 값에 기준(basis)이 없다
거부됨 ✅ ★ 계산 불가인데 기준(basis)을 붙인다
```

그리고 **내 규칙 V-3(기준 없는 값 → `계약 위반` 칩)이 계약 R-10으로 명시됐다** — *"읽는 쪽이 계약을 검사하는 것이 마지막 방어선"*. `DB-012` 해석 논쟁이 끝났다.

`basis`가 담는 것: `population` · `denominator_definition` · `denominator` · **`observed_count`** · `window` · **`excluded_count`** · **`excluded_reason`**.
→ `kpi-definition-v1.md` **R-6**(제외 인원을 값과 함께 보고)가 필드로 강제된다. 픽스처의 `purchase_interval`이 `denominator: 312` · `observed_count: 894` · `excluded_count: 582` · 제외 사유를 함께 준다.

## 1.1 ★ 가장 중요한 일치 — "세어 보니 0"

James §4.3이 내 규칙 **V-2**와 **독립적으로 같은 결론**에 도달했다.

| | 내 V-2 | James §4.3 |
|---|---|---|
| 이벤트 0건 | `0` + 기준 | `{"status":"ok","value":0}` |
| 분모 0인 비율 | `—` + `분모 0건` (**V-4**) | `{"status":"unavailable","denominator":0}` — **`denominator==0`이면 `ok`일 수 없다고 스키마가 거부** |
| 매출 (purchase 0건) | `—` | `unavailable` + `NO_SOURCE_EVENT` |

> **내 V-4("분모 0인 비율에 0%를 쓰지 않는다")가 스키마 제약으로 강제된다.** 화면이 실수할 경로가 닫혔다.

## 1.2 내 명세가 틀렸던 것 — James가 맞다

**V2 거부 샘플.** 내 `ui-spec.md` §3은 샘플을 *"사유 + 필드명 + 받은 값의 타입/형태"* 로 쓰고 예시에 `category="우주선"`처럼 **값을 넣었다.**

James의 보안 판정: `rejected.jsonl`에 **Hidden Trait·τ·Potential Outcome이 담긴 레코드가 원문으로 남는다**(`sink.py:203-206`). 값을 `results/`로 옮기면 **금지 필드가 대시보드까지 도달하는 경로**가 생긴다 — `ISO-003`·`NFR-002` 우회.

> **내 명세를 고친다: 샘플은 `offending_fields`(필드 **이름**만)를 쓰고 값을 일절 렌더링하지 않는다.**
> 거부 사유를 이해하기에 필드 이름으로 충분하고, 충분하지 않더라도 **누수 경로를 열 근거는 되지 않는다.** `additionalProperties:false`가 강제한다.

---

# 2.4 `stale` 미도입 — 수용. 그리고 **화면 쪽 귀결이 하나 있다**

James가 `sources[s].state`를 **2값**(`never_observed`/`observed`)으로 두고 `stale`을 뺐다. 근거: ⑴ *"멈췄다"* 판정에 임계값이 필요하고 그 임계값이 미확정이다 ⑵ **C1에서 도달할 수 없어 검증도 불가능한 분기를 계약에 넣으면 화면이 영원히 실행되지 않는 코드를 갖는다** ⑶ 대신 `first_event_at`·`last_event_at`을 주고 오래됐는지는 사람이 본다.

> **수용한다.** ⑵가 결정적이다 — 내 `design-handoff.md` M-3이 이미 `stale`을 *"구현하되 C1에서 검증 불가"* 로 한계 표시해 두었는데, **검증 못 하는 분기를 만드는 것 자체가 비용**이다. 그리고 ⑶은 내가 X-5(수집 공백)에서 취한 태도와 같다 — **데이터가 말해주지 않는 것을 화면이 단정하지 않는다.**
> **연결 상태를 3종 → 2종으로 줄인다.** `stale`은 `inconclusive`와 같은 **예약 슬롯**으로만 남기고 토큰도 만들지 않는다.

## ★ 귀결 — `observed`에 건강 판정 문구를 쓰지 않는다 (규칙 S-4 개정)

`observed`는 **"지금 수신 중"과 "예전에 받았고 끊겼다"를 모두 포함한다.** 픽스처가 그 형태다 — `state: "observed"` · `last_event_at: 2026-09-18T13:58:02+09:00`.

개정 전 내 명세는 `connected`에 **`✓ 수신 중`**(success)을 붙였다. **그건 건강 판정이고, 2값 상태로는 그 판정을 할 수 없다.**

> **확정 — `observed`는 사실만 쓴다. `success` 토큰을 쓰지 않는다.**
>
> | 상태 | 칩 | 같이 쓰는 사실 |
> |---|---|---|
> | `never_observed` | `unconnected` ○ **`아직 관측되지 않음`** | `첫 수신 —` · `마지막 수신 —` |
> | `observed` | **칩 없음** (상태가 아니라 사실이다) | **`마지막 수신 2026-09-18 13:58 KST`** · `첫 수신 …` · `건수 18,430` |
>
> `observed`에 칩을 붙이지 않는 이유: 칩은 **판정**의 표기이고, 여기서 화면이 할 수 있는 것은 **시각을 보여주는 것**뿐이다. `✓`를 붙이면 "건강하다"로 읽히고, `⚠`를 붙이면 "멈췄다"로 읽힌다. **둘 다 화면이 알 수 없다.**
> → 오래됐는지는 사람이 본다. 이것이 "관측하지 않은 것을 단정하지 않는다"의 같은 적용이다.

# 2.5 ★ 새로 발견한 빈틈 — `rejected_events`에 대응하는 `headline_code`가 없다

`verdict.counts`에 **`rejected_events`가 있는데** `headline_code` 7종(`QUALITY_VIOLATION`·`FREEZE_MISMATCH`·`CONTRACT_VIOLATION`·`CHECKS_NOT_RUN`·`SINK_EMPTY`·`METRICS_UNAVAILABLE`·`ALL_CLEAR`)에 **거부를 지목하는 코드가 없다.**

**깨지는 경우:** 품질 검사 전건 통과 · 봉인 정상 · 지표 계산됨 · **그런데 거부 217건.** 게시 계층이 고를 수 있는 코드가 `ALL_CLEAR` 뿐이고, **거부 217건을 "전부 정상"으로 띄운다.**

`CONTRACT_VIOLATION`이 그것을 덮을 수도 있는데 **이름이 두 가지로 읽힌다:**

| 읽는 방식 | 뜻 | 조치 주체 |
|---|---|---|
| 이벤트 계약 위반 | 생산자가 잘못된 이벤트를 보냈다 (`validate_event()` 거부) | **커머스·시뮬레이터** |
| 게시 계약 위반 | 게시물이 스키마를 어겼다 · `contract_version` 불일치 | **우리 파이프라인** |

**조치 주체가 다르다.** 이것은 James 자신이 `blocked_by[].kind` 9종으로 *"필드가 비었다 / 컬럼이 없다 / 테이블이 없다는 해결 주체가 다르다"* 고 가른 것과 **같은 종류의 구분**이다. 같은 원칙을 여기에도 적용해야 한다.

→ **요청: `REJECTED_EVENTS`를 신설하거나, `CONTRACT_VIOLATION`이 둘 중 무엇인지 계약에 한 줄로 고정한다.** 화면은 코드에서 문구를 매핑하므로 **코드가 모호하면 문구가 거짓이 된다.**

# 2. ★ 없는 것 3건 — James에게 요청 *(1차. 전부 해소됨 — 위 2차 개정 참조)*

## 2.1 요청 1 (최우선) · 결손 → 영향 인접 관계

**grep 결과 계약·스키마·예시 어디에도 없다.** 내 설계에서 다음이 전부 막힌다:
첫 화면 ⑨ 결손→영향 패널 · V3 영향 열 · V4 영향 열(역방향) · `ImpactChain` 컴포넌트 전체 (`missing-state-spec.md` §5).

**대체 경로를 찾아봤고, 전부 `DB-012` 위반이다:**

| 후보 | 왜 안 되는가 |
|---|---|
| `kpi_report.metrics[].source_events` (예: `revenue ← purchase`) | 지표→이벤트다. 내가 필요한 것은 **필드→지표** (`unit_cost` → `cogs`) |
| `field_coverage_report.fields[].applicable_event_types` | 필드→이벤트타입. 위와 조인하면 필드→지표가 나오지만 **그 조인이 새 분류이고 R-2 위반**이다 |
| `formula` 문자열 파싱 (`"revenue - cogs - coupon_cost - ..."`) | 화면이 수식을 파싱해 의존 그래프를 만드는 것 — 명백히 계산이고 깨지기 쉽다 |

> ### 필요한 최소 형태 — 배열 하나
> `field_coverage_report.fields[<name>]`에 **`blocks_metrics: ["cogs", "contribution_profit"]`**.
>
> 역방향(V4의 "왜 안 나오나")은 화면이 이 배열을 뒤집어 인덱스만 만들면 된다 — **같은 데이터의 재배열이지 새 분류가 아니다.** 그 경계는 내가 지킬 수 있다.
>
> **`[P1]` 배지는 추가 필드가 필요 없다.** `kpi_report.metrics[].role`이 이미 있다(현재 `"none"`). `role`이 `primary`/`guardrail`이면 배지를 붙인다.

**없을 때의 차선:** 영향 사슬 없이 결손 목록만 그린다. 그러면 Caleb T1.9 권고 4(*"결손을 숫자로 끝내지 말고 영향받는 하위 지표를 명시"*)를 충족하지 못하고, **"`unit_cost` 하나가 Primary `P1`을 무너뜨린다"는 이 프로젝트의 가장 중요한 한 문장이 화면에서 사라진다.**

## 2.2 요청 2 · `index.json`에 판정 집계

**내가 양보한 전제:** James의 *"화면 하나 = 게시물 하나"* 는 옳다. 내 첫 화면이 4~5개 게시물을 읽는 구조였고, **내가 고친다**(§3-①).

**남는 문제:** 첫 화면 판정 배너가 *"이벤트가 제대로 쌓이고 있는가"* 에 한 줄로 답해야 하는데(charter §7.1 "즉시 발견"), `index.json`에는 **산출물 간 집계가 없다.** `publish_result`·`notices`·`provenance`·`artifacts[]`·`views{}` 뿐이다.

화면이 6개 게시물을 열어 세면 **R-2 위반이다 — "합계를 새로 만들지 않는다". 단순 합산도 계산이다.**

> ### 필요한 최소 형태 — `index.json`에 블록 하나
> ```jsonc
> "verdict": {
>   "level": "unconnected",            // ok | unconnected | blocked | not_run | violation
>   "headline_code": "SINK_EMPTY",
>   "counts": { "rejected": 0, "quality_fail": 0, "quality_not_run": 2,
>               "quality_blocked": 3, "kpi_unavailable": 12, "kpi_blocked": 0,
>               "freeze_not_run": 9, "missing_fields": 22 }
> }
> ```
> 값은 이미 각 산출물이 들고 있다(`kpi_report.summary` · `data_quality_report.checks[].status` · `freeze_status.items[]`). **게시 시점에 합치는 것이고 새 계산이 아니다.**
>
> `headline_code`까지 게시물이 정해 주면 **화면은 우선순위 판정조차 하지 않는다.** 그게 `DB-012`에 가장 충실하다. 다만 우선순위 정책을 게시 계층에 두는 것이 맞는지는 당신 판단이다 — **`counts`만 주고 순위는 내가 화면에서 정하는 것도 받아들인다**(순위 7단계는 `ux-flow-map.md` §1.1에 적혀 있다).

## 2.3 요청 3 · 출처별 연결 상태

`ingestion_report.totals.events_ingested.by_source.commerce = {"status":"ok","value":0}`.
**이것만으로는 "아직 연결 안 됨(정상)"과 "수신하다 멈춤(이상)"이 구분되지 않는다.** 둘 다 0입니다.

charter·리드 지시가 *"커머스 0건을 오류로 보이게 하지 말고 '아직 연결 안 됨'으로 구분해 표현"* 을 요구한다. 화면이 "첫 수신이 null이면 미연결"로 판정하면 **분류를 새로 만드는 것이고 R-2 경계에 닿는다.**

> ### 필요한 최소 형태
> ```jsonc
> "sources": {
>   "commerce":  { "link_state": "never_connected", "first_event_at": null, "last_event_at": null },
>   "simulator": { "link_state": "never_connected", "first_event_at": null, "last_event_at": null }
> }
> ```
> `link_state`: `never_connected` | `connected` | `stale`.
> **C1에 `connected`·`stale`은 나타날 수 없으므로 검증되지 않는다** — 그 한계는 내가 `design-handoff.md`에 적었다. 그래도 `never_connected`가 **계약에 명시돼야** 화면이 "정상"과 "이상"을 판정 없이 그릴 수 있다.

---

# 3. 내가 고치는 것 — 화면 쪽 변경 6건

## ① 첫 화면 구조를 바꾼다 — 1:1 불변식을 지킨다

**James가 옳다.** 내 `/`가 4~5개 게시물을 읽었다. 라우트도 그의 것을 채택한다 — 산출물 이름과 1:1이라 불변식이 읽히고, `views.route`가 기계가독이므로 이름 일치가 실질적 가치가 있다.

| | 이전 (내 안) | **확정** |
|---|---|---|
| `/` | 수집 상태 전체 (게시물 4~5개) | **인덱스** — `index.json` **하나만** |
| `/ingestion` | (없음 — `/`가 겸함) | V1 수집 현황 — `ingestion_report` |
| `/rejections` | `/rejections` | 동일 |
| `/coverage` | `/fields` | **James 이름 채택** |
| `/kpi` | `/metrics` | **James 이름 채택** |
| `/quality` | `/quality` | 동일 |
| `/freeze` | `/seal` | **James 이름 채택** |
| `/triggers` | `/triggers` | **유지 — 게시물 없음(정적)**. §3-⑤ |

**새 `/` 구성** (게시물 하나만 읽는다):
① 제목 → ② 게시물 신원(`provenance`) → ③ **판정 배너**(`verdict` — 요청 2) → ④ 사이클 고지 → ⑤ **`notices[]`**(신설, §3-②) → ⑥ **화면 6개 진입 카드**(각 카드에 해당 산출물의 상태 요약 + `publish_result`) → ⑦ **결손→영향**(요청 1 충족 시. 아니면 `/coverage`로 이동) → ⑧ 수동 새로고침

**잃는 것:** 출처 2열·타임라인·16종 매트릭스가 한 스크롤 아래(`/ingestion`)로 내려간다. **받아들인다** — 첫 화면은 판정이고 분해는 다음 화면이다(`ux-flow-map.md` §1.1의 원래 취지와 더 일치한다).
**얻는 것:** `run_id` 대조가 한 곳에서 끝난다. `/`가 인덱스를 읽고 불일치면 **거기서 멈춘다** — 6개 화면이 각자 대조할 필요가 없다.

## ② `NoticeBar` 컴포넌트 신설 — 내 설계에 없었던 것

R-8: *"`notices`를 화면에 표시한다. 가정을 숨기지 않는다."* **내 컴포넌트 7개에 없었다. 추가한다(8개).**

James의 근거가 내 설계 원칙과 같다 — *"가정은 시간이 지나면 사실로 읽힌다."* 0을 채우지 않는 것과 같은 종류의 규율이다.

| `level` | 시각 상태 | 배치 |
|---|---|---|
| `assumption` | `unconnected`(info) + 글리프 ○ | 해당 화면 상단, 판정 배너 **아래** |
| `limitation` | `gap`(warning) + 글리프 ⚠ | 동일 |

- **접지 않는다**(V-0). `REFUND_NOT_ADJUSTED`가 첫 화면과 `/kpi`에 항상 보인다 — 환불 미차감이 `contribution_profit`을 과대평가한다는 가정이다
- `reference`를 함께 렌더한다 (`economic-rule-v1.md §6` 등)
- **토스트·모달을 쓰지 않는다** (`Plan/DESIGN.md`: *"성공 안내는 순간적인 토스트만으로 전달하지 않습니다"* — 가정 고지는 더더욱)

## ③ 상태 어휘 8종을 계약 5상태에서 **파생**시킨다 — 이름 충돌 해소

**문제: `blocked`라는 단어가 두 의미로 쓰인다.** James의 `status:"blocked"`는 **환경 제약**(pyarrow)이고, 내 시각 상태 `blocked`는 `NO_COST_BASIS`+`MISSING_FIELD`+`BLOCKED` 묶음이었다. **Andrew가 두 문서를 읽으면 혼동한다.**

그리고 James의 표가 *"`unavailable`은 0과 다른 시각 상태 / `blocked`는 **위와 또 다른 상태여야 함**"* 을 요구한다 — **내 설계는 둘을 같은 `warning` 채움으로 묶었다. 실제 불일치다.**

> ### 확정 — 시각 상태는 `(status, reason_code)`에서 기계적으로 파생된다
>
> | 계약 `status` | `reason_code` | **시각 상태 (개정)** | 글리프 | 색 · 형태 |
> |---|---|---|---|---|
> | `ok` | — | `measured` | 없음 | 숫자 `text` · 기준 문구 |
> | `unconfirmed` | `PARAM_UNCONFIRMED` | `provisional` | **◐** | `warning` · **실선 윤곽** |
> | `unavailable` | `NEEDS_TWO_STRATEGIES` · `NEEDS_MODEL_OUTPUT` · `PRECONDITION_MISSING` | `planned` | **·** | `text-muted` / `surface-muted` 채움 |
> | `unavailable` | `NO_SOURCE_EVENT` | `unconnected` | **○** | `info` / `info-surface` 채움 |
> | `unavailable` | `NO_COST_BASIS` · `MISSING_FIELD` | **`gap`** ← 개정 | **⚠** | `warning` / `warning-surface` **채움** |
> | `blocked` | `BLOCKED` | **`env_blocked`** ← 신설 | **⊘** | `warning` · **점선 윤곽** |
> | `not_run` | `NOT_RUN` | `not_run` | **?** | `error` · 실선 윤곽 |
> | (화면 검사) | — | `violation` | **✕** | `error` / `error-surface` 채움 |
>
> **`blocked` → `gap`으로 개명한다.** 계약의 `blocked`와 겹치지 않게 하고, 의미(*"근거의 공백, 조치 필요"*)에 더 정확하다.
> **`env_blocked`를 신설한다.** `gap`과 같은 `warning` 색이지만 **점선 윤곽 + ⊘ 글리프**로 가른다. `provisional`도 `warning` 윤곽이지만 **실선**이고 무엇보다 **값 슬롯에 숫자가 있다** — `env_blocked`는 `—`다. 값 슬롯 + 선 종류 + 글리프 3중으로 구분된다.
> **`PRECONDITION_MISSING`을 `planned`에 넣는다** — 6테이블 미구현·시뮬레이터 부재·`data_version` null은 전부 "이후 사이클"이다. 조치 대상이 아니다.

새 색값은 여전히 **0건**이다 (점선은 `border-style`).

## ④ ★ `examined_rows: 0`인 `pass`를 통과로 그리지 않는다 — 예시를 읽다 발견

`examples/empty-sink/data_quality_report.json`:
```jsonc
{ "id":"DQ-01", "title":"event_id 전역 유일", "status":"pass", "violations":0, "examined_rows":0,
  "scope":"… 오늘은 0행이므로 위반이 없는 것이 아니라 검사 대상이 없다 — examined_rows 를 함께 읽어야 한다." }
```

**`status`는 `pass`다. 순진하게 구현하면 초록 ✓ PASS로 그려진다.** 아무것도 검사하지 않았는데.
`scope`가 산문으로 경고하지만 **산문은 색을 이기지 못한다.** 이것은 "미실행을 통과로 표시"의 한 층 아래 변종이다 — **"검사했지만 아무것도 검사하지 않았다."**

> ### 규칙 V-12 (신설) — 공허한 통과
> **`status == "pass"` 이고 `examined_rows == 0` 이면 `measured`로 그리지 않는다.**
> `unconnected`(info) + 문구 **`공허한 통과 · 검사 대상 0행`** + `scope` 인라인.
> **`✓`도 초록도 쓰지 않는다.**
>
> `gate_result`가 이미 `incomplete`라 게이트 수준은 정직하다. 이 규칙은 **개별 검사 행**을 고친다. `DB-012` 위반이 아니다 — 판정하지 않고 게시물이 준 두 필드를 같이 읽을 뿐이다.

**`gate_result` 3값도 명세에 추가한다:** `pass`(success) / `fail`(violation) / **`incomplete`(gap — warning)**. `incomplete`에 **`success` 토큰을 일절 쓰지 않고, "통과"라는 단어를 단독으로 쓰지 않는다.** 문구는 `미완 · 통과 N / 미실행 M / 차단 K`.

## ⑤ V6를 두 축으로 분리 · `/triggers`는 정적

**V6 봉인:** 내 ui-spec이 Lock 상태와 해시 대조를 뒤섞었다. 계약은 두 축이다 — **고친다.**
- `items[].status`: `LOCKED`/`PARTIAL`/`PENDING`/`BLOCKED`/**`OUT_OF_SCOPE`**(내가 몰랐던 5번째)
- `items[].canonical_files[].verification`: `match`/`mismatch`/`missing`/**`not_run`**
- `overall`: `not_started`/`partial`/`sealed`/`violated` — **C1 도달 최대치는 `partial`**, 현재 예시는 `not_started`
- Lock 9종 전부 행으로, `scope_note` 필수, `verification: not_run`은 **통과가 아니다**

**`/triggers`(T2.16):** 게시물이 없다 → 1:1 불변식의 예외다. **C1에서 정적으로 둔다** — §71 5종과 각 차단 사유는 C1에 고정이고, 화면이 계산하는 것도 없다. `index.json.views`에 넣을지는 James 판단(§4 Y-4). **게시물 없는 화면이라는 사실을 `views`에 남기는 편이 불변식 검사에 정직하다고 본다.**

## ⑥ 빈 상태 안내 — 차단이 풀린 것이 아니라 정직하게 고정됐다

계약이 명령(`python3 -m src.measurement.publish --source data/raw --out results`)을 적었지만 *"**2026-09-11 현재 이 명령은 실행할 수 없다**"* 고 명시했고, *"빈 상태 안내에 표시할 때도 **'게시가 필요하다'는 안내로만** 쓴다"* 고 지침을 주었다.

> **화면 문구 확정:**
> ```
> ○ 게시물이 없습니다
>   측정 계층이 아직 산출물을 게시하지 않았습니다. 게시가 필요합니다.
>   게시 명령은 W5-A 에서 신설됩니다 — 2026-09-11 현재 실행할 수 없습니다.
> ```
> **명령 문자열을 실행 가능한 것처럼 제시하지 않는다.** AGENTS.md와 `DB-013`을 동시에 만족하는 유일한 형태다.
> `docs/gate1_checklist.md`에는 **`DB-013` 부분 충족**으로 남긴다 — 안내는 하지만 실행 가능한 명령을 주지는 못한다.

---

# 4. James 회신 대기 항목 (업데이트)

| # | 항목 | 상태 |
|---|---|---|
| **요청 1** | `blocks_metrics` 인접 관계 | **미해결 · 최우선.** 없으면 `ImpactChain` 전체 불가 |
| **요청 2** | `index.json.verdict` 집계 | **미해결.** 없으면 판정 배너가 R-2를 위반하거나 사라진다 |
| **요청 3** | `sources[].link_state` | **미해결.** 없으면 "미연결 vs 정지"를 화면이 판정(R-2 경계) |
| Y-1 | 스키마에 없는 필드 목록(배송비·`discount`) | **부분 — 계약 §8이 `discount` 공백을 새로 발견했다.** `field_coverage_report.fields`는 22개 고정이라 **없는 컬럼은 들어갈 자리가 없다.** 별도 배열이 필요하다 |
| Y-2 | 품질 검사 정본 목록 | **해결** — 18건이 게시물에 온다 |
| Y-3 | `scope_note` | **해결** — 필수 |
| Y-4 | `/triggers` 게시물 | 내 제안: 정적 + `views`에는 기록 |
| ~~D-15~~ | `NOT_RUN`·`PRECONDITION_MISSING` 2종 | **해소 (리드 판정, 2026-09-11).** 계약이 **9종으로 확정**했다. Joshua는 W2 1단계 후 종료되어 확인받을 수 없고, **어휘 정본이 기획 문서에서 계약으로 옮겨갔다** — `design-handoff.md` §0.0. **§3-③ 파생표 수정 불필요** |
| **신규** | `headline_code`에 `rejected_events` 대응 코드 부재 (§2.5) | **James 미해결.** 리드가 `REJECTED_EVENTS` 신설 + 우선순위 계약 명시를 지시 |

---

# 5. 이 대조로 바뀌지 않은 것

- 규칙 **V-0**(숨기지·접지 않는다) · **V-1**(`—`를 흐리게 만들지 않는다) · **V-2**(기준이 측정됨의 증거) · **V-3**(화면이 자기 입력을 검사) · **V-9**(사유 상시 인라인) · **V-11**(증감 금지)
- **USP-1 대표 장면** — 계약의 `revenue`(`NO_SOURCE_EVENT`)와 `contribution_profit`(**`NO_COST_BASIS`**)이 예시에 이미 다른 사유 코드로 들어 있다. **대표 장면이 계약 수준에서 성립한다.** 단 커머스 주문이 들어와야 `revenue`에 값이 뜨므로 **fixture 판정(리드 J-1)은 그대로 남는다**
- **출처는 색이 아니라 위치** (S-1~S-6)
- **§71 트리거 C1 작동 0종** — 계약에 게시물 이력이 없어 확인됐다. `↑`/`↓`를 그릴 근거가 없다
- 토큰 전략 — James가 독립적으로 같은 결론(복제 가능, `Plan` SHA 동일)에 도달했다
