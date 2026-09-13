---
name: review-w3-stories-thomas
cycle: C1
wave: W3
stage: 2 (독립 재검증 · fresh context)
reviewer: Thomas (Role 12 · Code Reviewer)
lens: 코드 품질 · 아키텍처 정합 · 패턴 · 엣지케이스
date: 2026-09-11
target: .agent-team/03-story-engineering/ (스토리 11종 + project-context + readiness-report)
verdict: CONCERNS (critical 5건 · noncritical 8건)
verdict_note: >
  최종 판정은 3단계에서 리드가 종합한다. 이 필드는 이 리뷰어의 렌즈에서 본 판정이다.
  critical 5건은 전부 "고치지 않으면 W5 가 잘못된 것을 만든다"에 해당하며,
  5건 모두 스토리 텍스트 수정만으로 닫힌다 — 구조 변경이 필요한 것은 없다.
---

# W3 스토리 게이트 — Thomas 독립 리뷰 (코드리뷰 렌즈)

**작성** Thomas (Role 12) · 2026-09-11 · fresh context · BATHOS Lv3 · 사이클 **C1**

> **읽는 법:** §1 이 critical 5건이다. §2 가 noncritical 8건. §3 이 Matthew §10 Thomas 5건에 대한 답.
> §4 가 8대 치명적 실수 대조. §5 가 실행한 검증 명령과 그 출력. §6 이 리드 판정 3건에 대한 의견.
>
> **Matthew 에게는 요약만 반환했다. 근거와 재현 명령은 전부 이 파일에 있다.**

**식별자 표기 규약 (리드 지시):** `Q-1`·`Q-2`·`Q-3` 은 **`story-m-07-data-quality-kr.md` §7.2 내부 번호**를 쓴다.
리드 지시문 §3 의 *"Q-2"*(계약 결함 3건 묶음 전체)와 구분하기 위해, 아래에서는 항상 **어느 문서 어느 절인지**를 함께 적었다.

---

# 1. critical — 이대로 W5 에 가면 잘못된 것이 만들어진다 (5건)

| # | 한 줄 요약 | 대상 |
|---|---|---|
| **C-1** | `value_formatted` 가 계약에 없다 — d-01·d-02 가 "올바른 형태"로 제시한 핵심 코드가 동작하지 않고, 구현자를 `?? 0` 으로 되돌린다 | d-01 §4.1 · d-02 §4.1 |
| **C-2** | `headline_code` 우선순위가 `empty-sink` 픽스처와 모순 — **오늘의 실제 상태**에서 첫 화면이 원인 대신 결과를 말한다 | m-06 §4.8 vs §7.2 |
| **C-3** | m-07 의 Q-2 스키마 제약과 m-06 의 "픽스처 2벌이 여전히 통과" AC 가 **동시에 만족될 수 없다** | m-07 §7.2 · m-06 T1·T5 |
| **C-4** | m-01 의 타임존 수정이 기존 테스트 1건을 깬다 — 스토리가 이 회귀를 적지 않았다 (**실행 재현함**) | m-01 §4.4 · §8.3 · AC-4 |
| **C-5** | m-03 이 `economics.py` 의 입력 자료구조를 한 번도 정의하지 않는다 — C1 에 존재하지 않는 테이블을 전제한다 | m-03 §4.2 · §4.7 · T5 · T7 |

---

## C-1 · `value_formatted` 는 계약에 **없다.** 그런데 두 대시보드 스토리의 핵심 코드가 그것을 읽는다

### 무엇이 적혀 있나

`story-d-01-dashboard-foundation-kr.md:144` · `story-d-02-observability-views-kr.md:182` — **글자 하나까지 같다:**

```ts
// 게시물이 포맷까지 끝낸 문자열을 준다. 화면은 숫자를 포맷하지 않는다 (DB-012)
const EM_DASH = '—';                       // — U+2014. hyphen(-) 아니다
const display = m.status === 'ok' ? m.value_formatted : EM_DASH;
```

이 다섯 줄은 **d-01 §4.1 "★★ 코드 수준 함정 — 이 사이클 최대 위험"** 절의 결론이고,
금지 패턴 8종(`?? 0`·`|| 0`·`Number(value)` …)을 나열한 뒤 제시하는 **유일한 대안**이다.

### 실측 — 그 필드는 존재하지 않는다

```
$ python3 -c "import json; d=json.load(open('.agent-team/04-architecture/schemas/common.schema.json'))
              mv=d['\$defs']['metric_value']
              print(list(mv['properties'])); print(mv['additionalProperties'])"

['status', 'value', 'unit', 'basis', 'reason_code', 'reason_detail',
 'blocked_by', 'derived', 'derivation', 'params_used', 'ci95']
False                                   ← ★ additionalProperties: false
```

```
$ grep -o "value_formatted" .agent-team/04-architecture/examples/*/*.json | wc -l
0                                       ← 픽스처 14파일 전수 0건

$ grep -rl "value_formatted" .
.agent-team/07-design/dashboard-agents-design-constraints.md    ← 원 출처 (Jonnathan)
.agent-team/03-story-engineering/story-d-01-dashboard-foundation-kr.md
.agent-team/03-story-engineering/story-d-02-observability-views-kr.md
```

**`metric_value` 는 `additionalProperties: false` 다.** Phillip 이 `value_formatted` 를 실어 보내면 **게시물이 자기 스키마를 어긴다** —
m-06 §4.8 우선순위 1위 `CONTRACT_VIOLATION` 이 그 자리다. 계약을 고치지 않고는 담을 방법이 **없다.**

그리고 **m-06 의 T1~T6 어디에도 `value_formatted` 를 만드는 task 가 없다.** Phillip 은 그런 필드가 요구된다는 사실 자체를 모른다.

### 왜 critical 인가 — 이 절이 막으려던 바로 그 경로를 연다

Andrew 가 d-01 §4.1 을 그대로 따르면:

1. 모든 `ok` 지표가 `undefined` 로 렌더된다. **`—` 도 아니고 값도 아니다.**
2. 원인을 찾다가 `m.value_formatted` 가 없다는 걸 알게 된다.
3. 남은 것은 `m.value` (숫자) 뿐이다. 그런데 같은 절이 **"`value` 를 숫자로 받아 포맷하지 않는다 (DB-012)"** 를 규칙으로 못박았다.
4. 규칙을 지킬 방법이 없으므로 `m.value.toLocaleString()` 을 쓴다.
5. `status !== 'ok'` 인 지표에서 `null.toLocaleString()` 이 던진다.
6. **예외를 막으려고 `?? 0` 을 쓴다.**

d-01 §4.1 이 직접 쓴 문장이다 — *"`(null).toLocaleString()` 이 예외를 던지기 때문에 구현자는 예외를 막으려고 `?? 0` 을 쓴다. 그 순간 USP-1 이 깨진다."*
**스토리가 그 경로를 경고해 놓고, 스스로 그 경로로 밀어 넣는다.**

### 어디서 왔나

`.agent-team/07-design/dashboard-agents-design-constraints.md:44` 가 원 출처다. Jonnathan 이 쓴 것이고 **계약과 대조되지 않았다.**
스토리는 그것을 두 파일에 그대로 옮겼다. `readiness-report-kr.md` §2 D2 가 자랑하는 *"인용 경로 45종 전수 존재 검사 — 실패 0건"* 은
**경로가 존재하는지**를 봤을 뿐 **인용한 내용이 계약과 맞는지**는 보지 않았다. 8대 실수 목록에 없는 유형이라 §4 에 별도로 적었다.

### 고칠 것 (택일 — 어느 쪽이든 세 파일을 같이 고쳐야 한다)

| 안 | 내용 | 건드리는 곳 |
|---|---|---|
| **① 계약에 넣는다 (권장)** | `common.schema.json` `$defs.metric_value` 에 `value_formatted: {"type":["string","null"]}` 추가. `status == "ok"` 이면 필수. **`docs/contracts/**` 는 Phillip 소유이므로 B-11 과 정확히 같은 논리로 W5 권한 안이다** | m-06 T1 (B-11 옆에 한 줄) · m-06 T2 (`contracts.py` 가 채운다) · d-01 §4.1 유지 |
| ② 화면이 포맷한다 | DB-012 를 지표 값에 한해 완화. **`status` 분기를 먼저 강제**하는 헬퍼 하나(`formatMetric(m): string`)를 `lib/format/` 에 두고 그 밖에서 `m.value` 접근 금지 | d-01 §4.1 · d-02 §4.1 재작성 · DB-012 예외를 PR 에 기록 |

**①을 권장한다.** DB-012(*"단순 합산도 계산이다"*)를 지키고, 통화·소수·천단위 결정이 두 곳에 생기는 것을 막는다.
그리고 이미 리드가 B-11 에서 *"화면 우회를 쓰지 않고 계약을 고친다"* 를 판정했다 — **같은 원칙이 여기에도 그대로 적용된다.**

> **어느 쪽을 고르든 d-01 AC-6 의 마지막 방어선은 그대로 둔다** — *"`status !== "ok"` 인데 `value !== null` 이면 던진다"*.
> 그것은 옳은 층에 있는 옳은 검사다.

---

## C-2 · `headline_code` 우선순위가 `empty-sink` 픽스처와 모순된다 — 그리고 m-06 자기 자신과도

### 무엇이 적혀 있나

`story-m-06-publish-kr.md` §4.8 ② — 계약에 넣을 8종 우선순위:

| 순위 | `headline_code` | 조건 |
|---|---|---|
| … | … | … |
| **5** | `CHECKS_NOT_RUN` | `counts.checks_not_run + checks_blocked > 0` |
| **6** | `SINK_EMPTY` | 수집 이벤트 0건 |

같은 파일 §7.2 — *"`empty-sink` 픽스처의 실측 특성 — **구현이 재현해야 하는 것**"*:

```
verdict.headline_code: "SINK_EMPTY" · level: "attention"
metrics_unavailable: 12 · checks_not_run: 10 · schema_gaps: 4 · lock_items_pending: 9
```

### 실측 — 두 절이 반대 값을 요구한다

```
$ python3 -c "import json; print(json.load(open('.agent-team/04-architecture/examples/empty-sink/index.json'))['verdict'])"

level: attention · headline_code: SINK_EMPTY
counts: {..., checks_not_run: 10, checks_blocked: 1, ..., rejected_events: 0}
```

`checks_not_run(10) + checks_blocked(1) = 11 > 0` → **§4.8 규칙대로면 5위 `CHECKS_NOT_RUN` 이 이긴다.**
그런데 픽스처는 `SINK_EMPTY` 이고, §7.2 는 그것을 *"구현이 재현해야 하는 것"* 으로 못박았다.
**같은 스토리 파일 안에서 §4.8 과 §7.2 가 서로를 부정한다.**

### 왜 critical 인가

`empty-sink` 는 가상 시나리오가 아니다. **오늘의 실제 상태다** — m-06 §7.2 자신이 *"7파일 — 오늘의 실제 상태"* 라고 적었다.
커머스 이벤트 0건(`Ecommerce_Service #28` **OPEN**, 라이브 확인) · 시뮬레이터 미구현.

즉 **C1 대시보드가 처음 켜졌을 때 항상 이 조합이다.** 잘못 고르면 첫 화면 한 줄이 이렇게 된다:

```
? 데이터 품질 검사 11건 미실행           ← 사용자가 "검사를 안 돌렸구나" 로 읽는다
```

실제 사실은 **"이벤트가 한 건도 안 들어와서 검사할 대상이 없다"** 이다.
`CHECKS_NOT_RUN` 은 `SINK_EMPTY` 의 **원인이 아니라 결과다.** 결과를 헤드라인으로 올리면 원인이 사라진다.

Jonnathan 도 같은 자리에서 흔들렸다 — `ux-flow-map.md` §1.1 의 7단계는 *"2위 미실행 검사 / 6위 수집 0건"* 인데,
바로 아래에 **"2026-09-11 현재 예상 판정: 순위 5 또는 6"** 이라고 적었다. **자기 표를 자기가 안 따랐다.**
Matthew 는 그 표의 상대 순서만 가져오고 픽스처와 대조하지 않았다.

### §4.8 의 논증이 어디서 미끄러졌나

§4.8 은 픽스처 무영향을 이렇게 주장한다:

> `examples/*/index.json` **고치지 않는다** — 픽스처. 둘 다 `headline_code` 가 8종 안에 있으므로 **여전히 통과한다** (실측: `SINK_EMPTY`·`QUALITY_VIOLATION`)

**"enum 소속 검사"와 "규칙 일치 검사"를 같은 것으로 다뤘다.** 전자는 맞다. 후자는 검사되지 않았다.
`commerce-connected` 는 우연히 맞는다 — `quality_violations: 3`(2위)이 `rejected_events: 217`(4위)을 이겨서
`QUALITY_VIOLATION` 이 나오고 픽스처와 같다. `empty-sink` 는 우연히 틀린다.

### 고칠 것

1. **§4.8 우선순위 표에서 `SINK_EMPTY` 를 `CHECKS_NOT_RUN` 위로 올린다.** 원인이 결과보다 위다.
   `SINK_EMPTY` 는 다른 모든 `attention` 조건의 상위 원인이므로 `attention` 군의 첫 자리다.
2. **§4.8 이 스스로 정한 검증을 AC 로 만든다** — *"픽스처 2벌의 `counts` 로 `headline_code` 를 **재계산**해 픽스처의 `headline_code` 와 일치하는지 단언한다."*
   enum 소속만 보는 검사로는 이 결함이 다시 들어온다.
3. §7.2 의 *"구현이 재현해야 하는 것"* 목록과 §4.8 의 표가 **한 번은 서로를 확인하도록** 스토리에 교차 참조를 남긴다.

> **리드 판정 B-11 자체에는 이견이 없다.** *"화면 우회를 쓰지 않고 계약을 고친다"* 는 옳다.
> 틀린 것은 **Matthew 가 채운 구체 순서**다. 리드는 순서를 지정하지 않았고 스토리가 *"순서를 바꿀 근거가 있으면 바꾸되 PR 에 적는다"* 로 열어 뒀다.
> **근거는 여기 있다.** 다만 W5 구현자가 픽스처와 대조할 이유를 못 찾으면 그대로 계약에 들어가고, **GATE 1 에서 Lock 된다.**

---

## C-3 · Q-2 스키마 제약과 m-06 의 "픽스처 2벌이 여전히 통과" AC 는 동시에 만족될 수 없다

### 무엇이 적혀 있나

`story-m-07-data-quality-kr.md` §7.2 **`Q-2`** — `docs/contracts/.../data_quality_report.schema.json` 에 추가할 제약:

```jsonc
{ "if":   { "properties": { "status": { "const": "not_run" } }, "required": ["status"] },
  "then": { "properties": { "reason_code": { "enum": ["NOT_RUN", "PRECONDITION_MISSING"] } } } }
```

`story-m-06-publish-kr.md` T1 — *"★ **Q-2 수정 2건** — `data_quality_report.schema.json` 에 `status`↔`reason_code` 제약 추가"*
`story-m-06-publish-kr.md` T5 / §9 DoD — *"`examples/empty-sink/` 7건이 **여전히 통과**하는지 확인 (계약 회귀)"* · *"**픽스처 2벌(14파일)이 여전히 계약을 통과한다**"*

### 실측 — 픽스처가 그 제약을 위반한다

```
$ python3 -c "... examples/empty-sink/data_quality_report.json ..."

checks: 18 · gate=incomplete · {not_run:10, vacuous:7, blocked:1}
  DQ-06  not_run  BLOCKED   '타임존 정책이 아직 강제되지 않는다(이슈 #53 D1-3)…'
                  ↑↑↑↑↑↑↑ status=not_run 인데 reason_code=BLOCKED
```

**제약을 넣는 순간 `empty-sink/data_quality_report.json` 이 계약 검증에 실패한다.**
그리고 그것이 `Q-2` 가 잡으려는 결함 **그 자체다** — 픽스처가 결함의 증거물이다.

**두 번째 사례도 같다.** `Q-3`(`reported_checks == len(checks)` 자기검증):

```
commerce-connected  checks 7건 · spec_coverage.reported_checks: 6
```

m-07 §7.2 는 *"게시 시점 자기검증(`contracts.py`)에서 `reported_checks != len(checks)` 면 `ContractViolation` → **fail closed**"* 를 지시한다.
그 검사를 픽스처에 적용하면 `commerce-connected` 도 막힌다.

### 왜 critical 인가 — W5 가 셋 중 하나를 하게 된다

두 스토리 모두 픽스처 수정을 **금지**한다 (m-06 §6.2 *"`examples/**` ← 픽스처. 읽기만"* · m-07 §7.2 *"`examples/` 픽스처는 고치지 않는다"*).
AC 두 개가 상호 배타이므로 Phillip 은:

| 도피로 | 결과 |
|---|---|
| a. 제약을 안 넣는다 | **`Q-2` 무력화.** 리드가 *"스키마로 막는 것을 W5 작업으로"* 라고 판정한 것이 사라진다 |
| b. 픽스처를 고친다 | **W2 산출물 무단 수정.** 두 스토리가 명시적으로 금지한 행위 |
| c. 테스트에서 `DQ-06` 만 예외 처리 | **조용한 약화.** *"결함을 조용히 고치지 않는다"*(`AGENTS.md`) 위반. 다음 사람은 왜 예외인지 모른다 |

**셋 다 나쁘고, 스토리는 이 갈림길이 있다는 사실조차 알려주지 않는다.**

### 고칠 것 — 리드가 이미 만든 패턴을 그대로 쓰면 된다

리드는 T6 대조 테스트를 *"바이트 일치"* 에서 ***"의도된 차이 목록과 대조"*** 로 바꿨다. **같은 패턴을 픽스처에 적용한다.**

m-06 AC 와 m-07 AC 양쪽에 **의도된 실패 목록**을 명시한다:

```
계약 수정(B-11 · Q-2) 후 픽스처 14파일 중 2건이 의도적으로 실패한다:
  examples/empty-sink/data_quality_report.json        DQ-06 status=not_run + reason_code=BLOCKED  → Q-2 가 잡는 결함
  examples/commerce-connected/data_quality_report.json  reported_checks 6 ≠ len(checks) 7          → Q-3 가 잡는 결함
나머지 12파일은 통과해야 한다. 이 목록 밖의 실패가 나오면 계약 수정이 잘못된 것이다.
```

**이렇게 적으면 실패가 증거가 된다** — 제약이 실제로 작동한다는 증거다.
*"검사가 잡는지 확인하지 않은 검사는 없는 검사와 같다"*(m-07 §4.7 자신의 문장)를 여기에 적용하는 것이다.

---

## C-4 · m-01 의 타임존 수정이 기존 테스트 1건을 깬다 — 스토리에 없다 (실행 재현)

### 재현

```
$ python3 -c '
import unittest
from datetime import datetime
from src.measurement import schema as sc
_orig = sc.validate_event
def patched(record):                        # ← m-01 §4.4 ⑵ "오프셋 존재를 요구" 를 흉내
    problems = _orig(record)
    ts = record.get("timestamp")
    if ts is not None and not isinstance(ts, datetime):
        try:    dt = datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
        except ValueError: problems.append(f"timestamp 를 해석할 수 없다: {ts!r}")
        else:
            if dt.tzinfo is None: problems.append("timestamp 에 오프셋이 없다")
    return problems
sc.validate_event = patched
unittest.TextTestRunner().run(unittest.TestLoader().discover("tests"))'

FAIL: test_unparsable_timestamp_is_reported (test_sink.TestRoundTrip)
  File "tests/test_sink.py", line 112, in test_unparsable_timestamp_is_reported
    with self.assertRaises(ValueError) as caught:
AssertionError: ValueError not raised

Ran 46 tests — FAILED (failures=1)
```

### 왜 깨지나

```python
# tests/test_sink.py:108-114
def test_unparsable_timestamp_is_reported(self) -> None:
    """스키마는 통과해도 파티션 키를 못 만들면 조용히 넘기지 않는다."""
    s = sk.EventSink(self.root)
    s.write_events([simulator_event(timestamp="어제")])
    with self.assertRaises(ValueError) as caught:
        s.flush()
```

이 테스트는 **`validate_event()` 가 `"어제"` 를 통과시키는 것에 의존한다.**
`validate_event()` 에 timestamp 검사가 들어가면 → `write_events()` 가 거부 → `strict=True` 기본값이므로 `continue` →
`_buffer` 가 빈다 → `flush()` 가 `if not self._buffer: return` 으로 즉시 반환 → **`ValueError` 가 안 난다.**

**§4.4 의 ⑴·⑵ 양쪽 다 해당한다.** ⑵도 *"오프셋 **존재**만 요구 (naive 는 거부)"* 를 하려면 파싱이 필요하고, 파싱은 `"어제"` 에서 실패한다.

### 46/46 을 지키는 유일한 좁은 길 — 이것도 실행으로 확인했다

```
$ python3 -c '... except ValueError: pass   # ← 파싱 실패는 validate_event 가 통과시킨다 ...'
Ran 46 tests in 0.029s — OK
```

**파싱 실패는 `validate_event()` 가 통과시키고 `_partition_key()` 가 계속 던지게 둔다.**
즉 *"형식은 못 읽어도 스키마 위반은 아니다. 파티션을 못 만드는 것이 오류다"* 라는 층 분리를 유지하는 것이다.
이건 사실 **옳은 설계**이기도 하다 — `validate_event()` 는 필드 규약을 보고, 파티션 키 생성은 저장 계층의 책임이다.

### 왜 critical 인가

- m-01 **AC-4** 가 *"기준선 46건에서 **회귀 0**"* 을 요구한다.
- m-01 **§8.3** 은 *"확립된 패턴 — 깨지 않는다"* 표에 5개를 나열하는데 **이 테스트가 없다.**
- 구현자는 원인 모를 실패를 만난다. 가장 짧은 해결은 **테스트를 고치는 것**이고, 그 순간
  *"결함을 조용히 고치지 않는다"*(`AGENTS.md`) 와 *"미실행 검증을 통과로 표시하지 않는다"* 를 동시에 어긴다.

### ★ 그리고 Matthew 가 표시한 R-3 은 **위험이 아니다** (§3-2 에서 상술)

`readiness-report-kr.md` §7 R-3 · m-01 §8.3 이 `test_same_input_gives_same_digest` 를 ★ 로 표시하고
*"해결책은 제시하지 않았다 — 구현자가 판단해야 하는 자리다"* 로 남겼다.
**그 테스트는 반복마다 새 `tempfile.TemporaryDirectory()` 를 쓴다. 디렉터리 스캔 방식(⑴)에서도 두 번 다 `part-0000` 이다.**
monkeypatch 로 넣고 **46 OK** 를 확인했다 (§5-5).

**Matthew 가 위험을 잘못 짚었고, 진짜 회귀는 표시하지 않았다.**

### 고칠 것

1. m-01 **§4.4 에 좁은 길을 명시한다** — *"파싱 실패(`ValueError`)는 `validate_event()` 가 문제로 보고하지 않는다. `_partition_key()` 가 계속 던진다. `tests/test_sink.py:108 test_unparsable_timestamp_is_reported` 가 그 계층 분리를 고정한다."*
2. m-01 **§8.3 표에 `test_unparsable_timestamp_is_reported` 를 추가**한다.
3. m-01 **§8.3 의 `test_same_input_gives_same_digest` ★ 표시를 내린다** — 근거는 §5-5 의 실행 결과.

---

## C-5 · m-03 이 `economics.py` 의 입력 자료구조를 정의하지 않는다 — C1 에 없는 테이블을 전제한다

### 무엇이 적혀 있나

`story-m-03-economics-kr.md` §4.2 · §4.7 · T5 · T7 이 일관되게 `order` 를 받는 함수를 지시한다:

```python
has_cost_basis(order)  :=  주문의 모든 품목에 unit_cost 값이 존재한다      # §4.2
cogs(order)  =  Σ (unit_cost × quantity)                                # §4.2

def cogs(order) -> MetricValue:                                          # §4.7
    ...
    return MetricValue.ok(sum(i["unit_cost"] * i["quantity"] for i in order["items"]), ...)
```

T5: `has_cost_basis(order) -> bool` · `cogs(order) -> MetricValue` · `revenue(orders) -> MetricValue`
T7: *"`has_cost_basis` — 전 품목에 `unit_cost` 있음/일부 없음/전부 없음"*

### 실측 — `order`·`items`·`unit_cost` 가 C1 에 하나도 없다

`.agent-team/04-architecture/data-model-erd.md` §1.1:

| 테이블 | C1 구현 |
|---|---|
| **`events`** | ✅ |
| `orders` | **❌** |
| `order_items` | **❌** |
| `products` | **❌** |
| `customers` | ❌ |

> 문서 머리말: *"**C1 에 구현된 테이블은 `events` 하나다.** 나머지는 정본이 요구하지만 존재하지 않는다."*

그리고 `events` 22컬럼에 **`unit_cost` 가 없다** (`schema.py:EVENT_FIELDS` 실측 — `unit_price` 는 있고 `unit_cost` 는 없다).
`purchase` 이벤트는 **주문 단위 1행**이라 품목 목록이 원리적으로 없다 —
m-07 픽스처의 `DQ-09` `reason_detail` 이 그 사실을 이미 적고 있다:
*"`discount` 필드가 22컬럼에 없고, `purchase` 이벤트는 주문 단위 1행이라 품목 합계를 재구성할 수 없다"*.

### 스토리가 답하지 않는 것 — 전부 구현자가 발명해야 한다

| 질문 | 스토리의 답 |
|---|---|
| `order` 는 어떤 dict 인가? 키가 무엇인가? | **없다** |
| `order["items"]` 는 어디서 오나? `purchase` 이벤트에는 품목이 없다 | **없다** |
| 품목을 만들 수 없을 때 `items` 는 `[]` 인가 `None` 인가? 그 둘의 `has_cost_basis` 판정은? | **없다** |
| `revenue(orders)` 의 `orders` 는 `purchase` 이벤트 리스트인가, 그것을 `order_id` 로 묶은 것인가? | **없다** |
| C1 에서 `cogs()` 가 `ok` 를 돌려주는 경우가 존재하나? | **§4.10 표가 "시뮬레이터 생성분 ✅ `products.parquet` 에서" 라고 적었으나 그 파일이 C1 에 없다** |

§4.10 의 그 ✅ 는 **C1 에서 거짓이다.** m-01 §9.2 자신이 *"6개 추가 테이블 — C1 범위 밖"* 이라고 적었다.

### 왜 critical 인가

`economics.py` 의 입력 형태는 **혼자 쓰는 내부 구현이 아니다.**
`kpi.py`(M-04)가 부르고, `publish.py`(M-06)가 `partition_by_source()` 로 나눠 두 번 부른다(m-03 §4.6).
**세 스토리 어디에도 공통 정의가 없다.** Phillip 이 M-03 에서 발명한 형태와 M-04·M-06 이 기대하는 형태가
다르면 Phase 2 → 2'' 사이에서 조용히 어긋난다. 그때는 이미 `MetricValue`·`Basis`·`blocked_by` 사슬이 그 위에 얹혀 있다.

체크리스트가 요구한 판정 기준 — *"Phillip 이 이 파일 하나만 읽고 구현을 시작해 끝까지 갈 수 있는가"* — 에
**`cogs()` 한 함수에서 걸린다.** m-03 은 40KB 짜리 스토리이고 §4.1·§4.2 가 *"왜 원가율을 곱하면 안 되는가"* 를
제1원리로 훌륭하게 설명한다. **그런데 무엇을 인자로 받는지를 안 적었다.**

### 고칠 것

1. **m-03 §4.7 에 `Order` 형태를 하나로 못박는다.** 예:
   ```python
   # C1 의 order 는 events 의 purchase 1건에서 만든다. 품목 목록이 없다.
   Order = TypedDict("Order", {"order_id": str, "order_amount": int,
                               "items": list[OrderItem] | None,   # ← C1 에서는 항상 None
                               "treatment_id": str | None, "coupon_used": bool})
   ```
2. **C1 에서 `has_cost_basis()` 가 출처와 무관하게 항상 `False` 라는 것을 명시한다.**
   그것이 §4.2 `EC-2` 의 요점(*"결과는 같다 — 그러나 이유가 다르다"*)과도 맞는다.
   `items is None` 을 `NO_COST_BASIS` 로 볼지 `PRECONDITION_MISSING`(`order_items` 테이블 부재)으로 볼지도 정한다 —
   **`blocked_by[].kind` 가 9종으로 나뉜 이유가 정확히 이것이다**(`ADR-0009`).
3. **§4.10 표의 `unit_cost` 행 ✅ 를 고친다** — *"시뮬레이터가 생기는 다음 사이클에 `products.parquet` 에서. **C1 에는 그 파일이 없다.**"*
4. **`MetricValue`·`Basis` 를 어느 파일에 두는지 확정한다.**
   지금 m-03 §6.1 은 *"`schema.py` — **조건부 수정** — `MetricValue` 를 여기 둘 경우"*,
   m-04 §6.1 은 *"**조건부** — `MetricValue` 를 여기 둘 경우 (M-03 과 합의)"* 로 **양쪽이 서로에게 미룬다.**
   두 스토리는 **병렬 Phase 2** 다(프론트매터 실측). 합의할 자리가 없다.
   → **M-02 가 `MetricStatus`·`ReasonCode` Enum 을 두는 파일과 같은 자리**로 W3 가 지정하면 끝난다.
   m-02 §4.6 이 이미 *"어휘(Enum)만 먼저 두면 M-03·M-04 가 같은 것을 두 번 정의하지 않는다"* 라는 원칙을 세웠다 — **그 원칙을 dataclass 에도 적용하면 된다.**

---

# 2. noncritical — 리스크로 기록하고 진행 가능 (8건)

## N-1 · 7개 스토리가 `team` 소유 파일 편집을 지시한다 — 그런데 추가할 것이 하나도 없다

**m-03·m-04·m-05·m-06·m-07·m-08·m-09 §6.1** 전부에 같은 줄이 있다:

```
| `.agent-team/04-architecture/tools/ownership.json` | **수정** — 새 파일 `planned` 등록 |
```

**실측 ①** — 그 파일의 소유자는 Phillip 이 아니다:

```
$ python3 -c "... owners_of('.agent-team/04-architecture/tools/ownership.json') ..."
[('team', '.agent-team/**')]
```

**실측 ②** — 등록할 것이 없다. `planned` 63개에 7개 스토리가 만드는 파일이 **전부 이미 들어 있다**:
`kpi.py`·`economics.py`·`validate.py`·`publish.py`·`freeze.py`·`config_loader.py`·`contracts.py`·`errors.py` ·
`economic_config.yaml`·`gate1_lock.yaml`·`requirements*.txt`·`measurement_contract.md`·`gate1_checklist.md` ·
`docs/contracts/.../*.schema.json` 7종 · `test_neutrality`·`test_economics`·`test_kpi_definitions`·`test_kpi_values`·
`test_quality_checks`·`test_publish_contract`·`test_publish_atomicity`·`test_freeze`·`test_config_loader`.

**모순도 있다.** d-02 §6.2 는 `.agent-team/**` 를 *"읽기만"* 으로 적었다. 같은 저장소 같은 웨이브에서 스토리끼리 반대로 말한다.
그리고 7개 스토리가 같은 JSON 을 각자 고치면 **충돌만 난다.**

**→ 7곳 전부에서 그 줄을 뺀다.** T9/검증 단계에는 `check_ownership.py` **실행**만 남긴다 (그건 읽기다).

## N-2 · `ownership.json` 의 `planned` 가 Jonnathan 개정 이후 낡았다 — 그리고 아무도 안 고친다

| `planned` (W2, James) | d-01·d-02 §6.1 (Jonnathan 개정 반영) |
|---|---|
| `MetricValue.tsx` · `SourceSplit.tsx` · `NoticeList.tsx` · `ProvenanceBar.tsx` · `EmptyState.tsx` | `MetricCell` · `StateChip` · `SourceColumns` · `VerdictBanner` · `ImpactChain` · `CoverageTable` · `IngestionTimeline` · `NoticeBar` |
| `design-rules.css` | + **`state-rules.css`** |
| 관측 페이지 6종 | + **`(observability)/triggers/page.tsx`** |
| — | + **`lib/format/**`** |

**스토리 쪽이 옳다.** `contract-reconciliation.md` §3-① 이 라우트·컴포넌트 개명을 정본으로 기록했고
`design-handoff.md:96` 이 *"**`MetricCell` 부터 만든다**"* 라고 지시한다. `dashboard-architecture.md:64-68` 이 개정 전 목록이다.

**검사는 통과한다** — `dashboard/**` → `andrew` 규칙이 전부 덮으므로 `check_ownership.py` 는 PASS 다(확인).
다만 d-01·d-02 는 `ownership.json` 을 만지지 않으므로(그건 맞다) **이 낡은 목록은 영원히 안 고쳐진다.**
`planned` 를 인벤토리로 믿는 사람이 없는 파일 5개를 찾고 있는 파일 4개를 못 찾는다.

**→ N-1 과 같은 결론.** `ownership.json` 갱신은 `team`(리드/W3)이 **한 번에** 한다.

## N-3 · "타입으로 막는다"에 강제 수단이 이 저장소에 없다

m-03 §4.5 — *"`economics.py` 의 함수 시그니처에 `ProductGenerationConfig` 가 등장하지 않는다. 원가율을 손에 넣을 방법이 **타입 수준에서** 없다."*
m-03 T-5 — *"`def cogs(...) -> float` … **`0.0` 을 돌려줄 방법이 타입에 없어야 한다**"*
m-04 §4.8 R-8 — *"반환이 **항상 `MetricValue`**. `0.0` 을 돌려줄 방법이 타입에 없다"*

**이 저장소에 타입 검사기가 없다.** m-01 §7.1 자신이 적었다 — *"lint·build·타입 검사는 이 저장소에 정의되어 있지 않다"*(charter §6.3).
m-05 AC-1 도 *"lint·타입 검사 도구를 넣지 않는다 — 없는 게이트를 만들지 않는다"* 로 못박았다.

→ `-> MetricValue` 라고 적고 `return 0.0` 해도 **아무것도 잡지 않는다.** Python 은 duck typing 이라
`CostAccountingConfig` 자리에 `ProductGenerationConfig` 를 넘겨도 통과한다.

**실제로 강제하는 것은 셋이고, 셋 다 스토리에 이미 있다:**
① `MetricValue.__post_init__` 의 불변식 검사(m-03 §4.7) ② `test_config_loader.py` 의 속성 부재 단언(m-03 T8) ③ `test_neutrality.py` 소스 검사(m-03 T6).
**문제는 수사(修辭)가 강제인 것처럼 읽힌다는 점**이고, 구현자가 ①②③ 을 "부수적"으로 볼 위험이다.

**→ 값싼 보강 하나.** `test_economics.py`·`test_kpi_values.py` 에 반환 타입 전수 검사 1건:

```python
def test_every_public_function_returns_metric_value(self):
    for name, fn in inspect.getmembers(economics, inspect.isfunction):
        if name.startswith("_") or fn.__module__ != economics.__name__: continue
        ... # 대표 입력으로 호출해 isinstance(result, MetricValue) 단언 (has_cost_basis 등 bool 반환은 명시 제외 목록)
```

10줄이다. ETHOS §1 — *"테스트가 가장 싼 호수다."* 그리고 이것이 **없는 게이트를 만드는 것이 아니다** — 기존 `unittest` 안이다.

## N-4 · `test_neutrality.py` 6종의 **스캔 범위**가 정해지지 않았다

m-03 T6 이 6종을 표로 정의했다. 방향은 옳고 `test_isolation.py` 와 같은 패턴이라 재발명도 아니다. 세 곳이 비었다:

| 검사 | 빈 곳 |
|---|---|
| `test_source_classification_is_single_sourced` | *"`simulator_version`+`random_seed` 를 함께 참조하는 파일이 `schema.py`·`sink.py` 뿐"* — **스캔 대상이 `src/` 인가 저장소 전체인가?** `tests/test_sink.py:47 commerce_event()` 가 둘 다 pop 한다. 저장소 전체면 실패한다 |
| 같은 검사 | m-03 §4.6 이 `publish.py` 에서 `partition_by_source(events)` 를 부른다. **그 함수를 어느 파일에 두는지 m-03·m-06 어디에도 없다.** `sink.event_source()` 를 부르면 통과하고, 두 필드명을 직접 보면 실패한다 |
| `test_no_hardcoded_krw_in_economics` | *"숫자 리터럴에 금액이 없음 (0·1 등 구조적 상수 제외)"* — **금액과 구조적 상수를 AST 로 가르는 규칙이 없다.** `100`(퍼센트)·`2`(반올림 자릿수)는? |

**→ 세 검사의 스캔 경로와 예외 목록을 스토리가 못박는다.** 특히 `partition_by_source` 의 위치는 **아키텍처 결정**이지 구현자 취향이 아니다.

> **덧 — N-1 검사의 한계 하나.** `test_economics_has_no_source_literal` 은 `if source == COMMERCE:` 를 잡는다.
> 그런데 `if record.get("simulator_version") is not None:` 은 **문자열 `commerce`·`simulator` 가 안 나오므로 통과한다.**
> 그 우회를 잡는 것이 바로 `test_source_classification_is_single_sourced` 인데, 그게 위에서 범위가 안 정해진 검사다.
> **두 검사가 같이 있어야 의미가 있다는 사실을 스토리가 적어야 한다.** m-03 T6 이 *"한계를 먼저 적는다"* 로 상대·동적 import 는 적었으나 이 조합은 안 적었다.

## N-5 · 스토리 의존 그래프가 비대칭이다 — 프론트매터가 실행 순서를 정하는 자리다

프론트매터 실측:

| 스토리 | `blocked_by` | 다른 스토리의 `blocks` |
|---|---|---|
| m-06 | `["M-02","M-03","M-04"]` | m-07 이 `blocks: ["M-06 게시 (data_quality_report)"]` ← **m-06 쪽에 없다** |
| m-07 | `["M-01"]` | m-05 가 `blocks: ["M-07 (#48) DQ-17 해소"]` ← **m-07 쪽에 없다** |

그리고 **m-06 본문 §8.1 은 M-05 를 선행으로 적는다** (*"`jsonschema` 가용 여부 → 자기검증 수단"*) — 프론트매터와 불일치.

**실행으로 확인한 실질 의존:**
```
$ python3 .agent-team/04-architecture/tools/validate_examples.py
BLOCKED — jsonschema 가 설치되지 않아 검증을 실행하지 못했다.
통과로 적지 않는다.
```
m-06 AC *"픽스처 2벌(14파일)이 여전히 계약을 통과한다"* 는 `jsonschema` 없이 **확인할 수 없다.** 그건 M-05 산출물이다.

**→ 양방향을 맞춘다.** m-06 `blocked_by` 에 `M-05`(픽스처 검증 수단)·`M-07`(`data_quality_report` 생산자)을 넣는다.

## N-6 · `gen_event_schema_doc.py` 는 stdout 으로 쓴다 — 스토리의 "재생성" 명령이 아무것도 재생성하지 않는다

스크립트 말미가 사용법을 직접 적고 있다:
```bash
python3 scripts/gen_event_schema_doc.py > docs/event_schema.md      # ← 리다이렉션이 있다
```

m-01 §7.1 · T4, m-02 §6.1 은 **리다이렉션 없이** `python3 scripts/gen_event_schema_doc.py` 만 적었다.
그대로 치면 화면에 출력만 되고 파일은 안 바뀐다. §7.1 이 *"실행 가능한 명령 — **이것뿐이다**"* 라고 선언한 절이라 더 아프다.

**참고 — 현재는 일치한다:** `python3 scripts/gen_event_schema_doc.py` 출력과 `docs/event_schema.md` 를 diff → **IDENTICAL** (§5-8).
m-09 AC-3 의 *"생성 출력이 `docs/event_schema.md` 와 일치함이 조건에 포함된다"* 는 현재 기준선에서 만족한다.

## N-7 · m-06 T1 *"복사본 머리에 출처 주석"* — `.schema.json` 은 순수 JSON 이라 주석을 넣을 수 없다

7개 스키마 전부 `json.load()` 로 파싱된다(확인). `//` 나 `/* */` 를 넣으면 파일이 깨지고,
`validate_examples.py`·`check_zero_fill_rejected.py`·`contracts.py` 가 전부 못 읽는다.

**→ *"최상위에 `$comment` 키로 출처를 적는다"* 로 고친다.** JSON Schema 표준 키워드이고 검증에 영향이 없다.
그리고 그 `$comment` 자체가 T6 "의도된 차이" 목록의 첫 항목이 된다 — 7파일 전부가 원본과 달라지므로 **목록에 미리 적어야 한다.**

## N-8 · m-04 §4.9 의 "한계 칩" 을 담을 자리가 계약에 없다

m-04 §4.9 · d-02 규칙 V-7 — *"`campaign_response_count` 는 값이 나오되 화면이 **`한계` 칩**을 붙인다."*

**실측** — `kpi_report.schema.json` `metrics[].items` 는 `additionalProperties: false` 이고 props 11종뿐:
`name · layer · role · population · window · denominator_definition · formula · definition_ref · source_events · value · blocks`.
`metric_value` 에도 한계 표시 필드가 없다(`derived`/`derivation` 은 파생 여부지 정밀도 한계가 아니다).

담을 수 있는 유일한 곳은 리포트 최상위 `notices[]` 의 `level: "limitation"` 인데 **그건 지표 단위가 아니라 리포트 단위다.**

→ d-02 가 `campaign_response_count` 라는 **이름을 화면에 하드코딩**하게 된다. **두 번째 정본이다** — C-1 과 같은 부류.
지표 1종에 국한되고 `notices[].message` 에 지표명을 적어 대응할 여지가 있어 noncritical 로 둔다.

**→ 최소 조치:** d-02 §V-7 에 *"한계 목록의 정본은 `notices[]` 이고, 화면은 `notice.code` 로 매칭한다.
   지표 이름을 화면 코드에 적지 않는다"* 를 명시하고, m-06 에 `CAMPAIGN_RESPONSE_UNDERCOUNT` notice 발행 task 를 추가한다.

---

# 3. Matthew §10 "Thomas 5건" 에 대한 답

## 3-1 · m-03 `test_neutrality.py` 6종이 실제로 창구 중립성을 잡는가

**부분적으로. 방향은 옳고 재발명도 아니다. 세 곳을 채우면 충분하다.**

**옳은 것:**
- 소스 검사를 고른 판단이 맞다. m-03 T6 의 근거 — *"값 검사로는 '오늘 우연히 맞다'만 보인다. 소스 검사는 다음 사람이 분기를 넣는 순간 실패한다"* — 이 정확하다.
- `test_isolation.py` 의 AST 헬퍼를 **복사해 쓰되 봉인 파일을 고치지 않는다**(§7.2)는 처리도 옳다. 바퀴 재발명이 아니다.
- 한계(상대 import·동적 import·f-string)를 **먼저 적으라**고 지시한 것도 옳다.

**빈 곳 셋 — N-4 에 상술:**
1. `test_source_classification_is_single_sourced` 의 **스캔 대상 경로**가 없다. `tests/test_sink.py:47` 이 두 필드를 함께 참조한다.
2. **`partition_by_source()` 를 어느 파일에 두는지** 어느 스토리에도 없다. 그게 `publish.py` 안이면 통과하고 `economics.py` 로 새면 실패한다 — 그 경계가 정해지지 않았다.
3. `test_no_hardcoded_krw_in_economics` 의 **금액 판별 규칙**이 없다.

**추가로 짚을 것:** N-1(`test_economics_has_no_source_literal`)은 `if source == COMMERCE:` 는 잡지만
`if record.get("simulator_version") is not None:` 은 **못 잡는다** — 문자열 `commerce`·`simulator` 가 안 나온다.
그 우회를 잡는 것이 N-4 검사인데 그게 1번에서 범위가 안 정해진 검사다. **둘이 짝이라는 사실을 스토리가 적어야 한다.**

그리고 N-3 — **`ProductGenerationConfig` 를 "타입으로 막는다"는 이 저장소에서 강제되지 않는다.**
실제 방어는 `test_config_loader.py` 의 속성 부재 단언이다. 그 사실을 스토리가 뒤집어 적었다.

## 3-2 · m-01 §8.3 R-3 — 파티션 수정이 `test_same_input_gives_same_digest` 를 깨뜨리는가

**깨뜨리지 않는다. 실행으로 확인했다. Matthew 가 잘못된 곳을 가리켰다.**

```python
# tests/test_sink.py:216-225
def test_same_input_gives_same_digest(self) -> None:
    records = [simulator_event(day=1), simulator_event(day=2)]
    digests = []
    for _ in range(2):
        with tempfile.TemporaryDirectory() as tmp:      # ← ★ 반복마다 새 디렉터리
            with sk.EventSink(tmp) as s:
                s.write_events(records)
            digests.append(s.manifest()["sha256"])
    self.assertEqual(digests[0], digests[1])
```

**반복마다 새 `tempfile.TemporaryDirectory()` 다.** 디렉터리 스캔 방식(§4.3 ⑴)에서 두 번 다 빈 디렉터리를 만나므로
두 번 다 `part-0000` 이다. `_digest()` 가 `path.name` 을 해시에 넣어도 값이 같다.

**실행 확인 (§5-5):** `_write_partition` 을 디렉터리 스캔 구현으로 monkeypatch → **Ran 46 · OK.**
`test_chunking_creates_multiple_parts`(같은 인스턴스가 같은 날짜에 3회 flush)도 통과한다 — 스캔 결과가 캐시와 같은 값을 준다.

**→ m-01 §8.3 의 ★ 표시와 `readiness-report` §7 R-3 을 내린다.**
*"구현자가 판단해야 하는 자리다"* 로 남긴 것은 **10줄짜리 테스트를 읽으면 5분에 닫히는 문제**였다.
W3 이 그것을 안 하고 W5 로 넘기면, 구현자는 위험 표시를 보고 방어적으로 설계를 바꿀 수 있다.

**★ 대신 진짜 회귀는 C-4 다.** `test_unparsable_timestamp_is_reported` 가 타임존 수정에서 실제로 깨진다(실행 재현).
**Matthew 는 없는 위험을 표시하고 있는 위험을 놓쳤다.**

## 3-3 · m-06 §4.8 B-11 우회가 정당한가 — `ALL_CLEAR` 가드 + `headline_detail` 로 덮는 것이 충분한지

**질문이 낡았다. 우회는 이미 없다.** 리드 판정 B-11 반영으로 §4.8 이 *"화면 우회를 쓰지 않고 계약을 고친다"* 로 바뀌었고,
d-02 §4.8 에서 우회 코드가 제거됐다(스토리 자체 기록).

**그 방향에 이견 없다.** `check_ownership.py` 가 `docs/contracts/**` 를 Phillip 소유로 판정하는 것을 직접 확인했다:
```
$ owners_of('docs/contracts/measurement-publish/v1/index.schema.json')
[('phillip', 'docs/contracts/**')]
```
저장소에 들어갈 진짜 계약을 W5 가 만드는 것이 맞고, *"계약이 옳으면 필요 없는 코드는 계약이 고쳐진 뒤에도 남는다"* 는 논거가 정확하다.
`REJECTED_EVENTS` 와 `CONTRACT_VIOLATION` 을 **조치 주체로 가른 것**(`ADR-0009` 와 같은 원칙)도 옳다.

**남은 결함은 우회가 아니라 우선순위 값이다 — C-2.** `SINK_EMPTY` 가 `CHECKS_NOT_RUN` 아래로 밀려서
**오늘의 실제 상태에서 첫 화면이 원인 대신 결과를 말한다.** 그리고 §4.8 과 §7.2 가 서로를 부정한다.

## 3-4 · m-07 §4.7 F-D — 위반 데이터 생성 방법 a 가 옳은지

**옳다. 전제도 맞다. 다만 한 줄이 빠졌다.**

**전제 확인** — `validate.py` 의 입력이 저장된 파일이라는 것:
```python
# src/measurement/sink.py:305-321
def read_events(root):
    for path in sorted((root / "events").rglob("part-*")):   # ← 파일을 읽는다. Sink API 가 아니다
```
맞다. Sink 를 우회해도 검사가 성립한다.

**방법 a 의 실행 가능성 확인** — `_write_rows` 는 `sink.py:283` 의 **모듈 수준 함수**다.
테스트에서 `sk._write_rows(path, rows, sk.SinkFormat.JSONL_GZ)` 로 직접 부를 수 있다. 제품 코드에 문을 열지 않는다.

**b 를 배제한 근거도 옳다** — *"제품 코드에 테스트 전용 문을 여는 것은 피한다."*
**c 를 배제한 것도 옳다** — `strict=False` 를 *"무효 데이터를 저장한다"* 로 재해석하면 `MEA-003` 해석이 바뀌고 m-01 §4.6 T-3 판정과 충돌한다.

**빠진 한 줄:** **테스트가 파티션 디렉터리 구조까지 만들어야 한다.**
`read_events()` 는 `root/events/date=YYYY-MM-DD/part-*` 를 `rglob` 한다. `_write_rows(path, ...)` 만 부르면
경로를 테스트가 직접 조립해야 하고, 이름 규약이 틀리면 **`read_events()` 가 조용히 0건을 돌려준다** —
그러면 검사가 `vacuous` 로 나오고 *"위반을 잡았다"* 가 아니라 *"검사할 게 없었다"* 가 된다. **이건 통과처럼 보이는 실패다.**

→ m-07 §4.7 a 항목에 경로 형태를 예시로 박는다: `root/events/date=2025-10-01/part-0000.jsonl.gz`.
그리고 **위반 데이터를 넣은 뒤 그 검사가 `fail` 인지 단언**하도록 AC 를 쓴다 — `vacuous` 를 성공으로 세지 않게.

## 3-5 · d-01/d-02 의 `?? 0` 방어가 충분한가 — 런타임 방어가 더 필요한지

**금지 패턴 나열은 충분하다. 런타임 방어도 이미 옳은 층에 있다. 문제는 방어가 아니라 "올바른 형태"가 동작하지 않는다는 것이다 — C-1.**

**충분한 것:**
- 금지 패턴 8종 나열이 실제 관용구를 잘 덮는다 (`?? 0`·`|| 0`·`Number(value)`·`(value ?? 0).toLocaleString()`·`value?.toLocaleString() ?? '0'`·`counts[k] || 0`·`parseFloat(v) || 0`·`value.toFixed(1)`).
- **`value.toFixed(1)` 을 목록에 넣은 것이 특히 좋다** — 그게 `?? 0` 으로 가는 입구다. 그 인과를 스토리가 명시했다.
- **런타임 방어가 이미 있다.** d-01 **AC-6**: *"★ `status !== "ok"` 인데 `value !== null` 이면 **던진다** — 0 채우기의 마지막 방어선"*.
  이건 **읽는 쪽 경계에서 계약 위반을 잡는 것**이고 정확히 옳은 층이다. 더 얹을 필요 없다.
- `counts[name] || 0` 을 *"키 부재는 0 이 아니라 계약 위반"* 으로 처리한 것도 옳다 — 계약이 `minProperties: 16`·22 고정·`minItems: 9` 로 키 존재를 보장한다(실측 확인).

**부족한 것 — 방어가 아니라 대안이다:**
`m.value_formatted` 가 계약에 없다(C-1). 금지 패턴을 다 지키면 **숫자를 표시할 방법이 하나도 남지 않는다.**
막다른 길에 몰린 구현자는 규칙을 어긴다. **그리고 이 경우 어기는 방향이 정확히 `?? 0` 이다.**

→ **런타임 방어를 추가하지 말고 C-1 을 고쳐라.** 방어가 부족한 게 아니라 **정상 경로가 없다.**

> 하나만 덧붙이면, d-02 §7 의 grep 체크리스트 `grep -rn '?? 0\|\|\| 0\|Number(' dashboard/src` 는
> `Number(` 를 지표 값과 무관한 자리에서도 잡는다. 그리고 d-01:431 의 `process.env.AIROI_RESULTS_DIR ?? resolve(...)` 처럼
> **정당한 `??`** 도 있다. *"지표 값 경로 0건"* 이라는 단서가 붙어 있으므로 사람 판단이 전제인데,
> **자동 검사처럼 읽히는 형식**이라 W6 에서 "grep 통과 = 검증됨" 으로 계산될 위험이 있다. §7 에 *"이 grep 은 후보 목록이고 판정은 사람이 한다"* 를 적으면 닫힌다.

---

# 4. 8대 치명적 실수 — 실제로 발견된 것

| # | 실수 | 발견 | 근거 |
|---|---|---|---|
| 1 | **바퀴 재발명** | **없음** | 오히려 잘 회피했다. 토큰 생성기 **이식**(d-01) · `test_isolation.py` 헬퍼 **복사 사용, 봉인 파일 미수정**(m-03 §7.2) · `kpi.py` 가 `OBSERVABLE_METRIC_SOURCES` 를 다시 만들지 않음(m-04 §8.2) · 계산은 `economics.py`/이름은 `kpi.py` 로 중복 차단. **W3 의 강점이다** |
| 2 | 잘못된 라이브러리/버전 | 없음 (범위 한계는 남음) | Matthew 가 R-1 로 스스로 표시했다. lock 버전 미확정을 *"설치해 해석하라"* 로 넘긴 것은 `dependency-plan.md` §3.3 지시에 맞다 |
| 3 | **잘못된 파일 위치** | **N-1 · N-2** | 7개 스토리가 `team` 소유 `ownership.json` 편집 지시(도구로 소유자 확인) · `planned` 의 대시보드 항목이 Jonnathan 개정 이후 낡음 |
| 4 | **회귀** | **C-4** | `test_unparsable_timestamp_is_reported` 가 타임존 수정에서 깨진다 — **실행 재현.** 스토리 §8.3 에 없다 |
| 5 | UX 무시 | 없음 (반대 방향으로 문제) | d-01·d-02 가 Jonnathan 설계를 성실히 옮겼다. **문제는 옮긴 것을 계약과 대조하지 않은 것** — 아래 별항 |
| 6 | **모호한 구현** | **C-5 · N-4** | `economics.py` 의 입력 자료구조 미정의 · `MetricValue` 를 둘 파일을 두 스토리가 서로에게 미룸 · `test_neutrality` 스캔 범위 미정 · `partition_by_source` 위치 미정 |
| 7 | 완료 거짓말 | **없음** | 정직하다. m-06 §7.2 가 스크래치패드 실행을 저장소 검증에서 명시적으로 뺐고, `validate_examples.py` 자체가 `BLOCKED` 를 출력한다(실행 확인). §0-③ · §9.1 DoD 의 *"미실행을 통과로 적지 않는다"* 가 11/11 에 있다 |
| 8 | 과거 학습 무시 | 없음 | §8 연속성이 머지된 PR 4건·확립 패턴·병렬 스토리 겹침 규칙을 담았다 |

## ★ 8대 목록에 없는 유형 — **상류 문서를 검증 없이 이식했다**

**C-1 · C-2 · N-8 이 전부 같은 형태다.**

| 스토리가 옮긴 것 | 어디서 | 계약과 대조했나 |
|---|---|---|
| `m.value_formatted` | `dashboard-agents-design-constraints.md:44` | ❌ `metric_value` 에 없고 `additionalProperties: false` |
| `headline_code` 우선순위 | `ux-flow-map.md` §1.1 7단계 | ❌ `empty-sink` 픽스처와 모순 |
| "한계 칩" | `missing-state-spec.md` V-7 | ❌ `metrics[]` 에 담을 자리 없음 |

`readiness-report-kr.md` §2 D2 는 *"인용 경로 45종 전수 존재 검사 — 실패 0건"* 을 D2 충족 근거로 든다.
**경로가 존재하는지만 봤다. 인용한 내용이 계약과 맞는지는 안 봤다.**

체크리스트 2단계는 *"**아키텍처 심층 분석** — API 패턴·데이터 계약"* 을 요구한다.
**"인용 경로 존재"는 그 요구의 절반이다.** 나머지 절반 — *"인용한 값이 계약에 실재하는가"* — 가 빠졌다.

> **다음 사이클 권고:** D2 검사에 한 줄 추가. *"화면·게시물이 읽는 **필드 이름**은 전부 `schemas/*.schema.json` 에서 grep 으로 확인한다."*
> 이번 3건 모두 **grep 한 번**이면 W3 에서 잡혔다.

---

# 5. 실행한 검증 명령과 결과

**전부 읽기 전용이다.** 저장소·`Ecommerce_Service`·`Plan/` 을 수정하지 않았다.
monkeypatch 실험은 `python3 -c` 인메모리이고 파일을 만들지 않았다. 문서 생성 diff 만 스크래치패드에 출력했다.

| # | 명령 | 결과 |
|---|---|---|
| 1 | `python3 -m unittest discover -s tests` | **Ran 46 · OK** — 기준선 확인 |
| 2 | `python3 .agent-team/04-architecture/tools/check_ownership.py` | **PASS** — 겹침 0 · 빠짐 0 · 봉인 격리 OK · `Phillip 42 ∩ Andrew 29 = 0` |
| 3 | `python3 .agent-team/04-architecture/tools/validate_examples.py` | **BLOCKED** — *"jsonschema 가 설치되지 않아 검증을 실행하지 못했다"* |
| 4 | `check_zero_fill_rejected.py` (소스 확인) | **BLOCKED** — 같은 이유 (`ImportError` → `SystemExit(2)`) |
| 5 | **파티션 ⑴ 시뮬레이션** — `_write_partition` 을 디렉터리 스캔으로 monkeypatch 후 전체 테스트 | **Ran 46 · OK** → **R-3 은 위험이 아니다** (§3-2) |
| 6 | **타임존 ⑵ 시뮬레이션** — `validate_event` 가 파싱 실패를 문제로 보고 | **FAILED (failures=1)** — `test_unparsable_timestamp_is_reported` → **C-4** |
| 7 | **타임존 ⑵ 좁은 길** — 파싱 실패는 통과, naive 만 거부 | **Ran 46 · OK** → C-4 의 해결책 |
| 8 | `python3 scripts/gen_event_schema_doc.py` ↔ `docs/event_schema.md` diff | **IDENTICAL** — m-09 AC-3 이 현재 기준선에서 만족 |
| 9 | 품질 픽스처 파싱 (`data_quality_report.json` × 2) | `empty-sink` **checks 18** {not_run 10 · vacuous 7 · blocked 1} · **`DQ-06` = not_run + BLOCKED** / `commerce-connected` **checks 7 vs `reported_checks` 6** → **Q-1·Q-2·Q-3 전부 재현** |
| 10 | `index.json` 픽스처 파싱 × 2 | `empty-sink` `SINK_EMPTY` + `checks_not_run 10`·`checks_blocked 1` → **C-2** / `commerce-connected` `QUALITY_VIOLATION` + `rejected_events 217` |
| 11 | `common.schema.json` `$defs.metric_value` 파싱 | props 11종 · **`additionalProperties: false`** · **`value_formatted` 없음** → **C-1** |
| 12 | `kpi_report.schema.json` `metrics[].items` 파싱 | props 11종 · `additionalProperties: false` · 한계 표시 필드 없음 → **N-8**. 단 `derived`/`derivation` 은 `metric_value` 에 있으므로 **G-8 ④ 는 성립한다**(S-2 확인) |
| 13 | `data_quality_report.schema.json` `checks[].allOf` 파싱 | **5건** — `status`↔`reason_code` 제약 **없음** → Matthew 의 Q-2 분석이 정확하다 |
| 14 | `ownership.json` `planned` 63건 ↔ 11개 스토리 §6.1 대조 | 측정 계층 신규 파일 **전부 이미 등록됨** → **N-1** / 대시보드 5종이 낡음 → **N-2** |
| 15 | `check_ownership.owners_of()` 직접 호출 | `ownership.json → team` · `tests-with-deps.yml → sealed` · `dashboard/** → andrew` (신규 컴포넌트 포함) |
| 16 | `gh issue list --state all` (AI_ROI) | `#42`~`#49`·`#53`·`#54` **전부 OPEN** — Matthew 의 표와 일치 |
| 17 | `gh issue view 24 / 28 / 29` (Ecommerce_Service) | **전부 OPEN** — m-03 §4.10(`#24`) · m-04 §4.5(`#29`) · d-02 V-10(`#28`) 인용 확인 |
| 18 | `Ecommerce_Service/src/lib/server/commerce/orders.ts:116` | `const createdAt = new Date().toISOString();` → **UTC 기록 확인.** m-01 §4.1 D1-3 주장이 정확하다 |
| 19 | `git log --oneline` · `git status --porcelain` (AI_ROI) | `?? .agent-team/03-story-engineering/` + `_state/` 4건. **제품 코드 변경 0건** — Matthew §9 주장 확인 |

**BLOCKED 로 남은 것:**

| 항목 | 이유 |
|---|---|
| 계약 스키마 실제 검증 (`validate_examples.py` · `check_zero_fill_rejected.py`) | **`jsonschema` 미설치.** C-3 의 "픽스처가 실패한다"는 **스키마 규칙과 픽스처 값의 대조로 확정**했고 validator 실행으로는 확인하지 못했다. **통과로도 실패로도 적지 않는다** — 규칙 대조 결과만 적었다 |
| `python3 scripts/bench_sink.py 20000 30` | 실행하지 않았다. 이 리뷰의 렌즈 밖이고, 실행하면 파일을 쓴다 |
| 대시보드 관련 전부 | **`dashboard/` 가 존재하지 않는다.** `npm run tokens:*` · 화면 명제 17종 전부 확인 불가 |

---

# 6. 리드 판정 3건에 대한 의견

**세 판정 모두 방향에 이견 없다.** 각각에 대해 이 리뷰가 추가로 확인한 것과 남은 결함만 적는다.

## B-11 — 화면 우회 금지, 계약 자체를 고친다

**동의한다.** 그리고 `docs/contracts/**` 가 Phillip 소유라는 근거를 도구로 재확인했다(§5-15).
*"계약이 옳으면 필요 없는 코드는 계약이 고쳐진 뒤에도 남아서 아무도 지우지 못한다"* 는 논거가 정확하다.

**남은 결함:** 리드는 *"8종 우선순위를 계약이 정의한다"* 만 지시하고 **구체 순서를 지정하지 않았다.**
Matthew 가 채운 순서에 **C-2** 가 있다. 스토리 스스로 *"순서를 바꿀 근거가 있으면 바꾸되 PR 에 적는다"* 로 열어 뒀으므로
**W5 권한 안에서 닫을 수 있다.** 다만 픽스처와 대조할 이유를 W5 가 못 찾으면 그대로 들어가고 **GATE 1 에서 Lock 된다.**
→ **§4.8 표를 W3 단계에서 고치는 편이 싸다.**

**그리고 같은 논리를 C-1 에 적용해야 한다.** `value_formatted` 도 *"계약이 옳으면 화면이 포맷하지 않아도 되는"* 사례다.
B-11 을 계약 수정으로 푼 것과 **정확히 같은 자리, 같은 이유**다.

## G-8 — ④ 게시 시점 계산 (`derived: true` + `derivation`)

**동의한다. 그리고 스키마 무변경으로 성립한다는 것을 확인했다.**
`metric_value` 에 `derived`·`derivation` 이 실재하고, `kpi_report.metrics[].items.layer` 에 `customer_kpi` 가 있다(§5-11·12).
Matthew 의 S-2 판정(*"스키마 변경 0건"*)이 맞다.

`EventType` 16 → 19 를 배제한 근거도 맞다 — `tests/test_schema.py:45-47` 이 `assertEqual` 로 16종을 고정한다(실측).
**Lock 하려는 대상을 Lock 직전에 바꾸는 것**이라는 판단이 정확하다.

**이견 없음.**

## Q-2 (리드 지시문 §3 의 "계약 결함 3건 묶음") — 스키마로 막는 것을 W5 작업으로

**묶음 판정에 동의한다.** 세 결함 모두 재현 확인했다(§5-9).
그리고 Matthew 의 S-1 판정(*"`reported_checks == len(checks)` 는 JSON Schema draft 2020-12 로 표현 불가"*)이 **맞다** —
교차 필드·배열 길이 비교 키워드가 없고 `$data` 는 Ajv 확장이다. *"스키마에 적으려 시도하지 마십시오"* 를 스토리에 박은 것도 좋다.

**남은 결함: 아무도 픽스처와의 충돌을 처리하지 않았다 — C-3.**
`m-07 §7.2` 의 `Q-2` 제약을 넣으면 `empty-sink/data_quality_report.json` 의 `DQ-06` 이 실패하고,
`Q-3` 자기검증을 적용하면 `commerce-connected` 의 `reported_checks` 가 막힌다.
**그런데 m-06 T5·DoD 는 "픽스처 2벌(14파일)이 여전히 계약을 통과한다"를 AC 로 요구한다.**

→ 리드가 T6 에서 이미 만든 **"의도된 차이 목록"** 패턴을 픽스처에도 적용하면 닫힌다.
**의도된 실패 2건을 명시하면 그 실패가 제약이 작동한다는 증거가 된다.**

---

# 7. 이 리뷰의 한계 — 통과로 적지 않는다

| # | 한계 |
|---|---|
| **L-1** | **계약 스키마를 validator 로 실제 검증하지 못했다.** `jsonschema` 미설치(§5-3·4). C-3 은 **스키마 규칙과 픽스처 값의 대조**로 확정했고 validator 실행으로 재확인하지 못했다 |
| **L-2** | **`dashboard/` 가 존재하지 않는다.** d-01·d-02 에 대한 판단은 전부 **문서·계약 대조**이고 실행 확인이 아니다. C-1 은 계약 실측(`value_formatted` 부재)으로 확정했으나 화면에서 `undefined` 가 나오는 것을 눈으로 보지는 않았다 |
| **L-3** | **11개 스토리 총 452KB 를 전수 정독하지 않았다.** 렌즈(아키텍처 정합·패턴·엣지케이스·소유 경계)를 따라 §3~§4·§6~§9 를 중심으로 읽었고, m-08·m-09 는 AC·파일 목록·의존 관계만 봤다. **QA·인수조건 렌즈는 Matthias 의 몫이다** |
| **L-4** | **`bench_sink.py` 를 돌리지 않았다.** m-01 AC-4 의 성능 회귀 항목은 이 리뷰가 판단하지 않았다 |
| **L-5** | **m-04 의 47종 지표 정의를 하나씩 검산하지 않았다.** §4.5 의 22/6/19 분류와 `kpi-definition-v1.md` §8 의 대조는 하지 않았다 — Matthias §10-4 항목과 겹친다 |
| **L-6** | `project-context-kr.md`(32KB)는 D3 해시 계산법·검색 확인 버전 부분만 확인했다. **`source_hash` 재현은 하지 않았다** — Matthias §10-5 항목이다 |
