# `src/` — 파트 경계 지도

이 시스템은 **서로 봐서는 안 되는 두 파트**로 나뉜다. 작업을 시작하기 전에 **자기 파트가 어디인지 확인**하고, 해당 디렉터리의 `AGENTS.md`를 읽는다.

## 왜 나누는가

`simulator`는 고객 행동의 **정답을 만들어내는 쪽**이고, `decision`은 그 행동 기록만 보고 **정답을 맞혀야 하는 쪽**이다. 시험에 비유하면 출제자와 수험생이다. 수험생이 답안지를 보면 점수는 100점이 나오지만 실력은 0이다.

가장 위험한 누수는 코드가 파일을 훔쳐보는 것이 아니라, **AI 성능이 낮다는 이유로 시뮬레이터를 고치는 것**이다 (PRD §80 Risk 1). 사람도 에이전트도 이 유혹에 빠진다.

## 파트

| 디렉터리 | 역할 | 비유 |
|---|---|---|
| `measurement/` | 이벤트 스키마·KPI·경제 규칙·Event Sink | **창구** — 두 파트가 만나는 유일한 지점 |
| `simulator/` | 가상 고객 생성과 행동·처치 반응 시뮬레이션 | **출제자** |
| `decision/` | Feature·Churn·Uplift·CLV·전략·최적화·대시보드 | **수험생** |
| `diagnostics/` | Ground-truth 대비 사후 채점 | **채점자** — 시험이 끝난 뒤에만 등장 |
| `orchestration/` | 실행 루프. 양쪽에 명령만 내린다 | **지휘자** |

## import 규칙 (`tests/test_isolation.py`가 강제)

| 이 모듈이 | 이것을 import할 수 없다 |
|---|---|
| `src.decision` | `src.simulator`, `src.diagnostics` |
| `src.simulator` | `src.decision`, `src.diagnostics` |
| `src.measurement` | `src.simulator`, `src.decision`, `src.diagnostics` |
| `src.orchestration` | `src.simulator._internal`, `src.diagnostics` |

`measurement`는 **아무에게도 의존하지 않는다.** 창구가 한쪽 편을 들면 계약이 아니게 된다.

## 데이터 경로 규칙

| 경로 | 내용 | 접근 가능 |
|---|---|---|
| `data/raw/`, `data/processed/` | 고객 행동 기록, Feature | 모두 |
| `data/hidden/` | Hidden Trait (쿠폰 민감도 등 생성 파라미터) | `simulator`, `diagnostics` |
| `data/ground_truth/` | Potential Outcome, 참 CATE | `diagnostics` **전용** |
| `results/` | 모델 성능·전략 결과 | `decision`, `orchestration` |

`simulator`에서 작업할 때 `results/`를 읽지 않는다. `decision`에서 작업할 때 `data/hidden/`·`data/ground_truth/`를 읽지 않는다.

## 봉인 (GATE)

- **GATE 1** 이후 `simulator/`의 행동·처치 파라미터를 AI 성능을 이유로 바꾸지 않는다.
- **GATE 2** 이후 `decision/strategies.py`의 S1 규칙(`S1_RULE` · `plan_S1`)과 예산 상한 `C_rule`을 바꾸지 않는다(#170).
- 결과 리포트에는 실행 시점의 `simulator_commit`을 기록한다. 봉인 후 `simulator/`가 바뀌면 이 값이 어긋나고, 그때는 **Baseline부터 전 전략을 재실행**한다 (SRS FREEZE-003).

상세는 `Plan/AI_Retention_ROI_PRD_v2.md` §10 · §21 · §80, `Plan/AI_Customer_Retention_ROI_SRS_v2.0.md` NFR-002 / ISO-001~005, `docs/data_spec.html` §17을 따른다.
