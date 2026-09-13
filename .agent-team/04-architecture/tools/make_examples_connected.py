"""두 번째 예시 — 커머스가 이벤트를 보내는 상태 (설계 도구 · 제품 코드가 아니다).

빈 Sink 예시가 "아무것도 없을 때"를 보여준다면, 이 예시는 **각 화면의 모든 시각 상태가
한 벌에 다 나오는 상태**를 보여준다. 디자인·구현이 픽스처 하나로 전 상태를 확인할 수 있다.

★ 이 예시의 핵심 장면 (USP-1):
    revenue              = 41,283,400원   ← 값
    contribution_profit  = 계산 불가 · 원가 근거 없음   ← 같은 카드에 나란히

    coupon_cost 0원(기준: coupon_use 0건 중 0건)   ← "세어 봤고 0이었다"
    coupon_exposure_count = 계산 불가              ← "셀 근거가 없다"
    둘이 화면에서 달라야 한다.

실행:
    python3 .agent-team/04-architecture/tools/make_examples_connected.py
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO))

from src.measurement import schema as sc  # noqa: E402

OUT = REPO / ".agent-team/04-architecture/examples/commerce-connected"
RUN_ID = "MR-20260918-141205-7c4e91ab"
NOW = "2026-09-18T14:12:05.000+09:00"
FIRST = "2026-09-12T09:04:11.000+09:00"
LAST = "2026-09-18T13:58:02.000+09:00"

TOTAL = 18_430
PURCHASES = 1_204
REJECTED = 217

PROVENANCE = {
    "schema_version": sc.SCHEMA_VERSION,
    "repo_commit": "3f9a2c1400000000000000000000000000000000",
    "data_version": None,
    "simulator_commit": None,
    "null_reason": {"data_version": "PRECONDITION_MISSING",
                    "simulator_commit": "PRECONDITION_MISSING"},
    "config_hashes": {
        "config/economic_config.yaml":
            "9f2b1e77c4a3d8065b1e0f4a2c7d9e3b5a8c1f0d6e4b2a9c7f3d1e8b5a0c6f24"},
    "source_root": "data/raw",
    "sink_manifest_sha256":
        "1a4c9e2b7d05f38416c0b9e7a2d4f6081c3e5b7a9d2f4068b1e3c5a7d9f0b2e4",
    "generated_by": "(예시 파일 — 실제 게시에서는 생성기가 자기 실행 명령을 런타임에 기록한다)",
    "publisher_version": "(동일 — W5 에서 채운다)",
}

N_REFUND = {"code": "REFUND_NOT_ADJUSTED", "level": "assumption",
            "message": "revenue 는 총매출이며 환불·취소를 차감하지 않는다. 환불이 발생하는 환경에서는 contribution_profit 이 과대평가된다.",
            "reference": "economic-rule-v1.md §6 가정 A-REFUND"}
N_GAP = {"code": "INGESTION_GAP_UNDECIDABLE", "level": "limitation",
         "message": "이벤트 0건인 날짜에 대해 '수집 중단'과 '활동 없음'을 현재 데이터로 구분할 수 없다. heartbeat 레코드가 없다.",
         "reference": "api-contracts.md §10 X-5"}
N_SIMULATOR = {"code": "SIMULATOR_ABSENT", "level": "limitation",
               "message": "시뮬레이터 생성분이 0건이다. src/simulator/ 는 C1 범위 밖이며, 실험 판정 지표는 시뮬레이터 생성분만 쓴다(MEA-002).",
               "reference": "charter §5"}
N_PARAM = {"code": "CHURN_THRESHOLD_UNCONFIRMED", "level": "assumption",
           "message": "이탈 임계값 28/42/60 일은 가설값이며 GATE 1 에서 Lock 하지 않았다.",
           "reference": "kpi-definition-v1.md §1.1"}


def envelope(artifact: str, notices: list[dict]) -> dict:
    return {"contract_version": "measurement-publish/v1", "artifact": artifact,
            "run_id": RUN_ID, "generated_at": NOW, "timezone": "Asia/Seoul",
            "provenance": PROVENANCE, "notices": notices}


def basis(population, denom_def, *, denominator=None, observed=0,
          direction="none", days=None, **extra):
    out = {"population": population, "denominator_definition": denom_def,
           "denominator": denominator, "observed_count": observed,
           "window": {"direction": direction, "days": days}}
    out.update(extra)
    return out


def ok(value, unit, population, denom_def, **kw):
    return {"status": "ok", "value": value, "unit": unit,
            "basis": basis(population, denom_def, **kw)}


def unav(code, detail, unit, blocked_by=None):
    out = {"status": "unavailable", "value": None, "unit": unit,
           "reason_code": code, "reason_detail": detail}
    if blocked_by:
        out["blocked_by"] = blocked_by
    return out


def blk(kind, ref, code):
    return {"kind": kind, "ref": ref, "reason_code": code}


NO_SIM = unav("NO_SOURCE_EVENT", "시뮬레이터 생성분이 0건이다.", "krw")

# 이벤트 타입별 실측 분포 (커머스만)
TYPE_COUNTS = {
    "session_start": 2_940, "page_view": 5_110, "search": 0, "product_view": 4_802,
    "return_visit": 1_016, "add_to_cart": 1_688, "remove_from_cart": 244,
    "checkout_start": 1_318, "purchase": PURCHASES, "campaign_exposed": 0,
    "push_sent": 0, "coupon_exposed": 0, "coupon_clicked": 0, "coupon_use": 0,
    "review": 102, "cs_contact": 6,
}
assert sum(TYPE_COUNTS.values()) == TOTAL, sum(TYPE_COUNTS.values())

PARTITIONS = [
    ("2026-09-12", 2_641), ("2026-09-13", 3_180), ("2026-09-14", 2_904),
    ("2026-09-15", 0), ("2026-09-16", 3_512), ("2026-09-17", 3_301),
    ("2026-09-18", 2_892),
]


def split(commerce, simulator, combined=None):
    out = {"by_source": {"commerce": commerce, "simulator": simulator}}
    if combined is not None:
        out["combined"] = combined
    return out


def sim_zero(unit="count", population="시뮬레이터 생성 이벤트"):
    return ok(0, unit, population, "분모 없음 (합계·건수)", observed=0)


def build_ingestion() -> dict:
    doc = envelope("ingestion_report", [N_GAP, N_SIMULATOR])
    attempted = TOTAL + REJECTED
    doc["totals"] = {
        "events_ingested": split(
            ok(TOTAL, "count", "저장된 커머스 이벤트", "분모 없음 (합계)", observed=TOTAL),
            sim_zero(),
            ok(TOTAL, "count", "저장된 전 이벤트", "분모 없음 (합계)", observed=TOTAL)),
        "events_rejected": ok(REJECTED, "count", "수집 시도된 전 이벤트",
                              "분모 없음 (합계)", observed=attempted),
        "rejection_rate": ok(round(REJECTED / attempted, 4), "ratio",
                             "수집 시도된 전 이벤트", "수집 시도 건수 (저장 + 거부)",
                             denominator=attempted, observed=attempted),
        "event_type_coverage": ok(round(sum(1 for v in TYPE_COUNTS.values() if v) / 16, 4),
                                  "ratio", "EventType 16종", "고정 분모 16",
                                  denominator=16, observed=TOTAL),
        "partition_day_count": ok(len([p for p in PARTITIONS if p[1]]), "count",
                                  "파티션 디렉터리", "분모 없음 (합계)",
                                  observed=len(PARTITIONS)),
        "ingestion_days_gap": ok(
            1, "count", "관측 구간(2026-09-12 ~ 2026-09-18) 내 날짜",
            "분모 없음 (합계)", observed=len(PARTITIONS),
            excluded_reason="구간 밖 날짜는 세지 않는다"),
        "ingestion_gap_attribution": GAP_ATTRIBUTION,
        "unavailable_metric_count": ok(6, "count", "Observable 지표 16종",
                                       "고정 분모 16", denominator=16, observed=16),
    }
    doc["sources"] = {
        "commerce": {"link_state": "connected", "first_event_at": FIRST,
                     "last_event_at": LAST, "event_count": TOTAL,
                     "staleness": STALENESS_UNDECIDABLE},
        "simulator": {"link_state": "never_connected", "first_event_at": None,
                      "last_event_at": None, "event_count": 0,
                      "staleness": STALENESS_UNDECIDABLE},
    }
    doc["by_event_type"] = {
        name: split(ok(count, "count", f"{name} 이벤트", "분모 없음 (합계)", observed=count),
                    sim_zero(population=f"{name} 이벤트 (시뮬레이터)"))
        for name, count in TYPE_COUNTS.items()
    }
    doc["partitions"] = [
        {"date": date, "present": bool(rows), "in_observed_range": True,
         "rows": split(ok(rows, "count", f"{date} 커머스 이벤트", "분모 없음 (합계)", observed=rows),
                       sim_zero(population=f"{date} 시뮬레이터 이벤트"))}
        for date, rows in PARTITIONS
    ]
    return doc


REASONS = [
    ("IDENTIFIER_FORMAT", "식별자 형식 위반", 148,
     {"customer_id": 148}, {"session_start": 61, "purchase": 42, "page_view": 45}),
    ("DISALLOWED_ENUM_VALUE", "허용값 밖의 값", 44,
     {"page_type": 31, "category": 13}, {"page_view": 31, "product_view": 13}),
    ("MISSING_REQUIRED_FIELD", "필수 필드 누락", 19,
     {"session_id": 19}, {"add_to_cart": 19}),
    ("TIMEZONE_POLICY", "타임존 정책 위반", 6,
     {"timestamp": 6}, {"purchase": 6}),
]


def build_rejection() -> dict:
    doc = envelope("rejection_report", [])
    attempted = TOTAL + REJECTED
    doc["totals"] = {
        "events_rejected": ok(REJECTED, "count", "수집 시도된 전 이벤트",
                              "분모 없음 (합계)", observed=attempted),
        "rejection_rate": ok(round(REJECTED / attempted, 4), "ratio",
                             "수집 시도된 전 이벤트", "수집 시도 건수 (저장 + 거부)",
                             denominator=attempted, observed=attempted),
        "distinct_reasons": ok(len(REASONS), "count", "거부 사유 종류",
                               "분모 없음 (합계)", observed=REJECTED),
    }
    doc["by_reason"] = [
        {"reason_key": key, "reason_label": label, "count": count,
         "by_field": fields, "by_event_type": types}
        for key, label, count, fields, types in REASONS
    ]
    doc["samples"] = [
        {"reason_key": "IDENTIFIER_FORMAT", "event_type": "purchase",
         "partition_date": "2026-09-14", "source": "commerce",
         "problems": ["customer_id 형식 위반 — ^C\\d{8}$ 를 만족하지 않는다"],
         "offending_fields": ["customer_id"],
         "offending_values": {"customer_id": "test-user-1"}},
        {"reason_key": "DISALLOWED_ENUM_VALUE", "event_type": "page_view",
         "partition_date": "2026-09-13", "source": "commerce",
         "problems": ["page_type 허용값 8종 밖의 값"],
         "offending_fields": ["page_type"],
         "offending_values": {"page_type": "main"}},
        {"reason_key": "MISSING_REQUIRED_FIELD", "event_type": "add_to_cart",
         "partition_date": "2026-09-16", "source": "commerce",
         "problems": ["add_to_cart: 필수 필드 누락 — session_id"],
         "offending_fields": ["session_id"]},
        {"reason_key": "TIMEZONE_POLICY", "event_type": "purchase",
         "partition_date": "2026-09-17", "source": "commerce",
         "problems": ["timestamp 가 KST(+09:00)가 아니다"],
         "offending_fields": ["timestamp"],
         "offending_values": {"timestamp": "2026-09-17T23:41:02.000Z"}},
    ]
    return doc


FILL = {
    "event_id": 1.0, "customer_id": 1.0, "timestamp": 1.0, "event_type": 1.0,
    "session_id": 0.9871, "session_duration": 0.1602, "page_type": 1.0,
    "product_id": 1.0, "category": 1.0, "quantity": 1.0, "unit_price": 0.8814,
    "order_id": 1.0, "order_amount": 1.0, "coupon_id": 0.0, "campaign_id": 0.0,
    "treatment_id": 0.0, "treatment_group": 0.0, "experiment_id": 0.0,
    "service_version": 1.0, "customer_version": 0.0,
    "simulator_version": 0.0, "random_seed": 0.0,
}
APPLICABLE = {
    "event_id": TOTAL, "customer_id": TOTAL, "timestamp": TOTAL, "event_type": TOTAL,
    "session_id": 18_424, "session_duration": 18_424, "page_type": 18_322,
    "product_id": 6_836, "category": 6_836, "quantity": 1_932, "unit_price": 6_734,
    "order_id": 2_630, "order_amount": 2_522, "coupon_id": 2_522, "campaign_id": 1_204,
    "treatment_id": TOTAL, "treatment_group": TOTAL, "experiment_id": TOTAL,
    "service_version": TOTAL, "customer_version": TOTAL,
    "simulator_version": TOTAL, "random_seed": TOTAL,
}

sys.path.insert(0, str(REPO / ".agent-team/04-architecture/tools"))  # noqa: E402
from make_examples import (FIELD_IMPACT, SCHEMA_GAPS,  # noqa: E402
                           GAP_ATTRIBUTION, STALENESS_UNDECIDABLE)


def build_field_coverage() -> dict:
    doc = envelope("field_coverage_report", [N_SIMULATOR])
    fields = {}
    for spec in sc.EVENT_FIELDS:
        applicable = sorted(e.value for e in sc.EventType
                            if sc.requirement(e, spec.name) is not sc.Requirement.NOT_APPLICABLE)
        n = APPLICABLE[spec.name]
        rate = FILL[spec.name]
        fields[spec.name] = {
            "group": spec.group.value,
            "fill_rate": split(
                ok(rate, "ratio", f"{spec.name} 가 적용되는 커머스 이벤트",
                   "NOT_APPLICABLE 을 제외한 적용 대상 건수",
                   denominator=n, observed=n),
                unav("NO_SOURCE_EVENT", "시뮬레이터 생성분이 0건이라 분모가 없다.", "ratio")),
            "applicable_event_types": applicable,
            "blocks_metrics": FIELD_IMPACT.get(spec.name, []),
        }
    doc["fields"] = fields
    doc["missing_fields"] = ["coupon_id", "campaign_id", "treatment_id",
                             "treatment_group", "experiment_id", "customer_version",
                             "simulator_version", "random_seed"]
    doc["schema_gaps"] = SCHEMA_GAPS
    return doc


REVENUE = 41_283_400


def build_kpi() -> dict:
    doc = envelope("kpi_report", [N_REFUND, N_PARAM, N_SIMULATOR])
    doc["index_date"] = "2026-09-18"
    doc["definition_version"] = "kpi-definition-v1 (미Lock · 확정안)"

    def m(name, layer, role, population, direction, days, denom, formula, ref,
          value, src=None, blocks=None):
        item = {"name": name, "layer": layer, "role": role, "population": population,
                "window": {"direction": direction, "days": days},
                "denominator_definition": denom, "formula": formula,
                "definition_ref": ref, "value": value}
        if src:
            item["source_events"] = src
        if blocks is not None:
            item["blocks"] = blocks
        return item

    metrics = [
        m("events_ingested", "collection_health", "none", "events", "none", None,
          "분모 없음 (합계)", "count(저장된 이벤트)", "kpi-definition-v1.md §3",
          split(ok(TOTAL, "count", "저장된 커머스 이벤트", "분모 없음 (합계)", observed=TOTAL),
                sim_zero(),
                ok(TOTAL, "count", "저장된 전 이벤트", "분모 없음 (합계)", observed=TOTAL)),
          blocks=[]),

        # ★ USP-1 대표 장면 1 — 값 / 계산 불가가 같은 카드에 나란히
        m("revenue", "business_kpi", "none", "orders", "retrospective", 42,
          "분모 없음 (합계)", "sum(order_amount)", "kpi-definition-v1.md §5.1",
          split(ok(REVENUE, "krw", "purchase 이벤트", "분모 없음 (합계)",
                   observed=PURCHASES, direction="retrospective", days=42),
                unav("NO_SOURCE_EVENT", "시뮬레이터 생성분이 0건이다.", "krw")),
          ["purchase"], blocks=["contribution_profit", "incremental_revenue"]),
        m("cogs", "business_kpi", "none", "orders", "retrospective", 42,
          "분모 없음 (합계)", "sum(unit_cost * quantity) 단 has_cost_basis(order) 인 주문만",
          "economic-rule-v1.md EC-1 · EC-2",
          split(unav("NO_COST_BASIS",
                     f"주문 {PURCHASES:,}건 중 {PURCHASES:,}건에 unit_cost 없음. 원가율을 곱해 추정하지 않는다.",
                     "krw", [blk("schema_gap", "unit_cost", "NO_COST_BASIS")]),
                unav("NO_SOURCE_EVENT", "시뮬레이터 생성분이 0건이다.", "krw")),
          ["purchase"], blocks=["contribution_profit"]),
        m("contribution_profit", "business_kpi", "none", "orders", "retrospective", 42,
          "분모 없음 (합계)",
          "revenue - cogs - coupon_cost - shipping_subsidy - message_cost - campaign_fixed_cost/N_targeted",
          "economic-rule-v1.md §3.4",
          split(unav("NO_COST_BASIS",
                     "cogs 를 계산할 수 없어 기여이익이 성립하지 않는다. revenue 는 계산되지만 이익은 계산되지 않는다.",
                     "krw", [blk("metric", "cogs", "NO_COST_BASIS"),
                             blk("schema_gap", "discount", "MISSING_FIELD"),
                             blk("schema_gap", "shipping_fee", "MISSING_FIELD")]),
                unav("NO_SOURCE_EVENT", "시뮬레이터 생성분이 0건이다.", "krw")),
          blocks=["incremental_contribution_profit", "ai_roi"]),

        # ★ USP-1 대표 장면 2 — "세어 봤고 0" vs "셀 근거가 없다"
        m("coupon_cost", "business_kpi", "none", "orders", "retrospective", 42,
          "분모 없음 (합계)", "sum(discount) — 쿠폰이 실제 사용된 주문에만",
          "kpi-definition-v1.md §5.1 · api-contracts.md §8",
          split(unav("MISSING_FIELD",
                     "discount 필드가 DATA-003 22컬럼에 없다. coupon_use 이벤트도 0건이다.",
                     "krw", [blk("schema_gap", "discount", "MISSING_FIELD"),
                             blk("event_type", "coupon_use", "NO_SOURCE_EVENT")]),
                unav("NO_SOURCE_EVENT", "시뮬레이터 생성분이 0건이다.", "krw")),
          blocks=["marketing_cost", "contribution_profit"]),
        m("coupon_usage_count", "collection_health", "none", "events", "retrospective", 42,
          "분모 없음 (건수)", "count(coupon_use)", "kpi-definition-v1.md §3",
          split(ok(0, "count", "coupon_use 이벤트", "분모 없음 (건수)",
                   observed=0, direction="retrospective", days=42),
                sim_zero()),
          ["coupon_use"], blocks=[]),

        m("average_order_value", "customer_kpi", "none", "P_buyer", "retrospective", 42,
          "주문 건수 (고객 수가 아니다)", "sum(order_amount) / count(purchase)",
          "kpi-definition-v1.md §4",
          split(ok(34_288, "krw", "purchase 이벤트", "주문 건수",
                   denominator=PURCHASES, observed=PURCHASES,
                   direction="retrospective", days=42),
                unav("NO_SOURCE_EVENT", "시뮬레이터 생성분이 0건이다.", "krw")),
          ["purchase"], blocks=[]),
        m("churn_rate", "customer_kpi", "secondary", "P_buyer", "point_in_time", None,
          "구매 이력 보유 고객 수",
          "|{c : days_since_last_purchase(c,D) >= no_purchase_days}| / |P_buyer(D)|",
          "kpi-definition-v1.md §4",
          split({"status": "unconfirmed", "value": 0.1834, "unit": "ratio",
                 "basis": basis("P_buyer(2026-09-18)", "구매 이력 보유 고객 수",
                                denominator=894, observed=894,
                                direction="point_in_time"),
                 "reason_code": "PARAM_UNCONFIRMED",
                 "reason_detail": "이탈 임계값이 GATE 1 에서 확정되지 않았다. 아래 파라미터로 계산한 값이다.",
                 "params_used": {"no_purchase_days": 42, "at_risk_days": 28}},
                unav("NO_SOURCE_EVENT", "시뮬레이터 생성분이 0건이다.", "ratio")),
          ["purchase"], blocks=["retention_rate", "winback_rate"]),
        m("campaign_response_count", "collection_health", "none", "events",
          "retrospective", 42, "분모 없음 (건수)",
          "count(campaign_exposed) + count(coupon_clicked) + count(purchase)",
          "kpi-definition-v1.md §4.2",
          split(unav("NO_SOURCE_EVENT",
                     "campaign_exposed·coupon_clicked 이벤트가 0건이다. 쿠폰 비종속 캠페인의 클릭을 담을 이벤트가 없어 이 지표는 쿠폰 캠페인만 측정한다.",
                     "count", [blk("event_type", "campaign_exposed", "NO_SOURCE_EVENT"),
                               blk("event_type", "coupon_clicked", "NO_SOURCE_EVENT")]),
                unav("NO_SOURCE_EVENT", "시뮬레이터 생성분이 0건이다.", "count")),
          blocks=[]),
        m("incremental_contribution_profit", "experiment", "primary", "test_holdout",
          "prospective", 42, "고객 수 (1인당 값 병기)", "CP_strategy - CP_S1_rule",
          "kpi-definition-v1.md §7.1",
          unav("NEEDS_TWO_STRATEGIES", "비교할 두 전략이 없다. 전략 구현은 C1 범위 밖이다.",
               "krw", [blk("metric", "contribution_profit", "NO_COST_BASIS"),
                       blk("strategy", "S1_rule_based", "NEEDS_TWO_STRATEGIES")]),
          blocks=["ai_roi"]),
        m("qini_coefficient", "experiment", "primary", "test_holdout", "prospective", 42,
          "Test 고객 수", "Qini curve 면적", "kpi-definition-v1.md §7.1",
          unav("NEEDS_MODEL_OUTPUT", "Uplift 모델 산출물이 없다. C1 범위 밖이다.", "ratio",
               [blk("model_output", "uplift_scores", "NEEDS_MODEL_OUTPUT")]),
          blocks=["auuc"]),
        m("marketing_cost", "business_kpi", "guardrail", "orders", "retrospective", 42,
          "분모 없음 (합계)", "message_cost + coupon_cost + campaign_fixed_cost",
          "kpi-definition-v1.md §5.1",
          split(unav("MISSING_FIELD",
                     "coupon_cost 를 계산할 수 없고 push_sent 이벤트가 0건이다. 임계값 C_rule 도 GATE 2 확정 항목이다.",
                     "krw", [blk("metric", "coupon_cost", "MISSING_FIELD"),
                             blk("event_type", "push_sent", "NO_SOURCE_EVENT"),
                             blk("parameter", "C_rule", "PARAM_UNCONFIRMED")]),
                unav("NO_SOURCE_EVENT", "시뮬레이터 생성분이 0건이다.", "krw")),
          blocks=[]),
        m("purchase_interval", "customer_kpi", "none", "P_buyer", "retrospective", 42,
          "구매 2건 이상인 고객 수 (제외 인원 병기)",
          "고객별 연속 purchase 간 일수의 중앙값 → 그 값들의 모집단 중앙값",
          "kpi-definition-v1.md §4",
          split(ok(11.0, "days", "P_buyer(2026-09-18) ∧ 구매 2건 이상",
                   "정의되는 고객 수", denominator=312, observed=894,
                   direction="retrospective", days=42, excluded_count=582,
                   excluded_reason="구매 1건인 고객은 구매 간격이 정의되지 않는다"),
                unav("NO_SOURCE_EVENT", "시뮬레이터 생성분이 0건이다.", "days")),
          ["purchase"], blocks=[]),
    ]
    doc["metrics"] = metrics

    counts = {"ok": 0, "unconfirmed": 0, "unavailable": 0, "blocked": 0, "not_run": 0}
    by_layer: dict[str, dict[str, int]] = {}
    for item in metrics:
        v = item["value"]
        statuses = [v["status"]] if "status" in v else [x["status"] for x in v["by_source"].values()]
        worst = "ok" if all(s == "ok" for s in statuses) else next(s for s in statuses if s != "ok")
        counts[worst] += 1
        by_layer.setdefault(item["layer"], {}).setdefault(worst, 0)
        by_layer[item["layer"]][worst] += 1
    doc["summary"] = {"total": len(metrics), **counts, "by_layer": by_layer}
    return doc


def build_quality() -> dict:
    doc = envelope("data_quality_report", [N_SIMULATOR])
    doc["gate_result"] = "fail"          # ★ 위반 상태의 렌더를 보이기 위한 시나리오
    doc["spec_coverage"] = {
        "spec_items": [
            {"spec_ref": "유일성", "covered_by": ["DQ-01", "DQ-02", "DQ-02b"], "worst_status": "not_run"},
            {"spec_ref": "참조 무결성", "covered_by": ["DQ-03"], "worst_status": "not_run"},
            {"spec_ref": "시간 정합성", "covered_by": ["DQ-04", "DQ-05", "DQ-06"], "worst_status": "not_run"},
            {"spec_ref": "퍼널 정합성", "covered_by": ["DQ-07", "DQ-08"], "worst_status": "fail"},
            {"spec_ref": "금액 정합성", "covered_by": ["DQ-09", "DQ-10"], "worst_status": "not_run"},
            {"spec_ref": "완전성", "covered_by": ["DQ-11", "DQ-12"], "worst_status": "not_run"},
            {"spec_ref": "생성 이탈률", "covered_by": ["DQ-13"], "worst_status": "not_run"},
            {"spec_ref": "실험 균형", "covered_by": ["DQ-14"], "worst_status": "not_run"},
            {"spec_ref": "처치 강도", "covered_by": ["DQ-15"], "worst_status": "not_run"},
            {"spec_ref": "4분면 분포", "covered_by": ["DQ-16"], "worst_status": "not_run"},
            {"spec_ref": "재현성", "covered_by": ["DQ-17"], "worst_status": "blocked"},
        ],
        "reported_checks": 6,
        "unmapped_spec_items": [],
    }
    doc["checks"] = [
        {"id": "DQ-01", "spec_ref": "유일성", "title": "event_id 전역 유일",
         "status": "pass", "violations": 0, "examined_rows": TOTAL,
         "scope": "저장된 events 파티션 전 구간(2026-09-12 ~ 2026-09-18)."},
        {"id": "DQ-02b", "spec_ref": "유일성(범위 축소)", "title": "order_id 당 purchase 이벤트 1건",
         "status": "pass", "violations": 0, "examined_rows": PURCHASES,
         "scope": "events 테이블에 한정. checkout_start·coupon_use 도 order_id 를 갖지만 중복이 정상이므로 purchase 만 센다."},
        {"id": "DQ-07", "spec_ref": "퍼널 정합성", "title": "purchase 는 선행 checkout_start 보유",
         "status": "pass", "violations": 0, "examined_rows": PURCHASES,
         "scope": "order_id 로 대응. 파티션 경계를 넘는 주문을 놓치지 않도록 전 구간을 한 번에 본다."},
        {"id": "DQ-08", "spec_ref": "퍼널 정합성", "title": "coupon_use 는 선행 coupon_exposed 보유",
         "status": "fail", "violations": 3, "examined_rows": PURCHASES,
         "scope": "coupon_id 로 대응. coupon_use 이벤트 자체는 0건이나 purchase 에 coupon_id 가 붙은 3건이 노출 기록 없이 나타났다.",
         "samples": [
             {"detail": "coupon_id=CPN-A19XZ4 가 노출 기록 없이 주문에 사용됐다",
              "order_id": "O20260914-000317", "partition_date": "2026-09-14"},
             {"detail": "coupon_id=CPN-B72KQ0 가 노출 기록 없이 주문에 사용됐다",
              "order_id": "O20260916-001044", "partition_date": "2026-09-16"},
             {"detail": "coupon_id=CPN-C08MW5 가 노출 기록 없이 주문에 사용됐다",
              "order_id": "O20260917-000892", "partition_date": "2026-09-17"},
         ]},
        {"id": "DQ-10", "spec_ref": "금액 정합성", "title": "음수 금액 0건",
         "status": "pass", "violations": 0, "examined_rows": TOTAL,
         "scope": "quantity·unit_price·order_amount·session_duration 4종."},
        {"id": "DQ-09", "spec_ref": "금액 정합성",
         "title": "order_amount = sum(unit_price*quantity) - discount, 오차 0원",
         "status": "not_run", "violations": None,
         "reason_code": "PRECONDITION_MISSING",
         "reason_detail": "discount 필드가 22컬럼에 없고 purchase 는 주문 단위 1행이라 품목 합계를 재구성할 수 없다. order_items 테이블이 필요하다.",
         "scope": "C1 에서 원리적으로 실행 불가."},
        {"id": "DQ-17", "spec_ref": "재현성", "title": "동일 seed 재실행 시 events.parquet SHA-256 일치",
         "status": "blocked", "violations": None, "reason_code": "BLOCKED",
         "reason_detail": "pyarrow 가 설치되지 않아 Parquet 경로가 실행되지 않았다.",
         "scope": "jsonl.gz 형식의 해시 재현성은 tests/test_sink.py 가 검사한다. Parquet 형식만 미검증."},
    ]
    return doc


def build_freeze() -> dict:
    doc = envelope("freeze_status", [
        {"code": "GATE1_NOT_PASSED", "level": "limitation",
         "message": "C1 은 GATE 1 을 통과시키지 않는다. 부분 봉인만 하며 EXPERIMENT_ENVIRONMENT_v1 을 선언하지 않는다.",
         "reference": "gate1-lock-scope.md §1"},
        {"code": "LOCK_MISMATCH", "level": "failure",
         "message": "EVENT SCHEMA v1 의 정본 파일 하나가 Lock 시점과 달라졌다. FREEZE-003 절차를 검토해야 한다.",
         "reference": "gate1-freeze-procedure.md §4"},
        {"code": "DASHBOARD_NOT_ISOLATION_CHECKED", "level": "limitation",
         "message": "격리 검사가 dashboard/ 를 보지 않는다. tests/test_isolation.py 는 src/**/*.py 만 순회한다.",
         "reference": "dashboard-architecture.md §6"},
    ])
    doc["gate"] = "GATE_1"
    doc["overall"] = "violated"          # ★ 위반 상태의 렌더
    # 이슈 #60 — 대조 결과를 게시물에 낸다.
    # ★ 여기서는 `match` 다. 이 픽스처의 목적은 **품질 위반** 화면이고,
    #   `freeze_mismatch > 0` 으로 두면 판정 우선순위상 headline 이
    #   FREEZE_MISMATCH 로 바뀌어 픽스처가 자기 목적과 어긋난다.
    #   봉인 불일치 화면이 필요하면 그 용도의 픽스처를 따로 만든다.
    doc["verification"] = "match"
    doc["mismatches"] = []
    doc["lock_record"] = {
        "path": "config/gate1_lock.yaml",
        "sha256": "b7e1d0c4a9f2635e8017c3b5d9a4e2f60817b3c5d9e1a4f60827b3c5d9e1a4f6",
        "locked_at": "2026-09-16T18:30:00.000+09:00",
        "locked_by": "(예시 · 실제 Lock 시 사람 이름을 기록한다)",
        "repo_commit": "88c1a730000000000000000000000000000000aa",
        "simulator_commit": None,
    }

    def item(name, status, owner, scope, code=None, detail=None, files=None):
        out = {"item": name, "status": status, "owner_part": owner, "scope_note": scope}
        if code:
            out["reason_code"] = code
            out["reason_detail"] = detail
        if files is not None:
            out["canonical_files"] = files
        return out

    H1 = "4d2f8a1c6e0b9375f4a2c8e1d0b6395f7a3c5e1d0b6284f7a3c5e1d0b6284f7a"
    H2 = "0b6284f7a3c5e1d0b6284f7a3c5e1d04d2f8a1c6e0b9375f4a2c8e1d0b6395f7"
    doc["items"] = [
        item("SERVICE_v1", "PENDING", "commerce",
             "기준 환경(커머스)의 확정. C1 은 갭을 이슈로 남기고 Lock 하지 않는다.",
             "PRECONDITION_MISSING", "unit_cost 부재를 비롯한 요구 대비 갭이 대부분 미해소다."),
        item("CUSTOMER_PERSONA_v1", "PENDING", "simulator", "Persona 6종 구성비. simulator 미가동.",
             "PRECONDITION_MISSING", "시뮬레이터 미구현."),
        item("HIDDEN_TRAIT_RULE_v1", "OUT_OF_SCOPE", "simulator",
             "measurement 는 data/hidden 을 참조조차 할 수 없다.",
             "PRECONDITION_MISSING", "격리 규칙상 C1 의 어떤 담당자도 Lock 할 위치에 있지 않다."),
        item("BEHAVIOR_RULE_v1", "PENDING", "simulator", "일별 행동 생성 규칙.",
             "PRECONDITION_MISSING", "src/simulator/ 미구현."),
        item("ECONOMIC_RULE_v1", "PARTIAL", "measurement",
             "원가율·Treatment 단위 비용·비용 회계 3원칙·N_targeted·기여이익식·EC-1·EC-2·AI 투자비용·가정 A-REFUND·EC-7 을 Lock 한다. C_rule·예산 상한 B·쿠폰 사용률 30% 가정은 Lock 하지 않는다.",
             files=[{"path": "config/economic_config.yaml", "locked_sha256": H1,
                     "current_sha256": H1, "verification": "match"},
                    {"path": "src/measurement/economics.py", "locked_sha256": H2,
                     "current_sha256": H2, "verification": "match"}]),
        item("CHURN_DEFINITION_v1", "PARTIAL", "measurement",
             "판정 방식(고정 윈도우)과 운영 상태/모델 라벨의 분리, label_window_days=42 를 Lock 한다. 임계값 28/42/60 은 가설값이며 Lock 하지 않는다.",
             "PARAM_UNCONFIRMED", "확정 절차(data_spec §5.1)가 시뮬레이터를 요구한다."),
        item("TREATMENT_RESPONSE_v1", "OUT_OF_SCOPE", "simulator",
             "Treatment 반응(tau·4분면)은 simulator 소유다. Treatment 비용은 ECONOMIC_RULE_v1 에 속하는 다른 항목이다.",
             "PRECONDITION_MISSING", "src/simulator/ 미구현."),
        item("EVENT_SCHEMA_v1", "PARTIAL", "measurement",
             "Lock 범위는 events 테이블에 한정한다. customers·orders·order_items·products·marketing_actions·assignment 6개 테이블은 정의되지 않았으며 이 Lock 이 덮지 않는다.",
             files=[{"path": "src/measurement/schema.py", "locked_sha256": H1,
                     "current_sha256":
                         "ffee1122334455667788990011223344556677889900aabbccddeeff00112233",
                     "verification": "mismatch"},
                    {"path": "docs/event_schema.md", "locked_sha256": H2,
                     "current_sha256": None, "verification": "not_run"}]),
        item("KPI_DEFINITION_v1", "PARTIAL", "measurement",
             "계산 계약(이름 ↔ 계산식·모집단·기간·분모)만 Lock 한다. 판정 역할 배정·C_rule·예산 상한 B 는 GATE 2 대상이다.",
             files=[{"path": "src/measurement/kpi.py", "locked_sha256": H1,
                     "current_sha256": H1, "verification": "match"}]),
    ]
    doc["unlocked_items"] = [
        {"id": "G-8", "title": "파생 상태 기록 경로 결정", "met": False,
         "evidence": "DerivedStateType 이 EventType 밖이라 Sink 에 기록할 수단이 없다."},
        {"id": "G-9", "title": "shipping_subsidy 처리 방침", "met": False, "evidence": "결정 D-3 대기."},
        {"id": "G-13", "title": "docs/event_schema.md 가 코드와 일치", "met": None,
         "evidence": "이 실행에서 재생성 대조를 하지 않았다. 확인하지 않은 것을 통과로 적지 않는다."},
        {"id": "G-16", "title": "discount 필드 처리 방침 결정", "met": False, "evidence": "결정 D-16 대기."},
    ]
    return doc


def build_index() -> dict:
    doc = envelope("index", [N_REFUND, N_SIMULATOR])
    doc["publish_result"] = "ok"
    doc["verdict"] = {
        "level": "violation",
        "headline_code": "QUALITY_VIOLATION",
        "headline_detail": "퍼널 정합성 검사에서 위반 3건이 나왔다. 봉인된 정본 파일 1건이 Lock 시점과 다르다. 미실행 검사 8종.",
        "counts": {"quality_violations": 3, "checks_not_run": 8, "checks_blocked": 1,
                   "metrics_unavailable": 7, "metrics_not_run": 0, "schema_gaps": 4,
                   "lock_items_pending": 6, "freeze_mismatch": 0,
                   "rejected_events": REJECTED},
    }
    doc["artifacts"] = []
    doc["static_views"] = [{
        "route": "/triggers", "title": "모니터링 트리거",
        "reason_code": "PRECONDITION_MISSING",
        "reason_detail": "PRD §71 트리거 5종은 전부 변화를 조건으로 하는데 게시물 이력이 없어 비교 기준이 없다. C1 작동 0종.",
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
    OUT.mkdir(parents=True, exist_ok=True)
    index = build_index()
    for name, (builder, path) in BUILDERS.items():
        text = json.dumps(builder(), ensure_ascii=False, indent=2) + "\n"
        (OUT / f"{name}.json").write_text(text, encoding="utf-8")
        index["artifacts"].append({
            "artifact": name, "path": path, "status": "published",
            "sha256": hashlib.sha256(text.encode()).hexdigest(),
            "bytes": len(text.encode())})
    (OUT / "index.json").write_text(
        json.dumps(index, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"예시 {len(BUILDERS) + 1}건을 {OUT.relative_to(REPO)} 에 썼다.")


if __name__ == "__main__":
    main()
