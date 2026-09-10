# KPI 정의 v1 — 확정안 (T2.3 · M-4 / `#46` 입력)

**작성** Joshua (Role 3) · 2026-09-11 · 사이클 C1
**정본 근거** PRD §66 · `docs/data_spec.html` §5 · §14 · SRS §24~25 · 이슈 `#46`
**검토 입력** `02-market-analysis/market-report.md` T1.10 (Caleb) · `01-reverse/measurement-map.md` §1.9 (John)
**지위** 이것은 **확정안**이다. Lock 여부·시점 판정은 `gate1-lock-scope.md`에 있다.

> **이 문서의 목적은 하나다 — 지표 이름 하나에 계산식·모집단·기간·분모가 1:1로 대응하게 만드는 것.**
> `#46` 완료 조건: *"같은 이름의 다른 계산을 막는다."*

---

# 1. Caleb의 조사 결과 검토 — 그대로 받지 않은 부분

| 조사 결과 | 내 판정 |
|---|---|
| **Primary / Guardrail / Secondary 3계층이 업계 정설** (Statsig · Mixpanel 출처 확인) | **수용.** PRD §66이 임의 발명이 아님이 교차검증됐다. §5의 구조를 그대로 쓴다 |
| **세션 타임아웃 30분이 GA4·PostHog 기본값과 정확히 일치** | **수용.** `SESSION_TIMEOUT_MINUTES = 30`(`schema.py:35`)을 바꿀 이유가 없다 |
| **그로서리 Churn 정의 4가지 관례 — 고정 윈도우가 30~60일 관행** | **수용.** ①고정 윈도우 **방식**을 C1에서 유지한다 |
| **"현행 42일 고정 윈도우를 GATE 1에서 그대로 유지(Lock)"** | **부분 기각.** 아래 §1.1 |
| **환불/취소 이벤트 부재가 기여이익 과대평가를 낳는다** | **수용.** 다만 KPI가 아니라 경제 규칙 문제다 → `economic-rule-v1.md` §6에서 판정 |
| **쿠폰 비종속 프로모션 클릭 이벤트 부재 (경미)** | **수용하되 C1 조치 없음.** `campaign_response_count`의 정밀도 한계로 §4에 기록 |

## 1.1 왜 "42일 Lock" 권고를 부분 기각하는가

Caleb의 권고: *"GATE 1 봉인 시점(C1)에는 현행 고정 42일 윈도우를 그대로 유지한다."*

**방식은 유지한다. 숫자는 Lock하지 않는다.** 근거 셋:

1. **정본이 확정 절차를 명시했고 그 절차가 실행되지 않았다.** `docs/data_spec.html` §5.1:
   > *"28일 / 42일은 현재 **가설값**이다(PRD §28은 [PROJECT-DECISION]·**미확정**으로 명시). GATE 1 이전에 다음 절차로 확정한다: ① Warm-up 구간(Day 0–272)의 고객별 구매 간격 분포 산출 → ② P75 / P90 분위수 → ③ `at_risk_days ≈ P75`, `churn_days ≈ P90` 근방 확인 → ④ 재생성 시 Generated Churn Rate 15~25%(SIM-005) 확인 → ⑤ 만족하면 `config/simulator_config.yaml`에 기록하고 GATE 1에서 Lock."*

   **①~④는 전부 시뮬레이터가 있어야 실행된다. C1에 시뮬레이터가 없다.** 절차를 건너뛰고 숫자를 Lock하면 *"미실행 검증을 통과로 표시하지 않는다"*(AGENTS.md)를 위반한다.

2. **Caleb 본인이 한계를 적었다** — *"42일이 '업계 관행'이지 '이 도메인에 최적'이라는 뜻은 아니다. PRD가 여러 페르소나를 전제하므로 고정 글로벌 윈도우는 구매 주기가 짧은 페르소나에는 너무 관대하고 긴 페르소나에는 너무 엄격할 수 있다."* 이 한계를 인지한 상태에서 되돌릴 수 없는 Lock을 거는 것은 정합적이지 않다.

3. **Lock 비용이 비대칭이다.** 지금 Lock하지 않는 비용 = 다음 사이클에 `simulator_config.yaml`에 값을 적는 일 한 번. 잘못 Lock한 비용 = **`FREEZE-003`에 따라 버전 상향 + 데이터 재생성 + Baseline부터 전 전략 재실행.**

**결론 — §7.1에서 Lock 대상을 이렇게 가른다:**

| Lock 한다 (C1) | Lock 하지 않는다 (다음 사이클) |
|---|---|
| **이탈 판정 방식** = 고정 윈도우 · `rule_operator: OR` 구조 | `at_risk_days` = 28 (가설값) |
| **운영 상태와 모델 라벨의 분리** (§6) | `no_purchase_days` = 42 (가설값) |
| **`label_window_days = 42`** — 운영 정의와 독립인 고정 상수 | `no_login_days` = 60 (가설값) |

`label_window_days`만 Lock하는 이유: `data_spec` §5는 이 값을 *"운영 정의가 바뀌어도 42일로 고정한다. 라벨 관찰기간이 바뀌면 Baseline과 AI 전략의 비교 기준이 달라져 Incremental Profit을 비교할 수 없다"* 고 **운영 임계값과 명시적으로 분리**했다. 확정 절차(§5.1)의 대상이 아니다.

---

# 2. 공통 규약 — 모든 지표에 적용

이 규약을 어기는 지표 정의는 v1에 포함하지 않는다.

## 2.1 시간 파라미터

| 기호 | 이름 | 의미 | 기본값 |
|---|---|---|---|
| `D` | 기준일 (index date) | 지표를 평가하는 시점. 실험 맥락에서는 `T0` | 명시 필수 — 기본값 없음 |
| `W` | 관찰기간 | `D` 이후를 보는 지표의 창 길이 | **42일** (`label_window_days`) |
| `L` | 회고기간 | `D` 이전을 보는 지표의 창 길이 | **42일** — 지표별로 다르면 이름에 명시 |

**규칙 R-1** 모든 지표는 `D`를 인자로 받는다. **"현재"라는 암묵 기준일을 쓰지 않는다.**
**규칙 R-2** `D` 이후를 보는 지표(전향적)와 `D` 이전을 보는 지표(후향적)를 **같은 이름으로 쓰지 않는다.**
**규칙 R-3** 모든 시각 비교는 **KST 단일 타임존**에서 한다(`schema.py:29-33`). 이것이 강제되지 않는 것이 `#53` D1-3이다 — **`#53` 수정 전에 산출한 KPI 값은 하루 어긋날 수 있다.**

## 2.2 모집단

| 기호 | 이름 | 정의 |
|---|---|---|
| `P_all(D)` | 전체 고객 | `signup_date ≤ D` |
| `P_buyer(D)` | 구매 이력 보유 | `P_all(D)` ∧ `lifetime_order_count(D) ≥ 1` |
| `P_eligible(D)` | 캠페인 대상 | `data_spec` §4.1 — `(D − signup_date ≥ 60일)` ∧ `(lifetime_order_count ≥ 1)` ∧ `(days_since_last_purchase ≥ 14일)` |

**규칙 R-4** 모든 지표는 위 셋 중 하나를 명시한다. **"고객"이라고만 쓰지 않는다.**
**규칙 R-5** `P_eligible`로 필터링한 결과에는 항상 `eligible_flag` 조건을 함께 보고한다(`data_spec` §4.1: *"모든 분석에서 필터 조건을 명시적으로 남긴다"*).
**규칙 R-6** **분모에서 제외한 고객 수를 값과 함께 보고한다.** 예: `purchase_interval`은 구매 2건 미만 고객이 정의되지 않으므로 제외하고, 제외 인원을 함께 낸다. 제외를 조용히 하지 않는다.

## 2.3 출처 규칙 (`MEA-002`)

| 지표 계층 | 커머스 실측분 | 시뮬레이터 생성분 |
|---|---|---|
| 수집 건전성 (§3) | **포함** — 출처별로 갈라서 보고 | **포함** |
| Customer KPI (§4) | **포함** — 단 출처를 섞지 않고 **각각 산출** | **포함** |
| Business KPI (§5) | **원가 근거가 있을 때만** (→ `economic-rule-v1.md` §3) | **포함** |
| 실험 판정 지표 (§5.3) | **제외** — `MEA-002`: *"실험 결과 산출에는 시뮬레이터 생성분만 사용한다"* | **포함** |

**규칙 R-7** 두 출처를 합산한 값을 기본 표시로 쓰지 않는다. 합산이 필요하면 **합산임을 이름에 표시**한다(`*_combined`).
근거: 출처를 섞으면 처치·통제 배정이 성립하지 않는다(`MEA-002`).

## 2.4 계산 불가 규칙 (`MEA-003` · PRD §10.1 · charter 절대제약 6)

**규칙 R-8** 근거 이벤트가 0건이거나 필수 필드가 결손이면 **값을 내지 않고 계산 불가로 표시한다.** `0`을 반환하지 않는다.
**규칙 R-9** 계산 불가에는 **사유 코드**가 붙는다.

| 사유 코드 | 의미 |
|---|---|
| `NO_SOURCE_EVENT` | 근거 이벤트가 한 건도 없다 (`sink.unavailable_metrics()`) |
| `MISSING_FIELD` | 필수 필드가 결손이다 |
| `NO_COST_BASIS` | 원가 근거가 없어 COGS 계열을 계산할 수 없다 |
| `NEEDS_TWO_STRATEGIES` | 비교 대상 전략이 없다 (Incremental 계열) |
| `NEEDS_MODEL_OUTPUT` | 모델 산출물이 없다 (AUC·Qini·CLV 계열) |
| `PARAM_UNCONFIRMED` | 계산은 되나 파라미터가 미확정이다 (이탈 임계값) |
| `BLOCKED` | 환경 제약으로 실행하지 못했다 (예: pyarrow 미설치) |

**규칙 R-10** `PARAM_UNCONFIRMED` 지표는 **값을 내되 사용한 파라미터를 값과 함께 표시한다.** 숨기지 않고, 확정된 것처럼도 쓰지 않는다.

## 2.5 신뢰구간

**규칙 R-11** 실험 판정 지표(§5.3)는 **95% CI를 동반 보고**한다. **고객 단위 Bootstrap, B = 2,000**(`data_spec` §14 · `#46`).
**규칙 R-12** 표본 부족으로 CI가 산출되지 않으면 "0"이나 "유의하지 않음"이 아니라 **`미결정(inconclusive)`** 으로 표시한다 — `market-report.md` T1.9가 확인한 A/B 대시보드 관례. *"표본 부족과 실제 효과 없음을 구분해야 한다."*

---

# 3. 계층 0 — 수집 건전성 지표 *(C1 신설 · 전부 계산 가능)*

PRD §66에는 없다. **charter §3.1③과 §7.1(1차 독자 = 이 팀)이 요구하는 것**이며, 원천은 이미 구현된 `manifest.json`(`sink.py:220-245`)이다.
**대시보드 V1·V2·V3의 데이터가 전부 이 계층이다.**

| 지표 | 계산식 | 모집단·기간 | 분모 | 원천 | C1 |
|---|---|---|---|---|---|
| `events_ingested` | 저장된 이벤트 수 | 파티션 전 구간 | — (count) | `manifest.rows` | ✅ |
| `events_rejected` | 거부된 이벤트 수 | 동일 | — (count) | `manifest.rejected` | ✅ |
| `rejection_rate` | `events_rejected / (events_ingested + events_rejected)` | 동일 | 시도 건수 | manifest | ✅ |
| `rejection_reason_count[r]` | 사유 `r`별 거부 건수 | 동일 | — | `rejected.jsonl` | ✅ |
| `event_type_coverage` | 1건 이상 발생한 `event_type` 종수 / **16** | 동일 | 16 (고정) | `manifest.event_type_counts` | ✅ |
| `event_type_count[e]` | 타입 `e`의 건수 | 동일 | — | 동일 | ✅ |
| `field_fill_rate[f]` | `present(f) / applicable(f)` — **`NOT_APPLICABLE`은 분모에서 제외** | 동일 | 해당 필드가 적용되는 이벤트 수 | `manifest.field_coverage` (`sink.py:88-97`) | ✅ |
| `missing_field_count` | 적용 대상인데 한 건도 없는 필드 수 | 동일 | — | `manifest.missing_fields` | ✅ |
| `unavailable_metric_count` | 계산 불가 Observable 지표 수 | 동일 | 16 | `sink.unavailable_metrics()` | ✅ |
| `source_event_count[s]` | 출처 `s`(commerce/simulator)별 건수 | 동일 | — | `manifest.sources` (`sink.py:79-83`) | ✅ |
| `partition_day_count` | 데이터가 존재하는 날짜 수 | 동일 | — | 파티션 디렉터리 | ✅ |
| `ingestion_days_gap` | 파티션 구간 내 **이벤트가 0건인 날짜 수** | 동일 | — | 파티션 목록 | ✅ |

**`ingestion_days_gap`을 넣은 이유:** 수집이 **멈춘 것**과 **그날 활동이 없던 것**을 화면에서 구분해야 한다. 0으로 채우면 둘이 같아 보인다 — USP-1이 막으려는 바로 그 상황이다.

> **주의 — 이 계층은 KPI가 아니다.** 서비스 성과가 아니라 **계약 준수 상태**를 잰다. 실험 판정에 쓰지 않는다.

---

# 4. 계층 1 — Customer KPI (PRD §66.2)

**전부 `purchase`·`session_start`·`return_visit` 이벤트만으로 계산된다. 원가·모델 산출물이 필요 없다.**

| 지표 | 계산식 | 모집단 | 기간 | 분모 | C1 |
|---|---|---|---|---|---|
| `churn_rate` | `\|{c : days_since_last_purchase(c,D) ≥ no_purchase_days}\| / \|P_buyer(D)\|` | `P_buyer(D)` | **시점 `D`** (후향적) | 구매 이력 보유 고객 수 | ⚠️ `PARAM_UNCONFIRMED` |
| `retention_rate` | `1 − churn_rate` — **동일 모집단·동일 시점의 파생값** | `P_buyer(D)` | 시점 `D` | 동일 | ⚠️ 동일 |
| `cohort_retention_rate[m]` | 가입 코호트 `m`개월차에 구매 ≥1건인 고객 / 해당 코호트 전체 | 가입월 코호트 | `M1/M3/M6/M12` | 코호트 인원 | ✅ |
| `repurchase_rate` | `\|{c : purchase_count(c, [D−L, D]) ≥ 2}\| / \|{c : purchase_count(c, [D−L, D]) ≥ 1}\|` | `P_all(D)` | 회고 `L` = 42일 | **기간 내 1회 이상 구매 고객** | ✅ |
| `winback_rate` | `\|{c : state(c, D−L) = churn ∧ purchase ∈ (D−L, D]}\| / \|{c : state(c, D−L) = churn}\|` | `P_buyer(D−L)` | `(D−L, D]` | `D−L` 시점 이탈 고객 수 | ⚠️ `PARAM_UNCONFIRMED` |
| `purchase_frequency` | `Σ purchase 건수 / \|P\|` | **`P_buyer(D)`** | 회고 `L` = 42일 | 고객 수 | ✅ |
| `purchase_interval` | 고객별 연속 `purchase` 간 일수의 **중앙값**을 구한 뒤, 그 값들의 **모집단 중앙값** | `P_buyer(D)` ∧ 구매 ≥ 2건 | 회고 `L` | 정의되는 고객 수 (**제외 인원 병기 — R-6**) | ✅ |
| `average_order_value` | `Σ order_amount / count(purchase)` | `P_buyer(D)` | 회고 `L` | **주문 건수** (고객 수 아님) | ✅ |

## 4.1 이름 충돌을 명시적으로 끊은 지점

`#46`이 경계한 *"같은 이름의 다른 계산"* 이 실제로 발생할 자리 셋을 미리 갈랐다.

| 충돌 지점 | 갈라놓은 방법 |
|---|---|
| **Retention** — PRD §66.2의 상태 기준 vs `DB-004`의 코호트 잔존율 | `retention_rate`(상태·시점) / `cohort_retention_rate[m]`(코호트·M1·M3·M6·M12). **이름이 다르다** |
| **Churn** — 운영 상태(후향적) vs 모델 라벨(전향적) | `churn_rate`(운영 상태) / `churn_label`(모델 라벨). **§6에서 분리 근거** |
| **AOV 분모** — 주문 건수 vs 고객 수 | `average_order_value`는 **주문 건수**가 분모. 고객당 매출이 필요하면 `revenue_per_customer`라는 **별도 이름**을 쓴다 |

## 4.2 `campaign_response_count`의 정밀도 한계 (Caleb 지적 반영)

`schema.py:341`은 `campaign_response_count`를 `campaign_exposed` · `coupon_clicked` · `purchase`로 계산한다.
**쿠폰이 없는 캠페인(배너·푸시)의 클릭을 담을 이벤트가 없다** — `coupon_clicked`는 쿠폰을 전제한다(`market-report.md` T1.8).
→ **쿠폰 비종속 캠페인의 반응률은 이 지표로 측정되지 않는다.** C1에서 이벤트를 추가하지 않고, **이 한계를 `docs/measurement_contract.md`(M-3)에 명시한다.**

---

# 5. 계층 2 — Business KPI (PRD §66.3)

계산식 정본은 `docs/data_spec.html` §6.3이며, 확정안은 `economic-rule-v1.md`에 있다. 여기서는 **이름 ↔ 계산 가능성**만 고정한다.

## 5.1 원가 근거가 필요 없는 것 — C1 계산 가능

| 지표 | 계산식 | 모집단 | 기간 | 분모 | C1 |
|---|---|---|---|---|---|
| `revenue` | `Σ order_amount` | 명시 | 명시 | — (합계) | ✅ |
| `coupon_cost` | `Σ discount` (`coupon_use` 발생 주문) | 명시 | 명시 | — | ✅ (이벤트 있을 때) |
| `message_cost` | `발송 건수 × 30원` (`push_sent` 기준, **반응 무관 전원**) | 처치군 | 명시 | — | ✅ (이벤트 있을 때) |
| `campaign_fixed_cost` | `100,000원 × 캠페인 수` | — | 명시 | — | ✅ |
| `shipping_subsidy` | `Σ 면제된 배송비` | 명시 | 명시 | — | ⚠️ `MISSING_FIELD` — 배송비 필드가 스키마에 없다(§5.4) |
| `marketing_cost` | `message_cost + coupon_cost + campaign_fixed_cost` | 처치군 | 명시 | — | ✅ (구성요소가 있을 때) |

## 5.2 원가 근거가 필요한 것 — 조건부

| 지표 | 계산식 | C1 |
|---|---|---|
| `cogs` | `Σ (unit_cost × quantity)` | ⚠️ **원가 근거 보유분만.** 없으면 `NO_COST_BASIS` |
| `contribution_profit` | `revenue − cogs − coupon_cost − shipping_subsidy − message_cost − campaign_fixed_cost / N_targeted` | ⚠️ 동일 |

**`cogs`를 `revenue × 원가율`로 추정하지 않는다.** 근거와 판정은 `economic-rule-v1.md` §3.2 — **이 문서에서 가장 중요한 한 줄이다.**

## 5.3 두 전략 또는 모델 산출물이 필요한 것 — **C1 계산 불가**

| 지표 | 사유 코드 |
|---|---|
| `incremental_revenue` · `incremental_contribution_profit` | `NEEDS_TWO_STRATEGIES` |
| `roi` · `ai_roi` · `ai_net_incremental_value` | `NEEDS_TWO_STRATEGIES` |
| `qini_coefficient` · `auuc` · `uplift_by_decile` · `persuadables_ratio` | `NEEDS_MODEL_OUTPUT` |
| `churn_test_auc` · `precision` · `recall` · `f1` | `NEEDS_MODEL_OUTPUT` |
| `predicted_clv` · `clv_mape` · `top20_precision` | `NEEDS_MODEL_OUTPUT` |
| `pehe` · `corr(τ̂, τ)` | `NEEDS_MODEL_OUTPUT` + `src/diagnostics/` 전용 |

**이 지표들의 정의는 v1에 포함한다. 계산은 이후 사이클이다.**
정의를 지금 고정하는 이유: `#46`이 *"실험 결과를 본 뒤 유리한 지표를 고르는 것은 결과 조작"* 이라고 못박았다. **정의는 결과보다 먼저 있어야 한다.**

## 5.4 스키마 공백 — `shipping_subsidy`를 계산할 필드가 없다 *(새 발견)*

`docs/data_spec.html` §6.3의 기여이익식은 `shipping_subsidy_i`를 뺀다. `config`에는 배송비 3,000원·무료배송 기준 40,000원이 있다(§6.2 T1).
그런데 **DATA-003 22개 컬럼 어디에도 배송비·배송보조 필드가 없다**(`schema.py:101-137` · `event_schema.md` 매트릭스 실측).

| 결과 | |
|---|---|
| **시뮬레이터 생성분** | T1 처치 배정 정보(`treatment_id = T1`)와 `order_amount`로 **재구성 가능** — `order_amount < 40,000` ∧ `treatment_id = T1` → 3,000원. 계산은 되지만 **저장된 사실이 아니라 규칙에서 유도한 값**이다 |
| **커머스 실측분** | `Ecommerce_Service`가 `shippingKrw = 0` 하드코딩(`purchase.ts:41`)이고 주문에 배송비를 저장하지 않는다(`ECOM-E9` / `Ecommerce #33`) → **`MISSING_FIELD`** |

→ **판정:** C1에서 `shipping_subsidy`는 **규칙 유도값**으로 정의하고, **유도했다는 사실을 산출물에 표시**한다(`derived: true`). 저장된 값과 구분되지 않으면 안 된다.
→ **DATA-003에 배송비 필드를 추가하는 것은 SRS 변경**이므로 이 팀의 권한 밖이다. **사용자 결정 항목 D-3**(§9)으로 올린다.

---

# 6. 이탈 정의 — 운영 상태와 모델 라벨을 분리한다

`docs/data_spec.html` §5가 이미 분리했고, **C1은 이 분리를 KPI 이름 수준까지 강제한다.**

## 6.1 ① 운영 상태 (Derived State · 후향적)

```
Active   : 마지막 구매 후 ≤ 27일
At Risk  : 마지막 구매 후 28 ~ 41일
Churn    : 마지막 구매 후 ≥ 42일
```

- 용도: **대시보드 표시 · 코호트 분석 · Rule-based Baseline 조건**
- `churn_rate`·`retention_rate`·`winback_rate`가 이 정의를 쓴다
- 임계값 28/42/60은 **가설값이며 C1에서 Lock하지 않는다**(§1.1)

## 6.2 ② 모델 라벨 (Prediction Target · 전향적)

```
churn_label_i = 1  if  count(purchase | T0 < t ≤ T0 + 42) == 0
                0  otherwise
retained_i    = 1 − churn_label_i
```

- `label_window_days = 42`는 **운영 정의와 독립인 고정 상수** — C1에서 Lock한다
- 용도: **모델 학습 라벨 전용.** 대시보드 상태 표시에 쓰지 않는다

## 6.3 왜 분리가 KPI 정의의 문제인가

`data_spec` §5: 운영 상태를 그대로 라벨로 쓰면 `days_since_last_purchase ≥ 42`라는 Feature가 라벨을 거의 완전히 결정한다. **AUC 0.99가 나오지만 학습된 것은 아무것도 없다**(PRD Risk 7 Churn Label Leakage).

**측정 계층이 이 분리를 지킨 증거가 이미 코드에 있다** — `DerivedStateType`(`schema.py:66-76`)이 `EventType` 16종과 교집합이 없고, `FEATURE_FORBIDDEN_EVENT_TYPES`로 Feature 사용 금지를 표시하며, `tests/test_schema.py:188-196`이 **Observable 지표가 파생 상태에 의존하면 실패**시킨다.

> **미해결 — W1 D-7:** `DerivedStateType`이 `EventType` 밖에 있어 **Sink에 기록할 수단 자체가 없다.** PRD §30.2·`data_spec` §7.3은 *"기록은 하되 Feature 금지"* 를 요구한다. 기록 경로가 설계되지 않았다.
> → **M-6(`#48`) 또는 M-3(`#45`)에서 결정해야 한다.** 이 문서는 "파생 상태를 KPI 계산에 쓰지 않는다"까지만 확정한다.

---

# 7. 실험 판정 지표 — Primary / Guardrail / Secondary

**정의만 확정한다. C1에서 계산하지 않는다.** 3계층 구조는 `market-report.md` T1.10이 업계 정설로 교차검증했다.

## 7.1 Primary — 2개 고정 (`data_spec` §14)

| # | 지표 | 기준 | 모집단 | 기간 | 비교 대상 |
|---|---|---|---|---|---|
| **P1** | `incremental_contribution_profit` = `CP_strategy − CP_S1_rule` | **> 0, 95% CI 하한 > 0** | **Test 20%** (최종 1회 Final Holdout) | `T0+1 ~ T0+42` | Rule-based Baseline S1 |
| **P2** | `qini_coefficient` | **> 0, Random 대비 유의** | Test 고객의 무작위 T/C | 동일 | Random 정책 (Qini = 0) |

- 단위: **원 · 고객 1인당 원** 둘 다 보고
- **95% CI (Bootstrap B = 2,000, 고객 단위) 동반 보고 필수** — R-11
- P2는 **Ground-truth 기반 `Qini_oracle` 대비 달성률 병기** (`src/diagnostics/` 전용, 사후 진단)

## 7.2 Guardrail — 4개

| 지표 | 임계 | 위반 시 |
|---|---|---|
| `churn_test_auc` | **≥ 0.78** (`ML-004`) | **전략 비교 진행 불가** |
| `marketing_cost` | **≤ C_rule** | 예산 위반 차단 |
| `sleeping_dog_targeting_rate` | Random 대비 **유의하게 낮음** | 역효과 고객 회피 실패 |
| `revenue_up_profit_down` (패턴) | 발생 시 **실패로 판정** | PRD §65 해석 규칙 |

**`revenue_up_profit_down`은 값이 아니라 판정 규칙이다** — `revenue` 증가 ∧ `contribution_profit` 감소이면 참. **`#47` 완료 조건에 이 규칙의 구현이 들어 있다.**

> **`C_rule`(Rule-based 실집행 비용)과 예산 상한 `B`는 C1에서 정할 수 없다.** `data_spec` §15.3이 **GATE 2 확정 항목**으로 지정했다. `PARAM_UNCONFIRMED`.

## 7.3 Secondary — Primary 판정을 뒤집지 않는다

`auuc` · `uplift_by_decile` · `pehe` · `corr(τ̂, τ)` · `clv_mape` · `top20_precision` · `retention_rate` · `repurchase_rate` · `ai_roi`

**규칙 R-13** Secondary는 **단독으로 실험을 중단시키지 않고 Primary 판정을 뒤집지 않는다**(`market-report.md` T1.10 · Mixpanel 출처). 역할은 **Primary가 왜 움직였는지 설명**하는 것뿐이다.
**규칙 R-14** 리포트는 **Primary 2개를 반드시 먼저 제시한 뒤** 나머지를 서술한다(`data_spec` §14).

## 7.4 ⚠ 정본 충돌 — KPI를 GATE 1에서 Lock하는가 GATE 2에서 하는가

| 정본 | 내용 |
|---|---|
| **PRD §22** | GATE 1 Lock 목록에 **`KPI DEFINITION v1 LOCK`** 이 있다 |
| **`data_spec` §14** | *"위 표는 **GATE 2에서 Lock**하고, 이후 지표 추가는 가능하되 Primary 교체는 불가하다"* |
| **`data_spec` §15.3** | GATE 1 확정 항목: Persona·Hidden Trait·행동 규칙·Churn 임계값·Treatment 반응 규칙·**경제 파라미터·Event Schema**. **KPI가 없다** |
| **`#46` 배경** | *"GATE 2에서 Lock한다"* |

**두 정본이 어긋난다. `Plan/` 수정은 이 팀의 권한 밖이므로 고치지 않고, 충돌하지 않는 해석을 확정안으로 제시한다.**

> ### 확정안 — Lock을 두 층으로 분해한다
>
> | Lock 층 | 무엇 | 시점 | 근거 |
> |---|---|---|---|
> | **계산 계약** — 지표 이름 ↔ 계산식·모집단·기간·분모의 1:1 대응 (§2~§6) | **GATE 1** | PRD §22 `KPI DEFINITION v1` |
> | **판정 역할 배정** — 어느 지표가 Primary인가 · 임계값 `C_rule`·`B` | **GATE 2** | `data_spec` §14·§15.3 |
>
> **이 분해는 두 정본을 모두 만족한다.** GATE 1은 *"같은 이름의 다른 계산"* 을 막고, GATE 2는 *"결과를 본 뒤 유리한 지표를 고르는 것"* 을 막는다. **막으려는 대상이 서로 다르므로 두 Lock은 충돌하지 않는다.**

**이것은 해석이다. 사용자가 다르게 판단하면 그쪽을 따른다** → 결정 항목 **D-4**(§9).

---

# 8. C1 계산 가능/불가 — 한 표

**대시보드 V4가 이 표를 그대로 화면에 옮긴 것이다.**

| 계층 | 지표 수 | C1 계산 가능 | 조건부 | 계산 불가 |
|---|---|---|---|---|
| 계층 0 수집 건전성 | 12 | **12** | 0 | 0 |
| 계층 1 Customer KPI | 8 | 5 | **3** (`PARAM_UNCONFIRMED`) | 0 |
| 계층 2 Business KPI | 12 | 5 | **3** (`NO_COST_BASIS`·`MISSING_FIELD`) | **4** |
| 실험 판정 지표 | 15 | 0 | 0 | **15** |
| **합계** | **47** | **22** | **6** | **19** |

**단, "계산 가능"은 근거 이벤트가 있을 때다.** 2026-09-11 현재 **커머스는 이벤트를 한 건도 기록하지 않고**(`Ecommerce #28` 미착수) 시뮬레이터도 없다.
→ **오늘 실제로 값이 나오는 지표는 계층 0의 일부뿐이며, 나머지는 전부 `NO_SOURCE_EVENT`다.**
빈 Sink가 Observable 16개 전부를 계산 불가로 표시하는 것이 이미 코드로 증명되어 있다(`tests/test_sink.py:198-203`).

> **이것을 숨기지 않는 것이 USP-1이다.** 대시보드가 처음 켜졌을 때 화면이 계산 불가로 가득한 것은 **버그가 아니라 정상 동작**이다.

---

# 9. 사용자 결정이 필요한 항목

| # | 항목 | 선택지 | 추천 |
|---|---|---|---|
| **D-3** | **`shipping_subsidy` 필드 부재** (§5.4) — DATA-003 22컬럼에 배송비가 없다 | ⑴ 규칙 유도값으로 계산하고 `derived: true` 표시 ⑵ `Plan/` SRS DATA-003에 필드 추가 후 Lock | **⑴.** SRS 변경은 권한 밖이고, 시뮬레이터 생성분에서는 규칙 유도가 정확하다. 커머스 실측분은 `MISSING_FIELD` |
| **D-4** | **KPI Lock 시점 정본 충돌** (§7.4) | ⑴ 계산 계약=GATE 1 / 역할 배정=GATE 2로 분해 ⑵ 전부 GATE 1 ⑶ 전부 GATE 2 | **⑴.** 두 정본을 모두 만족하는 유일한 해석 |
| **D-5** | **이탈 임계값(28/42/60)을 C1에서 Lock할 것인가** (§1.1) | ⑴ Lock하지 않고 방식만 Lock ⑵ Caleb 권고대로 42일 Lock | **⑴.** `data_spec` §5.1 확정 절차가 미실행이고 시뮬레이터 없이는 실행 불가 |

---

# 10. 미정으로 남긴 것

| 항목 | 왜 미정인가 |
|---|---|
| `at_risk_days` · `no_purchase_days` · `no_login_days` 확정값 | `data_spec` §5.1 절차가 시뮬레이터를 요구한다. **C1에서 판정 불가 — 범위 밖이 아니라 선후 관계상 불가능** |
| `C_rule` (Rule-based 실집행 비용) · 예산 상한 `B` | `data_spec` §15.3 — **GATE 2 확정 항목** |
| AI Investment Cost 최종값 | 초안은 `data_spec` §6.4에 있다. 확정은 `economic-rule-v1.md` §5 |
| 파생 상태(`inactive`/`at_risk`/`churn`)의 **기록 경로** | W1 D-7. `#48`(M-6) 또는 `#45`(M-3)에서 설계 필요 |
| `kpi.py`의 함수 시그니처·모듈 배치 | **James T2.6 소관**(측정 계층 내 배치·창구 중립성). 이 문서는 계약만 정한다 |
| Bootstrap 재현 seed 규약 | `#48` 재현성 검사와 함께 정하는 편이 자연스럽다 |
