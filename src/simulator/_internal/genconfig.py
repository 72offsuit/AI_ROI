"""생성 config(`config/simulator_config.yaml`) 로더 — Persona 구성비와 Hidden Trait 모수의 유일한 원천.

파일 확장자는 yaml 이지만 내용은 JSON 문법으로 제한한다(사용자 확정 U2). 그래서 PyYAML 이 없는
3.10 에서도 표준 `json` 으로 읽는다. 값은 정수만 받는다 — 소수·NaN·중복 키는 로드 단계에서 거부해
"조용히 다른 세계"가 생기지 않게 한다(`DR-S2-trait-sampling` 3절).

다이제스트는 생성에 쓰는 부분(`GENERATION_KEYS` — `config_version`·`personas`·`hidden_traits`·`behavior`·
`catalog`)의 정준 JSON sha256 이다. 결과를 바꾸지 않는 블록(`notes`·`guardrails`·`churn`)은 넣지 않는다.
이 값이 상태의 `generation` 과 `world_id` 에 결속돼, config 가 바뀌면 옛 상태·계보가 명시 오류로 거부된다.

활성 config 는 프로세스에 하나다(`active`). 기본 경로(`CONFIG_PATH`) 대신 실험용 파일을 쓰려면 `switch` 로
고른다. 판 고정(`tests/test_simulator_persona.py` `CONFIG_PINS`)은 기본 경로 파일에만 걸린다 — 실험 파일은
판 이름이 같아도 내용이 달라도 되며, 그 구분은 다이제스트 결속이 맡는다.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from types import MappingProxyType
from typing import Callable, Mapping, TypeVar

from src.simulator._internal.rng import canonical_json

CONFIG_PATH = Path(__file__).resolve().parents[3].joinpath("config", "simulator_config.yaml")
# 오류 메시지에는 절대 경로 대신 저장소 상대 이름만 싣는다.
CONFIG_NAME = "config/simulator_config.yaml"

# S4~S6(#143): behavior(행동·이탈·처치 반응 모수)와 catalog(상품 풀)도 생성 부분이다 — 다이제스트에 든다.
GENERATION_KEYS = ("config_version", "personas", "hidden_traits", "behavior", "catalog")
_REQUIRED_TOP = frozenset(GENERATION_KEYS)
# guardrails 는 검사 범위, churn 은 측정 계층이 읽는 이탈 운영 정의라 생성 결과를 바꾸지 않는다 — 다이제스트에
# 넣지 않는다. churn 의 의미 검증은 측정 계층이 하고 여기서는 객체인지만 본다.
_OPTIONAL_TOP = frozenset({"notes", "guardrails", "churn"})
_PERSONA_KEYS = frozenset({"id", "alias", "ratio_bp"})
# 선택 키. 없으면 Day 0 가입이다(DR-S3-p6-signup).
_PERSONA_OPTIONAL_KEYS = frozenset({"signup_day_range"})
_IDENTIFIER = re.compile(r"[a-z][a-z0-9_]*")
_ALIAS = re.compile(r"P[0-9]+")
_VERSION = re.compile(r"[a-z0-9][a-z0-9.-]*")

RATIO_TOTAL_BP = 10_000
# LogNormal 중앙값·Gamma 평균의 범위(정수 단위). 하한 1000 은 정수 1 단위가 중앙값·평균의 0.1% 이하가
# 되게 한다(DR-S2-trait-sampling 3절 해상도 근거 — 방문 빈도 평균 1.4회/주 대비 0.07%). 그보다 작은 척도는
# 값이 몇 개 정수로 뭉개지는데도 반올림 띠가 오차를 흡수해 정확도 관문이 잡지 못한다.
# 지금 config 의 최솟값은 1400(P5 방문 빈도)이라 ±20% 민감도 분석(1120)도 받는다.
MIN_SCALE_VALUE = 1_000
MAX_SCALE_VALUE = 1_000_000_000_000
# 퍼짐 하한(정수 단위). 척도 하한만으로는 σ·k 가 작을 때 분포가 몇 개 정수로 뭉개지는 것을 막지 못한다
# (σ = 1 ppm 이면 전원이 중앙값 한 값인데 관문은 통과한다). 해상도는 척도가 아니라 퍼짐 대비로 정해진다.
# LogNormal 은 σ·중앙값(중앙값 근처 표준편차의 근사), Gamma 는 평균/√k(표준편차)가 이 값 이상이어야 한다.
# 100 단위면 정수 1 단위가 표준편차의 1% 이하라 ±3 표준편차 안에 서로 다른 값이 수백 개 남는다.
# 지금 config 의 최솟값은 LogNormal 2,700(purchase_cycle P1 = 0.45 × 6,000), Gamma 700(P5 방문 = 1,400 / 2)이다.
MIN_SPREAD_UNITS = 100
MIN_PERSONAS = 6
# 가입일 범위 상한(일). 프로파일 중 가장 긴 long 의 총 일수(1,100일)를 덮는다.
MAX_SIGNUP_DAY = 3_650
PPM = 1_000_000


@dataclass(frozen=True)
class _Family:
    """분포족별 config 키와 수치 엔진이 검증한 모수 범위."""

    shape_key: str
    persona_key: str
    shape_range: tuple[int, int]
    value_range: tuple[int, int]
    units: frozenset[str]


# 범위 밖 모수는 매듭표 정확도를 검증하지 않은 영역이라 로드에서 거부한다. 넓히려면
# tests/test_simulator_trait_distribution.py 로 새 모양의 정확도를 먼저 확인한다.
FAMILIES: Mapping[str, _Family] = MappingProxyType({
    # Beta(μκ, (1−μ)κ): κ ∈ [1, 100], μ ∈ (0, 1) ppm. α·β 하한은 아래 _check_beta_shape.
    "beta": _Family("kappa_milli", "mu_ppm", (1_000, 100_000), (1, PPM - 1), frozenset({"ppm"})),
    # LogNormal(ln 중앙값, σ): σ ∈ (0, 1]
    "lognormal": _Family(
        "sigma_ppm", "median", (1, PPM), (MIN_SCALE_VALUE, MAX_SCALE_VALUE),
        frozenset({"krw", "milli_day"}),
    ),
    # Gamma(k, 평균): k ∈ [1, 100]
    "gamma": _Family(
        "shape_milli", "mean", (1_000, 100_000), (MIN_SCALE_VALUE, MAX_SCALE_VALUE),
        frozenset({"milli_per_week"}),
    ),
})
# α = μ·κ, β = (1−μ)·κ 를 1e-9 단위(ppm × milli)로 본 하한·상한: 0.3 ≤ α, β ≤ 100.
_BETA_SHAPE_NANO = (300_000_000, 100_000_000_000)


class ConfigError(Exception):
    """생성 config 를 읽을 수 없거나 계약을 어겼다."""


@dataclass(frozen=True)
class PersonaSpec:
    id: str
    alias: str
    ratio_bp: int
    # 반열림 [from, until) 일 번호. None 이면 Day 0 가입.
    signup_day_range: tuple[int, int] | None = None


@dataclass(frozen=True)
class TraitSpec:
    name: str
    family: str
    unit: str
    shape: int
    by_persona: Mapping[str, int]

    @property
    def kappa_milli(self) -> int:
        return self._shape("beta")

    @property
    def sigma_ppm(self) -> int:
        return self._shape("lognormal")

    @property
    def shape_milli(self) -> int:
        return self._shape("gamma")

    def _shape(self, family: str) -> int:
        if self.family != family:
            raise AttributeError(f"{self.name} 는 {self.family} 라서 {family} 모수가 없다")
        return self.shape


@dataclass(frozen=True)
class GenerationConfig:
    version: str
    digest: str
    personas: tuple[PersonaSpec, ...]
    traits: tuple[TraitSpec, ...]
    # 정수·문자열·null 만 담은 원본 블록. 해석·검사는 params.py 가 한다(S4~S6).
    # 기본값은 default_factory 로 둔다 — Python 3.11 의 dataclass 는 해시할 수 없는 기본값(mappingproxy 는 3.12
    # 부터 해시 가능)을 거부해 import 가 깨진다(#248).
    behavior: Mapping[str, object] = field(default_factory=lambda: MappingProxyType({}))
    catalog: Mapping[str, object] = field(default_factory=lambda: MappingProxyType({}))
    guardrails: Mapping[str, object] = field(default_factory=lambda: MappingProxyType({}))

    @property
    def persona_ids(self) -> tuple[str, ...]:
        return tuple(p.id for p in self.personas)

    @property
    def ratios(self) -> tuple[int, ...]:
        return tuple(p.ratio_bp for p in self.personas)

    @property
    def trait_names(self) -> tuple[str, ...]:
        return tuple(t.name for t in self.traits)


def _reject_float(text: str) -> object:
    raise ConfigError(f"정수만 받는다 — 소수 {text!r}")


def _reject_constant(text: str) -> object:
    raise ConfigError(f"정수만 받는다 — {text}")


def _unique_keys(pairs: list[tuple[str, object]]) -> dict[str, object]:
    found: dict[str, object] = {}
    for key, value in pairs:
        if key in found:
            raise ConfigError(f"중복 키: {key!r}")
        found[key] = value
    return found


def digest(document: Mapping[str, object]) -> str:
    return hashlib.sha256(canonical_json({key: document[key] for key in GENERATION_KEYS})).hexdigest()


def parse(text: str) -> GenerationConfig:
    try:
        document = json.loads(
            text,
            parse_float=_reject_float,
            parse_constant=_reject_constant,
            object_pairs_hook=_unique_keys,
        )
    except json.JSONDecodeError as error:
        raise ConfigError(f"JSON 문법이 아니다 ({error.lineno}행 {error.colno}열)") from error
    except (ValueError, RecursionError) as error:
        # 정수 자릿수 한계(int 변환 4300자리)·지나친 중첩 같은 파서 한계도 config 오류로 알린다.
        # 그대로 두면 공개 경계에서 "인자 범위 밖"을 뜻하는 ValueError 로 새 나간다.
        raise ConfigError(f"JSON 을 읽지 못했다: {type(error).__name__}") from error
    if not isinstance(document, dict):
        raise ConfigError("최상위가 객체가 아니다")
    _exact_keys("최상위", document, _REQUIRED_TOP, _OPTIONAL_TOP)
    version = document["config_version"]
    if not isinstance(version, str) or not _VERSION.fullmatch(version):
        raise ConfigError(f"config_version 형식 위반: {version!r}")
    notes = document.get("notes", [])
    if not isinstance(notes, list) or not all(isinstance(n, str) and n for n in notes):
        raise ConfigError("notes 는 비지 않은 문자열의 배열이어야 한다")
    personas = _personas(document["personas"])
    ids = tuple(p.id for p in personas)
    traits = _traits(document["hidden_traits"], ids)
    for block in ("behavior", "catalog", "guardrails", "churn"):
        if not isinstance(document.get(block, {}), dict):
            raise ConfigError(f"{block} 는 객체여야 한다")
    config = GenerationConfig(
        version, digest(document), personas, traits,
        document["behavior"], document["catalog"], document.get("guardrails", {}),
    )
    # 순환 import 를 피해 지연 import 한다. 블록 구조 위반은 로드 단계에서 거부한다.
    from src.simulator._internal import params

    try:
        params.Params(config)
    except (KeyError, TypeError, ValueError) as error:
        raise ConfigError(f"behavior·catalog·guardrails 블록 위반: {error}") from error
    return config


def _exact_keys(
    where: str, value: object, required: frozenset[str], optional: frozenset[str] = frozenset()
) -> dict[str, object]:
    if not isinstance(value, dict):
        raise ConfigError(f"{where}: 객체가 아니다")
    unknown = sorted(set(value) - required - optional)
    missing = sorted(required - set(value))
    if unknown or missing:
        raise ConfigError(f"{where}: 모르는 키 {unknown} · 없는 키 {missing}")
    return value


def _int(where: str, value: object, lo: int, hi: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ConfigError(f"{where}: 정수가 아니다 ({value!r})")
    if not lo <= value <= hi:
        raise ConfigError(f"{where}: 범위 [{lo}, {hi}] 밖 ({value})")
    return value


def _personas(value: object) -> tuple[PersonaSpec, ...]:
    if not isinstance(value, list):
        raise ConfigError("personas 는 배열이어야 한다")
    if len(value) < MIN_PERSONAS:
        raise ConfigError(f"페르소나가 {len(value)}종이다 — 최소 {MIN_PERSONAS}종(SRS SIM-001)")
    specs: list[PersonaSpec] = []
    for index, item in enumerate(value):
        where = f"personas[{index}]"
        entry = _exact_keys(where, item, _PERSONA_KEYS, _PERSONA_OPTIONAL_KEYS)
        pid, alias = entry["id"], entry["alias"]
        if not isinstance(pid, str) or not _IDENTIFIER.fullmatch(pid):
            raise ConfigError(f"{where}.id 형식 위반: {pid!r}")
        if not isinstance(alias, str) or not _ALIAS.fullmatch(alias):
            raise ConfigError(f"{where}.alias 형식 위반: {alias!r}")
        specs.append(PersonaSpec(
            pid, alias, _int(f"{where}.ratio_bp", entry["ratio_bp"], 1, RATIO_TOTAL_BP),
            _signup_range(f"{where}.signup_day_range", entry.get("signup_day_range")),
        ))
    for field in ("id", "alias"):
        seen = [getattr(p, field) for p in specs]
        if len(set(seen)) != len(seen):
            raise ConfigError(f"personas 의 {field} 가 겹친다")
    total = 0
    for spec in specs:
        total += spec.ratio_bp
    if total != RATIO_TOTAL_BP:
        raise ConfigError(f"ratio_bp 합이 {total} 이다 — {RATIO_TOTAL_BP} 이어야 한다")
    return tuple(specs)


def _signup_range(where: str, value: object) -> tuple[int, int] | None:
    if value is None:
        return None
    if not isinstance(value, list) or len(value) != 2:
        raise ConfigError(f"{where}: [from, until] 두 정수가 아니다")
    lo = _int(f"{where}[0]", value[0], 0, MAX_SIGNUP_DAY - 1)
    hi = _int(f"{where}[1]", value[1], lo + 1, MAX_SIGNUP_DAY)
    return lo, hi


def _traits(value: object, persona_ids: tuple[str, ...]) -> tuple[TraitSpec, ...]:
    if not isinstance(value, list) or not value:
        raise ConfigError("hidden_traits 는 비지 않은 배열이어야 한다")
    specs: list[TraitSpec] = []
    for index, item in enumerate(value):
        where = f"hidden_traits[{index}]"
        if not isinstance(item, dict):
            raise ConfigError(f"{where}: 객체가 아니다")
        family_name = item.get("family")
        if not isinstance(family_name, str) or family_name not in FAMILIES:
            raise ConfigError(f"{where}.family 를 모른다: {family_name!r} (허용: {sorted(FAMILIES)})")
        family = FAMILIES[family_name]
        entry = _exact_keys(
            where, item,
            frozenset({"name", "family", "unit", family.shape_key, family.persona_key}),
        )
        name = entry["name"]
        if not isinstance(name, str) or not _IDENTIFIER.fullmatch(name):
            raise ConfigError(f"{where}.name 형식 위반: {name!r}")
        unit = entry["unit"]
        if unit not in family.units:
            raise ConfigError(f"{where}.unit {unit!r} 는 {family_name} 에 허용되지 않는다")
        shape = _int(f"{name}.{family.shape_key}", entry[family.shape_key], *family.shape_range)
        mapping = _exact_keys(f"{name}.{family.persona_key}", entry[family.persona_key], frozenset(persona_ids))
        by_persona = {
            pid: _int(f"{name}.{family.persona_key}.{pid}", mapping[pid], *family.value_range)
            for pid in persona_ids
        }
        if family_name == "beta":
            _check_beta_shape(name, shape, by_persona)
        else:
            _check_spread(name, family_name, shape, by_persona)
        specs.append(TraitSpec(name, family_name, str(unit), shape, MappingProxyType(by_persona)))
    names = [s.name for s in specs]
    if len(set(names)) != len(names):
        raise ConfigError("hidden_traits 의 name 이 겹친다")
    return tuple(specs)


def _check_spread(name: str, family: str, shape: int, by_persona: Mapping[str, int]) -> None:
    for pid, scale in by_persona.items():
        if family == "lognormal":
            # σ·중앙값 ≥ 100 단위  ⇔  sigma_ppm · median ≥ 100 · 1e6
            wide_enough = shape * scale >= MIN_SPREAD_UNITS * PPM
            measure = "σ·중앙값"
        else:
            # 평균/√k ≥ 100 단위  ⇔  mean² · 1000 ≥ 100² · shape_milli (제곱해서 정수로 비교한다)
            wide_enough = scale * scale * 1000 >= MIN_SPREAD_UNITS * MIN_SPREAD_UNITS * shape
            measure = "평균/√k"
        if not wide_enough:
            raise ConfigError(
                f"{name}.{pid}: 퍼짐({measure})이 {MIN_SPREAD_UNITS} 단위 미만이다 — 값이 몇 개 정수로 뭉개진다"
            )


def _check_beta_shape(name: str, kappa_milli: int, by_persona: Mapping[str, int]) -> None:
    lo, hi = _BETA_SHAPE_NANO
    for pid, mu_ppm in by_persona.items():
        for label, nano in (("α", mu_ppm * kappa_milli), ("β", (PPM - mu_ppm) * kappa_milli)):
            if not lo <= nano <= hi:
                raise ConfigError(
                    f"{name}.{pid}: Beta {label} 가 검증 범위 [0.3, 100] 밖이다 (μκ 를 확인한다)"
                )


# 공개 메시지에 싣는 실험 파일 표기. 호출자가 준 경로는 싣지 않는다 — 파일 이름에 숨은 이름이 들어갈 수 있다.
EXPERIMENT_LABEL = "지정한 실험 설정 파일"


def public_label(path: str | os.PathLike[str] | None) -> str:
    """공개 오류 메시지에 싣는 config 이름. 기본 경로는 저장소 상대 이름, 실험 파일은 `EXPERIMENT_LABEL` 이다."""
    return CONFIG_NAME if path is None or _is_default(path) else EXPERIMENT_LABEL


def _is_default(path: str | os.PathLike[str]) -> bool:
    return Path(os.fspath(path)).resolve() == CONFIG_PATH.resolve()


def load(path: str | os.PathLike[str] | None = None) -> GenerationConfig:
    """config 를 읽는다. 오류 메시지에는 준 경로를 그대로 싣는다 — 공개 경계는 이 예외를 `__cause__` 로만 둔다."""
    name = CONFIG_NAME if path is None or _is_default(path) else os.fspath(path)
    path = CONFIG_PATH if path is None else Path(os.fspath(path))
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as error:
        raise ConfigError(f"{name} 를 읽지 못했다: {error.strerror or type(error).__name__}") from error
    try:
        return parse(text)
    except ConfigError as error:
        raise ConfigError(f"{name}: {error}") from error


_ACTIVE: GenerationConfig | None = None
# _ACTIVE 를 읽은 실험 파일의 절대 경로. None 이면 기본 경로(CONFIG_PATH)에서 읽었다.
_ACTIVE_PATH: Path | None = None

_T = TypeVar("_T")


def active() -> GenerationConfig:
    """이 프로세스에서 지금 고른 생성 config. 아무것도 고른 적이 없으면 기본 경로를 한 번 읽어 캐시한다.

    계약: 활성 세계가 있는 동안 config 는 바뀌지 않는다. 바꾸는 길은 `switch` 하나이고, 그것을 부르는
    `api.init`·`api.load_state` 는 성공하면 활성 세계도 함께 바꾼다.
    """
    global _ACTIVE, _ACTIVE_PATH
    if _ACTIVE is None:
        _ACTIVE, _ACTIVE_PATH = load(), None
    return _ACTIVE


def switch(path: str | os.PathLike[str] | None, action: Callable[[], _T]) -> _T:
    """`path`(None 이면 기본 경로)의 config 로 바꾸고 `action` 을 부른다. 성공하면 그 선택을 유지하고,
    `action` 이 예외를 내면 이전 선택으로 되돌린 뒤 그 예외를 다시 낸다.

    `action` 은 새 config 아래에서 활성 세계를 바꾸는 일(`api.init`·`api.load_state`)이다. config 와 세계가
    함께 바뀌거나 함께 그대로 남게 하려고 선택과 확정을 한 호출에 묶었다.

    읽기 규칙: 기본 경로는 프로세스에서 한 번 읽고 캐시한다(파일을 고쳐도 새 프로세스에서만 반영). 실험 파일은
    고를 때마다 다시 읽는다 — 같은 파일을 덮어쓰며 값을 바꿔 가는 실험이 옛 값으로 돌지 않게 한다.

    Raises:
        ConfigError: 파일을 읽을 수 없거나 계약을 어겼다. 이때 선택은 바뀌지 않고 `action` 도 부르지 않는다.
    """
    global _ACTIVE, _ACTIVE_PATH
    previous = (_ACTIVE, _ACTIVE_PATH)
    if path is None or _is_default(path):
        if _ACTIVE is None or _ACTIVE_PATH is not None:
            _ACTIVE, _ACTIVE_PATH = load(), None
    else:
        wanted = Path(os.fspath(path)).resolve()
        _ACTIVE, _ACTIVE_PATH = load(path), wanted
    try:
        return action()
    except BaseException:
        _ACTIVE, _ACTIVE_PATH = previous
        raise
