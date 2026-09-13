---
story_key: D-01
epic: GA형 관측 대시보드 (charter §3.1③)
issue: "(이슈 없음 — charter ③ 직접)"
title: 대시보드 앱 골격 — dashboard/ · 지침 파일 · 토큰 파이프라인 · 읽기 계층
status: done            # W5-C Andrew 2026-09-11 — AC-1~AC-7 전부 충족. 상세: .agent-team/08-impl-notes/frontend.md
owner: Andrew (W5-C)
phase: "—"
blocked_by: []
blocks: ["d-02"]
user_decisions_required: ["D-22", "D-23"]
source_hash: 5cf5ccb05350cf24
source_files: 23
---

# D-01 · 대시보드 앱 골격 (W5-C)

> **이 파일만 읽고 구현한다.** 인용에는 전부 `[Source: 경로#절]` 을 붙였다.

---

# 0. 작업 전 — 매번 확인하는 3줄 *(task-graph §3 T3.2)*

| # | 절대 제약 | 어기면 |
|---|---|---|
| **①** | **git·이슈 권한은 L1(제안만)이다.** commit·push 는 사용자가 **"커밋해"/"푸시해"** 를, 이슈 생성·수정·PR 은 **"이슈 만들어"/"PR 올려"** 를 명시한 뒤에만. **승격을 스스로 추론하지 않는다.** merge · Issue close · 브랜치 삭제 · `push --force` · `reset --hard` · `rebase` 는 **항상 개별 승인**. `main` 직접 커밋 금지 · `git add -A` 금지(경로 명시) · `git add Plan` 금지 | 사용자 결정을 대신한 것이 된다 |
| **②** | **`Ecommerce_Service` 파일 변경 0건.** 별도 저장소이고 사용자가 명시적으로 제외했다. **읽기는 허용**된다. 편집이 필요해지면 **멈추고 보고한다** | charter §5 위반 |
| **③** | **결손을 0 으로 채우지 않는다.** 명시적으로 기록하고 의존 지표는 **계산 불가로 표시**한다. **미실행 검증을 통과로 표시하지 않는다** — 실행 불가는 `BLOCKED` 로 **이유와 함께** | ★ **이 프로젝트의 USP-1 이 끝난다** |

`[Source: AGENTS.md#반드시-지킬-것]` · `[Source: docs/GIT_WORKFLOW.md#6]` · `[Source: .agent-team/00-plan/charter.md#6.1]` · `[Source: .agent-team/00-plan/task-graph.md#3 W3]`

---

# 1. 메타

| | |
|---|---|
| **대상** | charter §3.1③ — **소유 이슈가 없다** (`core-features.md` CF-7) |
| **담당** | Andrew · W5-C |
| **착수 조건** | ✅ **지금 착수 가능** (리드 판정 **D-28**) — 계약과 픽스처 2벌이 이미 있다 |
| **차단하는 것** | d-02 전체 |
| **커밋 type** | `feat` |

> ## ★ 확정 사항 — 뒤집지 않는다
> **A8 판정: 대시보드는 애플리케이션 하나다.** `dashboard/` · Next.js · `:3001` · **결과 파일 읽기(API 서버 없음)**.
> **화면군만 둘** — 관측(C1) / 결과(이후 사이클). 근거 전문은 `usp.md` §1.
> `[Source: .agent-team/03-service-planning/usp.md#1.2]`

> ## ★ 이 디렉터리가 지키는 것 한 줄
> **값이 없다는 사실을 값이 있는 것과 같은 크기로 쓴다.**
> **0 으로 채우는 것과 회색으로 흐리는 것은 같은 실패다** — 둘 다 읽는 사람이 부재를 인지하지 못하게 한다.
> **이 저장소의 USP-1 이 이 한 줄에 걸려 있다.**
> `[Source: .agent-team/07-design/dashboard-agents-design-constraints.md#0]`

---

# 2. 스토리

> **`P-팀`으로서 나는 대시보드가 `results/` 의 게시물만 읽고, 잘못된 값이 오면 그리지 않기를 원한다.**
> 왜냐하면 **0 으로 채워진 값을 화면에 올리느니 화면이 비는 편이 낫고**, 읽는 쪽이 계약을 검사하는 것이 게시 계약의 **마지막 방어선**이기 때문이다.
> `[Source: .agent-team/04-architecture/exceptions.md#9]`

---

# 3. 인수 조건 (AC)

## AC-1 · 앱 골격

- [ ] `dashboard/` 아래 Next.js 앱이 생성된다 — **App Router**
- [ ] 포트 **3001** (`DB-002` · 3000 은 커머스 점유)
- [ ] 라우트 그룹 `(observability)` 아래 6화면 자리 · **`(results)/` 디렉터리는 만들지 않는다**
- [ ] 루트 셸 — 사이드바 + 헤더 + `ProvenanceBar`
- [ ] **`export const dynamic = "force-dynamic"`** — 요청마다 다시 읽는다 (`DB-011`)
- [ ] `fetch` 캐시·ISR 을 쓰지 않는다

## AC-2 · 지침 파일 (리드 판정 D-6) ★

- [ ] **`dashboard/AGENTS.md` 최초 작성** — 디렉터리 생성과 **같은 작업 단위**
- [ ] **`dashboard/CLAUDE.md`** — **`@AGENTS.md` 한 줄.** 내용을 복제하지 않는다
- [ ] `AGENTS.md` 가 **DG-1 ~ DG-8 · 디자인 제약 8종을 전부 담는다** (§4.5)

## AC-3 · 토큰 파이프라인 (`ADR-0006`)

- [ ] 생성기 4개 파일을 `dashboard/scripts/` 로 **이식**한다
- [ ] `--input ../Plan/DESIGN.md --output src/styles/tokens.generated.css`
- [ ] `predev` · `prebuild` 에 연결
- [ ] `tokens:check` 가 드리프트를 **실패**로 만든다
- [ ] ★ **`verify.mjs` 의 9행을 고친다** (§4.4 — W3 가 실행으로 확인한 필수 수정)
- [ ] 이식 파일 머리에 **출처 커밋 SHA 주석**
- [ ] `tokens.generated.css` 를 **직접 수정하지 않는다** — `.gitignore` 대상 (Phillip 이 M-05 에서 넣는다)
- [ ] `design-rules.css` 를 함께 가져온다 — **생성물이 아니라 손으로 쓴 파일**

## AC-4 · 상태 토큰

- [ ] `dashboard/src/styles/state-rules.css` — `design-system/state-tokens.css` 를 옮긴다
- [ ] `tokens.generated.css` **다음에** import
- [ ] ★ **`dashboard/src` 에 hex 색 리터럴 0건** — `grep -rn '#[0-9A-Fa-f]\{3,6\}' dashboard/src` → 0
- [ ] `accent`·`brand-05`~`brand-09` 를 **상태에 쓰지 않는다**

## AC-5 · 읽기 계층 ★ (`DB-014` 를 코드로)

- [ ] **`src/lib/artifacts/` 밖에서 `node:fs` 를 쓰지 않는다**
- [ ] `paths.ts` — 허용 경로 화이트리스트. **경로 이탈이 예외가 된다**
- [ ] `read.ts` — `index.json` → 산출물 로딩 · **`run_id` 대조**
- [ ] `types.ts` — 게시 계약 v1 의 TypeScript 타입. **주석으로 정본을 가리킨다**
- [ ] 환경변수 `AIROI_RESULTS_DIR`

## AC-6 · 읽는 쪽 최소 불변식 검사 ★

- [ ] `contract_version` 이 다르면 **렌더링하지 않고** 불일치를 표시
- [ ] `run_id` 가 index 와 다르면 **값을 섞어 표시하지 않는다**
- [ ] ★ **`status !== "ok"` 인데 `value !== null` 이면 던진다** — 0 채우기의 마지막 방어선
- [ ] `status` 가 `ok`·`unconfirmed` 인데 `basis` 가 없으면 `계약 위반`
- [ ] `index.json` 이 없으면 **게시 방법을 안내한다.** 빈 화면을 그리지 않는다

## AC-7 · 회귀 없음

- [ ] `python3 -m unittest discover -s tests` — **기준선 46건 회귀 0** (Python 테스트를 건드리지 않으므로 당연하지만 확인한다)
- [ ] `python3 -m unittest tests.test_isolation -v` — 통과
- [ ] `python3 .agent-team/04-architecture/tools/check_ownership.py` — PASS
- [ ] `npm run tokens:check` — 통과
- [ ] `npm run tokens:test` — **15 scenarios passed**

---

# 4. 개발 컨텍스트 (`developer_context`)

## 4.1 ★★ 코드 수준 함정 — 이 사이클 최대 위험

**계약은 `status != "ok"` 이면 `value` 를 항상 `null` 로 준다**(스키마가 강제). **그 `null` 을 JS 관용구가 조용히 0 으로 바꾼다.**
**화면이 USP-1 을 어기는 가장 현실적인 경로가 이것이다.**

```ts
value ?? 0                      // ✕ null → 0
value || 0                      // ✕ null·0·"" 전부 → 0
Number(value)                   // ✕ Number(null) === 0
(value ?? 0).toLocaleString()   // ✕ "0"
value?.toLocaleString() ?? '0'  // ✕ "0"
counts[name] || 0               // ✕ 키 부재를 0으로 둔갑
parseFloat(value) || 0          // ✕
value.toFixed(1)                // ✕ null 에서 throw → 막으려고 위 패턴으로 도망간다
```

> **`(null).toLocaleString()` 이 예외를 던지기 때문에 구현자는 예외를 막으려고 `?? 0` 을 쓴다. 그 순간 USP-1 이 깨진다.**
> **예외를 막는 올바른 방법은 분기지 기본값이 아니다.**

**올바른 형태:**

```ts
// 게시물이 포맷까지 끝낸 문자열을 준다. 화면은 숫자를 포맷하지 않는다 (DB-012)
const EM_DASH = '—';                       // — U+2014. hyphen(-) 아니다
const display = m.status === 'ok' ? m.value_formatted : EM_DASH;
```

> ### ★★ `value_formatted` 는 **오늘 계약에 없다** — M-06 이 추가한다 (Thomas C-1)
> 실측: `common.schema.json` `$defs.metric_value` 는 **11종** 프로퍼티에 `additionalProperties: false` 이고 **`value_formatted` 가 없다.** 픽스처 14파일 grep **0건**.
> **위 코드를 지금 그대로 쓰면 모든 `ok` 지표가 `undefined` 다.** 그러면 구현자는 `m.value.toLocaleString()` 로 가고, `null` 예외를 막으려 **`?? 0`** 을 쓴다 — **이 절이 경고한 바로 그 경로를 이 절이 연다.**
>
> **→ M-06 §4.16 이 계약에 `value_formatted` 를 추가한다** (`ok`·`unconfirmed` 필수 / 계산 불가 금지 — `basis` 와 같은 패턴).
> **M-06 이 끝나기 전에는 이 코드를 쓸 수 없다.** 그 전에 화면을 만들어야 하면 **숫자를 그리지 말고 `계약 준비 중` 으로 두거나 M-06 을 기다린다.**
> ★ **`m.value` 를 직접 포맷하지 않는다.** 통화·소수·천단위 결정은 계산이고(`DB-012`) 그 순간 `?? 0` 이 따라온다.

> #### ★ 누가 포맷하는지 정해졌다 — **`contracts.py` 직렬화 시점** (리드 판정 2026-09-11)
> **화면도, 계산층(`kpi.py`·`economics.py`)도 아니다.** 게시물을 직렬화하는 한 자리에서 `unit` + `value` 로 만든다.
> **`unit` 별 규칙 8종이 M-06 §4.16.1 에 정본으로 있다:**
>
> | `unit` | 예 | | `unit` | 예 |
> |---|---|---|---|---|
> | `krw` | `38,400원` | | `ratio` | `18.3%` **(×100 을 화면이 다시 하지 않는다)** |
> | `krw_per_customer` | `2,130원/인` | | `percentage_point` | `+3.2%p` **(부호 유지)** |
> | `count` | `1,204건` | | `days` | `42일` |
> | `text` | 그대로 | | `datetime` | `2026-09-18 13:58` (KST) |
>
> **→ 화면은 이 문자열을 그대로 출력한다.** `toLocaleString()` 을 부르지 않는다 — 환경마다 결과가 달라 재현성이 깨진다.
> **`한계` 칩은 `limit_note`(선택 필드 · M-06 §4.17)를 읽는다.** C1 에서 실제로 채워지는 지표는 **`campaign_response_count` 하나**다 (M-04 AC-4b).

| 규칙 | 내용 |
|---|---|
| **`status` 로 분기한다.** `value` 의 falsy 여부로 분기하지 않는다 | **`value === 0` 은 정직한 값이다.** `0` 과 `null` 을 같은 조건으로 묶는 **모든 코드가 버그다** |
| **`value` 를 숫자로 받아 포맷하지 않는다** | 통화·소수·천단위 결정은 계산이다(`DB-012`) |
| **키 부재는 `0` 이 아니라 계약 위반이다** | 계약이 `minProperties: 16`·22 고정·`minItems: 9` 로 키 존재를 보장한다 |

`[Source: .agent-team/07-design/dashboard-agents-design-constraints.md#1]`

## 4.2 디렉터리 구조

```text
dashboard/
├── AGENTS.md · CLAUDE.md        ★ 디렉터리 생성과 같은 작업 단위 (리드 판정 D-6)
├── package.json · package-lock.json     ← package-lock 을 커밋한다
├── next.config.ts
├── postcss.config.mjs
├── tsconfig.json
├── scripts/                     디자인 토큰 생성기 (Ecommerce_Service 에서 이식)
│   ├── design-tokens.mjs
│   └── tokens/  render.mjs · resolve.mjs · verify.mjs
└── src/
    ├── app/
    │   ├── layout.tsx           루트 셸 — 사이드바 + 헤더 + provenance 바
    │   ├── globals.css
    │   ├── page.tsx             /  — 인덱스. index.json 하나만 읽는다
    │   └── (observability)/     ★ C1 — 산출 주체 src/measurement/
    │       ├── ingestion/page.tsx     V1
    │       ├── rejections/page.tsx    V2
    │       ├── coverage/page.tsx      V3
    │       ├── kpi/page.tsx           V4  ★ USP-1 대표 장면
    │       ├── quality/page.tsx       V5
    │       ├── freeze/page.tsx        V6
    │       └── triggers/page.tsx      §71 — 정적. 게시물 없음
    ├── lib/
    │   ├── artifacts/           ★ 파일을 읽는 유일한 모듈
    │   │   ├── paths.ts         허용 경로 화이트리스트
    │   │   ├── read.ts          index → 산출물 로딩 · run_id 대조
    │   │   └── types.ts         게시 계약 v1 의 TypeScript 타입
    │   └── format/              값 표시 규칙 (0 vs 계산 불가)
    ├── components/              d-02 가 채운다
    └── styles/
        ├── tokens.generated.css   ★ 생성물 · .gitignore · 직접 수정 금지
        ├── design-rules.css       손으로 쓴 파일 (그림자·모션·레이어)
        └── state-rules.css        상태 토큰
```

> **`(results)/` 디렉터리를 C1 에서 만들지 않는다.** 빈 디렉터리를 만들면 "구현했다"로 읽힌다.
> **만드는 것은 라우트 명명 규약과 사이드바 자리뿐이다.**
> `[Source: .agent-team/04-architecture/dashboard-architecture.md#2]`

### 왜 Route Group 인가

**Next.js 의 `(그룹명)` 은 URL 에 나타나지 않는다.** `/(observability)/kpi` 의 URL 은 `/kpi` 다.

| 얻는 것 | |
|---|---|
| **산출 주체가 디렉터리로 갈린다** | `(observability)` = `src/measurement/` · `(results)` = `src/decision/` |
| **URL 이 깨끗하다** | 이후 사이클이 붙어도 `/kpi` 가 `/observability/kpi` 로 바뀌지 않는다 |
| 그룹별 레이아웃을 나중에 둘 수 있다 | 결과 화면군에 모델 버전 바가 필요해지면 `(results)/layout.tsx` 하나로 |
| 격리 검사가 경로로 대상을 좁힐 수 있다 | — |

## 4.3 ★ 버전 — 검색·실측으로 확인한 것만

**`Ecommerce_Service/package.json` 실측 (2026-09-11, 읽기 전용):**

| 항목 | 값 |
|---|---|
| `next` | **16.3.4** |
| `react` · `react-dom` | **19.2.8** |
| `tailwindcss` · `@tailwindcss/postcss` | **^4** |
| `typescript` | **^5** |
| `eslint` · `eslint-config-next` | **^9** · **16.3.4** |
| `js-yaml` (devDependency) | **4.3.2** — 토큰 생성기의 **유일한 의존** |
| `pretendard` | **1.3.9** |
| 스크립트 | `"lint": "eslint"` — **`next lint` 가 아니다** |

**WebSearch 확인 (2026-09-11):**
- Next.js **16.3.4** 가 2026-08-31 최신 stable. **Next 16 은 LTS**
- **Node 최소 20.9.0** (Node 18 미지원). 로컬은 **v24.15.0** — 충족
- **TypeScript 최소 5.1.0**
- Tailwind v4 `@theme inline` 이 Next 16 + React 19 와 **호환 확인**

> **결정 D-23: 커머스와 버전을 맞춘다.** *"토큰 파이프라인이 Tailwind 4 의 `@theme inline` 을 전제한다. 다른 메이저를 쓰면 이식한 생성기의 출력이 동작하지 않는다."*
> **단 정확한 lock 버전은 설치 시점에 해석해 기록한다. 이 문서에서 베끼지 않는다.**
> `[Source: .agent-team/04-architecture/dashboard-architecture.md#9 D-23]`

### ★ Next.js 16 breaking change — 실제로 밟는 것

| 변경 | 우리에게 |
|---|---|
| **비동기 Request API** — `params`·`searchParams`·`cookies()`·`headers()` 의 동기 호환 shim 이 **16에서 제거**됐다. 동기 접근은 **throw** 한다 | **C1 의 8화면은 전부 정적 경로라 해당 없다.** 동적 라우트를 추가하면 즉시 걸린다 |
| **`next lint` 제거** | ★ **`npm run lint` 를 `next lint` 로 쓰지 않는다.** 커머스처럼 `"lint": "eslint"`. **단 C1 은 Node lint 를 CI 에 도입하지 않는다** — 없는 게이트를 만들지 않는다 |
| **Turbopack 기본** — 커스텀 webpack 설정은 **무시된다** | 커스텀 webpack 설정을 쓰지 않는다 |
| parallel-route slot 에 `default.js` 필수 | parallel route 를 쓰지 않는다 |
| `revalidateTag` 두 번째 인자 필수 | **캐시를 쓰지 않는다** (`force-dynamic`). 해당 없음 |
| `next/image` 기본값 변경 | 관측 화면군에 이미지가 없다 |

## 4.4 ★★ 토큰 파이프라인 — W3 가 **실행으로 확인**했다

**이식 대상 5파일** (`Ecommerce_Service` HEAD `6b186d0f20a3d134389ef84b490d9a374c760e37`):

```
sha256  b17ab2e4122b8c467d45e537b57b81195eaec1cca2d3219d338f9e6baed29c66  scripts/design-tokens.mjs
sha256  c0ed6edc7970a93091c4a8ca49382181dde5a0abf0f6e256f29b2929e4ad3272  scripts/tokens/render.mjs
sha256  ce07d675c9b86b94d3d6debeabde0836bee684fa87a6aa79d3d47c7ab1f3ba2a  scripts/tokens/resolve.mjs
sha256  d777aa8812e0e32ddde75a2c903f8eeabcafaad6bb5008c3dddb4615a0a8c27f  scripts/tokens/verify.mjs
sha256  810415a43e2ac0f21a9597cfc14fb418be3ab8ffd0ad39a9ed6a26dadaeef1da  src/styles/design-rules.css
```

**이 SHA 를 이식 파일 머리 주석에 적는다** (`ADR-0006` 이 요구하는 출처 추적).

### ✅ 확인된 것 — `design-tokens.mjs` 는 그대로 동작한다

**W3 이 `dashboard/scripts/` 깊이를 재현해 실행했다:**

```bash
node scripts/design-tokens.mjs --input ../Plan/DESIGN.md --output src/styles/tokens.generated.css
# → 디자인 토큰 생성 완료 · exit 0 · 306줄 · dashboard 토큰 5건 포함

node scripts/design-tokens.mjs --input ../Plan/DESIGN.md --output src/styles/tokens.generated.css --check
# → 디자인 토큰이 정본과 일치합니다 · exit 0
```

**근거:** `const root = fileURLToPath(new URL("../", import.meta.url))` — 스크립트 파일 디렉터리의 부모.
`dashboard/scripts/design-tokens.mjs` → `root = dashboard/` → `../Plan/DESIGN.md` 가 **저장소 루트의 `Plan/`** 을 가리킨다. ✅

### ❌★★ `verify.mjs` 는 **그대로 이식하면 깨진다** — W3 발견 · **리드 재현 확인**

> **리드 지시 (2026-09-11):** *"`token-strategy.md` 의 '스크립트 본문을 한 줄도 고치지 않는다'가 **이 파일에 대해서는 틀립니다.** 재현 방법을 d-01 에 적으십시오. **Jonnathan 의 문장을 인용만 하고 넘어가면 Andrew 가 첫날 막힙니다.**"*
>
> **→ 아래는 인용이 아니라 실행 결과다. 그대로 따르면 된다.**

Jonnathan 이 **미검증으로 남긴 항목**이다 (*"`verify.mjs`의 `root`는 `"../../"`이므로 경로 깊이가 다르다 — 같이 확인할 것"*).
**확인했다. 실제로 깨진다.**

```js
const root = fileURLToPath(new URL('../../', import.meta.url));      // 8행
const source = await readFile(join(root, 'Plan/DESIGN.md'), 'utf8');  // 9행 ← 저장소 루트를 원한다
… spawnSync(…, [join(root, 'scripts/design-tokens.mjs'), …])          // 15행 ← dashboard/ 를 원한다
```

`dashboard/scripts/tokens/verify.mjs` 에 두면 `root = dashboard/` 가 되어:
- **15행은 맞다** (`dashboard/scripts/design-tokens.mjs`)
- **9행은 틀리다** — `dashboard/Plan/DESIGN.md` 를 찾는다

```
Error: ENOENT: no such file or directory,
  open '…/dashboard/Plan/DESIGN.md'
```

**→ `root` 를 바꾸면 15행이 깨진다. 9행만 고쳐야 한다:**

```js
const source = await readFile(join(root, '../Plan/DESIGN.md'), 'utf8');   // ← 한 줄
```

**W3 실행 확인:** `15 scenarios passed; failed input and --check preserved output.`

### 재현 방법 — 이식 전에 그대로 해 보십시오 (약 1분)

```bash
SP=$(mktemp -d)
mkdir -p "$SP/dashboard/scripts/tokens"
cp ../Ecommerce_Service/scripts/design-tokens.mjs      "$SP/dashboard/scripts/"
cp ../Ecommerce_Service/scripts/tokens/*.mjs           "$SP/dashboard/scripts/tokens/"
ln -s "$PWD/../Ecommerce_Service/node_modules"         "$SP/dashboard/node_modules"   # js-yaml
cp -R Plan "$SP/Plan"
cd "$SP/dashboard"

node scripts/design-tokens.mjs --input ../Plan/DESIGN.md --output src/styles/tokens.generated.css
#   → 디자인 토큰 생성 완료          ✅ 306줄
node scripts/design-tokens.mjs --input ../Plan/DESIGN.md --output src/styles/tokens.generated.css --check
#   → 디자인 토큰이 정본과 일치합니다  ✅
node scripts/tokens/verify.mjs
#   → ENOENT … '<SP>/dashboard/Plan/DESIGN.md'   ❌ 여기서 깨진다

sed -i '' "s|join(root, 'Plan/DESIGN.md')|join(root, '../Plan/DESIGN.md')|" scripts/tokens/verify.mjs
node scripts/tokens/verify.mjs
#   → 15 scenarios passed             ✅
```

**저장소와 `Ecommerce_Service` 를 건드리지 않는다** — 임시 디렉터리에서만 돈다.

> ### ⚠ 이것이 `token-strategy.md` K 규약과 충돌한다
> `token-strategy.md` §2.1 과 `design-handoff.md` §1.1 이 *"**스크립트 본문은 한 줄도 고치지 않는다**"* 라고 적었다.
> **`design-tokens.mjs`·`render.mjs`·`resolve.mjs` 3개는 그 말이 맞다.**
> **`verify.mjs` 1개는 틀리다.** 한 줄을 고치지 않으면 `tokens:test` 가 실행 자체를 못 한다.
>
> **→ 이 한 줄 수정을 작업으로 포함하고, 수정 사실을 파일 머리 주석에 남긴다.** 이식 원본과의 차이를 숨기지 않는다.

### 절대 빠뜨리지 말 것 — 빠지면 **조용히** 깨진다

| # | 항목 | 빠지면 |
|---|---|---|
| 1 | `pretendard` npm 의존 | — |
| 2 | `layout.tsx` 의 `localFont` 설정 | — |
| 3 | CSS 변수명 **`--font-pretendard`** | 1·2·3 중 하나라도 빠지면 **화면이 깨지지 않고** fallback 체인이 작동해 시스템 글꼴로 렌더된다. **실패가 보이지 않는다.** 육안 확인 필요 |
| 4 | `design-rules.css` | 그림자·포커스·레이어·모션이 사라진다. **`tokens:check` 가 이 파일을 검사하지 않는다** |
| 5 | `adjustFontFallback: false` | 폴백 메트릭 보정이 Pretendard 로딩 전후 레이아웃을 흔든다 |

`[Source: .agent-team/07-design/design-handoff.md#1.1]`

### `package.json` 스크립트

```jsonc
{
  "scripts": {
    "tokens:generate": "node scripts/design-tokens.mjs --input ../Plan/DESIGN.md --output src/styles/tokens.generated.css",
    "tokens:check":    "node scripts/design-tokens.mjs --input ../Plan/DESIGN.md --output src/styles/tokens.generated.css --check",
    "tokens:test":     "node scripts/tokens/verify.mjs",
    "predev":   "npm run tokens:generate",
    "prebuild": "npm run tokens:generate",
    "dev":      "next dev --port 3001",
    "lint":     "eslint"
  }
}
```

### 왜 이것이 "토큰 두 벌"이 아닌가

| | 정본이 몇 벌인가 |
|---|---|
| **토큰 값** (색·타이포·간격·반경·컴포넌트) | **한 벌.** `Plan/DESIGN.md` 하나 |
| 생성기 코드 | 두 벌 (약 199줄 × 2) — **코드 중복이지 값 중복이 아니다** |

**두 저장소의 `Plan` 서브모듈이 같은 커밋을 가리킨다** — 양쪽 `c46aee5eed00193b9331403645b8dbccaef52278` (W2·W3 실측).
**PRD §69 가 금지한 것은 "동일한 값을 UI 마다 새로 정의"하는 것이다. 값의 정본은 여전히 하나다.**
`[Source: .agent-team/04-architecture/adr/ADR-0006-token-generator-port.md]`

## 4.5 ★ `dashboard/AGENTS.md` 에 **반드시** 들어갈 것

**최초 작성은 Andrew 소유**이고 디렉터리 생성과 같은 작업 단위다 (리드 판정 D-6).
**자기 말로 쓰되 아래가 빠지면 안 된다.**

### 격리·데이터 경로 절 (James)

| # | 반드시 포함 | 근거 |
|---|---|---|
| **DG-1** | **읽기 허용은 `results/` 와 `data/processed/` 뿐이다.** `data/raw/`·`data/hidden/`·`data/ground_truth/` 는 읽지 않는다 | `DB-014` |
| **DG-2** | **`src/**` 를 import 하지 않는다.** `src/simulator/` 는 **이름으로도 참조하지 않는다** | `DB-014`·`ISO-001` |
| **DG-3** | **계산하지 않는다.** 합계·비율·분류·지표 파생을 만들지 않는다. **표시 순서 정렬과 필터는 허용** | `DB-012` |
| **DG-4** | **출처(커머스/시뮬레이터)를 재분류하지 않는다.** `by_source` 를 그대로 쓴다 | `MEA-002` |
| **DG-5** | **`status !== "ok"` 인 값을 숫자로 그리지 않는다.** 0 과 다른 시각 상태 + 사유. **`not_run` 을 통과로 그리지 않는다** | PRD §10.1·`MEA-003`·AGENTS.md |
| **DG-6** | **파일 읽기는 `src/lib/artifacts/` 안에서만.** 다른 곳에서 `node:fs` 를 쓰지 않는다 | §4.6 |
| **DG-7** | **`src/styles/tokens.generated.css` 를 직접 수정하지 않는다.** 토큰 값은 `Plan/DESIGN.md` 가 정본이고 `Plan/` 은 이 저장소에서 수정하지 않는다. `scripts/` 는 `Ecommerce_Service` 에서 이식한 것이며 **로직 변경 시 양쪽을 함께 본다** | PRD §69 |
| **DG-8** | **`Ecommerce_Service` 를 편집하지 않는다.** 읽기 전용 조사만 | charter §5 |

`[Source: .agent-team/04-architecture/dashboard-architecture.md#7]`

### 디자인 절 (Jonnathan) — **구현자가 어기기 쉬운 것만**

| # | 반드시 포함 |
|---|---|
| **DG-9** | ★ **금지 패턴** — `?? 0` · `\|\| 0` · `Number(value)` · `(value ?? 0).toLocaleString()` · `counts[k] \|\| 0` · `parseFloat(v) \|\| 0` · `value.toFixed(1)` (§4.1) |
| **DG-10** | **`—` 를 작게·흐리게 만들지 않는다** (규칙 V-1) — 대체한 값과 **같은 타이포그래피 토큰·같은 크기·같은 자리**. `text-muted` 금지 |
| **DG-11** | **결손을 숨기지·접지·기본 필터하지 않는다** (V-0) — accordion · "더 보기" · `status === 'ok'` 기본 필터 · 건수 내림차순 기본 정렬 금지 |
| **DG-12** | **상태 글리프를 생략하지 않는다** — `gap`·`env_blocked`·`provisional` 이 같은 `warning` 색이다. **모든 글리프에 `aria-label`** |
| **DG-13** | **기준(basis)을 생략하지 않는다** (V-2·V-3) |
| **DG-14** | **사유를 호버·툴팁에 숨기지 않는다** (V-9) — **호버 상태는 스크린샷에 남지 않는다** |
| **DG-15** | **증감·델타·스파크라인을 만들지 않는다** (V-11) — 비교 기준이 없다. **슬롯도 두지 않는다** |
| **DG-16** | **"전체" 히어로 지표를 만들지 않는다** — 계층 1·2 KPI 에 `combined` 가 **스키마 수준에서 금지**다 |
| **DG-17** | **새 색값을 도입하지 않는다** — `dashboard/src` 에 hex 리터럴 **0건** |
| **DG-18** | **거부 레코드의 값을 렌더링하지 않는다** — `offending_fields`(이름만) |
| **DG-19** | **차트 함정** — `null` 을 데이터 배열에 넣으면 라이브러리가 0 으로 플로팅하거나 선을 잇는다. `filter(d => d.value > 0)` 는 0건 항목을 사라지게 한다 |

`[Source: .agent-team/07-design/dashboard-agents-design-constraints.md#1, #2, #4, #5]`

**`dashboard/CLAUDE.md` 는 `@AGENTS.md` 한 줄이다.** 내용을 복제하지 않는다 (`ISO-004` · `test_claude_md_delegates_to_agents_md` 와 같은 규약).

> ⚠ **`tests/test_isolation.py` 의 `test_each_part_has_agent_guides` 는 `src/` 하위만 본다.** `dashboard/` 를 검사하지 않는다.
> **그래도 규약을 지킨다** — D-22 로 검사가 확장되면 즉시 대상이 된다.

## 4.6 ★ 파일 읽기를 한 곳으로 모은다 — `DB-014` 를 코드로

```ts
// lib/artifacts/paths.ts — 허용 경로 화이트리스트
const RESULTS_DIR   = process.env.AIROI_RESULTS_DIR ?? resolve(process.cwd(), "../results");
const PROCESSED_DIR = resolve(process.cwd(), "../data/processed");

// DB-014: 읽기 허용은 results/ 와 data/processed/ 뿐이다.
export function resolveArtifactPath(relative: string): string {
  const target = resolve(RESULTS_DIR, relative);
  if (!target.startsWith(RESULTS_DIR + sep) && target !== RESULTS_DIR) {
    throw new IsolationError(`허용 경로 밖 접근: ${relative}`);
  }
  return target;
}
```

| 이 배치가 주는 것 | |
|---|---|
| **경로 이탈이 예외가 된다** | `../../data/hidden/...` 같은 경로가 런타임에 던진다. **조용히 읽히지 않는다** |
| **격리 검사 대상이 좁아진다** | *"`lib/artifacts/` 밖에서 `node:fs` import 금지"* 한 줄로 강해진다 |
| 경로가 환경변수 하나 | `AIROI_RESULTS_DIR` |
| `data/processed/` 는 **상수만 두고 C1 에서 쓰지 않는다** | 산출물이 없다. **쓰지 않는 코드를 만들지 않는다** |

### 읽기 순서와 불일치 처리

```text
1. index.json 을 읽는다
   └ 없다 → EmptyState: 게시 방법 안내 (DB-013)
2. contract_version 확인
   └ 다르다 → 렌더링하지 않고 "계약 버전 불일치" 표시
3. views[해당 화면].artifact 의 path 를 읽는다
4. run_id 가 index 와 같은지 확인
   └ 다르다 → "게시 진행 중 또는 불일치". ★ 값을 섞어 표시하지 않는다
5. 렌더링
```

**4단계가 원자성 계약의 읽는 쪽 절반이다.**

### 타입은 계약에서 파생한다

`lib/artifacts/types.ts` 는 `docs/contracts/measurement-publish/v1/*.schema.json` 과 **일치해야 한다.**
**C1 에서는 손으로 쓰고 주석으로 정본을 가리킨다.** 자동 생성기는 의존성과 빌드 단계를 늘리고 계약이 7개 파일 규모라 이득이 없다.

> **불일치 위험은 실재한다.** 완화: `read.ts` 가 **읽은 직후 최소 불변식을 확인한다** — `contract_version`·`artifact`·`run_id` 존재, 그리고 ★ **`status !== "ok"` 인데 `value !== null` 이면 던진다.**
> **마지막 항목이 중요하다. 대시보드가 계약 위반을 발견하면 그리지 않고 실패한다.**
> **0 으로 채워진 값을 화면에 올리느니 화면이 비는 편이 낫다.**
> `[Source: .agent-team/04-architecture/dashboard-architecture.md#3.2]`

## 4.7 빈 상태 안내 — **확정 문구**

`DB-013` 이 *"결과 파일이 없는 초기 상태에서는 **생성 방법을 안내**한다"* 를 `[MUST]` 로 요구하고, `AGENTS.md` 는 *"존재하지 않는 명령을 쓰지 않는다"* 로 막는다.

**충돌이 아니다 — 시점의 문제다.**

| 상황 | 답 |
|---|---|
| **게시물이 있을 때** | `provenance.generated_by` 를 그대로 표시한다. **생성기가 자기 실행을 런타임에 기록**했으므로 지어낸 값이 아니다 |
| **게시물이 아예 없을 때** | 아래 확정 문구 |

```
○ 게시물이 없습니다
  측정 계층이 아직 산출물을 게시하지 않았습니다. 게시가 필요합니다.
  게시 명령은 W5-A 에서 신설됩니다 — 2026-09-11 현재 실행할 수 없습니다.
```

> **명령 문자열을 실행 가능한 것처럼 제시하지 않는다.** `AGENTS.md` 와 `DB-013` 을 동시에 만족하는 유일한 형태다.
> **`docs/gate1_checklist.md`(M-09)에 `DB-013` 부분 충족으로 남긴다** — 안내는 하지만 실행 가능한 명령을 주지는 못한다.
>
> **M-06 이 먼저 끝나면** `python3 -m src.measurement.publish --source data/raw --out results` 가 **실재한다.**
> **그때는 실재를 확인한 뒤 문구를 갱신한다. 확인 전에는 넣지 않는다.**
> `[Source: .agent-team/07-design/contract-reconciliation.md#3-⑥]`

## 4.8 ★ W-8 — 격리 검사가 `dashboard/` 를 보지 않는다

```python
# tests/test_isolation.py
def _iter_source_files():
    if not SRC_ROOT.is_dir():          # SRC_ROOT = REPO_ROOT / "src"
        return
    for path in sorted(SRC_ROOT.rglob("*.py")):   # ← .py 만, src/ 만
        yield path, _module_name(path)
```

**`dashboard/` 는 `src/` 밖이고 TypeScript 다. 현재 검사가 한 줄도 보지 않는다.**
`DB-014` 는 `dashboard/` 가 `data/hidden/`·`data/ground_truth/`·`src/simulator/` 에 접근하지 않을 것을 요구하지만 **강제하는 코드가 없다.**

> ### ★ Andrew 도 Phillip 도 `tests/test_dashboard_isolation.py` 를 만들지 않는다
> **격리 검사 체계를 건드리는 일**이고 `task-graph` §4 는 그 체계를 **W6 Matthias + 사용자 승인**에 두었다.
> **결정 D-22 다.**
>
> **C1 에서 도입하지 않기로 결정되면:**
> - `docs/gate1_checklist.md` 에 *"격리 검사는 `dashboard/` 를 보지 않는다"* 를 **명시적 한계**로 적는다 (M-09 인계)
> - `freeze_status.notices` 에 **`DASHBOARD_NOT_ISOLATION_CHECKED`**
> - **검사하지 않은 것을 통과로 적지 않는다**
>
> **→ 그 전까지 DG-1~DG-8 은 사람의 규율로만 지켜진다. 이 스토리는 §4.6 의 런타임 화이트리스트로 한 겹을 만든다.**
> `[Source: .agent-team/04-architecture/dashboard-architecture.md#6]`

## 4.9 함정

| # | 함정 | 왜 빠지나 | 대신 |
|---|---|---|---|
| **T-1** | `value ?? 0` | ★ **예외를 막으려고** | §4.1 — `status` 로 분기 |
| **T-2** | `verify.mjs` 를 그대로 이식 | *"한 줄도 고치지 않는다"* 를 읽어서 | §4.4 — **깨진다.** 9행 한 줄을 고친다 |
| **T-3** | `next lint` 를 `package.json` 에 | 관습 | §4.3 — **Next 16 에서 제거됐다** |
| **T-4** | `lib/artifacts/` 밖에서 `fs` | 페이지에서 바로 읽는 것이 짧다 | DG-6 — **격리 검사 대상이 넓어지고 경로 방어가 뚫린다** |
| **T-5** | `(results)/` 빈 디렉터리를 만든다 | 자리를 잡으려고 | §4.2 — **"구현했다"로 읽힌다** |
| **T-6** | `fetch` 캐시·ISR 사용 | 성능 | **게시물이 갱신됐는데 화면이 옛것을 보이면 그것도 "조용히 틀린 값"** |
| **T-7** | hex 색을 하나만 추가 | 필요한 색이 없어서 | DG-17 — **별칭으로 해결하거나 멈추고 보고** |
| **T-8** | `tokens.generated.css` 를 커밋 | 생성물인 줄 몰라서 | `.gitignore` 대상 (Phillip 이 넣는다). **`.gitignore` 를 Andrew 가 고치지 않는다** |
| **T-9** | `dashboard/AGENTS.md` 를 W6 로 미룬다 | 봉인 규칙을 읽어서 | ★ **리드 판정 D-6 — 최초 작성은 Andrew 소유** |
| **T-10** | `CLAUDE.md` 에 내용을 복제 | 자족적으로 만들려고 | **`@AGENTS.md` 한 줄** |
| **T-11** | `Ecommerce_Service` 를 고친다 | 이식하다 보면 | **읽기만.** `git status --porcelain` 빈 출력 |
| **T-12** | Pretendard 가 안 떠도 넘어간다 | **화면이 깨지지 않는다** | §4.4 — **실패가 보이지 않는다.** 육안 확인 |

---

# 5. 작업 분해 (Tasks)

## T1 · 앱 골격 (AC-1)

- [ ] `dashboard/` 에 Next.js 앱 생성 — App Router · TypeScript
- [ ] **버전을 커머스와 맞춘다** (§4.3) · **설치 후 해석된 lock 버전을 PR 에 기록**
- [ ] `package-lock.json` 커밋
- [ ] `dev` 포트 **3001**
- [ ] 라우트 그룹 `(observability)` + 8화면 자리 (페이지 본문은 d-02)
- [ ] `layout.tsx` 루트 셸
- [ ] `export const dynamic = "force-dynamic"`

## T2 · 지침 파일 (AC-2) ★

- [ ] `dashboard/AGENTS.md` — **DG-1 ~ DG-19 전부** (§4.5)
- [ ] `dashboard/CLAUDE.md` — `@AGENTS.md` 한 줄

## T3 · 토큰 파이프라인 (AC-3)

- [ ] 4개 스크립트 + `design-rules.css` 이식
- [ ] **파일 머리에 출처 주석** — 경로 + `Ecommerce_Service` 커밋 SHA + 각 파일 sha256 (§4.4)
- [ ] ★ **`verify.mjs` 9행 수정** + **수정 사실을 주석에 명시**
- [ ] `package.json` 스크립트 (§4.4)
- [ ] `pretendard` 의존 · `localFont` · `--font-pretendard` · `adjustFontFallback: false`
- [ ] `npm run tokens:generate` → `npm run tokens:check` → `npm run tokens:test` **전부 통과 확인**
- [ ] **Pretendard 가 실제로 렌더되는지 육안 확인**

## T4 · 상태 토큰 (AC-4)

- [ ] `design-system/state-tokens.css` → `dashboard/src/styles/state-rules.css`
- [ ] `globals.css` 에서 `tokens.generated.css` **다음에** import
- [ ] `grep -rn '#[0-9A-Fa-f]\{3,6\}' dashboard/src` → **0건 확인**

## T5 · 읽기 계층 (AC-5·6) ★

- [ ] `paths.ts` — 화이트리스트 · `IsolationError`
- [ ] `types.ts` — 계약 v1 타입. **주석으로 정본 경로**
- [ ] `read.ts` — 읽기 순서 5단계 (§4.6) · **최소 불변식 검사**
- [ ] `EmptyState` — §4.7 확정 문구
- [ ] **`lib/artifacts/` 밖에 `node:fs` import 0건 확인** (grep)

## T6 · 픽스처로 확인

> ### ★★ `commerce-connected` 픽스처는 **검사 7종만 담고 있고 이것은 결함이다** (리드 지시)
>
> **정본은 18종이다. 화면은 18종을 전제로 만든다.**
> **픽스처에 없는 11종이 실제 게시물에는 온다:**
>
> ```
> DQ-02 · DQ-03 · DQ-04 · DQ-05 · DQ-06 · DQ-11 · DQ-12 · DQ-13 · DQ-14 · DQ-15 · DQ-16
> ```
>
> 픽스처에 실린 7종: `DQ-01`·`DQ-02b`·`DQ-07`·`DQ-08`·`DQ-09`·`DQ-10`·`DQ-17`.
> **`empty-sink` 는 18종을 전부 담는다** — 그쪽이 정상이다.
>
> **원인:** `tools/make_examples_connected.py` 가 `checks` 7종과 `reported_checks: 6` 을 **소스에 하드코딩**했다(453·456행). **재생성해도 같은 7종이 나온다.**
>
> ★ **픽스처를 열어 7개를 세고 "7개구나" 하지 마십시오.** V5 `/quality` 는 **18행**을 그린다.
> `spec_coverage.reported_checks` 도 **믿지 않는다** — 픽스처는 `6` 인데 실린 것은 `7` 이다. **실제 게시물에서는 `len(checks)` 와 같다**(M-07 `Q-3`).

- [ ] `.agent-team/04-architecture/examples/empty-sink/` 를 `AIROI_RESULTS_DIR` 로 가리켜 실행
- [ ] `/` 가 `index.json` 하나만 읽고 렌더되는지
- [ ] `run_id` 를 일부러 어긋나게 만들어 **불일치가 표시되는지**
- [ ] `status: "unavailable"` + `value: 0` 인 가짜 파일로 **던지는지** (AC-6)

## T7 · 검증 (AC-7)

- [ ] `python3 -m unittest discover -s tests` — 회귀 0
- [ ] `python3 -m unittest tests.test_isolation -v`
- [ ] `python3 .agent-team/04-architecture/tools/check_ownership.py`
- [ ] `npm run tokens:check` · `npm run tokens:test`
- [ ] `git -C ../Ecommerce_Service status --porcelain` **빈 출력**

---

# 6. 파일 목록 (`file_list`)

## 6.1 이 스토리가 만드는 파일 — **전부 `dashboard/` 안**

```text
dashboard/AGENTS.md · CLAUDE.md
dashboard/package.json · package-lock.json · next.config.ts · postcss.config.mjs · tsconfig.json
dashboard/scripts/design-tokens.mjs
dashboard/scripts/tokens/{render,resolve,verify}.mjs
dashboard/src/app/layout.tsx · globals.css · page.tsx
dashboard/src/app/(observability)/{ingestion,rejections,coverage,kpi,quality,freeze,triggers}/page.tsx  ← 자리만
dashboard/src/lib/artifacts/{paths,read,types}.ts
dashboard/src/styles/{design-rules,state-rules}.css
```

**`dashboard/` 밖의 파일을 쓰지 않는다.**

## 6.2 절대 만지지 않는 파일

```
src/**                              ← 편집 금지 (계약 확인용 read-only 는 허용)
config/** · requirements*.txt · .gitignore   ← Phillip 소유
tests/**                            ← Phillip · 봉인
Plan/**                             ← 서브모듈. Plan/DESIGN.md 는 read-only 정본
../Ecommerce_Service/**             ← ★ 읽기만. 변경 0건
AGENTS.md · src/AGENTS.md · README.md
data/raw/** · data/hidden/** · data/ground_truth/**   ← ★ DB-014
.agent-team/04-architecture/schemas/** · examples/**  ← 읽기만
```

`[Source: .agent-team/04-architecture/build-plan.md#3.2]`

> ⚠ **`.gitignore` 에 `dashboard/node_modules/`·`dashboard/.next/`·`dashboard/src/styles/tokens.generated.css` 가 필요하다.**
> **Phillip 이 M-05 에서 넣는다. Andrew 가 `.gitignore` 를 고치지 않는다** — 두 사람이 같은 파일을 쓰면 겹침 0 증명이 깨진다.
> **M-05 가 아직 안 끝났으면 그 사실을 PR 에 적고 커밋 전에 확인한다.**

---

# 7. 테스트

## 7.1 실행 가능한 명령

```bash
# Python (기존)
python3 -m unittest discover -s tests
python3 -m unittest tests.test_isolation -v
python3 .agent-team/04-architecture/tools/check_ownership.py

# ★ 이 스토리가 신설하는 명령
cd dashboard
npm run tokens:generate
npm run tokens:check        # 정본과 일치
npm run tokens:test         # 15 scenarios passed
npm run dev                 # :3001
```

> **`npm run *` 은 2026-09-11 현재 존재하지 않는다.** 이 스토리가 만든다.
> **C1 은 Node lint·build 를 CI 에 도입하지 않는다** (`dependency-plan.md` §5) — **없는 게이트를 만들지 않는다.**

## 7.2 W6 검증 항목 — 미리 알아둔다

Matthias 가 검증할 명제다. **구현이 이것을 만족해야 한다.**

| # | 명제 |
|---|---|
| C-1 | 계산 불가 셀에 문자 `0` 이 없다 |
| C-2 | `—` 의 font-size 가 같은 카드의 값과 같다 (**자동화 어려움 — 육안**) |
| C-3 | 모든 `available` 값에 기준 문구가 있다 |
| C-4 | 모든 계산 불가 셀에 사유 코드가 **상시** 보인다 |
| C-5 | `gap`·`env_blocked`·`not_run`·`violation` 에 조치 줄이 있다 |
| C-6 | 16종 `event_type` 이 전부 렌더링된다 |
| C-7 | 증감 화살표·스파크라인 0건 |
| **C-8** | **`state-rules.css` 에 hex 리터럴 0건** ← 이 스토리 |
| **C-9** | ★ **빈 게시물로 렌더 시 예외 없이 전부 계산 불가** ← **USP-1 자체의 회귀 테스트** |
| C-10 | 대비 8조합 기준 통과 |
| C-11 | 상태 칩에 글리프가 전부 있다 (**자동화 어려움**) |
| C-12 | 출처 2열 순서가 커머스 먼저 |
| C-13~C-17 | d-02 범위 |

**C-2·C-11 은 자동화가 어렵다. 어려운 것을 통과로 적지 않는다.**
`[Source: .agent-team/07-design/design-handoff.md#3]`

## 7.3 PR 전 체크리스트

```
- [ ] `?? 0` · `|| 0` · `Number(value)` 가 지표 값 경로에 0건
- [ ] hex 색 리터럴 0건
- [ ] `lib/artifacts/` 밖에 `node:fs` import 0건
- [ ] `tokens:check` · `tokens:test` 통과
- [ ] Pretendard 육안 확인
- [ ] `dashboard/` 밖 파일 변경 0건 — `git diff --name-only` 첨부
- [ ] `Ecommerce_Service` 변경 0건
```

---

# 8. 연속성

## 8.1 선행 스토리

**없다.** 리드 판정 D-28 — **계약과 픽스처가 이미 있으므로 지금 착수한다.**

**다만 실제 게시물 확인은 M-06 이후다.** 그 전까지 `.agent-team/04-architecture/examples/empty-sink/` 를 픽스처로 쓴다 — **실제 게시물과 같은 스키마를 통과한 파일이다.**

## 8.2 이미 확립된 것에서 이어받는 것

| 출처 | 이어받는 것 |
|---|---|
| `Ecommerce_Service` (read-only) | 토큰 생성기 4파일 + `design-rules.css` · Next 16.3.4 / React 19.2.8 / Tailwind 4 조합 · `"lint": "eslint"` 관례 |
| `Plan/DESIGN.md` (read-only 정본) | 토큰 값 · **`dashboard-max: 1440px`·`dashboard-sidebar: 224px` 가 이미 있다** |
| `.agent-team/04-architecture/examples/` | 픽스처 2벌 14파일 |
| `.agent-team/07-design/design-system/state-tokens.css` | 상태 토큰 167줄 · **hex 0건 확인됨** |

## 8.3 확립된 패턴

| 패턴 | 어디에 |
|---|---|
| **생성물은 커밋하지 않는다** | `tokens.generated.css` — 커머스도 gitignore |
| **`predev`·`prebuild` 로 드리프트 방지** | 커머스 `package.json` |
| **한국어 UI·문서** | 전 저장소 |
| **`@AGENTS.md` 한 줄 위임** | `src/*/CLAUDE.md` 전부 |

---

# 9. 완료 정의 (DoD) · 미결정 · 차단

## 9.1 DoD

- [ ] AC-1 ~ AC-7 전부 체크
- [ ] **`dashboard/AGENTS.md` 에 DG-1~DG-19 가 전부 있다**
- [ ] ★ **`verify.mjs` 수정 한 줄과 그 이유가 주석에 있다**
- [ ] 이식 파일 머리에 **출처 커밋 SHA + sha256**
- [ ] **hex 색 리터럴 0건** — grep 출력을 PR 에
- [ ] **`lib/artifacts/` 밖에 `node:fs` 0건** — grep 출력을 PR 에
- [ ] **Pretendard 육안 확인** 결과를 PR 에
- [ ] 설치된 **정확한 버전**을 PR 에 기록
- [ ] `Ecommerce_Service` 변경 0건
- [ ] `.gitignore` 항목이 **Phillip 쪽에 들어갔는지** 확인 (직접 고치지 않는다)

## 9.2 이 스토리에서 하지 않는 것

| 항목 | 왜 |
|---|---|
| 화면 본문·컴포넌트 8종 | **d-02 의 몫** |
| `(results)/` 디렉터리·8화면 | 이후 사이클 |
| `tests/test_dashboard_isolation.py` | ★ **W6 Matthias + 사용자 승인** (D-22) |
| Node CI · lint 게이트 | **없는 게이트를 만들지 않는다** |
| 이벤트 브라우저·검색·필터 | C1 범위 밖 (A5) |
| 자동 폴링·실시간 | `DB-011` 수동 새로고침 |
| 다크 모드·OS 테마 | `Plan/DESIGN.md` 라이트 고정 |
| 인증·다국어 | C1 범위 밖 |
| `docker-compose.yml` | **결정 D-20 — C1 범위 밖 추천** |

## 9.3 미결정 — 구현자가 정하고 PR 에 적는다

| # | 항목 | 선택지 |
|---|---|---|
| **D01-a** | `AIROI_RESULTS_DIR` 기본값의 최종 형태 | `../results` 는 `dashboard/` 에서 실행할 때의 값이다. **실제 실행 위치를 확인한 뒤 확정** |
| **D01-b** | `types.ts` 를 손으로 쓸지 생성할지 | 손으로(권장 — 7파일 규모) / 생성기 |
| **D01-c** | 사이드바 결과 화면군 8줄 노출 | **리드 판정 J-2 — 노출한다.** *"A8 판정이 구조로 보이는 이득"* |
| **D-23** | 버전을 커머스와 맞추는가 | **⑴ 맞춘다 (권장)** ⑵ 독립 — **⑵는 이식한 생성기 출력이 동작하지 않을 수 있다** |

## 9.4 차단 — **숫자 렌더 하나만 차단된다.** 나머지는 안고 간다

| # | 항목 | 성격 |
|---|---|---|
| **D-22** | `test_dashboard_isolation.py` 도입 | **W6 + 사용자 승인.** 미도입이면 DG-1~DG-8 이 **사람의 규율로만** 지켜진다 → **M-09 에 한계로 인계** |
| **M-06 미완** | 실제 게시물이 없다 | **골격·읽기 계층·토큰은 픽스처로 진행 가능.** 빈 상태 문구는 §4.7 확정본 |
| ★ **M-06 미완 (숫자 렌더)** | **픽스처 14파일에 `value_formatted` 가 0건이다** | ★ **숫자 렌더는 M-06 이후다.** `commerce-connected` 로 렌더하면 **모든 `ok` 셀이 `undefined`** 다(§4.1). 그 전에는 숫자를 그리지 말고 `계약 준비 중` 으로 두거나 M-06 을 기다린다 |

## 9.5 하류로 넘기는 것

| 받는 쪽 | 넘기는 것 |
|---|---|
| **d-02** | 앱 골격 · 읽기 계층 · 토큰 · 상태 토큰 · 지침 파일 · 최소 불변식 검사 |
| **M-09 (`#49`)** | ★ **`DASHBOARD_NOT_ISOLATION_CHECKED`** (D-22 미도입 시) · **`DB-013` 부분 충족** — 빈 상태 안내가 실행 가능한 명령을 주지 못한다 |
| **W6 Timothy** | `dashboard/AGENTS.md` — **검토·정제 대상.** 최초 작성은 이 스토리가 끝냈다 |
| **W6 Matthias** | §7.2 검증 명제 C-8·C-9 |
| **이후 사이클** | `(results)/` 자리 · 라우트 명명 규약 · 상태 어휘 — **`NEEDS_MODEL_OUTPUT` → `available` 전환만으로 결과 화면이 켜진다** |

<!-- ════════ source_hash inputs (D3 · Matthias 항목5) ════════
     계산법: project-context-kr.md §12  ·  파일 23종
     재현:  아래 목록을 sorted() 하고 각 파일에 f"{path}\n{sha256_hex}\n" 를 이어붙여
            그 바이트열의 SHA-256 앞 16자리를 취한다. 없는 파일은 "MISSING".

     .agent-team/00-plan/charter.md
     .agent-team/00-plan/task-graph.md
     .agent-team/03-service-planning/user-stories.md
     .agent-team/03-service-planning/usp.md
     .agent-team/04-architecture/adr/ADR-0001-publish-not-api.md
     .agent-team/04-architecture/adr/ADR-0006-token-generator-port.md
     .agent-team/04-architecture/api-contracts.md
     .agent-team/04-architecture/build-plan.md
     .agent-team/04-architecture/code-structure.md
     .agent-team/04-architecture/dashboard-architecture.md
     .agent-team/04-architecture/dependency-plan.md
     .agent-team/04-architecture/design-patterns.md
     .agent-team/04-architecture/exceptions.md
     .agent-team/04-architecture/schemas/common.schema.json
     .agent-team/04-architecture/schemas/index.schema.json
     .agent-team/07-design/dashboard-agents-design-constraints.md
     .agent-team/07-design/design-handoff.md
     .agent-team/07-design/design-system/state-tokens.css
     .agent-team/07-design/design-system/token-strategy.md
     .agent-team/07-design/ux-flow-map.md
     AGENTS.md
     docs/GIT_WORKFLOW.md
     src/AGENTS.md

     → source_hash = 5cf5ccb05350cf24
     ════════════════════════════════════════════════════ -->
