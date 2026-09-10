# ADR-0002 · 측정 게시물을 `results/measurement/` 아래에 둔다

**상태** 확정 · 2026-09-11 · James

## 문제
이후 사이클에서 `src/decision/` 이 `results/churn_predictions.csv` 등 8종을 같은 디렉터리에 쓴다(`data_spec` §7.5). 한 디렉터리에 섞이면 **누가 쓴 파일인지가 파일명 관례에만 의존**한다.

## 결정
- 측정 계층 게시물은 **`results/measurement/`** 아래
- **예외 하나** — `results/data_quality_report.json` 은 루트에 둔다

## 근거
- 소유 경계가 파일시스템에 드러난다 → W5·이후 사이클의 겹침 0 이 구조로 유지된다
- 예외를 두는 이유: **`data_spec` §9 가 그 경로를 명시했다.** 일관성보다 정본이 우선한다
- 두 진실이 생기지 않는다 — `index.json` 의 `artifacts[]` 가 그 파일을 경로로 참조한다

## 기각한 대안
| 대안 | 사유 |
|---|---|
| 전부 `results/` 루트 | decision 산출물과 섞인다 |
| `data_quality_report.json` 도 하위로 옮긴다 | **정본 경로 변경.** `data_spec` §9 와 `#48` 본문이 그 경로를 적는다 |
| `results/observability/` 등 다른 이름 | 산출 **주체**(measurement)로 이름 짓는 편이 소유 경계와 일치한다 |
