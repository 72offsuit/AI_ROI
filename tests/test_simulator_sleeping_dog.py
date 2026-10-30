"""#196 — Sleeping Dog 직접 경로(DR-196).

- Negative 고객은 노출 순간 `negative_effect.onset_at_exposure_pct` 확률로 이탈 진행(onset)에 들어간다.
- 확률 0 이면 노출이 이탈 상태를 바꾸지 않는다. 경로가 발화하지 않으면 이벤트도 바뀌지 않는다(전용 스트림).
- Negative 가 아닌 고객 · `T0` 배정 · 이미 이탈 진행 중인 고객에게는 아무 일도 일어나지 않는다.
- 이 경로가 잠재결과 4분면의 Sleeping Dog 을 실제로 만든다.
"""

from __future__ import annotations

import copy
import json
import unittest
from unittest import mock

from src.simulator._internal import clock, engine, genconfig, params, treatment
from src.simulator._internal import world as world_state
from tests.test_simulator_support import REPO_ROOT, event_digest

SEED, CUSTOMERS, WARMUP = 7, 400, 60


def params_with(negative_scale_pct: int | None = None, **negative_effect: int) -> params.Params:
    doc = json.loads((REPO_ROOT / "config" / "simulator_config.yaml").read_text(encoding="utf-8"))
    doc["behavior"]["treatment"]["negative_effect"].update(negative_effect)
    if negative_scale_pct is not None:
        doc["behavior"]["treatment"]["negative_scale_pct"] = negative_scale_pct
    return params.Params(genconfig.parse(json.dumps(doc, ensure_ascii=False)))


def warmed_world() -> dict[str, object]:
    world = world_state.new_world(SEED, CUSTOMERS, "small")
    list(engine.run(world, world["now_ms"] + WARMUP * clock.DAY_MS))
    return world


def expose(world: dict[str, object], customer: dict[str, object], tid: str, p: params.Params) -> dict[str, object]:
    """고객 사본에 지금 시각 배정을 적고 노출 항목 하나를 처리한 뒤의 사본을 돌려준다."""
    now = world["now_ms"]
    found = copy.deepcopy(customer)
    found["assignments"].append([now, tid])
    window = engine._Window(world, None)
    window.params = p
    window.draws = engine.rng.DayDraws(world["seed"], (now - world["calendar_start_ms"]) // clock.DAY_MS)
    engine._treat(window, found, now, engine.next_seq(found))
    return found


class TestExposureOnset(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.world = warmed_world()
        cls.full = params_with(onset_at_exposure_pct=100)
        cls.off = params_with(onset_at_exposure_pct=0)
        window = engine._Window(cls.world, None)
        window.params = cls.full
        cls.kinds = {}
        for customer in cls.world["customers"]:
            probe = copy.deepcopy(customer)
            probe["assignments"].append([cls.world["now_ms"], "T3"])
            cls.kinds[customer["customer_id"]] = treatment.effect(window, probe, cls.world["now_ms"])[1]

    def active(self) -> list[dict[str, object]]:
        return [c for c in self.world["customers"]
                if c["lifecycle"] == "active" and c["signup_ms"] <= self.world["now_ms"]]

    def test_negative_customers_start_churning_at_exposure_and_no_one_else_does(self) -> None:
        negatives = 0
        for customer in self.active():
            after = expose(self.world, customer, "T3", self.full)
            cid = customer["customer_id"]
            with self.subTest(customer=cid, kind=self.kinds[cid], churning=customer["churning"]):
                if self.kinds[cid] == treatment.NEGATIVE and not customer["churning"]:
                    negatives += 1
                    self.assertTrue(after["churning"])
                    self.assertFalse(after["gate_churning"])
                    self.assertLessEqual(after["engagement"], customer["engagement"])
                else:
                    self.assertEqual(customer["churning"], after["churning"])
                    self.assertEqual(customer["engagement"], after["engagement"])
        self.assertGreater(negatives, 0)

    def test_exposure_before_signup_does_not_start_churning(self) -> None:
        pending = [c for c in self.world["customers"]
                   if c["signup_ms"] > self.world["now_ms"] and self.kinds[c["customer_id"]] == treatment.NEGATIVE]
        self.assertTrue(pending, "가입 전 Negative 고객이 있어야 이 검사가 의미 있다")
        for customer in pending:
            after = expose(self.world, customer, "T3", self.full)
            with self.subTest(customer=customer["customer_id"]):
                self.assertEqual(customer["churning"], after["churning"])
                self.assertEqual(customer["engagement"], after["engagement"])

    def test_zero_probability_and_t0_leave_the_state_alone(self) -> None:
        for customer in self.active():
            for tid, p in (("T3", self.off), ("T0", self.full)):
                after = expose(self.world, customer, tid, p)
                with self.subTest(customer=customer["customer_id"], tid=tid):
                    self.assertEqual(customer["churning"], after["churning"])
                    self.assertEqual(customer["engagement"], after["engagement"])


class TestPathIsInertUnlessItFires(unittest.TestCase):
    """경로는 Negative 고객의 노출에서만 작동한다. Negative 를 만들지 않으면(배율 0) 확률 0 과 100 의 이벤트가 같다 —
    경로가 발화하지 않을 때 다른 추첨·상태를 건드리지 않는다는 뜻이다. Negative 가 있으면 두 확률의 이벤트가 다르다."""

    def run_world(self, p: params.Params) -> str:
        world = warmed_world()
        now = world["now_ms"]
        for customer in world["customers"][:120]:
            customer["assignments"].append([now, ("T1", "T2", "T3", "T4")[int(customer["customer_id"][1:]) % 4]])
            world["queue"].append((now, customer["customer_id"], engine.next_seq(customer), "treat"))
        world["queue"].sort()
        with mock.patch.object(params, "active", return_value=p):
            return event_digest(engine.run(world, now + 42 * clock.DAY_MS))

    def test_without_negative_customers_the_probability_does_not_matter(self) -> None:
        self.assertEqual(
            self.run_world(params_with(negative_scale_pct=0, onset_at_exposure_pct=0)),
            self.run_world(params_with(negative_scale_pct=0, onset_at_exposure_pct=100)),
        )

    def test_with_negative_customers_the_path_changes_events(self) -> None:
        self.assertNotEqual(
            self.run_world(params_with(onset_at_exposure_pct=0)),
            self.run_world(params_with(onset_at_exposure_pct=100)),
        )


class TestPathCreatesSleepingDogs(unittest.TestCase):
    def test_counterfactual_rows_gain_sleeping_dogs_when_the_path_is_on(self) -> None:
        world = warmed_world()
        ids = [c["customer_id"] for c in world["customers"]
               if c["rfm"]["last_purchase_ms"] is not None][:200]

        def count(p: params.Params) -> int:
            with mock.patch.object(params, "active", return_value=p):
                rows = treatment.potential_outcomes(world, ids)
            return sum(1 for r in rows if r["outcomes"]["T0"]["purchased"] and not r["outcomes"]["T3"]["purchased"])

        self.assertGreater(count(params_with(onset_at_exposure_pct=100)), count(params_with(onset_at_exposure_pct=0)))
