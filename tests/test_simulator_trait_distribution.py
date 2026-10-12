"""Hidden Trait 매듭표·추첨이 선언한 분포를 내는지 float 참조 CDF 와 대조한다(이 파일은 float 를 쓴다).

주 검사는 결정적인 분위 정확도다(`DR-S2-trait-sampling` 2절 관문). 정밀도는 두 가지로 나눠 잰다.
- (a) 매듭표 오차 — 저장 단위 양자화를 뺀다. 관문이다.
  - 매듭값: |F(Q[i]) − i/K| ≤ 1e-6. 정수 반올림(±0.5 단위)은 F 를 감싸서 뺀다.
  - 보간: 정수 매듭 사이 연속 보간값 y 에 대해 sup_u dist(u, [F(y−0.5), F(y+0.5)]) ≤ 1e-4.
- (b) 저장 단위 해상도 포함 오차 — 실제로 뽑히는 정수 v 로 sup_u dist(u, [F(v−0.5), F(v+0.5)]).
  매듭 반올림과 추첨 반올림이 겹쳐 원리상 1e-4 를 보장할 수 없는 Trait 이 있다. Trait 별 실측 상한을
  `RESOLUTION_CEILINGS` 로 고정해 회귀만 막는다.

배선 검사는 seed 를 미리 고정한 n=26,000 표본으로 생성 경로(페르소나 추첨 → 표 선택 → 추첨)를 본다.
결정적이라 흔들리지 않는다. 기각 기준은 α=0.001(구성비 카이제곱)·Bonferroni KS·평균·분산 4 SE 다.

참조 CDF 는 시뮬레이터 코드와 독립인 float 구현이고, 각자 닫힌식·수치적분과 자기검증을 거친다.
증거 출력: `python -m tests.test_simulator_trait_distribution report`
"""

from __future__ import annotations

import math
import sys
import unittest
from collections import Counter
from functools import lru_cache

from src.simulator._internal import genconfig, persona, traits
from src.simulator._internal.genconfig import TraitSpec

K = traits.KNOTS
KNOT_GATE = 1e-6
SUP_GATE = 1e-4
WIRING_SEED = 20_261_011
WIRING_N = 26_000
CHI2_DF5_CRITICAL_0_001 = 20.515  # 카이제곱 자유도 5 의 99.9% 분위
FAMILY_ALPHA = 0.001
UNIT_SCALE = {"ppm": 1e6}  # 나머지 단위(원·밀리일·밀리회)는 정수 그대로 쓴다


# ── 참조 CDF ────────────────────────────────────────────────────────────────

def _beta_cf(a: float, b: float, x: float) -> float:
    qab, qap, qam = a + b, a + 1.0, a - 1.0
    c, d = 1.0, 1.0 - qab * x / qap
    d = 1.0 / d
    h = d
    for m in range(1, 1000):
        m2 = 2 * m
        aa = m * (b - m) * x / ((qam + m2) * (a + m2))
        d = 1.0 / (1.0 + aa * d)
        c = 1.0 + aa / c
        h *= d * c
        aa = -(a + m) * (qab + m) * x / ((a + m2) * (qap + m2))
        d = 1.0 / (1.0 + aa * d)
        c = 1.0 + aa / c
        delta = d * c
        h *= delta
        if abs(delta - 1.0) < 1e-16:
            return h
    raise ArithmeticError("참조 베타 연분수가 수렴하지 않았다")


def beta_cdf(a: float, b: float, x: float) -> float:
    if x <= 0.0:
        return 0.0
    if x >= 1.0:
        return 1.0
    log_front = (
        math.lgamma(a + b) - math.lgamma(a) - math.lgamma(b) + a * math.log(x) + b * math.log1p(-x)
    )
    if x < (a + 1.0) / (a + b + 2.0):
        return math.exp(log_front) * _beta_cf(a, b, x) / a
    return 1.0 - math.exp(log_front) * _beta_cf(b, a, 1.0 - x) / b


def beta_cdf_by_quadrature(a: float, b: float, x: float) -> float:
    """자기검증용 — 연분수와 무관한 tanh-sinh 수치적분. 끝점 특이점(a < 1)도 다룬다."""
    log_norm = math.lgamma(a + b) - math.lgamma(a) - math.lgamma(b)
    h, total = 1.0 / 64.0, 0.0
    for k in range(-320, 321):
        s = k * h
        w = math.pi / 2.0 * math.sinh(s)
        if abs(w) > 350:
            continue
        t = x / (1.0 + math.exp(-2.0 * w))
        if not 0.0 < t < 1.0:
            continue
        weight = (math.pi / 2.0) * math.cosh(s) / math.cosh(w) ** 2 * (x / 2.0)
        total += weight * math.exp((a - 1.0) * math.log(t) + (b - 1.0) * math.log1p(-t))
    return total * h * math.exp(log_norm)


def normal_cdf(z: float) -> float:
    return 0.5 * math.erfc(-z / math.sqrt(2.0))


def gamma_cdf(shape: float, y: float) -> float:
    """정칙 불완전 감마 P(shape, y) — 급수와 연분수(Numerical Recipes gser·gcf)."""
    if y <= 0.0:
        return 0.0
    log_front = shape * math.log(y) - y - math.lgamma(shape)
    if y < shape + 1.0:
        term = total = 1.0 / shape
        a = shape
        while abs(term) > abs(total) * 1e-17:
            a += 1.0
            term *= y / a
            total += term
        return total * math.exp(log_front)
    b = y + 1.0 - shape
    c, d = 1e300, 1.0 / b
    h = d
    for i in range(1, 1000):
        an = -i * (i - shape)
        b += 2.0
        d = 1.0 / (an * d + b)
        c = b + an / c
        delta = d * c
        h *= delta
        if abs(delta - 1.0) < 1e-16:
            break
    return 1.0 - math.exp(log_front) * h


class Reference:
    """config 의 (Trait, 페르소나) 하나에 대한 참조 분포 — CDF 와 정확한 적률."""

    def __init__(self, spec: TraitSpec, persona_id: str) -> None:
        self.family = spec.family
        value = spec.by_persona[persona_id]
        self.scale = UNIT_SCALE.get(spec.unit, 1.0)
        if spec.family == "beta":
            kappa = spec.kappa_milli / 1000.0
            self.a = value / 1e6 * kappa
            self.b = kappa - self.a
        elif spec.family == "lognormal":
            self.median, self.sigma = float(value), spec.sigma_ppm / 1e6
        else:
            self.mean, self.shape = float(value), spec.shape_milli / 1000.0

    def cdf(self, units: float) -> float:
        x = units / self.scale
        if self.family == "beta":
            return beta_cdf(self.a, self.b, x)
        if self.family == "lognormal":
            return normal_cdf(math.log(x / self.median) / self.sigma) if x > 0 else 0.0
        return gamma_cdf(self.shape, x * self.shape / self.mean)

    def raw_moment(self, k: int) -> float:
        """E[X^k] (단위 척도)."""
        if self.family == "beta":
            value = 1.0
            for j in range(k):
                value *= (self.a + j) / (self.a + self.b + j)
            return value * self.scale ** k
        if self.family == "lognormal":
            return self.median ** k * math.exp(k * k * self.sigma ** 2 / 2.0)
        value = 1.0
        for j in range(k):
            value *= (self.shape + j) / self.shape
        return value * self.mean ** k

    def mean_var_kurt(self) -> tuple[float, float, float]:
        m1, m2, m3, m4 = (self.raw_moment(k) for k in (1, 2, 3, 4))
        var = m2 - m1 * m1
        central4 = m4 - 4 * m1 * m3 + 6 * m1 * m1 * m2 - 3 * m1 ** 4
        return m1, var, central4

    def quantile(self, p: float) -> float:
        lo, hi = 0.0, self.scale if self.family == "beta" else 1.0
        while self.cdf(hi) < p:
            hi *= 2.0
        for _ in range(200):
            mid = (lo + hi) / 2.0
            if self.cdf(mid) < p:
                lo = mid
            else:
                hi = mid
        return (lo + hi) / 2.0


# ── 대상 ────────────────────────────────────────────────────────────────────

@lru_cache(maxsize=1)
def config() -> genconfig.GenerationConfig:
    return genconfig.active()


@lru_cache(maxsize=1)
def unique_tables() -> list[tuple[str, str, traits.TraitTable, Reference]]:
    """같은 표를 공유하는 (Trait, 페르소나)는 한 번만 잰다."""
    seen: set[int] = set()
    out = []
    built = traits.tables(config())
    for spec in config().traits:
        for persona_id in config().persona_ids:
            table = built[spec.name][persona_id]
            if id(table) in seen:
                continue
            seen.add(id(table))
            out.append((spec.name, persona_id, table, Reference(spec, persona_id)))
    return out


def knot_error(table: traits.TraitTable, ref: Reference) -> float:
    worst = 0.0
    for i in range(1, K):
        u = i / K
        below, above = ref.cdf(table.knots[i] - 0.5), ref.cdf(table.knots[i] + 0.5)
        worst = max(worst, below - u, u - above)
    return max(worst, 0.0)


_POSITIONS = 1 << 52
_INTERIOR = (1, 2, 3)  # 셀 안 1/4·1/2·3/4 지점
_EDGE_POINTS = 64  # 양끝 셀은 오차가 가장 크다(DR 표) — 촘촘히 본다
_EXACT_LEVELS = 16  # 셀 폭이 이 정수 단위 이하이면 (b) 를 정수 수준마다 정확히 잰다


def interpolated(table: traits.TraitTable, cell: int, position: int) -> int:
    """`traits.draw` 와 같은 정수 보간 — 셀 안 선형 보간 뒤 반올림."""
    left = table.knots[cell]
    return left + (((table.knots[cell + 1] - left) * position + (1 << 51)) >> 52)


def _cell_points(cell: int) -> list[int]:
    if cell in (0, K - 1):
        return [(j * _POSITIONS) // _EDGE_POINTS for j in range(1, _EDGE_POINTS)]
    return [(j * _POSITIONS) // 4 for j in _INTERIOR]


def _gap(u: float, lower: float, upper: float) -> float:
    """u 가 구간 [lower, upper] 밖으로 나간 거리."""
    return max(lower - u, u - upper, 0.0)


def table_sup_error(table: traits.TraitTable, ref: Reference) -> float:
    """관문 (a) — 매듭표·보간의 오차. 저장 단위 양자화는 뺀다.

    정수 매듭 사이의 **연속** 선형 보간값 y(u) 와 u 를 비교한다. 매듭이 ±0.5 단위로 반올림돼 있으므로
    y 도 정확한 매듭의 보간에서 ±0.5 안이다. 그래서 [F(y − 0.5), F(y + 0.5)] 와 u 의 거리를 잰다.
    """
    worst = 0.0
    for cell in range(K):
        left, right = table.knots[cell], table.knots[cell + 1]
        for position in _cell_points(cell):
            t = position / _POSITIONS
            y = left + (right - left) * t
            worst = max(worst, _gap((cell + t) / K, ref.cdf(y - 0.5), ref.cdf(y + 0.5)))
    return worst


def resolution_sup_error(table: traits.TraitTable, ref: Reference) -> float:
    """관문 (b) — 저장 단위 해상도까지 포함한 오차. 실제로 뽑히는 정수 v 로 잰다.

    반올림이라 v 는 실수 구간 [v − 0.5, v + 0.5] 를 대표한다. u 와 [F(v − 0.5), F(v + 0.5)] 의 거리를 잰다.
    매듭 반올림(±0.5)이 여기에 겹치므로 단위가 거친 Trait 은 1e-4 를 넘을 수 있다 — DR 관문 대상이 아니라
    회귀 방지용 상한으로 고정한다. 셀 폭이 `_EXACT_LEVELS` 단위 이하인 셀(양자화가 큰 곳)은 셀 안의
    정수 수준마다 u 구간의 양끝을 정확히 계산하고, 넓은 셀은 표본점으로 잰다.
    """
    worst = 0.0
    for cell in range(K):
        left, right = table.knots[cell], table.knots[cell + 1]
        width = right - left
        if width <= _EXACT_LEVELS:
            for k in range(width + 1):
                lo_t = 0.0 if width == 0 else max(0.0, (k - 0.5) / width)
                hi_t = 1.0 if width == 0 else min(1.0, (k + 0.5) / width)
                if hi_t <= lo_t:
                    continue
                v = left + k
                lower, upper = ref.cdf(v - 0.5), ref.cdf(v + 0.5)
                worst = max(worst, _gap((cell + lo_t) / K, lower, upper), _gap((cell + hi_t) / K, lower, upper))
            continue
        for position in _cell_points(cell):
            v = interpolated(table, cell, position)
            worst = max(worst, _gap((cell + position / _POSITIONS) / K, ref.cdf(v - 0.5), ref.cdf(v + 0.5)))
    return worst


def exact_mean(table: traits.TraitTable) -> float:
    """뽑힌 정수의 정확한 기댓값. 반올림이라 셀마다 (Q[i] + Q[i+1]) / 2 다(52비트 위치의 이산성은 무시)."""
    knots = table.knots
    return math.fsum(knots[i] + knots[i + 1] for i in range(K)) / (2 * K)


def exact_share_of(table: traits.TraitTable, value: int) -> float:
    """P(뽑힌 정수 = value) — 셀마다 반올림 결과가 value 인 위치의 비율을 더한다."""
    total = 0.0
    for cell in range(K):
        left, right = table.knots[cell], table.knots[cell + 1]
        width = right - left
        if width == 0:
            total += left == value
            continue
        k = value - left
        if 0 <= k <= width:
            total += min(1.0, (k + 0.5) / width) - max(0.0, (k - 0.5) / width)
    return total / K


@lru_cache(maxsize=1)
def wiring_sample() -> dict[str, dict[str, list[int]]]:
    """`{persona: {trait: [값…]}}` — seed 를 미리 고정한 생성 경로 표본."""
    sample: dict[str, dict[str, list[int]]] = {
        p: {t: [] for t in config().trait_names} for p in config().persona_ids
    }
    for index in range(WIRING_N):
        persona_id, values = persona.generate(WIRING_SEED, f"C{index + 1:08d}", config())
        bucket = sample[persona_id]
        for name, value in values.items():
            bucket[name].append(value)
    return sample


def ks_statistic(values: list[int], ref: Reference) -> float:
    ordered = sorted(values)
    n = len(ordered)
    worst = 0.0
    for i, value in enumerate(ordered):
        f = ref.cdf(value)
        worst = max(worst, f - i / n, (i + 1) / n - f)
    return worst


def ks_critical(n: int, alpha: float) -> float:
    return math.sqrt(-math.log(alpha / 2.0) / 2.0) / math.sqrt(n)


def persona_chi_square(sample: dict[str, dict[str, list[int]]]) -> float:
    first = config().trait_names[0]
    chi2 = 0.0
    for spec in config().personas:
        expected = WIRING_N * spec.ratio_bp / genconfig.RATIO_TOTAL_BP
        observed = len(sample[spec.id][first])
        chi2 += (observed - expected) ** 2 / expected
    return chi2


def moment_gaps(values: list[int], ref: Reference) -> tuple[float, float]:
    """(평균 편차 / SE, 분산 편차 / SE)."""
    n = len(values)
    mean = math.fsum(values) / n
    var = math.fsum((v - mean) ** 2 for v in values) / (n - 1)
    mu, sigma2, central4 = ref.mean_var_kurt()
    return (mean - mu) / math.sqrt(sigma2 / n), (var - sigma2) / math.sqrt((central4 - sigma2 ** 2) / n)


# ── 테스트 ──────────────────────────────────────────────────────────────────

class TestReferenceCdfsAgreeWithIndependentForms(unittest.TestCase):
    def test_beta_matches_closed_forms_and_quadrature(self) -> None:
        for x in (0.05, 0.3, 0.5, 0.77):
            self.assertAlmostEqual(x, beta_cdf(1.0, 1.0, x), places=13)
            self.assertAlmostEqual(x * x, beta_cdf(2.0, 1.0, x), places=13)
            self.assertAlmostEqual(1 - (1 - x) ** 3.5, beta_cdf(1.0, 3.5, x), places=13)
        self.assertAlmostEqual(0.5, beta_cdf(4.2, 4.2, 0.5), places=13)
        for a, b, x in ((0.48, 11.52, 1e-4), (0.48, 11.52, 0.05), (5.04, 6.96, 0.4), (10.2, 1.8, 0.7)):
            with self.subTest(a=a, b=b, x=x):
                self.assertAlmostEqual(beta_cdf_by_quadrature(a, b, x), beta_cdf(a, b, x), delta=1e-9)

    def test_normal_and_gamma_match_known_values(self) -> None:
        self.assertAlmostEqual(0.975, normal_cdf(1.959963984540054), places=12)
        self.assertAlmostEqual(1.0, normal_cdf(-1.3) + normal_cdf(1.3), places=14)
        for y in (0.2, 1.0, 4.0, 9.0, 17.0):
            closed = 1 - math.exp(-y) * (1 + y + y * y / 2 + y ** 3 / 6)
            self.assertAlmostEqual(closed, gamma_cdf(4.0, y), delta=1e-14)
            self.assertAlmostEqual(math.erf(math.sqrt(y)), gamma_cdf(0.5, y), delta=1e-14)


# 관문 (b) 회귀 방지 상한 — Trait 별 저장 단위 해상도 포함 오차의 실측 최대(`report`)에 여유를 둔 값.
# DR 관문(1e-4)을 강제하지 않는다. config·단위·추첨식을 바꾸면 다시 재서 고친다(docs/persona_spec.md 8절).
RESOLUTION_CEILINGS: dict[str, float] = {
    "base_visit_frequency": 1.5e-04,  # 실측 1.22e-04
    "base_purchase_probability": 3.9e-05,  # 실측 3.24e-05
    "base_order_value": 4.9e-05,  # 실측 4.05e-05
    "purchase_cycle": 7.4e-05,  # 실측 6.10e-05
    "price_sensitivity": 3.8e-05,  # 실측 3.13e-05
    "coupon_sensitivity": 3.9e-05,  # 실측 3.19e-05
    "shipping_fee_sensitivity": 3.9e-05,  # 실측 3.19e-05
    "brand_loyalty": 3.9e-05,  # 실측 3.19e-05
    "repurchase_propensity": 3.9e-05,  # 실측 3.19e-05
    "base_churn_propensity": 1.5e-04,  # 실측 1.22e-04
    "marketing_responsiveness": 3.7e-05,  # 실측 3.08e-05
    "marketing_fatigue": 3.9e-05,  # 실측 3.24e-05
    "search_propensity": 3.9e-05,  # 실측 3.19e-05
    "cart_abandonment_propensity": 3.9e-05,  # 실측 3.19e-05
    "cs_contact_propensity": 3.9e-05,  # 실측 3.24e-05
    "review_propensity": 3.9e-05,  # 실측 3.24e-05
}


class TestQuantileAccuracy(unittest.TestCase):
    """주 정합성 검사 — 현재 config 의 모든 고유 표."""

    def test_every_knot_is_within_the_gate(self) -> None:
        for name, persona_id, table, ref in unique_tables():
            with self.subTest(trait=name, persona=persona_id):
                self.assertLessEqual(knot_error(table, ref), KNOT_GATE)

    def test_gate_a_interpolated_table_is_within_the_sup_gate(self) -> None:
        for name, persona_id, table, ref in unique_tables():
            with self.subTest(trait=name, persona=persona_id):
                self.assertLessEqual(table_sup_error(table, ref), SUP_GATE)

    def test_gate_b_storage_resolution_error_stays_under_its_pinned_ceiling(self) -> None:
        self.assertEqual(set(config().trait_names), set(RESOLUTION_CEILINGS))
        for name, persona_id, table, ref in unique_tables():
            with self.subTest(trait=name, persona=persona_id):
                self.assertLessEqual(resolution_sup_error(table, ref), RESOLUTION_CEILINGS[name])

    def test_tables_are_monotone_and_within_the_unit_range(self) -> None:
        for name, persona_id, table, _ in unique_tables():
            knots = table.knots
            with self.subTest(trait=name, persona=persona_id):
                self.assertEqual(K + 1, len(knots))
                self.assertTrue(all(isinstance(v, int) for v in knots))
                self.assertTrue(all(a <= b for a, b in zip(knots, knots[1:])))
                self.assertGreaterEqual(knots[0], 0)
                if ref_family(name) == "beta":
                    self.assertLessEqual(knots[K], genconfig.PPM)

    def test_draw_is_the_documented_integer_interpolation(self) -> None:
        table = unique_tables()[0][2]

        class Fixed:
            def __init__(self, value: int) -> None:
                self.value = value

            def next_u64(self) -> int:
                return self.value

        self.assertEqual(table.knots[0], traits.draw(Fixed(0), table))
        top = (1 << 64) - 1
        self.assertEqual(interpolated(table, K - 1, _POSITIONS - 1), traits.draw(Fixed(top), table))
        previous = -1
        for u in range(0, 1 << 64, (1 << 64) // 997):
            value = traits.draw(Fixed(u), table)
            self.assertEqual(interpolated(table, u >> 52, u & (_POSITIONS - 1)), value)
            self.assertGreaterEqual(value, previous)
            previous = value


class TestEngineAtTheEdgesOfTheLoaderRange(unittest.TestCase):
    """로더가 받는 모수 범위의 끝 모양에서도 매듭 관문을 지키는지 — 범위 주장의 근거다(genconfig.FAMILIES).

    1 근처 분위는 float 으로 바꾸면 1 − x 의 자릿수를 잃으므로, 가까운 쪽 끝에서 잰다(I_x(a,b) = 1 − I_{1−x}(b,a)).
    """

    def raw_knot_error(self, family, cdf_near) -> float:
        values, _ = traits.quantiles(family)
        return max(abs(cdf_near(values[i]) - i / K) for i in range(1, K))

    def test_beta_shapes_at_the_range_edges(self) -> None:
        one = traits.fx.ONE
        for a, b in ((0.3, 0.7), (0.7, 0.3), (0.3, 99.7), (99.7, 0.3), (50.0, 50.0)):
            family = traits._Beta(traits.fx.from_ratio(round(a * 1000), 1000), traits.fx.from_ratio(round(b * 1000), 1000))

            def near(raw: int, a: float = a, b: float = b) -> float:
                if raw <= one // 2:
                    return beta_cdf(a, b, raw / one)
                return 1.0 - beta_cdf(b, a, (one - raw) / one)

            with self.subTest(a=a, b=b):
                self.assertLessEqual(self.raw_knot_error(family, near), KNOT_GATE)

    def test_gamma_shapes_at_the_range_edges(self) -> None:
        one = traits.fx.ONE
        for k in (1.0, 100.0):
            family = traits._Gamma(traits.fx.from_ratio(round(k * 1000), 1000))
            with self.subTest(k=k):
                self.assertLessEqual(self.raw_knot_error(family, lambda raw, k=k: gamma_cdf(k, raw / one)), KNOT_GATE)


def ref_family(name: str) -> str:
    return next(s.family for s in config().traits if s.name == name)


class TestGenerationWiring(unittest.TestCase):
    """seed 고정 n=26,000 — 생성 경로가 선언한 구성비·분포를 내는지."""

    def test_persona_mix_matches_the_declared_ratios(self) -> None:
        self.assertLess(persona_chi_square(wiring_sample()), CHI2_DF5_CRITICAL_0_001)

    def test_each_persona_trait_passes_ks_and_moment_checks(self) -> None:
        sample = wiring_sample()
        pairs = len(config().traits) * len(config().personas)
        alpha = FAMILY_ALPHA / pairs  # Bonferroni
        for spec in config().traits:
            for persona_id in config().persona_ids:
                values = sample[persona_id][spec.name]
                ref = Reference(spec, persona_id)
                with self.subTest(trait=spec.name, persona=persona_id):
                    self.assertLess(ks_statistic(values, ref), ks_critical(len(values), alpha))
                    mean_gap, var_gap = moment_gaps(values, ref)
                    self.assertLess(abs(mean_gap), 4.0)
                    self.assertLess(abs(var_gap), 4.0)


# ── 증거 출력 ───────────────────────────────────────────────────────────────

def _fmt(value: float, unit: str) -> str:
    return f"{value / 1e6:.4f}" if unit == "ppm" else f"{value:,.0f}"


def _histogram(values: list[int], unit: str, mixture) -> list[str]:
    ordered = sorted(values)
    lo, hi = ordered[len(ordered) // 1000], ordered[-len(ordered) // 1000 - 1]
    width = (hi - lo) / 20 or 1
    counts = Counter(min(19, max(0, int((v - lo) / width))) for v in values)
    peak = max(counts.values())
    lines = []
    for b in range(20):
        left, right = lo + b * width, lo + (b + 1) * width
        expected = len(values) * (mixture(right) - mixture(left)) if 0 < b < 19 else None
        bar = "#" * round(40 * counts[b] / peak)
        exp_text = "" if expected is None else f" (기대 {expected:7.0f})"
        lines.append(f"  [{_fmt(left, unit):>9}, {_fmt(right, unit):>9}) {counts[b]:6d}{exp_text} {bar}".rstrip())
    return lines


# S6 τ 입력과 PRD §19 꼬리 — DR-S2-hidden-trait-dist 「민감도」·DR-S2-persona-mix 표와 같은 정의다.
# 기준값은 단위 척도의 경계다(ppm·원).
_TAILS = (
    ("P(marketing_fatigue > 0.6) — Sleeping Dog 상한", (("marketing_fatigue", ">", 600_000),)),
    ("P(coupon > 0.6, fatigue ≤ 0.6) — Persuadable 후보", (
        ("coupon_sensitivity", ">", 600_000), ("marketing_fatigue", "<=", 600_000))),
    ("P(shipping_fee_sensitivity > 0.7)", (("shipping_fee_sensitivity", ">", 700_000),)),
    ("P(cart_abandonment_propensity > 0.6)", (("cart_abandonment_propensity", ">", 600_000),)),
    ("P(base_churn_propensity > 0.5)", (("base_churn_propensity", ">", 500_000),)),
    ("P(base_order_value > 100,000원)", (("base_order_value", ">", 100_000),)),
)


def _tail_masses(sample: dict[str, dict[str, list[int]]]) -> None:
    """생성 표본의 꼬리 질량과, 페르소나 안 독립을 가정한 해석해(참조 CDF 의 혼합)를 나란히 낸다."""
    specs = {s.name: s for s in config().traits}
    print("\n## 꼬리 질량 — 생성 표본 대 해석해(페르소나 혼합, 페르소나 안 독립)")
    print("| 질량 | 표본 | 해석해 | 표본 − 해석해 (SE 배수) |")
    print("|---|---:|---:|---:|")
    for label, conditions in _TAILS:
        hits, total, analytic = 0, 0, 0.0
        for p in config().personas:
            columns = [sample[p.id][name] for name, _, _ in conditions]
            for row in zip(*columns):
                total += 1
                hits += all((v > t) if op == ">" else (v <= t) for v, (_, op, t) in zip(row, conditions))
            mass = 1.0
            for name, op, threshold in conditions:
                below = Reference(specs[name], p.id).cdf(threshold + 0.5)
                mass *= (1.0 - below) if op == ">" else below
            analytic += p.ratio_bp / genconfig.RATIO_TOTAL_BP * mass
        observed = hits / total
        se = math.sqrt(analytic * (1 - analytic) / total)
        print(f"| {label} | {observed:.2%} | {analytic:.2%} | {(observed - analytic) / se:+.2f} |")


def _raw_knot_errors() -> dict[str, float]:
    """반올림 전 고정소수점 매듭의 오차 |F(x_i) − i/K| — 분포족별 최대. 1 근처는 가까운 끝에서 잰다."""
    one = traits.fx.ONE
    worst: dict[str, float] = {"beta": 0.0, "lognormal(정규 표)": 0.0, "gamma": 0.0}
    seen: set[tuple[str, int, int]] = set()
    for spec in config().traits:
        for persona_id in config().persona_ids:
            ref = Reference(spec, persona_id)
            if spec.family == "beta":
                key = ("beta", spec.by_persona[persona_id], spec.kappa_milli)
                if key in seen:
                    continue
                seen.add(key)
                kappa = traits.fx.from_ratio(spec.kappa_milli, 1000)
                a = traits.fx.mul(traits.fx.from_ratio(spec.by_persona[persona_id], genconfig.PPM), kappa)
                values, _ = traits.quantiles(traits._Beta(a, kappa - a))

                def cdf(raw: int, ref: Reference = ref) -> float:
                    if raw <= one // 2:
                        return beta_cdf(ref.a, ref.b, raw / one)
                    return 1.0 - beta_cdf(ref.b, ref.a, (one - raw) / one)

                label = "beta"
            elif spec.family == "lognormal":
                key = ("normal", 0, 0)
                if key in seen:
                    continue
                seen.add(key)
                values, _ = traits.quantiles(traits._Normal())
                cdf, label = (lambda raw: normal_cdf(raw / one)), "lognormal(정규 표)"
            else:
                key = ("gamma", spec.shape_milli, 0)
                if key in seen:
                    continue
                seen.add(key)
                shape = traits.fx.from_ratio(spec.shape_milli, 1000)
                values, _ = traits.quantiles(traits._Gamma(shape))
                cdf, label = (lambda raw, k=spec.shape_milli / 1000: gamma_cdf(k, raw / one)), "gamma"
            error = max(abs(cdf(values[i]) - i / K) for i in range(1, K))
            worst[label] = max(worst[label], error)
    return worst


def _precision_tables() -> None:
    raw = _raw_knot_errors()
    print("반올림 전 매듭 오차 최대: " + " · ".join(f"{k} {v:.2e}" for k, v in raw.items()) + f" (관문 {KNOT_GATE:g})")
    built = traits.tables(config())
    measured = {
        id(t): (knot_error(t, r), table_sup_error(t, r), resolution_sup_error(t, r),
                exact_mean(t) - r.mean_var_kurt()[0], r.mean_var_kurt()[0])
        for _, _, t, r in unique_tables()
    }
    print(f"\n## 정밀도 — (a) 매듭표(양자화 제외, 관문) · (b) 저장 단위 해상도 포함(회귀 상한) · 평균 편향")
    print("| Trait | 단위 | (a) 매듭 최대 | (a) 보간 sup 최대 | (b) 해상도 포함 sup 최대 (페르소나) | (b) 고정 상한 | "
          "평균 편향 최대 (단위 · 상대) |")
    print("|---|---|---:|---:|---|---:|---|")
    for spec in config().traits:
        rows = [(measured[id(built[spec.name][p])], p) for p in config().persona_ids]
        knot = max(m[0] for m, _ in rows)
        table = max(m[1] for m, _ in rows)
        resolution, where = max((m[2], p) for m, p in rows)
        bias, mean = max(((m[3], m[4]) for m, _ in rows), key=lambda bm: abs(bm[0]))
        print(f"| `{spec.name}` | {spec.unit} | {knot:.2e} | {table:.2e} | {resolution:.2e} ({where}) | "
              f"{RESOLUTION_CEILINGS.get(spec.name, float('nan')):.1e} | {bias:+.3f} · {bias / mean:+.1e} |")
    zero = []
    for spec in config().traits:
        if spec.family != "beta":
            continue
        for p in config().persona_ids:
            share = exact_share_of(built[spec.name][p], 0)
            if share > 0:
                ref = Reference(spec, p)
                zero.append(f"`{spec.name}` · {p}: P(값 = 0 ppm) = {share:.4%} (참조 F(0.5 ppm) = {ref.cdf(0.5):.4%})")
    print("\n0 ppm 으로 저장되는 질량: " + ("; ".join(zero) if zero else "없음"))


def report() -> None:
    import time

    started = time.perf_counter()
    traits._CACHE.clear()
    traits.tables(config())
    build_seconds = time.perf_counter() - started
    print(f"Python {sys.version.split()[0]} · config {config().version} · digest {config().digest}")
    print(f"매듭표 생성 {build_seconds:.3f}s (K={K}, 고유 표 {len(unique_tables())}개)")
    _precision_tables()
    sample = wiring_sample()
    first = config().trait_names[0]
    print(f"\n## 구성비 (seed {WIRING_SEED}, n={WIRING_N:,})")
    print("| 페르소나 | 선언 bp | 실현 bp | 인원 |")
    print("|---|---:|---:|---:|")
    for spec in config().personas:
        count = len(sample[spec.id][first])
        print(f"| {spec.alias} `{spec.id}` | {spec.ratio_bp} | {count * 10000 / WIRING_N:.0f} | {count:,} |")
    chi2 = persona_chi_square(sample)
    print(f"카이제곱(자유도 5) = {chi2:.2f} · 임계값(α=0.001) {CHI2_DF5_CRITICAL_0_001} → "
          f"{'PASS' if chi2 < CHI2_DF5_CRITICAL_0_001 else 'FAIL'}")
    pairs = len(config().traits) * len(config().personas)
    alpha = FAMILY_ALPHA / pairs
    print(f"\n## (페르소나, Trait) 요약 — KS α={FAMILY_ALPHA}/{pairs} (Bonferroni), 평균·분산은 4 SE")
    print("| Trait | 페르소나 | n | 평균 (목표) | 표준편차 (목표) | p10 / p50 / p90 (목표) | KS D / 임계 | 평균·분산 z | 판정 |")
    print("|---|---|---:|---|---|---|---|---|---|")
    failures = 0
    for spec in config().traits:
        for p in config().personas:
            values = sample[p.id][spec.name]
            ref = Reference(spec, p.id)
            n = len(values)
            ordered = sorted(values)
            mean = math.fsum(values) / n
            sd = math.sqrt(math.fsum((v - mean) ** 2 for v in values) / (n - 1))
            mu, var, _ = ref.mean_var_kurt()
            q = [ordered[int(f * n)] for f in (0.1, 0.5, 0.9)]
            qt = [ref.quantile(f) for f in (0.1, 0.5, 0.9)]
            d, crit = ks_statistic(values, ref), ks_critical(n, alpha)
            zm, zv = moment_gaps(values, ref)
            ok = d < crit and abs(zm) < 4 and abs(zv) < 4
            failures += not ok
            u = spec.unit
            print(
                f"| `{spec.name}` | {p.alias} | {n:,} | {_fmt(mean, u)} ({_fmt(mu, u)}) | "
                f"{_fmt(sd, u)} ({_fmt(math.sqrt(var), u)}) | "
                f"{' / '.join(_fmt(v, u) for v in q)} ({' / '.join(_fmt(v, u) for v in qt)}) | "
                f"{d:.4f} / {crit:.4f} | {zm:+.2f} · {zv:+.2f} | {'PASS' if ok else 'FAIL'} |"
            )
    print(f"\n판정: {pairs - failures}/{pairs} PASS")
    _tail_masses(sample)
    print("\n## 모집단 히스토그램 (20구간, 양끝 0.1% 제외 범위, 기대 = 페르소나 혼합 CDF)")
    for spec in config().traits:
        values = [v for p in config().persona_ids for v in sample[p][spec.name]]
        refs = [(s.ratio_bp / genconfig.RATIO_TOTAL_BP, Reference(spec, s.id)) for s in config().personas]

        def mixture(x: float, refs=refs) -> float:
            return math.fsum(w * r.cdf(x) for w, r in refs)

        print(f"\n### `{spec.name}` ({spec.family}, 단위 {spec.unit})")
        print("\n".join(_histogram(values, spec.unit, mixture)))


if __name__ == "__main__":
    if sys.argv[1:] == ["report"]:
        report()
    else:
        unittest.main()
