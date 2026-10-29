# 시뮬레이터 공개 계약 — `src/simulator/api.py`

시스템 팀(`orchestration`)이 시뮬레이터를 부를 때 읽는 정본이다. `src/simulator/**`(`api.py` 포함)는 읽지 않고 이 문서만 본다.
이 문서와 `api.py` 의 공개 이름·시그니처·예외 목록, CLI 하위 명령·인자는 `tests/test_simulator_api.py` 가 대조한다.

```python
from src.simulator import api as sim
```

- 한 프로세스에 **활성 세계는 하나**다. 모든 함수는 그 세계에 작용한다.
- 실패는 **예외**로 알린다. `False` 나 빈 결과로 돌려주지 않는다. 인자 타입·범위 위반은 표준 `TypeError` · `ValueError`, 그 밖의 실패는 모두 `SimulatorError` 하위다.
- 스냅샷 토큰과 `state_id` 는 내용을 담지 않는 **불투명 문자열**이다. 형식에 기대지 않는다.
- 시각 인자(`until` · `start` · `end`)는 **시간대가 있는** `datetime` 이고 현재 세계 시각 이하여야 한다. 구간은 반열린 `[start, end)` 다.
- 공개 이름은 아래 함수 11개 · `RunSummary` · 예외 7개뿐이다(`api.__all__`). 밑줄로 시작하는 이름은 계약이 아니며 쓰지 않는다.

## 함수 시그니처

```python
def init(seed: int, num_customers: int, profile: str, output_root: str | os.PathLike[str], *, hidden_root: str | os.PathLike[str] | None = None) -> None
def advance(days: int) -> RunSummary
def snapshot() -> str
def restore(snap: str, *, output_root: str | os.PathLike[str]) -> None
def discard_snapshot(snap: str) -> None
def apply_treatment(assignments: Mapping[str, str]) -> None
def events(until: datetime) -> Iterator[dict[str, object]]
def metrics(start: datetime, end: datetime) -> dict[str, sc.MetricValue]
def save_state() -> str
def load_state(state_id: str, output_root: str | os.PathLike[str], *, hidden_root: str | os.PathLike[str] | None = None) -> None
def exchange_bundle(until: datetime) -> dict[str, object]
```

`sc` 는 `src.measurement.schema` 다. `hidden_root` 는 테스트·도구 전용이며 **오케스트레이션은 넘기지 않는다.**

## 반환 타입

```python
@dataclass(frozen=True)
class RunSummary:
    run_id: str | None
    start: datetime
    end: datetime
    event_count: int
```

`start` · `end` 는 KST `datetime`, 창은 `[start, end)` 다. `run_id` 는 측정 계층 실행 기록(`runs/run-<id>.json`)의 ID 이고 `advance(0)` 이면 `None` 이다.

## 예외

```python
class SimulatorError(Exception)
class NotInitializedError(SimulatorError)
class OutputRootError(SimulatorError)
class SnapshotError(SimulatorError)
class StateFormatError(SimulatorError)
class AssignmentError(SimulatorError)
class SinkFormatError(SimulatorError)
```

| 예외 | 언제 |
|---|---|
| `NotInitializedError` | 활성 세계가 없다 — `init` 또는 `load_state` 를 먼저 부른다 |
| `OutputRootError` | 출력 루트가 비어 있어야 하는데 비어 있지 않다 · 다른 누군가 그 루트에 썼다 · 쓰려는 루트의 실행 기록과 디스크가 어긋난다(중단된 쓰기의 흔적 포함) · 계보가 기록한 파티션이 사라졌거나 내용(바이트·건수)이 실행 기록과 다르거나 읽을 수 없다 · 이어받을 상태의 계보를 끝까지 검증할 수 없다. **그 루트에는 더 쓰지 않는다 — 새 빈 루트로 이어간다** |
| `SnapshotError` | 모르는(이미 버린) 토큰이거나 활성 세계의 토큰이 아니다 |
| `StateFormatError` | 저장 상태가 없거나 손상됐거나 구조가 틀렸거나 판이 다르다. 실행한 Python 판은 거부 사유가 아니다 |
| `AssignmentError` | 배정 목록에 틀린 항목이 있다. 이때 아무것도 기록하지 않는다 |
| `SinkFormatError` | 출력 루트의 저장 형식이 섞였거나, 쓰려는 루트·이어받을 계보의 형식을 현재 런타임이 읽거나 쓸 수 없다(예: parquet 루트인데 `pyarrow` 가 없다). 쓰기 전에 — `restore`·`load_state` 단계에서 — 거부하고 아무것도 바꾸지 않는다. `requirements.txt` 를 설치하면 모든 판(3.10 이상)에서 전 기능이 동작한다. 의존성이 없는 환경은 jsonl.gz 루트만 읽을 수 있다 |
| `SimulatorError` | 위에 속하지 않는 실패 — 출력 루트·상태 쓰기 실패(디스크 오류 등), 계보 기록 실패. 위 여섯 예외도 모두 이것의 하위다 |

예외 메시지에는 시뮬레이터 소유 위치의 경로가 들어가지 않는다. 원인 예외는 `__cause__` 에 남는다.

## 함수

| 함수 | 인자 | 반환 | 예외 |
|---|---|---|---|
| `init` | `seed`: `0 ≤ seed < 2⁶³` 정수 · `num_customers`: 1 ~ 99,999,999(고객 ID `C00000001` 부터 순번) · `profile`: `smoke` `short` `small` `reference` `long` `rolling` 중 하나 · `output_root`: 이 세계 전용 Sink 루트, 없거나 빈 디렉터리. `bool` 은 정수로 받지 않는다 | `None`. 이전 세계와 스냅샷 토큰을 버린다. 이벤트를 쓰지 않는다 | `TypeError` · `ValueError` · `OutputRootError` · `SimulatorError`(시뮬레이터의 생성 설정을 읽을 수 없거나 형식이 틀렸다) |
| `advance` | `days`: 0 이상의 `int`. 창 끝이 epoch ms 13자리(2286-11-20)를 넘으면 `ValueError` | `RunSummary`. 창 `[now, now+days)` 를 기록하고 시각을 옮긴다. 1회 = 측정 계층 실행 기록 1건. `advance(0)` 은 아무것도 하지 않는다. `advance(a)` 후 `advance(b)` 는 `advance(a+b)` 와 이벤트 단위로 같다. 비어 있지 않은 루트는 실행 기록과 디스크가 맞고 이 세계 계보의 파티션 내용이 계보 기록과 같을 때만 이어 쓰고, 루트의 저장 형식은 첫 쓰기 때 정해져 바뀌지 않는다 | `TypeError` · `ValueError` · `NotInitializedError` · `OutputRootError` · `SinkFormatError` · `SimulatorError` |
| `snapshot` | — | 토큰 `str`. 같은 토큰으로 여러 번 `restore` 할 수 있다 | `NotInitializedError` |
| `restore` | `snap` · `output_root`(키워드, **빈** 루트) | `None`. 토큰 시점으로 되돌리고 이후 쓰기를 `output_root` 로 돌린다. 이미 쓴 루트에는 다시 쓰지 않는다. 이어받을 계보를 이 런타임이 읽을 수 없으면 거부한다 | `TypeError` · `SnapshotError` · `OutputRootError` · `SinkFormatError` · `SimulatorError`(시뮬레이터의 생성 설정이 같은 프로세스 안에서 바뀌었다) |
| `discard_snapshot` | `snap` | `None` | `TypeError` · `SnapshotError` |
| `apply_treatment` | `assignments`: `customer_id`(`^C\d{8}$`, 이 세계의 고객) → `treatment_id`(`^T[0-4]$`). `T0` 포함 | `None`. 현재 시각으로 배정 이력에 적고, 다음 `advance` 의 계보 기록(그 전에 `save_state` 를 부르면 그 저장의 계보)에 남긴다. 전부 검사한 뒤 하나라도 틀리면 아무것도 적지 않는다. **의미는 아래 「처치 배정의 의미」** | `TypeError` · `NotInitializedError` · `AssignmentError` · `SimulatorError`(숨김 영역 기록 실패 — 배정을 적지 않았다) |
| `events` | `until` | 이 세계의 계보가 기록한 이벤트 중 `timestamp < until` 인 것을 측정 계약 형식(`docs/measurement_contract.md`) 그대로 생성 순서로 낸다. 분기 루트에서도 분기 이전 이력이 함께 나온다. 계보에 속한 실행이 기록한 파일만 읽는다 — 같은 루트에 남은 중단된 쓰기의 흔적이나 다른 작성자의 파일은 결과에 섞이지 않는다. 읽는 파일의 바이트·건수가 실행 기록과 다르면 예외를 낸다. 반복 도중 예외가 나면 그때까지 받은 이벤트는 불완전하므로 쓰지 않는다(전량을 받은 뒤에만 쓴다) | `TypeError` · `ValueError` · `NotInitializedError` · `OutputRootError` · `SinkFormatError` |
| `metrics` | `start` · `end` (`start ≤ end`) | `dict[str, MetricValue]` — `events_total` 과 `events.<event_type>` 16종, 비즈니스 지표 `churn_rate` · `revenue` · `contribution_profit` · `marketing_cost`. 이 판이 만들지 않는 유형(`search` · `return_visit` · `review` · `cs_contact`)과 비즈니스 지표는 `not_run` · `PRECONDITION_MISSING` 이다(0 이 아니다). 비즈니스 지표는 측정 계층(`publish`)이 이벤트와 교환 묶음으로 계산한다. `ok` 의 0 은 측정된 0 이다 | `events` 와 같다 |
| `save_state` | — | `state_id` `str`. 현재 상태를 시뮬레이터 소유 위치에 원자적으로 쓴다. 같은 상태는 같은 `state_id` 다. 쓰기에 실패하면 이미 있던 상태 파일은 그대로다 | `NotInitializedError` · `SimulatorError` |
| `load_state` | `state_id` · `output_root`: 비어 있거나, 실행 기록과 디스크가 맞고 그 루트의 마지막 실행이 바로 이 상태에서 끝났어야 한다 | `None`. 저장된 상태를 활성 세계로 둔다. 빈 루트로 이어받으면 이 상태에 이르는 계보가 끝까지 검증돼야 하고(이 런타임이 그 형식을 읽을 수 있어야 한다), 그 계보가 `events()` 의 이전 이력이 된다. 스냅샷 토큰은 그대로 두지만 다른 세계의 토큰은 `restore` 가 거부한다 | `TypeError` · `ValueError` · `StateFormatError`(시뮬레이터의 생성 설정이 그 상태를 만든 설정과 다르거나, 생성 설정을 읽을 수 없을 때도) · `OutputRootError` · `SinkFormatError` |
| `exchange_bundle` | `until` | `{"status": "ok", "path", "orders", "order_items", "customers", "generated_at"}`. 출력 루트의 형제 `simulator_exchange/` 에 교환 계약 v1(`docs/contracts/commerce-exchange/v1/README.md` §11) 묶음을 **전량 스냅샷**으로 쓴다 — 이 세계 계보의 주문 중 `ordered_at < until` 과 그때까지 가입한 고객, 카탈로그(주문 시점 원가 포함). 같은 부모 아래 분기 루트가 여럿이면 마지막 호출이 덮어쓰므로 본선 루트에서 부른다 | `TypeError` · `ValueError` · `NotInitializedError` · `OutputRootError`(계보 실행의 주문 기록이 없다) · `SimulatorError`(쓰기 실패) |

## 처치 배정의 의미 (S6 · #143)

- **노출**: `apply_treatment` 를 부른 시각(그때의 세계 시각, KST 자정)에 배정된 고객의 노출 이벤트가 다음 `advance` 의 첫 순간 시각으로 기록된다. `T1`~`T4` 는 `campaign_exposed` · `push_sent`, 쿠폰 처치(`T2` · `T3`)는 `coupon_exposed` 도 낸다. `T0` 은 노출이 없다. 노출·쿠폰·처치 창 안의 결제 이벤트에는 `treatment_id` 가 실린다.
- **효과 창**: 배정 시각부터 **42일**(`LABEL_WINDOW_DAYS` 와 같다). 창이 지나면 효과가 끝난다.
- **덮어쓰기**: 같은 고객에게 다시 `apply_treatment` 하면 새 배정이 앞 배정을 덮어쓴다. `T0` 배정은 앞선 처치의 효과를 끝낸다.
- **처치 종류**: `T1` 무료배송(할인 전 상품 합계 40,000원 미만 주문의 배송비 면제) · `T2` 정액 쿠폰(30,000원 이상 3,000원) · `T3` 강한 윈백 쿠폰(50,000원 이상 7,000원) · `T4` 재구매 리마인더(푸시). 쿠폰은 고객이 받아 둔 경우(`coupon_clicked`)에만, 배정 시각부터 **14일** 안에, 배정 1회에 한 번 결제에 쓰인다(`coupon_use`). 처치 효과는 쿠폰 사용 밖(방문·구매 의향)에서도 생긴다.
- **참 효과**: 배정된 고객마다 처치별 참 효과를 시뮬레이터 숨김 영역(`data/ground_truth/simulator/`, 시험·도구가 `hidden_root` 를 주면 그 아래 `ground_truth/`)에 기록한다. **의사결정 측(`src/decision/`)은 읽지 않는다** — 사후 채점(`src/diagnostics/`)만 읽는다. 공개 API 는 이 값을 돌려주지 않는다.
- **참 효과 기록 형식(#167)**: 배정 호출마다 JSON Lines 파일 하나 `po-<world_id>-<배정 시각 ms>-<배정 전 상태 다이제스트 16자>-<배정 다이제스트 16자>.jsonl`, 고객 한 명이 한 줄이다. 시뮬레이터는 표준 라이브러리만으로 돌아야 해서(Python 3.10 · 의존성 없음) Parquet 이 아니라 JSONL 이다.
  - `customer_id` · `at`(배정 시각, KST RFC 3339) · `window_days` · `assigned`(실제 배정 팔)
  - `outcomes[T0~T4]` — 그 팔을 지금 배정했을 때 창 안 결과: `purchased`(0/1) · `orders` · `revenue` · `cogs` · `shipping_subsidy` · `discount` · `coupon_used` · `contribution_profit` · `marketing_cost` · `net_profit`(원, 정수)
  - `tau_purchase[T1~T4]` · `tau_net_profit[T1~T4]` — `outcomes[팔] − outcomes[T0]`
  - `response_type[T1~T4]` — 숨은 반응 유형(`positive`·`neutral`·`negative`)
  - `supersedes` — 이 배정이 앞선 비-`T0` 처치의 효과 창 안에서 이뤄졌으면 `{file, at, treatment_id, observed_days}`, 아니면 `null`. `file` 은 끊긴 배정이 쓴 참 효과 파일 이름(확장자 없이)이다
- **오케스트레이션 통합**: 분기마다 `restore → apply_treatment → advance(42)` 순서로 부른다. 참 효과 파일은 분기(배정 내용)마다 따로 남는다.
- **창 안 재배정**: 효과 창 안에서 같은 고객을 다시 배정하면 앞 배정의 참 효과 행은 "더 배정하지 않았을 때"의 값이라 `observed_days` 일 뒤로는 관측과 어긋난다. 새 행의 `supersedes` 가 그 앞 행(`file` 의 같은 고객 행)을 가리킨다 — 고객 ID · 시각은 world · 분기 사이에서 겹치므로 파일 이름으로 가린다. 사후 채점(`src/diagnostics/report.py`)은 파일마다 그런 행 수를 `superseded_rows` 로 싣는다 — 채점에서 뺄지는 DR-S8 이 정한다. `advance(42)` 뒤에 다시 배정하는 지금의 오케스트레이션은 해당하지 않는다(창은 배정 시각부터 42일, 끝 배타).
- **비용**: 참 효과 계산 때문에 한 시작 상태에서 처음 부르는 `apply_treatment` 는 배정 고객 수에 비례해 걸린다(실측 5,000명 15.3초 — 고객당 약 3ms). 같은 스냅샷에서 갈라진 다음 분기는 같은 고객의 결과를 재사용해 빠르다(같은 5,000명 0.3초).

출력 루트는 시뮬레이터 전용이다. 커머스 이벤트와 같은 루트를 쓰지 않는다. 세계 상태 파일의 위치는 시뮬레이터가 정하며 호출자는 `state_id` 만 다룬다. 새 루트의 저장 형식은 그 런타임의 기본값(`pyarrow` 가 있으면 parquet, 없으면 jsonl.gz)이다.

## D9 루프 예시

T0 마다 `save_state()`(본선 재개용, 파일)와 `snapshot()`(전략 분기용, 메모리 토큰)을 **둘 다** 받는다. 분기는 새 빈 루트로 `restore` 하고, 본선은 `load_state(state_id, 본선 루트)` 로 잇는다. 경로 문자열은 오케스트레이션이 정한다.

```python
from src.simulator import api as sim

sim.init(seed=42, num_customers=26000, profile="rolling", output_root=main_root)
sim.advance(warmup_days)
for T0 in campaign_index_dates:
    state_id = sim.save_state()            # 본선 재개용 (파일)
    snap = sim.snapshot()                  # 전략 분기용 (메모리 토큰)
    features = build_features(sim.events(until=feature_cutoff(T0)))
    for strategy in strategies:
        sim.restore(snap, output_root=new_empty_root(T0, strategy))
        sim.apply_treatment(strategy.select(features, budget=C_rule))
        sim.advance(label_window_days)
        report(T0, strategy, sim.metrics(T0, T0 + timedelta(days=label_window_days)))
    sim.discard_snapshot(snap)
    sim.load_state(state_id, main_root)    # 본선 루트의 마지막 실행이 이 상태에서 끝났으므로 통과
    sim.advance(campaign_interval_days)
```

## CLI

`python -m src.simulator` — 세계를 만들거나 이어서 진행하고, 끝 상태를 저장한 뒤 그 `state_id` 를 표준 출력에 한 줄로 낸다. 실패 메시지는 표준 오류로 낸다.

```
python -m src.simulator init --seed N --customers N --profile NAME --output-root PATH [--days N] [--hidden-root PATH]
python -m src.simulator advance --output-root PATH --days N [--hidden-root PATH]
python -m src.simulator resume --state-id ID --output-root PATH --days N [--hidden-root PATH]
python -m src.simulator guardrails --seed N --customers N [--profile NAME] --warmup-days N [--sample N] --output-root PATH [--hidden-root PATH]
```

| 하위 명령 | 하는 일 |
|---|---|
| `init` | `api.init` → (`--days` 가 있으면) `api.advance` → `api.save_state` |
| `advance` | 출력 루트의 마지막 실행이 끝난 상태를 불러(`api.load_state`) N 일 진행하고 저장한다 |
| `resume` | 지정한 `state_id` 를 불러 N 일 진행하고 저장한다. `--output-root` 가 비어 있으면 새 루트로 이어간다 |
| `guardrails` | 시뮬레이터 팀 도구(S7-lite). 새 세계를 `--warmup-days` 진행한 시점에서 생성 이탈률 · 처치별 ATE · 쿠폰 사용률 · Sleeping Dog 비율을 계산해 시뮬레이터 숨김 영역 `ground_truth/guardrails/` 에 JSON 으로 쓰고 표로 출력한다. 봉인은 하지 않는다. 시스템 팀은 쓰지 않는다 |

| 종료 코드 | 뜻 |
|---|---|
| `0` | 성공. 표준 출력에 `state_id` |
| `1` | `SimulatorError` 하위 예외(루트·상태·계보·형식 문제) |
| `2` | 인자 오류(`TypeError` · `ValueError`, 필수 인자 누락 포함) |

운용 제약:

- `init` 을 `--days` 없이 실행한 루트에는 아직 실행 기록이 없다. 이어서 진행하려면 `advance` 가 아니라 `resume --state-id <init 이 출력한 값>` 을 쓴다.
- CLI `advance` 는 루트의 마지막 실행이 끝난 상태가 저장돼 있어야 한다. API 로 `advance` 만 하고 `save_state` 를 하지 않은 루트는 거부한다(종료 코드 1). 그 경우 API 쪽에서 `save_state` 를 부르거나 `resume` 을 쓴다.
- 중단된 쓰기의 흔적이 남은 루트는 `advance`·`resume` 모두 거부한다(종료 코드 1). 같은 명령을 다시 실행하지 말고 마지막으로 성공한 `state_id` 로 **새 빈 루트**에 `resume` 한다.
- `--hidden-root` 는 테스트·도구 전용이다.
- 런타임 범위: `requirements.txt` 를 설치하면 모든 판(3.10 이상)에서 전 기능이 동작한다. 의존성이 없는 환경은 jsonl.gz 루트만 읽을 수 있다. 의존성이 없는 런타임에서 parquet 계보를 이어가면 `SinkFormatError`(종료 코드 1)다.
