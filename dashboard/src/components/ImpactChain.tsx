/**
 * The gap -> impact chain: what a single missing field takes down with it.
 *
 * ★ The adjacency comes from the artifact (`blocks_metrics` on a field or schema gap,
 *   `blocked_by`/`blocks` on a metric). The screen never infers it — working out which
 *   metric depends on which is a derivation, and doing it here would create a second
 *   dependency graph that disagrees with the published one (DB-012).
 *
 * ★ The [P1]/[G1] badge is the reason this component exists. "unit_cost is missing" is
 *   a field-level nuisance; "unit_cost is missing, therefore the Primary metric cannot
 *   exist" is the finding. Without the role badge the chain reads as trivia.
 *
 * Two hops maximum — three or more stop being read. Anything deeper is a link.
 */
import type { ReasonCode } from "@/lib/artifacts/types";
import { actionFor } from "@/lib/format/metric";
import { REASON_LABEL } from "@/lib/format/state";
import { StateChip } from "./StateChip";

export interface ImpactLink {
  /** Metric names this gap blocks, in publish order. */
  metrics: string[];
  /** Roles of those metrics, when the artifact reports them. */
  roles?: Record<string, "none" | "primary" | "guardrail" | "secondary">;
  outcome: string;
}

export function ImpactChain({
  origin,
  reasonCode,
  detail,
  hops,
}: {
  /** What is missing: a field name, a schema gap, or an upstream metric. */
  origin: string;
  reasonCode: ReasonCode | undefined;
  detail?: string;
  hops: ImpactLink[];
}) {
  // Only the first two hops are drawn; the rest are acknowledged, not hidden.
  const shown = hops.slice(0, 2);
  const remaining = hops.length - shown.length;

  return (
    <div className="flex flex-col gap-xs rounded-lg border border-border p-base">
      <div className="flex flex-wrap items-center justify-between gap-sm">
        <div className="flex flex-wrap items-center gap-xs">
          <StateChip
            state={reasonCode === "BLOCKED" ? "env_blocked" : "gap"}
            label={`${origin} · ${reasonCode === undefined ? "사유 미표기" : REASON_LABEL[reasonCode]}`}
            reasonCode={reasonCode}
          />
        </div>
        {/* V-8 — never blank. "조치 미정" is written out when nothing is known. */}
        <span className="text-caption text-text-secondary">{actionFor(reasonCode)}</span>
      </div>

      {detail === undefined ? null : (
        <p className="text-caption text-text-secondary">{detail}</p>
      )}

      <ul className="flex flex-col gap-xs">
        {shown.map((hop, depth) => (
          <li key={depth} className="flex flex-wrap items-baseline gap-xs text-body-sm">
            <span aria-hidden="true" className="text-text-secondary">
              →
            </span>
            <span className="text-text">
              {hop.metrics.map((metric) => (
                <span key={metric} className="mr-xs">
                  {metric}
                  <RoleBadge role={hop.roles === undefined ? undefined : hop.roles[metric]} />
                </span>
              ))}
            </span>
            <span className="text-caption text-text-secondary">{hop.outcome}</span>
          </li>
        ))}
      </ul>

      {remaining > 0 ? (
        <p className="text-caption text-text-secondary">
          → 이하 {String(remaining)}단계는 /kpi 에서 확인합니다
        </p>
      ) : null}
    </div>
  );
}

/** [P1] / [G1]. Outline badge, required whenever the metric carries that role. */
export function RoleBadge({ role }: { role?: "none" | "primary" | "guardrail" | "secondary" }) {
  if (role === undefined || role === "none" || role === "secondary") return null;
  const [text, spoken] =
    role === "primary" ? ["P1", "Primary 지표"] : ["G1", "Guardrail 지표"];
  return (
    <span
      className="ml-xs inline-flex items-center rounded-sm border border-solid border-(--obs-impact-border) px-xs text-caption text-(--obs-impact-ink)"
      aria-label={spoken}
    >
      <span aria-hidden="true">{text}</span>
    </span>
  );
}
