# 개발 정의서 — 측정 계층 · 관측 대시보드

**작성** Timothy (Role 11 · W6 문서) · 2026-09-14
**대상** `src/measurement/`(측정 계층) + `dashboard/`(관측 대시보드), 브랜치 `feat/measurement-layer-and-dashboard`
**목적** 이후 사이클(시뮬레이터·의사결정 계층) 개발자와 신규 합류자가 이 두 영역의 핵심 개념·용어를 코드를 뒤지지 않고 파악하도록 한다. **상상으로 채우지 않았다 — 항목마다 코드·문서 근거를 달았다.**

---

## 1. 이 시스템의 구조

### 측정 계층 (창구, `src/measurement/`)

시뮬레이터(출제자)와 의사결정 계층(수험생)이 유일하게 만나는 지점. **아무에게도 의존하지 않는다** — `src.simulator`·`src.decision`·`src.diagnostics`를 import하지 않는다(`src/AGENTS.md`, `tests/test_isolation.py`가 강제). 실제 서비스(`Ecommerce_Service`)도 같은 스키마로 여기에 기록한다.

역할이 넷으로 나뉜다:

| 층 | 모듈 | 책임 |
|---|---|---|
| 계약층 | `schema.py` | 무엇이 통과하는가 — 이벤트 스키마, `MetricValue` 타입, enum 정의 |
| 계산층 | `kpi.py`·`economics.py` | 순수 함수. I/O 없음. **출처(커머스/시뮬레이터)를 모른다** |
| 입출력 | `sink.py`·`config_loader.py`·`validate.py`·`freeze.py` | 의존성(`pyarrow`·`PyYAML`)이 사는 유일한 층 |
| 조립층 | `contracts.py`·`publish.py` | 출처 분할·원자적 게시·자기검증 |

**규칙:** 아래 층은 위 층을 모른다. `publish.py`만 여러 모듈을 조립한다.

### 관측 대시보드 (`dashboard/`)

Next.js 앱(`:3001`). `results/`의 게시물을 **읽기만** 한다 — API 서버를 두지 않는다(`DB-013`). C1은 **관측 화면군**(측정 계층 산출물 6화면 + `/triggers` 정적 화면)만 만든다. **결과 화면군**(`(results)/` — `src/decision/` 산출물 8화면, 이후 사이클)은 라우트 자리만 남기고 만들지 않는다.

---

## 2. 핵심 원칙 (이 시스템 전체를 관통)

| 원칙 | 뜻 | 강제 지점 |
|---|---|---|
| **창구 중립성** | 측정 계층은 "커머스는 원가가 없다" 같은 지식을 갖지 않는다. 계산 가능 여부는 **출처가 아니라 근거(basis)의 유무**로 가른다 | `tests/test_neutrality.py` — `economics.py`·`kpi.py` 소스에 `commerce`·`cost_rate` 등 문자열이 없음을 검사 |
| **결손을 0으로 채우지 않는다** | 근거가 없으면 계산 불가로 표시한다. 0이나 추정값을 넣지 않는다 | `MetricValue`가 `float`를 직접 반환하지 않는 반환 타입 설계 자체 + `verify_core_invariants()` |
| **미실행 검증을 통과로 표시하지 않는다** | `not_run`은 `pass`와 다르다. 실행하지 못한 검사가 있으면 품질 게이트는 `incomplete`이지 `pass`가 아니다 | `data_quality_report.gate_result` 3값(`pass`/`fail`/`incomplete`) |
| **결정의 부재만 차단한다** | 데이터의 부재(필드 결손)가 아니라 규칙을 정하지 않은 것이 GATE 1을 막는다. 필드가 없어도 유도 규칙을 정하면 Lock 가능(D-16) | `GATE1_PRECONDITIONS` G-9·G-16 |

---

## 3. 이벤트 스키마 (`schema.py`)

### `EventType` — 관측 가능한 원본 이벤트 16종

**정의** `schema.py:77`

```
session_start · page_view · search · product_view · return_visit          (세션·탐색)
add_to_cart · remove_from_cart · checkout_start · purchase                (구매 퍼널)
campaign_exposed · push_sent · coupon_exposed · coupon_clicked · coupon_use  (마케팅)
review · cs_contact                                                        (부수)
```

`tests/test_schema.py`가 `assertEqual`로 정확히 16종을 고정한다(부분집합이 아니다). 늘리면 `EVENT SCHEMA v1`의 실질 변경 — `FREEZE-003`(버전 상향+데이터 재생성+전 전략 재실행)이 든다.

### `DerivedStateType` — 파생 상태 3종

**정의** `schema.py:102`: `inactive`·`at_risk`·`churn`. **`EventType`과 교집합이 없다** — `EventType`으로 기록할 수 없고, 측정 계층이 **게시 시점에 계산**해 `derived: true`로 낸다. Feature로 쓰면 라벨과 동어반복(운영 상태 임계값이 그대로 예측 라벨을 결정)이 되므로 **Feature 사용 절대 금지**(PRD Risk 7 — Churn Label Leakage).

### `EVENT_FIELDS` — 22컬럼

**정의** `schema.py:190`. 그룹 6개: `core`(4, 전 이벤트 필수) · `session`(3) · `product`(4) · `order`(2) · `marketing`(5, 뒤 3종은 항상 선택) · `meta`(4, 항상 선택). 표 없는 필드는 자동 `NOT_APPLICABLE`이고 **값이 있으면 거부된다**(화이트리스트가 부재로 동작). 예: `purchase`는 주문 단위 1행이라 `product_id`·`quantity`·`unit_price`가 `NOT_APPLICABLE`이다 — 품목을 넣으면 레코드 전체가 거부된다.

### 식별자 형식 9종

`event_id`(UUID4) · `customer_id`(`^C\d{8}$`) · `session_id`(`^S-C\d{8}-\d{13}$`) · `order_id`(`^O\d{8}-\d{6}$`) · `product_id`(`^P\d{4}$`) · `coupon_id`(`^CPN-[A-Z0-9]{6}$`) · `campaign_id`(`^CMP-\d{8}-\d{3}$`) · `treatment_id`(`^T[0-4]$`) · `experiment_id`(`^EXP-\d{8}-\d{2}$`). **커머스의 현재 식별자(`test-user-1`·`dummyjson-16`·`randomUUID()`)는 전부 이 형식을 위반한다** — 측정 계층에 매핑 계층을 두지 않고, 기록 시점에 변환하는 쪽이 소스다(`docs/measurement_contract.md` §1).

### `event_source()` — 출처 판별

**정의** `sink.py:74-83`

```
simulator_version is None and random_seed is None  →  COMMERCE
그 외                                               →  SIMULATOR
```

별도 플래그 컬럼 없이 스키마에서 파생한다(`MEA-002`) — 기록자가 출처를 위조할 여지가 적다.

### 타임존 정책

입력은 **오프셋이 붙은 어떤 표기든** 허용(`+09:00`·`Z`·`-05:00`). 오프셋 없는 timestamp는 **거부**(순간을 특정할 수 없어서). 저장 시 `EventSink`가 **KST로 정규화**한다 — 파티션 날짜(`date=YYYY-MM-DD`)도 같은 파싱에서 나온다.

---

## 4. `MetricValue` — 값·계산불가를 한 타입으로

`float`를 직접 반환하는 계산 함수를 두지 않는다는 것이 이 시스템에서 가장 중요한 설계 결정이다. 반환 타입에 `0.0`을 돌려줄 자리가 없으면, 결손이 0으로 채워질 **수가 없다**. 상세 구조·상태 5종·`basis`·`blocked_by`는 [`measurement-publish-api-v1.md` §4](./measurement-publish-api-v1.md#4-★-metric_value--값-표현의-핵심-타입)에 있다.

---

## 5. KPI 카탈로그 (`kpi.py`)

`METRIC_SPECS`(`kpi.py:1126`) — 지표 46종을 계층(`layer` 0~3)과 C1 가용성(`computable`/`conditional`/`unavailable`)으로 분류한 정본 목록.

| 계층 | 이름 | 개수 | C1 상태 |
|---|---|---|---|
| 0 | 수집 건전성 | 12 | 전부 `computable` |
| 1 | Customer KPI | 8 | `computable` 4 · `conditional` 3 · `unavailable` 1 |
| 2 | Business KPI | 12 | `computable` 5 · `conditional` 3 · `unavailable` 4 |
| 3 | 실험 판정 지표 | 14 | 전부 `unavailable`(모델 산출물·두 전략 비교 필요) |

**합계 46종** (2026-09-14 실측, `len(kpi.METRIC_SPECS)`). 계층0/1/2는 `kpi-definition-v1.md`의 §3/§4/§5.1~5.2와 정확히 개수가 일치하지만, 계층1 내부 분류(`cohort_retention_rate`)와 계층3 총수(14 vs 문서 15)에 불일치가 있다 — 상세는 `design-vs-impl-gaps.md` §1.

**게시되는 지표 행과 카탈로그가 다르다.** `publish.py:927` `_EXPERIMENT_METRICS`(kpi_report의 `layer: "experiment"` 행 14건)는 `METRIC_SPECS`의 계층3 14건과 **이름 구성이 다르다** — `precision`·`recall`·`f1`·`pehe`·`corr_tau_hat_tau`는 `METRIC_SPECS`에만 있고(`summary.total`에는 잡히지만 화면 행에는 없다), `sleeping_dog_targeting_rate`는 `_EXPERIMENT_METRICS`·`_METRIC_ROLES`(guardrail 역할)에만 있고 `METRIC_SPECS`에는 없다. 상세는 `design-vs-impl-gaps.md` §1.4.

### `churn_rate` vs `churn_label` — 운영 상태와 모델 라벨의 분리

| | 운영 상태 (`churn_rate` 등) | 모델 라벨 (`churn_label`) |
|---|---|---|
| 방향 | 후향적 (지금까지 안 샀다) | 전향적 (앞으로 42일 안 살 것이다) |
| 용도 | 대시보드 표시·코호트 분석·Rule-based Baseline | 학습 라벨 전용 |
| 임계값 | `at_risk_days=28`·`no_purchase_days=42`·`no_login_days=60` — **가설값, C1 Lock 안 함** | `label_window_days=42` — **C1 Lock함**(운영 정의와 독립) |

운영 상태를 그대로 라벨로 쓰면 `days_since_last_purchase ≥ 42`라는 Feature가 라벨을 거의 완전히 결정해 AUC 0.99가 나오지만 학습된 것은 없다(PRD Risk 7).

---

## 6. 경제 규칙 (`economics.py` + `config/economic_config.yaml`)

### `EC-1`/`EC-2` — 원가율은 생성 파라미터이지 추정 파라미터가 아니다

```
cogs(order) = Σ(unit_cost × quantity)   if has_cost_basis(order)   ← 저장된 값을 읽는다
            = NO_COST_BASIS             otherwise                  ← 원가율을 곱해 추정하지 않는다
```

가르는 기준은 **출처(커머스/시뮬레이터)가 아니라 근거(unit_cost 존재 여부)**다. `economics.py` 소스에 `commerce`라는 문자열이 없다(`test_neutrality.py`가 강제) — 측정 계층은 커머스의 구현 상태를 몰라야 한다.

### 발생주의 3원칙 (`EC-3`)

1. 발송 비용(`message_cost`, 30원/건)은 **발송 시점에 전원** 계상 — 반응 여부 무관
2. 할인 비용(`coupon_cost`)은 **쿠폰이 실제 사용된 주문에만** 계상 — 노출·클릭만으로는 발생하지 않는다
3. **역효과 고객(Sleeping Dog)에게 쓴 비용도 계상**한다 — 손실을 낸 지출을 지우지 않는다

이 구분이 없으면 "반응하지 않은 고객에게 쓴 돈"이 사라져 ROI가 과대평가된다.

### `revenue_up_profit_down` — 값이 아니라 판정 규칙

```
revenue(strategy) > revenue(baseline) AND contribution_profit(strategy) < contribution_profit(baseline)
```

참이면 그 전략은 Primary가 개선돼도 **실패로 판정**한다(Guardrail, PRD §65). `economics.py:718`.

### AI 투자비용

`config/economic_config.yaml`의 `ai_investment` 블록(모델 개발 1,200만원 + 컴퓨트 60만원, 12개월 상각 + 운영 30만원/월 + 모니터링 20만원/월). `economics.ai_investment_cost()`(`economics.py:630`)가 `monthly_amortized × (campaign_days/30)`으로 캠페인(42일) 귀속액을 계산하며 `status: unconfirmed`로 낸다(가정 기반 추정치). **실제 계산값은 2,170,000원**이다 — 상세와 문서 오류는 `design-vs-impl-gaps.md` §2.

### `A-REFUND` — 총매출을 순매출로 간주

환불·취소 이벤트가 없다(스키마 22컬럼·16종 고정이라 추가 불가, `Plan/` 개정 필요 = 권한 밖). `revenue = Σ order_amount`이며 환불을 차감하지 않는다 → `contribution_profit`이 **과대평가**된다(오차 방향 명시). `config`의 `assumptions.refund_adjusted: false`와 게시물 `notices`의 `REFUND_NOT_ADJUSTED`로 상시 표시한다. 실험 판정(Incremental Profit)에는 영향 없다 — `MEA-002`가 실험 결과에 시뮬레이터 생성분만 쓰도록 규정하고, 시뮬레이터는 환불을 생성하지 않는다.

---

## 7. GATE — 봉인(Freeze) 체계

### GATE 1과 `freeze.py`

`GATE1_PRECONDITIONS`(G-1~G-16, `freeze.py:230`)가 전부 충족돼야 Lock 가능(`can_lock`). C1은 **부분 봉인(`PARTIAL_FREEZE`)만 실행**하고 `EXPERIMENT_ENVIRONMENT_v1`(GATE 1 전체 통과 선언)은 선언하지 않는다. 상세 목록은 `measurement-publish-api-v1.md` §7.

### Lock 대상 9종 (PRD §22) — C1 상태

| 상태 | 항목 | 소관 |
|---|---|---|
| `OUT_OF_SCOPE`(5) | `SERVICE_v1`·`CUSTOMER_PERSONA_v1`·`HIDDEN_TRAIT_RULE_v1`·`BEHAVIOR_RULE_v1`·`TREATMENT_RESPONSE_v1` | commerce/simulator (미가동) |
| `PENDING`(2) | `EVENT_SCHEMA_v1`(events 테이블에 한정) · `ECONOMIC_RULE_v1` | measurement |
| `PARTIAL`(2) | `CHURN_DEFINITION_v1`(방식만, 임계값 미확정) · `KPI_DEFINITION_v1`(계산 계약만, 역할 배정은 GATE 2) | measurement |
| `LOCKED`(완전 봉인) | **0종** | — |

### 검증 3층 (탐지)

```
1층  tests/test_freeze.py       →  freeze.verify()   (실패하면 테스트가 죽는다)
2층  publish.py 게시 시점        →  freeze.verify()   →  results/measurement/freeze_status.json
3층  대시보드 /freeze            →  그 게시물을 그린다
```

세 층이 같은 함수(`freeze.verify()`)를 쓴다 — 각자 판정하면 갈린다.

### `FREEZE-003` — 해제 절차

Lock 이후 봉인 대상을 바꾸면: ① 스키마 버전 상향 → ② 전 데이터 재생성 → ③ Baseline부터 전 전략 재실행. 사용자 승인 사항이며 `config/gate1_lock.yaml`을 손으로 고치는 것으로 대체되지 않는다(해시 대조가 실패한다).

---

## 8. 대시보드 핵심 개념

### A8 판정 — 대시보드는 앱 하나

`dashboard/`는 **애플리케이션 하나**다. "관측 화면군"(C1, `src/measurement/` 산출물)과 "결과 화면군"(이후, `src/decision/` 산출물)은 같은 앱의 다른 라우트 그룹(`(observability)`/`(results)`)일 뿐 별개 대시보드가 아니다(`.agent-team/03-service-planning/usp.md` §1.2).

### `DB-012`/`DB-013`/`DB-014` — 세 계약 축

| 코드 | 뜻 |
|---|---|
| `DB-012` | 대시보드는 **계산하지 않는다.** 합계·비율·분류·판정을 만들지 않는다 |
| `DB-013` | HTTP API를 두지 않는다. 결과 파일이 없으면 생성 방법을 안내한다 |
| `DB-014` | 읽기는 `results/`와 `data/processed/`뿐. `data/raw/`·`data/hidden/`·`data/ground_truth/`·`src/**` 접근 금지 |

### 0 채우기 함정 (`?? 0` 함정)

`status !== "ok"`이면 `value`는 항상 `null`(스키마 강제). `(null).toLocaleString()`이 예외를 던지므로 구현자는 **예외를 막으려고** `value ?? 0`을 쓴다. 이 한 줄이 이 프로젝트의 USP-1(결손을 값과 같은 크기로 보여준다)을 끝낸다. 올바른 방법은 `status`로 분기하는 것이지 기본값을 주는 것이 아니다:

```ts
const display = m.status === 'ok' ? m.value_formatted : '—';   // '—' U+2014, hyphen 아님
```

`dashboard/src/lib/format/metric.ts`가 이 분기를 구현한다. `?? 0`·`|| 0`·`Number(value)`·`parseFloat(v) || 0`·`counts[k] || 0`·`value.toFixed(1)`은 전부 금지 패턴이다(`dashboard/AGENTS.md` DG-9).

### `run_id` 대조 — 원자성의 읽는 쪽 절반

게시는 `.staging/` → `os.replace()` → `index.json` 마지막 쓰기 순서로 원자적이다. 읽는 쪽은 각 산출물의 `run_id`가 `index.json`과 같은지 확인하고, 다르면 "게시 진행 중 또는 불일치"를 표시하며 **값을 섞지 않는다**. `dashboard/src/lib/artifacts/read.ts`.

### 시각 상태(Visual State) — 계약에서 기계적으로 파생

`dashboard/src/lib/format/state.ts`가 `(status, reason_code)` → 9종 시각 상태로 **순수 매핑**한다(화면이 새로 판정하지 않는다 — `DB-012`):

| 시각 상태 | 글리프 | 조건 |
|---|---|---|
| `available` | 없음 | `status:ok` |
| `provisional` | ◐ | `unconfirmed` + `PARAM_UNCONFIRMED` — **값이 있다**("계산 불가"로 부르면 안 됨) |
| `planned` | · | `unavailable` + `NEEDS_TWO_STRATEGIES`\|`NEEDS_MODEL_OUTPUT`\|`PRECONDITION_MISSING` |
| `unconnected` | ○ | `unavailable` + `NO_SOURCE_EVENT` |
| `gap` | ⚠ | `unavailable` + `NO_COST_BASIS`\|`MISSING_FIELD` |
| `env_blocked` | ⊘ | `blocked` + `BLOCKED` |
| `not_run` | ? | `not_run` + `NOT_RUN` — 값 슬롯은 `—`가 아니라 **글자 `미실행`**("모른다"는 "없다"보다 강하게 표시) |
| `violation` | ✕ | 화면 자기검사가 계약 위반을 발견했을 때 |
| (품질검사 전용) `vacuous`→`unconnected`류 | ○ | `checks[].status:"vacuous"` — "공허한 통과"(검사는 했으나 대상 0행). `✓`도 초록도 쓰지 않는다 |

### `표본 데이터` 배지

합성 입력(손으로 만든 이벤트, 테스트 픽스처)으로 렌더한 화면에만 붙는다. **배지가 말하는 것은 파이프라인이 아니라 입력이다** — 파이프라인(`publish()`)이 진짜여도 입력이 합성이면 배지가 붙는다. 실제 `results/`(빈 Sink를 포함해 진짜 데이터를 읽은 결과)에는 배지가 없다.

### 디자인 토큰 — 정본은 하나, 생성기는 두 벌

`Plan/DESIGN.md`(서브모듈, 두 저장소가 같은 커밋 참조)가 색·타이포·간격의 유일한 정본이다. 생성기 스크립트(`design-tokens.mjs` 등 4개 + `verify.mjs`) 자체는 `Ecommerce_Service`에서 **이식**한 코드 사본이다 — "코드 중복이지 값 중복이 아니다"(PRD §69가 금지하는 것은 값을 UI마다 새로 정의하는 것). `dashboard/scripts/tokens/verify.mjs`는 이식 시 상대경로 한 줄을 고쳐야 동작한다(원본 그대로 두면 `ENOENT`).

---

## 9. 자주 헷갈리는 이름 쌍 — 의도적으로 나뉜 것들

| 쌍 | 차이 | 근거 |
|---|---|---|
| `churn_rate` vs `churn_label` | 전자는 **운영 상태·후향**(대시보드 표시용, `days_since_last_purchase ≥ 42`), 후자는 **모델 라벨·전향**(`(T0, T0+42]`에 구매 0건). 섞으면 Feature가 라벨을 결정해 AUC가 허수로 나온다(PRD Risk 7) | `kpi.py:513-544, 829-874` |
| `retention_rate` vs `cohort_retention_rate` | 전자는 상태·시점 기준(`1 − churn_rate`), 후자는 가입 코호트의 M개월차 잔존율(`signup_date` 필요 → C1은 `customers` 테이블 미구현으로 `unavailable`. `design-vs-impl-gaps.md` §5 참조) | `kpi.py:547-596` |
| `average_order_value`(분모=주문 건수) vs `revenue_per_customer`(분모=고객 수, 미정의) | 같은 "평균 매출"이라도 분모가 다르면 다른 지표. 이름을 분리해 "같은 이름의 다른 계산"(이슈 `#46` 완료 조건)을 막는다 | `kpi.py:777-824` |
| `expected_cost_per_customer`(계획값) vs `realized_cost_per_customer`(실현값) | 전자는 쿠폰 사용률 가정치를 쓴 예산 계획, 후자는 실제 발생 이벤트 집계. 계획값을 실현 비용 집계에 쓰지 않는다(EC-5) | `economics.py:436-516` |
| `blocked` vs `not_run` | 전자는 "환경 제약으로 **못 했다**"(선언된 실행 불가), 후자는 "**안 했다**"(아무도 선언하지 않은 공백). 섞으면 "실행 안 한 것"이 "환경 탓"으로 읽힌다 | `schema.py:471-483` |
| `link_state`(2값: `never_connected`/`connected`) vs `staleness`(별도 `metric_value`) | "연결된 적 있는가"는 2값으로 결정 가능하지만, "지금 멈췄는가(stale)"는 임계값 미확정이라 C1에서 판정 불가 — enum에 넣는 대신 `not_run`+사유로 값 자체를 준다 | `ingestion_report.schema.json` |
| `unit_cost: null` vs `unit_cost: 0` | 전자는 "원가를 모른다", 후자는 "원가가 실제로 0원(사은품 등)". `0`으로 채우면 기여이익이 매출과 같아진다 | `docs/measurement_contract.md` §4 |

---

## 10. 용어집 (가나다순)

| 용어 | 정의 |
|---|---|
| `basis` | 계산에 쓰인 기준(모집단·분모·기간·관측건수). 계산됨에는 필수, 계산 불가에는 금지 — 이 유무로 "측정된 0"과 "값 없음"을 가른다 |
| `blocked_by` | 이 지표가 계산 불가인 원인 목록(양방향 사슬의 역방향) |
| `contract_version` | 게시 계약 버전 문자열(`"measurement-publish/v1"`). 다르면 렌더링하지 않는다 |
| `derived` | 저장된 사실이 아니라 규칙에서 유도한 값. `derivation`(계산식 문장) 동반 필수 |
| `EventSink` | 이벤트를 파티션(`date=YYYY-MM-DD`)에 저장하는 모듈(`sink.py`). `strict` 모드로 엄격/관용 전환 |
| `event_source` | 이벤트가 커머스 실측인지 시뮬레이터 생성인지. 별도 컬럼 없이 `simulator_version`·`random_seed`의 null 여부로 파생 |
| `GATE 1` | 측정 계약(스키마·경제규칙·이탈정의·KPI정의)을 봉인하는 지점. 봉인 이후 변경은 `FREEZE-003` |
| `MEA-002` | "실험 결과 산출에는 시뮬레이터 생성분만 쓴다"는 SRS 규칙. 출처를 섞으면 처치/통제 배정이 성립하지 않는다 |
| `MEA-003` | "누락 필드를 0이나 기본값으로 조용히 채우지 않는다"는 SRS 규칙 |
| `MetricValue` | 지표 하나의 값 또는 계산 불가 상태를 표현하는 dataclass. USP-1의 기계 표현 |
| `notices` | 게시물에 상시 표시되는 명시 가정·한계 목록 (예: `REFUND_NOT_ADJUSTED`) |
| `NOT_APPLICABLE` | 이벤트 타입별로 값을 가질 수 없는 필드. 값이 있으면 거부된다(화이트리스트가 부재로 동작) |
| `run_id` | 한 게시 실행을 식별하는 키. 같은 실행의 산출물 7종이 공유한다 |
| `unconfirmed` | 값은 있지만 계산에 쓴 파라미터가 아직 확정되지 않은 상태(`params_used` 동반) |
| `verify_core_invariants` | 게시 직전 런타임 자기검증 함수. 7개 핵심 불변식만 본다(전체 스키마 검증의 대체가 아니다) |
| `표본 데이터 배지` | 합성 입력으로 렌더된 화면에 붙는 표시. 파이프라인이 아니라 입력의 성격을 말한다 |

---

## 11. 더 읽을 것

| 주제 | 문서 |
|---|---|
| 게시 계약 API 전문 | `.agent-team/09-docs/measurement-publish-api-v1.md` |
| 설계-구현 불일치 전수 | `.agent-team/09-docs/design-vs-impl-gaps.md` |
| 아키텍처 결정 근거 | `.agent-team/04-architecture/adr/ADR-0001`~`ADR-0010` |
| 서비스 UI 담당자용 기록 계약 | `docs/measurement_contract.md` |
| GATE 1 절차 상세 | `docs/gate1_checklist.md` |
| KPI 정의 확정안 | `.agent-team/03-service-planning/kpi-definition-v1.md` |
| 경제 규칙 확정안 | `.agent-team/03-service-planning/economic-rule-v1.md` |
