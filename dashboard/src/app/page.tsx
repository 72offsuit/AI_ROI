/**
 * Index. Reads index.json and nothing else.
 *
 * Order is fixed by ux-flow-map: identity -> verdict -> cycle notice -> notices ->
 * entry cards -> gap/impact -> refresh. The verdict comes before the cards so that the
 * reader learns the state of the run before being offered six places to click.
 *
 * The screen list is read from index.views rather than hardcoded, so a contract that
 * grows a view shows up here without a code change.
 */
import Link from "next/link";

import { loadIndex } from "@/lib/artifacts/read";
import { ArtifactGate } from "@/components/ArtifactGate";
import { NoticeBar } from "@/components/NoticeBar";
import { CycleNotice, ProvenanceBar, RefreshLink } from "@/components/ProvenanceBar";
import { StateChip } from "@/components/StateChip";
import { VerdictBanner } from "@/components/VerdictBanner";

// Re-read the files on every request. No fetch cache, no ISR: showing a stale artifact
// after a new publish would be another way of displaying a quietly wrong value.
export const dynamic = "force-dynamic";

export default async function IndexPage() {
  const result = await loadIndex();
  if (result.kind !== "ok") return <ArtifactGate result={result} />;
  const index = result.index;

  const statusOf = (artifact: string) =>
    index.artifacts.find((entry) => entry.artifact === artifact);

  /*
   * Routes this build actually implements.
   *
   * The index is the canonical screen<->artifact<->route binding and this page renders
   * whatever it says (dashboard-architecture §2.2) — which is right, but it means a
   * route the app does not have would render as a link that 404s. A dead link on the
   * entry screen reads as "that screen is broken", not "the contract and the app
   * disagree", so the disagreement is named instead.
   *
   * ★ The real artifact binds V4 to `/metrics` while every design document, the W2
   * fixtures and this app use `/kpi`. Reported, not silently renamed — picking a side
   * unilaterally would just move the disagreement somewhere less visible.
   */
  const IMPLEMENTED = new Set([
    "/ingestion",
    "/rejections",
    "/coverage",
    "/kpi",
    "/quality",
    "/freeze",
    "/triggers",
  ]);

  return (
    <div className="flex flex-col gap-lg">
      <header className="flex flex-wrap items-center justify-between gap-sm">
        <h1 className="text-headline-lg text-text">관측 대시보드</h1>
        <RefreshLink route="/" />
      </header>

      <ProvenanceBar envelope={index} />
      <VerdictBanner verdict={index.verdict} />
      <CycleNotice />
      <NoticeBar notices={index.notices} />

      {index.publish_result === "ok" ? null : (
        <section className="rounded-lg border border-border px-base py-md">
          <StateChip
            state={index.publish_result === "partial" ? "gap" : "violation"}
            label={`게시 결과 · ${index.publish_result}`}
          />
          <p className="mt-xs text-body-sm text-text">
            일부 산출물이 게시되지 않았습니다. 아래 카드에서 해당 화면의 상태를 확인하십시오.
          </p>
        </section>
      )}

      <section aria-label="화면 목록">
        <h2 className="text-headline-sm text-text">관측 화면</h2>
        <ul className="mt-md grid grid-cols-1 gap-base md:grid-cols-2 xl:grid-cols-3">
          {Object.entries(index.views).map(([key, view]) => {
            const entry = statusOf(view.artifact);
            const published = entry !== undefined && entry.status === "published";
            return (
              <li key={key} className="rounded-lg border border-border p-base">
                {IMPLEMENTED.has(view.route) ? (
                  <Link href={view.route} className="text-headline-sm text-primary underline">
                    {view.title}
                  </Link>
                ) : (
                  <span className="text-headline-sm text-text">{view.title}</span>
                )}
                <p className="mt-xs text-caption text-text-secondary">
                  {key} · {view.artifact} · {view.route}
                </p>
                {IMPLEMENTED.has(view.route) ? null : (
                  <div className="mt-sm">
                    <StateChip
                      state="violation"
                      label={`계약 위반 · 이 빌드에 ${view.route} 라우트가 없습니다`}
                    />
                    <p className="mt-xs text-caption text-text-secondary">
                      게시물과 화면이 라우트 이름에 대해 서로 다르게 알고 있습니다. 죽은 링크를
                      만들지 않기 위해 링크로 만들지 않았습니다.
                    </p>
                  </div>
                )}
                <div className="mt-sm">
                  {published ? (
                    <span className="text-caption text-text-secondary">게시됨</span>
                  ) : (
                    <StateChip
                      state={entry === undefined ? "violation" : "not_run"}
                      label={
                        entry === undefined
                          ? "artifacts 목록에 없습니다"
                          : `게시되지 않음 · ${entry.status}`
                      }
                      reasonCode={entry === undefined ? undefined : entry.reason_code}
                    />
                  )}
                </div>
              </li>
            );
          })}

          {/* Screens drawn without an artifact. Listed from index.static_views so the
              exception to the 1:1 view/artifact rule is explicit, not implicit. */}
          {(index.static_views === undefined ? [] : index.static_views).map((view) => (
            <li key={view.route} className="rounded-lg border border-border p-base">
              <Link href={view.route} className="text-headline-sm text-primary underline">
                {view.title}
              </Link>
              <p className="mt-xs text-caption text-text-secondary">정적 화면 · 게시물 없음</p>
              <div className="mt-sm">
                <StateChip state="planned" label="계획된 부재" reasonCode={view.reason_code} />
              </div>
              <p className="mt-xs text-caption text-text-secondary">{view.reason_detail}</p>
            </li>
          ))}
        </ul>
      </section>
    </div>
  );
}
