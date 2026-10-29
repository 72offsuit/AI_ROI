"""고객 한 명의 정체(Persona + Hidden Trait)를 만든다 — `DR-S2-persona-mix` · `DR-S2-trait-sampling`.

결합 방식은 J2 다: 페르소나를 먼저 뽑고, Trait 마다 그 페르소나의 분포에서 독립으로 한 번씩 뽑는다.
난수 열쇠는 (seed, customer_id, 용도, day = `rng.GENERATION_DAY`) 뿐이라 `num_customers`·`profile`·가입일과 무관하다.
그래서 고객을 추가해도 기존 고객이 그대로이고, Trait 하나의 모수를 바꿔도 다른 Trait 은 바뀌지 않는다.
"""

from __future__ import annotations

from src.simulator._internal import traits
from src.simulator._internal.genconfig import GenerationConfig
from src.simulator._internal.rng import GENERATION_DAY, Stream

PERSONA_PURPOSE = "persona"
SIGNUP_PURPOSE = "signup"
TRAIT_PURPOSE_PREFIX = "trait:"


def generate(seed: int, customer_id: str, config: GenerationConfig) -> tuple[str, dict[str, int]]:
    """(persona id, {Trait 이름: 정수 값}). 같은 입력이면 어느 판·플랫폼에서도 같은 값이다."""
    tables = traits.tables(config)
    index = Stream(seed, customer_id, PERSONA_PURPOSE, GENERATION_DAY).weighted(config.ratios)
    persona = config.personas[index].id
    values = {
        spec.name: traits.draw(
            Stream(seed, customer_id, TRAIT_PURPOSE_PREFIX + spec.name, GENERATION_DAY),
            tables[spec.name][persona],
        )
        for spec in config.traits
    }
    return persona, values


def signup_day(seed: int, customer_id: str, persona_id: str, config: GenerationConfig) -> int:
    """가입일 번호(calendar_start 기준). 범위가 없는 페르소나는 0 — `DR-S3-p6-signup`.

    열쇠에 profile 이 없어 같은 seed 면 프로파일이 달라도 같은 날이다. 페르소나·Trait 추첨과 독립이다.
    """
    span = next(p.signup_day_range for p in config.personas if p.id == persona_id)
    if span is None:
        return 0
    return Stream(seed, customer_id, SIGNUP_PURPOSE, GENERATION_DAY).between(*span)
