from __future__ import annotations

import gzip
import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from typing import Iterable

from src.measurement import schema as sc
from src.measurement import sink as sk
from src.simulator import api

REPO_ROOT = Path(__file__).resolve().parent.parent
FIELDS = tuple(spec.name for spec in sc.EVENT_FIELDS)


def canonical_lines(records: Iterable[dict[str, object]]) -> list[bytes]:
    return [
        json.dumps(
            [record.get(name) for name in FIELDS],
            sort_keys=True, separators=(",", ":"), ensure_ascii=True,
        ).encode("ascii") + b"\n"
        for record in records
    ]


def event_digest(records: Iterable[dict[str, object]]) -> str:
    digest = hashlib.sha256()
    for line in canonical_lines(records):
        digest.update(line)
    return digest.hexdigest()


def root_digest(root: Path) -> str:
    return event_digest(sk.read_events(root))


def sink_files_digest(root: Path, names: list[str]) -> str:
    digest = hashlib.sha256()
    for path in sorted(root / name for name in names):
        digest.update(path.name.encode())
        digest.update(path.read_bytes())
    return digest.hexdigest()


def reseal_run_records(root: Path, hidden: Path | None = None) -> None:
    resealed: dict[str, dict[str, object]] = {}
    for record_path in sorted((root / sk.RUNS_DIR_NAME).glob("run-*.json")):
        record = json.loads(record_path.read_text(encoding="utf-8"))
        record["sha256"] = sink_files_digest(root, record["files"])
        record_path.write_text(json.dumps(record), encoding="utf-8")
        resealed[str(record["run_id"])] = record
    if hidden is None:
        return
    for run_id, record in resealed.items():
        sidecar = hidden / "runs" / f"{run_id}.json"
        if sidecar.is_file():
            lineage = json.loads(sidecar.read_text(encoding="ascii"))
            lineage["files"], lineage["sha256"] = record["files"], record["sha256"]
            sidecar.write_text(json.dumps(lineage), encoding="ascii")


def rewrite_gzip_lines(path: Path, keep) -> None:
    with gzip.open(path, "rt", encoding="utf-8") as handle:
        lines = [line for line in handle if line.strip()]
    with gzip.open(path, "wt", encoding="utf-8") as handle:
        handle.writelines(line for index, line in enumerate(lines) if keep(index))


def part_formats(root: Path) -> set[str]:
    return {path.name.split(".", 1)[1] for path in sorted((root / "events").rglob("part-*"))}


def digest_chain_breaks(hidden: Path, head: str) -> list[str]:
    records: dict[str, dict[str, object]] = {}
    run_id: str | None = head
    while run_id is not None:
        records[run_id] = json.loads((hidden / "runs" / f"{run_id}.json").read_text(encoding="ascii"))
        parent = records[run_id]["parent_run_id"]
        run_id = None if parent is None else str(parent)
    breaks: list[str] = []
    for run_id, record in records.items():
        parent = record["parent_run_id"]
        if parent is None:
            continue
        current = records[str(parent)]["end_state_digest"]
        for mutation in record["mutations"]:
            if mutation["before_digest"] != current:
                breaks.append(f"{run_id}: 변경 이전 다이제스트")
            current = mutation["after_digest"]
        if current != record["start_state_digest"]:
            breaks.append(f"{run_id}: 시작 다이제스트")
    return breaks


class SimulatorCase(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        self.hidden = self.tmp / "hidden"
        self._counter = 0

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def fresh_root(self, label: str = "root") -> Path:
        self._counter += 1
        return self.tmp / f"{label}-{self._counter}"

    def start(
        self, *, seed: int = 7, customers: int = 30, profile: str = "smoke",
        root: Path | None = None,
    ) -> Path:
        root = root or self.fresh_root("out")
        api.init(seed, customers, profile, root, hidden_root=self.hidden)
        return root

    def state_bytes(self, state_id: str) -> bytes:
        return (self.hidden / "states" / f"{state_id}.json").read_bytes()

    def state(self, state_id: str) -> dict[str, object]:
        return json.loads(self.state_bytes(state_id))

    def sidecar(self, run_id: str) -> dict[str, object]:
        return json.loads((self.hidden / "runs" / f"{run_id}.json").read_text(encoding="ascii"))
