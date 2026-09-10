# 이슈 대비 코드 실측 대조 — T1.4 · T1.5

**작성** 2026-09-10 · John (W1 Reverse) · **대상** `72offsuit/AI_ROI` 이슈 `#42`~`#49`, 커밋 `1140912`

---

## 0. 결론 먼저

- **`#43`(M-1)·`#44`(M-2)가 OPEN인 것은 실수가 아니다.** 두 이슈 모두 작성자가 "이 이슈를 닫지 않는 이유"를 코멘트로 명시했고, 내가 코드로 대조한 결과 **미충족 항목이 실제로 남아 있다.**
- 다만 이슈 코멘트가 밝힌 미충족분 **외에** 내가 추가로 찾은 미충족·결함이 있다 (§1.3, §2.3).
- `AGENTS.md`의 "프로젝트 현황(2026-09-10)"은 **실측과 어긋난다.** 보고만 하고 고치지 않았다(W6 Timothy 담당).

## 0.1 이슈 지형

| 이슈 | 제목 | 상태 | 담당 | 라벨 |
|---|---|---|---|---|
| `#42` | [범위 M] 측정 계층 (에픽) | OPEN | 없음 | kind/docs, scope/M-measurement |
| `#43` | [M-1] 이벤트 스키마·식별자 규칙 확정 | **OPEN** | 없음 | kind/decision |
| `#44` | [M-2] Event Sink 구현 | **OPEN** | 없음 | kind/dev |
| `#45` | [M-3] 서비스 UI ↔ 시뮬레이터 공통 기록 계약 | OPEN | 없음 | kind/docs |
| `#46` | [M-4] KPI·지표 정의 모듈 | OPEN | 없음 | kind/decision |
| `#47` | [M-5] 경제 규칙 + economic_config.yaml | OPEN | 없음 | kind/decision |
| `#48` | [M-6] 데이터 품질 검증 모듈 | OPEN | 없음 | kind/dev |
| `#49` | [M-7] GATE 1 Freeze 체크리스트 | OPEN | 없음 | kind/docs |

**`#4`~`#35`(범위 A~D)는 전부 CLOSED / `NOT_PLANNED`.** 구현되어서 닫힌 것이 아니라 **플로우 변경으로 재구성**되었다.
근거 — `#27` 종료 코멘트: *"PRD v2.2 §10에서 구축 순서가 `서비스 → 측정 계층 → 시뮬레이터 → Rule-based → AI`로 확정 … 시뮬레이터·의사결정 시스템 태스크는 이후 재작성합니다."*

> **주의: 이 저장소의 CLOSED 이슈는 "완료"를 뜻하지 않는다.** 이후 웨이브에서 진척 판정에 쓰지 말 것.

---

## 1. T1.4-a — `#43` (M-1) 요구 대비 코드 실측

### 1.1 이슈가 밝힌 미종결 사유 (원문 요약)

`#43` 코멘트(작성자 Danto7632, PR #50 병합 후):
1. **Observable 16개 "샘플 쿼리 확인"이 남았다** — 데이터가 없어 쿼리를 돌릴 수 없었고 매핑 표+테스트 3종으로 대체.
2. **근거 문서에 규정이 없어 임의로 정한 값이 있다** — `page_type` 8종 / 식별자 형식 / 세션 만료 30분. GATE 1 Lock 전 확정 필요.

### 1.2 체크리스트 대조 (내가 코드로 확인)

| `#43` 할 일 | 충족 | 근거 |
|---|---|---|
| `schema.py`에 단일 소스 정의 (dataclass **또는 pydantic + pyarrow schema**) | **부분** | dataclass는 됨(`schema.py:93-137`). **pyarrow schema 변환은 미구현** — `schema.py:14`가 "[M-2]에서 어댑터로 추가한다"고 넘겼으나 `sink.py`에도 없다(`sink.py:297-302`가 즉석 `pa.table` 생성) |
| DATA-003 전 컬럼 22종 | ✅ | `schema.py:101-137`, `test_schema.py:61-72`가 정확히 22종으로 고정 |
| `event_type` Enum 16종 | ✅ | `schema.py:41-63`, `test_schema.py:45-47` |
| 이벤트별 필수/Nullable 매트릭스 **문서화** | ✅ | `schema.py:176-245` → `docs/event_schema.md:56-73` (16×15). 재생성 diff 0 확인 |
| 식별자 규칙 확정 (`event_id`·`session_id` 생성·만료·`customer_id`) | **부분** | 정규식 9종 존재(`schema.py:309-319`)·세션 규칙 문서화(`schema.py:320-321`). 그러나 **① 값이 임의(이슈 자인) ② `check_identifier()`가 어디서도 호출되지 않아 위반이 저장된다**(`schema.py:324-326`, 실행 확인) |
| 파생 상태 정의 + Feature 금지 표기 | **부분** | 정의·금지 표기 완료(`schema.py:66-79`). 그러나 **`EventType`에 없어 Sink에 기록할 수단이 없다** — PRD §30.2는 "기록은 하되"를 요구 |
| 통과 금지 항목 명시 (Hidden Trait·τ·PO·persona) | ✅ | `schema.py:149-159` 25종, 런타임 거부(`schema.py:285-287`) |
| 타임존 단일화(KST)·timestamp 정밀도 확정 | **부분** | 상수 선언(`schema.py:29-33`). **검사가 없어 UTC `...Z`가 통과하고 파티션 날짜가 하루 어긋난다**(실행 확인) |

### 1.3 완료 조건 대조

| 완료 조건 | 판정 | 근거 |
|---|---|---|
| 스키마만 보고 양쪽이 동일하게 기록 가능 | **부분** | 필드·필수여부는 명확. 그러나 `category`·`page_type` **허용값이 코드에 없다**(`schema.py:111-115`) — 자체 테스트끼리 `"신선식품"`(`test_schema.py:32`)과 `"fresh_food"`(`test_sink.py:35`)로 갈리고 **둘 다 통과한다.** 커머스 구현자가 어느 어휘를 쓸지 알 수 없다 |
| Observable 16개를 **샘플 쿼리로** 확인 | ❌ | 매핑(`schema.py:331-348`)·테스트 3종(`test_schema.py:174-196`)까지. 쿼리 없음. **`#44` 병합으로 데이터 생성이 가능해졌으므로 이제는 실행할 수 있다** |
| `src/measurement/`가 아무것도 import 안 함 | ✅ | `test_isolation.py:86-102` 통과 (46건 전부 OK) |

### 1.4 판정

> **`#43`은 정당하게 OPEN이다.** 미충족: 샘플 쿼리 · pyarrow 스키마 · 식별자/타임존/어휘 강제 · 파생 상태 기록 경로 · 임의값 확정.
> 이 중 **임의값 확정(식별자·`page_type`·세션 만료)은 `#49`(M-7 GATE 1) 의 Lock 대상**이므로 `#43`은 M-7까지 열려 있는 것이 구조상 자연스럽다.

---

## 2. T1.4-b — `#44` (M-2) 요구 대비 코드 실측

### 2.1 이슈가 밝힌 미종결 사유 (원문 요약)

1. **`events` 외 테이블 미구현** — 생성 주체(시뮬레이터·커머스)가 없어 스키마 확정 근거가 없다.
2. **Parquet 경로 미검증** — pyarrow가 없어 실행하지 못함. `BLOCKED`.
3. **처리량은 Sink 비용만** 잰 값이다.

### 2.2 체크리스트 대조

| `#44` 할 일 | 충족 | 근거 |
|---|---|---|
| `write_events(records)` · `write_batch(...)` · `flush()` | **부분** | `write_events`(`sink.py:150`)·`flush`(`sink.py:179`) 있음. **`write_batch()` 없음** |
| Parquet(snappy) 기본, CSV 옵션 | **코드만** | `sink.py:59-69, 297-302`. **로컬·CI 어디서도 실행되지 않음**(`parquet_available() == False` 실행 확인, `isolation.yml:34-35`에 설치 단계 없음) |
| 파티셔닝 (일/월 또는 청크 append) | **부분** | 날짜 파티션+청크(`sink.py:190-197, 163-164`). **동일 root 재기록 시 `part-0000`을 덮어쓴다**(실행 확인) — 독트링(`sink.py:113`)은 append라고 적혀 있다 |
| 테이블별 경로 `data/raw/{events,customers,orders,order_items,products,marketing_actions,assignment}` | ❌ | `sink.py:191` — `events`만 |
| 민감 경로 분리 (`data/hidden/`·`data/ground_truth/`는 쓰지 않음) | ✅ | 참조 자체가 없고 `test_isolation.py:33`이 문자열 등장을 금지 |
| manifest: **버전키 4종** · 행 수 · 생성 시각 · **config 해시** | **부분** | 행 수·생성 시각·sha256 있음(`sink.py:227-245`). **버전키 4종의 값 없음**(충족률만), **config 해시 없음** |
| 성능 측정 20,000명×30일 기록 | ✅ | `scripts/bench_sink.py`. **내가 재현: 4,200,000건 / 64.7초 / 112.6MB / 64,899건·초** (이슈 기록 63.8초와 일치) |

### 2.3 완료 조건 대조

| 완료 조건 | 판정 | 근거 |
|---|---|---|
| 시뮬레이터가 `sink.write_events()`만으로 기록 가능 | ✅ | `test_sink.py:82-93` 왕복 통과 |
| 동일 seed 재실행 시 `events.parquet` SHA-256 일치 (NFR-001) | **부분** | 해시 재현성 테스트는 있으나(`test_sink.py:216-225`) **jsonl.gz 기준**이다. **`events.parquet`은 만들어본 적이 없다** → 완료 조건 문면 그대로는 미검증 |

### 2.4 이슈가 언급하지 않은 결함 (내가 추가로 발견)

| 결함 | 근거 | 영향 |
|---|---|---|
| **`strict=False`가 크래시** | `sink.py:158-160, 169`. 실행: `ValueError: 'teleport' is not a valid EventType`, `KeyError: 'event_type'` | 커머스 실측분처럼 **필드가 덜 찬 소스를 관용 모드로 받으려는 순간 터진다.** MEA-003의 취지와 정면 충돌 |
| **동일 root 재기록 시 덮어쓰기** | `sink.py:146, 193-195`. 실행: 2건 저장 후 3건 저장 → 총 3건(5건 아님) | `data/raw`에 두 번 쓰면 앞 데이터 소실 |
| **타임존 미강제** | `schema.py:29-33` 선언만, `sink.py:271-279` 파싱만. 실행: UTC `23:30Z` → 파티션 `2025-10-01`(KST로는 10-02) | 코호트·리텐션·`purchase_interval` 전부 하루 밀림 |
| **manifest `created_at`이 UTC** | `sink.py:229` vs `schema.py:29-30` | 자기 규약 위반(경미) |
| **출처가 저장 레코드·파티션에 남지 않음** | `sink.py:282-294` | **W5-C 대시보드**가 출처별 표시를 하려면 전량 재분류 필요 (charter §3.1③ 조건) |

### 2.5 판정

> **`#44`도 정당하게 OPEN이다.** 미충족: 추가 테이블 · Parquet 검증(`BLOCKED`) · manifest 재현 메타 · `write_batch`.
> **여기에 더해 §2.4의 결함 3건(덮어쓰기·`strict=False` 크래시·타임존)은 이슈에도 없고 테스트에도 없다.** 조용히 고치지 말고 별도로 기록해야 한다(charter 절대제약 5).

---

## 3. `#45`~`#49` 미착수 확인

| 이슈 | 산출물 요구 | 존재 여부 |
|---|---|---|
| `#45` M-3 | `docs/measurement_contract.md` | ❌ 없음 |
| `#46` M-4 | `src/measurement/kpi.py` | ❌ 없음 |
| `#47` M-5 | `src/measurement/economics.py`, `config/economic_config.yaml` | ❌ 없음 (`config/` 디렉터리 자체 없음) |
| `#48` M-6 | `src/measurement/validate.py`, `results/data_quality_report.json` | ❌ 없음 |
| `#49` M-7 | `docs/gate1_checklist.md` | ❌ 없음 |

**`#45`(M-3)가 병목이다.** 이슈 본문이 상품 참조 계약으로 `product_id, category, selling_price, unit_cost`를 요구하는데,
`Ecommerce_Service`에 `category`·`unit_cost`가 **없다**(`Ecommerce_Service/src/lib/server/commerce/schema.ts:9-16`).
즉 **M-3은 커머스 `#25`가 풀리기 전에는 "커머스가 아직 못 주는 것"까지만 쓸 수 있다.** → `ecommerce-gap.md` 참조.

또한 `#44` 코멘트가 "`#45`는 `Ecommerce_Service` `#28`의 선행 조건"이라고 명시했다. 커머스 이벤트 기록은 M-3 없이는 시작할 수 없다.

---

## 4. Q4 — `#43`·`#44`를 닫아야 하는가 (사용자 판정 필요)

**AGENTS.md L1 권한상 에이전트가 Issue를 닫지 않는다.** 판단 재료만 제시한다.

| 선택지 | 근거 | 대가 |
|---|---|---|
| **그대로 둔다** (권장) | 미충족 항목이 실재하고 두 이슈 모두 그 사유를 문서화했다. 특히 `#43`의 임의값은 `#49` GATE 1 Lock 대상 | 이슈 보드에 "머지됐는데 열려 있는" 항목이 남아 진척이 흐릿해 보인다 |
| 닫고 후속 이슈로 분리 | 보드가 깔끔해지고 남은 일이 명시적 태스크가 된다 | 후속 이슈 4~5건을 새로 만들어야 하고, 그 자체가 L1 승인 사항 |

**어느 쪽이든 §2.4의 결함 3건은 별도 기록이 필요하다** — 현재 어느 이슈에도 없다. 초안: `issue-drafts/AIROI-D1-sink-defects.md`.

---

## 5. T1.5 — `AGENTS.md` 실측 어긋남 (보고만 · 수정 금지)

### 5.1 어긋난 문단

`AGENTS.md` "프로젝트 현황 (2026-09-10)":

| 문장 | 실측 | 판정 |
|---|---|---|
| "`src/`에 파트 디렉터리와 지침 파일만 있고 **구현 코드는 아직 없다.**" | `src/measurement/schema.py` 350줄 + `sink.py` 321줄 (PR #50·#51 머지, 커밋 `105e83c`·`d1ca26f`) | **틀림** |
| "실행 가능한 검증 명령도 `tests.test_isolation` 하나뿐" | `tests.test_schema`(20) · `tests.test_sink`(20) 추가 → **총 46건**. CI(`isolation.yml:41`)도 `discover -s tests`를 돌린다 | **틀림** |
| "의존성 매니페스트는 아직 없다" | `requirements*.txt`·`pyproject.toml` 부재 확인 | 맞음 |
| "CI는 `.github/workflows/isolation.yml` 하나뿐" | 확인 | 맞음 |
| "lint·build·타입 검사는 미정의" | 확인 | 맞음 |

### 5.2 부수 지적

- `AGENTS.md` "검증" 절이 `python3 -m unittest tests.test_isolation -v`만 제시한다. **46건을 돌리는 명령이 문서에 없다.** charter §3.1④와 CI는 `discover -s tests`를 기준선으로 삼는다.
- `AGENTS.md` "먼저 읽을 것" 2번이 `docs/GIT_WORKFLOW.md`를 "아직 존재하지 않는다"고 적고 있다 — **사실이다**(부재 확인). W6 Timothy 작업.
- `README.md`가 1줄(`# AI_ROI`)이다.

### 5.3 조치

**수정하지 않았다.** `task-graph.md` §4 봉인 파일 표에 따라 `AGENTS.md`는 **W6 Timothy 단독 소유**다.
→ W6 인계: 현황 문단을 (a) 측정 계층 구현 존재 (b) 테스트 46건 (c) 검증 명령 `discover -s tests` 로 갱신.

---

## 6. BLOCKED

| 항목 | 사유 |
|---|---|
| `events.parquet` SHA-256 재현성 (`#44` 완료 조건) | pyarrow 미설치 — 설치는 환경 변경이라 금지 |
| Observable 16개 샘플 쿼리 (`#43` 완료 조건) | 실행은 가능하나 **쿼리 자체가 저장소에 없다.** 내가 새로 작성하면 제품 코드 추가가 되어 W1 권한 밖 |
| `#43`·`#44` close 여부 | Issue close는 개별 승인 사항 (AGENTS.md) — 사용자 판정 |
