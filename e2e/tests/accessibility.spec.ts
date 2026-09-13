/**
 * Keyboard/AT checks that Andrew's own screenshot suite could not fully cover
 * (frontend.md documents C-2/C-11 as automated, but the skip-link-first-tab and
 * disabled-results-nav-not-focusable claims are re-verified here independently).
 */
import { test, expect } from "@playwright/test";
import { datasets } from "../datasets";

const real = datasets.find((d) => d.name === "real")!;

test.describe("accessibility (real results/)", () => {
  test("first Tab focuses the skip-to-content link", async ({ page }) => {
    await page.goto(`http://127.0.0.1:${real.port}/`, { waitUntil: "networkidle" });
    await page.keyboard.press("Tab");
    const focused = await page.evaluate(() => ({
      tag: document.activeElement?.tagName,
      href: (document.activeElement as HTMLAnchorElement | null)?.getAttribute("href"),
      text: document.activeElement?.textContent?.trim(),
    }));
    expect(focused.href).toBe("#main");
    expect(focused.text).toContain("건너뛰기");
  });

  test("disabled results-group sidebar items are not reachable by Tab and are announced with a reason", async ({ page }) => {
    await page.goto(`http://127.0.0.1:${real.port}/`, { waitUntil: "networkidle" });

    const disabledItems = await page.evaluate(() => {
      const nodes = Array.from(document.querySelectorAll('[aria-disabled="true"]'));
      return nodes.map((n) => ({
        tag: n.tagName,
        hasHref: n.hasAttribute("href"),
        tabIndex: (n as HTMLElement).tabIndex,
        ariaLabel: n.getAttribute("aria-label"),
      }));
    });

    expect(disabledItems.length, "expected the 8 result-view sidebar entries to be present and disabled").toBeGreaterThan(0);
    for (const item of disabledItems) {
      expect(item.hasHref, `disabled item ${JSON.stringify(item)} must not carry an href`).toBe(false);
      expect(item.tabIndex, `disabled item ${JSON.stringify(item)} must be removed from tab order`).toBe(-1);
    }
  });

  test("every state-chip glyph has an accessible name and the glyph itself is hidden from AT", async ({ page }) => {
    await page.goto(`http://127.0.0.1:${real.port}/quality`, { waitUntil: "networkidle" });

    const chips = await page.evaluate(() => {
      // StateChip.tsx: outer span carries aria-label, inner glyph span is aria-hidden.
      const glyphSpans = Array.from(document.querySelectorAll('span[aria-hidden="true"]')).filter((n) =>
        ["◉", "·", "○", "⚠", "⊘", "?", "✕", "✓", "◐"].includes(
          (n.textContent ?? "").trim(),
        ),
      );
      return glyphSpans.map((n) => {
        const withLabel = n.closest("[aria-label]");
        return { glyph: n.textContent?.trim(), hasAccessibleName: !!withLabel?.getAttribute("aria-label") };
      });
    });

    expect(chips.length, "expected at least one state-chip glyph on /quality").toBeGreaterThan(0);
    for (const c of chips) {
      expect(c.hasAccessibleName, `glyph "${c.glyph}" has no ancestor aria-label`).toBe(true);
    }
  });
});
