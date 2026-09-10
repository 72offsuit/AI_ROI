"""예시 산출물을 게시 계약 스키마로 검증한다 (설계 도구 — 제품 코드가 아니다).

jsonschema 가 있어야 실행된다. 없으면 BLOCKED 로 보고하고 통과로 적지 않는다.
W5 에서는 같은 검증을 tests/test_publish_contract.py 가 수행한다
(dependency-plan.md — jsonschema 는 선택 의존성이며 없으면 skip 한다).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
SCHEMAS = HERE.parent / "schemas"
EXAMPLES = HERE.parent / "examples"

try:
    from jsonschema import Draft202012Validator
    from referencing import Registry, Resource
except ImportError:
    print("BLOCKED — jsonschema 가 설치되지 않아 검증을 실행하지 못했다.")
    print("통과로 적지 않는다.")
    raise SystemExit(2)


def build_registry() -> Registry:
    registry = Registry()
    for path in sorted(SCHEMAS.glob("*.schema.json")):
        doc = json.loads(path.read_text(encoding="utf-8"))
        resource = Resource.from_contents(doc)
        registry = registry.with_resource(uri=path.name, resource=resource)
        registry = registry.with_resource(uri=doc["$id"], resource=resource)
    return registry


def main() -> int:
    registry = build_registry()
    failures = 0
    checked = 0
    for example_dir in sorted(p for p in EXAMPLES.iterdir() if p.is_dir()):
        for path in sorted(example_dir.glob("*.json")):
            schema_path = SCHEMAS / f"{path.stem}.schema.json"
            if not schema_path.is_file():
                print(f"FAIL {path.name} — 대응 스키마가 없다: {schema_path.name}")
                failures += 1
                continue
            schema = json.loads(schema_path.read_text(encoding="utf-8"))
            validator = Draft202012Validator(schema, registry=registry)
            errors = sorted(validator.iter_errors(json.loads(path.read_text(encoding="utf-8"))),
                            key=lambda e: list(e.absolute_path))
            checked += 1
            if errors:
                failures += len(errors)
                print(f"FAIL {example_dir.name}/{path.name} — 위반 {len(errors)}건")
                for error in errors[:6]:
                    location = "/".join(str(p) for p in error.absolute_path) or "<root>"
                    print(f"     {location}: {error.message[:160]}")
            else:
                print(f"OK   {example_dir.name}/{path.name}")
    print(f"\n검증 {checked}건 · 위반 {failures}건")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
