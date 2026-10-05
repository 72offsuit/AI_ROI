# DR-S1-rng — 난수는 (고객 · 용도 · 날) 열쇠의 해시 카운터로 뽑고, 결과는 정수로만 만든다

| | |
|---|---|
| 태스크 | S1 · #75 |
| 작성 | James(BATHOS 역할 에이전트) · 2026-10-04 |
| 상태 | 확정 |

## 무엇을 정하는가

시뮬레이터의 난수를 **어떤 구조로 나누고(전역 1개 · 고객별 · 고객×용도별), 무엇으로 시드를 유도하고, 어떤 원시 연산으로 뽑는가.** 함께 정하는 것:

- `event_id`(UUID4 형태)를 어떻게 결정적으로 만드나
- "같은 seed → 같은 바이트"가 **어떤 범위에서** 성립하나 (Python 판 · 플랫폼)
- 그 범위를 지키려면 생성 코드가 **무엇을 쓰면 안 되나**(부동소수 · libm · `random` 모듈)
- 이슈 #75 리뷰 질문 — *시드를 고정해도 결과가 달라질 수 있는 경로*(dict 순회 · 집합 순서 · 병렬 · 부동소수 누적)에 각각 무엇으로 답하나

## 정하지 않으면 무엇이 막히나

- 이슈 #75 "증거로 남길 것" 3종이 전부 이 결정 위에 선다 — 같은 시드 2회 **바이트 동일**, `snapshot → advance(30) → restore → advance(30)` 이 **연속 실행과 동일**, 고객 1명을 바꿔도 **다른 고객 궤적 불변**.
- `snapshot()` 이 저장해야 하는 범위(`DR-S1-world-state`)가 난수 상태의 표현에 달려 있다. 이슈 #75 표: *"난수 상태를 빼먹으면 `restore` 후 다른 궤적이 나온다."*
- `S2`(#76)의 Hidden Trait 표집, `S6`의 Potential Outcome 이중 실행(Common Random Numbers, `docs/data_spec.html:387-397`, `src/simulator/_internal/AGENTS.md:21-27`)이 같은 스트림 구조를 쓴다. S2 이후 바꾸면 재현성 테스트가 전부 깨진다(이슈 #75 "미확정").
- `D9`(#91)의 "같은 시드 두 번 실행이 같은 결과" 완료 조건.
- SRS NFR-004 는 Python 3.10 이상을 선언하고 CI 가 3.10(`python-compat.yml`)과 3.12(`isolation.yml`·`tests-with-deps.yml`)에서 같은 테스트를 돈다(`AGENTS.md:107`). 판마다 다른 이벤트가 나오면 어느 판의 결과가 정답인지 말할 수 없다.

## 선택지

| 안 | 내용 | 장점 | 단점 |
|---|---|---|---|
| A | 전역 `random.Random(seed)` 1개 | 가장 단순 | 고객 한 명의 난수 소비가 바뀌면 **그 뒤 모든 고객**의 궤적이 밀린다. 스트림 독립 증명 불가 |
| B | 고객×용도별 영속 `random.Random` (리드 초기 권고). 시드 = sha256(JSON `["sim-rng-v1", seed, customer_id, purpose]`) | 표준 라이브러리. 뽑기가 빠르다(측정 19 ns) | 상태가 크다 — 스트림당 `getstate()` 625 정수(JSON 7,333 B, 메모리 약 24 KB, 아래 측정). 스냅샷·저장이 스트림 상태 전부를 들고 다녀야 한다. 한 번 어긋난 소비가 그 고객의 **남은 전 기간**을 밀어낸다 |
| C | **고객×용도×날 열쇠의 해시 카운터.** n 번째 뽑기 = sha256(열쇠 ‖ n) 앞 8바이트 | 날 경계에서 **난수 상태가 0** — 창 경계가 늘 자정이므로 스냅샷·저장에 난수 상태가 없다. 소비 어긋남이 그 고객의 그 날 안에 갇힌다. `random` 모듈에 의존하지 않아 판 간 알고리즘 변경과 무관하다 | 뽑기가 B 보다 약 15배 느리다(측정 270~310 ns) |
| D | numpy `PCG64` + `SeedSequence.spawn` | 사실상 표준. `data_spec` 이 이 표기를 쓴다 | **의존성 금지** — `requirements.txt:30-32` 가 numpy 를 의도적으로 빠뜨렸고 격리·3.10 CI 가 의존성 없이 전체 테스트를 돈다(`.github/workflows/isolation.yml`, `python-compat.yml`) |
| E | 고객×용도×날마다 `random.Random` 을 새로 시드 | 날 경계 상태 0 (C 와 같다) | 시드 1회 약 4.9 µs(측정). 26,000명 × 640일 × 용도 수만큼 반복. `random()` 외 메서드의 판 간 불변성은 보증되지 않는다 |
| F | Philox 등 카운터 기반 RNG 를 순수 파이썬으로 구현 | C 와 같은 성질, 원리상 더 빠를 수 있다 | 정답 벡터 대조까지 직접 해야 하고 순수 파이썬 정수 연산이라 C 구현인 `hashlib` 보다 빠르다는 근거가 없다 |

판 간 동일성 정책도 두 안이 있었다.

| 안 | 내용 |
|---|---|
| 판 엄격 일치 (초안) | 같은 판·같은 플랫폼에서만 바이트 동일을 보증하고, 판이 다른 상태 파일은 거부한다 |
| **판 무관 동일 (확정)** | Python 3.10 이상 모든 판에서 같은 seed 가 같은 바이트를 내도록 생성 코드를 정수로만 쓴다 |

## 조사한 것

| 출처 | 무엇을 말하나 | 우리 맥락에 얼마나 맞나 |
|---|---|---|
| CPython `random` 문서 "Notes on Reproducibility" (https://docs.python.org/3/library/random.html) | 판이 바뀌어도 보증되는 것은 둘뿐이다 — 호환 시더가 제공된다, **`random()` 이 같은 시드에서 같은 열을 낸다.** "Most of the random module's algorithms and seeding functions are subject to change across Python versions" | 리드 초기 권고의 "`random()`/`getrandbits()` 만 쓴다" 중 **`getrandbits()` 는 보증 대상이 아니다** — 문서에 판 간 안정성 언급이 없다 |
| 같은 문서의 변경 이력 | `randrange()` 3.2 에서 알고리즘 변경(균등 분포 개선), 3.12 에서 비정수 인자 거부 · `seed()` 3.11 허용 타입 축소 · `shuffle()` 3.11 `random` 인자 제거 · `sample()` 3.11 집합 입력 거부 · `binomialvariate()` 3.12 추가 | 알고리즘이 바뀐 이력이 실제로 있다(3.2 `randrange`). 3.10–3.12 사이 출력 변경 기록은 찾지 못했다 |
| 로컬 측정 (스크래치 스크립트, Python 3.9.6 · 3.12.13 · 3.13.13 · 3.14.7, macOS arm64) | seed 12345 에서 `random()`·`randrange()`·`choice()`·`gauss()`·`getrandbits()` 출력이 네 판 모두 같았다 | **관찰이지 보증이 아니다.** 3.10 은 로컬에 없어 직접 보지 못했다 |
| 같은 측정 — 비용 | `Random()` 생성 약 6 µs · `random()` 약 19 ns · sha256 `copy()+update(카운터)` 1회 270~310 ns · blake2b 키 모드 350~450 ns · 시드+1회 뽑기 약 4.9 µs · `getstate()` JSON 7,333 B / 메모리 약 24.5 KB (tracemalloc) | 안 B·C·E 비용 비교의 근거. blake2b 가 sha256 보다 느려 sha256 을 고른다 |
| Python 데이터 모델 문서 `object.__hash__` | `str`·`bytes` 의 `hash()` 는 프로세스마다 예측 불가 값으로 솔트된다(`PYTHONHASHSEED`) | 로컬에서 `hash("C00000001")` 이 실행마다 달랐다. **`hash()` 로 시드를 만들면 재현되지 않는다** |
| `docs/data_spec.html:236` · `:330` · `src/simulator/_internal/AGENTS.md:25` | "`customer_seed = hash(random_seed, customer_id)`", 배정 RNG `PCG64(seed = 20251001 ⊕ hash(customer_id))` | 해시 함수가 정해져 있지 않고, 파이썬 `hash()` 로 구현하면 위 이유로 재현이 깨진다. PCG64 는 numpy 다. **이 DR 이 그 자리를 구체화한다** |
| Salmon · Moraes · Dror · Shaw, "Parallel Random Numbers: As Easy as 1, 2, 3", SC11 (https://users.cs.utah.edu/~hari/teaching/bigdata/random123sc11.pdf) | 카운터에 대한 **열쇠 있는 변환**이 통계적으로 우수한 PRNG 계열을 이루고, 상태 메모리가 거의 없으며, AES·Threefish 같은 암호 기반 변형도 다룬다 | 안 C 는 이 계열의 암호 해시판이다. 논문의 성능 수치는 C/GPU 구현 기준이라 파이썬 속도에는 쓸 수 없다 — 속도는 위 로컬 측정만 쓴다 |
| NumPy "Parallel Random Number Generation" (https://numpy.org/doc/stable/reference/random/parallel.html) | `root_seed + worker_id` 같은 산술 시드는 "UNSAFE" — 겹치는 스트림이 생긴다. `SeedSequence` 는 아발란치 성질의 해시로 시드를 펼친다. n 개 스트림 충돌 확률 약 n²·2⁻¹²⁸ | "시드 하나 고정"으로 부족한 이유(이슈 #75 조사 항목)에 대한 답이다. 안 C 는 열쇠를 **문자열 그대로** 해시하므로 산술 결합이 없다 |
| 내장 `sum()` 문서 (https://docs.python.org/3/library/functions.html#sum) + gh-100425 (https://github.com/python/cpython/issues/100425) | "Changed in version 3.12: Summation of floats switched to an algorithm that gives higher accuracy" (Neumaier) | 로컬에서 `sum([0.1]*10)` 이 3.9.6 에서 `0.9999999999999999`, 3.12.13 에서 `1.0`. **3.10 CI 와 3.12 CI 가 다른 바이트를 낼 수 있는 실재하는 경로**다 |
| `math` 모듈 문서 CPython 구현 세부 (https://docs.python.org/3/library/math.html) | "The `math` module consists mostly of thin wrappers around the platform C math library functions." `exp`·`log` 의 정확 반올림 보증 문구는 없다. `fsum` 도 "On some non-Windows builds … may occasionally double-round an intermediate sum causing it to be off in its least significant bit" | `exp`·`log`·`pow` 의 결과는 **플랫폼 libm 에 따라 마지막 비트가 다를 수 있다.** 결과에 들어가는 값에 쓰면 판·플랫폼 간 바이트 동일을 보증할 수 없다 |
| `src/measurement/schema.py:192` · `:442` | `event_id` 는 UUID4, 패턴은 버전 니블 4 · variant `[89ab]` | 결정적으로 만들되 이 패턴을 지켜야 Sink 가 거부하지 않는다 |
| `src/measurement/sink.py:527-528` 주석 | 20K × 30일 벤치에서 Sink 쓰기 전체 78.7 s | 생성 시간 예산의 대부분이 Sink 쪽이라는 참고치 |

## 결정

**안 C — 고객×용도×날 열쇠의 sha256 카운터. 전역 RNG 없음, `random` 모듈 사용 없음.** (사용자 확인 2026-10-04)

**판 무관 동일 — Python 3.10 이상 모든 판(3.10 · 3.12 · 3.14)에서 같은 seed 는 바이트 동일한 이벤트를 낸다.** (사용자 결정 2026-10-04: "3.10 이 기준이니 3.10 에서도 문제가 안 생기도록 코드를 작성")

**호환 범위 (사용자 결정 2026-10-04, Matthias R-1).** "`requirements.txt` 를 설치하면 모든 판(3.10 이상)에서 전 기능이 동작한다. 의존성이 없는 환경은 jsonl.gz 루트만 읽을 수 있다." 바이트 동일한 **생성**과 상태 이어받기는 의존성과 무관하다. 저장 형식은 런타임 기본값(pyarrow 가 있으면 parquet)이고 루트마다 고정되므로, parquet 계보를 의존성 없는 런타임에서 잇거나 관측하면 `SinkFormatError` 다(`DR-S1-world-state`). 근거: `requirements.txt:21` 의 `pyarrow==25.0.1` 은 PyPI 에서 `requires_python >=3.10` 이고 cp310~cp314 휠을 낸다(2026-10-04 PyPI JSON 으로 직접 확인). 대안 "시뮬레이터는 항상 jsonl.gz"는 S3 규모의 크기·속도 때문에 사용자가 기각했다.

```
열쇠       = UTF-8( JSON ["sim-rng-v1", seed, customer_id, purpose, day], separators=(",", ":"), ensure_ascii=True )
n 번째 뽑기 = 앞 8바이트( sha256( 열쇠 ‖ n 을 8바이트 big-endian ) )   →  u64      (n 은 0 부터)
베르누이    p = p_num / p_den (정수 분수, 0 ≤ p_num ≤ p_den, p_den > 0)
              참  ⇔  u64 < (p_num · 2⁶⁴) // p_den                       정수 비교
정수 [0,k)  = u64 거부 표집 (2⁶⁴ − 2⁶⁴ mod k 이상이면 n+1 로 다시)        정수만
가중 선택   = 정수 가중치의 누적합 위에서 정수 [0, 합) 하나를 뽑는다
```

- `day` 는 KST 일 번호(시작일 0, `DR-S1-time-model`). 카운터 n 은 **(고객, 용도, 날) 안에서만** 산다. 창 경계는 언제나 자정이므로(같은 DR) **경계에서 살아 있는 난수 상태가 없다** — `snapshot()`·`save_state()` 는 난수 상태를 저장하지 않고 `rng_scheme = "sim-rng-v1"` 과 `seed` 만 싣는다. 이슈 #75 의 "난수 상태를 빼먹는" 실패가 **구조적으로 생길 자리가 없다.**
- 고객과 무관한 표집(예: `S4` 카탈로그 생성)은 `customer_id` 자리에 `null` 을 둔다.
- S1 용도 이름: `visit`(그날 방문 여부) · `session`(세션 시각·길이·간격) · `browse`(어떤 상품을 보나) · `cart`(담기·빼기·수량). 용도를 **추가**해도 다른 용도의 뽑기는 그대로다. 용도 이름을 **바꾸면** 그 용도의 난수가 바뀌므로 `simulator_version` 을 올린다.
- `event_id` = sha256(JSON `["sim-event-id-v1", seed, customer_id, seq]`) 앞 16바이트에 버전 니블 `4`, variant `10xx` 를 덮어쓴 UUID. `seq` 는 고객별 단조 순번(`DR-S1-world-state`) — **별도 스트림 상태가 필요 없다.** 무작위 비트 122개, 1,200만 건 충돌 확률 약 n²/2¹²³ ≈ 1.4×10⁻²³.

**판 무관 동일을 지키는 생성 코드 규칙** (결과 — 이벤트·상태 — 에 들어가는 모든 값에 적용)

| 규칙 | 왜 |
|---|---|
| 확률·비율은 **정수 분수**(`p_num`, `p_den`)로 표현하고 비교도 위 식처럼 정수로 한다. 부동소수 비교를 쓰지 않는다 | 부동소수 경로가 하나라도 있으면 `sum()`·libm 차이가 비교 결과를 뒤집을 수 있다 |
| 시각·지속시간은 **정수 ms**, 금액은 **정수 원** | `DR-S1-time-model`. 측정 계약도 금액을 정수 원으로 둔다(`schema.py:206` · `:209-210`) |
| float `sum()` · `math.exp`/`log`/`pow` · `random` 모듈을 쓰지 않는다 | `sum()` 은 3.12 에서 알고리즘이 바뀌었고(위 조사), `math` 는 플랫폼 libm 의 얇은 포장이며 정확 반올림을 보증하지 않는다. `random` 은 `random()` 외 판 간 보증이 없다 |
| JSON 직렬화는 `sort_keys=True` · `separators=(",", ":")` · `ensure_ascii=True` 로 고정하고, **결과에 float 가 들어가지 않는다** | float 의 텍스트 표현과 반올림 문제가 바이트에 새지 않게 한다 |
| 내장 `hash()` · `uuid.uuid4()` · `os.urandom` · `secrets` · `time.time()`/`datetime.now()` 를 생성 경로에서 쓰지 않는다 | 솔트 · OS 난수 · 벽시계 |
| `int.to_bytes`/`from_bytes` 에 길이·바이트 순서를 항상 명시한다. `datetime.UTC` 대신 `timezone.utc` | 기본값·별칭이 3.11 에서 생겼다 |

규칙의 대조 장치: 구현 시 `src/simulator/` 를 AST 로 훑어 위 금지 이름(`random` import, `math.exp`/`log`/`pow`, 내장 `hash`·`sum` 의 float 사용 지점, `uuid4`, `time.time`, `datetime.now`)을 잡는 테스트를 둔다 — 선언에는 대조 장치(`docs/TEAM_SETUP.md:268`).

**판 간 동일의 증명 — 골든 해시.** 소규모 정준 실행(예: seed 42 · 고객 50명 · 14일, 값은 구현 때 고정)의 정준 이벤트 열 SHA-256(`DR-S1-world-state` 의 비교 단위)과 끝 상태 다이제스트를 **테스트에 상수로 박아 둔다.** CI 세 잡 — `python-compat.yml`(3.10) · `isolation.yml`(3.12) · `tests-with-deps.yml`(3.12) — 이 같은 상수를 맞춰야 통과한다. 생성 규칙을 바꾸면 상수와 `simulator_version` 을 함께 올린다 — 상수가 바뀐 커밋이 곧 "무엇이 결과를 바꿨나"의 기록이 된다.

**구현 기록 (2026-10-04 리뷰 반영).** 골든 상수는 `{simulator_version: (이벤트 다이제스트, 끝 상태 다이제스트, 건수)}` 로 판에 묶여, 현재 판의 키가 없으면 실패한다(Thomas L7 — 상수만 갱신하고 판 상향을 빠뜨리는 것을 잡는다, `tests/test_simulator_reproducibility.py:13-22`). `simulator_version` 은 측정 계약 표기 `sim-{major}.{minor}`(`docs/measurement_contract.md:197`)를 따라 `sim-0.1` 이다(Thomas M4). 정준 실행은 seed 42 · 고객 50명 · 14일 · profile `smoke` 이고, `sim-0.1` 의 값은 이벤트 `fdfbc1e43a07ce603ab92a06b9fc4c0287e45d8be04f6d81f18adf7b7576cda1`, 끝 상태 `90cec765cabb841434760eb98b6a7881123061ac25765bab225edc9677ea7ed6`, 716건이다. 리드 보고로 3.10·3.12·3.14 에서 일치했다. 이 기록은 결정을 바꾸지 않는다 — 위 정책("상수와 판을 함께 올린다")을 테스트로 강제한 것이다. **남는 빈틈 (L7 잔여, Thomas 재리뷰):** 새 판의 키가 빠진 것은 잡지만, **같은 판 키 안에서 상수만 바꾸는 것은 기계적으로 막을 수 없다.** 리뷰가 막는다 — 골든 상수가 바뀌는 diff 에 `simulator_version` 변경이 없으면 리뷰에서 거부한다.

**이슈 #75 리뷰 질문에 대한 답**

| 경로 | 왜 결과를 흔드나 | 규칙 |
|---|---|---|
| dict 순회 | 삽입 순서가 보증되지만(3.7+) 삽입이 비결정적이면 순회도 그렇다 | 고객 집합은 `customer_id` 오름차순으로만 순회한다. 직렬화는 `sort_keys=True` |
| 집합(set) 순회 | `str` 의 해시가 프로세스마다 솔트되어 **실행마다 순서가 다르다** | 출력에 영향을 주는 경로에서 set 을 순회하지 않는다. 필요하면 `sorted()` |
| 병렬 실행 | 작업 완료 순서가 실행마다 다르다 | S1 은 단일 스레드. 고객별 열쇠라 나중에 고객 분할 병렬화를 해도 뽑기가 바뀌지 않으며, 합칠 때는 `(time_ms, customer_id, seq)` 로 정렬한다 |
| 부동소수 누적 | 합산 순서·알고리즘이 결과 비트를 바꾼다. 3.12 의 `sum()` 변경이 실례다 | **결과에 들어가는 값에 부동소수를 쓰지 않는다** (위 규칙표) |
| 내장 `hash()` · `uuid4()` | 솔트 · OS 난수 | 금지 |
| 벽시계 | 실행 시각이 섞인다 | 생성 경로 금지. Sink 의 `created_at`·`run_id`(`sink.py:307` · `:340-345`)는 시계를 쓰지만 이벤트 비교 대상이 아니다 |
| 파일 목록 순서 | `glob`·`iterdir` 순서는 파일시스템마다 다르다 | 항상 `sorted()` — Sink 도 이미 그렇게 한다(`sink.py:331` · `:360` · `:607`) |
| 압축 파일 바이트 | gzip 헤더에 기록 시각(mtime)이 들어간다. 로컬에서 같은 내용을 1.1초 간격으로 압축하니 바이트가 달랐다 | **파일 바이트를 비교하지 않는다.** 비교는 디코드한 레코드 열의 정준 직렬화로 한다(`DR-S1-world-state`) |
| `heapq` 동률 | 같은 키면 꺼내는 순서가 넣은 순서에 좌우된다 | 키 `(time_ms, customer_id, seq)` 가 유일하다(`DR-S1-time-model`) |
| Python 판의 알고리즘 변경 | `random`·`sum()`·libm | 셋 다 결과 경로에서 쓰지 않는다. 골든 해시가 3.10·3.12 에서 대조한다 |

**근거:** 리드 초기 권고(안 B)의 목표 — 고객×용도 독립, 솔트 없는 시드 유도, 전역 RNG 없음 — 를 그대로 지키면서, 안 B 가 남기는 두 비용을 없앤다. ① 상태 크기: 26,000명(`docs/data_spec.html:211`) × 용도 4 = 104,000 스트림이면 저장 JSON 약 760 MB, 메모리 스냅샷 약 2.5 GB(위 측정값 곱). ② CRN 표류: 안 B 에서 처치로 한 번 더 뽑으면 그 고객의 **이후 전 기간** 난수가 밀리고, 안 C 에서는 그 **날 안**에서만 밀린다 — S6 이중 실행의 `Y(1) − Y(0)` 이 처치 외 잡음을 덜 담는다. 판 무관 동일은 SRS 가 선언한 최소 판(3.10)을 CI 가 실제로 돌리는 저장소에서, "어느 판의 결과가 정답인가"라는 질문이 생기지 않게 하는 유일한 정책이다. 정수만 쓰면 판·플랫폼 차이가 끼어들 연산이 남지 않는다.

## 기각한 안과 기각 사유

| 안 | 왜 택하지 않았나 |
|---|---|
| A 전역 1개 | 이슈 #75 표 그대로 — 고객 한 명의 로직 변경이 다른 모든 고객을 바꿔 "이 변경이 무엇을 바꿨나"를 볼 수 없다. 스트림 독립 증거를 낼 수 없다 |
| B 영속 MT (리드 초기 권고) | 위 상태 크기·스냅샷 비용·CRN 표류. 그리고 `getrandbits()` 는 판 간 보증 대상이 아님을 문서에서 확인했다 |
| D numpy | 의존성 금지. 격리 CI 가 설치 단계 없이 돈다 |
| E 날마다 MT 재시드 | 26,000 × 640일 × 4 용도 ≈ 6,660만 회 × 4.9 µs ≈ 5.4 분이 시드에만 든다. 안 C 의 날 경계 상태 0 을 같은 값에 얻으면서 C 보다 비싸다 |
| F Philox 자체 구현 | 정답 벡터 대조 · 성능 근거 · 유지 비용이 모두 우리 몫이 된다. 같은 "카운터 기반" 성질을 표준 라이브러리 `hashlib` 이 이미 준다 |
| 시뮬레이터는 항상 jsonl.gz (R-1 대안) | **사용자 기각 2026-10-04.** S3 규모(20K+ · 12M+ 이벤트)에서 크기와 속도가 불리하다. 3.10 은 `requirements.txt` 설치로 전 기능을 얻는다 |
| 판 엄격 일치 — 같은 판·플랫폼에서만 보증, 판이 다르면 상태 거부 (초안) | **사용자 결정 2026-10-04.** 3.10 이 선언된 기준 판인데, 판마다 다른 결과를 허용하면 3.10 CI 와 3.12 CI 중 어느 쪽이 정답인지 말할 수 없고, 한 판에서 저장한 상태를 다른 판에서 이어받지 못한다 |
| 균등 실수 `(u64 >> 11) × 2⁻⁵³` 와 부동소수 비교 (초안) | 위 정책 변경으로 기각. 정수 비교로 같은 판정을 부동소수 없이 한다 |

## 이 결정이 틀렸다면 어떻게 드러나나

- 같은 시드 2회 실행의 이벤트 다이제스트가 다르다 → 금지 목록 밖의 비결정 경로가 있다.
- 고객 k 하나의 규칙을 바꿨는데 k 가 아닌 고객의 이벤트가 하나라도 달라진다 → 고객 간 공유 자원이 난수에 섞였다(아래 "남은 불확실성"의 `order_id` 처럼).
- **골든 해시가 3.10 잡에서만(또는 3.12 잡에서만) 깨진다** → 판에 의존하는 연산이 결과 경로에 남아 있다. AST 금지 검사를 빠져나간 지점을 찾는다.
- 개발 기계(macOS)의 골든 해시가 CI(Ubuntu)와 다르다 → 플랫폼 의존 연산이 남아 있다.
- `S3` 규모(20K+ · 12M+)에서 프로파일러로 본 sha256 호출이 생성 시간의 절반을 넘는다 → 속도 가정이 틀렸다. 그때 B 의 상태 비용과 다시 비교한다.
- 뽑기 100만 회 균등성 검정(용도별 χ², 정수 구간 빈도)이 기각된다 → 구현 결함이다(sha256 자체의 결함일 가능성은 낮다).

## 민감도

- **뽑기 비용.** 사건당 뽑기 수 k 는 S4 전까지 모른다. 이벤트 1,200만 건 × k=3 이면 약 3,600만 회 × 0.3 µs ≈ 11 초, 날마다 방문 결정 26,000 × 640 ≈ 1,660만 회 ≈ 5 초. Sink 쓰기 78.7 s(20K × 30일, `sink.py:528`)와 견주면 작다. k 가 ±20% 바뀌어도 초 단위 변화다. k 가 30 을 넘으면 1~2 분대가 되어 SIM-013 "20,000명 × 30일 ≤ 수 분"(`Plan/AI_Customer_Retention_ROI_SRS_v2.0.md:682`)과 견줄 만해진다.
- **정수 확률의 해상도.** 임계값이 `(p_num · 2⁶⁴) // p_den` 이라 확률 해상도는 2⁻⁶⁴ 이다. 정밀도 손실은 없고, 확률을 분수로 적는 쪽의 표현 해상도(`p_den`)만 결과를 좌우한다.
- **안 B 의 상태 크기**는 고객 수·용도 수에 정비례한다. 고객 ±20% → 저장 JSON 약 610~910 MB. 안 C 는 0 이다.

## 남은 불확실성

- **확인한 판과 플랫폼.** 이 DR 을 처음 쓸 때 로컬 기본 인터프리터는 3.14 하나였고 3.10 은 없었다. 이후 리드 보고로 골든(`sim-0.1`)이 3.10·3.12·3.14 에서 일치했다 — 모두 macOS 다. **Linux 골든은 첫 CI 가 확인한다.** 3.14 는 CI 잡이 없다. Thomas 재리뷰도 3.10 jsonl.gz · 3.12 parquet · 3.12 jsonl.gz 강제 · 3.14 와 `PYTHONHASHSEED`·`LC_ALL` 조합에서 골든 일치를 확인했다(macOS).
- **3.10 + 의존성 설치 조합은 CI 에 없다.** `python-compat.yml` 은 3.10 을 의존성 없이 돈다. R-1 의 "3.10 에서 전 기능"은 Matthias 가 scratchpad venv(3.10 + `requirements.txt`)에서 실측으로 확인했다 — 최종 검증 R-1 PASS, `events()` 전체가 3.12 연속 실행과 같았다. 이 조합을 상시 지키는 CI 잡은 여전히 없다.
- **F-1 — 3.10 간헐 실패, 누적 96회 중 1회, 원인 미상.** 첫 실패의 테스트 이름이 남지 않았고 그 뒤로 재현되지 않았다. 생성 결정성 문제인지는 모른다 — 골든·분할 불변성 시험은 같은 기간 모두 통과했다. CI `python-compat` 이력을 확인해야 한다.
- **S2 이후 연속 분포.** `data_spec` 의 Beta·LogNormal·Gamma 표집(`docs/data_spec.html:234-235` · `:241`)과 감쇠 `exp(−λ t)`(`:267`)는 지금 규칙 아래에서 `exp`·`log` 를 결과 경로에 쓸 수 없다. 오프라인에서 계산해 정수 상수로 고정한 분위수 표(역누적분포 표)나 정수 근사로 구현해야 한다. 표의 해상도가 분포 충실도를 정한다 — S2(#76)·S4(#78)·S5 가 각자 DR 에 적는다.
- **고객 간 공유 순번.** `order_id` 형식 `^O\d{8}-\d{6}$`(`schema.py:445`)을 날짜별 전역 순번으로 매기면 한 고객의 주문 추가가 다른 고객 주문의 ID 를 밀어 "다른 고객 궤적 불변" 대조가 깨진다. 해시로 만들면 6자리라 충돌한다. **S1 은 주문을 만들지 않으므로 S4(#78)가 정한다.**
- **후속 이슈 후보(보고만, 고치지 않음):** `docs/data_spec.html:236` · `:330`, `src/simulator/_internal/AGENTS.md:25` 의 `hash()`·`PCG64` 표기가 이 결정과 다르다. 정정 여부와 시점은 리드가 정한다.
- Windows 에서는 확인하지 않았다.
