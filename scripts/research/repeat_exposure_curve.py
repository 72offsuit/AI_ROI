"""처치 반복 노출 감쇠 곡선 (#183 ④ 증거) — 시뮬레이터 정답(숨은 반응 유형·반사실)으로 잰다.

닫힌 #78 의 "같은 쿠폰을 세 번 받은 고객은 첫 번째와 같이 반응하지 않는다"를 두 표로 보인다.

1. 반응 유형 구성 — 첫 세계(Day 0 Trait)의 `--mix-customers` 명 전원이 앞선 노출 n 번 뒤 각 처치를 받을 때
   Positive · Neutral · Negative 비율(`treatment.response_mix`).
2. 참 ATE(구매) — `--customers` 명 세계를 `--warmup-days` 일 진행한 뒤, 직전 `active_lookback_days`(config, 42)일에
   구매한 고객(가드레일 판정 모집단과 같은 정의)에게 과거 T3 노출 n 번만 배정 이력에 합성하고 T0~T4 반사실을
   `window_days` 일 돌린다. ATE = 처치 팔 − T0 팔의 구매 여부 차 평균. 같은 시점·같은 상태에서 n 만 다르다.
   - 합성 노출은 43일 간격으로 지금보다 앞에 둔다. 효과 창(42일) 밖이라 노출 효과는 남지 않고 노출 수에만 든다.
   - n = 0 행은 `python -m src.simulator guardrails` 의 같은 seed·규모·진행일 ATE 와 같아야 한다.

n = 이번 배정 전에 실제로 받은 비-T0 처치 노출 수(`treatment.prior_exposures` — 같은 시각 덮어쓰기는 한 번).

★ 숨은 반응 유형과 반사실을 읽는 시뮬레이터 팀 도구다. 출력은 결정 기록(DR-183-repeat-exposure) 증거용이며
  시스템 팀에 넘기지 않는다. 모델 성능은 다루지 않는다(`results/` 를 읽지 않는다).

사용 (저장소 루트에서)
    PYTHONPATH=. .venv/bin/python scripts/research/repeat_exposure_curve.py --seed 42 --customers 2000
"""

from __future__ import annotations

import argparse
import copy
import sys

from src.simulator._internal import clock, engine, params, treatment
from src.simulator._internal import world as world_state

ARMS = treatment.ARMS[1:]
SYNTHETIC_GAP_DAYS = 43  # 효과 창(42일)보다 길어야 합성 노출의 효과가 남지 않는다


def mix_table(seed: int, customers: int, max_exposures: int) -> list[str]:
    population = world_state.new_world(seed, customers, "small")["customers"]
    lines = [
        f"## 반응 유형 구성 (seed {seed} · {customers:,}명 small · Day 0 Trait) — Positive / Neutral / Negative",
        "",
        "| n | " + " | ".join(ARMS) + " |",
        "|---|" + "---|" * len(ARMS),
    ]
    for n in range(max_exposures + 1):
        cells = []
        for tid in ARMS:
            mix = treatment.response_mix(seed, population, tid, n)
            cells.append(" / ".join(
                f"{mix[kind] * 100 / customers:.2f}%"
                for kind in (treatment.POSITIVE, treatment.NEUTRAL, treatment.NEGATIVE)
            ))
        lines.append(f"| {n} | " + " | ".join(cells) + " |")
    return lines


def ate_table(seed: int, customers: int, warmup_days: int, max_exposures: int) -> list[str]:
    p = params.active()
    world = world_state.new_world(seed, customers, "small")
    orders: list[dict[str, object]] = []
    for _ in engine.run(world, world["now_ms"] + warmup_days * clock.DAY_MS, orders):
        pass
    now = world["now_ms"]
    lower = clock.timestamp(now - p.active_lookback_days * clock.DAY_MS)
    upper = clock.timestamp(now)
    active = sorted({str(o["customer_id"]) for o in orders if lower <= str(o["ordered_at"]) < upper})
    lines = [
        f"## 참 ATE(구매) (seed {seed} · {customers:,}명 small · {warmup_days}일 진행 뒤 직전 "
        f"{p.active_lookback_days}일 구매 고객 {len(active):,}명, 과거 T3 노출 n 번을 효과 창 밖에 합성)",
        "",
        "| n | " + " | ".join(f"{tid} ATE (P / N)" for tid in ARMS) + " |",
        "|---|" + "---|" * len(ARMS),
    ]
    for n in range(max_exposures + 1):
        shadow = copy.deepcopy(world)
        for cid in active:
            customer = shadow["customers"][world_state.customer_index(cid)]
            customer["assignments"] = [
                [now - (n - i) * SYNTHETIC_GAP_DAYS * clock.DAY_MS, "T3"] for i in range(n)
            ]
        rows = treatment.potential_outcomes(shadow, active)
        cells = []
        for tid in ARMS:
            ate = sum(row["tau_purchase"][tid] for row in rows) * 100 / len(rows)
            positive = sum(row["response_type"][tid] == treatment.POSITIVE for row in rows) * 100 / len(rows)
            negative = sum(row["response_type"][tid] == treatment.NEGATIVE for row in rows) * 100 / len(rows)
            cells.append(f"{ate:.2f}%p ({positive:.1f}% / {negative:.1f}%)")
        lines.append(f"| {n} | " + " | ".join(cells) + " |")
    return lines


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--customers", type=int, default=2000, help="참 ATE 표의 세계 규모")
    ap.add_argument("--warmup-days", type=int, default=180)
    ap.add_argument("--mix-customers", type=int, default=5000, help="반응 유형 구성 표의 모집단 규모")
    ap.add_argument("--max-exposures", type=int, default=3)
    args = ap.parse_args(argv)
    if min(args.customers, args.mix_customers, args.warmup_days) < 1 or args.max_exposures < 0:
        ap.error("규모·진행일은 1 이상, --max-exposures 는 0 이상이어야 한다")
    print(f"simulator_version {world_state.SIMULATOR_VERSION}")
    print()
    print("\n".join(mix_table(args.seed, args.mix_customers, args.max_exposures)))
    print()
    print("\n".join(ate_table(args.seed, args.customers, args.warmup_days, args.max_exposures)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
