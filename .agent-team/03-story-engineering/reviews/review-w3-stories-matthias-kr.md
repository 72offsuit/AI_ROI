---
reviewer: Matthias (Role 15 · QA Validator / SDET Lead)
stage: W3 Story Gate — 2단계 독립 리뷰 (QA 렌즈)
target: .agent-team/03-story-engineering/ — 스토리 11종 + project-context-kr.md + readiness-report-kr.md
date: 2026-09-11
verdict: CONCERNS
critical: 2
noncritical: 7
lens: QA · 테스트 커버리지 · 인수조건 충족 · "완료 거짓말" 차단
---

# W3 스토리 게이트 — Matthias 독립 검증

**판정: CONCERNS** — critical 2건을 고치면 W5 진입 가능하다. FAIL 은 아니다.

생성자(Matthew)의 요약을 받지 않고 fresh context 로 대상 문서·픽스처·스키마·코드를 직접 읽고 명령을 직접 실행했다.
**아래 모든 수치는 내가 이 기계에서 측정한 값이다. 측정하지 못한 것은 `BLOCKED` 로 적었다.**

---

# 0. 내가 실제로 실행한 것 — 전부 실행 결과다

| # | 명령 | 결과 | 용도 |
|---|---|---|---|
| 1 | `python3 -m unittest discover -s tests` | **`Ran 46 tests ... OK`** · **skip 0건** | 기준선 ④ 재현 |
| 2 | `python3 -V` | `3.14.6` | 환경 |
| 3 | `python3 -c "import jsonschema/pyarrow/pandas/yaml/pytest"` | **5종 전부 `ModuleNotFoundError`** | 의존성 실측 |
| 4 | `node -v` / `npm -v` | `v24.15.0` / `11.12.1` | 대시보드 전제 |
| 5 | `ls dashboard examples` | **둘 다 없음** | d-01·d-02 전제 |
| 6 | `python3 scripts/bench_sink.py 20000 30` | **4,200,000건 · 63.8초 · 112.6MB · 거부 0건** | m-01 AC-4 기준선 |
| 7 | `python3 scripts/gen_event_schema_doc.py \| diff - docs/event_schema.md` | **일치 ✅** (stdout 출력형, 파일 안 건드림) | m-02 AC-5 · m-09 AC-3 |
| 8 | `check_ownership.py` | **PASS** · exit 0 · 201경로(추적 125·미추적 13·계획 63) | 전 스토리 AC |
| 9 | `validate_examples.py` | **exit 2** · `BLOCKED — jsonschema 미설치` | fail closed 확인 |
| 10 | `check_zero_fill_rejected.py` | **exit 2** · `BLOCKED — jsonschema 미설치` | 동일 |
| 11 | 픽스처 2벌 `data_quality_report.json` 파싱 | **§2 표 참조** | Q-1·Q-2·Q-3 재확인 |
| 12 | `common.schema.json` · `data_quality_report.schema.json` 정독 | **§2 참조** | 스키마 강제력 검증 |
| 13 | `index.schema.json` `headline_code` enum | **7종** (`REJECTED_EVENTS` 없음) | B-11 재확인 |
| 14 | `EVENT_FIELDS` 순회 | **22개 · `signup_date` False** | F-C 재확인 |
| 15 | `Ecommerce_Service` `node scripts/tokens/verify.mjs` | **`15 scenarios passed`** · exit 0 · `git status` 변경 0 | F-A 재확인 |
| 16 | `verify.mjs` 8·9·15행 정독 | `root='../../'` · 9행 `Plan/DESIGN.md` · 15행 `scripts/design-tokens.mjs` | F-A |
| 17 | `grep js-yaml` → `resolve.mjs:1` | 토큰 파이프라인의 **유일 외부 의존** 확인 | d-01 AC-3 |
| 18 | 모듈 최상위 `import yaml` 재현 (스크래치패드) | **`FAILED (errors=1)`** — skip 이 **아니라** error | m-05 §4.3 위험 실증 |
| 19 | `ls ~/Library/Caches/ms-playwright` · `which chromium` | **둘 다 없음.** Chrome·Safari.app 은 있음 | d-02 AC-12 |
| 20 | WebSearch `CVE-2026-24009` | **실재.** docling-core PyYAML `FullLoader` RCE · 완화 `SafeLoader` | m-03·m-05 인용 검증 |

**미실행 = `BLOCKED`:**

| # | 못 한 것 | 이유 |
|---|---|---|
| B-1 | `validate_examples.py` 로 픽스처 2벌 스키마 통과 검증 | **`jsonschema` 미설치.** 설치는 내 권한 밖 |
| B-2 | `source_hash` 12건 재계산 | **대상 파일 목록이 어디에도 없다** — N-1 |
| B-3 | 격리 CI(`isolation.yml`) 실행 | GitHub Actions. 로컬에서 `act` 없음 |
| B-4 | d-01·d-02 화면 명제 검증 | **`dashboard/` 미존재.** W5 이후에만 가능 |

---

# 1. critical 2건

## ★ CR-1 — d-02: 검사 상태 `vacuous` 에 시각 매핑이 없다. V-12 방어가 **존재하지 않는 조건**을 겨눈다

**문서·위치:** `story-d-02-observability-views-kr.md` §4.2 상태표 · AC-6 · AC-7 · §4.5 C-2 보조 칩 표(376행) · §4.6 V5(492–493행)

### 무엇이 어긋났나

`ADR-0010` 이 **`checks[].status` 에 `vacuous` 를 신설하고 `pass ∧ examined_rows == 0` 을 스키마로 금지**했다. 내가 스키마에서 직접 확인한 강제 규칙:

```jsonc
// schemas/data_quality_report.schema.json  checks.items.allOf[1]
{ "if":   { "properties": { "examined_rows": { "const": 0 } }, "required": ["examined_rows"] },
  "then": { "properties": { "status": { "not": { "const": "pass" } } } } }
```

**→ 계약을 지킨 게시물에는 `status:"pass" ∧ examined_rows==0` 인 행이 존재할 수 없다.**

그런데 d-02 가 `vacuous` 를 다루는 **세 자리 전부가 그 불가능한 조합을 조건으로 쓴다:**

| 자리 | 조건 | 실제 데이터에서 참이 되나 |
|---|---|---|
| **AC-7** 첫 항목 | `status == "pass"` ∧ `examined_rows == 0` → 초록 금지 | **아니다.** 스키마가 거부한다 |
| **§4.5 C-2 표**(376행) `공허한 통과` 칩 | 발동 조건 = **"V-12"** (= 같은 조합) | **아니다** |
| **§4.6 V5**(493행) | `★ V-12 — pass ∧ examined_rows == 0 → 공허한 통과…` | **아니다** |

그리고 **§4.2 상태 8종 매핑표에 `vacuous` 행이 없다.** 그 표는 `metric_value.status` 5종(`ok`/`unconfirmed`/`unavailable`/`blocked`/`not_run`)만 덮는다.
**AC-6 은 "시각 상태가 `(status, reason_code)` 의 순수 매핑이다" 를 요구하는데, 그 매핑에 `vacuous` 키가 없다.**

### 실제 데이터 — 내 측정

```
examples/empty-sink/data_quality_report.json
  checks 18건 · gate_result "incomplete"
  status 분포:  vacuous 7 · not_run 10 · blocked 1
  vacuous 7건 = DQ-01 · DQ-02b · DQ-04 · DQ-07 · DQ-08 · DQ-10 · DQ-11
  (= m-07 AC-2 의 "C1 실행 가능 7종" 과 정확히 일치)
  pass ∧ examined_rows==0  →  0건
```

**빈 Sink 는 오늘의 정상 상태다.** d-02 AC-13 이 *"빈 Sink 픽스처로 렌더 시 예외 없이 전부 계산 불가"* 를 요구하므로 **Andrew 는 첫날 이 7행을 그린다.**

### W5 에서 일어나는 일 — 구체적으로

Andrew 가 AC-6 대로 `(status, reason_code) → 시각 상태` 순수 매핑 함수를 쓴다:

```ts
// §4.2 표를 그대로 옮긴 결과 — vacuous 키가 없다
switch (status) {
  case 'ok': …  case 'unconfirmed': …  case 'unavailable': …
  case 'blocked': …  case 'not_run': …
  default: /* ← DQ-01·02b·04·07·08·10·11 이 여기로 떨어진다 */
}
```

그리고 AC-7 의 가드는 `pass && examined_rows===0` 이라 **한 번도 발동하지 않는다.**
남은 단서는 §4.6 V5 의 *"검사 행 5상태 — pass/fail/**vacuous**/not_run/blocked"* 한 줄과, 같은 문서 849행의 *"**`vacuous` 가 오늘의 정상 상태**"* 다.
**"정상 상태"라는 문구는 중립·초록 쪽으로 기울게 만든다.** `ADR-0010` 이 막으려던 바로 그 오독이다:

> *"`status` 가 `pass` 다. **순진하게 구현하면 초록 ✓ PASS 로 그려진다 — 아무것도 검사하지 않았는데.**"*

**계약이 값을 `pass` 에서 `vacuous` 로 바꿔 첫째 층을 막았는데, 화면 층의 규칙이 옛 값에 그대로 남아 있다.** 방어가 한 층 통째로 비었다.
**18행 중 7행(39%) 이 정의되지 않은 경로로 떨어진다. 그 7행은 이 프로젝트의 USP-1 이 가장 정면으로 겨누는 행이다.**

### 무엇을 고쳐야 하나 (지적만 — 나는 스토리를 고치지 않는다)

1. **§4.2 표에 검사 행 상태 5종을 별도 표로 추가한다.** 지금 표는 지표(`metric_value`)용이고 검사(`checks[]`)용이 없다. **두 열거형은 값이 다르다** — `pass`/`fail`/`vacuous` 는 지표 쪽에 없고 `ok`/`unconfirmed`/`unavailable` 은 검사 쪽에 없다. 한 표에 섞으면 안 된다.
2. **`vacuous` 에 글리프·색·값 슬롯을 명시 배정한다.** `gap`/`env_blocked`/`provisional` 을 3중(값 슬롯·선 종류·글리프)으로 가른 것과 같은 수준으로.
3. **AC-7·C-2 칩·V5 의 조건을 `status === "vacuous"` 로 바꾼다.** `pass ∧ examined_rows==0` 은 **계약 위반 입력에 대한 2차 방어(`violation` 상태)** 로 따로 남긴다 — 없애지 말고 역할을 나눈다.
4. **AC 에 명제를 추가한다:** *"empty-sink 픽스처를 렌더했을 때 `vacuous` 7행이 `✓`·초록·`success` 토큰 없이, 각 행에 `공허한 통과 · 검사 대상 0행` 과 `scope` 가 붙어 그려진다."* — **이것이 실행하면 참/거짓이 갈리는 형태다.**

---

## ★ CR-2 — m-07: `commerce-connected` 픽스처가 검사 11종을 **목록에서 뺐다**(7 vs 18). 결함 3건 표에 없다

**문서·위치:** `story-m-07-data-quality-kr.md` §7.2 *"픽스처가 기대 형태를 준다"* · AC-2 · AC-3 · AC-8b(`Q-1`/`Q-2`/`Q-3`)
**관련:** `story-m-06-publish-kr.md` T5(픽스처 대조 테스트) · `story-d-02-…` §4.6 V5 마지막 항목

> **식별자 주의:** 아래 `Q-1`/`Q-2`/`Q-3` 은 **`story-m-07-data-quality-kr.md` §7.2 내부 번호**다 (리드 판정 ③ 의 "Q-2 묶음 전체"가 아니다).

### 내가 센 것

```
empty-sink          checks 18 · reported_checks 18 · gate incomplete
                    ids: DQ-01 02 02b 03 04 05 06 07 08 09 10 11 12 13 14 15 16 17

commerce-connected  checks  7 · reported_checks  6 · gate fail
                    ids: DQ-01 02b 07 08 10 09 17
                    실행된 것(pass/fail): DQ-01 02b 07 08 10  ← 5종뿐
                    빠진 것: DQ-02 03 04 05 06 11 12 13 14 15 16   ← 11종
```

**m-07 §7.2 는 이 두 줄을 실측으로 정확히 적었다. 그러나 `checks 7` 을 결함으로 표시하지 않았다.**
결함표에 오른 것은 `Q-1`(17 vs 18) · `Q-2`(`DQ-06` status↔reason_code) · `Q-3`(`reported_checks` 6 vs 7) **셋뿐이다.**

### 왜 이것이 결함인가 — 스토리 자신의 AC 와 정면 충돌한다

| 근거 | 문장 |
|---|---|
| **m-07 AC-3** | *"**미실행 항목을 목록에서 빼지 않는다**"* |
| **스키마 `checks` description** | *"C1 에서 실행할 수 없는 항목도 목록에 남기고 `not_run` 으로 적는다 — **목록에서 빼면 '검사하지 않았다'가 보이지 않는다**"* |
| **d-02 §4.6 V5** | *"**게시물이 주는 검사만 그린다** — 정본 목록을 화면 상수로 들지 않는다 (**게시물이 18건 전부 준다**)"* |
| **`spec_coverage` description** | *"화면이 정본 목록을 상수로 들고 있으면 정본이 두 벌이 되고, 게시물이 주는 것만 그리면 **빠진 검사가 사라진다 — 사라진 것은 통과처럼 읽힌다**"* |

**`commerce-connected` 는 계약이 명문으로 금지한 바로 그 형태다.** 그리고 **AC-2 의 "실행 가능 7종"과도 어긋난다** — AC-2 는 `DQ-01·02b·04·07·08·10·11` 인데 픽스처가 실행한 것은 `DQ-01·02b·07·08·10` 5종이고, **`DQ-04`(시간 정합성)·`DQ-11`(완전성) 은 픽스처에 아예 없다.** 대신 AC-2 에 없는 `DQ-09`·`DQ-17` 이 들어 있다.

### W5 에서 일어나는 일 — 구체적으로

1. Phillip 이 §7.2 제목 *"**픽스처가 기대 형태를 준다**"* 를 읽는다. 바로 아래 결함 3건 표가 있다. **거기 없는 것은 정상이라고 읽는다.** 이것이 결정적이다 — 결함을 열거한 문서에서 열거되지 않은 것은 "확인했고 문제없다"로 읽힌다.
2. **m-06 T5 "픽스처 대조 테스트"** 를 쓴다. 연결 상태의 정답 형태로 `commerce-connected` 를 쓰면 **`len(checks)==7` 이 테스트에 고정된다.**
3. 스키마는 못 잡는다 — 내가 확인한 `checks` 제약은 **`minItems: 1` 뿐이다.** `maxItems` 도 없고 18 을 요구하는 것도 없다.
4. 결과: 커머스가 연결되는 순간 게시물이 **7건만 보고**하고, 화면은 *"게시물이 주는 검사만 그린다"* 대로 7건만 그린다. **`DQ-04`·`DQ-11` 을 포함한 11종이 화면·리포트·CI 어디에도 나타나지 않는다.**
   **`gate_result` 는 `fail`(위반이 있으므로) 이라 게이트 층조차 이 소실을 가리지 못한다.**

**이것이 "8대 치명적 실수 7번 — 완료 거짓말"의 교과서적 형태다.** 미실행이 통과로 표시되는 것보다 나쁘다 — **미실행이 아예 존재하지 않은 것이 된다.**

### 무엇을 고쳐야 하나

1. **§7.2 결함표에 `Q-4` 를 추가한다:** *"`commerce-connected` 가 검사 11종을 목록에서 뺐다(7 vs 18). **픽스처가 틀렸다. 구현은 어느 상태에서도 18건을 전부 낸다.**"*
   → `Q-3`(`reported_checks` 6 vs 7)은 이 결함의 **부산물**이다. 원인은 `reported_checks` 가 아니라 **목록 자체가 잘렸다는 것**이다. 지금 Q-3 만 고치면 `reported_checks: 7` 이 되고 **11종 소실은 그대로 남는다.**
2. **AC-2 와 픽스처의 실행 집합 불일치(`DQ-04`·`DQ-11` 부재)를 명시한다.** AC-8 이 *"실행 가능한 7개 검사 각각에 위반 데이터를 만들어 `fail` 확인"* 을 요구하는데, 그 7종 중 2종은 **픽스처에 선례가 없다.** 구현자가 참고할 형태가 없다는 사실을 적어야 한다.
3. **AC-8b 에 명제를 추가한다:** *"`len(checks) == 18` 을 게시 자기검증(`contracts.py`)과 `tests/test_quality_checks.py` 가 **두 픽스처 상태 모두에서** 단언한다. 17 이나 19 를 일부러 만들어 실제로 실패하는지 확인한다."*
   → **`Q-3` 과 같은 층(스키마 불가 → 자기검증+테스트)에 두면 된다.** 이미 그 자리가 만들어져 있다.
4. **m-06 T5 에 한 줄:** *"`commerce-connected` 의 `checks` 배열은 대조 기준으로 쓰지 않는다 (`Q-4`). 봉투·필드 형태만 대조한다."*

---

# 2. Matthew 의 §10 "Matthias 에게" 5건 — 답

## ① AC 가 전부 검증 가능한가 — 특히 d-02 의 C-2·C-11

**대체로 그렇다. 예외 4건.**

**좋은 쪽부터 — 이것은 실측이다.** 11개 스토리의 AC·DoD 에 등장하는 **모든** 백틱 명령을 전수 추출해 각각 실행 가능성을 확인했다:

| 명령 | 상태 |
|---|---|
| `python3 -m unittest discover -s tests` | **지금 실행됨** (46 OK) |
| `python3 -m unittest tests.test_isolation -v` | 지금 실행됨 |
| `python3 .agent-team/04-architecture/tools/check_ownership.py` | 지금 실행됨 (PASS) |
| `python3 scripts/bench_sink.py 20000 30` | 지금 실행됨 (63.8초) |
| `python3 scripts/gen_event_schema_doc.py` | 지금 실행됨 (문서와 일치) |
| `npm run tokens:check` · `tokens:test` | **d-01 이 만든다.** §7.1 이 *"2026-09-11 현재 존재하지 않는다. 이 스토리가 만든다"* 를 명시 |
| `grep -rn …` 3종 | 표준 도구 |

**→ 존재하지 않는 명령을 AC 에 넣은 스토리는 0건이다.** `pytest`·`ruff`·`mypy`·`make`·`docker` 같은 미설치 게이트를 지어낸 자리가 하나도 없다. **이 저장소의 실행 가능한 검증이 `unittest discover` 하나뿐이라는 사실을 11개 스토리 전부가 지켰다.** 이것은 드문 일이고, 내가 가장 세게 찾은 함정이 여기서 나오지 않았다.

**C-2·C-11 에 대해:** d-01 §7.2 가 *"**C-2·C-11 은 자동화가 어렵다. 어려운 것을 통과로 적지 않는다**"* 라 적었고 d-02 DoD 가 *"**자동화하지 못했으면 그렇게 적었다**"* 를 항목으로 두었다. **처리 방식은 옳다.** 다만 검증 방법이 없다 — 내 제안:

| 항목 | 자동화 가능한 대체 명제 |
|---|---|
| **C-2** `—` 의 font-size 가 값과 같다 | **CSS 층에서 정적으로 검사할 수 있다.** `MetricCell` 의 값 슬롯이 상태와 무관하게 **같은 클래스/토큰**을 쓰는지 grep — 즉 *"값 슬롯에 `text-caption`·`text-sm` 등 축소 토큰이 조건부로 붙는 코드가 0건"*. **육안보다 강하고 스크린샷보다 싸다** |
| **C-11** 모든 글리프에 `aria-label` | **자동화 가능하다.** 글리프 문자(`◐ · ○ ⚠ ⊘ ? ✕`)를 렌더하는 지점이 `StateChip` **한 컴포넌트로 수렴**하면 *"글리프 리터럴이 `StateChip.tsx` 밖에 0건"* 이라는 grep 명제가 된다. 그 안에서 `aria-label` 필수는 타입으로 강제 |

**→ "자동화 어려움"으로 남긴 2건 중 최소 C-11 은 구조 제약으로 바꾸면 자동 검증 가능하다.** noncritical(N-6)로 기록한다.

**검증 불가로 남는 4건:**

| # | AC | 왜 |
|---|---|---|
| 1 | **d-02 AC-12 · DoD 스크린샷** | **N-4** 참조. 무조건 체크박스인데 수단이 §9.4 에 없다 |
| 2 | **m-01 AC-4 벤치 "회귀 없음"** | **N-2** 참조. 허용 오차가 없다 |
| 3 | **m-08 AC-1 "서비스 UI 담당자가 이 문서만 보고 알 수 있다"** | 자족성은 **사람이 읽어야** 판정된다. 대체 명제 제안: *"m-08 이 인용한 값 규약이 `schema.py` 의 Enum 과 문자 단위로 같다는 것을 테스트가 단언한다"* — m-02 AC-6 이 이미 같은 패턴(`common.schema.json` enum ↔ Python Enum 문자 대조)을 쓰고 있으므로 그대로 확장 가능하다 |
| 4 | **d-01 AC-2 "`AGENTS.md` 가 DG-1~DG-8 을 전부 담는다"** | 문서 내용 판정. 대체: 8개 식별자 문자열 grep |

## ② `F-B` `Q-1`·`Q-2`·`Q-3` — W3 판단(18 · `blocked` · `len(checks)`)이 옳은가

**셋 다 판단은 옳다. 재현했다. 단 `Q-4`(→ CR-2)가 빠졌고, `Q-3` 의 원인 진단이 얕다.**

| # | W3 판단 | 내 재현 | 판정 |
|---|---|---|---|
| **Q-1** 18종 | 픽스처·표가 18, 본문이 17 | `len(checks) == 18` · `reported_checks == 18` (empty-sink) | ✅ **18 이 옳다** |
| **Q-2** `blocked`+`BLOCKED` | 픽스처 `DQ-06` = `not_run`+`BLOCKED` | 확인. 같은 파일 `DQ-17` = **`blocked`+`BLOCKED`** — **같은 파일 안에서 두 표기가 공존한다** | ✅ **`blocked` 로 통일이 옳다.** `DQ-17` 이 이미 그 형태이므로 다수결로도 그쪽이다 |
| **Q-3** `len(checks)` | `reported_checks: 6` vs `checks` 7건 | 확인 | ⚠️ **조치는 옳으나 원인 진단이 틀렸다** — CR-2 |

### `Q-2` 의 스키마 제약 — **초안대로 넣으면 뚫린다**

m-07 §7.2 가 제안한 `allOf` 두 벌은 형태는 맞다. 그런데 **`vacuous` 를 빼놓았다.** 지금 스키마에서 `vacuous` 는 `reason_code` **필수**이지만 **어떤 값이든** 받는다. 그리고 픽스처 실측:

```
empty-sink 의 vacuous 7건 전부:  reason_code = "NOT_RUN"
```

**`vacuous` 는 "검사를 실행했는데 대상이 0행이었다"이고 `NOT_RUN` 은 "실행하지 않았다"이다. 정반대다.**
이것은 `Q-2` 와 **똑같은 종류의 결함**이다 — 실행 여부에 대해 `status` 와 `reason_code` 가 서로 다른 말을 한다. `Q-2` 를 잡았으면 이것도 같은 그물에 걸려야 했다.

**그리고 CR-1 과 맞물린다.** d-02 AC-6 이 **`(status, reason_code)` 순수 매핑**을 요구하므로, 화면은 `("vacuous", "NOT_RUN")` 이라는 **자기모순 쌍**을 받는다. `reason_code` 만 보는 분기를 타면 *"미실행"* 으로, `status` 만 보면 *"공허한 통과"* 로 그려진다. **같은 행이 두 가지로 그려질 수 있다.**

**→ 권고:** `Q-2` 의 스키마 `allOf` 에 셋째 벌을 넣는다. `reason_code` enum 9종에 `vacuous` 에 맞는 코드가 **없으므로** 둘 중 하나를 골라야 한다:

| 안 | 내용 | 비용 |
|---|---|---|
| **⑴** | `reason_code` enum 에 **`VACUOUS_NO_ROWS`** 추가 후 `status=="vacuous" → reason_code=="VACUOUS_NO_ROWS"` 강제 | `common.schema.json` enum 변경 → **d-02 §4.2 매핑표·`MetricStatus`/`ReasonCode` Enum(m-02 AC-6) 동반 변경.** `ReasonCode` 9종 → 10종 |
| **⑵** | `status=="vacuous"` 일 때 **`reason_code` 를 금지**하고 `reason_detail` 만 필수로 둔다 | enum 안 건드림. **`vacuous` 는 그 자체로 사유이므로 코드가 중복이다.** `metric_value` 쪽 9종을 검사 행에 재사용한 것이 애초에 무리였다 |

**나는 ⑵ 를 권한다** — `m-02` AC-6 이 *"`ReasonCode` Enum 9종 — 계약 정본과 정확히 일치"* 를 **문자 단위 대조 테스트로** 고정하려 하고 있어서, 지금 enum 을 늘리면 m-02·m-06·m-07·d-02 네 스토리가 동시에 움직인다. **다만 이것은 계약 판단이므로 리드·Thomas 영역이다. 나는 "지금 상태로는 자기모순 쌍이 통과한다"는 사실만 낸다.**

## ③ m-05 `A7` 판정 7항목이 `A7` 을 실제로 증명하는가

**charter `A7` = "의존성 도입 후에도 CI 격리 검사가 유지된다".**

**6/7 은 증명한다. `A7-4` 한 항목에 구멍이 있다.**

**먼저 잘한 것:** m-05 §4.3 이 위험을 정확히 짚었다 — *"`isolation.yml` 의 'Run all tests' 단계(의존성 미설치)가 `ImportError` 로 실패한다"*. **내가 스크래치패드에서 재현했다:**

```
tests/test_bad.py 에 최상위 import yaml 한 줄
$ python3 -m unittest discover -s tests
ModuleNotFoundError: No module named 'yaml'
Ran 1 test in 0.000s
FAILED (errors=1)      ← skip 이 아니라 error. CI 빨강
```

§4.4 의 `try/except ImportError` + `@skipUnless` 해법이 정확히 이것을 막는다. **`A7-6`(`import yaml` 봉쇄)·`AC-2`(`pyarrow` 지연 import 유지)와 함께 이 사슬은 튼튼하다.**

### 구멍 — `A7-4` "기준선 46건에서 회귀 0" 의 **판정 방법이 없다**

`unittest` 요약행은 **skip 된 테스트를 `Ran N` 에 포함한다.** 그래서:

```
기준선(오늘 내 실측):   Ran 46 tests ... OK              ← skip 0건
m-05 후 정상:          Ran 50 tests ... OK (skipped=4)   ← 신규 4건이 skip
m-05 후 사고:          Ran 50 tests ... OK (skipped=4)   ← 기존 4건이 skip 으로 바뀌고 신규 4건이 통과
```

**요약행이 같다.** `A7-4` 를 "요약행 확인"으로 채우면 두 경우가 구분되지 않는다.
`A7-5`(skip 수·사유 PR 기록)가 완화하지만, **"수"만으로는 여전히 안 된다** — 위 두 경우는 skip 수도 4로 같다.

**→ 권고 (한 줄이면 된다):**

> **`A7-4` 판정 = `python3 -m unittest discover -s tests -v` 출력에서 skip 된 테스트의 `모듈.클래스.메서드` **이름 목록**을 PR 에 붙인다. **기준선의 skip 은 0건이므로 그 목록은 전부 이 PR 이 새로 추가한 테스트여야 한다.** 목록에 기존 테스트 이름이 하나라도 있으면 회귀다.**

**"수"가 아니라 "이름"이어야 한다.** 이것이 `A7-5` 를 실제로 검증 가능하게 만든다. noncritical(N-3).

**나머지 `A7-3` 의 "로컬 또는 `tests-with-deps.yml`" 에 대해:** `tests-with-deps.yml` 은 **`D-19` 사용자 승인 사항**이고 m-05 가 *"확인 전에 만들지 않는다"* · *"미승인이면 만들지 않았고 그 사실을 PR 에 적는다"* 로 **정직하게 처리했다.** 이의 없다. 다만 미승인 경로에서는 `A7-3` 이 **로컬 1회 실행 증거**로만 남아 CI 재현성이 없다는 사실이 `M-09` 의 `BLOCKED` 목록에 가야 한다 — m-05 AC-3 이 `DQ-17`·`gate1_checklist.md` 인계를 이미 지시하고 있으므로 **같은 자리에 `A7-3` 도 넣으면 된다.**

## ④ `F-C` `customers` 부재 — `PRECONDITION_MISSING` 처리가 옳은가

**옳다. 재현했다. 단 `repurchase_rate` 한 건은 과대 재분류다.**

**재현:**
```
EVENT_FIELDS 22개 — signup_date 없음 (False)
['campaign_id','category','coupon_id','customer_id','customer_version','event_id','event_type',
 'experiment_id','order_amount','order_id','page_type','product_id','quantity','random_seed',
 'service_version','session_duration','session_id','simulator_version','timestamp',
 'treatment_group','treatment_id','unit_price']

kpi-definition-v1.md:149  cohort_retention_rate[m] | 모집단 "가입월 코호트" | C1: ✅
```

**`cohort_retention_rate[m]` 은 명백히 옳다.** 가입월 코호트를 `events` 만으로 만들 수 없다. `✅` 가 틀렸고 m-04 AC-3b 가 맞다. *"`events` 첫 등장일은 가입일이 아니다"* 도 정확하다 — 이벤트 기록 시작 시점에 이미 존재하던 고객은 첫 등장일이 가입일보다 늦다. **좌측절단(left truncation)** 이고, 보정 불가다.

### ⚠ `repurchase_rate` 는 다르다

```
kpi-definition-v1.md:150
  repurchase_rate = |{c : purchase_count(c,[D−L,D]) ≥ 2}| / |{c : purchase_count(c,[D−L,D]) ≥ 1}|
  모집단 P_all(D) · 분모 "기간 내 1회 이상 구매 고객"
```

**분자·분모 둘 다 `purchase` 이벤트만으로 계산된다. `signup_date` 가 한 번도 나오지 않는다.**
막힌 것은 **계산이 아니라 `모집단` 칸에 적힌 `P_all(D)` 라는 선언**이다. 계산식과 모집단 선언이 애초에 불일치한다 — **이것은 `customers` 부재 문제가 아니라 `kpi-definition-v1.md` 자체의 내부 모순이다.**

**m-04 §4.5(329행)는 이것을 알고 있다:**
> *"`events` 에 등장한 고객으로 근사할 수 있으나 그것은 `P_all` 이 아니다 → `PRECONDITION_MISSING` **또는 모집단 정의를 `basis.population` 에 정확히 적는다**"*

**그런데 AC-3b 는 "또는"을 지우고 `unavailable` + `PRECONDITION_MISSING` 하나로 고정했다.**

여기서 걱정되는 것: `unavailable` + `PRECONDITION_MISSING` 은 **"근거가 없어 계산할 수 없다"** 는 뜻이다. 그런데 근거는 있다 — 분모가 `P_all` 이 아닐 뿐이다. **계산할 수 있는 것을 "근거 없음"으로 적는 것은, 이 프로젝트가 막으려는 것의 거울상이다.** 과대보고가 아니라 과소보고지만, **이유를 틀리게 말한다는 점은 같다.**

**→ 권고 (셋 중 하나를 AC 가 골라야 한다. 지금은 §4 와 AC 가 다른 말을 한다):**

| 안 | 처리 | 정직한가 |
|---|---|---|
| **⑴** | `basis.population` 을 *"기간 [D−L, D] 내 `purchase` ≥ 1건인 고객"* 으로 **정확히 적고 `ok` 로 계산** + `notices` 에 *"`kpi-definition-v1.md` 의 `P_all(D)` 선언과 다르다"* | **가장 정직하다.** R-4 는 *"'고객'이라고만 쓰지 마라"* 이지 *"선언과 다르면 계산하지 마라"* 가 아니다 |
| ⑵ | `unavailable` + **`MISSING_FIELD`**(`PRECONDITION_MISSING` 아님) | 사유가 더 정확하나 여전히 계산 가능한 값을 버린다 |
| ⑶ | 현행 AC-3b (`unavailable` + `PRECONDITION_MISSING`) | 가장 보수적. **`cohort_retention_rate` 와 성격이 다른 것을 같게 취급한다** |

**⑴ 을 권한다.** 그리고 어느 쪽이든 **§4.5(329행)의 "또는" 분기를 지워야 한다** — AC 와 `developer_context` 가 다른 지시를 하면 구현자가 AC 를 어기는 쪽을 고를 수 있다. noncritical(N-5).

**`P_eligible` 계열은 AC-3b 대로가 맞다** — `P_eligible` 정의 자체가 `signup_date` 를 쓴다.

## ⑤ `source_hash` 계산법이 재현 가능한가 — **아니다. 실행할 수 없다**

**결과: `BLOCKED` — 재현 시도했으나 불가능하다.**

계산법 자체는 완전하고 결정적이다. `readiness-report-kr.md` §D3 의 5단계는 다른 도구로 그대로 구현할 수 있다. **문제는 알고리즘이 아니라 입력이다.**

```
$ grep -rn "source_files" .agent-team/03-story-engineering/*.md
story-m-01-…:12:  source_files: 17     ← 개수뿐
story-m-02-…:12:  source_files: 19
…  (12건 전부 개수만)
```

**어느 문서에도 해시 대상 파일의 경로 목록이 없다.** 프론트매터는 `source_hash` 와 `source_files`(개수)만 담는다.

**대안 복원 시도:** m-01 의 `[Source: …]` 인용을 전수 추출해 고유 경로를 뽑았다 → **16개**, 그중 `gh issue`·`경로` 같은 비경로 토큰 2개를 빼면 **14개**. **17 과 맞지 않는다.** 인용되지 않은 파일(`src/measurement/sink.py`·`schema.py`·`tests/test_sink.py` 등)이 해시 대상에 들어갔을 가능성이 높지만 **어느 조합인지 알 방법이 없다.**

### 왜 이것이 실제 문제인가

`readiness-report-kr.md` §D3 가 용도를 이렇게 적었다:

> *"**구현자가 스토리를 열 때 다시 계산해 다르면 스토리가 낡았다는 뜻**이고 리뷰어에게 보고한다."*

**구현자는 이 동작을 수행할 수 없다.** 대상 목록이 없으므로 재계산이 불가능하고, 재계산할 수 없으므로 비교도 불가능하다. **D3 신선도 방어는 현재 Matthew 만 실행할 수 있는 방어다** — 그리고 Matthew 는 W3 에서 나간다.

*(Matthew 의 "17파일 재해시 → `f9b50547bbb181fb` 재현"은 참일 것이다. 목록을 가진 사람이 자기 계산을 재현한 것이므로 — 다만 그것은 **알고리즘의 결정성**을 증명하지 **제3자 재현 가능성**을 증명하지 않는다.)*

**→ 권고:** 프론트매터에 `source_list:` 를 넣거나(12개 파일 × 17~62줄 → 스토리가 길어진다), **각 스토리 §8 끝에 `<!-- source_hash inputs: path1 path2 … -->` 주석 블록**을 둔다. 후자가 싸다. noncritical(N-1).

---

# 3. charter §3.1 ①~④ 커버리지 판정

| | 완료 조건 | 덮는 것 | 판정 |
|---|---|---|---|
| **①** | 커머스 갭 정리 (대조표 · `#24`~`#30` 커버 검증 · **제거 축** · 이슈는 사용자 지시 후 · 커머스 변경 0건) | **스토리 11종 어디에도 없다.** W1 `01-reverse/` 가 덮는다 — `ecommerce-gap.md`·`issue-code-audit.md`·`issue-drafts/ECOM-E7-removal-targets.md`(제거 축)·`E8`·`E9`·`E10`·`E11` | ⚠️ **실질 덮임 · 기록 누락** (N-7) |
| **②** | 측정 계층 완주 `#45`~`#49` | `#45`→m-08 · `#46`→m-04 · `#47`→m-03 · `#48`→m-07 · `#49`→m-09. 추가로 m-01(`#53`)·m-02(`#54`)·m-05·m-06 | ✅ **전부 덮임** |
| **③** | GA형 대시보드 (수집·KPI·품질 화면 · **출처 구분** · **계산 불가를 0 으로 표시 안 함**) | d-01(골격·토큰·읽기 계층) · d-02(화면 8개·컴포넌트 8종). 출처 구분 = d-02 AC-8. 0 채우기 금지 = d-02 AC-3 + d-01 AC-6 | ✅ **덮임** · CR-1 이 `vacuous` 구멍 |
| **④** | 회귀 없음 (46건 · 격리 CI · 신규 의존성 후에도 유지) | **11개 스토리 전부**가 마지막 AC 로 동일 4항목을 반복. 의존성 축은 m-05 `A7-1`~`A7-7` | ✅ **덮임** · N-3 이 판정 방법 구멍 |

## ① 에 대한 판정 — **덮이지 않은 것은 아니다. 기록되지 않았다**

`readiness-report-kr.md` §1.1 이 스토리 11종을 이슈에 매핑하면서 **charter §3.1③ 은 두 번 명시했지만 §3.1① 은 한 번도 언급하지 않는다.** 내가 스토리 디렉터리 전체를 grep 했다:

```
$ grep -rn "§3.1\|커머스 갭\|제거 축\|ECOM-E7" .agent-team/03-story-engineering/*.md
→ §3.1③ 5건 · "커머스 갭" 1건(권한 문맥) · "제거 축" 0건 · "ECOM-E7" 0건
```

**리드가 이 문서를 C1 커버리지 원장으로 쓰면 ① 이 공백으로 보인다.** ① 은 코드 작업이 아니라 W1 산출물이므로 W5 스토리가 없는 것이 **정상**이다 — 그 사실이 적혀 있어야 한다.

**그리고 ① 에는 실제로 열려 있는 항목이 있다:**
- `[ ] 이슈 발행·수정은 **사용자 명시 지시 후에만** 실행` — **미완.** `ECOM-E7`~`E11` 은 **초안** 상태이고 발행되지 않았다. 이것은 사용자 결정 대기이지 결함이 아니다.
- `[ ] 기존 이슈 `#24`~`#30`이 갭을 빠짐없이 덮는지 검증 — 누락분은 신규 이슈 초안 작성` — `issue-drafts/` 에 5건이 있으므로 수행된 것으로 보이나, **W3 문서만으로는 확인할 수 없다.**

**→ `readiness-report-kr.md` §1.1 표 아래에 한 줄:** *"charter §3.1① 은 W1(`01-reverse/`)이 덮으며 W5 스토리를 만들지 않는다. 남은 것은 이슈 발행 여부(사용자 결정)뿐이다."* noncritical(N-7).

---

# 4. ★ "완료 거짓말" 함정 — 스토리별 판정

**리드가 지목한 8대 실수 7번. 내 영역이다. 스토리 11종을 전수 검사했다.**

## 결론: **없는 명령을 AC 에 넣은 스토리는 0건이다.** 다른 형태의 함정이 3건 있다

| # | 스토리 | 함정 | 심각도 |
|---|---|---|---|
| **T-1** | **m-07** | `commerce-connected` 픽스처를 *"기대 형태"* 로 제시하면서 검사 11종 소실을 결함표에서 뺐다 → 구현이 7건만 게시해도 스키마·테스트·화면 전부 통과 | **critical (CR-2)** |
| **T-2** | **d-02** | AC-12·DoD 의 스크린샷 4종이 **무조건 체크박스**. 자동화 수단 부재가 §9.4 차단에 없다 | noncritical (N-4) |
| **T-3** | **m-01** | AC-4 벤치 *"기준선 4,200,000건 / 64.7초 / 112.6MB 대비 회귀 없음"* — **허용 오차가 없다.** 무엇이든 "회귀 없음"으로 적을 수 있다 | noncritical (N-2) |

**T-1 이 유일한 critical 급 함정이다.** T-2·T-3 은 구현자가 정직하면 `BLOCKED`/수치 병기로 넘어갈 수 있다.

## 반대로 — 정직하게 처리된 것 (이것은 통과로 적는다)

내가 세게 찾았고 **찾지 못한 것들**을 적는다. 없는 결함을 만들지 않기 위해서다:

| 자리 | 어떻게 처리했나 |
|---|---|
| `pyarrow` 미설치 | m-01 §9.2 *"Parquet 경로 검증 — **pyarrow 미설치 → `BLOCKED`.** M-05 의 몫"* — 떠넘기지 않고 **이관**했다 |
| PyYAML 미설치 | m-03 §4.8 *"**PyYAML 이 없으면 `ConfigError` 로 멈춘다. 폴백하지 않는다**"* + `@skipUnless(…, "BLOCKED: PyYAML 미설치 — config 로딩 경로를 검증하지 않았다")` — **skip 사유 문자열에 `BLOCKED` 를 박았다** |
| `jsonschema` 미설치 | m-06 AC-8 *"`jsonschema` 는 dev 전용 → 없으면 skip + 사유"* |
| `dashboard/` 미존재 | readiness §11 `L-2` *"d-01·d-02 의 화면 명제는 전부 `BLOCKED — 대시보드 미구현`"* |
| lock 버전 미확정 | readiness §7 `R-1` *"**W3 이 정확한 lock 버전을 확정하지 못했다**"* — 지어내지 않고 m-05 AC-1 로 이관 |
| `tests-with-deps.yml` | m-05 *"`D-19` 미승인이면 **만들지 않았고 그 사실을 PR 에 적는다**"* |
| `#53` 등 이슈 close | m-01 DoD *"`#53` 을 **닫지 않았다** — Issue close 는 개별 승인 사항"* |
| 검증도구 fail closed | **내가 실행 확인:** `validate_examples.py`·`check_zero_fill_rejected.py` 둘 다 `jsonschema` 부재 시 **`exit 2`** + *"통과로 적지 않는다"* 출력. **`exit 0` 으로 조용히 넘어가지 않는다** |
| `L-1`~`L-7` | readiness §11 이 한계 7건을 **판정 없이** 나열. *"이 문서에 판정이 없는 이유다"* |

**미실행을 통과로 적은 자리를 하나도 찾지 못했다.** `BLOCKED` 표기는 **정직하다**. 이것은 통과다.

---

# 5. noncritical 7건

| # | 대상 | 내용 | 조치 |
|---|---|---|---|
| **N-1** | 전 스토리 프론트매터 | **`source_hash` 대상 파일 목록이 없다** → 구현자가 재계산 불가. D3 신선도 방어가 Matthew 외에는 실행 불가 (§2⑤) | 각 스토리 §8 끝에 `<!-- source_hash inputs: … -->` 주석 |
| **N-2** | `m-01` AC-4 | 벤치 **허용 오차 없음**. 내 실측 **63.8초 / 112.6MB / 거부 0건** (기준선 64.7초 대비 −1.4%) — 20% 느려져도 "회귀 없음"으로 적을 수 있다 | *"기준선의 ±15% 이내. 벗어나면 수치를 PR 에 적고 원인을 밝힌다"* 같은 판정 규칙 |
| **N-3** | `m-05` `A7-4` | **"회귀 0" 판정 방법 없음.** `unittest` 요약이 skip 을 `Ran N` 에 포함 → 기존 통과가 skip 으로 바뀌어도 요약행이 같다. **기준선 skip 은 0건**(내 실측) (§2③) | `-v` 출력의 **skip 된 테스트 이름 목록**을 PR 에. 수가 아니라 이름 |
| **N-4** | `d-02` AC-12 · DoD | **스크린샷 수단이 §9.4 차단에 없다.** 실측: `ms-playwright` 캐시 없음 · `chromium` 바이너리 없음 · AI_ROI `node_modules` 없음. (Chrome·Safari.app 은 있으므로 **수동 촬영은 가능**) | §9.4 에 *"헤드리스 자동화 없음. 수동 촬영 경로를 정하거나 `BLOCKED`"* 추가. §7.2 가 C-2·C-11 에 보인 정직함을 여기에도 |
| **N-5** | `m-04` §4.5(329행) ↔ AC-3b | **`developer_context` 와 AC 가 다른 지시를 한다** — §4.5 는 *"`PRECONDITION_MISSING` **또는** 모집단을 `basis.population` 에 정확히 적는다"*, AC-3b 는 전자로 고정. `repurchase_rate` 는 `signup_date` 없이 계산 가능하다 (§2④) | "또는" 분기 제거 + 셋 중 하나 확정. **⑴(정확한 `basis.population` + `ok`)을 권함** |
| **N-6** | `d-01` §7.2 C-11 | *"자동화 어려움"* 으로 남겼으나 **구조 제약으로 바꾸면 자동 검증 가능하다** — 글리프 리터럴을 `StateChip` 한 곳에 수렴시키면 *"글리프가 `StateChip.tsx` 밖에 0건"* grep 명제가 된다 (§2①) | C-11 을 grep 명제로 재작성. C-2 도 CSS 토큰 grep 으로 부분 자동화 가능 |
| **N-7** | `readiness-report-kr.md` §1.1 | **charter §3.1① 이 한 번도 언급되지 않는다** (grep: `제거 축` 0건 · `ECOM-E7` 0건). W1 이 덮지만 커버리지 원장에서 공백으로 보인다 (§3) | §1.1 표 아래 한 줄 |

## 참고 — `yaml_available()` 소유 이중 기재 (기록만, 조치 불요로 본다)

`m-03` T4 *"`yaml_available()` guarded 함수"* 와 `m-05` T4 *"`config_loader.yaml_available()` 추가 (M-03 이 만든 파일)"* · `file_list` *"`config_loader.py` **수정** — `yaml_available()`"* 가 같은 함수를 양쪽에 적었다.
**Phase 순서(m-03 = 2, m-05 = 2')상 m-03 이 먼저 만들고 m-05 가 규약화하는 것으로 읽히며, 둘 다 Phillip 소유이므로 실제 충돌은 없다.** `check_ownership.py` 도 PASS 다. **다만 m-03 이 최상위 `import yaml` 로 만들면 m-03 머지 시점에 `isolation.yml` 이 빨강이 된다** — §2③ 에서 재현한 그 실패다. m-03 T4 에 *"`sink.py:52-56` 과 같은 `try/except ImportError` 형태로 만든다"* 한 줄이 있으면 이 seam 이 닫힌다. (m-03 §4.10 이 이미 *"`sink.py parquet_available()` → `config_loader.yaml_available()` 도 같게"* 를 적었으므로 **T4 로 올리기만 하면 된다.**)

---

# 6. 리드 판정 3건에 대한 이견 — **`Q-3` 판정에 부분 이견 있음**

| 판정 | 내 검토 | 이견 |
|---|---|---|
| **`B-11`** `REJECTED_EVENTS` + 우선순위 → 화면 우회 금지, W5 에서 계약 수정 | `index.schema.json` `headline_code` enum **7종** 확인 (`REJECTED_EVENTS` 없음). m-06 AC-4b·DoD 가 계약 수정으로 처리, d-02 §4.8 이 *"화면이 순위를 정하지 않는다"* 로 받음 | **이견 없음.** 화면에 우회 코드를 두는 것보다 계약을 고치는 쪽이 옳다 |
| **`G-8`** 파생 상태 → 게시 시점 계산(`derived: true`) | m-06 §4.13·DoD · m-08 AC-7 · d-02 §4.5 C-2 `유도값` 칩까지 3스토리가 일관 | **이견 없음** |
| **`Q-2` 묶음(계약 결함 3건) → 스키마로 막기** | 아래 | ⚠️ **부분 이견** |

## `Q-3` 에 대한 리드 정정 — **정정 자체는 옳다. 그런데 원인을 못 짚었다**

리드가 *"`Q-3` 은 JSON Schema draft 2020-12 로 교차 필드 비교를 표현할 수 없으니 스키마 제약 대신 3층으로 간다"* 로 정정했고 Matthew 가 반박해 그렇게 됐다.

**기술 판단은 옳다.** draft 2020-12 에 `reported_checks` 를 `checks` 의 길이와 비교할 키워드가 없다. `minItems`/`maxItems`/`const`/`enum` 은 전부 자기 자리만 본다. `$data` 는 Ajv 확장이다. **`unevaluatedItems`·`contains`+`minContains` 로도 "다른 필드의 값과 같은 개수"는 표현할 수 없다.** 3층(값을 `len(checks)` 로 산출 / 게시 자기검증 fail closed / 테스트 고정) 배치도 적절하고, 특히 **"상수를 두 번 적지 않는 것이 가장 싼 방어"** 는 정확한 원칙이다.

**이견은 진단의 깊이다.**

`Q-3` 은 *"`reported_checks` 가 `len(checks)` 와 다르다"* 로 정의됐고, 조치는 *"`reported_checks = len(checks)` 로 산출"* 이다. **이 조치를 그대로 하면 `commerce-connected` 는 `reported_checks: 7` 이 되고 — 여전히 검사 11종이 사라진 상태다.** (CR-2)

**즉 `Q-3` 은 증상이고 `Q-4`(목록 절단)가 원인이다.** `6 ≠ 7` 이라는 눈에 띄는 불일치가 `18 → 7` 이라는 큰 소실을 가렸다. `reported_checks: 6` 은 아마 **`DQ-17`(`blocked`, 환경 제약)을 세지 않은 결과**로 보이는데, 그렇다면 그 숫자에는 *"실제로 다룬 검사는 6종"* 이라는 의도가 담겨 있었고 — **진짜 문제는 그 6/7 이 18 이어야 했다는 것이다.**

**→ 리드께: `Q-3` 의 3층 배치는 유지하되, 그 등식의 우변을 `len(checks)` 로 두는 것과 **별개로** `len(checks) == 18` 을 같은 3층에 넣어야 합니다.** 지금 계약에는 검사 총수를 고정하는 장치가 어디에도 없습니다 (`checks: minItems 1` 뿐). **`reported_checks == len(checks)` 는 "보고한 수와 실린 수가 같다"만 보장하고, "실려야 할 것이 다 실렸다"는 보장하지 않습니다.** 두 명제는 다릅니다.

## `Q-2` 스키마 제약 초안에 대한 이견 — **`vacuous` 가 빠졌다**

§2② 에 적었다. 제안된 `allOf` 두 벌(`blocked`·`not_run`)은 옳지만 **`vacuous` + `reason_code: "NOT_RUN"`** 조합(픽스처 7행 전부)이 그대로 통과한다. `Q-2` 와 **정확히 같은 종류의 결함**이고, 같은 그물로 잡아야 한다.

---

# 7. 이 리뷰의 한계 — 통과로 적지 않는다

| # | 한계 |
|---|---|
| **ML-1** | **`jsonschema` 미설치.** 픽스처 2벌이 스키마를 실제로 통과하는지 **검증하지 못했다.** 내가 한 것은 JSON 파싱·필드 계수·스키마 정독이고, **`allOf` 조건부 규칙의 실제 평가는 실행하지 않았다.** CR-1·CR-2 의 근거는 *스키마 본문의 규칙*과 *픽스처의 값*을 사람이 대조한 것이다 |
| **ML-2** | **`dashboard/` 가 없다.** d-01·d-02 의 화면 명제 중 실제로 확인한 것은 **0건**이다. CR-1 은 **문서 간 논리 대조**이지 렌더 결과 관찰이 아니다 |
| **ML-3** | **스토리를 구현해 보지 않았다.** 11개 스토리 어느 것도 실행 가능성을 W5 전에 증명할 수 없다 |
| **ML-4** | **`source_hash` 12건 중 0건을 재계산했다** (N-1 — 대상 목록 없음). **스토리가 낡았는지 판정하지 못했다.** 내가 읽은 상류 문서가 스토리 작성 시점과 같은지 확인할 수단이 없다 |
| **ML-5** | 격리 CI 를 실행하지 못했다 (GitHub Actions). `isolation.yml` 은 **정독**했다 — 의존성 설치 단계 없음·`python -m unittest discover -s tests -t . -v` 확인 |
| **ML-6** | **문서 총량 약 450KB 중 §3 AC · §7 테스트 · §9 DoD 를 전수로, §4 `developer_context` 를 선택적으로 읽었다.** §4 에 남은 결함이 있을 수 있다 — **특히 Thomas 영역(코드 품질·아키텍처)은 보지 않았다** |
| **ML-7** | `Ecommerce_Service` 에서 `verify.mjs` 를 실행했다. **`git status` 로 변경 0건을 확인**했으나(`mkdtemp` 사용), 실행 자체가 읽기 전용 범위의 경계에 있다 |

---

# 8. 최종 판정

**CONCERNS** — critical 2건 수정 후 W5 진입.

**FAIL 이 아닌 이유:** 두 critical 모두 **계약·픽스처·스토리 문서의 국소 수정**으로 닫힌다. 설계를 되돌릴 필요가 없고, `charter §3.1` 커버리지에 실질 공백도 없다. 그리고 이 스토리 세트는 **"완료 거짓말" 방어에서 내가 예상한 것보다 훨씬 강했다** — 없는 명령을 AC 에 넣은 자리가 11개 스토리에서 **0건**이고, `BLOCKED` 표기가 일관되게 정직하다.

**critical 2건이 W5 를 잘못된 결과로 이끄는 이유는 같다:** 둘 다 **`ADR-0010`(공허한 통과 차단)이 만든 새 층과 그것을 소비하는 층 사이의 이음매**에 있다. 계약은 `pass` → `vacuous` 로 값을 바꿔 첫째 층을 막았는데, **화면(CR-1)과 픽스처(CR-2)가 옛 세계에 남아 있다.** 고치지 않으면 `ADR-0010` 이 막으려던 것이 **막힌 자리 바로 옆으로 돌아온다.**

| 순위 | 항목 | 반영처 |
|---|---|---|
| 1 | **CR-2** — `Q-4` 를 결함표에 추가 · `len(checks)==18` 을 `Q-3` 과 같은 3층에 · m-06 T5 에 대조 제외 한 줄 | `story-m-07` §7.2·AC-8b · `story-m-06` T5 |
| 2 | **CR-1** — 검사 행 상태 5종 매핑표 신설 · `vacuous` 시각 배정 · AC-7 조건을 `status==="vacuous"` 로 | `story-d-02` §4.2·AC-6·AC-7·§4.5 C-2·§4.6 V5 |
| 3 | **N-3** — `A7-4` 판정을 skip 된 **테스트 이름 목록** 대조로 | `story-m-05` AC-5 |
| 4 | **§2② `Q-2` 보강** — `vacuous`↔`reason_code` 제약 (⑵ 권장: `vacuous` 에 `reason_code` 금지) | `story-m-07` §7.2 → `story-m-06` T1 |
| 5 | N-1 · N-2 · N-4 · N-5 · N-6 · N-7 | 각 스토리 |

---

**Matthias** · Role 15 · QA Validator / SDET Lead
**"측정하지 않은 것은 적지 않았다."**
