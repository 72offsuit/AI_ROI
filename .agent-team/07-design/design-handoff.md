# 디자인 핸드오프 — W5-C Andrew · W6 Thomas·Matthias·Timothy

**작성** Jonnathan (Role 7 · Chief Designer) · 2026-09-11 · 사이클 **C1**
**목업** https://claude.ai/code/artifact/396e511c-8d97-4e60-ad2d-8d0ee6070cc2 (아트보드 5종)
**읽는 순서** `missing-state-spec.md` → `ux-flow-map.md` → `ui-spec.md` → **`contract-reconciliation.md`** → `design-system/`

> ### ⚠ 2026-09-11 — James T2.7 계약 수신 후 개정됨
> 라우트 이름·첫 화면 구조·시각 상태 이름이 바뀌었고 규칙 V-12와 `NoticeBar`가 신설됐다.
> **[`contract-reconciliation.md`](contract-reconciliation.md)가 그 델타의 정본이다.** 다른 문서의 개정 전 서술과 충돌하면 그 문서를 따른다.

---

# 0.0 ★ 어휘 우선순위 — 기획 문서와 계약이 겹치면 **계약이 이긴다** (리드 판정, 2026-09-11)

> **사유 코드·상태 이름·지표 이름이 `03-service-planning/`의 기획 문서와 `04-architecture/`의 게시물 계약에 둘 다 정의되어 있으면, 계약(`schemas/common.schema.json`)이 정본이다.**
> 근거: **계약은 검증되고 문서는 검증되지 않는다.** 스키마는 위반을 거부하고, 문서는 어긋나도 아무것도 실패하지 않는다.

| 항목 | 기획 문서 | **정본 (계약)** |
|---|---|---|
| 사유 코드 | `kpi-definition-v1.md` §2.4 — **7종** | **`common.schema.json` — 9종** (`NOT_RUN`·`PRECONDITION_MISSING` 추가) |
| 상태 이름 | (없음) | `metric_value.status` — 5종 |
| 지표 이름·계산식 | `kpi-definition-v1.md` | `kpi_report.metrics[]`의 `formula`·`definition_ref` (문서를 **인용**한다) |

**D-15는 해소됐다.** `NOT_RUN`·`PRECONDITION_MISSING`은 James가 계약에서 신설해 **9종으로 확정**했다. 정본 위치가 Joshua의 문서에서 계약으로 옮겨간 것이며, **이 설계의 상태 파생표(§3-③ `contract-reconciliation.md`)를 다시 짤 필요가 없다.**

**Andrew가 헷갈릴 자리다** — 두 문서가 같은 것을 다르게 세고 있으면(7종 vs 9종) 계약을 따른다.

---

# 0. 차단 항목 — 이것이 풀리기 전에 구현할 수 없는 것

task-graph §5: *"W5-C Andrew — **T2.7 지표 계약 확정 후에만 착수**"*. 그 계약이 아직 없다.

| # | 차단 | 막히는 것 | 대기 |
|---|---|---|---|
| ~~B-1~~ | ~~게시물 계약 전체~~ | **해소** — 계약 초안 수신(2026-09-11). 17개 요청 중 13개 충족 | — |
| **B-2** | **`blocks_metrics` 결손→영향 인접 관계** | ⑦ 결손→영향 패널 · V3 영향 열 · V4 영향 열 (`ImpactChain` 전체) | **James — 미해결 · 최우선** |
| ~~B-3~~ | ~~기준(basis) 필드~~ | **해소** — `denominator`·`population`·`window`·`denominator_definition`·`formula`·`definition_ref`가 온다 (요청보다 강하다) | — |
| ~~B-4~~ | ~~생성 명령 문자열~~ | **정직하게 고정.** 계약이 *"2026-09-11 현재 실행할 수 없다"* 를 명시하고 *"게시가 필요하다"* 안내로만 쓰라고 지침. 확정 문구는 `contract-reconciliation.md` §3-⑥. **`gate1_checklist.md`에 `DB-013` 부분 충족으로 남긴다** | — |
| ~~B-5~~ | ~~`not_run` 키~~ | **해소** — 계약 `status` 5값이 `blocked`(못 했다)와 `not_run`(안 했다)를 직접 가른다 | — |
| **B-8** | **`index.json.verdict` 판정 집계** | 첫 화면 판정 배너. 없으면 화면이 6개 게시물을 세어야 하고 **R-2 위반** | **James — 미해결** |
| **B-9** | **출처 `link_state`** | "미연결(정상) vs 정지(이상)" 구분. 없으면 화면이 판정 → R-2 경계 | **James — 미해결** |
| ~~B-10~~ | ~~사유 코드 `NOT_RUN`·`PRECONDITION_MISSING` (D-15)~~ | **해소 (리드 판정).** 계약이 **9종으로 확정**했고 계약이 어휘 정본이다 — §0.0. 상태 파생표 수정 불필요 | — |
| **B-11** | **`headline_code`에 `rejected_events` 대응 코드가 없다** | 거부 N건인데 나머지가 정상이면 판정 배너가 `ALL_CLEAR`로 뜬다. **첫 화면 한 줄이 거짓이 된다.** 리드가 `REJECTED_EVENTS` 신설 + **7종(→8종) 우선순위 계약 명시**를 James에게 지시 | **James — 미해결** |
| ~~B-6~~ | ~~`dashboard/AGENTS.md` 소유자~~ | **판정됨 (리드 J-3, 2026-09-11) — 최초 작성은 Andrew(W5-C) 소유.** Timothy(W6)가 아니다. 디자인 측 제약 초안은 **[`dashboard-agents-design-constraints.md`](dashboard-agents-design-constraints.md)**, 격리 측은 James | — |
| ~~B-7~~ | ~~USP-1 대표 장면의 C1 증명 수단~~ | **판정됨 (리드 J-1) — ⑴ fixture + `표본 데이터` 배지 승인. ★ 조건 추가: fixture는 실제 파이프라인 산출물이어야 한다** (§2) | — |

> **B-4는 조용히 넘기기 쉬운 차단이다.** "생성 방법을 안내한다"는 `DB-013` [MUST]이고, 안내할 명령이 없으면 충족할 수 없다. **빈 문구를 넣고 충족으로 적지 않는다** — `docs/gate1_checklist.md`에 `BLOCKED`로 기록한다.

---

# 1. Andrew가 첫날 부딪힐 것 — 순서대로

## 1.1 토큰 파이프라인 (우선 — 나머지 전부의 전제)

`design-system/token-strategy.md` K-1~K-7. 요약:

```bash
# Ecommerce_Service 에서 복사할 4개 파일
scripts/design-tokens.mjs
scripts/tokens/resolve.mjs
scripts/tokens/render.mjs
scripts/tokens/verify.mjs          # ← 버리지 말 것. 15 시나리오가 복제본 동작을 고정한다
src/styles/design-rules.css        # ← 생성물이 아니다. 손으로 쓴 파일 (§4.1)
```

`package.json` 스크립트 (입·출력만 바꾼다. **스크립트 본문은 한 줄도 고치지 않는다**):
```json
"tokens:generate": "node scripts/design-tokens.mjs --input ../Plan/DESIGN.md --output src/styles/tokens.generated.css",
"tokens:check":    "node scripts/design-tokens.mjs --input ../Plan/DESIGN.md --output src/styles/tokens.generated.css --check",
"tokens:test":     "node scripts/tokens/verify.mjs",
"predev":  "npm run tokens:generate",
"prebuild":"npm run tokens:generate",
```

> **⚠ 검증 안 함 — 첫 확인 항목:** `--input ../Plan/DESIGN.md`가 의도대로 해석되는지 **실행해 보지 않았다.** `design-tokens.mjs`의 `root`는 `new URL("../", import.meta.url)` — 스크립트 파일 위치의 부모다. `dashboard/scripts/`에 두면 `root = dashboard/`이고 `../Plan`이 저장소 루트의 `Plan/`을 가리킬 것으로 **읽었다.** `verify.mjs`의 `root`는 `"../../"`이므로 **경로 깊이가 다르다** — 같이 확인할 것.

### 절대 빠뜨리지 말 것 — 빠지면 **조용히** 깨진다

| # | 항목 | 빠지면 |
|---|---|---|
| 1 | `pretendard` npm 의존 | — |
| 2 | `layout.tsx`의 `localFont` 설정 | — |
| 3 | CSS 변수명 **`--font-pretendard`** | 1·2·3 중 하나라도 빠지면 **화면이 깨지지 않고** fallback 체인이 작동해 시스템 글꼴로 렌더된다. **실패가 보이지 않는다.** 육안 확인 필요 |
| 4 | `design-rules.css` | 그림자·포커스·레이어·모션이 사라진다. **`tokens:check`가 이 파일을 검사하지 않는다** (§4.1) |
| 5 | `adjustFontFallback: false` | 폴백 메트릭 보정이 Pretendard 로딩 전후 레이아웃을 흔든다 |

## 1.2 상태 토큰

`design-system/state-tokens.css`를 **`dashboard/src/styles/state-rules.css`로 옮긴다.** `tokens.generated.css` 다음에 import.

> **불변식: 새 hex 색값 0건.** 제안 파일에 `#` 리터럴이 0건임을 확인했다 (`grep -c '#[0-9A-Fa-f]\{3,6\}'` → 0). 구현본도 0건을 유지한다 — `missing-state-spec.md` §9 검사 **C-8**.

## 1.3 컴포넌트 7개

`design-system/components.md`. **`MetricCell`부터 만든다** — 모든 숫자가 이것을 거치고, 자기 검사 3건이 여기 있다.

---

# 2. ★ USP-1 대표 장면 — 리드 판정 완료 (J-1 · 2026-09-11)

> ### 판정: ⑴ fixture + `표본 데이터` 배지. **추가 조건 — fixture는 손으로 쓴 게시물 JSON이 아니라 실제 측정 계층 파이프라인을 통과한 산출물이어야 한다.**
>
> | 방식 | 스크린샷이 증명하는 것 |
> |---|---|
> | 손으로 쓴 게시물 JSON → 화면 | **화면이 그 JSON을 그릴 수 있다**는 것뿐 |
> | **합성 이벤트 → 실제 Sink → 실제 게시 → 화면** | **파이프라인이 실제로 계산 불가를 판정하고 게시한다**는 것 |
>
> **USP-1은 "화면이 회색 칩을 그릴 수 있다"가 아니라 "측정 계층이 계산 불가를 계산 불가로 말한다"다. 후자만 그것을 증명한다.**
>
> - 합성인 것은 **입력**이고 **파이프라인은 진짜**다 → 배지 문구 `표본 데이터 — 실측이 아닙니다`가 정확하다(파이프라인이 가짜라는 뜻이 아니라 **입력이 합성**이라는 뜻)
> - **게시물 JSON을 손으로 써서 스크린샷을 찍는 지름길을 쓰지 않는다.** 그렇게 찍은 스크린샷은 US-13 인수조건을 충족하지 않는다
> - 필요한 합성 입력: **`unit_cost`가 없는 `purchase` 이벤트 1건 이상.** 그러면 `revenue`는 `ok`, `contribution_profit`은 `unavailable`+`NO_COST_BASIS`가 **파이프라인에서** 나온다 (계약 예시가 이미 그 형태를 보여준다)
> - **`표본 데이터` 배지는 타협 불가다**
>
> → `dashboard-agents-design-constraints.md` §6에 Andrew가 읽을 형태로 적었다.

## 2.1 판정 전 검토 기록 *(참고용)*

`usp.md` §2.2가 USP-1을 **C1에서 전부 증명**한다고 확정했다. `user-stories.md` US-13 인수조건 3은 *"커머스 실측분의 `contribution_profit`이 계산 불가로 표시되고, **같은 화면에서 `revenue`는 값으로 표시**된다"* 를 요구한다.

**문제:** 2026-09-11 현재 커머스는 이벤트를 0건 기록한다. 따라서 `revenue`도 `—`(`NO_SOURCE_EVENT`)이고 **대표 장면이 성립하지 않는다.**

| 선택지 | 내용 | 위험 |
|---|---|---|
| **⑴ (추천) 고정 fixture** | `unit_cost` 없는 주문 1건이 든 테스트 게시물로 렌더 | 실데이터가 아니다. **`표본 데이터 — 실측이 아닙니다` 배지가 타협 불가** |
| ⑵ `Ecommerce #28` 완료까지 대기 | 실측 주문으로 증명 | C1 범위 밖 의존. `usp.md` 확정과 충돌 |
| ⑶ 빈 Sink 전부 계산 불가로 대체 | — | US-13 인수조건 3 **미충족** |

**⑴을 추천한다.** 목업의 `MetricsView` 아트보드가 ⑴을 구현한 것이며 배지가 붙어 있다.
**배지 없이 fixture를 렌더하는 것은 이 설계 전체가 금지하는 행위다** — 표본을 실측처럼 보이게 하는 것.

---

# 3. W6 검증 항목 — Matthias

**내가 실행한 검증은 없다.** `dashboard/`가 존재하지 않으므로 전부 `BLOCKED — 대시보드 미구현`이다.

| # | 검사 가능한 명제 | 방법 |
|---|---|---|
| C-1 | 계산 불가 셀에 문자 `0`이 없다 | `state != available` 셀 텍스트에 `/\d/` 0건 |
| C-2 | `—`의 font-size가 같은 카드의 값과 같다 | 계산된 스타일 대조 (V-1) |
| C-3 | 모든 `available` 값에 기준 문구가 있다 | DOM 검사 (V-2·V-3) |
| C-4 | 모든 계산 불가 셀에 사유 코드가 **상시** 보인다 | 호버 없이 텍스트 추출 (V-9) |
| C-5 | `blocked`·`not_run`·`violation`에 조치 줄이 있다 | DOM 검사 (V-8) |
| C-6 | 16종 `event_type`이 전부 렌더링된다 | 행 수 = 16 (V-0) |
| C-7 | 증감 화살표·스파크라인 0건 | 컴포넌트 검색 (V-11) |
| C-8 | `state-rules.css`에 hex 리터럴 0건 | `grep` |
| **C-13** | **`pass` ∧ `examined_rows==0`이 초록으로 그려지지 않는다** | 규칙 **V-12** — `success` 토큰·`✓` 검색 0건 |
| **C-14** | **`gate_result: incomplete`에 `success` 토큰이 없다** | 동일 |
| **C-15** | **V2 거부 샘플에 값이 렌더링되지 않는다** | 보안 — `offending_fields` 이름만. 값 문자열 0건 |
| **C-16** | **`notices[]`가 전부 렌더링되고 접히지 않는다** | 계약 R-8 · V-0 |
| **C-17** | 시각 상태가 `(status, reason_code)` 순수 매핑이다 | 화면에 판정 분기 0건 (`DB-012`) |
| C-9 | **빈 게시물로 렌더 시 예외 없이 전부 계산 불가** | 빈 Sink fixture 스냅샷 |
| C-10 | 대비 8조합 기준 통과 | 토큰값에서 계산 |
| C-11 | 상태 칩에 글리프가 전부 있다 | `blocked`/`provisional` 색 충돌 대비 (L-2) |
| C-12 | 출처 2열 순서가 커머스 먼저다 | 정렬·적층 후에도 유지 (S-1) |

> **C-9가 가장 중요하다.** 빈 Sink 스냅샷은 **USP-1 자체의 회귀 테스트**다. 누군가 "화면이 비어 보인다"는 이유로 0을 채우면 깨진다. `tests/test_sink.py:198-203`과 짝이 되는 화면 쪽 검사다.
>
> **C-2·C-11은 자동화가 어렵다.** 육안 또는 스크린샷 비교가 필요하다. **어려운 것을 통과로 적지 않는다.**

## 3.1 Thomas(리뷰)가 최우선 탐색할 것

task-graph §6: *"**창구 중립성 위반**과 **결손 은폐(0 채우기)**를 최우선 탐색"*.

화면 쪽 결손 은폐는 셋이다. 0을 쓰는 것만이 아니다:

| 은폐 방식 | 탐지 |
|---|---|
| `0`으로 채운다 | C-1 |
| **`—`를 작게·흐리게 만든다** | C-2 — **0 채우기의 정중한 버전** |
| **결손 항목을 접거나 기본 필터로 감춘다** | C-6 · 접기 컴포넌트 검색 (V-0) |

---

# 4. Timothy(문서)에게

| # | 항목 |
|---|---|
| D-1 | ~~`dashboard/AGENTS.md` 소유자~~ → **Andrew(W5-C) 소유로 판정됨.** Timothy는 **W6에서 정본을 인수·검수**한다. 디자인 측 제약 초안은 `dashboard-agents-design-constraints.md` |
| D-2 | `design-rules.css`의 **본문 유래 값은 `tokens:check` 검증 범위 밖**임을 명시. *"정본 일치 검증 파이프라인이 동작한다"* 는 **frontmatter YAML 범위에서만 정확하다** |
| D-3 | CI 토큰 검사 미도입 사유 — `Plan` private 서브모듈 체크아웃 인증 필요 (사용자 결정 Z-1) |
| D-4 | `docs/gate1_checklist.md`에 화면 쪽 `BLOCKED` 기록 — `DB-013` 빈 상태 안내(B-4) · 격리 검사 `dashboard/` 미포함(`usp.md` C-3) |

---

# 5. 목업 5종 — 무엇을 보라는 것인가

| 아트보드 | 무엇 | 유의 |
|---|---|---|
| **V1 수집 상태** | 첫 화면 전체. 판정 배너 · 출처 2열 · 타임라인 · 결손→영향 | **2026-09-11 실제 상태**(전부 미수신)를 그렸다. 비어 보이는 것이 정상 동작이다 |
| **V4 지표 상태** | ★ USP-1 대표 장면 + 상태 8종이 실제로 섞인 표 | `표본 데이터` 배지 확인. `violation` 행(`average_order_value`)이 **화면의 자기 검사**를 보여준다 |
| **V1 하단 event_type 16종** | 16행 전부 + 거부 요약 | `0 / 16`(측정된 0) vs `—`(미수신)의 차이 |
| **레퍼런스 상태 어휘 8종** | 금지 1호 대조 · V-1 대조 · 8종 표 · 대비 실측 | **Andrew의 구현 기준표** |
| **레퍼런스 연결 상태 3종** | 미연결 / 수신 중 / 정지 | 뒤 둘은 **C1에서 검증 불가** — 구현하되 통과로 적지 않는다 |

## 5.1 목업의 한계 — 실물과 다른 점

| # | 한계 |
|---|---|
| H-1 | **정적 목업이다.** 상호작용·라우팅·파일 읽기가 없다. 상태 어휘와 배치의 명세일 뿐이다 |
| H-2 | **Pretendard가 목업에서 로딩되지 않을 수 있다.** 아트보드 CSP는 Google Fonts만 허용하고 Pretendard는 거기 없다. 글꼴 스택은 실제 생성 CSS와 **동일하게**(`Pretendard, -apple-system, …`) 넣었으므로 로컬에 Pretendard가 있으면 보이고 없으면 폴백된다. **자간·행간 판정에 목업을 쓰지 말 것** |
| H-3 | 숫자는 **전부 표본값**이다. `38,400원`·`1,204건`·`18.4%` 등은 배치 확인용이며 실측이 아니다 |
| H-4 | 반응형(1024px 미만 적층·200% 확대)은 목업에서 확인하지 않았다. `Plan/DESIGN.md` 규정을 `ux-flow-map.md` §3.2에 옮겨 적었을 뿐이다 |
| H-5 | 결과 화면군 8개의 **내부** 화면은 설계하지 않았다. 자리만 잡았다 |

---

# 6. 쓰기 범위 준수 증명

```
$ git status --porcelain                              # AI_ROI
?? .agent-team/                                       # 작업 디렉터리만

$ cd /Users/otter/72offsuit/Ecommerce_Service && git status --porcelain
(빈 출력)                                              # 변경 0건
```

- **`Ecommerce_Service` 변경 0건.** 실행한 것은 `tokens:check`(읽기) · `tokens:test`(tmpdir) 둘뿐이다. `tokens:generate`는 실행하지 않았다
- **`Plan/` 변경 0건.** 읽기만
- **제품 코드(`src/`·`tests/`·`config/`·`.github/`) 변경 0건**
- **GitHub 이슈 생성·수정 0건** (L1)
- **git commit·push 0건**
