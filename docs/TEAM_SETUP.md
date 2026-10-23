# C2 착수 지침 — 두 팀, 하나의 저장소

> 읽는 순서: `README.md` → **이 문서** → `docs/DECISION_RECORDS.md` → 자기 이슈
>
> 사람이든 에이전트(Claude · Codex · 그 외)든 같다. 이 문서는 **팀·경로·태스크**를 말하고,
> `DECISION_RECORDS.md` 는 **왜 그렇게 만들었는지 남기는 법**을 말한다. 둘 다 필요하다.
> 기계가독 판본은 `docs/team_boundaries.json`, 강제는 `tests/test_team_boundaries.py`.

---

## 0. 30초 요약

| | |
|---|---|
| **무엇을 만드나** | C1 이 만든 측정 계층 위에 **고객 시뮬레이터**와 **의사결정 시스템**을 올린다 |
| **왜 팀을 나누나** | 시뮬레이터는 **정답을 만드는 쪽**, 의사결정은 **정답을 맞히는 쪽**이다. 수험생이 답안지를 보면 점수는 100 점이 나오지만 실력은 0 이다 |
| **두 팀이 만나는 곳** | `src/measurement/` — C1 에서 완성됐고 **읽기만** 한다 |
| **지금 상태** (2026-09-29) | 측정 계층·대시보드·교환 파일 소비(커머스·시뮬레이터) 완료. 리드 몫 선행 이슈 0건 — **두 팀 모두 바로 착수할 수 있다** |

```
src/measurement/    ✅ 완성 — 계약, 두 팀 공용 (읽기 전용)
src/simulator/      ⬜ 비어 있음 — 시뮬 팀
src/decision/       ⬜ 비어 있음 — 시스템 팀
src/orchestration/  ⬜ 비어 있음 — 시스템 팀
src/diagnostics/    ⬜ 비어 있음 — 시뮬 팀 (두 GATE 이후)
```

---

## 1. 팀과 사람

| 팀 | 구성원 | 태스크 | 소유 |
|---|---|---|---|
| **시뮬레이터** (출제자) | `limtjdghks`(성환) · `1anminJ`(민정) | `S1`~`S8` | `src/simulator/` `src/diagnostics/` `data/hidden/` `data/ground_truth/` |
| **시스템** (수험생) | `Danto7632`(인성) · `kwung0206`(광진) | `D1`~`D12` | `src/decision/` `src/orchestration/` `results/` |

### ★ 이슈는 태스크 목록이 아니다

각 이슈는 세 가지를 함께 담는다:

| | |
|---|---|
| **정해야 하는 것** | 임의로 고르면 안 되는 값·구조·방식. 왜 임의로 정하면 안 되는지와 함께 |
| **조사해야 하는 것** | 결정 전에 찾아봐야 할 것. **근거를 못 찾은 것도 결과다** |
| **증거로 남길 것** | 체크박스 + **결정 기록**(`DR-*.md`) · 모델이면 **모델 카드**(`MC-*.md`) |

체크박스를 다 채워도 결정 기록이 없으면 **그 태스크는 끝난 것이 아니다.** 제도 전문은
`docs/DECISION_RECORDS.md`, 검사는 `python3 -m unittest tests.test_decision_records`.

**태스크 번호는 팀 안에서 자유롭게 옮긴다.** `S3` 을 성환이 맡았다가 민정이 이어받아도 되고 둘이 나눠도 된다 — **소유는 팀 단위이지 사람 단위가 아니기 때문이다.** 팀을 넘는 이동만 안 된다.

---

## 2. ★ 경계 — 이 프로젝트의 핵심

### 서로 읽지 않는다

| 시뮬 팀이 읽지 않는 것 | 시스템 팀이 읽지 않는 것 |
|---|---|
| `results/**` | `data/hidden/**` |
| `src/decision/**` | `data/ground_truth/**` |
| `docs/model_report.md` | `src/simulator/**` (`api.py` 포함) |
| `docs/uplift_analysis.md` | `src/diagnostics/**` |
| `docs/ab_test_report.md` | |
| `docs/sprint1_report.md` (스프린트 1 결과 보고 — 모델 리포트) | |

**가장 위험한 누수는 코드가 파일을 훔쳐보는 것이 아니다.** AI 성능이 낮다는 이유로 시뮬레이터를 고치는 것이다 (PRD §80 Risk 1). 사람도 에이전트도 이 유혹에 빠진다.

> **AUC · Qini · Incremental Profit 이야기가 시뮬레이터 작업 중에 나오면 멈추고 보고한다.**
> 시뮬레이터가 맞춰야 할 기준은 AI 성능이 아니라 **생성 이탈률 15~25%**(SIM-005)와 **처치 강도 가드레일**(ATE 3~6%p · 쿠폰 사용률 5~20% · Sleeping Dog 8~15%)이다. 쿠폰 사용률 분모는 "쿠폰 처치군 전체 중 유효기간 내 사용"이며, 25~40% 에서 외부 근거로 교정했다(2026-10-22 사용자 확정, `docs/research/data_grounding.md` §3-1).

### 무엇이 강제되고 무엇이 안 되나

| | 강제 수단 |
|---|---|
| import 경계 · 데이터 경로 | `tests/test_isolation.py` — CI 4 잡 전부에서 돈다 |
| **한 브랜치가 두 팀 경로를 동시에 건드림** | `tests/test_team_boundaries.py` — **커밋 전 변경도 본다** |
| 파일을 *읽는* 것 | ❌ **기계가 못 잡는다.** `src/*/AGENTS.md` 와 리뷰가 잡는다 |

**읽기는 막을 수 없다.** 그래서 이 문서가 있다.

---

## 3. 착수 절차

### 3.1 준비물

| | |
|---|---|
| GitHub 권한 | `AI_ROI` · `Plan`(private 서브모듈) · `Ecommerce_Service` — 네 명 모두 이미 있다 |
| `git` · [`gh`](https://cli.github.com) | `gh auth login` 을 한 번 해 둔다. 이슈·PR 을 터미널에서 본다 |
| **Python 3.12** | **전체 파이프라인의 지원 런타임**이다 — CI · Dockerfile 과 같은 판. 고정 의존성(numpy · scipy · shap)이 3.12 이상에서만 설치된다. 3.10 은 **측정 계층 하한**(`python-compat.yml` 이 의존성 없이 확인)이지 전체가 도는 판이 아니다(`docs/decisions/DR-207-python-runtime.md`) |
| Node.js | `dashboard/` 를 건드릴 때만 |

### 3.2 받기 · 환경 · 첫 검증

```bash
git clone https://github.com/72offsuit/AI_ROI.git && cd AI_ROI
git submodule update --init                  # Plan/ (기획 문서 PRD/SRS · 공통 규약)

python3.12 -m venv .venv && source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements.txt -r requirements-dev.txt    # ★ 두 벌 다

python3 -m unittest discover -s tests        # 끝줄이 OK (skipped=3) 이어야 한다
```

★ **`skipped=` 수까지 본다.** `requirements-dev.txt`(`jsonschema`·`referencing`)를 빠뜨리면 계약 스키마 검증이 전부 skip 되고 **끝줄은 여전히 `OK` 다** — 실제로 그렇게 계약 위반을 놓쳤고 CI 가 잡았다(`#99`). 두 벌을 설치한 상태의 정상은 `skipped=3` 이고, 90 안팎이면 의존성이 빠진 것이다. **`skip` 은 통과가 아니다.**

의존성 없이도 스위트는 돌아야 한다(격리 CI 잡이 그렇게 돈다) — 그래서 테스트가 실패하지 않고 skip 으로 빠진다. 그것이 로컬 검증을 의존성 없이 해도 된다는 뜻은 아니다.

### 3.3 읽기 — 이 순서로

```bash
cat AGENTS.md                        # 저장소 전체 규칙
cat src/AGENTS.md                    # 파트 경계
cat src/<내 파트>/AGENTS.md           # 내 파트 (simulator · decision · orchestration · diagnostics)
cat docs/DECISION_RECORDS.md         # 결정 기록 제도
cat docs/measurement_contract.md     # 이벤트 기록 계약 (두 팀 공용, 읽기 전용)
ls  docs/contracts/measurement-publish/v1/   # 게시물 계약
gh issue view <내 첫 이슈 번호>
```

### 3.4 작업 → PR

```bash
git switch -c feat/s1-simulator-skeleton     # <type>/<short-kebab>. main 직접 커밋 금지
# … 작업 …

# 푸시 전 반드시
python3 -m unittest discover -s tests                   # 전건 통과 · skipped=3
python3 -m unittest tests.test_team_boundaries          # 한 브랜치가 두 팀 경로를 건드리지 않았는가
python3 .agent-team/04-architecture/tools/check_ownership.py   # 새 파일이 소유자를 갖는가 (CI 에 없다)

git add <경로를 명시한다>                                 # git add -A 지양
git commit -m "feat: 시뮬레이터 골격과 api.py 계약"          # 제목 한 줄
git push -u origin feat/s1-simulator-skeleton
gh pr create --base main                                 # 본문은 docs/GIT_WORKFLOW.md §5
```

`check_ownership.py` 가 "소유자 없음"을 내면 `.agent-team/04-architecture/tools/ownership.json` 의 `rules` 에 새 파일을 한 줄 등록한다(`pattern` · `owner` · `why`). 파트 디렉터리(`src/simulator/**` 등)는 C1 때 통째로 등록돼 있어 그 아래 새 파일은 걸리지 않는다 — **걸리는 것은 주로 새 테스트 파일(`tests/test_*.py`)이다.**

| PR 본문에 반드시 | |
|---|---|
| 연결 이슈 | `Closes #75` |
| 파트 격리 영향 | 어느 파트를 건드렸고 경계를 넘지 않았는가 |
| 봉인 영향 | GATE 1·2 봉인 항목을 건드렸는가 |
| 테스트 결과 | `unittest` 끝줄 (`skipped=` 포함) |
| 결정 기록 | 이 PR 이 만든 `docs/decisions/DR-*.md` · `MC-*.md` |

**병합 기준** — CI `Tests` 통과 · **리뷰 승인 1건** · squash merge. ★ **리뷰는 같은 팀 동료가 한다.** 다른 팀 사람은 그 코드를 읽으면 안 된다(§2) — 시뮬 PR 은 성환·민정이, 시스템 PR 은 인성·광진이 서로 본다.

---

## 4. 두 팀이 만나는 지점 — 계약

**`src/measurement/` 가 유일한 접점이다.** C1 에서 완성됐고 두 팀 다 **읽기만** 한다.

```
시뮬레이터  ──write_events()──▶  EventSink  ──▶  data/raw/
                                                    │
시스템      ◀──── 이벤트만 ────────────────────────┘
```

| 계약 | 내용 |
|---|---|
| `EventType` 16 종 | `session_start` `page_view` `search` `product_view` `return_visit` `add_to_cart` `remove_from_cart` `checkout_start` `purchase` `campaign_exposed` `push_sent` `coupon_exposed` `coupon_clicked` `coupon_use` `review` `cs_contact` |
| `EVENT_FIELDS` 22 컬럼 | `core` 4 (전 이벤트 필수) · `session` 3 · `product` 4 · `order` 2 · `marketing` 5 · `meta` 4 |
| 식별자 형식 | `customer_id` `^C\d{8}$` · `session_id` `^S-C\d{8}-\d{13}$` · `order_id` `^O\d{8}-\d{6}$` · `treatment_id` `^T[0-4]$` 등 9 종 |
| 출처 판별 | `simulator_version` · `random_seed` 가 있으면 시뮬레이터, 둘 다 `null` 이면 커머스 (`MEA-002`) |
| 타임존 | 오프셋 있는 표기만 허용(`+09:00` · `Z` 둘 다). 오프셋 없으면 **거부**. Sink 가 KST 로 정규화 |
| 교환 파일 | 주문·품목(주문 시점 원가)·고객·카탈로그 묶음. **커머스** `data/commerce/` · **시뮬레이터** `data/simulator_exchange/` — 같은 계약(`docs/contracts/commerce-exchange/v1/`), 묶음은 자기 출처 이벤트에만 붙는다. 있으면 COGS·기여이익과 `DQ-02`·`03`·`05`·`09` 가 계산된다. ★ **시뮬레이터 팀은 구매 이벤트와 함께 이 묶음을 낸다** — 규칙은 계약 README §11(#117). **실험 판정에는 시뮬레이터 생성분만 쓴다**(`MEA-002`) — 커머스 데이터는 관측·대조용이다 |

**계약을 바꾸려면 양 팀 합의 + `FREEZE-003`**(버전 상향 → 전 데이터 재생성 → Baseline 부터 재실행). 한 팀이 단독으로 고치지 않는다.

### 시뮬레이터의 공개 인터페이스

`orchestration` 은 `src/simulator/api.py` **만** 호출한다. 내부(`_internal`)는 보지 않는다.

```python
init(seed, num_customers, profile)
advance(days)
snapshot() / restore(snap)        # 같은 시점 · 같은 난수에서 여러 전략을 비교하기 위해
apply_treatment(assignments)
events(until)                      # measurement 계약 형식
metrics(start, end)
```

---

## 5. 태스크

### 시뮬레이터 팀 — `S1`~`S8`

| # | 이슈 | 담당 | 내용 | SRS | 선행 |
|---|---|---|---|---|---|
| **S1** | #75 | 성환 | 골격 · `api.py` 계약 확정 · 재현성 · 시간 제어 | SIM-011 · 012 · 013 | — |
| **S2** | #76 | 성환 | Persona 6+ · Hidden Trait 분포 | SIM-001 · 002 | S1 |
| **S3** | #77 | 민정 | 규모 · 배정 (20K+ / 12M+, T/C 각 10K+) | SIM-003 · 004 · 010 | S2 |
| **S4** | #78 | 민정 | 행동 규칙 · 이벤트 생성 (8+ 종) → 계약 형식으로 기록 | SIM-006 · 007 | S2 |
| **S5** | #79 | 성환 | 이탈 생성 15~25% · 설정화 | SIM-005 · 009 | S4 |
| **S6** | #80 | 민정 | 처치 반응 (Positive/Neutral/Negative) · `ground_truth` 산출 | SIM-008 | S3 · S5 |
| **S7** | #81 | 성환 | 가드레일 검증 · **GATE 1 봉인** | SIM 전체 | S1~S6 |
| **S8** | #82 | 민정 | `src/diagnostics/` — Qini_oracle · PEHE · corr(τ̂,τ) · 4분면 | — | **GATE 1 · GATE 2 이후** |

### 시스템 팀 — `D1`~`D12`

| # | 이슈 | 담당 | 내용 | SRS | 선행 |
|---|---|---|---|---|---|
| **D1** | #83 | 인성 | Feature 파이프라인 30+ (RFM · 행동변화 · 세션품질 · 시퀀스 · 결측/이상치) | FE-001~010 | 계약만 있으면 착수 |
| **D2** | #84 | 광진 | Churn ML — 트리 2+ · 불균형 · 5-Fold · SHAP · 임계값 | ML-001~008 | D1 |
| **D3** | #85 | 광진 | Churn DL — 시퀀스 · Early Stopping · 앙상블 | DL-001~007 | D1 |
| **D4** | #86 | 인성 | Uplift — 모델 2+ · CATE · 4분면 · Qini/AUUC | UP-001~007 | D1 |
| **D5** | #87 | 광진 | CLV — 예측 · 검증 · 고가치 판정 | CLV-001~005 | D1 |
| **D6** | #88 | 인성 | 세그먼테이션 6+ · 우선순위 점수 | SEG-001~005 | D2 · D4 · D5 |
| **D7** | #89 | 광진 | 전략 정의 S0~S5 · **Baseline 봉인(GATE 2)** | RET · STR · BASE | D6 |
| **D8** | #90 | 인성 | 예산 최적화 · What-if · CLI | OPT-001~006 | D7 |
| **D9** | #91 | 광진 | `src/orchestration/` 실행 루프 (snapshot/restore 기반 전략 비교) | — | D7 |
| **D10** | #92 | 인성 | A/B — 검정력 · 통계검정 · CI · p-value | AB-001~006 | D9 |
| **D11** | #93 | 광진 | ROI 집계 · 해석 규칙 · 코호트/퍼널 분석 | ROI-001~006 · ANA-001~006 | D9 |
| **D12** | #94 | 인성 | 모니터링(드리프트·성능추이·알림) · 문서 6종 | MON · DOC | D10 · D11 |

### 착수 순서 — 두 팀은 **병렬로 시작한다**

계약(`src/measurement/`)이 이미 완성돼 있어 **서로를 기다리지 않는다.** 시스템 팀은 `S4` 의 실제 이벤트가 나오기 전까지 **계약 형식의 픽스처**로 `D1` 을 만들 수 있다 — 형식 예시로 커머스가 실제로 만든 이벤트 `tests/fixtures/commerce_exchange_v1/events.jsonl` 이 있다(26건, 커머스 출처라 시뮬레이터 메타 필드는 `null`). **첫 태스크는 `S1`(#75)과 `D1`(#83)이다.**

```
시뮬   S1 ─ S2 ─┬─ S3 ─┐
                └─ S4 ─ S5 ─┴─ S6 ─ S7(GATE 1) ──┐
시스템 D1 ─┬─ D2 ─┐                                │
           ├─ D3 ─┼─ D6 ─ D7(GATE 2) ─ D8         ├──→ S8
           ├─ D4 ─┤                  └─ D9 ─┬─ D10 ─┬─ D12
           └─ D5 ─┘                          └─ D11 ─┘
```

**`S7`(GATE 1)이 `D9`(실행 루프)의 실질 선행이다** — 봉인되지 않은 시뮬레이터로 전략을 비교하면 결과가 재현되지 않는다.

### ★ `S8` 은 **두 팀을 가로질러** 마지막에 온다

`S8`(채점자)의 선행은 `S7`(GATE 1) **하나가 아니라** `D7`(GATE 2)까지 **둘 다**다. 그래서 그림에서 유일하게 두 줄이 만나는 지점이다.

채점자는 정답지(`data/ground_truth/`)와 답안(`results/`)을 **양쪽 다 본다.** 두 GATE 가 닫히기 전에 착수하면 그 시점엔 시뮬레이터도 전략도 아직 바꿀 수 있어, 채점을 보고 고치는 길이 열린다 — 이 프로젝트가 막으려는 바로 그 누수다. 두 GATE 뒤에는 **보아도 손댈 것이 없다.**

> 라벨도 그래서 다르다. `S8`(#82)은 `gate/after-both` 이고 `gate/blocks-gate2` 가 **아니다.** GATE 2 를 막는 것이 아니라 **GATE 2 에 막혀 있다** — 방향이 반대이며, 반대로 읽으면 일정이 거꾸로 잡힌다.

---

## 6. 봉인 (GATE)

| | 언제 | 무엇이 잠기나 | 이후 변경 비용 |
|---|---|---|---|
| **GATE 1** | `S7` | Persona 구성비 · Hidden Trait 분포 · 행동 규칙 · Churn 임계값 · Treatment 반응 · 경제 파라미터 · Event Schema | `FREEZE-003` — 버전 상향 → **전 데이터 재생성 → Baseline 부터 전 전략 재실행** |
| **GATE 2** | `D7` | `decision/strategies/rule_based.py` · 예산 상한 | 같음 |

**GATE 1 은 부분 봉인(`PARTIAL_FREEZE`)이다.** 완전히 잠긴(`LOCKED`) 항목은 아직 0 종이고, 측정 계층 항목은 `PENDING`·`PARTIAL`, 시뮬레이터 항목 5 종은 `OUT_OF_SCOPE` 다 — `S7` 이 그것을 채운다. 정본 4종(`schema.py` · `economic_config.yaml` · `event_schema.md` · `measurement_contract.md`)의 해시가 기록돼 있어, 이 넷을 고치면 재봉인(사람 서명)이 필요하다. 마지막 재봉인 2026-09-28(`#109`).

봉인 기록은 `config/gate1_lock.yaml` 이며 **사람이 손으로 쓰지 않는다** (`freeze.record()` 가 쓴다). 봉인 이후 정본 파일이 바뀌면 해시 대조가 실패하고 CI 가 잡는다.

---

## 7. 이 저장소가 지키는 규율

C1 에서 반복해 확인된 것들이다. 새 코드에도 그대로 적용된다.

| | |
|---|---|
| **결손을 0 으로 채우지 않는다** | 근거가 없으면 계산 불가로 표시한다. `?? 0` · `.get(k, 0)` · `or 0` 이 이 규율을 깨는 전형이다 |
| **미실행을 통과로 적지 않는다** | 실행하지 못한 검사는 `BLOCKED` 로 사유와 함께. `not_run` 은 `pass` 가 아니다 |
| **세 번째 값** | 참/거짓으로 표현 못 하는 상태에는 세 번째 값을 준다 — `vacuous` · 계산 불가 · `met: null` · `verification: not_run` |
| **선언에는 대조 장치를 붙인다** | 문서·주석·카탈로그가 "이렇다" 고 적으면 그것을 실제와 맞대는 검사가 있어야 한다. C1 의 major 10 건 중 4 건이 이것이 없어서 생겼다 |
| **결함을 조용히 고치지 않는다** | 발견 → Issue → 수정 → 재시험 |
| **경로를 명시해 스테이징한다** | `git add -A` 지양 |

### 권한 (`docs/GIT_WORKFLOW.md` §6)

- **에이전트 기본 권한은 L1(제안만).** commit · push · Issue · PR 생성은 **사람이 명시한 뒤에만**
- `main` 직접 커밋 금지. 브랜치는 `<type>/<short-kebab-description>`
- **merge · Issue close · 브랜치 삭제 · `push --force` · `reset --hard` · `rebase` 는 항상 개별 승인**

---

## 8. 막혔을 때

| 상황 | 어디로 |
|---|---|
| 계약이 애매하다 | `docs/measurement_contract.md` → 그래도 애매하면 **양 팀 합의 전까지 멈춘다** |
| 다른 팀 파일을 봐야 할 것 같다 | **보지 말고 보고한다.** 계약으로 풀 수 있는지가 먼저다 |
| 경계 테스트가 실패한다 | 브랜치를 팀별로 나눈다. 두 팀에 걸치는 작업은 애초에 한 PR 이 아니다 |
| 시뮬레이터 작업 중 성능 이야기가 나온다 | **멈추고 보고한다** (PRD §80 Risk 1) |
| 봉인된 파일을 고쳐야 한다 | `FREEZE-003` 절차. 사람의 서명이 필요하다 |

---

## 9. AI 에이전트로 작업할 때

Claude Code · Codex 모두 된다. 저장소의 `AGENTS.md`(Claude 는 `CLAUDE.md` 를 거쳐)를 자동으로 읽고, `src/` 아래로 들어가면 파트별 `AGENTS.md` 가 규칙을 더한다.

- **처음에 자기 팀과 이슈 번호를 말해 준다.** 예: *"나는 시뮬레이터 팀이다. #75 를 한다. docs/TEAM_SETUP.md 부터 읽어라."*
- **에이전트 권한은 L1(제안만)이다.** 커밋·푸시·이슈·PR 은 사람이 "커밋해"·"PR 올려" 라고 말한 뒤에만, 병합·이슈 닫기·브랜치 삭제는 매번 따로 승인한다
- 시뮬레이터 작업 중 에이전트가 AUC·Qini·Incremental Profit 을 꺼내면 **멈추게 한다** (§2)
- "통과했다" 는 보고를 받으면 **`skipped=` 수를 직접 확인한다** (§3.2)

### 선택 — BATHOS

리드가 쓰는 에이전트 운영 도구다. **없어도 작업할 수 있다** — C2 는 웨이브가 아니라 이슈 단위로 진행하고, 규칙은 저장소(`AGENTS.md`·테스트·CI)가 강제한다. 쓰면 얻는 것:

| | |
|---|---|
| 안전 훅 | 강제 푸시·하드 리셋·`rm -rf` 같은 파괴 명령을 에이전트가 실행하기 전에 막는다 |
| 세션 저장·복원 | `/save-session` → 다음에 `/cold-start` 로 어디까지 했는지 그대로 이어간다 |
| 역할 에이전트 | 코드 리뷰(`thomas-code-reviewer`)·보안 점검 등을 따로 불러 쓸 수 있다 |

**설치 — 저장소 밖 상위 폴더에 한다.** AI_ROI 안에 설치하면 `.claude/` 가 저장소에 섞이고, `AI_ROI/.agent-team/`(C1 의사결정 기록, 커밋돼 있다)을 덮어쓸 수 있다.

```bash
# 작업 폴더 — 상위 폴더가 BATHOS 워크스페이스, 저장소는 그 아래
mkdir -p ~/72offsuit && cd ~/72offsuit
git clone https://github.com/72offsuit/AI_ROI.git          # §3.2 는 여기서 한다

# 엔진 빌드 + 워크스페이스에 주입 (Rust · jq 필요)
git clone https://github.com/taxideftis/bathos.git ~/bathos
~/bathos/install.sh --into ~/72offsuit                      # Windows: .\install.ps1 -Into <경로>\72offsuit
echo 'export BATHOS_BIN="$HOME/bathos/core/target/release/bathos"' >> ~/.zshrc
"$BATHOS_BIN" doctor                                         # 배선 점검

cd ~/72offsuit && claude                                     # ★ 상위 폴더에서 연다
```

플랫폼별 전 과정은 BATHOS 저장소의 `docs/macos-linux-install-kr.md` · `windows-install-kr.md` · `wsl-install-kr.md`.

**알려진 함정**

| | |
|---|---|
| **AI_ROI 안에서 `/team-kickoff`·`/wave*` 를 실행하지 않는다** | C1 기록(`AI_ROI/.agent-team/`)이 덮인다. C2 는 웨이브를 쓰지 않는다 |
| 병합한 브랜치가 `git branch -d` 로 안 지워진다 | squash 병합이라 git 이 병합으로 보지 않는다. `-D` 가 필요한데 안전 훅이 **의도적으로** 막는다 — 병합 커밋과 파일 차이가 없는지 확인한 뒤 사람이 직접 실행한다(Claude Code 에서는 `! git branch -D …`) |
| 문서를 고치는 셸 명령이 막힌다 | 안전 훅은 명령 **글자**를 본다. 편집할 본문에 위험 명령 문자열이 들어 있으면 오탐으로 막힌다 — 셸 대신 편집 도구로 고친다 |
| 리드의 `.claude/` 를 복사해 쓰지 않는다 | 리드 개인 도구 경로가 섞여 있다. 위 `install.sh` 로 새로 받는다 |

---

**정본** — `Plan/AI_Retention_ROI_PRD_v2.md` · `Plan/AI_Customer_Retention_ROI_SRS_v2.0.md` · `docs/data_spec.html`
**이 문서의 기계가독 판본** — `docs/team_boundaries.json`
