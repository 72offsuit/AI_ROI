#!/usr/bin/env python3
"""`src/measurement/schema.py` 에서 `docs/event_schema.md` 를 생성한다.

스키마와 문서가 어긋나지 않도록 표를 손으로 쓰지 않는다.

    python3 scripts/gen_event_schema_doc.py > docs/event_schema.md
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.measurement import schema as sc  # noqa: E402

R = sc.Requirement
MARK = {R.REQUIRED: "●", R.OPTIONAL: "○", R.NOT_APPLICABLE: "—"}

IDENTIFIER_EXAMPLES = {
    "event_id": "3f2a1b4c-5d6e-4f70-8912-a3b4c5d6e7f8",
    "customer_id": "C00012345",
    "session_id": "S-C00012345-1759276800000",
    "order_id": "O20251001-000123",
    "product_id": "P0042",
    "coupon_id": "CPN-A1B2C3",
    "campaign_id": "CMP-20251001-001",
    "treatment_id": "T3",
    "experiment_id": "EXP-20251001-01",
}


def emit(*lines: str) -> None:
    for line in lines:
        print(line)


def main() -> None:
    emit(
        "# 이벤트 스키마 — 측정 계층 계약",
        "",
        f'> 정본은 `src/measurement/schema.py` (`SCHEMA_VERSION = "{sc.SCHEMA_VERSION}"`).',
        "> 이 문서의 표는 그 모듈에서 생성했다. 스키마를 바꾸면 이 문서도 다시 생성한다.",
        ">",
        "> 근거: SRS DATA-003 · SIM-006 · ISO-003, PRD §21 · §30-31, `docs/data_spec.html` §7",
        "",
        "실제 서비스 UI와 시뮬레이터가 **같은 스키마로 같은 Sink에 기록**한다.",
        "어떤 필드를 통과시킬지 판단하는 기준은 하나다 — **실제 커머스 서비스에서 로그로 남을 수 있는가.**",
        "",
        "## 전역 규약",
        "",
        "| 항목 | 값 |",
        "|---|---|",
        f"| 스키마 버전 | `{sc.SCHEMA_VERSION}` — GATE 1에서 `event-schema-v1.0`으로 Lock |",
        f"| 타임존 | `{sc.TIMEZONE}` 단일 — **저장 기준**. 입력은 오프셋이 붙은 어떤 표기든 받아 KST 로 정규화한다 |",
        "| 오프셋 없는 timestamp | **거부**. 순간을 특정할 수 없으므로 추측하지 않는다 |",
        f"| timestamp 정밀도 | {sc.TIMESTAMP_PRECISION}. ISO 8601 + offset (`2025-10-01T09:00:00.000+09:00`) |",
        f"| 세션 만료 | 무활동 {sc.SESSION_TIMEOUT_MINUTES}분 |",
        "",
        "## 필드",
        "",
        "| 필드 | 타입 | 그룹 | 설명 |",
        "|---|---|---|---|",
    )
    for f in sc.EVENT_FIELDS:
        emit(f"| `{f.name}` | `{f.dtype}` | {f.group.value} | {f.description} |")
    emit(
        "",
        "`event_id`·`customer_id`·`timestamp`·`event_type`는 **모든 이벤트에 필수**다.",
        "메타 4종(`service_version`·`customer_version`·`simulator_version`·`random_seed`)은",
        "재현성(SRS NFR-001 · SIM-011)을 위해 기록하며, 서비스 UI가 기록할 때는",
        "`simulator_version`·`random_seed`가 null이다.",
        "",
        "## 허용값",
        "",
        "`validate_event()` 가 **값이 있는 필드에만** 적용한다 — `None` 은 결손이지",
        "허용값 위반이 아니다. 둘을 섞으면 \"아직 안 준 것\"과 \"잘못 준 것\"이 한 줄로 보인다.",
        "",
        "| 필드 | 허용값 |",
        "|---|---|",
        f"| `category` | {' · '.join(f'`{c.value}`' for c in sc.Category)} |",
        f"| `page_type` | {' · '.join(f'`{p.value}`' for p in sc.PageType)} |",
        "",
        "**카테고리 어휘는 영문 코드가 정본이다** (SRS `COM-001`). `docs/data_spec.html` §6.1 의",
        "한글(신선식품·간편식·유제품·음료·생활용품)은 표 가독성을 위한 표기이며,",
        "**표시명 매핑은 UI 책임**이다 — 측정 계층은 코드만 안다.",
        "",
        "## 지표 상태 어휘",
        "",
        "게시물(`results/`)이 쓰는 어휘다. 정본은",
        "`.agent-team/04-architecture/schemas/common.schema.json` 이고,",
        "`tests/test_schema.py TestContractVocabulary` 가 그 파일을 읽어 대조한다.",
        "",
        "| Enum | 값 |",
        "|---|---|",
        f"| `MetricStatus` | {' · '.join(f'`{s.value}`' for s in sc.MetricStatus)} |",
        f"| `ReasonCode` | {' · '.join(f'`{r.value}`' for r in sc.ReasonCode)} |",
        "",
        "`unavailable`(근거가 없어 계산 못 했다)과 `not_run`(계산을 시도하지 않았다)은",
        "**다른 상태다.** 합치면 관측하지 않은 것을 관측했다고 말하게 된다.",
        "",
        "## 이벤트별 필수 / 선택 필드",
        "",
        "● 필수 · ○ 선택 · — 해당 없음. Core 4종과 Meta 4종은 공통이므로 표에서 제외했다.",
        "",
    )
    cols = [
        f.name
        for f in sc.EVENT_FIELDS
        if f.name not in sc.CORE_FIELDS and f.name not in sc.META_FIELDS
    ]
    emit(
        "| event_type | " + " | ".join(f"`{c}`" for c in cols) + " |",
        "|---|" + "---|" * len(cols),
    )
    for et in sc.EventType:
        cells = [MARK[sc.requirement(et, c)] for c in cols]
        emit(f"| `{et.value}` | " + " | ".join(cells) + " |")
    emit(
        "",
        "**`session_duration` 기록 규칙** — 세션 시작 시점에는 값을 알 수 없다.",
        "세션의 **마지막 이벤트에만** 기록한다. 이미 기록한 레코드를 나중에 갱신하지 않는다(append-only).",
        "",
        "**배정 필드** — `treatment_id`·`treatment_group`·`experiment_id`는 실험 기간 중",
        "모든 이벤트에 선택적으로 붙는다. 기록은 하되 **Feature로 사용하지 않는다**(SRS NFR-002).",
        "",
        "## 파생 상태 이벤트",
        "",
        "| 상태 | 의미 |",
        "|---|---|",
        "| `inactive` | 활동이 끊긴 상태 |",
        "| `at_risk` | 마지막 구매 후 28~41일 |",
        "| `churn` | 마지막 구매 후 42일 이상 |",
        "",
        "기록은 하되 **학습 Feature로 사용하지 않는다.** 라벨과 동어반복이 되어 AUC가",
        "비현실적으로 높아진다(PRD §80 Risk 7). 대시보드 표시와 코호트 분석 전용이다.",
        "모델 라벨은 전향적 42일 window로 따로 정의한다(`docs/data_spec.html` §5).",
        "",
        "## 식별자 형식",
        "",
        "| 필드 | 정규식 | 예 |",
        "|---|---|---|",
    )
    for name, pattern in sc.IDENTIFIER_PATTERNS.items():
        emit(f"| `{name}` | `{pattern}` | `{IDENTIFIER_EXAMPLES[name]}` |")
    emit(
        "",
        "`session_id`는 `S-{customer_id}-{세션 시작 epoch ms}` 형식이며,",
        f"무활동 {sc.SESSION_TIMEOUT_MINUTES}분이면 만료되고 다음 활동은 새 id를 받는다.",
        "",
        "## 이 계층을 통과할 수 없는 필드",
        "",
        "실제 서비스에서 알 수 없는 값이다. `validate_event()`가 거부하고",
        "`tests/test_schema.py`가 스키마 자체에 섞이지 않았는지 검사한다.",
        "",
        "```",
        "\n".join(sorted(sc.FORBIDDEN_FIELD_NAMES)),
        "```",
        "",
        "## Observable 지표 ↔ 이벤트 매핑",
        "",
        "PRD §21이 AI 입력으로 허용한 16개 지표를 이 스키마만으로 계산할 수 있어야 한다.",
        "",
        "| Observable 지표 | 계산에 쓰는 이벤트 |",
        "|---|---|",
    )
    for metric, sources in sc.OBSERVABLE_METRIC_SOURCES.items():
        emit(f"| `{metric}` | " + " · ".join(f"`{s}`" for s in sources) + " |")
    emit(
        "",
        "`cart_abandonment_count`는 `add_to_cart`가 있고 같은 세션에",
        "`purchase`가 없는 경우로 계산한다. `campaign_response_count`는",
        "`campaign_exposed` 이후 반응 관찰기간 내 `coupon_clicked` 또는 `purchase`로 계산한다.",
        "",
        "## 사용법",
        "",
        "```python",
        "from src.measurement.schema import EventType, validate_event",
        "",
        "problems = validate_event(record)   # 빈 리스트면 통과",
        "if problems:",
        "    raise ValueError(problems)",
        "```",
        "",
        "Event Sink([M-2])와 데이터 품질 검증([M-6])이 이 함수를 사용한다.",
        "",
        "## 이 문서 다시 만들기",
        "",
        "```bash",
        "python3 scripts/gen_event_schema_doc.py > docs/event_schema.md",
        "```",
    )


if __name__ == "__main__":
    main()
