from __future__ import annotations

import hashlib
import heapq
import json
import unittest
from collections import defaultdict
from unittest import mock
from datetime import datetime, timedelta, timezone

from src.measurement import sink as sk
from src.simulator import api
from src.simulator._internal import cart, engine, genconfig, traits
from src.simulator._internal import world as world_state
from tests.test_simulator_support import SimulatorCase

DAY_MS = 86_400_000
LIFETIME_MS = 30 * DAY_MS


def _canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("ascii")


def _ms(timestamp: str) -> int:
    date_part, time_part = timestamp[:10], timestamp[11:23]
    year, month, day = (int(x) for x in date_part.split("-"))
    hours, minutes, rest = time_part.split(":")
    seconds, millis = rest.split(".")
    moment = datetime(
        year, month, day, int(hours), int(minutes), int(seconds),
        tzinfo=timezone(timedelta(hours=9)),
    )
    epoch = datetime(1970, 1, 1, tzinfo=timezone.utc)
    return (moment - epoch) // timedelta(milliseconds=1) + int(millis)


class TestStateVersionGate(SimulatorCase):
    def setUp(self) -> None:
        super().setUp()
        self.start(customers=10)
        api.advance(5)
        self.state_id = api.save_state()
        self.document = self.state(self.state_id)

    def plant(self, document: dict[str, object], *, raw: bytes | None = None) -> str:
        data = raw if raw is not None else _canonical(document)
        state_id = "state-" + hashlib.sha256(data).hexdigest()[:16]
        (self.hidden / "states" / f"{state_id}.json").write_bytes(data)
        return state_id

    def test_each_version_field_mismatch_is_rejected(self) -> None:
        for field in ("format_version", "rng_scheme", "simulator_version"):
            with self.subTest(field=field):
                forged = self.plant({**self.document, field: self.document[field] + "-other"})
                with self.assertRaisesRegex(api.StateFormatError, field):
                    api.load_state(forged, self.fresh_root("load"), hidden_root=self.hidden)

    def test_forged_structure_with_recomputed_digest_is_rejected(self) -> None:
        def customer(edit):
            def apply(document):
                edit(document["customers"][0])
            return apply

        forgeries = {
            "now_ms_as_string": lambda d: d.__setitem__("now_ms", str(d["now_ms"])),
            "num_customers_negative": lambda d: d.__setitem__("num_customers", -1),
            "unknown_top_key": lambda d: d.__setitem__("unknown_extra", 1),
            "missing_queue": lambda d: d.pop("queue"),
            "seed_as_bool": lambda d: d.__setitem__("seed", True),
            "seed_changed": lambda d: d.__setitem__("seed", d["seed"] + 1),
            "now_not_midnight": lambda d: d.__setitem__("now_ms", d["now_ms"] + 1),
            "customer_unknown_key": customer(lambda c: c.__setitem__("segment", "x")),
            "customer_missing_key": customer(lambda c: c.pop("next_seq")),
            "next_seq_bool": customer(lambda c: c.__setitem__("next_seq", True)),
            "cart_quantity_zero": customer(lambda c: c.__setitem__(
                "cart", {"P0001": {"quantity": 0, "last_change_ms": 0, "unit_price": 1}})),
            "cart_unknown_product": customer(lambda c: c.__setitem__(
                "cart", {"P9999": {"quantity": 1, "last_change_ms": 0, "unit_price": 1}})),
            "hidden_trait_planted": customer(lambda c: c.__setitem__("hidden_traits", {"tau": 1})),
            "assignment_bad_treatment": customer(lambda c: c.__setitem__("assignments", [[0, "T9"]])),
            "queue_unknown_customer": lambda d: d.__setitem__(
                "queue", [[d["now_ms"], "C99999999", 0, "visit"]]),
            "queue_unknown_kind": lambda d: d.__setitem__("queue", [[d["now_ms"], "C00000001", 0, "x"]]),
            "orders_planted": lambda d: d.__setitem__("orders", [{"order_id": "O00000001-000001"}]),
        }
        for name, edit in forgeries.items():
            with self.subTest(forgery=name):
                document = json.loads(self.state_bytes(self.state_id))
                edit(document)
                forged = self.plant(document)
                with self.assertRaises(api.StateFormatError):
                    api.load_state(forged, self.fresh_root("load"), hidden_root=self.hidden)

    def test_forged_identity_with_recomputed_digest_is_rejected(self) -> None:
        config = genconfig.active()
        target = self.document["customers"][0]
        name = config.trait_names[0]
        table = traits.tables(config)[name][target["persona"]]

        def trait(edit):
            def apply(document):
                edit(document["customers"][0]["hidden_traits"])
            return apply

        forgeries = {
            "persona_unknown": lambda d: d["customers"][0].__setitem__("persona", "ghost"),
            "persona_alias_instead_of_id": lambda d: d["customers"][0].__setitem__("persona", "P1"),
            "persona_not_a_string": lambda d: d["customers"][0].__setitem__("persona", 1),
            "trait_missing": trait(lambda t: t.pop(name)),
            "trait_extra": trait(lambda t: t.__setitem__("tau", 1)),
            "trait_bool": trait(lambda t: t.__setitem__(name, True)),
            "trait_float": trait(lambda t: t.__setitem__(name, 0.5)),
            "trait_string": trait(lambda t: t.__setitem__(name, "1")),
            "trait_below_range": trait(lambda t: t.__setitem__(name, table.lo - 1)),
            "trait_above_range": trait(lambda t: t.__setitem__(name, table.hi + 1)),
            "traits_not_an_object": lambda d: d["customers"][0].__setitem__("hidden_traits", []),
            "generation_missing": lambda d: d.pop("generation"),
            "generation_other_digest": lambda d: d["generation"].__setitem__("config_digest", "0" * 64),
            "generation_other_version": lambda d: d["generation"].__setitem__("config_version", "x"),
            "generation_extra_key": lambda d: d["generation"].__setitem__("extra", 1),
        }
        for label, edit in forgeries.items():
            with self.subTest(forgery=label):
                document = json.loads(self.state_bytes(self.state_id))
                edit(document)
                forged = self.plant(document)
                with self.assertRaises(api.StateFormatError) as caught:
                    api.load_state(forged, self.fresh_root("load"), hidden_root=self.hidden)
                # 오류 메시지는 위치와 사유만 말한다 — 숨은 값(페르소나 id·Trait 값)을 싣지 않는다.
                message = str(caught.exception)
                self.assertNotIn(f"'{target['persona']}'", message)
                self.assertNotIn(str(target["hidden_traits"][name]), message)
        with self.subTest(forgery="generation"):
            document = json.loads(self.state_bytes(self.state_id))
            document["generation"]["config_digest"] = "0" * 64
            with self.assertRaisesRegex(api.StateFormatError, "generation"):
                api.load_state(self.plant(document), self.fresh_root("load"), hidden_root=self.hidden)

    def test_in_range_trait_change_is_caught_by_the_lineage(self) -> None:
        # 구조 검사는 Trait 을 다시 생성하지 않으므로 범위 안의 위조는 통과한다. 이어받을 계보의
        # 다이제스트 사슬(초기 상태 = 같은 seed 로 새로 만든 세계)이 그 위조를 잡는다.
        config = genconfig.active()
        document = json.loads(self.state_bytes(self.state_id))
        customer = document["customers"][0]
        name = config.trait_names[-1]
        table = traits.tables(config)[name][customer["persona"]]
        value = customer["hidden_traits"][name]
        customer["hidden_traits"][name] = value + 1 if value < table.hi else value - 1
        forged = self.plant(document)
        with self.assertRaises(api.OutputRootError):
            api.load_state(forged, self.fresh_root("load"), hidden_root=self.hidden)

    def test_unchanged_state_loads(self) -> None:
        api.load_state(self.state_id, self.fresh_root("load"), hidden_root=self.hidden)

    def test_tampered_bytes_under_the_old_id_are_rejected(self) -> None:
        path = self.hidden / "states" / f"{self.state_id}.json"
        path.write_bytes(_canonical({**self.document, "now_ms": self.document["now_ms"] + 1}))
        with self.assertRaises(api.StateFormatError):
            api.load_state(self.state_id, self.fresh_root("load"), hidden_root=self.hidden)

    def test_non_canonical_bytes_are_rejected(self) -> None:
        pretty = json.dumps(self.document, indent=2, sort_keys=True).encode("ascii")
        forged = self.plant(self.document, raw=pretty)
        with self.assertRaises(api.StateFormatError):
            api.load_state(forged, self.fresh_root("load"), hidden_root=self.hidden)

    def test_missing_state_is_rejected(self) -> None:
        with self.assertRaises(api.StateFormatError):
            api.load_state("state-0000000000000000", self.fresh_root("load"), hidden_root=self.hidden)

    def test_python_runtime_is_recorded_but_never_rejected(self) -> None:
        self.assertNotIn("runtime", self.document)
        self.assertNotIn("python", json.dumps(self.document).lower())
        root = self.start(customers=10)
        summary = api.advance(5)
        saved = api.save_state()
        record = self.sidecar(summary.run_id)
        self.assertEqual({"implementation", "version", "platform"}, set(record["runtime"]))
        record["runtime"]["version"] = "3.99.0"
        record["runtime"]["implementation"] = "OtherPython"
        (self.hidden / "runs" / f"{summary.run_id}.json").write_bytes(_canonical(record))
        api.load_state(saved, root, hidden_root=self.hidden)
        api.advance(1)

    def test_state_is_canonical_ascii_json_without_floats(self) -> None:
        data = self.state_bytes(self.state_id)
        self.assertEqual(_canonical(json.loads(data)), data)

        def walk(value: object) -> None:
            self.assertNotIsInstance(value, float)
            if isinstance(value, dict):
                for item in value.values():
                    walk(item)
            elif isinstance(value, list):
                for item in value:
                    walk(item)

        walk(self.document)

    def test_encoding_does_not_depend_on_heap_layout(self) -> None:
        items = [(5, "C00000002", 1, "action"), (1, "C00000001", 0, "visit"),
                 (3, "C00000003", 4, "visit"), (2, "C00000001", 1, "action")]
        base = world_state.new_world(1, 3, "smoke")
        pushed: list[tuple[int, str, int, str]] = []
        for item in items:
            heapq.heappush(pushed, item)
        reversed_push: list[tuple[int, str, int, str]] = []
        for item in reversed(items):
            heapq.heappush(reversed_push, item)
        self.assertNotEqual(pushed, reversed_push)
        self.assertEqual(
            world_state.encode({**base, "queue": pushed}),
            world_state.encode({**base, "queue": reversed_push}),
        )

    def test_saving_twice_gives_the_same_content_addressed_id(self) -> None:
        self.assertEqual(self.state_id, api.save_state())
        files = sorted((self.hidden / "states").iterdir())
        self.assertEqual([f"{self.state_id}.json"], [p.name for p in files])


class TestLineage(SimulatorCase):
    def test_parent_chain_crosses_roots_and_every_root_verifies(self) -> None:
        main = self.start(customers=12)
        first = api.advance(10)
        second = api.advance(10)
        state_id = api.save_state()
        snap = api.snapshot()
        branch = self.fresh_root("branch")
        api.restore(snap, output_root=branch)
        branched = api.advance(5)
        api.load_state(state_id, main, hidden_root=self.hidden)
        resumed = api.advance(5)

        records = {s.run_id: self.sidecar(s.run_id) for s in (first, second, branched, resumed)}
        self.assertIsNone(records[first.run_id]["parent_run_id"])
        self.assertEqual(first.run_id, records[second.run_id]["parent_run_id"])
        self.assertEqual(second.run_id, records[branched.run_id]["parent_run_id"])
        self.assertEqual(second.run_id, records[resumed.run_id]["parent_run_id"])
        for record in records.values():
            parent = record["parent_run_id"]
            if parent is not None:
                self.assertEqual(records[parent]["end_state_digest"], record["start_state_digest"])
            self.assertEqual(
                {"run_id", "parent_run_id", "output_root", "window", "mutations",
                 "start_state_digest", "end_state_digest", "world_id", "simulator_version",
                 "seed", "num_customers", "profile", "sink_format", "event_count", "files",
                 "sha256", "rows", "runtime"},
                set(record),
            )
        self.assertEqual(str(branch.resolve()), records[branched.run_id]["output_root"])
        self.assertEqual(
            {"from_ms", "to_ms", "from", "to"}, set(records[resumed.run_id]["window"])
        )

        for root in (main, branch):
            with self.subTest(root=root.name):
                self.assertEqual("ok", sk.verify_lineage(root).verification)
        sink_runs = {r["run_id"]: r for r in sk.run_records(main)}
        self.assertEqual(second.run_id, sink_runs[resumed.run_id]["parent_run_id"])
        self.assertEqual(
            [None], [r["parent_run_id"] for r in sk.run_records(branch)],
            "Sink 에 다른 루트의 부모를 넘기지 않는다",
        )

    def test_events_fail_when_an_ancestor_root_disappears(self) -> None:
        main = self.start(customers=5)
        api.advance(3)
        snap = api.snapshot()
        api.restore(snap, output_root=self.fresh_root("branch"))
        summary = api.advance(2)
        (main / sk.RUNS_DIR_NAME).rename(main / "runs-moved")
        with self.assertRaises(api.OutputRootError):
            api.events(summary.end)


class TestOutputRoots(SimulatorCase):
    def test_restore_refuses_a_written_root_and_accepts_an_empty_one(self) -> None:
        root = self.start(customers=8)
        api.advance(3)
        snap = api.snapshot()
        api.advance(3)
        with self.assertRaises(api.OutputRootError):
            api.restore(snap, output_root=root)
        occupied = self.fresh_root("occupied")
        occupied.mkdir()
        (occupied / "something").write_text("x", encoding="utf-8")
        with self.assertRaises(api.OutputRootError):
            api.restore(snap, output_root=occupied)
        empty_dir = self.fresh_root("empty")
        empty_dir.mkdir()
        api.restore(snap, output_root=empty_dir)
        summary = api.advance(3)
        self.assertGreater(summary.event_count, 0)
        api.restore(snap, output_root=self.fresh_root("missing"))

    def test_init_refuses_a_non_empty_root(self) -> None:
        root = self.start(customers=5)
        api.advance(1)
        with self.assertRaises(api.OutputRootError):
            api.init(1, 5, "smoke", root, hidden_root=self.hidden)

    def test_advance_refuses_after_a_foreign_writer(self) -> None:
        root = self.start(customers=5)
        api.advance(2)
        sk.EventSink(root).close()
        with self.assertRaises(api.OutputRootError):
            api.advance(1)

    def test_load_state_refuses_a_root_whose_head_is_elsewhere(self) -> None:
        root = self.start(customers=5)
        api.advance(2)
        early = api.save_state()
        api.advance(2)
        with self.assertRaises(api.OutputRootError):
            api.load_state(early, root, hidden_root=self.hidden)

    def test_snapshot_tokens_die_with_their_world(self) -> None:
        self.start(customers=5)
        snap = api.snapshot()
        api.discard_snapshot(snap)
        with self.assertRaises(api.SnapshotError):
            api.restore(snap, output_root=self.fresh_root("x"))
        with self.assertRaises(api.SnapshotError):
            api.discard_snapshot(snap)
        survivor = api.snapshot()
        self.start(seed=8, customers=5)
        with self.assertRaises(api.SnapshotError):
            api.restore(survivor, output_root=self.fresh_root("x"))

    def test_token_from_another_world_is_refused_after_load_state(self) -> None:
        self.start(seed=1, customers=5)
        other = api.save_state()
        self.start(seed=2, customers=5)
        snap = api.snapshot()
        api.load_state(other, self.fresh_root("other"), hidden_root=self.hidden)
        with self.assertRaises(api.SnapshotError):
            api.restore(snap, output_root=self.fresh_root("x"))


class TestCartRule(unittest.TestCase):
    T0 = 1_735_657_200_000

    def test_item_lives_until_the_exact_millisecond_of_expiry(self) -> None:
        items: cart.Cart = {}
        cart.add(items, "P0001", 2, 4900, self.T0, LIFETIME_MS)
        self.assertTrue(cart.is_live(items["P0001"], self.T0 + LIFETIME_MS - 1, LIFETIME_MS))
        self.assertFalse(cart.is_live(items["P0001"], self.T0 + LIFETIME_MS, LIFETIME_MS))

    def test_quantity_change_extends_and_other_products_do_not(self) -> None:
        items: cart.Cart = {}
        cart.add(items, "P0001", 2, 4900, self.T0, LIFETIME_MS)
        cart.add(items, "P0002", 1, 6500, self.T0, LIFETIME_MS)
        later = self.T0 + 10 * DAY_MS
        cart.add(items, "P0001", 1, 4900, later, LIFETIME_MS)
        at = self.T0 + LIFETIME_MS
        self.assertEqual(["P0001"], cart.live_products(items, at, LIFETIME_MS))
        cart.remove(items, "P0001", 1, later + DAY_MS, LIFETIME_MS)
        self.assertEqual(later + DAY_MS, items["P0001"]["last_change_ms"])

    def test_expired_item_is_purged_on_the_next_change_and_restarts(self) -> None:
        items: cart.Cart = {}
        cart.add(items, "P0001", 3, 4900, self.T0, LIFETIME_MS)
        cart.add(items, "P0002", 1, 6500, self.T0, LIFETIME_MS)
        expired = self.T0 + LIFETIME_MS
        self.assertIn("P0002", items)
        cart.add(items, "P0001", 1, 4900, expired, LIFETIME_MS)
        self.assertEqual({"P0001": {"quantity": 1, "last_change_ms": expired, "unit_price": 4900}}, items)
        self.assertEqual(0, cart.remove(items, "P0002", 1, expired, LIFETIME_MS))

    def test_quantity_never_exceeds_99(self) -> None:
        items: cart.Cart = {}
        self.assertEqual(99, cart.add(items, "P0001", 150, 4900, self.T0, LIFETIME_MS))
        self.assertEqual(0, cart.add(items, "P0001", 1, 4900, self.T0 + 1, LIFETIME_MS))


class TestSessionContinuity(unittest.TestCase):
    def run_visit(self, last_activity_offset_ms: int, still_open: bool) -> list[dict[str, object]]:
        state = world_state.new_world(1, 1, "smoke")
        start = state["calendar_start_ms"]
        visit_at = start + 12 * 3_600_000
        customer = state["customers"][0]
        customer["session"] = {
            "session_id": "S-C00000001-1735657200000", "start_ms": start,
            "last_activity_ms": visit_at - last_activity_offset_ms, "actions": 1,
            "open": still_open,
        }
        customer["next_seq"] = 1
        state["queue"] = [(visit_at, "C00000001", 0, "visit")]
        with mock.patch("src.simulator._internal.behavior.visit_probability", lambda cid: (0, 1)):
            return list(engine.run(state, start + DAY_MS))

    def test_visit_within_30_idle_minutes_does_not_start_a_session(self) -> None:
        self.assertEqual([], self.run_visit(30 * 60_000 - 1, still_open=False))

    def test_visit_while_a_session_is_open_does_not_start_another(self) -> None:
        self.assertEqual([], self.run_visit(60 * 60_000, still_open=True))

    def test_visit_after_30_idle_minutes_starts_a_new_session(self) -> None:
        records = self.run_visit(30 * 60_000, still_open=False)
        self.assertEqual("session_start", records[0]["event_type"])
        self.assertNotEqual("S-C00000001-1735657200000", records[0]["session_id"])


class TestCartThroughGeneratedEvents(SimulatorCase):
    def test_events_and_state_follow_the_30_day_rule_across_a_window_boundary(self) -> None:
        # S4: 카탈로그가 240개로 늘어 "만료 뒤 같은 상품 재담기" 가 드물어졌다. 이 시험은 장바구니 규칙을 보므로
        # 조회 대상을 카테고리마다 첫 상품(5개)으로 좁혀 S1 때의 밀도를 되살린다 — 생성 규칙은 그대로다.
        from src.simulator._internal import params

        active = params.active()
        narrow = tuple(pool[:1] for pool in active.category_pools)
        with mock.patch.object(active, "category_pools", narrow):
            root = self.start(customers=25)
            api.advance(75)
            boundary = api.save_state()
            api.load_state(boundary, root, hidden_root=self.hidden)
            api.advance(75)
            final = api.save_state()

        carts: dict[str, dict[str, list[int]]] = defaultdict(dict)
        views: dict[tuple[str, str], list[int]] = defaultdict(list)
        violations: list[str] = []
        re_added_after_expiry = 0
        view_inside_lifetime_then_expired = 0
        carried_over_boundary = 0
        boundary_ms = self.state(boundary)["now_ms"]

        checkout_lines: dict[str, list[str]] = {}
        for record in sk.read_events(root):
            cid, kind = str(record["customer_id"]), record["event_type"]
            # S4: 결제는 결제 시작 시점에 살아 있던 품목을 모두 사서 장바구니에서 뺀다(이벤트 없이).
            if kind == "checkout_start":
                at = _ms(str(record["timestamp"]))
                checkout_lines[cid] = [
                    pid for pid, value in carts[cid].items() if at < value[1] + LIFETIME_MS
                ]
                continue
            if kind == "purchase":
                for pid in checkout_lines.pop(cid, []):
                    carts[cid].pop(pid, None)
                continue
            if kind not in ("add_to_cart", "remove_from_cart", "product_view"):
                continue
            at, pid = _ms(str(record["timestamp"])), str(record["product_id"])
            if kind == "product_view":
                views[(cid, pid)].append(at)
                continue
            item = carts[cid].get(pid)
            live = item is not None and at < item[1] + LIFETIME_MS
            if item is not None and not live and kind == "add_to_cart":
                re_added_after_expiry += 1
                if any(item[1] < v < item[1] + LIFETIME_MS for v in views[(cid, pid)]):
                    view_inside_lifetime_then_expired += 1
            quantity = int(record["quantity"])
            if kind == "add_to_cart":
                carts[cid][pid] = [(item[0] if live else 0) + quantity, at]
                continue
            if not live or quantity > item[0]:
                violations.append(f"{cid} {pid} {record['timestamp']}")
                continue
            if item[1] < boundary_ms <= at:
                carried_over_boundary += 1
            if quantity == item[0]:
                del carts[cid][pid]
            else:
                carts[cid][pid] = [item[0] - quantity, at]

        self.assertEqual([], violations, "만료된 항목이나 없는 수량을 뺐다")
        self.assertGreater(re_added_after_expiry, 0)
        self.assertGreater(view_inside_lifetime_then_expired, 0)
        self.assertGreater(carried_over_boundary, 0)

        document = self.state(final)
        now = document["now_ms"]
        for customer in document["customers"]:
            cid = customer["customer_id"]
            in_state = {
                pid: [item["quantity"], item["last_change_ms"]]
                for pid, item in customer["cart"].items()
                if now < item["last_change_ms"] + LIFETIME_MS
            }
            reconstructed = {
                pid: value for pid, value in carts[cid].items() if now < value[1] + LIFETIME_MS
            }
            self.assertEqual(reconstructed, in_state, cid)


if __name__ == "__main__":
    unittest.main()
