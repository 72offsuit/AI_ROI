---
story_key: M-01
epic: 범위 M — 측정 계층 (이슈 #42)
issue: "#53"
title: Event Sink 결함 3건 — 파티션 덮어쓰기 · strict=False 크래시 · 타임존 미강제
status: done   # W5 Phillip 완료 — AC-1~4 전부. 벤치 건수·바이트 정확 일치
owner: Phillip (W5-A)
phase: 1
blocked_by: []
blocks: ["M-07 (#48)", "데이터 생성 전체"]
source_hash: f9b50547bbb181fb
source_files: 17
---

# M-01 · Event Sink 결함 3건 (`#53`)

> **이 파일만 읽고 구현한다.** 다른 문서를 열지 않아도 되도록 필요한 것을 전부 여기 적었다.

---

# 0. 작업 전 — 매번 확인하는 3줄 *(task-graph §3 T3.2)*

| # | 절대 제약 | 어기면 |
|---|---|---|
| **①** | **git·이슈 권한은 L1(제안만)이다.** commit·push 는 사용자가 **"커밋해"/"푸시해"** 를, 이슈 생성·수정·PR 은 **"이슈 만들어"/"PR 올려"** 를 명시한 뒤에만. **승격을 스스로 추론하지 않는다.** merge · Issue close · 브랜치 삭제 · `push --force` · `reset --hard` · `rebase` 는 **항상 개별 승인**. `main` 직접 커밋 금지 · `git add -A` 금지(경로 명시) · `git add Plan` 금지 | 사용자 결정을 대신한 것이 된다 |
| **②** | **`Ecommerce_Service` 파일 변경 0건.** 별도 저장소이고 사용자가 명시적으로 제외했다. **읽기는 허용**된다. 편집이 필요해지면 **멈추고 보고한다** | charter §5 위반 |
| **③** | **결손을 0 으로 채우지 않는다.** 명시적으로 기록하고 의존 지표는 **계산 불가로 표시**한다. **미실행 검증을 통과로 표시하지 않는다** — 실행 불가는 `BLOCKED` 로 **이유와 함께** | ★ **이 프로젝트의 USP-1 이 끝난다** |

`[Source: AGENTS.md#반드시-지킬-것]` · `[Source: docs/GIT_WORKFLOW.md#6]` · `[Source: .agent-team/00-plan/charter.md#6.1]` · `[Source: .agent-team/00-plan/task-graph.md#3 W3]`
> 인용에는 전부 `[Source: 경로#절]` 을 붙였다. 원문 확인이 필요하면 그 경로를 연다.

---

# 1. 메타

| | |
|---|---|
| **대상 이슈** | `#53` — OPEN (2026-09-11 `gh issue list` 라이브 확인) |
| **관련 이슈** | `#44` (M-2, OPEN) |
| **담당** | Phillip · W5-A |
| **Phase** | **1** — 차단 요인 없음. `#54` 와 병렬 가능 |
| **왜 최우선인가** | **D1-1 이 데이터 소실형이다.** `data/raw` 에 쌓인 뒤 고치면 사라진 것은 돌아오지 않는다 `[Source: .agent-team/03-service-planning/gate1-lock-scope.md#2.3]` |
| **차단하는 것** | `#48`(M-07) — 품질 검사가 위반 데이터를 저장하려면 `strict=False` 경로가 필요한데 **지금 크래시한다** `[Source: .agent-team/04-architecture/data-quality-design.md#6]` |
| **커밋 type** | `fix` — `fix: Sink 재기록 시 파티션 덮어쓰기 해소 (M-2)` 같은 형태 `[Source: docs/GIT_WORKFLOW.md#3]` |

---

# 2. 스토리

> **`P-시뮬`**(다음 사이클 시뮬레이터 개발자)**로서 나는 기간을 나눠 여러 번 기록해도 앞 구간이 지워지지 않기를 원한다.**
> 왜냐하면 `SIM-012` 분할 불변성에 따라 시뮬레이터는 `advance()` 를 반복하며 기록하는데, **매번 앞 구간이 지워지면 데이터가 남지 않기** 때문이다.
> `[Source: .agent-team/03-service-planning/user-stories.md#US-3]`

> **`P-팀`**(측정 계층 구현자·리뷰어)**으로서 나는 커머스의 불완전한 레코드를 관용 모드로 받아도 수집이 죽지 않기를 원하고, 시각이 하루 밀리지 않기를 원한다.**
> 왜냐하면 `MEA-003` 이 *"커머스가 아직 제공하지 않는 필드가 있어도 수집이 실패하지 않아야 한다"* 를 요구하는데 **첫 시도에서 예외가 나고**, 커머스가 UTC 로 기록해 **파티션이 하루 어긋나기** 때문이다.
> `[Source: .agent-team/03-service-planning/user-stories.md#US-4]`

---

# 3. 인수 조건 (AC)

`#53` 수용 기준 + `user-stories.md` US-3·US-4 인수조건을 합친 것이다. **전부 검증 가능하다.**

## AC-1 · D1-1 파티션 보존

- [ ] 같은 root 에 **2건 기록 후 3건을 추가 기록**하면 `read_events()` 가 **5건**을 돌려준다 (현재 3건)
- [ ] 파트 번호가 **디렉터리의 현재 상태에서 이어진다** — 두 번째 실행이 `part-0000` 을 덮지 않는다
- [ ] `sink.py:113` 독트링이 **실제 동작과 일치한다** — append 면 append, 덮어쓰기면 그렇게 적는다
- [ ] **먼저 실패하는 테스트**를 추가한 뒤 고쳤다

## AC-2 · D1-2 관용 모드 크래시

- [ ] `strict=False` 로 **무효 `event_type`**(`"teleport"`)을 넣어도 **예외가 발생하지 않는다**
- [ ] `strict=False` 로 **`event_type` 키가 없는 레코드**를 넣어도 **예외가 발생하지 않는다**
- [ ] 위 두 경우가 **거부 카운트(`WriteResult.rejected`)와 `rejected.jsonl` 에 사유와 함께** 남는다
- [ ] **먼저 실패하는 테스트**를 추가한 뒤 고쳤다

## AC-3 · D1-3 타임존

- [ ] `"2025-10-01T23:30:00.000Z"`(UTC)가 **거부되거나 KST 기준 `2025-10-02` 파티션**으로 들어간다
- [ ] **어느 쪽인지 결정하고 그 결정을 `docs/event_schema.md` 또는 코드 독트링에 남긴다** — §7.3
- [ ] **오프셋이 없는 timestamp**(`"2025-10-01T23:30:00"`)의 처리도 결정하고 남긴다
- [ ] `manifest.created_at` 이 **KST** 다 (현재 UTC — 자기 규약 위반)
- [ ] **먼저 실패하는 테스트**를 추가한 뒤 고쳤다

## AC-4 · 회귀 없음 (전 스토리 공통)

- [ ] `python3 -m unittest discover -s tests` — **기준선 46건에서 회귀 0** (신규 테스트 추가로 총계는 늘어난다)
- [ ] ★ **`test_unparsable_timestamp_is_reported` 가 그대로 통과한다** — §4.4.0. **테스트를 고쳐서 통과시키지 않는다**
- [ ] `python3 -m unittest tests.test_isolation -v` — 통과 (6건)
- [ ] `python3 scripts/bench_sink.py 20000 30` — **판정 규칙은 아래.** 기준선 4,200,000건 / 64.7초 / 112.6MB (2026-09-10)

> ### ★ 벤치 판정 규칙 — "회귀 없음"의 뜻을 정한다 (Matthias N-2)
> **오차 규칙이 없으면 무엇이든 통과로 적을 수 있다.** W3 재검증 실측이 **63.8초**였다 — 기준선보다 빠른데 ±얼마까지가 "회귀 없음"인지 정의가 없었다.
>
> | 축 | 판정 | 왜 |
> |---|---|---|
> | **건수 4,200,000** | ★ **정확 일치. 다르면 실패** | **결정적이다.** 다르면 데이터가 새거나 늘어난 것이고 D1-1 이 바로 그 결함이다 |
> | **바이트 112.6MB** | ★ **±1% 이내** | 거의 결정적이다. 형식·필드가 바뀌지 않았으면 같아야 한다 |
> | **시간 64.7초** | **판정에 쓰지 않는다. 값을 기록만 한다.** 단 **2배(129초) 초과면 보고** | 개발 기계의 wall-clock 은 부하·온도에 좌우된다. **재현되지 않는 수를 게이트로 쓰면 통과·실패가 임의가 된다** |
>
> **시간을 게이트에서 뺀 이유:** 이 스토리의 수정(디렉터리 스캔)은 **파티션당 1회** 추가되므로 이론상 영향이 작다. 그런데도 시간이 2배가 되면 그것은 **알고리즘이 바뀐 것**이므로 그때만 본다.
> **실행하지 못하면 `BLOCKED` 로 사유와 함께.** 값을 추정해 적지 않는다.
- [ ] `python3 .agent-team/04-architecture/tools/check_ownership.py` — PASS
- [ ] **의존성 설치 없이** 위가 전부 통과한다 (`ISO-005`)

---

# 4. 개발 컨텍스트 (`developer_context`)

## 4.1 지금 코드가 실제로 무엇을 하는가 — 실측

### D1-1 · 파티션 덮어쓰기 — **데이터 소실형**

```python
# src/measurement/sink.py:146  (__init__)
self._part_index: Counter[str] = Counter()        # ← 인스턴스마다 새 Counter

# src/measurement/sink.py:190-197  (_write_partition)
def _write_partition(self, date_key: str, rows: list[dict[str, object]]) -> None:
    directory = self.root / "events" / f"date={date_key}"
    directory.mkdir(parents=True, exist_ok=True)
    index = self._part_index[date_key]             # ← 새 인스턴스면 항상 0 부터
    self._part_index[date_key] += 1
    path = directory / f"part-{index:04d}.{self.format.value}"
    _write_rows(path, rows, self.format)           # ← open(path,"wt") 가 기존 파일을 지운다
    self._files.append(path)
```

```python
# src/measurement/sink.py:113  (EventSink 독트링) — 사실과 다르다
"""관측 이벤트를 파티션 파일로 append 한다."""
```

**리드 재현 확인 (이슈 본문):** `1회차 2건 → 2회차 3건 → read_events 3건` (5건이 아니다)
`[Source: gh issue #53#D1-1]`

### D1-2 · `strict=False` 크래시

```python
# src/measurement/sink.py:150-165  (write_events)
for record in records:
    problems = sc.validate_event(record)
    if problems:
        result.rejected += 1
        result.problems.extend(problems[:1])
        self._rejected.append({"record": record, "problems": problems})
        if self.strict:
            continue                 # ← strict 일 때만 건너뛴다
    self._observe(record)            # ← strict=False 면 거부된 레코드가 여기로 들어온다
    self._buffer.append(record)
    result.accepted += 1             # ← 거부한 레코드를 accepted 로도 센다

# src/measurement/sink.py:169  (_observe)
event_type = sc.EventType(record["event_type"])   # ← 무조건 호출. 여기서 터진다
```

**리드 재현 확인:**
```
ValueError: 'teleport' is not a valid EventType     ← sink.py:169
KeyError: 'event_type'                              ← sink.py:169
```
`[Source: gh issue #53#D1-2]`

> ⚠ **덤으로 드러나는 것:** `strict=False` 에서 거부된 레코드가 `result.rejected` 와 `result.accepted` **양쪽에 계상된다.**
> 이슈 본문이 명시하지 않았지만 같은 코드 경로의 문제다. **조용히 고치지 말고 PR 본문에 판단을 적는다** (`AGENTS.md` — 결함을 조용히 고치지 않는다).

### D1-3 · 타임존 미강제

```python
# src/measurement/schema.py:29-33  — 선언
TIMEZONE = "Asia/Seoul"
"""모든 timestamp는 KST 단일 타임존이다. UTC 혼재를 허용하지 않는다."""
TIMESTAMP_PRECISION = "milliseconds"

# src/measurement/schema.py:validate_event()  — 검사가 없다. timestamp 는
#   "필수 필드 누락" 여부만 본다. 형식·오프셋 검사 0줄.

# src/measurement/sink.py:271-279  (_partition_key)
def _partition_key(timestamp: object) -> str:
    if isinstance(timestamp, datetime):
        return timestamp.date().isoformat()
    text = str(timestamp)
    try:
        return datetime.fromisoformat(text).date().isoformat()   # ← 파싱만. KST 변환 없음
    except ValueError as error:
        raise ValueError(f"timestamp 를 해석할 수 없다: {timestamp!r}") from error
```

**리드 재현 확인:**
```python
validate_event({... "timestamp": "2025-10-01T23:30:00.000Z" ...})   # → []  (통과)
_partition_key("2025-10-01T23:30:00.000Z")                          # → '2025-10-01'
#                                              KST 로는 2025-10-02 08:30
```
`[Source: gh issue #53#D1-3]`

**커머스도 UTC 로 기록하고 있다** — `Ecommerce_Service/src/lib/server/commerce/orders.ts:116`. **실제로 발생할 조합이다.**

### 부수 항목 3건 (이슈가 "같이 볼 것"으로 지목)

| 항목 | 위치 | 이 스토리에서 |
|---|---|---|
| `manifest.created_at` 이 **UTC** | `sink.py:229` `datetime.now(timezone.utc)` | **AC-3 에 포함.** KST 로 고친다 |
| `WriteResult.problems` 가 레코드당 **첫 문제만** | `sink.py:156` `problems[:1]` | **고치지 않는다.** 의도면 독트링에 명시한다. 전체는 `rejected.jsonl` 에 있다 `[Source: .agent-team/04-architecture/exceptions.md#10]` |
| `_digest()` 가 전 파일을 다시 읽는다 | `sink.py:258-263` | **범위 밖.** 벤치 회귀만 확인한다 |

## 4.2 아키텍처 가드레일 — 이 스토리에 걸리는 것

| # | 규칙 | 근거 |
|---|---|---|
| **G-1** | **`sink.py` 는 `data/hidden`·`data/ground_truth` 문자열을 담을 수 없다.** `tests/test_isolation.py` 의 `FORBIDDEN_PATHS["src.measurement"]` 가 **문자열 상수**를 AST 로 검사한다 | `[Source: tests/test_isolation.py#FORBIDDEN_PATHS]` |
| **G-2** | **`src.measurement` 는 `src.simulator`·`src.decision`·`src.diagnostics` 를 import 할 수 없다** | `[Source: tests/test_isolation.py#FORBIDDEN_IMPORTS]` |
| **G-3** | **표준 라이브러리만 쓴다.** `sink.py` 의 pyarrow 는 이미 함수 안 지연 import 이고 guarded 다 — 그 패턴을 유지한다 | `[Source: .agent-team/04-architecture/dependency-plan.md#2.2]` |
| **G-4** | 예외는 **`ValueError` 대신 `PartitionKeyError`**(`MeasurementError` 하위)로 승격하는 것이 설계다. **단 `errors.py` 는 M-03 에서 만든다** — 이 스토리에서 먼저 만들 필요는 없다. 만들면 M-03 과 겹치므로 **`ValueError` 를 유지하고 M-03 에서 승격한다** | `[Source: .agent-team/04-architecture/exceptions.md#2, #10]` |
| **G-5** | **결손을 0 으로 채우지 않는다.** 이 스토리에서는 `_observe()` 를 고칠 때 `record.get(name)` 의 `None` 을 0 으로 바꾸지 않는 것이 해당한다 | `[Source: .agent-team/00-plan/charter.md#6.1-6]` |

## 4.3 ★ D1-1 을 어떻게 고치는가 — 설계 선택지 2개

**아키텍처가 방법을 지정하지 않았다.** 아래 둘 다 AC 를 만족한다. **구현자가 고르고 PR 본문에 근거를 적는다.**

| | ⑴ 디렉터리를 스캔해 이어붙인다 (권장) | ⑵ 파트 이름에 실행 식별자를 넣는다 |
|---|---|---|
| 방법 | `_write_partition` 진입 시 `directory.glob("part-*")` 로 현재 최대 번호를 읽고 그 다음부터 쓴다 | `part-{run_id}-{index:04d}` 처럼 실행마다 다른 접두어 |
| 장점 | 파일명 규약이 안 바뀐다. `read_events()` 의 `rglob("part-*")` 가 그대로 동작 | 스캔 비용 0. 동시 쓰기에도 충돌 없음 |
| 단점 | 파티션당 1회 디렉터리 스캔 | **파일명 규약이 바뀐다.** `data-model-erd.md` §3 이 `part-NNNN.{parquet\|jsonl.gz}` 를 적었다 |
| 주의 | 형식이 섞이면(`part-0000.jsonl.gz` 와 `part-0000.parquet`) 번호가 충돌할 수 있다 — **확장자를 무시하고 번호만 본다** | 기존 파일과 섞였을 때 순서가 불명확 |

> **⑴을 권장한다.** `data-model-erd.md` §3 의 저장 배치가 `part-NNNN` 을 명시했고 `read_events()` 가 그 패턴을 전제한다 `[Source: .agent-team/04-architecture/data-model-erd.md#3]`.
> **⑵를 고르면 `data-model-erd.md` 와 어긋나므로 그 사실을 PR 에 적는다.**

**어느 쪽이든 반드시 지킬 것:** 파트 번호 산출은 **`self._part_index` 캐시와 디렉터리 실제 상태가 어긋나지 않아야 한다.** 한 인스턴스가 같은 날짜에 여러 번 flush 하는 경우(`chunk_rows` 초과)가 이미 존재한다 — `tests/test_sink.py:227 test_chunking_creates_multiple_parts` 가 그 경로를 밟는다.

## 4.4 ★ D1-3 을 어떻게 고치는가 — **결정이 필요하다**

이슈가 **두 선택지를 열어두고 ⑵를 제안**했다 `[Source: gh issue #53#미확정]`:

| | ⑴ KST 오프셋만 허용하고 나머지 거부 | ⑵ 어떤 오프셋이든 받아 **KST 로 변환**해 파티션한다 (이슈 제안) |
|---|---|---|
| `validate_event()` | `+09:00` 이 아니면 문제로 보고 | 오프셋 **존재**만 요구 (naive 는 거부) |
| `_partition_key()` | 그대로 | `.astimezone(KST).date()` |
| `MEA-003` 관용성 | **충돌한다** — 커머스가 UTC 로 쓰는데 전량 거부된다 | 지킨다 |
| `#54` 와의 관계 | 값 수준 강제와 같은 부류 — 함께 처리하는 편이 자연스럽다 | 동일 |

> **이슈가 ⑵를 제안한 근거:** *"커머스가 UTC 로 쓰고 있고, 거부하면 MEA-003(부분 소스 관용)과 충돌합니다. 단 저장 시 KST 로 정규화해야 합니다."*
>
> **W3 는 이것을 확정하지 않는다.** ⑴/⑵ 어느 쪽이든 AC-3 을 만족하고, **결정을 문서에 남기는 것이 AC 다.**
> 다만 **⑵를 고르면 반드시 함께 해야 하는 것이 있다** — §4.5.

### ★★ 4.4.0 먼저 — **어느 정책이든 `test_unparsable_timestamp_is_reported` 를 깬다** (Thomas C-4 · 실행 재현)

```python
# tests/test_sink.py:108-114
def test_unparsable_timestamp_is_reported(self) -> None:
    """스키마는 통과해도 파티션 키를 못 만들면 조용히 넘기지 않는다."""
    s = sk.EventSink(self.root)
    s.write_events([simulator_event(timestamp="어제")])
    with self.assertRaises(ValueError) as caught:
        s.flush()
```

**`validate_event()` 에 timestamp 검사를 넣으면 `"어제"` 가 수집 시점에 거부되어 `_buffer` 에 들어가지 않는다.**
**→ `flush()` 가 아무것도 쓰지 않고 예외를 던지지 않는다 → `assertRaises` 가 실패한다.**

**W3 재현 (2026-09-11 실행):**
```
validate_event 에 파싱 검사 주입 → 거부=1 수용=0
flush() 예외 없음  →  assertRaises(ValueError) FAIL
```

> ### ★ 46/46 을 지키는 좁은 길 — 하나뿐이다
> **`validate_event()` 는 파싱 실패를 통과시키고, `_partition_key()` 가 계속 던지게 둔다.**
> 즉 **타임존 정책은 "오프셋의 유무·값"만 검사하고 "파싱 가능성"은 검사하지 않는다.**
> 이 테스트가 지키는 것은 *"스키마는 통과해도 파티션 키를 못 만들면 조용히 넘기지 않는다"* 이고, **그 계약을 깨지 않는 유일한 배치다.**
>
> **⚠ AC-4 가 회귀 0 을 요구한다.** 이 사실을 모르면 구현자가 **테스트를 고쳐서** 넘어간다 — 그것이 `AGENTS.md` 가 금지한 *"결함을 조용히 고치는 것"* 이다.
> **테스트를 고쳐야 한다고 판단되면 멈추고 보고한다.**

### 4.4.1 ⑵를 고를 때 반드시 함께 하는 것

**변환한 사실이 데이터에 남아야 한다.** 그러지 않으면 저장된 `timestamp` 문자열은 UTC 인데 파티션 날짜는 KST 가 되어 **되읽었을 때 둘이 어긋난다.**

- **저장 시 `timestamp` 자체를 KST 표기로 정규화**하거나,
- 원문을 보존한다면 **`manifest` 에 "정규화 적용" 사실을 남긴다**

**셋 중 하나를 고르고 PR 에 적는다:**

| 안 | 저장되는 `timestamp` | 파티션 | 되읽기 정합성 |
|---|---|---|---|
| a. 입력 원문 보존 | `2025-10-01T23:30:00.000Z` | `date=2025-10-02` | **어긋난다** — 되읽어 날짜를 다시 뽑으면 10-01 |
| b. **KST 로 정규화해 저장** | `2025-10-02T08:30:00.000+09:00` | `date=2025-10-02` | **일치한다** ← 권장 |
| c. 원문 보존 + manifest 플래그 | 원문 | `date=2025-10-02` | 어긋나되 **사실이 기록된다** |

> **b 를 권장한다.** `data_spec` §9 의 시간 정합성 검사(`DQ-06` — 모든 시각이 KST 단일)가 M-07 에서 실행되는데, **a 를 고르면 그 검사가 자기 저장물에 대해 실패한다** `[Source: .agent-team/04-architecture/data-quality-design.md#3]`.

## 4.5 ⚠ 이 결정이 하류를 바꾼다 — 미리 알아둘 것

| 하류 | 영향 |
|---|---|
| **M-07 (`#48`)** `DQ-06` 시간 정합성 | 현재 `BLOCKED — 타임존 정책 미확정`. **이 스토리가 정책을 확정하면 `DQ-06` 이 실행 가능해진다** `[Source: .agent-team/04-architecture/data-quality-design.md#3]` |
| **M-08 (`#45`)** 기록 계약 | 커머스에게 *"어떤 타임존으로 기록하라"* 를 적어야 한다. ⑴이면 "KST 로 기록하라", ⑵면 "오프셋을 붙여 기록하라" |
| **M-09 (`#49`)** GATE 1 | **`G-5` 선행 조건** — *"타임존 정책이 확정되고 강제된다"* `[Source: .agent-team/03-service-planning/gate1-lock-scope.md#3]` |
| **게시 계약** | `generated_at` 이 이미 **정규식으로 `+09:00` 을 강제**한다 (`Z` 표기는 실패). 게시 계층은 이미 ⑵-b 방향이다 `[Source: .agent-team/04-architecture/schemas/common.schema.json#kst_timestamp]` |

## 4.6 함정 — 이 스토리에서 실제로 밟기 쉬운 것

| # | 함정 | 왜 빠지나 | 대신 |
|---|---|---|---|
| **T-1** | `_observe()` 안에서 `record.get("event_type", "unknown")` 으로 방어 | 크래시를 막는 가장 짧은 코드다 | **`write_events()` 에서 거부 레코드를 `_observe` 에 넘기지 않는다.** `_observe` 는 유효한 레코드만 받는다는 계약을 유지한다 |
| **T-2** | `except Exception: pass` 로 `_observe` 를 감싼다 | 위와 같은 동기 | **금지.** *"예외를 사유 없이 삼키지 않는다"* `[Source: .agent-team/04-architecture/exceptions.md#1]` |
| **T-3** | 거부된 레코드를 `_buffer` 에 넣어 저장한다 | `strict=False` 의 뜻을 *"저장한다"* 로 읽는다 | **`strict=False` 는 "수집이 실패하지 않는다"이지 "무효 데이터를 저장한다"가 아니다.** 이슈 AC 가 *"거부 카운트·`rejected.jsonl` 에 남긴다"* 만 요구한다 — 저장을 요구하지 않는다 |
| **T-4** | 파트 번호 산출에 `len(list(directory.glob(...)))` 를 쓴다 | 자연스러워 보인다 | **개수가 아니라 최대 번호 + 1 이다.** 중간 파일이 지워졌으면 개수는 번호와 다르다 |
| **T-5** | timestamp 정규화를 `_partition_key` 에만 넣는다 | 파티션만 고치면 AC 가 통과하는 것처럼 보인다 | §4.4.1 — 저장되는 값과 파티션이 어긋나면 `DQ-06` 이 자기 저장물에서 실패한다 |
| **T-6** | 벤치를 안 돌리고 "성능 영향 없음"이라고 적는다 | 디렉터리 스캔은 작아 보인다 | **AC-4 가 벤치 실행을 요구한다.** 안 돌렸으면 `BLOCKED` 로 적는다 |

---

# 5. 작업 분해 (Tasks)

**순서를 지킨다 — 먼저 실패하는 테스트를 쓰고 고친다** (`#53` AC 명시).

## T1 · 실패하는 테스트 3벌 (AC-1·2·3)

- [ ] `tests/test_sink.py` 에 `TestRewriteSameRoot` 추가 — 2건 쓰고 close, 새 `EventSink` 로 3건 쓰고 close, `read_events()` 가 **5건**
- [ ] 같은 클래스에 파트 파일이 **2개 이상** 존재함을 확인 (`part-0000`·`part-0001`)
- [ ] `tests/test_sink.py` 의 `TestSchemaEnforcement` 에 `test_non_strict_survives_unknown_event_type` 추가 — `strict=False` + `{"event_type": "teleport", …}` → **예외 없음** · `rejected == 1`
- [ ] `test_non_strict_survives_missing_event_type` 추가 — `event_type` 키 부재 → **예외 없음**
- [ ] 두 경우가 `rejected.jsonl` 에 사유와 함께 남는지 확인
- [ ] `TestTimezonePolicy` 추가 — UTC 입력에 대해 §4.4 에서 고른 정책의 기대 동작을 단언
- [ ] `test_manifest_created_at_is_kst` 추가 — `manifest["created_at"]` 이 `+09:00` 으로 끝난다
- [ ] **여기서 전부 실패하는 것을 확인하고 출력을 PR 에 남긴다**

## T2 · D1-1 수정

- [ ] §4.3 에서 선택지 결정 → PR 본문에 근거 기록
- [ ] `_write_partition()` 수정 — 디렉터리 현재 상태에서 파트 번호를 이어받는다
- [ ] `sink.py:113` 독트링을 **실제 동작과 일치**시킨다
- [ ] `chunk_rows` 초과 경로(`test_chunking_creates_multiple_parts`)가 여전히 통과하는지 확인

## T3 · D1-2 수정

- [ ] `write_events()` 수정 — `strict` 여부와 무관하게 **`problems` 가 있으면 `_observe`·`_buffer` 로 보내지 않는다**
- [ ] `result.accepted` 가 거부 레코드를 세지 않는지 확인 (§4.1 덤 항목) — 동작을 바꾸면 **PR 에 명시**
- [ ] `strict` 파라미터의 독트링(`sink.py:135`)이 새 동작과 일치하는지 확인

## T4 · D1-3 수정

- [ ] §4.4 정책 결정 → **문서에 남긴다** (`docs/event_schema.md` 또는 코드 독트링·`schema.py` 상수 주석)
- [ ] §4.4.1 저장 표현 결정 (a/b/c) → PR 에 근거 기록
- [ ] `validate_event()` 또는 `_partition_key()` 수정
- [ ] `manifest()` 의 `created_at` 을 KST 로 (`sink.py:229`)
- [ ] `docs/event_schema.md` 를 재생성해야 하면 `python3 scripts/gen_event_schema_doc.py` 를 돌리고 결과를 확인

## T5 · 검증 (AC-4)

- [ ] `python3 -m unittest discover -s tests` — 출력 전문을 PR 에 붙인다 (총 건수 · skip 수 · 사유)
- [ ] `python3 -m unittest tests.test_isolation -v`
- [ ] `python3 scripts/bench_sink.py 20000 30` — 기준선 대비 기록. **실행 못 하면 `BLOCKED` 로 사유와 함께**
- [ ] `python3 .agent-team/04-architecture/tools/check_ownership.py`
- [ ] `git -C ../Ecommerce_Service status --porcelain` 빈 출력 확인

---

# 6. 파일 목록 (`file_list`)

## 6.1 이 스토리가 만지는 파일

| 파일 | 동작 | 소유 |
|---|---|---|
| `src/measurement/sink.py` | **수정** — `_write_partition` · `write_events` · `_partition_key` · `manifest` · 독트링 2곳 | Phillip |
| `src/measurement/schema.py` | **조건부 수정** — §4.4 에서 ⑴을 고르면 `validate_event()` 에 타임존 검사 추가 | Phillip |
| `tests/test_sink.py` | **수정** — 테스트 클래스 3개 추가 | Phillip |
| `docs/event_schema.md` | **조건부 재생성** — `schema.py` 를 고쳤을 때만 | Phillip |

## 6.2 절대 만지지 않는 파일

```
tests/test_isolation.py                 ← 봉인. W6 Matthias + 사용자 승인
.github/workflows/isolation.yml         ← 봉인
src/simulator/** src/decision/** src/diagnostics/** src/orchestration/**
Plan/**                                 ← 서브모듈. 포인터도 스테이징하지 않는다
AGENTS.md · src/AGENTS.md · src/*/AGENTS.md · src/*/CLAUDE.md · README.md   ← W6 Timothy
dashboard/**                            ← Andrew 소유
../Ecommerce_Service/**                 ← 별도 저장소. 읽기만
```

`[Source: .agent-team/00-plan/task-graph.md#4]` · `[Source: .agent-team/04-architecture/build-plan.md#2.2]`

## 6.3 ⚠ `schema.py` 를 건드릴 때 알아둘 것

`schema.py` 는 **`EVENT SCHEMA v1` Lock 대상 파일**이다 `[Source: .agent-team/04-architecture/gate1-freeze-procedure.md#2.2]`.
타임존 검사 추가는 **22 컬럼·16 타입·Nullable 매트릭스를 바꾸지 않으므로** 회귀가 즉시 잡힌다:

```python
tests/test_schema.py:45-47   assertEqual  event_type 16종
tests/test_schema.py:61-72   assertEqual  DATA-003 22컬럼
```

**M-02(`#54`)도 `schema.py` 를 고친다.** 두 스토리가 같은 파일을 만지므로:
- **같은 PR 로 묶거나**, 순서를 정해 하나가 끝난 뒤 다른 하나를 시작한다
- `#53` 미확정 항목이 *"D1-3 은 `#54`(값 수준 강제)와 함께 처리하는 편이 자연스러울 수 있습니다"* 라고 적었다 `[Source: gh issue #53#미확정]`
- **묶기로 하면 PR 제목·본문에 두 이슈를 모두 연결한다** (`Closes #53, Closes #54`)

---

# 7. 테스트

## 7.1 실행 가능한 명령 — **이것뿐이다**

```bash
python3 -m unittest discover -s tests          # 기준선 46건 (2026-09-11 라이브 확인: OK)
python3 -m unittest tests.test_isolation -v    # 격리 6건
python3 -m unittest tests.test_sink -v         # 이 스토리의 주 대상
python3 scripts/bench_sink.py 20000 30         # 기준선 4,200,000건 / 64.7초 / 112.6MB
python3 scripts/gen_event_schema_doc.py > docs/event_schema.md   # ★ stdout 이다. 리다이렉트해야 재생성된다
python3 .agent-team/04-architecture/tools/check_ownership.py
```

**존재하지 않는 명령을 쓰지 않는다.** lint·build·타입 검사는 이 저장소에 정의되어 있지 않다 `[Source: .agent-team/00-plan/charter.md#6.3]`.

## 7.2 기존 테스트에서 이어받는 관례

`tests/test_sink.py` 에 이미 있는 것 — **같은 헬퍼를 쓴다. 새로 만들지 않는다.**

```python
tests/test_sink.py:19   simulator_event(event_type=..., **overrides)   # 시뮬레이터 레코드 생성
tests/test_sink.py:47   commerce_event(*args, **overrides)             # 커머스 레코드 (meta 4종 None)
tests/test_sink.py:55   class SinkTestCase(unittest.TestCase)          # tmpdir 셋업 기반 클래스
```

**주의:** `simulator_event()` 는 `"category": "fresh_food"` 를 쓰고 `tests/test_schema.py:32` 는 `"category": "신선식품"` 을 쓴다 — **두 테스트의 어휘가 다르고 둘 다 통과한다.**
**이 스토리는 그것을 고치지 않는다. M-02(`#54`)의 몫이다.** 새 테스트는 `test_sink.py` 의 기존 어휘(`fresh_food`)를 따른다 `[Source: gh issue #54#D2-2]`.

## 7.3 결정을 어디에 기록하는가

AC-3 이 *"결정하고 문서에 남긴다"* 를 요구한다. **세 자리 중 최소 하나** — 어디에 적었는지 PR 에 쓴다.

| 자리 | 적합한 경우 |
|---|---|
| `src/measurement/schema.py` 의 `TIMEZONE` 상수 독트링 | 가장 가깝다. 이미 *"UTC 혼재를 허용하지 않는다"* 가 있으므로 **그 문장이 실제로 강제되는지**를 함께 적는다 |
| `docs/event_schema.md` | 생성 문서다. `gen_event_schema_doc.py` 가 만드는 범위 안이어야 한다 — **범위 밖이면 여기 적지 않는다** |
| `docs/measurement_contract.md` | **M-08 의 파일이다.** 이 스토리에서 만들지 않는다. M-08 에 인계 사항으로 남긴다 |

---

# 8. 연속성 — 이전 작업에서 이어받는 것

## 8.1 선행 스토리

**없다.** 이 스토리가 Phase 1 이고 차단 요인이 없다.

## 8.2 이미 머지된 코드에서 이어받는 것

| 출처 | 이어받는 것 |
|---|---|
| PR **#50** (`105e83c`) — 이벤트 스키마 (M-1) | `schema.py` 350줄. **표준 라이브러리만**, 아무것도 import 하지 않는다 |
| PR **#51** (`d1ca26f`) — Event Sink (M-2) | `sink.py` 321줄. pyarrow **지연 import + guarded** 패턴 |
| PR **#41** (`41ccf73`) — 격리 CI | `.github/workflows/isolation.yml` — **의존성 설치 단계 없음** |
| PR **#55** (`21bf7b9`) — git 워크플로우 | `docs/GIT_WORKFLOW.md` — 커밋 규약 · PR 필수 항목 · L1 권한 |

## 8.3 확립된 패턴 — 깨지 않는다

| 패턴 | 어디에 |
|---|---|
| **선택 의존성은 guarded import + 명시적 skip** | `sink.py:52-56 parquet_available()` · `test_sink.py:65,69` |
| **거부는 사유와 함께 남긴다** | `sink.py:203-206` `rejected.jsonl` |
| **결손을 0 으로 채우지 않는다** | `test_sink.py:172 test_missing_optional_field_is_not_filled` |
| **빈 Sink 에서 Observable 16개 전부 계산 불가** | `test_sink.py:198-203` — ★ **깨뜨리지 않는다.** USP-1 의 회귀 테스트다 |
| **같은 입력 → 같은 해시** | `test_sink.py:216-225 test_same_input_gives_same_digest` — **위험 없음(정정).** 반복마다 **새 `tempfile.TemporaryDirectory()`** 를 쓰므로(`test_sink.py:219`) 파트 번호가 이어질 자리가 없다. Thomas 가 디렉터리 스캔 monkeypatch 로 **46 OK** 를 확인했다 |
| ★ **파싱 불가 timestamp** | `test_sink.py:108-114 test_unparsable_timestamp_is_reported` — ★★ **진짜 회귀는 여기다.** §4.4.0. **타임존 정책 ⑴·⑵ 양쪽 다 이 테스트를 깬다** |

> **★ 1차 컴파일에서 위험을 반대로 짚었다 (Thomas 답변2 정정).**
> `test_same_input_gives_same_digest` 를 위험으로 표시했으나 **위험이 아니었고**, 실제 회귀인 `test_unparsable_timestamp_is_reported`(§4.4.0)는 **표에 없었다.**
> **없는 위험을 표시하고 있는 위험을 놓친 것**이므로 둘 다 고쳤다.

---

# 9. 완료 정의 (DoD) · 미결정 · 차단

## 9.1 DoD

- [ ] AC-1 ~ AC-4 전부 체크
- [ ] 세 결함 각각에 **먼저 실패하는 테스트**가 있고, 그 실패 출력을 PR 에 남겼다
- [ ] §4.3 · §4.4 · §4.4.1 의 선택을 **근거와 함께 PR 본문에 적었다**
- [ ] 타임존 정책이 **문서에 남았다** (§7.3 중 하나)
- [ ] PR 본문에 `project-context-kr.md` §9 체크리스트를 채웠다
- [ ] **미실행 검증을 통과로 적지 않았다.** 벤치를 못 돌렸으면 `BLOCKED` + 사유
- [ ] `#53` 을 **닫지 않았다** — Issue close 는 개별 승인 사항이다 `[Source: AGENTS.md#반드시-지킬-것]`

## 9.2 이 스토리에서 하지 않는 것

| 항목 | 왜 |
|---|---|
| Parquet 경로 검증 | **pyarrow 미설치 → `BLOCKED`.** M-05 의 몫 |
| `write_batch()` 구현 | 인터페이스 편의. 계약이 아니다 `[Source: .agent-team/03-service-planning/gate1-lock-scope.md#3.1]` |
| `_digest()` 성능 개선 | 범위 밖. 벤치 회귀만 확인 |
| `category`·`page_type` 허용값 | **M-02(`#54`)의 몫** |
| `errors.py` 예외 계층 | **M-03 의 몫.** 지금 만들면 소유가 겹친다 |
| 6개 추가 테이블 | C1 범위 밖 `[Source: .agent-team/04-architecture/data-model-erd.md#1.1]` |

## 9.3 미결정 — 구현자가 정하고 PR 에 적는다

| # | 항목 | 선택지 | 정본 참조 |
|---|---|---|---|
| **M01-a** | D1-1 수정 방식 | ⑴ 디렉터리 스캔 **(권장)** ⑵ 파트명에 실행 식별자 | §4.3 |
| **M01-b** | 타임존 정책 | ⑴ KST 만 허용·거부 ⑵ 변환 **(이슈 제안)** — ★ **어느 쪽이든 §4.4.0 좁은 길을 지켜야 46/46 이 유지된다** | §4.4 · §4.4.0 |
| **M01-c** | ⑵일 때 저장 표현 | a 원문 / **b KST 정규화 (권장)** / c 원문+플래그 | §4.4.1 |
| **M01-d** | `result.accepted` 가 거부분을 세는 것 | 고친다 / 유지하고 독트링에 명시 | §4.1 덤 항목 |
| **M01-e** | `#53` 과 `#54` 를 한 PR 로 묶는가 | 묶는다 / 나눈다 | §6.3 |

## 9.4 차단 — 없다

**차단 요인 0.** 결정 M01-a~e 는 구현자 판단 범위이고, 사용자 결정을 기다리지 않는다.
**단 M01-b 의 결과가 M-08·M-09 의 선행 조건 `G-5` 를 충족시키므로, 결정 내용을 그 스토리에 인계한다.**

## 9.5 하류로 넘기는 것

| 받는 스토리 | 넘기는 것 |
|---|---|
| **M-07 (`#48`)** | 타임존 정책 확정 → `DQ-06` 이 `BLOCKED` 를 벗어난다 · `strict=False` 경로 복구 → `DQ-10`·`DQ-11` 위반 데이터를 만들 수 있다 |
| **M-08 (`#45`)** | 커머스에게 요구할 타임존 표기 |
| **M-09 (`#49`)** | 선행 조건 **`G-5`**(타임존)·**`G-6`**(파티션 보존)·**`G-7`**(관용 모드) 충족 증거 |
| **M-03** | `ValueError` → `PartitionKeyError` 승격 대상 위치 (`sink.py:277-279`) |

<!-- ════════ source_hash inputs (D3 · Matthias 항목5) ════════
     계산법: project-context-kr.md §12  ·  파일 17종
     재현:  아래 목록을 sorted() 하고 각 파일에 f"{path}\n{sha256_hex}\n" 를 이어붙여
            그 바이트열의 SHA-256 앞 16자리를 취한다. 없는 파일은 "MISSING".

     .agent-team/00-plan/charter.md
     .agent-team/00-plan/task-graph.md
     .agent-team/03-service-planning/core-features.md
     .agent-team/03-service-planning/gate1-lock-scope.md
     .agent-team/03-service-planning/user-stories.md
     .agent-team/04-architecture/build-plan.md
     .agent-team/04-architecture/code-structure.md
     .agent-team/04-architecture/data-model-erd.md
     .agent-team/04-architecture/data-quality-design.md
     .agent-team/04-architecture/design-patterns.md
     .agent-team/04-architecture/exceptions.md
     AGENTS.md
     docs/GIT_WORKFLOW.md
     src/AGENTS.md
     src/measurement/schema.py
     src/measurement/sink.py
     tests/test_sink.py

     → source_hash = f9b50547bbb181fb
     ════════════════════════════════════════════════════ -->
