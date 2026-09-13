/**
 * V6 — freeze status. "Which schema and which commit am I looking at?"
 *
 * ★ `overall: "not_started"` is drawn as a fact, not a warning. C1 deliberately does
 *   not pass GATE 1 — partial sealing is the maximum in scope — so not_started is the
 *   correct state today, and colouring it red would train the reader to ignore it.
 *
 * ★ `scope_note` is never collapsed. A PARTIAL lock whose boundary is hidden reads as
 *   a full lock, which is the most consequential misreading this screen can produce.
 *   A PARTIAL item with no scope_note is flagged as a contract violation.
 *
 * ★ `verification: "not_run"` never shares a colour with `match`. Not comparing a file
 *   is not the same as comparing it and finding it identical.
 *
 * ★ `met: null` in the precondition list stays distinct from `false`: "not checked"
 *   and "checked and unmet" are different, and collapsing them is how an unchecked
 *   item becomes a passing one.
 */
import { loadFreezeStatus } from "@/lib/artifacts/read";
import type { FileVerification, FreezeStatus, LockItem } from "@/lib/artifacts/types";
import type { VisualState } from "@/lib/format/state";
import { ArtifactGate } from "@/components/ArtifactGate";
import { CoverageTable } from "@/components/CoverageTable";
import { NoticeBar } from "@/components/NoticeBar";
import { ProvenanceBar, RefreshLink } from "@/components/ProvenanceBar";
import { StateChip } from "@/components/StateChip";

export const dynamic = "force-dynamic";

const OVERALL: Record<FreezeStatus["overall"], { state: VisualState; text: string }> = {
  // Today's normal state: stated plainly, in info rather than warning colours.
  not_started: { state: "unconnected", text: "봉인 시작 전 — C1 의 정상 상태입니다" },
  partial: { state: "gap", text: "부분 봉인 — 범위 한정 문구를 함께 읽으십시오" },
  sealed: { state: "ok", text: "봉인됨" },
  violated: { state: "violation", text: "봉인 불일치 — 정본 파일이 Lock 시점과 다릅니다" },
};

const ITEM_STATE: Record<LockItem["status"], VisualState> = {
  LOCKED: "ok",
  PARTIAL: "gap",
  PENDING: "not_run",
  BLOCKED: "env_blocked",
  // Out of scope is a planned absence, not a failure to seal.
  OUT_OF_SCOPE: "planned",
};

const VERIFICATION: Record<FileVerification, { state: VisualState; text: string }> = {
  match: { state: "ok", text: "일치" },
  mismatch: { state: "violation", text: "불일치" },
  missing: { state: "gap", text: "파일 없음" },
  // Explicitly not the same visual state as `match`.
  not_run: { state: "not_run", text: "대조하지 않음" },
};

export default async function FreezePage() {
  const result = await loadFreezeStatus();
  if (result.kind !== "ok") return <ArtifactGate result={result} />;
  const report = result.artifact;
  const overall = OVERALL[report.overall];

  return (
    <div className="flex flex-col gap-lg">
      <header className="flex flex-wrap items-center justify-between gap-sm">
        <h1 className="text-headline-lg text-text">봉인 상태</h1>
        <RefreshLink route="/freeze" />
      </header>

      <ProvenanceBar envelope={report} />
      <NoticeBar notices={report.notices} />

      <section aria-label="전체 봉인 상태" className="rounded-lg border border-border px-base py-lg">
        <StateChip state={overall.state} label={`${report.gate} · ${overall.text}`} />
        <p className="mt-sm text-caption text-text-secondary">
          {report.lock_record === undefined || report.lock_record === null
            ? "Lock 기록 파일이 없습니다 (config/gate1_lock.yaml 미생성)."
            : `Lock 기록: ${report.lock_record.path} · ${report.lock_record.locked_at} · ${report.lock_record.locked_by}`}
        </p>
        <p className="mt-xs text-caption text-text-secondary">
          EXPERIMENT_ENVIRONMENT_v1 은 선언되지 않았습니다. C1 에서 도달 가능한 최대치는 부분
          봉인이며, GATE 1 을 통과시키지 않습니다.
        </p>
      </section>

      <section aria-label="Lock 항목 9종">
        <h2 className="text-headline-sm text-text">Lock 항목</h2>
        <p className="mt-xs text-caption text-text-secondary">
          {String(report.items.length)}종 전부를 표시합니다. C1 에서 다루지 않는 항목도 목록에
          남기고 사유를 적습니다.
        </p>
        <div className="mt-md">
          <CoverageTable
            caption="Lock 항목별 상태와 범위"
            rows={report.items}
            rowKey={(item) => item.item}
            columns={[
              {
                key: "item",
                header: "항목",
                render: (item) => (
                  <div>
                    <div className="text-body-sm text-text">{item.item}</div>
                    <span className="text-caption text-text-secondary">{item.owner_part}</span>
                  </div>
                ),
              },
              {
                key: "status",
                header: "상태",
                render: (item) => (
                  <div className="flex flex-col gap-xs">
                    <StateChip
                      state={ITEM_STATE[item.status]}
                      label={item.status}
                      reasonCode={item.reason_code}
                    />
                    {/* A PARTIAL lock without its boundary is a contract violation, not
                        a cosmetic omission — it silently upgrades to a full lock. */}
                    {item.status === "PARTIAL" && item.scope_note.trim().length === 0 ? (
                      <StateChip state="violation" label="계약 위반 · 범위 한정 문구 누락" />
                    ) : null}
                  </div>
                ),
              },
              {
                key: "scope",
                header: "범위 한정 문구",
                render: (item) => (
                  <div className="flex flex-col gap-xs">
                    {/* Always expanded. */}
                    <span className="text-caption text-text">{item.scope_note}</span>
                    {item.reason_detail === undefined ? null : (
                      <span className="text-caption text-text-secondary">{item.reason_detail}</span>
                    )}
                  </div>
                ),
              },
              {
                key: "files",
                header: "정본 파일 대조",
                render: (item) =>
                  item.canonical_files === undefined || item.canonical_files.length === 0 ? (
                    <span className="text-caption text-text-secondary">—</span>
                  ) : (
                    <ul className="flex flex-col gap-xs">
                      {item.canonical_files.map((file) => (
                        <li key={file.path} className="flex flex-col gap-xs">
                          <code className="text-caption text-text-secondary">{file.path}</code>
                          <StateChip
                            state={VERIFICATION[file.verification].state}
                            label={VERIFICATION[file.verification].text}
                          />
                        </li>
                      ))}
                    </ul>
                  ),
              },
            ]}
          />
        </div>
      </section>

      <section aria-label="선행 조건">
        <h2 className="text-headline-sm text-text">선행 조건</h2>
        <p className="mt-xs text-caption text-text-secondary">
          무엇이 아직 열려 있는지가 봉인만큼 중요합니다. <code>met: null</code> 은 &quot;확인하지
          않았다&quot;이며 <code>false</code> 와 구별합니다.
        </p>
        <div className="mt-md">
          <CoverageTable
            caption="GATE 1 선행 조건 충족 여부"
            rows={report.unlocked_items}
            rowKey={(item) => item.id}
            columns={[
              {
                key: "id",
                header: "ID",
                render: (item) => <span className="text-body-sm text-text">{item.id}</span>,
              },
              {
                key: "title",
                header: "조건",
                render: (item) => <span className="text-body-sm text-text">{item.title}</span>,
              },
              {
                key: "met",
                header: "충족",
                render: (item) =>
                  item.met === null ? (
                    <StateChip state="not_run" label="확인하지 않음" />
                  ) : item.met ? (
                    <StateChip state="ok" label="충족" />
                  ) : (
                    <StateChip state="gap" label="미충족" />
                  ),
              },
              {
                key: "evidence",
                header: "근거",
                render: (item) => (
                  <span className="text-caption text-text-secondary">
                    {item.evidence === undefined ? "근거 미표기" : item.evidence}
                  </span>
                ),
              },
            ]}
          />
        </div>
      </section>
    </div>
  );
}
