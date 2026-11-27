# 시뮬레이터 모수 외부 근거 대조 (Data Grounding)

| | |
|---|---|
| 대상 | `AI_ROI/config/simulator_config.yaml` (`config_version: sim-gen-v2`) · `config/economic_config.yaml` · PRD §5·§15·§17·§18·§24·§27·§28 |
| 작성 | 데이터 근거 리서처 · 2026-10-22 |
| 범위 규칙 | `results/`·`src/decision/`·모델 성능 문서는 읽지 않았다. **어떤 권고도 AI 성능을 근거로 하지 않는다**(SRS FREEZE-002). 근거는 외부 자료와 가드레일뿐이다 |
| 결정권 | 이 문서는 대조와 권고만 한다. 값을 바꿀지는 사람이 정한다 |
| 직접 계산 | Instacart 2017 원자료와 dunnhumby/84.51° Complete Journey 2.0 원자료를 내려받아 직접 집계했다. 우리 config 의 혼합 모집단 모멘트도 n=26,000 몬테카를로로 다시 계산했다(`our_mix.py` 와 그 출력은 시뮬 팀 내부 — 시스템 팀은 열지 않는다, #163 리드 요청 6). 스크립트는 `scripts/research/`, 출력은 `docs/research/computed/` 에 있다 |
| 원자료 묶음 | `research/raw_korea.md`(한국 통계 조사 원본) · `research/raw_uplift.md`(업리프트·리텐션 문헌 조사 원본) · `research/sources.json`(출처 기계가독판) |

**읽는 법.** 생성 모수 대조("우리 값")는 config 의 생성 모수만으로 계산한 값이고, 시뮬 팀 내부 문서에 있다. S4 행동식(감쇠·계절성·cycle_factor)이 들어간 **실현값은 다르다.** 그래서 생성 모수 대조는 "생성 모수가 외부 자릿수와 맞는가"를 보고, §4 는 "실현 데이터가 외부 stylized fact 를 재현하는가"를 볼 계획을 적는다.

**판정 기준.** 정합 = 외부 값·범위 안이거나 정의 차이를 감안해 같은 자릿수. 조정 권고 = 정의를 맞춰도 어긋남. 근거 없음 = 정량 근거를 찾지 못함(방향 근거만 있으면 그렇게 적음). 신뢰도 = 근거 자체의 품질 × 우리 맥락과의 비교 가능성.

---

## §1 요약 (발표용 5줄)

> 생성 모수에서 계산한 값("우리 값")은 2026-11-25 시뮬레이터 팀 내부 문서 `docs/simulator_generation.md` §7 로 옮겼다(#163). 아래는 외부 값과 판정만 남긴다.

1. **핵심 행동 모수는 외부와 같은 자릿수다.** 구매 빈도 · 객단가는 국내 설문의 컬리 이용자 값(월 2.5~2.66회 · 44,800원)과, 구매 주기는 Instacart 340만 주문에서 직접 계산한 고객별 중앙값(15.0일)과, 구매율 이질성은 dunnhumby 실데이터(gamma shape 0.82)와 대조해 맞았다.
2. **경제 규칙과 이탈 정의도 실제와 맞는다.** 배송비 3,000원·무료배송 4만원은 컬리 공식 조건과 같다. 42일 이탈 정의는 실데이터 개인 구매 간격의 p95~p99 다. 생성 이탈률 가드레일 15~25%는 dunnhumby 42일 라벨 비율(10.7~31.8%) 범위 안에 있다.
3. **처치 가드레일 두 개는 공개 실험으로 받쳐진다.** ATE 3~6%p 는 기저율이 높은 리텐션 실험(X5 +3.3%p, 통신사 +5%p)과 맞는다. Sleeping Dog 8~15%는 문헌의 세그먼트 추정(10~20%, ≤25%)과 질적으로 맞는다. 단, 공개 실험 원자료(Hillstrom·Lenta·X5)를 단일·2변수 세그먼트로 직접 집계했을 때 **95% CI 상한이 0 미만인 음수 세그먼트는 0개**였다(`reference_stats.md`) — Sleeping Dog 비율은 실데이터로 확인된 값이 아니라 **문헌 기반 가정**으로 표기한다. 업리프트 원자료 4종은 직접 집계했다.
4. **가드레일에서 어긋나는 곳이 두 군데 있다.** ① 쿠폰 사용률 25~40%는 외부 값(0.6~16.6%, dunnhumby 표적 쿠폰 12%)보다 높다. ② Persuadable 20~30%는 ATE·Sleeping Dog 가드레일과 항등식(P − D = ATE)상 거의 양립하지 않는다. 생성 쪽 대조는 시뮬 팀 내부 문서에 둔다.
5. **근거가 없는 곳은 숨기지 않는다.** 대조 35개 항목 가운데 정량 근거가 있는 것은 23개(정합 16, 조정 권고 7)다. 방향 근거만 있는 것이 5개, 근거가 없는 것이 7개다. 근거 없음에는 페르소나 구성비와 가격·쿠폰·피로·리뷰 Trait 분포가 들어간다(#149 보강으로 세그먼트 구성비·리뷰는 방향 근거, 푸시 반응률은 벤더 근거로 일부 채움 — §4-1). 그래서 "유의미성"은 모수가 아니라 **실현 데이터가 외부 stylized fact 17개를 재현하는지**로 증명한다(§4).

---

## §2 모수 ↔ 근거 대조표

### 2.0 근거 확보 현황 (대조 35개 항목 — config 모수 + 가드레일 + 이탈 정의)

| 판정 | 개수 | 항목 |
|---|---:|---|
| 정량 근거 · **정합** | 16 | 구매 빈도, 객단가 수준, 객단가 격차(P2/P6), 구매 주기 수준, 구매 주기 이질성, 구매율 이질성, 지출 집중도, 배송비·임계값, 기여마진율, P1 비중(간접), P5 비중(간접), `base_churn_propensity`(간접), 생성 이탈률, ATE(조건부), Sleeping Dog 가드레일(질적), 이탈 정의 42일 |
| 정량 근거 · **조정 권고** | 7 | 쿠폰 사용률 가드레일, Persuadable 목표, `base_purchase_probability`(정의 정렬), `cart_abandonment_propensity`(조건부), `base_order_value` σ(약), `repurchase_propensity` P6(약), `brand_loyalty`(조건부) |
| 방향 근거만 | 5 | `price_sensitivity`, `coupon_sensitivity`, `shipping_fee_sensitivity`, `search_propensity`, `cs_contact_propensity`(단위 미정) |
| **근거 없음** | 7 | 페르소나 구성비 전체, P6 비중, `base_visit_frequency` 수준(앱 사용일수 미공개), `marketing_responsiveness` 분포, `marketing_fatigue` 분포, `review_propensity`, Beta κ·LogNormal σ·Gamma k 의 값(분포족은 근거 있음) |

Hidden Trait 16종만 보면 정량 근거 7 · 방향 근거 5 · 근거 없음 4 다.

### 2.1 ~ 2.5 세부 대조표 — 내부 문서로 옮겼다

생성 모수 값("우리 값")이 들어 있는 세부 대조표(핵심 행동 모수 · 페르소나 구성비 · Hidden Trait · 처치 반응 가드레일 · 퍼널)는 2026-11-23 시뮬레이터 팀 내부 문서 `docs/simulator_generation.md` §6 으로 옮겼다(#163 리드 결정 2026-11-14 — 시스템 팀 must_not_read). 옮기기 전까지 시스템 팀이 이미 읽어 온 부분이다.

외부 근거 자체(출처 · 외부 값)는 §5 참고문헌과 `research/sources.json` 에 그대로 있다. 이 문서의 판정 결과는 위 §2.0 현황표와 §1 요약으로 본다.

---

## §3 조정 권고

> **사용자 결정 (2026-10-22, 스프린트 1 #142 · #148)**
> - §3-1 쿠폰 사용률: **(a) 채택** — 분모 "쿠폰 처치군(T2·T3) 전체 중 유효기간 내 사용", 가드레일 **5~20%** (PRD 원안 25~40% 대체). "처치군 중 구매자" 분모 값은 참고로만 함께 보고
> - §3-2 Persuadable: **(a) 채택** — 목표 **11~21%**, 잠재결과 유형 정의 유지 + 항등식 P − D = ATE(±0.5%p) 검사
> - §3-3~3-5 는 S4~S6 구현(#143)에 지침으로 전달 · §3-6 약한 권고는 스프린트 후 개선 이슈

**결정은 사람이 한다.** 아래 권고의 근거는 외부 자료와 가드레일뿐이다. AI 성능 지표는 하나도 보지 않았다. 바꾸기로 하면 GATE 1 **전에** 해당 DR 을 번복하는 절차(`docs/persona_spec.md` §8)를 따른다.

우선순위는 "외부 근거와 어긋나는 정도 × 과제 가드레일에 미치는 영향"으로 매겼다.

### 3-1. 쿠폰 사용률 가드레일 25~40% — 외부 근거보다 높다 【우선 1】

- **어긋남.** 처치군 대비 쿠폰 사용률로 확인한 외부 값은 모두 **0.02~16.6%** 다. 가장 가까운 맥락인 식료품 표적 쿠폰(Complete Journey)도 캠페인 1건당 **12.0%** 다. 25~40% 를 지지하는 공개 근거는 찾지 못했다.
- **내부 제약도 있다.** 쿠폰 사용률은 "처치군의 14일 안 구매율 × 그 구매가 최소주문금액을 넘을 확률"을 넘을 수 없다.
  - T3 는 50,000원 이상 주문이 조건이라, 처치군 전원이 14일 안에 산다고 해도 금액 조건만으로 상한이 낮아진다(생성 값 기준 계산은 내부 문서 §7). 이탈 위험군(최근 구매 14일 이상 전)의 14일 구매율은 그보다 훨씬 낮다.
- **권고(둘 중 하나, 사람이 선택).**
  - (a) **분모를 명시하고 하향한다.** "처치군 전체 중 유효기간 안 사용" 기준이면 **5~20%**. 하한은 앱 자동 적용·고액 정액 쿠폰이라 우편·이메일 쿠폰(0.6~1.5%)보다 높을 것이라는 판단이고, 상한은 Complete Journey Type A 16.6% 와 디지털 쿠폰 15.8% 다.
  - (b) **분모를 "처치군 중 유효기간 안 구매자"로 바꾸고 25~40% 를 유지한다.** 이 정의의 외부 근거는 찾지 못했다. 그렇게 적어야 한다.
- **구조 권고.** 할인 오퍼의 매출 증분 중 60~90% 가 쿠폰을 쓰지 않은 고객에게서 나왔다(Sahni 2017 · Venkatesan & Farris 2012). S6 가 처치 효과를 "쿠폰을 쓴 사람"에게만 묶으면 이 사실과 어긋난다. 노출 효과 경로를 따로 둘지 S6 DR 에서 정한다.

### 3-2. 4분면 목표 Persuadable 20~30% — 다른 두 가드레일과 수학적으로 거의 양립하지 않는다 【우선 2】

- **항등식.** 잠재결과로 유형을 정의하면 Persuadable 비율 − Sleeping Dog 비율 = ATE 다.
- **충돌.** ATE 3~6%p 와 Sleeping Dog 8~15% 를 함께 지키면 Persuadable 은 **11~21%** 다. 세 가드레일이 동시에 맞는 곳은 P≈20%, D≈14~15%, ATE≈5~6%p 의 좁은 모서리뿐이다. S6 가 이 모서리를 노려 모수를 깎으면 그것이 곧 과적합이다.
- **외부.** 공개 실험에서 Persuadable 의 이론 상한이 20% 를 넘는 곳은 기저율이 높은 X5(≤39.7%)와 통신사 Operator 1(≤30%)뿐이다.
- **권고(사람이 선택).**
  - (a) Persuadable 목표를 **11~21%** 로 내린다.
  - (b) 4분면을 잠재결과 유형이 아니라 **연속 CATE 임계값**으로 정의하고 그 임계값을 문서에 고정한다. 그러면 항등식이 그대로 적용되지 않는다. 어느 정의인지가 먼저 정해져야 한다.

### 3-3. Sleeping Dog — 가드레일은 외부와 질적으로 맞는다 【우선 3】

> **원자료 교차 확인 (reference_stats, 2026-10-22).** Hillstrom·Lenta·X5 를 단일 변수 세그먼트(23~32개)·2변수 교차(202~375개)로 집계한 결과, 95% CI 상한이 0 미만인 음수 ATE 세그먼트는 **0개**(BH 보정 전 기준으로도 0개). 점추정만 음수인 셀은 있다(Lenta 29 · X5 13 · Hillstrom 여성 메일 전환 44). 따라서 아래 "외부 정합"은 **문헌 서술·모형 기반 추정과의 질적 정합**이며, 원자료의 단순 세그먼트로는 재현되지 않았다. 모델 기반 음수 세그먼트 탐지는 하지 않았다.

- **외부.** 8~15% 는 문헌과 질적으로 정합한다. Hillstrom 여성 메일 10~20%, 통신사 사례 ≤25%, 역효과 실험의 이론 경계 3.6~10.0% 가 있다. **가드레일을 바꿀 이유는 없다.**
- **생성 모수 쪽 분석과 조정 후보**는 내부 문서 `docs/simulator_generation.md` §7 에 있다(시스템 팀 must_not_read).

### 3-4. 방문당 구매확률 — 정의를 맞춰야 비교가 된다 【우선 4】

- "방문"이 세션이면 F&B 세션 전환율 4.56% 와, 접속일이면 앱 사용일수와 비교해야 한다. **권고.** 방문 정의(접속일 / 세션)를 문서에 고정한다. 생성 값과의 대조는 내부 문서 §7.

### 3-5. 장바구니 이탈 — 실현값이 식료품 하한(50%)보다 낮지 않은지 【우선 5】

- 외부: 식료품 50.03% · 전체 70.22%. **권고.** 실현 장바구니 이탈률 통과 띠를 **50~75%** 로 고정한다(§4 F9).

### 3-6. 약한 권고 (근거 품질 하~중)

| 모수 | 근거 | 왜 약한가 |
|---|---|---|
| `base_order_value` σ | Complete Journey 가구 평균 장바구니 CV 0.65 | 오프라인 소액 방문이 섞인 표본이다. 온라인 최소주문·무료배송 임계값은 하단을 눌러 이질성을 줄인다 |
| P6 `repurchase_propensity` | 컬리 신규 고객 같은 해 재구매율 61.2~75% | 회사 발표 보도이고 정의·모수 비공개 |
| `brand_loyalty` | Instacart 재주문 품목 59.9% | 미국 대행 장보기 + 아직 소비처 미정 |
| ATE 시나리오 | 리텐션 처치가 이탈을 늘린 RCT 2건(+3.6%p, +1%p) | 가드레일 자체를 바꾸자는 것은 아니다 |

지금 값과 권고 값은 내부 문서 §7 에 있다.

### 3-7. 바꾸지 말 것 (근거로 확인됨)

- 배송비 3,000원 / 무료배송 40,000원 — 컬리 비회원 조건과 정확히 같다.
- 구매 주기 · 객단가 수준 · 구매 빈도 — 실데이터·국내 설문과 같은 자릿수다(생성 값은 내부 문서 §7).
- 구매율 이질성 — 식료품 실데이터(gamma shape 0.82)와 가깝다.
- 이탈 정의 42일 — 실데이터 개인 구매 간격 p95~p99 이고, 생성 이탈률 15~25% 가 외부 라벨 비율 범위 안에 있다.

---

## §4 "생성 데이터 유의미성" 검증 계획

**원칙.** "유의미하다"를 "모수가 그럴듯하다"로 증명하지 않는다. **실현 이벤트 로그에서 집계한 값이 외부 실데이터의 stylized fact 를 재현하는지**로 증명한다.
- 비교는 S4·S5·S6 실현 데이터로 한다. 생성 모수 대조(시뮬 팀 내부)는 출발점일 뿐이다.
- 비교 기준값은 GATE 1 **전에** 이 표로 고정한다. 결과를 본 뒤 기준값을 바꾸지 않는다.
- AI 성능 지표(AUC·Qini 등)는 이 검증에 들어가지 않는다.
- 같은 집계 코드를 외부 데이터(Instacart·Complete Journey)와 우리 로그에 **똑같이** 돌린다. 집계 정의 차이로 생기는 거짓 불일치를 막는다. `scripts/research/*.py` 가 외부 쪽 구현이다.

| # | Stylized fact | 우리 로그에서 잴 값 | 비교 기준값(통과 띠) | 비교 데이터셋/출처 | 왜 중요한가 |
|---|---|---|---|---|---|
| F1 | **구매 간격 분포가 오른쪽 꼬리가 긴 단봉형**이고 주 단위 피크가 있다 | 고객별 연속 주문 간격 분포: 중앙값, 평균, p75, p90, 7일 배수 피크 | 주문 단위 중앙값 **5~10일**, 평균 **9~15일**, p75 **12~20일**(Instacart 7 · 11.1 · 15). 7일 피크가 있으면 가점(Instacart 7일 = 10.0%) | Instacart 2017 [S01] | 구매 주기가 너무 규칙적이거나(시계) 지수분포처럼 무기억이면 이탈 신호가 비현실적으로 쉬워지거나 어려워진다 |
| F2 | **고객 안 간격이 불규칙**하다(시계도 아니고 무기억도 아님) | 주문 5회 이상 고객의 간격 CV 중앙값 | **0.45~0.70**(Instacart 0.571. 지수분포면 1.0, 시계면 0) | [S01] | PRD §26 "구매 간격 증가"를 잡음 속 신호로 만든다 |
| F3 | **고객별 평균 구매 주기**가 넓게 퍼진다 | 고객별 평균 간격의 중앙값, ln-sd | 중앙값 **12~18일**(Instacart 15.0일·컬리 월 2.5~2.66회 ⇒ 11~12일), ln-sd **0.5~0.9**(Instacart 0.53 절단 · Complete Journey 0.89 오프라인) | [S01][S02][S20][S21] | 페르소나 혼합이 이질성을 제대로 만드는지 |
| F4 | 월 구매 빈도 · 객단가 자릿수 | 활성 고객의 월 주문 수 평균, 주문 금액 평균 | 월 **2.0~3.2회**(컬리 2.5~2.66), 객단가 **38,000~55,000원**(컬리 44,800, 쿠팡 35,400~38,600, SSG 57,300~59,400) | [S20][S21] | 국내 맥락의 자릿수 앵커. 배 단위로 벗어나면 DR 이 이미 "재개" 조건으로 적어 둔 상태다 |
| F5 | **구매율 이질성이 크다**(NBD 계열) | 고객별 12주 주문 수 분포의 분산/평균비, Gamma shape 적합값 | shape **0.5~1.5**(Complete Journey 0.82, Instacart 1.72 상한) | [S02][S01] | 상위 고객이 매출을 끌고 다수는 드문드문 산다 — Pareto 와 이탈 분포의 바탕 |
| F6 | **Pareto 집중** | 1년 매출 상위 20%·10% 고객 비중 | 상위 20% **0.53~0.73**(CJ 0.545 · Instacart 주문 0.526 · M&W 0.67 · KSW 0.73). 상위 10% **0.33~0.50** | [S02][S01][S08][S09] | VIP 정의, CLV 꼬리, ROI 집중도의 현실성 |
| F7 | 객단가 분포가 로그정규에 가깝고 오른쪽 꼬리가 있다 | 주문 금액의 ln-sd, 고객 평균 객단가의 CV | 주문 금액 ln-sd **0.4~0.8**(CJ $20 이상 장보기 0.59). 고객 평균 객단가 CV **0.5~0.8**(CJ 0.65) | [S02] | 금액 이질성이 너무 작으면 CLV·고가치 세그먼트가 뭉개진다 |
| F8 | **무료배송 임계값 바로 위에 주문이 몰린다** | 주문 금액 히스토그램에서 [40,000, 44,000) 구간 밀도 ÷ [36,000, 40,000) 구간 밀도 | 비율 **> 1**(방향 검정). 52%가 기준을 맞추려 상품을 추가한다는 설문 | Lewis 2006 · Lewis·Singh·Fay 2006 · UPS [S15][S16][S14] | 배송비 민감도 Trait 가 실제로 행동에 반영되는지 보는 가장 직접적인 신호 |
| F9 | 퍼널 전환율 | 방문→장바구니, 장바구니→구매, 장바구니 이탈률 | 장바구니 이탈률 **50~75%**(식료품 50.03 · 전체 70.22). 방문→구매는 "방문" 정의에 맞춰 세션 기준이면 **3~8%**(F&B 4.56) | [S03][S07][S04] | 탐색형 페르소나와 장바구니 Trait 의 현실성 |
| F10 | 상품 재주문 비중 | 주문 품목 중 과거 구매 품목 비율 | **0.50~0.65**(Instacart 0.599) | [S01] | 반복구매형 장보기의 정체성. 너무 낮으면 "장보기"가 아니다 |
| F11 | 신규 고객 재구매 | 가입 첫 구매 후 365일 안에 2번째 구매한 비율 | **0.55~0.75**(컬리 2019~2021: 61.2·65.2·75%) | [S30] | P6 온보딩 서사의 현실성 |
| F12 | **생성 이탈률**(42일 무구매) | Eligible 고객 중 T0 이후 42일 무구매 비율 | 가드레일 **15~25%**. 외부 참조: 활성 가구 전체 10.7~13.1%, 최근 구매 14일 이상 전 가구 28.6~31.8% | [S02] 직접 계산(3개 시점) · PRD §24 | 과제 MUST. 외부 띠 안에 있음을 함께 보인다 |
| F13 | **일시 공백 뒤 복귀가 흔하다** | 42일 이상 공백을 겪은 고객 중 이후 다시 구매한 비율, 1년 중 42일 이상 공백을 한 번이라도 겪은 고객 비율 | 복귀가 **0보다 확실히 크다**(CJ: 1년간 가구 43.5%가 42일+ 공백 뒤 복귀. 단 CJ 는 "자주 사는 가구" 선발 표본이라 상한) | [S02] | 이탈이 흡수 상태(한 번 빠지면 영원히)면 이탈 예측이 비현실적으로 쉬워진다(PRD Risk 2) |
| F14 | 처치 효과 크기(ATE) | T3 vs T0 의 42일 유지율 차(무작위 배정 ITT) | 가드레일 **3~6%p**. 외부 참조: X5 +3.32%p(구매, 기저 60%), 통신사 +5%p(유지). **상대 효과**도 함께 본다: 외부 +5.5%~+7.4%(X5·Lenta) | [S43][S44][S48] 원자료 직접 계산 | 과제 가드레일. 상대 효과까지 보면 "기저율이 높아서 맞은 것"인지 구분된다 |
| F15 | 쿠폰 사용률 | 처치군 중 유효기간 안 쿠폰 사용 비율(**분모 명시**) | §3-1 결정 뒤 고정. 외부: Complete Journey 12.0%(캠페인당), 0.6~16.6% | [S02][S53] | 과제 가드레일. 지금 띠는 외부보다 높다 |
| F16 | 반응 이질성(4분면) | ground truth 의 Sleeping Dog(D)·Persuadable(P) 비율, 그리고 **P − D 와 ATE 의 일치** | D **8~15%**(외부 질적 정합). P 는 §3-2 결정 뒤 고정. **항등식 P − D = ATE 가 ±0.5%p 안에서 성립**해야 함(잠재결과 정의일 때) | [S41][S46][S47][S48] · 항등식 | PRD §27. 항등식 검사는 S6 구현 결함을 잡는 무료 검사다 |
| F17 | 처치 효과가 쿠폰 사용 밖에서도 생긴다 | 매출 증분 중 쿠폰 미사용 고객 몫 | **> 0**, 외부 60~90% | [S51][S52] | 처치 반응 구조의 현실성(§3-1 구조 권고를 택했을 때) |

**판정 방식.** 각 항목을 통과 / 경계(띠에서 ±20% 이내 이탈) / 실패로 적는다. 실패 항목은 원인 Trait 을 내부 문서 `docs/simulator_generation.md` §6 에서 찾아 **GATE 1 전에** 해당 DR 을 재개한다. 근거는 이 표와 외부 자료뿐이고 AI 결과는 쓰지 않는다.

> **GATE 1 판정 규칙은 `docs/decisions/DR-208-gate1-acceptance-criteria.md` 가 정한다**(seed · 표본 · 필수/기록 구분 · seed 집계, 기계가독 판본 `config/simulator_gate1_acceptance.yaml`). 띠 값의 정본은 이 표 그대로다. 단 기록 검사 항목(F1~F11 · F13 · F17)의 실패와 값 없음(no_data)은 위 "GATE 1 전에 DR 재개" 대신 **봉인 PR 전 DR 기록 + 후속 이슈**로 다룬다(DR-208, 리드 결정 2026-11-13).

**발표용 한 줄.** "생성 데이터는 실제 장보기 데이터 2종(Instacart 340만 주문, dunnhumby 2,469가구 1년), 공개 업리프트 실험 4종(Hillstrom·Criteo·X5·Lenta), 국내 통계(오픈서베이·국가데이터처·컬리 공개 수치)에서 뽑은 17개 stylized fact 와 대조해 검증한다."

---

## §4-1 근거 보강 (#149 · 1anminJ · 2026-10-22)

§2.0 의 "근거 없음 7항목 · 미확인 3건 · §3-3 Sleeping Dog" 빈칸만 다시 찾았다. 표기: **원문**(원문 PDF·공식 페이지 직접 확인) / **2차**(보도·검색 요약) / **못 찾음**. 상세·인용문은 #149 코멘트.

| 항목 | 결과 | 판정 변화 |
|---|---|---|
| 국내 온라인 장보기 세그먼트 구성비 | KREI「2023 가공식품 소비자 태도조사」(국가승인통계 114053, 2,203가구, **원문**): 가공식품 온라인 의존도 "대부분 온라인" 14.4% · "특정 상품만" 43.4% · "구입 안 함" 42.2%. 온라인 구입 가구의 구입 주기 주 1회 이상 18.4% · 2주 1회 38.8% · 월 1회 이하 42.8%(분모 추정). 페르소나 6종 구성비 자체는 못 찾음 | 근거 없음 → **방향 근거(간접)** |
| 신규 고객(P6) 비중 | 컬리 2024 경영실적(**원문**)에 신규 고객 수·비중 없음 | 근거 없음 유지 |
| 장보기 앱 월 사용일수 | 와이즈앱 지표 유료 비공개 | 근거 없음 유지 |
| 마케팅 반응성·피로 분포 | 개인 단위 분포 자료 없음(벤더 설문만) | 근거 없음 유지 |
| 리뷰 성향 | 주문당 리뷰율 1~5%(상위 22%) — 해외 벤더 **2차**. 국내 주문당 작성률 못 찾음 | 근거 없음 → **방향 근거(약)** |
| 국내 쿠폰 사용률 | 발급 대비 사용률 공식 통계 없음 | 미확인 유지 — 가드레일 5~20% 근거는 계속 §3-1 · 내부 문서 §6 |
| 국내 앱 푸시 반응률 | Blux「2026 커머스 브랜드 푸시알림 평균 오픈율」(국내 커머스 50여 개사·푸시 3억 건, **원문**): 클릭률 중앙 **1.5%** · 상위 10% 6.7% · 하위 10% 1.0% | 미확인 → **벤더 1개 근거** |
| 컬리 공식 객단가 | 공식 실적에 없음 — 오픈서베이 44,800원이 유일 | 미확인 유지 |
| Sleeping Dog | Anderson & Simester 2004 *Marketing Science* 23(1) 무작위 현장실험(기존 고객 56,466명, **원문 표**): 할인 처치의 장기 효과 **부호가 고객군마다 다름**(비빈번·비최근 +0.262 유의, 음수 세그먼트는 유의하지 않음), 할인 후 구매 단가 하락. 처치→이탈 증가의 **직접 근거로는 약함** | §3-3 "문헌 기반 가정" 보강(비율 근거 아님) |

## §5 참고문헌

`sources.json` 과 같은 목록이다. id 는 본문 [Sxx] 와 대응한다. 유형의 "(2차)"는 원문이 아니라 보도·요약으로 확인했다는 뜻이고, "(직접 계산)"은 공개 원자료를 내려받아 집계했다는 뜻이다.

- **[S01]** Instacart Online Grocery Shopping Dataset 2017 (Kaggle 'Instacart Market Basket Analysis') — 원자료 직접 계산(HF 미러 attik/Instacart-Market-Basket-Analysis, orders.csv 108,968,645 bytes). 2017. dataset(직접 계산) — https://huggingface.co/datasets/attik/Instacart-Market-Basket-Analysis
- **[S02]** dunnhumby / 84.51° The Complete Journey 2.0 (R 패키지 completejourney 데이터) — 원자료 직접 계산. 2017. dataset(직접 계산) — https://cran.r-project.org/web/packages/completejourney/vignettes/completejourney.html ; https://github.com/bradleyboehmke/completejourney/tree/master/data
- **[S03]** Baymard Institute — Cart Abandonment Rate Statistics. 2025. industry_benchmark — https://baymard.com/lists/cart-abandonment-rate
- **[S04]** Dynamic Yield eCommerce Benchmarks — Conversion Rate. 2026. industry_benchmark — https://marketing.dynamicyield.com/benchmarks/conversion-rate/
- **[S05]** Dynamic Yield eCommerce Benchmarks — Add-to-cart / Cart abandonment. 2026. industry_benchmark — https://marketing.dynamicyield.com/benchmarks/add-to-cart-rate/ ; https://marketing.dynamicyield.com/benchmarks/cart-abandonment-rate/
- **[S06]** Dynamic Yield eCommerce Benchmarks 출시 보도 (Enterprise Times / DestinationCRM). 2020. industry_benchmark(2차) — https://www.enterprisetimes.co.uk/2020/11/24/dynamic-yield-launches-ecommerce-benchmarks-a-free-tool-to-unlocking-industry-metrics/
- **[S07]** Stripe — Cart abandonment statistics: How rates vary by industry (업종 수치는 digitalapplied.com 인용). 2026. industry_benchmark(2차) — https://stripe.com/resources/more/cart-abandonment-statistics
- **[S08]** McCarthy & Winer (2019) The Pareto rule in marketing revisited: is it 80/20 or 70/20? Marketing Letters 30(2):139-150. 2019. academic(초록) — https://ideas.repec.org/a/kap/mktlet/v30y2019i2d10.1007_s11002-019-09490-y.html
- **[S09]** Kim, Singh & Winer (2017) The Pareto rule for frequently purchased packaged goods. Marketing Letters 28(4):491-507. 2017. academic(초록, DR 인용) — https://ideas.repec.org/a/kap/mktlet/v28y2017i4d10.1007_s11002-017-9442-5.html
- **[S10]** Sharp, Romaniuk & Graham (2019) Marketing's 60/20 Pareto Law (Ehrenberg-Bass). 2019. academic(검색 요약) — https://openresearch.lsbu.ac.uk/item/88vw1
- **[S11]** Fader, Hardie & Lee (2005) 'Counting Your Customers' the Easy Way: BG/NBD. Marketing Science 24(2):275-284. 2005. academic — https://ideas.repec.org/a/inm/ormksc/v24y2005i2p275-284.html
- **[S12]** Fader & Hardie (2013) The Gamma-Gamma Model of Monetary Value (note). 2013. academic(DR 인용) — https://www.brucehardie.com/notes/025/gamma_gamma.pdf
- **[S13]** 쿠폰·가격 민감도 방향 문헌: Narasimhan (1984) Marketing Science 3(2); Lichtenstein, Netemeyer & Burton (1990) JM 54(3), (1995) JCR 22(3). 1984. academic(DR 인용, 초록) — https://ideas.repec.org/a/inm/ormksc/v3y1984i2p128-147.html
- **[S14]** UPS Pulse of the Online Shopper (보도 인용; 판·연도 미확인). 연도 미확인. industry_survey(2차) — https://www.jckonline.com/editorial-article/should-you-be-offering-free-shipping-online
- **[S15]** Lewis (2006) The effect of shipping fees on customer acquisition, customer retention, and purchase quantities. Journal of Retailing 82(1):13-23. 2006. academic(2차 요약) — https://doi.org/10.1016/j.jretai.2005.11.005
- **[S16]** Lewis, Singh & Fay (2006) An Empirical Study of the Impact of Nonlinear Shipping and Handling Fees on Purchase Incidence and Expenditure Decisions. Marketing Science 25(1):51-64. 2006. academic(초록) — https://ideas.repec.org/a/inm/ormksc/v25y2006i1p51-64.html
- **[S17]** Buckinx & Van den Poel (2005) Customer base analysis: partial defection of behaviourally loyal clients in a non-contractual FMCG retail setting. EJOR 164(1):252-268. 2005. academic(초록) — https://ideas.repec.org/a/eee/ejores/v164y2005i1p252-268.html
- **[S18]** Brick Meets Click · Mercatus — eGrocery Performance Benchmark 2023. 2023. industry_benchmark — https://www.mercatus.com/newsroom/egrocery-performance-benchmark-2023/
- **[S19]** NHN데이터 「이커머스 성장을 위한 데이터 인사이트 보고서」 (바이라인네트워크 보도). 2022. korea_industry(2차) — https://byline.network/2022/10/1004_02
- **[S20]** 오픈서베이 「온라인 식료품 구매 트렌드 리포트 2023」 (바이라인네트워크·아주경제 보도). 2023. korea_survey(2차) — https://byline.network/2023/01/30_0976
- **[S21]** 오픈서베이 「온라인 식료품 구매 트렌드 리포트 2025」 (오픈서베이 블로그 원문 + 이투데이·위키트리 보도). 2025. korea_survey — https://blog.opensurvey.co.kr/trendreport/online-grocery-2025/ ; https://www.etoday.co.kr/news/view/2444070
- **[S22]** 컬리 공식 상품 상세 페이지(배송 조건). 2026. korea_company(원문) — https://www.kurly.com/goods/1000668010
- **[S23]** 컬리멤버스 보도 (위키트리 2026-02-19, 비즈워치 2026-03-12). 2026. korea_news(2차) — https://www.wikitree.co.kr/articles/1119026 ; https://news.bizwatch.co.kr/article/consumer/2026/03/11/0040
- **[S24]** 한국경제 2026-05-27 컬리 매출총이익률 보도. 2026. korea_news(2차) — https://www.hankyung.com/article/202605272197g
- **[S25]** 한국농촌경제연구원(KREI) 2025 식품소비행태조사 결과 보도(노컷뉴스) 및 설문지. 2025. korea_survey(2차) — https://www.nocutnews.co.kr/news/6442474 ; https://www.krei.re.kr/foodSurvey/board/atchDown.do?no=113681
- **[S26]** 국가데이터처 「2025년 12월 및 연간 온라인쇼핑동향」 보도자료(PDF 원문). 2026. korea_official(원문) — https://mods.go.kr/boardDownload.es?bid=241&list_no=443337&seq=1
- **[S27]** 컬리 2025 연간 실적 보도(시사경제 2026-03-04). 2026. korea_news(2차) — https://sateconomy.co.kr/news/view/1065591756041953
- **[S28]** KREI 2024 가공식품 소비자 태도 조사(이코노미스트 2025-05-06 보도). 2025. korea_survey(2차) — https://economist.co.kr/article/view/ecn202505060014
- **[S29]** 모바일인덱스 인용 보도(CEO스코어데일리 2026-01-06) 등 앱 이용 지표. 2026. korea_news(2차) — https://www.ceoscoredaily.com/page/view/2026010613013974822
- **[S30]** 컬리 재구매율 보도(벤처스퀘어 2020-04-03, 아시아경제 2023-01-04). 2020. korea_news(2차, 회사 발표) — https://www.venturesquare.net/806256/ ; https://core.asiae.co.kr/article/2023010310523087533
- **[S31]** Mailchimp 이메일 벤치마크(2015 데이터, 검색 요약 2차). 2015. industry_benchmark(2차) — https://www.smartbugmedia.com/blog/every-email-marketing-benchmark-you-will-ever-need
- **[S32]** Macha 블로그 — Support tickets per order by ecommerce vertical (Gorgias 데이터 인용). 2026. industry_benchmark(2차, 벤더) — https://www.getmacha.com/blog/support-tickets-per-order-by-ecommerce-vertical
- **[S33]** Shopify Engineering — How Shopify Merchants Can Measure Retention. 2017. industry_practice — https://shopify.engineering/how-shopify-merchants-can-measure-retention
- **[S34]** Indeed Engineering — Defining Churn (Dapaa & Adegoke). 2020. industry_practice — https://engineering.indeedblog.com/blog/2020/01/defining-churn/
- **[S35]** Clemente-Císcar, San Matías & Giner-Bosch (2014) A methodology based on profitability criteria for defining the partial defection of customers in non-contractual settings. EJOR 239(1):276-285. 2014. academic(초록) — https://riunet.upv.es/handle/10251/51314
- **[S40]** Hillstrom MineThatData E-Mail Analytics Challenge (2008) — 원자료 직접 계산. 2008. dataset(직접 계산) — http://www.minethatdata.com/Kevin_Hillstrom_MineThatData_E-MailAnalytics_DataMiningChallenge_2008.03.20.csv ; https://blog.minethatdata.com/2008/03/minethatdata-e-mail-analytics-and-data.html
- **[S41]** Radcliffe (2008) Hillstrom's MineThatData Email Analytics Challenge: An Approach Using Uplift Modelling. 2008. academic/whitepaper(원문) — https://www.stochasticsolutions.com/pdf/HillstromChallenge.pdf
- **[S42]** Criteo Uplift Prediction Dataset v2.1 (Diemert et al. 2018/2021) — 원자료 직접 계산(조사 보조자). 2021. dataset(직접 계산) — https://ailab.criteo.com/criteo-uplift-prediction-dataset/ ; https://huggingface.co/datasets/criteo/criteo-uplift
- **[S43]** X5 RetailHero Uplift (2019) — 원자료 직접 계산(조사 보조자). 2019. dataset(직접 계산) — https://www.uplift-modeling.com/en/latest/api/datasets/fetch_x5.html ; https://sklift.s3.eu-west-2.amazonaws.com/uplift_train.csv.gz
- **[S44]** Lenta Uplift Dataset (BigTarget Hackathon 2020) — 원자료 직접 계산(조사 보조자 + 본 리서처 교차 확인). 2020. dataset(직접 계산) — https://www.uplift-modeling.com/en/latest/api/datasets/fetch_lenta.html ; https://sklift.s3.eu-west-2.amazonaws.com/lenta_dataset.csv.gz
- **[S45]** Ascarza (2018) Retention Futility: Targeting High-Risk Customers Might Be Ineffective. JMR 55(1):80-98. 2018. academic(초록) — https://journals.sagepub.com/doi/10.1509/jmr.16.0163
- **[S46]** Ascarza, Iyengar & Schleicher (2016) The Perils of Proactive Churn Prevention Using Plan Recommendations. JMR 53(1):46-60. 2016. academic(원문) — https://drupalgsb-test.paas.cc.columbia.edu/sites/default/files-efs/pubfiles/12782/Perils_Ascarza.pdf
- **[S47]** Radcliffe & Surry (2011) Real-World Uplift Modelling with Significance-Based Uplift Trees. 2011. academic/whitepaper(원문) — https://stochasticsolutions.com/pdf/sig-based-up-trees.pdf
- **[S48]** Radcliffe (2007) Identifying who can be saved and who will be driven away by retention activity. 2007. whitepaper(원문) — https://www.stochasticsolutions.com/pdf/SavedAndDrivenAway.pdf
- **[S49]** Devriendt, Moldovan & Verbeke (2018) A Literature Survey and Experimental Evaluation of the State-of-the-Art in Uplift Modeling. Big Data 6(1):13-41. 2018. academic(초록) — https://doi.org/10.1089/big.2017.0104
- **[S50]** Gubela, Lessmann & Jaroszewicz (2020) Response Transformation and Profit Decomposition for Revenue Uplift Modeling. EJOR. 2020. academic(원문) — https://arxiv.org/pdf/1911.08729
- **[S51]** Sahni, Zou & Chintagunta (2017) Do Targeted Discount Offers Serve as Advertising? Evidence from 70 Field Experiments. Management Science 63(8):2688-2705. 2017. academic(초록) — https://pubsonline.informs.org/doi/10.1287/mnsc.2016.2450
- **[S52]** Venkatesan & Farris (2012) Measuring and Managing Returns from Retailer-Customized Coupon Campaigns. Journal of Marketing 76(1) (Darden 보도 2차). 2012. academic(2차) — https://news.darden.virginia.edu/2012/04/27/coupons-make-money/
- **[S53]** NCH/Inmar — Cashing in Coupons (AMA Marketing News, Inmar 호스팅 PDF). 2011. industry(2차) — https://www.inmar.com/-/Document/Cashing_in_Coupons.pdf
- **[S54]** Omnisend 2023 Email, SMS and Push Report. 2024. industry_benchmark(원문) — https://www.omnisend.com/wp-content/uploads/2024/02/2023-email-sms-and-push-report.pdf
- **[S55]** Klaviyo Email Marketing Benchmarks. 2026. industry_benchmark(원문) — https://www.klaviyo.com/products/email-marketing/benchmarks
- **[S56]** 통계청 「2024년 12월 및 연간 온라인쇼핑동향」 최초 발표(PDF 원문). 2025. korea_official(원문) — https://mods.go.kr/boardDownload.es?bid=241&list_no=434934&seq=1

**재현.** `scripts/research/` 의 `instacart_stats.py`·`cj_stats.py`·`cj_label.py` 와 출력 `docs/research/computed/research_*_out.txt`. `our_mix.py` · `research_ourmix_out.txt` 는 시뮬 팀 내부다(시스템 팀은 열지 않는다, #163 리드 요청 6). Criteo·X5 집계와 Hillstrom·Lenta 의 1차 집계는 조사 보조자가 했고, Hillstrom·Lenta 는 이 리서처가 독립으로 다시 집계해 같은 값을 얻었다(`research_hillstrom_out.txt`·`research_lenta_out.txt`). `research_cj_out.txt` 의 "[폐기-집계 결함]" 줄은 근거로 쓰지 않는다.

