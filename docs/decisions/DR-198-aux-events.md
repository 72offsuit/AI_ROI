# DR-198-aux-events — 부수 이벤트 4종 생성 규칙과 metrics() 비즈니스 지표 연동

| | |
|---|---|
| 태스크 | S2·SIM · #198 (부모 #166) |
| 작성 | 성환(limtjdghks) · 2026-10-30 |
| 상태 | 제안 — 규칙·구조 확정, 배율값은 #246(Sleeping Dog 경로) 병합 뒤 실측으로 확정 |

## 무엇을 정하는가

시뮬레이터가 아직 만들지 않던 `search` · `return_visit` · `review` · `cs_contact` 를 어떤 규칙으로 생성하는가. 그리고 `metrics()` 의 비즈니스 지표(`revenue` · `contribution_profit` · `marketing_cost`)를 어떻게 값으로 내는가.

## 정하지 않으면 무엇이 막히나

- 시스템 팀 Feature(`search_to_purchase_conversion` · `visit_count` · 리뷰·CS 관련)가 전부 NaN 이다(#161 의 우회 제외 대상).
- `sim.metrics()` 가 비즈니스 지표를 값으로 내지 못한다(이슈 체크박스 ②).
- `search_propensity` · `review_propensity` · `cs_contact_propensity` 는 생성·저장만 되고 행동에 쓰이지 않는다.

## 선택지

| 안 | 내용 | 장점 | 단점 |
|---|---|---|---|
| A | 세션 안 통합: search 는 세션 시작 때 한 번, return_visit 은 구매 뒤 첫 방문 세션의 시작 이벤트를 `session_start` 대신, review 는 구매 후 경과 1~5일(24~144시간) 안의 첫 방문 세션 안에서 | `review` 의 `session_id` 필수 조건과 `visit_count` 이중 계산 방지를 함께 만족 | 이탈 판정의 "접속" 이 `session_start` 만 보면 구매 뒤 첫 방문이 빠진다 → 측정 계층 수정 필요 |
| B | return_visit 을 `session_start` 직후 별도 이벤트로, review 는 전용 짧은 세션 | 측정 계층을 건드리지 않는다 | `visit_count`(계약 = session_start + return_visit) 이중 계산, 세션 수 부풀림 |
| C | data_spec 원문만 구현(배율 없음), 차이는 기록만 | 가장 단순 | 외부 범위를 벗어나도 보정하려면 판을 한 번 더 올려야 한다 |

## 조사한 것

| 출처 | 무엇을 말하나 | 우리 맥락에 얼마나 맞나 |
|---|---|---|
| `docs/data_spec.html` §3.4 ④ (리드, 2026-09-10 v1.0) | `review ~ Bernoulli(review_propensity_i)` 구매 후 1~5일 · `cs_contact ~ Bernoulli(cs_contact_propensity_i / 30)` 일 단위. `search`·`return_visit` 규칙은 없다 | 정본 규칙. 모집단 평균(config `sim-gen-v3` 계산) 리뷰 성향 0.187 · CS 0.149 · 검색 0.490 이라 원문 그대로면 주문당 리뷰 약 18.7%, 주문 100건당 CS 약 5.9건(계산) |
| #197 외부 근거 코멘트(리뷰율·CS·검색) | 리뷰 주문당 약 3~12%(자발 1~3%, 요청 3~10%, 식품 라인 11.6%), CS 주문 100건당 F&B 약 20건(다른 벤더 2~15건, 2차), 검색자는 방문자의 약 24%(방문자 기준), 검색 세션 전환 배수 1.2~2.7(F&B 1.35) | 리뷰·CS 는 주문 단위라 직접 비교 가능. 검색은 방문자 기준이라 세션 비율과 직접 비교 못 한다. 전환 배수는 선택 효과라 생성 모수가 아니라 실현 검증 항목으로 둔다 |
| `docs/event_schema.md` · `src/measurement/schema.py` `_EVENT_RULES` | `search`·`return_visit` 필수 `session_id`·`page_type`, `review` 필수 `session_id`·`product_id`·`category`(선택 `order_id`), `cs_contact` 필수 `customer_id` 만. `visit_count`·`last_visit_date` = `session_start`·`return_visit` | 세션 안 통합(A)이 계약과 맞는다. 리뷰에 `unit_price`·`quantity` 를 넣으면 계약 위반이다 |
| `src/measurement/kpi.py` `_churn_elapsed`(main `cd9f446`) | 이탈 판정의 접속 = `session_start`·`purchase` | A 를 쓰면 구매 뒤 첫 방문이 접속에서 빠져 미접속 경과일이 과대가 된다 |

`search_intent_weight_pct`(150)와 리뷰 기록 창을 "첫 방문 세션" 으로 둔 것은 외부 정량 근거가 없다.

## 결정

**A 안**(2026-10-26 사용자 결정, 리드 합의 사용자 전달). 규칙과 config(`behavior.aux_events`, `sim-gen-v5`):

| 이벤트 | 규칙 | config |
|---|---|---|
| `search` | 세션 시작 때 한 번 Bernoulli(검색 성향 × `search_scale_pct`/100, 구매 의도 세션은 × `search_intent_weight_pct`/100, 상한 100%). `page_type = search`. 전용 스트림 `search` | `search_scale_pct` 100 · `search_intent_weight_pct` 150 |
| `return_visit` | 마지막 방문 뒤 구매가 있었으면 다음 방문 세션을 `session_start` 대신 `return_visit` 으로 연다. `page_type = home` | 없음 |
| `review` | 구매마다 Bernoulli(리뷰 성향 × `review_scale_pct`/100), 주문당 최대 1건. 당첨 주문의 한 상품을 대기(`pending_reviews`, 숨은 상태)에 넣고, 구매 시각부터 경과 `[1, 6)` × 24시간(24시간 이상 144시간 미만 — 날짜 차수가 아니라 23:50 구매 뒤 다음 날 00:10 방문은 들지 않는다) 안의 첫 방문 세션을 여는 시각에 `page_type = history`·`order_id` 와 함께 기록한다. 그 안에 방문이 없으면 버린다. 전용 스트림 `review` | `review_scale_pct` 100 · `review_window_days` [1, 6] (끝은 365 이하) |
| `cs_contact` | 가입 이후 매일 Bernoulli(CS 성향 / 30 × `cs_scale_pct`/100), 그날 안 임의 시각, 세션 밖. 전용 스트림 `cs` | `cs_scale_pct` 100 |

- 판: `SIMULATOR_VERSION` `sim-0.7`, 상태 형식 `sim-state-v5`(고객 항목 `pending_reviews`, 큐 종류 `cs`). **판 번호는 #246(`sim-0.7`)과 병합 순서를 정한 뒤 rebase 때 다시 매긴다.**
- **측정 계층(공유 영역) 변경** — 이탈 판정의 접속에 `return_visit` 을 더한다(`kpi._churn_elapsed`, `churn_rate`·`retention_rate`·`winback_rate`·`derived_state_count` 의 `source_events`). 2026-10-30 사용자 결정, 시스템 팀 리뷰 요청.
- **`metrics()`** — 창 안 `purchase`·`coupon_use`·`push_sent`·캠페인 이벤트와 계보의 주문 기록으로 메모리 교환 묶음을 만들어 `publish.assemble_orders`·`assemble_campaign`·`economics.revenue`·`marketing_cost`·`contribution_profit` 을 부른다(게시물 `build_kpi_report` 와 같은 규칙, 같은 값 대조 테스트). 비용 설정을 읽지 못하면 비용 2종은 `not_run`. `churn_rate` 는 `not_run` 유지(2026-10-30 사용자 결정). 이 변경으로 시스템 팀 소유 테스트 11건이 실패한다 — 시스템 팀이 처리한다(2026-10-30 사용자 전달). 시뮬레이터 팀은 시스템 팀 코드를 읽지 않으므로 영향 판단은 시스템 팀이 한다.

**근거:** A 는 계약의 세션·방문 정의와 함께 성립하는 유일한 안이다. 접속 정의 수정은 계약의 방문 정의(`visit_count`·`last_visit_date`)와 맞추는 것이다. 배율 기본 100% 는 원문 그대로라 보정은 실측 수치로만 한다(과제 G3 "설정으로 변경"). 외부 근거로 보정하는 것은 PRD §80 Risk 1 이 금지하는 AI 성능 근거 조정이 아니다. 새 이벤트를 전용 스트림에서만 뽑아 기존 12종의 추첨 자리가 그대로다 — 배율을 0 으로 두고 `return_visit` 을 `session_start` 로 되돌리면 sim-0.6 골든 이벤트와 바이트까지 같다(`tests/test_simulator_reproducibility.py` `TestAuxEventsLeaveEarlierBehaviorUnchanged`). 그래서 구매·이탈·처치 반응과 참 효과(주문만 쓴다)는 바뀌지 않는다.

## 기각한 안과 기각 사유

| 안 | 왜 택하지 않았나 |
|---|---|
| B (return_visit 별도 이벤트·리뷰 전용 세션) | `visit_count` 이중 계산(계약 위반 소지)과 세션 수 부풀림 |
| C (원문만, 배율 없음) | 실측이 외부 범위를 벗어나면 보정에 판을 한 번 더 올려야 한다 |
| 접속 정의를 두고 별도 이슈로 | 그 이슈가 처리될 때까지 시뮬레이터가 이탈 지표를 체계적으로 과대로 만드는 판을 낸다 |
| `metrics()` 연동을 후속 이슈로 | 이슈 범위가 남는다. 사용자가 이번 PR 에 넣고 시스템 팀에 선행 수정을 요청하기로 했다 |
| search 를 세션 행동 가중치(`browse_weights`)에 넣기 | 기존 `browse` 스트림의 추첨 순서가 바뀌어 행동 불변 검사를 둘 수 없다 |
| review 단위를 상품 라인당 | 원문이 구매당 Bernoulli 이고 외부 근거도 주문 단위다 |

## 이 결정이 틀렸다면 어떻게 드러나나

- 보정 seed 42~46 평균 실측(확인 47~51)에서 리뷰가 주문당 3~12%, CS 가 주문 100건당 5~20건을 벗어나면 배율이 틀렸다(#246 병합 뒤 판정).
- 검색 세션의 구매 전환 배수가 1 근처면 의도 가중이 너무 약하고, 2.7 을 크게 넘으면 너무 강하다.
- 이탈 고객의 CS 비율이 활동 고객과 같으면 일 단위 원문 규칙이 이탈과 무관하다는 뜻이다 — ANA-005 "이탈 직전 CS 빈도" 신호가 없다(활동 조건 검토).
- 시스템 팀이 측정 계층 접속 정의 변경을 거절하면 A 의 전제가 무너진다 — 그때는 B 또는 C 로 다시 정한다.

## 민감도

- 리뷰·CS·검색 배율은 해당 이벤트 수에 선형이다. 다른 이벤트·구매·이탈에는 영향이 없다(전용 스트림, 행동 불변 검사).
- `search_intent_weight_pct` ±20% 는 검색 세션 전환 배수를 바꾼다. 의도 세션 비율에 따라 크기가 달라 실측으로 본다.
- 측정 계층 접속 정의는 `no_login_days` 를 쓰는 규칙(AND 또는 짧은 미접속 임계)에서만 값이 달라진다. 기본 OR(42/60)은 미구매 조건과 같은 결과라 값이 그대로다.

## 남은 불확실성

- **실측(미실행):** #246 병합 뒤 보정 seed 42~46 · 확인 47~51 로 리뷰·CS·검색 세션 비율·검색 전환 배수·return_visit 비율·이탈 고객 CS 비율·생성 시간을 잰다. 참고로 smoke 수준 1회(seed 42 · 500명 · small · 120일, 판정 아님)는 리뷰 주문당 약 20.9%(758/3,626), CS 주문 100건당 약 6.9건(249/3,626), 검색 세션 약 51%, return_visit 은 세션 시작의 약 19% 였다 — 리뷰가 외부 범위 위다.
- **생성 시간:** `cs` 추첨이 고객 × 일수만큼 늘어난다(#167 생성 성능, DR-167 U3). 2,000명 · small · 275일 `advance` CPU 시간 2회씩은 main 26.1 · 19.6초, 이 판 23.8 · 22.3초로 차이가 실행 간 잡음보다 작았다(이벤트는 903,047 → 997,841건, +10%). cProfile(500명 · 275일)에서 `_schedule_cs` 는 전체 15.5초 중 0.43초이고 대부분은 측정 계층의 이벤트 검증·기록이다. 20K × 600일 시간은 실측 때 함께 잰다.
- **시스템 팀 영향:** `metrics()` 비즈니스 값이 생기면 시스템 팀 소유 테스트(`tests/test_orchestration_sprint.py`) 11건이 실패한다. 영향 판단·수정과 Feature 값(`search_to_purchase_conversion` 등) 확인은 시스템 팀이 한다(2026-10-30 사용자 전달).
- **실측 비교 주의:** `cs_contact` 는 세션 밖에서 방문 없이도 나서 고객의 첫 이벤트가 될 수 있다. 고객의 첫 관측 시점을 이벤트로 잡는 실측 지표(`scripts/research/realism_check.py` 의 첫 관측 기반 항목)는 이 판에서 값이 달라질 수 있어, #246 뒤 실측 때 sim-0.6 수치와 바로 비교하지 않는다.
- **`session_duration` 원천:** 세션이 `search`·`review`·`return_visit` 에서 끝나면 세션 길이가 그 이벤트에 실린다(계약상 허용). 공유 스키마의 `session_duration` 지표 원천 목록(`session_start`·`page_view`·`product_view`)에는 이 셋이 없다 — 공유 계약 쪽 사안이라 이 PR 에서 고치지 않는다.
- `data_spec.html` §3.4 ④ 에 구현 규칙을 더했다(리드 합의 2026-10-26, 사용자 전달 — 합의 범위는 PR 에서 리드 확인).
