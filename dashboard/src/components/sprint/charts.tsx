/**
 * Hand-written SVG charts for the sprint result screens. No chart library is installed
 * and none is added (issue 147: no new npm packages during the sprint).
 *
 * Rules carried over from dashboard/AGENTS.md:
 *   - DG-19: a `null` is never plotted as 0 and never bridged. A bar with no value is
 *     drawn as the words "계산 불가" in its row; a curve breaks at a missing point.
 *   - DG-17: no colour literal. Fills are `--ds-*` variables from Plan/DESIGN.md.
 *     Proposed = `primary`, baseline = `text-secondary` — and the row label always
 *     says which, so identity is never colour alone.
 *   - Every chart sits next to a table carrying the same numbers; the chart is a
 *     reading aid, not the only place a value exists. Hover `<title>` repeats the
 *     row's number but nothing is ONLY in the hover (DG-14).
 *
 * Scale extents are derived from the values purely to place marks. No derived number
 * is ever printed.
 */
import { isNum } from "@/lib/format/sprint";
import { UNCOMPUTABLE_TEXT } from "./Value";

const INK = "var(--ds-colors-text)";
const INK_2 = "var(--ds-colors-text-secondary)";
const GRID = "var(--ds-colors-border)";
const PRIMARY = "var(--ds-colors-primary)";
const ABSENT = "var(--obs-absent-ink)";

const W = 760;
const LABEL_W = 230;
const VALUE_W = 120;
const PAD = 12;
const ROW_H = 30;
const BAR_H = 14;

export interface BarRow {
  key: string;
  label: string;
  /** Proposed model / the series under test. */
  emphasis: boolean;
  value: number | null;
  /** Half-width of the error bar (e.g. CV std). */
  err?: number | null;
  /** Already formatted text for the value column; `null` → "계산 불가". */
  display: string | null;
}

function extent(values: number[], include: number[]): [number, number] {
  const all = values.concat(include);
  let lo = Math.min(...all);
  let hi = Math.max(...all);
  if (lo === hi) {
    lo -= 1;
    hi += 1;
  }
  const pad = (hi - lo) * 0.06;
  return [lo < 0 ? lo - pad : lo, hi + pad];
}

/**
 * Horizontal bars anchored at zero, with optional ± error whiskers.
 * `domain` fixes the scale (e.g. `[0, 1]` for AUC); otherwise it is fitted to the data
 * and always includes zero so that sign is readable.
 */
export function BarChart({
  rows,
  domain,
  ariaLabel,
}: {
  rows: BarRow[];
  domain?: [number, number];
  ariaLabel: string;
}) {
  const present: number[] = [];
  for (const r of rows) {
    if (!isNum(r.value)) continue;
    const e = isNum(r.err) ? r.err : 0;
    present.push(r.value - e, r.value + e);
  }
  const [d0, d1] = domain !== undefined ? domain : extent(present.length > 0 ? present : [0, 1], [0]);
  const plotX = LABEL_W + PAD;
  const plotW = W - LABEL_W - VALUE_W - PAD * 2;
  const x = (v: number) => plotX + ((Math.min(Math.max(v, d0), d1) - d0) / (d1 - d0)) * plotW;
  const zero = x(Math.min(Math.max(0, d0), d1));
  const H = rows.length * ROW_H + 24;

  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="w-full max-w-[760px]" role="img" aria-label={ariaLabel}>
      {/* recessive axis: zero line + domain ends */}
      <line x1={zero} x2={zero} y1={0} y2={rows.length * ROW_H} stroke={GRID} strokeWidth={1} />
      <text x={plotX} y={H - 6} fontSize={11} fill={INK_2}>
        {d0 === 0 ? "0" : ""}
      </text>
      {rows.map((r, i) => {
        const cy = i * ROW_H + ROW_H / 2;
        const has = isNum(r.value);
        return (
          <g key={r.key}>
            <title>{`${r.label}: ${r.display === null ? UNCOMPUTABLE_TEXT : r.display}`}</title>
            <text x={LABEL_W} y={cy + 4} fontSize={13} textAnchor="end" fill={INK}>
              {r.label}
            </text>
            {has ? (
              <>
                <rect
                  x={Math.min(zero, x(r.value as number))}
                  y={cy - BAR_H / 2}
                  width={Math.max(1, Math.abs(x(r.value as number) - zero))}
                  height={BAR_H}
                  rx={4}
                  style={{ fill: r.emphasis ? PRIMARY : INK_2 }}
                />
                {isNum(r.err) ? (
                  <g stroke={INK} strokeWidth={1.5}>
                    <line x1={x((r.value as number) - r.err)} x2={x((r.value as number) + r.err)} y1={cy} y2={cy} />
                    <line x1={x((r.value as number) - r.err)} x2={x((r.value as number) - r.err)} y1={cy - 5} y2={cy + 5} />
                    <line x1={x((r.value as number) + r.err)} x2={x((r.value as number) + r.err)} y1={cy - 5} y2={cy + 5} />
                  </g>
                ) : null}
              </>
            ) : (
              <text x={plotX + 4} y={cy + 4} fontSize={13} fill={ABSENT}>
                {UNCOMPUTABLE_TEXT}
              </text>
            )}
            <text
              x={W - PAD}
              y={cy + 4}
              fontSize={13}
              textAnchor="end"
              style={{ fill: r.display === null ? ABSENT : INK, fontVariantNumeric: "tabular-nums" }}
            >
              {r.display === null ? UNCOMPUTABLE_TEXT : r.display}
            </text>
          </g>
        );
      })}
    </svg>
  );
}

export interface IntervalRow {
  key: string;
  label: string;
  value: number | null;
  lo: number | null;
  hi: number | null;
  display: string | null;
}

/** Point estimate + 95% interval around a zero reference (ATE, A/B differences). */
export function IntervalChart({ rows, ariaLabel }: { rows: IntervalRow[]; ariaLabel: string }) {
  const present: number[] = [];
  for (const r of rows) {
    for (const v of [r.value, r.lo, r.hi]) if (isNum(v)) present.push(v);
  }
  const [d0, d1] = extent(present.length > 0 ? present : [-1, 1], [0]);
  const plotX = LABEL_W + PAD;
  const plotW = W - LABEL_W - VALUE_W - PAD * 2 - 60;
  const x = (v: number) => plotX + ((v - d0) / (d1 - d0)) * plotW;
  const zero = x(0);
  const H = rows.length * ROW_H + 24;

  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="w-full max-w-[760px]" role="img" aria-label={ariaLabel}>
      <line x1={zero} x2={zero} y1={0} y2={rows.length * ROW_H} stroke={INK_2} strokeWidth={1} strokeDasharray="3 3" />
      <text x={zero} y={H - 6} fontSize={11} textAnchor="middle" fill={INK_2}>
        0 (효과 없음)
      </text>
      {rows.map((r, i) => {
        const cy = i * ROW_H + ROW_H / 2;
        const ok = isNum(r.value);
        const ci = isNum(r.lo) && isNum(r.hi);
        return (
          <g key={r.key}>
            <title>{`${r.label}: ${r.display === null ? UNCOMPUTABLE_TEXT : r.display}`}</title>
            <text x={LABEL_W} y={cy + 4} fontSize={13} textAnchor="end" fill={INK}>
              {r.label}
            </text>
            {ci ? (
              <g stroke={PRIMARY} strokeWidth={2}>
                <line x1={x(r.lo as number)} x2={x(r.hi as number)} y1={cy} y2={cy} />
                <line x1={x(r.lo as number)} x2={x(r.lo as number)} y1={cy - 6} y2={cy + 6} />
                <line x1={x(r.hi as number)} x2={x(r.hi as number)} y1={cy - 6} y2={cy + 6} />
              </g>
            ) : null}
            {ok ? (
              <circle cx={x(r.value as number)} cy={cy} r={5} style={{ fill: PRIMARY, stroke: "var(--ds-colors-surface)", strokeWidth: 2 }} />
            ) : (
              <text x={plotX + 4} y={cy + 4} fontSize={13} fill={ABSENT}>
                {UNCOMPUTABLE_TEXT}
              </text>
            )}
            <text
              x={W - PAD}
              y={cy + 4}
              fontSize={13}
              textAnchor="end"
              style={{ fill: r.display === null ? ABSENT : INK, fontVariantNumeric: "tabular-nums" }}
            >
              {r.display === null ? UNCOMPUTABLE_TEXT : r.display}
            </text>
          </g>
        );
      })}
    </svg>
  );
}

export interface CurveSeries {
  key: string;
  label: string;
  emphasis: boolean;
  points: [number | null, number | null][];
}

const DASHES = ["", "7 4", "2 3", "10 3 2 3"];

/**
 * Qini curves. Points are drawn exactly as given; a point with a missing coordinate
 * breaks the line instead of being bridged (DG-19). The dotted diagonal joins the
 * origin to the first series' last point — the conventional "random targeting" guide —
 * and is labelled as such.
 */
export function CurveChart({
  series,
  ariaLabel,
  xLabel,
  yLabel,
}: {
  series: CurveSeries[];
  ariaLabel: string;
  xLabel: string;
  yLabel: string;
}) {
  const xs: number[] = [];
  const ys: number[] = [];
  for (const s of series) {
    for (const [px, py] of s.points) {
      if (isNum(px) && isNum(py)) {
        xs.push(px);
        ys.push(py);
      }
    }
  }
  const CW = 760;
  const CH = 360;
  const L = 64;
  const R = 16;
  const T = 12;
  const B = 44;
  const [x0, x1] = xs.length > 0 ? [Math.min(0, ...xs), Math.max(...xs)] : [0, 1];
  const [y0, y1] = ys.length > 0 ? extent(ys, [0]) : [0, 1];
  const sx = (v: number) => L + ((v - x0) / (x1 - x0 || 1)) * (CW - L - R);
  const sy = (v: number) => CH - B - ((v - y0) / (y1 - y0 || 1)) * (CH - T - B);

  const paths = (pts: [number | null, number | null][]) => {
    const segs: string[] = [];
    let cur = "";
    for (const [px, py] of pts) {
      if (isNum(px) && isNum(py)) {
        cur += `${cur === "" ? "M" : "L"}${sx(px)},${sy(py)} `;
      } else if (cur !== "") {
        segs.push(cur);
        cur = "";
      }
    }
    if (cur !== "") segs.push(cur);
    return segs;
  };

  const first = series.find((s) => s.points.some(([px, py]) => isNum(px) && isNum(py)));
  const last = first?.points.filter(([px, py]) => isNum(px) && isNum(py)).at(-1);

  let baselineIdx = 0;
  let proposedIdx = 0;
  const styled = series.map((s) => {
    const dash = s.emphasis ? DASHES[proposedIdx++ % DASHES.length] : DASHES[baselineIdx++ % DASHES.length];
    return { ...s, dash, color: s.emphasis ? PRIMARY : INK_2 };
  });

  return (
    <div className="flex flex-col gap-sm">
      <ul className="flex flex-wrap gap-x-base gap-y-xs text-caption text-text" aria-label="범례">
        {styled.map((s) => (
          <li key={s.key} className="inline-flex items-center gap-xs">
            <svg width={28} height={10} aria-hidden="true">
              <line x1={0} x2={28} y1={5} y2={5} style={{ stroke: s.color }} strokeWidth={2.5} strokeDasharray={s.dash} />
            </svg>
            {s.label} ({s.emphasis ? "제안" : "기준선"})
          </li>
        ))}
        {last === undefined ? null : (
          <li className="inline-flex items-center gap-xs">
            <svg width={28} height={10} aria-hidden="true">
              <line x1={0} x2={28} y1={5} y2={5} stroke={GRID} strokeWidth={2} strokeDasharray="1 3" />
            </svg>
            무작위 타기팅 안내선 (원점 ↔ 끝점)
          </li>
        )}
      </ul>
      <svg viewBox={`0 0 ${CW} ${CH}`} className="w-full max-w-[760px]" role="img" aria-label={ariaLabel}>
        <line x1={L} x2={CW - R} y1={sy(0)} y2={sy(0)} stroke={GRID} />
        <line x1={L} x2={L} y1={T} y2={CH - B} stroke={GRID} />
        <text x={(L + CW - R) / 2} y={CH - 8} fontSize={12} textAnchor="middle" fill={INK_2}>
          {xLabel}
        </text>
        <text x={14} y={(T + CH - B) / 2} fontSize={12} textAnchor="middle" fill={INK_2} transform={`rotate(-90 14 ${(T + CH - B) / 2})`}>
          {yLabel}
        </text>
        <text x={L - 6} y={sy(0) + 4} fontSize={11} textAnchor="end" fill={INK_2}>
          0
        </text>
        <text x={L} y={CH - B + 16} fontSize={11} textAnchor="middle" fill={INK_2}>
          {x0 === 0 ? "0" : ""}
        </text>
        {last === undefined ? null : (
          <line
            x1={sx(0)}
            y1={sy(0)}
            x2={sx(last[0] as number)}
            y2={sy(last[1] as number)}
            stroke={GRID}
            strokeWidth={2}
            strokeDasharray="1 3"
          />
        )}
        {styled.map((s) => (
          <g key={s.key}>
            <title>{s.label}</title>
            {paths(s.points).map((d, i) => (
              <path key={i} d={d} fill="none" style={{ stroke: s.color }} strokeWidth={2} strokeDasharray={s.dash} />
            ))}
          </g>
        ))}
      </svg>
    </div>
  );
}

/** Two-entry legend for bar charts that mix baseline and proposed rows. */
export function KindLegend() {
  return (
    <ul className="flex flex-wrap gap-x-base gap-y-xs text-caption text-text" aria-label="범례">
      <li className="inline-flex items-center gap-xs">
        <span aria-hidden="true" className="inline-block h-[10px] w-[18px] rounded-sm" style={{ background: PRIMARY }} />
        제안 모델
      </li>
      <li className="inline-flex items-center gap-xs">
        <span aria-hidden="true" className="inline-block h-[10px] w-[18px] rounded-sm" style={{ background: INK_2 }} />
        기준선
      </li>
      <li className="inline-flex items-center gap-xs">
        <svg width={18} height={10} aria-hidden="true">
          <g stroke={INK} strokeWidth={1.5}>
            <line x1={1} x2={17} y1={5} y2={5} />
            <line x1={1} x2={1} y1={1} y2={9} />
            <line x1={17} x2={17} y1={1} y2={9} />
          </g>
        </svg>
        ± 표준편차 (교차검증)
      </li>
    </ul>
  );
}
