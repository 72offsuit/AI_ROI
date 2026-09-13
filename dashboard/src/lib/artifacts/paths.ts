/**
 * The only place in this app that turns a contract-supplied string into a
 * filesystem path.
 *
 * Why it is isolated: SRS DB-014 allows the dashboard to read `results/` and
 * `data/processed/` and nothing else — in particular never `data/hidden/`,
 * `data/ground_truth/` or `src/simulator/`. That rule is currently enforced by
 * human review only (the Python isolation suite does not look at `dashboard/`, and
 * extending it is decision D-22, owned by W6). Funnelling every path through one
 * whitelist gives a runtime guarantee that does not depend on anyone remembering
 * the rule: an escaping path throws instead of quietly reading a forbidden file.
 *
 * `node:fs` must not be imported anywhere outside `src/lib/artifacts/` (DG-6).
 */
import { isAbsolute, resolve, sep } from "node:path";

/** Thrown when a path would leave the area DB-014 permits. Never caught to a default. */
export class IsolationError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "IsolationError";
  }
}

/** Thrown when the published artifact does not match the shape the contract promises. */
export class ContractViolationError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "ContractViolationError";
  }
}

/**
 * Directory that the contract's `results/` prefix maps to.
 *
 * Default assumes the process runs with `dashboard/` as cwd (`npm run dev` from
 * this folder), which puts `../results` at the repository root — the location
 * ADR-0002 assigns to published artifacts. Override with AIROI_RESULTS_DIR to
 * point at a staged fixture (see scripts/stage-fixture.mjs).
 *
 * An empty string is treated as "not set": `process.env.X ?? d` would accept `""`
 * and silently resolve to cwd, which is exactly the class of quiet-wrong-default
 * this codebase is trying to avoid.
 */
function configuredResultsDir(): string {
  const fromEnv = process.env.AIROI_RESULTS_DIR;
  if (typeof fromEnv === "string" && fromEnv.trim().length > 0) {
    return resolve(fromEnv.trim());
  }
  return resolve(process.cwd(), "../results");
}

export const RESULTS_DIR = configuredResultsDir();

/** Prefix the publish contract uses for every artifact path (index.schema.json `pattern`). */
const RESULTS_PREFIX = "results/";

/**
 * `index.json` itself — the only path this app assumes rather than reads.
 *
 * Location is fixed by ADR-0002: measurement artifacts live under
 * `results/measurement/`.
 *
 * ★ There is exactly one exception, and it is deliberate:
 *   `results/data_quality_report.json` sits at the root of `results/`, because
 *   `data_spec` §9 and issue #48 name that path as canonical. It looks inconsistent
 *   and it is not — do NOT "tidy" it into the subdirectory. Nothing here depends on
 *   guessing it anyway: every artifact except this index is located from
 *   `artifacts[].path`, so the exception costs no code.
 *
 * ★ Do not re-derive this from whatever the publisher happens to emit. An earlier
 *   revision of this file pointed at `results/index.json` after observing a publish
 *   run that wrote it there, reasoning that the JSON Schema pins no location so the
 *   producer must be authoritative. The schema did not pin it, but ADR-0002 did, and
 *   the publish run was simply wrong. Order of authority: contract -> ADR -> fixtures
 *   -> and only if all three are silent, the producer.
 */
export const INDEX_RELATIVE_PATH = `${RESULTS_PREFIX}measurement/index.json`;

/**
 * Map a repository-root-relative artifact path from `index.json` onto disk.
 *
 * Input example: `results/measurement/kpi_report.json`
 * Output example: `<RESULTS_DIR>/measurement/kpi_report.json`
 *
 * Three things are rejected rather than normalised, because each of them would
 * mean the dashboard is reading something nobody promised it:
 *   1. absolute paths            — the contract only ever emits relative ones
 *   2. a prefix other than `results/`
 *   3. anything that escapes RESULTS_DIR after resolution (`..` segments)
 *
 * `data/processed/` is permitted by DB-014 and by the contract's own pattern, but
 * C1 publishes nothing there, so it is refused with an explicit message instead of
 * being wired to a second base directory that no artifact would ever use.
 * ponytail: only the `results/` prefix is mapped; add a PROCESSED_DIR branch here
 * the first time an index.json actually lists a `data/processed/` artifact.
 */
export function resolveArtifactPath(relative: string): string {
  if (isAbsolute(relative)) {
    throw new IsolationError(`허용 경로 밖 접근: 절대 경로는 읽지 않습니다 — ${relative}`);
  }
  if (relative.startsWith("data/processed/")) {
    throw new IsolationError(
      `data/processed/ 산출물은 C1 에서 게시되지 않습니다 — ${relative}`,
    );
  }
  if (!relative.startsWith(RESULTS_PREFIX)) {
    throw new IsolationError(
      `허용 경로 밖 접근: 게시 계약은 results/ 로 시작하는 경로만 허용합니다 — ${relative}`,
    );
  }

  const target = resolve(RESULTS_DIR, relative.slice(RESULTS_PREFIX.length));
  if (target !== RESULTS_DIR && !target.startsWith(RESULTS_DIR + sep)) {
    throw new IsolationError(`허용 경로 밖 접근: ${relative}`);
  }
  return target;
}
