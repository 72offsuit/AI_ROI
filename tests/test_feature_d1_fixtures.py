"""Contract-shaped synthetic Parquet and opaque bytes; never trained model fixtures."""

from copy import deepcopy
from dataclasses import replace
from datetime import date
import json
from importlib.util import find_spec
from pathlib import Path

from src.decision.features import d1_semantics as s
from src.decision.features.d1_loader import Expected
from src.decision.features.d1_serialization import SERIALIZATION, file_sha256, instant, semantic_hash, tlv

PARQUET_AVAILABLE = find_spec("pyarrow") is not None


def arrow_schema(kind, schema):
    import pyarrow as pa

    fields = [(name, pa.string()) for name in s.KEY[:-1]] + [("index_date", pa.date32())]
    if kind == "features":
        fields += [("feature_version", pa.string()), ("feature_cutoff_time", pa.timestamp("us", "UTC")),
                   ("generated_at", pa.timestamp("us", "UTC"))]
        for spec in schema["features"]:
            fields.append((spec["id"], {"Int64": pa.int64(), "Float32": pa.float32(),
                "Float64": pa.float64(), "VectorFloat32": pa.list_(pa.float32()),
                "Category": pa.string()}[spec["dtype"]]))
    elif kind == "quality":
        fields += [("feature_id", pa.string()), ("availability", pa.string()),
                   ("reasons", pa.list_(pa.string())), ("audit_counts", pa.map_(pa.string(), pa.int64())),
                   ("claim_indices", pa.list_(pa.int64()))]
    else:
        fields += [("state", pa.string()), ("length", pa.int64()), ("tokens", pa.list_(pa.string())),
                   ("mask", pa.list_(pa.bool_())), ("relative_gap_ms", pa.list_(pa.int64())),
                   ("gap_mask", pa.list_(pa.bool_())), ("claim_indices", pa.list_(pa.int64()))]
    return pa.schema(fields)


class Fixture:
    def __init__(self, root, *, generation="2026-10-20T00:00:00Z", compression="NONE",
                 reverse=False, consumer="D2", fold="fold-1", dtype="Int64", value=2,
                 swap=False, encoder=b"FROZEN-SYNTHETIC-ENCODER-1", cluster=b"FROZEN-SYNTHETIC-CLUSTER-1",
                 split_generation=None, republish=False, empty_test=False):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.compression, self.reverse = compression, reverse
        self.generation = generation
        self.schema = {"schema_version": "fixture-schema/1", "features": [
            dict(id=fid, name=fid, dtype=typ, dimension=dim, nullable=True,
                 definition_version="fixture-definition/1", categories=cats)
            for fid, typ, dim, cats in [("F02", dtype, 0, []), ("F36", "VectorFloat32", 2, []),
                                         ("F37", "Category", 0, ["cluster-0", "cluster-1"])]],
            "key_definition": list(s.KEY), "tokens": ["PAD", "VIEW"], "feature_order": ["F02", "F36", "F37"]}
        self.policy = {"policy_id": "fixture-only-unapproved", "policy_version": "fixture-policy/1",
            "cutoff": dict(operator="lt", boundary="KST midnight", timezone="Asia/Seoul", precision="us"),
            "windows": [dict(name="fixture", length_days=30, offset_days=0)], "denominators": {},
            "session": dict(definition_version="fixture", completion_rule="explicit", window_membership="end"),
            "duplicates": dict(event_id_policy="reject", row_key_policy="reject"),
            "missing": dict(definition_version="fixture", unknown_policy="null", zero_denominator_policy="null"),
            "outlier": dict(definition_version="fixture"),
            "sequence": dict(length=30, pad_direction="left", token_version="fixture", ordering_rule="explicit",
                             empty_policy="exclude_fit_null_transform"),
            "fit_protocol": dict(version="fixture", train_role="Train")}
        self.keys = [dict(entity_namespace="fixture-commerce", source="synthetic", customer_id=cid,
                          index_date=date(2026, 10, 20)) for cid in ("a", "b")]
        self.evidence = dict(provider="fixture-provider", provider_role="fixture-only", contract_version="fixture-evidence/1",
            source="synthetic", entity_namespace="fixture-commerce", entities=[s.entity(row) for row in self.keys],
            claims=[dict(event_types=["VIEW"], capability="fixture", start="2026-09-01T00:00:00Z",
                         end="2026-10-20T00:00:00Z", state="complete", gaps=[],
                         availability_basis={"as_of": "2026-10-19T15:00:00Z", "rule": "fixture-available"}, ordering="explicit",
                         session_completion="explicit")])
        self.allowlist = dict(allowlist_version="fixture-allowlist/1", consumer=consumer,
                              feature_ids=["F02", "F36", "F37"], channels=["sequence", "quality"])
        self.sh = semantic_hash("schema", s.schema_body(self.schema))
        self.ph = semantic_hash("policy", s.policy_body(self.policy))
        self.ah = semantic_hash("allowlist", s.allowlist_body(self.allowlist))
        self.rows = {kind: [] for kind in s.TABLES}
        for index, key in enumerate(self.keys):
            empty = empty_test and index == 1
            val = float(value) if value is not None and dtype.startswith("Float") else value
            self.rows["features"].append(dict(**key, feature_version=self.schema["schema_version"],
                feature_cutoff_time=instant("2026-10-19T15:00:00Z"), generated_at=instant(generation),
                F02=val, F36=None, F37=None))
            for fid in ("F02", "F36", "F37"):
                available = fid == "F02" and val is not None
                reason = [] if available else (["OBSERVATION_UNKNOWN"] if fid == "F02" else
                         ["NO_SEQUENCE_INFORMATION" if empty else "TRANSFORM_NOT_FITTED"])
                self.rows["quality"].append(dict(**key, feature_id=fid,
                    availability="available" if available else "unavailable", reasons=reason,
                    audit_counts={"observed": 0 if empty else 1}, claim_indices=[0]))
            self.rows["sequence"].append(dict(**key, state="EMPTY_COMPLETE" if empty else "VALID",
                length=0 if empty else 1, tokens=["PAD"] * (30 if empty else 29) + ([] if empty else ["VIEW"]),
                mask=[False] * (30 if empty else 29) + ([] if empty else [True]),
                relative_gap_ms=[0] * 30, gap_mask=[False] * 30, claim_indices=[0]))
        self.raw_a = self.write_raw("raw-a", self.rows, generation)
        self.raw_ref = self.raw_a
        if republish:
            republished = deepcopy(self.rows)
            for row in republished["features"]:
                row["generated_at"] = instant("2026-10-20T01:00:00Z")
            self.raw_ref = self.write_raw("raw-b", republished, "2026-10-20T01:00:00Z")
        roles = ["Test", "Train"] if swap else ["Train", "Test"]
        self.split = dict(serialization=SERIALIZATION, split_contract_version="fixture-split/1",
            role_definition_version="fixture-roles/1", generated_at=split_generation or generation,
            split_policy=dict(version="fixture-split-policy/1", method="explicit_fixture", seed=7, parameters={}),
            entity_assignments=[dict(**s.entity(key), role=role) for key, role in zip(self.keys, roles)],
            row_assignments=[dict(**key, consumer=consumer, fit_phase="cv", fold_id=fold, role=role,
                                 excluded=False, reason=None) for key, role in zip(self.keys, roles)])
        if reverse:
            self.split["entity_assignments"].reverse(); self.split["row_assignments"].reverse()
        self.sph = semantic_hash("split-assignments", s.split_body(self.split))
        self.split["split_semantic_hash"] = self.sph
        self.split_ref = self.write_json("split.json", self.split)
        self.selection = dict(input_definition="nonempty_sequences", target_definition=None)
        self.fit, self.transform = s.scopes(self.split, consumer, "cv", fold, self.selection,
            [s.key(row) for row in self.rows["sequence"] if row["state"] == "VALID"])
        self.fh, self.th = semantic_hash("fit-scope", self.fit), semantic_hash("transform-scope", self.transform)
        learned = deepcopy(self.rows)
        for row in learned["features"]:
            if not (empty_test and row["customer_id"] == "b"):
                row.update(F36=[0.25, -0.5], F37="cluster-0")
        for row in learned["quality"]:
            if row["feature_id"] in ("F36", "F37") and not (empty_test and row["customer_id"] == "b"):
                row.update(availability="available", reasons=[])
        train = {tlv(row) for row in self.fit["rows"]}
        intermediate = deepcopy(learned)
        for row in intermediate["features"]:
            row["F37"] = None
        for row in intermediate["quality"]:
            if row["feature_id"] == "F37":
                row.update(availability="unavailable", reasons=["TRANSFORM_NOT_FITTED"])
        self.graph, self.bindings, self.metas = {}, {}, {}
        for role, content, upstream, input_rows in [
            ("encoder", encoder, [], self.rows),
            ("cluster", cluster, ["encoder"], intermediate),
        ]:
            inputs = {kind: [row for row in input_rows[kind] if tlv(s.key(row)) in train] for kind in s.TABLES}
            logical = {kind: s.table_rows(kind, inputs[kind], self.schema, self.evidence) for kind in s.TABLES}
            parents = [self.bindings[name] for name in upstream]
            ih = s.fit_input_hash(role, self.sh, self.ph, self.ah, parents, logical)
            obj = self.write_bytes(f"objects/{role}.bin", content)
            meta = dict(metadata_contract_version="d1-object-metadata/1-proposed", role=role,
                status="fitted", reason=None, object_format_version="fixture-opaque/1",
                implementation_ref=f"fixture:{role}/1", upstream=[dict(role=name,
                    object_file_sha256=self.graph[name]["object"]["file_sha256"]) for name in upstream],
                training_raw_parent=self.raw_a, training_split=self.split_ref,
                fit_inputs={kind: self.write_parquet(f"objects/{role}-{kind}.parquet", kind, inputs[kind]) for kind in s.TABLES},
                fit_facts=dict(consumer=consumer, fit_phase="cv", fold_id=fold,
                    fit_scope_semantic_hash=self.fh, fit_input_value_sha256=ih, schema_semantic_hash=self.sh,
                    policy_semantic_hash=self.ph, allowlist_semantic_hash=self.ah, parameters={"fixture_only": True}, seed=7,
                    runtime=dict(python="fixture-3.12", libraries={"fixture": "1"}, serializer="opaque/1", options={})))
            self.metas[role] = meta
            self.graph[role] = dict(object=obj, metadata=self.write_json(f"objects/{role}.json", meta))
            self.bindings[role] = s.object_binding(meta, obj["file_sha256"], parents)
        raw_root = self.read_json(self.raw_ref["path"])["raw_bundle_semantic_hash"]
        self.payload = dict(view_semantic_contract_version=s.VIEW_CONTRACT, raw_bundle_semantic_hash=raw_root,
            consumer=consumer, schema_semantic_hash=self.sh, policy_semantic_hash=self.ph, allowlist_semantic_hash=self.ah,
            split_semantic_hash=self.sph, fit_phase="cv", fold_id=fold, fit_scope_semantic_hash=self.fh,
            transform_scope_semantic_hash=self.th, object_bindings=[self.bindings[name] for name in sorted(self.bindings)])
        self.vh = s.view_hash(self.payload)
        self.descriptor = dict(contract=s.DESCRIPTOR_CONTRACT, serialization=SERIALIZATION,
            generated_at=generation, semantic_payload=self.payload, view_semantic_hash=self.vh,
            raw_parent=self.raw_ref, split=self.split_ref, allowlist=self.write_json("allowlist.json", self.allowlist),
            fit_selection=self.selection, object_graph=self.graph, provenance={"fixture_only": True})
        self.manifest = dict(contract=s.CONTRACT, serialization=SERIALIZATION, kind="learned",
            descriptor=self.write_json("descriptor.json", self.descriptor), view_semantic_hash=self.vh,
            tables=self.write_tables("learned", learned, self.vh))
        self.write_json("manifest.json", self.manifest)
        self.expected = Expected(self.hash("manifest.json"), self.raw_ref["file_sha256"], self.split_ref["file_sha256"],
            self.hash("descriptor.json"), "synthetic", "fixture-commerce", consumer, "cv", fold,
            self.sh, self.ph, self.ah, self.sph, self.fh, self.th, "fixture-split/1", "fixture-roles/1",
            self.expected_objects())

    def expected_objects(self):
        return {role: dict(object_file_sha256=self.hash(f"objects/{role}.bin"),
            object_metadata_file_sha256=self.hash(f"objects/{role}.json"),
            object_format_version=meta["object_format_version"], implementation_ref=meta["implementation_ref"],
            runtime=meta["fit_facts"]["runtime"]) for role, meta in self.metas.items()}

    def write_bytes(self, name, data):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        return dict(path=name, file_sha256=file_sha256(data))

    def write_json(self, name, record):
        return self.write_bytes(name, json.dumps(record, ensure_ascii=False, default=lambda v: v.isoformat(),
            sort_keys=True, indent=2).encode("utf-8"))

    def read_json(self, name):
        return json.loads((self.root / name).read_text())

    def hash(self, name):
        return file_sha256((self.root / name).read_bytes())

    def write_parquet(self, name, kind, rows):
        import pyarrow as pa
        import pyarrow.parquet as pq

        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        pq.write_table(pa.Table.from_pylist(list(reversed(rows)) if self.reverse else rows,
                                         schema=arrow_schema(kind, self.schema)), path, compression=self.compression)
        return dict(path=name, file_sha256=self.hash(name))

    def write_tables(self, prefix, rows, view):
        return {kind: dict(**self.write_parquet(f"{prefix}/{kind}.parquet", kind, rows[kind]),
            value_sha256=s.table_hash(kind, s.table_rows(kind, rows[kind], self.schema, self.evidence), self.sh, self.ph, view),
            rows=len(rows[kind])) for kind in s.TABLES}

    def write_raw(self, prefix, rows, generation):
        tables = self.write_tables(prefix, rows, None)
        root = s.raw_hash(self.sh, self.ph, semantic_hash("observation-claims", s.evidence_body(self.evidence)),
                          {kind: record["value_sha256"] for kind, record in tables.items()})
        return self.write_json(f"{prefix}/manifest.json", dict(contract=s.CONTRACT, serialization=SERIALIZATION,
            kind="raw", source="synthetic", entity_namespace="fixture-commerce", generated_at=generation,
            schema=self.write_json(f"{prefix}/schema.json", self.schema),
            policy=self.write_json(f"{prefix}/policy.json", self.policy),
            evidence=self.write_json(f"{prefix}/evidence.json", self.evidence), tables=tables,
            input_files=[self.write_bytes(f"{prefix}/input.bin", b"opaque synthetic source snapshot")],
            raw_bundle_semantic_hash=root))

    def amend(self, name, change):
        record = self.read_json(name)
        change(record)
        self.write_json(name, record)

    def refresh_physical(self):
        """Reseal exact references only, leaving claimed semantics for negative tests."""
        def visit(name, active):
            if not name.endswith(".json"):
                return self.hash(name)
            assert name not in active
            record = self.read_json(name)
            def walk(value):
                if isinstance(value, dict):
                    if set(value) == {"path", "file_sha256"} or (
                        "path" in value and "file_sha256" in value and "value_sha256" in value):
                        value["file_sha256"] = visit(value["path"], active | {name})
                    else:
                        for item in value.values(): walk(item)
                elif isinstance(value, list):
                    for item in value: walk(item)
            walk(record)
            return self.write_json(name, record)["file_sha256"]
        visit("manifest.json", set())
        self.expected = replace(self.expected, manifest_sha256=self.hash("manifest.json"),
            raw_bundle_manifest_sha256=self.hash(self.raw_ref["path"]), split_manifest_sha256=self.hash("split.json"),
            view_descriptor_sha256=self.hash("descriptor.json"), objects=self.expected_objects())

    def read_parquet(self, name, kind):
        import pyarrow.parquet as pq

        rows = pq.read_table(self.root / name).to_pylist()
        if kind == "quality":
            for row in rows:
                row["audit_counts"] = dict(row["audit_counts"])
        return rows

    def reseal_learning(self, *, update_fit_scope=False):
        """Explicit attack builder: recompute semantics AND physical pins from actual files.

        Only use when the test intentionally requests the newly assembled bundle.
        Context facts remain untouched; scope declarations change only on request.
        No rows/values/selection are repaired or supplied by this helper.
        """
        descriptor = self.read_json("descriptor.json")
        raw = self.read_json(descriptor["raw_parent"]["path"])
        evidence = self.read_json(raw["evidence"]["path"])
        split = self.read_json(descriptor["split"]["path"])
        self.sph = semantic_hash("split-assignments", s.split_body(split))
        split["split_semantic_hash"] = self.sph
        self.write_json(descriptor["split"]["path"], split)
        context = descriptor["semantic_payload"]
        sequence = self.read_parquet(raw["tables"]["sequence"]["path"], "sequence")
        fit, transform = s.scopes(split, context["consumer"], context["fit_phase"], context["fold_id"],
            descriptor["fit_selection"], [s.key(row) for row in sequence if row["state"] == "VALID"])
        self.fh, self.th = semantic_hash("fit-scope", fit), semantic_hash("transform-scope", transform)
        bindings = {}
        for role in ("encoder", "cluster"):
            node = descriptor["object_graph"][role]
            meta = self.read_json(node["metadata"]["path"])
            parents = [bindings[edge["role"]] for edge in meta["upstream"]]
            if meta["status"] == "fitted":
                training = self.read_json(meta["training_raw_parent"]["path"])
                training_evidence = self.read_json(training["evidence"]["path"])
                inputs = {kind: s.table_rows(kind, self.read_parquet(meta["fit_inputs"][kind]["path"], kind),
                                             self.schema, training_evidence) for kind in s.TABLES}
                meta["fit_facts"]["fit_input_value_sha256"] = s.fit_input_hash(
                    role, self.sh, self.ph, self.ah, parents, inputs)
                if update_fit_scope:
                    meta["fit_facts"]["fit_scope_semantic_hash"] = self.fh
            self.metas[role] = meta
            self.write_json(node["metadata"]["path"], meta)
            bindings[role] = s.object_binding(meta, self.hash(node["object"]["path"]) if node["object"] else "", parents)
        context.update(raw_bundle_semantic_hash=raw["raw_bundle_semantic_hash"],
            split_semantic_hash=self.sph, fit_scope_semantic_hash=self.fh,
            transform_scope_semantic_hash=self.th, object_bindings=[bindings[role] for role in sorted(bindings)])
        self.payload, self.vh = context, s.view_hash(context)
        descriptor["view_semantic_hash"] = self.vh
        self.write_json("descriptor.json", descriptor)
        manifest = self.read_json("manifest.json")
        manifest["view_semantic_hash"] = self.vh
        for kind, table in manifest["tables"].items():
            rows = self.read_parquet(table["path"], kind)
            table.update(rows=len(rows), value_sha256=s.table_hash(kind,
                s.table_rows(kind, rows, self.schema, evidence), self.sh, self.ph, self.vh))
        self.write_json("manifest.json", manifest)
        self.refresh_physical()
        self.expected = replace(self.expected, split_semantic_hash=self.sph,
            fit_scope_semantic_hash=self.fh, transform_scope_semantic_hash=self.th)
