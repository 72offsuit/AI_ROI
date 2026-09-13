/**
 * Tailwind v4 runs as a PostCSS plugin. Ported as-is from Ecommerce_Service so
 * that the design tokens generated from Plan/DESIGN.md (which emit
 * `@theme inline` blocks) are interpreted identically in both repositories.
 */
const config = {
  plugins: ["@tailwindcss/postcss"],
};

export default config;
