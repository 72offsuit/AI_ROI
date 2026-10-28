# DR-169-measured-contribution-profit — 증분이익은 측정 계층 실측 기여이익으로만, 결손이면 계산 불가

| | |
|---|---|
| 태스크 | 이슈 #169 (출처 #156 · #150 사후 리뷰 PR #156 P1) · 관련 DR-145 · DR-101 · DR-108 · DR-117 |
| 작성 | 인성(`Danto7632`, 시스템 팀 리드 — 에이전트 구현) · 2026-10-23 |
| 상태 | 제안 — 리뷰(`kwung0206`) 후 확정. DR-145 의 「통합 계약」 중 `summarize_strategy` 대체 계산 한 줄을 **번복**한다 |

## 무엇을 정하는가

1. 전략 비교의 증분이익(ROI-003 · PRD §63)이 쓰는 **기여이익을 어디서 얻는가.**
2. 기여이익이 결손일 때 정식 증분이익 · 증분 ROI · AI ROI 를 어떻게 내고, `Δ(매출 − 마케팅비)` 대체값을 **어디에** 두는가.
3. 매출↑/이익↓ 가드레일(ROI-006 · PRD §65)을 판정할 수 없을 때 무엇으로 표시하는가.

## 정하지 않으면 무엇이 막히나

- 20K 실측 실행(`results/sprint-v0/SP-20261022-20k/strategy_comparison.json`)의 S0~S5 **6행 전부**가 대체 계산이었다(`incremental_profit_basis = fallback:revenue_minus_marketing_cost(revenue_krw−planned_treatment_cost_krw)`). S4 의 "증분이익 +157,906,270원" 은 COGS 를 빼지 않은 값이 정식 칸에 실린 것이다.
- 그 실행에서 ROI 가 `계산 불가` 였던 것은 우연이다 — 분모가 계획 비용이고 S2~S5 예산이 C_rule 과 같아 Δ ≤ 0 이었다. 분모가 양수인 입력이면 대체값으로 `roi_status = "ok"` · `ai_roi_status = "ok"` 가 나간다(기존 테스트 `test_revenue_fallback_is_flagged` 가 그 경로다: 대체값 60 · 분모 40 → ROI 1.5).
- 대체 계산의 발동 범위가 DR-145 가 적은 "양쪽에 없으면" 보다 넓다. 한쪽만 결손이거나 키 이름이 달라도 `_paired` 가 공통 키를 못 찾아 대체로 떨어진다.
- 매출↑/이익↓ 가드레일은 공통 기여이익 차이가 없으면 **플래그를 붙이지 않는다** — "발동 안 함" 과 "판정 못 함" 이 같은 빈 목록이다.
- GATE 2 정식 봉인(#170) 전에 ROI 정의가 서야 하고, 대시보드 전략 화면(#177)이 이 필드를 읽는다.

## 선택지

| 안 | 내용 | 장점 | 단점 |
|---|---|---|---|
| A | 분기마다 `sim.exchange_bundle` 로 그 분기의 교환 묶음을 받고, 측정 계층 `publish.build_kpi_report` 의 `contribution_profit`(교환 묶음 COGS)을 정식 증분이익에 쓴다. 결손 · 기준 불일치면 **계산 불가**, 대체값은 별도 필드 · 별도 상태 | 측정 계층이 게시하는 값과 같은 함수 · 같은 조립. COGS 가 저장된 `unit_cost` 에서 온다(EC-1) | 오케스트레이션에 분기별 측정 단계가 하나 는다. 분기 출력 루트 위치가 바뀐다 |
| B | 현행 유지 — 대체값을 증분이익 칸에 두고 플래그만 붙인다 | 변경 없음 | 정식 칸에 과대평가값. 숫자를 읽는 쪽(대시보드 막대 · ROI · AI ROI)이 플래그를 보지 않으면 그대로 쓴다 |
| C | 기여이익이 없으면 매출 × 가중 마진율(0.26)로 COGS 를 추정 | 언제나 숫자가 나온다 | `economic_config.yaml` 이 그 블록을 생성 파라미터로만 두고 비율 곱을 EC-1 위반으로 명시한다. 기여이익이 매출의 상수배가 되어 매출↑/이익↓ 가드레일이 원리적으로 발동할 수 없다 |
| D | 분기마다 측정 계층 `publish()` 전체를 돌려 `kpi_report.json` 을 읽는다 | 게시물 그대로다(DQ 검사 포함) | 분기 1.4M 이벤트(20K 실행)를 dict 로 전량 적재 · 필드 충족률 · DQ 전부를 분기 6번 — 시간과 메모리. DQ-09 는 묶음(계보 전량)과 분기 창 이벤트를 대조하면 창 이전 주문이 전부 "purchase 없음" 위반으로 나온다 |
| E | 시뮬레이터 팀이 `sim.metrics` 의 비즈니스 지표를 채울 때까지 기다린다 | 오케스트레이션 변경 없음 | `docs/simulator_api.md` 가 그 지표를 "측정 계층(`publish`)이 계산한다" 고 적는다 — 계산 주체가 우리 쪽 측정 호출이다. 기다리는 동안 대체값이 계속 게시된다 |

A 안 안의 세부 선택:

| 세부 | 택함 | 대안 |
|---|---|---|
| 묶음 위치 | 분기 루트를 `out/branches/{S}/raw` 로 두어 묶음이 `out/branches/{S}/simulator_exchange` 에 따로 남는다 — `exchange.default_roots` 의 형제 폴더 규칙 그대로 | `out/raw/{S}` 유지 — 같은 부모라 `out/raw/simulator_exchange` 를 마지막 분기가 덮어쓴다(`simulator_api.md` 가 경고한다). 바로 읽으면 값은 맞지만 사후에 분기별 근거를 디스크에서 대조할 수 없다 |
| 이벤트 | 분기 루트 이벤트 중 `purchase` · `coupon_use` · `push_sent` 와 `campaign_id` 가 있는 것만 읽어 `build_kpi_report` 에 넘기고, 경제 지표 8종만 꺼낸다 | 전량 적재(D 와 같은 메모리 문제) · 의사결정 로더 DataFrame 을 dict 로 되돌리기(`order_amount` 가 `int` 가 아니라 `assemble_orders` 가 주문을 버린다) |
| 출처 | 시뮬레이터 출처 이벤트만(`partition_by_source` · MEA-002) | 합산 — 커머스 이벤트가 섞이면 처치 · 통제 비교가 성립하지 않는다 |
| 키 | `measured_revenue` · `measured_marketing_cost` · `measured_contribution_profit`. 후보 순서 `sim_*` → `measured_*` → 단순 키 → (`revenue_krw` · 계획 비용) | `sim_*` 에 덮어쓰기 — 값의 출처(`sim.metrics` 인가 우리 측정 호출인가)가 키에서 사라진다 |

## 조사한 것

| 출처 | 무엇을 말하나 | 우리 맥락에 얼마나 맞나 |
|---|---|---|
| `results/sprint-v0/SP-20261022-20k/strategy_comparison.json` (`strategy_details.*.sim_metrics`) | `revenue` · `contribution_profit` · `marketing_cost` · `churn_rate` 가 6 분기 전부 `not_run · PRECONDITION_MISSING` — "시뮬레이터 sim-0.4 의 metrics 는 건수만 센다 — 비즈니스 지표는 측정 계층(publish)이 계산한다" | ★ **오케스트레이션이 기여이익을 못 얻은 이유가 이것이다.** `run_sprint.py` 는 `sim.metrics(t2, end)` 의 `contribution_profit` 만 읽었고, 측정 계층을 부르지 않았다 |
| `docs/simulator_api.md` — `metrics` · `exchange_bundle` | `exchange_bundle(until)` 이 활성 세계 출력 루트의 형제 `simulator_exchange/` 에 교환 계약 v1 묶음(주문 · 품목 · 주문 시점 원가)을 전량 스냅샷으로 쓴다. 같은 부모 아래 분기 루트가 여럿이면 마지막 호출이 덮어쓴다 | 공개 계약이다 — 시뮬레이터 내부를 읽지 않고 이 문서만 봤다. 분기마다 그 분기 세계가 활성일 때 부르면 분기 계보의 주문이 실린다 |
| `src/measurement/publish.py` `build_kpi_report` · `assemble_orders` · `assemble_campaign` | `contribution_profit = ec.contribution_profit(assemble_orders(e, 묶음), assemble_campaign(e, 묶음))`. 묶음에 없는 주문은 `items=()` → `NO_COST_BASIS` | 게시물의 기여이익과 **같은 함수 · 같은 조립**을 쓰면 정의가 두 벌이 되지 않는다. 조립이 읽는 이벤트는 `purchase` · `coupon_use` · `push_sent` 와 `campaign_id` 보유 이벤트뿐이다 |
| `src/measurement/economics.py` `contribution_profit` (DR-101) | 기여이익 = 매출 − COGS − 배송보조 − 메시지 − 캠페인 고정비. 쿠폰 할인은 순매출에 이미 반영돼 빼지 않는다 | 대체 계산 `Δ(매출 − 마케팅비)` 는 COGS 를 빼지 않고(과대) 마케팅비 안의 쿠폰을 다시 뺀다(이중 차감) — 이슈 본문 그대로 확인 |
| SRS ROI-002 · ROI-003 · ROI-006 · MEA-003 (`Plan/AI_Customer_Retention_ROI_SRS_v2.0.md`) | 증분 기여 = 기여이익_AI − 기여이익_Rule. "결손 필드에 의존하는 지표는 계산 불가로 표시한다. 추정값을 만들어내지 않는다" | 정식 증분이익의 유일한 정의가 기여이익 차이다. 대체값을 그 칸에 두는 것은 MEA-003 의 "추정값" 이다 |
| 소규모 확인 실행 (smoke · 300명 · warmup 60일 → 분기 42일, 한 분기만 앞 100명에게 T3) | 무처치 분기 기여이익 6,277,952원(매출 24,087,300 · COGS 17,809,348). T3 분기 6,198,289원 · 마케팅비 180,000원(메시지 3,000 · 쿠폰 77,000 · 고정비 100,000). **대체값은 +168,500원, 실측 Δ기여이익은 −79,663원** | 부호가 뒤집힌다. 매출↑(+348,500) · 이익↓ 이므로 가드레일이 발동해야 하는 경우인데, 대체 계산으로는 영원히 발동하지 않는다. 표본이 작고 처치 대상이 임의라 효과 크기의 근거는 아니다 — 대체값이 방향조차 보장하지 않는다는 반례로만 쓴다 |

마진율로 COGS 를 추정하는 외부 근거는 찾지 않았다 — 근거가 있어도 EC-1 이 금지한다.

## 결정

**A.**

- `run_sprint.py` 분기 루트 = `out/branches/{S}/raw`. 분기 `advance(42)` 직후 그 분기 세계가 활성일 때 `sim.exchange_bundle(end)` → `out/branches/{S}/simulator_exchange`. 경제 지표는 `measured_economics()` 가 `src.measurement.publish.build_kpi_report` 로 계산하고 시뮬레이터 출처 값만 꺼낸다. 전 과정을 `strategy_details.{S}.measured_economics` 에 상태 · 사유 · 묶음 행 수와 함께 남기고, `ok` 인 값만 `metrics.measured_*` 에 싣는다(아니면 `null`). 묶음 · 측정 실패는 분기 단계를 실패시키지 않고 그 기록에 `failed` · `not_run` 으로 남는다.
- **분기 창 금액 대조(DQ-09)** — 리뷰 R1(P1, 2026-10-27 `kwung0206`) 반영. `window_amount_check()` 가 묶음을 **그 분기 창의 시뮬레이터 출처 purchase 주문 ID** 로 좁힌 읽기 전용 뷰를 만들어 측정 계층 `validate.check_amount_equation` 에 그대로 넘긴다(대조 규칙은 측정 계층 한 벌). 결과(상태 · 대조 행 수 · 위반 수 · 표본 · 창 밖으로 뺀 묶음 주문 수 · 묶음에 없는 창 주문 수 · 못 잡는 것)는 `measured_economics.amount_check` 에 남는다. `fail` 이면 그 분기 기록이 `status: quality_failed` 가 되어 `metrics.measured_*` 가 전부 `null` — 정식 기여이익 · 증분이익 · ROI · 가드레일이 계산 불가로 나간다. 다른 분기는 각자 판정한다(S1 이 실패하면 S2~S5 증분이익이 기준선 쪽 결손으로 모두 계산 불가). 대조할 주문이 없으면 `not_run`(통과가 아니다)이고 값은 막지 않는다 — 이벤트에만 있고 묶음에 없는 주문은 `NO_COST_BASIS` 가 막는다.
- `src/decision/roi.py`:
  - `incremental_profit_vs_S1` 은 **전략과 기준선이 같은 키로 가진 기여이익의 차이로만** 낸다. 아니면 `null` 과 `incremental_profit_status = "계산 불가 — …"`(전략 쪽 결손 · 기준선 쪽 결손 · 양쪽 결손 · 키 불일치를 구분) · 플래그 `CONTRIBUTION_PROFIT_MISSING`.
  - 그때 `roi` · `ai_roi` · `ai_net_incremental_value` 도 `null` 이고 상태가 그 사유를 말한다. `roi_status = "ok"` 는 정식 증분이익이 있을 때만 나온다.
  - 대체값은 `directional_revenue_minus_marketing_vs_S1` · `directional_status` · `directional_basis` 로 **분리**하고 플래그 `PROFIT_FALLBACK_REVENUE_BASED` 를 유지한다(대시보드가 읽는다). ROI · AI ROI · 가드레일에는 쓰지 않는다. 정식 값이 있으면 대체값은 만들지 않는다(`not_run`).
  - `guardrails.revenue_up_profit_down` · `guardrails.retention_up_cost_surge` 는 `status: ok | not_run` · `triggered: true | false | null` · `basis` · `reason`. 판정 못 하면 `not_run` 과 플래그 `REVENUE_UP_PROFIT_DOWN_NOT_RUN` · `RETENTION_UP_COST_SURGE_NOT_RUN`. 발동하면 기존처럼 `revenue_up_profit_down` · `retention_up_cost_surge` 플래그.
  - 마케팅비 후보 순서에 `measured_marketing_cost` 가 계획 비용보다 앞선다 — 정상 실행에서 ROI 분모는 실현 비용이 되고 `MARKETING_COST_PLANNED_NOT_REALIZED` 는 붙지 않는다.
- **대시보드 전략 화면** — 리뷰 R2(P2) 반영. 증분이익 칸 · 막대는 `incremental_profit_status === "ok"` 일 때만, ROI 칸 · 막대는 그에 더해 `roi_status === "ok"` 일 때만 숫자로 그린다(DG-5). `roi_status` 만 보지 않는 것은 #169 이전 형식(구형 결과)의 `roi_status` 가 대체값 위에서도 `ok` 이기 때문이다. `incremental_profit_status` 가 없는 행은 구형 결과로 보고 두 값을 그리지 않은 채 재생성 안내를 붙인다 — 방향 확인용 줄도 그 행에는 내지 않는다(구형에는 `directional_*` 가 없다). 로더가 구형 파일을 거부하지는 않으므로 매출 · 마케팅비 등 다른 열은 그대로 보인다. 목업 6행에도 두 상태 필드를 넣었다.

**근거:** 기여이익을 못 얻은 원인은 측정 계층이 아니라 호출 경로였다(위 첫 두 줄). 시뮬레이터가 이미 공개 계약으로 교환 묶음을 내고 측정 계층이 그것으로 COGS 를 계산하므로, 오케스트레이션이 그 둘을 이어 주기만 하면 실측 기여이익이 나온다. 결손을 정식 칸에 대체값으로 채우는 것은 MEA-003 이 금지한 추정이고, 소규모 실행이 보이듯 그 값은 방향도 보장하지 않는다.

## 기각한 안과 기각 사유

| 안 | 왜 택하지 않았나 |
|---|---|
| B · 현행 유지 | 대체값이 정식 칸에 있으면 숫자를 읽는 모든 곳(대시보드 막대 · ROI · AI ROI · 세그먼트 ROI)이 플래그 확인을 책임진다. 한 곳이라도 안 보면 과대평가값이 결론이 된다. 반례(부호 반전)가 있다 |
| C · 마진율 곱 추정 | EC-1 위반. 기여이익이 매출의 상수배가 되어 ROI-006 가드레일이 죽는다 |
| D · 분기마다 `publish()` 전체 | 같은 기여이익을 내지만 분기마다 전량 적재 · DQ 전부 · 게시물 쓰기를 한다. 분기 창 이벤트로 돌리는 DQ-09 는 계보 전량 묶음과 맞지 않아 거짓 위반을 낸다 |
| E · 시뮬레이터 지표를 기다림 | 계산 주체가 측정 계층(우리가 부르는 쪽)이라고 계약이 적는다. 기다릴 대상이 없다 |
| 대체값을 증분이익 칸에 두고 상태만 `계산 불가` 로 | 숫자와 상태가 모순된다. 상태를 안 읽는 쪽이 숫자를 쓴다 |
| 결손 쪽 기여이익을 0 으로 | `.get(k, 0)` 계열 — 이 저장소 규율(§7 「결손을 0 으로 채우지 않는다」) 위반 |
| 키가 달라도 값이 있으면 차이를 낸다 | 기준이 섞인다(예: `sim.metrics` 값 대 우리 측정 호출 값). 같은 정의라는 대조가 없으면 차이가 의미를 잃는다 — 계산 불가로 두고 어떤 키가 있었는지 사유에 적는다 |
| 같은 부모 아래 묶음을 순서대로 읽기 | 값은 맞지만 마지막 분기 묶음만 디스크에 남아 다른 분기의 근거를 사후에 대조할 수 없다 |
| 조립(`assemble_*` → `ec.*`)을 오케스트레이션에 다시 쓰기 | 규칙이 두 벌이 된다. `build_kpi_report` 를 그대로 부르고 필요한 지표만 꺼낸다 |

## 이 결정이 틀렸다면 어떻게 드러나나

- 교환 묶음이 있는 정상 실행에서 어떤 행이든 `PROFIT_FALLBACK_REVENUE_BASED` · `CONTRIBUTION_PROFIT_MISSING` 이 나오면 측정 경로가 끊긴 것이다. 작은 실제 실행(PR 본문)과 `tests/test_orchestration_sprint.py` 가 본다.
- 분기마다 `measured_contribution_profit / measured_revenue` 가 소수점까지 같으면 COGS 가 원가율 곱으로 만들어지고 있다는 뜻이다(EC-1). 처치 구성이 다른 분기는 비율이 달라야 한다.
- 필터한 이벤트로 낸 경제 지표가 전량으로 낸 값과 다르면 필터가 `publish` 조립과 어긋난 것이다 — `tests/test_orchestration_sprint.py` 가 같은 분기에서 둘을 대조한다. 측정 계층이 조립에 다른 이벤트 유형을 쓰기 시작하면 이 테스트가 실패해야 한다.
- 가드레일이 `ok · triggered=false` 인데 매출↑ · 이익↓ 인 행이 있으면 판정 키가 어긋난 것이다.
- 상태 필드가 없는 구형 `strategy_comparison.json` 으로 전략 화면을 열었을 때 증분이익 · ROI 칸이나 막대에 숫자가 보이면 화면 게이트가 빠진 것이다. 대시보드에는 단위 테스트 · CI 빌드 게이트가 없어 자동으로 잡히지 않는다 — 2026-10-29 개발 서버 렌더로 구형 · 신형 · 목업 3종을 확인했고, 같은 구형 파일을 이 수정 전 페이지로 열면 `+₩60` · `1.50` 이 막대에 그려지는 것(리뷰가 지적한 상태)을 대조군으로 확인했다.
- 교환 묶음이 있는 정상 실행에서 `amount_check` 가 `pass` 가 아니거나 대조 행 수가 창의 purchase 주문 수와 다르면 뷰를 좁히는 규칙이 틀린 것이다. 좁히지 않은 묶음은 같은 실행에서 `fail` 이어야 한다(창 이전 주문) — `tests/test_orchestration_sprint.py` 가 둘을 함께 본다.

## 민감도

- 이 결정에는 조정할 수치가 없다 — 정식 값이 있거나 없거나다.
- 대체값의 오차는 ΔCOGS + Δ쿠폰비 만큼이다. 소규모 실행에서 COGS 는 매출의 약 74% 였고(17.8M / 24.1M), 매출이 34.9만 원 늘 때 COGS 가 32.5만 원 늘었다 — 대체값은 이 대부분을 이익으로 센다. 처치가 매출을 많이 바꾸는 전략일수록(20K 실행의 S4 · S5) 오차가 크다.
- 필터 집합이 가장 민감한 부분이다. 하나라도 빠지면 기여이익이 조용히 틀린다(예: `push_sent` 를 빼면 메시지비 0). 그래서 전량 대조 테스트를 붙였다.

## 남은 불확실성

- **분기 창 DQ-09 는 묶음에만 있고 창 purchase 이벤트가 빠진 주문을 못 잡는다.** `ExchangeOrder` 에 주문 시각이 없어 묶음 주문이 창 안인지 알 수 없다 — 그래서 뷰를 이벤트 쪽 주문 ID 로 좁혔다. 이 공백은 `amount_check.not_detected` 에 그대로 싣는다. 교환 계약에 주문 시각이 생기거나 측정 계층에 창 단위 대조가 생기면 해소된다.
- 측정 기여이익은 분기 창의 **전 고객** 주문이다. `revenue_krw` · `churn_rate`(이벤트 결과)는 Feature(t2) 모집단이다. 전략 비교표의 `revenue` 열이 이제 `measured_revenue` 를 먼저 쓰므로 표의 매출 · 마케팅비 · 기여이익은 같은 모집단이고 이탈률만 다르다. 같은 스냅샷 · 같은 난수라 비처치 고객의 차이는 전략 효과에 포함된다고 본다 — 확인한 사실이 아니라 `docs/simulator_api.md` restore 계약에 기댄 가정이다.
- 시뮬레이터 묶음의 `discount` 는 쿠폰 처치 단가 그대로다(교환 계약 §11, 가정 A-DISCOUNT). 실제 커머스 할인과 다를 수 있다. 환불은 차감하지 않는다(A-REFUND).
- S4 · S5 의 가치(CLV × `margin_rate`)는 여전히 `economic_config` 가중 마진을 계획 가정으로 쓴다 — #171 범위.
- 대시보드 전략 화면의 가드레일 `not_run` 표시, 측정 실패 분기 행의 매출 · 마케팅비 기준(basis) 표시(리뷰 N1)는 후속이다.
- 목업 `dashboard/fixtures/sprint-v0/strategy_comparison.json` 의 ROI 값(S1 0.205 · S2~S5)은 `roi.py` 정의와 맞지 않는다 — 다섯 행 모두 S1 보다 마케팅비가 적거나 같아(S1 은 자기 자신) 정의대로라면 `계산 불가 — 추가 마케팅비 ≤ 0` 이다. #147 때 손으로 만든 값이고 이 PR 이 만든 결함이 아니어서 값은 고치지 않고 상태 필드만 넣었다. 별도 이슈로 다룬다.
