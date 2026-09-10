# W1 Discovery — 리버스 분석 종합 (John · Role 1)

**작성** 2026-09-10 · BATHOS Lv3 · 사이클 C1 · W1
**대상** `AI_ROI` @ `1140912` (main) · `Ecommerce_Service` @ `6b186d0` (main, **읽기 전용**)
**제약 준수 증명** 두 저장소 모두 **파일 변경 0건.** 쓴 것은 `AI_ROI/.agent-team/01-reverse/` 아래뿐이다.

> **이 문서는 자족적이다.** 다른 파일을 열지 않아도 전체 그림이 선다. 세부 근거는 각 절 끝의 상세 문서를 참조.

---

## 1. 한 문단 요약

AI_ROI의 **측정 계층은 뼈대가 견고하다** — 문서를 스키마에서 생성하고, 파트 격리를 AST 검사로 강제하며, 결손을 0으로 채우지 않는 것을 코드로 지킨다. 테스트 46건이 전부 통과한다(실행 확인).
그러나 **값 수준의 강제가 통째로 비어 있고**(식별자·타임존·카테고리 어휘), **Sink에 실행으로 재현되는 결함 3건**(파티션 덮어쓰기·`strict=False` 크래시·타임존 미변환)이 있다.
`Ecommerce_Service`는 **앱 품질은 양호하나**(lint PASS, 134 tests PASS — 재현함) **도메인 요구는 대부분 미해소**다. 최상위 차단점은 여전히 `unit_cost` 부재 → 기여이익 계산 불가 → **AI ROI 산출 불가.**
기존 이슈 `#24`~`#30`의 대조표는 **정확하고 최신이지만**, 사용자가 지시한 **제거 축**과 **누락 갭 10건**을 덮지 못한다.

---

## 2. 강점 5개 이상 — 각각 `파일:라인` 근거

| # | 강점 | 근거 |
|---|---|---|
| **S-1** | **문서를 손으로 쓰지 않는다.** `docs/event_schema.md`는 스키마에서 생성된다. 재생성 후 `diff` → **IDENTICAL**(실행 확인) | `scripts/gen_event_schema_doc.py:1-6` · `docs/event_schema.md:3-4, 178-182` |
| **S-2** | **파트 격리가 "실패하는 테스트"로 강제된다.** gitignore가 아니라 AST 기반 import·경로 검사이고 CI가 매 PR에서 돌린다 | `tests/test_isolation.py:86-139` · `.github/workflows/isolation.yml:36-41` |
| **S-3** | **결손을 0으로 채우지 않는 것이 코드다.** 근거 이벤트가 없는 지표를 `unavailable_metrics`로 **명시 목록화**한다. 빈 Sink는 Observable 16개 전부를 계산 불가로 표시 | `sink.py:240-256` · `tests/test_sink.py:172-203` |
| **S-4** | **출처 구분이 스키마에서 파생된다.** 별도 플래그 컬럼이 아니라 `simulator_version`·`random_seed`의 null 여부로만 판정 — 기록자가 위조할 여지가 적다 | `sink.py:79-83` (SRS MEA-002) |
| **S-5** | **금지 필드가 3중 방어다.** 스키마 자체 검사 + 런타임 거부 + 저장 차단 | `tests/test_schema.py:78-81` · `schema.py:285-287` · `tests/test_sink.py:138-143` |
| **S-6** | **거부를 조용히 버리지 않는다.** 위반 레코드를 사유와 함께 `rejected.jsonl`에 남긴다 | `sink.py:203-206` · `tests/test_sink.py:128-136` |
| **S-7** | **성능을 주장하지 않고 잰다.** 벤치 스크립트가 동봉돼 있고 내가 재현했다 — **4,200,000건 / 64.7초 / 112.6MB** | `scripts/bench_sink.py` |
| **S-8** | **라벨 누수 방지가 테스트로 고정된다.** Observable 지표가 파생 상태(`churn` 등)에 의존하면 테스트가 실패한다 | `tests/test_schema.py:188-196` |
| **S-9** | **NOT_APPLICABLE이 화이트리스트로 동작한다.** 이벤트에 맞지 않는 필드가 붙으면 거부 (예: `push_sent`에 `product_id`) | `schema.py:293-297` · `tests/test_schema.py:112-116` |
| **S-10** | **이슈가 스스로 미완을 밝힌다.** `#43`·`#44` 둘 다 "이 이슈를 닫지 않는 이유"를 코멘트로 남겼고, 내 코드 대조 결과 그 내용이 사실이다 | `#43`·`#44` 코멘트 |

---

## 3. 보완점 5개 이상 — 각각 `파일:라인` 근거 (심각도 순)

| # | 보완점 | 근거 | 심각도 |
|---|---|---|---|
| **W-1** | **동일 root 재기록 시 기존 파티션 파일을 덮어쓴다.** 독트링은 "append"라고 적혀 있다. 실행: 2건 저장 후 3건 저장 → **총 3건**(5건 아님) | `sink.py:113`(독트링) · `sink.py:146`(인스턴스별 Counter) · `sink.py:193-195` | **높음 — 데이터 소실** |
| **W-2** | **`strict=False` 경로가 크래시한다.** `validate_event()`가 **이미 거부한** 레코드를 `_observe`에 넘긴다. 실행: `ValueError` / `KeyError` | `sink.py:158-160` → `sink.py:169` | **높음 — MEA-003과 정면 충돌** |
| **W-3** | **타임존이 강제되지 않는다.** UTC `…Z`가 통과하고 파티션 날짜가 하루 어긋난다. 실행: `2025-10-01T23:30Z` → 파티션 `2025-10-01`(KST로는 10-02) | `schema.py:29-33`(선언만) · `sink.py:271-279`(변환 없음) | **높음 — 코호트·리텐션 왜곡** |
| **W-4** | **`check_identifier()`가 어디에서도 호출되지 않는다.** 형식 위반 식별자가 그대로 저장된다. 실행: `customer_id="test-user-1"` → `validate_event()` 통과 | `schema.py:324-326` (호출부 0건) | 중 |
| **W-5** | **`category`·`page_type` 허용값이 코드에 없다.** 자체 테스트끼리 어휘가 다르고 **둘 다 통과한다** | `schema.py:111-115` · `tests/test_schema.py:32`(`"신선식품"`) vs `tests/test_sink.py:35`(`"fresh_food"`) | 중 |
| **W-6** | **Parquet 경로가 한 번도 실행되지 않았다.** 로컬 pyarrow 없음(확인), CI에 설치 단계 없음. `#44` 완료 조건은 `events.parquet` SHA-256 일치를 요구한다 | `sink.py:297-302, 318-321` · `isolation.yml:34-35` | 중 · **BLOCKED** |
| **W-7** | **출처가 저장 레코드·파티션에 남지 않는다.** 대시보드가 출처별로 보여주려면 전량 재분류가 필요하다 | `sink.py:282-294` | 중 · **W5-C 영향** |
| **W-8** | **격리 검사가 `src/` 밖을 보지 않는다.** 대시보드를 `src/` 밖에 두면 사각지대가 된다 | `tests/test_isolation.py:51-55` | 중 · **W2 T2.10 입력** |
| **W-9** | **파생 상태(`inactive`/`at_risk`/`churn`)를 기록할 경로가 없다.** `EventType` 밖의 별도 Enum이라 Sink에 넣을 수단이 없다 — PRD §30.2는 "기록은 하되"를 요구 | `schema.py:66-76` vs `schema.py:41-63` | 중 |
| **W-10** | **manifest에 재현 메타가 없다.** `#44`가 요구한 버전키 4종의 **값**과 config 해시가 빠졌다 | `sink.py:220-245` | 중 |
| **W-11** | **manifest `created_at`이 UTC** — 자기 규약(KST 단일)과 어긋난다 | `sink.py:229` vs `schema.py:29-30` | 낮음 |
| **W-12** | **`write_batch()` 미구현** — `#44` 요구 목록에 있으나 없다 | `sink.py` 전체 | 낮음 |
| **W-13** | **`README.md`가 1줄, `docs/GIT_WORKFLOW.md` 부재** | `README.md:1` | 낮음 · W6 |

---

## 4. 실행한 검증 — 수치는 전부 실측이다

### AI_ROI

| 명령 | 결과 |
|---|---|
| `python3 -m unittest discover -s tests -v` | **46 tests OK** (0.030초). Python 3.14.6. charter 기준선과 일치 |
| `python3 scripts/gen_event_schema_doc.py \| diff docs/event_schema.md -` | **IDENTICAL** |
| `python3 scripts/bench_sink.py 2000 30` | 420,000건 / **6.4초** / 65,890건·초 / 11.3MB |
| `python3 scripts/bench_sink.py 20000 30` | 4,200,000건 / **64.7초** / 64,899건·초 / 112.6MB — `#44` "수 분 이내" 충족 |
| `parquet_available()` | **False** (pyarrow 미설치) → auto는 `jsonl.gz` |
| 결함 재현 4종 | 파티션 덮어쓰기 · `strict=False` 크래시 2종 · UTC 파티션 어긋남 — **전부 재현됨** |

### Ecommerce_Service (읽기 전용)

| 명령 | 결과 |
|---|---|
| `npm run lint` | **PASS** |
| `npm test` | **PASS — 13 files / 134 tests** (1.50초). `#24` 기록과 일치 |
| `git status --porcelain` (분석 후) | **빈 출력 — 변경 0건** |
| `npm run build` | **BLOCKED** — `prebuild`가 `tokens.generated.css`를 쓰고 `.next/`를 생성 |
| `npm run tokens:check` · `tokens:test` | **BLOCKED** — `tokens:generate`(파일 생성) 전제 |
| `npm run test:e2e` | **BLOCKED** — Chromium 미설치 |

---

## 5. `#43`(M-1)·`#44`(M-2)가 OPEN인 이유 — 규명 완료

**실수가 아니다.** 두 이슈 모두 작성자가 사유를 코멘트로 남겼고, 내가 코드로 대조한 결과 **미충족 항목이 실재한다.**

| 이슈 | 이슈가 밝힌 사유 | 내 독립 확인 | 이슈에 없는 추가 미충족 |
|---|---|---|---|
| `#43` M-1 | ① Observable 16개 **샘플 쿼리** 미실행 ② 식별자·`page_type`·세션만료가 **임의값** (GATE 1 Lock 전 확정 필요) | 둘 다 사실. 쿼리 없음 확인, 임의값 확인 | pyarrow 스키마 변환 미구현(`schema.py:14`가 M-2로 넘겼으나 M-2에도 없음) · 파생 상태 기록 경로 부재 · `category`/`page_type` 어휘 미확정 |
| `#44` M-2 | ① `events` 외 테이블 미구현 ② **Parquet 경로 미검증(BLOCKED)** ③ 처리량은 Sink 비용만 | 셋 다 사실. pyarrow 부재 확인, 처리량 재현(64.7초 vs 이슈 기록 63.8초) | **결함 3건(W-1·W-2·W-3)** · manifest 재현 메타 없음 · `write_batch()` 없음 |

> **Q4(닫을지 여부)는 사용자 판정 사항이다** — Issue close는 개별 승인 (AGENTS.md).
> **어느 쪽을 택하든 W-1·W-2·W-3은 별도 기록이 필요하다.** 현재 어느 이슈에도 없다 → 초안 `issue-drafts/AIROI-D1-sink-defects.md`.

**부수 발견:** `AI_ROI` 이슈 `#4`~`#35`(범위 A~D)는 전부 CLOSED이지만 **`NOT_PLANNED`** 다. 구현되어 닫힌 것이 아니라 PRD v2.2의 구축 순서 변경으로 **재구성 예정**이다(`#27` 종료 코멘트). **이후 웨이브에서 CLOSED를 "완료"로 읽지 말 것.**

---

## 6. `AGENTS.md` 실측 어긋남 (T1.5) — **보고만 함, 수정 안 함**

`AGENTS.md` "프로젝트 현황 (2026-09-10)":

| 문장 | 실측 | 판정 |
|---|---|---|
| "`src/`에 … **구현 코드는 아직 없다**" | `src/measurement/schema.py` 350줄 + `sink.py` 321줄 (PR #50·#51 머지) | **틀림** |
| "실행 가능한 검증 명령도 `tests.test_isolation` 하나뿐" | `test_schema` 20 + `test_sink` 20 추가 → **총 46건**. CI도 `discover -s tests` 실행 | **틀림** |
| "의존성 매니페스트는 아직 없다" / "CI는 isolation.yml 하나뿐" / "lint·build·타입 검사 미정의" | 확인 | 맞음 |

부수: `AGENTS.md` "검증" 절에 **46건을 돌리는 명령이 없다**(`tests.test_isolation`만 제시). `README.md`가 1줄.
**수정하지 않았다** — `task-graph.md` §4에 따라 `AGENTS.md`는 W6 Timothy 단독 소유다.

---

## 7. `Ecommerce_Service` 갭 — 실측 대조 요약

### 7.1 요구사항 대조 (`COM-001~005` · `DATA-001`·`DATA-003`)

| 요구 | 현재 | 근거 (`Ecommerce_Service/`) | 판정 |
|---|---|---|---|
| 카테고리 5종 (COM-001) | `category` 컬럼 없음 | `src/lib/server/commerce/schema.ts:9-16` | ❌ |
| 상품 30~50개 (COM-002) | **10개** | `src/lib/server/commerce/seed-data.ts` | ❌ |
| **`unit_cost`** (COM-002) | 없음 | `schema.ts:9-16` | ❌ **최상위 차단점** |
| `gross_margin` · `active_status` | 없음 | `schema.ts:9-16` | ❌ |
| 커머스 퍼널 (COM-003) | UI는 있으나 **관측 기록 없음** + 검색·재방문 미구현 | 라우트 5개 | ⚠️ |
| 라이프사이클 (COM-004) | `users(id, name)` — `signup_date` 없음 | `schema.ts:4-7` | ❌ |
| T1 Free Shipping | `const shippingKrw = 0;` **하드코딩** | `src/lib/server/commerce/purchase.ts:41` | ❌ |
| T2·T3 최소주문금액·유효기간 | 쿠폰에 조건 필드 없음 | `schema.ts:25-35` | ❌ |
| T4 Repurchase Reminder | 개념 자체 없음 (grep 0건) | — | ❌ |
| DATA-001 Customer Master | 9개 컬럼 중 1개 상당만 | `schema.ts:4-7` | ❌ |
| DATA-003 Event Log | **이벤트 기록 자체가 없음** | — | ❌ |
| Pretendard · 디자인 토큰 | 적용·동작 | `package.json:22`, `scripts/tokens/*` | ✅ |
| 앱 품질 | lint PASS · 134 tests PASS (재현) | §4 | ✅ |

**최상위 차단점 그대로:** `unit_cost`가 없어 `COGS = Σ(unit_cost × quantity)`를 못 구한다 → 기여이익 불가 → **Incremental Profit·AI ROI 산출 불가.** 이 프로젝트의 North Star가 여기에 걸려 있다.
**두 번째:** `shippingKrw = 0` 하드코딩이 T1을 무효화하고 배송 보조금을 기여이익에서 지운다.

### 7.2 `#24` 대조표 재검증 — **전 항목 여전히 정확하다**

작성(2026-09-10 13:47) 이후 커머스 main에 **소스 변경이 없다**(마지막 소스 커밋 `39d1668` 19:14, 이후는 Plan 포인터뿐). 각 행을 코드로 직접 확인했고 **`purchase.ts:41`은 줄 번호까지 정확**하다.

### 7.3 기존 이슈가 덮지 못하는 누락 갭 10건

| # | 갭 | 왜 미커버인가 |
|---|---|---|
| **G-1** | **식별자 형식 3종 위반** — `product_id`(`dummyjson-16`) · `order_id`(`randomUUID()`) · `coupon_id`(`fixed-3000`) | `#28`은 `session_id`만, `#29`는 `customer_id`만 다룬다. **AI_ROI도 못 막는다**(W-4) |
| **G-2** | **`orders.created_at`이 UTC** (`orders.ts:116`) | `#28`은 이벤트 timestamp만 다룬다. AI_ROI도 UTC를 통과시킨다(W-3) → **하루 밀린 파티션** |
| **G-3** | **주문 경제값 미저장 · 조용한 0 채우기** — `orders`에 `total_krw`만(`schema.ts:49-54`), 쿠폰 없는 주문은 `shippingKrw: 0`으로 재구성(`orders.ts:62-64`) | `#26`이 배송비를 도입하는 순간 **모든 쿠폰 없는 주문의 배송비가 조용히 0으로 보고된다.** charter 절대제약 6 위반 |
| **G-4** | **검색 기능이 존재하지 않는다** | `#28`이 `search` 기록을 요구하지만 **발생시킬 기능이 없다.** `search_count` 영구 계산 불가 |
| **G-5** | **구매 이력 화면이 없다** — `listOrders()`는 구현됐으나 **테스트에서만 호출** | PRD §13 `Purchase History`, `page_type=history` 미발생 |
| **G-6** | **상품 목록 전용 라우트 없음** (`page_type=list`) | 홈 앵커뿐 |
| **G-7** | **세션 개념이 없다** — `session_start`·`return_visit`의 근거 부재 | `#28`이 형식만 적고 수명주기는 수용 기준에 없다 |
| **G-8** | **T4에 하위 이슈가 없다** | `#24` 표엔 ❌로 있으나 `#25`~`#30` 어디에도 없다. `campaign_exposed`·`push_sent`가 `#28` 목록에서도 빠졌다 → 비용 회계 불가 |
| **G-9** | **카테고리 어휘 3자 불일치** — SRS(영문) / data_spec(한글) / AI_ROI(열거 없음) | **AI_ROI 쪽에서 먼저 확정해야 한다** |
| **G-10** | **e2e가 모든 하위 이슈에서 BLOCKED 상속** | Chromium 미설치, CI 자동 실행 구성 없음 |

**상세:** `ecommerce-gap.md` §3

---

## 8. ★ 제거 대상 (T1.6-d) — **목록은 비어 있지 않다. 9건.**

> 사용자 원문: *"PRD/SRS 대비 없애야 할 것(A테스트 B테스트 UI같은)"*
> **해석 확인:** "A/B 테스트(실험) UI"로 읽을 여지가 있어 먼저 검색했다 — `src/`·`e2e/`·`scripts/`에서 `experiment` `ab-test` `feature-flag` `bucket` `treatment` `cohort` `flag` **매치 0건.** (`variant` 20건은 전부 버튼 스타일 prop과 CSS `font-variant-numeric`.)
> 대신 화면 헤더에 **「테스트 사용자 A / B / C」 전환기**가 실재한다. **후자를 가리킨 것으로 읽었다.**

### 확신 높음 (4건)

| # | 대상 | 위치 | 왜 |
|---|---|---|---|
| **R-1** | **테스트 사용자 전환 UI 전체** | `UserMenu.tsx`(전체 87줄) · `StoreShell.tsx:30-35` · `seed-data.ts:97-99`(`테스트 사용자 A/B/C`) · `selection.ts:5`(`commerce-test-user` 쿠키) · `CheckoutPage.tsx:106` · `OrderComplete.tsx:13-14` · `app/layout.tsx:15` · `StoreShell.test.tsx:42,56,57,67,69,82` | 실제 장보기 서비스에 "사용자를 골라 그 사람이 되는" 화면은 없다. DATA-001은 `customer_id`·`signup_date`를 가진 **고객**을 요구한다 |
| **R-2** | **"배송비 0원 / 무료배송" 고정 문구 7곳** | `HomeHero.tsx:36` · `StoreShell.tsx:22` · `ProductDetail.tsx:41` · `CartPage.tsx:86` · `CheckoutPage.tsx:111,122` · `OrderComplete.tsx:49` (+테스트 `Catalog.test.tsx:95`, `PurchaseFlow.test.tsx:157,163`) | **T1 Free Shipping을 처치로 만들려면 평소 배송비가 0이 아니어야 한다.** `#26`은 `purchase.ts:41` 코드 상수만 다루고 **UI 문구는 수용 기준에 없다** — 배송비를 넣어도 화면은 계속 "무료"라고 말한다 |
| **R-3** | **"샘플 추천" 배지** | `ShopHome.tsx:28` (렌더 `ProductShelf.tsx:21`) | 자기가 더미임을 화면에 표시하는 라벨 |
| **R-4** | **`dummyjson-` 상품 ID 접두사** | `seed-data.ts` 10건 · `heroBanners.ts:8,16,24` · `ShopHome.tsx:14-15` + 테스트 | AI_ROI `product_id ^P\d{4}$`(`schema.py:314`) 위반. **`#30`은 `source_id`/`source_url` 필드만 다루고 ID 접두사는 언급하지 않는다** |

### 확신 중간 — 사용자 확인 필요 (3건)

| # | 대상 | 위치 | 논점 |
|---|---|---|---|
| **R-5** | **"모의 주문 / 구매 테스트 서비스" 문구 9곳** | `StoreShell.tsx:22,70` · `HomeHero.tsx:37` · `ProductDetail.tsx:42` · `CartPage.tsx:90` · `CheckoutPage.tsx:112,113,126`("모의 주문하기" 버튼) · `OrderComplete.tsx:22` · `app/layout.tsx:15` | 기준 환경은 실제 서비스처럼 보여야 Context가 된다(PRD §12.1). 반면 SRS §4.2가 실결제를 Out of Scope로 두니 고지는 정당. → **푸터 1곳만 남기고 구매 동선에서 제거** 제안 |
| **R-6** | **하드코딩된 상품 큐레이션** | `heroBanners.ts:8,16,24` · `ShopHome.tsx:14-15` | 상품이 30~50개로 늘면(`#25`) 깨진다. 특히 `"다시 담고 싶은 상품"`(`ShopHome.tsx:26`)은 **재구매 이력 기반이어야** COM-004에 기여하는데 상수다 — 이름이 데이터에 대해 사실과 다른 말을 한다 |
| **R-7** | **`source_id` / `source_url`** | `schema.ts:14-15` · `models.ts:6-7` · `catalog.ts:7` | **`#30`이 이미 "이 Issue에서 결론을 낸다"고 선언 — 중복 발행 금지.** 사용자 지시와 `#30`이 같은 대상을 가리킨다는 사실만 기록 |

### 확신 낮음 — 판단 재료만 (2건)

| # | 대상 | 논점 |
|---|---|---|
| **R-8** | **"오늘의 추천" 섹션** (`ProductRecommendations.tsx` 57줄, `ShopHome.tsx:21`) | 추천 알고리즘은 SRS §4.2 Out of Scope이고 현재는 하드코딩. 그러나 `product_view`·`add_to_cart` 퍼널 진입점 역할은 유효하다 |
| **R-9** | **히어로 캐러셀 자동 전환** (`HomeHero.tsx:13,22-27,55-72`, `useHeroCarousel.ts`) | **측정 관점 리스크:** 자동 전환을 `page_view`로 기록하면 세션 품질 Feature(`avg_session_duration`·`page_views_per_session`, `data_spec` §8)에 잡음이 섞인다. → **최소한 "캐러셀 전환은 `page_view`로 기록하지 않는다"는 규칙이 `#45`(M-3) 계약에 필요하다** |

### ⚠ 충돌 — 사용자 판정 필요

> **R-1이 이슈 `#29`와 정면 충돌한다.**
> `#29` 범위 절: *"실제 회원가입·인증·비밀번호 (SRS §4.2 Out of Scope). **테스트 사용자 전환 방식은 유지해도 됩니다**"*
> 사용자 지시: *"없애야 할 것(테스트 사용자 A·B UI 같은)"*
> **같은 사람이 쓴 이슈와 지시가 서로 반대다.** 둘 중 하나가 갱신되어야 한다.

**상세:** `ecommerce-gap.md` §4

---

## 9. 타 개발자 작업 충돌 (T1.7) — ⚠️ **즉시 확인 필요**

### 9.1 참여자

| 저장소 | 작성자 | 커밋 | 성격 |
|---|---|---|---|
| `AI_ROI` | `Inseong Kim / Danto` (동일인 = 사용자) | 15 | **실질 단독** |
| `Ecommerce_Service` | **`SeongHwan <epaktldk0203@gmail.com>`** | **18** | **커머스 구현 전부** — 부트스트랩·디자인 토큰·테스트 환경·SQLite·구매 흐름·쿠폰·버그픽스 |
| `Ecommerce_Service` | `Inseong Kim / Danto` (사용자) | 9 | Plan 포인터 · AGENTS.md |

**SeongHwan의 최근 작업: `39d1668` "fix: 구매 동작 중 화면 번쩍임 방지" — 2026-09-10 19:14. 오늘이다.**
그리고 그 커밋은 **`#24`~`#30` 이슈 발행(13:47~13:49) 이후**다 — 활동이 살아 있는 저장소다.

### 9.2 즉시 눈에 띄게 보고할 것

> **`Ecommerce_Service`의 스토어프론트 코드는 우리가 아닌 다른 사람이 썼다.**
> §8의 제거 대상 R-1~R-9는 **전부 SeongHwan의 작업물**이다 (`UserMenu.tsx`·`HomeHero.tsx`·`ShopHome.tsx`·`heroBanners.ts`).
> `#24`~`#30` 7건은 **전부 사용자 계정이 작성**했고 **담당자가 지정되어 있지 않으며 착수 흔적이 없다.**
> 즉 **이슈를 쓰는 쪽과 코드를 쓰는 쪽이 다르다.** 우리가 초안을 얹으면 그 사람에게 갈 지시가 늘어난다.

### 9.3 코드 충돌 위험

| 축 | 결과 |
|---|---|
| 열린 PR | **0건** (양 저장소) |
| main보다 앞선 브랜치 | **실질 0건** — `feat/design-tokens`는 2026-09-05 낡은 잔재, `fix/storefront-pending-flicker`는 main과 **1줄(Plan 포인터) 차이** |
| 미커밋 변경 | AI_ROI `?? .agent-team/`(우리 것) · Ecommerce **없음** |
| C1 편집 영역 | `src/measurement/**` + 신규 대시보드 경로 — **타 작성자 없음** |

**→ C1 범위에서 코드 충돌은 발생하지 않는다.** 커머스 편집 0건 원칙을 지키는 한.

**상세:** `collision-check.md`

---

## 10. charter 가정 판정

### A6 — "`Ecommerce_Service`를 편집하지 않고 **스키마 계약만으로 통합이 성립**한다"

> **판정: ⚠️ 성립하나 지금은 아니다 — "계약이 존재한다"와 "계약이 지켜진다"는 다르다.**

| 근거 | 내용 |
|---|---|
| **성립 쪽** | 런타임 의존이 실제로 없다. 커머스는 Next.js/SQLite, AI_ROI는 표준 라이브러리 Python. 공유하는 것은 `docs/event_schema.md`뿐이고 SRS MEA-001이 이를 정본으로 지정했다(`SRS:826`). 측정 계층은 커머스가 없어도 단독 실행·테스트된다(46건 통과) |
| **아직 아닌 쪽** | **커머스가 이벤트를 한 건도 기록하지 않는다.** Sink의 `sources.commerce`는 영원히 0이다. 계약은 **한쪽만의 선언**으로 존재한다 |
| **계약 자체의 구멍** | 계약이 **값 수준을 규정하지 않는다** — 식별자·타임존·`category`/`page_type` 어휘가 비어 있거나 강제되지 않는다(W-3·W-4·W-5, G-9). 커머스가 "계약을 지켰다"고 말해도 검증할 기준이 없다 |
| **비대칭** | 계약이 커머스에 요구하는 것(`unit_cost`·`category`·이벤트) 중 **어느 것도 커머스에 없다.** 편집 없이 성립하려면 **커머스가 편집되어야 한다** — 그 편집을 우리가 하지 않을 뿐이다 |

**결론:** A6은 *"AI_ROI가 커머스를 편집하지 않는다"* 로는 **유효**하다. *"편집 없이도 통합이 완성된다"* 로는 **거짓**이다.
**C1 판정 기준으로 쓰려면 후자를 "커머스 갭을 이슈로 남긴다"로 좁혀야 한다** — charter §2.2 목표 1이 이미 그렇게 적혀 있으므로 실질 문제는 없다.
**단, `#45`(M-3) 계약 문서는 `AIROI-D2`(값 수준 강제)가 먼저 풀려야 쓸 수 있다.**

### A9 — "기존 Ecommerce 이슈 `#24`~`#30`이 갭의 **대부분**을 이미 덮는다"

> **판정: ✅ 성립. 단 "대부분"이지 전부는 아니다.**

| 축 | 판정 |
|---|---|
| `#24` 대조표의 **정확성** | ✅ **전 항목 정확하고 최신이다.** `purchase.ts:41`은 줄 번호까지 맞다. 작성 이후 소스 변경 없음 |
| **핵심 차단점 커버** | ✅ `unit_cost`(#25) · 배송비(#26) · 쿠폰 조건(#27) · 이벤트(#28) · `signup_date`(#29) — 5대 갭 전부 하위 이슈 존재 |
| **미커버** | ❌ **누락 갭 10건**(§7.3) + **제거 축 9건**(§8) |
| 특히 심각한 미커버 | **G-3**(주문 경제값 0 채우기 — `#26` 착수 시 즉시 데이터 오류) · **G-4**(기록하라는 `search`를 발생시킬 기능이 없다) · **G-8**(T4에 하위 이슈 자체가 없다) |

**결론:** 신규 이슈 **대량 발행은 불필요하다.** 초안 5~7건이면 충분하고, 그중 3건(`ECOM-E8`·`E9`·`E11`)은 기존 이슈에 흡수해도 된다.
**A9는 유지하되 "제거 축은 처음부터 없었다"는 단서를 붙인다.**

### A10 — "타 개발자와 작업이 충돌하지 않는다"

> **판정: ⚠️ 조건부 성립.**

- **코드 충돌: 없다.** C1 편집 영역(`src/measurement/**` + 신규 대시보드)에 타 작성자가 없다. 열린 PR·미완 브랜치 0건.
- **의사결정 충돌: 있다.** 커머스 코드의 **3분의 2를 SeongHwan이 소유**하고 우리 제거 제안은 그 작업물을 대상으로 한다. `#29`와 사용자 지시가 서로 반대다.
- **전제 조건:** `Ecommerce_Service` 편집 0건 원칙을 끝까지 지킬 것. 깨지는 순간 A10은 무효가 되고 별도 킥오프가 필요하다(charter §5).
- **권고:** W5 착수 직전에 이 점검을 1회 재실행한다 — 오늘 활동이 있었던 저장소라 스냅샷이 금방 낡는다.

---

## 11. BLOCKED 전체 목록

| # | 항목 | 사유 |
|---|---|---|
| B-1 | AI_ROI **Parquet 쓰기·읽기 경로 검증** | pyarrow 미설치(`parquet_available() == False` 확인). 설치는 환경 변경이라 금지. `#44` 완료 조건이 여기 걸려 있다 |
| B-2 | AI_ROI **Observable 16개 샘플 쿼리** (`#43` 완료 조건) | 데이터 생성은 이제 가능하나 **쿼리 자체가 저장소에 없다.** 내가 새로 쓰면 제품 코드 추가 → W1 권한 밖 |
| B-3 | Ecommerce **`npm run build`** | `prebuild`가 `src/styles/tokens.generated.css`를 쓰고 `next build`가 `.next/`를 생성 |
| B-4 | Ecommerce **`npm run tokens:check` · `tokens:test`** | `#24` 기록상 `tokens:generate`(파일 생성) 선행 전제 |
| B-5 | Ecommerce **`npm run test:e2e`** | Chromium 미설치. `playwright install`은 파일 생성 |
| B-6 | Ecommerce **앱 실행 후 화면 확인** | `npm run dev`가 `predev`→`tokens:generate`로 파일을 쓰고, `db:init`이 SQLite 파일을 만든다 |
| B-7 | 커머스 **카테고리별 원가율 정합 확인** (`#25` 수용 기준) | 원가 데이터 자체가 없다 |
| B-8 | **실제 커머스 이벤트로 스키마 왕복 검증** | 커머스에 이벤트 기록이 없다(`#28` 미착수) |
| B-9 | **`#43`·`#44` close 여부 판단** | Issue close는 개별 승인 사항 — 사용자 판정 |
| B-10 | `docs/data_spec.pdf` 대조 | PDF 바이너리. HTML 정본으로 대조함 |

---

## 12. 다음 웨이브 인계

### W2 Joshua (기획 · 게이트 소유)

- **T2.1(A8, 대시보드 개수) 판정 시 W-7·W-8을 입력으로 쓸 것** — 출처가 저장 레코드에 남지 않고(`sink.py:282-294`), 격리 검사가 `src/` 밖을 보지 않는다(`test_isolation.py:51-55`). 대시보드 경로 결정이 두 문제를 건드린다.
- **T2.4(경제 규칙, charter Q2) 결론 재료:** 커머스에 `unit_cost`가 없다는 사실은 확정이다. `docs/data_spec.html` §6.1이 카테고리별 원가율(신선 78% / 간편식 70% / 유제품 75% / 음료 68% / 생활용품 72%, 가중평균 기여마진 26%)을 초안으로 갖고 있으므로 **커머스 미해소 상태에서도 Config 값으로 정의는 가능**하다. 다만 그 값으로 계산한 기여이익은 **시뮬레이터 생성분에만** 유효하고 커머스 실측분에는 계산 불가로 표시해야 한다.
- **T2.5(이슈 발행 승인 패키지):** 초안 7건이 `issue-drafts/`에 있다. **`#29` 충돌(§8) 해소가 선행 조건.**

### W2 James (아키텍처)

- **T2.7(지표 계약):** `manifest.json`이 이미 대시보드가 읽을 수 있는 형태다(`sink.py:220-245`). 다만 **버전키 값·config 해시가 빠져 있어**(W-10) 재현 메타로는 부족하다.
- **T2.9(의존성 도입):** pyarrow를 넣는 순간 CI에 설치 단계가 생기고, 동시에 **B-1이 풀린다.** 두 사안을 함께 설계할 것.
- **T2.11(GATE 1 Freeze):** **`AIROI-D2`(값 수준 강제)가 Lock 이전에 끝나야 한다.** 어휘와 식별자 형식이 빠진 채 `EVENT SCHEMA v1`을 Lock하면 되돌릴 수 없다.

### W5 Phillip

- **W-1·W-2·W-3은 새 기능보다 먼저 고칠 것.** 초안 `AIROI-D1`에 재현 절차와 수용 기준이 있다.
- 기준선: `discover -s tests` **46건**, 벤치 **4,200,000건 / 64.7초 / 112.6MB**.

### W6 Timothy

- `AGENTS.md` "프로젝트 현황" 문단 갱신 (§6). `README.md`(1줄) · `docs/GIT_WORKFLOW.md`(부재).

---

## 13. 산출물

| 파일 | 내용 |
|---|---|
| `reverse-summary.md` | **이 문서** — 자족 종합 |
| `measurement-map.md` | T1.1~T1.3 — 측정 계층 실측 지도 · 문서/코드 불일치 14건 |
| `issue-code-audit.md` | T1.4~T1.5 — 이슈 대비 코드 대조 · `#43`·`#44` OPEN 사유 · `AGENTS.md` 어긋남 |
| `ecommerce-gap.md` | T1.6 (a)(b)(c)(d) — 대조표 · 이슈 커버리지 · 누락 갭 10건 · **제거 대상 9건** |
| `issue-drafts/` | T1.6(e) — 신규 이슈 초안 7건 (**발행 안 함**) + 발행 순서 제안 |
| `collision-check.md` | T1.7 — 참여자·브랜치·PR 실측 · 충돌 5건 |
