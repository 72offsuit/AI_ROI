"""#288: 완성한 DL 산출물의 게시와 Test 접근 예약을 분리한다 (표준 라이브러리)."""
from contextlib import contextmanager
import json
import os
from pathlib import Path
import tempfile


def evaluation_claim_path(directory):
    directory = Path(directory)
    return directory.parent / f'.{directory.name}.test-claim.json'


def claim_evaluation(directory, declaration):
    """Test를 읽기 전 선택을 고정한다. 실패해도 이 예약은 지우지 않아 자동 재평가를 막는다."""
    directory = Path(directory)
    if directory.exists() or directory.is_symlink():
        raise FileExistsError(directory)
    directory.parent.mkdir(parents=True, exist_ok=True)
    path = evaluation_claim_path(directory)
    with path.open('x', encoding='utf-8') as stream:
        json.dump(declaration, stream, ensure_ascii=False, allow_nan=False, indent=2)
        stream.flush()
        os.fsync(stream.fileno())
    return path


@contextmanager
def atomic_artifact_directory(directory):
    """동일 부모의 staging을 완성 후 rename한다. 기존 목적지·협력 작성자의 예약은 거부한다.

    로컬 신뢰 파일시스템의 협력 작성자 간 게시 규약이다. 악의적 비협력 프로세스나
    전원 장애의 내구성까지 보증하지 않는다. Test 예약은 별도이며 여기서 정리하지 않는다.
    """
    directory = Path(directory)
    if directory.exists() or directory.is_symlink():
        raise FileExistsError(directory)
    directory.parent.mkdir(parents=True, exist_ok=True)
    lock = directory.parent / f'.{directory.name}.publish.lock'
    reservation = lock.open('x', encoding='utf-8')
    try:
        with reservation as stream:
            stream.write('local artifact publication reservation\n')
        if directory.exists() or directory.is_symlink():
            raise FileExistsError(directory)
        with tempfile.TemporaryDirectory(prefix=f'.{directory.name}.staging-', dir=directory.parent) as name:
            staging = Path(name)
            yield staging
            if directory.exists() or directory.is_symlink():
                raise FileExistsError(directory)
            os.rename(staging, directory)
    finally:
        lock.unlink()
