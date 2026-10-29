# DR-183-experiment-config — 실험 config 경로와 Small 5,000명 프리셋 (#183 ②·③)

| | |
|---|---|
| 태스크 | #183 ② 실험 config 경로 · `CONFIG_PINS` 마찰, ③ Small 5,000명/6개월 프리셋(FR-04 · SIM-003) |
| 작성 | 시뮬레이터 팀 성환(limtjdghks) · Claude(Phillip 구현) · 2026-10-28 |
| 상태 | 확정 — 구현 범위는 사용자 승인 계획(2026-10-28) |

## 무엇을 정하는가

(②) 생성 config 의 값 하나를 바꿔 실험할 때 정본 파일을 고치지 않고 다른 파일을 지정하는 방법과, 그 상태를 이어갈 때의 결속 규칙. (③) FR-04 "Small Mode는 5,000명 / 6개월로 실행할 수 있어야 한다" 를 무엇으로 충족할지.

## 정하지 않으면 무엇이 막히나

- ②: 보정 실험(#183 ⑤ 등)마다 정본 config 를 고치면 판 상향·`CONFIG_PINS` 영구 기록·골든 재고정이 실험 수만큼 생긴다. 실험이 끝나야 판을 한 번 올리는 흐름이 불가능하다.
- ③: `small` 프로파일은 시간축만 정하고 고객 수는 문서로만 안내했다(`DR-S3-p6-signup` U11 단점) — CLI 로 "Small Mode" 를 실행할 수단이 없다.

## 선택지

| 안 | 내용 | 장점 | 단점 |
|---|---|---|---|
| ②-A | 전역 활성 config 하나를 유지하고 `init`·`load_state` 가 고를 수 있게(`genconfig.switch(path, action)` — 선택과 세계 교체를 함께 확정하거나 함께 취소) | `world`·`params` 가 `genconfig.active()` 를 그대로 쓴다. 기본 경로 동작은 그대로다 | 활성 세계가 있는 동안 config 는 하나뿐이다 |
| ②-B | config 객체를 모든 호출에 인자로 넘김 | 전역 상태가 없다 | `world`·`params`·`engine`·`treatment`·`lineage` 전부를 바꿔야 한다 |
| ③-A | API 는 그대로, CLI `init`·`guardrails` 에서 `--customers` 생략 시 프로파일 기본 고객 수(`small` = 5,000) | `DR-S3-p6-signup` S-c 기각(API 변경 회피)을 지킨다 | API 호출자는 여전히 고객 수를 넘긴다 |
| ③-B | 프로파일이 고객 수를 강제(S-c) | 이름만으로 규모가 정해진다 | API 변경 — 이미 기각한 안 |

## 조사한 것

| 출처 | 무엇을 말하나 | 우리 맥락에 얼마나 맞나 |
|---|---|---|
| `src/simulator/_internal/genconfig.py`(변경 전) | `active()` 가 고정 경로를 한 번 읽어 프로세스 전역에 캐시, "프로세스 수명 동안 불변" | ② 마찰의 원인 |
| `world.py:95-111` | `world_id` 에 config 다이제스트, 상태에 `generation` | 다른 config 로 이어가는 것은 이미 거부된다 — 결속을 새로 만들 필요가 없다 |
| `tests/test_simulator_persona.py` `CONFIG_PINS` | 판 이름 ↔ 다이제스트 영구 기록 | 실험 파일까지 핀 대상이면 실험마다 판이 생긴다 |
| PRD FR-04(`:2494-2497`) · §24(`:990-1012`) · SRS SIM-003(`:529-545`) | Small = 5,000명 / 6개월, "과제 제출 런의 하한" | 6개월은 하한 |
| `DR-S3-sample-size` U3·U4(`:89-90`) · `DR-S3-p6-signup` U11·S-c(`:40-42`) | small = 5,000명 × short 시간축(275일), 6개월은 하한. S-c 기각 | 시간축을 바꾸지 않는 근거 |
| 시스템 팀 #184 `experiment_config`(NFR-06, `docs/sprint_plan.md:124`) | 실험 설정은 시스템 팀 범위 | ② 는 시뮬레이터 생성 config 에 한정한다 |

## 결정

**②-A + ③-A.**

- ②: API `init(..., config_path=None)`·`load_state(..., config_path=None)`, CLI `init`·`advance`·`resume`·`guardrails` 의 `--config`. 생략하면 기본 경로이고 기본 파일은 지금처럼 프로세스에서 한 번만 읽는다. 실험 파일은 고를 때마다 다시 읽는다 — 같은 경로를 덮어쓰며 실험해도 옛 값으로 돌지 않는다(다이제스트로 캐시를 재사용하지 않는 이유: 다이제스트 밖 블록 `guardrails`·`churn` 변경이 묻힌다).
- 선택은 트랜잭션 함수 `genconfig.switch(path, action)` 이 한다 — 설정을 바꾸고 `action`(세계 생성·불러오기)을 부르며, 성공하면 유지하고 예외면 이전 선택으로 되돌린다. 처음 구현한 `with selected(...)` 는 정상 종료 시 복원하지 않아 계약이 놀라웠다(리뷰 지적) — "정상 종료 시 복원 + 명시 확정" 두 단계는 확정을 빠뜨리면 세계와 설정이 어긋나 기각했다.
- 다른 config 의 상태를 이어가면 `StateFormatError` — 생성 설정(generation)이 다를 때만(`world.GenerationMismatch`) 판 이름·다이제스트 앞 12자를 싣고 "이 상태를 만든 설정 파일을 다시 지정한다(API config_path · CLI --config)" 고 안내한다. 형식·판(`format_version`·`simulator_version`)이 다른 상태에는 따를 수 없는 안내라 붙이지 않는다.
- 공개 오류 메시지는 실험 파일 경로 대신 고정 문구 "지정한 실험 설정 파일" 과 판 이름·다이제스트 앞 12자를 싣는다 — 파일 이름이 숨은 Trait 이름을 실어 나를 수 있다. 경로는 원인 예외(`__cause__`)에만 남는다. isolation 탐침이 Trait 이름이 든 파일 이름으로 확인한다.
- `CONFIG_PINS` 는 기본 경로 파일에만 적용한다. 실험 파일은 판 이름이 같아도 받는다 — 구분은 다이제스트 결속이 한다.
- 실험 config 는 시뮬레이터 팀 실험 전용이다. 오케스트레이션의 정본 실행은 넘기지 않고, 실험 결과를 정본 결과로 쓰지 않는다(`docs/simulator_api.md`).
- ③: `profiles.py` `_DEFAULT_CUSTOMERS = {"small": 5_000}`(SSOT). CLI 에서 `--customers` 를 생략하면 이 값, 기본값이 없는 프로파일이면 인자 오류(종료 2). API `num_customers` 는 필수 그대로. 시간축 275일 그대로.

**근거:** 상태 결속이 이미 다이제스트로 있어 ②-A 는 "고르는 길" 하나만 더하면 된다. ③-A 는 이미 기각한 S-c 를 다시 열지 않고 FR-04 를 CLI 로 실행 가능하게 한다.

## 기각한 안과 기각 사유

| 안 | 왜 택하지 않았나 |
|---|---|
| ②-B | 시뮬레이터 내부 5개 모듈 변경 — 범위 대비 위험이 크다 |
| 상태·사이드카에 config 경로 기록 | `lineage.py` 검증과 엮인다. 다이제스트만으로도 "다른 설정" 은 정확히 잡힌다 |
| 실험 파일도 핀 대상 | 실험마다 판이 영구 기록돼 ② 의 목적이 사라진다 |
| ③-B | `DR-S3-p6-signup` S-c 기각(API 변경) |
| 시간축을 6개월(약 183일)로 | warmup ≥ 180일 + 라벨 42일과 양립하지 않는다(`DR-S3-sample-size:41`) |

## 이 결정이 틀렸다면 어떻게 드러나나

- 기본 경로 실행의 이벤트·상태 다이제스트가 이 변경 전과 다르면 "생략 = 기본" 이 깨진 것이다(골든 테스트).
- 실험 config 로 만든 상태가 `--config` 없이 이어지면 결속이 깨진 것이다(`tests/test_simulator_cli.py`).
- `small` 5,000명 × 275일 실행이 몇 분 안에 끝나지 않으면(`DR-S3-sample-size:108` 반증 조건) 프리셋을 다시 본다 — 실측은 #183 ⑥ 증거 문서.

## 민감도

기본 고객 수 5,000 은 요구 원문 값이다 — 바꾸면 FR-04 를 어긴다. `--config` 는 값이 아니라 경로라 민감도 대상이 아니다.

## 남은 불확실성

- `docs/persona_spec.md` 에 실험 config 를 적을지는 정하지 않았다.
- 시스템 팀 #184 의 `experiment_config` 와 이름이 비슷해 혼동될 수 있다 — 문서에 범위를 적었다.
