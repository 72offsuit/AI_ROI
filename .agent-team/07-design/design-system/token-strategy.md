# T2.15 — 디자인 토큰 전략 · `Ecommerce_Service` 파이프라인 read-only 조사

**작성** Jonnathan (Role 7 · Chief Designer) · 2026-09-11 · 사이클 **C1**
**조사 방식** read-only. `Ecommerce_Service` **파일 변경 0건** (§6에 `git status` 증명)
**정본** `Plan/DESIGN.md` · 근거 PRD §69 (Next.js 확정 근거) · SRS `DB-001`

---

# 0. 판정 한 줄

> ### 재사용 가능하다. **생성 스크립트를 복제(vendor)하고, 공유 npm 패키지는 만들지 않는다.**
>
> 결정적 근거: **두 저장소가 가리키는 `Plan` 서브모듈 커밋이 동일하고, `Plan/DESIGN.md`가 바이트 단위로 같은 파일이다** (§2.2 실측).
> 따라서 이것은 "토큰 값을 옮기는" 작업이 아니라 **같은 입력 파일에 같은 생성기를 돌리는** 작업이다. PRD §69가 막으려던 **토큰 이중 정의가 원리적으로 발생하지 않는다.**

---

# 1. 파이프라인 실측 — 무엇이 어떻게 동작하는가

## 1.1 구성 — 4개 파일, 약 150줄

| 파일 | 줄 수(약) | 역할 |
|---|---|---|
| `scripts/design-tokens.mjs` | 32 | CLI. `--check`·`--input`·`--output` 파싱 → 생성 또는 대조 |
| `scripts/tokens/resolve.mjs` | 75 | `DESIGN.md` frontmatter YAML 파싱 · `{참조}` 해석 · 순환 참조 검출 · 이름 검증 |
| `scripts/tokens/render.mjs` | 36 | CSS 출력 — `:root` 변수 · Tailwind `@theme inline` · 타이포그래피 `@utility` |
| `scripts/tokens/verify.mjs` | 62 | 파이프라인 자체의 테스트 15 시나리오 (tmpdir에서 실행, 저장소를 건드리지 않음) |

의존성은 **`js-yaml` 하나뿐이고 devDependency**다. 런타임 의존 0.

## 1.2 동작

```
Plan/DESIGN.md  (frontmatter YAML)
      │  npm run tokens:generate   →  node scripts/design-tokens.mjs
      ▼
src/styles/tokens.generated.css   (306줄)
      │  @import
      ▼
src/app/globals.css  →  Next.js
```

```json
"tokens:generate": "node scripts/design-tokens.mjs",
"tokens:check":    "node scripts/design-tokens.mjs --check",
"tokens:test":     "node scripts/tokens/verify.mjs",
"predev":          "npm run tokens:generate",
"prebuild":        "npm run tokens:generate",
```

`predev`·`prebuild`로 **dev·build 전에 자동 생성**된다. 수동 실행을 잊어도 드리프트가 생기지 않는다.

## 1.3 무엇을 보장하는가 — `verify.mjs` 15 시나리오

**내가 직접 실행해 확인했다** (2026-09-11, `npm run tokens:test` → `15 scenarios passed`).

| 보장 | 시나리오 |
|---|---|
| 출력 부재를 `--check`가 거부한다 | `missing output is rejected by check` |
| 정본이 바뀌면 `--check`가 **출력을 덮지 않고** 실패한다 | `changed source is detected without rewriting` |
| 멱등 — 반복 생성이 mtime까지 보존한다 | `repeated generation succeeds` |
| 별칭이 값 복사가 아니라 **`var()` 참조**로 남는다 | `scalar aliases preserve variable references` |
| 객체 참조가 속성으로 전개된다 | `object references expand into properties` |
| 순환 참조 검출 (스칼라·객체 양쪽) | `scalar cycle` · `object cycle` |
| 없는 참조 · 잘못된 YAML · 중복 키 · frontmatter 부재 · 타이포그래피 필수 속성 누락 | 각 거부 |

> **`scalar aliases preserve variable references`가 이 파이프라인의 핵심 성질이다.** `surface: "{colors.background}"`가 `#FFFFFF`로 **펼쳐지지 않고** `var(--ds-colors-background)`로 남는다. 즉 **생성물 안에서도 값이 한 곳에만 존재한다.** 토큰 이중 정의 금지가 출력 파일 내부까지 관철된다.

`npm run tokens:check`도 실행해 `디자인 토큰이 정본과 일치합니다`를 확인했다. **두 명령 모두 현재 통과한다.**

---

# 2. 재사용 판정 근거

## 2.1 입·출력이 CLI 인자다 — 코드 변경 0

```js
const input  = resolve(root, values.input  ?? "Plan/DESIGN.md");
const output = resolve(root, values.output ?? "src/styles/tokens.generated.css");
```

`AI_ROI`에서 `dashboard/`가 Next.js 앱이면 `Plan/`은 **저장소 루트**(`dashboard/`의 부모)에 있다. 기본값만 바꾸면 된다:

```json
"tokens:generate": "node scripts/design-tokens.mjs --input ../Plan/DESIGN.md --output src/styles/tokens.generated.css"
```

**스크립트 본문을 한 줄도 고치지 않는다.** 경로 유연성이 이미 설계되어 있다.

## 2.2 ★ 실측 — 두 저장소의 정본이 동일한 파일이다

```
Plan 서브모듈 커밋 (Ecommerce_Service)  c46aee5eed00193b9331403645b8dbccaef52278
Plan 서브모듈 커밋 (AI_ROI)             c46aee5eed00193b9331403645b8dbccaef52278
sha256 Plan/DESIGN.md (양쪽 동일)       f4dc7ba935b545b665446cbcfe738d25f2ccc3e46d3b8946a8111619f7b4e91b
```

**이것이 판정의 핵심 근거다.** `Plan/DESIGN.md`의 *"두 서비스는 `Plan` 서브모듈을 통해 같은 문서를 참조하고, 각 저장소가 가리키는 `Plan` 커밋 SHA로 적용 버전을 확인합니다"* 가 **현재 실제로 성립해 있다.**

→ 생성기를 복제해도 **토큰은 복제되지 않는다.** 복제되는 것은 150줄의 변환 코드이고, 값의 정본은 한 파일뿐이다.

## 2.3 대시보드 전용 토큰이 이미 정본에 있다

PRD §69가 Streamlit을 기각한 근거로 든 토큰이 생성물에 실재함을 확인했다:

| 토큰 | 생성된 CSS 변수 |
|---|---|
| `dashboard-max` 1440px | `--ds-spacing-dashboard-max` · `--container-dashboard-max` |
| `dashboard-sidebar` 224px | `--ds-spacing-dashboard-sidebar` |
| `metric-card` | `--ds-components-metric-card-{background-color,padding,rounded,text-color}` |
| `metric` 2rem/700/tnum | `@utility text-metric` (`font-feature-settings: tnum`) |
| `table-number` | `@utility text-table-number` |

**대시보드용 토큰을 새로 만들 필요가 없다.** 관측 화면군에 필요한 상태 토큰만 추가하며, 그것도 전부 별칭이다(`state-tokens.css`).

---

# 3. 방식 3안 비교

| | ⑴ **스크립트 복제 (추천)** | ⑵ 공유 npm 패키지 | ⑶ 재구현 |
|---|---|---|---|
| 무엇을 | 4개 파일을 `dashboard/scripts/`로 복사, 인자만 조정 | `@72offsuit/design-tokens` 발행 | AI_ROI에서 새로 작성 |
| 토큰 이중 정의 | **없음** — 입력이 같은 파일 (§2.2) | 없음 | 없음 |
| 저장소 간 런타임 의존 | **없음** | **생긴다** | 없음 |
| AGENTS.md 적합 | *"런타임 의존은 **없다**"* 와 일치 | **충돌** | 일치 |
| 초기 비용 | 파일 4개 복사 + 인자 2개 | 패키지 설정·레지스트리·버전 정책 | 150줄 재작성 + 테스트 |
| 유지 비용 | **생성기 드리프트 위험** (§3.1) | 버전 동기화·발행 절차 | 두 구현이 완전히 갈라진다 |
| 검증 | `verify.mjs` 15 시나리오가 같이 온다 | 동일 | **새로 써야 한다** |

## 3.1 ⑴의 유일한 위험과 대응

**위험:** `Ecommerce_Service`의 생성기가 개선되면 `AI_ROI` 복제본이 뒤처진다. 두 저장소가 같은 `DESIGN.md`에서 **다른 CSS**를 만들 수 있다.

**대응 3단:**
1. 복제 파일 머리에 **출처 주석** — 원본 경로 + 복사 시점 `Ecommerce_Service` 커밋 SHA. 대조 지점이 생긴다
2. `verify.mjs`를 함께 복제한다. 15 시나리오가 **복제본의 동작을 고정**한다
3. **`AI_ROI` CI에 `tokens:check`를 넣는다** — §5

**기각 근거 요약:** ⑵는 150줄을 아끼려고 AGENTS.md가 명시한 "런타임 의존 없음"을 깨뜨린다. ⑶는 검증된 15 시나리오를 버리고 같은 것을 다시 만든다 — ETHOS "이미 한 줄로 존재하는 것을 완전하게 다시 만드는 것이 최악"에 정확히 해당한다.

> **사용자·리드 결정 여지:** 두 저장소의 UI 코드를 장기적으로 공유할 계획이 있다면 ⑵가 맞을 수 있다. **그 계획은 내가 모른다.** `Plan/DESIGN.md`도 *"공유 토큰·UI 코드의 배포 여부는 대시보드 스택 확인 후 정합니다"* 로 열어두었다 — **스택이 확정됐으므로 지금이 그 결정 시점이다.**

---

# 4. 복제 시 반드시 같이 가져가야 하는 것 — 빠뜨리면 조용히 깨진다

## 4.1 `design-rules.css`는 **생성물이 아니다**

`src/styles/design-rules.css`는 손으로 쓴 파일이고 `DESIGN.md` **본문**(frontmatter 아님)에서 온 값을 담는다:

| 값 | `DESIGN.md` 본문 근거 |
|---|---|
| `--ds-shadow-popover: 0 4px 16px rgb(0 0 0 / 0.08)` | Elevation & Depth |
| `--ds-shadow-dialog: 0 12px 32px rgb(0 0 0 / 0.14)` | 동일 |
| `--ds-color-backdrop: rgb(0 0 0 / 0.40)` | 동일 |
| `--ds-focus-width/offset: 2px` | Colors — 포커스 규정 |
| `--ds-motion-duration: 120ms` · `ease-out` | Components — 전환 |
| `--ds-layer-*` 6단계 | Elevation — 레이어 순서 |
| `prefers-reduced-motion` → `0ms` | *"감소된 모션 설정에서는 불필요한 전환을 제거"* |

> **⚠ 발견 — `tokens:check`가 이 파일을 검사하지 않는다.**
> `--check`는 `tokens.generated.css`만 정본과 대조한다. `DESIGN.md` **본문**의 그림자·모션 규정이 바뀌면 `design-rules.css`는 **조용히 뒤처지고 아무 검사도 실패하지 않는다.**
>
> "정본 일치 검증 파이프라인이 동작한다"는 서술은 **frontmatter YAML 범위에서만 정확하다.** 본문 유래 값은 검증 범위 밖이다.
> → 복제 시 이 파일도 가져가고, **한계를 문서에 남긴다.** 본문 유래 값의 자동 검증은 C1 범위 밖(파서가 달라진다)이며 **거짓 안심을 만들지 않기 위해 "검증된다"고 쓰지 않는다.**

## 4.2 Pretendard 로딩 — 없으면 조용히 대체 글꼴이 된다

`resolve.mjs`는 `fontFamily: Pretendard`를 이렇게 바꾼다:

```js
if (path.endsWith(".fontFamily") && value === "Pretendard") {
  return 'var(--font-pretendard, Pretendard), -apple-system, BlinkMacSystemFont, system-ui, sans-serif';
}
```

**`--font-pretendard`를 정의하는 것은 생성기가 아니라 앱이다.** `Ecommerce_Service`의 `layout.tsx`:

```tsx
const pretendard = localFont({
  src: "../../node_modules/pretendard/dist/web/variable/woff2/PretendardVariable.woff2",
  variable: "--font-pretendard", weight: "100 900", display: "swap", adjustFontFallback: false,
});
```

> **⚠ 이것이 가장 놓치기 쉬운 지점이다.** `--font-pretendard`가 없어도 **CSS는 유효하고 화면은 깨지지 않는다** — fallback 체인이 작동해 시스템 글꼴로 렌더된다. 즉 **실패가 보이지 않는다.**
> `dashboard/`는 ⒜ `pretendard` 패키지 의존 ⒝ `localFont` 설정 ⒞ `--font-pretendard` 변수명 **세 가지를 모두** 복제해야 한다. 하나라도 빠지면 Pretendard가 아닌 화면이 Pretendard인 것처럼 보인다.
>
> `Plan/DESIGN.md`도 같은 것을 요구한다: *"실제 UI 적용 시 공식 배포본의 버전을 고정하고 웹폰트 로딩 실패 시에도 한국어와 숫자가 표시되도록 합니다."*
> → **`design-handoff.md` 확인 항목**으로 올린다. 육안 확인이 필요하다(글꼴은 자동 검사가 어렵다).

## 4.3 Tailwind v4 전제

`render.mjs`는 `@theme inline`·`@utility`를 출력한다 — **Tailwind v4 문법**이다. 재사용하면 `dashboard/`도 Tailwind v4를 쓴다.

| 함의 | 판단 |
|---|---|
| npm 의존 추가 — `tailwindcss ^4` · `@tailwindcss/postcss` · `js-yaml`(dev) | 불가피하되 **`Ecommerce_Service`와 동일 선택**이므로 새 결정이 아니다 |
| **가정 A7(격리 CI가 표준 라이브러리 전제)와 무관** | npm 측이다. `tests/test_isolation.py`는 Python `src/`만 본다. **Python 의존성 매니페스트(T2.9)와 별개 축** |
| Tailwind 없이 쓸 수 있는가 | `:root` 변수 블록만 쓰면 가능하나 `@theme`·`@utility`가 사문화된다. **권고하지 않는다** |

---

# 5. CI — `AI_ROI`가 원본보다 강하게 만들 수 있는 지점

## 5.1 실측 — `Ecommerce_Service`에는 CI가 없다

```
.github/PULL_REQUEST_TEMPLATE.md
.github/ISSUE_TEMPLATE/bug_report.md
.github/ISSUE_TEMPLATE/task.md
```

**`.github/workflows/`가 존재하지 않는다.** 따라서 `tokens:check`·`tokens:test`는 **로컬 `predev`/`prebuild` 훅으로만** 강제되고 **CI에서 검증되지 않는다.**

`AI_ROI`에는 CI가 있다 — `.github/workflows/isolation.yml`(AGENTS.md 확인).

## 5.2 권고

> **`dashboard/`가 생긴 뒤, `AI_ROI` CI에 `tokens:check`(필요시 `tokens:test`)를 추가할 것을 권고한다.**
> 효과: `Plan` 서브모듈 포인터가 움직였는데 생성 CSS를 다시 만들지 않은 PR이 **CI에서 잡힌다.**
>
> **⚠ 제약 3가지 — 지금 실행하지 않는 이유:**
> 1. **`dashboard/`가 아직 없다.** 없는 디렉터리를 대상으로 하는 워크플로우를 쓸 수 없다
> 2. **AGENTS.md: "존재하지 않는 명령을 문서·게이트·PR 본문에 쓰지 않는다."** `npm run tokens:check`는 `AI_ROI`에 **아직 없는 명령**이다. 이 문서에서도 **권고**로만 쓰고 게이트 조건으로 쓰지 않는다
> 3. **`Plan`은 private 서브모듈이고 현재 CI가 체크아웃하지 않는다**(AGENTS.md). `tokens:check`는 `Plan/DESIGN.md`를 읽어야 하므로 **서브모듈 체크아웃이 필요하고, 그러려면 CI에 인증이 필요하다.** 이것은 내 권한 밖의 결정이다
>
> → **⑶이 실질적 차단 요인이다.** 선택지: ⒜ CI에 서브모듈 인증을 추가한다(사용자 결정) ⒝ 토큰 검사를 로컬 훅(`prebuild`)에만 의존한다 — **`Ecommerce_Service`와 동일 수준** ⒞ 생성 CSS를 커밋하고 CI가 `Plan` 없이 "생성물이 최신인가"만 간접 확인한다(정본 없이 대조 불가 → 불가).
>
> **내 추천: ⒝로 C1을 진행하고, ⒜를 사용자 결정 항목으로 올린다.** 근거: `predev`/`prebuild` 훅이 dev·build 전에 **무조건** 생성하므로 실무상 드리프트는 막힌다. CI 강제는 "누군가 생성물만 손으로 고친 경우"를 잡는 추가 장치이고, 그 대가가 private 서브모듈 CI 인증이다. **비용이 이익보다 크다고 본다** — 다만 이것은 내 판단이고 사용자 맥락이 다를 수 있다.

---

# 6. `Ecommerce_Service` 변경 0건 증명

```
$ cd /Users/otter/72offsuit/Ecommerce_Service && git status --porcelain
(빈 출력)
```

**실행한 명령 2개는 모두 비파괴적이다:**
- `npm run tokens:check` — `--check`는 읽기만 한다 (`verify.mjs`의 `changed source is detected without rewriting` 시나리오가 이 성질을 보증한다)
- `npm run tokens:test` — `mkdtemp`로 만든 임시 디렉터리에서만 쓰고 `finally`에서 삭제한다

`tokens:generate`는 **실행하지 않았다** (쓰기 명령이다).

---

# 7. 확정 사항과 미정 사항

## 7.1 확정

| # | 내용 |
|---|---|
| K-1 | **`Plan/DESIGN.md`가 유일한 토큰 정본.** `dashboard/`에서 값을 재정의하지 않는다 |
| K-2 | **새 hex 색값 0건.** 상태 토큰은 전부 `--ds-*` 별칭 (`state-tokens.css`) |
| K-3 | 생성 스크립트 **복제**(⑴). 공유 패키지 만들지 않는다 |
| K-4 | `design-rules.css`도 복제. **본문 유래 값은 검증 범위 밖임을 명시** |
| K-5 | Pretendard 3요소(패키지·`localFont`·변수명)를 모두 복제 |
| K-6 | Tailwind v4 채택 (생성물 전제) |
| K-7 | 라이트 고정. OS 테마·다크 모드 없음 (`Plan/DESIGN.md`) |

## 7.2 미정 — 결정 필요

| # | 항목 | 결정자 |
|---|---|---|
| Z-1 | **CI 토큰 검사 — `Plan` private 서브모듈 체크아웃 인증을 추가할 것인가** | **사용자** (§5.2) |
| Z-2 | 장기적으로 두 저장소가 **UI 코드**(컴포넌트)를 공유할 계획이 있는가 | **사용자** — 있으면 ⑵ 재검토 (§3.1) |
| Z-3 | `dashboard/` 하위 **디렉터리 구조**(`scripts/`·`src/styles/` 위치) | **James T2.10** |
| Z-4 | npm 의존성 목록의 최종 확정 | **James T2.9** (npm 측) · Andrew W5-C |
| Z-5 | `dashboard/AGENTS.md`·`CLAUDE.md` 소유자 | **리드** — `usp.md` D-6 |

## 7.3 검증하지 않은 것

| # | 항목 |
|---|---|
| V-1 | **이 전략으로 실제 `dashboard/`를 세워본 것 — 없다.** 복제가 `AI_ROI`에서 동작하는지는 W5-C에서 확인된다. `BLOCKED — 대시보드 미구현` |
| V-2 | `--input ../Plan/DESIGN.md` 상대 경로가 의도대로 해석되는지 **실행 확인 안 함.** `resolve(root, ...)`의 `root`가 스크립트 위치의 부모이므로 `dashboard/scripts/`에 두면 `dashboard/`가 root가 되어 `../Plan`이 저장소 루트를 가리킬 것으로 **읽었으나, 실행해 확인하지 않았다** |
| V-3 | Pretendard가 `dashboard/`에서 실제 로딩되는지 — 육안 확인 필요 (§4.2) |
| V-4 | Tailwind v4 + 생성 CSS가 `dashboard/`에서 빌드되는지 |

> V-2는 **Andrew가 가장 먼저 부딪힐 지점**이므로 `design-handoff.md` 첫 확인 항목으로 올린다. 읽어서 추론한 것을 실행 확인으로 적지 않는다.
