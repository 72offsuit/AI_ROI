/**
 * V7 — monitoring triggers (PRD §71). Static: there is no artifact behind this screen.
 *
 * ★ All five triggers are conditioned on a change (↑ / ↓), and a change needs two
 *   points in time. C1 publishes a single snapshot and has no artifact-history
 *   contract, so zero of the five can fire. That is the finding, and this screen states
 *   it as a table of planned absences.
 *
 * ★ No alert UI, no threshold inputs, no toggles. A control that cannot do anything
 *   teaches the reader that the screen is wired up when it is not. The one trigger with
 *   a computable input is shown as partial, with its remaining blockers spelled out —
 *   not as something that nearly works.
 *
 * ★ index.json lists this route in `static_views`, which is what makes it an explicit
 *   exception to the one-screen-one-artifact rule rather than an undocumented gap.
 */
import { loadIndex } from "@/lib/artifacts/read";
import { ArtifactGate } from "@/components/ArtifactGate";
import { CoverageTable } from "@/components/CoverageTable";
import { ProvenanceBar, RefreshLink } from "@/components/ProvenanceBar";
import { StateChip } from "@/components/StateChip";
import type { VisualState } from "@/lib/format/state";

export const dynamic = "force-dynamic";

interface Trigger {
  name: string;
  state: VisualState;
  verdict: string;
  blockers: string[];
}

/**
 * PRD §71, verbatim in scope and outcome. Held as a screen constant because there is
 * no artifact to read it from — and that absence is itself declared in
 * index.static_views, so it is visible rather than assumed.
 */
const TRIGGERS: Trigger[] = [
  {
    name: "Churn ↑ → Segment Analysis",
    state: "planned",
    verdict: "계산 불가 · 이후 사이클",
    blockers: ["이탈 임계값 미확정", "Segment 모델 없음", "게시물 이력 없음"],
  },
  {
    name: "Retention ↓ → Cohort Analysis",
    state: "planned",
    verdict: "계산 불가 · 이후 사이클",
    blockers: ["코호트 기준 미확보 (signup_date 부재)", "게시물 이력 없음"],
  },
  {
    name: "AI ROI < Rule Baseline → Strategy Review",
    state: "planned",
    verdict: "계산 불가 · 비교 전략 없음",
    blockers: ["비교 전략 2종 필요", "모델 산출물 없음", "게시물 이력 없음"],
  },
  {
    name: "Marketing Cost ↑ → Target Threshold Review",
    // The only one with any computable input — shown as partial, never as working.
    state: "gap",
    verdict: "부분 · 임계값 미확정",
    blockers: [
      "marketing_cost 는 계산 가능",
      "임계 C_rule · B 는 GATE 2 확정 항목",
      "게시물 이력 없음 → 증가 여부를 판정할 수 없음",
    ],
  },
  {
    name: "Uplift ↓ → Treatment Policy Review",
    state: "planned",
    verdict: "계산 불가 · 모델 산출물 없음",
    blockers: ["Uplift 모델 산출물 없음", "게시물 이력 없음"],
  },
];

export default async function TriggersPage() {
  // Read only for provenance and to confirm this route is a declared static view.
  const result = await loadIndex();
  const declared =
    result.kind === "ok" &&
    (result.index.static_views === undefined
      ? []
      : result.index.static_views
    ).some((view) => view.route === "/triggers");

  return (
    <div className="flex flex-col gap-lg">
      <header className="flex flex-wrap items-center justify-between gap-sm">
        <h1 className="text-headline-lg text-text">모니터링 트리거</h1>
        <RefreshLink route="/triggers" />
      </header>

      {result.kind === "ok" ? (
        <ProvenanceBar envelope={result.index} />
      ) : (
        // The table below does not depend on an artifact, so it is still drawn; only
        // the provenance strip is replaced by the explanation of what is missing.
        <ArtifactGate result={result} />
      )}

      <section aria-label="트리거 요약" className="rounded-lg border border-border px-base py-lg">
        <StateChip state="planned" label="PRD §71 트리거 5종 · C1 작동 0종" />
        <p className="mt-sm text-body-sm text-text">
          5종 전부가 <strong>변화</strong>(↑ / ↓)를 전제합니다. 변화에는 비교 기준이 필요하고 C1
          게시물은 단일 시점 스냅샷입니다.
        </p>
        <p className="mt-xs text-caption text-text-secondary">
          공통 선행 조건: 게시물 이력 보관. 경보 UI · 임계 입력 · 토글을 만들지 않습니다 — 작동하지
          않는 컨트롤을 두지 않습니다.
        </p>
        {declared ? null : (
          <div className="mt-sm">
            <StateChip
              state="violation"
              label="계약 위반 · index.static_views 에 /triggers 가 선언되어 있지 않습니다"
            />
          </div>
        )}
      </section>

      <section aria-label="트리거 5종">
        <CoverageTable
          caption="PRD §71 트리거와 각 트리거의 차단 사유"
          rows={TRIGGERS}
          rowKey={(trigger) => trigger.name}
          columns={[
            {
              key: "name",
              header: "트리거",
              render: (trigger) => <span className="text-body-sm text-text">{trigger.name}</span>,
            },
            {
              key: "verdict",
              header: "상태",
              render: (trigger) => <StateChip state={trigger.state} label={trigger.verdict} />,
            },
            {
              key: "blockers",
              header: "차단",
              render: (trigger) => (
                <ul className="text-caption text-text-secondary">
                  {trigger.blockers.map((blocker) => (
                    <li key={blocker}>· {blocker}</li>
                  ))}
                </ul>
              ),
            },
          ]}
        />
      </section>
    </div>
  );
}
