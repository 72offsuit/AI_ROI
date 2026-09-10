"""게시 계약 v1 의 예시 산출물을 만든다 (설계 도구 — 제품 코드가 아니다).

빈 Sink 상태, 즉 **2026-09-11 현재의 실제 상태**를 예시로 만든다.
커머스는 이벤트를 한 건도 기록하지 않고(Ecommerce #28 미착수) 시뮬레이터도 없다.
대시보드가 처음 켜졌을 때 화면이 계산 불가로 가득한 것은 버그가 아니라 정상 동작이며,
이 예시가 그 정상 동작의 정의다.

실행:
    python3 .agent-team/04-architecture/tools/make_examples.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO))

from src.measurement import schema as sc  # noqa: E402

OUT = REPO / ".agent-team/04-architecture/examples/empty-sink"
RUN_ID = "MR-20260911-090000-0a1b2c3d"
NOW = "2026-09-11T09:00:00.000+09:00"

PROVENANCE = {
    "schema_version": sc.SCHEMA_VERSION,
    "repo_commit": "1140912aa0000000000000000000000000000000",
    "data_version": None,
    "simulator_commit": None,
    "null_reason": {
        "data_version": "PRECONDITION_MISSING",
        "simulator_commit": "PRECONDITION_MISSING",
    },
    "config_hashes": {},
    "source_root": "data/raw",
    "sink_manifest_sha256": None,
    "generated_by": "(예시 파일 — 실제 게시에서는 생성기가 자기 실행 명령을 런타임에 기록한다)",
}

NOTICE_EMPTY = {
    "code": "SINK_EMPTY",
    "level": "limitation",
    "message": "Event Sink 에 이벤트가 한 건도 없다. 커머스는 이벤트 기록이 미구현이고(Ecommerce #28) 시뮬레이터는 C1 범위 밖이다.",
    "reference": "charter §5 · Ecommerce_Service #28",
}
NOTICE_REFUND = {
    "code": "REFUND_NOT_ADJUSTED",
    "level": "assumption",
    "message": "revenue 는 총매출이며 환불·취소를 차감하지 않는다. 환불이 발생하는 환경에서는 contribution_profit 이 과대평가된다.",
    "reference": "economic-rule-v1.md §6 가정 A-REFUND",
}
NOTICE_GAP = {
    "code": "INGESTION_GAP_UNDECIDABLE",
    "level": "limitation",
    "message": "이벤트 0건인 날짜에 대해 '수집 중단'과 '활동 없음'을 현재 데이터로 구분할 수 없다. 두 경우가 같은 흔적을 남기고, 구분하려면 수집 시도를 남기는 heartbeat 레코드가 필요한데 Event Sink 에 없다.",
    "reference": "kpi-definition-v1.md §3 ingestion_days_gap · api-contracts.md §10 X-5",
}
NOTICE_PARAM = {
    "code": "CHURN_THRESHOLD_UNCONFIRMED",
    "level": "assumption",
    "message": "이탈 임계값 28/42/60 일은 가설값이며 GATE 1 에서 Lock 하지 않았다. 확정 절차(data_spec §5.1)는 시뮬레이터를 요구한다.",
    "reference": "kpi-definition-v1.md §1.1",
}


def envelope(artifact: str, notices: list[dict]) -> dict:
    return {
        "contract_version": "measurement-publish/v1",
        "artifact": artifact,
        "run_id": RUN_ID,
        "generated_at": NOW,
        "timezone": "Asia/Seoul",
        "provenance": PROVENANCE,
        "notices": notices,
    }


def basis(population: str, denom_def: str, *, denominator=None,
          observed=0, direction: str = "none", days=None, **extra) -> dict:
    """기준. ★ 계산된 값에만 붙는다 — 기준의 유무가 '측정된 0'과 '값 없음'을 가른다."""
    out = {
        "population": population,
        "denominator_definition": denom_def,
        "denominator": denominator,
        "observed_count": observed,
        "window": {"direction": direction, "days": days},
    }
    out.update(extra)
    return out


def zero(unit: str = "count", *, population: str = "저장된 전 이벤트",
         denom_def: str = "분모 없음 (합계·건수)", **kw) -> dict:
    """관측 결과로서의 0 — '세어 봤고 0이었다'는 사실이다. 기준이 붙는다."""
    return {"status": "ok", "value": 0, "unit": unit,
            "basis": basis(population, denom_def, **kw)}


def unavailable(code: str, detail: str, unit: str = "count", **extra) -> dict:
    """계산 불가 — value 는 null 이고 basis 를 가질 수 없다."""
    out = {"status": "unavailable", "value": None, "unit": unit,
           "reason_code": code, "reason_detail": detail}
    out.update(extra)
    return out


NO_EVENT = "근거 이벤트가 한 건도 없다. 저장된 이벤트 0건."


def split_zero(unit: str = "count", combined: bool = True, **kw) -> dict:
    out = {"by_source": {"commerce": zero(unit, **kw), "simulator": zero(unit, **kw)}}
    if combined:
        out["combined"] = zero(unit, **kw)
    return out


def split_unavailable(code: str, detail: str, unit: str, **extra) -> dict:
    return {"by_source": {
        "commerce": unavailable(code, detail, unit, **extra),
        "simulator": unavailable(code, detail, unit, **extra),
    }}


GAP_ATTRIBUTION = {
    "status": "not_run", "value": None, "unit": "text",
    "reason_code": "PRECONDITION_MISSING",
    "reason_detail": "heartbeat 레코드가 없어 이벤트 0건인 날짜가 수집 중단인지 활동 없음인지 구분할 수 없다.",
}
STALENESS_UNDECIDABLE = {
    "status": "not_run", "value": None, "unit": "text",
    "reason_code": "PARAM_UNCONFIRMED",
    "reason_detail": "정지 판정 임계값이 확정되지 않았고 C1 에서 그 상태에 도달할 수 없어 검증도 불가능하다.",
}


def never_connected() -> dict:
    return {"link_state": "never_connected", "first_event_at": None,
            "last_event_at": None, "event_count": 0,
            "staleness": STALENESS_UNDECIDABLE}


def build_ingestion() -> dict:
    doc = envelope("ingestion_report", [NOTICE_EMPTY, NOTICE_GAP])
    doc["totals"] = {
        "events_ingested": split_zero(),
        "events_rejected": zero(population="수집 시도된 전 이벤트"),
        "rejection_rate": unavailable(
            "NO_SOURCE_EVENT", "수집 시도가 0건이라 거부율의 분모가 없다.", "ratio"),
        "event_type_coverage": {
            "status": "ok", "value": 0.0, "unit": "ratio",
            "basis": basis("EventType 16종", "고정 분모 16 (event_type 전체 종수)",
                           denominator=16, observed=0)},
        "partition_day_count": zero(population="파티션 디렉터리"),
        "ingestion_days_gap": unavailable(
            "NO_SOURCE_EVENT",
            "파티션이 하나도 없어 관측 구간 자체가 정의되지 않는다. "
            "구간이 생겨도 '수집 중단'과 '활동 없음'은 현재 데이터로 구분할 수 없다.", "count"),
        "unavailable_metric_count": {
            "status": "ok", "value": 16, "unit": "count",
            "basis": basis("Observable 지표 16종", "고정 분모 16", denominator=16, observed=16)},
        "ingestion_gap_attribution": GAP_ATTRIBUTION,
    }
    doc["sources"] = {
        "commerce": never_connected(),
        "simulator": never_connected(),
    }
    doc["by_event_type"] = {e.value: split_zero(population=f"{e.value} 이벤트")
                            for e in sc.EventType}
    doc["partitions"] = []
    return doc


def build_rejection() -> dict:
    doc = envelope("rejection_report", [NOTICE_EMPTY])
    doc["totals"] = {
        "events_rejected": zero(population="수집 시도된 전 이벤트"),
        "rejection_rate": unavailable(
            "NO_SOURCE_EVENT", "수집 시도가 0건이라 거부율의 분모가 없다.", "ratio"),
        "distinct_reasons": zero(population="거부 사유 종류"),
    }
    doc["by_reason"] = []
    doc["samples"] = []
    return doc


FIELD_IMPACT: dict[str, list[str]] = {
    "event_id": ["events_ingested"],
    "customer_id": ["churn_rate", "retention_rate", "repurchase_rate", "winback_rate",
                    "purchase_frequency", "purchase_interval", "cohort_retention_rate"],
    "timestamp": ["churn_rate", "purchase_interval", "cohort_retention_rate",
                  "ingestion_days_gap", "partition_day_count"],
    "event_type": ["events_ingested", "event_type_coverage"],
    "session_id": ["session_duration", "page_views"],
    "session_duration": ["session_duration"],
    "page_type": ["page_views"],
    "product_id": ["cart_abandonment_count"],
    "category": [],
    "quantity": ["cogs"],
    "unit_price": ["cogs"],
    "order_id": ["average_order_value", "revenue"],
    "order_amount": ["revenue", "average_order_value", "cumulative_revenue",
                     "contribution_profit", "shipping_subsidy"],
    "coupon_id": ["coupon_usage_count", "coupon_exposure_count", "coupon_cost"],
    "campaign_id": ["campaign_response_count", "message_cost", "campaign_fixed_cost"],
    "treatment_id": ["shipping_subsidy", "marketing_cost"],
    "treatment_group": [],
    "experiment_id": [],
    "service_version": [],
    "customer_version": [],
    "simulator_version": ["events_ingested"],
    "random_seed": ["events_ingested"],
}

SCHEMA_GAPS = [
    {
        "ref": "unit_cost",
        "required_by_formula": "cogs = sum(unit_cost * quantity)",
        "where_it_should_live": "products 테이블 (data_spec §7.1 · 미구현). 커머스에도 없다 (Ecommerce #24)",
        "blocks_metrics": ["cogs", "contribution_profit", "incremental_contribution_profit", "ai_roi"],
        "blocks_checks": [],
        "reason_code": "NO_COST_BASIS",
        "reason_detail": "원가를 담을 테이블이 구현되지 않았고 커머스 스키마에도 unit_cost 컬럼이 없다. 원가율을 곱해 추정하지 않는다.",
        "decision_ref": "EC-1 · EC-2 · Ecommerce #24",
    },
    {
        "ref": "discount",
        "required_by_formula": "order_amount = sum(unit_price * quantity) - discount · coupon_cost = sum(discount)",
        "where_it_should_live": "events 22컬럼 (DATA-003) — 없다",
        "blocks_metrics": ["coupon_cost", "marketing_cost", "contribution_profit"],
        "blocks_checks": ["DQ-09"],
        "reason_code": "MISSING_FIELD",
        "reason_detail": "order_amount 의 정의식이 빼는 항목인데 22컬럼에 discount 가 없다. purchase 는 주문 단위 1행이라 품목 합계도 재구성할 수 없어 금액 정합성 검사가 원리적으로 불가하다.",
        "decision_ref": "D-16 · G-16",
    },
    {
        "ref": "shipping_fee",
        "required_by_formula": "contribution_profit = ... - shipping_subsidy",
        "where_it_should_live": "events 22컬럼 (DATA-003) — 없다",
        "blocks_metrics": ["shipping_subsidy", "contribution_profit"],
        "blocks_checks": [],
        "reason_code": "MISSING_FIELD",
        "reason_detail": "배송비·배송보조 필드가 없다. 시뮬레이터 생성분은 treatment_id=T1 과 order_amount 로 규칙 유도가 가능하나 저장된 사실이 아니다. 커머스는 배송비를 저장하지 않는다.",
        "decision_ref": "D-3",
    },
    {
        "ref": "refund",
        "required_by_formula": "revenue = 순매출 (환불 차감 후)",
        "where_it_should_live": "event_type 16종 — 환불·취소 이벤트가 없다",
        "blocks_metrics": ["revenue", "contribution_profit", "incremental_contribution_profit"],
        "blocks_checks": [],
        "reason_code": "MISSING_FIELD",
        "reason_detail": "환불/취소 이벤트가 없어 총매출을 순매출로 간주한다(가정 A-REFUND). 환불이 발생하는 환경에서는 기여이익이 과대평가된다.",
        "decision_ref": "D-2",
    },
]


def build_field_coverage() -> dict:
    doc = envelope("field_coverage_report", [NOTICE_EMPTY])
    fields = {}
    for spec in sc.EVENT_FIELDS:
        applicable = sorted(
            e.value for e in sc.EventType
            if sc.requirement(e, spec.name) is not sc.Requirement.NOT_APPLICABLE
        )
        fields[spec.name] = {
            "group": spec.group.value,
            "fill_rate": split_unavailable(
                "NO_SOURCE_EVENT",
                "이 필드가 적용되는 이벤트가 한 건도 없어 충족률의 분모가 0이다.",
                "ratio"),
            "applicable_event_types": applicable,
            "blocks_metrics": FIELD_IMPACT.get(spec.name, []),
        }
    doc["fields"] = fields
    doc["missing_fields"] = []
    doc["schema_gaps"] = SCHEMA_GAPS
    return doc


def build_kpi() -> dict:
    doc = envelope("kpi_report", [NOTICE_EMPTY, NOTICE_PARAM, NOTICE_REFUND])
    doc["index_date"] = None
    doc["definition_version"] = "kpi-definition-v1 (미Lock · 확정안)"

    def blocker(kind, ref, code):
        return {"kind": kind, "ref": ref, "reason_code": code}

    NO_EV = [blocker("event_type", "purchase", "NO_SOURCE_EVENT")]

    def m(name, layer, role, population, direction, days, denom, formula, ref, value,
          src=None, blocks=None):
        item = {
            "name": name, "layer": layer, "role": role, "population": population,
            "window": {"direction": direction, "days": days},
            "denominator_definition": denom, "formula": formula,
            "definition_ref": ref, "value": value,
        }
        if src:
            item["source_events"] = src
        if blocks is not None:
            item["blocks"] = blocks
        return item

    def unav(code, detail, unit, blocked_by=None, **extra):
        out = unavailable(code, detail, unit, **extra)
        if blocked_by:
            out["blocked_by"] = blocked_by
        return out

    def split_unav(code, detail, unit, blocked_by=None, **extra):
        return {"by_source": {
            "commerce": unav(code, detail, unit, blocked_by, **extra),
            "simulator": unav(code, detail, unit, blocked_by, **extra)}}

    metrics = [
        m("events_ingested", "collection_health", "none", "events", "none", None,
          "분모 없음 (합계)", "count(저장된 이벤트)", "kpi-definition-v1.md §3",
          split_zero(population="저장된 전 이벤트"), blocks=[]),
        m("field_fill_rate[order_amount]", "collection_health", "none", "events", "none", None,
          "order_amount 가 적용되는 이벤트 수 (NOT_APPLICABLE 제외)",
          "present(f) / applicable(f)", "kpi-definition-v1.md §3",
          split_unav("NO_SOURCE_EVENT", NO_EVENT, "ratio",
                     [blocker("event_type", "purchase", "NO_SOURCE_EVENT")]),
          blocks=["revenue", "average_order_value", "contribution_profit"]),
        m("churn_rate", "customer_kpi", "secondary", "P_buyer", "point_in_time", None,
          "구매 이력 보유 고객 수",
          "|{c : days_since_last_purchase(c,D) >= no_purchase_days}| / |P_buyer(D)|",
          "kpi-definition-v1.md §4",
          split_unav("NO_SOURCE_EVENT", NO_EVENT, "ratio", NO_EV),
          ["purchase"], blocks=["retention_rate", "winback_rate"]),
        m("average_order_value", "customer_kpi", "none", "P_buyer", "retrospective", 42,
          "주문 건수 (고객 수가 아니다)", "sum(order_amount) / count(purchase)",
          "kpi-definition-v1.md §4",
          split_unav("NO_SOURCE_EVENT", NO_EVENT, "krw", NO_EV),
          ["purchase"], blocks=[]),
        m("revenue", "business_kpi", "none", "orders", "retrospective", 42,
          "분모 없음 (합계)", "sum(order_amount)", "kpi-definition-v1.md §5.1",
          split_unav("NO_SOURCE_EVENT", NO_EVENT, "krw", NO_EV),
          ["purchase"], blocks=["contribution_profit", "incremental_revenue"]),
        m("cogs", "business_kpi", "none", "orders", "retrospective", 42,
          "분모 없음 (합계)", "sum(unit_cost * quantity)  단 has_cost_basis(order) 인 주문만",
          "economic-rule-v1.md EC-1 · EC-2",
          {"by_source": {
              "commerce": unav("NO_COST_BASIS",
                               "주문 품목에 unit_cost 값이 없다. 원가율을 곱해 추정하지 않는다.", "krw",
                               [blocker("schema_gap", "unit_cost", "NO_COST_BASIS")]),
              "simulator": unav("NO_SOURCE_EVENT", NO_EVENT, "krw", NO_EV)}},
          ["purchase"], blocks=["contribution_profit"]),
        m("contribution_profit", "business_kpi", "none", "orders", "retrospective", 42,
          "분모 없음 (합계)",
          "revenue - cogs - coupon_cost - shipping_subsidy - message_cost - campaign_fixed_cost/N_targeted",
          "economic-rule-v1.md §3.4",
          {"by_source": {
              "commerce": unav("NO_COST_BASIS",
                               "cogs 를 계산할 수 없어 기여이익이 성립하지 않는다.", "krw",
                               [blocker("metric", "cogs", "NO_COST_BASIS"),
                                blocker("schema_gap", "discount", "MISSING_FIELD"),
                                blocker("schema_gap", "shipping_fee", "MISSING_FIELD")]),
              "simulator": unav("NO_SOURCE_EVENT", NO_EVENT, "krw", NO_EV)}},
          blocks=["incremental_contribution_profit", "ai_net_incremental_value", "ai_roi"]),
        m("shipping_subsidy", "business_kpi", "none", "orders", "retrospective", 42,
          "분모 없음 (합계)", "T1 처치 주문 중 order_amount < 40,000 이면 3,000원",
          "kpi-definition-v1.md §5.4 (결정 D-3)",
          {"by_source": {
              "commerce": unav("MISSING_FIELD",
                               "배송비·배송보조 필드가 DATA-003 22컬럼에 없고 커머스는 배송비를 저장하지 않는다.",
                               "krw", [blocker("schema_gap", "shipping_fee", "MISSING_FIELD")]),
              "simulator": unav("NO_SOURCE_EVENT", NO_EVENT, "krw", NO_EV)}},
          blocks=["contribution_profit"]),
        m("coupon_cost", "business_kpi", "none", "orders", "retrospective", 42,
          "분모 없음 (합계)", "sum(discount) — 쿠폰이 실제 사용된 주문에만",
          "kpi-definition-v1.md §5.1 · api-contracts.md §8 (신규 발견 A-1)",
          {"by_source": {
              "commerce": unav("MISSING_FIELD",
                               "discount 필드가 DATA-003 22컬럼에 없다. 규칙 유도 여부는 미결정이다(D-16).",
                               "krw", [blocker("schema_gap", "discount", "MISSING_FIELD")]),
              "simulator": unav("NO_SOURCE_EVENT", NO_EVENT, "krw",
                                [blocker("event_type", "coupon_use", "NO_SOURCE_EVENT")])}},
          blocks=["marketing_cost", "contribution_profit"]),
        m("marketing_cost", "business_kpi", "guardrail", "orders", "retrospective", 42,
          "분모 없음 (합계)", "message_cost + coupon_cost + campaign_fixed_cost",
          "kpi-definition-v1.md §5.1",
          split_unav("NO_SOURCE_EVENT", NO_EVENT, "krw",
                     [blocker("metric", "coupon_cost", "MISSING_FIELD"),
                      blocker("event_type", "push_sent", "NO_SOURCE_EVENT"),
                      blocker("parameter", "C_rule", "PARAM_UNCONFIRMED")]),
          blocks=[]),
        m("incremental_contribution_profit", "experiment", "primary", "test_holdout",
          "prospective", 42, "고객 수 (1인당 값 병기)",
          "CP_strategy - CP_S1_rule", "kpi-definition-v1.md §7.1",
          unav("NEEDS_TWO_STRATEGIES",
               "비교할 두 전략이 없다. 전략 구현은 C1 범위 밖이다.", "krw",
               [blocker("metric", "contribution_profit", "NO_COST_BASIS"),
                blocker("strategy", "S1_rule_based", "NEEDS_TWO_STRATEGIES")]),
          blocks=["ai_net_incremental_value", "ai_roi"]),
        m("qini_coefficient", "experiment", "primary", "test_holdout", "prospective", 42,
          "Test 고객 수", "Qini curve 면적", "kpi-definition-v1.md §7.1",
          unav("NEEDS_MODEL_OUTPUT", "Uplift 모델 산출물이 없다. C1 범위 밖이다.", "ratio",
               [blocker("model_output", "uplift_scores", "NEEDS_MODEL_OUTPUT")]),
          blocks=["auuc"]),
        m("churn_test_auc", "experiment", "guardrail", "test_holdout", "prospective", 42,
          "Test 고객 수", "ROC AUC", "kpi-definition-v1.md §7.2",
          unav("NEEDS_MODEL_OUTPUT", "Churn 모델 산출물이 없다. C1 범위 밖이다.", "ratio",
               [blocker("model_output", "churn_predictions", "NEEDS_MODEL_OUTPUT")]),
          blocks=["incremental_contribution_profit"]),
    ]
    doc["metrics"] = metrics

    counts = {"ok": 0, "unconfirmed": 0, "unavailable": 0, "blocked": 0, "not_run": 0}
    by_layer: dict[str, dict[str, int]] = {}
    for item in metrics:
        value = item["value"]
        statuses = ([value["status"]] if "status" in value
                    else [v["status"] for v in value["by_source"].values()])
        worst = "ok" if all(s == "ok" for s in statuses) else next(
            s for s in statuses if s != "ok")
        counts[worst] += 1
        by_layer.setdefault(item["layer"], {}).setdefault(worst, 0)
        by_layer[item["layer"]][worst] += 1
    doc["summary"] = {"total": len(metrics), **counts, "by_layer": by_layer}
    return doc


def build_quality() -> dict:
    doc = envelope("data_quality_report", [NOTICE_EMPTY])
    doc["gate_result"] = "incomplete"
    doc["spec_coverage"] = {
        "spec_items": [
            {"spec_ref": "유일성", "covered_by": ["DQ-01", "DQ-02", "DQ-02b"], "worst_status": "not_run"},
            {"spec_ref": "참조 무결성", "covered_by": ["DQ-03"], "worst_status": "not_run"},
            {"spec_ref": "시간 정합성", "covered_by": ["DQ-04", "DQ-05", "DQ-06"], "worst_status": "not_run"},
            {"spec_ref": "퍼널 정합성", "covered_by": ["DQ-07", "DQ-08"], "worst_status": "vacuous"},
            {"spec_ref": "금액 정합성", "covered_by": ["DQ-09", "DQ-10"], "worst_status": "not_run"},
            {"spec_ref": "완전성", "covered_by": ["DQ-11", "DQ-12"], "worst_status": "not_run"},
            {"spec_ref": "생성 이탈률", "covered_by": ["DQ-13"], "worst_status": "not_run"},
            {"spec_ref": "실험 균형", "covered_by": ["DQ-14"], "worst_status": "not_run"},
            {"spec_ref": "처치 강도", "covered_by": ["DQ-15"], "worst_status": "not_run"},
            {"spec_ref": "4분면 분포", "covered_by": ["DQ-16"], "worst_status": "not_run"},
            {"spec_ref": "재현성", "covered_by": ["DQ-17"], "worst_status": "blocked"},
        ],
        "reported_checks": 18,
        "unmapped_spec_items": [],
    }
    doc["checks"] = [
        {"id": "DQ-01", "spec_ref": "유일성", "title": "event_id 전역 유일",
         "status": "vacuous", "violations": None, "examined_rows": 0,
         "reason_code": "NOT_RUN",
         "reason_detail": "검사는 실행했으나 검사 대상이 0행이었다. 위반이 없는 것이 아니라 검사할 것이 없었다.",
         "scope": "저장된 events 파티션 전 구간. 오늘은 0행이므로 위반이 없는 것이 아니라 검사 대상이 없다 — examined_rows 를 함께 읽어야 한다."},
        {"id": "DQ-02", "spec_ref": "유일성", "title": "order_id 유일",
         "status": "not_run", "violations": None,
         "reason_code": "PRECONDITION_MISSING",
         "reason_detail": "orders 테이블이 구현되지 않아 '전역 유일'의 검사 대상이 없다(sink.py 는 events 만 저장한다).",
         "scope": "C1 에서는 'order_id 당 purchase 이벤트가 정확히 1건'으로 범위를 좁혀야 검사할 수 있다. 그 좁힌 검사는 DQ-02b 다."},
        {"id": "DQ-02b", "spec_ref": "유일성(범위 축소)", "title": "order_id 당 purchase 이벤트 1건",
         "status": "vacuous", "violations": None, "examined_rows": 0,
         "reason_code": "NOT_RUN",
         "reason_detail": "검사는 실행했으나 검사 대상이 0행이었다. 위반이 없는 것이 아니라 검사할 것이 없었다.",
         "scope": "events 테이블에 한정한다. checkout_start·coupon_use 도 order_id 를 갖지만 중복이 정상이므로 purchase 만 센다."},
        {"id": "DQ-03", "spec_ref": "참조 무결성", "title": "고아 customer_id · product_id 0건",
         "status": "not_run", "violations": None,
         "reason_code": "PRECONDITION_MISSING",
         "reason_detail": "customers·products 테이블이 구현되지 않았다(data_spec §7.1 의 6개 테이블 미구현).",
         "scope": "C1 에서 실행 불가. 이 검사를 통과로 적지 않는다."},
        {"id": "DQ-04", "spec_ref": "시간 정합성", "title": "세션 내 이벤트 순서",
         "status": "vacuous", "violations": None, "examined_rows": 0,
         "reason_code": "NOT_RUN",
         "reason_detail": "검사는 실행했으나 검사 대상이 0행이었다. 위반이 없는 것이 아니라 검사할 것이 없었다.",
         "scope": "session_id 가 있는 이벤트만. session_id 가 NOT_APPLICABLE 인 push_sent 등은 대상이 아니다."},
        {"id": "DQ-05", "spec_ref": "시간 정합성", "title": "timestamp < signup_date 0건",
         "status": "not_run", "violations": None,
         "reason_code": "PRECONDITION_MISSING",
         "reason_detail": "signup_date 는 customers 테이블 컬럼이며 구현되지 않았다.",
         "scope": "C1 에서 실행 불가."},
        {"id": "DQ-06", "spec_ref": "시간 정합성", "title": "모든 시각이 KST 단일 타임존",
         "status": "not_run", "violations": None,
         "reason_code": "BLOCKED",
         "reason_detail": "타임존 정책이 아직 강제되지 않는다(이슈 #53 D1-3). 정책 확정 전에는 위반 판정 기준이 없다.",
         "scope": "#53 완료 후 실행한다."},
        {"id": "DQ-07", "spec_ref": "퍼널 정합성", "title": "purchase 는 선행 checkout_start 보유",
         "status": "vacuous", "violations": None, "examined_rows": 0,
         "reason_code": "NOT_RUN",
         "reason_detail": "검사는 실행했으나 검사 대상이 0행이었다. 위반이 없는 것이 아니라 검사할 것이 없었다.",
         "scope": "order_id 로 대응시킨다. 파티션 경계를 넘는 주문(자정 전후)을 놓치지 않도록 전 구간을 한 번에 본다."},
        {"id": "DQ-08", "spec_ref": "퍼널 정합성", "title": "coupon_use 는 선행 coupon_exposed 보유",
         "status": "vacuous", "violations": None, "examined_rows": 0,
         "reason_code": "NOT_RUN",
         "reason_detail": "검사는 실행했으나 검사 대상이 0행이었다. 위반이 없는 것이 아니라 검사할 것이 없었다.",
         "scope": "coupon_id 로 대응시킨다."},
        {"id": "DQ-09", "spec_ref": "금액 정합성", "title": "order_amount = sum(unit_price*quantity) - discount, 오차 0원",
         "status": "not_run", "violations": None,
         "reason_code": "PRECONDITION_MISSING",
         "reason_detail": "discount 필드가 DATA-003 22컬럼에 없고, purchase 이벤트는 주문 단위 1행이라 품목 합계를 재구성할 수 없다. order_items 테이블이 필요하다.",
         "scope": "C1 에서 원리적으로 실행 불가. api-contracts.md §8 신규 발견 A-1."},
        {"id": "DQ-10", "spec_ref": "금액 정합성", "title": "음수 금액 0건",
         "status": "vacuous", "violations": None, "examined_rows": 0,
         "reason_code": "NOT_RUN",
         "reason_detail": "검사는 실행했으나 검사 대상이 0행이었다. 위반이 없는 것이 아니라 검사할 것이 없었다.",
         "scope": "quantity·unit_price·order_amount·session_duration 4종. validate_event() 가 이미 수집 시점에 거부하므로 저장분에는 나타나지 않는 것이 정상이다."},
        {"id": "DQ-11", "spec_ref": "완전성", "title": "Key 결측 0%",
         "status": "vacuous", "violations": None, "examined_rows": 0,
         "reason_code": "NOT_RUN",
         "reason_detail": "검사는 실행했으나 검사 대상이 0행이었다. 위반이 없는 것이 아니라 검사할 것이 없었다.",
         "scope": "CORE 4종(event_id·customer_id·timestamp·event_type)."},
        {"id": "DQ-12", "spec_ref": "완전성", "title": "Feature 결측률 항목별 5% 미만",
         "status": "not_run", "violations": None,
         "reason_code": "PRECONDITION_MISSING",
         "reason_detail": "data/processed/features_t0 가 생성되지 않았다. Feature 생성은 decision 파트 소관이며 C1 범위 밖이다.",
         "scope": "C1 에서 실행 불가."},
        {"id": "DQ-13", "spec_ref": "생성 이탈률", "title": "Generated Churn Rate 15~25%",
         "status": "not_run", "violations": None, "threshold": "0.15 <= rate <= 0.25",
         "reason_code": "PRECONDITION_MISSING",
         "reason_detail": "시뮬레이터가 없다. C1 범위 밖이다(charter §5).",
         "scope": "범위 C 에서 실행한다."},
        {"id": "DQ-14", "spec_ref": "실험 균형", "title": "Balance Check |SMD| < 0.1",
         "status": "not_run", "violations": None,
         "reason_code": "PRECONDITION_MISSING",
         "reason_detail": "assignment 테이블과 시뮬레이터가 없다. 이슈 #48 이 이미 범위 C 로 이관했다.",
         "scope": "범위 C 에서 실행한다."},
        {"id": "DQ-15", "spec_ref": "처치 강도", "title": "ATE 3~6%p · 쿠폰 사용률 25~40% · Sleeping Dog 8~15%",
         "status": "not_run", "violations": None,
         "reason_code": "PRECONDITION_MISSING",
         "reason_detail": "시뮬레이터 산출물이 없다.",
         "scope": "범위 C 에서 실행한다."},
        {"id": "DQ-16", "spec_ref": "4분면 분포", "title": "Persuadables 20~30% 등",
         "status": "not_run", "violations": None,
         "reason_code": "PRECONDITION_MISSING",
         "reason_detail": "Ground-truth 는 diagnostics 전용이며 measurement 는 참조조차 할 수 없다.",
         "scope": "measurement 소관이 아니다. 범위 C·D 에서 diagnostics 가 검사한다."},
        {"id": "DQ-17", "spec_ref": "재현성", "title": "동일 seed 재실행 시 events.parquet SHA-256 일치",
         "status": "blocked", "violations": None,
         "reason_code": "BLOCKED",
         "reason_detail": "pyarrow 가 설치되지 않아 Parquet 경로가 한 번도 실행되지 않았다. 의존성 도입(dependency-plan.md) 후 해소된다.",
         "scope": "jsonl.gz 형식의 해시 재현성은 tests/test_sink.py 가 이미 검사한다. Parquet 형식만 미검증이다."},
    ]
    return doc


def build_freeze() -> dict:
    doc = envelope("freeze_status", [{
        "code": "GATE1_NOT_PASSED",
        "level": "limitation",
        "message": "C1 은 GATE 1 을 통과시키지 않는다. 부분 봉인만 하며 EXPERIMENT_ENVIRONMENT_v1 을 선언하지 않는다.",
        "reference": "gate1-lock-scope.md §1",
    }])
    doc["gate"] = "GATE_1"
    doc["overall"] = "not_started"
    doc["lock_record"] = None

    def item(name, status, owner, scope, code=None, detail=None, files=None):
        out = {"item": name, "status": status, "owner_part": owner, "scope_note": scope}
        if code:
            out["reason_code"] = code
            out["reason_detail"] = detail
        if files is not None:
            out["canonical_files"] = files
        return out

    doc["items"] = [
        item("SERVICE_v1", "PENDING", "commerce",
             "기준 환경(커머스)의 확정. C1 은 갭을 이슈로 남기고 Lock 하지 않는다.",
             "PRECONDITION_MISSING", "unit_cost 부재를 비롯한 요구 대비 갭이 대부분 미해소다(Ecommerce #24)."),
        item("CUSTOMER_PERSONA_v1", "PENDING", "simulator",
             "Persona 6종 구성비. src/simulator/ 가 C1 비범위다.",
             "PRECONDITION_MISSING", "시뮬레이터 미구현. 검증할 생성물이 없다."),
        item("HIDDEN_TRAIT_RULE_v1", "OUT_OF_SCOPE", "simulator",
             "measurement 는 data/hidden 을 참조조차 할 수 없다. C1 의 어떤 담당자도 이 항목을 Lock 할 위치에 있지 않다.",
             "PRECONDITION_MISSING", "tests/test_isolation.py FORBIDDEN_PATHS 가 src.measurement 의 data/hidden 참조를 금지한다."),
        item("BEHAVIOR_RULE_v1", "PENDING", "simulator",
             "일별 행동 생성 규칙. 시뮬레이터 미가동.",
             "PRECONDITION_MISSING", "src/simulator/ 미구현."),
        item("ECONOMIC_RULE_v1", "PENDING", "measurement",
             "확정안은 economic-rule-v1.md 에 있다. 선행 조건 G-9·G-10·G-12 미충족으로 아직 Lock 하지 않았다.",
             "NOT_RUN", "config/economic_config.yaml 이 아직 없다(이슈 #47 미착수)."),
        item("CHURN_DEFINITION_v1", "PENDING", "measurement",
             "판정 방식(고정 윈도우)과 label_window_days=42 는 Lock 대상이나, 임계값 28/42/60 은 Lock 하지 않는다 — 확정 절차(data_spec §5.1)가 시뮬레이터를 요구한다.",
             "PARAM_UNCONFIRMED", "임계값 확정 절차 ①~④가 전부 시뮬레이터를 요구한다."),
        item("TREATMENT_RESPONSE_v1", "OUT_OF_SCOPE", "simulator",
             "Treatment 반응(tau, 4분면)은 simulator 소유다. Treatment 비용(T0~T4)은 ECONOMIC_RULE_v1 에 속하며 서로 다른 항목이다.",
             "PRECONDITION_MISSING", "src/simulator/ 미구현."),
        item("EVENT_SCHEMA_v1", "PENDING", "measurement",
             "Lock 범위는 events 테이블에 한정한다. 나머지 6개 테이블(customers·orders·order_items·products·marketing_actions·assignment)은 미정의이며 이 Lock 이 덮지 않는다.",
             "NOT_RUN", "선행 조건 G-1~G-5(허용값 Enum·식별자 호출·타임존 정책) 미충족. 이슈 #53·#54 미완."),
        item("KPI_DEFINITION_v1", "PENDING", "measurement",
             "계산 계약(이름 ↔ 계산식·모집단·기간·분모)만 GATE 1 대상이고, 판정 역할 배정(Primary 지정·C_rule·B)은 GATE 2 대상이다.",
             "NOT_RUN", "src/measurement/kpi.py 가 아직 없다(이슈 #46 미착수)."),
    ]
    doc["unlocked_items"] = [
        {"id": "G-1", "title": "category 허용값 5종 Enum 정의 + validate_event() 검사", "met": False,
         "evidence": "schema.py:115 는 '상품 카테고리 5종'을 설명 문자열로만 적는다."},
        {"id": "G-3", "title": "validate_event() 가 check_identifier() 를 호출한다", "met": False,
         "evidence": "schema.py:324-326 이 어디에서도 호출되지 않는다."},
        {"id": "G-5", "title": "타임존 정책 확정·강제", "met": False, "evidence": "이슈 #53 D1-3."},
        {"id": "G-6", "title": "동일 root 재기록 시 기존 파티션 보존", "met": False,
         "evidence": "이슈 #53 D1-1 — 덮어쓰기 재현 확인."},
        {"id": "G-13", "title": "docs/event_schema.md 가 코드와 일치", "met": True,
         "evidence": "gen_event_schema_doc.py 재생성 diff 0 (W1 실행 확인)."},
        {"id": "G-14", "title": "python3 -m unittest discover -s tests 전건 통과", "met": None,
         "evidence": "이 게시 실행에서 확인하지 않았다. 확인하지 않은 것을 통과로 적지 않는다."},
        {"id": "G-15", "title": "Lock 시점 커밋 SHA·config 해시 기록 절차", "met": False,
         "evidence": "config/gate1_lock.yaml 미작성."},
        {"id": "G-16", "title": "discount 필드 처리 방침 결정", "met": False,
         "evidence": "api-contracts.md §8 신규 발견 A-1 — 결정 D-16."},
    ]
    return doc


def build_index() -> dict:
    doc = envelope("index", [NOTICE_EMPTY])
    doc["publish_result"] = "ok"
    doc["verdict"] = {
        "level": "attention",
        "headline_code": "SINK_EMPTY",
        "headline_detail": "이벤트가 한 건도 수집되지 않았다. 커머스는 이벤트 기록이 미구현이고 시뮬레이터는 C1 범위 밖이다. 계산 불가 지표 12종 · 미실행 검사 10종 · 봉인 대기 9종.",
        "counts": {
            "quality_violations": 0,
            "checks_not_run": 10,
            "checks_blocked": 1,
            "metrics_unavailable": 12,
            "metrics_not_run": 0,
            "schema_gaps": 4,
            "lock_items_pending": 9,
            "rejected_events": 0,
        },
    }
    doc["artifacts"] = []
    doc["static_views"] = [{
        "route": "/triggers", "title": "모니터링 트리거",
        "reason_code": "PRECONDITION_MISSING",
        "reason_detail": "PRD §71 트리거 5종은 전부 변화를 조건으로 하는데 게시물 이력이 없어 비교 기준이 없다. C1 작동 0종 — 각 트리거의 차단 사유를 적은 계획된 부재 표로 정적 구현한다.",
    }]
    doc["views"] = {
        "V1": {"title": "수집 현황", "artifact": "ingestion_report", "route": "/ingestion"},
        "V2": {"title": "계약 위반", "artifact": "rejection_report", "route": "/rejections"},
        "V3": {"title": "필드 충족률", "artifact": "field_coverage_report", "route": "/coverage"},
        "V4": {"title": "KPI", "artifact": "kpi_report", "route": "/kpi"},
        "V5": {"title": "데이터 품질", "artifact": "data_quality_report", "route": "/quality"},
        "V6": {"title": "봉인 상태", "artifact": "freeze_status", "route": "/freeze"},
    }
    return doc


BUILDERS = {
    "ingestion_report": (build_ingestion, "results/measurement/ingestion_report.json"),
    "rejection_report": (build_rejection, "results/measurement/rejection_report.json"),
    "field_coverage_report": (build_field_coverage, "results/measurement/field_coverage_report.json"),
    "kpi_report": (build_kpi, "results/measurement/kpi_report.json"),
    "data_quality_report": (build_quality, "results/data_quality_report.json"),
    "freeze_status": (build_freeze, "results/measurement/freeze_status.json"),
}


def main() -> None:
    import hashlib
    OUT.mkdir(parents=True, exist_ok=True)
    index = build_index()
    for name, (builder, path) in BUILDERS.items():
        doc = builder()
        text = json.dumps(doc, ensure_ascii=False, indent=2) + "\n"
        (OUT / f"{name}.json").write_text(text, encoding="utf-8")
        index["artifacts"].append({
            "artifact": name,
            "path": path,
            "status": "published",
            "sha256": hashlib.sha256(text.encode()).hexdigest(),
            "bytes": len(text.encode()),
        })
    (OUT / "index.json").write_text(
        json.dumps(index, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"예시 {len(BUILDERS) + 1}건을 {OUT.relative_to(REPO)} 에 썼다.")


if __name__ == "__main__":
    main()
