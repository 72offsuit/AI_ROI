# 의존성 매니페스트 도입 설계 (T2.9) — 가정 A7

**작성** James (Role 4 · Architect) · 2026-09-11 · 사이클 C1
**푸는 문제** 새 의존성(pyarrow · PyYAML)을 넣어도 **격리 CI 가 깨지지 않는 방법**을 정하고, 동시에 W1 의 **`B-1`(Parquet 경로 검증 BLOCKED)** 을 해소한다.
**정본 근거** SRS `ISO-005` · §31 · `NFR-001` · charter §8 가정 A7 · `.github/workflows/isolation.yml`

---

# 1. 현재 상태 — 실측

| 사실 | 근거 |
|---|---|
| **의존성 매니페스트가 없다** | 저장소에 `requirements.txt` · `pyproject.toml` 없음 |
| `src/measurement/**` 는 표준 라이브러리만 쓴다 | `schema.py:11-14` · `sink.py` (pyarrow 는 함수 안 지연 import) |
| 로컬에 `pyarrow` · `PyYAML` · `jsonschema` **전부 없다** | 실행 확인 (2026-09-11) |
| CI 는 **의존성 설치 단계가 없다** | `isolation.yml:32-35` 주석이 그 이유를 명시 |
| CI 는 `tests.test_isolation` 과 `discover -s tests` 를 **둘 다** 돌린다 | `isolation.yml:36-45` |
| `.github/workflows/isolation.yml` 은 **봉인 파일** | task-graph §4 — W6 Matthias + 사용자 승인 |

## 1.1 A7 이 깨지는 정확한 경로

```
config/economic_config.yaml 을 읽으려면 YAML 파서가 필요하다
        ↓
economics.py 가 yaml 을 import 한다
        ↓
tests/test_economics.py 가 economics 를 import 한다
        ↓
isolation.yml 의 "Run all tests" 단계(의존성 미설치)가 ImportError 로 실패한다
        ↓
격리 CI 가 빨개진다 — 격리와 무관한 이유로
```

**이것이 A7 이 예고한 실패다.** 아래 §2 가 이 사슬을 두 군데에서 끊는다.

---

# 2. 해법 — 세 겹

## 2.1 ① 모듈 경계에서 의존성을 가둔다 *(가장 중요)*

**설계 원칙: 계산층은 순수하게 두고, 의존성은 입출력 모듈 한 곳으로 밀어낸다.**

| 모듈 | 의존성 | 근거 |
|---|---|---|
| `schema.py` · `kpi.py` · `economics.py` · `contracts.py` · `publish.py` · `freeze.py` · `validate.py` | **표준 라이브러리만** | `code-structure.md` L-2 — 계산층은 I/O 를 하지 않는다 |
| `config_loader.py` | **PyYAML** ← 유일한 접점 | YAML 파싱은 I/O 다 |
| `sink.py` | **pyarrow** (이미 지연 import · 이미 guarded) | `sink.py:52-56, 297-302` |

`economics.py` 는 **dict/dataclass 를 인자로 받는다.** YAML 을 읽지 않는다.
→ `test_economics.py` 는 **PyYAML 없이 전부 돈다.** 사슬의 첫 고리가 끊긴다.

## 2.2 ② 선택 의존성은 반드시 guarded import + **명시적 skip**

`sink.py` 가 이미 쓰는 패턴을 규약으로 승격한다.

```python
def parquet_available() -> bool:
    try:
        import pyarrow  # noqa: F401
    except ImportError:
        return False
    return True
```

테스트 쪽:

```python
@unittest.skipUnless(sink.parquet_available(),
                     "BLOCKED: pyarrow 미설치 — Parquet 경로를 검증하지 않았다")
def test_parquet_roundtrip(self): ...
```

> ### ⚠ skip 은 통과가 아니다 — 이것을 값으로 만든다
> `unittest` 는 skip 을 exit code 0 으로 낸다. **스킵된 검증을 통과로 적으면 AGENTS.md 위반이다.**
> 세 곳에서 skip 을 드러낸다:
> 1. **PR 본문에 skip 수와 사유를 기록한다** (`build-plan.md` §5 PR 체크리스트)
> 2. **`results/data_quality_report.json` 의 DQ-17 이 `status: "blocked"`** 로 게시된다 → 대시보드 V5 에 보인다
> 3. **`docs/gate1_checklist.md` 의 `BLOCKED` 항목**에 남는다

## 2.3 ③ CI — 봉인 파일을 고치지 않고 **새 워크플로 파일을 추가**한다

**핵심 판단: `isolation.yml` 을 편집하지 않는다.**

봉인의 목적은 *"격리 검사가 조용히 헐거워지는 것"* 을 막는 데 있다. 그 파일에 `pip install` 단계를 넣으면 **"의존성 없이도 격리 검사가 돈다"(`ISO-005`)는 보장 자체가 사라진다.**
반대로 **새 파일을 추가하면** 두 보장이 동시에 성립한다.

```text
.github/workflows/
├── isolation.yml          [봉인 · 손대지 않는다]
│     의존성 0 · test_isolation + discover -s tests
│     → "표준 라이브러리만으로 전 테스트가 돈다" 를 매 PR 이 증명한다 (ISO-005)
│
└── tests-with-deps.yml    [신설 · 제안]
      pip install -r requirements.txt · discover -s tests
      → Parquet·YAML 경로가 실제로 실행된다 (B-1 해소)
```

| 이 배치가 주는 것 | |
|---|---|
| `isolation.yml` 이 **의존성 없이 초록** | `ISO-005` 유지 · A7 유지 |
| `tests-with-deps.yml` 가 **의존성 있게 초록** | `B-1` 해소 · `NFR-001` Parquet 재현성 검증 |
| 새 워크플로가 깨져도 | **격리 게이트는 그대로 돈다** |
| skip 수가 두 잡 사이에서 다르다 | **그 차이가 곧 "의존성이 필요한 검증"의 목록**이다 — 저절로 드러난다 |

> ### ⚠ 이것은 제안이다 — 결정 D-19
> **새 워크플로 파일 추가는 편집이 아니지만 CI 를 바꾸는 일이고, 매 PR 에서 돈다.**
> 봉인 규칙의 문언(*"`.github/workflows/isolation.yml`"* 한 파일)에는 걸리지 않으나, **취지상 사용자·리드 확인을 받고 만드는 것이 맞다.**
> 확인 없이 만들지 않는다. 확인 전까지 Parquet 검증은 **로컬 실행 증거로만** 남기고 `BLOCKED` 를 유지한다.

---

# 3. 매니페스트

SRS §31 이 `requirements.txt` 를 규정한다. **`pyproject.toml` 로 바꾸지 않는다** — 정본 변경은 권한 밖이고, 바꿔서 얻는 것이 C1 에 없다.

```text
requirements.txt         런타임 — 제품 코드가 실제로 import 하는 것
requirements-dev.txt     개발·검증 — 테스트를 더 강하게 만드는 것
```

## 3.1 `requirements.txt` — C1 에서 넣는 것은 둘뿐

| 패키지 | 무엇에 쓰나 | 없으면 | 해소하는 것 |
|---|---|---|---|
| `pyarrow` | `sink.py` Parquet 저장·되읽기 | `jsonl.gz` 로 자동 폴백 (이미 구현) | **W1 `B-1`** · `NFR-001` Parquet SHA-256 재현성 · `data_spec` §7 *"모든 테이블은 Parquet(snappy)"* |
| `PyYAML` | `config_loader.py` 가 `economic_config.yaml`·`gate1_lock.yaml` 을 읽는다 | config 를 읽을 수 없다 → `ConfigError` | `CFG-004` · `#47` |

**이 둘 말고는 넣지 않는다.** pandas · numpy · scikit-learn 은 `src/decision/` 의 것이고 C1 범위 밖이다. 지금 넣으면 쓰지 않는 의존성이 CI 시간을 먹고, "왜 있는지" 를 아무도 모르게 된다.

## 3.2 `requirements-dev.txt`

```text
-r requirements.txt
jsonschema     # 게시물 ↔ JSON Schema 검증 (tests/test_publish_contract.py)
referencing    # jsonschema 의 $ref 해석
```

**lint·타입 검사 도구를 넣지 않는다.** charter §6.3: *"lint·build·타입 검사 미정의"*. 도구를 넣으면 실행되지 않는 명령이 문서에 생긴다. 도입은 별도 결정 사항이다.

## 3.3 버전 고정 — 이 문서에 버전 번호를 쓰지 않는다

```text
# requirements.txt — 예시 형식. ★ 실제 값은 구현 시점에 해석해 넣는다.
pyarrow==<CI Python 3.12 에서 해석된 버전>
PyYAML==<동일>
```

> **이 문서에 구체적 버전을 적지 않는 이유:** 내가 로컬에서 확인할 수 없는 값을 적으면(설치를 하지 않았다) 그것은 **검증하지 않은 사실**이다.
> Phillip 이 CI 와 같은 Python 3.12 에서 해석한 값을 넣고 **그 실행 결과를 PR 에 기록**한다. 여기서 베낀 버전을 쓰지 않는다.

**정확 고정(`==`)을 쓰는 이유:** `NFR-001` 재현성. `pyarrow` 버전이 바뀌면 같은 데이터에서 **다른 Parquet 바이트**가 나올 수 있고, 그러면 `events.parquet` SHA-256 대조가 무의미해진다.
→ **`data_version.yaml` 에 라이브러리 버전을 기록한다**(`data_spec` §15.2 가 이미 요구). 게시물 `provenance.config_hashes` 와 함께 나른다.

---

# 4. `B-1` 해소 — Parquet 경로 검증

## 4.1 지금 무엇이 검증되지 않았나

| | 상태 | 근거 |
|---|---|---|
| `_write_parquet()` | **한 번도 실행된 적 없다** | `sink.py:297-302` · 로컬·CI 모두 pyarrow 없음 |
| Parquet 되읽기 | 동일 | `sink.py:318-321` |
| `test_sink.py:69-73` | pyarrow 가 **있으면 skip** 하는 반대 방향 테스트 | W1 실측 |
| `NFR-001` Parquet SHA-256 재현성 | **미검증** | `data_quality_report` DQ-17 = `blocked` |

## 4.2 해소 후 추가할 테스트

| 테스트 | 검사 |
|---|---|
| `test_parquet_roundtrip` | 22 컬럼이 왕복 후 값·타입 보존. **`None` 이 `0`·`""` 으로 바뀌지 않는다** ← 결손 은폐가 저장 계층에서 일어날 수 있는 자리 |
| `test_parquet_digest_reproducible` | 같은 입력 2회 → 같은 SHA-256 (`NFR-001`) |
| `test_format_auto_selects_parquet` | pyarrow 있으면 `resolve_format("auto")` 가 Parquet |
| `test_jsonl_and_parquet_agree` | 같은 레코드를 두 형식으로 쓰고 되읽어 **동일 결과** |

> **마지막 테스트가 핵심이다.** 지금까지의 46건은 전부 `jsonl.gz` 경로만 검증했다. 두 형식이 다른 결과를 낸다면 **`jsonl.gz` 기준으로 확인한 46건이 Parquet 환경에서는 보증되지 않는다.**

## 4.3 `pyarrow` 가 새로 만드는 위험 — 정직하게

| 위험 | 왜 |
|---|---|
| **형식이 환경에 따라 갈린다** | `resolve_format("auto")` 가 pyarrow 유무로 다른 형식을 고른다. 개발자 A 는 Parquet, B 는 jsonl.gz 를 만들고 **해시가 다르다** |
| 완화 | `data_version.yaml` · 게시물 `provenance` 에 **`format` 을 기록**한다(manifest 는 이미 기록). 재현성 대조는 **같은 형식끼리만** 성립함을 `docs/gate1_checklist.md` 에 명시 |
| **`isolation.yml` 잡과 `tests-with-deps.yml` 잡이 다른 형식을 검증한다** | 위와 같은 이유 |
| 완화 | 그것이 의도다 — **두 경로를 다 검증한다.** 다만 두 잡의 skip 수 차이를 PR 에 기록한다 |

---

# 5. Node/npm 과 Python 의 공존

한 저장소에 런타임이 둘이다.

```text
AI_ROI/
├── requirements.txt          Python 런타임        [Phillip]
├── requirements-dev.txt      Python 개발          [Phillip]
├── dashboard/
│   ├── package.json          Node 런타임          [Andrew]
│   └── package-lock.json     ★ 커밋한다           [Andrew]
└── docker-compose.yml        둘을 묶는다           [§6 · 결정 D-20]
```

| 규칙 | 내용 |
|---|---|
| **경계** | Node 의존성은 `dashboard/` **밖으로 나오지 않는다.** 저장소 루트에 `package.json` 을 두지 않는다 |
| **잠금** | `package-lock.json` 을 **커밋한다.** `node_modules/` 는 `.gitignore` |
| **CI** | Node 검사는 **C1 에서 도입하지 않는다.** `dashboard/` 의 lint·build 를 CI 에 넣으려면 새 워크플로가 필요하고, charter §6.3 이 *"lint·build 미정의"* 다. **없는 게이트를 만들지 않는다** |
| **`.gitignore`** | 아래 항목이 필요하다 |

```gitignore
# ── 대시보드 (Andrew 가 필요로 하는 항목 — .gitignore 는 Phillip 단독 소유)
dashboard/node_modules/
dashboard/.next/
dashboard/src/styles/tokens.generated.css   # Plan/DESIGN.md 에서 재생성한다

# ── 게시물 (결정 D-17)
results/
```

> **`.gitignore` 를 Phillip 단독 소유로 두고 Andrew 가 필요로 하는 항목을 여기 미리 적어 둔 이유:** 두 사람이 같은 파일을 쓰면 소유 경계에 겹침이 생긴다. `build-plan.md` §4 의 겹침 0 증명이 이 결정에 의존한다.

---

# 6. `docker-compose.yml`

SRS §31 이 파일 존재를 규정하고 PRD §90 DoD 가 `docker-compose up` 을 요구한다.
**단 charter §4 In Scope 에 없다** — 장기 DoD 항목이며 charter §3.2 가 *"C1 에서 판정하지 않는다"* 로 두었다.

> **판정: C1 필수가 아니다. 설계는 여기 남기고, 도입 여부는 결정 D-20 이다.**
> 도입하면 `docker-compose up` 이 문서에 실행 가능한 명령으로 등장할 수 있고, 도입하지 않으면 **그 명령을 어디에도 쓰지 않는다.**

## 6.1 구성 — 서비스 2개. DB 는 없다

```yaml
# docker-compose.yml — 설계안. 도입 결정(D-20) 전에는 만들지 않는다.
services:
  measurement:
    # 측정 계층 게시를 1회 실행하는 배치 컨테이너다. 상주 서버가 아니다.
    image: python:3.12-slim
    working_dir: /app
    volumes:
      - ./:/app
    command: >
      sh -c "pip install --no-cache-dir -r requirements.txt &&
             python -m src.measurement.publish --source data/raw --out results"
    # 포트를 열지 않는다 — 이 프로젝트에는 API 서버가 없다 (DB-013)

  dashboard:
    image: node:22-alpine
    working_dir: /app/dashboard
    depends_on:
      measurement:
        condition: service_completed_successfully
    volumes:
      - ./dashboard:/app/dashboard
      - ./results:/app/results:ro          # ★ read-only 마운트
      - ./Plan:/app/Plan:ro                # 디자인 토큰 정본
    environment:
      AIROI_RESULTS_DIR: /app/results
    ports:
      - "3001:3001"                        # DB-002. 3000 은 Ecommerce_Service 점유
    command: sh -c "npm ci && npm run dev -- --port 3001"
```

## 6.2 이 구성의 설계 판단

| 판단 | 근거 |
|---|---|
| **DB 서비스가 없다** | 이 저장소에 데이터베이스가 없다. 저장은 파일이다(`data/raw/**`) |
| **API 서버 서비스가 없다** | `DB-013` — *"별도 API 서버를 두지 않는다"* |
| **`results/` 를 `:ro` 로 마운트한다** | `DB-014` 를 **컨테이너 경계로도** 강제한다. 대시보드가 게시물을 쓸 수 없다 |
| **`data/` 를 대시보드에 마운트하지 않는다** | `data/hidden/`·`data/ground_truth/` 가 컨테이너 안에 존재조차 하지 않는다. **격리를 파일시스템으로 만든다** — 이 구성의 가장 좋은 부분이다 |
| **`measurement` 가 먼저 끝나야 `dashboard` 가 뜬다** | 게시물 없이 대시보드를 띄우면 첫 화면이 "게시 방법 안내"다. 순서를 강제해 그 경로를 줄인다 |
| **포트 3001** | `DB-002` · charter §6.3 (3000 은 커머스) |
| **`Plan` 을 `:ro` 로** | 토큰 생성 입력. **쓰기 금지** — 서브모듈 오염 방지 |

## 6.3 도입 시의 검증 — 미리 정한다

`docker-compose up` 이 문서에 등장하려면 **한 번이라도 실행되어야 한다.** 실행하지 않은 명령을 DoD 에 쓰지 않는다.
→ 도입 PR 은 **실제 실행 로그(두 컨테이너 기동 + `:3001` 응답)** 를 본문에 첨부한다. 첨부가 없으면 `BLOCKED`.

---

# 7. 도입 후에도 유지되어야 하는 것 — 회귀 판정 기준

`build-plan.md` §5 의 PR 체크리스트가 이 표를 그대로 쓴다.

| # | 판정 | 어떻게 확인하나 |
|---|---|---|
| A7-1 | `python3 -m unittest tests.test_isolation -v` 가 **의존성 없이** 통과 | 로컬 + `isolation.yml` |
| A7-2 | `python3 -m unittest discover -s tests` 가 **의존성 없이** 통과 (skip 허용) | 로컬 + `isolation.yml` |
| A7-3 | 같은 명령이 **의존성 설치 후에도** 통과 | `tests-with-deps.yml` (D-19 승인 시) 또는 로컬 |
| A7-4 | 기준선 46건에서 **회귀 0** | 실행 출력 |
| A7-5 | **skip 수와 사유를 PR 에 기록** | PR 본문 |
| A7-6 | `src/measurement/` 안에서 `import yaml` 이 `config_loader.py` **한 파일에만** 있다 | grep — `tests/test_neutrality.py` 로 고정 가능 |

> **A7-6 을 테스트로 고정하는 것을 권고한다.** 이것이 §2.1 의 봉쇄를 유지하는 유일한 방법이다.
> 없으면 다음 사람이 `economics.py` 에 `import yaml` 을 한 줄 넣고, 그 순간 `isolation.yml` 이 격리와 무관한 이유로 빨개진다.

---

# 8. 결정이 필요한 항목

| # | 항목 | 선택지 | 추천 |
|---|---|---|---|
| **D-19** | **`tests-with-deps.yml` 신규 워크플로를 만드는가** — §2.3 | ⑴ 만든다 (봉인 파일은 손대지 않음) ⑵ `isolation.yml` 에 설치 단계 추가 ⑶ 만들지 않고 로컬 실행 증거만 | **⑴.** ⑵는 `ISO-005` 보장을 없앤다. ⑶은 `B-1` 이 CI 에서 영구히 미검증으로 남는다. **단 CI 변경이므로 사용자 확인 후에** |
| **D-20** | **`docker-compose.yml` 을 C1 에 도입하는가** — §6 | ⑴ 도입 + 실행 증거 첨부 ⑵ C1 범위 밖으로 미룬다 | **⑵.** charter §4 In Scope 에 없다. **다만 §6.2 의 `:ro` 마운트 격리는 도입 시 큰 이득**이므로 리드가 범위를 넓힐지 판단할 값어치가 있다 |
| **D-21** | `jsonschema` 를 런타임에 넣는가 개발용에 넣는가 | ⑴ dev 전용 (게시 시 검증은 자체 구현) ⑵ 런타임 | **⑴.** 게시 시점 자기검증은 계약의 핵심 불변식 몇 개만 표준 라이브러리로 확인하면 충분하고, **전체 스키마 검증은 테스트에서 한다.** 런타임 의존을 하나 줄인다 |

---

# 9. 미정으로 남긴 것

| 항목 | 왜 |
|---|---|
| `pyarrow`·`PyYAML` 의 **정확한 버전** | 설치하지 않았다. 구현 시점에 CI 와 같은 Python 3.12 에서 해석해 넣고 그 결과를 PR 에 기록한다 (§3.3) |
| lint·타입 검사 도입 | charter §6.3 이 미정의로 둔다. **없는 게이트를 만들지 않는다** |
| Node CI | 위와 같다 |
| `data/data_version.yaml` 생성 주체 | C1 에는 데이터 생성 주체가 없다. 시뮬레이터 사이클로 넘긴다. C1 게시물은 `data_version: null` + `null_reason` |
