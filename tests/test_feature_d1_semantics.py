from copy import deepcopy
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from src.decision.features import d1_semantics as s
from src.decision.features.d1_loader import load_bundle
from src.decision.features.d1_serialization import D1ContractError, semantic_hash
from tests.test_feature_d1_fixtures import Fixture, PARQUET_AVAILABLE


class PureScopeTests(unittest.TestCase):
    def test_scope_selection_runs_without_parquet(self):
        keys = [dict(entity_namespace="fixture", source="synthetic", customer_id=cid,
                     index_date="2026-10-20") for cid in ("a", "c")]
        split = dict(split_contract_version="fixture-split/1", role_definition_version="fixture-roles/1",
            split_policy=dict(version="fixture", method="fixture", seed=7, parameters={}),
            entity_assignments=[dict(**s.entity(key), role="Train") for key in keys],
            row_assignments=[dict(**key, consumer="D2", fit_phase="cv", fold_id="fold-1", role="Train",
                                  excluded=False, reason=None) for key in keys])
        for selection, expected in (("all_train_rows", {"a", "c"}), ("nonempty_sequences", {"a"})):
            with self.subTest(selection=selection):
                fit, _ = s.scopes(split, "D2", "cv", "fold-1", dict(input_definition=selection,
                                  target_definition=None), [keys[0]])
                self.assertEqual({row["customer_id"] for row in fit["rows"]}, expected)


@unittest.skipUnless(PARQUET_AVAILABLE, "BLOCKED: pyarrow 미설치 — Parquet 묶음 의미 hash 시험")
class SemanticTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.counter = 0

    def fixture(self, **kwargs):
        self.counter += 1
        return Fixture(Path(self.temp.name) / str(self.counter), **kwargs)

    def load(self, fixture):
        return load_bundle(fixture.root, "manifest.json", fixture.expected)

    def same_meaning(self, first, second):
        a, b = self.load(first), self.load(second)
        self.assertEqual((a.raw_bundle_semantic_hash, a.split_semantic_hash, a.view_semantic_hash, a.value_sha256),
                         (b.raw_bundle_semantic_hash, b.split_semantic_hash, b.view_semantic_hash, b.value_sha256))
        self.assertNotEqual(a.view_descriptor_sha256, b.view_descriptor_sha256)

    def test_V08_A_C_generated_at_only_entire_dependency_path(self):
        a = self.fixture()
        b = self.fixture(generation="2026-10-20T02:00:00Z")
        self.same_meaning(a, b)
        self.assertNotEqual(a.hash("raw-a/manifest.json"), b.hash("raw-a/manifest.json"))
        self.assertEqual(a.hash("objects/encoder.bin"), b.hash("objects/encoder.bin"))

    def test_V08_B_parquet_compression_and_physical_order(self):
        a, b = self.fixture(), self.fixture(compression="ZSTD", reverse=True)
        self.same_meaning(a, b)
        for name in ("raw-a/features.parquet", "raw-a/quality.parquet", "learned/features.parquet"):
            self.assertNotEqual(a.hash(name), b.hash(name))

    def test_V08_D_split_manifest_republication(self):
        a, b = self.fixture(), self.fixture(split_generation="2026-10-20T03:00:00Z", reverse=True)
        self.same_meaning(a, b)
        self.assertNotEqual(a.hash("split.json"), b.hash("split.json"))

    def test_V08_C_object_metadata_publication_is_not_object_identity(self):
        a, b = self.fixture(), self.fixture()
        b.amend("objects/encoder.json", lambda d: d.update(generated_at="2026-10-20T05:00:00Z"))
        b.refresh_physical()
        self.same_meaning(a, b)
        self.assertNotEqual(a.hash("objects/encoder.json"), b.hash("objects/encoder.json"))

    def test_V08_E_null_zero_and_actual_value(self):
        bundles = [self.load(self.fixture(value=value)) for value in (None, 0, 2)]
        for field in ("raw_bundle_semantic_hash", "view_semantic_hash"):
            self.assertEqual(len({getattr(bundle, field) for bundle in bundles}), 3)
        self.assertEqual(len({bundle.value_sha256["features"] for bundle in bundles}), 3)
        self.assertEqual(len({bundle.split_semantic_hash for bundle in bundles}), 1)

    def test_V08_F_dtype_is_part_of_schema_and_values(self):
        variants = [self.fixture(dtype=dtype) for dtype in ("Int64", "Float32", "Float64")]
        bundles = [self.load(fixture) for fixture in variants]
        self.assertEqual(len({fixture.sh for fixture in variants}), 3)
        self.assertEqual(len({bundle.raw_bundle_semantic_hash for bundle in bundles}), 3)
        self.assertEqual(len({bundle.view_semantic_hash for bundle in bundles}), 3)

    def test_V10_A_consumer_fold_and_actual_split_change(self):
        base = self.load(self.fixture())
        for kwargs in (dict(consumer="D3"), dict(fold="fold-2"), dict(swap=True)):
            with self.subTest(kwargs=kwargs):
                changed = self.load(self.fixture(**kwargs))
                self.assertEqual(base.raw_bundle_semantic_hash, changed.raw_bundle_semantic_hash)
                self.assertNotEqual(base.split_semantic_hash, changed.split_semantic_hash)
                self.assertNotEqual(base.view_semantic_hash, changed.view_semantic_hash)
                self.assertNotEqual(base.value_sha256, changed.value_sha256)

    def test_V10_C1_encoder_and_cluster_exact_bytes(self):
        base = self.load(self.fixture())
        for kwargs in (dict(encoder=b"RE-SERIALIZED-SYNTHETIC-ENCODER"),
                       dict(cluster=b"REFITTED-SYNTHETIC-CLUSTER")):
            with self.subTest(kwargs=kwargs):
                changed = self.load(self.fixture(**kwargs))
                self.assertEqual(base.raw_bundle_semantic_hash, changed.raw_bundle_semantic_hash)
                self.assertEqual(base.split_semantic_hash, changed.split_semantic_hash)
                self.assertNotEqual(base.view_semantic_hash, changed.view_semantic_hash)
                self.assertNotEqual(base.value_sha256, changed.value_sha256)

    def test_same_object_bytes_same_settings_do_not_erase_fit_facts(self):
        fixture = self.fixture()
        original = fixture.bindings["encoder"]
        for field, value in (("parameters", {"fixture_only": False}), ("seed", 8),
                             ("runtime", dict(python="other", libraries={}, serializer="opaque/1", options={}))):
            meta = deepcopy(fixture.metas["encoder"])
            meta["fit_facts"][field] = value
            altered = s.object_binding(meta, original["object_file_sha256"], [])
            self.assertNotEqual(semantic_hash("binding-test", original), semantic_hash("binding-test", altered))

    def test_V10_D_legal_transform_B_keeps_training_A(self):
        fixture = self.fixture(republish=True)
        loaded = self.load(fixture)
        self.assertNotEqual(fixture.raw_ref["file_sha256"], fixture.raw_a["file_sha256"])
        self.assertEqual(loaded.raw_bundle_semantic_hash, fixture.payload["raw_bundle_semantic_hash"])
        for meta in fixture.metas.values():
            self.assertEqual(meta["training_raw_parent"], fixture.raw_a)
        self.same_meaning(self.fixture(), fixture)

    def test_empty_complete_remains_null_after_transform(self):
        loaded = self.load(self.fixture(empty_test=True))
        row = next(row for row in loaded.rows["features"] if row["customer_id"] == "b")
        self.assertIsNone(row["F36"])
        self.assertIsNone(row["F37"])
        for quality in loaded.rows["quality"]:
            if quality["customer_id"] == "b" and quality["feature_id"] in ("F36", "F37"):
                self.assertEqual(quality["availability"], "unavailable")
                self.assertEqual(quality["reasons"], ["NO_SEQUENCE_INFORMATION"])

    def test_closed_projection_ignores_top_level_publication_but_rejects_nested_physical(self):
        fixture = self.fixture()
        policy = deepcopy(fixture.policy)
        policy.update(generated_at="changed", path="elsewhere", file_sha256="f" * 64)
        self.assertEqual(semantic_hash("policy", s.policy_body(policy)), fixture.ph)
        policy["cutoff"]["generated_at"] = "changed"
        with self.assertRaises(D1ContractError): s.policy_body(policy)
        with self.assertRaises(D1ContractError): s.policy_body({"policy_id": "missing"})
        for value in ({"host": "machine"}, {"nested": {"raw_manifest_sha256": "f" * 64}}):
            with self.assertRaises(D1ContractError): s.semantic_settings(value)

    def test_observation_instants_use_UTC_payload_not_display_timezone(self):
        fixture = self.fixture()
        evidence = deepcopy(fixture.evidence)
        evidence["claims"][0]["availability_basis"]["as_of"] = "2026-10-20T00:00:00+09:00"
        self.assertEqual(semantic_hash("observation-claims", s.evidence_body(evidence)),
                         semantic_hash("observation-claims", s.evidence_body(fixture.evidence)))

    def test_split_duplicate_and_customer_multidate_leak_rejected(self):
        fixture = self.fixture()
        split = deepcopy(fixture.split)
        split["row_assignments"].append(deepcopy(split["row_assignments"][0]))
        with self.assertRaises(D1ContractError): s.split_body(split)
        split = deepcopy(fixture.split)
        second_date = dict(split["row_assignments"][0], index_date="2026-10-21", role="Test")
        split["row_assignments"].append(second_date)
        with self.assertRaisesRegex(D1ContractError, "same customer"): s.split_body(split)
        split["row_assignments"][-1]["role"] = "Validation"
        with self.assertRaisesRegex(D1ContractError, "within fold"): s.split_body(split)

    def test_table_missing_duplicate_and_array_order(self):
        fixture = self.fixture()
        rows = deepcopy(fixture.rows["features"])
        rows.append(deepcopy(rows[0]))
        with self.assertRaises(D1ContractError): s.table_rows("features", rows, fixture.schema, fixture.evidence)
        del rows[0]["F02"]
        with self.assertRaises(D1ContractError): s.table_rows("features", rows, fixture.schema, fixture.evidence)
        payload = deepcopy(fixture.payload)
        payload["object_bindings"].reverse()
        with self.assertRaises(D1ContractError): s.view_hash(payload)
