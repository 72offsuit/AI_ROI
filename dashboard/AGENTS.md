# dashboard/ — 에이전트 지침

측정 계층(`src/measurement/`)이 `results/` 에 게시한 산출물을 **읽어서 표시만** 하는 Next.js 앱이다.
포트 **3001** (3000 은 `Ecommerce_Service` 점유). API 서버를 두지 않는다 — 파일을 직접 읽는다.

> ## 이 디렉터리가 지키는 것 한 줄
> **값이 없다는 사실을 값이 있는 것과 같은 크기로 쓴다.**
> **0 으로 채우는 것과 회색으로 흐리는 것은 같은 실패다** — 둘 다 읽는 사람이 부재를 인지하지 못하게 한다.
> 이 저장소의 USP-1 이 이 한 줄에 걸려 있다.

---

## 0. 화면군 둘

| 화면군 | 산출 주체 | 상태 |
|---|---|---|
| **관측** `(observability)/` | `src/measurement/` | **C1 에서 구현** — 7화면 |
| **결과** `(results)/` | `src/decision/` | **이후 사이클.** 사이드바에 비활성으로 노출하되 **라우트 파일을 만들지 않는다.** 빈 디렉터리는 "구현했다"로 읽힌다 |

---

## 1. 격리·데이터 경로 (`DB-014`)

| # | 규칙 |
|---|---|
| **DG-1** | **읽기 허용은 `results/` 와 `data/processed/` 뿐이다.** `data/raw/` · `data/hidden/` · `data/ground_truth/` 는 **읽지 않는다** |
| **DG-2** | **`src/**` 를 import 하지 않는다.** `src/simulator/` 는 **이름으로도 참조하지 않는다** |
| **DG-3** | **계산하지 않는다.** 합계·비율·분류·지표 파생을 만들지 않는다. **표시 순서 정렬과 필터는 허용.** ★ **단순 합산도 계산이다** |
| **DG-4** | **출처(커머스/시뮬레이터)를 재분류하지 않는다.** 게시물의 `by_source` 를 그대로 쓴다 |
| **DG-5** | **`status !== "ok"` 인 값을 숫자로 그리지 않는다.** 0 과 다른 시각 상태 + 사유를 표시한다. **`not_run` 을 통과로 그리지 않는다** |
| **DG-6** | **파일 읽기는 `src/lib/artifacts/` 안에서만.** 다른 곳에서 `node:fs` 를 쓰지 않는다 |
| **DG-7** | **`src/styles/tokens.generated.css` 를 직접 수정하지 않는다.** 토큰 정본은 `Plan/DESIGN.md` 이고 `Plan/` 은 이 저장소에서 수정하지 않는다. `scripts/` 는 `Ecommerce_Service` 에서 **이식**한 것이며 **로직 변경 시 양쪽을 함께 본다** |
| **DG-8** | **`Ecommerce_Service` 를 편집하지 않는다.** 읽기 전용 조사만 |

> ⚠ **`tests/test_isolation.py` 는 `src/` 하위 `.py` 만 본다. `dashboard/` 를 한 줄도 검사하지 않는다.**
> `tests/test_dashboard_isolation.py` 도입은 **결정 D-22 (W6 Matthias + 사용자 승인)** 이며 **W5 에서 만들지 않는다.**
> 그때까지 DG-1~DG-8 은 **세 겹**으로 지켜진다 — 사람의 규율 · `src/lib/artifacts/paths.ts` 의 런타임 화이트리스트 · `npm run check:isolation`.
> **검사하지 않은 것을 통과로 적지 않는다.**
>
> ★ 세 번째 겹은 이슈 `#64`(보안 F1, CVSS 6.5)로 생겼다. 그전까지 화이트리스트는 **문자열만** 보았고, `results/` 안의 심볼릭 링크가 `data/hidden/` 을 가리키면 **여덟 검사 중 일곱을 통과하고 파일이 읽혔다**(실제로 재현했다). `resolveArtifactPath()` 가 이제 realpath 를 재검증하고, `scripts/check-path-isolation.mjs` 가 벡터 10종을 **디스크에 만들어 실행**한다 — 소스에 `realpathSync` 가 있는지 보는 것으로는 그것이 효력 없는 자리에 있어도 통과한다.
>
> **`check:isolation` 은 `D-22` 가 아니다.** `D-22` 는 파이썬 격리 검사를 `dashboard/` 까지 넓히는 것이고 여전히 열려 있다 — 이 스크립트는 `paths.ts` 한 함수만 본다. `src/**` import 금지(DG-2)나 `node:fs` 사용처 제한(DG-6)은 **아직 사람이 본다.**

---

## 2. ★ 코드 수준 함정 — 이 프로젝트 최대 위험

**계약은 `status != "ok"` 이면 `value` 를 항상 `null` 로 준다**(스키마가 강제). **그 `null` 을 JS 관용구가 조용히 0 으로 바꾼다.**

### DG-9 · 금지 패턴 — 전부 0 채우기다

```ts
value ?? 0                      // ✕ null → 0
value || 0                      // ✕ null·0·"" 전부 → 0
Number(value)                   // ✕ Number(null) === 0
(value ?? 0).toLocaleString()   // ✕ "0"
value?.toLocaleString() ?? '0'  // ✕ "0"
counts[name] || 0               // ✕ 키 부재를 0으로 둔갑
parseFloat(value) || 0          // ✕
value.toFixed(1)                // ✕ null 에서 throw → 막으려고 위 패턴으로 도망간다
filter(d => d.value > 0)        // ✕ 0건 항목이 조용히 사라진다
```

> **`(null).toLocaleString()` 이 예외를 던지기 때문에 구현자는 예외를 막으려고 `?? 0` 을 쓴다. 그 순간 USP-1 이 깨진다.**
> **예외를 막는 올바른 방법은 분기지 기본값이 아니다.**

### 올바른 형태

```ts
// 게시물이 포맷까지 끝낸 문자열을 준다. 화면은 숫자를 포맷하지 않는다 (DG-3)
const EM_DASH = '—';                       // U+2014. hyphen(-) 아니다
const display = m.status === 'ok' ? m.value_formatted : EM_DASH;
```

| 규칙 | 내용 |
|---|---|
| **`status` 로 분기한다** | `value` 의 falsy 여부로 분기하지 않는다. **`value === 0` 은 정직한 값이다.** `0` 과 `null` 을 같은 조건으로 묶는 **모든 코드가 버그다** |
| **`value` 를 숫자로 받아 포맷하지 않는다** | 통화·소수·천단위 결정은 계산이다(DG-3). `toLocaleString()` 은 환경마다 결과가 달라 재현성도 깨진다 |
| **키 부재는 `0` 이 아니라 계약 위반이다** | 계약이 `minProperties: 16`(event_type) · 22 고정(필드) · `minItems: 9`(Lock) 로 키 존재를 보장한다 |

**검사:**
```bash
grep -rn '?? 0\|\|\| 0\|Number(\|parseFloat(\|toFixed(\|toLocaleString(' src   # 0건
```

### ★ `value_formatted` 는 2026-09-11 현재 계약에 없다

M-06 §4.16 이 추가한다. **그 전까지 `ok`·`unconfirmed` 셀은 `계약 준비 중` 으로 렌더된다** (`src/lib/format/metric.ts`).
**`m.value` 를 직접 포맷해 이 자리를 메우지 않는다** — 그 순간 DG-3 을 어기고 `?? 0` 이 따라온다.

---

## 3. 시각 규칙 — 전부 "좋은 디자인처럼 느껴지는" 것들

| # | 규칙 | 왜 어기고 싶어지나 |
|---|---|---|
| **DG-10** | **`—` 를 작게·흐리게 만들지 않는다** — 대체한 값과 **같은 타이포그래피 토큰·같은 크기·같은 자리**. **`text-muted` 금지**(5.33:1), **`text-secondary`**(7.82:1) 사용 | *"화면이 시끄럽다 / 결손은 부차적이니 작게"* — **가장 자주 깨질 규칙** |
| **DG-11** | **결손을 숨기지·접지·기본 필터하지 않는다** — accordion · "더 보기" · `<details>` 기본 닫힘 · `status === 'ok'` 기본 필터 · **건수 내림차순 기본 정렬** 금지. 기본은 **고정 순서** (예외: `/coverage` 충족률 오름차순 — 결손이 위) | *"계산 불가 19행은 너무 길다"* — ★ **UX 개선처럼 보이기 때문에 가장 위험하다** |
| **DG-12** | **상태 글리프를 생략하지 않는다** — `gap`·`env_blocked`·`provisional` 이 **같은 `warning` 색**이다. **모든 글리프에 `aria-label`.** ★ 글리프 리터럴은 **`src/components/StateChip.tsx` 한 파일에만** 둔다 | *"색으로 충분하다 / 아이콘이 번잡하다"* |
| **DG-13** | **기준(basis)을 생략하지 않는다** — 모든 `ok` 값은 기준을 동반한다. **기준의 유무가 "측정됨"의 유일한 증거다.** 기준 없는 값은 `계약 위반` 칩 | *"카드가 길어진다"* |
| **DG-14** | **사유를 호버·툴팁·접기에 숨기지 않는다** — 사유 코드·`reason_detail`·기준·영향·조치 **전부 상시 표시** | *"인라인이 지저분하다"* — ★ **호버 상태는 스크린샷에 남지 않는다** |
| **DG-15** | **증감·델타·스파크라인을 만들지 않는다** — `↑`·`↓`·`+12%` 렌더 금지. **슬롯도 두지 않는다** (빈 증감 슬롯은 "변화 없음(0%)"으로 읽힌다) | *"대시보드엔 전기 대비 증감이 있어야"* — **비교 기준이 없다** |
| **DG-16** | **"전체" 히어로 지표를 만들지 않는다** — 계층 1·2 KPI 에 `combined` 가 **스키마 수준에서 금지**다. 항상 **출처 2열**(왼쪽 커머스 `◼ 실측` / 오른쪽 시뮬레이터 `◇ 생성`, **순서 불변**) | *"대시보드라면 큰 숫자가 하나 있어야"* |
| **DG-17** | **새 색값을 도입하지 않는다** — `dashboard/src` 에 **hex 리터럴 0건**. 상태 색은 전부 `--ds-*` 의 별칭(`src/styles/state-rules.css` 한 곳). `accent`·`brand-05`~`brand-09` 를 **상태에 쓰지 않는다** | *"필요한 색이 없어서"* → **별칭으로 해결하거나 멈추고 보고** |
| **DG-18** | **거부 레코드의 값을 렌더링하지 않는다** — `offending_fields`(**이름만**). `rejected.jsonl` 에는 Hidden Trait·τ 가 원문으로 남는다 | *"사유를 이해하려고"* |
| **DG-19** | **차트 함정** — 배열의 `null` 을 라이브러리가 **0 으로 플로팅**하거나 **선을 이어버린다**. `filter(d => d.value > 0)` 는 **0건 항목을 사라지게 한다**. **선 차트를 쓰지 않고 막대를 쓴다** — 결손 구간에서 이으면 없는 값을 만든다 | *"시계열이니까 / 차트를 깔끔하게"* |

**검사:**
```bash
grep -rn '#[0-9A-Fa-f]\{3,6\}' src                      # 0건 (DG-17)
grep -rn 'node:fs\|from "fs"' src | grep -v lib/artifacts # 0건 (DG-6)
```

---

## 4. 상태는 계약에서 **기계적으로 파생**된다

화면이 새로 판정하지 않는다. `(status, reason_code)` → 시각 상태는 **순수 매핑**이다(DG-3).
정본 구현: **`src/lib/format/state.ts`**. 검증: **`npm run check:state-map`**.

| 계약 `status` | `reason_code` | 시각 상태 | 글리프 | 값 슬롯 |
|---|---|---|---|---|
| `ok` | — | `available` | 없음 | **숫자** (측정된 0 포함) |
| `unconfirmed` | `PARAM_UNCONFIRMED` | `provisional` | **◐** | **숫자** + `params_used` |
| `unavailable` | `NEEDS_TWO_STRATEGIES`·`NEEDS_MODEL_OUTPUT`·`PRECONDITION_MISSING` | `planned` | **·** | `—` |
| `unavailable` | `NO_SOURCE_EVENT` | `unconnected` | **○** | `—` |
| `unavailable` | `NO_COST_BASIS`·`MISSING_FIELD` | `gap` | **⚠** | `—` |
| `blocked` | `BLOCKED` | `env_blocked` | **⊘** | `—` |
| `not_run` | `NOT_RUN` | `not_run` | **?** | **글자 `미실행`** |
| (화면 자기 검사) | — | `violation` | **✕** | `—` |

**★ `not_run` 의 값 슬롯은 `—` 가 아니라 글자 `미실행` 이다** — `—` 는 "없음", `미실행` 은 "모름"이다. **알지 못함이 결손보다 나쁘다.**
**★ `provisional` 은 값이 있다.** 칩에 `계산 불가` 를 쓰지 않는다 — 쓰면 쓸 수 있는 값을 못 쓰게 만든다.

### 검사 상태는 **별도 축이다**

`data_quality_report.checks[].status` 는 `metric_value.status` 와 **다른 enum** 이다. 위 표로 매핑하면 정의되지 않은 default 로 떨어진다.

| `checks[].status` | 시각 상태 | 글리프 | 값 슬롯 |
|---|---|---|---|
| `pass` | `ok` | ✓ | `통과` |
| `fail` | `violation` | ✕ | `실패 N건` |
| **`vacuous`** | **`unconnected`**(info) | ○ | **`공허한 통과 · 검사 대상 0행`** — ★ **`✓` 도 초록도 쓰지 않는다** |
| `not_run` | `not_run` | ? | **`미실행`** |
| `blocked` | `env_blocked` | ⊘ | `—` |

> ★ **`vacuous` 는 오늘 이 저장소의 정상 상태다**(`empty-sink` 18행 중 7행). **실패로 그려도 통과로 그려도 안 된다.**
> ★ **`status === "vacuous"` 로만 분기한다.** `pass ∧ examined_rows == 0` 은 **스키마가 금지해 영원히 거짓**이고, `examined_rows` 를 다시 읽는 것은 게시물이 한 판정을 화면이 반복하는 것이다(DG-3).
> ★ **`vacuous` 의 `reason_code` 는 신뢰하지 않는다** — 현재 픽스처가 전부 `NOT_RUN` 이라 "실행했는데 0행"과 "실행 안 함"이 섞여 있다. `status` 로 분기하고 `reason_detail` 을 문구로 쓴다.

---

## 5. 읽기 계층 — 읽는 쪽이 계약의 마지막 방어선이다

```
1. index.json 을 읽는다          └ 없다 → 게시 방법 안내 (빈 화면을 그리지 않는다)
2. contract_version 확인          └ 다르다 → 렌더링하지 않고 "계약 버전 불일치"
3. views[화면].artifact 의 path
4. run_id 가 index 와 같은지      └ 다르다 → "게시 진행 중 또는 불일치". ★ 값을 섞어 표시하지 않는다
5. 렌더링
```

**4단계가 원자성 계약의 읽는 쪽 절반이다.** `index.json` 은 게시 절차의 **마지막**에 쓰인다.

`src/lib/artifacts/read.ts` 가 읽은 직후 검사하는 불변식:

- `status ∈ {unavailable, blocked, not_run}` 인데 **`value !== null` 이면 던진다** ← ★ **0 채우기의 마지막 방어선**
- `status ∈ {ok, unconfirmed}` 인데 **값이 없으면 던진다**
- 계약이 보장한 봉투 키가 없으면 던진다

> **0 으로 채워진 값을 화면에 올리느니 화면이 비는 편이 낫다.**

**기준(basis) 부재는 던지지 않고 `계약 위반` 칩으로 화면에 드러낸다** — 숨기면 누락이 보이지 않는다.

---

## 6. 토큰 파이프라인

**토큰 값의 정본은 `Plan/DESIGN.md` 하나다.** 생성기 코드가 두 벌인 것은 **코드 중복이지 값 중복이 아니다**(PRD §69 가 금지한 것은 값 중복).

```bash
npm run tokens:generate   # Plan/DESIGN.md → src/styles/tokens.generated.css
npm run tokens:check      # 정본과 다르면 실패 (predev·prebuild 가 강제)
npm run tokens:test       # 생성기 자체 검증 — 15 scenarios
```

- `scripts/` 4개 파일은 `Ecommerce_Service` 에서 **이식**했다. 각 파일 머리에 **출처 커밋 SHA + sha256** 이 있다
- ★ **`scripts/tokens/verify.mjs` 는 원본과 한 줄이 다르다** (`Plan/DESIGN.md` → `../Plan/DESIGN.md`). 경로 깊이가 달라 그대로 두면 `ENOENT` 로 죽는다. 이유는 파일 머리 주석에 있다
- ★ **`src/styles/design-rules.css` 는 생성물이 아니다.** 손으로 쓴 파일이고 **`tokens:check` 검증 범위 밖**이다. 이 파일의 `rgb(0 0 0 / a)` 는 이식 원본에서 온 그림자·백드롭 알파이며 새 팔레트가 아니다

---

## 7. 만들지 않는 것

| 없음 | 근거 |
|---|---|
| 이벤트 행 목록·검색·필터 | **이벤트 브라우저는 C1 범위 밖.** 요구가 나오면 **멈추고 보고** |
| 기간 필터·날짜 선택 | 단일 시점 스냅샷. 기간 축이 없다 |
| 임계 입력·경보 토글 | **작동하지 않는 컨트롤을 두지 않는다** |
| 증감 배지·스파크라인·델타 | DG-15 |
| 다크 모드·OS 테마 | `Plan/DESIGN.md` 라이트 고정 |
| **빈 상태 일러스트** | ★ **이벤트 0건을 빈 상태로 대체하지 않는다.** 16종·지표·검사 목록을 **전부 그리고 전부 계산 불가로** 표시하는 것이 USP-1 증명이다 |
| 토스트·모달 | 가정 고지를 사라지게 만든다 |
| API 라우트·서버 액션 | 파일 읽기로 충분하다 |
| 자동 폴링·실시간 | 수동 새로고침. `force-dynamic` 이 매 요청 재읽기를 보장한다 |
| `tests/test_dashboard_isolation.py` | **W6 Matthias + 사용자 승인 (D-22)** |
| Node lint·build CI 게이트 | **없는 게이트를 만들지 않는다** |

---

## 8. 접근성

| 항목 | 명세 |
|---|---|
| 포커스 | `focus` 2px 외곽선 + 2px 간격 (`design-rules.css` `:focus-visible`). **호버와 독립** |
| 비활성 (사이드바 결과 항목) | `button-disabled` 색 + **실제 비활성 동작**(탭 순서 제외 · href 없음) + **사유 문구** |
| 전환 | 120ms ease-out. **`prefers-reduced-motion` 에서 0ms** |
| 글리프 | **전부 `aria-label`.** 아이콘 단독 전달 금지 |
| 200% 확대 | 칩이 **줄바꿈**한다. 고정 높이로 자르지 않는다 |
| 표 | 좁아지면 **해당 영역만** 가로 스크롤. **열을 숨기지 않는다** |
| 대비 | 8조합 전부 4.5:1 이상. ★ **`planned` 가 4.89:1 로 가장 빡빡하다 — 토큰 변경 시 재검산** |

---

## 9. 명령

```bash
npm run dev            # :3001 (predev 가 토큰을 생성한다)
npm run build          # prebuild 가 토큰을 생성한다
npm run tokens:check   # 토큰 드리프트 = 실패
npm run tokens:test    # 15 scenarios
npm run check:state-map # 상태 파생 + 0 채우기 불변식 25건
npm run lint

# 픽스처로 렌더 (원본을 수정하지 않고 실제 배치로 복사한다)
node scripts/stage-fixture.mjs empty-sink
AIROI_RESULTS_DIR=$PWD/.fixtures/empty-sink/results AIROI_FIXTURE_MODE=1 npm run dev
```

| 환경변수 | 뜻 |
|---|---|
| `AIROI_RESULTS_DIR` | 계약의 `results/` 가 가리킬 디렉터리. 기본값은 `dashboard/` 기준 `../results` |
| `AIROI_FIXTURE_MODE` | 비어 있지 않고 `0` 이 아니면 **`표본 데이터 — 실측이 아닙니다` 배지**를 띄운다. ★ **표본을 실측처럼 보이게 하지 않는다** |

---

## 10. git 권한 — **L1(제안만)**

commit·push 는 사용자가 **"커밋해"/"푸시해"** 를, 이슈·PR 은 **"이슈 만들어"/"PR 올려"** 를 명시한 뒤에만.
**승격을 스스로 추론하지 않는다.** `main` 직접 커밋 금지 · `git add -A` 금지(경로 명시) · `git add Plan` 금지.

**쓰기 허용 범위는 `dashboard/**` 뿐이다.** `src/**` · `config/**` · `tests/**` · `requirements*.txt` · 루트 `.gitignore` · `Plan/**` · `Ecommerce_Service` 는 **건드리지 않는다.**
검사: `python3 ../.agent-team/04-architecture/tools/check_ownership.py`

## 11. 정직성

1. **미실행 검증을 통과로 표시하지 않는다.** 실행 불가는 `BLOCKED` 로 **이유와 함께**
2. **결함을 조용히 고치지 않는다.** 발견 → 기록 → 수정 → 재시험
3. **결손을 조용히 0 으로 채우지 않는다**
4. **존재하지 않는 명령을 문서·화면에 쓰지 않는다** — 빈 상태 안내가 실행 가능한 게시 명령을 주지 못하는 이유가 이것이다
