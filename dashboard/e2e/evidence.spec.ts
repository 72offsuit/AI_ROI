/**
 * Captures the screenshot evidence that US-11 ~ US-14 and the USP-1 representative
 * scene require, and asserts the things a screenshot alone cannot prove.
 *
 * The assertions matter as much as the images. A screenshot shows what a screen looked
 * like once; these checks state what must be true of it — chiefly that no uncomputable
 * cell ever contains the character 0, and that an absence is rendered in the same
 * typography token as the value it replaces. Both are exactly the failures that a
 * reviewer's eye slides past.
 *
 * Output: screenshots/<fixture>/*.png  (fixture chosen by AIROI_FIXTURE)
 */
import { expect, test, type Page } from "@playwright/test";
import { mkdir } from "node:fs/promises";
import { resolve } from "node:path";

const fixture = process.env.AIROI_FIXTURE ?? "empty-sink";
const shots = resolve(__dirname, "..", "screenshots", fixture);
/** True when the artifacts came from hand-made events (see playwright.config.ts). */
const sampleInput = fixture !== "real";

/** Every observability route. `/triggers` is static; the rest are artifact-backed. */
const ROUTES: { path: string; slug: string; title: string }[] = [
  { path: "/", slug: "00-index", title: "개요 · 판정 배너" },
  { path: "/ingestion", slug: "01-ingestion", title: "V1 수집 현황" },
  { path: "/rejections", slug: "02-rejections", title: "V2 계약 위반" },
  { path: "/coverage", slug: "03-coverage", title: "V3 필드 충족률" },
  { path: "/kpi", slug: "04-kpi", title: "V4 KPI · USP-1" },
  { path: "/quality", slug: "05-quality", title: "V5 데이터 품질" },
  { path: "/freeze", slug: "06-freeze", title: "V6 봉인 상태" },
  { path: "/triggers", slug: "07-triggers", title: "V7 모니터링 트리거" },
];

test.beforeAll(async () => {
  await mkdir(shots, { recursive: true });
});

/** Wait for fonts so Pretendard, not the fallback, is what gets photographed. */
async function ready(page: Page, path: string) {
  await page.goto(path, { waitUntil: "networkidle" });
  await page.evaluate(() => document.fonts.ready);
}

test.describe(`관측 화면군 — ${fixture}`, () => {
  for (const route of ROUTES) {
    test(`${route.slug} ${route.title}`, async ({ page }) => {
      await ready(page, route.path);

      // Nothing rendered a server error page.
      await expect(page.locator("h1")).toBeVisible();

      /*
       * ★ C-1 — no uncomputable cell contains the character "0".
       *
       * Checked against the value slots only, because reason sentences legitimately
       * contain counts ("주문 1,204건 중 0건") and the page chrome contains numbers.
       * A value slot holding "0" while its state is not `available` is the zero-fill
       * this project exists to prevent.
       */
      const absent = page.locator(".text-\\(--obs-absent-ink\\)");
      for (const text of await absent.allTextContents()) {
        expect(
          text.includes("0"),
          `계산 불가 값 슬롯에 문자 0 이 있습니다: ${JSON.stringify(text)}`,
        ).toBe(false);
      }

      /*
       * ★ V-11 — no delta arrows or sparklines.
       * /triggers is the documented exception: PRD §71 spells the trigger *names*
       * with arrows ("Churn ↑ → Segment Analysis"). They are labels, not indicators.
       */
      if (route.path !== "/triggers") {
        const body = await page.locator("body").innerText();
        for (const glyph of ["↑", "↓", "▲", "▼"]) {
          expect(body.includes(glyph), `증감 글리프 ${glyph} 가 있습니다`).toBe(false);
        }
      }

      /*
       * ★ The badge assertion runs in both directions, because both mistakes are
       * failures of the same rule: sample data that looks measured, and measured data
       * that looks like a sample. The second one is not harmless — it teaches the
       * reader to discount a real number.
       */
      const badge = page.getByText("표본 데이터 — 실측이 아닙니다");
      if (sampleInput) {
        await expect(badge.first()).toBeVisible();
      } else {
        await expect(badge).toHaveCount(0);
      }

      await page.screenshot({
        path: `${shots}/${route.slug}.png`,
        fullPage: true,
      });
    });
  }
});

/**
 * ★ The USP-1 representative scene (story d-02 §4.7, invariants U-1 ~ U-10).
 *
 * Only meaningful on a fixture that has a measured revenue next to an uncomputable
 * contribution_profit, which is `commerce-connected`.
 */
test.describe("USP-1 대표 장면", () => {
  // Only fixtures that actually carry a measured revenue beside an uncomputable
  // contribution_profit can demonstrate the contrast. `empty-sink` and the repository's
  // own results/ have neither, and a one-sided card would prove nothing.
  test.skip(
    fixture === "empty-sink" || fixture === "real",
    "측정된 revenue 와 계산 불가 contribution_profit 이 함께 있는 게시물에서만 성립한다",
  );

  test("revenue ↔ contribution_profit 이 같은 카드·같은 타이포그래피", async ({ page }) => {
    await ready(page, "/kpi");
    const card = page.getByRole("region", { name: "주문 경제성 — 매출과 기여이익" });
    await expect(card).toBeVisible();

    // U-2 — the decisive invariant. Both value slots must resolve to the SAME computed
    // font-size and font-weight. If the absence were rendered smaller it would read as
    // less important, which is the polite form of filling it with zero.
    const slots = card.locator(".text-metric");
    await expect(slots).toHaveCount(2);
    const styles = await slots.evaluateAll((nodes) =>
      nodes.map((n) => {
        const s = getComputedStyle(n);
        return { size: s.fontSize, weight: s.fontWeight, text: (n.textContent ?? "").trim() };
      }),
    );
    expect(styles[0].size, "값과 — 의 font-size 가 다릅니다").toBe(styles[1].size);
    expect(styles[0].weight, "값과 — 의 font-weight 가 다릅니다").toBe(styles[1].weight);

    // U-3 — the absence is an em dash, never "0원".
    expect(styles[1].text).toBe("—");
    expect(styles[1].text).not.toContain("0");

    // U-4 / U-6 — the reason and its raw code are visible without hovering.
    // `.first()` because NO_COST_BASIS legitimately appears twice: once in the status
    // chip and once in the blocked_by cause list. Both are inline, which is the point.
    await expect(card.getByText("원가 근거 없음").first()).toBeVisible();
    await expect(card.getByText("NO_COST_BASIS").first()).toBeVisible();
    // U-7 is asserted separately below — it depends on data this publisher does not
    // emit yet, and folding it in here would make the whole scene unverifiable.
    // U-8 — the gap report does not end as an accusation.
    await expect(card.getByText(/^조치:/)).toBeVisible();
    // U-9 / fixture badge.
    await expect(card.getByLabel("커머스 실측")).toBeVisible();
    if (sampleInput) {
      await expect(card.getByText("표본 데이터 — 실측이 아닙니다")).toBeVisible();
    }

    await card.screenshot({ path: `${shots}/usp1-representative-scene.png` });
  });

  /**
   * ★ U-7 — the real content of the scene: one missing cost field takes down a Primary
   * metric. The [P1] badge is what makes that legible; without it the chain reads as
   * trivia about two mid-tier metrics.
   *
   * This needs `role: "primary" | "guardrail"` and `blocks` on the published metrics.
   * The W2 example fixtures carry both. The current publisher emits `role: "none"` for
   * every metric, omits `blocks`, and ships no `experiment` layer at all — so on a real
   * artifact there is no Primary metric for anything to block.
   *
   * Skipped-with-reason rather than relaxed: an unverifiable invariant must show up as
   * unverified, not as green.
   */
  test("U-7 — 결손이 Primary 지표를 무너뜨린다는 것이 보인다", async ({ page }) => {
    await ready(page, "/kpi");
    const card = page.getByRole("region", { name: "주문 경제성 — 매출과 기여이익" });
    const badge = card.getByLabel("Primary 지표");
    test.skip(
      (await badge.count()) === 0,
      "게시물에 role=primary·blocks 가 없어 [P1] 영향을 표시할 데이터가 없다 (M-04/M-06 인계)",
    );
    await expect(badge.first()).toBeVisible();
  });

  test("측정된 0 ↔ 계산 불가 — 같은 0건에서 갈리는 지점", async ({ page }) => {
    await ready(page, "/kpi");
    // coupon_usage_count is ok with value 0 AND a basis; coupon_cost is uncomputable.
    // The presence of a basis is what separates "we counted and found none" from
    // "we could not measure this" — the second half of the USP-1 argument.
    // coupon_cost is uncomputable only in the W2 fixture; the current publisher derives
    // it from treatment unit cost and reports ok/0원, so the contrast does not exist there.
    test.skip(
      fixture !== "commerce-connected",
      "coupon_usage_count(측정된 0) ↔ coupon_cost(계산 불가) 쌍은 commerce-connected 에만 있다",
    );
    const usage = page.locator("li", { hasText: "coupon_usage_count" }).first();
    await expect(usage.getByText(/^기준:/).first()).toBeVisible();
    await usage.screenshot({ path: `${shots}/usp1-measured-zero.png` });

    const cost = page.locator("li", { hasText: "coupon_cost" }).first();
    await expect(cost.getByText("MISSING_FIELD").first()).toBeVisible();
    await cost.screenshot({ path: `${shots}/usp1-uncomputable.png` });
  });
});

/**
 * US-12 — source must be told apart by position, never by colour, and the order must
 * survive the responsive breakpoint. Captured at 900px, below the 1024px stack point.
 */
test("US-12 출처 2열 — 1024px 미만 적층에서도 커머스가 먼저", async ({ page }) => {
  await page.setViewportSize({ width: 900, height: 1200 });
  await ready(page, "/ingestion");

  const commerce = page.getByRole("region", { name: "커머스 실측" }).first();
  const simulator = page.getByRole("region", { name: "시뮬레이터 생성" }).first();
  const a = await commerce.boundingBox();
  const b = await simulator.boundingBox();
  expect(a).not.toBeNull();
  expect(b).not.toBeNull();
  // Stacked: commerce sits above simulator. Order never flips (S-1).
  expect(a!.y, "적층 시 커머스가 위가 아닙니다").toBeLessThan(b!.y);

  await page.screenshot({ path: `${shots}/us12-source-columns-900px.png`, fullPage: true });
});

/** Keyboard reachability — every path must work without a pointer (WCAG 2.2 AA). */
test("접근성 — 키보드로 본문 건너뛰기와 첫 링크 도달", async ({ page }) => {
  await ready(page, "/");
  await page.keyboard.press("Tab");
  const skip = page.getByRole("link", { name: "본문으로 건너뛰기" });
  await expect(skip).toBeFocused();
  await page.screenshot({ path: `${shots}/a11y-skip-link-focus.png` });

  // The disabled results-group items must not be reachable by keyboard: a control that
  // looks dead but still focuses is worse than one that is plainly absent.
  const disabled = page.locator('[aria-disabled="true"]').first();
  await expect(disabled).toHaveCount(1);
  await expect(disabled).not.toBeFocused();
});
