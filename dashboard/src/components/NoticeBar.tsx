/**
 * Declared assumptions and limitations that travel with an artifact (contract R-8).
 *
 * The reasoning is the same as never filling a gap with zero: an assumption that is
 * not restated starts being read as a fact. So notices are pinned under the verdict
 * banner, never collapsed, never a toast, and never a modal — a notice the reader can
 * dismiss is a notice that stops existing after the first visit.
 *
 * ★ Zero notices renders nothing at all. Printing "가정 없음" would be a claim that no
 *   assumptions exist, which is a stronger statement than the artifact ever made.
 */
import type { Notice } from "@/lib/artifacts/types";
import { StateChip } from "./StateChip";
import type { VisualState } from "@/lib/format/state";

/** `notice.level` is its own vocabulary; map it onto the shared visual states. */
const LEVEL_STATE: Record<Notice["level"], VisualState> = {
  info: "unconnected",
  assumption: "unconnected",
  limitation: "gap",
  warning: "gap",
  failure: "violation",
};

const LEVEL_LABEL: Record<Notice["level"], string> = {
  info: "안내",
  assumption: "가정",
  limitation: "한계",
  warning: "경고",
  failure: "실패",
};

export function NoticeBar({ notices }: { notices: Notice[] }) {
  if (notices.length === 0) return null;

  return (
    <section aria-label="명시 가정과 한계" className="flex flex-col gap-sm">
      {notices.map((notice) => (
        <div
          key={notice.code}
          className="rounded-lg border border-border bg-surface px-base py-md"
        >
          <div className="flex flex-wrap items-center gap-xs">
            <StateChip state={LEVEL_STATE[notice.level]} label={LEVEL_LABEL[notice.level]} />
            {/* The raw code is shown next to the prose so a reader can trace it. */}
            <code className="text-caption text-text-secondary">{notice.code}</code>
          </div>
          <p className="mt-xs text-body-sm text-text">{notice.message}</p>
          {notice.reference === undefined ? null : (
            <p className="mt-xs text-caption text-text-secondary">근거: {notice.reference}</p>
          )}
        </div>
      ))}
    </section>
  );
}
