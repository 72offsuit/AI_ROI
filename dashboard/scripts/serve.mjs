/**
 * `npm run dev` · `npm start` 실행기 — 바인딩 주소를 환경변수로 바꿀 수 있게 한다 (#207).
 *
 *   node scripts/serve.mjs dev|start
 *
 * 포트는 3001 고정이다(DB-002 · 3000 은 Ecommerce_Service). 바뀌는 것은 주소 하나:
 *
 *   AIROI_DASHBOARD_HOST   비어 있으면 127.0.0.1 — 로컬에서는 지금처럼 밖으로 열지 않는다.
 *                          컨테이너는 0.0.0.0 (Dockerfile 이 설정한다). 컨테이너 루프백에
 *                          묶이면 포트 매핑이 닿지 않는다.
 *
 * 왜 npm 스크립트 안의 `${AIROI_DASHBOARD_HOST:-127.0.0.1}` 이 아닌가: npm 은 Windows 에서
 * 스크립트를 cmd.exe 로 돌려 그 문법이 글자 그대로 next 에 넘어간다 — 지금 Windows 에서도
 * 도는 `npm run dev` 가 깨진다. 이 파일은 node 만 있으면 어디서나 같다.
 *
 * next 는 dashboard/ 를 cwd 로 띄운다. `src/lib/artifacts/paths.ts` 의 기본 results 경로가
 * cwd 기준(`../results`)이라, 어디서 이 파일을 불러도 같은 곳을 읽게 하기 위해서다.
 *
 * ★ 컨테이너에서는 이 프로세스가 PID 1 이다. SIGTERM · SIGINT 를 next 에 넘기고 next 의
 *   종료 코드로 끝난다 — 넘기지 않으면 `docker stop` 이 10초를 기다린 뒤 강제 종료한다.
 */
import { spawn } from "node:child_process";
import { createRequire } from "node:module";
import { fileURLToPath } from "node:url";

const PORT = "3001";
const DEFAULT_HOST = "127.0.0.1";

const mode = process.argv[2];
if (mode !== "dev" && mode !== "start") {
  console.error("사용법: node scripts/serve.mjs <dev|start>");
  process.exit(2);
}

const host = process.env.AIROI_DASHBOARD_HOST?.trim() || DEFAULT_HOST;
const app = fileURLToPath(new URL("../", import.meta.url));
const next = createRequire(import.meta.url).resolve("next/dist/bin/next");

const child = spawn(process.execPath, [next, mode, "--port", PORT, "--hostname", host], {
  cwd: app,
  stdio: "inherit",
});
for (const signal of ["SIGINT", "SIGTERM"]) {
  process.on(signal, () => child.kill(signal));
}
child.on("exit", (code, signal) => process.exit(code ?? (signal ? 1 : 0)));
