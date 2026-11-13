# AI_ROI — 고객 이탈 예측과 리텐션 ROI 최적화

가상의 이커머스 고객을 **만들어 내는 쪽**과, 그 행동 기록만 보고 **누가 떠날지 맞히는 쪽**을 한 저장소 안에서 분리해 세운다. 맞히는 쪽이 잘 맞혔는지는 만든 쪽만 아는 정답으로 채점한다.

기획 문서는 `Plan/` 서브모듈의 PRD/SRS v2.0 이고, 커머스 서비스 자체는 `Ecommerce_Service` 에서 따로 구축한다. 이 저장소는 **런타임 의존이 없고 단독으로 돈다.**

---

## 5분 안에 돌려 보기

> **Python 3.12** 가 전체 파이프라인의 지원 런타임이다. 고정 의존성(numpy 2.5.4 · scipy 1.18.1 · shap 0.54.1)이
> 3.12 이상에서만 설치된다. 3.10 은 **측정 계층 하한**이다 — 아래 ①(의존성 0)과 측정 계층은 3.10 에서도 돌지만
> `pip install -r requirements.txt` 는 3.12 부터 된다. 근거 `docs/decisions/DR-207-python-runtime.md` (PRD NFR-04 `>= 3.10` 은 3.12 로 충족).

```bash
git clone https://github.com/72offsuit/AI_ROI.git
cd AI_ROI
git submodule update --init          # Plan/ (private — 접근 권한이 없으면 건너뛴다)

# ① 의존성 0 으로 전건 통과해야 한다 — 이것이 이 저장소의 기본 상태다
python3 -m unittest discover -s tests

# ② 게시 파이프라인은 PyYAML 이 필요하다
pip install -r requirements.txt
python3 -m src.measurement.publish --out /tmp/try-results
```

> ★ ②에서 왜 설치가 필요한가: `config_loader` 가 **YAML 파서를 자체 구현하지 않는다.**
> 부분 구현 파서는 조용히 다른 값을 읽고, 경제 규칙에서 그것은 **기여이익이 조용히 틀리는**
> 결과가 된다. 그래서 PyYAML 이 없으면 게시가 **거부**된다 — 추측해서 읽지 않는다.

마지막 명령이 내는 것:

```
run_id           MR-20260917-203058-9afd65ed
publish_result   ok
  ✅ results/measurement/ingestion_report.json
  ✅ results/measurement/kpi_report.json
  ... (6종)

verdict          attention · SINK_EMPTY
                 수집된 이벤트가 0건이다 — 활동 없음과 수집 중단을 현재 데이터로 구분할 수 없다
```

**이 한 줄이 이 저장소의 성격을 그대로 보여 준다.** 데이터가 없을 때 0% 나 빈 화면을 내지 않는다. *"0건이다"* 와 *"0건인지 아닌지 모른다"* 를 구분해서 말한다.

### 의사결정 파이프라인 — `src/main.py`

```bash
pip install -r requirements.txt
python src/main.py --mode train --customers 2000 --profile small     # 스모크 (약 1분)
python src/main.py --help                                            # 모드별 입력 · 출력 · 종료 코드
```

모드는 `train` · `uplift` · `optimize --budget <KRW>` · `evaluate` · `full`(SRS SYS-004 · PRD §73). 실행 루프
(`src/orchestration/run_sprint.py`)의 단계 중 무엇을 돌릴지만 고르는 디스패처이고, 모델 하이퍼파라미터 · 세그먼트 경계 ·
실험 값은 `config/model_config.yaml` · `config/experiment_config.yaml` 에서 읽는다. 근거와 한계: `docs/decisions/DR-206-main-cli-config.md`.

**학습한 모델과 Feature 는 기본으로 남는다**(#214) — 모델은 `models/<run_id>/`(ML-008 메타데이터와 SHA-256), Feature ·
라벨은 `data/processed/<run_id>/`(FS-002 메타 열을 붙인 parquet). `--no-persist` 로 끈다. 저장한 모델은 다른 seed 실행이
**다시 학습하지 않고** 불러와 평가만 할 수 있다 — Final Holdout(GATE 4)의 전제다. 결정 기록: `docs/decisions/DR-214-model-feature-store.md`.

```bash
python src/main.py --mode full --seed 42                                      # 학습 · 저장 → models/<run_id>/
python src/main.py --mode full --seed 7 --load-models models/<run_id>          # 불러와 평가만 (다시 학습 없음)
```

### 대시보드까지

```bash
cd dashboard
npm install
npm run dev            # http://127.0.0.1:3001  (AIROI_DASHBOARD_HOST 로 바인딩 주소를 바꾼다)
```

`results/` 의 게시물을 **읽기만** 한다. 계산하지 않는다.

> **`Plan/` 없이도 빌드된다** (#207). 디자인 토큰 CSS(`dashboard/src/styles/tokens.generated.css`)를 커밋해 두었고,
> `Plan/DESIGN.md` 가 있으면 `npm run dev`·`build` 가 그것과 대조한다. 없으면 `tokens:check 미실행` 을 출력하고 커밋본을 쓴다 —
> **대조하지 않았다는 뜻이다.** 토큰을 다시 생성(`npm run tokens:generate`)하려면 `Plan/` 접근 권한이 필요하다.

### Docker (초안 — 빌드까지)

```bash
docker build -t airoi .                                  # 서브모듈 없는 클론에서 된다 — Plan/ 은 이미지에 넣지 않는다
docker run --rm -p 3001:3001 airoi                       # 대시보드 → http://localhost:3001
docker run --rm airoi python -m src.measurement.publish  # 파이프라인 명령 예
docker build --build-arg WITH_TORCH=1 -t airoi .         # 선택: CPU torch(requirements-ml.txt)
```

Python 3.12 + Node 22 이미지 하나다. `docker-compose`(파이프라인 → `results/` 볼륨 → 대시보드)는 **아직 없다** — 다음 스프린트(#231).

---

## 왜 두 팀으로 나누나

| | 하는 일 | 비유 |
|---|---|---|
| **시뮬레이터 팀** | 가상 고객을 만들고 행동시킨다. 쿠폰 민감도·이탈 성향 같은 **정답을 안다** | 출제자 |
| **시스템 팀** | 행동 기록만 보고 이탈·처치 효과·생애가치를 맞힌다 | 수험생 |

수험생이 답안지를 보면 점수는 100점이 나오고 실력은 0이다. 그래서 두 팀은 **서로의 파일을 읽지 않는다.**

가장 위험한 누수는 코드가 파일을 훔쳐보는 것이 아니라, **AI 성능이 낮다는 이유로 시뮬레이터를 고치는 것**이다 (PRD §80 Risk 1). 사람도 에이전트도 이 유혹에 빠진다.

```
src/measurement/    ✅ 완료 — 계약. 두 팀이 만나는 유일한 지점 (읽기 전용)
src/simulator/      ⬜ 시뮬 팀
src/decision/       ⬜ 시스템 팀
src/orchestration/  ⬜ 시스템 팀
src/diagnostics/    ⬜ 시뮬 팀 (두 GATE 이후)
```

---

## 지금 있는 것 / 없는 것

**있다**

- `src/measurement/` — 이벤트 스키마 22컬럼·16종, KPI, 경제 규칙, Event Sink, 게시 파이프라인
- `dashboard/` — Next.js 라우트 8종. `results/` 를 읽기만 한다
- GATE 1 **부분 봉인** (`PARTIAL_FREEZE`) — 측정 계층 항목만. 완전 봉인은 0종
- 테스트 · CI 4종 — **건수는 여기 적지 않는다.** 명령을 돌리면 나오고, 문서에 박아 둔 숫자는
  테스트를 추가한 바로 다음 커밋에 낡는다 (이슈 `#59` 가 닫은 결함이 그 모양이었다)

**없다**

- **고객 시뮬레이터 전체.** 가상 고객도, 행동도, 처치 반응도 아직 없다
- **모델 전체.** Feature·Churn·Uplift·CLV·전략·최적화 전부
- 실행 루프, A/B, ROI 집계, 모니터링

즉 **지금 이 저장소는 "측정할 준비가 된 빈 계측기"** 다. 측정할 대상을 만드는 것이 C2 다.

---

## 어디서 시작하나

| 읽는 순서 | |
|---|---|
| 1 | **이 문서** |
| 2 | `docs/TEAM_SETUP.md` — 팀·소유 경로·태스크 번호·착수 절차 |
| 3 | `docs/DECISION_RECORDS.md` — **왜 그렇게 만들었는지 남기는 법** |
| 4 | 자기 이슈 (`gh issue list --label team/sys` 또는 `team/sim`) |
| 5 | 자기 파트의 `src/*/AGENTS.md` |

```bash
gh issue list --label team/sim   # S1~S8  시뮬레이터
gh issue list --label team/sys   # D1~D12 시스템
```

### ★ 이슈는 태스크 목록이 아니다

각 이슈는 **무엇을 정해야 하고, 무엇을 조사해야 하고, 무엇을 증거로 남겨야 하는지**를 함께 담는다. 체크박스를 다 채워도 **결정 기록이 없으면 그 태스크는 끝난 것이 아니다.**

```
"페르소나를 왜 6종으로 했나요?"     → docs/decisions/DR-S2-*.md 가 답한다
"AUC 0.82 는 믿을 만한가요?"        → docs/decisions/MC-D2-*.md 가 답한다
```

이 프로젝트에서 나올 수 있는 최악의 결과는 **작동하는데 왜 작동하는지 아무도 모르는 것**이다. 틀린 근거는 반박할 수 있지만 없는 근거는 반박할 수조차 없다.

---

## 검증

```bash
python3 -m unittest discover -s tests                        # 전건 (의존성 0)
python3 -m unittest tests.test_isolation                     # 파트 경계
python3 -m unittest tests.test_team_boundaries               # 팀 경계
python3 -m unittest tests.test_decision_records              # 결정 기록
python3 .agent-team/04-architecture/tools/check_ownership.py # 파일 소유
```

의존성을 설치하면 검사가 **늘어난다.**

```bash
pip install -r requirements.txt -r requirements-dev.txt
python3 -m unittest discover -s tests
```

> ★ **PyYAML 이 없으면 봉인 해시 대조가 `not_run` 이 된다.** 그것은 통과가 아니라 *"대조하지 않았다"* 다. 무의존 실행만 보고 초록이라고 판단하지 않는다 — 실제로 봉인 변조를 잡은 것은 의존성 있는 잡뿐이었다.

CI 4종이 PR 마다 돈다: 격리 경계 · 의존성 설치 후 전건(3.12) · **Python 3.10**(SRS 가 선언한 최소 버전 — 의존성 없이, 측정 계층까지) · 대시보드 경로 격리.

`npm run tokens:test` 는 **CI 에 없다** — `Plan/` 이 private 이라 체크아웃되지 않는다. **사람이 돌려야 하는 검사다.**

---

## 이 저장소의 규율

의견이 아니라 **테스트로 강제되는 것**들이다.

- **결손을 0으로 채우지 않는다.** 노출 0인 세그먼트의 전환율은 0% 가 아니라 **계산 불가**다. 0%로 적으면 그 세그먼트가 최악이라는 결론이 나오고 예산이 거기서 빠진다. `?? 0` · `.get(k, 0)` · `or 0` 이 이 규율을 깨는 전형이다
- **미실행을 통과로 적지 않는다.** 실행 못 한 검사는 `BLOCKED` 로 사유와 함께
- **선언에는 대조 장치를 붙인다.** "이렇다"고 적었으면 실제와 맞대는 검사가 있어야 한다. 이 사이클이 찾아낸 결함은 거의 전부 이 모양이었다
- **가정은 문서가 아니라 산출물에 붙인다.** 문서는 아무도 다시 열지 않는다. 게시물 `notices` 가 가정을 나른다
- **결함을 조용히 고치지 않는다.** 발견 → Issue → 수정 → 재시험

### git

- **에이전트 기본 권한은 L1(제안만).** commit·push·PR 은 사람이 명시한 뒤에만
- `main` 에 직접 커밋하지 않는다. 브랜치는 `<type>/<short-kebab-description>`
- merge · Issue close · 브랜치 삭제 · `push --force` · `reset --hard` · `rebase` 는 **항상 개별 승인**
- **서브모듈 포인터를 커밋하지 않는다** (`git add Plan` 금지)

전문: `docs/GIT_WORKFLOW.md` · `Plan/docs/GIT_WORKFLOW_CORE.md`

---

## 봉인 (GATE)

| | 언제 | 무엇이 잠기나 |
|---|---|---|
| **GATE 1** | `S7` (#81) | 페르소나 구성비 · Hidden Trait 분포 · 행동 규칙 · Churn 임계값 · 처치 반응 · 경제 파라미터 · 이벤트 스키마 |
| **GATE 2** | `D7` (#89) | 전략 정의 · `rule_based.py` · 예산 상한 |

봉인 후 변경 비용은 `FREEZE-003` — **버전 상향 → 전 데이터 재생성 → Baseline 부터 전 전략 재실행.**

봉인 기록(`config/gate1_lock.yaml`)은 **사람이 손으로 쓰지 않는다.** `freeze.record()` 가 쓰고, `locked_by` 는 **사람 서명**이다 — 에이전트가 대신 적지 않는다. 손으로 고치면 해시 대조가 실패한다.

---

## 저장소 구조

```
src/measurement/     계약 — 스키마·KPI·경제 규칙·Sink·게시        ✅
src/simulator/       가상 고객 생성·행동·처치 반응                ⬜ 시뮬 팀
src/decision/        Feature·Churn·Uplift·CLV·전략·최적화        ⬜ 시스템 팀
src/orchestration/   실행 루프                                   ⬜ 시스템 팀
src/diagnostics/     Ground-truth 대비 사후 채점                  ⬜ 시뮬 팀
dashboard/           Next.js — results/ 를 읽기만 한다            ✅
config/              경제 규칙 · GATE 1 봉인 기록
docs/decisions/      결정 기록 · 모델 카드                        ← 여기가 채워져야 한다
Plan/                PRD/SRS 서브모듈 (private · 읽기 전용)
```

---

## 라이선스·공개

**public 전환 계획이 없다** (2026-09-05 결정). SRS §37 의 public 요구는 기존 과제 기준이며, private `Plan` 서브모듈은 문제가 되지 않는다.
