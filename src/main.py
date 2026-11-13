"""main CLI — ``python src/main.py --mode train|uplift|optimize|evaluate|full`` (이슈 #206).

SRS SYS-004 · PRD §73. **디스패처다 — 계산하지 않는다.** 실행 루프는
``src.orchestration.run_sprint.run()`` 이고, 모델·세그먼트·전략·최적화는 ``src.decision.*`` 의 기존 함수다.
모드는 두 가지만 정한다.

  1. ``run()`` 의 단계 중 무엇을 실행하나(``MODES[...].stages``). 나머지 단계는 시도하지 않고
     ``not_run``(실행 범위 밖)으로 적힌다 — 결과 JSON 7종은 모드와 무관하게 늘 같은 모양으로 나온다.
  2. 실행 뒤 무엇을 더 쓰나 — 고객별 uplift 점수 CSV · 세그먼트별 예산 배분 JSON. 값은 전부 기존 함수
     (``segments.uplift_score`` · ``assign_quadrants`` · ``assign_segments`` · ``strategies.plan("S5")``)의
     결과를 옮겨 적은 것이다.

모드 사이에 넘기는 것 — **저장한 모델**(#214). 학습한 Churn · Uplift · CLV 모델을 ``models/<run_id>/`` 에
(ML-008 메타데이터와 함께), Feature · 라벨을 ``data/processed/<run_id>/`` 에(FS-001/002) 기본으로 남긴다
(``--no-persist`` 로 끈다). 다음 실행은 ``--load-models models/<run_id>`` 로 그 모델을 **다시 학습하지 않고**
불러와 새 seed 데이터로 평가만 할 수 있다 — Final Holdout(GATE 4)의 전제다. 저장 당시 Feature 정의
(``feature_version``)가 지금 코드와 다르면 시뮬레이션 전에 멈춘다(종료 코드 6). 시뮬레이션 세계는 넘기지
않는다 — 모든 모드가 시뮬레이션부터 다시 돈다(같은 seed · 고객 수 · 프로파일 · config 면 같은 세계).

격리: ``src.simulator`` · ``src.diagnostics`` 를 import 하지 않는다. 시뮬레이터는 ``run_sprint`` 가 공개 api 로만
부른다(``tests/test_orchestration_main_cli.py`` 가 AST 로 고정). 결정 기록: ``docs/decisions/DR-206-main-cli-config.md``.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib
import json
import math
import shutil
import sys
import textwrap
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Mapping

REPO_ROOT = Path(__file__).resolve().parents[1]
if __package__ in (None, ""):  # `python src/main.py` — sys.path[0] 이 src/ 라 `import src.…` 가 되지 않는다
    sys.path[0] = str(REPO_ROOT)

from src.measurement.errors import ConfigError  # noqa: E402 — 위 경로 보정 뒤에 import 한다

KST = timezone(timedelta(hours=9), "KST")
UPLIFT_SCORES = "uplift_scores.csv"
BUDGET_ALLOCATION = "budget_allocation.json"
MANIFEST = "main_cli.json"
NOT_RUN_EXIT = 3  # 2 는 argparse 의 인자 오류 코드다 — 겹치지 않게 둔다
CONFIG_FILES = ("config/model_config.yaml", "config/experiment_config.yaml")

# ── 모드 ─────────────────────────────────────────────────────────────────────
# 단계 이름은 src/orchestration/run_sprint.py 의 `log.stage(...)` 이름이다. 이름이 바뀌어 여기 적힌 단계가
# 실행 기록에 없으면 main_cli.json 의 `stages.unknown_selected` 에 남고 종료 코드 1 이다.

TRAIN_STAGES = frozenset({
    "simulate_warmup", "read_events_t1", "rct_assign", "features_t1", "simulate_rct",
    "read_events_t2", "outcomes_t1", "training_set", "churn", "uplift", "clv",
})
SCORING_STAGES = frozenset({"features_t2", "scores_t2", "segments"})
EVALUATION_STAGES = frozenset({"ab_test", "features_t2", "snapshot_t2", "strategy_S0", "churn_temporal_holdout"})


@dataclass(frozen=True)
class Mode:
    name: str
    does: str
    stages: frozenset[str] | None   # None = run() 전 구간 (python -m src.orchestration.run_sprint 와 같다)
    writes: tuple[str, ...]          # run() 의 JSON 7종 외에 main.py 가 더 쓰는 파일
    budget: str                      # --budget: required · optional · rejected


MODES: dict[str, Mode] = {
    "train": Mode(
        "train",
        "탐색 RCT 로 학습 데이터를 만들고 Churn(4 모델 교차검증 · SHAP) · Uplift(메타러너 3종) · CLV 를 "
        "학습·평가한다 → churn_eval · uplift_eval · clv_eval",
        TRAIN_STAGES, (), "rejected"),
    "uplift": Mode(
        "uplift",
        "train + t2 시점 Feature 로 고객별 CATE(T1~T4)를 점수화하고 4분면 · 세그먼트를 매긴다 → segments · "
        f"{UPLIFT_SCORES}",
        TRAIN_STAGES | SCORING_STAGES, (UPLIFT_SCORES,), "rejected"),
    "optimize": Mode(
        "optimize",
        "uplift + --budget 예산으로 S5 최적화 배정(strategies.plan) · What-if 50/100/200% → 세그먼트별 배분 · "
        f"기대 ROI ({BUDGET_ALLOCATION}). 전략 분기 시뮬레이션은 하지 않는다(계획 단계)",
        TRAIN_STAGES | SCORING_STAGES | {"what_if"}, (UPLIFT_SCORES, BUDGET_ALLOCATION), "required"),
    "evaluate": Mode(
        "evaluate",
        "train + 탐색 RCT A/B 분석(SRM · 검정력) + t2 이후 무처치(S0) 분기로 churn 모델 시간 홀드아웃 1회 평가 → "
        "ab_test · churn_eval.temporal_holdout. S1~S5 전략 비교는 full 에서",
        TRAIN_STAGES | EVALUATION_STAGES, (), "rejected"),
    "full": Mode(
        "full",
        "전 구간 — 위 전부 + S0~S5 전략 분기 시뮬레이션 · S1 대비 ROI (run_sprint 와 같은 단계)",
        None, (UPLIFT_SCORES, BUDGET_ALLOCATION), "optional"),
}

HANDOFF = (
    "저장한 모델을 넘긴다(#214) — 학습한 모델은 models/<run_id>/ 에, Feature · 라벨은 data/processed/<run_id>/ "
    "에 남는다(--no-persist 로 끈다). --load-models models/<run_id> 로 다시 학습하지 않고 불러와 평가만 한다. "
    "시뮬레이션 세계는 넘기지 않는다 — 같은 seed · 고객 수 · 프로파일 · config SHA-256 이면 같은 세계다"
)
NOT_PERSISTED = (
    "SHAP 요약 그림(png) — churn_eval.shap_top 의 수치만 있다",
    "시뮬레이션 세계 — 모든 모드가 시뮬레이션부터 다시 돈다",
)
EXIT_MODEL_LOAD = 6  # --load-models 폴더를 쓸 수 없다 (run_sprint.ModelLoadError.exit_code 와 같다)


def _epilog() -> str:
    def wrap(text: str, head: str, indent: int) -> list[str]:
        return textwrap.wrap(text, width=72, initial_indent=head, subsequent_indent=" " * indent)

    lines = ["모드 (무엇을 하고 무엇을 더 쓰나):"]
    for mode in MODES.values():
        budget = {"required": " · --budget 필수", "optional": " · --budget 선택", "rejected": ""}[mode.budget]
        lines += wrap(mode.does + budget, f"  {mode.name:<9} ", 12)
    lines += [
        "",
        "입력 (모든 모드): seed · 고객 수 · 프로파일로 시뮬레이터 공개 api 가 새 세계를 만든다. 기본값은",
        "  config/experiment_config.yaml, 모델 하이퍼파라미터 · 세그먼트 경계는 config/model_config.yaml.",
        "  이전 실행의 산출물을 읽지 않는다.",
        "",
        "출력 (모든 모드):",
        "  <results-root>/sprint-v0/<run_id>/  run_meta · churn_eval · clv_eval · uplift_eval · segments ·",
        "      strategy_comparison · ab_test (.json 7종 — 범위 밖 단계는 status=not_run 과 사유) + latest 링크",
        f"      + {MANIFEST} (모드 · 실행한 단계 · 산출물 상태) + 모드별 파일({UPLIFT_SCORES} · {BUDGET_ALLOCATION})",
        "      results-root 기본: full 은 results/ (대시보드가 읽는 곳), 나머지는 results/cli/<mode>/",
        "      — 부분 실행이 대시보드의 latest 를 덮지 않게 한다",
        "  <out>/raw/{main,S0..S5}/  시뮬레이터 이벤트 · <out>/assignments/  배정표.  out 기본: data/sprint/<run_id>/",
        "",
        *wrap(HANDOFF + ".", "모드 사이: ", 2),
        *wrap(" · ".join(NOT_PERSISTED), "저장하지 않는 것: ", 2),
        "",
        "종료 코드: 0 실행한 단계 전부 ok · 1 실패한 단계(또는 산출물) 있음 · 2 인자 오류(argparse) ·",
        "  3 실패는 없지만 실행 범위 안에 not_run 이 있음(예: 라벨이 한 값뿐) ·",
        "  4 --require-clean 인데 커밋 전 변경이 있음(시작 전에 멈춤) · 5 config 오류 ·",
        "  6 --load-models 폴더를 쓸 수 없음(없음 · 파일 변조 · Feature 정의 변경, 시작 전에 멈춤).",
        "  모델 · Feature 저장이 실패해도 1 이다(조용히 넘어가지 않는다)",
        "",
        "예:  python src/main.py --mode train --customers 2000 --profile small",
        "     python src/main.py --mode optimize --budget 50000000",
    ]
    return "\n".join(lines)


def build_parser() -> argparse.ArgumentParser:
    """인자 기본값을 비워 둔다 — 실제 기본값은 실행 시 config 에서 읽는다(--help 는 의존성 없이 돈다)."""
    parser = argparse.ArgumentParser(
        prog="python src/main.py",
        description="AI 리텐션 시스템 main CLI (SRS SYS-004 · PRD §73) — 실행 루프(run_sprint)와 의사결정 모듈을 "
                    "모드별로 부르는 디스패처.",
        epilog=_epilog(),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--mode", required=True, choices=list(MODES), help="실행할 범위 (아래 표)")
    parser.add_argument("--budget", type=int, default=None, metavar="KRW",
                        help="S5 · What-if 예산(원, 변동비 — 캠페인 고정비 제외) — optimize 필수, full 선택"
                             "(S2~S5 예산. 없으면 C_rule = S1 계획 비용, S1 이 없으면 S2~S5 not_run)")
    parser.add_argument("--seed", type=int, default=None,
                        help="기본: config/experiment_config.yaml holdout.development_seed")
    parser.add_argument("--customers", type=int, default=None, help="기본: config/experiment_config.yaml run.num_customers")
    parser.add_argument("--profile", default=None, help="기본: config/experiment_config.yaml run.profile")
    parser.add_argument("--out", type=Path, default=None, help="시뮬레이터 출력 폴더(새 폴더). 기본: data/sprint/<run_id>/")
    parser.add_argument("--results-root", type=Path, default=None,
                        help="기본: full 은 results/, 나머지는 results/cli/<mode>/")
    parser.add_argument("--warmup-days", type=int, default=None,
                        help="기본: --profile 이 config run.profile 이면 config run.warmup_days, "
                             "아니면 프로파일 권장값(data_spec §2.2)")
    parser.add_argument("--cv-folds", type=int, default=None,
                        help="churn 교차검증 fold 수 덮어쓰기 (기본: config/model_config.yaml churn.cv_folds)")
    parser.add_argument("--max-train-rows", type=int, default=None,
                        help="churn 학습·CV 표본 상한 — 클래스 비율 유지 추출 (기본: 전원)")
    parser.add_argument("--run-id", default=None, help="기본: SP-<날짜>-<시각>-<난수>")
    parser.add_argument("--require-clean", action="store_true",
                        help="저장소에 커밋 전 변경(추적 파일 변경 · .gitignore 밖 새 파일)이 있으면 시뮬레이션 전에 "
                             "멈춘다(종료 코드 4). 봉인 실행(GATE 2 Baseline)은 이 옵션으로 돌린다 (#262)")
    parser.add_argument("--models-root", type=Path, default=None,
                        help="학습한 모델을 <경로>/<run_id>/ 에 저장(ML-008). 기본: models/")
    parser.add_argument("--feature-store-root", type=Path, default=None,
                        help="Feature · 라벨을 <경로>/<run_id>/ 에 parquet 로 저장(FS-001/002). 기본: data/processed/")
    parser.add_argument("--no-persist", action="store_true", help="모델 · Feature 를 저장하지 않는다")
    parser.add_argument("--load-models", type=Path, default=None, metavar="DIR",
                        help="저장된 모델 폴더(models/<run_id>) — 다시 학습하지 않고 불러와 평가만 한다(GATE 4 전제). "
                             "못 쓰면 시작 전에 멈춘다(종료 코드 6)")
    return parser


def _check_budget(parser: argparse.ArgumentParser, mode: Mode, budget: int | None) -> None:
    if budget is None:
        if mode.budget == "required":
            parser.error(f"--mode {mode.name} 는 --budget <KRW> 가 필요하다 (SRS SYS-004)")
        return
    if mode.budget == "rejected":
        parser.error(f"--budget 은 optimize · full 에서만 쓴다 — --mode {mode.name} 는 예산을 쓰지 않는다")
    if budget <= 0:
        parser.error("--budget 은 양의 정수(원)여야 한다")


# ── 산출물 ───────────────────────────────────────────────────────────────────


class Unavailable(Exception):
    """산출물을 만들 근거가 없다 — not_run 으로 적는다. 빈 파일 · 0 으로 대신하지 않는다."""


def _decision_attr(module: str, name: str) -> Any:
    try:
        loaded = importlib.import_module(module)
    except ImportError as error:
        raise Unavailable(f"{module} 를 import 할 수 없다: {error}") from error
    value = getattr(loaded, name, None)
    if value is None:
        raise Unavailable(f"{module}.{name} 가 없다")
    return value


def _scores(capture: Mapping[str, Any], keys: tuple[str, ...]) -> Mapping[str, Any]:
    scores = capture.get("scores") or {}
    missing = [k for k in keys if scores.get(k) is None]
    if missing:
        raise Unavailable(f"점수가 없다: {missing} — 원인은 run_meta.json stages 의 churn · uplift · clv · scores_t2")
    return scores


def uplift_table(scores: Mapping[str, Any]) -> Any:
    """고객별 점수 표 — 값은 전부 의사결정 함수의 결과다. 세그먼트는 run() 의 segments 단계와 같은 호출이다."""
    import pandas as pd

    uplift_score = _decision_attr("src.decision.segments", "uplift_score")
    assign_quadrants = _decision_attr("src.decision.segments", "assign_quadrants")
    assign_segments = _decision_attr("src.decision.segments", "assign_segments")
    prd_ids = _decision_attr("src.decision.segments", "SEGMENT_PRD_ID")
    churn_p, cate, clv = scores["churn_p"], scores["cate"], scores["clv"]
    uplift = uplift_score(cate)
    arm = pd.Series(pd.NA, index=cate.index, dtype="object")
    known = cate.notna().any(axis=1)
    arm[known] = cate[known].astype(float).idxmax(axis=1)  # uplift_score(최대 CATE)를 낸 처치
    table = pd.DataFrame(index=churn_p.index)
    table["churn_p"] = churn_p.astype(float)
    table["clv"] = clv.reindex(table.index).astype(float)
    for column in cate.columns:
        table[f"cate_{column}"] = cate[column].reindex(table.index).astype(float)
    table["uplift_score"] = uplift.reindex(table.index)
    table["uplift_arm"] = arm.reindex(table.index)
    table["quadrant"] = assign_quadrants(uplift, churn_p).reindex(table.index)
    table["segment"] = assign_segments(churn_p, cate, clv).reindex(table.index)
    table["segment_prd_id"] = table["segment"].map(prd_ids)
    table.index.name = "customer_id"
    return table


def _read_json(path: Path) -> dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def write_uplift_scores(run_dir: Path, capture: Mapping[str, Any]) -> dict[str, Any]:
    table = uplift_table(_scores(capture, ("churn_p", "cate", "clv")))
    path = run_dir / UPLIFT_SCORES
    table.to_csv(path, encoding="utf-8")  # 결손은 빈 칸 — 0 으로 채우지 않는다
    counts = {str(k): int(v) for k, v in table["segment"].value_counts().sort_index().items()}
    reported = {str(row.get("name")): row.get("n")
                for row in _read_json(run_dir / "segments.json").get("segments") or []}
    return {
        "status": "ok", "path": str(path), "rows": int(len(table)), "columns": ["customer_id", *table.columns],
        "segment_counts": counts,
        "quadrant_counts": {str(k): int(v) for k, v in table["quadrant"].value_counts().sort_index().items()},
        # run() 의 segments 단계(segment_stats)와 같은 호출인지 대조한다 — 다르면 어느 한쪽이 다른 점수를 썼다
        "consistent_with_segments_json": (counts == reported) if reported else None,
        "missing_values": "빈 칸 = 계산 불가(결손). 0 으로 채우지 않았다",
    }


def write_budget_allocation(run_dir: Path, capture: Mapping[str, Any]) -> dict[str, Any]:
    scores = _scores(capture, ("churn_p", "cate", "clv"))
    costs = capture.get("costs")
    if not costs:
        raise Unavailable("처치별 계획 비용이 없다 — run_meta.json cost_basis_reason")
    budget = capture.get("budget") or {}
    planning = budget.get("planning_budget_krw")
    if planning is None:
        raise Unavailable("예산을 정하지 못했다 — strategy_comparison.json budget")
    import pandas as pd  # 근거를 확인한 뒤에 — 근거가 없으면 의존성과 무관하게 not_run 이다

    plan = _decision_attr("src.decision.strategies", "plan")
    try:
        assignment = dict(plan("S5", scores, planning, costs))
    except Exception as error:
        if type(error).__name__ == "NotComputable":
            raise Unavailable(f"strategies.plan('S5') NotComputable: {error}") from error
        raise
    segments = _decision_attr("src.decision.segments", "assign_segments")(
        scores["churn_p"], scores["cate"], scores["clv"])
    prd_ids = _decision_attr("src.decision.segments", "SEGMENT_PRD_ID")
    frame = pd.DataFrame({"segment": segments})
    frame["treatment"] = pd.Series(assignment, dtype="object").reindex(frame.index)
    frame["planned_cost_krw"] = frame["treatment"].map({t: float(c) for t, c in costs.items()})
    targeted_all = frame[frame["treatment"].notna()]
    if targeted_all["planned_cost_krw"].isna().any():
        raise Unavailable("배정된 처치의 계획 비용이 없다 — 0 원으로 보지 않는다")
    total = float(targeted_all["planned_cost_krw"].sum())
    rows = []
    for name, group in frame.groupby("segment", sort=True):
        targeted = group[group["treatment"].notna()]
        spend = float(targeted["planned_cost_krw"].sum())
        rows.append({
            "segment": str(name), "prd_id": prd_ids.get(name),
            "n_customers": int(len(group)), "n_targeted": int(len(targeted)),
            "treatment_mix": {str(t): int(n) for t, n in targeted["treatment"].value_counts().sort_index().items()},
            "planned_spend_krw": spend, "share_of_spend": spend / total if total > 0 else None,
        })
    mix = {str(t): int(n) for t, n in targeted_all["treatment"].value_counts().sort_index().items()}
    comparison = _read_json(run_dir / "strategy_comparison.json")
    what_if = (comparison.get("what_if") or {}).get("rows") or []
    row = next((r for r in what_if if r.get("budget_krw") is not None
                and math.isclose(float(r["budget_krw"]), float(planning))), None)
    if row is None:
        what_if_stage = ((comparison.get("stages") or {}).get("what_if") or {})
        expected: dict[str, Any] = {"status": "not_run",
                                    "reason": what_if_stage.get("reason") or "What-if 결과에 이 예산의 행이 없다"}
    else:
        expected = {
            "status": "ok", "source": "strategy_comparison.json what_if (예산 100% 행)",
            **{k: row.get(k) for k in ("expected_roi", "expected_net_krw", "expected_gain_krw",
                                       "expected_saved_customers", "spend_krw", "target_count", "treatment_mix")},
            # 같은 해법(optimize)·같은 점수면 S5 배정과 같아야 한다 — 다르면 어느 한쪽이 다른 입력을 썼다
            "consistent_with_allocation": (row.get("target_count") == len(assignment)
                                           and (row.get("treatment_mix") or {}) == mix
                                           and math.isclose(float(row.get("spend_krw") or 0.0), total)),
        }
    payload = {
        "status": "ok",
        "budget_krw": float(planning),
        "budget_source": budget.get("source"),
        "method": "strategies.plan('S5') → optimize.optimize_budget — 다중선택 배낭 탐욕 근사(최적해 보장 없음, "
                  "DR-145). 기대 증분가치 = CATE × CLV × margin_rate",
        "cost_basis": "planning_costs = 처치 단가 + 메시지 비용 — 쿠폰 전량 사용 가정의 상한, 캠페인 고정비 제외. "
                      "실집행 비용이 아니다",
        "planning_costs_krw": {str(t): float(c) for t, c in costs.items()},
        "totals": {"n_customers": int(len(frame)), "n_targeted": int(len(targeted_all)), "treatment_mix": mix,
                   "planned_spend_krw": total, "unspent_krw": float(planning) - total,
                   "n_assigned_outside_segments": len(set(assignment) - set(frame.index))},
        "segments": rows,
        "expected": expected,
        "not_provided": [
            "세그먼트별 기대 ROI — 고객별 기대 증분가치를 돌려주는 의사결정 공개 함수가 없다. main.py 에서 다시 "
            "계산하면 strategies 의 로직 복제다(전체 기대 ROI 는 expected)",
        ],
    }
    path = run_dir / BUDGET_ALLOCATION
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    return {"status": "ok", "path": str(path), "budget_krw": float(planning), "n_targeted": int(len(targeted_all)),
            "planned_spend_krw": total, "expected_roi": expected.get("expected_roi"),
            "consistent_with_what_if": expected.get("consistent_with_allocation")}


WRITERS = {UPLIFT_SCORES: write_uplift_scores, BUDGET_ALLOCATION: write_budget_allocation}


def write_artifact(name: str, run_dir: Path, capture: Mapping[str, Any]) -> dict[str, Any]:
    try:
        return WRITERS[name](run_dir, capture)
    except Unavailable as reason:
        return {"status": "not_run", "reason": str(reason)}
    except Exception as error:  # noqa: BLE001 — 한 산출물의 실패가 기록을 막지 않는다
        return {"status": "failed", "reason": f"{type(error).__name__}: {error}"}


# ── 기록 · 요약 ──────────────────────────────────────────────────────────────


def _sha256(relative: str) -> str | None:
    path = REPO_ROOT / relative
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else None


def stage_report(mode: Mode, stages: list[Mapping[str, Any]]) -> dict[str, Any]:
    """실행 기록을 모드 기준으로 나눈다 — 범위 밖 not_run 과 범위 안 not_run 을 섞지 않는다."""
    selected = mode.stages
    in_scope = [s for s in stages if selected is None or s["name"] in selected]
    seen = {s["name"] for s in stages}
    return {
        "selected": "all" if selected is None else sorted(selected),
        "ok": [s["name"] for s in in_scope if s["status"] == "ok"],
        "failed": [{"name": s["name"], "reason": s["reason"]} for s in in_scope if s["status"] == "failed"],
        "not_run_in_scope": [{"name": s["name"], "reason": s["reason"]} for s in in_scope if s["status"] == "not_run"],
        "out_of_scope": [s["name"] for s in stages if selected is not None and s["name"] not in selected],
        "unknown_selected": sorted(set(selected or ()) - seen),
    }


def exit_code(report: Mapping[str, Any], outputs: Mapping[str, Mapping[str, Any]]) -> int:
    statuses = [o.get("status") for o in outputs.values()]
    if report["failed"] or report["unknown_selected"] or "failed" in statuses:
        return 1
    if report["not_run_in_scope"] or "not_run" in statuses:
        return NOT_RUN_EXIT
    return 0


def _mirror_into_latest(run_dir: Path, names: list[str]) -> None:
    """`latest` 가 링크가 아니라 사본이면(심링크 불가 환경) 나중에 쓴 파일도 사본에 둔다."""
    latest = run_dir.parent / "latest"
    if latest.is_dir() and not latest.is_symlink():
        for name in names:
            if (run_dir / name).is_file():
                shutil.copyfile(run_dir / name, latest / name)


def summary_lines(mode: Mode, run_dir: Path, manifest: Mapping[str, Any]) -> list[str]:
    """사람이 읽는 요약 — 결과 JSON 에서 옮긴다. 없는 값은 '—' 로 적는다(0 으로 적지 않는다)."""
    def fmt(value: Any, digits: int = 3) -> str:
        return "—" if value is None else (f"{value:.{digits}f}" if isinstance(value, float) else str(value))

    report = manifest["stages"]
    lines = [f"--mode {mode.name} · run_id {manifest['run_id']} · 종료 코드 {manifest['exit_code']}",
             f"  결과 폴더  {run_dir}",
             f"  단계       ok {len(report['ok'])} · 범위 안 not_run {len(report['not_run_in_scope'])} · "
             f"failed {len(report['failed'])} · 범위 밖 {len(report['out_of_scope'])}"]
    for stage in report["failed"] + report["not_run_in_scope"]:
        lines.append(f"    ! {stage['name']}: {stage['reason']}")
    churn = _read_json(run_dir / "churn_eval.json")
    if churn.get("status") == "ok":
        models = " · ".join(f"{m.get('name')} {fmt(((m.get('cv') or {}).get('roc_auc') or {}).get('mean'))}"
                            for m in churn.get("models") or [])
        lines.append(f"  churn      CV ROC-AUC {models} · 확정 {churn.get('best_proposed')}")
        holdout = churn.get("temporal_holdout")
        if isinstance(holdout, Mapping):
            lines.append(f"             시간 홀드아웃 {holdout.get('name')} ROC-AUC {fmt(holdout.get('roc_auc'))} "
                         f"(n={holdout.get('n_test')})")
    uplift = _read_json(run_dir / "uplift_eval.json")
    if uplift.get("status") == "ok":
        lines.append(f"  uplift     학습 방법 {uplift.get('fitted_method')} ({uplift.get('fitted_method_source')})")
    clv = _read_json(run_dir / "clv_eval.json")
    if clv.get("status") == "ok":
        models = " · ".join(f"{m.get('name')} {fmt(m.get('spearman'))}" for m in clv.get("models") or [])
        lines.append(f"  clv        Spearman {models}")
    ab = _read_json(run_dir / "ab_test.json")
    if ab.get("status") == "ok":
        lines.append(f"  ab_test    SRM ok={fmt((ab.get('srm') or {}).get('ok'))} · α={fmt(ab.get('power', {}).get('alpha'))}")
    comparison = _read_json(run_dir / "strategy_comparison.json")
    if mode.stages is None:
        for row in comparison.get("strategies") or []:
            lines.append(f"  {row.get('id')} {fmt(row.get('status')):<7} 대상 {fmt(row.get('n_targeted'))} · "
                         f"S1 대비 증분이익 {fmt(row.get('incremental_profit_vs_S1'), 0)}")
    for name, output in manifest["outputs"]["files"].items():
        detail = output.get("path") or output.get("reason")
        lines.append(f"  {name:<22} {output.get('status')} — {detail}")
        if name == BUDGET_ALLOCATION and output.get("status") == "ok":
            lines.append(f"    예산 {fmt(output.get('budget_krw'), 0)}원 · 대상 {output.get('n_targeted')}명 · "
                         f"계획 지출 {fmt(output.get('planned_spend_krw'), 0)}원 · 기대 ROI {fmt(output.get('expected_roi'))}")
    persisted = manifest["outputs"].get("persisted") or {}
    if persisted.get("status") not in (None, "not_requested"):
        models = persisted.get("models") or {}
        features = persisted.get("features") or {}
        lines.append(f"  저장       {persisted.get('status')} — 모델 {models.get('root') or models.get('reason') or '—'} · "
                     f"Feature {features.get('root') or features.get('reason') or '—'}")
    if manifest["inputs"].get("models_from"):
        lines.append(f"  불러온 모델 {manifest['inputs']['models_from']} — 다시 학습하지 않음")
    return lines


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    mode = MODES[args.mode]
    _check_budget(parser, mode, args.budget)

    try:  # 시뮬레이션 전에 두 config 를 검증한다 — 잘못된 키는 여기서 멈춘다
        from src.decision.config import load_experiment_config, load_model_config

        experiment = load_experiment_config()
        load_model_config()
    except ConfigError as error:
        print(f"[main] config 오류: {error}", file=sys.stderr)
        return error.exit_code
    try:
        from src.orchestration import run_sprint as rs
    except ImportError as error:
        print(f"[main] 실행 루프를 불러올 수 없다: {error} — `pip install -r requirements.txt`", file=sys.stderr)
        return 1

    run_id = args.run_id or rs.new_run_id()
    capture: dict[str, Any] = {}
    sprint = rs.SprintConfig(
        seed=experiment.holdout.development_seed if args.seed is None else args.seed,
        num_customers=experiment.run.num_customers if args.customers is None else args.customers,
        profile=experiment.run.profile if args.profile is None else args.profile,
        out=args.out or REPO_ROOT / "data" / "sprint" / run_id,
        results_root=args.results_root or (rs.DEFAULT_RESULTS_ROOT if mode.stages is None
                                           else REPO_ROOT / "results" / "cli" / mode.name),
        warmup_days=args.warmup_days, budget_krw=args.budget, run_id=run_id,
        cv_folds=args.cv_folds, max_train_rows=args.max_train_rows,
        stages=mode.stages, scope=f"--mode {mode.name}", capture=capture, require_clean=args.require_clean,
        # #214 — 기본으로 저장한다. --no-persist 면 저장하지 않는다.
        models_root=None if args.no_persist else (args.models_root or REPO_ROOT / "models"),
        feature_store_root=None if args.no_persist else (args.feature_store_root or REPO_ROOT / "data" / "processed"),
        load_models=args.load_models,
    )
    started = time.perf_counter()
    try:
        run_dir = rs.run(sprint)
    except rs.DirtyRepoError as error:
        print(f"[main] {error}", file=sys.stderr)
        return error.exit_code
    except rs.ModelLoadError as error:
        print(f"[main] {error}", file=sys.stderr)
        return EXIT_MODEL_LOAD
    outputs = {name: write_artifact(name, run_dir, capture) for name in mode.writes}
    run_meta = _read_json(run_dir / "run_meta.json")
    stages = run_meta.get("stages") or []
    persisted = run_meta.get("persistence") or {"status": "not_requested"}
    report = stage_report(mode, stages)
    manifest = {
        "mode": mode.name, "run_id": run_id, "generated_at": datetime.now(KST).isoformat(),
        "argv": list(sys.argv[1:] if argv is None else argv), "does": mode.does,
        "inputs": {
            "seed": sprint.seed, "num_customers": sprint.num_customers, "profile": sprint.profile,
            "budget_krw": args.budget, "warmup_days": args.warmup_days, "cv_folds": args.cv_folds,
            "max_train_rows": args.max_train_rows,
            "config_sha256": {name: _sha256(name) for name in CONFIG_FILES},
            # 이전 실행에서 읽는 것은 --load-models 의 모델뿐이다(시뮬레이션 산출물 · 결과 파일은 읽지 않는다)
            "reads_previous_runs": sprint.load_models is not None,
            "models_from": None if sprint.load_models is None else str(sprint.load_models),
        },
        "stages": report,
        "outputs": {"results_dir": str(run_dir), "simulator_out": str(sprint.out), "files": outputs,
                    "persisted": persisted},
        "handoff": HANDOFF, "not_persisted": list(NOT_PERSISTED),
        "seconds": round(time.perf_counter() - started, 1),
    }
    # 저장을 요청했는데 실패하면 1 — 조용히 넘어가지 않는다(#214)
    manifest["exit_code"] = 1 if persisted.get("status") == "failed" else exit_code(report, outputs)
    (run_dir / MANIFEST).write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    _mirror_into_latest(run_dir, [MANIFEST, *mode.writes])
    print("\n".join(summary_lines(mode, run_dir, manifest)), flush=True)
    return manifest["exit_code"]


if __name__ == "__main__":
    raise SystemExit(main())
