from __future__ import annotations

import hashlib
import json
from typing import Sequence

RNG_SCHEME = "sim-rng-v1"
EVENT_ID_SCHEME = "sim-event-id-v1"

_TWO_64 = 1 << 64

# 날짜와 무관한 고객 고정 스트림의 day 열쇠. 행동 스트림은 관측 일수(day ≥ 0)를 쓰므로 음수를 용도마다 하나씩
# 나눠 서로·행동과 겹치지 않게 한다. 열쇠 형식은 그대로라 RNG_SCHEME 은 올리지 않는다.
# 값을 바꾸면 그 스트림의 추첨이 전부 바뀐다 — simulator_version 과 골든을 함께 올린다.
GENERATION_DAY = -1  # 페르소나·Trait·가입일 생성(persona)
RESPONSE_DAY = -2  # 처치 반응 유형(treatment)
REPURCHASE_DAY = -3  # 생애 첫 구매 뒤 재구매 게이트(engine)


def canonical_json(value: object) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=True
    ).encode("ascii")


class Stream:
    __slots__ = ("_base", "_count")

    def __init__(self, seed: int, customer_id: str | None, purpose: str, day: int) -> None:
        self._base = hashlib.sha256(_stream_key(seed, customer_id, purpose, day))
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


# 열쇠 직렬화의 빠른 경로 (S4 성능). canonical_json 과 **바이트까지 같은** 문자열을 직접 만든다 — 이스케이프가
# 필요 없는 문자(아스키 영숫자와 `_` `:` `-`)만 있는 문자열과 bool 이 아닌 int 에만 쓰고, 나머지는 canonical_json 으로
# 간다. 같은지는 tests/test_simulator_behavior.py 가 대조한다.
_PLAIN = frozenset("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_:-")
_PLAIN_SEEN: set[str] = set()


def _plain(text: object) -> bool:
    if type(text) is not str:
        return False
    if text in _PLAIN_SEEN:
        return True
    if text and _PLAIN.issuperset(text):
        if len(_PLAIN_SEEN) < 1_000_000:
            _PLAIN_SEEN.add(text)
        return True
    return False


def _stream_key(seed: int, customer_id: str | None, purpose: str, day: int) -> bytes:
    if type(seed) is int and type(day) is int and _plain(purpose) and (
        customer_id is None or _plain(customer_id)
    ):
        who = "null" if customer_id is None else f'"{customer_id}"'
        return f'["{RNG_SCHEME}",{seed},{who},"{purpose}",{day}]'.encode("ascii")
    return canonical_json([RNG_SCHEME, seed, customer_id, purpose, day])


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


def _event_key(seed: int, customer_id: str, seq: int) -> bytes:
    # canonical_json 과 바이트까지 같은 빠른 경로(_stream_key 와 같은 조건). 같음은 tests/test_simulator_behavior.py 가 대조한다.
    if type(seed) is int and type(seq) is int and _plain(customer_id):
        return f'["{EVENT_ID_SCHEME}",{seed},"{customer_id}",{seq}]'.encode("ascii")
    return canonical_json([EVENT_ID_SCHEME, seed, customer_id, seq])


def event_id(seed: int, customer_id: str, seq: int) -> str:
    raw = bytearray(hashlib.sha256(_event_key(seed, customer_id, seq)).digest()[:16])
    raw[6] = (raw[6] & 0x0F) | 0x40
    raw[8] = (raw[8] & 0x3F) | 0x80
    text = raw.hex()
    return f"{text[:8]}-{text[8:12]}-{text[12:16]}-{text[16:20]}-{text[20:]}"
