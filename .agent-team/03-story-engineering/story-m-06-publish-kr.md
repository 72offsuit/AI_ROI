---
story_key: M-06
epic: 범위 M — 측정 계층 (이슈 #42)
issue: "(이슈 없음 — AIROI-M8 초안 필요 · 결정 D-10)"
title: 측정 산출물 게시 — results/ 게시 계약 v1 구현
status: done   # W5 Phillip 완료 — T1~T8 + Andrew 지적 4건 수정(ADR-0002 배치 · V4 /kpi · role·blocks · experiment 계층). 게시물 7종 계약 위반 0건
owner: Phillip (W5-A)
phase: "2''"
blocked_by: ["M-02 (#54)", "M-03 (#47)", "M-04 (#46)"]
blocks: ["d-01 실제 게시물 확인", "d-02"]
user_decisions_required: ["D-10", "D-17", "B-11(리드)"]
source_hash: 453eccc2172bc7d2
source_files: 24
---

# M-06 · 측정 산출물 게시 (T2.7)

> **이 파일만 읽고 구현한다.** 인용에는 전부 `[Source: 경로#절]` 을 붙였다.

---

# 0. 작업 전 — 매번 확인하는 3줄 *(task-graph §3 T3.2)*

| # | 절대 제약 | 어기면 |
|---|---|---|
| **①** | **git·이슈 권한은 L1(제안만)이다.** commit·push 는 사용자가 **"커밋해"/"푸시해"** 를, 이슈 생성·수정·PR 은 **"이슈 만들어"/"PR 올려"** 를 명시한 뒤에만. **승격을 스스로 추론하지 않는다.** merge · Issue close · 브랜치 삭제 · `push --force` · `reset --hard` · `rebase` 는 **항상 개별 승인**. `main` 직접 커밋 금지 · `git add -A` 금지(경로 명시) · `git add Plan` 금지 | 사용자 결정을 대신한 것이 된다 |
| **②** | **`Ecommerce_Service` 파일 변경 0건.** 별도 저장소이고 사용자가 명시적으로 제외했다. **읽기는 허용**된다. 편집이 필요해지면 **멈추고 보고한다** | charter §5 위반 |
| **③** | **결손을 0 으로 채우지 않는다.** 명시적으로 기록하고 의존 지표는 **계산 불가로 표시**한다. **미실행 검증을 통과로 표시하지 않는다** — 실행 불가는 `BLOCKED` 로 **이유와 함께** | ★ **이 프로젝트의 USP-1 이 끝난다** |

`[Source: AGENTS.md#반드시-지킬-것]` · `[Source: docs/GIT_WORKFLOW.md#6]` · `[Source: .agent-team/00-plan/charter.md#6.1]` · `[Source: .agent-team/00-plan/task-graph.md#3 W3]`
> **기계가독 정본은 `.agent-team/04-architecture/schemas/*.schema.json` 이다.** 이 문서와 충돌하면 **스키마가 정본이다.**

---

# 1. 메타

| | |
|---|---|
| **대상** | W2 T2.7 — ★ **소유 이슈가 없다.** 신규 초안 `AIROI-M8` 이 필요하다 (결정 **D-10**) |
| **담당** | Phillip · W5-A |
| **Phase** | **2''** — M-02·M-03·M-04 완료 후 |
| **차단하는 것** | **d-01 의 실제 게시물 확인** · d-02 전체 |
| **커밋 type** | `feat` |

> ## ⚠ 이 기능을 소유한 이슈가 없다
> `usp.md` §1.4 조건 C-1 이 이 기능을 요구했고 `core-features.md` CF-6 이 *"이슈 없음 — 새로 발견"* 으로 기록했다.
> **이슈 발행은 L3 권한이다.** 사용자 지시 없이 만들지 않는다.
> **구현은 이슈 없이 진행할 수 있다** — 다만 추적이 흐려진다는 사실을 PR 에 적는다.
> `[Source: .agent-team/03-service-planning/core-features.md#CF-6]`

> ## ★ 이 프로젝트에는 HTTP API 가 없다
> 대시보드는 **파일을 읽는다** (`DB-013` — *"별도 API 서버를 두지 않는다"*).
> 이 스토리의 "계약"은 REST 엔드포인트가 아니라 **게시물의 경로·형식·갱신 시점·읽는 쪽의 제약**이다.
> **없는 REST API 를 지어내지 않는다.**
> `[Source: .agent-team/04-architecture/api-contracts.md#0]`

---

# 2. 스토리

> **`P-팀`으로서 나는 대시보드가 `data/raw/` 를 뒤지지 않고 `results/` 의 파일만 읽어도 되기를 원한다.**
> 왜냐하면 `DB-014` 의 대시보드 읽기 허용 목록에 **`data/raw/` 가 없고**, 예외를 한 번 열면 `data/hidden/` 예외 요구가 이어질 자리를 만들기 때문이다.
> `[Source: .agent-team/03-service-planning/user-stories.md#US-10]`

---

# 3. 인수 조건 (AC)

## AC-1 · 게시 경로

- [ ] `results/measurement/` 아래에 **6종 + 인덱스**를 게시한다
- [ ] `results/data_quality_report.json` 은 **루트에** 둔다 — `data_spec` §9 가 지정한 경로다
- [ ] `index.json` 의 `artifacts[].path` 가 `^(results|data/processed)/` 를 만족한다 (스키마 정규식이 강제)

## AC-2 · 공통 봉투

- [ ] 전 게시물이 같은 봉투를 갖는다 — `contract_version`·`artifact`·`run_id`·`generated_at`·`timezone`·`provenance`·`notices`
- [ ] `contract_version == "measurement-publish/v1"`
- [ ] **`generated_at` 이 KST(`+09:00`)** 다 — `Z` 표기는 스키마 정규식에서 실패한다
- [ ] `run_id` 가 `^MR-[0-9]{8}-[0-9]{6}-[0-9a-f]{8}$` 이고 **같은 실행의 산출물이 전부 같다**
- [ ] `provenance.generated_by` 를 **생성기가 런타임에 자기 실행을 기록한다** — 설계 시점에 지어내지 않는다

## AC-3 · ★ 핵심 불변식 4개 — 스키마가 거부한다

- [ ] **`status` 가 `unavailable`/`blocked`/`not_run` 이면 `value` 는 반드시 `null`** — 0 을 넣으면 검증 실패
- [ ] **계산된 값에는 `basis` 가 반드시 있고, 계산 불가에는 있을 수 없다**
- [ ] **검사 대상이 0행이면 `pass` 일 수 없다** — `vacuous`
- [ ] **판정할 수 없는 것은 값이 아니라 사유로 준다**

## AC-4 · 원자성

- [ ] `.staging/<run_id>/` 에 쓰고 → 자기 스키마로 검증 → `os.replace()` → **`index.json` 을 마지막에**
- [ ] staging 디렉터리를 완료 후 지운다
- [ ] **자기 스키마를 통과하지 못한 산출물은 게시하지 않는다** (fail closed)
- [ ] 실패 시 `index.json` 에 `status: failed` + 사유 · `publish_result: partial`

## AC-4b · ★ 계약 결함 수정 (리드 판정 B-11 · Q-2)

- [ ] `docs/contracts/.../index.schema.json` 의 `headline_code` enum 에 **`REJECTED_EVENTS` 추가** (7종 → 8종)
- [ ] **8종 우선순위를 계약에 명시**한다 — 화면이 순위를 정하지 않는다
- [ ] **`counts.rejected_events > 0` 이면 `ALL_CLEAR` 를 고를 수 없다**는 것이 계약으로 성립한다
- [ ] **`.agent-team/04-architecture/schemas/` 원본은 고치지 않는다**
- [ ] **의도된 차이를 문서로 남기고, T6 대조 테스트가 그 목록 밖의 차이를 실패로 만든다**
- [ ] ★ **`value_formatted` 를 계약에 추가**한다 — `ok`·`unconfirmed` 필수 / 계산 불가 금지 (§4.16)
- [ ] ★ **`limit_note` 를 계약에 추가**한다 — 선택 필드. `한계` 칩의 원천 (§4.17)
- [ ] ★ **픽스처 4개 규칙**(§4.15) — 도구의 하드코딩 결함을 **고치지 않고 결함으로 표기**한다
- [ ] ★ **픽스처의 의도된 실패를 목록으로 명시**하고, **목록의 *모든* 항목이 실제로 실패하는지** 단언한다 (§4.14). ★ **개수를 본문에 적지 않는다** — 항목이 늘면 숫자가 어긋나고, **세지 않은 항목은 통과해도 모른다.** **픽스처를 고치지 않는다**

## AC-4c · ★ `headline_code` 순위를 **기계가 검사한다** (Thomas NR-3)

- [ ] **`choose_headline_code(counts, ingestion_report)` 단일 함수**가 순위를 구현한다 — 화면·테스트가 같은 함수를 쓴다
- [ ] **픽스처 2벌로 `headline_code` 를 재계산**해 픽스처 값과 일치함을 단언한다 (`SINK_EMPTY`·`QUALITY_VIOLATION`). **enum 소속 검사로는 순위를 못 잡는다**
- [ ] **`SINK_EMPTY` 의 입력은 `ingestion_report.totals.events_ingested`** 라고 계약에 적는다 — `verdict.counts` 에는 수집 건수가 없다(실측)
- [ ] ★ **`events_ingested.status != "ok"` 이면 `SINK_EMPTY` 를 고르지 않는다** — 모르는 것을 0 으로 읽지 않는다. `notices` 에 보류 사유를 남긴다
- [ ] 표본 밖 8종 전부를 `counts` 를 지어내 통과시키는 단위 테스트가 있다

## AC-4d · ★★ 계약 수정을 **읽어서 판단하지 않는다 — validator 로 확인한다** (리드 지시 · Matthias RL-3 · Thomas TL-2)

> **이번 사이클의 계약 수정은 전부 JSON Schema 의미론에 걸려 있는데, W3 은 그것을 저장소에서 실행할 수 없었다.**
> Thomas 도 Matthias 도 *"읽어서 맞다고 판단"* 한 상태로 남겼다. **그 자리를 이 스토리가 실행으로 닫는다.**

- [ ] ★ **`jsonschema` 가 있는 환경에서 수정 전/후 스키마로 두 인스턴스를 직접 돌린다.** 통과/거부가 **의도와 일치**함을 확인하고 결과를 PR 에 붙인다
- [ ] **`value_formatted` 금지 형태** — ★ **`AC-4e` 의 네 레코드 표로 갈음한다.** 거기서 ③(`basis` 있음)까지 함께 본다 — `not` 형태가 틀리면 **`value_formatted` 가 새는 것보다 `basis` 금지가 사라지는 쪽이 더 크다**
- [ ] **`value_formatted` 필수 형태** — `ok` 인데 `value_formatted` 가 없으면 **거부**된다. `unconfirmed` 도 같이 확인한다 (`allOf[1]` 을 빠뜨리기 쉽다)
- [ ] ★ **`vacuous` 교체 형태** — `{"status":"vacuous","examined_rows":0,"violations":null,"reason_detail":"…"}` 가 **통과**하고, `reason_code` 를 넣으면 **거부**된다. **둘 다 확인한다** — 하나만 보면 만족 불가능해진 것을 못 잡는다
- [ ] **`empty-sink` 픽스처의 `vacuous` 7건이 수정 후 스키마에서 어떻게 되는지** 확인하고 §4.14 의도된 실패 목록과 대조한다 — ★ **결과는 이미 알고 있다: 7건 전부 `reason_code:"NOT_RUN"` 이라 거부된다**(W3 실측). **§4.14 에 등재해 두었으므로 회귀가 아니다.** 확인이 어긋나면 그때가 이상 신호다
- [ ] **하나라도 의도와 다르면 계약을 고치지 않고 멈춘다.** 스키마 문장을 믿고 진행하지 않는다

> **왜 AC 인가:** *"고쳤다"* 와 *"고친 것이 의도대로 동작한다"* 는 다르다. **NR-1 이 그 차이의 실물이다** — 자연스러운 수정이 조용히 무력화됐다.
> `jsonschema` 는 **M-05 의 `requirements-dev.txt`** 로 들어온다. 그 전이면 **이 AC 는 `BLOCKED`** 이고, **계약 수정도 함께 보류한다.**

## AC-4e · ★★★ **네 레코드를 실제로 넣어 본다** — 이 변경은 회귀 검사다 (리드 지시 2026-09-11)

> **이 계약 수정은 새 필드를 더하는 일이 아니다.** `allOf[2].then.not` 을 건드리므로 **지금 작동 중인 `basis` 금지가 사라질 수 있다.**
> **`{required:["basis","value_formatted"]}` 로 쓰면 `basis` 만 있는 계산 불가 레코드가 통과한다** (§4.16 표 3행).
> **픽스처에 그런 레코드가 없어서 기존 테스트는 전부 통과한다. 조용한 회귀다.**

- [ ] ★ **계산 불가 분기에 네 레코드를 넣어 결과를 표로 남긴다** — 수정 전/후 둘 다

| # | 레코드 (`status: "unavailable"`) | 수정 **전** | 수정 **후** |
|---|---|---|---|
| ① | `basis` 없음 · `value_formatted` 없음 | 통과 | **통과** |
| ② | `value_formatted` 있음 | 통과 | **거부** |
| ③ | ★ **`basis` 있음** | **거부** | **거부** ← ★ **여기가 회귀 지점** |
| ④ | 둘 다 있음 | 거부 | **거부** |

- [ ] ★★ **③이 수정 후에도 거부되는지 확인한다.** 통과로 바뀌었으면 **`not` 형태가 틀린 것**이다. **되돌리고 `{anyOf:[…]}` 로 고친다**
- [ ] **`jsonschema` 가 없어도 이 검사는 실행한다** — `not` 은 논리 연산이므로 표준 라이브러리로 계산된다:

```python
# tests/test_publish_contract.py — jsonschema 유무와 무관하게 항상 돈다
# 계약 파일에서 allOf[2].then.not 을 읽어와 아래 논리로 판정한다.
# required:[a,b] 로 쓰면 "둘 다 있지는 않다" 가 되어 basis 금지가 사라진다.

def _not_required(keys, inst):
    return not all(k in inst for k in keys)

def _not_anyof(keysets, inst):
    return not any(all(k in inst for k in ks) for ks in keysets)

CASES = [
    ({},                                      True),   # 정상
    ({"value_formatted": "0원"},              False),  # value_formatted 금지
    ({"basis": {"population": "P"}},          False),  # ★ basis 금지 — 회귀 지점
    ({"basis": {"population": "P"},
      "value_formatted": "0원"},              False),
]

def test_uncomputable_branch_rejects_each_key_individually():
    for inst, expected in CASES:
        assert _not_anyof([["basis"], ["value_formatted"]], inst) is expected
    # 틀린 형태가 3번을 통과시킨다는 것도 함께 고정한다
    assert _not_required(["basis", "value_formatted"], CASES[2][0]) is True
```

- [ ] ★ **이 테스트는 `jsonschema` skip 대상이 아니다.** 계약 파일에서 `allOf[2].then.not` 을 **읽어와** 위 논리로 판정한다 — 스키마가 바뀌면 테스트가 따라 깨진다
- [ ] **`basis` 금지가 살아 있다는 것을 W5 가 스스로 증명한 기록**을 PR 에 남긴다. *"고쳤다"* 가 아니라 *"기존 방어가 그대로다"* 를 적는다

> **왜 이 정도로 다루나:** `basis` 의 유무가 *"측정됨"* 의 판별자다 (`ADR-0003`). **계산 불가에 `basis` 가 붙으면 근거 없는 값이 근거 있는 값으로 읽힌다** — **이 프로젝트의 USP-1 이 무너지는 정확한 지점**이다.
> **자연스러운 한 줄 편집으로 사라지고, 픽스처가 그것을 못 잡는다.** 그래서 인수조건으로 박는다.

## AC-5 · 계산 주체 (`DB-012`)

- [ ] **출처 분류·계산 불가 판정·집계를 게시 시점에 끝낸다**
- [ ] `by_source.{commerce,simulator}` **두 키가 항상 존재한다** — 0건이어도 빼지 않는다
- [ ] **계층 1·2 KPI 에 `combined` 키가 없다** (R-7 · 스키마가 거부)
- [ ] `verdict` 를 **게시물이 집계한다** — 화면이 세지 않는다
- [ ] `blocked_by` / `blocks_metrics` **양방향 사슬**을 게시 시점에 넣는다

## AC-6 · 보안 — 거부 레코드 원문을 게시하지 않는다 ★

- [ ] `rejection_report.samples[]` 는 `event_type`·`partition_date`·`source`·`problems`·`offending_fields`(**필드 이름만**) 만 담는다
- [ ] `offending_values` 의 **키가 DATA-003 22컬럼으로 제한**된다
- [ ] `additionalProperties: false` 를 통과한다
- [ ] `rejected.jsonl` 원문을 `results/` 로 **복사하지 않는다**

## AC-7 · 창구 중립성

- [ ] `publish.py` **한 곳만** 출처를 안다. `kpi.py`·`economics.py` 는 모른다
- [ ] `partition_by_source()` 가 `sink.event_source()` 를 쓴다 — **재분류하지 않는다**
- [ ] `provenance.simulator_commit` 을 얻으려고 **`src/simulator/` 를 읽지 않는다** — 실행 메타로 주입받는다

## AC-8 · 회귀 없음

- [ ] `python3 -m unittest discover -s tests` — 기준선 46건 회귀 0
- [ ] `python3 -m unittest tests.test_isolation -v` — 통과
- [ ] **의존성 설치 없이** 통과 (`jsonschema` 는 dev 전용 → 없으면 skip + 사유)
- [ ] `python3 .agent-team/04-architecture/tools/check_ownership.py` — PASS

---

# 4. 개발 컨텍스트 (`developer_context`)

## 4.1 왜 게시가 필요한가 — 3줄

1. 관측 화면군의 원천은 Event Sink 의 `manifest.json` 이고, 그것은 Sink root(= `data/raw/`) 아래에 있다
2. 그런데 `DB-014` 의 대시보드 읽기 허용 목록은 **`results/` 와 `data/processed/` 뿐이고 `data/raw/` 가 없다**
3. → **측정 계층이 `results/` 에 게시하고 대시보드는 그것만 읽는다.** `DB-013`·`DB-014` 를 한 글자도 고치지 않고 성립한다

**격리 위반이 아니라는 실측 근거:**

```python
# tests/test_isolation.py
FORBIDDEN_PATHS = {
    "src.measurement": ("data/hidden", "data/ground_truth"),   # ← results/ 가 없다
    "src.simulator":   ("results/",),                          # ← simulator 만 금지
}
```

그리고 `docs/data_spec.html` §9 가 이미 규정한다 — *"모든 검사는 `src/measurement/validate.py` 에서 실행하고 **`results/data_quality_report.json`** 에 결과를 남긴다."*

**새 경로를 발명하지 않았다. 기존 규칙의 확장 적용이다.**
`[Source: .agent-team/04-architecture/api-contracts.md#1]` · `[Source: .agent-team/04-architecture/adr/ADR-0001-publish-not-api.md]`

> ### 정본 긴장 T-1 — 코드 주석과 M-08 문서에 남긴다
> `data_spec` §17.4 의 경로 표는 `results/` 접근 주체를 *"decision · orchestration"* 으로 적고 **measurement 를 넣지 않았다.**
> 그러나 같은 문서 §9 는 measurement 가 그곳에 쓰도록 규정하고, **강제 수단인 `tests/test_isolation.py` 는 막지 않는다.**
> → **강제되는 규칙(테스트)과 명시 규정(§9)이 일치하므로 게시는 성립한다.** §17.4 표는 **읽기 주체를 열거한 것**으로 읽는다.
> **`Plan/` 수정은 권한 밖이므로 고치지 않고 기록한다.**

## 4.2 파일 배치

```text
results/
├── data_quality_report.json          ← V5 · 정본이 지정한 경로. 발명 금지 · 이동 금지
└── measurement/                      ← 측정 계층 게시 영역 (신설)
    ├── index.json                    ← 대시보드가 가장 먼저 읽고, 게시는 마지막에 쓴다
    ├── ingestion_report.json         ← V1 수집 현황
    ├── rejection_report.json         ← V2 계약 위반
    ├── field_coverage_report.json    ← V3 필드 충족률
    ├── kpi_report.json               ← V4 KPI
    ├── freeze_status.json            ← V6 봉인 상태
    └── .staging/<run_id>/            ← 게시 중 임시. 완료 후 삭제
```

**`results/measurement/` 로 한 겹 내린 이유:** 이후 사이클에서 `src/decision/` 이 `results/churn_predictions.csv` 등 8종을 같은 디렉터리에 쓴다. **한 디렉터리에 섞이면 누가 쓴 파일인지가 파일명 관례에만 의존**하게 되고 소유 경계가 파일시스템에서 사라진다.
`data_quality_report.json` 하나만 루트에 두는 것은 **정본이 그 경로를 명시했기 때문**이며 **일관성보다 정본이 우선**한다.
`[Source: .agent-team/04-architecture/adr/ADR-0002-results-measurement-subdir.md]`

## 4.3 공통 봉투

```jsonc
{
  "contract_version": "measurement-publish/v1",
  "artifact": "ingestion_report",
  "run_id": "MR-20260911-090000-0a1b2c3d",
  "generated_at": "2026-09-11T09:00:00.000+09:00",   // ★ KST 강제. 'Z' 는 패턴에서 실패
  "timezone": "Asia/Seoul",
  "provenance": { ... },
  "notices": [ ... ],
  ... 산출물별 본문 ...
}
```

### `generated_at` 이 KST 를 정규식으로 강제하는 이유

`schema.py` 는 *"모든 timestamp 는 KST 단일 타임존, UTC 혼재 불허"* 라고 선언하지만 **`sink.py` 의 `manifest.created_at` 은 UTC 로 쓴다.**
**게시 계층은 이 어긋남을 계약으로 막는다** — `+09:00` 이 아닌 문자열은 스키마 검증에서 실패하고, 검증에 실패한 산출물은 게시되지 않는다.

> **M-01(`#53`)이 `manifest.created_at` 을 KST 로 고친다.** 두 스토리가 같은 문제를 양쪽에서 막는다.

### `provenance` (`DB-013`)

| 필드 | C1 값 |
|---|---|
| `schema_version` | `schema.py SCHEMA_VERSION` — `event-schema-v1.0-draft` |
| `repo_commit` | `git rev-parse HEAD`. 얻지 못하면 `null` + `null_reason` |
| `data_version` | ❌ **`null` + `null_reason: PRECONDITION_MISSING`** — `data/data_version.yaml` 이 없다 |
| `simulator_commit` | ❌ **`null` + `null_reason: PRECONDITION_MISSING`** — C1 에 시뮬레이터가 없다 |
| `config_hashes` | 읽은 config 파일의 SHA-256 (키는 저장소 기준 상대 경로) |
| `source_root` | Sink root. 예 `data/raw` |
| `sink_manifest_sha256` | 원천 manifest 의 해시 |
| **`generated_by`** | ★ **생성기가 런타임에 자기 실행을 기록한다** |
| `publisher_version` | 게시 모듈 버전·커밋 |

> **`simulator_commit` 을 빈 문자열이나 `"unknown"` 으로 채우지 않는다.** `null` + `null_reason`.
> **`measurement` 는 `src/simulator/` 를 읽어서 이 값을 얻지 않는다** — 실행 메타로 주입받는다.
> **값을 나르는 것은 의존이 아니지만, 읽으러 가는 것은 의존이다** (창구 중립성).
> `[Source: .agent-team/04-architecture/api-contracts.md#3.2]`

### `notices` — 가정을 산출물에 붙여 나른다

| code | level | C1 에서 언제 |
|---|---|---|
| `SINK_EMPTY` | limitation | 이벤트 0건일 때 |
| `REFUND_NOT_ADJUSTED` | assumption | **항상** (가정 `A-REFUND`) |
| `CHURN_THRESHOLD_UNCONFIRMED` | assumption | 이탈 관련 지표가 있을 때 |
| `GATE1_NOT_PASSED` | limitation | `freeze_status` 에 **항상** |
| `INGESTION_GAP_UNDECIDABLE` | limitation | 수집 공백이 있을 때 |
| `DASHBOARD_NOT_ISOLATION_CHECKED` | limitation | 격리 검사 확장을 하지 않기로 결정한 경우 |

> **가정은 시간이 지나면 사실로 읽힌다. 그래서 문서가 아니라 산출물에 붙인다.**
> `[Source: .agent-team/04-architecture/design-patterns.md#P-12]`

## 4.4 ★ `metric_value` — 이 프로젝트의 USP-1 이 사는 자리

```jsonc
// 계산됨 — 값과 기준이 있다
{ "status": "ok", "value": 41283400, "unit": "krw",
  "basis": { "population": "purchase 이벤트", "denominator_definition": "분모 없음 (합계)",
             "denominator": null, "observed_count": 1204,
             "window": { "direction": "retrospective", "days": 42 } } }

// 미확정 — 값을 내되 사용한 파라미터를 밝힌다
{ "status": "unconfirmed", "value": 0.1834, "unit": "ratio",
  "basis": { ..., "denominator": 894 },
  "reason_code": "PARAM_UNCONFIRMED",
  "reason_detail": "이탈 임계값이 GATE 1 에서 확정되지 않았다.",
  "params_used": { "no_purchase_days": 42, "at_risk_days": 28 } }

// 계산 불가 — value 는 null 이고 basis 를 가질 수 없다
{ "status": "unavailable", "value": null, "unit": "krw",
  "reason_code": "NO_COST_BASIS",
  "reason_detail": "주문 1,204건 중 1,204건에 unit_cost 없음. 원가율을 곱해 추정하지 않는다.",
  "blocked_by": [ { "kind": "schema_gap", "ref": "unit_cost", "reason_code": "NO_COST_BASIS" } ] }
```

### 스키마가 강제하는 것 — 실행 확인됨 (위반 시도 15건 중 거부 15건)

| 규칙 |
|---|
| `unavailable`·`blocked`·`not_run` → `value` 는 **반드시 `null`** |
| **계산된 값에 `basis` 필수** |
| **계산 불가에 `basis` 금지** — 현행 `not: {required: ["basis"]}`. ★ **이 스토리가 여기에 `value_formatted` 를 더한다. 배열로 늘리면 틀린다** → §4.16 |
| 계산 불가에 `reason_code` + `reason_detail` **필수** |
| `unconfirmed` → `params_used` 필수 · `reason_code == PARAM_UNCONFIRMED` |
| `unit: ratio` + 계산됨 → `basis.denominator` 필수 |
| **`basis.denominator == 0` → `ok` 일 수 없다** |
| `derived: true` → `derivation` 필수 |
| **KPI 계층에서 `combined` 키 금지** |
| 거부 샘플의 값은 **22컬럼만** |
| `provenance.generated_by` 필수 |
| `generated_at` 이 **KST** |

`[Source: .agent-team/04-architecture/schemas/common.schema.json#$defs.metric_value]`

## 4.5 ★ 0 을 언제 써도 되는가 — 가장 중요한 판단

**관측 결과로서의 0 은 정직한 값이다.** 이것을 계산 불가로 적으면 **그것도 거짓말이다.**

| 상황 | 올바른 표현 | 틀린 표현 |
|---|---|---|
| 이벤트가 0건 들어왔다 | `ok` + `0` + `basis.observed_count: 0` | `unavailable` — **우리는 0건임을 안다** |
| `coupon_use` 0건이라 쿠폰 사용 건수가 0 | `ok` + `0` + `basis.population: "coupon_use 이벤트"` | `unavailable` |
| 거부율 = 0건 / 0건 | `unavailable` (분모가 없다) | `{"value": 0}` |
| 매출 (`purchase` 0건) | `unavailable · NO_SOURCE_EVENT` | `{"value": 0}` — **매출 0원과 근거 없음은 다르다** |
| COGS (원가 근거 없음) | `unavailable · NO_COST_BASIS` | `0` 또는 `revenue × 0.74` |

> **가르는 기준:** *"세어 보니 0"* 은 **`ok`**(기준이 있다). *"셀 근거가 없다"* 는 **`unavailable`**(기준이 없다).
> `[Source: .agent-team/04-architecture/api-contracts.md#4.5]`

**`examples/commerce-connected/kpi_report.json` 이 이 구분을 한 파일에 담고 있다** — `coupon_usage_count` 는 `ok`+0, `coupon_cost` 는 `unavailable`. **테스트가 이 대비를 재현한다.**

## 4.6 ★ `blocked_by` 양방향 사슬 — 화면이 추론하면 `DB-012` 위반

**게시 시점에 넣는다.**

```jsonc
"blocked_by": [
  { "kind": "metric",     "ref": "cogs",       "reason_code": "NO_COST_BASIS" },
  { "kind": "schema_gap", "ref": "discount",   "reason_code": "MISSING_FIELD" },
  { "kind": "event_type", "ref": "coupon_use", "reason_code": "NO_SOURCE_EVENT" },
  { "kind": "parameter",  "ref": "C_rule",     "reason_code": "PARAM_UNCONFIRMED" }
]
```

`kind` **9종** — `field` · `schema_gap` · `event_type` · `metric` · `table` · `model_output` · `strategy` · `parameter` · `dependency`.

**`kind` 를 나눈 이유:** *"필드가 비었다"* 와 *"컬럼 자체가 없다"* 와 *"테이블이 없다"* 는 **해결 주체가 다르다.** 앞은 기록자, 가운데는 SRS 개정, 뒤는 구현이다.

| 방향 | 어디에 | 예 |
|---|---|---|
| 원인 → 영향 | `field_coverage_report.fields[f].blocks_metrics`<br>`field_coverage_report.schema_gaps[].blocks_metrics` | `unit_cost` → `cogs` · `contribution_profit` |
| 영향 → 원인 | `kpi_report.metrics[].value.blocked_by` | `contribution_profit` ← `cogs` · `discount` |
| 영향 → 하위 | `kpi_report.metrics[].blocks` | `cogs` → `contribution_profit` |

> **사슬은 `kpi.py` 의 지표 정의(어떤 이벤트·필드에 의존하는가)에서 파생되며 손으로 관리하는 표가 아니다.**
> **`tests/test_publish_contract.py` 가 `blocked_by` 와 `blocks_metrics` 의 역방향 일치를 검사할 것을 권고한다** — 사슬이 틀리면 화면이 틀린 인과를 보여준다.
> `[Source: .agent-team/04-architecture/adr/ADR-0009-blocker-chain.md]`

## 4.7 산출물 6종 + 인덱스 — 실측 구조

**픽스처 2벌이 실재한다.** 구현 결과를 이것과 대조할 수 있다:

```
.agent-team/04-architecture/examples/empty-sink/          ← 오늘의 실제 상태 (7파일)
.agent-team/04-architecture/examples/commerce-connected/  ← 전 시각 상태가 한 벌에 (7파일)
```

| 산출물 | 최상위 키 (봉투 제외) |
|---|---|
| `index` | `publish_result` · `verdict` · `artifacts[]` · `views{}` · `static_views[]` |
| `ingestion_report` | `totals` · `sources` · `by_event_type` · `partitions[]` |
| `rejection_report` | `totals` · `by_reason[]` · `samples[]` |
| `field_coverage_report` | `fields{}` · `missing_fields[]` · `schema_gaps[]` |
| `kpi_report` | `index_date` · `definition_version` · `metrics[]` · `summary` |
| `data_quality_report` | `gate_result` · `spec_coverage` · `checks[]` |
| `freeze_status` | `gate` · `overall` · `lock_record` · `items[]` · `unlocked_items[]` |

### V1 `ingestion_report` — 반드시 지킬 것

- `by_event_type` — **16종 전부가 키로 존재해야 한다** (`minProperties: 16`). **0건인 타입을 목록에서 빼면 "없다"가 화면에서 사라진다**
- `partitions[]` — 일자별 **배열**. **이벤트가 0건인 날짜도 행으로 존재한다** (`present: false`). 화면이 날짜 목록을 재구성하지 않는다
- `sources` — `link_state` **2값** (`never_connected` / `connected`). ★ **`stale` 을 넣지 않는다** (결정 D-29)
- `sources[s].staleness` — **`metric_value` 로 준다.** `status: "not_run"` + `PARAM_UNCONFIRMED` + 사유. **판정할 수 없다는 사실 자체가 값이다**
- `link_state: "never_connected"` 이면 스키마가 `first_event_at`·`last_event_at` 을 `null`, `event_count` 를 `0` 으로 **강제한다**
- `totals.ingestion_gap_attribution` — `not_run` + `PRECONDITION_MISSING` (§4.5). **수집 공백이 *"주문이 없었다"* 인지 *"연결이 끊겼다"* 인지 가를 근거가 C1 에 없다.** 0 으로도, `unavailable` 로도 적지 않는다 — **`INGESTION_GAP_UNDECIDABLE` notice 를 함께 붙인다**(§4.3)

### V2 `rejection_report` — ★ 보안 판정

> **`rejected.jsonl` 에는 `validate_event()` 가 거부한 레코드가 원문 그대로 들어 있다.**
> 거부 사유 중 하나가 *"측정 계층을 통과할 수 없는 필드"* — 즉 **Hidden Trait·τ·Potential Outcome 이 담긴 레코드가 거기 남는다.**
> **그 원문을 `results/` 로 옮기면 금지 필드가 대시보드까지 도달하는 경로가 생긴다.** `ISO-003`·`NFR-002` 를 우회하는 뒷문이다.

**→ 집계와 화이트리스트 필드만 게시한다.**

```
samples[] 이 담을 수 있는 것:
  reason_key · event_type · partition_date · source · problems · offending_fields · offending_values

offending_values 의 키 = DATA-003 22컬럼만  (propertyNames: {enum: [22종]})
```

**금지 필드(`coupon_sensitivity` 등)는 스키마에 없으므로 값을 담을 자리가 구조적으로 없다.**
**필드 이름은 항상 담을 수 있다** — `FORBIDDEN_FIELD_NAMES` 는 이미 코드에 공개된 목록이고 민감한 것은 값이다.

- `by_reason[]` — 사유를 **정규화한 키**로 집계한다. `validate_event()` 의 원문 메시지를 키로 쓰면 **필드명이 섞여 카디널리티가 폭발한다**
- `samples[]` — **사유당 최대 3건 권고**

`[Source: .agent-team/04-architecture/api-contracts.md#5.2]`

### V3 `field_coverage_report`

- `fields` — **정확히 22개** (`minProperties: 22`, `maxProperties: 22`)
- 각 필드에 `applicable_event_types` 와 **`blocks_metrics`**
- **`schema_gaps[]`** — ★ **컬럼 자체가 없는 것.** `field_coverage` 는 존재하는 컬럼만 세므로, 게시하지 않으면 **화면에서 영구히 사라진다**

**C1 의 `schema_gaps` 는 4건:**

| `ref` | 계산식이 요구 | 어디에 있어야 하나 | 결정 |
|---|---|---|---|
| `unit_cost` | `cogs = Σ(unit_cost × quantity)` | `products` 테이블(미구현) · 커머스에도 없음 | `EC-1`·`EC-2` · Ecommerce `#24` |
| `discount` | `order_amount` 정의식 · `coupon_cost = Σ discount` | events 22컬럼 — **없다** | **D-16 · G-16** |
| `shipping_fee` | `contribution_profit − shipping_subsidy` | events 22컬럼 — 없다 | D-3 |
| `refund` | `revenue` = 순매출 | `event_type` 16종 — 환불 이벤트 없음 | D-2 |

**넷 모두 기여이익식이 빼는 항목이다.** 우연이 아니라 **경제 모델이 스키마보다 나중에 정해진 결과**다.

### V4 `kpi_report`

- **`kpi-definition-v1.md` 가 정의한 지표 전부가 항목으로 존재한다.** 계산되지 않는 지표를 빼면 "무엇이 계산 불가인지"가 사라진다
- 각 항목이 **정의와 값을 같은 자리에** 담는다: `name`·`layer`·`role`·`population`·`window`·`denominator_definition`·`formula`·`definition_ref`·`value`·`blocks`
- `summary` 가 47종 분류를 그대로 옮긴다. **대시보드가 세지 않는다**
- 스키마 조건: `layer` 가 `customer_kpi`·`business_kpi` → `value` 는 **`combined` 없는** 출처 분해 / `layer` 가 `experiment` → **단일 값**

### V5 `data_quality_report` — M-07 이 만들고 이 스토리가 게시한다

- `checks[].status` **5값**: `pass` / `fail` / **`vacuous`** / `not_run` / `blocked`
- `gate_result` **3값**: `pass` / `fail` / **`incomplete`**
- 각 검사에 **`scope` 필수**
- `not_run`/`blocked`/`vacuous` → `violations` 는 **`null`**

### V6 `freeze_status` — M-09 가 만들고 이 스토리가 게시한다

- PRD §22 Lock **9종 전부** (`minItems: 9`, `maxItems: 9`)
- 각 항목에 **`scope_note` 필수**
- `verification` 4값 — `match`/`mismatch`/`missing`/**`not_run`**
- `overall` 의 **C1 도달 가능 최대치는 `partial`**. `sealed` 는 `EXPERIMENT_ENVIRONMENT_v1` 선언과 함께만

### `index.json`

- **`verdict`** — 첫 화면 판정 배너. **게시물이 집계한다** (§4.8)
- `views` 맵이 **V1~V6 ↔ 게시물 ↔ 라우트**를 고정한다 → **협업 불변식이 기계가독이 된다**
- `static_views[]` — `/triggers` 처럼 게시물 없는 화면. **1:1 불변식의 명시적 예외**
- `publish_result: partial` — 일부 산출물을 게시하지 못한 상태. **대시보드는 이 상태를 숨기지 않는다**

## 4.8 ★★ B-11 — `headline_code` 에 `REJECTED_EVENTS` 를 **추가한다** (리드 판정 · 2026-09-11)

### 문제

`verdict.counts` 에 **`rejected_events` 가 있는데** `headline_code` 7종 어디에도 거부를 지목하는 값이 없다 (실측: `index.schema.json` `verdict.properties.headline_code.enum`).

```
QUALITY_VIOLATION · FREEZE_MISMATCH · CONTRACT_VIOLATION
CHECKS_NOT_RUN · SINK_EMPTY · METRICS_UNAVAILABLE · ALL_CLEAR
```

**깨지는 경우:** 품질 전건 통과 · 봉인 정상 · 지표 계산됨 · **거부 217건** → 고를 수 있는 코드가 `ALL_CLEAR` 뿐이고 **첫 화면 한 줄이 거짓말한다.**

### ★ 리드 판정 — 화면 우회를 쓰지 않는다. **계약을 고친다**

> **근거:** `check_ownership.py` 가 **`docs/contracts/measurement-publish/v1/*.schema.json` 을 Phillip 소유로 판정한다** (실행 확인).
> **즉 저장소에 들어갈 진짜 계약 파일은 이 스토리가 만든다.** `.agent-team/04-architecture/schemas/` 는 **설계 원본**이다.
> **따라서 이것은 "W2 산출물 수정"이 아니라 "W5 에서 계약을 만들 때 무엇을 담을 것인가"이고, 이 스토리의 권한 안이다.**
>
> **화면 우회는 "계약이 옳으면 필요 없는 코드"다. 그런 코드는 계약이 고쳐진 뒤에도 남아서 아무도 지우지 못한다.**

### 무엇을 담나 — 둘

**① `headline_code` enum 에 `REJECTED_EVENTS` 를 추가한다 (7종 → 8종)**

```jsonc
"headline_code": { "enum": [
  "QUALITY_VIOLATION", "FREEZE_MISMATCH", "CONTRACT_VIOLATION",
  "REJECTED_EVENTS",                                    // ← 신설
  "CHECKS_NOT_RUN", "SINK_EMPTY", "METRICS_UNAVAILABLE", "ALL_CLEAR"
]}
```

**왜 `CONTRACT_VIOLATION` 으로 덮지 않나 — 조치 주체가 다르다:**

| 코드 | 무엇 | **누가 고치나** |
|---|---|---|
| **`REJECTED_EVENTS`** | 생산자가 잘못된 이벤트를 보냈다 (`validate_event()` 거부) | **커머스 · 시뮬레이터** |
| `CONTRACT_VIOLATION` | 게시물이 스키마를 어겼다 · `contract_version` 불일치 | **우리 파이프라인** |

**James 가 `blocked_by[].kind` 를 9종으로 나눈 것과 같은 원칙이다** — *"필드가 비었다 / 컬럼이 없다 / 테이블이 없다는 해결 주체가 다르다."*
`[Source: .agent-team/04-architecture/adr/ADR-0009-blocker-chain.md]`

**② 8종의 우선순위를 계약이 정의한다**

`headline_code` 는 **단일 값인데 여러 조건이 동시에 참일 수 있다.** 순위를 화면이 정하면 **두 번째 정본이 생긴다.**

**계약에 순위를 명시한다** (스키마 `description` 또는 별도 `$comment`. **enum 순서에 의미를 두지 않는다** — JSON Schema 의 enum 은 순서를 보장하지 않는 집합이다):

| 순위 | `headline_code` | 조건 | `level` |
|---|---|---|---|
| 1 | `CONTRACT_VIOLATION` | 게시물이 자기 스키마를 어겼거나 `contract_version` 불일치 | `violation` |
| 2 | `QUALITY_VIOLATION` | `counts.quality_violations > 0` | `violation` |
| 3 | `FREEZE_MISMATCH` | 봉인 해시 불일치 | `violation` |
| 4 | **`REJECTED_EVENTS`** | **`counts.rejected_events > 0`** | `violation` |
| **5** | **`SINK_EMPTY`** | **수집 이벤트 0건** | `attention` |
| **6** | **`CHECKS_NOT_RUN`** | `counts.checks_not_run + checks_blocked > 0` | `attention` |
| 7 | `METRICS_UNAVAILABLE` | `counts.metrics_unavailable > 0` | `attention` |
| 8 | `ALL_CLEAR` | **1~7 이 전부 비어 있을 때만** | `ok` |

> **8번의 조건이 요점이다.** *"부분 정상을 정상으로 쓰지 않는다"* (규칙 F-2).
> **`rejected_events > 0` 이면 `ALL_CLEAR` 를 고를 수 없다** — 이제 화면 가드가 아니라 **계약이 그렇게 정의한다.**
>
> ### ★ 순위 교정 — `SINK_EMPTY` 가 `CHECKS_NOT_RUN` 보다 **위**다 (Thomas C-2 · 2026-09-11)
>
> **1차 초안은 `CHECKS_NOT_RUN` 을 5위에 뒀고 그것이 픽스처와 모순됐다.**
> `empty-sink` 는 `checks_not_run: 10 · checks_blocked: 1` 인데 `headline_code: "SINK_EMPTY"` 다 — 초안 규칙대로면 `CHECKS_NOT_RUN` 이 이긴다.
>
> **`CHECKS_NOT_RUN` 은 `SINK_EMPTY` 의 결과다.** 데이터가 0건이라 검사가 안 돈 것이므로 원인을 먼저 말해야 한다.
> **`empty-sink` 는 오늘의 실제 상태**라 C1 첫 화면이 **항상** 이 조합이다 — 순위가 틀리면 첫 화면이 매번 틀린다.
>
> **교정 후 두 픽스처와 전부 일치함을 실행으로 확인했다 (2026-09-11):**
> ```
> empty-sink          픽스처=SINK_EMPTY         신규규칙=SINK_EMPTY         ✅
> commerce-connected  픽스처=QUALITY_VIOLATION  신규규칙=QUALITY_VIOLATION  ✅
> ```
> **★ 순위를 바꾸면 반드시 두 픽스처로 다시 대조한다.** enum 소속 검사만으로는 규칙 일치를 알 수 없다.

> ⚠ **위 순위는 이 스토리가 제안하는 값이다.** 리드가 *"8종 우선순위를 계약이 정의한다"* 를 지시했고 **구체 순서는 지정하지 않았다.**
> 순서를 바꿀 근거가 있으면 바꾸되 **① 계약에 적고 ② 화면이 정하지 않게 하고 ③ PR 에 근거를 적는다.**
> `ux-flow-map.md` §1.1 의 7단계 순위(`N-5` — *"실데이터 없이 정한 순서다"*)를 참고했으나 그것은 화면 쪽 초안이고 **계약이 정본이 된다.**

### 4.8.1 ★★ 순위를 **기계가 검사한다** — 그리고 5위만 `counts` 로 검산되지 않는다 (Thomas NR-3)

**구멍 ①  스키마 `description`·`$comment` 는 문장이지 강제가 아니다.**
`publish.py` 가 **다른 순서를 구현해도 전 테스트가 통과한다.** 위 표는 사람이 읽는 글일 뿐이다.

**구멍 ②  5위 `SINK_EMPTY` 의 입력이 `verdict.counts` 에 없다.** 실측:

```
index.schema.json  verdict.properties.counts
  required = 8키 · additionalProperties: false
  quality_violations · checks_not_run · checks_blocked · metrics_unavailable
  metrics_not_run · schema_gaps · lock_items_pending · rejected_events
  → 수집 건수가 없다.
```

순위 2·4·6·7 은 `counts` 한 객체로 검산된다. **5위만 다른 산출물을 봐야 한다.**

> #### 판정 — 5번째 계약 변경을 만들지 않는다. **입력 출처를 명시하고 순위를 테스트가 재계산한다**
> `counts.ingested_events` 를 새로 넣으면 **같은 수를 두 산출물이 말하게 되고**(§4.15 ②와 같은 이중 저작),
> 리드가 승인한 계약 변경은 **4건**이다. 다섯째를 스스로 추론하지 않는다.

**⑴ `SINK_EMPTY` 의 입력 출처 — 계약에 적는다**

| 항목 | 값 |
|---|---|
| 읽는 곳 | **`ingestion_report.totals.events_ingested`** (`source_split`) |
| 조건 | `by_source.commerce` 와 `by_source.simulator` 가 **둘 다 `status: "ok"` 이고 `value == 0`** |
| `combined` 가 있으면 | `combined` 가 `ok` 일 때 그 값을 쓴다 — 계층 0 에서만 허용된다(`common.schema.json` `$comment` 실측) |

> ★ **`events_ingested` 는 `metric_value` 다. 즉 계산 불가일 수 있다.**
> `status` 가 `ok` 가 아니면 **`SINK_EMPTY` 를 고를 수 없다** — *"0건이었다"* 를 확인하지 못했기 때문이다.
> 그때는 **6위로 내려가고**, `notices` 에 *"수집 건수를 확인할 수 없어 `SINK_EMPTY` 판정을 보류했다"* 를 남긴다.
> **모르는 것을 0 으로 읽지 않는다.** 이것이 이 사이클 전체의 `?? 0` 함정과 같은 자리다.

**⑵ 순위를 기계가 검사하는 AC — `AC-4c` 로 추가한다**

```python
# tests/test_publish_contract.py
def test_headline_code_is_recomputed_from_fixtures():
    """픽스처의 verdict/ingestion_report 로 headline_code 를 다시 계산해
    픽스처가 적어 둔 값과 일치하는지 본다. enum 소속 검사로는 순위를 못 잡는다."""
    for name, expected in [("empty-sink", "SINK_EMPTY"),
                           ("commerce-connected", "QUALITY_VIOLATION")]:
        idx = load(name, "index.json")
        ing = load(name, "ingestion_report.json")
        assert choose_headline_code(idx["verdict"]["counts"], ing) == expected, name
```

| 규칙 | 내용 |
|---|---|
| **`choose_headline_code()` 가 유일한 구현 자리** | 화면도 테스트도 이 함수를 부른다. 순위를 두 번 적지 않는다 |
| **순서를 바꾸면 이 테스트가 먼저 깨진다** | 그것이 목적이다 |
| **픽스처 2벌은 표본이지 증명이 아니다** | 표본 밖 사례(§4.8 Thomas 검증표)는 **함수 단위 테스트**로 따로 넣는다 — `counts` 를 직접 지어내 8종을 전부 통과시킨다 |

### 이 변경이 건드리는 것

| 파일 | 동작 |
|---|---|
| `docs/contracts/measurement-publish/v1/index.schema.json` | **enum 8종 + 순위 명시** ← **Phillip 소유. 이 스토리가 만든다** |
| `.agent-team/04-architecture/schemas/index.schema.json` | **고치지 않는다** — W2 설계 원본. **차이를 T6 대조 테스트가 드러낸다** (§5 T6) |
| `.agent-team/04-architecture/examples/*/index.json` | **고치지 않는다** — 픽스처. 둘 다 `headline_code` 가 8종 안에 있으므로 **여전히 통과한다** (실측: `SINK_EMPTY` · `QUALITY_VIOLATION`) |

> ### ★★ 두 벌을 맞추지 않는다 — T6 재정의 (리드 판정 2026-09-11)
>
> | 대상 | 지위 |
> |---|---|
> | `.agent-team/04-architecture/schemas/` | **W2 설계 스냅샷. 동결. 갱신하지 않는다** |
> | `docs/contracts/measurement-publish/v1/` | ★ **W5 부터 살아있는 정본** |
>
> **James 는 shutdown 됐고 W2 는 닫혔다.** `.agent-team/` 의 스키마는 **그때 그렇게 설계했다는 기록**이지 유지보수 대상이 아니다.
>
> **→ T6 은 "지속 동기화"가 아니라 "일회성 변경 이력 대조"다.**
> 스냅샷 대비 **의도된 차이를 changelog 로 고정**하고, **W5 이후에는 `docs/contracts/` 만 본다.**
> **두 벌을 맞추는 비용이 사라지고, 차이가 늘어도 changelog 한 줄이다.**

### `docs/contracts/measurement-publish/v1/CHANGELOG.md` — 이 스토리가 만든다

**서두에 적을 것 — 임기응변 4건이 아니라 두 원칙의 적용이다:**

> #### 원칙 ① · 필수/금지 쌍 — **상태가 값을 결정하면 그 값을 담을 필드의 유무도 결정한다**
> | 변경 | 필수일 때 | 금지일 때 |
> |---|---|---|
> | `basis` (기존 · `ADR-0008`) | `ok`·`unconfirmed` | `unavailable`·`blocked`·`not_run` |
> | **`value_formatted`** (C-1) | `ok`·`unconfirmed` | 계산 불가 3종 |
> | **`status` ↔ `reason_code`** (Q-2) | `blocked`→`BLOCKED` · `not_run`→`NOT_RUN`\|`PRECONDITION_MISSING` | **`vacuous` → `reason_code` 금지** |
>
> **★ `value_formatted` 를 `basis` 와 같은 패턴으로 넣는 것이 요점이다.**
> **계산 불가일 때는 `?? 0` 을 붙일 필드 자체가 존재하지 않는다.** 규율이 아니라 구조로 막는다.
>
> #### 원칙 ② · 담을 자리를 만든다 — **계약이 표현하지 못하면 화면이 추론하거나 지어낸다**
> | 변경 | 없으면 |
> |---|---|
> | **`REJECTED_EVENTS`** (B-11) | 거부 217건이 `ALL_CLEAR` 로 뜬다 |
> | **`limit_note`** (N-8) | `한계` 칩을 담을 자리가 없어 정밀도 한계가 사라진다 |
>
> ⚠ **리드는 넷을 "한 원칙의 4회 적용"으로 보았으나 정확히는 둘이다.**
> `REJECTED_EVENTS`·`limit_note` 는 **필수/금지 쌍이 아니다** — 전자는 enum 추가, 후자는 **선택 필드**다.
> **묶어서 적으면 다음 사람이 `limit_note` 를 조건부 필수로 오해한다.** 두 원칙으로 나눠 적는다.

**changelog 항목 형식:**

```markdown
## v1 — W5 변경 4건 (스냅샷: .agent-team/04-architecture/schemas/ · W2 2026-09-11)

| # | 파일 | 변경 | 원칙 | 근거 |
|---|---|---|---|---|
| 1 | index.schema.json | headline_code enum 7 → 8 (REJECTED_EVENTS) + 우선순위 명시 | ② | B-11 · 리드 판정 |
| 2 | data_quality_report.schema.json | checks.items allOf — blocked·not_run **추가 2건** + **vacuous 는 allOf[2] 교체** (required 에서 reason_code 제거 + not 추가) | ① | Q-2 · Matthias 항목2 |
| 3 | common.schema.json | value_formatted 추가 — allOf[0]·[1] required **추가** + **allOf[2].then.not 교체** ★ **기존 basis 금지를 건드리는 변경** (회귀 검사 대상 · AC-4e) | ① | C-1 · Thomas · 리드 실측 |
| 4 | common.schema.json | limit_note 추가 (선택) | ② | N-8 · Thomas |
```

| 규칙 | 내용 |
|---|---|
| **`.agent-team/` 를 고치지 않는다** | 스냅샷이다 |
| **W5 이후 정본은 `docs/contracts/` 하나** | 두 벌 동기화 없음 |
| **changelog 에 없는 차이가 생기면 실패** | T6 테스트가 그것만 본다 |
| **원칙 열을 비우지 않는다** | 원칙 없는 변경은 임기응변이고, 임기응변이 넷 넘어가면 계약이 무너진다 |
| ★ **`vacuous` 는 추가가 아니라 교체다** | 추가하면 `vacuous` 행이 **만족 불가능**해진다 (m-07 §7.2 W3 재현). changelog 에 *교체*라고 적는다 |
| ★ **`not` 절을 건드리는 변경은 회귀로 취급한다** | 네 수정 중 **2건이 기존 `not` 절을 교체**한다(`metric_value.allOf[2]` · `checks.items.allOf[2]`). **수정 전 거부되던 레코드가 수정 후에도 거부되는지 먼저 본다** (AC-4e) |

## 4.10 게시 절차 — 원자성

```text
1. .staging/<run_id>/ 에 6종을 쓴다
2. 각 산출물을 자기 스키마로 검증한다        ← 실패하면 여기서 멈춘다 (fail closed)
3. os.replace() 로 최종 경로에 하나씩 옮긴다  (같은 파일시스템 → 원자적)
4. ★ index.json 을 마지막에 쓴다
5. .staging/<run_id>/ 를 지운다
```

**읽는 쪽의 의무:** `index.json` 을 먼저 읽고, 각 산출물의 `run_id` 가 인덱스와 **같은지 확인한다.** 다르면 값을 섞어 표시하지 않는다.

> **부분 게시 상태를 읽지 않게 하는 가장 싼 방법이다.** 잠금도, 트랜잭션도, 버전 디렉터리도 필요 없다.
> `[Source: .agent-team/04-architecture/design-patterns.md#P-6]`

**실패 시 (fail closed):** *"부분적으로 잘못된 파일을 내보내는 것보다 안 내보내는 편이 낫다 — **잘못된 값은 화면에서 정상으로 보이지만, 없는 파일은 없다고 보인다.**"*

**종료 코드** `[Source: .agent-team/04-architecture/exceptions.md#5]`:

| 코드 | 뜻 |
|---|---|
| 0 | 정상. **`publish_result: partial` 도 0 이다** — 부분 게시는 정상적으로 완료된 부분 실패다 |
| 2 | 데이터 품질 게이트 실패 (`QualityGateFailure`) |
| 3 | 봉인 해시 불일치 (`FreezeViolation`) — **검증 명령에서만.** 게시 경로에서는 잡는다 |
| 4 | 게시 실패 (`PublishError`) |
| 5 | 설정 오류 (`ConfigError`) |

## 4.11 ★ 게시 시점 자기검증을 무엇으로 하나 — 결정 D-21 에 달렸다

`jsonschema` 는 **dev 전용**을 권고했다 (D-21 ⑴).

| 층 | 수단 |
|---|---|
| **게시 시점** (`contracts.py`) | **표준 라이브러리로 핵심 불변식 몇 개만** 확인 — §4.4 의 12개 중 값-null·basis 유무·denominator 0·combined 금지·KST·**`value_formatted` 유무(양방향)** |
| **테스트** (`test_publish_contract.py`) | **`jsonschema` 로 전체 스키마 검증.** 없으면 skip + 사유 |

**이유:** 런타임 의존을 하나 줄인다. `[Source: .agent-team/04-architecture/dependency-plan.md#8 D-21]`

> **⚠ 자기검증을 "몇 개만" 한다는 것은 나머지가 검사되지 않는다는 뜻이다.**
> ### ★ `value_formatted` 는 **반드시 이 목록에 있어야 한다** (Thomas NR-3·C-1)
>
> `jsonschema` 는 dev 전용이다. 즉 **운영 게시 경로에서는 전체 스키마 검증이 돌지 않는다.**
> `value_formatted` 를 이 목록에서 빼면 — 계약에 `required` 를 적어 놓고 **아무도 검사하지 않는 상태**가 된다.
> 게시는 성공하고 화면은 `undefined` 를 받는다. **C-1 의 원래 증상이 그대로 살아남는다.**
>
> | 방향 | 검사 |
> |---|---|
> | `status ∈ {ok, unconfirmed}` | `value_formatted` 가 **있고 빈 문자열이 아니다** |
> | `status ∈ {unavailable, blocked, not_run}` | `value_formatted` 가 **없다** · `basis` 도 없다 |
>
> **두 방향을 다 본다.** 한쪽만 보면 §4.16 NR-1 의 `not` 함정과 같은 결과가 된다.

> **그 사실을 `contracts.py` 독트링과 PR 에 적는다.** *"게시 시점 검증은 핵심 불변식 N개이고, 전체 스키마 검증은 `tests/test_publish_contract.py` 가 한다."*

## 4.12 함정

| # | 함정 | 왜 빠지나 | 대신 |
|---|---|---|---|
| **T-1** | 0건 `event_type` 을 `by_event_type` 에서 뺀다 | dict 가 깔끔해진다 | **`minProperties: 16`.** 빼면 "없다"가 화면에서 사라진다 |
| **T-2** | `sources` 에서 0건 출처 키를 뺀다 | 위와 같음 | **두 키 항상 존재.** 빼면 그 출처가 화면에서 사라진다 |
| **T-3** | `partitions[]` 에서 `present: false` 행을 뺀다 | 데이터가 없으니까 | **수집 공백이 화면에서 사라진다** |
| **T-4** | `generated_at` 에 `datetime.now(timezone.utc).isoformat()` | `sink.py` 가 그렇게 한다 | ★ **`Z` 표기는 스키마에서 실패한다.** KST 로 |
| **T-5** | `simulator_commit: ""` 또는 `"unknown"` | `null` 이 어색해 보인다 | **`null` + `null_reason`.** 빈 문자열은 대조를 조용히 성공시킨다 |
| **T-6** | `rejected.jsonl` 을 `results/` 로 복사 | 화면이 상세를 보려면 필요해 보인다 | ★ **금지 필드가 대시보드까지 간다** (§4.7 V2) |
| **T-7** | `by_reason` 키에 `validate_event()` 원문 메시지 | 그대로 쓰면 편하다 | **필드명이 섞여 카디널리티가 폭발한다.** 정규화한다 |
| **T-8** | `index.json` 을 먼저 쓴다 | 순서를 안 지킨다 | **마지막에.** 부분 게시를 읽는 경로가 열린다 |
| **T-9** | 검증 실패한 산출물도 일단 게시 | 화면이 비니까 | **fail closed.** *"잘못된 값은 정상으로 보이지만 없는 파일은 없다고 보인다"* |
| **T-10** | `publish.py` 에 계산식을 넣는다 | 조립하다 보면 자연스럽다 | **계산은 `kpi.py`·`economics.py`.** `publish.py` 는 조립만 (`code-structure.md` §4) |
| **T-11** | `verdict` 를 화면이 세게 둔다 | 게시가 단순해진다 | **단순 합산도 계산이다** (`DB-012`). 게시물이 집계한다 |
| **T-12** | `publish_result: partial` 에 종료 코드 1 | 실패니까 | **0 이다.** 비0 이면 CI·스크립트가 롤백해 **왜 실패했는지가 사라진다** |
| **T-13** | 계층 1·2 에 `combined` 를 넣는다 | 히어로 지표가 필요해 보인다 | **스키마가 거부한다** (R-7) |

---

## 4.13 ★ 파생 상태 — **게시 시점에 계산해 게시한다** (리드 판정 G-8 · 2026-09-11)

**W1 D-7 은 *"`DerivedStateType` 이 `EventType` 밖이라 Sink 에 기록할 수단이 없다"* 였다. 리드가 선택지 4개 중 ④를 확정했다.**

| 선택지 | 판정 |
|---|---|
| ① `EventType` 16 → 19 | **불가** — `test_schema.py` 가 `assertEqual` 로 고정한 16종을 바꾸는 것 = **`EVENT SCHEMA v1` 실질 변경.** 우리는 지금 그걸 Lock 하려는 중이다 |
| ② 별도 테이블 | **C1 범위 밖** — 6테이블 미구현 |
| ③ 기록 안 하고 한계로 Lock | **정보가 사라진다** |
| **④ 게시 시점 계산** | ★ **채택** |

**근거:** `at_risk`·`churn` 은 `days_since_last_purchase` 에서 **유도되는 값**이고 그 원천(`timestamp`·`purchase`)은 **이미 스키마에 있다.**
**계산해서 게시하면 스키마를 바꾸지 않고도 정보가 살아난다.**

> **D-16(`discount` 유도 규칙)과 같은 형태다** — *"규칙으로 덮을 수 있는 것을 가정으로 덮으면 **할 수 있는데 안 한 것**이다."*

### 어디에 담나 — **스키마를 바꾸지 않고 담을 수 있다** (실측)

```
kpi_report            top-level additionalProperties: false   ← 새 최상위 블록 불가
kpi_report.metrics[]  additionalProperties: false
                      required: name · layer · role · population · window
                                · denominator_definition · value
                      layer enum: collection_health | customer_kpi | business_kpi | experiment
```

**→ `metrics[]` 에 `layer: "customer_kpi"` 항목으로 담는다. 스키마 변경 0건이다.**

### 조건 셋 — 전부 필수

| # | 조건 | 왜 |
|---|---|---|
| **①** | **`derived: true` + `derivation`**(계산식)을 반드시 붙인다 | **저장된 사실과 구분되어야 한다.** 계약이 `derived: true → derivation` 을 강제한다 |
| **②** | **`DB-012` 위반이 아니다** — **계산하는 쪽은 `measurement` 이고 대시보드가 아니다** | 이 구분을 코드 주석에 적는다. *"대시보드는 계산하지 않는다"* 와 충돌하지 않는다 |
| **③** | ★ **Feature 로 쓰이지 않는다** | `FEATURE_FORBIDDEN_EVENT_TYPES` · `tests/test_schema.py:188-196 test_no_observable_depends_on_derived_state` 가 **그대로 통과해야 한다.** 이 게시물은 **대시보드 표시와 코호트 분석 전용**이다 (PRD §30.2) |

**③이 가장 위험한 자리다.** 파생 상태를 게시물에 넣는 순간 *"이제 Feature 로 써도 되는 것 아닌가"* 로 읽힐 수 있다.
**읽히지 않게 `kpi_report` 항목의 `population`·`derivation` 에 *"Feature 사용 금지 — 라벨과 동어반복"* 을 적는다.**

**지표 정의는 M-04 가 `kpi-definition-v1` 에 추가한다.** 이 스토리는 **게시 형식만** 책임진다.

## 4.14 ★★ 픽스처가 **의도적으로 실패한다** — 그 실패가 증거다 (Thomas C-3)

**문제:** AC 가 *"픽스처 2벌이 여전히 통과한다"* 를 요구하는데, **이 사이클이 넣는 계약 제약들이 픽스처를 실패시킨다.**

```
empty-sink/data_quality_report.json   DQ-06  status:"not_run" + reason_code:"BLOCKED"
                                             → Q-2 제약(not_run → NOT_RUN|PRECONDITION_MISSING) 위반
commerce-connected/…                  reported_checks 6  vs  len(checks) 7
                                             → Q-3 자기검증 위반
전 픽스처 14파일                       value_formatted 0건
                                             → C-1 제약 위반
```

**픽스처는 W2 산출물이라 고칠 수 없다.** 그대로 두면 W5 는 셋 중 하나를 한다 — **제약을 뺀다 / 픽스처를 몰래 고친다 / 테스트에서 예외 처리한다. 전부 나쁘다.**

> ### 판정 — 리드가 T6 에 도입한 **"의도된 차이"** 패턴을 픽스처에도 적용한다
> **의도된 실패를 목록으로 명시하면, 그 실패는 결함이 아니라 제약이 작동한다는 증거가 된다.**

```python
# tests/test_publish_contract.py
INTENDED_FIXTURE_FAILURES = {
    ("empty-sink", "data_quality_report", "DQ-06"):
        "Q-2 — status:not_run + reason_code:BLOCKED. 계약이 '안 했다'와 '못 했다'를 "
        "가르기 전에 만들어진 픽스처다. 이 실패가 Q-2 제약이 작동한다는 증거다.",
    ("commerce-connected", "data_quality_report", "spec_coverage.reported_checks"):
        "Q-3 — reported_checks 6 vs len(checks) 7.",
    # value_formatted 는 방향을 가른다 (Thomas NR-2). 부재만 의도된 실패다.
    ("*", "*", "value_formatted:missing"):
        "C-1 — ok/unconfirmed 인데 value_formatted 가 없다. 계약에 이 필드를 넣기 전에 "
        "만들어진 픽스처다. 의도된 실패.  판별: ValidationError.validator == 'required'",
    # ("*", "*", "value_formatted:forbidden") 은 일부러 등록하지 않는다.
    #   계산 불가(unavailable/blocked/not_run)인데 value_formatted 가 있으면
    #   그것은 낡은 픽스처가 아니라 0-채움 회귀다. 목록에 없으므로 즉시 실패한다.
    #   판별: ValidationError.validator == 'not'
    # F-E — allOf[2] 교체가 만드는 의도된 실패 (Matthias N-11 · W3 실측)
    ("empty-sink", "data_quality_report", "vacuous:reason_code"):
        "F-E / Matthias 항목2 — vacuous 7건(DQ-01·02b·04·07·08·10·11)이 전부 "
        "reason_code:'NOT_RUN' 을 갖고 있다. '실행했는데 0행'과 '실행 안 함'이 한 행에 "
        "섞인 것이고, allOf[2] 교체가 이것을 거부한다. 이 실패가 교체가 작동한다는 증거다. "
        "★ 수정이 의도대로 작동한 결과이지 결함이 아니다. 픽스처를 고치지 않는다. "
        "판별: ValidationError.validator == 'not'",
    ("commerce-connected", "data_quality_report", "checks[] 18종 불변식"):
        "Q-4 — checks 가 7종뿐이다(11종 누락: DQ-02·03·04·05·06·11·12·13·14·15·16). "
        "make_examples_connected.py 453·456행이 7종과 reported_checks:6 을 하드코딩했다. "
        "이 실패가 18종 불변식이 작동한다는 증거다.",
}
```

| 규칙 | 내용 |
|---|---|
| **목록에 있는 실패** | **기대된 것.** 테스트가 *"실패해야 실패한다"* 를 단언한다 — 통과해 버리면 제약이 안 걸린 것이므로 **그때 실패시킨다** |
| **목록에 없는 실패** | **회귀.** 즉시 실패 |
| ★ **방향이 다르면 다른 항목이다** | 같은 필드라도 **없어서 나는 실패**와 **있으면 안 되는데 있어서 나는 실패**는 반대다. `ValidationError.validator` 로 가른다 — `required`(부재) vs `not`(존재 금지). **`value_formatted` 의 존재-금지 위반은 목록에 없다. 그것이 이 사이클이 막으려는 `?? 0` 그 자체다** |
| ★ **개수를 문장으로 적지 않는다** | 항목이 늘 때마다 숫자가 어긋난다(실제로 3→4→5 두 번 어긋났다). **테스트는 dict 를 순회한다** |
| **픽스처를 고치지 않는다** | W2 산출물 |
| **제약을 빼지 않는다** | 픽스처를 정답으로 삼으면 계약이 픽스처에 맞춰 내려간다 |

> **★ "실패해야 실패한다"가 요점이다.** 의도된 실패를 그냥 건너뛰면(skip) **제약이 없어져도 아무도 모른다.**

## 4.15 ★★ 픽스처 결함은 **여기서 고치지 않는다** — 4개 규칙 (리드 판정 CR-2)

`tools/make_examples_connected.py` 는 **`checks` 7종과 `reported_checks: 6` 을 소스에 하드코딩**했다(453·456행 실측).
**재생성해도 같은 7종이 나온다. 버그가 도구 안에 있다.**
빠진 11종을 채우려면 `DQ-03`·`DQ-13`·`DQ-14` 각각의 `status`·`reason_code`·`examined_rows` 를 **판단**해야 하는데, **그 판단은 이 스토리가 실제 데이터로 할 판단과 같다. 두 번 저작하면 반드시 어긋난다.**

| # | 규칙 |
|---|---|
| **①** | **항상 18종을 낸다.** 실행 못 한 것은 `not_run`/`vacuous`/`blocked` 로 **목록에 남긴다. 빼지 않는다** (`AC-3`) |
| **②** | **`reported_checks` 를 상수로 적지 않는다.** `len(checks)` 로 산출한다 (`Q-3`) |
| **③** | **픽스처를 새로 만들 일이 생기면 이 모듈의 출력에서 만든다. 손으로 저작하지 않는다** |
| **④** | `make_examples_connected.py` 의 하드코딩 7종·`reported_checks: 6` 은 **W2 스냅샷의 알려진 결함**이다. **고치지 않고 결함으로 표기**한다 — m-06 §4.14 의도된 실패 목록 |

> **③이 요점이다.** 픽스처가 정본 노릇을 하는 자리가 여럿이라, **진짜 판정을 하는 코드에서 나온 것만 픽스처가 될 수 있다.**

## 4.16 ★★ `value_formatted` — 계약에 **없다.** 이 스토리가 만든다 (Thomas C-1)

### 문제 — 이 결함이 `?? 0` 을 직접 부른다

`07-design/dashboard-agents-design-constraints.md:44` 가 화면 올바른 형태로 제시한 코드:

```ts
const display = m.status === 'ok' ? m.value_formatted : EM_DASH;
```

**그런데 `value_formatted` 가 계약에 없다** (실측):

```
common.schema.json  $defs.metric_value.properties
  = status · value · unit · basis · reason_code · reason_detail
    · blocked_by · derived · derivation · params_used · ci95     ← 11종
  additionalProperties: false        ← 추가할 수 없다
픽스처 14파일 grep 'value_formatted'  →  0건
```

**→ 지금 상태로 구현하면 모든 `ok` 지표가 `undefined` 다.**
**→ 구현자는 `m.value.toLocaleString()` 로 가고 → `null` 예외를 막으려 `?? 0` 을 쓴다.**
**→ §4.5 와 d-02 §4.1 이 경고한 바로 그 경로를, 경고문 자신이 연다.**

### 판정 — 계약에 추가한다. B-11·Q-2 와 같은 경로다

`docs/contracts/**` 는 **Phillip 소유**이므로 이 스토리의 권한 안이다.

```jsonc
"value_formatted": {
  "type": "string", "minLength": 1,
  "description": "화면이 그대로 출력하는 표시 문자열. 예 '38,400원' · '18.3%' · '1,204건'.
                  통화·소수 자릿수·천단위 구분은 도메인 규칙이므로 게시 시점에 끝낸다(DB-012).
                  화면은 숫자를 포맷하지 않는다."
}
```

**`basis` 와 같은 자리, 같은 패턴으로 강제한다:**

| `status` | `value_formatted` |
|---|---|
| `ok` · `unconfirmed` | **필수** (`required`) |
| `unavailable` · `blocked` · `not_run` | **금지** — ★ 형태 주의, 아래 |

### ★★ NR-1 — `not` 을 배열로 확장하면 **0 채우기가 통과한다** (실행 재현)

현행 `allOf[2].then` 에 **이미 `not` 이 있다** (실측):

```jsonc
"not": { "required": ["basis"] }
```

**JSON Schema 객체에 `not` 은 하나뿐이다.** 그래서 가장 자연스러운 구현은 배열에 이름을 더하는 것인데 — **틀린다.**

```jsonc
// 틀렸다 — required:[a,b] 는 "둘 다 있다" 이고 그 부정은 "둘 다 있지는 않다"
"not": { "required": ["basis", "value_formatted"] }
```

### ★★★ 이 편집은 **새 제약을 못 넣는 정도가 아니다. 있던 제약을 지운다** (리드 실측 2026-09-11)

**계산 불가(`unavailable`) 분기에 네 레코드를 넣어 세 형태를 전수 대조했다** (W3 재현 · `jsonschema 4.26.0` + 순수 파이썬, **두 방법이 같은 결과**):

| 레코드 | **현행** `not:{required:["basis"]}` | **틀린 형태** `not:{required:["basis","value_formatted"]}` | **올바른 형태** `not:{anyOf:[…]}` |
|---|---|---|---|
| 정상 — `basis`·`value_formatted` 둘 다 없음 | 통과 | 통과 | 통과 |
| ★ 위반 — `value_formatted` 있음 | 통과 *(아직 제약이 없다)* | **통과** | **거부** ✅ |
| ★★ 위반 — **`basis` 있음** | **거부** ✅ | **★ 통과** ← **지금 막고 있는 것이 뚫린다** | **거부** ✅ |
| 위반 — 둘 다 있음 | 거부 | 거부 | 거부 |

> #### ★★ 세 번째 행이 핵심이다 — **회귀다**
>
> `not: {required: ["basis"]}` 는 **`basis` 하나만 있어도 거부**한다. 여기에 이름을 하나 더 넣으면 *"둘 다 있지는 않다"* 가 되어 **`basis` 만 있는 레코드가 통과한다.**
>
> **즉 이 한 줄 편집은 두 개를 한 번에 무력화한다** — **새로 넣는 `value_formatted` 금지가 안 걸리고, W2 가 세운 `basis` 금지가 지워진다.**
> **표 2행과 3행이 동시에 `통과` 다.** 계약을 고쳤는데 **고치기 전보다 나빠진다.**
> `basis` 의 유무가 *"측정됨"* 의 판별자라는 것이 **`ADR-0003`·`ADR-0010` 의 토대**다. **계산 불가에 `basis` 가 붙으면 근거 없는 값이 근거 있는 값으로 읽힌다** — USP-1 이 무너지는 정확한 지점이다.
>
> **그리고 이 회귀는 조용하다.** 픽스처 14파일에는 *"계산 불가인데 `basis` 가 있는"* 레코드가 없으므로 **기존 테스트가 전부 통과한다.** 아무도 모른다.

**W3 재현 (2026-09-11):**
```
인스턴스  {"status":"unavailable", "value":null, "value_formatted":"0원"}   ← basis 없음
required["basis","value_formatted"] 만족?  False
  → not 이므로 ★ 통과            USP-1 실패 양식이 스키마를 빠져나간다

인스턴스  {"status":"unavailable", "value":null, "basis":{...}}             ← formatted 없음
required["basis","value_formatted"] 만족?  False
  → not 이므로 ★ 통과            ★ 현행 스키마는 이것을 거부하고 있었다. 회귀다
```

```jsonc
// 올바르다 — "둘 중 하나라도 있으면 안 된다"
"not": { "anyOf": [ { "required": ["basis"] }, { "required": ["value_formatted"] } ] }
```
```
같은 인스턴스   anyOf 만족? True  →  not 이므로 ★ 거부 ✅
```

> **이 함정은 구현자가 반드시 밟는다.** 기존 `not` 옆에 이름 하나를 더하는 것이 가장 짧은 수정이기 때문이다.
> **`limit_note` 를 나중에 같은 자리에 넣을 때도 같다** — `anyOf` 배열에 항목을 더한다.

**요약 — `metric_value.allOf` 에서 고치는 자리는 셋이다** (`common.schema.json` 실측 6항목 중):

| 자리 | 편집 |
|---|---|
| `allOf[0].then.required` (`ok`) | `["value","unit","basis"]` → **`+ "value_formatted"`** |
| `allOf[1].then.required` (`unconfirmed`) | `[…,"params_used"]` → **`+ "value_formatted"`** |
| `allOf[2].then.not` (계산 불가 3종) | `{"required":["basis"]}` → **`{"anyOf":[{"required":["basis"]},{"required":["value_formatted"]}]}`** |

> **`allOf[1]` 을 빠뜨리기 쉽다.** `unconfirmed` 는 픽스처에 **1건뿐**이라 테스트가 조용히 통과한다.
> **`limit_note` 는 어느 자리에도 넣지 않는다** — 선택 필드다 (§4.17). 조건부 필수로 만들면 `한계` 없는 지표가 전부 실패한다.

> **왜 `basis` 와 짝지어 강제하나:** `basis` 의 유무가 *"측정됨"* 의 판별자라면, `value_formatted` 의 유무는 *"화면에 쓸 것이 있음"* 의 판별자다.
> **둘이 같이 있거나 같이 없어야 화면이 분기 하나로 끝난다.**

**기존 픽스처 14파일에는 이 필드가 없다** → **의도된 실패**로 §4.14 에 등록한다.

### 4.16.1 ★★ 포맷 주체 — **`contracts.py` 직렬화 시점** (리드 판정 2026-09-11)

| 안 | 판정 |
|---|---|
| ⇥₁ `MetricValue.ok()` **호출자**가 포맷해 넘긴다 | ❌ **호출 지점마다 다를 수 있고, 한 곳만 빠뜨리면 `undefined` 가 나오고, 구현자는 `?? 0` 을 쓴다** |
| **⇥₂ `contracts.py` 가 `unit`+`value` 로 직렬화 시점에** | ★ **채택. 한 곳에서 하면 빠뜨릴 자리가 없다.** 계산층이 표시 규칙을 모르고 규칙이 한 곳에 모인다 |

> **금지가 아니라 구조로 막는다** — 이 웨이브가 계속 적용한 원칙과 같다.
> `MetricValue` dataclass 에 `value_formatted` **필드를 두지 않는다.** 직렬화 함수가 만든다. **`kpi.py`·`economics.py` 는 이 필드의 존재를 모른다.**

**`unit` 별 포맷 규칙 — 이것이 정본이다:**

| `unit` | 형식 | 예 |
|---|---|---|
| `krw` | 천단위 `,` + `원`. **소수 없음** | `38,400원` |
| `krw_per_customer` | 동일 + `/인` | `2,130원/인` |
| `count` | 천단위 `,` + `건` | `1,204건` |
| `ratio` | **×100 · 소수 1자리** + `%` | `18.3%` |
| `percentage_point` | 소수 1자리 + `%p` · **부호 유지** | `+3.2%p` |
| `days` | 정수 + `일` | `42일` |
| `text` | 그대로 | — |
| `datetime` | **KST `YYYY-MM-DD HH:MM`** | `2026-09-18 13:58` |

| 규칙 | 내용 |
|---|---|
| **반올림은 표시에서만** | `value` 는 원값을 유지한다 |
| **`ratio` 의 ×100 을 화면이 다시 하지 않는다** | 화면은 문자열을 그대로 쓴다 |
| **로케일 함수에 의존하지 않는다** | `toLocaleString()` 은 환경마다 다르다. **명시적 포맷** — 재현성 |
| **`unit` 이 없으면 `value_formatted` 도 없다** | 계산 불가 상태이므로 정상 |

## 4.17 ★ `한계` 칩을 담을 자리도 계약에 없다 (Thomas N-8)

`kpi-definition-v1.md` §4.2 가 `campaign_response_count` 의 **정밀도 한계**(쿠폰 비종속 캠페인 미측정)를 규정하고, 화면 규칙 **V-7** 이 `한계` 칩을 요구한다.
**그런데 담을 필드가 없다** (실측):

```
metric_value props   status·value·unit·basis·reason_code·reason_detail
                     ·blocked_by·derived·derivation·params_used·ci95     ← limit 계열 0
kpi metrics[] props  name·layer·role·population·window·denominator_definition
                     ·formula·definition_ref·source_events·value·blocks   ← 동일
```

**`notices[]` 는 산출물 단위라 개별 지표에 붙지 않는다.**

> **→ `value_formatted` 와 같은 경로로 `metric_value` 에 `limit_note` 를 추가한다.**
> ```jsonc
> "limit_note": { "type": "string", "minLength": 1,
>   "description": "값은 나오나 정밀도 한계가 있는 지표의 한 줄 설명. status 는 ok 다.
>                   provisional(파라미터 미확정)과 다르다 — 한계는 이벤트가 추가되지 않으면 영원히 남는다." }
> ```
> **선택 필드다.** 있으면 화면이 `한계` 칩을 붙이고 없으면 붙이지 않는다.
> **`derived` 와 마찬가지로 `status` 를 바꾸지 않는다** — 값은 정상이고 정밀도만 한정된다.

# 5. 작업 분해 (Tasks)

## T1 · 계약 스키마 이관

- [ ] `.agent-team/04-architecture/schemas/*.schema.json` **7종을 `docs/contracts/measurement-publish/v1/` 로 복사**
- [ ] 복사본에 **출처 표기** — ★ **JSON 에는 주석을 쓸 수 없다.** 최상위 **`$comment`** 키에 `.agent-team/` 원본 경로 + W2 산출물임을 적는다 (Thomas N-7)
- [ ] `.agent-team/` 원본은 **읽기만.** 어긋나면 코드를 고친다
- [ ] ★ **B-11 수정** — `index.schema.json` 의 `headline_code` 에 `REJECTED_EVENTS` 추가 + 8종 우선순위 명시 (§4.8)
- [ ] ★ **Q-2 수정 3건** — `data_quality_report.schema.json` `checks.items` 에 `blocked`·`not_run` 의 `status`↔`reason_code` 제약 **추가** (m-07 §7.2 Q-2). **`reported_checks` 등식은 스키마로 표현 불가 — m-07 이 자기검증으로 처리한다**
- [ ] ★★ **`vacuous` 는 추가가 아니라 `checks.items.allOf[2]` *교체*** — `required` 에서 `reason_code` 를 빼고 `not: {required:["reason_code"]}` 를 더한다. **두 편집이 한 쌍이다.** 새 절로 추가하면 `vacuous` 행이 무엇을 써도 실패한다 (W3 재현 · m-07 §7.2)
- [ ] ★★ **C-1 수정 — 이것은 "새 필드 추가"가 아니라 `기존 불변식을 건드리는 변경`이다** (리드 실측). `common.schema.json` 에 **`value_formatted` 추가** · `allOf[0]`·`allOf[1]` `required` 에 추가 · **`allOf[2].then.not` 을 `{anyOf:[…]}` 로 교체**. ★ **`{required:["basis","value_formatted"]}` 로 쓰면 지금 작동 중인 `basis` 금지가 사라진다** (§4.16)
- [ ] ★ **회귀 검사로 취급한다** — 수정 전 거부되던 레코드가 수정 후에도 거부되는지 **먼저** 본다 (AC-4e)
- [ ] ★ **N-8 수정** — `common.schema.json` 에 **`limit_note` 추가** (선택 필드 · §4.17)
- [ ] **네 수정 전부 changelog 에 원칙 열과 함께 등재**
- [ ] **의도된 차이 목록**을 `docs/contracts/` 에 기록

> **왜 복사하나:** `build-plan.md` §2.1 이 `docs/contracts/**` 를 Phillip 소유로 배정했다. 제품 코드가 `.agent-team/`(웨이브 산출물)에 런타임 의존하는 것은 부자연스럽다.
> **다만 두 벌이 갈라질 수 있다** — 대조 테스트를 둔다 (T6).

## T2 · `contracts.py` — 봉투 생성 · 자기검증

- [ ] `envelope(artifact, run_id, provenance, notices)` 생성기
- [ ] `run_id` 생성 — `MR-{YYYYMMDD}-{HHMMSS}-{8hex}` (**KST 기준 시각**)
- [ ] `generated_at` KST 포맷터 — `+09:00` 보장
- [ ] `provenance` 수집 — `git rev-parse HEAD` · config SHA-256 · `sink_manifest_sha256` · **`generated_by`(런타임 자기 실행 기록)**
- [ ] 핵심 불변식 검증기 (표준 라이브러리 · §4.11) — **목록에 `value_formatted` 양방향을 포함한다**
- [ ] ★★ **`value_formatted` 생성 — 직렬화 시점에 `contracts.py` 가 한다** (리드 판정 · §4.16.1). **`MetricValue` → JSON 직렬화 함수가 유일한 생성 지점**이다. 호출자가 넘기지 않는다
- [ ] `unit` 별 포맷 규칙 8종 구현 — `krw`·`krw_per_customer`·`count`·`ratio`·`percentage_point`·`days`·`text`·`datetime` (§4.16.1 표). **`toLocaleString` 류 로케일 함수에 의존하지 않는다** — 재현성
- [ ] `limit_note` 는 **호출자가 넘긴다** — 정밀도 한계는 지표별 사실이지 `unit` 에서 나오지 않는다 (§4.17)
- [ ] `ContractViolation` 예외 (M-03 의 `errors.py`)

## T3 · `publish.py` — 조립

- [ ] `partition_by_source(events)` — **`sink.event_source()` 를 쓴다.** 재분류하지 않는다
- [ ] ★ `events` → `OrderView`·`OrderItem` 조립 (m-03 §4.7b 가 형태를 확정했다. **조립 주체는 여기다** — 출처를 아는 층)
- [ ] ★ `choose_headline_code(counts, ingestion_report)` — **순위를 구현하는 유일한 자리** (§4.8.1 · AC-4c). 화면·테스트가 이 함수를 부른다
- [ ] 6종 빌더 — `build_ingestion_report` · `build_rejection_report` · `build_field_coverage_report` · `build_kpi_report` · `build_freeze_status` · (품질은 M-07 의 `validate.py` 결과를 받는다)
- [ ] `build_index` — `verdict` 집계 (§4.8 B-11 가드 포함) · `views` · `static_views`
- [ ] `blocked_by` / `blocks_metrics` **양방향 사슬** 조립 (§4.6)
- [ ] 원자적 쓰기 — staging → 검증 → `os.replace` → index 마지막 → staging 삭제
- [ ] CLI — `python3 -m src.measurement.publish --source data/raw --out results`
- [ ] 종료 코드 (§4.10)

## T4 · 보안 — 거부 샘플 (AC-6)

- [ ] `samples[]` 화이트리스트 필드만
- [ ] `offending_values` 키를 **22컬럼으로 제한**
- [ ] ★ **일부러 금지 필드가 담긴 거부 레코드를 만들어, 게시물에 그 값이 없음을 확인하는 테스트**

## T5 · 픽스처 대조 테스트

- [ ] `tests/test_publish_contract.py` — `jsonschema` 있으면 전체 검증, 없으면 **skip + 사유**
- [ ] `examples/` 14파일이 **의도된 실패 목록 밖에서 전부 통과**하는지 (§4.14)
- [ ] ★ **`INTENDED_FIXTURE_FAILURES` 의 *모든* 항목이 실제로 실패하는지** — 통과해 버리면 제약이 안 걸린 것이다. **개수로 세지 않는다. dict 를 순회한다**
- [ ] ★ **`blocked_by` ↔ `blocks_metrics` 역방향 일치** 검사
- [ ] `by_event_type` 16키 · `fields` 22키 · `items` 9개 · `views` V1~V6 존재
- [ ] 계층 1·2 에 `combined` 가 없음
- [ ] `generated_at` 이 `+09:00`

## T6 · 계약 사본 대조

- [ ] ★ **`docs/contracts/measurement-publish/v1/CHANGELOG.md` 를 만든다** — 스냅샷 대비 변경 4건 + **원칙 열** (§4.8)
- [ ] ~~두 벌 바이트 일치~~ → **changelog 에 없는 차이가 생기면 실패**
- [ ] **`.agent-team/04-architecture/schemas/` 는 동결 스냅샷** — 고치지 않는다
- [ ] W5 이후 정본은 **`docs/contracts/` 하나**

## T7 · `tests/test_publish_atomicity.py`

- [ ] `index.json` 이 **마지막에** 쓰인다 (staging 중간 상태에서 index 부재 확인)
- [ ] 검증 실패 시 **최종 경로에 파일이 생기지 않는다**
- [ ] staging 디렉터리가 완료 후 **삭제된다**
- [ ] 부분 게시 시 `publish_result: partial` + 종료 코드 **0**

## T8 · ★ USP-1 대표 장면 fixture 생성 (리드 판정 J-1)

> **fixture 는 손으로 쓴 게시물 JSON 이 아니라 실제 측정 계층 파이프라인을 통과한 산출물이어야 한다.**
> *"USP-1 은 '화면이 회색 칩을 그릴 수 있다'가 아니라 '측정 계층이 계산 불가를 계산 불가로 말한다'다. 후자만 그것을 증명한다."*
> `[Source: .agent-team/07-design/design-handoff.md#2]`

- [ ] **`unit_cost` 가 없는 `purchase` 이벤트 1건 이상**을 합성 입력으로 만든다
- [ ] 실제 `EventSink` → 실제 `publish.py` 를 통과시킨다
- [ ] 산출물에서 `revenue` 는 **`ok`**, `contribution_profit` 은 **`unavailable` + `NO_COST_BASIS`** 가 나오는지 확인
- [ ] **Andrew 가 쓸 수 있게 경로와 생성 방법을 PR·인계 노트에 적는다**
- [ ] 합성 입력임을 산출물 `notices` 또는 별도 표시로 남긴다 → 화면이 `표본 데이터` 배지를 붙일 근거

## T9 · 검증 (AC-8)

- [ ] `python3 -m unittest discover -s tests` — 출력 전문 + skip 수·사유
- [ ] `python3 -m unittest tests.test_isolation -v`
- [ ] **실제 게시 1회 실행** — `python3 -m src.measurement.publish --source data/raw --out results` · 출력을 PR 에
- [ ] `python3 .agent-team/04-architecture/tools/check_ownership.py`

---

# 6. 파일 목록 (`file_list`)

## 6.1 이 스토리가 만드는 파일

| 파일 | 동작 |
|---|---|
| `src/measurement/contracts.py` | **신설** — 봉투·계약 상수·자기검증 |
| `src/measurement/publish.py` | **신설** — 유일한 조립 지점 |
| `docs/contracts/measurement-publish/v1/*.schema.json` | **신설** — 계약 7종. ★ **W5 부터 살아있는 정본** |
| `docs/contracts/measurement-publish/v1/CHANGELOG.md` | **신설** — 스냅샷 대비 변경 4건 + 원칙 |
| `tests/test_publish_contract.py` | **신설** |
| `tests/test_publish_atomicity.py` | **신설** |
| `.agent-team/04-architecture/tools/ownership.json` | **수정하지 않는다** — 이미 등록돼 있다(Thomas N-1). 돌려 **확인만** |

## 6.2 절대 만지지 않는 파일

```
tests/test_isolation.py · .github/workflows/isolation.yml          ← 봉인
.agent-team/04-architecture/schemas/*.json                         ← ★ W2 동결 스냅샷. 읽기·복사만. 갱신하지 않는다
.agent-team/04-architecture/examples/**                            ← 픽스처. 읽기만
src/simulator/** src/decision/** src/diagnostics/** src/orchestration/**
Plan/** · AGENTS.md · src/AGENTS.md · README.md
dashboard/**                                                       ← Andrew
../Ecommerce_Service/**
```

## 6.3 ⚠ `results/` 는 생성물이다

`.gitignore` 에 `results/` 를 넣을지가 **결정 D-17** 이다 (M-05 가 다룬다).
**넣으면 대시보드 스크린샷 증거를 저장소에 남길 수 없다.** W2 추천은 ⑶ — 제외하되 `.agent-team/` 에 증거 사본.

**어느 쪽이든 게시물을 커밋하지 않는다** — `AGENTS.md` *"비밀값·생성물을 커밋하지 않는다"*.

---

# 7. 테스트

## 7.1 실행 가능한 명령

```bash
python3 -m unittest discover -s tests
python3 -m unittest tests.test_publish_contract -v
python3 -m unittest tests.test_publish_atomicity -v
python3 -m unittest tests.test_isolation -v
python3 .agent-team/04-architecture/tools/check_ownership.py

# ★ 이 스토리가 신설하는 명령 — 그 전에는 존재하지 않는다
python3 -m src.measurement.publish --source data/raw --out results
```

> **이 명령은 2026-09-11 현재 실행할 수 없다.** 이 스토리가 만든다.
> **만들기 전에 문서·PR 에 "실행했다"로 쓰지 않는다.**

## 7.2 픽스처를 회귀 테스트로 쓴다

```
.agent-team/04-architecture/examples/empty-sink/          7파일 — 오늘의 실제 상태
.agent-team/04-architecture/examples/commerce-connected/  7파일 — 전 시각 상태
```

**W2 가 실행 확인한 것:**
```
tools/validate_examples.py         예시 14건 · 위반 0건
tools/check_zero_fill_rejected.py  위반 시도 15건 중 거부 15건 · 통과 0건
```

> ⚠ **위 두 실행은 스크래치패드 가상환경의 `jsonschema` 로 했다. 저장소 환경에는 `jsonschema` 가 없다.**
> **저장소 검증으로 계산하지 않는다.** 이관 조건은 M-05 의 `requirements-dev.txt` 다.
> `[Source: .agent-team/_state/wave-log.md#검증-한계]`

**`empty-sink` 픽스처의 실측 특성 — 구현이 재현해야 하는 것:**
- 검사 18건 중 **`vacuous` 7건** · **공허한 `pass` 0건**
- `gate_result: "incomplete"`
- `verdict.headline_code: "SINK_EMPTY"` · `level: "attention"`
- `metrics_unavailable: 12` · `checks_not_run: 10` · `schema_gaps: 4` · `lock_items_pending: 9`

## 7.3 깨뜨리면 안 되는 기존 테스트

| 테스트 | 이유 |
|---|---|
| `test_isolation.py` 6건 | `publish.py`·`contracts.py` 도 자동 검사 대상 |
| `test_sink.py:198-203` | USP-1 회귀 |
| `test_neutrality.py` (M-03·M-04) | `publish.py` 는 출처를 알아도 되지만 **`kpi.py`·`economics.py` 는 여전히 몰라야 한다** |
| ★ **계산 불가 + `basis` 거부** | **테스트가 아직 없다.** 픽스처에 그 레코드가 없어 아무도 안 지키고 있다. **`AC-4e` 가 이 자리를 테스트로 만든다** — 계약 수정으로 조용히 사라질 수 있는 방어다 |

---

# 8. 연속성

## 8.1 선행 스토리에서 이어받는 것

| 스토리 | 이어받는 것 |
|---|---|
| **M-02 (`#54`)** | `MetricStatus`·`ReasonCode` — 계약 enum 과 일치 보장 |
| **M-03 (`#47`)** | `MetricValue`·`Basis`·`BlockerRef` · `errors.py` · `CostAccountingConfig` · `assumptions` → `notices` |
| **M-04 (`#46`)** | 47종 정의 · `summary` 집계 구조 · 지표별 `blocked_by` 직접 원인 |
| **M-01 (`#53`)** | `manifest.created_at` KST · 파티션 보존 · `sink.event_source()` |
| **M-05 (의존성)** | `jsonschema` 가용 여부 → 자기검증 수단 (§4.11) |

## 8.2 M-07·M-09 와의 관계 — **게시는 이 스토리, 내용은 그쪽**

| 산출물 | 내용을 만드는 곳 | 게시 |
|---|---|---|
| `data_quality_report` | **M-07 `validate.py`** | 이 스토리 |
| `freeze_status` | **M-09 `freeze.py`** | 이 스토리 |
| 나머지 4종 + index | 이 스토리 | 이 스토리 |

**M-07·M-09 가 아직 없으면** 해당 산출물을 **`publish_result: partial`** 로 남기고 `index.json` 에 `status: failed` + 사유를 적는다. **빈 파일을 만들지 않는다.**

## 8.3 확립된 패턴

| 패턴 | 어디에 |
|---|---|
| **`from src.measurement import schema as sc`** | `sink.py` — 같은 alias |
| **한글 독트링·메시지** | 전 파일 |
| **guarded import** | `jsonschema` 도 같게 |
| **`@dataclass(frozen=True, slots=True)`** | `schema.py FieldSpec` |

---

# 9. 완료 정의 (DoD) · 미결정 · 차단

## 9.1 DoD

- [ ] AC-1 ~ AC-8 전부 체크
- [ ] **픽스처 2벌(14파일)이 의도된 실패 목록 밖에서는 전부 통과한다** (§4.14)
- [ ] **거부 샘플에 금지 필드 값이 없음을 테스트가 확인한다**
- [ ] ★ **B-11 을 계약에서 고쳤다** — `REJECTED_EVENTS` + 8종 우선순위. **화면 우회 코드 0건**
- [ ] ★ **파생 상태를 `metrics[]` 에 `derived: true` + `derivation` 으로 게시했고, Feature 금지 문구를 담았다** (§4.13)
- [ ] **`.agent-team/` 원본과의 의도된 차이를 기록했고 T6 이 그 밖의 차이를 잡는다**
- [ ] **T8 fixture 가 실제 파이프라인 산출물이고, 경로·생성 방법을 Andrew 에게 인계했다**
- [ ] **게시를 1회 실제로 실행하고 출력을 PR 에 붙였다**
- [ ] `AIROI-M8` 이슈가 **없는 상태로 진행했다는 사실**을 PR 에 적었다 (D-10)

## 9.2 이 스토리에서 하지 않는 것

| 항목 | 왜 |
|---|---|
| REST API · 서버 | **`DB-013` — API 서버를 두지 않는다** |
| 파일 감시 · 크론 · 스트리밍 | `DB-011` 수동 새로고침 |
| 게시물 **이력 보관** | C1 요구에 없다. `run_id` 로 확장 여지만 남긴다 (X-6) |
| 원본 이벤트 배열 게시 | 이벤트 브라우저는 C1 범위 밖 (A5) |
| `manifest.files` 파일 경로 목록 게시 | 쓰는 화면이 없다 |
| ~~파생 상태 분포 게시~~ | **리드 판정 G-8 로 바뀌었다 — 게시한다.** §4.13 |
| `data/processed/` 게시 | C1 에 산출물이 없다 |
| ~~계약 스키마 **수정**~~ | **리드 판정으로 바뀌었다 (2026-09-11) — T1 의 4건은 수정한다.** `.agent-team/04-architecture/schemas/` 는 동결 스냅샷이라 **읽기만** 하고, `docs/contracts/` 사본이 W5 부터 살아 있는 정본이다. **그 사본을 고친다** (§4.16·§4.17·m-07 Q-2). **여기 없는 수정은 여전히 금지** — 어긋나면 코드를 고친다 |

## 9.3 미결정 — 구현자가 정하고 PR 에 적는다

| # | 항목 | 선택지 |
|---|---|---|
| **M06-a** | 게시 시점 자기검증 범위 | 핵심 불변식 몇 개(권장) / 전체 — **몇 개인지 명시한다** (§4.11) |
| **M06-b** | 계약 스키마를 `docs/contracts/` 로 복사할지, `.agent-team/` 을 직접 읽을지 | 복사 **(권장 — `build-plan.md` 배정)** / 직접 읽기 (제품 코드가 웨이브 산출물에 의존) |
| **M06-c** | `blocked_by` 사슬 조립 위치 | `publish.py`(`ADR-0009`) / 계산층이 직접 원인만 담고 `publish.py` 가 전개 |
| **M06-d** | T8 fixture 산출물을 어디 두나 | `.agent-team/03-story-engineering/` 밖이어야 한다. **Andrew 가 읽을 수 있는 곳** — `results/` 는 gitignore 될 수 있다(D-17) |

## 9.4 차단

| # | 항목 | 성격 |
|---|---|---|
| **D-10** | `AIROI-M8` 이슈 신설 | **사용자 (L3).** 구현은 진행 가능하나 추적이 흐려진다 |
| **D-17** | `results/` gitignore | **사용자.** M-05 가 다룬다. T8 fixture 배치에 영향 (M06-d) |
| ~~**B-11**~~ | ~~`headline_code`~~ | ★ **해소 (리드 판정 2026-09-11)** — 계약을 고친다. §4.8 · AC-4b |
| ~~**G-8**~~ | ~~파생 상태 기록 경로~~ | ★ **해소 (리드 판정)** — 게시 시점 계산. §4.13 |
| **M-02·M-03·M-04** | 선행 스토리 | 완료 필요 |

## 9.5 하류로 넘기는 것

| 받는 쪽 | 넘기는 것 |
|---|---|
| **d-01 (대시보드 기반)** | ★ **실제 게시물** — 그 전에는 `examples/empty-sink/` 픽스처 · `provenance.generated_by` 의 실제 문자열 (빈 상태 안내에 쓸 수 있는지 확인) |
| **d-02 (관측 화면군)** | 6종 + index 의 실제 형태 · ★ **`headline_code` 8종과 계약이 정의한 우선순위** — 화면은 **코드 → 문구 매핑만** 한다 · **USP-1 대표 장면 fixture** · 파생 상태 지표(`derived: true` → `유도값` 칩) |
| **M-07 (`#48`)** | `data_quality_report` 게시 경로와 봉투 |
| **M-09 (`#49`)** | `freeze_status` 게시 경로와 봉투 · `provenance.config_hashes` 수집 방법 |

<!-- ════════ source_hash inputs (D3 · Matthias 항목5) ════════
     계산법: project-context-kr.md §12  ·  파일 24종
     재현:  아래 목록을 sorted() 하고 각 파일에 f"{path}\n{sha256_hex}\n" 를 이어붙여
            그 바이트열의 SHA-256 앞 16자리를 취한다. 없는 파일은 "MISSING".

     .agent-team/00-plan/charter.md
     .agent-team/00-plan/task-graph.md
     .agent-team/03-service-planning/user-stories.md
     .agent-team/04-architecture/adr/ADR-0001-publish-not-api.md
     .agent-team/04-architecture/adr/ADR-0002-results-measurement-subdir.md
     .agent-team/04-architecture/adr/ADR-0009-blocker-chain.md
     .agent-team/04-architecture/api-contracts.md
     .agent-team/04-architecture/build-plan.md
     .agent-team/04-architecture/code-structure.md
     .agent-team/04-architecture/design-patterns.md
     .agent-team/04-architecture/exceptions.md
     .agent-team/04-architecture/schemas/common.schema.json
     .agent-team/04-architecture/schemas/data_quality_report.schema.json
     .agent-team/04-architecture/schemas/field_coverage_report.schema.json
     .agent-team/04-architecture/schemas/freeze_status.schema.json
     .agent-team/04-architecture/schemas/index.schema.json
     .agent-team/04-architecture/schemas/ingestion_report.schema.json
     .agent-team/04-architecture/schemas/kpi_report.schema.json
     .agent-team/04-architecture/schemas/rejection_report.schema.json
     AGENTS.md
     docs/GIT_WORKFLOW.md
     src/AGENTS.md
     src/measurement/schema.py
     src/measurement/sink.py

     → source_hash = 453eccc2172bc7d2
     ════════════════════════════════════════════════════ -->
