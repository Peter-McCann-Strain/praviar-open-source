import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";

const WEB_ROOT = resolve(__dirname, "../..");

function readWebFile(path: string) {
  return readFileSync(resolve(WEB_ROOT, path), "utf8");
}

function readCssBlock(css: string, selector: string) {
  const escapedSelector = selector.replace(/[.*+?^${}()|[\]\\]/gu, "\\$&");
  return css.match(
    new RegExp(`${escapedSelector}\\s*\\{[\\s\\S]*?\\}`, "u"),
  )?.[0];
}

describe("public surface visual governance", () => {
  it("keeps the shared-report page background tokenized", () => {
    const sharePage = readWebFile("src/app/share/[token]/page.tsx");
    const shareShell = readWebFile(
      "src/app/share/[token]/share-page-shell.tsx",
    );
    const shareAccessPanel = readWebFile(
      "src/app/share/[token]/share-access-panel.tsx",
    );
    const globals = readWebFile("src/app/globals.css");
    const shareAccessFieldBlock = readCssBlock(
      globals,
      ".praviar-share-access-field",
    );
    const shareAccessPanelBlock = readCssBlock(
      globals,
      ".praviar-share-access-panel",
    );
    const shareGridBlock = readCssBlock(
      globals,
      ".praviar-share-evidence-grid",
    );

    expect(sharePage).toContain("SharePageShell");
    expect(shareShell).toContain("praviar-share-access-field");
    expect(shareShell).toContain("praviar-share-evidence-grid");
    expect(shareShell).toContain("praviar-glass-panel overflow-hidden");
    expect(shareShell).toContain("type-heading-xl text-[var(--text-primary)]");
    expect(shareShell).not.toContain("tracking-tight");
    expect(shareShell).toContain("[overflow-wrap:anywhere]");
    expect(shareShell).not.toContain("[font-family:var(--font-newsreader)]");
    expect(shareShell).not.toContain("praviar-marketing-shell");
    expect(shareShell).not.toContain("praviar-report-evidence-paper.svg");
    expect(shareShell).not.toContain(
      'className="light praviar-evidence-paper overflow-hidden',
    );
    expect(shareAccessPanel).toContain(
      "praviar-share-access-panel overflow-hidden",
    );
    expect(shareAccessPanel).toContain(
      "type-heading-xl text-[var(--text-primary)]",
    );
    expect(shareAccessPanel).not.toContain("tracking-tight");
    expect(shareAccessPanel).not.toContain("praviar-evidence-paper");
    expect(shareShell).toContain("sm:grid-cols-2");
    expect(shareShell).not.toContain("sm:grid-cols-3");
    expect(shareShell).not.toContain("rgba(14,111,104");
    expect(shareAccessFieldBlock).toBeTypeOf("string");
    expect(shareAccessFieldBlock).toContain("praviar-dossier-thread.svg");
    expect(shareAccessFieldBlock).toContain("praviar-app-evidence-field.svg");
    expect(shareAccessFieldBlock).not.toContain(
      "praviar-report-evidence-paper.svg",
    );
    expect(shareAccessPanelBlock).toBeTypeOf("string");
    expect(shareAccessPanelBlock).toContain("praviar-dossier-thread.svg");
    expect(shareAccessPanelBlock).toContain("praviar-app-evidence-field.svg");
    expect(shareAccessPanelBlock).not.toContain(
      "praviar-report-evidence-paper.svg",
    );
    expect(shareGridBlock).toBeTypeOf("string");
    expect(shareGridBlock).toContain("rgba(var(--brand-primary-rgb), 0.06)");
    expect(shareGridBlock).toContain("rgba(var(--brand-primary-rgb), 0.05)");
    expect(shareGridBlock).not.toContain("/brand/visuals/");
    expect(shareGridBlock).not.toContain("praviar-report-evidence-paper.svg");
    expect(shareGridBlock).not.toContain("praviar-dossier-thread.svg");
  });

  it("keeps shared packets preservable as premium print artifacts", () => {
    const globals = readWebFile("src/app/globals.css");
    const sharedReport = readWebFile(
      "src/app/share/[token]/shared-report-card.tsx",
    );

    expect(sharedReport).toContain("data-praviar-share-report");
    expect(sharedReport).toContain("data-praviar-share-packet-receipt");
    expect(sharedReport).toContain("data-praviar-share-reliance-status");
    expect(sharedReport).toContain("data-praviar-share-review-workflow");
    expect(sharedReport).toContain("data-praviar-share-trust-bar");

    expect(globals).toContain("[data-praviar-share-report]");
    expect(globals).toContain("print-color-adjust: exact");
    expect(globals).toContain("@media print");
    expect(globals).toContain(".praviar-share-access-field");
    expect(globals).toContain("background: var(--bg-base) !important");
    expect(globals).toContain(".praviar-share-evidence-grid");
    expect(globals).toContain("display: none !important");
    expect(globals).toContain("break-inside: avoid");
    expect(globals).toContain("page-break-inside: avoid");
    expect(globals).toContain("[data-praviar-share-trust-bar]");
    expect(globals).toContain("position: static !important");
  });

  it("keeps overlay spotlight colors on brand tokens", () => {
    const spotlight = readWebFile(
      "src/components/shared/onboarding-tooltip-spotlight.tsx",
    );

    expect(spotlight).toContain("data-praviar-onboarding-spotlight");
    expect(spotlight).toContain("color-mix(in srgb, var(--brand-ink)");
    expect(spotlight).toContain("rgba(var(--brand-primary-rgb), 0.3)");
    expect(spotlight).not.toContain("rgba(11,31,36");
  });
});
