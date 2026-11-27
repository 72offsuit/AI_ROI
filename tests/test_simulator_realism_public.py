"""scripts/realism_public.py — 공개판에 정답 · 생성 이탈률 · 숨은 값 · 로컬 경로가 들어가지 않는다."""
import copy
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location("realism_public", REPO / "scripts" / "realism_public.py")
rp = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(rp)

def _report():
    metrics = [{"id": f"F{i}", "name": f"m{i}", "verdict": "pass", "dashboard_verdict": "consistent", "secret": 1,
                "synthetic": {"median": 7.0}} for i in range(1, 18)]
    return {"generated_at": "t", "source": {"events": "/local/path", "random_seed": "42", "guardrail": True},
            "rules": {"bands_from": "x", "extra": "y"}, "summary": {}, "metrics": metrics}


class RealismPublicTest(unittest.TestCase):
    def test_only_observational_metrics_and_keys(self):
        public = rp.make_public(_report())
        self.assertEqual([m["id"] for m in public["metrics"]], [f"F{i}" for i in (*range(1, 12), 13)])
        self.assertTrue(all("secret" not in m for m in public["metrics"]))
        self.assertEqual(public["source"], {"random_seed": "42"})
        self.assertEqual(public["rules"], {"bands_from": "x"})
        self.assertEqual(public["summary"]["pass"], 12)

    def test_refuses(self):
        cases = {
            "missing": lambda r: r.update(metrics=[m for m in r["metrics"] if m["id"] != "F5"]),
            "duplicate": lambda r: r["metrics"].append(dict(r["metrics"][0])),
            "no_data": lambda r: r["metrics"][2].update(verdict="no_data"),
            "confirm seed": lambda r: r["source"].update(random_seed="49"),
            "confirm seed int": lambda r: r["source"].update(random_seed=49),
            "seed list": lambda r: r["source"].update(random_seed=["42", "49"]),
            "seed float": lambda r: r["source"].update(random_seed="49.0"),
            "seed spaces": lambda r: r["source"].update(random_seed=" 49 "),
            "seed missing": lambda r: r["source"].pop("random_seed"),
            "dashboard mismatch": lambda r: r["metrics"][0].update(dashboard_verdict="deviates"),
            "unknown path": lambda r: r["metrics"][0]["synthetic"].update(new_key=1),
            "arm suffix": lambda r: r["metrics"][0].update(note="lift_T3 기준"),
            "arm korean": lambda r: r["metrics"][0].update(note="T3군 값"),
            "korean term": lambda r: r["metrics"][0].update(note="고객군별 값"),
            "home path": lambda r: r["metrics"][0].update(note="~/runs/x.json"),
            "results path": lambda r: r["metrics"][0].update(note="results/s1/x.json"),
            "windows path": lambda r: r["metrics"][0].update(note="C:\\Users\\x"),
            "nested persona": lambda r: r["metrics"][0]["synthetic"].update(by_persona={"vip_loyal": 1}),
            "nested arm": lambda r: r["metrics"][0]["synthetic"].update(lift={"T3": 1}),
            "local path": lambda r: r["metrics"][0].update(note="/Users/x/realism_report.json"),
            "exception note": lambda r: r["metrics"][0].update(note="KeyError: 'x'"),
        }
        for name, mutate in cases.items():
            report = copy.deepcopy(_report())
            mutate(report)
            with self.subTest(name), self.assertRaises(ValueError):
                rp.make_public(report)

    def test_committed_file(self):
        public = json.loads((REPO / "docs" / "research" / "realism_public.json").read_text(encoding="utf-8"))
        self.assertEqual(set(rp._paths(public)), rp.ALLOWED_PATHS)
        self.assertEqual([m["id"] for m in public["metrics"]], list(rp.PUBLIC_IDS))
        scanned = {k: v for k, v in public.items() if k != "scope"}
        self.assertFalse([s for s in rp._strings(scanned) if rp.FORBIDDEN.search(s)])

    def test_regenerating_committed_file_is_byte_identical(self):
        committed = REPO / "docs" / "research" / "realism_public.json"
        with tempfile.TemporaryDirectory() as d:
            out = Path(d) / "out.json"
            rp.main([str(committed), "--out", str(out)])
            self.assertEqual(out.read_bytes(), committed.read_bytes())


if __name__ == "__main__":
    unittest.main()
