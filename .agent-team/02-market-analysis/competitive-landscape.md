# 경쟁 지형 — T1.11

**작성** Caleb (W1 Discovery) · 2026-09-11
**핵심 질문**: *"예측 정확도가 아니라 Incremental Profit을 파는 제품이 실제로 존재하는가?"* — 이 프로젝트 USP의 성립 여부를 가르는 질문.

> 모든 항목에 출처 URL과 확인 날짜(2026-09-11)를 표기한다. 가격은 대부분 비공개이며, 비공개 사실 자체를 명기한다.

---

## 조사 대상 5개 + 제외 1개

Braze · Optimove · Klaviyo · Bloomreach · Amplitude를 조사했다. Retention Science는 조사했으나 **경쟁사 목록에서 제외**한다(사유는 하단 참조).

---

## 1. Braze

| 항목 | 내용 |
|---|---|
| **무엇을 파는가** | 고객 인게이지먼트 플랫폼(이메일·푸시·인앱 메시징). `Braze Predictive Suite`의 `Predictive Churn`이 이탈 위험 점수(0~100)를 산출해 캠페인 타겟팅에 연결한다. |
| **가격 공개 여부** | **비공개.** 공개 가격 페이지·무료 플랜·월 단위 과금이 없다. MAU와 메시지 볼륨 기반 커스텀 연간 계약. 제3자(Vendr·G2) 계약 데이터 기준 중견기업 연 $50,000~$200,000, 대형 계약은 $500,000 이상, 초대형 소비자 브랜드는 7자리(수백만 달러)까지 보고된다. |
| **ROI를 어떻게 증명하는가** | **예측 정확도(Prediction Accuracy) 지표로 증명한다, Incremental Profit이 아니다.** `Prediction Quality` 점수를 사용 — 0%면 무작위 추측과 동일, 그 이상이면 실제 이탈자를 얼마나 잘 맞혔는지를 나타낸다. 모델을 학습→검증(1차: 과거 데이터 기준 예상 정확도 즉시 측정, 2차: 예측 기간 경과 후 실제 결과와 재대조)하는 2단계 검증 절차를 갖는다. **이 검증 절차 어디에도 Rule-based Baseline 대비 손익 비교가 없다** — "얼마나 잘 맞췄나"이지 "그래서 얼마를 더 벌었나"가 아니다. |
| **한계** | 캠페인 실행 후 매출 증분을 별도로 증명하는 기능이 공개 문서에서 확인되지 않는다. 정확도가 높아도 그 정확도가 실제 이익으로 전환됐는지는 사용자가 별도로 계산해야 한다. |
| **출처** | [Braze: Measuring Prediction Accuracy in the Braze Predictive Suite](https://www.braze.com/resources/articles/measuring-prediction-accuracy-in-the-braze-predictive-suite)(2026-09-11 확인) · [Braze Predictive Churn Docs](https://www.braze.com/docs/user_guide/brazeai/predictive_suite/predictive_churn)(2026-09-11 확인) · [StackScored: Braze Pricing 2026](https://www.stackscored.com/pricing/marketing-automation/braze/)(2026-09-11 확인) |

---

## 2. Optimove

| 항목 | 내용 |
|---|---|
| **무엇을 파는가** | 리텐션 마케팅 플랫폼(CRM 오케스트레이션 + 자가최적화 캠페인). "Productized Control Groups"라는 기능으로 캠페인마다 자동으로 대조군을 떼어 반응을 비교한다. |
| **가격 공개 여부** | **비공개.** 월 구독제, 고객 데이터베이스 규모·네트워크 수 기준. 제3자 보고 기준 시작가는 월 약 $4,000선으로 언급되나 공식 가격표는 없다. |
| **ROI를 어떻게 증명하는가** | **조사한 5개 도구 중 가장 근접 — 그러나 캠페인 단위이지 전략(정책) 단위 손익 비교가 아니다.** Optimove는 캠페인을 실행할 때 통제군(Control Group)을 자동으로 떼어, 그 캠페인이 대조군 대비 만들어낸 **"Increase in"(증분 반응/매출)** 을 계산해 보여준다. 사례(NYRA 등)에서 캠페인당 구체적 증분 순매출액(예: 특정 캠페인 +$17,792)을 제시한다. 이는 **A/B 대조군 기반 인과 추론이라는 점에서 우리 프로젝트와 방법론적으로 가장 유사**하다. |
| **한계** | ① 비교 단위가 **개별 캠페인**이지, "AI 알고리즘 전체 vs Rule-based Baseline"처럼 **의사결정 전략(정책) 수준**의 비교가 아니다. ② 공개 자료에서 이 증분 계산에 처치 비용(쿠폰·메시징 비용)을 뺀 **순이익(Contribution Margin 기준)** 인지, 단순 매출 증분인지 명확히 구분되지 않는다 — "매출 증분"과 "이익 증분"은 다른 주장이다. ③ 공개된 사례 연구가 마케팅 성과 홍보 목적의 사례이지, 방법론 자체를 검증 가능한 형태로 공개하지 않는다(계산식 비공개). |
| **출처** | [Optimove: NYRA Case Study](https://www.optimove.com/resources/case-studies/nyra)(2026-09-11 확인) · [Optimove: What is "Increase in" or Uplift?](https://academy.optimove.com/hc/en-us/articles/8727494583965-What-is-Increase-in-or-Uplift)(제목만 확인 — 본문은 인증 필요 페이지라 403, 2026-09-11 확인) |

---

## 3. Klaviyo

| 항목 | 내용 |
|---|---|
| **무엇을 파는가** | 이메일/SMS 마케팅 자동화 + CDP. 예측 CLV·이탈 위험 점수(Predictive Analytics)를 수만 개 커머스 고객사의 집계 데이터로 사전학습한 모델로 제공. |
| **가격 공개 여부** | **공개.** 무료 플랜(활성 프로필 250개·월 500건 발송)부터 시작해 활성 프로필 수 기준 계단식 과금: 500명 $20/월 · 1,000명 $30/월 · 10,000명 $150/월 · 50,000명 $720/월 · 250,000명 약 $2,300/월. 예측 분석 기능은 모든 유료 티어에 동일하게 포함된다. 25만 프로필 초과 시 별도 영업 협의. |
| **ROI를 어떻게 증명하는가** | 예측 CLV·이탈 위험 점수 자체를 제공하는 데 그친다. **공개 문서에서 대조군 기반 증분 매출/이익 검증 방법론을 확인하지 못했다.** |
| **한계** | 예측 정확도나 증분 이익 검증 방법론이 공개 자료에서 확인되지 않는다 — **확인 불가**로 처리하되, 확인되지 않았다는 사실 자체가 "이 부분을 제품 핵심으로 내세우지 않는다"는 정황 증거다. |
| **출처** | [TinyCommand: Klaviyo Pricing 2026](https://tinycommand.com/blogs/klaviyo-pricing-explained)(2026-09-11 확인) · [Contra Collective: Klaviyo vs Braze 2026](https://contracollective.com/blog/klaviyo-vs-braze-ecommerce-email-marketing-automation-2026)(2026-09-11 확인) |

---

## 4. Bloomreach (Engagement)

| 항목 | 내용 |
|---|---|
| **무엇을 파는가** | 커머스 특화 CDP + 마케팅 오케스트레이션. 구매·탐색 행동 기반 이탈 예측을 제공하며 고객군을 분리해 대응 강도를 다르게 건다. |
| **가격 공개 여부** | **부분 공개.** 정식 가격표는 없으나 Shopify 앱스토어 기준 진입가 연 $19,020, 엔터프라이즈 전체 배포는 연 $96,000~$180,000, 제3자 집계 기준 중앙값 계약 규모 약 연 $232,500로 보고된다. 모듈비 + 사용량(Billable Profile·MUV) 과금 구조. |
| **ROI를 어떻게 증명하는가** | 이탈 예측으로 고객군을 분리하고 대응 강도를 차등화하는 **세그멘테이션 도구**로 제시된다. **공개 문서에서 Rule-based 대비 증분 이익을 계량화하는 방법론을 확인하지 못했다.** |
| **한계** | 위 Klaviyo와 동일하게, 예측을 활용한 액션까지는 제공하나 **그 액션이 낸 순이익을 대조군 기반으로 증명하는 절차는 공개 자료 수준에서 확인 불가.** |
| **출처** | [Bloomreach Prediction Use Cases](https://documentation.bloomreach.com/engagement/docs/predictions-use-cases)(2026-09-11 확인) · [Costbench: Bloomreach Pricing 2026](https://costbench.com/software/customer-data-platform/bloomreach/)(2026-09-11 확인) |

---

## 5. Amplitude

| 항목 | 내용 |
|---|---|
| **무엇을 파는가** | **리텐션/이탈방지 전용 도구가 아니라 제품 분석(Product Analytics) 플랫폼이다.** `Predictive Cohorts`(Amplitude Engage 애드온)가 이탈·전환 가능성 기반으로 동적 코호트를 만들어 캠페인 도구(Braze·Iterable 등)로 내보낸다. |
| **가격 공개 여부** | 이번 조사에서 확인 불가 — 조사 범위를 Braze/Klaviyo/Bloomreach/Optimove 대비로 좁혔다. |
| **ROI를 어떻게 증명하는가** | Predictive Cohorts는 "누가 이탈/전환할 것인가"를 예측해 코호트로 묶어주는 데까지가 제품의 범위다. **자체적으로 증분 이익이나 Rule-based 대비 비교를 계산하지 않는다** — 그 코호트를 받아 실제 캠페인을 돌리는 것은 Braze 등 별도 도구의 역할이다. |
| **한계** | Amplitude는 애초에 "리텐션 전략의 손익을 증명하는 도구"로 설계되지 않았다. 경쟁사라기보다는 **우리 프로젝트가 참조할 예측 코호트 UX 패턴** 정도로 취급하는 것이 정확하다. |
| **출처** | [Amplitude: Predictive Cohorts](https://amplitude.com/docs/data/audiences/predictions-use)(2026-09-11 확인) |

---

## 제외 — Retention Science

**Endurance International Group(현 Newfold Digital)에 2020년 인수된 이후, 2026년 기준 독립 제품으로서의 활동을 이번 조사에서 확인하지 못했다.** 최신 공식 문서·사례·가격 정보가 검색되지 않는다. **확인 불가 — 사실상 비활성 또는 모기업 제품군에 흡수된 것으로 추정되나, 이를 확정할 자료는 찾지 못했다.** 이런 이유로 경쟁 지형 본표에서 제외하고 이 사실 자체를 보고한다.

출처: [Retention Science acquisition 2020](https://www.globenewswire.com/news-release/2020/07/30/2070228/28669/en/Endurance-International-Group-Reports-2020-Second-Quarter-Results-and-Announces-the-Acquisition-of-Retention-Science.html)(2026-09-11 확인)

---

## 핵심 질문에 대한 답: "예측 정확도가 아니라 Incremental Profit을 파는 제품이 존재하는가?"

**결론: 완전한 형태로는 존재하지 않는다. 가장 근접한 것은 Optimove의 캠페인 단위 대조군 기반 "Increase in" 지표이나, 이것도 우리가 만들려는 것과 3가지 지점에서 다르다.**

| 비교 축 | Optimove (가장 근접한 사례) | 이 프로젝트(AI_ROI) |
|---|---|---|
| 비교 단위 | 개별 캠페인 대 그 캠페인의 대조군 | **전략(정책) 전체** — Full AI 전략 대 Rule-based Baseline 전략, 동일 환경·동일 홀드아웃 |
| 측정값 | 매출/반응 증분으로 보이며, 처치 비용을 뺀 순이익 여부는 공개 자료로 확인 불가 | **기여이익(Contribution Margin) 기준 Incremental Profit** — 처치 비용을 명시적으로 차감 |
| 검증 가능성 | 계산 방법론 비공개(블랙박스), 사례 연구는 벤더의 마케팅 자료 | 시드·커밋 고정 시 **재현 가능**(SRS FREEZE-003), 방법론이 코드로 공개됨 |

이 세 가지 차이 — **정책 수준 비교 · 기여이익 기준 순이익 · 재현 가능성** — 가 실제로 시장에 없는 조합이라는 것이 이번 조사의 결론이다. Braze는 정확도(0~100 Prediction Quality)를 팔고, Klaviyo·Bloomreach는 예측 점수 자체를 팔며, Optimove만 인과추론에 가까운 개념(대조군)을 쓰지만 그 범위가 캠페인 단위에 머문다. **"AUC가 아니라 원화(₩) 단위 Incremental Profit을 판다"는 명제는 조사된 5개 도구 중 완전히 일치하는 선례가 없다.**

**단, 이것이 시장에 수요가 있다는 뜻은 아니라는 점을 명시한다.** 상용 도구들이 이 비교를 하지 않는 이유가 "기술적으로 불가능해서"인지 "고객이 원하지 않아서"인지는 이번 조사로 판정할 수 없다 — **확인 불가.**
