import { mkdir, writeFile } from "node:fs/promises";
import { resolve } from "node:path";

import AxeBuilder from "@axe-core/playwright";
import { chromium } from "@playwright/test";

const out = resolve("test-results/semantic-operational-adversary-20260718");
const width = Number(process.argv[2] ?? 1440);
const viewport =
  width === 390 ? { width: 390, height: 844 } : { width: 1440, height: 1000 };
await mkdir(out, { recursive: true });

const browser = await chromium.launch({ channel: "chrome", headless: true });
const context = await browser.newContext({
  colorScheme: "light",
  reducedMotion: "reduce",
  viewport,
});
await context.addInitScript(() => {
  localStorage.setItem("praviar_welcomed:v2:user=dev-user:org=dev-org", "true");
  localStorage.setItem(
    "praviar_tour_complete:v2:user=dev-user:org=dev-org",
    "true",
  );
});
const page = await context.newPage();
page.setDefaultTimeout(20_000);

const consoleErrors = [];
const pageErrors = [];
const badResponses = [];
page.on("console", (message) => {
  if (message.type() === "error") consoleErrors.push(message.text());
});
page.on("pageerror", (error) => pageErrors.push(error.message));
page.on("response", (response) => {
  if (response.status() >= 400) {
    badResponses.push({ status: response.status(), url: response.url() });
  }
});

async function inspect(path, heading, file, assertions) {
  await page.goto(`http://127.0.0.1:3100${path}`, {
    waitUntil: "domcontentloaded",
  });
  await page.getByRole("heading", { level: 1, name: heading }).waitFor();
  await page.waitForTimeout(500);
  const body = await page.locator("main").innerText();
  const axe = await new AxeBuilder({ page })
    .withTags(["wcag2a", "wcag2aa", "wcag22aa"])
    .analyze();
  await page.screenshot({
    fullPage: true,
    path: resolve(out, `${width}-${file}`),
  });
  return {
    assertions: Object.fromEntries(
      Object.entries(assertions).map(([label, text]) => [
        label,
        body.includes(text),
      ]),
    ),
    axe: axe.violations.map(({ id, impact }) => ({ id, impact })),
    bodyExcerpt: body.slice(0, 4_000),
    path,
    url: page.url(),
  };
}

const results = [];
results.push(
  await inspect(
    "/analyses",
    "Analysis Library",
    "analyses-fixture-labelled.png",
    {
      fixtureSignal: "Development fixture",
      seededPreview: "Seeded preview",
      staticStep: "Static · Step 4/8",
    },
  ),
);
results.push(
  await inspect(
    "/analyses/3f6bdb0a-a5ce-4d1d-a64a-2cd6bd160e12",
    "ibuprofen",
    "ibuprofen-static-preview.png",
    {
      noDispatch: "no task was dispatched",
      notWorkerHealth: "Not a worker health signal",
      staticPreview: "Static in-progress preview",
    },
  ),
);
results.push(
  await inspect(
    "/analyses/416b8625-882a-4d79-b845-d2a8b9e81acc",
    "sofosbuvir",
    "sofosbuvir-invalidity-coverage.png",
    {
      coverageBoundary: "Pipeline completion records that the stage returned",
      noOutput: "No output",
      unknownValidity: "validity remains unknown",
      workflowClosed: "Invalidity workflow closed without assessment output",
    },
  ),
);

if (width === 1440) {
  await page.goto("http://127.0.0.1:3100/analyses", {
    waitUntil: "domcontentloaded",
  });
  await page.getByRole("link", { name: "View run for Ibuprofen" }).click();
  await page.getByRole("heading", { level: 1, name: "Ibuprofen" }).waitFor();
  const fixtureBody = await page.locator("main").innerText();

  await page.goto("http://127.0.0.1:3100/analyses", {
    waitUntil: "domcontentloaded",
  });
  await page
    .locator('a[href="/analyses/416b8625-882a-4d79-b845-d2a8b9e81acc"]')
    .click();
  await page.getByRole("heading", { level: 1, name: "sofosbuvir" }).waitFor();
  const reportBody = await page.locator("main").innerText();
  await page.screenshot({
    fullPage: true,
    path: resolve(out, "1440-clickthrough-invalidity-coverage.png"),
  });
  results.push({
    assertions: {
      clickedFixtureWasStatic: fixtureBody.includes(
        "Not a worker health signal",
      ),
      clickedReportShowsCoverage: reportBody.includes(
        "Invalidity workflow closed without assessment output",
      ),
    },
    axe: [],
    path: "desktop-clickthrough",
    url: page.url(),
  });
}

await writeFile(
  resolve(out, `audit-${width}.json`),
  JSON.stringify({ badResponses, consoleErrors, pageErrors, results }, null, 2),
);
process.stdout.write(
  JSON.stringify({ badResponses, consoleErrors, pageErrors, results }, null, 2),
);
await browser.close();
