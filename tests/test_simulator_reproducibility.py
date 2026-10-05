from __future__ import annotations

import hashlib
import unittest
from collections import defaultdict
from unittest import mock

from src.measurement import sink as sk
from src.simulator import api
from src.simulator._internal import behavior, rng
from tests.test_simulator_support import SimulatorCase, event_digest, root_digest

GOLDEN_SEED = 42
GOLDEN_CUSTOMERS = 50
GOLDEN_DAYS = 14
GOLDEN: dict[str, tuple[str, str, int]] = {
    "sim-0.1": (
        "fdfbc1e43a07ce603ab92a06b9fc4c0287e45d8be04f6d81f18adf7b7576cda1",
        "90cec765cabb841434760eb98b6a7881123061ac25765bab225edc9677ea7ed6",
        716,
    ),
}


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
