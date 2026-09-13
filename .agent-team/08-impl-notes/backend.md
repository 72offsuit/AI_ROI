---
name: backend-impl-notes
cycle: C1
wave: W5
author: Phillip (Role 8 · Backend & Data Lead)
date: 2026-09-11
intensity: full
---

# W5-A 구현 노트 — 측정 계층

**작성** Phillip (Role 8) · 2026-09-11 · BATHOS Lv3 · 사이클 **C1**
**쓰기 범위 준수** 소유 경로 밖 변경 0건 · `check_ownership.py` **PASS** · `Plan/`·`Ecommerce_Service`·`dashboard/**` 변경 **0건** · 봉인 파일 변경 **0줄** · GitHub 이슈 조작 **0건**

---

# 0. 한 문단

기준선 **46건 → 407건**(회귀 0)으로 올리고, **계약 수정 4건을 validator 로 검증**한 뒤 **측정 계층을 끝까지 연결해 `results/` 7종을 실제로 게시했다.**

두 가지가 이 웨이브의 성과다:
1. *"고쳤다"* 가 아니라 **"기존 방어가 그대로다"** 를 기계로 증명했다 — `basis` 금지가 `not` 한 줄 편집으로 사라질 수 있었고 **사라지지 않았음을 실행으로 확인했다.**
2. **실제 게시물 7종이 수정된 계약을 전수 통과한다 (위반 0건).** 픽스처의 `vacuous` 7건은 계약에 걸려 거부되는데 **우리 출력은 통과한다** — 계약 수정이 픽스처의 결함을 겨냥했고 구현을 겨냥하지 않았다는 증거다.

---

# 1. 재현 명령 — 이것만 실재한다

```bash
# ① 전체 (의존성 없이 — isolation.yml 이 돌리는 것과 동일)
python3 -m unittest discover -s tests            # Ran 407 · OK · skipped=67

# ② 격리 경계
python3 -m unittest tests.test_isolation -v      # Ran 6 · OK

# ③ 의존성 설치 후 (선택 경로가 실제로 실행된다)
python3 -m venv /tmp/airoi-deps
/tmp/airoi-deps/bin/pip install -r requirements-dev.txt
/tmp/airoi-deps/bin/python -m unittest discover -s tests   # Ran 407 · OK · skipped=3

# ④ 소유 경계
python3 .agent-team/04-architecture/tools/check_ownership.py   # PASS

# ⑤ 부수 스크립트
python3 scripts/gen_event_schema_doc.py > docs/event_schema.md
python3 scripts/gen_event_schema_doc.py | diff - docs/event_schema.md   # 차이 0
python3 scripts/bench_sink.py 20000 30
```

### ★ 게시 — 이제 실재하는 명령이다

```bash
# 의존성이 필요하다 (config 를 읽어야 하고 자체 파서로 폴백하지 않는다)
/tmp/airoi-deps/bin/python -m src.measurement.publish
/tmp/airoi-deps/bin/python -m src.measurement.publish --source data/raw --out results
/tmp/airoi-deps/bin/python -m src.measurement.publish --fail-on-quality   # 품질 fail 이면 종료 2
```

**`config/gate1_lock.yaml` 은 없다** — Lock 을 실행하지 않았다 (§8.1 G-10).
실행 절차는 `docs/gate1_checklist.md` §5 에 있고 `freeze.record()` 가 선행 조건
미충족 시 거부한다.
lint·build·타입 검사는 이 저장소에 정의되어 있지 않다 (charter §6.3) — 만들지 않았다.

## 환경 변수

**없다.** 측정 계층은 환경 변수를 읽지 않는다. 설정은 `config/economic_config.yaml` 하나이고 경로는 인자로 받는다(`load_economic_config(path)`). 환경 변수를 쓰면 *"어떤 값으로 계산했는지"* 가 게시물에 남지 않는다.

---

# 2. ★★ 계약 수정 4건 — validator 실행 결과

**`AC-4d`·`AC-4e` 를 읽어서 판단하지 않고 `jsonschema 4.26.0` 으로 수정 전/후를 직접 돌렸다.**
정본 목록: `docs/contracts/measurement-publish/v1/CHANGELOG.md` · 기계 검사: `tests/test_publish_contract.py` (30건)

| # | 수정 | 형태 | 검증 |
|---|---|---|---|
| **FIX-1** | `headline_code` 7종 → **8종** (`REJECTED_EVENTS`) + 우선순위 계약화 + `ALL_CLEAR` 가드 | 추가 | ✅ |
| **FIX-2** | `metric_value.value_formatted` — `ok`·`unconfirmed` 필수 / 계산 불가 금지 | ★ **`allOf[2].then.not` 교체** | ✅ |
| **FIX-3** | `metric_value.limit_note` — 선택 필드 | 추가 | ✅ |
| **FIX-4** | `checks[]` `status`↔`reason_code` · **`vacuous` 절 교체** | ★ 추가 2 + **교체 1** | ✅ |

## 2.1 AC-4e — 네 레코드 (계산 불가 분기)

```
레코드 (status: unavailable)              수정 전   수정 후   기대      판정
① basis 없음 · value_formatted 없음        통과      통과     통과/통과   ✅
② value_formatted 있음                    거부 ※    거부     통과/거부   ※ 아래
③ ★ basis 있음   ← 회귀 지점               거부      거부     거부/거부   ✅
④ 둘 다 있음                              거부      거부     거부/거부   ✅
```

### ★ **`basis` 금지가 살아 있다** — W5 가 스스로 증명한 기록

③이 수정 후에도 **거부**된다. *"고쳤다"* 가 아니라 **"기존 방어가 그대로다"** 가 이 항목의 내용이다.

**틀린 형태를 실제로 만들어 반례를 확인했다** (`{"required":["basis","value_formatted"]}`):

```
① 통과   ② 통과 ← 새 금지가 안 걸린다   ③ ★ 통과 ← 기존 금지가 사라진다   ④ 거부
```

**두 개가 한 번에 무력화된다.** 픽스처에 *"계산 불가인데 `basis` 가 있는"* 레코드가 없으므로 기존 테스트는 전부 통과한다 — **조용한 회귀**다.
`tests/test_publish_contract.py` 의 `test_the_wrong_form_would_let_basis_through` 가 이 반례를 고정한다.

### ※ 발견 — ②의 "수정 전" 이 스토리 표와 다르다

| | 스토리 §4.16 표 | **실측 (스키마 전체)** |
|---|---|---|
| ② `value_formatted` 있음 · 수정 전 | **통과** | **거부** |

**스토리 표는 `allOf[2].then` 절만 떼어 평가한 결과다.** 절 단위로는 통과가 맞다.
그러나 스키마 전체로는 **`value_formatted` 가 `properties` 에 없고 `additionalProperties: false`** 이므로 미선언 키로 먼저 막혔다 — 실측 거부 사유가 `additionalProperties` 였다.

**→ 수정 전 상태가 스토리가 말한 것보다 안전했다.** 그래도 `anyOf` 는 필수다: **`value_formatted` 를 선언하는 순간 `additionalProperties` 방어가 사라지고 `not` 절이 유일한 방어가 된다.** 위 반례에서 ②와 ③이 함께 통과하는 것이 그 증거다.

## 2.2 AC-4d — `value_formatted` 필수 / `vacuous` 교체 / Q-2

```
ok           value_formatted 없음  →  전 통과 / 후 거부   ✅
ok           value_formatted 있음  →  전 거부 / 후 통과   ✅
unconfirmed  value_formatted 없음  →  전 통과 / 후 거부   ✅   ← allOf[1]. 빠뜨리기 쉬운 자리
unconfirmed  value_formatted 있음  →  전 거부 / 후 통과   ✅
limit_note   있어도/없어도 통과      →  선택 필드 확인      ✅

vacuous · reason_code 없음  ← 오늘의 정상 상태  →  전 거부 / 후 통과 ✅ / "추가"했다면 거부 ❌
vacuous · reason_code 있음                     →  전 통과 / 후 거부 ✅ / "추가"했다면 거부 ❌
```

**★ `vacuous` 를 "추가"했을 때 양쪽이 다 거부되는 것을 재현했다** — 만족 불가능해진다. 그래서 **교체**다.
**두 줄을 다 확인했다.** 하나만 보면 만족 불가능해진 것을 못 잡는다.

```
Q-2 blocked + BLOCKED               전 통과 / 후 통과  ✅
    blocked + NOT_RUN               전 통과 / 후 거부  ✅
    not_run + NOT_RUN               전 통과 / 후 통과  ✅
    not_run + PRECONDITION_MISSING  전 통과 / 후 통과  ✅
    not_run + BLOCKED  ← 픽스처 DQ-06  전 통과 / 후 거부  ✅
```

## 2.3 픽스처 영향 — **기존 결함과 섞이지 않았음을 확인했다**

```
수정 전 스냅샷:  14파일 전부 통과       (실측)
수정 후:         156건 실패 — 전부 내 수정이 만든 것
```

`test_snapshot_accepted_every_fixture` 가 *"원래 깨져 있었다"* 로 넘기는 경로를 막는다.
실패 원인은 셋뿐이고 전부 등재됐다 — **`INTENDED_FIXTURE_FAILURES`** 가 정본이고, 테스트가 **양방향**을 본다:

| 방향 | 검사 |
|---|---|
| 목록 **밖에서** 실패 | `test_fixtures_fail_only_where_intended` → 제약이 과하게 물었다 |
| ★ 목록 **안에서** 통과 | `test_every_intended_failure_actually_fails` → **제약이 안 걸렸다** |

**개수를 적지 않는다** — dict 를 순회한다. `empty-sink` 의 `vacuous` **7건 전부 거부**(W3 예측과 일치, `DQ-01·02b·04·07·08·10·11`).

---

# 3. 새 의존성 — 사다리 5단을 못 넘은 이유

**해석 환경: Python 3.12.4** (CI 와 동일). 로컬은 3.14.6 이지만 **거기서 해석하지 않았다** — cp314 휠만 있는 릴리스를 고정하면 CI 가 깨진다 (T-10).

| 패키지 | 버전 | 사다리 5단을 못 넘은 이유 (한 줄) |
|---|---|---|
| `pyarrow` | **25.0.1** | Parquet 은 컬럼 지향 바이너리 포맷이라 표준 라이브러리로 읽고 쓸 수 없다 — `SRS PIPE-002` 가 권장 형식으로 지정했고 대안이 자체 구현뿐이다 |
| `PyYAML` | **6.0.3** | YAML 파서를 자체 구현하면 **부분 구현 파서가 조용히 다른 값을 읽는다.** 경제 규칙 config 에서 그것은 기여이익이 조용히 틀리는 결과다 (`exceptions.md` §4) |
| `jsonschema` | **4.26.0** (dev) | draft 2020-12 의 `if/then`·`not/anyOf`·`$ref` 해석을 손으로 재현하는 것이 곧 validator 재구현이다. **계약 수정 4건이 전부 그 의미론에 걸려 있었다** |
| `referencing` | **0.37.0** (dev) | `common.schema.json#/$defs/...` 상대 참조를 오프라인에서 풀려면 `Registry` 가 필요하다. `jsonschema` 의 전이 의존이지만 테스트가 직접 import 하므로 명시 고정했다 |

**넣지 않은 것:** pandas · numpy · scikit-learn (`src/decision/` 의 것, C1 범위 밖) · lint·타입 검사 도구 (**없는 게이트를 만들지 않는다**) · `pyproject.toml` 전환 (SRS §31 이 `requirements.txt` 를 규정) · 전이 의존성 lock (게시물 바이트에 영향 없음).

**`==` 고정 이유:** `NFR-001`. `pyarrow` 버전이 바뀌면 같은 데이터에서 다른 Parquet 바이트가 나올 수 있고, 그러면 `events.parquet` SHA-256 대조가 무의미해진다.

## 3.1 ★★ `PyYAML CVE-2026-24009` — **PyYAML 의 CVE 가 아니다**

GitHub Advisory API 로 원문을 확인했다 (`GHSA-vqxf-v2gg-x3hc`):

| 항목 | 실측 |
|---|---|
| **영향 패키지** | ★ **`docling-core`** (pip) — `>= 2.21.0, < 2.48.4`. **PyYAML 이 아니다** |
| 내용 | `docling-core` 가 `yaml.FullLoader` 로 신뢰할 수 없는 YAML 을 읽어 **CVE-2020-14343 을 재노출**했다 |
| 그 원 CVE | `CVE-2020-14343` (`GHSA-8q59-q68h-6hv4`) — **PyYAML `< 5.4`**, 5.4 에서 패치 |
| 완화 | `SafeLoader` 사용 **또는** PyYAML ≥ 5.4 |

**PyYAML 에 공표된 권고 4건 전수 확인** — `CVE-2017-18342`(`<5.1`) · `CVE-2019-20477`(`5.1~5.2`) · `CVE-2020-1747`(`5.1b7~5.3.1`) · `CVE-2020-14343`(`<5.4`).
**넷 다 `< 5.4` 이고 고정한 6.0.3 은 전부 위다 → 해당 권고 없음.**

> **→ `project-context-kr.md` §7.1 과 m-05 §4.6 이 이 CVE 를 PyYAML 의 것으로 적은 것은 오귀속이다.** 사슬의 실제 PyYAML CVE 는 `CVE-2020-14343` 이다.
> **버전 선택 결론은 같다** (6.0.3 안전). 다만 *"PyYAML 에 CVE 가 있다"* 로 읽히면 다음 사이클이 없는 문제를 쫓는다.

**그래도 `safe_load()` 만 쓴다.** 로더 선택은 파일 출처와 무관한 습관의 문제이고, `tests/test_neutrality.py test_no_unsafe_yaml_loader` 가 `FullLoader`·`UnsafeLoader`·`unsafe_load`·`yaml.load()` 사용 0건을 고정한다.

---

# 4. 주요 결정 — 스토리가 구현자에게 맡긴 것

| # | 항목 | 결정 | 근거 |
|---|---|---|---|
| **M01-a** | D1-1 수정 방식 | ⑴ **디렉터리 스캔** (최댓값+1) | `data-model-erd.md` §3 의 `part-NNNN` 규약이 유지되고 `read_events()` 의 `rglob("part-*")` 가 그대로 동작한다. 확장자를 무시하고 번호만 읽어 형식 혼재 시 충돌을 피한다 |
| **M01-b** | 타임존 정책 | ⑵ **어떤 오프셋이든 받아 KST 로 변환** | 커머스가 UTC 로 기록하고 있어 전량 거부는 `MEA-003` 과 충돌한다. **오프셋 없는 timestamp 는 거부** — 순간을 특정할 수 없으므로 추측하지 않는다 |
| **M01-c** | 저장 표현 | **b — KST 로 정규화해 저장** | a(원문 보존)를 고르면 `DQ-06`("모든 시각이 KST 단일")이 **자기 저장물에 대해** 실패한다. `_normalize_timestamp()` 가 저장값과 파티션 날짜를 **한 번의 파싱에서** 함께 만들어 어긋날 자리를 없앴다 |
| **M01-d** | `strict=False` 의 `accepted` 이중 계상 | **유지 + 독트링 명시** | `accepted` 를 줄이면 저장된 행 수와 어긋난다. "받아들였다"와 "문제가 있었다"는 배타적이지 않다 |
| **M01-e/M02-c** | `#53`·`#54` 묶기 | **묶었다** | 둘 다 `schema.py` 를 고친다. 두 번 열면 한쪽이 다른 쪽을 되돌린다 |
| **M02-a** | 식별자 위반 표현 | ⑴ **`problems` 에 넣는다** | ⑵는 `list[str]` 반환 계약을 바꿔 `sink.py:151` 과 `test_schema.py` 다수를 흔든다. `#54` 가 요구한 것은 "보고한다"까지다 |
| **M02-b** | `MetricStatus`·`ReasonCode` 위치 | ⑴ **`schema.py`** (D-18) | `kpi.py`·`economics.py` 가 둘 다 쓴다. 한쪽에 두면 계산층 사이에 불필요한 의존이 생긴다 |
| **M03-b** | `blocked_by` 사슬 생성 | **계산층은 직접 원인만** | `ADR-0009` 가 전이 사슬을 `publish.py` 에 뒀다. 계산층이 전체 그래프를 알면 계산층마다 같은 그래프를 다시 만든다 |
| **M05-a/D-21** | `jsonschema` 위치 | ⑴ **dev 전용** | 런타임 의존을 둘로 유지한다. 대가는 §7 의 `ponytail` 마커에 적었다 |
| **M05-b** | 가상환경 위치 | 스크래치패드 (`/tmp/claude-501/airoi-deps`) | 저장소를 오염시키지 않는다 |

## 4.1 ★ D1-2 — 스토리 T3 을 그대로 따르면 기준선이 깨진다

**스토리 T3:** *"`strict` 여부와 무관하게 `problems` 가 있으면 `_observe`·`_buffer` 로 보내지 않는다"*
**그런데 기준선 46건에 이것과 정면 충돌하는 테스트가 있다:**

```python
# tests/test_sink.py  test_non_strict_keeps_record_but_still_reports  (기준선)
with sk.EventSink(self.root, strict=False) as s:
    result = s.write_events([bad])       # PURCHASE, order_amount 누락
self.assertEqual(1, result.accepted)
self.assertEqual(1, len(list(sk.read_events(self.root))))   # ★ 저장을 요구한다
```

T3 을 문자 그대로 구현하면 이 테스트가 실패하고, **테스트를 고쳐 통과시키는 것은 금지**다.

**→ 결손의 종류로 갈랐다. 크래시의 실제 원인만 막는다:**

| 레코드 | `strict=True` | `strict=False` |
|---|---|---|
| `event_type` 이 유효 + 다른 위반 | 거부 | **저장 + 보고** (기준선 유지) |
| ★ `event_type` 이 무효·부재 | 거부 | **거부** (크래시 원인) |

`_observe()` 는 `sc.EventType(record["event_type"])` 로 커버리지 행을 만든다. **`event_type` 이 없으면 요구사항 매트릭스를 조회할 수 없어 저장할 의미가 없다** — `_is_observable()` 이 그 경계다.
T-1(`record.get("event_type","unknown")`)·T-2(`except: pass`) 를 쓰지 않고 **`_observe` 의 "유효한 레코드만 받는다" 계약을 강화**해서 풀었다.

**리드 판정 요청:** 스토리 T3 의 문언과 기준선 테스트가 충돌한다. 위 해석이 둘을 모두 만족하는 유일한 배치라고 판단했으나, T3 의 의도가 *"관용 모드에서 아무것도 저장하지 않는다"* 였다면 기준선 테스트 수정 승인이 필요하다.

## 4.2 ★ 타임존 — 46/46 을 지키는 좁은 길

`validate_event()` 는 **오프셋의 유무만** 보고 **파싱 가능성은 보지 않는다.**

```
"2025-10-01T09:00:00.000+09:00"  →  통과
"2025-10-01T23:30:00.000Z"       →  통과 (Sink 가 KST 로 정규화)
"2025-10-01T23:30:00"            →  거부 (오프셋 없음)
"어제"                            →  ★ 통과. flush() 가 던진다
```

마지막 줄이 요점이다. `validate_event` 가 파싱 실패도 거부하면 `"어제"` 가 `_buffer` 에 들어가지 않고, `flush()` 가 예외를 던지지 않아 **`test_unparsable_timestamp_is_reported`**(스키마를 통과해도 파티션 키를 못 만들면 조용히 넘기지 않는다)가 깨진다.
ISO 8601 **모양을 먼저 알아보고 그 다음 오프셋을 요구**하는 두 정규식으로 구현했다. `test_unparsable_timestamp_is_left_to_the_sink` 가 이 불변식을 실행으로 고정한다 — **"tighten" 하지 말라는 경고를 테스트로 남겼다.**

---

# 5. 상류 문서에서 발견한 수치 불일치 2건 — **리드 판정 필요**

## 5.1 AI 비용 — 식과 결과가 어긋난다 (미해결)

```
economic-rule-v1.md §5 / story-m-03 §4.3
  적힌 식    (12,600,000 / 12 + 500,000) × (42/30)
  적힌 결과  ≈ 2,020,000원
  실제 값    1,550,000 × 1.4 = 2,170,000원        차이 150,000원
```

**식을 정본으로 보고 식을 구현했다.** 2,020,000 을 내는 식을 역산하지 못했다(여러 조합을 시도했으나 자연스러운 해석이 없었다).
`tests/test_economics.py test_ai_cost_is_unconfirmed_because_inputs_are_assumptions` 가 **2,170,000 을 단언**하고, 그 자리에 불일치를 주석으로 남겼다.

> **판정 필요:** 식이 맞고 결과가 오타인가, 아니면 다른 식이 의도였는가.
> **영향은 제한적이다** — `ai_investment_cost()` 는 `unconfirmed` 로 나가고(가정 기반 추정치) `ai_roi` 는 C1 에서 항상 계산 불가다.

## 5.2 기여마진율 26.0% — **문서가 맞았다** (해결)

1차 구현에서 빈도 가중으로 짜 **26.58%** 가 나왔고 문서가 틀렸다고 판단할 뻔했다.

```
빈도 가중   Σ(margin × frequency)                        = 26.58%
매출 가중   Σ(margin × price × freq) / Σ(price × freq)   = 26.00%   ← 문서값
```

**문서가 맞다.** 혼합 기여마진율은 매출 가중이 경제적으로 옳은 정의이기도 하다.
**교훈: 가중 기준을 적지 않은 요약값은 검산할 때 두 답을 준다.** `test_weighted_contribution_margin_is_26_percent` 가 가중 기준을 명시하고 두 값을 주석에 함께 남겼다.

---

# 6. 발견한 사실 — 다음 사이클이 알아야 할 것

## 6.1 `jsonl.gz` 와 Parquet 의 **구조 차이** (값 차이는 0건)

`test_jsonl_and_parquet_agree` 를 처음 dict 상등으로 썼더니 실패했다. **실패가 옳았다** — 차이가 실재한다.

```
jsonl.gz   없는 필드를 키째로 생략      (7 키)
parquet    없는 필드를 명시적 null 로   (22 키)

공유 키에서 값 불일치: 0건 ✅        None 이 0·"" 으로 바뀐 사례: 0건 ✅
```

둘 다 "이 필드는 없다"의 올바른 표현이고 `.get(name) is None` 에서 구분되지 않는다.
★ **그러나 키 개수를 세는 검사는 형식에 따라 다른 답을 얻는다.** 결손 집계를 `len(row)` 로 하면 Parquet 환경에서 조용히 틀린다 — **`sc.FIELD_INDEX` 를 순회해 `.get()` 으로 판정해야 한다.**
`jsonl.gz` 를 22 컬럼으로 맞추지 않았다: 레코드마다 null 키 15개가 늘어 압축 후 크기가 커지고(벤치 바이트 게이트가 ±1%) 얻는 의미가 없다.
`test_absent_field_representation_differs_by_format` 가 이 차이를 **명시적으로** 고정한다 — 숨기면 나중에 결함으로 오해된다.

## 6.2 `A7-4` 는 수로 판정할 수 없다 — **이름 목록으로 대조했다**

기준선 46건의 테스트 이름을 `git archive HEAD` 로 뽑아 skip 목록과 교집합을 계산했다.

```
no-deps   (isolation.yml 과 동일)  ran=200  skipped=35  기준선 skip=0  ✅ 회귀 0
with-deps                         ran=200  skipped= 2  기준선 skip=1
```

**with-deps 의 1건은 `test_parquet_request_without_pyarrow_raises`** 이고, pyarrow 가 없을 때만 존재하는 에러 경로를 단언하므로 **설치 환경에서 skip 되는 것이 올바른 동작**이다 (m-05 §4.4 가 예측함).
**`A7-4` 가 판정하는 환경은 no-deps 이고 거기서 기준선 skip 은 0 이다.**

> 부수 정정: m-05 §4.4 는 *"pyarrow 를 설치하면 **이 둘이** skip 된다"* 고 적었으나 실제로는 **1건만** skip 된다. `test_auto_falls_back_without_pyarrow` 는 조건식으로 기대값을 바꾸므로 skip 되지 않는다.

## 6.3 남은 값 수준 강제 공백 — `treatment_group`

`category`·`page_type` 과 같은 종류의 열거 공백이 `treatment_group`(`control`/`treatment`)에 남아 있다. **`#54` 수용 기준이 둘만 지목했으므로 넣지 않았다** — 요청받지 않은 범위 확장을 하지 않는다.
`_CATEGORICAL_VALUES` 주석에 이 사실을 적었다. 넣으려면 이슈에 추가하고 `Category`·`PageType` 과 같은 방식으로 한 줄이면 된다.

## 6.4 벤치 — 건수·바이트 정확 일치

```
              기준선(2026-09-10)   실측(2026-09-11)   판정
건수          4,200,000            4,200,000          ✅ 정확 일치
저장 크기     112.6 MB             112.6 MB           ✅ ±1% 이내
소요          64.7초               78.7초 (1.22x)     기록만 — 2배(129초) 미달
거부                               0건                 ✅ 새 강제가 벤치 레코드를 거부하지 않는다
```

시간 1.22x 는 파티션당 1회 디렉터리 스캔 + 레코드당 `isoformat()` 1회가 늘어난 것이다. **게이트가 아니므로 값만 기록한다** (개발 기계 wall-clock 은 재현되지 않는다).

---

# 7. `ponytail:` 마커 3건 — 전부 업그레이드 트리거 포함

```
src/measurement/sink.py:49       고정 +09:00 오프셋
    ceiling  1988년 이전 한국 서머타임과 향후 규칙 변경을 반영하지 못한다
    trigger  1988-10-09 이전 timestamp 수집이 필요해지거나 한국이 DST 를 재도입하면
    upgrade  zoneinfo.ZoneInfo("Asia/Seoul") + requirements.txt 에 tzdata

src/measurement/sink.py:362      파티션당 선형 glob 스캔
    ceiling  파티션 하나에 파트가 수천 개면 스캔이 비용이 된다 (현재 30 스캔 × ≤1 파일)
    trigger  bench_sink.py 소요가 기준선의 2배를 넘으면
    upgrade  다음 인덱스를 manifest.json 에 저장해 디렉터리에서 재유도하지 않는다

src/measurement/contracts.py:376 부분 계약 검증 (핵심 불변식 7개)
    ceiling  정규식·$ref·additionalProperties·enum 은 검사하지 않는다
    trigger  D-21 재검토로 jsonschema 가 런타임이 되면 / 이 함수를 통과한 계약 위반이
             results/ 에서 발견되면
    upgrade  Draft202012Validator 호출로 교체하고 ContractViolation 래퍼는 유지
```

수집: `grep -rnE '(#|//|--) ?ponytail:' . --include='*.py'`
**1차 작성 시 마커를 독트링에 넣어 `/bathos-debt` grep 에 걸리지 않았다** — `#` 주석으로 옮겼다.

---

# 8. ★ 완료하지 못한 것 — `BLOCKED` 와 미착수

**미실행을 통과로 적지 않는다.**

## 8.1 사용자 결정 — 2건 승인, 1건 남음

| # | 항목 | 상태 |
|---|---|---|
| **D-17** | `results/` gitignore | ✅ **승인 (2026-09-11)** — `.gitignore` 에 넣었고 왜 생성물인지·처음 clone 한 사람이 직접 생성해야 한다는 것을 주석으로 남겼다. `check_ownership.py` **PASS** |
| **D-19** | `tests-with-deps.yml` | ✅ **승인.** 사용자가 직접 생성했다(파일은 `sealed`). **`isolation.yml` 변경 0줄** 확인 — `ISO-005` 보장 유지 |
| ★ **D-2** | 환불/취소 이벤트 포함 여부 | ⚠ **미결. `G-10` 이 `met: null` 이고 그것이 GATE 1 Lock 을 막는 유일한 항목이다** (§8.3) |
| D-1 | 원가 근거 없는 주문의 COGS | W2 추천 ⑴ 전제로 구현 — `EC-1`·`EC-2` 대로 `NO_COST_BASIS` |

### ⚠ `tests-with-deps.yml` 은 **내가 만든 파일이 아니다** — 소유자 주의

| | |
|---|---|
| **소유** | `ownership.json` 상 **`sealed`** (*"CI 신설. 사용자 확인 후 (D-19)"*) |
| **작성** | **리드(Paul)가 작성**하고 훅 경로 불일치로 **사용자가 직접 복사**했다 |
| **내 역할** | 내용을 읽고 **의도와 맞는지 확인**했다. 아래가 확인 결과다 |

**W6 이 이 파일을 Phillip 산출물로 오해하지 않도록 적는다.** 내가 쓸 수 없는 파일이고, 고쳐야 할 것이 있으면 리드에게 올린다.

**확인 결과 — 내 의도와 일치한다:**

| 항목 | 확인 |
|---|---|
| `isolation.yml` 변경 | **0줄** (`git diff --stat` 빈 출력) — `ISO-005` 보장 유지 |
| Python 버전 | **3.12** — `isolation.yml` 과 같고 내가 pin 을 해석한 환경과 같다 |
| 설치 대상 | `requirements-dev.txt` (`-r requirements.txt` 포함 → 런타임+dev 전부) |
| ★ skip 수 보고 step | **있다.** 그것이 이 잡의 실제 산출물이다 |
| `pip freeze` 출력 | 있다 — 실패를 해석 드리프트와 구분할 수 있다 |

★ **skip 수가 올라가면 검사가 조용히 멈춘 것이고, 잡이 녹색이어도 회귀다.** 내가 `A7-4` 를 수가 아니라 **이름**으로 판정한 것과 같은 규율이며, 주석이 그것을 적고 있다.

### ★ D-19 적용 후 — `tests-with-deps.yml` 이 무엇을 증명하나

두 CI 잡의 **skip 수 차이가 곧 "의존성이 필요한 검증"의 목록**이다:

```
isolation.yml        의존성 0     Ran 397 · skipped 58    ISO-005 를 매 PR 이 증명한다
tests-with-deps.yml  의존성 설치   Ran 397 · skipped  2    Parquet·YAML·jsonschema 경로가 실제로 실행된다
```

**with-deps 의 skip 2건**은 `test_parquet_request_without_pyarrow_raises` 와
`test_loading_without_yaml_raises_config_error` — **설치 환경에서는 탈 수 없는 에러
경로**다. 그것이 skip 되는 것이 올바른 동작이고, `A7-4` 가 판정하는 환경은 no-deps 다.

## 8.2 스토리 상태 — 정직하게

| 스토리 | 상태 | 남은 것 |
|---|---|---|
| **M-01** (`#53`) | ✅ **done** | — |
| **M-02** (`#54`) | ✅ **done** | — |
| **M-03** (`#47`) | ✅ **done** | — |
| **M-04** (`#46`) | ✅ **done** | 실험 판정 14종은 정의만 — C1 에 전략·모델이 없다 (설계대로) |
| **M-05** (T2.9) | ✅ **done** | D-19 승인으로 T6 해소 |
| **M-06** (게시) | ✅ **done** | T1~T8. `results/` 7종 + 계약 전수 통과 |
| **M-07** (`#48`) | ✅ **done** | `#48` 은 C1 에서 닫히지 않는다 — 9종이 `PRECONDITION_MISSING` 으로 남는 것이 정상 |
| **M-08** (`#45`) | ✅ **done** | 표현력 공백 4건 전부 결론 · 차단 0 |
| **M-09** (`#49`) | ⚠ **부분** | 산출물 3종 완료. ★ **Lock 실행이 `G-10`(D-2)로 BLOCKED** (§8.3) |

### ★ `results/` 를 실제로 만들었다

```
run_id          MR-20260911-124223-874b8283
publish_result  ok
verdict         attention · SINK_EMPTY
산출물          7종 (ingestion · rejection · field_coverage · kpi · data_quality · freeze · index)
계약 검증       ★ 7종 전부 통과 — 위반 0건
```

**검증한 것:**
- 계산 불가에 `value`·`basis`·`value_formatted` 가 있는 것 **0건** (USP-1)
- 계산된 지표 **18건 전부**에 `value_formatted` 존재 (Andrew 의 화면이 읽는 필드)
- 전 산출물이 **같은 `run_id`** 를 공유 (대시보드가 값을 섞지 않는다)
- `index.json` 이 **마지막**에 쓰인다 (mtime 확인)
- `limit_note` **8건** 실림 (V-7 `한계` 칩의 원천)

### ★ DQ-06 이 `BLOCKED` 를 벗어났다 — M-01 의 부산물

`DQ-06`(모든 시각이 KST 단일)은 *"타임존 정책 미확정"* 으로 `BLOCKED` 였다. **M-01 이 정책을 확정했으므로 실행 가능해졌다** — 실제 데이터에서 `pass` 한다 (`TestRepresentativeScene.test_dq06_now_passes_because_sink_normalised_to_kst`).

**정책 ⑵-a(원문 보존)를 골랐다면 이 검사가 자기 저장물에서 실패했다.** 저장 표현 b 를 고른 이유가 실행으로 확인된 자리다.

→ 실행 가능 검사가 **7종 → 8종**이 되었고 `blocked` 는 `DQ-17` 하나만 남았다. m-07 §4.3 이 *"8건이 아니라 7건만 남는 것과, 그 차이를 리포트가 정확히 말하는 것이 C1 의 성과다"* 라고 적은 그 차이다.

### ⚠ `results/` 와 `check_ownership.py` — **D-17 이 하드 실패로 드러났다**

```
results/ 존재  →  ❌ 소유자 없음 7건  →  판정 FAIL
results/ 부재  →  판정 PASS  (Phillip 43 ∩ Andrew 48 = 0)
```

**경계 위반이 아니다.** `ownership.json` 에 `results/` 규칙이 없고(생성물이라 소유 개념이 없다) 도구가 **미추적 파일**을 훑기 때문이다. **`.gitignore` 에 `results/` 한 줄이면 해소되고 그것이 정확히 결정 D-17 이다** — 사용자 결정 대기라 넣지 않았다.

**Andrew 가 결정을 기다리지 않게** 증거 사본을 `.agent-team/08-impl-notes/results-sample/` 에 넣었다 (`.agent-team/**` 는 team 소유라 도구가 잡지 않는다). W2 추천 ⑶ 의 후반부다.

**리드 판정 필요:** `results/` 를 트리에 남긴 채 보고할지, 지우고 재생성 명령만 남길지. 검사를 초록으로 만들려고 산출물을 지우는 것이 옳아 보이지 않아 **남기고 사실을 적었다.**

## 8.3 ★★ GATE 1 부분 봉인을 **실행했다**

```
선행 조건 G-1~G-16      충족 16 / 미충족 0
config/gate1_lock.yaml   생성됨 (커밋 대상)
freeze.verify()          overall: partial · verification: match
```

| 항목 | 값 |
|---|---|
| `declaration` | **`PARTIAL_FREEZE`** — `FULL_FREEZE` 를 만들 경로가 코드에 없다 |
| `experiment_environment_v1_declared` | **`false`** |
| `locked_by` | **`Danto7632`** (사용자 GitHub 계정) — `"agent"`·`"unknown"`·빈 문자열은 거부된다 |
| `locked_at` | `2026-09-11T23:53:00.276+09:00` (KST) |
| `repo_commit` | `3ba2d34133fba8c2f14a43547b32ff122f306b72` |
| `simulator_commit` | **`null`** + `PRECONDITION_MISSING` — C1 에 시뮬레이터가 없다 |
| `items` | **9종** — `OUT_OF_SCOPE 5 · PENDING 2 · PARTIAL 2` · **`LOCKED` 0종** |
| `canonical_files` | 4종 SHA-256 (`schema.py`·`economic_config.yaml`·`event_schema.md`·`measurement_contract.md`) |
| `assumptions` | **4종** — `A-REFUND`·`A-DISCOUNT`·`A-SHIPPING`·`A-AI-INVESTMENT` |

### ★★ `G-10` — `true` 가 뜻하는 것을 세 곳에 못박았다

결정 **D-2** (사용자, 2026-09-11). **`true` 는 *"환불이 반영됐다"* 가 아니다** — *"환불 미반영이라는 사실을 확인하고 가정으로 수용했다"* 다. 그 구분이 기록에 없으면 다음 사이클이 `true` 를 보고 *"환불 처리됨"* 으로 읽는다.

**★ 오차 방향까지 적었다** — 방향이 없으면 읽는 사람이 보정할 수 없다:

```
revenue = Σ order_amount    환불된 매출을 뺄 수 없다
                            → contribution_profit 이 위로 치우친다 (과대평가)
                            → 아래로가 아니다
```

**실험 판정에는 영향이 없다** — `MEA-002` 가 실험 결과 산출에 시뮬레이터 생성분만 쓰도록 규정하고 그쪽은 환불을 생성하지 않는다.

| 자리 | 내용 |
|---|---|
| `config/economic_config.yaml` | `refund_adjusted: false` — **확정값**(내 전제가 아니다)임을 주석이 명시 |
| `config/gate1_lock.yaml` | `assumptions[0]` — `assumed`·`error_direction`·`why_no_verdict_impact`·`why_not_added`·`carried_in` |
| 게시물 `notices` | `REFUND_NOT_ADJUSTED` — **오차 방향을 메시지에 담았다.** ★ 화면에서 접히지 않아야 한다 |
| `freeze.GATE1_PRECONDITIONS` G-10 | *"확인함 · 미반영을 가정으로 수용"* |

### ★★ `null` 이 게시물까지 살아간 덕에 결정이 났다

**`false` 로 적었으면 아무도 묻지 않았다.** `met: null` 이 `freeze_status.json` 의 `unlocked_items[].met` 으로 나가 *"확인하지 않았다"* 가 보였고, 그것이 리드를 거쳐 사용자 결정을 불러왔다.

**같은 원칙이 이 사이클에서 네 층에 각각 구현됐다** — 세 번째 값을 만드는 것:

| 층 | 둘로는 표현 안 되는 것 | 세 번째 값 |
|---|---|---|
| 품질 검사 | 통과 / 실패 + **"검사했지만 대상이 0행"** | **`vacuous`** |
| 지표 | 값 있음 / 0 + **"근거가 없어 계산 못 함"** | **계산 불가 (`value: null` + `basis` 금지)** |
| 선행 조건 | 충족 / 미충족 + **"확인하지 않았다"** | **`met: null`** |
| 봉인 대조 | 일치 / 불일치 + **"대조하지 않았다"** | **`verification: not_run`** |

**네 번째가 이번에 실제로 필요해졌다** — §12.6.

### 해제 — `FREEZE-003`

봉인 대상을 변경하면 버전 상향 + 전 데이터 재생성 + Baseline 부터 전 전략 재실행. **`config/gate1_lock.yaml` 을 손으로 고치면 `tests/test_freeze.py` 의 해시 대조가 실패한다** — 그것이 이 파일을 기계가 쓰는 이유다.

## 8.3 하류로 넘기는 것

| 받는 쪽 | 넘기는 것 |
|---|---|
| **M-08** (`#45`) | 확정된 허용값·식별자 형식·타임존 표기 요구사항 · D-16/D-3 유도 규칙 문장 · **커머스 매핑 요구사항**(측정 계층이 소스별 예외를 갖지 않으므로 맞추는 쪽이 소스다) · `docs/contracts/.../CHANGELOG.md` 의 계약 수정 4건 |
| **M-09** (`#49`) | ★ **G-1~G-16 충족 상태가 이미 게시물에 있다** — `results/freeze_status.json` 의 `unlocked_items`. 16종 중 **미충족 2종**(`G-10` 사용자 결정 대기 → `met: null` · `G-15` M-09 미착수 → `met: false`)이고 나머지 14종은 근거와 함께 충족이다. `freeze.py` 는 이 판정을 읽어 Lock 기록을 만들면 된다 |
| **M-09** | `build_freeze_status()` 가 Lock 9종을 `owner_part` 와 함께 낸다 — 측정 계층 소관 4종(`EVENT_SCHEMA_v1`·`ECONOMIC_RULE_v1`·`CHURN_DEFINITION_v1`·`KPI_DEFINITION_v1`)만 우리가 봉인할 수 있고 5종은 `OUT_OF_SCOPE` 다 |
| **다음 사이클** | `_BLOCKS_METRICS`(필드→영향 지표)와 `kpi_report...blocked_by` 가 **양방향 사슬**이다. 화면은 한쪽을 뒤집어 인덱스를 만들 수 있고 그것은 재배열이지 새 분류가 아니다 (DB-012) |

---

# 9. Andrew 에게 전달해야 하는 것 (SendMessage 비활성 — 리드 중계 요청)

| # | 내용 |
|---|---|
| **1** | **정본 계약 경로가 `docs/contracts/measurement-publish/v1/` 로 바뀌었다.** `.agent-team/04-architecture/schemas/` 는 동결 스냅샷이다 |
| **2** | **`value_formatted` 가 계약에 들어갔다.** `m.status === 'ok' ? m.value_formatted : EM_DASH` 가 이제 성립한다. **화면은 숫자를 포맷하지 않는다** — `toLocaleString`·`toFixed`·`Number` 불필요. ★ **`ratio` 는 이미 ×100 되어 `"18.3%"` 로 온다. 다시 곱하지 말 것** |
| **3** | **`limit_note` 추가** — 선택 필드. `한계` 칩의 원천. `status` 는 `ok` 그대로다 |
| **4** | **`headline_code` 7종 → 8종** (`REJECTED_EVENTS`). **우선순위는 계약의 `description` 에 있다 — 화면이 순위를 정하지 않는다.** `counts.rejected_events > 0` 이면 `ALL_CLEAR` 가 계약상 불가능하다 |
| **5** | ★ **그가 쓰는 픽스처 14파일에는 `value_formatted` 가 없다** (계약보다 먼저 만들어졌다). 등재된 의도된 실패다. **픽스처를 고치지 말고**, `value_formatted` 가 없는 것을 전제로 화면을 짜지 말 것 — 실제 게시물에는 있다 |
| **6** | `empty-sink` 의 `vacuous` **7건은 오늘의 정상 상태**다. V5 가 이 7행을 표시해야 하고 `reason_code` 없이 `reason_detail` 만 온다 |
| **7** | `commerce-connected` 의 검사 **7건은 그 픽스처의 결함**이다(11종 누락, CR-2). **정답으로 삼지 말 것** — 구현은 항상 **18종**을 낸다. V5 는 18행 전제 |
| **8** | **`results/` 는 아직 없다** (§8.2). `.gitignore` 에 그가 필요한 3항목은 넣어 뒀으니 **`.gitignore` 를 고치지 말 것** — 소유 겹침 0 증명이 깨진다 |

---

# 10. 테스트 구성 — 46 → 407

| 파일 | 건수 | 무엇을 고정하나 |
|---|---|---|
| `test_isolation.py` | 6 | **봉인 — 0줄 수정** |
| `test_schema.py` | 59 | 16종·22컬럼 `assertEqual` · 허용값 거부 · 식별자 강제 · 타임존 3분기 · **계약 enum 대조** |
| `test_sink.py` | 39 | 파티션 보존 · 관용 모드 생존 · KST 정규화 · **Parquet 6종**(skipUnless) |
| `test_neutrality.py` | 9 | ★ **창구 중립성·의존성 봉쇄 — 소스 검사.** 8건 전부 **일부러 위반을 넣어 실패를 확인**했다 |
| `test_economics.py` | 29 | `cogs` 가 `0` 을 돌려주지 않는다 · 발생주의 · `N_targeted==0` · 판정 불가 ≠ `False` |
| `test_config_loader.py` | 19 | 타입 봉쇄(원가율 부재) · `ConfigError` 3경로 · 26.0% 검산 |
| `test_kpi_layers.py` | 40 | ★ **"세어 보니 0" vs "셀 근거가 없다"** · 이름 분리(R-2) · `index_date` 기본값 부재(R-1) · 파생 상태 4조건 |
| `test_quality_checks.py` | 41 | ★★ **8개 검사 × 3축**(정상→pass · 위반→fail · 0행→vacuous) · 18종 불변식 · 게이트 3값 |
| `test_publish_contract.py` | 30 | ★ **계약 수정 4건.** 16건은 `jsonschema` 없이 돈다 |
| `test_publish_envelope.py` | 38 | `value_formatted` 8종 · 로케일 무의존 · **fail-closed 7건** |
| `test_publish_pipeline.py` | 49 |
| `test_kpi_layers.py` | 40 | (위 참조) | ★ **J-1 대표 장면**(실제 파이프라인 산출물) · 순위 8종 도달 · 원자성 · **보안(Hidden Trait 미유출)** |

**skip 58건 (no-deps):** `PyYAML` 필요 경로(게시·config) · `jsonschema` 필요 경로(전체 스키마 검증) · `pyarrow` 필요 경로(Parquet). **전부 `BLOCKED:` 사유 문자열을 달았다.**
**skip 2건 (with-deps):** `test_parquet_request_without_pyarrow_raises`(설치 환경에서 탈 수 없는 에러 경로) · `test_loading_without_yaml_raises_config_error`(동일).

---

# 11. 검사가 잡아낸 내 오류 — **누적 14건**

*"검사를 만들면 그 검사가 계기를 잡는지부터 확인한다"* 의 실물이다. 전부 내가 틀렸고 검사가 맞았다.

| # | 검사 | 무엇을 잡았나 |
|---|---|---|
| **1** | `test_economics_has_no_source_literal` | 내가 쓴 `economics.py` **모듈 독트링**이 금지 토큰(`commerce`·`cost_rate`)을 담고 있었다 — 파일이 자기 규칙에 걸렸다 |
| **2** | 같은 검사 (kpi.py 로 확장 후) | `kpi.py` 의 `"Ecommerce_Service #29"` 가 부분문자열 `commerce` 로 걸렸다. ★ **검사 대상이 주장보다 좁았다** — `#46` AC-5 가 `kpi.py` 를 지목하는데 1차 구현은 `economics.py` 만 봤다 |
| **3** | `dump()` 의 계약 자기검증 + 전수 스키마 검증 | 1차 게시물이 **233건** 계약 위반이었다. 핵심 불변식(0 채우기)은 통과했지만 **구조**가 7종 중 6종에서 틀렸다 |
| **4** | `DQ-02b`(order_id 당 purchase 1건) | **내 테스트 픽스처**가 두 purchase 에 같은 `order_id` 를 썼다. 검사가 정당하게 `fail` 했고 픽스처가 틀렸다 |
| **5** | `test_measurement_layer_has_no_toplevel_third_party` | 화이트리스트가 `argparse`·`sys` 를 모르는 모듈로 잡았다 — **금지 목록은 아는 것만 막지만 화이트리스트는 모르는 것도 막는다** |
| **6** | 계약 문서 테스트의 **negative control** | 1차 작성한 8개 검사 중 **3개가 물지 않았다.** `assertIn` 이 *"어딘가 있으면 통과"* 라 §1 표가 틀려도 §8 이슈 초안이 같은 값을 담고 있으면 놓쳤다. **절 단위 파싱 + 양방향 대조**로 고쳐 8/8 이 됐다 |
| **7** | `test_yaml_import_is_contained` | `freeze.py` 가 YAML 을 직접 쓰려 해 A7-6 이 깨졌다. **규칙을 넓히지 않고** `config_loader.dump_yaml()` 로 경계를 재사용했다 — 규칙의 존재 이유가 "의존성 없는 import 그래프를 증명 가능하게" 이므로 넓히면 무의미해진다 |
| **8** | `test_freeze_reports_unmet_preconditions_honestly` | 내가 `G-15` 를 `met=False` 로 박아 넣었는데 **M-09 가 그 절차를 만들어 `True` 가 됐다.** 자기 웨이브의 진행으로 테스트가 낡았다 — 개별 G 를 박지 않고 `freeze.GATE1_PRECONDITIONS` 를 정본으로 대조하게 고쳤다 |
| **9** | `DQ-02b` (2회차) | `TestRepresentativeScene` 픽스처가 두 purchase 에 같은 `order_id` 를 썼다. 검사가 정당하게 `fail` 했고 **픽스처가 틀렸다** |
| **10** | `check_ownership.py` (2회) | `tests/test_contracts.py`·`test_measurement_contract.py` 가 소유 패턴에 걸리지 않았다. **`ownership.json` 을 고치는 대신** 파일명을 규약에 맞추고(`test_publish_envelope.py`) 검사 대상과 같은 파일로 합쳤다 — 소유 경계는 W2 가 정한 것이고 구현자가 넓히는 것이 아니다 |

> ## ★★ W6 에 남기는 문장 — **7불변식 통과는 계약 준수가 아니다** (리드 지시)
>
> `contracts.verify_core_invariants()` 는 **7개**만 본다. 전체 draft-2020-12 검증은
> `tests/test_publish_contract.py`·`test_publish_pipeline.py` 가 하고, **`jsonschema`
> 가 없으면 skip 된다.**
>
> ```
> 1차 게시물:  런타임 7불변식 → 통과 ✅       전체 스키마 검증 → 233건 위반 ❌
> ```
>
> **두 층이 서로를 대체하지 않는다.** 런타임 층은 *"화면에서 `?? 0` 을 부르는 위반"*
> 만 보고(그것이 fail-closed 의 대상이다), **구조 적합성**(정규식·`$ref`·
> `additionalProperties`·enum)은 테스트 층만 본다.
>
> **→ `verify_core_invariants` 가 통과했다는 것을 "계약을 준수한다"로 읽지 않는다.**
> `src/measurement/contracts.py:376` 의 `ponytail:` 마커가 그 경계와 업그레이드
> 트리거를 적어 두었다. W3 의 `AC-4d`(*"통과와 거부를 둘 다 확인한다"*)와 같은 자리다.

> **3번이 가장 중요하다.** `verify_core_invariants`(런타임, 7개 불변식)는 통과했는데 전체 스키마 검증은 233건을 냈다. **두 층이 서로를 대체하지 않는다** — 런타임 층은 *"화면에서 `?? 0` 을 부르는 위반"* 만 보고, 구조 적합성은 테스트 층이 본다. `ponytail:` 마커가 그 경계를 적어 둔 이유다.

---

# 12. ★★ Andrew 가 찾은 결함 4건 + Lock 실행이 드러낸 3건

**그가 고치지 않고 화면에 드러냈다.** *"조건을 느슨하게 했으면 초록으로 보였을 겁니다."* 그 판단이 이 넷을 살렸다.

## 12.1 ★★ ADR-0002 위반 — **가장 무겁다. 그가 옳았고 내가 틀렸다**

```
1차 구현:   results/*.json                        ← 전부 루트 (7종)
ADR-0002:   results/measurement/*.json            ← 6종
            results/data_quality_report.json      ← 예외 하나
```

**Andrew 의 리더가 원래 `results/measurement/index.json` 을 찾았다.** 그가 *"생산자를 정본으로 보고"* 내 출력에 맞춰 코드를 고쳤다 — **판단의 형식은 합리적이었지만 이 경우 생산자가 ADR 을 어기고 있었다.**

`ADR-0002` 는 이유까지 적어 두었다: 이후 사이클에서 `src/decision/` 이 `results/` 에 8종을 쓰므로 한 디렉터리에 섞이면 **누가 쓴 파일인지가 파일명 관례에만 의존**한다. 하위 디렉터리로 나누면 **소유 경계가 파일시스템에 드러난다.**

`data_quality_report.json` 만 루트인 것도 이유가 있다 — **`data_spec` §9 와 이슈 `#48` 본문이 그 경로를 명시했다. 일관성보다 정본이 우선한다.**

**→ 고쳤다. 그리고 `artifacts[].path` 를 W2 픽스처와 문자 단위로 대조하는 테스트를 넣었다** (`TestArtifactLayout`). 배치 규칙은 `publish.artifact_relative()` 한 곳에만 있다.

> ### ★ 리드 질문에 대한 답 — **Andrew 가 되돌려야 한다**
> *"생산자를 정본으로 본 판단이 맞는지"* → **형식은 맞지만 결론은 틀렸다.** 계약·ADR·픽스처가 정본이고 생산자가 그것을 따른다. 그의 **원래 기대(`results/measurement/index.json`)가 정확했다.**
> **계약에 위치를 고정할 필요는 없다** — `artifacts[].path` 가 이미 각 파일을 경로로 참조하고 `^(results|data/processed)/` 정규식이 상위 경계를 강제한다. 인덱스 위치만 계약에 없는데, **ADR-0002 + 픽스처가 그것을 정하고 테스트가 고정하므로 충분하다.**

## 12.2 R-1 · `views.V4.route` 가 `/metrics` 였다

W2 정합 라운드에서 Jonnathan 이 James 의 이름을 채택했다(`/metrics`→`/kpi`). 근거는 **산출물 이름과 1:1 이라 `views.route` 가 기계가독**이라는 것. **픽스처가 `/kpi` 이고 그것이 정본이다.**

**→ 고쳤다.** 6종 라우트 전부를 픽스처와 대조하는 테스트를 넣었다 — 하나만 고치면 다음에 다른 하나가 틀어진다.

## 12.3 R-2 · `spec_coverage` 자기모순 — **이미 고쳐져 있었다**

그가 본 것은 **수정 전 게시물**이다. `unmapped` 의 뜻을 *"실행된 검사가 없는 항목"* 으로 썼다가 *"검사가 아예 정의되지 않은 항목"* 으로 고쳤고(§11 의 별건), 현재 값은 `unmapped_spec_items: []` 이며 11종 전부 `covered_by` 가 있다. **자기모순 없음.**

**그의 지적은 유효했다** — 그 시점 게시물이 정말 그랬다. 실행 여부는 `worst_status` 가 말한다.

## 12.4 R-3 · `role` 전부 `none` · `blocks` 0건 · `experiment` 계층 없음

**셋 다 실재했다.** 원인은 내가 **D-4 를 잘못 읽은 것**이다:

> D-4 = *"역할 배정을 **GATE 2 에서 Lock 한다**"* ≠ *"C1 에서 게시하지 않는다"*

`kpi-definition-v1.md` §7 에 배정안이 **이미 있다**(P1 `incremental_contribution_profit` · P2 `qini_coefficient` · Guardrail 4종). W2 픽스처도 role 을 담았고 화면 규칙 `U-7` 이 `[P1]` 배지를 요구한다. **배정을 싣는 것과 봉인하는 것은 다른 행위**이고, Lock 되지 않았다는 사실은 `freeze_status` 의 `KPI_DEFINITION_v1.scope_note` 가 말한다.

| 항목 | 1차 | 수정 후 |
|---|---|---|
| `role` | 24종 전부 `none` | primary **2** · guardrail **3** · secondary **5** · none 28 |
| `blocks` | **0건** (픽스처는 13/13) | **11종** — `blocked_by` 의 역방향 |
| `layer: experiment` | **없음** | **14종** (전부 `unavailable`) |

★ **실험 계층을 빼는 것이 "계산 불가"를 숨기는 것과 같았다** — 목록에 없으면 *"계산 못 했다"* 가 아니라 *"그런 지표가 없다"* 로 읽힌다.

### ★ 그 과정에서 내가 또 틀렸다 — 계약이 28건으로 잡았다

실험 계층 `value` 에 `by_source` 를 담았다. **계약 `allOf[1]` 이 `layer == "experiment"` 에 대해 평범한 `metric_value` 를 못박는다.** 근거는 `MEA-002` 다 — *"실험 결과 산출에는 시뮬레이터 생성분만 쓴다."* 양쪽에 같은 계산 불가를 실으면 **"커머스에도 실험 판정이 있을 수 있다"** 는 뜻이 되고 그것이 `MEA-002` 가 막는 것이다.

**다른 계층의 모양을 계약 확인 없이 베낀 것이다.** `test_experiment_metrics_are_not_split_by_source` 가 고정한다.

## 12.5 ★ 그리고 테스트가 새 배치를 검증하지 않고 있었다

경로를 바꾼 뒤 **no-deps 는 `OK` 였고 with-deps 만 11건 실패**했다. 원인: 테스트가 `glob("*.json")` 을 써서 `measurement/` 를 못 보고 **대상 집합이 7 → 1 로 줄었는데도 통과**했다. no-deps 에서는 그 테스트들이 PyYAML 로 skip 되어 아예 안 돌았다.

**§11 의 "검사 대상이 주장보다 좁다" 패턴이 세 번째로 나왔다.** `rglob` 으로 고치고 **배치 자체를 단언하는 테스트 5건**을 넣었다 — 집합이 줄면 실패한다.


## 12.6 ★★ Lock 을 실행하니 **A7 이 무너질 수 있었다** — 네 번째 `not_run`

Lock 기록은 `config/gate1_lock.yaml` 이고 **YAML 이다.** 그런데 `isolation.yml` 은 의존성을 설치하지 않는다(`ISO-005`). 그래서:

```
Lock 기록 생성  →  load_record() 가 PyYAML 을 요구  →  ConfigError
                →  isolation.yml 이 영구 실패
                →  ★ 격리 CI 가 격리와 무관한 이유로 빨개진다
```

**가정 A7 이 막으려는 바로 그 실패 양식을, 내가 Lock 을 실행하면서 만들었다.** 실제로 no-deps 전체 테스트가 `ERROR` 로 떨어졌다.

**두 순진한 해법이 다 틀렸다:**

| 해법 | 왜 틀렸나 |
|---|---|
| `ConfigError` 로 터뜨린다 | 격리 CI 가 깨진다 — A7 위반 |
| `None` 으로 떨어뜨린다 | 기록이 실재하는데 *"봉인을 시작하지 않았다"* 가 된다 — **거짓말** |

**→ `RECORD_UNREADABLE` 센티넬 + `verification: "not_run"`.** 내가 `VERIFICATION_STATES` 에 정의해 두고 **한 번도 쓰지 않았던 값**이 정확히 이 자리였다.

```
overall: "partial"        완전 봉인이 아니다 — C1 에서 항상 참
verification: "not_run"   ★ 대조하지 않았다. 통과가 아니다
```

**두 축이 분리돼 있어서 정직한 쌍이 가능했다.** `overall` 하나였다면 거짓말을 하거나 CI 를 깨는 수밖에 없었다.

해시 대조는 `tests-with-deps.yml` 이 한다 — **두 잡의 차이가 곧 "의존성이 필요한 검증"의 목록**이라는 원칙이 여기서도 그대로 작동한다.

## 12.7 `lock_record` 는 **요약이다. 기록 전체가 아니다**

계약이 `path` + `sha256` + 핵심 4필드만 받고 `additionalProperties: false` 다. 1차 구현이 `gate1_lock.yaml` 전체를 넣어 **계약이 3건으로 거부**했다.

**계약이 옳다:** 게시물이 기록을 복제하면 **진실이 둘**이 되고 갈라지면 정본을 알 수 없다. **포인터 + 해시면 기록이 조용히 바뀐 것도 드러난다.**

## 12.8 그리고 또 내 테스트가 낡았다 — 두 번째

`test_freeze_reports_unmet_preconditions_honestly` 가 `overall == "not_started"` 를 박아뒀는데 **Lock 을 실행하니 `partial` 이 됐다.** `G-15` 때와 **같은 실수**를 반복했다.

**→ 상수를 박지 않고 `freeze.verify()` 를 정본으로 대조하게 고쳤다.** 정본이 하나면 낡을 자리가 없다.


<!-- 검증 실행 기록 (재현용)
     Python 3.14.6 (로컬) · 3.12.4 (venv, CI parity)
     jsonschema 4.26.0 · referencing 0.37.0 · pyarrow 25.0.1 · PyYAML 6.0.3
     AI_ROI HEAD  3ba2d34133fba8c2f14a43547b32ff122f306b72
     Ecommerce_Service  git status --porcelain → 빈 출력 (변경 0)
     Plan 서브모듈 포인터  스테이징 0
-->
