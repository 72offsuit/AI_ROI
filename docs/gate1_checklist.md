# GATE 1 부분 봉인 체크리스트

> ## ★★ C1 은 GATE 1 을 **통과시키지 않는다**
> 완전 Lock **0종**. 측정 계층이 소유한 4종만 부분/조건부이고 5종은 다른 파트 소관이다.
> **`EXPERIMENT_ENVIRONMENT_v1` 을 선언하지 않는다** — 그 선언은 GATE 1 전체 통과를 전제한다.
>
> **부분 Lock 은 시간이 지나면 "전체를 Lock 했다"로 읽힌다.** 그래서 범위를 문장으로 남긴다.

**대상 이슈** `#49` · **작성** Phillip (Role 8 · W5-A) · 2026-09-11
**정본** `src/measurement/freeze.py` — 이 문서는 그 판정을 사람이 읽는 형태로 옮긴다.
`tests/test_freeze.py TestChecklistDocument` 가 이 문서를 코드와 대조해 **낡으면 실패한다.**

---

## 0. 지금 Lock 할 수 있는가 — **예**

```
선행 조건 G-1~G-16    충족 16 / 미충족 0
freeze.verify()        can_lock = True
```

**마지막 차단이 풀렸다** — 결정 **D-2** (사용자, 2026-09-11).

### ★★ `G-10` 의 `true` 가 뜻하는 것 — 오해하면 안 된다

| `true` 가 아닌 것 | `true` 가 맞는 것 |
|---|---|
| ~~"환불이 반영됐다"~~ | **"환불 미반영이라는 사실을 확인하고 가정으로 수용했다"** |

**환불·취소 이벤트를 추가하지 않는다.** `DATA-003` 22컬럼과 `event_type` 16종을 그대로 두며, 셋 다 `Plan/` SRS 개정을 요구해 권한 밖이다.

**★ 오차 방향 — 적지 않으면 읽는 사람이 어느 쪽인지 모른다:**

```
revenue = Σ order_amount        환불된 매출을 뺄 수 없다
                                → contribution_profit 이 위로 치우친다 (과대평가)
                                → 아래로가 아니다
```

**실험 판정에는 영향이 없다** — `MEA-002` 가 실험 결과 산출에 시뮬레이터 생성분만 쓰라고 규정하고, 시뮬레이터는 환불을 생성하지 않는다.

**세 곳에 남는다:**

| 자리 | 내용 |
|---|---|
| `config/economic_config.yaml` | `assumptions.refund_adjusted: false` — **확정값** (구현자 전제가 아니다) |
| `config/gate1_lock.yaml` | Lock 기록의 `assumptions[]` — **봉인이 무엇을 가정한 채 성립하는지** |
| 게시물 `notices` | `REFUND_NOT_ADJUSTED` — ★ **항상 표시한다. 화면에서 접히지 않는다** |

> **가정은 시간이 지나면 사실로 읽힌다.** 그래서 문서가 아니라 **산출물에 붙여** 나른다 (`P-12`). **접힌 가정은 없는 가정이다.**

---

## 1. 하나라도 미충족이면 Lock 하지 않는다

이것이 이 문서의 첫 규칙이다. **Lock 이후의 변경 비용이 전 데이터 재생성 + 전 전략 재실행**이기 때문이다 (`FREEZE-003`).

`freeze.record()` 가 이 규칙을 **코드로** 강제한다 — 선행 조건이 하나라도 `true` 가 아니면 `FreezeViolation` 으로 거부하고, 무엇이 막았는지 **이름으로** 말한다. 체크리스트를 읽고 넘어갈 수 없다.

---

## 2. 선행 조건 G-1 ~ G-16

**정본은 `freeze.GATE1_PRECONDITIONS` 다.** 아래는 그 표의 사람용 판이다.

| # | 조건 | `met` | 근거 |
|---|---|---|---|
| **G-1** | `category` 5종 Enum + `validate_event()` 검사 | ✅ | `schema.Category` · `test_unknown_category_is_rejected` (M-02) |
| **G-2** | `page_type` 8종 동일 | ✅ | `schema.PageType` · `test_unknown_page_type_is_rejected` (M-02) |
| **G-3** | `validate_event()` 가 `check_identifier()` 호출 | ✅ | 호출부가 **0건**이었다. `test_malformed_identifier_is_reported` (M-02) |
| **G-4** | 카테고리 어휘 정본 확정 | ✅ | 영문 코드 (SRS `COM-001`). 3자 불일치를 `schema.Category` 독트링에 정리 (M-02) |
| **G-5** | 타임존 정책 확정·강제 | ✅ | 정책 ⑵+b. `TestTimezonePolicy` (M-01) |
| **G-6** | 동일 root 재기록 시 파티션 보존 | ✅ | `_next_part_index` 최대+1. `TestRewriteSameRoot` (M-01) |
| **G-7** | `strict=False` 가 예외를 던지지 않음 | ✅ | `_is_observable` 로 갈랐다. `TestTolerantModeSurvival` (M-01) |
| **G-8** | 파생 상태 기록 경로 결정 | ✅ | 리드 판정 ④ 게시 시점 계산. `kpi.derived_state_count` 가 `derived:true` + Feature 금지 문구로 낸다 |
| **G-9** | `shipping_subsidy` 처리 방침 | ✅ | 결정 D-3 ⑴ 규칙 유도. `economics.shipping_subsidy` (M-03) |
| **G-10** | **환불/취소 이벤트 포함 여부** | ✅ | ★ **확인함 · 미반영을 가정으로 수용** (결정 D-2, 2026-09-11). `true` 는 *"환불이 반영됐다"* 가 **아니다** — §0 |
| **G-11** | KPI 계산 계약 확정 | ✅ | `kpi.py` 시그니처 + `_KPI_META` + `METRIC_SPECS` 46종 (M-04) |
| **G-12** | 경제 규칙 확정 | ✅ | `config/economic_config.yaml` 6블록. 기여마진율 26.0% 검산 (M-03) |
| **G-13** | `docs/event_schema.md` ↔ 코드 일치 | ✅ | 재생성 diff **0** (실행 확인) |
| **G-14** | `discover -s tests` 전건 통과 | ✅ | 기준선 46건에서 회귀 0 (실행 확인) |
| **G-15** | Lock 시점 커밋 SHA·config 해시 기록 절차 | ✅ | **이 스토리가 만들었다** — `freeze.build_record()` · `freeze.verify()` (M-09) |
| **G-16** | `discount` 유도 규칙을 `ECONOMIC RULE v1` 에 넣는다 | ✅ | 결정 D-16 · 리드 판정. `config` `assumptions` 조항 (M-03) |

### Lock **이전**에 결정되지 않아도 되는 것 — **조건이 아닌 것**

**조건을 부풀리지 않는다.** 아래를 조건에 넣으면 Lock 이 영원히 불가능해지고, 그러면 체크리스트가 의미를 잃는다.

| 항목 | 왜 조건이 아닌가 |
|---|---|
| Parquet 경로 검증 (`DQ-17`) | **저장 형식**의 문제이지 **스키마 계약**의 문제가 아니다. 단 `#44` 완료 조건이므로 이슈 종결과는 별개 |
| `write_batch()` 미구현 | 인터페이스 편의. 계약이 아니다 |
| 6개 추가 테이블 | §3 에서 **Lock 대상에서 제외**로 판정 |
| `DQ-09` 금액 정합성 | 저장 구조의 문제다. 커머스 교환 파일(`data/commerce/`, #100)이 있으면 실행되고, 없으면 `not_run` + `PRECONDITION_MISSING` 으로 남긴다 |
| `customers` 테이블 부재 | 모집단이 성립하지 않는 지표를 `PRECONDITION_MISSING` 으로 **게시하는 것**이 정직한 상태다. 계산 계약 자체는 확정됐다 |

---

## 3. Lock 9종 — PRD §22

**완전 Lock 0종 · 부분/조건부 4종 · 다른 파트 소관 5종.**
**측정 계층이 소유한 4종이 정확히 "부분/조건부 가능"에 대응한다** — 우연이 아니라 범위의 결과다.

| # | 항목 | 상태 | 소관 | 범위 한정 |
|---|---|---|---|---|
| 1 | `SERVICE_v1` | `OUT_OF_SCOPE` | commerce | 별도 저장소 소관. 이 저장소가 봉인할 수 없다 |
| 2 | `CUSTOMER_PERSONA_v1` | `OUT_OF_SCOPE` | simulator | 시뮬레이터 미가동 |
| 3 | `HIDDEN_TRAIT_RULE_v1` | `OUT_OF_SCOPE` | simulator | 측정 계층은 이 값을 통과시키지 않으므로(`ISO-003`) 봉인 대상으로 **알 수도 없다** |
| 4 | `BEHAVIOR_RULE_v1` | `OUT_OF_SCOPE` | simulator | 시뮬레이터 미가동 |
| 5 | **`ECONOMIC_RULE_v1`** | **`PENDING`** | **measurement** | 상수 6블록 + 유도 규칙 2건 확정. 단 AI 투자비가 추정치(`is_estimate: true`)이고 `A-REFUND` 가정이 남아 있다 |
| 6 | **`CHURN_DEFINITION_v1`** | **`PARTIAL`** | measurement | ★ **방식만** Lock — 고정 윈도우 · 운영/라벨 분리 · `label_window_days=42`. **임계값 28/42/60 은 Lock 하지 않는다** (D-5) |
| 7 | `TREATMENT_RESPONSE_v1` | `OUT_OF_SCOPE` | simulator | ★ Treatment **비용**(`ECONOMIC_RULE_v1`)과 다르다. 반응은 시뮬레이터 소관이고, 섞으면 **창구 중립성이 깨진다** |
| 8 | **`EVENT_SCHEMA_v1`** | **`PENDING`** | **measurement** | ★ **Lock 범위는 `events` 테이블에 한정된다** (D-8). 나머지 6테이블은 미정의 |
| 9 | **`KPI_DEFINITION_v1`** | **`PARTIAL`** | measurement | ★ **계산 계약**만 Lock. **역할 배정은 GATE 2** (D-4) — 그래서 `metrics[].role` 이 전부 `none` 이다 |

### 미봉인 5종과 사유

`SERVICE_v1` · `CUSTOMER_PERSONA_v1` · `HIDDEN_TRAIT_RULE_v1` · `BEHAVIOR_RULE_v1` · `TREATMENT_RESPONSE_v1`

**전부 다른 파트 소관이다.** `OUT_OF_SCOPE` 로 적는 이유: **남의 소관을 `PENDING` 으로 적으면 우리가 안 한 것처럼 보인다.** 목록에서 빼면 *"봉인 대상이 아니다"* 와 *"봉인을 잊었다"* 가 같아진다.

### `EVENT_SCHEMA_v1` — 범위를 **좁혀서** Lock

| Lock 한다 | Lock 하지 않는다 |
|---|---|
| `events` **22컬럼** · `event_type` **16종** | **나머지 6개 테이블** — `customers`·`orders`·`order_items`·`products`·`marketing_actions`·`assignment` |
| 이벤트별 Nullable 매트릭스 (16×15) | 저장 형식(Parquet) 검증 — `DQ-17` `BLOCKED` |
| 식별자 정규식 9종 · `category` 5종 · `page_type` 8종 | |
| 타임존 정책 · 금지 필드 25종 | |
| Observable 16개 ↔ 이벤트 매핑 · 파생 상태 기록 경로 | |

> **6테이블을 제외하는 이유:** `data_spec` §7.1 이 요구하지만 **`sink.py` 는 `events` 만 구현했다. 정의되지 않은 것을 Lock 할 수 없다.**
> **나중에 "스키마를 Lock 했다"는 문장이 6테이블까지 덮는 것으로 읽히면 안 된다.**

### `CHURN_DEFINITION_v1` — 임계값을 Lock 하지 않는 이유

`data_spec` §5.1 이 확정 절차 5단계를 규정했고 **①~④가 전부 시뮬레이터를 요구한다.** C1 에 시뮬레이터가 없다. 절차를 건너뛰고 숫자를 Lock 하면 *"미실행 검증을 통과로 표시하지 않는다"* 를 위반한다.

> ⚠ `data_spec` §15.3 은 GATE 1 확정 항목에 "Churn 임계값"을 넣었다. **모순이 아니다** — 그 정본은 **GATE 1 전체 통과**를 전제하고, **C1 은 통과시키지 않는다.**

---

## 4. 탐지 3층 — **같은 함수를 쓴다**

```
1층  tests/test_freeze.py   →  freeze.verify()   ★ 실패한다. 경고가 아니다
2층  publish.py 게시 시점    →  freeze.verify()   →  results/freeze_status.json
3층  대시보드 V6            →  그 게시물을 그린다
```

**세 층이 각자 판정하면 갈린다.** `freeze.verify()` 하나가 정본이고 나머지는 그것을 표시한다 — `test_publish_delegates_to_verify` 가 `publish.py` 에 자기 사본의 선행 조건 표가 없음을 소스 검사로 고정한다.

### ★ Lock 기록이 없을 때 조용히 통과하지 않는다

```python
# ❌ 이 사이클이 지목한 가장 위험한 다섯 줄 중 하나
if not lock_file.exists():
    return          # 봉인하지 않은 상태가 초록으로 보인다
```

`test_locked_files_unchanged` 는 **skip 하지 않는다.** `overall == "not_started"` 임을 **단언**한다. `skipTest` 도 쓰지 않는다 — `unittest` 가 skip 을 exit 0 으로 내므로 사유 없이 넘기면 검증하지 않은 것이 검증한 것처럼 보인다.

### `verification` 4값 — `not_run` 이 있는 이유

| 값 | 뜻 |
|---|---|
| `match` | 대조했고 정본 파일 해시가 기록과 같다 |
| `mismatch` | ★ 대조했고 **다르다** — 봉인 이후 변경됐다 (`FREEZE-003`) |
| `missing` | 대조했고 **Lock 기록이 없다** |
| **`not_run`** | ★ **대조하지 않았다.** `missing` 과 다르다 |

*"기록이 없음을 확인했다"* 와 *"확인하지 않았다"* 는 다른 상태다. 후자를 전자로 적으면 **확인했다는 주장**이 된다.

### 불일치일 때 게시를 막지 않는다

막으면 *"무엇이 불일치했는지"* 를 화면이 알 수 없다. **실패 사실을 담은 게시물이 게시되지 않는 게시물보다 낫다** — `notices` 에 `level: "failure"` 로 싣는다.

---

## 5. Lock 실행 절차 — **D-2 가 결정됐다. 실행 가능하다**

### 5.1 실행 전 확인 (전부 통과해야 한다)

명령은 **지원 런타임 Python 3.12**(`requirements.txt` 의 `Supported runtime` · DR-207)로 적는다. `python3` 이 가리키는 판은 기기마다 다르다 — `python3` 이 3.11 인 기기에서 ① 이 실패했다(#248). ① 은 의존성 없는 3.12 와 **의존성 두 벌을 설치한** 3.12 **양쪽**에서 돌린다(`freeze.py` G-14 근거 *"의존성 없이·설치 후 양쪽 OK"* 와 같다).

- 설치 후 환경은 `pip install -r requirements.txt -r requirements-dev.txt` 로 준비한다(AGENTS.md · 의존성 설치 CI 와 같다). `requirements.txt` 만 설치하면 계약 스키마 검증(`jsonschema` · `referencing`)이 skip 되고도 ① 이 `OK` 로 끝난다.
- 설치 후 실행에서는 ①′ 로 skip 사유에 `미설치` 가 든 검사가 **0건**인지 본다. 의존성 설치 CI 게이트와 같은 기준이다 — skip 총수를 0 으로 요구하는 것은 아니다.

```bash
# ① 전건 통과 (G-14) — 의존성 없는 3.12 · 두 벌 설치한 3.12 양쪽
python3.12 -m unittest discover -s tests

# ①′ 설치 후 실행만 — 의존성 사유 skip 0건 (출력이 없고 종료 코드 0 이어야 한다)
! python3.12 -m unittest discover -s tests -v 2>&1 | grep -E "skipped '[^']*미설치"

# ② 생성 문서 ↔ 코드 일치 (G-13)
python3.12 scripts/gen_event_schema_doc.py | diff - docs/event_schema.md

# ③ 소유 경계
python3.12 .agent-team/04-architecture/tools/check_ownership.py

# ④ 선행 조건 16종 판정
python3.12 -c "from src.measurement import freeze as fz; \
  v = fz.verify(preconditions=fz.GATE1_PRECONDITIONS, items=fz.gate1_lock_items()); \
  print(v.overall, v.verification, 'can_lock:', v.can_lock); \
  [print(' 미충족', p.id, p.met, p.title) for p in v.unmet]"
```

### 5.2 실행

**`locked_by` 는 사람 이름이다.** `""`·`"agent"`·`"unknown"` 을 `freeze.build_record()` 가 거부한다 — 봉인은 책임 소재가 있는 행위이고, **누가 언제 무엇을 어느 범위까지 Lock 했는지**가 이 기록의 존재 이유다.

```python
from datetime import datetime
from pathlib import Path
from src.measurement import contracts as ct, freeze as fz
from src.measurement.sink import KST

verification = fz.verify(
    preconditions=fz.GATE1_PRECONDITIONS, items=fz.gate1_lock_items()
)
commit, _ = ct.repo_commit()
fz.record(
    verification,
    locked_by="<사람 이름>",                    # ★ agent 불가
    canonical_files=[
        Path("src/measurement/schema.py"),
        Path("config/economic_config.yaml"),
        Path("docs/event_schema.md"),
        Path("docs/measurement_contract.md"),
    ],
    repo_commit=commit,
    now=datetime.now(KST),
    assumptions=fz.gate1_assumptions(),      # ★ 빠뜨리면 가정이 전부 사라진다
)
```

> ★ **`assumptions=` 를 빠뜨리지 않는다.** 이 인자의 기본값은 `()` 이므로, 넘기지
> 않으면 기록의 `assumptions` 가 **조용히 빈 목록이 된다.** 가정을 잃은 봉인 기록은
> *"전부 확인했다"* 로 읽히고, 봉인은 그렇게 주장하지 않는다.
>
> 이 줄은 원래 이 문서에 없었다. 이슈 `#63` 이 요구한 **재기록을 절차대로
> 실행했다면 가정 4건이 그대로 사라졌을 것이고**, 대조하는 것이 없어 아무도 몰랐을
> 것이다. 지금은 정본이 `freeze.gate1_assumptions()` 에 있고
> `tests/test_freeze.py` 가 기록과 대조한다.

`config/gate1_lock.yaml` 이 생기고 **커밋한다.** 그 뒤 게시를 다시 돌리면 `freeze_status.json` 의 `overall` 이 `not_started` → `partial` 로 바뀐다.

### 5.3 기록에 들어가는 것

```
declaration: PARTIAL_FREEZE                      ★ FULL_FREEZE 가 아니다
experiment_environment_v1_declared: false
locked_at: <KST +09:00>
locked_by: <사람 이름>
repo_commit: <git rev-parse HEAD>
simulator_commit: null                           ★ "" · "unknown" · "0" 금지
simulator_commit_null_reason: PRECONDITION_MISSING
items: Lock 9종 전부 (status · owner_part · scope_note)
canonical_files: { 경로: SHA-256 }
release_procedure: FREEZE-003
```

**`simulator_commit` 은 `null` 이 정직한 값이다.** C1 에 시뮬레이터가 없다. 빈 문자열로 채우면 *"확인했고 이 값이다"* 가 되어 `FREEZE-003` 대조가 무의미해진다.

---

## 6. 해제 절차 — `FREEZE-003`

봉인 대상을 변경하면:

```
① 버전을 상향한다            event-schema-v1.0 → v1.1
② 전 데이터를 재생성한다
③ Baseline 부터 전 전략을 재실행한다
```

**해제는 사용자 승인 사항이며 `config/gate1_lock.yaml` 을 손으로 고치는 것으로 대체되지 않는다** — 손으로 고치면 `test_locked_files_unchanged` 의 해시 대조가 실패한다. 그것이 이 파일을 기계가 쓰는 이유다.

### `BLOCKED` 항목

| 항목 | 사유 | 해소 조건 |
|---|---|---|
| `DQ-17` Parquet 재현성 | pyarrow 가 저장소 기본 환경에 없다 (`ISO-005` — 격리 CI 는 의존성을 설치하지 않는다) | 설치 환경에서 `tests.test_sink.TestParquetPath` 실행. `requirements.txt` 에 `pyarrow==25.0.1` 이 있다 |

`DQ-17` 은 **Lock 전 조건이 아니다** (§2 "조건이 아닌 것") — 저장 형식의 문제이지 스키마 계약의 문제가 아니다.
