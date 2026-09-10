# ADR-0003 · 모든 지표를 `MetricValue` 로 표현하고 스키마로 강제한다

**상태** 확정 · 2026-09-11 · James
**이 프로젝트의 USP-1 이 사는 자리다**

## 문제
`MEA-003`·PRD §10.1·charter 절대제약 6 이 *"결손을 0으로 채우지 않는다"* 를 요구하는데, 강제 수단이 **사람의 규율**뿐이었다.
원가가 없을 때 0 으로 채우면 이익이 매출과 같아지고, **숫자는 나오고 화면은 채워지고 아무도 이상하다고 느끼지 않는다.**

## 결정
1. 지표 함수의 반환 타입을 **`MetricValue`** 로 고정한다. `float` 를 돌려주는 지표 함수를 두지 않는다
2. `status` 5종 — `ok` · `unconfirmed` · `unavailable` · `blocked` · `not_run`
3. **`unavailable`·`blocked`·`not_run` 이면 `value` 는 반드시 `null`** — JSON Schema `if/then` 이 강제한다
4. 계산 불가에는 `reason_code` + `reason_detail` 이 필수
5. 분모가 0 이면 `status` 가 `ok` 일 수 없다

## 검증 (실행함)
`tools/check_zero_fill_rejected.py` — 위반 시도 7건 전부 거부. 예시 7건 전부 통과.

```
거부됨 ✅  계산 불가를 0으로 채운다
거부됨 ✅  계산 불가인데 사유를 안 적는다
거부됨 ✅  BLOCKED 인데 값을 채운다
거부됨 ✅  분모가 0인데 계산됨(ok)이라고 한다
거부됨 ✅  미확정 파라미터를 밝히지 않는다
거부됨 ✅  KPI 계층에서 두 출처를 합산해 기본 표시로 쓴다
거부됨 ✅  UTC 시각으로 게시한다
```

## 기각한 대안
| 대안 | 사유 |
|---|---|
| `Optional[float]` | `None` 은 *"없다"* 만 말하고 *"왜"* 를 말하지 못한다. 화면이 `—` 만 그린다 |
| 값 + 별도 `unavailable_metrics` 목록 | 두 곳을 맞춰야 한다. 하나만 고치면 갈라진다 |
| 문서 규약 + 코드 리뷰 | 지금까지의 방식. 새 사람이 오면 무너진다 |
| `blocked` 와 `not_run` 을 합친다 | *"못 했다"* 와 *"안 했다"* 는 책임 소재가 다르다 |

## 결과
- `MetricStatus`·`ReasonCode` 를 `schema.py` 에 둔다 (결정 D-18 — 대안은 별도 `metrics.py`)
- 사유 코드 2종 추가 제안 (`NOT_RUN`·`PRECONDITION_MISSING`) — 결정 D-15
- 대시보드가 5상태를 **서로 다른 시각 상태**로 그려야 한다 → Jonnathan T2.13
