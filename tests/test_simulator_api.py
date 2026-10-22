from __future__ import annotations

import __future__
import argparse
import ast
import dataclasses
import inspect
import json
import re
import unittest
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

import src.simulator
import src.simulator.__main__ as cli
from src.measurement import schema as sc
from src.measurement import sink as sk
from src.simulator import api
from src.simulator._internal import profiles
from tests.test_simulator_support import REPO_ROOT, SimulatorCase, event_digest, root_digest

SIMULATOR_DIR = REPO_ROOT / "src" / "simulator"
CONTRACT_DOC = REPO_ROOT / "docs" / "simulator_api.md"
# S4(#143): 구매 퍼널(checkout_start·purchase)과 처치 노출·반응(마케팅 5종)이 더해졌다.
MARKETING = {"campaign_exposed", "push_sent", "coupon_exposed", "coupon_clicked", "coupon_use"}
UNTREATED = {
    "session_start", "page_view", "product_view", "add_to_cart", "remove_from_cart",
    "checkout_start", "purchase",
}
PRODUCED = UNTREATED | MARKETING
TIMESTAMP = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}\+09:00$")
KST = timezone(timedelta(hours=9))

BANNED_MODULES = frozenset({"random", "secrets", "uuid", "time", "math", "importlib"})
BANNED_ATTRIBUTES = frozenset({
    "now", "utcnow", "today", "time", "time_ns", "monotonic", "perf_counter", "process_time",
    "urandom", "uuid1", "uuid4", "getrandbits",
})
BANNED_BUILTINS = frozenset({"hash", "sum", "float", "__import__"})
DIRECTORY_LISTINGS = frozenset({"glob", "rglob", "iterdir", "listdir", "scandir"})
ORDER_INSENSITIVE_WRAPPERS = frozenset({"sorted", "any", "all"})


def _ms(timestamp: str) -> int:
    moment = datetime(
        int(timestamp[0:4]), int(timestamp[5:7]), int(timestamp[8:10]),
        int(timestamp[11:13]), int(timestamp[14:16]), int(timestamp[17:19]), tzinfo=KST,
    )
    epoch = datetime(1970, 1, 1, tzinfo=timezone.utc)
    return (moment - epoch) // timedelta(milliseconds=1) + int(timestamp[20:23])


def _unsorted_listing(node: ast.AST, parents: dict[ast.AST, ast.AST]) -> str | None:
    if not isinstance(node, ast.Call):
        return None
    func = node.func
    name = func.attr if isinstance(func, ast.Attribute) else getattr(func, "id", None)
    if name not in DIRECTORY_LISTINGS:
        return None
    parent = parents.get(node)
    if (
        isinstance(parent, ast.Call)
        and isinstance(parent.func, ast.Name)
        and parent.func.id in ORDER_INSENSITIVE_WRAPPERS
        and node in parent.args
    ):
        return None
    return name


def nondeterminism_findings(source: str, label: str) -> list[str]:
    findings: list[str] = []
    tree = ast.parse(source)
    parents = {child: node for node in ast.walk(tree) for child in ast.iter_child_nodes(node)}
    for node in ast.walk(tree):
        listing = _unsorted_listing(node, parents)
        if listing is not None:
            findings.append(f"{label}:{node.lineno} 정렬 없는 {listing}")
        where = f"{label}:{getattr(node, 'lineno', '?')}"
        if isinstance(node, ast.Import):
            findings += [f"{where} import {a.name}" for a in node.names
                         if a.name.split(".")[0] in BANNED_MODULES]
        elif isinstance(node, ast.ImportFrom) and node.module:
            if node.module.split(".")[0] in BANNED_MODULES:
                findings.append(f"{where} from {node.module}")
        elif isinstance(node, ast.Attribute) and node.attr in BANNED_ATTRIBUTES:
            findings.append(f"{where} .{node.attr}")
        elif isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            if node.func.id in BANNED_BUILTINS:
                findings.append(f"{where} {node.func.id}()")
        elif isinstance(node, ast.Constant) and isinstance(node.value, float):
            findings.append(f"{where} float {node.value!r}")
        elif isinstance(node, ast.BinOp) and isinstance(node.op, (ast.Div, ast.Pow)):
            findings.append(f"{where} {type(node.op).__name__}")
        elif isinstance(node, ast.AugAssign) and isinstance(node.op, (ast.Div, ast.Pow)):
            findings.append(f"{where} {type(node.op).__name__}=")
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            keywords = {k.arg for k in node.keywords}
            if node.func.attr == "to_bytes" and len(node.args) + len(keywords) < 2:
                findings.append(f"{where} to_bytes 길이·바이트 순서 생략")
            if node.func.attr == "from_bytes" and len(node.args) < 2 and "byteorder" not in keywords:
                findings.append(f"{where} from_bytes 바이트 순서 생략")
    return findings


def render(function: object) -> str:
    signature = inspect.signature(function)
    parts: list[str] = []
    star = False
    for parameter in signature.parameters.values():
        if parameter.kind is parameter.KEYWORD_ONLY and not star:
            parts.append("*")
            star = True
        text = parameter.name
        if parameter.annotation is not parameter.empty:
            text += f": {parameter.annotation}"
        if parameter.default is not parameter.empty:
            text += f" = {parameter.default!r}"
        parts.append(text)
    return f"def {function.__name__}({', '.join(parts)}) -> {signature.return_annotation}"


def public_functions() -> dict[str, object]:
    return {
        name: value for name, value in vars(api).items()
        if inspect.isfunction(value) and value.__module__ == api.__name__
        and not name.startswith("_")
    }


def public_exceptions() -> dict[str, str]:
    return {
        name: value.__bases__[0].__name__ for name, value in vars(api).items()
        if inspect.isclass(value) and issubclass(value, BaseException)
        and value.__module__ == api.__name__
    }


class TestGeneratedEventsMeetTheContract(SimulatorCase):
    def setUp(self) -> None:
        super().setUp()
        self.root = self.start(seed=5, customers=30)
        self.summary = api.advance(21)
        self.records = list(sk.read_events(self.root))

    def test_every_event_validates_and_is_attributed_to_the_simulator(self) -> None:
        self.assertGreater(len(self.records), 0)
        failures = [(r["event_id"], sc.validate_event(r)) for r in self.records if sc.validate_event(r)]
        self.assertEqual([], failures)
        sources = {sk.event_source(r) for r in self.records}
        self.assertEqual({sk.EventSource.SIMULATOR}, sources)
        manifest = sk.run_records(self.root)[0]
        self.assertEqual(0, manifest["rejected"])
        self.assertEqual({"simulator": len(self.records)}, manifest["sources"])

    def test_event_meta_and_identifiers(self) -> None:
        # 배정이 없는 세계는 마케팅 이벤트를 내지 않는다 — 노출은 apply_treatment 로만 생긴다.
        self.assertEqual(UNTREATED, {r["event_type"] for r in self.records})
        self.assertEqual(len(self.records), len({r["event_id"] for r in self.records}))
        for record in self.records:
            self.assertEqual(5, record["random_seed"])
            self.assertTrue(record["simulator_version"])
            self.assertRegex(str(record["timestamp"]), TIMESTAMP)

    def test_sessions_follow_the_session_id_rule(self) -> None:
        end_ms = _ms(self.summary.end.isoformat(timespec="milliseconds"))
        sessions: dict[str, list[dict[str, object]]] = defaultdict(list)
        for record in self.records:
            sessions[str(record["session_id"])].append(record)
        for session_id, rows in sessions.items():
            first = rows[0]
            self.assertEqual("session_start", first["event_type"], session_id)
            self.assertEqual(f"S-{first['customer_id']}-{_ms(str(first['timestamp']))}", session_id)
            stamps = [_ms(str(r["timestamp"])) for r in rows]
            self.assertTrue(all(b - a < 30 * 60_000 for a, b in zip(stamps, stamps[1:])), session_id)
            durations = [r["session_duration"] for r in rows]
            self.assertTrue(all(d is None for d in durations[:-1]), session_id)
            if durations[-1] is None:
                self.assertLess(end_ms - stamps[-1], 300_000, f"{session_id} 열린 채 끝나지 않았다")
            else:
                self.assertEqual((stamps[-1] - stamps[0]) // 1000, durations[-1], session_id)

    def test_a_customer_starts_a_new_session_only_after_30_idle_minutes(self) -> None:
        last_seen: dict[str, tuple[str, int]] = {}
        for record in self.records:
            cid, session_id = str(record["customer_id"]), str(record["session_id"])
            at = _ms(str(record["timestamp"]))
            previous = last_seen.get(cid)
            if previous is not None and previous[0] != session_id:
                self.assertGreaterEqual(at - previous[1], 30 * 60_000, session_id)
            last_seen[cid] = (session_id, at)

    def test_events_come_back_in_generation_order(self) -> None:
        returned = list(api.events(self.summary.end))
        self.assertEqual([r["event_id"] for r in self.records], [r["event_id"] for r in returned])
        keys = [(r["timestamp"], r["customer_id"]) for r in returned]
        self.assertEqual(sorted(keys), keys)

    def test_output_root_holds_only_sink_artifacts(self) -> None:
        self.assertEqual(
            {"events", "manifest.json", "runs"}, {p.name for p in self.root.iterdir()}
        )


class TestArgumentRules(SimulatorCase):
    def test_init_rejects_bad_arguments(self) -> None:
        root = self.fresh_root()
        cases = [
            (TypeError, (True, 5, "smoke", root)),
            (ValueError, (-1, 5, "smoke", root)),
            (ValueError, (1 << 63, 5, "smoke", root)),
            (TypeError, (1, True, "smoke", root)),
            (ValueError, (1, 0, "smoke", root)),
            (ValueError, (1, 100_000_000, "smoke", root)),
            (ValueError, (1, 5, "unknown", root)),
            (TypeError, (1, 5, 3, root)),
            (TypeError, (1, 5, "smoke", 3)),
        ]
        for error, arguments in cases:
            with self.subTest(arguments=arguments[:3]):
                with self.assertRaises(error):
                    api.init(*arguments, hidden_root=self.hidden)

    def test_profiles_from_the_spec_are_accepted(self) -> None:
        for profile in ("smoke", "short", "small", "reference", "long", "rolling"):
            with self.subTest(profile=profile):
                api.init(1, 2, profile, self.fresh_root(), hidden_root=self.hidden)

    def test_profile_time_axes_follow_the_spec(self) -> None:
        # data_spec §2.2 표 · DR-S3-p6-signup U11. label 42일은 프로파일 간 고정이다.
        expected = {
            "smoke": (90, None, 140), "short": (180, 90, 275), "small": (180, 90, 275),
            "reference": (273, 365, 640), "long": (365, 730, 1100), "rolling": (273, 365, 900),
        }
        self.assertEqual(set(expected), set(profiles.PROFILES))
        for name, (warmup, clv, run) in expected.items():
            with self.subTest(profile=name):
                axes = profiles.PROFILES[name]
                self.assertEqual((warmup, 42, clv, run), (
                    axes["warmup_days"], axes["label_window_days"],
                    axes["clv_horizon_days"], axes["run_days"],
                ))
                self.assertGreater(run, warmup + 42)

    def test_advance_rules(self) -> None:
        with mock.patch("src.simulator._internal.runtime.active", None):
            with self.assertRaises(api.NotInitializedError):
                api.advance(1)
            with self.assertRaises(api.NotInitializedError):
                api.snapshot()
            with self.assertRaises(api.NotInitializedError):
                api.save_state()
        self.start(customers=2)
        for value, error in ((True, TypeError), (1.0, TypeError), ("1", TypeError), (-1, ValueError)):
            with self.subTest(value=value):
                with self.assertRaises(error):
                    api.advance(value)

    def test_time_arguments_must_be_aware_and_not_in_the_future(self) -> None:
        self.start(customers=3)
        end = api.advance(2).end
        self.assertEqual([], [r for r in api.events(end - timedelta(days=2))])
        with self.assertRaises(ValueError):
            api.events(end.replace(tzinfo=None))
        with self.assertRaises(ValueError):
            api.events(end + timedelta(milliseconds=1))
        with self.assertRaises(TypeError):
            api.events("2025-01-03")
        with self.assertRaises(ValueError):
            api.metrics(end, end - timedelta(days=1))
        with self.assertRaises(ValueError):
            api.exchange_bundle(end + timedelta(days=1))

    def test_treatment_assignments_are_all_or_nothing(self) -> None:
        self.start(customers=4)
        api.advance(2)
        before = api.save_state()
        for bad in ({"C00000001": "T1", "C00000009": "T1"}, {"C00000001": "T5"},
                    {"C1": "T1"}, {1: "T1"}, {"C00000002": None}):
            with self.subTest(bad=bad):
                with self.assertRaises(api.AssignmentError):
                    api.apply_treatment(bad)
                self.assertEqual(before, api.save_state())
        with self.assertRaises(TypeError):
            api.apply_treatment([("C00000001", "T1")])
        api.apply_treatment({"C00000002": "T0", "C00000001": "T3"})
        recorded = self.state(api.save_state())
        self.assertEqual(
            [[recorded["now_ms"], "T3"]], recorded["customers"][0]["assignments"]
        )

    def test_treatment_changes_only_treated_customers_and_exposes_at_assignment(self) -> None:
        def by_customer(root: Path) -> dict[str, str]:
            grouped: dict[str, list[dict[str, object]]] = defaultdict(list)
            for record in sk.read_events(root):
                grouped[str(record["customer_id"])].append(record)
            return {cid: event_digest(rows) for cid, rows in grouped.items()}

        plain = self.start(customers=6)
        api.advance(3)
        api.advance(5)
        treated = self.start(customers=6)
        middle = api.advance(3).end
        api.apply_treatment({"C00000001": "T1", "C00000004": "T2", "C00000005": "T0"})
        api.advance(5)
        before, after = by_customer(plain), by_customer(treated)
        for cid in sorted(set(before) | set(after)):
            with self.subTest(customer=cid):
                if cid in ("C00000001", "C00000004"):
                    self.assertNotEqual(before.get(cid), after.get(cid))
                else:
                    self.assertEqual(before.get(cid), after.get(cid))
        stamp = middle.isoformat(timespec="milliseconds")
        exposures = sorted(
            (r["customer_id"], r["event_type"], r["treatment_id"], r["timestamp"])
            for r in sk.read_events(treated)
            if r["event_type"] in ("campaign_exposed", "push_sent", "coupon_exposed")
        )
        self.assertEqual([
            ("C00000001", "campaign_exposed", "T1", stamp),
            ("C00000001", "push_sent", "T1", stamp),
            ("C00000004", "campaign_exposed", "T2", stamp),
            ("C00000004", "coupon_exposed", "T2", stamp),
            ("C00000004", "push_sent", "T2", stamp),
        ], exposures)


class TestMetricsAndBundle(SimulatorCase):
    def setUp(self) -> None:
        super().setUp()
        self.root = self.start(customers=12)
        self.summary = api.advance(10)

    def test_counts_match_events_and_unproduced_types_are_not_run(self) -> None:
        start, end = self.summary.start + timedelta(days=2), self.summary.end - timedelta(days=3)
        values = api.metrics(start, end)
        window = [r for r in sk.read_events(self.root)
                  if start.isoformat(timespec="milliseconds") <= r["timestamp"]
                  < end.isoformat(timespec="milliseconds")]
        self.assertEqual(sc.MetricStatus.OK, values["events_total"].status)
        self.assertEqual(len(window), values["events_total"].value)
        for event_type in sc.EventType:
            value = values[f"events.{event_type.value}"]
            with self.subTest(event_type=event_type.value):
                if event_type.value in PRODUCED:
                    self.assertEqual(sc.MetricStatus.OK, value.status)
                    self.assertEqual(
                        sum(1 for r in window if r["event_type"] == event_type.value), value.value
                    )
                else:
                    self.assertEqual(sc.MetricStatus.NOT_RUN, value.status)
                    self.assertEqual(sc.ReasonCode.PRECONDITION_MISSING, value.reason_code)
                    self.assertIsNone(value.value)
        for name in ("churn_rate", "revenue", "contribution_profit", "marketing_cost"):
            with self.subTest(metric=name):
                self.assertEqual(sc.MetricStatus.NOT_RUN, values[name].status)
                self.assertIsNone(values[name].value)

    def test_empty_window_is_a_measured_zero_for_produced_types(self) -> None:
        values = api.metrics(self.summary.end, self.summary.end)
        self.assertEqual(0, values["events_total"].value)
        self.assertEqual(sc.MetricStatus.OK, values["events.session_start"].status)
        self.assertEqual(0, values["events.session_start"].value)

    def test_exchange_bundle_follows_contract_v1_and_matches_purchase_events(self) -> None:
        from src.measurement import exchange as ex

        bundle = api.exchange_bundle(self.summary.end)
        self.assertEqual("ok", bundle["status"])
        target = Path(str(bundle["path"]))
        self.assertEqual(self.root.resolve().parent / "simulator_exchange", target)
        loaded = ex.read_exchange(target, sk.EventSource.SIMULATOR)
        self.assertIsNotNone(loaded)
        purchases = {
            r["order_id"]: r["order_amount"] for r in sk.read_events(self.root)
            if r["event_type"] == "purchase"
        }
        orders = [
            json.loads(line)
            for line in (target / "orders.jsonl").read_text(encoding="utf-8").splitlines()
        ]
        self.assertEqual(bundle["orders"], len(orders))
        self.assertEqual(purchases, {o["order_id"]: o["order_amount"] for o in orders})
        items: dict[str, int] = defaultdict(int)
        for line in (target / "order_items.jsonl").read_text(encoding="utf-8").splitlines():
            item = json.loads(line)
            self.assertIsNotNone(item["unit_cost"])
            items[item["order_id"]] += item["unit_price"] * item["quantity"]
        for order in orders:
            with self.subTest(order=order["order_id"]):
                self.assertEqual(order["order_amount"], items[order["order_id"]] - order["discount"])
                expected_fee = 3000 if items[order["order_id"]] < 40000 else 0
                self.assertEqual(expected_fee, order["shipping_fee"])

    def test_exchange_bundle_carries_no_hidden_values(self) -> None:
        bundle = api.exchange_bundle(self.summary.end)
        text = "".join(
            path.read_text(encoding="utf-8") for path in sorted(Path(str(bundle["path"])).iterdir())
        )
        self.assertNotIn("treatment_id", text)
        for name in sc.FORBIDDEN_FIELD_NAMES:
            self.assertNotIn(f'"{name}"', text)

    def test_public_returns_carry_no_hidden_field_names(self) -> None:
        names: set[str] = set(f.name for f in dataclasses.fields(api.RunSummary))
        names |= set(api.metrics(self.summary.start, self.summary.end))
        names |= set(api.exchange_bundle(self.summary.end))
        for record in api.events(self.summary.end):
            names |= set(record)
        tokens = [api.snapshot(), api.save_state(), str(self.summary.run_id)]
        self.assertEqual(set(), names & sc.FORBIDDEN_FIELD_NAMES)
        for token in tokens:
            self.assertNotIn(str(self.hidden), token)
            self.assertFalse(any(name in token for name in sc.FORBIDDEN_FIELD_NAMES), token)

    def test_package_reexports_only_api(self) -> None:
        self.assertEqual(["api"], src.simulator.__all__)


class TestNoWallClockOrNondeterminism(unittest.TestCase):
    def test_simulator_sources_use_no_clock_os_randomness_or_floats(self) -> None:
        files = sorted(SIMULATOR_DIR.rglob("*.py"))
        self.assertGreater(len(files), 5)
        findings: list[str] = []
        for path in files:
            findings += nondeterminism_findings(
                path.read_text(encoding="utf-8"), str(path.relative_to(REPO_ROOT))
            )
        self.assertEqual([], findings)

    def test_scan_catches_planted_violations(self) -> None:
        planted = (
            "import random\nimport time\nimport importlib\nfrom datetime import datetime\n"
            "a = time.time()\nb = datetime.now()\nc = hash('x')\nd = 0.5\ne = 1 / 2\n"
            "f = (1).to_bytes(8)\ng = int.from_bytes(b'x')\nh = sum([1])\ni = __import__('os')\n"
            "for p in root.glob('*'):\n    pass\nj = os.listdir('.')\nk = sorted(root.rglob('*'))\n"
            "m = any(root.iterdir())\n"
        )
        findings = nondeterminism_findings(planted, "planted")
        for expected in ("import random", "import time", "import importlib", ".time", ".now",
                         "hash()", "float 0.5", "Div", "to_bytes", "from_bytes", "sum()",
                         "__import__()", "정렬 없는 glob", "정렬 없는 listdir"):
            with self.subTest(expected=expected):
                self.assertTrue(any(expected in f for f in findings), findings)
        self.assertFalse(any("rglob" in f or "iterdir" in f for f in findings), findings)

    def test_simulator_sources_never_mention_the_results_path(self) -> None:
        offenders = [
            str(path.relative_to(REPO_ROOT)) for path in SIMULATOR_DIR.rglob("*.py")
            if "results/" in path.read_text(encoding="utf-8")
        ]
        self.assertEqual([], offenders)


class TestContractDocumentMatchesApi(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.text = CONTRACT_DOC.read_text(encoding="utf-8")

    def test_function_list_and_signatures_match(self) -> None:
        documented = sorted(
            line.strip() for line in self.text.splitlines() if line.startswith("def ")
        )
        actual = sorted(render(f) for f in public_functions().values())
        self.assertEqual(actual, documented)
        self.assertEqual(11, len(actual))

    def test_exception_hierarchy_matches(self) -> None:
        documented = dict(re.findall(r"^class (\w+)\((\w+)\)$", self.text, flags=re.MULTILINE))
        self.assertEqual(public_exceptions(), documented)

    def test_run_summary_fields_match(self) -> None:
        block = self.text.split("class RunSummary:", 1)[1].split("```", 1)[0]
        documented = re.findall(r"^    (\w+): (.+)$", block, flags=re.MULTILINE)
        actual = [(f.name, str(f.type)) for f in dataclasses.fields(api.RunSummary)]
        self.assertEqual(actual, documented)

    def test_public_names_are_exactly_the_documented_contract(self) -> None:
        documented = set(re.findall(r"^def (\w+)\(", self.text, flags=re.MULTILINE))
        documented |= set(re.findall(r"^class (\w+)", self.text, flags=re.MULTILINE))
        public = {
            name for name, value in vars(api).items()
            if not name.startswith("_") and value is not __future__.annotations
        }
        self.assertEqual(documented, public)
        self.assertEqual(sorted(documented), sorted(api.__all__))
        self.assertEqual(len(api.__all__), len(set(api.__all__)))
        for internal in ("runtime", "wd", "engine", "storage", "behavior", "lineage", "world"):
            with self.subTest(name=internal):
                self.assertFalse(hasattr(api, internal))

    def test_cli_section_matches_the_parser(self) -> None:
        documented: dict[str, list[str]] = {}
        for line in self.text.splitlines():
            match = re.match(r"^python -m src\.simulator (\w+) (.*)$", line)
            if match:
                documented[match.group(1)] = sorted(set(re.findall(r"--[\w-]+", match.group(2))))
        commands = next(
            action for action in cli._parser()._actions
            if isinstance(action, argparse._SubParsersAction)
        )
        actual = {
            name: sorted(
                option for action in parser._actions for option in action.option_strings
                if option.startswith("--") and option != "--help"
            )
            for name, parser in commands.choices.items()
        }
        self.assertEqual(actual, documented)
        codes = {int(code) for code in re.findall(r"^\| `(\d)` \|", self.text, flags=re.MULTILINE)}
        self.assertEqual({cli.EXIT_OK, cli.EXIT_SIMULATOR_ERROR, cli.EXIT_BAD_ARGUMENT}, codes)

    def test_every_public_function_is_described(self) -> None:
        for name in public_functions():
            with self.subTest(function=name):
                self.assertIn(f"| `{name}` |", self.text)

    def test_document_carries_no_generation_rules(self) -> None:
        for word in ("만료", "30일", "장바구니", "sim-rng", "sha256", "확률", "분포", "persona"):
            with self.subTest(word=word):
                self.assertNotIn(word, self.text)


if __name__ == "__main__":
    unittest.main()
