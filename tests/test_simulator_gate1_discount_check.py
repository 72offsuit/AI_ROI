"""`scripts/gate1_discount_check.py` — 가정 A-DISCOUNT(시뮬레이터 할인액 = 처치 단가) 실측 판정.

세계 디렉터리(`run_world.py` 출력 모양: meta.json · assignments.json · raw/simulator_exchange/orders.jsonl)는
테스트 안에서 만든 가짜다. 단가는 테스트 경제 config 에서 읽고, 실제 `config/economic_config.yaml` 을 이 스크립트가
읽을 수 있는지는 `TestRealConfig` 가 본다. PyYAML 이 없으면 skip 한다. skip 은 통과가 아니다.
"""

from __future__ import annotations

import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path

from tests.test_simulator_gate1_churn_check import HAVE_YAML, REALISM_WORLD, base_criteria, write_yaml_json

REPO = Path(__file__).resolve().parents[1]
REAL_CRITERIA = REPO / "config" / "simulator_gate1_acceptance.yaml"
REAL_ECONOMIC_CONFIG = REPO / "config" / "economic_config.yaml"

NEEDS_YAML = "BLOCKED: PyYAML 미설치 — A-DISCOUNT 판정을 검증하지 않았다(통과가 아니다)"

# scripts/ 는 test_simulator_gate1_churn_check 가 sys.path 에 넣었다 — 같은 모듈 한 벌을 공유한다.
import gate1_discount_check as dc  # noqa: E402

SEEDS = [47, 48, 49, 50, 51]
CUSTOMERS = 13000
# 실제 단가(3,000 · 7,000)와 일부러 다르게 둔다 — 단가를 config 에서 읽는지 확인한다.
UNIT_COSTS = {"T2": 2500, "T3": 6500}
ASSIGNED_AT = "2025-06-30T00:00:00+09:00"
AFTER = "2025-07-01T10:00:00.000+09:00"
BEFORE = "2025-06-29T23:59:59.999+09:00"
ASSIGNMENTS = {"C1": "T2", "C2": "T3", "C3": "T0", "C4": "T1"}


def order(order_id: str, customer: str, discount, ordered_at: str = AFTER) -> dict:
    return {"order_id": order_id, "customer_id": customer, "ordered_at": ordered_at, "discount": discount,
            "order_amount": 50000, "shipping_fee": 0, "shipping_charged": 0}


def clean_orders() -> list[dict]:
    return [order("O1", "C1", 2500), order("O2", "C2", 6500), order("O3", "C3", 0), order("O4", "C9", 0),
            order("O5", "C1", 0, BEFORE), order("O6", "C2", 6500.0, ASSIGNED_AT)]


@unittest.skipUnless(HAVE_YAML, NEEDS_YAML)
class DiscountCase(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.tmp = Path(self._tmp.name)
        self.criteria = base_criteria()
        self.unit_costs = dict(UNIT_COSTS)
        self.metas = {seed: {"seed": seed, "customers": CUSTOMERS, **REALISM_WORLD, "assigned": 4}
                      for seed in SEEDS}
        self.orders = {seed: clean_orders() for seed in SEEDS}
        self.assigned_at = ASSIGNED_AT

    def write_world(self, name: str, seed: int) -> Path:
        world = self.tmp / name
        (world / dc.ORDERS_FILE.parent).mkdir(parents=True)
        (world / dc.META_FILE).write_text(json.dumps(self.metas[seed]), encoding="utf-8")
        (world / dc.ASSIGNMENTS_FILE).write_text(
            json.dumps({"assigned_at": self.assigned_at, "assignments": ASSIGNMENTS}), encoding="utf-8")
        lines = [json.dumps(row) for row in self.orders.get(seed, [])]
        (world / dc.ORDERS_FILE).write_text("\n".join(lines) + "\n", encoding="utf-8")
        return world

    def run_check(self, worlds: list[str] | None = None) -> tuple[int, dict | None, str, str]:
        criteria = write_yaml_json(self.tmp / "criteria.yaml", self.criteria)
        economic = write_yaml_json(self.tmp / "economic_config.yaml", {"treatment_cost": {
            "T1": {"unit_cost_krw": 3000}, **{arm: {"unit_cost_krw": cost} for arm, cost in self.unit_costs.items()}}})
        if worlds is None:
            worlds = [str(self.write_world(f"w{index}", seed))
                      for index, seed in enumerate(sorted(self.metas, reverse=True))]
        out_json, out_md = self.tmp / "out" / "discount.json", self.tmp / "out" / "discount.md"
        argv = ["--criteria", str(criteria), "--economic-config", str(economic), "--worlds", *worlds,
                "--out-json", str(out_json), "--out-md", str(out_md)]
        stdout, stderr = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            code = dc.main(argv)
        report = json.loads(out_json.read_text(encoding="utf-8")) if out_json.exists() else None
        return code, report, stdout.getvalue(), stderr.getvalue()

    def assert_input_error(self, fragment: str, **kwargs) -> None:
        code, report, out, err = self.run_check(**kwargs)
        self.assertEqual(dc.EXIT_INPUT_ERROR, code, err)
        self.assertIsNone(report)
        self.assertEqual("", out)
        self.assertIn(fragment, err)


class TestDiscountRule(DiscountCase):
    def test_clean_worlds_pass_with_counts(self) -> None:
        code, report, out, _ = self.run_check()
        self.assertEqual(dc.EXIT_PASS, code)
        self.assertTrue(report["passed"])
        row = report["per_seed"]["47"]
        self.assertEqual(6, row["orders"])
        self.assertEqual(3, row["discounted_orders"])
        self.assertEqual({"T2": 1, "T3": 2}, row["discounted_by_arm"])
        self.assertEqual({"T2": 2500, "T3": 6500}, report["unit_costs"]["values"])
        self.assertIn("A-DISCOUNT — 통과", out)

    def test_order_at_exact_assignment_instant_is_allowed(self) -> None:
        self.orders = {seed: [order("O1", "C2", 6500, ASSIGNED_AT), order("O2", "C1", 2500, ASSIGNED_AT)]
                       for seed in SEEDS}
        code, _, _, _ = self.run_check()
        self.assertEqual(dc.EXIT_PASS, code)

    def test_each_violation_kind_is_counted(self) -> None:
        self.orders[49] = clean_orders() + [
            order("X1", "C9", 2500),                  # 미배정 고객
            order("X2", "C3", 2500),                  # T0 (쿠폰 팔이 아님)
            order("X3", "C4", 3000),                  # T1 (쿠폰 팔이 아님)
            order("X4", "C2", 6500, BEFORE),          # 배정 전
            order("X5", "C1", 6500),                  # T2 인데 T3 금액
            order("X6", "C9", 100, BEFORE),           # 미배정 + 배정 전 — 두 종류 모두 센다
        ]
        code, report, out, _ = self.run_check()
        self.assertEqual(dc.EXIT_FAIL, code)
        row = report["per_seed"]["49"]
        self.assertEqual({"not_coupon_arm": 4, "before_assignment": 2, "wrong_amount": 1}, row["violations"])
        self.assertEqual({"T0": 1, "T1": 1, "unassigned": 2}, row["not_coupon_arm_by_arm"])
        self.assertEqual(6, row["violating_orders"])
        self.assertEqual("fail", row["verdict"])
        self.assertEqual("pass", report["per_seed"]["47"]["verdict"])
        self.assertEqual(["X4", "X6"], [e["order_id"] for e in row["examples"]["before_assignment"]])
        self.assertEqual({"not_coupon_arm": 4, "before_assignment": 2, "wrong_amount": 1}, report["violations_total"])
        self.assertIn("A-DISCOUNT — 실패", out)
        self.assertEqual("on_fail(테스트)", report["verdict"]["on_fail"])

    def test_arm_without_discounted_orders_fails_instead_of_passing_vacuously(self) -> None:
        # T2 할인 주문이 하나도 없는 seed — 위반 0건이지만 확인한 것이 없으므로 실패다.
        self.orders[48] = [order("O2", "C2", 6500), order("O3", "C3", 0)]
        code, report, out, _ = self.run_check()
        self.assertEqual(dc.EXIT_FAIL, code)
        row = report["per_seed"]["48"]
        self.assertEqual(0, row["violating_orders"])
        self.assertEqual([{"arm": "T2", "discounted_orders": 0, "minimum": 1}], row["shortages"])
        self.assertEqual("fail", row["verdict"])
        self.assertIn("T2 할인 주문 0건 < 최소 1건", out)

    def test_minimum_comes_from_the_criteria(self) -> None:
        self.criteria["a_discount"]["min_discounted_orders_per_arm"] = 2   # seed 마다 T2 할인 주문은 1건
        code, report, _, _ = self.run_check()
        self.assertEqual(dc.EXIT_FAIL, code)
        self.assertEqual(2, report["min_discounted_orders_per_arm"])
        self.assertEqual(["T2"], [s["arm"] for s in report["per_seed"]["47"]["shortages"]])

    def test_world_conditions_must_match_criteria(self) -> None:
        for key, value in (("profile", "small"), ("days", 314), ("assign_day", 181), ("config", "exp.yaml"),
                           ("days", 315.0)):
            with self.subTest(key=key, value=value):
                self.metas = {seed: {"seed": seed, "customers": CUSTOMERS, **REALISM_WORLD} for seed in SEEDS}
                self.metas[50][key] = value
                self.fresh_dir()
                self.assert_input_error(f"{key} {value!r} ≠ 기준")

    def test_world_meta_without_config_key_is_refused(self) -> None:
        del self.metas[47]["config"]
        self.assert_input_error("config '(없음)' ≠ 기준 None")

    def test_unit_cost_is_read_from_economic_config(self) -> None:
        self.unit_costs["T2"] = 3000        # 주문은 2,500 원 그대로
        code, report, _, _ = self.run_check()
        self.assertEqual(dc.EXIT_FAIL, code)
        self.assertEqual(1, report["per_seed"]["47"]["violations"]["wrong_amount"])

    def test_missing_seed(self) -> None:
        del self.metas[51]
        self.assert_input_error("기준 seed [51] 가 없다")

    def test_extra_seed(self) -> None:
        self.metas[46] = {"seed": 46, "customers": CUSTOMERS, **REALISM_WORLD}
        self.assert_input_error("기준에 없는 seed [46]")

    def test_duplicate_seed(self) -> None:
        self.metas[50] = dict(self.metas[51])
        self.orders[50] = clean_orders()
        self.assert_input_error("seed 51 가 중복된다")

    def test_customers_must_match_criteria(self) -> None:
        self.metas[48]["customers"] = 200
        self.assert_input_error("customers 200 ≠ 기준 13000")

    def test_missing_orders_file(self) -> None:
        world = self.write_world("lonely", 47)
        (world / dc.ORDERS_FILE).unlink()
        self.assert_input_error("orders.jsonl 가 없다", worlds=[str(world)])

    def test_malformed_order_lines_are_input_errors(self) -> None:
        cases = [
            ({"order_id": "B1", "customer_id": "C1", "ordered_at": AFTER, "discount": None}, "discount 가 0 이상의"),
            ({"order_id": "B2", "customer_id": "C1", "ordered_at": AFTER, "discount": True}, "discount 가 0 이상의"),
            ({"order_id": "B3", "customer_id": "C1", "ordered_at": "2025-07-01T10:00:00", "discount": 2500},
             "시간대가 있는 ISO 시각이 아니다"),
            ({"order_id": "B4", "customer_id": 7, "ordered_at": AFTER, "discount": 2500}, "customer_id 가 문자열이 아니다"),
        ]
        for bad, fragment in cases:
            with self.subTest(fragment=fragment):
                self.orders = {seed: clean_orders() for seed in SEEDS}
                self.orders[47].append(bad)
                self.fresh_dir()
                self.assert_input_error(fragment)

    def test_broken_json_line_reports_line_number(self) -> None:
        worlds = [self.write_world(f"w{seed}", seed) for seed in SEEDS]
        with (worlds[0] / dc.ORDERS_FILE).open("a", encoding="utf-8") as handle:
            handle.write("{not json\n")
        self.assert_input_error(f"orders.jsonl:{len(clean_orders()) + 1}", worlds=[str(w) for w in worlds])

    def test_naive_assignment_time_is_an_input_error(self) -> None:
        self.assigned_at = "2025-06-30T00:00:00"
        self.assert_input_error("assigned_at: 시간대가 있는 ISO 시각이 아니다")

    def test_block_and_unit_cost_structure_are_validated(self) -> None:
        cases = [
            (lambda: self.criteria["a_discount"].pop("coupon_arms"), "coupon_arms 가 비어 있지 않은 문자열 목록이 아니다"),
            (lambda: self.criteria["a_discount"].update(coupon_arms=["T2", "T2"]), "coupon_arms 에 중복이 있다"),
            (lambda: self.criteria["a_discount"].update(unit_cost_from="config/economic_config.yaml treatment_cost"),
             "{arm} 가 없다"),
            (lambda: self.criteria["a_discount"].update(role="x"), "role 이 'assumption_check' 가 아니다"),
            (lambda: self.criteria.pop("a_discount"), "a_discount 블록이 없다"),
            (lambda: self.unit_costs.pop("T3"), "treatment_cost.T3.unit_cost_krw 가 양의 정수가 아니다"),
            (lambda: self.criteria["a_discount"].pop("min_discounted_orders_per_arm"),
             "min_discounted_orders_per_arm 이 양의 정수가 아니다"),
            (lambda: self.criteria["a_discount"].update(min_discounted_orders_per_arm=0),
             "min_discounted_orders_per_arm 이 양의 정수가 아니다"),
            (lambda: self.criteria["a_discount"].update(min_discounted_orders_per_arm=True),
             "min_discounted_orders_per_arm 이 양의 정수가 아니다"),
            (lambda: self.criteria.pop("sources"), "sources.realism.world 블록이 없다"),
            (lambda: self.criteria["sources"]["realism"]["world"].pop("config"), "world.config 가 없거나"),
            (lambda: self.criteria["sources"]["realism"]["world"].update(days="315"), "world.days 가 양의 정수가 아니다"),
            (lambda: self.criteria["sources"]["realism"]["world"].update(assign_day=315), "보다 작지 않다"),
        ]
        for mutate, fragment in cases:
            with self.subTest(fragment=fragment):
                self.criteria, self.unit_costs = base_criteria(), dict(UNIT_COSTS)
                mutate()
                self.fresh_dir()
                self.assert_input_error(fragment)

    def fresh_dir(self) -> None:
        # subTest 마다 새 하위 디렉터리에 세계를 만든다(write_world 는 기존 디렉터리를 거부한다).
        self.tmp = Path(tempfile.mkdtemp(dir=self._tmp.name))


@unittest.skipUnless(HAVE_YAML, NEEDS_YAML)
class TestRealConfig(unittest.TestCase):
    def test_real_block_and_unit_costs_load(self) -> None:
        raw = dc.gj._load_yaml(REAL_CRITERIA, "기준 파일")
        block = dc.load_discount_block(raw, REAL_CRITERIA)
        costs = dc.load_unit_costs(block, REAL_ECONOMIC_CONFIG)
        self.assertEqual(set(block.coupon_arms), set(costs))
        self.assertGreaterEqual(block.min_discounted_orders_per_arm, 1)
        world = dc.load_realism_world(raw, REAL_CRITERIA)
        self.assertEqual(REALISM_WORLD, world.as_meta())
        self.assertEqual("config/economic_config.yaml", block.unit_cost_from.split()[0])


if __name__ == "__main__":
    unittest.main()
