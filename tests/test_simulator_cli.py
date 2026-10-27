from __future__ import annotations

import json
import subprocess
import sys
import unittest
from pathlib import Path
from unittest import mock

import src.simulator.__main__ as cli_main
from src.measurement import sink as sk
from src.simulator import api
from src.simulator._internal import genconfig
from tests.test_simulator_support import REPO_ROOT, SimulatorCase, root_digest


class TestCommandLine(SimulatorCase):
    def cli(self, *arguments: str, hidden: Path | None = None) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, "-m", "src.simulator", *arguments,
             "--hidden-root", str(hidden or self.tmp / "cli-hidden")],
            cwd=REPO_ROOT, capture_output=True, text=True, timeout=300, check=False,
        )

    def ok(self, *arguments: str) -> str:
        result = self.cli(*arguments)
        self.assertEqual(0, result.returncode, result.stderr)
        return result.stdout.strip()

    def test_init_then_resume_in_new_processes_matches_one_continuous_run(self) -> None:
        reference = self.start(seed=3, customers=20)
        api.advance(60)
        expected_digest, expected_state = root_digest(reference), api.save_state()

        root = self.fresh_root("cli")
        middle = self.ok(
            "init", "--seed", "3", "--customers", "20", "--profile", "smoke",
            "--output-root", str(root), "--days", "30",
        )
        self.assertRegex(middle, r"^state-[0-9a-f]{16}$")
        final = self.ok("resume", "--state-id", middle, "--output-root", str(root), "--days", "30")
        self.assertEqual(expected_state, final)
        self.assertEqual(expected_digest, root_digest(root))
        self.assertEqual("ok", sk.verify_lineage(root).verification)

    def test_advance_continues_from_the_root_head(self) -> None:
        reference = self.start(seed=4, customers=10)
        api.advance(12)
        expected = root_digest(reference), api.save_state()

        resumed_root = self.fresh_root("cli")
        first = self.ok("init", "--seed", "4", "--customers", "10", "--profile", "smoke",
                        "--output-root", str(resumed_root), "--days", "5")
        second = self.ok("advance", "--output-root", str(resumed_root), "--days", "7")
        self.assertNotEqual(first, second)
        self.assertEqual(expected, (root_digest(resumed_root), second))
        self.assertEqual(2, len(sk.run_records(resumed_root)))

    def test_failures_exit_non_zero(self) -> None:
        written = self.fresh_root("cli")
        self.ok("init", "--seed", "1", "--customers", "3", "--profile", "smoke",
                "--output-root", str(written), "--days", "1")
        cases = {
            "non-empty root": (1, ("init", "--seed", "1", "--customers", "3", "--profile", "smoke",
                                   "--output-root", str(written))),
            "unknown state": (1, ("resume", "--state-id", "state-0000000000000000",
                                  "--output-root", str(self.fresh_root("x")), "--days", "1")),
            "root without head": (1, ("advance", "--output-root", str(self.fresh_root("x")),
                                      "--days", "1")),
            "negative days": (2, ("advance", "--output-root", str(written), "--days", "-1")),
            "unknown profile": (2, ("init", "--seed", "1", "--customers", "3", "--profile", "nope",
                                    "--output-root", str(self.fresh_root("x")))),
            "missing argument": (2, ("init", "--seed", "1")),
            "customers omitted without a profile default": (
                2, ("init", "--seed", "1", "--profile", "smoke", "--output-root", str(self.fresh_root("x")))),
            "guardrails customers omitted without a profile default": (
                2, ("guardrails", "--seed", "1", "--profile", "short", "--warmup-days", "1",
                    "--output-root", str(self.fresh_root("x")))),
            "unreadable config": (1, ("init", "--seed", "1", "--customers", "3", "--profile", "smoke",
                                      "--output-root", str(self.fresh_root("x")),
                                      "--config", str(self.tmp / "nowhere.yaml"))),
            "malformed state id": (2, ("resume", "--state-id", "nope",
                                       "--output-root", str(self.fresh_root("x")), "--days", "1")),
        }
        for label, (code, arguments) in cases.items():
            with self.subTest(case=label):
                result = self.cli(*arguments)
                self.assertEqual(code, result.returncode, result.stderr)
                self.assertTrue(result.stderr.strip())
                self.assertEqual("", result.stdout)

    def test_small_profile_defaults_to_five_thousand_customers(self) -> None:
        # 5,000명 세계를 실제로 만들지 않고, CLI 가 API 에 넘기는 값만 본다.
        for command, extra in (("init", ()), ("guardrails", ("--warmup-days", "1"))):
            with self.subTest(command=command):
                with mock.patch.object(api, "init", side_effect=api.SimulatorError("멈춤")) as init:
                    code = cli_main.main([command, "--seed", "1", "--profile", "small",
                                          "--output-root", str(self.fresh_root("x")), *extra])
                self.assertEqual(cli_main.EXIT_SIMULATOR_ERROR, code)
                self.assertEqual(5_000, init.call_args.args[1])
        with mock.patch.object(api, "init", side_effect=api.SimulatorError("멈춤")) as init:
            cli_main.main(["init", "--seed", "1", "--customers", "12", "--profile", "small",
                           "--output-root", str(self.fresh_root("x"))])
        self.assertEqual(12, init.call_args.args[1])

    def test_experiment_config_runs_and_refuses_to_continue_under_another(self) -> None:
        document = json.loads(genconfig.CONFIG_PATH.read_text(encoding="utf-8"))
        document["behavior"]["visit"]["scale_pct"] += 1
        experiment = self.tmp / "experiment.yaml"
        experiment.write_text(json.dumps(document), encoding="utf-8")
        root = self.fresh_root("cli")
        first = self.ok("init", "--seed", "2", "--customers", "5", "--profile", "smoke",
                        "--output-root", str(root), "--days", "2", "--config", str(experiment))
        before = sorted(p.as_posix() for p in root.rglob("*"))
        for arguments in (("advance", "--output-root", str(root), "--days", "1"),
                          ("resume", "--state-id", first, "--output-root", str(self.fresh_root("x")),
                           "--days", "1")):
            with self.subTest(command=arguments[0]):
                result = self.cli(*arguments)
                self.assertEqual(1, result.returncode, result.stderr)
                self.assertIn("--config", result.stderr)
                self.assertIn("generation", result.stderr)
                self.assertNotIn("Traceback", result.stderr)
        self.assertEqual(before, sorted(p.as_posix() for p in root.rglob("*")))
        second = self.ok("advance", "--output-root", str(root), "--days", "1", "--config", str(experiment))
        self.assertNotEqual(first, second)
        self.assertEqual("ok", sk.verify_lineage(root).verification)

    def test_corrupt_head_record_exits_one(self) -> None:
        hidden = self.tmp / "cli-hidden"
        for label, damage in (("garbage", lambda text: "{not json"),
                              ("missing key", lambda text: json.dumps(
                                  {k: v for k, v in json.loads(text).items() if k != "end_state_digest"}))):
            with self.subTest(case=label):
                root = self.fresh_root("cli")
                self.ok("init", "--seed", "1", "--customers", "3", "--profile", "smoke",
                        "--output-root", str(root), "--days", "1")
                head = sk.run_records(root)[0]["run_id"]
                record = hidden / "runs" / f"{head}.json"
                record.write_text(damage(record.read_text(encoding="ascii")), encoding="ascii")
                result = self.cli("advance", "--output-root", str(root), "--days", "1")
                self.assertEqual(1, result.returncode, result.stderr)
                self.assertNotIn("Traceback", result.stderr)

    def test_interrupted_root_is_refused_and_recovery_uses_a_new_root(self) -> None:
        hidden = self.tmp / "cli-hidden"
        root = self.fresh_root("cli")
        api.init(2, 8, "smoke", root, hidden_root=hidden)
        api.advance(3)
        with mock.patch.object(sk.EventSink, "manifest", side_effect=OSError(28, "No space left")):
            with self.assertRaises(api.SimulatorError):
                api.advance(3)
        last_good = api.save_state()
        before = sorted(p.as_posix() for p in root.rglob("*"))
        for arguments in (("advance", "--output-root", str(root), "--days", "3"),
                          ("resume", "--state-id", last_good, "--output-root", str(root), "--days", "3")):
            with self.subTest(command=arguments[0]):
                result = self.cli(*arguments)
                self.assertEqual(1, result.returncode, result.stderr)
        self.assertEqual(before, sorted(p.as_posix() for p in root.rglob("*")))
        recovered = self.fresh_root("cli")
        self.ok("resume", "--state-id", last_good, "--output-root", str(recovered), "--days", "3")
        self.assertEqual("ok", sk.verify_lineage(recovered).verification)

    def test_root_with_changed_claimed_bytes_is_refused_by_advance_and_resume(self) -> None:
        hidden = self.tmp / "cli-hidden"
        root = self.fresh_root("cli")
        saved = self.ok("init", "--seed", "5", "--customers", "6", "--profile", "smoke",
                        "--output-root", str(root), "--days", "3")
        part = sorted((root / "events").rglob("part-*"))[0]
        data = bytearray(part.read_bytes())
        data[len(data) // 2] ^= 0x01
        part.write_bytes(bytes(data))
        self.assertTrue((hidden / "states" / f"{saved}.json").is_file())
        before = sorted(p.as_posix() for p in root.rglob("*"))
        for arguments in (("advance", "--output-root", str(root), "--days", "1"),
                          ("resume", "--state-id", saved, "--output-root", str(root), "--days", "1")):
            with self.subTest(command=arguments[0]):
                result = self.cli(*arguments)
                self.assertEqual(1, result.returncode, result.stderr)
        self.assertEqual(before, sorted(p.as_posix() for p in root.rglob("*")))


if __name__ == "__main__":
    unittest.main()
