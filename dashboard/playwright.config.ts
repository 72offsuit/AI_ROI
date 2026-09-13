/**
 * Screenshot evidence capture for the observability views.
 *
 * This config exists for one job: produce the visual proof that US-11 ~ US-14 and the
 * USP-1 representative scene require. It is not a test gate — C1 deliberately does not
 * add a Node CI gate, so nothing here runs automatically.
 *
 * Shape and version follow Ecommerce_Service/playwright.config.ts (@playwright/test
 * ^1.63.0, single Desktop Chrome project, webServer auto-start) so the two repositories
 * do not drift into different Playwright conventions. Only what must differ differs:
 *
 *   - port 3001, not 3100 (3000 is the commerce app, 3100 is its e2e server; all three
 *     can run side by side)
 *   - the server is fed a staged fixture through AIROI_RESULTS_DIR, because the
 *     measurement layer has not published real artifacts yet (M-06)
 *   - AIROI_FIXTURE_MODE=1, which makes every page carry the
 *     "표본 데이터 — 실측이 아닙니다" badge. That badge is non-negotiable: sample input
 *     must never be able to pass for measured data.
 *
 * Which fixture is captured is chosen by AIROI_FIXTURE (see the `shots:*` npm scripts).
 */
import { defineConfig, devices } from "@playwright/test";
import { resolve } from "node:path";

/**
 * Which artifacts to photograph, and whether they are sample input.
 *
 *   AIROI_FIXTURE=empty-sink|commerce-connected   staged example artifacts
 *   AIROI_FIXTURE=real                            the repository's own results/
 *   AIROI_SHOTS_RESULTS=<abs path>                any other published results/ dir
 *
 * ★ The sample-data badge is driven by whether the INPUT was synthetic, not by whether
 *   the pipeline was real. `results/` is a genuine publish of a genuine (empty) sink, so
 *   it carries no badge. Everything else here is fed hand-made events — the pipeline is
 *   real but the input is not, and that is exactly what the badge says.
 */
const fixture = process.env.AIROI_FIXTURE ?? "empty-sink";
const override = process.env.AIROI_SHOTS_RESULTS;
const isRealInput = fixture === "real";
const resultsDir =
  typeof override === "string" && override.trim().length > 0
    ? resolve(override.trim())
    : isRealInput
      ? resolve(__dirname, "..", "results")
      : resolve(__dirname, ".fixtures", fixture, "results");
const baseURL = "http://127.0.0.1:3001";

export default defineConfig({
  testDir: "./e2e",
  testMatch: "**/*.spec.ts",
  retries: 0,
  // One worker: every spec drives the same single server reading one fixture.
  workers: 1,
  reporter: [["list"]],
  // Evidence is the deliverable, so it goes in a named folder rather than
  // test-results/, which Playwright wipes between runs.
  outputDir: `./.playwright/${fixture}`,
  metadata: { fixture, resultsDir, sampleInput: !isRealInput },
  use: {
    baseURL,
    // 1440px = --ds-spacing-dashboard-max, the width the layout is designed for.
    viewport: { width: 1440, height: 1000 },
    screenshot: "off",
    trace: "off",
  },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
  webServer: {
    // `npm start` runs `next start --port 3001`; prebuild already generated the tokens.
    command: "npm run build && npm start",
    // /triggers renders without any artifact, so it is ready even for an empty fixture.
    url: `${baseURL}/triggers`,
    env: {
      AIROI_RESULTS_DIR: resultsDir,
      // ★ On whenever the input was synthetic. Off only for the repository's own
      // results/, which is a real publish of a real (empty) sink.
      AIROI_FIXTURE_MODE: isRealInput ? "" : "1",
    },
    reuseExistingServer: false,
    timeout: 180_000,
  },
});
