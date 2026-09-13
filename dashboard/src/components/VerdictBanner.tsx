/**
 * Exactly one verdict, at the top of the index screen.
 *
 * ★ The publisher decides which one. index.verdict already carries the winning
 *   headline_code, its detail sentence and every count. The screen only maps a code to
 *   Korean copy. If the screen re-ranked or re-counted, there would be two rankings of
 *   the same truth and they would drift — and tallying counts is itself a calculation
 *   (DB-012); "just adding up" is not an exception to that.
 *
 * ★ Zero collected events is not a warning (F-3). As of 2026-09-11 an empty sink is
 *   the correct state of this project, and painting the normal state red is how real
 *   warnings get ignored.
 */
import Link from "next/link";

import type { HeadlineCode, Verdict } from "@/lib/artifacts/types";
import type { VisualState } from "@/lib/format/state";
import { StateChip } from "./StateChip";

/**
 * Code -> copy. The contract supplies the code; the wording belongs to the screen,
 * the same split used for reason codes.
 *
 * `REJECTED_EVENTS` is rank 4, added by M-06 (lead ruling B-11). Before it existed a
 * run with clean quality checks and 217 rejected events reported ALL_CLEAR. The entry
 * is kept here even while the schema still lists seven codes: an index.json that never
 * emits it never reaches this branch, and the day it does the screen is already right.
 */
const HEADLINE: Record<HeadlineCode, { state: VisualState; text: string; route?: string }> = {
  CONTRACT_VIOLATION: {
    state: "violation",
    text: "계약 위반 — 게시물이 기준을 누락했습니다",
  },
  QUALITY_VIOLATION: { state: "violation", text: "데이터 품질 위반", route: "/quality" },
  FREEZE_MISMATCH: {
    state: "violation",
    text: "봉인 불일치 — 정본 파일이 Lock 시점과 다릅니다",
    route: "/freeze",
  },
  REJECTED_EVENTS: { state: "violation", text: "거부된 이벤트가 있습니다", route: "/rejections" },
  CHECKS_NOT_RUN: {
    state: "not_run",
    text: "데이터 품질 검사 미실행 — 통과로 볼 수 없습니다",
    route: "/quality",
  },
  SINK_EMPTY: {
    // info, not warning: an empty sink is today's expected state (F-3).
    state: "unconnected",
    text: "수집된 이벤트 0건 — 커머스 미연결 · 시뮬레이터 미구현",
    route: "/ingestion",
  },
  METRICS_UNAVAILABLE: { state: "gap", text: "계산 불가 지표가 있습니다", route: "/kpi" },
  ALL_CLEAR: { state: "ok", text: "수집 중 · 계약 위반 0건 · 거부 0건" },
};

const COUNT_LABEL: Record<keyof Verdict["counts"], string> = {
  quality_violations: "품질 위반",
  checks_not_run: "미실행 검사",
  checks_blocked: "차단된 검사",
  metrics_unavailable: "계산 불가 지표",
  metrics_not_run: "미실행 지표",
  schema_gaps: "스키마 공백",
  lock_items_pending: "선행조건 미충족",
  freeze_mismatch: "봉인 불일치",
  rejected_events: "거부 이벤트",
};

export function VerdictBanner({ verdict }: { verdict: Verdict }) {
  const headline = HEADLINE[verdict.headline_code];
  // An unknown code is surfaced rather than defaulted: a contract that grew a value
  // this build does not know about is a fact the reader needs.
  const resolved =
    headline === undefined
      ? {
          state: "violation" as VisualState,
          text: `알 수 없는 판정 코드 — ${verdict.headline_code}`,
          route: undefined,
        }
      : headline;

  return (
    <section
      aria-label="게시물 판정"
      className="rounded-lg border border-border bg-surface px-base py-lg"
    >
      <div className="flex flex-wrap items-center justify-between gap-sm">
        <div className="flex flex-wrap items-center gap-sm">
          <StateChip state={resolved.state} label={resolved.text} />
        </div>
        {resolved.route === undefined ? null : (
          <Link href={resolved.route} className="text-label-md text-primary underline">
            해당 화면으로 이동
          </Link>
        )}
      </div>

      {/* headline_detail carries the numbers behind the verdict. Rendering the code
          without it would leave the reader with a label and no evidence. */}
      <p className="mt-sm text-body-sm text-text">{verdict.headline_detail}</p>

      <dl className="mt-md grid grid-cols-2 gap-sm md:grid-cols-4">
        {(Object.keys(COUNT_LABEL) as (keyof Verdict["counts"])[]).map((key) => (
          <div key={key}>
            <dt className="text-caption text-text-secondary">{COUNT_LABEL[key]}</dt>
            {/* Counts come straight from the contract; the screen prints, never sums. */}
            <dd className="text-table-number text-text">{String(verdict.counts[key])}</dd>
          </div>
        ))}
      </dl>
    </section>
  );
}
