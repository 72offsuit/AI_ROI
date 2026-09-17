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
| **지금 상태** | 측정 계층·대시보드 완료. 나머지 네 파트는 **빈 디렉터리 + 지침 파일**뿐이다 |

```
src/measurement/    ✅ 10 모듈 · 7,600 줄 — 계약, 두 팀 공용 (읽기 전용)
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

**가장 위험한 누수는 코드가 파일을 훔쳐보는 것이 아니다.** AI 성능이 낮다는 이유로 시뮬레이터를 고치는 것이다 (PRD §80 Risk 1). 사람도 에이전트도 이 유혹에 빠진다.

> **AUC · Qini · Incremental Profit 이야기가 시뮬레이터 작업 중에 나오면 멈추고 보고한다.**
> 시뮬레이터가 맞춰야 할 기준은 AI 성능이 아니라 **생성 이탈률 15~25%**(SIM-005)와 **처치 강도 가드레일**(ATE 3~6%p · 쿠폰 사용률 25~40% · Sleeping Dog 8~15%)이다.

### 무엇이 강제되고 무엇이 안 되나

| | 강제 수단 |
|---|---|
| import 경계 · 데이터 경로 | `tests/test_isolation.py` — CI 4 잡 전부에서 돈다 |
| **한 브랜치가 두 팀 경로를 동시에 건드림** | `tests/test_team_boundaries.py` — **커밋 전 변경도 본다** |
| 파일을 *읽는* 것 | ❌ **기계가 못 잡는다.** `src/*/AGENTS.md` 와 리뷰가 잡는다 |

**읽기는 막을 수 없다.** 그래서 이 문서가 있다.

---

## 3. 착수 절차

```bash
git clone <repo> && cd AI_ROI
git submodule update --init          # Plan/ (private, 기획 문서)

# 1) 자기 파트 지침을 읽는다 — 이것이 실제 규칙이다
cat AGENTS.md                        # 저장소 전체
cat src/AGENTS.md                    # 파트 경계
cat src/<내 파트>/AGENTS.md           # 내 파트

# 2) 계약을 읽는다 (두 팀 공용, 읽기 전용)
cat docs/measurement_contract.md     # 이벤트 기록 계약
cat docs/event_schema.md             # 22 컬럼 · event_type 16 종
ls docs/contracts/measurement-publish/v1/   # 게시물 계약 9 종

# 3) 검증이 도는지 확인한다
python3 -m unittest discover -s tests        # 전부 통과해야 한다
python3 -m unittest tests.test_isolation -v  # 격리
python3 -m unittest tests.test_team_boundaries -v   # 팀 경계

# 4) 브랜치를 만든다 — <type>/<short-kebab>
git switch -c feat/s1-simulator-skeleton
```

### 푸시 전 반드시

```bash
python3 -m unittest discover -s tests                   # 전건 통과
python3 -m unittest tests.test_team_boundaries          # 경계를 넘지 않았는가
python3 .agent-team/04-architecture/tools/check_ownership.py
```

**의존성 설치 없이 도는 것이 원칙이다.** `pip install -r requirements.txt` 는 Parquet·YAML 경로를 검증할 때만 필요하고, 그 없이도 전체 스위트가 돌아야 한다(BLOCKED skip 으로 보고된다).

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

계약(`src/measurement/`)이 이미 완성돼 있어 **서로를 기다리지 않는다.** 시스템 팀은 `S4` 의 실제 이벤트가 나오기 전까지 **계약 형식의 픽스처**로 `D1` 을 만들 수 있다.

```
시뮬   S1 ─ S2 ─┬─ S3 ─┐
                └─ S4 ─ S5 ─┴─ S6 ─ S7(GATE 1) ─────────────── S8
시스템 D1 ─┬─ D2 ─┐
           ├─ D3 ─┼─ D6 ─ D7(GATE 2) ─ D8
           ├─ D4 ─┤                  └─ D9 ─┬─ D10 ─┬─ D12
           └─ D5 ─┘                          └─ D11 ─┘
```

**`S7`(GATE 1)이 `D9`(실행 루프)의 실질 선행이다** — 봉인되지 않은 시뮬레이터로 전략을 비교하면 결과가 재현되지 않는다.

---

## 6. 봉인 (GATE)

| | 언제 | 무엇이 잠기나 | 이후 변경 비용 |
|---|---|---|---|
| **GATE 1** | `S7` | Persona 구성비 · Hidden Trait 분포 · 행동 규칙 · Churn 임계값 · Treatment 반응 · 경제 파라미터 · Event Schema | `FREEZE-003` — 버전 상향 → **전 데이터 재생성 → Baseline 부터 전 전략 재실행** |
| **GATE 2** | `D7` | `decision/strategies/rule_based.py` · 예산 상한 | 같음 |

**C1 에서 GATE 1 은 부분 봉인(`PARTIAL_FREEZE`)까지 갔다.** 측정 계층 항목만 잠겼고 시뮬레이터 항목 5 종은 `OUT_OF_SCOPE` 다 — `S7` 이 그것을 채운다.

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

**정본** — `Plan/AI_Retention_ROI_PRD_v2.md` · `Plan/AI_Customer_Retention_ROI_SRS_v2.0.md` · `docs/data_spec.html`
**이 문서의 기계가독 판본** — `docs/team_boundaries.json`
