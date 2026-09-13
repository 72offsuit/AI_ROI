/**
 * Daily collection volume, drawn as bars with plain CSS — no chart library.
 *
 * ★ Why bars and not a line: a line has to span the gaps, and spanning a gap draws a
 *   value that was never observed. Breaking a line at nulls means fighting whichever
 *   library is in use, and most of them plot null as zero by default. Bars have no
 *   such failure mode — a day with no bar is visibly a day with no bar.
 *
 * ★ Why no library at all: every charting library reintroduces the null-to-zero
 *   problem at its own API boundary, and this view needs exactly one shape. The
 *   widths below are percentages of the largest published day; that is a layout
 *   proportion, not a derived metric, and no number produced here is ever displayed.
 *
 * ★ A zero-row day is NOT filtered out. `filter(d => d.value > 0)` would silently
 *   delete precisely the rows this screen exists to show. Zero days render as a 1px
 *   dotted empty slot on the baseline.
 *
 * ★ A zero-row day is never labelled "no activity". The data cannot separate an
 *   outage from genuine inactivity — that needs a heartbeat record the sink does not
 *   have — so the screen says it cannot tell. Asserting "no activity" would be the
 *   same class of error as filling a gap with zero.
 */
import type { MetricValue, Partition } from "@/lib/artifacts/types";
import { formatMetricValue } from "@/lib/format/metric";

const UNDECIDABLE = "수집 0건 · 활동 없음과 수집 중단을 현재 데이터로 구분할 수 없습니다";

/** Row count for one source on one day, or null when it was not a computed value. */
function publishedCount(metric: MetricValue): number | null {
  // Branch on status, never on the truthiness of value: 0 is a real measurement.
  if (metric.status !== "ok" && metric.status !== "unconfirmed") return null;
  return typeof metric.value === "number" ? metric.value : null;
}

export function IngestionTimeline({ partitions }: { partitions: Partition[] }) {
  if (partitions.length === 0) {
    // No axis, no empty slots, no illustration — just the fact and its basis.
    return (
      <div className="rounded-lg border border-border p-base">
        <p className="text-metric text-(--obs-absent-ink)">—</p>
        <p className="mt-xs text-caption text-(--obs-basis-ink)">기준: 파티션 0개</p>
        <p className="mt-xs text-caption text-text-secondary">
          수집된 날짜가 없습니다. 빈 상태 화면으로 대체하지 않고 사실을 그대로 적습니다.
        </p>
      </div>
    );
  }

  // Scale reference: the largest published count across both sources. Used only to
  // size bars; it is never rendered as a number.
  let scale = 0;
  for (const partition of partitions) {
    for (const source of ["commerce", "simulator"] as const) {
      const count = publishedCount(partition.rows.by_source[source]);
      if (count !== null && count > scale) scale = count;
    }
  }

  return (
    <div className="flex flex-col gap-lg">
      {(["commerce", "simulator"] as const).map((source) => (
        <SourceRow key={source} source={source} partitions={partitions} scale={scale} />
      ))}
      {/* DESIGN.md requires charts to be accompanied by labels and a data table, so
          the same numbers are always reachable without reading bar lengths. */}
      <DataTable partitions={partitions} />
    </div>
  );
}

function SourceRow({
  source,
  partitions,
  scale,
}: {
  source: "commerce" | "simulator";
  partitions: Partition[];
  scale: number;
}) {
  const title = source === "commerce" ? "◼ 커머스 실측" : "◇ 시뮬레이터 생성";
  return (
    <section aria-label={`${title} 일자별 수집량`}>
      <p className="text-label-md text-(--obs-source-ink)">{title}</p>
      <ul className="mt-sm flex flex-col gap-xs">
        {partitions.map((partition) => {
          const metric = partition.rows.by_source[source];
          const count = publishedCount(metric);
          const display = formatMetricValue(metric);
          // A bar only exists for a published count above zero; zero and "no value"
          // both render as the dotted empty slot, distinguished by the label beside it.
          const widthPercent = count !== null && scale > 0 ? (count / scale) * 100 : 0;

          return (
            <li key={partition.date} className="flex items-center gap-sm">
              <span className="w-[6.5rem] shrink-0 text-caption text-text-secondary">
                {partition.date}
              </span>
              <span className="flex h-md min-w-0 flex-1 items-center border-b border-(--obs-chart-baseline-ink)">
                {widthPercent > 0 ? (
                  <span
                    className="h-sm bg-(--obs-chart-series)"
                    style={{ width: `${widthPercent}%` }}
                    aria-hidden="true"
                  />
                ) : (
                  <span
                    className="h-sm w-full border border-dashed border-(--obs-chart-gap-ink)"
                    aria-hidden="true"
                  />
                )}
              </span>
              <span className="w-[9rem] shrink-0 text-right text-table-number text-text">
                {display.valueText}
              </span>
            </li>
          );
        })}
      </ul>
    </section>
  );
}

function DataTable({ partitions }: { partitions: Partition[] }) {
  return (
    <div className="w-full overflow-x-auto">
      <table className="w-full min-w-[40rem] border-collapse text-body-sm">
        <caption className="text-caption text-text-secondary">
          일자별 수집량 — 차트와 같은 값
        </caption>
        <thead>
          <tr className="border-b border-border">
            <th scope="col" className="px-sm py-sm text-left text-label-md">날짜</th>
            <th scope="col" className="px-sm py-sm text-right text-label-md">◼ 커머스</th>
            <th scope="col" className="px-sm py-sm text-right text-label-md">◇ 시뮬레이터</th>
            <th scope="col" className="px-sm py-sm text-left text-label-md">비고</th>
          </tr>
        </thead>
        <tbody>
          {partitions.map((partition) => {
            const commerce = formatMetricValue(partition.rows.by_source.commerce);
            const simulator = formatMetricValue(partition.rows.by_source.simulator);
            return (
              <tr key={partition.date} className="border-b border-border">
                <td className="px-sm py-md">{partition.date}</td>
                <td className="px-sm py-md text-right text-table-number">{commerce.valueText}</td>
                <td className="px-sm py-md text-right text-table-number">{simulator.valueText}</td>
                <td className="px-sm py-md text-caption text-text-secondary">
                  {partition.present ? (
                    partition.in_observed_range ? "관측 구간 내" : "관측 구간 밖"
                  ) : (
                    UNDECIDABLE
                  )}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
