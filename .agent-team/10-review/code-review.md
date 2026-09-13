# 코드 리뷰 — W5 측정 계층 + GA형 관측 대시보드 (PR #57)

**작성** Thomas (Role 12 · 코드 리뷰어) · 2026-09-14 · 사이클 C1 · 브랜치 `feat/measurement-layer-and-dashboard`
**대상** `src/measurement/**`(11파일 · 7,373줄) · `dashboard/src/**`(24파일 · 4,158줄) · `tests/**`(13파일) · `docs/contracts/**`(8 JSON Schema) · `config/**` · `.github/workflows/**`
**방법** 6개 영역(measurement 핵심/계산/게시·계약·freeze, JSON Schema, 대시보드, 테스트+CI)을 병렬로 전문 정독 + 직접 실행/grep 재현. 팀 리드가 그 중 4건(F1 원인 분석, Python 3.10 확정, 카탈로그 미검증 발견, doctest 18개 전수 실행)을 추가로 실행 검증해 전달했고, 본 문서 작성자가 가장 중대한 주장(FREEZE_MISMATCH 배선·ConfigError 미임포트·죽은 카탈로그 지표)을 별도로 grep 재확인했다.
**리뷰 범위 밖(제품 코드 미수정, 읽기만)**: `Ecommerce_Service/`·`Plan/` 접근 안 함. 소유 경로(`.agent-team/10-review/**`) 밖 파일 변경 0건.

---

## 0. 요약

- 실행 검증: `python3 -m unittest discover -s tests` — **의존성 없이 Ran 407 · OK (skipped=67)**, **의존성 설치 후(venv) Ran 407 · OK (skipped=3)**. `backend.md`·`wave-log.md`가 주장한 숫자와 **정확히 일치**한다.
- GATE 1 부분 봉인 `canonical_files` 4종의 SHA-256을 직접 재계산해 `config/gate1_lock.yaml` 기록값과 **전건 일치**를 확인했다. 봉인 기록 자체는 정직하다.
- "세 번째 값" 설계(vacuous·계산 불가·`met: null`·`verification: not_run`)는 스키마·Python·TypeScript 세 층에서 이중·삼중으로 강제되고 있고, 핵심 불변식(basis 필수/금지, `denominator==0`→`ok` 불가, `vacuous` 3중 강제, 계층별 `combined` 금지, 실험 계층 분리)은 실제 `jsonschema` 라이브러리로 반례를 만들어 검증한 결과 **전부 정상 작동**한다.
- 대시보드의 `?? 0`·`\|\| 0`·`Number(`·`.toFixed(`·`.toLocaleString(`·`filter(...>0)` 함정은 실행 코드 기준 **0건** — Andrew의 주장과 일치.
- 그러나 **같은 원칙(결손을 조용히 0으로 채우지 않는다)이 예외적으로 깨진 자리를 하나 찾았다** — `kpi.py`의 계층 0(수집 건전성) 지표 다수가 검증되지 않은 `manifest` 입력을 `.get(key, 0) or 0`으로 읽는다(Finding 4). 이것이 이번 리뷰에서 가장 중요한 발견이다.
- **blocking 등급 결함은 발견하지 못했다** — 발견한 모든 결함이 (a) 현재 데이터를 틀리게 만들지 않거나(스키마가 fail-closed로 잡음), (b) 아직 도달하지 않는 코드 경로(GATE 1 미잠금·단일 프로세스 실행)에 있다. 다만 major 10건 중 다수가 **GATE 2 이전에는 반드시 닫아야 하는 성격**이다. M4·M5는 blocking 후보로 별도 검토했다 — 판정과 근거는 각 항목 하단 및 `blocking-issues.md`에 있다.

| 심각도 | 건수 |
|---|---|
| blocking | 0 |
| major | 10 |
| minor | 10 |

---

## 0.1 관통 패턴 — "주장이 있는데 그것을 대조하는 장치가 없다"

이번 리뷰의 major 10건 중 4건(M1·M7·M9·M10)은 서로 다른 파일·다른 계층에 있지만 **같은 모양의 결함**이다: 이 코드베이스는 "값을 계약으로 강제하는 것"은 매우 잘하지만, **그 계약·선언·설정 자체가 실제와 일치하는지 대조하는 상위 장치가 곳곳에 비어 있다.**

| 자리 | 무엇을 선언/주장하는가 | 무엇이 빠졌는가 |
|---|---|---|
| **M1** `manifest.json` | Sink가 "이만큼 수집했다"고 기록 | 그 기록 자체를 검증하는 계약(`manifest.schema.json`)이 없다 — 8종 산출물은 전부 계약이 있는데 유일한 입력만 없다 |
| **M7** `METRIC_SPECS`의 `"computable"` | 카탈로그가 "이 지표는 계산 가능하다"고 선언 | 그 선언이 실제로 구현·게시됐는지 대조하는 테스트가 없다 — 3종이 선언만 있고 실체가 없다 |
| **M9** `tests-with-deps.yml`의 skip count | 주석이 "이 숫자가 회귀의 증거"라고 선언 | 그 숫자에 임계값 비교가 없다 — 사람이 로그를 읽어야만 의미가 생긴다 |
| **M10** doctest 18개 | 함수 docstring이 "이 예제가 이 값을 낸다"고 선언 | 어떤 테스트 러너도 이 예제를 실행하지 않는다 — 실제로 1개가 이미 실패 중이었다(§M10) |

**공통 처방:** 넷 다 "값 자체를 다시 계산"하는 수정이 아니라 **"선언 vs 실제"를 자동으로 대조하는 검사 하나씩을 추가**하면 닫힌다 — `manifest.schema.json` 신설, `METRIC_SPECS` ↔ 게시물 대조 테스트, skip-count 임계값 비교, doctest를 `unittest discover`에 편입. 이 프로젝트가 스스로 만든 "세 번째 값" 규율(vacuous·`met:null`·`not_run`)이 값 계층에서는 철저한데, **선언 계층에서는 아직 같은 철저함이 적용되지 않았다**는 것이 이번 리뷰의 결론 중 하나다.

---

## A. Major Findings

### M1 — `manifest` 입력이 검증되지 않아 결손이 조용히 0으로 치환된다 ★ 가장 중요

**파일** (증상) `src/measurement/kpi.py:205,216,224,237-238,295,301,337` · (원인) `src/measurement/publish.py:1467`(`_read_manifest()`) · `src/measurement/sink.py:266`(비원자적 `write_text()`)
**심각도** major

**요지:** 이 프로젝트가 게시하는 8종 산출물은 전부 JSON Schema로 자기검증되지만(`contracts.py`가 fail-closed로 막는다), 모든 지표가 파생되는 **유일한 입력**인 `sink.py`가 쓰는 `manifest.json`에는 검증 계약이 없다(`manifest.schema.json` 부재). `publish._read_manifest()`는 `json.loads()` 결과를 아무 검사 없이 그대로 돌려주고, `kpi.py`의 계층 0 지표 함수들이 그 결과를 `manifest.get("rows", 0) or 0` 형태로 읽는다. `or 0`은 키 누락뿐 아니라 **명시적 `null`까지 0으로 만든다** — `exceptions.md` X-1·charter 절대제약 6이 이름까지 들어 금지한 패턴이다.

**재현 (팀 리드 실행, python3.12):**

| 입력 상태 | 산출 |
|---|---|
| ① manifest 아예 없음 | `SINK_EMPTY` · 계산 불가 16종 — **정직** |
| ② manifest는 있으나 `rows` 키 없음 | `SINK_EMPTY` · 계산 불가 **0종** — ❌ |
| ③ `rows: null`(명시적 "모름") | `SINK_EMPTY` · 계산 불가 **0종** — ❌ |

**비대칭이 증거다 — 더 망가진 입력이 더 자신 있는 출력을 낸다.** ③이 특히 날카롭다: manifest가 `null`로 "모른다"를 명시했는데 파이프라인이 `ok, 0`으로 바꾼다.

**왜 8곳을 개별로 고치는 것으로 부족한가:** `.get(key, 0)`을 `.get(key)` + None 체크로 바꿔도 `_read_manifest()`가 여전히 임의의 dict를 내보낸다. `field_coverage`·`missing_fields`·`unavailable_metrics`·`event_type_counts`도 같은 `or {}`/`or []` 패턴으로 조용히 비워진다 — 예: `manifest.get("unavailable_metrics") or []`가 케이스 ②③에서 계산 불가 0종을 만드는 직접 원인이다. **입력에 계약을 주는 것이 근본 수정이다.**

**이것이 정상 운영에서 도달 가능한 이유:** `sink.py:266`이 `manifest.json`을 원자적 쓰기(tmp + `os.replace`)가 아니라 `write_text()`로 직접 쓴다. 중단된 실행(크래시·디스크 풀·SIGKILL)이 잘린/부분 manifest를 남기면 케이스 ②가 **손편집 없이 정상 운영 중 발생**한다.

**오탐이 아닌 근거 — 국소 누락이지 설계 오해가 아니다:** 같은 모듈의 `economics.py:282`(config에 없는 처치를 0원으로 읽지 않는다는 주석)와 `rejection_rate()`(분모 가드 정상)는 정확히 이 규율을 지킨다. 즉 설계는 알고 있었고 일부 자리에서만 놓쳤다 — 고칠 수 있다.

**영향:** `SINK_EMPTY` 판정은 `index.verdict`의 핵심 입력이며, 계층 0 지표는 대시보드 `/ingestion` 첫 화면에 직접 노출된다.

**권고(선택지 — 수정 권한은 Phillip 소유 경로라 리뷰어가 임의로 못 함, 판단은 사용자에게):**
1. `manifest.schema.json`을 신설해 `_read_manifest()`가 로드 직후 검증하도록 한다(다른 8종 산출물과 동일한 fail-closed 원칙 적용).
2. `kpi.py`의 `.get(key, 0) or 0`·`.get(key) or {}`·`.get(key) or []` 패턴 전체(8곳 이상)를 `key not in manifest` 또는 `manifest[key] is None`을 별도로 판별해 `unavailable`을 반환하도록 고친다.
3. `sink.py:266`의 manifest 쓰기를 다른 산출물과 동일하게 원자적 쓰기(tmp + `os.replace`)로 바꿔 부분 쓰기로 인한 잘린 manifest 자체를 없앤다.

---

### M2 — `field_fill_rate`에 분모 0 가드가 빠져 있다

**파일** `src/measurement/kpi.py:309-340`(`field_fill_rate`)
**심각도** major

**요지:** 이 파일에서 비율을 계산하는 함수 중 `field_fill_rate`만 유일하게 `denominator == 0` 사전 검사 없이 무조건 `MetricValue.ok(...)`를 반환한다. 같은 파일의 `rejection_rate`·`campaign_share`·`churn_rate` 등은 전부 `if denom == 0: return unavailable(...)` 가드를 먼저 둔다.

**failure_scenario:** M1의 manifest 결손과 결합하면 `denominator=0`인 `ok` 레코드가 만들어진다. 계약(`basis.denominator == 0` → `status: ok` 불가)이 이를 거부하므로 잘못된 숫자가 화면에 뜨지는 않지만, `contracts.py`의 fail-closed 정책에 따라 **`field_coverage_report` 산출물 전체가 게시되지 않는다** — "일부 필드가 계산 불가"로 표시되는 대신 `/coverage` 화면 전체가 증발하는 더 나쁜 실패 모드가 된다.

**권고:** 다른 비율 함수와 동일하게 `denominator == 0`을 함수 내부에서 먼저 검사해 `unavailable`을 반환하도록 통일한다.

---

### M3 — 파이썬 3.10 지원 선언과 실제 동작이 어긋난다 (`datetime.fromisoformat`의 `Z` 접미사)

**파일** `src/measurement/sink.py:394`(재현 확정) · 동일 패턴 `validate.py:357`·`contracts.py:144`·`kpi.py:121`·`publish.py:452,1497,1575`(총 7곳) · 선언 근거 `Plan/AI_Customer_Retention_ROI_SRS_v2.0.md:9`(`Target Runtime: Python 3.10+`)
**심각도** major

**요지:** `sink.py:394`의 `datetime.fromisoformat(str(timestamp))`는 전처리 없이 `Z` 접미사를 받는다. CPython의 `datetime.fromisoformat()`은 **3.11부터** `Z` 접미사를 포함한 임의 ISO 8601 형식을 받도록 확장됐다(bpo-35829) — **3.10에서는 `ValueError`다.** 이 입력은 우연이 아니라 문서화된 지원 사례다: 같은 파일 `sink.py:382` 독스트링이 `"2025-10-01T23:30:00.000Z"` → KST 정규화를 명시하고, `schema.py:423`가 이 값을 "통과 — Sink가 KST로 정규화"로 선언하며, `tests/test_sink.py:168,180`·`tests/test_schema.py:187`·`tests/test_quality_checks.py:303`가 이 값을 실사용한다.

**failure_scenario:** UTC로 기록하는 실제 커머스 이벤트(`"...Z"` 형식)를 Python 3.10 환경에서 수집하면 `sink.py:395-397`의 `except ValueError`가 이를 잡아 "timestamp를 해석할 수 없다"로 재던진다 — **런타임 비호환이 데이터 오류로 위장된다.** CI는 두 워크플로우 모두 Python 3.12로 고정되어 있어 이 경로가 CI에서 전혀 드러나지 않는다.

**실행 구분 (정직성 규율 준수):**
- **실행 확인함**(3.12.4·3.14.6 환경): `compileall` 통과, 전체 테스트 407 OK, `datetime.UTC`·`tomllib`·`StrEnum`·`Self`·`except*`·`TaskGroup`·`batched`·`file_digest`·`NotRequired`·`LiteralString` 등 3.11+ 전용 API grep 0건 — `Z` 접미사 외 다른 3.10 비호환은 발견되지 않았다.
- **실행하지 않음(BLOCKED)**: 3.10 인터프리터가 로컬에 없어 `ValueError` 자체를 직접 재현하지는 못했다. 이 결함은 CPython 공식 changelog에 근거한 것이며, 리뷰자·팀 리드 누구도 3.10에서 직접 실행하지 않았다는 점을 명시한다.

**해소 경로 (둘 다 C1 범위 밖 — 판단은 사용자에게):**
1. 선언을 좁힌다 — SRS 목표 런타임을 3.12로 수정. `Plan/`은 읽기 전용 서브모듈이라 이슈로만 제기 가능.
2. 코드를 선언에 맞춘다 — 파싱 전 `Z`→`+00:00` 정규화(7곳 모두). 다만 **CI에 3.10 잡이 없어 고쳐도 회귀를 자동으로 못 막는다.**

**권고:** `code-review.md`에 두 경로를 선택지로 남기고 코드·문서 중 어느 쪽을 정본으로 삼을지는 사용자 결정 사항으로 W6에 넘긴다.

---

### M4 — `FREEZE_MISMATCH` 헤드라인 코드가 배선 결함으로 절대 선택되지 않는다

**파일** `src/measurement/publish.py:262`(`choose_headline_code`), `publish.py:1188-1202`(`counts` 딕셔너리 조립부)
**심각도** major (**본 리뷰어가 grep으로 직접 재확인함**)

**요지:** `choose_headline_code()`는 `counts.get("lock_items_pending", 0) and counts.get("freeze_mismatch", 0)`를 검사해 `FREEZE_MISMATCH`를 반환한다(262-263행). 그런데 `build_index()`가 만드는 `counts` 딕셔너리(1190-1201행)는 `quality_violations`·`checks_not_run`·`checks_blocked`·`metrics_unavailable`·`metrics_not_run`·`schema_gaps`·`lock_items_pending`·`rejected_events` 8개 키만 채우고 **`freeze_mismatch` 키를 절대 채우지 않는다.** 저장소 전체에서 `"freeze_mismatch"` 문자열이 값으로 대입되는 곳은 0건이다(직접 grep 재확인 — 유일한 매치는 262행의 읽기 자신, 230행의 enum 목록, 284행의 우선순위 목록, 1254행의 문구 매핑, 그리고 손으로 값을 지어내는 단위 테스트 `tests/test_publish_pipeline.py:175`뿐).

**failure_scenario:** GATE 1이 향후 사이클에서 실제로 잠긴 뒤 `canonical_files`(예: `schema.py`) 중 하나가 수정되면, `freeze.verify()`는 `verification: "mismatch"`를 정확히 계산해 `freeze_status.json`에 담는다. 그러나 `build_index()`가 이 사실을 `counts.freeze_mismatch`로 옮기지 않으므로 `counts.get("freeze_mismatch", 0)`는 항상 0(falsy)이고, `index.schema.json`이 명시한 우선순위(`CONTRACT_VIOLATION > FREEZE_MISMATCH > ...`)에도 불구하고 이 코드는 **절대 선택될 수 없다.** 봉인 파일이 몰래 변경돼도 대시보드 최상단 배너가 그 사실을 드러내지 못하고 다른 코드(QUALITY_VIOLATION·심지어 ALL_CLEAR)로 떨어진다.

**현재 영향:** C1에서 GATE 1은 `overall: partial`이고 `LOCKED` 항목이 0종이므로 이 경로가 오늘 데이터에서 트리거될 수 없다 — 지금 당장 틀린 화면이 나오지는 않는다. 그러나 이 프로젝트의 결론 자체("같은 원칙이 네 층에 구현됐다" — 봉인 대조 `verification: not_run`도 그 중 하나)가 강조하는 **GATE 무결성 배너**가 실제로는 도달 불가능한 죽은 코드라는 점에서, GATE 2 진행 전에는 반드시 닫아야 한다.

**blocking 여부 판정:** **blocking 아님, major 유지.** `freeze.verify()`가 계산하는 `verification: "mismatch"` 자체는 정확하고 `freeze_status.json`에는 제대로 실린다 — 깨진 것은 그 사실을 `index.verdict`(대시보드 최상단 배너)로 옮기는 배선 한 단계뿐이며, `/freeze` 화면(V6)에서는 지금도 정확한 상태를 볼 수 있다. 즉 정보 자체는 어딘가에 존재하고 사라지지 않는다 — 다만 "한눈에 보이는 자리"에 못 온다. 또한 이 경로는 GATE 1이 `LOCKED` 항목을 하나라도 갖기 전에는 물리적으로 트리거될 수 없어(오늘 `LOCKED` 0종), **현재 브랜치의 어떤 실행에서도 잘못된 배너를 낸 적이 없고 낼 수도 없다.** 다음 사이클에서 GATE 1이 실제로 잠기기 전까지 고치면 되므로 이번 PR의 머지를 막을 이유는 아니다 — 단 GATE 2 착수 전 필수 확인 항목으로 이슈화할 것을 권고한다.

**권고:** `build_index()`에서 `freeze.get("verification") == "mismatch"`(또는 `overall == "violated"`)를 `counts["freeze_mismatch"]`로 채운다. 현재 단위 테스트는 `choose_headline_code()`를 격리해서 통과시키므로 이 배선 결함을 잡지 못한다 — `publish()` 전체를 실제 mismatch 상태로 실행해 최종 `index.json`의 `headline_code`를 확인하는 end-to-end 테스트를 추가한다.

---

### M5 — `freeze.py`의 방어 코드가 `ConfigError` 미임포트로 `NameError`를 던진다

**파일** `src/measurement/freeze.py:466`(raise 지점), 30-38행(import 목록)
**심각도** major (**본 리뷰어가 grep으로 직접 재확인함**)

**요지:** `verify()`는 `canonical_files`가 매핑이 아닐 때 `raise ConfigError(...)`를 호출하지만(466행), 이 파일의 import 목록(30-38행)은 `FreezeViolation`만 `src.measurement.errors`에서 가져오고 **`ConfigError`는 어디에서도 import하지 않는다.** 72행 주석에 `ConfigError`라는 단어가 나오지만 그것은 주석일 뿐 import가 아니다.

**failure_scenario:** `config/gate1_lock.yaml`의 `canonical_files`가 손상되어(사람 실수·다른 도구의 부분 쓰기 등) 매핑이 아닌 형태(리스트·문자열 등)가 되면, 이 방어 코드는 의도한 `ConfigError`(NFR-006이 요구하는 "무엇이·왜·해결법" 3요소 메시지) 대신 처리되지 않은 `NameError: name 'ConfigError' is not defined`를 던진다 — `exceptions.md` X-3("실행하지 못함과 위반을 다른 타입으로")과 NFR-006을 동시에 위반한다. `tests/test_freeze.py`에 이 분기를 트리거하는 테스트가 없어 CI가 잡지 못한다.

**blocking 여부 판정:** **blocking 아님, major 유지.** 현재 `config/gate1_lock.yaml`의 `canonical_files`는 정상적인 매핑이고(4/4 해시 일치를 직접 재계산해 확인함), 이 방어 코드는 그 값이 손상됐을 때만 실행된다 — 오늘의 어떤 정상 경로도 이 raise 문에 도달하지 않는다. 즉 지금 이 파일을 실행해도 크래시하지 않는다. 다만 (a) `NameError`가 발생하는 자리가 "방어 코드"라는 점에서 가치가 정확히 방어가 필요한 순간에 사라진다는 역설이 있고, (b) `import` 한 줄 누락이라는 원인의 단순함에 비해 발견이 늦어질수록(예: 실제 운영 중 lock 파일이 손상된 순간) 디버깅 비용이 커진다. **머지를 막을 근거는 없지만, GATE 1이 실제로 잠기는 시점 전에 반드시 고쳐야 한다** — 그 시점부터 `gate1_lock.yaml`은 사람이 참조하고 도구가 다루는 살아있는 파일이 되어 손상 가능성이 실질적으로 올라간다.

**권고:** `from src.measurement.errors import ConfigError, FreezeViolation`로 import를 추가한다. 이 분기를 실제로 트리거하는 테스트(`canonical_files`가 리스트인 손상된 lock 기록으로 `verify()` 호출 → `ConfigError` 발생 확인)를 `test_freeze.py`에 추가한다.

---

### M6 — JSON Schema가 "개수"만 세고 "이름·고유성"은 검증하지 않는다 (3개 산출물)

**파일** `docs/contracts/measurement-publish/v1/ingestion_report.schema.json:89-96`(`by_event_type`) · `field_coverage_report.schema.json:45-49`(`fields`) · `freeze_status.schema.json:102-106`(`items`)
**심각도** major (**jsonschema 4.25.1로 반례 3건 모두 실행 검증함**)

**요지:** 세 스키마 모두 "N종 전부가 존재해야 한다"는 설계 의도를 `minProperties`/`maxProperties`/`minItems`/`maxItems`로만 강제하고, **실제 키 이름/enum 값의 존재와 고유성은 검증하지 않는다.**

| 산출물 | 필드 | 실측 반례 (실행 검증) |
|---|---|---|
| `ingestion_report` | `by_event_type`(16종 요구) | 오타난 키 16개(`not_a_real_type_0`~`15`, 실제 event_type 0개)로 검증 시도 → **통과함** |
| `field_coverage_report` | `fields`(22종 요구) | 존재하지 않는 필드명 22개로 검증 시도 → **통과함** |
| `freeze_status` | `items`(Lock 9종 요구) | 동일 `item: "SERVICE_v1"`을 9번 반복(다른 8종 누락)해도 → **통과함** |

**failure_scenario:** `kpi.py`나 `publish.py`에 리팩터링 버그가 생겨 event_type 하나가 조용히 다른 이름으로 바뀌거나 필드 하나가 누락돼도, 혹은 `freeze.py`의 Lock 항목 생성 로직에 버그가 생겨 실제 Lock 대상(`EVENT_SCHEMA_v1` 등)이 사라지고 다른 항목이 중복돼도, 계약이 이를 잡지 못한다 — 이 프로젝트가 반복적으로 겪은 "검사 대상이 주장보다 좁다" 패턴(`backend.md` §11, 3회 발생 전례)의 계약 계층 버전이다. `freeze_status`가 GATE 1의 정본이라는 점에서 세 건 중 이것이 가장 무겁다.

**권고:** `required`에 실제 이름을 명시한다.
- `ingestion_report`: `required`에 16개 EventType 값 추가(`minProperties`는 유지).
- `field_coverage_report`: `required`에 DATA-003 22개 필드명 추가.
- `freeze_status`: draft 2020-12의 `contains`/`minContains`/`maxContains`로 9개 enum 값 각각에 대해 `{"contains": {"properties": {"item": {"const": "<값>"}}}, "minContains": 1, "maxContains": 1}` 절을 추가한다(이는 교차 필드 비교가 아니라 배열 원소 카운트이므로 JSON Schema로 완전히 표현 가능 — wave-log Q-3의 "스키마로 못 막는다" 정정과는 다른 종류의 제약이다).

---

### M7 — `METRIC_SPECS` 카탈로그가 "computable"로 선언한 지표 중 일부가 구현·계약 어디에도 없다

**파일** `src/measurement/kpi.py:1128-1141`(`METRIC_SPECS` 계층 0 목록), `kpi.py:343`(`missing_field_count` 함수), `kpi.py:378`(`source_event_count` 함수), `docs/contracts/measurement-publish/v1/*.schema.json`(3종 모두 부재 확인)
**심각도** major

**요지:** `METRIC_SPECS`(46종 카탈로그) 중 계층 0(수집 건전성) 3종이 `"computable"`로 선언되어 있으나 실제로는:

| 지표 | 구현 | `publish.py` 호출 | 계약 스키마 |
|---|---|---|---|
| `missing_field_count` | `kpi.py:343` **함수 있음** | **0건**(grep 재확인) | 0개 파일 |
| `source_event_count` | `kpi.py:378` **함수 있음** | **0건**(grep 재확인) | 0개 파일 |
| `rejection_reason_count` | **함수 자체가 없음** | — | 0개 파일 |

**failure_scenario:** layer 0은 Sink만으로 오늘 계산 가능하다고 선언된 계층인데, 이 3종은 "계산 불가"가 될 기회조차 갖지 못하고 게시물에서 완전히 사라진다 — `design-patterns.md`가 명시적으로 금지한 안티패턴 **A-4("계산되지 않는 지표를 목록에서 뺀다 → 화면이 초록이 되고 무엇이 계산 불가인지 사라진다")**와 정확히 같은 모양이다. `missing_field_count`·`source_event_count`는 구현이 멀쩡히 있는데 아무도 부르지 않는 죽은 코드이기도 하다.

**반대 방향 불일치도 있다:** `sleeping_dog_targeting_rate`는 실제로 게시되지만 `METRIC_SPECS` 46종 목록 자체에 없다 — 카탈로그로 "지금 무슨 지표가 있나"를 감사하면 이 지표를 놓친다. 즉 **카탈로그가 정본 노릇을 못 하며 양방향으로 어긋나 있다.**

**같은 계열의 layer 3(ML/uplift) 비일관:** `precision`·`recall`·`f1`·`pehe`·`corr_tau_hat_tau` 5종은 C1 범위 밖(ML 미가동)이라 미구현 자체는 정당하나, 같은 ML 계열 9종(`auuc`·`qini_coefficient` 등)은 `NEEDS_MODEL_OUTPUT` 사유로 정직하게 "계산 불가"로 게시된다. 같은 범주가 두 갈래로 갈리는데 그 선을 가르는 원칙이 문서 어디에도 없다 — 이 부분은 major라기보다 문서 정합 사안으로 별도 확인이 필요하다.

**권고:** ⑴ `missing_field_count`·`source_event_count`·`rejection_reason_count`를 `publish.py`의 게시 파이프라인에 연결하고 대응 계약 스키마 필드를 추가하거나, ⑵ C1에서 정말 필요 없다면 카탈로그에서 제거하거나 `"not_yet_wired"` 같은 별도 상태로 표시해 "계산 불가"가 될 기회를 준다. ⑶ `sleeping_dog_targeting_rate`를 카탈로그에 추가한다. ⑷ 테스트 가능한 불변식으로 고정: "`METRIC_SPECS`에서 `computable`로 선언된 지표는 구현이 있어야 하고 어떤 게시물의 계약 스키마에 자리가 있어야 한다"를 검증하는 테스트를 추가해 재발을 막는다. **수정은 Phillip 소유 경로이므로 판단은 사용자에게 남긴다.**

---

### M8 — `config/economic_config.yaml`의 `discount_cost_krw`가 죽은 설정값이다

**파일** `config/economic_config.yaml:124`(필드 선언) · `src/measurement/config_loader.py:130,230`(로딩) · `src/measurement/economics.py:260-322`(`coupon_cost()`, 미사용 확인)
**심각도** major

**요지:** `cost_accounting.discount_cost_krw: 7000`이 `CostAccountingConfig.discount_cost_krw`로 로딩되고 `_require()`로 필수값 취급되지만, 실제 쿠폰 비용 계산 함수 `economics.coupon_cost()`는 D-16 결정에 따라 `config.treatment_cost[treatment_id]`를 순회하는 유도 규칙으로 구현되어 있고 `discount_cost_krw`를 전혀 읽지 않는다(`grep -rn discount_cost_krw` 결과: yaml 선언 1 · config_loader 로딩 2 · 테스트 픽스처 1뿐, 계산 코드 0건).

**failure_scenario:** 이 값이 "쿠폰이 실제 사용된 주문에만 계상한다"는 주석 바로 옆에 있어, 다음 사이클 개발자가 "쿠폰 할인액은 이 필드 하나로 고정돼 있다"고 오독하기 쉽다. 실제로는 처치별(T2=3,000원·T3=7,000원)로 다른데, 이 필드를 바꿔도 아무 계산도 바뀌지 않는다.

**GATE 1과의 관계:** `economic_config.yaml`은 이미 `canonical_files`에 SHA-256으로 걸려 있고 `ECONOMIC_RULE_v1` 항목은 아직 `PENDING`(미잠금)이다. **지금이 정리 비용이 가장 싼 시점**이다 — 잠긴 뒤 정리하면 `FREEZE-003`(전 데이터 재생성)이 발동한다.

**권고:** ⑴ 불필요하면 config에서 제거하고 `_require` 호출도 제거한다(반쪽짜리 하위호환 유지 금지). ⑵ 별도 용도(예: 트리트먼트 아닌 다른 경로의 정액 할인)였다면 `economic-rule-v1.md`에 명시하고 실제로 읽는 코드를 추가한다.

---

### M9 — `tests-with-deps.yml`의 "Report skip count" 스텝이 회귀를 실제로 막지 못한다

**파일** `.github/workflows/tests-with-deps.yml`(`Report skip count` 스텝)
**심각도** major
**소유** `ownership.json`상 `sealed`(사용자 직접 작성, D-19 승인) — 아래는 수정 제안이 아니라 리드 보고용 관찰이다.

**요지:** 이 워크플로우의 주석 자체가 "skip 수가 올라가면 검사가 조용히 멈춘 것이고, 잡이 녹색이어도 회귀다"라고 명시하지만, 실제 스텝은 `python -m unittest discover -s tests -t . 2>&1 | tail -3`만 실행한다 — **임계값 비교도 실패 조건도 없다.** `skipped=3`이 다음 PR에서 `skipped=67`로 늘어나도(예: `skipUnless(pyarrow_available)` 조건이 잘못 바뀌어 with-deps 환경에서도 skip되도록 만들어도) 이 스텝은 여전히 exit 0으로 초록이다.

**참고 — 같은 실패 양식이 이미 한 번 있었다:** `wave-log.md`(N-12)가 기록한 `d3_source_hash_verify.py` 결함(`skipped`와 `unverifiable`을 한 버킷으로 묶어 종료 코드가 무시 → "검증 불가"를 출력하면서 exit 0)과 같은 종류다.

**권고(리드 판단 필요 — sealed 파일):** ⑴ skip 수 기준값(현재 3)을 명시하고 초과 시 `exit 1`하도록 바꾼다. ⑵ 최소한 `ponytail:` 마커(업그레이드 트리거 포함)로 "이 스텝은 사람이 읽어야 의미가 있다"는 한계를 명시한다.

---

### M10 — doctest 18개가 저장소 어디에서도 실행되지 않고, 그 중 1개가 이미 실패 중이다

**파일** `src/measurement/{contracts,economics,kpi,publish,schema,sink}.py`(doctest 보유 6개 모듈), 실패 지점 `kpi.py:1219`(`metric_classification()["total"]`)
**심각도** major (**팀 리드가 전수 실행해 확정함**)

**요지:** 전 소스에 doctest 예제가 18개 있으나(`contracts.py` 6 · `economics.py` 4 · `kpi.py` 1 · `publish.py` 4 · `schema.py` 1 · `sink.py` 2), `grep -rn "doctest" tests/ .github/workflows/`가 0건을 반환한다 — **어떤 테스트 러너도 이 예제들을 실행하지 않는다.** 실제로 실행해보면 17개는 통과하지만 `kpi.py:1219`의 doctest 하나가 이미 실패 중이다:

```
Failed example:
    metric_classification()["total"]
Expected: 47
Got:      46
```

**failure_scenario:** 이 `47`은 이미 **세 번째로 전파된 자리**다 — `kpi-definition-v1.md` §8 총계, `kpi_report.schema.json:5`의 `description`(기계가독 계약 문서화 텍스트), 그리고 이 doctest. 앞의 두 곳은 산문/문서라 자동 검출 수단이 원래 없지만, **doctest는 이미 실행 가능한 형태로 존재했는데 실행기가 없어서 놓쳤다.** 나머지 17개 예제는 통과하므로, `tests/`에 doctest 수집 한 줄만 있었어도 이 오류는 처음부터 잡혔을 것이다.

**권고:** `unittest` discovery에 doctest를 편입한다(예: `tests/__init__.py`의 `load_tests` 훅으로 `doctest.DocTestSuite("measurement.<module>")`를 6개 모듈에 대해 추가). **단, `isolation.yml`(의존성 없는 잡)에서 import 가능한 모듈만 넣어야 한다** — 위 6개 모듈은 의존성 있는 환경에서 import 성공을 확인했을 뿐이고, `config_loader.py`(유일한 `import yaml` 접점)는 doctest 예제가 0개라 대상이 아니다. **확인 없이 추가하면 ISO-005(의존성 없이 통과)를 깨고 `isolation.yml`이 `ImportError`로 죽을 수 있다** — 의존성 없는 환경에서 각 모듈의 import 가능 여부를 먼저 확인한 뒤 대상 목록을 확정할 것을 권고한다. `kpi.py:1219`의 `47→46` 불일치 자체는 이 doctest 하나만 고쳐 닫을 수 없다 — `kpi-definition-v1.md` §8과 `kpi_report.schema.json:5`도 함께 정정해야 세 자리가 다시 갈라지지 않는다.

---

## B. Minor Findings

### m1 — `errors.py`의 실제 종료 코드가 `exceptions.md` §5 설계표와 다르다

**파일** `src/measurement/errors.py:69,91,103,109,120` vs `.agent-team/04-architecture/exceptions.md` §5

| 예외 | 문서(§5) | 실제(`errors.py`) |
|---|---|---|
| `QualityGateFailure` | 2 | 2 ✅ |
| `ContractViolation` | (표에 없음) | **3** |
| `FreezeViolation` | 3 | **4** |
| `ConfigError` | 5 | 5 ✅ |
| `PublishError` | 4 | **6** |
| `DependencyMissing` | (표에 없음) | **7** |

현재 이 특정 숫자로 분기하는 CI·스크립트는 없다(`test_quality_checks.py`의 `exit_code==2` 단언 하나뿐). 다만 문서가 코드의 정본 노릇을 못 하고 있어, 나중에 exit code 3을 보고 "봉인 불일치"로 오판(실제로는 계약 위반)할 위험이 있다.

**권고:** `exceptions.md` §5 표를 실제 값(2/3/4/5/6/7)으로 갱신한다. 코드는 바꿀 필요 없음 — W6 Timothy 소관.

---

### m2 — `verify_core_invariants`/`assertMetricValueInvariants`의 노드 판별이 "위치"가 아니라 "모양"에 의존한다

**파일** `src/measurement/contracts.py:383-390` · `dashboard/src/lib/artifacts/read.ts:117-119`

두 구현 모두 "트리 안에서 문자열 `status` 필드를 가진 dict/object를 만나면 `metric_value`로 간주"하는 덕타이핑으로 재귀 검사를 한다. 현재는 `data_quality_report.checks[].status`가 `metric_value.status`와 `blocked`/`not_run` 값을 공유하지만 요구 필드가 우연히 호환돼 오탐이 없다. 이것이 의도적 설계가 아니라 우연이라면, 향후 한쪽 스키마에 이름이 겹치는 새 필드(예: `value`)가 추가되면 다른 쪽 검사기가 잘못된 규칙을 적용하게 된다.

**권고:** 급하지 않다. 다음 스키마 개정 시 판별을 "값이 사는 JSON 경로 패턴"으로 좁히거나, 최소한 "이 판별은 모양 기반이며 우연한 값 공간 공유에 의존한다"는 주석을 남긴다.

---

### m3 — `EventSink._next_part_index`는 동시 다중 프로세스 기록에서 경쟁 조건이 있다

**파일** `src/measurement/sink.py:350-372`(`_next_part_index`), `sink.py:244-255`(`_write_partition`)

같은 `EventSink` 인스턴스 안에서는 로컬 캐시로 D1-1(파티션 덮어쓰기) 재발을 막지만, **서로 다른 프로세스가 같은 `date=` 디렉터리에 동시에 쓰면** 둘 다 같은 "최댓값+1"을 읽고 같은 파일을 써서 나중 프로세스가 먼저 프로세스를 덮어쓴다 — D1-1과 같은 증상이 동시성이라는 다른 트리거로 재발할 수 있다.

**현재 영향:** C1에는 `src/orchestration/`·`src/simulator/`가 미가동이라 이 경로가 실행되지 않는다.

**권고:** 지금 고칠 필요 없음(범위 밖). `sink.py`의 기존 `ponytail:` 마커 옆에 "단일 프로세스 전제"를 명시하는 세 번째 마커를 추가해 다음 사이클(시뮬레이터/오케스트레이션)이 판단 없이 재사용하지 않게 한다.

---

### m4 — AI 투자 비용 문서 vs 코드 수치 불일치가 미해결로 이월되고 있다

**파일** `src/measurement/economics.py:630-657`(`ai_investment_cost`) vs `.agent-team/03-service-planning/economic-rule-v1.md` §5 / story `m-03` §4.3

설계 문서는 식의 결과를 "≈2,020,000원"이라 적었지만 실제 코드(식을 정확히 구현)는 `1,550,000 × 1.4 = 2,170,000`을 낸다. 코드는 정확하고 값은 `unconfirmed`로 정직하게 나가며 `ai_roi`가 C1에서 항상 `unavailable`이므로 판정에는 영향이 없다. **W3부터 "리드 판정 필요"로 여러 웨이브를 거쳐 미해소 상태다.**

**권고:** W6에서 반드시 닫는다 — 문서의 계산 결과가 오타였는지 확인하고 문서를 코드에 맞춰 정정한다.

---

### m5 — `economics.py`에 처치 ID `"T1"`이 매직 리터럴로 하드코딩되어 있다

**파일** `src/measurement/economics.py:333`(`shipping_subsidy`, `"T1" in order.treatment_ids`)

같은 함수의 `coupon_treatments`·`treatment_cost`는 전부 config에서 오는데 이 값만 예외다. 처치 ID 체계가 바뀌면 이 한 줄만 조용히 어긋난 채 남는다 — 스키마·컴파일 어느 쪽도 잡지 못한다.

**권고:** `config.free_shipping_treatment_id`처럼 config 필드로 승격하거나 최소한 모듈 상수로 분리한다.

---

### m6 — `freeze.py`에 죽은 함수 `build_freeze_status()`가 미정의 이름 2개를 참조한다

**파일** `src/measurement/freeze.py:300-344`

`freeze.build_freeze_status()`는 저장소 어디서도 호출되지 않는다(`publish.py`가 동일 이름의 별개 함수를 갖고 있고 실제 파이프라인은 그쪽을 쓴다). 이 죽은 함수 내부는 `_FREEZE_ITEMS`(존재하지 않음, 실제는 `_LOCK_ROWS`)와 `_GATE1_PRECONDITIONS`(존재하지 않음, 실제는 `GATE1_PRECONDITIONS`)를 참조한다 — 실행되면 즉시 `NameError`다.

**권고:** 삭제하거나(권장 — `publish.build_freeze_status()`가 이미 같은 역할), 별도 용도가 있다면 이름 충돌을 피하고 참조를 고친 뒤 테스트를 추가한다.

---

### m7 — `index.json` 쓰기가 다른 6종 산출물과 달리 원자적이지 않다

**파일** `src/measurement/publish.py:1396-1402`

6개 본체 산출물은 staging에 쓴 뒤 `os.replace()`로 원자적으로 옮기지만, `index.json`은 최종 경로에 `write_text()`로 직접 쓴다 — staging·`os.replace`를 거치지 않는다. 대시보드가 쓰기 도중(open→write→close 사이) `index.json`을 읽으면 손상된 JSON을 받을 수 있다.

**권고:** `index.json`도 임시 파일에 먼저 쓰고 `os.replace()`로 옮기도록 통일한다.

---

### m8 — `provenance.generated_by`가 실제 실행 명령이 아니라 고정 문자열이다

**파일** `src/measurement/contracts.py:316`

`"generated_by": "src.measurement.publish"`는 리터럴 상수다. `api-contracts.md` §3.2는 "생성기가 런타임에 자기 실행을 기록한다"고 명시했지만, 실제로는 `--source`/`--out`/`--config` 등 실행 인자를 담지 않는다.

**권고:** `main()`에서 실제 `sys.argv`(또는 재구성한 CLI 문자열)를 `publish()`에 전달해 `build_provenance()`가 쓰도록 한다.

---

### m9 — `index.json`의 `artifacts[].path` 정규식이 `..` 경로 탈출을 문자열 수준에서 막지 않는다 (런타임에서는 완화됨)

**파일** `docs/contracts/measurement-publish/v1/index.schema.json:114-118`

`pattern: "^(results|data/processed)/"`는 접두사만 검사한다. `"path": "results/../../data/hidden/secret.json"`은 이 정규식을 **통과한다**(jsonschema로 실행 검증함). 계약 문서(§5.7)는 "DB-014 위반 경로를 게시 인덱스에 적을 수 없다"고 설명하지만 이 특정 불변식은 스키마 자체로는 성립하지 않는다.

**완화 사실:** 실제 익스플로잇 경로는 막혀 있다 — `dashboard/src/lib/artifacts/paths.ts:98-118`의 `resolveArtifactPath()`가 `resolve()` 정규화 후 `startsWith(RESULTS_DIR + sep)`를 별도로 검사해 런타임에 `..` 탈출을 차단한다(코드 확인). 즉 계약은 뚫려 있지만 읽는 쪽(대시보드)이 최종 방어선 역할을 한다.

**권고:** 우선순위 낮음. 다음 계약 개정 시 `not: {"pattern": "\\.\\."}`를 추가해 계약 자체도 자기 설명을 충족하게 한다.

---

### m10 — `python -O` 실행 시 `sink.py`의 정밀도 자기검증이 통째로 사라진다

**파일** `src/measurement/sink.py:411-414`

저장 정밀도 자기검증이 `assert` 문으로 되어 있어 `python -O`(최적화 모드)로 실행하면 이 불변식 검사가 사라진다. 이 저장소 어디서도 `-O` 실행을 언급하지 않아 실무 영향은 낮다.

**권고:** 급하지 않음. 정직성 규율과 일관되게 `if ... raise AssertionError(...)` 형태로 바꾸거나 무시해도 됨을 명시한다.

---

## 확인했으나 문제 없음으로 판정한 항목 (근거 남김)

이하는 팀 리드가 특별히 주목하라고 지시한 항목들 중 **실측 결과 이상이 없는** 것들이다. "확인 안 했다"와 "확인했고 이상 없다"를 구분하기 위해 근거를 남긴다.

| 항목 | 확인 방법 | 결과 |
|---|---|---|
| `common.schema.json` `metric_value.allOf[2]`의 `not`/`anyOf` 구조(F-F 회귀 재발 여부) | jsonschema 4.25.1로 반례 실행(basis 단독/value_formatted 단독/둘 다) | **정상.** 3가지 반례 전부 정확히 거부됨 |
| `data_quality_report.schema.json`의 `vacuous` 절 개수(F-E 회귀 재발 여부) | 직접 파싱, `checks[].allOf` 중 `status.const=="vacuous"` 절 카운트 | **1개.** "추가"가 아니라 "교체"가 유지되고 있다 |
| `index.schema.json`의 `ALL_CLEAR` 가드 · `headline_code` 8종 enum | 직접 파싱 | `REJECTED_EVENTS` 포함 8종 · `rejected_events > 0 → ALL_CLEAR` 금지 가드 존재 확인 |
| `rejection_report.schema.json`의 `offending_values` 22컬럼 화이트리스트 | `propertyNames.enum` 원소 수 카운트 | **정확히 22개**, `DATA-003` `EVENT_FIELDS`와 이름까지 일치 |
| `kpi_report.schema.json`의 `combined` 키 금지(R-7), `experiment` 계층 `by_source` 분해 금지(MEA-002) | 스키마 직접 확인 + 실행 검증 | 둘 다 정확히 거부됨 |
| `derived:true → derivation` 필수, `unit:ratio → basis.denominator` 필수, `denominator==0 → ok` 불가 | jsonschema 실행 검증 | 전부 정확 |
| `generated_at`의 `Z` 표기 거부(`+09:00`만 허용) | 실행 검증 | 정확 |
| `src/measurement/`의 격리(`commerce`/`simulator` 미의존) — `kpi.py`·`economics.py` | grep 전체(대소문자 무관, docstring 포함) | **0건** |
| `freeze.py`/`contracts.py`의 "commerce"/"simulator" 매치 | 원문 확인 | 전부 `owner_part`(GATE 소유 파트 표기)·`simulator_commit`(재현성 해시)로, 이벤트 출처 분류(P-3)와 무관한 개념 |
| `index_date` 기본값 없는 키워드 전용 인자(R-1), 전향/후향 별도 함수명(R-2) | 전체 함수 시그니처 확인 | 준수 |
| `CostAccountingConfig`에 `cost_rate` 필드 부재(EC-9) | 확인 | 부재 확인 |
| `A-REFUND` 오차 방향 일관성 | `economic_config.yaml`·`gate1_lock.yaml`·`publish.py`(`REFUND_NOT_ADJUSTED` notice) 대조 | 세 곳 모두 "과대평가 방향"으로 일치 |
| GATE 1 `canonical_files` 해시 무결성 | 4개 파일 SHA-256 직접 재계산 vs `gate1_lock.yaml` | **4/4 일치** |
| `freeze.py`의 `import yaml` 격리 위반(frontend.md §12.7이 과거 발견) | import문 직접 확인 | **해소됨** — `config_loader.dump_yaml/load_yaml/yaml_available`를 통해서만 접근 |
| `met: None`이 `False`로 조용히 뭉개지는 곳 | `freeze.py`의 `met` 참조 전체 확인 | `is not True`·`is False`로 보수적 분기, None과 False가 섞이지 않는다 |
| 대시보드 `?? 0`·`\|\| 0`·`Number(`·`.toFixed(`·`.toLocaleString(`·`filter(...>0)` | `grep -rnE` 재실행(주석 제외) | **0건**(31개 파일) |
| 대시보드 `assertMetricValueInvariants()`의 계산 불가 3종(`unavailable`/`blocked`/`not_run`)만 throw 조건 | `read.ts:110-137` 원문 확인 | 스토리 AC-6 문언(`status !== "ok"`)을 문자 그대로 안 따른 것이 **의도적·정확한 이탈**임을 주석으로 확인 |
| `paths.ts`의 path traversal 방어 · `AIROI_RESULTS_DIR`의 `??` 미사용 | 원문 정독 | `results/../../data/hidden/secret.json` 우회 불가, `typeof === "string" && trim().length > 0` 판정 확인 |
| `run_id`/`contract_version` 불일치 시 값 혼합 방지 | `read.ts` 원문 | 개별 검사 후 즉시 실패 반환, 렌더링 안 함 |
| `RejectionSample`의 `offending_values` 제거 | `types.ts`·`rejections/page.tsx:157-158` | 타입에서 아예 빠져 있어 컴파일 타임에 그릴 수 없다 |
| `VerdictBanner.tsx`의 `headline_code` 8종 매핑 완전성 | `HEADLINE` 맵 확인 | 8종 전부 커버, 맵에 없는 코드는 조용한 기본값 대신 "알 수 없는 판정 코드" 명시 표시 |
| `dashboard/`의 `src/**`(Python) import 여부 | grep | import문 기준 0건(문자열 리터럴 2건은 안내 문구/주석일 뿐 실제 참조 아님) |
| 8개 데이터 품질 검사 × 3축(pass/fail/vacuous) 실제 커버리지 | `tests/test_quality_checks.py` 정독 | 8개 검사 전부 `subTest`로 3축 실행, `assertIn` 트랩 없음 |
| `test_isolation.py`의 우회 가능성(상대 import·동적 import) | 원문 정독 + grep | 이론적 한계는 문서화된 대로이나 실제로 그 구멍을 쓰는 코드는 0건 |
| `strict=False` 관용 모드가 backend.md §4.1 설명대로 구현됐는지 | `sink.py` `write_events()` 정독 | `event_type` 무효/부재만 거부, 나머지 위반은 저장+보고 — 설명과 일치 |
| `ponytail:` 마커 3건(sink.py 2건 확인, contracts.py 1건) | 위치·내용·업그레이드 트리거 직접 대조 | 전부 backend.md 주장과 일치 |

---

## 검증 실행 기록 (재현용)

```
$ python3 -m unittest discover -s tests
Ran 407 tests in 0.362s
OK (skipped=67)

$ /tmp/airoi-review-deps/bin/python3 -m unittest discover -s tests   # pyarrow 25.0.1 · PyYAML 6.0.3 · jsonschema 4.26.0 · referencing 0.37.0
Ran 407 tests in 4.680s
OK (skipped=3)
```

Python 버전 참고: 재현 venv는 로컬 3.14로 만들어졌다. CI parity(3.12.4)와 다르지만 두 값 모두 407/OK로 동일하게 나와 버전 차이로 인한 결과 차이는 없었다. **다만 M3이 지적하듯, 이 사실 자체가 "3.10에서도 통과한다"는 근거는 아니다** — 3.10 인터프리터로는 실행하지 못했다.

```
jsonschema 4.25.1(별도 python3.12 환경)로 common.schema.json·index.schema.json·
ingestion_report.schema.json·field_coverage_report.schema.json·freeze_status.schema.json·
kpi_report.schema.json·rejection_report.schema.json·data_quality_report.schema.json
8종 전부에 대해 Draft202012Validator.iter_errors()로 반례 실행 검증(F-F·F-E 회귀,
denominator==0, derived/derivation, ratio 필수, combined 금지, experiment 분리,
generated_at KST, offending_values 22컬럼, M6의 3개 반례 등)
```

---

## 결론

C1 측정 계층·대시보드 구현은 설계 문서(api-contracts.md·exceptions.md·design-patterns.md)가 요구한 핵심 불변식 대부분을 실제로 지키고 있다. "세 번째 값" 패턴이 스키마·백엔드·프론트엔드 세 층에 중복 강제되어 있고, 그 중복 방어가 실제로 서로 다른 버그(F-E/F-F 계약 회귀, ADR-0002 경로 오류, R-1/R-2/R-3 게시 결함)를 잡아낸 이력이 `wave-log.md`에 남아 있다.

그러나 이번 리뷰는 **같은 원칙이 예외적으로 깨진 자리(M1)를 하나 찾았다** — 계층 0 지표가 검증되지 않은 `manifest` 입력에서 `.get(key, 0) or 0`으로 결손을 조용히 0으로 채운다. 이 프로젝트가 스스로 가장 경계한 실패 양식이 정확히 재발한 자리이며, GATE 진행 전 최우선으로 닫아야 한다.

또한 이번 리뷰는 **값 계층의 철저함이 선언 계층에는 아직 미치지 않은 지점 4곳(§0.1 — M1·M7·M9·M10)**을 확인했다 — manifest 입력에 계약이 없고, 카탈로그의 "computable" 선언이 대조되지 않고, CI의 skip-count 경고가 임계값 없이 출력만 되고, 18개 doctest 중 실행 가능한 유일한 자동검출 지점(`kpi.py:1219`)이 아무도 돌리지 않아 이미 실패 중이었다. 그 외 major 6건(M2·M3·M4·M5·M6·M8)은 대부분 "현재는 도달하지 않지만 GATE 2 이전에는 반드시 확인해야 하는" 성격이며, M4·M5는 blocking 후보로 별도 검토한 결과 둘 다 blocking 아님(근거는 각 항목 참조)으로 판정했다.

발견한 20건(major 10 · minor 10) 중 **blocking은 없다** — 모든 결함이 현재 데이터를 틀리게 만들지 않거나(스키마가 fail-closed로 잡음) 아직 실행되지 않는 코드 경로에 있다.
