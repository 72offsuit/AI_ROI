/**
 * Smoke pass across every (dataset, route) pair: real HTTP 200, no console error during
 * hydration, and a full-page screenshot saved for visual QA (Pretendard rendering, layout,
 * contrast) — the part no DOM assertion can cover.
 */
import { test, expect } from "@playwright/test";
import { mkdir } from "node:fs/promises";
import { resolve } from "node:path";
import { datasets, ROUTES } from "../datasets";

const SHOTS_DIR = resolve(__dirname, "..", "screenshots");

for (const d of datasets) {
  test.describe(`pages · ${d.name}`, () => {
    for (const route of ROUTES) {
      test(`${route} loads clean`, async ({ page }) => {
        const errors: string[] = [];
        page.on("console", (msg) => {
          if (msg.type() === "error") errors.push(msg.text());
        });
        page.on("pageerror", (err) => errors.push(String(err)));

        const response = await page.goto(`http://127.0.0.1:${d.port}${route}`, { waitUntil: "networkidle" });
        expect(response?.status(), `${d.name}${route} HTTP status`).toBe(200);

        await page.evaluate(() => document.fonts.ready);

        await mkdir(resolve(SHOTS_DIR, d.name), { recursive: true });
        const safeName = route === "/" ? "index" : route.slice(1);
        await page.screenshot({ path: resolve(SHOTS_DIR, d.name, `${safeName}.png`), fullPage: true });

        expect(errors, `console/page errors on ${d.name}${route}:\n${errors.join("\n")}`).toEqual([]);
      });
    }
  });
}
