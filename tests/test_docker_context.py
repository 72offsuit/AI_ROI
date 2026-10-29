"""Docker 빌드 컨텍스트에서 비밀값이 빠지는가 (#207 · PR #240 리뷰 R1).

`docker build .` 는 로컬 작업 폴더를 컨텍스트로 쓴다. `.gitignore` 는 커밋만 막으므로, 커밋하지
않는 비밀값(감사 로그 서명 키)은 `.dockerignore` 에도 같은 줄이 있어야 이미지에서 빠진다.

  checked   .gitignore 의 `.agent-team/_state/` 줄(키 · 락)이 .dockerignore 에 그대로 있다
  checked   .dockerignore 가 그 줄을 `!` 로 다시 넣지 않는다
  NOT       Docker 의 실제 매칭. 표준 라이브러리로는 Docker 패턴 규칙을 재현하지 않는다 —
            합성 컨텍스트 빌드로 1회 확인한 기록이 DR-207-python-runtime 의 조사한 것에 있다
"""

from __future__ import annotations

import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
STATE_PREFIX = ".agent-team/_state/"


def _patterns(path: Path) -> list[str]:
    lines = (line.strip() for line in path.read_text(encoding="utf-8").splitlines())
    return [line for line in lines if line and not line.startswith("#")]


class TestStateSecretsLeaveTheImage(unittest.TestCase):
    def test_gitignored_state_files_are_dockerignored(self) -> None:
        secrets = [p for p in _patterns(REPO_ROOT / ".gitignore") if p.startswith(STATE_PREFIX)]
        # 빈 목록이면 아래 대조가 공허하게 통과한다 — 키 줄이 .gitignore 에서 사라진 것도 결함이다.
        self.assertIn(f"{STATE_PREFIX}*.audit-key", secrets)
        docker = _patterns(REPO_ROOT / ".dockerignore")
        missing = [p for p in secrets if p not in docker]
        self.assertEqual([], missing, ".gitignore 가 커밋에서 빼는 _state 파일이 이미지에는 들어간다")
        reincluded = [p for p in docker if p.startswith(f"!{STATE_PREFIX}") or p == "!.agent-team"]
        self.assertEqual([], reincluded)


if __name__ == "__main__":
    unittest.main()
