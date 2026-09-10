# `src/diagnostics/` — 채점자 (사후 진단 전용)

`data/ground_truth/`를 읽을 수 있는 **유일한 모듈**이다. 시험이 끝난 뒤에만 등장한다.

## 존재 이유

시뮬레이터이기 때문에 반사실(`Y(0)`, `Y(1)`)을 실제로 알 수 있다. 이 이점을 버리지 않되, **학습에는 절대 쓰지 않는다.**

| 산출 지표 | 의미 |
|---|---|
| `Qini_oracle` | 참 CATE로 정렬했을 때의 이론적 최대 Qini |
| Qini 달성률 | 모델 Qini ÷ `Qini_oracle` — 개선 여지가 얼마나 남았는지 |
| PEHE | CATE 추정 오차 (Qini는 순위만 보지만 이것은 크기를 본다) |
| `corr(τ̂, τ)` | 추정 uplift와 참 uplift의 상관 |
| 4분면 혼동행렬 | Persuadable을 Sleeping Dog으로 잘못 분류한 비율 등 |

## 절대 하지 않는 것

- **여기 결과를 모델·Feature·Threshold·전략·예산 정책 개선에 쓰지 않는다.** 최종 리포트의 진단 항목으로만 쓴다.
- **어떤 모듈도 `src.diagnostics`를 import하지 않는다.** `decision`, `simulator`, `measurement`, `orchestration` 전부 금지다.
- 실행 시점은 **모든 전략 평가가 끝난 뒤 리포트 생성 단계**다.

> Qini 달성률이 낮다고 해서 그 정보로 Uplift 모델을 고치면, 그 모델은 정답지를 보고 만든 것이 된다.
> 진단 결과는 **"이 정도가 한계였다"를 사후에 말하기 위한 것**이지 개선 신호가 아니다.

## 실행 방식

`orchestration`이 호출하지 않는다. 리포트 생성 스크립트가 **독립적으로** 실행한다. 이렇게 해야 실험 루프 안에 진단 결과가 섞여 들어가지 않는다.

상세는 `docs/data_spec.html` §4.4 · §14를 따른다.
