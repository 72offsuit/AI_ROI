"""`config/*.yaml` 을 읽어 **용도별로 분리된** 설정 객체로 돌려준다.

## 이 모듈의 두 가지 역할

1. **PyYAML 의 유일한 접점이다.** 저장소 전체에서 `import yaml` 은 이 파일에만 있고
   `tests/test_neutrality.py` 가 그것을 소스 검사로 고정한다. 이유는 CI 다 —
   `.github/workflows/isolation.yml` 에 의존성 설치 단계가 없으므로(ISO-005), YAML
   import 가 계산층으로 번지면 격리 CI 가 **격리와 무관한 이유로** 빨개진다:

       economics.py 가 yaml 을 import
         → tests/test_economics.py 가 economics 를 import
         → 의존성 미설치 CI 에서 ImportError
         → 격리 게이트가 깨진다

   여기서 끊으면 `test_economics.py` 는 PyYAML 없이 전부 돈다.

2. **원가율을 `economics.py` 로부터 격리한다** (EC-9). 한 덩어리 dict 를 돌려주면
   누구든 `cfg["product_margin"]["fresh_food"]["cost_rate"]` 에 손댈 수 있다.
   용도별 dataclass 로 쪼개면 `economics.py` 의 시그니처에
   `ProductGenerationConfig` 가 등장하지 않고, **원가율을 손에 넣을 방법이 타입
   수준에서 없어진다.** 규율이 아니라 구조로 막는다.

## 보안 — `yaml.safe_load()` 만 쓴다

`yaml.FullLoader` 는 조작된 페이로드로 임의 객체를 생성할 수 있다
(CVE-2020-14343, PyYAML < 5.4; CVE-2026-24009 는 docling-core 가 그 경로를 다시
노출시킨 사례다). 우리가 고정한 6.0.3 은 모든 공표 권고 범위보다 위지만, **로더
선택은 파일 출처와 무관한 습관의 문제**이므로 안전한 쪽을 기본으로 둔다.
`tests/test_neutrality.py` 가 `FullLoader`·`unsafe_load` 문자열이 0 건임을 고정한다.

**YAML 파서를 자체 구현하지 않는다.** 부분 구현 파서는 조용히 다른 값을 읽고, 경제
규칙 config 에서 그것은 기여이익이 조용히 틀리는 결과가 된다 — 이 프로젝트가
막으려는 실패 양식 그 자체다. PyYAML 이 없으면 `ConfigError` 로 멈춘다.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from src.measurement.errors import ConfigError

DEFAULT_ECONOMIC_CONFIG = Path("config/economic_config.yaml")


def yaml_available() -> bool:
    """PyYAML 이 설치되어 있는가.

    `sink.parquet_available()` 과 같은 guarded 패턴이다. 테스트가
    `@unittest.skipUnless(yaml_available(), "BLOCKED: …")` 로 쓰고, **skip 사유를
    남긴다** — skip 은 통과가 아니고 `unittest` 가 exit 0 을 내므로 사유 없이는
    검증하지 않은 것이 검증한 것처럼 보인다.
    """
    try:
        import yaml  # noqa: F401
    except ImportError:
        return False
    return True


# ── 용도별 설정 객체 ────────────────────────────────────────────────────────

@dataclass(frozen=True, slots=True)
class CategorySpec:
    """상품 생성 파라미터 한 카테고리분. **`cost_rate` 는 여기에만 있다.**"""

    display_name: str
    cost_rate: float
    margin_rate: float
    median_price_krw: int
    frequency_weight: float
    pool_size: int


@dataclass(frozen=True, slots=True)
class ProductGenerationConfig:
    """이후 사이클의 **시뮬레이터**가 받는 것. `economics.py` 는 이 타입을 모른다.

    `product_margin` 이 config 에 있는 이유는 `ECONOMIC RULE v1` Lock 대상이라서이지
    measurement 가 쓰기 위해서가 아니다.
    """

    categories: Mapping[str, CategorySpec]


@dataclass(frozen=True, slots=True)
class AiInvestmentConfig:
    model_development_cost_krw: int
    compute_cost_krw: int
    model_operating_cost_krw_per_month: int
    monitoring_cost_krw_per_month: int
    amortization_months: int
    is_estimate: bool
    estimate_note: str

    def monthly_amortized_krw(self) -> float:
        """월 귀속 AI 비용 = (개발 + 초기 컴퓨트) / 상각월수 + 월 운영비.

        `amortization_months` 가 0 이면 나누지 않고 예외를 던진다 — 0 으로 나눈
        결과를 0 이나 inf 로 만들면 그 값이 게시물까지 간다.
        """
        if self.amortization_months <= 0:
            raise ConfigError(
                "ai_investment.amortization_months 가 "
                f"{self.amortization_months} 다 — 1 이상이어야 한다. "
                f"{DEFAULT_ECONOMIC_CONFIG} 를 고친다."
            )
        upfront = self.model_development_cost_krw + self.compute_cost_krw
        recurring = (
            self.model_operating_cost_krw_per_month
            + self.monitoring_cost_krw_per_month
        )
        return upfront / self.amortization_months + recurring


@dataclass(frozen=True, slots=True)
class CostAccountingConfig:
    """**`economics.py` 가 받는 것.** 원가율 계열 속성이 하나도 없다 — 그것이 설계다.

    `tests/test_config_loader.py` 가 `cost_rate`·`margin_rate`·`product_margin`
    속성의 부재를 단언한다. 타입 봉쇄의 회귀 테스트다.
    """

    treatment_cost: Mapping[str, int]
    treatment_occurs_at: Mapping[str, str]
    coupon_treatments: tuple[str, ...]
    message_cost_krw: int
    campaign_fixed_cost_krw: int
    shipping_fee_krw: int
    free_shipping_threshold_krw: int
    ai_investment: AiInvestmentConfig
    assumptions: Mapping[str, object]


@dataclass(frozen=True, slots=True)
class EconomicConfig:
    """읽은 파일 전체. **두 조각을 따로 들고 있고 합쳐 주지 않는다.**"""

    version: str
    cost_accounting: CostAccountingConfig
    product_generation: ProductGenerationConfig


# ── 로딩 ────────────────────────────────────────────────────────────────────

def load_economic_config(path: Path | str = DEFAULT_ECONOMIC_CONFIG) -> EconomicConfig:
    """`economic_config.yaml` 을 읽어 검증하고 용도별로 쪼갠다.

    폴백이 없다. 파일이 없거나 파싱이 실패하거나 필수 키가 빠지면 `ConfigError` 다
    (종료 코드 5). 기본값으로 채워 계속 돌면 **어떤 값으로 계산했는지 아무도 모르는
    기여이익**이 나온다.

    `ConfigError` 메시지는 셋을 담는다 (NFR-006): 무엇이 · 왜 · 무엇을 하면 되는가.
    """
    path = Path(path)
    if not yaml_available():
        raise ConfigError(
            "PyYAML 이 설치되어 있지 않아 경제 규칙 config 를 읽을 수 없다. "
            "YAML 파서를 자체 구현하지 않는다 — 부분 구현 파서는 조용히 다른 값을 "
            "읽고, 경제 규칙에서 그것은 기여이익이 조용히 틀리는 결과가 된다. "
            "`pip install -r requirements.txt` 로 설치한다."
        )
    import yaml  # 함수 안 지연 import — 모듈 import 만으로 PyYAML 을 요구하지 않는다

    if not path.exists():
        raise ConfigError(
            f"경제 규칙 config 를 찾을 수 없다: {path} — 이 파일이 없으면 모든 금액이 "
            f"미정이고 비용 지표를 계산할 수 없다. 저장소 루트에서 실행하고 있는지 "
            f"확인하거나 {DEFAULT_ECONOMIC_CONFIG} 를 만든다."
        )
    try:
        # ★ safe_load 만 쓴다. 위 모듈 독트링의 보안 규약 참조.
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as error:
        raise ConfigError(
            f"{path} 를 YAML 로 해석할 수 없다: {error} — 들여쓰기나 콜론을 확인한다. "
            "부분적으로 읽어 계속 진행하지 않는다."
        ) from error

    if not isinstance(raw, Mapping):
        raise ConfigError(
            f"{path} 의 최상위가 매핑이 아니다 (읽은 타입: {type(raw).__name__}) — "
            "`key: value` 블록이어야 한다."
        )

    return EconomicConfig(
        version=_require(raw, "version", path),
        cost_accounting=_build_cost_accounting(raw, path),
        product_generation=_build_product_generation(raw, path),
    )


def _require(source: Mapping[str, Any], key: str, path: Path) -> Any:
    """필수 키를 꺼낸다. 없으면 `ConfigError`.

    `source.get(key, 기본값)` 을 쓰지 않는다. 기본값은 "설정하지 않았다"를
    "0 으로 설정했다"로 바꾸고, 그것이 이 프로젝트가 막는 결손 은폐다.
    """
    if key not in source:
        raise ConfigError(
            f"{path} 에 필수 키 `{key}` 가 없다 — 기본값으로 대체하지 않는다. "
            f"이 값이 없으면 그것을 쓰는 지표가 조용히 틀린다. "
            f"{path} 에 `{key}` 를 추가한다. (현재 키: {sorted(source)})"
        )
    return source[key]


def _build_cost_accounting(
    raw: Mapping[str, Any], path: Path
) -> CostAccountingConfig:
    treatments = _require(raw, "treatment_cost", path)
    accounting = _require(raw, "cost_accounting", path)
    shipping = _require(raw, "shipping", path)
    investment = _require(raw, "ai_investment", path)

    return CostAccountingConfig(
        treatment_cost={
            key: _require(spec, "unit_cost_krw", path)
            for key, spec in treatments.items()
        },
        treatment_occurs_at={
            key: _require(spec, "occurs_at", path)
            for key, spec in treatments.items()
        },
        coupon_treatments=tuple(_require(raw, "coupon_treatments", path)),
        message_cost_krw=_require(accounting, "message_cost_krw", path),
        campaign_fixed_cost_krw=_require(accounting, "campaign_fixed_cost_krw", path),
        shipping_fee_krw=_require(shipping, "shipping_fee_krw", path),
        free_shipping_threshold_krw=_require(
            shipping, "free_shipping_threshold_krw", path
        ),
        ai_investment=AiInvestmentConfig(
            model_development_cost_krw=_require(
                investment, "model_development_cost_krw", path
            ),
            compute_cost_krw=_require(investment, "compute_cost_krw", path),
            model_operating_cost_krw_per_month=_require(
                investment, "model_operating_cost_krw_per_month", path
            ),
            monitoring_cost_krw_per_month=_require(
                investment, "monitoring_cost_krw_per_month", path
            ),
            amortization_months=_require(investment, "amortization_months", path),
            is_estimate=_require(investment, "is_estimate", path),
            estimate_note=_require(investment, "estimate_note", path),
        ),
        assumptions=dict(_require(raw, "assumptions", path)),
    )


def _build_product_generation(
    raw: Mapping[str, Any], path: Path
) -> ProductGenerationConfig:
    margins = _require(raw, "product_margin", path)
    return ProductGenerationConfig(
        categories={
            key: CategorySpec(
                display_name=_require(spec, "display_name", path),
                cost_rate=_require(spec, "cost_rate", path),
                margin_rate=_require(spec, "margin_rate", path),
                median_price_krw=_require(spec, "median_price_krw", path),
                frequency_weight=_require(spec, "frequency_weight", path),
                pool_size=_require(spec, "pool_size", path),
            )
            for key, spec in margins.items()
        }
    )


# ── Lock 기록 입출력 (M-09 가 쓴다) ─────────────────────────────────────────
#
# `freeze.py` 가 YAML 을 직접 만지지 않게 여기 둔다. 가정 A7-6 이 `import yaml` 을
# **이 파일 한 곳**으로 제한하고 `tests/test_neutrality.py` 가 그것을 소스 검사로
# 고정한다 — 규칙을 넓히는 대신 경계를 재사용한다.

def dump_yaml(path: Path, payload: Mapping[str, Any], *, header: str = "") -> None:
    """매핑을 YAML 로 쓴다. **자체 직렬화기를 만들지 않는다.**

    부분 구현 직렬화기는 조용히 다른 값을 쓴다 — 읽는 쪽의 위험과 대칭이다.
    `sort_keys=False` 로 선언 순서를 유지한다: Lock 기록은 사람이 읽는 문서이기도
    하고, 키 순서가 바뀌면 diff 가 의미를 잃는다.
    """
    if not yaml_available():
        raise ConfigError(
            f"PyYAML 이 설치되어 있지 않아 {path} 를 쓸 수 없다. YAML 을 손으로 "
            "조립하지 않는다. `pip install -r requirements.txt`"
        )
    import yaml

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        (header.rstrip() + "\n" if header else "")
        + yaml.safe_dump(dict(payload), allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )


def load_yaml(path: Path) -> Mapping[str, Any]:
    """YAML 을 읽어 매핑으로 돌려준다. `yaml.safe_load()` 만 쓴다.

    ★ **파일이 없을 때의 처리는 호출자가 한다.** 여기서 `{}` 를 돌려주면
    "없다"와 "비어 있다"가 같아지고, `freeze.py` 에서 그 차이가 `not_started` 와
    `sealed` 를 가른다.
    """
    if not yaml_available():
        raise ConfigError(
            f"PyYAML 이 설치되어 있지 않아 {path} 를 읽을 수 없다. 파일이 "
            "존재하는데 읽지 못하는 것은 '파일이 없다'와 다르다 — 조용히 기본값으로 "
            "떨어지지 않고 멈춘다. `pip install -r requirements.txt`"
        )
    import yaml

    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, Mapping):
        raise ConfigError(
            f"{path} 의 최상위가 매핑이 아니다 (읽은 타입: {type(data).__name__})"
        )
    return data
