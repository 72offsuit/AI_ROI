/**
 * Commerce on the left, simulator on the right — always, in that order.
 *
 * ★ Source is conveyed by position and a glyph, not by colour, and the order never
 *   changes under sorting, filtering or stacking. MEA-002 forbids mixing sources
 *   because treatment/control assignment stops holding; a reader who has to check
 *   which column is which each time will eventually not check.
 *
 * ★ An empty column keeps its full width (S-6). Collapsing the commerce column when
 *   it has no data makes the project look like a simulator-only system, which is the
 *   opposite of the true state.
 *
 * Stacks vertically under 1024px, commerce still first.
 */
import type { SourceLink, SourceSplit } from "@/lib/artifacts/types";
import { MetricCell } from "./MetricCell";
import { StateChip } from "./StateChip";

/** Fixed 1:1 columns. Width never tracks row counts. */
export function SourceColumns({
  name,
  split,
  scale = "metric",
  renderCommerce,
  renderSimulator,
}: {
  name: string;
  split?: SourceSplit;
  scale?: "metric" | "table-number";
  renderCommerce?: React.ReactNode;
  renderSimulator?: React.ReactNode;
}) {
  return (
    <div className="grid grid-cols-1 gap-base lg:grid-cols-2">
      <section aria-label={`${name} · 커머스`} className="rounded-lg border border-border p-base">
        <SourceBadge source="commerce" />
        <div className="mt-sm">
          {renderCommerce !== undefined ? (
            renderCommerce
          ) : split === undefined ? null : (
            <MetricCell name={name} metric={split.by_source.commerce} scale={scale} hideName />
          )}
        </div>
      </section>
      <section aria-label={`${name} · 시뮬레이터`} className="rounded-lg border border-border p-base">
        <SourceBadge source="simulator" />
        <div className="mt-sm">
          {renderSimulator !== undefined ? (
            renderSimulator
          ) : split === undefined ? null : (
            <MetricCell name={name} metric={split.by_source.simulator} scale={scale} hideName />
          )}
        </div>
      </section>
    </div>
  );
}

/** Glyph + words, no background — a source is not a status (S-2). */
export function SourceBadge({ source }: { source: "commerce" | "simulator" }) {
  const [glyph, text] =
    source === "commerce" ? ["◼", "커머스 실측"] : ["◇", "시뮬레이터 생성"];
  return (
    <span className="inline-flex items-center gap-xs text-label-md text-(--obs-source-ink)" aria-label={text}>
      <span aria-hidden="true">{glyph}</span>
      <span aria-hidden="true">{text}</span>
    </span>
  );
}

/**
 * Connection state — the contract has exactly two values and this component adds none.
 *
 * ★ `connected` gets no chip. It covers both "receiving right now" and "received
 *   once and then stopped", and two values cannot tell those apart. A ✓ would be read
 *   as healthy and a ⚠ as stopped, and the screen knows neither. The facts (first
 *   seen, last seen, count) are printed instead, and `staleness` arrives as
 *   not_run + PARAM_UNCONFIRMED — "we cannot judge this" is itself the value.
 */
export function ConnectionState({ link }: { link: SourceLink }) {
  const never = link.link_state === "never_connected";
  return (
    <div className="flex flex-col gap-xs">
      {never ? <StateChip state="unconnected" label="아직 관측되지 않음" /> : null}
      <dl className="text-caption text-text-secondary">
        <div className="flex gap-xs">
          <dt>첫 수신</dt>
          <dd>{link.first_event_at === null ? "—" : link.first_event_at}</dd>
        </div>
        <div className="flex gap-xs">
          <dt>마지막 수신</dt>
          <dd>{link.last_event_at === null ? "—" : link.last_event_at}</dd>
        </div>
        <div className="flex gap-xs">
          <dt>건수</dt>
          {/* event_count is an integer the publisher counted; printed, never derived. */}
          <dd>{String(link.event_count)}건</dd>
        </div>
      </dl>
      <div className="mt-xs">
        <MetricCell name="정지 판정" metric={link.staleness} scale="table-number" />
      </div>
    </div>
  );
}

/** Required footnote: how source is derived, since no explicit flag exists (US-12). */
export function SourceFootnote() {
  return (
    <p className="text-caption text-text-secondary">
      출처는 <code>simulator_version</code> · <code>random_seed</code> 의 null 여부에서 파생됩니다
      (별도 플래그 없음). 대시보드는 출처를 재분류하지 않고 게시물의 <code>by_source</code> 를 그대로
      씁니다.
    </p>
  );
}
