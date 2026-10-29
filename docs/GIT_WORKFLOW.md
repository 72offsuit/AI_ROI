# AI_ROI Git Workflow

> 생성: `Plan/GIT_WORKFLOW_BOOTSTRAP.md` v1.0 기반 · 대상 저장소 정찰일 2026-09-11
> 목적: 어떤 에이전트·기여자가 작업하더라도 Issue → Branch → Commit → PR 흐름을 일관되게 유지한다.
> 상위 정본: `Plan/docs/GIT_WORKFLOW_CORE.md`(조직 공통). 충돌 시 정본이 우선한다.

## 1. 기본 원칙

- `main`에 직접 커밋하지 않는다. 통합 브랜치는 없다 — `<type>/<설명>` → `main` 1단이다.
- 한 Issue는 하나의 명확한 작업 단위를 가진다.
- 한 Branch는 원칙적으로 하나의 Issue를 해결한다.
- 하나의 변경과 그 변경의 테스트는 **같은 PR**에서 검증한다.
- 커밋 전 `git status`, `git diff --check`, §7 게이트, 비밀값 추적 여부를 확인한다.
- 생성물·비밀값을 커밋하지 않는다. `.gitignore`가 `data/`·`models/`·`docs/data_spec.pdf`·`__pycache__/`·`.venv/`를 제외한다.
- 서브모듈 `Plan/` 포인터 변경은 **에이전트가 커밋하지 않는다.** 작업용 체크아웃까지만 허용하고 스테이징·커밋에서 항상 제외한다. `git add Plan`은 사용자가 명시할 때만.
- **파트 격리(`src/AGENTS.md`)는 이 문서보다 상위 제약이다.** 격리를 깨는 변경은 워크플로우를 지켰더라도 병합하지 않는다.

## 2. 브랜치 이름

```text
<type>/<short-kebab-description>
```

허용 type은 §3의 커밋 type과 같다.

```text
feat/kpi-definition-module
fix/sink-partition-overwrite
docs/git-workflow
test/parquet-roundtrip
chore/requirements-manifest
```

## 3. Commit 메시지

Conventional Commits를 쓴다. **제목에 scope를 넣지 않는다.**

```text
type: 한글 설명
```

| type | 용도 | 근거 |
|---|---|---|
| `feat` | 기능 추가 | 기존 이력 (`#50`·`#51`) |
| `fix` | 재현 가능한 결함 수정 | 신규 — `#53` 등 결함 Issue 대응 |
| `docs` | 문서·명세 | 기존 이력 (`#36`·`#3`) |
| `chore` | 의존성·도구·서브모듈 포인터·설정 | 기존 이력 (7건, 최다) |
| `ci` | 워크플로우 | 기존 이력 (`#41`) |
| `refactor` | 동작을 유지하는 구조 변경 | 신규 |
| `test` | 테스트 추가·수정 | 신규 |

**scope를 쓰지 않는 근거:** 최근 100개 커밋에서 `type(scope):` 형식이 **0건**이다. 분류는 제목이 아니라 **라벨**이 담당한다(§4). 형제 저장소 `Ecommerce_Service/docs/GIT_WORKFLOW.md`도 같은 규약이다.

규칙:

- 콜론 앞에 공백을 넣지 않고 뒤에 한 칸을 둔다.
- 한글로 **변경 결과**를 쓴다. 식별자·고유명사는 원래 표기를 유지한다(`Event Sink`, `EVENT SCHEMA v1`, `pyarrow`).
- 제목 끝의 마침표는 생략한다.
- 커밋은 **본문 없이 제목 한 줄**로 쓴다. 상세는 PR 본문에 남긴다.
- 한 commit에는 한 논리 변경만 담는다.
- 요구사항 ID를 쓸 때는 제목에 괄호로 붙인다 — `(M-2)`, `(DATA-003)`.

실제 이력에서 형식에 맞는 예:

```text
feat: 이벤트 스키마 정의 — 측정 계층 계약 (M-1)
feat: Event Sink 구현 — 수집·검증·파티션 저장 (M-2)
ci: 파트 격리 검사 자동 실행 워크플로우 추가
```

앞으로 쓸 예 (실제 커밋이 아니다):

```text
fix: Sink 재기록 시 파티션 덮어쓰기 해소 (M-2)
docs: 서비스 UI ↔ 시뮬레이터 공통 기록 계약 정의 (M-3)
test: jsonl.gz 와 Parquet 산출 일치 검증 추가
```

형식 이탈률은 15건 중 1건(`Initial commit`)으로 약 6.7%다. 과거 이력은 손대지 않는다.

## 4. Issue

**모든 코드 변경에 Issue를 요구한다.** `src/`·`tests/`·`config/`·`dashboard/`·`.github/` 변경은 Issue 없이 시작하지 않는다. 문서·오타 수정은 예외다.

Issue 템플릿은 이 저장소에 없다. 아래를 본문에 포함한다.

- 문제와 목적 — 현재 문제 / 작업으로 달성할 결과
- 범위 — 포함 / 제외
- 수용 기준 — 체크박스
- 검증 계획 — 명령 · 기대 결과 · 필요한 환경
- 의존성과 미결정 사항 — 선행 Issue · 결정이 필요한 사항 · 진행을 막는 조건

제목은 커밋과 같은 형식(`type: 한글 설명`)을 쓴다.

라벨로 분류한다. **제목에 scope를 넣는 대신 라벨을 쓴다.**

| 축 | 라벨 |
|---|---|
| 작업 성격 | `kind/dev` · `kind/docs` · `kind/decision` · `kind/research` |
| 범위 | `scope/M-measurement` · `scope/A-foundation` · `scope/B-customer-model` · `scope/C-simulator` · `scope/D-dashboard` |
| 결함 | `bug` |

## 5. Pull Request

제목은 커밋 규약을 따르되 PR 전체의 최종 목적을 표현한다. squash merge로 생성될 커밋 제목이 곧 PR 제목이므로 **제목 한 줄 규칙을 유지**하고 자동 생성 본문은 비운다.

본문 필수 항목:

- 연결 Issue — `Closes #<n>` 또는 `Refs #<n>`
- 변경 요약
- **파트 격리 영향** — 어느 파트(`measurement`/`simulator`/`decision`/`diagnostics`/`orchestration`/`dashboard`)를 건드렸는지, 격리 규칙 위반이 없는지
- **봉인 영향** — GATE 1~4 봉인 항목을 건드렸는지. 건드렸다면 재실행 범위
- 테스트 결과 — `python3 -m unittest discover -s tests` 출력 요약
- 수동 검증 방법
- 남은 위험·미결정

Merge 기준:

- CI **전 잡** 통과 — `.github/workflows/` 의 `pull_request` 워크플로우 전부(현재 `Tests` · `Tests (with deps)` · `파이썬 3.10 호환` · `대시보드 검증`). `Tests` 하나만 보던 이전 기준이 `#141`(`Tests (with deps)` 실패)을 통과시켰다
- 작성자가 아닌 리뷰어의 **승인(`APPROVED`) 1건** — `COMMENTED` 는 승인이 아니다
- §7 출하 게이트 충족
- 미해결 `bug` 라벨 결함 0건

**merge 방식은 squash merge다.** PR 안의 작업 단위 커밋은 리뷰를 위해 보존되지만 `main`에는 squash 커밋 하나로 반영된다. merge 실행 권한은 §6을 따른다.

### 5.1 병합은 `scripts/safe_merge.py` 로만 한다 (#172)

이 저장소는 private + GitHub Free 라 **브랜치 보호(필수 체크 · 필수 리뷰)를 켤 수 없다.** 서버가 막아 주지 않아 `#141` 이 `Tests (with deps)` **실패 상태로 병합됐다.** GitHub 의 `reviewDecision` 도 보호 규칙이 없으면 계산되지 않아 늘 빈 값이다. 그래서 `gh pr merge` 를 직접 부르지 않고 아래 스크립트를 거친다.

```bash
python3 scripts/safe_merge.py <PR 번호> --dry-run   # 판정만 — 무엇이 막혔는지 출력
python3 scripts/safe_merge.py <PR 번호>             # 판정 → 통과하면 squash 병합
```

| 막는 조건 | |
|---|---|
| PR 이 열려 있지 않거나 초안 | |
| 필수 체크가 **아직 보고되지 않음** | 필수 목록은 `.github/workflows/*.yml` 에서 읽는다. 푸시 직후처럼 일부만 뜬 상태는 보고된 것만 보면 초록이다. 필수 잡은 **정확한 (워크플로우, 잡) 쌍**으로만 찾는다 — 다른 워크플로우의 같은 이름 잡이나 같은 이름의 외부 상태는 대신하지 못한다 |
| 필수 체크 목록이 **비었거나 읽지 못함** | 워크플로우가 없는 sparse checkout · 스크립트만 복사한 경우 · 해석 실패. 무엇을 요구할지 모르면 판정하지 않는다. **워크플로우 하나 · 잡 하나만 못 읽어도 막는다** — 트리거 · 잡 자리에 스크립트가 읽지 않는 표기(인라인 `{…}` · 여러 줄 `[…]` · `<<` · 여러 줄 따옴표 스칼라 · 최상위 키가 아닌 0열 줄 등)가 있으면 그 줄을 건너뛰지 않고 실패한다. 읽는 표기는 DR-172 「결정」 |
| 보고된 체크 중 `SUCCESS` 가 아닌 것 | `SKIPPED` · `NEUTRAL` · 진행 중도 통과가 아니다 |
| 작성자가 아닌 리뷰어의 승인 0건 · 해소되지 않은 변경 요청 | 리뷰어마다 **마지막 판정**만 센다 |
| main 과 충돌 | |

- 통과하면 `gh pr merge --squash --match-head-commit <판정한 head>` 를 실행한다 — 판정 뒤에 커밋이 올라오면 gh 가 거부한다.
- **우회 옵션이 없다.** 조건을 못 맞추면 조건을 맞춘다. 막혔는데 꼭 병합해야 하는 사정이 생기면 스크립트를 고치지 말고 **사람이 결정하고 PR 에 사유를 남긴다.**
- 승인 뒤에 커밋이 더 올라온 경우는 막지 않고 `[주의]` 로 알린다 — 리뷰어가 그 커밋을 봤는지 확인한다.
- **필수 목록을 어디서 읽나.** 스크립트가 놓인 체크아웃의 `.github/workflows/` 다(현재 작업 폴더가 아니다 — 출력 둘째 줄에 경로가 찍힌다). **최신 `main` 체크아웃에서 실행한다**(`git pull` 후). 그래야 PR 이 고친 정의가 아니라 `main` 의 정의로 판정해, PR 이 자기 필수 목록을 줄이지 못한다.
- **워크플로우 · 잡 이름을 바꾸거나 지우는 PR 은 막힌다** — 옛 이름이 보고되지 않기 때문이다. 의도된 동작이다. 그런 PR 은 리뷰어가 workflow 변경을 승인한 뒤, **그 PR head 를 체크아웃한 곳에서** 스크립트를 실행해 새 정의로 판정한다. 판정 기준을 그 PR 하나에서만 바꾸는 것이므로 PR 에 그 사유를 남긴다.
- `pull_request` 이벤트에 `paths` · `paths-ignore` 필터가 있는 워크플로우는 PR 마다 돈다는 보장이 없어 필수에서 뺀다. 빼면 `[주의]` 로 출력한다. `push.paths` 처럼 다른 이벤트의 필터는 필수 목록을 줄이지 않는다. 지금은 뺀 워크플로우가 0개이고, 생기면 `tests/test_safe_merge.py` 가 실패해 사람이 보게 한다.
- 병합 실행 자체는 여전히 §6 의 **개별 승인** 대상이다. 스크립트는 승인을 대신하지 않고, 승인된 병합이 실패한 CI 위로 나가지 않게만 한다.
- 근거 · 기각한 안: `docs/decisions/DR-172-merge-guard.md`. 검사: `tests/test_safe_merge.py`.

## 6. 에이전트 git 권한

**기본 등급 L1(제안만).** 승격은 사용자의 명시 지시로만 이뤄지며, 한 번의 승격은 **그 작업 범위에서만** 유효하다. 승격을 스스로 추론하지 않는다.

| 등급 | 허용 | 승격 조건 |
|---|---|---|
| **L1 (기본)** | 읽기, `status`/`diff`/`log`, 브랜치·커밋·PR·Issue **초안 제안** | — |
| **L2** | 브랜치 생성, commit, push | 사용자가 "커밋해" / "푸시해"를 명시 |
| **L3** | Issue 생성·수정, PR 생성 | 사용자가 "이슈 만들어" / "PR 올려"를 명시 |
| **금지(항상)** | merge, Issue close, 브랜치 삭제, `push --force`, `reset --hard`, `rebase`, release/deploy | 매번 개별 승인 |

L2 이상 수행 시 반드시:

1. 현재 브랜치가 `main`이면 **새 브랜치를 먼저 만든다.**
2. `git status`로 의도하지 않은 파일이 섞이지 않았는지 확인하고 **경로를 명시해 스테이징한다.** `git add -A`를 쓰지 않는다.
3. `git diff --check`와 §7 게이트를 확인한다.
4. 원격 작업 전 `gh auth status`를 확인하고 결과 URL을 보고한다.

## 7. 출하 게이트

정식 게이트 문서는 없다. 아래를 모두 충족하면 통과다. **하나라도 미실행이면 통과로 표시하지 않는다.**

```text
python3 -m unittest discover -s tests     # 기준선 46건 · 회귀 0
git diff --check                          # 공백 오류
git status                                # 의도하지 않은 파일 없음
```

- **현재 이 저장소에 실행 가능한 검증은 위 하나뿐이다.** lint·build·타입 검사는 정의되어 있지 않다. **존재하지 않는 명령을 PR 본문·문서·게이트에 쓰지 않는다.**
- 의존성 매니페스트가 없다. `tests/test_isolation.py`는 표준 라이브러리만 쓴다 — 새 의존성을 도입해도 이 성질이 유지되어야 한다(ISO-005).
- `확인하지 않음`·`아마 동작함`은 통과가 아니다.
- 실행할 수 없는 검증은 **`BLOCKED`로 이유와 함께** 기록한다.

## 8. 결함 수명주기

발견한 오류를 **조용히 고치지 않는다.**

```text
오류 발견 → 동일 원인 기존 Issue 검색 → 없으면 Issue 생성 → 수정
→ fix commit 에 Issue 연결 → 동일 재현 시험 → 게이트 재실행
→ merge 후 해결 근거 기록 → 승인 후 close
```

커밋 연결은 PR 본문에 쓴다(커밋은 제목 한 줄 규칙).

```text
Fixes #53
Refs #44
```

심각도는 기존 라벨에 매핑한다.

| 심각도 | 라벨 | 예 |
|---|---|---|
| 차단 | `bug` + 해당 `scope/*` | 데이터 소실, 격리 위반, 봉인 훼손 |
| 일반 | `bug` | 계산 오류, 크래시 |
| 개선 | `enhancement` | 성능·구조 |

- 같은 근본 원인의 반복 실패는 Issue 하나에 증거를 누적한다.
- 서로 다른 근본 원인은 각각 Issue로 만든다.
- **보안·데이터 유실·격리 위반은 다른 오류와 묶지 않는다.**
- Issue를 merge 전에 닫지 않는다.

## 9. 작업 단위별 권장 세트

**측정 계층 모듈 구현**

```text
Issue   feat: KPI·지표 정의 모듈 — Primary/Guardrail/Secondary 고정 (M-4)
        labels: kind/decision, scope/M-measurement
Branch  feat/kpi-definition-module
Commit  feat: KPI 정의 모듈 구현 (M-4)
PR      feat: KPI·지표 정의 모듈 추가 (M-4)   → Closes #46
```

**결함 수정**

```text
Issue   fix: Event Sink 결함 3건 — 파티션 덮어쓰기 · strict=False 크래시 · 타임존 미강제
        labels: kind/dev, scope/M-measurement
Branch  fix/sink-partition-overwrite
Commit  fix: Sink 재기록 시 파티션 덮어쓰기 해소 (M-2)
PR      fix: Event Sink 결함 3건 수정   → Closes #53, Refs #44
```

**대시보드 구현**

```text
Issue   feat: 관측 화면군 수집 현황 뷰 구현
        labels: kind/dev, scope/D-dashboard
Branch  feat/dashboard-ingestion-view
Commit  feat: 수집 현황 화면 구현
PR      feat: 관측 대시보드 수집 현황 뷰   → PR 본문에 파트 격리 영향 명시
```

## 10. `.agent-team/` 취급

BATHOS 웨이브 산출물은 **커밋한다.** 생성물이 아니라 **의사결정 기록**이며, W5·W6이 이 문서를 읽고 구현한다 — charter·task-graph·게이트 판정·게시 계약 스키마·ADR이 여기 있다.

예외 하나: **목업 캔버스 HTML은 커밋하지 않는다.** Claude Design 에디터 런타임이 통째로 들어간 생성물(2.5MB)이고 아티팩트 URL로 접근 가능하다. `.gitignore`가 제외한다.

`.agent-team/` 변경은 `docs` type을 쓴다.

## 11. git worktree 와 `Plan` 서브모듈 (#172)

에이전트가 이슈마다 `git worktree` 를 따로 쓰는 일이 많다. **새 worktree 의 `Plan/` 은 빈 디렉터리다** — 서브모듈은 worktree 마다 따로 초기화되기 때문이다. 이 상태는 정상이고 테스트도 그대로 돈다.

★ **본 체크아웃의 `Plan/` 을 worktree 로 복사하지 않는다.** `Plan/.git` 은 디렉터리가 아니라 `gitdir: ../.git/modules/Plan` 한 줄짜리 파일이다. worktree 에서는 `.git` 이 **파일**이라 이 상대 경로가 가리키는 곳이 없고, 그때부터 그 worktree 의 기본 `git status` 가 전부 `fatal: not a git repository: Plan/../.git/modules/Plan`(종료 코드 128)로 죽는다. 스프린트 1 에서 `tests/test_team_boundaries.py` 가 BLOCKED skip 으로 빠지고 에이전트마다 `GIT_CONFIG_* … submodule.Plan.ignore=all` 을 붙여 돌린 원인이 이것이다(2026-10-23 재현).

| 하고 싶은 것 | 할 일 |
|---|---|
| worktree 에서 PRD/SRS 를 **읽기만** | 본 체크아웃의 `Plan/` 을 **경로로 읽는다** (`<본 체크아웃>/Plan/…`). 복사하지 않는다 |
| worktree 안에 `Plan/` 이 **있어야** 함 (`tokens:test` 등) | worktree 안에서 `git submodule update --init` — worktree 전용 서브모듈 저장소가 `.git/worktrees/<이름>/modules/Plan` 에 따로 생긴다. 네트워크와 `Plan` 접근 권한이 필요하다 |
| 이미 복사해서 깨졌다 | 복사본 `Plan/` 을 지우고 빈 디렉터리로 되돌린 뒤 필요하면 위 줄. 복사본은 정본이 아니므로 지워도 잃는 것이 없다 — 다만 그 안에서 편집한 것이 있으면 먼저 `Plan` 저장소로 옮긴다 |

- `tests/test_team_boundaries.py` 는 이제 `git status --ignore-submodules=dirty` 로 변경 목록을 얻어 **깨진 gitdir 에서도 BLOCKED 가 되지 않는다.** `Plan/**` 은 어느 팀 소유도 아니라 판정에 영향이 없다. `GIT_CONFIG_*` 우회는 더는 필요 없다 — 쓰지 않는다.
- 저장소 설정(`.gitmodules` 의 `ignore = all`)으로 해결하지 않는다. 모든 체크아웃에서 `Plan` 포인터 변경까지 `git status` 에서 숨겨, "포인터를 커밋하지 않는다"(§1)를 사람이 확인할 수단이 사라진다.
- **검증 범위를 구분한다.** 무엇을 어디까지 확인했는지는 아래와 같다.
  - 실제 linked worktree 를 만들고, `Plan/` 을 복사해 깨뜨리고, worktree 안에서 서브모듈을 초기화하는 재현은 작성자 로컬(git 2.43, 2026-10-23)에서 1회 했다. 기록은 DR-172 조사한 것에 있다.
  - CI 의 회귀 테스트 2건(`TestBoundaryCheckSurvivesBrokenSubmoduleGitdir`)은 linked worktree 를 만들지 않는다. **일반 임시 저장소에 끊긴 gitfile 을 둔 등가 상태**로, `git status` 가 죽는 것(대조군)과 경계 검사가 그래도 도는 것을 본다. worktree 생성 · 서브모듈 초기화 절차 자체는 CI 가 검증하지 않는다.
  - `--ignore-submodules=dirty` 는 **검사 옵션**이다. 서브모듈 내부 상태를 보지 않게 할 뿐 깨진 gitdir 을 고치지 않는다. 복구는 위 표의 셋째 줄이다.
- 근거 · 기각한 안: `docs/decisions/DR-172-merge-guard.md`.
