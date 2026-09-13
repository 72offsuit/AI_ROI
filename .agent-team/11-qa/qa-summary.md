---
name: qa-summary
role: Matthias (Role 15 · QA/SDET 리드)
wave: W6 · 1단계
date: 2026-09-14
target: feat/measurement-layer-and-dashboard (PR #57, 미병합) · HEAD 99e7cd0
---

# QA 요약 — 측정 계층 + GA형 관측 대시보드 (W5 산출물 실측)

> **원칙**: 보고를 신뢰하지 않고 재현했다. 모든 수치는 이 세션에서 직접 실행한 결과다.
> 실행 로그·재현 명령은 `test-flow.md`에, 항목별 인수조건 대조는 `test-cases.md`에, latency 실측은 `latency-report.md`에 있다.

## 0. 결론 — 3줄

1. **차단 결함 0건.** `python3 -m unittest discover -s tests`(no-deps `Ran 407 · OK skip=67`, with-deps `Ran 407 · OK skip=3`) · 격리 · 소유권 · 빌드 · 토큰 파이프라인 · `check:state-map` 전부 **보고와 정확히 일치**하게 재현했다.
2. **USP-1 핵심 메커니즘(계산 불가 ≠ 0)을 실제 `results/`(픽스처가 아니라 현재 파이프라인 산출물)에서 라이브로 확인했다** — 계산 불가 셀 0건이 숫자로 새는 사례, 측정된 0(`0건`/`0원` + 기준선)이 `—`로 뭉개지는 사례 모두 0건.
3. **차단은 아니지만 기록해야 할 결함 1건**(중간 심각도) — 커밋된 예시 픽스처(`04-architecture/examples/`)가 M-06 계약보다 낡아, 문서가 지시하는 재현 절차를 그대로 따르면 **USP-1 대표 장면(AC-12)이 화면에서 `계약 준비 중` 오류로 깨져 보인다.** 대시보드 코드의 결함이 아니라 픽스처 데이터 드리프트다. 아래 §3-A.

## 1. 실행한 것 — 전부 직접 재현

| # | 명령 | 결과 | 보고값과 일치 |
|---|---|---|---|
| 1 | `python3 -m unittest discover -s tests` (의존성 없이, Python 3.14.6) | `Ran 407 tests · OK (skipped=67)` | ✅ 일치 |
| 2 | `python3 -m unittest discover -s tests` (venv, `jsonschema 4.26.0`·`referencing 0.37.0`·`pyarrow 25.0.1`·`PyYAML 6.0.3`, Python 3.14.6) | `Ran 407 tests · OK (skipped=3)` | ✅ 일치 (CI는 3.12.4 pin이지만 3.14.6에서도 동일 버전 조합이 재현됨을 추가 확인) |
| 3 | `python3 -m unittest tests.test_isolation -v` | `Ran 6 tests · OK` | ✅ 일치 |
| 4 | `python3 .agent-team/04-architecture/tools/check_ownership.py` | `Phillip 46개 ∩ Andrew 50개 = 0개` · PASS | ✅ 일치(0 겹침 유지) |
| 5 | `cd dashboard && npm ci` | 369 packages, 0 vulnerabilities | ✅ |
| 6 | `npm run build` | `next build` 성공, 8라우트 전부 컴파일 | ✅ |
| 7 | `npm run tokens:test` | `15 scenarios passed` | ✅ 일치 |
| 8 | `npm run check:state-map` | `25 assertions passed` | ✅ 일치 |
| 9 | 독립 e2e 스위트(아래) — `npx playwright test` (Chromium headless, 실브라우저) | 43 tests · **41 passed · 2 deliberately red**(§3-A) | 신규 작성 |

## 2. 독립 e2e 하네스 — `e2e/` (QA 소유, `dashboard/` 미수정)

Andrew의 `dashboard/e2e/evidence.spec.ts`(제품 소유, 스크린샷 증거용)와 별개로, 실제 실행 중인 앱의 HTTP/DOM/콘솔 출력을 독립적으로 재검증하는 하네스를 만들었다. `dashboard/` 코드는 전혀 수정하지 않았다 — 읽기와 `npx next start` 실행만 했다.

- 데이터셋 3종을 각자 포트에서 동시 서빙: `empty-sink`·`commerce-connected`(예시 픽스처 스테이징) · **`real`**(저장소의 실제 `results/`, 즉 `python -m src.measurement.publish`의 현재 산출물)
- 8화면 × 3데이터셋 = 24조합 전부 **HTTP 200 · 콘솔/페이지 에러 0건** 확인, 전체화면 스크린샷 24장 생성(`e2e/screenshots/`) 후 육안 검토

### 2.1 검증 항목별 결과

| 파일 | 무엇을 확인했나 | 결과 |
|---|---|---|
| `tests/pages.spec.ts` | 24조합 HTTP 200·콘솔 에러 0 | ✅ 24/24 |
| `tests/zero-fill.spec.ts` | ① `obs-absent-ink` 슬롯에 숫자 0건 ② 측정된 0(`0건`/`0원`)이 `obs-value-ink` + 기준선과 함께 렌더 ③ em dash 뒤에 `0` 이어붙는 템플릿 버그 0건 — **실제 `results/`(9개 지표×2출처=18개 측정된 0) 기준** | ✅ 4/4 |
| `tests/quality-gate.spec.ts` | JSON `checks[].status` 집계(pass/fail/vacuous/not_run/blocked)와 `/quality` 배너 문구가 **정확히 일치**하는지, `pass=0`일 때 `✓` 글리프 0건인지, vacuous 행이 `공허한 통과 · 검사 대상 0행`으로 표시되는지 | ✅ 3/3 |
| `tests/contrast.spec.ts` | **C-10 — Andrew가 "실측 계산 안 함"으로 남긴 항목.** 8개 상태색 조합을 브라우저에서 실제 `getComputedStyle`로 읽어 WCAG 상대휘도 공식으로 재계산 | ✅ 1/1 (8쌍 전부 4.5:1 이상) — §3-B에 문서 오차 1건 별도 기록 |
| `tests/accessibility.spec.ts` | 최초 Tab이 건너뛰기 링크에 닿는지, 비활성 결과화면군 사이드바 항목이 `href` 없음·`tabIndex=-1`인지, 상태 글리프에 접근성 이름이 있는지 | ✅ 3/3 |
| `tests/rejections-security.spec.ts` | `commerce-connected` 픽스처의 실제 거부 샘플 값(`test-user-1`, UTC 타임스탬프)이 `/rejections` HTML 어디에도 나타나지 않는지 | ✅ 1/1 |
| `tests/visual-contract.spec.ts` | **Pretendard가 실제로 적용됐는지**(로드된 FontFace·computed font-family·.woff2 네트워크 응답 모두 확인 — Andrew가 "육안 확인만"으로 남긴 항목 자동화) · 1024px 미만에서 출처 2열이 커머스 우선으로 적층되는지(US-12) · 프로젝트의 실제 검토 기준 뷰포트(1024/1280/1440px)에서 가로 스크롤 0px인지 | ✅ 5/5 |
| `tests/fixture-contract-freshness.spec.ts` | 커밋된 예시 픽스처가 M-06 계약(`value_formatted` 필수)을 만족하는지 | ❌ **의도적으로 red** — §3-A |

### 2.2 육안 검토 — 스크린샷 8장 직접 확인

`real`(index, kpi, quality, freeze) · `commerce-connected`(kpi) 스크린샷을 Read 도구로 직접 열어 확인했다.

- `/`(real): 판정 배너가 `수집된 이벤트 0건`을 **info(보라)** 로 표시(경고색 아님, F-3 준수), notices 4건 전부 인라인 상시 노출, 결과 화면군 8항목이 사이드바에서 시각적으로 비활성 처리됨.
- `/quality`(real): 18행 검사표에서 `공허한 통과`(연보라)·`? not_run`(빨강 윤곽)·`⊘ blocked`(점선 윤곽)이 명확히 구분됨. `✓` 글리프 전체 화면에 0건.
- `/freeze`(real): Lock 9항목이 `OUT_OF_SCOPE`(회색)·`? PENDING NOT_RUN`(빨강 윤곽)·`⚠ PARTIAL`(경고, 범위 한정 문구 동반)로 구분됨.
- `/kpi`(commerce-connected): **§3-A의 결함이 여기서 시각적으로 재현된다** — 대표 장면 카드 revenue 슬롯이 `계약 준비 중` + ✕ 아이콘으로 깨져 있다.
- 한글 글리프 렌더링은 육안상 정상(두부 박스·시스템 폴백 특유의 형태 없음) — 다만 자소 디자인이 정확히 Pretendard인지의 최종 판정은 §2.1의 자동화된 로드 확인으로 대체했다.

## 3. 발견 사항

### 3-A. [중간 · 비차단] 커밋된 예시 픽스처가 M-06 계약보다 낡음 — USP-1 대표 장면 재현 불가

**증상**: `.agent-team/04-architecture/examples/{empty-sink,commerce-connected}/kpi_report.json`의 일부 `ok`/`unconfirmed` 지표에 M-06이 추가한 필수 필드 `value_formatted`가 없다.
- `empty-sink`: 3곳(`metrics[0]`의 commerce/simulator/combined)
- `commerce-connected`: **9곳**(`metrics[0,1,5,6,7,12]`) — **대표 장면 카드의 revenue를 포함**

**재현 절차** (frontend.md §1.1·story d-02 §8.1이 문서화한 그대로):
```bash
cd dashboard
node scripts/stage-fixture.mjs commerce-connected
AIROI_RESULTS_DIR=$PWD/.fixtures/commerce-connected/results AIROI_FIXTURE_MODE=1 npm run dev
# /kpi 접속 → 대표 장면 카드 revenue 슬롯에 "✕ 계약 위반 · 계약 준비 중 — value_formatted 가 게시물에 없습니다" 표시됨
```

**판정**: 대시보드 코드는 **정확히 설계대로 동작한 것**이다(`read.ts`의 계약 강제 방어선이 작동 — DG-1~DG-8 위반이 아니라 오히려 방어가 작동한 증거). 결함은 코드가 아니라 **`04-architecture/examples/`(architecture 소유, dashboard도 measurement도 아님)의 픽스처 데이터가 2026-09-11 M-06 계약 확정 이전 상태로 멈춰 있는 것**이다.

**영향**:
- 실제 `results/`(현재 파이프라인 산출물)는 문제없음 — 별도로 확인했다(§1, §2.1).
- 그러나 **AC-12(USP-1 대표 장면)의 2026-09-11자 스크린샷 45장은 현재 코드/데이터로 재현 불가능하다.** 누군가 `npm run shots:connected`를 다시 돌리면 대표 장면이 깨진 상태로 촬영된다.
- 이미 알려진 "commerce-connected 픽스처가 품질검사 7종만 담아 정본 18종과 불일치"(frontend.md §9.1)와 같은 근본 원인 계열 — **`tools/make_examples_connected.py`가 여러 세대의 계약을 하드코딩한 스냅샷을 갱신 없이 유지**하고 있다.

**★ 영향 범위 — 리드(Paul) 재현으로 추가 확인된 것.** AC-12에 도달하는 **커밋된 경로가 이것 하나뿐**이다:

```
$ git check-ignore -v results/ dashboard/screenshots/
.gitignore:64:results/                results/
.gitignore:71:dashboard/screenshots/  dashboard/screenshots/

$ git ls-files .agent-team/04-architecture/examples/ | wc -l
14   ← 추적됨. 유일하게 커밋된 재현 자료
```

- `dashboard/screenshots/`(45장, 촬영 증거) — **gitignore**(결정 D-17)
- `results/`(실제 게시물) — **gitignore**(같은 결정)
- `.agent-team/04-architecture/examples/` — **커밋됨. 그런데 낡았다.**

즉 **새로 clone한 사람이 대표 장면을 보는 커밋된 경로가 지금은 전부 막혀 있다.** 스크린샷은 저장소에 없고, 유일하게 있는 픽스처는 `계약 준비 중`으로 깨진다. `results/`를 직접 만드는 길(`python -m src.measurement.publish`)은 살아 있고 이 세션이 `real` 데이터셋으로 증명했으므로 **차단은 아니다** — 다만 **"gitignore 결정(D-17) + 픽스처 드리프트"가 겹쳐, 문서가 지시하는 재현 절차가 하필 깨진 쪽만 가리키는 상태**가 이 발견의 실제 무게다. 어느 한쪽만 보면 둘 다 사소해 보인다.

**QA 조치**: 코드를 고치지 않고 기록만 했다(소유 경계 준수). `e2e/tests/fixture-contract-freshness.spec.ts`가 이 결함을 **의도적으로 red 테스트**로 고정해 뒀다 — 픽스처가 갱신되면 자동으로 green이 된다. 픽스처 재생성은 `tools/make_examples_connected.py`(James/architecture 소유)의 몫이며, 사용자 지시 없이 만들지 않았다.

**권고**: `tools/make_examples_connected.py`(및 `empty-sink` 대응 스크립트)를 현재 `docs/contracts/measurement-publish/v1/` 계약 기준으로 재생성 — **사용자 승인 후** architecture 소유자가 처리할 항목.

### 3-B. [낮음 · 문서 정확성] 대비 실측값 0.16 오차 — `info` on `info-surface`

`missing-state-spec.md` §4.3: *"info(#6A00F4) on info-surface(#F4EEFF) = 6.50:1"*.

독립 재계산(Python WCAG 공식 + 브라우저 `getComputedStyle` 실측 양쪽) 결과 **실제값은 6.34:1**이다(문서 대비 −0.16). 다른 7개 조합은 소수점 둘째 자리까지 전부 정확히 일치했다 — `info` 조합만 오차가 있다.

```
text-secondary/background   7.82  →  7.81 (반올림 차)   OK
warning/warning-surface     6.62  →  6.62              OK
warning/background          6.85  →  6.85              OK
error/error-surface         5.91  →  5.91              OK
error/background            6.47  →  6.47              OK
info/info-surface           6.50  →  6.34   ★ 불일치(0.16)
text-muted/surface-muted    4.89  →  4.89              OK
success/success-surface     6.81  →  6.81              OK
```

**영향**: 없음 — 4.5:1 최소 기준을 여전히 여유 있게(1.84) 통과한다. `planned` 칩(4.89:1, 여유 0.39)처럼 재계산이 필요한 빡빡한 조합이 아니다. **문서 수치 오기**로 판단, 코드·화면에는 영향이 없다.

### 3-C. [정보] "vacuous 7건"이 실제로는 8건으로 늘어남 — 결함 아님, 개선의 결과

여러 문서(wave-log, story-d-02, backend.md)가 "`empty-sink`는 18행 중 7행이 vacuous"라고 못박아 뒀다. **커밋된 예시 픽스처 기준으로는 정확히 7건**임을 재확인했다(문제없음).

그러나 **현재 실제 `results/`는 8건**이다. 원인은 `DQ-06`(시각 정합성)이 M-01의 타임존 정책 확정으로 `BLOCKED`를 벗어나 실행 가능해졌고(backend.md §8.2가 예고한 그대로), 빈 Sink에서는 검사 대상이 0건이라 `pass`가 아니라 정직하게 `vacuous`로 떨어지기 때문이다. **화면은 이 값을 하드코딩 없이 게시물 그대로 보여주고 있음**을 확인했다(`/quality` 배너가 JSON의 `pass 0 / not_run 9 / blocked 1 / vacuous 8`과 정확히 일치). DG-3(화면이 계산하지 않는다) 준수가 실측으로 증명된 사례이며, 팀 문서의 "7건" 서술이 이제 stale하다는 사실만 참고로 남긴다.

## 4. 인수조건(AC) 독립 판단 — d-01 AC-6

Andrew가 `d-01` AC-6 원문(*"`status !== "ok"` 인데 `value !== null` 이면 던진다"*)을 문자 그대로 구현하지 않고 `{unavailable, blocked, not_run}`에만 한정한 것에 대해, **독립적으로 검토한 결론: 올바른 판단이다.**

- AC-6을 문자 그대로 구현하면 **모든 정상 `unconfirmed` 지표(예: `churn_rate` 18.3%)가 렌더링 시 예외를 던진다** — `common.schema.json`이 `unconfirmed`에 `value`·`basis`·`params_used`를 필수로 요구하기 때문이다.
- 이는 **같은 스토리 묶음의 US-6 인수조건**(*"`PARAM_UNCONFIRMED` 지표는 값과 함께 사용한 파라미터를 표시한다"*)과 정면으로 충돌한다 — AC-6을 문자대로 따르면 US-6을 어긴다.
- 실제 코드(`read.ts:44,100-106`)에 이 이탈이 사유와 함께 주석으로 남아 있고, `UNCOMPUTABLE = {unavailable, blocked, not_run}`로 정확히 세 상태만 예외 대상이다.
- **라이브로 확인**: `commerce-connected`(unconfirmed `churn_rate` 포함) `/kpi`를 로드해도 콘솔/페이지 에러 0건(`pages.spec.ts`) — 예외가 발생하지 않는다는 것을 실제 실행으로 확인했다.

**결론**: AC-6의 **문서 표현이 부정확**한 것이지 구현이 잘못된 것이 아니다. 0-채움 방지라는 AC-6의 실제 의도(계산 불가 상태에 값이 새어나가는 것 차단)는 `{unavailable, blocked, not_run}` 세 상태로도 완전히 충족되며(§2.1 zero-fill 결과가 증거), 오히려 `unconfirmed`까지 포함했다면 제품이 깨졌을 것이다.

## 5. BLOCKED — 이번 세션에서 실행하지 못한 것

없음. 팀이 이전에 "육안 확인만 가능"으로 남긴 두 항목(대비 8조합 C-10, Pretendard 렌더링)을 모두 자동화된 검증으로 닫았다(§2.1). 남는 것은 **Pretendard 자소 디자인 자체가 다른 한글 산세리프와 시각적으로 구분되는가**라는, 폰트 렌더링 엔진 수준의 최종 확인뿐이며 이는 육안 스크린샷 검토(§2.2)로 대체했다 — 완전한 픽셀 비교 자동화는 이번 세션의 범위로 잡지 않았다(과잉 정밀도, 로드/적용 확인으로 실질적 리스크는 이미 닫힘).

## 6. 판정

| 게이트 | 판정 |
|---|---|
| 회귀 (`unittest`) | ✅ PASS — 407/407, 회귀 0 |
| 격리 (`test_isolation`) | ✅ PASS |
| 소유 경계 (`check_ownership`) | ✅ PASS |
| 대시보드 빌드·토큰·상태맵 | ✅ PASS |
| USP-1 (계산 불가 ≠ 0, 실제 `results/` 기준) | ✅ PASS |
| 접근성·보안(거부 샘플 마스킹) | ✅ PASS |
| 대비(C-10)·Pretendard | ✅ PASS (자동화로 신규 확인) |
| 차단 결함 | **0건** |
| 비차단 발견 | 3건 (§3-A 중간 · §3-B 낮음/문서 · §3-C 정보) |

**전체 판정: PASS (비차단 발견 3건 동반).** GATE 1 부분 봉인·PR #57 병합 여부는 사용자 판단 사항이며, §3-A(픽스처 드리프트)는 병합을 막을 이유가 아니지만 **다음에 USP-1 스크린샷을 다시 찍기 전에는 먼저 고쳐야 한다.**
