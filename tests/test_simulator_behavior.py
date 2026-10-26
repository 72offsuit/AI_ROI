"""S4~S6(#143) — 구매 퍼널 · 이탈 진행 · 처치 반응 · 참 효과 기록 · 가드레일 CLI.

- 처치를 배정한 세계는 8종 이상의 이벤트를 내고 전건이 측정 계약을 통과한다.
- 참 효과는 숨김 영역에만 쓰이고, 배정한 처치 팔의 반사실 결과는 실제로 관측된 결과와 같다(CRN 일관성).
- 처치가 있어도 분할 불변성(advance(a)+advance(b) == advance(a+b))이 유지된다.
- 카탈로그 사본은 정본 경제 규칙(product_margin)과 같다.
- 재구매 게이트(#183): 관측 중 가입 고객의 생애 첫 구매 뒤 한 번, 처치와 무관한 고객 고정 난수로 정해진다.
"""

from __future__ import annotations

import contextlib
import hashlib
import io
import json
import math
import unittest
from collections import defaultdict
from datetime import timedelta
from unittest import mock

import src.simulator.__main__ as cli
from src.measurement import schema as sc
from src.measurement import sink as sk
from src.simulator import api
from src.simulator._internal import clock, engine, params, rng, treatment
from src.simulator._internal import world as world_state
from tests.test_simulator_support import REPO_ROOT, SimulatorCase, event_digest

try:
    import yaml
except ImportError:  # 의존성 없는 잡에서는 정본 대조만 건너뛴다
    yaml = None

ARMS = ("T0", "T1", "T2", "T3", "T4")


def round_robin(customers: int) -> dict[str, str]:
    return {f"C{i:08d}": ARMS[i % len(ARMS)] for i in range(1, customers + 1)}


class TestTreatedWorld(SimulatorCase):
    CUSTOMERS = 80

    def setUp(self) -> None:
        super().setUp()
        self.root = self.start(seed=11, customers=self.CUSTOMERS, profile="small")
        self.warm = api.advance(60)
        self.assignment = round_robin(self.CUSTOMERS)
        api.apply_treatment(self.assignment)
        self.window = api.advance(42)
        self.records = list(sk.read_events(self.root))

    def test_at_least_eight_event_types_and_every_event_validates(self) -> None:
        types = {r["event_type"] for r in self.records}
        self.assertGreaterEqual(len(types), 8, sorted(types))
        for required in ("checkout_start", "purchase", "campaign_exposed", "push_sent",
                         "coupon_exposed", "coupon_clicked", "coupon_use"):
            self.assertIn(required, types)
        problems = [(r["event_id"], sc.validate_event(r)) for r in self.records if sc.validate_event(r)]
        self.assertEqual([], problems)

    def test_coupon_use_matches_a_purchase_of_the_same_order(self) -> None:
        purchases = {r["order_id"]: r for r in self.records if r["event_type"] == "purchase"}
        uses = [r for r in self.records if r["event_type"] == "coupon_use"]
        self.assertTrue(uses)
        for use in uses:
            with self.subTest(order=use["order_id"]):
                purchase = purchases[use["order_id"]]
                self.assertEqual(use["order_amount"], purchase["order_amount"])
                self.assertEqual(use["coupon_id"], purchase["coupon_id"])
                self.assertIn(use["treatment_id"], ("T2", "T3"))

    def test_ground_truth_lives_only_in_the_hidden_area(self) -> None:
        files = sorted((self.hidden / "ground_truth").glob("po-*.jsonl"))
        self.assertEqual(1, len(files))
        rows = [json.loads(line) for line in files[0].read_text(encoding="ascii").splitlines()]
        self.assertEqual(sorted(self.assignment), [r["customer_id"] for r in rows])
        for row in rows:
            self.assertEqual(self.assignment[row["customer_id"]], row["assigned"])
            self.assertEqual(set(ARMS), set(row["outcomes"]))
            self.assertEqual(set(ARMS[1:]), set(row["tau_purchase"]))
        published = "".join(
            path.name for path in sorted(self.root.rglob("*")) if path.is_file()
        )
        self.assertNotIn("ground_truth", published)
        self.assertNotIn("po-", published)

    def test_assigned_arm_of_the_counterfactual_equals_what_was_observed(self) -> None:
        start = self.warm.end.isoformat(timespec="milliseconds")
        end = (self.warm.end + timedelta(days=42)).isoformat(timespec="milliseconds")
        observed: dict[str, list[int]] = defaultdict(list)
        for record in self.records:
            if record["event_type"] == "purchase" and start <= str(record["timestamp"]) < end:
                observed[str(record["customer_id"])].append(int(record["order_amount"]))
        files = sorted((self.hidden / "ground_truth").glob("po-*.jsonl"))
        rows = [json.loads(line) for line in files[0].read_text(encoding="ascii").splitlines()]
        purchasers = 0
        for row in rows:
            cid = row["customer_id"]
            arm = row["outcomes"][row["assigned"]]
            with self.subTest(customer=cid):
                self.assertEqual(len(observed.get(cid, [])), arm["orders"])
                self.assertEqual(sum(observed.get(cid, [])), arm["revenue"])
            purchasers += arm["purchased"]
        self.assertGreater(purchasers, 0)


class TestBranchesFromOneSnapshot(SimulatorCase):
    def test_each_branch_keeps_its_own_ground_truth_file(self) -> None:
        self.start(seed=9, customers=20, profile="small")
        api.advance(30)
        snap = api.snapshot()
        plans = [
            {f"C{i:08d}": "T3" for i in range(1, 11)},
            {f"C{i:08d}": "T1" for i in range(5, 21)},
        ]
        for number, plan in enumerate(plans):
            api.restore(snap, output_root=self.fresh_root(f"branch{number}"))
            api.apply_treatment(plan)
            api.advance(42)
        files = sorted((self.hidden / "ground_truth").glob("po-*.jsonl"))
        self.assertEqual(2, len(files))
        rows = [
            {r["customer_id"]: r for r in map(json.loads, f.read_text(encoding="ascii").splitlines())}
            for f in files
        ]
        assigned = sorted([{r["assigned"] for r in found.values()} for found in rows], key=sorted)
        self.assertEqual([{"T1"}, {"T3"}], assigned)
        shared = sorted(set(rows[0]) & set(rows[1]))
        self.assertTrue(shared)
        for cid in shared:
            first = {k: v for k, v in rows[0][cid].items() if k != "assigned"}
            second = {k: v for k, v in rows[1][cid].items() if k != "assigned"}
            self.assertEqual(first, second, cid)


class TestTreatmentKeepsSplitInvariance(SimulatorCase):
    def run_split(self, splits: tuple[int, ...]) -> str:
        root = self.start(seed=3, customers=25, profile="small")
        api.advance(30)
        api.apply_treatment(round_robin(25))
        for days in splits:
            api.advance(days)
        return event_digest(sk.read_events(root))

    def test_one_window_equals_two_windows(self) -> None:
        self.assertEqual(self.run_split((42,)), self.run_split((10, 32)))


class TestReassignmentOverwrites(SimulatorCase):
    def test_t0_after_a_coupon_ends_coupon_use(self) -> None:
        root = self.start(seed=5, customers=40, profile="small")
        api.advance(30)
        api.apply_treatment({f"C{i:08d}": "T3" for i in range(1, 41)})
        api.advance(1)
        api.apply_treatment({f"C{i:08d}": "T0" for i in range(1, 41)})
        cutoff = api.advance(41).start.isoformat(timespec="milliseconds")
        late = [r for r in sk.read_events(root)
                if r["event_type"] == "coupon_use" and str(r["timestamp"]) >= cutoff]
        self.assertEqual([], late)


class TestStreamKeyFastPath(unittest.TestCase):
    def test_fast_key_is_byte_identical_to_canonical_json(self) -> None:
        cases = [
            (0, "C00000001", "day", 0), (2**63 - 1, "C99999999", "response:T3", -2),
            (42, None, "persona", -1), (7, "C00000002", "trait:x_y", 123456),
            (1, "C1", "공백 있는 용도", 3), (1, 'C"1', "day", 3), (1, "C1", "", 3), (True, "C1", "day", 1),
        ]
        for seed, cid, purpose, day in cases:
            with self.subTest(case=(seed, cid, purpose, day)):
                self.assertEqual(
                    rng.canonical_json([rng.RNG_SCHEME, seed, cid, purpose, day]),
                    rng._stream_key(seed, cid, purpose, day),
                )


class TestEventKeyFastPath(unittest.TestCase):
    def test_fast_event_key_is_byte_identical_to_canonical_json(self) -> None:
        for seed, cid, seq in [(0, "C00000001", 0), (2**63 - 1, "C99999999", 10**9), (True, "C1", 1),
                               (1, 'C"1', 2), (1, "", 3), (1, "고객", 4)]:
            with self.subTest(case=(seed, cid, seq)):
                self.assertEqual(
                    rng.canonical_json([rng.EVENT_ID_SCHEME, seed, cid, seq]), rng._event_key(seed, cid, seq)
                )


class TestCatalogCopy(unittest.TestCase):
    def test_catalog_is_generated_from_product_margin(self) -> None:
        catalog = params.active().catalog
        self.assertEqual(240, len(catalog))
        self.assertEqual([f"P{i:04d}" for i in range(1, 241)], [p.product_id for p in catalog])
        for product in catalog:
            self.assertGreater(product.unit_price, 0)
            self.assertLess(product.unit_cost, product.unit_price)

    @unittest.skipIf(yaml is None, "BLOCKED: PyYAML 없음 — 정본 economic_config.yaml 과 대조하지 않았다")
    def test_copy_matches_the_canonical_economic_rule(self) -> None:
        canonical = yaml.safe_load(
            (REPO_ROOT / "config" / "economic_config.yaml").read_text(encoding="utf-8")
        )["product_margin"]
        copy = json.loads(
            (REPO_ROOT / "config" / "simulator_config.yaml").read_text(encoding="utf-8")
        )["catalog"]["categories"]
        self.assertEqual(sorted(canonical), sorted(entry["category"] for entry in copy))
        for entry in copy:
            source = canonical[entry["category"]]
            with self.subTest(category=entry["category"]):
                self.assertEqual(round(source["cost_rate"] * 10_000), entry["cost_rate_bp"])
                self.assertEqual(source["median_price_krw"], entry["median_price_krw"])
                self.assertEqual(round(source["frequency_weight"] * 10_000), entry["frequency_weight_bp"])
                self.assertEqual(source["pool_size"], entry["pool_size"])


class TestGuardrailsCli(SimulatorCase):
    def test_guardrails_writes_hidden_json_and_prints_a_table(self) -> None:
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = cli.main([
                "guardrails", "--seed", "1", "--customers", "120", "--warmup-days", "60",
                "--output-root", str(self.fresh_root("guardrails")), "--hidden-root", str(self.hidden),
            ])
        self.assertEqual(cli.EXIT_OK, code)
        text = out.getvalue()
        for name in ("churn_rate", "ate_T1", "ate_T4", "coupon_use_T2", "coupon_use_T3",
                     "sleeping_dog_T3", "persuadable_T3", "identity_T3", "spec41_churn_rate"):
            self.assertIn(name, text)
        reports = sorted(
            path for path in (self.hidden / "ground_truth" / "guardrails").glob("guardrails-*.json")
        )
        self.assertEqual(1, len(reports))
        report = json.loads(reports[0].read_text(encoding="utf-8"))
        names = {check["name"] for check in report["checks"]}
        for arm in ("T1", "T2", "T3", "T4"):
            self.assertIn(f"ate_{arm}", names)
            self.assertIn(f"identity_{arm}", names)
            quadrant = report["potential_outcome_quadrants"][arm]
            cells = [quadrant[f"{k}_bp"] for k in ("persuadable", "sleeping_dog", "sure_thing", "lost_cause")]
            self.assertLessEqual(abs(sum(cells) - 10_000), 4)
            # 항등식 P − D = ATE (잠재결과 정의) — S6 구현 결함 검사
            self.assertLessEqual(abs(quadrant["persuadable_bp"] - quadrant["sleeping_dog_bp"] - quadrant["ate_bp"]), 2)
        self.assertEqual([500, 2000], next(c for c in report["checks"] if c["name"] == "coupon_use_T2")["range_bp"])
        self.assertIn("eligible_spec41", report)
        self.assertIn(report["checks"][0]["status"], ("pass", "fail", "not_run"))


# ── 재구매 게이트(#183) ───────────────────────────────────────────────────────


@contextlib.contextmanager
def recorded_gates(calls: list[dict[str, object]]):
    """엔진의 게이트 호출마다 전후 상태와 결정을 `calls` 에 남긴다. 엔진 동작은 바꾸지 않는다.

    결정은 이탈 중이 아닌 사본(probe)에 엔진의 게이트를 한 번 더 돌려 읽는다 — 이미 이탈 진행 중인 고객은 실제
    고객에서 결정이 드러나지 않아서다. 결정을 스파이가 따로 계산하지 않는 것은, 그러면 엔진이 열쇠를 바꿔도
    처치 무관 테스트가 스파이의 계산만 보게 되어서다. 대신 probe 가 고객·엔진 상태를 건드리지 않았는지
    매번 확인한다 — 게이트가 상태를 가진 난수(예: 하루 스트림)를 쓰면 여기서 바로 실패한다.
    """
    original = engine._repurchase_gate

    def spy(window, customer):
        probe = {**customer, "churning": False, "engagement": params.PPM}
        untouched = engine_view(window, customer)
        original(window, probe)
        if engine_view(window, customer) != untouched:
            raise AssertionError(f"{customer['customer_id']}: 게이트 probe 가 고객·엔진 상태를 바꿨다")
        before = (customer["churning"], customer["engagement"])
        original(window, customer)
        calls.append({
            "customer_id": customer["customer_id"],
            "order_count": customer["rfm"]["order_count"],
            "first_purchase_ms": customer["rfm"]["last_purchase_ms"],
            "observed_signup": customer["signup_ms"] > window.world["calendar_start_ms"],
            "failed": probe["churning"],
            "before": before,
            "after": (customer["churning"], customer["engagement"]),
        })

    with mock.patch.object(engine, "_repurchase_gate", spy):
        yield


def engine_view(window, customer: dict[str, object]) -> tuple[str, list, list]:
    """게이트 probe 가 바꾸면 안 되는 것: 고객 전체 · 하루 난수 스트림의 위치 · 사건 큐."""
    # DayDraws 에 공개 조회가 없어 내부 계수기를 읽는다. 열쇠에 None 이 섞여 repr 로 정렬한다.
    draws = sorted((repr(key), stream._count) for key, stream in window.draws._streams.items())
    return json.dumps(customer, sort_keys=True), draws, sorted(window.heap)


@contextlib.contextmanager
def repurchase_trait_forced_to_zero():
    """모든 고객의 재구매 성향을 0 으로 둔다 — 게이트가 적용되는 고객은 반드시 실패한다."""
    original = engine.behavior_traits
    with mock.patch.object(engine, "behavior_traits", lambda c: {**original(c), "repurchase": 0}):
        yield


def drain(world: dict[str, object], days: int) -> list[dict[str, object]]:
    return list(engine.run(world, world["now_ms"] + days * clock.DAY_MS))


class TestRepurchaseGateWiring(unittest.TestCase):
    """재구매 성향을 0 으로 고정해, 게이트가 적용되면 반드시 실패하게 만든 세계에서 배선을 본다."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.calls: list[dict[str, object]] = []
        cls.world = world_state.new_world(5, 400, "small")
        with repurchase_trait_forced_to_zero(), recorded_gates(cls.calls):
            drain(cls.world, 300)
        cls.p = params.active()

    def test_gate_runs_once_per_customer_right_after_the_first_purchase(self) -> None:
        self.assertTrue(self.calls)
        self.assertEqual({1}, {call["order_count"] for call in self.calls})
        ids = [call["customer_id"] for call in self.calls]
        self.assertEqual(len(ids), len(set(ids)))

    def test_day_zero_customers_are_left_unchanged_even_when_the_draw_would_fail(self) -> None:
        day_zero = [call for call in self.calls if not call["observed_signup"]]
        self.assertTrue(day_zero)
        for call in day_zero:
            with self.subTest(customer=call["customer_id"]):
                self.assertFalse(call["failed"])
                self.assertEqual(call["before"], call["after"])

    def test_failed_gate_starts_churn_progression_like_a_daily_onset(self) -> None:
        fresh = [c for c in self.calls if c["observed_signup"] and not c["before"][0]]
        self.assertTrue(fresh)
        for call in fresh:
            engagement = call["before"][1]
            expected = max(self.p.engagement_floor_ppm, engagement * self.p.decay_ppm // params.PPM)
            with self.subTest(customer=call["customer_id"]):
                self.assertTrue(call["failed"])
                self.assertEqual((True, expected), call["after"])

    def test_failed_gate_on_an_already_churning_customer_does_not_decay_twice(self) -> None:
        churning = [c for c in self.calls if c["observed_signup"] and c["before"][0]]
        self.assertTrue(churning)
        for call in churning:
            with self.subTest(customer=call["customer_id"]):
                self.assertEqual(call["before"], call["after"])

    def test_failed_gate_customers_can_still_recover(self) -> None:
        failed = {
            c["customer_id"] for c in self.calls
            if c["observed_signup"] and c["failed"] and not c["before"][0]
        }
        self.assertTrue(failed)
        # 게이트로 이탈 진행에 들어간 고객만 본다. 이탈 진행을 끝내는 길은 하루 recovery hazard 뿐이라
        # 끝에 이탈 중이 아니면 회복한 것이다.
        recovered = [
            c["customer_id"] for c in self.world["customers"]
            if c["customer_id"] in failed and not c["churning"]
        ]
        self.assertTrue(recovered)


class TestRepurchaseGateRate(unittest.TestCase):
    SEEDS = range(1, 31)

    def test_failure_rate_of_observed_signups_matches_their_repurchase_trait(self) -> None:
        base = world_state.new_world(3, 1000, "small")
        start = base["calendar_start_ms"]
        newcomers = [c for c in base["customers"] if c["signup_ms"] > start]
        self.assertGreater(len(newcomers), 50)
        failures = 0
        expected = 0.0
        variance = 0.0
        for seed in self.SEEDS:
            # seed 만 바꾼 세계마다 게이트 난수 열쇠가 달라 같은 고객·같은 Trait 의 독립 표본이 된다.
            window = engine._Window({**base, "seed": seed}, None)
            for customer in newcomers:
                probe = {**customer, "churning": False, "engagement": params.PPM}
                engine._repurchase_gate(window, probe)
                failures += probe["churning"]
                keep = window.traits(customer)["repurchase"] / params.PPM
                expected += 1 - keep
                variance += keep * (1 - keep)
        # 실패 수는 독립 Bernoulli(1 − repurchase) 의 합이다. 4σ 안이면 Trait 평균과 맞다고 본다
        # (정규 근사로 우연히 벗어날 확률 약 6e-5). 성공·실패를 뒤집은 구현은 P6 평균(약 0.55)에서
        # 약 0.1 × 표본 수만큼 어긋나 10σ 이상 벗어난다.
        self.assertLessEqual(abs(failures - expected), 4 * math.sqrt(variance), (failures, expected))


class TestRepurchaseGateIgnoresTreatment(unittest.TestCase):
    def test_same_customer_gets_the_same_gate_result_under_every_arm(self) -> None:
        world = world_state.new_world(5, 400, "small")
        drain(world, 120)
        start = world["calendar_start_ms"]
        candidates = [
            c["customer_id"] for c in world["customers"]
            if c["signup_ms"] > start and c["rfm"]["order_count"] == 0
        ]
        calls: list[dict[str, object]] = []
        with recorded_gates(calls):
            treatment.potential_outcomes(world, candidates)
        decisions: dict[str, set[bool]] = defaultdict(set)
        first_purchase_days: dict[str, set[int]] = defaultdict(set)
        for call in calls:
            decisions[call["customer_id"]].add(call["failed"])
            first_purchase_days[call["customer_id"]].add((call["first_purchase_ms"] - start) // clock.DAY_MS)
        self.assertTrue(decisions)
        self.assertEqual({cid: 1 for cid in decisions}, {cid: len(found) for cid, found in decisions.items()})
        # 처치로 첫 구매 날짜가 달라진 고객이 있어야 "날짜와 무관하다" 가 실제로 검사된다.
        self.assertTrue(any(len(found) > 1 for found in first_purchase_days.values()))


# 판마다 게이트가 실제로 발화하는 실행(seed 8 · small · 300명 · 200일)의 정확한 값. GOLDEN 의 14일 창에서는 게이트가
# 발화하지 않아, 이 표가 없으면 게이트 열쇠(purpose·day)를 바꿔도 판 상향 없이 통과한다. 지난 판은 기록으로 남긴다.
# (관측 중 가입 고객의 {customer_id: 게이트 결정}, 이벤트 다이제스트, 상태 sha256)
GATE_GOLDEN: dict[str, tuple[dict[str, str], str, str]] = {
    "sim-0.5": (
        {
            "C00000043": "pass", "C00000066": "fail", "C00000081": "pass", "C00000113": "pass",
            "C00000124": "pass", "C00000140": "pass", "C00000164": "fail", "C00000208": "pass",
            "C00000236": "pass", "C00000244": "fail", "C00000249": "fail", "C00000253": "pass",
            "C00000258": "pass", "C00000269": "fail", "C00000273": "fail", "C00000297": "pass",
        },
        "b56e49820e419ebe9ad7f114456ac92ff7452c4bc80b442cc7930341d85bc186",
        "14f7f41f7018de591bd1c98fc8f110981801c61cb62740cc949f164fab873bda",
    ),
}


class TestRepurchaseGateKeepsSplitInvariance(unittest.TestCase):
    SEED, CUSTOMERS, TOTAL = 8, 300, 200

    @classmethod
    def setUpClass(cls) -> None:
        cls.digest, cls.state, cls.calls = cls.run_world((cls.TOTAL,))
        cls.start_ms = world_state.new_world(cls.SEED, 1, "small")["calendar_start_ms"]

    @classmethod
    def run_world(cls, splits: tuple[int, ...], *, reload: bool = False) -> tuple[str, bytes, list]:
        world = world_state.new_world(cls.SEED, cls.CUSTOMERS, "small")
        records: list[dict[str, object]] = []
        calls: list[dict[str, object]] = []
        with recorded_gates(calls):
            for days in splits:
                if reload:
                    world = world_state.decode(world_state.encode(world))
                records += drain(world, days)
        return event_digest(records), world_state.encode(world), calls

    def test_gate_decisions_and_digests_match_the_pinned_values_of_this_version(self) -> None:
        version = world_state.SIMULATOR_VERSION
        self.assertIn(version, GATE_GOLDEN, f"{version} 의 게이트 골든 값이 없다 — 게이트를 바꾸면 판과 상수를 함께 올린다")
        decisions, event_sha, state_sha = GATE_GOLDEN[version]
        observed = {
            c["customer_id"]: "fail" if c["failed"] else "pass" for c in self.calls if c["observed_signup"]
        }
        self.assertEqual(decisions, observed)
        self.assertEqual(event_sha, self.digest)
        self.assertEqual(state_sha, hashlib.sha256(self.state).hexdigest())

    def test_split_and_save_load_runs_match_one_continuous_run_with_the_gate_firing(self) -> None:
        split_at = 70
        split_ms = self.start_ms + split_at * clock.DAY_MS
        self.assertTrue(any(
            c["observed_signup"] and c["failed"] and c["first_purchase_ms"] >= split_ms for c in self.calls
        ))
        for splits, reload in (((split_at, self.TOTAL - split_at), False),
                               ((split_at, self.TOTAL - split_at), True),
                               ((1, 33, 166), True)):
            with self.subTest(splits=splits, reload=reload):
                digest, state, _ = self.run_world(splits, reload=reload)
                self.assertEqual(self.digest, digest)
                self.assertEqual(self.state, state)


if __name__ == "__main__":
    unittest.main()
