/**
 * Ported from Ecommerce_Service — do not diverge silently (ADR-0006).
 *
 *   source repo   Ecommerce_Service (separate repository, read-only for this cycle)
 *   source path   scripts/tokens/resolve.mjs
 *   source commit 6b186d0f20a3d134389ef84b490d9a374c760e37
 *   source sha256 ce07d675c9b86b94d3d6debeabde0836bee684fa87a6aa79d3d47c7ab1f3ba2a
 *
 * The design-token values have exactly one canonical source: Plan/DESIGN.md.
 * Both repositories point their Plan submodule at the same commit, so porting the
 * generator duplicates ~199 lines of code, not a single token value (PRD §69).
 * If you change the logic here, change it in Ecommerce_Service too (DG-7).
 */
import { JSON_SCHEMA, load } from "js-yaml";

const groups = ["colors", "typography", "spacing", "rounded", "components"];
const reference = /^\{([\w.-]+)\}$/;
const isObject = (value) => value !== null && typeof value === "object" && !Array.isArray(value);

export function variableName(path) {
  return `--ds-${path.replaceAll(".", "-").replace(/[A-Z]/g, (letter) => `-${letter.toLowerCase()}`)}`;
}

export function resolveTokens(markdown) {
  const frontmatter = markdown.match(/^---\r?\n([\s\S]*?)\r?\n---(?:\r?\n|$)/);
  if (!frontmatter) throw new Error("DESIGN.md의 YAML frontmatter가 없습니다.");
  const source = load(frontmatter[1], { schema: JSON_SCHEMA });
  for (const group of groups) {
    if (!isObject(source?.[group]) || !Object.keys(source[group]).length) {
      throw new Error(`토큰 그룹이 없거나 올바르지 않습니다: ${group}`);
    }
  }

  function read(path) {
    let value = source;
    for (const key of path.split(".")) {
      if (!isObject(value) || !Object.hasOwn(value, key)) {
        throw new Error(`참조 토큰이 없습니다: ${path}`);
      }
      value = value[key];
    }
    if (!groups.includes(path.split(".")[0])) throw new Error(`지원하지 않는 참조: ${path}`);
    return value;
  }

  function resolve(path, ancestors = []) {
    if (ancestors.includes(path)) throw new Error(`순환 참조: ${[...ancestors, path].join(" → ")}`);
    const value = read(path);
    const chain = [...ancestors, path];
    if (isObject(value)) {
      if (!Object.keys(value).length) throw new Error(`빈 토큰 객체: ${path}`);
      return Object.fromEntries(Object.keys(value).sort().map((key) => {
        if (!/^[a-zA-Z0-9]+(?:-[a-zA-Z0-9]+)*$/.test(key)) throw new Error(`잘못된 토큰 이름: ${path}.${key}`);
        return [key, resolve(`${path}.${key}`, chain)];
      }));
    }
    const target = typeof value === "string" && value.match(reference)?.[1];
    if (target) {
      const resolved = resolve(target, chain);
      function alias(node, targetPath) {
        return isObject(node)
          ? Object.fromEntries(Object.entries(node).map(([key, child]) => [key, alias(child, `${targetPath}.${key}`)]))
          : `var(${variableName(targetPath)})`;
      }
      return alias(resolved, target);
    }
    if ((typeof value !== "string" && typeof value !== "number") || !String(value).length || /[{};\r\n]/.test(String(value))) {
      throw new Error(`잘못된 토큰 값: ${path}`);
    }
    if (path.endsWith(".fontFamily") && value === "Pretendard") {
      return 'var(--font-pretendard, Pretendard), -apple-system, BlinkMacSystemFont, system-ui, sans-serif';
    }
    return String(value);
  }

  return Object.fromEntries(groups.map((group) => [group, resolve(group)]));
}

export function flattenTokens(tokens, prefix = "") {
  return Object.entries(tokens).flatMap(([key, value]) => {
    const path = prefix ? `${prefix}.${key}` : key;
    return isObject(value) ? flattenTokens(value, path) : [[path, value]];
  });
}
