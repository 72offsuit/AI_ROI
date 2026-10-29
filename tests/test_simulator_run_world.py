"""`scripts/research/run_world.py` — DR-183 실측 실행기가 realism_check 입력을 만들고, 같은 seed 면 같은 배정을 낸다."""

from __future__ import annotations

import contextlib
import importlib.util
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location("run_world", REPO / "scripts" / "research" / "run_world.py")
rw = importlib.util.module_from_spec(_spec)
sys.modules["run_world"] = rw
_spec.loader.exec_module(rw)


class TestRunWorld(unittest.TestCase):
    def _run(self, root: Path, name: str) -> Path:
        out = root / name
        with contextlib.redirect_stdout(io.StringIO()):
            code = rw.main(["--seed", "7", "--customers", "40", "--profile", "smoke",
                            "--days", "30", "--assign-day", "20", "--out", str(out)])
        self.assertEqual(0, code)
        return out

    def test_writes_inputs_and_repeats_the_same_assignment(self):
        with tempfile.TemporaryDirectory() as tmp:
            first, second = self._run(Path(tmp), "a"), self._run(Path(tmp), "b")
            self.assertTrue((first / "raw" / "main").is_dir())
            self.assertTrue((first / "raw" / "simulator_exchange").is_dir())
            a = json.loads((first / "assignments.json").read_text(encoding="utf-8"))
            b = json.loads((second / "assignments.json").read_text(encoding="utf-8"))
            self.assertTrue(a["assignments"])
            self.assertTrue(set(a["assignments"].values()) <= set(rw.ARMS))
            self.assertEqual(a, b)

    def test_existing_output_directory_is_refused(self):
        with tempfile.TemporaryDirectory() as tmp, self.assertRaises(FileExistsError):
            rw.main(["--seed", "7", "--customers", "10", "--profile", "smoke", "--days", "30",
                     "--assign-day", "20", "--out", tmp])


if __name__ == "__main__":
    unittest.main()
