/**
 * V4 — KPI. This screen carries the proof the whole cycle is for.
 *
 * ★ The representative scene is pinned to the top: revenue next to
 *   contribution_profit, same card, same row, same width, same typography token. One
 *   has a value and a basis; the other has an em dash, a reason code and an action.
 *   The symmetry is the argument — if the absence were smaller or greyer the reader
 *   would conclude it mattered less, and that conclusion is the failure this project
 *   is trying to prevent.
 *
 * ★ Every metric the artifact publishes is rendered. The screen does not hold a
 *   canonical list of metric names: if it did, a metric the publisher dropped would
 *   vanish here too, and a vanished metric reads as a passing one. Layer sections are
 *   never collapsed, and the experiment layer prints all its rows — the shared reason
 *   is written once at the top of the block, but the rows stay open (gathering the
 *   prose is not the same as folding the rows).
 *
 * ★ No totals hero. Layers 1 and 2 are forbidden a `combined` key at schema level
 *   (R-7), so a single big number across both sources cannot be drawn honestly.
 */
import { loadKpiReport } from "@/lib/artifacts/read";
import { isSourceSplit, type KpiMetric, type KpiReport } from "@/lib/artifacts/types";
import { formatMetricValue } from "@/lib/format/metric";
import { ArtifactGate } from "@/components/ArtifactGate";
import { MetricCell } from "@/components/MetricCell";
import { NoticeBar } from "@/components/NoticeBar";
import { ProvenanceBar, RefreshLink } from "@/components/ProvenanceBar";
import { RoleBadge } from "@/components/ImpactChain";
import { SourceBadge, SourceFootnote } from "@/components/SourceColumns";
import { FixtureBadge, StateChip } from "@/components/StateChip";

export const dynamic = "force-dynamic";

/** Fixed display order. Never sorted by status — that would push gaps to the bottom. */
const LAYERS: { key: KpiMetric["layer"]; title: string; note?: string }[] = [
  { key: "collection_health", title: "계층 0 · 수집 건전성" },
  { key: "customer_kpi", title: "계층 1 · 고객 KPI", note: "출처를 합산하지 않습니다 (R-7)" },
  { key: "business_kpi", title: "계층 2 · 비즈니스 KPI", note: "출처를 합산하지 않습니다 (R-7)" },
  {
    key: "experiment",
    title: "실험 판정",
    note: "시뮬레이터 생성분만 사용하므로 출처 축이 없습니다 (MEA-002).",
  },
];

function isFixtureMode(): boolean {
  const flag = process.env.AIROI_FIXTURE_MODE;
  return typeof flag === "string" && flag.trim().length > 0 && flag.trim() !== "0";
}

export default async function KpiPage() {
  const result = await loadKpiReport();
  if (result.kind !== "ok") return <ArtifactGate result={result} />;
  const report = result.artifact;

  return (
    <div className="flex flex-col gap-lg">
      <header className="flex flex-wrap items-center justify-between gap-sm">
        <h1 className="text-headline-lg text-text">KPI</h1>
        <RefreshLink route="/kpi" />
      </header>

      <ProvenanceBar envelope={report} />
      <NoticeBar notices={report.notices} />

      <HeadlineScene report={report} />

      <Summary report={report} />

      {LAYERS.map((layer) => {
        const metrics = report.metrics.filter((metric) => metric.layer === layer.key);
        return (
          <section key={layer.key} aria-label={layer.title}>
            <h2 className="text-headline-sm text-text">{layer.title}</h2>
            {layer.note === undefined ? null : (
              <p className="mt-xs text-caption text-text-secondary">{layer.note}</p>
            )}
            {metrics.length === 0 ? (
              <p className="mt-sm text-body-sm text-text-secondary">
                이 계층의 지표가 게시물에 없습니다. 화면은 정본 목록을 들고 있지 않으므로 게시물이
                주는 것만 그립니다.
              </p>
            ) : (
              <ul className="mt-md flex flex-col gap-base">
                {metrics.map((metric) => (
                  <li key={metric.name} className="rounded-lg border border-border p-base">
                    <MetricRow metric={metric} />
                  </li>
                ))}
              </ul>
            )}
          </section>
        );
      })}

      <SourceFootnote />
    </div>
  );
}

/**
 * The representative scene (invariants U-1 ~ U-10).
 *
 * Built from whichever of the two metrics the artifact actually publishes — when one
 * is absent the card says so rather than silently rendering a single column, because a
 * one-sided card would quietly destroy the comparison that is the entire point.
 */
function HeadlineScene({ report }: { report: KpiReport }) {
  const revenue = report.metrics.find((metric) => metric.name === "revenue");
  const profit = report.metrics.find((metric) => metric.name === "contribution_profit");
  if (revenue === undefined || profit === undefined) {
    return (
      <section className="rounded-lg border border-border px-base py-lg">
        <StateChip state="planned" label="대표 장면을 그릴 수 없습니다" />
        <p className="mt-sm text-body-sm text-text">
          이 게시물에는 <code>revenue</code> 또는 <code>contribution_profit</code> 가 없습니다.
          두 지표가 같이 있어야 대비가 성립하므로 한쪽만 그리지 않습니다.
        </p>
      </section>
    );
  }

  return (
    <section
      aria-label="주문 경제성 — 매출과 기여이익"
      className="rounded-lg border border-border bg-surface p-lg"
    >
      <div className="flex flex-wrap items-center justify-between gap-sm">
        <div className="flex flex-wrap items-center gap-sm">
          <h2 className="text-headline-sm text-text">주문 경제성 · 커머스 실측</h2>
          <SourceBadge source="commerce" />
        </div>
        {isFixtureMode() ? <FixtureBadge /> : null}
      </div>

      {/* U-1 — same card, same row, 1:1 columns. Stacks under 1024px, commerce first. */}
      <div className="mt-md grid grid-cols-1 gap-base lg:grid-cols-2">
        {[revenue, profit].map((metric) => (
          <div key={metric.name} className="min-w-0">
            <MetricCell
              name={metric.name}
              // Layer 2 metrics are always split; commerce is the measured side here.
              metric={isSourceSplit(metric.value) ? metric.value.by_source.commerce : metric.value}
              scale="metric"
            />
            {metric.blocks === undefined || metric.blocks.length === 0 ? null : (
              <p className="mt-xs text-caption text-text-secondary">
                {/* U-7 — the real content of this scene: one cost field takes down a
                    Primary metric. The badge is what makes that legible. */}
                → {metric.blocks.join(" · ")}
                {metric.blocks.map((name) => {
                  const downstream = report.metrics.find((m) => m.name === name);
                  return downstream === undefined ? null : (
                    <RoleBadge key={name} role={downstream.role} />
                  );
                })}{" "}
                성립 불가
              </p>
            )}
          </div>
        ))}
      </div>
    </section>
  );
}

/** Counts published by the artifact. The screen prints them; it never tallies (DB-012). */
function Summary({ report }: { report: KpiReport }) {
  const s = report.summary;
  const cells: [string, number][] = [
    ["전체", s.total],
    ["계산됨", s.ok],
    ["잠정", s.unconfirmed],
    ["계산 불가", s.unavailable],
    ["실행 불가", s.blocked],
    ["미실행", s.not_run],
  ];

  /*
   * Contract self-check on the publisher's own numbers — not a recomputation.
   *
   * ★ `total` counts metric *values*, not metric rows. A layer-1/2 metric carries one
   * value per source, so the real artifact reports total 48 for 24 rows (24 x 2).
   * An earlier version of this check compared `total` with `metrics.length` and fired
   * a false "계약 위반" on a perfectly valid artifact — a screen that cries wolf about
   * its own input is as harmful as one that stays silent.
   *
   * What is actually checkable without knowing the row/value ratio is the summary's
   * internal consistency: the status breakdown must add up to `total`.
   */
  const breakdown = s.ok + s.unconfirmed + s.unavailable + s.blocked + s.not_run;
  const mismatch = s.total !== breakdown;

  return (
    <section aria-label="지표 집계" className="rounded-lg border border-border px-base py-md">
      <dl className="grid grid-cols-3 gap-sm md:grid-cols-6">
        {cells.map(([label, count]) => (
          <div key={label}>
            <dt className="text-caption text-text-secondary">{label}</dt>
            <dd className="text-table-number text-text">{String(count)}</dd>
          </div>
        ))}
      </dl>
      <p className="mt-sm text-caption text-text-secondary">
        기준일 D: {report.index_date === null ? "— (데이터가 없어 기준일을 정할 수 없습니다)" : report.index_date}
        {" · "}정의 버전: {report.definition_version}
        {" · "}지표 {String(report.metrics.length)}종 / 값 {String(s.total)}개 (계층 1·2 는
        출처별로 값이 둘이다)
      </p>
      {mismatch ? (
        <div className="mt-sm">
          <StateChip
            state="violation"
            label={`계약 위반 · summary.total ${String(
              s.total,
            )} 과 상태별 합계 ${String(breakdown)} 이 다릅니다`}
          />
        </div>
      ) : null}
    </section>
  );
}

/** One metric: definition on the left, the value(s) on the right, sources never merged. */
function MetricRow({ metric }: { metric: KpiMetric }) {
  return (
    <div className="flex flex-col gap-sm">
      <div className="flex flex-wrap items-baseline gap-xs">
        <span className="text-label-md text-text">{metric.name}</span>
        <RoleBadge role={metric.role} />
      </div>

      <dl className="grid grid-cols-1 gap-xs text-caption text-text-secondary md:grid-cols-2">
        <Definition label="모집단" value={metric.population} />
        <Definition
          label="기간"
          value={
            metric.window.label === undefined
              ? `${metric.window.direction}${
                  typeof metric.window.days === "number" ? ` · ${String(metric.window.days)}일` : ""
                }`
              : metric.window.label
          }
        />
        <Definition label="분모" value={metric.denominator_definition} />
        {metric.formula === undefined ? null : (
          <Definition label="계산식" value={metric.formula} />
        )}
        {metric.definition_ref === undefined ? null : (
          <Definition label="정의" value={metric.definition_ref} />
        )}
      </dl>

      {isSourceSplit(metric.value) ? (
        <div className="grid grid-cols-1 gap-base lg:grid-cols-2">
          {/* Order is fixed: commerce first, in the DOM as well as on screen, so that
              stacking and screen readers both keep it (S-1). */}
          <div className="rounded-md border border-border p-sm">
            <SourceBadge source="commerce" />
            <div className="mt-xs">
              <MetricCell
                name={metric.name}
                metric={metric.value.by_source.commerce}
                scale="table-number"
                hideName
              />
            </div>
          </div>
          <div className="rounded-md border border-border p-sm">
            <SourceBadge source="simulator" />
            <div className="mt-xs">
              <MetricCell
                name={metric.name}
                metric={metric.value.by_source.simulator}
                scale="table-number"
                hideName
              />
            </div>
          </div>
        </div>
      ) : (
        <MetricCell name={metric.name} metric={metric.value} scale="table-number" hideName />
      )}

      {metric.blocks === undefined || metric.blocks.length === 0 ? null : (
        <p className="text-caption text-text-secondary">
          이 지표가 무너지면 함께 무너지는 것: {metric.blocks.join(" · ")}
        </p>
      )}
      {isSourceSplit(metric.value) && metric.value.combined !== undefined ? (
        <p className="text-caption text-text-secondary">
          합산 값이 게시되었습니다 — 이름과 칩에 `합산` 을 함께 표시합니다:{" "}
          {formatMetricValue(metric.value.combined).valueText}
        </p>
      ) : null}
    </div>
  );
}

function Definition({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex gap-xs">
      <dt className="shrink-0">{label}</dt>
      <dd className="min-w-0 text-text">{value}</dd>
    </div>
  );
}
