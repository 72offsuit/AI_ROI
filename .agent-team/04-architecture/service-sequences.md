# 서비스 시퀀스

**작성** James (Role 4 · Architect) · 2026-09-11 · 사이클 C1

> C1 의 실행 경로는 넷이다. **각 시퀀스의 실패 분기를 함께 그린다** — 정상 경로만 그린 시퀀스는 설계가 아니다.

---

# S-1 · 이벤트 수집 (구현됨)

```mermaid
sequenceDiagram
    participant SRC as 기록자<br/>(커머스 UI / 시뮬레이터)
    participant Sink as sink.EventSink
    participant Schema as schema.validate_event
    participant FS as data/raw/

    SRC->>Sink: write_events(records)
    loop 레코드마다
        Sink->>Schema: validate_event(record)
        Schema-->>Sink: problems: list[str]
        alt problems 있음
            Sink->>Sink: rejected += 1 · _rejected 에 사유와 함께 보관
            alt strict=True (기본)
                Sink->>Sink: continue — 저장하지 않는다
            else strict=False
                Note over Sink: ⚠ #53 D1-2 — 여기서 크래시한다<br/>_observe() 가 EventType(record["event_type"]) 를<br/>무조건 호출하는데 이미 거부된 레코드다
            end
        else 통과
            Sink->>Sink: _observe — 출처 분류 · 타입 집계 · 필드 충족률
            Sink->>Sink: buffer 에 넣는다
        end
    end
    alt buffer >= chunk_rows (200,000)
        Sink->>FS: flush — date=YYYY-MM-DD/part-NNNN
    end

    SRC->>Sink: close()
    Sink->>FS: flush 잔여
    Sink->>FS: rejected.jsonl (거부분이 있을 때만)
    Sink->>FS: manifest.json
    Note over FS: ⚠ #53 D1-1 — 같은 root 에 두 번 쓰면<br/>part-0000 을 덮어쓴다 (데이터 소실)
```

| 결함 | 영향 | 이슈 |
|---|---|---|
| D1-1 파티션 덮어쓰기 | **데이터 소실.** 데이터 생성 전에 고쳐야 한다 | `#53` |
| D1-2 `strict=False` 크래시 | `MEA-003` 정면 충돌 — 결손 관용 경로가 죽는다 | `#53` |
| D1-3 타임존 미강제 | UTC 가 통과하고 **파티션 날짜가 하루 어긋난다** → 코호트·리텐션 왜곡 | `#53` |

---

# S-2 · ★ 게시 (신설 · T2.7)

```mermaid
sequenceDiagram
    participant Op as 사람
    participant Pub as publish.py
    participant Cfg as config_loader
    participant Sink as sink (manifest · read_events)
    participant Calc as kpi · economics<br/>(순수 함수)
    participant Val as validate.py
    participant Frz as freeze.py
    participant Con as contracts.py
    participant FS as results/

    Op->>Pub: python3 -m src.measurement.publish (★ 아직 없다)
    Pub->>Pub: run_id = MR-YYYYMMDD-HHMMSS-<8hex>

    Pub->>Cfg: load_economic_config()
    alt PyYAML 없음 / 파일 없음 / 스키마 위반
        Cfg-->>Pub: ConfigError → 종료 코드 5. 게시하지 않는다
    end
    Note over Cfg,Calc: ★ CostAccountingConfig 만 넘긴다<br/>ProductGenerationConfig(원가율)는 넘기지 않는다 (EC-9)

    Pub->>Sink: manifest() · read_events()
    Pub->>Pub: ★ partition_by_source(events)  ← 출처를 아는 유일한 자리

    loop 출처마다 (commerce · simulator)
        Pub->>Calc: kpi.*(events_of_source, index_date=D)
        Note over Calc: 자기가 어느 출처를 받았는지 모른다<br/>같은 함수 · 같은 식 · 다른 입력 (N-3)
        Calc-->>Pub: MetricValue (ok | unavailable | ...)
    end

    Pub->>Val: run_quality_checks()
    Val-->>Pub: QualityReport(gate_result, checks[])
    alt gate_result == "fail"
        Pub->>FS: data_quality_report.json 은 쓴다
        Pub-->>Op: QualityGateFailure → 종료 코드 2 · 이후 단계 중단
    end

    Pub->>Frz: verify(config/gate1_lock.yaml)
    Frz-->>Pub: FreezeVerification (match | mismatch | missing | not_run)

    Pub->>Con: envelope(...) + 자기검증
    loop 산출물 6종
        Con->>Con: 계약 불변식 확인
        alt 위반
            Con-->>Pub: ContractViolation → 그 산출물을 게시하지 않는다<br/>index 에 status:failed · publish_result:partial
        else 통과
            Pub->>FS: .staging/<run_id>/ 에 쓴다
        end
    end
    Pub->>FS: os.replace 로 최종 경로에 옮긴다
    Pub->>FS: ★ index.json 을 마지막에 쓴다
    Pub->>FS: .staging/<run_id>/ 삭제
```

## S-2 의 설계 요점 넷

| # | 요점 |
|---|---|
| **①** | **출처를 아는 자리는 `partition_by_source` 한 줄뿐이다.** 계산 함수는 출처를 모른다 → 창구 중립성이 구조로 유지된다 (`code-structure.md` N-3) |
| **②** | **`index.json` 을 마지막에 쓴다.** 읽는 쪽이 인덱스를 먼저 읽으므로, 인덱스가 없거나 옛것이면 부분 게시 상태를 보지 않는다 |
| **③** | **`fail closed`.** 자기 스키마를 통과하지 못한 산출물은 게시하지 않는다. 잘못된 값은 화면에서 정상으로 보이지만, 없는 파일은 없다고 보인다 |
| **④** | **품질 게이트 `fail` 은 게시를 멈추되 품질 리포트는 남긴다.** 왜 멈췄는지가 화면에 있어야 한다 |

---

# S-3 · 대시보드 읽기

```mermaid
sequenceDiagram
    participant U as 사용자
    participant Page as Server Component
    participant Art as lib/artifacts
    participant FS as results/

    U->>Page: GET /kpi  (수동 새로고침 — DB-011)
    Page->>Art: loadView("V4")
    Art->>FS: results/measurement/index.json
    alt 파일 없음
        Art-->>Page: ArtifactMissing
        Page-->>U: EmptyState — "게시물이 없다. 게시 명령을 실행한다" (DB-013)
    end

    Art->>Art: contract_version 확인
    alt 불일치
        Art-->>Page: ContractVersionMismatch
        Page-->>U: "계약 버전 불일치" — 그리지 않는다
    end

    Art->>FS: views.V4.artifact 경로 읽기
    Note over Art: resolveArtifactPath() 화이트리스트<br/>results/ 밖이면 IsolationError
    Art->>Art: run_id == index.run_id ?
    alt 다름
        Art-->>Page: RunIdMismatch
        Page-->>U: "게시 진행 중 또는 불일치" — ★ 값을 섞지 않는다
    end

    Art->>Art: 최소 불변식 — status != "ok" 인데 value != null 이면 던진다
    Art-->>Page: KpiReport
    Page->>Page: MetricValue 컴포넌트가 status 5종을 다른 시각 상태로 그린다
    Page-->>U: 렌더링 + notices + ProvenanceBar
```

**대시보드가 계산하지 않는다** (`DB-012`) — 합계·비율·출처 분류·계산 불가 판정이 **전부 게시 시점에 끝나 있다.**

---

# S-4 · GATE 1 부분 봉인과 대조

```mermaid
sequenceDiagram
    participant Op as 사람
    participant CL as docs/gate1_checklist.md
    participant Frz as freeze.py
    participant Lock as config/gate1_lock.yaml
    participant Test as tests/test_freeze.py
    participant Pub as publish.py
    participant V6 as 대시보드 V6

    rect rgb(245,245,245)
    Note over Op,CL: 봉인 — 사람이 판단한다
    Op->>CL: G-1 ~ G-16 을 하나씩 확인하고 증거를 적는다
    alt 미충족이 남았다
        Op->>CL: 그 항목을 PARTIAL/PENDING 으로 둔다. 없는 척하지 않는다
    end
    Op->>Frz: freeze record --by "<이름>"   (★ 아직 없는 명령 · 사용자 지시 후)
    Frz->>Lock: 항목 9종 · scope_note · SHA-256 · repo_commit · KST 시각 · locked_by
    Note over Lock: declaration: PARTIAL_FREEZE<br/>experiment_environment_v1_declared: false<br/>simulator_commit: null + 사유
    Op->>Lock: git add config/gate1_lock.yaml (사용자 지시 후)
    end

    rect rgb(245,245,245)
    Note over Test,V6: 탐지 3층 — 같은 freeze.verify() 를 쓴다
    Test->>Frz: verify()
    alt 해시 불일치
        Frz-->>Test: mismatch → ★ 테스트 실패 (경고 아님)
    else Lock 기록 없음
        Frz-->>Test: not_started → ★ skip 하지 않는다. not_started 임을 단언한다
    end

    Pub->>Frz: verify()
    Frz-->>Pub: FreezeVerification
    Pub->>V6: freeze_status.json (mismatch 면 notices level:failure)
    V6-->>Op: 화면에서 확인 (charter §2.2-3 "화면으로 증명한다")
    end
```

> **이 시퀀스가 막지 못하는 것:** *"결과를 본 뒤 시뮬레이터를 고치는 것"*.
> 해시는 **바뀌었다**를 알려줄 뿐 **왜**를 모른다. 성능이 나쁘다고 고치고 다시 Lock 하면 대조는 통과한다.
> 막는 것은 `FREEZE-002`·`FREEZE-003` 절차와 `git log config/gate1_lock.yaml` 에 남는 재봉인 이력이다. → `gate1-freeze-procedure.md` §4.5

---

# S-5 · 실패 경로 한 표

| # | 실패 | 어디서 | 결과 |
|---|---|---|---|
| F-1 | 스키마 위반 레코드 | `validate_event` | 거부 + `rejected.jsonl` → **V2 에 집계로 보인다** |
| F-2 | `timestamp` 해석 실패 | `_partition_key` | `ValueError` — **조용히 넘기지 않는다** (`sink.py:277-279`) |
| F-3 | config 없음/위반 | `config_loader` | `ConfigError` → 종료 5 · **게시하지 않는다** |
| F-4 | 품질 검사 위반 | `validate.py` | `QualityGateFailure` → 종료 2 · 품질 리포트는 남긴다 |
| F-5 | 산출물이 자기 스키마 위반 | `contracts.py` | `ContractViolation` → 그 산출물만 미게시 · `partial` |
| F-6 | 봉인 해시 불일치 | `freeze.verify` | 게시하되 `notices level:failure` · **테스트는 실패** |
| F-7 | 게시물 없음 | 대시보드 | **게시 방법 안내** (`DB-013`) |
| F-8 | `run_id` 불일치 | 대시보드 | 불일치 표시 · **값을 섞지 않는다** |
| F-9 | 허용 경로 밖 읽기 | `lib/artifacts` | `IsolationError` — 런타임 방어 |
| F-10 | pyarrow 없음 | `sink.resolve_format` | `jsonl.gz` 폴백 + **`DQ-17` 을 `blocked` 로 게시** |

전체 분류·종료 코드·처리 규칙은 `exceptions.md`.
