from __future__ import annotations

import hashlib
import json
import unittest
from collections import defaultdict
from unittest import mock

from src.measurement import sink as sk
from src.simulator import api
from src.simulator._internal import behavior, rng
from src.simulator._internal import world as world_state
from tests.test_simulator_support import REPO_ROOT, SimulatorCase, event_digest, root_digest

GOLDEN_SEED = 42
GOLDEN_CUSTOMERS = 50
GOLDEN_DAYS = 14
# 판마다 (이벤트 다이제스트, 상태 sha256, 이벤트 수). 지난 판은 기록으로 남긴다 — BEHAVIOR_BASELINE 이 대조한다.
GOLDEN: dict[str, tuple[str, str, int]] = {
    "sim-0.1": (
        "fdfbc1e43a07ce603ab92a06b9fc4c0287e45d8be04f6d81f18adf7b7576cda1",
        "90cec765cabb841434760eb98b6a7881123061ac25765bab225edc9677ea7ed6",
        716,
    ),
    "sim-0.2": (
        "77d67f87b899980fdd8b85921b5896ec201641e3ecd23f7cdd159ddee70fb958",
        "047c9d783cc91c1465a93d229c0916aad1e727c3f2a444ae1032135d68e79e72",
        716,
    ),
    # S3: P6 가 Day 1~272 에 가입해 14일 창에서 그 고객들의 이벤트가 빠진다(DR-S3-p6-signup).
    "sim-0.3": (
        "dcd8a4e0038f5be0db3ba003f66ec69e52d83e2480ffa56b894425dca73e7145",
        "827c8bc47e8122ce3ccd257fd101047e1a9c2595603375a949761a80966186b1",
        692,
    ),
    # S4~S6(#143): Trait 이 방문·퍼널·이탈을 구동하고 구매·카탈로그(240개)가 생겨 이벤트가 바뀐다(DR-143-sim-sprint).
    "sim-0.4": (
        "ed5073799331a49d0d704b8ea0aa9a0c0291486d10d9adb793a2dda34314c888",
        "c2fd38f7738b3b737645b7a6b11a65b21b346ec6bea7737396a8862db3ebfc1b",
        1160,
    ),
    # #183: 관측 중 가입 고객의 첫 구매 뒤 재구매 게이트. 이 14일 창에서는 게이트가 이벤트를 바꾸지 않아
    # 판 라벨만 다르다(라벨을 sim-0.4 로 되돌리면 sim-0.4 다이제스트와 같다). 그래도 행동을 바꾼 판이라
    # BEHAVIOR_BASELINE 에 넣지 않는다 — 게이트가 발화하는 실행의 정확한 값은 tests/test_simulator_behavior.py 의
    # GATE_GOLDEN(TestRepurchaseGateKeepsSplitInvariance.test_gate_decisions_and_digests_match_the_pinned_values_of_this_version)
    # 이 같은 판 키로 고정한다.
    "sim-0.5": (
        "182e880d5c295aabe97e83f56da83411a4b55b258143c1677669191b1342c210",
        "d0cbfc345a5efa2707e1de03593e1c4359336da752ded1c46ebb91e38bcfe255",
        1160,
    ),
    # #183(sim-gen-v4): 구매 의향 보정으로 이 14일 창의 이벤트가 sim-0.5 와 달라진다. 이탈 onset·쿠폰 받기는 이 창의 이벤트를
    # 바꾸지 않고 상태에 든 config 다이제스트(상태 sha)로만 드러난다 — onset 은 GATE_GOLDEN(test_simulator_behavior.py)이,
    # 쿠폰 받기는 CONFIG_PINS 가 고정한다. 반복 노출 감쇠·게이트 탈락 회복 분리는 이 창에서 발화하지 않는다(각각
    # tests/test_simulator_fatigue.py · test_simulator_gate_recovery.py).
    "sim-0.6": (
        "6d96c7def2a4818963165c1f20d3e8ebbc44b7e0003d1316f69871d93d24f6ed",
        "65e275c9ae40f5bbe23a3149e04ea74a41e89876bb09193d7aab07136149ce3f",
        1213,
    ),
    # #196(sim-gen-v5): Sleeping Dog 직접 경로는 처치 노출 때만 발화한다. 이 14일 창에는 처치가 없어 판 라벨과
    # 생성 다이제스트(상태)만 다르다. 경로 자체는 tests/test_simulator_sleeping_dog.py 가 고정한다.
    "sim-0.7": (
        "b8199d8a01c7c5bd1b47a93a1b77808d2cd5c3631f08f3a7d155690c0940fe15",
        "27e4c11d8b7885275c9c24fa1b106e472f3809f939cab9e5fd4c858896a87f13",
        1213,
    ),
    # #198(sim-gen-v6): 부수 이벤트 4종이 더해진다. 배율을 0 으로 두면 sim-0.7 과 같다
    # (TestAuxEventsLeaveEarlierBehaviorUnchanged).
    "sim-0.8": (
        "2ec052af891d27d975aa5b76203299673ff4348d3d0eadc9842d668a86662c3f",
        "a85b1319ed11ad0e02c63a4d6441c15c6cacf8e3a97059dd48051786789cd9cf",
        1342,
    ),
    # #282(sim-gen-v7): T3 처치 반응 계수 재보정. 이 14일 창에는 처치가 없어 판 라벨과 생성 다이제스트(상태)만
    # 다르다(라벨을 sim-0.8 로 되돌리면 이벤트 다이제스트가 sim-0.8 과 같다 — 상태 sha 는 v7 생성 다이제스트가 들어 있어 여전히 다르다).
    # 처치 반응을 바꾼 판이라 BEHAVIOR_BASELINE 에 넣지 않는다.
    "sim-0.9": (
        "0623c275998dacce34078ddae7f866cd4c41625c04fc54d4afcd720a24608bb4",
        "cc67d63692a8b6fba9ff672d935c9abe83f713f59b6982727082d3ec17f1969a",
        1342,
    ),
}
# 행동은 그대로이고 판 라벨만 바뀐 판 → 행동 기준 판. S2 는 생성(페르소나·Trait)만 더하고 이벤트 규칙을
# 건드리지 않는다(사용자 확정 U1·U4). sim-0.3(S3)은 가입일을 바꿔 행동이 바뀐 판이라 항목이 없다.
BEHAVIOR_BASELINE: dict[str, str] = {"sim-0.2": "sim-0.1"}
# seed 42 · 50명의 [customer_id, persona, hidden_traits] 정준 JSON sha256. 이벤트와 무관한 생성 결과의 고정점이다.
GENERATION_GOLDEN = "c9c991a24689051c08a739b06fe5701a0dd435a44f25ce45d1c390b572dae762"


def _by_customer(records) -> dict[str, str]:
    grouped: dict[str, list[dict[str, object]]] = defaultdict(list)
    for record in records:
        grouped[str(record["customer_id"])].append(record)
    return {cid: event_digest(rows) for cid, rows in grouped.items()}


class TestSameSeedSameBytes(SimulatorCase):
    def run_world(self, seed: int) -> tuple[str, str]:
        root = self.start(seed=seed, customers=25)
        api.advance(20)
        return root_digest(root), api.save_state()

    def test_same_seed_twice_gives_identical_event_digest_and_state(self) -> None:
        first = self.run_world(11)
        second = self.run_world(11)
        self.assertEqual(first, second)

    def test_different_seed_gives_different_events(self) -> None:
        self.assertNotEqual(self.run_world(11)[0], self.run_world(12)[0])


class TestSplitInvariance(SimulatorCase):
    TOTAL = 45

    def continuous(self) -> tuple[str, str]:
        root = self.start(customers=25)
        api.advance(self.TOTAL)
        return root_digest(root), api.save_state()

    def split(self, parts: tuple[int, ...]) -> tuple[str, str]:
        root = self.start(customers=25)
        for days in parts:
            api.advance(days)
        return root_digest(root), api.save_state()

    def test_any_split_matches_one_advance(self) -> None:
        expected = self.continuous()
        for parts in ((1, 44), (7, 38), (17, 28), (30, 15), (44, 1), (5, 0, 13, 27), (9, 9, 9, 9, 9)):
            with self.subTest(parts=parts):
                self.assertEqual(expected, self.split(parts))

    def test_advance_zero_writes_no_run(self) -> None:
        root = self.start()
        summary = api.advance(0)
        self.assertIsNone(summary.run_id)
        self.assertEqual(0, summary.event_count)
        self.assertEqual(summary.start, summary.end)
        self.assertFalse(root.exists())


class TestSnapshotRestoreMatchesContinuous(SimulatorCase):
    def test_restore_then_advance_equals_continuous_run(self) -> None:
        reference_root = self.start(customers=25)
        api.advance(60)
        reference_digest = root_digest(reference_root)
        reference_state = api.save_state()
        reference_events = list(sk.read_events(reference_root))
        cut = "2025-01-31T00:00:00.000+09:00"
        reference_tail = [r for r in reference_events if str(r["timestamp"]) >= cut]

        root_a = self.start(customers=25)
        api.advance(30)
        snap = api.snapshot()
        api.advance(30)
        self.assertEqual(reference_digest, root_digest(root_a))
        self.assertEqual(reference_state, api.save_state())

        root_b = self.fresh_root("branch")
        api.restore(snap, output_root=root_b)
        summary = api.advance(30)
        self.assertEqual(reference_state, api.save_state())
        self.assertEqual(event_digest(reference_tail), root_digest(root_b))
        self.assertEqual(reference_digest, event_digest(api.events(summary.end)))

    def test_same_token_restores_twice_to_identical_branches(self) -> None:
        self.start(customers=20)
        api.advance(10)
        snap = api.snapshot()
        digests = []
        for _ in range(2):
            root = self.fresh_root("branch")
            api.restore(snap, output_root=root)
            api.advance(15)
            digests.append((root_digest(root), api.save_state()))
        self.assertEqual(digests[0], digests[1])


class TestSaveLoadMatchesContinuous(SimulatorCase):
    def setUp(self) -> None:
        super().setUp()
        root = self.start(customers=25)
        api.advance(60)
        self.reference_digest = root_digest(root)
        self.reference_state = api.save_state()
        self.reference_bytes = self.state_bytes(self.reference_state)

    def test_save_load_resume_in_same_root_is_byte_identical(self) -> None:
        root = self.start(customers=25)
        api.advance(30)
        middle = api.save_state()
        self.start(seed=999, customers=3)
        api.load_state(middle, root, hidden_root=self.hidden)
        summary = api.advance(30)
        self.assertEqual(self.reference_digest, root_digest(root))
        self.assertEqual(self.reference_digest, event_digest(api.events(summary.end)))
        final = api.save_state()
        self.assertEqual(self.reference_state, final)
        self.assertEqual(self.reference_bytes, self.state_bytes(final))

    def test_load_into_new_root_continues_the_same_world(self) -> None:
        self.start(customers=25)
        api.advance(30)
        middle = api.save_state()
        fresh = self.fresh_root("resumed")
        api.load_state(middle, fresh, hidden_root=self.hidden)
        summary = api.advance(30)
        self.assertEqual(self.reference_state, api.save_state())
        self.assertEqual(self.reference_digest, event_digest(api.events(summary.end)))


class TestCustomerStreamsAreIndependent(SimulatorCase):
    TARGET = "C00000004"

    def per_customer(self, customers: int = 20, days: int = 40) -> dict[str, str]:
        root = self.start(customers=customers)
        api.advance(days)
        return _by_customer(sk.read_events(root))

    def test_changing_one_customer_parameter_leaves_others_unchanged(self) -> None:
        baseline = self.per_customer()
        original = behavior.visit_probability

        def boosted(customer_id: str) -> tuple[int, int]:
            return (9, 10) if customer_id == self.TARGET else original(customer_id)

        with mock.patch("src.simulator._internal.behavior.visit_probability", boosted):
            changed = self.per_customer()
        self.assertNotEqual(baseline.get(self.TARGET), changed.get(self.TARGET))
        others = {cid: d for cid, d in baseline.items() if cid != self.TARGET}
        self.assertEqual(others, {cid: d for cid, d in changed.items() if cid != self.TARGET})

    def test_adding_a_customer_leaves_existing_customers_unchanged(self) -> None:
        small = self.per_customer(customers=15)
        large = self.per_customer(customers=16)
        self.assertEqual(small, {cid: d for cid, d in large.items() if cid in small})


class TestGoldenHash(SimulatorCase):
    def test_canonical_run_matches_pinned_digests_on_every_python(self) -> None:
        root = self.start(seed=GOLDEN_SEED, customers=GOLDEN_CUSTOMERS, profile="smoke")
        summary = api.advance(GOLDEN_DAYS)
        state_id = api.save_state()
        version = self.state(state_id)["simulator_version"]
        self.assertEqual({version}, {r["simulator_version"] for r in sk.read_events(root)})
        self.assertIn(version, GOLDEN, f"{version} 의 골든 값이 없다 — 생성 규칙을 바꾸면 판과 상수를 함께 올린다")
        event_sha, state_sha, count = GOLDEN[version]
        self.assertEqual(count, summary.event_count)
        self.assertEqual(event_sha, root_digest(root))
        self.assertEqual(state_sha, hashlib.sha256(self.state_bytes(state_id)).hexdigest())
        self.assertEqual("state-" + state_sha[:16], state_id)


class TestBehaviorUnchangedSinceBaseline(SimulatorCase):
    def test_relabeled_events_match_the_baseline_golden(self) -> None:
        version = world_state.SIMULATOR_VERSION
        if version not in BEHAVIOR_BASELINE:
            self.skipTest(f"{version} 은 행동 기준 판이 없다 — 행동을 바꾼 판이다")
        baseline = BEHAVIOR_BASELINE[version]
        root = self.start(seed=GOLDEN_SEED, customers=GOLDEN_CUSTOMERS, profile="smoke")
        api.advance(GOLDEN_DAYS)
        relabeled = [{**r, "simulator_version": baseline} for r in sk.read_events(root)]
        event_sha, _, count = GOLDEN[baseline]
        self.assertEqual(count, len(relabeled))
        self.assertEqual(event_sha, event_digest(relabeled))


class TestAuxEventsLeaveEarlierBehaviorUnchanged(SimulatorCase):
    """#198 은 기존 12종의 추첨 자리를 밀지 않는다 — 부수 이벤트는 전용 스트림에서만 뽑는다.

    부수 이벤트 배율을 0 으로 둔 실험 config 로 돌리고 return_visit 을 session_start 로, 판 라벨을 sim-0.7 로
    되돌리면 sim-0.7 골든 이벤트와 바이트까지 같아야 한다. 새 이벤트가 하나도 나지 않아 고객별 seq·event_id 도
    그대로다. 판을 올릴 때 이 시험의 기준 판은 #198 직전 판으로 둔다.
    """

    BASELINE = "sim-0.7"

    def test_zero_scales_and_relabeled_openers_match_the_previous_golden(self) -> None:
        document = json.loads((REPO_ROOT / "config" / "simulator_config.yaml").read_text(encoding="utf-8"))
        aux = document["behavior"]["aux_events"]
        for key in ("search_scale_pct", "review_scale_pct", "cs_scale_pct"):
            aux[key] = 0
        config = self.fresh_root("config") / "aux-off.yaml"
        config.parent.mkdir(parents=True, exist_ok=True)
        config.write_text(json.dumps(document), encoding="utf-8")
        root = self.fresh_root("out")
        api.init(GOLDEN_SEED, GOLDEN_CUSTOMERS, "smoke", root, hidden_root=self.hidden, config_path=config)
        api.advance(GOLDEN_DAYS)
        records = list(sk.read_events(root))
        self.assertTrue(any(r["event_type"] == "return_visit" for r in records), "되돌릴 return_visit 이 없다")
        relabeled = [
            {
                **r,
                "event_type": "session_start" if r["event_type"] == "return_visit" else r["event_type"],
                "simulator_version": self.BASELINE,
            }
            for r in records
        ]
        event_sha, _, count = GOLDEN[self.BASELINE]
        self.assertEqual(count, len(relabeled))
        self.assertEqual(event_sha, event_digest(relabeled))


class TestAuxEventsDoNotShiftExistingEventsAtFullScale(SimulatorCase):
    """배율 0 비교(위)는 "배율이 0 보다 클 때만 공유 스트림에서 뽑는" 회귀를 잡지 못한다.

    기본 배율(100)과 배율 0 으로 처치까지 건 같은 세계를 돌려, 부수 이벤트를 걷어낸 투영이 같은지 본다. 걷어낼 때
    `return_visit` 은 `session_start` 로 되돌리고, 새 이벤트 때문에 달라지는 `event_id`(고객별 seq)와
    `session_duration`(세션의 마지막 이벤트에 실린다)은 비교에서 뺀다.
    """

    AUX = frozenset({"search", "review", "cs_contact"})
    CUSTOMERS = 60

    def run_projection(self, config) -> list[dict[str, object]]:
        root = self.fresh_root("out")
        api.init(11, self.CUSTOMERS, "small", root, hidden_root=self.fresh_root("hidden"), config_path=config)
        api.advance(60)
        arms = ("T0", "T1", "T2", "T3", "T4")
        api.apply_treatment({f"C{i:08d}": arms[i % 5] for i in range(1, self.CUSTOMERS + 1)})
        api.advance(42)
        projected = []
        for record in sk.read_events(root):
            if record["event_type"] in self.AUX:
                continue
            row = {k: v for k, v in record.items() if k not in ("event_id", "session_duration")}
            if row["event_type"] == "return_visit":
                row["event_type"] = "session_start"
            projected.append(row)
        return projected

    def test_existing_events_are_identical_with_and_without_aux_events(self) -> None:
        document = json.loads((REPO_ROOT / "config" / "simulator_config.yaml").read_text(encoding="utf-8"))
        full = self.fresh_root("config") / "aux-full.yaml"
        full.parent.mkdir(parents=True, exist_ok=True)
        full.write_text(json.dumps(document), encoding="utf-8")
        for key in ("search_scale_pct", "review_scale_pct", "cs_scale_pct"):
            document["behavior"]["aux_events"][key] = 0
        off = full.parent / "aux-off.yaml"
        off.write_text(json.dumps(document), encoding="utf-8")
        with_aux = self.run_projection(full)
        self.assertTrue(any(r["event_type"] == "coupon_use" for r in with_aux), "처치 반응이 이 창에 없다")
        self.assertEqual(self.run_projection(off), with_aux)


class TestGenerationGolden(unittest.TestCase):
    def test_identity_of_the_canonical_population_is_pinned(self) -> None:
        world = world_state.new_world(GOLDEN_SEED, GOLDEN_CUSTOMERS, "smoke")
        rows = [[c["customer_id"], c["persona"], c["hidden_traits"]] for c in world["customers"]]
        self.assertEqual(GENERATION_GOLDEN, hashlib.sha256(rng.canonical_json(rows)).hexdigest())


class TestCounterDraws(unittest.TestCase):
    def test_uniform_integer_draws_pass_chi_square(self) -> None:
        stream = rng.Stream(1, "C00000001", "uniformity", 0)
        draws, buckets = 100_000, 10
        counts = [0] * buckets
        for _ in range(draws):
            counts[stream.below(buckets)] += 1
        expected = draws // buckets
        chi2_scaled = 0
        for count in counts:
            chi2_scaled += (count - expected) ** 2
        self.assertLess(chi2_scaled, 2788 * expected // 100, counts)

    def test_bernoulli_extremes_are_exact(self) -> None:
        stream = rng.Stream(1, "C00000001", "edges", 0)
        self.assertFalse(any(stream.bernoulli(0, 7) for _ in range(1000)))
        self.assertTrue(all(stream.bernoulli(7, 7) for _ in range(1000)))

    def test_event_id_is_uuid4_shaped_and_deterministic(self) -> None:
        first = rng.event_id(42, "C00000001", 0)
        self.assertEqual(first, rng.event_id(42, "C00000001", 0))
        self.assertNotEqual(first, rng.event_id(42, "C00000001", 1))
        self.assertEqual("4", first[14])
        self.assertIn(first[19], "89ab")


if __name__ == "__main__":
    unittest.main()
