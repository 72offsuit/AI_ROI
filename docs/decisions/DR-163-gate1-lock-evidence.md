# DR-163-gate1-lock-evidence — 시뮬레이터 Lock 5종은 서명 때 증거로 LOCKED 를 정하고, 검증·게시는 서명 기록의 상태를 쓴다

| | |
|---|---|
| 태스크 | 리드 · #163 (GATE 1 봉인, 실측 #208 전 병합) |
| 작성 | Phillip(에이전트 구현) · 2026-11-09 |
| 상태 | 확정 — 설계 3항은 사용자 결정(2026-11-09). 예외/상태 유지의 경계는 구현 판단(아래 "결정") |

## 무엇을 정하는가

GATE 1 서명(`freeze.record()`)에서 시뮬레이터 Lock 5종(`CUSTOMER_PERSONA_v1` · `HIDDEN_TRAIT_RULE_v1` · `BEHAVIOR_RULE_v1` · `TREATMENT_RESPONSE_v1` · `CHURN_DEFINITION_v1`)을 `LOCKED` 로 기록하는 조건과 정본, 그리고 기록된 상태를 검증·게시가 어디서 읽는가.

## 정하지 않으면 무엇이 막히나

- **5종을 `LOCKED` 로 기록할 길이 없다.** `freeze._LOCK_ROWS` 가 시뮬레이터 4종을 `OUT_OF_SCOPE`, CHURN 을 `PARTIAL` 로 하드코딩했고, `record()` 는 `verification.items`(= 그 상수)를 그대로 썼고 `simulator_commit` 인자가 없었다. 민정의 독립 검증(§5.1 ④ "Lock 5종이 LOCKED 로 기록 가능한지")과 성환의 서명이 막힌다.
- **상수만 바꾸면 서명 전에 게시물이 `LOCKED` 로 나온다.** `publish.build_freeze_status()` 와 테스트가 항목 상태를 서명 기록이 아니라 코드 `gate1_lock_items()` 에서 읽었다.
- **계약과 어긋난다.** `freeze_status.schema.json` 은 `LOCKED` 항목에 객체 배열 `canonical_files[{path, verification, locked_sha256?, current_sha256?}]` 를 요구하는데, `to_artifact()` 는 문자열 목록을 냈다. 지금까지 `LOCKED` 가 0종이라 드러나지 않았다.

## 선택지

**축 1 — 상태를 어디서 정하나**

| 안 | 내용 | 장점 | 단점 |
|---|---|---|---|
| A | `_LOCK_ROWS` 상수를 `LOCKED` 로 바꾼다 | 가장 작다 | 서명 전에도 게시물이 `LOCKED`. 증거 없이 봉인된다 |
| B | `record()` 가 증거를 받아 서명 때 정하고, 검증·게시는 기록의 상태를 쓴다 | 서명한 것만 `LOCKED`. 기록이 정본 | `gate1_lock_items` 가 기록을 읽어야 한다 |

**축 2 — 증거가 없을 때**

| 안 | 내용 | 장점 | 단점 |
|---|---|---|---|
| 2a | 예외 | 실수로 빠뜨린 것을 즉시 안다 | 증거 없는 재서명(측정 정본 재기록, #256 같은 경우)이 불가능해진다 |
| 2b | 기본 상태 유지 | 지금 기록과 같은 재서명이 된다 | 증거를 빠뜨린 서명자가 모를 수 있다 |
| 2c | **없음은 기본 상태 유지, 쓸 수 없는 증거는 예외** | 두 경우를 가른다 | 규칙이 하나 늘어난다 |

## 조사한 것

| 출처 | 무엇을 말하나 | 우리 맥락에 얼마나 맞나 |
|---|---|---|
| `src/measurement/freeze.py`(main `ab629e3`) `_LOCK_ROWS` · `gate1_lock_items()` · `build_record()` · `record()` | 위 "막히나" 의 세 가지. `build_record` 가 `declaration` 을 `PARTIAL_FREEZE` 로 고정 | 직접 원인 |
| `src/measurement/publish.py` `build_freeze_status()` | `fz.gate1_lock_items()` 를 인자 없이 부른다 | 축 1 A 를 기각하는 근거 |
| `docs/contracts/measurement-publish/v1/freeze_status.schema.json` `items.allOf[0]` | `status: LOCKED` 이면 `canonical_files` 필수. 원소는 `path` · `verification` 필수, 해시는 `null` 허용 | 계약을 고치지 않고 코드를 맞췄다 |
| `tests/test_freeze.py` `TestThreeLayersAgree` (AC-4) | 탐지 3층이 같은 함수를 쓴다 | `gate1_lock_items(record)` 하나로 모았다 |
| `record()` 의 기존 거부 관례 | 선행 조건 미충족 · 자리 표시 `locked_by` 는 `FreezeViolation`. `simulator_commit` · `repo_commit` 을 모르면 `null` + 사유 | "모름은 값, 거짓은 예외" — 축 2c 의 근거 |
| `config/gate1_lock.yaml` (2026-11-05, Danto7632) | 9종 상태가 코드 기본값과 같다. `simulator_commit: null` | 게시 결과 불변을 테스트로 고정할 수 있다 |
| `docs/data_spec.html` §5.1 · `DR-183-churn-config.md` | 임계값 28/42/60 확정은 ①~④ 실측이 필요하다. 임계값은 `config/simulator_config.yaml` `churn` 블록에 있고 GATE 1 해시 대상이 아니었다 | CHURN 정본에 `simulator_config.yaml` 을 넣는 근거. ④ 가 재생성 결과라 `simulator_commit` 도 요구한다 |
| `src/diagnostics/report.py` `gate1_status` (읽기만) | `experiment_environment_v1_declared` · declaration≠PARTIAL · `simulator_commit` 을 요구한다 | 이번에 바꾸지 않는다. 유도 규칙이 이 판정과 같은 방향이다 |
| `tests/test_isolation.py` `TestHiddenNameConfinement` | 측정 계층 문자열에 Hidden 블록 이름이 나오면 실패 | scope_note 에 config 블록 이름을 쓰지 않았다 |

## 결정

**축 1 B + 축 2 2c.** 측정 3종(EVENT · ECONOMIC · KPI)은 바꾸지 않는다(리드 결정).

- `_LOCK_ROWS` 는 **서명 전 기본 상태**로 남는다. 5종의 `LOCKED` 목표(owner_part · scope_note)는 `_LOCK_TARGETS` 에 두고, 정본은 `SIMULATOR_CANONICAL_FILE = config/simulator_config.yaml` 이다.
- `record(..., simulator_commit=None, churn_evidence=None)` 가 `lock_items_at_signing()` 으로 항목을 정한다. 기본값에서 출발하고 **이전 기록의 `LOCKED` 를 이어받지 않는다.**

| 넘긴 것 | 결과 |
|---|---|
| 없음 | 기본값(시뮬레이터 4종 `OUT_OF_SCOPE` · CHURN `PARTIAL`). 예외 아님 |
| `simulator_commit`(40자 소문자 sha) | 시뮬레이터 4종 `LOCKED` |
| + `ChurnThresholdEvidence(met=True, evidence=…)` | CHURN 도 `LOCKED`. 근거가 `churn_threshold_evidence` 로 기록된다 |
| `met=False` | CHURN `PARTIAL`. 미충족 근거도 기록된다 |
| 40자 sha 가 아닌 값 · sha 없이 `met=True` · 빈 근거 | `FreezeViolation`(근거는 `ValueError`) — 기록을 쓰지 않는다 |

- `build_record()` 도 같은 불변식을 지킨다: 시뮬레이터 항목 `LOCKED` 인데 `simulator_commit` 없음, CHURN `LOCKED` 인데 충족 증거 없음, `LOCKED` 정본 파일 부재 → `FreezeViolation`. `LockItem` 은 `LOCKED` 에 `canonical_files` 가 없으면 만들어지지 않는다.
- `LOCKED` 항목의 정본은 기록 `canonical_files` 해시에 자동으로 들어가고, 항목에도 `canonical_files: [경로]` 가 남는다.
- `gate1_lock_items(record)` — 읽을 수 있는 기록이면 그 상태, `None` · `RECORD_UNREADABLE` 이면 기본값. 기록 `items` 가 깨졌으면 `ConfigError`. `verify()` · `publish.build_freeze_status()` · 테스트가 이것 하나를 쓴다.
- **읽을 때도 같은 규칙으로 검사한다** (리뷰 중요-2). `gate1_lock_items(record)` 가 기록의 `simulator_commit` · `churn_threshold_evidence` 를 `recorded_signing_evidence()` 로 읽어 쓰기 경로와 같은 `_check_lock_evidence()` 에 넣고, `declaration` · `experiment_environment_v1_declared` 가 항목에서 유도한 값과 같은지 본다. 어긋나면 `ConfigError` 다. 현재 `config/gate1_lock.yaml`(LOCKED 0종 · PARTIAL_FREEZE · `simulator_commit: null`)은 통과한다.
- `verify()` 는 `LOCKED` 항목 정본의 해시가 기록에 없으면 불일치로 센다. 게시물 항목별 `canonical_files[]` 는 `verify()` 가 잰 해시를 싣는다.
- **declaration 은 인자가 아니라 유도한다.** `SERVICE_v1` 을 뺀 8종이 전부 `LOCKED` 일 때만 `FULL_FREEZE` + `experiment_environment_v1_declared: true`. 게시 `overall: sealed` 도 같은 함수(`_all_lockable_locked`)다. 측정 3종이 `LOCKED` 가 아니므로 지금은 `PARTIAL_FREEZE` 다.

**근거:** 봉인은 서명자가 증거를 들고 하는 행위이고, 상수는 증거를 담지 못한다(A 기각). 이 모듈은 이미 "모르면 `null` + 사유, 거짓 값이면 거부" 로 나눈다 — 증거가 없는 것은 모르는 것이고, 자리 표시 sha 나 커밋 없는 실측은 거짓 값이다. 증거 없는 재서명은 측정 정본이 바뀔 때마다 필요하므로(#256) 막으면 안 된다.

## 기각한 안과 기각 사유

| 안 | 왜 택하지 않았나 |
|---|---|
| A 상수를 `LOCKED` 로 | 서명 전에 게시물이 `LOCKED`. 증거 없는 봉인 |
| 2a 증거 없으면 예외 | 측정 쪽 재서명이 시뮬레이터 실측을 기다려야 한다 |
| 2b 쓸 수 없는 증거도 조용히 기본값 | 서명자가 `LOCKED` 를 기대한 채 `PARTIAL` 기록을 커밋한다 |
| 이전 기록의 `LOCKED` 를 이어받음 | 재서명에 증거가 없으면 `simulator_commit: null` 인 기록에 `LOCKED` 시뮬레이터 항목이 남는다 |
| CHURN 은 §5.1 증거만 요구 | ④ 는 특정 시뮬레이터의 재생성 결과다. 커밋이 없으면 증거를 재현할 수 없다 |
| `declaration` 인자 추가 | 받으면 누군가 `FULL_FREEZE` 를 전달한다 (기존 `test_declaration_is_not_parameterised`) |
| `overall: sealed` 를 9종 전부 `LOCKED` 로 유지 | `SERVICE_v1` 은 이 저장소가 봉인할 수 없어 `FULL_FREEZE` 기록이 화면에서 영원히 `partial` 이 된다 |
| `verify()` 에서 `simulator_commit` 대조 | 사용자 결정으로 이번 범위 밖 |

## 이 결정이 틀렸다면 어떻게 드러나나

- 증거 없이 서명했는데 기록에 `LOCKED` 시뮬레이터 항목이 있다 → `TestRecordWritesEvidence` · `TestSigningItemsFollowEvidence` 가 잡는다.
- 게시 항목이 기록의 증거로 다시 계산한 항목과 다르다 → `test_current_record_publishes_the_items_its_evidence_signs`. 증거 없는 지금 기록이면 코드 기본값과도 같아야 한다(#163 전후 게시 불변). 처음 판은 "현재 기록 = 코드 기본값" 을 단언해 정상 서명 뒤 CI 가 실패했다(리뷰 중요-1). 지금은 5종 LOCKED 기록을 주입한 회귀 테스트 2건(`test_*_parity_holds_for_a_five_locked_record`)이 막는다.
- 손으로 고친 기록(증거 없는 LOCKED, 선언 불일치)이 게시된다 → `TestRecordedInvariantsAreChecked`.
- 서명된 `LOCKED` 가 게시물에 안 나오거나 계약을 통과하지 못한다 → `test_signed_record_reaches_the_publication` · `test_locked_publication_passes_the_contract`.
- 서명 뒤 `config/simulator_config.yaml` 이 바뀌었는데 `violated` 가 아니다 → `test_changed_simulator_config_is_a_per_item_mismatch`.
- 민정의 독립 검증에서 실측 근거를 `evidence` 문자열로 담기에 부족하다고 판단되면 증거 형식이 틀린 것이다.

## 민감도

- 시뮬레이터 정본이 `simulator_config.yaml` **한 파일**이다. `notes` 같은 설명 문구만 고쳐도 5종 전부 `mismatch` 가 된다 — 거짓 경보 쪽으로 기운다. 블록 단위 해시로 줄일 수 있지만 측정 계층이 Hidden 블록을 열어야 해서 택하지 않았다.
- `simulator_commit` 은 `src/simulator` 마지막 커밋이라 관련 없는 시뮬레이터 커밋도 값을 바꾼다. 대조를 붙이면(후속) 같은 이유로 거짓 경보가 난다.
- 유도 규칙의 면제 집합(`DECLARATION_EXEMPT_ITEMS` = `SERVICE_v1`)을 늘리면 `FULL_FREEZE` 가 쉬워진다. 이 집합이 `EXPERIMENT_ENVIRONMENT_v1` 선언을 직접 정한다.

## 남은 불확실성

- **`verify()` 는 `simulator_commit` 을 현재 코드와 대조하지 않는다** (사용자 결정, 후속). 그때까지 `src/simulator` 코드 변경은 봉인 대조에 걸리지 않고, 실행 기록 `run_meta.provenance.simulator_commit`(DR-262)과 사람의 비교로만 드러난다.
- **PyYAML 이 없는 환경**(`isolation.yml`)에서는 기록을 읽지 못해 게시 항목이 기본값으로 나온다. 서명 뒤에는 기록(`LOCKED`)과 다를 수 있다. 그때 `verification` 은 `not_run` 이라 대조하지 않았다는 사실은 드러나지만 항목 상태는 서명 전 값이다.
- **CHURN 증거 형식**은 `met` + 자유 문장이다. §5.1 ①~④ 각각의 수치(P75 · P90 · 이탈률)를 구조로 받을지는 실측(#208) 뒤 민정 검증에서 정한다.
- `src/diagnostics/report.py` 의 `gate1_status` 는 바꾸지 않았다. 측정 3종이 `LOCKED` 가 되기 전까지 `FULL_FREEZE` 가 나오지 않으므로 지금은 영향이 없다.
- 측정 3종의 `LOCKED` 조건과 정본은 리드 결정으로 남아 있다.
- **9종 · 선언 · 증거를 모두 일관되게 위조한 기록은 읽기 검사로 잡지 못한다.** 게시물 `lock_record.sha256` 과 리뷰가 막는다.
- **리뷰에서 지적됐지만 이번에 고치지 않은 것** (사용자 지시로 범위 밖, 2026-11-09):
  - 증거 없이 다시 서명하면 이전 기록의 LOCKED 가 경고 없이 기본 상태로 돌아간다 (code-reviewer Medium-2 · Thomas 사소-1).
  - CHURN 이 `met=False` 로 PARTIAL 일 때 scope_note 가 기본 문구 그대로라 미충족 사실은 `churn_threshold_evidence` 에만 남는다.
  - `verify()` mismatch `detail` 이 "봉인 이후 변경됐다" 로 고정돼, 기록에 해시가 없는 경우까지 같은 문장으로 나온다.
- **범위 밖 테스트 수정 1건.** `tests/test_freeze_mismatch_alarm.py` `test_no_undefined_names_remain` 의 AST 검사가 `except E as name` 의 이름(`ast.ExceptHandler.name`, 문자열)을 정의로 세지 않아 `freeze.py` 의 `except … as error` 를 정의되지 않은 이름으로 오탐했다. 그 분기 하나를 더했다. 검사 의도(미정의 이름 탐지)는 그대로다.
