# 빌드 계획 — W5 소유 경계와 겹침 0 증명 (T2.12)

**작성** James (Role 4 · Architect) · 2026-09-11 · 사이클 C1
**전제** C1 의 W5 는 **Phillip(측정 계층) + Andrew(대시보드) 2인**이고 **Stephen 은 미가동**이다 (task-graph §1)
**출발점** task-graph §4 의 기존 경계. **T2.7 게시 계약이 추가한 파일까지 반영했다**

---

# 0. 요약

| | |
|---|---|
| W5 소유자 | **Phillip · Andrew** 2인 |
| 겹침 | **0 — 실행으로 증명함** (§4) |
| 소유 파일 | Phillip 42 · Andrew 29 · 봉인 17 · W6 Timothy 7 |
| 증명 도구 | `tools/check_ownership.py` + `tools/ownership.json` |
| 제품 코드 변경 | **0건** (§7) |

---

# 1. task-graph §4 대비 달라진 것

기존 경계를 뒤집지 않았다. **T2.7·T2.9·T2.11 이 만든 새 파일을 배정하고, 이슈 본문과 어긋난 파일명 2건을 바로잡았다.**

| # | 항목 | task-graph §4 | 이 문서 | 근거 |
|---|---|---|---|---|
| **B-1** | M-3 문서 파일명 | `docs/measurement-contract.md` | **`docs/measurement_contract.md`** | **이슈 `#45` 본문이 언더스코어로 지정.** 이슈가 작업 정의의 정본이다 |
| **B-2** | M-7 문서 파일명 | `docs/gate1-freeze.md` | **`docs/gate1_checklist.md`** | **이슈 `#49` 본문이 지정.** Joshua 의 `core-features.md` 도 같은 이름을 쓴다 |
| **B-3** | 게시 계약 스키마 | 없음 | `docs/contracts/measurement-publish/v1/**` → **Phillip** | T2.7 신설 |
| **B-4** | `config/gate1_lock.yaml` | 없음 | **Phillip** | T2.11 신설 (`ADR-0005`) |
| **B-5** | `.gitignore` | 미배정 | **Phillip 단독** | Andrew 가 필요로 하는 항목은 `dependency-plan.md` §5 에 미리 규정 → 두 사람이 같은 파일을 쓰지 않는다 |
| **B-6** | `dashboard/AGENTS.md`·`CLAUDE.md` | 리드 판정 D-6 | **Andrew** (디렉터리 생성과 같은 작업 단위) | task-graph §4 리드 판정 D-6 |
| **B-7** | `tests/test_dashboard_isolation.py` | 없음 | **봉인** (W6 Matthias + 사용자 승인) | `dashboard-architecture.md` §6.4 |
| **B-8** | `.github/workflows/tests-with-deps.yml` | 없음 | **봉인** (사용자 확인 후) | `dependency-plan.md` §2.3 · 결정 D-19 |
| **B-9** | `docker-compose.yml` | 없음 | **Phillip** (도입 결정 D-20 시에만) | Andrew 는 리뷰만 한다 |
| **B-10** | `docs/event_schema.md`·`scripts/*` | 미배정 | **Phillip** | `#54` 가 문서를 재생성한다 |

> **B-1·B-2 는 리드 확인이 필요하다.** 이슈 본문과 task-graph 가 어긋나 있고, 나는 **이슈 본문을 따랐다.** 반대로 정하려면 이슈 본문 수정이 필요하고 그것은 L1 권한 밖이다.

---

# 2. Phillip — W5-A / W5-B

## 2.1 배타적 소유 (쓰기)

```text
src/measurement/*.py            schema · sink · kpi · economics · validate ·
                                publish · freeze · config_loader · contracts · errors
config/*.yaml                   economic_config.yaml · gate1_lock.yaml
requirements.txt · requirements-dev.txt
.gitignore
docs/measurement_contract.md    (#45)
docs/gate1_checklist.md         (#49)
docs/contracts/**               게시 계약 JSON Schema
docs/event_schema.md            (#54 재생성)
scripts/gen_event_schema_doc.py · scripts/bench_sink.py
tests/test_schema.py · test_sink.py · test_neutrality.py · test_economics.py ·
      test_kpi_*.py · test_quality_*.py · test_publish_*.py ·
      test_freeze.py · test_config_loader.py · __init__.py
docker-compose.yml              (D-20 승인 시에만)
```

## 2.2 읽기 허용 / 절대 금지

| 읽기 허용 | 절대 금지 |
|---|---|
| `data/raw/` · `data/processed/` | `src/simulator/**` · `src/decision/**` · `src/diagnostics/**` · `src/orchestration/**` |
| `docs/event_schema.md` · `docs/data_spec.html` | `dashboard/**` |
| `Ecommerce_Service/**` (read-only) | `data/hidden/**` · `data/ground_truth/**` |
| `.agent-team/**` | `Ecommerce_Service` **편집** · `Plan/**` |
| — | `tests/test_isolation.py` · `.github/workflows/isolation.yml` |

## 2.3 작업 순서 — `gate1-lock-scope.md` §2.3 Phase 를 따른다

| Phase | 이슈 | 산출 | 차단 |
|---|---|---|---|
| **1** | `#53` ∥ `#54` | `sink.py`·`schema.py` 결함·값 강제 · `test_sink.py`·`test_schema.py` · `docs/event_schema.md` 재생성 | 없음 |
| **2** | `#46` ∥ `#47` | `kpi.py` · `economics.py` · `config_loader.py` · `errors.py` · `config/economic_config.yaml` · `test_kpi_*` · `test_economics` · `test_neutrality` | D-1 · D-2 |
| **2'** | T2.9 | `requirements.txt` · `requirements-dev.txt` | D-19 |
| **2''** | T2.7 | `contracts.py` · `publish.py` · `docs/contracts/**` · `test_publish_*` | 없음 |
| **2'''** | `#48` | `validate.py` · `test_quality_checks.py` | `#53` D1-2 (§6) |
| **3** | `#45` | `docs/measurement_contract.md` — **Lock 최종 검산** | `#54` · G-8 · G-9 · G-16 |
| **4** | `#49` | `freeze.py` · `docs/gate1_checklist.md` · `config/gate1_lock.yaml` · `test_freeze.py` | 앞 전부 · D-2·3·4·7·8·16 |

> **Phase 3 에서 표현력 공백이 드러나면 Phase 4 로 가지 않는다. 멈추고 보고한다.**

## 2.4 Andrew 를 막지 않기 위한 순서

**Andrew 는 T2.7 계약에 묶여 있다.** 계약 문서(`api-contracts.md` + `schemas/`)는 **이미 나왔으므로 Andrew 는 지금 착수할 수 있다.**
다만 실제 게시물이 있어야 화면을 확인할 수 있다 → **Phase 2'' 가 끝나면 Phillip 이 게시를 한 번 실행하고 `results/` 를 만든다.**
그 전까지 Andrew 는 **`.agent-team/04-architecture/examples/empty-sink/` 를 픽스처로 쓴다** (실제 게시물과 같은 스키마를 통과한 파일이다).

---

# 3. Andrew — W5-C

## 3.1 배타적 소유 (쓰기)

```text
dashboard/**        전체. AGENTS.md · CLAUDE.md 최초 작성 포함 (리드 판정 D-6)
```

**`dashboard/` 밖의 파일을 쓰지 않는다.** `.gitignore` 에 필요한 항목은 `dependency-plan.md` §5 에 규정되어 있고 **Phillip 이 넣는다.**

## 3.2 읽기 허용 / 절대 금지

| 읽기 허용 | 절대 금지 |
|---|---|
| `results/**` (게시물) | `src/**` **편집** |
| `data/processed/**` (C1 에서 쓰지 않음) | `data/raw/**` · `data/hidden/**` · `data/ground_truth/**` |
| `src/measurement/**` (계약 확인용 read-only) | `Ecommerce_Service` **편집** · `Plan/**` |
| `Plan/DESIGN.md` (토큰 정본, read-only) | `config/**` · `requirements*.txt` · `.gitignore` |
| `Ecommerce_Service/**` (토큰 조사, read-only) | `tests/**` |
| `.agent-team/04-architecture/**` · `07-design/**` | |

## 3.3 착수 조건과 산출

| 조건 | 상태 |
|---|---|
| T2.7 게시 계약 확정 | ✅ `api-contracts.md` + `schemas/` |
| 예시 픽스처 | ✅ `examples/empty-sink/` (7건 · 스키마 검증 통과) |
| 정보구조 (Jonnathan) | ⏳ T2.12~T2.14 |
| A8 판정 | ✅ 대시보드는 하나 |

**산출:** `dashboard/` 앱 골격 + 관측 화면군 6화면 + 토큰 파이프라인 이식 + `AGENTS.md`·`CLAUDE.md`.
**만들지 않는 것:** `(results)/` 디렉터리 · `DB-003`~`DB-010` 화면 · 이벤트 행 브라우저 · 실시간 갱신 · 인증.

---

# 4. ★ 겹침 0 증명

## 4.1 증명 방법

**주장하지 않고 실행한다.**

```bash
python3 .agent-team/04-architecture/tools/check_ownership.py
```

`tools/ownership.json` 이 규칙 47개를 담고, 검사기가 **네 종류의 경로 집합**에 대해 세 가지를 확인한다.

| 경로 집합 | 무엇 |
|---|---|
| 추적됨 (32) | `git ls-files` — 현재 저장소의 모든 파일 |
| 미추적 (83) | `git ls-files --others --exclude-standard` — `.agent-team/` 등 |
| 계획 (63) | W5 가 만들 파일 전부 (`ownership.json` `planned`) |
| 대조 (15) | **경계에서 헷갈리기 쉬운 경로** — 봉인 파일 · `dashboard/AGENTS.md` · `.gitignore` 등 |

| 검사 | 내용 |
|---|---|
| **① 겹침 0** | 어떤 경로도 **두 소유자의 규칙에 동시에 매칭되지 않는다** |
| **② 빠짐 0** | 모든 경로가 소유자를 갖는다 — *"규칙에 안 걸리니 아무나 쓴다"* 를 막는다 |
| **③ 봉인 격리** | 봉인 파일이 W5 소유자(Phillip·Andrew)에게 매칭되지 않는다 |

## 4.2 실행 결과 (2026-09-11)

```text
==================================================================
W5 파일 소유 경계 — 겹침 0 검사
==================================================================
검사 대상 178개 경로 (추적 32 · 미추적 83 · 계획 63 · 대조 0)

  andrew       29개
  phillip      42개
  sealed       17개
  team         83개
  timothy       7개

✅ ① 겹침 0 — 두 소유자의 규칙에 동시에 매칭되는 경로가 없다
✅ ② 빠짐 0 — 모든 경로가 소유자를 갖는다
✅ ③ 봉인 격리 — 봉인 파일이 W5 소유자에게 매칭되지 않는다

W5 소유자 간 교집합:
  Phillip 42개 ∩ Andrew 29개 = 0개

대조 경로 — 경계에서 헷갈리기 쉬운 것들의 판정:
  ✅ tests/test_isolation.py                                    → sealed
  ✅ tests/test_kpi_definitions.py                              → phillip
  ✅ tests/test_quality_checks.py                               → phillip
  ✅ dashboard/AGENTS.md                                        → andrew
  ✅ dashboard/CLAUDE.md                                        → andrew
  ✅ dashboard/src/lib/artifacts/read.ts                        → andrew
  ✅ src/measurement/AGENTS.md                                  → timothy
  ✅ src/measurement/schema.py                                  → phillip
  ✅ docs/event_schema.md                                       → phillip
  ✅ docs/measurement_contract.md                               → phillip
  ✅ config/economic_config.yaml                                → phillip
  ✅ .gitignore                                                 → phillip
  ✅ README.md                                                  → timothy
  ✅ src/simulator/AGENTS.md                                    → sealed
  ✅ docs/contracts/measurement-publish/v1/common.schema.json   → phillip

판정: PASS
```

*(`대조 0` 은 대조 경로 15개가 이미 추적·계획 집합에 포함되어 중복 추가되지 않았다는 뜻이다. 판정은 하단 대조 표에 개별로 출력된다.)*

## 4.3 왜 이 증명이 성립하는가 — 구조 논거

실행 결과는 "오늘 이 파일 목록에서 겹치지 않는다"를 보인다. **왜 앞으로도 겹치지 않는가**는 규칙의 구조가 답한다.

| 논거 | |
|---|---|
| **A** | 두 W5 소유자의 규칙은 **최상위 디렉터리가 서로소**다 — Phillip 은 `src/measurement/`·`config/`·`docs/`·`scripts/`·`tests/`·루트 3파일, Andrew 는 **`dashboard/` 하나뿐**이다 |
| **B** | Andrew 의 규칙은 `dashboard/**` **한 줄**이다. `dashboard/` 밖으로 나갈 패턴이 없다 |
| **C** | Phillip 의 규칙 중 `dashboard/` 로 시작하는 것이 **하나도 없다** |
| **D** | `tests/` 안에서 Phillip 과 봉인이 공존하지만 **파일명이 명시적으로 갈린다.** `test_isolation.py`·`test_dashboard_isolation.py` 는 정확한 파일명 규칙이고, Phillip 의 규칙은 `test_kpi_*.py` 처럼 접두어가 다르다 |
| **E** | `docs/` 안에서 Phillip 과 Timothy 가 공존하지만 **정확한 파일명 규칙끼리 갈린다** (`GIT_WORKFLOW.md` ↔ `measurement_contract.md` 등) |
| **F** | 검사기의 `*` 는 **경로 구분자를 넘지 않는다**(세그먼트 수 비교). `src/measurement/*.py` 가 `src/measurement/sub/x.py` 를 잡지 않는다 |

> **A·B·C 가 핵심이다. Andrew 의 쓰기 영역이 디렉터리 하나로 완전히 격리되어 있으므로 겹침이 생길 구조적 가능성이 없다.**
> 나머지 겹침 위험은 전부 `tests/`·`docs/` 안의 파일명 문제이고, 그것은 D·E 가 명시적 파일명으로 처리한다.

## 4.4 이 검사를 언제 다시 돌리나

**새 파일을 만들 때마다.** `ownership.json` 의 `planned` 에 추가하고 다시 돌린다.
**빠짐(②)이 나오면 그 파일은 소유자가 없다는 뜻이고, 두 사람이 동시에 만들 수 있는 파일이라는 뜻이다.**

---

# 5. PR 체크리스트 — W5 공통

**모든 W5 PR 본문에 아래를 실행 결과와 함께 기록한다.** 실행하지 않은 항목은 `BLOCKED` 로 사유와 함께.

```markdown
## 검증
- [ ] `python3 -m unittest discover -s tests` — 통과 / 총 N건 / **skip M건 (사유: ...)**
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

---

# 6. 이슈 간 차단 관계 — 순서를 지켜야 하는 이유

| 선행 → 후행 | 왜 |
|---|---|
| `#53` → `#48` | `DQ-10`·`DQ-11` 위반 데이터를 저장하려면 `strict=False` 경로가 필요한데 **지금 크래시한다** (`data-quality-design.md` §6) |
| `#53` → 데이터 생성 | D1-1 이 **데이터 소실형**이다. `data/raw` 에 쌓인 뒤 고치면 사라진 것은 안 돌아온다 |
| `#54` → `#45` | 계약 문서가 허용값·식별자 형식을 인용한다 (`#54` 본문) |
| `#54` → `#49` | 값 규약이 빠진 채 Lock 되면 되돌릴 수 없다 (`#54` 본문) |
| `#46`·`#47` → `#49` | `#49` 의 명시적 선행 (이슈 본문 의존성) |
| `#45` → `#49` | **Lock 최종 검산.** 계약 문서를 쓰는 행위가 스키마의 표현력을 검산한다 |
| T2.7 게시 → Andrew 화면 확인 | 실제 게시물이 있어야 확인된다. 그 전에는 예시 픽스처 |
| T2.9 의존성 → `DQ-17` 해소 | pyarrow 없이는 Parquet 재현성을 검증할 수 없다 |

---

# 7. ★ 이 웨이브의 변경 0건 증명

```text
$ git status --porcelain
?? .agent-team/

$ git -C Plan status --porcelain
(빈 출력)

$ git -C ../Ecommerce_Service status --porcelain
(빈 출력)
```

| 판정 | |
|---|---|
| 제품 코드(`src/` · `tests/` · `config/` · `docs/` · `scripts/`) 변경 | **0건** |
| `Plan/` 서브모듈 변경 · 포인터 스테이징 | **0건** |
| **`Ecommerce_Service` 변경** | **0건** — 토큰 파이프라인 조사는 읽기만 했다 |
| GitHub 이슈 생성·수정·close | **0건** — `gh issue list` · `gh issue view` (읽기)만 실행 |
| 추가된 것 | `.agent-team/04-architecture/` 아래뿐 (미추적) |

---

# 8. 결정이 필요한 항목

| # | 항목 | 선택지 | 추천 |
|---|---|---|---|
| **B-1/B-2** | M-3·M-7 문서 파일명이 task-graph §4 와 이슈 본문에서 다르다 | ⑴ 이슈 본문을 따른다 (`measurement_contract.md` · `gate1_checklist.md`) ⑵ task-graph 를 따른다 | **⑴.** 이슈가 작업 정의의 정본이고, Joshua 의 `core-features.md` 도 같은 이름을 쓴다. **리드 확인 필요** |
| **D-18** | `MetricStatus`·`ReasonCode` 를 `schema.py` 에 두는가 별도 `metrics.py` 에 두는가 | ⑴ `schema.py` (계약 어휘의 정본) ⑵ 별도 `metrics.py` | **⑴.** `code-structure.md` §4.2. 단 `schema.py` 는 Lock 대상이므로 **`#54` 와 같은 PR 에서** 손대는 편이 안전하다 |
| **D-28** | Andrew 착수 시점 | ⑴ 지금 (예시 픽스처로) ⑵ Phase 2'' 게시 후 | **⑴.** 계약과 픽스처가 이미 있다. Jonnathan 의 정보구조만 기다리면 된다 |

---

# 9. 미정으로 남긴 것

| 항목 | 왜 |
|---|---|
| Phillip·Andrew 의 브랜치 이름 | git 작업은 L1. 사용자 지시 후 |
| PR 분할 단위 | 이슈 단위가 자연스러우나 `#53`·`#54` 는 함께 갈 수도 있다. 구현자 판단 |
| `docker-compose.yml` 도입 여부 | 결정 D-20 |
| Stephen 재가동 시의 경계 | C1 미가동. 시뮬레이터 사이클에서 다시 그린다 |
