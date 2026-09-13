# `results/` 증거 사본 — 실제 파이프라인 산출물

**생성** Phillip (Role 8 · W5-A) · 2026-09-11
**명령** `python3 -m src.measurement.publish`  (PyYAML·pyarrow 설치 환경)

## 왜 여기 있나

결정 **D-17**(`results/` 를 `.gitignore` 에 넣는가)이 사용자 결정 대기다. W2 추천은
**⑶ — `results/` 제외 + `.agent-team/` 에 증거 사본**이고, 이 디렉터리가 그 사본이다.
`.agent-team/**` 는 team 소유이므로 `check_ownership.py` 가 이것을 결함으로 잡지 않는다.

**Andrew 는 D-17 결정과 무관하게 이 사본을 실제 게시물 표본으로 쓸 수 있다.**
다만 대시보드가 런타임에 읽는 경로는 저장소 루트의 `results/` 다 — 이 사본은
형태 확인용이고 앱이 이것을 읽게 만들지 않는다.

## 이 산출물의 상태 — 오늘의 정상 상태다

```
verdict           attention · SINK_EMPTY
gate_result       incomplete
수집 이벤트        0건        (커머스 미연동 · 시뮬레이터 미가동)
품질 검사          18종 — vacuous 8 · not_run 9 · blocked 1
지표               계산됨 18 · 계산 불가 30
```

**화면이 계산 불가로 가득한 것은 버그가 아니라 정상 동작이다** (USP-1).
`SINK_EMPTY` 는 *"활동 없음"* 이라고 말하지 않는다 — heartbeat 가 없어 수집 중단과
활동 없음을 구분할 수 없고, 그 사실이 `notices` 의 `INGESTION_GAP_UNDECIDABLE` 에 있다.

## ★ 배치 — ADR-0002

```
results/measurement/index.json                    ← 대시보드 진입점
results/measurement/ingestion_report.json
results/measurement/rejection_report.json
results/measurement/field_coverage_report.json
results/measurement/kpi_report.json
results/measurement/freeze_status.json
results/data_quality_report.json                  ← ★ 예외 (data_spec §9 · 이슈 #48)
```

**1차 게시는 전부 루트에 넣었고 그것은 ADR-0002 위반이었다.** Andrew 의 리더가
원래 `results/measurement/index.json` 을 찾았는데 내 잘못된 출력에 맞춰 고쳤다 —
**그의 원래 기대가 맞았다.** `tests/test_publish_pipeline.py TestArtifactLayout` 이
`artifacts[].path` 를 W2 픽스처와 문자 단위로 대조해 고정한다.

## 검증됨

- **7종 전부 수정된 계약(`docs/contracts/measurement-publish/v1/`)을 통과** — 위반 0건
- 계산 불가에 `value`·`basis`·`value_formatted` 가 있는 것 **0건** (USP-1)
- 계산된 지표 18건 전부에 `value_formatted` **존재** (Andrew 의 화면이 읽는 필드)
- 전 산출물이 같은 `run_id` 를 공유
- `artifacts[].path` 와 `views[].route` 가 **W2 픽스처와 문자 단위로 일치** (`V4` = `/kpi`)
- `metrics[]` 38종 — `experiment` 계층 14종 포함 · `role` primary 2 · guardrail 3 · `blocks` 11종

## 데이터가 있는 경우의 산출물

이 사본은 빈 Sink 기준이다. **실제 이벤트가 있는 경로**는
`tests/test_publish_pipeline.py` 의 `TestRepresentativeScene` 이 `EventSink` 로
진짜 이벤트를 쓰고 게시해 검사한다 (리드 판정 J-1 — 손으로 쓴 JSON 이 아니라
실제 파이프라인 산출물). 그 장면에서 `revenue` 는 `ok`(`"47,000원"`)이고
`contribution_profit` 은 `unavailable`(`NO_COST_BASIS`)이다 — **USP-1 대표 장면**이다.

재현:
```bash
python3 -m unittest tests.test_publish_pipeline.TestRepresentativeScene -v
```
