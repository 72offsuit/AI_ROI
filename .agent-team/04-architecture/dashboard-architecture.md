# 대시보드 구조 설계 (T2.10)

**작성** James (Role 4 · Architect) · 2026-09-11 · 사이클 C1
**전제** Joshua 의 **A8 판정 — 대시보드는 애플리케이션 하나다** (`usp.md` §1.2). 경로 `dashboard/` · Next.js · `:3001` · **결과 파일 읽기**(API 서버 없음)
**정본 근거** SRS `DB-001`~`DB-014` · §31 · `ISO-004` · PRD §69 · `Plan/DESIGN.md`
**조사 방식** `Ecommerce_Service` 는 **읽기 전용으로만** 조사했다. 변경 0건 (`build-plan.md` §7 증명)

> 이 문서가 정하는 것은 **골격**이다. 정보구조·시각 표현은 **Jonnathan(T2.12~T2.14) 소관**이고 침범하지 않았다.

---

# 1. 남은 문제 넷

A8 판정이 스택·포트·경로·전달 경로를 확정했다. 아키텍처가 답할 것은 넷이다.

| # | 문제 | 절 |
|---|---|---|
| 1 | C1 의 **관측 화면군**과 이후의 **결과 화면군**이 같은 앱에 공존하는 라우팅 골격 | §2 |
| 2 | 파일 읽기를 **한 곳으로 모아** `DB-014` 를 코드로 강제하는 법 | §3 |
| 3 | **디자인 토큰 전략** — "토큰 두 벌 관리 금지"(PRD §69)를 지키는 법 | §4·§5 |
| 4 | **W-8** — 격리 검사가 `dashboard/` 를 보지 않는다 | §6 |

그리고 리드 판정 **D-6** 이 요구한 `dashboard/AGENTS.md` 내용 규정 → §7.

---

# 2. 디렉터리와 라우팅

```text
dashboard/
├── AGENTS.md · CLAUDE.md        ★ Andrew 가 디렉터리 생성과 같은 작업 단위로 쓴다 (리드 판정 D-6) · §7
├── package.json · package-lock.json
├── next.config.ts
├── postcss.config.mjs
├── tsconfig.json
├── scripts/                     디자인 토큰 생성기 (Ecommerce_Service 에서 이식) · §5
│   ├── design-tokens.mjs
│   └── tokens/  render.mjs · resolve.mjs · verify.mjs
└── src/
    ├── app/
    │   ├── layout.tsx           루트 셸 — 사이드바 + 헤더 + provenance 바
    │   ├── globals.css
    │   ├── page.tsx             / — 개요. index.json 의 views 를 그대로 그린다
    │   │
    │   ├── (observability)/     ★ C1 — 산출 주체 src/measurement/
    │   │   ├── ingestion/page.tsx     V1 수집 현황
    │   │   ├── rejections/page.tsx    V2 계약 위반
    │   │   ├── coverage/page.tsx      V3 필드 충족률
    │   │   ├── kpi/page.tsx           V4 KPI
    │   │   ├── quality/page.tsx       V5 데이터 품질
    │   │   └── freeze/page.tsx        V6 봉인 상태
    │   │
    │   └── (results)/           이후 사이클 — 산출 주체 src/decision/. ★ C1 에서 만들지 않는다
    │         churn · cohort · uplift · clv · segments ·
    │         optimization · experiments · targets        (DB-003~DB-010)
    │
    ├── lib/
    │   ├── artifacts/           ★ 파일을 읽는 유일한 모듈 · §3
    │   │   ├── paths.ts         허용 경로 화이트리스트
    │   │   ├── read.ts          index → 산출물 로딩 · run_id 대조
    │   │   └── types.ts         게시 계약 v1 의 TypeScript 타입
    │   └── format/              값 표시 규칙 (0 vs 계산 불가) — Jonnathan 설계를 코드로
    ├── components/
    │   ├── MetricValue.tsx      ★ status 5종을 서로 다른 시각 상태로 그리는 단일 컴포넌트
    │   ├── SourceSplit.tsx      commerce / simulator 병렬 표시
    │   ├── NoticeList.tsx       notices[] 표시 (가정·한계)
    │   ├── ProvenanceBar.tsx    무엇을 보고 있는가 (DB-013)
    │   └── EmptyState.tsx       게시물 없음 → 게시 방법 안내 (DB-013)
    └── styles/
        ├── tokens.generated.css   ★ 생성물 · .gitignore · 직접 수정 금지
        └── design-rules.css       YAML 표준 그룹 밖 규칙 (그림자·모션·레이어)
```

## 2.1 왜 Route Group 인가

**Next.js 의 `(그룹명)` 은 URL 에 나타나지 않는다.** `/(observability)/kpi` 의 URL 은 `/kpi` 다.

| 얻는 것 | |
|---|---|
| **산출 주체가 디렉터리로 갈린다** | `(observability)` = `src/measurement/` 게시물 · `(results)` = `src/decision/` 게시물 |
| **URL 이 깨끗하다** | 이후 사이클이 붙어도 `/kpi` 가 `/observability/kpi` 로 바뀌지 않는다 |
| **그룹별 레이아웃을 나중에 둘 수 있다** | 결과 화면군에 모델 버전 표시 바가 필요해지면 `(results)/layout.tsx` 하나로 끝난다 |
| **격리 검사가 경로로 대상을 좁힐 수 있다** | §6 |

**C1 에서 `(results)/` 디렉터리를 만들지 않는다.** 빈 디렉터리를 만들면 "구현했다"로 읽힌다. **만드는 것은 그 자리를 비워 둔 이 문서와 라우트 명명 규약뿐이다.**

## 2.2 라우트 ↔ 게시물 — `index.json` 이 정본

`index.json` 의 `views` 맵이 화면 ↔ 산출물 ↔ 라우트를 고정한다(`api-contracts.md` §5).
**대시보드가 라우트 목록을 하드코딩하지 않는다** — `/` 개요는 `views` 를 읽어 그린다. 계약에 화면이 늘면 개요가 자동으로 따라온다.

## 2.3 렌더링 — 서버에서 읽고, 캐시하지 않는다

| 결정 | 근거 |
|---|---|
| **Server Component 에서 파일을 읽는다** | 브라우저는 파일시스템에 접근할 수 없다. API 서버는 두지 않는다(`DB-013`) |
| **`export const dynamic = "force-dynamic"`** | 요청마다 다시 읽는다 → **수동 새로고침이 그대로 성립**한다 (`DB-011`) |
| **`fetch` 캐시·ISR 을 쓰지 않는다** | 게시물이 갱신됐는데 화면이 옛것을 보이면, 그것도 "조용히 틀린 값"이다 |
| **클라이언트 컴포넌트는 상호작용에만** | 정렬·필터·펼치기. **계산하지 않는다** (`DB-012`) |

---

# 3. ★ 파일 읽기를 한 곳으로 모은다 — `DB-014` 를 코드로

**`src/lib/artifacts/` 밖에서 `fs` 를 쓰지 않는다.**

```ts
// lib/artifacts/paths.ts — 허용 경로 화이트리스트
const RESULTS_DIR = process.env.AIROI_RESULTS_DIR ?? resolve(process.cwd(), "../results");
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
| **경로 이탈이 예외가 된다** | `../../data/hidden/...` 같은 경로가 런타임에 던진다. 조용히 읽히지 않는다 |
| **격리 검사 대상이 좁아진다** | §6 의 검사가 *"`lib/artifacts/` 밖에서 `node:fs` import 금지"* 한 줄로 강해진다 |
| **경로가 환경변수 하나** | `AIROI_RESULTS_DIR`. docker-compose 가 `:ro` 로 마운트하면 컨테이너 경계까지 이중 방어(`dependency-plan.md` §6.2) |
| **`data/processed/` 는 상수만 두고 C1 에서 쓰지 않는다** | C1 에 산출물이 없다. 쓰지 않는 코드를 만들지 않는다 |

## 3.1 읽기 순서와 불일치 처리

```text
1. index.json 을 읽는다
   └ 없다 → EmptyState: "게시물이 없다. 게시 명령을 실행한다." (DB-013)
2. contract_version 확인
   └ 다르다 → 렌더링하지 않고 "계약 버전 불일치" 표시
3. views[해당 화면].artifact 의 path 를 읽는다
4. run_id 가 index 와 같은지 확인
   └ 다르다 → "게시 진행 중 또는 불일치". ★ 값을 섞어 표시하지 않는다
5. 렌더링
```

**4단계가 원자성 계약의 읽는 쪽 절반이다**(`api-contracts.md` §6.2).

## 3.2 타입 — 계약에서 파생한다

`lib/artifacts/types.ts` 는 `docs/contracts/measurement-publish/v1/*.schema.json` 과 **일치해야 한다.**
C1 에서는 **손으로 쓰고 주석으로 정본을 가리킨다.** 자동 생성기를 넣는 것은 의존성과 빌드 단계를 늘리는 일이고, 계약이 7개 파일 규모라 이득이 없다.

> **불일치 위험은 실재한다.** 완화: `lib/artifacts/read.ts` 가 **읽은 직후 최소 불변식을 확인**한다 — `contract_version` · `artifact` · `run_id` 존재, 그리고 **`status !== "ok"` 인데 `value !== null` 이면 던진다.
> 마지막 항목이 중요하다. **대시보드가 계약 위반을 발견하면 그리지 않고 실패한다.** 0 으로 채워진 값을 화면에 올리느니 화면이 비는 편이 낫다.

---

# 4. 디자인 토큰 — 조사 결과 (read-only)

**PRD §69 가 Next.js 를 고른 유일한 결정적 근거가 "토큰 두 벌 관리 금지"였다.** 그래서 이 절이 스택 결정의 근거를 실제로 지키는지 확인하는 자리다.

## 4.1 `Ecommerce_Service` 의 파이프라인 — 실측

| 사실 | 근거 |
|---|---|
| 생성기는 **스크립트 4개 · 총 199줄** | `scripts/design-tokens.mjs`(33) · `scripts/tokens/render.mjs`(34) · `resolve.mjs`(71) · `verify.mjs`(61) |
| **입력은 `Plan/DESIGN.md` 하나** | `design-tokens.mjs` — `values.input ?? "Plan/DESIGN.md"` |
| 출력은 `src/styles/tokens.generated.css` | 동일 |
| **외부 의존은 `js-yaml` 하나** | `render.mjs`→`resolve.mjs`→`import { JSON_SCHEMA, load } from "js-yaml"` |
| `predev`·`prebuild` 에서 자동 생성 | `package.json` scripts |
| `tokens:check` 가 **생성물이 정본과 다르면 실패** | `design-tokens.mjs --check` |
| 생성 CSS 는 **Git 에서 제외** | `docs/DESIGN_TOKENS.md` |
| **`DESIGN.md` 가 이미 대시보드 토큰을 갖고 있다** | `dashboard-max: 1440px` · `dashboard-sidebar: 224px` (`DESIGN.md:107-108, 265`) |
| 생성기가 **`--container-dashboard-max` 를 이미 내보낸다** | `render.mjs` — `for (const key of ["commerce-max", "dashboard-max"])` |
| YAML 표준 그룹 밖 규칙은 손으로 쓴 `design-rules.css`(61줄)에 | 그림자·모션·포커스·z-layer |
| **두 저장소의 `Plan` 서브모듈이 같은 커밋을 가리킨다** | `git -C Plan rev-parse HEAD` — 양쪽 `c46aee5eed00193b9331403645b8dbccaef52278` (실행 확인) |

> **`DESIGN.md` 는 처음부터 커머스와 대시보드를 함께 정의하도록 쓰였고, 생성기도 이미 대시보드 토큰을 내보낸다.**
> 즉 **재사용 가능 여부를 판단할 문제가 아니라, 이미 준비된 것을 꺼내 쓰는 문제다.**

## 4.2 `Ecommerce_Service` 변경 0건

이 조사에서 읽기만 했다. `git status` 증명은 `build-plan.md` §7.

---

# 5. 토큰 전략 — 결정

> ### 결정 — 생성기 4개 파일을 `dashboard/scripts/` 로 **이식**하고, 입력을 `../Plan/DESIGN.md` 로 둔다

```jsonc
// dashboard/package.json (발췌)
{
  "scripts": {
    "tokens:generate": "node scripts/design-tokens.mjs --input ../Plan/DESIGN.md",
    "tokens:check":    "node scripts/design-tokens.mjs --check --input ../Plan/DESIGN.md",
    "tokens:test":     "node scripts/tokens/verify.mjs",
    "predev":   "npm run tokens:generate",
    "prebuild": "npm run tokens:generate",
    "dev":      "next dev --port 3001"
  }
}
```

## 5.1 이것이 "토큰 두 벌"이 아닌 이유 — 구분해야 할 두 가지

| | 정본이 몇 벌인가 |
|---|---|
| **토큰 값** (색·타이포·간격·반경·컴포넌트) | **한 벌.** `Plan/DESIGN.md` 하나. 두 저장소가 같은 서브모듈 커밋을 가리킨다 |
| **생성기 코드** | 두 벌 (199줄 × 2). **이것은 코드 중복이지 값 중복이 아니다** |

PRD §69 가 Streamlit 을 기각한 근거는 *"**동일한 값**을 UI 마다 새로 정의"* 하게 된다는 것이었다.
**값의 정본은 여전히 하나다.** 색상 하나를 바꾸면 `Plan/DESIGN.md` 를 고치고, 두 저장소가 서브모듈 포인터를 올리면 양쪽이 같이 바뀐다.

## 5.2 기각한 대안

| 대안 | 기각 사유 |
|---|---|
| **`Ecommerce_Service` 의 스크립트를 상대경로로 직접 실행** | **런타임 의존이 생긴다.** AGENTS.md: *"런타임 의존은 없다. 이 저장소는 단독으로 실행된다."* 그 저장소가 없으면 빌드가 깨진다 |
| **공유 npm 패키지로 배포** | 배포 인프라(레지스트리·버저닝·릴리스)를 새로 만든다. 199줄을 위해서. `Plan/DESIGN.md:190` 도 *"공유 토큰·UI 코드의 배포 여부는 대시보드 스택 확인 후 정한다"* 로 열어 두었을 뿐 요구하지 않는다 |
| **`git subtree`/서브모듈로 스크립트 공유** | 서브모듈이 하나 더 늘고, `Plan` 서브모듈 규약(포인터 커밋 금지)과 섞여 운영이 복잡해진다 |
| **토큰 값을 대시보드에 복사** | ★ **이것이 PRD §69 가 금지한 바로 그것이다.** 하지 않는다 |

## 5.3 남는 위험 — 정직하게

| 위험 | 완화 |
|---|---|
| **생성기 두 벌이 갈라진다.** 한쪽에서 `render.mjs` 를 고치면 두 저장소가 다른 CSS 를 만든다 | 이식 파일 머리에 **출처 커밋 SHA 를 주석으로 기록**한다. `dashboard/AGENTS.md` 에 *"이 스크립트는 `Ecommerce_Service` 에서 이식한 것이다. 로직을 바꾸려면 양쪽을 함께 본다"* 를 적는다 |
| **`Plan` 서브모듈 포인터가 갈라진다** | 오늘은 같다(`c46aee5`, 실행 확인). `tokens:check` 가 생성물 불일치를 실패로 만들고, 게시물 `provenance` 와 별개로 **`dashboard/` 는 `Plan` SHA 를 화면 하단에 표시**할 것을 권고한다 |
| CI 에서 자동 검사되지 않는다 | Node CI 는 C1 에서 도입하지 않는다(`dependency-plan.md` §5). **`tokens:check` 는 `predev`·`prebuild` 로 로컬에서 강제**된다 |

## 5.4 `design-rules.css`

YAML 표준 그룹에 없는 규칙(그림자·모션·포커스·z-layer)은 `Ecommerce_Service` 에서 **손으로 쓴 61줄**이다.
대시보드도 같은 값이 필요하다(`Plan/DESIGN.md` 본문이 정본). **같은 방식으로 손으로 쓰되, 값은 `DESIGN.md` 본문에서 가져온다.** 이 파일은 생성물이 아니므로 커밋한다.

---

# 6. ★ W-8 — 격리 검사를 `dashboard/` 까지 확장

## 6.1 문제 — 실측

`tests/test_isolation.py:51-55`:

```python
def _iter_source_files():
    if not SRC_ROOT.is_dir():          # SRC_ROOT = REPO_ROOT / "src"
        return
    for path in sorted(SRC_ROOT.rglob("*.py")):   # ← .py 만, src/ 만
        yield path, _module_name(path)
```

**`dashboard/` 는 `src/` 밖이고 TypeScript 다. 현재 검사가 한 줄도 보지 않는다.**
`DB-014` 는 `dashboard/` 가 `data/hidden/`·`data/ground_truth/`·`src/simulator/` 에 접근하지 않을 것을 요구하는데 **강제하는 코드가 없다.**

## 6.2 설계 — 별도 파일. 봉인 파일을 고치지 않는다

`tests/test_isolation.py` 는 봉인이다. **`tests/test_dashboard_isolation.py` 를 새로 만든다.** 표준 라이브러리만 쓴다.

| 검사 | 방법 | 강제하는 것 |
|---|---|---|
| `test_no_forbidden_data_paths` | `dashboard/**/*.{ts,tsx,js,jsx,mjs,json,css}` 텍스트에 `data/hidden` · `data/ground_truth` 부분 문자열 없음 | `DB-014` 접근 금지 |
| `test_no_simulator_reference` | 같은 대상에 `src/simulator` 없음 | `DB-014` |
| `test_no_src_import` | `from "../src/...` / `require("../src/...` 패턴 없음 | `DB-014` — 대시보드가 `src/**` 를 import 하지 않는다 |
| `test_fs_access_is_centralised` | **`node:fs`·`fs/promises` import 가 `src/lib/artifacts/` 안에서만** 발견된다 | §3 — 파일 읽기 단일 지점 |
| `test_dashboard_has_agent_guides` | `dashboard/AGENTS.md`·`CLAUDE.md` 존재 + `CLAUDE.md` 에 `@AGENTS.md` | `ISO-004` · `DB-014` |
| `test_dashboard_absent_is_skipped` | `dashboard/` 가 없으면 **skip 하되 사유를 남긴다** | 순서 의존 제거 |

**제외 경로:** `node_modules/` · `.next/` · `styles/tokens.generated.css`.

## 6.3 이 검사의 한계 — 먼저 적는다

| 못 막는 것 | 왜 |
|---|---|
| **정규식/부분 문자열 검사다. AST 가 아니다** | TypeScript 파서를 넣으려면 Node 의존성이 필요하고, 그러면 `isolation.yml` 의 무의존성 전제가 깨진다 |
| 문자열 조립 경로 (`` `data/${kind}` ``) | Python 쪽 검사도 같은 한계다 (`measurement-map.md` §2.3) |
| 런타임 접근 | §3 의 화이트리스트가 런타임 방어를 맡는다 — **두 겹으로 나눈 이유가 이것이다** |
| 오탐 가능성 | 주석·문서 문자열에 경로가 등장하면 실패한다. **오탐은 안전한 방향의 실패**이므로 허용한다 |

## 6.4 실행 권한 — ★ 명시

> **이 검사의 설계는 여기까지가 아키텍처의 몫이다. 구현·도입은 다르다.**
>
> - `tests/test_dashboard_isolation.py` 는 **신규 파일**이므로 봉인 규칙의 문언에는 걸리지 않는다.
> - 그러나 **격리 검사 체계를 건드리는 일**이고, task-graph §4 는 그 체계를 **W6 Matthias + 사용자 승인**에 두었다.
> - → **W6 Matthias 가 사용자 승인을 받아 도입한다.** W5 Andrew 도 Phillip 도 만들지 않는다.
>
> **C1 에서 도입하지 않기로 결정할 수 있다.** 그 경우:
> - `docs/gate1_checklist.md` 에 *"격리 검사는 `dashboard/` 를 보지 않는다"* 를 **명시적 한계**로 적는다
> - `results/measurement/freeze_status.json` 의 `notices` 에 `DASHBOARD_NOT_ISOLATION_CHECKED` 를 넣는다
> - **검사하지 않은 것을 통과로 적지 않는다** (AGENTS.md)

---

# 7. `dashboard/AGENTS.md` 에 들어갈 내용 — 리드 판정 D-6 대응

**최초 작성은 Andrew(W5-C)의 소유**이고 디렉터리 생성과 같은 작업 단위다(task-graph §4 D-6).
**여기서 규정하는 것은 그 파일에 반드시 들어갈 제약이다.** 문장 그대로 베끼지 말고 Andrew 가 자기 말로 쓰되, 아래 8항목이 빠지면 안 된다.

| # | 반드시 포함 | 근거 |
|---|---|---|
| **DG-1** | **읽기 허용은 `results/` 와 `data/processed/` 뿐이다.** `data/raw/`·`data/hidden/`·`data/ground_truth/` 는 읽지 않는다 | `DB-014` |
| **DG-2** | **`src/**` 를 import 하지 않는다.** `src/simulator/` 는 이름으로도 참조하지 않는다 | `DB-014` · `ISO-001` |
| **DG-3** | **계산하지 않는다.** 합계·비율·분류·지표 파생을 만들지 않는다. 표시 순서 정렬과 필터는 허용 | `DB-012` |
| **DG-4** | **출처(커머스/시뮬레이터)를 재분류하지 않는다.** `by_source` 를 그대로 쓴다 | `MEA-002` |
| **DG-5** | **`status !== "ok"` 인 값을 숫자로 그리지 않는다.** 0 과 다른 시각 상태 + 사유를 표시한다. **`not_run` 을 통과로 그리지 않는다** | PRD §10.1 · `MEA-003` · AGENTS.md |
| **DG-6** | **파일 읽기는 `src/lib/artifacts/` 안에서만.** 다른 곳에서 `node:fs` 를 쓰지 않는다 | §3 |
| **DG-7** | **`src/styles/tokens.generated.css` 를 직접 수정하지 않는다.** 토큰 값은 `Plan/DESIGN.md` 가 정본이고, `Plan/` 은 이 저장소에서 수정하지 않는다. `scripts/` 는 `Ecommerce_Service` 에서 이식한 것이며 로직 변경 시 양쪽을 함께 본다 | PRD §69 · AGENTS.md 서브모듈 규약 |
| **DG-8** | **`Ecommerce_Service` 를 편집하지 않는다.** 읽기 전용 조사만 | charter §5 |

`dashboard/CLAUDE.md` 는 **`@AGENTS.md` 한 줄**이다. 내용을 복제하지 않는다(`ISO-004` · `test_claude_md_delegates_to_agents_md` 와 같은 규약).

> **W6 Timothy 는 이 파일을 검토·정제한다. 최초 작성을 W6 까지 미루지 않는다** (리드 판정 D-6).

---

# 8. 이후 사이클이 얹힐 때 무엇을 하면 되는가

**C1 이 껍데기까지 세우는 이유는 결과 화면군을 만들 때 앱을 다시 만들지 않기 위해서다**(A8 판정 변경 CH-2).

| 이후 작업 | C1 이 이미 해 둔 것 | 그때 할 일 |
|---|---|---|
| `DB-003`~`DB-010` 8화면 추가 | 라우트 그룹 자리 · 루트 셸 · 토큰 파이프라인 | `(results)/<name>/page.tsx` 추가 |
| `src/decision/` 산출물 읽기 | `lib/artifacts/` 화이트리스트 · 읽기 순서 규약 | 계약 스키마 추가 (`results/*.csv` 는 `data_spec` §7.5) |
| 결과 화면군의 계약 | 게시 계약 v1 의 봉투·`metric_value` 를 그대로 재사용 가능 | `contract_version` 을 올릴지 판단 |
| 모델 버전 표시 | `ProvenanceBar` 컴포넌트 | `(results)/layout.tsx` 에서 확장 |

**C1 에서 만들지 않는 것:** `(results)/` 디렉터리 · CSV 파서 · 차트 라이브러리 선정 · 인증 · 다국어.

---

# 9. 결정이 필요한 항목

| # | 항목 | 선택지 | 추천 |
|---|---|---|---|
| **D-22** | **`tests/test_dashboard_isolation.py` 를 C1 에 도입하는가** — §6.4 | ⑴ W6 Matthias 가 사용자 승인 후 도입 ⑵ C1 에서 도입하지 않고 한계를 명시 | **⑴.** `DB-014` 를 강제하는 코드가 지금 하나도 없다. 대시보드가 만들어진 **직후**가 가장 싼 시점이다 |
| **D-23** | Next.js·React 버전을 `Ecommerce_Service` 와 맞추는가 | ⑴ 맞춘다 (Next 16 · React 19 · Tailwind 4) ⑵ 독립 선택 | **⑴.** 토큰 파이프라인이 Tailwind 4 의 `@theme inline` 을 전제한다. 다른 메이저를 쓰면 이식한 생성기의 출력이 동작하지 않는다. **단 정확한 버전은 Andrew 가 설치 시점에 해석해 기록한다** — 이 문서에서 베끼지 않는다 |

---

# 10. 미정으로 남긴 것

| 항목 | 왜 |
|---|---|
| 정보구조 · 화면 레이아웃 · 시각 표현 | **Jonnathan T2.12~T2.14 소관.** 침범하지 않는다 |
| 차트 라이브러리 | 관측 화면군에 차트가 필수인지가 정보구조에 달렸다. Jonnathan 결정 후 |
| `(results)/` 8화면의 라우트 이름 | 이후 사이클. 명명 규약(`DB-00X` 이름의 kebab-case)만 남긴다 |
| `AIROI_RESULTS_DIR` 기본값의 최종 형태 | Andrew 가 실제 실행 위치를 확인한 뒤 확정. `../results` 는 `dashboard/` 에서 실행할 때의 값이다 |
