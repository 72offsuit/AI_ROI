/**
 * Ported from Ecommerce_Service — do not diverge silently (ADR-0006).
 *
 *   source repo   Ecommerce_Service (separate repository, read-only for this cycle)
 *   source path   scripts/design-tokens.mjs
 *   source commit 6b186d0f20a3d134389ef84b490d9a374c760e37
 *   source sha256 b17ab2e4122b8c467d45e537b57b81195eaec1cca2d3219d338f9e6baed29c66
 *
 * The design-token values have exactly one canonical source: Plan/DESIGN.md.
 * Both repositories point their Plan submodule at the same commit, so porting the
 * generator duplicates ~199 lines of code, not a single token value (PRD §69).
 * If you change the logic here, change it in Ecommerce_Service too (DG-7).
 */
import { mkdir, readFile, writeFile } from "node:fs/promises";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { parseArgs } from "node:util";
import { renderTokens } from "./tokens/render.mjs";

const root = fileURLToPath(new URL("../", import.meta.url));

try {
  const { values } = parseArgs({ options: { check: { type: "boolean", default: false }, input: { type: "string" }, output: { type: "string" } } });
  const input = resolve(root, values.input ?? "Plan/DESIGN.md");
  const output = resolve(root, values.output ?? "src/styles/tokens.generated.css");
  const expected = renderTokens(await readFile(input, "utf8"));
  let current;
  try {
    current = await readFile(output, "utf8");
  } catch (error) {
    if (error.code !== "ENOENT") throw error;
  }
  if (values.check) {
    if (current !== expected) throw new Error("생성 토큰이 없거나 정본과 다릅니다. npm run tokens:generate를 실행하세요.");
    console.log("디자인 토큰이 정본과 일치합니다.");
  } else {
    if (current !== expected) {
      await mkdir(dirname(output), { recursive: true });
      await writeFile(output, expected);
    }
    console.log("디자인 토큰 생성 완료");
  }
} catch (error) {
  console.error(error.message);
  process.exitCode = 1;
}
