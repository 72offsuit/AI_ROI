# `src/decision/` — 수험생 (Decision Layer)

Feature 생성부터 Churn·Uplift·CLV·세그먼테이션·전략·예산 최적화·대시보드까지. **행동 기록만 보고 정답을 맞혀야 하는 쪽이다.**

## 절대 하지 않는 것

- **`data/hidden/`을 읽지 않는다.** Hidden Trait은 실제 서비스에서 알 수 없는 값이다.
- **`data/ground_truth/`를 읽지 않는다.** 정답지다.
- **`src/simulator/`를 import하지 않는다.** `api.py`도 포함이다. 시뮬레이터 동작이 궁금하면 `src/measurement/`의 스키마만 본다.
- `src.diagnostics`를 import하지 않는다.

시뮬레이터가 어떻게 행동을 만들어내는지 **몰라야 한다.** 알고 나면 그 구조에 맞춘 Feature를 만들게 되고, 그건 실제 데이터에서 통하지 않는다.

## Feature 규칙

모든 Feature는 `index_date = T0` 기준, **Feature Cutoff = T0 − 1일 23:59:59** 이전 이벤트로만 계산한다.

절대 Feature에 넣지 않는 것:

```
treatment_group · treatment_id · experiment_id
T0 이후의 coupon_use · campaign_exposed · push_sent
파생 상태 이벤트 churn · at_risk · inactive
persona 라벨
Hidden Trait 전체
```

Feature 이름이 `*_post_t0`로 끝나면 학습 로더가 차단한다.

## Test / Holdout 취급

- **Test 성능을 보며 하이퍼파라미터를 반복 조정하지 않는다.** 튜닝은 Validation에서 한다.
- **Final Holdout은 확정 전략 1회 평가에만 쓴다.** 튜닝·Threshold 선택·전략 선택·예산 정책에 사용 금지.
- Holdout 결과가 나쁘다는 이유로 모델을 고치면 그 순간부터 Holdout이 아니다. 수정이 불가피하면 새 seed로 재생성하고 리포트에 기록한다.

> 시뮬레이터를 건드리지 않아도, **Test를 반복해서 보면 그것 자체가 과적합이다.**

## 봉인 (GATE 2)

`strategies.py`의 S1 선정 규칙(`S1_RULE` · `plan_S1`, AI 결과 이전 커밋 `ce05a66` · 태그 `gate2-s1-rule`)과 `C_rule`(S1 계획 비용 합 — 쿠폰 전량 사용 상한, 캠페인 고정비 제외)은 GATE 2에서 확정한다(#170 · `docs/decisions/DR-170-c-rule-budget.md`). **AI 결과를 본 뒤 Baseline을 바꾸지 않는다** (SRS BASE-003). 기준선을 낮추면 Incremental Profit이 올라가지만 아무 의미가 없다.

## 하위 구조

```
features/  models/  uplift/  clv/  segmentation/
optimization/  strategies/  experiments/  analytics/  dashboard/
```

상세는 `docs/data_spec.html` §8 · §10 · §11 · §12 · §14를 따른다.
