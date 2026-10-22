"""S8 채점 지표·실행 가드 — 합성 τ·τ̂ 로만 시험한다 (실제 ground truth·results 를 읽지 않는다).

DR-142-diagnostics-sprint.
"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

try:
    import numpy as np
    import scipy  # noqa: F401
    import yaml  # noqa: F401
    HAVE_DEPS = True
except ImportError:  # pragma: no cover - 의존성 없는 CI 잡
    HAVE_DEPS = False

SKIP_REASON = "BLOCKED: numpy/pandas/scikit-learn 미설치"


@unittest.skipUnless(HAVE_DEPS, SKIP_REASON)
class TestScoringMetrics(unittest.TestCase):
    def setUp(self) -> None:
        from src.diagnostics import scoring
        self.s = scoring
        rng = np.random.default_rng(7)
        n = 4000
        self.tau = rng.choice([-1.0, 0.0, 1.0], size=n, p=[0.1, 0.6, 0.3])
        self.y0 = rng.integers(0, 2, size=n)
        # 잠재결과가 τ 와 맞도록 Y(1) 을 만든다: τ=1 → (1,0), τ=-1 → (0,1).
        self.y0 = np.where(self.tau == 1, 0, np.where(self.tau == -1, 1, self.y0))
        self.y1 = (self.y0 + self.tau).astype(int)
        self.w = rng.integers(0, 2, size=n)
        self.y = np.where(self.w == 1, self.y1, self.y0)

    def test_perfect_prediction(self) -> None:
        s = self.s
        self.assertEqual(s.pehe(self.tau, self.tau), 0.0)
        corr = s.corr_tau(self.tau, self.tau)
        self.assertAlmostEqual(corr["pearson"], 1.0, places=12)
        self.assertAlmostEqual(corr["spearman"], 1.0, places=12)
        oracle = s.qini_oracle(self.tau, self.w, self.y)
        model = s.qini_coefficient(self.tau, self.w, self.y)
        self.assertGreater(oracle, 0)
        self.assertAlmostEqual(s.qini_attainment(model, oracle)["value"], 1.0, places=12)

    def test_pehe_known_value(self) -> None:
        self.assertAlmostEqual(self.s.pehe([1, 2, 3], [1, 2, 5]), np.sqrt(4 / 3))

    def test_reversed_ranking_is_negative_correlation_and_below_oracle(self) -> None:
        s = self.s
        corr = s.corr_tau(-self.tau, self.tau)
        self.assertAlmostEqual(corr["pearson"], -1.0, places=12)
        oracle = s.qini_oracle(self.tau, self.w, self.y)
        self.assertLess(s.qini_coefficient(-self.tau, self.w, self.y), 0)
        self.assertLess(s.qini_attainment(s.qini_coefficient(-self.tau, self.w, self.y),
                                          oracle)["value"], 0)

    def test_constant_score_is_random_policy(self) -> None:
        q = self.s.qini_coefficient(np.zeros_like(self.tau), self.w, self.y)
        self.assertAlmostEqual(q, 0.0, places=12)

    def test_ties_do_not_depend_on_input_order(self) -> None:
        s = self.s
        perm = np.random.default_rng(1).permutation(len(self.tau))
        a = s.qini_oracle(self.tau, self.w, self.y)
        b = s.qini_oracle(self.tau[perm], self.w[perm], self.y[perm])
        self.assertAlmostEqual(a, b, places=12)

    def test_attainment_refuses_non_positive_denominator(self) -> None:
        for oracle in (0.0, -0.1):
            out = self.s.qini_attainment(0.05, oracle)
            self.assertIsNone(out["value"])
            self.assertTrue(out["reason"])
        self.assertIsNone(self.s.qini_attainment(None, 0.1)["value"])

    def test_corr_undefined_for_constant(self) -> None:
        out = self.s.corr_tau(np.zeros(10), np.arange(10))
        self.assertIsNone(out["pearson"])
        self.assertIsNone(out["spearman"])
        self.assertTrue(out["reason"])

    def test_spearman_is_rank_based(self) -> None:
        x = np.arange(1, 21, dtype=float)
        out = self.s.corr_tau(x ** 3, x)
        self.assertAlmostEqual(out["spearman"], 1.0, places=12)
        self.assertLess(out["pearson"], 1.0)

    def test_quadrants(self) -> None:
        s = self.s
        self.assertEqual(s.quadrant_of(1, 0), s.PERSUADABLE)
        self.assertEqual(s.quadrant_of(1, 1), s.SURE_THING)
        self.assertEqual(s.quadrant_of(0, 0), s.LOST_CAUSE)
        self.assertEqual(s.quadrant_of(0, 1), s.SLEEPING_DOG)

    def test_quadrant_confusion_rates(self) -> None:
        s = self.s
        true = [s.PERSUADABLE] * 4 + [s.SLEEPING_DOG] * 2 + [s.SURE_THING]
        pred = [0.3, 0.2, -0.1, -0.4, 0.5, -0.2, 0.0]
        out = s.quadrant_confusion(pred, true)
        self.assertEqual(out["persuadable_as_sleeping_dog"], 0.5)
        self.assertEqual(out["sleeping_dog_as_persuadable"], 0.5)
        self.assertEqual(out["matrix"][s.SURE_THING][s.NEUTRAL], 1)
        self.assertIsNone(s.quadrant_confusion([0.1], [s.PERSUADABLE])["sleeping_dog_as_persuadable"])

    def test_quadrant_confusion_perfect(self) -> None:
        s = self.s
        true = [s.quadrant_of(a, b) for a, b in zip(self.y1, self.y0)]
        out = s.quadrant_confusion(list(self.tau), true)
        self.assertEqual(out["persuadable_as_sleeping_dog"], 0.0)
        self.assertEqual(out["sleeping_dog_as_persuadable"], 0.0)

    def test_quadrant_labels_accepted(self) -> None:
        s = self.s
        out = s.quadrant_confusion([s.SLEEPING_DOG], [s.PERSUADABLE])
        self.assertEqual(out["persuadable_as_sleeping_dog"], 1.0)
        with self.assertRaises(ValueError):
            s.quadrant_confusion(["bogus"], [s.PERSUADABLE])

    def test_length_mismatch_rejected(self) -> None:
        with self.assertRaises(ValueError):
            self.s.pehe([1, 2], [1])
        with self.assertRaises(ValueError):
            self.s.qini_coefficient([1, 2], [0, 1], [1])


def _write_synthetic(root: Path, with_cate: bool) -> tuple[Path, Path]:
    """합성 ground truth(po-*.jsonl) 와 결과(cate.jsonl). 실제 시뮬레이터 산출물이 아니다."""
    gt = root / "gt"
    res = root / "res"
    gt.mkdir()
    res.mkdir()
    rng = np.random.default_rng(3)
    rows, cate = [], []
    arms = ("T0", "T1", "T2", "T3", "T4")
    for i in range(600):
        y0 = int(rng.integers(0, 2))
        ys = {"T0": y0}
        for arm in arms[1:]:
            ys[arm] = int(rng.integers(0, 2))
        cid = f"C{i + 1:08d}"
        rows.append({
            "customer_id": cid,
            "treatment_id": arms[i % 5],
            "outcomes": {a: {"purchased": ys[a], "revenue": 0, "contribution_profit": 0,
                             "marketing_cost": 0} for a in arms},
        })
        cate.append({"customer_id": cid, **{f"cate_{a}": float(ys[a] - y0) for a in arms[1:]}})
    (gt / "po-w1-20260101-s1-rct.jsonl").write_text(
        "".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
    if with_cate:
        (res / "cate.jsonl").write_text("".join(json.dumps(r) + "\n" for r in cate), encoding="utf-8")
    return gt, res


@unittest.skipUnless(HAVE_DEPS, SKIP_REASON)
class TestReportGuard(unittest.TestCase):
    def _run(self, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run([sys.executable, "-m", "src.diagnostics.report", *args],
                              cwd=REPO_ROOT, capture_output=True, text=True, timeout=120)

    def test_current_repo_is_unsealed(self) -> None:
        from src.diagnostics import report
        self.assertFalse(report.gate1_status()["sealed"])
        self.assertFalse(report.gate2_status()["sealed"])

    def test_cli_refuses_when_unsealed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            gt, res = _write_synthetic(Path(tmp), with_cate=True)
            out = Path(tmp) / "out.json"
            proc = self._run("--ground-truth", str(gt), "--results", str(res), "--out", str(out))
            from src.diagnostics import report
            self.assertEqual(proc.returncode, report.EXIT_REFUSED, proc.stderr)
            self.assertIn("거부", proc.stderr)
            self.assertIn("GATE 2", proc.stderr)
            self.assertFalse(out.exists())

    def test_allow_unsealed_still_refuses_real_paths(self) -> None:
        from src.diagnostics import report
        decision = report.guard(report.REAL_GROUND_TRUTH, report.REAL_RESULTS, allow_unsealed=True)
        self.assertFalse(decision["allowed"])
        self.assertIn("합성 데이터 전용", decision["reasons"][0])

    def test_gate1_sealed_only_when_fully_declared(self) -> None:
        from src.diagnostics import report
        with tempfile.TemporaryDirectory() as tmp:
            lock = Path(tmp) / "lock.yaml"
            lock.write_text("declaration: PARTIAL_FREEZE\nexperiment_environment_v1_declared: false\n"
                            "simulator_commit: null\n", encoding="utf-8")
            self.assertEqual(len(report.gate1_status(lock)["reasons"]), 3)
            lock.write_text("declaration: FREEZE\nexperiment_environment_v1_declared: true\n"
                            "simulator_commit: abc123\n", encoding="utf-8")
            self.assertTrue(report.gate1_status(lock)["sealed"])
            # GATE 1 이 봉인돼도 GATE 2 미정이면 거부.
            decision = report.guard(Path(tmp), Path(tmp), allow_unsealed=False, lock_path=lock)
            self.assertFalse(decision["allowed"])

    def test_allow_unsealed_synthetic_report(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            gt, res = _write_synthetic(Path(tmp), with_cate=True)
            out = Path(tmp) / "out.json"
            proc = self._run("--ground-truth", str(gt), "--results", str(res), "--out", str(out),
                             "--allow-unsealed")
            self.assertEqual(proc.returncode, 0, proc.stderr)
            data = json.loads(out.read_text(encoding="utf-8"))
            self.assertFalse(data["sealed"])
            self.assertTrue(data["allow_unsealed"])
            arm = data["files"][0]["arms"]["T1"]
            self.assertEqual(arm["status"], "ok")
            # 합성 τ̂ = 참 τ → 완벽 예측.
            self.assertEqual(arm["pehe"], 0.0)
            self.assertAlmostEqual(arm["qini_attainment"]["value"], 1.0, places=12)
            self.assertAlmostEqual(arm["corr_tau"]["pearson"], 1.0, places=12)

    def test_missing_tau_hat_is_partial_with_reason(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            gt, res = _write_synthetic(Path(tmp), with_cate=False)
            out = Path(tmp) / "out.json"
            proc = self._run("--ground-truth", str(gt), "--results", str(res), "--out", str(out),
                             "--allow-unsealed")
            self.assertEqual(proc.returncode, 0, proc.stderr)
            data = json.loads(out.read_text(encoding="utf-8"))
            self.assertEqual(data["inputs"]["tau_hat"], "missing")
            arm = data["files"][0]["arms"]["T2"]
            self.assertEqual(arm["status"], "partial")
            self.assertIn("고객별 τ̂", arm["reason"])
            self.assertIn("qini_oracle", arm)


if __name__ == "__main__":
    unittest.main()
