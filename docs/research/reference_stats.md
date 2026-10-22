# 공개 실데이터 기준 통계 (Reference stylized facts)

생성: 2026-10-22T14:22:34 · 스크립트: `scripts/compute_reference_stats.py` · 모든 수치는 스크립트 실측값(JSON과 동일).

## 1. 거래 데이터 stylized facts

#### UCI Online Retail II (영국 온라인 소매, GBP) — 관측창 2009-12-01~2011-12-09 (739일), 고객 5,854명, 주문 36,711건

| 지표 | 값 | 정의/비고 |
|---|---|---|
| 고객당 주문 수 평균 / 중앙 / p75 / p90 / p99 | 6.27 / 3 / 7 / 13 / 46 | 관측창 전체 |
| 재구매 고객 비율(주문 ≥2) | 72.5% | 서로 다른 2일 이상 기준: 71.5% |
| 구매 간격 중앙 / p25 / p75 / p90 (일) | 31 / 13 / 70 / 148 | 연속 구매일 간격, n=27,091 |
| 구매 간격 lognormal 적합 | μ=3.355, σ=1.302, KS D=0.038 | MLE, loc=0 |
| 구매 간격 gamma 적합 | k=0.816, θ=72.50, KS D=0.067 | 더 나은 적합(KS D): lognormal |
| 주문금액 중앙 / 평균 (GBP) | 303.85 / 470.54 | p10=85.10, p90=833.94 |
| 주문금액 lognormal σ (μ) | 1.071 (5.588) | KS D=0.067 |
| 매출 상위 10% / 20% 고객 비중 | 63.7% / 77.1% | 상위 1%: 32.0% |
| 고객 매출 지니계수 | 0.740 | |
| 관측 종료일 기준 무구매 >30 / >60 / >90일 | 71.5% / 58.9% / 50.7% | 분모=관측창 내 전체 구매고객 |
| forward churn L30_N30 (T 평균 [최소~최대]) | 61.7% [51.5%~72.8%] | 최근 T=2011-11-09: 51.5% (활성 1,451명), T 24개 |
| forward churn L30_N60 (T 평균 [최소~최대]) | 43.8% [35.1%~56.9%] | 최근 T=2011-10-10: 38.1% (활성 1,342명), T 23개 |
| forward churn L30_N90 (T 평균 [최소~최대]) | 34.0% [25.2%~49.2%] | 최근 T=2011-09-10: 25.2% (활성 903명), T 22개 |
| forward churn L90_N30 (T 평균 [최소~최대]) | 67.5% [57.6%~83.7%] | 최근 T=2011-11-09: 57.6% (활성 2,583명), T 22개 |
| forward churn L90_N60 (T 평균 [최소~최대]) | 51.2% [40.3%~70.1%] | 최근 T=2011-10-10: 40.8% (활성 2,243명), T 21개 |
| forward churn L90_N90 (T 평균 [최소~최대]) | 41.9% [30.9%~60.1%] | 최근 T=2011-09-10: 30.9% (활성 1,892명), T 20개 |
| 월간 구매일 수(해당 월 구매자) 평균 / 중앙 | 1.29 / 1 | 완전한 달 24개 |
| 주간 구매일 수(해당 주 구매자) 평균 / 중앙 | 1.05 / 1 | 완전한 주 102개 |
| 월 m 구매자의 m+1월 재구매율(평균) | 38.5% | |

- 12개월 고정창(2010-12-01~2011-11-30) 고객당 주문 수: 평균 4.12, 중앙 2, 재구매율 64.1% (n=4,293)
- 취소 차감 순매출 기준 집중도: 상위10% 63.0%, 상위20% 76.6%, 지니 0.735
- 고객 국가 구성(상위): United Kingdom 91.1%, Germany 1.8%, France 1.6%, Spain 0.6%, Belgium 0.5%
- 정제 로그: `{"raw_rows": 1067371, "overlap_rows_removed_from_sheet1": 22523, "rows_after_overlap": 1044848, "rows_with_customer_id": 809561, "cancel_rows_removed": 18446, "admin_code_rows_removed": 781, "clean_rows": 790273, "orders": 36711}`

#### X5 RetailHero 구매 이력 (러시아 오프라인 식료품, RUB) — 관측창 2018-11-21~2019-03-18 (118일), 고객 400,162명, 주문 8,044,662건

| 지표 | 값 | 정의/비고 |
|---|---|---|
| 고객당 주문 수 평균 / 중앙 / p75 / p90 / p99 | 20.10 / 15 / 27 / 42 / 85 | 관측창 전체 |
| 재구매 고객 비율(주문 ≥2) | 98.1% | 서로 다른 2일 이상 기준: 97.9% |
| 구매 간격 중앙 / p25 / p75 / p90 (일) | 3 / 1 / 6 / 12 | 연속 구매일 간격, n=6,744,998 |
| 구매 간격 lognormal 적합 | μ=1.167, σ=0.961, KS D=0.147 | MLE, loc=0 |
| 구매 간격 gamma 적합 | k=1.093, θ=4.96, KS D=0.152 | 더 나은 적합(KS D): lognormal |
| 주문금액 중앙 / 평균 (RUB) | 282.00 / 428.16 | p10=71.36, p90=928.00 |
| 주문금액 lognormal σ (μ) | 1.006 (5.592) | KS D=0.022 |
| 매출 상위 10% / 20% 고객 비중 | 33.0% / 50.6% | 상위 1%: 6.8% |
| 고객 매출 지니계수 | 0.467 | |
| 관측 종료일 기준 무구매 >30 / >60 / >90일 | 0.0% / 0.0% / 0.0% | 분모=관측창 내 전체 구매고객 |
| forward churn L30_N30 (T 평균 [최소~최대]) | 5.5% [0.0%~9.0%] | 최근 T=2019-02-16: 0.0% (활성 346,302명), T 10개 |
| forward churn L30_N60 (T 평균 [최소~최대]) | 1.4% [0.0%~2.5%] | 최근 T=2019-01-17: 0.0% (활성 330,181명), T 5개 |
| 월간 구매일 수(해당 월 구매자) 평균 / 중앙 | 5.23 / 4 | 완전한 달 3개 |
| 주간 구매일 수(해당 주 구매자) 평균 / 중앙 | 1.87 / 1 | 완전한 주 16개 |
| 월 m 구매자의 m+1월 재구매율(평균) | 92.3% | |

> ⚠️ 표본 선택 편향: 모든 고객이 관측 종료 전 22일 이내에 구매(마지막 구매일 최솟값 2019-02-24 21:27:32). 따라서 inactive_share_at_end·forward_churn·repeat_customer_rate 는 구조적으로 0/과소(또는 과대) 추정되어 이탈 기준값으로 사용 불가. 구매간격·주문금액·빈도·집중도만 참고(긴 간격은 과소대표).

- 정제 로그: `{"transactions": 8045229, "nonpositive_purchase_sum": 567}`

## 2. 처치(캠페인) 효과 — 전체 ATE

ATE = 처치군 평균 − 통제군 평균, 95% CI = Wald(비율)/Welch(금액) 정규근사. 상대 lift = ATE/통제군 평균.

| 데이터셋 · 처치 · 결과 | n 처치 / 통제 | 반응률 처치 / 통제 | ATE %p [95% CI] | 상대 lift |
|---|---|---|---|---|
| Hillstrom · any_email · visit | 42,694 / 21,306 | 16.70% / 10.62% | +6.088 [+5.544, +6.633] | 57.4% |
| Hillstrom · any_email · conversion | 42,694 / 21,306 | 1.07% / 0.57% | +0.495 [+0.355, +0.636] | 86.5% |
| Hillstrom · any_email · spend | 42,694 / 21,306 | 1.250 / 0.653 | +0.5968 [+0.3762, +0.8174] (USD) | 91.4% |
| Hillstrom · mens_email · visit | 21,307 / 21,306 | 18.28% / 10.62% | +7.659 [+6.995, +8.323] | 72.1% |
| Hillstrom · mens_email · conversion | 21,307 / 21,306 | 1.25% / 0.57% | +0.680 [+0.500, +0.861] | 118.8% |
| Hillstrom · mens_email · spend | 21,307 / 21,306 | 1.423 / 0.653 | +0.7698 [+0.4851, +1.0545] (USD) | 117.9% |
| Hillstrom · womens_email · visit | 21,387 / 21,306 | 15.14% / 10.62% | +4.523 [+3.889, +5.157] | 42.6% |
| Hillstrom · womens_email · conversion | 21,387 / 21,306 | 0.88% / 0.57% | +0.311 [+0.150, +0.472] | 54.3% |
| Hillstrom · womens_email · spend | 21,387 / 21,306 | 1.077 / 0.653 | +0.4244 [+0.1690, +0.6799] (USD) | 65.0% |
| Lenta · SMS · response_att | 515,892 / 171,137 | 11.01% / 10.26% | +0.755 [+0.588, +0.922] | 7.4% |
| X5 · SMS(treatment_flg) · target(구매) | 99,981 / 100,058 | 63.65% / 60.33% | +3.323 [+2.898, +3.748] | 5.5% |

## 3. 세그먼트별 ATE — 음수 세그먼트(Sleeping Dog 근거)

| 데이터셋 · 처치 · 결과 | 세그먼트 수 | ATE<0 (점추정) | ATE<0 & 95%CI 상한<0 | ATE<0 & BH q<0.05 | 가장 음수인 세그먼트 |
|---|---|---|---|---|---|
| Hillstrom · any_email · visit | 26 | 0 | 0 | 0 | purchased_mens_womens=mens_only: +4.002%p [+3.228, +4.776] |
| Hillstrom · any_email · conversion | 26 | 0 | 0 | 0 | history_quartile=(64.66, 158.11]: +0.232%p [-0.011, +0.475] |
| Hillstrom · mens_email · visit | 26 | 0 | 0 | 0 | history_segment=6) $750 - $1,000: +6.150%p [+1.889, +10.411] |
| Hillstrom · mens_email · conversion | 26 | 0 | 0 | 0 | history_quartile=(64.66, 158.11]: +0.336%p [+0.032, +0.639] |
| Hillstrom · womens_email · visit | 26 | 0 | 0 | 0 | purchased_mens_womens=mens_only: +1.108%p [+0.241, +1.975] |
| Hillstrom · womens_email · conversion | 26 | 2 | 0 | 0 | history_segment=4) $350 - $500: -0.216%p [-0.817, +0.385] |
| Lenta · SMS · response_att | 32 | 0 | 0 | 0 | response_sms_pos=0_or_missing: +0.192%p [-0.150, +0.535] |
| X5 · SMS · target | 23 | 0 | 0 | 0 | redeemed_ever_s=never_redeemed: +0.284%p [-1.141, +1.709] |
| Hillstrom · any_email · visit (2변수 교차) | 232 | 0 | 0 | 0 | purchased_mens_womens×zip_code=both & Rural: +1.885%p [-4.296, +8.066] |
| Hillstrom · any_email · conversion (2변수 교차) | 232 | 7 | 0 | 0 | purchased_mens_womens×zip_code=both & Rural: -1.167%p [-3.059, +0.726] |
| Hillstrom · mens_email · visit (2변수 교차) | 232 | 0 | 0 | 0 | history_segment×zip_code=6) $750 - $1,000 & Surburban: +4.462%p [-1.611, +10.535] |
| Hillstrom · mens_email · conversion (2변수 교차) | 232 | 2 | 0 | 0 | purchased_mens_womens×zip_code=both & Rural: -0.898%p [-3.047, +1.250] |
| Hillstrom · womens_email · visit (2변수 교차) | 232 | 3 | 0 | 0 | purchased_mens_womens×zip_code=both & Rural: -1.798%p [-8.919, +5.322] |
| Hillstrom · womens_email · conversion (2변수 교차) | 232 | 44 | 0 | 0 | purchased_mens_womens×zip_code=both & Rural: -1.453%p [-3.467, +0.560] |
| Lenta · SMS · response_att (2변수 교차) | 375 | 29 | 0 | 0 | gender×activity_12m_q=unknown & (12.0, 32.0]: -2.381%p [-5.778, +1.016] |
| X5 · SMS · target (2변수 교차) | 202 | 13 | 0 | 0 | redeemed_ever_s×n_tx_q=never_redeemed & (27.0, 320.0]: -1.643%p [-7.262, +3.976] |

### 95% CI 상한 < 0 인 음수 ATE 세그먼트 (패밀리별 ATE 오름차순 상위 8개)

| 패밀리 | 세그먼트 | n 처치 / 통제 | 반응률 처치 / 통제 | ATE %p [95% CI] | BH q |
|---|---|---|---|---|---|
| (없음) | | | | | |

## 4. 데이터셋 출처·라이선스

| 데이터셋 | 출처(인용) | 라이선스 | 연도 / 기간 | 내용 |
|---|---|---|---|---|
| UCI Online Retail II | Chen, D. (2012). *Online Retail II* [Dataset]. UCI Machine Learning Repository. https://doi.org/10.24432/C5CG6D · https://archive.ics.uci.edu/dataset/502/online+retail+ii | CC BY 4.0 (UCI 저장소 표기) | 거래 2009-12-01 ~ 2011-12-09 | 영국 기반 무점포 온라인 선물용품 소매업체의 송장 라인 1,067,371행. 고객 상당수가 도매상 |
| Hillstrom MineThatData E-Mail | Hillstrom, K. (2008). *MineThatData E-Mail Analytics and Data Mining Challenge*. https://blog.minethatdata.com/2008/03/minethatdata-e-mail-analytics-and-data.html (파일: scikit-uplift 미러 `hillstorm_no_indices.csv.gz`) | 명시적 라이선스 없음(챌린지용 공개) | 2008 공개 | 최근 12개월 내 구매 고객 64,000명, 남성 메일 / 여성 메일 / 무발송 1/3씩 무작위 배정, 이후 2주 방문·전환·지출 |
| Lenta uplift | BigTarget Hackathon (Lenta × Microsoft, 2020 여름). scikit-uplift `fetch_lenta`: https://www.uplift-modeling.com/en/latest/api/datasets/fetch_lenta.html (파일 https://sklift.s3.eu-west-2.amazonaws.com/lenta_dataset.csv.gz) | 라이선스 명시 확인 못함 | 2020 | 러시아 식료품 체인 Lenta 카드 고객 687,029명, SMS 처치(test 75% / control 25%), 결과 `response_att` |
| X5 RetailHero | X5 Retail Group, RetailHero.ai uplift modeling 대회 (2019 겨울). https://ods.ai/competitions/x5-retailhero-uplift-modeling/data (파일: scikit-uplift 미러 `uplift_train/clients/purchases.csv.gz`) | 대회 약관(공개 라이선스 명시 확인 못함) | 구매 이력 2018-11-21 ~ 2019-03-18 | 러시아 식료품 체인 로열티 고객 400,162명의 커뮤니케이션 이전 구매 라인 45.8M행(거래 8,045,229건), 학습셋 200,039명에 SMS 처치(`treatment_flg`)·이후 구매(`target`) |

데이터 로더: scikit-uplift (https://github.com/maks-sh/scikit-uplift)의 S3 미러 URL을 curl로 직접 받음. 정제·집계 규칙은 `scripts/compute_reference_stats.py` 상단 상수와 각 지표의 `definition` 필드에 있음.

Instacart 등 Kaggle 로그인이 필요한 데이터셋은 시도하지 않았음.

## 5. 한계와 비교 시 주의점

1. **업종·국가·채널이 우리 도메인(한국 온라인 반복구매 장보기)과 다르다.**
   - UCI = 영국 **온라인 선물용품**, 도매 고객 비중이 큼(주문금액 중앙값 £300대, 고객당 연간 주문 수가 낮음). 장보기가 아니다.
   - X5·Lenta = 러시아 **오프라인** 식료품 체인. 업종은 가장 가깝지만 오프라인이라 구매 빈도가 온라인 장보기보다 높다(구매간격 중앙 3일).
   - Hillstrom = 미국 의류·잡화 이메일 캠페인(2008).
   → 절대 수준(level)보다 **형태(shape)** 비교를 권장한다. 예: 구매간격·주문금액이 우측으로 긴 꼬리를 갖는지, lognormal이 gamma보다 잘 맞는지, 상위 20% 매출 비중 구간, 처치 효과의 크기 범위(수 %p, 상대 lift 5~120%).
2. **관측창 길이 의존성**: 고객당 주문 수·재구매율·이탈률은 창 길이에 따라 달라진다(UCI 739일, X5 118일). 시뮬레이터 데이터도 같은 길이로 잘라서 같은 정의로 계산해야 한다(UCI는 12개월 고정창 값을 따로 제공).
3. **X5 구매 이력의 표본 선택 편향**: 모든 고객의 마지막 구매가 관측 종료 22일 이내에 있다(캠페인 대상 = 최근 활성 고객). 그래서 X5의 무구매 비율·forward churn·재구매율은 이탈 기준값으로 **사용하면 안 된다**. 이탈 기준값은 UCI만 유효하다.
4. **구매간격 이산화·절단**: 간격은 일 단위 정수(같은 날 여러 주문은 1회로 셈)이다. KS D에는 이산화 영향이 들어 있고, 관측 종료 후의 간격은 보이지 않으므로(우측 절단) 긴 간격이 과소대표된다. 표본이 커서 KS p값은 사실상 0이니 D로 상대 비교한다.
5. **방문 로그 부재**: UCI·X5에는 세션/방문 기록이 없어서 방문 빈도는 '구매일 수'로 대신 쟀다. 방문 결과변수는 Hillstrom의 `visit`(2주 내 웹사이트 방문)뿐이다.
6. **UCI 정제 규칙**: 두 시트가 겹치는 구간(2010-12-01~09)의 22,523행을 제거했다. 고객ID 결측, 취소 송장(C*), 수량≤0, 단가≤0, 관리코드(AMAZONFEE, BANK CHARGES, M, D, CRUK 등)는 제외하고 배송비 라인(POST/DOT/C2)은 주문금액에 포함했다. 집중도는 총매출 기준과 취소 차감 순매출 기준을 둘 다 제공한다.
7. **처치 효과**: 무작위 배정을 가정한 단순 평균차(ATE)와 정규근사 95% CI다. Lenta의 `response_att`는 공개 문서에 'target'으로만 적혀 있어 정확한 정의(구매/방문)는 확인하지 못했다. X5의 `target`은 커뮤니케이션 후 구매 여부이고, `treatment_flg`는 커뮤니케이션 여부다.
8. **Sleeping Dog 근거**: 사전 정의한 단일 변수 세그먼트와 모든 2변수 교차 세그먼트(처치·통제 각 200명 이상)에서는 **95% CI 상한이 0보다 작은 음수 ATE 세그먼트가 하나도 없었다**(BH 보정 전 기준으로도 0개). 점추정이 음수인 셀은 있지만 모두 CI가 0을 포함한다. 따라서 이 데이터로는 "실데이터에 유의한 sleeping dog 세그먼트가 존재한다"고 주장할 수 없다. 시뮬레이터에 sleeping dog 비율을 넣는다면 실데이터로 뒷받침된 값이 아니라 **가정**으로 표기해야 한다. 모델 기반(교차적합 uplift 모델 분위)의 음수 uplift 탐지는 이번 범위에서 하지 않았다.

## 6. `uplift_benchmarks/*.parquet` 열 설명

### `hillstrom.parquet` — 64,000행
| 열 | 설명 |
|---|---|
| recency | 마지막 구매 후 경과 개월(1–12) |
| history_segment | 과거 1년 구매액 구간(원본 문자열, 예 `2) $100 - $200`) |
| history | 과거 1년 구매액(USD) |
| mens / womens | 과거 1년 남성 / 여성 상품 구매 여부(1/0) |
| zip_code | Urban / Surburban / Rural (원본 철자 그대로) |
| newbie | 최근 12개월 내 신규 고객(1/0) |
| channel | 과거 1년 구매 채널(Phone / Web / Multichannel) |
| segment | 원본 처치 라벨(Mens E-Mail / Womens E-Mail / No E-Mail) |
| treatment_arm | mens / womens / control |
| **treatment** | 이메일 수신 여부(1 = Mens 또는 Womens, 0 = No E-Mail) |
| **visit** / **conversion** | 2주 내 웹사이트 방문 / 구매(1/0) — outcome |
| **spend** | 2주 내 지출(USD) — outcome |

### `lenta.parquet` — 687,029행
| 열 | 설명 |
|---|---|
| (원본 특징 전부) | `age, children, cheque_count_[3,6,12]m_g*, crazy_purchases_*, disc_sum_6m_g34, food_share_*, k_var_*, main_format, months_from_register, perdelta_days_between_visits_15_30d, promo_share_15d, response_sms, response_viber, sale_count_*, sale_sum_*, stdev_*` 등. 정의는 scikit-uplift Lenta 문서(위 URL)를 따른다. 결측(NaN)은 원본 그대로 둔다 |
| gender | 원본 Ж → `F`, М → `M`, 결측 → `unknown` 으로 바꿈 |
| main_format | 매장 형태(1 = 식료품점, 0 = 하이퍼마켓), 원본 숫자 |
| **treatment** | `group == 'test'` → 1, `control` → 0 (원본 `group` 열은 삭제) |
| **response_att** | outcome(이진) |

### `x5.parquet` — 200,039행(학습셋 `uplift_train` 고객만)
| 열 | 설명 |
|---|---|
| client_id | 고객 ID(원본) |
| age | 원본 나이. 이상값(음수, 100 초과)이 있으니 사용 시 정제 필요 |
| gender | U / F / M |
| first_issue_days / first_redeem_days | 기준일(2019-03-19 = 마지막 거래일+1) 기준 카드 발급 / 첫 포인트 사용 후 경과일. 포인트를 쓴 적이 없으면 NaN |
| redeemed_ever | 포인트 사용 이력 여부(1/0) |
| n_tx, n_purchase_days | 관측창(2018-11-21~2019-03-18) 거래 수, 구매일 수 |
| total_sum, mean_basket, median_basket | 거래금액(`purchase_sum`, RUB) 합 / 평균 / 중앙 |
| recency_days, tenure_days | 기준일 기준 마지막 / 첫 거래 후 경과일(관측창 안) |
| n_stores, mean_items_per_tx | 이용 매장 수, 거래당 평균 상품 수량 |
| regular_points_spent_sum, express_points_spent_sum | 사용 포인트 합(원본 부호, 사용분은 음수) |
| express_points_received_sum | 익스프레스 포인트 적립 합 |
| **treatment** | `treatment_flg`(커뮤니케이션 여부) |
| **target** | 커뮤니케이션 후 구매 여부 — outcome |

X5 특징은 모두 **처치 이전 구매 이력**으로 만들었다(scikit-uplift 문서상 purchases = prior to communication).
