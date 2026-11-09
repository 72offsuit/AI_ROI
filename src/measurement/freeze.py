"""GATE 1 부분 봉인 — Lock 기록 작성과 해시 대조 (이슈 #49).

## ★★ C1 은 GATE 1 을 **통과시키지 않는다**

완전 Lock **0종**. 측정 계층이 소유한 4종만 부분/조건부이고 5종은 다른 파트 소관이다.
`EXPERIMENT_ENVIRONMENT_v1` 을 **선언하지 않는다** — 그 선언은 GATE 1 전체 통과를
전제하고, 부분 봉인은 시간이 지나면 *"전체를 Lock 했다"* 로 읽힌다.

## #163 — 항목 상태는 서명 때 증거로 정하고, 이후에는 서명 기록이 정본이다

`record()` 가 `simulator_commit`(시뮬레이터 4종) · `ChurnThresholdEvidence`(CHURN,
data_spec §5.1)를 받아 증거가 있는 항목만 LOCKED 로 쓴다(`lock_items_at_signing`).
verify · 게시 · 테스트는 `gate1_lock_items(record)` 로 **기록의 상태**를 읽는다.
declaration 은 인자가 아니라 항목에서 유도한다 — SERVICE_v1 을 뺀 8종이 LOCKED 일
때만 FULL_FREEZE 다. 근거: `docs/decisions/DR-163-gate1-lock-evidence.md`.

## ★ 탐지 3층이 **같은 함수**를 쓴다

    1층  tests/test_freeze.py      → verify() 를 부른다. **실패한다.** 경고가 아니다
    2층  publish.py 게시 시점       → verify() 를 부른다 → freeze_status.json
    3층  대시보드 V6                → 그 게시물을 그린다

세 층이 각자 판정하면 갈린다. **`verify()` 하나가 정본이고 나머지는 그것을 표시한다.**

## ★★ 이 모듈의 유일한 실패 양식

    if not lock_file.exists():
        return  # ← 봉인하지 않은 상태가 초록으로 보인다

**Lock 기록이 없는 것은 "통과"가 아니라 `not_started` 다.** 그것을 값으로 만들어
게시물과 화면까지 나르는 것이 이 모듈의 본업이다. `verify()` 가 `missing` 과
`not_run` 을 나누는 이유도 같다 — *"대조했고 기록이 없다"* 와 *"대조하지 않았다"* 는
다른 상태다.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Mapping, Sequence

from src.measurement import schema as sc
from src.measurement.config_loader import dump_yaml, load_yaml, yaml_available
from src.measurement.errors import ConfigError, FreezeViolation

DEFAULT_LOCK_RECORD = Path("config/gate1_lock.yaml")
LOCK_RECORD_VERSION = "gate1-lock/v1"

#: PRD §22 Lock 9종. **전부 목록에 남는다** — Lock 하지 않는 것도.
#:
#: 빼면 *"이 항목은 봉인 대상이 아니다"* 와 *"봉인을 잊었다"* 가 같아진다.
#: `owner_part` 가 그 구분이다: 남의 소관을 `PENDING` 으로 적으면 우리가 안 한
#: 것처럼 보이므로 `OUT_OF_SCOPE` 를 쓴다.
LOCK_ITEMS: tuple[str, ...] = (
    "SERVICE_v1",
    "CUSTOMER_PERSONA_v1",
    "HIDDEN_TRAIT_RULE_v1",
    "BEHAVIOR_RULE_v1",
    "ECONOMIC_RULE_v1",
    "CHURN_DEFINITION_v1",
    "TREATMENT_RESPONSE_v1",
    "EVENT_SCHEMA_v1",
    "KPI_DEFINITION_v1",
)

#: commerce 소관이라 이 저장소가 봉인할 수 없는 항목. declaration 유도에서 뺀다 (#163).
DECLARATION_EXEMPT_ITEMS = frozenset({"SERVICE_v1"})

#: 시뮬레이터 Lock 5종 (#163). 서명 시 증거가 있을 때만 LOCKED 로 기록한다.
SIMULATOR_LOCK_ITEMS: tuple[str, ...] = (
    "CUSTOMER_PERSONA_v1",
    "HIDDEN_TRAIT_RULE_v1",
    "BEHAVIOR_RULE_v1",
    "TREATMENT_RESPONSE_v1",
)
CHURN_ITEM = "CHURN_DEFINITION_v1"

#: 시뮬레이터 정본 파일. 페르소나 · Hidden Trait · 행동 · 가드레일 · churn 임계값 블록이
#: 모두 여기 있다. src/simulator 코드는 해시가 아니라 기록의 simulator_commit 으로 남는다.
SIMULATOR_CANONICAL_FILE = Path("config/simulator_config.yaml")

ITEM_STATUSES = ("LOCKED", "PARTIAL", "PENDING", "BLOCKED", "OUT_OF_SCOPE")
OVERALL_STATES = ("not_started", "partial", "sealed", "violated")
VERIFICATION_STATES = ("match", "mismatch", "missing", "not_run")

RECORD_UNREADABLE = object()
"""★ Lock 기록 **파일은 있으나 이 환경에서 읽을 수 없다**는 표시.

`None`(파일이 없다)과 **다른 상태다.** 기록이 YAML 이므로 PyYAML 이 없으면 읽을 수
없고, 그것이 `isolation.yml`(의존성 0)의 정상 환경이다.

## 왜 예외를 던지지 않나 — A7 이 무너진다

`load_record()` 가 여기서 `ConfigError` 를 던지면 **`isolation.yml` 이 빨개진다.**
그 잡은 의존성을 설치하지 않으므로(ISO-005) Lock 기록이 생긴 순간부터 영구히
실패하고, 그것은 **격리 CI 가 격리와 무관한 이유로 깨지는 것** — 가정 A7 이
막으려는 바로 그 실패 양식이다.

## 그래서 값으로 만든다

`verify()` 가 이것을 받으면 **`verification: "not_run"`** 을 낸다 — *"대조하지
않았다"* 다. `missing`(대조했고 기록이 없다)과 구분되고, 조용한 통과도 아니다.
해시 대조는 `tests-with-deps.yml` 이 수행한다: **두 잡의 차이가 곧 "의존성이
필요한 검증"의 목록**이라는 원칙이 여기서도 그대로 작동한다."""


@dataclass(frozen=True, slots=True)
class LockItem:
    """Lock 9종 중 하나의 판정.

    `PARTIAL` 이면 `scope_note` 가 **필수**다 — 부분 Lock 은 범위를 문장으로
    남기지 않으면 나중에 전체 Lock 으로 읽힌다.
    """

    item: str
    status: str
    owner_part: str
    scope_note: str
    reason_code: str | None = None
    reason_detail: str | None = None
    canonical_files: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.item not in LOCK_ITEMS:
            raise ValueError(f"PRD §22 Lock 9종 밖의 항목: {self.item!r}")
        if self.status not in ITEM_STATUSES:
            raise ValueError(f"{self.item}: 알 수 없는 status {self.status!r}")
        # ★ 부분 Lock 의 범위를 비워 두면 "전체를 Lock 했다" 로 읽힌다.
        if self.status in ("PARTIAL", "LOCKED") and not self.scope_note.strip():
            raise ValueError(
                f"{self.item}: status={self.status} 인데 scope_note 가 비었다. "
                "부분 Lock 은 범위를 문장으로 남긴다 — 남기지 않으면 시간이 지나 "
                "전체를 Lock 한 것으로 읽힌다"
            )
        # 계약(freeze_status.schema.json)이 LOCKED 항목에 canonical_files 를 요구한다.
        # 무엇을 봉인했는지 해시로 가리키지 못하는 LOCKED 는 대조할 수 없다.
        if self.status == "LOCKED" and not self.canonical_files:
            raise ValueError(
                f"{self.item}: LOCKED 인데 canonical_files 가 비었다. 봉인한 정본 "
                "파일을 가리켜야 verify() 가 해시를 대조할 수 있다"
            )


@dataclass(frozen=True, slots=True)
class Precondition:
    """선행 조건 G-n 하나.

    `met` 의 세 값을 구분한다 — `None` 을 `False` 로 적지 않는다:

        True   확인했고 충족한다
        False  확인했고 충족하지 않는다
        None   ★ **확인하지 않았다.** `False` 와 구별한다
    """

    id: str
    title: str
    met: bool | None
    evidence: str = ""


@dataclass(frozen=True, slots=True)
class ChurnThresholdEvidence:
    """`docs/data_spec.html` §5.1 ①~④(churn 임계값 실측 확인)의 결과.

    `met` 은 `True`/`False` 뿐이다. *"확인하지 않았다"* 는 이 객체를 넘기지 않는
    것으로 나타낸다 — 그때 CHURN_DEFINITION_v1 은 기본 상태(PARTIAL)로 남는다.
    `evidence` 는 충족이든 미충족이든 근거 경로나 설명이며 기록에 그대로 남는다.
    """

    met: bool
    evidence: str

    def __post_init__(self) -> None:
        if not isinstance(self.met, bool):
            raise ValueError(
                f"met={self.met!r} — True/False 만 받는다. 확인하지 않았으면 "
                "증거 객체를 넘기지 않는다"
            )
        if not isinstance(self.evidence, str) or not self.evidence.strip():
            raise ValueError(
                "§5.1 확인 근거가 비었다. 근거 없는 충족은 주장이고, 근거 없는 "
                "미충족은 다음 사람이 무엇을 다시 해야 하는지 모른다"
            )


@dataclass(frozen=True, slots=True)
class FreezeVerification:
    """`verify()` 의 결과. **세 층이 이 객체를 공유한다.**"""

    overall: str
    verification: str
    lock_record: Mapping[str, object] | None
    items: tuple[LockItem, ...]
    unmet: tuple[Precondition, ...]
    mismatches: tuple[str, ...] = ()
    detail: str = ""
    lock_record_path: Path | None = None
    """Lock 기록 **파일**의 경로. 게시물 `lock_record` 요약이 이것과 그 해시를 담는다.

    계약이 기록 전체가 아니라 `path` + `sha256` + 핵심 4필드만 받는 이유가 있다:
    게시물이 기록을 **복제하면 진실이 둘**이 되고, 둘이 갈라지면 어느 쪽이 정본인지
    알 수 없다. 포인터 + 해시면 **기록이 조용히 바뀐 것도 드러난다.**"""
    file_hashes: Mapping[str, tuple[str | None, str | None]] = field(default_factory=dict)
    """정본 경로 → (기록된 해시, 현재 해시). 대조를 실행했을 때만 채운다.

    게시물의 항목별 `canonical_files[]` 가 이것을 읽는다 — 항목마다 다시 해시하면
    한 번의 판정 안에서 같은 파일의 답이 둘이 될 수 있다."""

    def __post_init__(self) -> None:
        if self.overall not in OVERALL_STATES:
            raise ValueError(f"알 수 없는 overall: {self.overall!r}")
        if self.verification not in VERIFICATION_STATES:
            raise ValueError(f"알 수 없는 verification: {self.verification!r}")
        # ★ C1 에서 도달 가능한 최대치는 partial 이다 (gate1-lock-scope.md §1).
        #   sealed 는 EXPERIMENT_ENVIRONMENT_v1 선언과 함께만 쓴다.
        if self.overall == "sealed" and not self.detail:
            raise ValueError(
                "overall=sealed 인데 근거가 없다. C1 은 GATE 1 을 통과시키지 "
                "않으므로 sealed 에 도달하려면 EXPERIMENT_ENVIRONMENT_v1 선언이 "
                "함께 있어야 한다"
            )

    @property
    def can_lock(self) -> bool:
        """선행 조건이 **전부 `True`** 인가.

        `None`(확인하지 않았다)도 막는다 — 확인하지 않은 것을 충족으로 읽으면
        *"미실행 검증을 통과로 표시"* 하는 것이다.
        """
        return not self.unmet


def file_sha256(path: Path) -> str | None:
    """정본 파일 해시. 없으면 `None` — `""` 나 `"0"` 으로 채우지 않는다."""
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.exists() else None


#: ★ GATE 1 선행 조건 G-1~G-16 과 **W5 구현 후 실측 충족 상태**.
#:
#: `met` 의 세 값을 구분한다 — 계약이 `boolean | null` 을 허용하는 이유다:
#:
#:     True   확인했고 충족한다        (근거를 evidence 에 적는다)
#:     False  확인했고 충족하지 않는다
#:     None   ★ **확인하지 않았다.** False 와 구별한다
#:
#: **`None` 을 `False` 로 적지 않는다.** 확인하지 않은 것을 미충족으로 적으면
#: 우리가 확인했다는 주장이 되고, 그것이 이 사이클이 막는 실패 양식이다.
#: PRD §22 Lock 9종 전부. ★ **C1 에서 다루지 않는 항목도 목록에 남기고 사유를
#: 적는다** — 빼면 "이 항목은 봉인 대상이 아니다"와 "봉인을 잊었다"가 같아진다.
#:
#: `owner_part` 가 중요하다: 측정 계층이 봉인할 수 있는 것은 3종뿐이고 나머지는
#: 시뮬레이터·커머스 소관이다. **남의 소관을 `PENDING` 으로 적으면 우리가 안 한
#: 것처럼 보인다** — `OUT_OF_SCOPE` 가 그 구분이다.
#:
#: ★ #163 이후 이 표는 **서명 전 기본 상태**다. 서명된 기록이 있으면 verify · 게시는
#: 기록의 상태를 쓴다(`gate1_lock_items(record)`). 서명 때 증거로 올릴 목표는
#: `_LOCK_TARGETS` 에 있다.
_LOCK_ROWS: tuple[tuple[str, str, str, str], ...] = (
    ("SERVICE_v1", "OUT_OF_SCOPE", "commerce",
     "서비스 정의는 Ecommerce_Service 소관이고 이 저장소가 봉인할 수 없다. "
     "C1 범위 밖이다"),
    ("CUSTOMER_PERSONA_v1", "OUT_OF_SCOPE", "simulator",
     "고객 페르소나는 시뮬레이터 소관이고 시뮬레이터가 미가동이다"),
    ("HIDDEN_TRAIT_RULE_v1", "OUT_OF_SCOPE", "simulator",
     "Hidden Trait 규칙은 시뮬레이터 소관이다. 측정 계층은 이 값을 통과시키지 "
     "않으므로(ISO-003) 봉인 대상으로 알 수도 없다"),
    ("BEHAVIOR_RULE_v1", "OUT_OF_SCOPE", "simulator",
     "행동 규칙은 시뮬레이터 소관이고 시뮬레이터가 미가동이다"),
    ("TREATMENT_RESPONSE_v1", "OUT_OF_SCOPE", "simulator",
     "처치 반응 규칙은 시뮬레이터 소관이고 시뮬레이터가 미가동이다"),
    ("EVENT_SCHEMA_v1", "PENDING", "measurement",
     "Lock 범위는 events 테이블에 한정된다 (결정 D-8). 나머지 6개 테이블은 "
     "미정의 상태다. 22컬럼·16타입·Nullable 매트릭스가 확정되었고 "
     "tests/test_schema.py 가 assertEqual 로 고정하나, 실제 Lock 기록은 "
     "M-09 가 수행한다"),
    ("ECONOMIC_RULE_v1", "PENDING", "measurement",
     "경제 규칙 상수 6블록과 유도 규칙 2건(D-16 discount · D-3 shipping)이 "
     "config/economic_config.yaml 에 확정되었다. 단 AI 투자 비용이 가정 기반 "
     "추정치이고(is_estimate: true) 환불 미차감 가정 A-REFUND 가 남아 있다"),
    ("CHURN_DEFINITION_v1", "PARTIAL", "measurement",
     "★ 이탈 판정 **방식**(고정 윈도우 · 운영 상태와 모델 라벨의 분리 · "
     "label_window_days=42)은 Lock 한다. **임계값 28/42/60 은 Lock 하지 "
     "않는다** — data_spec §5.1 확정 절차 ①~④가 시뮬레이터를 요구하고 C1 에 "
     "없다 (결정 D-5). 해당 지표는 unconfirmed + params_used 로 나간다"),
    ("KPI_DEFINITION_v1", "PARTIAL", "measurement",
     "★ **계산 계약**(이름·계산식·모집단·기간·분모)은 GATE 1 에서 Lock 하고 "
     "**역할 배정**(Primary/Guardrail/Secondary)은 GATE 2 다 (결정 D-4). "
     "그래서 metrics[].role 이 전부 none 이다 — 배정하지 않은 것이지 "
     "빠뜨린 것이 아니다"),
)

_SIMULATOR_PROVENANCE_NOTE = (
    "정본은 config/simulator_config.yaml 해시와 기록의 simulator_commit"
    "(src/simulator 코드)이다. verify() 는 config 해시만 대조하고 simulator_commit "
    "은 대조하지 않는다(#163 후속)"
)

#: ★ 서명 시 증거가 있으면 LOCKED 로 기록할 **목표** (#163). item → (owner_part, scope_note).
#:
#: 정본 파일은 다섯 항목 모두 `SIMULATOR_CANONICAL_FILE` 이다. CHURN 의 임계값도
#: 그 파일의 `churn` 블록에 있다(DR-183). 판정 방식 자체는 측정 정본 4종이 덮는다.
_LOCK_TARGETS: Mapping[str, tuple[str, str]] = {
    "CUSTOMER_PERSONA_v1": (
        "simulator",
        "페르소나 정의(종류 · 구성비 · 가입일 범위)를 Lock 한다. "
        + _SIMULATOR_PROVENANCE_NOTE,
    ),
    "HIDDEN_TRAIT_RULE_v1": (
        "simulator",
        "Hidden Trait 생성 규칙을 Lock 한다. 측정 계층은 이 값을 "
        "통과시키지 않으므로(ISO-003) 내용이 아니라 해시만 안다. "
        + _SIMULATOR_PROVENANCE_NOTE,
    ),
    "BEHAVIOR_RULE_v1": (
        "simulator",
        "행동 규칙과 상품 카탈로그 생성 규칙을 Lock 한다. " + _SIMULATOR_PROVENANCE_NOTE,
    ),
    "TREATMENT_RESPONSE_v1": (
        "simulator",
        "처치 반응 규칙과 처치 강도 가드레일을 Lock 한다. Treatment 비용은 "
        "ECONOMIC_RULE_v1 이고 여기 들지 않는다. " + _SIMULATOR_PROVENANCE_NOTE,
    ),
    CHURN_ITEM: (
        "measurement",
        "이탈 판정 방식(고정 윈도우 · 운영 상태와 모델 라벨의 분리 · "
        "label_window_days=42)과 config/simulator_config.yaml churn 블록의 임계값을 "
        "Lock 한다. 임계값은 data_spec §5.1 ①~④ 실측으로 확정했고 근거는 기록의 "
        "churn_threshold_evidence 에 있다. 정본 해시는 config/simulator_config.yaml "
        "이고, 실측을 만든 시뮬레이터는 simulator_commit 이다",
    ),
}
assert set(_LOCK_TARGETS) == {*SIMULATOR_LOCK_ITEMS, CHURN_ITEM}
assert all(
    _LOCK_TARGETS[item][0] == owner
    for item, _status, owner, _note in _LOCK_ROWS if item in _LOCK_TARGETS
), "LOCKED 로 올려도 소관은 바뀌지 않는다 — 기본 상태와 목표의 owner_part 가 같아야 한다"


_GATE1_ROWS: tuple[tuple[str, str, bool | None, str], ...] = (
    ("G-1", "category 허용값 5종이 Enum 으로 정의되고 validate_event() 가 검사한다",
     True, "schema.Category 5종 · tests/test_schema.py "
           "test_unknown_category_is_rejected (M-02)"),
    ("G-2", "page_type 허용값 8종 동일",
     True, "schema.PageType 8종 · test_unknown_page_type_is_rejected (M-02)"),
    ("G-3", "validate_event() 가 check_identifier() 를 호출한다",
     True, "schema.validate_event 내 호출 · test_malformed_identifier_is_reported "
           "(M-02). 호출부가 0건이었던 것이 D2-1 이다"),
    ("G-4", "카테고리 어휘 정본이 확정된다 (영문/한글)",
     True, "영문 코드 확정 (SRS COM-001). data_spec §6.1 한글은 표기이며 표시명 "
           "매핑은 UI 책임 — schema.Category 독트링과 docs/event_schema.md (M-02)"),
    ("G-5", "타임존 정책이 확정되고 강제된다",
     True, "정책 ⑵+b — 오프셋 있는 어떤 표기든 받아 저장 시 KST 로 정규화, "
           "오프셋 없으면 거부. schema.TIMEZONE 독트링 · "
           "tests/test_sink.py TestTimezonePolicy (M-01)"),
    ("G-6", "동일 root 재기록 시 기존 파티션이 보존된다",
     True, "sink._next_part_index 가 디렉터리 최대 번호+1 을 쓴다 · "
           "TestRewriteSameRoot 3건 (M-01)"),
    ("G-7", "strict=False 가 무효 레코드에 예외를 던지지 않는다",
     True, "sink._is_observable 로 event_type 유효성을 갈랐다 · "
           "TestTolerantModeSurvival 4건 (M-01)"),
    ("G-8", "파생 상태 기록 경로가 결정된다 (기록하되 Feature 금지)",
     True, "리드 판정 ④ 게시 시점 계산. kpi.derived_state_count 3종이 "
           "derived:true + derivation(Feature 금지 문구 포함) 으로 나간다. "
           "OBSERVABLE_METRIC_SOURCES 에 넣지 않았고 "
           "test_no_observable_depends_on_derived_state 가 그대로 통과한다"),
    ("G-9", "shipping_subsidy 처리 방침이 결정된다 (규칙 유도 / 필드 추가)",
     True, "결정 D-3 ⑴ 규칙 유도. config assumptions."
           "shipping_subsidy_derived_from_rule · economics.shipping_subsidy 가 "
           "derived:true 로 낸다 (M-03)"),
    ("G-10", "환불/취소 이벤트 포함 여부가 결정된다",
     True, "★★ **확인함 · 미반영을 가정으로 수용** — 결정 D-2 (사용자, 2026-09-11). "
           "이 `true` 는 **'환불이 반영됐다'가 아니다.** '환불 미반영이라는 사실을 "
           "확인하고 가정 A-REFUND 로 받아들였다' 는 뜻이다. "
           "환불·취소 이벤트를 추가하지 않는다 — DATA-003 22컬럼과 event_type "
           "16종을 그대로 두며 둘 다 Plan/ SRS 개정을 요구해 권한 밖이다. "
           "★ 오차 방향: revenue = Σ order_amount 이므로 환불된 매출을 빼지 못해 "
           "**contribution_profit 이 위로 치우친다(과대평가)**. "
           "실험 판정에는 영향이 없다 — MEA-002 가 실험 결과 산출에 시뮬레이터 "
           "생성분만 쓰라고 규정하고 그쪽은 환불을 생성하지 않는다. "
           "근거: config assumptions.refund_adjusted=false (확정값) · "
           "게시물 notices REFUND_NOT_ADJUSTED (항상 표시) · "
           "gate1_lock.yaml assumptions"),
    ("G-11", "KPI 계산 계약이 확정된다 (이름 ↔ 계산식·모집단·기간·분모)",
     True, "kpi.py 의 함수별 시그니처(index_date 기본값 없음)와 "
           "_KPI_META 의 population·window·denominator_definition · "
           "METRIC_SPECS 46종 분류 · tests/test_kpi_layers.py 40건 (M-04)"),
    ("G-12", "경제 규칙이 확정된다 (원가·Treatment 비용·기여이익식·AI 투자비)",
     True, "config/economic_config.yaml 6블록 · tests/test_config_loader.py 가 "
           "가중 기여마진율 26.0% 와 pool 240 을 검산한다 (M-03). 단 AI 투자비는 "
           "is_estimate:true 이고 산출식과 문서 어림값이 15만원 어긋난다"),
    ("G-13", "docs/event_schema.md 가 재생성되어 코드와 일치한다",
     True, "python3 scripts/gen_event_schema_doc.py | diff - docs/event_schema.md "
           "→ 차이 0 (실행 확인)"),
    ("G-14", "python3 -m unittest discover -s tests 전건 통과",
     True, "기준선 46건에서 회귀 0. 의존성 없이·설치 후 양쪽 OK (실행 확인)"),
    ("G-15", "Lock 시점의 커밋 SHA 와 config 해시를 기록할 절차가 있다",
     True, "freeze.build_record() 가 repo_commit · canonical_files 의 SHA-256 · "
           "KST locked_at · locked_by(사람 이름 강제) 를 담고, freeze.record() 가 "
           "선행 조건 미충족 시 FreezeViolation 으로 거부한다. freeze.verify() 가 "
           "해시를 재대조한다 — 탐지 3층이 이 함수 하나를 쓴다. "
           "tests/test_freeze.py · docs/gate1_checklist.md (M-09)"),
    ("G-16", "discount 처리 방침이 결정된다 (규칙 유도 / 필드 추가)",
     True, "결정 D-16 · 리드 판정 — 차단되는 것은 필드의 부재가 아니라 결정의 "
           "부재다. 유도 규칙을 config assumptions 에 조항으로 넣고 "
           "economics.coupon_cost 가 derived:true + derivation 으로 낸다 (M-03)"),
)
# ── build_freeze_status() 는 여기 있었다 (이슈 #60 · 리뷰 minor)
#
# M-09 이전 판본이었고 `publish.py` 가 `freeze.verify()` 를 부르는 판본으로
# 대체했다. 남은 사본은 아무도 부르지 않았고, 불렀다면 `_FREEZE_ITEMS` ·
# `_GATE1_PRECONDITIONS` 두 미정의 이름으로 `NameError` 를 냈을 것이다.
#
# ★ 삭제한 이유가 "안 쓰니까" 가 아니다 — **탐지 3층(테스트·게시·화면)이
#   같은 함수를 쓴다는 것이 AC-4** 인데, 같은 이름의 두 번째 구현이 남아
#   있으면 누군가 그것을 불러 판정이 갈릴 수 있다. 봉인 상태는 `publish.py`
#   의 판본 하나가 만든다.

GATE1_PRECONDITIONS: tuple[Precondition, ...] = tuple(
    Precondition(gate_id, title, met, evidence)
    for gate_id, title, met, evidence in _GATE1_ROWS
)
"""★ **선행 조건 G-1~G-16 의 정본.** 탐지 3층이 이 하나를 쓴다.

`publish.py` 나 테스트가 자기 사본을 들면 판정이 갈린다 — `AC-4` 가 *"세 층이 같은
함수를 쓴다"* 를 요구하는 이유다."""

assert len(GATE1_PRECONDITIONS) == 16, (
    f"선행 조건이 16종이 아니다 (현재 {len(GATE1_PRECONDITIONS)}). "
    "gate1-freeze-procedure.md §3 이 G-1~G-16 을 규정한다"
)
assert len({item.id for item in GATE1_PRECONDITIONS}) == 16, "G-n 이 중복이다"


def _lock_item(
    item: str, status: str, owner: str, note: str,
    canonical_files: tuple[str, ...] = (),
) -> LockItem:
    """사유 필드를 상태 · 소관에서 유도한다. 기본값과 서명 기록이 같은 규칙을 쓴다."""
    return LockItem(
        item=item, status=status, owner_part=owner, scope_note=note,
        reason_code=(
            sc.ReasonCode.NOT_RUN.value if status == "PENDING"
            else sc.ReasonCode.PRECONDITION_MISSING.value
            if status == "OUT_OF_SCOPE" else None
        ),
        # LOCKED 에 "봉인할 수 없다" 류의 미봉인 사유를 붙이면 상태와 사유가 모순된다.
        reason_detail=(
            None if status == "LOCKED"
            else "C1 은 GATE 1 을 통과시키지 않고 부분 봉인만 한다. 실제 Lock 기록은 "
            "freeze.record() 가 쓴다"
            if owner == "measurement"
            else "이 저장소의 측정 계층이 봉인할 수 없는 항목이다"
        ),
        canonical_files=canonical_files,
    )


def _recorded_items(lock_record: Mapping[str, object]) -> tuple[LockItem, ...]:
    """서명 기록의 `items` 를 읽는다. 구조가 깨졌으면 `ConfigError` — 기본값으로 떨어지지 않는다.

    기본값으로 떨어지면 손으로 고쳐 깨진 기록이 *"서명 전 상태"* 로 보이고, 그것은
    `FREEZE-003` 이 막는 변조를 조용히 덮는 것이다.
    """
    entries = lock_record.get("items")
    if not isinstance(entries, Sequence) or isinstance(entries, (str, bytes)):
        raise ConfigError(
            "gate1_lock.yaml 의 items 가 목록이 아니다 — freeze.record() 로 다시 "
            "서명한다. 손으로 고치지 않는다"
        )
    items: list[LockItem] = []
    for index, entry in enumerate(entries):
        try:
            if not isinstance(entry, Mapping):
                raise TypeError("항목이 매핑이 아니다")
            files = entry.get("canonical_files") or ()
            if isinstance(files, (str, bytes)) or not isinstance(files, Sequence):
                raise TypeError("canonical_files 가 경로 목록이 아니다")
            items.append(_lock_item(
                str(entry["item"]), str(entry["status"]), str(entry["owner_part"]),
                str(entry["scope_note"]), tuple(str(path) for path in files),
            ))
        except (KeyError, TypeError, ValueError) as error:
            raise ConfigError(
                f"gate1_lock.yaml items[{index}] 를 읽을 수 없다: {error}. "
                "freeze.record() 로 다시 서명한다. 손으로 고치지 않는다"
            ) from error
    names = sorted(item.item for item in items)
    if names != sorted(LOCK_ITEMS):
        raise ConfigError(
            f"gate1_lock.yaml items 가 Lock 9종을 정확히 한 번씩 담지 않는다: {names}. "
            "빠지거나 겹친 기록은 무엇을 봉인했는지 말하지 못한다"
        )
    return tuple(items)


def gate1_lock_items(lock_record: object = None) -> tuple[LockItem, ...]:
    """PRD §22 Lock 9종의 판정. **9종 전부** 돌려준다. ★ verify · 게시 · 테스트가 이것 하나를 쓴다.

    - 읽을 수 있는 서명 기록을 넘기면 **그 기록의 상태**다. 서명 뒤에 코드
      기본값이 바뀌어도 게시물은 서명된 내용을 보여 준다.
    - `None`(기록 없음) · `RECORD_UNREADABLE`(PyYAML 없음)이면 코드의 서명 전 기본
      상태(`_LOCK_ROWS`)다. 후자는 기록 내용을 모르므로 이 값이 기록과 다를 수
      있다 — `verify()` 가 같은 경우를 `verification: not_run` 으로 표시한다.

    `LockItem.__post_init__` 이 `PARTIAL`·`LOCKED` 에 `scope_note` 를, `LOCKED` 에
    `canonical_files` 를 강제하므로 그런 항목은 **만들 수조차 없다.**

    기록은 쓰기 경로와 같은 규칙으로 다시 검사한다(`_check_recorded_invariants`).
    증거 없는 LOCKED · 항목과 어긋난 선언은 `ConfigError` 다.
    """
    if lock_record is not None and lock_record is not RECORD_UNREADABLE:
        if not isinstance(lock_record, Mapping):
            raise ConfigError("gate1_lock.yaml 이 매핑이 아니다")
        items = _recorded_items(lock_record)
        _check_recorded_invariants(lock_record, items)
        return items
    items = tuple(_lock_item(*row) for row in _LOCK_ROWS)
    assert {i.item for i in items} == set(LOCK_ITEMS), (
        "Lock 9종 중 빠진 항목이 있다 — 빼면 '봉인 대상이 아니다'와 '봉인을 "
        "잊었다'가 같아진다"
    )
    return items



def recorded_signing_evidence(
    lock_record: Mapping[str, object],
) -> tuple[str | None, ChurnThresholdEvidence | None]:
    """서명 기록에 적힌 증거를 `record()` 인자 형태로 돌려준다.

    같은 증거로 `lock_items_at_signing()` 을 다시 계산하면 기록의 항목이 나와야 한다 —
    검사와 테스트가 이 왕복을 쓴다. 형식이 틀리면 `ConfigError` 다.
    """
    simulator_commit = lock_record.get("simulator_commit")
    if simulator_commit is not None and not isinstance(simulator_commit, str):
        raise ConfigError(
            f"gate1_lock.yaml simulator_commit={simulator_commit!r} 가 문자열이 아니다. "
            "freeze.record() 로 다시 서명한다. 손으로 고치지 않는다"
        )
    try:
        _check_simulator_commit(simulator_commit)
    except FreezeViolation as error:
        raise ConfigError(f"gate1_lock.yaml — {error}") from error

    raw = lock_record.get("churn_threshold_evidence")
    if raw is None:
        return simulator_commit, None
    if not isinstance(raw, Mapping) or "met" not in raw or "evidence" not in raw:
        raise ConfigError(
            "gate1_lock.yaml churn_threshold_evidence 가 {met, evidence} 매핑이 아니다. "
            "freeze.record() 로 다시 서명한다. 손으로 고치지 않는다"
        )
    try:
        churn_evidence = ChurnThresholdEvidence(met=raw["met"], evidence=raw["evidence"])  # type: ignore[arg-type]
    except ValueError as error:
        raise ConfigError(f"gate1_lock.yaml churn_threshold_evidence — {error}") from error
    return simulator_commit, churn_evidence


def _check_recorded_invariants(
    lock_record: Mapping[str, object], items: Sequence[LockItem],
) -> None:
    """기록을 쓸 때의 불변식을 읽을 때 다시 본다. 같은 함수를 써야 두 경로가 갈리지 않는다.

    손으로 고친 기록을 막는 것이 목적이다 — 구조만 보면 증거 없는 LOCKED 가 게시되고,
    선언과 항목이 어긋난 기록에서 verify() 가 sealed 를 낸다. 9종 · 선언 · 증거를
    모두 일관되게 위조한 기록은 여기서 잡지 못한다. 게시물의 기록 파일 sha256 이 남는다.
    """
    simulator_commit, churn_evidence = recorded_signing_evidence(lock_record)
    try:
        _check_lock_evidence(items, simulator_commit, churn_evidence)
    except FreezeViolation as error:
        raise ConfigError(
            f"gate1_lock.yaml — {error}. freeze.record() 로 다시 서명한다"
        ) from error
    full = _all_lockable_locked(items)
    declaration = lock_record.get("declaration")
    declared = lock_record.get("experiment_environment_v1_declared")
    # `is` 로 비교한다 — 0 · 1 이 False · True 와 같다고 통과하지 않게.
    if declaration != ("FULL_FREEZE" if full else "PARTIAL_FREEZE") or declared is not full:
        raise ConfigError(
            f"gate1_lock.yaml 선언(declaration={declaration!r}, "
            f"experiment_environment_v1_declared={declared!r})이 항목에서 유도한 값"
            f"({'FULL_FREEZE' if full else 'PARTIAL_FREEZE'}, {full})과 다르다. "
            "선언은 항목에서만 유도한다 — freeze.record() 로 다시 서명한다"
        )


_SIMULATOR_COMMIT = re.compile(r"^[0-9a-f]{40}$")


def _check_simulator_commit(simulator_commit: str | None) -> None:
    """40자 소문자 git sha 만 받는다. 자리 표시값은 *"확인했고 이 값이다"* 가 되어 거부한다."""
    if simulator_commit is not None and not _SIMULATOR_COMMIT.match(simulator_commit):
        raise FreezeViolation(
            f"simulator_commit={simulator_commit!r} 는 40자 git sha 가 아니다. "
            "`git log -1 --format=%H -- src/simulator` 값을 넘긴다. 모르면 넘기지 "
            "않는다 — 그러면 시뮬레이터 항목은 LOCKED 로 기록되지 않는다"
        )


def _all_lockable_locked(items: Sequence[LockItem]) -> bool:
    """commerce 소관(SERVICE_v1)을 뺀 8종이 전부 LOCKED 인가. declaration 과 overall 이 공유한다."""
    locked = {item.item for item in items if item.status == "LOCKED"}
    # 빈 목록에서 all() 이 참이 되는 것을 막으려고 항목 이름으로 센다.
    return locked >= set(LOCK_ITEMS) - DECLARATION_EXEMPT_ITEMS


def lock_items_at_signing(
    *,
    simulator_commit: str | None = None,
    churn_evidence: ChurnThresholdEvidence | None = None,
) -> tuple[LockItem, ...]:
    """서명 시점에 기록할 9종. **코드 기본값에서 출발해 증거가 있는 항목만** LOCKED 로 올린다.

    | 증거 | 결과 |
    |---|---|
    | 없음 | 기본값 그대로 (시뮬레이터 4종 OUT_OF_SCOPE · CHURN PARTIAL) |
    | `simulator_commit` | 시뮬레이터 4종 LOCKED |
    | + `churn_evidence.met is True` | CHURN 도 LOCKED |
    | `churn_evidence.met is False` | CHURN 은 PARTIAL 로 남는다 (근거는 기록에 남는다) |

    이전 서명 기록의 상태는 이어받지 않는다 — 이번 서명의 증거로만 정한다.

    Raises:
        FreezeViolation: `simulator_commit` 이 40자 sha 가 아니거나, §5.1 충족 증거를
            `simulator_commit` 없이 넘겼다. 쓸 수 없는 증거를 조용히 무시하면
            서명자는 LOCKED 를 기대한 채 PARTIAL 기록을 커밋한다.
    """
    _check_simulator_commit(simulator_commit)
    churn_met = churn_evidence is not None and churn_evidence.met
    if churn_met and simulator_commit is None:
        raise FreezeViolation(
            "§5.1 충족 증거를 받았지만 simulator_commit 이 없다. ④(재생성 이탈률)는 "
            "특정 시뮬레이터의 실행 결과이므로 그 커밋이 없으면 증거가 재현되지 "
            "않는다. simulator_commit 을 함께 넘긴다"
        )
    promoted = set(SIMULATOR_LOCK_ITEMS) if simulator_commit is not None else set()
    if churn_met:
        promoted.add(CHURN_ITEM)
    return tuple(
        _lock_item(
            item.item, "LOCKED", *_LOCK_TARGETS[item.item],
            (SIMULATOR_CANONICAL_FILE.as_posix(),),
        )
        if item.item in promoted else item
        for item in gate1_lock_items()
    )


#: The assumptions a GATE 1 seal stands on. **A record without these reads as
#: "everything was verified"**, which the seal does not claim.
#:
#: ★ Why these live in code. They used to exist only inside the written record,
#:   handed to `record()` by whoever ran it. `docs/gate1_checklist.md` §5.2 showed
#:   the call *without* an `assumptions=` argument, so re-recording the seal --
#:   which issue #63 required -- would have silently produced `assumptions: []`.
#:   Nothing compared the two, so nothing would have said so. A record whose
#:   content must be retyped from the previous record is not reproducible; this
#:   makes it derivable instead, and `tests/test_freeze.py` compares what is
#:   written against what is here.
_GATE1_ASSUMPTIONS: tuple[Mapping[str, object], ...] = (
    {
        "id": "A-REFUND",
        "decision": "D-2 (사용자, 2026-09-11)",
        "assumed": (
            "환불·취소 이벤트를 추가하지 않는다. revenue = Σ order_amount 이며 "
            "총매출을 순매출로 간주한다"
        ),
        "confirmed_not_implemented": True,
        "error_direction": (
            "contribution_profit 이 위로 치우친다 (과대평가). 환불된 매출을 "
            "순매출에서 뺄 수 없기 때문이다. 아래로가 아니다"
        ),
        "why_no_verdict_impact": (
            "MEA-002 가 실험 결과 산출에 시뮬레이터 생성분만 쓰도록 규정하고, "
            "시뮬레이터는 환불을 생성하지 않는다"
        ),
        "why_not_added": (
            "DATA-003 22컬럼과 event_type 16종이 tests/test_schema.py 의 "
            "assertEqual 로 고정돼 있고, 변경은 Plan/ SRS 개정을 요구해 이 팀의 "
            "권한 밖이다"
        ),
        "carried_in": [
            "config/economic_config.yaml assumptions.refund_adjusted",
            "results/measurement/kpi_report.json notices REFUND_NOT_ADJUSTED",
        ],
    },
    {
        "id": "A-DISCOUNT",
        "decision": "D-16 (리드 판정)",
        "assumed": (
            "discount 필드가 이벤트 스키마에 없다. 커머스 교환 파일에 실제 할인액이 "
            "있는 주문은 그 값을 쓰고, 없는 주문만 treatment_cost 에서 유도한다. "
            "쿠폰을 썼는데 둘 다 없으면 coupon_cost 는 계산 불가다 (#108)"
        ),
        "error_direction": (
            "유도분만 오차가 있다 — 처치 단가(T2 3,000 · T3 7,000)와 실제 할인의 차이라 "
            "주문마다 방향이 다르다. 관측분은 오차가 없다"
        ),
        "why_no_verdict_impact": (
            "실험 판정은 시뮬레이터 생성분만 쓰고(MEA-002) 시뮬레이터가 처치를 "
            "배정하므로 유도가 정의상 정확하다. 유도값에는 derived:true + derivation "
            "이 붙어 저장된 사실과 구분된다"
        ),
        "carried_in": [
            "config assumptions.discount_derived_from_treatment",
            "docs/decisions/DR-108-coupon-cost-basis.md",
        ],
    },
    {
        "id": "A-SHIPPING",
        "decision": "D-3 (사용자 추천 ⑴)",
        "assumed": (
            "배송비 필드가 이벤트 스키마에 없다. 커머스 교환 파일이 있는 주문은 "
            "shipping_fee − shipping_charged 관측값을 쓰고, 없는 주문만 무료배송 "
            "기준과 T1 처치에서 유도한다 (#100)"
        ),
        "error_direction": (
            "교환 파일이 없는 커머스 주문은 처치 ID 가 없어 배송보조가 계상되지 "
            "않는다 (과소). 교환 파일이 있으면 해소된다"
        ),
        "carried_in": [
            "config assumptions.shipping_subsidy_derived_from_rule",
            "docs/contracts/commerce-exchange/v1/README.md §5",
        ],
    },
    {
        "id": "A-AI-INVESTMENT",
        "decision": "미결 — 값에 외부 출처가 없다",
        "assumed": (
            "인건비 400만원/월 · 상각 12개월 · 컴퓨트 단가가 가정 기반 추정치다"
        ),
        "error_direction": (
            "방향 불명 — 실제 집행 내역이 없어 어느 쪽인지 알 수 없다"
        ),
        "carried_in": [
            "config ai_investment.is_estimate=true",
            "게시물 notices AI_INVESTMENT_IS_ESTIMATE",
        ],
    },
)


def gate1_assumptions() -> tuple[Mapping[str, object], ...]:
    """The assumptions to hand `record()`. Pass this, never a retyped literal.

    Each entry carries `error_direction` on purpose: an assumption without a
    direction tells the next reader that something is uncertain but not which way
    it is wrong, and that is the half that changes a decision.
    """
    return _GATE1_ASSUMPTIONS


assert len({a["id"] for a in _GATE1_ASSUMPTIONS}) == len(_GATE1_ASSUMPTIONS), (
    "가정 id 가 중복이다"
)
assert all(str(a.get("error_direction", "")).strip() for a in _GATE1_ASSUMPTIONS), (
    "오차 방향이 빈 가정이 있다 — 방향 없는 가정은 읽는 사람이 쓸 수 없다"
)


# ── 판정 — 세 층이 공유하는 유일한 자리 ─────────────────────────────────────

def verify(
    *,
    preconditions: Sequence[Precondition],
    items: Sequence[LockItem],
    lock_record: Mapping[str, object] | None = None,
    repo_root: Path = Path("."),
    lock_record_path: Path = DEFAULT_LOCK_RECORD,
) -> FreezeVerification:
    """봉인 상태를 판정한다. **기록이 없으면 `not_started` 이고 통과가 아니다.**

    | `verification` | 뜻 |
    |---|---|
    | `match` | 대조했고 정본 파일 해시가 기록과 같다 |
    | `mismatch` | ★ 대조했고 **다르다** — 봉인 이후 변경됐다 (`FREEZE-003`) |
    | `missing` | 대조했고 **Lock 기록이 없다** |
    | `not_run` | ★ **대조하지 않았다.** `missing` 과 다르다 |

    `missing` 과 `not_run` 을 나누는 이유: *"기록이 없음을 확인했다"* 와 *"확인하지
    않았다"* 는 다른 상태다. 후자를 전자로 적으면 확인했다는 주장이 된다.
    """
    unmet = tuple(item for item in preconditions if item.met is not True)

    if lock_record is None:
        return FreezeVerification(
            overall="not_started",
            verification="missing",
            lock_record=None,
            items=tuple(items),
            unmet=unmet,
            lock_record_path=None,
            detail=(
                "Lock 기록(config/gate1_lock.yaml)이 없다. 봉인을 시작하지 않은 "
                f"상태이며 통과가 아니다. 선행 조건 {len(preconditions)}종 중 "
                f"{len(unmet)}종이 미충족이다"
                if unmet else
                "Lock 기록이 없다. 선행 조건은 전부 충족했으므로 "
                "`freeze.record()` 를 실행할 수 있다"
            ),
        )

    if lock_record is RECORD_UNREADABLE:
        # ★ 기록 파일은 있으나 읽을 수 없다. 두 축을 나눠 정직하게 낸다:
        #
        #   overall: "partial"        완전 봉인이 아니다 — C1 에서 항상 참이다
        #   verification: "not_run"   ★ **대조하지 않았다.** 통과가 아니다
        #
        # `overall` 에 `not_started` 를 쓰지 않는 이유: 기록 파일이 실재하므로
        # "봉인을 시작하지 않았다" 는 거짓이다. `verification` 이 별도 축인
        # 이유가 이것이고, 화면은 둘을 함께 읽는다.
        return FreezeVerification(
            overall="partial",
            verification="not_run",
            lock_record=None,
            items=tuple(items),
            unmet=unmet,
            lock_record_path=lock_record_path,
            detail=(
                f"Lock 기록({DEFAULT_LOCK_RECORD})은 있으나 PyYAML 이 없어 이 "
                "환경에서 해시를 대조하지 못했다 — 통과가 아니라 미실행이다. "
                "격리 CI 는 의존성을 설치하지 않으므로(ISO-005) 이것이 그 잡의 "
                "정상 상태다. 대조는 tests-with-deps.yml 이 수행한다: "
                "`pip install -r requirements.txt` 후 "
                "`python3 -m unittest tests.test_freeze`"
            ),
        )

    # 기록이 있으면 정본 파일 해시를 대조한다.
    mismatches: list[str] = []
    recorded = lock_record.get("canonical_files") or {}
    if not isinstance(recorded, Mapping):
        raise ConfigError(
            "gate1_lock.yaml 의 canonical_files 가 매핑이 아니다 — "
            "`경로: sha256` 형태여야 한다"
        )
    file_hashes: dict[str, tuple[str | None, str | None]] = {}
    for relative, expected in recorded.items():
        actual = file_sha256(repo_root / str(relative))
        file_hashes[str(relative)] = (None if expected is None else str(expected), actual)
        if actual != expected:
            mismatches.append(
                f"{relative}: 기록 {str(expected)[:12]}… ≠ 현재 "
                f"{(actual or '(파일 없음)')[:12]}…"
            )
    # LOCKED 항목이 가리키는 정본의 해시가 기록에 없으면 대조할 기준이 없다.
    # 일치로 적으면 봉인하지 않은 파일이 봉인된 것으로 보인다.
    for item in items:
        if item.status != "LOCKED":
            continue
        for relative in item.canonical_files:
            if relative not in file_hashes:
                file_hashes[relative] = (None, file_sha256(repo_root / relative))
                mismatches.append(
                    f"{relative}: LOCKED 항목 {item.item} 의 정본인데 기록에 해시가 없다"
                )

    if mismatches:
        return FreezeVerification(
            overall="violated",
            verification="mismatch",
            lock_record=lock_record,
            items=tuple(items),
            unmet=unmet,
            lock_record_path=lock_record_path,
            mismatches=tuple(mismatches),
            file_hashes=file_hashes,
            detail=(
                f"봉인된 정본 파일 {len(mismatches)}건이 봉인 이후 변경됐다. "
                "FREEZE-003 — Baseline 부터 전 전략을 재실행해야 한다"
            ),
        )

    locked = sum(1 for item in items if item.status == "LOCKED")
    return FreezeVerification(
        # build_record() 의 FULL_FREEZE 유도와 같은 규칙이다. 갈리면 기록은 FULL 인데
        # 화면은 partial 이 된다.
        overall="sealed" if _all_lockable_locked(items) else "partial",
        verification="match",
        lock_record=lock_record,
        items=tuple(items),
        unmet=unmet,
        lock_record_path=lock_record_path,
        file_hashes=file_hashes,
        detail=(
            f"정본 파일 {len(recorded)}건이 기록과 일치한다. "
            f"{locked}/{len(LOCK_ITEMS)} 종이 LOCKED 다"
        ),
    )


def _lock_record_summary(
    verification: FreezeVerification,
) -> dict[str, object] | None:
    """계약 `freeze_status.lock_record` — **기록 전체가 아니라 요약이다.**

    `path` + `sha256`(기록 파일 자체의 해시) + 핵심 4필드만 담는다.

    ★ 1차 구현이 `gate1_lock.yaml` 전체를 그대로 넣어 계약이 3건으로 거부했다
    (`additionalProperties: false`). 계약이 요약만 받는 이유:

      · 게시물이 기록을 **복제하면 진실이 둘**이 되고 갈라지면 정본을 알 수 없다
      · 포인터 + 해시면 **기록이 조용히 바뀐 것도 드러난다**

    읽을 수 없는 경우(`not_run`)에도 `None` 이다 — 내용을 모르므로 요약할 수
    없다. `verification` 축이 그 사실을 따로 말한다.
    """
    record = verification.lock_record
    if record is None or verification.lock_record_path is None:
        return None
    digest = file_sha256(verification.lock_record_path)
    if digest is None:
        return None
    return {
        "path": verification.lock_record_path.as_posix(),
        "sha256": digest,
        "locked_at": record["locked_at"],
        "locked_by": record["locked_by"],
        "repo_commit": record.get("repo_commit"),
        # ★ null 이 정직한 값이다. 0 이나 빈 문자열로 채우지 않는다 (ISO-006).
        "simulator_commit": record.get("simulator_commit"),
    }


def _canonical_file_entry(
    verification: FreezeVerification, path: str,
) -> dict[str, object]:
    """계약 `items[].canonical_files[]` 한 칸. 대조하지 않았으면 해시를 싣지 않고 그 사실만 싣는다."""
    hashes = verification.file_hashes.get(path)
    if hashes is None:
        # 대조하지 않았거나(not_run) 기록에 이 경로의 해시가 없다(missing).
        # 전체 판정이 match 여도 이 파일은 대조되지 않았으므로 match 로 적지 않는다.
        state = "not_run" if verification.verification == "not_run" else "missing"
        return {"path": path, "verification": state}
    locked, current = hashes
    return {
        "path": path,
        "locked_sha256": locked,
        "current_sha256": current,
        "verification": "match" if locked is not None and locked == current else "mismatch",
    }


def to_artifact(verification: FreezeVerification) -> dict[str, object]:
    """`results/measurement/freeze_status.json` 본문 (봉투는 `contracts.envelope`).

    ★ **불일치일 때도 게시를 막지 않는다.** 막으면 *"무엇이 불일치했는지"* 를
    화면이 알 수 없다 — 실패 사실을 담은 게시물이 게시되지 않는 게시물보다 낫다.
    대신 `notices` 에 `level: "failure"` 로 싣는다 (호출자가 붙인다).
    """
    return {
        "gate": "GATE_1",
        "overall": verification.overall,
        # ★ 이 두 필드가 없어서 봉인 변조 경보가 작동한 적이 없었다 (이슈 #60).
        #   `verify()` 는 처음부터 대조 결과를 들고 있었는데 게시물로 나가지 않아
        #   `build_index` 가 `freeze_mismatch` 를 셀 방법이 없었다. 판정이 만들어진
        #   자리와 판정을 읽는 자리 사이의 배선이 끊겨 있었다.
        #
        #   `verification` 은 네 값이고 그중 둘이 "세 번째 값" 이다 —
        #   `match`/`mismatch` 외에 `missing`(기록이 없다) · `not_run`(대조하지
        #   않았다). 대조하지 않은 것을 일치로 적지 않는다.
        "verification": verification.verification,
        "mismatches": list(verification.mismatches),
        "lock_record": _lock_record_summary(verification),
        "items": [
            {
                "item": item.item,
                "status": item.status,
                "owner_part": item.owner_part,
                "scope_note": item.scope_note,
                **({"reason_code": item.reason_code} if item.reason_code else {}),
                **({"reason_detail": item.reason_detail} if item.reason_detail else {}),
                **({"canonical_files": [
                    _canonical_file_entry(verification, path)
                    for path in item.canonical_files
                ]} if item.canonical_files else {}),
            }
            for item in verification.items
        ],
        "unlocked_items": [
            {
                "id": item.id, "title": item.title, "met": item.met,
                **({"evidence": item.evidence} if item.evidence else {}),
            }
            for item in verification.unmet
        ],
    }


# ── 기록 작성 (G-15) ────────────────────────────────────────────────────────

def build_record(
    *,
    locked_by: str,
    items: Sequence[LockItem],
    canonical_files: Sequence[Path],
    repo_commit: str | None,
    now: datetime,
    simulator_commit: str | None = None,
    churn_evidence: ChurnThresholdEvidence | None = None,
    assumptions: Sequence[Mapping[str, object]] = (),
) -> dict[str, object]:
    """Lock 기록을 만든다. **`declaration` 은 인자가 아니라 `items` 에서 유도한다.**

    SERVICE_v1(commerce 소관)을 뺀 8종이 전부 LOCKED 일 때만 `FULL_FREEZE` +
    `experiment_environment_v1_declared: true` 이고, 아니면 `PARTIAL_FREEZE` + `false` 다.

    ★ `locked_by` 는 **사람 이름**이다. 빈 문자열이나 `"agent"` 를 허용하지
    않는다 — 봉인은 책임 소재가 있는 행위이고, 누가 눌렀는지가 기록의 요점이다.

    ★ `simulator_commit` 을 모르면 **`None`** 이 정직한 값이다. `""`·`"unknown"`·
    `"0"` 은 *"확인했고 이 값이다"* 가 되어 `FREEZE-003` 대조가 무의미해지므로
    40자 sha 가 아니면 거부한다.

    Raises:
        FreezeViolation: 사람 이름이 아니거나, 증거 없이 LOCKED 인 항목이 있거나
            (시뮬레이터 4종 · CHURN), LOCKED 항목의 정본 파일이 없다.
    """
    if not locked_by.strip() or locked_by.strip().lower() in (
        "agent", "unknown", "n/a", "-",
    ):
        raise FreezeViolation(
            f"locked_by={locked_by!r} 는 사람 이름이 아니다. 봉인은 책임 소재가 "
            "있는 행위이고, 누가 언제 무엇을 어느 범위까지 Lock 했는지가 이 "
            "기록의 존재 이유다"
        )
    _check_simulator_commit(simulator_commit)
    _check_lock_evidence(items, simulator_commit, churn_evidence)

    # LOCKED 항목의 정본도 해시 대조 대상이다. 호출자가 넘긴 목록에 없으면 덧붙인다.
    hashed = [path.as_posix() for path in canonical_files]
    for item in items:
        if item.status == "LOCKED":
            hashed.extend(path for path in item.canonical_files if path not in hashed)
    hashes = {path: file_sha256(Path(path)) for path in hashed}
    absent = sorted(
        path for item in items if item.status == "LOCKED"
        for path in item.canonical_files if hashes[path] is None
    )
    if absent:
        # 해시가 null 이면 verify() 가 null == null 로 일치를 낸다 — 없는 파일이 봉인된다.
        raise FreezeViolation(
            f"LOCKED 항목의 정본 파일이 없다: {absent}. 저장소 루트에서 실행했는지 "
            "확인한다"
        )

    # ★ declaration 을 인자로 받지 않는다 — 받으면 누군가 FULL_FREEZE 를 전달한다.
    #   항목에서 유도하므로 LOCKED 증거 없이는 FULL 이 될 수 없다.
    full = _all_lockable_locked(items)
    record: dict[str, object] = {
        "lock_record_version": LOCK_RECORD_VERSION,
        "gate": "GATE_1",
        "declaration": "FULL_FREEZE" if full else "PARTIAL_FREEZE",
        "experiment_environment_v1_declared": full,
        "declaration_note": _declaration_note(items, full=full),
        "locked_at": now.isoformat(timespec="milliseconds"),
        "locked_by": locked_by.strip(),
        "repo_commit": repo_commit,
        "simulator_commit": simulator_commit,
        "items": [
            {
                "item": item.item, "status": item.status,
                "owner_part": item.owner_part, "scope_note": item.scope_note,
                **({"canonical_files": list(item.canonical_files)}
                   if item.canonical_files else {}),
            }
            for item in items
        ],
        "canonical_files": hashes,
        # ★ 봉인이 무엇을 **가정한 채** 성립하는지 기록에 남긴다.
        #   가정을 남기지 않으면 다음 사이클이 Lock 을 "전부 확인됨" 으로 읽는다.
        "assumptions": [dict(item) for item in assumptions],
        "release_procedure": (
            "FREEZE-003 — 봉인 대상을 변경하면 버전을 상향하고 전 데이터를 "
            "재생성한 뒤 Baseline 부터 전 전략을 재실행한다. 해제는 사용자 "
            "승인 사항이며 이 파일을 손으로 고치는 것으로 대체되지 않는다."
        ),
    }
    if churn_evidence is not None:
        record["churn_threshold_evidence"] = {
            "met": churn_evidence.met, "evidence": churn_evidence.evidence,
        }
    if simulator_commit is None:
        record["simulator_commit_null_reason"] = (
            sc.ReasonCode.PRECONDITION_MISSING.value
        )
    if repo_commit is None:
        record["repo_commit_null_reason"] = sc.ReasonCode.PRECONDITION_MISSING.value
    return record


def _check_lock_evidence(
    items: Sequence[LockItem],
    simulator_commit: str | None,
    churn_evidence: ChurnThresholdEvidence | None,
) -> None:
    """LOCKED 항목이 그 증거와 함께 기록되는가. `lock_items_at_signing()` 을 거치지 않은 호출도 막는다."""
    locked = {item.item for item in items if item.status == "LOCKED"}
    if locked & set(SIMULATOR_LOCK_ITEMS) and simulator_commit is None:
        raise FreezeViolation(
            f"{sorted(locked & set(SIMULATOR_LOCK_ITEMS))} 가 LOCKED 인데 "
            "simulator_commit 이 없다. 어느 시뮬레이터를 봉인했는지 모르는 봉인은 "
            "FREEZE-003 대조를 할 수 없다"
        )
    if CHURN_ITEM in locked and not (churn_evidence is not None and churn_evidence.met):
        raise FreezeViolation(
            f"{CHURN_ITEM} 가 LOCKED 인데 data_spec §5.1 충족 증거가 없다. 임계값 "
            "28/42/60 은 ①~④ 실측 없이 Lock 하지 않는다 (DR-183)"
        )


def _declaration_note(items: Sequence[LockItem], *, full: bool) -> str:
    if full:
        return (
            "SERVICE_v1(commerce 소관)을 뺀 Lock 8종이 전부 LOCKED 다. "
            "EXPERIMENT_ENVIRONMENT_v1 을 선언한다."
        )
    locked = [item.item for item in items if item.status == "LOCKED"]
    if not locked:
        # #163 전 기록과 같은 문장 — 증거 없이 다시 서명해도 기록이 바뀌지 않는다.
        return (
            "C1 은 GATE 1 을 통과시키지 않는다. 측정 계층이 소유한 항목만 부분 "
            "봉인하고 나머지는 봉인 대기로 남긴다. EXPERIMENT_ENVIRONMENT_v1 을 "
            "선언하지 않는다."
        )
    return (
        f"LOCKED {len(locked)}종({', '.join(locked)})이다. SERVICE_v1 을 뺀 8종이 "
        "전부 LOCKED 가 아니므로 부분 봉인이다. EXPERIMENT_ENVIRONMENT_v1 을 "
        "선언하지 않는다."
    )


def record(
    verification: FreezeVerification,
    *,
    locked_by: str,
    canonical_files: Sequence[Path],
    repo_commit: str | None,
    now: datetime,
    path: Path = DEFAULT_LOCK_RECORD,
    assumptions: Sequence[Mapping[str, object]] = (),
    simulator_commit: str | None = None,
    churn_evidence: ChurnThresholdEvidence | None = None,
) -> dict[str, object]:
    """Lock 을 **실행**한다. ★ 선행 조건이 하나라도 미충족이면 거부한다.

    `can_lock` 은 `met is None`(확인하지 않았다)도 미충족으로 센다. **확인하지 않은 것을 충족으로 읽으면 봉인이
    거짓말이 된다.**

    항목 상태는 `verification.items` 가 아니라 이번에 넘긴 증거로 정한다
    (`lock_items_at_signing()`). 증거가 없으면 시뮬레이터 4종 · CHURN 은 서명 전
    기본 상태로 기록된다 — 예외가 아니다. 쓸 수 없는 증거(자리 표시 sha, sha 없는
    §5.1 충족)는 `FreezeViolation` 이다.
    """
    if not verification.can_lock:
        raise FreezeViolation(
            "선행 조건이 충족되지 않아 Lock 할 수 없다:\n"
            + "\n".join(
                f"  {item.id} ({'미충족' if item.met is False else '확인하지 않았다'})"
                f" — {item.title}"
                for item in verification.unmet
            )
            + "\n하나라도 미충족이면 Lock 하지 않는다. Lock 이후의 변경 비용이 "
            "전 데이터 재생성 + 전 전략 재실행이다 (FREEZE-003)."
        )
    payload = build_record(
        locked_by=locked_by,
        items=lock_items_at_signing(
            simulator_commit=simulator_commit, churn_evidence=churn_evidence,
        ),
        canonical_files=canonical_files, repo_commit=repo_commit, now=now,
        simulator_commit=simulator_commit, churn_evidence=churn_evidence,
        assumptions=assumptions,
    )
    # ★ YAML 은 config_loader 가 만진다. 가정 A7-6 이 `import yaml` 을 그 파일
    #   한 곳으로 제한하고, 여기서 직접 쓰면 그 불변식이 깨진다.
    dump_yaml(
        path, payload,
        header=(
            "# GATE 1 Lock 기록. **사람이 손으로 쓰지 않는다** — freeze.record() 가 쓴다.\n"
            "# 이 파일을 손으로 고치면 tests/test_freeze.py 의 해시 대조가 실패한다."
        ),
    )
    return payload


def load_record(path: Path = DEFAULT_LOCK_RECORD) -> Mapping[str, object] | None:
    """Lock 기록을 읽는다. **없으면 `None`** — 그것이 `not_started` 의 입력이다.

    ★ 여기서 `return` 으로 조용히 넘기지 않는다. `None` 을 돌려주고 `verify()` 가
    그것을 `not_started` + `missing` 으로 **값으로 만든다.**
    """
    if not path.exists():
        return None
    if not yaml_available():
        # ★ 예외를 던지지 않는다 — 위 RECORD_UNREADABLE 독트링 참조.
        #   조용히 None 으로 떨어뜨리지도 않는다. 그러면 기록이 있는데 '봉인을
        #   시작하지 않았다' 가 되어 거짓말이 된다.
        return RECORD_UNREADABLE  # type: ignore[return-value]
    return load_yaml(path)
