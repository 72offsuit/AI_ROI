"""정수 고정소수점 수치 함수 — 실수 x 를 정수 `round(x · 2**FRAC)` 로 나타낸다.

시뮬레이터는 결과에 들어가는 값에 float 을 쓰지 않는다(`DR-S1-rng`). 플랫폼 libm 은 마지막 비트가
판·OS 마다 다를 수 있어서, Trait 매듭표(`traits.py`)가 쓰는 ln·exp·lgamma·불완전 감마를 여기서
정수 연산만으로 구현한다. 같은 입력이면 어느 Python 판·플랫폼에서도 같은 정수를 낸다.

정확도는 절대오차 몇 ulp(≈1e-18) 수준이다. 매듭표 관문(CDF 오차 1e-6)보다 열두 자릿수 작다.
상수(ln 2·π·표)는 import 때 정수 급수로 만든다 — 손으로 옮긴 매직 넘버를 두지 않는다.
"""

from __future__ import annotations

FRAC = 64
ONE = 1 << FRAC
HALF = ONE >> 1

# 상수를 만들 때만 쓰는 보호 비트. 급수 항마다 생기는 내림 오차를 최종 자리 아래로 밀어낸다.
_GUARD = 32


def mul(a: int, b: int) -> int:
    return (a * b) >> FRAC


def div(a: int, b: int) -> int:
    if b == 0:
        raise ZeroDivisionError("고정소수점 나눗셈의 분모가 0 이다")
    return (a << FRAC) // b


def from_ratio(numerator: int, denominator: int) -> int:
    return (numerator << FRAC) // denominator


def round_to_int(raw: int) -> int:
    """고정소수점 값을 가장 가까운 정수로 반올림한다(0.5 는 올림)."""
    return (raw + HALF) >> FRAC


def _atanh_ratio(p: int, q: int, bits: int) -> int:
    """atanh(p/q)·2**bits, 0 <= p/q < 1. ln 상수를 만드는 데만 쓴다."""
    scale = 1 << bits
    term = (scale * p) // q
    q2, p2 = q * q, p * p
    total, n = 0, 1
    while term:
        total += term // n
        term = (term * p2) // q2
        n += 2
    return total


def _atan_inverse(x: int, bits: int) -> int:
    """atan(1/x)·2**bits — Machin 공식용."""
    term = (1 << bits) // x
    x2 = x * x
    total, n, sign = 0, 1, 1
    while term:
        total += sign * (term // n)
        term //= x2
        n += 2
        sign = -sign
    return total


_WIDE = FRAC + _GUARD
LN2 = (2 * _atanh_ratio(1, 3, _WIDE)) >> _GUARD
PI = (16 * _atan_inverse(5, _WIDE) - 4 * _atan_inverse(239, _WIDE)) >> _GUARD

# ln 은 가수 m ∈ [1, 2) 를 16칸으로 나눠 칸 중심 c_j = 1 + (2j+1)/32 로 줄인다.
# 그러면 s = (m − c)/(m + c) 가 1/65 미만이라 atanh 급수가 여섯 항 안에 끝난다.
_LN_CELLS = 16
_LN_CENTERS = tuple(ONE + ((2 * j + 1) << FRAC) // 32 for j in range(_LN_CELLS))
_LN_OF_CENTERS = tuple(
    (2 * _atanh_ratio(2 * j + 1, 65 + 2 * j, _WIDE)) >> _GUARD for j in range(_LN_CELLS)
)


def ln(x: int) -> int:
    if x <= 0:
        raise ValueError(f"ln 의 인자가 양수가 아니다: {x}")
    shift = x.bit_length() - 1 - FRAC
    mantissa = x >> shift if shift >= 0 else x << -shift
    cell = (mantissa - ONE) >> (FRAC - 4)
    center = _LN_CENTERS[cell]
    s = ((mantissa - center) << FRAC) // (mantissa + center)
    # 음수에 >> 를 쓰면 −1 에서 멈추지 않으므로 크기로 급수를 돌리고 부호를 마지막에 붙인다.
    negative = s < 0
    s = -s if negative else s
    s2 = (s * s) >> FRAC
    term, total, n = s, s, 1
    while term:
        term = (term * s2) >> FRAC
        n += 2
        total += term // n
    if negative:
        total = -total
    return shift * LN2 + _LN_OF_CENTERS[cell] + 2 * total


# exp 는 y = k·ln2 + j·(ln2/16) + r 로 나눈다. 2**(j/16) 표가 있어 r < 0.044 이고 Taylor 가 열 항 안에 끝난다.
_EXP_STEP = LN2 // 16


def _exp_series(r: int, bits: int) -> int:
    """exp(r)·2**bits, r 은 같은 척도의 0 이상 값."""
    scale = 1 << bits
    term, total, n = scale, scale, 1
    while term:
        term = (term * r) >> bits
        term //= n
        total += term
        n += 1
    return total


_EXP_TABLE = tuple(
    _exp_series((j * _EXP_STEP) << _GUARD, _WIDE) >> _GUARD for j in range(17)
)


def exp(y: int) -> int:
    k = y // LN2
    r = y - k * LN2
    j = r // _EXP_STEP
    r -= j * _EXP_STEP
    value = (_EXP_TABLE[j] * _exp_series(r, FRAC)) >> FRAC
    return value << k if k >= 0 else value >> -k


LN_SQRT_2PI = (LN2 + ln(PI)) >> 1

# Stirling 급수 계수 B_2k / (2k(2k−1)), k = 1 … 7. z ≥ 16 에서 다음 항이 3e-20 미만이다.
_STIRLING = ((1, 12), (-1, 360), (1, 1260), (-1, 1680), (1, 1188), (-691, 360360), (1, 156))
_STIRLING_FROM = 16 * ONE


def lgamma(x: int) -> int:
    """ln Γ(x), x > 0. 작은 x 는 Γ(x+1) = x·Γ(x) 로 16 이상까지 올린 뒤 Stirling 급수를 쓴다."""
    if x <= 0:
        raise ValueError(f"lgamma 의 인자가 양수가 아니다: {x}")
    product = ONE
    while x < _STIRLING_FROM:
        product = (product * x) >> FRAC
        x += ONE
    inverse = div(ONE, x)
    inverse_sq = mul(inverse, inverse)
    power, series = inverse, 0
    for numerator, denominator in _STIRLING:
        series += (power * numerator) // denominator
        power = mul(power, inverse_sq)
    value = mul(x - HALF, ln(x)) - x + LN_SQRT_2PI + series
    return value - ln(product) if product != ONE else value


# 불완전 감마 연분수의 "1/FPMIN" 자리. an/c 가 첫 단계에서 사실상 0 이 되면 충분하다.
_HUGE = ONE << FRAC
_MAX_TERMS = 1000
# 연분수 종료 기준 |delta − 1| ≤ 2**-52. 단계마다 몇 ulp 의 내림 오차가 있어 ulp 단위로 기다리면 끝나지 않는다.
CF_EPS = ONE >> 52


def gamma_pq(s: int, x: int, lgamma_s: int) -> tuple[int, int]:
    """정칙 불완전 감마 (P(s, x), Q(s, x)) — P + Q = 1. `lgamma_s` 는 ln Γ(s).

    x < s + 1 이면 급수로 P 를, 아니면 Lentz 연분수로 Q 를 직접 구한다(Numerical Recipes gser·gcf).
    작은 쪽을 직접 구하므로 앞인자 e^(−x)·x^s 가 0 으로 내려가도 큰 쪽은 1 로 정확하다.
    """
    if x <= 0:
        return 0, ONE
    log_front = mul(s, ln(x)) - x - lgamma_s
    if x < s + ONE:
        # P = e^(−x) x^s / Γ(s+1) · Σ x^n / ((s+1)…(s+n)),  Γ(s+1) = s·Γ(s)
        term = div(ONE, s)
        total, a = term, s
        for _ in range(_MAX_TERMS):
            a += ONE
            term = div(mul(term, x), a)
            total += term
            if term == 0:
                break
        else:
            raise ArithmeticError("불완전 감마 급수가 수렴하지 않았다")
        front = exp(log_front)
        p = mul(front, total)
        return p, ONE - p
    b = x + ONE - s
    c = _HUGE
    d = div(ONE, b)
    h = d
    for i in range(1, _MAX_TERMS):
        an = -i * (i * ONE - s)
        b += 2 * ONE
        d = mul(an, d) + b
        d = div(ONE, d)
        c = b + div(an, c)
        delta = mul(d, c)
        h = mul(h, delta)
        if abs(delta - ONE) <= CF_EPS:
            break
    else:
        raise ArithmeticError("불완전 감마 연분수가 수렴하지 않았다")
    front = exp(log_front)
    q = mul(front, h)
    return ONE - q, q
