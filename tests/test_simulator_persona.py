"""S2 생성 config·페르소나·Trait 생성의 계약 검사 (#76).

- 로더: 정수만, 중복 키·미지 키 거부, 구성비 합 10000, 6종 이상, 수치 엔진이 검증한 모수 범위.
- 생성 성질: 같은 seed → 같은 정체, 고객을 추가해도 기존 고객 불변, profile 무관, Trait 사이 독립.
- 결속: config 가 바뀌면 옛 상태·계보·실행 중 세계가 명시 오류로 멈춘다. 판 관리는 CONFIG_PINS.
- 대조: Trait 이름이 측정 계약 이름과 겹치지 않고, `docs/persona_spec.md` 의 모수 표가 config 와 같다.

분포 자체의 정합성은 `tests/test_simulator_trait_distribution.py` 가 본다.
"""

from __future__ import annotations

import copy
import json
import unittest
from unittest import mock

from src.measurement import kpi
from src.measurement import schema as sc
from src.simulator import api
from src.simulator._internal import clock, genconfig, persona, rng, traits
from src.simulator._internal import world as world_state
from tests.test_isolation import SRS_HIDDEN_TRAITS
from tests.test_simulator_support import REPO_ROOT, SimulatorCase

try:
    import yaml
except ImportError:  # 의존성 없는 잡(isolation·python-compat)에서는 대조만 건너뛴다
    yaml = None

SPEC_DOC = REPO_ROOT / "docs" / "persona_spec.md"
CONFIG_TEXT = genconfig.CONFIG_PATH.read_text(encoding="utf-8")

# config_version → 생성 부분 다이제스트. 생성 부분을 바꾸면 config_version 을 올리고 여기에 줄을 더한다.
# 지난 판은 지우지 않는다 — 같은 판 이름에 다른 내용이 실리는 것을 막는 기록이다.
CONFIG_PINS: dict[str, str] = {
    "sim-gen-v1": "e150e434d1abef461b9491f1e70f0902f83c4ef999d108a04e0e85bd79c19ccc",
    "sim-gen-v2": "49bfe06b2edaa9d45ca653d98175d7458b90e7707dca1d00f57a28f9e4d4006d",
    "sim-gen-v3": "66588097846aa9914aa57f62034a4d2d05bbe8cc66b2a01e3a89040b55df1157",
}


def document() -> dict[str, object]:
    return json.loads(CONFIG_TEXT)


def text_of(doc: dict[str, object]) -> str:
    return json.dumps(doc, ensure_ascii=False, indent=2)


def trait_entry(doc: dict[str, object], name: str) -> dict[str, object]:
    return next(t for t in doc["hidden_traits"] if t["name"] == name)


def variant(edit) -> genconfig.GenerationConfig:
    doc = document()
    edit(doc)
    return genconfig.parse(text_of(doc))


def identities(world: dict[str, object]) -> list[tuple[str, str, dict[str, int]]]:
    return [(c["customer_id"], c["persona"], c["hidden_traits"]) for c in world["customers"]]


class TestCurrentConfig(unittest.TestCase):
    def test_config_is_the_srs_16_traits_and_six_personas(self) -> None:
        config = genconfig.active()
        self.assertEqual(sorted(SRS_HIDDEN_TRAITS), sorted(config.trait_names))
        self.assertEqual(
            ("vip_loyal", "loyal", "price_sensitive", "explorer", "churn_progressing", "new_customer"),
            config.persona_ids,
        )
        self.assertEqual(("P1", "P2", "P3", "P4", "P5", "P6"), tuple(p.alias for p in config.personas))
        self.assertEqual((800, 2700, 2200, 1800, 1500, 1000), config.ratios)

    def test_config_version_is_pinned_to_its_content(self) -> None:
        config = genconfig.active()
        self.assertIn(
            config.version, CONFIG_PINS,
            "생성 부분을 바꿨다면 config_version 을 올리고 CONFIG_PINS 에 새 다이제스트를 추가한다",
        )
        self.assertEqual(
            CONFIG_PINS[config.version], config.digest,
            f"{config.version} 의 내용이 바뀌었다 — config_version 을 올린다",
        )

    def test_digest_covers_only_the_generation_part(self) -> None:
        base = genconfig.active().digest
        reordered = json.dumps(dict(reversed(list(document().items()))), ensure_ascii=False)
        self.assertEqual(base, genconfig.parse(reordered).digest)
        self.assertEqual(base, variant(lambda d: d.__setitem__("notes", ["다른 설명"])).digest)
        self.assertEqual(base, variant(lambda d: d.pop("notes")).digest)
        changed = variant(lambda d: trait_entry(d, "coupon_sensitivity")["mu_ppm"].__setitem__("loyal", 410000))
        self.assertNotEqual(base, changed.digest)


class TestLoaderRejects(unittest.TestCase):
    def assert_rejected(self, text: str, fragment: str = "") -> None:
        with self.assertRaises(genconfig.ConfigError) as caught:
            genconfig.parse(text)
        self.assertIn(fragment, str(caught.exception))

    def assert_edit_rejected(self, edit, fragment: str = "") -> None:
        doc = document()
        edit(doc)
        self.assert_rejected(text_of(doc), fragment)

    def test_non_integer_numbers(self) -> None:
        self.assert_rejected(CONFIG_TEXT.replace('"ratio_bp": 800', '"ratio_bp": 800.0', 1), "소수")
        self.assert_rejected(CONFIG_TEXT.replace('"ratio_bp": 800', '"ratio_bp": 8e2', 1), "소수")
        self.assert_rejected(CONFIG_TEXT.replace('"ratio_bp": 800', '"ratio_bp": NaN', 1), "NaN")
        self.assert_rejected(CONFIG_TEXT.replace('"ratio_bp": 800', '"ratio_bp": Infinity', 1))
        self.assert_edit_rejected(lambda d: d["personas"][0].__setitem__("ratio_bp", True), "정수")
        self.assert_edit_rejected(
            lambda d: trait_entry(d, "base_order_value")["median"].__setitem__("loyal", "48000"), "정수"
        )

    def test_duplicate_keys_anywhere(self) -> None:
        self.assert_rejected(
            CONFIG_TEXT.replace('"alias": "P1",', '"alias": "P1", "alias": "P1",', 1), "중복 키"
        )
        self.assert_rejected('{"config_version": "a", "config_version": "b"}', "중복 키")

    def test_ratio_and_persona_rules(self) -> None:
        self.assert_edit_rejected(lambda d: d["personas"][0].__setitem__("ratio_bp", 801), "10000")
        self.assert_edit_rejected(lambda d: d["personas"].pop(), "최소 6")
        self.assert_edit_rejected(lambda d: d["personas"][1].__setitem__("id", "vip_loyal"), "겹친다")
        self.assert_edit_rejected(lambda d: d["personas"][1].__setitem__("alias", "P1"), "겹친다")
        self.assert_edit_rejected(lambda d: d["personas"][0].__setitem__("id", "VIP"), "형식")
        self.assert_edit_rejected(lambda d: d["personas"][0].__setitem__("ratio_bp", 0), "범위")

    def test_unknown_or_missing_keys(self) -> None:
        self.assert_edit_rejected(lambda d: d.__setitem__("simulation", {}), "모르는 키")
        self.assert_edit_rejected(lambda d: d.pop("hidden_traits"), "없는 키")
        self.assert_edit_rejected(lambda d: d["personas"][0].__setitem__("label", "x"), "모르는 키")
        self.assert_edit_rejected(lambda d: d["hidden_traits"][1].__setitem__("sigma_ppm", 1), "모르는 키")
        self.assert_edit_rejected(
            lambda d: trait_entry(d, "price_sensitivity")["mu_ppm"].pop("explorer"), "없는 키"
        )
        self.assert_edit_rejected(
            lambda d: trait_entry(d, "price_sensitivity")["mu_ppm"].__setitem__("ghost", 1), "모르는 키"
        )

    def test_trait_rules(self) -> None:
        self.assert_edit_rejected(lambda d: d["hidden_traits"][1].__setitem__("family", "uniform"), "family")
        self.assert_edit_rejected(lambda d: d["hidden_traits"][1].__setitem__("unit", "krw"), "unit")
        self.assert_edit_rejected(lambda d: d["hidden_traits"].append(copy.deepcopy(d["hidden_traits"][1])), "겹친다")
        self.assert_edit_rejected(lambda d: d.__setitem__("hidden_traits", []), "비지 않은")
        mu = lambda pid, value: lambda d: trait_entry(d, "marketing_fatigue")["mu_ppm"].__setitem__(pid, value)  # noqa: E731
        self.assert_edit_rejected(mu("loyal", 0), "범위")
        self.assert_edit_rejected(mu("loyal", 1_000_000), "범위")
        # κ=12 에서 μ=0.02 이면 α=0.24 — 수치 엔진이 검증한 범위(α ≥ 0.3) 밖이다.
        self.assert_edit_rejected(mu("loyal", 20_000), "검증 범위")
        self.assert_edit_rejected(
            lambda d: trait_entry(d, "base_visit_frequency").__setitem__("shape_milli", 500), "범위"
        )

    def test_not_json(self) -> None:
        self.assert_rejected("config_version: sim-gen-v1\n", "JSON")
        self.assert_rejected("[]", "최상위")

    def test_parser_limits_are_config_errors_not_value_errors(self) -> None:
        # int 변환 자릿수 한계(4300자리)는 json 안에서 ValueError 로 난다. 공개 경계에서 "인자 범위 밖"
        # ValueError 나 "상태 손상"으로 잘못 분류되지 않게 ConfigError 로 감싼다.
        huge = CONFIG_TEXT.replace('"ratio_bp": 800', '"ratio_bp": ' + "9" * 5000, 1)
        self.assert_rejected(huge, "JSON")

    def test_scales_below_the_unit_resolution_floor(self) -> None:
        # 중앙값·평균이 1000 단위보다 작으면 값이 몇 개 정수로 뭉개진다(정확도 관문이 잡지 못한다).
        floor = genconfig.MIN_SCALE_VALUE
        self.assert_edit_rejected(
            lambda d: trait_entry(d, "base_order_value")["median"].__setitem__("loyal", floor - 1), "범위"
        )
        self.assert_edit_rejected(
            lambda d: trait_entry(d, "base_visit_frequency")["mean"].__setitem__("loyal", 1), "범위"
        )
        variant(lambda d: trait_entry(d, "base_visit_frequency")["mean"].__setitem__("loyal", floor))

    def test_spread_below_the_unit_resolution_floor(self) -> None:
        # 척도가 충분해도 σ·k 가 작으면 값이 몇 개 정수로 뭉개진다(σ = 1 ppm 이면 전원 같은 값).
        # LogNormal σ·중앙값, Gamma 평균/√k 가 100 단위 이상이어야 한다.
        self.assert_edit_rejected(
            lambda d: trait_entry(d, "purchase_cycle").__setitem__("sigma_ppm", 1), "퍼짐"
        )
        # purchase_cycle P1 중앙값 6000: σ·6000 ≥ 100 ⇔ σ ≥ 0.016667 → 16667 ppm 이 경계다
        self.assert_edit_rejected(
            lambda d: trait_entry(d, "purchase_cycle").__setitem__("sigma_ppm", 16_666), "퍼짐"
        )
        variant(lambda d: trait_entry(d, "purchase_cycle").__setitem__("sigma_ppm", 16_667))
        # Gamma 는 지금 범위(k ≤ 100, 평균 ≥ 1000)에서는 평균/√k ≥ 100 이 늘 성립한다. 경계(k=100, 평균 1000)를
        # 받는지와, 범위를 넓혔을 때를 대비한 검사 자체가 동작하는지를 본다.
        def edge(d: dict[str, object]) -> None:
            entry = trait_entry(d, "base_visit_frequency")
            entry["shape_milli"] = 100_000
            entry["mean"] = {pid: 1000 for pid in entry["mean"]}

        variant(edge)
        with self.assertRaisesRegex(genconfig.ConfigError, "퍼짐"):
            genconfig._check_spread("t", "gamma", 100_000, {"p": 999})


class TestYamlReadsTheSameDocument(unittest.TestCase):
    @unittest.skipUnless(yaml, "PyYAML 미설치 — config 의 YAML·JSON 동등성 대조를 건너뛴다")
    def test_yaml_and_json_parsers_agree(self) -> None:
        self.assertEqual(json.loads(CONFIG_TEXT), yaml.safe_load(CONFIG_TEXT))


class TestGenerationProperties(unittest.TestCase):
    def test_same_seed_gives_the_same_identities(self) -> None:
        first = identities(world_state.new_world(9, 30, "smoke"))
        self.assertEqual(first, identities(world_state.new_world(9, 30, "smoke")))
        self.assertNotEqual(first, identities(world_state.new_world(10, 30, "smoke")))

    def test_adding_customers_leaves_existing_identities_unchanged(self) -> None:
        small = identities(world_state.new_world(9, 15, "smoke"))
        large = identities(world_state.new_world(9, 16, "smoke"))
        self.assertEqual(small, large[:15])

    def test_profile_does_not_change_the_population(self) -> None:
        reference = identities(world_state.new_world(9, 20, "smoke"))
        for profile in ("short", "reference", "long", "rolling"):
            with self.subTest(profile=profile):
                self.assertEqual(reference, identities(world_state.new_world(9, 20, profile)))

    def test_changing_one_trait_parameter_changes_only_that_trait(self) -> None:
        base = genconfig.active()
        changed = variant(lambda d: trait_entry(d, "coupon_sensitivity").__setitem__("kappa_milli", 9600))
        moved = 0
        for index in range(60):
            cid = world_state.customer_id(index)
            p0, t0 = persona.generate(3, cid, base)
            p1, t1 = persona.generate(3, cid, changed)
            self.assertEqual(p0, p1)
            others = {k: v for k, v in t0.items() if k != "coupon_sensitivity"}
            self.assertEqual(others, {k: v for k, v in t1.items() if k != "coupon_sensitivity"})
            moved += t0["coupon_sensitivity"] != t1["coupon_sensitivity"]
        self.assertGreater(moved, 50)

    def test_raising_a_mean_moves_the_same_customers_monotonically(self) -> None:
        # 같은 고객은 같은 u 를 쓰므로 μ 를 올리면 값이 줄지 않는다 — S6 짝지은 민감도 분석의 전제다.
        base = genconfig.active()
        raised = variant(lambda d: trait_entry(d, "coupon_sensitivity")["mu_ppm"].__setitem__("price_sensitive", 900000))
        seen = 0
        for index in range(200):
            cid = world_state.customer_id(index)
            p0, t0 = persona.generate(4, cid, base)
            if p0 != "price_sensitive":
                continue
            seen += 1
            self.assertGreaterEqual(persona.generate(4, cid, raised)[1]["coupon_sensitivity"], t0["coupon_sensitivity"])
        self.assertGreater(seen, 20)

    def test_changing_a_ratio_moves_only_boundary_customers_and_keeps_their_draws(self) -> None:
        base = genconfig.active()

        def shift(d: dict[str, object]) -> None:
            d["personas"][4]["ratio_bp"] += 300  # P5 ×1.2
            d["personas"][1]["ratio_bp"] -= 300

        shifted = variant(shift)
        changed = 0
        for index in range(300):
            cid = world_state.customer_id(index)
            p0, t0 = persona.generate(5, cid, base)
            p1, t1 = persona.generate(5, cid, shifted)
            if p0 == p1:
                self.assertEqual(t0, t1)
            else:
                changed += 1
        self.assertGreater(changed, 0)
        self.assertLess(changed, 60)



class TestSignupSchedule(unittest.TestCase):
    """S3(#77) 가입일 — `DR-S3-p6-signup` U10."""

    @staticmethod
    def signup_days(world: dict[str, object]) -> dict[str, int]:
        start = world["calendar_start_ms"]
        return {c["customer_id"]: (c["signup_ms"] - start) // clock.DAY_MS for c in world["customers"]}

    def test_only_the_scheduled_persona_joins_late_and_inside_its_range(self) -> None:
        config = genconfig.active()
        spans = {p.id: p.signup_day_range for p in config.personas}
        scheduled = [pid for pid, span in spans.items() if span is not None]
        self.assertEqual(1, len(scheduled), "가입 일정이 있는 페르소나는 신규가입 하나다")
        self.assertEqual((1, 273), spans[scheduled[0]])
        world = world_state.new_world(7, 3000, "reference")
        days = self.signup_days(world)
        late = []
        for customer in world["customers"]:
            day = days[customer["customer_id"]]
            if customer["persona"] in scheduled:
                self.assertTrue(1 <= day <= 272, day)
                late.append(day)
            else:
                self.assertEqual(0, day)
        # 균등 [1, 272]: n≈300 이면 양 끝 3분위에 모두 들어온다(한쪽이 비면 범위 해석 오류).
        self.assertGreater(len(late), 200)
        self.assertTrue(any(d <= 90 for d in late) and any(d >= 182 for d in late))

    def test_signup_day_does_not_depend_on_profile_or_population_size(self) -> None:
        base = self.signup_days(world_state.new_world(11, 400, "smoke"))
        for profile in ("small", "reference", "rolling"):
            with self.subTest(profile=profile):
                self.assertEqual(base, self.signup_days(world_state.new_world(11, 400, profile)))
        larger = self.signup_days(world_state.new_world(11, 401, "smoke"))
        self.assertEqual(base, {cid: d for cid, d in larger.items() if cid in base})

    def test_no_event_before_signup(self) -> None:
        from src.simulator._internal import engine
        world = world_state.new_world(3, 300, "smoke")
        signup = {c["customer_id"]: clock.timestamp(c["signup_ms"]) for c in world["customers"]}
        records = list(engine.run(world, world["calendar_start_ms"] + 60 * clock.DAY_MS))
        self.assertTrue(records)
        # 타임스탬프는 같은 +09:00 고정 폭 문자열이라 사전순이 시간순이다.
        self.assertEqual([], [r for r in records if r["timestamp"] < signup[r["customer_id"]]])
        late = {cid for cid, ts in signup.items() if ts > clock.timestamp(world["calendar_start_ms"])}
        self.assertTrue(late, "60일 창에 아직 가입하지 않은 고객이 있어야 검사가 의미 있다")

    def test_loader_rejects_malformed_ranges(self) -> None:
        def with_range(value):
            def edit(doc):
                doc["personas"][0]["signup_day_range"] = value
            return edit
        cases = [[1], [5, 5], [6, 5], [-1, 3], [1.0, 3], [True, 3], "1-3", [0, genconfig.MAX_SIGNUP_DAY + 1]]
        for value in cases:
            with self.subTest(value=value):
                doc = document()
                with_range(value)(doc)
                with self.assertRaises(genconfig.ConfigError):
                    genconfig.parse(text_of(doc))


class TestNamesDoNotCollideWithTheMeasurementContract(unittest.TestCase):
    def test_trait_names_are_not_event_fields_or_metric_names(self) -> None:
        names = set(genconfig.active().trait_names)
        self.assertEqual(set(), names & {f.name for f in sc.EVENT_FIELDS})
        self.assertEqual(set(), names & {m.name for m in kpi.METRIC_SPECS})
        self.assertNotIn("average_order_value", names)


def _cells(line: str) -> list[str]:
    return [cell.strip() for cell in line.strip().strip("|").split("|")]


def _marked_table(text: str, tag: str) -> tuple[list[str], list[list[str]]]:
    start, end = f"<!-- config:{tag} -->", f"<!-- /config:{tag} -->"
    block = text.split(start, 1)[1].split(end, 1)[0]
    rows = [line for line in block.splitlines() if line.startswith("|")]
    return _cells(rows[0]), [_cells(line) for line in rows[2:]]


class TestSpecDocumentMatchesConfig(unittest.TestCase):
    """`docs/persona_spec.md` 의 표지 사이 표가 config 와 같은지 — 문서와 config 의 드리프트 가드."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.text = SPEC_DOC.read_text(encoding="utf-8")
        cls.config = genconfig.active()

    def test_persona_table(self) -> None:
        _, rows = _marked_table(self.text, "personas")
        documented = [(r[0], r[1].strip("`"), int(r[3])) for r in rows]
        self.assertEqual([(p.alias, p.id, p.ratio_bp) for p in self.config.personas], documented)

    def test_trait_parameter_table(self) -> None:
        header, rows = _marked_table(self.text, "hidden_traits")
        aliases = header[4:]
        by_alias = {p.alias: p.id for p in self.config.personas}
        self.assertEqual([p.alias for p in self.config.personas], aliases)
        documented = {}
        for row in rows:
            key, value = row[2].split()
            documented[row[0].strip("`")] = (
                row[1], key, int(value), row[3],
                {by_alias[a]: int(v) for a, v in zip(aliases, row[4:])},
            )
        actual = {
            t.name: (t.family, genconfig.FAMILIES[t.family].shape_key, t.shape, t.unit, dict(t.by_persona))
            for t in self.config.traits
        }
        self.assertEqual(actual, documented)

    def test_document_names_the_config_version_and_digest(self) -> None:
        self.assertIn(f"`{self.config.version}`", self.text)
        self.assertIn(self.config.digest, self.text)


class TestConfigBinding(SimulatorCase):
    """config 가 바뀌면 옛 상태·계보를 조용히 다른 결과로 읽지 않는다."""

    def other_config(self) -> genconfig.GenerationConfig:
        def edit(d: dict[str, object]) -> None:
            d["config_version"] = "sim-gen-test"
            trait_entry(d, "marketing_fatigue")["mu_ppm"]["churn_progressing"] = 600000

        return variant(edit)

    def test_state_saved_under_another_config_is_refused(self) -> None:
        self.start(customers=6)
        api.advance(2)
        state_id = api.save_state()
        with mock.patch.object(genconfig, "_ACTIVE", self.other_config()):
            with self.assertRaisesRegex(api.StateFormatError, "generation"):
                api.load_state(state_id, self.fresh_root("load"), hidden_root=self.hidden)
        api.load_state(state_id, self.fresh_root("load"), hidden_root=self.hidden)

    def test_running_world_stops_when_the_config_changes_under_it(self) -> None:
        self.start(customers=6)
        summary = api.advance(2)
        with mock.patch.object(genconfig, "_ACTIVE", self.other_config()):
            with self.assertRaisesRegex(api.OutputRootError, "생성 설정"):
                api.advance(1)
            with self.assertRaisesRegex(api.OutputRootError, "생성 설정"):
                list(api.events(summary.end))
        api.advance(1)  # 원래 config 로 돌아오면 같은 세계가 이어서 진행된다

    def test_same_version_with_other_content_names_both_digests(self) -> None:
        self.start(customers=4)
        api.advance(1)
        state_id = api.save_state()
        same_version = variant(lambda d: trait_entry(d, "marketing_fatigue")["mu_ppm"].__setitem__("loyal", 260000))
        self.assertEqual(genconfig.active().version, same_version.version)
        with mock.patch.object(genconfig, "_ACTIVE", same_version):
            with self.assertRaises(api.StateFormatError) as caught:
                api.load_state(state_id, self.fresh_root("load"), hidden_root=self.hidden)
        message = str(caught.exception)
        self.assertIn(same_version.digest[:12], message)
        self.assertIn(genconfig.active().digest[:12], message)

    def test_config_change_without_lineage_is_a_public_error(self) -> None:
        # 계보가 아직 없는 세계(advance 전)는 계보 대조를 거치지 않고 상태 재적재에서 걸린다.
        # 그때도 내부 IncompatibleState 가 아니라 공개 SimulatorError 여야 한다.
        self.start(customers=4)
        snap = api.snapshot()
        with mock.patch.object(genconfig, "_ACTIVE", self.other_config()):
            for call in (lambda: api.advance(1), lambda: api.restore(snap, output_root=self.fresh_root("r"))):
                with self.assertRaises(api.SimulatorError) as caught:
                    call()
                self.assertNotIsInstance(caught.exception, world_state.IncompatibleState)
                self.assertIn("생성 설정", str(caught.exception))
        api.advance(1)

    def test_config_error_details_stay_in_the_cause(self) -> None:
        # 공개 메시지에는 숨은 필드 이름·페르소나 id 를 싣지 않고, 자세한 사유는 __cause__ 에 둔다.
        broken = self.tmp / "broken.yaml"
        doc = document()
        trait_entry(doc, "marketing_fatigue")["mu_ppm"]["churn_progressing"] = 0
        broken.write_text(text_of(doc), encoding="utf-8")
        with mock.patch.object(genconfig, "_ACTIVE", None), mock.patch.object(genconfig, "CONFIG_PATH", broken):
            with self.assertRaises(api.SimulatorError) as caught:
                api.init(1, 3, "smoke", self.fresh_root(), hidden_root=self.hidden)
        self.assertNotIn("marketing_fatigue", str(caught.exception))
        self.assertNotIn("churn_progressing", str(caught.exception))
        self.assertIn("marketing_fatigue", str(caught.exception.__cause__))

    def test_world_id_and_initial_digest_follow_the_config(self) -> None:
        before_id = world_state.current_world_id(7, 5, "smoke")
        before_digest = world_state.initial_digest(7, 5, "smoke")
        with mock.patch.object(genconfig, "_ACTIVE", self.other_config()):
            self.assertNotEqual(before_id, world_state.current_world_id(7, 5, "smoke"))
            self.assertNotEqual(before_digest, world_state.initial_digest(7, 5, "smoke"))
        self.assertEqual(before_digest, world_state.initial_digest(7, 5, "smoke"))

    def test_unreadable_config_is_a_simulator_error_without_absolute_paths(self) -> None:
        missing = self.tmp / "nowhere" / "simulator_config.yaml"
        with mock.patch.object(genconfig, "_ACTIVE", None), mock.patch.object(genconfig, "CONFIG_PATH", missing):
            with self.assertRaises(api.SimulatorError) as caught:
                api.init(1, 3, "smoke", self.fresh_root(), hidden_root=self.hidden)
            self.assertNotIsInstance(caught.exception, api.StateFormatError)
            self.assertIn(genconfig.CONFIG_NAME, str(caught.exception))
            self.assertNotIn(str(self.tmp), str(caught.exception))
            self.assertNotIn(str(REPO_ROOT), str(caught.exception))

    def test_unreadable_config_refuses_load_state(self) -> None:
        self.start(customers=4)
        api.advance(1)
        state_id = api.save_state()
        broken = self.tmp / "broken.yaml"
        broken.write_text(CONFIG_TEXT.replace('"ratio_bp": 800', '"ratio_bp": 800.5', 1), encoding="utf-8")
        with mock.patch.object(genconfig, "_ACTIVE", None), mock.patch.object(genconfig, "CONFIG_PATH", broken):
            with self.assertRaisesRegex(api.StateFormatError, "생성 설정"):
                api.load_state(state_id, self.fresh_root("load"), hidden_root=self.hidden)


class TestStateCarriesTheIdentity(SimulatorCase):
    def test_saved_state_has_generation_and_identity_fields(self) -> None:
        self.start(seed=13, customers=8)
        document = self.state(api.save_state())
        config = genconfig.active()
        self.assertEqual({"config_version": config.version, "config_digest": config.digest}, document["generation"])
        expected = identities(world_state.new_world(13, 8, "smoke"))
        self.assertEqual(expected, identities(document))
        tables = traits.tables(config)
        for customer in document["customers"]:
            for name, value in customer["hidden_traits"].items():
                table = tables[name][customer["persona"]]
                self.assertTrue(table.lo <= value <= table.hi)

    def test_generation_streams_use_day_minus_one_and_their_own_purposes(self) -> None:
        config = genconfig.active()
        cid = "C00000001"
        index = rng.Stream(21, cid, "persona", -1).weighted(config.ratios)
        expected_persona = config.personas[index].id
        name = config.trait_names[0]
        table = traits.tables(config)[name][expected_persona]
        expected_value = traits.draw(rng.Stream(21, cid, "trait:" + name, -1), table)
        found_persona, values = persona.generate(21, cid, config)
        self.assertEqual(expected_persona, found_persona)
        self.assertEqual(expected_value, values[name])


if __name__ == "__main__":
    unittest.main()
