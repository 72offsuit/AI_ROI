# 게시 계약 변경 이력 — `measurement-publish/v1`

> **이 디렉터리가 W5 이후의 정본이다.**
> `.agent-team/04-architecture/schemas/` 는 **동결 스냅샷**이며 고치지 않는다. 두 벌이 조용히 갈라지는 것을 막기 위해 `tests/test_publish_contract.py` 의 `TestContractCopyDiffersOnlyAsDocumented` 가 **아래 등재되지 않은 차이가 생기면 실패**한다.
>
> JSON 에 주석을 쓸 수 없으므로 각 파일 최상위 **`$comment`** 에 원본 경로를 적었다 (N-7).

**스냅샷 기준** `.agent-team/04-architecture/schemas/` · W2 산출물 (2026-09-11 동결)
**변경자** Phillip (Role 8 · W5-A) · 2026-09-11 · 스토리 M-06 T1

---

## 원칙 — 왜 계약을 고치고 화면을 우회하지 않았나

| # | 원칙 |
|---|---|
| **P-1** | **화면이 계약의 공백을 메우지 않는다.** 계약에 없는 것을 화면이 만들면 규칙이 두 곳에 살고 갈라진다 (`DB-012`) |
| **P-2** | **기존 `not`·`required`·`if/then` 을 건드리는 수정은 "추가"가 아니라 "회귀"로 취급한다.** 수정 전 거부되던 레코드를 먼저 목록으로 만들고, 수정 후에도 거부되는지 본다 |
| **P-3** | **읽어서 판단하지 않는다.** 네 수정 전부 `jsonschema 4.26.0` 으로 수정 전/후를 돌려 확인했다 (AC-4d·AC-4e) |
| **P-4** | **픽스처를 고치지 않는다.** 픽스처가 실패하면 그 실패를 **의도된 실패 목록**에 등재한다 — 제약을 빼지 않는다 |

---

## 변경 4건

### FIX-1 · `index.schema.json` — `headline_code` 7종 → 8종 (B-11)

**근거** 리드 판정 2026-09-11 · `.agent-team/03-story-engineering/story-m-06-publish-kr.md` §4.8

| | |
|---|---|
| **문제** | 수집 거부가 발생했는데 그것을 말할 코드가 enum 에 없었다. 화면이 `counts` 를 다시 세어 판단하는 우회로 갈 수밖에 없었다 |
| **변경** | `REJECTED_EVENTS` 추가 · **8종 우선순위를 `description` 에 명시** · 최상위 `allOf` 에 **`counts.rejected_events > 0` 이면 `ALL_CLEAR` 금지** 가드 추가 |
| **왜 계약인가** | 순위를 화면이 정하면 화면마다 다른 최상위가 나온다. 구현은 `publish.choose_headline_code()` 한 곳이다 |

```
우선순위  1 CONTRACT_VIOLATION > 2 FREEZE_MISMATCH > 3 QUALITY_VIOLATION
        > 4 REJECTED_EVENTS   > 5 SINK_EMPTY      > 6 CHECKS_NOT_RUN
        > 7 METRICS_UNAVAILABLE > 8 ALL_CLEAR
```

**`SINK_EMPTY` 의 입력은 `ingestion_report.totals.events_ingested`** 이며(`verdict.counts` 에 수집 건수가 없다 — 실측), 그 `status` 가 `ok` 가 아니면 `SINK_EMPTY` 를 고르지 않는다. **모르는 것을 0 으로 읽지 않는다.**

---

### FIX-2 · `common.schema.json` — `metric_value.value_formatted` 추가 (C-1)

**근거** Thomas C-1 · 리드 판정 2026-09-11 · 스토리 §4.16

| | |
|---|---|
| **문제** | 디자인 문서가 `m.status === 'ok' ? m.value_formatted : EM_DASH` 를 올바른 화면 형태로 제시했는데 **그 필드가 계약에 없었다.** `additionalProperties: false` 라 추가도 불가능했다 |
| **결과** | 그대로 구현하면 모든 `ok` 지표가 `undefined` → 구현자는 `m.value.toLocaleString()` 로 가고 → `null` 예외를 막으려 **`?? 0`** 을 쓴다. **경고문 자신이 그 경로를 열고 있었다** |
| **변경** | ① `properties.value_formatted` 추가 ② `allOf[0].then.required`(`ok`) 에 추가 ③ `allOf[1].then.required`(`unconfirmed`) 에 추가 ④ **`allOf[2].then.not` 을 `anyOf` 형태로 교체** |

#### ★★ ④가 이 사이클 최대 위험이었다 — **회귀 지점**

```jsonc
// 현행
"not": { "required": ["basis"] }

// ❌ 가장 짧은 자연스러운 편집 — 이름을 하나 더한다
"not": { "required": ["basis", "value_formatted"] }
//   required:[a,b] 는 "둘 다 있다" 이고 그 부정은 "둘 다 있지는 않다" 다.
//   → basis 만 있는 계산 불가 레코드가 통과한다. W2 가 세운 basis 금지가 지워진다.

// ✅ 채택
"not": { "anyOf": [ {"required":["basis"]}, {"required":["value_formatted"]} ] }
```

**실측 (jsonschema 4.26.0 · 수정 전/후 + 틀린 형태 3경로):**

| 레코드 (`status: unavailable`) | 수정 전 | **수정 후** | 틀린 형태였다면 |
|---|---|---|---|
| ① `basis`·`value_formatted` 둘 다 없음 | 통과 | **통과** | 통과 |
| ② `value_formatted` 있음 | 거부 ※ | **거부** | **통과** ← 새 금지가 안 걸린다 |
| ③ ★ **`basis` 있음** | **거부** | **거부** ✅ | **통과** ← **기존 금지가 사라진다** |
| ④ 둘 다 있음 | 거부 | **거부** | 거부 |

> ### ※ ②의 "수정 전 거부" — 스토리 표와 다르다. 확인해 기록한다
> 스토리 §4.16 표는 ②를 *"수정 전 통과"* 로 적었다. **절 단위로는 맞다** — `allOf[2].then.not` 만 떼어 평가하면 통과다.
> **그러나 스키마 전체로는 `거부`** 였다. `value_formatted` 가 `properties` 에 없고 `additionalProperties: false` 이므로 **미선언 키로 먼저 막혔다** (실측: 거부 사유가 `additionalProperties`).
>
> **즉 수정 전 상태가 스토리가 말한 것보다 안전했다.** 그래도 `anyOf` 형태는 필수다 — **`value_formatted` 를 `properties` 에 선언하는 순간 `additionalProperties` 방어가 사라지고 `not` 절이 유일한 방어가 된다.** 위 표의 "틀린 형태" 열에서 ②와 ③이 함께 통과하는 것이 그 증거다.

**`limit_note` 를 나중에 같은 자리에 넣을 때도 `anyOf` 배열에 항목을 더한다.** `required` 배열로 되돌리면 같은 회귀가 재발한다.

---

### FIX-3 · `common.schema.json` — `metric_value.limit_note` 추가 (N-8)

**근거** Thomas N-8 · 스토리 §4.17

| | |
|---|---|
| **문제** | `kpi-definition-v1.md` §4.2 가 `campaign_response_count` 의 정밀도 한계를 규정하고 화면 규칙 `V-7` 이 `한계` 칩을 요구하는데 **담을 필드가 없었다**. `notices[]` 는 산출물 단위라 개별 지표에 붙지 않는다 |
| **변경** | `properties.limit_note` 추가. **선택 필드** |
| **주의** | **어느 `allOf` 분기에도 넣지 않았다.** 조건부 필수로 만들면 한계 없는 지표가 전부 실패한다. 금지 목록(`allOf[2].then.not`)에도 넣지 않았다 |

`unconfirmed`(파라미터 미확정)와 다르다 — **한계는 이벤트가 추가되지 않으면 영원히 남는다.** `unit` 에서 유도할 수 없는 지표별 사실이므로 **호출자(`kpi.py`·`economics.py`)가 넘긴다.** `value_formatted` 와 생성 주체가 반대다.

---

### FIX-4 · `data_quality_report.schema.json` — `status` ↔ `reason_code` (Q-2)

**근거** 리드 판정 2026-09-11 · 스토리 m-07 §7.2

| 하위 변경 | 형태 |
|---|---|
| `blocked` → `reason_code` 는 `BLOCKED` 만 | **추가** (새 `allOf` 절) |
| `not_run` → `NOT_RUN` 또는 `PRECONDITION_MISSING` | **추가** (새 `allOf` 절) |
| **`vacuous` → `reason_code` 금지** | ★★ **`allOf[2]` 교체** |

계약이 `BLOCKED`(환경 제약으로 **못 했다**)와 `NOT_RUN`(**안 했다**)을 명시적으로 갈랐는데 스키마가 그 조합을 막지 않았다. 픽스처 `DQ-06` 이 `status:"not_run"` + `reason_code:"BLOCKED"` 로 **안 한 것을 못 한 것으로** 적고 있었다 — 책임이 환경으로 넘어가는 형태다.

#### ★★ `vacuous` 는 왜 **추가가 아니라 교체**인가

현행 `allOf[2]` 는 `vacuous` 에 `reason_code` 를 **`required` 로 걸고 있다.** 여기에 금지 절을 *추가*하면:

```
reason_code 있음  →  새 절이 거부
reason_code 없음  →  현행 절이 거부
                     ⇒ 양쪽 다 거부 — vacuous 가 만족 불가능해진다
```

**`empty-sink` 의 `vacuous` 7건이 오늘의 정상 상태인데 게시할 수 없게 된다.**

**실측 (jsonschema 4.26.0):**

| 레코드 | 수정 전 | **수정 후** | "추가" 했다면 |
|---|---|---|---|
| `vacuous` · `reason_code` 없음 ← 오늘의 정상 상태 | 거부 | **통과** ✅ | **거부** ❌ |
| `vacuous` · `reason_code:"NOT_RUN"` | 통과 | **거부** ✅ | **거부** |

**두 줄을 다 확인했다.** 하나만 보면 만족 불가능해진 것을 못 잡는다.

> **`reported_checks == len(checks)` (Q-3) 는 여기 없다.**
> draft 2020-12 에 **교차 필드·배열 길이 비교 키워드가 없다** (`$data` 는 Ajv 확장이지 표준이 아니다). 스키마에 적으려 시도하지 않았고, **게시 자기검증 + 테스트**로 막는다. 애초에 `len(checks)` 로 산출해 상수를 두 번 적지 않는다.

---

## 픽스처 영향 — **의도된 실패 9항목**

**수정 전 스냅샷에서는 14파일 전부 통과했다** (실측). 따라서 아래 실패는 **전부 이번 수정이 만든 것**이고 픽스처의 기존 결함과 섞이지 않는다 — `test_snapshot_accepted_every_fixture` 가 이 사실을 고정한다.

정본 목록은 **`tests/test_publish_contract.py` 의 `INTENDED_FIXTURE_FAILURES`** 다. 그 테스트는 두 방향을 모두 본다:

| 방향 | 검사 |
|---|---|
| **목록 밖에서 실패하면** | `test_fixtures_fail_only_where_intended` 가 실패 — 제약이 과하게 물었다 |
| ★ **목록 안에서 통과하면** | `test_every_intended_failure_actually_fails` 가 실패 — **제약이 안 걸렸다** |

**개수를 본문에 적지 않는다.** 항목이 늘면 숫자가 어긋나고, 세지 않은 항목은 통과해도 모른다 — dict 를 순회한다.

| 원인 | 어디에 |
|---|---|
| **C-1** `value_formatted` 부재 | `ingestion_report` · `rejection_report` · `field_coverage_report` · `kpi_report` (양 픽스처) |
| **F-E** `vacuous` 7건이 `reason_code` 를 담고 있다 | `empty-sink/data_quality_report.json` |
| **Q-2** `DQ-06` 이 `not_run`+`BLOCKED` | 동일 |

> ★ `commerce-connected/kpi_report.json` 의 **`allOf[1]`(`unconfirmed`) 항목이 중요하다.** 픽스처 14파일에 `unconfirmed` 가 **1건뿐**이라 `allOf[1]` 을 빠뜨리면 조용히 통과한다. 그 항목이 그 자리를 지킨다.
>
> ★ `commerce-connected` 의 **검사 11종 누락(7 vs 18)은 이 수정과 무관한 픽스처 자체의 결함**이다 (CR-2). **정답으로 삼지 않는다.** 구현은 항상 18종을 낸다.

---

## 검증 방법

```bash
# 계약 수정 검사 — 30건. 아래층 16건은 jsonschema 없이도 돈다
python3 -m unittest tests.test_publish_contract -v

# 전체 (기준선 46건 대비 회귀 0)
python3 -m unittest discover -s tests
```

`jsonschema` 는 **dev 전용**이다 (결정 D-21). 미설치 환경에서는 전체 스키마 검증 14건이 **`BLOCKED` 사유와 함께 skip** 되고, **`not` 논리 검사(AC-4e)는 skip 되지 않는다** — 회귀 지점이 거기이므로 의존성 없는 CI 에서도 검사된다.
