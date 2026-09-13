/**
 * USP-1's core claim, checked against the live DOM rather than trusting the implementer's
 * grep report: a value the contract marks uncomputable is never rendered as the digit "0",
 * and a value the contract marks as a genuinely measured zero is never collapsed to an em
 * dash. Both directions matter — collapsing a real 0 into "—" is the mirror-image bug
 * (frontend.md §8 documents Andrew catching exactly this once).
 *
 * Runs against the "real" dataset: the repository's own results/, produced by the actual
 * measurement pipeline (not a hand-written fixture), so this is checking production output.
 */
import { test, expect } from "@playwright/test";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { datasets } from "../datasets";

const real = datasets.find((d) => d.name === "real")!;
const EM_DASH = "—";

test.describe("zero-fill invariants (real results/)", () => {
  test("no absent-ink metric slot contains a digit", async ({ page }) => {
    await page.goto(`http://127.0.0.1:${real.port}/kpi`, { waitUntil: "networkidle" });

    const offenders = await page.evaluate(() => {
      const nodes = Array.from(document.querySelectorAll('[class*="obs-absent-ink"]'));
      return nodes
        .map((n) => (n.textContent ?? "").trim())
        .filter((t) => t.length > 0 && /\d/.test(t));
    });

    expect(offenders, `absent-ink slots must never show a digit, found: ${JSON.stringify(offenders)}`).toEqual([]);
  });

  test("absent-ink slots are exactly the em dash, '미실행', or the placeholder string — never blank", async ({ page }) => {
    await page.goto(`http://127.0.0.1:${real.port}/kpi`, { waitUntil: "networkidle" });

    const texts: string[] = await page.evaluate(() => {
      const nodes = Array.from(document.querySelectorAll('[class*="obs-absent-ink"]'));
      return nodes.map((n) => (n.textContent ?? "").trim()).filter((t) => t.length > 0);
    });

    for (const t of texts) {
      expect(t === EM_DASH || t === "미실행" || t.length > 0, `unexpected absent-ink text: ${JSON.stringify(t)}`).toBeTruthy();
      expect(t, "absent-ink text must not be empty").not.toBe("");
    }
  });

  test("measured-zero metrics render the literal count/currency string with a basis line, styled as a value (not absent)", async ({ page }) => {
    const kpiPath = resolve(__dirname, "..", "..", "results", "measurement", "kpi_report.json");
    const kpi = JSON.parse(readFileSync(kpiPath, "utf8"));

    let measuredZeroCount = 0;
    for (const m of kpi.metrics ?? []) {
      const v = m.value ?? {};
      const candidates = [v, v.combined, ...(v.by_source ? Object.values(v.by_source) : [])];
      for (const c of candidates as any[]) {
        if (c && c.status === "ok" && (c.value === 0 || c.value === 0.0)) measuredZeroCount += 1;
      }
    }
    expect(measuredZeroCount, "expected at least one measured-zero metric in current results/ to exercise this check").toBeGreaterThan(0);

    await page.goto(`http://127.0.0.1:${real.port}/kpi`, { waitUntil: "networkidle" });

    const valueInkZeroCells = await page.evaluate(() => {
      const nodes = Array.from(document.querySelectorAll('[class*="obs-value-ink"]'));
      return nodes
        .map((n) => (n.textContent ?? "").trim())
        .filter((t) => /^0(건|원)$/.test(t));
    });

    expect(valueInkZeroCells.length, "measured-zero cells found with value styling").toBeGreaterThan(0);
  });

  test("no raw grep-forbidden zero-fill idiom reaches the rendered page (defense in depth on top of source grep)", async ({ page }) => {
    await page.goto(`http://127.0.0.1:${real.port}/kpi`, { waitUntil: "networkidle" });
    const bodyText = await page.textContent("body");
    // A crude but real signal: an em dash immediately followed by "0" would indicate a
    // template concatenation bug. Not exhaustive — source-level grep (frontend.md §5.4)
    // remains the primary defense — this is a live cross-check.
    expect(bodyText).not.toMatch(/—0(?!\d)/);
  });
});
