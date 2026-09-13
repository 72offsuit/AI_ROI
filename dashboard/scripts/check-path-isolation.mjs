/**
 * Executable check for the one runtime guarantee this app has: `DB-014`.
 *
 * Run: npm run check:isolation
 *
 * Why this exists (issue #64, security finding F1, CVSS 6.5): `resolveArtifactPath`
 * is the only place that turns a contract string into a filesystem path, and the
 * Python isolation suite does not look at `dashboard/` (extending it is decision
 * D-22, still open). So this function *is* the enforcement — human review is the
 * only other layer, and human review already missed a symlink walking straight
 * through every string check it performs.
 *
 * Why a script rather than a test framework: same reason as check-state-map.mjs —
 * these assertions must run with no dependencies installed. Node strips the
 * TypeScript types on import, and `paths.ts` imports only `node:fs`/`node:path`.
 *
 * ★ Each vector is *built on disk and executed*, never asserted against the source
 *   text. Checking that the file contains the word `realpathSync` would pass even
 *   if the call sat somewhere it had no effect — which is how the original defect
 *   survived review.
 */
import assert from "node:assert/strict";
import { mkdirSync, mkdtempSync, rmSync, symlinkSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

const sandbox = mkdtempSync(join(tmpdir(), "airoi-isolation-"));
const results = join(sandbox, "results");
const hidden = join(sandbox, "data", "hidden");

mkdirSync(join(results, "measurement"), { recursive: true });
mkdirSync(hidden, { recursive: true });
writeFileSync(join(hidden, "secret.json"), '{"SECRET":"ground truth"}');
writeFileSync(join(results, "measurement", "real.json"), '{"ok":1}');

// The attack: a link inside results/ aimed at a directory DB-014 forbids.
symlinkSync(join(hidden, "secret.json"), join(results, "measurement", "leak.json"));
// A link aimed at a *directory* outside, so a deeper path escapes through it.
symlinkSync(hidden, join(results, "escape"));

process.env.AIROI_RESULTS_DIR = results;
const { resolveArtifactPath, IsolationError } = await import(
  "../src/lib/artifacts/paths.ts"
);

let passed = 0;

function allows(name, relative) {
  assert.doesNotThrow(
    () => resolveArtifactPath(relative),
    `${name}: 정상 경로가 거부됐다 — 격리가 지나치게 넓으면 화면이 빈다`,
  );
  passed += 1;
  console.log(`PASS  허용  ${name}`);
}

function rejects(name, relative) {
  let thrown;
  try {
    resolveArtifactPath(relative);
  } catch (error) {
    thrown = error;
  }
  assert.ok(thrown, `${name}: 거부되어야 하는데 통과했다 — DB-014 우회다`);
  assert.ok(
    thrown instanceof IsolationError,
    `${name}: IsolationError 가 아닌 ${thrown?.constructor?.name} 가 났다. ` +
      "격리 위반은 다른 오류와 구분되어야 한다",
  );
  passed += 1;
  console.log(`PASS  차단  ${name}`);
}

// ── 허용되어야 하는 것 ────────────────────────────────────────────────────
// 존재하지 않는 경로가 대부분이다 — 호출자가 resolve 한 뒤 ENOENT 를 처리한다.
// 이 셋이 막히면 게시 전 화면이 통째로 죽는다.
allows("존재하는 파일", "results/measurement/real.json");
allows("아직 없는 파일", "results/measurement/absent.json");
allows("아직 없는 하위 디렉터리", "results/nope/deep/x.json");
allows("results 루트 자신", "results/");

// ── 차단되어야 하는 것 ────────────────────────────────────────────────────
// ★ 심볼릭 링크 2종이 이 스크립트의 존재 이유다. 나머지 넷은 원래도 막혔고,
//   회귀로 열리지 않게 함께 고정한다.
rejects("심볼릭 링크가 파일을 가리킴", "results/measurement/leak.json");
rejects("심볼릭 링크가 디렉터리를 가리킴", "results/escape/secret.json");
rejects("상위 이동으로 탈출", "results/../../etc/passwd");
rejects("절대 경로", "/etc/passwd");
rejects("results/ 접두사 없음", "measurement/x.json");
rejects("data/processed (C1 미게시)", "data/processed/x.json");

// ── 검사 자체가 비어 있지 않은지 ─────────────────────────────────────────
// 0 건을 검사하고 통과하는 것이 이 저장소가 반복해 겪은 실패 양식이다.
assert.ok(passed >= 10, `검사 건수가 ${passed} 건이다 — 벡터가 사라졌다`);

rmSync(sandbox, { recursive: true, force: true });
console.log(`\n${passed} 건 통과 — DB-014 런타임 강제가 살아 있다.`);
