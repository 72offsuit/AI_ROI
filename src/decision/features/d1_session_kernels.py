"""Conditional F31-F35 kernels over explicit synthetic session facts.

This is not a session evidence producer or an event-to-session adapter. Such an
adapter remains blocked on the actual SD3 provider/ordering contract.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
import re

from src.measurement.schema import check_identifier
from .d1_feature_inputs import Entity, TimePolicy, timestamp
from .d1_calculate import FeatureValue, combine, outcome
from .d1_serialization import require


@dataclass(frozen=True)
class SessionFact:
    entity: Entity
    session_id: str
    started_at: str | datetime | None
    ended_at: str | datetime | None
    completion: str
    observation_complete: bool | None
    duration_seconds: int | None
    page_views: int | None
    search_present: bool | None
    search_converted: bool | None
    cart_present: bool | None
    cart_converted: bool | None
    input_value_sha256: str
    evidence_ref: str

    def __post_init__(self):
        require(type(self.entity) is Entity,"invalid session entity")
        require(type(self.session_id) is str and check_identifier("session_id",self.session_id) and
                self.session_id.startswith("S-"+self.entity.customer_id+"-"), "invalid session fact key")
        require(self.completion in ("complete","open","unknown"), "invalid session completion state")
        for field in ("observation_complete","search_present","search_converted","cart_present","cart_converted"):
            require(getattr(self,field) is None or type(getattr(self,field)) is bool,"session truth must be true/false/unknown")
        for field in ("started_at","ended_at"):
            if getattr(self,field) is not None: object.__setattr__(self,field,timestamp(getattr(self,field)))
        require(self.completion != "complete" or self.ended_at is not None, "completed session needs end proof")
        require(self.completion != "open" or self.ended_at is None, "open session cannot have end proof")
        if self.started_at is not None and self.ended_at is not None:
            require(self.started_at <= self.ended_at,"session end precedes start")
        for field in ("duration_seconds","page_views"):
            value = getattr(self,field)
            require(value is None or type(value) is int and 0<=value<2**63,"invalid session scalar")
        for present,converted in ((self.search_present,self.search_converted),(self.cart_present,self.cart_converted)):
            require(converted is not True or present is True,"conversion requires known antecedent")
            require(present is not False or self.observation_complete is True,"antecedent absence needs complete observation")
            require(not (present is True and converted is False) or self.observation_complete is True,
                    "conversion absence needs complete observation")
        require(type(self.input_value_sha256) is str and bool(re.fullmatch(r"[0-9a-f]{64}",self.input_value_sha256)),
                "session input identity required")
        require(type(self.evidence_ref) is str and bool(self.evidence_ref),"session evidence reference required")


def calculate_session_kernels(facts: list[SessionFact], *, entity: Entity, index_date: date,
                              policy: TimePolicy, population_complete: bool | None,
                              input_value_sha256: str) -> dict[str,FeatureValue]:
    require(type(policy) is TimePolicy,"explicit time policy required")
    policy.validate(index_date)
    require(type(facts) is list and all(type(fact) is SessionFact for fact in facts),"explicit session facts required")
    require(population_complete is None or type(population_complete) is bool,"session population completeness required")
    require(len({fact.session_id for fact in facts})==len(facts),"duplicate session fact")
    for fact in facts:
        require(type(fact) is SessionFact and fact.entity==entity,"session source/namespace/customer mismatch")
        require(fact.input_value_sha256==input_value_sha256,"session input identity mismatch")
        for at in (fact.started_at,fact.ended_at):
            if at is not None:
                policy.check_precision(at)
                require(policy.permits(at),"future session fact: reject kernel input")

    def members(days,offset=0):
        window = policy.window(index_date,days,offset)
        complete,unknown,open_excluded = [],0,0
        for fact in facts:
            if fact.started_at is not None and not window.contains(fact.started_at): continue
            if fact.completion=="open": open_excluded+=1;continue
            if fact.started_at is None or fact.completion=="unknown": unknown+=1;continue
            complete.append(fact)
        reasons = set()
        if population_complete is None: reasons.add("OBSERVATION_UNKNOWN")
        if population_complete is False or window.start<policy.history_start: reasons.add("INCOMPLETE_WINDOW")
        if unknown: reasons.add("SESSION_INCOMPLETE")
        audit = dict(completed_sessions=len(complete),n_unknown_membership=unknown,n_open_excluded=open_excluded)
        refs = [fact.evidence_ref for fact in facts]
        return complete,reasons,dict(audit=audit,windows=(window.record(),),refs=refs)

    def average(days,offset=0,field="duration_seconds"):
        selected,reasons,meta = members(days,offset)
        missing = sum(getattr(fact,field) is None or (field=="page_views" and fact.observation_complete is not True)
                      for fact in selected)
        meta["audit"]["missing_"+field] = missing
        if missing: reasons.add("MISSING_DURATION" if field=="duration_seconds" else "OBSERVATION_UNKNOWN")
        if not selected and not reasons: reasons.add("ZERO_DENOMINATOR")
        numerator = sum(getattr(fact,field) for fact in selected if getattr(fact,field) is not None)
        return outcome(numerator/len(selected) if selected else None,reasons=reasons,
                       numerator=numerator if not reasons else None,denominator=len(selected) if not reasons else None,**meta)

    def conversion(days,offset=0,antecedent="search"):
        selected,reasons,meta = members(days,offset)
        audit = meta["audit"]
        audit.update(n_true=0,n_false=0,n_unknown_outcome=0,n_no_antecedent=0)
        for fact in selected:
            present,converted = getattr(fact,antecedent+"_present"),getattr(fact,antecedent+"_converted")
            if present is None: audit["n_unknown_membership"]+=1
            elif present is False: audit["n_no_antecedent"]+=1
            elif converted is True: audit["n_true"]+=1
            elif converted is False: audit["n_false"]+=1
            else: audit["n_unknown_outcome"]+=1
        observed_denominator = audit["n_true"]+audit["n_false"]+audit["n_unknown_outcome"]
        audit["observed_denominator"] = observed_denominator
        if audit["n_unknown_membership"] or audit["n_unknown_outcome"]: reasons.add("SESSION_INCOMPLETE")
        if not observed_denominator and not reasons: reasons.add("ZERO_DENOMINATOR")
        return outcome(audit["n_true"]/observed_denominator if observed_denominator else None,
                       reasons=reasons,numerator=audit["n_true"] if not reasons else None,
                       denominator=observed_denominator if not reasons else None,**meta)

    return {"F31":average(60),"F32":average(60,field="page_views"),"F33":conversion(60),
            "F34":combine(average(14),average(14,14),"difference"),
            "F35":combine(conversion(30,antecedent="cart"),conversion(30,30,antecedent="cart"),"difference")}
