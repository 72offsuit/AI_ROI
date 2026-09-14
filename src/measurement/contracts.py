"""게시 계약의 코드 측면 — 봉투 생성 · `MetricValue` 직렬화 · 자기검증.

## 이 모듈이 쥐고 있는 한 가지

★ **`value_formatted` 를 만드는 유일한 자리다.**

계약은 `status` 가 `ok`·`unconfirmed` 인 지표에 `value_formatted` 를 **필수**로
요구한다. 그것을 누가 만드느냐가 설계 결정이었고, 호출자에게 맡기지 않았다:

    ⇥₁ MetricValue.ok() 호출자가 포맷해 넘긴다
       → 호출 지점마다 규칙이 달라지고, **한 곳만 빠뜨리면 화면이 undefined 를
         받는다.** 그리고 그 자리에 `?? 0` 이 생긴다.

    ⇥₂ 직렬화 시점에 한 곳에서 (채택)
       → 빠뜨릴 자리가 없다. `economics.py`·`kpi.py` 는 표시 규칙을 모른다 —
         창구 중립성과 같은 방향이다.

그래서 `MetricValue` dataclass 에 `value_formatted` **필드가 없다.**
`(status, unit, value)` 세 값이 있으면 결정되는 순수 함수이므로, 직렬화가 만든다.
**`unit` 이 없으면 그 함수가 성립하지 않는다** — `MetricValue.__post_init__` 이
계산된 상태에 `unit` 을 필수로 거는 이유가 이것이다.

`limit_note` 는 반대다. `unit` 에서 유도할 수 없는 지표별 사실이므로 **호출자가
넘기고** 직렬화는 그대로 옮긴다.

## 포맷 규칙은 왜 직접 쓰나

`locale` 모듈이나 `f"{x:,}"` 의 로케일 의존 경로를 쓰지 않는다. 환경마다 다른 결과가
나오면 같은 데이터가 다른 게시물이 되고 `NFR-001` 재현성이 무너진다. **명시적으로
포맷한다.**

## 자기검증 — `jsonschema` 없이 도는 층

결정 D-21 로 `jsonschema` 는 dev 전용이다. 그래서 게시 시점 자기검증은 **표준
라이브러리로 핵심 불변식만** 확인하고 `ContractViolation` 으로 fail closed 한다.
전체 draft-2020-12 검증은 `tests/test_publish_contract.py` 가 한다.

"핵심"의 기준: **위반이 화면에서 `?? 0` 을 부르는 것.** 그것만 골랐다.
"""

from __future__ import annotations

import hashlib
import json
import secrets
import subprocess
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable, Mapping

from src.measurement import schema as sc
from src.measurement import timeparse as tp
from src.measurement.errors import ContractViolation
from src.measurement.sink import KST

CONTRACT_VERSION = "measurement-publish/v1"
ARTIFACT_NAMES = frozenset({
    "index", "ingestion_report", "rejection_report", "field_coverage_report",
    "kpi_report", "data_quality_report", "freeze_status",
})


# ── run_id · 시각 ───────────────────────────────────────────────────────────

def new_run_id(*, now: datetime | None = None) -> str:
    """`MR-YYYYMMDD-HHMMSS-<8hex>` — 계약 정규식 `^MR-\\d{8}-\\d{6}-[0-9a-f]{8}$`.

    **KST 기준 시각**이다. 같은 게시 실행의 산출물은 전부 같은 `run_id` 를 갖고,
    대시보드는 `run_id` 가 다르면 값을 섞어 표시하지 않는다.

    난수에 `secrets` 를 쓰는 이유는 보안이 아니라 **충돌 회피**다. 같은 초에 두 번
    게시하면 시각 부분이 같아지므로 뒤 8자리가 구분해야 한다.

        >>> new_run_id(now=datetime(2026, 9, 11, 13, 58, 2, tzinfo=KST))[:19]
        'MR-20260911-135802-'
    """
    moment = (now or datetime.now(KST)).astimezone(KST)
    return f"MR-{moment:%Y%m%d}-{moment:%H%M%S}-{secrets.token_hex(4)}"


def kst_now(*, now: datetime | None = None) -> str:
    """계약 `kst_timestamp` 를 만족하는 문자열. **`Z` 표기는 이 패턴에서 실패한다.**

    W1 이 잡은 `manifest.created_at` 이 UTC 였던 문제(W-8)를 게시 계층에서 계약으로
    막는 자리다. 밀리초를 항상 붙여 자릿수가 흔들리지 않게 한다 — 마이크로초가 0 인
    시각만 `.000` 이 빠지면 같은 데이터가 다른 바이트를 낸다.
    """
    return (now or datetime.now(KST)).astimezone(KST).isoformat(
        timespec="milliseconds"
    )


# ── value_formatted — 이 모듈의 핵심 ────────────────────────────────────────

def _thousands(value: float) -> str:
    """천단위 구분을 로케일 없이 만든다.

    `f"{value:,.0f}"` 는 로케일 설정에 따라 구분자가 바뀔 수 있다. 반올림은
    표시에서만 하고 원값(`value`)은 건드리지 않는다.

        >>> _thousands(38400), _thousands(-1234.6), _thousands(0)
        ('38,400', '-1,235', '0')
    """
    rounded = int(round(value))
    sign = "-" if rounded < 0 else ""
    digits = str(abs(rounded))
    groups = []
    while len(digits) > 3:
        groups.insert(0, digits[-3:])
        digits = digits[:-3]
    groups.insert(0, digits)
    return sign + ",".join(groups)


def format_value(status: sc.MetricStatus, unit: sc.Unit | None, value: object) -> str | None:
    """`(status, unit, value)` → 화면이 그대로 출력하는 문자열. 순수 함수다.

    계산 불가 3종에는 `None` 을 돌려준다 — 계약이 그 상태에서
    `value_formatted` 를 **금지**하기 때문이다. 화면은 그때 `—`(EM DASH) 를 쓴다.

        >>> format_value(sc.MetricStatus.OK, sc.Unit.KRW, 38400)
        '38,400원'
        >>> format_value(sc.MetricStatus.OK, sc.Unit.RATIO, 0.1834)
        '18.3%'
        >>> format_value(sc.MetricStatus.OK, sc.Unit.PERCENTAGE_POINT, 3.2)
        '+3.2%p'
        >>> format_value(sc.MetricStatus.UNAVAILABLE, sc.Unit.KRW, None) is None
        True
    """
    if status not in (sc.MetricStatus.OK, sc.MetricStatus.UNCONFIRMED):
        return None
    if unit is None or value is None:
        # MetricValue.__post_init__ 이 이미 막지만, 직렬화가 계약 위반 문자열을
        # 만들어내지 않도록 여기서도 멈춘다. 조용히 빈 문자열을 쓰지 않는다.
        raise ContractViolation(
            f"status={status.value} 인데 unit 또는 value 가 없어 value_formatted 를 "
            f"만들 수 없다 (unit={unit!r}, value={value!r}). 계산한 쪽에서 unit 을 "
            "넘긴다 — unit 은 표시용 장식이 아니라 필수 입력이다."
        )
    if unit is sc.Unit.TEXT:
        return str(value)
    if unit is sc.Unit.DATETIME:
        # KST `YYYY-MM-DD HH:MM`. 화면이 다시 파싱하지 않게 완성해 보낸다.
        moment = value if isinstance(value, datetime) else tp.parse_datetime(str(value))
        return moment.astimezone(KST).strftime("%Y-%m-%d %H:%M")

    number = float(value)
    if unit is sc.Unit.KRW:
        return f"{_thousands(number)}원"
    if unit is sc.Unit.KRW_PER_CUSTOMER:
        return f"{_thousands(number)}원/인"
    if unit is sc.Unit.COUNT:
        return f"{_thousands(number)}건"
    if unit is sc.Unit.DAYS:
        return f"{_thousands(number)}일"
    if unit is sc.Unit.RATIO:
        # ★ ×100 을 여기서 끝낸다. 화면이 다시 곱하지 않는다.
        return f"{number * 100:.1f}%"
    if unit is sc.Unit.PERCENTAGE_POINT:
        # 부호를 유지한다 — "+3.2%p" 와 "3.2%p" 는 다른 주장이다.
        return f"{number:+.1f}%p"
    raise ContractViolation(f"포맷 규칙이 없는 unit: {unit!r}")  # pragma: no cover


def metric_to_json(metric: sc.MetricValue) -> dict[str, Any]:
    """`MetricValue` → 계약 `metric_value` dict.

    ★ `value_formatted` 가 여기서 붙는다. 호출자는 이 필드의 존재를 모른다.

    계약이 `additionalProperties: false` 이므로 **`None` 인 선택 필드를 키째로
    생략한다.** `"basis": null` 을 내보내면 계산 불가 분기의 `not` 이 키의 존재만
    보기 때문에 거부된다 — 값이 `null` 이어도 키가 있으면 위반이다.
    """
    payload: dict[str, Any] = {"status": metric.status.value}

    if metric.status in (sc.MetricStatus.OK, sc.MetricStatus.UNCONFIRMED):
        payload["value"] = metric.value
        payload["value_formatted"] = format_value(
            metric.status, metric.unit, metric.value
        )
        payload["basis"] = _basis_to_json(metric.basis)  # type: ignore[arg-type]
    else:
        # 계약이 value 를 null 로 요구한다. 키를 빼면 required 에 걸린다.
        payload["value"] = None

    if metric.unit is not None:
        payload["unit"] = metric.unit.value
    if metric.reason_code is not None:
        payload["reason_code"] = metric.reason_code.value
    if metric.reason_detail is not None:
        payload["reason_detail"] = metric.reason_detail
    if metric.blocked_by:
        payload["blocked_by"] = [
            {"kind": ref.kind.value, "ref": ref.ref,
             "reason_code": ref.reason_code.value}
            for ref in metric.blocked_by
        ]
    if metric.derived:
        payload["derived"] = True
        payload["derivation"] = metric.derivation
    if metric.params_used:
        payload["params_used"] = dict(metric.params_used)
    if metric.ci95 is not None:
        payload["ci95"] = {"low": metric.ci95[0], "high": metric.ci95[1]}
    if metric.limit_note is not None:
        payload["limit_note"] = metric.limit_note
    return payload


def _basis_to_json(basis: sc.Basis) -> dict[str, Any]:
    window: dict[str, Any] = {"direction": basis.window.direction.value}
    if basis.window.days is not None:
        window["days"] = basis.window.days
    if basis.window.label is not None:
        window["label"] = basis.window.label

    payload: dict[str, Any] = {
        "population": basis.population,
        "denominator_definition": basis.denominator_definition,
        "window": window,
    }
    # denominator·observed_count 는 null 이 의미 있는 값이다 (합계 지표의 분모 없음).
    # 그래서 None 이라도 키를 남긴다 — 계약이 `["number","null"]` 을 허용한다.
    payload["denominator"] = basis.denominator
    payload["observed_count"] = basis.observed_count
    if basis.excluded_count is not None:
        payload["excluded_count"] = basis.excluded_count
    if basis.excluded_reason is not None:
        payload["excluded_reason"] = basis.excluded_reason
    if basis.source_event_types:
        payload["source_event_types"] = list(basis.source_event_types)
    return payload


# ── 봉투 ────────────────────────────────────────────────────────────────────

@dataclass(frozen=True, slots=True)
class Notice:
    """읽을 때 함께 보여야 하는 명시 가정·한계.

    가정은 시간이 지나면 사실로 읽힌다. 그래서 문서가 아니라 **산출물에 붙여
    나른다** (`P-12`) — 문서는 아무도 다시 열지 않는다.
    """

    code: str
    level: str
    message: str
    reference: str | None = None

    def to_json(self) -> dict[str, Any]:
        payload = {"code": self.code, "level": self.level, "message": self.message}
        if self.reference:
            payload["reference"] = self.reference
        return payload


def repo_commit() -> tuple[str | None, str | None]:
    """`(commit, null_reason)`. 얻지 못하면 `(None, 사유)` — 빈 문자열로 채우지 않는다."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            capture_output=True, text=True, timeout=5, check=False,
        )
    except (OSError, subprocess.SubprocessError) as error:
        return None, f"git 실행 실패: {error}"
    if result.returncode != 0:
        return None, f"git rev-parse 실패: {result.stderr.strip()}"
    return result.stdout.strip(), None


def file_sha256(path: Path) -> str | None:
    """파일 해시. 없으면 `None` — 0 이나 빈 문자열로 채우지 않는다."""
    if not path.exists():
        return None
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build_provenance(
    *,
    source_root: Path | str,
    config_paths: Iterable[Path] = (),
    sink_manifest_sha256: str | None = None,
    simulator_commit: str | None = None,
    data_version: str | None = None,
) -> dict[str, Any]:
    """`DB-013` — 이 산출물이 무엇에서 나왔는가.

    ★ `simulator_commit` 을 얻으려고 `src/simulator/` 를 읽지 않는다. 격리 규칙
    위반이고, C1 에는 시뮬레이터가 없으므로 `None` 이 정직한 값이다. **`null` 인
    필드는 `null_reason` 에 사유를 남긴다** — 그것이 없으면 "0 으로 채운 것"과
    구분되지 않는다.
    """
    commit, commit_reason = repo_commit()
    hashes = {
        str(path): file_sha256(Path(path)) for path in config_paths
    }
    if sink_manifest_sha256 is not None:
        hashes["sink_manifest_sha256"] = sink_manifest_sha256

    null_reason: dict[str, str] = {}
    if commit is None:
        null_reason["repo_commit"] = sc.ReasonCode.PRECONDITION_MISSING.value
    if simulator_commit is None:
        null_reason["simulator_commit"] = sc.ReasonCode.PRECONDITION_MISSING.value
    if data_version is None:
        null_reason["data_version"] = sc.ReasonCode.PRECONDITION_MISSING.value

    provenance: dict[str, Any] = {
        "schema_version": sc.SCHEMA_VERSION,
        "repo_commit": commit,
        "data_version": data_version,
        "simulator_commit": simulator_commit,
        "config_hashes": hashes,
        "source_root": str(source_root),
        # 런타임 자기 실행 기록. "누가 만들었나" 가 없으면 재현 경로를 못 찾는다.
        "generated_by": "src.measurement.publish",
    }
    if null_reason:
        provenance["null_reason"] = null_reason
    if commit_reason:
        # 사유를 잃지 않는다. reason_code 는 기계용, 이 문장은 사람용이다.
        provenance["config_hashes"]["_repo_commit_note"] = commit_reason
    return provenance


def envelope(
    artifact: str,
    *,
    run_id: str,
    provenance: Mapping[str, Any],
    notices: Iterable[Notice] = (),
    now: datetime | None = None,
) -> dict[str, Any]:
    """모든 게시물의 공통 머리. 대시보드는 파서를 하나만 갖는다."""
    if artifact not in ARTIFACT_NAMES:
        raise ContractViolation(
            f"계약에 없는 산출물 이름: {artifact!r} — 허용: {sorted(ARTIFACT_NAMES)}"
        )
    return {
        "contract_version": CONTRACT_VERSION,
        "artifact": artifact,
        "run_id": run_id,
        "generated_at": kst_now(now=now),
        "timezone": sc.TIMEZONE,
        "provenance": dict(provenance),
        "notices": [notice.to_json() for notice in notices],
    }


# ── 자기검증 — 표준 라이브러리로 핵심 불변식만 ──────────────────────────────

_COMPUTED = frozenset({"ok", "unconfirmed"})
_UNCOMPUTED = frozenset({"unavailable", "blocked", "not_run"})


def verify_core_invariants(payload: object, *, where: str = "$") -> None:
    """게시 전 마지막 문. 위반이면 `ContractViolation` — **fail closed**.

    `jsonschema` 가 dev 전용이므로(D-21) 런타임은 이 함수가 전부다. 전체 스키마를
    다시 구현하지 않고, **위반이 화면에서 `?? 0` 을 부르는 것만** 고른다:

      1. 계산 불가에 `value` 가 `null` 이 아니다        → 0 채우기
      2. 계산 불가에 `basis` 가 있다                   → 근거 없는 값이 근거 있게 읽힌다
      3. 계산 불가에 `value_formatted` 가 있다          → 없는 값에 표시가 붙는다
      4. 계산됨에 `value_formatted` 가 없다             → 화면이 undefined 를 받는다
      5. 계산됨에 `basis`·`unit` 이 없다                → "측정된 0" 과 구분 불가
      6. `basis.denominator == 0` 인데 `ok`            → 0/0 을 0 으로 표시
      7. `derived` 인데 `derivation` 이 없다            → 유도값이 사실처럼 보인다

    나머지(정규식 방언·`$ref` 해석·`additionalProperties`)는
    `tests/test_publish_contract.py` 가 실제 validator 로 본다.

    재귀로 전체 트리를 훑는다 — `metric_value` 가 산출물마다 다른 깊이에 있고,
    경로를 손으로 적으면 새 산출물에서 빠뜨린다.
    """
    # ponytail: partial contract — 7 invariants, not the full draft-2020-12 schema.
    # Regexes (run_id · kst_timestamp), $ref resolution, additionalProperties and enum
    # membership are checked only by tests/test_publish_contract.py, which skips when
    # jsonschema is absent. Upgrade trigger: if D-21 is revisited and jsonschema moves
    # to requirements.txt, replace this body with a real Draft202012Validator call and
    # keep the ContractViolation wrapper; also upgrade if any contract violation is ever
    # found in a published results/ artifact that this function let through.
    if isinstance(payload, dict):
        if isinstance(payload.get("status"), str) and "status" in payload:
            _verify_metric_like(payload, where)
        for key, value in payload.items():
            verify_core_invariants(value, where=f"{where}.{key}")
    elif isinstance(payload, list):
        for index, value in enumerate(payload):
            verify_core_invariants(value, where=f"{where}[{index}]")


def _verify_metric_like(node: Mapping[str, Any], where: str) -> None:
    status = node["status"]
    if status in _UNCOMPUTED:
        if node.get("value", None) is not None:
            raise ContractViolation(
                f"{where}: status={status} 인데 value={node['value']!r} 다. 계산 "
                "불가에 0 이나 추정값을 넣지 않는다 — 이 한 줄이 USP-1 을 끝낸다."
            )
        for forbidden, why in (
            ("basis", "기준의 유무가 '측정된 0'과 '값 없음'을 가른다"),
            ("value_formatted", "없는 값에 표시 문자열이 붙으면 화면이 값으로 읽는다"),
        ):
            if forbidden in node:
                raise ContractViolation(
                    f"{where}: status={status} 인데 {forbidden} 가 있다 — {why}"
                )
        if not node.get("reason_code") or not str(node.get("reason_detail", "")).strip():
            raise ContractViolation(
                f"{where}: status={status} 인데 reason_code/reason_detail 이 없다. "
                "계산하지 못한 이유가 없으면 화면이 그 자리를 비운다."
            )
    elif status in _COMPUTED:
        for required, why in (
            ("value_formatted", "화면이 undefined 를 받고 그 자리에 ?? 0 이 생긴다"),
            ("basis", "'측정된 0'과 '값 없음'을 구분할 수 없다"),
            ("unit", "value_formatted 를 만들 수 없다"),
        ):
            if required not in node:
                raise ContractViolation(
                    f"{where}: status={status} 인데 {required} 가 없다 — {why}"
                )
        if node.get("value") is None:
            raise ContractViolation(f"{where}: status={status} 인데 value 가 null 이다")
        basis = node.get("basis") or {}
        if status == "ok" and isinstance(basis, dict) and basis.get("denominator") == 0:
            raise ContractViolation(
                f"{where}: basis.denominator=0 인데 status=ok 다. 분모가 0 이면 "
                "계산된 것이 아니다 — 0/0 을 0 으로 표시하는 경로다."
            )
    if node.get("derived") and not str(node.get("derivation", "")).strip():
        raise ContractViolation(
            f"{where}: derived=true 인데 derivation 이 없다. 규칙에서 유도한 값이 "
            "저장된 사실처럼 보이면 안 된다."
        )


#: manifest 에서 없거나 `null` 이면 **결손이 조용히 0 으로 바뀌는** 건수 필드.
#: 나머지 필드는 없어도 읽는 쪽이 정직하게 처리할 수 있지만, 이 둘은 아니다.
_MANIFEST_COUNT_FIELDS = ("rows", "rejected")

#: 값이 있으면 그 타입이어야 하는 필드. 타입이 어긋나면 읽는 쪽의
#: `or {}` / `or []` 가 **조용히 빈 값으로 바꾼다** — 그것이 M1 에서
#: `unavailable_metrics` 가 0 종이 된 직접 경로다.
_MANIFEST_SHAPES: tuple[tuple[str, type, str], ...] = (
    ("sources", dict, "매핑"),
    ("event_type_counts", dict, "매핑"),
    ("field_coverage", dict, "매핑"),
    ("missing_fields", list, "배열"),
    ("unavailable_metrics", list, "배열"),
    ("files", list, "배열"),
)


def verify_manifest_invariants(manifest: object, *, where: str = "manifest.json") -> None:
    """**읽기 전** 마지막 문. `verify_core_invariants()` 의 입력 쪽 대칭이다.

    산출물 8종에는 전부 계약이 있는데 **모든 지표가 파생되는 유일한 입력에만
    없었다** (리뷰 M1 · 이슈 #59). 그 비대칭이 만든 실제 동작:

        manifest 없음          → SINK_EMPTY · 계산 불가 16종   ✅ 정직
        rows 키 없음           → SINK_EMPTY · 계산 불가  0종   ❌
        rows: null             → SINK_EMPTY · 계산 불가  0종   ❌

    **더 망가진 상태가 더 자신 있는 출력을 냈다.** ``rows: null`` 은 manifest 가
    "모른다"를 명시한 것인데 ``.get("rows", 0) or 0`` 이 그것을 0("세어봤고
    없었다")으로 바꾼다 — 이 프로젝트가 가장 경계하는 실패 양식이다.

    ★ 고르는 기준은 `verify_core_invariants()` 와 같다. 전체 스키마를 다시
      구현하지 않고(`jsonschema` 는 dev 전용 — D-21), **위반이 결손을 0 으로
      보이게 만드는 것만** 고른다. 전체 검증은 테스트층이
      `manifest.schema.json` 으로 한다. **두 층은 서로를 대체하지 않는다.**

    ★ 트리거를 오해하지 말 것. 비원자적 쓰기가 만드는 것은 **잘린 JSON** 이고
      그것은 `JSONDecodeError` 로 **시끄럽게** 죽는다. 조용한 0-채움은
      **유효한 JSON 이 키를 빠뜨리거나 `null` 일 때** 생기며, 원인은 부분 기록이
      아니라 **버전 스큐·손편집·다른 생산자**다 (보안 감사 F6 가 정정).
    """
    if not isinstance(manifest, Mapping):
        raise ContractViolation(
            f"{where}: manifest 가 매핑이 아니다 ({type(manifest).__name__}). "
            "이후 검사가 전부 무의미해지므로 여기서 멈춘다."
        )
    for field_name in _MANIFEST_COUNT_FIELDS:
        if field_name not in manifest:
            raise ContractViolation(
                f"{where}: 필수 필드 `{field_name}` 이 없다. 읽는 쪽이 이것을 0 으로 "
                "읽으면 '세어봤고 없었다' 가 되어, 깨진 manifest 가 '수집 0건인 "
                "정상 상태' 로 화면에 뜬다. manifest 가 통째로 없는 것과 다르다 — "
                "그 경우는 읽는 쪽이 계산 불가로 정직하게 처리한다."
            )
        value = manifest[field_name]
        if value is None:
            raise ContractViolation(
                f"{where}: `{field_name}` 이 null 이다. null 은 '모른다' 이고 0 은 "
                "'세어봤고 없었다' 이며 **둘은 다르다**. 모르는 상태를 manifest 로 "
                "표현하지 않는다."
            )
        if isinstance(value, bool) or not isinstance(value, int):
            raise ContractViolation(
                f"{where}: `{field_name}` 이 정수가 아니다 ({value!r}). 건수 필드다."
            )
        if value < 0:
            raise ContractViolation(
                f"{where}: `{field_name}` 이 음수다 ({value}). 건수는 음수일 수 없다."
            )
    for field_name, expected, korean in _MANIFEST_SHAPES:
        if field_name not in manifest:
            continue
        value = manifest[field_name]
        if not isinstance(value, expected):
            raise ContractViolation(
                f"{where}: `{field_name}` 이 {korean}이 아니다 ({type(value).__name__}). "
                f"읽는 쪽의 `or` 폴백이 이것을 조용히 빈 값으로 바꾸고, 그러면 "
                "계산 불가 표시가 사라진다."
            )


def dump(payload: Mapping[str, Any]) -> str:
    """게시물 직렬화. **검증을 통과하지 못하면 문자열을 만들지 않는다.**

    `sort_keys=True` 로 키 순서를 고정한다 — 같은 내용이 같은 바이트를 내야
    `NFR-001` 해시 대조가 성립한다.
    """
    verify_core_invariants(payload)
    return json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
