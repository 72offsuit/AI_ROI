# 07-design — C1 관측 화면군 설계 (Jonnathan · Role 7)

**사이클** C1 · BATHOS Lv3 · 2026-09-11
**태스크** T2.12 정보구조 · **★ T2.13 결손·계산 불가 시각 표현** · T2.14 출처 구분 · T2.15 디자인 토큰 전략 · T2.16 §71 트리거
**목업** https://claude.ai/code/artifact/396e511c-8d97-4e60-ad2d-8d0ee6070cc2 (아트보드 5종)

---

## 읽는 순서

| # | 문서 | 무엇 |
|---|---|---|
| 1 | **[missing-state-spec.md](missing-state-spec.md)** | **★ T2.13 — 이 웨이브의 핵심.** 상태 어휘 8종 · 값 슬롯 규칙 V-0~V-11 · 색·글리프·문구·대비 실측 · **USP-1 대표 장면 명세** · 결손→영향 사슬 |
| 2 | [ux-flow-map.md](ux-flow-map.md) | T2.12 — 첫 화면 판정 배너 · 라우트 지도 · 결과 화면군 자리 · UX Flow ↔ 게시물 계약 대응표 |
| 3 | [ui-spec.md](ui-spec.md) | V1~V7 화면별 명세 · **T2.14 출처 구분** · **T2.16 §71 트리거** |
| 4 | [design-system/token-strategy.md](design-system/token-strategy.md) | **T2.15** — `Ecommerce_Service` 파이프라인 read-only 조사 결과와 재사용 판정 |
| 5 | [design-system/components.md](design-system/components.md) | 컴포넌트 7개 입력 계약·금지 사항 |
| 6 | [design-system/state-tokens.css](design-system/state-tokens.css) | 상태 토큰 제안 CSS — **새 hex 색값 0건** |
| 6.4 | **[dashboard-agents-design-constraints.md](dashboard-agents-design-constraints.md)** | **`dashboard/AGENTS.md` 디자인 절 초안** (리드 J-3 — Andrew 소유). 구현자가 어기기 쉬운 것 + **JS `?? 0` 함정** + fixture 규칙 |
| 6.5 | **[contract-reconciliation.md](contract-reconciliation.md)** | **★ James T2.7 계약과의 대조 결과** — 충족 13 / 미해결 3 / 내 쪽 변경 6. **상태 이름·라우트 개정의 정본** |
| 7 | **[design-handoff.md](design-handoff.md)** | Andrew(W5-C)·W6 전달 · 차단 항목 · **§0.0 어휘 우선순위(계약 > 기획 문서)** · Andrew(W5-C)·Thomas·Matthias·Timothy(W6) 전달 · **차단 항목 B-1~B-7** |

`canvas/` 는 목업 작업 파일이다 (`*.dc.html` 아트보드 · `canvas.json` · 시드된 `c1-observability-dashboard.html`).

---

## 한 줄 요약 3개

1. **`계산 불가`는 한 상태가 아니라 범주다.** C1 지표 47개 중 19개가 계산 불가이므로 단일 회색 상태로는 "이후 사이클(정상)"과 "구조적 결손(조치 필요)"이 구분되지 않는다 → **상태 8종**으로 가른다.
2. **값이 없다는 사실을 값이 있는 것과 같은 크기로 쓴다.** 0으로 채우는 것과 회색으로 흐리는 것은 같은 실패다 (규칙 **V-1**).
3. **기준(분모·모집단·기간)의 유무가 "측정됨"의 판별자다.** 따라서 기준 없는 값은 **우리 쪽 계약 위반**으로 화면에 드러난다 (규칙 **V-3**) — 화면이 자기 입력을 검사한다.

---

## 확정 / 미확정

**확정** — 라우트 8개(계약 `views`와 1:1) · 상태 어휘 8종(계약 `(status, reason_code)`에서 파생) · **UX Flow ↔ 게시물 대응표 대조 완료** (합의 10 · 부분 1 · 불일치 3 — `ux-flow-map.md` §5.1) · 값 슬롯 규칙 12종 · 첫 화면 판정 배너 구조 · 라우트 7 + 결과 8(자리) · 출처는 색이 아니라 위치 · 커머스 0건은 `info`(미연결)이며 오류가 아니다 · 토큰 파이프라인 복제 채택 · §71 트리거는 계획된 부재 표

**리드 판정 완료 (2026-09-11)** — **J-1** USP-1 증명은 fixture + `표본 데이터` 배지, **단 fixture는 실제 파이프라인 산출물이어야 한다** · **J-2** 사이드바 결과 8줄 노출 · **J-3** `dashboard/AGENTS.md` 최초 작성은 **Andrew(W5-C)** 소유

**정합 완료 (2026-09-11, 계약 개정 1)** — 요청 17건 중 **합의 16 · 미해결 1**. 미해결은 **X-5**(수집 0건의 "중단 vs 활동 없음")이며 **계약으로 풀 수 없는 것**이다 — 화면은 "구분할 수 없습니다"라고 쓴다. 대응표는 `ux-flow-map.md` §5.1 ↔ James `api-contracts.md` §9.

**어휘 정본** — 사유 코드·상태 이름이 기획 문서와 계약에 겹치면 **계약이 이긴다**(리드 판정). 사유 코드는 **9종**(계약) 이며 `kpi-definition-v1.md`의 7종이 아니다 → `design-handoff.md` §0.0

**미확정** — **James 1건**: `headline_code`에 `rejected_events` 대응 코드 부재(거부만 있을 때 판정 배너가 `ALL_CLEAR`로 뜬다) + 7종 우선순위 미정. **사용자 2건**: J-4(CI 토큰 검사 — 로컬 훅 수준 추천) · J-5(UI 코드 공유 계획)

**검증하지 않은 것** — `dashboard/`가 존재하지 않으므로 화면 검증 전부 `BLOCKED — 대시보드 미구현`. 검사 가능 지점 12종은 `design-handoff.md` §3에 설계해 두었고 **실행하지 않았다.**

---

## 쓰기 범위

`.agent-team/07-design/` 아래만 썼다. `Ecommerce_Service`·`Plan/`·제품 코드 **변경 0건** (증명: `design-handoff.md` §6). 이슈·commit·push **0건**.
