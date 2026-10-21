"""Explicit, test-policy D1 inputs; no inference of observation completeness."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
import re
from typing import Iterable

from src.measurement.schema import EVENT_FIELDS, SCHEMA_VERSION, EventType, check_identifier, validate_event
from src.measurement.sink import EventSource, event_source
from src.measurement.timeparse import parse_datetime
from .d1_serialization import D1ContractError, normalize_timestamp, require, semantic_hash, tlv

KST = timezone(timedelta(hours=9))
EVENT_TYPES = frozenset(item.value for item in EventType)
ACTIVITY = EVENT_TYPES - {"campaign_exposed", "push_sent", "coupon_exposed"}
FIELDS = {item.name: item.dtype for item in EVENT_FIELDS}
INPUT_VERSION = "d1-calculation-input/1-proposed"


def timestamp(value: str | datetime) -> datetime:
    if isinstance(value, str):
        normalized = normalize_timestamp(value,
            syntax_message="timestamp: explicit offset and <=6 fractional digits required")
        try:
            value = parse_datetime(normalized)
        except ValueError as exc:
            raise D1ContractError("invalid event/policy timestamp") from exc
    require(type(value) is datetime and value.utcoffset() is not None, "timestamp must be offset-aware")
    try:
        return value.astimezone(timezone.utc)
    except (ValueError,OverflowError) as exc:
        raise D1ContractError("timestamp outside supported UTC range") from exc


def t0(index_date: date) -> datetime:
    require(type(index_date) is date, "index_date must be a calendar date")
    return datetime.combine(index_date, time(), KST).astimezone(timezone.utc)


@dataclass(frozen=True, order=True)
class Entity:
    entity_namespace: str
    source: str
    customer_id: str

    def __post_init__(self):
        require(all(type(value) is str and value for value in (
            self.entity_namespace, self.source, self.customer_id)), "invalid entity key")
        require(check_identifier("customer_id", self.customer_id), "invalid customer identifier")

    def record(self) -> dict:
        return dict(entity_namespace=self.entity_namespace, source=self.source, customer_id=self.customer_id)


@dataclass(frozen=True)
class Window:
    start: datetime
    end: datetime
    end_inclusive: bool

    def contains(self, at: datetime) -> bool:
        return self.start <= at and (at <= self.end if self.end_inclusive else at < self.end)

    def overlaps(self, start: datetime, end: datetime) -> bool:
        """Evidence/gaps are [start, end); only this request may include its end."""
        return end > self.start and (start <= self.end if self.end_inclusive else start < self.end)

    def record(self) -> dict:
        return dict(start=self.start, end=self.end, end_inclusive=self.end_inclusive)


@dataclass(frozen=True)
class TimePolicy:
    policy_id: str
    boundary: str | datetime
    operator: str
    precision: str
    history_start: str | datetime
    purpose: str

    def __post_init__(self):
        require(type(self.policy_id) is str and bool(self.policy_id), "time policy ID required")
        require(self.operator in ("lt", "le"), "explicit cutoff operator required")
        require(self.precision in ("ms", "us"), "explicit supported precision required")
        require(self.purpose == "synthetic", "operational cutoff unresolved: #126/SD1/SD2")
        object.__setattr__(self, "boundary", timestamp(self.boundary))
        object.__setattr__(self, "history_start", timestamp(self.history_start))
        require(self.history_start < self.boundary, "reversed/empty H")
        self.check_precision(self.boundary)
        self.check_precision(self.history_start)

    def check_precision(self, value: datetime):
        require(self.precision != "ms" or value.microsecond % 1000 == 0,
                "timestamp is not on declared millisecond grid")

    def validate(self, index_date: date):
        origin = t0(index_date)
        require((self.boundary == origin and self.operator == "lt") or
                self.boundary == origin - timedelta(seconds=1),
                "cutoff boundary/operator inconsistent with explicit P1/P2/P3 alternatives")

    def permits(self, value: datetime) -> bool:
        return value <= self.boundary if self.operator == "le" else value < self.boundary

    def window(self, index_date: date, days: int | None, offset: int = 0) -> Window:
        self.validate(index_date)
        origin = t0(index_date)
        start = self.history_start if days is None else origin - timedelta(days=days+offset)
        end = origin - timedelta(days=offset)
        if self.boundary < end:
            return Window(start, self.boundary, self.operator == "le")
        return Window(start, end, False)

    def record(self) -> dict:
        return dict(version="d1-calculation-policy/1-proposed", policy_id=self.policy_id,
                    boundary=self.boundary, operator=self.operator, precision=self.precision,
                    history_start=self.history_start, purpose=self.purpose)


@dataclass(frozen=True)
class ObservationClaim:
    entity: Entity
    event_types: frozenset[str]
    start: str | datetime
    end: str | datetime
    state: str
    gaps: tuple[tuple[str | datetime, str | datetime], ...]
    provider: str
    provider_role: str
    contract_version: str
    input_value_sha256: str
    evidence_ref: str

    def __post_init__(self):
        require(type(self.event_types) is frozenset and self.event_types <= EVENT_TYPES and bool(self.event_types),
                "observation event types required")
        object.__setattr__(self, "start", timestamp(self.start))
        object.__setattr__(self, "end", timestamp(self.end))
        object.__setattr__(self, "gaps", tuple((timestamp(a), timestamp(b)) for a, b in self.gaps))
        require(self.start < self.end, "invalid observation period")
        require(self.state in ("complete", "incomplete", "unknown", "unsupported"), "observation state")
        require(all(self.start <= a < b <= self.end for a, b in self.gaps), "invalid observation gap")
        require(not (self.state == "complete" and self.gaps), "complete claim conflicts with gaps")
        require(all(type(value) is str and value for value in (
            self.provider, self.provider_role, self.contract_version, self.evidence_ref)),
            "observation provider/contract/reference required")
        require(type(self.input_value_sha256) is str and bool(re.fullmatch(r"[0-9a-f]{64}", self.input_value_sha256)),
                "observation input identity required")

    def record(self) -> dict:
        return dict(entity=self.entity.record(), event_types=sorted(self.event_types), start=self.start,
                    end=self.end, state=self.state, gaps=[list(gap) for gap in self.gaps],
                    provider=self.provider, provider_role=self.provider_role, contract_version=self.contract_version,
                    input_value_sha256=self.input_value_sha256, evidence_ref=self.evidence_ref)


class EventBatch:
    """One explicitly separated source/namespace snapshot. Events have only the 22 public columns."""

    def __init__(self, *, source: str, entity_namespace: str, start: str | datetime,
                 records: Iterable[dict], roster: Iterable[str] | None):
        require(type(source) is str and source in {item.value for item in EventSource},
                "unsupported contract source: simulator/commerce required")
        require(type(entity_namespace) is str and bool(entity_namespace), "source and namespace required")
        self.source, self.entity_namespace, self.start = source, entity_namespace, timestamp(start)
        events, seen = [], set()
        for record in records:
            require(type(record) is dict, "event must be a public-contract object")
            require(set(record) <= set(FIELDS), "forbidden/non-22-column event field")
            normalized = {name: record.get(name) for name in FIELDS}
            for name, value in normalized.items():
                if value is None: continue
                if FIELDS[name] == "int":
                    require(type(value) is int and -(2**63) <= value < 2**63, f"invalid integer field: {name}")
                else:
                    require(type(value) is str, f"invalid string field: {name}")
            problems = validate_event(normalized)
            require(not problems, "public event contract: " + "; ".join(problems))
            require(event_source(normalized).value == source,
                    "event source mismatch: mixed or misdeclared source; reject entire D1 input")
            require(normalized["event_id"] not in seen, "duplicate event_id (including content conflict)")
            seen.add(normalized["event_id"])
            require(normalized["quantity"] is None or normalized["quantity"] >= 1, "quantity must be positive")
            normalized["timestamp"] = timestamp(normalized["timestamp"])
            require(normalized["session_id"] is None or normalized["session_id"].startswith(
                "S-"+normalized["customer_id"]+"-"), "session/customer identity mismatch")
            require(normalized["timestamp"] >= self.start, "event before declared snapshot start")
            tlv(normalized)
            events.append(normalized)
        # A stable content identity; physical input order is not event-order evidence.
        self._events = tuple(sorted(events, key=lambda row: row["event_id"]))
        customers = {row["customer_id"] for row in self.events}
        self.population_scope = "observed_only" if roster is None else "explicit_roster"
        if roster is not None:
            members = list(roster)
            require(all(type(member) is str for member in members),"roster contains non-customer metadata")
            require(len(set(members)) == len(members), "duplicate roster customer")
            require(customers <= set(members), "event customer absent from roster")
            customers = set(members)
        self.entities = tuple(sorted(Entity(entity_namespace, source, customer) for customer in customers))
        self.input_value_sha256 = semantic_hash("d1-calculation-input", dict(
            version=INPUT_VERSION, event_contract_version=SCHEMA_VERSION,
            source=source, entity_namespace=entity_namespace, start=self.start,
            events=list(self.events), population_scope=self.population_scope,
            customers=[entity.customer_id for entity in self.entities]))
        # Same order may legitimately have several records, but conflicting purchases cannot be collapsed.
        orders = {}
        self.repeated_purchase_records = 0
        for event in self.events:
            if event["event_type"] != "purchase": continue
            identity = event["order_id"]
            facts = (event["customer_id"], event["timestamp"], event["order_amount"])
            require(identity not in orders or orders[identity] == facts, "conflicting purchase order facts")
            self.repeated_purchase_records += int(identity in orders)
            orders[identity] = facts

    @property
    def events(self):
        return tuple(dict(row) for row in self._events)

    def guard(self, policy: TimePolicy, index_date: date):
        require(type(policy) is TimePolicy, "explicit time policy required")
        policy.validate(index_date)
        require(self.start <= policy.history_start, "H starts before extracted input")
        for event in self.events:
            policy.check_precision(event["timestamp"])
            require(policy.permits(event["timestamp"]), "forbidden-time event: reject entire D1 input")


def check_claims(batch: EventBatch, claims: tuple[ObservationClaim, ...]) -> tuple[ObservationClaim, ...]:
    for claim in claims:
        require(type(claim) is ObservationClaim and claim.entity in batch.entities,
                "observation source/namespace/customer mismatch")
        require(claim.input_value_sha256 == batch.input_value_sha256, "observation input identity mismatch")
    encoded = [tlv(claim.record()) for claim in claims]
    require(len(set(encoded)) == len(encoded), "duplicate observation claim")
    return tuple(claim for _, claim in sorted(zip(encoded, claims), key=lambda pair: pair[0]))


def observation_reasons(batch: EventBatch, entity: Entity, types: frozenset[str], window: Window,
                        claims: tuple[ObservationClaim, ...]) -> tuple[str, ...]:
    reasons = set()
    if window.start < batch.start:
        reasons.add("INCOMPLETE_WINDOW")
    for event_type in types:
        overlapping = [claim for claim in claims if claim.entity == entity and event_type in claim.event_types
                       and window.overlaps(claim.start, claim.end)]
        covering = [claim for claim in overlapping if claim.start <= window.start and
                    (claim.end > window.end if window.end_inclusive else claim.end >= window.end)]
        states = {claim.state for claim in overlapping}
        # No union of partial complete claims; inspect negative evidence even with full coverage.
        if not covering or "unknown" in states:
            reasons.add("OBSERVATION_UNKNOWN")
        if not covering and overlapping:
            reasons.add("INCOMPLETE_WINDOW")
        if "unsupported" in states:
            reasons.add("UNSUPPORTED_EVENT_KIND")
        for claim in overlapping:
            if claim.state == "incomplete" or any(window.overlaps(start, end) for start, end in claim.gaps):
                reasons.add("INCOMPLETE_WINDOW")
        # Different assertions about the same requested scope are not silently reconciled.
        if len(states) > 1:
            reasons.add("OBSERVATION_UNKNOWN")
    return tuple(sorted(reasons))
