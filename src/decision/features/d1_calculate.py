"""Past-only canonical Feature calculations. No fit, imputation, publication or implicit policy."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from datetime import date, datetime, timezone
import math
import statistics

from src.measurement.schema import SCHEMA_VERSION

from .d1_feature_inputs import (
    ACTIVITY, KST, Entity, EventBatch, ObservationClaim, TimePolicy, Window,
    check_claims, observation_reasons, t0, timestamp,
)
from .d1_serialization import require, semantic_hash, tlv
from .d1_semantics import typed

FEATURE_VERSION = "d1-calculation/1-proposed"
VISITS = frozenset({"session_start", "return_visit"})
PURCHASE = frozenset({"purchase"})

# ID, public name, formula, unit, period, event sources. Definitions are v0.2.2 A.
DEFINITIONS = [
    ("F01", "recency", "(T0-last_purchase)/86400", "days", "H", "purchase"),
    ("F02", "frequency_90d", "count(distinct order_id)", "orders", "90d", "purchase"),
    ("F03", "monetary_90d", "sum(net order_amount per unique order)", "KRW", "90d", "purchase"),
    ("F04", "aov_90d", "F03/F02", "KRW/order", "90d", "purchase"),
    ("F05", "avg_purchase_interval", "mean(adjacent unique purchase gaps)", "days", "H", "purchase"),
    ("F06", "purchase_interval_cv_90d", "population_sd(gaps)/mean(gaps); >=2 gaps", "ratio", "90d", "purchase"),
    ("F07", "purchase_cycle_anomaly", "F01/F05", "ratio", "H", "purchase"),
    ("F08", "visit_count_60d", "count(distinct session_id)", "sessions", "60d", "session_start,return_visit"),
    ("F09", "visit_recency", "(T0-last_visit)/86400", "days", "H", "session_start,return_visit"),
    ("F10", "active_days_30d", "count(distinct KST activity date)", "days", "30d", "A"),
    ("F11", "page_view_count_60d", "count(page_view)", "events", "60d", "page_view"),
    ("F12", "product_view_count_60d", "count(product_view)", "events", "60d", "product_view"),
    ("F13", "distinct_viewed_products_180d", "count(distinct product_id)", "products", "180d", "product_view"),
    ("F14", "search_count_60d", "count(search)", "events", "60d", "search"),
    ("F15", "add_to_cart_count_60d", "count(add_to_cart)", "events", "60d", "add_to_cart"),
    ("F16", "remove_from_cart_count_60d", "count(remove_from_cart)", "events", "60d", "remove_from_cart"),
    ("F17", "checkout_count_60d", "count(distinct order_id)", "orders", "60d", "checkout_start"),
    ("F18", "cs_contact_count_60d", "count(cs_contact)", "events", "60d", "cs_contact"),
    ("F19", "review_count_180d", "count(review)", "events", "180d", "review"),
    ("F20", "coupon_exposure_count_180d", "count(coupon_exposed)", "events", "180d", "coupon_exposed"),
    ("F21", "coupon_used_order_count_180d", "count(distinct order_id)", "orders", "180d", "coupon_use"),
    ("F22", "days_since_last_campaign_180d", "(T0-last_campaign)/86400", "days", "180d", "campaign_exposed"),
    ("F23", "category_entropy_180d", "-sum(p*ln(p))", "nats", "180d", "product_view"),
    ("F24", "dominant_category_share_180d", "max(category count)/product_view count", "ratio", "180d", "product_view"),
    ("F25", "visit_count_change_2w", "recent14 visits/previous14 visits", "ratio", "14d+14d", "session_start,return_visit"),
    ("F26", "purchase_frequency_change", "(recent30 orders-previous30 orders)/30", "orders/day", "30d+30d", "purchase"),
    ("F27", "purchase_interval_change", "mean(recent45 internal gaps)-mean(previous45 internal gaps)", "days", "45d+45d", "purchase"),
    ("F28", "weekday_purchase_ratio", "KST weekday orders/all orders", "ratio", "90d", "purchase"),
    ("F29", "morning_activity_ratio", "06<=KST hour<12 activity/all activity", "ratio", "90d", "A"),
    ("F30", "evening_activity_ratio", "18<=KST hour<24 activity/all activity", "ratio", "90d", "A"),
    ("F31", "avg_session_duration", "mean(completed session duration)", "seconds", "60d", "session facts"),
    ("F32", "page_views_per_session", "completed session page_views/completed sessions", "views/session", "60d", "session facts"),
    ("F33", "search_to_purchase_conversion", "search conversion true/(true+false); unknown -> null", "ratio", "60d", "session facts"),
    ("F34", "session_duration_change", "recent14 duration mean-previous14 duration mean", "seconds", "14d+14d", "session facts"),
    ("F35", "cart_conversion_change", "recent30 cart conversion-previous30 cart conversion", "ratio difference", "30d+30d", "session facts"),
    ("F36", "recent_event_sequence_embedding", "Train-fitted sequence representation", "vector", "H", "16 event types"),
    ("F37", "behavior_pattern_cluster_id", "Train-fitted cluster(F36)", "category", "F36", "F36"),
    ("F38", "current_journey_stage", "approved public journey state table", "category", "lifetime", "approved journey inputs"),
    ("F39", "days_in_current_stage", "(T0-stage entry)/86400", "days", "lifetime", "approved journey inputs"),
    ("F40", "days_signup_to_first_purchase", "KST first purchase date-KST signup date", "days", "lifetime", "approved signup"),
    ("F41", "repurchase_count", "max(lifetime unique purchases-1,0)", "orders", "lifetime", "lifetime purchase evidence"),
    ("F42", "weekend_purchase_ratio", "KST weekend orders/all orders", "ratio", "90d", "purchase"),
]
INTEGER_IDS = frozenset({"F02", "F03", "F08", "F10", "F11", "F12", "F13", "F14", "F15", "F16",
                         "F17", "F18", "F19", "F20", "F21", "F40", "F41"})
CORE_IDS = tuple(row[0] for row in DEFINITIONS if row[0] <= "F30" or row[0] == "F42")


def dtype(feature_id: str) -> str:
    return ("Int64" if feature_id in INTEGER_IDS else "VectorFloat32" if feature_id == "F36" else
            "Category" if feature_id in ("F37", "F38") else "Float64")


def core_feature_schema() -> dict:
    """Only implemented event columns; descriptive names remain in the Dictionary."""
    from .d1_feature_inputs import EVENT_TYPES
    return dict(schema_version=FEATURE_VERSION,features=[dict(id=fid,name=fid,dtype=dtype(fid),dimension=0,
        nullable=True,definition_version="D1-v0.2.2/"+fid,categories=[]) for fid in CORE_IDS],
        key_definition=["entity_namespace","source","customer_id","index_date"],
        tokens=["PAD",*sorted(EVENT_TYPES)],feature_order=list(CORE_IDS))


@dataclass(frozen=True)
class FeatureValue:
    value: int | float | None
    reasons: tuple[str, ...]
    audit_counts: dict[str, int]
    windows: tuple[dict, ...]
    evidence_refs: tuple[str, ...]
    numerator: int | float | None = None
    denominator: int | float | None = None

    @property
    def availability(self):
        return "available" if self.value is not None else "unavailable"


def outcome(value, *, reasons=(), audit=None, windows=(), refs=(), numerator=None, denominator=None):
    reasons = tuple(sorted(set(reasons)))
    require(value is not None or reasons, "null Feature needs a reason")
    if reasons: value = None
    if value is not None:
        require(type(value) in (int, float) and math.isfinite(value), "invalid canonical number")
    return FeatureValue(value, reasons, dict(audit or {}), tuple(windows), tuple(sorted(set(refs))), numerator, denominator)


@dataclass(frozen=True)
class FeatureOutput:
    feature_rows: list[dict]
    quality_rows: list[dict]
    reproducibility: list[dict]

    def learning_view(self, feature_ids: list[str]) -> dict:
        require(type(feature_ids) is list and len(set(feature_ids)) == len(feature_ids), "duplicate/invalid allowlist")
        require(all(type(fid) is str and fid in CORE_IDS for fid in feature_ids),
                "forbidden, metadata or deferred Feature in X allowlist")
        return dict(keys=[{name: row[name] for name in ("entity_namespace", "source", "customer_id", "index_date")}
                          for row in self.feature_rows],
                    X=[{fid: row[fid] for fid in feature_ids} for row in self.feature_rows])

    def typed_core_rows(self) -> list[dict]:
        """Partial compatibility with existing typed hash primitives, not a loader bundle."""
        result = []
        for row in self.feature_rows:
            projected = {name: row[name] for name in ("entity_namespace", "source", "customer_id", "index_date",
                                                       "feature_version", "feature_cutoff_time")}
            projected.update({fid: typed(row[fid], dict(dtype=dtype(fid), nullable=True,
                                                       dimension=0, categories=[])) for fid in CORE_IDS})
            result.append(projected)
        return sorted(result, key=tlv)


class _Customer:
    def __init__(self, batch, entity, index_date, policy, claims):
        self.batch, self.entity, self.index_date, self.policy, self.claims = batch, entity, index_date, policy, claims
        self.events = [row for row in batch.events if row["customer_id"] == entity.customer_id]

    def data(self, types, days=None, offset=0, unique=None):
        window = self.policy.window(self.index_date, days, offset)
        rows = [row for row in self.events if row["event_type"] in types and window.contains(row["timestamp"])]
        raw_count = len(rows)
        if unique is not None:
            rows = list({row[unique]: row for row in rows}.values())
        rows.sort(key=lambda row: (row["timestamp"], row["event_id"]))
        reasons = observation_reasons(self.batch, self.entity, types, window, self.claims)
        refs = tuple(claim.evidence_ref for claim in self.claims if claim.entity == self.entity and claim.event_types & types)
        return rows, reasons, dict(audit={"observed_events": raw_count, "observed_units": len(rows)},
                                  windows=({**window.record(),"event_types":sorted(types)},), refs=refs)

    def count(self, types, days, offset=0, unique=None):
        rows, reasons, meta = self.data(types, days, offset, unique)
        return outcome(len(rows), reasons=reasons, **meta)

    def recency(self, types, days=None):
        rows, reasons, meta = self.data(types, days)
        if not rows and not reasons: reasons = ("NO_SOURCE_EVENT",)
        return outcome((t0(self.index_date)-rows[-1]["timestamp"]).total_seconds()/86400 if rows else None,
                       reasons=reasons, **meta)

    def intervals(self, days=None, offset=0, *, cv=False):
        rows, reasons, meta = self.data(PURCHASE, days, offset, "order_id")
        gaps = [(b["timestamp"]-a["timestamp"]).total_seconds()/86400 for a,b in zip(rows, rows[1:])]
        meta["audit"].update(observed_intervals=len(gaps))
        mean = math.fsum(gaps)/len(gaps) if gaps else None
        if not reasons:
            reasons = tuple((["INSUFFICIENT_PURCHASE_INTERVALS"] if len(gaps) < (2 if cv else 1) else []) +
                            (["ZERO_DENOMINATOR"] if cv and mean == 0 else []))
        value = statistics.pstdev(gaps)/mean if cv and mean and len(gaps) >= 2 else mean if not cv else None
        numerator = (statistics.pstdev(gaps) if cv else math.fsum(gaps)) if gaps and not reasons else None
        denominator = (mean if cv else len(gaps)) if not reasons else None
        return outcome(value,reasons=reasons,numerator=numerator,denominator=denominator,**meta)


def combine(first: FeatureValue, second: FeatureValue, operation: str) -> FeatureValue:
    reasons = set(first.reasons) | set(second.reasons)
    denominator = None if second.value is None else second.value
    if operation == "ratio" and denominator == 0:
        reasons.add("ZERO_DENOMINATOR")
    value = None
    if not reasons:
        value = first.value/second.value if operation == "ratio" else first.value-second.value
    audit = {"recent_"+key: value for key,value in first.audit_counts.items()}
    audit.update({"previous_"+key: value for key,value in second.audit_counts.items()})
    return outcome(value, reasons=reasons, audit=audit, windows=first.windows+second.windows,
                   refs=first.evidence_refs+second.evidence_refs,
                   numerator=first.value, denominator=denominator if operation == "ratio" else None)


def _calculate(customer: _Customer) -> dict[str, FeatureValue]:
    c = customer
    result = {"F01": c.recency(PURCHASE), "F02": c.count(PURCHASE,90,unique="order_id"),
              "F05": c.intervals(), "F06": c.intervals(90,cv=True),
              "F08": c.count(VISITS,60,unique="session_id"), "F09": c.recency(VISITS)}
    rows,reasons,meta = c.data(PURCHASE,90,unique="order_id")
    result["F03"] = outcome(sum(row["order_amount"] for row in rows), reasons=reasons, **meta)
    result["F04"] = combine(result["F03"],result["F02"],"ratio")
    result["F07"] = combine(result["F01"],result["F05"],"ratio")
    rows,reasons,meta = c.data(ACTIVITY,30)
    result["F10"] = outcome(len({row["timestamp"].astimezone(KST).date() for row in rows}),reasons=reasons,**meta)
    counts = [("F11","page_view",60,None),("F12","product_view",60,None),
              ("F13","product_view",180,"product_id"),("F14","search",60,None),
              ("F15","add_to_cart",60,None),("F16","remove_from_cart",60,None),
              ("F17","checkout_start",60,"order_id"),("F18","cs_contact",60,None),
              ("F19","review",180,None),("F20","coupon_exposed",180,None),
              ("F21","coupon_use",180,"order_id")]
    for fid,event_type,days,unique in counts:
        result[fid] = c.count(frozenset({event_type}),days,unique=unique)
    result["F22"] = c.recency(frozenset({"campaign_exposed"}),180)
    rows,reasons,meta = c.data(frozenset({"product_view"}),180)
    categories = Counter(row["category"] for row in rows)
    if not rows and not reasons: reasons = ("ZERO_DENOMINATOR",)
    denominator = len(rows) if not reasons else None
    result["F23"] = outcome(-math.fsum((n/len(rows))*math.log(n/len(rows)) for n in categories.values())
                            if rows else None, reasons=reasons, denominator=denominator, **meta)
    result["F24"] = outcome(max(categories.values())/len(rows) if rows else None, reasons=reasons,
                            numerator=max(categories.values()) if categories and not reasons else None,
                            denominator=denominator, **meta)
    result["F25"] = combine(c.count(VISITS,14,unique="session_id"),c.count(VISITS,14,14,unique="session_id"),"ratio")
    result["F26"] = combine(c.count(PURCHASE,30,unique="order_id"),c.count(PURCHASE,30,30,unique="order_id"),"difference")
    value = result["F26"]
    result["F26"] = outcome(value.value/30 if value.value is not None else None, reasons=value.reasons,
                            audit=value.audit_counts, windows=value.windows, refs=value.evidence_refs,denominator=30)
    result["F27"] = combine(c.intervals(45),c.intervals(45,45),"difference")
    for fid,types,predicate in [
        ("F28",PURCHASE,lambda at: at.weekday()<5),("F42",PURCHASE,lambda at: at.weekday()>=5),
        ("F29",ACTIVITY,lambda at: 6<=at.hour<12),("F30",ACTIVITY,lambda at: 18<=at.hour<24)]:
        rows,reasons,meta = c.data(types,90,unique="order_id" if types==PURCHASE else None)
        numerator = sum(predicate(row["timestamp"].astimezone(KST)) for row in rows)
        if not rows and not reasons: reasons = ("ZERO_DENOMINATOR",)
        result[fid] = outcome(numerator/len(rows) if rows else None, reasons=reasons,
                              numerator=numerator if not reasons else None,denominator=len(rows) if not reasons else None,**meta)
    return result


def calculate_features(batches: list[EventBatch], *, index_date: date, policy: TimePolicy | None = None,
                       observation_claims: tuple[ObservationClaim, ...] = (), generated_at: datetime | None = None) -> FeatureOutput:
    require(type(policy) is TimePolicy, "explicit time policy required; #126 unresolved")
    require(type(batches) is list and all(type(batch) is EventBatch for batch in batches), "explicit source batches required")
    require(all(type(claim) is ObservationClaim for claim in observation_claims), "invalid observation claim type")
    namespaces = [(batch.source,batch.entity_namespace) for batch in batches]
    require(len(set(namespaces))==len(namespaces), "duplicate source/namespace snapshot in transaction")
    all_entities = {entity for batch in batches for entity in batch.entities}
    require(all(claim.entity in all_entities for claim in observation_claims), "observation source/customer outside transaction")
    checked = []
    for batch in batches:
        batch.guard(policy,index_date)
        relevant = tuple(claim for claim in observation_claims if
                         (claim.entity.source,claim.entity.entity_namespace)==(batch.source,batch.entity_namespace))
        checked.append(check_claims(batch,relevant))
    generated_at = timestamp(datetime.now(timezone.utc) if generated_at is None else generated_at)
    feature_rows,quality_rows,reproducibility = [],[],[]
    for batch,claims in zip(batches,checked):
        reproducibility.append(dict(source=batch.source,entity_namespace=batch.entity_namespace,
            feature_version=FEATURE_VERSION,event_contract_version=SCHEMA_VERSION,input_value_sha256=batch.input_value_sha256,
            policy=policy.record(),policy_value_sha256=semantic_hash("d1-calculation-policy",policy.record()),
            evidence_value_sha256=semantic_hash("d1-calculation-evidence",[claim.record() for claim in claims]),
            population_scope=batch.population_scope,implementation="d1_calculate/1-proposed"))
        for entity in batch.entities:
            calculated = _calculate(_Customer(batch,entity,index_date,policy,claims))
            key = dict(**entity.record(),index_date=index_date)
            row = dict(**key,feature_version=FEATURE_VERSION,feature_cutoff_time=policy.boundary,generated_at=generated_at)
            for fid,_,_,_,_,_ in DEFINITIONS:
                if fid not in calculated:
                    reason = ("TRANSFORM_NOT_FITTED" if fid in ("F36","F37") else
                              "NO_LIFETIME_COVERAGE" if fid=="F41" else "CONTRACT_UNRESOLVED")
                    calculated[fid] = outcome(None,reasons=(reason,))
                value = calculated[fid]
                canonical = value.value
                if canonical is not None:
                    require(dtype(fid)!="Int64" or type(canonical) is int,"integer canonical cannot be truncated")
                    canonical = int(canonical) if dtype(fid)=="Int64" else float(canonical)
                    if canonical==0:canonical=0 if dtype(fid)=="Int64" else 0.0
                    if dtype(fid)=="Int64": require(-(2**63)<=canonical<2**63,"canonical Int64 overflow")
                    if fid in ("F24","F28","F29","F30","F42"): require(0<=canonical<=1,"invalid ratio")
                row[fid] = canonical
                quality_rows.append(dict(**key,feature_id=fid,availability=value.availability,reasons=list(value.reasons),
                    audit_counts=value.audit_counts,required_windows=list(value.windows),evidence_refs=list(value.evidence_refs),
                    numerator=value.numerator,denominator=value.denominator,
                    support="event_kernel" if fid in CORE_IDS else "deferred_event_connection"))
            feature_rows.append(row)
    return FeatureOutput(feature_rows,quality_rows,reproducibility)
