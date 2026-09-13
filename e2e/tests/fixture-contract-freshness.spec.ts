/**
 * QA finding (2026-09-14, Matthias/W6): the committed example fixtures under
 * .agent-team/04-architecture/examples/{empty-sink,commerce-connected}/ predate the M-06
 * contract change that added `value_formatted` (required on every ok/unconfirmed metric
 * value — see docs/contracts/measurement-publish/v1/CHANGELOG.md). Following the exact
 * reproduction steps documented in frontend.md §1.1 / story d-02 §8.1
 * (`node scripts/stage-fixture.mjs <name>` then load the page) therefore renders a
 * spurious "✕ 계약 위반 · value_formatted 가 게시물에 없습니다" banner that does NOT
 * reflect the real pipeline — confirmed separately that the actual results/ directory
 * (produced by `python -m src.measurement.publish`) carries value_formatted on all 18
 * computed metrics.
 *
 * This is NOT a dashboard defect — read.ts is correctly enforcing the contract it was
 * built against — it is committed test-fixture drift under 04-architecture/examples/,
 * which is architecture-owned, not dashboard-owned or QA-owned. Left RED deliberately:
 * flip to green is the acceptance signal once the fixtures are regenerated against the
 * current contract (see qa-summary.md for the full writeup).
 */
import { test, expect } from "@playwright/test";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";

const EXAMPLES_ROOT = resolve(__dirname, "..", "..", ".agent-team", "04-architecture", "examples");

function collectOkOrUnconfirmedWithoutFormatted(node: any, hits: string[], path = ""): void {
  if (node && typeof node === "object") {
    if (!Array.isArray(node) && (node.status === "ok" || node.status === "unconfirmed") && !("value_formatted" in node)) {
      hits.push(path);
    }
    for (const [k, v] of Object.entries(node)) {
      collectOkOrUnconfirmedWithoutFormatted(v, hits, `${path}.${k}`);
    }
  }
}

for (const fixture of ["empty-sink", "commerce-connected"]) {
  test(`fixture "${fixture}" kpi_report.json satisfies the current value_formatted requirement`, () => {
    const kpi = JSON.parse(readFileSync(resolve(EXAMPLES_ROOT, fixture, "kpi_report.json"), "utf8"));
    const hits: string[] = [];
    collectOkOrUnconfirmedWithoutFormatted(kpi, hits);

    expect(
      hits,
      `Stale fixture: these ok/unconfirmed nodes in .agent-team/04-architecture/examples/${fixture}/kpi_report.json ` +
        `predate M-06 and lack the now-required value_formatted field, which causes a false ` +
        `"계약 위반" banner when this fixture is staged and viewed:\n${hits.join("\n")}`,
    ).toEqual([]);
  });
}
