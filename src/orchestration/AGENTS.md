# `src/orchestration/` — 지휘자 (Experiment Runner)

시뮬레이터와 의사결정 시스템에 **명령만 내린다.** 양쪽의 속을 들여다보지 않는다.

## 규칙

- `src.simulator.api`의 공개 함수와 `src.decision`의 공개 인터페이스만 호출한다.
- **`src.simulator._internal`을 import하지 않는다.**
- **`src.diagnostics`를 import하지 않는다.** 진단은 실험 루프 밖에서 독립 실행한다.
- **데이터를 직접 가공하지 않는다.** Feature 계산은 `decision`, 이벤트 생성은 `simulator`의 일이다.

## 기본 루프

```python
sim = Simulator.init(seed=42, num_customers=26000, profile="reference")
sim.advance(warmup_days)

for T0 in campaign_index_dates:
    snap = sim.snapshot()
    features = build_features(sim.events(until=T0 - 1))      # Feature Cutoff
    for strategy in [S0, S1, S2, S3, S4, S5]:
        sim.restore(snap)                                     # 동일 시점 · 동일 난수
        sim.apply_treatment(strategy.select(features, budget=C_rule))
        sim.advance(label_window_days)
        report(T0, strategy, sim.metrics(T0, T0 + label_window_days))
    sim.restore(snap)
    sim.advance(campaign_interval_days)
```

`snapshot`/`restore` 덕에 모든 전략이 **같은 시점·같은 고객 상태**에서 출발한다. "동일 고객·동일 기간" 비교가 코드로 강제된다.

## 루프 안에서 하지 않는 것

- 중간 결과를 보고 시뮬레이터 파라미터를 바꾸는 것 (GATE 1 이후 금지)
- 중간 결과를 보고 `S1` 규칙이나 `C_rule`을 바꾸는 것 (GATE 2 이후 금지)
- Final Holdout 모집단을 루프에 넣는 것

## 리포트에 반드시 남기는 것

```
simulator_commit · simulator_version · data_version
config 4종의 SHA-256 · random_seed · profile
```

`simulator_commit`이 GATE 1 봉인 시점과 다르면 **Baseline부터 전 전략을 재실행**한다.

상세는 `docs/data_spec.html` §13.4를 따른다.
