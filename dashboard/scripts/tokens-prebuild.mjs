/**
 * predev · prebuild 의 토큰 단계 — `Plan/` 없이도 빌드된다 (#207).
 *
 * 이 저장소 고유 파일이다. Ecommerce_Service 에서 이식한 생성기(design-tokens.mjs ·
 * tokens/*.mjs)는 고치지 않고 그대로 부른다 (DG-7 — 이식 로직을 조용히 갈라놓지 않는다).
 *
 *   ../Plan/DESIGN.md 가 있다  → `design-tokens.mjs --check`. 커밋된
 *                                src/styles/tokens.generated.css 가 정본과 다르면 실패한다
 *                                → `npm run tokens:generate` 후 생성물을 함께 커밋한다.
 *   ../Plan/DESIGN.md 가 없다  → 커밋된 생성물을 **정본 대조 없이** 쓴다고 알리고 통과한다.
 *                                Plan 은 private 서브모듈이라 CI · 컨테이너 · 권한 없는
 *                                클론 · 새 git worktree 에는 없다. 대조하지 않은 것을
 *                                대조했다고 적지 않는다 — 그래서 "미실행" 을 출력한다.
 *   생성물 자체가 없다         → 실패. 커밋돼 있어야 하는 파일이 없으면 빌드가 아니라
 *                                체크아웃이 잘못된 것이다.
 *
 * 왜 생성물을 커밋하는가: docs/decisions/DR-207-plan-free-tokens.md.
 */
import { existsSync } from "node:fs";
import { spawnSync } from "node:child_process";
import { join } from "node:path";
import { fileURLToPath } from "node:url";

const app = fileURLToPath(new URL("../", import.meta.url));
const source = join(app, "../Plan/DESIGN.md");
const output = join(app, "src/styles/tokens.generated.css");

if (!existsSync(output)) {
  console.error(
    "src/styles/tokens.generated.css 가 없다 — 커밋돼 있어야 하는 생성물이다 (#207). " +
      "Plan/ 이 있으면 npm run tokens:generate 로 다시 만들고 커밋한다.",
  );
  process.exit(1);
}

if (!existsSync(source)) {
  console.log(
    "tokens:check 미실행 — ../Plan/DESIGN.md 가 없다 (private 서브모듈 미초기화). " +
      "커밋된 src/styles/tokens.generated.css 를 정본 대조 없이 쓴다.",
  );
  process.exit(0);
}

const result = spawnSync(
  process.execPath,
  [join(app, "scripts/design-tokens.mjs"), "--input", source, "--output", output, "--check"],
  { stdio: "inherit" },
);
process.exit(result.status ?? 1);
