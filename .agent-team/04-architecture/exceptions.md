# 예외 정의

**작성** James (Role 4 · Architect) · 2026-09-11 · 사이클 C1
**정본 근거** SRS `NFR-006`(입력/결과 파일 부재 시 원인과 해결 방법을 명확히 출력) · `MEA-003` · `docs/data_spec.html` §9 · charter 절대제약 4~6

> **이 프로젝트에서 예외 설계의 목적은 견고함이 아니라 정직함이다.**
> 조용히 계속 도는 코드가 조용히 틀린 숫자를 만든다. **어떤 예외를 삼키지 않는가**가 어떤 예외를 던지는가보다 중요하다.

---

# 1. 최상위 규칙 넷

| # | 규칙 | 근거 |
|---|---|---|
| **X-1** | **결손을 기본값으로 대체하지 않는다.** `except: return 0` · `.get(key, 0)` · `or 0` 을 쓰지 않는다 | `MEA-003` · charter 절대제약 6 |
| **X-2** | **예외를 사유 없이 삼키지 않는다.** `except Exception: pass` 는 이 저장소에 없어야 한다 | charter 절대제약 5 |
| **X-3** | **"실행하지 못함"과 "위반"을 다른 타입으로 만든다.** 하나로 묶으면 미실행이 실패로, 또는 실패가 미실행로 읽힌다 | AGENTS.md |
| **X-4** | **복구 가능한 결손은 예외가 아니라 값이다.** `MetricValue(status="unavailable", reason_code=...)` 로 표현한다 | `api-contracts.md` §4 |

## 1.1 X-4 가 가장 자주 틀리는 지점

원가 근거가 없는 주문에서 COGS 를 계산할 수 없는 것은 **예외 상황이 아니라 정상적인 관측 결과**다.
예외로 만들면 호출자가 `try/except` 로 감싸고, 그러다 `except: return 0` 이 생긴다.

```python
# ❌ 예외로 만들면 0 으로 채워지는 경로가 열린다
def cogs(order) -> int:
    if not has_cost_basis(order):
        raise NoCostBasisError(...)

# ✅ 값으로 만들면 계산 불가가 그대로 게시물까지 간다
def cogs(order) -> MetricValue:
    if not has_cost_basis(order):
        return MetricValue.unavailable(ReasonCode.NO_COST_BASIS,
                                       "주문 품목에 unit_cost 값이 없다.")
```

> **판정 기준:** *"이것이 화면에 표시되어야 하는가?"* → 표시되어야 하면 **값**이다. 실행을 계속할 수 없으면 **예외**다.

---

# 2. 예외 계층

```text
MeasurementError (Exception)                     src/measurement/errors.py
├── ContractError            계약 위반 — 코드·데이터가 계약을 어겼다
│   ├── SchemaError             스키마 해석 불가 (알 수 없는 event_type 등)
│   ├── PartitionKeyError       timestamp 를 해석할 수 없다   ← 현재 ValueError
│   └── ContractViolation       산출물이 자기 게시 스키마를 위반했다
├── GateError                게이트 실패 — 진행하면 안 된다
│   ├── QualityGateFailure      data_spec §9 검사 위반        → 종료 2
│   └── FreezeViolation         봉인 해시 불일치              → 종료 3
├── ConfigError              설정을 읽을 수 없다·불완전하다     → 종료 5
├── PublishError             게시 실패 (쓰기·이름 바꾸기)       → 종료 4
└── DependencyMissing        선택 의존성이 없어 요청을 수행할 수 없다
```

**`errors.py` 를 별도 파일로 두는 이유:** `schema.py` 는 아무것도 import 하지 않아야 하는데(`ISO-002` 정신), 예외를 거기 두면 다른 모듈이 `schema` 를 import 하게 된다. `errors.py` 는 표준 라이브러리만 쓰고 **아무도 import 하지 않는 잎 노드**다.

## 2.1 각 예외의 계약

| 예외 | 언제 | 삼켜도 되나 | 어디까지 전파 |
|---|---|---|---|
| `SchemaError` | `EventType` 로 해석 불가 | **아니오** | `validate_event()` 가 **문자열 목록으로 변환**해 돌려준다 — 이 경로에서는 던지지 않는다 |
| `PartitionKeyError` | `timestamp` 해석 불가 | **아니오** | 호출자까지. `sink.py:277-279` 가 이미 그렇게 한다 |
| `ContractViolation` | 산출물이 자기 스키마 위반 | **부분** — 그 산출물만 건너뛴다 | `publish.py` 가 잡아 `index` 에 `status:failed` 로 남기고 `publish_result:partial` |
| `QualityGateFailure` | `gate_result == "fail"` | **아니오** | 최상위. 종료 코드 2 |
| `FreezeViolation` | 해시 불일치 | **게시 경로에서는 잡는다** | 게시는 계속하되 `notices level:failure`. **테스트 경로에서는 잡지 않는다** |
| `ConfigError` | config 부재·파싱 실패·필수 키 없음 | **아니오** | 최상위. 종료 코드 5 |
| `PublishError` | staging·rename 실패 | **아니오** | 최상위. 종료 코드 4 |
| `DependencyMissing` | pyarrow/PyYAML 필요한데 없음 | **경우에 따라** — §4 | — |

## 2.2 `FreezeViolation` 을 게시 경로에서 잡는 이유

봉인이 깨진 사실은 **화면에 나와야 하는 정보**다. 게시를 막으면 화면이 비고, 사람은 왜 비었는지 모른다.
**막아야 하는 것은 그 데이터로 실험을 계속하는 것**이지 사실을 보여주는 것이 아니다 → `gate1-freeze-procedure.md` §4.3.

---

# 3. 예외가 **아닌** 것 — 값으로 표현한다

| 상황 | 표현 | 예외로 만들면 |
|---|---|---|
| 근거 이벤트 0건 | `unavailable · NO_SOURCE_EVENT` | 빈 데이터에서 파이프라인이 죽는다. **오늘의 정상 상태가 죽는 상태가 된다** |
| 원가 근거 없음 | `unavailable · NO_COST_BASIS` | §1.1 |
| 필수 필드 결손 | `unavailable · MISSING_FIELD` | 동일 |
| 모델 산출물 없음 | `unavailable · NEEDS_MODEL_OUTPUT` | C1 에서 대부분의 지표가 예외가 된다 |
| 비교 전략 없음 | `unavailable · NEEDS_TWO_STRATEGIES` | 동일 |
| 파라미터 미확정 | `unconfirmed · PARAM_UNCONFIRMED` + `params` | 값을 낼 수 있는데 못 내게 된다 |
| pyarrow 없어 검사 못 함 | `blocked · BLOCKED` | 환경 차이로 CI 가 죽는다 |
| 검사를 실행하지 않음 | `not_run · NOT_RUN` | "안 함"이 "실패"가 된다 |
| 선행 테이블 없음 | `not_run · PRECONDITION_MISSING` | 동일 |
| 거부된 레코드 | `WriteResult.rejected` + `rejected.jsonl` | 한 건 때문에 배치 전체가 죽는다 |

> **표의 왼쪽 열이 오늘 이 저장소의 거의 모든 상태다.** 이것들을 예외로 만들면 **빈 Sink 에서 아무것도 돌아가지 않는다.**

---

# 4. `DependencyMissing` — 폴백과 실패를 가르는 규칙

| 상황 | 동작 | 왜 |
|---|---|---|
| pyarrow 없음 + `fmt="auto"` | **`jsonl.gz` 로 폴백** (이미 구현) | 표준 라이브러리만으로 동작해야 한다 (`ISO-005`) |
| pyarrow 없음 + `fmt="parquet"` **명시** | **`RuntimeError`** (이미 구현) | 사용자가 명시적으로 요청했다. 조용히 다른 것을 주지 않는다 |
| pyarrow 없음 + Parquet 재현성 검사 | **`DQ-17` 을 `blocked` 로 게시** | 검사를 통과로 적지 않는다 |
| PyYAML 없음 + config 필요 | **`ConfigError`** — 폴백 없음 | ★ 아래 |
| PyYAML 없음 + `test_config_loader` | **skip + 사유** | CI 무의존성 유지 (`dependency-plan.md` §2.2) |

> ### ★ YAML 파서를 자체 구현하지 않는다
> "PyYAML 이 없으면 간단한 파서로 대체" 는 매력적으로 보이지만, **부분 구현 파서는 조용히 다른 값을 읽는다.**
> 경제 규칙 config 를 잘못 읽으면 기여이익이 조용히 틀린다 — 이 프로젝트가 막으려는 실패 양식 그 자체다.
> **파서가 없으면 `ConfigError` 로 멈춘다.** 없는 능력을 있는 척하지 않는다.

## 4.1 폴백이 허용되는 조건

**셋을 다 만족할 때만:**
1. 폴백 결과가 **의미상 같다** (`jsonl.gz` 와 Parquet 은 같은 레코드를 담는다)
2. 폴백 사실이 **산출물에 기록된다** (`manifest.format` · 게시물 `provenance`)
3. 폴백이 **검증 결과를 통과로 바꾸지 않는다** (`DQ-17` 은 여전히 `blocked`)

**하나라도 어기면 폴백하지 않고 던진다.**

---

# 5. 종료 코드

| 코드 | 뜻 | 던지는 예외 |
|---|---|---|
| 0 | 정상. **`publish_result: partial` 도 0 이다** — §5.1 | — |
| 1 | 예상치 못한 오류 | 그 외 전부 |
| 2 | **데이터 품질 게이트 실패** | `QualityGateFailure` |
| 3 | **봉인 해시 불일치** | `FreezeViolation` (검증 명령에서) |
| 4 | 게시 실패 | `PublishError` |
| 5 | 설정 오류 | `ConfigError` |

## 5.1 `partial` 이 0 인 이유

부분 게시는 **정상적으로 완료된 부분 실패**다. 사실은 `index.json` 의 `publish_result` 와 `artifacts[].status` 에 남고, 대시보드가 표시한다.
0 이 아니게 만들면 **CI 나 스크립트가 "실패"로 처리해 게시물을 지우거나 롤백할 수 있고**, 그러면 왜 실패했는지가 사라진다.

> **호출자가 `partial` 을 무시하지 않게 하는 것은 종료 코드가 아니라 화면과 리포트다.**

---

# 6. 메시지 규약 — `NFR-006`

> `NFR-006`: *"입력/결과 파일 부재 시 **원인과 해결 방법**을 명확히 출력한다."*

**모든 예외 메시지는 세 가지를 담는다:**

```
① 무엇이 · ② 왜 · ③ 무엇을 하면 되는가
```

```python
raise ConfigError(
    f"경제 규칙 config 를 읽을 수 없다: {path}. "                      # ①
    f"파일이 없다. "                                                   # ②
    f"config/economic_config.yaml 을 만들거나 --config 로 경로를 준다."  # ③
)
```

**금지:**

| 금지 | 왜 |
|---|---|
| `raise ValueError("invalid")` | 무엇이 왜 잘못됐는지가 없다 |
| 파일 경로 없는 파일 오류 | 어느 파일인지 모른다 |
| 스택트레이스만 | `NFR-006` 이 요구하는 것은 원인과 해결이다 |
| **영어와 한국어 혼용** | 이 저장소는 한국어로 쓴다 (기존 코드 관례) |

**대시보드도 같은 규약을 따른다.** `EmptyState` 는 *"결과 파일이 없습니다"* 가 아니라 **무엇을 실행하면 되는지**를 말한다 (`DB-013`).

---

# 7. 로깅 — `NFR-005`

`NFR-005` 는 `[Simulator]`·`[Feature]` 등 단계 태그를 요구한다. **C1 에 해당하는 단계는 둘이다.**

```
[Measurement] Sink · 스키마 · 품질 검사
[Publish]     게시
```

| 규칙 | |
|---|---|
| **거부는 반드시 로그에 남는다** | 건수와 사유별 집계. 원문은 남기지 않는다 (§8) |
| **skip 은 로그에 남는다** | 조용한 skip 이 미실행을 통과로 만든다 |
| **폴백은 로그에 남는다** | *"pyarrow 없음 → jsonl.gz 로 저장한다"* |
| 진행률 로그를 남기지 않는다 | C1 에 장시간 작업이 없다 |

---

# 8. ★ 예외·로그에 담아서는 안 되는 것

> **`rejected.jsonl` 에는 금지 필드(Hidden Trait · τ · Potential Outcome)가 담긴 레코드가 원문으로 남는다** (`sink.py:203-206`).
> 그것이 이 파일의 존재 이유다 — 왜 거부됐는지 알아야 하니까.

| 규칙 | |
|---|---|
| **예외 메시지에 레코드 원문을 넣지 않는다** | 로그·CI 출력·이슈 코멘트로 흘러간다 |
| **게시물에 레코드 원문을 넣지 않는다** | `results/` 는 대시보드가 읽는다 → 금지 필드가 화면까지 간다 (`api-contracts.md` §5.2) |
| 대신 **필드 이름과 사유만** | `"측정 계층을 통과할 수 없는 필드: ['coupon_sensitivity']"` — 이름은 되고 **값은 안 된다** |
| `rejected.jsonl` 은 `data/raw/` 에 남는다 | `.gitignore` 가 `data/` 를 덮으므로 저장소에 들어가지 않는다 |

**이것은 격리 규칙의 연장이다.** `ISO-003` 이 경로로 막는 것을, 여기서는 **출력 경로**로 막는다.

---

# 9. 대시보드의 예외

| 상황 | 처리 | 화면 |
|---|---|---|
| `index.json` 없음 | `ArtifactMissing` | **게시 방법 안내** (`DB-013`) |
| `contract_version` 불일치 | `ContractVersionMismatch` | **그리지 않는다.** 버전 표시 |
| `run_id` 불일치 | `RunIdMismatch` | "게시 진행 중 또는 불일치". **값을 섞지 않는다** |
| 허용 경로 밖 접근 | `IsolationError` | 500. **조용히 읽지 않는다** |
| `status != "ok"` 인데 `value != null` | `ContractViolation` | **그리지 않고 실패한다** |
| 필드 누락 | `ContractViolation` | 동일 |

> ### ★ 마지막 둘 — 대시보드가 계약 위반을 발견하면 **그리지 않는다**
> 0 으로 채워진 값을 화면에 올리느니 화면이 비는 편이 낫다.
> **읽는 쪽이 계약을 검사하는 것이 게시 계약의 마지막 방어선이다** — 쓰는 쪽의 자기검증(§S-2 `contracts.py`)이 뚫려도 여기서 걸린다.

---

# 10. 기존 코드에서 고쳐야 할 것

| 위치 | 현재 | 고칠 방향 | 이슈 |
|---|---|---|---|
| `sink.py:158-160` | `strict=False` 가 거부된 레코드를 `_observe` 에 넘겨 **크래시** | 거부 후 `continue`. **`MEA-003` 관용 경로가 살아난다** | `#53` D1-2 |
| `sink.py:277-279` | `ValueError` | `PartitionKeyError`(`MeasurementError` 하위)로 승격 | — |
| `sink.py:156` | `WriteResult.problems` 가 레코드당 **첫 문제만** 담는다 | 의도적이면 독트링에 명시. 전체는 `rejected.jsonl` 에 있다 | — |
| `sink.py:113` | 독트링 *"append 한다"* 가 **사실과 다르다** | 동작을 고치거나 문서를 고친다 — `#53` 이 동작을 고친다 | `#53` D1-1 |
| `sink.py:229` | `created_at` 이 **UTC** — 자기 규약(KST 단일)과 어긋난다 | KST 로. 게시 계층은 이미 정규식으로 강제한다 | W-8 |
