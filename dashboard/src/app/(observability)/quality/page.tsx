/**
 * V5 — data quality. "Which checks ran, and what did they actually examine?"
 *
 * ★ Five check statuses, not two. `vacuous` — the check ran and examined zero rows —
 *   is neither a pass nor a failure, and in C1 it is the *normal* state (7 of the 18
 *   checks in the empty-sink artifact). Drawing it green would claim something was
 *   verified when nothing was; drawing it red would cry wolf about the expected state.
 *   It renders as info, with no ✓ and no green anywhere.
 *
 * ★ The condition is `status === "vacuous"` alone. ADR-0010 made `pass` with
 *   `examined_rows: 0` schema-illegal, so the older `pass && rows === 0` test is dead
 *   code that can never fire, and re-reading examined_rows would repeat a judgement the
 *   publisher already made (DB-012).
 *
 * ★ `vacuous` rows' reason_code is not trusted: every one in the current fixtures says
 *   NOT_RUN, which conflates "ran and found nothing" with "never ran". The screen
 *   branches on status only and prints reason_detail as prose. M-07 fixes the contract.
 *
 * ★ `gate_result: incomplete` never uses a success token and never says "통과" on its
 *   own — it reads "미완 · 통과 N / 미실행 M / 차단 K".
 *
 * ★ The canonical check list is NOT held here as a constant. The artifact ships every
 *   check it knows about (18 in empty-sink) and `spec_coverage` reports what the spec
 *   expects; a screen-side list would be a second source of truth, and a check missing
 *   from both would read as passing.
 */
import { loadDataQualityReport } from "@/lib/artifacts/read";
import type { CheckStatus, DataQualityReport, QualityCheck } from "@/lib/artifacts/types";
import { deriveCheckState } from "@/lib/format/state";
import { ArtifactGate } from "@/components/ArtifactGate";
import { CoverageTable } from "@/components/CoverageTable";
import { NoticeBar } from "@/components/NoticeBar";
import { ProvenanceBar, RefreshLink } from "@/components/ProvenanceBar";
import { StateChip, VacuousChip } from "@/components/StateChip";

export const dynamic = "force-dynamic";

/** Value-slot copy per check status. `vacuous` never borrows the pass wording. */
function checkValueText(check: QualityCheck): string {
  switch (check.status) {
    case "pass":
      return "통과";
    case "fail":
      return typeof check.violations === "number" ? `실패 ${String(check.violations)}건` : "실패";
    case "vacuous":
      return "공허한 통과";
    case "not_run":
      // "미실행" means unknown; an em dash would mean absent. Different facts.
      return "미실행";
    case "blocked":
      return "—";
    default:
      return "—";
  }
}

const GATE_COPY: Record<DataQualityReport["gate_result"], string> = {
  pass: "통과 — 실행한 검사가 전부 통과했고 미실행·차단·공허한 통과가 없습니다",
  fail: "실패 — 하나 이상의 검사가 위반을 발견했습니다",
  // Never the word "통과" alone, and never a success token (C-14).
  incomplete: "미완",
};

export default async function QualityPage() {
  const result = await loadDataQualityReport();
  if (result.kind !== "ok") return <ArtifactGate result={result} />;
  const report = result.artifact;

  // Counting the rows the artifact shipped, to state the gate in "N / M / K" form and
  // to verify the artifact's own reported_checks. Both are contract checks over given
  // values, not metric derivation (R-10).
  const tally = (status: CheckStatus) =>
    report.checks.filter((check) => check.status === status).length;

  const gateState = report.gate_result === "fail" ? "violation" : report.gate_result === "pass" ? "ok" : "gap";
  const gateLabel =
    report.gate_result === "incomplete"
      ? `${GATE_COPY.incomplete} · 통과 ${String(tally("pass"))} / 미실행 ${String(
          tally("not_run"),
        )} / 차단 ${String(tally("blocked"))} / 공허한 통과 ${String(tally("vacuous"))}`
      : GATE_COPY[report.gate_result];

  const reportedMismatch = report.spec_coverage.reported_checks !== report.checks.length;

  /*
   * Contract self-check: an item cannot be both "covered by DQ-xx" and "covered by
   * nothing". The real artifact (run_id MR-20260911-124223) lists all 11 spec items in
   * `unmapped_spec_items` while every one of them has a non-empty `covered_by`.
   *
   * Reporting the field verbatim would tell the reader 11 canonical checks are
   * unmapped, which is not true — so the contradiction itself is surfaced instead of
   * being passed through. Comparing two published fields is a contract check, not a
   * derivation (R-10).
   */
  const contradictorilyUnmapped = report.spec_coverage.unmapped_spec_items.filter((ref) => {
    const item = report.spec_coverage.spec_items.find((i) => i.spec_ref === ref);
    return item !== undefined && item.covered_by.length > 0;
  });

  return (
    <div className="flex flex-col gap-lg">
      <header className="flex flex-wrap items-center justify-between gap-sm">
        <h1 className="text-headline-lg text-text">데이터 품질</h1>
        <RefreshLink route="/quality" />
      </header>

      <ProvenanceBar envelope={report} />
      <NoticeBar notices={report.notices} />

      <section aria-label="게이트 결과" className="rounded-lg border border-border px-base py-lg">
        <StateChip state={gateState} label={gateLabel} />
        <p className="mt-sm text-caption text-text-secondary">
          실린 검사 {String(report.checks.length)}건. 화면은 정본 목록을 상수로 들지 않고 게시물이
          주는 검사만 그립니다.
        </p>
      </section>

      <section aria-label="검사 목록">
        <h2 className="text-headline-sm text-text">검사</h2>
        <div className="mt-md">
          <CoverageTable
            caption="데이터 품질 검사와 각 검사의 범위"
            // Publish order, not status order: sorting by status would group the
            // uninteresting passes at one end and the gaps at the other, which changes
            // what the reader notices first.
            rows={report.checks}
            rowKey={(check) => check.id}
            columns={[
              {
                key: "id",
                header: "검사",
                render: (check) => (
                  <div>
                    <div className="text-body-sm text-text">
                      {check.id} · {check.title}
                    </div>
                    <span className="text-caption text-text-secondary">{check.spec_ref}</span>
                  </div>
                ),
              },
              {
                key: "status",
                header: "결과",
                render: (check) => (
                  <div className="flex flex-col gap-xs">
                    <span className="text-table-number text-text">{checkValueText(check)}</span>
                    {check.status === "vacuous" ? (
                      <VacuousChip />
                    ) : (
                      <StateChip
                        state={deriveCheckState(check.status)}
                        label={check.status}
                        reasonCode={check.reason_code}
                      />
                    )}
                  </div>
                ),
              },
              {
                key: "rows",
                header: "검사 대상",
                align: "right",
                render: (check) => (
                  <span className="text-table-number text-text-secondary">
                    {/* typeof, not truthiness: examined_rows 0 is the evidence that
                        the check looked and found nothing. */}
                    {typeof check.examined_rows === "number"
                      ? `${String(check.examined_rows)}행`
                      : "—"}
                  </span>
                ),
              },
              {
                key: "scope",
                header: "범위",
                render: (check) => (
                  <div className="flex flex-col gap-xs">
                    {/* Always inline. A partial check with its scope hidden reads as
                        a full check. */}
                    <span className="text-caption text-text-secondary">{check.scope}</span>
                    {check.reason_detail === undefined ? null : (
                      <span className="text-caption text-text-secondary">
                        {check.reason_detail}
                      </span>
                    )}
                  </div>
                ),
              },
            ]}
          />
        </div>
      </section>

      <section aria-label="정본 검사 목록 대비 적용 범위">
        <h2 className="text-headline-sm text-text">정본 대비 적용 범위</h2>
        {reportedMismatch ? (
          <div className="mt-sm">
            <StateChip
              state="violation"
              label={`계약 위반 · reported_checks ${String(
                report.spec_coverage.reported_checks,
              )} 와 실린 검사 ${String(report.checks.length)} 건이 다릅니다`}
            />
          </div>
        ) : null}

        {contradictorilyUnmapped.length > 0 ? (
          <div className="mt-sm">
            <StateChip
              state="violation"
              label={`계약 위반 · ${String(
                contradictorilyUnmapped.length,
              )}개 항목이 unmapped_spec_items 에 있으면서 covered_by 도 비어 있지 않습니다`}
            />
            <p className="mt-xs text-caption text-text-secondary">
              해당 항목: {contradictorilyUnmapped.join(" · ")}
            </p>
          </div>
        ) : null}

        {report.spec_coverage.unmapped_spec_items.length === 0 ? (
          <p className="mt-sm text-body-sm text-text-secondary">
            정본 항목 중 어떤 검사도 덮지 않는 것은 없습니다.
          </p>
        ) : (
          <div className="mt-sm">
            <StateChip
              state="gap"
              label={`정본에 있으나 덮는 검사가 없는 항목 ${String(
                report.spec_coverage.unmapped_spec_items.length,
              )}건`}
            />
            <ul className="mt-xs text-body-sm text-text">
              {report.spec_coverage.unmapped_spec_items.map((item) => (
                <li key={item}>· {item}</li>
              ))}
            </ul>
          </div>
        )}

        <div className="mt-md">
          <CoverageTable
            caption="정본 검사 항목과 이를 덮는 검사"
            rows={report.spec_coverage.spec_items}
            rowKey={(item) => item.spec_ref}
            columns={[
              {
                key: "spec",
                header: "정본 항목",
                render: (item) => <span className="text-body-sm text-text">{item.spec_ref}</span>,
              },
              {
                key: "covered",
                header: "덮는 검사",
                render: (item) => (
                  <span className="text-caption text-text-secondary">
                    {item.covered_by.length === 0 ? "없음" : item.covered_by.join(" · ")}
                  </span>
                ),
              },
              {
                key: "worst",
                header: "최악 결과",
                render: (item) =>
                  item.worst_status === "vacuous" ? (
                    <VacuousChip />
                  ) : (
                    <StateChip
                      state={deriveCheckState(item.worst_status)}
                      label={item.worst_status}
                    />
                  ),
              },
            ]}
          />
        </div>
      </section>
    </div>
  );
}
