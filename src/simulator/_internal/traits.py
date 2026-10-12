"""Hidden Trait 정수 역CDF 매듭표와 추첨 — `DR-S2-trait-sampling` 의 S-B 안.

생성 config 에서 (Trait, 페르소나)마다 K+1 = 4097 개 정수 매듭 Q[0..K] 를 만든다. 안쪽 매듭은
Q[i] = round(F⁻¹(i/K)), 양끝 매듭은 끝 셀 안 선형 보간의 평균이 실제 조건부 평균과 같게 고른다.
고객 한 명의 Trait 하나는 u64 한 번으로 뽑는다(`draw`, 셀 안 보간 뒤 반올림). u 에 단조라서 모수를 바꿔도 같은 고객은 같은 분위에 머문다.

매듭값은 정수 고정소수점(`fixedpoint`)으로 푼다. 4095 개를 모두 정확히 풀면 3.10 에서 1초 예산을
넘기므로, 양 꼬리 `_TAIL` 개와 가운데의 `_STRIDE` 칸마다만 Newton–Halley 로 정확히 풀고
그 사이는 5차 Hermite 보간으로 채운다. 분위함수의 도함수는 Q′ = 1/f(Q), Q″ = G(Q)·Q′² 이고
G = −(ln f)′ 가 유리식이라 초월함수 없이 얻는다. 정확도는 float 참조 테스트
(`tests/test_simulator_trait_distribution.py`)가 현재 config 의 모든 모양에서 잰다.
"""

from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType
from typing import Callable, Mapping, Sequence

from src.simulator._internal import fixedpoint as fx
from src.simulator._internal.genconfig import GenerationConfig, TraitSpec
from src.simulator._internal.rng import Stream

KNOTS = 4096
_CELL_BITS = 12
_POSITION_BITS = 64 - _CELL_BITS
_POSITION_MASK = (1 << _POSITION_BITS) - 1

PPM = 1_000_000

# 정확히 푸는 매듭: 양 꼬리 각 _TAIL 개 + 가운데 _STRIDE 칸마다. 꼬리는 분위함수의 고차 도함수가
# 커서 보간하지 않는다. 두 값을 바꾸면 정확도 테스트로 다시 확인한다.
_TAIL = 64
_STRIDE = 16

# 반복 종료: Halley 한 걸음이 (가까운 지지 끝까지의 거리)·2**-26 이하이면 받아들인다. 그 뒤 남는
# 오차는 걸음의 세제곱 규모라 CDF 관문(1e-6)보다 열 자릿수 이상 작다. 절대 하한 2**-60 은
# 거리가 0 인 점(정규의 z = 0)에서만 쓰인다.
_REL_TOL_SHIFT = 26
_ABS_TOL = 1 << (fx.FRAC - 60)
_MAX_ITER = 200


class _Family:
    """연속분포 하나의 CDF·밀도와 G = −(ln f)′ · G′ — 분위 엔진이 요구하는 전부."""

    lo: int
    hi: int

    def cdf_pdf(self, x: int) -> tuple[int, int]:
        raise NotImplementedError

    def hazard(self, x: int) -> tuple[int, int]:
        """(G(x), G′(x))."""
        raise NotImplementedError

    def scale(self, x: int) -> int:
        """수렴 판정의 척도. 지지 끝 근처에서는 끝까지의 거리가 의미 있는 자릿수다."""
        return abs(x)


class _Beta(_Family):
    def __init__(self, a: int, b: int) -> None:
        self.a, self.b = a, b
        self.lo, self.hi = 0, fx.ONE
        self.log_beta = fx.lgamma(a) + fx.lgamma(b) - fx.lgamma(a + b)
        # x 가 (a+1)/(a+b+2) 보다 크면 대칭 I_x(a,b) = 1 − I_{1−x}(b,a) 로 연분수 수렴을 지킨다.
        self.switch = fx.div(a + fx.ONE, a + b + 2 * fx.ONE)

    def cdf_pdf(self, x: int) -> tuple[int, int]:
        return beta_cdf_pdf(self.a, self.b, self.log_beta, self.switch, x)

    def scale(self, x: int) -> int:
        # β < 1 이면 위 꼬리 분위가 1 − 1e-14 근처까지 간다. |x| 로 재면 1 − x 의 자릿수를 잃는다.
        return min(x, fx.ONE - x)

    def hazard(self, x: int) -> tuple[int, int]:
        am, bm, rest = self.a - fx.ONE, self.b - fx.ONE, fx.ONE - x
        g = fx.div(bm, rest) - fx.div(am, x)
        slope = fx.div(fx.div(bm, rest), rest) + fx.div(fx.div(am, x), x)
        return g, slope


def beta_cdf_pdf(a: int, b: int, log_beta: int, switch: int, x: int) -> tuple[int, int]:
    """정칙 불완전 베타 I_x(a, b) 와 밀도. `log_beta` = ln B(a, b)."""
    if x <= 0:
        return 0, 0
    if x >= fx.ONE:
        return fx.ONE, 0
    rest = fx.ONE - x
    front = fx.exp(fx.mul(a, fx.ln(x)) + fx.mul(b, fx.ln(rest)) - log_beta)
    density = fx.div(fx.div(front, x), rest)
    if x < switch:
        return fx.div(fx.mul(front, _beta_cf(a, b, x)), a), density
    return fx.ONE - fx.div(fx.mul(front, _beta_cf(b, a, rest)), b), density


def _beta_cf(a: int, b: int, x: int) -> int:
    """I_x 의 Lentz 연분수(Numerical Recipes betacf). x < (a+1)/(a+b+2) 에서 빨리 수렴한다."""
    # 매듭표 생성 시간의 대부분이 이 반복이라 fx.mul·fx.div 호출을 풀어 쓴다(같은 정수 연산이다).
    one, frac = fx.ONE, fx.FRAC
    qab, qap, qam = a + b, a + one, a - one
    c = one
    d = one - ((qab * x) << frac) // (qap * one)
    d = (one << frac) // d
    h = d
    for m in range(1, 1000):
        m_one = m * one
        two_m = 2 * m_one
        aa = ((m * (((b - m_one) * x) >> frac)) << frac) // (((qam + two_m) * (a + two_m)) >> frac)
        d = (one << frac) // (one + ((aa * d) >> frac))
        c = one + (aa << frac) // c
        h = (h * ((d * c) >> frac)) >> frac
        aa = -((((a + m_one) * (((qab + m_one) * x) >> frac)) >> frac) << frac) // (
            ((a + two_m) * (qap + two_m)) >> frac
        )
        d = (one << frac) // (one + ((aa * d) >> frac))
        c = one + (aa << frac) // c
        delta = (d * c) >> frac
        h = (h * delta) >> frac
        if abs(delta - one) <= fx.CF_EPS:
            return h
    raise ArithmeticError("불완전 베타 연분수가 수렴하지 않았다")


class _Normal(_Family):
    """표준 정규. Φ(z) = (1 ± P(1/2, z²/2)) / 2 로 불완전 감마를 재사용한다."""

    # Φ(±8) 은 고정소수점에서 0·1 과 1e-15 안쪽으로 같다. 필요한 분위는 |z| < 3.5 다.
    lo, hi = -8 * fx.ONE, 8 * fx.ONE
    _S = fx.HALF
    _LGAMMA_S = fx.lgamma(fx.HALF)

    def cdf_pdf(self, z: int) -> tuple[int, int]:
        half_sq = fx.mul(z, z) >> 1
        density = fx.exp(-half_sq - fx.LN_SQRT_2PI)
        return normal_cdf(z), density

    def hazard(self, z: int) -> tuple[int, int]:
        return z, fx.ONE


def normal_cdf(z: int) -> int:
    half_sq = fx.mul(z, z) >> 1
    p, q = fx.gamma_pq(_Normal._S, half_sq, _Normal._LGAMMA_S)
    # z < 0 이면 Φ = Q/2 를 바로 쓴다 — 왼쪽 꼬리에서 작은 값을 1 − 큰 값으로 만들지 않는다.
    return (fx.ONE + p) >> 1 if z >= 0 else q >> 1


class _Gamma(_Family):
    """표준 Gamma(s, 1). 평균 1 로 맞추는 나눗셈은 표를 만들 때 한다."""

    def __init__(self, s: int) -> None:
        self.s = s
        # 상한에서 고정소수점 Q(s, y) 가 0 으로 내려가 F = 1 이 된다 — bracket 의 위쪽 끝으로 충분하다.
        self.lo, self.hi = 0, 16 * s + 64 * fx.ONE
        self.log_gamma = fx.lgamma(s)

    def cdf_pdf(self, y: int) -> tuple[int, int]:
        if y <= 0:
            return 0, 0
        p, _ = fx.gamma_pq(self.s, y, self.log_gamma)
        density = fx.exp(fx.mul(self.s - fx.ONE, fx.ln(y)) - y - self.log_gamma)
        return p, density

    def hazard(self, y: int) -> tuple[int, int]:
        sm = self.s - fx.ONE
        return fx.ONE - fx.div(sm, y), fx.div(fx.div(sm, y), y)


@dataclass(frozen=True)
class _Knot:
    x: int
    slope: int  # Q′(u) = 1/f
    curve: int  # Q″(u) = G·Q′²


def _solve(family: _Family, target: int, guess: int | None, lo: int) -> _Knot:
    """F(x) = target 를 bracket 안 Newton–Halley 로 푼다. 걸음이 bracket 을 벗어나면 이분한다."""
    hi = family.hi
    x = guess if guess is not None and lo < guess < hi else lo + ((hi - lo) >> 1)
    for _ in range(_MAX_ITER):
        cdf, density = family.cdf_pdf(x)
        gap = cdf - target
        if gap < 0:
            lo = x
        else:
            hi = x
        if density <= 0:
            x = lo + ((hi - lo) >> 1)
            continue
        step = fx.div(gap, density)
        g, _ = family.hazard(x)
        correction = fx.ONE + (fx.mul(g, step) >> 1)
        if fx.HALF < correction < 2 * fx.ONE:
            step = fx.div(step, correction)
        # 수렴 판정을 bracket 검사보다 먼저 한다. 답이 bracket 끝(F 가 목표와 정확히 같은 점)에
        # 있으면 후보가 열린 구간 밖이 되어 이분만 반복하기 때문이다.
        if abs(step) <= max(family.scale(x) >> _REL_TOL_SHIFT, _ABS_TOL):
            # 기울기는 마지막 평가점의 밀도로 둔다. 걸음이 허용치 이하라 보간에 주는 영향이 없다.
            slope = fx.div(fx.ONE, density)
            return _Knot(x - step, slope, fx.mul(g, fx.mul(slope, slope)))
        candidate = x - step
        if not lo < candidate < hi:
            x = lo + ((hi - lo) >> 1)
            continue
        x = candidate
    raise ArithmeticError(f"분위 {target} 를 {_MAX_ITER}회 안에 풀지 못했다")


def _predict(knot: _Knot, family: _Family, delta: int) -> int:
    """이전 매듭에서 3차 Taylor 로 다음 매듭을 예측한다. Q‴ = (G′ + 2G²)·Q′³."""
    g, slope_g = family.hazard(knot.x)
    third = fx.mul(slope_g + 2 * fx.mul(g, g), fx.mul(knot.slope, fx.mul(knot.slope, knot.slope)))
    d2 = fx.mul(delta, delta)
    return (
        knot.x + fx.mul(knot.slope, delta) + (fx.mul(knot.curve, d2) >> 1)
        + fx.mul(third, fx.mul(d2, delta)) // 6
    )


def _exact_indices() -> tuple[int, ...]:
    middle = range(_TAIL, KNOTS - _TAIL + 1, _STRIDE)
    indices = tuple(sorted({*range(1, _TAIL + 1), *middle, *range(KNOTS - _TAIL, KNOTS)}))
    # 보간 가중치는 간격 _STRIDE 하나로만 만든다. _TAIL 이 _STRIDE 의 배수가 아니면 다른 간격이 생긴다.
    gaps = {right - left for left, right in zip(indices, indices[1:])}
    if not gaps <= {1, _STRIDE}:
        raise AssertionError(f"정확 매듭 간격이 {sorted(gaps)} 이다 — _TAIL 을 _STRIDE 의 배수로 둔다")
    return indices


_EXACT = _exact_indices()


def _hermite_weights(m: int) -> tuple[tuple[int, ...], ...]:
    """t = j/m 에서 5차 Hermite 기저 × 2m⁵ (정수). 순서: y0, y0′, y0″, y1, y1′, y1″."""
    rows = []
    for j in range(1, m):
        t = [1, j, j * j, j * j * j, j * j * j * j, j * j * j * j * j]
        p = [t[k] * _int_pow(m, 5 - k) for k in range(6)]  # m⁵·t^k
        rows.append((
            2 * (p[0] - 10 * p[3] + 15 * p[4] - 6 * p[5]),
            2 * (p[1] - 6 * p[3] + 8 * p[4] - 3 * p[5]),
            p[2] - 3 * p[3] + 3 * p[4] - p[5],
            2 * (10 * p[3] - 15 * p[4] + 6 * p[5]),
            2 * (-4 * p[3] + 7 * p[4] - 3 * p[5]),
            p[3] - 2 * p[4] + p[5],
        ))
    return tuple(rows)


def _int_pow(base: int, exponent: int) -> int:
    value = 1
    for _ in range(exponent):
        value *= base
    return value


_HERMITE = _hermite_weights(_STRIDE)


def _fill(left: _Knot, right: _Knot) -> list[int]:
    """두 정확 매듭 사이 _STRIDE−1 개를 5차 Hermite 로 채운다. 구간 폭은 Δ = _STRIDE/K 다."""
    # y′ = Q′·Δ, y″ = Q″·Δ² 를 공통 척도 2**(2·_CELL_BITS) 로 올려 반올림 손실 없이 합친다.
    m = _STRIDE
    scale = 2 * _CELL_BITS
    terms = (
        left.x << scale, left.slope * m << _CELL_BITS, left.curve * m * m,
        right.x << scale, right.slope * m << _CELL_BITS, right.curve * m * m,
    )
    denominator = (2 * _int_pow(m, 5)) << scale
    out = []
    for weights in _HERMITE:
        total = 0
        for weight, term in zip(weights, terms):
            total += weight * term
        out.append((total + (denominator >> 1)) // denominator)
    return out


def quantiles(family: _Family) -> tuple[list[int], dict[int, _Knot]]:
    """고정소수점 분위 x_i (i = 1 … K−1, 0·K 자리는 비워 둔다)와 정확히 푼 매듭.

    정확 매듭은 작은 i 부터 차례로 푼다. 직전 매듭이 bracket 하한과 Taylor 예측의 출발점이 된다.
    """
    exact: dict[int, _Knot] = {}
    previous: _Knot | None = None
    previous_index = 0
    for index in _EXACT:
        target = fx.from_ratio(index, KNOTS)
        guess = None
        if previous is not None:
            guess = _predict(previous, family, fx.from_ratio(index - previous_index, KNOTS))
        lo = family.lo if previous is None else previous.x
        previous = exact[index] = _solve(family, target, guess, lo)
        previous_index = index
    values = [0] * (KNOTS + 1)
    ordered = list(_EXACT)
    for left_index, right_index in zip(ordered, ordered[1:]):
        values[left_index] = exact[left_index].x
        if right_index - left_index > 1:
            values[left_index + 1:right_index] = _fill(exact[left_index], exact[right_index])
    values[ordered[-1]] = exact[ordered[-1]].x
    return values, exact


@dataclass(frozen=True)
class TraitTable:
    """한 (Trait, 페르소나)의 정수 매듭 4097 개. `lo`·`hi` 는 뽑힐 수 있는 값의 범위다."""

    knots: tuple[int, ...]

    @property
    def lo(self) -> int:
        return self.knots[0]

    @property
    def hi(self) -> int:
        return self.knots[KNOTS]


_HALF_POSITION = 1 << (_POSITION_BITS - 1)


def draw(stream: Stream, table: TraitTable) -> int:
    """u64 한 번: 상위 12비트가 셀, 하위 52비트가 셀 안 위치. 거부 표집이 없어 소비 난수가 고정이다.

    셀 안 선형 보간값을 가장 가까운 정수로 반올림한다(절반은 올림). 내림이면 값이 평균 최대 0.5 단위
    아래로 치우친다. 위치가 2**52 − 1 이어도 결과는 오른쪽 매듭 Q[i+1] 을 넘지 않아 [Q[0], Q[K]] 안이다.
    """
    u = stream.next_u64()
    cell = u >> _POSITION_BITS
    position = u & _POSITION_MASK
    left = table.knots[cell]
    return left + (((table.knots[cell + 1] - left) * position + _HALF_POSITION) >> _POSITION_BITS)


def _assemble(inner: Sequence[int], lower_mean: int, upper_mean: int, lo: int, hi: int | None) -> TraitTable:
    """안쪽 정수 매듭에 양끝 매듭을 붙인다. Q[0] = 2·E[X | 첫 셀] − Q[1], Q[K] = 2·E[X | 끝 셀] − Q[K−1]."""
    knots = list(inner)
    knots[0] = max(lo, lower_mean - knots[1])
    top = upper_mean - knots[KNOTS - 1]
    knots[KNOTS] = top if hi is None else min(hi, top)
    return TraitTable(tuple(knots))


def _beta_table(a: int, kappa: int) -> TraitTable:
    b = kappa - a
    family = _Beta(a, b)
    values, exact = quantiles(family)
    inner = [0] + [fx.round_to_int(v * PPM) for v in values[1:KNOTS]] + [0]
    mean = fx.div(a, a + b)
    # E[X | X ≤ q] = μ · I_q(a+1, b) / I_q(a, b);  ln B(a+1, b) = ln B(a, b) + ln a − ln(a+b)
    shifted_log_beta = family.log_beta + fx.ln(a) - fx.ln(a + b)
    shifted_switch = fx.div(a + 2 * fx.ONE, a + b + 3 * fx.ONE)
    first, last = exact[1].x, exact[KNOTS - 1].x
    low_p, _ = family.cdf_pdf(first)
    low_shifted, _ = beta_cdf_pdf(a + fx.ONE, b, shifted_log_beta, shifted_switch, first)
    high_p, _ = family.cdf_pdf(last)
    high_shifted, _ = beta_cdf_pdf(a + fx.ONE, b, shifted_log_beta, shifted_switch, last)
    lower = fx.div(fx.mul(mean, low_shifted), low_p)
    upper = fx.div(fx.mul(mean, fx.ONE - high_shifted), fx.ONE - high_p)
    return _assemble(inner, fx.round_to_int(2 * lower * PPM), fx.round_to_int(2 * upper * PPM), 0, PPM)


@dataclass(frozen=True)
class _ScaledShape:
    """평균·중앙값을 곱하기만 하면 되는 공용 표 — 고정소수점 안쪽 매듭과 양끝 조건부 평균 배율."""

    inner: tuple[int, ...]
    lower: int
    upper: int

    def scaled(self, scale: int) -> TraitTable:
        inner = [0] + [fx.round_to_int(scale * v) for v in self.inner[1:KNOTS]] + [0]
        return _assemble(
            inner, fx.round_to_int(2 * scale * self.lower), fx.round_to_int(2 * scale * self.upper),
            0, None,
        )


def _lognormal_shape(sigma: int, z_values: Sequence[int], z_first: int, z_last: int) -> _ScaledShape:
    inner = tuple([0] + [fx.exp(fx.mul(sigma, z)) for z in z_values[1:KNOTS]] + [0])
    # E[e^{σZ} | Z ≤ z₁] = e^{σ²/2}·Φ(z₁ − σ)/Φ(z₁),  E[e^{σZ} | Z ≥ z_K−1] = e^{σ²/2}·Φ(σ − z)/Φ(−z)
    lift = fx.exp(fx.mul(sigma, sigma) >> 1)
    lower = fx.div(fx.mul(lift, normal_cdf(z_first - sigma)), normal_cdf(z_first))
    upper = fx.div(fx.mul(lift, normal_cdf(sigma - z_last)), normal_cdf(-z_last))
    return _ScaledShape(inner, lower, upper)


def _gamma_shape(shape: int) -> _ScaledShape:
    family = _Gamma(shape)
    values, exact = quantiles(family)
    inner = tuple([0] + [fx.div(v, shape) for v in values[1:KNOTS]] + [0])
    # 평균 1 척도에서 E[X; X ≤ q] = P(s+1, s·q).
    log_gamma_next = family.log_gamma + fx.ln(shape)
    first, last = exact[1].x, exact[KNOTS - 1].x
    low_p, _ = family.cdf_pdf(first)
    high_p, _ = family.cdf_pdf(last)
    low_next, _ = fx.gamma_pq(shape + fx.ONE, first, log_gamma_next)
    _, high_next = fx.gamma_pq(shape + fx.ONE, last, log_gamma_next)
    return _ScaledShape(inner, fx.div(low_next, low_p), fx.div(high_next, fx.ONE - high_p))


Tables = Mapping[str, Mapping[str, TraitTable]]
_CACHE: dict[str, Tables] = {}


def tables(config: GenerationConfig) -> Tables:
    """`{trait_name: {persona_id: TraitTable}}`. config 다이제스트로 프로세스 안에 캐시한다."""
    found = _CACHE.get(config.digest)
    if found is None:
        found = _CACHE[config.digest] = _Builder().build(config)
    return found


class _Builder:
    """같은 모양을 Trait 사이에서도 한 번만 푼다 — Beta 는 (μ, κ), LogNormal 은 σ, Gamma 는 k 가 열쇠다."""

    def __init__(self) -> None:
        self._beta: dict[tuple[int, int], TraitTable] = {}
        self._normal: tuple[list[int], dict[int, _Knot]] | None = None
        self._lognormal: dict[int, _ScaledShape] = {}
        self._gamma: dict[int, _ScaledShape] = {}

    def build(self, config: GenerationConfig) -> Tables:
        builders: dict[str, Callable[[TraitSpec], dict[str, TraitTable]]] = {
            "beta": self._beta_tables, "lognormal": self._lognormal_tables, "gamma": self._gamma_tables,
        }
        return MappingProxyType({
            spec.name: MappingProxyType(builders[spec.family](spec)) for spec in config.traits
        })

    def _beta_tables(self, spec: TraitSpec) -> dict[str, TraitTable]:
        kappa = fx.from_ratio(spec.kappa_milli, 1000)
        out: dict[str, TraitTable] = {}
        for persona, mu_ppm in spec.by_persona.items():
            key = (mu_ppm, spec.kappa_milli)
            if key not in self._beta:
                self._beta[key] = _beta_table(fx.mul(fx.from_ratio(mu_ppm, PPM), kappa), kappa)
            out[persona] = self._beta[key]
        return out

    def _lognormal_tables(self, spec: TraitSpec) -> dict[str, TraitTable]:
        if self._normal is None:
            self._normal = quantiles(_Normal())
        if spec.sigma_ppm not in self._lognormal:
            z_values, exact = self._normal
            self._lognormal[spec.sigma_ppm] = _lognormal_shape(
                fx.from_ratio(spec.sigma_ppm, PPM), z_values, exact[1].x, exact[KNOTS - 1].x
            )
        shape = self._lognormal[spec.sigma_ppm]
        return {persona: shape.scaled(median) for persona, median in spec.by_persona.items()}

    def _gamma_tables(self, spec: TraitSpec) -> dict[str, TraitTable]:
        if spec.shape_milli not in self._gamma:
            self._gamma[spec.shape_milli] = _gamma_shape(fx.from_ratio(spec.shape_milli, 1000))
        shape = self._gamma[spec.shape_milli]
        return {persona: shape.scaled(mean) for persona, mean in spec.by_persona.items()}
