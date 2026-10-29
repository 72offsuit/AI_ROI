"""시스템 관측 계약 클라이언트 — 선택적 로더·모델과 독립 (#179).

공개 파티션 파서·파일 검증·관측 판정의 단일 구현이다. 모듈 import는 ML 패키지나
모델 모듈을 적재하지 않는다. pandas는 기존 파싱·시각 판정 함수에서만 지연 import한다.
시뮬레이터 구현을 참조하지 않으며 N2의 부모 연결 조건을 완화하지 않는다.
"""
from __future__ import annotations

import gzip
import hashlib
import json
import re
from collections.abc import Mapping
from pathlib import Path

from src.measurement.schema import TIMEZONE


def read_event_part(path: Path):
    """공개 파티션 파서. 기존 로더와 검증기가 같은 행 해석을 사용한다."""
    import pandas as pd

    if path.suffix == ".parquet":
        return pd.read_parquet(path)
    if path.suffix == ".csv":
        return pd.read_csv(path, dtype=str, keep_default_na=False, na_values=[""])
    opener = gzip.open if path.suffix == ".gz" else open
    with opener(path, "rt", encoding="utf-8") as handle:  # type: ignore[operator]
        rows = [json.loads(line) for line in handle if line.strip()]
    return pd.DataFrame.from_records(rows)


def normalize_index_time(index_time):
    """T0. tz 가 없으면 스키마 단일 타임존(KST)으로 해석한다 — 이벤트가 아니라 설정값이다."""
    import pandas as pd

    stamp = pd.Timestamp(index_time)
    if stamp.tzinfo is None:
        stamp = stamp.tz_localize(TIMEZONE)
    return stamp.tz_convert(TIMEZONE)


def verify_event_run(raw_root, run_id, known_parent_runs=(), *, history_evidence=None) -> dict:
    """실험용 simulator 단일 출처 실행의 파일·바이트·중복 제거 전 행 수를 대조한다 (#179).

    외부 부모는 검증된 history의 머리와 정확히 같아야 한다. ID 목록만으로는 승인하지 않는다.
    조상 실행의 거부 수는 감사에 보존하되 새 Feature/S1 차단 정책을 정하지 않는다.
    분기 루트 단독의 계보 결손을
    무시하지도, 부모가 다른 루트에 있다는 이유만으로 정상 분기를 거부하지도 않는다.
    """
    from src.measurement import sink

    root = Path(raw_root).resolve()
    audit = {"status": "not_run", "run_id": run_id, "root": str(root),
             "method": "file-digest-pre-dedup-rows-v1", "reason": None,
             "chain_rejected_total": None, "ancestor_rejected_total": None,
             "ancestor_rejection_policy": "audit_only_no_new_feature_or_s1_gate"}
    try:
        if not isinstance(run_id, str) or not run_id.strip():
            raise ValueError("검증할 실행 ID가 없다")
        known, inherited, history_head = set(known_parent_runs), {}, None
        if history_evidence is not None:
            audit["history_link_status"] = "not_run"
            if not isinstance(history_evidence, Mapping) or history_evidence.get("status") != "ok":
                raise ValueError("검증된 history 읽기 근거가 없다")
            ids = history_evidence.get("verified_run_ids")
            history_head = history_evidence.get("run_id")
            inherited = history_evidence.get("run_rejections")
            if (not isinstance(ids, list) or any(not isinstance(i, str) or not i for i in ids)
                    or len(ids) != len(set(ids)) or not isinstance(history_head, str) or history_head not in ids
                    or not isinstance(inherited, Mapping) or set(inherited) != set(ids)
                    or any(type(v) is not int or v < 0 for v in inherited.values())):
                raise ValueError("history 머리·실행별 거부 수 근거가 없거나 잘못됐다")
            if known and known != set(ids):
                raise ValueError("history 실행 목록과 별도 부모 목록이 다르다")
            known = set(ids)
            audit["history_head_run_id"] = history_head
        elif known:
            raise ValueError("실행 ID 목록만으로 history 머리·거부 수를 검증할 수 없다")
        else:
            audit["history_link_status"] = "not_applicable"
        records = sink.run_records(root)
        by_id = {}
        for record in records:
            if not isinstance(record, Mapping) or "unreadable" in record:
                raise ValueError("실행 기록이 dict가 아니거나 읽을 수 없다")
            if not {"run_id", "parent_run_id", "rows", "rejected", "files", "sha256", "sources"} <= record.keys():
                raise ValueError("실행 기록의 필수 필드가 빠졌다")
            rid = record.get("run_id")
            if not isinstance(rid, str) or rid in by_id:
                raise ValueError("실행 ID가 없거나 중복이다")
            by_id[rid] = record
        if run_id not in by_id:
            raise ValueError("해당 실행 기록이 없다")
        chain, cursor, external = [], run_id, None
        while cursor is not None:
            if cursor in chain:
                raise ValueError("실행 부모 사슬이 순환한다")
            if cursor not in by_id:
                if cursor not in known:
                    raise ValueError("외부 부모의 검증된 history가 없다")
                external = cursor
                break
            chain.append(cursor)
            parent = by_id[cursor].get("parent_run_id")
            if parent is not None and (not isinstance(parent, str) or not parent):
                raise ValueError("부모 실행 ID 형식이 잘못됐다")
            cursor = parent
        if set(chain) != set(by_id):
            raise ValueError("루트에 현재 세계 사슬 밖 실행이 섞였다")
        if history_evidence is not None and external != history_head:
            raise ValueError("HISTORY_PARENT_UNRESOLVED: 분기 외부 부모가 history 머리와 일치하지 않는다")
        if set(chain) & set(inherited):
            raise ValueError("분기와 history가 같은 실행 ID를 중복 주장한다")
        claimed, fingerprints = set(), {}
        run_rejections = dict(inherited)
        for rid in chain:
            record = by_id[rid]
            rows, rejected, files, expected = (record.get(k) for k in ("rows", "rejected", "files", "sha256"))
            if type(rows) is not int or rows < 0 or type(rejected) is not int or rejected < 0:
                raise ValueError("원시 행 수·거부 수는 0 이상의 정수여야 한다")
            run_rejections[rid] = rejected
            sources = record["sources"]
            if (not isinstance(sources, Mapping) or any(type(v) is not int or v < 0 for v in sources.values())
                    or sum(sources.values()) != rows or any(k != "simulator" and v for k, v in sources.items())):
                raise ValueError("실험 입력의 출처 근거가 simulator 단일 출처가 아니다")
            if (not isinstance(files, list) or any(not isinstance(x, str) for x in files)
                    or len(files) != len(set(files)) or not isinstance(expected, str)
                    or not re.fullmatch(r"[0-9a-fA-F]{64}", expected)):
                raise ValueError("필수 파일 목록·다이제스트가 없거나 잘못됐다")
            paths = []
            for name in files:
                if not re.fullmatch(r"events/date=\d{4}-\d{2}-\d{2}/part-\d+\.(?:parquet|jsonl\.gz|jsonl|csv)", name):
                    raise ValueError("공개 이벤트 파티션 밖 파일 주장")
                path = root / name
                if not path.resolve().is_relative_to(root / "events") or not path.is_file() or name in claimed:
                    raise ValueError("파일 부재·루트 이탈·중복 소유 주장")
                claimed.add(name)
                paths.append(path)
            digest, raw_rows = hashlib.sha256(), 0
            for path in sorted(paths):
                before = path.stat()
                digest.update(path.name.encode())  # EventSink 실행 다이제스트 계약과 같은 순서
                with path.open("rb") as stream:
                    for block in iter(lambda: stream.read(1024 * 1024), b""):
                        digest.update(block)
                raw_rows += len(read_event_part(path))  # 아직 필터링·event_id 중복 제거하지 않는다
                after = path.stat()
                if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
                    raise ValueError("검증 도중 파일이 바뀌었다")
                fingerprints[path.relative_to(root).as_posix()] = [after.st_size, after.st_mtime_ns]
            if raw_rows != rows or digest.hexdigest() != expected.lower():
                raise ValueError("실행의 원시 행 수·파일 내용 주장이 실제와 다르다")
            if rid == run_id:
                audit.update(rejected=rejected, raw_rows=raw_rows, n_files=len(files))
        disk = {p.relative_to(root).as_posix() for p in (root / "events").rglob("part-*") if p.is_file()}
        if disk != claimed:
            raise ValueError("실행이 주장하지 않은 파티션이 있거나 주장 파일이 빠졌다")
        audit.update(status="ok", verified_run_ids=sorted(run_rejections), run_rejections=run_rejections,
                     chain_rejected_total=sum(run_rejections.values()),
                     ancestor_rejected_total=sum(v for rid, v in run_rejections.items() if rid != run_id),
                     history_link_status="ok" if history_evidence is not None else "not_applicable",
                     external_parent_run_id=external, fingerprints=fingerprints)
    except Exception as error:  # 근거 실패는 0이 아니라 not_run이다. 호출자가 해당 단계만 중단한다.
        audit["reason"] = f"{type(error).__name__}: {error}"
    return audit


def outcome_observation_status(index_time, window_days: int, observation: Mapping | None) -> dict:
    """공개 관측·쓰기 근거의 판정. 이벤트 최댓값으로 근거를 만들지 않는다 (#179)."""
    import pandas as pd

    t0 = normalize_index_time(index_time)
    if type(window_days) is not int or window_days <= 0:
        raise ValueError("라벨 창 일수는 양의 정수여야 한다")
    end = t0 + pd.Timedelta(days=window_days)
    evidence = observation if isinstance(observation, Mapping) else {}
    reasons = []
    bounds = {}
    for key in ("start", "end"):
        try:
            stamp = pd.Timestamp(evidence.get(key))
            bounds[key] = stamp.tz_convert(TIMEZONE) if not pd.isna(stamp) and stamp.tzinfo else None
        except (TypeError, ValueError, OverflowError):
            bounds[key] = None
    start, observed_end = bounds["start"], bounds["end"]
    complete = start is not None and observed_end is not None and start <= t0 and observed_end >= end
    if not complete:
        reasons.append("LABEL_WINDOW_INCOMPLETE_OR_UNKNOWN")
    run_id = evidence.get("run_id")
    if not isinstance(run_id, str) or not run_id.strip():
        reasons.append("RUN_ID_MISSING")
    rejected = evidence.get("rejected")
    writing_complete = type(rejected) is int and rejected == 0 and "RUN_ID_MISSING" not in reasons
    if type(rejected) is not int or rejected < 0:
        reasons.append("WRITE_EVIDENCE_UNKNOWN")
    elif rejected > 0:
        reasons.append("WRITE_REJECTED")
    generated = evidence.get("purchase_generated")
    read_complete = evidence.get("read_complete") is True
    if not read_complete:
        reasons.append("EVENT_READ_INCOMPLETE_OR_UNKNOWN")
    if generated is not True:
        reasons.append("PURCHASE_NOT_OBSERVABLE" if generated is False else "PURCHASE_OBSERVATION_UNKNOWN")
    return {
        "status": "not_run" if reasons else "ok", "reasons": reasons,
        "run_id": run_id if isinstance(run_id, str) else None,
        "rejected": rejected if type(rejected) is int and rejected >= 0 else None,
        "label_window_complete": bool(complete), "writing_complete": writing_complete,
        "read_complete": read_complete, "read_detail": evidence.get("read_detail"), "root": evidence.get("root"),
        "purchase_generated": generated if type(generated) is bool else None,
        "window_start": t0.isoformat(), "window_end": end.isoformat(),
        "observation_start": None if start is None else start.isoformat(),
        "observation_end": None if observed_end is None else observed_end.isoformat(),
        "write_detail": evidence.get("write_detail"), "purchase_detail": evidence.get("purchase_detail"),
    }
