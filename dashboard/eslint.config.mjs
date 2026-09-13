import { defineConfig, globalIgnores } from "eslint/config";
import nextVitals from "eslint-config-next/core-web-vitals";
import nextTs from "eslint-config-next/typescript";

/**
 * Flat ESLint config. Next 16 removed `next lint`, so the `lint` npm script
 * invokes `eslint` directly and this file is what it picks up.
 *
 * Shape copied from Ecommerce_Service/eslint.config.mjs so that both apps fail
 * on the same rules; only the ignore list differs (this app has no test runner).
 */
const eslintConfig = defineConfig([
  ...nextVitals,
  ...nextTs,
  globalIgnores([
    ".next/**",
    "out/**",
    "next-env.d.ts",
    // Generated from Plan/DESIGN.md on every predev/prebuild — never hand-edited (DG-7).
    "src/styles/tokens.generated.css",
    ".fixtures/**",
  ]),
]);

export default eslintConfig;
