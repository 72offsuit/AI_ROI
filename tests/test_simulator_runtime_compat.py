"""#248 — 시뮬레이터가 Python 3.11 에서도 import 된다.

3.11 의 dataclass 는 해시할 수 없는 기본값을 모두 거부한다(3.10 은 list · dict · set 만, `MappingProxyType` 은 3.12 부터
해시 가능). CI 는 3.10 · 3.12 에서만 돌아 이 차이를 보지 못하므로 두 겹으로 막는다.

- 정적 검사(어느 판에서나): 시뮬레이터 dataclass 필드의 기본값에 3.11 이 거부하는 타입이 없다.
- 실제 3.11: 이 기기에 `python3.11` 이 있으면 그 인터프리터로 시뮬레이터를 import 한다. 없으면 BLOCKED 로 건너뛴다.
"""

from __future__ import annotations

import dataclasses
import importlib
import inspect
import pkgutil
import shutil
import subprocess
import unittest
from types import MappingProxyType

import src.simulator._internal as internal
from tests.test_simulator_support import REPO_ROOT

# 3.11 이 dataclass 기본값으로 거부하는 타입 중 이 저장소가 쓸 법한 것. mappingproxy 는 3.12 의 해시 가능 판정과
# 무관하게 막는다 — 3.11 에서는 해시할 수 없다.
_REJECTED_ON_311 = (list, dict, set, bytearray, MappingProxyType)


def simulator_dataclasses() -> list[type]:
    found = []
    names = ["src.simulator.api"] + [f"{internal.__name__}.{m.name}" for m in pkgutil.iter_modules(internal.__path__)]
    for name in names:
        module = importlib.import_module(name)
        for _, value in inspect.getmembers(module, inspect.isclass):
            if dataclasses.is_dataclass(value) and value.__module__ == name:
                found.append(value)
    return found


class TestDataclassDefaultsImportOn311(unittest.TestCase):
    def test_no_field_default_is_a_type_python_311_rejects(self) -> None:
        classes = simulator_dataclasses()
        self.assertTrue(any(c.__name__ == "GenerationConfig" for c in classes))
        offenders = [
            f"{cls.__module__}.{cls.__name__}.{f.name}: {type(f.default).__name__}"
            for cls in classes
            for f in dataclasses.fields(cls)
            if f.default is not dataclasses.MISSING and isinstance(f.default, _REJECTED_ON_311)
        ]
        self.assertEqual([], offenders, "default_factory 로 바꾼다 — 3.11 dataclass 가 거부한다(#248)")

    def test_the_simulator_imports_on_a_real_python_311_when_available(self) -> None:
        python311 = shutil.which("python3.11")
        if python311 is None:
            self.skipTest("BLOCKED: 이 기기에 python3.11 이 없다 — 정적 검사만 돌았다")
        completed = subprocess.run(
            [python311, "-I", "-c", "import sys; sys.path.insert(0, '.'); import src.simulator; "
             "from src.simulator._internal import genconfig; genconfig.load()"],
            cwd=REPO_ROOT, capture_output=True, text=True, timeout=120, check=False,
        )
        self.assertEqual(0, completed.returncode, completed.stderr[-2000:])
