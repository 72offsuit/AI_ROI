# `src/simulator/_internal/` — 정답이 계산되는 곳

Hidden Trait, 처치 효과 `τ_i`, Potential Outcome이 여기서 만들어진다. **시스템 전체에서 가장 민감한 디렉터리다.**

## 규칙

- 여기서 만든 값은 **`measurement` 스키마를 통과하지 않는다.** 저장 경로는 `data/hidden/`과 `data/ground_truth/`다.
- `simulator/api.py`를 포함해 **어떤 외부 모듈에도 이 값을 반환하지 않는다.** 반환하는 것은 이벤트뿐이다.
- 이 패키지는 `src.simulator` 내부에서만 import한다. `orchestration`도 접근하지 않는다.

## 여기서 다루는 것

| 산출물 | 저장 위치 | 용도 |
|---|---|---|
| Hidden Trait 15종 | `data/hidden/hidden_traits.parquet` | 행동 생성 파라미터 |
| 처치 효과 `τ_i` | `data/ground_truth/simulator/po-*.jsonl` (배정 호출마다 한 파일, 형식은 `docs/simulator_api.md` 「참 효과 기록 형식」) | 4분면 정답 |
| `Y(T0)`~`Y(T4)` 반사실 실행 결과 | 같음 | Qini 검증용 참값 |

참 효과는 Parquet 이 아니라 JSONL 이다 — 시뮬레이터는 의존성 없는 표준 라이브러리로 돌아야 한다(#167).

## Potential Outcome 이중 실행

Common Random Numbers를 써서 처치 외의 모든 난수를 동일 스트림에서 뽑는다. 그래야 `Y(1) − Y(0)`의 차이가 오직 처치에서 온다.

```python
for W in (0, 1):
    rng = PCG64(seed=customer_seed_i)   # 동일 스트림
    Y_i[W] = simulate(customer_i, treatment=W, days=label_window)
```

**관측 데이터셋에는 배정된 `W_i`에 해당하는 결과만 남긴다.** 반사실은 `data/ground_truth/`로 분리 저장하며, 모델 학습·Feature·타게팅에 사용하지 않는다.

계산식은 `docs/data_spec.html` §3.3 · §4.3 · §4.4를 따른다.
