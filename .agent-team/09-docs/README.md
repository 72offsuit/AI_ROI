# `09-docs/` — W6 문서 산출물

BATHOS W6(검증·문서화·리포트) 1단계 산출물. 작성 Timothy(Role 11) · 2026-09-14 · 대상 브랜치 `feat/measurement-layer-and-dashboard`(PR #57, 미병합).

## 무엇이 있는가

| 파일 | 내용 | 독자 |
|---|---|---|
| [`measurement-publish-api-v1.md`](./measurement-publish-api-v1.md) | 게시 계약 `measurement-publish/v1` API 문서 — `docs/contracts/measurement-publish/v1/*.schema.json` + 실제 코드 근거 | 게시물을 읽거나 만드는 개발자(대시보드 결과 화면군 구현자, 다음 사이클 `src/decision/` 개발자) |
| [`dev-definitions.md`](./dev-definitions.md) | 측정 계층·대시보드 핵심 개념·용어 정의서 | 신규 합류자, 다음 사이클 시뮬레이터/의사결정 계층 개발자 |
| [`design-vs-impl-gaps.md`](./design-vs-impl-gaps.md) | 설계 문서(W2~W5)와 실제 구현의 불일치 전수 기록 + 수정 권고 (11건) | 설계 문서를 갱신할 역할, W6 후속 검증(Matthias·Thomas) |

## 이 문서들의 지위

**정본이 아니다.** 코드·계약이 바뀌면 여기가 낡는다 — 방향은 항상 코드/계약 → 이 문서다. 내용은 전부 실제 소스코드·계약 파일을 직접 열어 확인한 것이며, 상상으로 채운 부분이 없다(각 주장에 파일:줄 근거를 달았다).

## 검증 범위 밖

- `src/simulator/`·`src/decision/`·`src/diagnostics/`·`src/orchestration/` — C1에서 미구현, 다룰 내용이 없다.
- `Ecommerce_Service` — 별도 저장소, 이 작업 범위 밖.
- `design-vs-impl-gaps.md`에 기록된 gap의 **실제 수정**(원본 설계 문서 편집) — `09-docs/**` 소유 범위 밖이라 하지 않았다.
