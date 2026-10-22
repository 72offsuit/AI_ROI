/**
 * Loads the sprint-v0 result files (issue 147).
 *
 * Source is chosen once, explicitly, by `AIROI_SPRINT_SOURCE`:
 *
 *   unset / anything else   `results/sprint-v0/latest/` through the DB-014 whitelist
 *   `mock`                  the hand-made files in `dashboard/fixtures/sprint-v0/`
 *
 * ★ There is no automatic fallback from results to mock. A missing real file renders
 *   as "미생성"; it never quietly turns into a mock value. The two are only ever mixed
 *   by a person setting the variable, and then every screen carries the 목업 badge.
 *
 * ★ Mock files are bundled through static JSON imports, not read from disk, so this
 *   module never opens a path outside `results/` (DG-1). Real files go through
 *   `resolveArtifactPath()`, which also enforces the symlink guard of issue #64.
 *
 * Reading order mirrors read.ts for the parts that apply:
 *   1. file absent                -> "missing" (미생성), not an empty screen
 *   2. header keys present        -> otherwise "violation"
 *   3. run_id equals run_meta's   -> otherwise "run-id-mismatch"; values of two runs are
 *                                    never put on one screen
 */
import { readFile } from "node:fs/promises";

import { resolveArtifactPath } from "./paths";
import type { RunMeta, SprintFileName, SprintFiles } from "./sprint-types";

import mockRunMeta from "../../../fixtures/sprint-v0/run_meta.json";
import mockChurn from "../../../fixtures/sprint-v0/churn_eval.json";
import mockClv from "../../../fixtures/sprint-v0/clv_eval.json";
import mockUplift from "../../../fixtures/sprint-v0/uplift_eval.json";
import mockSegments from "../../../fixtures/sprint-v0/segments.json";
import mockStrategy from "../../../fixtures/sprint-v0/strategy_comparison.json";
import mockAb from "../../../fixtures/sprint-v0/ab_test.json";
import mockRealism from "../../../fixtures/sprint-v0/realism_report.json";

export type SprintSource = "results" | "mock";

export const SPRINT_DIR = "results/sprint-v0/latest";

const MOCK: Record<SprintFileName, unknown> = {
  run_meta: mockRunMeta,
  churn_eval: mockChurn,
  clv_eval: mockClv,
  uplift_eval: mockUplift,
  segments: mockSegments,
  strategy_comparison: mockStrategy,
  ab_test: mockAb,
  realism_report: mockRealism,
};

/** Files produced by the pipeline run. `realism_report` comes from research instead. */
const RUN_FILES: ReadonlySet<SprintFileName> = new Set([
  "run_meta",
  "churn_eval",
  "clv_eval",
  "uplift_eval",
  "segments",
  "strategy_comparison",
  "ab_test",
]);

export function sprintSource(): SprintSource {
  const flag = process.env.AIROI_SPRINT_SOURCE;
  return typeof flag === "string" && flag.trim() === "mock" ? "mock" : "results";
}

export type SprintLoad<K extends SprintFileName> =
  | { kind: "ok"; source: SprintSource; path: string; artifact: SprintFiles[K] }
  | { kind: "missing"; source: SprintSource; path: string }
  | { kind: "run-id-mismatch"; source: SprintSource; path: string; expected: string; found: string }
  | { kind: "violation"; source: SprintSource; path: string; message: string };

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function pathOf(file: SprintFileName, source: SprintSource): string {
  return source === "mock"
    ? `dashboard/fixtures/sprint-v0/${file}.json`
    : `${SPRINT_DIR}/${file}.json`;
}

async function readRaw(file: SprintFileName, source: SprintSource): Promise<unknown | undefined> {
  if (source === "mock") return MOCK[file];
  const relative = pathOf(file, source);
  let text: string;
  try {
    text = await readFile(resolveArtifactPath(relative), "utf8");
  } catch (error) {
    // Only "not there" is an absence. Permissions, I/O and isolation errors propagate.
    if (isRecord(error) && error.code === "ENOENT") return undefined;
    throw error;
  }
  return JSON.parse(text) as unknown;
}

/** Steps 1 and 2 for one file, without the run_id comparison. */
async function loadOne<K extends SprintFileName>(file: K, source: SprintSource): Promise<SprintLoad<K>> {
  const path = pathOf(file, source);
  let raw: unknown | undefined;
  try {
    raw = await readRaw(file, source);
  } catch (error) {
    return { kind: "violation", source, path, message: (error as Error).message };
  }
  if (raw === undefined) return { kind: "missing", source, path };
  if (!isRecord(raw)) {
    return { kind: "violation", source, path, message: "최상위가 객체가 아닙니다." };
  }
  if (RUN_FILES.has(file)) {
    for (const key of ["sprint", "sealed", "run_id", "generated_at"]) {
      if (!(key in raw)) {
        return { kind: "violation", source, path, message: `공통 머리 키 누락: ${key}` };
      }
    }
    if (typeof raw.sealed !== "boolean") {
      return { kind: "violation", source, path, message: "sealed 가 boolean 이 아닙니다." };
    }
  }
  return { kind: "ok", source, path, artifact: raw as unknown as SprintFiles[K] };
}

export async function loadRunMeta(): Promise<SprintLoad<"run_meta">> {
  return loadOne("run_meta", sprintSource());
}

/**
 * Loads one file and, for pipeline files, checks it belongs to the same run as
 * `run_meta.json`. If run_meta itself is absent the comparison cannot be made; the file
 * is still shown, and the page header says run_meta is 미생성.
 */
export async function loadSprint<K extends SprintFileName>(file: K): Promise<SprintLoad<K>> {
  const source = sprintSource();
  const result = await loadOne(file, source);
  if (result.kind !== "ok" || file === "run_meta" || !RUN_FILES.has(file)) return result;

  const meta = await loadOne("run_meta", source);
  if (meta.kind !== "ok") return result;
  const expected = (meta.artifact as RunMeta).run_id;
  const found = (result.artifact as { run_id: string }).run_id;
  if (expected !== found) {
    return { kind: "run-id-mismatch", source, path: result.path, expected, found };
  }
  return result;
}
