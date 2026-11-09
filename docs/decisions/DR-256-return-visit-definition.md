# DR-256-return-visit-definition — `return_visit` 은 구매 뒤 첫 방문 세션을 `session_start` **대신** 연다

| | |
|---|---|
| 태스크 | 리드 · #256 (Sprint 3, GATE 1 봉인 전 — `docs/sprint_plan.md` §3 GATE 1 선행 조건) |
| 작성 | 인성(Danto7632, 에이전트 작성) · 2026-11-05 |
| 상태 | 리드 결정(2026-11-05) — 시뮬레이터 팀 합의 대기(#256, 11/06 오전) |

## 무엇을 정하는가

`return_visit` 이벤트를 **언제** 기록하는가, 그리고 그 세션에 `session_start` 도 남기는가. 측정 계약에 적고 두 생산자(커머스 · 시뮬레이터)를 맞춘다.

## 정하지 않으면 무엇이 막히나

- **같은 이름의 숫자가 출처마다 다른 뜻이 된다.** 커머스는 "이전 세션이 있는 고객의 새 세션마다, `session_start` 와 함께" 기록하고, 시뮬레이터는 "구매 뒤 첫 방문 세션에, `session_start` 대신" 기록한다(#256 본문의 근거 표). 이벤트 수를 그대로 세는 Feature(`return_visit_count_60d`)와 Churn DL 의 방문 채널은 시뮬레이터 데이터로 학습한 모델을 커머스 데이터에 쓰면 입력 분포가 어긋난다.
- **측정 계약은 GATE 1 해시 대상이다**(`config/gate1_lock.yaml` canonical_files). 봉인 뒤에 정의를 바꾸면 FREEZE-003(재생성 → Baseline 부터 재실행)이다. 그래서 GATE 1 실측(#208) 전에 정해야 한다.

## 선택지

| 안 | 정의 | 바꿀 곳 | 봉인 전 시뮬레이터 변경 |
|---|---|---|---|
| A. 커머스 정의 | 첫 세션 이후 모든 새 세션 · `session_start` 와 함께 | 시뮬레이터 생성 규칙, data_spec §3.4 ④ | 필요 |
| **B. data_spec ④ 정의** | 구매 뒤 첫 방문 세션 · `session_start` 대신 | 커머스 기록 조건, 측정 계약 · 이벤트 스키마 문서 | **없음** |
| C. 혼합 | 구매 뒤 첫 방문 세션 · `session_start` 와 함께 | 시뮬레이터, 커머스, data_spec ④, 측정 계약 | 필요 |

## 조사한 것

- **data_spec §3.4 ④ 구현 규칙**(#198, 리드 합의 2026-10-26): "`return_visit` — 구매 뒤 첫 방문 세션을 `session_start` 대신 이 이벤트로 연다(visit_count 이중 계산 방지)". 두 팀이 이미 합의한 정의다.
- **시뮬레이터**는 #252(2026-10-31 병합)에서 이 규칙으로 만든다 — #256 본문의 근거 표(정의 수준). 시뮬레이터 코드는 읽지 않았다.
- **커머스** `Ecommerce_Service` `src/lib/server/commerce/event-log.ts` 276–278행 — 새 세션마다 · 함께(#256 본문).
- **측정 계층이 접속 · 방문을 세는 방식**(이 저장소, main `e2942a1`):
  - Observable `visit_count` · `last_visit_date` 의 근거 이벤트는 `session_start` · `return_visit` 이다(`src/measurement/schema.py` 매핑 — 어느 이벤트로 계산하는지를 정하고, `coverage.py` 는 그 이벤트가 있는지를 본다). B 에서는 생산자가 규칙을 지키면 세션마다 둘 중 하나만 있으므로 **두 이벤트를 합친 수 = 세션 수**다.
  - **방문 Feature 는 어느 안이든 두 번 세지 않는다.** F08 · F25 · `visit_count_60d` 는 `session_id` 고유 개수다(`src/decision/features/d1_calculate.py` · `sprint_table.py`). 커머스의 지금 방식(함께)에서 **이벤트 수가 두 번 쌓이는 곳은 Churn DL 의 `visit` 채널**(`src/decision/churn_dl.py`, 일별 `session_start` · `return_visit` 이벤트 수)이다 — 재방문 세션이 커머스에서 2, 시뮬레이터에서 1 이다. 이벤트 수를 세는 `return_visit_count_60d` 도 출처마다 뜻이 다르다(#256 본문). B 를 고르는 이유는 이 두 곳이다 — PR #265 리뷰(광진)에서 범위를 좁혔다.
  - 미접속 경과일의 접속 = `session_start` · `return_visit` · `purchase`(`src/measurement/kpi.py`) — 마지막 시각만 보므로 어느 안이든 같다.
  - 퍼널 방문 단계 = `session_start ∪ return_visit`(#255 · #259, DR-255) — B 에 맞는다.
  - `session_duration` 의 계산 이벤트는 `session_start` · `page_view` · `product_view` 다(`schema.py`). B 에서 `return_visit` 하나로 끝나는 세션이 이 계산에서 빠지는지는 반영 ③에서 확인한다.

## 결정

**B.** 고객의 마지막 `purchase` 뒤 처음 시작하는 세션은 `return_visit` 으로 열고, 그 세션에는 `session_start` 를 남기지 않는다. 다른 세션은 `session_start` 로 연다. 세션은 둘 중 하나로 시작한다.

- 이 PR: `docs/measurement_contract.md` §1 · `docs/event_schema.md`(생성기 `scripts/gen_event_schema_doc.py`)에 적는다 — 반영 ①.
- 반영 ② 커머스 기록 조건(인성, 리뷰 성환) · 반영 ③ DQ · 소비처 점검(광진)은 `docs/sprint_plan.md` §5.
- 시뮬레이터는 바꾸지 않는다.

## 기각한 안과 기각 사유

- **A** — `return_visit` 이 "첫 세션이 아님"과 같아져 방문 수 이상의 정보가 거의 없다. PRD 퍼널의 Return Visit(구매 뒤 재방문) 단계와 뜻이 다르다. 봉인 전에 시뮬레이터를 고쳐야 한다.
- **C** — 11/02 #256 본문의 추천이었다. "모든 세션은 `session_start` 로 연다"가 유지되는 장점이 있지만, 두 생산자를 모두 고치고 공유 문서 data_spec ④ 를 두 팀 합의로 다시 써야 하며 봉인 전에 시뮬레이터를 고쳐야 한다. GATE 1 이 이미 늦어진 지금(기한 11/04 경과) 봉인을 시뮬레이터 변경에 묶지 않는다.
- **B 의 비용** — "모든 세션은 `session_start` 로 연다"는 불변식이 깨진다. 세션을 다루는 소비처는 `return_visit` 도 세션을 여는 이벤트로 받아야 한다. 측정 계층의 방문 · 접속 · 퍼널은 이미 그렇게 센다(위 조사). 나머지는 반영 ③에서 확인한다.

## 이 결정이 틀렸다면 어떻게 드러나나

- **소비처가 `return_visit` 세션을 빠뜨린다:** 어떤 집계에서 `session_start` 수가 `session_id` 고유 수보다 작고, 그 차이가 재방문 세션 수와 같다. 퍼널 · 세션 길이 · Feature 에서 이런 차이가 나오면 그 소비처를 고친다(반영 ③).
- **생산자가 정의를 어긴다:** 한 `session_id` 에 `session_start` 와 `return_visit` 이 함께 있거나, 구매 뒤 첫 세션이 `session_start` 로 열린다. 커머스 반영 ② 뒤에도 그러면 ②가 틀렸다.
- **합의가 뒤집힌다:** 시뮬레이터 팀이 B 에 동의하지 않으면 이 기록은 철회하고 #256 에서 다시 정한다 — 그때는 이 PR 을 병합하지 않는다.

## 민감도

정의 선택이라 수치 모수가 없다. 영향 크기는 **구매 뒤 첫 세션의 비율**이다 — 그 비율만큼 `session_start` 만 세는 집계가 줄어든다. 비율은 생산자와 기간에 따라 달라서 이 기록에 값을 적지 않는다.

## 남은 불확실성

- 시뮬레이터 팀 합의 전이다(#256, 11/06 오전 회신 요청).
- 반영 ②(커머스) · ③(DQ · 소비처)은 이 기록 뒤에 한다. ③에서 `session_duration` 계산 이벤트(`schema.py`, GATE 1 정본)를 바꿔야 한다고 정하면 그것도 #208 실측 전에 병합한다.
- 반영 ③에서 함께 볼 것(PR #265 리뷰):
  - **DQ 가 B 를 강제하지 않는다.** `DQ-04` 는 시간 순서 검사라, 같은 세션에 두 시작 이벤트가 있어도 통과한다. 위반을 잡을 검사가 필요한지 정한다.
  - **반영 ② 전에 "함께" 기록된 커머스 데이터**는 생산자를 고쳐도 그대로다. 이벤트 수를 세는 소비처(Churn DL `visit` 채널)에 쓸 때의 처리 방침을 정한다. 데이터 수정 · 삭제 · 재생성은 이 기록이 정하지 않는다.
- **GATE 1 부분 봉인 기록은 다시 썼다 — 끝났다.** 정본 해시 2건(`measurement_contract.md` · `event_schema.md`)이 바뀌어, 사람(Danto7632)이 `freeze.record()` 로 서명했다(PR #265 두 번째 커밋 `1f6ff94`, 기록의 `repo_commit` = 첫 커밋 `e1372ec`). 바뀐 칸은 `locked_at` · `repo_commit` · 해시 2건뿐이고 판 `gate1-lock/v1` · 항목 9종 · `PARTIAL_FREEZE` · 가정 4건은 그대로다. 같은 판으로 다시 쓴 근거는 DR-109 의 전제("시뮬레이터 산출물 없음")가 아니라 지금의 사실이다 — **`EVENT_SCHEMA_v1` 은 아직 `PENDING` 이고, B 는 시뮬레이터가 이미 쓰는 정의를 바꾸지 않는 문서 정합 변경**이다. 이 DR 은 정본 해시 대상이 아니라 이 보완으로 다시 서명할 필요는 없다.
