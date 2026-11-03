# DR-262-run-provenance-dirty — 실행 기록에 시스템 쪽 커밋 전 변경을 남기고, 봉인 실행은 `--require-clean` 으로 막는다

| | |
|---|---|
| 태스크 | 리드 · #262 (Sprint 3, GATE 2 Baseline #170 전) |
| 작성 | 인성(Danto7632, 에이전트 구현) · 2026-11-03 |
| 상태 | 확정 — 차단 정책은 사용자 결정(2026-11-03) |

## 무엇을 정하는가

`run_meta.provenance` 가 실행에 쓰인 코드를 어떻게 기록하는가. 그리고 저장소에 커밋 전 변경이 있을 때 실행을 막는가.

## 정하지 않으면 무엇이 막히나

- **GATE 2 Baseline(#170 · 11/06)의 출처를 믿을 수 없다.** 광진의 GATE 2 리뷰는 "Baseline 이 GATE 1 봉인 환경에서 나왔는지" 확인하는 것이다(#170 Sprint 3 범위). 그런데 지금 기록으로는 커밋 전 코드로 돈 실행도 HEAD 커밋으로 돈 것처럼 보인다.
- **실제로 일어났다.** #211 확인 실행(`SP-20261103-114303-75f731f8`)은 커밋 전 #211 변경(`run_sprint.py` · `config.py` 등)으로 돌았다. 그런데 `repo_commit` 은 `02648e9`, `simulator_worktree_dirty` 는 `false` 였다(#262).
- **조사하다 하나 더 찾았다. 출처를 실행이 _끝날 때_ 잰다.** `run()` 은 결과를 쓰기 직전에 `provenance()` 를 부른다. 기본 실행은 ≈ 2시간 10분이 걸린다(DR-211). 그 사이 같은 체크아웃에서 커밋하거나 config 를 고치면, 실제로 돈 것이 아니라 바뀐 뒤의 HEAD · config 해시가 기록된다.

## 선택지

어느 안이든 `run_meta` 에는 커밋 전 변경 여부와 바뀐 경로를 남긴다. 안끼리 다른 것은 실행을 막는가뿐이다.

| 안 | 내용 | 장점 | 단점 |
|---|---|---|---|
| A | 기록만 한다 | 코드가 가장 작다. 실행 방식이 바뀌지 않는다 | Baseline 을 커밋 전 변경으로 돌려도 2시간 실행이 끝나야, 그것도 리뷰 때에야 드러난다. 그러면 다시 돌려야 한다 |
| B | 기록하고, `--require-clean` 을 주면 시작 전에 막는다 | 봉인 실행만 막고 개발 실행은 그대로다. 막힌 실행도 시뮬레이션 전에 멈춰 비용이 없다 | 옵션을 빠뜨리면 막지 못한다. 기록에 `require_clean` 값과 변경 여부가 남으므로 리뷰에서 드러나기는 한다 |
| C | 기본으로 막고, `--allow-dirty` 를 주면 돈다 | 가장 엄격하다 | 개발 중 실행은 거의 늘 커밋 전 상태다. 그래서 `--allow-dirty` 가 상시 붙어 사실상 의미가 없다. `run()` 을 직접 부르는 로컬 테스트 하네스도 깨진다 |

## 조사한 것

| 출처 | 무엇을 말하나 | 우리 맥락에 얼마나 맞나 |
|---|---|---|
| `src/orchestration/run_sprint.py` `provenance()` (main `02648e9`) | dirty 검사는 `git status --porcelain -- src/simulator` 뿐이다. `repo_commit` 은 `rev-parse HEAD` 다. `run()` 이 결과를 쓰기 직전에 부른다 | 빈칸 두 개(경로 범위 · 측정 시점)의 직접 원인이다 |
| #211 확인 실행 `run_meta.json` (DR-211) | 커밋 전 변경으로 돈 실행이 `02648e9` · `simulator_worktree_dirty: false` 로 남았다 | 이 결정의 재현 사례다 |
| `docs/decisions/DR-179-restored-branch-read.md` NB-D · `MC-179-development-evaluation.md` | 같은 일이 있었다 — `repo_commit` 은 `cdc9233` 인데 실제 실행은 그 위 커밋 전 N2 코드였다. 그때는 결과의 commit 을 사후 수정하지 않고, 깨끗한 커밋에서 다시 돌리고 sidecar preflight 로 상태를 고정했다. "공용 게시물에 새 dirty 필드를 추가하는 변경은 이번 범위 밖" 이었다 | 사람이 매번 따로 하던 확인을 실행 기록 안으로 옮긴다. 사후 수정 금지 원칙은 그대로다 |
| `src/measurement/contracts.py` `build_provenance()` | 측정 계층 게시물도 `repo_commit` 만 적는다. 그 provenance 는 계약 스키마(`additionalProperties: false`, `tests/test_publish_contract.py`)에 묶여 있다 | 같은 빈칸이지만 고치려면 게시물 계약을 바꿔야 한다. GATE 1 봉인(11/04) 직전이라 이 기록에서 다루지 않는다(아래 불확실성) |
| `dashboard/src/lib/artifacts/sprint-types.ts` · `fixtures/sprint-v0/run_meta.json` | 대시보드의 `RunMeta` 는 `provenance` 를 읽지 않는다 | 필드를 더해도 대시보드는 바뀌지 않는다 |
| `docs/GIT_WORKFLOW.md` "worktree 에 `Plan/` 을 복사하지 않는다" | `Plan/` 을 잘못 복사한 worktree 에서는 `git status` 가 종료 코드 128 로 죽는다 | 그때 저장소 상태는 `null` 이고, `--require-clean` 은 "확인 못 함"으로 멈춘다. 깨끗하다고 추측하지 않는다 |
| `src/orchestration/AGENTS.md` "리포트에 반드시 남기는 것" | `simulator_commit` · config SHA-256 등을 실행 기록에 남긴다 | 기존 키는 이름과 뜻을 그대로 두고, 측정 시점만 시작으로 옮긴다 |

## 결정

**B.** 사용자가 2026-11-03 에 골랐다.

- **측정 시점은 시작이다.** `run()` 첫머리에서 `repo_state()` 로 HEAD · 커밋 전 변경 경로 · 시뮬레이터 커밋 · config 해시를 잰다. `run_meta.provenance` 는 이 값을 싣는다. 끝날 때 한 번 더 재서 달라진 것을 적는다.
- **범위는 저장소 전체다.** 추적 파일의 변경(스테이징 여부와 무관)과 `.gitignore` 밖의 새 파일을 센다. 서브모듈은 보지 않는다. 파일 이름은 `git status --porcelain=v1 -z` 로 읽어 공백 · 한글 이름도 그대로 남긴다.
- **새 · 바뀐 `run_meta.provenance` 키**:

| 키 | 뜻 |
|---|---|
| `repo_commit` | **시작 때의** HEAD (예전에는 끝날 때) |
| `repo_worktree_dirty` | 시작 때 커밋 전 변경이 있었나. git 을 못 쓰면 `null` |
| `repo_dirty_paths` · `repo_dirty_path_count` | 바뀐 경로(앞 200개)와 총수 |
| `simulator_commit` · `simulator_worktree_dirty` · `config_sha256` | 뜻은 같고, 시작 때 값이다. 시뮬레이터 dirty 는 위 경로 목록 중 `src/simulator/` 아래가 있는지다 |
| `require_clean` | `--require-clean` 으로 돌았나 |
| `repo_changed_during_run` · `repo_changes_during_run` | 끝날 때 HEAD · 바뀐 경로 · config 해시가 시작과 다른가, 다르면 무엇이 |
| `null_reason` | 저장소 상태를 읽지 못했을 때만 |

- **`--require-clean`**(`run_sprint` · `src/main.py` 둘 다): 시작 때 커밋 전 변경이 있거나 git 으로 확인하지 못하면 `DirtyRepoError` 를 던진다. 시뮬레이션 전이라 결과 폴더도 만들지 않는다. 종료 코드는 **4** 다. `src/main.py` 종료 코드 표에서 비어 있던 번호다(2 는 argparse 인자 오류).
- **봉인 실행(GATE 2 Baseline)은 `--require-clean` 으로, 태그한 커밋의 깨끗한 worktree 에서 돌린다.** 이 절차는 #170 할 일 표에 적는다.

**근거:** 봉인 실행이 커밋 전 코드로 도는 것은 시작 전에 막는 것이 가장 싸다(A 기각). 개발 실행까지 막으면 옵션이 상시 붙어 의미를 잃는다(C 기각). B 는 옵션을 빠뜨려도 조용히 넘어가지 않는다 — `require_clean: false` 와 `repo_worktree_dirty` 가 기록에 남아 GATE 2 리뷰에서 보인다.

## 기각한 안과 기각 사유

| 안 | 왜 택하지 않았나 |
|---|---|
| A 기록만 | 2시간 실행이 끝난 뒤, 그것도 리뷰에서야 드러난다. 그러면 다시 돌린다 |
| C 기본 차단 | 개발 실행 · 스모크 · 로컬 하네스 테스트가 거의 늘 커밋 전 상태라 `--allow-dirty` 가 상시 붙는다 |
| 결과에 영향을 주는 경로(`src/` · `config/`)만 보고 막는다 | 무엇이 결과에 영향을 주는지 고르는 것 자체가 틀릴 수 있다. 예컨대 `docs/research/realism_report.json` 은 결과 폴더로 복사된다. 봉인 실행은 깨끗한 worktree 에서 돌리면 되므로 전체를 본다 |
| 끝날 때만 잰다(예전 그대로) | 2시간 사이의 커밋 · config 수정이 이 실행의 기록이 된다 |
| 측정 계층 `build_provenance()` 도 같이 고친다 | 게시물 계약 스키마 변경이다. GATE 1 봉인 직전이라 따로 정한다 |

## 이 결정이 틀렸다면 어떻게 드러나나

- Baseline `run_meta` 에서 `require_clean: true` 인데 `repo_worktree_dirty` 가 `true` 다 → 차단 배선이 틀렸다.
- 실행 중에 커밋했는데 `repo_commit` 이 새 커밋이거나 `repo_changed_during_run` 이 `false` 다 → 시작 측정이나 대조가 틀렸다.
- 깨끗한 worktree 에서 `--require-clean` 이 멈춘다 → 오탐이다. `.gitignore` 에서 빠진 실행 부산물이 있거나, git 을 못 쓰는 환경이다. 메시지에 경로가 나온다.

## 민감도

- `DIRTY_PATHS_LIMIT` 200 은 기록 크기만 바꾼다. 총수(`repo_dirty_path_count`)는 늘 다 센다. 50 이나 1,000 이어도 판정은 같다.
- `git` 호출은 시작과 끝에 각 3번씩이다(`rev-parse` · `status` · `log`). 이 저장소에서는 1초 안에 끝나므로 2시간 실행에 비하면 무시할 만하다. 제한 시간 10초를 넘기면 상태는 `null` 이 되고, `--require-clean` 이면 멈춘다.

## 남은 불확실성

- **이미 바뀌어 있던 파일을 실행 중에 또 고친 것은 잡지 못한다.** 경로 목록이 같기 때문이다. `--require-clean` 실행은 시작 때 바뀐 파일이 없으므로 해당하지 않는다. 내용 지문(diff 해시)까지 남기는 것은 봉인 실행에 필요 없어 넣지 않았다.
- **`--out` 을 저장소 안 · `.gitignore` 밖에 두면, 실행이 만든 파일이 "실행 중 생긴 변경"으로 적힌다.** 기본값(`data/sprint/…` · `results/`)은 `.gitignore` 안이다.
- **측정 계층 게시물(`build_provenance`)과 `src/main.py` 의 `main_cli.json` 은 여전히 `repo_commit` · config 해시만 적는다.** 같은 실행의 `run_meta.provenance` 가 정본이다. 게시물 쪽은 필요하면 따로 정한다.
- **main 클론에는 남의 변경(` M dashboard/AGENTS.md`)이 있다.** 그래서 거기서는 `--require-clean` 이 멈춘다. 의도한 동작이다. 봉인 실행은 깨끗한 worktree 에서 한다.
- **로컬 검증 범위.** 새 `tests/test_run_provenance.py` 는 시뮬레이터 import 를 뺀 하네스와 임시 git 저장소로 돈다. 실제 실행 루프 통합 테스트(`test_orchestration_*`)는 로컬에서 돌리지 않았다 — CI 가 판정한다.
