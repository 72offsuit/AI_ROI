"""`scripts/safe_merge.py` — 병합 전 안전장치가 실제로 막는지 (#172).

브랜치 보호를 못 켜는 저장소(private + Free)에서 병합을 막는 것은 이 스크립트 하나다.
그래서 "막아야 할 때 막는가" 를 사고 그대로의 모양으로 고정한다:

  - #141 의 실제 체크 상태(`Tests (with deps)` FAILURE · 리뷰 0건)를 넣으면 막는다
  - 아직 안 뜬 체크 · 진행 중 · SKIPPED 는 통과가 아니다
  - 승인은 작성자가 아닌 리뷰어의 **마지막 판정**으로 센다
  - 막히면 `gh pr merge` 를 **부르지 않는다** — 판정 함수가 맞아도 배선이 틀리면 소용없다
  - 필수 목록은 `pull_request` 이벤트의 필터로만 줄어든다 · 다른 워크플로우의 동명 체크가 필수
    체크를 대신하지 못한다 · 필수 목록이 비거나 못 읽으면 막는다 (PR #238 리뷰 R1~R3)
  - 트리거 · 잡 자리의 표기를 하나라도 못 읽으면 막는다 — 목록이 **일부만** 줄어도 같다.
    기대값은 파서와 따로 정한다(직접 적은 목록 · PyYAML 독립 읽기) (PR #238 리뷰 R4)
  - 따옴표 · 흐름 표기의 연속 줄이 0열이어도 같다 — 블록의 끝으로 오인하지 않는다 (N1). 흐름 안의
    공백 없는 `:` · `? ` 뒤에서 열리는 따옴표도 같다 (P3)
  - 최상위 키 · 이벤트 키 · 잡 ID 가 겹쳐도 같다 — 첫 블록만 읽지 않는다 (중복 키)
  - 서로 다른 잡이 같은 (워크플로우, 체크 이름) 쌍을 내면 막는다 — 한 잡의 보고가 다른 잡을 대신하지
    못한다 (체크 이름 중복)
  - 우회 옵션이 생기지 않는다

`gh` 는 부르지 않는다 — `subprocess.run` 을 바꿔 끼워 PR JSON 을 주입한다.
"""

from __future__ import annotations

import importlib.util
import io
import json
import subprocess
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest import mock

try:
    import yaml
except ImportError:  # 의존성 없는 잡 — 독립 읽기 대조만 BLOCKED 로 빠진다
    yaml = None

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPT = REPO_ROOT / "scripts" / "safe_merge.py"
WORKFLOWS = REPO_ROOT / ".github" / "workflows"

_spec = importlib.util.spec_from_file_location("safe_merge", SCRIPT)
safe_merge = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(safe_merge)

HEAD = "16b2c404ea57b03c58e4d77981b31da0d2685722"
REQUIRED = [
    ("Tests", "격리 경계 + 전체 테스트"),
    ("Tests (with deps)", "의존성 설치 후 전체 테스트"),
]

#: ★ 지금 저장소의 PR 필수 체크 — 파서와 따로 적은 기대값이다. 워크플로우 · 잡을 더하거나
#:   이름을 바꾸면 이 목록과 DR-172 를 함께 고친다(필수 목록이 바뀌는 것을 사람이 보게 한다).
REQUIRED_TODAY = sorted([
    ("Tests", "격리 경계 + 전체 테스트"),
    ("Tests (with deps)", "의존성 설치 후 전체 테스트"),
    ("대시보드 검증", "경로 격리 · 상태 매핑"),
    ("파이썬 3.10 호환", "선언된 최소 버전에서 전체 테스트"),
])
DASHBOARD = ("대시보드 검증", "경로 격리 · 상태 매핑")

_ON_BLOCK = "on:\n  push:\n    branches: [main]\n  pull_request:\n  workflow_dispatch:\n"
#: R4 — 같은 트리거를 다르게 적은 `dashboard.yml` 사본. 기대값은 REQUIRED_TODAY 그대로다.
TRIGGER_NOTATIONS = {
    "큰따옴표 키": ("\n  pull_request:\n", '\n  "pull_request":\n'),
    "작은따옴표 키": ("\n  pull_request:\n", "\n  'pull_request':\n"),
    "키 끝 주석": ("\n  pull_request:\n", "\n  pull_request:  # PR 마다\n"),
    "목록 + 끝 주석": (_ON_BLOCK, "on:\n  - push\n  - pull_request  # 주석\n  - workflow_dispatch\n"),
    "목록 따옴표 항목": (_ON_BLOCK, 'on:\n  - push\n  - "pull_request"\n  - workflow_dispatch\n'),
    "여러 줄 flow 목록": (_ON_BLOCK, "on: [push,\n  pull_request, workflow_dispatch]\n"),
}
#: R4 — `dashboard.yml` 사본 끝에 둘째 잡을 붙인다. 기대값은 REQUIRED_TODAY + (대시보드 검증, extra).
JOB_KEY_NOTATIONS = {
    "평범한 키": "extra:",
    "키 끝 주석": "extra:  # 주석",
    "큰따옴표 키": '"extra":',
    "작은따옴표 키": "'extra':",
}
EXTRA = ("대시보드 검증", "extra")


def _with_extra_job(notation: str):
    key = JOB_KEY_NOTATIONS[notation]
    return lambda text: text.rstrip("\n") + f"\n\n  {key}\n    runs-on: ubuntu-latest\n    steps:\n      - run: echo\n"


def _replaced(old: str, new: str, then=lambda text: text):
    return lambda text: then(text.replace(old, new, 1))


def _before_first_steps(snippet: str):
    """첫 잡의 `steps:` 앞에 `snippet` 을 넣고 둘째 잡을 붙인다."""
    return _replaced("    steps:\n", snippet + "    steps:\n", _with_extra_job("평범한 키"))


def _in_on_before_pull_request(snippet: str):
    """`on:` 안에서 `workflow_dispatch:` 아래에 `snippet` 을 넣고 `pull_request:` 를 그 뒤로 옮긴다."""
    return _replaced("  pull_request:\n  workflow_dispatch:\n",
                     "  workflow_dispatch:\n" + snippet + "  pull_request:\n")


#: N1 — 흐름 컬렉션 · 따옴표 스칼라의 연속 줄을 **0열**에 둔 `dashboard.yml` 사본.
#:   PyYAML 은 받아들이고 체크를 전부 읽는다. 예전 파서는 0열 줄을 블록의 끝으로 읽어 뒤의 트리거 · 잡을
#:   오류 없이 빠뜨렸다. 값: (사본 변형, 필요한 체크, 미보고로 둘 체크).
N1_CONTINUATIONS = {
    # PR #238 리뷰 N1 의 반례 3건
    "on 블록의 flow 목록": (
        _replaced("    branches: [main]\n  pull_request:\n", "    branches: [main,\ndevelop]\n  pull_request:\n"),
        REQUIRED_TODAY, DASHBOARD),
    "잡의 flow 매핑": (
        _replaced("    runs-on: ubuntu-latest\n", '    runs-on: ubuntu-latest\n    env: {A: "1",\nB: "2"}\n',
                  _with_extra_job("평범한 키")),
        [*REQUIRED_TODAY, EXTRA], EXTRA),
    "step 이름의 따옴표 스칼라": (
        _replaced("      - name: 경로 격리\n", '      - name: "경로\n격리"\n', _with_extra_job("평범한 키")),
        [*REQUIRED_TODAY, EXTRA], EXTRA),
    # PR #238 리뷰 P3 의 X1~X4 — 흐름 안의 공백 없는 `:` · `? ` 뒤에서 따옴표가 열린다. 예전 파서는
    #   그 따옴표를 글자로 보고 문자열 속 `}` 를 컬렉션의 끝으로 셌다.
    "X1 공백 없는 값의 큰따옴표": (_before_first_steps('    env: {"A":"}\nB: end"}\n'), [*REQUIRED_TODAY, EXTRA], EXTRA),
    "X2 공백 없는 값의 작은따옴표": (_before_first_steps("    env: {'A':'}\nB: end'}\n"), [*REQUIRED_TODAY, EXTRA], EXTRA),
    "X3 흐름 안 복합 키의 따옴표": (_before_first_steps('    env: {? "}\nB: end"}\n'), [*REQUIRED_TODAY, EXTRA], EXTRA),
    "X4 on 안의 공백 없는 값": (_in_on_before_pull_request('    inputs: {"a":"}\nB: x"}\n'), REQUIRED_TODAY, DASHBOARD),
    # P3 — 같은 계열로 더 찾은 것. PyYAML 만 `?` 를 키 표시로 · `,#` 를 주석으로 읽는다.
    "흐름 안 공백 없는 ? 뒤의 따옴표": (_before_first_steps('    env: {?"}\nB: end"}\n'), [*REQUIRED_TODAY, EXTRA], EXTRA),
    "흐름 구분 문자에 붙은 #": (_in_on_before_pull_request("    inputs: [a,#]\nB: x]\n"), REQUIRED_TODAY, DASHBOARD),
}

#: 중복 키 — PyYAML 은 겹친 키의 마지막 값을 읽고, 예전 파서는 첫 블록만 읽어 뒤의 트리거 · 잡을 오류 없이
#:   빠뜨렸다(PR #238 리뷰 D1~D3). 값의 모양은 `N1_CONTINUATIONS` 와 같다.
DUPLICATE_KEYS = {
    "D1 on 두 번 — 뒤 블록에만 pull_request": (
        _replaced(_ON_BLOCK, "on:\n  push:\n    branches: [main]\non:\n  pull_request:\n  workflow_dispatch:\n"),
        REQUIRED_TODAY, DASHBOARD),
    "D2 jobs 두 번 — 뒤 블록에만 둘째 잡": (
        lambda text: _with_extra_job("평범한 키")(text + "\n" + text[text.index("\njobs:") + 1:]),
        [*REQUIRED_TODAY, EXTRA], EXTRA),
    "D3 pull_request 두 번 — 첫째에만 paths": (
        _replaced("  pull_request:\n  workflow_dispatch:\n",
                  "  pull_request:\n    paths:\n      - docs/**\n  pull_request:\n  workflow_dispatch:\n"),
        REQUIRED_TODAY, DASHBOARD),
}


def _with_jobs(*jobs: tuple[str, str | None]):
    """`dashboard.yml` 사본 끝에 잡을 붙인다 — (잡 ID, `name:` 값 · 없으면 None)."""
    def mutate(text: str) -> str:
        for job_id, name in jobs:
            named = "" if name is None else f"    name: {name}\n"
            text = text.rstrip("\n") + f"\n\n  {job_id}:\n{named}    runs-on: ubuntu-latest\n    steps:\n      - run: echo\n"
        return text
    return mutate


def _dashboard_twin(on: str) -> dict[str, str]:
    """`dashboard.yml` 과 워크플로우 이름 · 잡 이름이 같은 다른 파일. `on` 은 `on:` 블록 그대로."""
    return {"dashboard-twin.yml": f"name: 대시보드 검증\n{on}jobs:\n  twin:\n    name: 경로 격리 · 상태 매핑\n"
                                  "    runs-on: ubuntu-latest\n    steps:\n      - run: echo\n"}


LINT = ("대시보드 검증", "lint")
#: 체크 이름 중복 — 서로 다른 잡이 같은 최종 (워크플로우, 체크 이름) 쌍을 낸다. 보고 대조는 쌍의 집합이라
#:   한 잡의 SUCCESS 가 다른 잡의 미보고를 가렸다(PR #238 리뷰 A~C). D · E 는 같은 계열 — 필수가 아닌
#:   워크플로우의 잡도 같은 head 에 보고될 수 있다. 값: (`dashboard.yml` 변형 · 없으면 None, 더할 파일,
#:   PyYAML 이 읽는 필수 체크 — 겹친 쌍은 겹친 수만큼, 겹친 쌍).
SHARED_CHECK_NAMES = {
    "A 둘째 잡의 name 이 첫 잡과 같다": (
        _with_jobs(("review_extra", "경로 격리 · 상태 매핑")), {}, [*REQUIRED_TODAY, DASHBOARD], DASHBOARD),
    "B name 없는 lint 와 name: lint 인 lint_check": (
        _with_jobs(("lint", None), ("lint_check", "lint")), {}, [*REQUIRED_TODAY, LINT, LINT], LINT),
    "C 다른 파일의 같은 워크플로우 이름 · 잡 이름": (
        None, _dashboard_twin("on:\n  pull_request:\n"), [*REQUIRED_TODAY, DASHBOARD], DASHBOARD),
    "D 경로 필터로 뺀 워크플로우의 같은 쌍": (
        None, _dashboard_twin("on:\n  pull_request:\n    paths:\n      - dashboard/**\n"), REQUIRED_TODAY, DASHBOARD),
    "E PR 이 아닌 트리거(workflow_dispatch)의 같은 쌍": (
        None, _dashboard_twin("on:\n  workflow_dispatch:\n"), REQUIRED_TODAY, DASHBOARD),
}

#: 이름 해석 — 필수가 아닌 워크플로우가 `dashboard.yml` 과 같은 쌍을 다른 표기로 쓴다. YAML 로는 같은 이름인데 예전
#:   파서가 다른 글자로 읽어 겹침을 놓쳤다(PR #238 리뷰 이름 해석). 값: `_twin` 의 인자.
_TWIN_ATTRS = "    runs-on: ubuntu-latest\n    steps:\n      - run: echo\n"
TWIN_TRIGGERS = {
    "workflow_dispatch 전용": "on:\n  workflow_dispatch:\n",
    "pull_request.paths 로 제외": "on:\n  pull_request:\n    paths:\n      - dashboard/**\n",
}
NAME_NOTATIONS = {
    # 리뷰의 처음 네 표기
    "잡 name 의 공백을 \\u0020 으로": {"job": '    name: "경로\\u0020격리 · 상태 매핑"\n' + _TWIN_ATTRS},
    "워크플로우 name 의 공백을 \\u0020 으로": {"workflow": 'name: "대시보드\\u0020검증"\n'},
    "잡 name 을 >- 블록으로": {"job": "    name: >-\n      경로 격리 · 상태 매핑\n" + _TWIN_ATTRS},
    "워크플로우 name 을 >- 블록으로": {"workflow": "name: >-\n  대시보드 검증\n"},
    # 리뷰의 독립 검수 11표기
    "잡 속성을 6칸 들여쓰기": {"job": "      name: 경로 격리 · 상태 매핑\n      runs-on: ubuntu-latest\n"
                                     "      steps:\n        - run: echo\n"},
    "잡 name 을 여러 줄 평범한 스칼라로": {"job": "    name: 경로 격리\n      · 상태 매핑\n" + _TWIN_ATTRS},
    "잡 name 에 앵커": {"job": "    name: &n 경로 격리 · 상태 매핑\n" + _TWIN_ATTRS},
    "잡 name 에 태그": {"job": "    name: !!str 경로 격리 · 상태 매핑\n" + _TWIN_ATTRS},
    "이스케이프한 name 키": {"job": '    "n\\x61me": 경로 격리 · 상태 매핑\n' + _TWIN_ATTRS},
    "복합 키 ? name": {"job": "    ? name\n    : 경로 격리 · 상태 매핑\n" + _TWIN_ATTRS},
    "잡 name 의 공백을 \\x20 으로": {"job": '    name: "경로\\x20격리 · 상태 매핑"\n' + _TWIN_ATTRS},
    "잡 name 을 |- 블록으로": {"job": "    name: |-\n      경로 격리 · 상태 매핑\n" + _TWIN_ATTRS},
    "잡 name 을 별칭으로": {"job": "    env:\n      LABEL: &n 경로 격리 · 상태 매핑\n    name: *n\n" + _TWIN_ATTRS},
    "워크플로우 name 을 여러 줄 평범한 스칼라로": {"workflow": "name: 대시보드\n  검증\n"},
    "워크플로우 name 에 앵커": {"workflow": "name: &w 대시보드 검증\n"},
    # 같은 계열로 더 찾은 것 — 예전 파서는 jobs 앞의 name 만, 겹친 name 키는 첫 값만 읽었다(PyYAML 은 마지막 값)
    "워크플로우 name 을 jobs 뒤에": {"workflow": "", "tail": "name: 대시보드 검증\n"},
    "잡 name 키가 두 번 — 뒤의 값이 같은 이름": {"job": "    name: 다른 이름\n    name: 경로 격리 · 상태 매핑\n" + _TWIN_ATTRS},
}


def _twin(on: str, *, workflow: str = "name: 대시보드 검증\n",
          job: str = "    name: 경로 격리 · 상태 매핑\n" + _TWIN_ATTRS, tail: str = "") -> dict[str, str]:
    """`dashboard.yml` 옆에 둘 쌍둥이 워크플로우 — 기본값은 같은 쌍을 평범하게 쓴 것이다."""
    return {"dashboard-twin.yml": f"{workflow}{on}jobs:\n  twin:\n{job}{tail}"}


def _name_cases():
    for notation, parts in NAME_NOTATIONS.items():
        for trigger, on in TWIN_TRIGGERS.items():
            yield f"{notation} · {trigger}", _twin(on, **parts)


IDEO, NBSP = "\u3000", "\u00a0"
X_WS = ("Shared", f"X{IDEO}")
#: 유니코드 공백 — YAML 의 공백은 스페이스와 탭뿐이고 U+3000 · U+00A0 등은 글자다. 예전 파서는 파이썬의 `strip()` ·
#:   `\s` 로 이 글자를 벗겨 주석이 아닌 줄을 주석으로, 다른 키를 name 으로, 다른 이름을 같은 이름으로 읽었다(이름 해석
#:   적대 검증 — 퍼저 · 값 · 구조 · 배치 네 갈래 17건이 이 한 원인이었다). 값: (추가 파일, PyYAML 로 둘 이상이 내는 필수 쌍).
UNICODE_WHITESPACE = {
    "U+3000 # 로 시작하는 잡 ID 를 주석으로 오인해 잡을 숨김": (
        {"twin.yml": f"name: 대시보드 검증\non: workflow_dispatch\njobs:\n  lead:\n    runs-on: ubuntu-latest\n"
                     f"  {IDEO}#x:\n      name: 경로 격리 · 상태 매핑\n      runs-on: ubuntu-latest\n"}, DASHBOARD),
    "키 앞 U+3000 을 벗겨 name 으로 오인": (
        {"twin.yml": f"name: 대시보드 검증\non: workflow_dispatch\njobs:\n  '경로 격리 · 상태 매핑':\n"
                     f"    runs-on: ubuntu-latest\n    {IDEO}name: other\n"}, DASHBOARD),
    "평범한 이름 끝 U+3000 을 벗겨 다른 이름으로(교차 파일)": (
        {"cross-a.yml": f"name: Shared\non: pull_request\njobs:\n  a:\n    name: 'X{IDEO}'\n    runs-on: x\n",
         "cross-b.yml": f"name: Shared\non:\n  pull_request:\n    paths:\n      - 'docs/**'\njobs:\n  b:\n"
                        f"    name: X{IDEO}\n    runs-on: x\n"}, X_WS),
    "평범한 이름 끝 NBSP# 꼬리를 주석으로 떼어 다른 이름으로": (
        {"cross-a.yml": f"name: Shared\non: pull_request\njobs:\n  a:\n    name: 'X{NBSP}#y'\n    runs-on: x\n",
         "cross-b.yml": f"name: Shared\non: workflow_dispatch\njobs:\n  b:\n    name: X{NBSP}#y\n    runs-on: x\n"},
        ("Shared", f"X{NBSP}#y")),
    "U+3000 paths 를 경로 필터로 오인해 필수에서 뺌": (
        {"twin.yml": f"name: Twin\non:\n  pull_request:\n    {IDEO}paths: [x]\njobs:\n  a:\n    name: X\n"
                     f"    runs-on: x\n  b:\n    name: X\n    runs-on: x\n"}, ("Twin", "X")),
}

_DASHBOARD_TWIN_BODY = "name: 대시보드 검증\non: workflow_dispatch\njobs:\n  twin:\n    name: 경로 격리 · 상태 매핑\n    runs-on: x\n"
#: 파일 이름 — 예전 파서는 `Path.suffix` 로 파일을 골라 대문자 확장자(1라운드)와 점으로만 된 이름(2라운드 — `.yml`,
#:   그리고 파이썬 3.14 에서는 `..yml` 도)을 건너뛰었다. 그 파일의 잡이 겹침 판정에서 통째로 빠진다.
FILE_NAME_MISREADS = {
    "확장자가 대문자": {"extra.YML": _DASHBOARD_TWIN_BODY},
    "점과 확장자뿐인 이름 .yml": {".yml": _DASHBOARD_TWIN_BODY},
    "점이 둘인 이름 ..yaml": {"..yaml": _DASHBOARD_TWIN_BODY},
}


def _workflow_copy(directory: Path, mutate, extra: dict[str, str] | None = None) -> None:
    """실제 워크플로우를 `directory` 에 베끼고 `dashboard.yml` 만 `mutate` 로 바꾼다. `extra` 파일을 더한다."""
    if mutate is None and not extra:
        raise AssertionError("바꾼 것도 더한 것도 없다 — 대조군이 공허하다")
    for path in WORKFLOWS.glob("*.yml"):
        text = path.read_text(encoding="utf-8")
        if path.name == "dashboard.yml" and mutate is not None:
            changed = mutate(text)
            if changed == text:
                raise AssertionError("사본을 바꾸지 못했다 — 대조군이 공허하다")
            text = changed
        (directory / path.name).write_text(text, encoding="utf-8")
    for name, text in (extra or {}).items():
        (directory / name).write_text(text, encoding="utf-8")


def _with_trigger(notation: str):
    old, new = TRIGGER_NOTATIONS[notation]
    return lambda text: text.replace(old, new, 1)


def _yaml_reading(directory: Path) -> tuple[list[tuple[str, str]], list[str]]:
    """PyYAML(BaseLoader — `on` 을 참으로 바꾸지 않는다)로 따로 읽은 (필수 체크, 뺀 워크플로우)."""
    required: list[tuple[str, str]] = []
    excluded: list[str] = []
    for path in sorted(directory.glob("*.yml")):
        doc = yaml.load(path.read_text(encoding="utf-8"), Loader=yaml.BaseLoader)
        on = doc.get("on")
        events = on if isinstance(on, (list, dict)) else [on]
        if "pull_request" not in events:
            continue
        workflow = doc.get("name", path.name)
        settings = on.get("pull_request") if isinstance(on, dict) else None
        if isinstance(settings, dict) and set(settings) & {"paths", "paths-ignore"}:
            excluded.append(workflow)
            continue
        required.extend((workflow, job.get("name", job_id)) for job_id, job in doc["jobs"].items())
    return sorted(required), excluded


def _yaml_job_pairs(directory: Path) -> list[tuple[str, str]]:
    """PyYAML 로 읽은 **모든** 워크플로우 잡의 (워크플로우, 체크 이름) — 트리거와 무관하다. 파일은 이름 끝으로 고르고
    (`.YML` · `.yml` 도), 이름 없는 워크플로우는 GitHub 처럼 `.github/workflows/<파일>` 이다."""
    pairs: list[tuple[str, str]] = []
    for path in sorted(p for p in directory.iterdir() if p.name.lower().endswith((".yml", ".yaml"))):
        doc = yaml.load(path.read_text(encoding="utf-8-sig"), Loader=yaml.BaseLoader)
        workflow = doc.get("name", f".github/workflows/{path.name}")
        pairs.extend((workflow, job.get("name", job_id)) for job_id, job in doc["jobs"].items())
    return pairs


def _run(workflow: str, name: str, conclusion: str | None = "SUCCESS", status: str = "COMPLETED") -> dict:
    return {"__typename": "CheckRun", "workflowName": workflow, "name": name,
            "status": status, "conclusion": conclusion}


def _review(login: str, state: str, at: str, commit: str = HEAD) -> dict:
    return {"author": {"login": login}, "state": state, "submittedAt": at, "commit": {"oid": commit}}


def _pr(**overrides) -> dict:
    base = {
        "number": 999, "title": "t", "url": "u", "state": "OPEN", "isDraft": False,
        "headRefOid": HEAD, "author": {"login": "Danto7632"}, "mergeable": "MERGEABLE",
        "statusCheckRollup": [_run(w, n) for w, n in REQUIRED],
        "reviews": [_review("kwung0206", "APPROVED", "2026-10-23T10:00:00Z")],
    }
    base.update(overrides)
    return base


class TestEvaluate(unittest.TestCase):
    def problems(self, pr: dict) -> list[str]:
        return safe_merge.evaluate(pr, REQUIRED)[1]

    def test_all_green_and_approved_passes(self) -> None:
        self.assertEqual([], self.problems(_pr()))

    def test_the_141_incident_is_blocked(self) -> None:
        """#141 이 병합될 때의 실제 상태 — 체크 하나 FAILURE, 리뷰 0건."""
        pr = _pr(
            statusCheckRollup=[_run("Tests", "격리 경계 + 전체 테스트"),
                               _run("Tests (with deps)", "의존성 설치 후 전체 테스트", "FAILURE")],
            reviews=[],
        )
        problems = self.problems(pr)
        self.assertTrue(any("FAILURE" in p for p in problems), problems)
        self.assertTrue(any("승인" in p for p in problems), problems)

    def test_a_check_that_has_not_appeared_yet_is_not_a_pass(self) -> None:
        """푸시 직후 — 보고된 것만 보면 전부 초록이다."""
        pr = _pr(statusCheckRollup=[_run("Tests", "격리 경계 + 전체 테스트")])
        self.assertTrue(any("보고되지 않았다" in p for p in self.problems(pr)))

    def test_no_checks_at_all_is_not_a_pass(self) -> None:
        problems = safe_merge.evaluate(_pr(statusCheckRollup=None), [])[1]
        self.assertTrue(any("0건" in p for p in problems), problems)

    def test_in_progress_skipped_and_neutral_are_not_passes(self) -> None:
        for status, conclusion in (("IN_PROGRESS", None), ("QUEUED", None),
                                   ("COMPLETED", "SKIPPED"), ("COMPLETED", "NEUTRAL"),
                                   ("COMPLETED", "CANCELLED")):
            with self.subTest(status=status, conclusion=conclusion):
                pr = _pr(statusCheckRollup=[_run("Tests", "격리 경계 + 전체 테스트"),
                                            _run("Tests (with deps)", "의존성 설치 후 전체 테스트",
                                                 conclusion, status)])
                self.assertTrue(self.problems(pr))

    def test_status_context_must_be_success(self) -> None:
        pending = {"__typename": "StatusContext", "context": "ext", "state": "PENDING"}
        pr = _pr(statusCheckRollup=[*_pr()["statusCheckRollup"], pending])
        self.assertTrue(any("PENDING" in p for p in self.problems(pr)))

    def test_comment_only_review_is_not_an_approval(self) -> None:
        pr = _pr(reviews=[_review("kwung0206", "COMMENTED", "2026-10-23T10:00:00Z")])
        self.assertTrue(any("승인" in p for p in self.problems(pr)))

    def test_authors_own_review_does_not_count(self) -> None:
        pr = _pr(reviews=[_review("Danto7632", "APPROVED", "2026-10-23T10:00:00Z")])
        self.assertTrue(any("승인" in p for p in self.problems(pr)))

    def test_latest_verdict_per_reviewer_wins(self) -> None:
        approved_then_changes = _pr(reviews=[
            _review("kwung0206", "APPROVED", "2026-10-23T10:00:00Z"),
            _review("kwung0206", "CHANGES_REQUESTED", "2026-10-23T11:00:00Z"),
        ])
        self.assertTrue(any("변경 요청" in p for p in self.problems(approved_then_changes)))
        changes_then_approved = _pr(reviews=[
            _review("kwung0206", "CHANGES_REQUESTED", "2026-10-23T10:00:00Z"),
            _review("kwung0206", "COMMENTED", "2026-10-23T10:30:00Z"),
            _review("kwung0206", "APPROVED", "2026-10-23T11:00:00Z"),
        ])
        self.assertEqual([], self.problems(changes_then_approved))

    def test_open_change_request_from_another_reviewer_blocks(self) -> None:
        pr = _pr(reviews=[_review("kwung0206", "APPROVED", "2026-10-23T10:00:00Z"),
                          _review("1anminJ", "CHANGES_REQUESTED", "2026-10-23T11:00:00Z")])
        self.assertTrue(any("1anminJ" in p for p in self.problems(pr)))

    def test_stale_approval_is_a_note_not_a_block(self) -> None:
        pr = _pr(reviews=[_review("kwung0206", "APPROVED", "2026-10-23T10:00:00Z", commit="a" * 40)])
        _, problems, notes = safe_merge.evaluate(pr, REQUIRED)
        self.assertEqual([], problems)
        self.assertTrue(any("aaaaaaa" in n for n in notes), notes)

    def test_same_job_name_from_another_workflow_does_not_stand_in(self) -> None:
        """R2 — 필수 잡이 미보고인데 다른 워크플로우 · 외부 상태에 같은 이름의 SUCCESS 가 있다."""
        job = "의존성 설치 후 전체 테스트"
        for stand_in in (_run("Other", job),
                         {"__typename": "StatusContext", "context": job, "state": "SUCCESS"}):
            with self.subTest(stand_in=stand_in.get("__typename")):
                pr = _pr(statusCheckRollup=[_run("Tests", "격리 경계 + 전체 테스트"), stand_in])
                self.assertTrue(any("보고되지 않았다" in p and job in p for p in self.problems(pr)),
                                self.problems(pr))

    def test_an_empty_required_list_blocks(self) -> None:
        """R3 — 보고된 체크가 전부 SUCCESS 이고 승인이 있어도, 무엇을 요구할지 모르면 막는다."""
        problems = safe_merge.evaluate(_pr(), [])[1]
        self.assertTrue(any("필수 체크 목록이 비어 있다" in p for p in problems), problems)

    def test_closed_draft_and_conflicting_are_blocked(self) -> None:
        for overrides in ({"state": "MERGED"}, {"state": "CLOSED"}, {"isDraft": True},
                          {"mergeable": "CONFLICTING"}):
            with self.subTest(**overrides):
                self.assertTrue(self.problems(_pr(**overrides)))


class TestRequiredChecksComeFromTheWorkflows(unittest.TestCase):
    def test_the_job_that_failed_in_141_is_required(self) -> None:
        """사고를 낸 잡이 필수 목록에서 빠지면 이 스크립트는 같은 사고를 다시 통과시킨다."""
        required = safe_merge.required_checks()
        self.assertIn(("Tests (with deps)", "의존성 설치 후 전체 테스트"), required)
        self.assertIn(("Tests", "격리 경계 + 전체 테스트"), required)

    def test_required_list_is_exactly_the_pr_jobs_written_down_today(self) -> None:
        """PR 워크플로우의 잡은 전부 필수이거나 사유와 함께 뺀 것이다 — 조용히 빠지는 것은 없다.

        ★ 기대값을 파서와 따로 적는다. 예전에는 PR 워크플로우 수를 별도 정규식으로 셌는데, 그
          정규식이 파서와 같은 표기(따옴표 키 · 목록 항목)를 못 읽어 둘이 함께 놓쳤고 잡 수는
          아예 대조하지 않았다(PR #238 리뷰 R4)."""
        self.assertEqual(REQUIRED_TODAY, sorted(safe_merge.required_checks()))

    def test_required_list_matches_an_independent_yaml_reading(self) -> None:
        """실제 워크플로우를 YAML 파서로 따로 읽은 결과와 (워크플로우, 잡) 쌍까지 같다."""
        if yaml is None:
            self.skipTest("BLOCKED: PyYAML 미설치 — 독립 YAML 읽기와 대조하지 않았다 (통과가 아니다)")
        required, excluded = _yaml_reading(WORKFLOWS)
        self.assertEqual(required, sorted(safe_merge.required_checks()))
        self.assertEqual(excluded, [w for w, _ in safe_merge.excluded_workflows()])

    def test_another_trigger_notation_keeps_every_check_or_blocks(self) -> None:
        """R4 — 같은 트리거를 다르게 적어도 필수 체크가 하나도 빠지지 않거나, `WorkflowError` 로 막는다."""
        for notation in TRIGGER_NOTATIONS:
            with self.subTest(notation=notation), tempfile.TemporaryDirectory() as tmp:
                d = Path(tmp)
                _workflow_copy(d, _with_trigger(notation))
                if yaml is not None:  # 사본이 정말 같은 뜻인지 — 아니면 이 대조가 공허하다
                    self.assertEqual(_yaml_reading(WORKFLOWS), _yaml_reading(d))
                try:
                    required = sorted(safe_merge.required_checks(d))
                except safe_merge.WorkflowError:
                    continue
                self.assertEqual(REQUIRED_TODAY, required)
                self.assertEqual([], safe_merge.excluded_workflows(d))

    def test_a_second_job_in_any_key_notation_is_required_or_blocks(self) -> None:
        """R4 — 잡 키를 어떻게 적어도 둘째 잡이 필수에 들어가거나, `WorkflowError` 로 막는다."""
        for notation in JOB_KEY_NOTATIONS:
            with self.subTest(notation=notation), tempfile.TemporaryDirectory() as tmp:
                d = Path(tmp)
                _workflow_copy(d, _with_extra_job(notation))
                if yaml is not None:
                    self.assertEqual(sorted([*REQUIRED_TODAY, EXTRA]), _yaml_reading(d)[0])
                try:
                    required = sorted(safe_merge.required_checks(d))
                except safe_merge.WorkflowError:
                    continue
                self.assertEqual(sorted([*REQUIRED_TODAY, EXTRA]), required)

    def _assert_keeps_every_check_or_blocks(self, cases: dict) -> None:
        for label, (mutate, needed, _) in cases.items():
            with self.subTest(case=label), tempfile.TemporaryDirectory() as tmp:
                d = Path(tmp)
                _workflow_copy(d, mutate)
                if yaml is not None:  # PyYAML 이 받아들이고 전부 읽는 사본이어야 반례다
                    self.assertEqual(sorted(needed), _yaml_reading(d)[0])
                try:
                    required = sorted(safe_merge.required_checks(d))
                except safe_merge.WorkflowError:
                    continue
                self.assertEqual(sorted(needed), required)
                self.assertEqual([], safe_merge.excluded_workflows(d))

    def test_a_continuation_at_column_zero_keeps_every_check_or_blocks(self) -> None:
        """N1 — 연속 줄이 0열이어도 필수 체크가 하나도 빠지지 않거나, `WorkflowError` 로 막는다."""
        self._assert_keeps_every_check_or_blocks(N1_CONTINUATIONS)

    def test_a_duplicate_key_keeps_every_check_or_blocks(self) -> None:
        """중복 키 — `on:` · `jobs:` · 이벤트 키가 겹쳐도 필수 체크가 하나도 빠지지 않거나, `WorkflowError` 로 막는다."""
        self._assert_keeps_every_check_or_blocks(DUPLICATE_KEYS)

    def test_a_check_name_made_by_two_jobs_blocks(self) -> None:
        """체크 이름 중복 — 같은 최종 (워크플로우, 체크 이름) 쌍을 내는 잡이 둘이면 `WorkflowError` 다.
        보고는 쌍으로만 구분돼(`statusCheckRollup` 에 잡 ID 가 없다) 한 잡의 보고가 다른 잡을 대신한다."""
        for label, (mutate, extra, needed, shared) in SHARED_CHECK_NAMES.items():
            with self.subTest(case=label), tempfile.TemporaryDirectory() as tmp:
                d = Path(tmp)
                _workflow_copy(d, mutate, extra)
                if yaml is not None:  # PyYAML 로도 그 쌍이 필수이고 잡 둘이 낸다 — 아니면 반례가 아니다
                    self.assertEqual(sorted(needed), _yaml_reading(d)[0])
                    self.assertEqual(2, _yaml_job_pairs(d).count(shared))
                with self.assertRaises(safe_merge.WorkflowError) as raised:
                    safe_merge.required_checks(d)
                self.assertIn(f"{shared[0]} / {shared[1]}", str(raised.exception))

    def test_a_name_notation_is_read_exactly_or_blocks(self) -> None:
        """이름 해석 — 필수가 아닌 워크플로우가 같은 쌍을 어떤 표기로 써도 `WorkflowError` 다(표기를 읽지 않아서든,
        정확히 읽어 겹침을 찾아서든). 예전 파서는 이스케이프 · 블록 · 앵커 등을 글자 그대로 읽어 다른 쌍으로 셌다."""
        for label, extra in _name_cases():
            with self.subTest(case=label), tempfile.TemporaryDirectory() as tmp:
                d = Path(tmp)
                _workflow_copy(d, None, extra)
                if yaml is not None:  # PyYAML 로도 같은 쌍을 잡 둘이 낸다 — 아니면 반례가 아니다
                    self.assertEqual(2, _yaml_job_pairs(d).count(DASHBOARD))
                with self.assertRaises(safe_merge.WorkflowError):
                    safe_merge.required_checks(d)

    def test_unicode_whitespace_is_text_not_space(self) -> None:
        """유니코드 공백 — YAML 이 글자로 읽는 공백을 벗기지 않는다. 같은 쌍을 다른 쌍으로 세거나 줄 · 잡을 숨기던
        사례가 전부 `WorkflowError` 다(겹침을 찾아서든, 키 · 잡 ID 를 읽지 않아서든)."""
        for label, (extra, shared) in UNICODE_WHITESPACE.items():
            with self.subTest(case=label), tempfile.TemporaryDirectory() as tmp:
                d = Path(tmp)
                _workflow_copy(d, None, extra)
                if yaml is not None:  # PyYAML 로는 그 쌍을 잡 둘 이상이 낸다 — 아니면 반례가 아니다
                    self.assertGreaterEqual(_yaml_job_pairs(d).count(shared), 2)
                with self.assertRaises(safe_merge.WorkflowError):
                    safe_merge.required_checks(d)

    def test_every_workflow_file_name_is_read(self) -> None:
        """파일 이름 — 이름이 .yml · .yaml 로 끝나는 파일은 대소문자 · 앞 점과 상관없이 전부 읽어 겹침을 센다."""
        for label, extra in FILE_NAME_MISREADS.items():
            with self.subTest(case=label), tempfile.TemporaryDirectory() as tmp:
                d = Path(tmp)
                _workflow_copy(d, None, extra)
                if yaml is not None:
                    self.assertEqual(2, _yaml_job_pairs(d).count(DASHBOARD))
                with self.assertRaises(safe_merge.WorkflowError):
                    safe_merge.required_checks(d)

    def test_file_level_readings_match_github(self) -> None:
        """대조군 — 맨 앞 BOM 은 벗기고 읽는다. 이름 없는 워크플로우는 GitHub 처럼 `.github/workflows/<파일>` 이다.
        `.` 같은 숫자가 아닌 이름 · 규칙에 맞는 잡 ID(`_ok-1`) · 대문자 확장자 파일도 그대로 읽는다."""
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            (d / "b.yml").write_text("\ufeffname: BOM\non: pull_request\njobs:\n  _ok-1:\n    name: .\n    runs-on: x\n",
                                     encoding="utf-8")
            (d / "n.yml").write_text("on: pull_request\njobs:\n  j:\n    runs-on: x\n", encoding="utf-8")
            (d / "u.YAML").write_text("name: U\non: pull_request\njobs:\n  u:\n    runs-on: x\n", encoding="utf-8")
            expected = [("BOM", "."), (".github/workflows/n.yml", "j"), ("U", "u")]
            if yaml is not None:
                self.assertEqual(sorted(expected), sorted(_yaml_job_pairs(d)))
            self.assertEqual(expected, safe_merge.required_checks(d))

    def test_an_indented_root_is_named_as_such(self) -> None:
        """들여쓴 최상위 매핑은 첫 내용 줄에서 그 이유로 막는다 — 다른 규칙(on 못 찾음)에 기대지 않는다. 적대 검증에서
        들여쓴 루트 안의 따옴표 연속 줄에 숨긴 0열 줄을 진짜 on · jobs 로 읽게 한 사례가 있었다."""
        with self.assertRaisesRegex(safe_merge.WorkflowError, "0열이 아니다"):
            safe_merge._check_top_level_keys(["# 머리 주석", " name: J", " on: push"], "r.yml")
        safe_merge._check_top_level_keys(["---", "name: J", "on: push"], "ok.yml")  # 대조군

    def test_a_non_utf8_file_is_a_workflow_error(self) -> None:
        """UTF-16 파일은 `WorkflowError` 다 — 예전에는 UnicodeDecodeError 가 그대로 올라가 'BLOCKED' 안내 없이 끝났다."""
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            (d / "w.yml").write_bytes("name: W\non: pull_request\njobs:\n  j:\n    runs-on: x\n".encode("utf-16"))
            with self.assertRaises(safe_merge.WorkflowError):
                safe_merge.required_checks(d)

    def test_supported_name_notations_are_read_exactly(self) -> None:
        """이름 해석의 대조군 — 읽기로 한 표기(평범한 한 줄 · 작은따옴표 · 이스케이프 없는 큰따옴표 · 끝 주석 · 일정한
        6칸 속성 · 같은 칸의 steps 목록 · jobs 뒤의 워크플로우 name)는 실제 이름 그대로 읽는다."""
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            (d / "n1.yml").write_text(
                "name: 'N1'\non:\n  pull_request:\njobs:\n  a:\n    name: '작은 따옴표'  # 주석\n    runs-on: x\n"
                "  b:\n    name: \"큰 따옴표\"\n    steps:\n    - run: echo\n    - name: 단계 이름\n      run: echo\n"
                "  c:\n      name: 여섯 칸 속성\n      runs-on: x\n", encoding="utf-8")
            (d / "n2.yml").write_text("on:\n  pull_request:\njobs:\n  d:\n    runs-on: x\nname: 뒤에 둔 이름\n",
                                      encoding="utf-8")
            expected = [("N1", "작은 따옴표"), ("N1", "큰 따옴표"), ("N1", "여섯 칸 속성"), ("뒤에 둔 이름", "d")]
            if yaml is not None:
                self.assertEqual(sorted(expected), _yaml_reading(d)[0])
            self.assertEqual(expected, safe_merge.required_checks(d))

    def test_distinct_final_check_names_are_read_even_when_they_look_alike(self) -> None:
        """체크 이름 중복의 대조군 — 최종 쌍이 다르면 막지 않는다. 다른 워크플로우의 같은 잡 이름, 대소문자만
        다른 이름(보고 대조도 정확한 문자열이다), 다른 잡의 ID 와 같은 `name:`, PR 이 아닌 워크플로우의 다른 쌍."""
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            (d / "u1.yml").write_text(
                "name: U1\non:\n  pull_request:\njobs:\n  lint:\n    runs-on: x\n  upper:\n    name: Lint\n"
                "  a:\n    name: b\n  b:\n    name: c\n", encoding="utf-8")
            (d / "u2.yml").write_text("name: U2\non:\n  pull_request:\njobs:\n  lint:\n    runs-on: x\n",
                                      encoding="utf-8")
            (d / "u3.yml").write_text("name: U1\non:\n  workflow_dispatch:\njobs:\n  lint:\n    name: 배포\n",
                                      encoding="utf-8")
            expected = [("U1", "lint"), ("U1", "Lint"), ("U1", "b"), ("U1", "c"), ("U2", "lint")]
            if yaml is not None:
                self.assertEqual(sorted(expected), _yaml_reading(d)[0])
            self.assertEqual(expected, safe_merge.required_checks(d))

    def test_plain_and_block_scalars_are_not_mistaken_for_open_nodes(self) -> None:
        """N1 대조군 — 여러 줄 표기를 막는 검사가 평범한 스칼라 속 따옴표 · 괄호와 블록 스칼라(`run: |`)
        내용을 열린 표기로 오인하면 정상 PR 이 병합되지 못한다. P3 대조군 — 흐름 안의 공백 없는 값 ·
        복합 키도 한 줄에서 닫히면 읽고, 흐름 안 평범한 스칼라 속 `"` · `'` · `#` · `:` 는 글자다."""
        text = (
            "name: P\non:\n  pull_request:\njobs:\n"
            "  p:\n    name: \"P: 잡\"  # 따옴표 이름\n"
            "    if: ${{ github.event_name == 'pull_request' }}\n"
            "    runs-on: ubuntu-latest  # it's\n"
            "    env: &shared {A: \"1\", B: '2'}\n"
            "    outputs: {\"C\":\"1\", 'D':'}', ? \"E\" : \"]\", f:\"g\"}\n"
            "    services: [a\"b, c'd, -1, a#b, \"h\":i]\n"
            "    steps:\n"
            "      - name: don't [panic\n"
            "        run: |\n          {\n            echo \"it's [ {\n          } > out.txt\n          'x\n"
            "      - name: 'it''s'\n        run: >-\n          echo '\n"
            "      - name: \"a\\\"b\"\n"
            "      - |\n        literal \"\n"
            "  second:\n    name: 둘째\n")
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            (d / "p.yml").write_text(text, encoding="utf-8")
            if yaml is not None:  # 대조군이 실제로 올바른 YAML 이어야 한다
                self.assertEqual([("P", "P: 잡"), ("P", "둘째")], _yaml_reading(d)[0])
            self.assertEqual([("P", "P: 잡"), ("P", "둘째")], safe_merge.required_checks(d))

    def test_quoted_keys_items_and_trailing_comments_are_read(self) -> None:
        """R4 — 막는 것만으로는 부족하다. 읽기로 한 표기는 실제로 읽혀야 정상 PR 이 병합된다."""
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            (d / "q1.yml").write_text(
                "name: Q1\non:\n  'pull_request':\njobs:\n  \"first\":  # 첫 잡\n"
                "    name: \"첫 잡\"  # 이름\n  'second':\n    runs-on: x\n", encoding="utf-8")
            (d / "q2.yml").write_text(
                "name: 'Q2'  # 이름\non:\n  - push  # 푸시\n  - \"pull_request\"\njobs:\n  q:\n    name: Q\n",
                encoding="utf-8")
            (d / "q3.yml").write_text(
                "name: Q3\non: [\"push\", 'pull_request']  # 둘\njobs:\n  q:\n    name: Q\n", encoding="utf-8")
            (d / "q4.yml").write_text(
                "name: Q4\non:\n  \"pull_request\":\n    \"paths\":\n      - src/**\njobs:\n  q:\n    name: Q\n",
                encoding="utf-8")
            # 중복 키 검사의 대조군 — 맨 앞 `---` · 0열 주석 · 따옴표 최상위 키 · 이름이 다른 이벤트와 잡
            (d / "q5.yml").write_text(
                "# 머리 주석\n---\nname: Q5\n'on':\n  push:\n  pull_request:\n  pull_request_target:\n"
                "\"permissions\":\n  contents: read\n# 잡\njobs:\n  q:\n    name: Q\n  q2:\n    name: Q2\n",
                encoding="utf-8")
            self.assertEqual([("Q1", "첫 잡"), ("Q1", "second"), ("Q2", "Q"), ("Q3", "Q"), ("Q5", "Q"), ("Q5", "Q2")],
                             safe_merge.required_checks(d))
            self.assertEqual(["Q4"], [w for w, _ in safe_merge.excluded_workflows(d)])

    def test_no_pull_request_workflow_is_excluded_today(self) -> None:
        """★ 제외가 생기면 그 워크플로우는 PR 에서 안 떠도 병합된다. 의도한 것이면 이 기대값과
        DR-172 를 함께 고친다 — 필수 목록이 줄어드는 것을 사람이 보게 한다."""
        self.assertEqual([], safe_merge.excluded_workflows())

    def test_a_push_only_path_filter_does_not_shrink_the_required_list(self) -> None:
        """R1 — 실제 워크플로우 사본의 `push:` 에만 `paths` 를 넣는다. 필수 목록이 그대로여야 한다."""
        source = REPO_ROOT / ".github" / "workflows"
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            for path in source.glob("*.yml"):
                text = path.read_text(encoding="utf-8")
                if path.name == "tests-with-deps.yml":
                    patched = text.replace("  push:\n    branches: [main]\n",
                                           "  push:\n    branches: [main]\n    paths:\n      - src/**\n", 1)
                    self.assertNotEqual(text, patched, "사본에 push 필터를 넣지 못했다 — 대조군이 공허하다")
                    text = patched
                (d / path.name).write_text(text, encoding="utf-8")
            self.assertEqual(safe_merge.required_checks(), safe_merge.required_checks(d))
            self.assertEqual([], safe_merge.excluded_workflows(d))

    def test_parser_reads_job_names_and_skips_non_pr_or_path_filtered(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            (d / "a.yml").write_text(
                "name: 'A'\n# pull_request 는 주석\non:\n  pull_request:\njobs:\n"
                "  one:\n    name: 첫 잡\n    steps:\n      - name: step\n  two:\n    runs-on: x\n",
                encoding="utf-8")
            (d / "b.yml").write_text("name: B\non:\n  push:\njobs:\n  x:\n    name: X\n", encoding="utf-8")
            (d / "c.yml").write_text(
                "name: C\non:\n  pull_request:\n    paths:\n      - src/**\njobs:\n  y:\n    name: Y\n",
                encoding="utf-8")
            (d / "d.yml").write_text("name: D\n# pull_request\non:\n  push:\njobs:\n  z:\n    name: Z\n",
                                     encoding="utf-8")
            (d / "e.yml").write_text(
                "name: E\non:\n  push:\n    paths-ignore: [docs/**]\n  pull_request:\n    branches: [main]\n"
                "jobs:\n  e:\n    name: 이 잡\n", encoding="utf-8")
            (d / "f.yml").write_text("name: F\non: [push, pull_request]\njobs:\n  f:\n    name: 인라인\n",
                                     encoding="utf-8")
            (d / "g.yml").write_text("name: G\non:\n  - push\n  - pull_request\njobs:\n  g:\n    name: 목록\n",
                                     encoding="utf-8")
            (d / "h.yml").write_text(
                "name: H\non:\n  pull_request:\n    paths-ignore:\n      - docs/**\njobs:\n  h:\n    name: H\n",
                encoding="utf-8")
            self.assertEqual([("A", "첫 잡"), ("A", "two"), ("E", "이 잡"), ("F", "인라인"), ("G", "목록")],
                             safe_merge.required_checks(d))
            self.assertEqual(["C", "H"], [w for w, _ in safe_merge.excluded_workflows(d)])

    def test_unreadable_definitions_raise_instead_of_shrinking(self) -> None:
        """R3 — 읽지 못한 것을 빈 목록으로 두면 필수 대조 없이 병합된다."""
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            with self.assertRaises(safe_merge.WorkflowError):
                safe_merge.required_checks(d)  # 워크플로우 없음 (sparse checkout · 스크립트만 복사)
            with self.assertRaises(safe_merge.WorkflowError):
                safe_merge.required_checks(d / "missing")
            for name, text in (
                    ("jobs-missing.yml", "name: J\non:\n  pull_request:\n"),
                    ("jobs-unreadable.yml", "name: J\non:\n  pull_request:\njobs:\n    deep:\n      name: x\n"),
                    ("inline-on.yml", "name: J\non: {pull_request: {paths: [src/**]}}\njobs:\n  j:\n    name: x\n"),
                    ("inline-event.yml", "name: J\non:\n  pull_request: {paths: [src/**]}\njobs:\n  j:\n    name: x\n"),
                    # R4 — 아래는 예전에 PR 워크플로우가 아닌 것으로 · 잡이 없는 것으로 조용히 넘어갔다
                    ("multiline-flow.yml", "name: J\non: [push,\n  pull_request]\njobs:\n  j:\n    name: x\n"),
                    ("on-after-jobs.yml", "name: J\njobs:\n  j:\n    name: x\non:\n  pull_request:\n"),
                    ("complex-key.yml", "name: J\non:\n  ? pull_request\njobs:\n  j:\n    name: x\n"),
                    ("unclosed-quote.yml", "name: J\non:\n  \"pull_request:\njobs:\n  j:\n    name: x\n"),
                    ("event-value.yml", "name: J\non:\n  pull_request: [opened]\njobs:\n  j:\n    name: x\n"),
                    ("merge-key-job.yml", "name: J\non:\n  pull_request:\njobs:\n  j:\n    name: x\n  <<: *shared\n"),
                    ("inline-job.yml", "name: J\non:\n  pull_request:\njobs:\n  j:\n    name: x\n  k: {runs-on: x}\n"),
                    ("odd-job-indent.yml", "name: J\non:\n  pull_request:\njobs:\n  j:\n    name: x\n   k:\n    name: y\n"),
                    # N1 — 0열 줄이 최상위 키가 아니면 블록의 끝으로 읽지 않는다
                    ("column-zero-in-on.yml",
                     "name: J\non:\n  push:\n    branches: main\ndevelop\n  pull_request:\njobs:\n  j:\n    name: x\n"),
                    ("column-zero-in-jobs.yml",
                     "name: J\non:\n  pull_request:\njobs:\n  j:\n    steps:\n      - name: a\nb\n  k:\n    name: y\n"),
                    # N1 — 여러 줄 따옴표 스칼라 · 흐름 컬렉션은 들여쓰기와 무관하게 여는 줄에서 막는다
                    ("indented-multiline-flow.yml",
                     "name: J\non:\n  pull_request:\njobs:\n  j:\n    env: {A: 1,\n      B: 2}\n  k:\n    name: y\n"),
                    ("anchored-multiline-flow.yml",
                     "name: J\non:\n  pull_request:\njobs:\n  j:\n    env: &e {A: 1,\nB: 2}\n  k:\n    name: y\n"),
                    ("escaped-single-quote.yml",
                     "name: J\non:\n  pull_request:\njobs:\n  j:\n    steps:\n      - name: 'it''s\n"
                     "        x'\n  k:\n    name: y\n"),
                    ("escaped-double-quote.yml",
                     "name: J\non:\n  pull_request:\njobs:\n  j:\n    steps:\n      - name: \"a\\\"\n"
                     "        b\"\n  k:\n    name: y\n"),
                    # P3 — 공백 없는 값의 따옴표도 들여쓴 여러 줄이면 막는다(리뷰 X1i)
                    ("indented-adjacent-value.yml",
                     "name: J\non:\n  pull_request:\njobs:\n  j:\n    env: {\"A\":\"}\n      B: end\"}\n"
                     "  k:\n    name: y\n"),
                    # P3 — 흐름 안에서 YAML 1.2 와 PyYAML 이 토큰을 다르게 나누는 표기는 한 줄이어도 읽지 않는다
                    ("flow-question-without-space.yml",
                     "name: J\non:\n  pull_request:\njobs:\n  j:\n    env: {?a: 1}\n  k:\n    name: y\n"),
                    ("flow-colon-without-node.yml",
                     "name: J\non:\n  pull_request:\njobs:\n  j:\n    env: {:a}\n  k:\n    name: y\n"),
                    ("flow-anchor.yml",
                     "name: J\non:\n  pull_request:\njobs:\n  j:\n    env: {A: &x 1}\n  k:\n    name: y\n"),
                    ("flow-tag.yml",
                     "name: J\non:\n  pull_request:\njobs:\n  j:\n    env: [!t a]\n  k:\n    name: y\n"),
                    ("hash-glued-to-quote.yml",
                     "name: J\non:\n  pull_request:\njobs:\n  j:\n    name: \"a\"#x\n  k:\n    name: y\n"),
                    # 중복 키 — 따옴표를 벗기고 대소문자를 구분하지 않고 비교한다. `true:` 는 `on:` 이다
                    ("duplicate-quoted-on.yml",
                     "name: J\non:\n  push:\n\"on\":\n  pull_request:\njobs:\n  j:\n    name: x\n"),
                    ("duplicate-true-on.yml",
                     "name: J\ntrue:\n  push:\non:\n  pull_request:\njobs:\n  j:\n    name: x\n"),
                    ("duplicate-cased-jobs.yml",
                     "name: J\non:\n  pull_request:\njobs:\n  j:\n    name: x\nJOBS:\n  k:\n    name: y\n"),
                    ("duplicate-name.yml",
                     "name: J\non:\n  pull_request:\nname: K\njobs:\n  j:\n    name: x\n"),
                    ("duplicate-cased-event.yml",
                     "name: J\non:\n  Pull_Request:\n  pull_request:\njobs:\n  j:\n    name: x\n"),
                    ("duplicate-job-id.yml",
                     "name: J\non:\n  pull_request:\njobs:\n  j:\n    name: x\n  'j':\n    name: y\n"),
                    # 0열 줄은 전부 최상위 키다 — 맨 앞 `---` 하나만 예외
                    ("column-zero-non-key.yml",
                     "name: J\n? extra\non:\n  pull_request:\njobs:\n  j:\n    name: x\n"),
                    ("second-document.yml",
                     "name: J\non:\n  pull_request:\njobs:\n  j:\n    name: x\n---\nname: K\n"),
                    # 체크 이름 중복 — PR 이 아닌 · 경로 필터로 뺀 워크플로우의 잡도 겹침을 세려고 읽는다.
                    #   못 읽으면 막는다(4칸 들여쓴 잡은 YAML 로 유효하지만 이 스크립트는 읽지 않는다)
                    ("non-pr-unreadable-job.yml", "name: J\non:\n  push:\njobs:\n    deep:\n      name: x\n"),
                    ("filtered-unreadable-job.yml",
                     "name: J\non:\n  pull_request:\n    paths:\n      - src/**\njobs:\n    deep:\n      name: x\n"),
                    # 이름 해석 — 파서마다 다르게 읽거나 실행 때 정해지는 이름은 읽지 않는다
                    ("cased-job-name-key.yml", "name: J\non:\n  push:\njobs:\n  j:\n    Name: x\n    runs-on: y\n"),
                    ("cased-workflow-name-key.yml", "Name: J\non:\n  push:\njobs:\n  j:\n    runs-on: y\n"),
                    ("expression-name.yml",
                     "name: J\non:\n  push:\njobs:\n  j:\n    name: ${{ 'x' }}\n    runs-on: y\n"),
                    ("typed-number-name.yml", "name: J\non:\n  push:\njobs:\n  j:\n    name: 1.10\n    runs-on: y\n"),
                    ("typed-bool-name.yml", "name: J\non:\n  push:\njobs:\n  j:\n    name: yes\n    runs-on: y\n"),
                    ("null-name.yml", "name: ~\non:\n  push:\njobs:\n  j:\n    runs-on: y\n"),
                    ("empty-name.yml", "name: J\non:\n  push:\njobs:\n  j:\n    name:\n    runs-on: y\n"),
                    ("flow-name.yml", "name: J\non:\n  push:\njobs:\n  j:\n    name: [x]\n    runs-on: y\n"),
                    ("merge-key-attribute.yml",
                     "name: J\non:\n  push:\njobs:\n  j:\n    <<: *base\n    runs-on: y\n"),
                    ("non-key-attribute-line.yml",
                     "name: J\non:\n  push:\njobs:\n  j:\n    runs-on: y\n    stray text\n"),
                    ("stray-list-item.yml", "name: J\non:\n  push:\njobs:\n  j:\n    runs-on: y\n    - z\n"),
                    ("shallower-attribute-indent.yml",
                     "name: J\non:\n  push:\njobs:\n  j:\n      runs-on: y\n    name: x\n"),
                    ("empty-job.yml", "name: J\non:\n  push:\njobs:\n  j:\n  k:\n    runs-on: y\n"),
                    # 적대 검증 — 파서마다 줄 · 문서 · 이름이 달라지는 파일은 읽지 않는다
                    ("line-separator.yml", "name: J\non:\n  push:\n# a\u2028jobs:\njobs:\n  j:\n    runs-on: y\n"),
                    ("next-line.yml", "name: J\non:\n  push:\njobs:\n  j:\x85    runs-on: y\n"),
                    ("indented-root.yml", " name: J\n on:\n   push:\n jobs:\n   j:\n     runs-on: y\n"),
                    ("ideographic-name-key.yml", f"name{IDEO}: J\non:\n  push:\njobs:\n  j:\n    runs-on: y\n"),
                    ("quoted-job-id-with-space.yml",
                     "name: J\non:\n  push:\njobs:\n  '경로 격리':\n    runs-on: y\n"),
                    ("digit-job-id.yml", "name: J\non:\n  push:\njobs:\n  1job:\n    runs-on: y\n"),
                    ("trailing-ws-job-id.yml", f"name: J\non:\n  push:\njobs:\n  twin{IDEO}:\n    runs-on: y\n"),
                    ("matrix-job.yml",
                     "name: J\non:\n  push:\njobs:\n  j:\n    strategy:\n      matrix:\n        v: [1, 2]\n    runs-on: y\n"),
                    ("reusable-call.yml", "name: J\non:\n  push:\njobs:\n  j:\n    uses: ./.github/workflows/x.yml\n"),
                    ("sexagesimal-name.yml",
                     "name: J\non:\n  push:\njobs:\n  j:\n    name: 1:2:3.5\n    runs-on: y\n"),
                    # 2라운드 — 대소문자만 다른 이벤트 이름은 PR 여부를 정할 수 없다
                    ("cased-event-key.yml", "name: J\non:\n  Pull_Request:\njobs:\n  j:\n    runs-on: y\n"),
                    ("cased-event-item.yml", "name: J\non: [push, PULL_REQUEST]\njobs:\n  j:\n    runs-on: y\n")):
                with self.subTest(name=name):
                    for old in d.glob("*.yml"):
                        old.unlink()
                    (d / name).write_text(text, encoding="utf-8")
                    with self.assertRaises(safe_merge.WorkflowError):
                        safe_merge.required_checks(d)


class TestMainWiring(unittest.TestCase):
    """판정이 맞아도 배선이 틀리면 막지 못한다 — `gh pr merge` 호출 여부를 본다."""

    def _main(self, pr: dict, *argv: str) -> tuple[int, list[list[str]]]:
        calls: list[list[str]] = []

        def fake_run(cmd, *args, **kwargs):
            calls.append(list(cmd))
            if cmd[:3] == ["gh", "pr", "view"]:
                return subprocess.CompletedProcess(cmd, 0, stdout=json.dumps(pr), stderr="")
            return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

        with mock.patch.object(safe_merge.subprocess, "run", side_effect=fake_run), \
                mock.patch.object(safe_merge, "required_checks", return_value=REQUIRED), \
                redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            code = safe_merge.main([str(pr["number"]), *argv])
        return code, calls

    @staticmethod
    def _merges(calls: list[list[str]]) -> list[list[str]]:
        return [c for c in calls if c[:3] == ["gh", "pr", "merge"]]

    def test_blocked_pr_is_never_merged(self) -> None:
        code, calls = self._main(_pr(reviews=[]))
        self.assertEqual(1, code)
        self.assertEqual([], self._merges(calls))

    def test_dry_run_never_merges(self) -> None:
        code, calls = self._main(_pr(), "--dry-run")
        self.assertEqual(0, code)
        self.assertEqual([], self._merges(calls))

    def test_passing_pr_is_squash_merged_pinned_to_the_checked_head(self) -> None:
        code, calls = self._main(_pr())
        self.assertEqual(0, code)
        merges = self._merges(calls)
        self.assertEqual(1, len(merges))
        self.assertIn("--squash", merges[0])
        self.assertEqual(HEAD, merges[0][merges[0].index("--match-head-commit") + 1])
        self.assertNotIn("--admin", merges[0])

    def test_unreadable_or_empty_required_list_is_never_merged(self) -> None:
        """R3 — 배선까지: 목록을 못 읽으면 2, 빈 목록이면 1. 둘 다 `gh pr merge` 를 부르지 않는다."""
        for side_effect, expected in ((safe_merge.WorkflowError("없음"), 2), (None, 1)):
            with self.subTest(expected=expected):
                calls: list[list[str]] = []

                def fake_run(cmd, *args, **kwargs):
                    calls.append(list(cmd))
                    return subprocess.CompletedProcess(cmd, 0, stdout=json.dumps(_pr()), stderr="")

                with mock.patch.object(safe_merge.subprocess, "run", side_effect=fake_run), \
                        mock.patch.object(safe_merge, "required_checks", side_effect=side_effect,
                                          return_value=[]), \
                        redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
                    code = safe_merge.main(["999"])
                self.assertEqual(expected, code)
                self.assertEqual([], self._merges(calls))

    def _main_with_workflows(self, directory: Path, pr: dict) -> tuple[int, list[list[str]]]:
        """`required_checks` 를 바꿔 끼우지 않고 **실제 파서**로 `directory` 의 정의를 읽는다."""
        calls: list[list[str]] = []

        def fake_run(cmd, *args, **kwargs):
            calls.append(list(cmd))
            out = json.dumps(pr) if cmd[:3] == ["gh", "pr", "view"] else ""
            return subprocess.CompletedProcess(cmd, 0, stdout=out, stderr="")

        real_required, real_excluded = safe_merge.required_checks, safe_merge.excluded_workflows
        with mock.patch.object(safe_merge.subprocess, "run", side_effect=fake_run), \
                mock.patch.object(safe_merge, "required_checks", lambda: real_required(directory)), \
                mock.patch.object(safe_merge, "excluded_workflows", lambda: real_excluded(directory)), \
                redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            code = safe_merge.main([str(pr["number"])])
        return code, calls

    def test_a_check_dropped_by_notation_is_never_merged_unreported(self) -> None:
        """R4 — 배선까지: 표기만 바꾼 정의에서 그 체크가 미보고이면 종료 0 이 아니고 병합 호출 0회."""
        cases = [(f"트리거 {n}", _with_trigger(n), REQUIRED_TODAY, DASHBOARD) for n in TRIGGER_NOTATIONS]
        cases += [(f"잡 키 {n}", _with_extra_job(n), [*REQUIRED_TODAY, EXTRA], EXTRA) for n in JOB_KEY_NOTATIONS]
        cases += [(f"N1 {n}", *case) for n, case in N1_CONTINUATIONS.items()]
        cases += [(f"중복 키 {n}", *case) for n, case in DUPLICATE_KEYS.items()]
        for label, mutate, needed, missing in cases:
            with self.subTest(case=label), tempfile.TemporaryDirectory() as tmp:
                d = Path(tmp)
                _workflow_copy(d, mutate)
                pr = _pr(statusCheckRollup=[_run(w, n) for w, n in needed if (w, n) != missing])
                code, calls = self._main_with_workflows(d, pr)
                self.assertNotEqual(0, code)
                self.assertEqual([], self._merges(calls))

    def test_a_check_name_shared_by_two_jobs_is_never_merged_on_one_report(self) -> None:
        """체크 이름 중복 — 배선까지: 겹친 쌍이 SUCCESS 한 건으로만 보고되면(한 잡은 미보고) 종료 0 이 아니고
        병합 호출 0회. 나머지 체크는 전부 SUCCESS · 비작성자 승인 · 충돌 없음이다(리뷰의 합성 PR 입력)."""
        for label, (mutate, extra, needed, _) in SHARED_CHECK_NAMES.items():
            with self.subTest(case=label), tempfile.TemporaryDirectory() as tmp:
                d = Path(tmp)
                _workflow_copy(d, mutate, extra)
                pr = _pr(statusCheckRollup=[_run(w, n) for w, n in sorted(set(needed))])
                code, calls = self._main_with_workflows(d, pr)
                self.assertNotEqual(0, code)
                self.assertEqual([], self._merges(calls))

    def test_a_name_notation_never_merges_on_the_twins_report(self) -> None:
        """이름 해석 — 배선까지: 필수 dashboard 잡은 미보고이고 쌍둥이의 SUCCESS 만 그 쌍으로 보고되면 병합 호출 0회.
        나머지 체크는 SUCCESS · 비작성자 승인 · 충돌 없음이다(리뷰의 합성 PR 입력)."""
        for label, extra in _name_cases():
            with self.subTest(case=label), tempfile.TemporaryDirectory() as tmp:
                d = Path(tmp)
                _workflow_copy(d, None, extra)
                code, calls = self._main_with_workflows(d, _pr(statusCheckRollup=[_run(w, n) for w, n in REQUIRED_TODAY]))
                self.assertNotEqual(0, code)
                self.assertEqual([], self._merges(calls))

    def test_a_twin_with_a_different_name_still_merges(self) -> None:
        """위 대조군 — 이름이 정말 다른 쌍둥이는 막지 않는다. 아니면 위 검사는 쌍둥이만 있으면 늘 막는 배선만 본 것이다."""
        for trigger, on in TWIN_TRIGGERS.items():
            with self.subTest(trigger=trigger), tempfile.TemporaryDirectory() as tmp:
                d = Path(tmp)
                _workflow_copy(d, None, _twin(on, job="    name: 경로 격리 · 상태 매핑 (보조)\n" + _TWIN_ATTRS))
                code, calls = self._main_with_workflows(d, _pr(statusCheckRollup=[_run(w, n) for w, n in REQUIRED_TODAY]))
                self.assertEqual(0, code)
                self.assertEqual(1, len(self._merges(calls)))

    def test_the_real_parser_still_merges_when_every_check_is_reported(self) -> None:
        """위 대조군 — 같은 배선에서 전부 보고되면 병합한다. 아니면 위 검사는 늘 막는 배선만 본 것이다."""
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            _workflow_copy(d, _with_extra_job("큰따옴표 키"))
            pr = _pr(statusCheckRollup=[_run(w, n) for w, n in [*REQUIRED_TODAY, EXTRA]])
            code, calls = self._main_with_workflows(d, pr)
        self.assertEqual(0, code)
        self.assertEqual(1, len(self._merges(calls)))

    def test_gh_failure_is_blocked_not_passed(self) -> None:
        def failing(cmd, *args, **kwargs):
            return subprocess.CompletedProcess(cmd, 1, stdout="", stderr="boom")

        with mock.patch.object(safe_merge.subprocess, "run", side_effect=failing), \
                redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            self.assertEqual(2, safe_merge.main(["1"]))


class TestNoBypass(unittest.TestCase):
    def test_options_are_exactly_repo_and_dry_run(self) -> None:
        """★ 우회 옵션(`--admin` · `--force` · `--skip-*`)이 생기면 안전장치가 아니다."""
        options = {opt for action in safe_merge.build_parser()._actions for opt in action.option_strings}
        self.assertEqual({"-h", "--help", "--repo", "--dry-run"}, options)


if __name__ == "__main__":
    unittest.main()
