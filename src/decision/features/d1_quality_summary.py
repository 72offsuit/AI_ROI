"""Descriptive raw null counts for caller-supplied K populations; no quality gate."""

from __future__ import annotations

from collections import Counter
import math

from .d1_calculate import DEFINITIONS, FeatureOutput
from .d1_semantics import KEY, key
from .d1_serialization import require, tlv

QUALITY_VERSION = "d1-raw-quality/1-proposed"
FEATURE_IDS = frozenset(definition[0] for definition in DEFINITIONS)


def _identity(record):
    require(type(record) is dict, "quality key must be an object")
    normalized = key(record)
    return tuple(normalized[name] for name in KEY)


def aggregate_raw_quality(output: FeatureOutput, *, population: list[dict], feature_ids: list[str]) -> dict:
    require(type(output) is FeatureOutput, "canonical FeatureOutput required")
    require(type(output.feature_rows) is list and type(output.quality_rows) is list, "canonical/quality row lists required")
    require(type(population) is list, "explicit K population required")
    require(type(feature_ids) is list and bool(feature_ids) and
            all(type(fid) is str and fid in FEATURE_IDS for fid in feature_ids), "explicit known Feature IDs required")
    require(len(set(feature_ids)) == len(feature_ids), "duplicate quality Feature ID")
    identities = []
    for member in population:
        require(type(member) is dict and set(member) == set(KEY), "population must contain only explicit K fields")
        identities.append(_identity(member))
    require(len(set(identities)) == len(identities), "duplicate population K")
    identities.sort(key=lambda identity: tlv(dict(zip(KEY, identity))))
    features, qualities = {}, {}
    for row in output.feature_rows:
        identity = _identity(row)
        require(identity not in features, "duplicate canonical K")
        features[identity] = row
    for row in output.quality_rows:
        identity = _identity(row)
        require(type(row.get("feature_id")) is str and row["feature_id"] in FEATURE_IDS, "invalid quality Feature ID")
        pair = (identity, row["feature_id"])
        require(pair not in qualities, "duplicate quality K/Feature")
        qualities[pair] = row
    count, summaries = len(identities), []
    for fid in feature_ids:
        missing, reasons = 0, Counter()
        for identity in identities:
            require(identity in features, "population K missing canonical row")
            require(fid in features[identity], "requested canonical Feature column missing")
            require((identity, fid) in qualities, "population K/Feature missing quality row")
            value, quality = features[identity][fid], qualities[(identity, fid)]
            codes = quality.get("reasons")
            require(type(codes) is list and all(type(code) is str and code for code in codes) and
                    len(set(codes)) == len(codes), "quality reasons must be unique nonempty codes")
            if type(value) is float:
                require(math.isfinite(value), "nonfinite canonical quality input")
            if value is None:
                require(quality.get("availability") == "unavailable" and bool(codes),
                        "null canonical/quality availability mismatch")
                missing += 1
                reasons.update(codes)
            else:
                require(quality.get("availability") == "available" and not codes,
                        "available canonical/quality availability mismatch")
        summaries.append(dict(feature_id=fid, denominator=count, missing_count=missing, available_count=count-missing,
            missing_rate=missing/count if count else None, reason_counts=dict(sorted(reasons.items())),
            status="summarized" if count else "unavailable", reasons=[] if count else ["ZERO_DENOMINATOR"],
            official_verdict=None))
    return dict(aggregation_version=QUALITY_VERSION, population_definition="caller_supplied_K",
                population=[dict(zip(KEY, identity)) for identity in identities], population_count=count,
                entity_count=len({identity[:-1] for identity in identities}), feature_ids=list(feature_ids),
                summaries=summaries, excluded_count=0, short_history_adjustment="not_applied", official_verdict=None,
                pending_decisions=["SD6", "SD7"])
