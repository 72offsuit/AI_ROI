/**
 * Number display for the sprint-v0 result screens (issue 147).
 *
 * ★ Documented exception to DG-3 ("the screen does not format numbers"). The measurement
 *   contract hands the dashboard pre-formatted strings; the sprint files do not — they
 *   carry raw numbers and have no schema yet. Formatting is therefore done here, in one
 *   file, with a pinned locale (`ko-KR`) and fixed fraction digits so that the output
 *   does not vary by machine. Nothing here derives a new metric: no sums, ratios or
 *   classifications. Remove this file once the sprint files gain `*_formatted` fields.
 *
 * ★ Every function returns `null` for anything that is not a finite number, and the
 *   caller renders `null` as "계산 불가" (see components/sprint/Value.tsx). A `0` stays
 *   `0` — it is an honest value. There is deliberately no default argument that turns
 *   an absence into a number.
 */

const cache = new Map<string, Intl.NumberFormat>();

function formatter(key: string, options: Intl.NumberFormatOptions): Intl.NumberFormat {
  let f = cache.get(key);
  if (f === undefined) {
    f = new Intl.NumberFormat("ko-KR", options);
    cache.set(key, f);
  }
  return f;
}

export function isNum(value: unknown): value is number {
  return typeof value === "number" && Number.isFinite(value);
}

/** Fixed-digit decimal, e.g. AUC `0.803`. */
export function fmtDec(value: unknown, digits = 3): string | null {
  if (!isNum(value)) return null;
  return formatter(`d${digits}`, {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  }).format(value);
}

/** Signed fixed-digit decimal, e.g. ATE `+0.021`. */
export function fmtSigned(value: unknown, digits = 3): string | null {
  if (!isNum(value)) return null;
  return formatter(`s${digits}`, {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
    signDisplay: "exceptZero",
  }).format(value);
}

/** Up to `digits` fraction digits, trailing zeros dropped, e.g. `4.8`, `38,500`. */
export function fmtAuto(value: unknown, digits = 3): string | null {
  if (!isNum(value)) return null;
  return formatter(`a${digits}`, { maximumFractionDigits: digits }).format(value);
}

/** Grouped integer, e.g. `20,000`. */
export function fmtInt(value: unknown): string | null {
  if (!isNum(value)) return null;
  return formatter("i", { maximumFractionDigits: 0 }).format(value);
}

/** A fraction shown as a percentage, e.g. `0.284` → `28.4%`. */
export function fmtPct(value: unknown, digits = 1): string | null {
  if (!isNum(value)) return null;
  return formatter(`p${digits}`, {
    style: "percent",
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  }).format(value);
}

/** Signed percentage point difference of two fractions already given by the file. */
export function fmtPctSigned(value: unknown, digits = 1): string | null {
  if (!isNum(value)) return null;
  return formatter(`ps${digits}`, {
    style: "percent",
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
    signDisplay: "exceptZero",
  }).format(value);
}

/** Difference of two rates in percentage points, e.g. `-0.021` → `-2.1%p`. */
export function fmtPp(value: unknown, digits = 1): string | null {
  const s = fmtPctSigned(value, digits);
  return s === null ? null : s.replace("%", "%p");
}

/** Korean won, grouped, e.g. `₩1,824,000,000`. */
export function fmtKrw(value: unknown, signed = false): string | null {
  if (!isNum(value)) return null;
  return formatter(signed ? "ks" : "k", {
    style: "currency",
    currency: "KRW",
    maximumFractionDigits: 0,
    signDisplay: signed ? "exceptZero" : "auto",
  }).format(value);
}

/** p-value. Below 0.001 the digits stop carrying meaning, so the bound is shown. */
export function fmtP(value: unknown): string | null {
  if (!isNum(value)) return null;
  if (value < 0.001) return "< 0.001";
  return fmtDec(value, 3);
}

/** `[lo, hi]` → `[a, b]`. Either end missing makes the interval unknown as a whole. */
export function fmtInterval(
  ci: unknown,
  each: (v: unknown) => string | null,
): string | null {
  if (!Array.isArray(ci) || ci.length !== 2) return null;
  const lo = each(ci[0]);
  const hi = each(ci[1]);
  if (lo === null || hi === null) return null;
  return `[${lo}, ${hi}]`;
}

/** `{mean, std}` or a bare number, as found in churn_eval. */
export function meanStd(value: unknown): { mean: number | null; std: number | null } {
  if (isNum(value)) return { mean: value, std: null };
  if (typeof value === "object" && value !== null && !Array.isArray(value)) {
    const record = value as Record<string, unknown>;
    return {
      mean: isNum(record.mean) ? record.mean : null,
      std: isNum(record.std) ? record.std : null,
    };
  }
  return { mean: null, std: null };
}

/** `mean ± std`, or just `mean` when the file gave no spread. */
export function fmtMeanStd(value: unknown, digits = 3): string | null {
  const { mean, std } = meanStd(value);
  const m = fmtDec(mean, digits);
  if (m === null) return null;
  const s = fmtDec(std, digits);
  return s === null ? m : `${m} ± ${s}`;
}

/** Plain seconds with one decimal, e.g. `41.2초`. */
export function fmtSeconds(value: unknown): string | null {
  const s = fmtDec(value, 1);
  return s === null ? null : `${s}초`;
}
