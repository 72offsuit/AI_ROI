# 보안 감사 — 측정 계층 + GA형 관측 대시보드 (PR #57)

**작성** Michael (Role 13 · 방어적 보안 전문가) · 2026-09-14 · 사이클 C1 · 브랜치 `feat/measurement-layer-and-dashboard`
**대상** `src/measurement/**` · `dashboard/src/**` · `config/**` · `requirements*.txt` · `dashboard/package-lock.json` · `e2e/package-lock.json` · `.github/workflows/**`
**성격** 보고 전용 — 제품 코드 미수정. 쓰기 권한은 `.agent-team/10-security/**` 뿐이며, 종료 시 `git status --porcelain -- src/ dashboard/ config/ tests/ docs/ .github/` 빈 출력을 확인했다.
**중복 방지** `.agent-team/10-review/code-review.md`(Thomas, 20건) · `.agent-team/11-qa/qa-summary.md`(Matthias) · `.agent-team/09-docs/design-vs-impl-gaps.md`(Timothy)를 먼저 읽었다. 이미 나온 결함은 재확인만 표시하고, 보안 관점에서 새로 더할 것이 있을 때만 상세히 썼다.

---

## 0. 경영진 요약

| 심각도 | 건수 |
|---|---|
| Medium (CVSS 5.0~6.9) | 4 (F1 · F2 · F3 · F8) |
| Low / Informational | 4 (F4 · F5 · F6 · F7) |
| **Critical / High** | **0** |

> **개정 이력**: 리드(Paul)가 M4·M5 를 직접 실행 검증한 뒤 "변조 탐지가 침묵한다"는 관점으로 보안 재평가를 요청해 §1.4(F8, M4 재평가)를 신규 추가하고 §2 F5(M5 재평가)를 실측으로 보강했다. **리드 메시지의 수치 하나(오늘 미결 "2건")는 직접 재실행한 결과 실제 값(0건)과 달라 정정해 반영했다** — 아래 F8에 재현 근거와 함께 명시한다.

**이 시스템의 위협면은 좁다.** HTTP API가 없고, 인증·세션·사용자 입력 폼이 없으며, 외부 네트워크 입력을 받지 않는다. 실행은 로컬 CLI(`python3 -m src.measurement.publish`)와 로컬 dev/start 서버뿐이다. 그래서 OWASP Top 10을 기계적으로 대입하면 SQL Injection·SSRF·CSRF·인증 우회 대부분이 "해당 없음"이 되는 것이 정상이며, 억지로 채우지 않았다(§5 해당 없음 목록 참조).

실제로 의미 있는 위협면은 **파일 시스템 경계**(`results/`↔`data/hidden/`)와 **공급망**이었다. 결론부터: 공급망은 깨끗하다(§4) — 고정된 모든 의존성(Python 4종·npm 445개)을 GitHub Advisory Database와 `npm audit`으로 개별 대조했고 적용 가능한 취약점 0건이다. 파일 경계는 문자열 검사만으로는 완전하지 않다 — **심볼릭 링크를 따라가는 경로로 두 곳(읽기 측 대시보드, 쓰기 측 게시 파이프라인)에서 격리가 뚫리는 것을 직접 재현했다**(F1, F3). 다만 둘 다 공격자가 이미 로컬에 동등한 쓰기 권한을 가져야 발동하므로 — 이 시스템에 없는 원격/네트워크 공격 표면을 만들어내지는 않는다 — Critical이 아니라 Medium으로 매겼다.

추가로 대시보드가 기본 설정으로 모든 네트워크 인터페이스에 바인딩되는 것을 실측했다(F2) — 인증이 전혀 없는 앱이므로 배포 환경에 따라 노출 범위가 달라진다. Thomas가 코드 품질 관점에서 major로 분류한 두 건(M1 manifest 미검증, M5 `NameError`)은 보안 관점에서 재평가했고, **둘 다 우회가 아니라 fail-closed가 유지된다**는 점을 확인해 정보성으로 재분류했다(F5, F6) — 이것이 이번 감사가 코드 리뷰에 더한 값이다.

---

## 1. Medium 등급 — 직접 재현으로 확인

### F1 · 대시보드 읽기 경로가 심볼릭 링크를 따라가 `results/` 격리를 우회한다

| | |
|---|---|
| 파일 | `dashboard/src/lib/artifacts/paths.ts:98-118` (`resolveArtifactPath`) |
| CWE | CWE-59 (Improper Link Resolution Before File Access) |
| CVSS 3.1 | **6.5 (Medium)** — `AV:L/AC:L/PR:L/UI:N/S:C/C:H/I:N/A:N` |

**요지.** `resolveArtifactPath()`는 절대경로·`..` 이스케이프를 문자열/`path.resolve()` 수준에서 정확히 막는다(아래 §5.1에서 정상 작동을 직접 검증). 그러나 이 검사는 **문자열 경로에 대한 검사일 뿐, 파일 시스템의 실제 대상(realpath)을 확인하지 않는다.** `readFile()`은 기본적으로 심볼릭 링크를 따라간다. 따라서 `results/` 아래(또는 `results/measurement/` 아래) 심볼릭 링크가 하나라도 존재하고 그것이 `data/hidden/`·`data/ground_truth/`·저장소 밖 임의 파일을 가리키면, 문자열 검사는 통과하고 실제로는 그 파일의 내용이 그대로 반환된다.

**재현(직접 실행, 요약 로그).**
```
$ ln -s .../secret_area/secret.json .../fake_results/measurement/evil_symlink.json
$ AIROI_RESULTS_DIR=.../fake_results node -e "
    const p = resolveArtifactPath('results/measurement/evil_symlink.json');
    // 문자열 검사 통과 — target은 여전히 RESULTS_DIR 하위 문자열이다
    console.log(await readFile(p, 'utf8'));
  "
resolved path (string-check passed): .../fake_results/measurement/evil_symlink.json
ACTUAL FILE CONTENT READ: {"hidden":"TOP SECRET HIDDEN TRAIT DATA"}
```
같은 스크립트로 일반적인 `..` 트래버설·절대경로·대소문자 우회·`%2e%2e` URL 인코딩 8종은 **전부 정상 차단**됨을 함께 확인했다(§5.1) — 이 코드가 부주의한 것이 아니라, realpath 검증이라는 한 겹만 빠져 있다.

**실제 위험도 판단.** 이 앱은 HTTP API가 없고 `index.json`(및 그것이 가리키는 파일들)은 로컬 `python3 -m src.measurement.publish` 파이프라인만 쓴다. `results/`에 심볼릭 링크를 심으려면 공격자가 **이미 그 디렉터리에 대한 로컬 쓰기 권한**을 가져야 하고, 그 권한은 측정 계층 자체를 실행할 권한과 사실상 동급이다. 즉 원격/네트워크 공격자가 이 경로로 `data/hidden/`을 훔쳐볼 방법은 없다. 그러나 (a) `dashboard/AGENTS.md`가 이 파일을 "이 앱에서 유일한 파일 읽기 관문"으로 명시하고 DB-014 격리의 마지막 방어선으로 삼고 있고, (b) `tests/test_isolation.py`가 `dashboard/`를 검사하지 않는다는 사실이 이미 문서화되어 있어(D-22 보류) 이 파일이 사실상 유일한 런타임 방어이므로, 심층방어 관점에서 반드시 닫아야 할 구멍으로 본다.

**수정안.**
```ts
import { realpathSync } from "node:fs";
// resolve() 이후, 최종 사용 직전에 추가
const real = realpathSync(target);          // 심볼릭 링크를 실제로 해석
const realBase = realpathSync(RESULTS_DIR); // 매 호출 캐시 가능
if (real !== realBase && !real.startsWith(realBase + sep)) {
  throw new IsolationError(`허용 경로 밖 접근(심볼릭 링크 우회 시도): ${relative}`);
}
```
파일이 존재하지 않는 정상 케이스(ENOENT)는 `realpathSync`가 던지므로 `read.ts`의 기존 ENOENT 처리 분기와 순서를 맞춰야 한다(먼저 `lstat`으로 존재를 확인한 뒤 심볼릭 링크 여부만 검사하는 방식도 가능).

**검증 방법.** 수정 후 위 재현 스크립트를 다시 실행해 `IsolationError`가 던져지는지 확인한다.

---

### F2 · 인증 없는 대시보드가 기본값으로 모든 네트워크 인터페이스에 바인딩된다

| | |
|---|---|
| 파일 | `dashboard/package.json`(`"dev": "next dev --port 3001"`, `"start": "next start --port 3001"`) |
| CWE | CWE-1188 (Insecure Default Initialization of Resource), CWE-306 관련 |
| CVSS 3.1 | **4.3 (Medium-Low)** — `AV:A/AC:L/PR:N/UI:N/S:U/C:L/I:N/A:N` (방화벽 없는 공인 호스트에 배포될 경우 `AV:N` 기준 **5.3**로 상승) |

**요지.** `dashboard/AGENTS.md`는 "API 서버를 두지 않는다", "인증·세션이 없다"를 설계로 명시한다 — 이는 로컬 전용 사용을 전제로 한 합리적 결정이다. 그런데 `-H`(hostname) 옵션 없이 실행되는 `next dev`/`next start`는 Next.js 기본값대로 **`0.0.0.0`(모든 인터페이스)에 바인딩**된다. 즉 "로컬에서만 접근 가능"이라는 설계 전제가 실행 스크립트로 강제되지 않는다.

**재현(직접 실행).**
```
$ npm run start -- --port 3999   # AIROI_RESULTS_DIR=/tmp/fake_results_empty
▲ Next.js 16.3.4
- Local:         http://localhost:3999
- Network:       http://192.168.0.63:3999      ← Next.js 자신이 LAN 노출을 알린다
✓ Ready in 85ms

$ lsof -iTCP -sTCP:LISTEN -P | grep 3999
node   ...   TCP *:3999 (LISTEN)                ← 와일드카드 바인딩 확인
```
`node_modules/next/dist/server/lib/start-server.js:278`도 `hostname`이 없을 때 실제 바인딩 주소가 `0.0.0.0`임을 전제로 표시 문자열만 `localhost`로 바꿔 보여준다는 것을 소스에서 확인했다 — 화면 출력과 실제 바인딩이 다르다는 뜻이다.

**실제 위험도 판단.** 인증이 전혀 없으므로 이 포트에 닿을 수 있는 누구나 내부 KPI·경제 지표(기여이익·AI ROI 추정치)·거부 사유 요약을 볼 수 있다(단, `offending_values` 자체는 §5.4에서 확인했듯 렌더링되지 않는다). 같은 사무실/가정 LAN에서 실행하는 일반적 사용에서는 노출 범위가 그 네트워크로 제한되지만, 이 저장소 어디에도 "로컬호스트에서만 실행하라"는 명시적 경고나 강제가 없어 향후 누군가 CI 러너·공유 서버·클라우드 VM에서 `npm run dev`를 그대로 돌리면 방화벽 설정에 전적으로 의존하게 된다.

**수정안.**
```json
"dev": "next dev --port 3001 -H 127.0.0.1",
"start": "next start --port 3001 -H 127.0.0.1"
```
LAN 공유가 실제로 필요한 사용 사례가 생기면 그때 별도 스크립트(`dev:lan`)로 명시적으로 분리한다.

**검증 방법.** 수정 후 동일하게 `lsof -iTCP -sTCP:LISTEN` 실행 시 `127.0.0.1:PORT`만 보이고 `*:PORT`가 사라지는지 확인한다.

---

### F3 · 게시 파이프라인의 staging 디렉터리 경로가 예측 가능하고 심볼릭 링크 선점에 취약하다

| | |
|---|---|
| 파일 | `src/measurement/publish.py:1453-1455`(`_reset`), 사용처 `:1340-1341`, 승격 루프 `:1393-1396` |
| CWE | CWE-59, CWE-377 (Insecure Temporary File) |
| CVSS 3.1 | **5.1 (Medium)** — `AV:L/AC:L/PR:L/UI:N/S:C/C:N/I:L/A:L` |

**요지.** `publish()`는 `<output_root>.staging`(예: `results.staging`)이라는 **고정·예측 가능한 경로**에 중간 산출물을 쓴 뒤 `os.replace()`로 `results/`에 승격한다. `_reset()`은 `shutil.rmtree(path, ignore_errors=True)` 다음 `path.mkdir(parents=True, exist_ok=True)`만 한다 — 이 경로에 **사전에 심볼릭 링크가 심어져 있어도 검출·거부하지 않는다.**

**재현(표준 라이브러리만으로 직접 실행, `_reset()` 로직을 그대로 복제해 검증).**
```
Before _reset(): staging is symlink -> True -> points to .../attacker_dir
After  _reset(): staging is symlink -> True      ← rmtree+mkdir이 링크를 그대로 둔다
Attacker file survived rmtree? True
Writing through 'staging' now writes into: .../attacker_dir/measurement/kpi_report.json
Real attacker_dir file content now (simulated legit write): {"legit": "value"}
output_root now contains: ['measurement/evil_extra.json', 'measurement/kpi_report.json']
evil_extra.json ended up in output_root: True   ← 무관한 공격자 파일이 results/ 로 승격됨
```
즉 (1) 정상 게시 내용이 공격자가 지정한 디렉터리로 우회 기록되고, (2) 공격자가 미리 그 디렉터리에 심어 둔 **이번 실행과 무관한 임의 `.json` 파일**이 `rglob("*.json")` + `os.replace()` 단계에서 그대로 `results/`까지 승격된다.

**실제 위험도 판단.** 공격자는 `python3 -m src.measurement.publish` 실행 **이전에** 저장소 루트(정확히는 `output_root`의 부모 디렉터리)에 쓰기 권한을 이미 가지고 있어야 한다 — 이는 측정 계층을 직접 실행할 권한과 사실상 동급이라 원격 공격 표면을 새로 만들지는 않는다. 또한 현재 대시보드는 `index.json.artifacts[]`에 명시된 경로만 읽으므로(§5.1의 읽기 계층 검증), 승격된 무관한 파일이 자동으로 화면에 반영되지는 않는다 — 다만 `index.json` 자체도 최종적으로 이 디렉터리 트리 안에 쓰이므로, **레이스 타이밍이 정확히 맞으면 진짜 게시물 대신 공격자 콘텐츠가 같은 파일명으로 남을 가능성**은 남는다(본 감사는 그 정밀 타이밍 경쟁까지는 재현하지 않았다 — 사전 심볼릭 링크 선점만으로 충분히 결함이 성립함을 보였다).

**수정안.**
1. `_reset()` 진입 시 `if path.is_symlink(): raise PublishError(...)`로 명시적으로 거부한다.
2. 더 근본적으로는 `tempfile.mkdtemp(dir=output_root.parent)`로 매 실행 예측 불가능한 이름을 쓰고, 완료 후 원자적으로 옮긴다.
3. 승격 루프를 `rglob("*.json")` 전체가 아니라 **이번 실행이 실제로 쓴 파일 이름의 allowlist**로 제한한다 — `bodies.items()`가 이미 그 목록을 알고 있다.

**검증 방법.** 위 재현 스크립트를 실제 `_reset()`/승격 루프 함수를 import해 다시 실행하고, 수정 후 심볼릭 링크가 명시적 예외로 거부되는지 확인한다.

---

### F8 · GATE 1 변조 경보(`FREEZE_MISMATCH`)가 오늘부터 이미 구조적으로 도달 불가능하다 (Thomas M4 보안 재평가 — 리드 요청)

| | |
|---|---|
| 파일 | `src/measurement/publish.py:262`(`choose_headline_code`), `:1188-1202`(`counts` 조립), `:286-287`(`headline_level`) |
| CWE | CWE-390 (Detection of Error Condition Without Action) · CWE-1023(Incomplete Comparison, `and`가 있어야 할 자리에 독립 조건이어야 함) |
| CVSS 3.1(참고치 — 아래 성격 설명 참조) | **5.6 (Medium)** — `AV:L/AC:L/PR:L/UI:N/S:U/C:N/I:H/A:N` |

**성격에 대한 유보.** 이 결함은 외부에서 트리거하는 고전적 "취약점"이 아니라 **탐지 통제(detective control) 자체의 논리 결함**이다. CVSS는 참고용으로만 제시한다 — 실제 심각도는 "GATE 1 봉인 무결성이 깨졌을 때 대시보드 최상단 배너가 그것을 알리는가"라는 이 프로젝트의 핵심 보증에 대한 것이다.

**Thomas 의 M4(major, 기능 결함)를 그대로 재확인**했다 — `counts` 딕셔너리는 8개 키만 채우고 `freeze_mismatch`를 절대 채우지 않는다(겹 1, 아래에서 직접 재확인). 여기서 **새로 보탠 것은 두 가지**다.

**① `lock_items_pending`의 실제 값을 직접 실행해 확인했다 — 리드 메시지의 수치를 정정한다.**

리드는 "오늘 미결 2건"이라 적었으나, 실제로 `fz.verify()`를 직접 호출하고 저장소에 이미 게시되어 있는 실제 산출물(`results/measurement/index.json`, 2026-09-11 실행분)을 함께 대조한 결과:

```
$ python3 -c "from src.measurement import freeze as fz; ..."
overall: partial · verification: not_run · unmet(G-precondition 미충족) count: 0

$ cat results/measurement/index.json | jq .verdict.counts
{
  "checks_blocked": 1, "checks_not_run": 17, "lock_items_pending": 0,
  "metrics_not_run": 0, "metrics_unavailable": 44, "quality_violations": 0,
  "rejected_events": 0, "schema_gaps": 5
}
```

**`lock_items_pending`은 오늘 실제로 0이다** — G-1~G-16 선행 조건(`GATE1_PRECONDITIONS`) 16종이 전부 `met=True`이기 때문이다. 이 필드의 이름은 "봉인 항목 대기중"처럼 읽히지만 실제로는 **9종 LOCK_ITEMS의 PENDING/PARTIAL 개수가 아니라 G-precondition 미충족 개수**를 센다(`freeze.to_artifact()`의 `unlocked_items` = `verification.unmet`). 이 이름-의미 불일치 자체가 겹 2를 눈에 띄지 않게 만드는 근본 원인 중 하나다 — "미결 항목이 있을 때만 경보한다"는 조건이 실제로는 "**아직 개발 중이라 선행 조건을 다 못 채웠을 때만** 경보한다"는 의미가 되어 버린다.

**② `and` 로직이 오늘 이미 죽어 있음을 실제 함수·실제 데이터로 재현했다 — "미래 GATE 2 문제"가 아니라 "지금부터 문제".**

Thomas의 코드 리뷰는 이 결함을 "GATE 2에서 완전 봉인되는 순간 조용히 죽는다"로 그렸다. 실제로 실행해 보니 **더 나쁘다** — 별도로 만든 예시 딕셔너리가 아니라 저장소에 실제로 게시된 오늘의 `counts`를 가져와 실제 `choose_headline_code()`(수정 없이 원본 함수 그대로)에 통과시켰다:

```python
from src.measurement.publish import choose_headline_code, headline_level
real_counts = <오늘 게시된 results/measurement/index.json 의 counts>

# 시나리오 B — Thomas 의 "명백한 수정"(freeze_mismatch 키만 채운다)을 적용하고
#             다른 위반은 없다고 가정한 뒤, 실제 오늘 데이터의 lock_items_pending(=0)은 그대로 둔다
counts_b = {**real_counts, "freeze_mismatch": 1, "quality_violations": 0, "rejected_events": 0}
choose_headline_code(counts_b)   # → 'CHECKS_NOT_RUN' (attention) — FREEZE_MISMATCH 아님!

# 시나리오 C — lock_items_pending 도 인위로 1로 만들어야만 비로소 작동
counts_c = {**counts_b, "lock_items_pending": 1}
choose_headline_code(counts_c)   # → 'FREEZE_MISMATCH' (violation) — 이 조합에서만 성립
```

**결론: Thomas가 제안한 "겹 1만 고치는 명백한 수정"(`counts["freeze_mismatch"]`를 채워 넣는 것)을 오늘 그대로 적용해도, 실제 게시되는 데이터로는 여전히 `FREEZE_MISMATCH`가 뜨지 않는다** — `lock_items_pending`이 오늘 이미 0이기 때문이다. 이것이 리드가 경고한 "한 겹만 고치면 더 나빠진다"의 정확한 메커니즘이다: 수정한 사람은 (겹 1이 고쳐졌으니) 코드가 옳아 보인다고 판단하고 넘어가지만, **실제 실행 결과는 오늘도, 그리고 G-precondition이 전부 충족된 이후 내내(=거의 항상), 변경되지 않는다.** 겹 2(`and`)가 살아 있는 한 이 경보는 "G-precondition이 아직 미완인 드문 개발 중 시점에 우연히 변조까지 겹치는" 사실상 도달 불가능한 조합에서만 작동한다 — 이는 "GATE 2 이후에만 위험"이 아니라 **설계된 순간부터 지금까지 단 한 번도 유효하게 작동한 적이 없다(작동할 수 있는 실측 조건이 존재한 적이 없다)**는 뜻이다.

**Thomas가 이미 확인한 완화 사실(재확인, 축소 없이 인용)**: `freeze_status.json`(V6, `/freeze` 화면)에는 `verify()`가 계산한 정확한 `verification: "mismatch"`가 그대로 실린다 — 상세 화면까지 파고 들어가면 진실을 볼 수 있다. 뚫린 것은 **"한눈에 보이는 자리"**(대시보드 최상단 배너, `index.json.verdict`)뿐이다. 그러나 이 프로젝트의 설계 철학 자체가 "그 한 줄이 전부 답한다"는 헤드라인 코드 우선순위 체계이므로(§DB-012 관련 문서), 상세 화면까지 확인하는 사람만 진실을 본다는 것은 이 통제의 실효성이 사실상 없는 것과 같다.

**failure_scenario.** GATE 2에서 실제로 완전 봉인(`LOCKED` 9/9)에 도달한 뒤 봉인된 정본 파일(예: `schema.py`) 중 하나가 몰래(또는 실수로) 수정되면: `freeze.verify()`는 정확히 `verification: "mismatch"`를 계산해 `freeze_status.json`에 담지만, `/`(대시보드 첫 화면)와 `index.json.verdict.headline_code`는 — Thomas의 제안대로 겹 1만 고쳐져 있다면 — **`ALL_CLEAR`/`ok`(초록, "이상 없음")로 표시된다.** 이 프로젝트의 North Star(AI ROI 측정)가 의존하는 데이터 계보 무결성이 깨졌는데, 그 사실을 확인하려면 아무도 굳이 열어보지 않을 `/freeze` 세부 화면까지 찾아가야 한다.

**수정안(겹 2건을 함께 고쳐야 한다 — 하나만 고치면 위 시나리오가 재발한다).**
1. `build_index()`에서 `counts["freeze_mismatch"] = 1 if freeze.get("verification") == "mismatch" else 0`으로 겹 1을 채운다(Thomas 권고와 동일).
2. **`choose_headline_code()`의 262행 조건에서 `lock_items_pending`을 제거하고 `freeze_mismatch` 단독 조건으로 바꾼다** — 봉인 대상이 변경됐다는 사실은 미결 항목 개수와 무관하게 그 자체로 최우선 경보 사유다. `and`를 쓴 원래 의도(아마도 "아직 아무것도 Lock되지 않았으면 mismatch가 의미 없다"는 생각)가 있었다면, 그 조건은 `lock_items_pending`이 아니라 **LOCKED 상태인 LOCK_ITEMS가 1개 이상 존재하는지**로 정확히 표현해야 한다 — 지금의 프록시는 완전히 다른 것(G-precondition 완료 여부)을 재는 필드라 의도와 무관하게 작동한다.
3. `lock_items_pending`이라는 필드명 자체를 실제 의미(`unmet_preconditions` 등)로 바꾸는 것을 권고한다 — 이름과 의미의 불일치가 이번 결함을 눈에 띄지 않게 만든 근본 원인 중 하나였다.

**검증 방법.** 수정 후 위 세 시나리오(A/B/C)를 실제 `choose_headline_code()`로 다시 실행해, `freeze_mismatch=1`이면 `lock_items_pending` 값과 무관하게 항상 `FREEZE_MISMATCH`가 선택되는지 확인한다. 이어서 `build_index()` 전체를 손상된 정본 파일 해시로 end-to-end 실행해(Thomas가 이미 권고한 통합 테스트) `index.json.verdict.headline_code`가 실제로 `FREEZE_MISMATCH`로 뜨는지까지 확인한다 — 단위별로 격리된 테스트만으로는 이번에 발견된 것과 같은 조합 결함을 다시 놓칠 수 있다.

---

## 2. Low / Informational

### F4 · GitHub Dependabot alerts · Secret scanning이 저장소에서 비활성 상태다

```
$ gh api repos/72offsuit/AI_ROI --jq '{private, security_and_analysis}'
{"private": true, "security_and_analysis": null}
$ gh api repos/72offsuit/AI_ROI/dependabot/alerts
{"message":"Dependabot alerts are disabled for this repository.", "status":"403"}
$ gh api repos/72offsuit/AI_ROI/secret-scanning/alerts
{"message":"Secret scanning is disabled on this repository.", "status":"404"}
```
현재 고정 의존성에는 알려진 취약점이 없다(§4에서 개별 검증) — 이것은 "지금 안전하다"이지 "앞으로도 자동으로 안전하다"가 아니다. 두 기능 모두 **private 저장소에서 무료로 켤 수 있다**(브랜치 보호처럼 GitHub Pro가 필요하지 않다 — 브랜치 보호 API는 실제로 `403 Upgrade to GitHub Pro`를 반환해 별개 사안임을 확인했다). **권고:** 저장소 Settings → Security 에서 두 기능을 켠다. 코드 변경 불필요.

### F5 · `freeze.py`의 `NameError` — 봉인 변조 방어선이 크래시하며 탬퍼 신호를 잃는다 (Thomas M5 재확인 — 보안 관점 재평가, 리드 요청으로 실측 보강)

| | |
|---|---|
| 파일 | `src/measurement/freeze.py:466`(raise 지점), `:30-38`(import 목록), `src/measurement/publish.py:1586`(`except MeasurementError`) |
| CWE | CWE-390(Detection of Error Condition Without Action) · CWE-703(Improper Check for Unusual or Exceptional Conditions) |
| 심각도 | **Low(정보성에서 상향)** — 우회는 없으나 탬퍼-경보의 진단 품질이 실측으로 확인된 것보다 더 나쁘다 |

Thomas의 코드 리뷰가 이미 major로 분류했다(`config/gate1_lock.yaml`의 `canonical_files`가 매핑이 아닐 때 `ConfigError` 미임포트로 `NameError`). 직접 grep으로 재확인했다 — `freeze.py:30-38`에 `FreezeViolation`만 import되어 있고 `ConfigError`는 없으며, `:466`에서 `raise ConfigError(...)`를 호출한다.

**보안 관점에서 확인해야 할 질문은 "검증 우회로 이어지는가"였다. 결론은 여전히 "아니다"** — 이 결론 자체는 바뀌지 않는다. `NameError`도 처리되지 않은 예외이므로 `verify()` 실행을 즉시 중단시키고, 손상된 `gate1_lock.yaml`이 "검증 통과"로 조용히 받아들여지는 경로는 없다.

**리드 요청에 따라 실제로 end-to-end 재현해 진단 품질 저하를 정량적으로 확인했다 — 이것이 이번에 새로 더한 것이다.** 실제 `config/gate1_lock.yaml`을 건드리지 않고, `freeze.load_record()`만 손상된 구조(`canonical_files`가 리스트)를 반환하도록 메모리에서 치환한 뒤 **`main()`(실제 CLI 진입점)을 그대로 호출**했다:

```
$ python3 -c "... pub.main(['--source', 'data/raw']) ..."   # PyYAML 6.0.3 설치된 venv
Traceback (most recent call last):
  File ".../publish.py", line 1582, in main
    outcome = publish(...)
  File ".../publish.py", line 1337, in publish
    "freeze_status": build_freeze_status(),
  File ".../publish.py", line 1162, in build_freeze_status
    verification = fz.verify(...)
  File ".../freeze.py", line 466, in verify
    raise ConfigError(
          ^^^^^^^^^^^
NameError: name 'ConfigError' is not defined
```

이 트레이스백은 **`main()`을 완전히 뚫고 나온다** — `publish.py:1586`의 `except MeasurementError as error:`가 `NameError`를 잡지 못하기 때문이다(직접 확인: `isinstance(NameError(), MeasurementError)` → `False`). 그 결과:

1. 의도된 메시지("`게시 실패: canonical_files 가 매핑이 아니다 — 경로: sha256 형태여야 한다`")는 **아무에게도 도달하지 않는다** — NFR-006이 요구하는 무엇이·왜·해결법 3요소가 전부 사라지고, 파이썬 내부 이름 오류처럼 보이는 원시 스택 트레이스만 남는다. 이걸 본 운영자는 "GATE 1 봉인 무결성이 깨졌다"가 아니라 "코드에 import 버그가 있다"로 오인하기 쉽다 — **탬퍼링 신호가 프로그래밍 실수 신호로 위장된다.**
2. `error.exit_code`(정의대로라면 `ConfigError`의 5)가 아니라 **파이썬 기본 미처리 예외 종료 코드(1)**로 끝난다. `errors.py`가 예외별로 종료 코드를 구분해 둔 이유(m1, Thomas 기록) 자체가 무의미해진다 — 자동화가 "종료 코드 5 = config 손상"으로 분기하는 미래 시나리오를 상정했다면 그 분기가 작동하지 않는다.

**CWE 재평가.** 이 결함은 "예외를 안 던진다"(CWE-248, 최초 분류)가 아니라 **"올바른 예외 타입을 던지지 못해 상위의 구조화된 처리·분류 체계에서 이탈한다"**는 성격이다 — CWE-390(오류 조건을 탐지했으나 의도한 조치로 이어지지 않음)과 CWE-703(예외적 조건에 대한 부적절한 처리)이 더 정확한 매핑이다.

**여전히 유지되는 결론:** fail-closed는 유지된다 — 프로세스가 죽으므로 게시물이 나오지 않고, 대시보드에는 손상 이전 상태(또는 미게시 안내)만 남을 뿐 "검증 통과"라는 거짓 신호는 없다. **그래서 이 결함은 F1·F3·F8과 달리 Medium이 아니라 Low다** — 다만 리드가 지적한 대로 "방어 코드가 정확히 방어가 필요한 순간에 무너진다"는 역설, 그리고 진단 품질이 실측으로 확인된 것보다 나쁘다는 점(원시 트레이스백, 잘못된 종료 코드)은 M5의 major 등급(코드 품질)과 별개로 보안 문서에도 남길 가치가 있다고 판단해 등급을 정보성에서 Low로 상향했다.

**수정안.** Thomas의 권고(import 추가)에 다음을 더한다: `verify()`의 이 방어 코드가 실제로 `ConfigError`를 던지고 `main()`이 그것을 잡아 구조화된 메시지 + exit_code 5로 종료하는지까지 검증하는 테스트를 추가한다(단위 테스트가 `verify()`만 격리해서 부르면 이번처럼 `main()` 레벨의 예외 전파 문제를 놓친다 — F8과 같은 교훈).

### F6 · `manifest.json` 파싱에 예외 처리가 없다 (Thomas M1 재확인 — 보안 관점 재평가)

Thomas의 M1(가장 중요한 major)은 `manifest.get(key, 0) or 0` 패턴이 **유효한 JSON인데 키가 없거나 `null`인 경우** 결손을 조용히 0으로 바꾸는 것을 지적했다. 이번 감사는 그 바로 앞 단계 — `_read_manifest()`의 `json.loads(path.read_text(...))`(`publish.py:1458-1466`) — 를 확인했다.

**보안 관점에서 더한 것:** M1이 지목한 원인(`sink.py:266`의 비원자적 `write_text()`로 인한 잘린 manifest)이 실제로 발생하면, 그 결과물은 대개 **유효한 JSON이 아니라 잘린 문자열**이다(예: `{"rows": 12, "rejected"`처럼 중간에 끊김). 이 경우 M1이 그린 "조용한 0-채움" 경로가 아니라 **처리되지 않은 `json.JSONDecodeError`로 `publish()` 전체가 비정상 종료**된다 — 정보 노출이나 우회가 아니라 가용성 문제(예고 없는 크래시)다. `PublishError`/`ContractViolation` 같은 구조화된 예외로 감싸여 있지 않아 운영자에게 원시 스택 트레이스만 남는다. **권고:** M1 수정(매니페스트 스키마 도입)과 함께, 초기 `json.loads()` 호출을 `try/except json.JSONDecodeError`로 감싸 NFR-006 형식의 메시지를 내도록 한다.

### F7 · CI 서드파티 액션이 커밋 SHA가 아닌 태그로 고정되어 있다

`actions/checkout@v4`, `actions/setup-python@v5` (두 워크플로우 모두). GitHub 공식 액션이고 `permissions: contents: read`만 부여되며 `pull_request`(`pull_request_target`이 아님)로 트리거되고 시크릿을 쓰지 않아 실질 위험은 낮다 — OpenSSF Scorecard의 Pinned-Dependencies 관행에 맞춰 커밋 SHA 고정을 권고 수준으로 남긴다.

---

## 3. 팀 리드가 특별히 지목한 항목 — 결과

| 지목 항목 | 결과 |
|---|---|
| `paths.ts` 경로 이탈 — `..`·URL 인코딩·절대경로·대소문자 우회 | **8종 시도, 정상 차단 전부 확인**(§1 F1 참조, 표는 아래 §5.1) |
| `paths.ts` 경로 이탈 — 심볼릭 링크 | **우회 확인 — F1** |
| 공급망(`pyarrow`·`PyYAML`·`jsonschema`·`referencing`·npm 445개) | **알려진 취약점 0건**(§4) |
| 역직렬화(`yaml.safe_load` vs `yaml.load`) | **`safe_load`만 사용, `tests/test_neutrality.py`가 AST 기반으로 강제함을 확인**(§5.2) |
| 비밀값 노출 | **없음**(§5.3) |
| 정보 노출 — `rejection_report`의 `offending_values` | **차단됨, 계약→타입→화면 3중 확인**(§5.4) |
| CI 보안 — 권한·서드파티 액션 핀 | **권한은 최소(`contents: read`), 액션 핀은 태그 — F7** |
| M1 재평가 | **완료 — F6, fail-closed 유지 확인** |
| M5 재평가 | **완료 — F5, fail-closed 유지하나 탬퍼 신호 품질 저하를 실측(end-to-end 재현)으로 확인, 등급 Low로 상향** |
| M4 재평가(리드 추가 요청, 실행 검증분) | **완료 — F8, 겹 2건 모두 실제 함수·실제 데이터로 재현. 리드가 언급한 수치("미결 2건")는 실측 결과 0건으로 정정. "GATE 2 이후 문제"가 아니라 "설계 시점부터 도달 불가능했던 조합"임을 확인 — Medium으로 상향(우회가 아니라 탐지 통제 자체의 무효화)** |

---

## 4. 공급망 — 개별 검증 기록

`gh api /advisories`로 GitHub Advisory Database를 직접 조회하고, npm 두 저장소는 `npm audit`(레지스트리 실시간 조회)로 교차 검증했다. 추정으로 심각도를 매기지 않기 위해 **범위 문자열을 직접 대조**했다.

| 패키지 | 고정 버전 | 조회한 GHSA 건수 | 현재 버전에 적용되는 것 |
|---|---|---|---|
| pyarrow | 25.0.1 | 4건(최고 critical, `<14.0.1`) | **0건** — 전부 범위 상한이 25.0.1보다 낮음 |
| PyYAML | 6.0.3 | 4건(전부 critical, 최고 상한 `<5.4`) | **0건** |
| jsonschema | 4.26.0 | 0건 | 해당 없음 |
| referencing | 0.37.0 | 0건 | 해당 없음 |
| next | 16.3.4 | 67건 검토, 최신 critical 2건(RCE, `<16.3.3`) | **0건** — 16.3.4는 그 상한보다 위(패치됨) |
| react / react-dom | 19.2.8 / 19.2.9 | 3건(전부 0.x~16.4.x 시대 XSS) | **0건** |
| playwright | 1.63.0 | 1건(`<1.55.1`, SSL 인증서 미검증) | **0건** |

```
$ (cd dashboard && npm audit --json) | jq .metadata.vulnerabilities
{"info":0,"low":0,"moderate":0,"high":0,"critical":0,"total":0}   # 442 packages

$ (cd e2e && npm audit --json) | jq .metadata.vulnerabilities
{"info":0,"low":0,"moderate":0,"high":0,"critical":0,"total":0}   # 3 packages
```

`config_loader.py` 독트링이 인용한 `CVE-2026-24009`(docling-core, PyYAML 안전하지 않은 사용 경유 RCE)가 **실재하는 최신 advisory**임을 `gh api`로 확인했다(`GHSA-vqxf-v2gg-x3hc`) — 인용이 날조가 아니라 정확하다는 뜻이다. `PyYAML==6.0.3`도 PyPI에 실재하는 배포 버전임을 확인했다(가상의 미래 버전 핀이 아니다).

**결론: 공급망에서 발견 0건.** F4(Dependabot·Secret scanning 비활성)만 프로세스 항목으로 남는다.

---

## 5. 확인했으나 문제 없음 — 근거를 남긴다

### 5.1 경로 이탈 — 직접 실행한 8종 우회 시도

`paths.ts`의 `resolveArtifactPath()` 로직을 Node 표준 라이브러리만으로 그대로 복제해 실행했다(로직은 원본과 동일, `RESULTS_DIR=/tmp/fake_results`).

| 시도 | 결과 |
|---|---|
| `/etc/passwd`(절대경로) | `BLOCKED` |
| `data/processed/x.json` | `BLOCKED`(C1 미게시로 명시적 거부) |
| `not_results/x.json`(접두사 없음) | `BLOCKED` |
| `results/../../data/hidden/secret.json` | `BLOCKED` |
| `results/measurement/../../../../../../etc/passwd` | `BLOCKED` |
| `results//..//..//data/hidden/secret.json` | `BLOCKED` |
| `RESULTS/measurement/...`(대문자) | `BLOCKED`(접두사 대소문자 정확 일치 요구) |
| `results/%2e%2e/%2e%2e/data/hidden/secret.json`(URL 인코딩) | **문자열 그대로 리터럴 디렉터리명으로 처리되어 트래버설 아님** — 존재하지 않는 경로라 실제로는 ENOENT |
| **심볼릭 링크** | **우회됨 — F1로 보고** |

### 5.2 `yaml.safe_load()` 전용 사용

`config_loader.py`가 저장소 유일한 `import yaml` 지점임을 확인했고, `tests/test_neutrality.py:301-353`이 **grep이 아니라 AST 파싱**으로 (a) `import yaml`이 이 파일에만 있는지, (b) `FullLoader`·`UnsafeLoader`·`unsafe_load`·`full_load`·`yaml.load(...)`가 소스 전체에 0건인지를 강제하는 것을 직접 읽고 확인했다. 속성 접근(`yaml.FullLoader`)과 호출(`yaml.load(...)`) 양쪽 다 별도 AST 노드 타입으로 잡는 구현이라 단순 문자열 우연 매치가 아니다.

### 5.3 비밀값 노출

- `git ls-files`로 추적 파일 전체에서 AWS 키·GitHub 토큰·PEM 개인키·Slack 토큰 패턴 검색 — **0건**
- `git log --all -p`로 `.env`·`.pem`·`*credentials*` 이력 검색 — **0건**
- `.agent-team/_state/audit-log.jsonl.audit-key`(32바이트 대칭키)·`.audit-log.jsonl.lock`이 디스크에 존재하지만 `git check-ignore -v`로 `.gitignore:31-32`에 의해 **추적 대상에서 확실히 제외됨**을 확인했고, 키 파일 권한이 `-rw-------`(600, 소유자 전용)로 적절히 제한되어 있음을 확인했다
- `secrets.token_hex(4)`(`contracts.py:78`)는 `run_id` 충돌 회피용이며 보안 목적 난수가 아님을 독트링이 명시하고 실제 용례도 일치한다

### 5.4 `rejection_report`의 `offending_values` — 계약→타입→화면 3중 차단

- 계약: `rejection_report.schema.json`이 `offending_values`를 DATA-003 22컬럼 화이트리스트로 제한(Thomas가 이미 확인)
- 타입: `dashboard/src/lib/artifacts/types.ts:320-337`의 `RejectionSample` 인터페이스에 `offending_values` 필드 자체가 **없음** — `offending_fields?: string[]`(이름만)만 존재. TypeScript 컴파일 타임에 애초에 그릴 수 없는 구조임을 직접 읽어 확인했다
- 화면: `dashboard/src/app/(observability)/rejections/page.tsx:1-16, 157-164`가 "SECURITY BOUNDARY" 주석과 함께 `offending_fields`(이름만)만 렌더링하고, 파일 헤더에 값이 아닌 이름만 표시하는 이유를 명시한다

세 층 모두 직접 읽어 확인했다 — 값이 새어나갈 자리가 구조적으로 없다.

### 5.5 명령 실행 · 역직렬화 위험 패턴

`subprocess`는 저장소 전체에서 `contracts.py:260`(`repo_commit()`) 한 곳뿐이며 고정 argv 리스트(`["git", "rev-parse", "HEAD"]`)에 `shell=True` 없이 호출되어 커맨드 인젝션 표면이 없다. `eval`·`exec`·`pickle`·`marshal.load`·`os.system`·`__import__`·`shell=True`를 저장소 전체에서 grep — **0건**.

### 5.6 대시보드 XSS 표면

`dangerouslySetInnerHTML`·`innerHTML`·`document.write`·`eval`·`new Function`을 `dashboard/src` 전체에서 grep — **0건**. 화면에 그려지는 모든 데이터가 로컬 신뢰 파이프라인(`results/`)에서 오고 외부 사용자 입력이 없어 고전적 XSS 위협모델 자체가 약하지만, 안전하지 않은 sink가 코드에 존재하지 않는다는 점은 심층방어로서 확인했다.

### 5.7 CI 권한·트리거

`isolation.yml`·`tests-with-deps.yml` 둘 다 `permissions: contents: read`만 명시(쓰기·시크릿 접근 없음), `pull_request`로 트리거(`pull_request_target` 아님 — 포크 PR이 시크릿·쓰기 토큰을 받지 않는다), `submodules: false`로 private `Plan` 서브모듈 체크아웃 자체를 안 하므로 그 토큰이 CI에 필요하지도 노출되지도 않는다.

---

## 6. 해당 없음 (기계적 대입 대신 이유를 남긴다)

| OWASP/일반 카테고리 | 판정 | 이유 |
|---|---|---|
| SQL Injection | 해당 없음 | DB 자체가 없다(JSON 파일 게시물) |
| 인증/세션/CSRF | 해당 없음(설계상 의도) | 로그인·세션이 없는 로컬 도구. 단 F2가 그 전제의 실행 환경 강제 부재를 지적 |
| SSRF | 해당 없음 | 외부 요청을 만드는 코드가 없다(네트워크 호출 0건, `subprocess`는 로컬 `git`뿐) |
| XXE | 해당 없음 | XML 파서 사용 0건 |
| 역직렬화(pickle 등) | 해당 없음 | `pickle`/`marshal` 사용 0건, YAML은 `safe_load`만(§5.2) |
| CSP/클릭재킹 | 낮은 우선순위 | 인증된 세션·폼이 없어 클릭재킹의 통상적 피해 시나리오(계정 탈취 등)가 성립하지 않는다. 다만 F2로 노출 범위가 넓어지면 재검토 여지가 있다 — 이번 사이클에서는 새 발견으로 올리지 않았다 |

---

## 7. 커버리지 공백 — 정직하게 공개한다

*실패에도 대칭 적용* — 확인하지 않은 것을 확인한 것처럼 적지 않는다.

| 항목 | 상태 | 이유 |
|---|---|---|
| F3(게시 staging 심볼릭 링크)의 **실시간 레이스 타이밍** 재현 | **BLOCKED(부분)** | 사전 심볼릭 링크 선점만으로 결함 성립을 보이는 데 그쳤다. 두 프로세스가 정확한 타이밍에 경쟁하는 시나리오는 재현하지 않았다 — 다만 결함 성립에 그 타이밍이 필요하지 않으므로 결론에는 영향 없음 |
| 실제 OS 계정 간 권한 경계(다른 사용자 계정) 테스트 | **BLOCKED** | 같은 OS 계정 안에서 심볼릭 링크 메커니즘만 검증했다. 별도 계정을 프로비저닝하는 것은 이번 감사 수단 밖이다 |
| GitHub 브랜치 보호 규칙 확인 | **BLOCKED** | `gh api repos/.../branches/main/protection` → `403 Upgrade to GitHub Pro`(private 저장소 + Free 플랜). AGENTS.md가 문서화한 수동 승인 프로세스(L1 권한, merge/force-push/rebase 개별 승인)가 사실상의 보완 통제이나, GitHub 플랫폼 수준에서 강제되는지는 확인 불가 |
| 저장소 push 권한 보유자 전체 목록 | **BLOCKED** | 현재 `gh auth` 토큰에 `admin:repo_hook` 등 필요한 스코프가 없다 |
| npm 445개 패키지 전건에 대한 수동 개별 대조 | **부분** | 상위 직접 의존성(next·react·react-dom·playwright·eslint·typescript)은 GHSA로 개별 대조했고, 전체는 `npm audit`(레지스트리 실시간 조회)로 교차 검증했다 — `npm audit`이 놓칠 수 있는 아직 미등록 취약점까지는 원천적으로 볼 수 없다 |
| `src/measurement/*.py`(약 8,200줄)·`dashboard/src`(약 1,600줄 TS) 전수 라인 단위 재독 | **의도적으로 하지 않음** | Thomas(코드리뷰)·Matthias(QA)가 이미 계약 정확성·0-채움·접근성·doctest 등을 전수 검증했다. 이번 감사는 보안 관점(경로·역직렬화·비밀값·공급망·CI)에 표적화했고 겹치는 것은 재확인만 표시했다 |
| `src/decision/`·`src/simulator/`·`src/diagnostics/`·`src/orchestration/` | **해당 없음(N/A)** | 지침 파일(`AGENTS.md`)만 있고 구현 코드가 아직 없다 — 감사할 대상이 없다 |
| `Ecommerce_Service`·`Plan` 서브모듈 | **범위 밖(지시에 따름)** | 팀 리드 지시로 접근하지 않았다 |
| F2의 실제 운영 배포 이력(공인 IP에서 실제로 노출된 적 있는지) | **확인 불가** | 코드/설정의 기본값 문제를 실측했을 뿐, 실제 사고 이력은 없다(관측된 바 없음) |

---

## 8. 결론

이 시스템의 위협면은 설계상 좁고, 그 좁음이 정직하게 지켜지고 있다 — HTTP API·인증·외부 입력이 실제로 없다는 것을 코드에서 직접 확인했다. 공급망은 개별 검증 결과 완전히 깨끗하다. 발견된 3건의 Medium 등급은 전부 **"파일 시스템 문자열 검사와 실제 파일 시스템 대상(realpath) 사이의 간극"**이라는 같은 모양의 결함이며(F1은 읽기 측, F3은 쓰기 측), 둘 다 공격자가 이미 로컬에 동등한 권한을 가져야 발동해 이 앱에 없는 원격 공격 표면을 새로 만들지는 않는다 — 그러나 `dashboard/AGENTS.md`가 이 파일을 "격리의 마지막 방어선"으로 명시한 만큼 심층방어로서 닫을 가치가 있다. F2(전 인터페이스 바인딩)는 배포 환경에 따라 실제 노출로 이어질 수 있는 설정 기본값 문제로, 수정 비용이 한 줄(`-H 127.0.0.1`)에 불과하다.

Thomas의 M1·M5를 보안 렌즈로 재평가한 결과 **둘 다 검증 우회로 이어지지 않고 fail-closed가 유지됨**을 확인했다 — 코드 품질 문제는 실재하지만 데이터 위조로 이어지는 경로는 없다. 다만 M5는 end-to-end 재현 결과 탬퍼 신호가 원시 트레이스백으로 위장되는 것을 확인해 Low로 상향했다.

**리드가 추가로 요청한 M4 재평가(F8)는 이번 감사에서 가장 중요한 추가 발견이다.** Thomas가 이미 major로 분류한 이 결함을 실제 함수(`choose_headline_code`)와 실제 게시 데이터(`results/measurement/index.json`)로 재현한 결과, "겹 1(누락된 키)만 고치는 명백한 수정"은 **오늘도, 그리고 예측 가능한 미래 내내 여전히 작동하지 않는다**는 것을 확인했다 — `lock_items_pending`이 측정하는 것이 이름과 달리 G-precondition 완료 여부이고, 그 값은 이미 0(전부 충족)이기 때문이다. Thomas의 "GATE 2 이전에만 닫으면 된다"는 시간표 판단에 **정정을 제안한다**: 이 결함은 GATE 2 도달을 기다릴 필요 없이, 겹 1과 겹 2를 **함께** 고쳐야만 실제로 닫힌다. 겹 1만 고치고 넘어가면 "고쳤다"는 확신과 함께 여전히 무효한 통제가 남는, 가장 위험한 종류의 미해결 상태가 된다.

**Critical·High 등급 발견은 0건이다.**
