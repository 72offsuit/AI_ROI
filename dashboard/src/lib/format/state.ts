/**
 * Contract -> visual state. A pure lookup, deliberately with no logic of its own.
 *
 * The screen must not decide anything (DB-012). Every visual state here is derived
 * mechanically from the `(status, reason_code)` pair the publisher already decided
 * on. If this file ever grows an `if` that inspects counts, thresholds or field
 * presence, the dashboard has started judging and there are now two rankings of the
 * truth.
 *
 * Why eight states rather than one "uncomputable": in C1 most metrics are
 * uncomputable, and a screen that is 80% one shade of grey reads as a background,
 * not a warning. The seven reason codes split by *who has to act*, not by severity —
 * NEEDS_MODEL_OUTPUT means "carry on, this is on schedule" while NO_COST_BASIS means
 * "stop and look". Giving those the same treatment guarantees one of them is
 * misread, and it is always the smaller group (the ones needing action).
 *
 * Splitting them does not weaken "never fill with zero": none of the five
 * uncomputable states puts a number in the value slot. Only the emphasis changes.
 *
 * Canonical table: .agent-team/07-design/contract-reconciliation.md §3-③
 */
import type { CheckStatus, MetricStatus, ReasonCode } from "@/lib/artifacts/types";

export type VisualState =
  | "available"
  | "provisional"
  | "planned"
  | "unconnected"
  | "gap"
  | "env_blocked"
  | "not_run"
  | "violation"
  /** Gate verdicts only — never a metric value slot (F-2). */
  | "ok";

/**
 * Reason codes that mean "this is on the plan, not a defect".
 * PRECONDITION_MISSING joins them because a missing upstream artifact is a sequencing
 * fact, not a data gap the reader can act on today.
 */
const PLANNED_REASONS: ReadonlySet<ReasonCode> = new Set([
  "NEEDS_TWO_STRATEGIES",
  "NEEDS_MODEL_OUTPUT",
  "PRECONDITION_MISSING",
]);

/** Reason codes that mean "evidence is structurally missing — act on it". */
const GAP_REASONS: ReadonlySet<ReasonCode> = new Set(["NO_COST_BASIS", "MISSING_FIELD"]);

/**
 * metric_value `(status, reason_code)` -> visual state.
 *
 * Expected results:
 *   ("ok",          undefined)            -> "available"     (includes a measured 0)
 *   ("unconfirmed", "PARAM_UNCONFIRMED")  -> "provisional"   (a number, outlined)
 *   ("unavailable", "NO_COST_BASIS")      -> "gap"
 *   ("unavailable", "NO_SOURCE_EVENT")    -> "unconnected"
 *   ("unavailable", "NEEDS_MODEL_OUTPUT") -> "planned"
 *   ("blocked",     "BLOCKED")            -> "env_blocked"
 *   ("not_run",     "NOT_RUN")            -> "not_run"
 *
 * An `unavailable` whose reason code is missing or unrecognised returns "violation"
 * rather than a default state: the schema makes reason_code required there, so its
 * absence is a contract breach and must be visible, not smoothed over.
 */
export function deriveMetricState(
  status: MetricStatus,
  reasonCode: ReasonCode | undefined,
): VisualState {
  switch (status) {
    case "ok":
      return "available";
    case "unconfirmed":
      return "provisional";
    case "blocked":
      return "env_blocked";
    case "not_run":
      return "not_run";
    case "unavailable":
      if (reasonCode === undefined) return "violation";
      if (PLANNED_REASONS.has(reasonCode)) return "planned";
      if (reasonCode === "NO_SOURCE_EVENT") return "unconnected";
      if (GAP_REASONS.has(reasonCode)) return "gap";
      return "violation";
    default:
      return "violation";
  }
}

/**
 * data_quality_report `checks[].status` -> visual state.
 *
 * ★ A separate axis from metric_value. The two enums overlap in spelling only;
 * routing check rows through deriveMetricState() would drop `pass`, `fail` and
 * `vacuous` into an undefined default.
 *
 * ★ `vacuous` maps to `unconnected` (info) — neither green nor red. It means the
 * check ran and examined zero rows. In C1 this is the *normal* state (7 of 18 checks
 * in the empty-sink fixture), so drawing it as a failure would cry wolf and drawing
 * it as a pass would claim something was verified when nothing was.
 *
 * Note the condition is `status === "vacuous"` alone. The older phrasing
 * `pass && examined_rows === 0` is dead code: ADR-0010 made the schema reject that
 * combination, and re-reading examined_rows would mean the screen repeats a judgement
 * the publisher already made (DB-012).
 */
export function deriveCheckState(status: CheckStatus): VisualState {
  switch (status) {
    case "pass":
      return "ok";
    case "fail":
      return "violation";
    case "vacuous":
      return "unconnected";
    case "not_run":
      return "not_run";
    case "blocked":
      return "env_blocked";
    default:
      return "violation";
  }
}

/** Canonical Korean copy per visual state. Glyphs live only in StateChip. */
export const STATE_LABEL: Record<VisualState, string> = {
  available: "측정됨",
  provisional: "잠정값 · 파라미터 미확정",
  planned: "계획된 부재",
  unconnected: "아직 관측되지 않음",
  gap: "계산 불가 · 근거 공백",
  env_blocked: "실행 불가 · 환경 제약",
  not_run: "미실행",
  violation: "계약 위반",
  ok: "통과",
};

/** Korean copy per reason code. The code itself is always shown next to it (U-6). */
export const REASON_LABEL: Record<ReasonCode, string> = {
  NO_SOURCE_EVENT: "원천 이벤트 없음",
  MISSING_FIELD: "필드 결손",
  NO_COST_BASIS: "원가 근거 없음",
  NEEDS_TWO_STRATEGIES: "비교 전략 2종 필요",
  NEEDS_MODEL_OUTPUT: "모델 산출물 필요",
  PARAM_UNCONFIRMED: "파라미터 미확정",
  BLOCKED: "환경 제약",
  NOT_RUN: "실행하지 않음",
  PRECONDITION_MISSING: "선행 조건 없음",
};
