# DR-172-merge-guard — 병합 전 체크·승인 강제 · worktree 의 `Plan` 서브모듈 절차

| | |
|---|---|
| 태스크 | 리드 인프라 · #172 (Sprint 2) |
| 작성 | 인성(Danto7632, 에이전트 구현) · 2026-10-23 |
| 상태 | 확정 |

## 무엇을 정하는가

두 가지다.

1. 브랜치 보호를 켤 수 없는 저장소에서 **"전 체크 통과 + 승인 1건" 을 무엇으로 강제하는가**, 그리고 그 강제가 무엇을 통과로 치는가(SKIPPED · 진행 중 · 오래된 승인).
2. git worktree 에서 `Plan` 서브모듈 gitdir 이 깨져 `tests/test_team_boundaries.py` 가 BLOCKED 되는 문제를 **어느 층에서 고치는가** — 테스트 · 저장소 설정 · 작업 절차.

## 정하지 않으면 무엇이 막히나

- 병합: `#141` 이 `Tests (with deps)` FAILURE 상태로 병합됐다. 같은 사고를 막는 장치가 없으면 Sprint 3 의 GATE 1·2 봉인 PR 도 같은 길로 나갈 수 있다 — 봉인 해시 대조가 실패한 채 병합되면 FREEZE-003 재실행 범위를 판단할 근거가 사라진다.
- worktree: 팀 경계 검사가 skip 으로 빠지면 **한 브랜치가 두 팀 경로를 건드려도 초록**이다. 에이전트마다 `GIT_CONFIG_* … submodule.Plan.ignore=all` 을 붙여 돌렸고, 그것을 잊은 실행은 아무것도 대조하지 않았다.

## 선택지

**병합 강제**

| 안 | 내용 | 장점 | 단점 |
|---|---|---|---|
| A | 브랜치 보호 · rulesets | 서버가 강제 — 우회 불가 | private + Free 에서 쓸 수 없다 |
| B | `gh` 별칭 / 셸 함수 | 한 줄 | 개인 설정이라 저장소에 남지 않고, 검사할 수 없다 |
| C | 저장소의 스크립트(`scripts/safe_merge.py`, 표준 라이브러리) + 테스트 | 저장소에 남고, 판정 논리를 단위 테스트로 고정할 수 있다 | 스크립트를 거치지 않고 웹 버튼으로 병합하면 못 막는다 |
| D | 병합 후 감시 워크플로우(main push 에서 직전 PR 체크를 확인해 이슈 생성) | 사후라도 기계가 잡는다 | 막지 못하고 알릴 뿐이다. `.github/` 봉인 파일이 하나 늘어난다 |

**승인 판정**

| 안 | 내용 | 장점 | 단점 |
|---|---|---|---|
| R1 | `reviewDecision == APPROVED` | 간단 | 보호 규칙이 없으면 **늘 빈 문자열**이다 — 영원히 막힌다 |
| R2 | `reviews` 에서 리뷰어별 마지막 판정(APPROVED · CHANGES_REQUESTED · DISMISSED)을 센다 | GitHub 의 판정 규칙과 같고 보호 없이도 계산된다 | 직접 구현해야 한다 |
| R3 | R2 + 승인 커밋 ≠ head 면 막는다 | 리뷰 뒤 커밋까지 강제 | 리뷰 반영 커밋마다 재승인이 필요하다 |

**worktree**

| 안 | 내용 | 장점 | 단점 |
|---|---|---|---|
| W1 | 테스트의 `git status` 에 `--ignore-submodules=dirty` | 어떤 worktree 상태에서도 경계 검사가 돈다 | `git status` 를 직접 치는 사람의 문제는 남는다 |
| W2 | `.gitmodules` 에 `ignore = all` | 모든 체크아웃에서 증상이 사라진다 | `Plan` 포인터 변경까지 `git status` 에서 숨긴다 |
| W3 | 문서화된 worktree 절차(복사 금지 · 필요하면 worktree 안에서 `git submodule update --init`) | 원인 자체를 피한다 | 절차를 안 읽으면 그대로 깨진다 |
| W4 | `GIT_CONFIG_*` 우회를 공식화 | 지금 하던 그대로 | 잊으면 BLOCKED 로 조용히 빠지고, `ignore=all` 이 포인터까지 숨긴다 |

## 조사한 것

| 출처 | 무엇을 말하나 | 우리 맥락에 얼마나 맞나 |
|---|---|---|
| `gh pr view 141 --json statusCheckRollup,reviews` (2026-10-23 실행) | `Tests (with deps)` → `FAILURE`, 나머지 3종 `SUCCESS`, `reviews: []`, `reviewDecision: ""` | 사고 그 자체. `test_the_141_incident_is_blocked` 가 이 모양을 그대로 쓴다 |
| `gh pr list --state all --limit 60 --json reviewDecision,reviews` | 60건 전부 `reviewDecision` 이 빈 문자열, `APPROVED` 리뷰 **0건**(`COMMENTED` 4건뿐) | R1 이 불가능함을 확인. 동시에 **승인 1건 규칙이 지금까지 한 번도 지켜지지 않았다** — 이 스크립트를 쓰기 시작하면 모든 PR 에 광진(또는 같은 팀 동료)의 승인이 실제로 필요해진다 |
| `scripts/safe_merge.py 141 --dry-run` · `236 --dry-run` | 141: 막힘 3건(MERGED · FAILURE · 승인 0) / 236: 체크 4종 SUCCESS, 막힘 1건(승인 0) | 실 PR 데이터로 판정이 기대대로 나온다. 병합은 실행하지 않았다 |
| 재현 — 스크래치 클론 + worktree 4가지 (git 2.43, 2026-10-23) | ① 그냥 만든 worktree: `Plan/` 빈 디렉터리, `git status` rc=0, 경계 검사 OK ② 본 체크아웃 `Plan/` 을 `cp -R`: `Plan/.git` = `gitdir: ../.git/modules/Plan` → `fatal: … Plan/../.git/modules/Plan` rc=128, 경계 검사 `skipped=1` ③ worktree 안에서 `git submodule update --init`: gitdir 이 `.git/worktrees/wt-init/modules/Plan` 로 따로 생기고 rc=0 ④ 심볼릭 링크: 동작은 하나 `T Plan`(typechange)이 변경으로 잡힌다 | 원인은 **복사된 상대 경로 gitfile** 이다. worktree 자체나 git 버그가 아니다 |
| 같은 재현에서 `--ignore-submodules` 단계별 | `none`·`untracked` rc=128, `dirty`·`all` rc=0 | `dirty` 가 깨진 gitdir 을 견디는 가장 좁은 단계다. `all` 은 포인터 이동까지 숨긴다 |
| 수정 후 같은 깨진 worktree | 경계 검사 skip 0, 양 팀 경로에 파일을 두면 **FAIL** 로 잡는다 / 수정을 되돌리면 새 회귀 테스트가 FAIL | 고친 것이 실제로 대조를 되살렸고, 회귀 테스트가 그 수정에 묶여 있다 |
| PR #238 리뷰(2026-10-28 `kwung0206`) 반례 → 수정 후 재현 (2026-10-29) | R1: `push:` 에만 `paths` 가 있어도 `jobs:` 앞 전체에서 필터를 찾아 필수 4→3 이 됐다. 그 PR 은 미보고 체크가 있어도 종료 0 · 병합 호출 1회였다. R2: 필수 잡이 미보고여도 다른 워크플로우의 동명 체크(또는 같은 이름의 StatusContext) SUCCESS 로 충족됐다. R3: `required=[]` 이면 필수 대조 없이 종료 0 이었다. 수정 후에는 실제 워크플로우 사본의 `push:` 에 필터를 넣어도 필수 목록이 그대로다. 셋 다 막히고, 수정을 하나씩 되돌리면 새 테스트가 실패한다(변이 4종) | 셋 다 기본 설정에서 난 사고가 아니라 조건부 결함(P3)이다. 다만 이 스크립트가 유일한 병합 강제라, 막는 쪽으로 틀리게 고쳤다 |
| `safe_merge.py 242 · 238 · 141 --dry-run` (수정 후, 2026-10-29, 읽기만) | 242: 필수 4종 정확 쌍 대조 통과, 승인 1 → 조건 충족 / 238: 변경 요청 미해소로 막힘 / 141: MERGED · FAILURE · 승인 0 으로 막힘 | 실 PR 의 `statusCheckRollup` 에 `workflowName` 이 실려 있어 정확 쌍 대조가 실제 데이터에서 동작한다 |
| `gh api repos/72offsuit/AI_ROI/branches/main/protection` · `…/rulesets` (2026-10-23, 읽기만) | 둘 다 HTTP 403 `Upgrade to GitHub Pro or make this repository public to enable this feature.` | #172 의 전제(private + Free 라 보호 불가)를 API 응답으로 확인. public 전환은 하지 않기로 했고(2026-09-05) 플랜 변경은 이 결정의 범위가 아니다 |

## 결정

**병합 — 안 C + R2.** `scripts/safe_merge.py` 가 아래를 전부 만족할 때만 `gh pr merge --squash --match-head-commit` 을 실행한다.

- PR 이 OPEN 이고 초안이 아니다
- `.github/workflows/*.yml` 중 `pull_request` 로 도는 워크플로우의 잡이 **전부 보고**됐다(아직 안 뜬 체크는 통과가 아니다)
- 보고된 체크가 **전부 `SUCCESS`** — `SKIPPED` · `NEUTRAL` · `CANCELLED` · 진행 중은 통과가 아니다
- 작성자가 아닌 리뷰어의 마지막 판정 중 `APPROVED` 1건 이상, `CHANGES_REQUESTED` 0건
- `CONFLICTING` 이 아니다

우회 옵션은 두지 않는다(`test_options_are_exactly_repo_and_dry_run`). 승인 커밋 ≠ head 는 막지 않고 `[주의]` 로 알린다.

리뷰 R1~R3(PR #238) 반영:

- **필수 목록에서 빼는 사유는 `pull_request` 이벤트 자신의 `paths` · `paths-ignore` 필터뿐이다.** `push.paths` 같은 다른 이벤트의 필터는 보지 않는다. 기존 제외 정책(PR 경로 필터가 있으면 PR 마다 돈다는 보장이 없으니 필수에서 뺀다)은 유지한다. 뺀 워크플로우는 `excluded_workflows()` 가 사유와 함께 내고 `[주의]` 로 출력한다. `tests/test_safe_merge.py` 는 지금 저장소의 제외 목록이 비어 있음을 고정한다. 그래서 제외가 생기면 테스트가 실패하고, 사람이 이 DR 과 함께 본다. 개수 검사도 같은 정책을 따른다(필수 ∪ 제외 = PR 워크플로우 전부).
- **필수 Actions 잡은 정확한 `(workflow, job)` 쌍으로만 충족된다.** 잡 이름만 같은 다른 워크플로우의 체크나 StatusContext 는 대신하지 못한다. 외부 상태는 ③(보고된 것 전부 `SUCCESS`)으로 따로 본다.
- **필수 목록이 비었거나 만들지 못하면 막는다.** 워크플로우 파일 없음 · PR 워크플로우에서 잡을 못 읽음 · 인라인 매핑 `on: {…}` 같이 읽지 않는 형태는 `WorkflowError` 로 종료 2, 빈 목록은 판정에서 막힘(종료 1)이다. 둘 다 `gh pr merge` 를 부르지 않는다.
- 필수 목록은 **스크립트가 놓인 체크아웃**의 정의에서 읽는다. 최신 `main` 에서 실행해 PR 이 자기 필수 목록을 줄이지 못하게 한다. 워크플로우 · 잡 이름을 바꾸는 PR 은 막히며, 그 처리(리뷰 승인 뒤 PR head 체크아웃에서 판정)는 `docs/GIT_WORKFLOW.md` §5.1 에 적는다.

**worktree — W1 + W3.** 경계 검사는 `git status --porcelain --ignore-submodules=dirty` 로 변경 목록을 얻고, `docs/GIT_WORKFLOW.md` §11 에 "복사하지 않는다 · 필요하면 worktree 안에서 `git submodule update --init`" 절차를 적는다.

**근거:** 병합 쪽은 서버 강제(A)가 불가능하므로 저장소에 남고 테스트할 수 있는 C 가 남는 안 중 가장 강하다. 판정 논리를 테스트로 묶어야 "스크립트가 있다" 가 "막는다" 와 같은 뜻이 된다. 승인은 R1 이 원리적으로 불가능해(조사 2행) R2 다. worktree 쪽은 원인이 복사된 gitfile 이라는 재현 결과에 따라, 검사는 어떤 상태에서도 돌게(W1) 하고 사람은 원인을 피하게(W3) 한다. `Plan/**` 은 어느 팀 소유도 아니므로 서브모듈 안을 보지 않아도 경계 판정은 바뀌지 않는다.

## 기각한 안과 기각 사유

| 안 | 왜 택하지 않았나 |
|---|---|
| A 브랜치 보호 | 플랜 제한으로 불가. 플랜이 바뀌면 이 결정을 번복하고 A 로 옮긴다 — 그때 스크립트는 남겨도 해가 없다 |
| B 개인 별칭 | 저장소에 남지 않아 다음 사람·다음 에이전트가 모른다. 판정 논리를 검사할 수 없다 |
| D 사후 감시 워크플로우 | 막지 못한다. 막는 장치(C)가 먼저고, 웹 버튼 병합까지 잡아야 할 사고가 다시 나면 그때 더한다 |
| R1 `reviewDecision` | 보호 규칙 없이는 계산되지 않는다 — 모든 PR 이 영원히 막힌다 |
| R3 오래된 승인 차단 | 리뷰 반영 커밋마다 재승인이 필요해져 이번 스프린트 일정(광진 1인 리뷰)에 비해 비용이 크다. GitHub 기본값도 새 커밋이 승인을 무효화하지 않는다. 대신 `[주의]` 로 드러낸다 |
| W2 `.gitmodules` `ignore = all` | 모든 체크아웃에서 `Plan` 포인터 변경을 `git status` 에서 숨긴다 — "포인터를 커밋하지 않는다"(AGENTS.md) 를 사람이 확인하는 수단을 없앤다 |
| W4 `GIT_CONFIG_*` 우회 공식화 | 잊은 실행이 BLOCKED skip 으로 **조용히 초록**이 된다. 이 저장소가 계속 잡아 온 결함 모양이다 |
| 심볼릭 링크 `Plan → 본 체크아웃` | `T Plan` 이 변경으로 잡혀 `git add -A` 한 번에 포인터 자리에 링크가 커밋될 수 있다 |

## 이 결정이 틀렸다면 어떻게 드러나나

- 병합: 스크립트를 거쳐 병합된 PR 의 head 에 `SUCCESS` 가 아닌 체크가 있으면 틀린 것이다 — `gh pr view N --json statusCheckRollup` 으로 사후 확인할 수 있다. 반대로 정상 PR 이 계속 막히면(예: 워크플로우에 `if:` 조건 잡이 생겨 `SKIPPED` 가 정상이 되면) 판정이 너무 좁은 것이다.
- 스크립트를 거치지 않은 병합(웹 버튼)은 이 결정이 **막지 못한다.** 그런 병합이 생기면 안 C 의 한계가 드러난 것이고 D 를 더한다.
- worktree: `--ignore-submodules=dirty` 로도 rc≠0 인 서브모듈 상태가 나오면 W1 이 틀렸다 — 경계 검사가 다시 `BLOCKED` skip 사유를 내므로 skip 수에 드러난다. `TestBoundaryCheckSurvivesBrokenSubmoduleGitdir` 의 대조군이 git 버전 변화로 재현을 잃어도 그 테스트가 실패해 알린다.

## 민감도

- 필수 체크 목록은 숫자가 아니라 워크플로우 파일에서 매번 읽는다. 워크플로우가 하나 늘거나 줄어도 스크립트를 고칠 필요가 없다 — `paths` 필터 · `if:` 조건 잡이 생기는 경우만 판정 규칙을 다시 본다.
- 승인 기준 1건을 2건으로 올리면 시스템 팀은 2인 팀이라 작성자 외 승인자가 1명뿐이다 — 병합이 불가능해진다. 1건은 팀 규모가 정한 값이다.

## 남은 불확실성

- 웹 UI 의 병합 버튼은 여전히 열려 있다. 사람의 규율(§5.1 "스크립트로만")에 맡긴다.
- worktree 쪽 검증은 범위가 셋으로 나뉜다. 실제 linked worktree 생성 · 복사 · 서브모듈 초기화는 작성자 로컬 재현(git 2.43) 1회다. CI 회귀 테스트 2건은 일반 임시 저장소에 끊긴 gitfile 을 둔 **등가 상태**다(리뷰 기록상 CI git 2.55.0). `--ignore-submodules=dirty` 는 검사 옵션이지 복구 명령이 아니다. CI 가 worktree 절차(W3)까지 검증한 것은 아니다 — `docs/GIT_WORKFLOW.md` §11 에 같은 구분을 적었다.
- `pull_request` 에 `branches` · `types` 필터가 있어 PR 에서 돌지 않는 워크플로우는 필수로 남아 **영원히 막힌다**. 막는 쪽으로 틀리지만, 그런 필터가 생기면 판정 규칙을 다시 본다.
- `required_checks()` 는 YAML 파서 없이 이 저장소 워크플로우의 들여쓰기 모양만 읽는다. 행렬(matrix) 잡이나 재사용 워크플로우가 들어오면 체크 이름이 달라져 "보고되지 않았다" 로 막힌다 — 막는 쪽으로 틀리므로 위험하지는 않지만, 그때 파서를 고친다.
- 지금까지 60건 중 승인 0건이었다는 사실은 이 스크립트를 쓰기 시작하는 순간 **리뷰 대기**가 병합 일정의 병목이 된다는 뜻이다. Sprint 2 일정에서 그 비용이 얼마인지는 아직 모른다.
