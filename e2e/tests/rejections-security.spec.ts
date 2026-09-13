/**
 * V2 must show which fields were rejected without ever leaking the offending values
 * themselves (frontend.md §9 claims this was closed by removing `offending_values` from
 * the TypeScript type entirely). Re-verified here against the live DOM using the
 * commerce-connected fixture, whose sample rejections carry values that would be an
 * obvious leak if they ever reached the page: a raw customer_id ("test-user-1"), a raw
 * page_type ("main"), and a raw UTC timestamp.
 */
import { test, expect } from "@playwright/test";
import { datasets } from "../datasets";

const connected = datasets.find((d) => d.name === "commerce-connected")!;

const SECRET_VALUES = ["test-user-1", "2026-09-17T23:41:02.000Z"];

test("no offending value from the rejection samples appears anywhere in /rejections HTML", async ({ page }) => {
  const response = await page.goto(`http://127.0.0.1:${connected.port}/rejections`, { waitUntil: "networkidle" });
  expect(response?.status()).toBe(200);

  const html = await page.content();
  for (const secret of SECRET_VALUES) {
    expect(html, `offending value "${secret}" must not leak into /rejections markup`).not.toContain(secret);
  }

  // The field name IS allowed to appear (that's the point — name yes, value no).
  const bodyText = (await page.textContent("body")) ?? "";
  expect(bodyText).toContain("customer_id");
});
