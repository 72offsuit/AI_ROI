# 설계 문서 vs 실제 구현 — 불일치 전수 기록

**작성** Timothy (Role 11 · W6 문서) · 2026-09-14
**대상 브랜치** `feat/measurement-layer-and-dashboard` (PR #57, 미병합)
**방법** 설계 문서(W2~W5 산출물: `03-service-planning/`·`04-architecture/`·`07-design/`·`03-story-engineering/`)의 각 주장을 실제 소스코드(`src/measurement/`·`dashboard/`)와 대조했다. **읽어서 판단하지 않았다** — 코드를 열어 값을 세거나 계산했다.

> 이 문서는 `.agent-team/09-docs/` 소유(W6 Timothy)다. 기록된 gap을 해소하려면 **원본 문서**(`03-service-planning/`·`04-architecture/`)를 고쳐야 하는데, 그 문서들은 각각 W2 산출물로 다른 역할 소유이고 이 팀의 이번 작업 범위(`09-docs/**`) 밖이다. 여기서는 **기록 + 수정 권고**까지만 한다.

> ### ⚠ 병합 경위 (2026-09-14, 리드 판정으로 원인 확정)
> 이 문서를 포함한 `09-docs/**` 산출물은 Timothy가 병행 조사를 위해 스폰한 **fork 3개가 각자 `.agent-team/09-docs/`에 직접 써서 서로 덮어쓴** 결과물이다(E-PATH-COLLISION). 애초 가설(별도 원격 세션이 동시에 같은 경로에 썼을 가능성)은 **리드가 확인해 기각했다** — 이 사이클의 W6 역할은 Thomas·Timothy·Matthias 셋뿐이고 Role 11(문서)은 Timothy 하나다. `09-docs/`는 git 미추적이라 덮어쓰인 이전 내용은 복구 불가능했다.
>
> **조치:** 리드 판정에 따라 `09-docs/`의 쓰기 주체를 Timothy 단독으로 확정하고, 남은 fork들에게 이후로는 파일을 쓰지 말고 내용을 반환하도록 지시했다. 디스크에 남은 버전(초기 §1~§11)을 기반으로, fork가 반환한 내용과 리드의 직접 실행 검증을 Timothy가 대조·재검증해 **§1(원인 C 추가)·§6(5종→8종으로 범위 재검증)·§11(PR 시각 보강)을 수정하고 §16~§19를 신규 추가**했다. §12~§15는 병합 시점에 먼저 추가돼 있던 내용을 그대로 유지·재확인했다. 같은 사고로 중복 생성됐던 `glossary.md`(`dev-definitions.md`와 내용 중복)는 유의미한 부분(시각 상태 9종 표·용어 쌍 비교표)을 `dev-definitions.md`에 병합한 뒤 삭제했다. **이 문서의 모든 수치는 최종적으로 Timothy가 직접 재실행해 확인한 값이다** — 어느 fork가 먼저 썼는지와 무관하게, 여기 남은 숫자는 검증된 것이다.

---

## 요약

| # | 항목 | 심각도 | 상태 |
|---|---|---|---|
| [1](#1-kpi-지표-개수--47-vs-26-vs-46) | KPI 지표 개수 — 47 vs 26 vs 46 | 중 | 리드 사전 지적, 검증 완료 + 원인 세분화 |
| [2](#2-ai-투자비용-산술-오류) | AI 투자비용 산술 오류 (2,020,000 vs 2,170,000) | 낮 | 리드 사전 지적, 검증 완료(코드가 옳다) |
| [3](#3-dashboard-architecturemd-3-예시-코드-경로-이중-접두사) | `dashboard-architecture.md` §3 예시 코드 버그 | 낮 | 리드 사전 지적, 검증 완료(구현에서 수정됨) |
| [4](#4-d-01-ac-6-문언--모든-정상-unconfirmed를-던진다) | `d-01` AC-6 문언 — 모든 정상 `unconfirmed`를 던진다 | 중 | 리드 사전 지적, 검증 완료(구현이 의도적으로 이탈) |
| [5](#5-cohort_retention_rate-분류-불일치) | `cohort_retention_rate` 분류 불일치 (✅ 계산가능 vs 실제 `unavailable`) | 중 | ★ 신규 발견 (단, `measurement_contract.md` §6.4가 이미 인지) |
| [6](#6-metric_specs-카탈로그-46종-중-게시물에-절대-도달하지-않는-것--8종-양방향-불일치) | `METRIC_SPECS` 카탈로그 46종 중 게시물에 도달 못 하는 것 — **8종**(layer3 ML 5 + layer0 미호출/미구현 3), 역방향 1종도 존재 | 중 | ★ 신규 발견, 리드가 5→8종으로 범위 확장·재검증 |
| [7](#7-kpi-definition-v1md-7-secondary-9종-vs-실제-역할-배정-5종) | `kpi-definition-v1.md` §7 Secondary 9종 vs 실제 역할 배정 5종 | 중 | ★ 신규 발견 |
| [8](#8-reasoncode-7종-vs-9종) | `ReasonCode` 7종(기획) vs 9종(계약·구현) | 낮 | ★ 신규 발견 (계약 문서가 이미 "정본은 계약" 선언) |
| [9](#9-agentsmd-프로젝트-현황-문단이-실측과-어긋난다) | `AGENTS.md` "프로젝트 현황" 문단이 실측과 어긋난다 | 중 | 리드 사전 지적(`wave-log.md`), 미수정 상태 확인 |
| [10](#10-data_spechtml-174-의-results-접근-주체-목록-공백) | `data_spec.html` §17.4의 `results/` 접근 주체 목록 공백 | 낮 | 문서 자체가 이미 인지(`measurement_contract.md` §7.5) — 참고 기록 |
| [11](#11-issue-43-44-가-merge-이후에도-open) | 이슈 `#43`·`#44`가 머지 이후에도 OPEN | 낮 | 프로세스 항목 (문서 불일치 아님, 참고 기록) |
| [12](#12-계약-스키마-자체의-description에-47종-인용이-남아-있음) | 계약 스키마 `kpi_report.schema.json`의 `description`에 "47종" 인용이 남아 있음 | 낮 | ★ 신규 발견 — §1 오류가 기계가독 계약 문서화 텍스트까지 전파됨 |
| [13](#13-data_spechtml-72--메타-4필드-nullable--n-표기가-낡음) | `docs/data_spec.html` §7.2 — 메타 4필드 `Nullable = N` 표기가 낡음 | 낮 | 이미 두 설계 문서(`data-model-erd.md`·`measurement_contract.md`)가 독립적으로 지적 — 참고 재확인 |
| [14](#14-story-m-01-t3-문언-vs-기준선-테스트--운영적으로-해결-문서-미정정) | `story-m-01` T3 문언 vs 기준선 테스트 충돌 — 코드는 동작하나 스토리 문서 미정정 | 낮 | ★ 신규 발견, **리드 판정 D-25로 해소**(승인 불필요 확정, 기준선 단언 무변경 실행 확인) — 문서 정정만 남음 |
| [15](#15-토큰-전략-규약-예외가-원-규약-문서에-반영되지-않음) | 토큰 전략 규약("스크립트 한 줄도 안 고친다")의 예외가 원 규약 문서(`token-strategy.md`)에 반영 안 됨 | 낮 | ★ 신규 발견 |
| [16](#16-dashboardagentsmd의-value_formatted-서술이-낡았다) | `dashboard/AGENTS.md`의 `value_formatted` 서술이 낡음 — "계약에 없다"고 적었으나 이미 존재 | 중 | ★ 신규 발견 — 0채우기 금지 경고문이 자기 낡은 전제로 반대 결과를 유도할 위험 |
| [17](#17-gate-1-lock-cli가-설계-문서대로-구현되지-않았다) | GATE 1 Lock CLI(`freeze record --by`)가 설계대로 구현되지 않음 — 실제는 인라인 Python 호출 | 낮 | ★ 신규 발견 — 설계 문서 스스로 "아직 없다"고 인지했던 상태가 구현 후에도 유지 |
| [18](#18-gate1-freeze-proceduremd-6의-lock-상태-예측이-실제-결과와-다르다) | `gate1-freeze-procedure.md` §6 Lock 상태 예측("PARTIAL 최대 4") vs 실측("PARTIAL 2") | 낮 | ★ 신규 발견 — 예측이 빗나갔고 갱신 안 됨(모순은 아님) |
| [19](#19-uspmd-d-6-권고가-실제-리드-결정과-다르다-이미-다른-문서에는-정확히-반영됨--참고용) | `usp.md` D-6 권고("Timothy 소유")가 실제 리드 결정("Andrew 소유")과 다름 | 낮 | ★ 신규 발견, 실무 영향 없음(다른 문서는 이미 정확) — 참고용 |

---

## 1. KPI 지표 개수 — 47 vs 26 vs 46

**주장 위치** `.agent-team/03-service-planning/kpi-definition-v1.md`
**실제** `src/measurement/kpi.py:1126` `METRIC_SPECS`

### 1.1 세 숫자 검증

| 숫자 | 근거 | 실측 |
|---|---|---|
| §8 총계 "47종" | §8 표: 계층0(12)+계층1(8)+계층2(12)+실험판정(15) | 문서 원문 그대로. 자체 합산은 맞다(12+8+12+15=47) |
| §5가 이름 붙인 것 "26종" | §5.1(6행: `revenue`·`coupon_cost`·`message_cost`·`campaign_fixed_cost`·`shipping_subsidy`·`marketing_cost`) + §5.2(2행: `cogs`·`contribution_profit`) + §5.3(표 6행에 담긴 이름 18개: `incremental_revenue`·`incremental_contribution_profit`·`roi`·`ai_roi`·`ai_net_incremental_value`·`qini_coefficient`·`auuc`·`uplift_by_decile`·`persuadables_ratio`·`churn_test_auc`·`precision`·`recall`·`f1`·`predicted_clv`·`clv_mape`·`top20_precision`·`pehe`·`corr(τ̂,τ)`) | **직접 세어 확인: 6+2+18=26.** 정확히 일치한다 |
| 실제 구현 | `python3 -c "from src.measurement import kpi; print(len(kpi.METRIC_SPECS))"` | **46** |

### 1.2 원인 — 두 가지가 독립적으로 섞여 있다

**(A) 계층별 총수는 대부분 일치하지만 계층3만 1개 어긋난다.**

| 계층 | 문서(§8) | 코드(`METRIC_SPECS`) |
|---|---|---|
| 0 (수집 건전성) | 12 | 12 ✅ |
| 1 (Customer KPI) | 8 | 8 ✅ |
| 2 (Business KPI) | 12 | 12 ✅ |
| 3 (실험 판정 지표) | **15** | **14** ← 47→46 차이의 원천 |

문서 §5.3 표는 계층3 후보 이름을 18개 나열하지만, 그중 4개(`incremental_revenue`·`incremental_contribution_profit`·`roi`·`ai_roi`)는 실제로 계층2(Business KPI) 소속으로 구현됐다(§5.1~5.2가 이미 이 흐름을 서술 — "두 전략이 필요한 것"이 §5의 하위 절이므로). 나머지 14개가 코드의 계층3(전부 `unavailable`)과 대응하는데, 문서 §8은 이 실질 14개를 "15"로 잘못 합산했다.

**(B) 계층1 내부 분류가 코드와 반대다(§5 참조).** `cohort_retention_rate`가 문서에서는 계산가능(✅)이지만 코드는 `unavailable`이다. 이 재분류는 계층1 총수(8)를 바꾸지 않지만, §8의 "계산가능 22 / 조건부 6 / 불가 19" 세부 합계를 어긋나게 한다 — 실제 세부 합계는 **계산가능 21 / 조건부 6 / 불가 19**다(코드 직접 실행: `Counter({'computable': 21, 'unavailable': 19, 'conditional': 6})`, 합계 46). 공교롭게도 계층3의 "-1"과 "불가" 열에서 상쇄되어 "불가 19"는 문서와 코드가 우연히 일치한다 — **계산가능 열(22 vs 21)만 실제로 어긋난다.**

**(C) 코드 자신의 docstring도 47을 주장하며, CI가 이 모순을 잡지 못한다.** `kpi.py:1213-1221`의 `metric_classification()` 함수는 doctest 형태의 예시를 갖고 있다:
```python
def metric_classification() -> dict[str, object]:
    """47종의 계층별·가용성별 분포. **개수를 리터럴로 적지 않고 집계한다.**
    ...
        >>> metric_classification()["total"]
        47
    """
```
실제로 실행하면 `47`이 아니라 `46`이 나온다(위 §1.1 실측). 이 저장소의 `tests/`·`.github/workflows/` 어디에도 `doctest` 실행기가 없다(`grep -rn "doctest" tests/ .github/workflows/` → 매치 0건) — **이 doctest는 한 번도 실행되지 않았고, 407건의 테스트가 전부 통과해도 이 모순은 CI에서 드러나지 않는다.** 함수 본문이 스스로 "개수를 리터럴로 적지 않고 집계한다"고 설명한 바로 그 함수의 docstring 예시에 리터럴 오답이 남아 있다는 점이 역설적이다.

**저장소 전체의 doctest 실행 가능성을 리드가 전수 확인했다**(2026-09-14): `contracts.py` 6개 · `economics.py` 4개 · `kpi.py` 1개 · `publish.py` 4개 · `schema.py` 1개 · `sink.py` 2개 = **예제 18개, 실패 1개**(바로 이 `kpi.py:1219` 건), **CI가 실행하는 것 0개.** 나머지 17개는 전부 통과한다 — 즉 **실행기만 있었으면 이 오류는 GATE 1 Lock(§7) 이전에 CI에서 잡혔을 것이다.**

> **"47종" 오류가 전파된 자리는 이제 셋으로 확정된다** — 사람이 읽는 기획 문서(`kpi-definition-v1.md` §8, 이 절)뿐 아니라 **기계가독 계약**([§12](#12-계약-스키마-자체의-description에-47종-인용이-남아-있음), `kpi_report.schema.json:5`)과 **실행 가능한 형태였던 코드 자신의 예제**(이 절, `kpi.py:1219`) 양쪽에도 같은 숫자가 새어 나갔다. 세 번째가 특히 의미가 크다 — 나머지 둘은 "읽고 옮겨적다 틀렸다"이지만, 이것은 **"검증 가능한 형태로 이미 존재했는데 아무도 실행하지 않아 놓쳤다"**는, 이 gap 문서 전체가 경계하는 실패 양식(`AGENTS.md` "미실행 검증을 통과로 표시하지 않는다")과 정확히 같은 자리다. 코드 결함(doctest 값 자체를 고치는 것)은 Thomas(코드 리뷰)에게 별도로 넘겨졌다 — 이 문서는 문서 일관성 관점의 기록까지만 한다.

### 1.3 권고

`kpi-definition-v1.md`를 갱신할 때:
1. §8 총계 행을 `12+8+12+14=46`으로, 계산가능 열을 `22`→`21`로 정정한다.
2. §5.3의 18개 이름 중 4개(`incremental_revenue`·`incremental_contribution_profit`·`roi`·`ai_roi`)가 계층2 소속이고 계층3(실험 판정)은 나머지 14개뿐임을 명시한다.
3. cohort_retention_rate 재분류는 [§5](#5-cohort_retention_rate-분류-불일치) 참조.
4. `kpi.py:1219-1220`의 doctest 리터럴 `47`을 `46`으로 정정한다 — 이 수정은 `src/measurement/kpi.py`(Phillip 소유) 코드 자체이므로 이 문서는 사실만 남기고 직접 수정하지 않았다. **리드가 이 항목을 이미 코드 결함으로 Thomas(코드 리뷰)에게 별도로 전달했다** — 이 문서와 중복 수정하지 않는다.
5. 장기적으로는 `tests/`에 `doctest.testmod()`(또는 `pytest --doctest-modules`)를 추가해, 실행 가능한 형태로 존재하는 예제가 실제로 CI를 거치게 한다 — 이번 건과 같은 "실행기 부재로 놓친 1/18" 패턴의 재발을 막는다.

---

## 2. AI 투자비용 산술 오류

**주장 위치** `.agent-team/03-service-planning/economic-rule-v1.md` §5
**실제** `src/measurement/config_loader.py:97-114` `AiInvestmentConfig.monthly_amortized_krw()` + `src/measurement/economics.py:630` `ai_investment_cost()`

### 2.1 검증

문서가 적은 식과 결과:

```
식     (12,600,000 / 12 + 500,000) × (42/30)
결과   ≈ 2,020,000원
```

**직접 계산:**

```python
>>> (12_600_000 / 12 + 500_000) * (42 / 30)
2170000.0
```

**코드 구현** — `config_loader.py:109-114`:
```python
upfront = self.model_development_cost_krw + self.compute_cost_krw          # 12,000,000 + 600,000 = 12,600,000
recurring = self.model_operating_cost_krw_per_month + self.monitoring_cost_krw_per_month  # 300,000 + 200,000 = 500,000
return upfront / self.amortization_months + recurring                       # 1,050,000 + 500,000 = 1,550,000
```
`ai_investment_cost()`가 이 월 상각액에 `(campaign_days/30)=1.4`를 곱한다 → **1,550,000 × 1.4 = 2,170,000**.

**테스트 단언** `tests/test_economics.py:344`:
```python
self.assertAlmostEqual(2170000.0, float(result.value), delta=1.0)
```

### 2.2 판정

**식과 코드가 정확히 일치한다. 문서의 "≈2,020,000원"이 산술 오류다.** `2,020,000원`을 만드는 다른 자연스러운 식(예: 개발비 1,200만원만 상각에 넣고 컴퓨트 비용을 빼거나, 운영·모니터링 비용을 다른 비율로 섞는 조합)을 여러 방식으로 시도했으나 **깔끔하게 재현되는 대안 식을 찾지 못했다** — `backend.md` §5.1의 기록과 일치한다("2,020,000을 내는 식을 역산할 수 없었다").

### 2.3 권고

`economic-rule-v1.md` §5의 "**캠페인 1회(42일) 귀속 AI Cost** | **≈ 2,020,000원**" 행을 **`2,170,000원`**으로 정정한다. 영향은 제한적이다 — `ai_investment_cost()`는 항상 `status: unconfirmed`(가정 기반 추정치)로 나가고, `ai_roi`는 C1에서 `NEEDS_TWO_STRATEGIES`로 항상 계산 불가이므로 이 값이 다른 계산에 전파되지 않는다.

---

## 3. `dashboard-architecture.md` §3 예시 코드 경로 이중 접두사

**주장 위치** `.agent-team/04-architecture/dashboard-architecture.md` §3
**실제** `dashboard/src/lib/artifacts/paths.ts:97-124` `resolveArtifactPath()`

### 3.1 검증

문서의 예시 코드(현재도 그대로 남아 있다, 2026-09-14 확인):

```ts
// lib/artifacts/paths.ts — 허용 경로 화이트리스트
const RESULTS_DIR = process.env.AIROI_RESULTS_DIR ?? resolve(process.cwd(), "../results");
export function resolveArtifactPath(relative: string): string {
  const target = resolve(RESULTS_DIR, relative);   // ← relative 가 "results/kpi_report.json" 이면
  ...                                                //    RESULTS_DIR/results/kpi_report.json 이 된다 (이중 접두사)
```

`index.json`의 `artifacts[].path`는 저장소 루트 기준(`^(results|data/processed)/`로 시작)이다. `RESULTS_DIR`은 이미 `results/`를 가리키므로, `resolve(RESULTS_DIR, "results/kpi_report.json")`을 그대로 실행하면 `<RESULTS_DIR>/results/kpi_report.json`이 되어 경로가 어긋난다.

**실제 구현**(`dashboard/src/lib/artifacts/paths.ts:97-124`)은 `results/` 접두사를 **떼어낸 뒤** `RESULTS_DIR` 아래로 해석한다:
```ts
export function resolveArtifactPath(relative: string): string {
  if (isAbsolute(relative)) { throw new IsolationError(...); }
  if (relative.startsWith("data/processed/")) { throw new IsolationError(...); }
  if (!relative.startsWith(RESULTS_PREFIX)) { throw new IsolationError(...); }
  // (이하 RESULTS_PREFIX 를 제거하고 RESULTS_DIR 기준으로 resolve)
```
파일 머리 주석에 이 버그를 명시적으로 경고하는 문장이 있다: *"Do not re-derive this from whatever the publisher happens to emit... The schema did not pin it, but ADR-0002 did, and the publish run was simply wrong."*

### 3.2 판정

**리드 사전 지적(`wave-log.md` W6 인계, Andrew `frontend.md` §10)이 정확하다.** 구현은 이미 올바르게 고쳐졌지만, **설계 문서의 예시 코드는 여전히 버그가 있는 버전 그대로다.**

### 3.3 권고

`dashboard-architecture.md` §3의 예시 코드를 `paths.ts:97-124`의 실제 구현(접두사 제거 후 resolve)으로 교체한다. 이 문서를 계속 예시로 참고할 이후 사이클 개발자(결과 화면군 구현 시)가 같은 버그를 재현할 위험이 있다.

---

## 4. `d-01` AC-6 문언 — 모든 정상 `unconfirmed`를 던진다

**주장 위치** `.agent-team/03-story-engineering/story-d-01-dashboard-foundation-kr.md` AC-6 (및 같은 문언이 `dashboard-architecture.md` §3.2에도 있다)
**실제** `dashboard/src/lib/artifacts/read.ts` `assertMetricValueInvariants()` (Andrew `frontend.md` §5.2 기록)

### 4.1 검증

문언 원문(AC-6):
> `status !== "ok"` 인데 `value !== null` 이면 던진다

`common.schema.json`의 `metric_value` 스키마는 `status: "unconfirmed"`일 때 `value`·`basis`·`params_used`를 **필수**로 요구한다(`allOf[1]`). 즉 정상적인 `unconfirmed` 레코드는 **항상 `value !== null`**이다.

문언을 문자 그대로 구현하면: `status="unconfirmed"` (≠ "ok") 이고 `value=0.183` (≠ null) → **모든 정상 `unconfirmed` 지표가 예외를 던진다.** 실제 C1 데이터에서 `churn_rate`(`unconfirmed`, 18.3%)가 이 경로에 걸리는 실제 사례다.

**실제 구현**은 조건을 "계산 불가 3종"(`unavailable`·`blocked`·`not_run`)으로 좁혔다 — `status !== "ok"`가 아니라 `status ∈ {unavailable, blocked, not_run}`일 때만 `value !== null`을 예외로 취급한다.

### 4.2 판정

**리드 사전 지적이 정확하다.** Andrew의 기록(`frontend.md` §5.2)이 이 이탈을 이미 자체적으로 문서화했다: *"이것은 W3이 놓친 자리다(리드 확인). 스토리 문언이 스키마와 어긋났고, D2b 값 실재 검사는 인용한 키가 계약에 있는지를 보지 조건식이 계약과 모순되는지는 보지 않는다."*

### 4.3 권고

`story-d-01-dashboard-foundation-kr.md` AC-6과 `dashboard-architecture.md` §3.2의 동일 문언을 다음으로 정정한다:
> `status ∈ {"unavailable", "blocked", "not_run"}` 인데 `value !== null` 이면 던진다.

Andrew의 지적대로 **"같은 종류의 결함이 더 있을 수 있다"** — 스토리 문서의 조건식이 계약 스키마와 논리적으로 모순되는지 확인하는 절차(단순 "인용 키 존재 확인"을 넘어)가 향후 스토리 리뷰(W3)에 추가돼야 한다.

---

## 5. `cohort_retention_rate` 분류 불일치

**주장 위치** `.agent-team/03-service-planning/kpi-definition-v1.md` §4 표(`cohort_retention_rate[m]` 행, "C1" 열 `✅`) 및 §8 총계 표
**실제** `src/measurement/kpi.py` `METRIC_SPECS`(`kpi.py:1126` 부근): `MetricSpec("cohort_retention_rate", 1, "customer", "unavailable")`

### 5.1 검증

`kpi-definition-v1.md` §4:
```
| `cohort_retention_rate[m]` | 가입 코호트 m개월차에 구매 ≥1건인 고객 / 해당 코호트 전체 | 가입월 코호트 | M1/M3/M6/M12 | 코호트 인원 | ✅ |
```

실제 코드는 이 지표를 `unavailable`로 분류한다. 원인은 `docs/measurement_contract.md` §6.4가 이미 상세히 서술한다 — `customers` 테이블(`signup_date` 보유)이 미구현이라 `P_all(D)`(가입 기준 모집단)가 성립하지 않아 코호트 지표가 `PRECONDITION_MISSING`으로 게시된다.

### 5.2 판정

**신규 발견이지만, 근본 원인은 이미 `docs/measurement_contract.md` §6.4에 명시적으로 인지·기록되어 있다:**
> *"다만 kpi-definition-v1.md §8 이 이 지표를 ✅(계산 가능)로 적은 것은 틀렸다 — 그 문서가 갱신되어야 한다 (W6 항목)."*

이 gap 문서는 그 W6 항목을 실행한 것이다. 이 항목이 [§1(KPI 개수)](#1-kpi-지표-개수--47-vs-26-vs-46)의 "계산가능 22 vs 21" 세부 불일치의 원인이기도 하다.

### 5.3 권고

`kpi-definition-v1.md` §4의 `cohort_retention_rate[m]` 행의 C1 열을 `✅`→`⚠️ PRECONDITION_MISSING`(customers 테이블 부재)으로 정정하고, §8 총계 표의 계층1 "계산가능" 수를 5→4, "불가" 수를 0→1로 정정한다(총 46종 유지, [§1](#1-kpi-지표-개수--47-vs-26-vs-46) 정정과 함께 처리하면 §8 표 전체가 한 번에 맞아떨어진다).

---

## 6. `METRIC_SPECS` 카탈로그 46종 중 게시물에 절대 도달하지 않는 것 — 8종 (양방향 불일치)

**주장 위치** (암묵적) — `kpi-definition-v1.md` §5.3·§7·§8이 "46(47)종 지표 카탈로그"를 게시 대상과 1:1로 서술
**실제** `src/measurement/kpi.py:1126` `METRIC_SPECS`(46종) vs 실제로 `results/measurement/*.json`에 값으로 도달하는 경로(함수 호출 여부까지 추적)

> **검증 방법론 — 1차 시도의 오탐을 기록해 둔다.** 문자열 리터럴 grep(`grep "missing_field_count\|event_type_count\|..." publish.py`)만으로는 오탐이 난다 — `event_type_count`·`field_fill_rate`는 **문자열로는 안 걸리지만 실제로 함수 호출**(`kpi.event_type_count(...)`·`kpi.field_fill_rate(manifest)`)로 게시되고 있어 유령이 아니다. **"함수가 실제로 호출되는 경로까지" 확인해야 정확하다.** 아래는 그 기준으로 재검증한 결과다.

### 6.1 검증 (A) — layer 3(실험 판정) 중 5종은 카탈로그에만 있고 게시 화면에 전혀 나타나지 않는다

`METRIC_SPECS`의 layer=3(14종) vs `publish.py:927` `_EXPERIMENT_METRICS`(kpi_report에 실제 게시되는 `layer:"experiment"` 행, 14종)를 직접 비교했다(개수는 우연히 같다):

| `METRIC_SPECS` layer=3 (46종 집계·`summary.total`에 반영) | `publish._EXPERIMENT_METRICS` (실제 kpi_report.metrics[]의 `layer:"experiment"` 행) |
|---|---|
| `ai_net_incremental_value` · `qini_coefficient` · `auuc` · `uplift_by_decile` · `persuadables_ratio` · `churn_test_auc` · `precision` · `recall` · `f1` · `predicted_clv` · `clv_mape` · `top20_precision` · `pehe` · `corr_tau_hat_tau` | `incremental_contribution_profit` · `qini_coefficient` · `incremental_revenue` · `roi` · `ai_roi` · `ai_net_incremental_value` · `churn_test_auc` · `sleeping_dog_targeting_rate` · `auuc` · `uplift_by_decile` · `persuadables_ratio` · `predicted_clv` · `clv_mape` · `top20_precision` |

**공통 9종:** `ai_net_incremental_value`·`qini_coefficient`·`auuc`·`uplift_by_decile`·`persuadables_ratio`·`churn_test_auc`·`predicted_clv`·`clv_mape`·`top20_precision` — 이 9종은 `NEEDS_MODEL_OUTPUT` 사유로 **"계산 불가"라는 값으로 게시된다**(카탈로그에도 있고 화면에도 있다).

**`METRIC_SPECS`에만 있음(5종, ML 계열) — 카탈로그 46종에는 잡히지만 게시 화면에는 절대 나타나지 않는다:** `precision`·`recall`·`f1`·`pehe`·`corr_tau_hat_tau`

**`_EXPERIMENT_METRICS`에만 있음(5종) — 화면에는 나타나지만 카탈로그 46종 어디에도 없다:** `incremental_contribution_profit`·`incremental_revenue`·`roi`·`ai_roi`(이 4종은 `METRIC_SPECS`에 **계층2** 항목으로 별도 존재 — 같은 이름이 계층2 `by_source` 값과 계층3 단일 값 양쪽으로 이중 게시된다는 뜻), `sleeping_dog_targeting_rate`(카탈로그 46종 어디에도 없다)

**같은 "ML 산출물 필요" 범주인데 취급이 갈린다 — 그 선을 가르는 원칙이 문서에 없다:** `auuc`·`qini_coefficient`·`uplift_by_decile`·`top20_precision`·`persuadables_ratio`·`predicted_clv`·`clv_mape`·`churn_test_auc`·`sleeping_dog_targeting_rate`(9종)는 `NEEDS_MODEL_OUTPUT`으로 **표시되는데**, 같은 계열인 `precision`·`recall`·`f1`·`pehe`·`corr_tau_hat_tau`(5종)는 **카탈로그에만 있고 어떤 화면 행으로도 나타나지 않는다.** 왜 후자 5종만 게시 목록에서 빠졌는지 설명하는 문서·주석이 없다.

### 6.2 검증 (B) — layer 0(수집 건전성) 중 3종이 구현·게시 어느 쪽에도 완전히 도달하지 않는다 — (A)보다 더 무겁다

| 지표 | `kpi.py` 구현 | `publish.py` 호출 | 계약 스키마(`docs/contracts/.../*.schema.json`) |
|---|---|---|---|
| `missing_field_count` | **있음**(`kpi.py:343`, 함수 정의됨) | **호출 0회**(`grep -n "missing_field_count" src/measurement/publish.py` → 매치 없음) | **0개 파일에 등장** |
| `source_event_count` | **있음**(`kpi.py:378`, 함수 정의됨) | **호출 0회**(동일 grep, 매치 없음) | **0개 파일에 등장** |
| `rejection_reason_count` | **없음** — `METRIC_SPECS`에 `MetricSpec("rejection_reason_count", 0, "collection", "computable")`(`kpi.py:1131`)로 **"계산 가능"을 선언만 하고, 그 이름의 함수 자체가 `kpi.py`에 없다**(`grep -n "^def rejection_reason_count" src/measurement/kpi.py` → 매치 없음) | — | **0개 파일에 등장** |

layer 0은 "Sink만으로 오늘 계산되는 계층"(§2.1 이하)인데, `rejection_reason_count`는 **구현조차 없이 "computable"로 카탈로그에 선언**돼 있다. `missing_field_count`·`source_event_count`는 함수는 있지만 `publish.py`의 어떤 산출물 조립 코드도 그 함수를 호출하지 않아, 있으나 마나다.

### 6.3 판정

**유령 카탈로그 항목은 5종이 아니라 8종이다**(layer 3의 5종 + layer 0의 3종). 그리고 반대 방향도 있다 — `sleeping_dog_targeting_rate`는 게시되는데 카탈로그 46종에 없다. **따라서 `METRIC_SPECS`는 "게시되는 지표의 정본 목록"으로 읽을 수 없다 — 양방향으로 어긋나 있다.**

이것은 설계 문서 자체의 오류라기보다 **구현 내부에서 "지표 분류 카탈로그"(집계·문서화용)와 "실제 게시 대상 목록"(화면용)이 별도로 손으로 유지되면서 갈라진 사례**다. 실사용에 즉각적인 문제는 없다(계약 검증은 통과한다 — 카탈로그가 계약이 아니므로) — 다만 `kpi_report.summary.total`(카탈로그 기반 집계, 46)과 실제 화면에 그려지는 지표 행 수가 다를 수 있어, **다음 사이클에서 "46종 중 몇 개나 실제로 계산되는가"라는 진행률 질문에 답을 흐리게 만든다.**

### 6.4 권고

1. 카탈로그와 게시 목록 중 하나를 단일 정본으로 통합하거나(예: `_EXPERIMENT_METRICS`가 `METRIC_SPECS`에서 `layer==3`인 항목을 파생하도록), 통합이 부담되면 최소한 **왜 두 목록이 다른지**를 코드 주석과 `kpi-definition-v1.md`에 명시한다.
2. `rejection_reason_count`는 구현 없이 "computable"로 선언된 것이 가장 위험하다 — **함수를 만들거나, 카탈로그에서 빼거나, 상태를 `not_run`으로 바꾼다.** "구현도 없이 계산 가능이라 적힌 지표"는 이 프로젝트가 가장 경계하는 종류의 결함(선언과 실제의 불일치)과 정확히 같은 모양이다.
3. `missing_field_count`·`source_event_count`는 함수가 이미 있으므로 `publish.py`의 `ingestion_report` 조립부에 호출을 추가하기만 하면 된다(비용이 낮다).
4. ML 계열 9종 게시 vs 5종 비게시의 경계 원칙을 문서화하거나, 5종도 동일하게 `NEEDS_MODEL_OUTPUT`으로 게시한다.

---

## 7. `kpi-definition-v1.md` §7 Secondary 9종 vs 실제 역할 배정 5종

**주장 위치** `.agent-team/03-service-planning/kpi-definition-v1.md` §7.3
**실제** `src/measurement/publish.py:880-896` `_METRIC_ROLES`

### 7.1 검증

문서 §7.3 Secondary 목록(9종): `auuc`·`uplift_by_decile`·`pehe`·`corr(τ̂,τ)`·`clv_mape`·`top20_precision`·`retention_rate`·`repurchase_rate`·`ai_roi`

코드 `_METRIC_ROLES`의 `"secondary"` 값을 가진 항목(5종): `incremental_revenue`·`roi`·`ai_roi`·`retention_rate`·`repurchase_rate`

**교집합 3종만 일치**(`ai_roi`·`retention_rate`·`repurchase_rate`). 문서에는 있지만 코드에 role이 없는 것(6종, 기본값 `"none"`으로 게시됨): `auuc`·`uplift_by_decile`·`pehe`·`corr_tau_hat_tau`·`clv_mape`·`top20_precision`. 코드에는 있지만 문서 §7.3에 없는 것(2종): `incremental_revenue`·`roi`(단, 이 둘은 §7.1의 P1 계산식 구성요소이자 §5.3 표에 이름이 등장하므로 "언급되지 않은 것"은 아니다 — §7의 역할 분류표에만 없다는 뜻이다).

**Primary(2종)·Guardrail(4종)은 문서와 코드가 정확히 일치한다** — 이 불일치는 Secondary 계층에 국한된다.

### 7.2 판정

Primary·Guardrail 배정은 정확히 옮겨졌지만, Secondary 배정은 구현 시점에 축소된 것으로 보인다(9종 중 5종만 코드화, 그중 2종은 문서 목록 밖). `metrics[].role`은 `KPI_DEFINITION_v1`이 `PARTIAL`(GATE 2에서 Lock 예정)이므로 이 배정 자체가 아직 확정값은 아니다 — 즉 **차단 사유는 아니다.** 다만 "문서가 말하는 배정"과 "화면이 실제로 보여주는 배정"이 다르면, GATE 2 이전에 Secondary 배지를 보는 사람이 문서와 다른 인상을 받을 수 있다.

### 7.3 권고

GATE 2에서 역할 배정을 최종 확정할 때 `_METRIC_ROLES`를 `kpi-definition-v1.md` §7.3의 9종 전체(또는 그 문서를 코드에 맞춰 축소)로 맞춘다. C1 범위에서는 "역할은 PARTIAL이며 배정이 미완"이라는 사실 자체가 이미 `freeze_status.json`의 `scope_note`로 드러나 있으므로 긴급하지 않다.

---

## 8. `ReasonCode` 7종(기획) vs 9종(계약·구현)

**주장 위치** `.agent-team/03-service-planning/kpi-definition-v1.md` §2.4
**실제** `src/measurement/schema.py:486-505` `class ReasonCode` — 9종

### 8.1 검증

문서 §2.4 표: `NO_SOURCE_EVENT`·`MISSING_FIELD`·`NO_COST_BASIS`·`NEEDS_TWO_STRATEGIES`·`NEEDS_MODEL_OUTPUT`·`PARAM_UNCONFIRMED`·`BLOCKED` — 7종.

코드: 위 7종 + `NOT_RUN` + `PRECONDITION_MISSING` = **9종**. `schema.py`의 `ReasonCode` 클래스 독트링이 이 차이를 이미 정확히 서술한다:
> *"기획 문서(kpi-definition-v1.md §2.4)는 7종을 적었고 계약은 9종이다... 계약이 정본이다."*

### 8.2 판정

이것은 오류라기보다 **의도된 확장이 기획 문서에 소급 반영되지 않은 것**이다. `api-contracts.md`의 결정 D-15가 이 확장을 이미 승인·기록했다("사유 코드 2종 추가"). 코드 자체가 "계약이 정본"이라고 선언하므로 실사용 위험은 낮다.

### 8.3 권고

`kpi-definition-v1.md` §2.4 표에 `NOT_RUN`·`PRECONDITION_MISSING` 2행을 추가해 실제 계약과 맞춘다 — 값에는 영향 없는 문서 갱신이다.

---

## 9. `AGENTS.md` "프로젝트 현황" 문단이 실측과 어긋난다

**주장 위치** `/Users/otter/72offsuit/AI_ROI/AGENTS.md` "## 프로젝트 현황 (2026-09-10)"
**실제** `src/measurement/` 11개 모듈, 테스트 407건, GATE 1 부분 봉인 실행 완료

### 9.1 검증

2026-09-14 현재 `AGENTS.md` 원문:
> *"`src/`에 파트 디렉터리와 지침 파일만 있고 **구현 코드는 아직 없다.**"*
> *"CI는 `.github/workflows/isolation.yml` 하나뿐이다. 실행 가능한 검증 명령도 `tests.test_isolation` 하나뿐이며..."*

실측:
- `src/measurement/`에 `.py` 파일 11개(각각 5~75KB), 구현 완료(M-01~M-09 스토리 전부 `done`)
- `python3 -m unittest discover -s tests` — **407건**, `tests.test_isolation` 하나가 아니다
- `.github/workflows/`에 `isolation.yml` 외 `tests-with-deps.yml`(D-19)도 존재
- `config/gate1_lock.yaml`이 생성되어 GATE 1 부분 봉인이 이미 실행됨(`locked_by: Danto7632`, 2026-09-11)

### 9.2 판정

**리드가 이미 W1(2026-09-10)부터 CONCERNS로 지적하고 `wave-log.md`에 "W6 Timothy 수정" 대상으로 명시한 항목이다.** 이 문서(`09-docs/`) 작성 시점(W6 1단계, 2026-09-14)까지도 아직 반영되지 않았다.

### 9.3 권고

**이 항목은 제 소유 경로(`09-docs/**`) 밖이다** — 팀 리드의 지시("제품 코드 수정 절대 금지")에 따라 직접 수정하지 않았다. 권고 수정안:

```diff
- ## 프로젝트 현황 (2026-09-10)
+ ## 프로젝트 현황 (2026-09-14)

- - `src/`에 파트 디렉터리와 지침 파일만 있고 **구현 코드는 아직 없다.**
+ - `src/measurement/`는 구현 완료(M-01~M-09). `src/simulator/`·`decision/`·`diagnostics/`·`orchestration/`은
+   여전히 지침 파일만 있고 구현 코드가 없다.
+ - `dashboard/`(Next.js, :3001)에 관측 화면군 6화면 + 정적 화면 1종이 구현됨(d-01·d-02).
+ - GATE 1은 부분 봉인(PARTIAL_FREEZE) 상태다. 완전 봉인(LOCKED)은 0종.

- - CI는 `.github/workflows/isolation.yml` 하나뿐이다. 실행 가능한 검증 명령도
-   `tests.test_isolation` 하나뿐이며 lint·build·타입 검사는 미정의.
+ - CI는 `.github/workflows/isolation.yml`(의존성 없이) · `tests-with-deps.yml`(의존성 설치 후)
+   2종이다. 저장소 전체 검증은 `python3 -m unittest discover -s tests`(407건)이며
+   lint·build·타입 검사는 여전히 미정의.
```

브랜치 `feat/measurement-layer-and-dashboard`(PR #57)가 병합되면 이 정정이 특히 시급해진다 — `main`을 처음 여는 사람이 이 문단을 그대로 믿으면 이미 구현된 측정 계층·대시보드를 없는 것으로 오인한다.

---

## 10. `data_spec.html` §17.4의 `results/` 접근 주체 목록 공백

**주장 위치** `docs/data_spec.html` §17.4 (경로 접근 표에 `measurement`가 없다)
**실제** `src/measurement/publish.py`가 `results/`에 쓴다. `docs/data_spec.html` §9는 이를 요구한다.

### 10.1 검증

`docs/measurement_contract.md` §7.5가 이 정본 긴장(`T-1`)을 이미 상세히 기록했다: §17.4(접근 주체 목록)와 §9(측정 계층이 `results/`에 쓰라는 규정)가 서로 다른 말을 한다. `tests/test_isolation.py:31-36`(강제 수단)은 `measurement`의 `results/` 접근을 막지 않는다 — 즉 **강제 규칙(테스트)과 §9는 일치하고, §17.4 표만 낡았다.**

### 10.2 판정

이미 `docs/measurement_contract.md`(내 소유 경로 밖, `docs/` 최상위)가 인지·기록했고 "§17.4의 접근 주체 목록에 `measurement`(쓰기)를 추가해야 한다"고 W6 항목으로 남겼다. 이 gap 문서는 그 사실을 재확인하고 `.agent-team/09-docs/`에도 남긴다 — `data_spec.html`은 `Plan/` 서브모듈이 아니라 이 저장소의 `docs/`에 있으므로(정본 SRS/PRD와 별개로 이 저장소가 만든 파생 문서) 수정 자체는 이 팀 권한 내이지만, **이번 작업 범위(`09-docs/**`)에 포함되지 않아 직접 수정하지 않았다.**

### 10.3 권고

`docs/data_spec.html` §17.4 표에 `measurement | results/ | 쓰기` 행을 추가한다.

---

## 11. 이슈 `#43`·`#44`가 머지 이후에도 OPEN

**주장 위치** (프로세스, 문서 불일치 아님) `wave-log.md` "2026-09-10 · W1 Discovery" 이후 반복 언급
**실제** PR **#50**(M-1, merged 2026-09-10T13:34)·**#51**(M-2, merged 2026-09-10T14:03)이 머지됐으나(리드가 GitHub에서 직접 확인, 2026-09-14) 이슈 `#43`·`#44`는 GitHub 상 OPEN 상태로 남아 있다(리드가 여러 차례 "사용자 확인 필요"로 표시, 머지 후 나흘째 아직 미해소)

### 11.1 판정

이것은 **설계 문서와 구현의 불일치가 아니라 GitHub 이슈 상태와 실제 완료 상태의 불일치**이며, `AGENTS.md`의 Issue close 개별 승인 규칙상 L1 권한 밖(사용자 명시 지시 필요)이다. 참고용으로만 기록한다 — `09-docs/` 소유 범위 밖이고 이슈 조작은 이 역할의 권한도 아니다.

### 11.2 권고

사용자가 `#43`·`#44`의 close 여부를 판단할 때 참고할 근거: 두 이슈가 요구한 구현(M-1 sink 결함 수정, M-2 스키마 값 강제)은 이후 스토리(M-01~M-09)에서 상세 커버됐고 `tests/test_schema.py`·`tests/test_sink.py`가 이를 고정한다. 다만 이슈 본문의 원래 수용 기준과 현재 구현이 1:1로 대조됐는지는 이 문서의 검증 범위 밖이다.

---

## 12. 계약 스키마 자체의 `description`에 "47종" 인용이 남아 있음

**주장 위치** `docs/contracts/measurement-publish/v1/kpi_report.schema.json:5` (JSON Schema `description` 필드)
**실제** `src/measurement/kpi.py` `METRIC_SPECS` — 46종(§1 참조)

### 12.1 검증

```
$ grep -n "47종" docs/contracts/measurement-publish/v1/kpi_report.schema.json
5:  "description": "... ★ kpi-definition-v1.md 가 정의한 지표 전부(47종)가 항목으로 존재한다 — ...",
```

### 12.2 판정

이 문자열은 `minItems`·`enum` 같은 구조적 제약이 아니라 **사람이 읽는 설명 텍스트**라 계약 검증에는 영향을 주지 않는다(§1의 총계 오류와 달리 `jsonschema` 검증이 이 숫자를 강제하지 않는다). 그러나 **API 문서의 기계가독 정본인 스키마 파일 자체**에 §1의 오류(47)가 그대로 인용되어 있어, 다음에 이 스키마를 읽는 사람(대시보드 `types.ts` 작성자, 이 저장소를 처음 여는 개발자)이 재확인 없이 "47종이 정답"이라 믿을 위험이 있다 — §1의 오류가 **문서 하나가 아니라 세 곳(기획 문서 §1·계약 스키마 여기·코드 자신의 doctest §1.2(C))에 이미 전파됐다.** 세 번째(`kpi.py:1219` doctest)는 실행 가능한 형태였는데 실행기가 없어 놓쳤다는 점에서 이 프로젝트가 가장 경계하는 실패 양식과 같은 자리이며, 리드가 저장소 전체 doctest 18개를 전수 실행해 확정했다(§1.2(C) 참조).

### 12.3 권고

`kpi_report.schema.json`의 `description`을 46종으로 정정한다. `description` 필드만 바꾸는 것은 구조 변경이 아니므로 `tests/test_publish_contract.py::TestContractCopyDiffersOnlyAsDocumented`(스냅샷과의 의도된 차이 검사)에 영향이 없을 것으로 예상되나, **실행해서 확인하기 전까지는 단언하지 않는다** — 수정 자체는 Phillip 소유 경로(`docs/contracts/**`)이므로 이 문서는 사실만 남기고 실행하지 않았다.

---

## 13. `data_spec.html` §7.2 — 메타 4필드 `Nullable = N` 표기가 낡음

**주장 위치** `docs/data_spec.html` §7.2 (`Plan/` 서브모듈 정본)
**실제** `src/measurement/sink.py:74-83` `event_source()` — `simulator_version`·`random_seed`가 둘 다 `null`이면 커머스 실측분으로 판정(`MEA-002`)

### 13.1 검증

두 설계 문서가 **이미 독립적으로** 이 낡음을 지적했다:
- `.agent-team/04-architecture/data-model-erd.md` §2.2: *"⚠ `data_spec` §7.2 는 메타 4종을 `Nullable = N`으로 적었다(W1 D-1). **코드가 옳다** — null을 출처 판별에 쓰는 것이 `MEA-002`다. `data_spec`이 낡았다."*
- `docs/measurement_contract.md` §3: *"⚠ `docs/data_spec.html` §7.2 가 메타 4종을 `Nullable = N` 으로 적었다. **그 문서가 낡았다.**"*

`schema.py`의 `_EVENT_RULES`에서 메타 4종(`service_version`·`customer_version`·`simulator_version`·`random_seed`)은 항상 OPTIONAL(=nullable)이고, `null`이 단순 "값 없음"이 아니라 **출처 판별의 핵심 신호**로 쓰인다.

### 13.2 판정

**W1(2026-09-10~11) 시점에 이미 발견·기록된 낡음**이며 새 발견이 아니다. 다만 `data_spec.html`은 `Plan/` 서브모듈(정본은 `Plan` 저장소)이라 **이 저장소에서 수정할 권한이 없다**(`AGENTS.md` — "기획 문서 수정은 `Plan` 저장소에서 직접 한다"). 두 개의 독립 설계 문서가 같은 낡음을 반복해서 지적했다는 사실 자체가, 이 낡음이 실제 개발 과정에서 반복적으로 혼선을 준다는 신호이므로 W6 종합 목록에 다시 올린다.

### 13.3 권고

`Plan` 저장소의 `data_spec.html` §7.2를 사용자가 직접(또는 `Plan` 저장소 담당자에게 요청해) 정정 — **이 저장소의 권한 밖.**

---

## 14. `story-m-01` T3 문언 vs 기준선 테스트 — 운영적으로 해결, 문서 미정정

**주장 위치** `.agent-team/03-story-engineering/story-m-01-sink-defects-kr.md` T3
**실제** `src/measurement/sink.py` `_observe()`/`_is_observable()` — `tests/test_sink.py`

### 14.1 검증

`backend.md` §4.1이 이미 상세히 기록한 충돌:
> "**스토리 T3:** '`strict` 여부와 무관하게 `problems`가 있으면 `_observe`·`_buffer`로 보내지 않는다' **그런데 기준선 46건에 이것과 정면 충돌하는 테스트가 있다** ... T3을 문자 그대로 구현하면 이 테스트가 실패하고, 테스트를 고쳐 통과시키는 것은 금지다."

실제 구현은 위반을 두 종류로 갈랐다 — `event_type`이 유효한데 다른 위반이 있으면 관용 모드(`strict=False`)에서 **저장+보고**(기준선 유지), `event_type` 자체가 무효/부재이면 **거부**(크래시 방지). `tests/test_sink.py`의 `test_non_strict_keeps_record_but_still_reports`(기준선)와 새 방어 테스트가 공존하며 407 tests 전부 OK다.

`wave-log.md`(W5 완료 인계 목록)가 이를 W6 인계 항목으로 명시적으로 남겼다: *"`m-03 T3` 문언 ↔ 기준선 테스트 충돌 (Phillip이 `event_type` 유효성으로 갈라 둘 다 만족)"*.

### 14.2 ★ 리드 판정 D-25(2026-09-14) — 승인은 애초에 필요 없었다

**코드는 동작한다(407 tests OK)**. `backend.md:235`가 요청한 승인은 **조건부**였다:
> *"위 해석이 둘을 모두 만족하는 유일한 배치라고 판단했으나, T3의 의도가 '관용 모드에서 아무것도 저장하지 않는다'였다면 **기준선 테스트 수정 승인이 필요하다**."*

리드가 실행으로 그 조건이 성립하지 않았음을 확인했다:
```
$ git diff $(git merge-base origin/main HEAD) HEAD -- tests/
11 files changed, 5220 insertions(+), 1 deletion(-)
```
**삭제는 정확히 1줄이고, 단언이 아니라 픽스처 값이다:**
```
-        "category": "신선식품",
+        "category": "fresh_food",
```
이 변경은 GATE 1 선행조건 G-4(카테고리 어휘 정본 확정 — 영문)에 따른 것이지 T3 충돌 회피가 아니다. **기준선 단언은 한 줄도 수정되지 않았다.** Phillip이 `event_type` 유효성으로 위반을 가른 해석이 두 요구(스토리 T3 정신 + 기준선 테스트)를 모두 실제로 만족시켰고(407 OK, 기준선 단언 무변경), **승인 요청의 전제 조건("의도가 달랐다면")이 발동하지 않았다.**

**→ 판정: "미승인 상태로 남은 것"이 아니라 "승인이 필요 없었던 것으로 확정된다"(D-25).** 남는 것은 문서뿐이다 — `story-m-01-sink-defects-kr.md`의 T3 문언 자체가 실제 채택된 해석을 반영해 갱신되지 않았다는 사실.

### 14.3 권고

`story-m-01-sink-defects-kr.md`의 T3 문언을 실제 구현 규칙("`event_type`이 유효한데 다른 위반이 있으면 관용 모드에서 저장+보고, `event_type` 자체가 무효/부재이면 거부")으로 정정하고, "리드 판정 D-25(2026-09-14) — 이 해석은 기준선 테스트를 한 줄도 바꾸지 않고 성립하며, 승인은 필요 없었던 것으로 확정됐다"는 확정 주석을 추가한다.

---

## 15. 토큰 전략 규약 예외가 원 규약 문서에 반영되지 않음

**주장 위치** `.agent-team/07-design/design-system/token-strategy.md` §2.1 · `.agent-team/07-design/design-handoff.md` §1.1 — "이식하는 토큰 생성기 스크립트 본문은 한 줄도 고치지 않는다"(K 규약)
**실제** `dashboard/scripts/tokens/verify.mjs` — 실제로 1줄 수정됨

### 15.1 검증

`story-d-01-dashboard-foundation-kr.md` §4.4가 리드 지시로 이미 이 규약의 예외를 기록했다:
> "⚠ 이것이 `token-strategy.md` K 규약과 충돌한다 ... `design-tokens.mjs`·`render.mjs`·`resolve.mjs` 3개는 그 말이 맞다. **`verify.mjs` 1개는 틀리다.** 한 줄을 고치지 않으면 `tokens:test`가 실행 자체를 못 한다."

실제 `dashboard/scripts/tokens/verify.mjs` 머리 주석에 수정 사실과 사유가 남아 있다(`join(root, 'Plan/DESIGN.md')` → `join(root, '../Plan/DESIGN.md')`, 1줄). `frontend.md` §4가 `npm run tokens:test` 실행 결과(`15 scenarios passed`)로 이 수정이 문제를 일으키지 않음을 확인했다.

### 15.2 판정

**스토리 문서(`story-d-01`)에는 예외가 정확히 기록되어 있다.** 그러나 **원 규약 문서(`token-strategy.md`·`design-handoff.md`)는 "한 줄도 고치지 않는다"는 절대 규칙을 그대로 유지**하고 있어, 이 규약만 읽는 사람(예: 이후 사이클에서 `(results)/` 화면군을 위해 토큰 파이프라인을 다시 만지는 개발자)은 예외를 모른 채 잘못된 전제로 작업할 수 있다.

### 15.3 권고

`token-strategy.md` §2.1과 `design-handoff.md` §1.1에 "단 `verify.mjs`는 경로 깊이 차이로 1줄 수정이 불가피하다(사유는 파일 머리 주석 참조)"는 각주를 추가한다.

---

## 16. `dashboard/AGENTS.md`의 `value_formatted` 서술이 낡았다

**주장 위치** `dashboard/AGENTS.md` §4(코드 예시 직후) — *"★ `value_formatted`는 2026-09-11 현재 계약에 없다. M-06 §4.16이 추가한다. 그 전까지 `ok`·`unconfirmed` 셀은 `계약 준비 중`으로 렌더된다."*
**실제** `docs/contracts/measurement-publish/v1/common.schema.json`(§215-329)에 `value_formatted`가 이미 존재하고(최종 수정 2026-09-12, `dashboard/AGENTS.md`의 서술 시점보다 이전), `frontend.md` §12(Andrew 기록)에 따르면 M-06 완료 후 실제 게시물에서 `value_formatted` 18건 전부가 렌더링됨을 확인했다.

### 16.1 검증

```
$ grep -n "value_formatted" docs/contracts/measurement-publish/v1/common.schema.json
215:        "value_formatted": {
244:              "value_formatted"
280:              "value_formatted"
329:                    "value_formatted"
```

`dashboard/AGENTS.md`의 문장은 **작성 시점(d-01, M-06 착수 전)에는 정확했다.** M-06이 나중에 완료되면서 이 전제 자체가 무효화됐는데, `dashboard/AGENTS.md` 본문이 그 사실을 반영하도록 갱신되지 않았다.

### 16.2 판정

`dashboard/AGENTS.md`는 이후 사이클(`(results)/` 화면군) 구현자가 가장 먼저 읽는 지침 파일이다. 이 문장을 그대로 믿으면 "계약에 `value_formatted`가 없다"고 오인하고 `m.value`를 직접 포맷하는 코드(정확히 이 문서가 금지하려는 `?? 0` 패턴으로 이어지는 경로)를 쓸 위험이 있다 — **금지 패턴을 경고하는 문장이, 그 문장 자신의 낡은 전제 때문에 반대 결과를 유도할 수 있는 역설적 상태다.**

### 16.3 권고

`dashboard/AGENTS.md`의 해당 문단을 다음으로 갱신한다: *"`value_formatted`는 계약에 존재한다(M-06 완료, `common.schema.json` 참조). `ok`·`unconfirmed`이면 반드시 채워진다. 화면은 이 문자열을 그대로 출력하고 `m.value`를 직접 포맷하지 않는다."* 이 파일은 `dashboard/**` 소유(Andrew/W5-C)이며 09-docs 소유 범위 밖이라 직접 수정하지 않았다.

---

## 17. GATE 1 Lock CLI가 설계 문서대로 구현되지 않았다

**주장 위치** `.agent-team/04-architecture/gate1-freeze-procedure.md` §6.1 Phase 4 — *"③ `python3 -m src.measurement.freeze record --by "<이름>"` ← `config/gate1_lock.yaml`을 쓴다"*
**실제** `src/measurement/freeze.py`에 CLI 진입점이 없다 — `record()` 함수만 정의돼 있고 `argparse`·`if __name__ == "__main__"` 블록이 없다.

### 17.1 검증

```
$ grep -n "^def main\|argparse\|__main__\|^def record" src/measurement/freeze.py
648:def record(
```

`gate1-freeze-procedure.md` 자신도 같은 절에서 이미 이 공백을 인지하고 있었다:
> *"③의 `freeze record` 명령은 **아직 존재하지 않는다.** W5-B에서 만든다."*

그러나 W5(Phillip)가 실제로 GATE 1 부분 봉인을 실행한 절차(`docs/gate1_checklist.md` §5.2, `backend.md` §8.3)는 CLI가 아니라 **Python 인터프리터에서 `freeze.record()`를 직접 호출**하는 방식이었다 — CLI 래퍼 자체가 끝내 만들어지지 않았다.

### 17.2 판정

이것은 "리드가 이미 지적한 4건"류의 설계-구현 어긋남과는 성격이 다르다 — **설계 문서가 스스로 "아직 없다"고 명시했고, 그 상태가 구현 완료 이후에도 그대로 참으로 남았다.** 방치인지 의도된 축소(스크립트 대신 인라인 호출로 충분하다고 판단)인지가 문서에 구분되어 있지 않다. 영향은 낮다 — GATE 1 Lock은 이미 실행되어 `config/gate1_lock.yaml`이 존재하고, `docs/gate1_checklist.md`가 실제로 작동하는 절차(인라인 Python)를 이미 안내하고 있다.

### 17.3 권고

`gate1-freeze-procedure.md` §6.1의 ③ 단계를 CLI 예시 대신 `docs/gate1_checklist.md` §5.2가 쓰는 실제 인라인 Python 절차로 교체하거나, CLI가 정말 필요하면 `freeze.py`에 `argparse` 진입점을 추가한다.

---

## 18. `gate1-freeze-procedure.md` §6의 Lock 상태 예측이 실제 결과와 다르다

**주장 위치** `.agent-team/04-architecture/gate1-freeze-procedure.md` §6 "C1이 도달하는 상태"(W2 시점 예측) — *"Lock 9종 | LOCKED 0 · PARTIAL 최대 4 · PENDING/OUT_OF_SCOPE 5"*
**실제** `config/gate1_lock.yaml`(W5 결과) — `OUT_OF_SCOPE` 5 · `PENDING` 2 · `PARTIAL` 2 · `LOCKED` 0

### 18.1 검증

```yaml
items:
- {item: SERVICE_v1, status: OUT_OF_SCOPE}
- {item: CUSTOMER_PERSONA_v1, status: OUT_OF_SCOPE}
- {item: HIDDEN_TRAIT_RULE_v1, status: OUT_OF_SCOPE}
- {item: BEHAVIOR_RULE_v1, status: OUT_OF_SCOPE}
- {item: TREATMENT_RESPONSE_v1, status: OUT_OF_SCOPE}
- {item: EVENT_SCHEMA_v1, status: PENDING}
- {item: ECONOMIC_RULE_v1, status: PENDING}
- {item: CHURN_DEFINITION_v1, status: PARTIAL}
- {item: KPI_DEFINITION_v1, status: PARTIAL}
```

설계 시점 예측("PARTIAL 최대 4")과 실측("PARTIAL 정확히 2", `EVENT_SCHEMA_v1`·`ECONOMIC_RULE_v1`은 `PARTIAL`이 아니라 `PENDING`으로 확정)이 다르다.

### 18.2 판정

**문서 오류라기보다 예측이 빗나갔고 갱신되지 않은 경우다** — W2 시점에 James가 상한선("최대 4")으로 적은 것이 실제 W5 판정(2)보다 보수적으로 넓게 잡혔을 뿐, 논리적 모순은 아니다("최대 4" 안에 "정확히 2"가 포함된다). 심각도는 낮다.

### 18.3 권고

`gate1-freeze-procedure.md` §6을 실측값(`PARTIAL 2 · PENDING 2 · OUT_OF_SCOPE 5 · LOCKED 0`)으로 갱신해 "예측"이 아니라 "확정 결과"로 읽히게 한다.

---

## 19. `usp.md` D-6 권고가 실제 리드 결정과 다르다 (이미 다른 문서에는 정확히 반영됨 — 참고용)

**주장 위치** `.agent-team/03-service-planning/usp.md` §4 D-6 — *"내 추천: ⑵ Timothy. 지침 파일 정본을 한 사람이 갖는 규칙을 깨지 않는 편이 안전하다."*
**실제** 리드 판정(`wave-log.md` 2026-09-11, D-6) — *"`dashboard/AGENTS.md`·`CLAUDE.md` 최초 작성은 **Andrew**(W5-C) 소유. … W6 Timothy는 검토·정제."*

### 19.1 검증

`dashboard-architecture.md` §7과 `story-d-01-dashboard-foundation-kr.md` §4.5는 이미 정확히 "최초 작성 Andrew 소유"로 반영돼 있다. `usp.md`만 자신이 W2에서 낸 원래 권고를 리드 판정 이후 갱신하지 않은 채 남아 있다.

### 19.2 판정

**실무 영향 없음.** 실제로 소유권을 참조하는 다른 모든 문서(아키텍처·스토리)가 이미 올바른 결정을 반영하고 있어, `usp.md`를 읽고 혼동할 사람이 이 문장에 도달하기 전에 다른 정본을 먼저 만날 가능성이 높다. 완전성을 위해 기록만 남긴다.

### 19.3 권고

`usp.md` §4 D-6에 "이 권고는 채택되지 않았다 — 최종 결정은 `wave-log.md` 2026-09-11 D-6(Andrew 소유) 참조"라는 각주를 추가한다.

---

## 대조했으나 불일치 없음 (gap 아님 — 다음 사이클을 위한 보존 기록)

gap이 아니라도 **무엇을 확인했는지 자체가 다음 사이클에 값어치가 있다.** 아래는 설계 문서·계약과 실제 구현을 대조했고, **불일치가 없었던** 항목들이다(2026-09-14, Timothy + fork 회수분 교차검증).

### `dashboard/AGENTS.md`(256줄) — DG-1~DG-19 전수 실재, 누락 0건

```
$ grep -o "DG-[0-9]*" dashboard/AGENTS.md | sort -u
DG-1 DG-2 DG-3 ... DG-19   (19/19 전부 존재)
```
`dashboard-architecture.md` §7·`story-d-01` §4.5가 "반드시 포함"으로 요구한 항목 19종(격리·데이터경로 8종 DG-1~DG-8 + 디자인 제약 11종 DG-9~DG-19)이 전부 실제 파일에 있다. `dashboard/CLAUDE.md`도 `@AGENTS.md` 한 줄 위임(`ISO-004`)을 정확히 지킨다(내용 복제 0줄).

### `types.ts`(487줄) — 계약 7종과 필드 단위 대조, 구조적 불일치 0건

`ReasonCode`(`types.ts:22-30`)가 정확히 9종(`NO_SOURCE_EVENT`~`PRECONDITION_MISSING`), `HeadlineCode`(`types.ts:200-207`)가 정확히 8종(`CONTRACT_VIOLATION`~`ALL_CLEAR`) — 둘 다 계약의 실제 enum과 일치한다(§4.2·§7.1 참조).

**타입 수준의 추가 방어 한 겹 — `RejectionSample` 인터페이스에 `offending_values`가 의도적으로 없다:**
```ts
// types.ts:320-327
export interface RejectionSample {
  reason_key: string;
  event_type: string | null;
  partition_date?: string | null;
  source?: "commerce" | "simulator" | "unknown";
  problems: string[];
  offending_fields?: string[];   // ← 값이 아니라 필드 "이름"만
}
```
`offending_values`(값)가 타입 자체에 없어 **실수로도 렌더링할 수 없다.** 계약 스키마의 `propertyNames.enum`(22컬럼 제한, §6.4·gap §5 참조)이 게시 시점 방어라면, 이것은 **읽는 쪽 타입 시스템에서의 두 번째 방어층**이다 — DG-18("거부 레코드의 값을 렌더링하지 않는다")이 한 층이 아니라 두 층으로 강제된다는 뜻이라 기록해 둔다.

### `metric.ts`(225줄) — 금지 패턴 0건, `countText()`의 0/null 구분 확인

```
$ grep -nE '\?\?\s*0|\|\|\s*0|Number\(|parseFloat|toFixed\(|toLocaleString\(' dashboard/src/lib/format/metric.ts
```
전 매치(5건)가 **주석**(금지 패턴을 설명·경고하는 문서화 텍스트)이고 실행 코드에는 0건이다.

`countText()`(`metric.ts:78-81`)가 `basis.observed_count: 0`과 `basis.denominator: null`을 정확히 구분한다:
```ts
function countText(n: number | null | undefined): string | undefined {
  if (typeof n !== "number" || Number.isNaN(n)) return undefined;   // null/undefined → 절 자체 생략
  return String(n);                                                  // 0 → "0" 문자열로 출력
}
```
`typeof n !== "number"` 검사이지 falsy 검사가 아니라서, `observed_count: 0`은 "0"으로 정직하게 출력되고(§4.5 R-6이 요구하는 "세어 봤고 0이었다"의 증거), `denominator: null`은 문구 자체가 사라진다("분모 0"이 아니다) — dev-definitions.md §9(자주 헷갈리는 이름 쌍)가 서술하는 "measured 0 vs 값 없음" 구분이 코드에 그대로 구현돼 있다.

### `paths.ts` — `ponytail:` 마커 실재, 업그레이드 트리거 포함

```ts
// paths.ts:95-96
* ponytail: only the `results/` prefix is mapped; add a PROCESSED_DIR branch here
* the first time an index.json actually lists a `data/processed/` artifact.
```
W5 DoD가 요구한 "ponytail 마커에 업그레이드 트리거 필수"(`wave-log.md` W5 착수 기록)를 충족한다 — 조건("`data/processed/` 산출물이 실제로 등장하면")이 명시돼 있다.

---

## 검증 방법 메모

이 문서의 모든 수치는 다음 방식으로 확인했다(재현 가능):

```bash
# KPI 카탈로그 개수·분류
python3 -c "
from src.measurement import kpi
from collections import Counter
print('total', len(kpi.METRIC_SPECS))
print(Counter(s.layer for s in kpi.METRIC_SPECS))
print(Counter(s.c1 for s in kpi.METRIC_SPECS))
"

# AI 투자비용 산술
python3 -c "print((12_600_000/12 + 500_000) * (42/30))"

# ReasonCode / MetricStatus 종수
python3 -c "
from src.measurement.schema import ReasonCode, MetricStatus
print(len(list(ReasonCode)), len(list(MetricStatus)))
"

# 테스트 건수
grep -c '^    def test_' tests/test_*.py
```

읽기 전용 조사였다 — `src/`·`dashboard/`·`config/`·`docs/`·`tests/` 어디에도 파일을 쓰지 않았다.
