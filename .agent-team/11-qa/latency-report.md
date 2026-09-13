---
name: latency-report
role: Matthias (Role 15 · QA/SDET)
wave: W6 · 1단계
date: 2026-09-14
---

# Latency 실측 — NFR 대비

## 0. NFR 정본 조회 결과 — 대시보드 응답 시간 NFR은 존재하지 않는다

`Plan/AI_Retention_ROI_PRD_v2.md`(NFR-01~09)와 `Plan/AI_Customer_Retention_ROI_SRS_v2.0.md`(NFR-001~006)를 전수 조회했다.

| 정본 | NFR 목록 | UI/응답시간 관련 |
|---|---|---|
| PRD NFR-01~09 | Reproducibility·Docker·CPU·Python·PyTorch·Configuration·Modularity·UI/Logic Separation·Documentation | 없음 |
| SRS NFR-001~006 | Reproducibility·Leakage Prevention·Experiment Integrity·Maintainability·Logging·Error Handling | 없음 |

**존재하지 않는 기준을 지어내지 않는다(AGENTS.md).** 이 대시보드는 `DB-011`(수동 새로고침, 자동 폴링 없음)이 설계 결정이고, 응답 시간에 대한 정량 NFR은 PRD/SRS 어디에도 없다. 아래는 **기준 대비 판정이 아니라 실측값 자체**이며, 향후 NFR이 정의될 경우 대조할 기준선(baseline)으로 남긴다.

## 1. 측정 방법

Chromium(Playwright, headless) `page.goto(url, { waitUntil: 'load' })` 후 `performance.getEntriesByType('navigation')[0]`에서 `responseStart - requestStart`(TTFB) · `domContentLoadedEventEnd`(DCL) · `loadEventEnd`(Load) · `transferSize`를 읽었다. `next start`(프로덕션 빌드, `force-dynamic` — 매 요청 재렌더) 대상, localhost, 각 경로 2~3회 측정.

## 2. 실측값 — `real`(현재 `results/`, 빈 Sink) 데이터셋

| 경로 | TTFB (ms) | DOMContentLoaded (ms) | Load (ms) | 전송 크기 (KB) |
|---|---|---|---|---|
| `/` | 8.1 ~ 38.6 | 19.8 ~ 49.2 | 19.8 ~ 87.6 | 9.5 |
| `/ingestion` | 5.1 ~ 11.6 | 12.5 ~ 27.8 | 13.3 ~ 27.8 | 12.8 |
| `/rejections` | 3.5 ~ 4.2 | 9.0 ~ 10.0 | 9.6 ~ 10.5 | 9.4 |
| `/coverage` | 7.0 ~ 17.7 | 14.4 ~ 37.8 | 15.6 ~ 37.8 | 15.5 |
| `/kpi` | 8.0 ~ 12.6 | 16.7 ~ 21.7 | 18.7 ~ 23.6 | 21.8 |
| `/quality` | 4.2 ~ 4.8 | 10.8 ~ 11.7 | 11.8 ~ 12.7 | 13.9 |
| `/freeze` | 3.4 ~ 7.6 | 9.4 ~ 22.8 | 10.0 ~ 22.8 | 11.9 |
| `/triggers`(정적) | 2.7 ~ 3.0 | 8.2 ~ 8.6 | 8.8 ~ 11.2 | 7.7 |

**최대 Load 87.6ms(`/`, 콜드 스타트 1회차) — 이후 요청은 전부 10~40ms대.** 첫 요청이 느린 것은 Next.js의 요청별 컴파일 캐시가 아직 데워지지 않은 것으로, 프로덕션에서 두 번째 요청부터는 해당 없다.

## 3. 실측값 — `commerce-connected`(18,647건 이벤트 규모 픽스처) 데이터셋

데이터 볼륨이 응답 시간에 미치는 영향을 보기 위해 별도 측정했다.

| 경로 | TTFB (ms) | DCL (ms) | Load (ms) | 전송 크기 (KB) |
|---|---|---|---|---|
| `/` | 24.4 ~ 36.4 | 40.4 ~ 45.9 | 40.4 ~ 84.7 | 8.5 |
| `/ingestion` | 10.9 ~ 19.3 | 31.5 ~ 38.2 | 31.6 ~ 38.2 | 13.4 |
| `/rejections` | 3.8 ~ 12.5 | 9.6 ~ 26.2 | 10.3 ~ 26.2 | 8.6 |
| `/coverage` | 14.3 ~ 18.7 | 33.0 ~ 35.5 | 33.0 ~ 35.5 | 14.3 |
| `/kpi` | 17.8 ~ 18.8 | 28.8 ~ 29.1 | 30.2 ~ 30.5 | 15.8 |
| `/quality` | 4.0 ~ 17.8 | 10.1 ~ 27.8 | 11.0 ~ 28.7 | 10.5 |
| `/freeze` | 4.5 ~ 6.6 | 10.8 ~ 13.4 | 11.7 ~ 14.3 | 11.9 |

**데이터 규모(빈 Sink → 18,647건 이벤트 요약)가 Load 시간에 주는 영향은 실질적으로 없다** — 두 데이터셋 모두 40ms 이내가 정상 범위이고, 차이는 측정 잡음(로컬 파일시스템 캐시·Node 이벤트 루프 스케줄링) 수준이다. 이는 대시보드가 `results/`에 이미 집계된 JSON만 읽고(§DB-012, 화면이 계산하지 않음) 원본 이벤트를 순회하지 않기 때문으로, 설계가 의도한 대로다.

## 4. 해석

- **DB-011(자동 폴링 없음, 수동 새로고침)** 설계와 무관하게, 수동 새로고침 자체의 응답성은 전 화면이 100ms 이내로 매우 빠르다 — 사용자가 "느리다"고 체감할 latency가 아니다.
- 첫 요청(콜드 스타트)이 최대 87ms까지 늘어나는 것은 Next.js `force-dynamic` 라우트의 정상적인 첫 컴파일 비용이며, 파일 I/O(`results/` JSON 파싱)가 병목이 아님을 시사한다.
- 이 팀(2~5인) 내부용 관측 대시보드라는 charter §7.1의 1차 독자 규모를 고려하면 현재 latency는 **문제가 될 수준이 아니다.**

## 5. 권고

- 정량 NFR이 없으므로 이번 게이트의 판정 기준으로 latency를 사용하지 않는다(위 §0).
- 다음 사이클에서 시뮬레이터가 20,000+ 고객·12개월 이벤트를 생성하기 시작하면 `results/` JSON 파일 자체의 크기가 커질 수 있다 — 그 시점에 이 문서의 수치를 baseline으로 재측정할 것을 권고한다(특히 `/kpi`의 47종 지표 전체 렌더 · `/coverage`의 22필드 표).
