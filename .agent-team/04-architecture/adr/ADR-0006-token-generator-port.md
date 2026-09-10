# ADR-0006 · 디자인 토큰 생성기를 이식한다 (값은 `Plan/DESIGN.md` 한 벌)

**상태** 확정 · 2026-09-11 · James
**맥락** T2.10 · PRD §69

## 문제
PRD §69 가 Next.js 를 고른 **유일한 결정적 근거**가 *"`Ecommerce_Service` 의 토큰 파이프라인을 재사용하지 못하면 토큰을 두 벌 관리하게 된다"* 였다.
그런데 AGENTS.md 는 *"런타임 의존은 없다. 이 저장소는 단독으로 실행된다"* 를 못박는다. **직접 참조는 불가능하다.**

## 조사 (read-only · 변경 0건)
| 사실 | 근거 |
|---|---|
| 생성기는 스크립트 4개 · 총 **199줄** | `design-tokens.mjs`(33) · `render.mjs`(34) · `resolve.mjs`(71) · `verify.mjs`(61) |
| 입력은 **`Plan/DESIGN.md` 하나**, 출력은 gitignore 된 생성 CSS | `design-tokens.mjs` |
| 외부 의존은 **`js-yaml` 하나** | `resolve.mjs` |
| **`DESIGN.md` 가 이미 대시보드 토큰을 갖고 있다** | `dashboard-max: 1440px` · `dashboard-sidebar: 224px` (`DESIGN.md:107-108`) |
| 생성기가 **이미 `--container-dashboard-max` 를 내보낸다** | `render.mjs` |
| **두 저장소의 `Plan` 서브모듈이 같은 커밋** | 양쪽 `c46aee5eed00193b9331403645b8dbccaef52278` (실행 확인) |

## 결정
**4개 파일을 `dashboard/scripts/` 로 이식하고 입력을 `../Plan/DESIGN.md` 로 둔다.** `predev`·`prebuild` 에 연결하고 `tokens:check` 로 드리프트를 실패로 만든다.

## 근거 — 구분해야 할 두 가지
| | 정본이 몇 벌인가 |
|---|---|
| **토큰 값** | **한 벌.** `Plan/DESIGN.md` |
| 생성기 코드 | 두 벌 (199줄 × 2) — **코드 중복이지 값 중복이 아니다** |

PRD §69 가 금지한 것은 *"**동일한 값**을 UI 마다 새로 정의"* 하는 것이다. **값의 정본은 여전히 하나다.**

## 기각한 대안
| 대안 | 사유 |
|---|---|
| `Ecommerce_Service` 스크립트를 상대경로로 실행 | **런타임 의존.** AGENTS.md 위반. 그 저장소가 없으면 빌드가 깨진다 |
| 공유 npm 패키지 배포 | 199줄을 위해 레지스트리·버저닝·릴리스를 새로 만든다 |
| 서브모듈/subtree 로 공유 | 서브모듈이 하나 더 늘고 `Plan` 규약과 섞여 운영이 복잡해진다 |
| **토큰 값을 복사** | ★ PRD §69 가 금지한 바로 그것 |

## 남는 위험
생성기 두 벌이 갈라질 수 있다. 완화: 이식 파일 머리에 **출처 커밋 SHA 를 주석으로** 기록하고, `dashboard/AGENTS.md` DG-7 에 *"로직을 바꾸려면 양쪽을 함께 본다"* 를 적는다. CI 로 강제하지 않는다(Node CI 미도입).
