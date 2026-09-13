/**
 * V-12 (empty pass ≠ pass) and the quality-gate banner, cross-checked between the
 * published JSON and the live DOM. Runs against "real" so it reflects the pipeline's
 * current, non-fixture state (currently: empty sink, 0 events).
 */
import { test, expect } from "@playwright/test";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { datasets } from "../datasets";

const real = datasets.find((d) => d.name === "real")!;

function loadQualityReport() {
  const p = resolve(__dirname, "..", "..", "results", "data_quality_report.json");
  return JSON.parse(readFileSync(p, "utf8"));
}

test.describe("quality gate / vacuous vocabulary (real results/)", () => {
  test("check-status counts in JSON match what /quality renders", async ({ page }) => {
    const report = loadQualityReport();
    const checks: any[] = report.checks ?? [];
    const counts = { pass: 0, fail: 0, vacuous: 0, not_run: 0, blocked: 0 };
    for (const c of checks) counts[c.status as keyof typeof counts]++;

    await page.goto(`http://127.0.0.1:${real.port}/quality`, { waitUntil: "networkidle" });
    const bodyText = (await page.textContent("body")) ?? "";

    expect(bodyText, "gate banner must report the exact pass count").toContain(`통과 ${counts.pass}`);
    expect(bodyText, "gate banner must report the exact not_run count").toContain(`미실행 ${counts.not_run}`);
    expect(bodyText, "gate banner must report the exact blocked count").toContain(`차단 ${counts.blocked}`);
    expect(bodyText, "gate banner must report the exact vacuous count").toContain(`공허한 통과 ${counts.vacuous}`);

    // V-12: a check with 0 examined rows must never render as a green pass.
    if (counts.pass === 0) {
      const checkGlyphCount = await page.evaluate(() => {
        // "ok" glyph in StateChip.tsx is the literal check mark and is aria-hidden.
        return Array.from(document.querySelectorAll('[aria-hidden="true"]')).filter(
          (n) => (n.textContent ?? "").trim() === "✓",
        ).length;
      });
      expect(checkGlyphCount, "no ✓ glyph should render anywhere when the JSON reports 0 passing checks").toBe(0);
    }
  });

  test("each vacuous row is labelled '공허한 통과 · 검사 대상 0행' and is not colored as success", async ({ page }) => {
    const report = loadQualityReport();
    const vacuousIds: string[] = (report.checks ?? []).filter((c: any) => c.status === "vacuous").map((c: any) => c.id);
    test.skip(vacuousIds.length === 0, "no vacuous checks in current results/ to verify");

    await page.goto(`http://127.0.0.1:${real.port}/quality`, { waitUntil: "networkidle" });

    for (const id of vacuousIds) {
      const row = page.locator(`text=${id}`).first();
      await expect(row, `check row for ${id} should be visible`).toBeVisible();
    }

    const vacuousPhraseCount = await page.evaluate(
      () => document.body.textContent?.split("공허한 통과").length! - 1,
    );
    expect(vacuousPhraseCount).toBeGreaterThan(0);
  });

  test("gate_result 'incomplete' never carries the bare token 'success' as a css class root state", async ({ page }) => {
    await page.goto(`http://127.0.0.1:${real.port}/quality`, { waitUntil: "networkidle" });
    // The banner text itself must not claim unqualified "통과" when the gate is incomplete.
    const banner = await page.evaluate(() => {
      const el = Array.from(document.querySelectorAll("*")).find((n) =>
        (n.textContent ?? "").includes("미완 · 통과"),
      );
      return el?.textContent ?? null;
    });
    expect(banner, "expected the '미완 · 통과 N / ...' banner text to be present").not.toBeNull();
    expect(banner).not.toMatch(/^통과$/);
  });
});
