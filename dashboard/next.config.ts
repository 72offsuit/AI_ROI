import type { NextConfig } from "next";

/**
 * Next.js 16 configuration for the AI_ROI observability dashboard.
 *
 * Deliberately empty: Next 16 makes Turbopack the default and ignores custom
 * webpack config, so adding knobs here would be silently dead code. The two
 * behaviours this app actually depends on are set where they belong instead:
 *   - port 3001 -> the `dev`/`start` npm scripts (3000 is taken by Ecommerce_Service)
 *   - no caching -> `export const dynamic = "force-dynamic"` in every route (DB-011)
 */
const nextConfig: NextConfig = {};

export default nextConfig;
