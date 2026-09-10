# Task Graph — AI_ROI · 사이클 C1 (BATHOS 7-Wave)

**레벨** **Lv3 확정** (2026-09-10, `user_verdict=approve`, `decision_id=ld-558a7916…`)
**개정 1** — `/route` stakes 응답 반영. C1 = 커머스 갭 이슈 정리 + 측정 계층 완주 + GA형 대시보드
**정본** `Plan/AI_Retention_ROI_PRD_v2.md` v2.3 · `AI_ROI/AGENTS.md` · `AI_ROI/src/AGENTS.md` · `charter.md`

---

## 0. 상위 제약 (웨이브 순서보다 위)

1. **파트 격리** — `src/AGENTS.md`. C1은 `measurement`만 만지지만, **창구는 누구의 편도 들지 않는다**는 원칙은 그대로다.
2. **git·이슈 권한 L1** — 이슈 생성·수정, 커밋·PR은 **사용자 명시 지시 후에만**. 그 전까지는 파일 초안만.
3. **`Ecommerce_Service` 코드 편집 0건** — 읽기 전용 분석만. 편집 필요 시 멈추고 보고.

---

## 1. Lv3 웨이브 편성 — 엔진 기본값 대비 조정분

엔진 `route decide`는 Lv3 기본 편성(`W0~W6`, 18 role slot)을 반환했다.
C1 실범위에 맞춰 **아래 3건을 뺀다.** manifest에는 기본 편성이 기록되어 있으므로 이 표가 실제 운용 기준이다.

| 항목 | 엔진 기본 | C1 운용 | 근거 |
|---|---|---|---|
| **W0 Analysis** (Caleb) | 포함 | **생략** | 컨셉이 PRD v2.3 확정 · 사용자 승인 |
| **W4 IP·연구** (Mark·Nathanael) | Optional | **off** | `regulation_ip=false` |
| **Stephen (ML)** | 포함 | **미가동** | C1에 decision layer 없음 |

| W | 이름 | 담당 | 게이트 | C1 |
|---|---|---|---|---|
| W1 | Discovery | John + Caleb | USP Readiness | **필수** |
| W2 | Design | Joshua → James ∥ Jonnathan | Plan Readiness | **필수 · A8 차단조건** |
| W3 | Story Gate | Matthew (+Thomas·Matthias) | PASS/CONCERNS/FAIL | **필수** |
| W5 | Implementation | Phillip ∥ Andrew | — | **필수** (Stephen 미가동) |
| W6 | Verify & Report | Thomas+Timothy+Matthias → Michael → Hananiah → Martin | Release Readiness | **필수** |

---

## 2. 의존성 그래프

```text
                        [킥오프 · /route Lv3 확정]
                                    │
        ┌───────────────────────────┴───────────────────────────┐
        │ W1 Discovery                                          │
        │   John ── AI_ROI 측정계층 실측 + Ecommerce 갭 대조      │
        │   Caleb ── GA/제품분석 도구 지형 + KPI 표준            │
        └───────────────────────────┬───────────────────────────┘
                                    │ GATE: USP Readiness
                                    ▼
                        Joshua (기획 · W2 게이트 소유)
                    ★ A8 판정 — 대시보드가 몇 개인가
                                    │
                  ┌─────────────────┴─────────────────┐
                  │ James(아키텍처)  ∥  Jonnathan(디자인) │
                  └─────────────────┬─────────────────┘
                                    │ GATE: Plan Readiness
                                    │  (A8 미해결 시 통과 불가)
                                    ▼
                          W3  Matthew (스토리 응축)
                           Thomas ∥ Matthias 독립 리뷰
                                    │ GATE: PASS / CONCERNS / FAIL
                                    ▼
        ┌───────────────────────────┴───────────────────────────┐
        │ W5 Implementation                                      │
        │                                                        │
        │  W5-A  Phillip ── src/measurement/ (M-4·M-5·M-6)       │
        │            │       config/economic_config.yaml         │
        │            │       의존성 매니페스트                     │
        │            ▼                                           │
        │        [지표 계약 확정] ──────┐                          │
        │            │                 │                         │
        │  W5-B  Phillip ── M-3·M-7    │  W5-C  Andrew ── 대시보드 │
        │        (문서·Freeze 절차)      │        (지표 계약 소비)    │
        └───────────────────────────┬───────────────────────────┘
                                    ▼
        ┌───────────────────────────┴───────────────────────────┐
        │ W6  Thomas(리뷰) ∥ Timothy(문서) ∥ Matthias(QA)         │
        │         → Michael(보안) → Hananiah(리팩토링)            │
        │         → Martin(리포트)                                │
        └───────────────────────────┬───────────────────────────┘
                                    │ GATE: Release Readiness
                                    ▼
                              /team-confirm
```

**핵심 의존:** `W5-A의 지표 계약`이 Andrew의 전제다. 계약이 흔들리면 대시보드를 두 번 만든다.
그래서 W2 T2.7(지표 계약 확정)이 Plan Readiness의 통과 조건에 들어간다.

---

## 3. 웨이브별 태스크

### W1 — Discovery *(필수)*

**John (리버스)** → `01-reverse/`
- T1.1 `src/measurement/` 실측 — `schema.py`·`sink.py`가 실제로 무엇을 보장하는지 (event_type 16종, Nullable 매트릭스, 파티셔닝, source 분류, reject 로깅)
- T1.2 `tests/` 46건이 강제하는 것 — 특히 `test_isolation.py`의 import 경계·데이터 경로 검사
- T1.3 `docs/event_schema.md` · `docs/data_spec.html`과 `schema.py`의 **정합성 대조**
- T1.4 **이슈 `#42`~`#49` 대비 코드 실측 대조** — M-1·M-2가 이슈 요구를 실제로 충족했는가 (`#43`·`#44`가 OPEN인 이유 규명)
- T1.5 `AGENTS.md` "프로젝트 현황" 실측 어긋남 보고 (charter CONCERNS 1) — **보고만**, 수정은 W6
- **T1.6 `Ecommerce_Service` 읽기 전용 갭 분석** *(코드 편집 절대 금지)*
  - `COM-001~005` · `DATA-001·003` 대비 현재 상태 대조 — 이슈 `#24`의 대조표를 **재검증**(작성 후 변경 있었는지)
  - 기존 이슈 `#24`~`#30`이 갭을 빠짐없이 덮는지 → **누락분 목록**
  - **제거 대상 식별** — 기준 환경에 있으면 안 되는 UI/필드(A·B 테스트성 화면 등). 현재 어느 이슈에도 없는 축이다
  - 산출: `01-reverse/ecommerce-gap.md` + 신규 이슈 **초안**(발행 아님)
- **T1.7 타 개발자 작업 충돌 점검** (가정 A10) — 이슈 담당·최근 브랜치·열린 PR 확인. 겹치면 즉시 보고

**Caleb (시장분석)** → `02-market-analysis/`
- T1.8 GA4·Amplitude·Mixpanel·PostHog의 **이벤트 스키마 설계 관례** — 우리 16종 event_type이 업계 관례 대비 과부족한지
- T1.9 제품분석 대시보드가 **데이터 품질·결손을 어떻게 표시하는지** — "조용히 0" 안티패턴 회피 사례
- T1.10 리텐션 KPI 표준 정의(Primary/Guardrail/Secondary) 교차검증 → M-4 입력

**게이트 — USP Readiness 통과 조건**
- T1.3(스키마 정합성) 답변 완료
- T1.6 갭 대조표 + **제거 대상 목록** 산출
- T1.7 충돌 여부 판정

### W2 — Design *(필수)*

**Joshua (기획 · 게이트 소유)** → `03-service-planning/`
- **T2.1 ★ 가정 A8 판정 — 대시보드는 몇 개인가**
  "GA형 로그/지표 추적 대시보드"(사용자 요청)와 PRD §69.1 "AI ROI 결과 대시보드(:3001)"가 같은 것인가 별개인가.
  **이것이 풀리기 전에는 Andrew를 스폰하지 않는다.**
- T2.2 C1 완료 조건을 이슈 단위로 매핑 — `#45`·`#46`·`#47`·`#48`·`#49` 각각의 Done 정의
- T2.3 **KPI 정의 v1** 확정 (M-4 입력, PRD §66) — Primary / Guardrail / Secondary
- T2.4 **경제 규칙 v1** 확정 (M-5 입력, CFG-004) — 마진·Treatment 비용·기여이익식
  ※ `unit_cost`가 커머스에 없다(이슈 #24). **커머스 미해소 상태에서 경제 규칙을 어떻게 정의할지** 결정 필요
- T2.5 Ecommerce 신규 이슈 초안 검토 → 사용자 발행 승인 요청 패키지 구성

**James (아키텍처)** → `04-architecture/`
- T2.6 KPI·경제 규칙 모듈의 `measurement` 내 배치 — **창구 중립성**을 깨지 않는 구조
- **T2.7 ★ 지표 계약 확정** — 대시보드가 읽을 산출물의 형식·경로·갱신 방식. Andrew의 전제
- T2.8 데이터 품질 검증(M-6) 설계 — 유일성·정합성·완전성·재현성 (data_spec §9)
- T2.9 **의존성 매니페스트 도입 설계** — 격리 CI(표준 라이브러리 전제)가 깨지지 않는 방법 (가정 A7)
- T2.10 대시보드 스택·포트 결정 (3000은 커머스 점유) — A8 판정 결과에 종속
- T2.11 M-7 GATE 1 Freeze 절차 설계 — 무엇을 어떻게 Lock하고, 깨졌을 때 어떻게 감지하는가

**Jonnathan (디자인)** → `07-design/`
- T2.12 대시보드 정보구조 — 1차 독자는 **이 팀**. 첫 화면이 "이벤트가 제대로 쌓이고 있는가"에 답해야 한다
- T2.13 **결손·계산 불가 상태의 시각 표현** — 0과 명확히 구별되어야 한다 (PRD §10.1 · 절대 제약 6)
- T2.14 커머스 이벤트 / 시뮬레이터 이벤트 **출처 구분** 표현
- T2.15 `Ecommerce_Service` design token 파이프라인 **read-only 조사** — 재사용 가능 여부 (PRD L2240). **편집 금지**

**게이트 — Plan Readiness 통과 조건**
- **T2.1 (A8) 판정 완료** ← 차단 조건
- T2.3 · T2.4 확정 (봉인 대상)
- T2.7 지표 계약 확정
- T2.9 의존성·CI 방법 확정

### W3 — Story Engineering & Readiness Gate *(필수)*

**Matthew** → `03-story-engineering/`
- T3.1 Phillip·Andrew용 **자족 스토리파일** — 각 파일만 읽고도 구현 가능
- T3.2 스토리파일에 제약 개별 명시 — `Ecommerce_Service` 편집 금지, 결손 0 채우기 금지, 이슈 발행 L1 권한
- T3.3 M-3~M-7 이슈와 스토리의 1:1 대응 · GATE 1 Freeze 트리거 지점
- **Thomas · Matthias 독립 리뷰** → PASS / CONCERNS / FAIL

**FAIL 조건:** 스토리가 PRD 섹션 참조로 때움 / A8 미해결 상태로 대시보드 스토리 작성 / 지표 계약 미확정

### W5 — Implementation *(필수 · Stephen 미가동)*

**W5-A · Phillip (backend)** — 측정 계층
- T5.1 `M-4` KPI·지표 정의 모듈 (`#46`)
- T5.2 `M-5` 경제 규칙 모듈 + `config/economic_config.yaml` (`#47`)
- T5.3 `M-6` 데이터 품질 검증 모듈 (`#48`)
- T5.4 의존성 매니페스트 도입 + 격리 CI 유지 확인
- T5.5 각 모듈 테스트 — 기준선 46건에서 **회귀 0**

**W5-B · Phillip (문서·절차)** — T5.1~T5.3 이후
- T5.6 `M-3` 서비스 UI ↔ 시뮬레이터 공통 기록 계약 문서화 (`#45`)
- T5.7 `M-7` GATE 1 Freeze 체크리스트 · Lock 절차 (`#49`)

**W5-C · Andrew (frontend)** — **T2.7 지표 계약 확정 후에만 착수**
- T5.8 GA형 로그/지표 추적 대시보드 — 수집 현황·KPI·데이터 품질
- T5.9 출처 구분(커머스 / 시뮬레이터) 표시
- T5.10 **계산 불가 지표를 '계산 불가'로 표시** — 0으로 채우지 않는다

### W6 — Verify & Report *(필수)*

1. **Thomas** → `10-review/` — 코드 리뷰. **창구 중립성 위반**과 **결손 은폐(0 채우기)** 를 최우선 탐색
2. **Matthias** → `11-qa/` — C1 완료 조건 §3.1 ①~④를 **실행 증거**로 검증. 미실행은 `BLOCKED`
3. **Timothy** → `09-docs/` — README, `docs/GIT_WORKFLOW.md` 생성(BOOTSTRAP 절차), **`AGENTS.md` 현황 문단 갱신**(T1.5 후속)
4. **Michael** — 비밀값·생성물 커밋 여부, `data/` 유출 경로
5. **Hananiah** — 리팩토링 (외부 행동 보존)
6. **Martin** → `12-report/` — 최종 리포트 + **다음 사이클(시뮬레이터) 인계 사항**

**게이트 — Release Readiness:** §3.1 ①~④ 전 항목이 실행 증거와 함께 체크. 장기 DoD 미착수는 **FAIL이 아니다**(범위 밖).

---

## 4. 파일 소유 경계 — W5 (겹침 0)

| 담당 | 배타적 소유 (쓰기) | 읽기 허용 | 절대 금지 |
|---|---|---|---|
| **Phillip** | `src/measurement/**`<br>`config/economic_config.yaml`<br>`requirements*.txt`<br>`tests/test_schema.py` · `tests/test_sink.py` · `tests/test_kpi_*.py` · `tests/test_quality_*.py`<br>`docs/measurement_contract.md`(M-3)<br>`docs/gate1_checklist.md`(M-7) | `data/raw/` `data/processed/`<br>`docs/event_schema.md` `docs/data_spec.html`<br>`Ecommerce_Service/**` (read-only) | `src/simulator/**` `src/decision/**`<br>`src/diagnostics/**` `src/orchestration/**`<br>대시보드 경로<br>`Ecommerce_Service` **편집** |
| **Andrew** | 대시보드 경로 전체 (W2 T2.10에서 확정) | 지표 산출물(T2.7 계약)<br>`data/processed/**`<br>`src/measurement/` (계약 확인) | `src/**` **편집**<br>`data/hidden/**` `data/ground_truth/**`<br>`Ecommerce_Service` **편집** |
| **Stephen** | — | — | **C1 미가동** |

**겹침 검증:** `src/measurement` + `config` + `requirements` + `tests/test_{schema,sink,kpi,quality}*` (Phillip) / 대시보드 경로 (Andrew) — **교집합 없음.**
`src/simulator` · `decision` · `diagnostics` · `orchestration`은 **C1에서 아무도 소유하지 않는다.**

### 봉인 파일 — C1 전원 수정 금지

| 파일 | 이유 | 수정 권한 |
|---|---|---|
| `tests/test_isolation.py` | 격리 규칙 헌법 | W6 Matthias만, 사용자 승인 후 |
| `.github/workflows/isolation.yml` | 위 검사의 CI 강제 | W6 Matthias만, 사용자 승인 후 |
| `src/simulator/**` · `src/decision/**` · `src/diagnostics/**` · `src/orchestration/**` | C1 범위 밖 | 아무도 안 됨 |
| `Plan/**` | 서브모듈 · 기획 정본 | 아무도 안 됨 |
| `AGENTS.md` · `*/AGENTS.md` · `*/CLAUDE.md` — **기존 파일** | 에이전트 지침 정본 | W6 Timothy만 |
| **신규 디렉터리의 `AGENTS.md`·`CLAUDE.md`** | **봉인 아님** — 아래 리드 판정 D-6 참조 | **그 디렉터리를 만드는 담당자** |
| **`../Ecommerce_Service/**`** | **별도 저장소 · 사용자 명시 제외** | **아무도 안 됨** (read-only만) |

### 리드 판정 D-6 (Paul · 2026-09-11) — 신규 디렉터리의 지침 파일은 봉인 대상이 아니다

**문제:** SRS ISO-004(`SRS:1794`)가 *"`dashboard/`에도 `AGENTS.md`와 `CLAUDE.md`를 둔다"* 를 요구한다.
그런데 위 봉인 표가 `*/AGENTS.md`를 **W6 Timothy 단독**으로 못박아, Andrew가 W5-C에서 `dashboard/`를 만드는 순간부터 W6까지 **지침 없는 디렉터리가 존재하는 구간**이 생긴다.
격리 제약(DB-014)을 지켜야 하는 코드가 정작 그 제약을 적어둔 파일 없이 쓰이는 셈이다.

**판정:** 봉인 규칙의 목적은 **이미 존재하는 지침 정본이 작업 중에 조용히 바뀌는 것**을 막는 데 있다.
**아직 없는 디렉터리의 지침 파일을 처음 만드는 일은 그 목적과 무관하며, 디렉터리를 만드는 행위의 일부다.**

- `dashboard/AGENTS.md`·`dashboard/CLAUDE.md`의 **최초 작성은 Andrew(W5-C)의 소유**다. 디렉터리 생성과 **같은 작업 단위**로 처리한다.
- 내용은 **DB-014 격리 제약을 반드시 포함**한다 — `results/`·`data/processed/`만 읽고 `data/hidden/`·`data/ground_truth/`·`src/simulator/`에 접근하지 않는다.
- W6 Timothy는 이 파일을 **검토·정제**한다. 최초 작성을 W6까지 미루지 않는다.
- 기존 `AGENTS.md`·`src/*/AGENTS.md`는 **여전히 봉인**이다. 이 판정은 신규 디렉터리에만 적용된다.

### 공유 경로

| 경로 | 규칙 |
|---|---|
| `README.md` | W5 중 누구도 쓰지 않는다. W6 Timothy 단독 |
| `docs/GIT_WORKFLOW.md` | 없음. W6 Timothy가 BOOTSTRAP 절차로 생성 |
| `tests/` | 파일 접두어로 소유가 갈린다. 남의 접두어 파일 수정 금지 |
| GitHub 이슈 | **L1 — 사용자 명시 지시 후에만.** 그 전엔 `.agent-team/` 안에 초안만 |

---

## 5. 미해결 (다음 웨이브로 넘김)

| # | 항목 | 넘길 곳 | 차단 |
|---|---|---|---|
| **Q1** | **A8 — GA형 대시보드가 PRD §69.1 대시보드와 같은가 별개인가** | **W2 Joshua T2.1** | **Andrew 스폰 차단** |
| Q2 | 커머스에 `unit_cost`가 없는데 경제 규칙(M-5)을 어떻게 정의하나 | W2 Joshua T2.4 | M-5 착수 |
| Q3 | ML 의존성 도입 후 격리 CI 유지 방법 (A7) | W2 James T2.9 | T5.4 |
| Q4 | 이슈 `#43`·`#44`가 머지 후에도 OPEN — 닫을지 여부 | **사용자** (Issue close는 개별 승인) | — |
| Q5 | Ecommerce 신규 이슈 발행 승인 | **사용자** (L1) | T1.6 후속 |
| Q6 | `.agent-team/`을 git에 커밋할지 `.gitignore`에 넣을지 | **사용자** | — |
| Q7 | 타 개발자와의 작업 충돌 (A10) | W1 John T1.7 | W5 착수 |

**CONCERNS:**
1. ~~manifest에 C1 운용 편성을 담을 필드가 없다~~ → **해소** (2026-09-10, W1 착수 시). `wave init --wave-set "W1,W2,W3,W5,W6"` 로 W0·W4를 `skipped`로 기록했다. 다만 `routing[].role_set`은 여전히 Lv3 기본 18 slot이므로 **Stephen 미가동은 이 문서 §1 표가 정본**이다.
2. Phillip이 W5-A와 W5-B를 연속 수행하므로 **W5는 실질 2인**(Phillip·Andrew)이고, Andrew는 T2.7 계약에 묶여 앞부분이 대기다. 동시 3인 병렬은 C1에서 발생하지 않는다.
3. C1은 측정 계층만 만지므로 격리 위반 **가능성 자체는 낮다.** 다만 창구 중립성(measurement가 아무에게도 의존하지 않음)은 KPI·경제 규칙을 넣으면서 깨지기 쉽다 — W6 Thomas의 최우선 점검 항목.
