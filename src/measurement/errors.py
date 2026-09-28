"""측정 계층 예외 계층 (SRS NFR-006).

**이 모듈은 아무것도 import 하지 않는다** — 표준 라이브러리조차. 잎 노드로 두면
`schema.py`·`economics.py`·`config_loader.py` 가 서로를 거치지 않고 예외를 공유할 수
있고, 순환 import 가 생길 자리가 없다.

## 값이냐 예외냐 — 이 프로젝트에서 가장 중요한 구분

    "이것이 화면에 표시되어야 하는가?"
        표시되어야 한다  →  값이다   (schema.MetricValue — status/reason_code)
        실행을 계속할 수 없다 →  예외다  (이 모듈)

"원가 근거가 없어 기여이익을 계산할 수 없다"는 **예외가 아니다.** 그것은 화면에
`계산 불가 · NO_COST_BASIS` 로 표시되어야 하는 **결과**다. 예외로 만들면 호출자가
`try/except` 로 감싸고, 그러다 `except: return 0` 이 생긴다 — 이 프로젝트가 막으려는
실패 양식 그 자체다.

## 메시지 규약 — 셋을 담는다 (NFR-006)

    ① 무엇이 일어났는가 · ② 왜 · ③ 무엇을 하면 되는가

③ 이 없는 메시지는 읽는 사람을 막다른 길에 세운다. `ConfigError` 가 파일 경로와
누락 키를 함께 싣는 이유다.
"""


class MeasurementError(Exception):
    """측정 계층의 모든 예외의 뿌리.

    호출자가 `except MeasurementError` 하나로 이 계층의 실패를 묶어 잡을 수 있게
    한다. 그러라고 두는 것이지 **삼키라고** 두는 것이 아니다 — 잡았으면 사유를 남긴다.
    """

    #: 프로세스 종료 코드. CLI·CI 가 실패의 종류를 문자열 파싱 없이 구분한다.
    exit_code = 1


# ── 계약 위반 ───────────────────────────────────────────────────────────────

class ContractError(MeasurementError):
    """계약(스키마·타입·불변식)이 깨졌다. 데이터나 코드가 약속을 어긴 것이다."""


class SchemaError(ContractError):
    """이벤트 레코드가 `EVENT SCHEMA v1` 을 어겼다.

    주의: 레코드 **한 건**의 위반은 예외가 아니라 `validate_event()` 의
    `list[str]` 이다. 수집은 한 건 때문에 멈추지 않는다 (MEA-003). 이 예외는
    스키마 자체가 모순인 경우 — 호출자가 계약을 잘못 쓴 경우에 쓴다.
    """


class PartitionKeyError(ContractError):
    """`timestamp` 에서 파티션 키를 만들 수 없다.

    스키마를 통과한 레코드가 저장 단계에서 걸리는 자리다. **조용히 넘기지 않는다** —
    파티션 키가 없으면 그 레코드는 어느 날짜에도 속하지 않고, 기본값으로 넣으면
    하루치 데이터가 조용히 오염된다.
    """


class ExchangeContractError(ContractError):
    """커머스 교환 파일(`data/commerce/`)이 계약 v1 을 어겼다.

    행 하나의 형식이 틀리거나 매니페스트 행 수와 파일이 어긋나면 묶음 전체를
    거부한다. 일부만 읽으면 COGS 가 **일부 주문의 합계**인데 전체처럼 보인다.
    품목이 없는 주문은 형식 위반이 아니라 `DQ-09` 위반이므로 여기서 막지 않는다.
    """

    exit_code = 3


class ContractViolation(ContractError):
    """게시물이 자기 계약(`docs/contracts/**`)을 어겼다. 게시를 중단한다.

    fail closed — 계약을 어긴 게시물을 내보내는 것보다 아무것도 내보내지 않는 것이
    낫다. 어긴 게시물은 화면에서 `undefined` 가 되고, 그 자리에 `?? 0` 이 생긴다.
    """

    exit_code = 3


# ── 게이트 ──────────────────────────────────────────────────────────────────

class GateError(MeasurementError):
    """게이트(품질·봉인) 판정이 실패했다."""


class QualityGateFailure(GateError):
    """데이터 품질 검사가 `fail` 로 판정했다."""

    exit_code = 2


class FreezeViolation(GateError):
    """봉인된 대상이 봉인 이후 변경됐다 (FREEZE-003).

    이것이 참이면 Baseline 부터 전 전략을 재실행해야 한다. 경고로 낮추지 않는다 —
    봉인하지 않은 상태가 초록으로 보이는 것이 봉인 검사의 유일한 실패 양식이다.
    """

    exit_code = 4


# ── 설정·게시·의존성 ────────────────────────────────────────────────────────

class ConfigError(MeasurementError):
    """`config/*.yaml` 을 읽을 수 없거나 필수 키가 없다.

    **폴백하지 않는다.** 경제 규칙 config 를 부분적으로 읽으면 기여이익이 조용히
    틀리고, 그것은 틀린 값을 만드는 가장 비싼 방법이다.
    """

    exit_code = 5


class PublishError(MeasurementError):
    """게시 과정의 I/O 실패. 부분 게시물을 남기지 않는다."""

    exit_code = 6


class DependencyMissing(MeasurementError):
    """선택 의존성이 필요한 경로인데 설치되어 있지 않다.

    `skip` 과 구분한다 — 테스트는 `skipUnless` 로 건너뛰고 **그 사실을 남기지만**,
    프로덕션 경로에서 명시적으로 요청된 기능(`fmt="parquet"`)은 조용히 다른 형식으로
    바꾸지 않고 이 예외로 멈춘다.
    """

    exit_code = 7
