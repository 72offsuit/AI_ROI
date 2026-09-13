#!/usr/bin/env python3
"""D3 신선도 검사 — 각 산출물의 source_hash 를 선언 목록으로 재계산해 대조한다.

계산법은 project-context-kr.md §12 와 같다:
  1. 경로를 저장소 루트 기준 상대경로로
  2. sorted()
  3. 각 파일에 f"{path}\n{sha256_hex}\n" 를 이어붙이고
  4. 그 바이트열의 SHA-256 앞 16자리
  5. 없는 파일은 해시 자리에 "MISSING" — 조용히 빼지 않는다

목록은 각 파일 말미의 <!-- ... source_hash inputs ... --> 주석에서 읽는다.
"""
import hashlib, pathlib, re, sys

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parents[2]                      # .agent-team/03-story-engineering/tools → 저장소 루트
DOCS = HERE.parent

# ★ 확장자 목록이 좁으면 파일이 조용히 빠진다.
#   첫 판은 "'/' 가 있는 줄"로 걸러 AGENTS.md 를 놓쳤고 12건 전부 불일치로 나왔다.
#   검사기 자신의 대상 범위가 주장보다 좁았던 사례 — readiness-report §0.39 와 같은 형태다.
PATH_LINE = re.compile(r'\s*[\w./\-]+\.(?:md|json|py|yml|yaml|mjs|ts|tsx|css|txt|toml)\s*$')


def source_hash(paths):
    buf, missing = b'', 0
    for rel in sorted(paths):
        f = ROOT / rel
        if f.exists():
            h = hashlib.sha256(f.read_bytes()).hexdigest()
        else:
            h, missing = 'MISSING', missing + 1
        buf += f"{rel}\n{h}\n".encode()
    return hashlib.sha256(buf).hexdigest()[:16], missing


def main():
    # Three outcomes, not two. A document that declares `source_hash` but ships no
    # input list makes a claim nobody can re-derive -- that is a failure, not a skip.
    # Lumping it with "no declaration at all" made this checker report the problem
    # and still exit 0 (Matthias N-12). `validate_examples.py` fails closed in the
    # analogous case; this one now matches.
    ok = bad = skipped = unverifiable = 0
    for sf in sorted(DOCS.glob('*.md')):
        text = sf.read_text(encoding='utf-8')
        declared = re.search(r'^source_hash:\s*(\w+)', text, re.M)
        block = re.search(r'<!-- ═+ source_hash inputs.*?═+\n(.*?)-->', text, re.S)
        if not declared:
            skipped += 1          # no claim made -- nothing to verify
            continue
        if not block:
            unverifiable += 1     # claim made, no inputs -- cannot be reproduced
            print(f"★검증불가 {sf.name:<41} {declared.group(1)} 선언 · 입력 목록 없음")
            continue
        paths = [l.strip() for l in block.group(1).split('\n') if PATH_LINE.fullmatch(l)]
        got, missing = source_hash(paths)
        good = got == declared.group(1)
        ok, bad = ok + good, bad + (not good)
        mark = 'OK ' if good else '★불일치'
        print(f"{mark} {sf.name:<44} {declared.group(1)} vs {got}   files={len(paths)} MISSING={missing}")
    print(f"\n일치 {ok} · 불일치 {bad} · 검증불가 {unverifiable} · 선언없음 {skipped}")
    # Self-check: every document is accounted for in exactly one bucket.
    assert ok + bad + unverifiable + skipped == len(list(DOCS.glob('*.md')))
    return 1 if (bad or unverifiable) else 0


if __name__ == '__main__':
    sys.exit(main())
