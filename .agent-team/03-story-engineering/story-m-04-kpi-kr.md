---
story_key: M-04
epic: 범위 M — 측정 계층 (이슈 #42)
issue: "#46"
title: KPI 정의 v1 — 계산 계약 47종 + 계산 가능분 구현
status: done   # W5 Phillip 완료 — AC-1~6. 지표 46종 분류(문서 §8 의 47 은 자기 지표표보다 1 많다) · cohort_retention_rate 재분류(AC-3b)
owner: Phillip (W5-A)
phase: 2
blocked_by: ["M-02 (#54) — MetricStatus/ReasonCode", "M-03 — MetricValue (합의 필요)"]
blocks: ["M-06 (게시)", "M-09 (#49)"]
user_decisions_required: ["D-3", "D-4", "D-5", "D-9"]
source_hash: f8a349053598902b
source_files: 19
---

# M-04 · KPI 정의 v1 (`#46`)

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
| **대상 이슈** | `#46` — OPEN (2026-09-11 라이브 확인) |
| **담당** | Phillip · W5-A |
| **Phase** | **2** — `#47`(M-03)과 병렬 |
| **차단** | 사용자 결정 **D-3 · D-4 · D-5 · D-9** (§9.4) |
| **차단하는 것** | M-06(게시) · M-09(Lock 대상 `KPI DEFINITION v1`) |
| **커밋 type** | `feat` |

> ## ★ 이 스토리 한 줄
> **지표 이름 하나에 계산식·모집단·기간·분모가 1:1로 대응하게 만든다.**
> `#46` 완료 조건: *"같은 이름의 다른 계산을 막는다."*

> ## ⚠ 이슈 체크리스트에 C1 범위 밖이 섞여 있다
> `#46` 본문이 **Qini · AUUC · Uplift by Decile · CLV MAPE · Churn AUC-ROC ≥ 0.78** 을 요구한다.
> 이것들은 **모델 산출물이 있어야 계산된다**(`NEEDS_MODEL_OUTPUT`). charter §5 가 이후 사이클로 뺐다.
>
> **이 스토리는 `정의 확정 + 계산 가능분 구현` 으로 범위를 재단했다** — 기획 판정 **D-9**.
> **정의는 47종 전부 고정한다. 계산하지 않는 것도 정의는 한다.**
> **이슈 본문을 수정하지 않는다** (L3). 재단 사실을 **PR 본문에 적는다.**
> `[Source: .agent-team/03-service-planning/core-features.md#3.2]`

---

# 2. 스토리

> **`P-AI`**(다음 사이클 decision 개발자)**로서 나는 지표 이름을 보면 계산식·모집단·기간·분모를 알 수 있기를 원한다.**
> 왜냐하면 같은 "Retention" 이 상태 기준일 수도 코호트 잔존율일 수도 있고, 그 차이가 **결론을 바꾸기** 때문이다.
> `[Source: .agent-team/03-service-planning/user-stories.md#US-5]`

> **`P-팀`**(측정 계층 구현자·리뷰어)**으로서 나는 근거가 없는 지표가 0 으로 나오지 않기를 원한다.**
> 왜냐하면 0 은 "측정했더니 0"과 "측정할 수 없음"을 구분하지 못하고, **후자를 전자로 읽으면 잘못된 결론이 조용히 만들어지기** 때문이다.
> `[Source: .agent-team/03-service-planning/user-stories.md#US-6]`

---

# 3. 인수 조건 (AC)

## AC-1 · 계산 계약 — 이름 ↔ 계산식·모집단·기간·분모 1:1

- [ ] 모든 지표에 **계산식 · 모집단(`P_all`/`P_buyer`/`P_eligible`) · 기간 · 분모**가 명시된다
- [ ] `retention_rate`(상태·시점)와 `cohort_retention_rate[m]`(코호트)가 **다른 이름**이다
- [ ] `churn_rate`(운영 상태·후향)와 `churn_label`(모델 라벨·전향)이 **다른 이름**이고 분리 근거가 문서에 있다
- [ ] `average_order_value` 의 분모가 **주문 건수**임이 명시된다 (고객 수 아님)
- [ ] 분모에서 제외한 고객이 있으면 **제외 인원이 값과 함께** 보고된다 (`purchase_interval`)
- [ ] `docs/data_spec.html` §14 지표 체계와 **불일치 0**

## AC-2 · 공통 규약 R-1~R-14 를 시그니처로 강제

- [ ] **`index_date` 가 기본값 없는 키워드 인자**다 — R-1 *"'현재'라는 암묵 기준일을 쓰지 않는다"*
- [ ] 전향적 지표와 후향적 지표의 **함수 이름이 다르다** — R-2. 플래그로 만들지 않는다
- [ ] 모집단이 인자 또는 반환 `basis.population` 에 명시된다 — R-4
- [ ] 제외 인원이 `basis.excluded_count`·`excluded_reason` 으로 보고된다 — R-6
- [ ] **KPI 계층(1·2)에 `combined` 를 만들지 않는다** — R-7

## AC-3 · 계산 불가 (USP-1) ★

- [ ] 근거 이벤트가 0건인 지표가 **`0` 이 아니라 계산 불가로 산출**된다
- [ ] 계산 불가에 **사유 코드 9종 중 하나**가 붙는다
- [ ] **빈 Sink 에서 Observable 16개 전부가 계산 불가**로 표시된다 — 기존 동작 유지 (`tests/test_sink.py:198-203`)
- [ ] `PARAM_UNCONFIRMED` 지표는 **값과 함께 사용한 파라미터**를 표시한다 (이탈 임계값 28/42/60)
- [ ] **47개 지표의 계산 가능 / 조건부 / 불가 분류**가 산출물에 있다
- [ ] ★ **모든 지표 함수의 반환 타입이 `MetricValue` 다. `float` 를 돌려주는 함수가 없다**

## AC-3b · ★ `customers` 부재 — 모집단이 성립하지 않는 지표를 재분류한다 (리드 지시)

- [ ] **`cohort_retention_rate[m]`** → **`unavailable` + `PRECONDITION_MISSING`** · `blocked_by: [{kind:"table", ref:"customers"}]`
- [ ] ★ **`repurchase_rate` 는 제외한다 — `ok` + 정확한 `basis.population`** (Matthias 항목4)
- [ ] `P_eligible` 를 쓰는 모든 지표 → 동일
- [ ] **조치 줄에 `Ecommerce_Service #29`** — *"feat: 고객 모델에 가입일 추가와 라이프사이클 기준 확보"* (OPEN, 라이브 확인)
- [ ] **`kpi-definition-v1.md` §4 와의 모순을 문서에 명시한다** — 그 문서는 `cohort_retention_rate` 를 `✅`(계산 가능)로 적었다
- [ ] **임의로 근사하지 않는다** — `events` 첫 등장일은 가입일이 아니다

> ### ★★ `repurchase_rate` 를 여기 넣지 않는 이유 (Matthias 항목4 — 1차 컴파일 오류 정정)
> 계산식이 `|{purchase_count(c,[D−L,D]) ≥ 2}| / |{purchase_count(c,[D−L,D]) ≥ 1}|` 이고 **분모 정의가 이미 "기간 내 1회 이상 구매 고객"** 이다.
> **분자·분모 둘 다 `purchase` 이벤트만으로 계산된다. `signup_date` 가 계산식에 나오지 않는다.**
>
> **막힌 것은 계산이 아니라 `모집단` 칸의 `P_all(D)` 선언이고, 그건 `customers` 부재가 아니라 `kpi-definition-v1.md` 내부 모순이다.**
>
> `unavailable` + `PRECONDITION_MISSING` 은 *"근거가 없다"* 는 뜻인데 **근거는 있다.**
> **과대보고의 거울상이지만 이유를 틀리게 말하는 것은 같다.**
>
> **→ `status: "ok"` + `basis.population` 에 실제 모집단을 정확히 적는다:**
> ```
> "population": "[D−L, D] 구간에 purchase 이벤트가 1건 이상인 고객"
> "denominator_definition": "기간 내 1회 이상 구매 고객 수"
> ```
> **그리고 `kpi-definition-v1.md` 의 `P_all(D)` 표기와 어긋난다는 사실을 PR 과 M-08 에 보고한다.**

## AC-4 · "세어 보니 0"과 "셀 근거가 없다"를 가른다 ★

- [ ] `coupon_use` 0건일 때 `coupon_usage_count` 는 **`ok` + `0`** + `basis.observed_count: 0`
- [ ] `purchase` 0건일 때 `revenue` 는 **`unavailable` + `NO_SOURCE_EVENT`** (0원이 아니다)
- [ ] **분모가 0 인 비율 지표는 `ok` 일 수 없다** — 계약이 스키마로 거부한다
- [ ] 위 세 경우를 각각 확인하는 테스트가 있다

## AC-4b · ★ 정밀도 한계를 데이터에 남긴다 (Thomas N-8)

- [ ] `campaign_response_count` 가 **`limit_note` 에 한 줄**을 담는다 — *"쿠폰 비종속 캠페인의 반응은 담을 이벤트가 없어 과소계상된다"* (§4.9)
- [ ] `status` 는 **`ok`** 다 — `unconfirmed` 가 아니다. 파라미터로 맞아지는 종류가 아니다
- [ ] **`limit_note` 는 호출자가 넘긴다.** `value_formatted` 와 달리 `unit` 에서 유도되지 않는다 (m-03 §4.7)
- [ ] `limit_note` 가 실제로 게시물에 실렸는지 확인하는 테스트가 있다 — **선택 필드라 빠뜨려도 스키마가 안 잡는다**

## AC-5 · 창구 중립성

- [ ] **`kpi.py` 에 `commerce`·`simulator` 문자열이 없다**
- [ ] `kpi.py` 가 `open`·`Path`·`json`·`csv`·`gzip`·`yaml` 을 import 하지 않는다 (순수 함수)
- [ ] `tests/test_neutrality.py` 가 위를 소스 검사로 고정한다

## AC-6 · 회귀 없음

- [ ] `python3 -m unittest discover -s tests` — 기준선 46건 회귀 0
- [ ] `python3 -m unittest tests.test_isolation -v` — 통과
- [ ] **의존성 설치 없이** 통과
- [ ] `python3 .agent-team/04-architecture/tools/check_ownership.py` — PASS

---

# 4. 개발 컨텍스트 (`developer_context`)

## 4.1 공통 규약 R-1 ~ R-14 — **이 규약을 어기는 지표 정의는 v1 에 넣지 않는다**

### 시간 파라미터

| 기호 | 이름 | 의미 | 기본값 |
|---|---|---|---|
| `D` | 기준일 (index date) | 지표를 평가하는 시점. 실험 맥락에서는 `T0` | **명시 필수 — 기본값 없음** |
| `W` | 관찰기간 | `D` 이후를 보는 지표의 창 길이 | **42일** (`label_window_days`) |
| `L` | 회고기간 | `D` 이전을 보는 지표의 창 길이 | **42일** — 지표별로 다르면 이름에 명시 |

- **R-1** 모든 지표는 `D` 를 인자로 받는다. **"현재"라는 암묵 기준일을 쓰지 않는다**
- **R-2** `D` 이후를 보는 지표(전향적)와 `D` 이전을 보는 지표(후향적)를 **같은 이름으로 쓰지 않는다**
- **R-3** 모든 시각 비교는 **KST 단일 타임존**에서 한다. ⚠ 이것이 강제되지 않는 것이 `#53` D1-3 이다 — **`#53` 수정 전에 산출한 KPI 값은 하루 어긋날 수 있다**

### 모집단

| 기호 | 정의 |
|---|---|
| `P_all(D)` | `signup_date ≤ D` |
| `P_buyer(D)` | `P_all(D)` ∧ `lifetime_order_count(D) ≥ 1` |
| `P_eligible(D)` | `(D − signup_date ≥ 60일)` ∧ `(lifetime_order_count ≥ 1)` ∧ `(days_since_last_purchase ≥ 14일)` |

- **R-4** 모든 지표는 위 셋 중 하나를 명시한다. **"고객"이라고만 쓰지 않는다**
- **R-5** `P_eligible` 필터 결과에는 항상 `eligible_flag` 조건을 함께 보고한다
- **R-6** **분모에서 제외한 고객 수를 값과 함께 보고한다.** 제외를 조용히 하지 않는다

> ⚠ **`signup_date` 는 `customers` 테이블 컬럼이고 그 테이블이 미구현이다** `[Source: .agent-team/04-architecture/data-model-erd.md#1.1]`.
> **→ `P_all`·`P_eligible` 은 C1 에서 `events` 만으로 구성할 수 없다.** §4.5 참조.

### 출처 (R-7)

- **R-7** 두 출처를 합산한 값을 **기본 표시로 쓰지 않는다.** 합산이 필요하면 이름에 표시한다(`*_combined`)
- **계층 0(수집 건전성)에서만 `combined` 가 허용된다.** 계층 1·2 KPI 는 **계약 스키마가 `combined` 키를 거부**한다 `[Source: .agent-team/04-architecture/schemas/common.schema.json#$defs.kpi_source_split]`

### 계산 불가 (R-8 ~ R-10)

- **R-8** 근거 이벤트가 0건이거나 필수 필드가 결손이면 **값을 내지 않고 계산 불가로 표시한다.** `0` 을 반환하지 않는다
- **R-9** 계산 불가에는 **사유 코드**가 붙는다
- **R-10** `PARAM_UNCONFIRMED` 지표는 **값을 내되 사용한 파라미터를 값과 함께 표시한다**

### 신뢰구간 (R-11 ~ R-12) · Secondary (R-13 ~ R-14)

- **R-11** 실험 판정 지표는 95% CI 동반 — **고객 단위 Bootstrap, B = 2,000**
- **R-12** 표본 부족으로 CI 가 산출되지 않으면 "0"이나 "유의하지 않음"이 아니라 **`inconclusive`**
- **R-13** Secondary 는 **단독으로 실험을 중단시키지 않고 Primary 판정을 뒤집지 않는다**
- **R-14** 리포트는 **Primary 2개를 반드시 먼저 제시한 뒤** 나머지를 서술한다

`[Source: .agent-team/03-service-planning/kpi-definition-v1.md#2]`

> **C1 에서 R-11~R-14 는 정의만 한다.** 실험 판정 지표를 계산하지 않는다.

## 4.2 계층 0 — 수집 건전성 12종 *(C1 전부 계산 가능)*

**PRD §66 에 없다.** charter §3.1③ 과 §7.1(1차 독자 = 이 팀)이 요구하며, 원천은 **이미 구현된 `manifest.json`** 이다.
**대시보드 V1·V2·V3 의 데이터가 전부 이 계층이다.**

| 지표 | 계산식 | 분모 | 원천 |
|---|---|---|---|
| `events_ingested` | 저장된 이벤트 수 | — (count) | `manifest.rows` |
| `events_rejected` | 거부된 이벤트 수 | — (count) | `manifest.rejected` |
| `rejection_rate` | `events_rejected / (events_ingested + events_rejected)` | 시도 건수 | manifest |
| `rejection_reason_count[r]` | 사유 `r` 별 거부 건수 | — | `rejected.jsonl` |
| `event_type_coverage` | 1건 이상 발생한 `event_type` 종수 / **16** | **16 (고정)** | `manifest.event_type_counts` |
| `event_type_count[e]` | 타입 `e` 의 건수 | — | 동일 |
| `field_fill_rate[f]` | `present(f) / applicable(f)` — **`NOT_APPLICABLE` 은 분모에서 제외** | 해당 필드가 적용되는 이벤트 수 | `manifest.field_coverage` |
| `missing_field_count` | 적용 대상인데 한 건도 없는 필드 수 | — | `manifest.missing_fields` |
| `unavailable_metric_count` | 계산 불가 Observable 지표 수 | 16 | `sink.unavailable_metrics()` |
| `source_event_count[s]` | 출처 `s` 별 건수 | — | `manifest.sources` |
| `partition_day_count` | 데이터가 존재하는 날짜 수 | — | 파티션 디렉터리 |
| `ingestion_days_gap` | 파티션 구간 내 **이벤트가 0건인 날짜 수** | — | 파티션 목록 |

`[Source: .agent-team/03-service-planning/kpi-definition-v1.md#3]`

> **`ingestion_days_gap` 을 넣은 이유:** 수집이 **멈춘 것**과 **그날 활동이 없던 것**을 화면에서 구분해야 한다. 0 으로 채우면 둘이 같아 보인다.
> ⚠ **그러나 현재 데이터로는 구분할 수 없다** — heartbeat 가 없다. §4.7.

> **이 계층은 KPI 가 아니다.** 서비스 성과가 아니라 **계약 준수 상태**를 잰다. 실험 판정에 쓰지 않는다.

## 4.3 계층 1 — Customer KPI 8종

| 지표 | 계산식 | 모집단 | 기간 | 분모 | C1 |
|---|---|---|---|---|---|
| `churn_rate` | `\|{c : days_since_last_purchase(c,D) ≥ no_purchase_days}\| / \|P_buyer(D)\|` | `P_buyer(D)` | **시점 `D`** (후향) | 구매 이력 보유 고객 수 | ⚠ `PARAM_UNCONFIRMED` |
| `retention_rate` | `1 − churn_rate` — **동일 모집단·동일 시점의 파생값** | `P_buyer(D)` | 시점 `D` | 동일 | ⚠ 동일 |
| `cohort_retention_rate[m]` | 가입 코호트 `m` 개월차 구매 ≥1건 고객 / 코호트 전체 | 가입월 코호트 | `M1/M3/M6/M12` | 코호트 인원 | ✅ |
| `repurchase_rate` | `\|{c : purchase_count(c,[D−L,D]) ≥ 2}\| / \|{c : purchase_count(c,[D−L,D]) ≥ 1}\|` | `P_all(D)` | 회고 `L`=42일 | **기간 내 1회 이상 구매 고객** | ✅ |
| `winback_rate` | `\|{c : state(c,D−L)=churn ∧ purchase ∈ (D−L,D]}\| / \|{c : state(c,D−L)=churn}\|` | `P_buyer(D−L)` | `(D−L, D]` | `D−L` 시점 이탈 고객 수 | ⚠ `PARAM_UNCONFIRMED` |
| `purchase_frequency` | `Σ purchase 건수 / \|P\|` | **`P_buyer(D)`** | 회고 `L` | 고객 수 | ✅ |
| `purchase_interval` | 고객별 연속 `purchase` 간 일수의 **중앙값**을 구한 뒤, 그 값들의 **모집단 중앙값** | `P_buyer(D)` ∧ 구매 ≥ 2건 | 회고 `L` | 정의되는 고객 수 (**제외 인원 병기 — R-6**) | ✅ |
| `average_order_value` | `Σ order_amount / count(purchase)` | `P_buyer(D)` | 회고 `L` | **주문 건수** (고객 수 아님) | ✅ |

`[Source: .agent-team/03-service-planning/kpi-definition-v1.md#4]`

### 이름 충돌을 명시적으로 끊은 지점 3곳

| 충돌 | 갈라놓은 방법 |
|---|---|
| **Retention** — PRD §66.2 상태 기준 vs `DB-004` 코호트 잔존율 | `retention_rate`(상태·시점) / `cohort_retention_rate[m]`. **이름이 다르다** |
| **Churn** — 운영 상태(후향) vs 모델 라벨(전향) | `churn_rate` / `churn_label`. §4.4 |
| **AOV 분모** — 주문 건수 vs 고객 수 | `average_order_value` 는 **주문 건수**가 분모. 고객당 매출이 필요하면 `revenue_per_customer` 라는 **별도 이름** |

## 4.4 ★ 이탈 정의 — 운영 상태와 모델 라벨을 **함수 이름 수준까지** 분리한다

### ① 운영 상태 (Derived State · 후향적)

```
Active   : 마지막 구매 후 ≤ 27일
At Risk  : 마지막 구매 후 28 ~ 41일
Churn    : 마지막 구매 후 ≥ 42일
```

- 용도: **대시보드 표시 · 코호트 분석 · Rule-based Baseline 조건**
- `churn_rate`·`retention_rate`·`winback_rate` 가 이 정의를 쓴다
- **임계값 28/42/60 은 가설값이며 C1 에서 Lock 하지 않는다** — §4.6

### ② 모델 라벨 (Prediction Target · 전향적)

```
churn_label_i = 1  if  count(purchase | T0 < t ≤ T0 + 42) == 0
                0  otherwise
retained_i    = 1 − churn_label_i
```

- `label_window_days = 42` 는 **운영 정의와 독립인 고정 상수** — **C1 에서 Lock 한다**
- 용도: **모델 학습 라벨 전용.** 대시보드 상태 표시에 쓰지 않는다

### 왜 분리가 KPI 정의의 문제인가

운영 상태를 그대로 라벨로 쓰면 `days_since_last_purchase ≥ 42` 라는 Feature 가 라벨을 거의 완전히 결정한다.
**AUC 0.99 가 나오지만 학습된 것은 아무것도 없다** (PRD Risk 7 Churn Label Leakage).

**측정 계층이 이 분리를 지킨 증거가 이미 코드에 있다:**

```python
src/measurement/schema.py   DerivedStateType(inactive/at_risk/churn)  ← EventType 16종과 교집합 없음
src/measurement/schema.py   FEATURE_FORBIDDEN_EVENT_TYPES
tests/test_schema.py:188-196  test_no_observable_depends_on_derived_state   ← 깨뜨리지 않는다
```

`[Source: .agent-team/03-service-planning/kpi-definition-v1.md#6]`

> ### ★ W1 D-7 — **리드가 판정했다 (2026-09-11). 이 스토리가 정의를 추가한다**
>
> **문제였던 것:** `DerivedStateType` 이 `EventType` 밖이라 **Sink 에 기록할 수단 자체가 없다.**
>
> **판정: ④ 게시 시점 계산.** `at_risk`·`churn` 은 `days_since_last_purchase` 에서 유도되고 그 원천(`timestamp`·`purchase`)은 **이미 스키마에 있다.**
> **계산해서 게시하면 스키마를 바꾸지 않고도 정보가 살아난다.**
> ① `EventType` 16→19 는 **`EVENT SCHEMA v1` 실질 변경**이라 불가, ② 별도 테이블은 C1 범위 밖, ③ 기록 안 하면 정보가 사라진다.

### 이 스토리가 추가하는 것 — 파생 상태 분포 지표 3종

| 지표 | 계산식 | 모집단 | 기간 | 분모 | C1 |
|---|---|---|---|---|---|
| `derived_state_count[inactive]` | `\|{c : 27일 < days_since_last_purchase(c,D) ≤ … }\|` — 임계값은 `params_used` | `P_buyer(D)` | 시점 `D` (후향) | — (count) | ⚠️ `PARAM_UNCONFIRMED` |
| `derived_state_count[at_risk]` | `28 ≤ days_since_last_purchase < 42` | `P_buyer(D)` | 동일 | — | ⚠️ 동일 |
| `derived_state_count[churn]` | `days_since_last_purchase ≥ 42` | `P_buyer(D)` | 동일 | — | ⚠️ 동일 |

**필수 조건 넷 — 전부 지킨다:**

| # | 조건 | 왜 |
|---|---|---|
| ① | **`derived: true` + `derivation`**(계산식) 필수 | 계약이 강제한다. **저장된 사실과 구분되어야 한다** |
| ② | **`status: "unconfirmed"` + `params_used`** | 임계값 28/42/60 이 **가설값**이다 (§4.6) |
| ③ | ★ **Feature 사용 금지 문구를 `population` 또는 `derivation` 에 적는다** | *"라벨과 동어반복"* — PRD Risk 7 |
| ④ | ★ **`tests/test_schema.py:188-196 test_no_observable_depends_on_derived_state` 가 그대로 통과한다** | **Observable 16개가 파생 상태에 의존하면 안 된다.** 이 지표는 Observable 이 아니라 **표시 전용**이다 |

**④가 가장 위험한 자리다.** 파생 상태가 `kpi_report` 에 나타나는 순간 *"이제 Feature 로 써도 되는 것 아닌가"* 로 읽힐 수 있다.
**`OBSERVABLE_METRIC_SOURCES` 에 넣지 않는다.** 게시 형식은 M-06 §4.13, 계약 문장은 M-08 §4.5①.

## 4.5 ★ C1 에서 실제로 계산할 수 있는 것 — 정직한 경계

`kpi-definition-v1.md` §8 의 분류:

| 계층 | 지표 수 | C1 계산 가능 | 조건부 | 계산 불가 |
|---|---|---|---|---|
| 계층 0 수집 건전성 | 12 | **12** | 0 | 0 |
| 계층 1 Customer KPI | 8 | 5 | **3** (`PARAM_UNCONFIRMED`) | 0 |
| 계층 2 Business KPI | 12 | 5 | **3** (`NO_COST_BASIS`·`MISSING_FIELD`) | **4** |
| 실험 판정 지표 | 15 | 0 | 0 | **15** |
| **합계** | **47** | **22** | **6** | **19** |

> **단 "계산 가능"은 근거 이벤트가 있을 때다.**
> 2026-09-11 현재 **커머스는 이벤트를 한 건도 기록하지 않고**(`Ecommerce #28` 미착수) 시뮬레이터도 없다.
> **→ 오늘 실제로 값이 나오는 지표는 계층 0 의 일부뿐이며, 나머지는 전부 `NO_SOURCE_EVENT` 다.**
> **이것을 숨기지 않는 것이 USP-1 이다. 대시보드가 처음 켜졌을 때 화면이 계산 불가로 가득한 것은 버그가 아니라 정상 동작이다.**
> `[Source: .agent-team/03-service-planning/kpi-definition-v1.md#8]`

### ⚠ `customers` 테이블 부재가 만드는 추가 제약 — 스토리가 새로 짚는 것

`P_all(D)` 는 `signup_date ≤ D` 로 정의되는데 **`signup_date` 는 `customers` 컬럼이고 그 테이블이 미구현이다.**
`events` 22컬럼에 `signup_date` 가 없다 (실측: `event_id·customer_id·timestamp·event_type·session_id·session_duration·page_type·product_id·category·quantity·unit_price·order_id·order_amount·coupon_id·campaign_id·treatment_id·treatment_group·experiment_id·service_version·customer_version·simulator_version·random_seed`).

**영향받는 지표:**

| 지표 | 무엇이 막히나 | C1 처리 |
|---|---|---|
| `repurchase_rate` | **막히지 않는다 — AC-3b 참조** | ★ **계산식이 `purchase` 이벤트만 쓴다.** `signup_date` 가 나오지 않는다. 막힌 것은 `모집단` 칸의 `P_all(D)` **선언**이지 계산이 아니다 → **`ok` + 정확한 `basis.population`**(*"[D−L, D] 구간에 purchase 이벤트가 1건 이상인 고객"*). **`PRECONDITION_MISSING` 을 쓰지 않는다** — 근거가 있는데 없다고 말하는 것이다 |
| `cohort_retention_rate[m]` | **가입월 코호트**를 만들 수 없다 | `PRECONDITION_MISSING` |
| `P_eligible` 를 쓰는 모든 지표 | `signup_date` 필요 | 동일 |

> ### ★ 리드 지시 (2026-09-11) — **이 모순을 명시하고 재분류한다**
> *"이벤트는 '무언가 한 고객'만 보여주지 **전체 고객 명부가 아니다**."*
> **→ `PRECONDITION_MISSING` 으로 재분류하고 `Ecommerce_Service #29`(가입일 추가, OPEN)를 선행으로 적는다.**
>
> **W2 문서들이 이 지점을 명시하지 않았다.** `kpi-definition-v1.md` §8 은 `cohort_retention_rate` 를 `✅`(계산 가능)로 표시했으나, **가입월을 알 방법이 `events` 에 없다.**
> **→ 임의로 근사하지 않는다.** `PRECONDITION_MISSING` + `blocked_by: [{kind: "table", ref: "customers"}]` 로 게시하고 **조치 줄에 `Ecommerce_Service #29`** 를 적는다. **이 발견을 M-08(Lock 최종 검산)과 리뷰어에게 보고한다.**
> `basis.population` 에 *"고객"* 이라고만 쓰는 것이 R-4 위반이다 — **모집단을 정확히 쓸 수 없으면 그 지표는 계산 불가다.**

## 4.6 임계값 28/42/60 은 **가설값이다 — Lock 하지 않는다**

`data_spec` §5.1 이 확정 절차 5단계를 규정했다:

```
① Warm-up 구간(Day 0–272)의 고객별 구매 간격 분포 산출
② P75 / P90 분위수
③ at_risk_days ≈ P75,  churn_days ≈ P90 근방 확인
④ 재생성 시 Generated Churn Rate 15~25%(SIM-005) 확인
⑤ 만족하면 config/simulator_config.yaml 에 기록하고 GATE 1 에서 Lock
```

**①~④가 전부 시뮬레이터를 요구한다. C1 에 시뮬레이터가 없다.**
절차를 건너뛰고 숫자를 Lock 하면 *"미실행 검증을 통과로 표시하지 않는다"*(`AGENTS.md`)를 위반한다.

| Lock 한다 (C1) | Lock 하지 않는다 |
|---|---|
| **이탈 판정 방식** = 고정 윈도우 · `rule_operator: OR` 구조 | `at_risk_days` = 28 (가설값) |
| **운영 상태와 모델 라벨의 분리** | `no_purchase_days` = 42 (가설값) |
| **`label_window_days = 42`** — 운영 정의와 독립인 고정 상수 | `no_login_days` = 60 (가설값) |

`[Source: .agent-team/03-service-planning/kpi-definition-v1.md#1.1]`

**→ 임계값을 쓰는 지표는 `status: "unconfirmed"` + `params_used: {no_purchase_days: 42, at_risk_days: 28}`** (계약이 `params_used` 를 필수로 강제한다).

## 4.7 ★ 수집 0건의 "중단 vs 활동 없음" — 풀지 않고 사실을 싣는다

**계약으로 풀 수 없다.** heartbeat 레코드가 필요한데 `event_type` 16종을 늘리는 것은 `EVENT SCHEMA v1` 의 실질 변경이고, 커머스 편집이 필요하며, C1 에 검증할 데이터가 없다.

**→ 두 값을 나눠 낸다:**

```jsonc
"ingestion_days_gap":        { "status": "ok", "value": 1, "unit": "count", "basis": {...} },
"ingestion_gap_attribution": { "status": "not_run", "value": null,
                               "reason_code": "PRECONDITION_MISSING",
                               "reason_detail": "heartbeat 레코드가 없어 이벤트 0건인 날짜가 수집 중단인지 활동 없음인지 구분할 수 없다." }
```

**공백이 몇 개인지는 안다. 그것이 무엇인지는 모른다.**
`[Source: .agent-team/04-architecture/api-contracts.md#5.1.2]`

> **"활동 없음"이라고 쓰지 않는다.** 관측하지 않은 것을 단정하는 것이고, **0 채우기와 같은 종류의 잘못**이다.

## 4.8 ★ 시그니처 원칙 — 규약을 타입으로 만든다

```python
def average_order_value(
    events: Sequence[Mapping[str, object]],
    *,
    index_date: date,          # ← 기본값이 없다. R-1 을 시그니처로 강제
    lookback_days: int,
) -> MetricValue: ...          # ← float 를 돌려줄 자리가 없다
```

| 규칙 | 강제 방법 |
|---|---|
| **R-1** 암묵 기준일 금지 | `index_date` 가 **기본값 없는 키워드 인자** |
| **R-2** 전향/후향 혼동 금지 | **함수 이름이 다르다.** `churn_rate()` / `churn_label()` 을 같은 함수의 플래그로 만들지 않는다 |
| **R-8** 0 반환 금지 | 반환이 **항상 `MetricValue`**. `0.0` 을 돌려줄 방법이 타입에 없다 |
| **N-3** 출처 무지 | `events` 를 받을 뿐 출처를 판정하지 않는다. `publish.py` 가 나눠 두 번 부른다 |

`[Source: .agent-team/04-architecture/code-structure.md#4.1]` · `[Source: .agent-team/04-architecture/design-patterns.md#P-5]`

## 4.9 `campaign_response_count` 의 정밀도 한계 — 값이 나오는데 **틀린다**

`schema.py OBSERVABLE_METRIC_SOURCES` 가 `campaign_response_count` 를 `campaign_exposed`·`coupon_clicked`·`purchase` 로 계산한다.
**쿠폰이 없는 캠페인(배너·푸시)의 클릭을 담을 이벤트가 없다** — `coupon_clicked` 는 쿠폰을 전제한다.

**→ 쿠폰 비종속 캠페인의 반응률은 이 지표로 측정되지 않는다.**

**C1 에서 이벤트를 추가하지 않고 한계를 명시한다.** 계약에는 담을 자리가 있다 — 값은 `ok` 이되 화면이 **`한계` 칩**을 붙인다 (규칙 V-7).

> **`provisional`(잠정)과 다르다.** `provisional` 은 파라미터가 확정되면 값이 맞아진다. **`한계` 는 이벤트가 추가되지 않으면 영원히 과소계상이다.**
> `[Source: .agent-team/03-service-planning/kpi-definition-v1.md#4.2]` · `[Source: .agent-team/07-design/missing-state-spec.md#5.2]`

### ★ 어디에 담나 — `limit_note` 에 한 줄 (Thomas N-8·C-1 파생)

**계약에 담을 자리가 없었다.** `metric_value` 11프로퍼티 + `additionalProperties: false` 실측 — `한계` 를 담을 필드가 없다.
**M-06 이 `limit_note` 를 선택 필드로 계약에 추가한다** (`[Source: .agent-team/03-story-engineering/story-m-06-publish-kr.md#4.17]`).

```python
MetricValue.ok(
    value=1204, unit="count", basis=...,
    limit_note="쿠폰 비종속 캠페인(배너·푸시)의 반응은 담을 이벤트가 없어 과소계상된다.",
)
```

| 규칙 | 내용 |
|---|---|
| **`limit_note` 는 호출자가 넘긴다** | `unit` 에서 유도할 수 없는 **지표별 사실**이다. `value_formatted` 와 반대다 (m-03 §4.7) |
| **선택 필드다** | 없어도 계약을 어기지 않는다. **그래서 빠뜨려도 아무도 안 잡는다** — AC 로 못 박는다 |
| **`status` 는 `ok` 다** | 값은 나온다. `unconfirmed` 가 아니다 — 파라미터가 확정되면 맞아지는 종류가 아니기 때문이다 |
| **C1 에서 이 한 곳뿐이다** | 47종 중 `campaign_response_count` 하나. 늘리려면 근거를 PR 에 적는다 |

> ⚠ **이 한 줄이 없으면 d-02 V-7 의 `한계` 칩은 영원히 뜨지 않는다.** 화면이 그리라고 한 것이 데이터에 없다.

## 4.10 함정

| # | 함정 | 왜 빠지나 | 대신 |
|---|---|---|---|
| **T-1** | `def churn_rate(...) -> float` | 비율이니까 | AC-3 — **`MetricValue`.** `0.0` 을 돌려줄 방법이 없어야 한다 |
| **T-2** | `index_date: date = date.today()` | 편하다 | R-1 — **기본값 없는 키워드 인자** |
| **T-3** | `churn_rate(events, prospective=True)` | 코드가 짧다 | R-2 — **함수 이름이 다르다** |
| **T-4** | 분모 0 일 때 `0.0` 반환 | `ZeroDivisionError` 를 막으려고 | **계약이 `denominator == 0 → ok 불가` 를 스키마로 거부한다.** `unavailable` + `basis` 없이 |
| **T-5** | `coupon_use` 0건 → `unavailable` | *"이벤트가 없으니 계산 불가"* 로 읽는다 | ★ **`ok` + `0`.** 세어봤고 0 이었다. `coupon_use` 라는 모집단이 존재한다 (AC-4) |
| **T-6** | `purchase` 0건 → `revenue: 0` | 위의 반대 실수 | ★ **`unavailable` + `NO_SOURCE_EVENT`.** 매출 0원과 근거 없음은 다르다 |
| **T-7** | `cohort_retention_rate` 를 `events` 첫 등장일로 근사 | 값이 나온다 | §4.5 — **가입월이 아니다.** `PRECONDITION_MISSING` |
| **T-8** | 계산 불가 지표를 `metrics[]` 목록에서 뺀다 | 화면이 깨끗해진다 | **A-4 안티패턴.** *"무엇이 계산 불가인지 사라진다"* |
| **T-9** | 계층 1·2 에 `combined` 를 넣는다 | "전체" 숫자가 필요해 보인다 | **R-7 · 계약이 스키마로 거부한다** |
| **T-10** | `basis.population` 에 `"고객"` | 짧다 | **R-4 위반.** `P_buyer(2026-09-18)` 처럼 정확히 |
| **T-11** | `purchase_interval` 에서 구매 1건 고객을 조용히 뺀다 | 정의되지 않으니까 | **R-6 — `excluded_count`·`excluded_reason` 을 함께 낸다** |
| **T-12** | 실험 판정 지표 15종을 아예 만들지 않는다 | C1 에 계산이 없으니까 | **정의는 47종 전부 한다.** *"정의는 결과보다 먼저 있어야 한다"* — `#46` 완료 조건 |

---

# 5. 작업 분해 (Tasks)

## T1 · `MetricValue` 합의 (M-03 과)

- [ ] ★ **`MetricValue`·`Basis`·`BlockerRef` 는 M-03 이 `schema.py` 에 정의한다. 이 스토리는 import 만 한다** — 정의하지 않는다
- [ ] M-03 이 아직이면 **그 부분을 먼저 요청**한다. 임시로 자기 버전을 만들지 않는다

## T2 · 계층 0 — 12종 (AC-1·3·4)

- [ ] 12종 구현. **원천은 `manifest.json` 이지만 `kpi.py` 는 파일을 읽지 않는다** — manifest dict 를 인자로 받는다
- [ ] `rejection_rate` 의 분모 0 처리 (T-4)
- [ ] `event_type_coverage` 는 분모가 **16 고정**이므로 0건이어도 `ok` + `0/16`
- [ ] `ingestion_gap_attribution` 을 `not_run` + `PRECONDITION_MISSING` 으로 (§4.7)

## T3 · 계층 1 — 8종 (AC-1·2)

- [ ] 5종 구현 + 3종 `unconfirmed` (`params_used` 포함)
- [ ] `signup_date` 의존 지표는 `PRECONDITION_MISSING` (§4.5)
- [ ] `purchase_interval` 의 `excluded_count`·`excluded_reason`
- [ ] `average_order_value` 의 `denominator_definition` = *"주문 건수"*

## T4 · 계층 2 — 12종

- [ ] 원가 근거 불필요 6종 — `revenue` · `coupon_cost` · `message_cost` · `campaign_fixed_cost` · `shipping_subsidy` · `marketing_cost`
- [ ] **계산은 `economics.py` 가 한다.** `kpi.py` 는 이름·계약·`MetricValue` 조립만 — 중복 구현하지 않는다
- [ ] `cogs`·`contribution_profit` 은 `NO_COST_BASIS` 경로 (M-03 위임)
- [ ] `shipping_subsidy`·`coupon_cost` 의 `derived: true` + `derivation` (D-3 · D-16)

## T5 · 실험 판정 지표 15종 — **정의만**

- [ ] `incremental_*` · `roi` · `ai_roi` · `ai_net_incremental_value` → `NEEDS_TWO_STRATEGIES`
- [ ] `qini_coefficient` · `auuc` · `uplift_by_decile` · `persuadables_ratio` → `NEEDS_MODEL_OUTPUT`
- [ ] `churn_test_auc` · `precision` · `recall` · `f1` → `NEEDS_MODEL_OUTPUT`
- [ ] `predicted_clv` · `clv_mape` · `top20_precision` → `NEEDS_MODEL_OUTPUT`
- [ ] `pehe` · `corr(τ̂, τ)` → `NEEDS_MODEL_OUTPUT` + `src/diagnostics/` 전용 표시
- [ ] **Primary 2개**(`incremental_contribution_profit` · `qini_coefficient`)와 **Guardrail 4개**의 `role` 을 정의에 담는다

## T6 · 47종 분류 산출 (AC-3)

- [ ] `summary` 구조 — `total` · `ok` · `unconfirmed` · `unavailable` · `blocked` · `not_run` · `by_layer`
- [ ] **게시물이 이 집계를 준다. 대시보드가 세지 않는다** (`DB-012`)

## T7 · 테스트

- [ ] `tests/test_kpi_definitions.py` — **이름 ↔ 계산식·모집단·기간·분모 1:1**
      - 47종 전부에 `population`·`window`·`denominator_definition`·`formula`·`definition_ref` 가 있다
      - 이름이 중복되지 않는다
      - `retention_rate` ≠ `cohort_retention_rate`, `churn_rate` ≠ `churn_label`
- [ ] `tests/test_kpi_values.py` — 값 검사
      - ★ `coupon_use` 0건 → `coupon_usage_count` 가 **`ok` + `0`**
      - ★ `purchase` 0건 → `revenue` 가 **`unavailable` + `NO_SOURCE_EVENT`**
      - ★ 분모 0 비율 → **`ok` 가 아니다**
      - `unconfirmed` 지표에 `params_used` 가 있다
      - `purchase_interval` 의 `excluded_count` 가 실제 제외 인원과 같다
- [ ] `tests/test_neutrality.py` 에 `test_kpi_has_no_source_literal` 추가 (M-03 이 만든 파일)

## T8 · 검증 (AC-6)

- [ ] `python3 -m unittest discover -s tests` — 출력 전문 + skip 수·사유
- [ ] `python3 -m unittest tests.test_isolation -v`
- [ ] `python3 .agent-team/04-architecture/tools/check_ownership.py`

---

# 6. 파일 목록 (`file_list`)

## 6.1 이 스토리가 만드는 파일

| 파일 | 동작 |
|---|---|
| `src/measurement/kpi.py` | **신설** — 순수 함수 |
| `tests/test_kpi_definitions.py` | **신설** |
| `tests/test_kpi_values.py` | **신설** |
| `tests/test_neutrality.py` | **수정** (M-03 이 만듦) — `kpi.py` 검사 추가 |
| `src/measurement/schema.py` | **조건부** — `MetricValue` 를 여기 둘 경우 (M-03 과 합의) |
| `.agent-team/04-architecture/tools/ownership.json` | **수정하지 않는다** — 이미 등록돼 있다(Thomas N-1). 돌려 **확인만** |

## 6.2 절대 만지지 않는 파일

```
tests/test_isolation.py · .github/workflows/isolation.yml          ← 봉인
src/measurement/economics.py                                       ← M-03 소유. 중복 구현하지 않는다
src/simulator/** src/decision/** src/diagnostics/** src/orchestration/**
Plan/** · AGENTS.md · src/AGENTS.md · src/*/AGENTS.md · README.md
dashboard/**                                                       ← Andrew
../Ecommerce_Service/**                                            ← 읽기만
```

---

# 7. 테스트

## 7.1 실행 가능한 명령

```bash
python3 -m unittest discover -s tests
python3 -m unittest tests.test_kpi_definitions -v
python3 -m unittest tests.test_kpi_values -v
python3 -m unittest tests.test_neutrality -v
python3 -m unittest tests.test_isolation -v
python3 .agent-team/04-architecture/tools/check_ownership.py
```

## 7.2 깨뜨리면 안 되는 기존 테스트

| 테스트 | 이유 |
|---|---|
| `test_sink.py:198-203 test_empty_sink_marks_every_metric_unavailable` | ★ **USP-1 회귀 테스트** |
| `test_schema.py:175 test_all_sixteen_observables_are_derivable` | Observable 16개가 이벤트로 계산 가능 |
| `test_schema.py:188-196 test_no_observable_depends_on_derived_state` | ★ **파생 상태가 Feature 로 새지 않는다** — §4.4 |
| `test_isolation.py` 6건 | 새 파일도 자동 검사 대상 |

## 7.3 계약 픽스처로 대조할 수 있다

`.agent-team/04-architecture/examples/commerce-connected/kpi_report.json` 이 **대표 13종의 실제 형태**를 담고 있다.
구조: `metrics[]` 의 각 항목이 `name` · `layer` · `role` · `population` · `window` · `denominator_definition` · `formula` · `definition_ref` · `value` · `blocks`.

**★ 이 픽스처가 §4.10 T-5·T-6 의 대비를 한 파일에 담고 있다:**
- `coupon_usage_count` → `ok` + `0` (기준: `coupon_use` 이벤트 0건 중)
- `coupon_cost` → `unavailable` (`discount` 필드 부재 + 이벤트 0건)

**같은 0 에서 갈리는 지점이다.** 테스트가 이 대비를 재현해야 한다.

---

# 8. 연속성

## 8.1 선행 스토리에서 이어받는 것

| 스토리 | 이어받는 것 |
|---|---|
| **M-02 (`#54`)** | `MetricStatus` 5종 · `ReasonCode` 9종 · `Category`·`PageType` Enum |
| **M-03 (`#47`)** | `MetricValue`·`Basis`·`BlockerRef` (합의로 소유 결정) · `errors.py` · **계층 2 계산 실체** |
| **M-01 (`#53`)** | ⚠ **타임존 정책** — R-3. `#53` 수정 전 KPI 값은 하루 어긋날 수 있다 |

## 8.2 확립된 패턴

| 패턴 | 어디에 |
|---|---|
| `OBSERVABLE_METRIC_SOURCES` — 지표 ↔ 근거 이벤트 매핑 | `schema.py`. **`kpi.py` 가 이 매핑을 다시 만들지 않는다** |
| `sink.unavailable_metrics()` — 근거 0건 판정 | `sink.py`. 계층 0 의 `unavailable_metric_count` 원천 |
| **`float` 반환 금지** | 아직 없다. **이 스토리가 확립한다** |
| 한글 독트링·메시지 | 전 파일 |

## 8.3 M-03 과 병렬이다 — 겹치는 지점

| 겹침 | 처리 |
|---|---|
| `MetricValue` 정의 | ★ **M-03 소유. 이 스토리는 import 한다** |
| 계층 2 지표 | **계산은 `economics.py`, 이름·계약은 `kpi.py`.** `kpi.py` 가 기여이익식을 다시 쓰지 않는다 |
| `tests/test_neutrality.py` | M-03 이 만들고 M-04 가 항목을 추가한다 |

---

# 9. 완료 정의 (DoD) · 미결정 · 차단

## 9.1 DoD

- [ ] AC-1 ~ AC-6 전부 체크
- [ ] **47종 전부가 정의로 존재한다.** 계산하지 않는 것도 목록에 있다
- [ ] `kpi.py` 에 출처 문자열 0건 · I/O import 0건 — `test_neutrality.py` 로 고정
- [ ] `float` 를 돌려주는 지표 함수 0건
- [ ] ★ **`customers` 부재 지표를 `PRECONDITION_MISSING` 으로 재분류**하고 `Ecommerce_Service #29` 를 조치로 적었다 (AC-3b)
- [ ] ★ **파생 상태 분포 지표 3종을 정의**했고 `derived: true`·`params_used`·**Feature 금지 문구**를 담았다
- [ ] **`test_no_observable_depends_on_derived_state` 가 그대로 통과한다**
- [ ] **범위 재단(D-9) 사실을 PR 본문에 적었다** — 이슈 본문은 수정하지 않는다
- [ ] `#46` 을 **닫지 않았다**

## 9.2 이 스토리에서 하지 않는 것

| 항목 | 왜 |
|---|---|
| Qini · AUUC · AUC · CLV MAPE **계산** | `NEEDS_MODEL_OUTPUT` — 이후 사이클 (D-9 재단) |
| Bootstrap CI **산출** | 실험 판정 지표가 계산되지 않는다 |
| Primary 지표 **실산출** | 두 전략이 없다 |
| 기여이익 **계산식 구현** | **M-03 의 `economics.py`** |
| ~~파생 상태 기록 경로~~ | ★ **해소 (리드 판정 ④)** — **이 스토리가 분포 지표 3종을 정의한다.** §4.4 |
| 게시 (`results/`) | **M-06** |
| 출처 분할 | **M-06 의 `publish.py`** |

## 9.3 미결정 — 구현자가 정하고 PR 에 적는다

| # | 항목 | 선택지 |
|---|---|---|
| ~~**M04-a**~~ | ~~`MetricValue` 소유~~ | ★ **확정 — M-03 이 소유하고 이 스토리는 import 한다.** 병렬이라 "먼저 만든 쪽"은 합의 자리가 없었다(Thomas C-5) |
| **M04-b** | 계층 0 의 원천 형태 | ⑴ `manifest` dict 를 인자로 ⑵ 정규화된 dataclass — **⑴이 단순하나 `kpi.py` 가 manifest 키에 결합된다** |
| ~~**M04-c**~~ | ~~`signup_date` 의존 지표~~ | ★ **해소 (리드 지시)** — `PRECONDITION_MISSING`. AC-3b |

## 9.4 차단 — 사용자 결정 4건

| # | 항목 | 선택지 | W2 추천 |
|---|---|---|---|
| **D-3** | `shipping_subsidy` 필드 부재 | ⑴ **규칙 유도값 + `derived: true`** ⑵ `Plan/` SRS 개정 후 필드 추가 | **⑴.** SRS 변경은 권한 밖. 커머스 실측분은 `MISSING_FIELD` |
| **D-4** | KPI Lock 시점 정본 충돌 (PRD §22 GATE 1 vs `data_spec` §14 GATE 2) | ⑴ **계산 계약=GATE 1 / 역할 배정=GATE 2 로 분해** ⑵ 전부 GATE 1 ⑶ 전부 GATE 2 | **⑴.** 두 정본을 모두 만족하는 유일한 해석 |
| **D-5** | 이탈 임계값 28/42/60 을 C1 에서 Lock 하는가 | ⑴ **Lock 하지 않고 방식만** ⑵ 42일 유지 Lock | **⑴.** `data_spec` §5.1 확정 절차가 미실행이고 시뮬레이터 없이 실행 불가 |
| **D-9** | `#46` 범위 재단 | ⑴ **"정의 확정 + 계산 가능분"으로 C1 종결 + `M-4b` 분리** ⑵ 열어둔 채 다음 사이클로 | **⑴.** 하나의 이슈가 두 사이클에 걸치면 무엇이 끝났는지 흐려진다. **이슈 신설·수정은 L3 — 사용자 지시 필요** |

`[Source: .agent-team/03-service-planning/kpi-definition-v1.md#9]` · `[Source: .agent-team/03-service-planning/core-features.md#5]`

> **이 스토리는 D-3⑴ · D-4⑴ · D-5⑴ · D-9⑴ 을 전제로 쓰였다.** 다르게 판정되면 §4.6 · §4.5 · T4 를 다시 읽는다.

## 9.5 하류로 넘기는 것

| 받는 스토리 | 넘기는 것 |
|---|---|
| **M-06 (게시)** | 47종 정의 · `summary` 집계 구조 · `blocked_by`/`blocks` 사슬의 지표 쪽 절반 |
| **M-08 (`#45`)** | ★ **`customers` 부재로 `P_all`·코호트가 성립하지 않는다는 발견** (§4.5) — Lock 최종 검산 입력 · `campaign_response_count` 정밀도 한계 문구 · **파생 상태 기록 경로 결정 요구** |
| **M-09 (`#49`)** | Lock 대상 정본 파일 `src/measurement/kpi.py` · 선행 조건 **`G-11`** 충족 증거 · D-4 해석 결과 |
| **d-02 (대시보드)** | 47종 분류표 → 화면 V4 가 그대로 옮긴다 · `한계` 칩 대상(`campaign_response_count`) |

<!-- ════════ source_hash inputs (D3 · Matthias 항목5) ════════
     계산법: project-context-kr.md §12  ·  파일 19종
     재현:  아래 목록을 sorted() 하고 각 파일에 f"{path}\n{sha256_hex}\n" 를 이어붙여
            그 바이트열의 SHA-256 앞 16자리를 취한다. 없는 파일은 "MISSING".

     .agent-team/00-plan/charter.md
     .agent-team/00-plan/task-graph.md
     .agent-team/03-service-planning/economic-rule-v1.md
     .agent-team/03-service-planning/kpi-definition-v1.md
     .agent-team/03-service-planning/user-stories.md
     .agent-team/04-architecture/adr/ADR-0003-metric-value-shape.md
     .agent-team/04-architecture/adr/ADR-0007-blind-calculation.md
     .agent-team/04-architecture/adr/ADR-0008-basis-required.md
     .agent-team/04-architecture/build-plan.md
     .agent-team/04-architecture/code-structure.md
     .agent-team/04-architecture/design-patterns.md
     .agent-team/04-architecture/exceptions.md
     .agent-team/04-architecture/schemas/common.schema.json
     .agent-team/04-architecture/schemas/kpi_report.schema.json
     AGENTS.md
     docs/GIT_WORKFLOW.md
     src/AGENTS.md
     src/measurement/schema.py
     src/measurement/sink.py

     → source_hash = f8a349053598902b
     ════════════════════════════════════════════════════ -->
