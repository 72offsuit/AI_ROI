---
name: project-context
cycle: C1
wave: W3
author: Matthew (Role 17 · Story Engineer)
date: 2026-09-11
status: ready-for-dev
source_hash: 968e6c27ef3ef83d
source_files: 62
---

# 확정 헌법 — C1 팀 공통 기술 규칙

**작성** Matthew (Role 17 · Story Engineer) · 2026-09-11 · BATHOS Lv3 · 사이클 **C1**
**쓰기 범위 준수** `.agent-team/03-story-engineering/` 아래만 썼다. 제품 코드 · `Plan/` · `Ecommerce_Service` **변경 0건.** GitHub 이슈 생성·수정 **0건.**

> ## 이 문서의 지위
> **스토리파일은 각각 자족적이다.** 이 문서를 열지 않아도 구현할 수 있다.
> 여기 있는 것은 **11개 스토리에 공통으로 반복되는 규칙의 근거**이고, 스토리파일은 자기에게 필요한 부분을 **다시 적는다.** 중복은 의도된 것이다 — 구현자가 문서를 찾아가야 하는 순간 컨텍스트가 유실된다.
>
> 이 문서를 읽어야 하는 사람: **리드 · 리뷰어(Thomas·Matthias) · W6.**
>
> **모든 스토리파일의 §0 이 반드시 지킬 3줄(L1 권한 · `Ecommerce_Service` 금지 · 0 채우기 금지)을 다시 적는다** — `task-graph` §3 T3.2 요구.

---

# 0. 한 문단

C1 은 **측정 계층(창구)을 완주하고 그것이 관측 가능함을 화면으로 증명한다.**
기술적 중심 문제는 성능도 확장성도 아니고 둘이다 — **계약이 한쪽 편을 들지 않게 하는 것**, **결손이 조용히 0 이 되지 않게 하는 것.**
W2 가 이 둘을 문서 규율에서 **스키마·타입 제약**으로 끌어올렸다. W5 의 일은 그 제약을 코드로 옮기는 것이고, **가장 큰 위험은 구현자가 예외를 막으려다 그것을 되돌리는 것**이다 (§4).

---

# 1. 스토리 목록 — 11개

| 스토리 | 대상 | 담당 | Phase | 차단 |
|---|---|---|---|---|
| [`story-m-01-sink-defects-kr.md`](story-m-01-sink-defects-kr.md) | 이슈 `#53` — Sink 결함 3건 | Phillip | **1** | 없음 |
| [`story-m-02-schema-value-enforcement-kr.md`](story-m-02-schema-value-enforcement-kr.md) | 이슈 `#54` — 값 수준 강제 + `MetricValue` 어휘 | Phillip | **1** | 없음 |
| [`story-m-03-economics-kr.md`](story-m-03-economics-kr.md) | 이슈 `#47` — 경제 규칙 + config | Phillip | 2 | D-1 · D-2 |
| [`story-m-04-kpi-kr.md`](story-m-04-kpi-kr.md) | 이슈 `#46` — KPI 계산 계약 | Phillip | 2 | D-4 · D-5 · D-9 |
| [`story-m-05-dependencies-kr.md`](story-m-05-dependencies-kr.md) | T2.9 — 의존성 매니페스트 | Phillip | 2' | **D-19(사용자)** |
| [`story-m-06-publish-kr.md`](story-m-06-publish-kr.md) | T2.7 — `results/` 게시 | Phillip | 2'' | m-02·m-03·m-04 |
| [`story-m-07-data-quality-kr.md`](story-m-07-data-quality-kr.md) | 이슈 `#48` — 데이터 품질 검증 | Phillip | 2''' | **m-01(D1-2)** |
| [`story-m-08-measurement-contract-kr.md`](story-m-08-measurement-contract-kr.md) | 이슈 `#45` — 기록 계약 · **Lock 최종 검산** | Phillip | 3 | m-02 · G-8 · G-9 · G-16 |
| [`story-m-09-gate1-freeze-kr.md`](story-m-09-gate1-freeze-kr.md) | 이슈 `#49` — GATE 1 부분 봉인 | Phillip | 4 | 앞 전부 · D-7 |
| [`story-d-01-dashboard-foundation-kr.md`](story-d-01-dashboard-foundation-kr.md) | W5-C — 앱 골격 · 토큰 · 읽기 계층 | Andrew | — | 없음(픽스처로 착수) |
| [`story-d-02-observability-views-kr.md`](story-d-02-observability-views-kr.md) | W5-C — 관측 화면군 8화면 | Andrew | — | d-01 |

**의존 그래프** (`build-plan.md` §2.3 · `gate1-lock-scope.md` §2.3)

```
Phase 1   m-01 (#53)  ∥  m-02 (#54)
              │              │
              │              ├──────────────► m-08 (#45) ──► m-09 (#49)
              │              │                    Phase 3      Phase 4
              ▼              ▼
Phase 2   m-07 (#48)   m-03 (#47) ∥ m-04 (#46)
                              │         │
                              └────┬────┘
                                   ▼
Phase 2''                    m-06 (게시) ──────► 실제 게시물 산출
                                   │                    │
Phase 2'  m-05 (의존성) ───────────┘                    ▼
                                              d-01 ──► d-02
                                        (그 전에는 examples/ 픽스처)
```

> **Andrew 는 지금 착수할 수 있다** (리드 판정 D-28). 계약(`api-contracts.md` + `schemas/`)과 픽스처 2벌이 이미 있다.
> 다만 **실제 게시물 확인은 m-06 이후**다. 그 전까지는 `.agent-team/04-architecture/examples/empty-sink/` 를 픽스처로 쓴다.

---

# 2. 절대 제약 — 전 스토리 공통

## 2.1 파일 소유 경계 (`build-plan.md` §2·§3 · `task-graph.md` §4)

| 담당 | 쓰기 허용 | 절대 금지 |
|---|---|---|
| **Phillip** | `src/measurement/*.py` · `config/*.yaml` · `requirements*.txt` · `.gitignore` · `docs/measurement_contract.md` · `docs/gate1_checklist.md` · `docs/contracts/**` · `docs/event_schema.md` · `scripts/*` · `tests/test_{schema,sink,neutrality,economics,kpi_*,quality_*,publish_*,freeze,config_loader}.py` | `dashboard/**` · `src/{simulator,decision,diagnostics,orchestration}/**` |
| **Andrew** | **`dashboard/**` 하나뿐** (`AGENTS.md`·`CLAUDE.md` 최초 작성 포함 — 리드 판정 D-6) | `src/**` 편집 · `config/**` · `requirements*.txt` · `.gitignore` · `tests/**` |

**겹침 0 이 실행으로 증명되어 있다** — `python3 .agent-team/04-architecture/tools/check_ownership.py` → `PASS` · `Phillip 42 ∩ Andrew 29 = 0`.
**새 파일을 만들면 `tools/ownership.json` 의 `planned` 에 추가하고 다시 돌린다.**

## 2.2 봉인 파일 — C1 전원 수정 금지

```
tests/test_isolation.py              ← 격리 규칙 헌법
.github/workflows/isolation.yml      ← 위 검사의 CI 강제
src/simulator/** · src/decision/** · src/diagnostics/** · src/orchestration/**
Plan/**                              ← 서브모듈. 포인터도 커밋하지 않는다
AGENTS.md · src/AGENTS.md · src/*/AGENTS.md · src/*/CLAUDE.md   ← 기존 파일. W6 Timothy 만
README.md                            ← W6 Timothy 만
```

**예외 하나** — **신규 디렉터리의 지침 파일은 봉인 대상이 아니다** (리드 판정 D-6, `task-graph.md` §4).
`dashboard/AGENTS.md`·`dashboard/CLAUDE.md` 의 **최초 작성은 Andrew 소유**이며 디렉터리 생성과 같은 작업 단위다.

## 2.3 git · 이슈 권한 — **L1(제안만)**

| 등급 | 허용 | 승격 조건 |
|---|---|---|
| **L1 (기본)** | 읽기 · `status`/`diff`/`log` · 브랜치·커밋·PR·이슈 **초안 제안** | — |
| L2 | 브랜치 생성 · commit · push | 사용자가 **"커밋해" / "푸시해"** 를 명시 |
| L3 | 이슈 생성·수정 · PR 생성 | 사용자가 **"이슈 만들어" / "PR 올려"** 를 명시 |
| **금지(항상)** | merge · Issue close · 브랜치 삭제 · `push --force` · `reset --hard` · `rebase` | 매번 개별 승인 |

- **승격을 스스로 추론하지 않는다.** 한 번의 승격은 그 작업 범위에서만 유효하다.
- `main` 에 직접 커밋하지 않는다. 브랜치는 `<type>/<short-kebab-description>`.
- `git add -A` 를 쓰지 않는다. **경로를 명시해 스테이징한다.**
- `git add Plan` (서브모듈 포인터)은 사용자 명시 지시 시에만.

## 2.4 `Ecommerce_Service` — 읽기 전용

**파일 변경 0건.** 별도 저장소이고 사용자가 명시적으로 제외했다 (charter §5).
읽는 것은 허용된다 — 토큰 생성기 조사(Andrew) · 커머스 갭 확인(Phillip). **편집이 필요해지면 멈추고 보고한다.**

증명 방법: `git -C ../Ecommerce_Service status --porcelain` 이 **빈 출력**.

## 2.5 정직성 — AGENTS.md

1. **미실행 검증을 통과로 표시하지 않는다.** 실행 불가는 `BLOCKED` 로 **이유와 함께** 기록한다.
2. **결함을 조용히 고치지 않는다.** 발견 → Issue 기록 → 수정 → 재시험.
3. **결손을 조용히 0 으로 채우지 않는다.** 명시적으로 기록하고 의존 지표는 계산 불가로 표시한다.
4. **존재하지 않는 명령을 문서·게이트·PR 본문에 쓰지 않는다.**
5. **비밀값·생성물을 커밋하지 않는다.**

---

# 3. 실행 가능한 검증 — 오늘 이 저장소에 **하나뿐이다**

```bash
python3 -m unittest discover -s tests        # 기준선 46건 · 회귀 0
python3 -m unittest tests.test_isolation -v  # 격리 6건
```

**2026-09-11 라이브 실행 확인:** `Ran 46 tests in 0.026s / OK`

부수 스크립트 (실재 확인함):

```bash
python3 scripts/gen_event_schema_doc.py      # docs/event_schema.md 재생성
python3 scripts/bench_sink.py 20000 30       # 기준선 4,200,000건 / 64.7초 / 112.6MB
python3 .agent-team/04-architecture/tools/check_ownership.py   # 소유 겹침 0
```

> **lint · build · 타입 검사는 정의되어 있지 않다** (charter §6.3).
> **아직 존재하지 않는 명령 — 문서에 "실행했다"로 쓰지 않는다:**
> - `python3 -m src.measurement.publish …` — **m-06 에서 신설**
> - `python3 -m src.measurement.freeze record …` — **m-09 에서 신설**
> - `npm run dev` · `npm run tokens:generate` — **d-01 에서 신설**
> - `python3 .agent-team/04-architecture/tools/validate_examples.py` — 존재하나 **`jsonschema` 가 저장소 환경에 없다.** 스크래치패드 venv 실행분은 저장소 검증으로 계산하지 않는다

**환경 실측 (2026-09-11):**

| 항목 | 값 |
|---|---|
| 로컬 Python | **3.14.6** (CI 는 3.12) |
| `pyarrow` | **미설치** (`ModuleNotFoundError`) |
| `PyYAML` | **미설치** |
| `jsonschema` | **미설치** |
| Node · npm | **v24.15.0** · 11.12.1 |
| AI_ROI HEAD | `3ba2d34133fba8c2f14a43547b32ff122f306b72` |
| `Plan` 서브모듈 | `c46aee5eed00193b9331403645b8dbccaef52278` |
| `Ecommerce_Service` HEAD | `6b186d0f20a3d134389ef84b490d9a374c760e37` |

---

# 4. ★ 이 사이클에서 가장 위험한 다섯 줄

W2 가 규율을 스키마로 만들었다. **그 스키마를 되돌리는 방법은 전부 "예외를 막으려는 선의"에서 나온다.**

| # | 한 줄 | 어디서 | 무엇이 끝나나 |
|---|---|---|---|
| **1** | `value ?? 0` | 대시보드 | **USP-1 전체.** `(null).toLocaleString()` 이 던지므로 구현자가 예외를 막으려고 쓴다 |
| **2** | `if source == COMMERCE: return unavailable(...)` | `economics.py` | **창구 중립성.** 커머스가 `unit_cost` 를 넣어도 코드가 계속 거부한다 |
| **3** | `cogs = order_amount * 0.74` | `economics.py` | **PRD §65 가드레일.** `contribution_profit` 이 `revenue` 의 상수배가 되어 `revenue_up_profit_down` 이 원리적으로 참이 될 수 없다 |
| **4** | `if not lock_file.exists(): return` | `test_freeze.py` | **봉인 검사.** 봉인하지 않은 상태가 초록으로 보인다 |
| **5** | `except Exception: pass` · `.get(k, 0)` | 어디든 | **정직성 전체.** 조용히 도는 코드가 조용히 틀린 값을 만든다 |

> **1번이 최대 위험이다** (W2 종료 시 Jonnathan 지목, `wave-log.md` "W5 최대 위험").
> 계약이 아무리 정직해도 화면의 한 줄이 전부 무너뜨린다. 같은 부류: `value || 0` · `Number(value)` · `parseFloat(v) || 0` · `counts[k] || 0` · `filter(d => d.value > 0)` · `value.toFixed(1)`.

---

# 5. 어휘 정본 — 겹치면 **계약이 이긴다** (리드 판정)

기획 문서(`03-service-planning/`)와 게시물 계약(`04-architecture/schemas/`)이 같은 것을 다르게 정의하면 **계약이 정본이다.**
근거: **계약은 검증되고 문서는 검증되지 않는다.** 스키마는 위반을 거부하고, 문서는 어긋나도 아무것도 실패하지 않는다.

| 항목 | 기획 문서 | **정본 (계약)** |
|---|---|---|
| 사유 코드 | `kpi-definition-v1.md` §2.4 — **7종** | **`common.schema.json` — 9종** (`NOT_RUN` · `PRECONDITION_MISSING` 추가) |
| 지표 상태 | (없음) | `metric_value.status` — **5종** `ok`·`unconfirmed`·`unavailable`·`blocked`·`not_run` |
| 검사 상태 | `ui-spec.md` 개정 전 4종 | `data_quality_report.checks[].status` — **5종** (`vacuous` 포함) |
| 지표 이름·계산식 | `kpi-definition-v1.md` | `kpi_report.metrics[]` 의 `formula`·`definition_ref` 가 그 문서를 **인용**한다 |
| 문서 파일명 | task-graph §4 (`measurement-contract.md`) | **이슈 본문** (`docs/measurement_contract.md`) — 리드 판정 B-1/B-2 |

**사유 코드 9종 (`schemas/common.schema.json` `$defs.reason_code`):**

```
NO_SOURCE_EVENT · MISSING_FIELD · NO_COST_BASIS · NEEDS_TWO_STRATEGIES
NEEDS_MODEL_OUTPUT · PARAM_UNCONFIRMED · BLOCKED · NOT_RUN · PRECONDITION_MISSING
```

---

# 6. 확정 아키텍처 — 뒤집지 않는다

| # | 확정 | 근거 |
|---|---|---|
| **A8** | 대시보드는 **앱 하나** — `dashboard/` · Next.js · `:3001` · 결과 파일 읽기. **화면군만 둘** (관측 C1 / 결과 이후) | `usp.md` §1.2 |
| **A5** | 대시보드는 **파일 읽기만으로 충분**하다. API 서버를 두지 않는다 | `usp.md` §1.7 · `ADR-0001` · `DB-013` |
| **EC-1** | **원가율을 곱해 COGS 를 추정하지 않는다** | `economic-rule-v1.md` §3.2 |
| **EC-2** | 가르는 기준은 **출처가 아니라 `has_cost_basis(order)`** | `economic-rule-v1.md` §3.3 |
| **EC-9** | `economics.py` 는 `product_margin` 원가율을 **읽지 않는다** | `economic-rule-v1.md` §8 |
| **N-3** | 출처별 결과는 **분기가 아니라 입력 분할** | `ADR-0007` · `code-structure.md` §3 |
| **D-6** | `dashboard/AGENTS.md`·`CLAUDE.md` 최초 작성은 **Andrew 소유** | `task-graph.md` §4 |
| **J-1** | USP-1 대표 장면의 fixture 는 **손으로 쓴 JSON 이 아니라 실제 파이프라인 산출물** | `design-handoff.md` §2 |
| **D-16** | `discount` 부재는 **차단이 아니다.** 차단되는 것은 **결정의 부재** — 유도 규칙을 `ECONOMIC RULE v1` 에 넣는다 | `gate1-freeze-procedure.md` §3.2 |
| — | **C1 은 GATE 1 을 통과시키지 않는다.** 부분 봉인만 한다 | `gate1-lock-scope.md` §1 |

---

# 7. 검색으로 확인한 버전 — **검색한 것만 적는다**

2026-09-11 WebSearch + 로컬 실측. **`dependency-plan.md` §3.3 이 "구현 시점에 해석해 넣고 그 결과를 PR 에 기록한다"고 했으므로, 아래는 참고값이고 확정값은 구현자가 설치해 기록한다.**

## 7.1 Python

| 패키지 | 검색 확인 | 이 저장소에 의미 |
|---|---|---|
| **pyarrow** | 최신 **25.0.1** (2026-08-10). 25.0.0 은 2026-07-10, 222 issues / 268 commits | `sink.py` Parquet 경로. **`==` 로 정확 고정** — 버전이 바뀌면 같은 데이터에서 다른 바이트가 나올 수 있고 `NFR-001` SHA-256 대조가 무의미해진다 |
| pyarrow ↔ Python 3.14 | **cp314 휠 존재** (25.0.1). 3.10~3.14 지원 | **로컬 3.14.6 에서 설치 가능.** CI 3.12 는 문제없다 |
| **PyYAML** | 6.0.2 에 **직접 취약점 없음**(Snyk). 단 **CVE-2026-24009** — `yaml.FullLoader` 를 통한 RCE (Docling 사례). 완화는 **`SafeLoader` 사용** | ★ **`config_loader.py` 는 `yaml.safe_load()` 만 쓴다.** `yaml.load(..., Loader=yaml.FullLoader)` · `yaml.unsafe_load` 금지 — §8 |
| **jsonschema** | ⚠ **최신 버전을 검색으로 확정하지 못했다** (문서 사이트가 4.22.x 계열을 보인다). **설치해 해석한 값을 쓴다.** Draft 2020-12 지원은 확인됨 — `referencing.jsonschema.DRAFT202012` | `requirements-dev.txt` 전용 (결정 D-21). 우리 스키마가 draft 2020-12 다 |

## 7.2 Node (`Ecommerce_Service/package.json` 실측 + 검색)

| 항목 | 값 | 출처 |
|---|---|---|
| `next` | **16.3.4** | 커머스 실측. 검색: 16.3.4 가 2026-08-31 최신 stable, Next 16 은 LTS |
| `react` · `react-dom` | **19.2.8** | 커머스 실측 |
| `tailwindcss` · `@tailwindcss/postcss` | **^4** | 커머스 실측. `@theme inline` 이 Next 16 + React 19 와 호환 확인 |
| `typescript` | **^5** (Next 16 최소 5.1.0) | 커머스 실측 + 검색 |
| `eslint` · `eslint-config-next` | **^9** · **16.3.4** | 커머스 실측 |
| `js-yaml` | **4.3.2** (devDependency) | 커머스 실측 — 토큰 생성기의 유일한 의존 |
| `pretendard` | **1.3.9** | 커머스 실측 |
| **Node 최소 버전** | **>= 20.9.0** (Node 18 미지원) | 검색. 로컬은 v24.15.0 |

## 7.3 ★ Next.js 16 breaking change — Andrew 가 실제로 밟는 것

| 변경 | 우리에게 |
|---|---|
| **비동기 Request API** — `params`·`searchParams`·`cookies()`·`headers()` 의 동기 호환 shim 이 **16에서 제거**됐다. 동기 접근은 이제 **throw** 한다 | 동적 라우트를 쓰면 `await params` 가 필수다. **C1 의 8화면은 전부 정적 경로라 해당 없다** — 그래도 동적 라우트를 추가하면 즉시 걸린다 |
| **`next lint` 제거** | **`npm run lint` 를 `next lint` 로 쓰지 않는다.** 커머스는 `"lint": "eslint"` 를 쓴다. **C1 은 Node lint 를 CI 에 도입하지 않는다** (`dependency-plan.md` §5) — 없는 게이트를 만들지 않는다 |
| **Turbopack 기본** — 커스텀 webpack 설정은 **무시된다** | 커스텀 webpack 설정을 쓰지 않는다 |
| parallel-route slot 에 `default.js` 필수 | 관측 화면군은 parallel route 를 쓰지 않는다 |
| `revalidateTag` 두 번째 인자 필수 | **캐시를 쓰지 않는다** (`force-dynamic`). 해당 없다 |
| `next/image` 기본값 변경 (`minimumCacheTTL` 4h, `qualities [75]`) | 관측 화면군에 이미지가 없다 |

---

# 8. `config_loader.py` 보안 규약 — 검색 결과 반영

**CVE-2026-24009 는 라이브러리 버그가 아니라 로더 선택의 문제다.** `yaml.FullLoader` 는 조작된 페이로드로 임의 객체를 생성할 수 있다.

```python
# ✅ 이것만 쓴다
data = yaml.safe_load(path.read_text(encoding="utf-8"))

# ❌ 금지
yaml.load(text)                              # 구버전에서 unsafe
yaml.load(text, Loader=yaml.FullLoader)      # CVE-2026-24009 경로
yaml.unsafe_load(text)
```

`config/economic_config.yaml` · `config/gate1_lock.yaml` 은 이 저장소가 만드는 파일이지만, **로더 선택은 파일 출처와 무관한 습관의 문제**다. 안전한 쪽을 기본으로 둔다.

> **YAML 파서를 자체 구현하지 않는다** (`exceptions.md` §4).
> *"부분 구현 파서는 조용히 다른 값을 읽는다."* 경제 규칙 config 에서 그것은 치명적이다. PyYAML 이 없으면 `ConfigError` 로 멈춘다.

---

# 9. PR 체크리스트 — 전 W5 PR 공통 (`build-plan.md` §5)

```markdown
## 검증
- [ ] `python3 -m unittest discover -s tests` — 통과 / 총 N건 / **skip M건 (사유: …)**
- [ ] `python3 -m unittest tests.test_isolation -v` — 통과 (6건)
- [ ] 기준선 46건 대비 회귀 0
- [ ] 의존성 설치 **없이** 위 둘이 통과 (A7-1 · A7-2)
- [ ] 의존성 설치 **후에도** 통과 (A7-3) — 미실행이면 BLOCKED
- [ ] `python3 .agent-team/04-architecture/tools/check_ownership.py` — PASS

## 경계
- [ ] 내 소유 밖 파일 변경 0건 — `git diff --name-only` 를 본문에 첨부
- [ ] `Ecommerce_Service` 변경 0건 — `git -C ../Ecommerce_Service status --porcelain` 빈 출력
- [ ] `Plan/` 변경 0건 · 서브모듈 포인터 스테이징 0건
- [ ] 봉인 파일 변경 0건 (`tests/test_isolation.py` · `.github/workflows/isolation.yml`)

## 정직성
- [ ] 결손을 0으로 채운 곳 0건
- [ ] 미실행 검증을 통과로 적지 않았다
- [ ] 존재하지 않는 명령을 문서에 쓰지 않았다
```

**PR 본문 필수 항목** (`docs/GIT_WORKFLOW.md` §5): 연결 Issue · 변경 요약 · **파트 격리 영향** · **봉인 영향** · 테스트 결과 · 수동 검증 방법 · 남은 위험·미결정.

**커밋 규약** (`docs/GIT_WORKFLOW.md` §3): `type: 한글 설명` — **scope 를 제목에 넣지 않는다.** 본문 없이 제목 한 줄. 요구사항 ID 는 괄호로 — `(M-2)`.

---

# 10. 사용자·리드 결정 대기 — W5 착수 전 확인 필요

**스토리파일은 각 결정의 두 갈래를 모두 적었다.** 임의로 정하지 않는다.

| # | 항목 | 막는 스토리 | W2 추천 |
|---|---|---|---|
| **D-1** | 원가 근거 없는 주문의 COGS 처리 | m-03 | ⑴ 계산 불가 (EC-1·EC-2) |
| **D-2** | 환불 이벤트를 GATE 1 전에 추가하는가 | m-03 · m-09 | ⑴ 가정 `A-REFUND` 로 Lock |
| **D-3** | `shipping_subsidy` 필드 부재 처리 | m-04 · m-08 | ⑴ 규칙 유도값 + `derived: true` |
| **D-4** | KPI Lock 시점 정본 충돌 | m-04 · m-09 | ⑴ 계산 계약=GATE 1 / 역할 배정=GATE 2 |
| **D-5** | 이탈 임계값 28/42/60 을 C1 에서 Lock 하는가 | m-04 · m-09 | ⑴ Lock 하지 않고 방식만 |
| **D-7** | C1 에서 부분 Lock 을 **실행**하는가 | m-09 | ⑴ G-1~G-16 충족 후 실행 |
| **D-8** | `EVENT SCHEMA v1` Lock 범위를 `events` 로 한정 | m-09 | ⑴ 한정 |
| **D-9** | `#46` 범위 재단 (`M-4b` 분리) | m-04 | ⑴ 분리 — **이슈 조작은 L3** |
| **D-10** | `AIROI-M8` (게시 계약) 이슈 신설 | m-06 | ⑴ 발행 — **L3** |
| **D-16** | `discount` 필드 부재 처리 | m-03 · m-08 | ⑴ 규칙 유도 + `ECONOMIC RULE v1` 에 조항 |
| **D-17** | `results/` 를 `.gitignore` 에 넣는가 | m-06 | ⑶ 넣되 증거 사본은 `.agent-team/` |
| **D-19** | **`tests-with-deps.yml` 신규 워크플로** | m-05 | ⑴ 만든다 — **사용자 확인 후** |
| **D-20** | `docker-compose.yml` C1 도입 | (없음) | ⑵ C1 범위 밖 |
| **D-22** | `test_dashboard_isolation.py` C1 도입 | d-01 | ⑴ **W6 Matthias + 사용자 승인** |
| **D-26** | `gate1_lock.yaml` 위치 | m-09 | ⑴ `config/` |
| ~~**B-11**~~ | ~~`headline_code`~~ | — | ★ **판정됨 (2026-09-11)** — 계약을 고친다. §11.1 |

---

# 11. 리드 판정 3건 (2026-09-11) · 남은 미해결 1건

## 11.1 판정된 것 — W5 가 **고친다**

| # | 항목 | 판정 | 반영 |
|---|---|---|---|
| **B-11** | `headline_code` 에 `REJECTED_EVENTS` 부재 | ★ **화면 우회를 쓰지 않고 계약을 고친다.** `docs/contracts/**` 는 **Phillip 소유**이므로(`check_ownership.py` 확인) W5 권한 안이다. **enum 8종 + 우선순위를 계약이 정의**한다 | **m-06 §4.8 · AC-4b · T1** / **d-02 §4.8**(코드→문구 매핑만) |
| **G-8** | 파생 상태 기록 경로 | ★ **④ 게시 시점 계산.** `EventType` 16→19 는 `EVENT SCHEMA v1` 실질 변경이라 불가. `at_risk`·`churn` 은 이미 스키마에 있는 원천에서 **유도되므로 계산해 게시하면 스키마를 바꾸지 않고 정보가 산다** | **m-04**(분포 지표 3종 정의) · **m-06 §4.13**(게시 형식) · **m-08 §4.5①**(계약 문장) · **m-09**(`scope_note`) |
| **Q-2** | 품질 계약 결함 3건 | ★ **한 스토리로 묶어 고친다.** Q-1(18종) · Q-2(`status`↔`reason_code` 스키마 제약) · Q-3(`reported_checks` 등식) | **m-07 §7.2 · AC-8b · T5b** |

### ★ G-8 의 조건 셋 — 어기면 판정의 의미가 사라진다

| # | 조건 |
|---|---|
| ① | **`derived: true` + `derivation`**(계산식) 필수 — 저장된 사실과 구분 |
| ② | **`DB-012` 위반이 아니다** — 계산하는 쪽은 `measurement` 이고 **대시보드가 아니다** |
| ③ | ★ **Feature 로 쓰지 않는다.** `tests/test_schema.py:188-196` 이 **그대로 통과해야 한다** — 라벨과 동어반복(PRD Risk 7) |

### ★ Q-3 은 **JSON Schema 로 표현할 수 없다**

`reported_checks == len(checks)` — **draft 2020-12 에 교차 필드·배열 길이 비교 키워드가 없다.** (`$data` 는 Ajv 확장이지 표준이 아니다.)
**→ 스키마에 적으려 시도하지 않는다.** 게시 자기검증(`ContractViolation` → fail closed) + 테스트로 막고, **애초에 `len(checks)` 로 산출해 상수를 두 번 적지 않는다.**

## 11.2 ★ 남은 미해결 1건 — X-5 · 수집 0건의 "중단 vs 활동 없음"

**계약으로 풀 수 없다.** heartbeat 레코드가 필요한데:
1. `event_type` 16종을 늘리는 것은 **`EVENT SCHEMA v1` 의 실질 변경**이고 `FREEZE-003` 비용이 붙는다
2. Sink 밖의 별도 레코드로 두려면 **커머스와 시뮬레이터 양쪽이 써야 하는데 커머스는 편집 금지**다
3. C1 에는 그것을 검증할 데이터가 없다

**해결하지 않는다. 사실을 그대로 싣는다** — 확정 처리:
- `ingestion_report.totals.ingestion_days_gap` → **공백이 몇 개인지는 안다**
- `ingestion_report.totals.ingestion_gap_attribution` → `not_run` + `PRECONDITION_MISSING` — **그것이 무엇인지는 모른다**
- `notices` 의 `INGESTION_GAP_UNDECIDABLE`
- 화면 문구: **`수집 0건 · 활동 없음과 수집 중단을 현재 데이터로 구분할 수 없습니다`**

> **"활동 없음"이라고 쓰지 않는다.** 관측하지 않은 것을 단정하는 것이고 **0 채우기와 같은 종류의 잘못**이다.

## 11.3 리드 지시 — `customers` 부재

`kpi-definition-v1.md:149` 가 `cohort_retention_rate[m]` 을 `✅`(계산 가능)로 적었으나 **`signup_date` 가 `EVENT_FIELDS` 에 없다**(실행 확인).
*"이벤트는 '무언가 한 고객'만 보여주지 **전체 고객 명부가 아니다**."*

**→ `cohort_retention_rate`·`repurchase_rate`·`P_eligible` 계열을 `PRECONDITION_MISSING` 으로 재분류하고 조치에 `Ecommerce_Service #29`**(*"feat: 고객 모델에 가입일 추가와 라이프사이클 기준 확보"*, OPEN 라이브 확인)를 적는다. **m-04 AC-3b.**

# 11.4 ★★ D2 를 두 층으로 재정의한다 (Thomas 메타 지적 · 리드 지시)

> *"인용 경로 45종 전수 존재 검사는 **경로가 존재하는지**만 봤고, 인용한 **값**이 계약에 실재하는지는 보지 않았습니다. C-1·C-2·N-8 세 건 모두 `grep` 한 번이면 잡혔습니다."*

**`[Source: path#section]` 이 경로만 검증하면 없는 필드·없는 enum 값을 인용해도 통과한다.**
**C-1(`value_formatted`)이 정확히 그렇게 빠져나갔다** — 경로(`dashboard-agents-design-constraints.md`)는 실재했고 그 안의 코드도 실재했지만, **그 코드가 쓰는 필드가 계약에 없었다.**

| 층 | 검사 | 도구 |
|---|---|---|
| **D2a · 경로 실재** | 인용한 파일이 있는가 | `grep -ho '\[Source: [^]]*\]' … \| sed … \| while read p; do [ -e "$p" ]…` |
| **D2b · 값 실재** ★ | 스토리가 **게시물의 형태라고 주장하는 키·enum 값**이 계약·픽스처·`sink.manifest()` 에 실재하는가 | 아래 |

**D2b 대상 — "게시물 형태를 주장하는 자리"만 본다:**
1. 스토리의 `json`/`jsonc` 코드블록 안의 **키**(`"key":`)
2. 같은 블록 안의 **대문자 상수 문자열**(enum 후보)
3. `artifact.field` 형태의 **점 경로 인용**
4. ★ **`ts`·`tsx`·`js`·`jsx` 코드블록의 `<식별자>.<프로퍼티>` 접근** *(regate 1 신설 · Thomas NR-4)*

> ### ★★ 4번이 없으면 **이 도구가 자기 창립 사례를 못 잡는다**
> D2b 는 C-1 때문에 만들었는데, **C-1 의 증거는 `ts` 코드블록 한 줄**이다:
> ```ts
> const display = m.status === 'ok' ? m.value_formatted : EM_DASH;
> ```
> 1차판은 `json`/`jsonc` 와 백틱 점 경로만 봤다. **즉 C-1 을 오늘 다시 넣어도 통과시켰다.**
> **검사를 만들면 그 검사가 계기를 잡는지부터 확인한다** — m-06 §4.14 의 *"실패해야 실패한다"* 와 같은 규율이다.

**도구:** `.agent-team/03-story-engineering/tools/d2b_value_existence.py` — **저장소에 넣었다.** 재게이트마다 `python3 .agent-team/03-story-engineering/tools/d2b_value_existence.py` 로 돌린다. *(이 저장소의 실행 가능한 검증 명령은 `python3 -m unittest discover -s tests` 뿐이다. 이 스크립트는 **게이트 보조 도구**이지 제품 검증이 아니다.)*

**대조 집합:** `schemas/*.json` 의 전 `properties` + 전 `enum`/`const` · `examples/**.json` 의 전 키 · **`sink.py` 의 식별자(AST 추출)**
**오탐 필터:** 파일명(확장자) · python 점 경로 · JSON Schema 메타 키워드(`if`·`then`·`required`·…) · npm 스크립트 키 · **JS 호스트 객체**(`console`·`Math`·`JSON`…) · **JS 표준 메서드**(`map`·`toFixed`·`then`…)

> **오탐 필터가 없으면 못 쓴다.** 1차 시도는 659종 중 238건을 냈고 대부분 npm 패키지·디자인 토큰이었다. **정밀도가 낮은 검사는 아무도 안 본다.**

**W3 실행 결과 ② (2026-09-11 · 재게이트 regate 1 · `ts` 블록 포함):**

```
계약 프로퍼티 176 · enum 148 · 픽스처 키 208 · sink.py 식별자(AST)

① 게시물 키          270종 검사 → 4건
② enum 값             18종 검사 → 1건
③ ts/tsx/js 프로퍼티  10건 검사 → 3건   ← ★ 신설

  ① d-02  rounded.full            오탐 — Plan/DESIGN.md:118 디자인 토큰
  ① m-06  counts.ingested_events  ★ 의도 — §4.8.1 이 "택하지 않는다"고 적으며 인용
  ① m-06  limit_note              ★ 의도된 신설 (N-8)
  ① m-06  value_formatted         ★ 의도된 신설 (C-1)
  ② m-06  REJECTED_EVENTS         ★ 의도된 신설 (B-11)
  ③ d-01  m.value_formatted       ★ C-1 창립 사례 — 이번에 처음 잡혔다
  ③ d-02  m.value_formatted       ★ 동일
  ③ m-06  m.value_formatted       ★ 동일
```

**→ 오탐 1 · 의도된 신설 6 · 의도된 인용 1 · 의도하지 않은 결함 0.**

> ⚠ **1차의 *"남은 것 0건"* 은 대상이 좁아서 나온 0 이었다.** `ADR-0010` 의 `vacuous` 와 같은 종류의 0 이다 —
> **검사는 돌았지만 대상 집합에 그 코드블록이 없었다.** **재게이트마다 이 도구를 돌리되, 대상 목록을 먼저 본다.**

# 12. D3 신선도 — `source_hash` 계산 방법

각 스토리파일 프론트매터의 `source_hash` 는 **그 스토리가 인용한 상류 산출물의 합산 해시**다. 재현 가능하다.

```
1. 대상 파일 경로를 저장소 루트 기준 상대경로로 만든다
2. 경로를 sorted() 로 정렬한다 (유니코드 코드포인트 오름차순)
3. 각 파일에 대해  f"{path}\n{sha256_hex(file_bytes)}\n"  를 순서대로 이어붙인다
4. 그 바이트열의 SHA-256 앞 16자리를 source_hash 로 쓴다
5. 파일이 없으면 해시 자리에 "MISSING" 을 넣는다 — 조용히 빼지 않는다
```

**5번이 중요하다.** 파일이 사라진 것과 안 본 것을 같게 만들지 않는다. `source_files` 개수가 프론트매터에 함께 있다.

| 스토리 | `source_hash` | 파일 수 |
|---|---|---|
| project-context (전체 상류) | `968e6c27ef3ef83d` | 62 |
| m-01 | `f9b50547bbb181fb` | 17 |
| m-02 | `71caee737d21c72b` | 19 |
| m-03 | `55894406a021293f` | 18 |
| m-04 | `f8a349053598902b` | 19 |
| m-05 | `4ab8babbc1e25356` | 16 |
| m-06 | `453eccc2172bc7d2` | 24 |
| m-07 | `85e5519b725c4840` | 17 |
| m-08 | `82ffbab104b22402` | 17 |
| m-09 | `a20dd972916f0565` | 17 |
| d-01 | `5cf5ccb05350cf24` | 23 |
| d-02 | `edb8e795ec6bf1c4` | 27 |

> ### ★ 재현 가능성 보완 (Matthias 항목5)
> 1차 컴파일은 **알고리즘과 개수만** 적고 **대상 파일 목록을 적지 않았다.**
> **→ 제3자가 재계산할 수 없었다.** §D3 이 적은 용도(*"열었을 때 다시 계산해 다르면 낡았다"*)를 **구현자가 수행할 수 없었다.**
> **각 스토리 말미에 `<!-- source_hash inputs: … -->` 주석으로 전 목록을 기록했다.** 11종 전부 재계산해 프론트매터와 일치를 확인했다.

**용도:** 상류 문서가 바뀌면 해시가 달라진다. W5 구현자가 스토리를 열었을 때 해시를 다시 계산해 다르면 **스토리가 낡았다는 뜻**이고, 리뷰어에게 보고한다.
**한계:** 해시는 *"바뀌었다"* 만 알려주고 *"무엇이 왜"* 는 모른다. `git diff` 로 확인한다.

---

# 13. W3 가 실행으로 확인한 것 — 스토리에 반영됨

| # | 확인 | 방법 | 결과 |
|---|---|---|---|
| 1 | 기준선 46건 | `python3 -m unittest discover -s tests` | **OK · 46건** |
| 2 | 의존성 3종 부재 | `python3 -c "import …"` | pyarrow · yaml · jsonschema **전부 미설치** |
| 3 | 이슈 10건 OPEN | `gh issue list` | `#42`~`#49` · `#53` · `#54` 전부 **OPEN** |
| 4 | `scripts/` 2종 실재 | `ls scripts/` | `gen_event_schema_doc.py` · `bench_sink.py` |
| 5 | 커머스 스택 버전 | `Ecommerce_Service/package.json` (읽기) | next 16.3.4 · react 19.2.8 · js-yaml 4.3.2 |
| 6 | **토큰 생성기가 `dashboard/scripts/` 깊이에서 동작** | 스크래치패드 재현 실행 | ✅ `tokens:generate` · `tokens:check` **통과** · 306줄 · dashboard 토큰 5건 |
| 7 | ★ **`verify.mjs` 는 그대로 이식하면 깨진다** | 같은 실행 | ❌ **ENOENT `dashboard/Plan/DESIGN.md`** — §14 |
| 8 | 위의 최소 수정 후 통과 | 같은 실행 | ✅ **15 scenarios passed** |

---

# 14. ★ W3 신규 발견 — `verify.mjs` 경로 깊이 (실행 확인)

Jonnathan 이 **미검증으로 남긴 항목**이다 (`design-handoff.md` §1.1: *"`verify.mjs`의 `root`는 `"../../"`이므로 경로 깊이가 다르다 — 같이 확인할 것"*).
**확인했다. 실제로 깨진다.**

`Ecommerce_Service/scripts/tokens/verify.mjs` 의 `root` 사용처는 둘이고 **요구하는 기준점이 서로 다르다**:

```js
const root = fileURLToPath(new URL('../../', import.meta.url));      // 8행
const source = await readFile(join(root, 'Plan/DESIGN.md'), 'utf8');  // 9행 ← 저장소 루트를 원한다
… spawnSync(…, [join(root, 'scripts/design-tokens.mjs'), …])          // 15행 ← dashboard/ 를 원한다
```

`dashboard/scripts/tokens/verify.mjs` 에 두면 `root = dashboard/` 가 되어:
- 15행은 **맞다** (`dashboard/scripts/design-tokens.mjs`)
- 9행은 **틀리다** — `dashboard/Plan/DESIGN.md` 를 찾고 `Plan/` 은 저장소 루트에 있다

```
Error: ENOENT: no such file or directory,
  open '…/dashboard/Plan/DESIGN.md'
```

**→ `root` 를 바꾸면 15행이 깨진다. 9행만 고쳐야 한다.**

```js
const source = await readFile(join(root, '../Plan/DESIGN.md'), 'utf8');   // ← 한 줄
```

**실행 확인:** `15 scenarios passed; failed input and --check preserved output.`

> ### 이것이 `token-strategy.md` K 규약과 충돌한다
> `token-strategy.md` §2.1 과 `design-handoff.md` §1.1 이 *"**스크립트 본문은 한 줄도 고치지 않는다**"* 라고 적었다.
> **`design-tokens.mjs`·`render.mjs`·`resolve.mjs` 3개는 그 말이 맞다** — 인자만 바꾸면 그대로 돈다(실행 확인).
> **`verify.mjs` 1개는 틀리다.** 한 줄을 고치지 않으면 `tokens:test` 가 실행 자체를 못 한다.
>
> **d-01 스토리는 이 한 줄 수정을 작업으로 포함하고, 수정 사실을 파일 머리 주석에 남기게 했다.** 이식 원본과의 차이를 숨기지 않는다.

**이식 원본 추적 정보 (ADR-0006 이 요구하는 출처 주석용):**

```
Ecommerce_Service HEAD  6b186d0f20a3d134389ef84b490d9a374c760e37   (2026-09-11 실측)

sha256  b17ab2e4122b8c467d45e537b57b81195eaec1cca2d3219d338f9e6baed29c66  scripts/design-tokens.mjs
sha256  c0ed6edc7970a93091c4a8ca49382181dde5a0abf0f6e256f29b2929e4ad3272  scripts/tokens/render.mjs
sha256  ce07d675c9b86b94d3d6debeabde0836bee684fa87a6aa79d3d47c7ab1f3ba2a  scripts/tokens/resolve.mjs
sha256  d777aa8812e0e32ddde75a2c903f8eeabcafaad6bb5008c3dddb4615a0a8c27f  scripts/tokens/verify.mjs
sha256  810415a43e2ac0f21a9597cfc14fb418be3ab8ffd0ad39a9ed6a26dadaeef1da  src/styles/design-rules.css
```

---

# 15. 미정으로 남긴 것 — W3 이 정하지 않는다

| 항목 | 왜 |
|---|---|
| 브랜치 이름 · PR 분할 단위 | git 작업은 L1. 사용자 지시 후 · 구현자 판단 |
| `pyarrow`·`PyYAML` 의 **정확한 버전** | 설치하지 않았다. 구현자가 CI 와 같은 Python 3.12 에서 해석해 넣고 **PR 에 기록**한다 (`dependency-plan.md` §3.3) |
| Next.js·React 의 **정확한 lock 버전** | Andrew 가 설치 시점에 해석해 기록한다. §7.2 는 커머스 실측 참고값이다 |
| `headline_code` 8종화 여부 (B-11) | **리드 판정.** 계약 변경은 W2 산출물 수정이고 W3 권한이 아니다 |
| `#43`·`#44` close 여부 | charter Q4 — Issue close 는 개별 승인 |
| 차트 라이브러리 | Jonnathan 이 미정으로 남겼다. d-02 는 **막대만** 쓰므로 라이브러리 없이 가능하다는 선택지를 제시했다 |
| Bootstrap 재현 seed 규약 | 실험 판정 지표가 C1 에서 계산되지 않는다. 정할 근거가 없다 |

<!-- ════════ source_hash inputs (D3 · Matthias N-1') ════════
     계산법: 이 문서 §12  ·  파일 62종
     ★ 이 문서 자신의 목록이다. '각 스토리 말미에' 라고만 적어 자신이 범위 밖으로 빠졌던 자리다.
        확정 헌법이고 구현자가 가장 먼저 읽는 문서이므로 같은 이유로 닫는다.

     .agent-team/00-plan/charter.md
     .agent-team/00-plan/task-graph.md
     .agent-team/03-service-planning/README.md
     .agent-team/03-service-planning/core-features.md
     .agent-team/03-service-planning/economic-rule-v1.md
     .agent-team/03-service-planning/gate1-lock-scope.md
     .agent-team/03-service-planning/issue-priority.md
     .agent-team/03-service-planning/kpi-definition-v1.md
     .agent-team/03-service-planning/service-stories.md
     .agent-team/03-service-planning/user-stories.md
     .agent-team/03-service-planning/usp.md
     .agent-team/04-architecture/README.md
     .agent-team/04-architecture/adr/ADR-0001-publish-not-api.md
     .agent-team/04-architecture/adr/ADR-0002-results-measurement-subdir.md
     .agent-team/04-architecture/adr/ADR-0003-metric-value-shape.md
     .agent-team/04-architecture/adr/ADR-0004-ci-new-workflow-file.md
     .agent-team/04-architecture/adr/ADR-0005-gate1-lock-record.md
     .agent-team/04-architecture/adr/ADR-0006-token-generator-port.md
     .agent-team/04-architecture/adr/ADR-0007-blind-calculation.md
     .agent-team/04-architecture/adr/ADR-0008-basis-required.md
     .agent-team/04-architecture/adr/ADR-0009-blocker-chain.md
     .agent-team/04-architecture/adr/ADR-0010-vacuous-pass.md
     .agent-team/04-architecture/api-contracts.md
     .agent-team/04-architecture/architecture-overview.md
     .agent-team/04-architecture/build-plan.md
     .agent-team/04-architecture/code-structure.md
     .agent-team/04-architecture/dashboard-architecture.md
     .agent-team/04-architecture/data-model-erd.md
     .agent-team/04-architecture/data-quality-design.md
     .agent-team/04-architecture/dependency-plan.md
     .agent-team/04-architecture/design-patterns.md
     .agent-team/04-architecture/exceptions.md
     .agent-team/04-architecture/gate1-freeze-procedure.md
     .agent-team/04-architecture/schemas/common.schema.json
     .agent-team/04-architecture/schemas/data_quality_report.schema.json
     .agent-team/04-architecture/schemas/field_coverage_report.schema.json
     .agent-team/04-architecture/schemas/freeze_status.schema.json
     .agent-team/04-architecture/schemas/index.schema.json
     .agent-team/04-architecture/schemas/ingestion_report.schema.json
     .agent-team/04-architecture/schemas/kpi_report.schema.json
     .agent-team/04-architecture/schemas/rejection_report.schema.json
     .agent-team/04-architecture/service-sequences.md
     .agent-team/07-design/README.md
     .agent-team/07-design/contract-reconciliation.md
     .agent-team/07-design/dashboard-agents-design-constraints.md
     .agent-team/07-design/design-handoff.md
     .agent-team/07-design/design-system/components.md
     .agent-team/07-design/design-system/state-tokens.css
     .agent-team/07-design/design-system/token-strategy.md
     .agent-team/07-design/missing-state-spec.md
     .agent-team/07-design/ui-spec.md
     .agent-team/07-design/ux-flow-map.md
     AGENTS.md
     docs/GIT_WORKFLOW.md
     src/AGENTS.md
     src/measurement/__init__.py
     src/measurement/schema.py
     src/measurement/sink.py
     tests/__init__.py
     tests/test_isolation.py
     tests/test_schema.py
     tests/test_sink.py

     → source_hash = 968e6c27ef3ef83d
     ════════════════════════════════════════════════════ -->
