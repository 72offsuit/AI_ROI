"""NFR-01 재현성 — feature · strategy · experiment 버전을 **소스에서** 잰다 (#214).

PRD NFR-01 은 ``service_version · simulator_version · customer_seed · random_seed · feature_version ·
model_version · strategy_version · experiment_version`` 을 기록하라고 한다. 앞의 넷과 model_version 은
실행 기록(`run_meta.provenance` · 시뮬레이터 관측값 · `model_store`)이 이미 갖고 있다. 이 모듈은 나머지
셋을 정한다.

## 왜 손으로 올리는 번호가 아니라 소스 해시인가

``FEATURE_VERSION = "v2"`` 같은 상수는 코드를 고치고 번호를 안 올리면 **같은 이름의 다른 Feature** 가
된다. 저장한 모델을 불러올 때 이 값을 대조하므로(``model_store.load_models``), 틀린 같음이 가장 위험하다.
정의를 담은 파일의 바이트로 재면 한 글자만 바뀌어도 버전이 바뀐다 — 주석만 고쳐도 바뀌는 것은
감수한다(틀린 다름은 다시 학습하면 되지만, 틀린 같음은 조용히 다른 모델을 평가한다).

파일을 읽지 못하면 ``None`` 이다. 추측한 값을 넣지 않는다.
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any, Mapping

REPO_ROOT = Path(__file__).resolve().parents[2]

#: Feature 값을 정하는 소스 — 스프린트 Feature 테이블과 재방문 입력 의미(#256).
FEATURE_SOURCES = ("src/decision/features/sprint_table.py", "src/decision/return_visit.py")
#: 대상 · 처치 · 예산을 고르는 소스 — S0~S5 규칙과 S5 최적화.
STRATEGY_SOURCES = ("src/decision/strategies.py", "src/decision/optimize.py")
#: 실험 설계(규모 · seed · 기간) — config 한 곳.
EXPERIMENT_SOURCES = ("config/experiment_config.yaml",)

DEFINITION = ("feature · strategy · experiment 버전 = 정의 소스 파일(경로 + 바이트)의 SHA-256 앞 12자리 "
              "(src/decision/versions.py). 파일을 읽지 못하면 null")


def source_digest(paths: tuple[str, ...], root: Path = REPO_ROOT) -> str | None:
    """경로 순서대로 ``경로 \\0 바이트 \\0`` 를 이어 SHA-256. 하나라도 없으면 None."""
    digest = hashlib.sha256()
    for rel in paths:
        path = root / rel
        try:
            data = path.read_bytes()
        except OSError:
            return None
        digest.update(rel.encode("utf-8") + b"\0" + data + b"\0")
    return digest.hexdigest()


def _version(prefix: str, paths: tuple[str, ...], root: Path = REPO_ROOT) -> str | None:
    digest = source_digest(paths, root)
    return None if digest is None else f"{prefix}-{digest[:12]}"


def feature_version(root: Path = REPO_ROOT) -> str | None:
    return _version("features", FEATURE_SOURCES, root)


def strategy_version(root: Path = REPO_ROOT) -> str | None:
    return _version("strategies", STRATEGY_SOURCES, root)


def experiment_version(root: Path = REPO_ROOT) -> str | None:
    return _version("experiment", EXPERIMENT_SOURCES, root)


def versions_record(*, service_version: Any = None, simulator_version: Any = None, customer_seed: Any = None,
                    random_seed: Any = None, model_versions: Mapping[str, Any] | None = None,
                    root: Path = REPO_ROOT) -> dict[str, Any]:
    """NFR-01 의 8개 키를 한 곳에 모은다. 모르는 값은 None 으로 둔다(0 · 빈 문자열로 채우지 않는다)."""
    return {
        "service_version": service_version,
        "simulator_version": simulator_version,
        "customer_seed": customer_seed,
        "random_seed": random_seed,
        "feature_version": feature_version(root),
        "model_version": dict(model_versions) if model_versions else None,
        "strategy_version": strategy_version(root),
        "experiment_version": experiment_version(root),
        "sources": {"feature": list(FEATURE_SOURCES), "strategy": list(STRATEGY_SOURCES),
                    "experiment": list(EXPERIMENT_SOURCES)},
        "definition": DEFINITION,
    }
