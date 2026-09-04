# 72offsuit / AI_ROI — 에이전트 지침

`Plan/`의 PRD/SRS v2.0(**AI 기반 고객 이탈 예측 및 리텐션 ROI 최적화 시스템**)을 기준 문서로 삼는 저장소.

> **저장소 경계 미확정 (추정 아님 — 확인 필요)**
> PRD §88 *Suggested Repository Structure*는 `project/` **단일 저장소** 구조를 전제한다.
> `Ecommerce_Service` / `AI_ROI` 2개로 분리한 것은 PRD·SRS에 근거가 없는 결정이며,
> 두 저장소 간 책임 경계가 아직 문서화되어 있지 않다.
> **scope 목록과 `docs/GIT_WORKFLOW.md`를 만들기 전에 이 경계를 먼저 확정한다.**

## 먼저 읽을 것

1. **조직 공통 git 규약 정본** — `Plan/docs/GIT_WORKFLOW_CORE.md`
   git 작업(브랜치·커밋·PR·이슈) 전에 반드시 읽는다. 아래 요약은 정본을 대체하지 않는다.
2. **이 저장소의 워크플로우** — `docs/GIT_WORKFLOW.md`
   **아직 존재하지 않는다.** 스택과 디렉터리 구조가 잡힌 뒤
   `Plan/GIT_WORKFLOW_BOOTSTRAP.md` 절차(Step 1 정찰 → 추론표 → 확정 → 생성)로 만든다.

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

## 프로젝트 현황 (2026-09-04)

- 스택 **미확정**. 소스 디렉터리·의존성 매니페스트·CI 워크플로우가 아직 없다.
- 따라서 **검증 명령·CI job 이름·scope 목록이 정의되어 있지 않다.**
- **존재하지 않는 명령을 문서·게이트·PR 본문에 쓰지 않는다.** 검증을 실행할 수 없으면 `BLOCKED`로 보고한다.
