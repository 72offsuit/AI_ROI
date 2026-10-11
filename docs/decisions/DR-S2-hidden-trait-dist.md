# DR-S2-hidden-trait-dist — Hidden Trait 16종은 페르소나 조건부, 페르소나 안에서는 서로 독립으로 뽑는다

[0,1] 범위 Trait 은 Beta(μ_p·κ, (1−μ_p)·κ), κ=12 로 뽑는다. 금액과 주기는 LogNormal σ=0.45, 방문은 Gamma k=4 로 뽑는다.

| | |
|---|---|
| 태스크 | S2 · #76 |
| 작성 | James(BATHOS 역할 에이전트) · 2026-10-06 |
| 상태 | 확정 · 2026-10-11 사용자 확인(권장안 그대로) |

## 무엇을 정하는가

Hidden Trait 은 가상 고객의 두 번째 층이다. 실제 서비스에서는 절대 알 수 없는 값이다(PRD §21 `:837-870`). 이 DR 이 정하는 것은 다음과 같다.

- SRS SIM-002(`:506-527`)의 **16종 각각**에 대해 정한다.
  - 의미
  - 분포족
  - 페르소나별 모수(μ 또는 중앙값)
  - 저장 단위
  - 이 값을 읽을 후속 태스크
- **결합 방식**을 정한다. 페르소나와 무관하게 독립으로 뽑을지, 페르소나 조건부로 뽑고 페르소나 안에서는 독립으로 둘지, copula 로 상관을 줄지 고른다.
- **Beta 와 Uniform 중 무엇을 쓸지**, 그 선택이 S6 처치 효과 이질성에 어떻게 영향을 주는지 정한다.
- **`repurchase_propensity` 의 의미와 모수**를 정한다. data_spec 에 이 Trait 이 없다.
- 이슈 #76 리뷰 질문 두 개에 답한다.
  - *"쿠폰 민감도를 이 분포로 둔 근거가 우리 맥락에 맞나, 아니면 남의 업종 숫자인가?"*
  - *"이 분포가 ±20% 달라지면 S6 의 4분면 비율이 얼마나 움직이나?"*

다른 DR 이 맡는 부분도 있다. 구성비는 `DR-S2-persona-mix` 가 정한다. 정수 표집, 값 표현, 저장은 `DR-S2-trait-sampling` 이 정한다.

## 정하지 않으면 무엇이 막히나

- **S4(행동).** data_spec §3.4(`docs/data_spec.html:259-291`)의 방문·구매·장바구니·세션 식이 모두 Trait 을 읽는다.
- **S5(이탈).** `base_churn_propensity` 가 감쇠 진입 여부와 λ 를 정한다(`:268-270`). 생성 이탈률 15~25%(SRS SIM-005 `:558`)가 여기에 걸린다.
- **S6(처치 반응).** τ 식(`:351-352`)이 `coupon_sensitivity` 와 `marketing_fatigue` 를 직접 읽는다. 4분면 목표(`:379-384`)와 가드레일인 Sleeping Dog 8~15%, 쿠폰 사용률 25~40%(`:372-376`)도 여기에 걸린다.
- **S7(GATE 1).** `HIDDEN TRAIT RULE v1` 을 봉인한다(FREEZE-001 `:1610`). 봉인 뒤에는 AI 결과를 이유로 Churn Propensity, Purchase Probability, Marketing Responsiveness 를 바꿀 수 없다(FREEZE-002 `:1626-1634`).
- 이슈 #76 표에 적힌 대로다. *"쿠폰 민감도를 `Beta(2,5)` 로 둘지 `Uniform` 으로 둘지가 S6 의 처치 효과 이질성을 거의 결정한다."*

## 선택지

| 축 | 안 | 내용 | 장점 | 단점 |
|---|---|---|---|---|
| [0,1] 분포족 | **D-β** | 페르소나별 Beta(μ_p·κ, (1−μ_p)·κ) (`docs/data_spec.html:233-235`) | 평균(μ)과 집중도(κ)를 따로 조절할 수 있다. 지지 범위가 [0,1] 이다. 이질성 혼합분포의 표준 부품이다(아래 조사) | κ 에 근거가 없다 |
| | D-U | Uniform(0,1), 페르소나 무관 | 가정이 가장 적다 | 페르소나 신호가 0 이다. P(fatigue > 0.6) 이 40% 가 되어 Sleeping Dog 상한이 가드레일(8~15%)의 세 배에 가깝다(아래) |
| | D-β1 | 모집단 하나의 Beta, 페르소나 무관(예: 이슈의 Beta(2,5)) | 모수가 2개뿐이다 | 페르소나 신호가 0 이다. "알뜰족인데 쿠폰 민감도 0.1" 같은 조합이 페르소나와 무관하게 나온다 |
| | D-ln | 로짓정규 | 상관 확장이 쉽다 | 정수 표집에 정규 분위표가 필요하고, Beta 보다 나은 근거가 없다 |
| 금액·주기 | **D-LN** | LogNormal(ln 중앙값_p, σ=0.45) | 양수이고 오른쪽 꼬리가 있다. 표준 정규 분위표 하나를 모든 페르소나가 함께 쓴다 | σ 에 근거가 없다 |
| | D-GG | Gamma-Gamma(고객별 평균 거래액이 역감마) | CLV 문헌의 표준 지출 모형이다 | 모수 q, γ 를 우리 데이터로 추정할 수 없다. 꼬리가 무거워 q ≤ 2 이면 분산이 발산한다 |
| 방문 빈도 | **D-Γ** | Gamma(k=4, 평균_p) | Poisson × Gamma = NBD. 구매 빈도 이질성의 표준이다(아래) | k 에 근거가 없다 |
| 결합 | J1 | 페르소나와 무관하게 전부 독립 | 가장 단순하다 | 페르소나가 이름표일 뿐이다. 상관이 0 이다 |
| | **J2** | 페르소나 조건부, 페르소나 안에서는 독립 | 상관과 꼬리가 페르소나 혼합에서 생긴다. 모수가 페르소나 × Trait 표 하나다 | 페르소나 안의 상관(예: 같은 P3 안에서 쿠폰과 가격의 동조)을 표현하지 못한다 |
| | J3 | 가우스 copula 로 페르소나 안 상관까지 줌(Danaher & Smith 2011) | 표현력이 가장 크다 | 16×16 상관행렬(120 모수)에 근거가 전혀 없다. 정수 정규 CDF 와 촐레스키가 더 필요하다 |
| | J4 | 페르소나가 Trait 을 결정(분산 0) | 해석이 쉽다 | 페르소나를 맞히면 Trait 을 맞히게 된다. PRD Risk 2(`Plan/AI_Retention_ROI_PRD_v2.md:2819`)의 Noise·Overlap 요구를 위반한다 |
| κ | κ6 / **κ12** / κ24 | 집중도 | — | 아래 「민감도」 표 |
| `repurchase_propensity` 의미 | **R1** | 구매 1건 뒤 다음 구매로 이어지는 고객 고유 성향. 첫 구매에서 재구매로 넘어가는 깔때기(SRS `:469`)와 T4 Repurchase Reminder 의 대상 신호 | 프로젝트 어휘("Repurchase" = 고객 단위 재구매, SRS `:463` · `:469`, KPI Repurchase Rate)와 맞는다. BG/NBD 의 거래 단위 생존확률 1−p 와 같은 구조다 | `base_churn_propensity`(시간 기반 감쇠)와 이탈을 이중으로 셀 위험이 있다. S4 가 둘의 합성 규칙을 정해야 한다 |
| | R2 | 같은 상품 재주문 성향(장바구니를 과거 구매 상품으로 채울 확률) | 다른 Trait 과 거의 겹치지 않는다 | 프로젝트 어휘와 다르다. 식품 데이터의 59% 재주문 통계(미국 Instacart)를 끌어오게 된다 |
| | R3 | 재구매 알림(T4) 반응성 | T4 와 직결된다 | `marketing_responsiveness` 와 겹친다. T4 는 MVP 처치가 아니다(`config/economic_config.yaml` T4 `mvp: false`, MVP 는 T0·T3) |

## 조사한 것

| 출처 | 무엇을 말하나 | 우리 맥락에 얼마나 맞나 |
|---|---|---|
| Ehrenberg (1959), "The Pattern of Consumer Purchases", *JRSS Series C (Applied Statistics)* 8:26-41 (서지와 요지는 웹 검색 결과로만 확인했고 원문은 열지 못했다) | 정기 구매 브랜드 상품(시리얼, 통조림, 음료, 세제)의 기간 내 구매 횟수가 음이항분포(NBD)를 따른다. NBD = 고객별 Poisson 율이 Gamma 로 퍼진 혼합이다 | **분포족의 근거다.** 방문·구매 빈도의 고객 간 이질성을 Gamma 로 두는 것이 60년 넘게 표준인 이유다. 다만 1950년대 영국 오프라인 브랜드 구매이고, 우리는 소매점 방문이다. **모수는 가져오지 않는다** |
| Schmittlein, Morrison & Colombo (1987), "Counting Your Customers: Who Are They and What Will They Do Next?", *Management Science* 33(1):1-24 (https://ideas.repec.org/a/inm/ormnsc/v33y1987i1p1-24.html) | Pareto/NBD 모형이다. 구매는 Poisson(λ), 수명은 지수(μ)이고, λ 와 μ 가 **서로 독립인 Gamma** 로 퍼진다. 비계약형 환경에서 구매와 이탈을 함께 모형화한 첫 모형이다 | **결합 방식의 선례다.** 구매율과 이탈율을 고객 안에서 독립으로 둔다. 우리 J2 는 이것을 "페르소나 안에서 독립"으로 확장한 것이다. 모수는 가져오지 않는다 |
| Fader, Hardie & Lee (2005), "'Counting Your Customers' the Easy Way: An Alternative to the Pareto/NBD Model", *Marketing Science* 24(2):275-284 (https://brucehardie.com/abstracts/abstract-fhl_2004-04.html) | BG/NBD 모형이다. 거래 직후 이탈확률 p 가 고객 간 **Beta(a, b)** 로 퍼진다. CDNOW 추정값은 r=0.243, α=4.414, a=0.793, b=2.426 이다(검색 결과의 R BTYD 문서·스프레드시트 노트 인용으로 확인. 원 논문 표는 PDF 글꼴 인코딩 때문에 직접 읽지 못했다). pymc-marketing 의 MCMC 재현값도 r≈0.246, α≈4.51, a≈0.785, b≈2.43 이다(https://www.pymc-marketing.io/en/latest/notebooks/clv/bg_nbd.html) | **이탈 성향을 Beta 로 두는 근거다.** CDNOW 의 이탈확률 평균은 0.246, 집중도 a+b=3.22 다. 우리 혼합 모집단 `base_churn_propensity` 의 등가 집중도 κ_eff 는 4.10 으로 같은 자릿수다. 반면 거래율 이질성은 CDNOW CV 2.03, 우리 0.62 로 차이가 크다. 다만 CDNOW 는 **1997년 미국 음반 소매의 첫 구매 코호트**다. 일회성 구매자가 많아 식품 반복구매보다 이질성이 클 것으로 본다(추정이다). **숫자를 쓰지 않고 자릿수 대조에만 쓴다** |
| Fader & Hardie, "The Gamma-Gamma Model of Monetary Value" (2013 노트, https://www.brucehardie.com/notes/025/gamma_gamma.pdf — 본문 첫 쪽을 텍스트로 추출해 확인) | 가정이 셋이다. ① 거래액은 고객 평균 주변에서 무작위로 변한다. ② 고객 평균은 고객마다 다르지만 시간에 따라 변하지 않는다. ③ **고객 평균 거래액의 분포는 거래 과정과 독립이다.** CDNOW 추정값은 p=6.25, q=3.74, γ=15.44 다(검색 결과의 lifetimes 재현값으로 확인. 노트 표는 직접 읽지 못했다). pymc-marketing 은 CDNOW 에서 평균 거래액과 빈도의 상관이 약 0.11 이라 "진행 가능할 만큼 낮다"고 했다(https://www.pymc-marketing.io/en/latest/notebooks/clv/gamma_gamma.html) | ②는 "Trait 은 고객 고유이고 시간에 불변"이라는 우리 설계와 같다. ③은 J2 의 페르소나 안 독립과 같다. q=3.74 가 함의하는 고객 평균 거래액의 CV 는 0.76 이고, 우리 혼합 모집단 `base_order_value` 의 CV 는 0.556 이다. **음반과 식품은 객단가 구조가 달라 숫자를 쓰지 않는다** |
| Chatfield & Goodhardt (1970), "The Beta-Binomial Model for Consumer Purchasing Behaviour", *JRSS Series C* 19(3):240-250 (https://ideas.repec.org/a/bla/jorssc/v19y1970i3p240-250.html — 서지만 확인) · NBD-Dirichlet (Goodhardt, Ehrenberg & Chatfield 1984) | 기회당 구매확률이 고객 간 Beta 로 퍼진다(베타-이항). Dirichlet 모형은 구매 발생 Poisson, 구매율 Gamma, 브랜드 선택 다항, 선택확률 Dirichlet 의 4단 혼합이다 | **`base_purchase_probability` 를 Beta 로 두는 근거다**(방문 = 기회). 모수는 영국 패널이라 쓰지 않는다 |
| Kim, Singh & Winer (2017), *Marketing Letters* 28(4):491-507 (https://ideas.repec.org/a/kap/mktlet/v28y2017i4d10.1007_s11002-017-9442-5.html) | 미국 CPG 브랜드 수준 Pareto 비율 평균 0.73 | "RFM 분포는 헤비테일인가"에 대한 답이다. 우리 생성 모수만으로 지출률(방문 × 구매확률 × 객단가)을 계산하면 상위 20% 지출 비중은 약 0.676 이다. 같은 자릿수지만 그쪽은 **브랜드** 수준이고 우리는 **소매점** 수준이라 맞춰야 할 목표가 아니다 |
| Narasimhan (1984), "A Price Discrimination Theory of Coupons", *Marketing Science* 3(2):128-147 (https://ideas.repec.org/a/inm/ormksc/v3y1984i2p128-147.html — 초록 확인) | 쿠폰 사용자는 비사용자보다 **가격탄력적**이다. 시간의 기회비용 같은 가구 자원이 쿠폰 사용을 결정한다 | **쿠폰 민감도와 가격 민감도가 같은 방향으로 움직인다는 방향의 근거다.** 우리 혼합에서 corr(coupon, price) 는 +0.65 다. 1980년대 미국 제조사 종이 쿠폰이고 우리는 국내 앱 쿠폰이라 **크기는 가져오지 않는다** |
| Lichtenstein, Netemeyer & Burton (1990), "Distinguishing Coupon Proneness from Value Consciousness", *Journal of Marketing* 54(3):54-67 (https://vivo.colorado.edu/display/pubid_59898 — 초록 확인) | 쿠폰 반응 행동은 **가치 의식과 쿠폰 성향 두 구성개념** 모두의 발현이다 | `coupon_sensitivity` 를 `price_sensitivity` 와 별개 Trait 으로 두는 근거다. 미국 소비자 설문이다. 분포 모양은 말하지 않는다 |
| Lichtenstein, Netemeyer & Burton (1995), "Assessing the Domain Specificity of Deal Proneness: A Field Study", *Journal of Consumer Research* 22(3):314-326 (https://ideas.repec.org/a/oup/jconrs/v22y1995i3p314-26.html — 요지 확인) | 딜 성향은 **영역 특수적**이다. 쿠폰 성향과 세일 성향을 나눠 재는 쪽이 행동을 더 잘 예측했다 | 고객당 쿠폰 민감도 스칼라 하나는 단순화다. 우리 서비스는 식품 한 영역이고 처치도 쿠폰(T3) 하나라 허용할 수 있다. 다처치(T1 무료배송·T2 정액)로 넓히면 다시 볼 일이다 |
| Bawa & Shoemaker (1987), "The Coupon-Prone Consumer: Some Findings Based on Purchase Behavior Across Product Classes", *Journal of Marketing* 51(4):99-110 | 제목, 게재지, 쪽수만 확인했다. 초록은 403 으로 읽지 못했다 | **후보다. 내용을 확인하지 못했으므로 근거로 쓰지 않는다** |
| Morrison & Schmittlein (1988), "Generalizing the NBD Model for Customer Purchases", *J. Business & Economic Statistics* 6(2):145-159 | 서지만 확인했다. Erlang 구매간격 일반화를 다룬 것으로 인용된다 | **후보다.** 구매간격의 규칙성은 S4 의 몫이라 S2 는 쓰지 않는다 |
| Danaher & Smith (2011), "Modeling Multivariate Distributions Using Copulas: Applications in Marketing", *Marketing Science* 30(1):4-21 (https://pubsonline.informs.org/doi/10.1287/mksc.1090.0491 — 초록 확인) | copula 로 서로 다른 주변분포를 결합할 수 있다. 타원형 copula 는 차원이 늘어도 복잡도가 천천히 는다 | J3 가 방법론상 가능하다는 근거다. **상관 모수의 근거는 아니다** |
| 오픈서베이 2023 · 바이라인네트워크(https://byline.network/2023/01/30_0976) | 컬리 이용자는 월 2.5회 구매하고, 1회 평균 44,800원을 쓴다(자기응답, n=800) | 국내 온라인 식료품이다. 우리 생성 모수의 모집단 평균은 월 2.53회(S4 미반영 상한), 객단가 45,889원, 구매주기 중앙값 가중평균 16.4일이다. 2.5회/월이면 간격이 약 12일이다. **자릿수 대조일 뿐이고 페르소나별 근거는 아니다** |
| 컬리 보도자료(2020, https://www.venturesquare.net/806256/) | 2019년 가입 고객의 재구매율 61.2% | `repurchase_propensity`(R1)와 같은 종류의 지표다. 다만 정의, 관찰 기간, 모수를 밝히지 않은 회사 발표라 **모수 근거로 쓰지 않는다** |
| Instacart Market Basket Analysis 데이터(2017, 약 20만 이용자, 340만 주문) 분석 글(https://towardsdatascience.com/instacart-market-basket-analysis-part-1-which-grocery-items-are-popular-61cadbb401c8) | 주문 상품의 약 59% 가 이전에 주문한 상품이다 | R2 의미를 택했을 때의 자릿수다. 미국 앱 대행 장보기의 **주문 라인** 기준이라 고객 성향 평균과 같지 않다. R2 를 택하지 않으므로 쓰지 않는다 |
| `docs/data_spec.html:232-257` §3.3 | 15종의 분포족과 페르소나별 μ·중앙값이 있다. κ=12, σ=0.45, Gamma k=4 다 | **출처 표기가 없다.** SRS 의 16종 가운데 `repurchase_propensity` 가 빠져 있다 |
| PRD §21 `:859` · `src/measurement/kpi.py:793` | `average_order_value` 는 **관측 가능한** 데이터와 측정 KPI 의 이름이다 | Hidden Trait 이 같은 이름을 쓰면 관측 KPI 와 숨은 값이 이름으로 섞인다. U5 대로 `base_order_value` 로 저장한다 |
| 쿠폰 민감도의 **분포 모양과 모수**, 국내 온라인 식품 맥락 | 찾지 못했다. 문헌이 주는 것은 이질성이 있다는 사실, 가격 민감도와의 방향, 별개 구성개념이라는 점뿐이다 | **근거를 찾지 못했다.** Beta 의 μ_p 와 κ 는 근거 없는 값이다. 민감도 분석으로 대신한다 |
| `repurchase_propensity` 의 페르소나별 모수 | 찾지 못했다 | **근거를 찾지 못했다.** 아래 잠정값과 민감도로 둔다 |
| scratchpad 계산 `…/scratchpad/james/s2_mix_tails.py` · `s2_kappa_alt.py` · `s2_scale_checks.py`(출력 `out_*.txt`) | 혼합 모집단 모멘트, η²(페르소나가 설명하는 분산 비율), Trait 간 상관, τ 입력 꼬리 질량의 해석해(scipy, 페르소나 안 독립), 같은 난수로 짝지은 n=26,000 몬테카를로, κ 대안 | 생성 모수 수준의 계산이다. τ 의 `recency_gain`(S4 상태)과 Y(0)·Y(1)(S5·S6)은 들어 있지 않다 |

## 결정

**D-β · D-LN · D-Γ · J2 · κ=12 · R1.** 모수는 data_spec §3.3 초안을 쓰고, `repurchase_propensity` 만 잠정값을 쓴다. 정수 단위는 `DR-S2-trait-sampling` 이 정한다.

| # | SRS 이름 → 저장 이름 | 의미 | 분포 | P1 | P2 | P3 | P4 | P5 | P6 | 읽는 태스크 |
|---|---|---|---|---:|---:|---:|---:|---:|---:|---|
| 1 | `base_visit_frequency` | 기준 방문 빈도(회/주) | Gamma k=4, 평균 | 4.5 | 2.8 | 2.0 | 3.5 | 1.4 | 2.2 | S4 방문 `p_visit`(`:261`) |
| 2 | `base_purchase_probability` | 방문당 기준 구매확률 | Beta κ=12 | .42 | .30 | .18 | .10 | .12 | .20 | S4 구매(`:273`) |
| 3 | `average_order_value` → **`base_order_value`** | 기준 객단가(원) | LogNormal σ=.45, 중앙값 | 72,000 | 48,000 | 34,000 | 39,000 | 31,000 | 36,000 | S4 장바구니 크기(`:283`) |
| 4 | `purchase_cycle` | 기준 구매 간격(일) | LogNormal σ=.45, 중앙값 | 6 | 10 | 16 | 21 | 30 | 14 | S4 `cycle_factor`(`:277`) |
| 5 | `price_sensitivity` | 가격 민감도 | Beta κ=12 | .20 | .35 | .80 | .50 | .45 | .45 | S4 `price_factor`(`:278`) |
| 6 | `coupon_sensitivity` | 쿠폰 민감도 | Beta κ=12 | .25 | .40 | .85 | .45 | .50 | .60 | S4 `coupon_factor`(`:279`), **S6 τ 양 성분**(`:351`) |
| 7 | `shipping_fee_sensitivity` | 배송비 민감도 | Beta κ=12 | .15 | .40 | .70 | .50 | .45 | .55 | S4 `ship_factor`(`:280`) |
| 8 | `brand_loyalty` | 브랜드·상품 충성 | Beta κ=12 | .85 | .70 | .25 | .30 | .30 | .40 | **data_spec 행동식에 쓰는 곳이 없다** → S4 가 정한다 |
| 9 | `repurchase_propensity` | 구매 뒤 재구매 성향(R1) | Beta κ=12 | **.85** | **.75** | **.60** | **.50** | **.40** | **.55** | S4. **잠정값이고 근거를 찾지 못했다** |
| 10 | `base_churn_propensity` | 이탈 진행 성향 | Beta κ=12 | .04 | .10 | .22 | .28 | .55 | .30 | S4·S5 감쇠 λ·진입(`:268-270`) |
| 11 | `marketing_responsiveness` | 마케팅 반응성 | Beta κ=12 | .35 | .45 | .75 | .40 | .30 | .65 | **τ 식이 읽지 않는다** → S6 가 정한다 |
| 12 | `marketing_fatigue` | 마케팅 피로 | Beta κ=12 | .30 | .25 | .15 | .30 | .55 | .10 | **S6 τ 음 성분**(`:352`) |
| 13 | `search_propensity` | 탐색 성향 | Beta κ=12 | .30 | .35 | .55 | .85 | .25 | .60 | S4 `page_views`·세션(`:285-286`) |
| 14 | `cart_abandonment_propensity` | 장바구니 이탈 성향 | Beta κ=12 | .15 | .25 | .45 | .65 | .40 | .40 | S4(`:287`) |
| 15 | `cs_contact_propensity` | 고객센터 문의 성향 | Beta κ=12 | .10 | .10 | .18 | .12 | .22 | .20 | S4(`:291`) |
| 16 | `review_propensity` | 리뷰 작성 성향 | Beta κ=12 | .30 | .20 | .15 | .20 | .10 | .25 | S4(`:290`) |

- **결합(J2).** 페르소나를 먼저 뽑고, Trait 마다 그 페르소나의 분포에서 **독립으로** 한 번씩 뽑는다. Trait 마다 난수 용도를 따로 둔다(`DR-S2-trait-sampling`).
- **κ 는 Trait 마다 config 칸을 둔다.** 지금은 전부 12 다. 표적 민감도 분석을 하려고 칸을 두는 것이고, 값을 바꾸려는 것이 아니다.
- **R1 의 정의.** "구매 1건 뒤, 그 고객이 다음 구매로 이어질 고객 고유 성향 [0,1]."
  - S4 는 이것과 `base_churn_propensity`(시간 기반 감쇠 진입)를 **어떻게 합성하는지, 혹은 한쪽만 쓰는지**를 자기 DR 에 적어야 한다.
  - 둘 다 그대로 쓰면 이탈을 두 번 세게 된다. Pareto/NBD 는 시간 기반, BG/NBD 는 거래 기반이다. 두 문헌은 둘 중 **하나**를 고른다.
- **잠정값의 성격.** R1 잠정값은 PRD §17 의 서열만 반영해 정했다. P1 이 높은 충성, P5 가 감쇠, P6 이 "첫 구매 여부가 중요"하다는 서술이다.
  - 모집단 평균은 0.607 이다. 컬리 보도자료의 61.2% 와 자릿수가 같지만 그 지표는 정의가 공개되지 않았다. **이것을 근거로 쓰지 않는다.**
- **데이터에 소비처가 없는 Trait 이 셋 있다.** `brand_loyalty`, `marketing_responsiveness`, `repurchase_propensity` 다.
  - data_spec 행동식과 τ 식 어디에서도 읽지 않는다.
  - 생성과 저장은 하지만(U5, SRS 16종), **S4·S6 가 소비처를 정하거나 "쓰지 않는다"고 DR 에 적어야 한다.** 그러지 않으면 봉인되는 죽은 값이 된다.

**근거.**

- **분포족.** 고객 간 이질성의 혼합분포로 Gamma(빈도)와 Beta(확률)를 쓰는 것은 NBD, 베타-이항, Pareto/NBD, BG/NBD 계열이 60년 동안 표준으로 써 온 부품이다. 그래서 **분포족은 근거가 있다.**
- **모수.** μ_p, κ, σ, k 는 data_spec 초안이고 출처가 없다. **모수는 근거가 없다.** 분포족과 모수에 대한 판단을 구분해서 적는다.
- **Beta 와 Uniform — 이슈 표에 대한 답.** Uniform 이면 쿠폰과 피로가 페르소나와 무관해진다(η²=0). 그러면 τ 입력이 다음처럼 바뀐다(해석해).

  | 분포 | P(fatigue > 0.6) = Sleeping Dog 상한 | Persuadable 후보 질량 | E[τ 음 성분의 Trait 부분] | 페르소나가 설명하는 coupon 분산 η² |
  |---|---:|---:|---:|---:|
  | **Beta κ=12, data_spec μ** | **6.18%** | **33.81%** | 0.0135 | **0.681** |
  | Uniform(0,1) | 40.00% | 24.00% | 0.2000 | 0 |
  | 모집단 Beta(2,5) | 4.10% | — | — | 0 |

  - Uniform 이면 Sleeping Dog 후보가 가드레일 상한 15% 의 2.7배가 된다. 음 성분의 기댓값은 15배가 된다.
  - 무엇보다 **누가 Persuadable 이고 누가 Sure Thing 인지가 페르소나나 다른 Trait 과 무관한 동전 던지기**가 된다. 이슈의 "Uniform 이면 뭉개진다"가 수치로 맞다.
  - 용어 정의. **Persuadable 후보 질량**은 P(coupon > 0.6, fatigue ≤ 0.6) 이다. fatigue ≤ 0.6 이면 τ 의 음 성분이 정확히 0 이다. **Sleeping Dog 상한**은 τ 가 음수가 되기 위한 필요조건 fatigue > 0.6 의 질량이다(`:351-352`).
- **J2 와 "조건부면 페르소나를 맞히면 Trait 을 맞힌다"는 우려 — 이슈 표에 대한 답.**
  - 페르소나가 설명하는 분산 비율 η² 는 Trait 마다 다르다. `cs_contact` 0.19, `review` 0.20 에서 `search` 0.73, `brand_loyalty` 0.75 까지 퍼져 있다. `coupon_sensitivity` 는 0.68 이다.
  - **페르소나를 완벽히 맞혀도 쿠폰 민감도 분산의 32% 는 개인차로 남는다.** 페르소나 자체가 관측되지 않는다는 점도 있다(PRD §21, FORBIDDEN_FIELD_NAMES 에 `persona`).
  - 극단 쌍은 거의 겹치지 않는다. 같은 κ=12 에서 P(P3 고객의 coupon < P1 고객의 coupon) 은 6.6×10⁻⁴ 이다. 인접 쌍은 겹친다. P4 와 P5 는 평균이 0.45 대 0.50 이다.
  - J2 에서 Trait 사이 상관은 **전부 페르소나 혼합에서 나온다.**
    - corr(coupon, price) = +0.65
    - corr(coupon, brand_loyalty) = −0.52
    - corr(coupon, responsiveness) = +0.55
    - corr(fatigue, churn) = +0.38
    - corr(search, cart_abandon) = +0.55
    - corr(purchase_prob, churn) = −0.42
  - 이 부호들은 PRD §17 의 서술과 Narasimhan(1984)의 방향과 맞는다.
- **쿠폰 민감도 — 리뷰 질문 "남의 업종 숫자인가?"에 대한 답.**
  - **남의 업종 숫자는 하나도 쓰지 않았다. 쓸 숫자 자체가 없었다.**
  - 문헌에서 온 것은 **방향**뿐이다.
    - 쿠폰 성향은 고객마다 다르다.
    - 쿠폰 성향은 가격 민감도와 같은 방향이다(Narasimhan 1984).
    - 쿠폰 성향은 가치 의식과 별개 구성개념이다(Lichtenstein et al. 1990).
    - 쿠폰 성향은 영역 특수적이다(1995).
  - μ_p(0.25~0.85)와 κ=12 는 data_spec 초안이고 출처가 없다. 그래서 **우리 맥락에 맞는지 확인할 수 없다.**
  - 그 대신 아래 「민감도」가 이 값이 틀렸을 때 τ 입력이 얼마나 흔들리는지를 보인다.
- **연속량.**
  - 생성 모수만으로 본 모집단 평균은 국내 컬리 이용자 설문과 같은 자릿수다(월 2.53회 대 2.5회, 45,889원 대 44,800원).
  - 혼합 모집단의 이질성은 CDNOW 보다 약하다. 방문 CV 는 0.62(등가 Gamma shape 2.58)이고 CDNOW 거래율 CV 는 2.03 이다. 객단가 CV 는 0.556 이고 CDNOW 는 0.76 이다.
  - 그래도 상위 20% 지출 비중은 0.676 으로, 지출 집중이 생긴다(헤비테일 성격).
  - LogNormal 을 고른 이유는 단순하다. 표준 정규 분위표 하나를 6 페르소나 × 2 Trait 이 함께 쓸 수 있어 정수 표집이 가장 단순하다(`DR-S2-trait-sampling`).

## 기각한 안과 기각 사유

| 안 | 왜 택하지 않았나 |
|---|---|
| D-U (Uniform) | Sleeping Dog 상한이 40% 다. 가드레일 8~15% 와 양립할 수 없다. 페르소나 신호가 0 이라 4분면이 Trait 구조와 무관한 잡음이 된다 |
| D-β1 (모집단 단일 Beta, 예: Beta(2,5)) | 페르소나 신호가 0 이다. 이슈의 "알뜰족인데 쿠폰 민감도 0.1" 이 페르소나와 무관하게 나온다. Beta(2,5) 의 근거도 없다 |
| D-ln (로짓정규) | Beta 보다 나은 근거가 없다. J3 로 갈 때 다시 볼 안이다 |
| D-GG (Gamma-Gamma) | CLV 문헌의 표준이지만 q, γ 를 우리 데이터로 추정할 수 없다. CDNOW 숫자를 쓰면 "남의 업종 숫자"가 된다. q ≤ 2 이면 분산이 발산해 생성 단계 검정(평균·분산 4 SE)이 성립하지 않는다 |
| J1 (전부 독립) | 페르소나가 이름표일 뿐이 된다. P3 를 빼도 아무것도 안 바뀌는 구조라 `DR-S2-persona-mix` 의 "왜 6종인가"에 답할 수 없다 |
| J3 (copula) | 페르소나 안 상관 120개에 근거가 0 이다. 근거 없는 모수를 120개 늘리는 것은 정밀함이 아니라 위장이다. S4·S6 의 실현 분포가 페르소나 안 상관이 필요하다고 보여 줄 때 다시 연다 |
| J4 (페르소나 = Trait) | PRD Risk 2(Unrealistically Easy Model)의 완화 수단인 Noise·Overlap·Heterogeneity 를 정면으로 위반한다 |
| κ=6 · κ=24 | 아래 「민감도」. κ=6 은 페르소나 신호가 약해지고(coupon η² 0.54) Sleeping Dog 상한이 8.98% 로 오른다. κ=24 는 페르소나가 Trait 을 거의 결정한다(η² 0.80, Sleeping Dog 상한 4.79%). 어느 쪽에도 근거가 없어 data_spec 값 12 를 유지한다. **가드레일에 맞추려고 κ 를 고르지 않는다**(아래 「이 결정이 틀렸다면」) |
| R2 (같은 상품 재주문) | 프로젝트 어휘("Repurchase" = 고객 단위 재구매, 깔때기, KPI)와 다르다. 다른 의미로 쓰면 SRS 이름과 의미가 어긋나는 함정이 된다 |
| R3 (알림 반응성) | `marketing_responsiveness` 와 겹친다. T4 는 MVP 처치(T3)가 아니다 |
| `average_order_value` 이름 그대로 저장 | 관측 KPI(`kpi.py:793`, PRD §21 `:859`)와 같은 이름이 된다. 격리 지문 검사와 사람의 읽기 모두에서 숨은 값과 관측값이 섞인다(U5) |

## 이 결정이 틀렸다면 어떻게 드러나나

- **구현 결함.** 생성 표본의 (페르소나, Trait)별 KS 검정(Bonferroni)과 평균·분산 4 SE 검사가 기각되면, 표집이 선언한 분포를 내지 않는 것이다. 이 검사는 이슈 「증거로 남길 것」이다.
- **S6 Sleeping Dog 가드레일 8~15% — 지금 이미 보이는 위험 신호.**
  - data_spec τ 식에서 τ 가 음수가 되려면 `marketing_fatigue > 0.6` 이어야 한다. 그래서 경로 의존 효과를 빼면 Sleeping Dog 비율은 **P(fatigue > 0.6) = 6.18%** 를 넘을 수 없다.
  - 실제 Sleeping Dog 는 Y(0)=1 까지 요구하므로 이보다 작다. **가드레일 하한 8% 에 못 미칠 가능성이 높다.**
  - **지금 S2 에서 고치지 않는 이유가 셋 있다.**
    - ① 가드레일은 Eligible 모집단과 S5·S6 의 실현값에 대한 것이다. S2 에서는 실현값을 계산할 수 없다.
    - ② 고칠 수 있는 손잡이가 여럿이다. P5 의 fatigue μ, κ, τ 식의 임계 0.6, P5 비중이 있다. 어느 손잡이를 쓸지는 τ 식과 함께 S6 가 판단해야 한다.
    - ③ data_spec 이 가드레일 이탈 시 "GATE 1 이전에 조정"하는 절차를 이미 두고 있다(`:371`). 다만 data_spec 이 지목한 손잡이 `τ_base = 0.55` 는 양 성분 계수라서 **Sleeping Dog 상한을 올리지 못한다.**
  - S6 는 이 사실을 알고 시작해야 한다. **조정 근거는 가드레일뿐이고 AI 결과가 아니다**(FREEZE-002).
- **S5 생성 이탈률 15~25%.** 실현 이탈률이 범위를 벗어나고 원인이 `base_churn_propensity` 분포에 있으면 이 DR 을 다시 연다.
- **J2 의 한계.** S4 이후 실현 KPI 에서 페르소나 안 Trait 상관이 없어서 생기는 비현실이 드러날 수 있다. 예를 들어 같은 P3 안에서 쿠폰 반응과 가격 반응이 무관하게 나오는 경우다. 그러면 J3 를 다시 연다.
- **외부 자릿수.** S4 실현 구매 빈도나 실현 객단가가 국내 자릿수(월 2.5회, 44,800원)에서 배 단위로 벗어나면 빈도·금액 모수를 다시 연다.
- **R1 의미.** S4 가 `repurchase_propensity` 를 쓸 곳을 찾지 못하거나 `base_churn_propensity` 와 합성할 수 없다고 판단하면, 의미를 R2 로 바꾸거나 "생성만 하고 쓰지 않음"으로 번복한다.

## 민감도

**리뷰 질문 "이 분포가 ±20% 달라지면 S6 의 4분면 비율이 얼마나 움직이나?"에 대한 정직한 답.**

4분면 비율은 S2 에서 **계산할 수 없다.** 이유는 셋이다.

- τ 에 들어가는 `recency_gain` 은 T0 시점의 `days_since_last_purchase` 로, S4 행동의 결과다.
- 4분면을 정하는 Y(0)·Y(1) 은 S5·S6 의 이중 실행 결과다.
- 경로 의존 때문에 τ 의 부호만으로 분면이 정해지지도 않는다.

계산할 수 있는 것은 **τ 입력의 꼬리 질량**이다. 아래 표가 그것이다. 해석해는 scipy `beta.sf` 와 페르소나 안 독립 가정으로 구했고, 교차 확인은 같은 난수로 짝지은 n=26,000 몬테카를로로 했다. 둘의 차이는 0.2%p 이내였다. 스크립트는 `…/scratchpad/james/s2_mix_tails.py`, 출력은 `out_mix_tails.txt` 3~4·6절이다.

| 시나리오 | P(fatigue > 0.6) Sleeping Dog 상한 | Persuadable 후보 P(c > .6, f ≤ .6) | E[c · 1{f ≤ .6}] τ 양 성분 | E[max(0, f−.6)/.4] τ 음 성분 |
|---|---:|---:|---:|---:|
| **기준** (data_spec μ, κ=12) | **6.18%** | **33.81%** | 0.5007 | 0.0135 |
| κ ×0.8 (coupon·fatigue, κ=9.6) | 6.88% | 34.84% | 0.4976 | 0.0165 |
| κ ×1.2 (κ=14.4) | 5.73% | 32.94% | 0.5027 | 0.0115 |
| **fatigue μ ×0.8** (전 페르소나) | **2.16%** | 34.75% | 0.5204 | 0.0035 |
| **fatigue μ ×1.2** | **11.92%** | 32.54% | 0.4730 | 0.0358 |
| **coupon μ ×0.8** | 6.18% | **20.44%** | 0.4005 | 0.0135 |
| **coupon μ ×1.2** (P3 1.02 → 0.95 로 자름) | 6.18% | **46.80%** | 0.5854 | 0.0135 |
| P5 비중 ×0.8 / ×1.2 (`DR-S2-persona-mix`) | 5.09 / 7.28% | 34.46 / 33.16% | 0.507 / 0.494 | 0.011 / 0.016 |
| P3 비중 ×0.8 / ×1.2 | 6.53 / 5.84% | 30.20 / 37.42% | 0.481 / 0.520 | 0.014 / 0.013 |

**κ 대안**(`out_kappa_alt.txt`)

| κ | coupon η² | P(fatigue > 0.6) | Persuadable 후보 | P(P3 coupon < P1 coupon) |
|---:|---:|---:|---:|---:|
| 6 | 0.535 | 8.98% | 36.72% | 8.6×10⁻³ |
| **12** | **0.681** | **6.18%** | **33.81%** | 6.6×10⁻⁴ |
| 24 | 0.804 | 4.79% | 30.62% | 4.6×10⁻⁶ |
| 48 | 0.889 | 3.68% | 28.40% | 2.8×10⁻¹⁰ |

읽는 법은 다섯 가지다.

- **가장 민감한 손잡이는 fatigue μ 다.** ±20% 에 Sleeping Dog 상한이 0.35배에서 1.93배로 움직인다(2.16~11.92%). 거의 전부가 P5 의 μ=0.55 에서 온다. P5 혼자 6.18%p 중 5.59%p 를 기여한다. Beta 의 꼬리 질량은 μ 가 임계(0.6) 근처일 때 μ 에 가장 민감하기 때문이다.
- **coupon μ ±20%** 는 Sleeping Dog 상한을 바꾸지 않는다. 대신 Persuadable 후보를 20~47% 사이로 움직인다. 4분면 목표 Persuadables 는 20~30% 다.
- **κ ±20%** 는 두 질량 모두 ±1%p 안팎으로만 움직인다. κ 의 근거 부족은 μ 의 근거 부족보다 덜 위험하다.
- **같은 ±20% 라도 페르소나 비중보다 Trait μ 쪽이 훨씬 크게 움직인다.** 비중은 Sleeping Dog 상한을 최대 ±1.1%p 움직이고, μ 는 −4.0~+5.7%p 움직인다.
- **`repurchase_propensity` 잠정값 ±20%.** 페르소나 μ 가 0.32~0.68(×0.8)에서 0.48~0.95(×1.2, P1 1.02 → 0.95 로 자름) 범위가 된다. 모집단 평균은 0.607 에서 0.49~0.72 로 움직인다. 이 값을 읽는 식이 S4 전에는 없어서 하류 영향은 계산할 수 없다. **그렇게 적는다.**

## 남은 불확실성

- **모수 전부에 외부 근거가 없다.** 분포족은 문헌이 받쳐 준다. μ_p, κ, σ, k 는 data_spec 초안이다. 국내 온라인 식품 커머스의 고객 단위 이질성 추정치(NBD r, BG/NBD a·b 등)가 공개되면 해소된다. 찾지 못했다.
- **Sleeping Dog 하한 미달 위험.** 상한이 6.18% 이고 가드레일은 8% 다. S6 전에는 실현값을 알 수 없다. 어느 손잡이로 조정할지도 S6 가 τ 식과 함께 판단한다. **조정이 필요해지면 이 DR 과 `DR-S2-persona-mix` 를 GATE 1 전에 번복하고 그 근거로 가드레일만 적는다.**
- **R1 과 `base_churn_propensity` 의 합성.** S4 가 정한다. 두 Trait 을 함께 쓰면 이탈을 이중으로 셀 위험이 있고, PRD Risk 2 의 "너무 쉬운 모델"을 낳을 수 있다는 점을 S4 에 넘긴다.
- **소비처가 없는 Trait 셋**(`brand_loyalty`, `marketing_responsiveness`, `repurchase_propensity`). S4·S6 가 쓸 곳을 정하지 않으면 GATE 1 에 죽은 값으로 봉인된다.
- **원문을 직접 읽지 못한 수치가 있다.** BG/NBD 와 Gamma-Gamma 의 CDNOW 모수는 2차 인용(R BTYD, lifetimes, pymc-marketing)으로만 확인했다. Bawa & Shoemaker(1987)와 Morrison & Schmittlein(1988)은 서지만 확인했다.
- 후속 이슈 후보(보고만 하고 고치지 않는다).
  - `src/measurement/schema.py:238-248` 의 `FORBIDDEN_FIELD_NAMES` 에 `repurchase_propensity`, `base_order_value`, `hidden_traits` 가 없다.
  - data_spec §3.3 은 15종이다(SRS 는 16종). AOV 이름이 `average_order_value` 다.
  - data_spec `:371` 이 가드레일 이탈 시 조정할 손잡이로 `τ_base` 만 지목하는데, 이 손잡이로는 Sleeping Dog 하한을 맞출 수 없다.
