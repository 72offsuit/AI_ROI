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
