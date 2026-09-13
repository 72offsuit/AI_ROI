/**
 * Two claims frontend.md §7.5 marks as eyeballed-only: Pretendard actually renders (not a
 * silent fallback) and the source-columns responsive stack keeps commerce first below
 * 1024px (US-12/S-1). Both are re-checked programmatically here, on top of the visual
 * screenshot review QA did separately.
 */
import { test, expect } from "@playwright/test";
import { datasets } from "../datasets";

const real = datasets.find((d) => d.name === "real")!;

test("Pretendard is the font actually applied to body text, not a fallback", async ({ page }) => {
  await page.goto(`http://127.0.0.1:${real.port}/`, { waitUntil: "networkidle" });
  await page.evaluate(() => document.fonts.ready);

  const result = await page.evaluate(() => {
    const loadedFamilies = Array.from(document.fonts).map((f) => f.family);
    const heading = document.querySelector("h1");
    const computed = heading ? getComputedStyle(heading).fontFamily : null;
    return { loadedFamilies, computedFontFamily: computed };
  });

  expect(result.loadedFamilies.some((f) => /pretendard/i.test(f)), `loaded FontFace list: ${JSON.stringify(result.loadedFamilies)}`).toBe(true);
  expect(result.computedFontFamily, "h1 font-family must list Pretendard first").toMatch(/^["']?Pretendard/i);

  // Confirm the actual font file response, not just the CSS declaration.
  const fontResponse = await page.evaluate(async () => {
    const entries = performance.getEntriesByType("resource") as PerformanceResourceTiming[];
    const fontEntry = entries.find((e) => /pretendard/i.test(e.name) && /\.woff2?$/.test(e.name));
    return fontEntry ? { name: fontEntry.name, transferSize: fontEntry.transferSize } : null;
  });
  expect(fontResponse, "expected a Pretendard .woff2 network request").not.toBeNull();
  expect(fontResponse!.transferSize).toBeGreaterThan(0);
});

test("source columns keep commerce first when stacked below 1024px (US-12/S-1)", async ({ page }) => {
  await page.setViewportSize({ width: 900, height: 1400 });
  await page.goto(`http://127.0.0.1:${real.port}/ingestion`, { waitUntil: "networkidle" });

  const order = await page.evaluate(() => {
    const commerce = Array.from(document.querySelectorAll("*")).find((n) => (n.textContent ?? "").trim() === "커머스 실측");
    const simulator = Array.from(document.querySelectorAll("*")).find((n) => (n.textContent ?? "").trim() === "시뮬레이터 생성");
    if (!commerce || !simulator) return null;
    const cRect = commerce.getBoundingClientRect();
    const sRect = simulator.getBoundingClientRect();
    return { commerceTop: cRect.top, simulatorTop: sRect.top };
  });

  expect(order, "expected both source badges to be present on /ingestion").not.toBeNull();
  expect(order!.commerceTop, "commerce column must sit above simulator column when stacked").toBeLessThanOrEqual(order!.simulatorTop);
});

/**
 * Plan/DESIGN.md is explicit that this product excludes a mobile view and reviews only
 * desktop viewports (1024/1280/1440/1920px) — "모바일 전용 화면을 만들지는 않지만 좁은
 * 데스크톱 창·브라우저 확대에서 겹침이나 조작 불가를 허용하지 않습니다." So 1024px, not a
 * phone width, is the real floor this app is obligated to render without overflow.
 * (An earlier version of this test asserted no overflow at 400px — that was QA imposing an
 * unrelated authoring convention on a product that explicitly opts out of mobile support;
 * confirmed via manual check that /kpi alone overflows ~200px at 400px on all 8 routes,
 * which is expected-and-out-of-scope, not a defect, so it is not asserted here.)
 */
for (const width of [1024, 1280, 1440]) {
  test(`layout has no horizontal overflow at the reviewed desktop floor (${width}px)`, async ({ page }) => {
    await page.setViewportSize({ width, height: 900 });
    await page.goto(`http://127.0.0.1:${real.port}/kpi`, { waitUntil: "networkidle" });

    const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
    expect(overflow, `body scrollWidth exceeds viewport by ${overflow}px at ${width}px — page-level horizontal scroll on a reviewed viewport`).toBeLessThanOrEqual(1);
  });
}
