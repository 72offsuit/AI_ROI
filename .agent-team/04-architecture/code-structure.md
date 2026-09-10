# 코드 구조 — KPI·경제 규칙 모듈의 `measurement` 내 배치 (T2.6)

**작성** James (Role 4 · Architect) · 2026-09-11 · 사이클 C1
**푸는 문제** KPI 와 경제 규칙을 창구 안에 넣으면서 **창구 중립성을 깨지 않는 구조**를 정한다.
**정본 근거** `src/AGENTS.md` · SRS `ISO-002` §31 · `economic-rule-v1.md` `EC-2`·`EC-9` · `kpi-definition-v1.md` §2.3

---

# 1. 이 문제가 왜 어려운가 — 한 문단

`measurement` 는 *"아무에게도 의존하지 않는다. 창구가 한쪽 편을 들면 계약이 아니다"* (`src/AGENTS.md`).
그런데 C1 이 넣으려는 것은 **KPI 와 경제 규칙** — 즉 *"커머스에는 원가가 없어서 기여이익을 못 낸다"* 같은 지식이 자연스럽게 들어오는 자리다.
`if source == COMMERCE: 계산 불가` 한 줄이면 오늘 요구는 충족되고, **그 순간 창구가 커머스의 구현 상태를 알게 된다.** 커머스가 나중에 `unit_cost` 를 넣어도(`Ecommerce #25`) 이 코드는 계속 거부한다.

Joshua 가 `EC-2` 로 규칙은 정했다 — *"가르는 기준은 출처가 아니라 `has_cost_basis(order)`"*.
**남은 것은 그 규칙이 지켜질 수밖에 없는 구조를 만드는 일이다.** 아래 §3 의 N-3 이 그 답이다.

---

# 2. 파일 배치

```text
src/measurement/
├── AGENTS.md · CLAUDE.md     [기존 · 봉인]  W6 Timothy 만 수정
├── __init__.py               [기존]  아무것도 import 하지 않는다 (ISO-002)
│
│  ── 계약층 (contract) — 무엇이 통과하는가 ──────────────────
├── schema.py                 [기존 350줄]  필드·이벤트 규칙·식별자·Observable 매핑
│
│  ── 계산층 (pure) — I/O 를 하지 않는다 ────────────────────
├── economics.py              [신설 · #47]  기여이익·비용 회계. 순수 함수
├── kpi.py                    [신설 · #46]  지표 계산 계약. 순수 함수
│
│  ── 입출력층 (io) ──────────────────────────────────────
├── sink.py                   [기존 321줄]  수집·검증·파티션 저장·manifest·되읽기
├── config_loader.py          [신설]        YAML 로딩. ★ PyYAML 의 유일한 접점
├── validate.py               [신설 · #48]  데이터 품질 검사
├── freeze.py                 [신설 · #49]  Lock 기록 작성·해시 대조
│
│  ── 조립층 (composition root) ─────────────────────────
├── contracts.py              [신설]        게시 봉투 생성·계약 상수·자기검증
└── publish.py                [신설 · T2.7] results/ 게시. 유일한 조립 지점
```

**`main.py` 를 두지 않는다.** SRS §31 은 `src/main.py` 를 두지만 C1 에는 실행 루프가 없다(orchestration 미가동). 없는 진입점을 만들지 않는다.

## 2.1 의존 방향 — 아래는 위를 모른다

```text
                      publish.py            ← 유일한 조립 지점
                          │
        ┌────────┬────────┼────────┬────────┐
        ▼        ▼        ▼        ▼        ▼
    contracts  validate  freeze   kpi   economics
        │        │        │        │        │
        └────────┴────┬───┘        └────┬───┘
                      ▼                 ▼
                 sink.py ──────────► schema.py
                      ▲
              config_loader.py  (값만 넘긴다. 위를 모른다)
```

| 규칙 | 내용 |
|---|---|
| **L-1** | `schema.py` 는 아무것도 import 하지 않는다 (표준 라이브러리 제외). **지금 그렇고 계속 그렇다** |
| **L-2** | `kpi.py` · `economics.py` 는 **`sink.py` 를 import 하지 않는다.** 파일도 읽지 않는다 |
| **L-3** | `publish.py` 만 여러 모듈을 조립한다. 다른 모듈은 서로를 최소로 안다 |
| **L-4** | 순환 없음. 위 그래프에 사이클이 없다 |

---

# 3. ★ 창구 중립성을 구조로 만드는 6개 규칙

이름을 붙여 둔다. `design-patterns.md` 와 `build-plan.md` 가 이 번호를 참조한다.

## N-1 · `economics.py` 에 출처 문자열이 없다

```python
# ❌ 금지
if event_source(record) is EventSource.COMMERCE:
    return unavailable("NO_COST_BASIS")

# ✅ 계약
def has_cost_basis(order: Mapping[str, object]) -> bool:
    """주문의 모든 품목에 unit_cost 값이 존재하는가."""

def cogs(order) -> MetricValue:
    if not has_cost_basis(order):
        return unavailable("NO_COST_BASIS", "주문 품목에 unit_cost 값이 없다.")
    return ok(sum(item["unit_cost"] * item["quantity"] for item in order["items"]))
```

**검사 가능** — `economics.py` 소스에 `commerce` · `simulator` 문자열이 없음을 테스트로 고정한다(`economic-rule-v1.md` §3.3 이 "부수 효과"로 지목한 바로 그 검사).

## N-2 · `economics.py` 가 원가율을 읽지 않는다 (`EC-9`)

`config/economic_config.yaml` 의 `product_margin` 블록은 **생성 파라미터**이지 추정 파라미터가 아니다.
읽는 순간 `order_amount × 0.74` 경로가 열리고, 그러면 `contribution_profit` 이 `revenue` 의 상수배가 되어 **PRD §65 가드레일(`revenue_up_profit_down`)이 원리적으로 참이 될 수 없다.**

**구조적 강제:** `config_loader.load_economic_config()` 가 **용도별로 분리된 객체**를 돌려준다.

```python
@dataclass(frozen=True, slots=True)
class CostAccountingConfig:   # economics.py 가 받는 것
    treatment_cost: Mapping[str, int]
    message_cost_krw: int
    campaign_fixed_cost_krw: int
    shipping_fee_krw: int
    free_shipping_threshold_krw: int
    ai_investment: AiInvestmentConfig
    assumptions: Mapping[str, object]      # refund_adjusted: False 등

@dataclass(frozen=True, slots=True)
class ProductGenerationConfig:  # 시뮬레이터(이후 사이클)가 받는 것
    categories: Mapping[str, CategorySpec]   # cost_rate 는 여기에만 있다
```

**`economics.py` 의 함수 시그니처에 `ProductGenerationConfig` 가 등장하지 않는다.** 원가율을 손에 넣을 방법이 타입 수준에서 없다.
검사 가능 — `economics.py` 에 `cost_rate` · `margin_rate` · `product_margin` 참조가 없음을 테스트로 고정한다.

## N-3 · ★ 계산층은 출처를 **알 수 없다** — 분기가 아니라 입력 분할

가장 중요한 규칙이다.

출처별 결과가 필요한 것은 사실이다(`MEA-002`). 그러나 그것을 **계산식의 분기**로 만들면 계약이 편을 든다.
**입력의 분할**로 만들면 계약은 하나로 남는다.

```python
# publish.py — 출처를 아는 유일한 자리
by_source = partition_by_source(events)          # sink.event_source() 사용
report = {
    "by_source": {
        "commerce":  kpi.average_order_value(by_source.commerce,  index_date=D),
        "simulator": kpi.average_order_value(by_source.simulator, index_date=D),
    }
}
```

`kpi.average_order_value()` 는 **자기가 어느 출처의 데이터를 받았는지 모른다.** 같은 함수, 같은 식, 다른 입력이다.

| | 분기로 구현 | 입력 분할로 구현 |
|---|---|---|
| 커머스가 `unit_cost` 를 넣으면 | 코드를 고쳐야 계산된다 | **자동으로 계산된다** |
| 시뮬레이터가 원가 없는 상품을 만들면 | 출처가 시뮬레이터라서 **잘못 계산된다** | **계산을 거부한다 — 올바르다** |
| 계약이 아는 것 | 커머스의 구현 상태 | **자기 계약뿐** |
| 검사 방법 | 사람이 코드를 읽는다 | **`kpi.py`·`economics.py` 에 출처 문자열이 없음을 테스트한다** |

## N-4 · 출처 분류는 `sink.event_source()` 한 곳에만 있다

`sink.py:74-83` 이 이미 구현했다. **다른 모듈이 `simulator_version`·`random_seed` 를 보고 출처를 다시 판정하지 않는다.**
분류 규칙이 두 곳에 있으면 언젠가 갈라지고, 그때 대시보드와 리포트가 다른 숫자를 낸다.

**검사 가능** — `src/measurement/` 안에서 `"simulator_version"` 과 `"random_seed"` 문자열이 함께 등장하는 파일이 `schema.py`(필드 정의)와 `sink.py`(분류) 둘뿐임을 테스트로 고정한다.

## N-5 · 파트 import 금지 — 기존 검사가 이미 강제한다

`tests/test_isolation.py` `FORBIDDEN_IMPORTS["src.measurement"]`. 신규 파일도 자동으로 검사 대상이 된다(`SRC_ROOT.rglob("*.py")`).

## N-6 · 금지 데이터 경로 — 기존 검사가 이미 강제한다

`FORBIDDEN_PATHS["src.measurement"] = ("data/hidden", "data/ground_truth")`.
**`results/` 는 금지 목록에 없다** — 게시가 격리 위반이 아닌 실측 근거다(`api-contracts.md` §1).

---

# 4. 모듈별 책임 — 한 줄씩

| 모듈 | 책임 | 하지 않는 것 |
|---|---|---|
| `schema.py` | 어떤 이벤트가 어떤 필드로 통과하는가 | 저장·계산·게시 |
| `sink.py` | 수집·검증·파티션 저장·manifest·되읽기·**출처 분류** | 지표 계산 |
| `economics.py` | 기여이익·비용 회계. **순수 함수** | 파일 I/O · 출처 판정 · 원가율 참조 |
| `kpi.py` | 지표 계산 계약. **순수 함수** | 파일 I/O · 출처 판정 · 모델 산출물 소비 |
| `config_loader.py` | YAML → 동결 dataclass. **용도별로 분리해 돌려준다** | 계산 |
| `validate.py` | `data_spec` §9 검사 실행 | 게시 (결과 객체만 돌려준다) |
| `freeze.py` | Lock 기록 작성 · 해시 대조 | 게시 · Lock 여부 판단(사람이 한다) |
| `contracts.py` | 게시 봉투 생성 · 계약 상수 · 자기검증 | 계산 |
| `publish.py` | 조립 · 출처 분할 · 원자적 쓰기 | 계산식 보유 |

## 4.1 `kpi.py` 의 시그니처 원칙

```python
def average_order_value(
    events: Sequence[Mapping[str, object]],
    *,
    index_date: date,
    lookback_days: int,
) -> MetricValue: ...
```

- **`index_date` 는 필수 키워드 인자다.** 기본값이 없다 → `kpi-definition-v1.md` R-1 *"'현재'라는 암묵 기준일을 쓰지 않는다"* 를 **시그니처로 강제**한다
- 전향적 지표와 후향적 지표는 **함수 이름이 다르다** (R-2). `churn_rate()` / `churn_label()` 을 같은 함수의 플래그로 만들지 않는다
- 반환은 항상 `MetricValue` 다. **`float` 를 돌려주는 지표 함수가 없다** → 계산 불가를 표현할 자리가 항상 있다. `0.0` 을 돌려줄 방법이 타입에 없다

> **이것이 "결손을 0으로 채우지 않는다"의 코드 수준 강제다.** 문서의 규율이 아니라 반환 타입이다.

## 4.2 `MetricValue` 는 어디에 정의하나

`schema.py` 에 둔다. 이유:

1. `kpi.py` 와 `economics.py` 가 둘 다 쓰는데, 한쪽에 두면 다른 쪽이 그쪽을 import 해야 한다 → 계산층 사이에 불필요한 의존이 생긴다
2. `schema.py` 는 이미 **계약 어휘의 정본**이다(`Requirement`, `EventType`, `FieldSpec`). 계산 불가 사유 코드도 같은 성격의 어휘다
3. `schema.py` 는 아무것도 import 하지 않으므로 순환이 생길 수 없다

```python
# schema.py 에 추가
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
    NOT_RUN = "NOT_RUN"                    # 제안 · D-15
    PRECONDITION_MISSING = "PRECONDITION_MISSING"  # 제안 · D-15
```

> ⚠ **`schema.py` 를 건드리는 것은 `EVENT SCHEMA v1` Lock 대상 파일을 건드리는 것이다.**
> `MetricStatus`·`ReasonCode` 추가는 **이벤트 스키마(22 컬럼 · 16 타입 · Nullable 매트릭스)를 바꾸지 않는다.** `tests/test_schema.py:45-47, 61-72` 가 그 둘을 `assertEqual` 로 고정하고 있으므로 회귀는 즉시 잡힌다.
> 그래도 **`#54`(값 수준 강제) 작업과 같은 PR 에서 하는 편이 안전하다** — `schema.py` 를 두 번 열지 않는다.
> **대안**(별도 `metrics.py` 에 정의)도 유효하다. `build-plan.md` §6 결정 항목 D-18.

---

# 5. `config/` 배치

```text
config/
├── economic_config.yaml     [신설 · #47]  CFG-004. 6블록
└── gate1_lock.yaml          [신설 · #49]  Lock 기록 (기계가독)
```

SRS §31 은 `config/` 에 4개 파일(`simulator_config` · `model_config` · `experiment_config` · `economic_config`)을 열거한다.
`gate1_lock.yaml` 은 **5번째**다 — 구조 확장이다. 근거와 대안은 `adr/ADR-0005-gate1-lock-record.md`.
나머지 3개는 C1 범위 밖이므로 만들지 않는다. **빈 파일을 두지 않는다.**

## 5.1 `economic_config.yaml` 의 6블록과 소비자

`economic-rule-v1.md` §8 의 표를 구조로 옮긴 것이다.

| 블록 | `config_loader` 가 넣는 곳 | `economics.py` 가 보나 |
|---|---|---|
| `product_margin` | `ProductGenerationConfig` | **아니오** (`EC-9`) |
| `treatment_cost` | `CostAccountingConfig` | 예 |
| `cost_accounting` | `CostAccountingConfig` | 예 |
| `shipping` | `CostAccountingConfig` | 예 |
| `ai_investment` | `CostAccountingConfig.ai_investment` | 예 |
| `assumptions` | `CostAccountingConfig.assumptions` → 게시물 `notices` | 값을 나른다 |

---

# 6. `tests/` 배치 — 접두어로 소유가 갈린다

```text
tests/
├── test_isolation.py          [기존 · 봉인]  W6 Matthias + 사용자 승인
├── test_schema.py             [기존]  #54 로 확장
├── test_sink.py               [기존]  #53 으로 확장
├── test_neutrality.py         [신설]  ★ N-1·N-2·N-4 를 소스 검사로 고정
├── test_economics.py          [신설 · #47]
├── test_kpi_definitions.py    [신설 · #46]  이름 ↔ 계산식·모집단·기간·분모 1:1
├── test_kpi_values.py         [신설 · #46]
├── test_quality_checks.py     [신설 · #48]
├── test_publish_contract.py   [신설 · T2.7]  게시물 ↔ JSON Schema
├── test_publish_atomicity.py  [신설 · T2.7]
├── test_freeze.py             [신설 · #49]
└── test_config_loader.py      [신설]  PyYAML 필요 → 없으면 skip
```

## 6.1 `test_neutrality.py` — 창구 중립성을 실패하는 테스트로 만든다

`test_isolation.py` 가 봉인이므로 **거기에 넣지 않고 별도 파일로 만든다.** 표준 라이브러리(`ast` · `pathlib`)만 쓴다.

| 테스트 | 검사 | 강제하는 규칙 |
|---|---|---|
| `test_economics_has_no_source_literal` | `economics.py` 문자열 상수에 `commerce`·`simulator` 없음 | **N-1** (`EC-2`) |
| `test_economics_does_not_read_cost_rate` | `economics.py` 에 `cost_rate`·`margin_rate`·`product_margin` 식별자·문자열 없음 | **N-2** (`EC-9`) |
| `test_kpi_has_no_source_literal` | `kpi.py` 동일 | **N-3** |
| `test_pure_layer_has_no_io` | `kpi.py`·`economics.py` 가 `open`·`Path`·`json`·`csv`·`gzip` 을 import 하지 않음 | **L-2** |
| `test_source_classification_is_single_sourced` | `simulator_version`+`random_seed` 를 함께 참조하는 파일이 `schema.py`·`sink.py` 뿐 | **N-4** |
| `test_metric_functions_return_metric_value` | `kpi.py` 의 공개 함수 반환 애너테이션이 전부 `MetricValue` | **§4.1** |

> **왜 소스 검사인가:** 값 검사로는 "오늘 우연히 맞다"만 보인다. 소스 검사는 **다음 사람이 분기를 넣는 순간 실패한다.**
> `test_isolation.py` 가 import 를 AST 로 검사하는 것과 같은 방식이고, 같은 이유다.

---

# 7. 이후 사이클이 얹힐 자리 — 지금 비워 두는 것

C1 에서 만들지 않지만, **구조가 그것을 받을 수 있어야** 나중에 다시 만들지 않는다.

| 이후 필요 | 지금의 대비 | C1 에서 만드나 |
|---|---|---|
| 실험 판정 지표 계산 (Qini·AUC 등) | `kpi.py` 에 **정의는 있고 구현은 `not_run` 을 돌려준다** | 정의만 |
| `src/decision/` 의 결과 게시 | `results/measurement/` 와 `results/` 루트를 분리해 충돌 자리를 미리 비웠다 | 디렉터리 분리만 |
| 6개 추가 테이블 | `sink.py` 의 `_write_partition` 이 테이블명을 인자로 받도록 열어 둘 수 있다 | **아니오** — `#44` 후속. 열어 두기만 하고 구현하지 않는다 |
| 파생 상태 기록 경로 (W1 D-7) | **설계 공백이다.** `DerivedStateType` 이 `EventType` 밖이라 Sink 에 기록할 수단이 없다 | **아니오 — `#45`(M-3)에서 결정** |
| 시뮬레이터의 `economic_config` 소비 | `ProductGenerationConfig` 를 지금 분리해 둔다 | 타입 분리만 |

> **파생 상태 기록 경로(D-7)를 C1 에서 설계하지 않는 이유:** 기록 수단을 만들려면 `EventType` 에 3종을 추가하거나 별도 테이블을 만들어야 한다.
> 전자는 `tests/test_schema.py:45-47` 이 고정한 **16종을 19종으로 바꾸는 것** — `EVENT SCHEMA v1` 의 실질 변경이다. 후자는 6테이블 문제와 같다.
> **둘 다 `#45` 의 Lock 최종 검산에서 결론을 내야 하고, 아키텍처가 먼저 정하면 그 검산을 건너뛰는 것이 된다.**
