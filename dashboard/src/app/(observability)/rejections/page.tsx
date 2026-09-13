/**
 * V2 — contract violations. "What was rejected and why?"
 *
 * ★ SECURITY BOUNDARY. rejected.jsonl keeps rejected records verbatim, and one of the
 *   rejection reasons is "carries a field the measurement layer must never see" —
 *   Hidden Trait, tau and potential outcomes end up in exactly those records. The
 *   contract already restricts what may be published, and this screen narrows it
 *   further: only `offending_fields` (names) is rendered, never any value. Field names
 *   are enough to understand a rejection, and if they were not, that still would not
 *   justify opening a leak path (ISO-003).
 *
 * ★ Zero rejections out of N attempts is a measured zero and is shown as one, with its
 *   basis. Zero rejections out of zero attempts is not: the denominator is zero, so
 *   the rate is an em dash rather than 0% (V-4).
 */
import { loadRejectionReport } from "@/lib/artifacts/read";
import { ArtifactGate } from "@/components/ArtifactGate";
import { CoverageTable } from "@/components/CoverageTable";
import { MetricCell } from "@/components/MetricCell";
import { NoticeBar } from "@/components/NoticeBar";
import { ProvenanceBar, RefreshLink } from "@/components/ProvenanceBar";

export const dynamic = "force-dynamic";

/** At most three examples per reason: the reader needs illustrations, not a log. */
const SAMPLES_PER_REASON = 3;

export default async function RejectionsPage() {
  const result = await loadRejectionReport();
  if (result.kind !== "ok") return <ArtifactGate result={result} />;
  const report = result.artifact;

  // Group in publish order; no sorting by count, which would bury the zero rows.
  const byReason = report.by_reason;

  // At most three examples per reason, keeping the publisher's reason order. Samples
  // whose reason_key is not in by_reason are still shown — dropping them would hide a
  // rejection the summary already counted.
  const seen = new Map<string, number>();
  const shownSamples = report.samples.filter((sample) => {
    const taken = seen.get(sample.reason_key);
    const next = taken === undefined ? 1 : taken + 1;
    seen.set(sample.reason_key, next);
    return next <= SAMPLES_PER_REASON;
  });

  return (
    <div className="flex flex-col gap-lg">
      <header className="flex flex-wrap items-center justify-between gap-sm">
        <h1 className="text-headline-lg text-text">계약 위반 (거부)</h1>
        <RefreshLink route="/rejections" />
      </header>

      <ProvenanceBar envelope={report} />
      <NoticeBar notices={report.notices} />

      <section aria-label="거부 요약">
        <div className="grid grid-cols-1 gap-base md:grid-cols-3">
          <div className="rounded-lg border border-border p-base">
            <MetricCell name="events_rejected" metric={report.totals.events_rejected} />
          </div>
          <div className="rounded-lg border border-border p-base">
            <MetricCell name="rejection_rate" metric={report.totals.rejection_rate} />
          </div>
          <div className="rounded-lg border border-border p-base">
            <MetricCell name="distinct_reasons" metric={report.totals.distinct_reasons} />
          </div>
        </div>
      </section>

      <section aria-label="사유별 거부 건수">
        <h2 className="text-headline-sm text-text">사유별</h2>
        {byReason.length === 0 ? (
          <p className="mt-sm text-body-sm text-text-secondary">
            게시물에 사유별 집계가 없습니다. 거부 건수 자체는 위의 지표가 말합니다 — 이 목록이 비어
            있다는 것을 &quot;거부 없음&quot;으로 바꿔 쓰지 않습니다.
          </p>
        ) : (
          <div className="mt-md">
            <CoverageTable
              caption="거부 사유별 건수"
              rows={byReason}
              rowKey={(row) => row.reason_key}
              columns={[
                {
                  key: "reason",
                  header: "사유",
                  render: (row) => (
                    <div>
                      <div className="text-body-sm text-text">{row.reason_label}</div>
                      <code className="text-caption text-text-secondary">{row.reason_key}</code>
                    </div>
                  ),
                },
                {
                  key: "count",
                  header: "건수",
                  align: "right",
                  // An integer counted by the publisher, printed as given.
                  render: (row) => <span className="text-table-number">{String(row.count)}</span>,
                },
                {
                  key: "fields",
                  header: "관련 필드",
                  render: (row) =>
                    row.by_field === undefined ? (
                      <span className="text-caption text-text-secondary">—</span>
                    ) : (
                      <span className="text-caption text-text-secondary">
                        {Object.entries(row.by_field)
                          .map(([field, count]) => `${field} ${String(count)}건`)
                          .join(" · ")}
                      </span>
                    ),
                },
              ]}
            />
          </div>
        )}
      </section>

      <section aria-label="사유별 대표 사례">
        <h2 className="text-headline-sm text-text">대표 사례</h2>
        <p className="mt-xs text-caption text-text-secondary">
          필드 <strong>이름</strong>만 표시합니다. 거부 레코드의 값은 렌더링하지 않습니다 — 거부
          사유 중 하나가 &quot;측정 계층을 통과할 수 없는 필드&quot;이고, 그 값이 화면까지 오면
          격리가 뚫립니다.
        </p>
        {shownSamples.length === 0 ? (
          <p className="mt-sm text-body-sm text-text-secondary">
            대표 사례가 게시되지 않았습니다. 이것을 &quot;거부 없음&quot;으로 바꿔 쓰지 않습니다.
          </p>
        ) : (
          <ul className="mt-md flex flex-col gap-sm">
            {shownSamples.map((sample, i) => (
              <li
                key={`${sample.reason_key}-${String(i)}`}
                className="rounded-lg border border-border p-base"
              >
                <div className="flex flex-wrap items-center gap-xs">
                  <code className="text-caption text-text-secondary">{sample.reason_key}</code>
                  <span className="text-caption text-text-secondary">
                    event_type: {sample.event_type === null ? "—" : sample.event_type}
                  </span>
                  {sample.source === undefined ? null : (
                    <span className="text-caption text-text-secondary">출처: {sample.source}</span>
                  )}
                  {sample.partition_date === undefined || sample.partition_date === null ? null : (
                    <span className="text-caption text-text-secondary">{sample.partition_date}</span>
                  )}
                </div>
                <ul className="mt-xs text-body-sm text-text">
                  {sample.problems.map((problem) => (
                    <li key={problem}>· {problem}</li>
                  ))}
                </ul>
                {/* ★ Names only. `offending_values` exists in the contract but is
                    deliberately absent from RejectionSample so it cannot be rendered. */}
                {sample.offending_fields === undefined ||
                sample.offending_fields.length === 0 ? null : (
                  <p className="mt-xs text-caption text-text-secondary">
                    문제 필드(이름만): {sample.offending_fields.join(" · ")}
                  </p>
                )}
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}
