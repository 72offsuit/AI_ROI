---
name: review-w3-stories-thomas-regate1
cycle: C1
wave: W3
stage: 2 (재검증 · regate_count = 1)
reviewer: Thomas (Role 12 · Code Reviewer)
scope: 좁힘 — C-1~C-5 닫힘 여부 · 수정이 만든 새 모순 · 계약 4회 충돌 · D2b 타당성 · CR-2 처리
date: 2026-09-11
verdict: CONCERNS → critical 1건 잔존 (C-1)
verdict_note: >
  C-2·C-3·C-4·C-5 는 닫혔다. CR-2 처리는 충분하다.
  C-1 은 닫히지 않았다 — 계약에 필드를 추가하는 결정은 있으나 그것을 채우는 작업이
  어느 스토리에도 없다. 리드가 지목한 "계획만 있고 작업이 없다"가 그대로다.
  새로 발견한 noncritical 6건은 전부 이번 수정이 만든 것이다.
---

# W3 재게이트 1회차 — Thomas 재검증 (범위 좁힘)

**작성** Thomas (Role 12) · 2026-09-11 · `regate_count = 1`

> 리드 지시대로 **전면 재독하지 않았다.** 1차 리뷰 `review-w3-stories-thomas-kr.md` 를 전제로,
> **내가 낸 지적이 실제로 닫혔는지**와 **수정이 만든 새 모순**만 봤다.

---

# 0. 결론

| # | 판정 | 한 줄 |
|---|---|---|
| **C-1** | 🔴 **열려 있다** | 계약에 `value_formatted` 를 **추가하는 결정**만 있다. **채우는 작업이 어느 스토리에도 없다** |
| **C-2** | 🟢 **닫혔다** | 순위 교정 확인. 두 픽스처와 일치 재현. **단 규칙 자체에 구멍 2개** → NR-3 |
| **C-3** | 🟢 **닫혔다** | 의도된 실패 목록 + *"실패해야 실패한다"*. **단 와일드카드가 방향을 안 가른다** → NR-2 |
| **C-4** | 🟢 **완전히 닫혔다** | §4.4.0 신설. 이번 수정 중 가장 잘 된 것 |
| **C-5** | 🟢 **닫혔다** | `OrderItem`·`OrderView` 정의 · 조립 위치 · `items: ()` 정상경로. **단 조립 task 부재** → NR-6 |
| **CR-2** | 🟢 **처리 충분** | Q-4 의 *"18종 · ID 집합 일치 · 정답으로 삼지 않는다"* 가 옳은 닫음이다 |

**새로 발견한 noncritical 6건(NR-1~NR-6)은 전부 이번 수정이 만든 것이다.**

**재게이트 판단:** critical 1건 → **FAIL 유지.** 다만 C-1 은 **한 스토리(m-03)에 필드 하나 + m-06 T 에 두 줄**이면 닫힌다. 2회차는 짧다.

---

# 1. 🔴 C-1 — 닫히지 않았다

리드가 정확히 지목한 자리다. *"계획만 있고 작업이 없으면 C-1이 그대로입니다."* **그대로다.**

## 1.1 있는 것 / 없는 것 — 실측

**있는 것 (계약 쪽):**
```
m-06 §4.12      value_formatted 스키마 정의 · ok·unconfirmed 필수 / 계산 불가 금지
m-06 AC-4b:104  "★ value_formatted 를 계약에 추가한다"
m-06 §4.14      픽스처 14파일이 이 제약으로 실패함을 의도된 실패로 등록
d-01:155·d-02:186  "오늘 계약에 없다 — M-06 이 추가한다" 경고 삽입
project-context §11.4  D2b 결과에 "★ 의도된 신설 (C-1)"
```

**없는 것 (생산 쪽) — grep 실측:**

```
$ grep -c "value_formatted\|limit_note" story-m-0{2,3,4,7,9}-*.md
m-02  0        m-03  0        m-04  0        m-07  0        m-09  0
```

| 빠진 것 | 근거 |
|---|---|
| **`MetricValue` dataclass 에 `value_formatted` 필드가 없다** | m-03 §4.7 *"계약이 강제하는 불변식을 dataclass 가 그대로 담아야 한다"* 표 **7행 전수 확인 — `value_formatted` 없음** |
| **`kpi.py`·`economics.py` 가 채우지 않는다** | m-03·m-04 grep **0건** |
| **`publish.py`·`contracts.py` 에 생성 task 가 없다** | m-06 **T1·T2·T3 전수 확인 — 없다.** T1 이 나열하는 계약 수정은 **B-11 과 Q-2 둘뿐**이다 |
| **스키마 추가조차 task 에 없다** | `value_formatted` 는 **AC-4b(인수조건)에만** 있고 §5 작업 분해에 없다 |
| **포맷 규칙을 아무도 정하지 않았다** | `unit` 이 `krw`·`ratio`·`count`·`days` 로 갈리는데 통화 기호·소수 자릿수·천단위를 **누가 어디서** 정하는지 어느 스토리에도 없다 |

> **readiness-report §0.1 은 *"`contracts.py` 에 생성 task"* 라고 적었다. 그 task 는 파일에 없다.**

## 1.2 그래서 무슨 일이 일어나는가 — 두 갈래, 둘 다 나쁘다

계약이 `status ∈ {ok, unconfirmed}` → `value_formatted` **required** 를 선언하는데 **아무도 그 값을 만들지 않는다.**

**규모 실측** — 픽스처에서 영향받는 `metric_value` 개수:

```
전체 metric_value 상태 분포: ok 148 · unconfirmed 1 · unavailable 106 · not_run 17 · blocked 2 · vacuous 7

commerce-connected/ingestion_report.json    ok/unconfirmed  55 / 58   (95%)
empty-sink/ingestion_report.json            ok/unconfirmed  55 / 60   (92%)
commerce-connected/field_coverage_report    ok/unconfirmed  22 / 44
commerce-connected/kpi_report               ok/unconfirmed   9 / 25
empty-sink/kpi_report                       ok/unconfirmed   3 / 24
commerce-connected/rejection_report          3/3   ·  empty-sink/rejection_report  2/3
                                            ─────────────────────────────
                                            6파일 · 149개 metric_value
```

실제 게시물도 같은 비율이다. **`ingestion_report` 는 계층 0 수집 건전성이라 거의 전부 `ok` 다.**

| 갈래 | 조건 | 결과 |
|---|---|---|
| **① 테스트가 잡는다** | `jsonschema` 설치됨(M-05 이후) → `test_publish_contract.py` 전체 스키마 검증 | **W5 가 만든 모든 게시물이 자기 계약을 어긴다.** 149개 × 게시 1회 |
| **② 아무도 못 잡는다** | `jsonschema` 미설치 → 테스트 skip. 게시 시점 자기검증은 §4.11 이 *"핵심 불변식 몇 개"* 로 한정했고 **그 목록(값-null·basis 유무·denominator 0·combined 금지·KST)에 `value_formatted` 가 없다** | 게시는 성공하고 **화면은 `undefined`** — ★ **C-1 의 원래 증상이 그대로 살아남는다** |

**②가 더 위험하다.** 계약에 required 를 적어 놓고 아무도 검사하지 않으면, **"계약이 강제한다"는 문장만 남고 강제는 없다.**
그리고 §4.11 의 "핵심 불변식 몇 개"는 이미 스토리가 정한 목록이라 **W5 가 늘릴 이유가 없다.**

## 1.3 닫으려면 — 네 줄

| # | 어디 | 무엇 |
|---|---|---|
| ① | **m-03 §4.7 불변식 표** | `status ∈ {ok, unconfirmed} → value_formatted 필수` 행 추가. `MetricValue` dataclass 에 `value_formatted: str \| None` · `limit_note: str \| None` 필드 추가. **`__post_init__` 이 검사한다** |
| ② | **★ 누가 포맷하는가를 정한다** | 미결정이다. 둘 중 하나를 W3 가 고른다 — ⑴ `MetricValue.ok(...)` 호출자(`kpi.py`·`economics.py`)가 만든다 ⑵ **`contracts.py` 가 `unit`+`value` 로 직렬화 시점에 만든다(권장)**. ⑵면 계산층이 표시 규칙을 모르고, 규칙이 한 곳에 모인다 |
| ③ | **m-06 T1** | `value_formatted`·`limit_note` **스키마 추가**를 task 로. 지금 T1 은 B-11·Q-2 만 나열한다 |
| ④ | **m-06 T2 또는 T3** | **생성 task.** ②에서 ⑵를 고르면 `contracts.py` 의 직렬화 함수 |

**그리고 §4.11 의 "핵심 불변식" 목록에 `value_formatted` 유무를 넣는다** — 그러지 않으면 갈래 ②가 남는다.

## 1.4 `limit_note` 도 같은 구멍이다 (N-8)

`limit_note` 를 필요로 하는 유일한 자리는 **m-04 §4.9 `campaign_response_count`** 인데 **m-04 grep 0건**이다.
선택 필드라 fail-closed 는 안 되지만 **`한계` 칩은 영원히 안 뜬다.** d-02 V-7 이 그리라고 한 것이 데이터에 없다.
→ m-04 §4.9 에 *"`limit_note` 에 한 줄을 담는다"* 를 AC 로 넣으면 닫힌다.

---

# 2. 🟢 C-2 — 순위는 닫혔다. **규칙 자체에는 구멍이 남았다**

## 2.1 닫힌 부분 — 재현 확인

```
m-06 §4.8 ② 개정 후:
  1 CONTRACT_VIOLATION  2 QUALITY_VIOLATION  3 FREEZE_MISMATCH  4 REJECTED_EVENTS
  5 SINK_EMPTY  ←★ 올라감    6 CHECKS_NOT_RUN  ←★ 내려감    7 METRICS_UNAVAILABLE  8 ALL_CLEAR
```

두 픽스처 대조 (실측):

| 픽스처 | `counts` | 규칙이 고르는 값 | 픽스처 값 |
|---|---|---|---|
| `empty-sink` | `quality_violations 0` · `rejected_events 0` · 수집 0건 | **5위 `SINK_EMPTY`** | `SINK_EMPTY` ✅ |
| `commerce-connected` | `quality_violations 3` · `rejected_events 217` | **2위 `QUALITY_VIOLATION`** | `QUALITY_VIOLATION` ✅ |

**§7.2 의 *"구현이 재현해야 하는 것"* 과 §4.8 이 이제 같은 값을 말한다.** 자기모순 해소.

## 2.2 ★ 리드가 지목한 자리 — **2개 표본에 맞춘 것이 규칙이 옳다는 뜻은 아니다**

**표본 밖에서 규칙을 밀어 봤다. 순서 자체는 방어된다:**

| 상태 | 규칙이 고르는 값 | 옳은가 |
|---|---|---|
| 보낸 것이 전부 거부됨 (수집 0 ∧ `rejected 217`) | **4위 `REJECTED_EVENTS`** | ✅ *"안 왔다"* 보다 *"보낸 게 다 튕겼다"* 가 상위다 |
| 수집 정상 ∧ 검사 일부 미실행 | 6위 `CHECKS_NOT_RUN` | ✅ |
| 수집 0 ∧ 검사 전부 미실행 ∧ 지표 전부 불가 | 5위 `SINK_EMPTY` | ✅ **원인이 결과보다 위** |
| 게시물 자체가 없음 | — | `headline_code` 밖. d-01 AC-6 이 처리 ✅ |

**→ 순서 교정은 옳다. 표본에 맞춘 것이 아니라 원인–결과 관계에 맞췄다.**

**그런데 구멍이 둘 남았다 → NR-3.**

---

# 3. 🟢 C-3 — 닫혔다. 와일드카드 하나만 정밀도가 부족하다 → NR-2

§4.14 가 `INTENDED_FIXTURE_FAILURES` 를 신설했고, 규칙 넷이 정확하다:
*목록에 있는 실패 = 기대된 것 · 목록에 없는 실패 = 회귀 · 픽스처를 고치지 않는다 · 제약을 빼지 않는다.*

**★ *"실패해야 실패한다 — 통과해 버리면 제약이 안 걸린 것이므로 그때 실패시킨다"* 가 요점이고, 이게 정확하다.**
skip 으로 처리하면 제약이 사라져도 아무도 모른다. 그 함정을 스토리가 스스로 막았다.

**구현 가능한 형태인가 — 그렇다.** jsonschema 는 `ValidationError.json_path`·`message`·`validator` 를 준다.
`("empty-sink","data_quality_report","DQ-06")` 는 `json_path` 로, `value_formatted` 는 `message` 로 매칭된다.

---

# 4. 🟢 C-4 — 완전히 닫혔다

m-01 **§4.4.0 신설.** 이번 수정 중 가장 잘 된 것이다.

- 깨지는 테스트를 **코드째 인용**하고 왜 깨지는지 2줄로 설명
- **W3 재현 출력**을 붙였다 (`거부=1 수용=0` · `flush() 예외 없음`)
- **좁은 길을 명시** — *"`validate_event()` 는 파싱 실패를 통과시키고 `_partition_key()` 가 계속 던지게 둔다"*
- **왜 그것이 옳은 배치인지**까지 적었다 — *"스키마는 통과해도 파티션 키를 못 만들면 조용히 넘기지 않는다"* 는 계약을 깨지 않는 유일한 배치
- **AC-4 에 항목 추가** — *"`test_unparsable_timestamp_is_reported` 가 그대로 통과한다. **테스트를 고쳐서 통과시키지 않는다**"*
- **§8.3 에서 R-3 을 내리고 C-4 를 올렸고**, *"없는 위험을 표시하고 있는 위험을 놓쳤다"* 를 기록으로 남겼다
- **§9.3 M01-b 에도 교차 참조**를 걸어 정책 선택 시점에 다시 보이게 했다

---

# 5. 🟢 C-5 — 닫혔다

m-03 **§4.7b 신설.** `OrderItem`·`OrderView` frozen dataclass 로 확정.

| 확인 항목 | 결과 |
|---|---|
| `order` 형태 정의 | ✅ `order_id`·`order_amount`·`items`·`treatment_ids`·`has_coupon_use` |
| `items` 원천 부재를 명시 | ✅ *"C1 에서는 비어 있는 것이 정상이다"* |
| 조립 위치 지정 | ✅ *"조립은 `publish.py`(M-06)가 한다"* — 출처를 아는 층과 같은 자리. **N-3 창구 중립성과 일관된다** |
| `unit_cost: None` ↔ `items: ()` 구분 | ✅ *"품목은 아는데 원가를 모른다"* vs *"품목 자체를 모른다"* — `reason_detail` 이 다르게 쓴다 |
| §4.10 표의 거짓 ✅ 정정 | ✅ *"`시뮬레이터 ✅`는 이후 사이클 이야기. C1 에서는 두 출처 모두 `NO_COST_BASIS`"* |
| `MetricValue` 소유 확정 | ✅ M-03 으로 단일화 (상호 위임 해소) |

**`unit_cost: None` 과 `items: ()` 를 가른 것이 특히 좋다.** `blocked_by[].kind` 를 9종으로 나눈 `ADR-0009` 와 같은 원칙이고, 조치 주체가 다르다.

---

# 6. 🟢 CR-2 — 처리가 충분하다

리드 판정(*"도구에 하드코딩 · W5 로 넘김"*)과 m-07 **Q-4** 의 닫음을 확인했다.

**충분하다고 보는 근거:**

1. **`len(checks) == 18` + ID 집합 일치**를 함께 단언한다. 개수만 세면 다른 18종이 와도 통과한다 — **집합을 본 것이 옳다.**
2. ***"`commerce-connected` 의 7종을 정답으로 삼지 않는다"*** 가 명시됐다. 픽스처가 정본 노릇을 하는 자리를 끊었다.
3. m-06 §4.15 규칙 ③ — ***"픽스처를 새로 만들 일이 생기면 이 모듈의 출력에서 만든다. 손으로 저작하지 않는다"***.
   **이게 진짜 닫음이다.** 리드가 *"빠진 11종을 저작하려면 `publish.py` 가 할 판단과 같은 판단이 필요하다"* 고 한 것과 정확히 같은 논리이고, **두 번 저작하면 어긋난다**는 것이 근거다.
4. §4.15 규칙 ④ — 도구 결함을 **고치지 않고 결함으로 표기**. §4.14 의도된 실패 목록과 연결된다.

**W5 로 넘긴 것도 옳다.** 픽스처를 지금 저작하면 그것이 정답이 되고, 실제 구현이 그것에 맞춰 내려간다.

---

# 7. 계약 4회 수정 — **서로 충돌하지 않는다.** 단 구현 함정 1개

## 7.1 충돌 없음 — 실측 확인

| # | 변경 | 대상 | 충돌 |
|---|---|---|---|
| 1 | `REJECTED_EVENTS` | `index.schema.json` `verdict.headline_code.enum` | 없음 (독립 파일) |
| 2 | `status`↔`reason_code` | `data_quality_report.schema.json` `checks[].items.allOf` | 없음 (독립 파일) |
| 3 | `value_formatted` | `common.schema.json` `$defs.metric_value` | 4와 같은 자리 |
| 4 | `limit_note` | 동일 | 3과 같은 자리 |

**3·4 는 같은 `$defs` 를 건드리지만 충돌하지 않는다** — 둘 다 `properties` 추가이고, `additionalProperties: false` 는 둘을 등록하면 해소된다.

**★ 파급 확인:** `source_split.by_source.{commerce,simulator}` 와 `combined` 이 **`$ref: "#/$defs/metric_value"`** 다(실측).
→ **`value_formatted` 가 출처 분해 값에도 자동으로 전파된다.** 별도 처리가 필요 없다. 이건 좋은 소식이다.

**리드 서술 정정(①필수/금지 쌍 vs ②담을 자리)도 옳다.** `limit_note` 를 조건부 필수로 오해하면 `한계` 없는 지표가 전부 실패한다.

## 7.2 🔴 구현 함정 — `not: {required: [...]}` 를 그대로 늘리면 **guard 가 조용히 무력화된다** → NR-1

m-06 §4.12 가 금지 쪽을 이렇게 적었다:

> | `unavailable` · `blocked` · `not_run` | **금지** (`not: {required: [...]}`) |

**그런데 그 자리에 이미 `not` 이 있다** (실측):

```json
// common.schema.json  $defs.metric_value.allOf[2].then
{ "required": ["reason_code", "reason_detail"],
  "properties": { "value": { "type": "null" } },
  "not": { "required": ["basis"] } }          ← ★ 이미 점유돼 있다
```

**JSON Schema 객체에 `not` 은 하나뿐이다.** 가장 자연스러운 구현 — 배열에 이름을 하나 더 넣는 것 — 이 **틀린다:**

```json
"not": { "required": ["basis", "value_formatted"] }     // ❌ 조용히 약해진다
```

`required: [a, b]` 는 **"둘 다 있다"** 이므로 그 부정은 **"둘 다 있지는 않다"** 다.
→ `{"status":"unavailable", "value":null, "reason_code":"...", "value_formatted":"0원"}` 이 **통과한다.**
**`basis` 가 없으므로.** 계산 불가 지표가 `"0원"` 이라는 표시 문자열을 달고 계약을 통과한다 — **USP-1 실패 양식 그 자체다.**

**올바른 형태:**
```json
"not": { "anyOf": [ {"required": ["basis"]}, {"required": ["value_formatted"]} ] }
```
또는 `allOf` 에 **별도 항목**으로 추가한다.

**→ §4.12 에 이 함정을 함정 표(T-…)로 박는다.** 지금 문구(`not: {required: [...]}`)가 **틀린 구현을 직접 유도한다.**

> 화면 쪽 피해는 제한적이다 — d-01 §4.1 이 `status` 로 분기하므로 `unavailable` 이면 `—` 를 그린다.
> **그러나 계약이 막는다고 적어 놓고 안 막는 것**이 문제다. 다음 사람은 계약을 믿는다.

---

# 8. D2b — **결과는 맞다. 그런데 검사가 자기 창립 사례를 못 잡는다** → NR-4

## 8.1 결과 재현 — 맞다

```
찾은 4  ·  의도된 신설 3 (REJECTED_EVENTS · value_formatted · limit_note)  ·  오탐 1 (rounded.full)  ·  남은 0
```

**오탐 판정도 맞다.** `rounded.full` 은 `Plan/DESIGN.md` 의 디자인 토큰이다 — 게시 계약 필드가 아니다.
**오탐 필터가 진짜를 걸렀는지**를 확인하려고 **독립 스캔을 돌렸다.** 걸러내지 않았다 (§8.2).

## 8.2 ★ 그런데 D2b 의 대상 정의가 **C-1 이 살던 자리를 안 본다**

§11.4 가 정한 D2b 대상:
```
1. json/jsonc 코드블록 안의 키("key":)
2. 같은 블록 안의 대문자 상수 문자열
3. artifact.field 형태의 점 경로
```

**C-1 은 셋 중 어디에도 없었다.** d-01:152 · d-02:183 의 그 줄은 **```ts 블록**이다:

```ts
const display = m.status === 'ok' ? m.value_formatted : EM_DASH;
```

**→ D2b 가 `value_formatted` 를 잡은 것은 m-06 이 새로 만든 `jsonc` 블록 때문이지, d-01·d-02 의 원래 인용 때문이 아니다.**
실행 결과 표가 그 사실을 그대로 보여준다 — `m-06 [키] value_formatted` 로만 잡혔고 **d-01·d-02 는 안 잡혔다.**

**만약 m-06 의 계약 추가 결정이 빠지면, d-01·d-02 는 없는 필드를 계속 인용하고 D2b 는 "남은 0" 을 보고한다.**
**검사가 자기 창립 사례에 대해 눈이 멀어 있다.**

## 8.3 독립 재현 — 범위를 넓혀 돌렸다

```
$ python3 -c "… ts/tsx/js 블록에서 '객체.프로퍼티' 접근을 뽑아
              계약 properties 176 + enum/const 148 + 픽스처 키 208 과 대조 …"

ts/tsx 블록에서 계약·픽스처 어디에도 없는 프로퍼티 접근:
  toFixed            ['d-01 (ts)', 'd-02 (ts)']      ← 금지 패턴 목록의 JS 메서드. 잡음
  value_formatted    ['d-01 (ts)', 'd-02 (ts)']      ← ★ C-1
```

**새 발견은 없다.** `value_formatted` 외에 매달린 필드 인용은 없다 — **그 점에서 §11.4 의 "남은 0" 결론은 맞다.**

**→ D2b 대상에 `ts`·`tsx`·`js` 코드블록의 `<식별자>.<프로퍼티>` 접근을 추가한다.** 위 한 줄이면 된다.
잡음은 `toFixed` 하나뿐이고 그것도 **금지 패턴 목록에 이미 있는 이름**이라 필터가 쉽다.

---

# 9. noncritical — 이번 수정이 만든 것 (6건)

| # | 내용 |
|---|---|
| **NR-1** | **§7.2** — `not: {required: [...]}` 를 그대로 늘리면 `value_formatted` 금지가 조용히 무력화된다. 문구가 틀린 구현을 유도한다 |
| **NR-2** | **§4.14 와일드카드가 방향을 안 가른다.** `("*","*","value_formatted")` 는 *"없어서 실패"* 와 *"있으면 안 되는데 있어서 실패"* 를 같이 삼킨다. **후자는 회귀다.** → 항목을 *"`value_formatted` **부재**만 의도된 실패다. 있으면 안 되는 자리에 있으면 **회귀**"* 로 쪼갠다 |
| **NR-3** | **`SINK_EMPTY` 를 아무도 검산할 수 없다.** `verdict.counts` 는 `additionalProperties: false` · 8키이고 **수집 건수가 없다**(실측). 순위 2·4·6·7 은 `counts` 로 검산되는데 **5위만 안 된다.** 게다가 **순위를 기계로 검사하는 AC 가 없다** — 스키마 `description`/`$comment` 는 문장이지 강제가 아니다. `publish.py` 가 다른 순서를 구현해도 전 테스트가 통과한다. → ⑴ `counts.ingested_events` 추가(5번째 계약 변경) 또는 ⑵ AC 에 *"픽스처 2벌의 `verdict` 로 `headline_code` 를 **재계산**해 픽스처 값과 일치"* 를 넣고 `SINK_EMPTY` 입력만 `ingestion_report` 에서 읽는다고 명시 |
| **NR-4** | **D2b 가 `ts` 블록을 안 본다** (§8). 자기 창립 사례를 못 잡는 검사다 |
| **NR-5** | **m-06 §9.2 잔재** — *"이 스토리에서 하지 않는 것"* 표 1028행에 **`계약 스키마 수정 \| W2 산출물. 어긋나면 코드를 고친다`** 가 그대로 있다. **AC-4b·T1 이 계약을 4회 고치는데 §9.2 는 안 고친다고 적었다.** B-11 이전 판본의 잔재다 |
| **NR-6** | **m-06 절 번호가 무너졌다.** 파일 순서가 `4.8 → 4.9 → 4.12(value_formatted) → 4.12b → 4.13 → 4.14 → 4.15 → 4.10 → 4.11 → 4.12(함정)` 이다. **`## 4.12` 가 둘이다.** 64KB 자족 문서에서 *"§4.12 참조"* 가 어디를 가리키는지 모호하다. → `value_formatted` 를 **§4.16**, `limit_note` 를 **§4.17** 로 옮기고 뒤에 붙인다 |

**덤 (오타 1건):** m-01:461 이 `test_same_import_gives_same_digest` 로 적었다. 실제 이름은 **`test_same_input_gives_same_digest`** 다(`import`→`input`). 테스트 이름의 정확성이 요점인 문단이라 고치는 편이 좋다.

**C-5 파생 (경미):** m-03 §4.7b 가 *"조립은 `publish.py`(M-06)가 한다"* 로 지정했는데 **m-06 에 `OrderView` grep 0건**이다. T3 빌더 목록에 *"`events` → `OrderView` 변환"* 이 없다. **C-1 과 같은 패턴** — 하류 소유자를 지목했으나 그 스토리에 작업이 없다. 다만 `OrderView` 는 §4.7b 에 형태가 확정돼 있어 구현자가 만들 수 있다.

---

# 10. 실행한 검증 (재검증분)

| # | 명령·검사 | 결과 |
|---|---|---|
| 1 | `python3 -m unittest discover -s tests` | **Ran 46 · OK** (기준선 불변) |
| 2 | `python3 .agent-team/04-architecture/tools/check_ownership.py` | **PASS** |
| 3 | `grep -c value_formatted\|limit_note` × m-02·03·04·07·09 | **전부 0** → **C-1 미해소 확정** |
| 4 | m-06 T1·T2·T3 전수 확인 | 계약 수정 task 는 **B-11·Q-2 둘뿐.** `value_formatted` 없음 |
| 5 | m-03 §4.7 `MetricValue` 불변식 표 7행 확인 | `value_formatted` **없음** |
| 6 | 픽스처 `metric_value` 상태 집계 | `ok 148 · unconfirmed 1` — **6파일 149개가 영향** |
| 7 | `verdict.counts` 스키마 실측 | 8키 · `additionalProperties: false` · **수집 건수 없음** → NR-3 |
| 8 | §4.8 개정 순위 ↔ 두 픽스처 대조 | **둘 다 일치** — `SINK_EMPTY` · `QUALITY_VIOLATION` ✅ |
| 9 | 순위 규칙을 표본 밖 4개 상태로 밀어봄 | **전부 방어된다** (§2.2) |
| 10 | `metric_value.allOf` 6항목 전문 확인 | `allOf[2].then.not` **이미 점유** → NR-1 |
| 11 | `source_split`·`kpi_source_split` `$ref` 확인 | **`$ref: metric_value`** — `value_formatted` 자동 전파 ✅ |
| 12 | **D2b 독립 재현** — ts/tsx/js 블록 `X.prop` 접근 × 계약 532종 대조 | **`toFixed`(잡음) · `value_formatted`(C-1) 둘뿐** — 새 발견 0 ✅ |
| 13 | `ownership.json` 지시 7종 확인 | **전부 *"수정하지 않는다 — 돌려 확인만"*** → N-1 완전 해소 ✅ |
| 14 | m-01 §4.4.0 · AC-4 · §8.3 · §9.3 교차참조 | **4곳 전부 반영** ✅ |
| 15 | m-03 §4.7b `OrderItem`·`OrderView` | 정의·조립 위치·`items:()` 정상경로 ✅ |
| 16 | d-02 `vacuous` 반영 (CR-1, Matthias 렌즈) | AC-7·§4.2 표·V-12·C-13 이 **`status === "vacuous"`** 로 통일 ✅ |
| 17 | m-07 Q-4 · m-06 §4.15 (CR-2) | `len==18` + **ID 집합 일치** + *"정답으로 삼지 않는다"* ✅ |

**BLOCKED (1차와 동일):** `validate_examples.py`·`check_zero_fill_rejected.py` — `jsonschema` 미설치.
§7.2 의 `not` 함정과 §1.2 의 149건은 **스키마 구조 분석**으로 확정했고 validator 실행으로는 재확인하지 못했다.

---

# 11. 2회차에서 볼 것 — 짧다

| 순위 | 항목 | 크기 |
|---|---|---|
| **1** | **C-1** — m-03 §4.7 표 1행 + dataclass 2필드 · **포맷 주체 결정** · m-06 T1 1줄 · T2/T3 1줄 · §4.11 목록 1항목 | **결정 1개 + 5줄** |
| 2 | NR-1 — §4.12 에 `not` 함정 명시 | 3줄 |
| 3 | NR-2 — §4.14 `value_formatted` 항목을 방향별로 쪼갬 | 2줄 |
| 4 | NR-3 — 순위 재계산 AC + `SINK_EMPTY` 입력 출처 명시 | 2줄 |
| 5 | NR-5 · NR-6 — §9.2 잔재 삭제 · 절 번호 정리 | 편집 |
| 6 | NR-4 — D2b 에 ts 블록 추가 | 도구 1줄 |

**②(포맷 주체)만 판단이고 나머지는 편집이다.** 그것만 정해지면 C-1 은 닫힌다.
