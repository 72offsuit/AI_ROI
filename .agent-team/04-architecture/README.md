# W2 아키텍처 산출물 — 색인 (James · Role 4)

**작성** 2026-09-11 · **개정 2** — 정합 1라운드 (이름 통일 · V-12 · 구분 불가를 값으로) · **개정 1** — Jonnathan 요청 17건 + 리드 판정 3건 · 사이클 C1 · BATHOS Lv3
**제약 준수** 이 디렉터리 아래만 썼다. 제품 코드 · `Plan/` · `Ecommerce_Service` **변경 0건.** GitHub 이슈 생성·수정 **0건.**

## 한 문단 요약

**게시 계약을 기계가독으로 확정했다** — 대시보드가 읽을 6종 게시물의 경로·형식·갱신 방식이 JSON Schema 7개로 고정됐고, **예시 14건과 위반 시도 15건을 실행해 검증했다.**
계약의 불변식은 넷이다 — **계산 불가면 `value` 가 반드시 `null`** · **계산된 값에는 기준(`basis`)이 반드시 있고 계산 불가에는 있을 수 없다** · **검사 대상이 0행이면 `pass` 일 수 없다** · **판정할 수 없는 것은 값이 아니라 사유로 준다.**
*"결손을 0으로 채우지 않는다"* 가 규율에서 **스키마 검증**이 됐고, *"측정된 0 과 값 없음의 구별"* 이 글리프가 아니라 **구조**가 됐다.
**창구 중립성은 분기를 금지하는 대신 계산층이 출처를 알 수 없게 만들어** 구조로 유지한다.
**W5 소유 경계는 겹침 0 을 실행으로 증명했다** (Phillip 42 ∩ Andrew 29 = 0).

## 읽는 순서

| # | 파일 | 태스크 | 먼저 읽어야 할 사람 |
|---|---|---|---|
| 0 | **`architecture-overview.md`** | 전체 | **리드** · 전원 |
| 1 | **`api-contracts.md`** ★ | **T2.7 게시물 계약** | **Jonnathan · Andrew · Phillip · 리드** |
| 2 | **`build-plan.md`** ★ | **T2.12 W5 경계 · 겹침 0 증명** | **리드 · Phillip · Andrew** |
| 3 | `code-structure.md` | T2.6 창구 중립성 배치 | Phillip · Thomas(W6) |
| 4 | `dashboard-architecture.md` | T2.10 라우팅·토큰·W-8·D-6 | **Andrew · Jonnathan · Matthias** |
| 5 | `dependency-plan.md` | T2.9 A7 · CI · docker-compose | Phillip · **리드** |
| 6 | `data-quality-design.md` | T2.8 검사 17종 | Phillip · Matthias |
| 7 | `gate1-freeze-procedure.md` | T2.11 Lock · 탐지 3층 | Phillip · **리드** |
| 8 | `data-model-erd.md` · `service-sequences.md` · `exceptions.md` · `design-patterns.md` | — | 전원 |
| 9 | `adr/ADR-0001~0010` | 결정 근거 | 필요할 때 |

## 기계가독 정본

```
schemas/     JSON Schema draft 2020-12 · 8종
             common · index · ingestion_report · rejection_report ·
             field_coverage_report · kpi_report · data_quality_report · freeze_status
examples/    empty-sink/          — 2026-09-11 현재의 실제 상태 (이벤트 0건 · 미봉인)
             commerce-connected/  — ★ 전 시각 상태가 한 벌에
                                    값/계산불가/미확정/차단/미실행 · 품질 FAIL · 봉인 불일치
tools/       make_examples.py · make_examples_connected.py · validate_examples.py ·
             check_zero_fill_rejected.py · check_ownership.py · ownership.json
```

**문서와 스키마가 충돌하면 스키마가 정본이다.**

## 실행한 검증

```bash
# 1) 예시가 계약을 만족하는가                      → 14건 · 위반 0건
python tools/validate_examples.py

# 2) 계약이 위반을 실제로 거부하는가                → 위반 시도 15건 중 거부 15건
python tools/check_zero_fill_rejected.py

# 3) W5 소유 경계에 겹침이 없는가                  → PASS · Phillip ∩ Andrew = 0
python3 tools/check_ownership.py
```

> ⚠ **1·2 는 스크래치패드 가상환경의 `jsonschema` 4.26.0 으로 실행했다.** 저장소 환경에는 `jsonschema` 가 없고 **설치하지 않았다.**
> 3 은 표준 라이브러리만 쓰므로 저장소 환경에서 그대로 돈다.
> 저장소 테스트로 옮기는 조건은 `dependency-plan.md` §3.2 · §4.

## 이 웨이브의 새 발견

| # | 발견 | 결정 |
|---|---|---|
| **A-1** | **`discount` 필드가 스키마에 없다** — `coupon_cost` 계산 불가 · 금액 정합성 검사 원리적 불가 | **D-16** · **G-16 신설 제안** |
| **T-1** | `data_spec` §17.4 의 `results/` 접근 주체에 measurement 가 없다 (강제 수단은 막지 않는다) | 기록만 |
| **S-1** | `rejected.jsonl` 에 금지 필드가 원문으로 남는다 → 게시하면 화면까지 간다 | 집계·화이트리스트만 게시 |
| **B-1/B-2** | M-3·M-7 문서 파일명이 task-graph 와 이슈 본문에서 다르다 | 이슈 본문을 따름. **리드 확인** |

## Jonnathan 요청 17건 대응

**전부 응답했다.** 대응표는 `api-contracts.md` §9 (17행 · 판정 포함).
**정합 1라운드 완료** — 충족 15 · 조건부 1(`offending_values` 22컬럼 제한) · **미해결 1**(X-5 수집 0건의 *"중단 vs 활동 없음"* — heartbeat 없이는 계약으로 풀 수 없다).
그가 예시에서 찾은 **공허한 통과(V-12)** 는 계약 쪽에서 막는 것이 낫다는 그의 되물음을 받아 **스키마 강제**로 올렸다 (`ADR-0010`).

## 결정 대기

**D-15 ~ D-30 (16건) + B-1/B-2.** 전체 목록과 추천은 `architecture-overview.md` §10.
그중 **사용자·리드 판단이 특히 필요한 것 넷:**

- **D-16** `discount` 처리 — GATE 1 이전에 결정해야 하고 지금이 가장 싸다
- **D-19** `tests-with-deps.yml` 신설 — CI 변경
- **D-22** `test_dashboard_isolation.py` 도입 — 봉인 체계 확장
- **B-1/B-2** 문서 파일명 — task-graph ↔ 이슈 불일치

## 변경 0건 증명

```text
$ git status --porcelain
?? .agent-team/
$ git -C Plan status --porcelain            (빈 출력)
$ git -C ../Ecommerce_Service status --porcelain   (빈 출력)
```
