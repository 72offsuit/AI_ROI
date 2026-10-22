# 리텐션 처치(쿠폰·무료배송·푸시) 효과 크기·반응 이질성: 외부 근거 수치 (raw)

- 조사일: 2026-10-22 / 조사자: 데이터 근거 리서처(웹 조사만 수행, 저장소 파일은 읽거나 수정하지 않음)
- 표기 규칙
  - **원문 직접**: 1차 문서(논문 PDF, 데이터 공식 페이지)를 직접 열어 확인함.
  - **원자료 직접 계산**: 공개 원자료 CSV를 내려받아 그룹별 평균을 직접 집계함. 다운로드 URL은 항목마다 적음.
  - **2차**: 언론·블로그·요약 글 등 재인용 출처.
  - **미확인**: 원문에 접근하지 못했거나 수치를 찾지 못함.
- 인용문은 원문 영어를 그대로 따옴표 안에 옮겼음.
- 비교 대상 가드레일(우리 시뮬레이터)
  - 처치 ATE(이탈/유지 확률 차): 3~6%p
  - 쿠폰 사용률(처치군 가운데 쿠폰을 쓴 비율): 25~40%
  - Sleeping Dog(처치가 역효과인 고객) 비율: 8~15%
  - Persuadable 비율: 20~30%
  - 윈백 쿠폰: T3 = 5만원 이상 7,000원 할인(14일 유효), T2 = 3만원 이상 3,000원 할인

---

## 0. 한눈에 보기 (ATE)

| 출처 | 처치 | 결과지표(창) | 처치군 | 통제군 | ATE | 상대 효과 | ATE 3~6%p와 대조 |
|---|---|---|---|---|---|---|---|
| Hillstrom 2008, Men's | 이메일 | 사이트 방문(2주) | 18.28% | 10.62% | +7.66%p | +72% | 높음 (지표가 다름) |
| Hillstrom 2008, Women's | 이메일 | 사이트 방문(2주) | 15.14% | 10.62% | +4.52%p | +43% | 정합 (지표가 다름) |
| Hillstrom 2008, Men's / Women's | 이메일 | 구매 전환(2주) | 1.25% / 0.88% | 0.57% | +0.68%p / +0.31%p | +119% / +54% | 낮음 |
| Criteo v2.1 | 광고 타기팅 | 방문 | 4.854% | 3.820% | +1.03%p | +27% | 낮음 |
| Criteo v2.1 | 광고 타기팅 | 전환 | 0.309% | 0.194% | +0.115%p | +59% | 낮음 |
| X5 RetailHero | "communication"(종류는 미확인) | 구매 | 63.65% | 60.33% | +3.32%p | +5.5% | **정합** (리테일, 기저율 높음) |
| Lenta | 캠페인(채널은 미확인) | response_att | 11.01% | 10.26% | +0.76%p | +7.4% | 낮음 |
| Gubela·Lessmann·Jaroszewicz 2020 | 세션 내 10% 할인 쿠폰 | 세션 전환 | 7.35% | 7.19% | +0.16%p | +2.2% | 낮음 |
| Ascarza·Iyengar·Schleicher 2016 | 전화 요금제 추천 + 월 $15 크레딧 | 3개월 이탈 | 10.0% | 6.4% | 이탈 **+3.6%p (역효과)** | — | 크기는 범위 안이나 부호가 반대 |
| Radcliffe 2007, Operator 1 | 모바일 리텐션 캠페인 | 이탈 | 25% | 30% | 이탈 −5%p (유지 +5%p) | — | **정합** |
| Radcliffe 2007, Operator 2 | 모바일 리텐션 캠페인 | 이탈 | 10% | 9% | 이탈 **+1%p (역효과)** | — | 부호가 반대 |
| Sahni·Zou·Chintagunta 2017 | 이메일 할인 오퍼(70개 실험) | 지출 | — | — | +$3.03/인 | +37.2% | 비교불가 (금액 지표) |

---

## 1. 공개 업리프트 데이터셋

### 1.1 Hillstrom MineThatData E-Mail Analytics Challenge (2008)
- 저자/연도: Kevin Hillstrom, 2008
- URL
  - 원문 블로그: https://blog.minethatdata.com/2008/03/minethatdata-e-mail-analytics-and-data.html
  - 원자료 CSV: http://www.minethatdata.com/Kevin_Hillstrom_MineThatData_E-MailAnalytics_DataMiningChallenge_2008.03.20.csv
  - sklift 문서: https://www.uplift-modeling.com/en/latest/api/datasets/fetch_hillstrom.html
  - 교차검증 문서: Radcliffe (2008) "Hillstrom's MineThatData Email Analytics Challenge: An Approach Using Uplift Modelling", https://www.stochasticsolutions.com/pdf/HillstromChallenge.pdf
- 인용 수치
  - 블로그(원문 직접): "This dataset contains 64,000 customers who last purchased within twelve months." / "1/3 were randomly chosen to receive an e-mail campaign featuring Mens merchandise." / "During a period of two weeks following the e-mail campaign, results were tracked." / Conversion = "1 = Customer purchased merchandise in the following two weeks."
  - 블로그 본문에는 그룹별 통계가 없음. 원자료를 직접 집계함.
  - sklift 문서(원문 직접): "Average visit Rate: .15", "Average conversion Rate: .009"
  - **원자료 직접 계산** (n = 64,000)

    | segment | n | visit | conversion | spend/인 |
    |---|---|---|---|---|
    | Mens E-Mail | 21,307 | 18.28% | 1.253% | $1.423 |
    | Womens E-Mail | 21,387 | 15.14% | 0.884% | $1.077 |
    | No E-Mail | 21,306 | 10.62% | 0.573% | $0.653 |

  - Radcliffe 2008 Table 2(원문 직접)도 같은 값을 보고함: Men's "18.28% 10.62% 7.66%"(visit 처치/통제/차이), "1.25% 0.57% 0.68%"(purchase), "$1.41 $0.65 $0.77"(spend). Women's "15.14% 10.62% 4.52%", "0.88% 0.57% 0.31%", "$1.07 $0.65 $0.42".
  - 이질성(원문 직접, Radcliffe 2008): "There is reasonably strong evidence of some negative effects for the last 10–20% of the population, again, even on validation. This suggests that the Women's email is actually detrimental to sales for a portion of the population."
  - 같은 문서: "people with historical spend in the range $200 to $400. For these people, the Men's Mailing increases spend by $1.35 per head, whereas the Women' Mailing it reduces spend by $0.37 per head."
- 확인 방법: 원문 직접 + 원자료 직접 계산(두 결과가 일치함)
- 가드레일 대조
  - ATE 3~6%p: 방문 지표는 Women's +4.52%p로 **정합**, Men's +7.66%p로 **높음**. 구매 전환은 +0.31~0.68%p로 **낮음**. 다만 Hillstrom의 지표는 "2주 내 방문·구매"이고 우리 지표는 이탈 확률 차라서 직접 비교하기 어려움. 리텐션(재구매) 관점에 가까운 쪽은 구매 전환이며, 이 기준으로는 우리 ATE가 한 자릿수 배 이상 큼.
  - 쿠폰 사용률: **비교불가**(쿠폰 없음). 다만 구매가 있어야 쿠폰을 쓸 수 있으므로 "처치군 구매율 1.25%"가 쿠폰 사용률의 상한 역할을 함. 이 기준이면 25~40%는 **높음**.
  - Sleeping Dog 8~15%: Radcliffe가 Women's 메일에 대해 모델 기반으로 추정한 "last 10–20% of the population" 음의 효과 구간과 **정합**. 단 이는 구매액(spend) 기준 세그먼트 추정이며, 개인 단위로 식별한 값이 아님.

### 1.2 Criteo Uplift Prediction Dataset v2.1 (Diemert et al. 2018 / 2021)
- 제목: "A Large Scale Benchmark for Uplift Modeling" (AdKDD 2018). 확장판은 "A Large Scale Benchmark for Individual Treatment Effect Prediction and Uplift Modeling" (arXiv 2111.10106, 2021)
- 저자: Eustache Diemert, Artem Betlei, Christophe Renaudin, Massih-Reza Amini (2021판에는 Théophane Gregoir, Thibaud Rahier 추가)
- URL
  - https://ailab.criteo.com/criteo-uplift-prediction-dataset/
  - https://www.uplift-modeling.com/en/latest/api/datasets/fetch_criteo.html
  - https://ar5iv.labs.arxiv.org/html/2111.10106
  - 원자료: https://huggingface.co/datasets/criteo/criteo-uplift (criteo-research-uplift-v2.1.csv.gz, 311MB). 공식 go.criteo.net 링크는 2026-10-22 기준 404.
- 인용 수치(원문 직접)
  - Criteo 페이지(v2.1): "Rows: 13,979,592", "Treatment ratio: .85", "Average visit rate: .046992", "Average conversion rate: .00292". 구버전은 25,309,483행이며 "leak" 때문에 v2.1을 권장함.
  - 처치 정의: "incrementality tests, a particular randomized trial procedure where a random part of the population is prevented from being targeted by advertising". exposure 필드 = "whether the user has been effectively exposed".
  - arXiv 2111.10106 Table 1(CRITEO-UPLIFTv2 열): Avg. positive outcome (Visit / Conversion) "4.70 / 0.29"%, Relative Avg. Uplift "68.7 / 37.2"%. Hillstrom 열은 "12.88 / 0.73", "42.6 / 54.3"(Women's 대 No e-mail, 42,693행).
  - **원자료 직접 계산** (v2.1, 13,979,592행)

    | treatment | n | 비중 | visit | conversion | exposure |
    |---|---|---|---|---|---|
    | 0 (통제) | 2,096,937 | 15.0% | 3.820% | 0.194% | 0.00% |
    | 1 (처치) | 11,882,655 | 85.0% | 4.854% | 0.309% | 3.60% |

    → ATE: visit +1.03%p(상대 +27.1%), conversion +0.115%p(상대 +59.3%). 처치군 가운데 실제 광고 노출은 3.6%뿐임.
  - **불일치 메모**: 직접 계산한 상대 uplift(27.1% / 59.3%)가 arXiv Table 1의 "68.7 / 37.2"와 맞지 않음. 같은 표의 Hillstrom 값(42.6 / 54.3)과 전체 평균(4.70 / 0.29)은 직접 계산과 일치함. 원인(정의 차이나 표 오기 가능성)은 미확인.
- 확인 방법: 원문 직접 + 원자료 직접 계산
- 가드레일 대조
  - ATE 3~6%p: **낮음**(방문 +1.03%p, 전환 +0.115%p). 처치가 리텐션 쿠폰이 아니라 디스플레이 광고 타기팅이고, 실제 노출률이 3.6%라서 ITT 효과가 희석됨.
  - 쿠폰 사용률: **비교불가**.
  - Sleeping Dog: **비교불가**(개인 단위로 식별 불가). §4의 경계 계산상 방문 기준 D ≤ 3.82%.

### 1.3 X5 RetailHero Uplift (2019)
- 출처: X5 Retail Group, RetailHero hackathon(2019)
- URL
  - https://www.uplift-modeling.com/en/latest/api/datasets/fetch_x5.html
  - https://raw.githubusercontent.com/maks-sh/scikit-uplift/master/sklift/datasets/descr/x5.rst
  - 원자료: https://sklift.s3.eu-west-2.amazonaws.com/uplift_train.csv.gz
  - 대회 페이지: https://ods.ai/competitions/x5-retailhero-uplift-modeling/data (접속 실패)
- 인용 수치(원문 직접, sklift 문서)
  - "in 'clients.csv': 400,162", "in 'uplift_train.csv': 200,039", "Response Ratio: .62", "Treatment Ratio: .5"
  - "The column *treatment_flg* indicates if there was a communication. The column *target* shows if there was a purchase afterward"
  - **원자료 직접 계산** (uplift_train, 200,039명)

    | treatment_flg | n | 구매율(target) |
    |---|---|---|
    | 0 | 100,058 | 60.33% |
    | 1 | 99,981 | 63.65% |

    → ATE +3.32%p(상대 +5.5%). 대략 SE 0.22%p이며 매우 유의함(직접 근사 계산).
- 확인 방법: 원문 직접 + 원자료 직접 계산. 처치가 SMS라는 점은 **미확인**(sklift 문서에는 "communication"으로만 적혀 있음).
- 가드레일 대조
  - ATE 3~6%p: **정합**(+3.32%p). 오프라인 리테일에서 기저 구매율이 60%로 높은 환경이라 우리 리텐션 지표와 구조가 가장 비슷함.
  - 쿠폰 사용률: **비교불가**(쿠폰 여부·사용 데이터 없음).
  - Sleeping Dog: **비교불가**(식별 불가). §4 경계상 D ∈ [0, 36.4%]로, 가드레일 범위가 들어갈 여지는 있음.

### 1.4 Lenta Uplift Dataset (BigTarget Hackathon 2020)
- 출처: Lenta와 Microsoft의 BigTarget Hackathon(2020 여름)
- URL
  - https://www.uplift-modeling.com/en/latest/api/datasets/fetch_lenta.html
  - https://raw.githubusercontent.com/maks-sh/scikit-uplift/master/sklift/datasets/descr/lenta.rst
  - 원자료: https://sklift.s3.eu-west-2.amazonaws.com/lenta_dataset.csv.gz
- 인용 수치(원문 직접): "Rows: 687,029", "Response Ratio: .1", "Treatment Ratio: .75". 필드 정의는 "group (str): treatment/control group flag", "response_att (binary): target".
- **원자료 직접 계산** (687,029행)

  | group | n | 비중 | response_att |
  |---|---|---|---|
  | control | 171,137 | 24.9% | 10.26% |
  | test | 515,892 | 75.1% | 11.01% |

  → ATE +0.755%p(상대 +7.4%). 대략 SE 0.085%p(직접 근사 계산).
- 확인 방법: 원문 직접 + 원자료 직접 계산. 처치 채널(SMS 등)과 target의 정확한 정의는 **미확인**. 데이터에 response_sms, response_viber 컬럼이 있지만 sklift 문서에 설명이 없음.
- 가드레일 대조: ATE는 **낮음**. 쿠폰 사용률과 Sleeping Dog는 **비교불가**(§4 경계상 D ≤ 10.26%).

### 1.5 (참고) MegaFon Uplift Competition (2021)
- sklift 문서: "The dataset contains generated synthetic data". 600,000행, "Response Ratio: .2", "Treatment Ratio: .5".
- 합성 데이터라 근거로서 가치가 낮아 집계하지 않음.

### 1.6 sklift / causalml 문서 URL 정리
- sklift 데이터셋 API: fetch_hillstrom / fetch_criteo / fetch_x5 / fetch_lenta / fetch_megafon (https://www.uplift-modeling.com/en/latest/api/datasets/)
- 설명 원본: https://github.com/maks-sh/scikit-uplift/tree/master/sklift/datasets/descr
- sklift 문서에는 그룹별(처치/통제) 반응률이 없음. 전체 평균과 비율만 있음.
- causalml 문서에서 위 데이터셋들의 그룹별 통계 표는 찾지 못함(미확인).

---

## 2. 학술 문헌

### 2.1 Ascarza (2018) "Retention Futility: Targeting High-Risk Customers Might Be Ineffective", JMR 55(1): 80–98
- URL: https://journals.sagepub.com/doi/10.1509/jmr.16.0163 (403), SSRN 2759170(봇 차단), https://www.hbs.edu/ris/download.aspx?name=ascarza_jmr_18.pdf (봇 차단)
- 인용 수치
  - JMR 초록(OpenAlex에서 원문 초록 확인): "Combining two field experiments with machine learning techniques, the author demonstrates that customers identified as having the highest risk of churning are not necessarily the best targets for proactive churn programs." / "firms should focus their modeling efforts on identifying the observed heterogeneity in response to the intervention and to target customers on the basis of their sensitivity to the intervention, regardless of their risk of churning."
  - 워킹페이퍼 초록(Universidad de Chile 세미나 페이지, https://www.dii.uchile.cl/?p=32838): "We show that the same retention campaign would result in a further reduction of up to seven percentage points in churn rate if the focal firm had followed our proposed approach (instead of the industry standard)."
  - 2차(AMA 수상 기사, https://www.ama.org/2019/04/24/...): 필드 데이터는 무선통신사와 회원제 조직에서 나왔다고 함.
  - 2차(INMA/ANA 보도, 검색 요약에서만 확인, 원문 403): "of the top 10% at risk of churn, only 6% were highly receptive to intervention" → **미확인**(원문 열람 실패).
- 확인 방법: 초록만 원문 직접. 실험별 처치/통제 이탈률, ATE, CATE<0 비율은 **미확인**.
- 가드레일 대조
  - ATE: **비교불가**(실험별 ATE 미확인). "up to seven percentage points"는 ATE가 아니라 타기팅 규칙을 바꿨을 때 추가로 줄어드는 이탈률임.
  - Sleeping Dog: **비교불가**. 이질성이 존재한다는 질적 근거로만 쓸 수 있음.

### 2.2 Ascarza, Iyengar, Schleicher (2016) "The Perils of Proactive Churn Prevention Using Plan Recommendations: Evidence from a Field Experiment", JMR 53(1): 46–60
- URL: https://drupalgsb-test.paas.cc.columbia.edu/sites/default/files-efs/pubfiles/12782/Perils_Ascarza.pdf (PDF 원문 직접)
- 인용 수치(원문 직접)
  - 초록: "whereas only 6% of customers in the control condition churned during the three months following the intervention, 10% did so in the treatment group."
  - 설계: "64,147 were randomly selected to be included in the experiment. We randomly assigned 10,058 customers (15.7%) to the control group and the remaining 54,089 to the treatment group."
  - 처치: "Customers in the treatment condition were contacted (via phone) ... the company offered an additional credit of $15 for each of the following three months if they agreed to upgrade to one of the featured plans."
  - Table 3: "Percentage of customers churning 6.4% [Control] 10.0% [Treatment] −3.6% [Difference] .3% [SE] <.001"
  - 본문: "whereas only 6.4% of customers in the control group left the company during the first three months after the campaign, 10.0% did so in the treatment group (p < .001)."
  - 수락률(Table 4): Accepted "828", Rejected "53,261" → 828 / 54,089 = **1.53%**(직접 계산). 이탈률은 Accepted "5.9%", Rejected "10.1%".
  - 이질성: "the treatment increased churn to a lesser extent, and sometimes even decreased it, for customers with lower (vs. higher) overage, lower variability, and positive trend. For example, while the average difference in churn rate between customers in the treatment and control groups is 3.6 percentage points, those customers with a positive trend show a difference of only 2.4 percentage points."
  - 함정 경고: 수락자만 통제군과 비교하면 "lower churn rate (5.9% vs. 6.4%)"가 나와 성공으로 오판하게 됨.
- 확인 방법: 원문 직접
- 가드레일 대조
  - ATE 3~6%p: 크기(3.6%p)는 범위 안에 있지만 **부호가 반대**(처치가 이탈을 늘림). 처치는 요금제 추천과 금전 인센티브임.
  - 쿠폰 사용률 25~40%: 인센티브 수락률 1.53% 대비 **높음**(채널은 전화, 오퍼는 요금제 업그레이드).
  - Sleeping Dog 8~15%: §4의 Fréchet 경계상 D ∈ [3.6%, 10.0%]. 가드레일 하단(8~10%)과 **부분 정합**.

### 2.3 Radcliffe & Surry (2011) "Real-World Uplift Modelling with Significance-Based Uplift Trees", Portrait Technical Report TR-2011-1 / Stochastic Solutions White Paper
- URL: https://stochasticsolutions.com/pdf/sig-based-up-trees.pdf (원문 직접)
- "sleeping dog"라는 용어는 이 논문 본문에 없음(텍스트 검색 결과 0건). 같은 저자의 2007 백서(아래)에서 정의함.
- 인용 수치(원문 직접)
  - "A mobile churn reduction initiative actually increased churn from 9% to 10% prior to uplift modelling. The uplift model allowed a 30% subsegment to be identified. Targeting only that subsegment reduced overall churn from 9% to under 8%, while reducing spend by 70%"
  - "A different mobile churn reduction initiative (at a different operator) was successful in reducing churn by about 5 percentage points (pp), but an uplift model was able to identify 25% of the population where the activity was marginal or counterproductive. By targeting only the identified 75% overall retention was increased by from 5 pp to 6 pp"
  - US Bank 사례: "the top 30% identified by a conventional 'response' model was targeted, the result was almost exactly zero incremental sales"
  - 일반적 크기: "it would not be atypical for the purchase rate in the control group to be around 1% while the rate in the treated group was around 1.1%, representing an uplift of 0.1pp." / "for typical marketing problems, where background rates might be 1–3% and uplift might be 0.1 to 2 percentage points"
  - 음의 효과: "It is not uncommon, particularly in the area of retention, for uplift modelling to deliver more value by identifying populations where negative effects are prevalent ... Negative effects tend to occur most when uplift is small relative to the background outcome rate, where inaction on the part of the customer leads to a positive outcome for the supplier, where interventions are intrusive, and where customers targeted are already unhappy with the supplier"
- 관련 백서(원문 직접): Radcliffe (2007) "Identifying who can be saved and who will be driven away by retention activity", Stochastic Solutions, https://www.stochasticsolutions.com/pdf/SavedAndDrivenAway.pdf
  - 정의: "Sleeping Dogs tend to be driven away by treatment / Lost Causes are likely to leave whether treated or not / Sure Things are likely to stay whether treated or not / Persuadables are made more likely to stay by treatment"
  - 표 "Key metrics from two Mobile Retention Campaigns"
    - Churn rate in control group: Operator 1 "30%", Operator 2 "9%"
    - Churn rate in treated group: "25%", "10%"
    - Size of control group: "10,000", "100,000"
    - Size of treated group: "20,000", "1,000,000"
    - Best targeting cutoff found: "75%", "30%"
  - Operator 2: "these figures suggest that the retention activity has a somewhat negative effect for 70% of the population, though this may be misleading"
- 확인 방법: 원문 직접
- 가드레일 대조
  - ATE 3~6%p: Operator 1(이탈 −5%p)은 **정합**. Operator 2(+1%p 역효과)는 부호가 반대.
  - Sleeping Dog 8~15%: Operator 1의 "25% ... marginal or counterproductive"는 '미미한 효과'까지 포함하므로 순수 역효과는 그보다 작음. **상한 기준으로 정합~높음**. Operator 2의 "negative effect for 70%"와 비교하면 가드레일이 **낮음**.
  - 두 수치 모두 모델 기반 세그먼트 추정이며, 개인 단위로 식별한 값이 아님.

### 2.4 Devriendt, Moldovan, Verbeke (2018) "A Literature Survey and Experimental Evaluation of the State-of-the-Art in Uplift Modeling: A Stepping Stone Toward the Development of Prescriptive Analytics", Big Data 6(1): 13–41
- URL: https://doi.org/10.1089/big.2017.0104 / PubMed 29570415
- 인용(초록, 원문 직접): "An experimental evaluation on four real-world data sets provides further insight into their use. Uplift random forests are found to be consistently among the best performing techniques ... uplift models are frequently observed to be unstable and display a strong variability in terms of performance across different folds"
- 데이터셋별 처치효과 크기: **미확인**(OpenAlex 기준 "closed" 접근)
- 가드레일 대조: **비교불가**. 업리프트 추정이 불안정하다는 질적 근거로만 쓸 수 있음.

### 2.5 Gubela 등: 이커머스 업리프트 벤치마크
- (a) Gubela, Bequé, Gebert, Lessmann (2019) "Conversion Uplift in E-Commerce: A Systematic Benchmark of Modeling Strategies", IJITDM 18(3): 747–791. 원문 PDF(HU Berlin IRTG DP 2018-062)가 봇 차단 페이지로 막혀 데이터 통계는 **미확인**.
- (b) Gubela, Lessmann, Jaroszewicz (2020) "Response Transformation and Profit Decomposition for Revenue Uplift Modeling", EJOR. https://arxiv.org/pdf/1911.08729 (원문 직접)
  - 처치: "Treatment group visitors are offered the discount, which they can use in the current browsing session." / "offered a ten percent discount off their shopping basket". 처치:통제 = "3:1". 25개 유럽 온라인몰, "2,951,313 observations".
  - 준실험 성격: 구매 가능성이 높은 방문자는 사전에 제외됨.
  - Table 2: Treatment "74.9 [%] 2,210,190 [sessions] 162,570 [purchasers] 7.35 [conv %]", Control "25.1 741,123 53,340 7.19", Conversion Uplift "0.16" [%], Revenue per person "0.08" vs "0.03", Revenue uplift "0.05" [€]
  - 원문 문장: "with a conversion and (normalized) revenue uplift of 0.16% and 0.05€, respectively, the overall uplift signal is rather low." 같은 문단에 "is not statistically significant for our data (p-value of 5.93e-06)"라는 표현이 있는데, p값과 문장이 서로 모순되는 원문 오기로 보임.
  - 같은 논문의 2차 인용: "coupon redemption rates in grocery retailing are only 0.6% in the US (NCH Marketing Services)" / "US retailers distributed 256.5 billion coupons ... consumers redeemed over 1.7 billion coupons" (NCH 2019)
- 가드레일 대조
  - ATE 3~6%p: **낮음**(세션 전환 +0.16%p). 단 세션 단위 즉시 쿠폰이라 우리의 14일 윈백과는 다름.
  - 쿠폰 사용률: NCH 0.6% 대비 **높음**(2차 인용, 오프라인 CPG 쿠폰 기준).

### 2.6 Sahni, Zou, Chintagunta (2017) "Do Targeted Discount Offers Serve as Advertising? Evidence from 70 Field Experiments", Management Science 63(8): 2688–2705
- URL: https://pubsonline.informs.org/doi/10.1287/mnsc.2016.2450 (본문 미열람). 초록은 https://academicnewsletter.sufe.edu.cn/info/392661 에서 원문 그대로 확인.
- 인용(초록, 원문 직접)
  - "We find that the offers cause the average expenditure to increase significantly, by $3.03 ( a 37.2% increase) during the promotion window. However, the redemption rate of these offers is low. Importantly, 90% of these gains are not through redemption of the offers."
  - "the effect of the offers is significantly higher among individuals who did not transact on the platform in the year before the offer was given."
  - "we find that spending increases by $ 1.55 in the week after the offer expires."
- 2차(Stanford GSB Insights): 예시 오퍼는 "promised free delivery to those who spent $200 or more"(무료배송형 오퍼). 이월 효과는 "25% 'carryover' bump in spending the week after the discount expired".
- 확인 방법: 초록은 원문 직접. 정확한 redemption rate 수치는 **미확인**(초록에는 "low"로만 적혀 있음).
- 가드레일 대조
  - ATE: **비교불가**(지출액 지표). 다만 1년 이상 거래가 없던 휴면 고객에서 효과가 더 크다는 결과는 윈백 처치 설계를 뒷받침함.
  - 쿠폰 사용률 25~40%: 원문이 "low"라고 하고 증분의 90%가 쿠폰 사용 밖에서 나왔으므로 **높음** 쪽(정량 비교는 불가). 우리 시뮬레이터가 쿠폰 사용 = 처치효과 경로로 가정한다면 구조적 차이가 있음.

### 2.7 Venkatesan & Farris (2012) "Measuring and Managing Returns from Retailer-Customized Coupon Campaigns", Journal of Marketing 76(1)
- URL: 본문 미열람. 2차 출처는 Darden 보도자료 https://news.darden.virginia.edu/2012/04/27/coupons-make-money/
- 인용(2차)
  - "In 2010, U.S. consumers redeemed 3.3 billion coupons, cutting about $3.7 billion from purchase prices, though only about 1 percent are ever used, the professors write."
  - "analyzed the advertising campaigns of eight national retailers involving more than 500,000 targeted coupons for items representing more than 300 brands mailed out over 16 months."
  - "these consumers [쿠폰을 받았지만 쓰지 않은 고객] accounted for 60 percent of the coupons' 'sales lift'"
- 확인 방법: 2차. 연구 자체의 redemption rate는 **미확인**("about 1 percent"는 업계 전반 수치로 인용된 것으로 보임).
- 가드레일 대조: 쿠폰 사용률 **높음**(약 1% 대비). 노출 효과가 sales lift의 60%를 차지한다는 결과는 Sahni와 같은 방향임.

---

## 3. 쿠폰 사용률 / 리텐션·윈백 캠페인 전환 벤치마크

| 출처 | 수치(원문) | 확인 | 쿠폰 사용률 25~40% 대조 |
|---|---|---|---|
| NCH(AMA Marketing News, Inmar 호스팅 PDF: https://www.inmar.com/-/Document/Cashing_in_Coupons.pdf) | "the overall redemption rate for FSI coupons for CPG products was 0.7% in 2010" / "amongst digital coupons for CPG products printed by consumers, 15.8% are redeemed." | 2차(NCH 인용) | 높음 |
| 같은 문서(Kahala 사례) | "Digital coupons are being redeemed at a rate of 14%, ... far greater than the company's 0.02% redemption rate for print coupons" | 2차 | 높음 |
| NCH via Gubela et al. 2020 | "coupon redemption rates in grocery retailing are only 0.6% in the US" | 2차 | 높음 |
| Inmar(검색 요약) | 2018 L2C(load-to-card)가 "1.6% of all coupons distributed ... and 14.8% of all coupons redeemed". 쿠폰당 사용률이 아니라 **사용 점유율**임 | 2차, 원문 미열람 | 비교불가 |
| Omnisend 2023 report (https://www.omnisend.com/wp-content/uploads/2024/02/2023-email-sms-and-push-report.pdf) | 정의: "conversion rates by looking at attributed orders compared to total emails/SMS/push messages sent". "Lapsed purchase ... 31.6% [open] 1.9% [click] 0.50% [conversion]". Welcome "2.74%", Cart Abandonment "2.56%". Push: Campaigns "0.04%", Automation "0.38%" | 원문 직접 | 높음(발송 1건당 귀속 주문 0.5%) |
| Omnisend Q1 2020 (https://www.omnisend.com/resources/reports/email-sms-marketing-statistics-q1-2020/) | "Lapsed-Purchaser 18.34%", Welcome "34.46%", Cart Abandonment "12.89%". 분모 정의가 없어 클릭 대비 전환으로 추정되나 미확인 | 원문 직접(정의는 미확인) | 비교불가 |
| Klaviyo 2026 benchmarks (https://www.klaviyo.com/products/email-marketing/benchmarks) | "Average ecommerce email conversion rates, or order rates, by industry". 예: Clothing and accessories campaigns "0.97%", flows "1.62%". Home and garden "1.34%" / "2.17%". "based on over 183,000 Klaviyo customers". 윈백 flow만 따로 낸 수치는 없음 | 원문 직접 | 높음 |
| Ascarza et al. 2016 | 인센티브 수락 828 / 54,089 = 1.53% | 원문 직접 + 직접 계산 | 높음 |

- 공통 주의: 위 벤치마크는 모두 귀속(attributed) 전환이나 사용률이며 증분(incremental) 효과가 아님. 반면 우리 쿠폰 사용률은 처치군 가운데 쿠폰을 쓴 비율로, 쿠폰을 받은 고객 기준(redeemed/distributed)과 정의가 같음. 이 정의로 확인된 외부 수치는 **0.02%~15.8%** 범위이고, 가장 높은 값은 고객이 직접 출력한 디지털 CPG 쿠폰(자기선택이 강함)임.
- 25~40%를 지지하는 외부 공개 근거는 찾지 못함. 고액 정액 쿠폰(7,000원/5만원 = 14%)이라도 사용률은 14일 창 안의 처치군 구매율을 넘을 수 없음. 시뮬레이터의 처치군 14일 구매율이 25~40% 이상인지 내부적으로 먼저 확인해야 함.

---

## 4. 사람 단위 '음의 반응' 정량화: 식별 한계와 Fréchet 경계 (직접 계산)

- 원리: RCT에서 개인의 잠재결과 쌍 (Y1, Y0)은 동시에 관측할 수 없음. 그래서 Sleeping Dog 비율 D = P(Y1=0, Y0=1)(좋은 결과 = 1)은 점추정되지 않고 경계만 나옴.
  - D ∈ [max(0, p0 − p1), min(p0, 1 − p1)]
  - Persuadable P = D + (p1 − p0), 즉 **P − D = ATE (항등식)**
- 외부 연구에서 "음의 효과 비율"로 보고된 값(Radcliffe의 10–20%, 25%, 70% 등)은 모두 세그먼트·모델 기반 추정임. 개인 단위로 식별한 비율을 보고한 연구는 찾지 못함.

| 사례 | p1(처치) | p0(통제) | ATE | D(Sleeping Dog) 경계 | P(Persuadable) 경계 |
|---|---|---|---|---|---|
| Hillstrom Mens 방문 | 18.28% | 10.62% | +7.66%p | [0, 10.62%] | [7.66%, 18.28%] |
| Hillstrom Womens 방문 | 15.14% | 10.62% | +4.52%p | [0, 10.62%] | [4.52%, 15.14%] |
| Hillstrom 구매(M/W) | 1.25% / 0.88% | 0.57% | +0.68 / +0.31%p | [0, 0.57%] | ≤ 1.25% |
| Criteo 방문 | 4.85% | 3.82% | +1.03%p | [0, 3.82%] | [1.03%, 4.85%] |
| X5 구매 | 63.65% | 60.33% | +3.32%p | [0, 36.35%] | [3.32%, 39.67%] |
| Lenta | 11.01% | 10.26% | +0.76%p | [0, 10.26%] | [0.76%, 11.01%] |
| Gubela 세션 쿠폰 | 7.35% | 7.19% | +0.16%p | [0, 7.19%] | [0.16%, 7.35%] |
| Perils(유지=1) | 90.0% | 93.6% | −3.6%p | **[3.6%, 10.0%]** | [0, 6.4%] |
| Radcliffe Op1(유지=1) | 75% | 70% | +5%p | [0, 25%] | [5%, 30%] |
| Radcliffe Op2(유지=1) | 90% | 91% | −1%p | [1%, 10%] | [0, 9%] |

- 시사점 1: 결과의 기저율이 낮은 지표(구매 전환 0.2~1%)에서는 D가 8~15%가 될 수 **없음**(D ≤ p0). 가드레일 8~15%는 기저율이 높은 '유지/이탈' 결과에서만 가능함. 우리는 이탈 확률 차를 쓰므로 이 조건은 충족될 수 있음.
- 시사점 2: Persuadable 20~30%는 Hillstrom 방문(P ≤ 18.3%), Criteo, Lenta, Perils 등에서 수학적으로 불가능함. X5와 Radcliffe Op1처럼 기저율이 높은 경우에만 가능함.
- **시사점 3(가드레일 내부 정합성 경고)**: 잠재결과 유형 정의(P − D = ATE)를 쓰면, 가드레일 P 20~30%와 D 8~15%가 함의하는 ATE는 **5~22%p**임. 반면 ATE 가드레일은 3~6%p임. 셋을 동시에 만족하는 영역은 P ≈ 20~21%, D ≈ 14~15%(ATE 5~6%p) 정도의 좁은 모서리뿐임. ATE 3~6%p와 D 8~15%를 함께 지키면 P는 11~21%가 됨. 시뮬레이터가 세그먼트를 연속 CATE 임계값(예: CATE<0 = Sleeping Dog, CATE>τ = Persuadable)으로 정의한다면 이 항등식이 그대로 적용되지는 않음. 어떤 정의를 쓰는지 확인이 필요함(직접 계산에 근거한 분석이며 외부 수치가 아님).

---

## 5. 가드레일 대조 종합

| 가드레일 | 외부 근거 요약 | 판정 |
|---|---|---|
| ATE 3~6%p | 기저율이 높은 리텐션·리테일 맥락: X5 +3.32%p, Radcliffe Op1 +5%p(유지)는 정합. 이메일 방문 지표: Hillstrom +4.5~7.7%p는 정합~높음. 구매/전환 지표: 0.1~0.7%p(Hillstrom, Criteo, Gubela, Lenta)는 우리가 높음. 역효과 사례: Perils −3.6%p, Op2 −1%p | **조건부 정합**. 기저율이 높은 이탈 지표라면 상단(6%p)도 외부 상위 사례 수준. 처치 효과의 부호가 음수인 실험이 실재하므로 ATE가 음수인 시나리오도 필요 |
| 쿠폰 사용률 25~40% | 외부 쿠폰 사용률: 0.02%(인쇄) / 0.6~0.7%(FSI·식료품) / 약 1%(업계) / 1.5%(Perils 인센티브 수락) / 14~15.8%(디지털, 자기선택). 이메일 lapsed 자동화 귀속 주문 0.5%/발송 | **높음**. 25~40%를 지지하는 공개 근거는 찾지 못함. Sahni·Venkatesan에 따르면 증분의 60~90%가 쿠폰 미사용자에게서 나옴 |
| Sleeping Dog 8~15% | Radcliffe 2008 Hillstrom Women's "last 10–20%"는 정합. Radcliffe 2011 Op1 "25% marginal or counterproductive"는 상한 기준 정합~높음. Op2 "70%"는 외부가 큼. Perils Fréchet 경계 [3.6%, 10.0%]는 하단과 부분 정합 | **정합(질적)**. 개인 단위 식별은 불가능함. 외부 범위가 넓고(약 4~70%) 가드레일은 그 중간 이하에 있음 |
| Persuadable 20~30% | Fréchet 상한이 대부분 데이터에서 20% 미만. X5·Op1만 가능 | **높음 가능성**. §4 시사점 3의 내부 정합성 문제도 함께 있음 |

---

## 6. 찾지 못한 것 (미확인)

1. Ascarza (2018) 두 필드 실험의 처치/통제 이탈률, ATE, CATE<0 고객 비율. SAGE(403), HBS PDF(봇 차단), SSRN(봇 차단)으로 본문에 접근하지 못함. "top 10% at risk 중 6%만 receptive"는 2차 검색 요약에서만 봄.
2. Devriendt, Moldovan, Verbeke (2018)의 데이터셋별 처치효과 크기. 논문이 비공개(closed access)임.
3. Gubela, Bequé, Gebert, Lessmann (2019, IJITDM)의 데이터 통계. 원문 PDF가 봇 차단으로 막힘. 대신 같은 그룹의 2020 EJOR 논문 수치를 확인함.
4. Sahni, Zou, Chintagunta (2017)의 정확한 redemption rate 수치(초록에는 "low"로만 적혀 있음).
5. Venkatesan & Farris (2012) 연구 자체의 redemption rate. "about 1 percent"는 보도자료 속 업계 수치임.
6. Inmar의 최근(2020년 이후) 쿠폰당 디지털 사용률. 사용 점유율만 2차로 확인함.
7. Klaviyo, Mailchimp, Braze, Airship의 공식 윈백 또는 푸시 홀드아웃(증분) 벤치마크. Klaviyo는 업종별 flow/campaign 주문률만 있고, Braze와 Airship의 1차 보고서는 찾지 못함.
8. X5 처치가 SMS라는 공식 확인(sklift 문서는 "communication"), Lenta 처치 채널과 target 정의.
9. Criteo arXiv 2111.10106 Table 1의 상대 uplift "68.7 / 37.2"와 직접 계산값(27.1 / 59.3)의 불일치 원인.
10. 무료배송 처치 단독 효과의 RCT 수치. Sahni 2017 예시 오퍼에 무료배송이 있었다는 2차 언급만 있고 별도 효과 크기는 없음.
11. 개인 단위 음의 반응 비율을 직접 식별한 연구. 원리적으로 식별이 불가능하며, 찾은 수치는 모두 세그먼트·모델 기반 추정 또는 §4의 경계임.

---

### 부록: 재현 메모
- 직접 계산에 쓴 원자료(조사자 스크래치패드에 내려받음, 저장소 밖): Hillstrom CSV(minethatdata.com), Criteo v2.1(HuggingFace criteo/criteo-uplift), X5 uplift_train.csv.gz, Lenta lenta_dataset.csv.gz(sklift S3)
- 집계 방식: 처치 플래그별 평균(visit, conversion, spend, target, response_att, exposure). 결측 없음.
