# ADR-0001 · 대시보드에 API 서버를 두지 않고 파일로 게시한다

**상태** 확정 (정본 재확인) · 2026-09-11 · James
**맥락** T2.7

## 문제
관측 화면군의 원천(`manifest.json`)은 `data/raw/` 아래에 있는데, `DB-014` 의 대시보드 읽기 허용 목록에 `data/raw/` 가 없다.

## 결정
**측정 계층이 `results/` 에 게시하고 대시보드는 그것만 읽는다. API 서버를 두지 않는다.**

## 근거
- `DB-013` 이 *"별도 API 서버를 두지 않는다"* 를 명시하고 `DB-011` 이 수동 새로고침만 요구한다
- `data_spec` §9 가 이미 `src/measurement/validate.py` → `results/data_quality_report.json` 을 규정한다 — **새 경로가 아니라 기존 규칙의 확장 적용이다**
- `tests/test_isolation.py` 의 `FORBIDDEN_PATHS["src.measurement"]` 에 `results/` 가 없다 (실측)
- 관측 화면군이 필요로 하는 것은 집계 수치와 목록뿐이다 — 파일 한 벌로 표현 가능 (가정 A5)

## 기각한 대안
| 대안 | 사유 |
|---|---|
| 대시보드가 `data/raw/` 를 직접 읽는다 | `DB-014` 위반. 예외를 두면 `data/hidden/` 예외 요구가 이어질 자리를 만든다 |
| API 서버를 둔다 | `DB-011`·`DB-013` 이 수동 새로고침·API 없음으로 확정. 실시간 요구가 어느 문서에도 없다 |
| 대시보드가 manifest 를 복사해 온다 | 복사 시점이 계약에 없으면 두 진실이 생긴다 |

## 결과
- 게시 모듈 `src/measurement/publish.py` 가 필요해진다 (소유 이슈 없음 → `AIROI-M8` 초안 · 결정 D-10)
- **깨지는 조건:** 개별 이벤트 검색·필터 요구가 나오면 파일 읽기로 부족해진다. **그때는 멈추고 보고한다. 조용히 API 를 만들지 않는다**

## 정본 긴장
`data_spec` §17.4 는 `results/` 접근 주체를 *"decision · orchestration"* 으로 적고 measurement 를 넣지 않았다.
그러나 같은 문서 §9 가 measurement 의 쓰기를 규정하고 **강제 수단(테스트)이 막지 않는다.** §17.4 표는 읽기 주체 열거로 읽는다. `Plan/` 수정은 권한 밖이므로 고치지 않고 기록만 한다.
