/**
 * Copies an example artifact set into the directory layout the publish contract
 * describes, so the dashboard can render it without special-casing fixtures.
 *
 * Why this exists: the examples in .agent-team/04-architecture/examples/ keep all seven
 * files flat in one directory, but index.json addresses them at their real repository
 * paths — results/measurement/*.json plus results/data_quality_report.json. Pointing
 * AIROI_RESULTS_DIR straight at the flat directory therefore resolves nothing.
 *
 * Of the three options in story d-02 §9.3 (D02-b) this is option 1: stage a copy in the
 * real layout. The reader keeps one code path, so what the screenshots exercise is the
 * same code that will read a real publish — a "fixture mode" branch inside read.ts would
 * mean the fixtures test a path that production never takes.
 *
 * The example files are never modified; they are only read.
 *
 * Usage:
 *   node scripts/stage-fixture.mjs empty-sink
 *   node scripts/stage-fixture.mjs commerce-connected
 *
 * Then:
 *   AIROI_RESULTS_DIR=$PWD/.fixtures/<name>/results AIROI_FIXTURE_MODE=1 npm run dev
 */
import { cp, mkdir, readFile, rm } from "node:fs/promises";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const appRoot = fileURLToPath(new URL("../", import.meta.url));
const examplesRoot = resolve(appRoot, "../.agent-team/04-architecture/examples");

const name = process.argv[2];
if (name === undefined) {
  console.error("사용법: node scripts/stage-fixture.mjs <empty-sink|commerce-connected>");
  process.exitCode = 1;
} else {
  const source = join(examplesRoot, name);
  const stageRoot = join(appRoot, ".fixtures", name);

  // index.json is the only file whose location we have to assume; every other path
  // comes from index.json itself, so the staged tree follows the contract rather than
  // a hardcoded layout.
  const index = JSON.parse(await readFile(join(source, "index.json"), "utf8"));

  await rm(stageRoot, { recursive: true, force: true });

  // ADR-0002: measurement artifacts live under results/measurement/. The lone
  // exception is results/data_quality_report.json, which stays at the root because
  // data_spec §9 names that path — and it needs no special case here, since it is
  // copied from its own artifacts[].path like everything else.
  const indexTarget = join(stageRoot, "results/measurement/index.json");
  await mkdir(dirname(indexTarget), { recursive: true });
  await cp(join(source, "index.json"), indexTarget);

  for (const entry of index.artifacts) {
    // Basename, because the flat example directory is keyed by file name only.
    const fileName = entry.path.split("/").pop();
    const target = join(stageRoot, entry.path);
    await mkdir(dirname(target), { recursive: true });
    await cp(join(source, fileName), target);
    console.log(`  ${fileName} -> ${entry.path}`);
  }

  console.log(`\n${name} 스테이징 완료: ${join(stageRoot, "results")}`);
  console.log(
    `AIROI_RESULTS_DIR=${join(stageRoot, "results")} AIROI_FIXTURE_MODE=1 npm run dev`,
  );
}
