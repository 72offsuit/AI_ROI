"""Local review schemas are optional artifacts, never a provider acceptance test."""

from copy import deepcopy
from importlib.util import find_spec
import json
from pathlib import Path
import unittest

from src.decision.features.d1_serialization import D1ContractError, tlv

ROOT = Path(__file__).resolve().parents[1]
NAMES = tuple(f"D1-W0-{name}-contracts-20261021.schema.json" for name in ("common", "input", "output"))
AVAILABLE = all((ROOT / "plans" / name).is_file() for name in NAMES)
DEPENDENCIES = find_spec("jsonschema") is not None and find_spec("referencing") is not None
MAX = 2**63 - 1


def int64_nodes(value):
    if type(value) is dict:
        if value.get("type") == "integer" and value.get("maximum", 0) >= MAX - 1024:
            yield value
        for child in value.values():
            yield from int64_nodes(child)
    elif type(value) is list:
        for child in value:
            yield from int64_nodes(child)


class W0PrimitiveTests(unittest.TestCase):
    def test_Int64_TLV_limits_are_literal_and_overflow_is_rejected(self):
        self.assertEqual(tlv(MAX).hex(), "0200000000000000087fffffffffffffff")
        self.assertEqual(tlv(-(2**63)).hex(), "0200000000000000088000000000000000")
        for value in (MAX + 1, -(2**63) - 1):
            with self.subTest(value=value), self.assertRaisesRegex(D1ContractError, "integer outside Int64"):
                tlv(value)


@unittest.skipUnless(AVAILABLE, "BLOCKED: Git 제외된 로컬 W0 검토 계약 미제공")
class W0LiteralTests(unittest.TestCase):
    def test_every_Int64_bound_is_an_exact_JSON_integer(self):
        for name in NAMES:
            schema = json.loads((ROOT / "plans" / name).read_text())
            nodes = list(int64_nodes(schema))
            self.assertTrue(nodes, name)
            for index, node in enumerate(nodes):
                with self.subTest(file=name, node=index):
                    self.assertIs(type(node["maximum"]), int)
                    self.assertEqual(node["maximum"], MAX)


@unittest.skipUnless(AVAILABLE and DEPENDENCIES,
                     "BLOCKED: 로컬 W0 계약 미제공 또는 jsonschema/referencing 미설치")
class W0SchemaTests(unittest.TestCase):
    def setUp(self):
        from jsonschema import Draft202012Validator, FormatChecker
        from referencing import Registry, Resource

        self.schemas = [json.loads((ROOT / "plans" / name).read_text()) for name in NAMES]
        registry = Registry().with_resources((item["$id"], Resource.from_contents(item)) for item in self.schemas)
        self.registry = registry
        self.validators = {name: Draft202012Validator(schema, registry=registry, format_checker=FormatChecker())
                           for name, schema in zip(("input", "output"), self.schemas[1:])}
        self.examples = json.loads((ROOT / "plans/D1-W0-contract-examples-20261021.json").read_text())

    def test_schema_documents_are_well_formed(self):
        from jsonschema import Draft202012Validator

        for schema in self.schemas:
            Draft202012Validator.check_schema(schema)

    def test_each_Int64_field_accepts_max_and_rejects_max_plus_one(self):
        from jsonschema import Draft202012Validator

        for schema in self.schemas:
            for index, node in enumerate(int64_nodes(schema)):
                validator = Draft202012Validator(node)
                with self.subTest(schema=schema["$id"], node=index):
                    self.assertTrue(validator.is_valid(MAX - 1))
                    self.assertTrue(validator.is_valid(MAX))
                    self.assertFalse(validator.is_valid(MAX + 1))
                    self.assertFalse(validator.is_valid(True))

    def test_existing_shape_examples_keep_their_declared_expectations(self):
        for case in self.examples["cases"]:
            with self.subTest(case=case["id"]):
                self.assertEqual(self.validators[case["schema_family"]].is_valid(case["instance"]),
                                 case["expected"] == "accept")

    def test_semantic_plan_is_still_NOT_RUN_not_claimed_by_schema_acceptance(self):
        by_id = {case["id"]: case for case in self.examples["cases"]}
        for case in self.examples["semantic_plan_cases"]:
            base = by_id[case["base_case_id"]]
            instance = deepcopy(base["instance"])
            for change in case["assignments"]:
                parts = change["pointer"].split("/")[1:]
                target = instance
                for part in parts[:-1]:
                    target = target[int(part)] if type(target) is list else target[part]
                if type(target) is list:
                    target[int(parts[-1])] = change["value"]
                else:
                    target[parts[-1]] = change["value"]
            with self.subTest(case=case["id"]):
                self.assertEqual(case["execution"], "NOT_RUN")
                self.assertEqual(self.validators[base["schema_family"]].is_valid(instance),
                                 case["schema_expected"] == "accept")

    def test_new_synthetic_I03_and_sequence_projection_match_W0_shapes(self):
        from jsonschema import Draft202012Validator, FormatChecker
        from src.decision.features.d1_sequence_file import adapt_sequences
        from tests.test_feature_d1_evidence import SyntheticEvidenceFixture

        f = SyntheticEvidenceFixture()
        self.validators["input"].validate(f.envelope)
        raw, context = f.raw()
        rows = adapt_sequences(raw, contexts=(context,))
        validator = Draft202012Validator({"$ref": self.schemas[0]["$id"]+"#/$defs/SequenceRow"},
                                          registry=self.registry, format_checker=FormatChecker())
        for row in rows:
            validator.validate(dict(row, index_date=row["index_date"].isoformat()))
