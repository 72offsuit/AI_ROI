"""공개 Uplift 실험 데이터 외부 검증 — Hillstrom 재검 · Lenta (#217 3부, DR-217-uplift-tuning).

처치 · 결과 · 특성 · seed 는 결정 기록에 **결과 전에** 고정한 값 그대로다(``BENCHMARKS``). 실행 루프와 같은
``evaluate_on_benchmark``(= ``evaluate_uplift_models``)를 부르므로 규제 격자 · Validation 선택 규칙도 같다.
결과를 보고 여기 값을 바꾸지 않는다 — 바꾸면 결정 기록에 사유와 함께 적는다.

데이터 파일은 저장소에 두지 않는다. 내려받은 경로를 인자로 받고, 집계 지표만 JSON 으로 쓴다(고객별 값 없음).

    python -I src/decision/uplift_benchmarks.py --hillstrom <hillstorm_no_indices.csv.gz> \\
        --lenta <lenta_dataset.csv.gz> --out docs/research/computed/uplift_external.json
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from pathlib import Path
from typing import Any

#: 원자료 공변량 8개 그대로 — 가공 · 선택 없음(DR-217-uplift-tuning 「외부 검증」).
HILLSTROM_FEATURES = ("recency", "history_segment", "history", "mens", "womens", "zip_code", "newbie", "channel")
LENTA_TREATMENT, LENTA_OUTCOME = "group", "response_att"

#: 사전 고정 — id · 데이터 · 처치 열 · 대조 값 · 처치 값(None = 대조가 아닌 전부) · 결과 · seed.
BENCHMARKS: tuple[dict[str, Any], ...] = (
    {"id": "hillstrom_any_email_visit", "dataset": "hillstrom", "treatment_col": "segment",
     "control_value": "No E-Mail", "treatment_value": None, "outcome": "visit", "seeds": (0, 1, 2)},
    {"id": "hillstrom_mens_conversion", "dataset": "hillstrom", "treatment_col": "segment",
     "control_value": "No E-Mail", "treatment_value": "Mens E-Mail", "outcome": "conversion", "seeds": (0, 1, 2)},
    {"id": "lenta_response_att", "dataset": "lenta", "treatment_col": LENTA_TREATMENT,
     "control_value": "control", "treatment_value": "test", "outcome": LENTA_OUTCOME, "seeds": (0,)},
)


def load_hillstrom(path) -> tuple[Any, list[str]]:
    """Hillstrom(scikit-uplift 미러) — ``segment`` · ``visit`` · ``conversion`` 과 공변량 8개."""
    import pandas as pd

    frame = pd.read_csv(path)
    missing = [c for c in (*HILLSTROM_FEATURES, "segment", "visit", "conversion") if c not in frame.columns]
    if missing:
        raise ValueError(f"Hillstrom 파일에 열이 없다: {missing}")
    return frame, list(HILLSTROM_FEATURES)


def load_lenta(path) -> tuple[Any, list[str]]:
    """Lenta — ``group``(test/control) · ``response_att`` 와 나머지 원자료 열 전부(가공 없음)."""
    import pandas as pd

    frame = pd.read_csv(path)
    missing = [c for c in (LENTA_TREATMENT, LENTA_OUTCOME) if c not in frame.columns]
    if missing:
        raise ValueError(f"Lenta 파일에 열이 없다: {missing}")
    return frame, [c for c in frame.columns if c not in (LENTA_TREATMENT, LENTA_OUTCOME)]


def _row(model_row: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in model_row.items() if k != "qini_curve"}


def summarize(out: dict[str, Any], seconds: float) -> dict[str, Any]:
    """``evaluate_on_benchmark`` 결과 → 게시용 집계(고객 ID · 곡선 제외)."""
    selection = out["best_method_selection"]
    current = out["tuning_report"]["test_current_regularization"]
    return {
        "n": out["n"], "n_train": out["n_train"], "n_test": out["n_test"],
        "n_validation": selection.get("n_validation"),
        "arms": out["arms"], "ate_T1": out["ate"]["T1"], "outcome_kind": out["outcome_kind"],
        "chosen_method": selection["best_method"], "chosen_base_learner": selection["base_learner"],
        "chosen_is_current": selection["base_learner_is_current"],
        "validation_grid": selection["tuning"]["grid"], "configs": selection["tuning"]["configs"],
        "validation_reasons": selection["tuning"]["reasons"],
        "test": {row["name"]: _row(row) for row in out["models"]},
        "test_current_regularization": None if current is None else _row(current),
        "feature_screening": out["feature_screening"]["train_dropped"],
        "seconds": round(seconds, 1),
    }


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def run(paths: dict[str, Path], threads: int | None = 1) -> dict[str, Any]:
    """``paths`` 에 있는 데이터의 사전 고정 분석을 전부 돈다. 없는 데이터는 not_run(사유)."""
    import numpy as np
    import pandas as pd
    import sklearn

    from src.decision import uplift

    previous, uplift.N_THREADS = uplift.N_THREADS, threads  # 끝나면 되돌린다(실행 루프 기본값을 남기지 않는다)
    try:
        loaders = {"hillstrom": load_hillstrom, "lenta": load_lenta}
        frames = {name: loaders[name](path) for name, path in paths.items()}
        results: dict[str, Any] = {}
        for spec in BENCHMARKS:
            if spec["dataset"] not in frames:
                results[spec["id"]] = {"status": "not_run", "reason": f"{spec['dataset']} 경로가 주어지지 않았다"}
                continue
            frame, features = frames[spec["dataset"]]
            runs = {}
            for seed in spec["seeds"]:
                started = time.perf_counter()
                out = uplift.evaluate_on_benchmark(frame, features, spec["treatment_col"], spec["outcome"],
                                                   control_value=spec["control_value"],
                                                   treatment_value=spec["treatment_value"], seed=seed)
                runs[str(seed)] = summarize(out, time.perf_counter() - started)
            results[spec["id"]] = {"status": "ok", "spec": {k: v for k, v in spec.items() if k != "seeds"},
                                   "seeds": list(spec["seeds"]), "n_features": len(features), "runs": runs}
    finally:
        uplift.N_THREADS = previous
    return {
        "decision_record": "docs/decisions/DR-217-uplift-tuning.md",
        "procedure": "evaluate_on_benchmark — 실행 루프와 같은 분할 · 규제 격자 · Validation Qini 선택(Test 미사용)",
        "base_learner_current": dict(uplift.BASE_LEARNER), "tuning": json.loads(json.dumps(dict(uplift.TUNING),
                                                                                             default=dict)),
        "datasets": {name: {"file": Path(path).name, "bytes": Path(path).stat().st_size, "sha256": _sha256(Path(path)),
                            "rows": int(len(frames[name][0]))} for name, path in paths.items()},
        "environment": {"python": sys.version.split()[0], "numpy": np.__version__, "pandas": pd.__version__,
                        "sklearn": sklearn.__version__, "openmp_threads": threads},
        "results": results,
        "note": "공개 실험 데이터 외부 검증 — 우리 시뮬레이션 결과가 아니다. 집계값만(고객별 값 없음).",
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--hillstrom", type=Path)
    parser.add_argument("--lenta", type=Path)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--threads", type=int, default=1, help="OpenMP 스레드 상한(0 = 제한 없음). 기록에 남는다")
    args = parser.parse_args(argv)
    paths = {name: p for name, p in (("hillstrom", args.hillstrom), ("lenta", args.lenta)) if p is not None}
    if not paths:
        parser.error("--hillstrom 또는 --lenta 중 하나는 필요하다")
    report = run(paths, threads=None if args.threads == 0 else args.threads)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, ensure_ascii=False, indent=2, default=str) + "\n", encoding="utf-8")
    print(f"wrote {args.out}")
    return 0


if __name__ == "__main__":  # python -I 로 돌 때 — 저장소 루트를 직접 넣는다(현재 폴더를 sys.path 에 두지 않는다)
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    raise SystemExit(main())
