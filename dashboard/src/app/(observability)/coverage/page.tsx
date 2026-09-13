/**
 * V3 — field coverage. "Which fields are empty?"
 *
 * ★ This is the one screen whose default sort is not the canonical order. Rows are
 *   ascending by fill rate so the gaps float to the top — the single sanctioned
 *   exception to V-0, because here putting gaps first *surfaces* them rather than
 *   burying them. Everywhere else, sorting by magnitude pushes zeros out of sight.
 *
 * ★ schema_gaps get their own rows. field_coverage only counts columns that exist, so
 *   a formula input that has no column at all (unit_cost, discount, shipping_fee,
 *   refund) appears in no coverage number anywhere. If this table did not list them
 *   they would be invisible on every screen, forever — and invisible reads as fine.
 *
 * ★ Every one of the 22 fields is a row, including fully-populated ones and
 *   never-seen ones. No column is ever dropped on narrow screens; the table scrolls.
 */
import { loadFieldCoverageReport } from "@/lib/artifacts/read";
import type { FieldCoverage, MetricValue } from "@/lib/artifacts/types";
import { ArtifactGate } from "@/components/ArtifactGate";
import { CoverageTable } from "@/components/CoverageTable";
import { ImpactChain } from "@/components/ImpactChain";
import { MetricCell } from "@/components/MetricCell";
import { NoticeBar } from "@/components/NoticeBar";
import { ProvenanceBar, RefreshLink } from "@/components/ProvenanceBar";
import { SourceFootnote } from "@/components/SourceColumns";
import { StateChip } from "@/components/StateChip";

export const dynamic = "force-dynamic";

interface FieldRow {
  name: string;
  field: FieldCoverage;
}

/**
 * Sort key for "gaps first".
 *
 * Only published, computed fill rates take part in the ordering; anything not computed
 * sorts to the very top, because an unknown coverage is at least as interesting as a
 * low one. Returning a number here is layout ordering, not a derived metric — no value
 * produced by this function is ever displayed.
 */
function fillRateOrder(metric: MetricValue): number {
  if (metric.status !== "ok" && metric.status !== "unconfirmed") return -1;
  return typeof metric.value === "number" ? metric.value : -1;
}

export default async function CoveragePage() {
  const result = await loadFieldCoverageReport();
  if (result.kind !== "ok") return <ArtifactGate result={result} />;
  const report = result.artifact;

  const rows: FieldRow[] = Object.entries(report.fields)
    .map(([name, field]) => ({ name, field }))
    .sort((a, b) => {
      const diff =
        fillRateOrder(a.field.fill_rate.by_source.commerce) -
        fillRateOrder(b.field.fill_rate.by_source.commerce);
      // Ties keep a stable, name-based order so the table does not reshuffle between
      // loads of the same artifact.
      return diff !== 0 ? diff : a.name.localeCompare(b.name);
    });

  return (
    <div className="flex flex-col gap-lg">
      <header className="flex flex-wrap items-center justify-between gap-sm">
        <h1 className="text-headline-lg text-text">필드 충족률</h1>
        <RefreshLink route="/coverage" />
      </header>

      <ProvenanceBar envelope={report} />
      <NoticeBar notices={report.notices} />

      <section aria-label="결손 필드 요약">
        <h2 className="text-headline-sm text-text">한 건도 값이 없는 필드</h2>
        {report.missing_fields.length === 0 ? (
          <p className="mt-sm text-body-sm text-text-secondary">
            게시물이 결손 필드를 보고하지 않았습니다 (<code>missing_fields</code> 0건).
          </p>
        ) : (
          <ul className="mt-sm flex flex-wrap gap-xs">
            {report.missing_fields.map((name) => (
              <li key={name}>
                <StateChip state="gap" label={name} reasonCode="MISSING_FIELD" />
              </li>
            ))}
          </ul>
        )}
      </section>

      <section aria-label="필드 22종 충족률">
        <h2 className="text-headline-sm text-text">필드별 충족률</h2>
        <p className="mt-xs text-caption text-text-secondary">
          {String(rows.length)}개 필드 전부를 <strong>충족률 오름차순</strong>(결손이 위)으로
          표시합니다. 열을 숨기지 않고, 좁아지면 표만 가로로 스크롤합니다.
        </p>
        <div className="mt-md">
          <CoverageTable
            caption="필드별 충족률과 영향"
            rows={rows}
            rowKey={(row) => row.name}
            columns={[
              {
                key: "field",
                header: "필드",
                render: (row) => (
                  <div>
                    <div className="text-body-sm text-text">{row.name}</div>
                    <span className="text-caption text-text-secondary">{row.field.group}</span>
                  </div>
                ),
              },
              {
                key: "commerce",
                header: "◼ 커머스 충족률",
                align: "right",
                render: (row) => (
                  <MetricCell
                    name={row.name}
                    metric={row.field.fill_rate.by_source.commerce}
                    scale="table-number"
                    hideName
                  />
                ),
              },
              {
                key: "simulator",
                header: "◇ 시뮬레이터 충족률",
                align: "right",
                render: (row) => (
                  <MetricCell
                    name={row.name}
                    metric={row.field.fill_rate.by_source.simulator}
                    scale="table-number"
                    hideName
                  />
                ),
              },
              {
                key: "impact",
                header: "영향",
                render: (row) =>
                  row.field.blocks_metrics.length === 0 ? (
                    <span className="text-caption text-text-secondary">—</span>
                  ) : (
                    <span className="text-caption text-text-secondary">
                      {row.field.blocks_metrics.join(" · ")}
                    </span>
                  ),
              },
            ]}
          />
        </div>
      </section>

      <section aria-label="스키마 공백">
        <h2 className="text-headline-sm text-text">스키마 공백</h2>
        <p className="mt-xs text-caption text-text-secondary">
          계산식이 요구하는데 <strong>컬럼 자체가 없는</strong> 항목입니다. 충족률 표는 존재하는
          컬럼만 세므로 이 행이 없으면 어디에도 나타나지 않습니다.
        </p>
        {report.schema_gaps.length === 0 ? (
          <p className="mt-sm text-body-sm text-text-secondary">
            게시물이 스키마 공백을 보고하지 않았습니다.
          </p>
        ) : (
          <ul className="mt-md flex flex-col gap-sm">
            {report.schema_gaps.map((gap) => (
              <li key={gap.ref}>
                <ImpactChain
                  origin={gap.ref}
                  reasonCode={gap.reason_code}
                  detail={`${gap.reason_detail} · 요구하는 계산식: ${gap.required_by_formula} · 있어야 할 곳: ${gap.where_it_should_live}${
                    gap.decision_ref === undefined ? "" : ` · 결정 항목: ${gap.decision_ref}`
                  }`}
                  hops={[
                    { metrics: gap.blocks_metrics, outcome: "계산 불가" },
                    ...(gap.blocks_checks === undefined || gap.blocks_checks.length === 0
                      ? []
                      : [{ metrics: gap.blocks_checks, outcome: "검사 불가" }]),
                  ]}
                />
              </li>
            ))}
          </ul>
        )}
      </section>

      <SourceFootnote />
    </div>
  );
}
