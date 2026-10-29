# DR-183-churn-config — 운영 이탈 정의를 config 로 (#183 ①)

| | |
|---|---|
| 태스크 | #183 ① 이탈 정의 config (FR-10 · SIM-009 · CFG-001, GATE 1 #163 선행, 스프린트 2) |
| 작성 | 시뮬레이터 팀 성환(limtjdghks) · Claude · 2026-10-28 |
| 상태 | 확정 — 위치·범위는 사용자 확정(2026-10-28). 공유 영역(`src/measurement`) 변경은 양 팀 사전 합의 없이 이 PR 에 넣었다(사용자 결정, PR 에 명시) |

## 무엇을 정하는가

운영 이탈 정의(`at_risk_days` · `no_purchase_days` · `no_login_days` · `rule_operator`)를 코드 상수에서 config 로 옮길 때, 어느 파일에 두고 누가 읽으며 `rule_operator`·"미접속"을 무엇으로 계산할지 정한다.

## 정하지 않으면 무엇이 막히나

- FR-10(ASSIGNMENT-MUST) "Churn Definition을 Config에서 변경 가능해야 한다" 와 SIM-009 를 충족하지 못한다. GATE 1 이 `CHURN DEFINITION v1` 을 잠그려면 잠글 대상이 config 에 있어야 한다(data_spec §5.1 "config/simulator_config.yaml 에 기록하고 GATE 1 에서 Lock").
- 지금 `kpi.py` 는 `NO_LOGIN_DAYS` 를 보고만 하고 계산에 쓰지 않으며, `rule_operator` 는 구현이 없다 — config 로 옮겨도 바꿀 수 있는 것이 미구매 일수 하나뿐이다.

## 선택지

| 안 | 내용 | 장점 | 단점 |
|---|---|---|---|
| A | `config/simulator_config.yaml` 에 최상위 `churn` 블록. 시뮬레이터 생성 다이제스트 밖. 측정 계층 `config_loader` 가 그 블록만 읽는다 | CFG-001(SRS `:345-375`)·data_spec §5.1 이 지정한 위치. 생성 다이제스트·`CONFIG_PINS`·골든이 바뀌지 않는다 | 측정 계층이 Hidden Trait 모수가 든 파일을 연다 — 블록만 꺼내고 버리는 규율이 필요하다 |
| B | 별도 파일(예: `config/churn_definition.yaml`) | 경계가 깔끔하다 | CFG-001 위치와 다르다. 새 파일의 소유 경로를 정해야 한다 |

`rule_operator` 의미: OR/AND 두 값만 둔다. "미접속" 은 스키마에 로그인 이벤트가 없으므로 마지막 `session_start`·`purchase` 중 늦은 날부터 센다.

## 조사한 것

| 출처 | 무엇을 말하나 | 우리 맥락에 얼마나 맞나 |
|---|---|---|
| PRD FR-10(`Plan/AI_Retention_ROI_PRD_v2.md:2524-2527`) · §28(`:1123-1156`) | Churn Rule 은 Config 에서 변경 가능. 예시 "30일 미구매 / 또는 60일 미접속", 초기 가설 28/42. yaml 예시에 `rule_operator` 키 없음 | 요구 원문 |
| SRS CFG-001(`Plan/AI_Customer_Retention_ROI_SRS_v2.0.md:345-375`) · SIM-009(`:626-643`) | `churn: no_purchase_days · no_login_days · rule_operator: OR`. "Freeze 전 최종 결정" | 위치(`simulator_config.yaml`)와 키 이름의 근거. `rule_operator` 허용값은 어디에도 열거돼 있지 않다 — OR 예시만 있다 |
| `docs/data_spec.html` §5(`:405-438`) · 부록(`:1183-1188`) | 운영 정의(후향)와 모델 라벨(전향) 분리. `label_window_days` 42 는 운영 정의가 바뀌어도 고정(`:438`) | 라벨 창을 config 로 옮기지 않는 근거 |
| `docs/measurement_contract.md:243` · `:515` | 28/42/60 은 가설값, C1 에서 Lock 하지 않는다. 지표는 `unconfirmed` + `params_used` | 이번에도 값은 가설값 그대로다 |
| `src/measurement/schema.py` `EventType` | 16종에 `login` 없음 | "미접속" 을 `session_start`·`purchase` 로 셀 수밖에 없다 |
| `src/orchestration/run_sprint.py:69-70` | 운영 임계(28/42/60)를 쓰지 않는다. 라벨 창 42 만 쓴다 | 시스템 팀 코드를 고칠 필요가 없다(이 브랜치에서 고치면 `tests/test_team_boundaries.py` 가 실패) |
| `tests/test_neutrality.py` | `kpi.py` 는 I/O 금지, 계산층에 출처 리터럴 금지, `import yaml` 은 `config_loader.py` 에만 | 로딩은 `config_loader`, 계산은 정의 객체를 인자로 받는 구조로 나눠야 한다 |

## 결정

**A.** (사용자 확정 2026-10-28)

- `config/simulator_config.yaml` 최상위 `churn` = `{"at_risk_days": 28, "no_purchase_days": 42, "no_login_days": 60, "rule_operator": "OR"}`. 값은 기존 가설값 그대로다. 시뮬레이터 `genconfig` 는 이 키를 선택 블록으로 받고(객체인지만 확인) 생성 다이제스트에 넣지 않는다.
- `src/measurement/kpi.py` `ChurnDefinition`(frozen dataclass) — 이탈 = (미구매 경과일 ≥ `no_purchase_days`) `rule_operator` (미접속 경과일 ≥ `no_login_days`). `at_risk` = 이탈이 아니고 미구매 경과일 ≥ `at_risk_days`. 값 검사(양의 정수 · `at_risk_days < no_purchase_days` · OR/AND)는 생성 시점에 한다.
- `churn_rate` · `retention_rate` · `winback_rate` · `derived_state_count` 가 `definition` 인자를 받는다(기본 = 가설값). `params_used` 에 `rule_operator` 가 더해지고 `source_event_types` 에 `session_start` 가 더해진다.
- `src/measurement/config_loader.py` `load_churn_definition()` — 파일을 JSON 으로 읽어 `churn` 블록만 꺼내고 나머지는 즉시 버린다. 블록·키·값이 틀리면 `ConfigError`(폴백 없음). 오류 메시지에 다른 블록 이름·값을 싣지 않는다(테스트로 고정).
- `src/measurement/publish.py` — `publish(churn_config_path=…)`, CLI `--churn-config`(기본 `config/simulator_config.yaml`). 지표 메타의 식·알림 문구가 정의를 그대로 싣는다.
- 라벨 창 42일(`LABEL_WINDOW_DAYS` 3곳)은 config 로 옮기지 않는다.
- **정본 값 고정:** `churn` 블록은 생성 다이제스트·`CONFIG_PINS`·GATE 1 해시 어디에도 들지 않는다. 그래서 `tests/test_config_loader.py` 가 정본 config 의 블록 = `kpi.DEFAULT_CHURN_DEFINITION` = 28/42/60·OR 을 단언한다 — 값을 바꾸면 config·kpi 기본값·이 DR 을 함께 고쳐야 테스트가 통과한다. `definition` 을 넘기지 않는 호출자와 게시가 같은 정의를 쓰는 것도 이 단언이 보장한다.

- **소유와 변경 절차(PR #243 리뷰 반영):** 파일은 시뮬레이터 팀 소유(`docs/team_boundaries.json` `owned.sim` 의 `config/simulator*.yaml`)지만 `churn` 블록은 시스템 팀 KPI(`churn_rate`·`retention_rate`·`winback_rate`·파생 상태 수)를 정한다. 그래서 **블록 값 변경은 양 팀 합의 사항**이다 — 시뮬레이터 팀이 단독으로 바꾸지 않는다. 블록은 생성 다이제스트 밖이라 값을 바꿔도 `SIMULATOR_VERSION`·`world_id` 가 바뀌지 않는다. 변경은 게시물의 `params_used` 와 위 핀 테스트로만 드러난다. GATE 1 봉인 편입은 리드 결정(아래 "남은 불확실성").
- **"기본값에서 결과 불변" 의 범위:** 지표 **값**은 그대로다. 게시물 **메타**는 4가지가 바뀐다 — ① `churn_rate`·`retention_rate`·`winback_rate`·`derived_state_count` 의 `source_events`(지표 메타·basis)에 `session_start` 추가, ② `params_used` 에 `rule_operator` 추가, ③ `CHURN_THRESHOLDS_UNCONFIRMED` 알림 문구가 정의 문자열을 싣도록 변경, ④ 공개 상수 `kpi.AT_RISK_DAYS`·`NO_PURCHASE_DAYS`·`NO_LOGIN_DAYS` 제거(→ `kpi.ChurnDefinition`·`DEFAULT_CHURN_DEFINITION`). 대시보드는 `params_used` 를 키·값 그대로 나열하고(`dashboard/src/lib/format/metric.ts:165`) `source_events` 는 타입 선언만 있다. `src/decision` 은 시뮬레이터 팀이 읽을 수 없어 상수 참조 여부를 확인하지 못했다 — 전체 테스트·CI 는 통과했고, 시스템 팀 리뷰로 확인한다.

**근거:** CFG-001(SRS `Plan/AI_Customer_Retention_ROI_SRS_v2.0.md:345-372`, 제목이 `config/simulator_config.yaml` 이고 그 안에 `churn: no_purchase_days · no_login_days · rule_operator`)과 data_spec §5.1 5단계("두 조건을 만족하면 `config/simulator_config.yaml` 에 기록하고 GATE 1 에서 Lock")가 지정한 위치다. 다이제스트 밖에 두면 시뮬레이터 판·골든이 흔들리지 않는다. 기본값에서는 미접속 경과일 ≤ 미구매 경과일이라 OR(42/60)이 미구매 조건 하나와 같다 — 기존 지표 값이 바뀌지 않는다(기존 테스트 전부 통과).

## 기각한 안과 기각 사유

| 안 | 왜 택하지 않았나 |
|---|---|
| B(별도 파일, 예: `config/churn_definition.yaml`) | CFG-001·data_spec §5.1 이 지정한 위치와 다르고 소유 경로를 새로 정해야 한다(사용자 선택 A). PR #243 리뷰가 격리 관점에서 분리를 제안했지만, 요구 원문 위치를 지키고 대신 소유·변경 절차(양 팀 합의)와 "블록만 읽는다" 규율을 명시했다 |
| `kpi.py` 가 config 를 직접 읽음 | `test_neutrality` 의 I/O 금지·출처 리터럴 금지를 깬다 |
| `economic_config.yaml` 에 둠 | GATE 1 정본 해시 대상이라 고치면 `FREEZE_MISMATCH` — 재봉인이 필요하다 |
| "미접속" = `session_start` 만 | 구매 이벤트만 남은 출처(커머스 일부)에서 미구매보다 미접속이 길어지는 모순이 생긴다 |
| `rule_operator` 에 임의 식 허용 | 요구 원문에 OR 예시뿐이다. 두 값으로 충분하고 검증이 쉽다 |
| 라벨 창도 config 로 | data_spec `:193`·`:438` — 바뀌면 런 사이 Incremental Profit 비교가 깨진다 |

## 이 결정이 틀렸다면 어떻게 드러나나

- 기본값으로 게시한 `churn_rate`·`derived_state_count` 가 이 변경 전과 다르면 기본값 보존이 깨진 것이다(`tests/test_kpi_layers.py` 기존 테스트가 잡는다).
- 측정 계층 출력·오류에 Hidden 블록 이름이나 값이 나오면 "블록만 읽는다" 규율이 깨진 것이다(`tests/test_config_loader.py` `TestChurnDefinitionLoader`).
- 비기본 정의가 게시물(`churn_rate`·`retention_rate`·`derived_state_count`·알림)까지 닿지 않으면 전달 경로가 끊긴 것이다(`tests/test_publish_pipeline.py` `TestChurnDefinitionReachesThePublication`, CLI 포함).
- 시스템 팀·리드가 공유 영역 변경을 거절하면 `kpi`·`config_loader`·`publish` 변경을 되돌리고 시뮬레이터 쪽만 남긴다.

## 민감도

`no_purchase_days` ±20%(34~50일)는 이탈률을 직접 바꾼다 — 그래서 값은 가설값 그대로 두고 확정은 data_spec §5.1 절차(구매 간격 P75/P90)와 GATE 1 에 맡긴다. `rule_operator` 를 AND 로 바꾸거나 `no_login_days` 를 `no_purchase_days` 보다 작게 두면 이탈 판정이 실제로 달라진다(테스트로 확인).

## 남은 불확실성

- 값(28/42/60)은 여전히 가설값이다 — `unconfirmed` 로 나간다. data_spec §5.1 확정 절차는 이 DR 범위 밖이다.
- **GATE 1 봉인 대상 편입은 후속이다.** data_spec §5.1 은 이 값을 "GATE 1 에서 Lock" 한다고 적지만, `config/gate1_lock.yaml`(리드 소유)의 정본 해시 목록에 `simulator_config.yaml` 이나 `churn` 블록은 없다. 지금은 핀 테스트만 값을 지킨다. 리드가 GATE 1 범위를 정할 때 함께 정한다.
- `docs/measurement_contract.md`·`docs/event_schema.md`(정본 해시 대상)의 문구는 바꾸지 않았다. 계약 문서에 `rule_operator`·미접속 정의를 적는 것은 재봉인 절차와 함께 양 팀이 정한다.
- 공유 영역 변경을 양 팀 합의 없이 넣었다(사용자 결정 2026-10-28). PR 에서 시스템 팀(민정) 리뷰가 필요하다.
