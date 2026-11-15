"""공개 Uplift 데이터 외부 검증 실행기 (#217 3부). 실제 Hillstrom · Lenta 가 아니라 같은 열 이름의 합성 CSV 로 돈다.

    python -m unittest tests.test_uplift_benchmarks -v
"""

from __future__ import annotations

import json
import tempfile
import unittest
from unittest import mock
from importlib.util import find_spec
from pathlib import Path

DEPS = all(find_spec(m) for m in ("numpy", "pandas", "sklearn"))
REASON = "BLOCKED: numpy/pandas/scikit-learn 미설치"


def _hillstrom_like(n: int, seed: int):
    """Hillstrom 과 같은 열 — 남성 메일이 history 높은 고객의 방문을 올린다(합성)."""
    import numpy as np
    import pandas as pd

    rng = np.random.default_rng(seed)
    history = rng.gamma(2.0, 120.0, n)
    segment = rng.choice(["Mens E-Mail", "Womens E-Mail", "No E-Mail"], n)
    lift = np.where(segment == "No E-Mail", 0.0, 0.15 * (history > 200))
    visit = (rng.random(n) < 0.1 + lift).astype(int)
    return pd.DataFrame({
        "recency": rng.integers(1, 13, n), "history_segment": np.where(history > 200, "3) $200 - $350", "1) $0 - $100"),
        "history": history.round(2), "mens": rng.integers(0, 2, n), "womens": rng.integers(0, 2, n),
        "zip_code": rng.choice(["Urban", "Rural", "Surburban"], n), "newbie": rng.integers(0, 2, n),
        "channel": rng.choice(["Web", "Phone", "Multichannel"], n), "segment": segment,
        "visit": visit, "conversion": (visit & (rng.random(n) < 0.3)).astype(int), "spend": 0.0})


@unittest.skipUnless(DEPS, REASON)
class TestBenchmarkRunner(unittest.TestCase):
    def test_specs_match_the_pre_registration(self) -> None:
        """DR-217-uplift-tuning 「외부 검증」 표와 같은 처치 · 결과 · seed."""
        from src.decision.uplift_benchmarks import BENCHMARKS, HILLSTROM_FEATURES

        got = {b["id"]: (b["dataset"], b["control_value"], b["treatment_value"], b["outcome"], b["seeds"])
               for b in BENCHMARKS}
        self.assertEqual({
            "hillstrom_any_email_visit": ("hillstrom", "No E-Mail", None, "visit", (0, 1, 2)),
            "hillstrom_mens_conversion": ("hillstrom", "No E-Mail", "Mens E-Mail", "conversion", (0, 1, 2)),
            "lenta_response_att": ("lenta", "control", "test", "response_att", (0,)),
        }, got)
        self.assertEqual(("recency", "history_segment", "history", "mens", "womens", "zip_code", "newbie", "channel"),
                         HILLSTROM_FEATURES)

    def test_loaders_refuse_missing_columns(self) -> None:
        from src.decision.uplift_benchmarks import load_hillstrom, load_lenta

        with tempfile.TemporaryDirectory() as tmp:
            bad = Path(tmp) / "bad.csv"
            bad.write_text("a,b\n1,2\n", encoding="utf-8")
            with self.assertRaises(ValueError):
                load_hillstrom(bad)
            with self.assertRaises(ValueError):
                load_lenta(bad)

    def test_lenta_features_are_every_other_column(self) -> None:
        import pandas as pd

        from src.decision.uplift_benchmarks import load_lenta

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "lenta.csv"
            pd.DataFrame({"age": [30, 40], "gender": ["Ж", "М"], "group": ["test", "control"],
                          "response_att": [1, 0], "cheque_count_12m_g20": [1.0, None]}).to_csv(path, index=False)
            _, features = load_lenta(path)
        self.assertEqual(["age", "gender", "cheque_count_12m_g20"], features)

    def test_run_writes_aggregates_only(self) -> None:
        from src.decision import uplift
        from src.decision.uplift_benchmarks import main

        with tempfile.TemporaryDirectory() as tmp:
            data = Path(tmp) / "hillstorm_like.csv"
            frame = _hillstrom_like(2400, seed=1)
            frame.to_csv(data, index=False)
            out = Path(tmp) / "out.json"
            with mock.patch.dict("src.decision.uplift_benchmarks.INTEGRITY", clear=True):  # 합성 CSV — 기준 없음
                self.assertEqual(0, main(["--hillstrom", str(data), "--out", str(out)]))
            report = json.loads(out.read_text(encoding="utf-8"))
        self.assertEqual("no_reference", report["integrity"]["hillstrom"]["status"])
        self.assertTrue(report["run"]["started_at"] <= report["run"]["finished_at"])
        self.assertIn("commit", report["run"]["code"])
        self.assertEqual("not_run", report["results"]["lenta_response_att"]["status"])
        self.assertEqual({"file": "hillstorm_like.csv", "rows": 2400},
                         {k: report["datasets"]["hillstrom"][k] for k in ("file", "rows")})
        self.assertEqual(1, report["environment"]["openmp_threads"])
        self.assertEqual(1, uplift.N_THREADS)  # 실행 루프 기본값 그대로 — 실행기가 바꾼 뒤에도
        for bid in ("hillstrom_any_email_visit", "hillstrom_mens_conversion"):
            block = report["results"][bid]
            self.assertEqual(["0", "1", "2"], list(block["runs"]))
            run = block["runs"]["0"]
            self.assertEqual(len(run["configs"]) * 2, len(run["validation_grid"]))
            self.assertIn(run["chosen_method"], ("t_learner", "x_learner"))
            self.assertEqual(["random", "churn_risk_targeting", "s_learner", "t_learner", "x_learner"], list(run["test"]))
            self.assertNotIn("qini_curve", run["test"]["t_learner"])
        text = json.dumps(report)
        self.assertNotIn("customer_ids", text)  # 고객 ID · 곡선 없이 집계만

    def test_integrity_mismatch_refuses_to_run(self) -> None:
        """PR #294 리뷰 2 — 사전 고정 무결성 기준(행 수 · 처치별 결과 비율)과 다르면 실행하지 않는다."""
        from src.decision import uplift_benchmarks as ub

        frame = _hillstrom_like(600, seed=2)
        record = ub.check_integrity("hillstrom", frame)  # 실제 기준(64,000행 · 18.28/15.14/10.62%)과 다르다
        self.assertEqual("mismatch", record["status"])
        self.assertEqual(600, record["rows"])
        with tempfile.TemporaryDirectory() as tmp:
            data = Path(tmp) / "h.csv"
            frame.to_csv(data, index=False)
            with self.assertRaises(ValueError):
                ub.run({"hillstrom": data})
        rates = {k: round(float(v) * 100, 2) for k, v in frame.groupby("segment")["visit"].mean().items()}
        spec = {"hillstrom": {"rows": 600, "group_col": "segment", "outcome": "visit", "rates": rates}}
        with mock.patch.dict(ub.INTEGRITY, spec, clear=True):
            self.assertEqual("ok", ub.check_integrity("hillstrom", frame)["status"])


if __name__ == "__main__":
    unittest.main()
