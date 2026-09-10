# 게시물 계약 — 측정 산출물 (T2.7) ★

**작성** James (Role 4 · Architect) · 2026-09-11 · 사이클 C1
**개정 2** (2026-09-11) — 정합 1라운드. 이름 통일(`blocks_metrics`·`link_state`) · **V-12 공허한 통과 차단** · 구분 불가를 명시적 값으로 · `static_views`. 변경 요약은 §11.
**개정 1** (2026-09-11) — Jonnathan 의 화면 요구 17건 + 리드 판정 3건 반영.
**상태** 확정안. Jonnathan(T2.12~T2.14) · Andrew(W5-C) · Phillip(W5-A) 의 **전제**다.
**기계가독 정본** `schemas/*.schema.json` (JSON Schema draft 2020-12) — **이 문서는 그 스키마의 해설이다. 충돌하면 스키마가 정본이다.**

> ## ⚠ 이 프로젝트에는 HTTP API 가 없다
> 대시보드는 **파일을 읽는다** (SRS `DB-013` — *"별도 API 서버를 두지 않는다"*).
> 그래서 이 문서의 "계약"은 REST 엔드포인트가 아니라 **게시물(published artifact) 의 경로·형식·갱신 시점·읽는 쪽의 제약**이다.
> 없는 REST API 를 지어내지 않았다.

---

# 0. 한 장 요약

| 축 | 확정 |
|---|---|
| **누가 쓰나** | `src/measurement/publish.py` (신설) — 측정 계층 |
| **어디에** | `results/measurement/*.json` + `results/data_quality_report.json` |
| **누가 읽나** | `dashboard/` 만. `data/raw/` 는 읽지 않는다 (`DB-014`) |
| **형식** | UTF-8 JSON. 전 게시물이 **같은 봉투(envelope)** 를 쓴다 |
| **갱신** | 게시 명령을 사람이 실행할 때. 자동 감시·스트리밍 없음 (`DB-011` 수동 새로고침) |
| **원자성** | staging → `os.replace` → `index.json` 을 **마지막에** 쓴다. 읽는 쪽은 `run_id` 일치를 확인한다 |
| **계산 주체** | 출처 분류·계산 불가 판정·집계를 **게시 시점에 끝낸다.** 대시보드는 계산하지 않는다 (`DB-012`) |
| **핵심 불변식 ①** | **`status` 가 `unavailable`/`blocked`/`not_run` 이면 `value` 는 반드시 `null`.** 0 을 넣으면 스키마 검증이 실패한다 |
| **핵심 불변식 ②** | **계산된 값에는 `basis`(기준)가 반드시 있고, 계산 불가에는 있을 수 없다.** 기준의 유무가 "측정된 0"과 "값 없음"을 가른다 |
| **핵심 불변식 ③** | **검사 대상이 0행이면 `pass` 일 수 없다.** "검사했지만 아무것도 검사하지 않았다"를 `vacuous` 로 분리한다 |
| **핵심 불변식 ④** | **판정할 수 없는 것은 값이 아니라 사유로 준다.** 화면이 추측하지 않는다 |

**검증 실행 결과 (2026-09-11, 이 문서 작성 중 실행):**

```
tools/validate_examples.py         예시 14건 · 위반 0건   (빈 Sink 7 + 커머스 연결 7)
                                   examples/empty-sink/          — 오늘의 실제 상태
                                   examples/commerce-connected/  — 전 시각 상태가 한 벌에
tools/check_zero_fill_rejected.py  위반 시도 15건 중 거부 15건 · 통과 0건
tools/check_ownership.py           PASS (표준 라이브러리 · 저장소 환경에서 실행)
```

> 앞의 두 실행은 **스크래치패드 가상환경의 `jsonschema` 4.26.0** 으로 했다. 저장소 환경에는 `jsonschema` 가 없고 설치하지 않았다.
> W5 에서 저장소 테스트로 옮길 때의 조건은 `dependency-plan.md` §4 에 있다. **저장소에서 실행하지 않은 것을 실행했다고 적지 않는다.**

---

# 1. 왜 게시가 필요한가 — 3줄

1. 관측 화면군의 원천은 Event Sink 의 `manifest.json` 이고, 그것은 Sink root(= `data/raw/`) 아래에 있다 (`sink.py:220-245`).
2. 그런데 `DB-014` 의 대시보드 읽기 허용 목록은 **`results/` 와 `data/processed/` 뿐이고 `data/raw/` 가 없다.**
3. → **측정 계층이 `results/` 에 게시하고 대시보드는 그것만 읽는다.** `DB-013`·`DB-014` 를 한 글자도 고치지 않고 성립한다.

**격리 위반이 아니라는 실측 근거** — `tests/test_isolation.py:31-36`:

```python
FORBIDDEN_PATHS = {
    "src.measurement": ("data/hidden", "data/ground_truth"),   # results/ 가 없다
    "src.simulator":   ("results/",),                          # simulator 만 금지
}
```

그리고 정본이 이미 같은 방향을 규정한다 — `docs/data_spec.html` §9:
> *"모든 검사는 `src/measurement/validate.py` 에서 실행하고 **`results/data_quality_report.json`** 에 결과를 남긴다."*

**새 경로를 발명하지 않았다.** 기존 규칙의 확장 적용이다.

> ### 정본 긴장 T-1 — 기록해 둔다
> `data_spec` §17.4 의 경로 표는 `results/` 접근 가능 주체를 *"decision · orchestration"* 으로 적고 **measurement 를 넣지 않았다.**
> 그러나 같은 문서 §9 는 measurement 가 그곳에 쓰도록 규정하고, **강제 수단인 `tests/test_isolation.py` 는 measurement 의 `results/` 접근을 막지 않는다.**
> → **강제되는 규칙(테스트)과 명시 규정(§9)이 일치하므로 게시는 성립한다.** §17.4 표는 읽기 주체를 열거한 것으로 읽는다.
> `Plan/` 수정은 권한 밖이므로 고치지 않고 여기에 남긴다. **`docs/measurement_contract.md`(M-3)에도 같은 문장을 남긴다.**

---

# 2. 파일 배치

```text
results/
├── data_quality_report.json          ← V5 · 정본이 지정한 경로 (data_spec §9). 발명 금지 · 이동 금지
└── measurement/                      ← 측정 계층 게시 영역 (신설)
    ├── index.json                    ← 게시 인덱스. 대시보드가 가장 먼저 읽고, 게시는 마지막에 쓴다
    ├── ingestion_report.json         ← V1 수집 현황
    ├── rejection_report.json         ← V2 계약 위반
    ├── field_coverage_report.json    ← V3 필드 충족률
    ├── kpi_report.json               ← V4 KPI
    ├── freeze_status.json            ← V6 봉인 상태
    └── .staging/<run_id>/            ← 게시 중 임시. 완료 후 삭제
```

**왜 `results/measurement/` 로 한 겹 내렸는가 (ADR-0002)**
이후 사이클에서 `src/decision/` 이 `results/churn_predictions.csv` 등 8종을 같은 디렉터리에 쓴다 (`data_spec` §7.5). 한 디렉터리에 섞이면 **누가 쓴 파일인지가 파일명 관례에만 의존**하게 되고, 소유 경계가 파일시스템에서 사라진다.
`data_quality_report.json` 하나만 루트에 두는 것은 **정본이 그 경로를 명시했기 때문**이며, 일관성보다 정본이 우선한다. `index.json` 이 이 파일을 경로로 참조하므로 두 진실이 생기지 않는다.

**`.gitignore` — 결정 필요 (D-17)**
현재 `.gitignore` 는 `data/` 와 `models/` 를 제외하지만 **`results/` 는 제외하지 않는다.** 게시물은 생성물이므로 AGENTS.md *"비밀값·생성물을 커밋하지 않는다"* 에 걸린다.
→ **`results/` 를 `.gitignore` 에 추가할 것을 권고**하되, 그러면 대시보드 스크린샷 증거를 저장소에 남길 수 없다. 대안은 `results/` 제외 + `.agent-team/` 에 증거 사본. **사용자 결정 항목.**

---

# 3. 공통 봉투 (envelope)

전 게시물이 같은 머리를 갖는다. **대시보드는 파서를 하나만 갖는다.**

```jsonc
{
  "contract_version": "measurement-publish/v1",   // 다르면 렌더링하지 않고 '계약 버전 불일치'를 표시
  "artifact": "ingestion_report",
  "run_id": "MR-20260911-090000-0a1b2c3d",        // 같은 게시 실행의 산출물은 전부 동일
  "generated_at": "2026-09-11T09:00:00.000+09:00", // ★ KST 강제. 'Z' 표기는 패턴에서 실패한다
  "timezone": "Asia/Seoul",
  "provenance": { ... },                           // DB-013 — 무엇을 보여주고 있는지
  "notices": [ ... ],                              // 명시 가정·한계. 화면에 표시한다
  ... 산출물별 본문 ...
}
```

## 3.1 `generated_at` 이 KST 를 정규식으로 강제하는 이유

`schema.py:29-30` 은 *"모든 timestamp 는 KST 단일 타임존, UTC 혼재 불허"* 라고 선언하지만, **`sink.py:229` 의 `manifest.created_at` 은 UTC 로 쓴다** (W1 보완점 W-8). 선언과 코드가 어긋난 상태다.
게시 계층은 이 어긋남을 **계약으로 막는다** — `+09:00` 이 아닌 문자열은 스키마 검증에서 실패하고, 검증에 실패한 산출물은 게시되지 않는다(§6.3 fail-closed).

## 3.2 `provenance` — `DB-013` 대응

| 필드 | 값 | C1 |
|---|---|---|
| `schema_version` | `schema.py` `SCHEMA_VERSION` | ✅ |
| `repo_commit` | 게시 시점 `git rev-parse HEAD` | ✅ |
| `data_version` | `data/data_version.yaml` 의 값 | ❌ `null` + `null_reason` |
| `simulator_commit` | `ISO-006`·`FREEZE-003` 대조용 | ❌ `null` + `null_reason` |
| `config_hashes` | 읽은 config 파일의 SHA-256 (`data_spec` §15.2) | 부분 |
| `source_root` | Sink root. 예 `data/raw` | ✅ |
| `sink_manifest_sha256` | 원천 manifest 의 해시 | ✅ |
| **`generated_by`** | **이 게시물을 만든 실행 명령.** 설계 시점에 지어내지 않고 **생성기가 런타임에 자기 실행을 기록**한다 | ✅ (값은 W5) |
| `publisher_version` | 게시 모듈 버전·커밋 | ✅ |

> ### `generated_by` — 리드 판정 반영
> `DB-013` 이 요구하는 것은 **게시물을 어떻게 만들었는지 보여주는 것**이고, 그 값은 아키텍처가 지어낼 것이 아니라 **생성기가 자기 실행을 기록**하면 된다.
> 계약은 필드를 필수로 두고, **값을 채우는 주체는 W5 다.** 이것은 `BLOCKED` 가 아니라 **채우는 주체가 다른 것**이다.
> 빈 상태(파일이 아예 없을 때)의 안내 문구는 §7 R-7 참조 — **Andrew 착수 시점(W5-C)에는 이미 `publish.py` 가 존재하므로**(build-plan Phase 2'' → W5-C) 실재하는 명령을 쓸 수 있다.

> **`simulator_commit` 을 빈 문자열이나 `"unknown"` 으로 채우지 않는다.** `null` 로 두고 `null_reason` 에 `PRECONDITION_MISSING` 을 적는다.
> **`measurement` 는 `src/simulator/` 를 읽어서 이 값을 얻지 않는다** — 실행 메타로 주입받는다. 값을 나르는 것은 의존이 아니지만, 읽으러 가는 것은 의존이다(창구 중립성).

## 3.3 `notices` — 가정을 산출물에 붙여 나른다

가정은 시간이 지나면 사실로 읽힌다. 그래서 문서가 아니라 **산출물에** 붙인다.

| code | level | C1 에서 언제 |
|---|---|---|
| `SINK_EMPTY` | limitation | 이벤트 0건일 때 |
| `REFUND_NOT_ADJUSTED` | assumption | 항상 (`economic-rule-v1.md` §6 가정 `A-REFUND`) |
| `CHURN_THRESHOLD_UNCONFIRMED` | assumption | 이탈 관련 지표가 있을 때 |
| `GATE1_NOT_PASSED` | limitation | `freeze_status` 에 항상 |
| `DASHBOARD_NOT_ISOLATION_CHECKED` | limitation | 격리 검사 확장을 하지 않기로 결정한 경우 (§7 W-8) |

---

# 4. ★ 값 표현 — `metric_value`

이 프로젝트의 USP-1 이 사는 자리다.

```jsonc
// 계산됨 — 값과 기준이 있다
{ "status": "ok", "value": 41283400, "unit": "krw",
  "basis": { "population": "purchase 이벤트", "denominator_definition": "분모 없음 (합계)",
             "denominator": null, "observed_count": 1204,
             "window": { "direction": "retrospective", "days": 42 } } }

// 미확정 — 값을 내되 사용한 파라미터를 밝힌다
{ "status": "unconfirmed", "value": 0.1834, "unit": "ratio",
  "basis": { "population": "P_buyer(2026-09-18)", "denominator_definition": "구매 이력 보유 고객 수",
             "denominator": 894, "observed_count": 894,
             "window": { "direction": "point_in_time", "days": null } },
  "reason_code": "PARAM_UNCONFIRMED",
  "reason_detail": "이탈 임계값이 GATE 1 에서 확정되지 않았다.",
  "params_used": { "no_purchase_days": 42, "at_risk_days": 28 } }

// 계산 불가 — value 는 null 이고 basis 를 가질 수 없다
{ "status": "unavailable", "value": null, "unit": "krw",
  "reason_code": "NO_COST_BASIS",
  "reason_detail": "주문 1,204건 중 1,204건에 unit_cost 없음. 원가율을 곱해 추정하지 않는다.",
  "blocked_by": [ { "kind": "schema_gap", "ref": "unit_cost", "reason_code": "NO_COST_BASIS" } ] }

{ "status": "blocked",  "value": null, "reason_code": "BLOCKED", "reason_detail": "pyarrow 미설치" }
{ "status": "not_run",  "value": null, "reason_code": "NOT_RUN", "reason_detail": "검사를 실행하지 않았다." }
```

## 4.1 ★ `basis` — 기준. 두 번째 핵심 불변식

**"측정된 0"과 "값 없음"을 가르는 것은 글리프가 아니라 기준의 유무다.**

| 필드 | 의미 |
|---|---|
| `population` | 무엇을 셌는가 / 모집단. R-4 — *"고객"이라고만 쓰지 않는다* |
| `denominator_definition` | 분모가 무엇인지의 **문장**. 합계·건수 지표는 *"분모 없음 (합계)"* |
| `denominator` | 분모의 실제 값. 합계·건수는 `null` |
| `observed_count` | **실제로 검사·집계한 레코드 수.** *"세어 봤고 0이었다"* 의 증거 |
| `window` | `direction`(retrospective/prospective/point_in_time/none) · `days`. R-2 |
| `excluded_count` · `excluded_reason` | 분모에서 제외한 대상 수와 사유. R-6 — **제외를 조용히 하지 않는다** |
| `source_event_types` | 근거 이벤트 종류 |

**스키마 강제:**
- `status` 가 `ok`·`unconfirmed` → **`basis` 필수**
- `status` 가 `unavailable`·`blocked`·`not_run` → **`basis` 금지** (`not: {required: ["basis"]}`)
- `unit: ratio` + 계산됨 → `basis.denominator` 필수
- `basis.denominator == 0` → `status` 가 `ok` 일 수 **없다**

> **결과:** 화면은 `basis` 의 존재 여부만 보고 두 상태를 판별할 수 있고, **기준 없는 값이 오면 계약 위반으로 렌더링**할 수 있다. 지표를 계산하는 것이 아니라 필수 필드의 존재만 보므로 `DB-012` 위반이 아니다.

## 4.2 ★ `blocked_by` — 결손 → 영향의 사슬

**화면이 사슬을 추론하면 `DB-012` 위반이다. 게시 시점에 넣는다.**

```jsonc
"blocked_by": [
  { "kind": "metric",     "ref": "cogs",          "reason_code": "NO_COST_BASIS" },
  { "kind": "schema_gap", "ref": "discount",      "reason_code": "MISSING_FIELD" },
  { "kind": "event_type", "ref": "coupon_use",    "reason_code": "NO_SOURCE_EVENT" },
  { "kind": "parameter",  "ref": "C_rule",        "reason_code": "PARAM_UNCONFIRMED" }
]
```

`kind` 9종 — `field` · `schema_gap` · `event_type` · `metric` · `table` · `model_output` · `strategy` · `parameter` · `dependency`.

**양방향으로 게시한다.** 화면이 어느 쪽에서 들어와도 사슬을 따라갈 수 있어야 한다.

| 방향 | 어디에 | 예 |
|---|---|---|
| 원인 → 영향 | `field_coverage_report.fields[f].blocks_metrics`<br>`field_coverage_report.schema_gaps[].blocks_metrics` | `unit_cost` → `cogs` · `contribution_profit` · `incremental_contribution_profit` |
| 영향 → 원인 | `kpi_report.metrics[].value.blocked_by` | `contribution_profit` ← `cogs` · `discount` · `shipping_fee` |
| 영향 → 하위 | `kpi_report.metrics[].blocks` | `cogs` → `contribution_profit` |

## 4.3 스키마가 강제하는 것 (실행으로 확인함 — 11/11 거부)

| 규칙 | 근거 |
|---|---|
| `unavailable`·`blocked`·`not_run` → `value` 는 **반드시 `null`** | `MEA-003` · charter 절대제약 6 |
| **계산된 값에 `basis` 필수** | Jonnathan T2.13 판별자 |
| **계산 불가에 `basis` 금지** | 동일 — 기준의 유무가 판별자이므로 |
| 계산 불가에 `reason_code` + `reason_detail` **필수** | R-9 |
| `unconfirmed` → `params_used` 필수 | R-10 |
| `unit: ratio` → `basis.denominator` 필수 | R-6 |
| `basis.denominator == 0` → `ok` 일 수 **없다** | 0/0 을 0 으로 표시하는 경로 차단 |
| `derived: true` → `derivation` 필수 | `kpi-definition-v1.md` §5.4 |
| KPI 계층에서 `combined` 키 **금지** | R-7 |
| 거부 샘플의 값은 **22컬럼만** | §5.2 보안 경계 |
| `provenance.generated_by` **필수** | `DB-013` |
| `generated_at` 이 **KST** | `schema.py:29-30` |

## 4.4 사유 코드 — 7종 확정 + 2종 제안

`kpi-definition-v1.md` §2.4 의 7종:
`NO_SOURCE_EVENT` · `MISSING_FIELD` · `NO_COST_BASIS` · `NEEDS_TWO_STRATEGIES` · `NEEDS_MODEL_OUTPUT` · `PARAM_UNCONFIRMED` · `BLOCKED`

**추가 제안 2종 (결정 D-15 — Joshua 확인 필요):**

| 코드 | 왜 필요한가 | 대체 불가 이유 |
|---|---|---|
| `NOT_RUN` | *"검사를 실행하지 않았다"* — `usp.md` §1.8 이 사유로 열거했으나 코드가 없다 | `BLOCKED`(환경 제약으로 **못 했다**)와 다르다. **실행 안 한 것을 못 한 것으로 적으면 책임이 환경으로 넘어간다** |
| `PRECONDITION_MISSING` | *"선행 산출물이 없어 검사 대상 자체가 없다"* | `MISSING_FIELD`(필드가 결손)와 다르다. 여기서는 **테이블·모집단 자체가 없다** |

> **Jonnathan 이 같은 것을 다른 말로 요구했다** — *"`BLOCKED`(선언된 실행 불가)와 미실행(아무도 선언하지 않은 공백)은 다르고, 후자를 가장 강하게 표시한다. 알지 못함이 결손보다 나쁘다."*
> 계약의 5상태가 그 요구를 그대로 담는다.

## 4.5 ★ 0 을 언제 써도 되는가

**관측 결과로서의 0 은 정직한 값이다.** 이것을 계산 불가로 적으면 그것도 거짓말이다.

| 상황 | 올바른 표현 | 틀린 표현 |
|---|---|---|
| 이벤트가 0건 들어왔다 | `ok` + `0` + `basis.observed_count: 0` | `unavailable` — 우리는 0건임을 **안다** |
| `coupon_use` 0건이라 쿠폰 사용 건수가 0 | `ok` + `0` + `basis.population: "coupon_use 이벤트"` | `unavailable` |
| 거부율 = 0건 / 0건 | `unavailable` (분모가 없다) | `{"value": 0}` |
| 매출 (`purchase` 0건) | `unavailable · NO_SOURCE_EVENT` | `{"value": 0}` — 매출 0원과 근거 없음은 다르다 |
| COGS (원가 근거 없음) | `unavailable · NO_COST_BASIS` | `0` 또는 `revenue × 0.74` |

**가르는 기준:** *"세어 보니 0"* 은 `ok`(기준이 있다). *"셀 근거가 없다"* 는 `unavailable`(기준이 없다).

> **`examples/commerce-connected/kpi_report.json` 이 이 구분을 한 파일에 담고 있다** — `coupon_usage_count` 는 `ok` + 0(기준: `coupon_use` 이벤트 0건 중), `coupon_cost` 는 `unavailable`(`discount` 필드 부재 + 이벤트 0건). 화면에서 둘이 달라야 한다.

## 4.6 출처 분해 — `MEA-002`

```jsonc
{ "by_source": { "commerce": <metric_value>, "simulator": <metric_value> },
  "combined":  <metric_value>          // 계층 0 에서만 허용
}
```

- **대시보드는 재분류하지 않는다.** `sink.event_source()` 결과를 게시 시점에 집계한다 → W1 **W-7 해소**
- **계층 1·2 KPI 에는 `combined` 키를 둘 수 없다** (R-7). 스키마가 거부한다
  → **"전체" 숫자를 크게 보여주는 히어로 지표를 KPI 화면에 만들 수 없다.** 정보구조 설계 전에 알아야 하는 제약이다
- `commerce`/`simulator` 두 키는 **항상 존재한다.** 한쪽이 0건이어도 키를 빼지 않는다 — 빼면 화면에서 그 출처가 사라진다

# 5. 산출물 6종 + 인덱스

**화면 ↔ 게시물이 1:1이다.** 이 대응은 `index.json` 의 `views` 맵에 **기계가독으로** 들어간다 — 검사할 수 있다.

| 화면 | 답하는 질문 | 게시물 | 라우트 | 스키마 |
|---|---|---|---|---|
| **V1** 수집 현황 | 이벤트가 쌓이고 있는가? 언제·무엇이 얼마나? | `results/measurement/ingestion_report.json` | `/ingestion` | `ingestion_report.schema.json` |
| **V2** 계약 위반 | 무엇이 왜 거부됐는가? | `results/measurement/rejection_report.json` | `/rejections` | `rejection_report.schema.json` |
| **V3** 필드 충족률 | 어떤 필드가 비어 있는가? | `results/measurement/field_coverage_report.json` | `/coverage` | `field_coverage_report.schema.json` |
| **V4** KPI | 계산되는 KPI 는? 안 되는 것은 왜? | `results/measurement/kpi_report.json` | `/kpi` | `kpi_report.schema.json` |
| **V5** 데이터 품질 | `data_spec` §9 검사가 통과했는가? | `results/data_quality_report.json` | `/quality` | `data_quality_report.schema.json` |
| **V6** 봉인 상태 | 지금 보는 것이 어느 스키마·어느 커밋인가? | `results/measurement/freeze_status.json` | `/freeze` | `freeze_status.schema.json` |
| — | (인덱스) | `results/measurement/index.json` | `/` | `index.schema.json` |

## 5.1 V1 `ingestion_report`

- `totals` — 계층 0 지표 7종
- `by_event_type` — **16종 전부가 키로 존재해야 한다** (`minProperties: 16`). 0건인 타입을 목록에서 빼면 "없다"가 화면에서 사라진다
- `partitions[]` — 일자별 **배열**. **이벤트가 0건인 날짜도 행으로 존재한다** (`present: false`). 화면이 날짜 목록을 재구성하지 않는다
- **`sources`** — 출처별 관측 상태. **판정 주체는 게시물이다**

### 5.1.1 `sources` — 연결 상태를 게시물이 판정한다

```jsonc
"sources": {
  "commerce":  { "link_state": "connected",       "first_event_at": "2026-09-12T09:04:11.000+09:00",
                 "last_event_at": "2026-09-18T13:58:02.000+09:00", "event_count": 18430,
                 "staleness": { "status": "not_run", "value": null,
                                "reason_code": "PARAM_UNCONFIRMED",
                                "reason_detail": "정지 판정 임계값이 확정되지 않았고 C1 에서 그 상태에 도달할 수 없어 검증도 불가능하다." } },
  "simulator": { "link_state": "never_connected", "first_event_at": null,
                 "last_event_at": null, "event_count": 0, "staleness": { ... } }
}
```

**`link_state` 는 결정 가능한 것만 담는다 — 2값이다.**

| | |
|---|---|
| `never_connected` vs `connected` | **데이터로 결정된다.** 화면이 *"첫 수신이 null 이면 미연결"* 을 추론하지 않게 게시물이 판정한다 |
| **`stale` 을 enum 에 넣지 않는 이유** | *"멈췄다"* 판정에는 **임계값이 필요하고 그것이 미확정**이며, **C1 에서 그 상태에 도달할 수 없어 검증도 불가능하다.** 도달 불가 분기를 enum 에 넣으면 화면이 영원히 실행되지 않는 코드를 갖는다 |
| **대신 `staleness`** | **`metric_value` 로 준다** — `status: "not_run"` · `reason_code: "PARAM_UNCONFIRMED"` + 사유. **판정할 수 없다는 사실 자체가 값이다** |

> **리드 지시 *"불가능한 부분은 계약이 '구분 불가'를 명시적 값으로 주십시오"* 를 이렇게 푼다.**
> `metric_value` 를 재사용하므로 **화면이 이미 그릴 줄 아는 형태**이고, 빈칸 대신 사유가 온다.
> `link_state: "never_connected"` 이면 스키마가 `first_event_at`·`last_event_at` 을 `null`, `event_count` 를 `0` 으로 **강제**한다 — 실행 확인: *"미연결인데 수신 시각을 채운다"* → 거부됨.

### 5.1.2 ★ 수집 0건 날짜 — 구분할 수 없다고 쓴다 (Jonnathan X-5)

`partitions[].in_observed_range` 가 **관측 구간 안의 공백**과 **구간 밖**을 가른다. 그러나 그것으로도 **"수집 중단"과 "활동 없음"은 구분되지 않는다.**

> **두 경우가 같은 흔적을 남긴다.** 구분하려면 *"수집을 시도했다"* 를 남기는 heartbeat 레코드가 필요한데 Event Sink 에 없다.
>
> **heartbeat 를 C1 계약에 넣지 않는다.** 근거 셋:
> 1. `event_type` 16종을 늘리는 것은 `tests/test_schema.py:45-47` 이 `assertEqual` 로 고정한 값을 바꾸는 것 — **`EVENT SCHEMA v1` 의 실질 변경**이고 `FREEZE-003` 비용이 붙는다
> 2. Sink 밖의 별도 레코드로 두려면 **커머스와 시뮬레이터 양쪽이 써야 하는데 커머스는 편집 금지**다(charter §5)
> 3. C1 에는 그것을 검증할 데이터가 없다
>
> → **Jonnathan 의 문구를 그대로 지지한다.** 화면은 구분하지 않고 *"활동 없음과 수집 중단을 현재 데이터로 구분할 수 없습니다"* 라고 쓴다.
> **"활동 없음"이라고 쓰면 관측하지 않은 것을 단정하는 것이고, 0 채우기와 같은 종류의 잘못이다.**

**그리고 그 사실을 두 곳에 명시적 값으로 싣는다** — 화면이 빈칸을 보고 추측하지 않게:

```jsonc
"totals": {
  "ingestion_days_gap":        { "status": "ok", "value": 1, "unit": "count", "basis": { ... } },
  "ingestion_gap_attribution": { "status": "not_run", "value": null,
                                 "reason_code": "PRECONDITION_MISSING",
                                 "reason_detail": "heartbeat 레코드가 없어 이벤트 0건인 날짜가 수집 중단인지 활동 없음인지 구분할 수 없다." }
}
```

`notices` 의 **`INGESTION_GAP_UNDECIDABLE`** 이 화면 상단에서 같은 사실을 말한다.
**공백이 몇 개인지는 안다(`ingestion_days_gap`). 그것이 무엇인지는 모른다(`ingestion_gap_attribution`).** 두 개를 나눈 이유다.

## 5.2 V2 `rejection_report`

> ### ★ 보안 판정 — 거부 레코드 원문을 게시하지 않는다
> `rejected.jsonl` 에는 **`validate_event()` 가 거부한 레코드가 원문 그대로** 들어 있다 (`sink.py:203-206`).
> 거부 사유 중 하나가 *"측정 계층을 통과할 수 없는 필드"* — 즉 **Hidden Trait·τ·Potential Outcome 이 담긴 레코드가 `rejected.jsonl` 에 남는다.**
> 그 원문을 `results/` 로 옮기면 **금지 필드가 대시보드까지 도달하는 경로가 생긴다.** `ISO-003`·`NFR-002` 를 우회하는 뒷문이다.
>
> **→ 집계와 화이트리스트 필드만 게시한다.** `samples[]` 는 `event_type`·`partition_date`·`source`·`problems`·`offending_fields`(필드 **이름**만) 만 담고 **값은 담지 않는다.**
> 스키마의 `additionalProperties: false` 가 이것을 강제한다.

- `by_reason[]` — 사유를 **정규화한 키 10종**으로 집계한다. `validate_event()` 의 원문 메시지를 키로 쓰면 필드명이 섞여 카디널리티가 폭발한다
- `samples[]` — **사유당 최대 3건 권고.** 화면이 요구하는 것은 *"왜 거부됐나"* 의 예시이지 목록이 아니다

### 5.2.1 값은 담되 — 22컬럼만

Jonnathan 이 *"사유 + 필드명 + 값"* 을 요구했고, 나는 처음에 **값 전부를 금지**했다. 그러면 `page_type="main"` 같은 **화면에 꼭 필요한 정보**까지 사라진다.

> **타협이 아니라 정확한 경계를 그었다** — 유출 위험은 **스키마에 없는 필드의 값**에서 온다.
> `offending_values` 의 **키를 DATA-003 22컬럼으로 제한**한다 (`propertyNames: {enum: [22종]}`).
> 금지 필드(`coupon_sensitivity` 등)는 스키마에 없으므로 **값을 담을 자리가 구조적으로 없다.**
> **필드 이름은 항상 담을 수 있다** — `FORBIDDEN_FIELD_NAMES` 는 이미 코드에 공개된 목록이고 민감한 것은 값이다.
>
> 실행 확인: *"거부 샘플에 스키마 밖 필드의 값을 담는다"* → **거부됨.**

## 5.3 V3 `field_coverage_report`

- `fields` — **정확히 22개** (`minProperties: 22`, `maxProperties: 22`). `tests/test_schema.py:61-72` 가 `assertEqual` 로 고정한 22 와 같은 수다
- 각 필드에 `applicable_event_types`(충족률 분모의 의미) 와 **`affected_metrics`**(이 필드가 결손일 때 무너지는 지표)를 함께 낸다
- **`schema_gaps[]`** — ★ 아래

### 5.3.1 ★ `schema_gaps[]` — 컬럼 자체가 없는 것 (Jonnathan Y-1)

**`field_coverage` 는 존재하는 컬럼만 센다.** 계산식이 요구하는데 **컬럼 자체가 없는 것**은 어느 집계에도 나타나지 않고, 게시하지 않으면 **화면에서 영구히 사라진다.**

```jsonc
{ "ref": "discount",
  "required_by_formula": "order_amount = sum(unit_price*quantity) - discount · coupon_cost = sum(discount)",
  "where_it_should_live": "events 22컬럼 (DATA-003) — 없다",
  "blocks_metrics": ["coupon_cost", "marketing_cost", "contribution_profit"],
  "blocks_checks": ["DQ-09"],
  "reason_code": "MISSING_FIELD",
  "reason_detail": "...", "decision_ref": "D-16 · G-16" }
```

**C1 의 `schema_gaps` 는 4건이다:**

| `ref` | 계산식이 요구 | 어디에 있어야 하나 | 결정 |
|---|---|---|---|
| `unit_cost` | `cogs = Σ(unit_cost × quantity)` | `products` 테이블(미구현) · 커머스에도 없음 | `EC-1`·`EC-2` · Ecommerce `#24` |
| **`discount`** | `order_amount` 정의식 · `coupon_cost = Σ discount` | events 22컬럼 — **없다** | **D-16 · G-16 (신규)** |
| `shipping_fee` | `contribution_profit − shipping_subsidy` | events 22컬럼 — 없다 | D-3 |
| `refund` | `revenue` = 순매출 | `event_type` 16종 — 환불 이벤트 없음 | D-2 |

**네 건 모두 기여이익식이 빼는 항목이다.** 우연이 아니라 경제 모델이 스키마보다 나중에 정해진 결과다 (`data-model-erd.md` §5).

## 5.4 V4 `kpi_report`

- **`kpi-definition-v1.md` 가 정의한 지표 전부가 항목으로 존재한다.** 계산되지 않는 지표를 빼면 "무엇이 계산 불가인지"가 사라진다
- 각 항목이 **정의와 값을 같은 자리에** 담는다: `population` · `window` · `denominator_definition` · `formula` · `definition_ref` · `value`
  → *"같은 이름의 다른 계산"* (이슈 `#46` 완료 조건)이 **구조적으로 성립할 수 없다**
- `summary` 가 `kpi-definition-v1.md` §8 표(계산 가능/조건부/불가 집계)를 그대로 화면에 옮긴다. **대시보드가 세지 않는다** (`DB-012`)
- `metrics[].blocks` — 이 지표가 무너질 때 함께 무너지는 하위 지표. `blocked_by` 의 역방향 (§4.2)
- 스키마 조건:
  - `layer` 가 `customer_kpi`·`business_kpi` → `value` 는 **`combined` 없는** 출처 분해여야 한다
  - `layer` 가 `experiment` → `value` 는 단일 값 (`MEA-002` — 실험 판정에는 시뮬레이터 생성분만)

## 5.5 V5 `data_quality_report`

- `checks[].status` 가 **5값**이다: `pass` / `fail` / **`vacuous`** / `not_run` / `blocked`
- `gate_result` 가 **3값**이다: `pass` / `fail` / **`incomplete`**
  → **`incomplete` 를 둔 이유가 이 계약의 요점 중 하나다.** 실행한 검사가 전부 통과했어도 실행하지 못한 검사가 있으면 `pass` 가 아니다. *"미실행 검증을 통과로 표시하지 않는다"*(AGENTS.md)를 값으로 만든다
- 각 검사에 **`scope` 가 필수**다 — *"이 검사가 실제로 무엇을 검사했는가"* 의 범위 한정 문구. 범위를 적지 않으면 부분 검사가 전체 검사로 읽힌다
- `status` 가 `not_run`/`blocked`/`vacuous` 이면 `violations` 는 **`null` 이어야 한다.** `0` 으로 적으면 통과처럼 읽힌다 — 스키마가 거부한다
- **`spec_coverage`** — ★ 아래
- 상세 설계는 `data-quality-design.md`

### 5.5.1 ★ V-12 — "공허한 통과"를 계약에서 막는다

리드가 예시를 세어 확인한 것:
```
examples/empty-sink/data_quality_report.json  (개정 전)
  검사 18건 중 status="pass" ∧ examined_rows==0  →  7건 (39%)
  DQ-01 · DQ-02b · DQ-04 · DQ-07 · DQ-08 · DQ-10 · DQ-11
```

**순진하게 구현하면 화면의 39%가 초록 ✓ PASS 인데 아무것도 검사하지 않았다.**
`gate_result: incomplete` 라 게이트 층은 정직했지만 **개별 검사 행이 거짓말을 했다.**
*"미실행을 통과로 표시하지 않는다"* 의 한 층 아래 변종이다 — **"검사했지만 검사 대상이 0행이었다."**

> ### 판정 — 화면 규율이 아니라 스키마로 막는다
> Jonnathan 은 화면 규칙 `V-12` 로 막겠다고 했고, **그가 스스로 "당신 쪽에서 더 강하게 만들 여지가 있다"고 되물었다.**
> **그 말이 맞다.** 화면 규율로 남기면 **구현자 한 명이 놓치는 순간 뚫린다.** `denominator == 0 → ok 불가` 와 같은 자리, 같은 패턴이다.

**`status` 에 `vacuous` 를 신설하고 두 층에서 강제한다:**

| 층 | 규칙 |
|---|---|
| 검사 행 | `examined_rows == 0` → `status` 가 **`pass` 일 수 없다** |
| 검사 행 | `status == "vacuous"` → `examined_rows == 0` 이고 `violations` 는 **`null`** 이고 사유가 필수 |
| 검사 행 | `status == "pass"` → `examined_rows >= 1` |
| **게이트** | `gate_result == "pass"` → **모든 검사가 `pass`** 여야 한다 (→ `vacuous` 하나만 있어도 `pass` 불가) |

**개정 후 실측 — 7건이 전부 `vacuous` 로 바뀌었다:**
```
empty-sink: 검사 18건 · gate=incomplete · 공허한 pass 0건
            vacuous 7건 [DQ-01 · DQ-02b · DQ-04 · DQ-07 · DQ-08 · DQ-10 · DQ-11]
```
리드가 센 7건과 정확히 일치한다.

**화면의 부담이 줄어든다.** `status == "vacuous"` 를 그리면 되고, `pass` 와 `examined_rows` 를 함께 읽어 판정할 필요가 없다.

### 5.5.2 `spec_coverage` — 검사 정본 목록을 게시물이 준다 (Jonnathan Y-2)

> **판정: 게시물이 준다. 화면이 상수로 들고 있지 않는다.**
> 정본 목록이 두 곳에 있으면 갈라지고(P-4), 게시물이 주는 것만 그리면 **빠진 검사가 사라지며 사라진 것은 통과처럼 읽힌다.**

```jsonc
"spec_coverage": {
  "spec_items": [
    { "spec_ref": "퍼널 정합성", "covered_by": ["DQ-07","DQ-08"], "worst_status": "fail" },
    { "spec_ref": "참조 무결성", "covered_by": ["DQ-03"],          "worst_status": "not_run" }
  ],
  "reported_checks": 18,
  "unmapped_spec_items": []          // 비어 있지 않으면 화면이 그 사실을 표시한다
}
```

`data_spec` §9 의 **11개 정본 항목 전부**가 `spec_items` 에 온다. `unmapped_spec_items` 가 비어 있지 않다는 것은 **정본에 있는데 아무 검사도 덮지 않는 항목이 있다**는 뜻이고, 화면이 그것을 드러낸다.

## 5.6 V6 `freeze_status`

- PRD §22 Lock **9종 전부**가 항목으로 존재한다 (`minItems: 9`, `maxItems: 9`)
- 각 항목에 **`scope_note` 필수** — 부분 Lock 의 범위를 문장으로 남긴다. 예: *"`EVENT SCHEMA v1` 의 Lock 범위는 `events` 테이블에 한정된다"*
- `verification` 은 `match`/`mismatch`/`missing`/**`not_run`** — 대조를 실행하지 않았으면 `not_run` 이고 **통과가 아니다**
- `overall` 의 C1 도달 가능 최대치는 **`partial`** 이다. `sealed` 는 `EXPERIMENT_ENVIRONMENT_v1` 선언과 함께만 쓴다
- 상세 절차는 `gate1-freeze-procedure.md`

## 5.7 `index.json`

- **`verdict`** — ★ 첫 화면 최상단 판정 배너. 아래
- `views` 맵이 **V1~V6 ↔ 게시물 ↔ 라우트** 를 고정한다 → **Jonnathan 과의 협업 불변식이 기계가독이 된다**
- `artifacts[]` 의 `path` 는 정규식으로 `^(results|data/processed)/` 를 강제한다 → `DB-014` 위반 경로를 게시 인덱스에 적을 수 없다
- `publish_result: partial` — 일부 산출물을 게시하지 못한 상태. **대시보드는 이 상태를 숨기지 않는다**

### 5.7.0 `static_views` — 1:1 불변식의 명시적 예외

`/triggers`(PRD §71 트리거 5종)는 **게시물이 없다.** 정적 화면이다.
그러나 **적지 않으면 "계약에 없는 화면"과 "의도적으로 정적인 화면"을 구분할 수 없다** — 불변식 검사가 전자를 놓친다.

```jsonc
"static_views": [{
  "route": "/triggers", "title": "모니터링 트리거",
  "reason_code": "PRECONDITION_MISSING",
  "reason_detail": "PRD §71 트리거 5종은 전부 변화를 조건으로 하는데 게시물 이력이 없어 비교 기준이 없다. C1 작동 0종 — 각 트리거의 차단 사유를 적은 계획된 부재 표로 정적 구현한다."
}]
```

> **Jonnathan 의 제안을 채택한다** — *"`views` 에 게시물 없는 화면으로 기록하는 편이 불변식 검사에 정직하다"*.
> 다만 `views` 안에 넣으면 `artifact` 가 필수라 스키마가 깨지므로 **별도 배열**로 뒀다.
> 불변식은 이렇게 읽는다: **모든 라우트는 `views` 에 있거나 `static_views` 에 있다. 어디에도 없으면 계약이 모르는 화면이다.**

### 5.7.1 `verdict` — 배너를 게시물이 집계한다 (Jonnathan X-1)

> **판정: 게시물이 집계한다.** 리드 지적대로 **단순 합산도 계산이고**(`DB-012`), 무엇이 최상위인지의 규칙이 두 곳에 있으면 화면과 리포트가 다른 답을 낸다(P-4).

```jsonc
"verdict": {
  "level": "violation",                    // ok < attention < violation
  "headline_code": "QUALITY_VIOLATION",    // 7종 — 화면이 문구를 매핑한다
  "headline_detail": "퍼널 정합성 검사에서 위반 3건이 나왔다. 봉인된 정본 파일 1건이 Lock 시점과 다르다. 미실행 검사 8종.",
  "counts": { "quality_violations": 3, "checks_not_run": 8, "checks_blocked": 1,
              "metrics_unavailable": 7, "metrics_not_run": 0, "schema_gaps": 4,
              "lock_items_pending": 6, "rejected_events": 217 }
}
```

`headline_code` 7종 — `QUALITY_VIOLATION` · `FREEZE_MISMATCH` · `CONTRACT_VIOLATION` · `CHECKS_NOT_RUN` · `SINK_EMPTY` · `METRICS_UNAVAILABLE` · `ALL_CLEAR`.
**코드로 준다. 문구는 화면이 매핑한다** — Jonnathan 이 사유 코드에 대해 요구한 것과 같은 원칙이다.

---

# 6. 게시 절차

## 6.1 명령 — ⚠ 아직 존재하지 않는다

```bash
# W5-A 에서 신설한다. 2026-09-11 현재 이 명령은 실행할 수 없다.
python3 -m src.measurement.publish --source data/raw --out results
```

**현재 저장소에서 실행 가능한 명령은 `python3 -m unittest discover -s tests` 하나뿐이다.**
이 명령을 문서·게이트·PR 본문에 "실행했다"로 쓰지 않는다. `dashboard/` 의 빈 상태 안내(`DB-013`)에 이 명령을 표시할 때도 **"게시가 필요하다"** 는 안내로만 쓴다.

## 6.2 순서 — 원자성

```text
1. .staging/<run_id>/ 에 6종을 쓴다
2. 각 산출물을 자기 스키마로 검증한다        ← 실패하면 여기서 멈춘다 (§6.3)
3. os.replace() 로 최종 경로에 하나씩 옮긴다  (같은 파일시스템 → 원자적)
4. ★ index.json 을 마지막에 쓴다
5. .staging/<run_id>/ 를 지운다
```

**읽는 쪽의 의무:** `index.json` 을 먼저 읽고, 각 산출물의 `run_id` 가 인덱스와 **같은지 확인한다.**
다르면 값을 섞어 표시하지 않고 **"게시가 진행 중이거나 불일치"** 를 표시한다. `sha256` 대조는 선택이다(큰 파일에서 비용).

## 6.3 실패 시 — fail closed

> **자기 스키마를 통과하지 못한 산출물은 게시하지 않는다.**
> 부분적으로 잘못된 파일을 내보내는 것보다 안 내보내는 편이 낫다 — 잘못된 값은 화면에서 정상으로 보이지만, 없는 파일은 없다고 보인다.

`index.json` 에는 `status: failed` + 사유가 남고 `publish_result: partial` 이 된다. 자세한 예외 분류는 `exceptions.md`.

## 6.4 갱신 시점

| | |
|---|---|
| 트리거 | **사람이 게시 명령을 실행할 때만.** 파일 감시·크론·스트리밍 없음 |
| 대시보드 | 요청 시점에 파일을 다시 읽는다 (캐시하지 않는다) → `DB-011` 수동 새로고침이 그대로 성립 |
| 근거 | `DB-011`·`DB-013`. 실시간 요구가 어느 문서·사용자 발언에도 없다 |

**깨지는 조건:** 화면에서 개별 이벤트를 검색·필터링하고 싶다는 요구가 나오면 파일 읽기로 부족해진다(가정 A5). **그 요구가 나오면 멈추고 보고한다. C1 에서 조용히 API 를 만들지 않는다.**

---

# 7. 읽는 쪽(대시보드)의 제약 — 계약의 절반

| # | 제약 | 근거 |
|---|---|---|
| R-1 | **`results/` 와 `data/processed/` 만 읽는다.** `data/raw/`·`data/hidden/`·`data/ground_truth/` 접근 금지 | `DB-014` |
| R-2 | **계산하지 않는다.** 합계·비율·분류·정렬 기준을 새로 만들지 않는다. 표시 순서 정렬과 필터는 허용 | `DB-012` |
| R-3 | **출처를 재분류하지 않는다.** `by_source` 를 그대로 쓴다 | `MEA-002` · W-7 해소 |
| R-4 | **`status != "ok"` 인 값을 숫자로 렌더링하지 않는다.** 0 과 다른 시각 상태 + `reason_detail` 표시 | PRD §10.1 · USP-1 |
| R-5 | **`not_run` 을 `pass` 로 표시하지 않는다** | AGENTS.md |
| R-6 | `contract_version` 이 다르면 렌더링하지 않고 불일치를 표시한다 | 이 계약 |
| R-7 | `index.json` 이 없으면 **게시 방법을 안내한다** (`DB-013`). 빈 화면을 그리지 않는다 — §7.1 | `DB-013`·`SYS-001` |
| R-10 | **기준(`basis`) 없는 계산된 값이 오면 `계약 위반` 으로 렌더링한다.** 지표를 계산하지 않고 필수 필드의 존재만 보므로 `DB-012` 위반이 아니다 | 이 계약 §4.1 |
| R-8 | `notices` 를 화면에 표시한다. 가정을 숨기지 않는다 | `economic-rule-v1.md` §6.4 |
| R-9 | `src/**` 를 import 하지 않는다 | `DB-014` |

## 7.1 빈 상태의 명령 문구 — `BLOCKED` 가 아니다

`DB-013` 은 *"결과 파일이 없는 초기 상태에서는 **생성 방법을 안내**한다"* 를 `[MUST]` 로 요구하고, AGENTS.md 는 *"존재하지 않는 명령을 쓰지 않는다"* 로 막는다. 둘이 충돌하는 것처럼 보인다.

**충돌이 아니다 — 시점의 문제다.**

| 상황 | 답 |
|---|---|
| **게시물이 있을 때** | `provenance.generated_by` 를 그대로 표시한다. 생성기가 **자기 실행을 런타임에 기록**했으므로 지어낸 값이 아니다 |
| **게시물이 아예 없을 때** | 화면이 명령을 **문구로** 안내해야 한다. 그 문구는 **Andrew 착수 시점(W5-C)에 이미 실재한다** — `build-plan.md` §2.3 Phase 2''(Phillip 이 `publish.py` 를 만든다) 가 **W5-C 보다 앞선다** |

> **따라서 `BLOCKED` 로 남기지 않는다.** 설계 시점(W2)에 문구를 확정할 필요가 없고, 구현 시점에는 명령이 실재한다.
> **Andrew 는 실재하는 명령을 확인한 뒤 문구를 쓴다.** 확인 전에는 넣지 않는다.
> 만약 순서가 어긋나 W5-C 착수 시점에 `publish.py` 가 없다면 — **그때는 `BLOCKED` 다.** 그 경우에만 `docs/gate1_checklist.md` 에 기록한다.

> ### W-8 — `dashboard/` 는 현재 격리 검사의 사각지대다
> `tests/test_isolation.py:51-55` 의 `_iter_source_files()` 는 `src/` 하위 `*.py` 만 순회한다. **`dashboard/` 는 `src/` 밖이고 TypeScript 다 — 한 줄도 검사되지 않는다.**
> 위 R-1·R-9 를 강제하는 코드가 없다.
> **검사 확장 설계는 `dashboard-architecture.md` §6 에 있다. 실행은 봉인 규칙상 W6 Matthias + 사용자 승인 사항이다.**
> **C1 에서 확장하지 않기로 결정하면** `docs/gate1_checklist.md` 와 `freeze_status.notices` 에 `DASHBOARD_NOT_ISOLATION_CHECKED` 를 명시적 한계로 남긴다. **검사하지 않은 것을 통과로 적지 않는다.**

---

# 8. ★ 이 설계 중 발견한 것 — 새 스키마 공백 A-1 (`discount`)

`kpi-definition-v1.md` §5.4 가 `shipping_subsidy` 필드 부재를 발견했다. **같은 종류의 공백이 하나 더 있다.**

## 8.1 발견

| 근거 | 내용 |
|---|---|
| `schema.py:121` | `order_amount` 의 정의가 **`Σ(unit_price × quantity) − discount`** 다 |
| `EVENT_FIELDS` 22종 실측 | **`discount` 필드가 없다.** (event_id · customer_id · timestamp · event_type · session_id · session_duration · page_type · product_id · category · quantity · unit_price · order_id · order_amount · coupon_id · campaign_id · treatment_id · treatment_group · experiment_id · service_version · customer_version · simulator_version · random_seed) |
| `kpi-definition-v1.md` §5.1 | `coupon_cost = Σ discount` — **계산할 필드가 없다** |
| `data_spec` §9 금액 정합성 | `order_amount = Σ(unit_price × quantity) − discount`, 오차 0원 — **검산 불가** |

## 8.2 두 번째 층 — 품목 합계도 재구성할 수 없다

`_EVENT_RULES[PURCHASE]` 실측: 필수 `session_id`·`page_type`·`order_id`·`order_amount`, 선택 `coupon_id`·`campaign_id`·`session_duration`.
**`product_id`·`quantity`·`unit_price` 는 `purchase` 에서 `NOT_APPLICABLE` 이다** — 값이 있으면 거부된다(`schema.py:293-297`).

→ **`purchase` 이벤트는 주문 단위 1행이고, 한 주문의 `Σ(unit_price × quantity)` 를 `events` 테이블만으로 재구성할 수 없다.**
`add_to_cart` 로 근사하는 것은 장바구니 ≠ 주문이므로 부정확하다(`remove_from_cart` 가 있고 결제 실패도 있다).

→ **`data_spec` §9 의 금액 정합성 검사는 C1 에서 원리적으로 실행 불가**하며, `order_items` 테이블(§7.1)이 있어야 성립한다. `data-quality-design.md` DQ-09.

## 8.3 판정 제안 — `shipping_subsidy`(D-3)와 **같은 처리**

| 대상 | `coupon_cost` |
|---|---|
| **시뮬레이터 생성분** | `coupon_use` 이벤트 + `economic_config.treatment_cost` 로 **규칙 유도 가능** (T3 → 7,000원). `derived: true` + `derivation` 표시 |
| **커머스 실측분** | `MISSING_FIELD` — 커머스는 할인액을 저장하지 않는다 |
| **금액 정합성 검사** | `PRECONDITION_MISSING` — `order_items` 필요 |

**이것은 GATE 1 선행 조건이다.** `gate1-lock-scope.md` 의 G-1~G-15 에 **G-16 을 추가**할 것을 제안한다 — *"`discount` 필드 처리 방침이 결정된다"*.
**지금이 결정 비용이 가장 싼 시점이다** (`FREEZE-003` — Lock 이후 변경은 데이터 재생성 + 전 전략 재실행).

---

# 9. ★ Jonnathan 요청 ↔ 계약 대응표 (17행)

**협업 불변식의 오른쪽 열이다.** 화면이 요구하는 데이터가 게시물에 없거나, 게시물에 있는데 아무 화면도 안 쓰면 둘 중 하나가 틀린 것이다.

## 9.1 공통 지표 셀 (A-1 ~ A-6)

| # | 요청 | 계약 대응 | 판정 |
|---|---|---|---|
| **A-1** | `state` 4상태 이상 · `not_run` 을 `unavailable` 과 합치지 말 것 | `metric_value.status` **5종** — `ok` / `unconfirmed` / `unavailable` / **`blocked`** / **`not_run`** | **충족 (+1)** `blocked`(선언된 실행 불가)와 `not_run`(선언되지 않은 공백)을 따로 둔다 |
| **A-2** | `reason` 을 **문구가 아니라 코드**로 | `reason_code` — 7종 확정 + 2종 제안(`NOT_RUN`·`PRECONDITION_MISSING`) | **충족.** 2종은 D-15 확인 대기 |
| **A-3** | `reason_detail` 사람이 읽는 보충 | `reason_detail` (필수 · `minLength: 1`) | **충족.** 예시가 *"주문 1,204건 중 1,204건에 unit_cost 없음"* 형태를 쓴다 |
| **A-4** | `derived` bool | `derived` + **`derivation`**(유도 규칙, `derived:true` 면 필수) | **충족 (+1)** |
| **A-5** | `params_used` | **`params_used`** — 요청한 이름 그대로. `unconfirmed` 면 필수 | **충족** (초안의 `params` 를 개명함) |
| **A-6** | **`affected_metrics` 인접 관계** | **양방향으로 게시한다** — §4.2<br>원인→영향: `fields[f].blocks_metrics` · `schema_gaps[].blocks_metrics`<br>영향→원인: `metrics[].value.blocked_by`<br>영향→하위: `metrics[].blocks` | **충족.** 요청보다 넓다 — `blocked_by.kind` 9종으로 필드·스키마 공백·이벤트·지표·테이블·모델산출물·전략·파라미터를 구분한다 |

## 9.2 화면별 (B-1 ~ B-8)

| # | 요청 | 계약 대응 | 판정 |
|---|---|---|---|
| **B-1** | V1 — 16종 전부 키 · 일자별 배열 · 출처별 | `by_event_type` `minProperties: 16` · `partitions[]` 배열 · 전 항목 `by_source` | **충족** |
| **B-2** | V1-a — `ingestion_days_gap` + **0건 날짜 목록** | `partitions[]` 에 `present:false` 행이 남는다 + **`in_observed_range`** | **부분 충족.** 날짜 목록은 준다. **"중단 vs 활동 없음"은 못 준다** — §5.1.2 |
| **B-3** | V2 — 사유별 집계 + 대표 샘플 | `by_reason[]` · `samples[]`(사유당 3건 권고) | **충족** |
| **B-4** | V2 샘플에 **값** 포함 | `offending_values` — **키를 22컬럼으로 제한** | **조건부 충족.** §5.2.1 — 스키마 밖 필드의 값은 담을 수 없다(금지 필드 유출 차단). 필드 **이름**은 항상 담는다 |
| **B-5** | V3 — 충족률 + **분모** + `NOT_APPLICABLE` 제외 | `basis.denominator`(비율이면 필수) · `basis.observed_count` · `applicable_event_types` | **충족** |
| **B-6** | V4 — 지표 전부, 계산 불가도 키 | `metrics[]` 에 정의된 지표 전부. 계산되지 않는 것도 항목으로 존재 | **충족** |
| **B-7** | V5 — 4상태 + 사유 | `checks[].status` 4종 + `reason_code`/`reason_detail` + **`scope` 필수** | **충족 (+1)** `scope` 로 범위 한정 문구까지 |
| **B-8** | V6 — Lock 4상태 + **범위 한정 문구** | `items[].status` 5종 + **`scope_note` 필수** + `verification` 4값 | **충족 (+1)** `OUT_OF_SCOPE` 와 `not_run` 이 추가 |
| **B-9** | 전 화면 공통 헤더 — `data_version`·시각·커밋·**게시물 스키마 버전** | `provenance` + **`contract_version`** + `generated_at`(KST 강제) | **충족** |
| **B-10** | 빈 상태 안내의 **명령 문자열** | `provenance.generated_by`(런타임 기록) + §7.1 시점 판정 | **충족 · `BLOCKED` 아님.** 리드 판정 반영 |

## 9.3 추가 요청 (Y-1 ~ Y-4) · 경계 질문 (X-1 ~ X-6)

| # | 요청 | 계약 대응 | 판정 |
|---|---|---|---|
| **Y-1** | **스키마에 없는 필드 목록** | **`field_coverage_report.schema_gaps[]`** — C1 은 4건 | **충족.** §5.3.1. 이것이 없으면 `unit_cost`·`discount`·`shipping_fee`·환불이 화면에서 영구히 사라진다 |
| **Y-2** | 품질 **검사 정본 목록**을 게시물이 주는가 | **`spec_coverage`** — 게시물이 준다 | **충족.** §5.5.1. 화면이 상수로 들지 않는다 |
| **Y-3** | `PARTIAL` 의 **범위 한정 문구** | `items[].scope_note` **필수** | **충족** |
| **Y-4** | `/triggers` 데이터 | **게시물이 주지 않는다.** C1 에 트리거 계약이 없다 | **정적 구현 지지** |
| **X-1** | 판정 배너 집계 주체 | **`index.verdict`** — 게시물이 집계한다 | **충족.** §5.7.1. 단순 합산도 계산이다 |
| **X-4** | 출처별 연결 상태 (`link_state`) | **`sources[s].link_state`** 2값 — 게시물이 판정.<br>**`stale` 대신 `staleness` 를 `metric_value` 로** 준다 (`not_run` + `PARAM_UNCONFIRMED`) | **충족(형태 조정).** §5.1.1 — 도달·검증 불가 분기를 enum 에 넣는 대신 **판정할 수 없다는 사실을 값으로** 준다 |
| **X-5** | 수집 0건의 "중단 vs 활동 없음" | **못 푼다.** heartbeat 를 C1 에 넣지 않는다.<br>대신 **`ingestion_gap_attribution`** 을 `not_run` + `PRECONDITION_MISSING` 으로 게시한다 | **미해결 — 당신 판단을 지지한다.** §5.1.2. **공백이 몇 개인지는 알고, 그것이 무엇인지는 모른다** — 둘을 나눠 실었다 |
| **V-12** | (당신이 예시에서 발견) 공허한 통과 | **스키마로 막는다** — `status: "vacuous"` 신설. `examined_rows==0 → pass 불가`, `gate pass → 전건 pass` | **충족.** §5.5.1 — 당신이 되물은 대로 **계약 쪽이 더 나은 자리다.** 실측 7건이 전부 `vacuous` 로 바뀌었다 |
| **Y-4b** | `/triggers` 를 불변식에 기록 | **`index.static_views[]`** 신설 | **충족.** §5.7.0 — `views` 안에 넣으면 스키마가 깨져 별도 배열로 |
| **X-6** | 게시물 이력 보관 | **C1 에 넣지 않는다.** 쓰는 화면이 없다 | **합의.** 최신 1벌만. `run_id` 로 확장 여지만 남긴다 |

## 9.4 게시물에서 빼라는 권고 — 전부 수용

| 항목 | 조치 |
|---|---|
| 원본 이벤트 배열 | **게시하지 않는다.** V2 의 거부 샘플만 예외 |
| `manifest.files` 파일 경로 목록 | **게시하지 않는다** |
| 파생 상태 분포 | **게시하지 않는다.** W1 D-7 미해결 — `DerivedStateType` 이 `EventType` 밖이라 Sink 에 기록할 수단 자체가 없다 |
| 시계열 이력 | **게시하지 않는다** (X-6) |
| ~~`partitions[].files`~~ | **초안에 있었으나 제거했다** — 쓰는 화면이 없다. 협업 불변식의 반대 방향을 스스로 어겼던 자리다 |
| **V2 샘플의 값** | 당신이 *"값을 일절 렌더링하지 않겠다"* 로 고쳤다. **계약은 `offending_values`(22컬럼)를 그대로 둔다** — 게시하되 화면이 안 쓰는 것은 낭비지만, **지우면 나중에 필요할 때 계약을 다시 고쳐야 하고 그때는 Lock 이후일 수 있다.** 쓸지는 화면의 자유이고 담을 수 있는 범위는 계약이 정한다. 이견 있으면 지운다 |

> **되묻는 것 하나:** `partitions[].files`(일자별 파트 파일 수)는 `#53` D1-1(파티션 덮어쓰기)이 재발했는지 화면에서 보는 단서가 된다.
> 그러나 **당신이 요구하지 않았으므로 넣지 않았다.** 필요하면 말해 달라 — 한 줄이다.

---

# 10. 사용자·리드 결정이 필요한 항목

| # | 항목 | 선택지 | 추천 |
|---|---|---|---|
| **D-15** | 사유 코드 2종 추가 (`NOT_RUN` · `PRECONDITION_MISSING`) — §4.4 | ⑴ 9종으로 확장 ⑵ 7종 유지하고 `BLOCKED` 로 흡수 | **⑴.** ⑵는 "안 했다"와 "못 했다"를 같은 코드로 적게 되고, 그것이 미실행을 환경 탓으로 보이게 한다. **Jonnathan 도 같은 것을 독립적으로 요구했다** |
| **D-16** | **`discount` 필드 부재** — §8 · §5.3.1 | ⑴ 규칙 유도값(`derived:true`) + 금액 정합성은 `PRECONDITION_MISSING` ⑵ `Plan/` SRS DATA-003 개정 후 필드 추가 ⑶ 미결정으로 Lock 진행 | **⑴.** D-3(`shipping_subsidy`)과 같은 처리로 일관성 유지. **단 ⑵의 비용이 가장 싼 시점이 지금이다** — `discount` 는 `marketing_cost` Guardrail 의 구성요소라 `shipping_subsidy` 보다 무겁다 |
| **D-17** | `results/` 를 `.gitignore` 에 넣는가 — §2 | ⑴ 넣는다 ⑵ 넣지 않는다 ⑶ 넣되 `.agent-team/` 에 증거 사본 | **⑶** |
| **D-29** | `sources[s].state` 에 `stale` 을 넣는가 — §5.1.1 | ⑴ 넣지 않는다 (2값) ⑵ 임계값을 정하고 3값 | **⑴.** 임계값이 미확정이고 C1 에서 도달·검증 불가한 분기를 만들지 않는다 |
| **D-30** | 거부 샘플에 값을 담는가 — §5.2.1 | ⑴ 22컬럼만 담는다 ⑵ 전부 금지 ⑶ 제한 없이 담는다 | **⑴.** ⑵는 화면에 필요한 정보까지 없앤다. ⑶은 `rejected.jsonl` 의 Hidden Trait 이 화면까지 가는 경로를 연다 |

---

# 11. 개정 요약

## 11.1 개정 2 (2026-09-11 · 정합 1라운드)

| 무엇 | 왜 | 요청자 |
|---|---|---|
| `affected_metrics` → **`blocks_metrics`** · `affected_checks` → `blocks_checks` | 요청한 이름 그대로. `metrics[].blocks` 와 동사가 일치한다 | Jonnathan B-2 |
| `sources[s].state` → **`link_state`**, 값도 `never_connected`/`connected` | 요청한 이름 그대로 | Jonnathan B-9 |
| **`sources[s].staleness`** 신설 (`metric_value`) | 판정 불가를 **값으로** 준다. 도달 불가 분기를 enum 에 넣지 않는다 | 리드 |
| **`totals.ingestion_gap_attribution`** 신설 | 동일 — "구분 불가"를 명시적 값으로 | 리드 |
| ★ **`checks[].status` 에 `vacuous` 신설 + 2층 강제** | 공허한 통과를 화면 규율이 아니라 스키마로 막는다 | 리드 V-12 · Jonnathan |
| **`index.static_views[]`** 신설 | 1:1 불변식의 명시적 예외 (`/triggers`) | Jonnathan Y-4b |
| 사유 코드 **9종 확정** | Joshua shutdown — 리드 판정으로 이 계약이 정본 | 리드 D-15 |

## 11.2 개정 1 (2026-09-11)

| 무엇 | 왜 | 요청자 |
|---|---|---|
| **`basis` 신설** — 계산된 값에 필수, 계산 불가에 금지 | *"기준의 유무가 측정된 0 과 값 없음을 가른다"* | Jonnathan |
| **`blocked_by` · `affected_metrics` · `blocks`** — 결손 사슬 양방향 | 화면이 사슬을 추론하면 `DB-012` 위반 | Jonnathan · 리드 |
| **`schema_gaps[]`** — 컬럼 자체가 없는 것 | `field_coverage` 는 존재하는 컬럼만 센다 | Jonnathan Y-1 |
| **`sources[s]`** — 출처별 관측 상태 (2값) | 판정 주체를 게시물로 | Jonnathan X-4 |
| **`index.verdict`** — 배너 집계 | 단순 합산도 계산이다 | 리드 X-1 |
| **`spec_coverage`** — 검사 정본 목록 | 빠진 검사가 사라지는 것을 막는다 | Jonnathan Y-2 |
| **`provenance.generated_by`** | `DB-013` 을 지키면서 명령을 지어내지 않는다 | 리드 판정 ① |
| **`offending_values`** — 22컬럼 제한 | 화면 필요와 금지 필드 유출 차단을 동시에 | Jonnathan B-4 + 이 문서 S-1 |
| **`partitions[].in_observed_range`** | 구간 안 공백과 구간 밖을 가른다 | Jonnathan X-5 (부분) |
| `params` → **`params_used`** 개명 | 요청한 이름 그대로 | Jonnathan A-5 |
| `partitions[].files` **제거** | 쓰는 화면이 없다 | 협업 불변식 |
| 예시 **2벌**로 확장 | 전 시각 상태를 픽스처 하나로 확인 | — |

---

# 12. 미정으로 남긴 것

| 항목 | 왜 |
|---|---|
| 각 화면의 **정보구조·시각 표현** | **Jonnathan T2.12~T2.14 소관.** 이 문서는 "무엇이 데이터로 있는가"까지다 |
| `kpi_report.metrics` 의 **전체 47종 목록** | `kpi-definition-v1.md` 가 정의 정본이다. 이 계약은 **형식**을 고정하고 목록은 그 문서를 따른다. 예시에는 대표 13종만 |
| `by_reason.reason_key` **10종의 최종 확정** | `#53`·`#54` 완료 후 실제 발생분으로 확정한다 |
| **수집 0건의 "중단 vs 활동 없음"** | **계약으로 풀 수 없다.** heartbeat 가 필요하고 그것은 `EVENT SCHEMA v1` 변경 + 커머스 편집을 요구한다 (§5.1.2) |
| `data/processed/` 게시 여부 | C1 에 산출물이 없다 |
| 게시물 이력 | C1 요구에 없다. `run_id` 로 확장 여지만 남긴다 |
