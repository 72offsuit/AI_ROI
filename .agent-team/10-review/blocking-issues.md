# Blocking Issues — W5 측정 계층 + GA형 관측 대시보드 (PR #57)

**작성** Thomas (Role 12 · 코드 리뷰어) · 2026-09-14
**갱신** 6개 병렬 리뷰 포크 + 팀 리드 추가 실행 검증 4건(F1 원인, Python 3.10, 카탈로그 미검증, doctest 18개)을 전부 병합한 최종본. 이전 버전이 포크 하나가 자기 소관 6건만 담아 먼저 디스크에 쓴 것을 리드가 지적해 이번에 전체 집합으로 재작성했다.

## 판정: blocking 0건

전체 리뷰(`code-review.md`, finding **20건 — major 10 · minor 10**)에서 **머지를 막아야 할 결함은 발견하지 못했다.**

일반 근거:

- `python3 -m unittest discover -s tests`가 의존성 유무 양쪽 환경에서 모두 실제로 재현되며(`Ran 407 · OK`, skip 67/3), PR이 주장하는 수치와 정확히 일치한다.
- GATE 1 부분 봉인의 `canonical_files` SHA-256 4건을 직접 재계산해 전건 일치를 확인했다 — 봉인 기록이 실제 파일 상태를 정확히 반영한다.
- "결손을 조용히 0으로 채운다" 계열 결함을 이 사이클이 스스로 가장 취약하다고 지목한 지점(JSON Schema `not`/`anyOf`, `vacuous` 이중 강제, 대시보드 `?? 0`) 위주로 직접 재현·재파싱했고 전부 방어가 살아 있었다.
- 파트 격리(`measurement`가 `simulator`/`decision`/`diagnostics`를 참조하지 않음)와 창구 중립성(`kpi.py`/`economics.py`가 출처 문자열을 모름)도 재확인해 위반이 없었다.

## ★ blocking 후보로 개별 검토한 2건 — 판정과 근거

리드 지시에 따라 아래 2건은 "major로 뭉뚱그리지 않고" 각각 blocking 여부를 명시적으로 판정한다.

### M4 — `FREEZE_MISMATCH` 헤드라인 배선 결함 → **blocking 아님**

`build_index()`가 조립하는 `counts` 딕셔너리에 `freeze_mismatch` 키가 절대 채워지지 않아(직접 grep 재확인 — 값 대입 0건), 봉인 파일이 변경돼도 대시보드 최상단 배너(`index.verdict`)가 그 사실을 드러내지 못한다.

**blocking이 아닌 이유:**
1. **정보 자체는 사라지지 않는다** — `freeze.verify()`가 계산하는 `verification: "mismatch"`는 정확하고 `/freeze` 화면(V6, freeze_status.json)에는 지금도 정확히 실린다. 깨진 것은 "최상단 배너로 옮기는 배선"뿐이다.
2. **오늘 이 경로는 물리적으로 트리거될 수 없다** — GATE 1은 `overall: partial`, `LOCKED` 항목 0종이다. 잠긴 대상이 없으므로 "잠긴 뒤 변경됨"이라는 전제 자체가 성립하지 않는다. 즉 현재 브랜치의 어떤 실행도 이 결함으로 인해 잘못된 배너를 낸 적이 없고 낼 수도 없다.
3. 다음 사이클에서 GATE 1이 실제로 잠기기 전까지 고치면 충분하다.

**언제까지는 반드시 고쳐야 하는가:** GATE 2 착수 전. 리드가 이슈화 여부를 판단할 것.

### M5 — `freeze.py`의 `ConfigError` 미임포트로 인한 `NameError` → **blocking 아님**

`verify()`가 손상된 `canonical_files`(매핑이 아닌 형태)를 만나면 `ConfigError`를 raise하려 하지만 import가 없어 `NameError`로 크래시한다(직접 grep 재확인 — import 목록에 `ConfigError` 없음, 72행은 주석일 뿐).

**blocking이 아닌 이유:**
1. **오늘 이 경로에 도달하는 정상 입력이 없다** — 현재 `config/gate1_lock.yaml`의 `canonical_files`는 정상 매핑이고, SHA-256 4건 전부 일치를 직접 재계산해 확인했다. 이 파일이 손상되지 않는 한 이 raise 문은 실행되지 않는다.
2. `freeze.py:466`은 방어 코드이지 정상 경로가 아니다 — 방어 코드의 오류는 "정상 동작이 잘못됨"보다 한 단계 낮은 심각도다.

**그럼에도 가볍게 볼 수 없는 이유(기록해 둔다):** 방어 코드가 정확히 방어가 필요한 순간(lock 파일 손상)에 더 나쁜 실패(정체불명 크래시)로 바뀐다는 역설이 있다. `import` 한 줄 누락이라는 원인의 단순함을 생각하면 지금 고치는 비용은 거의 0에 가깝다.

**언제까지는 반드시 고쳐야 하는가:** GATE 1이 실제로 잠기는 시점 전 — 그때부터 `gate1_lock.yaml`은 사람·도구가 다루는 살아있는 파일이 되어 손상 가능성이 실질적으로 올라간다.

## Major 10건 전체 요약표

| # | 요지 | 왜 지금은 blocking이 아닌가 |
|---|---|---|
| M1 | `manifest` 무검증 입력 → 계층 0 지표 `.get(key,0) or 0` | 국소 누락(같은 모듈 다른 함수는 규율 준수), 정상 manifest에서는 미재현. 리드가 직접 3케이스 재현 |
| M2 | `field_fill_rate` 분모 0 가드 누락 | 스키마가 fail-closed로 잡아 화면 증발로 그침(틀린 값 아님) |
| M3 | Python 3.10 선언 vs 실제 미지원(`Z` 접미사, `fromisoformat`) | CI가 3.12 고정이라 오늘 발현 안 함, 3.10 직접 재현은 못 함(BLOCKED로 구분 표기) |
| M4 | `FREEZE_MISMATCH` 배너 배선 결함 | 위 개별 판정 참조 — GATE 1이 아직 아무것도 `LOCKED`하지 않아 오늘 도달 불가 |
| M5 | `freeze.py` `ConfigError` 미임포트 → `NameError` | 위 개별 판정 참조 — lock 기록이 정상인 한 이 분기에 도달 안 함 |
| M6 | JSON Schema 3종(ingestion/field_coverage/freeze_status)이 개수만 세고 이름·고유성 미검증 | 현재 게시물은 이름이 정확함(별도 확인) — 미래 회귀를 못 잡는 것이 문제 |
| M7 | 카탈로그 `computable` 선언 3종 구현/계약 부재 + 반대방향 1건(sleeping_dog_targeting_rate) | 사라진 것이지 틀린 값이 아님(A-4 패턴이지만 크래시·오염 없음) |
| M8 | `discount_cost_krw` 죽은 설정값 | 미사용 상태일 뿐 계산에 영향 없음 |
| M9 | `tests-with-deps.yml` skip-count 무의미(sealed) | 사람이 로그를 보면 여전히 알아챌 수 있음, 구현자 수정 권한 밖 |
| M10 | doctest 18개 미실행, 1개 이미 실패(`kpi.py:1219`, 47 vs 46) | 실패 자체가 `unconfirmed`/문서 수준 불일치일 뿐 게시물 값에 영향 없음(이미 알려진 47 vs 46 불일치의 세 번째 자리) |

## 리드 확인 요청 사항 (판정이 아니라 보고)

1. **M1·M2** — 수정은 Phillip 소유 경로(`src/measurement/kpi.py`·`publish.py`)이므로 리뷰어가 임의로 고칠 수 없다. GATE 1이 `ECONOMIC_RULE_v1`·`KPI_DEFINITION_v1`을 실제로 잠그기 전에 닫을 것을 강력히 권고한다.
2. **M3(Python 3.10)** — 해소 경로가 둘 다 C1 범위 밖이다: ⑴ SRS 목표 런타임 선언을 3.12로 좁힌다(`Plan/`은 읽기 전용, 이슈로만 제기 가능) ⑵ 코드에서 `Z`→`+00:00` 전처리를 추가한다(CI에 3.10 잡이 없어 회귀 방지 불가). 어느 쪽을 택할지 사용자 결정이 필요하다.
3. **M4·M5** — GATE 1이 실제로 잠긴 뒤(다음 사이클)에는 반드시 고쳐야 하는 잠재 결함이다. 지금 병합을 막을 이유는 없지만 이슈로 남겨 GATE 2 착수 전 재확인을 권고한다.
4. **M6** — 다음 계약 개정(어차피 GATE 1 완전 잠금 전 최소 1회는 더 있을 것) 때 함께 반영 권고. `contains`/`minContains`/`maxContains`로 JSON Schema 자체에서 표현 가능함을 확인했다(교차 필드 비교가 아니라 배열 원소 카운트라 Q-3 정정과 무관).
5. **M7** — `missing_field_count`·`source_event_count`·`rejection_reason_count`를 실제로 게시할지, 카탈로그에서 뺄지 결정이 필요하다. `sleeping_dog_targeting_rate`는 카탈로그 추가가 명백히 맞다.
6. **M8** — `discount_cost_krw`를 지금(아직 `PENDING` 시점) 정리할지, 다음 사이클로 미룰지는 리드 판단이 필요하다.
7. **M9** — `.github/workflows/tests-with-deps.yml`은 `sealed`이므로 구현자가 임의로 고칠 수 없다 — skip 수 임계값 검사를 추가할지는 사용자/리드 결정 사항이다.
8. **M10** — doctest를 `unittest discover`에 편입하되 ISO-005(의존성 없이 통과) 유지 여부를 먼저 확인해야 한다. `kpi.py:1219`의 `47→46` 불일치는 `kpi-definition-v1.md` §8·`kpi_report.schema.json:5`와 함께 세 자리를 동시에 정정해야 재발하지 않는다.
9. **m4(AI 투자 비용 문서-코드 불일치, code-review.md 참조)** — W3부터 "리드 판정 필요"로 여러 웨이브를 거쳐 미해소 상태다. 이번 W6에서 반드시 닫을 것을 권고한다.

## 관통 패턴 (code-review.md §0.1 참조)

M1·M7·M9·M10 네 건은 "선언이 있는데 그 선언을 실제와 대조하는 장치가 없다"는 동일한 결함 양식이다 — manifest 입력에 계약이 없고, 카탈로그의 `computable` 선언이 검증되지 않고, skip-count 경고에 임계값이 없고, doctest가 실행되지 않는다. 개별 수정보다 이 네 자리에 "대조 장치 하나씩 추가"가 근본 처방이라는 점을 리드 판단에 참고 자료로 남긴다.
