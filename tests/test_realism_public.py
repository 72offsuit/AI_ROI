"""scripts/realism_public.py — 공개판에 F14~F17 · 허용 목록 밖 키가 들어가지 않는다."""
import importlib.util
import unittest
from pathlib import Path

_spec = importlib.util.spec_from_file_location(
    "realism_public", Path(__file__).resolve().parents[1] / "scripts" / "realism_public.py")
rp = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(rp)


def _report():
    metrics = [{"id": f"F{i}", "name": f"m{i}", "verdict": "pass", "secret": 1} for i in range(1, 18)]
    return {"generated_at": "t", "source": {"events": "/local/path", "random_seed": "42", "guardrail": True},
            "rules": {}, "summary": {}, "metrics": metrics}


class RealismPublicTest(unittest.TestCase):
    def test_only_observational_metrics_and_keys(self):
        public = rp.make_public(_report())
        self.assertEqual([m["id"] for m in public["metrics"]], [f"F{i}" for i in range(1, 14)])
        self.assertTrue(all("secret" not in m for m in public["metrics"]))
        self.assertEqual(public["source"], {"random_seed": "42"})
        self.assertEqual(public["summary"]["pass"], 13)

    def test_missing_metric_refuses(self):
        report = _report()
        report["metrics"] = [m for m in report["metrics"] if m["id"] != "F5"]
        with self.assertRaises(ValueError):
            rp.make_public(report)


if __name__ == "__main__":
    unittest.main()
