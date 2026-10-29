#!/usr/bin/env python3
"""병합 전 안전장치 — 체크 전부 통과 + 승인 1건 이상이 아니면 병합하지 않는다 (#172).

왜 필요한가: 이 저장소는 private + GitHub Free 라 브랜치 보호(필수 체크·필수 리뷰)를
켤 수 없다. 서버가 막아 주지 않으니 #141 이 `Tests (with deps)` 실패 상태로 병합됐다.
GitHub 의 `reviewDecision` 도 보호 규칙이 없으면 계산되지 않아 **늘 빈 문자열**이다
(2026-10-23 기준 최근 PR 60건 전부) — 그래서 승인 여부는 `reviews` 에서 직접 센다.
병합을 실행하는 쪽이 막는 수밖에 없다.

사용 (docs/GIT_WORKFLOW.md §5):

    python3 scripts/safe_merge.py <PR 번호> --dry-run   # 판정만
    python3 scripts/safe_merge.py <PR 번호>             # 판정 → 통과 시 squash 병합

병합 조건 — 하나라도 어기면 병합하지 않고 종료 코드 1:

  ① PR 이 열려 있고 초안이 아니다
  ② `.github/workflows/*.yml` 중 `pull_request` 로 도는 워크플로우의 잡이 **전부**
     체크로 보고됐다. 아직 뜨지 않은 체크는 실패도 성공도 아니어서, 보고된 것만 보면
     통과로 보인다 — 푸시 직후가 그 상태다. 필수 잡은 정확한 (워크플로우, 잡) 쌍으로만
     찾는다. 필수 목록이 비었거나 읽지 못하면 막는다 — 워크플로우 하나 · 잡 하나만 읽지
     못해도 막는다(목록이 조용히 줄면 그 체크는 안 떠도 병합된다).
     필수 목록은 **이 스크립트가 놓인 체크아웃**(작업 폴더가 아니다)의 워크플로우에서 읽는다 —
     최신 `main` 체크아웃에서 실행한다. 이름 변경 처리는 docs/GIT_WORKFLOW.md §5.1.
  ③ 보고된 체크가 **전부** `SUCCESS` 다. `SKIPPED` · `NEUTRAL` · 진행 중은 통과가 아니다.
  ④ 작성자가 아닌 리뷰어의 승인(`APPROVED`)이 1건 이상이고, 마지막 판정이
     변경 요청(`CHANGES_REQUESTED`)인 리뷰어가 없다.
  ⑤ 충돌(`CONFLICTING`)이 없다.

통과하면 `gh pr merge --squash --match-head-commit <판정한 head>` 를 실행한다 —
판정과 병합 사이에 새 커밋이 올라오면 gh 가 병합을 거부한다.

★ 우회 옵션이 없다. `--admin` · `--force` 같은 것을 넣지 않는다. 넣는 순간 이 파일은
  안전장치가 아니라 한 단계 긴 병합 명령이 된다 — 조건을 못 맞추면 조건을 맞춘다.
  `tests/test_safe_merge.py` 가 옵션 목록을 고정한다.
★ 승인 뒤에 커밋이 더 올라온 경우(승인한 커밋 ≠ head)는 막지 않고 `[주의]` 로 알린다.
  근거와 기각한 안은 docs/decisions/DR-172-merge-guard.md.
★ 표준 라이브러리만 쓴다(ISO-005). `gh` 가 PATH 에 있고 로그인돼 있어야 한다.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
WORKFLOWS = REPO_ROOT / ".github" / "workflows"
DEFAULT_REPO = "72offsuit/AI_ROI"

PR_FIELDS = (
    "number,title,url,state,isDraft,headRefOid,author,reviews,statusCheckRollup,mergeable"
)

#: 리뷰어의 판정을 바꾸는 리뷰 상태. `COMMENTED` 는 판정을 바꾸지 않는다(GitHub 규칙).
_VERDICT_STATES = ("APPROVED", "CHANGES_REQUESTED", "DISMISSED")


class WorkflowError(ValueError):
    """필수 체크 목록을 만들지 못했다 — 판정 기준이 없으니 병합하지 않는다."""


#: `on:` 키. YAML 1.1 은 따옴표 없는 `on` 을 참(true)으로 읽으므로 그 표기도 받는다.
_ON_KEY = re.compile(r"""^(?:on|"on"|'on'|true):(.*)$""")
#: 블록 매핑의 키 줄 — 따옴표 없는 키 · `"키"` · `'키'`. 값은 `:` 뒤 공백 다음이다.
_KEY_LINE = re.compile(r"""^(?:"([^"\\]+)"|'([^']+)'|([A-Za-z0-9_-]+))\s*:(?:\s+(.*))?$""")
#: 블록 목록의 항목 줄 `- 값`.
_ITEM_LINE = re.compile(r"^-(?:\s+(.*))?$")
#: GitHub 이벤트 이름.
_EVENT = re.compile(r"[A-Za-z_]+")
#: `pull_request` 이벤트에 이 필터가 있으면 PR 마다 돈다는 보장이 없다.
_PATH_FILTERS = ("paths", "paths-ignore")


def _indent(line: str) -> int:
    return len(line) - len(line.lstrip(" "))


def _strip_comment(text: str) -> str:
    """끝 주석을 뗀다. YAML 의 `#` 은 줄 처음이거나 앞에 공백이 있을 때만 주석이다."""
    return re.sub(r"(?:^|\s+)#.*$", "", text).strip()


def _scalar(text: str) -> str:
    """한 줄 스칼라 값 — 따옴표를 벗기고 끝 주석을 뗀다. 따옴표를 읽지 못하면 `WorkflowError`."""
    text = text.strip()
    if text[:1] in ("'", '"'):
        end = text.find(text[0], 1)
        rest = text[end + 1:].strip() if end > 0 else None
        if rest is None or (rest and not rest.startswith("#")):
            raise WorkflowError(f"따옴표 값을 읽지 못했다: {text!r}")
        return text[1:end]
    return _strip_comment(text)


def _mapping_key(item: str) -> tuple[str, str] | None:
    """블록 매핑 키 줄의 (키, 값 원문). 키 줄이 아니면 None — 호출부가 막을지 정한다."""
    match = _KEY_LINE.match(item)
    if not match:
        return None
    return next(g for g in match.groups()[:3] if g is not None), (match.group(4) or "").strip()


def _event(text: str, where: str) -> str:
    name = _scalar(text)
    if not _EVENT.fullmatch(name):
        raise WorkflowError(f"{where} 를 이벤트 이름으로 읽지 못했다: {text.strip()!r}")
    return name


def _pull_request_trigger(head: list[str]) -> tuple[bool, list[str]]:
    """(`pull_request` 로 도는가, **그 이벤트에** 붙은 경로 필터).

    `push.paths` 같은 다른 이벤트의 필터는 보지 않는다 — PR 필수 목록을 줄이지 못한다.

    ★ 읽는 표기를 정해 두고, 그 밖의 줄은 `WorkflowError` 다(PR #238 리뷰 R4). 모르는 표기를
      "PR 워크플로우가 아니다" 로 두면 그 워크플로우의 잡이 사유 없이 필수에서 빠진다.
      읽는 것: `on:` 한 줄 값(이벤트 하나 · 한 줄 `[…]` 목록) · 블록 목록(`- 이벤트`) ·
      블록 매핑(`이벤트:`) — 키와 항목의 따옴표, 끝 주석 포함. 인라인 매핑 `{…}` · 여러 줄
      `[…]` · `jobs:` 뒤의 `on:` 은 읽지 않고 실패한다.
    """
    start = next((i for i, line in enumerate(head) if _ON_KEY.match(line)), None)
    if start is None:
        raise WorkflowError("`jobs:` 앞에서 최상위 `on:` 을 찾지 못했다")
    inline = _strip_comment(_ON_KEY.match(head[start]).group(1))
    if inline:  # `on: pull_request` · `on: [push, pull_request]` — 필터가 들어갈 자리가 없다
        if inline.startswith("{"):
            raise WorkflowError(f"인라인 매핑 `on: {inline}` 은 읽지 않는다")
        if inline.startswith("["):
            if not inline.endswith("]"):
                raise WorkflowError(f"여러 줄 목록 `on: {inline}` 은 읽지 않는다")
            events = [_event(item, "`on: […]` 의 항목") for item in inline[1:-1].split(",") if item.strip()]
        else:
            events = [_event(inline, "`on:` 의 값")]
        return "pull_request" in events, []
    block = [line for line in head[start + 1:] if line.strip()]
    block = block[:next((k for k, line in enumerate(block) if _indent(line) == 0), len(block))]
    if not block:
        raise WorkflowError("`on:` 아래에 이벤트가 없다")
    child = _indent(block[0])
    found, filters = False, []
    for j, line in enumerate(block):
        if _indent(line) > child:
            continue  # 이벤트의 설정 — `pull_request` 의 것만 아래에서 읽는다
        item = line.strip()
        listed = _ITEM_LINE.match(item)
        key = None if listed else _mapping_key(item)
        if _indent(line) < child or (listed is None and key is None):
            raise WorkflowError(f"`on:` 아래 줄을 읽지 못했다: {item!r}")
        if listed:
            found = _event(listed.group(1) or "", "`on:` 목록 항목") == "pull_request" or found
            continue
        event, value = key
        if not _EVENT.fullmatch(event):
            raise WorkflowError(f"`on:` 아래 키를 이벤트 이름으로 읽지 못했다: {event!r}")
        if event != "pull_request":
            continue
        value = _scalar(value)
        if value.startswith("{"):
            raise WorkflowError(f"인라인 매핑 `pull_request: {value}` 은 읽지 않는다")
        if value not in ("", "~", "null"):
            raise WorkflowError(f"`pull_request:` 의 값을 읽지 못했다: {value!r}")
        found = True
        sub = block[j + 1:]
        sub = sub[:next((k for k, s in enumerate(sub) if _indent(s) <= child), len(sub))]
        for setting in sub:
            if _indent(setting) != _indent(sub[0]):
                continue
            pair = _mapping_key(setting.strip())
            if pair is None:
                raise WorkflowError(f"`pull_request:` 아래 줄을 읽지 못했다: {setting.strip()!r}")
            if pair[0] in _PATH_FILTERS:
                filters.append(pair[0])
    return found, filters


def _scan(workflow_dir: Path) -> tuple[list[tuple[str, str]], list[tuple[str, str]]]:
    """(필수 체크, 필수에서 뺀 워크플로우와 사유). 읽지 못하면 `WorkflowError`."""
    files = sorted([*workflow_dir.glob("*.yml"), *workflow_dir.glob("*.yaml")]) if workflow_dir.is_dir() else []
    if not files:
        raise WorkflowError(f"워크플로우 파일이 없다: {workflow_dir}")
    required: list[tuple[str, str]] = []
    excluded: list[tuple[str, str]] = []
    for path in files:
        text = path.read_text(encoding="utf-8")
        head_text, sep, body = text.partition("\njobs:")
        # 주석 줄은 트리거 판정에서 뺀다 — 설명문 속 "pull_request" 에 속지 않게.
        head = [line for line in head_text.splitlines() if not line.lstrip().startswith("#")]
        runs_on_pr, filters = _pull_request_trigger(head)
        if not runs_on_pr:
            continue
        names = [pair[1] for line in head if _indent(line) == 0
                 for pair in [_mapping_key(line)] if pair and pair[0] == "name"]
        workflow = (_scalar(names[0]) if names else "") or path.name
        if filters:
            excluded.append((workflow, f"{path.name}: pull_request.{' · '.join(filters)} 필터"))
            continue
        jobs: list[tuple[str, str]] = []
        job_id: str | None = None
        job_name: str | None = None
        for line in body.splitlines()[1:] if sep else []:
            if not line.strip() or line.lstrip().startswith("#"):
                continue
            if _indent(line) == 0:
                break  # 다음 최상위 키
            if _indent(line) < 4:
                # ★ 잡 자리(2칸)의 줄은 전부 잡 ID 로 읽혀야 한다(PR #238 리뷰 R4). 못 읽은 줄을
                #   건너뛰면 그 잡만 필수에서 빠지고, 나머지 잡이 있어 아무 오류도 나지 않는다.
                pair = _mapping_key(line.strip()) if _indent(line) == 2 else None
                if pair is None or _scalar(pair[1]):
                    raise WorkflowError(f"{path.name}: 잡 자리의 줄을 잡 ID 로 읽지 못했다: {line.strip()!r}")
                if job_id is not None:
                    jobs.append((workflow, job_name or job_id))
                job_id, job_name = pair[0], None
                continue
            pair = _mapping_key(line.strip()) if _indent(line) == 4 else None
            if pair and pair[0] == "name" and job_id is not None and job_name is None:
                job_name = _scalar(pair[1]) or None
        if job_id is not None:
            jobs.append((workflow, job_name or job_id))
        if not jobs:
            raise WorkflowError(f"{path.name}: pull_request 워크플로우인데 잡을 하나도 읽지 못했다")
        required.extend(jobs)
    return required, excluded


def required_checks(workflow_dir: Path = WORKFLOWS) -> list[tuple[str, str]]:
    """PR 에서 반드시 보고돼야 하는 (워크플로우 이름, 잡 이름) 목록.

    YAML 파서 없이 이 저장소 워크플로우의 모양(최상위 `name:` · `on:` · `jobs:` 아래 2칸 들여쓴
    잡 ID · 4칸 들여쓴 잡 `name:`)만 읽는다. 잡 `name:` 이 없으면 GitHub 처럼 잡 ID 를
    체크 이름으로 쓴다. `pull_request` 트리거가 없는 워크플로우, 그리고 **`pull_request` 이벤트에**
    `paths` · `paths-ignore` 필터가 있는 워크플로우는 PR 마다 돈다는 보장이 없으므로 필수에서
    뺀다(`excluded_workflows()` 가 사유를 낸다) — 보고되면 ③이 여전히 SUCCESS 를 요구한다.
    `push.paths` 처럼 다른 이벤트의 필터는 필수 목록을 줄이지 않는다.
    읽을 파일이 없거나, 트리거 · 잡 자리의 줄을 **하나라도** 읽지 못하면 `WorkflowError` 다 —
    일부만 읽고 나머지를 버리면 버린 만큼 필수 목록이 조용히 준다(PR #238 리뷰 R4).
    """
    return _scan(workflow_dir)[0]


def excluded_workflows(workflow_dir: Path = WORKFLOWS) -> list[tuple[str, str]]:
    """`pull_request` 로 돌지만 경로 필터 때문에 필수에서 뺀 (워크플로우, 사유)."""
    return _scan(workflow_dir)[1]


def _check_label(check: dict) -> tuple[str, str]:
    return (check.get("workflowName") or "", check.get("name") or check.get("context") or "")


def _check_passed(check: dict) -> tuple[bool, str]:
    """(통과 여부, 상태 문자열). CheckRun 은 완료 + SUCCESS, StatusContext 는 SUCCESS 만."""
    if check.get("__typename") == "StatusContext":
        state = check.get("state") or "UNKNOWN"
        return state == "SUCCESS", state
    status = check.get("status") or "UNKNOWN"
    conclusion = check.get("conclusion") or ""
    if status != "COMPLETED":
        return False, status
    return conclusion == "SUCCESS", conclusion or "UNKNOWN"


def evaluate(pr: dict, required: list[tuple[str, str]]) -> tuple[list[str], list[str], list[str]]:
    """(통과한 것, 막힌 것, 주의) — 막힌 것이 하나라도 있으면 병합하지 않는다."""
    ok: list[str] = []
    problems: list[str] = []
    notes: list[str] = []

    # ① 상태
    if pr.get("state") != "OPEN":
        problems.append(f"PR 상태가 OPEN 이 아니다: {pr.get('state')}")
    elif pr.get("isDraft"):
        problems.append("초안(draft) PR 이다")
    else:
        ok.append("PR 이 열려 있고 초안이 아니다")

    # ②③ 체크 — 필수 Actions 잡은 정확한 (워크플로우, 잡) 쌍으로만 찾는다. 다른 워크플로우의
    # 동명 잡이나 같은 이름의 외부 상태(StatusContext)는 그 자리를 대신하지 못한다.
    checks = pr.get("statusCheckRollup") or []
    reported = {_check_label(c) for c in checks}
    if not required:
        problems.append("필수 체크 목록이 비어 있다 — 무엇이 보고돼야 하는지 모르면 판정하지 않는다")
    for workflow, job in required:
        if (workflow, job) not in reported:
            problems.append(f"필수 체크가 보고되지 않았다: {workflow} / {job} — 아직 안 떴거나 돌지 않았다")
    if not checks:
        problems.append("보고된 체크가 0건이다 — 통과한 체크가 없다")
    for check in checks:
        passed, state = _check_passed(check)
        workflow, name = _check_label(check)
        label = f"{workflow} / {name}" if workflow else name
        if passed:
            ok.append(f"체크 SUCCESS: {label}")
        else:
            problems.append(f"체크가 SUCCESS 가 아니다: {label} → {state}")

    # ④ 리뷰 — 리뷰어마다 마지막 판정만 본다. 작성자 자신의 리뷰는 세지 않는다.
    author = (pr.get("author") or {}).get("login")
    head = pr.get("headRefOid") or ""
    latest: dict[str, dict] = {}
    reviews = sorted(pr.get("reviews") or [], key=lambda r: r.get("submittedAt") or "")
    for review in reviews:
        login = (review.get("author") or {}).get("login")
        if not login or login == author or review.get("state") not in _VERDICT_STATES:
            continue
        latest[login] = review
    approvers = sorted(login for login, r in latest.items() if r.get("state") == "APPROVED")
    blockers = sorted(login for login, r in latest.items() if r.get("state") == "CHANGES_REQUESTED")
    if approvers:
        ok.append(f"승인 {len(approvers)}건: {', '.join(approvers)}")
    else:
        problems.append("작성자가 아닌 리뷰어의 승인(APPROVED)이 0건이다")
    for login in blockers:
        problems.append(f"변경 요청이 해소되지 않았다: {login}")
    for login in approvers:
        commit = ((latest[login].get("commit") or {}).get("oid")) or ""
        if head and commit and commit != head:
            notes.append(
                f"{login} 의 승인은 {commit[:7]} 에 대한 것이고 head 는 {head[:7]} 다 — "
                "승인 뒤 커밋을 리뷰어가 봤는지 확인한다"
            )

    # ⑤ 충돌
    mergeable = pr.get("mergeable")
    if mergeable == "CONFLICTING":
        problems.append("main 과 충돌한다 (CONFLICTING)")
    elif mergeable != "MERGEABLE":
        notes.append(f"병합 가능 여부를 GitHub 가 아직 계산하지 않았다: {mergeable} — 충돌이면 gh 가 거부한다")

    return ok, problems, notes


def _gh(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["gh", *args], capture_output=True, text=True)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="체크 전부 SUCCESS + 승인 1건 이상일 때만 squash 병합한다 (#172). 우회 옵션은 없다.",
    )
    parser.add_argument("pr", type=int, help="PR 번호")
    parser.add_argument("--repo", default=DEFAULT_REPO, help=f"OWNER/NAME (기본 {DEFAULT_REPO})")
    parser.add_argument("--dry-run", action="store_true", help="판정만 하고 병합하지 않는다")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        viewed = _gh("pr", "view", str(args.pr), "--repo", args.repo, "--json", PR_FIELDS)
    except FileNotFoundError:
        print("BLOCKED: gh 가 PATH 에 없다 — 판정하지 못했다. 병합하지 않았다.", file=sys.stderr)
        return 2
    if viewed.returncode != 0:
        print(f"BLOCKED: gh pr view 실패 — 판정하지 못했다. 병합하지 않았다.\n{viewed.stderr.strip()}",
              file=sys.stderr)
        return 2
    pr = json.loads(viewed.stdout)
    try:
        required = required_checks()
        excluded = excluded_workflows()
    except (WorkflowError, OSError) as error:
        print(f"BLOCKED: 필수 체크 목록을 만들지 못했다 — {error}. 병합하지 않았다.", file=sys.stderr)
        return 2
    ok, problems, notes = evaluate(pr, required)
    notes.extend(f"필수에서 뺀 워크플로우: {workflow} — {reason}" for workflow, reason in excluded)

    print(f"PR #{pr.get('number')} {pr.get('title', '')}")
    print(f"head {(pr.get('headRefOid') or '')[:12]} · 필수 체크 {len(required)}종 "
          f"({WORKFLOWS} 에서 읽음 — 이 스크립트가 놓인 체크아웃의 정의)")
    for line in ok:
        print(f"  [통과] {line}")
    for line in problems:
        print(f"  [막힘] {line}")
    for line in notes:
        print(f"  [주의] {line}")

    if problems:
        print(f"\n병합하지 않았다 — 막힌 항목 {len(problems)}건. 조건을 맞춘 뒤 다시 실행한다.")
        return 1
    if args.dry_run:
        print("\n병합 조건 충족 (dry-run — 병합하지 않았다).")
        return 0

    head = pr["headRefOid"]
    print(f"\n병합 조건 충족 — gh pr merge {args.pr} --squash --match-head-commit {head[:12]}")
    merged = subprocess.run(
        ["gh", "pr", "merge", str(args.pr), "--repo", args.repo, "--squash",
         "--match-head-commit", head],
    )
    return merged.returncode


if __name__ == "__main__":
    sys.exit(main())
