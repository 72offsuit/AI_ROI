"""S4~S6(#143) — 구매 퍼널 · 이탈 진행 · 처치 반응 · 참 효과 기록 · 가드레일 CLI.

- 처치를 배정한 세계는 8종 이상의 이벤트를 내고 전건이 측정 계약을 통과한다.
- 참 효과는 숨김 영역에만 쓰이고, 배정한 처치 팔의 반사실 결과는 실제로 관측된 결과와 같다(CRN 일관성).
- 처치가 있어도 분할 불변성(advance(a)+advance(b) == advance(a+b))이 유지된다.
- 카탈로그 사본은 정본 경제 규칙(product_margin)과 같다.
"""

from __future__ import annotations

import contextlib
import io
import json
import unittest
from collections import defaultdict
from datetime import timedelta

import src.simulator.__main__ as cli
from src.measurement import schema as sc
from src.measurement import sink as sk
from src.simulator import api
from src.simulator._internal import params, rng
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


if __name__ == "__main__":
    unittest.main()
