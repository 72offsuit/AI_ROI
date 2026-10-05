from __future__ import annotations

import hashlib
import json
from typing import Sequence

RNG_SCHEME = "sim-rng-v1"
EVENT_ID_SCHEME = "sim-event-id-v1"

_TWO_64 = 1 << 64


def canonical_json(value: object) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=True
    ).encode("ascii")


class Stream:
    __slots__ = ("_base", "_count")

    def __init__(self, seed: int, customer_id: str | None, purpose: str, day: int) -> None:
        self._base = hashlib.sha256(
            canonical_json([RNG_SCHEME, seed, customer_id, purpose, day])
        )
        self._count = 0

    def next_u64(self) -> int:
        digest = self._base.copy()
        digest.update(self._count.to_bytes(8, "big"))
        self._count += 1
        return int.from_bytes(digest.digest()[:8], "big")

    def bernoulli(self, p_num: int, p_den: int) -> bool:
        if p_den <= 0 or not 0 <= p_num <= p_den:
            raise ValueError(f"확률 분수가 [0, 1] 밖이다: {p_num}/{p_den}")
        return self.next_u64() < (p_num * _TWO_64) // p_den

    def below(self, k: int) -> int:
        if k <= 0:
            raise ValueError(f"구간 크기는 1 이상이어야 한다: {k}")
        limit = _TWO_64 - _TWO_64 % k
        while True:
            value = self.next_u64()
            if value < limit:
                return value % k

    def between(self, lo: int, hi: int) -> int:
        return lo + self.below(hi - lo)

    def weighted(self, weights: Sequence[int]) -> int:
        pick = self.below(_total(weights))
        for index, weight in enumerate(weights):
            if pick < weight:
                return index
            pick -= weight
        raise AssertionError("누적 가중치를 벗어났다")


def _total(weights: Sequence[int]) -> int:
    total = 0
    for weight in weights:
        if weight < 0:
            raise ValueError(f"가중치는 음수일 수 없다: {weight}")
        total += weight
    return total


class DayDraws:
    __slots__ = ("_seed", "_day", "_streams")

    def __init__(self, seed: int, day: int) -> None:
        self._seed = seed
        self._day = day
        self._streams: dict[tuple[str | None, str], Stream] = {}

    def stream(self, customer_id: str | None, purpose: str) -> Stream:
        key = (customer_id, purpose)
        found = self._streams.get(key)
        if found is None:
            found = self._streams[key] = Stream(self._seed, customer_id, purpose, self._day)
        return found


def event_id(seed: int, customer_id: str, seq: int) -> str:
    raw = bytearray(
        hashlib.sha256(canonical_json([EVENT_ID_SCHEME, seed, customer_id, seq])).digest()[:16]
    )
    raw[6] = (raw[6] & 0x0F) | 0x40
    raw[8] = (raw[8] & 0x3F) | 0x80
    text = raw.hex()
    return f"{text[:8]}-{text[8:12]}-{text[12:16]}-{text[16:20]}-{text[20:]}"
