# 생성 데이터 유의미성 검증 — 외부 stylized fact F1~F17

- 생성: 2026-10-22T16:15:42+09:00 · 이벤트 루트: `<scratch>/runs/run20k/raw/main`
- 고객 19,992명 · 주문 290,231건 · 관측 315일 · simulator_version `sim-0.4` · seed `42`
- 교환 묶음: 있음 · 배정 근거: assignments_file · 가드레일 리포트: 있음
- 기준 띠: docs/research/data_grounding.md §4 (GATE 1 전 고정, 결과를 보고 바꾸지 않는다) · 경계 = 띠 밖이지만 가까운 경계값의 ±20% 이내

**한 줄 요약.** 17개 중 통과 11 · 경계 1 · 실패 5 · 데이터 없음 0 — 계산 가능한 17개 중 11개가 외부 실데이터 띠 안이다.

| # | 항목 | 우리 값 | 기준 띠 | 출처 | 판정 |
|---|---|---|---|---|---|
| F1 | 구매 간격 분포 (주문 단위, 30일 절단) | 중앙 9.0 · 평균 12.03 · p75 18.0 | 중앙값 5~10 · 평균 9~15 · p75 12~20 | [Instacart 2017](https://huggingface.co/datasets/attik/Instacart-Market-Basket-Analysis) | ✅ 통과 |
| F2 | 고객 안 간격 불규칙성 (간격 CV 중앙값) | 0.525 | 0.45~0.70 | [Instacart 2017](https://huggingface.co/datasets/attik/Instacart-Market-Basket-Analysis) | ✅ 통과 |
| F3 | 고객별 평균 구매 주기의 퍼짐 | 중앙 17.29일 · ln-sd 0.498 | 중앙값 12~18일 · ln-sd 0.5~0.9 | [Instacart 2017 · Complete Journey · 오픈서베이](https://huggingface.co/datasets/attik/Instacart-Market-Basket-Analysis) | 🟡 경계 |
| F4 | 월 구매 빈도 · 객단가 자릿수 | 월 1.59회 · 51,919원 | 월 2.0~3.2회 · 객단가 38,000~55,000원 | [오픈서베이 2023·2025 (컬리 이용자)](https://byline.network/2023/01/30_0976) | ❌ 실패 |
| F5 | 구매율 이질성 (12주 주문 수 NBD shape) | 1.152 | 0.5~1.5 | [Complete Journey 2.0](https://cran.r-project.org/web/packages/completejourney/vignettes/completejourney.html) | ✅ 통과 |
| F6 | Pareto 집중 (매출 상위 고객 비중) | 상위20% 0.65 · 상위10% 0.458 | 상위 20% 0.53~0.73 · 상위 10% 0.33~0.50 | [Complete Journey 2.0 · Instacart · 문헌](https://cran.r-project.org/web/packages/completejourney/vignettes/completejourney.html) | ✅ 통과 |
| F7 | 객단가 분포 (로그정규·오른쪽 꼬리) | ln-sd 0.526 · CV 0.528 | 주문 금액 ln-sd 0.4~0.8 · 고객 평균 객단가 CV 0.5~0.8 | [Complete Journey 2.0](https://cran.r-project.org/web/packages/completejourney/vignettes/completejourney.html) | ✅ 통과 |
| F8 | 무료배송 임계값(40,000원) 바로 위 몰림 | 2.901 (44677/15401) | > 1 | [Lewis 2006 · Lewis·Singh·Fay 2006 · UPS](https://doi.org/10.1016/j.jretai.2005.11.005) | ✅ 통과 |
| F9 | 장바구니 이탈률 | 62.75% | 50~75% | [Baymard · Stripe(식료품)](https://baymard.com/lists/cart-abandonment-rate) | ✅ 통과 |
| F10 | 상품 재주문 비중 | 0.591 | 0.50~0.65 | [Instacart 2017](https://huggingface.co/datasets/attik/Instacart-Market-Basket-Analysis) | ✅ 통과 |
| F11 | 신규 고객 재구매율 (첫 구매 후 365일 안 2번째 구매) | 0.912 (n=1802) | 0.55~0.75 | [컬리 2019~2021 (보도)](https://www.venturesquare.net/806256/) | ❌ 실패 |
| F12 | 생성 이탈률 (42일 무구매) | 41.94% (§4.1) · 참고 180일 25.29% | 가드레일 15~25% | [Complete Journey 2.0 (42일 라벨)](https://cran.r-project.org/web/packages/completejourney/vignettes/completejourney.html) | ❌ 실패 |
| F13 | 일시 공백 뒤 복귀 (42일+ 공백 후 재구매) | 0.5274 (n=9661) | > 0 | [Complete Journey 2.0](https://cran.r-project.org/web/packages/completejourney/vignettes/completejourney.html) | ✅ 통과 |
| F14 | 처치 효과 크기 ATE (T3 vs T0, 42일 유지율 차) | 7.65%p (log_itt) | 3~6%p | [X5 · Lenta · 통신사 실험](https://www.uplift-modeling.com/en/latest/api/datasets/fetch_x5.html) | ❌ 실패 |
| F15 | 쿠폰 사용률 (T2·T3 처치군 전체 중 유효기간 내 사용) | 13.52% | 5~20% | [Complete Journey 2.0 · NCH/Inmar](https://cran.r-project.org/web/packages/completejourney/vignettes/completejourney.html) | ✅ 통과 |
| F16 | 반응 이질성 (Sleeping Dog · Persuadable · 항등식) | D 1.8% · P 4.3% · 항등식 차 -0.0%p | D 8~15% · P 11~21% · \|P − D − ATE\| ≤ 0.5%p | [Hillstrom · 통신사 · 항등식](https://www.stochasticsolutions.com/pdf/HillstromChallenge.pdf) | ❌ 실패 |
| F17 | 처치 효과가 쿠폰 사용 밖에서도 생긴다 (증분 매출 중 쿠폰 미사용 몫) | 0.61 | > 0 | [Sahni·Zou·Chintagunta 2017 · Venkatesan & Farris 2012](https://pubsonline.informs.org/doi/10.1287/mnsc.2016.2450) | ✅ 통과 |

## 항목별 메모

- **F1** (pass) Instacart 와 같게 30일에서 절단해 판정한다(절단 전 값은 uncapped). 7일 피크 없음(가점 항목, 판정에 쓰지 않음).
- **F2** (pass) 간격 5개 이상 고객의 고객 안 간격 CV(모표준편차/평균) 중앙값. 30일 절단(Instacart 와 같음). 지수분포면 1.0, 시계면 0.
- **F3** (borderline) 간격 3개 이상 고객의 고객별 평균 간격(30일 절단, Instacart 정의). 절단 전 값은 uncapped(Complete Journey 0.89 는 절단 없음).
- **F4** (fail) 구매 고객(1회 이상)의 월 주문 수 = 주문 수 ÷ 노출 기간(첫 이벤트~관측 끝, 28일 미만 제외) × 30.44일. 객단가는 purchase.order_amount(할인 후·배송비 제외) 평균.
- **F5** (pass) 마지막 12주 창, 창 이전부터 관측된 구매 고객(0건 포함). NBD 적률 추정 r = m²/(v − m) (Poisson 잡음 보정). cj_style 은 cj_stats.py 와 같은 (평균/표준편차)² 보조값.
- **F6** (pass) 관측 315일(최대 365일) 매출, 구매 고객만(cj_stats.py 와 같은 정의). 1년 미만 창 — 기간이 짧으면 집중도가 높게 나온다.
- **F7** (pass) pandas 표본표준편차(ddof=1), cj_stats.py 와 같다.
- **F8** (pass) 구간 폭이 같으므로 밀도비 = 건수비. 금액은 purchase.order_amount(할인 후). 무료배송 판정이 할인 전 금액이면 몰림이 할인 폭만큼 흐려진다.
- **F9** (pass) 장바구니 이탈률 = 1 − (add_to_cart 와 purchase 가 함께 있는 세션 ÷ add_to_cart 세션). 판정은 이 값만. 세션→구매 전환(참고 3~8%)은 '방문 = 세션'일 때만 비교 대상이라 판정에 넣지 않는다(§3-4 미정).
- **F10** (pass) 주문 품목 중 그 고객이 이전 주문에서 산 상품의 비율. Instacart train 이 4번째 이후 주문이라 같은 조건으로 판정.
- **F11** (fail) 신규 기준: 교환 묶음 customers.signup_date > 관측 첫날. 관측 끝에서 잘린 추적(중앙 151일)이라 컬리의 '같은 해' 재구매율처럼 하한 쪽이다.
- **F12** (fail) 모집단은 이 프로젝트 정본 정의인 docs/data_spec.html §4.1 eligible(T0 − 가입일 ≥ 60일 ∧ T0 이전 구매 ≥ 1 ∧ 마지막 구매 ≥ 14일 전, 오케스트레이션 배정 모집단과 같다)이고 라벨은 §5 ② (T0, T0+42일] 무구매다. 30일 간격 여러 T0 평균, 비-T0 처치 고객 제외. 가입일 근거: 교환 묶음 customers.signup_date. 첫판은 PRD 에 정의가 없다고 보고 외부 집계(cj_label.py)의 180일 정의로 판정했으나, 정본 정의가 data_spec §4.1 에 있어 모집단을 그것으로 맞췄다 — 통과 띠 15~25% 는 바꾸지 않았다. 참고값(판정에 쓰지 않음): 180일 활성(cj_label.py 정의) · 그중 마지막 구매 14일+ 전 · 최근 42일 활성(시뮬레이터 guardrails 정의). 외부 참조: dunnhumby 180일 활성 가구 10.7~13.1%, 최근 구매 14일+ 전 가구 28.6~31.8% — §4.1 은 14일+ 조건을 포함하므로 외부에서 가장 가까운 비교는 뒤쪽 값이다. 관측 시작 전 구매 이력은 로그에 없어 초기 T0 는 eligible 이 작게 잡힌다.
- **F13** (pass) cj_stats.py 와 같은 정의: 구매 날짜(중복 제거) 사이 공백이 42일 이상이었던 고객 비율 = 공백 뒤 돌아온 고객. 0 이면 이탈이 흡수 상태다(PRD Risk 2). CJ 43.5% 는 선발 표본이라 상한 참고.
- **F14** (fail) T3 vs T0, 배정 시각부터 42일 안 구매 여부(ITT). 배정 근거: --assignments (apply_treatment 기록).
- **F15** (pass) 분모 = 쿠폰 처치군(T2·T3) 전체, 분자 = 배정 후 14일 안 coupon_use (§3-1 결정 (a)). '처치군 중 구매자' 분모 값은 참고. T2 유효기간은 config 에 없어 14일로 쟀다. 배정 근거: --assignments (apply_treatment 기록).
- **F16** (fail) ground truth 잠재결과 4분면(T3). P = 처치 때만 구매, D = 처치 때만 미구매. 항등식 P − D = ATE 를 ±0.5%p 로 검사(값은 이 스크립트가 다시 계산하고, 리포트의 identity_gap_pp 는 함께 싣는다).
- **F17** (pass) Sahni 2017 정의: (처치군 쿠폰 미사용 주문 매출 − 통제군 매출) ÷ (처치군 매출 − 통제군 매출), 1인당·배정 후 42일. 배정 근거: --assignments (apply_treatment 기록).
