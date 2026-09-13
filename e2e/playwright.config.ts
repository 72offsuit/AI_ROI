/**
 * Independent QA harness for the observability dashboard (BATHOS W6 · Matthias / Role 15).
 *
 * This is NOT the product's own screenshot tool (dashboard/e2e/evidence.spec.ts, owned by
 * Andrew). It exists to re-verify the acceptance criteria against the built app's actual
 * HTTP/DOM/console output, independent of the implementer's own claims. QA owns this file
 * and everything under e2e/ — dashboard/** is read-only from here.
 *
 * Three datasets are served concurrently, each on its own port, each a real `next start`
 * against a real (or staged) results/ directory — no mocking of the read layer. See
 * datasets.ts for the exact list. Fixture staging reuses dashboard/scripts/stage-fixture.mjs
 * (read-only invocation; it only writes into dashboard/.fixtures/, which is gitignored
 * product scratch space) — run it once before `npx playwright test` if .fixtures/ is empty.
 */
import { defineConfig, devices } from "@playwright/test";
import { datasets, dashboardDirPath } from "./datasets";

export default defineConfig({
  testDir: "./tests",
  fullyParallel: false,
  retries: 0,
  workers: 1,
  reporter: [["list"], ["json", { outputFile: "./report.json" }]],
  outputDir: "./.playwright-artifacts",
  timeout: 30_000,
  use: {
    screenshot: "off",
    trace: "off",
    viewport: { width: 1440, height: 1000 },
  },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
  webServer: datasets.map((d) => ({
    command: `npx next start -p ${d.port}`,
    cwd: dashboardDirPath,
    url: `http://127.0.0.1:${d.port}/triggers`,
    env: {
      AIROI_RESULTS_DIR: d.resultsDir,
      AIROI_FIXTURE_MODE: d.fixtureMode ? "1" : "",
    },
    reuseExistingServer: false,
    timeout: 60_000,
  })),
});
