# DR-207-plan-free-tokens — 대시보드 토큰 CSS 를 커밋하고, Plan 이 있을 때만 정본과 대조한다

| | |
|---|---|
| 태스크 | 리드 인프라 · #207 (Sprint 2, 부모 범위 #191) |
| 작성 | 인성(Danto7632, 에이전트 구현) · 2026-10-24 |
| 상태 | 확정 |

## 무엇을 정하는가

대시보드의 디자인 토큰 CSS(`dashboard/src/styles/tokens.generated.css`)는 private 서브모듈 `Plan/DESIGN.md` 에서 생성되고, 생성물은 gitignore 였다. **Plan 이 없는 클론(CI · 컨테이너 · 권한 없는 기기 · 새 worktree)에서 대시보드가 빌드되려면 토큰을 어디서 얻는가**를 정한다.

## 정하지 않으면 무엇이 막히나

- #207 완료 조건 "서브모듈 없는 클론에서 `docker build` 성공" 이 막힌다. 대시보드 빌드 단계에서 죽는다.
- SYS-001 "Fresh clone 에서 build 성공 · Dashboard 실행"(compose, #231)과 다른 기기 검증(#232)이 막힌다.

## 선택지

| 안 | 내용 | 장점 | 단점 |
|---|---|---|---|
| A | 생성물을 **커밋**한다. predev · prebuild 는 `Plan/DESIGN.md` 가 있으면 `tokens:check` 로 대조하고, 없으면 "미실행" 을 알리고 커밋본을 쓴다 | 이식한 생성기를 고치지 않는다. Plan 이 있는 모든 체크아웃에서 드리프트가 빌드 실패로 드러난다 | 정본 대조가 CI 에서는 돌지 않는다(`tokens:test` 와 같은 사정) |
| B | `DESIGN.md`(또는 그 frontmatter) 사본을 저장소에 두고 거기서 생성한다 | 생성 경로가 그대로다 | 정본 문서가 두 벌이 된다. 사본은 손으로 고칠 수 있는 원천이라, PRD §69 가 막으려던 "토큰 이중 정의" 에 더 가깝다 |
| C | CI · Docker 빌드에서 Plan 을 비밀 토큰(PAT · deploy key)으로 체크아웃한다 | 커밋본이 필요 없다 | 비밀값을 CI 와 빌드 인자로 돌려야 한다. "서브모듈 없는 클론" 이라는 완료 조건과 정면으로 어긋난다. 다른 기기 검증자도 Plan 권한이 필요해진다 |
| D | Plan 이 없으면 내장 기본 토큰(최소 팔레트)으로 빌드한다 | 빌드는 된다 | 정본과 다른 색 · 간격으로 **조용히** 렌더된다. 결손을 그럴듯한 기본값으로 채우는 것과 같은 실패다(USP-1) |
| E | `Ecommerce_Service` 의 생성물을 가져온다 | 같은 정본에서 나왔다 | 런타임·빌드 의존이 생긴다. 2저장소 분리(AGENTS.md "런타임 의존은 없다")를 깬다 |

## 조사한 것

| 출처 | 무엇을 말하나 | 우리 맥락에 얼마나 맞나 |
|---|---|---|
| 재현 — `git clone`(서브모듈 미초기화) → `dashboard/` 에서 `npm ci && npm run build` (2026-10-23) | `prebuild` 의 `tokens:generate` 가 `ENOENT … /Plan/DESIGN.md` 로 죽는다, 종료 코드 1. `next build` 만 돌려도 `globals.css` 가 `@import "../styles/tokens.generated.css"` 를 못 찾아 실패한다 | 위험이 아니라 **실제 결함**이었다. Plan 없는 클론에서 대시보드는 빌드되지 않았다 |
| 생성물 비교 | Plan 포인터 `c46aee5` 의 `DESIGN.md`(sha256 `f4dc7ba9…`)로 만든 CSS 가 sha256 `a26ece41…` 이다. 본 체크아웃이 로컬에 만들어 둔 생성물과 바이트 단위로 같다. 별도 클론 `~/72offsuit/Plan` 의 `DESIGN.md` 도 같은 해시다 | 커밋한 것은 지금 쓰고 있는 것과 같은 파일이다 |
| `dashboard/scripts/tokens/verify.mjs` 시나리오 | "repeated generation succeeds" — 같은 입력이면 같은 출력이고, 다시 써도 mtime 이 그대로다 | 생성기가 결정론적이다. 커밋본의 diff 는 **DESIGN.md 가 바뀔 때만** 생긴다 — `results/` 를 커밋하지 않는 이유(매 실행 run_id · 시각 변화, `.gitignore`)가 여기는 해당하지 않는다 |
| PRD §69 (`Plan/AI_Retention_ROI_PRD_v2.md`) | Next.js 를 택한 결정적 근거가 "토큰 이중 정의" 를 피하는 것 — 값은 DESIGN.md 한 곳에서 정의하고 생성 파이프라인으로 연결한다 | A 의 커밋본은 손으로 정의한 값이 아니라 생성물이다(DG-7 직접 수정 금지). 그래도 **물리적 사본이 하나 생기는 것은 사실**이고, 그 사본이 정본과 같은지는 Plan 이 있는 곳에서만 확인된다 |
| `AGENTS.md` · `dashboard.yml` 머리 주석 | `tokens:test` 는 Plan 을 읽어 CI 에 없다 — 사람이 돌리는 검사다 | A 는 이 사정을 바꾸지 않는다. CI 에 Plan 을 넣지 않는다. 같은 이유로 커밋본 ↔ 정본 대조도 CI 에 없다고 적는다 |

## 결정

**안 A.**

- `dashboard/src/styles/tokens.generated.css` 를 커밋한다. 루트 `.gitignore` 에서 그 줄을 지우고, 그 자리에 예외 사유를 적는다.
- `predev` · `prebuild` 는 새 `dashboard/scripts/tokens-prebuild.mjs` 를 부른다.
  - `../Plan/DESIGN.md` 가 있으면 이식된 `design-tokens.mjs --check` 를 그대로 실행한다. 다르면 빌드가 실패하고 `npm run tokens:generate` 후 커밋하라고 알린다.
  - 없으면 `tokens:check 미실행 — … 정본 대조 없이 쓴다` 를 출력하고 통과한다.
  - 생성물이 없으면 실패한다.
- 이식 파일 4종(`design-tokens.mjs` · `tokens/*.mjs`)은 고치지 않는다. 고치지 않아야 Ecommerce_Service 와 갈라지지 않는다(DG-7).
- `tokens:generate` · `tokens:check` · `tokens:test` 명령은 그대로 둔다.

**근거:** 재현으로 결함이 확인됐다(조사 1행). 남는 안 중 비밀값도(C), 조용한 기본값도(D), 저장소 간 의존도(E) 만들지 않는 것은 A 와 B 뿐이다. 둘 다 사본이 생기지만, A 의 사본은 기계가 만들고 기계가 대조하는 생성물이다. B 의 사본은 사람이 고칠 수 있는 원천이다. 생성기가 결정론적이어서(조사 3행) 생성물을 커밋해도 의미 없는 diff 가 생기지 않는다.

## 기각한 안과 기각 사유

| 안 | 왜 택하지 않았나 |
|---|---|
| B DESIGN.md 사본 | 원천 문서가 두 벌이 된다. 사본을 고치는 사람이 생기면 정본과 갈라지고, 갈라진 것을 아는 장치는 A 와 똑같이 Plan 이 있는 곳의 대조뿐이다. 비용은 같고 위험은 더 크다 |
| C Plan 비밀 체크아웃 | 비밀값을 CI · 빌드 인자로 돌려야 한다. 완료 조건("서브모듈 없는 클론")을 우회하는 것이지 충족하는 것이 아니다 |
| D 내장 기본 토큰 | 틀린 값으로 조용히 그린다. 이 저장소에서 가장 나쁜 실패 모양이다 |
| E Ecommerce_Service 에서 가져오기 | 저장소 간 의존이 생긴다 |
| Plan 이 있을 때 predev 가 계속 **재생성**(이전 동작) | 커밋된 파일을 빌드가 조용히 덮어써 diff 가 생기는데 아무도 이유를 모른다. 실패시키고 "생성해서 커밋하라" 고 말하는 쪽이 드리프트를 드러낸다 |

## 이 결정이 틀렸다면 어떻게 드러나나

- Plan 이 있는 체크아웃에서 `npm run dev` · `npm run build` 가 `생성 토큰이 없거나 정본과 다릅니다` 로 실패하면 커밋본이 정본에서 벗어난 것이다. 의도된 신호다.
- Plan 포인터를 올렸는데 아무도 Plan 있는 곳에서 빌드하지 않으면, **드리프트는 드러나지 않는다.** 이것이 이 결정의 사각이다. Plan 포인터 갱신은 사용자 지시로만 하므로(AGENTS.md), 그 작업에 `npm run tokens:generate` 를 함께 넣는 것이 대응이다.
- 이식 원본(Ecommerce_Service)의 생성기 로직이 바뀌어 출력이 달라지면, 같은 DESIGN.md 에서 다른 CSS 가 나온다. DG-7 절차(양쪽을 함께 본다)가 잡아야 한다.

## 민감도

토큰 값 자체가 바뀌는 경우(DESIGN.md 개정)만 이 결정이 비용을 낸다. 비용은 생성 → 커밋 1회다. 값을 ±20% 바꿔도 절차는 같다. 대비 4.5:1 재검산(`dashboard/AGENTS.md` §8, `planned` 4.89:1)은 이 결정과 무관하게 필요하다.

## 남은 불확실성

- 커밋본 ↔ 정본 대조는 **CI 에서 돌지 않는다.** Plan 이 private 인 한 해소되지 않는다. `tokens:test` 와 같은 처지이며, Plan 접근이 있는 사람의 `npm run build` 가 그 대조를 대신한다.
- `dashboard/AGENTS.md` 의 DG-17 검사(`grep … '#[0-9A-Fa-f]…' src` → 0건)는 원래도 로컬 생성물에 걸렸다. 이제는 클론에서 바로 걸린다. 그래서 그 명령에 `--exclude=tokens.generated.css` 를 더했다. 생성물은 DG-17 이 막는 "새 색값 도입" 이 아니라 정본 값의 사본이다.
