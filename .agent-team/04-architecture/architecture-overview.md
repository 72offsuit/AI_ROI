# 아키텍처 개요 — C1 측정 계층 + 관측 대시보드

**작성** James (Role 4 · Architect) · 2026-09-11 · BATHOS Lv3 · 사이클 **C1**
**정본** `Plan/AI_Retention_ROI_PRD_v2.md` v2.3 · `Plan/AI_Customer_Retention_ROI_SRS_v2.0.md` · `docs/data_spec.html` · `AGENTS.md` · `src/AGENTS.md`
**전제** Joshua 의 W2 기획 확정본 9종. 특히 **A8 판정(대시보드는 하나)** · `EC-1`·`EC-2`(원가 근거 규칙) · GATE 1 부분 봉인

---

# 1. 한 문단

C1 은 **측정 계층(창구)을 완주하고, 그것이 실제로 관측 가능함을 화면으로 증명한다.**
아키텍처의 중심 문제는 성능도 확장성도 아니다 — **계약이 한쪽 편을 들지 않게 하는 것**과 **결손이 조용히 0 이 되지 않게 하는 것** 둘이다.
이 문서군의 거의 모든 결정이 그 둘에서 나온다.

---

# 2. 시스템 컨텍스트

```text
┌──────────────────────┐        ┌──────────────────────┐
│  Ecommerce_Service   │        │   src/simulator/     │
│  (별도 저장소 · :3000) │        │   ★ C1 미가동         │
│  런타임 의존 없음      │        │                      │
└──────────┬───────────┘        └──────────┬───────────┘
           │  같은 스키마로 기록 (공유하는 것은 스키마뿐)  │
           └──────────────┬───────────────────────────┘
                          ▼
              ┌───────────────────────────┐
              │   src/measurement/  창구   │  ★ C1 의 본진
              │   schema · sink            │  아무에게도 의존하지 않는다
              │   kpi · economics          │
              │   validate · freeze        │
              │   publish                  │
              └───────┬───────────┬───────┘
                      │           │
              data/raw/           results/
              (수집)               (게시)
                                  ▼
                       ┌────────────────────┐
                       │  dashboard/ :3001  │  파일 읽기 · API 없음
                       │  관측 화면군 V1~V6  │  계산하지 않는다
                       │  (결과 화면군: 이후) │
                       └────────────────────┘
```

| 파트 | C1 | 비유 |
|---|---|---|
| `src/measurement/` | ★ **주력** | 창구 — 두 파트가 만나는 유일한 지점 |
| `src/simulator/` | 미가동 | 출제자 |
| `src/decision/` | 미가동 | 수험생 |
| `src/diagnostics/` | 미가동 | 채점자 |
| `src/orchestration/` | 미가동 | 지휘자 |
| `dashboard/` | ★ **신설** | `decision` 과 동일한 격리 제약 (`DB-014`) |

---

# 3. 중심 문제 둘

## 3.1 창구가 편들지 않게 하기

**문제.** C1 이 창구에 넣는 것은 KPI 와 경제 규칙이다 — *"커머스에는 원가가 없어서 기여이익을 못 낸다"* 는 지식이 자연스럽게 들어오는 자리다.
`if source == COMMERCE: 계산 불가` 한 줄이면 오늘 요구는 충족되고, 창구는 커머스의 구현 상태를 알게 된다.

**해법.** 편들지 말라고 쓰는 대신 **편들 정보를 주지 않는다.**

| 규칙 | 내용 | 강제 |
|---|---|---|
| N-1 | `economics.py` 에 출처 문자열이 없다 | `test_neutrality.py` |
| N-2 | `economics.py` 가 원가율을 읽지 않는다 (`EC-9`) | 타입 분리 + 테스트 |
| **N-3** | **계산층은 출처를 알 수 없다** — 분기가 아니라 **입력 분할** | 테스트 |
| N-4 | 출처 분류는 `sink.event_source()` 한 곳 | 테스트 |
| N-5·N-6 | 파트 import · 데이터 경로 | **기존 `test_isolation.py`** |

상세 `code-structure.md` §3 · `ADR-0007`.

## 3.2 결손이 조용히 0 이 되지 않게 하기

**문제.** 원가가 없을 때 기여이익을 0 으로 채우면 **이익이 매출과 같아진다.** 숫자는 나오고 화면은 채워지고 아무도 이상하다고 느끼지 않는다.
원가율로 추정하면 더 위험하다 — 더 그럴듯하고, `contribution_profit` 이 `revenue` 의 상수배가 되어 **PRD §65 가드레일이 원리적으로 작동 불가**가 된다.

**해법.** 지표의 **반환 타입과 게시 스키마**를 그렇게 만든다.

```
지표 함수는 MetricValue 를 돌려준다 — float 를 돌려줄 자리가 없다
        ↓
status 가 unavailable/blocked/not_run 이면 value 는 반드시 null
        ↓
JSON Schema 가 0 을 거부한다        ← 실행 확인: 위반 시도 7건 전부 거부
        ↓
게시 전 자기검증에서 걸린다 (fail closed)
        ↓
읽는 쪽도 다시 확인한다 — 위반이면 그리지 않는다
```

상세 `api-contracts.md` §4 · `ADR-0003`.

---

# 4. 계층

```text
계약층   schema.py                         무엇이 통과하는가
계산층   kpi.py · economics.py             순수 함수 · I/O 없음 · 출처를 모른다
입출력   sink.py · config_loader.py        의존성이 사는 유일한 층
         validate.py · freeze.py
조립층   contracts.py · publish.py         출처 분할 · 원자적 게시 · 자기검증
────────────────────────────────────────────────────────────
게시물   results/measurement/*.json        기계가독 계약 (JSON Schema)
         results/data_quality_report.json
────────────────────────────────────────────────────────────
표시     dashboard/ (Next.js · :3001)      계산하지 않는다 · 파일만 읽는다
```

**규칙:** 아래는 위를 모른다. `publish.py` 만 여러 모듈을 조립한다. 순환 없음.

---

# 5. 결정 요약

| # | 결정 | 문서 |
|---|---|---|
| 1 | 대시보드에 API 를 두지 않고 `results/` 에 **게시**한다 | `ADR-0001` · `api-contracts.md` |
| 2 | 측정 게시물은 `results/measurement/` (품질 리포트만 정본 경로에) | `ADR-0002` |
| 3 | 모든 지표를 **`MetricValue`** 로 표현하고 **스키마로 강제**한다 | `ADR-0003` |
| 3b | **계산된 값에 기준(`basis`)을 필수로, 계산 불가에 금지**한다 | `ADR-0008` |
| 3c | **결손 → 영향 사슬을 게시 시점에 넣는다** (화면이 추론하지 않게) | `ADR-0009` |
| 4 | 봉인된 `isolation.yml` 을 고치지 않고 **새 워크플로**를 추가한다 | `ADR-0004` · `dependency-plan.md` |
| 5 | Lock 기록을 **`config/gate1_lock.yaml`** 에 두고 **커밋**한다 | `ADR-0005` · `gate1-freeze-procedure.md` |
| 6 | 토큰 **생성기를 이식**한다 (값은 `Plan/DESIGN.md` 한 벌) | `ADR-0006` · `dashboard-architecture.md` |
| 7 | 출처별 결과를 **분기가 아니라 입력 분할**로 만든다 | `ADR-0007` · `code-structure.md` |
| 8 | 의존성은 `config_loader.py`·`sink.py` **두 곳에만** 산다 | `dependency-plan.md` |
| 9 | 품질 게이트를 **3값**(`pass`/`incomplete`/`fail`)으로 | `data-quality-design.md` |
| 10 | 라우트 그룹으로 **관측/결과 화면군을 같은 앱에 공존**시킨다 | `dashboard-architecture.md` |

---

# 6. C1 이 만드는 것 / 만들지 않는 것

| 만든다 | 만들지 않는다 |
|---|---|
| `kpi.py` · `economics.py` · `validate.py` · `publish.py` · `freeze.py` · `config_loader.py` · `contracts.py` · `errors.py` | `src/simulator/` · `decision/` · `diagnostics/` · `orchestration/` |
| `config/economic_config.yaml` · `config/gate1_lock.yaml` | `simulator_config` · `model_config` · `experiment_config` |
| 게시 계약 v1 + JSON Schema 7종 | ML · DL · Uplift · CLV · Segmentation · 최적화 · A/B |
| `dashboard/` 앱 + 관측 화면군 6화면 | `DB-003`~`DB-010` 결과 화면군 · `(results)/` 디렉터리 |
| `requirements.txt` (pyarrow · PyYAML) | pandas · numpy · scikit-learn |
| `docs/measurement_contract.md` · `docs/gate1_checklist.md` | `src/main.py` (실행 루프가 없다) |
| 부분 봉인 (LOCKED 0 · PARTIAL 최대 4) | **GATE 1 통과 선언** · `EXPERIMENT_ENVIRONMENT_v1` |
| 6개 추가 테이블을 위한 자리 | 6개 추가 테이블 구현 |

---

# 7. 이 웨이브에서 새로 발견한 것

| # | 발견 | 영향 | 결정 |
|---|---|---|---|
| **A-1** | **`discount` 필드가 스키마에 없다.** `order_amount` 의 정의식이 그것을 빼는데 22 컬럼에 없다 | `coupon_cost` 계산 불가 → **`marketing_cost` Guardrail 구성요소** | **D-16** · **G-16 신설 제안** |
| **A-1b** | **`purchase` 는 주문 단위 1행**이라 `Σ(unit_price×quantity)` 를 `events` 만으로 재구성할 수 없다 | **`data_spec` §9 금액 정합성 검사가 원리적으로 불가** (`order_items` 필요) | 동일 |
| **T-1** | `data_spec` §17.4 의 `results/` 접근 주체에 measurement 가 없다 | 정본 긴장. **강제 수단(테스트)은 막지 않는다** | 기록만 (`ADR-0001`) |
| **S-1** | `rejected.jsonl` 에 **금지 필드가 원문으로 남는다** | 게시하면 Hidden Trait 이 화면까지 가는 경로가 생긴다 | 게시물은 **집계·화이트리스트 필드만** (`api-contracts.md` §5.2) |
| **B-1/B-2** | M-3·M-7 문서 **파일명이 task-graph 와 이슈 본문에서 다르다** | 소유 경계 혼선 | **이슈 본문을 따랐다.** 리드 확인 필요 |
| **A-3** | 두 저장소의 `Plan` 서브모듈이 **같은 커밋을 가리킨다** (`c46aee5`) | 토큰 정본이 하나임이 확인됐다 | 토큰 이식 근거 (`ADR-0006`) |

---

# 8. 남는 위험 — 아키텍처로 막지 못하는 것

| 위험 | 왜 막지 못하나 | 완화 |
|---|---|---|
| **"결과를 본 뒤 시뮬레이터를 고치는 것"** (PRD §80 Risk 1) | 해시는 *"바뀌었다"* 만 알려주고 *"왜"* 를 모른다. 고치고 다시 Lock 하면 대조는 통과한다 | `FREEZE-002`·`FREEZE-003` 절차 · `git log config/gate1_lock.yaml` 의 재봉인 이력 |
| **`dashboard/` 격리 미강제** | 현재 검사가 `src/**/*.py` 만 본다 | `test_dashboard_isolation.py` 설계 (D-22) · 런타임 화이트리스트 · 미도입 시 **명시적 한계로 기록** |
| **토큰 생성기 두 벌이 갈라진다** | Node CI 를 도입하지 않는다 | 출처 커밋 SHA 주석 · `tokens:check` · `DG-7` |
| **`types.ts` 가 JSON Schema 와 갈라진다** | 자동 생성기를 두지 않는다 | 읽는 쪽 최소 불변식 검사 (`dashboard-architecture.md` §3.2) |
| **스키마 공백 3건** (`shipping_subsidy`·`discount`·환불) | 필드 추가는 `Plan/` 수정 = 권한 밖 | 규칙 유도값(`derived: true`) 또는 계산 불가. **감추지 않는다** |
| **skip 이 exit 0 이다** | `unittest` 의 동작 | PR 본문 기록 + `DQ-17` `blocked` 게시 + 체크리스트 |

---

# 9. 읽는 순서

| # | 문서 | 먼저 읽어야 할 사람 |
|---|---|---|
| 1 | **`api-contracts.md`** ★ T2.7 게시 계약 + `schemas/` + `examples/` | **Jonnathan · Andrew · Phillip · 리드** |
| 2 | **`build-plan.md`** ★ T2.12 W5 소유 경계 · 겹침 0 증명 | **리드 · Phillip · Andrew** |
| 3 | `code-structure.md` T2.6 창구 중립성 6규칙 | Phillip · Thomas(W6) |
| 4 | `dashboard-architecture.md` T2.10 라우팅·토큰·격리·`AGENTS.md` 내용 | **Andrew · Jonnathan · Matthias** |
| 5 | `dependency-plan.md` T2.9 A7 해법 · CI · docker-compose | Phillip · **리드**(D-19·D-20) |
| 6 | `data-quality-design.md` T2.8 검사 17종 · C1 가능/불가 | Phillip · Matthias |
| 7 | `gate1-freeze-procedure.md` T2.11 Lock 기록 · 탐지 3층 | Phillip · **리드** |
| 8 | `data-model-erd.md` · `service-sequences.md` · `exceptions.md` · `design-patterns.md` | 전원 |
| 9 | `adr/` ADR-0001~0007 | 결정 근거가 필요할 때 |

---

# 10. 결정 대기 목록 — 이 웨이브에서 발생한 것

| # | 항목 | 문서 | 추천 |
|---|---|---|---|
| **D-15** | 사유 코드 2종 추가 (`NOT_RUN`·`PRECONDITION_MISSING`) | `api-contracts.md` §9 | 추가 |
| **D-16** | **`discount` 필드 부재 처리** ← **새 발견** | `api-contracts.md` §9 | D-3 과 같은 처리 (규칙 유도) |
| **D-17** | `results/` 를 `.gitignore` 에 넣는가 | `api-contracts.md` §9 | 넣되 증거 사본은 `.agent-team/` |
| **D-18** | `MetricStatus`·`ReasonCode` 위치 | `build-plan.md` §8 | `schema.py` |
| **D-19** | **`tests-with-deps.yml` 신규 워크플로** | `dependency-plan.md` §8 | 만든다 (사용자 확인 후) |
| **D-20** | `docker-compose.yml` C1 도입 여부 | `dependency-plan.md` §8 | C1 범위 밖 |
| **D-21** | `jsonschema` 를 런타임/개발 중 어디에 | `dependency-plan.md` §8 | 개발 전용 |
| **D-22** | `test_dashboard_isolation.py` C1 도입 | `dashboard-architecture.md` §9 | 도입 (W6 Matthias + 승인) |
| **D-23** | Next.js·React 버전을 커머스와 맞추는가 | `dashboard-architecture.md` §9 | 맞춘다 |
| **D-24** | 품질 게이트 3값 | `data-quality-design.md` §8 | 3값 |
| **D-25** | `DQ-02` 원본을 목록에 남기는가 | `data-quality-design.md` §8 | 남긴다 |
| **D-26** | `gate1_lock.yaml` 위치 | `gate1-freeze-procedure.md` §7 | `config/` |
| **D-27** | 봉인 불일치 시 게시를 막는가 | `gate1-freeze-procedure.md` §7 | 막지 않고 실패로 표시 |
| **D-28** | Andrew 착수 시점 | `build-plan.md` §8 | 지금 (예시 픽스처 2벌로) |
| **D-29** | `sources[s].state` 에 `stale` 을 넣는가 | `api-contracts.md` §10 | 넣지 않는다 (도달·검증 불가 분기) |
| **D-30** | 거부 샘플에 값을 담는가 | `api-contracts.md` §10 | 22컬럼만 |
| **B-1/B-2** | M-3·M-7 **문서 파일명** — task-graph ↔ 이슈 본문 불일치 | `build-plan.md` §1 | 이슈 본문 |

*Joshua 의 D-1~D-14 는 `03-service-planning/` 에 있다.*
