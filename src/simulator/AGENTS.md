# `src/simulator/` — 출제자 (Customer Behavior Simulator)

가상 고객을 만들고 시간을 진행시키며 행동과 처치 반응을 생성한다. **이 파트는 정답을 알고 있다.**

## 절대 하지 않는 것

- **`results/`를 읽지 않는다.** 모델 성능·전략 결과를 확인하지 않는다.
- **`docs/model_report.md`, `docs/uplift_analysis.md`, `docs/ab_test_report.md`를 읽지 않는다.**
- **AI 성능을 이유로 파라미터를 조정하지 않는다.** 이것이 이 프로젝트에서 가장 위험한 누수다 (PRD §80 Risk 1).
- `src.decision`, `src.diagnostics`를 import하지 않는다.

> **AUC·Qini·Incremental Profit 이야기가 나오면 작업을 멈추고 사용자에게 보고한다.**
> "성능이 목표에 미달하니 이탈 감쇠 파라미터를 조정할까요" 같은 제안을 하지 않는다.
> 시뮬레이터가 맞춰야 할 기준은 AI 성능이 아니라 **생성 이탈률 15~25%**(SRS SIM-005)와
> **처치 강도 가드레일**(ATE 3~6%p, 쿠폰 사용률 25~40%, Sleeping Dog 8~15%)이다.

## 봉인 (GATE 1)

다음이 확정된 뒤에는 AI 결과를 근거로 바꾸지 않는다.

```
Persona 구성비 · Hidden Trait 분포 · 행동 규칙 · Churn 임계값
Treatment 반응 규칙 · 경제 파라미터 · Event Schema
```

설계 결함이 발견되면 조용히 고치지 않는다. **Issue 기록 → 수정 → `simulator_version` 상향 → Baseline부터 전 전략 재실행**(SRS FREEZE-003).

## 공개 인터페이스

외부(`orchestration`)에는 `api.py`만 노출한다.

```python
init(seed, num_customers, profile)
advance(n_days)
snapshot() / restore(snapshot_id)
apply_treatment(assignments)
```

- **분할 불변성**: `advance(a)` 후 `advance(b)`는 `advance(a+b)`와 이벤트 단위로 동일해야 한다. 깨지면 오케스트레이션 결과를 재현할 수 없다.
- **Backend-only**: 서비스 UI를 거치지 않고 `measurement`의 Event Sink에 직접 기록한다.
- `_internal/`은 외부에 노출하지 않는다.

## 잡음을 없애지 않는다

측정되지 않는 행동은 구현하지 않되, **예측에 기여하지 않는 잡음 행동은 유지한다.** 측정 항목과 예측 신호가 1:1로 맞물리면 Churn 문제가 비현실적으로 쉬워진다 (PRD §80 Risk 2).

상세 생성 규칙은 `docs/data_spec.html` §3 · §4를 따른다.
