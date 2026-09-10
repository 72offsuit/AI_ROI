# 타 개발자 작업 충돌 점검 — T1.7 (가정 A10)

**작성** 2026-09-10 · John (W1 Reverse)
**대상** `72offsuit/AI_ROI` @ `1140912` · `72offsuit/Ecommerce_Service` @ `6b186d0`

---

## 0. 판정 — ⚠️ **A10은 "조건부 성립"이다**

| 축 | 결과 |
|---|---|
| **진행 중인 PR** | **0건** (양 저장소 모두 `gh pr list --state open` 빈 출력) |
| **main보다 앞선 브랜치** | **0건** (실질) — 아래 §2.2 |
| **작업 트리 미커밋 변경** | AI_ROI: `?? .agent-team/`(우리 것) · Ecommerce: **없음** |
| **AI_ROI 영역 충돌** | **없음.** 최근 커밋 전부 단일 작성자 |
| **`Ecommerce_Service` 영역 충돌** | **⚠️ 실재한다** — 다른 개발자가 코드의 대부분을 소유 |

> **즉시 눈에 띄게 보고할 것: `Ecommerce_Service`의 스토어프론트 코드는 우리가 아닌 다른 사람이 썼다.**
> C1은 커머스를 편집하지 않으므로 **이번 사이클에 코드 충돌은 발생하지 않는다.**
> 그러나 우리가 만들 **이슈 초안(특히 제거 대상)** 은 그 사람의 작업물을 지우자는 제안이다. **발행 전 사용자·해당 개발자 합의가 필요하다.**

---

## 1. 참여자 실측

### 1.1 `AI_ROI` — 27개 커밋, 실질 단일 작성자

| 작성자 | 커밋 수 |
|---|---|
| `Inseong Kim <74861101+Danto7632@users.noreply.github.com>` | 13 |
| `Danto <rlarladlstjd@gmail.com>` | 2 |

두 항목은 **같은 사람**이다(사용자 계정: `rlarladlstjd@gmail.com` / GitHub `Danto7632`).
최근 커밋 전부 이 계정 — `1140912`·`d1ca26f`·`105e83c`·`41ccf73`·`8908ffc` (2026-09-10 21:29~23:03).

**→ AI_ROI 안에서는 충돌 위험이 없다.**

### 1.2 `Ecommerce_Service` — 27개 커밋, **2인**

| 작성자 | 커밋 수 | 성격 |
|---|---|---|
| **`SeongHwan <epaktldk0203@gmail.com>`** | **18** | 커머스 구현 전부 — 부트스트랩·디자인 토큰·테스트 환경·SQLite 기반·구매 흐름·쿠폰·버그픽스 |
| `Inseong Kim <…Danto7632…>` | 7 | Plan 서브모듈 포인터 갱신 · AGENTS.md 진입점 |
| `Danto <rlarladlstjd@gmail.com>` | 2 | 초기 |

**SeongHwan의 최근 작업**: `39d1668` "fix: 구매 동작 중 화면 번쩍임 방지" (PR #21, **2026-09-10 19:14**) — **오늘이다.**

### 1.3 이슈 작성자

`Ecommerce_Service` `#24`~`#30`(2026-09-10 13:47~13:49) — **전부 `Danto7632`가 작성**했다. 즉 **우리 쪽(사용자)이 낸 이슈이고, 담당자는 지정되어 있지 않다.**
`AI_ROI` `#42`~`#49`도 동일 작성자.

> **핵심 구도: 이슈를 쓰는 쪽(사용자)과 커머스 코드를 쓰는 쪽(SeongHwan)이 다르다.**
> `#24`~`#30`은 아직 아무도 착수하지 않았고 담당도 없다. 우리가 초안을 얹으면 **SeongHwan에게 전달될 작업 지시가 늘어나는 것**이다.

---

## 2. 브랜치·PR 상태

### 2.1 열린 PR

| 저장소 | 결과 |
|---|---|
| `AI_ROI` | **0건** |
| `Ecommerce_Service` | **0건** |

전 PR이 MERGED다 (AI_ROI 12건, Ecommerce 13건).

### 2.2 원격 브랜치 — 실질 잔재뿐

**AI_ROI**: `origin/main` 외 **없음**. 병합 후 삭제 관리가 되어 있다.

**Ecommerce_Service**: 6개 잔재 브랜치. 두 개가 커밋 수로는 앞서 보이나 **내용 차이를 확인한 결과 미착수 작업이 아니다.**

| 브랜치 | main 대비 커밋 | 실제 내용 차이 (`git diff main branch`) | 판정 |
|---|---|---|---|
| `feat/design-tokens` | 4 | 90 files, +3570 / −12552 · 최신 커밋 **2026-09-05** · `src/app/page.tsx`(구 구조) 포함 | **낡은 squash 잔재.** 이후 라우트가 `src/app/(store)/`로 재구성됨 |
| `fix/storefront-pending-flicker` | 2 | **1 file, +1/−1 — `Plan` 서브모듈 포인터뿐** | 사실상 main과 동일 (PR #21 병합 완료) |
| `chore/9-test-tooling`·`chore/project-bootstrap`·`feat/commerce-data-foundation`·`feat/one-page-purchase` | 0 | — | 병합 완료 |

**→ 진행 중인 미완 작업 브랜치는 없다.**

> 부수 관찰: `fix/storefront-pending-flicker`의 `Plan` 포인터가 `46ba14e`로, main(`c46aee5`)과 다르다. 어느 쪽이 최신인지는 `Plan` 저장소 소관이라 여기서 판단하지 않는다. **우리는 서브모듈 포인터를 건드리지 않는다**(AGENTS.md).

---

## 3. 소유 경계 충돌 분석

### 3.1 C1 실행 계획(`task-graph.md` §4)과의 대조

| C1 담당 | 배타 소유 | 타인 작업과 겹치나 |
|---|---|---|
| Phillip | `src/measurement/**` · `config/` · `requirements*` · `tests/test_{schema,sink,kpi,quality}*` · `docs/measurement-contract.md` · `docs/gate1-freeze.md` | **아니오.** AI_ROI 단독 작성자 영역 |
| Andrew | 대시보드 경로 (W2 T2.10 확정) | **아니오.** 신규 경로 |
| — | `Ecommerce_Service/**` | **읽기 전용.** 편집 0건 원칙 유지 시 충돌 없음 |

**코드 충돌 위험: 0.** C1은 커머스를 편집하지 않고, AI_ROI 측 편집 영역에 다른 작성자가 없다.

### 3.2 실재하는 충돌 — 이슈·의사결정 층

| # | 충돌 | 상세 | 조치 |
|---|---|---|---|
| **C-1** | **제거 대상 제안 ↔ SeongHwan의 작업물** | `ecommerce-gap.md` §4의 R-1~R-9는 전부 SeongHwan이 구현한 코드다(`UserMenu.tsx`·`HomeHero.tsx`·`ShopHome.tsx`·`heroBanners.ts`). 특히 R-1(테스트 사용자 전환 UI)은 헤더 핵심 컴포넌트 | **초안만 두고 발행 보류.** 사용자 승인 + 담당 개발자 합의 후 |
| **C-2** | **`#29`의 명문 ↔ 사용자 지시** | `#29` 범위 절: *"테스트 사용자 전환 방식은 유지해도 됩니다"* / 사용자: *"없애야 할 것(테스트 사용자 A·B UI 같은)"*. **같은 사람이 쓴 이슈와 지시가 서로 반대다** | **사용자 판정 필요.** `#29` 수정 또는 제거 이슈 분리 |
| **C-3** | **이슈 7건이 담당자 없이 대기** | `#24`~`#30` 전부 assignee 없음, 착수 흔적 없음 | 초안을 더 얹기 전에 **기존 7건의 담당·우선순위를 먼저 정하는 편이 안전** |
| **C-4** | **`AI_ROI` `#43`·`#44` close 판단** | 사용자만 결정 가능 (`issue-code-audit.md` §4) | 사용자 판정 |
| **C-5** | **`Plan` 서브모듈 포인터 불일치** | 두 저장소 main은 `c46aee5`로 정렬됨. 잔재 브랜치 하나만 다름 | 조치 불필요. 건드리지 않는다 |

### 3.3 타이밍 관찰

2026-09-10 하루에 양 저장소에서 작업이 동시에 있었다.

```
13:47~13:49  Ecommerce #24~#30 이슈 생성        (Danto7632)
19:14        Ecommerce PR #21 병합              (SeongHwan)   ← 이슈 이후에도 커머스 작업이 계속됨
21:29~23:03  AI_ROI #39~#52 병합 (측정 계층)     (Danto7632)
23:04        Ecommerce Plan 포인터 갱신          (Danto7632)
```

**SeongHwan이 `#24`~`#30` 발행 이후에도 커머스를 계속 만지고 있었다**(PR #21). 활동이 살아 있는 저장소다.
지금 이 순간 열린 PR·미커밋 변경은 없지만, **다음 커밋이 언제 들어올지 모른다는 전제로 움직여야 한다.**

---

## 4. 권고

1. **커머스 이슈 초안은 발행하지 않는다.** 사용자 승인 전까지 `.agent-team/01-reverse/issue-drafts/`에만 둔다. (AGENTS.md L1 — 이미 준수)
2. **발행한다면 `#24` 하위로 묶고, 제거 축은 별도 1건으로 분리한다.** 기존 `#25`~`#30`의 수용 기준을 사후 수정하면 착수자가 혼란스럽다.
3. **`#29`와의 모순(C-2)을 먼저 해소한다.** 제거 이슈를 내기 전에 `#29`의 "테스트 사용자 유지 가능" 문장에 대한 사용자 판정이 필요하다.
4. **커머스 코드는 계속 읽기 전용으로 둔다.** 편집이 필요해지면 `Ecommerce_Service` 자체 킥오프로 넘긴다(charter §5).
5. **W5 착수 직전에 이 점검을 1회 재실행한다.** `gh pr list --state open` · `git fetch && git log origin/main -5` — 오늘 활동이 있었던 저장소이므로 스냅샷이 금방 낡는다.

---

## 5. A10 판정

> **A10("타 개발자와 작업이 충돌하지 않는다") — C1 범위에서는 성립. 단 조건부.**
>
> - **코드 충돌: 없다.** C1은 `src/measurement/**`와 신규 대시보드 경로만 만지고, 그 영역에 타 작성자가 없다. 열린 PR·미완 브랜치도 0건.
> - **의사결정 충돌: 있다.** 커머스 코드의 3분의 2를 다른 개발자가 소유하고 있고, 우리 제거 제안은 그 작업물을 대상으로 한다.
> - **전제 조건: `Ecommerce_Service` 편집 0건 원칙을 끝까지 지킬 것.** 이것이 깨지는 순간 A10은 무효가 되고 별도 킥오프가 필요하다(charter §5).

---

## 6. 실행한 확인 명령

```
gh issue list --state all --limit 60          (양 저장소)
gh pr list --state all --limit 30             (양 저장소)
gh pr list --state open                       (양 저장소 — 빈 출력)
git branch -a                                 (양 저장소)
git log --format='%an <%ae>' | sort | uniq -c (양 저장소)
git log -20 --format='%h %ad %an %s'          (양 저장소)
git status --porcelain                        (양 저장소)
git rev-list --count origin/main..<branch>    (Ecommerce 6개 브랜치)
git diff --shortstat origin/main origin/<b>   (Ecommerce 2개 브랜치)
```

`BLOCKED`: 없음.
