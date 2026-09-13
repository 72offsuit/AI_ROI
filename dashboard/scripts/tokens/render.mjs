/**
 * Ported from Ecommerce_Service — do not diverge silently (ADR-0006).
 *
 *   source repo   Ecommerce_Service (separate repository, read-only for this cycle)
 *   source path   scripts/tokens/render.mjs
 *   source commit 6b186d0f20a3d134389ef84b490d9a374c760e37
 *   source sha256 c0ed6edc7970a93091c4a8ca49382181dde5a0abf0f6e256f29b2929e4ad3272
 *
 * The design-token values have exactly one canonical source: Plan/DESIGN.md.
 * Both repositories point their Plan submodule at the same commit, so porting the
 * generator duplicates ~199 lines of code, not a single token value (PRD §69).
 * If you change the logic here, change it in Ecommerce_Service too (DG-7).
 */
import { flattenTokens, resolveTokens, variableName } from "./resolve.mjs";

export function renderTokens(markdown) {
  const tokens = resolveTokens(markdown);
  const entries = flattenTokens(tokens);
  const names = entries.map(([path]) => variableName(path));
  if (new Set(names).size !== names.length) throw new Error("CSS 변수 이름이 중복됩니다.");
  const css = (path) => `var(${variableName(path)})`;
  const theme = [];
  for (const [group, namespace] of [["colors", "color"], ["spacing", "spacing"], ["rounded", "radius"]]) {
    for (const key of Object.keys(tokens[group])) theme.push(`  --${namespace}-${key}: ${css(`${group}.${key}`)};`);
  }
  theme.push(`  --color-foreground: ${css("colors.text")};`);
  theme.push(`  --font-sans: ${css("typography.body-md.fontFamily")};`);
  for (const key of ["commerce-max", "dashboard-max"]) theme.push(`  --container-${key}: ${css(`spacing.${key}`)};`);

  const typography = Object.entries(tokens.typography).map(([key, values]) => {
    const properties = { fontFamily: "font-family", fontSize: "font-size", fontWeight: "font-weight", lineHeight: "line-height" };
    const declarations = Object.entries(properties).map(([property, cssProperty]) => {
      if (typeof values[property] !== "string") throw new Error(`필수 타이포그래피 속성 누락: ${key}.${property}`);
      return `  ${cssProperty}: ${css(`typography.${key}.${property}`)};`;
    });
    declarations.push(`  letter-spacing: ${values.letterSpacing ? css(`typography.${key}.letterSpacing`) : "normal"};`);
    declarations.push(`  font-feature-settings: ${values.fontFeature ? css(`typography.${key}.fontFeature`) : "normal"};`);
    return `@utility text-${key} {\n${declarations.join("\n")}\n}`;
  });

  return [
    `:root {\n${entries.map(([path, value]) => `  ${variableName(path)}: ${value};`).join("\n")}\n}`,
    `@theme inline {\n${theme.join("\n")}\n}`,
    ...typography,
    "",
  ].join("\n\n");
}
