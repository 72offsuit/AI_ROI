"""★ 반증 검사 — "결손을 0으로 채우기"가 스키마에서 실제로 거부되는지 확인한다.

주장하지 않고 실행해서 보인다. 아래 6가지 위반 시도가 전부 실패해야 이 계약이
USP-1 을 기계로 강제한다고 말할 수 있다.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
SCHEMAS = HERE.parent / "schemas"

try:
    from jsonschema import Draft202012Validator
    from referencing import Registry, Resource
except ImportError:
    print("BLOCKED — jsonschema 미설치. 통과로 적지 않는다.")
    raise SystemExit(2)

registry = Registry()
for path in sorted(SCHEMAS.glob("*.schema.json")):
    doc = json.loads(path.read_text(encoding="utf-8"))
    resource = Resource.from_contents(doc)
    registry = registry.with_resource(uri=path.name, resource=resource)
    registry = registry.with_resource(uri=doc["$id"], resource=resource)

METRIC_SCHEMA = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "$ref": "common.schema.json#/$defs/metric_value",
}
KPI_SPLIT_SCHEMA = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "$ref": "common.schema.json#/$defs/kpi_source_split",
}
PROVENANCE_SCHEMA = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "$ref": "common.schema.json#/$defs/provenance",
}
SAMPLE_SCHEMA = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "$ref": "rejection_report.schema.json#/properties/samples/items",
}
CHECK_SCHEMA = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "$ref": "data_quality_report.schema.json#/properties/checks/items",
}
LINK_SCHEMA = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "$ref": "ingestion_report.schema.json#/properties/sources/properties/commerce",
}
OK_BASIS = {"population": "orders", "denominator_definition": "분모 없음 (합계)",
            "window": {"direction": "retrospective", "days": 42}}

CASES = [
    ("계산 불가를 0으로 채운다", METRIC_SCHEMA, {
        "status": "unavailable", "value": 0, "unit": "krw",
        "reason_code": "NO_COST_BASIS", "reason_detail": "원가 근거 없음"}),
    ("★ 계산된 값에 기준(basis)이 없다", METRIC_SCHEMA, {
        "status": "ok", "value": 0, "unit": "krw"}),
    ("★ 계산 불가인데 기준(basis)을 붙인다", METRIC_SCHEMA, {
        "status": "unavailable", "value": None, "unit": "krw",
        "reason_code": "NO_COST_BASIS", "reason_detail": "원가 근거 없음",
        "basis": {"population": "orders", "denominator_definition": "분모 없음",
                  "window": {"direction": "none"}}}),
    ("계산 불가인데 사유를 안 적는다", METRIC_SCHEMA, {
        "status": "unavailable", "value": None, "unit": "krw"}),
    ("BLOCKED 인데 값을 채운다", METRIC_SCHEMA, {
        "status": "blocked", "value": 0.0, "unit": "ratio", "denominator": 0,
        "reason_code": "BLOCKED", "reason_detail": "pyarrow 없음"}),
    ("분모가 0인데 계산됨(ok)이라고 한다", METRIC_SCHEMA, {
        "status": "ok", "value": 0, "unit": "ratio",
        "basis": {"population": "P_buyer", "denominator_definition": "구매 이력 보유 고객 수",
                  "denominator": 0, "window": {"direction": "point_in_time"}}}),
    ("미확정 파라미터를 밝히지 않는다", METRIC_SCHEMA, {
        "status": "unconfirmed", "value": 0.18, "unit": "ratio",
        "basis": {"population": "P_buyer", "denominator_definition": "구매 이력 보유 고객 수",
                  "denominator": 100, "window": {"direction": "point_in_time"}},
        "reason_code": "PARAM_UNCONFIRMED", "reason_detail": "임계값 미확정"}),
    ("KPI 계층에서 두 출처를 합산해 기본 표시로 쓴다", KPI_SPLIT_SCHEMA, {
        "by_source": {
            "commerce": {"status": "ok", "value": 100, "unit": "krw", "basis": OK_BASIS},
            "simulator": {"status": "ok", "value": 200, "unit": "krw", "basis": OK_BASIS}},
        "combined": {"status": "ok", "value": 300, "unit": "krw", "basis": OK_BASIS}}),
    ("★ 거부 샘플에 스키마 밖 필드의 값을 담는다 (금지 필드 유출 경로)", SAMPLE_SCHEMA, {
        "reason_key": "FORBIDDEN_FIELD", "event_type": "purchase",
        "problems": ["측정 계층을 통과할 수 없는 필드: ['coupon_sensitivity']"],
        "offending_fields": ["coupon_sensitivity"],
        "offending_values": {"coupon_sensitivity": 0.85}}),
    ("★ 게시물이 생성 명령(generated_by)을 기록하지 않는다", PROVENANCE_SCHEMA, {
        "schema_version": "event-schema-v1.0-draft", "repo_commit": None,
        "data_version": None, "simulator_commit": None,
        "config_hashes": {}, "source_root": "data/raw"}),
    ("★ V-12 · 검사 대상 0행인데 pass 라고 한다 (공허한 통과)", CHECK_SCHEMA, {
        "id": "DQ-01", "spec_ref": "유일성", "title": "event_id 전역 유일",
        "status": "pass", "violations": 0, "examined_rows": 0,
        "scope": "저장된 events 전 구간."}),
    ("★ V-12 · vacuous 인데 위반 건수를 0으로 적는다", CHECK_SCHEMA, {
        "id": "DQ-01", "spec_ref": "유일성", "title": "event_id 전역 유일",
        "status": "vacuous", "violations": 0, "examined_rows": 0,
        "reason_code": "NOT_RUN", "reason_detail": "검사 대상이 0행이었다.",
        "scope": "저장된 events 전 구간."}),
    ("★ 미연결인데 수신 시각을 채운다", LINK_SCHEMA, {
        "link_state": "never_connected", "first_event_at": "2026-09-12T09:04:11.000+09:00",
        "last_event_at": None, "event_count": 0,
        "staleness": {"status": "not_run", "value": None, "unit": "text",
                      "reason_code": "PARAM_UNCONFIRMED", "reason_detail": "임계값 미확정"}}),
    ("★ 정지 판정을 값으로 단정한다 (임계값 없이)", LINK_SCHEMA, {
        "link_state": "stale", "first_event_at": None, "last_event_at": None,
        "event_count": 0,
        "staleness": {"status": "not_run", "value": None, "unit": "text",
                      "reason_code": "PARAM_UNCONFIRMED", "reason_detail": "임계값 미확정"}}),
    ("UTC 시각으로 게시한다", {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$ref": "common.schema.json#/$defs/kst_timestamp",
    }, "2026-09-11T00:00:00.000Z"),
]

fails = 0
for title, schema, instance in CASES:
    validator = Draft202012Validator(schema, registry=registry)
    errors = list(validator.iter_errors(instance))
    if errors:
        print(f"거부됨 ✅  {title}")
    else:
        print(f"통과함 ❌  {title}  ← 계약이 이 위반을 막지 못한다")
        fails += 1

print(f"\n위반 시도 {len(CASES)}건 중 거부 {len(CASES) - fails}건 · 통과 {fails}건")
sys.exit(1 if fails else 0)
