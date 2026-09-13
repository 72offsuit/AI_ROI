/**
 * V1 — collection status. "Are events arriving? When, what, how many?"
 *
 * ★ All 16 event types are rows, always, in fixed alphabetical order. Sorting by
 *   count would push every zero type to the bottom, which hides them without anyone
 *   deciding to hide them, and the types with zero rows are exactly what a reader
 *   comes here to find.
 *
 * ★ `event_type_coverage` has a fixed denominator of 16, so even all-zero collection
 *   yields a measured `0 / 16` rather than an em dash — it is a counted zero, and the
 *   basis line is what proves it.
 */
import Link from "next/link";

import { loadIngestionReport } from "@/lib/artifacts/read";
import type { SourceSplit } from "@/lib/artifacts/types";
import { ArtifactGate } from "@/components/ArtifactGate";
import { CoverageTable } from "@/components/CoverageTable";
import { IngestionTimeline } from "@/components/IngestionTimeline";
import { MetricCell } from "@/components/MetricCell";
import { NoticeBar } from "@/components/NoticeBar";
import { ProvenanceBar, RefreshLink } from "@/components/ProvenanceBar";
import { ConnectionState, SourceBadge, SourceFootnote } from "@/components/SourceColumns";

export const dynamic = "force-dynamic";

export default async function IngestionPage() {
  const result = await loadIngestionReport();
  if (result.kind !== "ok") return <ArtifactGate result={result} />;
  const report = result.artifact;

  const totals = report.totals;
  // Fixed order: the key set is guaranteed to hold all 16 types (minProperties: 16),
  // so sorting by name is stable and independent of how many events arrived.
  const eventTypes = Object.keys(report.by_event_type).sort();

  return (
    <div className="flex flex-col gap-lg">
      <header className="flex flex-wrap items-center justify-between gap-sm">
        <h1 className="text-headline-lg text-text">수집 현황</h1>
        <RefreshLink route="/ingestion" />
      </header>

      <ProvenanceBar envelope={report} />
      <NoticeBar notices={report.notices} />

      <section aria-label="출처별 연결 상태">
        <h2 className="text-headline-sm text-text">출처</h2>
        <div className="mt-md grid grid-cols-1 gap-base lg:grid-cols-2">
          {/* Commerce is always the left/first column, even when it is empty (S-1, S-6).
              Each source is its own landmark region so a screen reader user can jump
              between them and always knows which source they are inside. */}
          <section aria-label="커머스 실측" className="rounded-lg border border-border p-base">
            <SourceBadge source="commerce" />
            <div className="mt-sm">
              <ConnectionState link={report.sources.commerce} />
            </div>
          </section>
          <section aria-label="시뮬레이터 생성" className="rounded-lg border border-border p-base">
            <SourceBadge source="simulator" />
            <div className="mt-sm">
              <ConnectionState link={report.sources.simulator} />
            </div>
          </section>
        </div>
      </section>

      <section aria-label="수집 건전성 지표">
        <h2 className="text-headline-sm text-text">수집 건전성</h2>
        <div className="mt-md grid grid-cols-1 gap-base md:grid-cols-2 xl:grid-cols-3">
          <SplitCard name="events_ingested" split={totals.events_ingested} />
          <Card name="events_rejected" metric={totals.events_rejected} />
          <Card name="rejection_rate" metric={totals.rejection_rate} />
          <Card name="event_type_coverage" metric={totals.event_type_coverage} />
          <Card name="partition_day_count" metric={totals.partition_day_count} />
          <Card name="ingestion_days_gap" metric={totals.ingestion_days_gap} />
          <Card name="unavailable_metric_count" metric={totals.unavailable_metric_count} />
          {/* Published as not_run + PRECONDITION_MISSING: the sink has no heartbeat
              record, so an outage and genuine inactivity leave identical traces. The
              screen states that it cannot tell rather than guessing. */}
          <Card name="ingestion_gap_attribution" metric={totals.ingestion_gap_attribution} />
        </div>
      </section>

      <section aria-label="수집 타임라인">
        <h2 className="text-headline-sm text-text">수집 타임라인</h2>
        <p className="mt-xs text-caption text-text-secondary">
          막대만 씁니다. 선 차트는 결손 구간을 이어 없는 값을 만듭니다.
        </p>
        <div className="mt-md">
          <IngestionTimeline partitions={report.partitions} />
        </div>
      </section>

      <section aria-label="event_type 16종 매트릭스">
        <h2 className="text-headline-sm text-text">event_type 매트릭스</h2>
        <p className="mt-xs text-caption text-text-secondary">
          {String(eventTypes.length)}종 전부를 이름 고정 순서로 표시합니다. 0건 종류를 목록에서
          빼지 않습니다.
        </p>
        <div className="mt-md">
          <CoverageTable
            caption="event_type 별 수집 건수"
            rows={eventTypes}
            rowKey={(name) => name}
            columns={[
              {
                key: "name",
                header: "event_type",
                render: (name) => <span className="text-body-sm text-text">{name}</span>,
              },
              {
                key: "commerce",
                header: "◼ 커머스",
                align: "right",
                render: (name) => (
                  <MetricCell
                    name={name}
                    metric={report.by_event_type[name].by_source.commerce}
                    scale="table-number"
                    hideName
                  />
                ),
              },
              {
                key: "simulator",
                header: "◇ 시뮬레이터",
                align: "right",
                render: (name) => (
                  <MetricCell
                    name={name}
                    metric={report.by_event_type[name].by_source.simulator}
                    scale="table-number"
                    hideName
                  />
                ),
              },
            ]}
          />
        </div>
      </section>

      <p className="text-body-sm">
        <Link href="/rejections" className="text-primary underline">
          거부된 이벤트 보기 →
        </Link>
      </p>

      <SourceFootnote />
    </div>
  );
}

function Card({ name, metric }: { name: string; metric: Parameters<typeof MetricCell>[0]["metric"] }) {
  return (
    <div className="rounded-lg border border-border p-base">
      <MetricCell name={name} metric={metric} />
    </div>
  );
}

/** Collection health is the one layer where a `combined` value is contract-legal. */
function SplitCard({ name, split }: { name: string; split: SourceSplit }) {
  return (
    <div className="rounded-lg border border-border p-base">
      <p className="text-label-md text-text">{name}</p>
      <div className="mt-sm flex flex-col gap-sm">
        <div>
          <SourceBadge source="commerce" />
          <MetricCell name={name} metric={split.by_source.commerce} scale="table-number" hideName />
        </div>
        <div>
          <SourceBadge source="simulator" />
          <MetricCell name={name} metric={split.by_source.simulator} scale="table-number" hideName />
        </div>
      </div>
    </div>
  );
}
