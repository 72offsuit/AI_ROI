import { resolve } from "node:path";

const dashboardDir = resolve(__dirname, "..", "dashboard");
const reposRoot = resolve(__dirname, "..");

export interface Dataset {
  name: "empty-sink" | "commerce-connected" | "real";
  port: number;
  resultsDir: string;
  /** Whether this dataset's input events are synthetic (drives the sample-data badge). */
  fixtureMode: boolean;
}

export const datasets: Dataset[] = [
  { name: "empty-sink", port: 4601, resultsDir: resolve(dashboardDir, ".fixtures/empty-sink/results"), fixtureMode: true },
  { name: "commerce-connected", port: 4602, resultsDir: resolve(dashboardDir, ".fixtures/commerce-connected/results"), fixtureMode: true },
  { name: "real", port: 4603, resultsDir: resolve(reposRoot, "results"), fixtureMode: false },
];

export const ROUTES = [
  "/",
  "/ingestion",
  "/rejections",
  "/coverage",
  "/kpi",
  "/quality",
  "/freeze",
  "/triggers",
] as const;

export const dashboardDirPath = dashboardDir;
export const reposRootPath = reposRoot;
