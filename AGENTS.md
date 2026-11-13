# 72offsuit / AI_ROI — 에이전트 지침

기존 과제(`Plan/`의 PRD/SRS v2.0 — **AI 기반 고객 이탈 예측 및 리텐션 ROI 최적화 시스템**)가 요구한 **시뮬레이터·AI 시스템**을 구현하는 저장소.

커머스 서비스 자체는 `Ecommerce_Service`에서 실체로 구축하며, 이 저장소는 그 위에 과제 내용을 이어붙인다. 2저장소 분리는 의도된 결정이다.

## `Ecommerce_Service`와의 관계

- 런타임 의존은 **없다.** 이 저장소는 단독으로 실행된다.
- 다만 이 저장소는 **`Ecommerce_Service`와 동일한 구조·환경으로 인식되어야 한다.** 별개의 가상 환경이 아니라 그 서비스를 대상으로 하는 시스템이다.
- 의도된 통합 플로우: **서비스에 시뮬레이터를 돌려 잡힌 결과를 대시보드에서 확인·검증하고 시스템을 활용**한다.

> PRD §88 / SRS §31의 단일 `project/` 구조와 SRS §37 제출 요구사항(public 전환 등)은 **기존 과제 기준**이다.
> **저장소는 2026-11-14 public 으로 전환했다** — 2026-09-05 "전환 계획 없음" 결정의 번복(리드 결정). 이유: 조직 Free 요금제의
> Actions 무료 시간(월 2,000분)이 바닥나 CI 가 시작되지 않았고, 비공개로 지킬 상업적 이유가 없다.
> 그래서 이슈 · PR · 코멘트 · 커밋(작성자 이메일 포함)이 **모두 공개**다 — 개인정보 · 멘토 정보 · 비밀값을 올리지 않는다.
> **자체 호스팅 러너를 등록하지 않는다**(public 저장소에서는 누구나 PR 로 그 기기에서 코드를 돌릴 수 있다).
> 라이선스 파일은 두지 않는다 — 열람은 자유지만 저작권은 팀에 있다. private `Plan` 서브모듈은 그대로 private 이고 CI 는 체크아웃하지 않는다.

## 먼저 읽을 것

0. **최초 진입점** — `README.md`
   저장소가 무엇이고, 어떻게 돌리고, 지금 무엇이 있고 없는지. **처음 붙으면 여기부터.**

0-1. **결정 기록 제도** — `docs/DECISION_RECORDS.md`
   이슈는 태스크 목록이 아니라 **무엇을 정하고 무엇을 조사하고 무엇을 증거로 남길지의 안내서**다.
   체크박스를 다 채워도 결정 기록이 없으면 그 태스크는 끝난 것이 아니다.
   템플릿 `docs/decisions/_TEMPLATE_{design,model}.md`, 강제 `tests/test_decision_records.py`.

0-2. **C2 착수 지침** — `docs/TEAM_SETUP.md`
   **두 팀(시뮬레이터 · 시스템)으로 나뉜 뒤의 진입점이다.** 팀·소유 경로·태스크 번호·착수 절차가 한 곳에 있다.
   사람이든 에이전트(Claude · Codex · 그 외)든 **처음 붙을 때 여기부터 읽는다.**
   기계가독 판본은 `docs/team_boundaries.json`, 강제는 `tests/test_team_boundaries.py`.
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
- `decision/`에서 작업할 때 **`data/hidden/`·`data/ground_truth/`·`src/simulator/`를 읽지 않는다.** 시뮬레이터 생성 규칙 · 보정값 문서(페르소나 · `config/simulator*.yaml` · 일부 DR)도 읽지 않는다 — 전체 목록은 `docs/team_boundaries.json` 의 `teams.sys.must_not_read`.
- **AUC·Qini·Incremental Profit 이야기가 시뮬레이터 작업 중에 나오면 멈추고 사용자에게 보고한다.**

가장 위험한 누수는 코드가 파일을 훔쳐보는 것이 아니라 **결과를 본 뒤 시뮬레이터를 고치는 것**이다 (PRD §80 Risk 1). 이 규칙은 `tests/test_isolation.py`가 강제한다.

## 검증

```bash
python3 -m unittest tests.test_isolation -v
```

파트 격리 규칙(import 경계·데이터 경로·지침 파일 존재)을 검사한다. **표준 라이브러리만 사용하므로 의존성 설치 없이 실행된다.** `src/` 또는 `tests/`를 수정하면 반드시 실행하고 결과를 PR에 기록한다.

**CI에서도 자동 실행된다** — `.github/workflows/isolation.yml`이 모든 PR과 `main` push에서 이 검사를 돌린다. `Plan` 서브모듈은 private이라 체크아웃하지 않으며, 검사 대상이 `src/`·`tests/`뿐이라 필요도 없다.

## 프로젝트 현황 (2026-09-22)

- 스택은 Python으로 확정. 의존성 매니페스트는 `requirements.txt`(`pyarrow`·`PyYAML`)와 `requirements-dev.txt`(`jsonschema`·`referencing`) 2종이며, **버전은 CI와 같은 3.12에서 해석해 고정했다.**
  - SRS NFR-004의 `>= 3.10` 선언에 **코드를 맞췄다** (이슈 `#62`, 결정 B). `datetime.fromisoformat()`의 `Z` 접미사가 3.11부터 지원되므로(bpo-35829) `src/measurement/timeparse.py`가 파싱 전에 `Z` → `+00:00`으로 정규화한다. **`datetime.fromisoformat`을 직접 부르지 않는다** — `tests/test_timeparse.py`가 AST로 강제하고, `python-compat.yml`이 3.10에서 실제로 돌려 확인한다.
  - ★ **지원 런타임은 둘로 선언한다** (이슈 `#207`) — **전체 파이프라인 3.12** · **측정 계층 하한 3.10**. 고정 의존성 numpy 2.5.4 · scipy 1.18.1 · shap 0.54.1 이 `Requires-Python >=3.12` 라 3.10·3.11 에서는 `pip install -r requirements.txt` 가 실패한다. NFR-04 `>= 3.10` 은 3.12 로 충족한다. 선언은 `requirements.txt` 머리 두 줄이고 `tests/test_runtime_declaration.py` 가 Dockerfile · CI · 설치된 메타데이터와 대조한다. 근거: `docs/decisions/DR-207-python-runtime.md`.
- `src/measurement/`는 구현 완료(M-01~M-09). `src/simulator/`·`decision/`·`diagnostics/`·`orchestration/`은 **여전히 지침 파일만 있고 `.py` 가 0개다.** 그것이 C2 가 채울 자리다.
  - 여기에도 **모듈 개수를 적지 않는다.** 이전 판은 `모듈 10개` 라고 적었고 `timeparse.py`·`coverage.py` 가 들어오며 낡았다 — 테스트 건수와 같은 종류의 낡음이다 (`#59`). `ls src/measurement/*.py` 가 답한다.
- **C2 에서 추가된 것** (이슈 `#63`·`#97`·`#99`·`#101`·`#100`·`#106`·`#108`·`#110`·`#116`·`#117`):
  - `src/measurement/coverage.py` — 필드 충족 집계의 **유일한 규칙.** `sink` 는 쓰면서 세고 `publish` 는 읽으며 센다. 규칙이 두 벌이면 둘 다 따로 보기에는 맞아 보이면서 어긋난다.
  - **계보** — `data/raw/runs/run-<id>.json` 이 실행 1건씩을 불변으로 남기고 `parent_run_id` 로 사슬을 이룬다. `sink.verify_lineage()` 가 그 주장을 디스크의 파티션과 대조하며, `runs/` 가 없으면 `not_run` 이다(**통과가 아니다**). 게시물 `provenance.lineage` 로 실려 나간다.
  - **매출 기준은 순매출이다.** 계약이 `order_amount` 를 할인 후 상품 합계(배송비 제외)로 정의하므로 `contribution_profit` 에서 쿠폰 할인을 **다시 빼지 않는다.** 쿠폰은 `marketing_cost`(ROI 분모)에 남는다. 근거: `docs/decisions/DR-101-revenue-basis.md`.
    - ★ 이 전제는 **커머스 코드가 실제로 지켜야 성립한다.** DR-101 은 처음에 확인 없이 "커머스가 이미 할인 후를 내보낸다"고 적었고 사실이 아니었다(`#106`). 지금은 커머스가 고쳤고 `DQ-09` ③이 이벤트와 교환 파일의 금액을 매번 대조한다.
  - **교환 파일** (`#100` · `#117`) — 주문·품목·고객·카탈로그 묶음. 커머스는 `data/commerce/`(`npm run exchange:export`), 시뮬레이터는 `data/simulator_exchange/` 에 **같은 계약**으로 낸다. `publish` 가 출처마다 자기 묶음을 읽어 **그 출처의 이벤트에만** 붙이고, 품목·주문 시점 원가·할인·배송비로 `cogs`·`contribution_profit` 을 계산하고 `DQ-02`·`03`·`05`·`09` 를 돌린다. 묶음이 없으면 `NO_COST_BASIS`·`not_run` 이다. 계약: `docs/contracts/commerce-exchange/v1/`(시뮬레이터 규칙 §11), 로더: `src/measurement/exchange.py`, 근거: `docs/decisions/DR-117-simulator-exchange.md`.
  - **쿠폰 비용(ROI 분모)은 주문마다 실제 할인액을 먼저 쓴다** (`#108`). 교환 파일 `discount` → 없으면 처치 단가 유도(D-16) → 둘 다 없는데 쿠폰을 썼으면 **계산 불가**(0 원이 아니다). 커머스 운영 쿠폰도 마케팅 비용이다. 근거: `docs/decisions/DR-108-coupon-cost-basis.md`.
  - **명부 대조** (`#110`) — 교환 파일이 있으면 `DQ-02`·`DQ-03`·`DQ-05` 가 실행된다. 대조 대상은 **커머스 출처 이벤트만**(명부가 커머스 것이다)이고, 명부 생성 시각 이후 이벤트는 대조하지 않고 건수를 남긴다. 근거: `docs/decisions/DR-110-roster-checks.md`.
  - `treatment_cost.*.occurs_at` 은 **`EventType` 어휘**다. 로딩 시 실재 여부를 거부하고, `tests/test_treatment_accrual.py` 가 `economics.py` 의 실제 계상 근거와 대조한다.
- `dashboard/`(Next.js, `:3001`)에 **라우트 8종**이 구현됨(d-01·d-02) — 게시물 연동 6(`V1`~`V6`) + 정적 1(`/triggers`, C1 작동 0종) + 개요 1(`/`). `results/`의 게시물을 **읽기만** 한다(`DB-012`·`DB-013`·`DB-014`).
- GATE 1은 **부분 봉인(`PARTIAL_FREEZE`)** 상태다. 완전 봉인(`LOCKED`)은 **0종**.
- CI는 **4종**이다 — `isolation.yml`(의존성 없이, 3.12) · `tests-with-deps.yml`(의존성 설치 후, 3.12) · `python-compat.yml`(**3.10**, 의존성 없이 — SRS 가 선언한 최소 버전을 실제로 도는 유일한 잡. **측정 계층과 의존성 없는 스위트만 보증한다**) · `dashboard.yml`(경로 격리 · 상태 매핑).
  - ★ **`tokens:test`는 CI에 없다.** `scripts/tokens/verify.mjs`가 `Plan/DESIGN.md`를 읽는데 `Plan`은 private 서브모듈이라 CI가 체크아웃하지 않는다. **사람이 돌려야 하는 검사다** — 대시보드 검증 3종 중 2종만 자동이다.
  - 대시보드 **빌드**는 Plan 없이 된다 (`#207`). `dashboard/src/styles/tokens.generated.css` 를 **커밋**하고("생성물을 커밋하지 않는다"의 문서화된 예외), `predev`·`prebuild` 는 Plan 이 있을 때만 `tokens:check` 로 대조한다 — 없으면 `tokens:check 미실행` 을 출력한다. 커밋본 ↔ 정본 대조도 `tokens:test` 처럼 **CI 에 없다.** 근거: `docs/decisions/DR-207-plan-free-tokens.md`.
- **결정 기록 제도가 있다** — `docs/DECISION_RECORDS.md`. 이슈는 태스크 목록이 아니라 *무엇을 정하고·무엇을 조사하고·무엇을 증거로 남길지*의 안내서이며, **체크박스를 다 채워도 결정 기록이 없으면 그 태스크는 끝난 것이 아니다.** 강제는 `tests/test_decision_records.py`.
- 저장소 전체 검증은 `python3 -m unittest discover -s tests` 이며 lint·build·타입 검사는 여전히 미정의.
  - 여기에 **건수를 적지 않는다.** 이전 판은 `407건` 이라고 적었고 테스트를 추가한 바로 다음 커밋에 낡았다 — 아무도 대조하지 않는 숫자를 문서에 두는 것이 이슈 `#59` 가 닫은 결함의 모양이다. 건수는 명령을 실행하면 나온다.
- 저장소 보안 설정 (이슈 `#66` · 보안 F4, 2026-09-14):
  - **Dependabot alerts — 활성화됨.** `gh api -X PUT repos/…/vulnerability-alerts`. 되돌리려면 같은 경로에 `DELETE`.
  - **Secret scanning — 꺼져 있다(켤 수 있게 됨).** 2026-09-14 에는 private 저장소의 플랜 제한(`HTTP 422 Secret scanning is not available for this repository`)으로 `BLOCKED` 였다. 2026-11-14 public 전환 뒤 `security_and_analysis.secret_scanning` · `secret_scanning_push_protection` 이 `disabled` 인 것을 확인했다 — 켜는 것은 리드 승인 뒤. **켜지 않은 것을 켠 것으로 적지 않는다.** 전환 전 비밀값 패턴 점검(시스템 팀이 읽을 수 있는 경로 · 모든 브랜치의 커밋 기록)은 0건이었고, 시뮬레이터 팀 경로는 그 팀이 본다. 그때까지 커밋된 비밀값 감시는 **사람이 본다**.
  - CI 서드파티 액션은 커밋 SHA 로 고정돼 있다. 갱신 시 `uses:` 옆 주석의 태그를 함께 고친다.
- ★ **로컬 검증은 의존성 두 벌을 다 설치하고 돌린다.**
  ```bash
  pip install -r requirements.txt -r requirements-dev.txt
  ```
  `requirements-dev.txt`(`jsonschema`·`referencing`)를 빠뜨리면 **계약 스키마 검증이 전부 skip 되고 `OK` 로 보인다.** 실제로 그렇게 게시 계약 위반을 놓쳤고 CI 가 잡았다 (`#99`). **`skip` 은 통과가 아니다** — 끝줄의 `OK` 만 보지 말고 `skipped=` 수를 함께 본다.
- **존재하지 않는 명령을 문서·게이트·PR 본문에 쓰지 않는다.** 검증을 실행할 수 없으면 `BLOCKED`로 보고한다.
