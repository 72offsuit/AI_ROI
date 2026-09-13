---
story_key: M-02
epic: 범위 M — 측정 계층 (이슈 #42)
issue: "#54"
title: 스키마 값 수준 강제 — 식별자·category·page_type + MetricValue 어휘 신설
status: done   # W5 Phillip 완료 — AC-1~7 전부. #53 과 한 PR 로 묶었다
owner: Phillip (W5-A)
phase: 1
blocked_by: []
blocks: ["M-03 (#47)", "M-04 (#46)", "M-06 (게시)", "M-08 (#45)", "M-09 (#49)"]
source_hash: 71caee737d21c72b
source_files: 19
---

# M-02 · 스키마 값 수준 강제 (`#54`) + `MetricValue` 어휘

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
| **대상 이슈** | `#54` — OPEN (2026-09-11 라이브 확인) |
| **관련 이슈** | `#43`(M-1, OPEN) · `#45`(M-3) · `#49`(M-7) |
| **담당** | Phillip · W5-A |
| **Phase** | **1** — 차단 요인 없음. `#53` 과 병렬 가능 |
| **왜 지금인가** | **`EVENT SCHEMA v1` Lock 이후에는 되돌릴 수 없다.** 값 규약이 빠진 채 Lock 되면 `FREEZE-003` — 버전 상향 + 전 데이터 재생성 + Baseline 부터 전 전략 재실행 `[Source: gh issue #54#왜-지금인가]` |
| **차단하는 것** | `#45`(계약 문서가 이 값들을 인용) · `#49`(Lock 선행) · `#48`(식별자 형식 없이는 참조 무결성 검사가 커머스 실측분에 적용되지 않는다) |
| **커밋 type** | `fix` |

> ## ★ 이 스토리는 이슈 `#54` 보다 넓다
> `#54` 는 값 수준 강제만 요구한다. **여기에 `MetricStatus`·`ReasonCode` Enum 신설을 함께 넣는다.**
> 근거: 아키텍처가 그 둘을 `schema.py` 에 두기로 했고(**결정 D-18**), *"`schema.py` 는 Lock 대상이므로 **`#54` 와 같은 PR 에서** 손대는 편이 안전하다 — `schema.py` 를 두 번 열지 않는다"* 고 명시했다
> `[Source: .agent-team/04-architecture/code-structure.md#4.2]` · `[Source: .agent-team/04-architecture/build-plan.md#8]`
>
> **이슈 본문을 수정하지 않는다** (L3 권한). 범위 확장 사실을 **PR 본문에 적는다.**

---

# 2. 스토리

> **`P-커머스`**(`Ecommerce_Service` 구현자)**로서 나는 내가 기록한 값이 계약을 어겼을 때 즉시 거부되기를 원한다.**
> 왜냐하면 통과해 버리면 **잘못된 데이터가 쌓인 뒤에야** 드러나고, 그때는 이미 늦기 때문이다.
> `[Source: .agent-team/03-service-planning/user-stories.md#US-1]`

> **`P-시뮬`**(다음 사이클 시뮬레이터 개발자)**로서 나는 카테고리 어휘가 어느 문서에서든 같기를 원한다.**
> 왜냐하면 SRS 는 영문(`fresh_food`), `data_spec` 은 한글(신선식품), 코드는 열거가 없어서 **어느 것을 써야 할지 알 수 없기** 때문이다.
> `[Source: .agent-team/03-service-planning/user-stories.md#US-2]`

---

# 3. 인수 조건 (AC)

## AC-1 · `category` 허용값 (`#54` D2-2·D2-3)

- [ ] `category` 허용값 **5종을 Enum 으로 정의**하고 `validate_event()` 가 검사한다
- [ ] `category="우주선"` 이 **거부**된다 (현재 통과)
- [ ] **어휘(영문/한글)를 확정하고 근거를 문서에 남긴다** — §4.4
- [ ] `docs/data_spec.html` §6.1 과 SRS `COM-001` 의 차이에 대한 **결론**이 기록된다

## AC-2 · `page_type` 허용값

- [ ] `page_type` 허용값 **8종을 Enum 으로 정의**하고 검사한다
- [ ] `page_type="아무거나"` 가 **거부**된다 (현재 통과)

## AC-3 · 식별자 강제 (`#54` D2-1)

- [ ] **`validate_event()` 가 `check_identifier()` 를 호출한다** — 현재 호출부가 **자기 단위테스트 2곳뿐**이다
- [ ] `customer_id="test-user-1"` 이 **문제로 보고된다** (현재 통과)
- [ ] `None` 인 선택 식별자는 검사하지 않는다 — 결손과 형식 위반을 섞지 않는다

## AC-4 · 어휘 통일

- [ ] `tests/test_schema.py` 와 `tests/test_sink.py` 가 **같은 어휘**를 쓴다
      (현재 `"신선식품"` vs `"fresh_food"` — **둘 다 통과 중**)
- [ ] 허용값 밖의 값이 거부되는 테스트가 각 항목마다 있다

## AC-5 · 문서 재생성

- [ ] `python3 scripts/gen_event_schema_doc.py` 출력이 `docs/event_schema.md` 와 **일치**한다
- [ ] 그 문서에 **허용값 표**가 있다

## AC-6 · `MetricValue` 어휘 (범위 확장분 · 결정 D-18)

- [ ] `MetricStatus` Enum **5종** — `ok` · `unconfirmed` · `unavailable` · `blocked` · `not_run`
- [ ] `ReasonCode` Enum **9종** — 계약 정본과 정확히 일치 (§4.6)
- [ ] 두 Enum 이 **`EventType` 16종·`EVENT_FIELDS` 22개를 바꾸지 않는다** — 기존 `assertEqual` 테스트가 그대로 통과
- [ ] `MetricStatus`·`ReasonCode` 의 값 문자열이 **`schemas/common.schema.json` 의 enum 과 문자 단위로 같다**는 것을 검사하는 테스트가 있다

## AC-7 · 회귀 없음

- [ ] `python3 -m unittest discover -s tests` — 기준선 46건에서 **회귀 0**
- [ ] `python3 -m unittest tests.test_isolation -v` — 통과 (6건)
- [ ] `python3 .agent-team/04-architecture/tools/check_ownership.py` — PASS
- [ ] **의존성 설치 없이** 통과

---

# 4. 개발 컨텍스트 (`developer_context`)

## 4.1 지금 코드가 실제로 무엇을 하는가 — 실측

### D2-1 · `check_identifier()` 가 프로덕션 경로에서 안 쓰인다

```python
# src/measurement/schema.py — 정의는 있다
IDENTIFIER_PATTERNS: dict[str, str] = {
    "event_id":      r"^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$",
    "customer_id":   r"^C\d{8}$",
    "session_id":    r"^S-C\d{8}-\d{13}$",
    "order_id":      r"^O\d{8}-\d{6}$",
    "product_id":    r"^P\d{4}$",
    "coupon_id":     r"^CPN-[A-Z0-9]{6}$",
    "campaign_id":   r"^CMP-\d{8}-\d{3}$",
    "treatment_id":  r"^T[0-4]$",
    "experiment_id": r"^EXP-\d{8}-\d{2}$",
}

def check_identifier(field_name: str, value: str) -> bool:
    pattern = IDENTIFIER_PATTERNS.get(field_name)
    return True if pattern is None else bool(re.fullmatch(pattern, value))
```

**`validate_event()` 도 `EventSink` 도 이 함수를 부르지 않는다.** 호출부는 `tests/test_schema.py:159,171` 둘뿐이다.

**리드 재현 확인:**
```python
validate_event({... "customer_id": "test-user-1", "session_id": "whatever" ...})
#   → []                     (통과. 그대로 저장된다)
check_identifier("customer_id", "test-user-1")
#   → False                  (형식 위반은 맞다 — 아무도 묻지 않을 뿐)
```
`[Source: gh issue #54#D2-1]`

**커머스의 현재 식별자가 정확히 이 형태다** — `test-user-1`(`seed-data.ts:97`) · `dummyjson-16`(`seed-data.ts:5`) · `randomUUID()`(`orders.ts:115`).

### D2-2 · 허용값이 코드에 없다

```python
# src/measurement/schema.py — 설명 문자열뿐, 열거가 없다
FieldSpec("category", "category", FieldGroup.PRODUCT, "상품 카테고리 5종"),
FieldSpec("page_type", "category", FieldGroup.SESSION,
          "home / list / search / detail / cart / checkout / complete / history"),
```

```python
tests/test_schema.py:32    "category": "신선식품"      # 한글
tests/test_sink.py:35      "category": "fresh_food"    # 영문
#                          ↑ 둘 다 통과한다
```

**리드 재현 확인:** `validate_event({... "page_type": "아무거나" ...})` → `[]`
`[Source: gh issue #54#D2-2]`

### D2-3 · 카테고리 어휘 3자 불일치

| 출처 | 값 |
|---|---|
| SRS `COM-001` (`Plan/…SRS_v2.0.md:434-444`) | `fresh_food` `meal_solution` `dairy` `beverage` `household` |
| `docs/data_spec.html` §6.1 | 신선식품 · 간편식 · 유제품 · 음료 · 생활용품 |
| `src/measurement/schema.py` | **열거 없음** |

`[Source: gh issue #54#D2-3]`

## 4.2 확정된 허용값 — **이 값을 쓴다**

### `category` 5종

| 코드 | 표시명 | 원가율 | 기여마진율 | 가격 중앙값 | 구매빈도 가중 | Pool |
|---|---|---|---|---|---|---|
| `fresh_food` | 신선식품 | 78% | 22% | 8,900원 | 0.32 | 70 |
| `meal_solution` | 간편식 | 70% | 30% | 6,500원 | 0.24 | 55 |
| `dairy` | 유제품 | 75% | 25% | 4,200원 | 0.18 | 35 |
| `beverage` | 음료 | 68% | 32% | 3,500원 | 0.14 | 40 |
| `household` | 생활용품 | 72% | 28% | 12,000원 | 0.12 | 40 |

`[Source: .agent-team/03-service-planning/economic-rule-v1.md#2]`
**가중평균 기여마진율 26.0% · 총 240개.** 원가율은 이 스토리에서 쓰지 않는다 — **M-03 의 config 값이다.**

### `page_type` 8종

```
home · list · search · detail · cart · checkout · complete · history
```

`[Source: src/measurement/schema.py#EVENT_FIELDS page_type description]`
**이것이 유일한 출처다.** 다른 문서에 8종 열거가 없다 — 이 문자열이 정본이 된다.

## 4.3 ★ 어휘 결정 — **영문 코드** (기획 권고, 근거 3개)

`economic-rule-v1.md` §2 가 같은 결론에 도달했다 `[Source: .agent-team/03-service-planning/economic-rule-v1.md#2]`:

1. **SRS `COM-001` 이 영문 코드로 규정한다** (`SRS:434-444`) — 정본이다
2. `data_spec` §6.1 의 한글은 **표 가독성 표기로 보인다**
3. **표시명 매핑은 UI 책임이다** — 측정 계층은 코드만 안다

**추가 근거 2개:**

4. `data_spec` §8 이 `category_share_fresh` 외 4개를 CLV Feature 로 요구한다. **Feature 이름이 영문이므로 값도 영문이어야 자연스럽다** `[Source: gh issue #54#왜-지금인가]`
5. **`config/economic_config.yaml` 의 카테고리 키가 같은 어휘를 써야 한다** (US-2 인수조건 4). YAML 키에 한글을 쓰는 것은 `PyYAML` 로 가능하지만 도구 호환성을 좁힌다

> **다만 `economic-rule-v1.md` 가 명시했다:** *"단 이것은 `#54` 의 결정 사항이다. 이 문서는 같은 결론을 내렸다는 사실만 기록하고, 확정은 `#54` 에서 한다."*
> **→ 확정은 이 스토리에서 한다. 결론과 근거를 문서에 남기는 것이 AC-1 이다.**

**결론을 남길 자리:**

| 자리 | 무엇을 |
|---|---|
| `src/measurement/schema.py` Enum 독트링 | *"SRS COM-001 이 정본. `data_spec` §6.1 의 한글은 표기이며 표시명 매핑은 UI 책임"* |
| `docs/event_schema.md` (재생성) | 허용값 표 |
| PR 본문 | 3자 불일치의 결론 |

## 4.4 ★ 식별자 강제의 수위 — **결정이 필요하다**

`#54` 미확정 표가 **거부**를 제안했다 `[Source: gh issue #54#미확정]`:

> *"**거부.** 단 `MEA-003`(부분 소스 관용)과 충돌하지 않도록, **커머스 실측분에는 매핑 계층을 두는 쪽**을 `#45` 계약에 명시"*
> *"매핑 책임 위치: **커머스가 기록 시점에 변환.** 측정 계층이 소스별 예외를 알면 창구 중립성이 깨진다"*

> ### ⚠ 이것이 창구 중립성의 시험대다
> `if source == COMMERCE: skip_identifier_check` 를 쓰고 싶어진다. **금지다.**
> *"측정 계층에 '커머스는 이런 ID 를 쓴다'는 지식이 들어가면 **창구가 한쪽 편을 드는 것**이 된다. 계약은 하나여야 하고, 맞추는 쪽은 소스다."*
> `[Source: gh issue #54#미확정]` · `[Source: src/AGENTS.md#import-규칙]`
>
> **`validate_event()` 는 출처를 모른다.** 지금도 그렇고 계속 그래야 한다.

**그럼 커머스는 어떻게 되나** — 그것이 `strict=False` 관용 모드의 존재 이유다:

```
strict=True   → 형식 위반 레코드를 거부한다 (기본)
strict=False  → 거부 카운트와 rejected.jsonl 에 남기되 수집은 죽지 않는다
```

**M-01(`#53`)이 `strict=False` 크래시를 고치면 이 경로가 실제로 살아난다.** 두 스토리가 여기서 만난다.

### 선택지 — 구현자가 정하고 PR 에 적는다

| | ⑴ 문제로 보고 (권장) | ⑵ 별도 심각도 축을 만든다 |
|---|---|---|
| 방법 | `validate_event()` 의 `problems` 리스트에 다른 문제와 같이 넣는다 | `problems` 와 `warnings` 를 나눈다 |
| 결과 | `strict=True` 면 거부 · `strict=False` 면 기록 | 형식 위반만 경고로 통과시킬 수 있다 |
| 위험 | 커머스 실측분이 전량 거부된다 (오늘 이벤트가 0건이라 실해는 없다) | **반환 타입이 바뀐다.** `validate_event()` 를 쓰는 곳이 전부 영향 |
| 정본 | `#54` 미확정 표가 **거부**를 제안 | 어느 문서도 요구하지 않는다 |

> **⑴을 권장한다.** ⑵는 `list[str]` 반환 계약을 바꾸고 `sink.py:151` · `test_schema.py` 다수를 흔든다. **`#54` 가 요구한 것은 "보고한다"까지다.**

## 4.5 ★ `None` 을 형식 위반으로 보고하지 않는다 — 가장 밟기 쉬운 함정

```python
# ❌ 이렇게 하면 선택 필드가 전부 위반이 된다
for name in IDENTIFIER_PATTERNS:
    if not check_identifier(name, record.get(name)):     # None 이 들어간다 → TypeError 또는 False
        problems.append(...)
```

`validate_event()` 는 **이미 결손과 형식을 분리해 다룬다:**

```python
# src/measurement/schema.py — 결손은 여기서만 본다
for name in sorted(required_fields(event_type)):
    if record.get(name) is None:
        problems.append(f"{event_type.value}: 필수 필드 누락 — {name}")
```

**식별자 검사는 "값이 있는 것"만 본다:**

```python
# ✅ 기존 루프를 따른다 — 이미 None 과 미지 필드를 건너뛴다
for name, value in record.items():
    if value is None or name not in FIELD_INDEX:
        continue
    ...
```

**같은 규율이 허용값 검사에도 적용된다.** `category` 가 `None` 인 것은 결손이지 위반이 아니다.

## 4.6 ★ `MetricStatus`·`ReasonCode` — 계약이 정본이다

**기획 문서(7종)와 계약(9종)이 다르면 계약이 이긴다** (리드 판정).
`[Source: .agent-team/07-design/design-handoff.md#0.0]`

```python
# schemas/common.schema.json  $defs.reason_code.enum — 문자 단위로 이것과 같아야 한다
"NO_SOURCE_EVENT", "MISSING_FIELD", "NO_COST_BASIS", "NEEDS_TWO_STRATEGIES",
"NEEDS_MODEL_OUTPUT", "PARAM_UNCONFIRMED", "BLOCKED", "NOT_RUN", "PRECONDITION_MISSING"

# schemas/common.schema.json  $defs.metric_value.properties.status.enum
"ok", "unconfirmed", "unavailable", "blocked", "not_run"
```

`[Source: .agent-team/04-architecture/schemas/common.schema.json#$defs.reason_code]`

**아키텍처가 제시한 형태** `[Source: .agent-team/04-architecture/code-structure.md#4.2]`:

```python
class MetricStatus(str, Enum):
    OK = "ok"; UNCONFIRMED = "unconfirmed"
    UNAVAILABLE = "unavailable"; BLOCKED = "blocked"; NOT_RUN = "not_run"

class ReasonCode(str, Enum):
    NO_SOURCE_EVENT = "NO_SOURCE_EVENT"
    MISSING_FIELD = "MISSING_FIELD"
    NO_COST_BASIS = "NO_COST_BASIS"
    NEEDS_TWO_STRATEGIES = "NEEDS_TWO_STRATEGIES"
    NEEDS_MODEL_OUTPUT = "NEEDS_MODEL_OUTPUT"
    PARAM_UNCONFIRMED = "PARAM_UNCONFIRMED"
    BLOCKED = "BLOCKED"
    NOT_RUN = "NOT_RUN"
    PRECONDITION_MISSING = "PRECONDITION_MISSING"
```

### 왜 `schema.py` 인가

1. `kpi.py` 와 `economics.py` 가 둘 다 쓴다. 한쪽에 두면 다른 쪽이 그쪽을 import 해야 한다 → **계산층 사이에 불필요한 의존**
2. `schema.py` 는 이미 **계약 어휘의 정본**이다 (`Requirement`·`EventType`·`FieldSpec`)
3. `schema.py` 는 아무것도 import 하지 않으므로 **순환이 생길 수 없다**

`[Source: .agent-team/04-architecture/code-structure.md#4.2]`

> **결정 D-18 의 대안** — 별도 `metrics.py` 에 두는 것도 유효하다 `[Source: .agent-team/04-architecture/build-plan.md#8]`.
> **⑴(`schema.py`)을 권장한다.** 다만 **`MetricValue` dataclass 자체를 여기서 만들지는 않는다** — §4.7.

## 4.7 ⚠ 범위 경계 — 여기서 `MetricValue` **dataclass** 를 만들지 않는다

| 만든다 (M-02) | 만들지 않는다 (M-03·M-04) |
|---|---|
| `MetricStatus` Enum | `MetricValue` dataclass (필드·생성자·`ok()`/`unavailable()` 헬퍼) |
| `ReasonCode` Enum | `Basis` dataclass |
| 계약 enum 과의 일치 테스트 | `BlockerRef` dataclass |

**이유:** `MetricValue` 의 필드 구성은 `basis` 필수/금지 규칙과 엮여 있고, 그것을 **처음 실제로 쓰는 것이 `economics.py`(M-03)** 다.
**어휘(Enum)만 먼저 두면 M-03·M-04 가 같은 것을 두 번 정의하지 않는다.**

`MetricValue` 를 어디에 두는지는 M-03 이 정한다. 이 스토리는 **Enum 2개만** 놓는다.

## 4.8 함정

| # | 함정 | 왜 빠지나 | 대신 |
|---|---|---|---|
| **T-1** | `category` Enum 을 `EventType` 처럼 `str, Enum` 이 아닌 `Enum` 으로 만든다 | 습관 | `str, Enum` 으로. 기존 Enum 전부 그렇고 JSON 직렬화가 자연스럽다 |
| **T-2** | 허용값 검사를 `requirement()` 안에 넣는다 | 이벤트별 규칙이 거기 있다 | **`validate_event()` 에 넣는다.** `requirement()` 는 필수/선택/해당없음만 판정한다 |
| **T-3** | `check_identifier()` 를 전 필드에 돌린다 | 짧다 | `IDENTIFIER_PATTERNS` 에 없는 필드는 `True` 를 돌려주므로 동작은 맞다. 다만 **`None` 을 먼저 걸러야 한다** (§4.5) |
| **T-4** | `test_sink.py` 의 어휘를 `test_schema.py` 에 맞춘다 (한글로) | 파일 두 개 중 하나를 고치는 것이 짧다 | **영문으로 통일한다** (§4.3). `test_schema.py:32` 를 고친다 |
| **T-5** | `MetricStatus` 값에 대문자를 쓴다 (`"OK"`) | `ReasonCode` 가 대문자라서 | **계약이 소문자다** (`"ok"`·`"not_run"`). `ReasonCode` 만 대문자다. **섞이는 것이 정상이고 계약이 그렇다** |
| **T-6** | `docs/event_schema.md` 를 손으로 고친다 | 빠르다 | **생성 문서다.** `scripts/gen_event_schema_doc.py` 를 고치고 재생성한다. 손으로 고치면 다음 재생성에서 지워진다 `[Source: .agent-team/04-architecture/design-patterns.md#P-13]` |
| **T-7** | `if source == COMMERCE: skip` | 커머스 식별자가 전부 위반이라 | **§4.4 — 창구 중립성 위반.** 맞추는 쪽은 소스다 |

---

# 5. 작업 분해 (Tasks)

## T1 · 실패하는 테스트 (AC-1·2·3·4)

- [ ] `tests/test_schema.py` `TestValidateEvent` 에 `test_unknown_category_is_rejected` — `category="우주선"` → 문제 보고
- [ ] `test_unknown_page_type_is_rejected` — `page_type="아무거나"` → 문제 보고
- [ ] `test_malformed_identifier_is_reported` — `customer_id="test-user-1"` → 문제 보고
- [ ] `test_none_identifier_is_not_a_format_violation` — 선택 식별자가 `None` 일 때 형식 위반으로 보고되지 **않는다** (§4.5)
- [ ] **전부 실패하는 것을 확인하고 출력을 PR 에 남긴다**

## T2 · Enum 3개 + 검사 (AC-1·2·3)

- [ ] `Category` Enum 5종 — `str, Enum`. 독트링에 §4.3 결론
- [ ] `PageType` Enum 8종 — `str, Enum`
- [ ] `validate_event()` 에 허용값 검사 추가 — **`None` 은 건너뛴다**
- [ ] `validate_event()` 에 `check_identifier()` 호출 추가 — **`None` 은 건너뛴다**
- [ ] `FieldSpec` 의 설명 문자열을 Enum 참조로 정리 (선택 — 재생성 문서에 영향)

## T3 · 어휘 통일 (AC-4)

- [ ] `tests/test_schema.py:32` 의 `"신선식품"` → `"fresh_food"`
- [ ] 두 파일의 모든 `category` 값이 `Category` Enum 값인지 확인
- [ ] `page_type` 값도 `PageType` Enum 값인지 확인 (`test_sink.py:19` 헬퍼 포함)

## T4 · `MetricStatus`·`ReasonCode` (AC-6)

- [ ] `schema.py` 에 Enum 2개 추가 (§4.6)
- [ ] `tests/test_schema.py` 에 **계약 대조 테스트** 추가:
      `.agent-team/04-architecture/schemas/common.schema.json` 을 `json.load` 로 읽어
      `$defs.reason_code.enum` 과 `ReasonCode` 값 집합이 **같은지** 단언
      `$defs.metric_value.properties.status.enum` 과 `MetricStatus` 값 집합이 **같은지** 단언
- [ ] 기존 `assertEqual` 2건(16종·22컬럼)이 그대로 통과하는지 확인

> **T4 마지막 테스트가 중요하다.** 계약이 바뀌면 코드가 **실패로 알려준다.** 표준 라이브러리(`json`·`pathlib`)만 쓰므로 `jsonschema` 없이 돈다.
> **경로 주의:** `.agent-team/` 은 `src/` 밖이므로 `test_isolation.py` 의 검사 대상이 아니다. 상대 경로는 `Path(__file__).resolve().parents[1]` 기준으로 만든다 (`test_isolation.py:22` 와 같은 관례).

## T5 · 문서 재생성 (AC-5)

- [ ] `scripts/gen_event_schema_doc.py` 가 허용값 표를 내보내도록 수정
- [ ] `python3 scripts/gen_event_schema_doc.py > docs/event_schema.md` — ★ **stdout 이다**(`scripts/gen_event_schema_doc.py:36` `print`). 리다이렉트 없이는 재생성되지 않는다 (Thomas N-6)
- [ ] 출력과 `docs/event_schema.md` 가 **일치**하는지 확인 (`diff`)

## T6 · 검증 (AC-7)

- [ ] `python3 -m unittest discover -s tests` — 출력 전문을 PR 에
- [ ] `python3 -m unittest tests.test_isolation -v`
- [ ] `python3 .agent-team/04-architecture/tools/check_ownership.py`
- [ ] `git -C ../Ecommerce_Service status --porcelain` 빈 출력

---

# 6. 파일 목록 (`file_list`)

## 6.1 이 스토리가 만지는 파일

| 파일 | 동작 |
|---|---|
| `src/measurement/schema.py` | **수정** — `Category`·`PageType`·`MetricStatus`·`ReasonCode` Enum 신설 · `validate_event()` 확장 |
| `tests/test_schema.py` | **수정** — 거부 테스트 4건 + 계약 대조 2건 + 어휘 수정 |
| `tests/test_sink.py` | **조건부 수정** — 어휘 통일이 필요하면 |
| `scripts/gen_event_schema_doc.py` | **수정** — 허용값 표 출력 |
| `docs/event_schema.md` | **재생성** — 손으로 고치지 않는다 |

## 6.2 절대 만지지 않는 파일

```
tests/test_isolation.py · .github/workflows/isolation.yml          ← 봉인
src/simulator/** src/decision/** src/diagnostics/** src/orchestration/**
Plan/**                                                            ← 서브모듈
AGENTS.md · src/AGENTS.md · src/*/AGENTS.md · src/*/CLAUDE.md · README.md
dashboard/**                                                       ← Andrew
../Ecommerce_Service/**                                            ← 읽기만
.agent-team/04-architecture/schemas/*.json                         ← W2 산출물. 읽기만
```

> **마지막 줄 주의:** T4 의 대조 테스트는 계약 스키마를 **읽기만** 한다. 코드와 어긋나면 **코드를 고친다.** 계약을 고치지 않는다.

## 6.3 M-01 과 같은 파일을 만진다

**`src/measurement/schema.py` 를 M-01(`#53` D1-3, 타임존)도 만질 수 있다.**
`#53` 미확정이 *"D1-3 은 `#54` 와 함께 처리하는 편이 자연스러울 수 있습니다"* 라고 적었다.

**둘 중 하나:**
- **한 PR 로 묶는다** — `Closes #53, Closes #54`. `schema.py` 를 한 번만 연다
- **순서를 정한다** — 먼저 끝난 쪽이 머지된 뒤 다른 쪽이 rebase

**구현자가 정하고 PR 에 적는다.** (M-01 §9.3 M01-e 와 같은 결정)

---

# 7. 테스트

## 7.1 실행 가능한 명령

```bash
python3 -m unittest discover -s tests
python3 -m unittest tests.test_schema -v          # 이 스토리의 주 대상
python3 -m unittest tests.test_isolation -v
python3 scripts/gen_event_schema_doc.py > docs/event_schema.md   # ★ stdout — 리다이렉트 필수
python3 scripts/gen_event_schema_doc.py | diff - docs/event_schema.md    # 일치 확인
python3 .agent-team/04-architecture/tools/check_ownership.py
```

## 7.2 깨뜨리면 안 되는 기존 테스트

| 테스트 | 무엇을 고정하나 |
|---|---|
| `test_schema.py:45-47 test_sixteen_raw_event_types` | **`EventType` 정확히 16종** — `assertEqual` |
| `test_schema.py:61-72 test_data_003_columns_present` | **`EVENT_FIELDS` 정확히 22개** — `assertEqual`, 부분집합 아님 |
| `test_schema.py:49-53 test_derived_states_are_not_raw_events` | `DerivedStateType` ∩ `EventType` = ∅ |
| `test_schema.py:78-81 test_no_forbidden_field_leaked_into_schema` | `FORBIDDEN_FIELD_NAMES` 25종이 스키마에 없다 |
| `test_schema.py:101-105 test_minimal_records_pass_for_every_event_type` | ★ **16종 전부의 최소 레코드가 통과한다** — 허용값 검사를 추가하면 **이 테스트가 먼저 깨진다.** 헬퍼 `_base_record()` 의 값이 새 Enum 을 만족해야 한다 |
| `test_sink.py:198-203 test_empty_sink_marks_every_metric_unavailable` | ★ **USP-1 의 회귀 테스트.** 깨뜨리지 않는다 |

> **`test_minimal_records_pass_for_every_event_type` 가 이 스토리에서 가장 먼저 깨진다.**
> `tests/test_schema.py:18 _base_record()` 의 `category`·`page_type` 기본값을 Enum 값으로 바꾸는 것이 T3 의 실질이다.

## 7.3 새 테스트가 쓸 헬퍼

```python
tests/test_schema.py:18   _base_record(event_type, **overrides)   # 이벤트 타입별 최소 유효 레코드
tests/test_sink.py:19     simulator_event(event_type=..., **overrides)
tests/test_sink.py:47     commerce_event(*args, **overrides)
```

**새로 만들지 않는다.** 기존 헬퍼에 `overrides` 로 위반 값을 주입한다.

---

# 8. 연속성

## 8.1 선행 스토리

**없다.** Phase 1 이고 차단 요인이 없다. **M-01 과 병렬이지만 같은 파일(`schema.py`)을 만질 수 있다** — §6.3.

## 8.2 이미 머지된 코드에서 이어받는 것

| 출처 | 이어받는 것 |
|---|---|
| PR **#50** (`105e83c`) — M-1 | `schema.py` 의 구조: 전역 규약 → EventType → FieldSpec → 이벤트별 규칙 → `validate_event()` → 식별자 → Observable 매핑. **새 Enum 은 "필드 정의" 절 근처에 둔다** |
| PR **#51** (`d1ca26f`) — M-2 | `sink.py` 가 `validate_event()` 를 쓰는 방식 (`sink.py:151`). 반환 타입을 바꾸면 여기가 깨진다 |

## 8.3 확립된 패턴

| 패턴 | 어디에 |
|---|---|
| **Enum 은 `str, Enum`** | `EventType` · `DerivedStateType` · `FieldGroup` · `Requirement` · `SinkFormat` · `EventSource` |
| **모듈 상수 뒤에 `"""독트링"""`** | `SCHEMA_VERSION` · `TIMEZONE` · `FEATURE_FORBIDDEN_FIELDS` — 왜 그런지를 적는다 |
| **`validate_event()` 는 예외를 던지지 않고 `list[str]` 을 돌려준다** | `schema.py` — 알 수 없는 `event_type` 일 때만 조기 반환 |
| **한글 문제 메시지** | `f"{event_type.value}: 필수 필드 누락 — {name}"`. 새 메시지도 한글로 |
| **문서는 코드에서 생성된다** | `scripts/gen_event_schema_doc.py` — W1 이 재생성 diff 0 을 실행 확인했다 |

## 8.4 M-01 에서 이어받을 수 있는 것

M-01 이 **먼저 끝나면** 그 결과가 이 스토리에 들어온다:

| M-01 결과 | 이 스토리에서 |
|---|---|
| 타임존 정책 ⑴(거부) 선택 시 | `validate_event()` 에 **타임존 검사가 이미 있다.** 허용값 검사를 그 옆에 붙인다 |
| 타임존 정책 ⑵(변환) 선택 시 | `validate_event()` 는 오프셋 존재만 본다. 허용값 검사와 독립 |
| `strict=False` 복구 | **식별자 강제의 안전판이 생긴다** — 커머스 실측분이 전량 거부되어도 수집이 죽지 않는다 (§4.4) |

---

# 9. 완료 정의 (DoD) · 미결정 · 차단

## 9.1 DoD

- [ ] AC-1 ~ AC-7 전부 체크
- [ ] **먼저 실패하는 테스트**를 쓰고 그 출력을 PR 에 남겼다
- [ ] 어휘 결론과 3자 불일치 처리를 **문서에 남겼다** (§4.3)
- [ ] 식별자 강제 수위(§4.4)를 **PR 에 적었다**
- [ ] `MetricStatus`·`ReasonCode` 가 **계약과 문자 단위로 일치**하고 그것을 테스트가 고정한다
- [ ] **범위 확장(§1) 사실을 PR 본문에 적었다** — 이슈 본문은 수정하지 않는다
- [ ] `#54` 를 **닫지 않았다**

## 9.2 이 스토리에서 하지 않는 것

| 항목 | 왜 |
|---|---|
| 커머스 측 식별자 변경 | **별도 저장소.** 편집 금지. `#45` 계약에 요구사항만 적는다 |
| 매핑 계층 구현 | *"맞추는 쪽은 소스"* — 측정 계층에 넣지 않는다 |
| `MetricValue` dataclass | **M-03 의 몫** (§4.7) |
| `economic_config.yaml` 의 카테고리 블록 | **M-03 의 몫.** 이 스토리는 Enum 만 |
| 원가율 사용 | **`economics.py` 는 원가율을 읽지 않는다** (`EC-9`). M-03 참조 |
| 6개 추가 테이블의 식별자 | C1 범위 밖 |

## 9.3 미결정 — 구현자가 정하고 PR 에 적는다

| # | 항목 | 선택지 | 참조 |
|---|---|---|---|
| **M02-a** | 식별자 위반의 표현 | ⑴ `problems` 에 넣는다 **(권장)** ⑵ 별도 축 | §4.4 |
| **M02-b** | `MetricStatus`·`ReasonCode` 위치 | ⑴ `schema.py` **(권장 · D-18)** ⑵ 별도 `metrics.py` | §4.6 |
| **M02-c** | `#53` 과 한 PR 로 묶는가 | 묶는다 / 나눈다 | §6.3 |
| **M02-d** | `FieldSpec` 설명 문자열을 Enum 참조로 바꾸는가 | 바꾼다 / 유지 | 재생성 문서 형태에 영향 |

## 9.4 차단 — 없다

**어휘는 이 스토리가 확정한다.** 사용자 결정을 기다리지 않는다 — `#54` 가 결정 권한을 이 작업에 두었다.

## 9.5 하류로 넘기는 것

| 받는 스토리 | 넘기는 것 |
|---|---|
| **M-03 (`#47`)** | `Category` Enum → `economic_config.yaml` 의 `product_margin` 키가 같은 어휘를 쓴다 (US-2 인수조건 4) · `ReasonCode.NO_COST_BASIS` |
| **M-04 (`#46`)** | `MetricStatus`·`ReasonCode` 전부 |
| **M-06 (게시)** | 두 Enum 이 계약 enum 과 일치한다는 보장 |
| **M-08 (`#45`)** | **확정된 허용값과 식별자 형식** — 계약 문서가 이것을 **인용**한다. 값을 다시 정의하지 않는다 (US-15 인수조건 2) · **커머스 매핑 요구사항**(별도 저장소 이슈 초안) |
| **M-09 (`#49`)** | 선행 조건 **`G-1`**(category Enum)·**`G-2`**(page_type Enum)·**`G-3`**(`check_identifier` 호출)·**`G-4`**(어휘 정본) 충족 증거 |
| **d-02 (대시보드)** | 사유 코드 9종의 정확한 문자열 — 화면이 이 코드를 시각 상태로 매핑한다 |

<!-- ════════ source_hash inputs (D3 · Matthias 항목5) ════════
     계산법: project-context-kr.md §12  ·  파일 19종
     재현:  아래 목록을 sorted() 하고 각 파일에 f"{path}\n{sha256_hex}\n" 를 이어붙여
            그 바이트열의 SHA-256 앞 16자리를 취한다. 없는 파일은 "MISSING".

     .agent-team/00-plan/charter.md
     .agent-team/00-plan/task-graph.md
     .agent-team/03-service-planning/economic-rule-v1.md
     .agent-team/03-service-planning/gate1-lock-scope.md
     .agent-team/03-service-planning/user-stories.md
     .agent-team/04-architecture/adr/ADR-0003-metric-value-shape.md
     .agent-team/04-architecture/build-plan.md
     .agent-team/04-architecture/code-structure.md
     .agent-team/04-architecture/design-patterns.md
     .agent-team/04-architecture/exceptions.md
     .agent-team/04-architecture/schemas/common.schema.json
     AGENTS.md
     docs/GIT_WORKFLOW.md
     docs/event_schema.md
     scripts/gen_event_schema_doc.py
     src/AGENTS.md
     src/measurement/schema.py
     tests/test_schema.py
     tests/test_sink.py

     → source_hash = 71caee737d21c72b
     ════════════════════════════════════════════════════ -->
