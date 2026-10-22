# DR-S3-p6-signup — 신규가입 페르소나의 중도 가입일과 `small` 프로파일

| | |
|---|---|
| 태스크 | S3 · #77 |
| 작성 | 민정 · 2026-10-22 |
| 상태 | 제안 |

## 무엇을 정하는가

1. 신규가입 페르소나(P6) 고객의 **가입일을 어떤 범위에서, 어떤 난수로, 어디에 적어 두고** 뽑는가. S2 는 전원 Day 0 가입으로 두고 이 일을 S3 에 넘겼다(`docs/persona_spec.md` §2.3·§6).
2. 이슈 #77 의 `init(profile="small")` 을 어떻게 구현하는가(`DR-S3-sample-size` U3: 5,000명 × `short` 시간축).

## 정하지 않으면 무엇이 막히나

- Eligible 조건 "가입 60일 이상"(data_spec §4.1)이 전원 Day 0 가입이면 언제나 참이 된다. 이력 길이가 다른 고객이 섞인 모집단(data_spec §3.2)이 만들어지지 않는다.
- 가입일이 바뀌면 이벤트가 바뀐다. 이벤트 골든과 `SIMULATOR_VERSION` 을 S4 전에 한 번 정리해 둬야 S4 가 깨끗한 기준에서 시작한다.
- `DR-S3-assignment` 의 배정은 T0 = `calendar_start + warmup_days` 를 쓴다. 프로파일에 기간 값이 없으면 T0 를 알 수 없다.

## 선택지

**가입일 범위**

| 안 | 내용 | 장점 | 단점 |
|---|---|---|---|
| A | Day 1~272 균등, 프로파일과 무관 (data_spec §3.2) | 같은 seed 면 프로파일이 달라도 같은 고객 — data_spec §2.2 "프로파일을 바꿔도 고객 모집단은 유지된다" | `short`(T0 = Day 180)에서는 P6 일부가 T0 뒤에 가입한다 |
| B | Day 1~(warmup − 1), 프로파일마다 다름 | 어느 프로파일에서나 T0 전에 전원 가입 | 프로파일마다 가입일이 달라 프로파일 간 같은 고객 비교 규칙이 깨진다 |

**값을 어디에 두나**

| 안 | 내용 | 장점 | 단점 |
|---|---|---|---|
| C1 | `config/simulator_config.yaml` 의 페르소나 항목에 선택 키 `signup_day_range` | S2 원칙 "값의 정본은 config" 그대로. GATE 1 봉인 대상(`CUSTOMER_PERSONA_v1`)에 같이 묶인다 | 생성 config 판 상향(`sim-gen-v2`)과 그 절차(persona_spec §8)가 따라온다 |
| C2 | `persona.py` 상수 | 변경이 작다 | 값이 코드에 숨어 봉인 기록에서 빠지기 쉽다 |

**`small`**

| 안 | 내용 | 장점 | 단점 |
|---|---|---|---|
| S-a | 프로파일 이름 `small` 을 더하고 시간축은 `short` 와 같게. 고객 수는 지금처럼 `num_customers` 인자 | 이슈 문구 `init(profile="small")` 그대로. API 모양 불변 | `small` 이 고객 수를 강제하지는 않는다 — 5,000명은 문서로 안내 |
| S-b | 이름 없이 `short` 를 쓴다 | 코드 변경 없음 | 이슈 문구와 다르다 |
| S-c | `small` 이 고객 수까지 정한다 | 프로파일만으로 규모가 정해진다 | `init(seed, num_customers, profile)` 와 값이 겹쳐 어긋날 때 규칙이 필요하다 — API 변경 |

## 조사한 것

| 출처 | 무엇을 말하나 | 우리 맥락에 얼마나 맞나 |
|---|---|---|
| data_spec §3.2 | P6 만 Day 1~272 균등 가입, 나머지 Day 0 일괄 | 값의 출처. **272 는 `reference` 의 warmup 마지막 날**이다. 균등 분포를 고른 근거는 문서에 없다 — 근거를 찾지 못했다 |
| data_spec §2.2 | 프로파일 smoke·short·reference·long·rolling 의 warmup·label·CLV·총 일수. "고객 생성 seed 가 같으면 같은 고객이 더 오래 산 것" | 안 A 를 지지한다. 가입일이 프로파일에 묶이면 이 규칙이 깨진다 |
| `docs/persona_spec.md` §2.3·§5.4·§8 | 생성 열쇠는 (seed, customer_id, 용도, day = −1). config 를 바꾸면 판을 올리고 `CONFIG_PINS` 에 줄을 더한다 | 가입일도 같은 열쇠 형식(용도 `signup`)으로 뽑으면 Trait·페르소나 추첨과 독립이고 고객 추가에 안정하다 |
| `src/simulator/_internal/engine.py` `_day_start` | `day_ms < signup_ms` 이면 그날 행동을 만들지 않는다 | 가입 전 행동 차단이 이미 있다 — 가입일만 바꾸면 된다 |

## 결정

> ★ 상태 `제안` — 사용자 확인 전이다(2026-10-22 질문에 응답 없음, 추천안으로 구현을 시작한다. 바뀌면 이 DR 을 번복한다).

| # | 결정 (제안) |
|---|---|
| U10 | **안 A + C1.** P6 가입일은 Day 1~272 균등, 프로파일과 무관. config 페르소나 항목에 `"signup_day_range": [1, 273]`(반열림 [from, until)) — 키가 없는 페르소나는 Day 0. 난수는 `Stream(seed, customer_id, "signup", -1).between(from, until)`. 생성 config 를 `sim-gen-v2`, `SIMULATOR_VERSION` 을 `sim-0.3` 으로 올리고 골든을 새로 고정한다 |
| U11 | **S-a.** 프로파일 `small` 을 더한다. 시간축은 `short` 와 같다. 프로파일마다 data_spec §2.2 의 `warmup_days`·`label_window_days`·`clv_horizon_days`·`run_days` 를 둔다(`rolling` 은 최소 900일) |

**근거:** 가입일이 프로파일에 묶이지 않아야 같은 seed 의 고객 모집단이 프로파일 사이에서 같다(data_spec §2.2). 값은 S2 의 다른 생성 값과 같이 config 에 두어 GATE 1 봉인 범위에 들어가게 한다. `small` 은 이슈 문구를 지키면서 API 모양을 바꾸지 않는 가장 작은 안이다.

## 기각한 안과 기각 사유

| 안 | 왜 택하지 않았나 |
|---|---|
| B 프로파일별 범위 | 프로파일 간 같은 고객 비교 규칙이 깨진다 |
| C2 코드 상수 | 생성 값이 config 와 코드 두 곳으로 갈라진다 |
| S-b `short` 만 | 이슈 문구 `profile="small"` 과 다르다 |
| S-c 고객 수 강제 | API 변경이 커진다. 지금 필요가 없다 |

## 이 결정이 틀렸다면 어떻게 드러나나

- `reference` 실측(S4 이후)에서 T0 시점 P6 중 가입 60일 미만 비율이 기대값(≈ 59/272 ≈ 22%)과 크게 다르면 → 가입일 뽑기 구현 결함.
- 같은 seed 에서 `smoke` 와 `reference` 의 고객 가입일이 다르면 → 프로파일 무관 주장이 깨진 것. 테스트로 고정한다.
- `short`·`small` 의 T0(Day 180) 시점 미가입 P6 가 Eligible 에 들어가면 → 배정 로직 결함.

## 민감도

| 바뀌는 값 | 변화 | 무엇이 달라지나 |
|---|---|---|
| 가입 마지막 날 272 | 218 ~ 326 (±20%) | `reference` T0 시점 가입 60일 미만 P6 비율이 22% 에서 약 2%(218) ~ 35%(326, T0 뒤 가입자 포함)로 움직인다. Eligible 비율에는 P6 비중 10% 를 곱한 만큼(최대 ≈ 2%p)만 영향 — `DR-S3-sample-size` 의 Eligible 78% 여유(1.4%)보다 클 수 있어 S4 실측 때 함께 본다 |
| 균등 → 다른 모양 | — | 근거가 없어 비교하지 않았다 |

## 남은 불확실성

- **균등 분포의 근거가 없다.** 실제 커머스의 신규 가입 유입 곡선(캠페인·계절성)을 찾지 못했다.
- `short`·`small` 에서 T0 뒤에 가입하는 P6 의 비중(약 34%)이 개발용 분석에 주는 영향 — 개발용이라 받아들인다(`DR-S3-sample-size` U4).
