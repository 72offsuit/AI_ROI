/**
 * Executable check for the two pieces of non-obvious logic in this app:
 * the contract -> visual state mapping, and the value slot rules that keep a
 * missing measurement from turning into a zero.
 *
 * Run: npm run check:state-map
 *
 * Why this exists rather than a test framework: these are the assertions that fail
 * the moment someone "fixes" a null-pointer exception with `?? 0`, and they need to
 * be runnable with no dependencies. Node strips the TypeScript types on import; the
 * only `@/…` imports in the modules under test are type-only, so they erase cleanly.
 */
import assert from "node:assert/strict";

import { deriveCheckState, deriveMetricState } from "../src/lib/format/state.ts";
import {
  EM_DASH,
  NOT_RUN_TEXT,
  PENDING_CONTRACT_TEXT,
  formatMetricValue,
} from "../src/lib/format/metric.ts";

let passed = 0;
function ok(name, action) {
  action();
  passed++;
  console.log(`PASS ${name}`);
}

const basis = {
  population: "coupon_use 이벤트",
  denominator_definition: "분모 없음 (건수)",
  denominator: null,
  observed_count: 0,
  window: { direction: "retrospective", days: 42 },
};

/* ── 1. metric_value (status, reason_code) -> visual state ──────────────── */

ok("ok -> available", () => assert.equal(deriveMetricState("ok", undefined), "available"));
ok("unconfirmed -> provisional", () =>
  assert.equal(deriveMetricState("unconfirmed", "PARAM_UNCONFIRMED"), "provisional"));
ok("NO_COST_BASIS -> gap", () =>
  assert.equal(deriveMetricState("unavailable", "NO_COST_BASIS"), "gap"));
ok("MISSING_FIELD -> gap", () =>
  assert.equal(deriveMetricState("unavailable", "MISSING_FIELD"), "gap"));
ok("NO_SOURCE_EVENT -> unconnected", () =>
  assert.equal(deriveMetricState("unavailable", "NO_SOURCE_EVENT"), "unconnected"));
ok("NEEDS_MODEL_OUTPUT -> planned", () =>
  assert.equal(deriveMetricState("unavailable", "NEEDS_MODEL_OUTPUT"), "planned"));
ok("NEEDS_TWO_STRATEGIES -> planned", () =>
  assert.equal(deriveMetricState("unavailable", "NEEDS_TWO_STRATEGIES"), "planned"));
ok("PRECONDITION_MISSING -> planned", () =>
  assert.equal(deriveMetricState("unavailable", "PRECONDITION_MISSING"), "planned"));
ok("blocked -> env_blocked", () =>
  assert.equal(deriveMetricState("blocked", "BLOCKED"), "env_blocked"));
ok("not_run -> not_run", () => assert.equal(deriveMetricState("not_run", "NOT_RUN"), "not_run"));
ok("unavailable without reason_code -> violation (schema requires one)", () =>
  assert.equal(deriveMetricState("unavailable", undefined), "violation"));

/* ── 2. check status is a separate axis ─────────────────────────────────── */

ok("check pass -> ok", () => assert.equal(deriveCheckState("pass"), "ok"));
ok("check fail -> violation", () => assert.equal(deriveCheckState("fail"), "violation"));
ok("★ check vacuous -> unconnected (neither green nor red)", () =>
  assert.equal(deriveCheckState("vacuous"), "unconnected"));
ok("check not_run -> not_run", () => assert.equal(deriveCheckState("not_run"), "not_run"));
ok("check blocked -> env_blocked", () => assert.equal(deriveCheckState("blocked"), "env_blocked"));

/* ── 3. ★ the zero-fill rules ───────────────────────────────────────────── */

ok("★ a measured 0 renders as the published string, not an em dash", () => {
  const d = formatMetricValue({
    status: "ok", value: 0, unit: "count", basis, value_formatted: "0건",
  });
  assert.equal(d.valueText, "0건");
  assert.equal(d.state, "available");
  assert.equal(d.isPublishedValue, true);
  assert.deepEqual(d.violations, []);
});

ok("★ uncomputable renders an em dash and never the character 0", () => {
  const d = formatMetricValue({
    status: "unavailable", value: null, unit: "krw",
    reason_code: "NO_COST_BASIS", reason_detail: "cogs 를 계산할 수 없다.",
  });
  assert.equal(d.valueText, EM_DASH);
  assert.equal(d.state, "gap");
  assert.equal(d.isPublishedValue, false);
  assert.equal(d.valueText.includes("0"), false);
  assert.equal(d.basisText, undefined, "계산 불가에는 기준이 있을 수 없다");
});

ok("★ not_run says 미실행, not an em dash — absent and unknown differ", () => {
  const d = formatMetricValue({
    status: "not_run", value: null, unit: "text",
    reason_code: "NOT_RUN", reason_detail: "실행하지 않았다.",
  });
  assert.equal(d.valueText, NOT_RUN_TEXT);
  assert.notEqual(d.valueText, EM_DASH);
});

ok("★ a value arriving on an uncomputable status is suppressed and flagged", () => {
  const d = formatMetricValue({
    status: "unavailable", value: 0, unit: "krw",
    reason_code: "NO_COST_BASIS", reason_detail: "publisher bug",
  });
  assert.equal(d.valueText, EM_DASH, "0 must never reach the value slot");
  assert.equal(d.state, "violation");
  assert.ok(d.violations.some((v) => v.includes("계산 불가 상태에 값이 왔습니다")));
});

ok("★ observed_count 0 stays in the basis line (evidence of a counted zero)", () => {
  const d = formatMetricValue({
    status: "ok", value: 0, unit: "count", basis, value_formatted: "0건",
  });
  assert.ok(d.basisText.includes("관측 0건"), `basis line dropped the zero: ${d.basisText}`);
});

ok("null denominator is omitted entirely rather than shown as 0", () => {
  const d = formatMetricValue({
    status: "ok", value: 0, unit: "count", basis, value_formatted: "0건",
  });
  assert.equal(d.basisText.includes("분모 0"), false);
});

ok("a computed value without a basis is flagged, not silently accepted", () => {
  const d = formatMetricValue({ status: "ok", value: 1, unit: "count", value_formatted: "1건" });
  assert.ok(d.violations.some((v) => v.includes("기준 미표기")));
});

ok("value_formatted absent -> placeholder, never a self-formatted number", () => {
  const d = formatMetricValue({ status: "ok", value: 41283400, unit: "krw", basis });
  assert.equal(d.valueText, PENDING_CONTRACT_TEXT);
  assert.equal(d.valueText.includes("41283400"), false);
  assert.equal(d.isPublishedValue, false);
  assert.ok(d.violations.some((v) => v.includes("value_formatted")));
});

ok("unconfirmed without params_used is flagged (R-10)", () => {
  const d = formatMetricValue({
    status: "unconfirmed", value: 0.1834, unit: "ratio", basis,
    reason_code: "PARAM_UNCONFIRMED", reason_detail: "임계값 미확정", value_formatted: "18.3%",
  });
  assert.ok(d.violations.some((v) => v.includes("params_used")));
});

console.log(`\n${passed} assertions passed.`);
