/**
 * TypeScript view of the measurement publish contract v1.
 *
 * CANONICAL SOURCE (these types must follow it, never the other way round):
 *   .agent-team/04-architecture/schemas/*.schema.json          (W2 design copy)
 *   docs/contracts/measurement-publish/v1/*.schema.json        (Phillip, M-06)
 *
 * Hand-written on purpose: a generator would add a dependency and a build step
 * for seven schema files, and TypeScript types vanish at runtime anyway — they
 * cannot catch a publisher that breaks the contract. The actual protection is in
 * read.ts, which re-checks the invariants that matter on every load.
 *
 * ★ The single most important fact encoded here: when `status` is not "ok" or
 *   "unconfirmed", `value` is `null` — the schema refuses anything else. Every
 *   consumer must branch on `status`, never on the falsiness of `value`, because
 *   `value === 0` is an honest measurement and `null` is the absence of one.
 */

export const CONTRACT_VERSION = "measurement-publish/v1";

/** common.schema.json#/$defs/reason_code — 9 values, not the 7 in the planning docs. */
export type ReasonCode =
  | "NO_SOURCE_EVENT"
  | "MISSING_FIELD"
  | "NO_COST_BASIS"
  | "NEEDS_TWO_STRATEGIES"
  | "NEEDS_MODEL_OUTPUT"
  | "PARAM_UNCONFIRMED"
  | "BLOCKED"
  | "NOT_RUN"
  | "PRECONDITION_MISSING";

/** common.schema.json#/$defs/metric_value.status */
export type MetricStatus = "ok" | "unconfirmed" | "unavailable" | "blocked" | "not_run";

/** common.schema.json#/$defs/unit */
export type Unit =
  | "count"
  | "krw"
  | "krw_per_customer"
  | "ratio"
  | "days"
  | "percentage_point"
  | "text"
  | "datetime";

export interface Window {
  direction: "retrospective" | "prospective" | "point_in_time" | "none";
  days?: number | null;
  label?: string;
}

/**
 * The evidence that a number was actually counted.
 *
 * The schema requires `basis` when status is ok/unconfirmed and forbids it
 * otherwise, which makes "has a basis" the machine-checkable difference between
 * a measured 0 and a missing value. That is why V-2 demands it be rendered next
 * to every value rather than hidden behind a tooltip.
 */
export interface Basis {
  population: string;
  denominator_definition: string;
  denominator?: number | null;
  observed_count?: number | null;
  window: Window;
  excluded_count?: number;
  excluded_reason?: string;
  source_event_types?: string[];
}

export interface BlockerRef {
  kind:
    | "field"
    | "schema_gap"
    | "event_type"
    | "metric"
    | "table"
    | "model_output"
    | "strategy"
    | "parameter"
    | "dependency";
  ref: string;
  reason_code: ReasonCode;
}

export interface Ci95 {
  status: "ok" | "inconclusive" | "not_run";
  lower?: number | null;
  upper?: number | null;
  method?: string;
  bootstrap_samples?: number;
}

export interface MetricValue {
  status: MetricStatus;
  /** null whenever status is unavailable/blocked/not_run — enforced by the schema. */
  value?: number | string | null;
  unit?: Unit;
  basis?: Basis;
  reason_code?: ReasonCode;
  reason_detail?: string;
  blocked_by?: BlockerRef[];
  derived?: boolean;
  derivation?: string;
  params_used?: Record<string, unknown>;
  ci95?: Ci95;

  /**
   * ★ NOT IN THE CONTRACT AS OF 2026-09-11 — M-06 §4.16 adds it.
   *
   * The publisher formats the number once, at serialisation time, from
   * `unit` + `value`; the screen prints the resulting string verbatim. The screen
   * must not format numbers itself: choosing currency/decimals/thousands
   * separators is a calculation (DB-012), and the moment a screen calls
   * `value.toLocaleString()` it hits `null` for every uncomputable metric and the
   * author "fixes" the crash with `?? 0` — which is precisely the failure this
   * whole project exists to prevent.
   *
   * Until it lands, `formatMetricValue()` renders a "계약 준비 중" marker instead
   * of a number. Optional here so that the day M-06 ships, the value simply
   * appears with no code change.
   */
  value_formatted?: string;

  /**
   * ★ NOT IN THE CONTRACT AS OF 2026-09-11 — M-06 §4.17 adds it.
   * Precision caveat for a metric that does produce a value but structurally
   * undercounts (V-7). Distinct from `unconfirmed`: an unconfirmed value becomes
   * correct once a parameter is fixed, a limited one stays wrong until new events
   * exist. Expected to be populated for `campaign_response_count` only in C1.
   */
  limit_note?: string;
}

/** common.schema.json#/$defs/source_split — commerce and simulator are both required. */
export interface SourceSplit {
  by_source: { commerce: MetricValue; simulator: MetricValue };
  /** Collection-health layer only; schema-forbidden on KPI layers 1 and 2 (R-7). */
  combined?: MetricValue;
}

export type SplitOrValue = MetricValue | SourceSplit;

export function isSourceSplit(value: SplitOrValue): value is SourceSplit {
  return typeof value === "object" && value !== null && "by_source" in value;
}

export interface Notice {
  code: string;
  level: "info" | "assumption" | "limitation" | "warning" | "failure";
  message: string;
  reference?: string;
}

export interface Provenance {
  schema_version: string;
  repo_commit: string | null;
  data_version: string | null;
  simulator_commit: string | null;
  null_reason?: Record<string, ReasonCode>;
  config_hashes: Record<string, string>;
  source_root: string;
  sink_manifest_sha256?: string | null;
  /** Recorded by the generator at runtime — never invented by design (DB-013). */
  generated_by: string;
  publisher_version?: string;
}

export interface Envelope {
  contract_version: string;
  artifact: ArtifactName;
  run_id: string;
  generated_at: string;
  timezone: "Asia/Seoul";
  provenance: Provenance;
  notices: Notice[];
}

export type ArtifactName =
  | "index"
  | "ingestion_report"
  | "rejection_report"
  | "field_coverage_report"
  | "kpi_report"
  | "data_quality_report"
  | "freeze_status";

/* ── index.json ─────────────────────────────────────────────────────────── */

/**
 * Banner codes. The contract picks exactly one and the screen only maps it to
 * Korean copy — if the screen re-ranked them there would be two rankings (P-4).
 *
 * ★ `REJECTED_EVENTS` is the 8th value added by M-06 (lead ruling B-11): without
 * it, a run with 217 rejected events but clean quality checks reported ALL_CLEAR.
 * Declared here ahead of the schema change so the mapping is complete on arrival;
 * an index.json that never emits it simply never hits that branch.
 */
export type HeadlineCode =
  | "CONTRACT_VIOLATION"
  | "QUALITY_VIOLATION"
  | "FREEZE_MISMATCH"
  | "REJECTED_EVENTS"
  | "CHECKS_NOT_RUN"
  | "SINK_EMPTY"
  | "METRICS_UNAVAILABLE"
  | "ALL_CLEAR";

export interface Verdict {
  level: "ok" | "attention" | "violation";
  headline_code: HeadlineCode;
  headline_detail: string;
  counts: {
    quality_violations: number;
    checks_not_run: number;
    checks_blocked: number;
    metrics_unavailable: number;
    metrics_not_run: number;
    schema_gaps: number;
    lock_items_pending: number;
    rejected_events: number;
  };
}

export interface ArtifactEntry {
  artifact: ArtifactName;
  /** Repository-root relative, always `results/…` — resolved by paths.ts. */
  path: string;
  status: "published" | "skipped" | "failed";
  sha256?: string;
  bytes?: number;
  reason_code?: ReasonCode;
  reason_detail?: string;
}

export interface ViewBinding {
  title: string;
  artifact: ArtifactName;
  route: string;
}

/** Screens drawn without an artifact. The explicit exception to the 1:1 rule. */
export interface StaticView {
  route: string;
  title: string;
  reason_code: ReasonCode;
  reason_detail: string;
}

export interface IndexArtifact extends Envelope {
  artifact: "index";
  publish_result: "ok" | "partial" | "failed";
  artifacts: ArtifactEntry[];
  views: Record<"V1" | "V2" | "V3" | "V4" | "V5" | "V6", ViewBinding>;
  verdict: Verdict;
  static_views?: StaticView[];
}

/* ── V1 ingestion_report.json ───────────────────────────────────────────── */

export interface SourceLink {
  link_state: "never_connected" | "connected";
  first_event_at: string | null;
  last_event_at: string | null;
  event_count: number;
  /** not_run + PARAM_UNCONFIRMED in C1: "we cannot judge staleness" is the value. */
  staleness: MetricValue;
}

export interface Partition {
  date: string;
  present: boolean;
  rows: SourceSplit;
  /** Inside first_event_at..last_event_at. Still does not distinguish a
   *  collection outage from genuine inactivity — see V-6. */
  in_observed_range: boolean;
}

export interface IngestionReport extends Envelope {
  artifact: "ingestion_report";
  totals: {
    events_ingested: SourceSplit;
    events_rejected: MetricValue;
    rejection_rate: MetricValue;
    event_type_coverage: MetricValue;
    partition_day_count: MetricValue;
    ingestion_days_gap: MetricValue;
    unavailable_metric_count: MetricValue;
    ingestion_gap_attribution: MetricValue;
  };
  /** All 16 event types are keys, including the ones with zero rows. */
  by_event_type: Record<string, SourceSplit>;
  partitions: Partition[];
  sources: { commerce: SourceLink; simulator: SourceLink };
}

/* ── V2 rejection_report.json ───────────────────────────────────────────── */

export interface RejectionReason {
  reason_key: string;
  reason_label: string;
  count: number;
  by_field?: Record<string, number>;
  by_event_type?: Record<string, number>;
}

/**
 * A representative rejected record.
 *
 * ★ `offending_values` exists in the contract (whitelisted to the 22 schema
 * columns) but this app never renders it. rejected.jsonl holds raw records
 * including fields that failed validation precisely because they do not belong in
 * the measurement layer — Hidden Trait / tau / potential outcomes among them.
 * Field *names* are enough to understand why a record was rejected, and "not
 * quite enough" would still not justify opening a leak path (ISO-003).
 * The field is deliberately absent from this interface so it cannot be rendered
 * by accident.
 */
export interface RejectionSample {
  reason_key: string;
  event_type: string | null;
  partition_date?: string | null;
  source?: "commerce" | "simulator" | "unknown";
  problems: string[];
  offending_fields?: string[];
}

export interface RejectionReport extends Envelope {
  artifact: "rejection_report";
  totals: {
    events_rejected: MetricValue;
    rejection_rate: MetricValue;
    distinct_reasons: MetricValue;
  };
  by_reason: RejectionReason[];
  samples: RejectionSample[];
}

/* ── V3 field_coverage_report.json ──────────────────────────────────────── */

export interface FieldCoverage {
  group: "core" | "session" | "product" | "order" | "marketing" | "meta";
  fill_rate: SourceSplit;
  applicable_event_types?: string[];
  /** Published so the screen never has to infer the gap → impact chain (DB-012). */
  blocks_metrics: string[];
}

/**
 * A column the formulas need that the schema does not have at all.
 * field_coverage only counts columns that exist, so without this list these gaps
 * would be invisible on every screen forever.
 */
export interface SchemaGap {
  ref: string;
  required_by_formula: string;
  where_it_should_live: string;
  blocks_metrics: string[];
  reason_code: ReasonCode;
  reason_detail: string;
  decision_ref?: string;
  blocks_checks?: string[];
}

export interface FieldCoverageReport extends Envelope {
  artifact: "field_coverage_report";
  /** Exactly 22 keys (DATA-003), including fields that never arrived. */
  fields: Record<string, FieldCoverage>;
  missing_fields: string[];
  schema_gaps: SchemaGap[];
}

/* ── V4 kpi_report.json ─────────────────────────────────────────────────── */

export interface KpiMetric {
  name: string;
  layer: "collection_health" | "customer_kpi" | "business_kpi" | "experiment";
  role: "none" | "primary" | "guardrail" | "secondary";
  population: string;
  window: Window;
  denominator_definition: string;
  formula?: string;
  definition_ref?: string;
  source_events?: string[];
  value: SplitOrValue;
  /** Downstream metrics that collapse with this one. Reverse of value.blocked_by. */
  blocks?: string[];
}

export interface KpiReport extends Envelope {
  artifact: "kpi_report";
  /** null when there is no data to anchor a reference date on (R-1). */
  index_date: string | null;
  definition_version: string;
  /** Counted by the publisher — the screen must not tally (DB-012). */
  summary: {
    total: number;
    ok: number;
    unconfirmed: number;
    unavailable: number;
    blocked: number;
    not_run: number;
    by_layer?: Record<string, Record<string, number>>;
  };
  metrics: KpiMetric[];
}

/* ── V5 data_quality_report.json ────────────────────────────────────────── */

/**
 * ★ A different enum from MetricStatus. Mapping check rows through the
 * metric_value table would drop them into an undefined default.
 * `vacuous` = the check ran and examined 0 rows. It is neither a pass nor a
 * failure, and in C1 it is the normal state.
 */
export type CheckStatus = "pass" | "fail" | "vacuous" | "not_run" | "blocked";

export interface QualityCheck {
  id: string;
  spec_ref: string;
  title: string;
  status: CheckStatus;
  /** What was actually examined. Without it a partial check reads as a full one. */
  scope: string;
  reason_code?: ReasonCode;
  reason_detail?: string;
  violations?: number | null;
  examined_rows?: number | null;
  threshold?: string | number | null;
  samples?: { detail: string; event_id?: string | null; order_id?: string | null; customer_id?: string | null; partition_date?: string | null }[];
}

export interface SpecCoverage {
  spec_items: { spec_ref: string; covered_by: string[]; worst_status: CheckStatus }[];
  reported_checks: number;
  /** Non-empty means a canonical check is covered by nothing. Must be shown. */
  unmapped_spec_items: string[];
}

export interface DataQualityReport extends Envelope {
  artifact: "data_quality_report";
  gate_result: "pass" | "fail" | "incomplete";
  checks: QualityCheck[];
  spec_coverage: SpecCoverage;
}

/* ── V6 freeze_status.json ──────────────────────────────────────────────── */

export type LockItemStatus = "LOCKED" | "PARTIAL" | "PENDING" | "BLOCKED" | "OUT_OF_SCOPE";
/** `not_run` is not a pass — it must not share a colour with `match`. */
export type FileVerification = "match" | "mismatch" | "missing" | "not_run";

export interface LockItem {
  item: string;
  status: LockItemStatus;
  owner_part: "measurement" | "simulator" | "commerce" | "decision";
  /** Partial locks state their boundary in prose; without it PARTIAL reads as full. */
  scope_note: string;
  reason_code?: ReasonCode;
  reason_detail?: string;
  canonical_files?: {
    path: string;
    locked_sha256?: string | null;
    current_sha256?: string | null;
    verification: FileVerification;
  }[];
}

export interface FreezeStatus extends Envelope {
  artifact: "freeze_status";
  gate: "GATE_1";
  /** C1 cannot exceed `partial`; `not_started` is today's normal, not a warning. */
  overall: "not_started" | "partial" | "sealed" | "violated";
  lock_record?: {
    path: string;
    sha256: string;
    locked_at: string;
    locked_by: string;
    repo_commit: string | null;
    simulator_commit: string | null;
  } | null;
  /** Exactly 9 items (PRD §22), including the ones out of C1 scope. */
  items: LockItem[];
  /** `met: null` means "not checked" and must stay distinct from `false`. */
  unlocked_items: { id: string; title: string; met: boolean | null; evidence?: string }[];
}
