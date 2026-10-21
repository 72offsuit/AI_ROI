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


class EvidenceAndGapTests(unittest.TestCase):
    """Literal logical inputs: these checks also execute without pyarrow."""

    def setUp(self):
        self.key = dict(entity_namespace="fixture", source="synthetic", customer_id="a",
                        index_date="2026-10-20")
        self.schema = dict(schema_version="fixture/1", features=[], key_definition=list(s.KEY),
                           tokens=["PAD", "VIEW"], feature_order=[])
        self.evidence = dict(provider="fixture", provider_role="fixture", contract_version="fixture/1",
            source="synthetic", entity_namespace="fixture", entities=[s.entity(self.key)],
            claims=[dict(event_types=["VIEW"], capability="fixture", start="2026-09-01T00:00:00Z",
                end="2026-10-20T00:00:00Z", state="complete", gaps=[],
                availability_basis=dict(as_of="2026-10-19T15:00:00Z", rule="fixture-available"),
                ordering="explicit", session_completion="explicit")])

    def sequence(self, length=1, state="VALID", gaps=None):
        return dict(**self.key, state=state, length=length, tokens=["PAD"]*(30-length)+["VIEW"]*length,
            mask=[False]*(30-length)+[True]*length,
            relative_gap_ms=[None]*30 if gaps is None else gaps,
            gap_mask=[False]*(31-length)+[True]*max(0, length-1) if length else [False]*30,
            claim_indices=[0])

    def logical(self, row):
        return s.table_rows("sequence", [row], self.schema, self.evidence)[0]

    def test_HL01_null_padding_first_and_real_zero_are_distinct(self):
        for length, tail in ((1, []), (2, [0]), (3, [1250, 750]), (30, [1]*29)):
            row = self.sequence(length, gaps=[None]*(31-length)+tail)
            result = self.logical(row)
            self.assertEqual(result["relative_gap_ms"], [None]*(31-length)+tail)
            self.assertEqual(result["gap_mask"], [False]*(31-length)+[True]*(length-1))
        for state, length in (("EMPTY_COMPLETE", 0), ("UNKNOWN", 0), ("UNKNOWN", 1)):
            self.assertEqual(self.logical(self.sequence(length, state))["relative_gap_ms"], [None]*30)

    def test_HL01_invalid_positions_types_lengths_and_masks_rejected(self):
        changes = [dict(relative_gap_ms=[None]*29+[100], gap_mask=[False]*29+[True]),
            dict(relative_gap_ms=[0]+[None]*28+[5]),
            dict(relative_gap_ms=[None]*29+[-1]), dict(relative_gap_ms=[None]*29+[1.0]),
            dict(relative_gap_ms=[None]*29+[True]), dict(relative_gap_ms=[None]*29+["1"]),
            dict(relative_gap_ms=[None]*30), dict(gap_mask=[False]*30),
            dict(relative_gap_ms=[None]*29), dict(mask=[False]*30),
            dict(gap_mask=[False]*28+[1, True]), dict(tokens=["PAD"]*30)]
        for change in changes:
            with self.subTest(change=change):
                row = self.sequence(2, gaps=[None]*29+[5])
                row.update(change)
                # A separate one-event row is required for the fake first-gap attack.
                if change.get("relative_gap_ms") == [None]*29+[100]:
                    row.update(length=1, tokens=["PAD"]*29+["VIEW"], mask=[False]*29+[True])
                with self.assertRaises(D1ContractError): self.logical(row)

    def test_HL02_closed_publication_projection_preserves_existing_explicit_meaning(self):
        expected = s.evidence_body(self.evidence)
        for field in ("ordering", "session_completion"):
            for stamp in ("2026-10-20T01:00:00Z", "2026-10-20T02:00:00Z"):
                altered = deepcopy(self.evidence)
                altered["claims"][0][field] = dict(rule="explicit", asserted_at=stamp, assessed_at=stamp)
                self.assertEqual(s.evidence_body(altered), expected)
                self.assertEqual(semantic_hash("observation-claims", s.evidence_body(altered)),
                                 semantic_hash("observation-claims", expected))

    def test_HL02_unsupported_or_malformed_evidence_is_not_silently_discarded(self):
        variants = ("event_id_sort", None, [], {}, {"rule": "other"},
            {"rule": "explicit", "asserted_at": "2026-10-20T00:00:00+09:60"},
            {"rule": "explicit", "asserted_at": None},
            {"rule": "explicit", "ordinal": [1, 2]},
            {"rule": "explicit", "ended_at": "2026-10-19T01:00:00Z"},
            {"rule": "explicit", "availability_basis": {"as_of": "2026-10-19T01:00:00Z"}},
            {"rule": "explicit", "path": "proof.json"})
        for field in ("ordering", "session_completion"):
            for value in variants:
                with self.subTest(field=field, value=value):
                    altered = deepcopy(self.evidence)
                    altered["claims"][0][field] = value
                    with self.assertRaises(D1ContractError): s.evidence_body(altered)

    def test_HL02_actual_availability_and_completion_claim_are_semantic(self):
        baseline = semantic_hash("observation-claims", s.evidence_body(self.evidence))
        for field in ("as_of", "state"):
            altered = deepcopy(self.evidence)
            if field == "as_of":
                altered["claims"][0]["availability_basis"]["as_of"] = "2026-10-19T15:00:00.000001Z"
            else:
                altered["claims"][0]["state"] = "incomplete"
            self.assertNotEqual(semantic_hash("observation-claims", s.evidence_body(altered)), baseline)


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

    def test_HL02_publication_only_changes_exact_pins_not_raw_view_or_results(self):
        for field in ("ordering", "session_completion"):
            class PublicationFixture(Fixture):
                stamp = ""

                def write_raw(self, prefix, rows, generation):
                    self.evidence["claims"][0][field] = dict(rule="explicit",
                        asserted_at=self.stamp, assessed_at=self.stamp)
                    return super().write_raw(prefix, rows, generation)

            PublicationFixture.stamp = "2026-10-20T01:00:00Z"
            a = PublicationFixture(Path(self.temp.name) / (field+"-a"))
            PublicationFixture.stamp = "2026-10-20T02:00:00Z"
            b = PublicationFixture(Path(self.temp.name) / (field+"-b"))
            self.same_meaning(a, b)
            for role in ("encoder", "cluster"):
                self.assertEqual(a.hash(f"objects/{role}.bin"), b.hash(f"objects/{role}.bin"))
            for path in ("raw-a/evidence.json", "raw-a/manifest.json", "descriptor.json", "manifest.json"):
                self.assertNotEqual(a.hash(path), b.hash(path))
            # The newly assembled bundle is valid, but it cannot impersonate A's exact parent.
            from dataclasses import replace
            with self.assertRaisesRegex(D1ContractError, "requested raw parent mismatch"):
                load_bundle(b.root, "manifest.json", replace(b.expected,
                    raw_bundle_manifest_sha256=a.expected.raw_bundle_manifest_sha256))

    def test_HL02_actual_availability_changes_raw_view_results_with_fixed_objects(self):
        class AvailabilityFixture(Fixture):
            def write_raw(self, prefix, rows, generation):
                self.evidence["claims"][0]["availability_basis"]["as_of"] = "2026-10-19T15:00:00.000001Z"
                return super().write_raw(prefix, rows, generation)

        a = self.fixture()
        b = AvailabilityFixture(Path(self.temp.name) / "actual-availability")
        first, second = self.load(a), self.load(b)
        self.assertNotEqual(first.raw_bundle_semantic_hash, second.raw_bundle_semantic_hash)
        self.assertNotEqual(first.view_semantic_hash, second.view_semantic_hash)
        for kind in s.TABLES:
            self.assertNotEqual(first.value_sha256[kind], second.value_sha256[kind])
        for role in ("encoder", "cluster"):
            self.assertEqual(a.hash(f"objects/{role}.bin"), b.hash(f"objects/{role}.bin"))

    def test_HL04_float32_scalar_vector_parquet_roundtrip_has_identical_semantics(self):
        import pyarrow as pa
        import pyarrow.parquet as pq
        from src.decision.features.d1_serialization import Float32, tlv
        from io import BytesIO

        values = [-1e-50, 1e-50, -0.0, 0.0, 2**-149, -2**-149, 1.5, -1.5]
        table = pa.table({"scalar": pa.array(values, type=pa.float32()),
                          "vector": pa.array([[v, -v] for v in values], type=pa.list_(pa.float32()))})
        output = BytesIO()
        pq.write_table(table, output)
        read = pq.read_table(BytesIO(output.getvalue())).to_pylist()
        for value, row in zip(values, read):
            for before, after in ((Float32(value), Float32(row["scalar"])),
                                  ([Float32(value), Float32(-value)],
                                   [Float32(v) for v in row["vector"]])):
                self.assertEqual(tlv(before), tlv(after))
                self.assertEqual(semantic_hash("float32-roundtrip", before),
                                 semantic_hash("float32-roundtrip", after))
        negative, zero = self.fixture(dtype="Float32", value=-1e-50), self.fixture(dtype="Float32", value=0.0)
        self.assertEqual(self.load(negative).value_sha256, self.load(zero).value_sha256)

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
