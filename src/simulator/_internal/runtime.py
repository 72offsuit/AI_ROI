from __future__ import annotations

import itertools
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class Session:
    world: dict[str, object]
    hidden_root: Path
    output_root: Path
    root_head: str | None
    lineage_head: str | None
    pending: list[dict[str, object]] = field(default_factory=list)


@dataclass(frozen=True)
class Snapshot:
    world_id: str
    data: bytes
    lineage_head: str | None
    pending: tuple[dict[str, object], ...]


active: Session | None = None
snapshots: dict[str, Snapshot] = {}
_tokens = itertools.count(1)


def activate(session: Session, *, drop_snapshots: bool) -> None:
    global active
    if drop_snapshots:
        snapshots.clear()
    active = session


def new_token() -> str:
    return f"snap-{next(_tokens):08d}"
