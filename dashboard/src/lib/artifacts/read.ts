/**
 * Loads published artifacts and refuses to hand the UI anything that breaks the
 * publish contract.
 *
 * The reading order is fixed by dashboard-architecture.md §3.1:
 *   1. read index.json            -> absent: tell the reader how to publish (DB-013)
 *   2. check contract_version     -> different: render nothing, say so (R-6)
 *   3. read views[view].artifact
 *   4. compare run_id with index  -> different: never mix values from two runs
 *   5. render
 *
 * Step 4 is the reading half of the atomic-publish contract: index.json is written
 * last, so a run_id mismatch means the publisher is mid-flight and the two files on
 * disk describe different runs.
 *
 * ★ Why this module throws instead of substituting defaults: if the measurement
 *   layer ever emits a value alongside an "uncomputable" status, putting that number
 *   on screen would be the exact failure USP-1 exists to prevent. An empty screen is
 *   better than a screen with a quietly invented number.
 */
import { readFile } from "node:fs/promises";

import {
  ContractViolationError,
  INDEX_RELATIVE_PATH,
  RESULTS_DIR,
  resolveArtifactPath,
} from "./paths";
import {
  CONTRACT_VERSION,
  type ArtifactName,
  type DataQualityReport,
  type Envelope,
  type FieldCoverageReport,
  type FreezeStatus,
  type IndexArtifact,
  type IngestionReport,
  type KpiReport,
  type MetricValue,
  type RejectionReport,
} from "./types";

/** Statuses for which the schema requires `value: null` and forbids `basis`. */
const UNCOMPUTABLE: ReadonlySet<string> = new Set(["unavailable", "blocked", "not_run"]);

/**
 * Outcome of a load attempt. A discriminated union rather than exceptions-only so
 * that pages can render the right explanation: "nothing published yet" and "the
 * publisher broke the contract" are different facts and must not collapse into one
 * blank screen.
 */
export type LoadResult<T> =
  | { kind: "ok"; index: IndexArtifact; artifact: T }
  | { kind: "missing"; resultsDir: string }
  | { kind: "contract-mismatch"; expected: string; found: string }
  | { kind: "run-id-mismatch"; indexRunId: string; artifactRunId: string; artifactName: string }
  | { kind: "violation"; message: string };

export type IndexLoadResult =
  | { kind: "ok"; index: IndexArtifact }
  | { kind: "missing"; resultsDir: string }
  | { kind: "contract-mismatch"; expected: string; found: string }
  | { kind: "violation"; message: string };

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

async function readJson(relative: string): Promise<unknown | undefined> {
  const absolute = resolveArtifactPath(relative);
  let text: string;
  try {
    text = await readFile(absolute, "utf8");
  } catch (error) {
    // Only "file is not there" becomes `undefined`; every other I/O failure keeps
    // propagating, because a permissions or disk error is not an empty state.
    if (isRecord(error) && error.code === "ENOENT") return undefined;
    throw error;
  }
  try {
    return JSON.parse(text) as unknown;
  } catch (error) {
    throw new ContractViolationError(
      `게시물이 JSON 으로 읽히지 않습니다 — ${relative}: ${(error as Error).message}`,
    );
  }
}

/**
 * Walks an already-parsed artifact and asserts the two metric_value invariants
 * that the whole project rests on.
 *
 * Invariant A — an uncomputable status must carry `value: null`.
 *   This is the last line of defence against zero-fill. If the publisher sends
 *   `{status: "unavailable", value: 0}` the dashboard refuses to draw it.
 *
 * Invariant B — a computed status (ok/unconfirmed) must carry a non-null value.
 *   Otherwise the UI would have to invent something to show.
 *
 * ★ Deliberate divergence from story d-01 AC-6, which says "throw when status is
 *   not 'ok' and value is not null". Read literally that rejects every legitimate
 *   `unconfirmed` metric, because common.schema.json requires `unconfirmed` to
 *   carry a value plus `params_used`. The contract wins over the prose (project
 *   constitution §5), so the check keys off the three uncomputable statuses.
 *
 * A missing `basis` is NOT thrown here: contract-reconciliation V-3 wants that value
 * rendered with a "계약 위반" chip so the omission is visible on screen rather than
 * hidden behind an error page. formatMetricValue() attaches that chip.
 */
function assertMetricValueInvariants(node: unknown, path: string): void {
  if (Array.isArray(node)) {
    node.forEach((child, i) => assertMetricValueInvariants(child, `${path}[${i}]`));
    return;
  }
  if (!isRecord(node)) return;

  const status = node.status;
  // A metric_value is recognised by `status` holding one of the five known values.
  if (typeof status === "string" && (UNCOMPUTABLE.has(status) || status === "ok" || status === "unconfirmed")) {
    const candidate = node as unknown as MetricValue;
    if (UNCOMPUTABLE.has(status)) {
      if (candidate.value !== null && candidate.value !== undefined) {
        throw new ContractViolationError(
          `계산 불가 상태에 값이 왔습니다 — ${path}: status=${status}, value=${JSON.stringify(candidate.value)}`,
        );
      }
    } else if (candidate.value === null || candidate.value === undefined) {
      throw new ContractViolationError(
        `계산된 상태인데 값이 없습니다 — ${path}: status=${status}`,
      );
    }
  }

  for (const [key, child] of Object.entries(node)) {
    assertMetricValueInvariants(child, `${path}.${key}`);
  }
}

/** Envelope fields every artifact must have before anything else is trusted. */
function assertEnvelope(node: unknown, expected: ArtifactName, relative: string): Envelope {
  if (!isRecord(node)) {
    throw new ContractViolationError(`게시물이 객체가 아닙니다 — ${relative}`);
  }
  for (const key of ["contract_version", "artifact", "run_id", "generated_at", "provenance", "notices"]) {
    if (!(key in node)) {
      throw new ContractViolationError(`계약이 보장한 키 누락 — ${relative}: ${key}`);
    }
  }
  if (node.artifact !== expected) {
    throw new ContractViolationError(
      `산출물 이름이 다릅니다 — ${relative}: ${String(node.artifact)} (기대: ${expected})`,
    );
  }
  return node as unknown as Envelope;
}

/**
 * Step 1 and 2. Every page starts here, including `/`, which reads nothing else.
 */
export async function loadIndex(): Promise<IndexLoadResult> {
  let raw: unknown | undefined;
  try {
    raw = await readJson(INDEX_RELATIVE_PATH);
  } catch (error) {
    return { kind: "violation", message: (error as Error).message };
  }
  if (raw === undefined) return { kind: "missing", resultsDir: RESULTS_DIR };

  if (!isRecord(raw) || typeof raw.contract_version !== "string") {
    return { kind: "violation", message: "index.json 에 contract_version 이 없습니다." };
  }
  // Version check comes before any other validation: a different contract means the
  // field names below may not mean what this build thinks they mean.
  if (raw.contract_version !== CONTRACT_VERSION) {
    return { kind: "contract-mismatch", expected: CONTRACT_VERSION, found: raw.contract_version };
  }

  try {
    assertEnvelope(raw, "index", INDEX_RELATIVE_PATH);
    assertMetricValueInvariants(raw, "index");
  } catch (error) {
    return { kind: "violation", message: (error as Error).message };
  }
  return { kind: "ok", index: raw as unknown as IndexArtifact };
}

type ViewKey = "V1" | "V2" | "V3" | "V4" | "V5" | "V6";

/** Maps a view to its artifact via index.views, then runs steps 3 and 4. */
async function loadView<T>(view: ViewKey): Promise<LoadResult<T>> {
  const indexResult = await loadIndex();
  if (indexResult.kind !== "ok") return indexResult;
  const index = indexResult.index;

  const binding = index.views[view];
  if (binding === undefined) {
    return { kind: "violation", message: `index.json 의 views 에 ${view} 가 없습니다.` };
  }

  const entry = index.artifacts.find((item) => item.artifact === binding.artifact);
  if (entry === undefined) {
    return {
      kind: "violation",
      message: `index.json 이 ${binding.artifact} 를 artifacts 목록에 싣지 않았습니다.`,
    };
  }
  if (entry.status !== "published") {
    return {
      kind: "violation",
      message: `${binding.artifact} 가 게시되지 않았습니다 — ${entry.status}: ${
        entry.reason_detail === undefined ? "사유 미표기" : entry.reason_detail
      }`,
    };
  }

  let raw: unknown | undefined;
  try {
    raw = await readJson(entry.path);
  } catch (error) {
    return { kind: "violation", message: (error as Error).message };
  }
  if (raw === undefined) {
    return {
      kind: "violation",
      message: `index.json 이 published 로 적은 파일이 없습니다 — ${entry.path}`,
    };
  }

  try {
    const envelope = assertEnvelope(raw, binding.artifact, entry.path);
    if (envelope.contract_version !== CONTRACT_VERSION) {
      return {
        kind: "contract-mismatch",
        expected: CONTRACT_VERSION,
        found: envelope.contract_version,
      };
    }
    // Step 4 — the reading half of atomic publish. Values from two runs are never mixed.
    if (envelope.run_id !== index.run_id) {
      return {
        kind: "run-id-mismatch",
        indexRunId: index.run_id,
        artifactRunId: envelope.run_id,
        artifactName: binding.artifact,
      };
    }
    assertMetricValueInvariants(raw, binding.artifact);
  } catch (error) {
    return { kind: "violation", message: (error as Error).message };
  }

  return { kind: "ok", index, artifact: raw as T };
}

export const loadIngestionReport = () => loadView<IngestionReport>("V1");
export const loadRejectionReport = () => loadView<RejectionReport>("V2");
export const loadFieldCoverageReport = () => loadView<FieldCoverageReport>("V3");
export const loadKpiReport = () => loadView<KpiReport>("V4");
export const loadDataQualityReport = () => loadView<DataQualityReport>("V5");
export const loadFreezeStatus = () => loadView<FreezeStatus>("V6");
