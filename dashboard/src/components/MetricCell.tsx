/**
 * One metric. Every number on every screen goes through this component.
 *
 * Four fixed slots, in this order, always all present:
 *   1. name    — text-label-md
 *   2. value   — text-metric (card) or text-table-number (dense table)
 *   3. status  — chip + reason sentence + raw reason code, always inline
 *   4. evidence— basis / impact / action, text-caption
 *
 * ★ The value slot uses the SAME typography token whether it holds a number or an
 *   em dash. That symmetry is the argument the screen is making: an absence rendered
 *   smaller or greyer than a value tells the reader the absence matters less, which
 *   is the polite version of filling it with zero. The em dash is 2rem/700 and
 *   visually heavy on purpose.
 *
 * ★ Colour for the absent value is text-secondary (7.82:1 on white), never
 *   text-muted (5.33:1). DESIGN.md scopes text-muted to "supporting badges, dates"
 *   — a missing measurement is not supporting information.
 *
 * ★ Reasons are never behind hover or a disclosure widget. US-11/US-13 require the
 *   state to be provable by screenshot, and a hover state does not survive a
 *   screenshot; it is also not equivalent on touch or keyboard.
 */
import type { MetricValue } from "@/lib/artifacts/types";
import { actionFor, formatMetricValue, type MetricDisplay } from "@/lib/format/metric";
import { REASON_LABEL, STATE_LABEL, type VisualState } from "@/lib/format/state";
import { DerivedChip, LimitChip, StateChip } from "./StateChip";

/** States that owe the reader an action line; blank would read as "nothing to do" (V-8). */
const NEEDS_ACTION = new Set(["gap", "env_blocked", "not_run", "violation"]);

/**
 * Chip prefix per state. `provisional` must NOT say "계산 불가": it HAS a value, it is
 * the parameter behind it that is unconfirmed. Labelling a computed number
 * "uncomputable" is the mirror image of the zero-fill error — it misreports a value as
 * an absence — and it makes the reader distrust a number they are allowed to use.
 */
const STATE_PREFIX: Partial<Record<VisualState, string>> = {
  provisional: "잠정값",
  env_blocked: "실행 불가",
  not_run: "미실행",
  planned: "계산 불가",
  unconnected: "계산 불가",
  gap: "계산 불가",
};

const VALUE_INK: Record<"present" | "absent", string> = {
  present: "text-(--obs-value-ink)",
  absent: "text-(--obs-absent-ink)",
};

export function MetricCell({
  name,
  metric,
  scale = "metric",
  hideName = false,
}: {
  name: string;
  metric: MetricValue;
  /** `table-number` for dense tables; both keep value and em dash at one size. */
  scale?: "metric" | "table-number";
  /** Table rows carry the metric name in their own header cell. */
  hideName?: boolean;
}) {
  return (
    <MetricCellView
      name={name}
      display={formatMetricValue(metric)}
      scale={scale}
      hideName={hideName}
    />
  );
}

/**
 * Rendering half, separated so screens that build a display model by hand — the
 * self-check rows that have no metric_value behind them — reuse the exact same layout
 * rather than growing a parallel one that could drift from these rules.
 */
export function MetricCellView({
  name,
  display,
  scale = "metric",
  hideName = false,
}: {
  name: string;
  display: MetricDisplay;
  scale?: "metric" | "table-number";
  hideName?: boolean;
}) {
  const valueType = scale === "metric" ? "text-metric" : "text-table-number";
  const ink = display.isPublishedValue ? VALUE_INK.present : VALUE_INK.absent;
  const action = NEEDS_ACTION.has(display.state) ? actionFor(display.reasonCode) : undefined;

  return (
    <div className="flex flex-col gap-(--obs-cell-gap)">
      {hideName ? null : <div className="text-label-md text-text">{name}</div>}

      {/* Slot 2 — one typography token for both a value and its absence (V-1). */}
      <div className={`${valueType} ${ink}`}>{display.valueText}</div>

      {/* Slot 3 — status is always visible, never a tooltip (V-9). */}
      {display.state === "available" && display.violations.length === 0 ? null : (
        <div className="flex flex-wrap items-center gap-xs">
          {display.state === "available" ? null : (
            <StateChip
              state={display.state}
              label={
                display.reasonCode === undefined
                  ? undefined
                  : `${
                      STATE_PREFIX[display.state] === undefined
                        ? STATE_LABEL[display.state]
                        : STATE_PREFIX[display.state]
                    } · ${REASON_LABEL[display.reasonCode]}`
              }
              reasonCode={display.reasonCode}
            />
          )}
          {display.derived ? <DerivedChip derivation={display.derivation} /> : null}
          {display.limitNote === undefined ? null : <LimitChip note={display.limitNote} />}
          {display.violations.map((violation) => (
            <StateChip key={violation} state="violation" label={`계약 위반 · ${violation}`} />
          ))}
        </div>
      )}

      {display.reasonDetail === undefined ? null : (
        <p className="text-caption text-text-secondary">{display.reasonDetail}</p>
      )}

      {/* Slot 4 — evidence. A computed value without a basis has already been flagged
          above; here the basis is printed whenever the publisher supplied one (V-2). */}
      {display.basisText === undefined ? null : (
        <p className="text-caption text-(--obs-basis-ink)">{display.basisText}</p>
      )}

      {display.paramsUsed === undefined ? null : (
        <p className="text-caption text-text-secondary">
          사용한 파라미터:{" "}
          {display.paramsUsed.map(([key, value]) => `${key}=${value}`).join(" · ")}
        </p>
      )}

      {display.blockedBy.length === 0 ? null : (
        <ul className="text-caption text-text-secondary">
          {display.blockedBy.map((blocker) => (
            <li key={`${blocker.kind}:${blocker.ref}`}>
              원인: {blocker.ref} ({blocker.kind}) · {blocker.reasonCode}
            </li>
          ))}
        </ul>
      )}

      {action === undefined ? null : (
        <p className="text-caption text-text-secondary">{action}</p>
      )}
    </div>
  );
}
