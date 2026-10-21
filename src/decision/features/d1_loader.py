"""Read an explicitly pinned D1 bundle. No discovery, publication or object execution."""

from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from . import d1_semantics as s
from .d1_serialization import (
    D1ContractError, SERIALIZATION, file_sha256, instant, project, require,
    semantic_hash, strict_json, tlv,
)

UNKNOWN_SEQUENCE_REASONS = frozenset({
    "OBSERVATION_UNKNOWN", "AMBIGUOUS_EVENT_ORDER", "INCOMPLETE_WINDOW",
    "UNSUPPORTED_EVENT_KIND", "CONTRACT_UNRESOLVED",
})


@dataclass(frozen=True)
class Expected:
    manifest_sha256: str
    raw_bundle_manifest_sha256: str
    split_manifest_sha256: str
    view_descriptor_sha256: str
    source: str
    entity_namespace: str
    consumer: str
    fit_phase: str
    fold_id: str
    schema_semantic_hash: str
    policy_semantic_hash: str
    allowlist_semantic_hash: str
    split_semantic_hash: str
    fit_scope_semantic_hash: str
    transform_scope_semantic_hash: str
    split_contract_version: str
    role_definition_version: str
    # role -> exact object/metadata hashes and explicit format/implementation/runtime.
    objects: dict[str, dict]


@dataclass(frozen=True)
class VerifiedBundle:
    manifest_sha256: str
    view_descriptor_sha256: str
    raw_bundle_semantic_hash: str
    split_semantic_hash: str
    view_semantic_hash: str
    value_sha256: dict[str, str]
    rows: dict[str, list[dict]]


class _Reader:
    def __init__(self, root: Path, expected: Expected):
        self.root = root.resolve(strict=True)
        self.expected = expected
        self.cache: dict[str, bytes] = {}
        self.raw_cache: dict[str, dict] = {}

    def data(self, ref: dict) -> bytes:
        s.closed(ref, ("path", "file_sha256"))
        name, wanted = ref["path"], s.digest(ref["file_sha256"])
        require(type(name) is str and bool(name), "missing file path")
        relative = Path(name)
        require(not relative.is_absolute() and ".." not in relative.parts,
                "bundle path escapes explicit root")
        current = self.root
        for part in relative.parts:
            current = current / part
            require(not current.is_symlink(), "symlink in bundle path")
        try:
            if name not in self.cache:
                self.cache[name] = current.read_bytes()
        except OSError as exc:
            raise D1ContractError(f"missing/unreadable bundle file: {name}") from exc
        data = self.cache[name]
        require(file_sha256(data) == wanted, f"exact file hash mismatch: {name}")
        return data

    def json(self, ref: dict) -> dict:
        result = strict_json(self.data(ref))
        require(type(result) is dict, "JSON document must be an object")
        return result

    def parquet(self, ref: dict, kind: str, schema: dict) -> list[dict]:
        # Optional storage dependency is required only for the actual bundle loader.
        try:
            import pyarrow as pa
            import pyarrow.parquet as pq
        except ImportError as exc:
            raise D1ContractError("Parquet loader requires the existing pyarrow dependency") from exc
        try:
            table = pq.read_table(BytesIO(self.data(ref)))
        except (pa.ArrowException, OSError) as exc:
            raise D1ContractError("invalid Parquet file") from exc
        require(len(table.column_names) == len(set(table.column_names)), "duplicate Parquet column")
        types = {"entity_namespace": pa.string(), "source": pa.string(), "customer_id": pa.string(),
                 "index_date": pa.date32()}
        if kind == "features":
            types.update(feature_version=pa.string(), feature_cutoff_time=pa.timestamp("us", "UTC"),
                         generated_at=pa.timestamp("us", "UTC"))
            for spec in schema["features"]:
                dtype = {"Int64": pa.int64(), "Float32": pa.float32(), "Float64": pa.float64(),
                         "Bool": pa.bool_(), "Category": pa.string(),
                         "VectorFloat32": pa.list_(pa.float32())}[spec["dtype"]]
                types[spec["id"]] = dtype
        elif kind == "quality":
            types.update(feature_id=pa.string(), availability=pa.string(), reasons=pa.list_(pa.string()),
                         audit_counts=pa.map_(pa.string(), pa.int64()), claim_indices=pa.list_(pa.int64()))
        elif kind == "sequence":
            types.update(state=pa.string(), length=pa.int64(), tokens=pa.list_(pa.string()),
                         mask=pa.list_(pa.bool_()), relative_gap_ms=pa.list_(pa.int64()),
                         gap_mask=pa.list_(pa.bool_()), claim_indices=pa.list_(pa.int64()))
        require(set(types) == set(table.column_names), "missing or forbidden Parquet column")
        require(all(table.schema.field(name).type == dtype for name, dtype in types.items()),
                "actual Parquet dtype mismatch")
        rows = table.to_pylist()
        if kind == "quality":
            for row in rows:
                counts = row["audit_counts"]
                require(counts is not None and len({key for key, _ in counts}) == len(counts),
                        "duplicate audit count key")
                row["audit_counts"] = dict(counts)
        return rows

    def tables(self, records: dict, schema: dict, policy: dict, evidence: dict,
               view: str | None) -> tuple[dict, dict, dict]:
        require(set(records) == set(s.TABLES), "incomplete table bundle")
        sh = semantic_hash("schema", s.schema_body(schema))
        ph = semantic_hash("policy", s.policy_body(policy))
        rows, logical, values = {}, {}, {}
        for name in s.TABLES:
            record = s.closed(records[name], ("path", "file_sha256", "value_sha256", "rows"))
            rows[name] = self.parquet(project(record, ("path", "file_sha256")), name, schema)
            require(type(record["rows"]) is int and len(rows[name]) == record["rows"], "row count mismatch")
            logical[name] = s.table_rows(name, rows[name], schema, evidence)
            values[name] = s.table_hash(name, logical[name], sh, ph, view)
            require(values[name] == record["value_sha256"], "table value hash mismatch")
        self.consistency(rows, schema, policy, raw=view is None)
        return rows, logical, values

    def consistency(self, rows: dict, schema: dict, policy: dict, raw: bool) -> None:
        expected = self.expected
        feature_keys = {tlv(s.key(row)): row for row in rows["features"]}
        require({tlv(s.key(row)) for row in rows["sequence"]} == set(feature_keys),
                "sequence key coverage mismatch")
        features = {spec["id"] for spec in schema["features"]}
        require({(tlv(s.key(row)), row["feature_id"]) for row in rows["quality"]} ==
                {(key, fid) for key in feature_keys for fid in features}, "quality key coverage mismatch")
        for group in rows.values():
            for row in group:
                require((row["source"], row["entity_namespace"]) ==
                        (expected.source, expected.entity_namespace), "source/namespace mismatch")
        for row in rows["features"]:
            cutoff = instant(row["feature_cutoff_time"]).astimezone(ZoneInfo("Asia/Seoul"))
            require(cutoff.date() == row["index_date"], "index_date/cutoff mismatch")
            require((cutoff.hour, cutoff.minute, cutoff.second, cutoff.microsecond) == (0, 0, 0, 0),
                    "cutoff must be explicit KST date boundary")
            instant(row["generated_at"])
            if raw:
                require(all(row.get(fid) is None for fid in ("F36", "F37")), "raw learned feature present")
        sequences = {tlv(s.key(row)): row for row in rows["sequence"]}
        for quality in rows["quality"]:
            code, fid = tlv(s.key(quality)), quality["feature_id"]
            value = feature_keys[code][fid]
            available = quality["availability"] == "available"
            require(available == (value is not None), "canonical/quality availability mismatch")
            require(not available or not quality["reasons"], "available value has missing reasons")
            require(available or bool(quality["reasons"]), "unavailable value needs a reason")
            if fid in ("F36", "F37"):
                state = sequences[code]["state"]
                if state == "EMPTY_COMPLETE":
                    require(value is None and "NO_SEQUENCE_INFORMATION" in quality["reasons"],
                            "empty sequence cannot become learned zero/category")
                elif state == "UNKNOWN":
                    require(value is None and not available, "unknown sequence cannot have learned output")
                    require(bool(set(quality["reasons"]) & UNKNOWN_SEQUENCE_REASONS) and
                            "NO_SEQUENCE_INFORMATION" not in quality["reasons"],
                            "unknown sequence needs observation/order reason")
                elif raw:
                    require("TRANSFORM_NOT_FITTED" in quality["reasons"], "raw transform reason")

    def raw(self, ref: dict) -> dict:
        code = ref["file_sha256"]
        manifest = self.json(ref)  # Even cached semantic parents must match exact requested bytes.
        if code in self.raw_cache:
            return self.raw_cache[code]
        require(manifest["contract"] == s.CONTRACT and manifest["serialization"] == SERIALIZATION,
                "raw contract/serialization version mismatch")
        require(manifest["kind"] == "raw", "wrong parent kind")
        require((manifest["source"], manifest["entity_namespace"]) ==
                (self.expected.source, self.expected.entity_namespace), "raw provenance mismatch")
        schema, policy, evidence = [self.json(manifest[name]) for name in ("schema", "policy", "evidence")]
        sh = semantic_hash("schema", s.schema_body(schema))
        ph = semantic_hash("policy", s.policy_body(policy))
        eh = semantic_hash("observation-claims", s.evidence_body(evidence))
        require(sh == self.expected.schema_semantic_hash and ph == self.expected.policy_semantic_hash,
                "schema/policy expectation mismatch")
        require((evidence["source"], evidence["entity_namespace"]) ==
                (self.expected.source, self.expected.entity_namespace), "evidence source mismatch")
        rows, logical, values = self.tables(manifest["tables"], schema, policy, evidence, None)
        require({tlv(s.entity(row)) for row in rows["features"]} ==
                {tlv(s.entity(row)) for row in evidence["entities"]}, "evidence entity scope mismatch")
        for input_ref in manifest["input_files"]:
            self.data(input_ref)
        require(bool(manifest["input_files"]), "missing exact source lineage")
        root = s.raw_hash(sh, ph, eh, values)
        require(root == manifest["raw_bundle_semantic_hash"], "raw semantic root mismatch")
        result = dict(schema=schema, policy=policy, evidence=evidence, rows=rows,
                      logical=logical, root=root)
        self.raw_cache[code] = result
        return result

    def split(self, ref: dict) -> dict:
        record = self.json(ref)
        require(record["serialization"] == SERIALIZATION, "split serialization mismatch")
        require(record["split_contract_version"] == self.expected.split_contract_version and
                record["role_definition_version"] == self.expected.role_definition_version,
                "split version mismatch")
        computed = semantic_hash("split-assignments", s.split_body(record))
        require(computed == record["split_semantic_hash"], "split semantic mismatch")
        return record

    def load(self, manifest_path: str) -> VerifiedBundle:
        e = self.expected
        manifest = self.json({"path": manifest_path, "file_sha256": e.manifest_sha256})
        require(manifest["contract"] == s.CONTRACT and manifest["serialization"] == SERIALIZATION and
                manifest["kind"] == "learned", "learned bundle version/kind mismatch")
        descriptor_ref = manifest["descriptor"]
        require(descriptor_ref["file_sha256"] == e.view_descriptor_sha256, "requested descriptor mismatch")
        descriptor = self.json(descriptor_ref)
        require(descriptor["contract"] == s.DESCRIPTOR_CONTRACT and
                descriptor["serialization"] == SERIALIZATION, "descriptor version mismatch")
        require(not (set(descriptor) & {"view_descriptor_sha256", "value_sha256", "manifest_sha256"}),
                "self/downstream reference in descriptor")
        raw_ref, split_ref = descriptor["raw_parent"], descriptor["split"]
        require(raw_ref["file_sha256"] == e.raw_bundle_manifest_sha256, "requested raw parent mismatch")
        require(split_ref["file_sha256"] == e.split_manifest_sha256, "requested split mismatch")
        raw, split = self.raw(raw_ref), self.split(split_ref)
        allowlist = self.json(descriptor["allowlist"])
        ah = semantic_hash("allowlist", s.allowlist_body(allowlist))
        require(ah == e.allowlist_semantic_hash and allowlist["consumer"] == e.consumer,
                "allowlist context mismatch")
        require(set(allowlist["feature_ids"]) <= {spec["id"] for spec in raw["schema"]["features"]},
                "allowlist references absent feature")
        split_hash = semantic_hash("split-assignments", s.split_body(split))
        require(split_hash == e.split_semantic_hash, "requested actual split mismatch")
        fit, transform = s.scopes(split, e.consumer, e.fit_phase, e.fold_id, descriptor["fit_selection"],
            [s.key(row) for row in raw["rows"]["sequence"] if row["state"] == "VALID"])
        raw_keys = {tlv(s.key(row)) for row in raw["rows"]["features"]}
        require({tlv(s.key(row)) for row in transform["rows"]} <= raw_keys,
                "requested split rows absent from raw parent")
        fh, th = semantic_hash("fit-scope", fit), semantic_hash("transform-scope", transform)
        require((fh, th) == (e.fit_scope_semantic_hash, e.transform_scope_semantic_hash),
                "requested fit/transform scope mismatch")
        graph = descriptor["object_graph"]
        require(set(graph) == set(e.objects), "requested object roles mismatch")
        bindings, visiting = {}, set()

        def visit(role: str) -> dict:
            require(role not in visiting, "object graph cycle")
            if role in bindings:
                return bindings[role]
            visiting.add(role)
            node, wanted = graph[role], e.objects[role]
            require(node["metadata"]["file_sha256"] == wanted["object_metadata_file_sha256"],
                    "requested object metadata mismatch")
            meta = self.json(node["metadata"])
            require(meta["metadata_contract_version"] == "d1-object-metadata/1-proposed",
                    "object metadata contract version mismatch")
            require(meta["role"] == role, "object role mismatch")
            require(role in ("encoder", "cluster"), "unsupported D1 transform role")
            upstream = []
            for edge in meta["upstream"]:
                s.closed(edge, ("role", "object_file_sha256"))
                require(edge["role"] in graph, "unknown upstream role")
                parent = visit(edge["role"])
                require(parent["status"] == "fitted" and
                        parent["object_file_sha256"] == edge["object_file_sha256"],
                        "wrong upstream object connection")
                upstream.append(parent)
            require(len({item["role"] for item in upstream}) == len(upstream), "duplicate upstream")
            if meta["status"] == "fitted":
                require((role == "encoder" and not upstream) or
                        (role == "cluster" and [item["role"] for item in upstream] == ["encoder"]),
                        "unsupported transform stage dependency")
                require(node["object"]["file_sha256"] == wanted["object_file_sha256"],
                        "requested object bytes mismatch")
                self.data(node["object"])
                require(meta["object_format_version"] == wanted["object_format_version"] and
                        meta["implementation_ref"] == wanted["implementation_ref"] and
                        meta["fit_facts"]["runtime"] == wanted["runtime"], "object/runtime version mismatch")
                training_raw, training_split = self.raw(meta["training_raw_parent"]), self.split(meta["training_split"])
                # Establish membership before applying a selection predicate. A missing
                # row is not evidence of an empty/unusable sequence and cannot be dropped.
                declared_train, _ = s.scopes(training_split, e.consumer, e.fit_phase, e.fold_id,
                    {**descriptor["fit_selection"], "input_definition": "all_train_rows"})
                training_keys = {tlv(s.key(row)) for row in training_raw["rows"]["features"]}
                require({tlv(row) for row in declared_train["rows"]} <= training_keys,
                        "declared Train rows absent from training raw parent")
                train_fit, _ = s.scopes(training_split, e.consumer, e.fit_phase, e.fold_id,
                    descriptor["fit_selection"], [s.key(row) for row in training_raw["rows"]["sequence"]
                                                  if row["state"] == "VALID"])
                require(semantic_hash("fit-scope", train_fit) == fh, "object fit scope differs from view")
                train_keys = {tlv(row) for row in train_fit["rows"]}
                require(bool(train_keys), "fitted object has no valid Train rows")
                inputs, input_storage = {}, {}
                for kind in s.TABLES:
                    records = self.parquet(meta["fit_inputs"][kind], kind, raw["schema"])
                    input_storage[kind] = records
                    inputs[kind] = s.table_rows(kind, records, raw["schema"], training_raw["evidence"])
                    require({tlv(s.key(row)) for row in records} == train_keys,
                            "fit inputs must be exactly selected Train keys")
                    parent_rows = [row for row in training_raw["logical"][kind] if tlv(s.key(row)) in train_keys]
                    if not upstream:
                        require(inputs[kind] == parent_rows, "raw fit input values differ")
                    else:
                        current = inputs[kind]
                        if kind == "features":
                            fields = (*s.KEY, "feature_version", "feature_cutoff_time", *(
                                spec["id"] for spec in raw["schema"]["features"] if spec["id"] not in ("F36", "F37")))
                            current = [project(row, fields) for row in current]
                            parent_rows = [project(row, fields) for row in parent_rows]
                        elif kind == "quality":
                            current = [row for row in current if row["feature_id"] not in ("F36", "F37")]
                            parent_rows = [row for row in parent_rows if row["feature_id"] not in ("F36", "F37")]
                        require(tlv(current) == tlv(parent_rows), f"upstream fit raw {kind} differ")
                self.consistency(input_storage, raw["schema"], raw["policy"], raw=not upstream)
                if role == "cluster":
                    require(all(row.get("F37") is None for row in input_storage["features"]),
                            "cluster fit input contains its own output")
                ih = s.fit_input_hash(role, e.schema_semantic_hash, e.policy_semantic_hash, ah, upstream, inputs)
                facts = meta["fit_facts"]
                require(all(facts[name] == value for name, value in {
                    "consumer": e.consumer, "fit_phase": e.fit_phase, "fold_id": e.fold_id,
                    "fit_scope_semantic_hash": fh, "fit_input_value_sha256": ih,
                    "schema_semantic_hash": e.schema_semantic_hash, "policy_semantic_hash": e.policy_semantic_hash,
                    "allowlist_semantic_hash": ah}.items()), "frozen fit facts mismatch")
                binding = s.object_binding(meta, node["object"]["file_sha256"], upstream)
            else:
                require(node.get("object") is None and wanted["object_file_sha256"] is None,
                        "unfitted object must not have bytes")
                binding = s.object_binding(meta, "", upstream)
            visiting.remove(role)
            bindings[role] = binding
            return binding

        for role in sorted(graph):
            visit(role)
        payload = {"view_semantic_contract_version": s.VIEW_CONTRACT, "raw_bundle_semantic_hash": raw["root"],
                   "consumer": e.consumer, "schema_semantic_hash": e.schema_semantic_hash,
                   "policy_semantic_hash": e.policy_semantic_hash, "allowlist_semantic_hash": ah,
                   "split_semantic_hash": split_hash, "fit_phase": e.fit_phase, "fold_id": e.fold_id,
                   "fit_scope_semantic_hash": fh, "transform_scope_semantic_hash": th,
                   "object_bindings": [bindings[role] for role in sorted(bindings)]}
        vh = s.view_hash(payload)
        require(tlv(payload) == tlv(descriptor["semantic_payload"]) and
                vh == descriptor["view_semantic_hash"] == manifest["view_semantic_hash"],
                "view semantic payload mismatch")
        rows, logical, values = self.tables(manifest["tables"], raw["schema"], raw["policy"], raw["evidence"], vh)
        raw_features = {tlv(s.key(row)): row for row in raw["logical"]["features"]}
        immutable_fields = (*s.KEY, "feature_version", "feature_cutoff_time", *(
            spec["id"] for spec in raw["schema"]["features"] if spec["id"] not in ("F36", "F37")))
        for row in logical["features"]:
            require(tlv(project(row, immutable_fields)) ==
                    tlv(project(raw_features.get(tlv(s.key(row)), {}), immutable_fields)),
                    "learned view changed raw canonical values")
        output_keys = {tlv(s.key(row)) for row in logical["features"]}
        require(logical["sequence"] == [row for row in raw["logical"]["sequence"] if
                                        tlv(s.key(row)) in output_keys], "learned view changed raw sequence")
        require([row for row in logical["quality"] if row["feature_id"] not in ("F36", "F37")] ==
                [row for row in raw["logical"]["quality"] if tlv(s.key(row)) in output_keys and
                 row["feature_id"] not in ("F36", "F37")], "learned view changed raw quality")
        for fid, role in (("F36", "encoder"), ("F37", "cluster")):
            if fid in {spec["id"] for spec in raw["schema"]["features"]}:
                fitted = role in bindings and bindings[role]["status"] == "fitted"
                for row in rows["features"]:
                    require(fitted or row[fid] is None, "output uses an unfitted transform")
        require({tlv(s.key(row)) for row in rows["features"]} ==
                {tlv(s.key(row)) for row in transform["rows"]}, "output transform scope mismatch")
        return VerifiedBundle(e.manifest_sha256, e.view_descriptor_sha256, raw["root"], split_hash, vh, values, rows)


def load_bundle(root: str | Path, manifest_path: str, expected: Expected) -> VerifiedBundle:
    """Return only after the entire pinned bundle validates; failure returns no rows."""
    try:
        return _Reader(Path(root), expected).load(manifest_path)
    except (KeyError, TypeError, AttributeError, IndexError) as exc:
        raise D1ContractError("missing or malformed contract field") from exc
