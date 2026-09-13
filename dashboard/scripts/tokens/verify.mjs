/**
 * Ported from Ecommerce_Service — do not diverge silently (ADR-0006).
 *
 *   source repo   Ecommerce_Service (separate repository, read-only for this cycle)
 *   source path   scripts/tokens/verify.mjs
 *   source commit 6b186d0f20a3d134389ef84b490d9a374c760e37
 *   source sha256 d777aa8812e0e32ddde75a2c903f8eeabcafaad6bb5008c3dddb4615a0a8c27f
 *
 * The design-token values have exactly one canonical source: Plan/DESIGN.md.
 * Both repositories point their Plan submodule at the same commit, so porting the
 * generator duplicates ~199 lines of code, not a single token value (PRD §69).
 * If you change the logic here, change it in Ecommerce_Service too (DG-7).
 *
 * ★ ONE LINE DIFFERS FROM THE ORIGINAL — see the marked line below.
 *   `root` is used for two different anchors: line ~9 wants the repository root
 *   (to read Plan/DESIGN.md) and line ~15 wants the app root (to spawn
 *   scripts/design-tokens.mjs). In Ecommerce_Service both live under the same
 *   parent, so `../../` satisfied both. Here the generator sits at
 *   dashboard/scripts/ and Plan/ sits at the repository root, one level above
 *   dashboard/ — so `root` resolves to dashboard/ and the unmodified file dies with
 *       Error: ENOENT ... open '.../dashboard/Plan/DESIGN.md'
 *   Changing `root` itself would break the spawn path instead, so only the
 *   Plan/DESIGN.md read is re-anchored with a leading '../'.
 *   Verified: 15 scenarios passed after this change.
 */
import assert from 'node:assert/strict';
import { mkdtemp, readFile, writeFile, stat, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { spawnSync } from 'node:child_process';

const root = fileURLToPath(new URL('../../', import.meta.url));
const source = await readFile(join(root, '../Plan/DESIGN.md')  /* ★ ported-file change: '../' added — see header */, 'utf8');
const dir = await mkdtemp(join(tmpdir(), 'design-tokens-'));
const input = join(dir, 'DESIGN.md');
const output = join(dir, 'tokens.css');
let passed = 0;
function run(...args) {
  return spawnSync(process.execPath, [join(root, 'scripts/design-tokens.mjs'), '--input', input, '--output', output, ...args], { encoding: 'utf8' });
}
function ok(name, action) {
  action();
  passed++;
  console.log(`PASS ${name}`);
}
try {
  await writeFile(input, source);
  ok('missing output is rejected by check', () => assert.equal(run('--check').status, 1));
  await assert.rejects(stat(output), { code: 'ENOENT' });
  ok('valid source generates output', () => assert.equal(run().status, 0));
  const first = await readFile(output, 'utf8');
  const firstStat = await stat(output);
  ok('matching output passes check', () => assert.equal(run('--check').status, 0));
  assert.equal((await stat(output)).mtimeMs, firstStat.mtimeMs);
  ok('repeated generation succeeds', () => assert.equal(run().status, 0));
  assert.equal(await readFile(output, 'utf8'), first);
  assert.equal((await stat(output)).mtimeMs, firstStat.mtimeMs);
  ok('scalar aliases preserve variable references', () => assert.match(first, /--ds-colors-surface: var\(--ds-colors-background\);/));
  ok('object references expand into properties', () => assert.match(first, /--ds-components-button-primary-typography-font-size: var\(--ds-typography-label-md-font-size\);/));
  ok('typography includes tnum and normal defaults', () => {
    assert.match(first, /@utility text-price \{[^}]*font-feature-settings: var\(--ds-typography-price-font-feature\)/);
    assert.match(first, /@utility text-headline-sm \{[^}]*letter-spacing: normal/);
  });
  await writeFile(input, source.replace('"#6A00F4"', '"#6200F4"'));
  ok('changed source is detected without rewriting', () => assert.equal(run('--check').status, 1));
  assert.equal(await readFile(output, 'utf8'), first);
  const failures = [
    ['missing reference', source.replace('"{colors.background}"', '"{colors.missing}"'), /참조 토큰이 없습니다/],
    ['scalar cycle', source.replace('"#FFFFFF"', '"{colors.surface}"'), /순환 참조/],
    ['object cycle', source.replace('"{typography.label-md}"', '"{components.button-primary}"'), /순환 참조/],
    ['invalid YAML', source.replace('primary: "#6A00F4"', 'primary: [unclosed'), /missed comma between flow collection entries/],
    ['missing frontmatter', 'hello', /frontmatter/],
    ['duplicate YAML key', source.replace('colors:', 'colors:\n  primary: duplicate'), /duplicated mapping key/],
    ['missing typography property', source.replace('    fontSize: 1rem\n', ''), /필수 타이포그래피 속성 누락/],
  ];
  for (const [name, content, message] of failures) {
    await writeFile(input, content);
    const result = run();
    ok(name, () => { assert.equal(result.status, 1); assert.match(result.stderr, message); });
    assert.equal(await readFile(output, 'utf8'), first);
  }
  console.log(`${passed} scenarios passed; failed input and --check preserved output.`);
} finally {
  await rm(dir, { recursive: true, force: true });
}
