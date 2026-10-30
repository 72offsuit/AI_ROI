# DR-183-repeat-exposure — 처치 반복 노출 시 반응 감쇠 (#183 ④)

| | |
|---|---|
| 태스크 | #183 ④ 처치 반복 노출 시 반응 감쇠(피로 동학, 닫힌 #78) |
| 작성 | 시뮬레이터 팀 성환(limtjdghks) · Claude(Phillip 구현) · 2026-10-28 |
| 상태 | 확정 — 형태·기본값은 사용자 승인 계획(2026-10-28). 계수 값은 **외부 정량 근거 없음** |

## 무엇을 정하는가

같은 고객이 처치를 여러 번 받을 때 반응 유형(Positive · Neutral · Negative) 확률이 어떻게 바뀌는지 — 노출 수 n 의 정의, 감쇠 형태, 계수 기본값.

## 정하지 않으면 무엇이 막히나

반응 유형은 고객×처치 단위로 영구 고정이다(`treatment.py` 변경 전 `:28-37`). 다중 T0 배정(`DR-S3-assignment`)에서 같은 쿠폰을 세 번 받은 고객이 첫 번째와 똑같이 반응한다 — #78 이 요구한 "반복 노출 시 반응률 감쇠 곡선" 을 낼 수 없고, data_spec `:733` "후반 T0 의 ATE 가 낮아지는 것은 설계된 현상" 이 성립하지 않는다.

## 선택지

| 안 | 내용 | 장점 | 단점 |
|---|---|---|---|
| A | n = 처치 종류 무관 누적(마지막 배정 이전, 같은 시각은 한 번, T0 제외) | #78 "같은 쿠폰을 세 번", data_spec `:727` "marketing_fatigue 누적" 에 맞다. 새 상태 키 없이 `assignments` 에서 계산 | 처치 종류별 차이를 표현하지 않는다 |
| B | 같은 처치만 셈 | 처치별 습관화 | 피로(고객 단위 Trait)와 의미가 어긋난다 |
| C | A + 시간에 따른 회복(반감기) | 오래 쉬면 회복 | 근거 없는 계수가 하나 더 는다 |

형태: Positive = 첫 노출 확률 × (1 − decay)^n, 바닥 floor%(기하 감쇠) / 선형 감쇠. Negative = 피로 × min(scale + n × step, max)%.

## 조사한 것

| 출처 | 무엇을 말하나 | 우리 맥락에 얼마나 맞나 |
|---|---|---|
| 닫힌 #78 "추가 요구" | "같은 쿠폰을 세 번 받은 고객은 첫 번째와 같이 반응하지 않는다", 증거로 감쇠 곡선 | 요구 원문 |
| `docs/data_spec.html:170` · `:727` · `:733` | 처치 1회 노출이 기본, 반복 노출은 marketing_fatigue 를 누적, 후반 T0 ATE 하락은 설계된 현상 | 형태(누적)의 근거 |
| PRD A4(`Plan/AI_Retention_ROI_PRD_v2.md:2793-2794`) · SRS SIM-008(`:614-624`) | 일부 고객은 Marketing Fatigue 로 Negative | Negative 를 피로에 비례시키는 근거 |
| `docs/research/data_grounding.md` marketing_fatigue | **근거 없음**(Mailchimp 구독해지율은 근거 없음 확인용) | 계수에 외부 정량 근거가 없다 |
| `DR-S1-world-state:82` | 배정·노출 이력을 상태로 둔 목적이 반복 노출 피로(#78) | n 을 `assignments` 에서 계산하는 근거 |

## 결정

**A + 기하 감쇠.** `src/simulator/_internal/treatment.py`:

- `prior_exposures` 가 n 의 유일한 정의다. 실제 `campaign_exposed` 수와 같음을 대조했다.
- `negative_ppm` = 피로 × min(`negative_scale_pct` + n × `negative_step_pct`, `negative_max_pct`) // 100. `positive_ppm` = 첫 노출 확률 × keep(n), keep 은 노출마다 (100 − `positive_decay_pct`)% 곱, 첫 노출 대비 `positive_floor_pct`% 에서 멈춘다.
- **n = 0 이면 이전 식 그대로** — 단일 배정 결과가 바뀌지 않는다(구현 시점 sim-0.5 config 에서 가드레일 seed 42·2,000명 결과 표·리포트·반사실 1,304행 바이트 동일).
- 난수 열쇠(`response`·`response:` + 처치 id)는 그대로, n 은 문턱에만 들어간다(CRN). 한 고객의 유형은 Positive → Neutral → Negative 방향으로만 움직인다. 캐시 키는 `(cid, tid, n)`. 반사실(`potential_outcomes`)도 같은 이력으로 n 을 센다.
- config `behavior.treatment.repeat_exposure` = `positive_decay_pct` 10 · `positive_floor_pct` 50 · `negative_step_pct` 5 · `negative_max_pct` 60(+ `note` "외부 정량 근거 없음"). Negative 는 n = 4 에서 상한, Positive 는 n = 7 에서 바닥. **→ #196 에서 `negative_scale_pct` · `negative_max_pct` 를 모두 100 으로 올렸다 — 첫 노출 배율이 이미 상한이라 반복 노출은 Positive 만 줄이고 Negative 쪽 감쇠는 꺼진다(`DR-196-sleeping-dog-path` U3). 아래 「60%」 서술은 이 결정 당시 기록이다.**

반응 유형 비율(seed 42, 5,000명 small, Positive / Negative):

| n | T1 | T2 | T3 | T4 |
|---|---|---|---|---|
| 0 | 44.42 / 10.70% | 46.26 / 10.70% | 45.02 / 10.70% | 49.66 / 10.70% |
| 1 | 39.30 / 11.86% | 40.72 / 11.86% | 40.26 / 11.86% | 44.26 / 11.86% |
| 2 | 34.44 / 13.32% | 35.78 / 13.32% | 35.74 / 13.32% | 39.20 / 13.32% |
| 3 | 30.54 / 15.04% | 31.58 / 15.04% | 31.56 / 15.04% | 34.22 / 15.04% |

참 ATE(구매) — **sim-0.6 정본 config**, seed 42 · 2,000명 small · 180일 진행 뒤 직전 42일 구매 고객 1,263명(2026-10-29 재보정 config), 과거 T3 노출 n 번을 43일 간격(효과 창 밖)으로 합성. 재현 `PYTHONPATH=. python scripts/research/repeat_exposure_curve.py --seed 42 --customers 2000`. n = 0 행은 sim-0.6 가드레일 값과 같다:

| n | T1 | T2 | T3 | T4 |
|---|---|---|---|---|
| 0 | 4.83%p | 3.25%p | 4.75%p | 3.33%p |
| 1 | 3.96%p | 2.38%p | 3.56%p | 2.45%p |
| 2 | 3.33%p | 1.74%p | 3.09%p | 2.06%p |
| 3 | 2.69%p | 1.27%p | 2.53%p | 1.58%p |

위 반응 유형 비율 표는 Trait 과 처치 계수만 읽어 sim-0.5·0.6 이 같다. 감쇠 형태(기하 감쇠·바닥·Negative 상한)는 `tests/test_simulator_fatigue.py` `TestDecayShapeIsPinned` 가 손 계산 정수와 5,000명 n = 0..8 인원 골든으로 고정한다(선형 감쇠·step 변경·바닥/상한 무시를 넣으면 실패).

**근거:** 요구가 "고객 단위 피로 누적" 이고 그 이력이 이미 상태에 있다. 기하 감쇠 + 바닥은 큰 n 에서도 범위가 보장된다. 계수는 근거가 없어 "첫 노출 절반 아래로, 피로의 60% 위로 가지 않는다" 는 보수적 범위로만 정했다 — AI 성능을 보지 않았다.

## 기각한 안과 기각 사유

| 안 | 왜 택하지 않았나 |
|---|---|
| B(같은 처치만) | 고객 단위 Trait 인 피로와 의미가 어긋난다 |
| C(시간 회복) | 근거 없는 계수가 하나 더 는다 — 후속으로 남긴다 |
| 선형 감쇠 | 바닥 처리가 따로 필요하고 n 이 크면 0 이 된다 |
| 새 난수 스트림 | CRN 이 깨지고 단일 배정 결과가 바뀐다 |
| 상태에 노출 수 키 추가 | `FORMAT_VERSION` 상향이 필요하다. `assignments` 로 계산된다 |

## 이 결정이 틀렸다면 어떻게 드러나나

- 반복 배정 실험에서 후반 T0 ATE 가 0 근처로 무너지면 감쇠가 과하다. 위 표에서 T2 는 n = 3 에 1.27%p(첫 노출의 39%)로 크게 줄어든다 — Positive 감소와 Negative 증가가 겹치기 때문이다.
- 단일 배정 가드레일 결과가 바뀌면 n = 0 보존이 깨진 것이다(`tests/test_simulator_fatigue.py`).

## 민감도

계수 ±20%(decay 8~12, step 4~6)는 n ≥ 1 의 반응 비율만 바꾼다. 단일 배정 실행(가드레일·realism 실측·GATE 판정)은 n = 0 이라 영향이 없다. 영향은 다중 T0 반복 배정 전략에서 후반 ATE 크기로 나타난다.

## 남은 불확실성

- 계수 4개에 외부 정량 근거가 없다. 반복 노출 감쇠의 외부 자료(리타게팅 피로 등)를 찾으면 대조한다.
- ATE 감쇠가 Positive 비율 감쇠보다 가파르다. "보수적" 기준이라면 step·decay 를 낮출지 다시 볼 수 있다 — AI 성능과 무관하게, 외부 근거가 생길 때 정한다.
- 시간에 따른 회복(C)은 없다.
