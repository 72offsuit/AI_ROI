"""파트 격리 규칙 검사.

시뮬레이터(출제자)와 의사결정 시스템(수험생)이 서로를 참조하지 못하게 강제한다.
gitignore와 달리 이 검사는 위반 시 실패하므로 실제 방어선이 된다.

규칙의 근거: Plan/AI_Retention_ROI_PRD_v2.md §10 · §21 · §80,
Plan/AI_Customer_Retention_ROI_SRS_v2.0.md ISO-001~005, docs/data_spec.html §17

실행:
    python3 -m unittest tests.test_isolation -v
"""

from __future__ import annotations

import ast
import gzip
import json
import os
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"

# ── 모듈이 import할 수 없는 대상 ─────────────────────────────────────────────
FORBIDDEN_IMPORTS: dict[str, tuple[str, ...]] = {
    "src.decision": ("src.simulator", "src.diagnostics"),
    "src.simulator": ("src.decision", "src.diagnostics"),
    "src.measurement": ("src.simulator", "src.decision", "src.diagnostics"),
    "src.orchestration": ("src.simulator._internal", "src.diagnostics"),
}

# ── 모듈이 참조할 수 없는 데이터 경로 ───────────────────────────────────────
FORBIDDEN_PATHS: dict[str, tuple[str, ...]] = {
    "src.decision": ("data/hidden", "data/ground_truth"),
    "src.measurement": ("data/hidden", "data/ground_truth"),
    "src.orchestration": ("data/hidden", "data/ground_truth"),
    "src.simulator": ("results/",),
}

# ── 어떤 모듈도 import해서는 안 되는 대상 ───────────────────────────────────
NEVER_IMPORTED = "src.diagnostics"


def _module_name(path: Path) -> str:
    """레포 루트 기준 파일 경로를 점 표기 모듈명으로 바꾼다."""
    rel = path.relative_to(REPO_ROOT).with_suffix("")
    parts = list(rel.parts)
    if parts[-1] == "__init__":
        parts.pop()
    return ".".join(parts)


def _iter_source_files():
    if not SRC_ROOT.is_dir():
        return
    for path in sorted(SRC_ROOT.rglob("*.py")):
        yield path, _module_name(path)


def _imported_modules(tree: ast.AST) -> list[tuple[str, int]]:
    """(import된 모듈 경로, 줄 번호) 목록. 상대 import는 절대 경로로 정규화하지 않는다."""
    found: list[tuple[str, int]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                found.append((alias.name, node.lineno))
        elif isinstance(node, ast.ImportFrom):
            if node.level == 0 and node.module:
                found.append((node.module, node.lineno))
    return found


def _string_constants(tree: ast.AST) -> list[tuple[str, int]]:
    return [
        (node.value, node.lineno)
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant) and isinstance(node.value, str)
    ]


def _under(module: str, package: str) -> bool:
    return module == package or module.startswith(package + ".")


class TestPartIsolation(unittest.TestCase):
    """파트 간 import 경계."""

    def test_forbidden_imports(self) -> None:
        violations: list[str] = []
        for path, module in _iter_source_files():
            owner = next(
                (pkg for pkg in FORBIDDEN_IMPORTS if _under(module, pkg)), None
            )
            if owner is None:
                continue
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            for imported, lineno in _imported_modules(tree):
                for banned in FORBIDDEN_IMPORTS[owner]:
                    if _under(imported, banned):
                        violations.append(
                            f"{path.relative_to(REPO_ROOT)}:{lineno} "
                            f"— {owner} 는 {banned} 를 import할 수 없다 (발견: {imported})"
                        )
        self.assertEqual([], violations, "\n" + "\n".join(violations))

    def test_diagnostics_is_never_imported(self) -> None:
        """진단 모듈은 어디에서도 import되지 않는다. 리포트 단계에서 독립 실행한다."""
        violations: list[str] = []
        for path, module in _iter_source_files():
            if _under(module, NEVER_IMPORTED):
                continue
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            for imported, lineno in _imported_modules(tree):
                if _under(imported, NEVER_IMPORTED):
                    violations.append(
                        f"{path.relative_to(REPO_ROOT)}:{lineno} "
                        f"— {NEVER_IMPORTED} 는 어떤 모듈도 import할 수 없다"
                    )
        self.assertEqual([], violations, "\n" + "\n".join(violations))


class TestDataPathIsolation(unittest.TestCase):
    """민감 데이터 경로 참조 경계."""

    def test_forbidden_data_paths(self) -> None:
        violations: list[str] = []
        for path, module in _iter_source_files():
            owner = next(
                (pkg for pkg in FORBIDDEN_PATHS if _under(module, pkg)), None
            )
            if owner is None:
                continue
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            for text, lineno in _string_constants(tree):
                for banned in FORBIDDEN_PATHS[owner]:
                    if banned in text:
                        violations.append(
                            f"{path.relative_to(REPO_ROOT)}:{lineno} "
                            f"— {owner} 는 '{banned}' 경로를 참조할 수 없다 (발견: {text!r})"
                        )
        self.assertEqual([], violations, "\n" + "\n".join(violations))


class TestPartLayout(unittest.TestCase):
    """파트 디렉터리와 지침 파일이 제자리에 있는지."""

    REQUIRED_DIRS = (
        "src/measurement",
        "src/simulator",
        "src/simulator/_internal",
        "src/decision",
        "src/diagnostics",
        "src/orchestration",
    )

    def test_part_directories_exist(self) -> None:
        missing = [d for d in self.REQUIRED_DIRS if not (REPO_ROOT / d).is_dir()]
        self.assertEqual([], missing, f"파트 디렉터리 누락: {missing}")

    def test_each_part_has_agent_guides(self) -> None:
        """Codex와 Claude 양쪽이 읽도록 AGENTS.md와 CLAUDE.md를 함께 둔다."""
        missing: list[str] = []
        for d in ("src", *self.REQUIRED_DIRS):
            for guide in ("AGENTS.md", "CLAUDE.md"):
                target = REPO_ROOT / d / guide
                if not target.is_file():
                    missing.append(f"{d}/{guide}")
        self.assertEqual([], missing, f"지침 파일 누락: {missing}")

    def test_claude_md_delegates_to_agents_md(self) -> None:
        """CLAUDE.md는 내용을 복제하지 않고 AGENTS.md를 import한다."""
        offenders: list[str] = []
        for d in ("src", *self.REQUIRED_DIRS):
            target = REPO_ROOT / d / "CLAUDE.md"
            if target.is_file() and "@AGENTS.md" not in target.read_text(encoding="utf-8"):
                offenders.append(f"{d}/CLAUDE.md")
        self.assertEqual([], offenders, f"@AGENTS.md import 누락: {offenders}")


# ── Hidden Trait 이름과 값의 봉쇄 (S2 #76) ──────────────────────────────────
# 헌법 목록 — SRS SIM-002 의 16종(저장 이름, `base_order_value` 는 SRS `average_order_value`)과
# 생성 라벨. config 에서 읽은 이름을 더하지만, config 가 없거나 이름을 지워도 이 목록은 남는다.
SRS_HIDDEN_TRAITS = (
    "base_visit_frequency", "base_purchase_probability", "base_order_value", "purchase_cycle",
    "price_sensitivity", "coupon_sensitivity", "shipping_fee_sensitivity", "brand_loyalty",
    "repurchase_propensity", "base_churn_propensity", "marketing_responsiveness",
    "marketing_fatigue", "search_propensity", "cart_abandonment_propensity",
    "cs_contact_propensity", "review_propensity",
)
HIDDEN_LABELS = ("persona", "hidden_traits")
SIMULATOR_CONFIG = REPO_ROOT / "config" / "simulator_config.yaml"

# 숨은 이름이 문자열 상수로 나와도 되는 곳: 생성·저장 모듈, 금지 이름 목록, 사후 채점.
HIDDEN_NAME_HOMES = frozenset({
    "src/simulator/_internal/world.py",
    "src/simulator/_internal/persona.py",
    "src/simulator/_internal/traits.py",
    "src/simulator/_internal/genconfig.py",
    "src/measurement/schema.py",
})
HIDDEN_NAME_HOME_DIRS = ("src/diagnostics/",)


def _config_trait_names(path: Path) -> set[str]:
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
        return {t["name"] for t in document["hidden_traits"] if isinstance(t["name"], str)}
    except (OSError, ValueError, KeyError, TypeError):
        return set()


def hidden_names(config_path: Path = SIMULATOR_CONFIG) -> frozenset[str]:
    return frozenset(SRS_HIDDEN_TRAITS) | frozenset(HIDDEN_LABELS) | _config_trait_names(config_path)


def _name_pattern(names: frozenset[str]) -> re.Pattern[str]:
    # 식별자 경계로 찾는다 — `persona` 가 `personal` 이나 다른 식별자의 일부일 때는 세지 않는다.
    alternatives = "|".join(re.escape(n) for n in sorted(names, key=len, reverse=True))
    return re.compile(rf"(?<![A-Za-z0-9_])(?:{alternatives})(?![A-Za-z0-9_])")


def hidden_name_findings(source: str, label: str, names: frozenset[str]) -> list[str]:
    pattern = _name_pattern(names)
    return [
        f"{label}:{lineno} — {match!r}"
        for text, lineno in _string_constants(ast.parse(source))
        for match in pattern.findall(text)
    ]


class TestHiddenNameConfinement(unittest.TestCase):
    """Hidden Trait·페르소나 이름은 생성·저장 모듈 밖에서 문자열로 쓰이지 않는다 (정적 AST)."""

    def test_hidden_names_appear_only_in_their_homes(self) -> None:
        names = hidden_names()
        violations: list[str] = []
        for path, _module in _iter_source_files():
            rel = path.relative_to(REPO_ROOT).as_posix()
            if rel in HIDDEN_NAME_HOMES or rel.startswith(HIDDEN_NAME_HOME_DIRS):
                continue
            violations += hidden_name_findings(path.read_text(encoding="utf-8"), rel, names)
        self.assertEqual([], violations, "\n" + "\n".join(violations))

    def test_scanner_catches_planted_names(self) -> None:
        planted = (
            'a = "coupon_sensitivity"\n'
            'b = f"trait:{a} persona"\n'
            'c = "marketing_fatigue_extra · personal"\n'
            '"""문서 문자열의 hidden_traits."""\n'
        )
        findings = hidden_name_findings(planted, "planted", hidden_names())
        self.assertEqual(3, len(findings), findings)
        for expected in ("coupon_sensitivity", "'persona'", "hidden_traits"):
            self.assertTrue(any(expected in f for f in findings), findings)

    def test_constitution_survives_a_missing_or_shrunk_config(self) -> None:
        constitution = frozenset(SRS_HIDDEN_TRAITS) | frozenset(HIDDEN_LABELS)
        with tempfile.TemporaryDirectory() as tmp:
            missing = Path(tmp) / "absent.yaml"
            self.assertEqual(constitution, hidden_names(missing))
            shrunk = Path(tmp) / "shrunk.yaml"
            shrunk.write_text('{"hidden_traits": [{"name": "new_trait"}]}', encoding="utf-8")
            self.assertEqual(constitution | {"new_trait"}, hidden_names(shrunk))


def _gunzipped_text(path: Path) -> str:
    raw = path.read_bytes()
    if path.name.endswith(".gz"):
        raw = gzip.decompress(raw)
    return raw.decode("utf-8", errors="replace")


def _config_persona_ids(path: Path = SIMULATOR_CONFIG) -> set[str]:
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
        return {p["id"] for p in document["personas"] if isinstance(p["id"], str)}
    except (OSError, ValueError, KeyError, TypeError):
        return set()


class Fingerprints:
    """숨김 영역의 상태에서 뽑은 누수 지문.

    - 고객별 Trait 사전의 정준 JSON(문자열 그대로 찾는다)
    - 페르소나 id — 식별자 경계로 찾는다. `seg-<id>-v1`·`C00000001,<id>`·`segment=<id>`·`persona=<id>/`
      처럼 따옴표 없이 다른 글자에 붙어도 잡는다. 다른 식별자의 일부(`<id>_x`)는 세지 않는다
    - Trait 이름과 생성 라벨(`persona`·`hidden_traits`) — 식별자 경계. 공개 경계에서는 이름도 싣지 않는다
    """

    def __init__(self, state: dict[str, object], persona_ids: set[str]) -> None:
        customers = state["customers"]
        self.literals = sorted({
            json.dumps(c["hidden_traits"], sort_keys=True, separators=(",", ":")) for c in customers
        })
        ids = persona_ids | {c["persona"] for c in customers}
        self.personas = _name_pattern(frozenset(ids))
        self.names = _name_pattern(frozenset(customers[0]["hidden_traits"]) | frozenset(HIDDEN_LABELS))

    def findings(self, haystacks: dict[str, str]) -> list[str]:
        found: set[str] = set()
        for where, text in haystacks.items():
            found.update(f"{where}: {lit[:40]}" for lit in self.literals if lit in text)
            found.update(f"{where}: {m}" for m in self.personas.findall(text))
            found.update(f"{where}: {m}" for m in self.names.findall(text))
        return sorted(found)


def output_haystacks(root: Path) -> dict[str, str]:
    """출력 루트의 파일 내용(gz 는 풀어서)과, 디렉터리·파일의 상대 경로 이름 전체."""
    haystacks = {
        path.relative_to(root).as_posix(): _gunzipped_text(path)
        for path in sorted(root.rglob("*")) if path.is_file()
    }
    haystacks["<출력 루트 경로 이름>"] = "\n".join(
        path.relative_to(root).as_posix() for path in sorted(root.rglob("*"))
    )
    return haystacks


# 자식 프로세스에서 도는 탐침. 공개 API 로 세계를 돌리고, 대표 오류 경로를 일부러 밟아 메시지를 모은 뒤
# 결과를 JSON 한 줄로 낸다. 판정(지문 대조)은 부모가 표준 라이브러리만으로 한다.
_PROBE_MARK = "@@probe@@"
_PROBE = r'''
import hashlib, json, sys
from pathlib import Path
from unittest import mock

from src.measurement import schema as sc
from src.measurement import sink as sk
from src.simulator import api
from src.simulator._internal import genconfig, storage, traits

work = Path(sys.argv[1])
out, hidden = work / "out", work / "hidden"
errors = []


def attempt(label, call):
    try:
        call()
    except Exception as error:  # 공개 경계를 넘는 예외의 메시지를 모두 모은다
        errors.append([label, type(error).__name__, str(error)])
    else:
        errors.append([label, None, ""])


def plant(state_path, edit):
    doc = json.loads(state_path.read_text(encoding="ascii"))
    edit(doc)
    data = json.dumps(doc, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("ascii")
    sid = "state-" + hashlib.sha256(data).hexdigest()[:16]
    (state_path.parent / f"{sid}.json").write_bytes(data)
    return sid


with mock.patch.object(sk, "parquet_available", return_value=False):
    api.init(11, 40, "smoke", out, hidden_root=hidden)
    api.apply_treatment({"C00000001": "T3", "C00000002": "T0"})
    summary = api.advance(3)
    token = api.snapshot()
    state_id = api.save_state()
    events = list(api.events(summary.end))
    returned = [
        summary, token, state_id, events,
        api.metrics(summary.start, summary.end), api.exchange_bundle(summary.end),
    ]

    attempt("init 인자 오류", lambda: api.init(True, 1, "smoke", work / "e1", hidden_root=hidden))
    attempt("배정 오류", lambda: api.apply_treatment({"C99999999": "T9"}))
    attempt("모르는 스냅샷", lambda: api.restore("snap-x", output_root=work / "e2"))
    attempt("없는 상태", lambda: api.load_state("state-0000000000000000", work / "e3", hidden_root=hidden))

    state_path = hidden / "states" / f"{state_id}.json"
    config = genconfig.active()
    tables = traits.tables(config)
    first, last = config.trait_names[0], config.trait_names[-1]

    def out_of_range(doc):
        c = doc["customers"][0]
        c["hidden_traits"][first] = tables[first][c["persona"]].hi + 1

    def not_integer(doc):
        doc["customers"][0]["hidden_traits"][first] = 0.5

    def unknown_persona(doc):
        doc["customers"][0]["persona"] += "_x"

    def missing_trait(doc):
        doc["customers"][0]["hidden_traits"].pop(last)

    def missing_label(doc):
        doc["customers"][0].pop("persona")

    def in_range(doc):
        c = doc["customers"][0]
        v = c["hidden_traits"][last]
        c["hidden_traits"][last] = v + 1 if v < tables[last][c["persona"]].hi else v - 1

    for label, edit in (
        ("범위 밖 Trait", out_of_range), ("정수 아닌 Trait", not_integer),
        ("모르는 페르소나", unknown_persona), ("빠진 Trait", missing_trait),
        ("빠진 생성 라벨", missing_label), ("범위 안 위조(계보)", in_range),
    ):
        attempt("위조 상태: " + label, lambda edit=edit, label=label: api.load_state(
            plant(state_path, edit), work / ("e-" + str(len(errors))), hidden_root=hidden))

    text = genconfig.CONFIG_PATH.read_text(encoding="utf-8")
    broken_doc = json.loads(text)
    beta = next(t for t in broken_doc["hidden_traits"] if t["family"] == "beta")
    beta["mu_ppm"][next(iter(beta["mu_ppm"]))] = 0  # 원인 메시지에 Trait 이름·페르소나 id 가 들어가는 위반
    broken = work / "broken.yaml"
    broken.write_text(json.dumps(broken_doc), encoding="utf-8")
    with mock.patch.object(genconfig, "_ACTIVE", None), mock.patch.object(genconfig, "CONFIG_PATH", broken):
        attempt("config 위반: init", lambda: api.init(1, 3, "smoke", work / "e4", hidden_root=hidden))
        attempt("config 위반: load_state", lambda: api.load_state(state_id, work / "e5", hidden_root=hidden))
    other_doc = json.loads(text)
    other_doc["config_version"] = "sim-gen-probe"
    beta = next(t for t in other_doc["hidden_traits"] if t["family"] == "beta")
    pid = next(iter(beta["mu_ppm"]))
    beta["mu_ppm"][pid] += 1
    with mock.patch.object(genconfig, "_ACTIVE", genconfig.parse(json.dumps(other_doc))):
        attempt("config 변경: load_state", lambda: api.load_state(state_id, work / "e6", hidden_root=hidden))
        attempt("config 변경: advance", lambda: api.advance(1))
        attempt("config 변경: events", lambda: list(api.events(summary.end)))
    # 실험용 설정 파일(config_path)을 고른 경로도 같은 공개 메시지 규칙을 따른다(#183 ②). 파일 이름에 Trait
    # 이름을 넣어, 호출자가 준 경로가 공개 메시지로 새는지도 함께 본다.
    experiment = work / f"experiment-{first}.yaml"
    experiment.write_text(json.dumps(other_doc), encoding="utf-8")
    broken_experiment = work / f"broken-{last}.yaml"
    broken_experiment.write_text(json.dumps(broken_doc), encoding="utf-8")
    attempt("실험 설정 불일치: load_state", lambda: api.load_state(
        state_id, work / "e7", hidden_root=hidden, config_path=experiment))
    attempt("실험 설정 위반: init", lambda: api.init(
        1, 3, "smoke", work / "e8", hidden_root=hidden, config_path=broken_experiment))
    attempt("실험 설정 없음: load_state", lambda: api.load_state(
        state_id, work / "e9", hidden_root=hidden, config_path=work / f"missing-{first}.yaml"))

print(PROBE_MARK + json.dumps({
    "state_id": state_id,
    "returned": repr(returned),
    "errors": errors,
    "event_keys": sorted({k for e in events for k in e}),
    "event_fields": [f.name for f in sc.EVENT_FIELDS],
    "default_hidden_root": str(storage.default_hidden_root().resolve()),
}))
'''


def probe_environment() -> dict[str, str]:
    """자식 프로세스 환경. 부모의 `PYTHON*` 변수를 모두 빼고 필요한 것만 다시 넣는다.

    `PYTHONVERBOSE`·`PYTHONPROFILEIMPORTTIME` 등은 인터프리터가 stderr 에 모듈 이름
    (`src.simulator._internal.persona` 등)을 찍게 해 stderr 지문 검사가 거짓 실패한다.
    `PYTHONINSPECT`·`PYTHONSTARTUP`·`PYTHONWARNINGS` 등은 탐침의 동작 자체를 바꾼다.
    `PYTHONHASHSEED` 는 부모 값을 그대로 넘긴다 — 생성 결과는 해시 seed 와 무관해야 하므로
    부모가 seed 를 바꿔 가며 돌리는 검증이 자식에도 닿게 한다. 나머지(PATH·HOME·로캘 등)는 그대로다.
    """
    env = {key: value for key, value in os.environ.items() if not key.startswith("PYTHON")}
    env.update({
        "PYTHONPATH": str(REPO_ROOT),
        "PYTHONDONTWRITEBYTECODE": "1",
        "PYTHONIOENCODING": "utf-8",
    })
    if "PYTHONHASHSEED" in os.environ:
        env["PYTHONHASHSEED"] = os.environ["PYTHONHASHSEED"]
    return env


def run_probe(work: Path, preamble: str = "") -> dict[str, object]:
    """탐침을 자식 프로세스(`sys.executable`)로 돌린다. 프로젝트 코드가 이 프로세스에 적재되지 않으므로
    같은 실행의 정적 검사(`ast` 등)를 오염시킬 수 없다. `preamble` 은 자기검증이 누수를 심는 자리다."""
    # stdin 을 닫는다 — 물려받으면 대화 모드 같은 환경에서 자식이 멈출 수 있다.
    completed = subprocess.run(
        [sys.executable, "-c", f"PROBE_MARK = {_PROBE_MARK!r}\n" + preamble + _PROBE, str(work)],
        cwd=REPO_ROOT, env=probe_environment(), stdin=subprocess.DEVNULL, capture_output=True,
        text=True, encoding="utf-8", errors="replace", timeout=600,
    )
    if completed.returncode != 0:
        raise AssertionError(f"탐침 실패 (exit {completed.returncode}):\n{completed.stderr[-3000:]}")
    # 디코딩은 replace 로 해서 부모가 죽지 않게 하되, 읽지 못한 출력은 검사를 통과시키지 않는다(실패 쪽으로
    # 닫는다). UTF-16 등으로 쓴 id 는 대체 문자(U+FFFD)나 NUL 이 끼어 지문과 맞지 않기 때문이다.
    # 자식은 PYTHONIOENCODING=utf-8 이라 정상 실행에서는 둘 다 나오지 않는다.
    for stream, text in (("stdout", completed.stdout), ("stderr", completed.stderr)):
        if "\ufffd" in text or "\x00" in text:
            raise AssertionError(f"자식 {stream} 을 UTF-8 로 읽을 수 없다 — 읽지 못한 출력은 누수 검사를 통과시키지 않는다")
    lines = completed.stdout.splitlines()
    line = next(l for l in lines if l.startswith(_PROBE_MARK))
    result = json.loads(line[len(_PROBE_MARK):])
    # 보고 줄 밖의 출력(디버그 print·logging)도 검사 대상이다 — 가장 흔한 우발 누수 경로다.
    result["stdout"] = "\n".join(l for l in lines if l != line)
    result["stderr"] = completed.stderr
    return result


def probe_haystacks(work: Path, result: dict[str, object]) -> dict[str, str]:
    haystacks = output_haystacks(work / "out")
    haystacks["<공개 반환값>"] = str(result["returned"])
    for label, kind, message in result["errors"]:
        haystacks[f"<오류: {label}>"] = f"{kind}: {message}"
    haystacks["<자식 stdout>"] = str(result["stdout"])
    haystacks["<자식 stderr>"] = str(result["stderr"])
    return haystacks


def output_format_problems(root: Path) -> list[str]:
    """출력 루트의 모든 파일(최상위 포함)이 읽을 수 있는 형식인지. 지문 검사는 내용을 글자로 읽으므로,
    압축·이진 덩어리를 `.json` 이름으로 두면 그 안의 누수를 보지 못한다. 그래서 형식부터 요구한다:
    `.json` 은 UTF-8 JSON 으로 파싱돼야 하고, `.gz` 는 풀려서 UTF-8 이어야 한다."""
    problems: list[str] = []
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        name = path.relative_to(root).as_posix()
        try:
            if path.name.endswith(".json"):
                json.loads(path.read_bytes().decode("utf-8"))
            elif path.name.endswith(".gz"):
                gzip.decompress(path.read_bytes()).decode("utf-8")
            else:
                problems.append(f"{name}: 허용하지 않는 형식")
        except (ValueError, OSError, EOFError) as error:
            problems.append(f"{name}: 읽을 수 없다 ({type(error).__name__})")
    return problems


def probe_fingerprints(work: Path, result: dict[str, object]) -> Fingerprints:
    state_path = work / "hidden" / "states" / f"{result['state_id']}.json"
    return Fingerprints(json.loads(state_path.read_text(encoding="ascii")), _config_persona_ids())


class TestHiddenValuesStayHidden(unittest.TestCase):
    """실제로 세계를 돌려, 숨은 값이 공개 경계에 없음을 본다 (동적, 자식 프로세스).

    검사 대상: 출력 루트의 파일 내용(jsonl.gz 로 강제해 풀어 읽는다)과 상대 경로 이름, Sink 실행 기록,
    모든 공개 반환값의 `repr`, 대표 오류 경로의 공개 예외 메시지, 자식 프로세스의 stdout·stderr 원문.
    stdout·stderr 를 UTF-8 로 읽을 수 없으면(대체 문자·NUL) 검사하지 못하므로 실패로 본다.
    출력 루트의 파일은 최상위까지 모두 `.json`(파싱되어야 함)·`.gz`(풀려야 함)여야 한다.

    ★ 원리상 한계 — 이름 없이 숫자만 새는 경우는 잡지 못한다. Trait 값은 평범한 정수(예: 812345)라
    이벤트의 수량·시간·금액과 구분할 수 없다. 값을 지문으로 쓰면 우연 일치로 거짓 실패가 나고,
    S4 이후에는 Trait 에서 관측값을 정당하게 만들기 시작한다. 이 경로는 리뷰와 `docs/persona_spec.md`
    7절이 맡는다(후속 이슈 후보).
    """

    def test_no_hidden_value_reaches_outputs_returns_or_error_messages(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            work = Path(tmp)
            result = run_probe(work)
            fingerprints = probe_fingerprints(work, result)
            state_text = (work / "hidden" / "states" / f"{result['state_id']}.json").read_text(encoding="ascii")
            # 지문이 제대로 만들어졌는지: 숨김 영역의 상태에서는 모두 찾혀야 한다.
            self.assertTrue(fingerprints.findings({"<상태>": state_text}))
            haystacks = probe_haystacks(work, result)
            self.assertTrue(any(name.startswith("runs/") for name in haystacks), sorted(haystacks))
            self.assertTrue(any(name.startswith("events/") for name in haystacks), sorted(haystacks))
            self.assertEqual([], output_format_problems(work / "out"))
            self.assertEqual([], fingerprints.findings(haystacks))
            silent = [label for label, kind, _ in result["errors"] if kind is None]
            self.assertEqual([], silent, "오류 경로가 예외 없이 지나갔다 — 그 경로의 메시지를 검사하지 못한다")
            self.assertTrue(result["event_keys"])
            self.assertEqual([], sorted(set(result["event_keys"]) - set(result["event_fields"])))
            self.assertTrue(Path(str(result["default_hidden_root"])).is_relative_to(REPO_ROOT / "data" / "hidden"))

    def test_detector_catches_representative_leaks(self) -> None:
        state = {"customers": [
            {"persona": "vip_loyal", "hidden_traits": {"coupon_sensitivity": 812345, "marketing_fatigue": 1}},
            {"persona": "loyal", "hidden_traits": {"coupon_sensitivity": 2, "marketing_fatigue": 3}},
        ]}
        fingerprints = Fingerprints(state, {"explorer"})
        leaks = {
            "따옴표 없는 id 연결": "segment vip_loyal",
            "삽입된 id": "seg-vip_loyal-v1",
            "헤더 없는 CSV": "C00000001,loyal\n",
            "키=값": "segment=explorer",
            "hive 경로": "events/persona=loyal/part-0.jsonl.gz",
            "Trait 이름": "coupon_sensitivity is high",
            "Trait 사전 JSON": '{"coupon_sensitivity":812345,"marketing_fatigue":1}',
            "생성 라벨": "hidden_traits",
        }
        for label, text in leaks.items():
            with self.subTest(leak=label):
                self.assertTrue(fingerprints.findings({label: text}), text)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "blob.json").write_bytes(gzip.compress(b'{"x": 1}'))
            (root / "notes.txt").write_text("x", encoding="utf-8")
            (root / "ok.json").write_text("{}", encoding="utf-8")
            (root / "sub").mkdir()
            (root / "sub" / "bad.gz").write_bytes(b"not gzip")
            self.assertEqual(["blob.json", "notes.txt", "sub/bad.gz"], [p.split(":")[0] for p in output_format_problems(root)])
        clean = {"이벤트": '{"customer_id":"C00000001","page_type":"home","unit_price":4900}',
                 "다른 식별자의 일부": "vip_loyal_x · loyalty · explorers · personal"}
        self.assertEqual([], fingerprints.findings(clean))

    def test_planted_leaks_in_a_real_run_are_caught(self) -> None:
        # 실제 실행에 누수를 심어 끝에서 끝까지 잡히는지 본다: 출력 루트의 hive 식 경로,
        # 공개 반환값의 따옴표 없는 id 연결, 자식 프로세스 stderr 의 디버그 출력.
        preamble = (
            "from src.simulator import api as _api\n"
            "from src.simulator._internal import runtime as _rt\n"
            "_real_bundle, _real_advance = _api.exchange_bundle, _api.advance\n"
            "def _bundle(until):\n"
            "    c = _rt.active.world['customers'][0]\n"
            "    return {**_real_bundle(until), 'detail': 'segment ' + c['persona']}\n"
            "def _advance(days):\n"
            "    summary = _real_advance(days)\n"
            "    c = _rt.active.world['customers'][1]\n"
            "    leak = _rt.active.output_root / ('persona=' + c['persona']) / 'x.txt'\n"
            "    leak.parent.mkdir(parents=True, exist_ok=True)\n"
            "    leak.write_text('x')\n"
            "    import json as _j, sys as _s\n"
            "    print(_j.dumps(c['hidden_traits'], sort_keys=True, separators=(',', ':')), file=_s.stderr)\n"
            "    return summary\n"
            "_api.exchange_bundle, _api.advance = _bundle, _advance\n"
        )
        with tempfile.TemporaryDirectory() as tmp:
            work = Path(tmp)
            result = run_probe(work, preamble)
            findings = probe_fingerprints(work, result).findings(probe_haystacks(work, result))
            self.assertTrue(any(f.startswith("<출력 루트 경로 이름>") for f in findings), findings)
            self.assertTrue(any(f.startswith("<공개 반환값>") for f in findings), findings)
            self.assertTrue(any(f.startswith("<자식 stderr>") for f in findings), findings)

    def test_unreadable_child_output_fails_closed(self) -> None:
        # UTF-16 으로 쓴 id 는 UTF-8 로 읽으면 대체 문자·NUL 이 끼어 지문과 맞지 않는다. 그런 출력은
        # 검사 없이 통과시키지 않고 실패로 본다(BOM 있는 utf-16 · BOM 없는 utf-16-le 둘 다).
        for codec in ("utf-16", "utf-16-le"):
            preamble = (
                "import sys as _s\n"
                "from src.simulator import api as _api\n"
                "from src.simulator._internal import runtime as _rt\n"
                "_real_advance = _api.advance\n"
                "def _advance(days):\n"
                "    summary = _real_advance(days)\n"
                "    _s.stderr.flush()\n"
                f"    _s.stderr.buffer.write(_rt.active.world['customers'][0]['persona'].encode({codec!r}))\n"
                "    _s.stderr.buffer.flush()\n"
                "    return summary\n"
                "_api.advance = _advance\n"
            )
            with self.subTest(codec=codec), tempfile.TemporaryDirectory() as tmp:
                with self.assertRaisesRegex(AssertionError, "UTF-8 로 읽을 수 없다"):
                    run_probe(Path(tmp), preamble)


if __name__ == "__main__":
    unittest.main()
