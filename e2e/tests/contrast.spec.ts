/**
 * C-10 — WCAG contrast for the 8 foreground/background combinations documented in
 * missing-state-spec.md §4.3. Frontend's own notes (frontend.md §7.5) mark this as
 * "실측 계산 안 함" (not automated) — this closes that gap.
 *
 * Colors are read live from the running app's computed CSS custom properties (not
 * retyped from the design doc), so this also catches drift between the doc and the
 * shipped tokens.generated.css.
 */
import { test, expect } from "@playwright/test";
import { datasets } from "../datasets";

const real = datasets.find((d) => d.name === "real")!;

/** Browsers may normalize `#FFFFFF` to the shorthand `#fff` when read back via getComputedStyle. */
function expandHex(hex: string): string {
  const h = hex.replace("#", "");
  if (h.length === 3) {
    return `#${h[0]}${h[0]}${h[1]}${h[1]}${h[2]}${h[2]}`;
  }
  return `#${h}`;
}

function srgbToLinear(c: number): number {
  const s = c / 255;
  return s <= 0.03928 ? s / 12.92 : ((s + 0.055) / 1.055) ** 2.4;
}

function relativeLuminance(hex: string): number {
  const h = hex.replace("#", "");
  const r = parseInt(h.slice(0, 2), 16);
  const g = parseInt(h.slice(2, 4), 16);
  const b = parseInt(h.slice(4, 6), 16);
  return 0.2126 * srgbToLinear(r) + 0.7152 * srgbToLinear(g) + 0.0722 * srgbToLinear(b);
}

function contrastRatio(hexA: string, hexB: string): number {
  const l1 = relativeLuminance(hexA);
  const l2 = relativeLuminance(hexB);
  const [lighter, darker] = l1 >= l2 ? [l1, l2] : [l2, l1];
  return (lighter + 0.05) / (darker + 0.05);
}

const PAIRS: Array<{ label: string; fg: string; bg: string; docClaim: number }> = [
  { label: "text-secondary on background (em dash)", fg: "--ds-colors-text-secondary", bg: "--ds-colors-background", docClaim: 7.82 },
  { label: "warning on warning-surface (blocked chip)", fg: "--ds-colors-warning", bg: "--ds-colors-warning-surface", docClaim: 6.62 },
  { label: "warning on background (provisional outline)", fg: "--ds-colors-warning", bg: "--ds-colors-background", docClaim: 6.85 },
  { label: "error on error-surface (violation chip)", fg: "--ds-colors-error", bg: "--ds-colors-error-surface", docClaim: 5.91 },
  { label: "error on background (not_run outline)", fg: "--ds-colors-error", bg: "--ds-colors-background", docClaim: 6.47 },
  { label: "info on info-surface (unconnected/vacuous chip)", fg: "--ds-colors-info", bg: "--ds-colors-info-surface", docClaim: 6.5 },
  { label: "text-muted on surface-muted (planned chip)", fg: "--ds-colors-text-muted", bg: "--ds-colors-surface-muted", docClaim: 4.89 },
  { label: "success on success-surface (ok gate banner)", fg: "--ds-colors-success", bg: "--ds-colors-success-surface", docClaim: 6.81 },
];

test("all 8 documented state-color pairs meet WCAG 4.5:1 for normal text, computed from live tokens", async ({ page }) => {
  await page.goto(`http://127.0.0.1:${real.port}/kpi`, { waitUntil: "networkidle" });

  const resolved = await page.evaluate((vars: string[]) => {
    const style = getComputedStyle(document.documentElement);
    const out: Record<string, string> = {};
    for (const v of vars) out[v] = style.getPropertyValue(v).trim();
    return out;
  }, Array.from(new Set(PAIRS.flatMap((p) => [p.fg, p.bg]))));

  const mismatches: string[] = [];
  const failures: string[] = [];

  for (const pair of PAIRS) {
    const rawFg = resolved[pair.fg];
    const rawBg = resolved[pair.bg];
    expect(rawFg, `${pair.fg} must resolve to a hex color`).toMatch(/^#([0-9a-fA-F]{3}|[0-9a-fA-F]{6})$/);
    expect(rawBg, `${pair.bg} must resolve to a hex color`).toMatch(/^#([0-9a-fA-F]{3}|[0-9a-fA-F]{6})$/);
    const fgHex = expandHex(rawFg);
    const bgHex = expandHex(rawBg);

    const actual = contrastRatio(fgHex, bgHex);
    if (actual < 4.5) failures.push(`${pair.label}: ${actual.toFixed(2)}:1 < 4.5:1 required`);
    if (Math.abs(actual - pair.docClaim) > 0.05) {
      mismatches.push(`${pair.label}: doc claims ${pair.docClaim}:1, live tokens compute to ${actual.toFixed(2)}:1`);
    }
  }

  // Hard gate: nothing may fall below the accessibility floor.
  expect(failures, failures.join("\n")).toEqual([]);

  // Soft signal, not a failure: report doc/reality drift so it can be corrected upstream.
  if (mismatches.length > 0) {
    test.info().annotations.push({
      type: "contrast-doc-drift",
      description: mismatches.join(" | "),
    });
  }
});
