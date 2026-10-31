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
     못해도 막는다(목록이 조용히 줄면 그 체크는 안 떠도 병합된다). 여러 줄에 걸친 따옴표 ·
     흐름 표기는 어디에 있든 막는다 — 연속 줄이 0열이면 블록이 끝난 것처럼 보인다(N1).
     흐름 안에서 파서마다 토큰을 다르게 나누는 표기도 한 줄이어도 막는다(P3). 최상위 키 · 이벤트
     키 · 잡 ID 가 겹쳐도 막는다 — 파서마다 읽는 블록이 다르다(중복 키). 서로 다른 잡이 같은
     (워크플로우, 체크 이름) 쌍을 내도 막는다 — 보고는 그 쌍으로만 구분된다(체크 이름 중복). 그 판정이
     성립하도록 이름은 정해진 문법으로만 읽고, 그 밖의 표기는 모든 워크플로우에서 막는다(이름 해석).
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


#: YAML 의 공백(s-white)은 스페이스와 탭뿐이다(YAML 1.2.2 §5.5). 파이썬의 인자 없는 `strip()` · 정규식 `\s` 는
#: 유니코드 공백(U+00A0 · U+3000 등 16자)도 벗겨 YAML 과 다르게 읽는다 — 주석이 아닌 줄을 주석으로, 다른 키를
#: `name` 으로, 다른 이름을 같은 이름으로(PR #238 이름 해석 적대 검증). 줄 · 키 · 값을 다듬을 때는 이것만 벗긴다.
_WS = " \t"
#: `\n` · `\r` 이 아닌 줄바꿈 후보 — 파이썬 `splitlines()` 는 줄을 나누고, YAML 1.1(PyYAML)은 NEL · LS · PS 를
#: 줄바꿈으로, YAML 1.2 는 글자로 읽는다. 파서마다 줄이 달라지므로 막는다. `\r` · `\r\n` 은 `read_text` 가 `\n` 으로
#: 바꾸고 YAML 도 줄바꿈으로 읽어 서로 같다.
_ODD_BREAKS = re.compile("[\x0b\x0c\x1c\x1d\x1e\x85\u2028\u2029]")
#: `on:` 키. YAML 1.1 은 따옴표 없는 `on` 을 참(true)으로 읽으므로 그 표기도 받는다.
_ON_KEY = re.compile(r"""^(?:on|"on"|'on'|true):(.*)$""")
#: 블록 매핑의 키 줄 — 따옴표 없는 키 · `"키"` · `'키'`. 값은 `:` 뒤 공백 다음이다.
_KEY_LINE = re.compile(r"""^(?:"([^"\\]+)"|'([^']+)'|([A-Za-z0-9_-]+))[ \t]*:(?:[ \t]+(.*))?$""")
#: 블록 목록의 항목 줄 `- 값`.
_ITEM_LINE = re.compile(r"^-(?:[ \t]+(.*))?$")
#: GitHub 이벤트 이름.
_EVENT = re.compile(r"[A-Za-z_]+")
#: `pull_request` 이벤트에 이 필터가 있으면 PR 마다 돈다는 보장이 없다.
_PATH_FILTERS = ("paths", "paths-ignore")


def _indent(line: str) -> int:
    return len(line) - len(line.lstrip(" "))


def _strip_comment(text: str) -> str:
    """끝 주석을 뗀다. YAML 의 `#` 은 줄 처음이거나 앞에 공백이 있을 때만 주석이다."""
    return re.sub(r"(?:^|[ \t]+)#.*$", "", text).strip(_WS)


def _scalar(text: str) -> str:
    """한 줄 스칼라 값 — 따옴표를 벗기고 끝 주석을 뗀다. 따옴표를 읽지 못하면 `WorkflowError`.

    ★ 큰따옴표 안의 이스케이프(`\\u0020` 등)는 해석하지 않고 막는다 — 글자 그대로 돌려주면 YAML 이 읽는 값과
      달라진다(PR #238 리뷰 이름 해석). 작은따옴표의 `''` 도 읽지 않는다(첫 `'` 에서 끊겨 막힌다)."""
    text = text.strip(_WS)
    if text[:1] in ("'", '"'):
        end = text.find(text[0], 1)
        rest = text[end + 1:].strip(_WS) if end > 0 else None
        if rest is None or (rest and not rest.startswith("#")):
            raise WorkflowError(f"따옴표 값을 읽지 못했다: {text!r}")
        if text[0] == '"' and "\\" in text[1:end]:
            raise WorkflowError(f"큰따옴표 값의 이스케이프는 읽지 않는다: {text!r}")
        return text[1:end]
    return _strip_comment(text)


#: 이름으로 읽지 않는 평범한 스칼라의 첫 글자 — 앵커 · 별칭 · 태그 · 블록 스칼라 · 흐름 · 예약 표시라 값이 글자
#: 그대로가 아니다(PR #238 리뷰 이름 해석).
_NAME_UNREAD_START = "&*!|>{[%@`"
#: 따옴표 없이 쓰면 파서(YAML 1.1 · 1.2)에 따라 문자열이 아닌 값(null · 참거짓 · 숫자 · 날짜)이 되는 표기.
#: 한 글자 y · n 은 YAML 1.1 명세에만 참거짓이고 PyYAML · YAML 1.2 는 문자열로 읽어 넣지 않았다.
_TYPED_PLAIN = re.compile(
    r"(?i)~|null|true|false|yes|no|on|off"
    r"|[-+]?(?:[0-9][0-9_]*(?::[0-5]?[0-9])*|0x[0-9a-f_]+|0o[0-7_]+|0b[01_]+)"
    r"|[-+]?(?:[0-9][0-9_]*(?::[0-5]?[0-9])*\.[0-9_]*|\.[0-9][0-9_]*)(?:e[-+]?[0-9]+)?|[-+]?[0-9][0-9_]*e[-+]?[0-9]+"
    r"|[-+]?\.inf|\.nan|[0-9]{4}-[0-9]{1,2}-[0-9]{1,2}(?:[tT ].*)?")


def _name_value(raw: str, where: str) -> str:
    """워크플로우 · 잡 `name:` 의 값을 실제 이름 그대로 읽는다(PR #238 리뷰 이름 해석).

    받는 것: 한 줄의 평범한 스칼라 · 작은따옴표 · 이스케이프 없는 큰따옴표, 끝 주석. 그 밖은 `WorkflowError` 다 —
    빈 값 · null, 앵커 · 별칭 · 태그 · 블록 스칼라 · 흐름 · 예약 표시, 이스케이프, `${{ }}` 식(실행 때 정해진다),
    따옴표 없이 쓴 숫자 · 참거짓 · null · 날짜 모양, 평범한 스칼라 속 `: `. 이름을 글자 그대로 잘못 읽으면 같은
    쌍을 다른 쌍으로 세어 겹침을 놓친다. 다음 줄로 이어지는지는 호출부가 `_single_line_value` 로 본다.
    """
    text = raw.strip(_WS)
    quoted = text[:1] in ("'", '"')
    if not quoted and (not text or text.startswith("#") or text[0] in _NAME_UNREAD_START
                       or (text[0] in "?:-" and text[1:2] in ("", " ", "\t"))):
        raise WorkflowError(f"{where}: 이름 표기를 읽지 않는다 — 빈 값 · 앵커 · 별칭 · 태그 · 블록 · 흐름 표기는 "
                            f"글자 그대로가 아니다: {text!r}")
    name = _scalar(text)
    if not name:
        raise WorkflowError(f"{where}: 이름이 비어 있다: {text!r}")
    if not quoted and (_TYPED_PLAIN.fullmatch(name) or ": " in name or name.endswith(":")):
        raise WorkflowError(f"{where}: 따옴표 없는 이름 {name!r} 은 파서마다 다른 값으로 읽힐 수 있다 — 따옴표로 감싼다")
    if "${{" in name:
        raise WorkflowError(f"{where}: 식이 든 이름 {name!r} 은 실행 때 정해져 읽지 않는다")
    return name


def _single_line_value(lines: list[str], index: int, key_indent: int, where: str) -> None:
    """`lines[index]` 의 값이 그 줄에서 끝나는지 본다 — 다음 내용 줄이 키보다 깊으면 여러 줄 스칼라다."""
    for line in lines[index + 1:]:
        if not line.strip(_WS) or line.lstrip(_WS).startswith("#"):
            continue
        if _indent(line) > key_indent:
            raise WorkflowError(f"{where}: 이름이 다음 줄로 이어진다 — 여러 줄 스칼라는 읽지 않는다: {line.strip(_WS)!r}")
        return


def _mapping_key(item: str) -> tuple[str, str] | None:
    """블록 매핑 키 줄의 (키, 값 원문). 키 줄이 아니면 None — 호출부가 막을지 정한다."""
    match = _KEY_LINE.match(item)
    if not match:
        return None
    return next(g for g in match.groups()[:3] if g is not None), (match.group(4) or "").strip(_WS)


def _event(text: str, where: str) -> str:
    name = _scalar(text)
    if not _EVENT.fullmatch(name):
        raise WorkflowError(f"{where} 를 이벤트 이름으로 읽지 못했다: {text.strip(_WS)!r}")
    _check_event_case(name, where)
    return name


def _check_event_case(name: str, where: str) -> None:
    """`Pull_Request` 처럼 대소문자만 다른 이벤트 이름은 막는다 — `pull_request` 와 다르다고 보면 그 워크플로우가
    필수에서 조용히 빠지고, 같다고 보면 GitHub 과 다를 수 있다(PR #238 이름 해석 적대 검증 2라운드)."""
    if _key_identity(name) == "pull_request" and name != "pull_request":
        raise WorkflowError(f"{where}: 대소문자가 다른 이벤트 이름(`{name}`)은 읽지 않는다")


def _quote_end(line: str, start: int) -> int:
    """`line[start]` 에서 연 따옴표가 닫히는 위치. 줄 안에서 안 닫히면 -1.

    작은따옴표 안의 `''` 와 큰따옴표 안의 `\\` 이스케이프는 닫는 따옴표가 아니다."""
    quote, i = line[start], start + 1
    while i < len(line):
        if quote == '"' and line[i] == "\\":
            i += 2
            continue
        if line[i] == quote:
            if quote == "'" and line[i + 1:i + 2] == "'":
                i += 2
                continue
            return i
        i += 1
    return -1


#: 흐름 컬렉션의 구분 문자 — 흐름 안에서는 평범한 스칼라도 여기서 끝난다.
_FLOW_INDICATORS = ",[]{}"
#: 흐름 안의 토큰 자리에서 읽지 않는 표시 문자(PR #238 리뷰 P3).
_FLOW_UNREAD = "?:-&*!|>%@`"


def _check_one_line_nodes(line: str, where: str) -> None:
    """한 줄 안에서 따옴표 스칼라와 흐름 컬렉션(`[…]` · `{…}`)이 전부 닫히는지 본다.

    ★ 여러 줄에 걸친 것은 읽지 않고 `WorkflowError` 다(PR #238 리뷰 N1). 이어지는 줄이 0열이면
      블록이 거기서 끝난 것처럼 보여, 뒤의 트리거 · 잡이 오류 없이 필수에서 빠진다.
    따옴표 · 괄호는 토큰 자리에서만 표시다. 평범한 스칼라(`${{ … }}` · `don't`) 속에서는 글자고,
    평범한 스칼라는 `: ` · ` #` 에서, 흐름 안에서는 `,[]{}` 에서도 끝난다.
    ★ 흐름 안에서는 따옴표 · 괄호 바로 뒤의 `:` 도 값 표시다 — `{"A":"…"}` 의 둘째 따옴표가
      스칼라를 연다(PR #238 리뷰 P3). YAML 1.2 와 PyYAML 이 토큰을 다르게 나누는 표기 —
      그 밖의 공백 없는 `:` · `?`, 앵커 · 별칭 · 태그 — 는 흐름 안에서 읽지 않는다.
      토큰 자리에 공백 없이 붙은 `#`(`"a"#` · `[a,#`)는 PyYAML 만 주석으로 읽으므로 어디서든
      읽지 않는다. 평범한 스칼라 속 `a#b` 는 두 쪽 다 글자다.
    """
    depth, plain, after_node, i = 0, False, False, _indent(line)
    while i < len(line):
        c, ahead = line[i], line[i + 1:i + 2]
        spaced = ahead in ("", " ", "\t")
        if c in " \t":
            i += 1
            continue
        if c == "#" and line[i - 1:i] in ("", " ", "\t"):
            break  # 끝 주석
        if plain:
            if c == ":" and (spaced or (depth and ahead in _FLOW_INDICATORS)):
                plain = False  # 값 표시 — 다음은 토큰 자리다
                i += 1
                continue
            if not (depth and c in _FLOW_INDICATORS):
                i += 1
                continue  # 평범한 스칼라 속 글자
            plain = False  # 흐름 구분 문자는 아래에서 토큰으로 읽는다
        after, after_node = after_node, False
        if c == "#":
            raise WorkflowError(f"{where}: 공백 없이 붙은 `#` 는 파서마다 주석 여부가 다르다 — "
                                f"읽지 않는다: {line.strip(_WS)!r}")
        if c in "'\"":
            end = _quote_end(line, i)
            if end < 0:
                raise WorkflowError(f"{where}: 따옴표 스칼라가 줄 안에서 닫히지 않는다 — "
                                    f"여러 줄 따옴표 스칼라는 읽지 않는다: {line.strip(_WS)!r}")
            i, after_node = end + 1, True
            continue
        if c in "[{":
            depth += 1
        elif c in "]}" and depth:
            depth, after_node = depth - 1, True
        elif c == "," and depth:
            pass
        elif c == ":" and (spaced or (depth and (ahead in _FLOW_INDICATORS or after))):
            pass  # 값 표시
        elif c == "?" and spaced:
            pass  # 복합 키 표시
        elif depth and c in _FLOW_UNREAD and (c != "-" or spaced):
            raise WorkflowError(f"{where}: 흐름 표기 안의 `{c}` 는 읽지 않는다 — 파서마다 토큰을 다르게 "
                                f"나누거나 받지 않는다: {line.strip(_WS)!r}")
        elif c == "-" and spaced:
            pass  # 블록 목록 항목
        elif c in "&!":
            while i < len(line) and line[i] not in " \t":
                i += 1  # 앵커 · 태그 — 그 뒤가 값이다
            continue
        else:
            plain = True
        i += 1
    if depth:
        raise WorkflowError(f"{where}: 흐름 컬렉션이 줄 안에서 닫히지 않는다 — "
                            f"여러 줄 `[…]` · `{{…}}` 는 읽지 않는다: {line.strip(_WS)!r}")


#: 블록 스칼라 표시 — `|` · `>` 와 들여쓰기 · chomping 표시.
_BLOCK_SCALAR = re.compile(r"[|>](?:[1-9][+-]?|[+-][1-9]?)?")


def _block_scalar_parent(line: str) -> int | None:
    """`키: |` · `- |` 처럼 블록 스칼라를 여는 줄이면, 내용이 그보다 깊어야 하는 기준 열. 아니면 None."""
    column, rest, dash = _indent(line), line.lstrip(" "), None
    while (item := re.match(r"-(?:[ \t]+|$)", rest)):
        dash, column, rest = column, column + item.end(), rest[item.end():]
    pair = _mapping_key(rest)
    value = pair[1] if pair else rest
    if not _BLOCK_SCALAR.fullmatch(_strip_comment(value)):
        return None
    return column if pair or dash is None else dash


def _check_no_multiline_nodes(lines: list[str], where: str) -> None:
    """파일 전체에서 여러 줄 따옴표 스칼라 · 흐름 컬렉션을 막는다. 블록 스칼라(`run: |`)의 내용은 글자라 보지 않는다."""
    content_deeper_than: int | None = None
    for number, line in enumerate(lines, 1):
        if content_deeper_than is not None:
            if not line.strip(_WS) or _indent(line) > content_deeper_than:
                continue
            content_deeper_than = None
        if not line.strip(_WS) or line.lstrip(_WS).startswith("#"):
            continue
        _check_one_line_nodes(line, f"{where} {number}행")
        content_deeper_than = _block_scalar_parent(line)


def _key_identity(key: str) -> str:
    """중복을 가리는 키 — 따옴표는 `_mapping_key` 가 벗긴다. 대소문자는 구분하지 않는다(Actions 파서는
    키를 대문자로 바꿔 겹치면 거부한다)."""
    return key.casefold()


def _check_top_level_keys(lines: list[str], where: str) -> None:
    """0열 줄은 전부 최상위 키이고, 같은 키가 두 번 나오지 않는다(PR #238 리뷰 중복 키).

    ★ PyYAML 은 겹친 키의 마지막 값을, 이 스크립트는 첫 블록을 읽는다. `on:` · `jobs:` 가 겹치면
      뒤 블록의 트리거 · 잡이 오류 없이 필수에서 빠진다. `true:` 는 `_ON_KEY` 처럼 `on:` 과 같은 키다.
    맨 앞의 문서 시작 표시 `---` 하나만 키가 아닌 0열 줄로 받는다.
    ★ 첫 내용 줄은 0열이어야 한다 — 최상위 매핑을 통째로 들여쓰면 YAML 로는 정상이지만 이 스크립트는 0열 줄만
      최상위 키로 보므로, 그 안의 따옴표 연속 줄 등에 숨긴 0열 줄을 진짜 키로 읽게 된다(PR #238 이름 해석 적대 검증).
    """
    seen: dict[str, int] = {}
    for number, line in enumerate(lines, 1):
        if not line.strip(_WS) or line.lstrip(_WS).startswith("#"):
            continue
        if _indent(line):
            if not seen:
                raise WorkflowError(f"{where} {number}행: 첫 내용 줄이 0열이 아니다 — 들여쓴 최상위 매핑은 읽지 않는다: "
                                    f"{line.strip(_WS)!r}")
            continue
        if not seen and line.rstrip(_WS) == "---":
            seen["---"] = number  # 다음 `---` 는 키가 아니라 아래에서 막힌다(문서 여러 개)
            continue
        pair = _mapping_key(line)
        if pair is None:
            raise WorkflowError(f"{where} {number}행: 0열 줄을 최상위 키로 읽지 못했다: {line.strip(_WS)!r}")
        key = _key_identity(pair[0])
        key = "on" if key == "true" else key
        if key in seen:
            raise WorkflowError(f"{where} {number}행: 최상위 키가 {seen[key]}행과 겹친다(`{pair[0]}`) — "
                                f"파서마다 읽는 블록이 다르다")
        seen[key] = number


def _top_level_boundary(line: str, where: str) -> None:
    """블록을 끝내는 0열 줄은 최상위 키여야 한다. 아니면 블록의 끝을 확인하지 못한 것이다(PR #238 리뷰 N1)."""
    if _mapping_key(line) is None:
        raise WorkflowError(f"{where} 뒤의 0열 줄이 최상위 키가 아니다 — 블록이 어디서 끝나는지 "
                            f"확인하지 못했다: {line.strip(_WS)!r}")


def _pull_request_trigger(head: list[str]) -> tuple[bool, list[str]]:
    """(`pull_request` 로 도는가, **그 이벤트에** 붙은 경로 필터).

    `push.paths` 같은 다른 이벤트의 필터는 보지 않는다 — PR 필수 목록을 줄이지 못한다.

    ★ 읽는 표기를 정해 두고, 그 밖의 줄은 `WorkflowError` 다(PR #238 리뷰 R4). 모르는 표기를
      "PR 워크플로우가 아니다" 로 두면 그 워크플로우의 잡이 사유 없이 필수에서 빠진다.
      읽는 것: `on:` 한 줄 값(이벤트 하나 · 한 줄 `[…]` 목록) · 블록 목록(`- 이벤트`) ·
      블록 매핑(`이벤트:`) — 키와 항목의 따옴표, 끝 주석 포함. 인라인 매핑 `{…}` · 여러 줄
      `[…]` · `jobs:` 뒤의 `on:` · 겹친 이벤트 키는 읽지 않고 실패한다.
    ★ 블록은 다음 0열 줄에서 끝나는데, 그 줄이 최상위 키가 아니면 끝을 확인하지 못한 것이라
      실패한다(PR #238 리뷰 N1). 여러 줄 따옴표 · 흐름 표기는 `_scan` 이 먼저 막는다.
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
            events = [_event(item, "`on: […]` 의 항목") for item in inline[1:-1].split(",") if item.strip(_WS)]
        else:
            events = [_event(inline, "`on:` 의 값")]
        return "pull_request" in events, []
    block = [line for line in head[start + 1:] if line.strip(_WS)]
    end = next((k for k, line in enumerate(block) if _indent(line) == 0), len(block))
    if end < len(block):
        _top_level_boundary(block[end], "`on:` 블록")
    block = block[:end]
    if not block:
        raise WorkflowError("`on:` 아래에 이벤트가 없다")
    child = _indent(block[0])
    found, filters, events = False, [], set()
    for j, line in enumerate(block):
        if _indent(line) > child:
            continue  # 이벤트의 설정 — `pull_request` 의 것만 아래에서 읽는다
        item = line.strip(_WS)
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
        _check_event_case(event, "`on:` 아래 키")
        if _key_identity(event) in events:  # 겹치면 첫 이벤트의 필터만 본다(PR #238 리뷰 중복 키)
            raise WorkflowError(f"`on:` 아래 이벤트가 두 번 나온다(`{event}`) — 파서마다 읽는 설정이 다르다")
        events.add(_key_identity(event))
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
            pair = _mapping_key(setting.strip(_WS))
            if pair is None:
                raise WorkflowError(f"`pull_request:` 아래 줄을 읽지 못했다: {setting.strip(_WS)!r}")
            if pair[0] in _PATH_FILTERS:
                filters.append(pair[0])
    return found, filters


def _workflow_name(lines: list[str], where: str) -> str | None:
    """최상위 `name:` 의 값. 없으면 None. `jobs:` 뒤에 있어도 같은 키라 파일 전체에서 찾는다(PR #238 리뷰 이름 해석)."""
    for index, line in enumerate(lines):
        if _indent(line) or not line.strip(_WS) or line.lstrip(_WS).startswith("#"):
            continue
        pair = _mapping_key(line)
        if pair is None or _key_identity(pair[0]) != "name":
            continue  # 0열의 키가 아닌 줄은 `_check_top_level_keys` 가 막는다
        if pair[0] != "name":
            raise WorkflowError(f"{where} {index + 1}행: 대소문자가 다른 name 키(`{pair[0]}`)는 읽지 않는다")
        _single_line_value(lines, index, 0, f"{where} {index + 1}행 워크플로우 이름")
        return _name_value(pair[1], f"{where} {index + 1}행 워크플로우 이름")
    return None


#: GitHub 잡 ID 규칙 — 문자나 `_` 로 시작하고 영숫자 · `-` · `_` 만 쓴다(워크플로우 문법 `jobs.<job_id>`).
_JOB_ID = re.compile(r"[A-Za-z_][A-Za-z0-9_-]*")
#: 보고되는 체크 이름을 바꾸는 잡 속성 — 재사용 워크플로우 호출(`uses`)은 `<job name> / <reusable job name>` 으로
#: 보고되고(GitHub 문서 '규칙 세트 문제 해결'), matrix(`strategy`)는 `이름 (값, …)` 으로 보인다(관찰 기준 — 형식
#: 명시 문서는 찾지 못했다). 이 스크립트가 정확히 읽을 수 없어 막는다.
_RENAMING_JOB_KEYS = ("strategy", "uses")


def _jobs(lines: list[str], where: str) -> list[tuple[str, str]]:
    """`jobs:` 블록(그 줄 다음부터)의 (잡 ID, 체크 이름). 잡 `name:` 이 없으면 GitHub 처럼 잡 ID 다.

    ★ 잡 자리(2칸)의 줄은 전부 잡 ID 로 읽혀야 한다(PR #238 리뷰 R4). 못 읽은 줄을 건너뛰면 그 잡만 필수에서
      빠지고, 나머지 잡이 있어 아무 오류도 나지 않는다.
    ★ 잡 본문의 칸은 첫 내용 줄이 정한다 — 4칸만 보면 6칸으로 쓴 `name` 을 놓치고 잡 ID 로 조용히 대체한다
      (PR #238 리뷰 이름 해석). 그 칸의 줄은 전부 속성 키이거나, 값이 빈 키 바로 아래의 목록 항목이다. 잡 자리와
      본문 칸 사이의 줄 · 키로 읽지 못한 줄(이스케이프 · 복합 키 `?` · `<<` 등) · 겹친 키 · 대소문자가 다른
      `name` 키 · 본문 없는 잡은 막는다. 본문 칸보다 깊은 줄은 속성의 내용이다(`name` 은 한 줄로 끝나야 한다).
    """
    jobs: list[tuple[str, str]] = []
    job_ids: set[str] = set()
    job: dict | None = None  # {"id", "indent", "keys", "name", "items_ok"}

    def finish() -> None:
        if job is None:
            return
        if job["indent"] is None:
            raise WorkflowError(f"{where}: 잡 `{job['id']}` 의 본문이 없다")
        jobs.append((job["id"], job["name"] or job["id"]))

    for index, line in enumerate(lines):
        if not line.strip(_WS) or line.lstrip(_WS).startswith("#"):
            continue
        indent, item = _indent(line), line.strip(_WS)
        if indent == 0:
            _top_level_boundary(line, f"{where}: `jobs:` 블록")
            break  # 다음 최상위 키
        if indent <= 2 or job is None:
            pair = _mapping_key(item) if indent == 2 else None
            if pair is None or _scalar(pair[1]):
                raise WorkflowError(f"{where}: 잡 자리의 줄을 잡 ID 로 읽지 못했다: {item!r}")
            if not _JOB_ID.fullmatch(pair[0]):
                raise WorkflowError(f"{where}: 잡 ID `{pair[0]}` 가 GitHub 규칙(문자나 _ 로 시작, 영숫자 · - · _)에 "
                                    f"맞지 않는다 — 이름 없는 잡이면 이 ID 가 체크 이름이 된다")
            if _key_identity(pair[0]) in job_ids:  # PR #238 리뷰 중복 키
                raise WorkflowError(f"{where}: 잡 ID가 두 번 나온다(`{pair[0]}`) — 파서마다 읽는 잡이 다르다")
            job_ids.add(_key_identity(pair[0]))
            finish()
            job = {"id": pair[0], "indent": None, "keys": set(), "name": None, "items_ok": False}
            continue
        if job["indent"] is None:
            job["indent"] = indent
        if indent > job["indent"]:
            continue  # 속성의 내용
        if indent < job["indent"]:
            raise WorkflowError(f"{where}: 잡 `{job['id']}` 본문의 들여쓰기가 일정하지 않다: {item!r}")
        if _ITEM_LINE.match(item):
            if not job["items_ok"]:
                raise WorkflowError(f"{where}: 잡 `{job['id']}` 속성 자리의 목록 항목을 읽지 못했다: {item!r}")
            continue  # 바로 위 키(steps 등)의 목록 — 같은 칸에 쓴 목록이다
        pair = _mapping_key(item)
        if pair is None:
            raise WorkflowError(f"{where}: 잡 `{job['id']}` 의 속성 줄을 키로 읽지 못했다 — 이스케이프 · 복합 키 · "
                                f"병합 키는 읽지 않는다: {item!r}")
        key = _key_identity(pair[0])
        if key in job["keys"]:
            raise WorkflowError(f"{where}: 잡 `{job['id']}` 의 속성 `{pair[0]}` 가 두 번 나온다 — 파서마다 읽는 값이 다르다")
        job["keys"].add(key)
        job["items_ok"] = not _strip_comment(pair[1])
        if key in _RENAMING_JOB_KEYS:
            raise WorkflowError(f"{where}: 잡 `{job['id']}` 의 `{pair[0]}` — matrix · 재사용 워크플로우 잡은 보고되는 체크 "
                                f"이름이 바뀌어(`이름 (값, …)` · `호출 / 피호출`) 읽지 않는다. 그런 잡을 넣을 때 이 가드를 함께 고친다")
        if key == "name":
            label = f"{where}: 잡 `{job['id']}` 의 이름"
            if pair[0] != "name":
                raise WorkflowError(f"{label} — 대소문자가 다른 name 키(`{pair[0]}`)는 읽지 않는다")
            _single_line_value(lines, index, indent, label)
            job["name"] = _name_value(pair[1], label)
    finish()
    return jobs


def _scan(workflow_dir: Path) -> tuple[list[tuple[str, str]], list[tuple[str, str]]]:
    """(필수 체크, 필수에서 뺀 워크플로우와 사유). 읽지 못하면 `WorkflowError`."""
    # 파일은 이름 끝으로 고른다 — 확장자 대소문자를 가리지 않고(`x.YML`), 점으로만 된 이름(`.yml` · `..yml`)도 읽는다.
    # `Path.suffix` 는 맨 앞 점을 확장자로 보지 않고 그 규칙이 파이썬 판마다 달라, 그런 파일의 잡이 겹침 판정에서
    # 통째로 빠졌다(PR #238 이름 해석 적대 검증 2라운드).
    files = sorted(p for p in workflow_dir.iterdir()
                   if p.is_file() and p.name.lower().endswith((".yml", ".yaml"))) if workflow_dir.is_dir() else []
    if not files:
        raise WorkflowError(f"워크플로우 파일이 없다: {workflow_dir}")
    required: list[tuple[str, str]] = []
    excluded: list[tuple[str, str]] = []
    made_by: dict[tuple[str, str], list[str]] = {}  # (워크플로우, 체크 이름) → 그 쌍을 내는 잡
    for path in files:
        try:
            text = path.read_text(encoding="utf-8-sig")  # 맨 앞 BOM 은 YAML 처럼 벗긴다
        except UnicodeDecodeError as error:
            raise WorkflowError(f"{path.name}: UTF-8 로 읽지 못했다 — {error}") from error
        odd = _ODD_BREAKS.search(text)
        if odd:
            raise WorkflowError(f"{path.name}: 줄바꿈으로 읽을지 파서마다 다른 문자({odd.group()!r})가 있다 — 읽지 않는다")
        _check_no_multiline_nodes(text.splitlines(), path.name)
        _check_top_level_keys(text.splitlines(), path.name)
        head_text, sep, body = text.partition("\njobs:")
        # 주석 줄은 트리거 판정에서 뺀다 — 설명문 속 "pull_request" 에 속지 않게.
        head = [line for line in head_text.splitlines() if not line.lstrip(_WS).startswith("#")]
        runs_on_pr, filters = _pull_request_trigger(head)
        # ★ 이름과 잡은 PR 워크플로우가 아니어도 같은 문법으로 읽는다 — 경로 필터 · 다른 트리거로 돈 잡도 같은 head 에
        #   보고될 수 있어 겹침을 세야 하고, 이름을 잘못 읽으면 그 겹침을 놓친다(PR #238 리뷰 이름 해석).
        # 이름이 없으면 GitHub 은 저장소 루트 기준 파일 경로를 워크플로우 이름으로 쓴다(워크플로우 문법 `name`).
        workflow = _workflow_name(text.splitlines(), path.name) or f".github/workflows/{path.name}"
        jobs = _jobs(body.splitlines()[1:] if sep else [], path.name)
        if not jobs:
            raise WorkflowError(f"{path.name}: 잡을 하나도 읽지 못했다")
        for job, check in jobs:
            made_by.setdefault((workflow, check), []).append(f"{path.name} `{job}`")
        if not runs_on_pr:
            continue
        if filters:
            excluded.append((workflow, f"{path.name}: pull_request.{' · '.join(filters)} 필터"))
            continue
        required.extend((workflow, check) for _, check in jobs)
    # ★ 보고는 (워크플로우, 체크 이름) 쌍으로만 구분된다 — `statusCheckRollup` 에 잡 ID 가 없다. 같은 쌍을
    #   내는 잡이 둘이면 한 잡의 SUCCESS 가 다른 잡의 미보고를 가린다(PR #238 리뷰 체크 이름 중복).
    for pair in dict.fromkeys(required):
        if len(made_by[pair]) > 1:
            raise WorkflowError(f"필수 체크(`{pair[0]} / {pair[1]}`)를 잡 {len(made_by[pair])}개가 낸다"
                                f"({' · '.join(made_by[pair])}) — 한 잡의 보고가 다른 잡의 미보고를 가린다. "
                                f"체크 이름(잡 `name:` · 없으면 잡 ID)을 고유하게 바꾼다")
    return required, excluded


def required_checks(workflow_dir: Path = WORKFLOWS) -> list[tuple[str, str]]:
    """PR 에서 반드시 보고돼야 하는 (워크플로우 이름, 잡 이름) 목록.

    YAML 파서 없이 이 저장소 워크플로우의 모양(최상위 `name:` · `on:` · `jobs:` 아래 2칸 들여쓴
    잡 ID · 잡 본문 칸(첫 내용 줄)의 `name:`)만 읽는다. 잡 `name:` 이 없으면 GitHub 처럼 잡 ID 를
    체크 이름으로 쓴다. `pull_request` 트리거가 없는 워크플로우, 그리고 **`pull_request` 이벤트에**
    `paths` · `paths-ignore` 필터가 있는 워크플로우는 PR 마다 돈다는 보장이 없으므로 필수에서
    뺀다(`excluded_workflows()` 가 사유를 낸다) — 보고되면 ③이 여전히 SUCCESS 를 요구한다.
    `push.paths` 처럼 다른 이벤트의 필터는 필수 목록을 줄이지 않는다.
    읽을 파일이 없거나, 트리거 · 잡 자리의 줄을 **하나라도** 읽지 못하면 `WorkflowError` 다 —
    일부만 읽고 나머지를 버리면 버린 만큼 필수 목록이 조용히 준다(PR #238 리뷰 R4).
    파일 어디에든 여러 줄에 걸친 따옴표 스칼라 · 흐름 컬렉션(`[…]` · `{…}`)이 있거나, 블록을
    끝내는 0열 줄이 최상위 키가 아니어도 `WorkflowError` 다(N1). 블록 스칼라(`run: |`)의 내용은
    글자라 보지 않는다. 필수 쌍을 내는 잡이 **모든** 워크플로우 파일을 통틀어 둘 이상이어도
    `WorkflowError` 다 — 필수에서 뺀 워크플로우 · PR 이 아닌 워크플로우의 잡도 센다(체크 이름 중복).
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
