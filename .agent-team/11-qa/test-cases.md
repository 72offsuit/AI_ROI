---
name: test-cases
role: Matthias (Role 15 · QA/SDET)
wave: W6 · 1단계
date: 2026-09-14
---

# 테스트 케이스 — 인수조건(AC) 대조표

`user-stories.md`(US-1~US-18)와 `story-d-01`·`story-d-02`의 AC를 실측으로 검증했다. `검증 방법` 열은 이 세션이 실제로 실행한 것만 적는다. 표시: ✅ 확인됨 · ⚠ 발견 있음(qa-summary.md §3 참조) · — 이번 세션 범위 밖(이미 407 unittest가 덮음, 재실행으로 회귀 0 확인).

## CF-1 · 이벤트 계약 값 수준 강제 (US-1·US-2)

| AC | 검증 방법 | 결과 |
|---|---|---|
| category 허용값 5종 Enum, 위반 거부 | `python3 -c` 라이브 실행 — `category="우주선"` → `validate_event()`가 `"category 허용값이 아니다 — '우주선'"` 반환 | ✅ |
| page_type 허용값 8종 Enum, 위반 거부 | 동일 방식 — `page_type="아무거나"` → 거부 문구 포함 | ✅ |
| `validate_event()`가 `check_identifier()` 호출 | `grep -n check_identifier src/measurement/schema.py` → 400행에서 호출 확인 + `customer_id="test-user-1"` 라이브 실행 → `"customer_id 식별자 형식 위반"` 반환 | ✅ |
| `unittest discover` 46건 기준 회귀 0 | 407건으로 확장된 현재 스위트 전건 재실행, OK | ✅ (기준선 초과 확장, 회귀 0) |
| 카테고리 어휘 단일화 | — | 407건 스위트에 포함, 재실행으로 간접 확인 |

## CF-2 · Event Sink 신뢰성 복구 (US-3·US-4)

| AC | 검증 방법 | 결과 |
|---|---|---|
| 두 번 나눠 쓴 이벤트(2건+3건)가 5건으로 유지 | `python3 -c` 라이브 실행 — 별도 `EventSink` 컨텍스트 2회(2건, 3건 기록) 후 `read_events()` 합계 확인 | ✅ **5건 확인** (구 결함: 2건+3건→3건) |
| `strict=False`가 크래시하지 않음 | 407건 스위트 내 `test_sink.py` 39건에 포함 — 재실행 OK | — (재실행으로 회귀 없음만 확인, 별도 라이브 재현은 생략) |
| 타임존 KST 정규화 | 실제 `results/`의 `provenance.generated_at`이 KST(`+09:00`) 형식으로 확인됨(§ latency-report에서 재사용한 JSON 조회) | ✅ |

## CF-3 · KPI 정의 v1 (US-5·US-6)

| AC | 검증 방법 | 결과 |
|---|---|---|
| 계산 불가 지표가 0이 아니라 계산 불가로 산출 | `e2e/tests/zero-fill.spec.ts` — 실제 `results/`의 `/kpi`에서 `obs-absent-ink` 슬롯 전수 조사, 숫자 0건 | ✅ |
| 계산 불가에 사유 코드 부착 | `e2e/tests/quality-gate.spec.ts` + 스크린샷 육안 확인(`/kpi`, `/quality`) — `NO_COST_BASIS`·`PRECONDITION_MISSING` 등 원문 코드 인라인 표시 확인 | ✅ |
| 빈 Sink에서 Observable 16개 전부 계산 불가 | 실제 `results/`가 이미 "빈 Sink"(2026-09-14 현재 커머스·시뮬레이터 미연결) 상태 — `/kpi` 라이브 로드로 확인 | ✅ |
| `PARAM_UNCONFIRMED` 지표가 값+파라미터 표시 | `d-01 AC-6` 독립 판단(§4, qa-summary.md) — 코드가 이 요구를 우선했음을 소스 레벨로 확인 | ✅ |

## CF-6 · 측정 산출물 게시 계약 (US-10)

| AC | 검증 방법 | 결과 |
|---|---|---|
| `results/` 아래 파일로 게시 | `ls results/` — `data_quality_report.json` + `measurement/*.json` 6종 확인 | ✅ |
| 출처 분류가 게시 시점에 완료(대시보드가 재분류 안 함) | 코드 리뷰(`Sidebar`/`SourceColumns` 등 — read-only) + `by_source` 필드를 그대로 렌더하는 것을 `/ingestion`·`/kpi` 스크린샷으로 확인 | ✅ |
| `results/` 없는 초기 상태 안내 | 코드상 `EmptyState` 문구 확인(§d-01 4.7) — 이번 세션은 `results/`가 항상 존재해 직접 재현하지 않음 | — |
| `test_isolation -v` 통과 (measurement이 hidden/ground_truth 미참조) | 직접 재실행 — `Ran 6 · OK` | ✅ |

## CF-7 · GA형 관측 대시보드 (US-11~US-14)

| AC (US-11) | 검증 방법 | 결과 |
|---|---|---|
| 총 수집 건수·거부 건수·날짜 범위 | `/` 스크린샷 육안 확인 — 품질 위반 0, 미실행 검사 17, 차단 검사 1, 계산 불가 지표 44 등 요약 카드 확인 | ✅ |
| event_type별 건수 + 1건도 없는 타입 구분 | `/ingestion` 스크린샷 — 16종 매트릭스 렌더 확인(코드 리뷰: 항상 16행 렌더) | ✅ |
| 수집 0건 날짜와 "활동 없음" 구분 | `/` notices의 `INGESTION_GAP_UNDECIDABLE` 인라인 표시 확인 | ✅ |
| 거부를 사유별로 | `/rejections` 페이지 로드 확인(HTTP 200, 콘솔 에러 0) | ✅ |
| 필드 충족률 + 0건 필드 목록 | `/coverage` 페이지 로드 확인 | ✅ |

| AC (US-12 출처 구분) | 검증 방법 | 결과 |
|---|---|---|
| 수집 현황·필드 충족률·KPI에서 출처 2열 | 스크린샷 육안 확인(`/kpi` 등) — 좌 커머스/우 시뮬레이터 구조 확인 | ✅ |
| 1024px 미만 적층 시 커머스 우선 | `e2e/tests/visual-contract.spec.ts` — 900px에서 두 출처 배지의 `getBoundingClientRect().top` 비교, 커머스가 위 | ✅ |
| 출처 파생 근거 각주 | 코드 리뷰로 각주 문구 존재 확인(read-only) | ✅ |

| AC (US-13 계산 불가 비은폐) | 검증 방법 | 결과 |
|---|---|---|
| "계산 불가"가 0과 다른 시각 상태 | `e2e/tests/zero-fill.spec.ts` + `check:state-map`(25/25) 재실행 | ✅ |
| 사유가 화면에 상시 표시 | 스크린샷 육안 확인 — 호버 없이 인라인 노출 | ✅ |
| 커머스 실측 `contribution_profit`이 `계산 불가·원가 근거 없음`, 같은 화면 `revenue`는 값 | **실제 `results/`에서는 revenue도 `NO_SOURCE_EVENT`로 계산 불가**(커머스 이벤트 0건이므로 정상) — 이 정확한 대비는 `commerce-connected` 픽스처에서만 성립. **픽스처가 M-06 계약보다 낡아 현재 깨져 있음**(qa-summary.md §3-A) | ⚠ **발견** |
| 데이터 0건 상태에서 계산 불가로 가득한 것이 정상임을 화면/문서가 설명 | `/` 상단 안내 배너("C1 관측 사이클 — 계산 불가 지표가 많은 것이 정상입니다") 스크린샷 확인 | ✅ |

| AC (US-14 버전 추적) | 검증 방법 | 결과 |
|---|---|---|
| schema_version·config 해시·생성 시각(KST)·커밋 SHA 표시 | `/` 스크린샷 — 게시물 신원 카드에서 전부 확인 | ✅ |
| Lock/미Lock 구분 | `/freeze` 스크린샷 — 9항목 상태별 구분(`OUT_OF_SCOPE`·`PENDING NOT_RUN`·`PARTIAL`) 확인 | ✅ |
| 해시 대조 미실행 시 "미실행" 표시 | `/freeze` — `canonical_files[].verification` not_run 값 렌더 확인(코드 리뷰) | — |
| 데이터 품질 4상태(PASS/FAIL/BLOCKED/미실행) | `e2e/tests/quality-gate.spec.ts` — JSON 5상태(pass/fail/vacuous/not_run/blocked) 전부와 화면 배너 정확 일치 확인 | ✅ |

## d-01 대시보드 앱 골격

| AC | 검증 방법 | 결과 |
|---|---|---|
| AC-1 앱 골격(포트 3001, App Router, force-dynamic) | `npm run build` 성공, 8라우트 컴파일 확인. 포트는 `next start -p`로 임의 지정 가능함을 확인(코드가 포트를 하드코딩하지 않음) | ✅ |
| AC-2 지침 파일(`dashboard/AGENTS.md`·`CLAUDE.md`) | 파일 존재 확인(`ls dashboard/`) | ✅ |
| AC-3 토큰 파이프라인 | `npm run tokens:generate`(prebuild에 연결됨, `npm run build` 성공으로 간접 확인) + `npm run tokens:test` 15/15 | ✅ |
| AC-4 상태 토큰 hex 리터럴 0건 | 코드 리뷰(read-only) — `state-rules.css`가 전부 `var(--ds-colors-*)` 별칭 사용 확인 | ✅ |
| AC-5 읽기 계층(`lib/artifacts/` 화이트리스트) | 코드 리뷰 — `paths.ts`의 `IsolationError` 확인. 라이브 우회 시도는 하지 않음(제품코드 수정 금지 범위 내에서 read-only 확인만) | ✅ |
| AC-6 읽기 최소 불변식(§4 독립 판단) | 위 §4 참조 | ✅ (문서 표현 vs 구현 간 의도적 이탈, 타당함) |
| AC-7 회귀 없음 | `unittest`·`test_isolation`·`check_ownership`·`tokens:check`·`tokens:test` 전부 재실행 | ✅ |

## d-02 관측 화면군

| AC | 검증 방법 | 결과 |
|---|---|---|
| AC-1 화면 8개 | `e2e/tests/pages.spec.ts` — 8라우트 × 3데이터셋 = 24조합 전부 200 | ✅ |
| AC-3 0 채우기 0건(C-1) | `e2e/tests/zero-fill.spec.ts` | ✅ |
| AC-4 결손 비은폐(C-6 등) | 스크린샷 — `/quality` 18행 전부 렌더, `/ingestion` 16종 매트릭스 전부 렌더 | ✅ |
| AC-5 사유 상시 표시 | 스크린샷 육안(호버 없이 인라인) | ✅ |
| AC-6 상태 8종·글리프 | `e2e/tests/accessibility.spec.ts`(글리프 접근성 이름) + `check:state-map` 25/25 | ✅ |
| AC-7 V-12 공허한 통과 | `e2e/tests/quality-gate.spec.ts` — vacuous가 `✓`/초록 없이 정보색으로 렌더, pass=0일 때 체크마크 전체 0건 | ✅ |
| AC-8 출처 2열·순서 불변 | `e2e/tests/visual-contract.spec.ts`(US-12/S-1) | ✅ |
| AC-9 증감 금지 | 코드 리뷰(차트 라이브러리 미도입 확인, D02-a) — grep 기반 재확인은 생략(Andrew 보고와 소스 구조 일치 확인) | — |
| AC-10 거부 샘플 값 미노출 | `e2e/tests/rejections-security.spec.ts` — 실제 offending value 2종이 HTML에 0건 | ✅ |
| AC-11 notices 상시 렌더 | 스크린샷 — `/`·`/quality`·`/freeze`에서 notices 인라인 확인 | ✅ |
| AC-12 USP-1 대표 장면 | **`commerce-connected` 픽스처로 재현 시도 → 실패**(qa-summary.md §3-A). 2026-09-11 촬영분 스크린샷 45장은 현재 코드/데이터로 재현 불가 확인 | ⚠ **발견** |
| AC-13 회귀 없음 + 빈 Sink 전부 계산 불가(C-9) | `unittest` 재실행 + `e2e/tests/zero-fill.spec.ts`(실제 빈 `results/`) | ✅ |

## 신규 검증 — 팀이 "자동화 어려움"으로 남긴 항목

| 항목 | 원 상태 | 이번 세션 결과 |
|---|---|---|
| C-2 (`—` font-size = 값 font-size) | Andrew가 자동화함(Playwright `getComputedStyle`) | — (재검증 생략, 팀 근거를 신뢰. 재현 필요시 `dashboard/e2e/evidence.spec.ts` 참조) |
| C-10 대비 8조합 | "실측 계산 안 함"(BLOCKED로 인지) | **`e2e/tests/contrast.spec.ts`로 자동화, 8/8 4.5:1 이상 확인.** 문서 수치 1건 오차 발견(§3-B) |
| C-11 상태 칩 글리프 전수 | grep 명제로 전환됨(Andrew) | `e2e/tests/accessibility.spec.ts`로 라이브 DOM 재확인 — 접근성 이름 포함 전수 확인 |
| Pretendard 실제 렌더 | 체인 확인(HTTP 200·바이트수·WOFF2 시그니처) + 육안 필요 | **`e2e/tests/visual-contract.spec.ts`로 FontFace 로드·computed font-family·네트워크 응답 자동 확인 + 스크린샷 육안 검토 병행** |

## 발견된 항목 (신규, 팀이 몰랐던 것)

| # | 항목 | 심각도 | 문서 |
|---|---|---|---|
| 1 | 커밋된 예시 픽스처가 M-06 계약보다 낡음 → AC-12 대표 장면 재현 불가 | 중간 · 비차단 | qa-summary.md §3-A |
| 2 | `info` 색 대비 문서값 6.50 vs 실측 6.34 | 낮음 · 문서만 | qa-summary.md §3-B |
| 3 | vacuous 문서상 7건 → 실측 8건(개선, 결함 아님) | 정보 | qa-summary.md §3-C |
