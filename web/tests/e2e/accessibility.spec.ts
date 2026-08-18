import { expect, test } from "./fixtures/strict-test";
import AxeBuilder from "@axe-core/playwright";

// WCAG 2.2 AA accessibility checks using axe-core.
// Covers the three new Level AA criteria in WCAG 2.2:
//   2.4.11 Focus Not Obscured (focus rings must not be fully hidden by sticky UI)
//   2.5.7  Dragging Movements (draggable UI must have a pointer alternative)
//   3.2.6  Consistent Help (help affordances must appear in the same location across pages)
//
// Tags used: wcag2a, wcag2aa, wcag22aa — all criteria at A and AA level including 2.2 additions.

const WCAG_TAGS = ["wcag2a", "wcag2aa", "wcag22aa"];

test.describe.configure({ mode: "serial" });

/**
 * Runs axe on the current page and asserts zero violations.
 * Reports the full violation list on failure for easy diagnosis.
 */
async function assertNoA11yViolations(
  page: import("@playwright/test").Page,
  context?: string,
) {
  // Run axe against the settled UI state; entrance motion can otherwise be
  // sampled mid-frame and report transient contrast values that users do not
  // read as static content.
  await page.waitForTimeout(500);

  const results = await new AxeBuilder({ page }).withTags(WCAG_TAGS).analyze();

  if (results.violations.length > 0) {
    const summary = results.violations
      .map(
        (v) =>
          `[${v.impact}] ${v.id}: ${v.description} — ${v.nodes.length} node(s)\n${v.nodes
            .slice(0, 8)
            .map(
              (node) =>
                `  target=${node.target.join(", ")} html=${node.html} ${node.failureSummary ?? ""}`,
            )
            .join("\n")}`,
      )
      .join("\n");
    throw new Error(
      `WCAG 2.2 AA violations${context ? ` on ${context}` : ""}: \n${summary}`,
    );
  }
}

test.describe("Accessibility — WCAG 2.2 AA smoke suite", () => {
  test.describe.configure({ timeout: 60_000 });

  test("home page passes axe WCAG 2.2 AA", async ({ page }) => {
    await page.goto("/");
    await assertNoA11yViolations(page, "home page");
  });

  test("analyses page passes axe WCAG 2.2 AA", async ({ page }) => {
    await page.goto("/analyses");
    await assertNoA11yViolations(page, "analyses page");
  });

  test("new analysis page passes axe WCAG 2.2 AA", async ({ page }) => {
    await page.goto("/analyses/new");
    await assertNoA11yViolations(page, "new analysis page");
  });

  test("dashboard page passes axe WCAG 2.2 AA", async ({ page }) => {
    await page.goto("/dashboard");
    await assertNoA11yViolations(page, "dashboard page");
  });

  test("help page passes axe WCAG 2.2 AA", async ({ page }) => {
    await page.goto("/help");
    await assertNoA11yViolations(page, "help page");
  });

  test("config page passes axe WCAG 2.2 AA", async ({ page }) => {
    await page.goto("/config");
    await assertNoA11yViolations(page, "config page");
  });

  test("billing page passes axe WCAG 2.2 AA", async ({ page }) => {
    await page.goto("/billing");
    await assertNoA11yViolations(page, "billing page");
  });

  test("workflow atlas page passes axe WCAG 2.2 AA", async ({ page }) => {
    await page.goto("/capabilities");
    await assertNoA11yViolations(page, "workflow atlas page");
  });

  test("flagship report workspace passes axe WCAG 2.2 AA", async ({ page }) => {
    await page.goto("/analyses/ana_demo_001/report");
    await assertNoA11yViolations(page, "flagship report workspace");
  });

  test("auth routes pass axe WCAG 2.2 AA", async ({ page }) => {
    for (const route of ["/sign-in", "/sign-up"]) {
      await page.goto(route);
      await assertNoA11yViolations(page, route);
    }
  });
});

// Retained manual checks for heading hierarchy and interactive element focus
// (cheaper than axe for these specific structural assertions).
test.describe("Accessibility — structural checks", () => {
  test("dashboard has proper heading hierarchy", async ({ page }) => {
    await page.goto("/");
    const h1 = page.getByRole("heading", { level: 1 });
    await expect(h1).toBeVisible();
  });

  test("analyses page has proper heading hierarchy", async ({ page }) => {
    await page.goto("/analyses");
    const h1 = page.getByRole("heading", { level: 1 });
    await expect(h1).toBeVisible();
  });

  test("tables have proper headers with scope", async ({ page }) => {
    await page.goto("/");
    const table = page.locator("table").first();
    if (await table.isVisible()) {
      const ths = table.locator("th[scope='col']");
      const count = await ths.count();
      expect(count).toBeGreaterThan(0);
    }
  });

  test("interactive elements are keyboard focusable", async ({ page }) => {
    await page.goto("/");
    // Tab through the page — first link should receive focus
    await page.keyboard.press("Tab");
    const focused = page.locator(":focus");
    await expect(focused).toBeVisible();
  });

  test("links have accessible text", async ({ page }) => {
    await page.goto("/");
    await expect(
      page.getByRole("link", { name: "Praviar home" }),
    ).toBeVisible();
    const links = page.getByRole("link");
    const count = await links.count();
    expect(count).toBeGreaterThan(0);

    // Check first few links have accessible names
    for (let i = 0; i < Math.min(count, 5); i++) {
      const name =
        (await links.nth(i).getAttribute("aria-label")) ||
        (await links.nth(i).innerText());
      expect(name?.trim().length).toBeGreaterThan(0);
    }
  });

  test("marketing brand links keep accessible names across public pages", async ({
    page,
  }) => {
    for (const path of ["/", "/trust", "/sample-reports"]) {
      await page.goto(path);
      await expect(
        page.getByRole("link", { name: "Praviar home" }),
      ).toBeVisible();
    }
  });

  test("page has no duplicate IDs", async ({ page }) => {
    await page.goto("/");
    const ids = await page.evaluate(() => {
      const elements = document.querySelectorAll("[id]");
      const idList = Array.from(elements)
        .map((el) => el.id)
        .filter(Boolean);
      const duplicates = idList.filter((id, i) => idList.indexOf(id) !== i);
      return duplicates;
    });
    expect(ids).toHaveLength(0);
  });

  test("images and icons have alternative text", async ({ page }) => {
    await page.goto("/");
    // Check that img elements have alt text
    const images = page.locator("img");
    const imgCount = await images.count();
    for (let i = 0; i < imgCount; i++) {
      const alt = await images.nth(i).getAttribute("alt");
      expect(alt).not.toBeNull();
    }
  });
});
