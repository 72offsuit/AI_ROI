"""W5 파일 소유 경계의 겹침 0 을 실행으로 증명한다 (설계 도구 — 제품 코드가 아니다).

세 가지를 확인한다.
  ① 겹침 0    — 어떤 파일도 두 소유자의 규칙에 동시에 매칭되지 않는다
  ② 빠짐 0    — 저장소의 모든 추적 파일과 계획된 모든 파일이 소유자를 갖는다
  ③ 봉인 격리 — 봉인 파일이 W5 소유자(phillip · andrew)에게 매칭되지 않는다

실행:
    python3 .agent-team/04-architecture/tools/check_ownership.py
"""

from __future__ import annotations

import fnmatch
import json
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
MAP = json.loads((HERE / "ownership.json").read_text(encoding="utf-8"))
RULES = MAP["rules"]
W5_OWNERS = {"phillip", "andrew"}


def matches(pattern: str, path: str) -> bool:
    """glob 매칭. '**' 는 경로 구분자를 넘어 매칭한다."""
    if pattern.endswith("/**"):
        prefix = pattern[:-3]
        return path == prefix or path.startswith(prefix + "/")
    if "**" in pattern:
        return fnmatch.fnmatch(path, pattern.replace("**", "*"))
    # fnmatch 의 '*' 는 '/' 도 먹으므로 세그먼트 수를 함께 본다.
    if fnmatch.fnmatch(path, pattern):
        return path.count("/") == pattern.count("/")
    return False


def owners_of(path: str) -> list[tuple[str, str]]:
    return [(r["owner"], r["pattern"]) for r in RULES if matches(r["pattern"], path)]


def tracked_files() -> list[str]:
    out = subprocess.run(
        ["git", "-C", str(REPO), "ls-files"],
        capture_output=True, text=True, check=True).stdout
    # Plan 은 서브모듈이라 한 줄로 나온다. 규칙이 Plan/** 이므로 정규화한다.
    return [line for line in out.splitlines() if line and line != "Plan"] + ["Plan/AGENTS.md"]


def untracked_files() -> list[str]:
    out = subprocess.run(
        ["git", "-C", str(REPO), "ls-files", "--others", "--exclude-standard"],
        capture_output=True, text=True, check=True).stdout
    return [line for line in out.splitlines() if line]


def main() -> int:
    corpus: dict[str, str] = {}
    for path in tracked_files():
        corpus[path] = "추적됨"
    for path in untracked_files():
        corpus.setdefault(path, "미추적")
    for path in MAP["planned"]:
        corpus.setdefault(path, "계획")
    for path in MAP["adversarial"]:
        corpus.setdefault(path, "대조")

    overlaps: list[str] = []
    unowned: list[str] = []
    sealed_leaks: list[str] = []
    by_owner: dict[str, int] = {}

    for path in sorted(corpus):
        hits = owners_of(path)
        distinct = sorted({owner for owner, _ in hits})
        if not hits:
            unowned.append(f"{path}  ({corpus[path]})")
            continue
        if len(distinct) > 1:
            detail = " · ".join(f"{o} ← {p}" for o, p in hits)
            overlaps.append(f"{path}\n     {detail}")
            continue
        owner = distinct[0]
        by_owner[owner] = by_owner.get(owner, 0) + 1
        if owner in W5_OWNERS:
            for rule in RULES:
                if rule["owner"] == "sealed" and matches(rule["pattern"], path):
                    sealed_leaks.append(f"{path} — 봉인 규칙 {rule['pattern']} 과 겹친다")

    print("=" * 66)
    print("W5 파일 소유 경계 — 겹침 0 검사")
    print("=" * 66)
    print(f"검사 대상 {len(corpus)}개 경로 "
          f"(추적 {sum(1 for v in corpus.values() if v == '추적됨')} · "
          f"미추적 {sum(1 for v in corpus.values() if v == '미추적')} · "
          f"계획 {sum(1 for v in corpus.values() if v == '계획')} · "
          f"대조 {sum(1 for v in corpus.values() if v == '대조')})")
    print()
    for owner, count in sorted(by_owner.items()):
        print(f"  {owner:10s} {count:4d}개")
    print()

    ok = True
    if overlaps:
        ok = False
        print(f"❌ 겹침 {len(overlaps)}건")
        for line in overlaps:
            print(f"   - {line}")
    else:
        print("✅ ① 겹침 0 — 두 소유자의 규칙에 동시에 매칭되는 경로가 없다")

    if unowned:
        ok = False
        print(f"❌ 소유자 없음 {len(unowned)}건")
        for line in unowned:
            print(f"   - {line}")
    else:
        print("✅ ② 빠짐 0 — 모든 경로가 소유자를 갖는다")

    if sealed_leaks:
        ok = False
        print(f"❌ 봉인 누수 {len(sealed_leaks)}건")
        for line in sealed_leaks:
            print(f"   - {line}")
    else:
        print("✅ ③ 봉인 격리 — 봉인 파일이 W5 소유자에게 매칭되지 않는다")

    print()
    print("W5 소유자 간 교집합:")
    phillip = {p for p in corpus if owners_of(p) and owners_of(p)[0][0] == "phillip"}
    andrew = {p for p in corpus if owners_of(p) and owners_of(p)[0][0] == "andrew"}
    print(f"  Phillip {len(phillip)}개 ∩ Andrew {len(andrew)}개 = {len(phillip & andrew)}개")
    if phillip & andrew:
        ok = False
        for path in sorted(phillip & andrew):
            print(f"   ❌ {path}")

    print()
    print("대조 경로 — 경계에서 헷갈리기 쉬운 것들의 판정:")
    for path in MAP["adversarial"]:
        hits = owners_of(path)
        distinct = sorted({owner for owner, _ in hits})
        mark = "✅" if len(distinct) == 1 else "❌"
        if len(distinct) != 1:
            ok = False
        print(f"  {mark} {path:58s} → {', '.join(distinct) or '(없음)'}")

    print()
    print("판정:", "PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
