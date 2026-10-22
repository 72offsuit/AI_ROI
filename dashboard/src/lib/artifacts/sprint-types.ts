/**
 * Shapes of the sprint-v0 result files (`results/sprint-v0/latest/*.json`, issue 147).
 *
 * ★ These files are NOT the measurement publish contract (`types.ts`). They have no
 *   JSON Schema yet, no `metric_value` envelope and no `value_formatted`. Every field is
 *   therefore typed as possibly `null` (or absent): the producer was written in the same
 *   three-hour sprint, and a field this build expected but did not get must render as
 *   "계산 불가", never as 0 and never as a crash.
 */

/** Common header of the seven pipeline files. */
export interface SprintHeader {
  sprint: string;
  sealed: boolean;
  run_id: string;
  generated_at: string;
}

export type StageStatus = "ok" | "not_run" | "failed";

export interface RunMeta extends SprintHeader {
  seed?: number | null;
  N?: number | null;
  profile?: string | null;
  simulator_version?: string | null;
  stages?: { name: string; status: StageStatus | string; reason?: string | null; seconds?: number | null }[];
}

/** Cross-validation summaries are `{mean, std}`; a holdout may be a bare number. */
export type MeanStd = { mean?: number | null; std?: number | null } | number | null;

export type ModelKind = "baseline" | "proposed" | string;

export interface ChurnModel {
  name: string;
  kind: ModelKind;
  cv?: Record<string, MeanStd> | null;
  temporal_holdout?: Record<string, MeanStd> | null;
}

export interface ChurnEval extends SprintHeader {
  label_def?: string | null;
  n?: number | null;
  pos_rate?: number | null;
  models?: ChurnModel[];
  shap_top?: { feature: string; mean_abs?: number | null }[];
  importance_method?: string | null;
}

export interface ClvEval extends SprintHeader {
  horizon_days?: number | null;
  models?: {
    name: string;
    kind: ModelKind;
    mae?: number | null;
    rmse?: number | null;
    spearman?: number | null;
    top20_hit?: number | null;
  }[];
}

export interface UpliftEval extends SprintHeader {
  n?: number | null;
  arms?: Record<string, number | null>;
  ate?: Record<string, { value?: number | null; ci95?: [number | null, number | null] | null } | null>;
  models?: {
    name: string;
    kind: ModelKind;
    qini?: number | null;
    auuc?: number | null;
    uplift_at_k?: Record<string, number | null> | null;
    qini_curve?: [number | null, number | null][] | null;
  }[];
}

export interface Segments extends SprintHeader {
  segments?: {
    id: string;
    name?: string | null;
    n?: number | null;
    share?: number | null;
    avg_churn_p?: number | null;
    avg_cate?: number | null;
    avg_clv?: number | null;
  }[];
}

export interface StrategyComparison extends SprintHeader {
  window?: { start?: string | null; end?: string | null } | null;
  budget_krw?: number | null;
  strategies?: {
    id: string;
    name?: string | null;
    n_targeted?: number | null;
    treatment_mix?: Record<string, number | null> | null;
    revenue?: number | null;
    marketing_cost?: number | null;
    contribution_profit?: number | null;
    churn_rate?: number | null;
    incremental_profit_vs_S1?: number | null;
    incremental_profit_basis?: string | null;
    flags?: string[] | null;
    roi?: number | null;
  }[];
}

export interface AbTest extends SprintHeader {
  srm?: { chi2?: number | null; p?: number | null; ok?: boolean | null } | null;
  arms?: {
    arm: string;
    n?: number | null;
    rate?: number | null;
    diff_vs_control?: number | null;
    ci95?: [number | null, number | null] | null;
    p_raw?: number | null;
    p_holm?: number | null;
  }[];
  power?: Record<string, number | string | boolean | null> | null;
}

/**
 * `docs/research/realism_report.json`, read from its copy in `results/sprint-v0/latest/`
 * (DG-1 — the dashboard reads `results/` only). It is produced by research, not by the
 * pipeline run, so it carries no `run_id` and is not compared against `run_meta`.
 */
export interface RealismReport {
  generated_at?: string | null;
  metrics?: {
    id?: string | null;
    name: string;
    unit?: string | null;
    /** A number, or a record of named sub-values (e.g. median · mean · p75) — scripts/research/realism_check.py. */
    synthetic?: number | Record<string, unknown> | null;
    reference?: {
      dataset?: string | null;
      value?: number | Record<string, unknown> | null;
      band?: unknown;
      source_url?: string | null;
    } | null;
    /** realism_check.py's own verdict: pass · borderline · fail · no_data. */
    verdict?: string | null;
    /** The same verdict in the dashboard vocabulary: consistent · deviates · no_reference. */
    dashboard_verdict?: "consistent" | "deviates" | "no_reference" | string | null;
  }[];
}

export interface SprintFiles {
  run_meta: RunMeta;
  churn_eval: ChurnEval;
  clv_eval: ClvEval;
  uplift_eval: UpliftEval;
  segments: Segments;
  strategy_comparison: StrategyComparison;
  ab_test: AbTest;
  realism_report: RealismReport;
}

export type SprintFileName = keyof SprintFiles;
