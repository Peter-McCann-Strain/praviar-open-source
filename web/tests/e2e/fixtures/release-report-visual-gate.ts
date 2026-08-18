import AxeBuilder from "@axe-core/playwright";
import {
  expect,
  type Locator,
  type Page,
  type TestInfo,
} from "@playwright/test";

import { waitForDeterministicSurface } from "./surface-readiness";

const WCAG_TAGS = ["wcag2a", "wcag2aa", "wcag22aa"];
const PRIVATE_CONTROL_SELECTOR = [
  "input",
  "textarea",
  "[contenteditable='true']",
  ".cl-userButtonTrigger",
  "[aria-label*='account' i]",
  "[aria-label*='profile' i]",
].join(",");

export const RELEASE_REPORT_VIEWPORTS = [
  { name: "desktop", width: 1440, height: 1000 },
  { name: "mobile", width: 390, height: 844 },
] as const;

type ReleaseReportViewportReceipt = {
  axe_violation_count: number;
  horizontal_overflow_px: number;
  primary_control_height_px: number;
  primary_control_width_px: number;
  surface: "evidence" | "overview";
  viewport: (typeof RELEASE_REPORT_VIEWPORTS)[number];
};

async function expectPrimaryControlTarget(
  control: Locator,
  label: string,
): Promise<{ height: number; width: number }> {
  await expect(control, `${label} primary report control`).toBeVisible();
  const box = await control.boundingBox();
  expect(box, `${label} primary report control bounds`).not.toBeNull();
  if (!box) {
    throw new Error(`${label} primary report control has no layout bounds.`);
  }
  expect(
    box.width,
    `${label} primary report control width`,
  ).toBeGreaterThanOrEqual(44);
  expect(
    box.height,
    `${label} primary report control height`,
  ).toBeGreaterThanOrEqual(44);
  return { height: box.height, width: box.width };
}

async function inspectReleaseReportViewport(
  page: Page,
  label: string,
  viewportName: (typeof RELEASE_REPORT_VIEWPORTS)[number]["name"],
): Promise<Omit<ReleaseReportViewportReceipt, "surface" | "viewport">> {
  await waitForDeterministicSurface(page, label);
  await expect(page.getByRole("main"), `${label} main landmark`).toBeVisible();
  await expect(
    page.locator('[data-praviar-app-state="loading"]'),
    `${label} unresolved loading state`,
  ).toHaveCount(0);
  await expect(
    page.locator('[data-praviar-app-state="error"]'),
    `${label} application error state`,
  ).toHaveCount(0);

  const primaryControl =
    viewportName === "mobile"
      ? page.getByRole("button", { name: "More report actions" })
      : page
          .getByRole("button", {
            name: /Verify export readiness|Review export blockers|Export evidence packet|Prepare evidence packet export with source caveat/i,
          })
          .first();
  const primaryControlBounds = await expectPrimaryControlTarget(
    primaryControl,
    label,
  );
  const horizontalOverflowPx = await page.evaluate(() => {
    const root = document.documentElement;
    return (
      Math.max(root.scrollWidth, document.body.scrollWidth) - root.clientWidth
    );
  });
  expect(
    horizontalOverflowPx,
    `${label} horizontal overflow`,
  ).toBeLessThanOrEqual(1);

  const axeResults = await new AxeBuilder({ page })
    .withTags(WCAG_TAGS)
    .analyze();
  const violations = axeResults.violations.map((violation) => ({
    help: violation.help,
    id: violation.id,
    impact: violation.impact,
    targets: violation.nodes.map((node) => node.target),
  }));
  expect(violations, `${label} WCAG 2.2 AA violations`).toEqual([]);

  return {
    axe_violation_count: violations.length,
    horizontal_overflow_px: horizontalOverflowPx,
    primary_control_height_px: primaryControlBounds.height,
    primary_control_width_px: primaryControlBounds.width,
  };
}

async function openEvidenceWorkbench(
  page: Page,
  viewportName: (typeof RELEASE_REPORT_VIEWPORTS)[number]["name"],
): Promise<void> {
  if (viewportName === "mobile") {
    await page
      .getByRole("combobox", { name: "Report section" })
      .selectOption("evidence");
  } else {
    await page.getByRole("tab", { name: /^Evidence(?:,|$)/i }).click();
    await expect(
      page.getByRole("tab", { name: /^Evidence(?:,|$)/i }),
      "Evidence report tab selected",
    ).toHaveAttribute("aria-selected", "true");
  }

  const workbench = page.getByRole("region", { name: "Evidence workbench" });
  await expect(workbench, "live Evidence workbench").toBeVisible();
  await expect(
    workbench.getByRole("heading", {
      name: "Source ledger and citation verification",
    }),
    "Evidence workbench identity",
  ).toBeVisible();

  if (viewportName === "mobile") {
    await workbench
      .getByText("Inspect source ledger, citations, and gaps", { exact: true })
      .click();
    await workbench
      .getByText(/Inspect \d+ customer-visible assertions/i)
      .click();
  }

  await expect(
    workbench.getByRole("region", { name: "Counsel evidence ledger" }),
    "live counsel evidence ledger",
  ).toBeVisible();
}

async function restoreOverview(
  page: Page,
  viewportName: (typeof RELEASE_REPORT_VIEWPORTS)[number]["name"],
): Promise<void> {
  if (viewportName === "mobile") {
    await page
      .getByRole("combobox", { name: "Report section" })
      .selectOption("overview");
    return;
  }

  await page.getByRole("tab", { name: /^Outcome(?:,|$)/i }).click();
  await expect(
    page.getByRole("tab", { name: /^Outcome(?:,|$)/i }),
    "Outcome report tab selected",
  ).toHaveAttribute("aria-selected", "true");
}

async function attachMaskedScreenshot({
  attachmentName,
  page,
  privateControls,
  testInfo,
}: {
  attachmentName: string;
  page: Page;
  privateControls: Locator;
  testInfo: TestInfo;
}): Promise<void> {
  await testInfo.attach(attachmentName, {
    body: await page.screenshot({
      animations: "disabled",
      caret: "hide",
      fullPage: true,
      mask: [privateControls],
      maskColor: "#111827",
    }),
    contentType: "image/png",
  });
}

/**
 * Proves the authenticated, newly generated report itself is responsive and
 * accessible. These receipts complement the mocked visual matrix; they do not
 * substitute for a real staging or production journey.
 */
export async function attachReleaseReportVisualReceipts({
  attachmentNames,
  attachmentPrefix,
  page,
  testInfo,
}: {
  attachmentNames?: Partial<
    Record<(typeof RELEASE_REPORT_VIEWPORTS)[number]["name"], string>
  >;
  attachmentPrefix: string;
  page: Page;
  testInfo: TestInfo;
}): Promise<void> {
  const originalViewport = page.viewportSize();
  const receipts: ReleaseReportViewportReceipt[] = [];
  const privateControls = page.locator(PRIVATE_CONTROL_SELECTOR);

  try {
    for (const viewport of RELEASE_REPORT_VIEWPORTS) {
      await page.setViewportSize({
        width: viewport.width,
        height: viewport.height,
      });
      await page.emulateMedia({ reducedMotion: "reduce" });
      const overviewLabel = `${attachmentPrefix} overview ${viewport.name}`;
      const overviewReceipt = await inspectReleaseReportViewport(
        page,
        overviewLabel,
        viewport.name,
      );
      receipts.push({
        ...overviewReceipt,
        surface: "overview",
        viewport,
      });

      await attachMaskedScreenshot({
        attachmentName:
          attachmentNames?.[viewport.name] ??
          (viewport.name === "desktop"
            ? attachmentPrefix
            : `${attachmentPrefix}-${viewport.name}`),
        page,
        privateControls,
        testInfo,
      });

      await openEvidenceWorkbench(page, viewport.name);
      const evidenceLabel = `${attachmentPrefix} Evidence workbench ${viewport.name}`;
      const evidenceReceipt = await inspectReleaseReportViewport(
        page,
        evidenceLabel,
        viewport.name,
      );
      receipts.push({
        ...evidenceReceipt,
        surface: "evidence",
        viewport,
      });
      await attachMaskedScreenshot({
        attachmentName: `${attachmentPrefix}-evidence-${viewport.name}`,
        page,
        privateControls,
        testInfo,
      });
      await restoreOverview(page, viewport.name);
    }
  } finally {
    await page.emulateMedia({ reducedMotion: "no-preference" });
    if (originalViewport) {
      await page.setViewportSize(originalViewport);
    }
  }

  await testInfo.attach(`${attachmentPrefix}-visual-quality`, {
    body: JSON.stringify(
      {
        receipts,
        schema_version: 1,
        wcag_tags: WCAG_TAGS,
      },
      null,
      2,
    ),
    contentType: "application/json",
  });
}
