"""실행 기록의 출처 — 저장소 상태(HEAD · 커밋 전 변경 경로 · config 해시)와 ``--require-clean`` 검사 (#262 · #264).

``run_sprint`` 가 실행을 **시작할 때** ``repo_state()`` 를 재고, ``--require-clean`` 이면 ``check_clean()`` 으로
시뮬레이션 전에 멈추며, 끝날 때 ``provenance()`` 로 ``run_meta.provenance`` 를 만든다.

표준 라이브러리만 쓴다. ``run_sprint`` 는 의사결정 모듈 · 시뮬레이터 공개 API 를 import 하므로, 이 기능을
따로 두어야 ML 의존성 없는 환경(3.10 최소 버전 잡)에서도 검사가 실제로 돈다(#264).
"""

from __future__ import annotations

import hashlib
import subprocess
from pathlib import Path
from typing import Any, Mapping

REPO_ROOT = Path(__file__).resolve().parents[2]


#: `run_meta.provenance.repo_dirty_paths` 에 싣는 경로 수 상한. 넘으면 앞에서부터 이만큼만 싣고,
#: 총수는 `repo_dirty_path_count` 에 둔다.
DIRTY_PATHS_LIMIT = 200


class DirtyRepoError(RuntimeError):
    """`--require-clean` 인데 저장소에 커밋 전 변경이 있거나, 그 여부를 확인하지 못했다 (#262).

    시뮬레이션을 시작하기 전에 던진다. 결과 폴더는 만들지 않는다.
    """

    exit_code = 4  # src/main.py 종료 코드 표의 4


def _git(*args: str, strip: bool = True) -> str | None:
    """``git`` 을 부르고 표준 출력을 UTF-8 로 읽는다. 실패하면 ``None`` (#262 · #264).

    ★ **바이트로 받아 직접 디코딩한다**(``text=True`` 를 쓰지 않는다). 텍스트 모드는 로캘 인코딩(CP949 등)으로
      읽어 한글 · 비 UTF-8 경로에서 ``UnicodeDecodeError`` 를 그대로 올리고, 줄바꿈 변환으로 이름 속 CR 을
      LF 로 바꿔 기록했다(#264). 디코딩하지 못하면 ``None`` 이다 — 깨끗하다고 추측하지 않고, 기본 실행은
      ``null_reason`` 으로 남기고 ``--require-clean`` 실행은 시작 전에 멈춘다(종료 코드 4).
    """
    try:
        result = subprocess.run(["git", *args], cwd=REPO_ROOT, capture_output=True, timeout=10, check=False)
    except (OSError, subprocess.SubprocessError):
        return None
    if result.returncode != 0:
        return None
    try:
        out = result.stdout.decode("utf-8")
    except UnicodeDecodeError:
        return None
    return out.strip() if strip else out


def _dirty_paths(porcelain: str) -> list[str]:
    """`git status --porcelain=v1 -z` 출력에서 경로만 뽑는다(저장소 루트 기준).

    이름 바꿈 · 복사 항목은 새 경로 다음 칸에 옛 경로가 오므로 둘 다 싣는다.
    """
    tokens = porcelain.split("\0")
    paths: set[str] = set()
    i = 0
    while i < len(tokens):
        entry = tokens[i]
        i += 1
        if not entry:
            continue
        status, path = entry[:2], entry[3:]
        paths.add(path)
        if "R" in status or "C" in status:
            if i < len(tokens) and tokens[i]:
                paths.add(tokens[i])
            i += 1
    return sorted(paths)


def repo_state() -> dict[str, Any]:
    """지금 저장소 상태 — HEAD · 커밋 전 변경 경로 · 시뮬레이터 커밋 · config 해시 (#262).

    커밋 전 변경은 추적 파일의 변경(스테이징 여부와 무관)과 `.gitignore` 밖의 새 파일이다. 서브모듈은 보지 않는다.
    git 을 쓰지 못하면 ``dirty`` · ``paths`` 가 ``None`` 이다. 깨끗하다고 추측하지 않는다.
    """
    porcelain = _git(
        "status", "--porcelain=v1", "-z", "--untracked-files=all", "--ignore-submodules=all", strip=False
    )
    paths = None if porcelain is None else _dirty_paths(porcelain)
    config_dir = REPO_ROOT / "config"
    return {
        "head": _git("rev-parse", "HEAD"),
        "dirty": None if paths is None else bool(paths),
        "paths": paths,
        "simulator_commit": _git("log", "-1", "--format=%H", "--", "src/simulator"),
        "simulator_dirty": None if paths is None else any(p.startswith("src/simulator/") for p in paths),
        "config_sha256": {
            p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(config_dir.glob("*.yaml"))
        },
    }


def check_clean(state: Mapping[str, Any]) -> None:
    """`--require-clean` 검사. 변경이 있거나 확인하지 못하면 `DirtyRepoError` 를 던진다 (#262)."""
    if state["dirty"] is None:
        raise DirtyRepoError(
            "--require-clean: git 으로 저장소 상태를 읽지 못했다 — 깨끗한지 확인할 수 없어 시작하지 않는다"
        )
    if state["dirty"]:
        paths = state["paths"]
        shown = ", ".join(paths[:10]) + (f" 외 {len(paths) - 10}개" if len(paths) > 10 else "")
        raise DirtyRepoError(
            f"--require-clean: 커밋 전 변경이 {len(paths)}개 있다({shown}) — "
            "커밋하거나 깨끗한 worktree 에서 다시 시작한다"
        )


def _state_changes(start: Mapping[str, Any], end: Mapping[str, Any]) -> list[str] | None:
    """시작 때와 끝날 때 상태의 차이를 문장 목록으로. 어느 한쪽이라도 읽지 못했으면 ``None``."""
    if start["head"] is None or end["head"] is None or start["paths"] is None or end["paths"] is None:
        return None
    changes: list[str] = []
    if start["head"] != end["head"]:
        changes.append(f"HEAD {start['head'][:7]} → {end['head'][:7]}")
    added = sorted(set(end["paths"]) - set(start["paths"]))
    removed = sorted(set(start["paths"]) - set(end["paths"]))
    if added:
        changes.append(f"커밋 전 변경 경로가 생겼다: {', '.join(added[:10])}" + (" …" if len(added) > 10 else ""))
    if removed:
        changes.append(f"커밋 전 변경 경로가 사라졌다: {', '.join(removed[:10])}" + (" …" if len(removed) > 10 else ""))
    for name in sorted(set(start["config_sha256"]) | set(end["config_sha256"])):
        if start["config_sha256"].get(name) != end["config_sha256"].get(name):
            changes.append(f"config/{name} 내용이 바뀌었다")
    return changes


def provenance(start: Mapping[str, Any], *, require_clean: bool = False) -> dict[str, Any]:
    """실행 기록의 출처. **실행을 시작할 때** 잰 저장소 상태(``start``)를 싣는다 (#262).

    끝날 때 한 번 더 재서, 실행 중에 HEAD · 커밋 전 변경 경로 · config 가 바뀌었으면 그 내용을 적는다.
    이미 바뀌어 있던 파일을 실행 중에 또 고친 것은 잡지 못한다. `--require-clean` 실행은 시작 때 바뀐
    파일이 없으므로, 실행 중에 생긴 변경은 모두 경로 차이로 드러난다.
    """
    changes = _state_changes(start, repo_state())
    paths = start["paths"]
    record: dict[str, Any] = {
        "repo_commit": start["head"],
        "repo_worktree_dirty": start["dirty"],
        "repo_dirty_paths": None if paths is None else paths[:DIRTY_PATHS_LIMIT],
        "repo_dirty_path_count": None if paths is None else len(paths),
        "simulator_commit": start["simulator_commit"],
        "simulator_worktree_dirty": start["simulator_dirty"],
        "config_sha256": start["config_sha256"],
        "require_clean": require_clean,
        "repo_changed_during_run": None if changes is None else bool(changes),
        "repo_changes_during_run": changes,
    }
    if paths is None or changes is None:
        record["null_reason"] = "git 으로 저장소 상태를 읽지 못했다 — 깨끗하다고 추측하지 않는다"
    return record
