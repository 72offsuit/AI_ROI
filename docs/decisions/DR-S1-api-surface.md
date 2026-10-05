# DR-S1-api-surface — `api.py` 는 모듈 함수, 한 프로세스에 세계 하나, 핸들은 불투명 문자열

| | |
|---|---|
| 태스크 | S1 · #75 |
| 작성 | James(BATHOS 역할 에이전트) · 2026-10-04 |
| 상태 | 번복 (부분) · 2026-10-04 리뷰 반영 — 결정 7 의 계약 문서 범위에 CLI 절을 더했다(사용자 확인 2026-10-04). 그 밖의 결정은 확정 그대로 (아래 「정정 (2026-10-04, 리뷰 반영)」) |

## 무엇을 정하는가

`src/simulator/api.py` 가 **무엇을 열고 무엇을 닫나.** 함수 목록 · 시그니처 · 각 함수의 S1 동작 · 실패 방식 · 절대 돌려주지 않는 것 · CLI. 그리고 문서마다 다른 표기(SRS · 파트 지침 · 이슈 · `data_spec`)를 하나로 정리한다.

## 정하지 않으면 무엇이 막히나

- `D9`(#91)는 이 계약 위에서 스텁으로 진행한다 — *"`S1` 이 아직 없으면 계약 형식만 합의하고 스텁으로 진행"*(이슈 #91). 시스템 팀은 `src/simulator/**` 를 **`api.py` 포함** 읽지 않는다(`docs/TEAM_SETUP.md:62`). 시그니처가 문서로 고정되지 않으면 D9 가 설 자리가 없다.
- 이슈 #75 표: *"너무 많이 열면 시스템 팀이 내부를 보게 되고, 너무 적게 열면 `orchestration` 이 못 돈다."*
- `S2`~`S6` 이 이 표면 뒤에 구현을 채운다. 표면이 바뀌면 D9 가 따라 바뀐다.
- 교환 묶음을 내는 표면(이슈 #75 코멘트, #117).

## 선택지

| 축 | 안 | 장점 | 단점 |
|---|---|---|---|
| 형태 | ① 모듈 함수 + 프로세스당 활성 세계 1개 | 이슈·SRS 표기 그대로. 세계를 여러 개 들고 섞을 길이 없다 | 테스트가 세계를 바꿀 때 전역 상태를 갈아끼운다 |
| | ② 클래스 인스턴스(`Simulator.init(...)`, `src/orchestration/AGENTS.md:15`) | 여러 세계를 동시에 들 수 있다 | 인스턴스 속성으로 내부(Hidden Trait 포함)를 들여다볼 수 있다 |
| 스냅샷 핸들 | ⓐ 상태를 담은 객체 | 단순 | 호출자가 객체를 열어 Hidden Trait 을 볼 수 있다 |
| | ⓑ 불투명 문자열 토큰, 상태는 시뮬레이터 안 레지스트리 | 호출자 손에 숨김 정보가 없다. SRS 의 `restore(snapshot_id)` 와 이슈의 `restore(snap)` 이 둘 다 맞는 표기가 된다 | 레지스트리 메모리를 누가 비우나 정해야 한다 |
| 저장 위치 | ㉠ `save_state(path)` — 호출자가 경로 지정 (리드 권고) | 유연 | 상태에 Hidden Trait 이 있어 `data/hidden/` 에 둬야 하는데, **`src/orchestration` 소스에는 `"data/hidden"` 문자열이 금지**다(`tests/test_isolation.py:31-35`). D9 가 올바른 경로를 쓸 수 없다 |
| | ㉡ `save_state()` 가 시뮬레이터 소유 위치에 쓰고 `state_id` 를 돌려준다 | 숨김 경로를 시스템 팀 코드가 몰라도 된다 | 테스트용 위치 지정 인자가 하나 필요하다 |
| 실패 | 예외 / 상태값 반환 | 예외는 무시할 수 없다 | 상태값은 확인을 잊으면 조용히 진행한다 |
| `metrics` | 지금 비즈니스 지표까지 / 건수만, 나머지 계산 불가 | — | S1 은 구매를 만들지 않아 비즈니스 지표의 근거가 없다 |

## 조사한 것

| 출처 | 무엇을 말하나 | 우리 맥락에 얼마나 맞나 |
|---|---|---|
| 표기 대조 — 아래 "표기 대응표" | 다섯 곳이 서로 다른 이름·형태를 쓴다 | 정본을 하나로 정하고 나머지 정정을 후속으로 남긴다 |
| `tests/test_isolation.py:23-36` | orchestration 은 `src.simulator._internal` import 금지, 소스에 `"data/hidden"` 문자열 금지. simulator 는 `"results/"` 문자열 금지 | 안 ㉠ 이 막히는 직접 근거. 표면은 `api.py` 하나여야 한다 |
| `src/simulator/_internal/AGENTS.md:8` | Hidden Trait·τ·Potential Outcome 을 `api.py` 를 포함해 **어떤 외부 모듈에도 반환하지 않는다** | 핸들 ⓑ 의 근거. 반환값 전부가 이 규칙의 대상이다 |
| 이슈 #91 "상태 저장 실패 시" | *"저장이 실패했는데 진행하면 다음 창이 조용히 새 세계에서 시작한다. 거부해야 한다"* | 실패는 예외여야 한다 |
| `src/measurement/schema.py:471-484` · `:855-879` | `MetricStatus` 5종, `not_run` 은 "시도하지 않음", 선행 산출물이 없으면 `PRECONDITION_MISSING` | `metrics` 가 비즈니스 지표를 0 으로 채우지 않고 낼 어휘가 이미 있다. 같은 타입을 쓴다 |
| 계약 README §8 (`docs/contracts/commerce-exchange/v1/README.md:120-130`) · §11 끝줄(`:172`) | 묶음이 없으면 `not_run`. 묶음 생성 시점·주기는 S1·S4 가 정한다 | `exchange_bundle` 이 S1 에서 아무것도 쓰지 않고 `not_run` 을 돌려주는 것이 계약과 맞다 |
| `src/measurement/exchange.py:148-153` | 묶음 위치는 Sink 루트의 형제 `simulator_exchange` | 묶음 경로를 시뮬레이터가 Sink 루트에서 유도할 수 있다 |
| `Plan/AI_Customer_Retention_ROI_SRS_v2.0.md:678-683` SIM-013 | UI 없이 Event Sink 에 직접 기록, 백엔드 전용 | CLI 가 필요하다 |
| `requirements.txt:11-16` | `import yaml` 은 `src/measurement/config_loader.py` 한 곳. 격리 CI 에 PyYAML 이 없다 | profile 정의를 YAML 로 두면 S1 테스트가 격리 CI 에서 돌지 못한다. `docs/data_spec.html:180` 이 말하는 `config/simulator_config.yaml` 은 **존재하지 않는다**(`config/` 에 `economic_config.yaml`·`gate1_lock.yaml` 뿐) |

**표기 대응표**

| 출처 | 초기화 | 진행 | 분기 | 기타 |
|---|---|---|---|---|
| SRS SIM-012 (`SRS:667-672`) | `init(seed, num_customers, profile)` | `advance(n_days)` | `snapshot() / restore(snapshot_id)` | `apply_treatment(assignments)` |
| `src/simulator/AGENTS.md:33-36` | 같음 | `advance(n_days)` | `restore(snapshot_id)` | 같음 |
| `src/orchestration/AGENTS.md:15-27` · `docs/data_spec.html:880-892` | `Simulator.init(seed=…, …)` 클래스 | `sim.advance(…)` | `sim.snapshot()` / `sim.restore(snap)` | `sim.events(until=…)` · `sim.metrics(…)` |
| `docs/TEAM_SETUP.md:178-185` · 이슈 #75 | `init(seed, num_customers, profile)` | `advance(days)` | `snapshot() / restore(snap)` | `events(until)` · `metrics(start, end)` |
| **이 DR (정본)** | `init(seed, num_customers, profile, output_root)` | `advance(days)` | `snapshot()` → 토큰 · `restore(snap, *, output_root)` | 아래 표 |

## 결정

**사용자 결정 (2026-10-04. 결정 4 는 `DR-S1-cart-lifetime`):**

1. 모듈 함수. 한 프로세스에 활성 세계 1개. `src/orchestration/AGENTS.md` 의 `Simulator.init(...)` 클래스 표기와 `src/simulator/AGENTS.md` 의 `advance(n_days)`/`restore(snapshot_id)` 표기는 이 DR 이 위 대응표로 정리하고, 그 문서들(리드 전용) 정정은 후속 과제로 남긴다.
2. S1 범위는 최소 검증 시나리오 — 단순 규칙으로 `session_start`·`page_view`·`product_view`·`add_to_cart`·`remove_from_cart` 만 만든다. 페르소나·분포·구매·처치 반응은 S2~S6. **검증용이며 분포 근거 없음.**
3. `restore` 뒤의 쓰기는 호출자가 지정한 **빈** `output_root` 에만. 이미 쓴 경로에 다시 쓰려 하면 오류. 자동 분기 경로·메모리 전용 분기는 기각.
5. `exchange_bundle(until)` 은 표면만 두고 S4(#78) 전까지 `status = not_run` 을 돌려준다.
6. **본선 이어가기.** T0 에서 `save_state()` 와 `snapshot()` 을 **둘 다** 받는다. 전략 분기는 `restore(snap, output_root=새 빈 경로)`, 본선은 `load_state(state_id, 본선 루트)` 로 이어간다(아래 D9 루프 예시).
7. **계약 공개 문서 `docs/simulator_api.md` 를 신설한다** (시뮬레이터 팀 소유 경로). 시스템 팀이 읽는 계약의 정본은 이 파일이다. 구현 단계에서 Phillip 이 쓴다. 담는 것은 **함수 · 인자 · 예외 · D9 루프 예시**이고, 장바구니 30일 같은 **행동 규칙은 넣지 않는다**(출제자 내부 규칙). **2026-10-04 리뷰 반영(사용자 확인 2026-10-04):** CLI 절을 더한다(`docs/simulator_api.md:112` 이하) — 하위 명령·인자·종료 코드·운용 제약. 계기는 Matthias D-3(계약 문서만으로 CLI 를 검증할 수 없었다). 행동 규칙 제외는 그대로다.
8. 나머지는 리드 기본값으로 확정 — 스냅샷은 불투명 토큰, `discard_snapshot` 추가, `save_state()` 는 `state_id` 를 돌려준다. **커머스 이벤트와 시뮬레이터 이벤트를 한 Sink 루트에 섞지 않는다** — 시뮬레이터는 자기 루트에만 쓴다. 장바구니 30일은 시스템 팀 공개 문서에 넣지 않는다.

**공개 표면** (이름은 이슈 #75 표기를 정본으로 한다)

| 함수 | S1 동작 | 실패 |
|---|---|---|
| `init(seed, num_customers, profile, output_root, *, hidden_root=None) -> None` | 새 세계를 만들어 활성 세계로 둔다(이전 세계와 스냅샷 토큰은 버린다). 이벤트를 쓰지 않는다. `seed` 는 `0 ≤ seed < 2⁶³` 정수(이벤트 `random_seed` 가 정수 열이다, `schema.py:224`), `num_customers` 는 1 ~ 99,999,999(`customer_id` 8자리), `bool` 거부. `customer_id` 는 `C00000001` 부터 순번. `output_root` 는 시뮬레이터 전용 Sink 루트이며 비어 있어야 한다(커머스 이벤트와 섞지 않는다) | `TypeError` · `ValueError` · `OutputRootError` |
| `advance(days) -> RunSummary` | `DR-S1-time-model` 의 창을 생성해 `EventSink` 로 기록한다. 한 번 = Sink 실행 1건 + 시뮬레이터 계보 기록 1건. 돌려주는 것은 `run_id`·창·이벤트 수뿐 | 초기화 전 `NotInitializedError`. 끝 시각이 `MAX_TIME_MS = 10¹³` 을 넘으면 쓰기 전에 `ValueError`. 비어 있지 않은 루트의 `verify_lineage` 가 `ok` 가 아니거나(중단된 쓰기 흔적 — fail-closed), **계보 사슬 검증**(구성원이 주장한 파일의 sha256·건수)을 통과하지 못하거나, 계보 머리가 예상과 다르면(다른 누군가 썼다) `OutputRootError`. 쓰기 관문은 이어쓰기 `load_state` 와 같은 기준이다(리뷰 반영 3차 — Thomas F2, 사용자 승인 2026-10-04). 루트의 형식이 섞였거나 런타임이 그 형식을 쓸 수 없으면 `SinkFormatError` (`src/simulator/api.py:160-180`, 사슬 검증 `:173`) |
| `snapshot() -> str` | 현재 상태 전체를 시뮬레이터 안 레지스트리에 담고 불투명 토큰을 돌려준다. 같은 토큰으로 여러 번 `restore` 할 수 있다 | `NotInitializedError` |
| `restore(snap, *, output_root) -> None` | 토큰의 상태로 되돌리고 이후 쓰기를 **빈** `output_root` 로 돌린다(사용자 결정 3) | 모르는 토큰·다른 세계의 토큰 `SnapshotError`, 비지 않은 루트 `OutputRootError`. 스냅샷 계보의 저장 형식을 이 런타임이 읽을 수 없으면 **세션을 바꾸기 전에** `SinkFormatError` — 새 루트도 만들지 않는다(리뷰 반영 2차 — Thomas N4, `src/simulator/api.py:275` → `:610-613`) |
| `discard_snapshot(snap) -> None` | 레지스트리에서 지운다 | `SnapshotError` |
| `apply_treatment(assignments) -> None` | `assignments: Mapping[str, str]` — `customer_id → treatment_id`. 전부 검사한 뒤 하나라도 틀리면 **아무것도 기록하지 않는다**. 검사: 키가 `^C\d{8}$` 이고 이 세계에 있는 고객, 값이 `^T[0-4]$`(`schema.py:449`). 통과하면 현재 시각으로 배정 이력에 적는다(`T0` 포함). **S1 에서는 행동이 바뀌지 않고 이벤트도 생기지 않는다** — 반응은 S5·S6 | `AssignmentError` |
| `events(until) -> Iterator[dict]` | 이 세계의 계보가 낸 이벤트 중 `timestamp < until` 인 것을 측정 계약 형식 그대로, 생성 순서 `(time_ms, customer_id, seq)` 로 돌려준다. 분기 루트라면 분기 이전 이력도 계보를 따라 읽는다(`DR-S1-world-state`). `until` 은 시간대가 있는 `datetime`, 현재 시각 이하 | naive `datetime` `ValueError`, 미래 시각 `ValueError`. 반환 전에 계보 사슬과 조상 루트를 검증한다. 조상 루트에서는 **계보 구성원이 주장한 파일만** 읽는다. 기준값은 숨김 영역 사이드카의 `files`·`sha256`·`rows` 이고, run 기록 · 사이드카 · 재계산한 다이제스트가 모두 같고 run `rows` = 사이드카 `rows` = `event_count` 여야 하며, 같은 계보의 두 구성원이 같은 파티션을 주장하면 거부한다 — 모두 **읽기 전에** 확인한다. 읽은 뒤에는 실제 행 수 = `event_count` 를 대조한다(`DR-S1-world-state` 리뷰 반영 2·3차). 실패하면(실행 기록·파티션이 사라짐, 내용이 다름, 행 수가 다름, 사슬이 이어지지 않음) **일부만 돌려주지 않고** `OutputRootError`. 디코드 오류(`EOFError`·`zlib.error`·`ArrowInvalid` 등)도 `OutputRootError` 이고 원래 예외는 `__cause__` 에 있다. 계보 루트의 형식을 이 런타임이 읽을 수 없거나 의존성이 없으면 `SinkFormatError` (`src/simulator/api.py:597-607` · `:616-647`). **계약 문장 (리뷰 반영 3차 — Thomas F3):** "반복 도중 예외가 나면 그때까지 받은 이벤트는 불완전하므로 쓰지 않는다(전량을 받은 뒤에만 쓴다)"(`docs/simulator_api.md:81`, `src/simulator/api.py:351`). 순회 도중 실패는 숨김 영역 사이드카까지 run 기록과 함께 위조한 경우에만 남는다(`DR-S1-world-state` N3) |
| `metrics(start, end) -> dict[str, MetricValue]` | `[start, end)` 의 이벤트 건수와 유형별 건수. 유형 중 **이 시뮬레이터 판이 만들 수 있는 것**의 0 은 측정된 0(`ok`)이고, 만들 수 없는 유형(S1 에서는 `purchase` 등 11종)은 `not_run`·`PRECONDITION_MISSING`. 비즈니스 지표는 전부 `not_run` — **0 으로 채우지 않는다**(`docs/TEAM_SETUP.md:265`). 관측 이벤트만으로 계산하고 숨김 상태를 읽지 않는다. **구현 키**(`src/simulator/api.py:61` · `:369-411`): `events_total`, `events.{event_type}` 16종(만들지 않는 유형은 `not_run`·`PRECONDITION_MISSING`·단위 `count`), 비즈니스 지표 `churn_rate`·`revenue`·`contribution_profit`·`marketing_cost` 는 `not_run`·`PRECONDITION_MISSING` | `events` 와 같음(사슬 검증 후 반환). `start > end` 도 `ValueError` |
| `save_state() -> str` | 현재 상태를 시뮬레이터 소유 위치(`DR-S1-world-state`)에 원자적으로 쓰고 `state_id` 를 돌려준다 | 쓰기 실패는 예외로 올린다(이슈 #91) |
| `load_state(state_id, output_root, *, hidden_root=None) -> None` | 저장된 상태를 활성 세계로 둔다. `output_root` 는 비어 있거나, 그 루트의 계보 머리가 이 상태에서 끝났어야 한다 | `StateFormatError` — 상태 파일이 **없거나**, **손상됐거나**(JSON·구조 오류), 정준형·다이제스트가 `state_id` 와 맞지 않거나, `format_version`·`rng_scheme`·`simulator_version` 이 다르다. Python 판은 거부 사유가 아니다(`DR-S1-world-state`). `state_id` 의 타입·형식 오류는 `TypeError`/`ValueError`. `StateFormatError` 는 **판 불일치·무결성·구조 위반** 전부다 — `decode` 가 항목의 형태·타입·범위를 검사한다(2026-10-04 리뷰 반영, Thomas L5 · Matthias D-2). `OutputRootError` — 비지 않은 루트의 `verify_lineage` 가 `ok` 가 아니거나, 머리 사이드카가 이 상태에서 끝나지 않았거나 다른 루트의 것이거나, 빈 루트인데 이 상태로 이어지는 계보를 검증할 수 없다(`DR-S1-world-state` `parent_run_id` 규칙). `SinkFormatError` — 이어 쓸 루트의 형식을 이 런타임이 쓸 수 없거나, **빈 루트로 이어받을 때** 계보의 `sink_format` 을 이 런타임이 읽을 수 없다. 둘 다 세션을 바꾸기 전에 거부하고 새 루트를 만들지 않는다(리뷰 반영 2차 — Thomas N4, `src/simulator/api.py:496-497` → `:610-613`). 이어쓰기 `OutputRootError` 판정에는 계보 사슬 검증(sha256·건수·이중 주장)이 포함된다 — `advance` 와 같은 관문이다 |
| `exchange_bundle(until) -> dict` | S1: 아무것도 쓰지 않고 `{"status": "not_run", "reason_code": "PRECONDITION_MISSING", "detail": "S4(#78) 전까지 주문을 생성하지 않는다", "path": None}` 을 돌려준다. S4 부터는 시뮬레이터가 직접 Sink 루트의 형제 `simulator_exchange` 에 전량 스냅샷을 쓰고 같은 모양으로 경로와 행 수를 돌려주는 것을 **제안**한다 — S4 가 확정 | 초기화 전 `NotInitializedError`. `until` 은 `events` 와 같은 검사를 받는다 — `datetime` 이 아니면 `TypeError`, 시간대가 없거나 현재 시각보다 미래면 `ValueError` (`src/simulator/api.py:504-522` · `:583-594`) |

- 예외는 `api.py` 의 `SimulatorError` 아래에 둔다(`NotInitializedError`·`OutputRootError`·`SnapshotError`·`StateFormatError`·`AssignmentError`·`SinkFormatError`). `SinkFormatError` 는 2026-10-04 리뷰 반영으로 더했다(Matthias D-1: pyarrow 없는 런타임에서 계약에 없는 `ModuleNotFoundError` 가 새던 것을 쓰기·읽기 **전에** 이 예외로 막는다, `src/simulator/api.py:88`).
- **런타임 범위 (사용자 결정 2026-10-04, R-1).** "`requirements.txt` 를 설치하면 모든 판(3.10 이상)에서 전 기능이 동작한다. 의존성이 없는 환경은 jsonl.gz 루트만 읽을 수 있다." 계약 문서에도 같은 문장이 있다(`docs/simulator_api.md:66` · `:140`). 고정된 `pyarrow==25.0.1` 은 cp310 휠을 낸다(PyPI `requires_python >=3.10`, 2026-10-04 확인). 대안 "시뮬레이터는 항상 jsonl.gz"는 S3 규모의 크기·속도 때문에 사용자가 기각했다. 3.10 + `requirements.txt` 조합은 Matthias 가 scratchpad venv 에서 실측으로 확인했다(최종 검증 R-1 PASS, `events()` 전체가 3.12 연속 실행과 같음). CI 잡은 없다.
- 인자 타입·범위 위반은 표준 `TypeError`/`ValueError`. 실패를 `False`·빈 결과로 돌려주지 않는다.
- **`SinkFormatError` 메시지 (리뷰 반영 3차).** 이어 쓸 출력 루트의 형식을 쓸 수 없을 때와 조상 계보의 형식을 읽을 수 없을 때 메시지를 따로 둔다. 앞쪽은 "pyarrow 가 있는 런타임에서 잇거나 새 빈 루트로 이어간다", 뒤쪽은 "requirements.txt 를 설치한 런타임에서 이어받거나 읽는다"를 안내한다. 두 메시지 모두 경로를 담지 않는다(`src/simulator/_internal/lineage.py:49-56` · `:76`).
- `hidden_root` 는 테스트·도구용 키워드다. 기본값은 저장소 루트의 `data/hidden/simulator`(`DR-S1-world-state`). 오케스트레이션은 넘기지 않는다.
- **절대 돌려주지 않는 것:** Hidden Trait · persona · τ · Potential Outcome · 난수 열쇠 · 상태 내용 · `data/hidden` 아래 경로. 토큰과 `state_id` 는 내용을 담지 않는 식별자다. 구현 시 공개 함수 반환값을 `FORBIDDEN_FIELD_NAMES`(`schema.py:238-248`)로 훑는 테스트를 둔다.
- **열지 않는 것:** `_internal` 전부, 하루 단위 `step()`, 고객 단위 조회, 시드 재설정, 난수 접근. `src/simulator/__init__.py` 는 `api` 만 다시 내보낸다.
- **네임스페이스 (2026-10-04 리뷰 반영 — Thomas M3).** `api` 는 `__all__` 로 계약 이름(예외 7종 · `RunSummary` · 함수 11개)만 공개하고, 내부 모듈과 표준 라이브러리는 밑줄 별칭(`_runtime`·`_wd`·`_storage` 등)으로만 import 한다(`src/simulator/api.py:9-58`). 초안의 `api.runtime.active.world` 같은 공개 속성 경로(Hidden Trait 자리까지 닿는다)를 없앤 것이다.
- **profile.** S1 은 `docs/data_spec.html:182-188` 의 이름(`smoke`·`short`·`reference`·`long`·`rolling`)만 받고 모르는 이름은 `ValueError`. S1 에서 profile 이 정하는 것은 `calendar_start`(전부 2025-01-01)와 기록용 이름뿐이다 — 창 길이는 호출자가 `advance(days)` 로 정한다. profile 표는 코드 상수로 둔다(YAML 의존 회피).
- **이벤트 메타.** 모든 이벤트에 `simulator_version`·`random_seed`(=`seed`)를 싣는다 — 출처 판별(`MEA-002`, `sink.py:97-101`). `simulator_version` 값은 측정 계약의 표기 `sim-{major}.{minor}`(`docs/measurement_contract.md:197`)를 따라 `sim-0.1` 이다(2026-10-04 리뷰 반영 — Thomas M4, 초안 구현값 `sim-s1-0.1.0`). `service_version`·`customer_version` 값은 이 DR 에서 정하지 않는다(남은 불확실성).
- **CLI** — `python -m src.simulator`:
  - `init --seed --customers --profile --output-root [--days N]` — 세계를 만들고(선택적으로 N 일 진행) 상태를 저장, `state_id` 를 출력
  - `advance --output-root --days N` — 그 루트의 계보 머리 상태를 불러 N 일 진행하고 저장
  - `resume --state-id --output-root --days N` — 지정한 상태를 불러 진행하고 저장
  - 세 명령 모두 `--hidden-root` 를 받는다 — **테스트·도구 전용**이며 운영 실행은 쓰지 않는다(API 의 `hidden_root` 키워드와 같은 뜻).
  - 종료 코드: 성공 `0`, 시뮬레이터 오류(`SimulatorError` 계열) `1`, 인자 오류(`TypeError`·`ValueError`) `2`. argparse 가 인자 해석 단계에서 거부하는 경우도 argparse 기본값으로 `2` 다. 성공하면 저장한 `state_id` 를 표준 출력에, 실패 메시지는 표준 오류에 낸다 (`src/simulator/__main__.py:12-14` · `:67-89`).
  - `docs/simulator_api.md` 에 **CLI 절이 있다**(`:112` 이하, 2026-10-04 리뷰 반영 — 앞선 기록의 "CLI 절이 없다"를 고친다). D9 는 API 만 써도 되지만, 계약 문서만으로 CLI 를 검증할 수 있어야 한다(Matthias D-3). 중단된 쓰기 흔적이 남은 루트는 `advance`·`resume` 모두 종료 코드 1 로 거부하고, 복구는 마지막으로 성공한 `state_id` 로 새 빈 루트에 `resume` 한다.
- **테스트 방침.** 시뮬레이터 팀 소유 테스트(`tests/test_simulator_*.py`)가 `src.simulator._internal` 을 직접 import 하는 것은 화이트박스 검증으로 허용한다 — import 금지 대상은 `src.orchestration` 이다(`tests/test_isolation.py:27`).
- **D9 루프 예시** (`docs/simulator_api.md` 에 이 형태로 싣는다. 경로 문자열은 오케스트레이션이 정하며 `data/hidden` 을 쓰지 않는다)

```python
from src.simulator import api as sim

sim.init(seed=42, num_customers=26000, profile="rolling", output_root=main_root)
sim.advance(warmup_days)
for T0 in campaign_index_dates:
    state_id = sim.save_state()            # 본선 재개용 (파일)
    snap = sim.snapshot()                  # 전략 분기용 (메모리 토큰)
    features = build_features(sim.events(until=feature_cutoff(T0)))
    for strategy in strategies:
        sim.restore(snap, output_root=new_empty_root(T0, strategy))
        sim.apply_treatment(strategy.select(features, budget=C_rule))
        sim.advance(label_window_days)
        report(T0, strategy, sim.metrics(T0, T0 + timedelta(days=label_window_days)))
    sim.discard_snapshot(snap)
    sim.load_state(state_id, main_root)    # 본선 루트의 계보 머리가 이 상태에서 끝났으므로 통과
    sim.advance(campaign_interval_days)
```

- 문서 정정(후속, 리드 몫): `src/orchestration/AGENTS.md:15-27`, `src/simulator/AGENTS.md:33-36`, `docs/data_spec.html:880-892`, `docs/TEAM_SETUP.md:178-185`(`docs/simulator_api.md` 를 가리키도록).

**근거:** 형태·본선 이어가기·계약 공개 위치는 사용자 결정이다. 핸들 ⓑ 와 ㉡ 은 두 가지 강제 규칙에서 나온다 — 숨김 값을 어떤 외부에도 돌려주지 않는다(`_internal/AGENTS.md:8`), 오케스트레이션 소스는 숨김 경로를 쓸 수 없다(`test_isolation.py:34`). 핸들이 객체면 첫째가, 경로를 호출자가 정하면 둘째가 깨진다. `discard_snapshot` 은 리드 초기 목록에 없던 추가다 — D9 루프가 T0 마다 스냅샷을 하나씩 만들면 레지스트리가 계속 자라기 때문이다. 계약을 별도 문서로 내는 것은 시스템 팀이 `src/simulator/**`(`api.py` 포함)를 읽지 않기 때문이고(`docs/TEAM_SETUP.md:62`), 행동 규칙을 빼는 것은 그 문서가 수험생에게 출제 방식을 알려 주지 않게 하기 위해서다.

## 기각한 안과 기각 사유

| 안 | 왜 택하지 않았나 |
|---|---|
| ② 클래스 인스턴스 | 사용자 결정 1. 인스턴스 속성 경로로 숨김 상태가 드러난다 |
| ⓐ 상태 객체 핸들 | 호출자 손에 Hidden Trait 이 담긴 객체가 들어간다 |
| ㉠ `save_state(path)` · `load_state(path, …)` (리드 초기 권고) | D9 가 `data/hidden` 경로를 소스에 쓸 수 없어(`test_isolation.py:34`) 숨김 정보가 담긴 상태 파일을 `data/hidden` 밖에 두게 된다 |
| 실패를 상태값으로 | 이슈 #91 의 "저장 실패 시 진행 거부"를 호출자 규율에 맡기게 된다 |
| `metrics` 에 지금 비즈니스 지표 | S1 에는 근거 이벤트(구매)가 없다. 내면 0 이나 추정값이 된다. 나중에 들어갈 때도 측정 계층 KPI 를 불러 계산하고 정의를 다시 만들지 않는다 |
| 유형별 건수를 16종 전부 `ok` 로 | S1 이 만들지 못하는 `purchase` 의 0 이 "구매가 없었다"는 측정값처럼 읽힌다 |
| `exchange_bundle` 을 S4 에서 추가 | 사용자 결정 5. D9 가 지금부터 자리를 알고 스텁을 짤 수 있다 |
| profile 을 YAML 로 | 격리 CI 에 PyYAML 이 없다(`requirements.txt:11-16`) |
| 본선을 `restore(snap)` 으로 원래 루트에 이어 쓰기 | 사용자 결정 3 — `restore` 뒤 쓰기는 빈 경로만. 같은 목적을 `load_state` 가 이어쓰기 검사와 함께 한다 |
| 커머스·시뮬레이터 이벤트를 한 Sink 루트에 | 리드 기본값으로 확정(2026-10-04). 커머스 실행 기록이 같은 `runs/` 사슬에 끼어 계보 머리 대조가 성립하지 않는다 |
| 계약을 `docs/TEAM_SETUP.md` §4 에만 | 사용자 결정 7. 팀 착수 지침과 계약의 수명이 달라 한쪽이 낡는다 |
| 계약 문서에 행동 규칙(장바구니 30일 등)도 | 사용자 결정 7·8. 출제자 내부 규칙이 수험생 문서로 새어 나간다 |
| 계약 문서에서 CLI 를 빼 둠 (앞선 기록) | 2026-10-04 리뷰 반영(사용자 확인 2026-10-04). 계약 문서만으로 CLI 의 종료 코드·운용 제약을 검증할 수 없었다(Matthias D-3) |
| 내부 모듈을 `api` 의 공개 속성으로 import | Thomas M3 — `api.runtime.active.world` 로 Hidden Trait 자리까지 닿는다. 클래스 인스턴스를 기각한 이유와 같은 종류의 경로다 |
| pyarrow 없는 런타임에서 `ModuleNotFoundError` 를 그대로 흘림 | Matthias D-1 — 계약 예외 목록 밖의 예외다. `SinkFormatError` 로 미리 거부한다 |

### 정정 (2026-10-04, 리뷰 반영)

- **바뀐 결정:** 사용자 결정 7 의 계약 문서 범위 — "함수 · 인자 · 예외 · D9 루프 예시**뿐**"에 CLI 절을 더했다(리드 제안, 사용자 확인 2026-10-04 — 명령 3종·인자·종료 코드 0/1/2·운용 제약. 계기는 Matthias D-3). 행동 규칙 제외는 그대로다.
- **더한 것(결정의 구체화):** `SinkFormatError`, 쓰기 전 fail-closed, `events()`·`metrics()` 의 사슬 검증, `StateFormatError` 범위 확대, `__all__`·밑줄 별칭, `simulator_version = "sim-0.1"`, `MAX_TIME_MS`.
- **번복 판단.** 결정 7 의 문구("뿐")가 바뀌었으므로 `docs/DECISION_RECORDS.md:107` 의 "결정이 바뀌면 번복"에 해당한다고 보고 헤더를 `번복 (부분)` 으로 적었다. 저장소에 `번복` 선례는 없고, `DR-101-revenue-basis.md:7` 의 "확정 · 날짜 · 정정" 헤더와 「개정 이력」 형식을 빌렸다. 결정 7 은 사용자 결정이었으므로 이 변경도 **사용자가 확인했다(2026-10-04)** — 리드 결정으로 먼저 전달될 때 남겨 둔 "사용자 확인 필요" 단서는 해소됐다. 사용자 결정 자체가 바뀌었으므로 헤더의 `번복 (부분)` 은 유지한다.

## 이 결정이 틀렸다면 어떻게 드러나나

- D9 가 이 표면만으로 루프(초기화 → 진행 → 스냅샷 → 분기별 처치·진행 → 지표 → 저장 → 재개)를 짤 수 없어 `_internal` 이나 `data/hidden` 을 건드려야 한다 → 표면이 좁다. D9 의 요청이 그 증거가 된다.
- 공개 함수 반환값 검사에서 금지 필드명이 나온다 → 표면이 숨김 정보를 흘린다.
- `docs/simulator_api.md` 의 시그니처와 `api.py` 가 어긋난다 → 구현 때 두 쪽을 맞대는 테스트(공개 함수 이름·인자 목록 대조)를 둔다. 없으면 선언에 대조 장치가 없는 것이다(`docs/TEAM_SETUP.md:268`).
- `docs/simulator_api.md` 에 행동 규칙(만료 기간·확률·분포)이 들어간다 → 결정 7 위반. 리뷰가 잡는다.
- `metrics` 결과에 `not_run` 이 아닌 0 이 근거 없이 나온다 → 결손을 0 으로 채웠다.
- `restore` 후 기존 루트에 이벤트가 덧붙는다 → 사용자 결정 3 위반. 시험으로 막는다.

## 민감도

- 함수 하나를 더 열 때마다 시스템 팀이 의존할 계약이 하나 는다. 지금 표면은 11개(리드 목록 10 + `discard_snapshot`)다.
- 스냅샷 메모리는 상태 크기 × 동시에 든 토큰 수다. 상태 크기는 아직 재지 않았다(`DR-S1-world-state` 민감도). D9 가 T0 마다 `discard_snapshot` 을 부르면 동시 토큰은 1~2개다.
- `events(until)` 은 디스크에서 다시 읽는다. S3 규모(1,200만 건)에서 한 번 읽는 비용을 아직 재지 않았다.

## 남은 불확실성

- **네임스페이스는 완전히 막히지 않는다.** 파이썬에서 모듈 속성 접근을 완전 차단할 수 없어 `api._runtime` 경로가 남는다. orchestration 소스의 `api._*` 속성 접근을 금지하는 AST 검사는 시스템 팀 경로 규칙과 얽혀 있어 리드와 합의할 **후속 후보**다.
- **M6 — 비용 미측정.** 리뷰 반영 3차로 `advance` 도 매번 계보 전체를 다시 해시한다(쓰기 관문) — S3 규모는 재지 않았다. `events()`·`metrics()` 는 매번 전체를 다시 읽고 사슬을 검증한다. S3 규모 비용은 재지 않았다.
- 시스템 팀이 `docs/decisions/DR-S1-*` 을 읽지 않는다는 규칙을 `docs/TEAM_SETUP.md` §2 에 명시할지는 리드가 정한다 — 이 DR 들에는 장바구니 30일 같은 내부 규칙이 있다.
- `apply_treatment` 가 실험 ID·캠페인 ID·집행 시각(09:00)을 받아야 하는지 — S5·S6 이 정한다. 그때 시그니처가 늘면 D9 가 따라 바뀐다.
- 비즈니스 지표를 `metrics` 가 언제부터 무엇으로 계산하나 — 측정 계층 KPI 를 부르는 방식으로 S4 이후 정한다.
- `service_version`·`customer_version` 에 시뮬레이터가 무엇을 싣나.
