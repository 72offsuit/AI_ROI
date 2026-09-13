---
reviewer: Matthias (Role 15 · QA Validator / SDET Lead)
stage: W3 Story Gate — 최종 재확인 (regate 2)
prior: review-w3-stories-matthias-regate1-confirm-kr.md (PASS · critical 0 · noncritical 2)
date: 2026-09-11
verdict: PASS (Matthias 렌즈 한정)
critical: 0
noncritical: 1 (N-11 · 낮은 가중치)
correction: N-4 — 내 1차 실측 범위가 좁았다
---

# W3 최종 재확인 (regate 2) — Matthias

**내 렌즈 판정: PASS · critical 0 · noncritical 1(낮은 가중치)**

**먼저 정정합니다 — N-4 의 제 실측이 틀렸습니다.** §3.

`F-E` 는 **제 코드로 직접 계산해 확인**했습니다. Matthew 의 venv 재현과 **독립적인 근거**입니다.

---

# 0. 이번에 실행한 것

| # | 검증 | 결과 |
|---|---|---|
| 1 | ★ **`F-E` 스키마 의미론 독립 계산** — 필요한 draft 2020-12 부분집합을 직접 구현 | **리드 표와 완전 일치** (§1) |
| 2 | ★ **`AC-4e` 회귀 주장 독립 계산** | **확인 · 리드/Thomas 판정보다 한 칸 더 샌다** (§4) |
| 3 | ★ `Ecommerce_Service/node_modules/@playwright/test` | **`1.63.0` 설치됨** — 내 1차 보고가 틀렸다 |
| 4 | ★ `playwright.config.ts` | **있음** · `baseURL 127.0.0.1:3100` · `Desktop Chrome` 1개 · `webServer` 자동 기동 |
| 5 | ★ `npx playwright install --dry-run` | **`~/Library/Caches/ms-playwright/chromium-1243` 로 다운로드 예정** = 바이너리 미설치 확인 |
| 6 | `package.json` devDeps | `@playwright/test ^1.63.0` · `js-yaml 4.3.2` · `"test:e2e": "playwright test"` |
| 7 | m-07 `vacuous` 교체 스니펫 원문 | **`examined_rows: 0` · `violations: null` 보존 확인** (§1) |
| 8 | m-06 §4.14 dict 계수 | **4건 + `value_formatted` 방향 분리** (§2) |
| 9 | d-02 §9.4 · T6 · AC-12 · DoD 원문 | ✅ (§3) |
| 10 | AC-4d · AC-4e 원문 | ✅ (§4) |
| 11 | AC·DoD 명령 **4차 전수** | **7종 — 1·2·3차와 동일.** 유령 명령 0건 |
| 12 | `unittest discover` · `check_ownership` | **Ran 46 OK** · **exit 0 PASS** |

---

# 1. ★ F-E — **수정이 정확합니다. 제 코드로 재현했습니다**

## 독립 검증 — Matthew 의 venv 를 근거로 쓰지 않았습니다

리드가 *"논리로 풀리는 것은 validator 없이 확정된다"* 고 하셨는데 맞습니다.
`const` · `required` · `properties` · `not` · `type:null` · `if/then` **여섯 키워드만** 쓰이므로, draft 2020-12 의미론을 그 범위에서 직접 구현해 계산했습니다. **미구현 키워드에 걸리면 즉시 중단하도록 만들어 두었고, 걸리지 않았습니다** — 커버리지가 완전하다는 뜻입니다.

```
                     현행allOf2   신규절    추가(둘다)   교체안
reason_code 없음        거부       통과       거부        통과
reason_code:NOT_RUN     통과       거부       거부        거부

→ 추가 방식: 두 경우 다 거부 = vacuous 게시 불가
→ 교체 방식: reason_code 없음만 통과 ✅
```

**리드 표와 한 칸도 다르지 않습니다.** `F-E` 는 사실이고, 정답은 **교체**입니다.

## 내가 놓친 이유 — 기록해 둡니다

regate 1 에서 저는 *"m-07 이 그 충돌을 스스로 표시했고(`⚠ allOf[2] 와 충돌한다`) **읽어서 맞다고 판단했을 뿐이다**"* 로 남겼습니다.
**충돌을 표시했다는 사실은 봤지만, 두 절을 `allOf` 로 합성했을 때의 결과를 계산하지 않았습니다.** 표시가 있으니 처리됐다고 읽은 것이고, `allOf` 는 **교집합**이라 "충돌"이 곧 "만족 불가능"이 되는 자리였습니다.

**그 자리를 `BLOCKED` 로 남긴 것이 발견을 불러왔다면, 남긴 값은 있습니다. 그러나 계산할 수 있었던 것을 계산하지 않은 것도 사실입니다.**
→ 이번에는 계산했습니다.

## 수정 반영 — 정확합니다

| 확인 | 결과 |
|---|---|
| `blocked`·`not_run` | **추가** (기존 제약 없음 → 올바름) |
| **`vacuous`** | **`allOf[2]` 교체** ✅ |
| 교체안이 `examined_rows: {const: 0}` 보존 | ✅ — `ADR-0010` 의 다른 보장이 살아 있다 |
| 교체안이 `violations: {type: null}` 보존 | ✅ |
| `required` 에서 `reason_code` 제거 + `not` 추가 | ✅ — **내 모델과 동일**, 계산 결과 의도대로 |
| *"두 편집이 한 쌍이다 — 하나만 하면 위 표의 실패로 간다"* | ✅ **이 문장이 핵심입니다.** `required` 만 지우고 `not` 을 빠뜨리면 `reason_code:NOT_RUN` 이 다시 통과합니다 |
| m-06 §4.15 규칙표 *"`vacuous` 는 추가가 아니라 교체다 — changelog 에 *교체*라고 적는다"* | ✅ |

---

# 2. noncritical 1건 — `empty-sink` 의 `vacuous` 7행

## N-11 — 교체 후 거부되는데 `INTENDED_FIXTURE_FAILURES` 에 없다

**실측:** `empty-sink` 의 `vacuous` 7건(`DQ-01`·`02b`·`04`·`07`·`08`·`10`·`11`)이 **전부 `reason_code: "NOT_RUN"`** 입니다.
**교체 후 계약은 이 7행을 거부합니다** — 제 계산의 두 번째 행이 바로 그 경우입니다.

`INTENDED_FIXTURE_FAILURES` 현재 4건 — `DQ-06`(Q-2) · `reported_checks`(Q-3) · `value_formatted:missing`(C-1) · `checks[] 18종`(Q-4). **`vacuous` 7행이 없습니다.**
m-06 자신의 규칙이 *"목록에 없는 실패 = 회귀. 즉시 실패"* 이므로, W5 는 `empty-sink` 에서 **7건의 미등록 실패**를 봅니다.

## 다만 — 함정은 아닙니다. 가중치를 낮춥니다

**AC-4d 의 다섯째 항목이 정확히 이것을 지시합니다:**

> *"**`empty-sink` 픽스처의 `vacuous` 7건이 수정 후 스키마에서 어떻게 되는지** 확인하고 **§4.14 의도된 실패 목록과 대조한다**"*

**대조하라고 했으므로 W5 가 스스로 발견해 등재합니다.** `G-1` 때와 달리 프로세스가 덮고 있습니다.

**그래도 미리 적는 편이 낫다고 봅니다** — 결과가 **결정론적**이고(제가 계산했습니다) 미리 적으면 *"빨간불을 보고 원인을 찾는 순간"* 자체가 없어집니다. §4.14 가 경계한 회피 반응(*"제약을 뺀다"*)이 나올 창이 닫힙니다. 여기서 제약을 빼면 **`F-E` 수정이 통째로 되돌아갑니다.**

**→ 항목 하나:**
```python
("empty-sink", "data_quality_report", "vacuous reason_code"):
    "F-E — vacuous 7건(DQ-01·02b·04·07·08·10·11)이 전부 reason_code:'NOT_RUN' 이다. "
    "allOf[2] 교체(not:{required:['reason_code']}) 후 거부된다. "
    "이 실패가 '실행했는데 0행'과 '실행 안 함'을 가르는 제약이 작동한다는 증거다.",
```

---

# 3. ★ N-4 — **내 1차 실측이 틀렸습니다.** 정정합니다

## 무엇을 잘못했나

1차·regate 1 에서 저는 이렇게 보고했습니다:

> *"수단은 어디에도 없습니다 — 전 스토리 grep `playwright`·`chromium` 0건. 실측: `ms-playwright` 캐시 없음 · `chromium` 바이너리 없음 · `AI_ROI/node_modules` 없음."*

**세 측정 전부 사실입니다. 그런데 범위가 `AI_ROI` 와 PATH 뿐이었습니다.**

**내 재실측:**

| 확인 | 결과 |
|---|---|
| `Ecommerce_Service/node_modules/@playwright/test/package.json` | **`"version": "1.63.0"`** |
| `package.json` devDependencies | **`"@playwright/test": "^1.63.0"`** · `"test:e2e": "playwright test"` |
| `playwright.config.ts` | **있음** — `baseURL "http://127.0.0.1:3100"` · `projects: [chromium/Desktop Chrome]` · `webServer` 자동 기동 |
| `npx playwright install --dry-run` | `Chrome for Testing 153.0.8010.12 → ~/Library/Caches/ms-playwright/chromium-1243` |

**리드 지적이 맞습니다. 막힌 것은 도구 선택이 아니라 `npx playwright install` 한 번입니다.**
*"수단이 없다"* 와 *"수단은 있고 바이너리만 없다"* 는 **구현자에게 완전히 다른 정보**입니다. 전자는 새로 설계하게 만들고, 후자는 버전·설정 형태를 옆 저장소에서 그대로 가져오게 만듭니다.

**교훈:** 이 사이클은 **2저장소 구조**이고 `AGENTS.md` 가 *"`Ecommerce_Service` 는 읽기 전용 참조 허용"* 을 명시합니다. **읽기가 허용된 곳은 실측 범위에 넣어야 합니다.** d-01 의 토큰 생성기는 제가 옆 저장소에서 확인했으면서 스크린샷 도구는 확인하지 않았습니다 — 일관되지 않았습니다.

## 처리가 충분한가 — **충분합니다**

| 요구 | 확인 |
|---|---|
| 셋 중 하나를 **먼저 고른다** | ✅ T6 첫 체크박스 · AC-12 마지막 항목 |
| **무조건 체크박스가 아니다** | ✅ **DoD:** *"위 두 항목은 T6 의 선택 ⑴·⑵·⑶ 중 하나를 고른 뒤에만 체크한다. ⑶ 을 골랐으면 `BLOCKED` 와 사유를 §9.4 에 적고 **체크하지 않는다** — 미실행을 통과로 표시하지 않는다"* |
| ⑶ 이 항목 삭제로 흐르지 않는다 | ✅ *"`AC-12`·DoD 항목을 지우지 않는다"* |
| L1 경계 | ✅ *"`npx playwright install` 은 네트워크 다운로드이고 `dashboard/` 에 devDependency 를 추가하는 것은 새 의존성이다 — **둘 다 L1, 사용자 결정**"* |
| 포트 충돌 | ✅ **3001**(dashboard) vs **3100**(Ecommerce) — 내가 config 에서 확인했습니다. 충돌 없음 |
| 버전 임의 결정 방지 | ✅ *"`^1.63.0`(옆 저장소와 맞춘다) … 새로 정하지 않는다"* |
| **`Ecommerce_Service` 편집 차단** | ✅ *"⚠ `Ecommerce_Service` 를 편집해 찍지 않는다. 그 저장소는 이 사이클에서 읽기 전용이다"* |
| §9.4 차단표 등재 | ✅ 전용 행 + 실측 표 |

**§7.2 가 C-2·C-11 에 보인 정직함이 이제 스크린샷에도 적용됐습니다.** 이것이 제가 요구한 전부입니다.

**한 가지만 덧붙입니다(조치 불요):** ⑵ 는 **네트워크 다운로드**를 전제합니다. W5 실행 환경에 외부 네트워크가 없으면 ⑵ 는 승인되어도 실패하고 ⑴ 또는 ⑶ 으로 되돌아옵니다. **스토리가 *"네트워크 다운로드"* 라고 적어 두었으므로 구현자가 그 사실을 알고 고릅니다.** 충분합니다.

## N-10 — 반영 확인

d-02 §9.4 에 숫자 렌더 차단 행이 들어갔고, **제 지적 근거까지 문장에 담겼습니다** — *"여기가 d-01 보다 무겁다. 숫자를 실제로 그리는 것은 골격이 아니라 `MetricCell` × 8화면이고, T5 가 `commerce-connected` 전 화면 렌더를 요구한다"* · *"`픽스처로 진행 가능` 에 숫자 렌더는 포함되지 않는다"*. ✅

---

# 4. AC-4d · AC-4e — **충분합니다. AC-4e 는 제가 요구한 것보다 강합니다**

## AC-4d — 내 `RL-3` 한계를 W5 에서 닫는 장치

*"계약 수정을 읽어서 판단하지 않는다 — validator 로 확인한다"* + 양방향 검증(`통과`/`거부` 둘 다) + *"하나라도 의도와 다르면 계약을 고치지 않고 멈춘다"*.

**특히 이 항목이 정확합니다:**
> *"`vacuous` 교체 형태 — … 가 **통과**하고, `reason_code` 를 넣으면 **거부**된다. **둘 다 확인한다** — 하나만 보면 만족 불가능해진 것을 못 잡는다"*

**`F-E` 를 놓친 실패 양식을 그대로 방어합니다.** 거부만 확인하면 `F-E` 상태가 "정상"으로 보입니다. 양방향이어야 잡힙니다.
그리고 *"`jsonschema` 가 없으면 이 AC 는 `BLOCKED` 이고 **계약 수정도 함께 보류한다**"* 가 맞습니다 — 검증할 수 없는 계약 수정을 진행시키지 않습니다.

## AC-4e — **더 강합니다. 그리고 제 계산으로는 한 칸 더 샙니다**

`not: {required: ["basis","value_formatted"]}` 는 *"둘 다 있지는 않다"* 가 되어 `basis` 금지가 사라집니다. **제 독립 계산:**

```
레코드                  틀린형태 not+required[a,b]   옳은형태 not+anyOf
① 둘 다 없음              통과                       통과
② value_formatted        통과   ← ★ 여기도 샌다      거부
③ ★ basis 있음           통과   ← ★ 회귀 지점        거부
④ 둘 다                  거부                       거부
```

**스토리 표는 ③을 회귀 지점으로 지목했고 맞습니다. 다만 틀린 형태는 ②도 함께 통과시킵니다** — 즉 **`value_formatted` 금지와 `basis` 금지가 동시에 무력화**되고, 새로 넣는 제약과 기존 제약이 **한 번에** 사라집니다. 스토리의 경고가 오히려 보수적이었습니다. (표의 `수정 후` 열은 옳은 형태 기준이라 정확합니다.)

**가장 좋은 부분은 이것입니다:**
> *"**`jsonschema` 가 없어도 이 검사는 실행한다** — `not` 은 논리 연산이므로 표준 라이브러리로 계산된다. … 계약 파일에서 `allOf[2].then.not` 을 **읽어와** 위 논리로 판정한다"*

**막힌 검사를 실행 가능한 검사로 바꿨습니다.** 이 저장소에서 실행 가능한 것이 `unittest` 하나뿐이라는 제약 안에서, **계약 의미론 검사를 그 하나 안으로 끌어들인 것**입니다. `skip` 대상이 아니라고 못 박은 것도 맞습니다 — 이 검사가 skip 되면 `basis` 금지 소멸이 조용히 통과합니다.

**더 필요한 것은 없습니다.** 굳이 하나 든다면 *"틀린 형태가 ③을 통과시킨다는 것도 함께 고정한다"* 는 이미 테스트 코드에 있습니다(`_not_required` 단언). **역방향까지 박아 두었습니다.**

---

# 5. "완료 거짓말" 최종 점검 — **새로 들어온 것 0건**

계약 수정이 4건 → 5건(`vacuous` 교체 포함)으로 늘고 AC-4d·AC-4e 가 신설됐습니다. **네 번째 전수 추출:**

```
npm run tokens:check · npm run tokens:test
python3 -m unittest discover -s tests
python3 -m unittest tests.test_isolation -v
python3 .agent-team/04-architecture/tools/check_ownership.py
python3 scripts/bench_sink.py 20000 30
python3 scripts/gen_event_schema_doc.py
```

**7종 — 1·2·3차와 동일 집합.** `pip install`·`pytest`·`ruff`·`mypy`·`docker` 0건.

**발생 불가한 조건이 새로 들어갔는가 — 없습니다.** 새 AC 의 조건을 전수 확인했습니다:

| AC | 조건 | 오늘 참/거짓이 갈리는가 |
|---|---|---|
| AC-4d `vacuous` 교체 양방향 | `{status:vacuous, examined_rows:0, violations:null, reason_detail:…}` 통과 / `reason_code` 추가 시 거부 | ✅ **내가 계산했습니다.** 두 경우 다 실재 |
| AC-4d `empty-sink` 7건 대조 | 실측 7건 존재 | ✅ |
| AC-4e ①~④ | 네 레코드 전부 구성 가능 | ✅ **`jsonschema` 없이도 실행 가능**하게 만들었다 |
| AC-4e ③ 회귀 | 실재하는 분기 | ✅ 계산 확인 |
| d-02 T6 선택 ⑴⑵⑶ | 셋 다 실행 가능 경로 | ✅ ⑴은 오늘 가능, ⑵는 L1 승인 + 다운로드, ⑶은 정직한 출구 |

**`jsonschema` 의존 항목은 전부 *"없으면 `BLOCKED`, 계약 수정도 보류"* 로 묶였습니다.** 미실행이 통과로 흐르는 경로가 없습니다.

## 회귀

```
python3 -m unittest discover -s tests   →  Ran 46 tests · OK
check_ownership.py                      →  exit 0 · PASS
```

---

# 6. 한계

| # | 한계 |
|---|---|
| **FL-1** | **`jsonschema` 로 돌리지 않았다.** `F-E`·`AC-4e` 는 **내가 구현한 부분집합 평가기**로 계산했다. 여섯 키워드(`const`·`required`·`properties`·`not`·`type:null`·`if/then`)의 draft 2020-12 의미론은 명확하고 미구현 키워드에 걸리지 않았지만, **실제 라이브러리가 아니다.** `AC-4d` 가 W5 에서 실물로 닫는 것이 맞다 |
| **FL-2** | **이번에도 수정 자리만 봤다.** §4 전면 재독은 하지 않았다 |
| **FL-3** | **Thomas 렌즈 미검증.** `NR-1`·`NR-2`·`TL-2` 가 어떻게 반영됐는지 보지 않았다. `AC-4e`·`value_formatted` 방향 분리는 내 항목과 겹쳐 확인했다 |
| **FL-4** | `dashboard/` 미존재 — 화면 명제는 **W6 에서만** 확인된다 |
| **FL-5** | `source_hash` 는 regate 1 에서 8/13 재현. **이번 수정 후 값은 다시 계산하지 않았다** — 스토리 본문이 바뀌었으므로 스토리 자신의 해시는 무관하나, **상류 문서가 바뀌지 않았다는 것은 확인하지 않았다** |
| **FL-6** | ⑵ Playwright 경로의 **네트워크 가용성**을 확인하지 않았다. `--dry-run` 은 다운로드 URL 만 보여준다 |

---

# 7. 판정

**Matthias 렌즈: PASS · critical 0 · noncritical 1**

| # | 남은 것 | 성격 | 비용 |
|---|---|---|---|
| **N-11** | `empty-sink` 의 `vacuous` 7행을 `INTENDED_FIXTURE_FAILURES` 에 미리 등재 | **AC-4d 가 대조를 지시하므로 함정 아님.** 결정론적이므로 미리 적으면 빨간불 구간이 없어진다 | dict 1항목 |

**`F-E` 는 정확히 고쳐졌고 제 코드로 확인했습니다. `N-4`·`N-10` 은 닫혔습니다. `AC-4d`·`AC-4e` 는 우리 셋이 공유한 한계를 W5 에서 실물로 닫습니다.**

**W5 가 잘못된 결과를 내거나 거짓 완료를 선언할 경로를 더 찾지 못했습니다.**

**제 실측 오류 하나를 기록으로 남깁니다** — `N-4` 에서 `AI_ROI` 만 보고 *"수단 없음"* 이라 보고했습니다. 2저장소 구조에서 **읽기가 허용된 저장소는 실측 범위에 넣어야 합니다.** 리드 지적이 맞았고, 그 지적이 없었으면 구현자가 이미 있는 도구를 새로 설계할 뻔했습니다.

**verdict 종합은 Thomas 재검증 후 리드 몫입니다.**

---

**Matthias** · Role 15 · QA Validator / SDET Lead
**"이번엔 읽지 않고 계산했다. 그리고 내가 좁게 본 자리를 적었다."**
