"""창구 중립성과 의존성 봉쇄를 **소스 검사로** 고정한다 (이슈 #47 AC-3 · 가정 A7-6).

## 왜 값 검사가 아니라 소스 검사인가

값 검사는 *"오늘 우연히 맞다"* 만 보여준다. `contribution_profit(commerce_events)` 가
오늘 `unavailable` 을 돌려주는 것은 오늘 커머스에 원가가 없기 때문이고, 출처로
분기하는 코드를 넣어도 **같은 값이 나온다.**

소스 검사는 다음 사람이 분기를 넣는 순간 실패한다. `tests/test_isolation.py` 가
import 를 AST 로 검사하는 것과 같은 방식이고 같은 이유다.

## ★ 이 파일의 검사는 **짝으로** 동작한다 — 하나만 있으면 구멍이 남는다

`test_economics_has_no_source_literal` 은 **문자열 상수만** 본다. 그래서 이 우회를
못 잡는다:

    if record.get("simulator_version") is not None:   # 출처 이름이 안 나온다
        return unavailable(...)                        # 그런데 출처로 분기하고 있다

그것을 잡는 것이 `test_source_classification_is_single_sourced` 다 — 출처 판별에
쓰이는 두 메타 필드를 **함께** 참조하는 파일을 `schema.py`·`sink.py` 로 제한한다.
**두 검사는 짝이다.** 하나를 지우면 다른 하나가 막던 것도 함께 열린다.

## 이 검사의 한계 — 적어 두지 않으면 통과가 보증으로 오해된다

AST 정적 검사이므로 아래를 **잡지 못한다**:

  - 동적 import (`importlib.import_module("yaml")`)
  - `getattr(config, "cost" + "_rate")` 같은 문자열 조립 접근
  - f-string 으로 만든 경로·식별자
  - 별칭을 통한 재수출 (`from x import y as z` 뒤의 `z` 사용)

즉 **우회하려는 사람을 막지 못한다. 실수로 넣는 사람을 막는다.** 그것이 이 검사의
목적이고, 우회는 코드 리뷰가 잡는다.

실행:
    python3 -m unittest tests.test_neutrality -v
"""

from __future__ import annotations

import ast
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
MEASUREMENT = REPO_ROOT / "src" / "measurement"

#: ★ I/O 를 하지 않는 순수 계산 모듈. `#47` AC-3 이 지목한 집합이다.
#:
#: 아직 만들어지지 않은 파일도 적어 둔다. 존재하는 것만 검사하되, 만들어지는 순간
#: 자동으로 검사 대상이 된다 — 새 파일이 조용히 예외가 되지 않게 한다.
#:
#: **`contracts.py`·`publish.py`·`freeze.py`·`validate.py` 는 여기 없다.** 1차
#: 구현에서 넣었다가 `contracts.py` 가 걸렸는데, 그것은 검사가 맞고 코드가 틀린
#: 경우가 아니었다 — `provenance` 수집(`git rev-parse` · config SHA-256)이 그
#: 모듈의 본업이고 AC-3 이 지목한 것은 `economics.py` 였다. **"표준 라이브러리만
#: 쓴다"와 "I/O 를 하지 않는다"는 다른 명제이고, 섞어 두면 둘 다 헐거워진다.**
#: 두 명제를 각각 다른 테스트가 본다.
NO_IO_MODULES = (
    "schema.py",
    "kpi.py",
    "economics.py",
    "errors.py",
)

#: 출처 이름. 계산층이 이 문자열을 담으면 창구가 한쪽 편을 드는 것이다.
SOURCE_LITERALS = ("commerce", "simulator")

#: ★ 출처를 알아서는 안 되는 계산층. `#47` AC-3 은 `economics.py` 를, `#46` AC-5 는
#: `kpi.py` 를 지목한다 — **둘 다 검사한다.**
SOURCE_BLIND_MODULES = ("economics.py", "kpi.py")

#: 원가율 계열. `economics.py` 가 이것을 읽으면 EC-1(추정 COGS) 로 가는 문이 열린다.
COST_RATE_TOKENS = ("cost_rate", "margin_rate", "product_margin")

#: 출처 판별에 쓰이는 메타 필드. 둘을 **함께** 보는 파일이 출처를 아는 파일이다.
SOURCE_DISCRIMINATOR_FIELDS = ("simulator_version", "random_seed")

#: 출처를 알아도 되는 파일. `schema.py` 는 필드를 선언하고 `sink.py` 는 MEA-002 가
#: 요구하는 출처 구분을 구현한다. 그 둘이 유일한 자리다.
SOURCE_AWARE_MODULES = frozenset({"schema.py", "sink.py"})

#: 순수 계산 모듈이 import 하면 안 되는 것 — I/O 경로.
FORBIDDEN_IO_IMPORTS = frozenset(
    {"json", "csv", "gzip", "pathlib", "os", "shutil", "sqlite3", "subprocess",
     "socket", "urllib", "tempfile"}
)

#: 표준 라이브러리 화이트리스트. **최상위 import** 에만 적용한다 — 선택 의존성은
#: 함수 안 지연 import 여야 하고, 그것은 `test_pyarrow_import_is_lazy` 와
#: `test_yaml_import_is_contained` 가 따로 본다.
STDLIB_ALLOWED = frozenset({
    "__future__", "abc", "ast", "collections", "contextlib", "csv", "dataclasses",
    "datetime", "decimal", "enum", "functools", "gzip", "hashlib", "itertools",
    "json", "math", "os", "pathlib", "re", "secrets", "shutil", "statistics",
    "subprocess", "tempfile", "textwrap", "typing", "unicodedata", "uuid", "src",
    # CLI 용. publish.py 가 `python3 -m src.measurement.publish` 로 실행된다.
    "argparse", "sys",
})


def _parse(path: Path) -> ast.AST:
    return ast.parse(path.read_text(encoding="utf-8"), filename=str(path))


def _string_constants(tree: ast.AST) -> list[tuple[str, int]]:
    """모든 문자열 상수와 줄 번호. 독트링도 포함된다 — 의도한 것이다."""
    return [
        (node.value, node.lineno)
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant) and isinstance(node.value, str)
    ]


def _identifiers(tree: ast.AST) -> list[tuple[str, int]]:
    """이름·속성 접근·키워드 인자.

    속성 접근을 함께 보는 이유는 `config.cost_rate` 가 `ast.Name` 이 아니라
    `ast.Attribute` 로 오기 때문이다. 이름만 보면 그 형태를 놓친다.
    """
    found: list[tuple[str, int]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Name):
            found.append((node.id, node.lineno))
        elif isinstance(node, ast.Attribute):
            found.append((node.attr, node.lineno))
        elif isinstance(node, ast.keyword) and node.arg:
            found.append((node.arg, node.lineno))
    return found


def _imported_roots(tree: ast.AST) -> list[tuple[str, int]]:
    """import 된 최상위 모듈 이름. `import a.b` 와 `from a.b import c` 모두 `a`."""
    roots: list[tuple[str, int]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            roots.extend((alias.name.split(".")[0], node.lineno) for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            roots.append((node.module.split(".")[0], node.lineno))
    return roots


def _existing(names: tuple[str, ...]) -> list[Path]:
    return [MEASUREMENT / name for name in names if (MEASUREMENT / name).exists()]


def _toplevel_imported_roots(tree: ast.AST) -> list[tuple[str, int]]:
    """**모듈 최상위** import 만. 함수 안 지연 import 는 제외한다.

    "의존성 설치 없이 import 되는가"가 판정 대상이므로 최상위만 본다. 함수 안
    import 는 그 함수를 부를 때만 필요하고, 그것이 guarded 패턴의 핵심이다.
    """
    roots: list[tuple[str, int]] = []
    for node in ast.iter_child_nodes(tree):
        if isinstance(node, ast.Import):
            roots.extend((a.name.split(".")[0], node.lineno) for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            roots.append((node.module.split(".")[0], node.lineno))
    return roots


class TestWindowNeutrality(unittest.TestCase):
    """N-1 · N-2 — 계산층이 출처와 원가율을 알 수 없게 한다."""

    def test_calculation_layer_has_no_source_literal(self) -> None:
        """N-1 (EC-2 · #46 AC-5) — **계산층 전체**에 출처 이름이 문자열로도 없다.

        ★ 1차 구현은 `economics.py` 만 검사했다. `#46` AC-5 가 `kpi.py` 에도 같은
        규칙을 요구하고, 실제로 `kpi.py` 가 `"Ecommerce_Service #29"`(부분문자열
        `commerce`)를 담고 있었다 — **검사 대상이 주장보다 좁았던 자리다.**

        짝: `test_source_classification_is_single_sourced`.
        """
        hits: list[str] = []
        for path in _existing(SOURCE_BLIND_MODULES):
            hits.extend(
                f"{path.name}:{line} — {literal!r}"
                for literal, line in _string_constants(_parse(path))
                for banned in SOURCE_LITERALS
                if banned in literal.lower()
            )
        self.assertEqual(
            [], hits,
            "계산층이 출처 이름을 담고 있다. 출처별 결과는 분기가 아니라 입력 "
            "분할로 얻는다 (N-3) — publish.py 가 쪼개 호출한다. 부분문자열도 "
            "걸린다(Ecommerce ⊃ commerce): 오탐은 안전한 방향의 실패이므로 "
            "검사를 느슨하게 하지 않고 문구를 바꾼다:\n" + "\n".join(hits),
        )

    def test_economics_does_not_read_cost_rate(self) -> None:
        """N-2 (EC-9) — 원가율을 식별자로도 문자열로도 참조하지 않는다.

        원가율에 닿을 수 있으면 `order_amount × cost_rate` 가 COGS 로 들어가고,
        그러면 기여이익이 매출의 상수배가 되어 `revenue_up_profit_down`
        가드레일이 원리적으로 발동할 수 없다.
        """
        hits: list[str] = []
        for path in _existing(SOURCE_BLIND_MODULES):
            tree = _parse(path)
            hits.extend(
                f"{path.name}:{line} — {name}"
                for name, line in _identifiers(tree)
                if name in COST_RATE_TOKENS
            )
            hits.extend(
                f"{path.name}:{line} — {literal!r}"
                for literal, line in _string_constants(tree)
                for banned in COST_RATE_TOKENS
                if banned in literal
            )
        self.assertEqual(
            [], hits,
            "계산층이 원가율을 참조한다. COGS 는 저장된 unit_cost 로만 "
            "계산한다 (EC-1):\n" + "\n".join(hits),
        )

    def test_source_classification_is_single_sourced(self) -> None:
        """N-4 — 출처 판별 필드를 **함께** 보는 파일이 schema.py · sink.py 뿐이다.

        ★ `test_economics_has_no_source_literal` 의 짝이다. 저쪽이 출처 이름을
        막고 이쪽이 이름 없이 출처를 판별하는 우회를 막는다.
        """
        offenders: list[str] = []
        for path in sorted(MEASUREMENT.glob("*.py")):
            if path.name in SOURCE_AWARE_MODULES or path.name == "__init__.py":
                continue
            seen = {
                literal
                for literal, _ in _string_constants(_parse(path))
                for field in SOURCE_DISCRIMINATOR_FIELDS
                if field == literal
            } | {
                name
                for name, _ in _identifiers(_parse(path))
                if name in SOURCE_DISCRIMINATOR_FIELDS
            }
            if len(seen) == len(SOURCE_DISCRIMINATOR_FIELDS):
                offenders.append(f"{path.name} — {sorted(seen)}")
        self.assertEqual(
            [], offenders,
            "출처 판별이 두 곳 이상에 있다. event_source() 하나만 쓴다 "
            "(같은 규칙이 갈라지면 어느 쪽이 정본인지 알 수 없다):\n"
            + "\n".join(offenders),
        )


class TestPureLayer(unittest.TestCase):
    """L-2 — 두 명제를 **따로** 검사한다.

      ① 순수 계산 모듈은 I/O 를 하지 않는다        (대상: NO_IO_MODULES)
      ② 측정 계층 전체가 최상위에서 서드파티를 쓰지 않는다  (대상: *.py 전부)

    ②가 ①보다 대상이 넓다. ISO-005("표준 라이브러리만으로 전 테스트가 돈다")를
    지키는 것은 ②이고, ①은 `economics.py` 를 순수 함수로 묶어 PyYAML 사슬을 끊는
    것(A7)이다. 목적이 다르므로 대상도 다르다.
    """

    def test_pure_layer_has_no_io(self) -> None:
        """① `#47` AC-3 — 순수 계산 모듈이 I/O 를 import 하지 않는다."""
        offenders: list[str] = []
        for path in _existing(NO_IO_MODULES):
            offenders.extend(
                f"{path.name}:{line} — import {root}"
                for root, line in _imported_roots(_parse(path))
                if root in FORBIDDEN_IO_IMPORTS
            )
        self.assertEqual(
            [], offenders,
            "순수 계산 모듈이 I/O 를 import 한다. config·파일을 읽으면 테스트가 "
            "픽스처 파일을 필요로 하고, economics.py 의 경우 PyYAML 사슬이 다시 "
            "이어져 의존성 미설치 CI 가 깨진다:\n" + "\n".join(offenders),
        )

    def test_measurement_layer_has_no_toplevel_third_party(self) -> None:
        """② ISO-005 — 측정 계층 **전체**가 최상위에서 서드파티를 쓰지 않는다.

        화이트리스트 방식이다. 금지 목록은 아는 것만 막지만 화이트리스트는
        **모르는 것도** 막는다 — 다음 사람이 새 패키지를 넣으면 걸린다.
        """
        offenders: list[str] = []
        for path in sorted(MEASUREMENT.glob("*.py")):
            offenders.extend(
                f"{path.name}:{line} — {root}"
                for root, line in _toplevel_imported_roots(_parse(path))
                if root not in STDLIB_ALLOWED
            )
        self.assertEqual(
            [], offenders,
            "측정 계층이 최상위에서 허용 목록 밖의 모듈을 import 한다. 표준 "
            "라이브러리면 STDLIB_ALLOWED 에 추가하고, 서드파티면 함수 안 지연 "
            "import + guarded 패턴을 쓴다 (sink.parquet_available 참조):\n"
            + "\n".join(offenders),
        )


class TestDependencyContainment(unittest.TestCase):
    """A7-6 — 새 의존성이 격리 CI 를 깨지 않게 모듈 경계에 가둔다."""

    def test_yaml_import_is_contained(self) -> None:
        """`import yaml` 이 `config_loader.py` 한 파일에만 있다."""
        offenders = [
            f"{path.name}:{line}"
            for path in sorted(MEASUREMENT.glob("*.py"))
            if path.name != "config_loader.py"
            for root, line in _imported_roots(_parse(path))
            if root == "yaml"
        ]
        self.assertEqual(
            [], offenders,
            "config_loader.py 밖에서 yaml 을 import 한다. PyYAML 접점이 번지면 "
            "의존성 미설치 CI 가 ImportError 로 깨진다:\n" + "\n".join(offenders),
        )

    def test_no_unsafe_yaml_loader(self) -> None:
        """`FullLoader` · `unsafe_load` · `yaml.load` 가 0 건이다.

        CVE-2020-14343 (PyYAML < 5.4) 는 `FullLoader` 를 통해 임의 객체를 생성할
        수 있다. 우리가 고정한 6.0.3 은 그 범위 밖이지만, **로더 선택은 파일
        출처와 무관한 습관의 문제**이므로 안전한 쪽을 고정한다.
        """
        banned = ("FullLoader", "UnsafeLoader", "unsafe_load", "full_load")
        offenders: list[str] = []
        for path in sorted(MEASUREMENT.glob("*.py")):
            tree = _parse(path)
            # ★ 식별자만 본다 — 문자열 상수는 보지 않는다.
            #
            # 이 검사는 위 두 검사와 범위가 다르고, 그 차이가 의도적이다.
            # `test_economics_has_no_source_literal` 은 문자열까지 보지만(출처
            # 이름이 문자열로 들어오는 것 자체가 위반이다), 이쪽은 **사용**을 본다.
            # `config_loader.py` 의 독트링이 "FullLoader 를 쓰지 않는다"고 적는 것은
            # FullLoader 의 사용이 아니라 금지의 문서화다 — 1차 구현에서 그 독트링이
            # 자기 검사에 걸렸고, 그때 막아야 할 것은 문서가 아니라 호출이었다.
            #
            # `yaml.FullLoader` · `yaml.unsafe_load(...)` 는 전부 속성 접근이므로
            # _identifiers() 가 잡는다. `getattr(yaml, "Full" + "Loader")` 는 못
            # 잡지만, 그것은 모듈 독트링의 "한계" 절이 이미 밝힌 범위다.
            offenders.extend(
                f"{path.name}:{line} — {name}"
                for name, line in _identifiers(tree)
                if name in banned
            )
            # `yaml.load(...)` 는 이름이 `load` 뿐이라 위에서 걸러지지 않는다
            # (`json.load` 등 정당한 load 가 많다). 수신자가 yaml 인 호출만 본다.
            for node in ast.walk(tree):
                if (
                    isinstance(node, ast.Call)
                    and isinstance(node.func, ast.Attribute)
                    and node.func.attr == "load"
                    and isinstance(node.func.value, ast.Name)
                    and node.func.value.id == "yaml"
                ):
                    offenders.append(f"{path.name}:{node.lineno} — yaml.load()")
        self.assertEqual(
            [], offenders,
            "안전하지 않은 YAML 로더를 쓴다. yaml.safe_load() 만 쓴다:\n"
            + "\n".join(offenders),
        )

    def test_pyarrow_import_is_lazy(self) -> None:
        """`pyarrow` 를 모듈 최상위에서 import 하지 않는다.

        최상위 import 는 `import src.measurement.sink` 만으로 pyarrow 를 요구하고,
        그러면 의존성 없는 CI 에서 `sink` 를 쓰는 전 테스트가 죽는다.
        """
        offenders: list[str] = []
        for path in sorted(MEASUREMENT.glob("*.py")):
            tree = _parse(path)
            for node in ast.iter_child_nodes(tree):  # 최상위만 본다
                if isinstance(node, (ast.Import, ast.ImportFrom)):
                    names = (
                        [a.name for a in node.names]
                        if isinstance(node, ast.Import)
                        else [node.module or ""]
                    )
                    offenders.extend(
                        f"{path.name}:{node.lineno} — {name}"
                        for name in names
                        if name.split(".")[0] == "pyarrow"
                    )
        self.assertEqual(
            [], offenders,
            "pyarrow 를 모듈 최상위에서 import 한다. 함수 안 지연 import + "
            "parquet_available() 가드를 쓴다:\n" + "\n".join(offenders),
        )


class TestNoHardcodedAmounts(unittest.TestCase):
    """AC-8 (#47 완료 조건) — `economics.py` 에 하드코딩된 금액이 0 건이다."""

    #: 구조적 상수만 허용한다. 0·1 은 경계 비교, 2 는 "두 전략", 30 은 월 환산
    #: 일수다. 금액으로 쓰일 수 있는 값(1000 이상)은 전부 config 에서 온다.
    ALLOWED_NUMBERS = frozenset({0, 1, 2, 30, 100})

    def test_no_hardcoded_krw_in_economics(self) -> None:
        path = MEASUREMENT / "economics.py"
        offenders = [
            f"{path.name}:{node.lineno} — {node.value}"
            for node in ast.walk(_parse(path))
            if isinstance(node, ast.Constant)
            and isinstance(node.value, (int, float))
            and not isinstance(node.value, bool)
            and node.value not in self.ALLOWED_NUMBERS
        ]
        self.assertEqual(
            [], offenders,
            "economics.py 에 숫자 리터럴이 있다. 금액은 전부 "
            "config/economic_config.yaml 에서 온다 — 코드에 있으면 무엇이 가정이고 "
            "무엇이 실측인지 구분이 사라진다:\n" + "\n".join(offenders),
        )


if __name__ == "__main__":
    unittest.main()
