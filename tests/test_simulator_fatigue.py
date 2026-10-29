"""#183 ④ — 처치 반복 노출 시 반응 감쇠(피로 동학).

- 노출 수 n(`treatment.prior_exposures`)은 실제로 난 노출 이벤트 수와 같다(T0·같은 시각 덮어쓰기 제외).
- 첫 노출(n = 0)은 반복 노출 계수와 무관하고, 도입 전 식과 비트 단위로 같다 — 단일 배정 실행이 바뀌지 않는다.
- n 이 늘면 모집단 Positive 비율은 줄고 Negative 비율은 줄지 않는다. 고객 한 명 단위로도 단조다(CRN).
- 반사실(`potential_outcomes`)의 반응 유형은 실제 실행의 반응 유형과 같은 노출 수에서 정해진다.
- config `behavior.treatment.repeat_exposure` 키가 빠지거나 남거나 범위를 벗어나면 로드를 거부한다.
"""

from __future__ import annotations

import json
import unittest
from collections import defaultdict
from unittest import mock

from src.measurement import sink as sk
from src.simulator import api
from src.simulator._internal import clock, engine, genconfig, params, rng, treatment
from src.simulator._internal import world as world_state
from tests.test_simulator_support import REPO_ROOT, SimulatorCase, event_digest

ARMS = ("T1", "T2", "T3", "T4")
RANK = {treatment.POSITIVE: 0, treatment.NEUTRAL: 1, treatment.NEGATIVE: 2}
_TWO_64 = 1 << 64


def config_document() -> dict[str, object]:
    return json.loads((REPO_ROOT / "config" / "simulator_config.yaml").read_text(encoding="utf-8"))


def repeat_block(doc: dict[str, object]) -> dict[str, object]:
    return doc["behavior"]["treatment"]["repeat_exposure"]


def extreme_config() -> genconfig.GenerationConfig:
    """반복 노출 계수를 극단값으로 바꾼 config — 첫 노출이 이 계수를 읽으면 결과가 달라지게 만든다."""
    doc = config_document()
    repeat_block(doc).update(
        positive_decay_pct=100, positive_floor_pct=0, negative_step_pct=100, negative_max_pct=100
    )
    return genconfig.parse(json.dumps(doc, ensure_ascii=False))


def legacy_response_type(seed: int, cid: str, traits: dict[str, int], tid: str, p: params.Params) -> str:
    """반복 노출 도입 전 `treatment.response_type` 의 식을 그대로 옮긴 것 — n = 0 불변의 기준이다."""
    fatigue = traits["fatigue"] * p.negative_scale_pct // 100
    if rng.Stream(seed, cid, "response", rng.RESPONSE_DAY).next_u64() < fatigue * _TWO_64 // params.PPM:
        return treatment.NEGATIVE
    chance = (traits[tid] + traits["responsiveness"]) // 2 * p.positive_scale_pct // 100
    if rng.Stream(seed, cid, "response:" + tid, rng.RESPONSE_DAY).next_u64() < chance * _TWO_64 // params.PPM:
        return treatment.POSITIVE
    return treatment.NEUTRAL


def assign(world: dict[str, object], plan: dict[str, str]) -> None:
    """`api.apply_treatment` 와 같은 자리에 배정과 노출 항목을 적는다(참 효과 기록은 하지 않는다).

    api 는 `advance` 때 상태를 정렬해 다시 읽어 힙을 복원한다. 여기서는 엔진을 바로 돌리므로 정렬로 힙을 맞춘다.
    """
    now = world["now_ms"]
    for cid in sorted(plan):
        customer = world["customers"][world_state.customer_index(cid)]
        customer["assignments"].append([now, plan[cid]])
        world["queue"].append((now, cid, engine.next_seq(customer), "treat"))
    world["queue"].sort()


def drain(world: dict[str, object], days: int) -> list[dict[str, object]]:
    return list(engine.run(world, world["now_ms"] + days * clock.DAY_MS))


class TestPriorExposures(unittest.TestCase):
    def test_counts_earlier_non_t0_assignments_once_per_time(self) -> None:
        cases = [
            ([], 0),
            ([[10, "T3"]], 0),
            ([[10, "T3"], [20, "T3"]], 1),
            ([[10, "T3"], [20, "T0"], [30, "T1"]], 1),  # T0 은 노출이 아니다
            ([[10, "T3"], [10, "T4"], [20, "T2"]], 1),  # 같은 시각 덮어쓰기는 한 번
            ([[10, "T3"], [10, "T0"], [20, "T2"]], 0),  # 같은 시각에 T0 으로 덮어쓰면 노출이 없다
            ([[10, "T1"], [20, "T2"], [20, "T3"]], 1),  # 현재 시각의 앞선 항목은 덮어쓰인 것이다
            ([[10, "T1"], [20, "T2"], [30, "T0"]], 2),  # 현재가 T0 이어도 앞선 노출은 센다
        ]
        for assignments, expected in cases:
            with self.subTest(assignments=assignments):
                self.assertEqual(expected, treatment.prior_exposures(assignments))


class TestExposureCountMatchesEmittedExposures(SimulatorCase):
    """api 로 T0·같은 시각 덮어쓰기를 섞어 배정하고, 실제로 난 노출 이벤트 수와 n 의 정의를 대조한다."""

    CUSTOMERS = 40

    def test_prior_exposures_equals_campaign_exposed_events_before_the_last_assignment(self) -> None:
        root = self.start(seed=5, customers=self.CUSTOMERS, profile="small")
        ids = [f"C{i:08d}" for i in range(1, self.CUSTOMERS + 1)]
        history: dict[str, list[list]] = defaultdict(list)

        def apply(step: int, plan: dict[str, str]) -> None:
            api.apply_treatment(plan)
            for cid, tid in plan.items():
                history[cid].append([step, tid])

        api.advance(30)
        apply(1, dict.fromkeys(ids, "T3"))
        api.advance(10)
        apply(2, {cid: ("T0" if index % 2 else "T1") for index, cid in enumerate(ids)})
        api.advance(10)
        apply(3, dict.fromkeys(ids, "T2"))
        apply(3, dict.fromkeys(ids[:10], "T4"))  # 같은 시각 덮어쓰기
        api.advance(10)
        apply(4, dict.fromkeys(ids, "T3"))
        api.advance(5)

        exposed: dict[str, set[str]] = defaultdict(set)
        for record in sk.read_events(root):
            if record["event_type"] == "campaign_exposed":
                exposed[str(record["customer_id"])].add(str(record["timestamp"]))
        for cid in ids:
            with self.subTest(customer=cid):
                # 마지막 배정(T3)도 노출되므로 그 앞의 노출 수는 전체 노출 시각 수 − 1 이다.
                self.assertEqual(len(exposed[cid]) - 1, treatment.prior_exposures(history[cid]))
        self.assertEqual({2, 3}, {treatment.prior_exposures(history[cid]) for cid in ids})


class TestFirstExposureIsUnchanged(SimulatorCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.world = world_state.new_world(42, 2000, "small")

    def test_first_exposure_matches_the_pre_fatigue_formula_bit_for_bit(self) -> None:
        p = params.active()
        for customer in self.world["customers"]:
            traits = world_state.behavior_traits(customer)
            for tid in ARMS:
                expected = legacy_response_type(42, customer["customer_id"], traits, tid, p)
                actual = treatment.response_type(42, customer["customer_id"], traits, tid, p, 0)
                if expected != actual:
                    self.fail(f"{customer['customer_id']} {tid}: {expected} → {actual}")

    def test_first_exposure_probabilities_do_not_read_repeat_exposure_coefficients(self) -> None:
        default = params.active()
        extreme = params.Params(extreme_config())
        for fatigue in (0, 1, 123_457, 600_000, params.PPM):
            self.assertEqual(
                treatment.negative_ppm(fatigue, 0, default), treatment.negative_ppm(fatigue, 0, extreme)
            )
            self.assertEqual(
                treatment.positive_ppm(fatigue, 0, default), treatment.positive_ppm(fatigue, 0, extreme)
            )

    def run_single_assignment(self, config: genconfig.GenerationConfig | None) -> tuple[str, list[dict]]:
        patch = mock.patch.object(genconfig, "_ACTIVE", config) if config else mock.patch.object(
            genconfig, "_ACTIVE", genconfig.active()
        )
        hidden = self.fresh_root("hidden")
        with patch:
            root = self.fresh_root("out")
            api.init(13, 60, "small", root, hidden_root=hidden)
            api.advance(30)
            api.apply_treatment({f"C{i:08d}": ARMS[i % 4] for i in range(1, 61)})
            api.advance(42)
            digest = event_digest(sk.read_events(root))
        files = sorted((hidden / "ground_truth").glob("po-*.jsonl"))
        self.assertEqual(1, len(files))
        rows = [json.loads(line) for line in files[0].read_text(encoding="ascii").splitlines()]
        return digest, [{k: v for k, v in row.items() if k != "at"} for row in rows]

    def test_single_assignment_run_is_identical_under_any_repeat_exposure_coefficients(self) -> None:
        self.assertEqual(self.run_single_assignment(None), self.run_single_assignment(extreme_config()))


class TestDecayCurve(unittest.TestCase):
    """5,000명 small 모집단에서 n = 0..10 의 반응 유형 구성."""

    N = range(0, 11)

    @classmethod
    def setUpClass(cls) -> None:
        cls.customers = world_state.new_world(42, 5000, "small")["customers"]
        cls.p = params.active()

    def test_population_positive_share_falls_and_negative_share_does_not(self) -> None:
        rule = self.p.repeat_exposure
        self.assertGreater(rule.positive_decay_pct, 0, "감쇠가 꺼진 config 로는 이 검사가 의미 없다")
        # #196: 배율이 상한(100)이면 반복 노출이 Negative 를 더 늘리지 않는다 — 늘지 않되 줄지도 않는다. 증가 모양은
        # TestDecayShapeIsPinned 가 배율 40 · 상한 60 으로 따로 고정한다.
        grows = rule.negative_max_pct > self.p.negative_scale_pct
        for tid in ARMS:
            curve = [treatment.response_mix(42, self.customers, tid, n) for n in self.N]
            positive = [mix[treatment.POSITIVE] for mix in curve]
            negative = [mix[treatment.NEGATIVE] for mix in curve]
            with self.subTest(arm=tid, positive=positive, negative=negative):
                self.assertEqual(positive, sorted(positive, reverse=True))
                self.assertEqual(negative, sorted(negative))
                self.assertLess(positive[1], positive[0])
                if grows:
                    self.assertLess(negative[0], negative[-1])
                else:
                    self.assertEqual(negative[0], negative[-1])
                for mix in curve:
                    self.assertEqual(len(self.customers), sum(mix.values()))

    def test_each_customer_only_moves_towards_negative_as_exposures_grow(self) -> None:
        for customer in self.customers[:1000]:
            traits = world_state.behavior_traits(customer)
            for tid in ARMS:
                ranks = [
                    RANK[treatment.response_type(42, customer["customer_id"], traits, tid, self.p, n)]
                    for n in self.N
                ]
                if ranks != sorted(ranks):
                    self.fail(f"{customer['customer_id']} {tid}: {ranks}")


# seed 42 · 5,000명 small(Day 0 Trait) 전원이 앞선 노출 n 번 뒤 그 처치를 받을 때의 (Positive, Neutral, Negative) 인원.
# DR-183-repeat-exposure 의 반응 유형 표(n = 0..3, sim-0.6 계수)와 같은 표본이다 — #196 에서 Negative 배율 · 상한 100 으로
# 다시 계산했다(배율 · 상한 100 — Negative 는 노출 수와 무관하게 같다). n = 7 은 Positive
# 바닥(첫 노출의 50%)에 처음 닿는 자리라 그 너머(n = 8)까지 고정해 감쇠의 모양 전체를 잡는다.
RESPONSE_MIX_GOLDEN: dict[str, tuple[tuple[int, int, int], ...]] = {
    "T1": (
        (1825, 1799, 1376), (1631, 1993, 1376), (1451, 2173, 1376), (1311, 2313, 1376), (1178, 2446, 1376),
        (1060, 2564, 1376), (945, 2679, 1376), (887, 2737, 1376), (887, 2737, 1376),
    ),
    "T2": (
        (1917, 1707, 1376), (1711, 1913, 1376), (1519, 2105, 1376), (1368, 2256, 1376), (1239, 2385, 1376),
        (1115, 2509, 1376), (1009, 2615, 1376), (944, 2680, 1376), (944, 2680, 1376),
    ),
    "T3": (
        (1879, 1745, 1376), (1700, 1924, 1376), (1528, 2096, 1376), (1374, 2250, 1376), (1216, 2408, 1376),
        (1087, 2537, 1376), (982, 2642, 1376), (915, 2709, 1376), (915, 2709, 1376),
    ),
    "T4": (
        (2086, 1538, 1376), (1882, 1742, 1376), (1693, 1931, 1376), (1501, 2123, 1376), (1353, 2271, 1376),
        (1212, 2412, 1376), (1102, 2522, 1376), (1034, 2590, 1376), (1034, 2590, 1376),
    ),
}


class TestDecayShapeIsPinned(unittest.TestCase):
    """감쇠의 모양(기하 감쇠·가산 step·바닥·상한)을 고정한다.

    다른 테스트는 단조성·범위만 보거나 기대값을 같은 함수로 계산해, 감쇠 식을 바꿔도(예: 선형 감쇠) 통과한다.
    여기서는 손으로 계산한 정수와 모집단 인원을 그대로 대조한다. 계수(config)를 바꾸면 이 표도 함께 고친다.
    """

    def test_probabilities_match_hand_computed_integers(self) -> None:
        p = params.active()
        rule = p.repeat_exposure
        self.assertEqual((10, 50, 5, 100), (
            rule.positive_decay_pct, rule.positive_floor_pct, rule.negative_step_pct, rule.negative_max_pct
        ))
        self.assertEqual((100, 100), (p.negative_scale_pct, p.positive_scale_pct))
        # 800,000 × 0.9ⁿ (정수 내림) — 0.9⁷ = 0.478 < 0.5 이므로 n = 7 부터 바닥 400,000.
        self.assertEqual(
            [800_000, 720_000, 648_000, 583_200, 524_880, 472_392, 425_152, 400_000, 400_000],
            [treatment.positive_ppm(800_000, n, p) for n in range(9)],
        )
        # 500,000 × min(100 + 5n, 100)% — #196 에서 배율이 상한(100)이라 반복 노출이 Negative 를 더 늘리지 않는다.
        self.assertEqual([500_000] * 7, [treatment.negative_ppm(500_000, n, p) for n in range(7)])
        # 가산 step · 상한의 모양은 지금 config 에서 드러나지 않으므로 배율 40 · 상한 60 으로 따로 고정한다.
        doc = config_document()
        doc["behavior"]["treatment"]["negative_scale_pct"] = 40
        repeat_block(doc)["negative_max_pct"] = 60
        stepped = params.Params(genconfig.parse(json.dumps(doc, ensure_ascii=False)))
        self.assertEqual(
            [200_000, 225_000, 250_000, 275_000, 300_000, 300_000, 300_000],
            [treatment.negative_ppm(500_000, n, stepped) for n in range(7)],
        )

    def test_population_mix_matches_the_golden_table(self) -> None:
        customers = world_state.new_world(42, 5000, "small")["customers"]
        for tid, rows in RESPONSE_MIX_GOLDEN.items():
            observed = tuple(
                (mix[treatment.POSITIVE], mix[treatment.NEUTRAL], mix[treatment.NEGATIVE])
                for mix in (treatment.response_mix(42, customers, tid, n) for n in range(len(rows)))
            )
            self.assertEqual(rows, observed, tid)


class TestProbabilityBounds(unittest.TestCase):
    def test_probabilities_stay_within_the_trait_and_the_floor_under_extreme_coefficients(self) -> None:
        for p in (params.active(), params.Params(extreme_config())):
            rule = p.repeat_exposure
            for trait in (0, 1, 499_999, params.PPM):
                first = treatment.positive_ppm(trait, 0, p)
                for n in (1, 2, 5, 50, 10_000):
                    with self.subTest(trait=trait, n=n, rule=rule):
                        self.assertLessEqual(0, treatment.negative_ppm(trait, n, p))
                        self.assertLessEqual(treatment.negative_ppm(trait, n, p), trait * rule.negative_max_pct // 100)
                        chance = treatment.positive_ppm(trait, n, p)
                        self.assertLessEqual(chance, first)
                        self.assertGreaterEqual(chance, first * rule.positive_floor_pct // 100 - 1)


class TestCommonRandomNumbers(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.world = world_state.new_world(7, 300, "small")
        cls.p = params.active()

    def test_type_depends_only_on_the_fixed_draws_and_the_threshold_of_n(self) -> None:
        for customer in self.world["customers"]:
            cid = customer["customer_id"]
            traits = world_state.behavior_traits(customer)
            u_negative = rng.Stream(7, cid, "response", rng.RESPONSE_DAY).next_u64()
            for tid in ARMS:
                u_positive = rng.Stream(7, cid, "response:" + tid, rng.RESPONSE_DAY).next_u64()
                sensitivity = (traits[tid] + traits["responsiveness"]) // 2
                for n in range(5):
                    if u_negative < treatment.negative_ppm(traits["fatigue"], n, self.p) * _TWO_64 // params.PPM:
                        expected = treatment.NEGATIVE
                    elif u_positive < treatment.positive_ppm(sensitivity, n, self.p) * _TWO_64 // params.PPM:
                        expected = treatment.POSITIVE
                    else:
                        expected = treatment.NEUTRAL
                    self.assertEqual(expected, treatment.response_type(7, cid, traits, tid, self.p, n), (cid, tid, n))

    def test_same_count_from_different_histories_gives_the_same_type_without_touching_day_draws(self) -> None:
        window = engine._Window(self.world, None)
        histories = (
            [[1_000, "T1"], [2_000, "T4"]],
            [[1_000, "T3"], [1_000, "T2"], [1_500, "T0"], [2_000, "T2"]],  # 덮어쓰기·T0 을 섞은 같은 n = 2
        )
        at_ms = 3_000
        for customer in self.world["customers"]:
            for tid in ARMS:
                found = set()
                for history in histories:
                    copy = {**customer, "assignments": [*history, [at_ms, tid]]}
                    before = sorted((repr(key), s._count) for key, s in window.draws._streams.items())
                    found.add(treatment.effect(window, copy, at_ms)[1])
                    after = sorted((repr(key), s._count) for key, s in window.draws._streams.items())
                    self.assertEqual(before, after, "반응 유형이 하루 난수 스트림을 소비했다")
                self.assertEqual(1, len(found), (customer["customer_id"], tid))
        self.assertIn((self.world["customers"][0]["customer_id"], "T1", 2), window.responses)


class TestCounterfactualTypesFollowExposures(unittest.TestCase):
    def test_potential_outcome_types_equal_the_effect_of_the_real_assignment(self) -> None:
        world = world_state.new_world(21, 300, "small")
        drain(world, 40)
        ids = [c["customer_id"] for c in world["customers"]]
        assign(world, dict.fromkeys(ids, "T3"))
        drain(world, 42)
        rows = {row["customer_id"]: row for row in treatment.potential_outcomes(world, ids)}
        now = world["now_ms"]
        p = params.active()
        changed = 0
        for index, cid in enumerate(ids):
            tid = ARMS[index % 4]
            customer = world["customers"][index]
            traits = world_state.behavior_traits(customer)
            changed += rows[cid]["response_type"][tid] != treatment.response_type(21, cid, traits, tid, p, 0)
            for arm in ARMS:
                copy = json.loads(json.dumps(customer))
                copy["assignments"].append([now, arm])
                self.assertEqual(rows[cid]["response_type"][arm], treatment.effect(engine._Window(world, None), copy, now)[1])
        # 노출 수를 무시한 구현이면 0 이다 — 이 검사가 실제로 n = 1 을 보고 있다는 증거.
        self.assertGreater(changed, 0)


class TestRepeatedAssignmentCounterfactualEqualsObserved(SimulatorCase):
    def test_assigned_arm_of_the_second_assignment_equals_what_was_observed(self) -> None:
        root = self.start(seed=11, customers=80, profile="small")
        api.advance(40)
        api.apply_treatment({f"C{i:08d}": "T3" for i in range(1, 81)})
        api.advance(42)
        second = api.advance(0).end
        api.apply_treatment({f"C{i:08d}": (("T0",) + ARMS)[i % 5] for i in range(1, 81)})
        api.advance(42)
        start = second.isoformat(timespec="milliseconds")
        observed: dict[str, list[int]] = defaultdict(list)
        for record in sk.read_events(root):
            if record["event_type"] == "purchase" and str(record["timestamp"]) >= start:
                observed[str(record["customer_id"])].append(int(record["order_amount"]))
        files = sorted((self.hidden / "ground_truth").glob("po-*.jsonl"))
        self.assertEqual(2, len(files))
        rows = [
            row for path in files for row in map(json.loads, path.read_text(encoding="ascii").splitlines())
            if row["at"] == start
        ]
        self.assertEqual(80, len(rows))
        for row in rows:
            arm = row["outcomes"][row["assigned"]]
            with self.subTest(customer=row["customer_id"]):
                self.assertEqual(len(observed.get(row["customer_id"], [])), arm["orders"])
                self.assertEqual(sum(observed.get(row["customer_id"], [])), arm["revenue"])


class TestRepeatExposureConfigIsStrict(unittest.TestCase):
    def assert_rejected(self, edit, fragment: str) -> None:
        doc = config_document()
        edit(doc)
        with self.assertRaises(genconfig.ConfigError) as caught:
            genconfig.parse(json.dumps(doc, ensure_ascii=False))
        self.assertIn(fragment, str(caught.exception))

    def test_missing_block_is_rejected(self) -> None:
        self.assert_rejected(lambda d: d["behavior"]["treatment"].pop("repeat_exposure"), "repeat_exposure")

    def test_missing_or_extra_keys_are_rejected(self) -> None:
        self.assert_rejected(lambda d: repeat_block(d).pop("negative_step_pct"), "negative_step_pct")
        self.assert_rejected(lambda d: repeat_block(d).pop("note"), "note")
        self.assert_rejected(lambda d: repeat_block(d).__setitem__("lookback_days", 90), "lookback_days")

    def test_out_of_range_or_non_integer_values_are_rejected(self) -> None:
        scale = config_document()["behavior"]["treatment"]["negative_scale_pct"]
        self.assert_rejected(lambda d: repeat_block(d).__setitem__("negative_max_pct", scale - 1), "negative_max_pct")
        self.assert_rejected(lambda d: repeat_block(d).__setitem__("negative_max_pct", 101), "negative_max_pct")
        self.assert_rejected(lambda d: repeat_block(d).__setitem__("positive_decay_pct", 101), "positive_decay_pct")
        self.assert_rejected(lambda d: repeat_block(d).__setitem__("positive_floor_pct", -1), "positive_floor_pct")
        self.assert_rejected(lambda d: repeat_block(d).__setitem__("negative_step_pct", True), "negative_step_pct")
        self.assert_rejected(lambda d: repeat_block(d).__setitem__("note", ""), "note")


if __name__ == "__main__":
    unittest.main()
