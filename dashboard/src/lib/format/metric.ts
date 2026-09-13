/**
 * Turns a contract `metric_value` into everything the UI needs to draw one cell.
 *
 * ★ This file is where the project's single largest risk lives.
 *
 * The contract guarantees `value: null` whenever a metric could not be computed.
 * `(null).toLocaleString()` throws, so the natural reflex is to write `value ?? 0`
 * — and that one line converts "we could not measure this" into "we measured zero",
 * which is the exact claim this whole repository exists to avoid making.
 *
 * The right way to stop the exception is a branch, not a default. Nothing in this
 * module ever substitutes a value; when there is no value it says so, in the same
 * type size as a value (V-1), because shrinking or greying the absence is the polite
 * version of the same lie.
 *
 * Forbidden everywhere in this app:
 *   value ?? 0 · value || 0 · Number(value) · parseFloat(v) || 0
 *   counts[k] || 0 · value.toFixed(1) · (value ?? 0).toLocaleString()
 */
import type { Basis, MetricValue, ReasonCode } from "@/lib/artifacts/types";
import { deriveMetricState, type VisualState } from "./state.ts";

/** U+2014 EM DASH. Not a hyphen, not a minus sign. */
export const EM_DASH = "—";

/** `not_run` says "unknown", which is a different fact from "absent" — so not EM_DASH. */
export const NOT_RUN_TEXT = "미실행";

/**
 * Shown in the value slot while the publisher cannot yet supply a formatted string.
 *
 * `value_formatted` is not in the contract as of 2026-09-11; M-06 §4.16 adds it. Until
 * then a computed metric has a number but no presentable form, and formatting it here
 * would mean the screen deciding currency/decimals/separators — a calculation (DB-012)
 * and the on-ramp to `?? 0`. So the cell states the contract is not ready instead of
 * inventing a rendering.
 *
 * ponytail: renders a placeholder for every ok/unconfirmed metric until the contract
 * carries value_formatted; delete nothing when M-06 lands — the branch below simply
 * stops being taken. Revisit if M-06 ships a different field name.
 */
export const PENDING_CONTRACT_TEXT = "계약 준비 중";

export interface MetricDisplay {
  state: VisualState;
  /** Exactly what goes in the value slot. Always a string this app did not compute. */
  valueText: string;
  /** True only when valueText is a published value, not a placeholder. */
  isPublishedValue: boolean;
  reasonCode?: ReasonCode;
  reasonDetail?: string;
  /** "기준: …" evidence line. Present iff the publisher supplied a basis. */
  basisText?: string;
  paramsUsed?: [string, string][];
  derived: boolean;
  derivation?: string;
  limitNote?: string;
  blockedBy: { kind: string; ref: string; reasonCode: ReasonCode }[];
  /**
   * Contract breaches this cell found in its own input (V-3). Rendered inline, never
   * swallowed — the dashboard checking its input is the last place a zero-fill can be
   * caught, and R-10 explicitly sanctions it (presence checks, not recomputation).
   */
  violations: string[];
}

/**
 * Renders an integer the publisher supplied as evidence (denominator, observed_count).
 *
 * ★ `typeof n === "number"`, never truthiness: `observed_count: 0` is the whole point
 * of rule V-2 ("we counted and found none") and must print "0", while `null` must make
 * the clause disappear entirely rather than print "0".
 *
 * No thousands separators: `toLocaleString()` depends on the host locale, so the same
 * artifact would render differently on two machines and screenshots would stop being
 * reproducible evidence. Separators belong to the publisher's formatting step.
 */
function countText(n: number | null | undefined): string | undefined {
  if (typeof n !== "number" || Number.isNaN(n)) return undefined;
  return String(n);
}

/**
 * Composes the evidence line from fields the publisher already supplied.
 * This is sentence assembly, not arithmetic — nothing here derives a new quantity.
 */
function buildBasisText(basis: Basis): string {
  const parts: string[] = [basis.population, basis.denominator_definition];

  const denominator = countText(basis.denominator);
  if (denominator !== undefined) parts.push(`분모 ${denominator}`);

  const observed = countText(basis.observed_count);
  if (observed !== undefined) parts.push(`관측 ${observed}건`);

  if (basis.window.label !== undefined) {
    parts.push(basis.window.label);
  } else {
    const days = countText(basis.window.days);
    if (days !== undefined) parts.push(`${days}일 구간`);
  }

  const excluded = countText(basis.excluded_count);
  if (excluded !== undefined) {
    const why = basis.excluded_reason === undefined ? "사유 미표기" : basis.excluded_reason;
    parts.push(`제외 ${excluded}건 (${why})`);
  }
  return `기준: ${parts.join(" · ")}`;
}

/** Statuses for which the schema requires `value: null`. */
const UNCOMPUTABLE = new Set(["unavailable", "blocked", "not_run"]);

/**
 * The only path from contract data to a value slot.
 *
 * Expected results:
 *   {status:"ok", value:0, unit:"count", basis:{…}, value_formatted:"0건"}
 *     -> valueText "0건",   state "available", basisText present
 *   {status:"ok", value:0, unit:"count", basis:{…}}            // M-06 not shipped
 *     -> valueText "계약 준비 중", state "available", one violation
 *   {status:"unavailable", value:null, reason_code:"NO_COST_BASIS", …}
 *     -> valueText "—",     state "gap"
 *   {status:"not_run", value:null, reason_code:"NOT_RUN", …}
 *     -> valueText "미실행", state "not_run"
 *   {status:"unavailable", value:0, …}                          // publisher bug
 *     -> valueText "—",     state "violation" appended, value never shown
 */
export function formatMetricValue(metric: MetricValue): MetricDisplay {
  const violations: string[] = [];
  let state = deriveMetricState(metric.status, metric.reason_code);
  const uncomputable = UNCOMPUTABLE.has(metric.status);

  let valueText: string;
  let isPublishedValue = false;

  if (uncomputable) {
    // Defence in depth: read.ts already refuses to load this shape, but if a value
    // ever reaches here it is suppressed rather than printed (components.md check 3).
    if (metric.value !== null && metric.value !== undefined) {
      violations.push("계산 불가 상태에 값이 왔습니다");
      state = "violation";
    }
    valueText = metric.status === "not_run" ? NOT_RUN_TEXT : EM_DASH;
  } else if (typeof metric.value_formatted === "string" && metric.value_formatted.length > 0) {
    // The publisher already decided currency, decimals and separators. Print verbatim.
    valueText = metric.value_formatted;
    isPublishedValue = true;
  } else {
    valueText = PENDING_CONTRACT_TEXT;
    violations.push("계약 준비 중 — value_formatted 가 게시물에 없습니다 (M-06 에서 추가)");
  }

  // V-3 — a computed value without evidence is our own contract violation, shown
  // beside the value instead of being quietly accepted.
  let basisText: string | undefined;
  if (metric.basis !== undefined) {
    basisText = buildBasisText(metric.basis);
  } else if (!uncomputable) {
    violations.push("기준 미표기 — 분모를 확인할 수 없습니다");
  }

  // R-10 — an unconfirmed value must disclose which unconfirmed parameters produced it.
  let paramsUsed: [string, string][] | undefined;
  if (metric.params_used !== undefined) {
    paramsUsed = Object.entries(metric.params_used).map(([k, v]) => [k, String(v)]);
  } else if (metric.status === "unconfirmed") {
    violations.push("params_used 미표기 — 어떤 파라미터로 계산했는지 알 수 없습니다");
  }

  const derived = metric.derived === true;
  if (derived && metric.derivation === undefined) {
    violations.push("derived: true 인데 derivation 이 없습니다");
  }

  return {
    state,
    valueText,
    isPublishedValue,
    reasonCode: metric.reason_code,
    reasonDetail: metric.reason_detail,
    basisText,
    paramsUsed,
    derived,
    derivation: metric.derivation,
    limitNote: metric.limit_note,
    blockedBy: (metric.blocked_by === undefined ? [] : metric.blocked_by).map((b) => ({
      kind: b.kind,
      ref: b.ref,
      reasonCode: b.reason_code,
    })),
    violations,
  };
}

/**
 * Action line per reason code.
 *
 * V-8 — a cell in gap/env_blocked/not_run/violation must never leave this blank, because
 * a blank reads as "no action needed". When nothing is known, it says so out loud.
 */
export function actionFor(reasonCode: ReasonCode | undefined): string {
  switch (reasonCode) {
    case "NO_COST_BASIS":
      return "조치: 원가 근거 확보 — Ecommerce_Service #24 (주문 경제성 필드)";
    case "MISSING_FIELD":
      return "조치: 결손 필드 수신 — /coverage 의 결손 행과 schema_gaps 참조";
    case "NO_SOURCE_EVENT":
      return "조치: 이벤트 연결 — Ecommerce_Service #28 (이벤트 기록 미구현)";
    case "NEEDS_TWO_STRATEGIES":
      return "조치: 없음 — 비교 전략 2종은 이후 사이클 범위입니다";
    case "NEEDS_MODEL_OUTPUT":
      return "조치: 없음 — 모델 산출물은 이후 사이클 범위입니다";
    case "PRECONDITION_MISSING":
      return "조치: 선행 산출물 게시 후 재확인";
    case "PARAM_UNCONFIRMED":
      return "조치: GATE 1 에서 파라미터 확정";
    case "BLOCKED":
      return "조치: 환경 제약 해소 후 재실행";
    case "NOT_RUN":
      return "조치: 해당 검사·계산 실행";
    default:
      return "조치 미정";
  }
}
