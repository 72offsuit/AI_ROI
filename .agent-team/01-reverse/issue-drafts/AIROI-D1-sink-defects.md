# [발행됨 → AI_ROI#53] fix: Event Sink 결함 3건 — 파티션 덮어쓰기 · `strict=False` 크래시 · 타임존 미강제

> **발행 완료 (2026-09-11):** https://github.com/72offsuit/AI_ROI/issues/53 · **관련:** #44 (M-2) · **라벨 제안:** `kind/dev`, `scope/M-measurement`

## 배경

PR #51(`d1ca26f`)로 `src/measurement/sink.py`가 병합되었고 테스트 46건이 전부 통과합니다.
그러나 **테스트가 밟지 않는 경로 3곳에서 결함을 실행으로 확인**했습니다. 셋 다 조용히 잘못된 데이터를 만들거나 실행을 중단시킵니다.

`AGENTS.md`: *"결함을 조용히 고치지 않는다. 발견 → Issue 기록 → 수정 → 재시험."*

## 결함

### D1-1 · 동일 root 재기록 시 기존 파티션 파일을 덮어쓴다 — **데이터 소실**

`sink.py:113` 독트링은 *"이벤트는 … 파티션 파일로 **append** 한다"* 라고 적습니다. 실제로는 덮어씁니다.

원인: `self._part_index`가 **인스턴스마다 새 `Counter`** 입니다(`sink.py:146`). 두 번째 `EventSink`가 같은 root를 열면 파트 번호가 다시 `0000`부터 시작하고, `_write_partition`(`sink.py:190-197`)이 `open(path, "wt")`로 기존 파일을 지웁니다.

재현 (실행 확인):

```
1회차  EventSink(root) 에 2건  → events/date=2025-10-01/part-0000.jsonl.gz  · read_events → 2건
2회차  EventSink(root) 에 3건  → events/date=2025-10-01/part-0000.jsonl.gz  · read_events → 3건
                                                                              ↑ 5건이 아니다
```

**영향:** `data/raw`에 두 번 쓰면 앞선 데이터가 사라집니다. 시뮬레이터가 기간을 나눠 `advance()`하며 기록하면(SIM-012 분할 불변성) 매번 앞 구간이 지워집니다.

### D1-2 · `strict=False` 경로가 크래시한다

`write_events`(`sink.py:150-165`)는 `strict`가 False면 `continue`하지 않고 `_observe(record)`로 진입합니다(`sink.py:158-160`).
`_observe`(`sink.py:169`)는 `sc.EventType(record["event_type"])`를 무조건 호출합니다 — **`validate_event()`가 이미 거부한 레코드**가 그대로 넘어옵니다.

재현 (실행 확인):

```python
EventSink(root, strict=False).write_events([{"event_type": "teleport"}])
#   ValueError: 'teleport' is not a valid EventType        ← sink.py:169

EventSink(root, strict=False).write_events([{"customer_id": "C00012345"}])
#   KeyError: 'event_type'                                 ← sink.py:169
```

**영향:** `strict=False`는 *"기록하되 표시한다"*(`sink.py:135`)는 관용 모드입니다. SRS MEA-003 *"커머스가 아직 제공하지 않는 필드가 있어도 수집이 실패하지 않아야 한다"* 와 정면으로 어긋납니다. 커머스 실측분을 관용 모드로 받으려는 첫 순간에 터집니다.

기존 테스트(`tests/test_sink.py:145-152`)는 `event_type`이 유효한 경우만 다뤄 이 경로를 밟지 않습니다.

### D1-3 · 타임존이 강제되지 않아 파티션 날짜가 하루 어긋난다

`schema.py:29-33`이 `TIMEZONE = "Asia/Seoul"` · `TIMESTAMP_PRECISION = "milliseconds"` 를 선언하고 `docs/event_schema.md:16`은 *"UTC 혼재 불허"* 라고 적습니다. 그러나 `validate_event()`에 검사가 없고, `_partition_key`(`sink.py:271-279`)는 `datetime.fromisoformat()`으로 파싱만 한 뒤 `.date()`를 취합니다 — **오프셋을 KST로 변환하지 않습니다.**

재현 (실행 확인):

```python
validate_event({... "timestamp": "2025-10-01T23:30:00.000Z" ...})  # → []  (통과)
_partition_key("2025-10-01T23:30:00.000Z")                          # → '2025-10-01'
#                                             KST로는 2025-10-02 08:30
```

**영향:** 코호트 경계·`purchase_interval`·리텐션·`last_visit_date`가 하루씩 밀립니다. 커머스도 UTC로 기록하고 있어(`Ecommerce_Service/src/lib/server/commerce/orders.ts:116`) 실제로 발생할 조합입니다.

## 부수 항목 (같이 볼 것)

| 항목 | 근거 |
|---|---|
| manifest `created_at`이 UTC — 자기 규약(KST 단일)과 어긋난다 | `sink.py:229` vs `schema.py:29-30` |
| `WriteResult.problems`가 레코드당 첫 문제만 담는다 | `sink.py:156` `problems[:1]` |
| `_digest()`가 전 파일을 다시 읽는다 (112MB 규모에서 close 비용) | `sink.py:258-263` |

## 수용 기준

- [ ] 기존 root에 다시 쓰면 **기존 파티션 파일을 보존**한다. 파트 번호가 디렉터리의 현재 상태에서 이어진다
- [ ] 독트링(`sink.py:113`)이 실제 동작과 일치한다 — append면 append, 덮어쓰기면 그렇게 적는다
- [ ] `strict=False`에서 무효 레코드(알 수 없는 `event_type`, `event_type` 키 부재)를 받아도 **예외 없이** 진행하고 거부 카운트·`rejected.jsonl`에 남긴다
- [ ] `validate_event()`가 **오프셋 없는 timestamp와 KST 아닌 오프셋을 거부**한다. 또는 파티션 키 산출 시 KST로 변환한다 — 어느 쪽이든 결정하고 문서에 남긴다
- [ ] 세 결함 각각에 대해 **먼저 실패하는 테스트**를 추가한 뒤 고친다
- [ ] `python3 -m unittest discover -s tests` 기준선 46건에서 **회귀 0**

## 검증 계획

| 명령 또는 확인 절차 | 기대 결과 | 필요한 환경·제약 |
|---|---|---|
| `python3 -m unittest discover -s tests -v` | 신규 테스트 포함 전건 통과 | 표준 라이브러리만 |
| 재기록 시나리오 | 2건 + 3건 → `read_events` 5건 | — |
| `strict=False` + 무효 레코드 | 예외 없음 · `rejected.jsonl`에 기록 | — |
| UTC timestamp 입력 | 거부되거나 KST 기준 날짜로 파티션 | — |
| `python3 scripts/bench_sink.py 20000 30` | 회귀 없음 (기준: 4,200,000건 / 64.7초 / 112.6MB, 2026-09-10 실측) | — |

## 미확정

- **타임존 정책 선택:** ⑴ KST 오프셋만 허용하고 나머지 거부 ⑵ 어떤 오프셋이든 받아 KST로 변환. **⑵를 제안** — 커머스가 UTC로 쓰고 있고, 거부하면 MEA-003(부분 소스 관용)과 충돌합니다. 단 저장 시 KST로 정규화해야 합니다
- D1-3은 `AIROI-D2`(값 수준 강제)와 함께 처리하는 편이 자연스러울 수 있습니다

## 의존성

- 없음. `#44`가 아직 OPEN이므로 그 하위 작업으로 처리해도 됩니다
