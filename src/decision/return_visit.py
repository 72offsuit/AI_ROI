"""#256 ③b: 입력의 출처·return_visit 정의를 계산값과 분리해 기록한다.

공유 이벤트 계약을 바꾸거나 행을 재작성하지 않는다. 커머스 정의는 생산 이력의
명시적 선언만 받으며 service_version·이벤트 시각·export 시각으로 추측하지 않는다.
"""
from __future__ import annotations

import copy

import pandas as pd

from src.measurement.schema import SCHEMA_VERSION
from src.measurement.sink import event_source

INPUT_METADATA = "return_visit_input"
DECLARATION = "commerce_return_visit_definition"
INPUT_VERSION = "return-visit-input/v1"
B_DEFINITION = "purchase_first_session"
LEGACY_DEFINITION = "every_repeat_session_with_session_start"
UNKNOWN_DEFINITION = "unknown"


def label_commerce_definition(events: pd.DataFrame, definition: str, *, evidence_ref: str) -> pd.DataFrame:
    """커머스 생산 이력의 선언을 사본에 붙인다. 참조는 자동 검증된 증명이 아니다."""
    if definition not in (B_DEFINITION, LEGACY_DEFINITION):
        raise ValueError("commerce return_visit definition must be explicit legacy or purchase_first_session")
    if not isinstance(evidence_ref, str) or not evidence_ref.strip():
        raise ValueError("commerce definition requires a non-empty producer evidence_ref")
    result = events.copy(deep=True)
    result.attrs = copy.deepcopy(events.attrs)
    result.attrs[DECLARATION] = {"definition": definition, "evidence_ref": evidence_ref}
    result.attrs[INPUT_METADATA] = input_metadata(result)
    return result


def input_metadata(events: pd.DataFrame) -> dict:
    """공개 출처 규칙을 재사용한다. B/legacy는 데이터 소유자의 선언이며 DQ 판정이 아니다."""
    declaration = events.attrs.get(DECLARATION)
    if declaration is not None and (
            not isinstance(declaration, dict)
            or declaration.get("definition") not in (B_DEFINITION, LEGACY_DEFINITION)
            or not isinstance(declaration.get("evidence_ref"), str)
            or not declaration["evidence_ref"].strip()):
        raise ValueError("invalid commerce return_visit definition declaration")
    columns = ("service_version", "customer_version", "simulator_version", "random_seed")
    groups = {}
    for values in events.reindex(columns=columns).itertuples(index=False, name=None):
        record = {key: None if pd.isna(value) else value for key, value in zip(columns, values)}
        source = event_source(record).value
        group = groups.setdefault(source, {"source": source, "event_rows": 0,
                                           "service_versions": set(), "customer_versions": set(),
                                           "simulator_versions": set()})
        group["event_rows"] += 1
        for field in ("service_version", "customer_version", "simulator_version"):
            if record[field] is not None:
                group[field.replace("_version", "_versions")].add(str(record[field]))
    records = []
    for source, group in sorted(groups.items()):
        for name in ("service_versions", "customer_versions", "simulator_versions"):
            group[name] = sorted(group[name])
        if source == "simulator":
            group.update(definition=B_DEFINITION, definition_basis="AI_ROI #256 public simulator contract",
                         evidence_ref="https://github.com/72offsuit/AI_ROI/issues/256#issuecomment-6706213916")
        else:
            group.update(definition=declaration["definition"] if declaration else UNKNOWN_DEFINITION,
                         definition_basis="producer declaration" if declaration else "producer definition unconfirmed",
                         evidence_ref=declaration["evidence_ref"] if declaration else None)
        records.append(group)
    return {"version": INPUT_VERSION, "event_schema_version": SCHEMA_VERSION,
            "groups": records, "experiment_source_allowed": bool(records) and all(g["source"] == "simulator" for g in records),
            "definition_verified": False,
            "notice": "선언·출처 구분이며 B안 준수·관측 완전성·모집단 적격성의 증명이 아니다"}


def check_input(events: pd.DataFrame, purpose: str) -> dict:
    """출처를 합산하지 않는다. 커머스 계산은 명시적인 관측·대조 호출에서만 허용한다."""
    if purpose not in ("experiment", "observation"):
        raise ValueError("purpose must be experiment or observation")
    metadata = input_metadata(events)
    if len(metadata["groups"]) > 1:
        raise ValueError("mixed event sources: separate simulator and commerce inputs before calculation")
    if purpose == "experiment" and not metadata["groups"]:
        raise ValueError("experiment input source is unconfirmed: no in-scope events")
    if purpose == "experiment" and not metadata["experiment_source_allowed"]:
        raise ValueError("commerce is observation-only; keep legacy/B/unknown inputs separate from experiment input")
    metadata["purpose"] = purpose
    return metadata
