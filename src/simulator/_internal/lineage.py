from __future__ import annotations

import gzip
import hashlib
import json
from pathlib import Path
from typing import Iterator

from src.measurement import sink as sk
from src.simulator._internal import storage
from src.simulator._internal import world as wd
from src.simulator._internal.rng import canonical_json

_FORMATS = {fmt.value: fmt for fmt in sk.SinkFormat}
_ANY = object()


class LineageBroken(Exception):
    pass


class FormatProblem(Exception):
    pass


def root_formats(root: Path) -> set[str]:
    found: set[str] = set()
    events = root.joinpath("events")
    if events.is_dir():
        for path in sorted(events.rglob("part-*")):
            found.add(path.name.split(".", 1)[1] if "." in path.name else "")
    for record in sk.run_records(root):
        value = record.get("format")
        if isinstance(value, str):
            found.add(value)
    return found


def _single_format(root: Path) -> sk.SinkFormat | None:
    found = root_formats(root)
    unknown = sorted(found - set(_FORMATS))
    if unknown:
        raise FormatProblem(f"출력 루트에 모르는 저장 형식이 있다: {unknown}")
    if len(found) > 1:
        raise FormatProblem(f"출력 루트에 저장 형식이 섞여 있다: {sorted(found)}")
    return _FORMATS[found.pop()] if found else None


_WRITE_ROOT = "이어 쓸 출력 루트는 parquet 으로 기록됐는데 현재 런타임에 pyarrow 가 없다 — pyarrow 가 있는 런타임에서 잇거나 새 빈 루트로 이어간다"
_LINEAGE = "이 세계의 계보(조상 루트)가 parquet 으로 기록됐는데 현재 런타임에 pyarrow 가 없다 — requirements.txt 를 설치한 런타임에서 이어받거나 읽는다"


def require_capability(fmt: sk.SinkFormat, message: str = _WRITE_ROOT) -> None:
    if fmt is sk.SinkFormat.PARQUET and not sk.parquet_available():
        raise FormatProblem(message)


def write_format(root: Path) -> sk.SinkFormat:
    fmt = _single_format(root) or sk.resolve_format("auto")
    require_capability(fmt)
    return fmt


_READABLE = {
    sk.SinkFormat.PARQUET.value: sk.SinkFormat.PARQUET,
    sk.SinkFormat.JSONL_GZ.value: sk.SinkFormat.JSONL_GZ,
    sk.SinkFormat.JSONL.value: sk.SinkFormat.JSONL,
}


def require_formats_readable(formats: set[str]) -> None:
    unknown = sorted(formats - set(_READABLE))
    if unknown:
        raise FormatProblem(f"계보에 이 런타임이 읽지 않는 저장 형식이 있다: {unknown}")
    for value in sorted(formats):
        require_capability(_READABLE[value], _LINEAGE)


def lineage_formats(verifier: Verifier, head: str | None) -> set[str]:
    formats: set[str] = set()
    seen: set[str] = set()
    run_id = head
    while run_id is not None and run_id not in seen:
        seen.add(run_id)
        record = verifier.sidecar(run_id)
        formats.add(str(record.get("sink_format")))
        parent = record.get("parent_run_id")
        run_id = None if parent is None else str(parent)
    return formats


def read_file(path: Path) -> Iterator[dict[str, object]]:
    suffix = path.name.split(".", 1)[1]
    if suffix == sk.SinkFormat.PARQUET.value:
        import pyarrow.parquet as pq

        yield from pq.read_table(path).to_pylist()
        return
    opener = gzip.open if suffix == sk.SinkFormat.JSONL_GZ.value else open
    with opener(path, "rt", encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                record = json.loads(line)
                if not isinstance(record, dict):
                    raise ValueError(f"{path.name} 에 객체가 아닌 행이 있다")
                yield record


def check_mutations(base: object, mutations: object, target: object) -> None:
    if not isinstance(mutations, list):
        raise LineageBroken("mutations 가 배열이 아니다")
    current = base
    for index, mutation in enumerate(mutations):
        if not isinstance(mutation, dict) or mutation.get("before_digest") != current:
            raise LineageBroken(f"상태 변경 {index} 의 이전 다이제스트가 사슬과 다르다")
        current = mutation.get("after_digest")
    if current != target:
        raise LineageBroken("상태 변경을 거친 다이제스트가 다음 상태와 다르다")


class Verifier:
    def __init__(self, hidden_root: Path) -> None:
        self.hidden_root = hidden_root
        self._intact: dict[str, None] = {}
        self._chains: dict[str, list[dict[str, object]]] = {}
        self.files: dict[str, list[Path]] = {}

    def require_intact(self, root: Path) -> None:
        key = str(root)
        if key in self._intact:
            return
        result = sk.verify_lineage(root)
        if result.verification != "ok":
            raise LineageBroken(
                f"출력 루트 {root} 의 계보가 {result.verification} 이다: {result.detail[:300]}"
            )
        self._intact[key] = None

    def sidecar(self, run_id: str) -> dict[str, object]:
        try:
            record = storage.read_sidecar(self.hidden_root, run_id)
        except (OSError, ValueError) as error:
            raise LineageBroken(f"계보 기록 {run_id} 를 읽을 수 없다") from error
        if record is None:
            raise LineageBroken(f"계보 기록 {run_id} 가 없다")
        return record

    def chain(self, head: str | None) -> list[dict[str, object]]:
        if head is None:
            return []
        if head in self._chains:
            return self._chains[head]
        try:
            records = self._verify(head)
        except (KeyError, TypeError) as error:
            raise LineageBroken(f"계보 기록의 형태가 틀렸다: {error!r}") from error
        self._chains[head] = records
        return records

    def _verify(self, head: str) -> list[dict[str, object]]:
        records: list[dict[str, object]] = []
        seen: set[str] = set()
        run_id: str | None = head
        while run_id is not None:
            if run_id in seen:
                raise LineageBroken(f"계보에 순환이 있다: {run_id}")
            seen.add(run_id)
            record = self.sidecar(run_id)
            records.append(record)
            parent = record["parent_run_id"]
            run_id = None if parent is None else str(parent)
        records.reverse()
        previous_end: object = None
        by_root: dict[str, list[dict[str, object]]] = {}
        for record in records:
            by_root.setdefault(str(record["output_root"]), []).append(record)
            _require_current_generation(record)
            base = previous_end if record["parent_run_id"] is not None else wd.initial_digest(
                record["seed"], record["num_customers"], str(record["profile"])
            )
            check_mutations(base, record.get("mutations", []), record["start_state_digest"])
            previous_end = record["end_state_digest"]
        for root, members in sorted(by_root.items()):
            self.files.update(_member_files(Path(root), members))
        return records

    def derivation_base(self, record: dict[str, object], world: dict[str, object]) -> object:
        parent = record.get("parent_run_id")
        if parent is None:
            if record.get("world_id") != world["world_id"]:
                raise LineageBroken(_GENERATION_CHANGED)
            return wd.initial_digest(world["seed"], world["num_customers"], str(world["profile"]))
        chain = self.chain(str(parent))
        return chain[-1]["end_state_digest"]


_GENERATION_CHANGED = "생성 설정이 이 계보를 만든 설정과 다르다"


def _require_current_generation(record: dict[str, object]) -> None:
    # world_id 는 생성 config 다이제스트를 담는다. 기준 상태를 다시 만들기 전에 대조해야
    # config 변경을 "변조"(다이제스트 사슬 불일치)로 오진하지 않는다.
    expected = wd.current_world_id(record["seed"], record["num_customers"], str(record["profile"]))
    if record.get("world_id") != expected:
        raise LineageBroken(_GENERATION_CHANGED)


def _member_files(root: Path, members: list[dict[str, object]]) -> dict[str, list[Path]]:
    # 계보 구성원 실행이 주장한 파일만 본다. 고아·외부 Sink 파일은 읽지도 판정하지도 않는다.
    # 기준값은 숨김 영역 사이드카에 있다. 출력 루트의 실행 기록만 다시 봉인한 위조는 여기서 걸린다.
    runs = {str(r.get("run_id")): r for r in sk.run_records(root)}
    found: dict[str, list[Path]] = {}
    claimed_by: dict[str, str] = {}
    for member in members:
        run_id = str(member["run_id"])
        run = runs.get(run_id)
        if run is None or run.get("unreadable"):
            raise LineageBroken(f"실행 {run_id} 의 출력 루트 {root} 에 읽을 수 있는 실행 기록이 없다")
        names = member["files"]
        if not isinstance(names, list) or any(
            not isinstance(n, str) or not n.startswith("events/") or ".." in n for n in names
        ):
            raise LineageBroken(f"실행 {run_id} 의 계보 기록 files 가 틀렸다")
        if run.get("files") != names or run.get("sha256") != member["sha256"]:
            raise LineageBroken(f"실행 {run_id} 의 실행 기록이 계보 기록과 다르다 ({root})")
        if not run.get("rows") == member["rows"] == member["event_count"]:
            raise LineageBroken(f"실행 {run_id} 의 행 수가 계보 기록과 다르다 ({root})")
        for name in names:
            other = claimed_by.setdefault(name, run_id)
            if other != run_id:
                raise LineageBroken(f"두 실행 {other} · {run_id} 가 같은 파티션을 주장한다: {name}")
        paths = sorted(root.joinpath(name) for name in names)
        missing = [p.relative_to(root).as_posix() for p in paths if not p.is_file()]
        if missing:
            raise LineageBroken(f"실행 {run_id} 가 기록한 파티션이 {root} 에 없다: {missing[:3]}")
        if _files_digest(paths) != member["sha256"]:
            raise LineageBroken(f"실행 {run_id} 의 파티션 내용이 계보 기록의 sha256 과 다르다 ({root})")
        found[run_id] = paths
    return found


def _files_digest(paths: list[Path]) -> str:
    # measurement.sink.EventSink._digest 와 같은 정의다(이름 바이트 + 파일 바이트, 경로 정렬).
    digest = hashlib.sha256()
    for path in paths:
        digest.update(path.name.encode())
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1 << 20), b""):
                digest.update(chunk)
    return digest.hexdigest()


def _derivation_key(record: dict[str, object]) -> tuple[str, bytes]:
    return (str(record.get("parent_run_id") or ""), canonical_json(record.get("mutations")))


def _verified_derivations(
    verifier: Verifier, world: dict[str, object], state_digest: str, parent: object
) -> list[dict[str, object]]:
    found: list[dict[str, object]] = []
    for record in storage.derivations(verifier.hidden_root):
        if record.get("state_digest") != state_digest:
            continue
        if parent is not _ANY and record.get("parent_run_id") != parent:
            continue
        try:
            check_mutations(
                verifier.derivation_base(record, world), record.get("mutations"), state_digest
            )
        except (LineageBroken, KeyError, TypeError):
            continue
        found.append(record)
    return sorted(found, key=_derivation_key)



def resolve_origin(
    verifier: Verifier, world: dict[str, object], state_digest: str
) -> tuple[str | None, list[dict[str, object]]]:
    try:
        runs = sorted(
            str(r["run_id"]) for r in storage.sidecars(verifier.hidden_root)
            if r.get("end_state_digest") == state_digest
        )
        derivations = [
            r for r in storage.derivations(verifier.hidden_root)
            if r.get("state_digest") == state_digest
        ]
    except (OSError, ValueError, KeyError) as error:
        raise LineageBroken("숨김 영역의 계보 기록을 읽을 수 없다") from error
    for run_id in runs:
        try:
            verifier.chain(run_id)
        except LineageBroken:
            continue
        return run_id, []
    verified = _verified_derivations(verifier, world, state_digest, _ANY)
    if verified:
        chosen = verified[0]
        return chosen.get("parent_run_id"), list(chosen["mutations"])
    if runs or derivations:
        raise LineageBroken(
            f"이 상태로 끝난 계보 후보 {len(runs) + len(derivations)}건 중 끝까지 검증되는 것이 없다"
        )
    if state_digest == wd.initial_digest(world["seed"], world["num_customers"], str(world["profile"])):
        return None, []
    raise LineageBroken("이 상태로 이어지는 계보 기록이 없다 — 이어받으면 이전 이력을 잃는다")


def resolve_continuation(
    verifier: Verifier, world: dict[str, object], root: Path, state_digest: str
) -> tuple[str, list[dict[str, object]]]:
    verifier.require_intact(root)
    head = sk.latest_run_id(root)
    if head is None:
        raise LineageBroken(f"{root} 에 계보 머리가 없다")
    record = verifier.sidecar(head)
    if record.get("output_root") != str(root):
        raise LineageBroken(f"계보 머리 {head} 는 {root} 에 쓴 실행이 아니다")
    verifier.chain(head)
    if record.get("end_state_digest") == state_digest:
        return head, []
    verified = _verified_derivations(verifier, world, state_digest, head)
    if verified:
        return head, list(verified[0]["mutations"])
    raise LineageBroken(f"{root} 의 계보 머리 {head} 가 이 상태에서 끝나지 않았다")
