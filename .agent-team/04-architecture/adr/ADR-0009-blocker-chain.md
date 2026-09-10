# ADR-0009 · 결손 → 영향의 사슬을 게시 시점에 넣는다

**상태** 확정 · 2026-09-11 · James
**요청** Jonnathan A-6 · 리드 지적 1

## 문제
첫 화면이 답해야 하는 질문은 *"무엇이 비었나"* 가 아니라 **"그래서 무엇을 못 하나"** 다.

`unit_cost` 미수신 → `cogs` 계산 불가 → `contribution_profit` 계산 불가 → `incremental_contribution_profit`(**Primary**) 성립 불가.

이 사슬을 **화면이 추론하면 `DB-012`(대시보드는 계산하지 않는다) 위반**이다.
그리고 추론 규칙이 화면과 측정 계층 두 곳에 있으면 갈라진다(P-4).

## 결정
**사슬을 게시 시점에 계산해 양방향으로 게시한다.**

| 방향 | 어디에 |
|---|---|
| 원인 → 영향 | `field_coverage_report.fields[f].affected_metrics`<br>`field_coverage_report.schema_gaps[].affected_metrics` · `.affected_checks` |
| 영향 → 원인 | `kpi_report.metrics[].value.blocked_by` |
| 영향 → 하위 | `kpi_report.metrics[].blocks` |

`blocked_by[].kind` **9종** — `field` · `schema_gap` · `event_type` · `metric` · `table` · `model_output` · `strategy` · `parameter` · `dependency`.

## 근거
- **양방향이어야 한다.** 화면은 V3(필드 카드)에서도 V4(지표 카드)에서도 들어온다. 한 방향만 게시하면 반대쪽에서 화면이 역인덱스를 만들어야 하고, 그것이 계산이다
- `kind` 를 나눈 이유: *"필드가 비었다"* 와 *"컬럼 자체가 없다"* 와 *"테이블이 없다"* 는 **해결 주체가 다르다.** 앞은 기록자, 가운데는 SRS 개정, 뒤는 구현이다. 화면이 그 차이를 표시할 수 있어야 사람이 다음 행동을 안다
- `schema_gap` 이 `field` 와 별개인 것이 `ADR` 로 남길 만한 지점이다 — **`manifest.field_coverage` 는 존재하는 컬럼만 세므로 컬럼 부재는 어느 집계에도 나타나지 않는다**

## 결과
- `publish.py` 가 사슬을 계산한다. 규칙은 `kpi.py` 의 지표 정의(어떤 이벤트·필드에 의존하는가)에서 파생되며 **손으로 관리하는 표가 아니다**
- C1 의 `schema_gaps` 는 4건 — `unit_cost` · `discount` · `shipping_fee` · `refund`. **넷 다 기여이익식이 빼는 항목이다**
- 사슬이 틀리면 화면이 틀린 인과를 보여준다. → `tests/test_publish_contract.py` 가 **`blocked_by` 와 `affected_metrics` 의 역방향 일치**를 검사할 것을 권고한다
