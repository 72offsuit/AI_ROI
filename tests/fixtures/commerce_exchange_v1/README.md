# 커머스 교환 파일 실제 표본

손으로 쓴 값이 아니라 `Ecommerce_Service` `3ac62ba` 가 실제로 만든 산출물이다. 기대값을 손으로 쓰면 구현과 기대가 함께 틀릴 수 있다.

| 파일 | 만든 명령 |
|---|---|
| `exchange/*` | `npm run exchange:export -- <디렉터리>` |
| `events.jsonl` | `npm run events:export` |
| `contribution.json` | `npm run economics:report` |

빈 DB(`ECOMMERCE_DB_PATH`)에 브라우저 고객 3명이 아래 순서로 구매한 뒤 세 명령을 실행했다. 쿠폰 두 종(정률·정액)과 쿠폰 없는 주문이 모두 들어 있다.

| 고객 | 품목 (상품 × 수량) | 쿠폰 |
|---|---|---|
| 1 | `dummyjson-16` × 8, `dummyjson-19` × 1 | `rate-10` |
| 2 | `dummyjson-16` × 1 | 없음 |
| 3 | `dummyjson-19` × 3, `dummyjson-16` × 2 | `fixed-3000` |

커머스 교환 파일 형식이나 이벤트 금액 규칙이 바뀌면 같은 절차로 다시 만든다.
