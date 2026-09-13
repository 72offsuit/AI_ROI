---
name: test-flow
role: Matthias (Role 15 · QA/SDET)
wave: W6 · 1단계
date: 2026-09-14
---

# 테스트 실행 절차 — 재현 명령

이 문서에 적힌 명령은 **전부 이 세션에서 실제로 실행해 통과를 확인한 것**이다. 존재하지 않는 명령을 적지 않는다(AGENTS.md).

## 0. 사전 준비

```bash
cd /Users/otter/72offsuit/AI_ROI
git status --porcelain   # 작업 전 상태 확인 — .agent-team/_state/* 외 변경 없어야 함
python3 --version        # 3.14.6 (로컬)
```

## 1. Python 측 — 회귀·격리·소유권

```bash
# ① 의존성 없이 (isolation.yml과 동일 조건)
python3 -m unittest discover -s tests
# → Ran 407 tests in 0.393s · OK (skipped=67)

# ② 격리 경계 단독
python3 -m unittest tests.test_isolation -v
# → Ran 6 tests · OK

# ③ 소유 경계
python3 .agent-team/04-architecture/tools/check_ownership.py
# → Phillip 46개 ∩ Andrew 50개 = 0개 · 판정: PASS

# ④ 의존성 설치 후 (선택 경로가 실제로 실행되는지)
python3 -m venv /tmp/qa-airoi-deps
/tmp/qa-airoi-deps/bin/pip install -q -r requirements-dev.txt
/tmp/qa-airoi-deps/bin/python -m unittest discover -s tests
# → Ran 407 tests in 4.481s · OK (skipped=3)
```

## 2. 대시보드 — 빌드·토큰·상태맵

```bash
cd dashboard
npm ci
# → added 369 packages, 0 vulnerabilities

npm run build
# → next build 성공, 8라우트 컴파일 (Route (app) 목록에 /, /coverage, /freeze, /ingestion, /kpi, /quality, /rejections, /triggers)

npm run tokens:test
# → 15 scenarios passed

npm run check:state-map
# → 25 assertions passed
```

## 3. 픽스처 준비 (Andrew의 스크립트를 read-only로 호출 — `dashboard/.fixtures/`는 gitignore 대상)

```bash
cd dashboard
node scripts/stage-fixture.mjs empty-sink
node scripts/stage-fixture.mjs commerce-connected
# 실제 results/는 이미 저장소 루트에 존재 (M-06 publish() 산출물, gitignore 대상)
```

## 4. 독립 e2e 하네스 — `e2e/` (QA 신규 작성, `dashboard/` 미수정)

```bash
cd e2e
npm install                 # @playwright/test 1.63.0 — 브라우저 바이너리는 이미 캐시됨(~/Library/Caches/ms-playwright)
npx playwright test
# → 43 tests · 41 passed · 2 failed (의도적 red, 아래 참조)
```

`playwright.config.ts`가 포트 4601(`empty-sink`)·4602(`commerce-connected`)·4603(`real`)에서 `npx next start`를 각각 띄운다(`webServer` 배열, `cwd: ../dashboard`). 세 서버가 각자 다른 `AIROI_RESULTS_DIR`을 읽으므로 `dashboard/` 코드를 건드리지 않고도 세 데이터셋을 동시에 실제로 서빙해 비교할 수 있다.

### 4.1 의도적으로 red인 테스트 2건

```
tests/fixture-contract-freshness.spec.ts
  ✘ fixture "empty-sink" kpi_report.json satisfies the current value_formatted requirement
  ✘ fixture "commerce-connected" kpi_report.json satisfies the current value_formatted requirement
```

이 둘은 실패가 **의도된 결과**다 — qa-summary.md §3-A에서 기록한 실제 결함(커밋된 예시 픽스처가 M-06 계약보다 낡음)을 자동으로 고정해 둔 것이다. 픽스처가 `docs/contracts/measurement-publish/v1/` 현재 계약에 맞게 재생성되면 이 두 테스트가 저절로 green이 된다 — 그것이 "고쳤다"의 검증 기준이다.

## 5. 라이브 코드 실행으로 인수조건 재현 (unittest 커버리지와 별개로, 독립적으로 다시 실행)

```bash
# US-1 — 값 수준 강제가 실제로 거부하는지
python3 -c "
import sys; sys.path.insert(0, '.')
from src.measurement import schema as sc
rec = {'event_id':'e1','event_type':'product_view','timestamp':'2025-10-01T09:00:00.000+09:00',
       'session_id':'s1','customer_id':'C12345678','category':'우주선','page_type':'product_detail'}
print(sc.validate_event(rec))
"
# → problems 리스트에 "category 허용값이 아니다 — '우주선'" 포함

# US-3 — 분할 기록이 앞 구간을 지우지 않는지
python3 -c "
import sys, tempfile
sys.path.insert(0, '.')
from src.measurement import sink as sk
with tempfile.TemporaryDirectory() as tmp:
    ev = lambda i: {'event_id': f'{i:08x}-1234-4123-8123-{i:012x}', 'event_type':'session_start',
                    'timestamp':'2025-10-01T09:00:00.000+09:00', 'session_id': f'S-C{i:08d}-{1700000000000+i:013d}',
                    'customer_id': f'C{i:08d}', 'page_type':'home'}
    with sk.EventSink(tmp) as s: s.write_events([ev(1), ev(2)])
    with sk.EventSink(tmp) as s: s.write_events([ev(3), ev(4), ev(5)])
    print(len(list(sk.read_events(tmp))))
"
# → 5 (2+3, 소실 없음)

# US-7 — economics.py 창구 중립성
grep -inE "commerce|simulator" src/measurement/economics.py || echo "0 matches"
# → 0 matches
```

## 6. 대비(C-10) 독립 재계산

```bash
python3 /tmp/contrast_check.py   # WCAG 상대휘도 공식, missing-state-spec.md §4.3의 8개 hex 쌍
```

브라우저 측 재확인은 `e2e/tests/contrast.spec.ts`가 `getComputedStyle`로 실제 CSS 변수를 읽어 같은 공식으로 재계산한다(문서 hex를 베끼지 않고 라이브 토큰에서 읽음).

## 7. 스크린샷 생성 + 육안 검토

```bash
cd e2e
npx playwright test tests/pages.spec.ts
# → e2e/screenshots/{empty-sink,commerce-connected,real}/{index,ingestion,rejections,coverage,kpi,quality,freeze,triggers}.png
```

24장 중 8장(real 4종 + commerce-connected 1종 + 추가 확인분)을 Read 도구로 직접 열어 육안 검토했다 — qa-summary.md §2.2.

## 8. 정리

```bash
# 백그라운드로 띄운 수동 확인용 서버(4501·4502·4701·4801·4802 포트) 전부 종료 확인
lsof -i :4501 -i :4502 -i :4701 -i :4801 -i :4802 -i :4601 -i :4602 -i :4603
# → 출력 없음 (전부 종료됨)

git status --porcelain -- dashboard/ src/ tests/ config/
# → 빈 출력 (제품 코드 변경 0건 — e2e/·.agent-team/11-qa/만 신규)
```
