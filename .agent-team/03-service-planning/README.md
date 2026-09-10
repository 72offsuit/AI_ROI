# W2 기획 산출물 — 색인 (Joshua · Role 3)

**작성** 2026-09-11 · 사이클 C1 · BATHOS Lv3
**제약 준수** 이 디렉터리 아래만 썼다. 제품 코드 · `Plan/` · `Ecommerce_Service` **변경 0건.** GitHub 이슈 **생성·수정·close 0건.**

## 읽는 순서

| # | 파일 | 내용 | 먼저 읽어야 할 사람 |
|---|---|---|---|
| 1 | **`usp.md`** | **★ 가정 A8 판정 (대시보드는 하나다)** + USP 확정 3종 | **리드 · James · Jonnathan · Andrew** |
| 2 | `core-features.md` | Core Feature 10종 + **T2.2 이슈별 Done 정의와 C1 종결 여부** | 리드 · Matthew(W3) |
| 3 | `user-stories.md` | 사용자 스토리 18건 + 인수 조건 | Matthew · Phillip · Andrew |
| 4 | `service-stories.md` | 서비스 스토리 12건 (SS1~SS12 · **자체 정의 번호**) | Matthew · Thomas(W6) |
| 5 | `kpi-definition-v1.md` | **T2.3 확정안** — 지표 47종의 계산식·모집단·기간·분모 | Phillip · James |
| 6 | `economic-rule-v1.md` | **T2.4 확정안** — 원가 근거 규칙 `EC-1`~`EC-9` | Phillip · James |
| 7 | `gate1-lock-scope.md` | **T2.6** — Lock 9종 분류 · 선행 조건 G-1~G-15 | 리드 · Phillip |
| 8 | `issue-priority.md` | **T2.5** — 미발행 초안 3건 우선순위 | **리드 (발행 권한자)** |

## 한 문단 요약

**A8을 기각했다 — 대시보드는 하나다.** 같은 앱(`dashboard/` · Next.js · `:3001` · 결과 파일 읽기)에 **화면군이 둘**이고, C1은 관측 화면군만 만든다.
**C1의 USP는 "계산 불가를 계산 불가로 말하는 것"** 하나다. 나머지 둘은 부분 증명·이후 사이클이다.
**경제 규칙의 핵심은 원가율을 곱해 COGS를 추정하지 않는 것**이고, 가르는 기준은 **출처가 아니라 원가 근거의 유무**다.
**GATE 1은 C1에서 통과하지 않는다** — Lock 9종 중 완전 Lock 가능한 것은 0종, 부분·조건부 4종, 불가 5종이다.

## 추적 연결

```
usp.md §2  USP-1·2·3
        ↓
core-features.md  CF-1 ~ CF-10   (+ charter §3.1 ①~④ 이슈별 Done)
        ↓
user-stories.md   US-1 ~ US-18   (전부 인수 조건 보유)
        ↓
service-stories.md  SS1 ~ SS12   (+ 실패 시 동작)
```

## 사용자 결정 대기 — 14건

`D-1`~`D-14`. 전체 목록과 추천은 최종 보고에 있으며, 각 항목의 근거는 해당 문서 말미에 있다.

| 문서 | 결정 항목 |
|---|---|
| `economic-rule-v1.md` | D-1 원가 근거 처리 · D-2 환불 이벤트 |
| `kpi-definition-v1.md` | D-3 `shipping_subsidy` · D-4 KPI Lock 시점 · D-5 이탈 임계값 |
| `usp.md` | D-6 `dashboard/AGENTS.md` 소유권 |
| `gate1-lock-scope.md` | D-7 부분 Lock 실행 · D-8 `EVENT SCHEMA v1` Lock 범위 |
| `core-features.md` | D-9 `#46` 범위 재단 · D-10 `AIROI-M8` 발행 |
| `issue-priority.md` | ~~D-11 `#29` 충돌~~(**해소 — 리드 정정**) · D-12 T4 · D-13 발행 시점 |
