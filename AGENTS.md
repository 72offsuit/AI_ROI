# 72offsuit / AI_ROI — 에이전트 지침

기존 과제(`Plan/`의 PRD/SRS v2.0 — **AI 기반 고객 이탈 예측 및 리텐션 ROI 최적화 시스템**)가 요구한 **시뮬레이터·AI 시스템**을 구현하는 저장소.

커머스 서비스 자체는 `Ecommerce_Service`에서 실체로 구축하며, 이 저장소는 그 위에 과제 내용을 이어붙인다. 2저장소 분리는 의도된 결정이다.

## `Ecommerce_Service`와의 관계

- 런타임 의존은 **없다.** 이 저장소는 단독으로 실행된다.
- 다만 이 저장소는 **`Ecommerce_Service`와 동일한 구조·환경으로 인식되어야 한다.** 별개의 가상 환경이 아니라 그 서비스를 대상으로 하는 시스템이다.
- 의도된 통합 플로우: **서비스에 시뮬레이터를 돌려 잡힌 결과를 대시보드에서 확인·검증하고 시스템을 활용**한다.

> PRD §88 / SRS §31의 단일 `project/` 구조와 SRS §37 제출 요구사항(public 전환 등)은 **기존 과제 기준**이다.
> **저장소를 public으로 전환할 계획이 없다** (2026-09-05 결정). private `Plan` 서브모듈은 문제가 되지 않는다.

## 먼저 읽을 것

1. **조직 공통 git 규약 정본** — `Plan/docs/GIT_WORKFLOW_CORE.md`
   git 작업(브랜치·커밋·PR·이슈) 전에 반드시 읽는다. 아래 요약은 정본을 대체하지 않는다.
2. **이 저장소의 워크플로우** — `docs/GIT_WORKFLOW.md`
   `Plan/GIT_WORKFLOW_BOOTSTRAP.md` 절차로 2026-09-11 생성했다. git 작업은 이 문서를 따른다.

`Plan/`이 비어 있으면 먼저 초기화한다.

```bash
git submodule update --init
```

## 반드시 지킬 것 (요약 — 전문은 `Plan/docs/GIT_WORKFLOW_CORE.md`)

- **에이전트 기본 권한은 L1(제안만).** commit·push는 사용자가 "커밋해"/"푸시해"를,
  Issue·PR 생성은 "이슈 만들어"/"PR 올려"를 명시한 뒤에만. **승격을 스스로 추론하지 않는다.**
- `main`에 직접 커밋하지 않는다. 브랜치는 `<type>/<short-kebab-description>`.
- merge · Issue close · 브랜치 삭제 · `push --force` · `reset --hard` · `rebase`는 **항상 개별 승인.**
- 미실행 검증을 통과로 표시하지 않는다. 실행 불가는 `BLOCKED`로 이유와 함께 기록한다.
- 결함을 조용히 고치지 않는다. 발견 → Issue 기록 → 수정 → 재시험.
- 스테이징은 경로를 명시한다. `git add -A` 지양.
- 비밀값·생성물을 커밋하지 않는다.

## 서브모듈

`Plan/`은 `72offsuit/Plan` 서브모듈이다 (기획 문서 PRD/SRS + 공통 규약).

- **서브모듈 포인터를 커밋하지 않는다.** `git add Plan`은 사용자가 명시적으로 지시할 때만.
- 작업용 체크아웃까지만 허용하고 스테이징·커밋에서 항상 제외한다.
- 기획 문서 수정은 `Plan` 저장소에서 직접 한다. 이 저장소의 `Plan/` 안에서 커밋하지 않는다.

## 파트 경계 — 작업 전 반드시 확인

이 저장소는 **서로 봐서는 안 되는 두 파트**로 나뉜다. `src/` 안에서 작업하기 전에 **`src/AGENTS.md`를 먼저 읽고**, 이어서 자기 파트 디렉터리의 `AGENTS.md`를 읽는다.

| 디렉터리 | 역할 | 비유 |
|---|---|---|
| `src/measurement/` | 이벤트 스키마·KPI·경제 규칙·Event Sink | 창구 |
| `src/simulator/` | 가상 고객 생성·행동·처치 반응 | 출제자 (정답을 안다) |
| `src/decision/` | Feature·Churn·Uplift·CLV·전략·최적화 | 수험생 (맞혀야 한다) |
| `src/diagnostics/` | Ground-truth 대비 사후 채점 | 채점자 |
| `src/orchestration/` | 실행 루프 | 지휘자 |

핵심 금지 사항:

- `simulator/`에서 작업할 때 **`results/`와 모델 리포트를 읽지 않는다.** AI 성능을 이유로 시뮬레이터 파라미터를 조정하지 않는다.
- `decision/`에서 작업할 때 **`data/hidden/`·`data/ground_truth/`·`src/simulator/`를 읽지 않는다.**
- **AUC·Qini·Incremental Profit 이야기가 시뮬레이터 작업 중에 나오면 멈추고 사용자에게 보고한다.**

가장 위험한 누수는 코드가 파일을 훔쳐보는 것이 아니라 **결과를 본 뒤 시뮬레이터를 고치는 것**이다 (PRD §80 Risk 1). 이 규칙은 `tests/test_isolation.py`가 강제한다.

## 검증

```bash
python3 -m unittest tests.test_isolation -v
```

파트 격리 규칙(import 경계·데이터 경로·지침 파일 존재)을 검사한다. **표준 라이브러리만 사용하므로 의존성 설치 없이 실행된다.** `src/` 또는 `tests/`를 수정하면 반드시 실행하고 결과를 PR에 기록한다.

**CI에서도 자동 실행된다** — `.github/workflows/isolation.yml`이 모든 PR과 `main` push에서 이 검사를 돌린다. `Plan` 서브모듈은 private이라 체크아웃하지 않으며, 검사 대상이 `src/`·`tests/`뿐이라 필요도 없다.

## 프로젝트 현황 (2026-09-14)

- 스택은 Python으로 확정. 의존성 매니페스트는 `requirements.txt`(`pyarrow`·`PyYAML`)와 `requirements-dev.txt`(`jsonschema`·`referencing`) 2종이며, **버전은 CI와 같은 3.12에서 해석해 고정했다.**
  - ★ SRS NFR-004는 `>= 3.10`이라고 적지만 **실제로는 3.10에서 동작하지 않는다.** `datetime.fromisoformat()`의 `Z` 접미사가 3.11부터 지원되는데(bpo-35829) `sink.py:394` 외 6곳이 전처리 없이 그 값을 넘긴다. CI가 3.12 고정이라 드러나지 않을 뿐이다. 선언을 좁히거나 코드를 맞추거나 — **아직 결정되지 않았다** (코드 리뷰 M3).
- `src/measurement/`는 구현 완료(M-01~M-09, 모듈 10개 + `__init__.py`). `src/simulator/`·`decision/`·`diagnostics/`·`orchestration/`은 **여전히 지침 파일만 있고 구현 코드가 없다.**
- `dashboard/`(Next.js, `:3001`)에 **라우트 8종**이 구현됨(d-01·d-02) — 게시물 연동 6(`V1`~`V6`) + 정적 1(`/triggers`, C1 작동 0종) + 개요 1(`/`). `results/`의 게시물을 **읽기만** 한다(`DB-012`·`DB-013`·`DB-014`).
- GATE 1은 **부분 봉인(`PARTIAL_FREEZE`)** 상태다. 완전 봉인(`LOCKED`)은 **0종**.
- CI는 `.github/workflows/isolation.yml`(의존성 없이) · `tests-with-deps.yml`(의존성 설치 후) **2종**이다. 저장소 전체 검증은 `python3 -m unittest discover -s tests` 이며 lint·build·타입 검사는 여전히 미정의.
  - 여기에 **건수를 적지 않는다.** 이전 판은 `407건` 이라고 적었고 테스트를 추가한 바로 다음 커밋에 낡았다 — 아무도 대조하지 않는 숫자를 문서에 두는 것이 이슈 `#59` 가 닫은 결함의 모양이다. 건수는 명령을 실행하면 나온다.
- 저장소 보안 설정 (이슈 `#66` · 보안 F4, 2026-09-14):
  - **Dependabot alerts — 활성화됨.** `gh api -X PUT repos/…/vulnerability-alerts`. 되돌리려면 같은 경로에 `DELETE`.
  - **Secret scanning — `BLOCKED`.** `HTTP 422 Secret scanning is not available for this repository` — private 저장소의 플랜 제한(GitHub Advanced Security 필요)이라 설정으로 열 수 없다. **켜지 않은 것을 켠 것으로 적지 않는다.** 커밋된 비밀값 감시는 여전히 **사람이 본다**.
  - CI 서드파티 액션은 커밋 SHA 로 고정돼 있다. 갱신 시 `uses:` 옆 주석의 태그를 함께 고친다.
- **존재하지 않는 명령을 문서·게이트·PR 본문에 쓰지 않는다.** 검증을 실행할 수 없으면 `BLOCKED`로 보고한다.
