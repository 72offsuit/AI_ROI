# Wave Log — AI_ROI

## 2026-09-10 · 킥오프 (리드 Paul 단독)

킥오프 완료 — BATHOS 7웨이브 파이프라인 초기화. 다음: `/route` 로 Scale-Adaptive 레벨 확정.

### 생성물

| 경로 | 내용 |
|---|---|
| `.agent-team/00-plan/charter.md` | 컨셉·목표·성공기준(DoD)·범위·비범위·제약·타깃·가정 A1~A7 |
| `.agent-team/00-plan/task-graph.md` | W0~W6 분해 · 의존성 · W5 파일 소유 경계(겹침 0) |
| `.agent-team/_state/manifest.json` | `bathos state init --codename AI_ROI` 시딩 → `state validate` VALID |

### 확정 사항

- **대상 경로: `AI_ROI` 단독.** 워크스페이스 루트가 아니다.
  근거 — PRD §10.1 "두 저장소는 런타임 의존이 없고 공유하는 것은 스키마뿐이다",
  AGENTS.md "런타임 의존은 없다. 이 저장소는 단독으로 실행된다",
  PRD §69.1 대시보드가 AI_ROI 내부 `dashboard/`(:3001)에 있음.
  E2E가 이 저장소 안에서 닫힌다.
- **`Ecommerce_Service`는 비범위 + read-only 참조 허용.** 편집이 필요해지면 멈추고 사용자에게 보고, 별도 킥오프.
- **charter 기준: PRD v2.3** (사용자 지정).
- **레벨 0은 잠정값.** `/route` 확정 전 웨이브 실행 금지.

### 킥오프 시점 실측 (2026-09-10)

- `src/measurement/` 구현 완료 (`schema.py`·`sink.py`, PR #50 M-1 · #51 M-2)
- `src/simulator/` · `decision/` · `diagnostics/` · `orchestration/` — 지침 파일만, 구현 코드 없음
- `python3 -m unittest discover -s tests` → **46 tests OK** (Python 3.14.6)
- 의존성 매니페스트 없음 · `docker-compose.yml` 없음 · `docs/GIT_WORKFLOW.md` 없음
- 실행 가능한 검증은 unittest 하나뿐. lint·build·타입 검사 미정의

### CONCERNS

- `AGENTS.md` "프로젝트 현황(2026-09-10)"이 실측과 어긋남 — "`src/`에 구현 코드는 아직 없다"고 적혀 있으나 `measurement`는 구현되어 있고 테스트 46건이 통과한다. → W1 John 보고, W6 Timothy 수정.
- W5-A(Phillip)와 W5-B(Stephen)는 PRD GATE 1 봉인 때문에 **실질 병렬이 아니다.** `/route` 결과에 따라 W5 소요 재산정 필요.
- `.agent-team/`의 git 취급(커밋 vs `.gitignore`) 미결.

### 다음

```
/route /Users/otter/72offsuit/AI_ROI
```

---

## 2026-09-10 · /route — Scale-Adaptive 레벨 확정

### Stakes (User 응답)

| 항목 | 응답 | 엔진 매핑 |
|---|---|---|
| scope | 커머스 갭 분석→이슈 정리(코드 편집 없음) + AI_ROI GA형 로그/지표 추적 시스템·대시보드 | `module` |
| novelty | C. 완전 신규 아키텍처/기술 | `true` |
| regulation_ip | A. 없음 | `false` |
| team_size | B. 소팀 (2~5) | `medium` |

### 판정

- **인라인 매트릭스:** `novelty=C + scope≥C` → **Lv3**
- **엔진 `route decide`:** **Lv3** (`w4_mode: Optional`, `story_engineer: true`) — 일치
- **User 확정: Lv3** → `route decide --confirm 3` 기록 완료
  - `decision_id=ld-558a7916-0d1a-407a-8145-8bbd3c733f84` · `user_verdict=approve` · `state validate` VALID

### C1 운용 편성 (엔진 기본값 대비 조정)

| 항목 | 엔진 기본 | C1 운용 | 근거 |
|---|---|---|---|
| W0 Analysis | 포함 | **생략** | 컨셉 PRD v2.3 확정 · 사용자 승인 |
| W4 IP·연구 | Optional | **off** | `regulation_ip=false` |
| Stephen (ML) | 포함 | **미가동** | C1에 decision layer 없음 |

가동: **W1 · W2 · W3 · W5 · W6** / 실행 역할 13명 (Phillip·Andrew 2인 구현)
※ manifest의 `wave_set`/`role_set`은 Lv3 기본 편성. 운용 편성은 `task-graph.md` §1이 정본.

### 사이클 C1 범위 확정

1. **Ecommerce_Service** — PRD/SRS 대비 갭 분석 → 이슈 수정/신규 발행. **코드 편집 0건.**
2. **AI_ROI** — 측정 계층(범위 M, `#42`) 완주: M-3~M-7 (`#45`~`#49`)
3. **GA형 로그/지표 추적 대시보드**

### 실측 근거 (2026-09-10)

- **AI_ROI 이슈:** `#42`(범위 M) 아래 `#43`~`#49`. M-1(`#43`)·M-2(`#44`)는 PR #50·#51 머지 완료했으나 **이슈는 OPEN**
- **Ecommerce 이슈:** `#24`(COM-001~005 갭 대조표, 작성자 Inseong Kim) + `#25`~`#30` 하위 작업 존재
  - `#24` 판정: `unit_cost` 부재 → **기여이익 계산 불가 → AI ROI 산출 불가**. 이 프로젝트 North Star의 차단점
  - **누락 축:** "제거 대상"(A·B 테스트성 UI 등)이 어느 이슈에도 없음 → W1 T1.6에서 목록화

### 킥오프 산출물 개정

`/route` 결과로 charter·task-graph를 **개정 1**로 갱신 (킥오프 초안은 PRD §90 DoD 전체를 성공기준으로 잡았음).

- `charter.md` — §0 개정 요약 추가, §3 성공기준을 **C1 완료 조건 ①~④** + 장기 DoD(참조)로 분리, 가정 A8·A9·A10 신규
- `task-graph.md` — C1 편성표, W1에 Ecommerce 갭 분석(T1.6)·충돌 점검(T1.7) 추가, W5를 Phillip·Andrew 2인으로 재편, 소유 경계 재작성

### CONCERNS

- **A8 미해결 — "GA형 대시보드"가 PRD §69.1 AI ROI 대시보드(:3001)와 같은 것인지 별개인지 불명.**
  W2 Joshua T2.1의 최우선 판정 항목이며, **풀리기 전 Andrew 스폰 금지**(Plan Readiness 차단 조건).
- 커머스에 `unit_cost`가 없는 상태에서 경제 규칙(M-5)을 어떻게 정의할지 미결 → W2 T2.4
- 이슈 `#43`·`#44` close 여부는 사용자 승인 사항 (AGENTS.md: Issue close 개별 승인)
- 팀 2~5인 — 이슈 #24 작성자와 작업 충돌 가능성 → W1 T1.7 즉시 점검
- 이슈 발행·수정은 L1 권한 — 사용자가 "이슈 만들어"를 명시하기 전까지 초안만 작성

### 다음

```
/wave1-discovery /Users/otter/72offsuit/AI_ROI
```

---

## 2026-09-10 · W1 Discovery — 착수

### 모델 선택 (User Sovereignty 절차 완료)

| 역할 | runtime | model | source |
|---|---|---|---|
| john-reverse-specialist | claude | **opus** | plan (User 확정) |
| caleb-market-analyst | claude | **sonnet** | plan (User 확정) |

- `model detect` → `session_backend=claude`
- `model validate --wave W1` → **PASS** (혼합 규칙 위반 없음, 2 roles)
- 두 역할 모두 runtime=claude → 통상 스폰 (codex 위임·GLM 분기 해당 없음)

### 웨이브 상태 초기화

`wave init --wave-set "W1,W2,W3,W5,W6"` → W0·W4 **skipped**, 나머지 pending
`wave activate W1` → **W1 Active**

```
W0 skipped · W1 active · W2 pending · W3 pending · W4 skipped · W5 pending · W6 pending
```

→ task-graph CONCERNS 1(“엔진 스키마에 C1 편성을 담을 필드가 없다”) **해소.**
   단 `routing[].role_set`은 Lv3 기본 18 slot이라 Stephen 미가동은 task-graph §1 표가 정본.

### 스폰 (2명 동시)

**John** (opus) — 입력 `charter.md` · 출력 `01-reverse/**`
- T1.1 measurement 실측 / T1.2 tests 46건 / T1.3 문서↔코드 정합성
- T1.4 이슈 #42~#49 대비 코드 대조 (#43·#44 OPEN 사유 규명)
- T1.5 AGENTS.md 현황 어긋남 **보고만**
- **T1.6 Ecommerce 읽기 전용 갭 분석** — 대조표 재검증 · 기존 이슈 커버리지 · **제거 대상 식별** · 이슈 초안
- T1.7 타 개발자 작업 충돌 점검

**Caleb** (sonnet) — 입력 `charter.md` + WebSearch · 출력 `02-market-analysis/**`
- T1.8 GA4/Amplitude/Mixpanel/PostHog 이벤트 스키마 관례 ↔ 우리 event_type 과부족 판정
- T1.9 데이터 품질·결손 표시 패턴 (“조용히 0” 안티패턴 회피)
- T1.10 그로서리 Churn 정의 관례 → **M-4(#46) 직접 입력**
- T1.11 경쟁 지형 4~6개 — “Incremental Profit을 파는 제품이 존재하는가”

양쪽 모두 `ETHOS.md` 선독 지시 + 제품 코드·`Ecommerce_Service`·`Plan/` 수정 금지, 이슈 발행 금지(L1), 수치 날조 금지·미실행은 `BLOCKED` 명시.

### 상태

**진행 중** — 두 팀원 작업 대기. 완료 후 리드가 산출물 Read 검수 → USP Readiness 게이트 판정 → shutdown.

---

## 2026-09-11 · W1 Discovery — 완료 · USP Readiness 게이트 **CONCERNS**

`gate_id=gate-72118a25-5ab9-4d95-9972-7469b0db3c07` · facilitator=Paul · wave_id=W1

### 리드 검수 — 요약을 받지 않고 표본 재현했다

| 팀원 주장 | 리드 검증 방법 | 결과 |
|---|---|---|
| Caleb: `SESSION_TIMEOUT_MINUTES=30` @ `schema.py:35` | 직접 조회 | ✅ 정확히 35행 |
| Caleb: EventType 16종 | `EventType` 열거 | ✅ 16종 일치 |
| Caleb: 환불/취소 이벤트 부재 | 열거 검색 | ✅ 없음 (`return_visit`는 재방문) |
| Caleb: `at_risk` 28~41일 / `churn` 42일+ | 문서 조회 | ✅ `event_schema.md:86-87` |
| John: sink 결함 1 (파티션 덮어씀) | **재현 스크립트 실행** | ✅ 2건+3건 → **3건** (2건 소실) |
| John: sink 결함 2 (strict=False 크래시) | **재현 스크립트 실행** | ✅ `ValueError: 'NOT_A_REAL_TYPE' is not a valid EventType` |
| John: sink 결함 3 (타임존 미강제) | **재현 스크립트 실행** | ✅ UTC 검증 통과 · 파티션키 `2025-10-01` (KST 10-02) |
| John: `#29`가 R-1과 충돌 | `gh issue view 29` | ✅ 범위 제외절에 "테스트 사용자 전환 방식은 유지해도 됩니다" 문자 그대로 존재 |
| John: `data_spec` §6.1 원가율 초안 | HTML 파싱 조회 | ✅ 신선78/간편식70/유제품75/음료68/생활72 · 가중평균 74.0% · 기여마진 26.0% |
| John: SeongHwan main 커밋 18건 | `git shortlog -sne main` | ✅ 18 (전 브랜치 기준 24) |
| John: 두 저장소 변경 0건 | `git status` × 3 | ✅ AI_ROI `?? .agent-team/`만 · Ecommerce·Plan clean |
| **John: 커밋 39d1668이 이슈 발행 이후** | `git show --format=%aI` + 이슈 createdAt | ❌ **오류** — 커밋 `2026-09-10T19:14:08+09:00`(=10:14Z), 이슈 `13:47Z`. **3시간 33분 전이다.** KST와 UTC를 같은 축으로 비교한 실수 |

**정정의 방향:** 충돌 위험을 **낮추는** 쪽이다. 이슈 발행(13:47Z) 이후 커머스 코드 커밋은 **0건**이며, 유일한 이후 커밋은 사용자 본인의 Plan 포인터 갱신(`6b186d0`, 14:04Z)뿐이다.

### 판정 근거 — 왜 PASS가 아니라 CONCERNS인가

USP 방향은 명확하다(후보 3개, 그중 1개는 C1 안에서 증명 가능). 경쟁사 분석도 완료다 → **FAIL 아님.**
그러나 charter 가정 3개 중 **2개가 조건부**로 돌아왔고, 사용자 지시와 사용자 본인 이슈 사이에 **문서화된 모순**이 있으며, 재현된 결함 3건이 W5 범위를 늘린다 → **PASS로 올리면 이 리스크가 기록 없이 통과한다.**

### 가정 판정

| 가정 | 판정 | 요지 |
|---|---|---|
| A6 (스키마 계약만으로 통합 성립) | ⚠️ **조건부** | "편집 안 함"으로는 유효(런타임 의존 실제 0). "편집 없이 완성"으로는 거짓 — 커머스 이벤트 기록 0건, 계약이 값 수준 미규정 |
| A9 (기존 이슈가 갭 대부분 커버) | ✅ **성립** | `#24` 대조표 전 항목 정확·최신. 신규 이슈 대량 발행 불필요(초안 7건이면 충분). **단 제거 축은 처음부터 없었다** |
| A10 (작업 충돌 없음) | ⚠️ **조건부** | 코드 충돌 0(열린 PR 0·미완 브랜치 0·C1 편집영역에 타 작성자 없음). 의사결정 충돌 있음 — 제거 대상 R-1~R-9가 전부 SeongHwan 작업물 |

### 기록된 이슈 8건 (critical 3 / enhancement 3 / optimization 2)

1. **critical** — R-1이 사용자 지시 ↔ 이슈 `#29` 제외절과 정면 충돌. **사용자 판정 필요**
2. **critical** — EventSink 결함 3건 (리드 재현 확인). W5 범위 증가
3. **critical** — G-3 주문 경제값 미저장 + 조용한 0 채우기. `#26` 배송비 도입 시 즉시 데이터 오류. charter 절대제약 6 위반
4. enhancement — A6 조건부. `#45`(M-3)는 `AIROI-D2` 선행 필요
5. enhancement — A10 조건부
6. enhancement — 환불/취소 이벤트 부재 → M-5 입력. `return_visit` 오독 주의
7. optimization — John 시각 주장 오류 정정
8. optimization — BLOCKED 10건

### Q2(경제 규칙) 부분 해소

`docs/data_spec.html` §6.1이 카테고리별 원가율 초안을 이미 갖고 있다 → **커머스 `unit_cost` 미해소 상태에서도 `economic_config.yaml` 정의가 가능하다.**
단 그 값은 **시뮬레이터 생성분에만 유효**하고, 커머스 실측분은 계산 불가로 표시해야 한다(charter 절대제약 6).
Caleb이 업계 표준 공식(기여이익 = 순매출 − 변동비, 변동 COGS 필수)으로 `unit_cost` 없이는 공식 자체가 성립 불가함을 교차 확인했다.

### 산출물

- `01-reverse/` — `reverse-summary.md`(자족, 329줄) · `measurement-map.md` · `issue-code-audit.md` · `ecommerce-gap.md` · `collision-check.md` · `issue-drafts/`(7건 + README)
- `02-market-analysis/` — `market-report.md` · `competitive-landscape.md` · `usp-recommendations.md`
- **이슈 초안 7건은 발행하지 않았다** (L1 권한 — 사용자 명시 지시 대기)

### 팀원 shutdown

John · Caleb 모두 종료. W1 Active 유지(게이트 기록 완료).

### 다음

```
/wave2-design /Users/otter/72offsuit/AI_ROI
```

**W2 착수 전 사용자 판정이 필요한 3건:** R-1 vs `#29` 충돌 · 이슈 초안 7건 발행 여부 · `#43`/`#44` close 여부.

---

## 2026-09-11 · 사용자 판정 — R-1 (테스트 사용자 전환 UI)

### 판정

> **"테스트 사용자 전환 UI는 제거 대상 맞아, #29 수정해줘"** — 사용자

USP 게이트 CONCERNS 이슈 #1(critical, "사용자 지시 ↔ 이슈 #29 정면 충돌")이 **해소**되었다.

### 실행 — `Ecommerce_Service#29` 본문 수정 (L1 권한: 사용자 명시 지시)

| 위치 | 변경 |
|---|---|
| 범위 > 제외 | *"**테스트 사용자 전환 방식은 유지해도 됩니다**"* **삭제** → "전환 UI 제거 **작업**은 이 Issue와 분리해 다룸"으로 대체 |
| 수용 기준 | 신규 1건 — "고객 모델이 **테스트 사용자 전환 UI에 의존하지 않는다** — 전환 UI가 제거돼도 `signup_date`·라이프사이클 계산이 그대로 성립한다" |
| 본문 말미 | 「**결정 기록 (2026-09-11)**」 절 신규 — 철회 사실·근거(SRS DATA-001, PRD §12.1)·영향 위치 8곳 명시 |

- 원문 문장은 삭제하지 않고 **"철회한다"고 명시**해 이력을 남겼다 — 다른 협업자(SeongHwan)가 이전 지침을 보고 작업 중일 수 있으므로 조용한 삭제는 위험하다.
- **아직 발행되지 않은 Issue를 존재하는 것처럼 쓰지 않았다** — "별도 Issue에서 다룹니다"를 "이 Issue와 분리해 다룹니다"로 정정 후 반영.
- **커머스 저장소 코드 변경 0건** (`git status` clean). 이슈 본문만 수정.

### 초안 갱신

`01-reverse/issue-drafts/ECOM-E7-removal-targets.md` — "⚠ 발행 전 해소 필요" 헤더를 "✅ 선행 결정 해소"로 교체, 1번 항목 차단 해제, 의존성 절 갱신. **발행 가능 상태.**

### 남은 대기 결정 2건

| | 항목 | 상태 |
|---|---|---|
| 1 | ~~R-1 vs #29 충돌~~ | ✅ **해소** |
| 2 | 이슈 초안 7건 발행 여부 | ⏳ 대기 (E7은 이제 차단 없음) |
| 3 | `#43`·`#44` close 여부 | ⏳ 대기 |

---

## 2026-09-11 · 이슈 발행 — `Ecommerce_Service#32` (E7 제거 대상)

사용자 지시 **"E7 이슈 만들어"** (L1 권한 충족) → 발행 완료.

| | |
|---|---|
| URL | https://github.com/72offsuit/Ecommerce_Service/issues/32 |
| 제목 | `refactor: 기준 환경에 남으면 안 되는 테스트성 UI·문구·식별자 정리` |
| label | `enhancement` · 상위 Issue `#24` |
| 본문 | `01-reverse/issue-drafts/ECOM-E7-removal-targets.md` 기반. 초안 전용 헤더 제거, 「선행 결정 완료」 blockquote로 대체 |

### 상호 참조 연결

`#29` 재수정 — "이 Issue와 분리해 다룹니다" → **"#32 에서 다룹니다"**, 결정 기록 절도 "#32 가 담당합니다"로 갱신. **더 이상 dangling 참조 없음.**

### 발행 내용 요약 (제거·교체 대상 6종 + 판단 유보 2건)

1. **테스트 사용자 전환 UI 전체** — `UserMenu.tsx`(87줄)·`StoreShell.tsx:30-35`·`seed-data.ts:97-99`·`selection.ts:5`·`CheckoutPage.tsx:106`·`OrderComplete.tsx:13-14`·`layout.tsx:15` + 테스트 6곳 **(결정 완료)**
2. **"배송비 0원/무료배송" 고정 문구 7곳** — `#26`이 코드 상수만 다루고 UI 문구는 수용 기준에 없어 생기는 구멍
3. **"샘플 추천" 배지** — `ShopHome.tsx:28`
4. **`dummyjson-` 상품 ID 접두사** — AI_ROI `^P\d{4}$`(`schema.py:314`) 위반. `#30`은 `source_*` 필드만 다룸
5. "모의 주문/구매 테스트" 문구 9곳 — 푸터 1곳만 남기는 안 제시
6. 하드코딩 상품 큐레이션 — `#25` 이후로 미룰 수 있음
7. 판단 유보 2건 — "오늘의 추천" · 히어로 캐러셀 자동 전환(→ **캐러셀 전환을 `page_view`로 기록하지 않는다**는 규칙이 M-3(`#45`) 계약에 필요)

### 커머스 저장소 코드 변경 0건 (`git status` clean) — 이슈만 조작

### 남은 대기 결정

| | 항목 | 상태 |
|---|---|---|
| 1 | ~~R-1 vs #29 충돌~~ | ✅ 해소 |
| 2 | 이슈 초안 발행 | ✅ **E7 발행(#32)** · 나머지 6건(`AIROI-D1`·`D2`·`ECOM-E8`~`E11`)은 대기 |
| 3 | `#43`·`#44` close 여부 | ⏳ 대기 |

---

## 2026-09-11 · 이슈 발행 — `AI_ROI#53`(D1) · `AI_ROI#54`(D2)

사용자 지시 **"D1이랑 D2도 이슈 만들어"** (L1 권한 충족) → 발행 완료.

| 이슈 | 제목 | label | 관련 |
|---|---|---|---|
| [#53](https://github.com/72offsuit/AI_ROI/issues/53) | `fix: Event Sink 결함 3건 — 파티션 덮어쓰기 · strict=False 크래시 · 타임존 미강제` | `kind/dev`·`scope/M-measurement` | `#44`(M-2) |
| [#54](https://github.com/72offsuit/AI_ROI/issues/54) | `fix: 스키마가 값 수준을 강제하지 않는다 — 식별자·category·page_type` | `kind/decision`·`scope/M-measurement` | `#43`(M-1)·`#45`(M-3)·`#49`(M-7) |

### 발행 전 리드 재현 검증

두 초안 모두 발행 전에 리드가 직접 실행으로 재확인하고, 그 사실을 이슈 본문 상단 blockquote에 명시했다.

| 주장 | 재현 결과 |
|---|---|
| D1-1 파티션 덮어쓰기 | `2건+3건 → 3건` (2건 소실) |
| D1-2 `strict=False` 크래시 | `ValueError: 'NOT_A_REAL_TYPE' is not a valid EventType` |
| D1-3 타임존 미강제 | UTC `23:30Z` 검증 통과 · `partition_key='2025-10-01'` (KST 10-02) |
| D2-1 `check_identifier` 미사용 | 프로덕션 경로 호출 0건 |
| D2-2 값 미강제 | `page_type="아무거나"` · `category="우주선"` · `customer_id="test-user-1"` → `validate_event()` 문제 0건 통과 |

### 초안 표현 정정 1건

D2-1 원문 *"어디에서도 호출되지 않는다"* → **부정확.** 호출부가 `tests/test_schema.py:159,171` 2곳 존재한다(자기 단위테스트).
발행본에서 *"호출부는 자기 단위테스트 2곳뿐 — **프로덕션 수집 경로에서는 한 번도 쓰이지 않습니다**"* 로 정밀화해 반영했다.

### `#54`가 GATE 1보다 앞서야 하는 이유 (W2 James T2.11 입력)

`#49`(M-7)가 `EVENT SCHEMA v1`을 Lock한다. **Lock 이후에는 되돌릴 수 없다.**
현재 `category` 어휘가 3자 불일치(SRS COM-001 영문 / `data_spec` §6.1 한글 / `schema.py` 열거 없음)이고 식별자 형식이 강제되지 않으므로, 이 상태로 Lock하면 계약이 값 수준을 규정하지 못한 채 고정된다.
→ **`#54` → `#45`(M-3) → `#49`(M-7) 순서가 강제된다.**

### 남은 대기 결정

| | 항목 | 상태 |
|---|---|---|
| 1 | ~~R-1 vs #29 충돌~~ | ✅ 해소 |
| 2 | 이슈 초안 발행 | ✅ **E7(#32) · D1(#53) · D2(#54) 발행** · 나머지 4건(`ECOM-E8`~`E11`) 대기 |
| 3 | `#43`·`#44` close 여부 | ⏳ 대기 |

---

## 2026-09-11 · 이슈 발행 — `Ecommerce_Service#33` (E9 주문 경제값)

사용자 지시 **"E9도 이슈 만들어"** (L1 권한 충족) → 발행 완료.

| | |
|---|---|
| URL | https://github.com/72offsuit/Ecommerce_Service/issues/33 |
| 제목 | `fix: 주문의 경제값을 저장한다 — 배송비·할인이 조용히 0으로 채워진다` |
| label | `bug` (기존 커머스 이슈 중 첫 `bug`) · 상위 Issue `#24` |

### 발행 전 리드 코드 확인

| 주장 | 확인 |
|---|---|
| `orders`가 4개 컬럼뿐 | ✅ `id`·`user_id`·`created_at`·`total_krw` (`schema.ts:49-54`) |
| 쿠폰 없으면 0으로 재구성 | ✅ `discountKrw: 0, shippingKrw: 0` (`orders.ts:58-66`) |
| 값을 받고도 버린다 | ✅ `saveOrder`가 `subtotal + shipping − discount = total` **검증까지 한 뒤**(`orders.ts:107-110`) `total_krw`만 저장 |

마지막 항목이 이 이슈의 핵심 근거다 — 정보가 없어서 못 남기는 게 아니라 **가지고 있으면서 버린다.**

### `#26`과의 순서 강제

`#26`(배송비 정책 도입)이 착수되는 순간 쿠폰 없는 모든 주문의 배송비가 **조용히 0으로 보고**된다.
→ `#33`은 **`#26`보다 먼저 또는 함께** 처리해야 한다.
GitHub 타임라인에 `#26 ← #33` cross-reference 자동 생성 확인(`#24`·`#32`·`#33` 3건).

### charter 절대제약 6 위반 사례

*"결손을 조용히 0으로 채우지 않는다"* — 커머스 측에서 이 원칙이 이미 깨져 있는 지점이다.
AI_ROI `sink.py:11-14`가 같은 이유로 `unavailable_metrics()`를 두고 있다. **두 저장소가 같은 원칙에 대해 반대 방향으로 구현되어 있다.**

### 발행 현황

| 초안 | 상태 |
|---|---|
| `ECOM-E7` 제거 대상 | ✅ `Ecommerce_Service#32` |
| `AIROI-D1` sink 결함 | ✅ `AI_ROI#53` |
| `AIROI-D2` 스키마 값 강제 | ✅ `AI_ROI#54` |
| `ECOM-E9` 주문 경제값 | ✅ `Ecommerce_Service#33` |
| `ECOM-E8` 식별자·타임존 | ⏳ 미발행 |
| `ECOM-E10` 구매이력·검색 부재 | ⏳ 미발행 |
| `ECOM-E11` Treatment T4 | ⏳ 미발행 |

**양 저장소 코드 변경 0건 유지.**

---

## 2026-09-11 · W2 Design — 1단계 착수 (Joshua)

### 모델 선택 (User Sovereignty 절차 완료)

| 역할 | runtime | model | source |
|---|---|---|---|
| joshua-service-planner | claude | **opus** | plan (User 확정) |
| james-architect | claude | **opus** | plan (User 확정) |
| jonnathan-chief-designer | claude | **opus** | plan (User 확정) |

`model validate --wave W2` → **PASS** (3 roles). 전원 runtime=claude → 통상 스폰.
사용자 판단: W2는 되돌리기가 가장 비싼 웨이브 — A8 오판은 W5 재작업, GATE 1 Lock 순서 오판은 봉인 후 복구 불가.

### 웨이브 상태

`wave activate W2` → W2 Active.
**엔진 한계 기록:** `bathos wave`에 `complete` 하위 명령이 없어 **W1이 `active`로 남는다.** W1은 게이트 판정(CONCERNS)·팀원 shutdown까지 끝났으므로 실질 완료다. `wave show`만으로는 진행 웨이브를 판별할 수 없으니 이 로그가 정본.

### 1단계 — Joshua 스폰 (단독)

입력: `charter.md` · `task-graph.md` · **W1 산출물 9종 전부** · 발행 이슈 4건(`#53`·`#54`·`#32`·`#33`) · 범위 M 이슈 8건
출력·소유: `03-service-planning/**`

태스크: **T2.1 A8 판정(최우선)** · T2.2 이슈 단위 Done 매핑 · T2.3 KPI v1 · T2.4 경제 규칙 v1 · T2.5 미발행 초안 3건 우선순위 · T2.6 GATE 1 Lock 범위

### 리드가 스폰 전 확인한 것 — `SS1~SS14`는 정의가 없다

커맨드 문구가 `service-stories.md`에 *"SS1~SS14 매핑"* 을 요구하나, **`SS1~SS14`의 정의가 저장소·BATHOS 설치본 어디에도 없다.**
검색 결과 이 토큰은 커맨드 문구 자체(`.claude/commands/wave2-design.md` 및 BATHOS 배포본 SKILL.md)에만 등장한다.
→ Joshua에게 **없는 분류 체계를 지어내지 말 것**, 프로젝트 자체 번호(SS1, SS2, …)로 정의하되 **개수를 14개에 억지로 맞추지 말 것**, 문서 서두에 외부 표준이 아님을 밝힐 것을 지시했다.

### 상태

**진행 중** — Joshua 완료 후 리드 검수 → shutdown → 2단계(James·Jonnathan 병렬) 스폰.

---

## 2026-09-11 · W2 1단계 완료 (Joshua) — 리드 검수 · 2단계 착수

### 리드 검수 — 표본 재현

| Joshua 주장 | 검증 | 결과 |
|---|---|---|
| 격리검사가 `measurement`의 `results/` 접근을 막지 않음 | `test_isolation.py:31-36` 직접 조회 | ✅ `src.measurement`는 `data/hidden`·`data/ground_truth`만 금지. `results/`는 `src.simulator`에만 금지 |
| SRS §31에 `dashboard/`가 **단수** | `SRS:1772,1781,1790,1915` | ✅ 단수. + `SRS:1794` "`dashboard/`에도 `AGENTS.md`·`CLAUDE.md`를 둔다(ISO-004)" 확인 |
| DATA-003 22컬럼에 `shipping_subsidy` 없음 | `EVENT_FIELDS` 열거 | ✅ 22개 정확, shipping·cost 관련 필드 **0개** |
| PRD §65 가드레일 | `PRD §65` 원문 | ✅ *"Revenue 증가 but Profit 감소 — 좋은 결과로 판단하지 않는다"* 실재 |
| `core-features.md`·`economic-rule-v1.md` 동일 크기(23236B) | md5 대조 | ✅ 해시 상이 — **우연**, 복사 사고 아님 |
| 변경 0건 | `git status` × 2 | ✅ AI_ROI `?? .agent-team/`만 · Ecommerce clean |

**용어 정정 1건:** Joshua가 쓴 식별자 `revenue_up_profit_down` 은 **정본에 없는 이름**이다. 정본 표현은 `data_spec` §14.1의 *"Revenue↑ · Profit↓ 패턴 발생 시 실패로 판정 — PRD §65 해석 규칙"*.
논지(EC-1)는 **정확하나** W5가 이 식별자를 grep하지 않도록 주의. 코드에 넣으려면 새로 정의하는 것임을 명시할 것.

### ⚠ D-11 정정 — stale 정보에 근거한 항목

Joshua가 *"`#29`와 `#32`가 이미 발행된 채 서로 반대 지시를 준다"* 를 **critical 결정 항목 D-11**로 올렸으나, **살아 있는 모순이 아니다.**

`#29`는 `2026-09-10T15:33:58Z`에 이미 수정됐다(W2 착수 이전). 현재 본문 실측:
- 범위 제외절 → *"…제거 작업 — **#32 에서 다룹니다**"*
- 수용 기준 신규 → *"고객 모델이 전환 UI에 **의존하지 않는다**"*
- 「결정 기록」 절 → *"이 문장을 **철회합니다**"*

*"유지해도 됩니다"* 문자열은 **철회 선언 문장 안에만** 남아 있다.

**stale 원인:** W1 산출물 `01-reverse/ecommerce-gap.md`가 **수정 전 `#29`를 스냅샷**했고, 이 문서가 라이브 이슈 대신 스냅샷을 근거로 삼았다.
**조치:** `03-service-planning/issue-priority.md` D-11 블록과 `README.md`에 리드 정정 삽입. **사용자 결정 필요 항목에서 제외** (13건 → 12건).
**W3·W5 인계 교훈:** `.agent-team/` 산출물은 **작성 시점 동결본**이다. 이슈·코드 상태를 근거로 판단할 땐 `gh issue view`·`git`으로 **라이브 확인**할 것.

### 리드 판정 D-6 — 신규 디렉터리의 지침 파일은 봉인 대상이 아니다

**충돌:** SRS ISO-004(`SRS:1794`)가 `dashboard/AGENTS.md`·`CLAUDE.md`를 요구하는데, task-graph §4 봉인표가 `*/AGENTS.md`를 W6 Timothy 단독으로 못박아 **W5-C~W6 사이에 지침 없는 `dashboard/`가 존재하는 구간**이 생긴다.

**판정:** 봉인 규칙의 목적은 **기존 지침 정본이 작업 중 조용히 바뀌는 것**을 막는 데 있다. 없던 디렉터리의 지침 파일을 **처음 만드는 일**은 그 목적과 무관하며 디렉터리 생성의 일부다.
→ `dashboard/AGENTS.md`·`CLAUDE.md` **최초 작성은 Andrew(W5-C) 소유.** 내용에 **DB-014 격리 제약 필수 포함.** W6 Timothy는 검토·정제. **기존 `AGENTS.md`·`src/*/AGENTS.md`는 여전히 봉인.**
task-graph §4에 판정 전문 삽입 완료.

### Joshua 산출물 (9종, `03-service-planning/`)

`usp.md`(A8 판정+USP 확정) · `core-features.md` · `user-stories.md`(US 18종+인수조건) · `service-stories.md`(SS1~SS12) · `kpi-definition-v1.md`(지표 47종, 가능22/조건부6/불가19) · `economic-rule-v1.md` · `gate1-lock-scope.md` · `issue-priority.md` · `README.md`

**`SS1~SS14` 처리 확인:** 지어내지 않았다. SS1~SS12로 자체 정의하고 서두에 *"외부 표준이 아니다"* 고지. 지시대로 개수를 14에 맞추지 않았다.

### A8 판정 (확정)

> **대시보드는 애플리케이션 하나.** 다른 것은 **화면군**이다.
> 관측 화면군(C1 · 산출 주체 `src/measurement/`) / 결과 화면군(이후 · 산출 주체 `src/decision/`)
> 같은 것: 스택 Next.js · 포트 `:3001` · 결과 파일 읽기 · 격리 제약 DB-014 · 경로 `dashboard/`(SRS §31 단수)

**→ Andrew 스폰 차단 해제.** 단 James T2.7(게시물 형식) 확정 후 착수.

### Joshua shutdown 완료

### 2단계 스폰 — James · Jonnathan 병렬 (동시 2명, ≤3 준수)

- **James**(opus) → `04-architecture/**` · T2.6~T2.12. 핵심: **T2.7 게시물 계약(기계가독 필수)** · T2.12 build-plan 겹침 0
- **Jonnathan**(opus) → `07-design/**` · T2.12~T2.16. 핵심: **T2.13 결손·계산 불가 시각 표현** = USP-1 증명 장면
- 협업 불변식: **UX Flow 각 단계 ↔ 게시물 계약 1:1**. SendMessage 직접 연락 지시, James가 계약 초안을 먼저 보내기로 함
- 양쪽에 "HTTP API 없음 — `api-contracts.md`는 게시물 계약으로 채울 것", "없는 REST API 지어내지 말 것" 명시

### 상태

**진행 중** — 완료 후 리드 검수 → **Plan Readiness 게이트** 판정 → 둘 다 shutdown.

---

## 2026-09-11 · W2 Design 완료 — Plan Readiness 게이트 **CONCERNS**

`gate_id=gate-31511ac8-ebe6-4a7c-94bf-fd2b675943f2` · facilitator=Paul · wave_id=W2

### 검수 4항목 — 전부 충족

| 기준 | 결과 | 검증 방법 |
|---|---|---|
| API 계약 기계가독 | ✅ JSON Schema 7종 + 픽스처 **2벌 14파일** | 리드가 표준 라이브러리 최소검증(required·type·enum) 7/7 통과 확인 |
| ERD·시퀀스·예외 정의 | ✅ | 문서 확인 |
| build-plan W5 겹침 0 | ✅ **`Phillip 42 ∩ Andrew 29 = 0`** | `tools/check_ownership.py` **리드가 직접 실행** — 178경로(추적32+미추적83+계획63+대조15) |
| UX Flow ↔ API 연결 | ✅ **합의 16 · 미해결 1** | 양쪽 대응표 상호 참조 (`ux-flow-map.md` §5.1 ↔ `api-contracts.md` §9) |

### 이번 웨이브의 성과 — 규율이 스키마가 됐다

W2 시작 시 *"결손을 0으로 채우지 않는다"* 는 **문서에 적힌 규율**이었다. 종료 시점에는:

```
status != "ok"            →  value 는 반드시 null
denominator == 0          →  status 가 "ok" 일 수 없음
status 가 ok/unconfirmed  →  basis 필수
status 가 계산 불가        →  basis 금지          ← "—는 정의상 기준을 가질 수 없다"가 구조적 사실이 됨
examined_rows == 0        →  status 가 "pass" 일 수 없음 (vacuous)
gate_result == "pass"     →  모든 검사가 pass    (vacuous 하나만 있어도 pass 불가)
offending_values 키       →  DATA-003 22컬럼만   ← 금지 필드가 담길 자리가 구조적으로 없음
```

마지막이 특히 중요하다 — **"담지 마라"는 어길 수 있지만 "담을 자리가 없다"는 어길 수 없다.**

### 리드 재현 검증 (표본)

| 주장 | 검증 | 결과 |
|---|---|---|
| Joshua: 격리검사가 measurement의 `results/` 접근 미차단 | `test_isolation.py:31-36` | ✅ |
| Joshua: SRS §31 `dashboard/` 단수 | `SRS:1772,1781,1790,1915` | ✅ (+`SRS:1794` ISO-004 확인) |
| Joshua: `shipping_subsidy` 계산 필드 없음 | `EVENT_FIELDS` 열거 | ✅ 22개 중 shipping·cost 0개 |
| Joshua: PRD §65 가드레일 | 원문 | ✅ 실재. 단 식별자 `revenue_up_profit_down`은 **정본에 없는 이름**(Joshua 작명) |
| Jonnathan: `DESIGN.md` 두 저장소 동일 | sha256 | ✅ `f4dc7ba9…` 일치 · Plan 커밋 둘 다 `c46aee5` |
| Jonnathan: `state-tokens.css` hex 0건 | grep | ✅ 전부 `var(--ds-*)` 별칭 |
| Jonnathan: V-12 공허한 통과 | 예시 파싱 | ✅ **18건 중 7건(39%)** — 개정 후 `vacuous` 7건·공허한 pass 0건 |
| James: D-16 `discount` 부재 | `event_schema.md:36` + `requirement()` | ✅ 정의식이 없는 필드 참조 · purchase의 품목 3필드 전부 NOT_APPLICABLE |
| James: 겹침 0 | `check_ownership.py` 실행 | ✅ PASS |
| James: `headline_code` 빈틈 | `index.schema.json` enum | ✅ `counts.rejected_events`는 있고 대응 코드 없음 |
| 양쪽: 변경 0건 | `git status` × 3 | ✅ |

### 리드 판정 6건

| # | 판정 |
|---|---|
| **D-6** | 신규 디렉터리의 지침 파일은 **봉인 대상이 아니다.** `dashboard/AGENTS.md`·`CLAUDE.md` 최초 작성은 **Andrew(W5-C) 소유**. 기존 `AGENTS.md`·`src/*/AGENTS.md`는 여전히 봉인. task-graph §4에 전문 |
| **J-1** | USP-1 대표 장면 = fixture + `표본 데이터` 배지 승인. **추가 조건: fixture는 손으로 쓴 JSON이 아니라 실제 측정 계층 파이프라인을 통과한 산출물이어야 한다.** 손으로 쓴 JSON은 "화면이 그 JSON을 그릴 수 있다"만 증명한다 |
| **J-2** | 사이드바 결과 화면군 8줄 **노출** — A8 판정이 구조로 보이는 이득 |
| **D-29** | `stale` 미도입 **승인** — C1에서 도달 불가한 분기를 계약에 넣으면 화면이 영원히 실행되지 않는 코드를 갖는다 |
| **D-30** | 거부 샘플 값 **22컬럼 제한 승인** — 금지가 아니라 구조로 막는 것 |
| **B-1/B-2** | 문서 파일명은 **이슈 본문 표기 채택**(`measurement_contract.md`·`gate1_checklist.md`). task-graph를 수정, 이슈는 건드리지 않음 |

### ★ D-16 GATE 1 판정 — 무게 완화

James 판정: **차단 조건이 아니다. 차단되는 것은 필드의 부재가 아니라 결정의 부재다.**

| | D-2 환불 | D-16 `discount` |
|---|---|---|
| 시뮬레이터가 생성하나 | 아니오 | **예** (`coupon_use` + T3) |
| 유도 가능 | 아니오 — 원천 없음 | **예** — `treatment_cost[T3]` |
| 유도 성격 | — | **추정이 아니라 재구성. 정확하다** |
| 남는 것 | 가정 `A-REFUND` | **규칙 하나 — Lock 대상** |

→ **`G-16` 충족 조건이 "필드를 추가한다"가 아니라 "유도 규칙을 `ECONOMIC RULE v1`에 넣는다"로 변경.**
진짜 차단은 **유도 규칙을 안 정한 채 Lock하는 것** — 다음 사이클이 임의로 정하면 Lock 이후 변경이라 `FREEZE-003` 전량 재실행.

### 협업 — 정합 라운드가 실질 수확을 냈다

James·Jonnathan이 서로 먼저 보내고 서로 못 받아 대응표가 양쪽 다 절반이었다. **리드가 개입해 1라운드를 강제**한 결과:

- **James의 `stale` 거절이 Jonnathan의 화면 문구를 바로잡았다.** `observed`는 "지금 수신 중"과 "예전에 받고 끊겼다"를 둘 다 포함하므로, 거기 붙인 `✓ 수신 중` 칩은 **2값으로 할 수 없는 건강 판정**이었다. Jonnathan: *"혼자서는 못 찾았을 것"*
- **James의 픽스처가 Jonnathan의 증명 장면을 1쌍 → 2쌍으로 늘렸다.** 두 번째 쌍(`coupon_usage_count` 0/ok ↔ `coupon_cost` 계산 불가)은 **같은 0건에서 갈리는 지점**이다. Jonnathan: *"제 V-2를 제가 덜 활용하고 있었습니다"*
- **Jonnathan의 V-12 제안이 James의 스키마 제약이 됐고**, 그 결과 화면이 판정하지 않게 되어 `DB-012`에 더 충실해졌다
- **이름 불일치 교훈:** James가 소비자(Jonnathan)가 제안한 이름 대신 자기 이름을 써서(`affected_metrics`/`state`), Jonnathan이 대체 경로 3개를 검증하는 헛수고를 했다. **계약은 생산자가 만들지만 읽는 쪽이 못 찾으면 없는 것과 같다.**

### 미해결 — W3이 받는다

| # | 항목 | 성격 |
|---|---|---|
| **B-11** | `headline_code`에 `REJECTED_EVENTS` 없음 + 8종 우선순위 미정 | **끝내 미반영.** 품질 전건 통과 + 거부 217건이면 `ALL_CLEAR`로 뜬다. 첫 화면이 한 줄로 답하는 설계라 그 한 줄이 틀리면 전부 틀림 |
| **X-5** | 수집 0건의 "중단 vs 활동 없음" | **계약으로 풀 수 없음.** heartbeat는 `event_type` 16종 확장(=EVENT SCHEMA v1 실질 변경) + 커머스 편집 필요. `notices`의 `INGESTION_GAP_UNDECIDABLE`로 사실만 전달 |
| **V-12 후속** | 없음 — **해소됨** | `vacuous` 신설로 2층 강제 |

### W5 최대 위험 — Jonnathan이 지목

**계약이 아무리 정직해도 화면의 `?? 0` 한 줄이 전부 무너뜨린다.**
`(null).toLocaleString()`이 예외를 던지므로 구현자는 **예외를 막으려고** `?? 0`을 쓴다. `value || 0` · `Number(value)` · `filter(d => d.value > 0)` 도 같은 부류.
→ `07-design/dashboard-agents-design-constraints.md` §1에 금지 패턴과 **"왜 그렇게 하고 싶어지는지"** 를 함께 기록. Andrew의 W5-C 필독.

### 산출물

- `03-service-planning/` 9종 (Joshua)
- `04-architecture/` 문서 15종 + JSON Schema 7 + 픽스처 2벌(14파일) + 검증도구 4 + **ADR 10건** (James)
- `07-design/` md 9종 + `state-tokens.css` + 아트보드 6종(목업 v3) (Jonnathan)

### 검증 한계 (통과로 적지 않음)

- `validate_examples.py`·`check_zero_fill_rejected.py`는 **스크래치패드 venv** 실행 → **저장소 검증으로 계산하지 않음.** 이관 조건은 `dependency-plan.md` §3.2
- 화면 검증 17종 + PR 체크리스트 13항목 — **`BLOCKED — 대시보드 미구현`.** 설계만 했고 실행 안 함
- 저장소에서 실행 가능한 검증은 여전히 `python3 -m unittest discover -s tests`(46 OK) 하나뿐

### 팀원 shutdown

Joshua(1단계) · James · Jonnathan(2단계) 전원 종료.

### 다음

```
/wave3-story-gate /Users/otter/72offsuit/AI_ROI
```
