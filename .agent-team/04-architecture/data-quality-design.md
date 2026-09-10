# 데이터 품질 검증 설계 (T2.8 · M-6 / `#48`)

**작성** James (Role 4 · Architect) · 2026-09-11 · 사이클 C1
**정본 근거** `docs/data_spec.html` §9 · 이슈 `#48` · SRS `NFR-001`
**기획 판정 입력** Joshua — *"`#48` 은 C1 에서 닫히지 않는다"* (`core-features.md` §3.2)

> **이 설계의 목적은 "무엇을 검사하는가"보다 "무엇을 검사하지 **않았는가**를 어떻게 남기는가"다.**
> `data_spec` §9 의 10개 항목 중 C1 에서 실행할 수 있는 것은 절반이 안 된다. 나머지를 목록에서 빼면 리포트는 초록이 되고, **검사하지 않은 것이 통과로 읽힌다.**

---

# 1. 산출물과 계약

| | |
|---|---|
| 실행 모듈 | **`src/measurement/validate.py`** — `data_spec` §9 가 지정한 경로. 발명하지 않았다 |
| 리포트 | **`results/data_quality_report.json`** — 동일 |
| 스키마 | `schemas/data_quality_report.schema.json` (`api-contracts.md` §5.5) |
| 화면 | **V5** `/quality` |

---

# 2. 게이트 의미 — 3값으로 나눈 이유

`data_spec` §9: *"하나라도 실패하면 파이프라인은 **중단**한다(경고로 넘어가지 않는다)."*

그대로 2값(`pass`/`fail`)으로 만들면 문제가 생긴다. **C1 에서는 검사의 절반이 실행 불가**인데, 그것을 `fail` 로 두면 파이프라인이 영원히 멈추고, `pass` 로 두면 미실행이 통과가 된다.

> ### 확정 — `gate_result` 는 3값이다
>
> | 값 | 뜻 | 파이프라인 |
> |---|---|---|
> | `pass` | 실행한 검사가 전부 통과했고 **실행하지 못한 검사가 없다** | 진행 |
> | `incomplete` | 실행한 검사는 전부 통과했으나 **`not_run`·`blocked` 가 하나 이상 있다** | **진행하되 화면·리포트에 크게 표시** |
> | `fail` | **데이터가 검사를 위반했다** | **중단** (`data_spec` §9) |
>
> **`not_run` 은 데이터의 실패가 아니라 검사기의 한계다.** 둘을 같은 값으로 적으면 책임 소재가 뒤바뀐다.

**`fail` 의 처리** — `validate.py` 는 `QualityGateFailure` 를 던지고 종료 코드 `2` 를 낸다(`exceptions.md` §5). 게시는 리포트까지만 하고 그 뒤 단계를 진행하지 않는다.

---

# 3. ★ C1 에서 실행 가능한 것 / 불가능한 것

`data_spec` §9 의 항목을 검사 단위로 쪼갠 17종이다. **불가능한 것도 전부 목록에 남는다.**

| ID | `data_spec` 항목 | 검사 | C1 | 사유 코드 |
|---|---|---|---|---|
| **DQ-01** | 유일성 | `event_id` 전역 유일 | ✅ | — |
| **DQ-02** | 유일성 | `order_id` 전역 유일 | ❌ | `PRECONDITION_MISSING` — `orders` 테이블 미구현 |
| **DQ-02b** | 유일성(범위 축소) | **`order_id` 당 `purchase` 이벤트 정확히 1건** | ✅ | — |
| **DQ-03** | 참조 무결성 | 고아 `customer_id`·`product_id` 0건 | ❌ | `PRECONDITION_MISSING` — `customers`·`products` 미구현 |
| **DQ-04** | 시간 정합성 | 세션 내 이벤트 순서 | ✅ | — |
| **DQ-05** | 시간 정합성 | `timestamp < signup_date` 0건 | ❌ | `PRECONDITION_MISSING` — `signup_date` 는 `customers` 컬럼 |
| **DQ-06** | 시간 정합성 | 모든 시각이 KST 단일 | ⚠️ | `BLOCKED` — 타임존 정책 미확정 (`#53` D1-3) |
| **DQ-07** | 퍼널 정합성 | `purchase` ← 선행 `checkout_start` | ✅ | — |
| **DQ-08** | 퍼널 정합성 | `coupon_use` ← 선행 `coupon_exposed` | ✅ | — |
| **DQ-09** | 금액 정합성 | `order_amount = Σ(unit_price×quantity) − discount`, 오차 0원 | ❌ | `PRECONDITION_MISSING` — **§4 참조. 원리적으로 불가** |
| **DQ-10** | 금액 정합성 | 음수 금액 0건 | ✅ | — |
| **DQ-11** | 완전성 | Key 결측 0% | ✅ | — |
| **DQ-12** | 완전성 | Feature 결측률 항목별 5% 미만 | ❌ | `PRECONDITION_MISSING` — `data/processed/` 미생성 · decision 소관 |
| **DQ-13** | 생성 이탈률 | 15% ≤ rate ≤ 25% | ❌ | `PRECONDITION_MISSING` — 시뮬레이터 없음 |
| **DQ-14** | 실험 균형 | \|SMD\| < 0.1 | ❌ | `PRECONDITION_MISSING` — `#48` 이 이미 범위 C 로 이관 |
| **DQ-15** | 처치 강도 | ATE 3~6%p · 쿠폰 사용률 25~40% · Sleeping Dog 8~15% | ❌ | `PRECONDITION_MISSING` |
| **DQ-16** | 4분면 분포 | Persuadables 20~30% 등 | ❌ | `PRECONDITION_MISSING` — **measurement 소관이 아니다**. Ground-truth 는 `diagnostics` 전용 |
| **DQ-17** | 재현성 | `events.parquet` SHA-256 일치 (`NFR-001`) | ⚠️ | `BLOCKED` — pyarrow 미설치. **`dependency-plan.md` 도입으로 해소 가능** |

**실행 가능 7 · BLOCKED 2 · PRECONDITION_MISSING 8.**

> **`#48` 은 C1 에서 닫히지 않는다.** Joshua 의 판정이 옳다.
> **다만 `DQ-17` 은 T2.9 의 의존성 도입으로 해소된다.** 8건이 아니라 7건만 남는 것과, 그 차이를 리포트가 정확히 말하는 것이 C1 의 성과다.

## 3.1 `scope` 는 선택 항목이 아니다

스키마가 각 검사에 **`scope` 를 필수**로 요구한다(`data_quality_report.schema.json`).

예 — `DQ-01`:
> *"저장된 `events` 파티션 전 구간. 오늘은 0행이므로 위반이 없는 것이 아니라 **검사 대상이 없다** — `examined_rows` 를 함께 읽어야 한다."*

**범위 문구가 없으면 부분 검사가 전체 검사로 읽힌다.** 빈 데이터에 대한 `pass` 는 특히 위험하다 — `examined_rows` 를 함께 내는 이유가 이것이다.

## 3.2 `not_run` 은 `violations: null` 이다

스키마 강제: `status` 가 `not_run`·`blocked` 면 `violations` 는 **`null` 이어야 한다.**
`0` 으로 적으면 "위반 0건" 으로 읽히고, 그것이 미실행을 통과로 만드는 가장 흔한 경로다.

---

# 4. ★ 새 발견 — `DQ-09` 금액 정합성은 원리적으로 불가하다

`api-contracts.md` §8 의 발견을 검사 관점에서 다시 적는다.

## 4.1 두 겹의 장벽

**① `discount` 필드가 없다.**
`schema.py:121` 이 `order_amount` 를 `Σ(unit_price × quantity) − discount` 로 정의하는데, **DATA-003 22 컬럼에 `discount` 가 없다** (실측: `event_id`·`customer_id`·`timestamp`·`event_type`·`session_id`·`session_duration`·`page_type`·`product_id`·`category`·`quantity`·`unit_price`·`order_id`·`order_amount`·`coupon_id`·`campaign_id`·`treatment_id`·`treatment_group`·`experiment_id`·`service_version`·`customer_version`·`simulator_version`·`random_seed`).

**② 품목 합계를 재구성할 수 없다.**
`_EVENT_RULES[PURCHASE]` 실측 — 필수 `session_id`·`page_type`·`order_id`·`order_amount`.
**`product_id`·`quantity`·`unit_price` 는 `purchase` 에서 `NOT_APPLICABLE`** 이고, 값이 있으면 `validate_event()` 가 거부한다(`schema.py:293-297`).

→ **`purchase` 는 주문 단위 1행이다. 한 주문의 `Σ(unit_price × quantity)` 가 `events` 안에 없다.**
`add_to_cart` 로 근사하는 것은 부정확하다 — `remove_from_cart` 가 있고, 담았지만 사지 않은 품목이 있고, 결제 실패가 있다.

## 4.2 판정

**`DQ-09` 는 `order_items` 테이블(`data_spec` §7.1)이 있어야 성립한다. C1 에서 `not_run` + `PRECONDITION_MISSING` 이다.**
대신 **`DQ-10`(음수 0건)은 실행한다.** 두 검사를 하나로 묶어 "금액 정합성 통과"로 적으면 안 된다 — 그래서 ID 를 나눴다.

**연쇄 영향:** `coupon_cost = Σ discount`(`kpi-definition-v1.md` §5.1)도 계산할 필드가 없다. **`marketing_cost` 의 구성요소이고, `marketing_cost ≤ C_rule` 은 Guardrail 이다.**
→ **GATE 1 선행 조건에 G-16 추가를 제안한다** (`gate1-freeze-procedure.md` §3 · 결정 D-16).

---

# 5. 알고리즘 설계 — 25,000,000 행에서도 돌아야 한다

`data_spec` §7.1 의 예상 행 수는 `events ≈ 25,000,000` 이다. W1 실측은 4,200,000 행 / 112.6MB.
**메모리로 다 올릴 수 없다.** 설계를 미리 정하지 않으면 구현이 `set()` 하나로 시작하고 규모가 커질 때 터진다.

## 5.1 `DQ-01` 유일성 — 정렬 병합

```text
① 파티션마다 event_id 를 뽑아 정렬해 임시 파일에 쓴다   (파티션 하나는 메모리에 올라간다)
② heapq.merge() 로 정렬된 스트림을 병합한다            (표준 라이브러리 · 메모리 O(파티션 수))
③ 이웃한 두 값이 같으면 중복이다
```

- **표준 라이브러리만 쓴다** (`heapq` · `tempfile`)
- 메모리는 파티션 하나 + 병합 힙. **전체 행 수에 비례하지 않는다**
- 임시 파일은 `tempfile.TemporaryDirectory()` — `data/`·`results/` 를 오염시키지 않는다

> **`set()` 에 25M UUID 를 담지 않는다.** 대략 3GB 이상이 필요하고, 개발 기계에서 조용히 스왑하거나 CI 에서 죽는다. **"오늘 0행이라 돌아간다"는 설계가 아니다.**

## 5.2 `DQ-04` 세션 순서 · `DQ-07`·`DQ-08` 퍼널 — 파티션 경계를 넘는다

**⚠ 함정:** 세션과 주문은 **자정을 넘는다.** 파티션(날짜)별로 검사하면 23:58 `checkout_start` → 00:02 `purchase` 인 정상 주문이 위반으로 잡힌다.

```text
① 전 파티션을 스캔하며 (key, event_type, timestamp) 만 뽑는다
     DQ-04 → key = session_id
     DQ-07 → key = order_id
     DQ-08 → key = coupon_id
② key 로 정렬해 임시 파일에 쓴다 (5.1 과 같은 방식)
③ 같은 key 의 이벤트를 모아 순서를 검사한다
```

레코드 전체가 아니라 **3개 필드만** 나르므로 메모리가 작다.

## 5.3 `DQ-17` 재현성 — 무엇과 무엇을 비교하나

`NFR-001`: *"동일 seed·동일 config 로 재실행 시 `events.parquet` 의 SHA-256 이 일치한다."*

**C1 에는 재생성할 주체(시뮬레이터)가 없다.** 그래서 이 검사는 두 층으로 나뉜다.

| 층 | C1 | 방법 |
|---|---|---|
| **Sink 의 결정성** — 같은 입력을 두 번 쓰면 같은 바이트 | `jsonl.gz` ✅ (`test_sink.py:216-225` 가 이미) / **Parquet ⚠️ `BLOCKED`** | 테스트 |
| **파이프라인 재현성** — 같은 seed 로 재생성하면 같은 데이터 | ❌ | 시뮬레이터 사이클 |

**`DQ-17` 이 검사하는 것은 첫째 층뿐이며, 그 범위를 `scope` 에 적는다.**
그리고 **형식이 다르면 해시가 다르다** — 재현성 대조는 같은 형식끼리만 성립한다(`dependency-plan.md` §4.3). 이것도 `scope` 에 적는다.

## 5.4 데이터가 0행일 때 — 무엇이 정상인가

오늘의 상태다. **`pass` 지만 `examined_rows: 0` 이다.**

| 검사 | 0행에서 | 왜 |
|---|---|---|
| `DQ-01` 유일성 | `pass` · `examined_rows: 0` | 중복이 없는 것은 사실이다 |
| `DQ-10` 음수 금액 | `pass` · `examined_rows: 0` | 동일 |
| `gate_result` | **`incomplete`** | `not_run`·`blocked` 가 10건 있다 |

**화면(V5)은 `examined_rows: 0` 인 `pass` 를 "통과"로만 그리면 안 된다.** 검사 대상이 없었다는 사실이 함께 보여야 한다 → **Jonnathan 에게 전달된 설계 요구**다.

---

# 6. 의도적으로 깨뜨린 데이터로 검사한다 — `#48` 완료 조건

> `#48`: *"의도적으로 깨뜨린 데이터로 각 검사가 실제로 실패하는지 확인한다."*

`tests/test_quality_checks.py` 는 **실행 가능한 7개 검사 각각에 대해 위반 데이터를 만들어 `fail` 이 나오는지 확인한다.**

| 검사 | 깨뜨리는 방법 |
|---|---|
| `DQ-01` | 같은 `event_id` 를 서로 다른 파티션에 하나씩 |
| `DQ-02b` | 같은 `order_id` 로 `purchase` 두 건 |
| `DQ-04` | 같은 세션에서 `purchase` 가 `session_start` 보다 이르게 |
| `DQ-07` | `checkout_start` 없는 `purchase` |
| `DQ-08` | `coupon_exposed` 없는 `coupon_use` |
| `DQ-10` | 음수 `order_amount` (**`strict=False` 로 Sink 를 우회해 저장** — `#53` D1-2 수정 후에 가능) |
| `DQ-11` | `customer_id` 가 `None` 인 레코드 (동일) |

> ⚠ **`DQ-10`·`DQ-11` 의 위반 데이터는 `validate_event()` 가 수집 시점에 막는다.**
> 저장된 데이터에 넣으려면 `strict=False` 경로를 써야 하는데 **그 경로가 지금 크래시한다**(`#53` D1-2).
> → **`#53` 이 `#48` 의 선행이다.** `gate1-lock-scope.md` §2.3 의 Phase 1 배치와 일치한다.

**검사가 잡는지 확인하지 않은 검사는 없는 검사와 같다** — `data_spec` §17.5 가 격리 검사에 대해 같은 것을 했다(*"규칙을 일부러 어기는 파일 3개를 넣었을 때 6종 위반을 모두 보고하고 실패했다"*). 같은 규율을 품질 검사에도 적용한다.

---

# 7. `#48` 을 C1 에서 어디까지 하는가 — 경계

| C1 에서 한다 | C1 에서 하지 않는다 |
|---|---|
| `validate.py` 구현 + 리포트 게시 | 참조 무결성 (`DQ-03`·`DQ-05`) |
| 실행 가능 7건 + 위반 탐지 테스트 | Feature 결측률 (`DQ-12`) |
| **미실행 10건을 사유와 함께 리포트에 남기기** | 시뮬레이터 의존 4건 (`DQ-13`~`DQ-16`) |
| `gate_result` 3값 · `fail` 시 중단 | 금액 정합성 (`DQ-09`) — 원리적으로 불가 |
| `DQ-17` 은 의존성 도입 시 해소 | 6개 추가 테이블 구현 |
| 25M 행 알고리즘 설계 반영 | 25M 행 실측 (데이터가 없다) |

> **이슈 `#48` 은 열어 둔다.** 미실행 항목을 `BLOCKED`·`not_run` 으로 남기고, **닫지 않는다.**
> Issue close 는 개별 승인 사항이므로 이 팀이 판단하지 않는다.

---

# 8. 결정이 필요한 항목

| # | 항목 | 선택지 | 추천 |
|---|---|---|---|
| **D-24** | `gate_result` 를 3값으로 하는가 | ⑴ `pass`/`incomplete`/`fail` ⑵ 2값 유지하고 미실행은 별도 필드 | **⑴.** ⑵는 요약 한 줄이 초록이 되고, 요약만 보는 사람이 대부분이다 |
| **D-25** | `DQ-02` 를 범위 축소한 `DQ-02b` 로 대체하는가 | ⑴ 둘 다 목록에 두고 원본은 `not_run` ⑵ `DQ-02b` 만 둔다 | **⑴.** ⑵는 정본 항목이 목록에서 사라져 `data_spec` §9 와 1:1 대응이 깨진다(`#48` 완료 조건) |

*D-16(`discount` 처리)은 `api-contracts.md` §9 에 있다.*

---

# 9. 미정으로 남긴 것

| 항목 | 왜 |
|---|---|
| `validate.py` 의 함수 시그니처 | **Phillip T5.3 소관.** 이 문서는 검사 목록·의미·알고리즘 제약까지다 |
| Bootstrap 재현 seed 규약 | `kpi-definition-v1.md` §10 이 `#48` 과 함께 정하자고 남겼다. **실험 판정 지표가 C1 에서 계산되지 않으므로 지금 정할 근거가 없다** |
| 파생 상태(`inactive`/`at_risk`/`churn`) 기록 경로 | W1 D-7. `#45`(M-3)의 Lock 최종 검산에서 결론 (`code-structure.md` §7) |
| 25M 행 실측 성능 | 데이터가 없다. 알고리즘 제약만 정하고 측정은 시뮬레이터 사이클로 |
