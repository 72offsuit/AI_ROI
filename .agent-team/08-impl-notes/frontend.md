---
name: frontend-impl-notes
cycle: C1
wave: W5
author: Andrew (Role 9 · Frontend & Mobile Lead)
date: 2026-09-11
stories: [d-01, d-02]
---

# W5-C 구현 노트 — 관측 대시보드

**쓰기 범위 준수** `dashboard/**` 와 이 파일만 썼다. `src/**` · `config/**` · `tests/**` · 루트 `.gitignore` · `Plan/**` · `Ecommerce_Service` **변경 0건.**
**git 작업 0건** — L1 권한이므로 commit·push·이슈·PR 을 하지 않았다.

---

# 0. 한 문단

관측 화면군 8화면 · 컴포넌트 11종 · 읽기 계층 · 토큰 파이프라인을 구현했다.
**`d-01`·`d-02` 둘 다 완료했다.** AC-12 는 **리드의 L1 승격**으로 Playwright 로 닫았다(§7.1).
**2026-09-11 M-06 이 끝나 실제 `results/` 로 전환했다** — `value_formatted` 가 도착해 **코드 변경 0건**으로 숫자가 켜졌다(§12).
이 구현의 중심 결정은 하나다: **화면은 숫자를 만들지 않는다.** `value_formatted` 가 계약에 도착하기 전까지 `ok` 셀은 `계약 준비 중` 으로 렌더된다. 그 자리를 `m.value` 포맷으로 메우는 것이 이 사이클에서 가장 하기 쉬운 잘못이고, 그 한 줄이 USP-1 을 끝낸다.

---

# 1. 재현 명령

```bash
cd dashboard
npm install                 # 최초 1회

npm run tokens:generate     # Plan/DESIGN.md → src/styles/tokens.generated.css (306줄)
npm run tokens:check        # 정본과 다르면 실패. predev·prebuild 가 자동 실행한다
npm run tokens:test         # 생성기 자체 검증 → 15 scenarios passed
npm run check:state-map     # 상태 파생 + 0 채우기 불변식 → 25 assertions passed
npm run lint                # eslint (CI 게이트로 만들지 않았다)
npm run build
```

## 1.1 E2E · 수동 확인용 dev 서버 기동 + 시드 데이터

**게시물이 아직 없다**(`results/` 미생성 · M-06 미완). 픽스처로 띄운다.

```bash
cd dashboard

# ① 시드: 예시 산출물을 계약이 규정한 실제 배치로 복사한다 (원본은 수정하지 않는다)
node scripts/stage-fixture.mjs empty-sink
node scripts/stage-fixture.mjs commerce-connected

# ② 기동 — 포트 3001 (3000 은 Ecommerce_Service 점유)
AIROI_RESULTS_DIR=$PWD/.fixtures/empty-sink/results \
AIROI_FIXTURE_MODE=1 \
npm run dev

# 또는 프로덕션 빌드로
npm run build && AIROI_RESULTS_DIR=$PWD/.fixtures/commerce-connected/results \
AIROI_FIXTURE_MODE=1 npm start
```

### ★ E2E · 스크린샷 증거 (Playwright)

```bash
npx playwright install chromium   # 최초 1회 · 브라우저 바이너리 다운로드

npm run shots:empty        # empty-sink 픽스처 → screenshots/empty-sink/
npm run shots:connected    # commerce-connected → screenshots/commerce-connected/
npm run shots              # 둘 다
```

**각 스크립트가 `stage-fixture.mjs` 를 먼저 돌리고, `playwright.config.ts` 의 `webServer` 가
`npm run build && npm start` 로 `:3001` 을 띄운 뒤 촬영한다.** 시드·기동·촬영이 한 명령에 들어 있어
**사람이 순서를 기억할 필요가 없다.**

| 산출물 | 내용 |
|---|---|
| `screenshots/<픽스처>/00-index … 07-triggers.png` | 8화면 전폭(fullPage, 1440px) |
| `screenshots/commerce-connected/usp1-representative-scene.png` | ★ **USP-1 대표 장면** |
| `screenshots/commerce-connected/usp1-measured-zero.png` · `usp1-uncomputable.png` | 측정된 0 ↔ 계산 불가 |
| `screenshots/<픽스처>/us12-source-columns-900px.png` | 1024px 미만 적층 (US-12) |
| `screenshots/<픽스처>/a11y-skip-link-focus.png` | 키보드 포커스 |

**증거 위치 = `dashboard/screenshots/`** (D02-c). `.playwright/`·`test-results/`·`playwright-report/` 는
실행 부산물이라 gitignore 했고 **스크린샷은 증거이므로 하지 않았다.** `results/` 의 gitignore 여부(D-17)와
무관한 위치다 — 내 소유 경계 안이다.

**실제 게시물이 생긴 뒤에는 환경변수 없이 `npm run dev` 만으로 동작한다** — 기본값이 `dashboard/` 기준 `../results` 다.

| 환경변수 | 뜻 | 기본값 |
|---|---|---|
| `AIROI_RESULTS_DIR` | 계약의 `results/` 접두사가 가리킬 디렉터리 | `<cwd>/../results` (cwd = `dashboard/`) |
| `AIROI_FIXTURE_MODE` | 비어 있지 않고 `"0"` 이 아니면 **`표본 데이터 — 실측이 아닙니다`** 배지 | 미설정 |

> `process.env.X ?? 기본값` 을 쓰지 않고 `typeof === "string" && trim().length > 0` 으로 판정한다.
> `??` 는 빈 문자열을 유효값으로 받아 cwd 로 해석해 버린다 — 이 저장소가 막으려는 "조용히 틀린 기본값" 과 같은 부류다.

## 1.2 저장소 검증 (전부 실행함)

```bash
python3 -m unittest discover -s tests          # Ran 132 tests · OK (skipped=21) · 회귀 0
python3 -m unittest tests.test_isolation -v    # Ran 6 tests · OK
python3 .agent-team/04-architecture/tools/check_ownership.py   # 판정: PASS
git -C ../Ecommerce_Service status --porcelain # 빈 출력
git -C Plan status --porcelain                 # 빈 출력
```

> 기준선은 46건이었으나 실행 시점에 **132건**이었다 — Phillip 이 W5-A 를 병행 중이다. **OK · 회귀 0.**

---

# 2. 주요 결정사항

| # | 결정 | 근거 |
|---|---|---|
| **D01-a** | `AIROI_RESULTS_DIR` 기본값 = `<cwd>/../results`, **cwd 는 `dashboard/`** | `index.json` 의 `artifacts[].path` 가 **저장소 루트 기준**(`^(results\|data/processed)/`)이다. 그래서 `resolveArtifactPath()` 는 `results/` 접두사를 **떼고** `RESULTS_DIR` 아래로 해석한다. 아키텍처 §3 의 예시 코드는 `resolve(RESULTS_DIR, relative)` 인데, 그대로 쓰면 `RESULTS_DIR/results/...` 가 되어 **경로가 두 번 붙는다.** 실측으로 확인하고 고쳤다 |
| **D01-b** | `types.ts` 를 **손으로** 작성 | 계약 7파일 규모에 생성기는 의존성·빌드 단계만 늘린다. **타입은 런타임에 사라지므로 계약 위반을 못 잡는다** — 실제 방어는 `read.ts` 의 불변식 검사다 |
| **D01-c** | 사이드바에 결과 화면군 8항목 **비활성 노출** | 리드 판정 J-2. 비활성은 **실제 비활성**으로 구현했다 — `aria-disabled` · href 없음 · 탭 순서 제외 · 사유 문구를 접근 가능한 이름에 포함 |
| **D-23** | 버전을 커머스와 **맞춘다** | 이식한 생성기가 Tailwind 4 `@theme inline` 을 전제한다. 해석된 정확한 버전은 §3 |
| **D02-a** | **차트 라이브러리를 넣지 않는다** | 관측 화면군은 막대만 쓴다. 라이브러리를 넣으면 §5 의 `null → 0` 함정을 그 API 경계에서 **새로 관리**해야 한다. CSS 폭 퍼센트로 충분하고, 여기서 만든 숫자는 **화면에 출력되지 않는다**(레이아웃 비율일 뿐) |
| **D02-b** | 픽스처를 **실제 배치로 스테이징**(선택 ⑴) | 픽스처는 7파일이 한 디렉터리에 있고 실제 배치는 `results/measurement/*` + `results/data_quality_report.json` 이다. **읽기 계층에 "픽스처 모드"를 만들지 않았다** — 그러면 스크린샷이 검증하는 코드 경로를 실제 게시가 지나가지 않는다. `scripts/stage-fixture.mjs` 가 `index.json` 의 `artifacts[].path` 를 읽어 복사하므로 **배치가 바뀌어도 따라간다.** 픽스처 원본은 수정하지 않았다 |
| **D02-c** | 스크린샷 수단 = **⑶ `BLOCKED`** | §7.1 |
| **D02-d** | `headline_code` → 문구 매핑을 **화면 상수**로 | 계약이 코드를 주고 문구는 화면이 매핑한다. **순위는 화면이 정하지 않는다** |
| — | **`dashboard/.gitignore` 를 따로 두었다** | 루트 `.gitignore` 는 Phillip 단독 소유라 내가 못 고친다. git 은 디렉터리별 `.gitignore` 를 지원하므로 소유 경계를 넘지 않고 같은 결과를 얻는다. **Phillip 이 이미 루트에 3항목을 넣어 두어서**, 내 파일은 루트가 덮지 않는 `.fixtures/` · `out/` · `tsconfig.tsbuildinfo` 만 적었다 — 같은 규칙을 두 곳에 두면 한쪽만 고치는 사고가 난다 |
| — | `ProvenanceBar` 를 **layout 이 아니라 각 화면**에 | 아키텍처 §2 는 루트 셸에 두라고 했으나, provenance 는 **그 화면이 읽은 산출물의 봉투**에서 와야 한다. layout 에 두면 `index.json` 을 따로 한 번 더 읽게 되고 **화면이 그리는 값과 다른 신원을 표시할 수 있다.** `run_id` 대조의 의미가 사라진다 |

---

# 3. 설치된 정확한 버전 (lock 해석값)

| 패키지 | 선언 | 해석됨 |
|---|---|---|
| `next` | `16.3.4` | **16.3.4** |
| `react` · `react-dom` | `19.2.8` | **19.2.8** |
| `pretendard` | `1.3.9` | **1.3.9** |
| `tailwindcss` · `@tailwindcss/postcss` | `^4` | **4.3.3** |
| `typescript` | `^5` | **5.9.3** |
| `eslint` | `^9` | **9.39.5** |
| `eslint-config-next` | `16.3.4` | **16.3.4** |
| `js-yaml` | `4.3.2` | **4.3.2** |
| `@types/node` | `^24.13.3` | **24.13.4** |
| `@types/react` · `@types/react-dom` | `^19` | **19.3.0** |

환경: **Node v24.15.0** · **npm 11.12.1** (Next 16 최소 20.9.0 충족)
`Ecommerce_Service` HEAD `6b186d0f20a3d134389ef84b490d9a374c760e37`
`Plan` 서브모듈 — **양쪽 저장소가 같은 커밋** `c46aee5eed00193b9331403645b8dbccaef52278` (실행 확인). 토큰 값의 정본이 하나라는 주장이 오늘 참이다.

## 3.1 새 의존성 — 사다리 5단을 못 넘은 이유 (각 한 줄)

**`AI_ROI` 에는 `package.json` 자체가 없었다.** 따라서 아래는 전부 "이미 설치된 의존성이 푸는가"에서 **설치된 것이 0개**라 걸렸다.

| 의존성 | 사다리 5단을 못 넘은 이유 |
|---|---|
| `next` · `react` · `react-dom` | A8 판정이 스택을 Next.js 로 확정했다. 대안은 Streamlit 이고 PRD §69 가 **토큰 이중 정의**를 이유로 기각했다 |
| `pretendard` | `Plan/DESIGN.md` 가 지정한 글꼴이고 npm 패키지가 유일한 배포 경로다. 웹폰트 CDN 은 런타임 외부 의존을 새로 만든다 |
| `tailwindcss` · `@tailwindcss/postcss` | **이식한 생성기의 출력이 `@theme inline` 블록이다.** Tailwind 없이는 그 출력이 해석되지 않는다 — 선택이 아니라 생성기가 요구한다 |
| `typescript` · `@types/*` | `next build` 의 타입 검사 경로. 계약 7종을 손으로 옮겨 적는 작업에서 타입이 유일한 즉시 피드백이다 |
| `js-yaml` | **이식한 `resolve.mjs` 의 유일한 외부 의존.** 대안은 YAML 파서 자체 구현이고 `exceptions.md` §4 가 *"부분 구현 파서는 조용히 다른 값을 읽는다"* 로 금지했다 |
| **`@playwright/test`** | ★ **내가 스스로 넣지 않았다.** 새 devDependency + `npx playwright install` 네트워크 다운로드는 **L1** 이라 ⑶ `BLOCKED` 로 멈추고 보고했고, **리드가 사용자 승인을 받아 L1 승격**을 내린 뒤에 도입했다(2026-09-11). 사다리로는 5단에서 걸린다 — 설치된 브라우저 자동화 수단이 이 저장소에 0개였다. **버전 `^1.63.0` 과 설정 형태는 `Ecommerce_Service` 정본을 그대로 따랐고 새로 정하지 않았다.** 승격은 **이 작업 범위에서만** 유효하다 |
| `eslint` · `eslint-config-next` | ★ **넣지 않는 쪽을 먼저 검토했다.** `dependency-plan.md` §5 가 Node lint 를 CI 에 도입하지 않기로 했기 때문이다. 그런데 `d-01` §4.4 의 `package.json` 이 `"lint": "eslint"` 를 명시했고, **실행할 수 없는 명령을 스크립트에 적는 것은 AGENTS.md 정직성 위반**이다. 스크립트를 실재하게 만드는 최소 비용으로 도입했고 **CI 게이트로는 만들지 않았다** |

**차트 라이브러리는 넣지 않았다**(D02-a). **테스트 러너·Playwright 도 넣지 않았다**(§7.1).

## 3.2 `ponytail:` 마커 3건

```
src/lib/format/metric.ts:38
  ponytail: renders a placeholder for every ok/unconfirmed metric until the contract
  carries value_formatted; delete nothing when M-06 lands — the branch below simply
  stops being taken. Revisit if M-06 ships a different field name.

src/lib/artifacts/paths.ts:79
  ponytail: only the `results/` prefix is mapped; add a PROCESSED_DIR branch here
  the first time an index.json actually lists a `data/processed/` artifact.

src/components/ArtifactGate.tsx:75
  ponytail: the "게시 명령은 아직 없습니다" sentence is accurate only until M-06 ships
  `python3 -m src.measurement.publish`; replace it with the real command once that
  module exists and has been run, not before.
```

**세 건 모두 업그레이드 트리거가 있다** (`no-trigger` 0건).

---

# 4. `verify.mjs` 이식 결과 — **15 scenarios passed**

W3 의 예측이 정확했다. 그대로 이식하면 깨지고, **9행 한 줄**을 고치면 통과한다.

```js
// 이식 전 (Ecommerce_Service 원본)
const source = await readFile(join(root, 'Plan/DESIGN.md'), 'utf8');
//   → dashboard/scripts/tokens/ 깊이에서 root = dashboard/ 이므로
//     ENOENT: .../dashboard/Plan/DESIGN.md

// 이식 후
const source = await readFile(join(root, '../Plan/DESIGN.md')  /* ★ ported-file change */, 'utf8');
```

`root` 자체를 바꾸면 15행의 `spawnSync(... 'scripts/design-tokens.mjs')` 가 깨진다. **두 앵커가 서로 다른 기준점을 원하므로 9행만 고치는 것이 유일한 해다.**
수정 사실과 이유는 **파일 머리 주석**에 남겼다.

```
$ npm run tokens:test
15 scenarios passed; failed input and --check preserved output.
```

**나머지 3개(`design-tokens.mjs`·`render.mjs`·`resolve.mjs`)는 한 줄도 고치지 않았다** — `token-strategy.md` §2.1 의 K 규약이 그 셋에 대해서는 맞다.

## 4.1 이식 파일 출처 — 전부 머리 주석에 기록

| 파일 | 원본 sha256 | 스토리 기록값과 일치 |
|---|---|---|
| `scripts/design-tokens.mjs` | `b17ab2e4122b8c467d45e537b57b81195eaec1cca2d3219d338f9e6baed29c66` | ✅ |
| `scripts/tokens/render.mjs` | `c0ed6edc7970a93091c4a8ca49382181dde5a0abf0f6e256f29b2929e4ad3272` | ✅ |
| `scripts/tokens/resolve.mjs` | `ce07d675c9b86b94d3d6debeabde0836bee684fa87a6aa79d3d47c7ab1f3ba2a` | ✅ |
| `scripts/tokens/verify.mjs` | `d777aa8812e0e32ddde75a2c903f8eeabcafaad6bb5008c3dddb4615a0a8c27f` | ✅ (+1행 수정) |
| `src/styles/design-rules.css` | `810415a43e2ac0f21a9597cfc14fb418be3ab8ffd0ad39a9ed6a26dadaeef1da` | ✅ |

## 4.2 ★ `design-rules.css` 는 검증 범위 밖이다 (W6 인계)

**생성물이 아니라 손으로 쓴 파일**이고 `tokens:check` 가 이 파일을 **검사하지 않는다.**
값의 출처는 `Plan/DESIGN.md` **본문**(그림자·모션·포커스·z-layer)이며 생성기는 frontmatter 만 파싱한다.

> *"정본 일치 검증 파이프라인이 동작한다"* 는 **frontmatter YAML 범위에서만 참이다.** 이 문장을 그대로 W6 Timothy 에게 넘긴다.

이 파일의 `rgb(0 0 0 / 0.08)` 류는 **이식 원본의 그림자·백드롭 알파**이고 새 팔레트가 아니다. hex 리터럴은 0건이다.

---

# 5. ★ 0 채우기 방어 — 무엇을 어떻게 막았나

## 5.1 3중 방어

| 층 | 위치 | 무엇을 막나 |
|---|---|---|
| **① 읽는 즉시** | `lib/artifacts/read.ts` `assertMetricValueInvariants()` | `status ∈ {unavailable, blocked, not_run}` 인데 `value !== null` 이면 **던진다.** 화면이 그리지 않고 실패한다 |
| **② 표시 직전** | `lib/format/metric.ts` `formatMetricValue()` | 그래도 값이 오면 **`—` 로 렌더하고 `계약 위반` 칩**을 붙인다 (①이 있으면 도달 불가 — 심층 방어) |
| **③ 기준 검사** | 같은 곳 | `ok`·`unconfirmed` 인데 `basis` 가 없으면 **던지지 않고 화면에 `계약 위반` 칩**. 던지면 누락이 보이지 않는다 |

## 5.2 ★ 스토리 AC-6 문언과 의도적으로 다르게 구현한 곳

`d-01` AC-6 은 *"`status !== "ok"` 인데 `value !== null` 이면 던진다"* 라고 적었다.
**문자 그대로 구현하면 모든 정상 `unconfirmed` 지표가 던진다** — `common.schema.json` 이 `unconfirmed` 에 `value`·`basis`·`params_used` 를 **필수**로 요구하기 때문이다.

> **계약이 이긴다**(project-context §5). 그래서 조건을 **계산 불가 3종**(`unavailable`·`blocked`·`not_run`)으로 구현했고, 그 사유를 코드 주석에 남겼다.
>
> ★ **이것은 W3 이 놓친 자리다** (리드 확인). 스토리 문언이 스키마와 어긋났고, D2b 값 실재 검사는 **인용한 키가 계약에 있는지**를 보지 **조건식이 계약과 모순되는지**는 보지 않는다. 같은 종류의 결함이 더 있을 수 있다.
> `commerce-connected` 의 `churn_rate`(`unconfirmed`, 18.3%)가 이 차이에 걸리는 실제 사례다.

## 5.3 실행으로 증명한 방어 5종

각각 픽스처 사본을 만들어 실제로 렌더했다 (원본 수정 0건).

| 공격 | 결과 |
|---|---|
| `contribution_profit` 에 `value: 0` 주입 | `✕ 계약 위반 — 렌더링을 중단했습니다` / `계산 불가 상태에 값이 왔습니다 — kpi_report.metrics[3].value.by_source.commerce: status=unavailable, value=0` |
| `kpi_report.run_id` 를 어긋나게 | `✕ 게시가 진행 중이거나 불일치` + 양쪽 `run_id` 명시 + **값 렌더 0** |
| `contract_version` 을 `v2` 로 | `✕ 계약 버전 불일치` + *"필드 이름이 같아도 의미가 다를 수 있으므로 값을 렌더링하지 않습니다"* |
| `index.json` 없음 | `○ 게시물이 없습니다` + 게시 방법 안내 (**실행 가능한 명령을 제시하지 않는다**) |
| `path` 를 `results/../../data/hidden/secret.json` 로 | `✕ 허용 경로 밖 접근` — **`DB-014` 런타임 화이트리스트가 막았다** |

## 5.4 grep 증명 — **주석을 제외한 실행 코드 기준 0건**

```
?? 0                 0건
|| 0                 0건
Number(              0건
parseFloat           0건
.toFixed(            0건
.toLocaleString(     0건
filter(... > 0)      0건
─────────────────────────
합계 0건 (31개 파일)
```

> **원시 `grep` 은 히트가 난다** — 전부 **금지 패턴을 설명하는 주석**이다(`metric.ts` 머리 주석, `types.ts` 의 `value_formatted` 설명, `IngestionTimeline` 의 차트 함정 설명). 주석을 지우면 다음 사람이 같은 실수를 한다. 그래서 남겼고, 판정은 주석 제외 기준으로 한다.

**새 색값(hex):** `src/` 에서 **0건** (`tokens.generated.css` 제외 · 28파일).
`tokens.generated.css` 는 `Plan/DESIGN.md` 에서 **생성된 팔레트 자체**이므로 hex 를 담는 것이 정상이고 gitignore 대상이다. `scripts/tokens/verify.mjs` 의 hex 3개는 **이식한 테스트가 DESIGN.md 문자열을 변조해 생성기의 거부를 확인하는 픽스처**이며 색 정의가 아니다.

**`node:fs`:** `lib/artifacts/` 밖 **0건.**

---

# 6. 실행 가능한 검증 — `npm run check:state-map` (25건)

**비자명 로직 = 상태 파생 + 값 슬롯 규칙.** 그 로직이 깨지면 실패하는 가장 작은 것을 남겼다. 프레임워크·픽스처 없이 `node:assert` 만 쓴다.

```
① 계약 (status, reason_code) → 시각 상태 : 11건  (9종 사유 코드 전부 + reason_code 부재)
② 검사 상태 5종 (별도 축)               :  5건  (★ vacuous → unconnected)
③ ★ 0 채우기 규칙                       :  9건
```

③이 핵심이다:

| 검증 | 왜 |
|---|---|
| 측정된 0 은 게시 문자열(`0건`)로 렌더된다 | `—` 로 바꾸면 **측정한 것을 안 측정한 것으로** 만든다 |
| 계산 불가는 `—` 이고 **문자 `0` 이 없다** | 금지 1호 |
| `not_run` 은 `미실행`, `—` 가 **아니다** | `—` 는 "없음", `미실행` 은 "모름" |
| 계산 불가에 값이 오면 **억제 + 플래그** | 최종 방어선 |
| ★ **`observed_count: 0` 이 기준 문구에 남는다** | `typeof n === "number"` 로 판정한다. truthy 검사였으면 **"세어봤고 0이었다"는 증거가 사라진다** |
| `denominator: null` 은 **절 자체가 사라진다**(`분모 0` 아님) | 없는 분모를 0 으로 둔갑시키지 않는다 |
| `basis` 없는 `ok` 는 플래그된다 | V-3 |
| `value_formatted` 부재 → 자체 포맷 **금지** | 숫자를 만들면 `DB-012` 위반 |
| `unconfirmed` 에 `params_used` 없으면 플래그 | R-10 |

---

# 7. ★★ BLOCKED — 미실행을 통과로 적지 않는다

## 7.1 스크린샷 촬영 수단 — **해소됨** (⑵ Playwright · 리드 승인 2026-09-11)

**경위를 그대로 적는다.** 처음 보고 시점에는 ⑶ `BLOCKED` 를 골랐다:

| 선택지 | 1차 판정 |
|---|---|
| ⑴ 수동 촬영 | ❌ 브라우저를 조작하는 사람이 필요하다 |
| ⑵ Playwright 도입 | ❌ **L1 — 새 devDependency + 네트워크 다운로드.** 승격을 스스로 추론하지 않는다 |
| ⑶ `BLOCKED` | ✅ 1차 선택 → **AC-12 와 DoD 2줄을 체크하지 않고 보고** |

**그 뒤 리드가 사용자 승인을 받아 L1 승격을 내렸고, 승격 후 ⑵ 로 닫았다.**
**내가 판단을 바꾼 것이 아니라 권한이 바뀐 것이다.** 승격은 이 작업 범위에서만 유효하다.

```
@playwright/test  ^1.63.0  →  해석값 1.63.0   (Ecommerce_Service 와 동일)
npx playwright install chromium  →  Chrome Headless Shell 153.0.8010.12
                                    (chromium-headless-shell v1243, 94.3 MiB)
```

**`Ecommerce_Service` 는 읽기 전용을 유지했다** — 거기서 찍지 않았고 변경 0건이다(확인함).
설정 형태는 옆 저장소 `playwright.config.ts` 를 따랐고 **다른 것은 셋뿐**이다: 포트 **3001**(커머스 3100 과 공존),
`AIROI_RESULTS_DIR` 로 픽스처 주입, **`AIROI_FIXTURE_MODE=1` 강제**.

### 촬영 결과 — **23장 · 22 assertion 통과**

```
empty-sink          10 passed  (USP-1 2건은 skip — 그 픽스처에 revenue 측정값이 없다)
commerce-connected  12 passed
```

**스크린샷은 "한 번 이렇게 보였다"만 증명한다.** 그래서 이미지와 함께 명제를 걸었다:

| 명제 | 어떻게 |
|---|---|
| ★ **계산 불가 값 슬롯에 문자 `0` 이 없다** | 8화면 × 2픽스처에서 `--obs-absent-ink` 슬롯 전체를 훑어 `"0"` 포함 여부 검사 |
| ★ **C-2 — `—` 와 값의 타이포그래피가 같다** | ★ **육안에서 자동 검사로 바꿨다.** 대표 장면의 두 값 슬롯에 `getComputedStyle` 을 걸어 **`fontSize`·`fontWeight` 동일**을 단언한다. 클래스 비교가 아니라 **계산된 값** 비교다 |
| **U-3** | `—` 가 정확히 `—` 이고 `"0"` 을 포함하지 않는다 |
| **U-4 · U-6** | 사유 문구와 **사유 코드 원문**이 호버 없이 보인다 |
| **U-7** | `Primary 지표` 배지(`[P1]`)가 보인다 |
| **U-8 · U-9** | 조치 줄 · 출처 배지 |
| ★ **`표본 데이터` 배지** | **8화면 전부**에서 존재를 단언한다. 빠지면 실패한다 |
| **V-11** | `/triggers` 를 제외한 7화면에서 `↑↓▲▼` 0건 |
| **US-12 · S-1** | 900px 에서 `boundingBox().y` 비교 — **적층 시 커머스가 위** |
| **접근성** | 첫 `Tab` 이 건너뛰기 링크에 닿고, **비활성 결과 항목은 포커스되지 않는다** |

### ★ M-06 리허설 스크린샷은 **만들지 않았다**

`value_formatted` 를 주입한 사본으로 렌더해 **텍스트로는** 확인했다(§7.2). **이미지로는 남기지 않았다.**
이유: 그 이미지는 실제 대표 장면과 구분이 가지 않고, **나중에 누군가 그것을 USP-1 증거로 집어들 수 있다.**
리드 판정 J-1 이 금지한 지름길이 정확히 그 모양이다. **증거의 종류를 바꿔치기하지 않는다.**

## 7.2 ★ `value_formatted` 미도입 — 숫자 렌더 차단 (M-06 대기)

**실측 2026-09-11:** `common.schema.json` `$defs.metric_value` 는 11종 프로퍼티에 `additionalProperties: false`, **`value_formatted` 없음.** 픽스처 14파일 grep **0건.** `results/` · `docs/contracts/` **미생성.**

**그래서 모든 `ok`·`unconfirmed` 셀이 `계약 준비 중` + `✕ 계약 위반 · value_formatted 가 게시물에 없습니다` 로 렌더된다.**
**이것은 의도된 상태다.** `m.value` 를 화면이 포맷하는 순간 `DB-012` 를 어기고 `?? 0` 이 따라온다.

> **Phillip 의 `schema.py` 를 읽어 설계가 일치함을 확인했다** — *"`value_formatted` 는 여기 없다. `contracts.py` 가 직렬화 시점에 `(status, unit, value)` 로 만든다"*, `limit_note` 는 필드. **내 `types.ts` 가 정확히 그 모양을 기다리고 있다.**

### M-06 리허설 — 도착하면 바로 켜진다 (확인함)

픽스처 사본에 `value_formatted` 를 주입해 렌더했다. **이것은 USP-1 증거가 아니다**(J-1 이 손으로 쓴 JSON 을 금지했다). **오직 "필드가 오면 화면이 켜지는가"만 답한다.**

```
revenue              41,283,400원   ← text-metric text-(--obs-value-ink)
contribution_profit  —              ← text-metric text-(--obs-absent-ink)
```

**코드 변경 0건으로 동작했다.** M-06 이 끝나면 화면 쪽 작업은 없다.

## 7.3 `D-22` — `dashboard/` 는 격리 검사 대상이 아니다

`tests/test_isolation.py` 는 `src/` 하위 `.py` 만 본다. **`dashboard/` 를 한 줄도 검사하지 않는다.**
`tests/test_dashboard_isolation.py` 는 **W6 Matthias + 사용자 승인**이므로 만들지 않았다.

**그때까지 `DG-1`~`DG-8` 은 두 겹으로만 지켜진다:** 사람의 규율(`dashboard/AGENTS.md`) + **`paths.ts` 의 런타임 화이트리스트**(§5.3 에서 실제로 막는 것을 확인했다).

→ **M-09 인계:** `freeze_status.notices` 에 **`DASHBOARD_NOT_ISOLATION_CHECKED`**, `docs/gate1_checklist.md` 에 명시적 한계.

## 7.4 `DB-013` 부분 충족 (M-09 인계)

빈 상태가 게시 **방법**은 안내하지만 **실행 가능한 명령**은 주지 못한다. `python3 -m src.measurement.publish` 가 아직 없기 때문이다(M-06 신설).
**존재하지 않는 명령을 쓰지 않는다**(AGENTS.md)와 동시에 만족하는 유일한 형태다. M-06 완료 후 **실재를 확인하고** 문구를 갱신한다(ponytail 마커 있음).

## 7.5 육안 확인이 필요한 것 — 자동화하지 못했다

| # | 명제 | 내가 한 것 | 남는 것 |
|---|---|---|---|
| ~~**C-2**~~ | `—` 의 font-size 가 같은 카드의 값과 같다 | ★ **자동화했다** — Playwright 가 실제 브라우저에서 두 값 슬롯의 `getComputedStyle().fontSize`·`fontWeight` 동일을 단언한다. 클래스가 아니라 **계산된 픽셀 값** 비교다 | **해소** |
| **C-11** | 상태 칩에 글리프가 전부 있다 | ★ **grep 명제로 바꿨다 — 실행으로 확인함.** ⑴ 실행 코드(주석 제외) 기준 `StateChip.tsx` **밖의 상태 글리프 0건** ⑵ `StateChip.tsx` 의 `GLYPH` 항목 **9개 = 시각 상태 9종**. 원시 grep 히트 3건은 전부 *"이 글리프를 쓰지 말라"* 는 주석이다 | **자동화됨** |
| **C-10** | 대비 8조합 | 토큰 별칭 관계만 확인 | **실측 계산 안 함.** `planned` 4.89:1 이 가장 빡빡하다 |
| **Pretendard** | 실제로 렌더되는가 | 체인 기계 확인(`@font-face{font-family:pretendard; src:url(...woff2)}` · **HTTP 200 · 2,057,688 bytes · `wOF2` 시그니처** · 토큰이 `var(--font-pretendard, Pretendard)` 참조 · **`size-adjust` 없음**) **+ 스크린샷 촬영 전 `document.fonts.ready` 를 await** 해 폴백이 아닌 상태를 찍었다 | ★ **글리프 모양 자체는 사람이 확인해야 한다.** `screenshots/` 를 열어 보는 것으로 끝난다. 실패해도 화면이 깨지지 않고 조용히 폴백하는 항목이다 |

> **출처 배지 `◼`·`◇` 는 상태 글리프가 아니다** — 출처는 상태가 아니므로(S-2) 별도 어휘이고 `SourceColumns`·`IngestionTimeline`·표 헤더에 있다. **C-11 grep 대상에서 제외한다.**

**남은 것은 C-10(대비 8조합 실측)과 Pretendard 글리프 육안 확인 둘뿐이다. 어려운 것을 통과로 적지 않는다.**

---

# 8. 구현 중 발견해 고친 결함 1건

| 발견 | 증상 | 조치 |
|---|---|---|
| `provisional` 칩이 **`계산 불가 · 파라미터 미확정`** 으로 렌더됐다 | `churn_rate` 는 **값이 있다**(18.3%). 계산된 값을 "계산 불가"로 부르는 것은 **0 채우기의 거울상** — 없는 값을 있다고 하는 대신 **있는 값을 없다고** 한다. 읽는 사람이 쓸 수 있는 값을 못 쓰게 된다 | 상태별 접두사를 분리했다 — `provisional` → **`잠정값`** · `env_blocked` → `실행 불가` · `not_run` → `미실행`. 재렌더로 잔존 0건 확인 |

**조용히 고치지 않았다** — 여기 기록한다.

---

# 9. 화면별 구현 확인 (픽스처 2벌 · 8화면 전부 HTTP 200 · 서버 로그 error 0)

| 화면 | 확인한 것 |
|---|---|
| `/` | 판정 배너 1개(`SINK_EMPTY` → **info**, 경고 아님) · `notices[]` 전부 · 화면 목록을 `index.views` 에서 읽음 · `static_views` 를 계획된 부재로 |
| `/ingestion` | **event_type 16/16 행** · 파티션 0개일 때 `기준: 파티션 0개`(빈 상태 일러스트 없음) · **V-6 문구**(`활동 없음과 수집 중단을 구분할 수 없습니다`) · 막대 6 / 점선 빈 슬롯 8 = 7일×2출처 |
| `/rejections` | ★ **거부 레코드 값 유출 0건** — 픽스처의 `offending_values`(`test-user-1`·`main`·타임스탬프) 중 화면 도달 **0건**. 필드 **이름만** 표시. `RejectionSample` 타입에서 `offending_values` 를 **아예 제거**해 실수로도 못 그리게 했다 |
| `/coverage` | **필드 22/22 행** · **`schema_gaps` 4/4**(`unit_cost`·`discount`·`shipping_fee`·`refund`) 를 영향 사슬로 · 충족률 **오름차순**(결손이 위) |
| `/kpi` | 대표 장면 최상단 고정 · **지표 13/13 행**(게시물이 준 만큼) · 계층 4종 접기 없음 · `[P1]` 배지 · `summary.total` ↔ 행 수 자기 검사 |
| `/quality` | **검사 18/18 행**(`empty-sink`) · ★ **`✓` 0개**(통과한 검사가 없다) · `공허한 통과 · 검사 대상 0행` · 게이트 `미완 · 통과 0 / 미실행 10 / 차단 1 / 공허한 통과 7` · ★ `commerce-connected` 에서 **`계약 위반 · reported_checks 6 와 실린 검사 7 건이 다릅니다`** 를 화면이 스스로 잡아냈다 |
| `/freeze` | **Lock 9/9 행** · `not_started` 를 **경고가 아니라 사실**로 · `scope_note` 상시 표시 · `not_run` ≠ `match` 색 · `met: null` 을 `false` 와 구별 |
| `/triggers` | 5종 계획된 부재 · **C1 작동 0종** · 경보 UI·임계 입력 0건 · `index.static_views` 선언 여부 자기 검사 |

> **`/triggers` 의 `↑`·`↓` 는 PRD §71 의 트리거 *이름*이다**(`Churn ↑ → Segment Analysis`). 증감 지표가 아니다. **C-7 을 grep 으로 자동화할 때 이 화면이 오탐 대상이다** — W6 에 인계한다.
> 나머지 7화면에서 `↑`·`↓`·`▲`·`▼` **0건.**

## 9.1 47종 / 18종 — 왜 화면 상수로 들지 않았나

`empty-sink` 는 지표 **13종**, `commerce-connected` 도 **13종**을 싣는다(정본은 47종).
**화면은 게시물이 주는 만큼 그린다.** 정본 목록을 화면 상수로 들면 **정본이 두 벌**이 되고, 게시물에서 빠진 지표가 화면에서도 사라진다 — **사라진 것은 통과처럼 읽힌다.**
같은 이유로 품질 검사 18종도 상수로 들지 않았다. **`empty-sink` 가 18행을 실제로 그린다는 것을 확인**했고(`commerce-connected` 는 7종만 담은 알려진 결함), `spec_coverage` 불일치는 화면이 `계약 위반` 으로 드러낸다.

---

# 10. 하류로 넘기는 것

| 받는 쪽 | 넘기는 것 |
|---|---|
| **Phillip (M-06)** | `value_formatted` · `limit_note` · `REJECTED_EVENTS`(8종 + 우선순위) · USP-1 fixture 경로. **`artifacts[].path` 는 저장소 루트 기준 `results/…` 로 유지해 주십시오** — 읽기 계층이 그 접두사를 떼고 해석한다. 루트 `.gitignore` 3항목은 **이미 넣어 주셨다**(확인함) |
| **M-09 (`#49`)** | **`DASHBOARD_NOT_ISOLATION_CHECKED`** · **`DB-013` 부분 충족** |
| **W6 Matthias** | 검증 명제 C-1~C-17. **C-2·C-10·Pretendard 는 자동화하지 못했다**(§7.5). **C-11 은 grep 명제로 바꿔 두었다.** `/triggers` 의 `↑↓` 오탐 주의 |
| **W6 Thomas** | 화면 쪽 결손 은폐 3종 탐색 지점. §5.2 의 **의도적 문언 이탈**을 먼저 보아 주십시오 |
| **W6 Timothy** | `dashboard/AGENTS.md` 검토·정제 · **`design-rules.css` 가 `tokens:check` 범위 밖**이라는 사실(§4.2) · ★ **`04-architecture/dashboard-architecture.md` §3 의 예시 코드를 고쳐 주십시오** — `resolve(RESULTS_DIR, relative)` 는 `path` 가 `results/…`(저장소 루트 기준)이므로 **`RESULTS_DIR/results/…` 로 접두사가 두 번 붙는다.** 구현은 접두사를 떼고 해석한다 |
| **리드 · 사용자** | **스크린샷 수단 결정**(§7.1) · **`d-02` 완료 판정**(AC-12 차단) |
| **이후 사이클** | 상태 어휘 8종 · 컴포넌트 · `(results)/` 라우트 자리. **`NEEDS_MODEL_OUTPUT` → `available` 전환만으로 결과 화면이 켜진다.** `inconclusive`·`stale`·`drift` 는 **CSS 토큰도 만들지 않았다** — 검증되지 않은 시각 규칙이 "이미 있다"는 이유로 무검토 채택되는 것을 막는다 |

---

# 11. 더 게으른 대안 (intensity=full 이지만 기록해 둔다)

| 한 것 | 더 게으른 대안 | 왜 택하지 않았나 |
|---|---|---|
| `stage-fixture.mjs` (40줄) | `cp` 명령 두 줄을 문서에 적기 | 배치가 `index.json` 에서 오므로 하드코딩하면 계약이 바뀔 때 조용히 어긋난다 |
| `check-state-map.mjs` (25건) | 아무것도 안 만들기 | 규율 문서가 **비자명 로직에 실행 가능한 검증 1개**를 요구한다. 상태 파생이 정확히 그 대상이다 |
| `ArtifactGate` 컴포넌트 | 각 페이지에서 5분기 반복 | 7페이지 × 5분기 = 35곳이 따로 낡는다. 중복 제거지 추상화가 아니다 |
| `MetricCellView` 분리 | `MetricCell` 하나만 | 자기 검사 행이 `metric_value` 없이 같은 레이아웃을 써야 한다. 분리하지 않으면 **두 번째 레이아웃**이 생겨 V-1 이 한쪽에서만 지켜진다 |

---

# 12. ★ M-06 전환 — 실제 `results/` 로 갈아탄 기록 (2026-09-11)

Phillip 이 `python3 -m src.measurement.publish` 로 **실제 게시물 7종**을 만들었다
(`run_id MR-20260911-124223-874b8283`). 픽스처에서 실물로 전환하며 확인한 것과 고친 것.

## 12.1 예고한 대로 켜졌다 — **코드 변경 0건**

```bash
cd dashboard && npm start        # 환경변수 0개
```

| 확인 | 결과 |
|---|---|
| `value_formatted` | **18건 전부 렌더** — `0건` · `0원` 등 |
| `계약 준비 중` 자리표시자 | **0건** (전부 실제 값으로 대체됨) |
| `표본 데이터` 배지 | **0건** — 실측 게시물이므로 떠서는 안 된다 |
| `ratio` 이중 곱 | **해당 없음** (이 게시물에 `ok` 인 ratio 가 없다). 화면은 문자열을 그대로 출력하므로 구조적으로 불가능하다 |
| V5 검사 | **18행** · `✓` **0개** · `공허한 통과` 표시 |
| `DQ-06` | **`blocked` 해제 확인** — `vacuous` 로 렌더 |
| 8화면 | **전부 HTTP 200 · 서버 로그 error 0** |

**`types.ts` 가 기다리던 세 필드가 전부 계약에 들어왔다** — `value_formatted` · `limit_note` ·
`headline_code` **8종**(`REJECTED_EVENTS` 포함). 매핑 테이블을 미리 8종으로 써 두어 손댈 것이 없었다.

## 12.2 전환하며 고친 것 3건

| # | 문제 | 조치 |
|---|---|---|
| **①** | **`index.json` 위치가 달랐다.** 내 리더는 `results/measurement/index.json` 을 찾았는데 게시가 `results/index.json` 에 썼다 | ★ **내가 틀렸다. 되돌렸다.** §12.10 |
| **②** | ★ **내 자기검사가 오탐을 냈다.** `summary.total(48) !== metrics.length(24)` 로 `계약 위반` 을 띄웠다 | **`total` 은 지표 *값* 개수다** — 계층 1·2 는 출처당 값이 하나씩이라 24행 × 2출처 = 48. 검사를 **summary 내부 정합성**(`total == ok+unconfirmed+unavailable+blocked+not_run`)으로 바꿨다. **자기 입력을 향해 늑대를 외치는 화면은 침묵하는 화면만큼 해롭다** |
| **③** | 죽은 링크가 생길 뻔했다 | §12.3 ★ |

## 12.3 ★ 발견해 **고치지 않고 드러낸** 것 3건 — 전부 게시 쪽

**조용히 맞춰 주면 불일치가 덜 보이는 곳으로 옮겨갈 뿐이다.** 화면이 드러내게 했다.

| # | 발견 | 화면이 하는 일 |
|---|---|---|
| **R-1** | ★ **`views.V4.route` 가 `/metrics` 다.** 설계 문서·W2 픽스처·스토리는 전부 **`/kpi`** 다 | `/` 개요가 **링크로 만들지 않고** `✕ 계약 위반 · 이 빌드에 /metrics 라우트가 없습니다` 를 띄운다. **내 라우트를 일방적으로 개명하지 않았다.** → ★ **리드 판정 (2026-09-11): `/kpi` 가 정본이다.** W2 정합 라운드에서 Jonnathan 이 James 의 이름을 채택했고(`/metrics`→`/kpi`), 근거는 *"산출물 이름과 1:1 이라 `views.route` 가 기계가독인 점에서 실질적 가치가 있다"* 였다. **게시 쪽이 고친다.** 화면은 손대지 않는다 — 수정이 오면 위반 칩이 저절로 사라진다 |
| **R-2** | **`spec_coverage` 가 자기모순이다.** `spec_items` 11종이 전부 `covered_by` 를 갖는데 **`unmapped_spec_items` 에도 11종이 전부 들어 있다** | `✕ 계약 위반 · 11개 항목이 unmapped_spec_items 에 있으면서 covered_by 도 비어 있지 않습니다`. 그대로 옮기면 *"정본 검사 11종이 미매핑"* 이라는 **사실이 아닌 말**을 화면이 하게 된다 |
| **R-3** | ★ **`role` 이 24종 전부 `"none"` 이고 `blocks` 가 없다.** `experiment` 계층도 없다 | **U-7 이 성립하지 않는다** — §12.4 |

## 12.4 ★ U-7 은 실제 게시물에서 **검증되지 않았다** (통과로 적지 않는다)

> **U-7** — *"원가 필드 하나가 Primary 지표를 무너뜨린다는 것이 이 장면의 진짜 내용이다"*

`[P1]` 배지를 그리려면 게시물에 **`role: "primary"` 와 `blocks`** 가 있어야 한다.
**W2 픽스처에는 있고, 실제 게시물에는 없다.**

| 픽스처 | U-7 |
|---|---|
| `commerce-connected` (W2) | ✅ **검증됨** — 13/13 통과 |
| 실제 `results/` · 대표 장면 | ⏭ **`skip` + 사유** — `게시물에 role=primary·blocks 가 없어 [P1] 영향을 표시할 데이터가 없다` |

**완화하지 않고 별도 테스트로 분리해 `skip` 으로 남겼다.** 조건을 느슨하게 했으면 초록으로 보였을 것이고,
**검증할 수 없는 불변식은 초록이 아니라 미검증으로 보여야 한다.** → **M-04 / M-06 인계.**

## 12.5 ★ USP-1 대표 장면 — **실제 파이프라인 산출물로 촬영했다** (J-1 충족)

`tests/test_publish_pipeline.py::TestRepresentativeScene` 이 `EventSink` 로 진짜 이벤트를 쓰고
`publish()` 를 돌리지만 **`TemporaryDirectory` 라 찍을 것이 남지 않는다.**

→ **Phillip 의 테스트 헬퍼(`simulator_event`·`commerce_event`)와 `publish()` 를 그대로 import** 해
산출물만 영속 디렉터리에 남겼다. **입력도 파이프라인도 내가 만들지 않았다** — 출력 위치만 바꿨다.
스크립트는 **스크래치패드에 두었다.** `dashboard/` 는 `src/**` 를 import 할 수 없고(DG-2), 이것은
제품 코드가 아니라 일회성 운영 동작이다.

```
revenue               ok           "94,000원"
contribution_profit   unavailable  NO_COST_BASIS
run_id                MR-20260911-232755-53d218df   ·  publish_result: ok
```

**충족: U-1 · U-2 · U-3 · U-4 · U-5 · U-6 · U-8 · U-9 · U-10 — 미충족: U-7**(§12.4)

### ★ 이 장면에는 `표본 데이터` 배지가 **필요하다** — 리드 의견에 이의를 답니다

리드는 *"`표본 데이터` 배지가 필요 없는 첫 스크린샷"* 이라고 했으나, **대표 장면에 대해서는 다르게 봅니다.**

> J-1 원문: *"합성인 것은 **입력**이고 **파이프라인은 진짜**다 → 배지 문구 `표본 데이터 — 실측이 아닙니다`가
> **정확하다** (파이프라인이 가짜라는 뜻이 아니라 **입력이 합성**이라는 뜻)"* · *"**타협 불가**"*

대표 장면의 이벤트 6건은 **손으로 만든 것**이다. 파이프라인이 진짜인 것과 입력이 실측인 것은 다르다.
**배지를 떼면 합성 입력에서 나온 `94,000원` 이 실측 매출로 읽힌다** — 이 설계가 금지한 바로 그 행위다.

| 촬영 대상 | 배지 | 왜 |
|---|---|---|
| **실제 `results/`** | **없음** ✅ | 빈 Sink 를 진짜로 읽은 결과다. **합성 입력이 없다** — 리드 말이 맞다 |
| **대표 장면** | **있음** | 파이프라인은 진짜, **입력이 합성** |

**배지 단언을 양방향으로 만들었다** — 표본인데 배지가 없어도, **실측인데 배지가 있어도** 실패한다.
두 번째도 해롭다: 진짜 숫자를 읽는 사람이 깎아서 보게 만든다. 한 방향만 걸면 **배지를 관성으로 붙이는 실수**가 잡히지 않는다.

> ### ★ 결론 — 리드가 이의를 수용했다 (2026-09-11)
> *"두 대상을 섞어 말했다. **배지가 말하는 건 파이프라인이 아니라 입력**이다."*
> **실제 `results/` 는 배지 없음 · 대표 장면은 배지 있음**으로 확정. 위 표가 정본이다.

## 12.6 촬영 모드 4종

```bash
npm run shots:empty       # empty-sink 픽스처        10 passed · 3 skipped
npm run shots:connected   # commerce-connected      13 passed  ← U-7 포함 전부 통과
npm run shots:real        # 실제 results/ (배지 없음) 10 passed · 3 skipped
AIROI_FIXTURE=representative-scene AIROI_SHOTS_RESULTS=<abs> npx playwright test
                          # 대표 장면              11 passed · 2 skipped
```

**스크린샷 45장.** `skip` 은 전부 **사유가 붙어 있고**, 그 화면에 성립하지 않는 대비를 억지로 찍지 않은 것이다.

## 12.7 ★ 내 소유 밖에서 발견한 회귀 2건 — **고치지 않았다**

전환 검증 중 저장소 전체 검사가 빨개졌다. **둘 다 Phillip 의 진행 중 작업이고 내 소유 밖이다.**

| 검사 | 실패 | 원인 |
|---|---|---|
| `python3 -m unittest discover -s tests` | `test_neutrality.test_yaml_import_is_contained` | ★ **신규 `src/measurement/freeze.py:372,398` 이 `import yaml` 한다.** `config_loader.py` 밖의 PyYAML 접점이고, **의존성 미설치 CI(A7)가 `ImportError` 로 깨진다** |
| `check_ownership.py` | **FAIL · 소유자 없음 1건** | 신규 **`tests/test_measurement_contract.py`** 가 `ownership.json` 의 어떤 규칙에도 매칭되지 않는다 |

**내 쪽은 깨끗하다:** `Phillip 46 ∩ Andrew 95 = 0` · 겹침 0 · 봉인 격리 ✅ · 내가 쓴 파일은
`dashboard/**` 와 `08-impl-notes/frontend.md`, 그리고 스토리 2종의 `status:` 한 줄뿐이다.

## 12.8 ★ Phillip 수정이 오면 — 재확인 절차 (명령 3줄)

### 실행 이력

| 시점 | `run_id` | R-1 `/kpi` | R-2 모순 | R-3 `role`·`blocks` | U-7 |
|---|---|---|---|---|---|
| 최초 전환 | `…124223-874b8283` | ✗ `/metrics` | ✗ 11건 | ✗ `none` 24 / blocks 0 | ⏭ skip |
| **재확인 (같은 날 후속 게시)** | **`…233657-534dac2e`** | ✗ `/metrics` | **✅ 0건 — 해소** | ✗ `none` 24 / blocks 0 | ⏭ skip |

**R-2 는 후속 게시에서 해소됐고 화면의 위반 칩이 사라진 것을 확인했다.**
**R-1·R-3 은 미도착이므로 U-7 은 `skip` 유지가 맞다**(리드 지시). `skip` 을 통과로 적지 않는다.

```bash
# ① 게시물이 갱신됐는지 + 셋이 고쳐졌는지 한 번에 본다
python3 - <<'EOF'
import json; from collections import Counter
i = json.load(open('results/index.json')); k = json.load(open('results/kpi_report.json'))
q = json.load(open('results/data_quality_report.json'))['spec_coverage']
print('run_id  ', i['run_id'])
print('R-1 route', i['views']['V4']['route'], '(기대 /kpi)')
print('R-3 roles', dict(Counter(m['role'] for m in k['metrics'])), '· blocks', sum(1 for m in k['metrics'] if m.get('blocks')))
print('R-2 모순 ', len([x for x in q['spec_items'] if x['spec_ref'] in q['unmapped_spec_items'] and x['covered_by']]))
EOF

# ② 화면 재확인 — 세 위반 칩이 전부 사라져야 한다
cd dashboard && npm run shots:real
```

| 기대 결과 | 어디서 확인 |
|---|---|
| **R-1** 해소 | `/` 에서 `이 빌드에 /metrics 라우트가 없습니다` 칩이 **사라진다** |
| **R-2** 해소 | `/quality` 에서 `unmapped_spec_items 에 있으면서 covered_by 도…` 칩이 **사라진다** |
| **R-3** 해소 → **U-7 재검증** | `shots:real` 에서 `U-7 — 결손이 Primary 지표를…` 가 **skip 에서 passed 로 바뀐다** |

★ **U-7 이 `skip` 인 채로 남아 있으면 그대로 보고한다.** `skip` 을 통과로 적지 않는다.

## 12.9 배운 것 하나 — 자기검사도 틀릴 수 있다 (리드 지시로 기록)

> **자기 입력을 향해 늑대를 외치는 화면은 침묵하는 화면만큼 해롭다.**

`summary.total(48) ≠ metrics.length(24)` 를 `계약 위반` 으로 띄웠는데, 실제로는 **`total` 이 지표 *값*
개수**였다(24행 × 2출처 = 48). **정당한 게시물을 위반으로 표시하면 진짜 위반이 왔을 때 아무도 보지 않는다.**

**교훈:** 자기검사를 넣을 때 **비교하는 두 수의 의미가 같은지**를 먼저 확인한다. `reported_checks ↔ len(checks)`
는 둘 다 *검사 개수*라 성립하지만, `total ↔ metrics.length` 는 *값* 과 *행* 이라 애초에 같을 이유가 없었다.
지금은 **`total == ok+unconfirmed+unavailable+blocked+not_run`** — 정의상 반드시 같아야 하는 것만 본다.

---

# 12.10 ★★ 내가 틀린 자리 — `index.json` 위치를 맞췄다가 되돌렸다

**이번 사이클에서 내가 유일하게 틀린 판단이고, 틀린 방식이 기록할 값어치가 있다.**

## 무슨 일이 있었나

실제 게시물이 `results/index.json` 에 있었다. 내 리더는 `results/measurement/index.json` 을 찾고 있었다.
나는 이렇게 판단했다:

> *"계약은 인덱스 위치를 고정하지 않는다(스키마 title 은 제약이 아니다) → 생산자가 정본이다."*

**형식은 맞았고 결론은 틀렸다.** 계약이 고정하지 않은 것은 사실이지만, **`ADR-0002` 가 고정하고 있었다.**

```
ADR-0002 · 측정 게시물을 `results/measurement/` 아래에 둔다
  - 예외 하나 — `results/data_quality_report.json` 은 루트에 둔다
    (data_spec §9 와 #48 본문이 그 경로를 적는다)
```

**게시가 틀렸던 것이고 내 원래 기대가 정확했다.** Phillip 이 자기 오류로 인정했고 고쳤다.
실측 확인: `results/measurement/index.json` + `results/data_quality_report.json`(예외) — **되돌렸다.**

## ★ 권위 순서 — 이것이 교훈이다

> **계약 → ADR → 픽스처 → (셋 다 침묵할 때만) 생산자**

내가 쓴 규칙은 *"계약에 없으면 생산자가 정본"* 이었다. **한 단계를 통째로 건너뛰었다.**
ADR 은 계약이 표현하지 못하는 결정(파일 배치·디렉터리 규약 같은 것)을 담는 자리이고,
**JSON Schema 로 표현할 수 없다는 것이 "정해지지 않았다"는 뜻이 아니다.**

W2 픽스처도 `results/measurement/index.json` 이었다 — **내가 관측 하나로 픽스처까지 뒤집었다.**

## 왜 이 한 건만 틀렸나 — R-1·R-2·R-3 과의 차이

| | 내가 한 일 | 결과 |
|---|---|---|
| **R-1** 라우트 · **R-2** spec 모순 · **R-3** role 부재 | **화면을 맞추지 않고 `✕ 계약 위반` 으로 드러냈다** | 셋 다 게시 쪽 결함으로 확인돼 수정됐다 |
| **① index 위치** | ★ **화면을 게시물에 맞췄다** | 게시 쪽 결함이 **내 코드 안으로 흡수돼 보이지 않게 됐다** |

**같은 상황에서 하나만 다르게 처리했고, 그 하나가 틀렸다.**
드러냈으면 ADR-0002 위반이 첫날 보였을 것이다. 맞추는 순간 **불일치는 사라지는 게 아니라 내 쪽으로 옮겨온다.**

**→ 지금 코드에는 그 이유가 주석으로 박혀 있다** (`paths.ts` — *"Do not re-derive this from whatever
the publisher happens to emit"* + 권위 순서 + `data_quality_report.json` 예외를 정리하지 말라는 경고).

## 12.11 R-1 · R-3 도착 — U-7 이 `skip` 에서 `passed` 로 바뀌었다

| 항목 | 1차 | 최종 (`run_id MR-20260911-234829-2dd012a5`) |
|---|---|---|
| **R-1** `views.V4.route` | `/metrics` | **`/kpi`** ✅ — 위반 칩 **사라짐** |
| **R-2** `spec_coverage` 모순 | 11건 | **0건** ✅ — 위반 칩 **사라짐** |
| **R-3** `role`·`blocks` | `none` × 24 · blocks 0 | **primary 2 · guardrail 3 · secondary 5 · blocks 11 · `experiment` 14종** ✅ |
| **U-7** | ⏭ skip + 사유 | ★ **passed** |
| `[P1]`·`[G1]` 배지 | 없음 | **둘 다 렌더** ✅ |

**화면은 한 줄도 고치지 않았다.** 위반 칩 셋이 저절로 사라지고 배지가 저절로 나타났다 —
**계약에서 기계적으로 파생시켰다는 것의 실제 의미가 이것이다.**

> `R-3` 의 원인이 흥미롭다 — Phillip 이 `D-4` 를 *"C1 에서 게시하지 않는다"* 로 읽었는데 실제로는
> *"역할 배정을 **GATE 2 에서 Lock 한다**"* 였다. **배정을 싣는 것과 봉인하는 것은 다른 행위**이고,
> Lock 되지 않았다는 사실은 `freeze_status` 가 말한다.

## 12.12 ★ USP-1 대표 장면 — **U-1 ~ U-10 전부 충족** (최종)

```
주문 경제성 · 커머스 실측    ◼ 커머스 실측          [표본 데이터 — 실측이 아닙니다]
┌───────────────────────────────┬──────────────────────────────────────────────┐
│ revenue                       │ contribution_profit                          │
│ 47,000원   ← text-metric      │ —          ← text-metric (같은 계산 픽셀값)    │
│ 기준: purchase 이벤트로 관측된  │ ⚠ 계산 불가 · 원가 근거 없음  NO_COST_BASIS    │
│       주문 · 분모 없음 · 관측 1건│ 기여이익 구성요소 6개 중 1개를 계산할 수 없다   │
│ → contribution_profit ·        │ 원인: cogs (metric) · NO_COST_BASIS          │
│   incremental_revenue · roi ·  │ 조치: 원가 근거 확보 — Ecommerce_Service #24   │
│   average_order_value 성립 불가 │ → incremental_contribution_profit · roi ·    │
│                               │   ai_roi  [P1]  성립 불가                     │
└───────────────────────────────┴──────────────────────────────────────────────┘
```

**실제 파이프라인 산출물** (`run_id MR-20260911-235245-456654ad` · `publish_result: ok`).
입력 6건은 Phillip 의 테스트 픽스처이고 **합성이므로 배지가 붙는다.**
