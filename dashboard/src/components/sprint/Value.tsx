/**
 * A value slot on the sprint screens.
 *
 * `null` means the file did not give a number. It renders as the words "계산 불가" in the
 * SAME typography as the number it replaces (DG-10) and in `text-secondary`, never
 * `text-muted`. The class `text-(--obs-absent-ink)` is also what e2e/evidence.spec.ts
 * scans for a stray "0".
 */
export const UNCOMPUTABLE_TEXT = "계산 불가";

export function Val({ text, className = "" }: { text: string | null; className?: string }) {
  if (text === null) {
    return <span className={`text-(--obs-absent-ink) ${className}`}>{UNCOMPUTABLE_TEXT}</span>;
  }
  return <span className={`text-(--obs-value-ink) ${className}`}>{text}</span>;
}

/** Plain-text fallback for strings (names, reasons) that may be missing. */
export function Txt({ text, className = "" }: { text: string | null | undefined; className?: string }) {
  if (typeof text !== "string" || text.length === 0) {
    return <span className={`text-(--obs-absent-ink) ${className}`}>미표기</span>;
  }
  return <span className={className}>{text}</span>;
}

/** Baseline vs proposed, as words — identity is never colour alone. */
export function KindTag({ kind }: { kind: string | null | undefined }) {
  const label = kind === "proposed" ? "제안" : kind === "baseline" ? "기준선" : "구분 미표기";
  const tone =
    kind === "proposed"
      ? "border-primary text-primary"
      : "border-border-control text-text-secondary";
  return (
    <span
      className={`inline-flex items-center rounded-(--obs-chip-radius) border px-(--obs-chip-padding-inline) text-caption ${tone}`}
    >
      {label}
    </span>
  );
}
