from copy import deepcopy
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from src.decision.features import d1_semantics as s
from src.decision.features.d1_loader import load_bundle
from src.decision.features.d1_serialization import D1ContractError
from tests.test_feature_d1_fixtures import Fixture, PARQUET_AVAILABLE, arrow_schema

if PARQUET_AVAILABLE:
    import pyarrow as pa
    import pyarrow.parquet as pq


@unittest.skipUnless(PARQUET_AVAILABLE, "BLOCKED: pyarrow 미설치 — 실제 Parquet 로더 시험")
class LoaderTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.fixture = Fixture(self.temp.name)

    def reject(self, pattern=None):
        with self.assertRaisesRegex(D1ContractError, pattern or ".+"):
            load_bundle(self.fixture.root, "manifest.json", self.fixture.expected)

    def test_explicit_manifest_and_opaque_objects_accepted(self):
        bundle = load_bundle(self.fixture.root, "manifest.json", self.fixture.expected)
        self.assertEqual(bundle.view_semantic_hash, self.fixture.vh)
        self.assertEqual(len(bundle.rows["features"]), 2)

    def test_134_ASCII_bundle_keeps_recorded_semantic_hashes(self):
        result = load_bundle(self.fixture.root, "manifest.json", self.fixture.expected)
        # Fixed baseline from the independently reviewed pre-policy fixture.
        self.assertEqual(result.raw_bundle_semantic_hash,
                         "eb256f17f08acbd09e4f257d2cbe397e5f1117a0c5ec2a140df34494d4e82724")
        self.assertEqual(result.split_semantic_hash,
                         "8be11f64934eaa781fe507ad7566a84f226da289ff542202c31b377bb1859c3f")
        self.assertEqual(result.view_semantic_hash,
                         "f0817f8f5c6f4450139469273f5be15446cab42b42e9586cd85d8138bb62f38c")
        self.assertEqual(result.value_sha256, dict(
            features="dae799832c4a3eb5f94cf302388988fcf45ecc34150da1fd70eefbc1413bb9fb",
            quality="30bc210b8d561a3021f91ecba8bd5c151a525e0a0437a2e3817c319d56aded75",
            sequence="39585c841c04b67b171940e6403f7c205f945c46a3d7b0b566c3b179b5b82503"))

    def test_134_resealed_non_ASCII_split_reaches_date_guard(self):
        variants = ("٢٠٢٦-١٠-٢٠", "２０２６-１０-２０",
                    "".join(chr(0x10D40 + digit) for digit in (2, 0, 2, 6)) + "-10-20")
        for index, value in enumerate(variants):
            with self.subTest(value=ascii(value)):
                f = Fixture(self.fixture.root / f"date-{index}")
                baseline = load_bundle(f.root, "manifest.json", f.expected)
                requested_split = f.expected.split_semantic_hash
                old_pin = f.expected.split_manifest_sha256
                f.amend("split.json", lambda d: d["row_assignments"][0].update(index_date=value))
                # Equivalent pre-policy dates: semantic claims stay frozen. Only
                # exact byte references are resealed, including training_split.
                f.refresh_physical()
                self.assertNotEqual(f.expected.split_manifest_sha256, old_pin)
                self.assertEqual(f.expected.split_semantic_hash, requested_split)
                self.assertEqual(f.read_json("descriptor.json")["view_semantic_hash"], baseline.view_semantic_hash)
                self.assertEqual(f.read_json("split.json")["row_assignments"][0]["index_date"], value)
                with patch.object(s, "calendar_date", wraps=s.calendar_date) as guard:
                    with self.assertRaisesRegex(D1ContractError, "^invalid date syntax$"):
                        load_bundle(f.root, "manifest.json", f.expected)
                    guard.assert_any_call(value)

    def test_HL01_fully_resealed_fake_first_gap_reaches_position_guard(self):
        class FirstGapFixture(Fixture):
            def write_tables(self, prefix, rows, view):
                for row in rows["sequence"]:
                    row["relative_gap_ms"][-1] = 100
                    row["gap_mask"][-1] = True
                return super().write_tables(prefix, rows, view)

        original = s.table_rows

        def unchecked_sequence(kind, rows, schema, evidence):
            if kind != "sequence":
                return original(kind, rows, schema, evidence)
            # Attack construction only: independent projection deliberately skips
            # gap validation, so every actual wire hash/pin can be coherent.
            claims = s.evidence_body(evidence)["claims"]
            fields = ("state", "length", "tokens", "mask", "relative_gap_ms", "gap_mask")
            result = [{**s.key(row), **{field: row[field] for field in fields},
                "ordering_claims": s.canonical_set([claims[i] for i in row["claim_indices"]])}
                for row in rows]
            return s.ordered(result, s.key)

        with patch.object(s, "table_rows", side_effect=unchecked_sequence):
            f = FirstGapFixture(self.fixture.root / "HL01-first-gap")
        # No patch is active during loading. The caller requests these exact bytes.
        for path in ("raw-a/sequence.parquet", "objects/encoder-sequence.parquet",
                     "objects/cluster-sequence.parquet", "learned/sequence.parquet"):
            row = f.read_parquet(path, "sequence")[0]
            self.assertEqual((row["length"], row["relative_gap_ms"][-1], row["gap_mask"][-1]),
                             (1, 100, True))
        with self.assertRaisesRegex(D1ContractError, "first actual event gap must be null/false"):
            load_bundle(f.root, "manifest.json", f.expected)

    def test_HL01_nullable_gaps_survive_raw_fit_and_output_parquet(self):
        f = self.fixture
        result = load_bundle(f.root, "manifest.json", f.expected)
        for path in ("raw-a/sequence.parquet", "objects/encoder-sequence.parquet",
                     "objects/cluster-sequence.parquet", "learned/sequence.parquet"):
            for row in f.read_parquet(path, "sequence"):
                self.assertEqual(row["relative_gap_ms"], [None]*30)
                self.assertEqual(row["gap_mask"], [False]*30)
        self.assertEqual(len(result.rows["features"]), 2)

    def test_HL01_generator_and_parquet_gap_channels_agree_for_real_zero_and_elapsed(self):
        from tests.test_feature_d1_calculation import batch, event
        from tests.test_feature_d1_sequence import make_sequence, order

        for gap, second_at in ((0, "2026-10-02T00:00:00+09:00"),
                               (1250, "2026-10-02T00:00:01.250+09:00")):
            with self.subTest(gap=gap):
                records = [event("page_view", number=1), event("search", second_at, 2)]
                source = batch(records)
                produced = make_sequence(source, orders=(order(source, records),) if gap == 0 else ()).rows[0]

                class TwoEventFixture(Fixture):
                    def write_tables(self, prefix, rows, view):
                        for row in rows["sequence"]:
                            row.update(length=2, tokens=["PAD"]*28+["VIEW", "VIEW"],
                                mask=[False]*28+[True, True], relative_gap_ms=[None]*29+[gap],
                                gap_mask=[False]*29+[True])
                        return super().write_tables(prefix, rows, view)

                f = TwoEventFixture(self.fixture.root / f"gap-{gap}")
                result = load_bundle(f.root, "manifest.json", f.expected)
                for row in result.rows["sequence"]:
                    for field in ("length", "mask", "relative_gap_ms", "gap_mask"):
                        self.assertEqual(row[field], produced[field])
                # Only the gap channel is compared; no numeric-token adapter is supplied.
                self.assertEqual(produced["relative_gap_ms"], [None]*29+[gap])
                self.assertEqual(produced["gap_mask"], [False]*29+[True])

    def test_V10_D1_equal_semantics_wrong_exact_requested_parent(self):
        f = Fixture(self.fixture.root / "republish", republish=True)
        f.amend("descriptor.json", lambda d: d.update(raw_parent=f.raw_a))
        f.refresh_physical()
        with self.assertRaisesRegex(D1ContractError, "requested raw parent"):
            load_bundle(f.root, "manifest.json", f.expected)

    def test_V10_D2_declared_B_actual_A_file_bytes(self):
        f = Fixture(self.fixture.root / "republish", republish=True)
        (f.root / f.raw_ref["path"]).write_bytes((f.root / f.raw_a["path"]).read_bytes())
        with self.assertRaisesRegex(D1ContractError, "exact file hash"):
            load_bundle(f.root, "manifest.json", f.expected)

    def test_exact_file_hash_mismatch(self):
        f = self.fixture
        with (f.root / "learned/features.parquet").open("ab") as stream: stream.write(b"changed")
        self.reject("exact file hash")

    def test_parent_training_A_is_still_required_when_transforming_B(self):
        f = Fixture(self.fixture.root / "republish", republish=True)
        (f.root / f.raw_a["path"]).unlink()
        with self.assertRaisesRegex(D1ContractError, "missing/unreadable"):
            load_bundle(f.root, "manifest.json", f.expected)

    def test_V10_A_external_consumer_fold_phase_scope_mismatch(self):
        f = self.fixture
        cases = [(dict(consumer="D3"), "allowlist context mismatch"),
                 (dict(fold_id="fold-2"), "requested split context absent"),
                 (dict(fit_phase="final"), "requested split context absent"),
                 (dict(fit_scope_semantic_hash="0" * 64), "requested fit/transform scope mismatch"),
                 (dict(transform_scope_semantic_hash="0" * 64), "requested fit/transform scope mismatch")]
        for kwargs, message in cases:
            with self.subTest(kwargs=kwargs), self.assertRaisesRegex(D1ContractError, message):
                load_bundle(f.root, "manifest.json", replace(f.expected, **kwargs))

    def test_V10_B_actual_split_changed_self_hash_cannot_hide_it(self):
        f = Fixture(self.fixture.root / "reassigned", swap=True)
        # The new split, fit inputs, view, values and exact pins are all internally coherent.
        # Only the caller's requested split remains the original assignment.
        expected = replace(f.expected, split_semantic_hash=self.fixture.expected.split_semantic_hash)
        with self.assertRaisesRegex(D1ContractError, "requested actual split mismatch"):
            load_bundle(f.root, "manifest.json", expected)

    def test_object_context_fact_mismatch_after_full_reseal(self):
        for field, value in (("consumer", "D3"), ("fit_phase", "other-phase"), ("fold_id", "other-fold")):
            with self.subTest(field=field):
                f = Fixture(self.fixture.root / field)
                f.amend("objects/encoder.json", lambda d: d["fit_facts"].update({field: value}))
                f.reseal_learning()
                with self.assertRaisesRegex(D1ContractError, "frozen fit facts mismatch"):
                    load_bundle(f.root, "manifest.json", f.expected)

    def test_exact_split_and_metadata_pins_are_not_relaxed(self):
        f = self.fixture
        for kwargs in (dict(split_manifest_sha256="f" * 64), dict(view_descriptor_sha256="f" * 64),
                       dict(raw_bundle_manifest_sha256="f" * 64), dict(manifest_sha256="f" * 64)):
            with self.subTest(kwargs=kwargs), self.assertRaises(D1ContractError):
                load_bundle(f.root, "manifest.json", replace(f.expected, **kwargs))
        objects = deepcopy(f.expected.objects)
        objects["encoder"]["object_metadata_file_sha256"] = "f" * 64
        with self.assertRaises(D1ContractError):
            load_bundle(f.root, "manifest.json", replace(f.expected, objects=objects))

    def test_V10_C1_wrong_expected_object_and_changed_object_file(self):
        f = self.fixture
        objects = deepcopy(f.expected.objects)
        objects["encoder"]["object_file_sha256"] = "f" * 64
        with self.assertRaisesRegex(D1ContractError, "requested object bytes"):
            load_bundle(f.root, "manifest.json", replace(f.expected, objects=objects))
        (f.root / "objects/encoder.bin").write_bytes(b"changed object")
        self.reject("exact file hash")

    def test_V10_C2_wrong_upstream_connection(self):
        f = self.fixture
        f.amend("objects/cluster.json", lambda d: d["upstream"][0].update(object_file_sha256="f" * 64))
        f.refresh_physical()
        self.reject("wrong upstream object connection")

    def test_object_graph_cycle(self):
        f = self.fixture
        f.amend("objects/encoder.json", lambda d: d.update(upstream=[{
            "role": "cluster", "object_file_sha256": f.graph["cluster"]["object"]["file_sha256"]}]))
        f.refresh_physical()
        self.reject("object graph cycle")

    def test_wrong_train_membership_and_frozen_fit_facts(self):
        f = self.fixture
        rows = [dict(f.rows["features"][1])]
        f.write_parquet("objects/encoder-features.parquet", "features", rows)
        f.refresh_physical()
        self.reject("exactly selected Train keys")

    def test_frozen_fit_facts_are_recomputed(self):
        f = self.fixture
        f.amend("objects/encoder.json", lambda d: d["fit_facts"].update(fit_input_value_sha256="f" * 64))
        f.refresh_physical()
        self.reject("frozen fit facts mismatch")

    def test_raw_fit_values_are_not_self_declarations(self):
        f = self.fixture
        rows = [dict(f.rows["features"][0], F02=999)]
        f.write_parquet("objects/encoder-features.parquet", "features", rows)
        f.refresh_physical()
        self.reject("raw fit input values differ")

    def test_cluster_fit_cannot_use_its_own_output(self):
        f = self.fixture
        rows = pq.read_table(f.root / "objects/cluster-features.parquet").to_pylist()
        rows[0]["F37"] = "cluster-0"
        f.write_parquet("objects/cluster-features.parquet", "features", rows)
        quality = pq.read_table(f.root / "objects/cluster-quality.parquet").to_pylist()
        for row in quality:
            row["audit_counts"] = dict(row["audit_counts"])
            if row["feature_id"] == "F37": row.update(availability="available", reasons=[])
        f.write_parquet("objects/cluster-quality.parquet", "quality", quality)
        f.refresh_physical()
        self.reject("contains its own output")

    def test_unfitted_object_cannot_emit_a_category(self):
        f = self.fixture
        f.amend("objects/cluster.json", lambda d: d.update(status="not_fitted", reason="fixture-not-fitted", upstream=[]))
        f.amend("descriptor.json", lambda d: d["object_graph"]["cluster"].update(object=None))
        # Use the correctly recomputed non-fitted semantic binding, so the output guard is reached.
        binding = s.object_binding(dict(role="cluster", status="not_fitted", reason="fixture-not-fitted"), "", [])
        f.payload["object_bindings"][0] = binding
        f.vh = s.view_hash(f.payload)
        f.amend("descriptor.json", lambda d: d.update(semantic_payload=f.payload, view_semantic_hash=f.vh))
        f.amend("manifest.json", lambda d: d.update(view_semantic_hash=f.vh))
        f.refresh_physical()
        self.rehash_learned_values(f.vh)
        objects = deepcopy(f.expected.objects)
        objects["cluster"]["object_file_sha256"] = None
        f.expected = replace(f.expected, objects=objects)
        self.reject("unfitted transform")

    def rehash_learned_values(self, view=None):
        f = self.fixture
        def update(manifest):
            for kind in s.TABLES:
                rows = pq.read_table(f.root / f"learned/{kind}.parquet").to_pylist()
                if kind == "quality":
                    for row in rows: row["audit_counts"] = dict(row["audit_counts"])
                manifest["tables"][kind]["value_sha256"] = s.table_hash(kind,
                    s.table_rows(kind, rows, f.schema, f.evidence), f.sh, f.ph, view or f.vh)
        f.amend("manifest.json", update)
        f.refresh_physical()

    def test_quality_consistency_even_when_all_claimed_hashes_are_resealed(self):
        f = self.fixture
        rows = pq.read_table(f.root / "learned/features.parquet").to_pylist()
        rows[0]["F02"] = None  # quality still claims available, and nothing may fill this with zero.
        self.rewrite_learned(rows=rows)
        self.rehash_learned_values()
        self.reject("canonical/quality availability mismatch")

    def test_resealed_output_cannot_change_raw_canonical_values(self):
        f = self.fixture
        rows = pq.read_table(f.root / "learned/features.parquet").to_pylist()
        rows[0]["F02"] = 999
        self.rewrite_learned(rows=rows)
        self.rehash_learned_values()
        self.reject("changed raw canonical values")

    def test_resealed_output_cannot_change_raw_sequence(self):
        f = self.fixture
        rows = pq.read_table(f.root / "learned/sequence.parquet").to_pylist()
        rows[0].update(length=2, tokens=["PAD"]*28+["VIEW", "VIEW"],
                       mask=[False]*28+[True, True], relative_gap_ms=[None]*29+[100],
                       gap_mask=[False]*29+[True])
        f.write_parquet("learned/sequence.parquet", "sequence", rows)
        self.rehash_learned_values()
        self.reject("changed raw sequence")

    def test_quality_coverage_even_when_table_hash_is_resealed(self):
        f = self.fixture
        rows = pq.read_table(f.root / "learned/quality.parquet").to_pylist()[:-1]
        for row in rows: row["audit_counts"] = dict(row["audit_counts"])
        f.write_parquet("learned/quality.parquet", "quality", rows)
        f.amend("manifest.json", lambda d: d["tables"]["quality"].update(rows=len(rows)))
        self.rehash_learned_values()
        self.reject("quality key coverage mismatch")

    def test_v021_v022_serialization_mix_rejected(self):
        f = self.fixture
        f.amend("raw-a/manifest.json", lambda d: d.update(serialization="d1-semantic/1-proposed"))
        f.refresh_physical()
        self.reject("contract/serialization version mismatch")

    def test_missing_required_field(self):
        f = self.fixture
        f.amend("descriptor.json", lambda d: d.pop("object_graph"))
        f.refresh_physical()
        self.reject("missing or malformed")

    def test_duplicate_json_key_even_with_exact_hash(self):
        f = self.fixture
        (f.root / "descriptor.json").write_text('{"contract":"a","contract":"b"}')
        f.manifest["descriptor"] = dict(path="descriptor.json", file_sha256=f.hash("descriptor.json"))
        f.write_json("manifest.json", f.manifest)
        f.expected = replace(f.expected, manifest_sha256=f.hash("manifest.json"), view_descriptor_sha256=f.hash("descriptor.json"))
        self.reject("duplicate JSON key")

    def rewrite_learned(self, rows=None, table=None):
        f = self.fixture
        if table is None: table = pa.Table.from_pylist(rows, schema=arrow_schema("features", f.schema))
        pq.write_table(table, f.root / "learned/features.parquet")
        f.refresh_physical()

    def test_actual_dtype_not_metadata_claim(self):
        f = self.fixture
        table = pq.read_table(f.root / "learned/features.parquet")
        schema = table.schema.set(table.schema.get_field_index("F02"), pa.field("F02", pa.float64()))
        self.rewrite_learned(table=table.cast(schema))
        self.reject("actual Parquet dtype")

    def test_forbidden_metadata_column(self):
        f = self.fixture
        table = pq.read_table(f.root / "learned/features.parquet").append_column("treatment_post_t0", pa.array([1, 0]))
        self.rewrite_learned(table=table)
        self.reject("missing or forbidden Parquet column")

    def test_duplicate_row_key(self):
        f = self.fixture
        rows = pq.read_table(f.root / "learned/features.parquet").to_pylist()
        rows[1] = deepcopy(rows[0])
        self.rewrite_learned(rows=rows)
        self.reject("duplicate logical key")

    def test_source_namespace_mixing(self):
        for field in ("source", "entity_namespace"):
            with self.subTest(field=field):
                f = Fixture(self.fixture.root / field)
                for kind in s.TABLES:
                    rows = f.read_parquet(f"learned/{kind}.parquet", kind)
                    for row in rows:
                        if row["customer_id"] == "b": row[field] = "other"
                    f.write_parquet(f"learned/{kind}.parquet", kind, rows)
                f.reseal_learning()
                with self.assertRaisesRegex(D1ContractError, "source/namespace mismatch"):
                    load_bundle(f.root, "manifest.json", f.expected)

    def three_customer_fixture(self, name, *, missing=False, selection="all_train_rows", empty_c=False):
        f = Fixture(self.fixture.root / name)
        rows = deepcopy(f.rows)
        for kind in s.TABLES:
            for original in list(rows[kind]):
                if original["customer_id"] != "a": continue
                new = dict(deepcopy(original), customer_id="c")
                if empty_c and kind == "sequence":
                    new.update(state="EMPTY_COMPLETE", length=0, tokens=["PAD"] * 30,
                               mask=[False] * 30, relative_gap_ms=[None] * 30, gap_mask=[False] * 30)
                if empty_c and kind == "quality" and new["feature_id"] in ("F36", "F37"):
                    new["reasons"] = ["NO_SEQUENCE_INFORMATION"]
                rows[kind].append(new)
        c = dict(f.keys[0], customer_id="c")
        f.evidence["entities"].append(s.entity(c))
        f.raw_ref = f.write_raw("raw-b", rows, f.generation)
        if not missing:
            training = f.write_raw("training-a", rows, f.generation)
            for role in ("encoder", "cluster"):
                f.amend(f"objects/{role}.json", lambda d: d.update(training_raw_parent=training))
                if not (empty_c and selection == "nonempty_sequences"):
                    for kind in s.TABLES:
                        inputs = f.read_parquet(f"objects/{role}-{kind}.parquet", kind)
                        inputs += [dict(deepcopy(row), customer_id="c") for row in list(inputs)]
                        f.write_parquet(f"objects/{role}-{kind}.parquet", kind, inputs)
        f.amend("split.json", lambda d: (
            d["entity_assignments"].append(dict(**s.entity(c), role="Train")),
            d["row_assignments"].append(dict(**c, consumer="D2", fit_phase="cv", fold_id="fold-1",
                                            role="Train", excluded=False, reason=None))))
        f.amend("descriptor.json", lambda d: d.update(raw_parent=f.raw_ref,
            fit_selection=dict(input_definition=selection, target_definition=None)))
        for kind in s.TABLES:
            outputs = f.read_parquet(f"learned/{kind}.parquet", kind)
            for original in list(outputs):
                if original["customer_id"] != "a": continue
                new = dict(deepcopy(original), customer_id="c")
                if empty_c:
                    if kind == "features": new.update(F36=None, F37=None)
                    elif kind == "sequence":
                        new = next(row for row in rows[kind] if row["customer_id"] == "c")
                    elif new["feature_id"] in ("F36", "F37"):
                        new.update(availability="unavailable", reasons=["NO_SEQUENCE_INFORMATION"])
                outputs.append(new)
            f.write_parquet(f"learned/{kind}.parquet", kind, outputs)
        f.reseal_learning(update_fit_scope=True)
        return f

    def test_123_all_train_missing_parent_row_fully_resealed(self):
        f = self.three_customer_fixture("missing-train", missing=True)
        with self.assertRaisesRegex(D1ContractError, "declared Train rows absent from training raw parent"):
            load_bundle(f.root, "manifest.json", f.expected)

    def test_123_declared_parent_and_actual_train_inputs_match(self):
        f = self.three_customer_fixture("complete-train")
        loaded = load_bundle(f.root, "manifest.json", f.expected)
        self.assertEqual({row["customer_id"] for row in loaded.rows["features"]}, {"a", "b", "c"})

    def test_123_actual_fit_rows_cannot_shrink_a_complete_parent_scope(self):
        f = self.three_customer_fixture("missing-actual-input")
        for role in ("encoder", "cluster"):
            for kind in s.TABLES:
                inputs = f.read_parquet(f"objects/{role}-{kind}.parquet", kind)
                f.write_parquet(f"objects/{role}-{kind}.parquet", kind,
                                [row for row in inputs if row["customer_id"] != "c"])
        f.reseal_learning()
        with self.assertRaisesRegex(D1ContractError, "fit inputs must be exactly selected Train keys"):
            load_bundle(f.root, "manifest.json", f.expected)

    def test_123_nonempty_selection_still_excludes_observed_empty_train(self):
        f = self.three_customer_fixture("empty-c", selection="nonempty_sequences", empty_c=True)
        loaded = load_bundle(f.root, "manifest.json", f.expected)
        self.assertEqual(len(loaded.rows["features"]), 3)
        self.assertEqual({row["customer_id"] for row in f.read_parquet(
            "objects/encoder-features.parquet", "features")}, {"a"})

    def test_124_cluster_raw_feature_sequence_quality_fully_resealed(self):
        for kind in s.TABLES:
            with self.subTest(kind=kind):
                f = Fixture(self.fixture.root / kind)
                rows = f.read_parquet(f"objects/cluster-{kind}.parquet", kind)
                if kind == "features": rows[0]["F02"] = 999
                elif kind == "sequence":
                    rows[0].update(length=2, tokens=["PAD"] * 28 + ["VIEW", "VIEW"],
                        mask=[False] * 28 + [True, True], relative_gap_ms=[None] * 29 + [100],
                        gap_mask=[False] * 29 + [True])
                else:
                    next(row for row in rows if row["feature_id"] == "F02")["audit_counts"]["observed"] = 999
                f.write_parquet(f"objects/cluster-{kind}.parquet", kind, rows)
                f.reseal_learning()
                with self.assertRaisesRegex(D1ContractError, f"upstream fit raw {kind} differ"):
                    load_bundle(f.root, "manifest.json", f.expected)

    def unknown_fixture(self, name, *, f36=False, f37=False, reason="OBSERVATION_UNKNOWN", output_reasons=None):
        f = Fixture(self.fixture.root / name)
        for row in f.rows["sequence"]:
            if row["customer_id"] == "b": row["state"] = "UNKNOWN"
        for row in f.rows["quality"]:
            if row["customer_id"] == "b" and row["feature_id"] in ("F36", "F37"):
                row["reasons"] = [reason, "TRANSFORM_NOT_FITTED"]
        f.raw_a = f.raw_ref = f.write_raw("raw-a", f.rows, f.generation)
        f.amend("descriptor.json", lambda d: d.update(raw_parent=f.raw_ref))
        for kind in s.TABLES:
            rows = f.read_parquet(f"learned/{kind}.parquet", kind)
            for row in rows:
                if row["customer_id"] != "b": continue
                if kind == "features":
                    row.update(F36=[0.25, -0.5] if f36 else None, F37="cluster-0" if f37 else None)
                elif kind == "sequence": row["state"] = "UNKNOWN"
                elif row["feature_id"] in ("F36", "F37"):
                    available = f36 if row["feature_id"] == "F36" else f37
                    row.update(availability="available" if available else "unavailable",
                               reasons=[] if available else ([reason] if output_reasons is None else output_reasons))
            f.write_parquet(f"learned/{kind}.parquet", kind, rows)
        f.reseal_learning()
        return f

    def test_125_unknown_each_nonnull_output_fully_resealed(self):
        for f36, f37 in ((True, False), (False, True), (True, True)):
            with self.subTest(f36=f36, f37=f37):
                f = self.unknown_fixture(f"unknown-{f36}-{f37}", f36=f36, f37=f37)
                with self.assertRaisesRegex(D1ContractError, "unknown sequence cannot have learned output"):
                    load_bundle(f.root, "manifest.json", f.expected)

    def test_125_unknown_null_retains_observation_or_order_reason(self):
        for reason in ("OBSERVATION_UNKNOWN", "AMBIGUOUS_EVENT_ORDER"):
            with self.subTest(reason=reason):
                f = self.unknown_fixture(reason, reason=reason)
                loaded = load_bundle(f.root, "manifest.json", f.expected)
                row = next(row for row in loaded.rows["features"] if row["customer_id"] == "b")
                self.assertIsNone(row["F36"])
                self.assertIsNone(row["F37"])

    def test_125_unknown_cannot_borrow_empty_or_only_unfitted_reason(self):
        cases = [["NO_SEQUENCE_INFORMATION"], ["TRANSFORM_NOT_FITTED"],
                 ["OBSERVATION_UNKNOWN", "NO_SEQUENCE_INFORMATION"]]
        for index, reasons in enumerate(cases):
            with self.subTest(reasons=reasons):
                f = self.unknown_fixture(f"wrong-reason-{index}", output_reasons=reasons)
                with self.assertRaisesRegex(D1ContractError, "unknown sequence needs observation/order reason"):
                    load_bundle(f.root, "manifest.json", f.expected)

    def test_null_zero_quality_and_nonfinite_not_silently_repaired(self):
        f = self.fixture
        rows = pq.read_table(f.root / "learned/features.parquet").to_pylist()
        rows[0]["F36"] = [float("nan"), 0.0]
        self.rewrite_learned(rows=rows)
        self.reject("non-finite")

    def test_safe_paths_no_parent_traversal(self):
        f = self.fixture
        f.amend("descriptor.json", lambda d: d["raw_parent"].update(path="../outside.json"))
        # No need to read the disallowed path to refresh outer exact hashes.
        f.amend("manifest.json", lambda d: d["descriptor"].update(file_sha256=f.hash("descriptor.json")))
        f.expected = replace(f.expected, manifest_sha256=f.hash("manifest.json"), view_descriptor_sha256=f.hash("descriptor.json"))
        self.reject("escapes explicit root")

    def test_symlink_ref_is_rejected_without_following_it(self):
        f = self.fixture
        (f.root / "raw-link.json").symlink_to(f.root / f.raw_ref["path"])
        f.amend("descriptor.json", lambda d: d["raw_parent"].update(path="raw-link.json"))
        f.amend("manifest.json", lambda d: d["descriptor"].update(file_sha256=f.hash("descriptor.json")))
        f.expected = replace(f.expected, manifest_sha256=f.hash("manifest.json"), view_descriptor_sha256=f.hash("descriptor.json"))
        self.reject("symlink in bundle path")
