# DR-241-ci-boundary-fetch-depth — PR CI 가 팀 경계를 실제로 대조하게 한다

| | |
|---|---|
| 태스크 | 이슈 241 · 관련 172 · 238 |
| 작성 | Paul(리드) · 2026-10-25 |
| 상태 | 확정 (사용자 결정 2026-10-25 — 수정 진행 · BLOCKED 는 CI 에서 실패) |

## 무엇을 정하는가

① PR CI 에서 `test_branch_stays_inside_one_team` 이 `main` 대비 변경 목록을 못 구해 BLOCKED skip 되던 것을 어느 층에서 고치는가 ② 고친 뒤에도 같은 BLOCKED 가 CI 에서 다시 나면 skip 으로 둘 것인가 실패로 볼 것인가.

## 정하지 않으면 무엇이 막히나

두 팀 경로(시뮬 · 시스템)를 한 PR 에 섞어도 CI 가 초록이다. `scripts/safe_merge.py`(#238)는 체크 SUCCESS 만 보므로 이것도 막지 못한다. 격리(PRD §21.1)의 쓰기 쪽 자동 대조가 **PR 단계에서 비어 있는** 채로 GATE 1·2 봉인 전까지 두 팀이 동시에 작업한다.

## 선택지

| 안 | 내용 | 장점 | 단점 |
|---|---|---|---|
| A | 전체 스위트를 돌리는 workflow 3개의 checkout 에 `fetch-depth: 0` | 한 줄씩. `origin/main` 이 항상 있다 | 전체 이력을 받는다 |
| B | checkout 뒤 `git fetch --depth=N origin main` 단계 추가 | 받는 양이 적다 | N 을 골라야 하고, 브랜치가 N 보다 오래되면 merge-base 가 범위 밖이라 다시 실패한다 |
| C | 테스트가 `GITHUB_BASE_REF` 로 비교 대상을 고른다 | PR 이 다른 브랜치를 겨냥해도 맞다 | 그 ref 도 얕은 체크아웃엔 없다 — A·B 가 여전히 필요하고 테스트에 CI 전용 분기가 는다 |
| D1 | CI(`GITHUB_ACTIONS=true`)에서는 BLOCKED 를 **실패**로, 로컬은 skip 유지 — 테스트 안에서 | 세 잡 모두에 같은 규칙. 단위 테스트로 두 방향을 고정할 수 있다 | 테스트가 실행 환경을 안다 |
| D2 | `tests-with-deps.yml` 의 "미설치 skip 0건" 게이트처럼 workflow 에서 skip 사유를 grep 해 실패 | 테스트 무변경 | 한 잡에만 붙는다. 사유 문구가 바뀌면 조용히 무력화된다 |
| D3 | 지금처럼 skip | 변경 없음 | 이 결함 그 자체다 |

## 조사한 것

| 출처 | 무엇을 말하나 | 우리 맥락에 얼마나 맞나 |
|---|---|---|
| `actions/checkout` `action.yml` — 우리가 고정한 커밋 `11d5960a` (`gh api repos/actions/checkout/contents/action.yml?ref=11d5960a…`) | `fetch-depth`: "Number of commits to fetch. 0 indicates all history for all branches and tags." · `default: 1` | 그대로 맞다 — 세 workflow 모두 이 커밋을 쓰고 `fetch-depth` 를 주지 않았다 |
| GitHub 문서 Variables reference (<https://docs.github.com/en/actions/reference/workflows-and-actions/variables>) | `GITHUB_ACTIONS`: "Always set to `true` when GitHub Actions is running the workflow." · "differentiate when tests are being run locally or by GitHub Actions" | 그대로 맞다 — workflow 가 따로 선언하지 않아도 켜지므로 선언을 잊을 자리가 없다 |
| 같은 문서의 `GITHUB_BASE_REF` | `pull_request` · `pull_request_target` 에서만 설정 | C 를 택해도 push · `workflow_dispatch` 에선 쓸 수 없다 |
| CI 실행 비교 (2026-10-25 `gh run view --log`) | `main` d9a3902 push (run 39931602748) `Tests (with deps)` skipped=12 · PR #236(문서 1개만 변경) skipped=13, 차이는 이 검사의 BLOCKED 1건. #237~#240 도 전부 13 | PR 내용과 무관한 +1 — 체크아웃 설정이 원인임을 가리킨다 |
| 로컬 재현 | `--depth 1` 클론 + `GITHUB_ACTIONS=true` → 이 PR 의 테스트로 **FAIL**(#241 사유), 환경변수 없이 → skip. `origin/main` 이 있는 클론 → ok | 수정 전 CI 조건과 수정 후 CI 조건을 둘 다 재현했다 |
| 저장소 크기 | 전체 이력 클론의 `.git` 28MB · `main` 커밋 63개 | A 의 비용이 무시할 만하다 |

## 결정

**A + D1.** `isolation.yml` · `tests-with-deps.yml` · `python-compat.yml` 의 checkout 에 `fetch-depth: 0`. `tests/test_team_boundaries.py` 는 변경 목록을 못 구하면 `GITHUB_ACTIONS=true` 에서 `self.fail`, 그 밖에서는 지금처럼 BLOCKED skip. `TestBlockedIsAFailureInCI` 가 두 방향을 고정한다.

**근거:** A 는 기본값 1 이 원인이라는 사실(위 `action.yml`)에 정확히 대응하고, 이력이 28MB 라 비용이 없다. D1 은 이 저장소가 반복해서 잡아 온 모양 — **대조하지 않은 것이 초록으로 보이는 것** — 을 CI 에서 다시 못 일어나게 한다. CI 는 이제 `main` 을 받으므로 거기서 못 구했다면 skip 할 이유가 아니라 설정이 깨진 것이다. 로컬은 git 이 없거나 `main` 을 받지 않은 체크아웃이 정상적으로 있으니 skip 이 정직하다.

## 기각한 안과 기각 사유

| 안 | 왜 택하지 않았나 |
|---|---|
| B | N 이 선언이 되고 아무도 대조하지 않는다 — 오래된 브랜치에서 merge-base 가 잘려 같은 BLOCKED 로 돌아온다. 아끼는 양(28MB 중 일부)이 그 위험보다 작다 |
| C | 얕은 체크아웃엔 base ref 도 없어 A 를 대체하지 못한다. push · `workflow_dispatch` 에선 값이 없다 |
| D2 | 세 잡 중 한 곳에만 붙고, skip 사유 문구를 grep 하는 순간 그 문구가 계약이 된다 — 문구를 다듬으면 게이트가 조용히 꺼진다. 단위 테스트로 고정할 수도 없다 |
| D3 | #241 이 이것이다 |
| 테스트를 workflow 에서 따로 한 번 더 돌려 결과 확인 | 스위트가 이미 세 번 돈다(`tests-with-deps.yml`). 같은 정보를 테스트 안에서 얻을 수 있다 |

## 이 결정이 틀렸다면 어떻게 드러나나

- PR CI 로그에 `test_branch_stays_inside_one_team ... ok` 대신 `FAIL … (#241)` 가 찍힌다 → `fetch-depth: 0` 만으로는 `origin/main` 이 생기지 않는다는 뜻이다.
- 두 팀 경로를 함께 바꾼 시험 브랜치에서 CI 가 초록이다 → 검사가 돌기는 하지만 비교 범위가 비어 있다(예: `main` 푸시처럼 `origin/main...HEAD` 가 공집합). 이 대조군이 이 결정의 핵심 반증이다.
- `Tests (with deps)` 의 PR skip 수가 `main` 과 같아지지 않는다.

## 민감도

`fetch-depth` 값은 0 을 택해 민감도 자체를 없앴다(B 의 N 이 사라짐). 이력이 10배(약 280MB)가 되어도 checkout 시간 몇 초 수준이라 결정이 바뀌지 않는다. `GITHUB_ACTIONS` 이외의 CI(로컬 `act` 등)에서는 이 규칙이 켜지지 않고 skip 으로 남는다 — 그 환경은 지금 없다.

## 남은 불확실성

- **원격 대조군 미실행(BLOCKED)** — 두 팀 경로를 섞은 시험 브랜치를 `workflow_dispatch` 로 돌려 CI 가 실패하는지는 이 PR 을 올린 뒤에 확인한다. 로컬에서는 같은 테스트가 그 모양을 잡는다.
- `main` 푸시 실행은 `origin/main...HEAD` 가 비어 대조할 것이 없다. 이 검사는 브랜치 단위라 의도된 것이지만, `main` 에 직접 섞인 커밋은 이 검사가 아니라 리뷰와 병합 절차(#238)가 막아야 한다.
- 앞으로 git 이 없는 CI 잡(예: Docker 안에서 스위트 실행)이 생기면 거기서 이 테스트가 실패한다. 그 잡은 `GITHUB_ACTIONS` 를 컨테이너에 넘기지 않거나 이 테스트를 제외해야 한다 — 그때 이 DR 을 갱신한다.
