# `.agent-team/09-docs/` — 문서 산출물 (W6 · Timothy)

이 디렉터리는 **BATHOS W6(검증·문서화·리포트)의 문서 산출물 전용 공간**이다. 리드 판정 D-6(2026-09-11, `.agent-team/00-plan/task-graph.md` §4)에 따라 **새로 만드는 디렉터리의 지침 파일은 최초 작성자가 소유한다** — 이 파일은 Timothy(Role 11·문서 전문가)가 작성했다.

## 소유

**W6 Timothy 단독 소유.** 다른 역할이 이 디렉터리에 쓰지 않는다.

## 이 디렉터리가 아닌 것

- **제품 코드가 아니다.** `src/`·`dashboard/`·`config/`·`tests/`·`docs/` 를 대체하지 않는다.
- **정본이 아니다.** 여기 문서는 코드·계약(`docs/contracts/measurement-publish/v1/`)·기획 문서(`.agent-team/03-service-planning/`·`04-architecture/`·`07-design/`)를 **읽고 옮긴 것**이다. 어긋나면 **원본 쪽이 정본**이고, 이 디렉터리의 문서를 갱신한다.
- **기획 문서(`03-service-planning/`·`04-architecture/`·`07-design/`) 를 대체하거나 고치지 않는다.** 그 웨이브들의 산출물은 봉인 대상이며 W6은 검토·정제·gap 기록만 한다 (`task-graph.md` §4).

## 파일

| 파일 | 내용 |
|---|---|
| `README.md` | 이 디렉터리의 안내 |
| `measurement-publish-api-v1.md` | 게시 계약 `measurement-publish/v1` 의 API 문서 — `docs/contracts/measurement-publish/v1/*.schema.json` 을 코드 근거와 함께 사람이 읽는 형태로 옮긴 것 |
| `dev-definitions.md` | 측정 계층·대시보드 핵심 개념·용어의 개발 정의서 |
| `design-vs-impl-gaps.md` | 설계 문서(W2~W5 산출물)와 실제 구현(코드)의 불일치 전수 기록 + 수정 권고 |

## 갱신 규칙

- 코드·계약이 바뀌면 이 문서들도 갱신 대상이다. 단 **이 문서를 수정한다고 코드나 계약이 따라 바뀌지 않는다** — 방향은 언제나 코드/계약 → 이 문서다.
- `design-vs-impl-gaps.md` 에 기록된 gap은 **이 디렉터리 밖의 문서(예: `03-service-planning/kpi-definition-v1.md`)를 고쳐야 해소된다.** 그 문서들은 W6 Timothy 소유가 아니므로, 이 디렉터리에는 **권고만** 남기고 실제 수정은 하지 않았다.
