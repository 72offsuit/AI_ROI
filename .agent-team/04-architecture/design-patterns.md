# 설계 패턴

**작성** James (Role 4 · Architect) · 2026-09-11 · 사이클 C1

> 이 프로젝트에서 반복되는 판단을 이름 붙여 둔다.
> **대부분은 "무엇을 하는가"가 아니라 "무엇을 조용히 하지 않는가"에 관한 것이다** — 이 도메인의 실패는 크래시가 아니라 **그럴듯한 잘못된 숫자**로 온다.

---

# P-1 · 명시적 부재 (Explicit Absence)

**값이 없다는 사실을 값의 자리에 담는다.**

```python
def cogs(order) -> MetricValue:          # ← float 가 아니다
    if not has_cost_basis(order):
        return MetricValue.unavailable(ReasonCode.NO_COST_BASIS, "...")
```

| 어디에 | |
|---|---|
| `MetricValue` 5상태 | `api-contracts.md` §4 |
| JSON Schema 의 `value: null` 강제 | `schemas/common.schema.json` |
| `data_quality_report` 의 `violations: null` | 미실행에 0 을 적지 않는다 |
| `simulator_commit: null` + `null_reason` | 없앰도 빈 문자열도 아니다 |

**안티패턴:** `return 0` · `.get(k, 0)` · `value or 0` · `except: return None` (사유 없음) · 계산되지 않는 지표를 목록에서 빼기.

> **왜 `Optional[float]` 이 아니라 `MetricValue` 인가:** `None` 은 *"없다"* 만 말하고 *"왜 없는지"* 를 말하지 못한다.
> 사유가 없으면 화면이 *"—"* 만 그리고, 사람은 버그인지 정상인지 구별할 수 없다.

---

# P-2 · 계약이 게이트다 (Contract as Gate)

**산출물은 자기 스키마를 통과해야 존재한다.**

게시 전에 `contracts.py` 가 각 산출물을 자기 JSON Schema 로 검사하고, 통과하지 못하면 **게시하지 않는다**(`fail closed`).
읽는 쪽(`lib/artifacts`)도 최소 불변식을 다시 확인하고, 위반이면 **그리지 않는다**.

| 장점 | |
|---|---|
| **규율이 검사가 된다** | *"0 으로 채우지 마세요"* 라는 문장 대신 **스키마가 거부한다** (실행 확인: 위반 시도 7건 전부 거부) |
| 양쪽에서 검사한다 | 쓰는 쪽이 뚫려도 읽는 쪽이 잡는다 |
| 계약이 문서와 코드를 동시에 만족한다 | 스키마가 정본이고 문서는 해설이다 |

**안티패턴:** 계약을 산문으로만 적기 · 잘못된 산출물을 "일단 게시하고 나중에 고치기".

---

# P-3 · ★ 눈먼 계산 (Blind Calculation)

**계약이 편들지 않게 하는 방법은 "편들지 마라"라고 쓰는 것이 아니라, 편들 정보를 주지 않는 것이다.**

```python
# publish.py — 출처를 아는 유일한 자리
by_source = partition_by_source(events)
{
  "commerce":  kpi.average_order_value(by_source.commerce,  index_date=D),
  "simulator": kpi.average_order_value(by_source.simulator, index_date=D),
}
```

`kpi.average_order_value()` 는 **자기가 어느 출처를 받았는지 모른다.** 출처별 결과는 **분기**가 아니라 **입력의 분할**로 나온다.

| | |
|---|---|
| 강제 방법 | `kpi.py`·`economics.py` 소스에 `commerce`·`simulator` 문자열이 없음을 테스트로 고정 (`code-structure.md` N-1·N-3) |
| 부수 효과 | 커머스가 `unit_cost` 를 넣으면 **코드 수정 없이 자동으로 계산된다** |
| 부수 효과 2 | 시뮬레이터가 원가 없는 상품을 만들면 **계산을 거부한다 — 올바르다** |

**안티패턴:** `if source == COMMERCE: return unavailable(...)`.
**같은 패턴의 다른 적용:** `has_cost_basis(order)` — 출처가 아니라 **근거의 유무**로 가른다 (`economic-rule-v1.md` `EC-2`).

---

# P-4 · 분류는 한 곳에서만 (Single Source of Classification)

출처 판정은 **`sink.event_source()` 하나뿐이다.** 다른 모듈이 `simulator_version`·`random_seed` 를 보고 다시 판정하지 않는다.

> 분류 규칙이 두 곳에 있으면 언젠가 갈라지고, **그때 대시보드와 리포트가 다른 숫자를 낸다.**
> 그 순간 어느 쪽이 맞는지 아무도 모른다.

**강제:** `test_neutrality.py::test_source_classification_is_single_sourced`.
**같은 패턴:** 사유 코드 Enum · 허용값 Enum · 계약 상수 — 전부 정본이 하나다.

---

# P-5 · 타입으로 막기 (Make It Unrepresentable)

**틀린 상태를 표현할 방법 자체를 없앤다.**

| 무엇을 막나 | 어떻게 |
|---|---|
| 지표 함수가 0 을 돌려주는 것 | 반환 타입이 `MetricValue` 다. `float` 를 돌려줄 자리가 없다 |
| `economics.py` 가 원가율을 읽는 것 | `CostAccountingConfig` 에 `cost_rate` 가 **없다.** 손에 넣을 방법이 타입에 없다 (`EC-9`) |
| 암묵 기준일 | `index_date` 가 **기본값 없는 키워드 인자**다 (R-1) |
| 전향/후향 혼동 | **함수 이름이 다르다.** 플래그로 만들지 않는다 (R-2) |
| KPI 계층의 출처 합산 | 스키마가 `combined` 키를 **금지**한다 (R-7) |
| UTC 게시 | `generated_at` 정규식이 `+09:00` 만 받는다 |

**안티패턴:** 규약을 주석으로 적고 사람이 지키기를 기대하기.

---

# P-6 · 인덱스를 마지막에 (Last-Write Index)

게시는 staging → `os.replace` → **`index.json` 을 마지막에**. 읽는 쪽은 인덱스를 먼저 읽고 `run_id` 일치를 확인한다.

> **부분 게시 상태를 읽지 않게 하는 가장 싼 방법이다.** 잠금도, 트랜잭션도, 버전 디렉터리도 필요 없다.

**안티패턴:** 파일마다 타임스탬프를 비교하기 · 읽는 쪽이 "대충 최신인 것 같으면" 섞어 쓰기.

---

# P-7 · 소스 검사로 규율 강제 (Source-Level Guard)

**값 검사는 "오늘 우연히 맞다"만 보인다. 소스 검사는 다음 사람이 규칙을 깨는 순간 실패한다.**

이 저장소는 이미 이 패턴을 쓴다 — `tests/test_isolation.py` 가 AST 로 import 를 검사하고, 문자열 상수로 데이터 경로를 검사한다.
C1 은 같은 방식을 **창구 중립성**(`test_neutrality.py`)과 **대시보드 격리**(`test_dashboard_isolation.py`)로 확장한다.

**한계를 먼저 적는다:** 상대 import · 동적 import · f-string 경로를 못 잡는다. **한계를 적지 않은 검사는 통과가 보증으로 오해된다.**

---

# P-8 · 부재로 화이트리스트 (Whitelist by Absence)

`schema.py` 의 `_EVENT_RULES` 에 없는 필드는 자동으로 `NOT_APPLICABLE` 이고, **값이 있으면 거부된다.**

| 효과 | |
|---|---|
| 새 필드가 조용히 흘러들지 않는다 | 규칙에 넣어야 통과한다 |
| **스키마 공백이 드러난다** | 값을 붙일 자리가 없으면 그 정보는 존재할 수 없다 |

**실제로 이 패턴이 공백 3건을 드러냈다** — `shipping_subsidy`(A-0) · `discount`(A-1) · 환불 이벤트(A-2). `data-model-erd.md` §5.

---

# P-9 · 의존성 봉쇄 (Dependency Containment)

**의존성은 입출력 모듈 한 곳에만 산다.**

| 층 | 의존성 |
|---|---|
| 계약·계산·조립 | **표준 라이브러리만** |
| `config_loader.py` | PyYAML (유일한 접점) |
| `sink.py` | pyarrow (이미 guarded) |

**효과:** `isolation.yml` 이 의존성 없이 계속 초록이다(`ISO-005` 유지) — A7 이 지켜진다.
**강제:** `import yaml` 이 `config_loader.py` 한 파일에만 있음을 테스트로 고정 (A7-6).

**안티패턴:** 편의를 위해 계산 모듈에서 config 를 직접 읽기.

---

# P-10 · 범위 한정 문구 필수화 (Mandatory Scope Note)

**부분적으로 한 일은 부분임을 문장으로 남긴다. 그리고 그 문장을 스키마가 요구한다.**

| 어디에 | 무엇을 막나 |
|---|---|
| `data_quality_report.checks[].scope` | 부분 검사가 전체 검사로 읽히는 것 |
| `freeze_status.items[].scope_note` | 부분 Lock 이 전체 Lock 으로 읽히는 것 |
| `metric_value.reason_detail` | *"—"* 만 보이고 왜인지 모르는 것 |

> **문장이 짧아지면 한정이 사라진다.** *"스키마를 Lock 했다"* 는 6개월 뒤에 6테이블까지 덮는 것으로 읽힌다.
> 그래서 **선택 필드로 두지 않고 스키마 `required` 로 만든다.**

---

# P-11 · 3값 게이트 (Three-State Gate)

**`pass` / `fail` 두 값은 "안 했다"를 담지 못한다.**

| 어디에 | 3값 |
|---|---|
| `data_quality_report.gate_result` | `pass` · **`incomplete`** · `fail` |
| 봉인 대조 `verification` | `match` · `mismatch` · `missing` · **`not_run`** |
| `index.publish_result` | `ok` · **`partial`** · `failed` |

> **`incomplete` 이 없으면 미실행이 `pass` 로 숨거나 `fail` 로 과장된다.**
> 전자는 통과로 적는 거짓말이고, 후자는 파이프라인을 영원히 멈춘다. **`not_run` 은 데이터의 실패가 아니라 검사기의 한계다.**

---

# P-12 · 가정을 산출물에 붙여 나른다 (Assumptions Travel)

명시 가정(`refund_adjusted: false`)과 한계(`DASHBOARD_NOT_ISOLATION_CHECKED`)를 **문서가 아니라 게시물의 `notices[]` 에** 담는다.

> **가정은 시간이 지나면 사실로 읽힌다.** 문서에만 있으면 6개월 뒤에 아무도 안 읽는다.
> 화면 옆에 붙어 있으면 그 숫자를 보는 사람이 함께 본다.

---

# P-13 · 생성된 문서 (Generated Documentation)

`docs/event_schema.md` 는 `schema.py` 에서 생성된다(`gen_event_schema_doc.py`). **W1 이 재생성 diff 0 을 실행으로 확인했다.**

> **이 저장소에서 가장 잘 된 설계 판단이다** (W1 S-1). 문서와 코드가 구조적으로 어긋날 수 없다.
> C1 은 이 패턴을 확장하지 않는다 — 게시 계약 스키마는 손으로 쓰되 **예시를 실행으로 검증**한다(`tools/validate_examples.py`). 생성기를 만드는 비용이 7개 파일 규모에서는 이득이 아니다.

---

# 안티패턴 목록 — 이 저장소에서 하지 않는 것

| # | 안티패턴 | 왜 위험한가 | 대신 |
|---|---|---|---|
| **A-1** | 결손을 0 으로 채운다 | 이익이 매출과 같아진다. **숫자는 나오고 아무도 이상하다고 느끼지 않는다** | P-1 |
| **A-2** | 결손을 원가율로 추정한다 | 0 보다 그럴듯해서 **더 위험하다.** `contribution_profit` 이 `revenue` 의 상수배가 되어 PRD §65 가드레일이 죽는다 | `EC-1` |
| **A-3** | 출처로 분기한다 | 창구가 커머스의 구현 상태를 알게 된다. 커머스가 고쳐도 코드가 계속 거부한다 | P-3 |
| **A-4** | 계산되지 않는 지표를 목록에서 뺀다 | 화면이 초록이 되고 **무엇이 계산 불가인지 사라진다** | P-1 |
| **A-5** | 미실행 검사를 `pass` 로 적는다 | 검사하지 않은 것이 보증이 된다 | P-11 |
| **A-6** | 부분 Lock 을 "Lock 했다"로 적는다 | 6테이블까지 봉인된 것으로 읽힌다 | P-10 |
| **A-7** | 대시보드가 계산한다 | 게시물과 화면이 다른 숫자를 낸다. 어느 쪽이 맞는지 모른다 | `DB-012` · P-4 |
| **A-8** | 예외를 사유 없이 삼킨다 | 조용히 도는 코드가 조용히 틀린 값을 만든다 | `exceptions.md` X-2 |
| **A-9** | 없는 라이브러리를 자체 구현으로 대체한다 | 부분 구현 파서가 **조용히 다른 값을 읽는다** | `exceptions.md` §4 |
| **A-10** | 거부 레코드 원문을 게시·로그에 넣는다 | 금지 필드(Hidden Trait)가 화면까지 간다 — `ISO-003` 우회 | `exceptions.md` §8 |
| **A-11** | 존재하지 않는 명령을 문서·게이트에 쓴다 | 실행할 수 없는 검증이 통과로 기록된다 | AGENTS.md |
| **A-12** | 토큰 값을 복사한다 | PRD §69 가 Streamlit 을 기각한 바로 그 이유 | `dashboard-architecture.md` §5 |
