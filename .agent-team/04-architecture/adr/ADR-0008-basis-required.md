# ADR-0008 · 계산된 값에 기준(`basis`)을 필수로, 계산 불가에 금지한다

**상태** 확정 · 2026-09-11 · James
**요청** Jonnathan (Role 7 · 디자인) T2.13
**맥락** T2.7 개정 1

## 문제
`ADR-0003` 이 `value: null` 을 강제해 "0으로 채우기"를 막았다. 그러나 **반대 방향의 실패**가 남아 있었다.

`{"status":"ok","value":0}` 과 `{"status":"unavailable","value":null}` 을 화면에서 구별하는 일이 **글리프 하나**(0 vs —)에 걸린다.
글리프는 색·폰트·밀도에 따라 읽히는 강도가 달라지고, 스크린샷·인쇄·저시력 환경에서 무너진다.
그리고 **"세어 봤고 0이었다"** 는 정직한 값인데, 그것을 계산 불가로 그리면 그것도 거짓말이다.

## 결정
`metric_value` 에 **`basis`(기준)** 를 도입한다.

```jsonc
"basis": { "population": "coupon_use 이벤트", "denominator_definition": "분모 없음 (건수)",
           "denominator": null, "observed_count": 0,
           "window": { "direction": "retrospective", "days": 42 },
           "excluded_count": 0, "excluded_reason": "..." }
```

**스키마 강제:**
- `status` 가 `ok`·`unconfirmed` → **`basis` 필수**
- `status` 가 `unavailable`·`blocked`·`not_run` → **`basis` 금지**
- `unit: ratio` + 계산됨 → `basis.denominator` 필수
- `basis.denominator == 0` → `status` 가 `ok` 일 수 없다

## 근거
> **기준의 유무가 판별자가 된다.**
> `0원 · 기준: coupon_use 1,204건 중 0건` 은 *"세어 봤다"* 의 증거이고, `—` 는 **정의상 기준을 가질 수 없다.**
> 화면은 글리프가 아니라 **필드의 존재**로 두 상태를 가른다.

부수 효과 셋:
1. **화면이 계약을 검사한다** — 기준 없는 계산된 값이 오면 `계약 위반` 으로 렌더링한다. 지표를 계산하지 않고 필수 필드의 존재만 보므로 `DB-012` 위반이 아니다
2. `kpi-definition-v1.md` R-4(모집단 명시) · R-6(제외 인원 병기) · R-2(전향/후향 구분)가 **모든 지표에 구조적으로 강제**된다 — KPI 계층뿐 아니라 수집 건전성 지표에도
3. `observed_count` 가 *"오늘 0행이라 통과했다"* 를 화면에서 드러낸다

## 검증 (실행함)
```
거부됨 ✅  ★ 계산된 값에 기준(basis)이 없다
거부됨 ✅  ★ 계산 불가인데 기준(basis)을 붙인다
거부됨 ✅  분모가 0인데 계산됨(ok)이라고 한다
```

## 기각한 대안
| 대안 | 사유 |
|---|---|
| `basis` 를 선택 필드로 | 선택이면 빠지고, 빠지면 판별자가 아니게 된다 |
| 기준을 지표 정의(정적 문서)에만 둔다 | 화면이 문서를 읽을 수 없다. `observed_count` 는 **실행마다 다르다** |
| `denominator` 만 둔다 | 합계·건수 지표에는 분모가 없다. 그러면 그 지표들이 판별에서 빠진다 |
| 계산 불가에도 `basis` 를 허용 | 판별자가 사라진다. 근거 수치는 `reason_detail` 이 나른다 |
