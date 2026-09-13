# API 문서 — `measurement-publish/v1`

**작성** Timothy (Role 11 · W6 문서) · 2026-09-14
**대상 브랜치** `feat/measurement-layer-and-dashboard` (PR #57, 미병합) — 이 문서의 모든 코드 인용은 이 브랜치 기준
**기계가독 정본** `docs/contracts/measurement-publish/v1/*.schema.json` (JSON Schema draft 2020-12). **이 문서는 그 스키마 + 실제 구현 코드의 해설이다. 충돌하면 스키마가 정본이다.**
**동결 스냅샷(고치지 않음)** `.agent-team/04-architecture/schemas/` — W2 산출물. 실제 계약은 `docs/contracts/measurement-publish/v1/`이 W5(M-06)부터 정본이다(`CHANGELOG.md`).

> ⚠ **이 프로젝트에는 HTTP API가 없다.** 대시보드는 `results/`의 파일을 읽는다(SRS `DB-013`). 아래의 "API"는 REST 엔드포인트가 아니라 **게시물(published artifact)의 경로·형식·읽기 규약**이다.

---

## 1. 전체 그림

```
python3 -m src.measurement.publish --source data/raw --out results
                    │
                    ▼
results/
├── data_quality_report.json          ← V5 (정본 경로 고정, data_spec §9)
└── measurement/
    ├── index.json                    ← V0 인덱스. 가장 먼저 읽는다
    ├── ingestion_report.json         ← V1 수집 현황
    ├── rejection_report.json         ← V2 계약 위반
    ├── field_coverage_report.json    ← V3 필드 충족률
    ├── kpi_report.json               ← V4 KPI
    └── freeze_status.json            ← V6 GATE 1 봉인 상태
```

대시보드는 `src/lib/artifacts/`에서만 이 파일들을 읽는다(`DB-014`). 계산하지 않는다(`DB-012`) — 집계·판정·출처 분해는 전부 게시 시점(`src/measurement/publish.py`)에 끝난다.

---

## 2. CLI — 게시 명령

**정의** `src/measurement/publish.py:1564` `main()`

```bash
python3 -m src.measurement.publish [--source PATH] [--out PATH] [--config PATH] [--index-date YYYY-MM-DD] [--fail-on-quality]
```

| 인자 | 기본값 | 의미 |
|---|---|---|
| `--source` | `data/raw` | Event Sink 루트 |
| `--out` | `results` | 게시 대상 디렉터리 |
| `--config` | `config/economic_config.yaml` | 경제 규칙 config |
| `--index-date` | 마지막 파티션 날짜 | KPI 계산 기준일 `D` |
| `--fail-on-quality` | (플래그) | 품질 게이트가 `fail`이면 종료 코드 2로 중단 |

**의존성.** `PyYAML`(config 읽기)이 필요하다 — `requirements.txt`의 런타임 의존 2종(`pyarrow`·`PyYAML`) 중 하나. `jsonschema`는 **dev 전용**(결정 D-21)이라 게시 실행 자체에는 불필요하고, 런타임 자기검증(§6)만으로 게시 여부를 판정한다.

**종료 코드.** `MeasurementError`를 잡아 `error.exit_code`로 반환한다. `--fail-on-quality`가 있으면 품질 게이트 실패 시 별도로 2를 반환한다.

---

## 3. 공통 봉투 (envelope)

전 게시물 7종이 공유하는 최상위 구조. `docs/contracts/measurement-publish/v1/common.schema.json`이 정의하고, 각 산출물 스키마의 `required`에 다음 7개가 공통으로 들어간다 — `contract_version`·`artifact`·`run_id`·`generated_at`·`timezone`·`provenance`·`notices`.

| 필드 | 의미 |
|---|---|
| `contract_version` | `"measurement-publish/v1"` — 다르면 대시보드가 렌더링하지 않고 "계약 버전 불일치"를 표시 |
| `artifact` | 산출물 식별자 (예: `"kpi_report"`) |
| `run_id` | 같은 게시 실행의 산출물은 전부 동일. 예 `MR-20260911-124223-874b8283`. 읽는 쪽이 `index.json`과 대조해 다르면 값을 섞지 않는다 |
| `generated_at` | **KST(`+09:00`) 강제.** `Z` 표기는 정규식에서 거부된다 |
| `timezone` | `"Asia/Seoul"` |
| `provenance` | `schema_version`·`repo_commit`·`data_version`(C1: null)·`simulator_commit`(C1: null+`PRECONDITION_MISSING`)·`config_hashes`·`source_root`·`sink_manifest_sha256`·`generated_by`(게시 실행 명령의 런타임 기록)·`publisher_version` |
| `notices[]` | 명시 가정·한계. 화면이 접지 않고 표시한다 (예: `REFUND_NOT_ADJUSTED`·`SINK_EMPTY`·`INGESTION_GAP_UNDECIDABLE`) |

### 3.1 게시 절차 — 원자성

`src/measurement/publish.py`:

```
1. .staging/<run_id>/ 에 7종을 쓴다
2. 각 산출물을 자기 스키마로 자기검증한다 (§6) — 실패하면 여기서 멈춘다 (fail closed)
3. os.replace() 로 최종 경로에 하나씩 옮긴다
4. index.json 을 마지막에 쓴다
5. .staging/<run_id>/ 를 지운다
```

읽는 쪽(`dashboard/src/lib/artifacts/read.ts`)의 의무: `index.json`을 먼저 읽고, 각 산출물의 `run_id`가 인덱스와 같은지 확인한다. 다르면 "게시가 진행 중이거나 불일치"를 표시하고 값을 섞지 않는다.

---

## 4. ★ `metric_value` — 값 표현의 핵심 타입

**정의** `src/measurement/schema.py:636` `class MetricValue` (dataclass) · 계약 `common.schema.json#/$defs/metric_value`

```python
@dataclass(frozen=True)
class MetricValue:
    status: MetricStatus
    value: float | str | None = None
    unit: Unit | None = None
    basis: Basis | None = None
    reason_code: ReasonCode | None = None
    reason_detail: str | None = None
    blocked_by: tuple[BlockerRef, ...] = ()
    derived: bool = False
    derivation: str | None = None
    params_used: Mapping[str, object] | None = None
    ci95: tuple[float, float] | None = None
    limit_note: str | None = None
```

`value_formatted`는 이 dataclass에 **없다** — `src/measurement/contracts.py`가 직렬화 시점에 `(status, unit, value)`로부터 만들어 붙인다(§4.4). 호출자마다 포맷하면 한 곳만 빠뜨려도 화면이 `undefined`를 받는다는 것이 이유다(`docs/contracts/.../CHANGELOG.md` FIX-2).

### 4.1 `status` — 5종

**정의** `src/measurement/schema.py:471`

| 값 | 의미 |
|---|---|
| `ok` | 계산됨 — 값이 있고 관측된 사실이다 |
| `unconfirmed` | 계산됨 — 값은 있으나 사용한 파라미터가 미확정이다 (`params_used` 필수) |
| `unavailable` | 계산 불가 — 근거가 없어서 계산하려 했으나 못 했다 |
| `blocked` | 계산 불가 — 환경 제약으로 실행하지 못했다 (예: `pyarrow` 미설치) |
| `not_run` | 계산 불가 — **시도조차 하지 않았다** |

`unavailable`과 `not_run`의 구분이 이 프로젝트의 요점이다: 전자는 "계산하려 했으나 근거가 없다", 후자는 "계산을 시도하지 않았다". 둘을 합치면 관측하지 않은 것을 관측했다고 말하게 된다.

`ok`·`unconfirmed`를 **계산됨(computed)**, `unavailable`·`blocked`·`not_run`을 **미계산(uncomputed)**으로 묶는다(`schema.py` `_COMPUTED_STATUSES`/`_UNCOMPUTED_STATUSES`).

### 4.2 `reason_code` — 9종

**정의** `src/measurement/schema.py:486`

```
NO_SOURCE_EVENT · MISSING_FIELD · NO_COST_BASIS · NEEDS_TWO_STRATEGIES ·
NEEDS_MODEL_OUTPUT · PARAM_UNCONFIRMED · BLOCKED · NOT_RUN · PRECONDITION_MISSING
```

기획 문서(`kpi-definition-v1.md` §2.4)는 7종만 적었다(`NOT_RUN`·`PRECONDITION_MISSING`이 없다). **계약이 정본**이며 9종이다 — 이것은 design-vs-impl-gaps.md에 별도 기록한다. 대소문자 규칙: `status`는 소문자, `reason_code`는 대문자다(오타가 아니라 계약이 그렇게 정의한다).

### 4.3 `Unit` — 지표 단위

`common.schema.json#/$defs/unit`. `value_formatted` 규칙(구현자용, `contracts.py`):

| `unit` | 예 |
|---|---|
| `krw` | `38,400원` |
| `krw_per_customer` | `2,130원/인` |
| `count` | `1,204건` |
| `text` | 그대로 |
| `ratio` | `18.3%` — **이미 ×100 되어 온다. 화면이 다시 곱하지 않는다** |
| `percentage_point` | `+3.2%p` (부호 유지) |
| `days` | `42일` |
| `datetime` | `2026-09-18 13:58` (KST) |

### 4.4 `basis` — 계산의 기준

**정의** `src/measurement/schema.py` `class Basis`

| 필드 | 의미 |
|---|---|
| `population` | 모집단 (예: `"P_buyer(2026-09-18)"`) |
| `denominator_definition` | 분모의 정의 문장. 합계·건수 지표는 `"분모 없음 (합계)"` |
| `denominator` | 실제 분모 값. 합계·건수는 `null` |
| `observed_count` | 실제로 검사·집계한 레코드 수 |
| `window` | `{direction, days}` — `direction`은 `retrospective`/`prospective`/`point_in_time`/`none` |
| `excluded_count` · `excluded_reason` | 분모 제외 인원과 사유 (조용히 제외하지 않는다) |
| `source_event_types` | 근거 이벤트 종류 |

**스키마 강제 (핵심 불변식 ②):**
- `status`가 `ok`·`unconfirmed` → **`basis` 필수**
- `status`가 `unavailable`·`blocked`·`not_run` → **`basis` 금지**
- `unit: ratio` + 계산됨 → `basis.denominator` 필수
- `basis.denominator == 0` → `status`가 `ok`일 수 **없다**

"측정된 0"과 "값 없음"을 가르는 것은 `basis`의 존재 여부다.

### 4.5 `blocked_by` — 결손 → 영향 사슬

`{kind, ref, reason_code}` 튜플. `kind` 9종: `field`·`schema_gap`·`event_type`·`metric`·`table`·`model_output`·`strategy`·`parameter`·`dependency`. 화면이 사슬을 추론하지 않도록 게시 시점에 넣는다(`DB-012`).

### 4.6 `derived` / `derivation`

`derived: true`면 `derivation`(유도 계산식 문장)이 **필수**다 — 유도값이 저장된 사실처럼 보이면 안 된다(`MetricValue.__post_init__`이 생성 시점에 강제). C1에서 `derived: true`로 나가는 지표: `shipping_subsidy`(D-3), `coupon_cost`(D-16), `derived_state_count` 3종(inactive/at_risk/churn).

### 4.7 `by_source` — 출처 분해 (`MEA-002`)

```jsonc
{ "by_source": { "commerce": <metric_value>, "simulator": <metric_value> } }
```

계층 1·2(customer_kpi·business_kpi) KPI에는 **`combined`(합산) 키를 둘 수 없다** — 스키마가 거부한다. 출처를 섞으면 처치·통제 배정이 성립하지 않는다는 이유다. 두 키(`commerce`/`simulator`)는 한쪽이 0건이어도 **항상 존재**한다. `layer: experiment`는 예외로 `by_source` 없이 단일 `metric_value`다(`MEA-002` — 실험 판정에는 시뮬레이터 생성분만).

---

## 5. 런타임 자기검증 — `verify_core_invariants()`

**정의** `src/measurement/contracts.py:356`

`jsonschema`가 dev 전용(§2)이므로 **런타임에 실제로 도는 검증은 이 함수뿐**이다. 전체 draft-2020-12 스키마를 재구현하지 않고, "화면에서 `?? 0`을 부르게 만드는 위반"만 고른다 — 정확히 7개:

1. 계산 불가에 `value`가 `null`이 아니다 → 0 채우기
2. 계산 불가에 `basis`가 있다 → 근거 없는 값이 근거 있게 읽힌다
3. 계산 불가에 `value_formatted`가 있다 → 없는 값에 표시가 붙는다
4. 계산됨에 `value_formatted`가 없다 → 화면이 `undefined`를 받는다
5. 계산됨에 `basis`·`unit`이 없다 → "측정된 0"과 구분 불가
6. `basis.denominator == 0`인데 `ok` → 0/0을 0으로 표시
7. `derived`인데 `derivation`이 없다 → 유도값이 사실처럼 보인다

위반 시 `ContractViolation`을 던지고(fail closed), `publish.py`의 `dump()`가 이 함수를 통과하지 못한 산출물은 **문자열조차 만들지 않는다**. 나머지(정규식 방언·`$ref` 해석·`additionalProperties`·enum)는 `tests/test_publish_contract.py`·`tests/test_publish_pipeline.py`가 `jsonschema`로 검증하며, `jsonschema` 미설치 시 skip된다(BLOCKED 사유 문자열과 함께).

> **주의.** 런타임 7불변식 통과는 "계약을 완전히 준수한다"는 뜻이 아니다 — 1차 구현이 7불변식은 통과했지만 전체 스키마 검증에서 233건 위반이 나온 사례가 있다(`backend.md` §11). 두 층은 서로를 대체하지 않는다.

---

## 6. 산출물 7종

`index.json`의 `views` 맵이 화면↔산출물↔라우트를 고정한다. 아래는 각 산출물의 필수 최상위 필드(공통 7개 제외)와 핵심 내용.

### 6.1 `index.json`

**경로** `results/measurement/index.json` · **스키마** `index.schema.json`
**required(추가)** `publish_result` · `artifacts` · `views` · `verdict`

| 필드 | 내용 |
|---|---|
| `publish_result` | `ok`/`partial`/`failed` |
| `artifacts[]` | `{path, sha256, status}` — `path`는 정규식 `^(results\|data/processed)/`로 강제(`DB-014` 위반 경로를 인덱스에 적을 수 없다) |
| `views` | V1~V6 각각을 `{artifact, route}`로 매핑. `/kpi`가 `V4`의 정본 라우트다(`/metrics`가 아니다 — design-vs-impl-gaps.md 참조) |
| `static_views[]` | 게시물 없는 정적 화면(`/triggers`) — 1:1 불변식의 명시적 예외 |
| `verdict` | `{level, headline_code, headline_detail, counts}` — `level`은 `ok < attention < violation`. `headline_code` 8종: `CONTRACT_VIOLATION`·`FREEZE_MISMATCH`·`QUALITY_VIOLATION`·`REJECTED_EVENTS`·`SINK_EMPTY`·`CHECKS_NOT_RUN`·`METRICS_UNAVAILABLE`·`ALL_CLEAR`(우선순위 이 순서, `publish.choose_headline_code()`가 단일 산출 지점) |

### 6.2 `ingestion_report.json` (V1)

**required(추가)** `totals` · `by_event_type` · `partitions` · `sources`

- `by_event_type` — **16종 전부**가 키로 존재(`minProperties: 16`)
- `partitions[]` — 일자별 배열. 이벤트 0건 날짜도 `present:false`로 존재
- `sources.{commerce,simulator}.link_state` — `never_connected`/`connected` 2값(게시물이 판정). `staleness`는 `metric_value`로(C1에서는 임계값 미확정이라 `not_run`+`PARAM_UNCONFIRMED`)
- `totals.ingestion_gap_attribution` — `not_run`+`PRECONDITION_MISSING`. "수집 중단"과 "활동 없음"은 heartbeat 레코드가 없어 C1에서 구분 불가(§7.2 참조)

### 6.3 `rejection_report.json` (V2)

**required(추가)** `totals` · `by_reason` · `samples`

`samples[]`는 `offending_values`의 **키를 DATA-003 22컬럼으로 제한**한다(`propertyNames.enum`) — 스키마 밖 필드(Hidden Trait 등)의 값은 담을 자리가 구조적으로 없다. 필드 **이름**은 항상 담긴다(`offending_fields`).

### 6.4 `field_coverage_report.json` (V3)

**required(추가)** `fields` · `missing_fields` · `schema_gaps`

- `fields` — **정확히 22개**(`minProperties`/`maxProperties: 22`)
- `schema_gaps[]` — 계산식이 요구하는데 **컬럼 자체가 없는 것** — 실측(`src/measurement/publish.py:577` `_SCHEMA_GAPS`) **5건**: `unit_cost`·`discount`·`shipping_fee`·`signup_date`·`refund`. 각 항목이 `blocks_metrics`(원인→영향 사슬)를 담는다. **`signup_date`는 `api-contracts.md` §5.3.1 작성 시점(W2, 4건)에는 없던 항목으로, W5 구현 중 `cohort_retention_rate`(코호트 잔존율)가 `customers` 테이블 부재로 계산 불가임이 드러나며 추가됐다 — `kpi.py:183`가 `blocks_metrics: ["cohort_retention_rate"]`로 연결한다. 상세는 [`design-vs-impl-gaps.md` §5](./design-vs-impl-gaps.md#5-cohort_retention_rate-분류-불일치) 참조**

### 6.5 `kpi_report.json` (V4)

**required(추가)** `index_date` · `definition_version` · `summary` · `metrics`

- `metrics[]`의 각 항목: `population`·`window`·`denominator_definition`·`formula`·`definition_ref`·`value`(계산과 정의를 같은 자리에)
- `summary` — `kpi-definition-v1.md` §8 표(계층별 계산가능/조건부/불가)를 그대로 옮긴 집계. `total`은 **지표 값 개수**다(계층 1·2는 출처당 값이 하나씩이라 24종×2출처=48 — 지표 *행* 개수가 아니다)
- `layer`가 `experiment`인 항목은 `by_source` 없는 단일 값이다(`MEA-002`)
- `metrics[].role` — `primary`/`guardrail`/`secondary`/`none`. GATE 2에서 Lock 예정(`KPI_DEFINITION_v1` `PARTIAL`)이므로 C1 게시물의 role은 배정만 있고 봉인되지 않았다
- `metrics[].blocks` — 이 지표가 무너질 때 함께 무너지는 하위 지표(`blocked_by`의 역방향)

### 6.6 `data_quality_report.json` (V5)

**경로** `results/data_quality_report.json` (정본 경로 고정, `results/measurement/` 예외) · **required(추가)** `gate_result` · `checks` · `spec_coverage`

- `checks[].status` — **5값**: `pass`/`fail`/**`vacuous`**/`not_run`/`blocked`. `examined_rows == 0`이면 `pass`일 수 없다(`vacuous`로 분리) — "공허한 통과"를 스키마로 막는다
- `gate_result` — **3값**: `pass`/`fail`/**`incomplete`**. 실행한 검사가 전부 통과해도 실행 못한 검사가 있으면 `pass`가 아니다
- `spec_coverage` — `data_spec` §9의 11개 정본 항목 전부를 `spec_items[]`로 게시. `unmapped_spec_items`가 비어 있지 않으면 "정본에 있는데 아무 검사도 덮지 않는 항목이 있다"는 뜻

### 6.7 `freeze_status.json` (V6)

**required(추가)** `gate` · `overall` · `items` · `unlocked_items`

- `items[]` — PRD §22 Lock **9종 전부**. 각 항목에 `scope_note`(부분 Lock의 범위 문장) 필수
- `verification` — `match`/`mismatch`/`missing`/`not_run`. 대조를 실행하지 않았으면 `not_run`이고 통과가 아니다
- `overall`의 C1 도달 가능 최대치는 `partial`이다. `sealed`는 `EXPERIMENT_ENVIRONMENT_v1` 선언과 함께만 쓴다
- **현재 상태 (2026-09-14 실측, `config/gate1_lock.yaml`)**: `declaration: PARTIAL_FREEZE` · `locked_by: Danto7632` · `locked_at: 2026-09-11T23:53:00.276+09:00` · `simulator_commit: null` · Lock 9종 중 `OUT_OF_SCOPE` 5 · `PENDING` 2(`EVENT_SCHEMA_v1`·`ECONOMIC_RULE_v1`) · `PARTIAL` 2(`CHURN_DEFINITION_v1`·`KPI_DEFINITION_v1`) · **`LOCKED`(완전 봉인) 0종**

---

## 7. GATE 1 선행 조건 — `GATE1_PRECONDITIONS` (G-1~G-16)

**정의** `src/measurement/freeze.py` `_GATE1_ROWS`/`GATE1_PRECONDITIONS`(§300~361). 정확히 16개(모듈 로드 시 `assert`로 강제).

| ID | 조건 | 현재 |
|---|---|---|
| G-1 | `category` 5종 Enum + 검증 | ✅ |
| G-2 | `page_type` 8종 동일 | ✅ |
| G-3 | `validate_event()`가 `check_identifier()` 호출 | ✅ |
| G-4 | 카테고리 어휘 정본 확정(영문) | ✅ |
| G-5 | 타임존 정책 확정·강제 | ✅ |
| G-6 | 동일 root 재기록 시 파티션 보존 | ✅ |
| G-7 | `strict=False`가 예외를 던지지 않음 | ✅ |
| G-8 | 파생 상태 기록 경로 결정(게시 시점 계산) | ✅ |
| G-9 | `shipping_subsidy` 처리 방침(규칙 유도) | ✅ |
| G-10 | 환불/취소 이벤트 포함 여부 | ✅ (결정 D-2 — "미반영을 가정으로 수용", "반영됐다"가 아님) |
| G-11 | KPI 계산 계약 확정 | ✅ (`METRIC_SPECS` 46종) |
| G-12 | 경제 규칙 확정 | ✅ (AI 투자비는 `is_estimate: true`) |
| G-13 | `docs/event_schema.md` ↔ 코드 일치 | ✅ |
| G-14 | 전건 테스트 통과 | ✅ |
| G-15 | Lock 절차(SHA·커밋 기록) | ✅ |
| G-16 | `discount` 유도 규칙 확정 | ✅ |

16종 전부 충족 → `freeze.verify().can_lock == True`. **실제 Lock은 실행됐다**(§6.7). C1은 이후에도 **GATE 1 전체 통과를 선언하지 않는다** — 부분 봉인만 한다.

---

## 8. 계약 변경 이력 (요약)

**정본** `docs/contracts/measurement-publish/v1/CHANGELOG.md` (W5-A, M-06 T1)

| # | 변경 | 파일 | 요지 |
|---|---|---|---|
| FIX-1 | `headline_code` 7→8종 | `index.schema.json` | `REJECTED_EVENTS` 추가 + 우선순위 8종 확정 + `counts.rejected_events > 0` → `ALL_CLEAR` 금지 가드 |
| FIX-2 | `metric_value.value_formatted` 추가 | `common.schema.json` | `ok`/`unconfirmed` 필수, 계산 불가 금지. **회귀 위험**: 계산 불가 금지 절을 `not:{required:[...]}` 배열 추가로 구현하면 `basis` 금지까지 무력화된다 — `anyOf` 형태로 교체해야 한다 |
| FIX-3 | `metric_value.limit_note` 추가 | `common.schema.json` | 선택 필드. 지표별 정밀도 한계(예: `campaign_response_count`의 쿠폰 비종속 캠페인 과소계상) |
| FIX-4 | `checks[].status`↔`reason_code` | `data_quality_report.schema.json` | `blocked`→`BLOCKED`, `not_run`→`NOT_RUN`/`PRECONDITION_MISSING` 강제 + **`vacuous`→`reason_code` 금지 절 교체**(추가가 아니다 — 추가하면 `vacuous`가 만족 불가능해진다) |

---

## 9. 읽는 쪽(대시보드) 제약 요약

| 제약 | 근거 |
|---|---|
| `results/`와 `data/processed/`만 읽는다. `data/raw/`·`data/hidden/`·`data/ground_truth/` 금지 | `DB-014` |
| 계산하지 않는다(합계·비율·분류·정렬 기준 생성 금지). 표시 순서 정렬·필터는 허용 | `DB-012` |
| `by_source`를 재분류하지 않는다 | `MEA-002` |
| `status !== "ok"`인 값을 숫자로 렌더링하지 않는다 | PRD §10.1 |
| `not_run`을 `pass`로 표시하지 않는다 | AGENTS.md |
| `contract_version` 불일치 시 렌더링하지 않는다 | 이 계약 |
| `index.json`이 없으면 게시 방법을 안내한다(실행 가능한 명령이 있을 때만 명령 문자열을 보여준다) | `DB-013` |
| `src/**`를 import하지 않는다 | `DB-014` |

구현 위치: `dashboard/src/lib/artifacts/{paths,read,types}.ts` — 파일 읽기는 이 디렉터리 안에서만 일어난다(`resolveArtifactPath()`가 경로 이탈을 예외로 만든다).
