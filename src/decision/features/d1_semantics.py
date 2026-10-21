"""Closed D1 review-contract projections; physical references never enter implicitly."""

from __future__ import annotations

import re
from typing import Any

from .d1_serialization import (
    Float32, Float64, calendar_date, canonical_set, instant, project, require,
    semantic_hash, tlv,
)

CONTRACT = "d1-features/0.2.2-proposed"
VIEW_CONTRACT = "d1-view-semantic/1-proposed"
DESCRIPTOR_CONTRACT = "d1-view-descriptor/1-proposed"
KEY = ("entity_namespace", "source", "customer_id", "index_date")
TABLES = ("features", "quality", "sequence")
PHYSICAL = {"generated_at", "path", "file_sha256", "manifest_sha256", "host", "pid",
            "provenance", "bundle_id", "view_descriptor_sha256"}


def digest(value: Any) -> str:
    require(type(value) is str and bool(re.fullmatch("[0-9a-f]{64}", value)),
            "invalid SHA-256 reference")
    return value


def text(value: Any) -> str:
    require(type(value) is str and bool(value), "nonempty string required")
    tlv(value)
    return value


def closed(record: Any, fields: tuple[str, ...]) -> dict:
    result = project(record, fields)
    require(set(record) == set(fields), "unknown semantic field")
    return result


def semantic_settings(value: Any) -> Any:
    """Explicit parameters only; no whole metadata/provenance object is accepted."""
    if type(value) is dict:
        require(not (set(value) & PHYSICAL) and
                not any(key.endswith(("_manifest_sha256", "_file_sha256")) for key in value),
                "physical reference in semantic settings")
        return {text(key): semantic_settings(item) for key, item in value.items()}
    if type(value) is list:
        return [semantic_settings(item) for item in value]
    tlv(value)
    return value


def schema_body(record: dict) -> dict:
    body = project(record, ("schema_version", "features", "key_definition", "tokens",
                            "feature_order"))
    text(body["schema_version"])
    require(body["key_definition"] == list(KEY), "unsupported logical key definition")
    ids = []
    names = []
    for item in body["features"]:
        closed(item, ("id", "name", "dtype", "dimension", "nullable",
                      "definition_version", "categories"))
        require(bool(re.fullmatch(r"F(?:0[1-9]|[1-3][0-9]|4[0-2])", item["id"])),
                "feature outside D1 candidate set")
        require(item["name"] == item["id"], "feature columns use explicit D1 IDs")
        require(item["dtype"] in ("Int64", "Float32", "Float64", "Bool", "Category",
                                  "VectorFloat32"), "unsupported feature type")
        require(type(item["nullable"]) is bool, "nullable must be Bool")
        require(type(item["dimension"]) is int and item["dimension"] >= 0,
                "invalid feature dimension")
        require((item["dimension"] > 0) == (item["dtype"] == "VectorFloat32"),
                "dimension/type mismatch")
        text(item["definition_version"])
        canonical_set(item["categories"])
        ids.append(item["id"])
        names.append(item["name"])
    require(len(set(ids)) == len(ids) and len(set(names)) == len(names), "duplicate feature")
    require(body["feature_order"] == ids == sorted(ids), "D1 feature order mismatch")
    require(type(body["tokens"]) is list and body["tokens"] and body["tokens"][0] == "PAD",
            "token vocabulary must start with PAD")
    canonical_set(body["tokens"])
    return body


POLICY_FIELDS = {
    "cutoff": ("operator", "boundary", "timezone", "precision"),
    "session": ("definition_version", "completion_rule", "window_membership"),
    "duplicates": ("event_id_policy", "row_key_policy"),
    "missing": ("definition_version", "unknown_policy", "zero_denominator_policy"),
    "outlier": ("definition_version",),
    "sequence": ("length", "pad_direction", "token_version", "ordering_rule", "empty_policy"),
    "fit_protocol": ("version", "train_role"),
}


def policy_body(record: dict) -> dict:
    body = project(record, ("policy_id", "policy_version", "windows", "denominators",
                            *POLICY_FIELDS))
    text(body["policy_id"])
    text(body["policy_version"])
    for section, fields in POLICY_FIELDS.items():
        closed(body[section], fields)
    body["windows"] = canonical_set([
        closed(window, ("name", "length_days", "offset_days")) for window in body["windows"]])
    for spec in body["denominators"].values():
        closed(spec, ("definition", "zero_policy"))
    require(body["cutoff"]["operator"] in ("lt", "le"), "explicit cutoff operator required")
    require(body["cutoff"]["timezone"] == "Asia/Seoul", "D1 date timezone mismatch")
    require(body["sequence"]["length"] == 30, "sequence length must be 30")
    require(body["sequence"]["pad_direction"] == "left", "left padding required")
    require(body["fit_protocol"]["train_role"] == "Train", "Train fit required")
    return semantic_settings(body)


def allowlist_body(record: dict) -> dict:
    body = project(record, ("allowlist_version", "consumer", "feature_ids", "channels"))
    text(body["allowlist_version"])
    text(body["consumer"])
    canonical_set(body["feature_ids"])
    canonical_set(body["channels"])
    require(all(bool(re.fullmatch(r"F\d{2}", fid)) for fid in body["feature_ids"]),
            "metadata/target cannot be a feature")
    return body


def key(row: dict) -> dict:
    body = project(row, KEY)
    for name in KEY[:-1]:
        text(body[name])
    body["index_date"] = calendar_date(body["index_date"])
    return body


def entity(row: dict) -> dict:
    body = project(row, KEY[:-1])
    for value in body.values():
        text(value)
    return body


def ordered(rows: list[dict], identity) -> list[dict]:
    pairs = [(tlv(identity(row)), row) for row in rows]
    require(len({code for code, _ in pairs}) == len(pairs), "duplicate logical key")
    return [row for _, row in sorted(pairs, key=lambda pair: pair[0])]


def evidence_body(record: dict) -> dict:
    body = project(record, ("provider", "provider_role", "contract_version", "source",
                            "entity_namespace", "entities", "claims"))
    for name in ("provider", "provider_role", "contract_version", "source", "entity_namespace"):
        text(body[name])
    body["entities"] = canonical_set([entity(row) for row in body["entities"]])
    claims = []
    for item in body["claims"]:
        claim = closed(item, ("event_types", "capability", "start", "end", "state", "gaps",
                              "availability_basis", "ordering", "session_completion"))
        claim = dict(claim)
        claim["start"], claim["end"] = instant(claim["start"]), instant(claim["end"])
        require(claim["start"] <= claim["end"], "reversed observation period")
        claim["event_types"] = canonical_set(claim["event_types"])
        claim["gaps"] = canonical_set([{
            "start": instant(closed(gap, ("start", "end"))["start"]),
            "end": instant(gap["end"]),
        } for gap in claim["gaps"]])
        basis = dict(closed(claim["availability_basis"], ("as_of", "rule")))
        basis["as_of"] = instant(basis["as_of"])
        text(basis["rule"])
        claim["availability_basis"] = basis
        claim["ordering"] = explicit_evidence(claim["ordering"])
        claim["session_completion"] = explicit_evidence(claim["session_completion"])
        claims.append(claim)
    body["claims"] = canonical_set(claims)
    return body


def explicit_evidence(value: Any) -> str:
    """Closed review-only evidence vocabulary; publication is not calculation time."""
    if type(value) is str:
        require(value == "explicit", "unsupported explicit evidence rule")
        return value
    require(type(value) is dict and "rule" in value and
            set(value) <= {"rule", "asserted_at", "assessed_at"},
            "unsupported explicit evidence structure")
    require(value["rule"] == "explicit", "unsupported explicit evidence rule")
    for field in ("asserted_at", "assessed_at"):
        if field in value:
            instant(value[field])
    return "explicit"


def typed(value: Any, spec: dict) -> Any:
    if value is None:
        require(spec["nullable"], "non-nullable feature is null")
        return None
    dtype = spec["dtype"]
    if dtype == "Int64":
        require(type(value) is int, "Int64 feature has wrong type")
    elif dtype == "Bool":
        require(type(value) is bool, "Bool feature has wrong type")
    elif dtype in ("Float32", "Float64"):
        require(type(value) is float, "float feature has wrong type")
        value = Float32(value) if dtype == "Float32" else Float64(value)
    elif dtype == "VectorFloat32":
        require(type(value) is list and len(value) == spec["dimension"], "vector dimension")
        require(all(type(item) is float for item in value), "vector element type")
        value = [Float32(item) for item in value]
    elif dtype == "Category":
        require(type(value) is str and value in spec["categories"], "unknown category")
    tlv(value)
    return value


def table_rows(kind: str, rows: list[dict], schema: dict, evidence: dict) -> list[dict]:
    specs = schema_body(schema)["features"]
    claims = evidence_body(evidence)["claims"]
    result = []
    for row in rows:
        item = key(row)
        if kind == "features":
            required = ("feature_version", "feature_cutoff_time", *(spec["id"] for spec in specs))
            project(row, required)
            require(row["feature_version"] == schema["schema_version"], "row schema version")
            item.update(feature_version=row["feature_version"],
                        feature_cutoff_time=instant(row["feature_cutoff_time"]))
            item.update({spec["id"]: typed(row[spec["id"]], spec) for spec in specs})
        elif kind == "quality":
            item.update(project(row, ("feature_id", "availability", "reasons", "audit_counts")))
            require(item["feature_id"] in {spec["id"] for spec in specs}, "unknown quality feature")
            require(item["availability"] in ("available", "unavailable"), "quality availability")
            item["reasons"] = sorted(set(row["reasons"]), key=lambda value: value.encode("utf-8"))
            require(all(type(value) is int and value >= 0 for value in row["audit_counts"].values()),
                    "invalid audit count")
            require(type(row["claim_indices"]) is list and all(
                type(index) is int and 0 <= index < len(claims) for index in row["claim_indices"]),
                "unresolved observation claim")
            item["observation_claims"] = canonical_set([claims[index] for index in row["claim_indices"]])
        elif kind == "sequence":
            item.update(project(row, ("state", "length", "tokens", "mask", "relative_gap_ms", "gap_mask")))
            require(item["state"] in ("VALID", "EMPTY_COMPLETE", "UNKNOWN"), "sequence state")
            require(type(item["length"]) is int and 0 <= item["length"] <= 30, "sequence length")
            require(all(type(row[name]) is list and len(row[name]) == 30 for name in
                        ("tokens", "mask", "relative_gap_ms", "gap_mask")), "sequence array length")
            require(all(type(v) is bool for v in row["mask"] + row["gap_mask"]), "mask type")
            require(all(v is None or (type(v) is int and v >= 0) for v in row["relative_gap_ms"]),
                    "gap type")
            require(all(v in schema["tokens"] for v in row["tokens"]), "unknown token")
            length = item["length"]
            require(row["mask"] == [False] * (30 - length) + [True] * length, "padding mask")
            require(all(v == "PAD" for v in row["tokens"][:30-length]) and
                    all(v != "PAD" for v in row["tokens"][30-length:]), "padding tokens")
            first = 30-length
            require(all(gap is None and not mask for gap, mask in
                        zip(row["relative_gap_ms"][:first], row["gap_mask"][:first])),
                    "padding gap must be null/false")
            if length:
                require(row["relative_gap_ms"][first] is None and not row["gap_mask"][first],
                        "first actual event gap must be null/false")
                require(all(row["gap_mask"][first+1:]), "following event gap mask must be true")
                require(all(type(gap) is int and gap >= 0 for gap in row["relative_gap_ms"][first+1:]),
                        "following event gap must be nonnegative Int64")
            require(item["state"] != "EMPTY_COMPLETE" or length == 0, "empty sequence has events")
            require(item["state"] != "VALID" or length > 0, "valid sequence is empty")
            require(type(row["claim_indices"]) is list and all(
                type(index) is int and 0 <= index < len(claims) for index in row["claim_indices"]),
                "unresolved ordering claim")
            item["ordering_claims"] = canonical_set([claims[index] for index in row["claim_indices"]])
        else:
            require(False, "unknown table kind")
        result.append(item)
    return ordered(result, lambda row: {**key(row), **(
        {"feature_id": row["feature_id"]} if kind == "quality" else {})})


def table_hash(kind: str, rows: list[dict], schema_hash: str, policy_hash: str,
               view_hash: str | None = None) -> str:
    return semantic_hash("table-values", {"table_kind": kind,
        "schema_semantic_hash": digest(schema_hash), "policy_semantic_hash": digest(policy_hash),
        "view_semantic_hash": None if view_hash is None else digest(view_hash), "rows": rows})


def raw_hash(schema_hash: str, policy_hash: str, evidence_hash: str, tables: dict) -> str:
    require(set(tables) == set(TABLES), "raw table set")
    return semantic_hash("raw-bundle", {"schema_semantic_hash": digest(schema_hash),
        "policy_semantic_hash": digest(policy_hash), "evidence_semantic_hash": digest(evidence_hash),
        "tables": {name: digest(value) for name, value in tables.items()}})


def split_body(record: dict) -> dict:
    body = project(record, ("split_contract_version", "role_definition_version", "split_policy",
                            "entity_assignments", "row_assignments"))
    policy = closed(body.pop("split_policy"), ("version", "method", "seed", "parameters"))
    body["split_policy_semantic_hash"] = semantic_hash("split-policy", semantic_settings(policy))
    text(body["split_contract_version"])
    text(body["role_definition_version"])
    entities = []
    for row in body["entity_assignments"]:
        closed(row, (*KEY[:-1], "role"))
        require(row["role"] in ("Train", "Validation", "Test", "Holdout"), "outer split role")
        entities.append({**entity(row), "role": row["role"]})
    body["entity_assignments"] = ordered(entities, entity)
    outer = {tlv(entity(row)): row["role"] for row in entities}
    rows = []
    inner_roles = {}
    for row in body["row_assignments"]:
        closed(row, (*KEY, "consumer", "fit_phase", "fold_id", "role", "excluded", "reason"))
        require(type(row["excluded"]) is bool, "exclusion must be Bool")
        require(row["role"] in ("Train", "Validation", "Test", "Holdout"), "row split role")
        outer_role = outer.get(tlv(entity(row)))
        require(outer_role is not None, "split row missing entity")
        require((outer_role == "Train" and row["role"] in ("Train", "Validation")) or
                row["role"] == outer_role, "same customer crosses outer split roles")
        require(not row["excluded"] or bool(row["reason"]), "missing exclusion reason")
        text(row["consumer"]); text(row["fit_phase"]); text(row["fold_id"])
        if not row["excluded"]:
            context = tlv({**entity(row), **project(row, ("consumer", "fit_phase", "fold_id"))})
            require(context not in inner_roles or inner_roles[context] == row["role"],
                    "same customer crosses roles within fold")
            inner_roles[context] = row["role"]
        rows.append({**row, **key(row)})
    body["row_assignments"] = ordered(rows, lambda row: project(row, (*KEY, "consumer", "fit_phase", "fold_id")))
    return body


def scopes(split: dict, consumer: str, phase: str, fold: str, selection: dict,
           nonempty_keys: list[dict] | None = None) -> tuple[dict, dict]:
    selected = [row for row in split_body(split)["row_assignments"] if
                (row["consumer"], row["fit_phase"], row["fold_id"]) == (consumer, phase, fold)]
    require(bool(selected), "requested split context absent")
    train = [row for row in selected if row["role"] == "Train" and not row["excluded"]]
    selection = closed(selection, ("input_definition", "target_definition"))
    require(selection["input_definition"] in ("all_train_rows", "nonempty_sequences"),
            "unsupported explicit fit selection")
    require(selection["target_definition"] is None, "supervised target contract not implemented")
    if selection["input_definition"] == "nonempty_sequences":
        require(nonempty_keys is not None, "actual nonempty sequence membership required")
        allowed = {tlv(key(row)) for row in nonempty_keys}
        train = [row for row in train if tlv(key(row)) in allowed]
    entities = {tlv(entity(row)): entity(row) for row in train}
    fit = {"consumer": consumer, "fit_phase": phase, "fold_id": fold,
           "entities": [entities[code] for code in sorted(entities)],
           "rows": canonical_set([key(row) for row in train]), "role": "Train", "selection": selection}
    transform = {"consumer": consumer, "rows": canonical_set([
        {**key(row), "role": row["role"]} for row in selected if not row["excluded"]])}
    return fit, transform


def object_binding(metadata: dict, object_hash: str, upstream: list[dict]) -> dict:
    body = project(metadata, ("role", "status", "reason"))
    require(body["status"] in ("fitted", "not_fitted", "not_applicable"), "object status")
    if body["status"] == "fitted":
        facts = closed(metadata["fit_facts"], ("consumer", "fit_phase", "fold_id",
            "fit_scope_semantic_hash", "fit_input_value_sha256", "schema_semantic_hash",
            "policy_semantic_hash", "allowlist_semantic_hash", "parameters", "seed", "runtime"))
        closed(facts["runtime"], ("python", "libraries", "serializer", "options"))
        semantic_settings(facts["parameters"]); semantic_settings(facts["runtime"])
        body.update(object_file_sha256=digest(object_hash),
                    object_format_version=text(metadata["object_format_version"]),
                    implementation_ref=text(metadata["implementation_ref"]),
                    fit_facts=facts, upstream_object_bindings=upstream)
    else:
        text(body["reason"])
        require(not upstream, "unfitted object cannot have upstream")
    return body


def fit_input_hash(role: str, schema_hash: str, policy_hash: str, allowlist_hash: str,
                   upstream: list[dict], tables: dict, target_definition=None, target_rows=None) -> str:
    require(target_definition is None and target_rows is None,
            "supervised transform requires a separately reviewed target contract")
    return semantic_hash("fit-inputs", {"stage_role": role, "schema_semantic_hash": schema_hash,
        "policy_semantic_hash": policy_hash, "allowlist_semantic_hash": allowlist_hash,
        "upstream_object_bindings": upstream, "feature_rows": tables["features"],
        "sequence_rows": tables["sequence"], "quality_rows": tables["quality"],
        "target_definition": None, "target_rows": None})


VIEW_FIELDS = ("view_semantic_contract_version", "raw_bundle_semantic_hash", "consumer",
               "schema_semantic_hash", "policy_semantic_hash", "allowlist_semantic_hash",
               "split_semantic_hash", "fit_phase", "fold_id", "fit_scope_semantic_hash",
               "transform_scope_semantic_hash", "object_bindings")


def view_hash(payload: dict) -> str:
    body = closed(payload, VIEW_FIELDS)
    require(body["view_semantic_contract_version"] == VIEW_CONTRACT, "view contract version")
    roles = [binding["role"] for binding in body["object_bindings"]]
    require(roles == sorted(set(roles)), "object bindings must be unique and role-sorted")
    for name in VIEW_FIELDS:
        if name.endswith("_hash"):
            digest(body[name])
    return semantic_hash("learned-view", body)
