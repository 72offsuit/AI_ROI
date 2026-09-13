---
story_key: M-05
epic: 범위 M — 측정 계층 (이슈 #42)
issue: "(이슈 없음 — W2 T2.9)"
title: 의존성 매니페스트 도입 — pyarrow · PyYAML + 격리 CI 유지 (가정 A7)
status: done   # W5 Phillip 완료 — T1~T7. D-19 승인으로 tests-with-deps.yml 생겼고 isolation.yml 변경 0줄 확인. A7 판정 7항목 전부
owner: Phillip (W5-A)
phase: "2'"
blocked_by: []
blocks: ["M-07 (#48) DQ-17 해소"]
user_decisions_required: ["D-19", "D-21"]
source_hash: 4ab8babbc1e25356
source_files: 16
---

# M-05 · 의존성 매니페스트 (T2.9 · 가정 A7)

> **이 파일만 읽고 구현한다.** 인용에는 전부 `[Source: 경로#절]` 을 붙였다.

---

# 0. 작업 전 — 매번 확인하는 3줄 *(task-graph §3 T3.2)*

| # | 절대 제약 | 어기면 |
|---|---|---|
| **①** | **git·이슈 권한은 L1(제안만)이다.** commit·push 는 사용자가 **"커밋해"/"푸시해"** 를, 이슈 생성·수정·PR 은 **"이슈 만들어"/"PR 올려"** 를 명시한 뒤에만. **승격을 스스로 추론하지 않는다.** merge · Issue close · 브랜치 삭제 · `push --force` · `reset --hard` · `rebase` 는 **항상 개별 승인**. `main` 직접 커밋 금지 · `git add -A` 금지(경로 명시) · `git add Plan` 금지 | 사용자 결정을 대신한 것이 된다 |
| **②** | **`Ecommerce_Service` 파일 변경 0건.** 별도 저장소이고 사용자가 명시적으로 제외했다. **읽기는 허용**된다. 편집이 필요해지면 **멈추고 보고한다** | charter §5 위반 |
| **③** | **결손을 0 으로 채우지 않는다.** 명시적으로 기록하고 의존 지표는 **계산 불가로 표시**한다. **미실행 검증을 통과로 표시하지 않는다** — 실행 불가는 `BLOCKED` 로 **이유와 함께** | ★ **이 프로젝트의 USP-1 이 끝난다** |

`[Source: AGENTS.md#반드시-지킬-것]` · `[Source: docs/GIT_WORKFLOW.md#6]` · `[Source: .agent-team/00-plan/charter.md#6.1]` · `[Source: .agent-team/00-plan/task-graph.md#3 W3]`

---

# 1. 메타

| | |
|---|---|
| **대상** | W2 T2.9 — **소유 이슈가 없다.** charter §4 In Scope 의 *"의존성 매니페스트 — 현재 없음 → C1 에서 도입"* 에 대응 |
| **담당** | Phillip · W5-A |
| **Phase** | **2'** — M-03/M-04 와 병렬 가능 |
| **차단** | **사용자 결정 D-19** (신규 CI 워크플로) — §9.4 |
| **차단하는 것** | M-07 의 `DQ-17`(Parquet 재현성) `BLOCKED` 해소 |
| **커밋 type** | `chore` |

> ## ★ 이 스토리가 푸는 문제
> **새 의존성을 넣어도 격리 CI 가 깨지지 않게 하고, 동시에 W1 의 `B-1`(Parquet 경로 미검증)을 해소한다.**
> charter 가정 **A7** — *"의존성 도입 후에도 CI 격리 검사가 유지된다"* 의 실검증이다.

---

# 2. 스토리

> **`P-팀`으로서 나는 새 의존성을 넣어도 격리 CI 가 격리와 무관한 이유로 빨개지지 않기를 원한다.**
> 왜냐하면 `isolation.yml` 이 **의존성 설치 단계 없이** 전 테스트를 돌리는 것이 `ISO-005` 보장이고, 그것이 깨지면 *"표준 라이브러리만으로 전 테스트가 돈다"* 는 매 PR 의 증명이 사라지기 때문이다.

> **`P-팀`으로서 나는 `events.parquet` 재현성이 영원히 `BLOCKED` 로 남지 않기를 원한다.**
> 왜냐하면 그것이 **USP-2("정직성을 코드로 강제")의 근거 중 하나**인데 지금 한 번도 실행된 적이 없기 때문이다.

---

# 3. 인수 조건 (AC)

## AC-1 · 매니페스트

- [ ] `requirements.txt` — **런타임.** `pyarrow` · `PyYAML` **둘뿐**
- [ ] `requirements-dev.txt` — `-r requirements.txt` + `jsonschema` + `referencing`
- [ ] **정확 고정(`==`)** 을 쓴다 — `NFR-001` 재현성
- [ ] **버전은 CI 와 같은 Python 3.12 에서 해석해 넣고, 그 실행 결과를 PR 에 기록한다** (§4.6)
- [ ] pandas · numpy · scikit-learn 을 **넣지 않는다** — `src/decision/` 의 것이고 C1 범위 밖
- [ ] lint · 타입 검사 도구를 **넣지 않는다** — 없는 게이트를 만들지 않는다

## AC-2 · 의존성 봉쇄 (A7-6) ★

- [ ] **`import yaml` 이 `src/measurement/config_loader.py` 한 파일에만 있다**
- [ ] `pyarrow` 는 `sink.py` 의 **함수 안 지연 import + guarded** 패턴을 유지한다
- [ ] `schema.py` · `kpi.py` · `economics.py` · `contracts.py` · `publish.py` · `freeze.py` · `validate.py` 는 **표준 라이브러리만**
- [ ] 위를 `tests/test_neutrality.py` 가 **소스 검사로 고정한다**

## AC-3 · skip 을 통과로 만들지 않는다 ★

- [ ] 선택 의존성 테스트는 **`@unittest.skipUnless(...)` + 사유 문자열**
- [ ] **skip 수와 사유를 PR 본문에 기록한다**
- [ ] `DQ-17` 이 `results/data_quality_report.json` 에 **`status: "blocked"`** 로 게시된다
- [ ] `docs/gate1_checklist.md` 의 `BLOCKED` 항목에 남는다 (M-09 인계)

## AC-4 · Parquet 경로 검증 (`B-1` 해소)

- [ ] `test_parquet_roundtrip` — **22 컬럼이 왕복 후 값·타입 보존.** ★ **`None` 이 `0`·`""` 으로 바뀌지 않는다**
- [ ] `test_parquet_digest_reproducible` — 같은 입력 2회 → 같은 SHA-256 (`NFR-001`)
- [ ] `test_format_auto_selects_parquet` — pyarrow 있으면 `resolve_format("auto")` 가 Parquet
- [ ] ★ `test_jsonl_and_parquet_agree` — 같은 레코드를 두 형식으로 쓰고 되읽어 **동일 결과**

## AC-5 · A7 회귀 판정 7항목

| # | 판정 | 확인 |
|---|---|---|
| A7-1 | `python3 -m unittest tests.test_isolation -v` 가 **의존성 없이** 통과 | 로컬 + `isolation.yml` |
| A7-2 | `python3 -m unittest discover -s tests` 가 **의존성 없이** 통과 (skip 허용) | 동일 |
| A7-3 | 같은 명령이 **의존성 설치 후에도** 통과 | 로컬 또는 `tests-with-deps.yml` |
| A7-4 | 기준선 46건에서 **회귀 0** — ★ **수가 아니라 skip 된 테스트 이름 목록으로 대조한다** | 아래 |
| A7-5 | **skip 수와 사유를 PR 에 기록** | PR 본문 |
| A7-6 | `import yaml` 이 `config_loader.py` 한 파일에만 | grep + `test_neutrality.py` |
| **A7-7** | ★ **`.gitignore` 에 새 항목이 들어갔다** — §4.5 | 파일 확인 |

`[Source: .agent-team/04-architecture/dependency-plan.md#7]`

---

# 4. 개발 컨텍스트 (`developer_context`)

## 4.1 현재 상태 — 실측 (2026-09-11)

| 사실 | 확인 방법 |
|---|---|
| **의존성 매니페스트가 없다** | `ls` — `requirements.txt` · `pyproject.toml` 없음 |
| `pyarrow` · `PyYAML` · `jsonschema` **전부 미설치** | `python3 -c "import …"` → `ModuleNotFoundError` × 3 |
| 로컬 Python **3.14.6** · CI **3.12** | `python3 --version` · `isolation.yml` |
| CI 에 **의존성 설치 단계가 없다** | `isolation.yml` — 주석이 그 이유를 명시 |
| CI 가 `tests.test_isolation` 과 `discover -s tests` 를 **둘 다** 돌린다 | 동일 |
| `.github/workflows/isolation.yml` 은 **봉인 파일** | `task-graph.md` §4 |
| `sink.py` 의 pyarrow 는 **이미 지연 import + guarded** | `sink.py parquet_available()` |

## 4.2 ★ A7 이 깨지는 정확한 경로

```
config/economic_config.yaml 을 읽으려면 YAML 파서가 필요하다
        ↓
economics.py 가 yaml 을 import 한다            ← 여기서 끊는다 (§4.3)
        ↓
tests/test_economics.py 가 economics 를 import 한다
        ↓
isolation.yml 의 "Run all tests" 단계(의존성 미설치)가 ImportError 로 실패한다
        ↓
격리 CI 가 빨개진다 — 격리와 무관한 이유로
```

`[Source: .agent-team/04-architecture/dependency-plan.md#1.1]`

## 4.3 해법 ① — 모듈 경계에서 의존성을 가둔다 *(가장 중요)*

| 모듈 | 의존성 |
|---|---|
| `schema.py` · `kpi.py` · `economics.py` · `contracts.py` · `publish.py` · `freeze.py` · `validate.py` | **표준 라이브러리만** |
| `config_loader.py` | **PyYAML** ← 유일한 접점 |
| `sink.py` | **pyarrow** (이미 지연 import · guarded) |

`economics.py` 는 **dict / dataclass 를 인자로 받는다.** YAML 을 읽지 않는다.
→ `test_economics.py` 는 **PyYAML 없이 전부 돈다.** 사슬의 첫 고리가 끊긴다.

`[Source: .agent-team/04-architecture/dependency-plan.md#2.1]` · `[Source: .agent-team/04-architecture/design-patterns.md#P-9]`

## 4.4 해법 ② — guarded import + **명시적 skip**

`sink.py` 가 이미 쓰는 패턴을 **규약으로 승격**한다:

```python
def parquet_available() -> bool:
    try:
        import pyarrow  # noqa: F401
    except ImportError:
        return False
    return True
```

```python
@unittest.skipUnless(sink.parquet_available(),
                     "BLOCKED: pyarrow 미설치 — Parquet 경로를 검증하지 않았다")
def test_parquet_roundtrip(self): ...
```

> ### ⚠ skip 은 통과가 아니다 — 이것을 **값**으로 만든다
> `unittest` 는 skip 을 **exit code 0** 으로 낸다. **스킵된 검증을 통과로 적으면 AGENTS.md 위반이다.**
> 세 곳에서 skip 을 드러낸다:
> 1. **PR 본문**에 skip 수와 사유
> 2. **`results/data_quality_report.json` 의 `DQ-17` 이 `status: "blocked"`** → 대시보드 V5 에 보인다
> 3. **`docs/gate1_checklist.md` 의 `BLOCKED` 항목**
>
> `[Source: .agent-team/04-architecture/dependency-plan.md#2.2]`

**⚠ 기존 테스트가 반대 방향이다:**

```python
tests/test_sink.py:65   test_auto_falls_back_without_pyarrow      # pyarrow 가 있으면 skip
tests/test_sink.py:69   test_parquet_request_without_pyarrow_raises  # 동일
```

**pyarrow 를 설치하면 이 둘이 skip 된다.** 그것이 올바른 동작이지만 **두 잡의 skip 수가 다른 이유**가 되므로 PR 에 적는다.

## 4.5 ★ `.gitignore` — Andrew 가 필요로 하는 항목을 **Phillip 이 미리 넣는다**

**`.gitignore` 는 Phillip 단독 소유다.** 두 사람이 같은 파일을 쓰면 `build-plan.md` §4 의 겹침 0 증명이 깨진다.

```gitignore
# ── 대시보드 (Andrew 가 필요로 하는 항목 — .gitignore 는 Phillip 단독 소유)
dashboard/node_modules/
dashboard/.next/
dashboard/src/styles/tokens.generated.css   # Plan/DESIGN.md 에서 재생성한다

# ── 게시물 (결정 D-17)
results/
```

`[Source: .agent-team/04-architecture/dependency-plan.md#5]`

**현재 `.gitignore` 실측:** `data/` · `models/` · `docs/data_spec.pdf` · `__pycache__/` · `.venv/` · `.DS_Store` · `.agent-team/07-design/canvas/` · `.agent-team/_state/*.audit-key` · `*.lock` 을 제외한다. **`results/` 는 아직 없다.**

> **D-17 이 미결정이다** (§9.4). `results/` 를 ignore 하면 **대시보드 스크린샷 증거를 저장소에 남길 수 없다.**
> W2 추천은 **⑶ — `results/` 제외 + `.agent-team/` 에 증거 사본**이다.

## 4.6 버전 — **이 문서에서 베끼지 않는다**

`dependency-plan.md` §3.3 이 명시했다:

> *"내가 로컬에서 확인할 수 없는 값을 적으면(설치를 하지 않았다) 그것은 **검증하지 않은 사실**이다. Phillip 이 CI 와 같은 Python 3.12 에서 해석한 값을 넣고 **그 실행 결과를 PR 에 기록**한다. 여기서 베낀 버전을 쓰지 않는다."*

**W3 가 검색으로 확인한 참고값 (2026-09-11):**

| 패키지 | 검색 확인 | 주의 |
|---|---|---|
| **pyarrow** | 최신 **25.0.1** (2026-08-10). 25.0.0 은 2026-07-10 · 222 issues / 268 commits | **cp314 휠 존재** — 로컬 3.14.6 에서도 설치 가능. **CI 3.12 가 기준**이다 |
| **PyYAML** | 6.0.2 에 직접 취약점 없음(Snyk) | ★ **CVE-2026-24009** — `yaml.FullLoader` 를 통한 RCE. 완화는 **`SafeLoader`** — §4.7 |
| **jsonschema** | ⚠ **최신 버전 미확정** — 검색으로 확정하지 못했다. **설치해 해석한 값을 쓴다.** Draft 2020-12 지원은 확인됨 (`referencing.jsonschema.DRAFT202012`) | 우리 스키마가 draft 2020-12 다 |

**정확 고정(`==`)을 쓰는 이유:** `NFR-001` 재현성. **`pyarrow` 버전이 바뀌면 같은 데이터에서 다른 Parquet 바이트가 나올 수 있고, 그러면 `events.parquet` SHA-256 대조가 무의미해진다.**
→ **라이브러리 버전을 `data_version.yaml` 에 기록한다**(`data_spec` §15.2 가 이미 요구). 게시물 `provenance.config_hashes` 와 함께 나른다.

## 4.7 ★ PyYAML 보안 — 로더 선택이 문제다

**CVE-2026-24009** 는 라이브러리 버그가 아니라 **로더 선택**의 문제다. `yaml.FullLoader` 는 조작된 페이로드로 임의 객체를 생성할 수 있다 (Docling RCE 사례).

```python
# ✅ 이것만 쓴다
data = yaml.safe_load(path.read_text(encoding="utf-8"))

# ❌ 금지
yaml.load(text)                            # 구버전에서 unsafe
yaml.load(text, Loader=yaml.FullLoader)    # CVE-2026-24009 경로
yaml.unsafe_load(text)
```

**`test_neutrality.py` 에 검사를 추가한다** — `config_loader.py` 에 `FullLoader`·`unsafe_load` 문자열이 없음.

## 4.8 해법 ③ — CI. **봉인 파일을 고치지 않고 새 워크플로를 추가한다**

**핵심 판단: `isolation.yml` 을 편집하지 않는다.**

봉인의 목적은 *"격리 검사가 조용히 헐거워지는 것"* 을 막는 데 있다. 그 파일에 `pip install` 을 넣으면 **"의존성 없이도 격리 검사가 돈다"(`ISO-005`)는 보장 자체가 사라진다.**

```text
.github/workflows/
├── isolation.yml          [봉인 · 손대지 않는다]
│     의존성 0 · test_isolation + discover -s tests
│     → "표준 라이브러리만으로 전 테스트가 돈다" 를 매 PR 이 증명한다 (ISO-005)
│
└── tests-with-deps.yml    [신설 · 제안 · D-19]
      pip install -r requirements.txt · discover -s tests
      → Parquet·YAML 경로가 실제로 실행된다 (B-1 해소)
```

| 이 배치가 주는 것 | |
|---|---|
| `isolation.yml` 이 **의존성 없이 초록** | `ISO-005` 유지 · A7 유지 |
| `tests-with-deps.yml` 가 **의존성 있게 초록** | `B-1` 해소 · `NFR-001` Parquet 재현성 검증 |
| 새 워크플로가 깨져도 | **격리 게이트는 그대로 돈다** |
| **skip 수가 두 잡 사이에서 다르다** | **그 차이가 곧 "의존성이 필요한 검증"의 목록**이다 — 저절로 드러난다 |

`[Source: .agent-team/04-architecture/adr/ADR-0004-ci-new-workflow-file.md]`

> ### ⚠ 이것은 **제안**이다 — 결정 D-19
> **새 워크플로 파일 추가는 편집이 아니지만 CI 를 바꾸는 일이고 매 PR 에서 돈다.**
> 봉인 규칙의 문언(`isolation.yml` 한 파일)에는 걸리지 않으나 **취지상 사용자·리드 확인을 받고 만든다.**
> **확인 없이 만들지 않는다.** 확인 전까지 Parquet 검증은 **로컬 실행 증거로만** 남기고 `BLOCKED` 를 유지한다.
>
> **`build-plan.md` §1 B-8 이 이 파일을 "봉인(사용자 확인 후)"으로 분류했다** — Phillip 의 배타적 소유가 아니다.

## 4.9 ★ pyarrow 가 새로 만드는 위험 — 정직하게

| 위험 | 왜 |
|---|---|
| **형식이 환경에 따라 갈린다** | `resolve_format("auto")` 가 pyarrow 유무로 다른 형식을 고른다. 개발자 A 는 Parquet, B 는 `jsonl.gz` 를 만들고 **해시가 다르다** |
| 완화 | `data_version.yaml` · 게시물 `provenance` 에 **`format` 을 기록**한다 (manifest 는 이미 기록). **재현성 대조는 같은 형식끼리만 성립함을 `docs/gate1_checklist.md` 에 명시** |
| **두 CI 잡이 다른 형식을 검증한다** | 위와 같은 이유 |
| 완화 | **그것이 의도다** — 두 경로를 다 검증한다. 다만 **두 잡의 skip 수 차이를 PR 에 기록**한다 |

`[Source: .agent-team/04-architecture/dependency-plan.md#4.3]`

## 4.10 ★ `test_jsonl_and_parquet_agree` 가 이 스토리의 핵심이다

> *"지금까지의 46건은 전부 `jsonl.gz` 경로만 검증했다. 두 형식이 다른 결과를 낸다면 **`jsonl.gz` 기준으로 확인한 46건이 Parquet 환경에서는 보증되지 않는다.**"*
> `[Source: .agent-team/04-architecture/dependency-plan.md#4.2]`

**특히 확인할 것:** `_write_parquet()` 는 `pa.table({name: [row.get(name) for row in rows] …})` 로 쓴다.
**`row.get(name)` 이 `None` 을 돌려주는 컬럼이 전체 `None` 이면 pyarrow 가 타입을 추론할 수 없어 `null` 타입 컬럼이 된다.** 되읽었을 때 값이 보존되는지 확인해야 한다.

**결손 은폐가 저장 계층에서 일어날 수 있는 자리다** — `None` 이 `0` 이나 `""` 으로 바뀌면 그것이 곧 0 채우기다.

## 4.11 함정

| # | 함정 | 왜 빠지나 | 대신 |
|---|---|---|---|
| **T-1** | `isolation.yml` 에 `pip install` 한 줄 추가 | 가장 짧다 | **봉인 파일 · `ISO-005` 보장 소멸.** §4.8 |
| **T-2** | `economics.py` 에 `import yaml` | config 를 읽어야 하니까 | §4.3 — **`config_loader.py` 만** |
| **T-3** | PyYAML 없을 때 간단 파서로 폴백 | 견고해 보인다 | **금지.** *"부분 구현 파서는 조용히 다른 값을 읽는다"* `[Source: .agent-team/04-architecture/exceptions.md#4]` |
| **T-4** | skip 을 PR 에 안 적고 "전건 통과"로 | exit 0 이라서 | AC-3 — **skip 은 통과가 아니다** |
| **T-5** | 버전을 이 문서에서 베낀다 | 편하다 | §4.6 — **설치해 해석한 값을 쓴다** |
| **T-6** | `pyproject.toml` 로 바꾼다 | 현대적이다 | **SRS §31 이 `requirements.txt` 를 규정한다.** 정본 변경은 권한 밖이고 바꿔서 얻는 것이 C1 에 없다 |
| **T-7** | pandas·numpy 를 "나중에 쓸 테니" 넣는다 | 미리 준비 | **쓰지 않는 의존성이 CI 시간을 먹고 "왜 있는지"를 아무도 모르게 된다** |
| **T-8** | `>=` 로 느슨하게 고정 | 유연하다 | **`NFR-001` 재현성.** 정확 고정 |
| **T-9** | `.gitignore` 를 Andrew 가 고치게 둔다 | 자기 파일이니까 | §4.5 — **겹침 0 증명이 깨진다** |
| **T-10** | 로컬 3.14.6 에서 해석한 버전을 그대로 넣는다 | 로컬이 편하다 | **CI 는 3.12 다.** 3.14 에서만 있는 버전을 고정하면 CI 가 깨진다 |

---

# 5. 작업 분해 (Tasks)

## T1 · D-19 확인 (차단)

- [ ] **사용자에게 `tests-with-deps.yml` 신설 여부를 확인한다.** 확인 전에 만들지 않는다
- [ ] 미승인이면 Parquet 검증을 **로컬 실행 증거로만** 남기고 `BLOCKED` 유지 → M-07·M-09 에 그대로 인계

## T2 · 매니페스트 (AC-1)

- [ ] **CI 와 같은 Python 3.12 환경**에서 `pip install pyarrow PyYAML` → 해석된 버전 확인
- [ ] `requirements.txt` 작성 — `==` 고정, 주석에 용도
- [ ] `requirements-dev.txt` — `-r requirements.txt` + `jsonschema` + `referencing`
- [ ] **설치 출력을 PR 본문에 붙인다**

## T3 · `.gitignore` (AC-5 A7-7)

- [ ] §4.5 항목 추가
- [ ] `results/` 는 **D-17 확인 후**. 미확인이면 넣지 않고 PR 에 사유를 적는다

## T4 · guarded 패턴 규약화 (AC-2·3)

- [ ] `config_loader.yaml_available()` 추가 (M-03 이 만든 파일)
- [ ] `test_config_loader.py` 에 `skipUnless` + 사유
- [ ] `tests/test_neutrality.py` 에 추가:
      - `test_yaml_import_is_contained` — `import yaml` 이 `config_loader.py` 한 파일에만
      - `test_no_unsafe_yaml_loader` — `FullLoader`·`unsafe_load` 문자열 0건
      - `test_pure_layer_has_no_third_party_import` — 계산층 7파일이 표준 라이브러리만

## T5 · Parquet 테스트 4건 (AC-4)

- [ ] `tests/test_sink.py` 에 `TestParquetPath` 추가, 전부 `skipUnless(parquet_available())`
- [ ] `test_parquet_roundtrip` — ★ **`None` 이 `0`·`""` 으로 바뀌지 않는다**
- [ ] `test_parquet_digest_reproducible`
- [ ] `test_format_auto_selects_parquet`
- [ ] ★ `test_jsonl_and_parquet_agree`

## T6 · CI (D-19 승인 시에만)

- [ ] `.github/workflows/tests-with-deps.yml` 신설
- [ ] `isolation.yml` 과 **다른 job 이름**을 쓴다 — 머지 기준이 `Tests / 격리 경계 + 전체 테스트` 다 (`docs/GIT_WORKFLOW.md` §5)
- [ ] `pip install -r requirements.txt` → `python -m unittest discover -s tests -t . -v`
- [ ] **`isolation.yml` 을 한 글자도 고치지 않았음을 `git diff` 로 증명**

## T7 · A7 판정 7항목 (AC-5)

- [ ] A7-1 ~ A7-7 각각 실행하고 결과를 PR 표로
- [ ] **두 환경(의존성 유/무)의 skip 수 차이**를 표로 기록

---

# 6. 파일 목록 (`file_list`)

## 6.1 이 스토리가 만지는 파일

| 파일 | 동작 | 소유 |
|---|---|---|
| `requirements.txt` | **신설** | Phillip |
| `requirements-dev.txt` | **신설** | Phillip |
| `.gitignore` | **수정** | **Phillip 단독** |
| `tests/test_sink.py` | **수정** — Parquet 테스트 4건 | Phillip |
| `tests/test_neutrality.py` | **수정** — 봉쇄 검사 3건 | Phillip |
| `src/measurement/config_loader.py` | **수정** — `yaml_available()` | Phillip |
| `.github/workflows/tests-with-deps.yml` | **신설 — D-19 승인 시에만** | **봉인(사용자 확인 후)** |
| `.agent-team/04-architecture/tools/ownership.json` | **수정하지 않는다** — 이미 등록돼 있다(Thomas N-1). 돌려 **확인만** | Phillip |

## 6.2 절대 만지지 않는 파일

```
.github/workflows/isolation.yml     ← ★ 봉인. 이 스토리의 존재 이유가 이것을 안 고치는 것이다
tests/test_isolation.py             ← 봉인
src/simulator/** src/decision/** src/diagnostics/** src/orchestration/**
Plan/** · AGENTS.md · src/AGENTS.md · README.md
dashboard/**                        ← Andrew. .gitignore 항목만 대신 넣는다
../Ecommerce_Service/**
```

---

# 7. 테스트

## 7.1 실행 가능한 명령

```bash
# 의존성 없이 (오늘의 기본 상태)
python3 -m unittest discover -s tests
python3 -m unittest tests.test_isolation -v

# 의존성 설치 후 (가상환경 권장 — 저장소를 오염시키지 않는다)
python3 -m venv /tmp/airoi-deps && /tmp/airoi-deps/bin/pip install -r requirements.txt
/tmp/airoi-deps/bin/python -m unittest discover -s tests

python3 .agent-team/04-architecture/tools/check_ownership.py
```

> **가상환경 경로를 `.venv/` 로 두면 `.gitignore` 가 이미 제외한다.** 저장소 안에 만들어도 커밋되지 않는다.
> **로컬 Python 은 3.14.6, CI 는 3.12 다.** 버전 해석은 3.12 기준으로 한다 (T-10).

## 7.1b ★★ A7-4 는 **수로 판정할 수 없다** (Matthias 항목3 · 실행 확인)

**`unittest` 는 skip 을 `Ran N` 에 포함한다.** W3 재현:

```python
class T(unittest.TestCase):
    def test_a(self): pass
    @unittest.skip("사유")
    def test_b(self): pass
# → Ran 2 tests · OK (skipped=1)      testsRun == 2
```

**그래서 이 둘의 요약행이 같다:**

| | `Ran` | skip |
|---|---|---|
| 정상 — 46 통과 + 신규 4 통과 | `Ran 50` | 0 |
| **회귀 — 기존 4건이 skip 으로 바뀌고 신규 4건이 통과** | `Ran 50` | 4 |

**A7-5 의 "skip 수"로도 구분되지 않는다** — 신규 skip 4건과 회귀 skip 4건이 둘 다 4다.

> ### ★ → **skip 된 테스트 이름 목록**을 대조한다
> **기준선 skip 은 0건이다** (W3 실측: `discover -s tests -v` 에서 `skipped` 0).
> **→ skip 목록에 기존 46건의 이름이 하나라도 있으면 회귀다.**

```bash
python3 -m unittest discover -s tests -v 2>&1 | grep -i "skipped" | sed 's/ \.\.\..*//'
```

**PR 에 이름 목록을 붙인다.** 수만 적으면 회귀가 통과로 보인다.

## 7.2 skip 수를 어떻게 보고하나

```markdown
| 환경 | 총 | 통과 | skip | skip 사유 |
|---|---|---|---|---|
| 의존성 없음 | N | N-4 | 4 | pyarrow 미설치(3) · PyYAML 미설치(1) |
| 의존성 설치 | N | N-2 | 2 | `test_auto_falls_back_without_pyarrow` 등 반대 방향 2건 |
```

**두 줄의 차이가 곧 "의존성이 필요한 검증"의 목록이다.**

---

# 8. 연속성

## 8.1 선행 스토리에서 이어받는 것

| 스토리 | 이어받는 것 |
|---|---|
| **M-03 (`#47`)** | `config_loader.py` — 이 스토리가 `yaml_available()` 를 붙인다 · `tests/test_neutrality.py` |
| **M-01 (`#53`)** | `sink.py` 의 수정된 파티션 로직 — Parquet 왕복 테스트가 그 경로를 밟는다 |

## 8.2 확립된 패턴

| 패턴 | 어디에 |
|---|---|
| **guarded import** | `sink.py parquet_available()` — 그대로 따른다 |
| **명시 요청 시 폴백하지 않고 예외** | `sink.py resolve_format()` — `fmt="parquet"` 인데 pyarrow 가 없으면 `RuntimeError` |
| **CI 주석이 "왜 없는지"를 적는다** | `isolation.yml` — 새 워크플로도 같게 |

## 8.3 폴백이 허용되는 조건 — 셋을 다 만족할 때만

1. 폴백 결과가 **의미상 같다** (`jsonl.gz` 와 Parquet 은 같은 레코드를 담는다)
2. 폴백 사실이 **산출물에 기록된다** (`manifest.format` · 게시물 `provenance`)
3. 폴백이 **검증 결과를 통과로 바꾸지 않는다** (`DQ-17` 은 여전히 `blocked`)

**하나라도 어기면 폴백하지 않고 던진다.** `[Source: .agent-team/04-architecture/exceptions.md#4.1]`

---

# 9. 완료 정의 (DoD) · 미결정 · 차단

## 9.1 DoD

- [ ] AC-1 ~ AC-5 전부 체크
- [ ] **버전을 CI 와 같은 3.12 에서 해석해 넣고 설치 출력을 PR 에 붙였다**
- [ ] **skip 수와 사유를 두 환경에 대해 표로 기록했다**
- [ ] `isolation.yml` 변경 **0줄** — `git diff` 로 증명
- [ ] D-19 미승인이면 `tests-with-deps.yml` 을 **만들지 않았고** 그 사실을 PR 에 적었다
- [ ] `DQ-17` 의 상태(해소 / 여전히 `BLOCKED`)를 M-07·M-09 에 인계했다

## 9.2 이 스토리에서 하지 않는 것

| 항목 | 왜 |
|---|---|
| lint · 타입 검사 도입 | charter §6.3 이 미정의로 둔다. **없는 게이트를 만들지 않는다** |
| Node CI | 동일 (`dependency-plan.md` §5) |
| `docker-compose.yml` | **결정 D-20 — C1 범위 밖 추천** |
| pandas · numpy · scikit-learn | `src/decision/` 의 것 |
| `data/data_version.yaml` 생성 | **C1 에 데이터 생성 주체가 없다.** 게시물은 `data_version: null` + `null_reason` |

## 9.3 미결정 — 구현자가 정하고 PR 에 적는다

| # | 항목 | 선택지 |
|---|---|---|
| **M05-a** | `jsonschema` 를 어디에 | **D-21 — ⑴ dev 전용 (권장)** ⑵ 런타임. ⑴이면 게시 시점 자기검증은 **핵심 불변식 몇 개만 표준 라이브러리로** 확인하고 전체 스키마 검증은 테스트에서 한다 |
| **M05-b** | 가상환경 위치 | `.venv/`(gitignore 됨) / `/tmp` |

## 9.4 차단 — 사용자 결정

| # | 항목 | 선택지 | W2 추천 |
|---|---|---|---|
| **D-19** | **`tests-with-deps.yml` 신규 워크플로를 만드는가** | ⑴ **만든다** (봉인 파일은 손대지 않음) ⑵ `isolation.yml` 에 설치 단계 추가 ⑶ 만들지 않고 로컬 실행 증거만 | **⑴.** ⑵는 `ISO-005` 보장을 없앤다. ⑶은 `B-1` 이 CI 에서 영구히 미검증으로 남는다. **단 CI 변경이므로 사용자 확인 후에** |
| **D-17** | `results/` 를 `.gitignore` 에 넣는가 | ⑴ 넣는다 ⑵ 넣지 않는다 ⑶ **넣되 `.agent-team/` 에 증거 사본** | **⑶** |
| **D-21** | `jsonschema` 를 런타임/개발 중 어디에 | ⑴ **dev 전용** ⑵ 런타임 | **⑴** — 런타임 의존을 하나 줄인다 |

`[Source: .agent-team/04-architecture/dependency-plan.md#8]`

## 9.5 하류로 넘기는 것

| 받는 스토리 | 넘기는 것 |
|---|---|
| **M-06 (게시)** | `jsonschema` 가용 여부 → 게시 시점 자기검증의 수단 결정 (M05-a) |
| **M-07 (`#48`)** | **`DQ-17` 이 해소됐는지** — 해소되면 `blocked` → `pass`/`fail`. 안 됐으면 `blocked` 유지 · 형식 차이(`jsonl.gz` vs Parquet)가 재현성 대조에 미치는 영향 |
| **M-09 (`#49`)** | `BLOCKED` 항목 `PARQUET_REPRODUCIBILITY` 의 최종 상태 · **라이브러리 버전을 `provenance` 에 나르는 규약** |
| **d-01 (대시보드)** | `.gitignore` 에 `dashboard/node_modules/` 등이 **이미 있다** — Andrew 는 `.gitignore` 를 고치지 않는다 |

<!-- ════════ source_hash inputs (D3 · Matthias 항목5) ════════
     계산법: project-context-kr.md §12  ·  파일 16종
     재현:  아래 목록을 sorted() 하고 각 파일에 f"{path}\n{sha256_hex}\n" 를 이어붙여
            그 바이트열의 SHA-256 앞 16자리를 취한다. 없는 파일은 "MISSING".

     .agent-team/00-plan/charter.md
     .agent-team/00-plan/task-graph.md
     .agent-team/04-architecture/adr/ADR-0004-ci-new-workflow-file.md
     .agent-team/04-architecture/build-plan.md
     .agent-team/04-architecture/code-structure.md
     .agent-team/04-architecture/data-quality-design.md
     .agent-team/04-architecture/dependency-plan.md
     .agent-team/04-architecture/design-patterns.md
     .agent-team/04-architecture/exceptions.md
     .github/workflows/isolation.yml
     AGENTS.md
     docs/GIT_WORKFLOW.md
     src/AGENTS.md
     src/measurement/sink.py
     tests/test_isolation.py
     tests/test_sink.py

     → source_hash = 4ab8babbc1e25356
     ════════════════════════════════════════════════════ -->
