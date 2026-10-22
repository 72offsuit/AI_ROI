# docs/research — 생성 데이터의 외부 근거

스프린트 1(#142) · 이슈 #148. 시뮬레이터가 **데이터를 가져오지 않고 생성**하므로, 생성 모수와 실현 데이터가 외부 실데이터·통계와 맞는지를 여기서 증빙한다.

| 파일 | 내용 |
|---|---|
| `data_grounding.md` | 정본. §1 발표용 요약 · §2 모수↔근거 대조표(35항목) · §3 조정 권고와 사용자 결정 · §4 stylized fact 검증 기준 F1~F17 · §5 참고문헌 |
| `sources.json` | 출처 52건 (url · 연도 · 유형 · 인용 수치 · 쓰인 모수) |
| `raw_korea.md` · `raw_uplift.md` | 국내 통계 · 업리프트 실험 원자료 메모 |
| `computed/research_*_out.txt` | 외부 원자료 직접 집계 출력 |
| `../../scripts/research/*.py` | 집계 재현 스크립트 (Instacart · dunnhumby Complete Journey · 우리 혼합 모집단) |

원칙: AI 성능 지표(AUC · Qini 등)는 이 근거에 쓰지 않는다. 비교 기준값은 결과를 보기 전에 고정한다(§4).
| `reference_stats.md` · `reference_stats.json` | 공개 실데이터 4종(UCI Online Retail II · Hillstrom · Lenta · X5) 직접 집계 — 구매 간격·객단가 분포 적합, Pareto·지니, 이탈 비율, 처치 ATE·CI, 세그먼트별 음수 ATE 탐색 |
| `../../scripts/research/compute_reference_stats.py` | 위 집계 재현 (입력 경로 인자, 약 1분) |
| `realism_report.md` · `realism_report.json` | 실현 데이터 ↔ stylized fact F1~F17 판정 (`scripts/research/realism_check.py`). ⚠ **F16 은 ground truth(잠재결과 4분면) 집계값**이다 — 시스템 팀은 F16 을 모델 개발 근거로 쓰지 않는다 |
