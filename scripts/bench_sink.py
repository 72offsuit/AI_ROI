#!/usr/bin/env python3
"""Event Sink 처리량 측정 (#44 수용 기준: 20,000명 × 30일 ≤ 수 분).

    python3 scripts/bench_sink.py [고객수] [일수]

합성 이벤트를 만들어 쓰기까지의 시간을 잰다. 실제 시뮬레이터 행동 생성 비용은
포함하지 않는다 — 여기서 재는 것은 **Sink 의 수집·검증·저장 비용**이다.
"""

from __future__ import annotations

import sys
import tempfile
import time
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.measurement import schema as sc  # noqa: E402
from src.measurement import sink as sk  # noqa: E402

# 고객 1명이 하루에 남기는 이벤트의 대략적 구성
DAILY_SHAPE = (
    (sc.EventType.SESSION_START, 1),
    (sc.EventType.PAGE_VIEW, 3),
    (sc.EventType.PRODUCT_VIEW, 2),
    (sc.EventType.ADD_TO_CART, 1),
)


def generate(customers: int, days: int):
    for day in range(days):
        stamp = f"2025-10-{(day % 30) + 1:02d}T09:00:00.000+09:00"
        for index in range(customers):
            customer_id = f"C{index:08d}"
            session_id = f"S-{customer_id}-{1759276800000 + day}"
            for event_type, count in DAILY_SHAPE:
                for _ in range(count):
                    record = {
                        "event_id": str(uuid.uuid4()),
                        "customer_id": customer_id,
                        "timestamp": stamp,
                        "event_type": event_type.value,
                        "session_id": session_id,
                        "page_type": "home",
                        "simulator_version": "bench",
                        "random_seed": 42,
                    }
                    if event_type in (sc.EventType.PRODUCT_VIEW, sc.EventType.ADD_TO_CART):
                        record |= {"product_id": "P0042", "category": "fresh_food"}
                    if event_type is sc.EventType.ADD_TO_CART:
                        record |= {"quantity": 1, "unit_price": 8900}
                    yield record


def main() -> None:
    customers = int(sys.argv[1]) if len(sys.argv) > 1 else 20_000
    days = int(sys.argv[2]) if len(sys.argv) > 2 else 30
    per_day = sum(count for _, count in DAILY_SHAPE)
    total = customers * days * per_day

    print(f"고객 {customers:,}명 × {days}일 × 이벤트 {per_day}건 = {total:,}건")
    with tempfile.TemporaryDirectory() as tmp:
        started = time.perf_counter()
        with sk.EventSink(tmp) as s:
            result = s.write_events(generate(customers, days))
        elapsed = time.perf_counter() - started
        manifest = s.manifest()
        size = sum(p.stat().st_size for p in Path(tmp).rglob("part-*"))

    print(f"형식      {manifest['format']}")
    print(f"수집      {result.accepted:,}건 · 거부 {result.rejected:,}건")
    print(f"소요      {elapsed:.1f}초 ({total / elapsed:,.0f} 건/초)")
    print(f"저장 크기 {size / 1024 / 1024:.1f} MB")
    print(f"계산 불가 지표 {len(manifest['unavailable_metrics'])}개: "
          f"{', '.join(manifest['unavailable_metrics'][:5])} …")


if __name__ == "__main__":
    main()
