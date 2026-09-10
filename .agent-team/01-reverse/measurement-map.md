# 측정 계층 실측 지도 — T1.1 · T1.2 · T1.3

**작성** 2026-09-10 · John (W1 Reverse) · **대상 커밋** `1140912` (main)
**모든 주장에 `파일:라인` 근거를 단다. 실행하지 않은 것은 `BLOCKED`로 적는다.**

---

## 0. 한 줄 요약

`src/measurement/`는 **671줄(schema 350 + sink 321)** 로 이벤트 계약과 저장을 구현했고 테스트 46건이 전부 통과한다.
계약의 **뼈대는 견고하다**(문서 자동생성 · AST 격리검사 · 결손 비은폐 · 출처 구분).
반면 **값 수준의 강제가 비어 있다** — 타임존·식별자 형식·`category`/`page_type` 허용값은 선언만 있고 `validate_event()`가 검사하지 않는다.
추가로 **동일 root 재기록 시 기존 파티션 파일을 덮어쓰는 결함**을 실행으로 확인했다.

---

## 1. T1.1 — `src/measurement/`가 실제로 보장하는 것

### 1.1 파일 구성

| 파일 | 줄 | 역할 |
|---|---|---|
| `src/measurement/__init__.py` | 4 | 패키지 독트링. "아무것도 import하지 않는다"(ISO-002) |
| `src/measurement/schema.py` | 350 | 이벤트 계약 — 필드·이벤트별 규칙·식별자 정규식·Observable 매핑 |
| `src/measurement/sink.py` | 321 | Event Sink — 수집·검증·파티션 저장·manifest·되읽기 |

`kpi.py` · `economics.py` · `validate.py` 는 **없다** (이슈 `#42` 본문이 범위 M의 소유물로 열거한 파일들이다. `#46`·`#47`·`#48` 미착수).

### 1.2 event_type — 16종 맞다

`schema.py:41-63`. 이슈 주장(16종)과 코드가 일치하며 `tests/test_schema.py:45-47`이 개수를 고정한다.

| 구분 | 값 | 근거 |
|---|---|---|
| 세션·탐색 (5) | `session_start` `page_view` `search` `product_view` `return_visit` | `schema.py:45-49` |
| 구매 퍼널 (4) | `add_to_cart` `remove_from_cart` `checkout_start` `purchase` | `schema.py:51-54` |
| 마케팅 (5) | `campaign_exposed` `push_sent` `coupon_exposed` `coupon_clicked` `coupon_use` | `schema.py:56-60` |
| 부수 (2) | `review` `cs_contact` | `schema.py:62-63` |

**파생 상태 3종은 별도 Enum이다** — `DerivedStateType` (`schema.py:66-76`: `inactive`/`at_risk`/`churn`).
raw 16종과 교집합이 없음을 `test_schema.py:49-53`이 강제하고, `FEATURE_FORBIDDEN_EVENT_TYPES`(`schema.py:78-79`)로 Feature 사용 금지를 표시한다.
**주의: 파생 상태는 `EventType`에 없으므로 현재 Sink에 기록할 수단 자체가 없다.** PRD §30.2·`docs/data_spec.html` §7.3은 "기록은 하되 Feature 금지"를 요구한다 → 기록 경로가 미정이다(M-3/M-6 후속).

### 1.3 필드 22종과 Nullable 매트릭스

필드 정의는 `schema.py:101-137`. 그룹 6종(`core`/`session`/`product`/`order`/`marketing`/`meta`, `schema.py:84-90`).

**필수/선택 판정 규칙** — `requirement()` (`schema.py:251-262`):

| 조건 | 결과 | 근거 |
|---|---|---|
| CORE 4종 (`event_id` `customer_id` `timestamp` `event_type`) | 항상 **REQUIRED** | `schema.py:255-256` |
| META 4종 (`service_version` `customer_version` `simulator_version` `random_seed`) | 항상 **OPTIONAL** | `schema.py:255-256` |
| `_EVENT_RULES[event_type]`의 required 집합 | REQUIRED | `schema.py:257-259` |
| optional 집합 또는 배정 3종(`treatment_id` `treatment_group` `experiment_id`) | OPTIONAL | `schema.py:248, 260-261` |
| 그 외 전부 | **NOT_APPLICABLE** (값이 있으면 위반) | `schema.py:262` |

이벤트별 규칙 전체는 `schema.py:176-245`, 사람이 읽는 16×15 매트릭스는 `docs/event_schema.md:56-73`.

**NOT_APPLICABLE이 화이트리스트로 동작한다** — 규칙에 없는 필드에 값이 있으면 거부한다(`schema.py:296-297`). 예: `push_sent`에 `product_id`를 붙이면 위반(`test_schema.py:112-116`).

### 1.4 `validate_event()`가 실제로 잡는 것 / 못 잡는 것

`schema.py:269-304`.

**잡는다 (실행 확인)**

| 검사 | 근거 |
|---|---|
| 알 수 없는 `event_type` (즉시 반환) | `schema.py:276-280` |
| 스키마에 없는 필드 | `schema.py:282-284` |
| 금지 필드 유입 (Hidden Trait·τ·Potential Outcome·persona 25종) | `schema.py:149-159, 285-287` |
| 필수 필드 누락 (`None` 포함) | `schema.py:289-291` |
| 해당 없는 필드에 값 존재 | `schema.py:293-297` |
| 음수 금액 4종 | `schema.py:299-302` |

**못 잡는다 (내가 실행해 확인한 결과)**

| 통과해버리는 입력 | 실행 결과 | 근거 |
|---|---|---|
| `page_type="아무거나"` | `validate_event() → []` (통과) | `schema.py:111-112`는 8종을 **설명 문자열**로만 적음 |
| `category="우주선"` | `validate_event() → []` (통과) | `schema.py:115` "상품 카테고리 5종" — 열거 없음 |
| `customer_id="test-user-1"` | `validate_event() → []` (통과). 단 `check_identifier()`는 `False` | `schema.py:324-326`가 **어디에서도 호출되지 않는다** |
| `timestamp="2025-10-01T23:30:00.000Z"` (UTC) | 통과 + 파티션키 `2025-10-01` (KST로는 10-02) | `schema.py:29-33`는 상수 선언뿐, 검사 없음 |

> 즉 **형식·어휘·타임존은 "규약으로 적혀 있으나 코드가 막지 않는다."** 커머스(`Ecommerce_Service`)의 현재 식별자(`dummyjson-16`·`test-user-1`)가 그대로 흘러들어와도 Sink는 받아들인다.

### 1.5 식별자 규칙

`schema.py:309-319`에 정규식 9종. 문서 예시는 `docs/event_schema.md:95-105`.

```
event_id      UUID4
customer_id   ^C\d{8}$
session_id    ^S-C\d{8}-\d{13}$      (= S-{customer_id}-{세션시작 epoch ms})
order_id      ^O\d{8}-\d{6}$
product_id    ^P\d{4}$
coupon_id     ^CPN-[A-Z0-9]{6}$
campaign_id   ^CMP-\d{8}-\d{3}$
treatment_id  ^T[0-4]$
experiment_id ^EXP-\d{8}-\d{2}$
```

**이 값들은 근거 문서에 규정이 없어 임의로 정한 것이다** — 이슈 `#43` 코멘트가 스스로 밝히고 있다. GATE 1(`#49`) 전에 확정이 필요하다.

### 1.6 파티셔닝

`sink.py:190-197`. **날짜 단일 파티션**이다.

```
{root}/events/date=YYYY-MM-DD/part-NNNN.{format}
{root}/manifest.json
{root}/rejected.jsonl        ← 거부분이 있을 때만
```

- 파티션 키는 `timestamp`에서 뽑는다 (`sink.py:271-279`). 파싱 실패는 조용히 넘기지 않고 `ValueError`(`sink.py:277-279`, 테스트 `test_sink.py:108-114`).
- 청크: 버퍼가 `chunk_rows`(기본 200,000, `sink.py:39`)에 도달하면 flush (`sink.py:163-164`).
- 형식 자동 선택: pyarrow 있으면 Parquet, 없으면 gzip JSONL (`sink.py:59-69`).

**⚠ 결함 — 동일 root 재기록 시 덮어쓴다.** `_part_index`가 인스턴스마다 새 `Counter`다(`sink.py:146`). 실행 확인:

```
1회차 EventSink(root) 2건 → part-0000.jsonl.gz, 읽힌 이벤트 2
2회차 EventSink(root) 3건 → part-0000.jsonl.gz, 읽힌 이벤트 3   ← 5가 아니다
```

`sink.py:113` 독트링은 "파티션 파일로 **append** 한다"고 적혀 있으나 실제로는 덮어쓴다. `data/raw`에 두 번 쓰면 앞선 데이터가 사라진다.

### 1.7 source 분류 (커머스 vs 시뮬레이터)

`sink.py:74-83`. SRS MEA-002를 그대로 구현했다.

```python
simulator_version 과 random_seed 가 둘 다 None  →  EventSource.COMMERCE
그 외                                          →  EventSource.SIMULATOR
```

- 별도 플래그 컬럼이 아니라 **스키마 필드에서 파생**한다 → 기록자가 출처를 위조할 여지가 적다. 설계상 강점.
- manifest `sources`에 소스별 건수가 집계된다 (`sink.py:139, 168, 237`). 테스트 `test_sink.py:155-166`.
- **다만 이 분류 결과는 저장 레코드에 남지 않는다.** 파일에 쓰이는 것은 원본 레코드뿐(`sink.py:282-294`)이므로, 되읽은 뒤 출처를 알려면 `event_source()`를 다시 호출해야 한다. 파티션도 출처로 나뉘지 않는다 — 대시보드(W5-C)가 출처별로 보여주려면 전량 재분류가 필요하다.

### 1.8 reject 로깅

`sink.py:150-165, 200-206`.

- 위반 레코드는 `self._rejected`에 `{"record":…, "problems":[…]}` 로 모았다가 `close()`에서 `rejected.jsonl`에 기록 (`sink.py:203-206`). 테스트 `test_sink.py:128-136`.
- `strict=True`(기본)면 저장에서 제외, `strict=False`면 저장하되 거부 카운트에 남긴다 (`sink.py:158-159`).
- **`WriteResult.problems`는 레코드당 첫 문제만 담는다** (`sink.py:156` `problems[:1]`). 전체 사유는 `rejected.jsonl`에만 있다.

**⚠ 결함 — `strict=False` 경로가 크래시한다.** 실행 확인:

```
EventSink(strict=False).write_events([{"event_type": "teleport"}])
  → ValueError: 'teleport' is not a valid EventType     (sink.py:169)
EventSink(strict=False).write_events([{"customer_id": "C00012345"}])
  → KeyError: 'event_type'                              (sink.py:169)
```

`sink.py:158-160`에서 `strict`가 False면 `continue`하지 않고 `_observe(record)`로 진입하는데, `_observe`(`sink.py:169`)가 `sc.EventType(record["event_type"])`를 무조건 호출한다. `validate_event()`가 **이미 거부한 레코드**를 그대로 넘기므로 터진다. `strict=False` 테스트(`test_sink.py:145-152`)는 event_type이 유효한 경우만 다뤄 이 경로를 밟지 않는다.

### 1.9 결손 처리 (MEA-003) — 이 계층에서 가장 잘 된 부분

| 장치 | 동작 | 근거 |
|---|---|---|
| `FieldCoverage` | 필드별 `present/applicable` 비율. NOT_APPLICABLE은 분모에서 제외 | `sink.py:88-97, 171-176` |
| `field_coverage` | manifest에 필드별 충족률 | `sink.py:222-226, 239` |
| `missing_tokens` → `missing_fields` | 해당되는데 한 건도 없는 필드 목록 | `sink.py:240-243` |
| `unavailable_metrics()` | 근거 이벤트가 0건이라 **계산 불가한** Observable 지표 | `sink.py:247-256` |

빈 Sink는 Observable 16개 전부를 계산 불가로 표시한다(`test_sink.py:198-203`). 선택 필드가 비면 **0으로 채우지 않고 비운 채 저장**한다(`test_sink.py:172-179`).
이것이 charter 절대제약 6("결손을 조용히 0으로 채우지 않는다")과 PRD §10.1을 코드로 지킨 지점이다.

### 1.10 manifest

`sink.py:220-245`. 담기는 것: `schema_version` `created_at` `format` `partition` `timezone` `rows` `rejected` `files` `sha256` `sources` `event_type_counts` `field_coverage` `missing_fields` `unavailable_metrics`.

**이슈 `#44`가 요구했으나 없는 것**: 버전키 4종의 **값**(`service_version`/`customer_version`/`simulator_version`/`random_seed`), **config 해시**. 현재는 충족률만 있고 실제 값이 없어 재현 메타로 쓸 수 없다.
**`created_at`이 UTC다** (`sink.py:229` `datetime.now(timezone.utc)`) — `schema.py:29-30`의 "KST 단일, UTC 혼재 불허"와 어긋난다.

### 1.11 성능 — 내가 실행한 실측

`scripts/bench_sink.py` 실행 (로컬 Python 3.14.6, pyarrow 없음 → jsonl.gz):

| 규모 | 건수 | 소요 | 처리량 | 저장 크기 |
|---|---|---|---|---|
| 2,000명 × 30일 | 420,000 | **6.4초** | 65,890 건/초 | 11.3 MB |
| **20,000명 × 30일** | **4,200,000** | **64.7초** | **64,899 건/초** | **112.6 MB** |

`#44` 수용 기준 "수 분 이내" 충족. 이슈 `#44` 코멘트의 기록(63.8초)과 재현성 있게 일치한다.
단 이는 **Sink의 수집·검증·저장 비용만**이며 시뮬레이터 행동 생성 비용은 포함하지 않는다(`scripts/bench_sink.py:6-7`).

---

## 2. T1.2 — 테스트 46건이 강제하는 것

### 2.1 실행 결과 (실제 실행함)

```
$ python3 -m unittest discover -s tests -v
Ran 46 tests in 0.030s
OK
```

Python 3.14.6. charter 기준선(46 tests OK)과 일치. 내역: `test_isolation` 6 · `test_schema` 20 · `test_sink` 20.

### 2.2 `tests/test_isolation.py` — 무엇을 막는가

**① import 경계** (`test_isolation.py:23-28, 86-102`) — AST로 `src/**/*.py`를 파싱해 `import`/`from X import` 노드를 수집하고 금지 패키지 하위인지 검사한다.

| 이 모듈이 | 금지 대상 |
|---|---|
| `src.decision` | `src.simulator` · `src.diagnostics` |
| `src.simulator` | `src.decision` · `src.diagnostics` |
| `src.measurement` | `src.simulator` · `src.decision` · `src.diagnostics` |
| `src.orchestration` | `src.simulator._internal` · `src.diagnostics` |

**② `src.diagnostics`는 누구도 import 못 한다** (`test_isolation.py:39, 104-117`).

**③ 데이터 경로 문자열 금지** (`test_isolation.py:31-36, 123-139`) — 소스의 **문자열 상수**를 훑어 금지 경로가 **부분 문자열로라도** 들어 있으면 실패한다.

| 이 모듈이 | 참조 금지 경로 |
|---|---|
| `src.decision` · `src.measurement` · `src.orchestration` | `data/hidden` · `data/ground_truth` |
| `src.simulator` | `results/` |

**④ 지침 파일 배치** (`test_isolation.py:142-175`) — 6개 파트 디렉터리 존재 / 각 디렉터리에 `AGENTS.md`+`CLAUDE.md` 둘 다 / `CLAUDE.md`에 `@AGENTS.md` 문자열 포함(내용 복제 금지).

### 2.3 이 검사의 **한계** — 정확히 무엇을 못 막는가

에이전트·구현자가 오해하기 쉬운 지점이라 명시한다.

| 못 막는 것 | 근거 |
|---|---|
| **상대 import** (`from ..simulator import x`) | `test_isolation.py:65-67`이 `node.level == 0`인 절대 import만 수집한다 |
| **동적 import** (`importlib.import_module("src.simulator")`) | 문자열 검사 대상은 `FORBIDDEN_PATHS`뿐이고 모듈명은 검사하지 않는다 |
| **f-string으로 조립한 경로** (`f"data/{kind}"`) | `_string_constants`(`test_isolation.py:71-76`)는 `ast.Constant` 문자열만 본다 |
| **`src/` 밖의 코드** | `_iter_source_files`(`test_isolation.py:51-55`)가 `SRC_ROOT` 하위만 순회. `scripts/`·대시보드 경로는 **무검사** |
| **"결과를 본 뒤 시뮬레이터를 고치는 것"** | 이것이 PRD §80 Risk 1의 진짜 위험이고, 이 테스트로는 원리상 막을 수 없다 |

> **W5-C 대시보드가 `src/` 밖에 놓이면 격리 검사의 사각지대가 된다.** W2 T2.10(경로 결정) 시 반드시 고려해야 한다.

### 2.4 `tests/test_schema.py` 20건이 고정하는 것

| 고정 사항 | 근거 |
|---|---|
| event_type 정확히 16종 | `test_schema.py:45-47` |
| 파생 상태 3종이 raw와 분리 + `FEATURE_FORBIDDEN_EVENT_TYPES`와 동일 | `test_schema.py:49-53` |
| 16종 전부 `_EVENT_RULES`에 규칙 보유 | `test_schema.py:55-57` |
| **DATA-003 컬럼 집합이 정확히 22종** (`assertEqual`, 부분집합 아님) | `test_schema.py:61-72` |
| 금지 필드가 스키마에 섞이지 않음 | `test_schema.py:78-81` |
| required∩optional = ∅ | `test_schema.py:91-97` |
| 16종 전부 최소 레코드가 통과 | `test_schema.py:101-104` |
| Hidden Trait 유입 거부 / 음수 금액 거부 / n/a 필드 거부 / 미지 event_type 거부 | `test_schema.py:106-133` |
| 배정 3종이 어디서나 optional | `test_schema.py:135-141` |
| 식별자 정규식 유효/무효 케이스 | `test_schema.py:144-171` |
| **Observable 16개 전부 매핑 존재 + 실재 이벤트만 참조 + 파생 상태 미의존** | `test_schema.py:174-196` |

마지막 항목이 중요하다 — **라벨 누수(파생 상태를 지표 계산에 쓰는 것)를 구조적으로 막는다.**

### 2.5 `tests/test_sink.py` 20건이 고정하는 것

형식 해석 3 · 라운드트립 4 · 스키마 강제 4 · 출처 구분 2 · 결손 관용 4 · manifest 3.
핵심: 재현성 해시 동일성(`test_sink.py:216-225`), Hidden Trait이 저장소에 도달하지 않음(`test_sink.py:138-143`), 빈 Sink가 전 지표를 계산 불가로 표시(`test_sink.py:198-203`).

**테스트가 비어 있는 영역**
- Parquet 실제 쓰기·읽기 (`sink.py:297-302, 318-321`) — pyarrow 부재로 미실행. `test_sink.py:69-73`은 pyarrow가 **있으면** skip하는 반대 방향 테스트다.
- 동일 root 재기록 (§1.6 결함)
- `strict=False` + 무효 event_type (§1.8 결함)
- 타임존·식별자·카테고리 어휘 (§1.4)

---

## 3. T1.3 — 문서 ↔ 코드 정합성 대조

### 3.1 `docs/event_schema.md` ↔ `schema.py` — **완전 일치 (실행 확인)**

```
$ python3 scripts/gen_event_schema_doc.py > /tmp/gen.md
$ diff -u docs/event_schema.md /tmp/gen.md
IDENTICAL
```

문서가 스키마에서 생성되므로(`scripts/gen_event_schema_doc.py:1-6`) 구조적으로 어긋날 수 없다. **이 저장소에서 가장 잘 된 설계 판단이다.**

### 3.2 불일치 전체 목록

| # | 항목 | 문서 | 코드/실측 | 성격 |
|---|---|---|---|---|
| **D-1** | 메타 4종 Nullable | `data_spec.html` §7.2 = **`N`(비허용)** | `schema.py:255-256` META = **OPTIONAL**, `event_schema.md:48-50` "서비스 UI 기록 시 null" | **data_spec이 낡음.** SRS MEA-002(`SRS:826-833`)가 null을 출처 판별에 쓰므로 코드가 옳다 |
| **D-2** | 카테고리 어휘 | `data_spec.html` §6.1 = **한글**(신선식품·간편식·유제품·음료·생활용품) / SRS COM-001 = **영문**(`fresh_food`…) | `schema.py:115` "상품 카테고리 5종" — **열거 없음**. 자체 테스트도 혼용: `test_schema.py:32` `"신선식품"` vs `test_sink.py:35` `"fresh_food"` — **둘 다 통과** | **3자 불일치.** 정본 미확정 |
| **D-3** | `random_seed` | PRD §31 기본 스키마에 **없음**(`PRD:1230-1264`) | SRS DATA-003·`schema.py:135`에 **있음** | PRD가 낡음. 코드는 SRS 상위집합을 따름 — 정상 |
| **D-4** | 저장 테이블 | `data_spec.html` §7.1: `customers`·`orders`·`order_items`·`products`·`marketing_actions`·`assignment` 6종 추가 요구 | `sink.py:191` — **`events`만** | 미구현 (`#44` OPEN 사유 1) |
| **D-5** | 품질 검사 | `data_spec.html` §9: 유일성·참조무결성·시간정합·퍼널정합·금액정합·완전성·재현성 | `src/measurement/validate.py` **부재** | 미착수 (`#48`) |
| **D-6** | `#42` 소유 파일 | 이슈 본문이 `kpi.py`·`economics.py`·`validate.py`를 범위 M 소유물로 열거 | **셋 다 없음** | 미착수 (`#46`·`#47`·`#48`) |
| **D-7** | 파생 상태 기록 경로 | PRD §30.2 · `data_spec` §7.3 "기록은 하되 Feature 금지" | `DerivedStateType`(`schema.py:66-76`)은 `EventType`에 없어 **Sink에 기록할 수단이 없다** | 설계 공백 |
| **D-8** | 타임존 | `event_schema.md:16` "UTC 혼재 불허" | UTC `...Z` 입력이 `validate_event()`를 통과하고 파티션 날짜가 하루 어긋남 (실행 확인) | **선언만, 미강제** |
| **D-9** | Sink 독트링 | `sink.py:113` "파티션 파일로 **append** 한다" | 동일 root 재기록 시 `part-0000` **덮어씀** (실행 확인) | **독트링이 사실과 다름** |
| **D-10** | manifest 내용 | `#44` "버전키 4종, 행 수, 생성 시각, config 해시" | `sink.py:220-245` — 버전키 **값** 없음, config 해시 없음 | 미충족 |
| **D-11** | `AGENTS.md` 현황 | "`src/`에 파트 디렉터리와 지침 파일만 있고 **구현 코드는 아직 없다**" | `schema.py` 350줄 + `sink.py` 321줄 존재 | **T1.5 → `issue-code-audit.md`** |
| **D-12** | `AGENTS.md` 검증 명령 | `python3 -m unittest tests.test_isolation -v` (6건)만 제시 | 실제 46건은 `discover -s tests`. CI(`isolation.yml:41`)와 charter §3.1④는 discover 사용 | 문서가 좁게 적힘 |
| **D-13** | `README.md` | — | **1줄**(`# AI_ROI`) | 빈 문서 |
| **D-14** | `docs/GIT_WORKFLOW.md` | `AGENTS.md`가 "아직 존재하지 않는다 … BOOTSTRAP 절차로 만든다"고 명시 | 부재 확인 | 알려진 미결 (W6 Timothy) |

### 3.3 `docs/data_spec.pdf`

`.gitignore:20`이 무시하고 `git ls-files docs/` 결과에도 없다. 작업 트리에만 존재하는 생성물 — **규약 위반 아님.**

---

## 4. 강점 / 보완점 (근거 첨부)

### 강점

| # | 강점 | 근거 |
|---|---|---|
| S-1 | **문서를 손으로 쓰지 않는다** — 스키마에서 생성. 재생성 diff 0 확인 | `scripts/gen_event_schema_doc.py:1-6`, `docs/event_schema.md:3-4, 178-182` |
| S-2 | **격리가 실패하는 테스트로 강제된다** — gitignore가 아니라 AST 검사. CI 자동 실행 | `tests/test_isolation.py:86-139`, `.github/workflows/isolation.yml:36-41` |
| S-3 | **결손을 0으로 채우지 않는 것이 코드다** — 계산 불가 지표를 명시 목록으로 산출 | `sink.py:240-256`, `test_sink.py:172-203` |
| S-4 | **출처 구분이 스키마에서 파생된다** — 별도 플래그가 없어 위조 여지가 적다 | `sink.py:79-83`, SRS MEA-002 |
| S-5 | **금지 필드가 3중 방어** — 스키마 검사 + 런타임 거부 + 저장 차단 | `test_schema.py:78-81`, `schema.py:285-287`, `test_sink.py:138-143` |
| S-6 | **거부를 조용히 버리지 않는다** — 사유와 함께 `rejected.jsonl` | `sink.py:203-206`, `test_sink.py:128-136` |
| S-7 | **표준 라이브러리만** — 의존성 매니페스트 없이 CI가 돈다 | `schema.py:11-14`, `isolation.yml:34-35` |
| S-8 | **성능을 주장하지 않고 잰다** — 벤치 스크립트 동봉, 내가 재현(4.2M건/64.7초) | `scripts/bench_sink.py` |
| S-9 | **NOT_APPLICABLE이 화이트리스트로 동작** — 이벤트에 안 맞는 필드가 붙으면 거부 | `schema.py:293-297`, `test_schema.py:112-116` |
| S-10 | **라벨 누수 방지가 테스트로 고정** — Observable 지표가 파생 상태에 의존하면 실패 | `test_schema.py:188-196` |

### 보완점

| # | 보완점 | 근거 | 심각도 |
|---|---|---|---|
| W-1 | **동일 root 재기록 시 기존 파티션을 덮어쓴다.** 독트링은 append라고 적혀 있다 | `sink.py:113, 146, 193-195` (실행 확인: 2건+3건 → 3건) | **높음 — 데이터 소실** |
| W-2 | **`strict=False` 경로가 크래시한다.** 이미 거부된 레코드를 `_observe`에 넘긴다 | `sink.py:158-160, 169` (실행 확인: ValueError / KeyError) | **높음** |
| W-3 | **타임존이 강제되지 않는다.** UTC 입력이 통과하고 파티션 날짜가 하루 어긋난다 | `schema.py:29-33`(선언만), `sink.py:271-279` (실행 확인) | **높음 — 코호트·리텐션 계산 왜곡** |
| W-4 | **`check_identifier()`가 어디에서도 호출되지 않는다.** 형식 위반 식별자가 그대로 저장된다 | `schema.py:324-326` 미호출 (실행 확인) | 중 |
| W-5 | **`category`·`page_type` 허용값이 코드에 없다.** 자체 테스트끼리 어휘가 다르고 둘 다 통과 | `schema.py:111-115`, `test_schema.py:32` vs `test_sink.py:35` | 중 |
| W-6 | **Parquet 경로가 한 번도 실행되지 않았다.** 로컬 pyarrow 없음, CI에 설치 단계 없음 | `sink.py:297-302, 318-321`, `isolation.yml:34-35` | 중 — `BLOCKED` |
| W-7 | **manifest에 재현 메타(버전키 값·config 해시)가 없다** | `sink.py:220-245` vs `#44` 요구 | 중 |
| W-8 | **manifest `created_at`이 UTC** — 자기 규약(KST 단일)과 어긋난다 | `sink.py:229` vs `schema.py:29-30` | 낮음 |
| W-9 | **`write_batch()` 미구현** — `#44` 요구 목록에 있으나 없다 | `sink.py` 전체 | 낮음 |
| W-10 | **출처가 저장 레코드·파티션에 남지 않는다.** 대시보드가 출처별로 보려면 전량 재분류 | `sink.py:282-294` | 중 — **W5-C 영향** |
| W-11 | **파생 상태(`inactive`/`at_risk`/`churn`)를 기록할 경로가 없다** | `schema.py:66-76`이 `EventType` 밖 | 중 |
| W-12 | **격리 검사가 `src/` 밖을 보지 않는다.** 대시보드를 `src/` 밖에 두면 사각지대 | `test_isolation.py:51-55` | 중 — **W2 T2.10 입력** |
| W-13 | **`README.md` 1줄, `docs/GIT_WORKFLOW.md` 부재** | `README.md:1` | 낮음 (W6 Timothy) |
| W-14 | **`_digest()`가 전 파일을 재읽기한다.** 112MB 규모에서 close 비용 | `sink.py:258-263` | 낮음 |

---

## 5. BLOCKED

| 항목 | 사유 |
|---|---|
| Parquet 쓰기·읽기 경로 검증 | pyarrow 미설치 (`parquet_available() == False` 실행 확인). 설치는 lockfile/환경 변경이라 금지 |
| `docs/data_spec.pdf` 대조 | PDF 바이너리 — HTML 정본(`docs/data_spec.html`)으로 대조함 |
| 실제 커머스 이벤트로 스키마 왕복 검증 | 커머스에 이벤트 기록이 없다 (`Ecommerce_Service` `#28` 미착수) |
