"""현실성·기제 실측용 세계 생성기 — `realism_check.py`·`sim_evidence.py` 입력을 만든다.

DR-183 의 20K 실측과 같은 절차다: init → advance(배정일) → 그때까지 이벤트가 있는 고객 전원에
T0~T4 균등 무작위 배정 → advance(나머지) → 교환 묶음. 1회 배정이라 오케스트레이션의 다중 T0
배정과 처치 관련 값(F14·F15·F17)의 절대값이 다를 수 있다.

공개 API(`src.simulator.api`)만 쓴다. 저장소 루트를 cwd 로 두고 실행한다.

사용
    PYTHONPATH=. python scripts/research/run_world.py --seed 42 --customers 20000 --out <새 디렉터리> \
        [--profile reference] [--days 315] [--assign-day 180] [--config <실험 config>]
    python scripts/research/realism_check.py --events <out>/raw/main \
        --exchange <out>/raw/simulator_exchange --assignments <out>/assignments.json --out-json <json>
"""

from __future__ import annotations

import argparse
import json
import random
import time
from pathlib import Path

from src.simulator import api

ARMS = ("T0", "T1", "T2", "T3", "T4")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--seed", type=int, required=True)
    ap.add_argument("--customers", type=int, required=True)
    ap.add_argument("--out", required=True, help="새 디렉터리(이미 있으면 거부)")
    ap.add_argument("--profile", default="reference")
    ap.add_argument("--days", type=int, default=315)
    ap.add_argument("--assign-day", type=int, default=180)
    ap.add_argument("--config", default=None, help="실험 생성 config(생략 시 정본)")
    args = ap.parse_args(argv)
    if not 0 < args.assign_day < args.days:
        ap.error("--assign-day 는 0 과 --days 사이여야 한다")

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=False)
    started = time.time()
    api.init(args.seed, args.customers, args.profile, str(out / "raw" / "main"),
             hidden_root=str(out / "hidden"), config_path=args.config)
    now = api.advance(args.assign_day).end
    active = sorted({str(e["customer_id"]) for e in api.events(now) if e.get("customer_id")})
    # 배정 난수는 세계 난수와 분리한다 — 같은 seed 면 같은 배정이다.
    rng = random.Random(args.seed * 1_000_003 + 183)
    arms = {cid: ARMS[rng.randrange(len(ARMS))] for cid in active}
    api.apply_treatment(arms)
    (out / "assignments.json").write_text(
        json.dumps({"assigned_at": now.isoformat(), "assignments": arms}, ensure_ascii=False), encoding="utf-8")
    end = api.advance(args.days - args.assign_day).end
    bundle = api.exchange_bundle(end)
    meta = {"seed": args.seed, "customers": args.customers, "profile": args.profile, "days": args.days,
            "assign_day": args.assign_day, "assigned": len(arms), "config": args.config,
            "exchange": bundle.get("path"), "seconds_total": round(time.time() - started, 1)}
    (out / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps(meta, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
