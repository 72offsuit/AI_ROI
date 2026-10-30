"""#183 ⑤ — 재구매 게이트 탈락자의 회복을 일반 이탈자와 분리한다.

- 게이트 탈락으로 시작한 이탈은 회복 hazard = recovery × gate_recovery_scale_pct // 100 (+ 처치 Positive 가산은 그대로).
- 회복하면 표시가 지워지고, 그 뒤로는 일반 고객과 같다.
- 0일차 고객·게이트 통과자의 이벤트는 배율과 무관하다. 배율 100 은 표시가 없는 엔진과 결정·이벤트가 같다.
- 표시는 숨은 상태다 — 상태 검증은 이름을 싣지 않고, 공개 출력에 나오지 않는다.
"""

from __future__ import annotations

import contextlib
import gzip
import json
import unittest
from collections import defaultdict
from unittest import mock

from src.measurement import sink as sk
from src.simulator import api
from src.simulator._internal import clock, engine, genconfig, params, rng, treatment
from src.simulator._internal import world as world_state
from tests.test_simulator_behavior import drain, recorded_gates
from tests.test_simulator_support import REPO_ROOT, SimulatorCase, event_digest

FLAG = "gate_churning"


def config_with_scale(scale: int) -> genconfig.GenerationConfig:
    doc = json.loads((REPO_ROOT / "config" / "simulator_config.yaml").read_text(encoding="utf-8"))
    doc["behavior"]["churn"]["gate_recovery_scale_pct"] = scale
    return genconfig.parse(json.dumps(doc, ensure_ascii=False))


@contextlib.contextmanager
def scale_of(scale: int):
    with mock.patch.object(genconfig, "_ACTIVE", config_with_scale(scale)):
        yield


def draw_counts(window) -> list[tuple[str, int]]:
    # DayDraws 에 공개 조회가 없어 내부 계수기를 읽는다(test_simulator_behavior.engine_view 와 같은 방식).
    return sorted((repr(key), stream._count) for key, stream in window.draws._streams.items())


class TestRecoveryHazard(unittest.TestCase):
    """하루 시작(`_day_start`)의 회복 판정을, 같은 자리의 난수 u 로 계산한 기대값과 대조한다."""

    SEED, CUSTOMERS, DAYS = 4, 300, 300
    # 회복 hazard 는 최대 recovery + arm.recovery_ppm(5,000 + 50,000 ppm) — 그보다 큰 u 는 어느 경우에도 회복하지 않는다.
    PROBE_PPM = 100_000

    @classmethod
    def setUpClass(cls) -> None:
        cls.world = world_state.new_world(cls.SEED, cls.CUSTOMERS, "small")
        cls.p = params.active()

    def run_day(self, customer, day: int, flag: bool, tid: str | None):
        day_ms = self.world["calendar_start_ms"] + day * clock.DAY_MS
        window = engine._Window({**self.world, "queue": []}, None)
        window.draws = rng.DayDraws(self.SEED, day)
        copy = json.loads(json.dumps(customer))
        copy.update(churning=True, engagement=params.PPM // 2, assignments=[[day_ms, tid]] if tid else [])
        copy[FLAG] = flag
        expected_response = treatment.effect(engine._Window(self.world, None), copy, day_ms)[1]
        engine._day_start(window, copy, day_ms)
        return copy, window, expected_response

    def test_gate_churn_recovers_at_the_scaled_hazard_and_clears_the_flag(self) -> None:
        scale = self.p.gate_recovery_scale_pct
        self.assertLess(scale, 100, "배율 100 config 로는 분리 여부를 볼 수 없다")
        between = 0
        for index, customer in enumerate(self.world["customers"]):
            first_day = max(0, -(-(customer["signup_ms"] - self.world["calendar_start_ms"]) // clock.DAY_MS))
            tid = "T3" if index % 2 else None
            for day in range(first_day, self.DAYS):
                u = rng.DayDraws(self.SEED, day).stream(customer["customer_id"], "day").next_u64()
                if u >= self.PROBE_PPM * (1 << 64) // params.PPM:
                    continue
                outcomes = {}
                for flag in (False, True):
                    after, window, response = self.run_day(customer, day, flag, tid)
                    hazard = self.p.recovery_ppm * (scale if flag else 100) // 100
                    if response == treatment.POSITIVE:
                        hazard += self.p.arms["T3"].recovery_ppm
                    recovered = engine._below_ppm(u, hazard)
                    with self.subTest(customer=customer["customer_id"], day=day, flag=flag):
                        self.assertEqual(not recovered, after["churning"])
                        self.assertEqual(flag and not recovered, after[FLAG])
                    outcomes[flag] = (recovered, draw_counts(window))
                if outcomes[False][0] == outcomes[True][0]:
                    # 회복 결과가 같으면 표시는 난수를 더 쓰거나 덜 쓰지 않는다(CRN). 결과가 다르면 engagement 가
                    # 달라 방문 여부와 방문 시각 난수 소비가 달라지는 것이 정상이다.
                    self.assertEqual(outcomes[False][1], outcomes[True][1])
                else:
                    between += 1
        # 일반 이탈자는 회복하고 탈락자는 회복하지 않는 u 가 실제로 있었다 — 위 검사가 배율 차이를 본 증거.
        self.assertGreater(between, 0)


class TestUnaffectedCustomers(unittest.TestCase):
    SEED, CUSTOMERS, DAYS = 5, 400, 300

    def run_world(self, scale: int) -> tuple[dict[str, str], dict[str, object], list[dict[str, object]]]:
        with scale_of(scale):
            world = world_state.new_world(self.SEED, self.CUSTOMERS, "small")
            calls: list[dict[str, object]] = []
            with recorded_gates(calls):
                records = drain(world, self.DAYS)
        by_customer: dict[str, list[dict[str, object]]] = defaultdict(list)
        for record in records:
            by_customer[str(record["customer_id"])].append(record)
        return {cid: event_digest(found) for cid, found in by_customer.items()}, world, calls

    def test_day_zero_customers_and_gate_passers_do_not_depend_on_the_scale(self) -> None:
        stalled, stalled_world, calls = self.run_world(0)
        normal, _, _ = self.run_world(100)
        start = stalled_world["calendar_start_ms"]
        # 배율 0 이면 처치가 없는 이 실행에서 탈락 이탈자는 회복하지 못하므로 끝까지 표시가 남는다.
        flagged = {c["customer_id"] for c in stalled_world["customers"] if c[FLAG]}
        gate_entered = {
            c["customer_id"] for c in calls if c["observed_signup"] and c["failed"] and not c["before"][0]
        }
        self.assertEqual(gate_entered, flagged)
        self.assertTrue(flagged)
        day_zero = {c["customer_id"] for c in stalled_world["customers"] if c["signup_ms"] <= start}
        self.assertFalse(day_zero & flagged)
        for cid in sorted(set(stalled) | set(normal)):
            if cid not in flagged:
                self.assertEqual(stalled.get(cid), normal.get(cid), cid)
        self.assertTrue(any(stalled.get(cid) != normal.get(cid) for cid in flagged))


class TestScaleHundredIsThePreviousBehavior(unittest.TestCase):
    """배율 100 이면 표시가 동작에 아무 영향이 없다 — 표시 도입 전 엔진과 결정·이벤트가 같다.

    도입 전 판(sim-0.5)의 GATE_GOLDEN 과 직접 대조하지 않는 이유: 같은 판 상향(sim-0.6)에서 구매 의향·onset 등 다른
    계수도 바뀌어 그 값은 더는 재현되지 않는다. 대신 같은 config 에서 "표시를 아예 켜지 않는 엔진"(게이트가 켠 표시를
    곧바로 지운다 — 도입 전 동작)과 배율 100 실행을 비교한다. 배율이 실제로 쓰이는지도 함께 확인한다.
    """

    SEED, CUSTOMERS, DAYS = 8, 300, 200

    def run_world(self, scale: int, *, without_flag: bool) -> tuple[dict[str, str], str]:
        original = engine._repurchase_gate

        def gate_without_flag(window, customer):
            original(window, customer)
            customer[FLAG] = False

        patch = (
            mock.patch.object(engine, "_repurchase_gate", gate_without_flag)
            if without_flag else contextlib.nullcontext()
        )
        with scale_of(scale), patch:
            world = world_state.new_world(self.SEED, self.CUSTOMERS, "small")
            calls: list[dict[str, object]] = []
            with recorded_gates(calls):
                records = drain(world, self.DAYS)
        decisions = {c["customer_id"]: "fail" if c["failed"] else "pass" for c in calls if c["observed_signup"]}
        return decisions, event_digest(records)

    def test_scale_100_equals_the_engine_without_the_flag(self) -> None:
        baseline = self.run_world(100, without_flag=True)
        self.assertIn("fail", baseline[0].values())
        self.assertEqual(baseline, self.run_world(100, without_flag=False))
        # 표시를 끈 엔진은 배율과 무관하고, 표시를 켠 엔진은 배율 0 에서 달라진다 — 위 비교가 빈 검사가 아니다.
        self.assertEqual(baseline, self.run_world(0, without_flag=True))
        self.assertNotEqual(baseline[1], self.run_world(0, without_flag=False)[1])


class TestFlagIsHiddenState(SimulatorCase):
    def setUp(self) -> None:
        super().setUp()
        self.world = world_state.new_world(5, 200, "small")
        drain(self.world, 200)

    def forged(self, edit) -> bytes:
        document = json.loads(world_state.encode(self.world))
        edit(document)
        return world_state.canonical_json(document)

    def test_round_trip_keeps_the_flag_and_new_customers_start_without_it(self) -> None:
        fresh = world_state.new_world(5, 200, "small")
        self.assertEqual({False}, {c[FLAG] for c in fresh["customers"]})
        self.assertIn(True, {c[FLAG] for c in self.world["customers"]})
        self.assertEqual(world_state.encode(self.world), world_state.encode(world_state.decode(world_state.encode(self.world))))

    def test_forged_flags_are_rejected_without_naming_the_field(self) -> None:
        plain = next(i for i, c in enumerate(self.world["customers"]) if not c["churning"])

        def set_flag(value):
            return lambda d: d["customers"][plain].__setitem__(FLAG, value)

        forgeries = {
            "not_bool": set_flag(1),
            "set_while_not_churning": set_flag(True),
            "missing": lambda d: d["customers"][plain].pop(FLAG),
        }
        for name, edit in forgeries.items():
            with self.subTest(name), self.assertRaises(ValueError) as caught:
                world_state.decode(self.forged(edit))
            self.assertNotIn(FLAG, str(caught.exception))

    def test_previous_state_format_is_rejected(self) -> None:
        # #198 이 sim-state-v5 로 올렸다. v3(이 표시가 없던 형식)와 v4(대기 리뷰가 없던 형식) 모두 거부된다.
        self.assertEqual("sim-state-v5", world_state.FORMAT_VERSION)
        for previous in ("sim-state-v3", "sim-state-v4"):
            with self.subTest(previous=previous), self.assertRaises(world_state.IncompatibleState):
                world_state.decode(self.forged(lambda d: d.__setitem__("format_version", previous)))

    def test_flag_never_reaches_the_public_output(self) -> None:
        root = self.start(seed=5, customers=200, profile="small")
        api.advance(200)
        api.save_state()
        self.assertFalse(any(FLAG in record for record in sk.read_events(root)))
        for path in sorted(root.rglob("*")):
            if path.is_file():
                data = gzip.decompress(path.read_bytes()) if path.suffix == ".gz" else path.read_bytes()
                self.assertNotIn(FLAG.encode(), data, str(path))


class TestGateRecoveryConfigIsStrict(unittest.TestCase):
    def test_missing_extra_and_out_of_range_values_are_rejected(self) -> None:
        def parse(edit) -> None:
            doc = json.loads((REPO_ROOT / "config" / "simulator_config.yaml").read_text(encoding="utf-8"))
            edit(doc["behavior"]["churn"])
            genconfig.parse(json.dumps(doc, ensure_ascii=False))

        for name, edit in {
            "missing": lambda c: c.pop("gate_recovery_scale_pct"),
            "extra": lambda c: c.__setitem__("gate_recovery_floor_ppm", 1),
            "above_100": lambda c: c.__setitem__("gate_recovery_scale_pct", 101),
            "negative": lambda c: c.__setitem__("gate_recovery_scale_pct", -1),
            "bool": lambda c: c.__setitem__("gate_recovery_scale_pct", True),
        }.items():
            with self.subTest(name), self.assertRaises(genconfig.ConfigError) as caught:
                parse(edit)
            self.assertIn("gate_recovery", str(caught.exception))


if __name__ == "__main__":
    unittest.main()
