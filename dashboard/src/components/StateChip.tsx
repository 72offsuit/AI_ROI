/**
 * The status chip, and the ONLY file in this app that contains glyph literals.
 *
 * Two reasons for that concentration:
 *
 *  1. `gap`, `env_blocked` and `provisional` all resolve to the same warning colour.
 *     They are told apart by three things at once — value slot (number vs em dash),
 *     outline (filled / solid / dashed) and glyph. Drop the glyph and the first two
 *     survive greyscale printing and screenshot downscaling but the third does not,
 *     so gap and env_blocked become indistinguishable. DESIGN.md also forbids
 *     carrying meaning by colour alone.
 *
 *  2. Keeping the literals here turns "does every state have a glyph?" from an
 *     eyeball review into two greps: no glyph literal outside this file, and one
 *     entry per state inside it. The difficulty of that check was an artefact of
 *     where the characters lived, not of the design.
 *
 * Every glyph is announced: `aria-label` carries the full sentence and the glyph
 * itself is `aria-hidden`, so a screen reader hears the meaning once, not a symbol.
 */
import type { ReasonCode } from "@/lib/artifacts/types";
import { REASON_LABEL, STATE_LABEL, type VisualState } from "@/lib/format/state";

/** ★ Glyph literals live here and nowhere else. */
const GLYPH: Record<VisualState, string> = {
  available: "",
  provisional: "◐",
  planned: "·",
  unconnected: "○",
  gap: "⚠",
  env_blocked: "⊘",
  not_run: "?",
  violation: "✕",
  ok: "✓",
};

/**
 * Colour/shape per state, written as literal class strings so Tailwind's source
 * scanner can see them. The `(--obs-*)` values are aliases of Plan/DESIGN.md tokens —
 * there is no colour literal anywhere in this app (DG-17).
 */
const STATE_CLASS: Record<VisualState, string> = {
  available: "text-(--obs-value-ink)",
  provisional:
    "text-(--obs-provisional-ink) bg-(--obs-provisional-surface) border border-solid border-(--obs-provisional-border)",
  planned: "text-(--obs-planned-ink) bg-(--obs-planned-surface) border border-transparent",
  unconnected:
    "text-(--obs-unconnected-ink) bg-(--obs-unconnected-surface) border border-transparent",
  gap: "text-(--obs-gap-ink) bg-(--obs-gap-surface) border border-transparent",
  env_blocked:
    "text-(--obs-envblocked-ink) bg-(--obs-envblocked-surface) border border-dashed border-(--obs-envblocked-border)",
  not_run:
    "text-(--obs-notrun-ink) bg-(--obs-notrun-surface) border border-solid border-(--obs-notrun-border)",
  violation: "text-(--obs-violation-ink) bg-(--obs-violation-surface) border border-transparent",
  ok: "text-(--obs-ok-ink) bg-(--obs-ok-surface) border border-transparent",
};

/* Chips wrap instead of clipping: at 200% zoom a fixed-height chip would cut its own
   text, and the reason code is the part that gets cut first. */
const CHIP_BASE =
  "inline-flex max-w-full items-center gap-xs rounded-(--obs-chip-radius) px-(--obs-chip-padding-inline) py-xs text-caption whitespace-normal break-keep obs-transition";

export function StateChip({
  state,
  label,
  reasonCode,
}: {
  state: VisualState;
  /** Overrides the default copy when the screen has a more specific sentence. */
  label?: string;
  /** Rendered verbatim next to the Korean copy: prose is for people, the code is for tracing (U-6). */
  reasonCode?: ReasonCode;
}) {
  const glyph = GLYPH[state];
  const text = label === undefined ? STATE_LABEL[state] : label;
  const spoken = reasonCode === undefined ? text : `${text} · 사유 코드 ${reasonCode}`;

  return (
    <span className={`${CHIP_BASE} ${STATE_CLASS[state]}`} aria-label={spoken} role="img">
      {glyph.length > 0 ? (
        <span aria-hidden="true" className="leading-none">
          {glyph}
        </span>
      ) : null}
      <span aria-hidden="true">{text}</span>
      {reasonCode === undefined ? null : (
        <code aria-hidden="true" className="font-mono opacity-100">
          {reasonCode}
        </code>
      )}
    </span>
  );
}

/** Human copy for a reason code, with the raw code always shown beside it. */
export function reasonSentence(reasonCode: ReasonCode | undefined): string {
  if (reasonCode === undefined) return "사유 미표기";
  return REASON_LABEL[reasonCode];
}

/* ── Auxiliary chips — combine with a state chip, never replace one ───────── */

const AUX_BASE =
  "inline-flex max-w-full items-center gap-xs rounded-(--obs-chip-radius) px-(--obs-chip-padding-inline) py-xs text-caption whitespace-normal break-keep";

/** `derived: true` — a value produced by a rule, not a stored fact. */
export function DerivedChip({ derivation }: { derivation?: string }) {
  const detail = derivation === undefined ? "유도 규칙 미표기" : derivation;
  return (
    <span className={`${AUX_BASE} text-(--obs-derived-ink)`} aria-label={`유도값 · ${detail}`}>
      <span aria-hidden="true">유도값</span>
    </span>
  );
}

/**
 * A precision ceiling that does not go away on its own.
 * Distinct from `provisional`: an unconfirmed value becomes correct once a parameter
 * is fixed, whereas a limited one stays an undercount until new events exist (V-7).
 */
export function LimitChip({ note }: { note: string }) {
  return (
    <span className={`${AUX_BASE} text-(--obs-limit-ink)`} aria-label={`한계 · ${note}`}>
      <span aria-hidden="true">한계 · {note}</span>
    </span>
  );
}

/** Source totals. Shown with the word, never as a bare number (R-7 / S-3). */
export function CombinedChip() {
  return (
    <span className={`${AUX_BASE} text-(--obs-combined-ink)`} aria-label="출처 합산 값">
      <span aria-hidden="true">합산</span>
    </span>
  );
}

/**
 * ★ Non-negotiable whenever the rendered artifacts are sample input.
 * Making sample data look like measured data is precisely the behaviour this whole
 * design forbids, so the badge is not conditional on anything but the fact itself.
 */
export function FixtureBadge() {
  return (
    <span
      className={`${AUX_BASE} text-(--obs-fixture-ink) bg-(--obs-fixture-surface)`}
      aria-label="표본 데이터 — 실측이 아닙니다"
    >
      <span aria-hidden="true">표본 데이터 — 실측이 아닙니다</span>
    </span>
  );
}

/** `status: "vacuous"` — the check ran and examined nothing. Never green, never ✓. */
export function VacuousChip() {
  return (
    <span
      className={`${AUX_BASE} text-(--obs-vacuous-ink) bg-(--obs-vacuous-surface)`}
      aria-label="공허한 통과 · 검사 대상 0행"
    >
      <span aria-hidden="true">공허한 통과 · 검사 대상 0행</span>
    </span>
  );
}
