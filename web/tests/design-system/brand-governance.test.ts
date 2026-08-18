import { createHash } from "node:crypto";
import { existsSync, readdirSync, readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";

const WEB_ROOT = resolve(__dirname, "..", "..");
const REPO_ROOT = resolve(WEB_ROOT, "..");

function readWebFile(pathFromWebRoot: string) {
  return readFileSync(resolve(WEB_ROOT, pathFromWebRoot), "utf-8");
}

function readWebBinary(pathFromWebRoot: string) {
  return readFileSync(resolve(WEB_ROOT, pathFromWebRoot));
}

function sha256(buffer: Buffer) {
  return createHash("sha256").update(buffer).digest("hex");
}

function readRepoFile(pathFromRepoRoot: string) {
  return readFileSync(resolve(REPO_ROOT, pathFromRepoRoot), "utf-8");
}

type PaletteManifest = {
  core: Record<string, string>;
  support: Record<string, string>;
};

function readPaletteManifest() {
  return JSON.parse(
    readRepoFile("brand/praviar-palette.json"),
  ) as PaletteManifest;
}

function paletteHexSet() {
  const palette = readPaletteManifest();
  return new Set(
    [...Object.values(palette.core), ...Object.values(palette.support)].map(
      (hex) => hex.toUpperCase(),
    ),
  );
}

function corePaletteHexSet() {
  const palette = readPaletteManifest();
  return new Set(Object.values(palette.core).map((hex) => hex.toUpperCase()));
}

function extractHexColors(source: string) {
  return [...source.matchAll(/#[0-9a-f]{6}\b/giu)].map((match) =>
    match[0].toUpperCase(),
  );
}

function readPngDimensions(png: Buffer) {
  expect(png.subarray(0, 8).toString("hex")).toBe("89504e470d0a1a0a");

  return {
    height: png.readUInt32BE(20),
    width: png.readUInt32BE(16),
  };
}

function walkWebDir(pathFromWebRoot: string): string[] {
  const root = resolve(WEB_ROOT, pathFromWebRoot);
  const files: string[] = [];

  function visit(dir: string) {
    for (const entry of readdirSync(dir, { withFileTypes: true })) {
      const absolutePath = resolve(dir, entry.name);
      if (entry.isDirectory()) {
        visit(absolutePath);
      } else if (entry.isFile()) {
        files.push(absolutePath.replace(`${WEB_ROOT}/`, ""));
      }
    }
  }

  visit(root);
  return files.sort();
}

function hexToRgb(hex: string): [number, number, number] {
  const normalized = hex.replace("#", "");
  return [
    Number.parseInt(normalized.slice(0, 2), 16),
    Number.parseInt(normalized.slice(2, 4), 16),
    Number.parseInt(normalized.slice(4, 6), 16),
  ];
}

function relativeLuminance([red, green, blue]: [number, number, number]) {
  const [r, g, b] = [red, green, blue].map((channel) => {
    const value = channel / 255;
    return value <= 0.03928 ? value / 12.92 : ((value + 0.055) / 1.055) ** 2.4;
  });

  return 0.2126 * r + 0.7152 * g + 0.0722 * b;
}

function contrastRatio(foreground: string, background: string) {
  const foregroundLuminance = relativeLuminance(hexToRgb(foreground));
  const backgroundLuminance = relativeLuminance(hexToRgb(background));
  const lighter = Math.max(foregroundLuminance, backgroundLuminance);
  const darker = Math.min(foregroundLuminance, backgroundLuminance);

  return (lighter + 0.05) / (darker + 0.05);
}

function readToken(block: string, token: string) {
  const escapedToken = token.replace(/[.*+?^${}()|[\]\\]/gu, "\\$&");
  const match = block.match(
    new RegExp(`${escapedToken}:\\s*(#[0-9a-f]{6})`, "iu"),
  );
  return match?.[1];
}

function readCanonicalPraviarMarkPaths() {
  const markData = JSON.parse(
    readWebFile("src/components/icons/praviar-mark-data.json"),
  ) as {
    paths: {
      bands: string[];
      ink: string;
      tile: string;
    };
  };

  expect(markData.paths.tile, "Missing canonical mark tile path").toBeTypeOf(
    "string",
  );
  expect(markData.paths.ink, "Missing canonical mark ink path").toBeTypeOf(
    "string",
  );
  expect(markData.paths.bands).toHaveLength(4);

  return [markData.paths.tile, markData.paths.ink, ...markData.paths.bands];
}

function expectManifestIconEntry(
  manifest: string,
  {
    purpose,
    sizes,
    src,
  }: {
    purpose: "any" | "maskable";
    sizes: string;
    src: string;
  },
) {
  const escapedSrc = src.replace(/[.*+?^${}()|[\]\\]/gu, "\\$&");
  const escapedSizes = sizes.replace(/[.*+?^${}()|[\]\\]/gu, "\\$&");
  const iconObjectPattern = new RegExp(
    `\\{[\\s\\S]*?src:\\s*"${escapedSrc}"[\\s\\S]*?sizes:\\s*"${escapedSizes}"[\\s\\S]*?type:\\s*"image/png"[\\s\\S]*?purpose:\\s*"${purpose}"[\\s\\S]*?\\}`,
    "u",
  );

  expect(
    manifest,
    `manifest.ts must pair ${src} with ${sizes} image/png ${purpose}`,
  ).toMatch(iconObjectPattern);
}

describe("Design system: Praviar brand governance", () => {
  it("keeps the repo palette manifest aligned with the selected premium system", () => {
    const palette = readPaletteManifest();

    expect(palette.core).toEqual({
      ink: "#0B1F24",
      forensicTeal: "#0E6F68",
      clinicalMint: "#5FB7A6",
      clinicalCopper: "#B87333",
      paper: "#F6F4EF",
      softMint: "#D7ECE5",
    });
    expect(palette.support.chartMint).toBe("#8ED7C9");
    expect(palette.support.copperDepth).toBe("#8A4F1F");
    expect(palette.support.clinicalRed).toBe("#C2413A");
  });

  it("keeps Praviar mark CSS variables aligned with the canonical evidence mark", () => {
    const globals = readWebFile("src/app/globals.css");
    const markData = JSON.parse(
      readWebFile("src/components/icons/praviar-mark-data.json"),
    ) as {
      palette: {
        copper: string;
        ink: string;
        mint: string;
        paper: string;
        softMint: string;
        teal: string;
      };
    };
    const markTokenBlocks = [
      ...globals.matchAll(/(?:^|\n)\s*(?::root|\.light)\s*\{[\s\S]*?\n\s*\}/gu),
    ]
      .map((match) => match[0])
      .filter((block) => block.includes("--praviar-mark-paper"));

    expect(markTokenBlocks.length).toBeGreaterThanOrEqual(2);

    for (const block of markTokenBlocks) {
      expect(readToken(block, "--praviar-mark-paper")?.toUpperCase()).toBe(
        markData.palette.paper.toUpperCase(),
      );
      expect(readToken(block, "--praviar-mark-ink")?.toUpperCase()).toBe(
        markData.palette.ink.toUpperCase(),
      );
      expect(readToken(block, "--praviar-mark-band-1")?.toUpperCase()).toBe(
        markData.palette.teal.toUpperCase(),
      );
      expect(readToken(block, "--praviar-mark-band-2")?.toUpperCase()).toBe(
        markData.palette.mint.toUpperCase(),
      );
      expect(readToken(block, "--praviar-mark-band-3")?.toUpperCase()).toBe(
        markData.palette.copper.toUpperCase(),
      );
      expect(readToken(block, "--praviar-mark-copper")?.toUpperCase()).toBe(
        markData.palette.copper.toUpperCase(),
      );
      expect(readToken(block, "--praviar-mark-soft-mint")?.toUpperCase()).toBe(
        markData.palette.softMint.toUpperCase(),
      );
    }
  });

  it("keeps the active brand token layer inside the selected premium palette", () => {
    const globals = readWebFile("src/app/globals.css").toLowerCase();
    const forbiddenLegacyTints = ["#d49a5a", "#e7f5f0", "#eaf3ee", "#cfe7de"];

    for (const tint of forbiddenLegacyTints) {
      expect(
        globals,
        `globals.css still contains legacy tint ${tint}`,
      ).not.toContain(tint);
    }
  });

  it("exposes premium support roles as named web tokens", () => {
    const palette = readPaletteManifest();
    const globals = readWebFile("src/app/globals.css");

    expect(readToken(globals, "--chart-mint")).toBe(
      palette.support.chartMint.toLowerCase(),
    );
    expect(readToken(globals, "--risk-high-wash")).toBe(
      palette.support.riskHighWash.toLowerCase(),
    );
    expect(readToken(globals, "--risk-medium-wash")).toBe(
      palette.support.riskMediumWash.toLowerCase(),
    );
    expect(readToken(globals, "--risk-clear-wash")).toBe(
      palette.support.riskClearWash.toLowerCase(),
    );
  });

  it("keeps public web docs aligned to Forensic Teal + Clinical Copper", () => {
    const docs = [
      ["DESIGN.md", readWebFile("DESIGN.md")],
      ["README.md", readWebFile("README.md")],
    ] as const;
    const retiredPaletteTerms = [
      "teal/purple",
      "Indigo Primary",
      "Indigo Deep",
      "Violet Accent",
      "Void Black",
      "Charcoal Surface",
      "#4F46E5",
      "#818CF8",
      "#A78BFA",
      "#6366F1",
      "flask-vial",
    ];

    for (const [file, text] of docs) {
      expect(text, `${file} must name the selected premium palette.`).toContain(
        "Forensic Teal + Clinical Copper",
      );
      expect(
        text,
        `${file} must document Soft Mint as a first-class brand wash.`,
      ).toContain("Soft Mint");

      for (const term of retiredPaletteTerms) {
        expect(
          text,
          `${file} still references retired palette language: ${term}`,
        ).not.toContain(term);
      }
    }
  });

  it("keeps every public static SVG logo on the canonical Praviar mark geometry", () => {
    const canonicalPaths = readCanonicalPraviarMarkPaths();
    const staticLogoAssets = [
      [
        "web/public/brand/praviar-mark.svg",
        readWebFile("public/brand/praviar-mark.svg"),
      ],
      [
        "web/public/brand/praviar-mark-on-light.svg",
        readWebFile("public/brand/praviar-mark-on-light.svg"),
      ],
      [
        "web/public/brand/praviar-mark-on-dark.svg",
        readWebFile("public/brand/praviar-mark-on-dark.svg"),
      ],
      ["web/src/app/icon.svg", readWebFile("src/app/icon.svg")],
    ] as const;

    for (const [file, svg] of staticLogoAssets) {
      for (const path of canonicalPaths) {
        expect(
          svg,
          `${file} must reuse the canonical Praviar evidence mark path.`,
        ).toContain(path);
      }

      expect(
        svg,
        `${file} must not contain the retired flask-era mark geometry.`,
      ).not.toContain("M115 37L178 73");
      expect(
        svg,
        `${file} must not contain the earlier brighter mint band.`,
      ).not.toContain("#8ED7C9");
    }
  });

  it("keeps globals.css raw hexes documented in the shared palette manifest", () => {
    const allowedHexes = paletteHexSet();
    const globals = readWebFile("src/app/globals.css");
    const unknownHexes = [
      ...new Set(
        (globals.match(/#[0-9A-Fa-f]{6}/gu) ?? []).map((hex) =>
          hex.toUpperCase(),
        ),
      ),
    ].filter((hex) => !allowedHexes.has(hex));

    expect(
      unknownHexes,
      `globals.css contains undocumented palette values. Add the role to brand/praviar-palette.json or derive it from a named token.`,
    ).toEqual([]);
  });

  it("keeps public link previews on the Praviar visual identity", () => {
    const rootLayout = readWebFile("src/app/layout.tsx");
    const homePage = readWebFile("src/app/page.tsx");
    const sampleReport = readWebFile(
      "src/app/(marketing)/sample-reports/[slug]/page.tsx",
    );
    const ogImage = readWebFile("src/app/opengraph-image.tsx");

    for (const source of [rootLayout, homePage, sampleReport]) {
      expect(source).toContain('url: "/opengraph-image"');
      expect(source).toContain('card: "summary_large_image"');
      expect(source).toContain('images: ["/opengraph-image"]');
    }

    for (const brandColor of [
      "#0B1F24",
      "#0E6F68",
      "#5FB7A6",
      "#B87333",
      "#F6F4EF",
      "#D7ECE5",
    ]) {
      expect(ogImage).toContain(brandColor);
    }
    expect(ogImage).toContain("Compound-first patent risk");
    expect(ogImage).toContain("FTO screening intelligence");
    expect(ogImage).toContain("Georgia, 'Times New Roman', serif");
    expect(ogImage).toContain("PRAVIAR_MARK_TILE_PATH");
    expect(ogImage).toContain("PRAVIAR_MARK_INK_PATH");
    expect(ogImage).toContain("PRAVIAR_MARK_BAND_PATHS");
    expect(ogImage).toContain("PRAVIAR_MARK_ON_LIGHT_OUTLINE");
    expect(ogImage).toContain("strokeWidth={4}");
    expect(ogImage).not.toContain("M115 37L178 73");
    expect(ogImage).not.toContain('strokeWidth="24"');
    expect(ogImage).not.toContain("#4F46E5");
    expect(ogImage).not.toContain("#FFFFFF");
    expect(ogImage).not.toContain("#000000");
  });

  it("keeps browser install surfaces on canonical Praviar identity assets", () => {
    const manifest = readWebFile("src/app/manifest.ts");
    const appIcon = readWebFile("src/app/icon.svg");
    const installIcon192 = readWebBinary("public/icons/praviar-icon-192.png");
    const installIcon512 = readWebBinary("public/icons/praviar-icon-512.png");
    const maskableIcon512 = readWebBinary(
      "public/icons/praviar-maskable-512.png",
    );
    const appleIcon = readWebBinary("src/app/apple-icon.png");

    expect(existsSync(resolve(WEB_ROOT, "src/app/apple-icon.png"))).toBe(true);
    expect(
      existsSync(resolve(WEB_ROOT, "public/icons/praviar-icon-192.png")),
    ).toBe(true);
    expect(
      existsSync(resolve(WEB_ROOT, "public/icons/praviar-icon-512.png")),
    ).toBe(true);
    expect(
      existsSync(resolve(WEB_ROOT, "public/icons/praviar-maskable-512.png")),
    ).toBe(true);
    expect(readPngDimensions(installIcon192)).toEqual({
      height: 192,
      width: 192,
    });
    expect(readPngDimensions(installIcon512)).toEqual({
      height: 512,
      width: 512,
    });
    expect(readPngDimensions(maskableIcon512)).toEqual({
      height: 512,
      width: 512,
    });
    expect(readPngDimensions(appleIcon)).toEqual({
      height: 180,
      width: 180,
    });

    expect(manifest).toContain("MetadataRoute.Manifest");
    expect(manifest).toContain("short_name: BRAND.shortName");
    expect(manifest).toContain('start_url: "/"');
    expect(manifest).toContain('display: "standalone"');
    expect(manifest).toContain('theme_color: "#0B1F24"');
    expect(manifest).toContain('background_color: "#F6F4EF"');
    expectManifestIconEntry(manifest, {
      purpose: "any",
      sizes: "192x192",
      src: "/icons/praviar-icon-192.png",
    });
    expectManifestIconEntry(manifest, {
      purpose: "any",
      sizes: "512x512",
      src: "/icons/praviar-icon-512.png",
    });
    expectManifestIconEntry(manifest, {
      purpose: "maskable",
      sizes: "512x512",
      src: "/icons/praviar-maskable-512.png",
    });
    expect(appIcon).toContain("praviar-icon-glow");
    expect(appIcon).toContain('fill="#0B1F24"');
    expect(appIcon).toContain('fill="#F6F4EF"');
  });

  it("keeps the server-rendered app baseline on the premium light palette", () => {
    const layout = readWebFile("src/app/layout.tsx");

    expect(layout).toContain('<html lang="en" className="light"');
    expect(layout).not.toContain("ThemeScript");
    expect(layout).toContain("await headers()");
  });

  it("keeps runtime chrome locked to the premium light palette", () => {
    const uiStore = readWebFile("src/stores/ui-store.ts");
    const sidebarFooter = readWebFile(
      "src/components/layout/sidebar-footer.tsx",
    );
    const globals = readWebFile("src/app/globals.css");

    for (const forbiddenStoreTerm of [
      "setTheme",
      "matchMedia",
      '"dark"',
      '"system"',
    ]) {
      expect(uiStore).not.toContain(forbiddenStoreTerm);
    }

    for (const forbiddenSidebarTerm of [
      "Moon",
      "Sun",
      "onToggleTheme",
      "Switch to light mode",
      "Switch to dark mode",
    ]) {
      expect(sidebarFooter).not.toContain(forbiddenSidebarTerm);
    }

    for (const forbiddenCssThemeTerm of [
      "@custom-variant dark",
      "color-scheme: dark",
      "end @layer base — dark theme",
    ]) {
      expect(globals).not.toContain(forbiddenCssThemeTerm);
    }
  });

  it("keeps display typography deterministic without unloaded custom fonts", () => {
    const globals = readWebFile("src/app/globals.css");
    const layout = readWebFile("src/app/layout.tsx");
    const sourceFiles = walkWebDir("src").filter((file) =>
      /\.(?:ts|tsx)$/u.test(file),
    );
    const sourceText = sourceFiles.map(readWebFile).join("\n");

    expect(globals).toContain(
      '--font-newsreader: Georgia, "Times New Roman", ui-serif, serif;',
    );
    expect(globals).not.toContain("--font-newsreader: Newsreader");
    expect(layout).not.toContain("next/font/google");
    expect(layout).not.toContain("Newsreader");
    expect(sourceText).toContain("[font-family:var(--font-newsreader)]");
    expect(sourceText).not.toContain("font-[var(--font-newsreader)]");
  });

  it("keeps public, auth, and app route shells on branded premium fields", () => {
    const rootLayout = readWebFile("src/app/layout.tsx");
    const marketingLayout = readWebFile("src/app/(marketing)/layout.tsx");
    const marketingShell = readWebFile(
      "src/components/marketing/site-shell.tsx",
    );
    const dashboardLayout = readWebFile("src/app/(dashboard)/layout.tsx");
    const dashboardContent = readWebFile(
      "src/components/layout/dashboard-content.tsx",
    );
    const authSignInPage = readWebFile("src/app/(auth)/sign-in/page.tsx");
    const authSignUpPage = readWebFile("src/app/(auth)/sign-up/page.tsx");
    const authSignInSsoPage = readWebFile(
      "src/app/(auth)/sign-in/sso-callback/page.tsx",
    );
    const authSignUpSsoPage = readWebFile(
      "src/app/(auth)/sign-up/sso-callback/page.tsx",
    );
    const authSignIn = readWebFile(
      "src/app/(auth)/sign-in/sign-in-content.tsx",
    );
    const authSignUp = readWebFile(
      "src/app/(auth)/sign-up/sign-up-content.tsx",
    );
    const authSignInSso = readWebFile(
      "src/app/(auth)/sign-in/sso-callback/sign-in-sso-callback-content.tsx",
    );
    const authSignUpSso = readWebFile(
      "src/app/(auth)/sign-up/sso-callback/sign-up-sso-callback-content.tsx",
    );
    const authSurface = readWebFile("src/components/auth/auth-surface.tsx");
    const clerkRuntimeBoundary = readWebFile(
      "src/components/auth/clerk-runtime-boundary.tsx",
    );

    expect(rootLayout).toContain('<html lang="en" className="light"');
    expect(rootLayout).toContain("bg-[var(--bg-base)]");
    expect(marketingLayout).toContain("MarketingSiteShell");
    expect(marketingShell).toContain("light praviar-marketing-shell");
    expect(marketingShell).toContain("MarketingNav");
    expect(marketingShell).toContain("PraviarLockup");
    expect(marketingShell).toContain("tagline={BRAND.tagline}");
    expect(dashboardLayout).toContain("DashboardContent");
    expect(dashboardLayout).toContain("Topbar");
    expect(dashboardLayout).toContain("Sidebar");
    expect(dashboardContent).toContain("praviar-app-field");
    expect(authSignInPage).toContain("Suspense");
    expect(authSignUpPage).toContain("Suspense");
    expect(authSignInSsoPage).toContain("Suspense");
    expect(authSignUpSsoPage).toContain("Suspense");
    expect(authSignIn).toContain("ClerkRuntimeBoundary");
    expect(authSignUp).toContain("ClerkRuntimeBoundary");
    expect(authSignInSso).toContain("ClerkRuntimeBoundary");
    expect(authSignUpSso).toContain("ClerkRuntimeBoundary");
    expect(clerkRuntimeBoundary).toContain("AuthSurface");
    expect(clerkRuntimeBoundary).toContain("ClerkFailed");
    expect(clerkRuntimeBoundary).toContain("ClerkDegraded");
    expect(authSurface).toContain("praviar-auth-field");
    expect(authSurface).not.toContain("praviar-app-field min-h-screen");
    expect(authSurface).toContain("PraviarLockup");
  });

  it("keeps shared reports sticky-safe and resilient to long evidence tokens", () => {
    const sharedReportPage = readWebFile("src/app/share/[token]/page.tsx");
    const sharedReportShell = readWebFile(
      "src/app/share/[token]/share-page-shell.tsx",
    );
    const sharedReportCard = readWebFile(
      "src/app/share/[token]/shared-report-card.tsx",
    );

    expect(sharedReportPage).toContain("SharePageShell");
    expect(sharedReportShell).toContain("overflow-x-clip");
    expect(sharedReportShell).not.toContain("min-h-screen overflow-hidden");
    expect(sharedReportShell).toContain("PraviarLockup");
    expect(sharedReportShell).toContain(
      "type-heading-xl text-[var(--text-primary)]",
    );
    expect(sharedReportShell).not.toContain("tracking-tight");
    expect(sharedReportShell).not.toContain(
      "[font-family:var(--font-newsreader)]",
    );
    expect(sharedReportCard).toContain("data-praviar-share-trust-bar");
    expect(sharedReportCard).toContain("md:sticky md:top-3");
    expect(sharedReportCard).toContain("shadow-[var(--shadow-md)]");
    expect(sharedReportCard).toContain("[overflow-wrap:anywhere]");
  });

  it("keeps the Praviar mark on flagship brand and report surfaces", () => {
    const requiredMarkSurfaces = [
      "src/app/global-error.tsx",
      "src/app/error.tsx",
      "src/app/not-found.tsx",
      "src/app/(dashboard)/not-found.tsx",
      "src/components/auth/auth-surface.tsx",
      "src/components/marketing/marketing-nav.tsx",
      "src/components/marketing/home-page-demo-panel.tsx",
      "src/components/marketing/trust-page.tsx",
      "src/components/layout/sidebar.tsx",
      "src/components/layout/topbar.tsx",
      "src/app/share/[token]/share-page-shell.tsx",
      "src/components/dashboard/page-header.tsx",
      "src/components/analyses-page/analyses-page-header.tsx",
      "src/components/analysis-detail/analysis-header.tsx",
      "src/components/analysis-detail/analysis-states.tsx",
      "src/components/batch/batch-page-header.tsx",
      "src/components/billing/billing-header.tsx",
      "src/components/compounds/compounds-page-header.tsx",
      "src/components/help/page-header.tsx",
      "src/components/monitors/page-header.tsx",
      "src/components/patents-page/patents-page-header.tsx",
      "src/components/reviews/review-queue-page.tsx",
      "src/components/settings/settings-page-header.tsx",
      "src/components/settings/notifications/notification-settings-page.tsx",
      "src/components/report-page/report-page-header.tsx",
      "src/components/report-page/report-status-state.tsx",
      "src/components/report/print-report-header.tsx",
      "src/components/shared/account-control-status-state.tsx",
      "src/components/shared/app-error-state.tsx",
      "src/components/shared/library-status-state.tsx",
      "src/components/shared/workspace-status-state.tsx",
      "src/app/(dashboard)/admin/page.tsx",
      "src/app/(dashboard)/admin/analytics/page.tsx",
    ];

    for (const file of requiredMarkSurfaces) {
      const text = readWebFile(file);
      expect(
        text,
        `${file} must import the Praviar mark, shared lockup, shared mark frame, shared app header, shared status frame, or shared recovery frame`,
      ).toMatch(
        /Praviar(?:Mark|MarkFrame|Lockup)|AppSurfaceHeader|OperationalStatusFrame|AppErrorState|EmptyState/u,
      );
      expect(
        text,
        `${file} must render the Praviar mark, shared lockup, shared mark frame, shared app header, shared status frame, or shared recovery frame`,
      ).toMatch(
        /<Praviar(?:Mark|MarkFrame|Lockup)\b|<AppSurfaceHeader\b|<OperationalStatusFrame\b|<AppErrorState\b|<EmptyState\b/u,
      );
    }
  });

  it("keeps app chrome lockups on the approved Praviar mark", () => {
    const sidebar = readWebFile("src/components/layout/sidebar.tsx");
    const topbar = readWebFile("src/components/layout/topbar.tsx");
    const lockup = readWebFile("src/components/brand/praviar-lockup.tsx");
    const mark = readWebFile("src/components/icons/praviar-mark.tsx");

    expect(sidebar).toContain("data-praviar-brand-lockup");
    expect(sidebar).toContain("PraviarLockup");
    expect(sidebar).toContain("<PraviarLockup");
    expect(sidebar).not.toContain('variant="mono"');
    expect(sidebar).not.toContain("BenzeneArc");

    expect(topbar).toContain("data-praviar-brand-lockup");
    expect(topbar).toContain("PraviarLockup");
    expect(topbar).toContain("<PraviarLockup");
    expect(topbar).not.toContain('variant="mono"');
    expect(topbar).not.toContain("BenzeneArc");

    expect(lockup).toContain("PraviarMark");
    expect(lockup).toContain("<PraviarMark");
    expect(lockup).toContain('surface === "dark" ? "onDark" : "onLight"');
    expect(lockup).not.toContain('variant="mono"');
    expect(lockup).not.toContain("BenzeneArc");

    expect(mark).not.toContain('"mono"');
    expect(mark).not.toContain('variant === "mono"');
    expect(mark).not.toContain('fill="currentColor"');
  });

  it("keeps raw Praviar mark imports explicit and whitelisted", () => {
    const directMarkImportPattern =
      /import\s+\{[^}]*\bPraviarMark\b[^}]*\}\s+from\s+"@\/components\/icons\/praviar-mark";/u;
    const allowedDirectMarkImports = [
      "src/app/global-error.tsx",
      "src/components/brand/praviar-lockup.tsx",
      "src/components/brand/praviar-mark-frame.tsx",
      "src/components/marketing/home-page-demo-panel.tsx",
      "src/components/marketing/legal-document-page.tsx",
      "src/components/marketing/trust-page.tsx",
      "src/components/report/print-report-header.tsx",
      "src/components/shared/welcome-modal-constants.ts",
    ].sort();
    const actualDirectMarkImports = walkWebDir("src")
      .filter((file) => /\.(?:ts|tsx)$/u.test(file))
      .filter((file) => directMarkImportPattern.test(readWebFile(file)))
      .sort();

    expect(actualDirectMarkImports).toEqual(allowedDirectMarkImports);

    const lockup = readWebFile("src/components/brand/praviar-lockup.tsx");
    const frame = readWebFile("src/components/brand/praviar-mark-frame.tsx");

    expect(lockup).toContain("praviar-lockup-mark-shell");
    expect(lockup).not.toContain("praviar-brand-mark-shell-dark");
    expect(frame).toContain("praviar-brand-mark-shell");
    expect(frame).toContain("praviar-brand-mark-shell-dark");
  });

  it("keeps the retired BenzeneArc visual out of active web source", () => {
    const activeSource = walkWebDir("src")
      .filter((file) => /\.(?:ts|tsx|css|svg)$/u.test(file))
      .filter((file) => file !== "src/components/icons/benzene-arc.tsx");
    const reportTabs = readWebFile("src/components/report-page/tabs.ts");

    expect(
      existsSync(resolve(WEB_ROOT, "src/components/icons/benzene-arc.tsx")),
      "The retired logo-shaped BenzeneArc component should stay removed.",
    ).toBe(false);

    for (const file of activeSource) {
      const source = readWebFile(file);
      expect(
        source,
        `${file} should use lucide domain icons or the canonical PraviarMark, not the retired BenzeneArc visual.`,
      ).not.toMatch(/BenzeneArc|benzene-arc/u);
    }

    expect(reportTabs).toContain("ScrollText");
    expect(reportTabs).not.toContain("FlaskConical");
  });

  it("keeps legacy flask naming out of active brand primitives", () => {
    const brandFiles = walkWebDir("src/components/brand").filter((file) =>
      /\.(?:ts|tsx)$/u.test(file),
    );
    const analysisStatusCards = readWebFile(
      "src/components/analysis-detail/analysis-status-cards.tsx",
    );
    const constants = readWebFile("src/lib/constants.ts");

    expect(
      existsSync(resolve(WEB_ROOT, "src/components/brand/loading-flask.tsx")),
      "The loading primitive should be named after the canonical Praviar mark, not the retired flask-era visual.",
    ).toBe(false);
    expect(analysisStatusCards).toContain("LoadingMark");
    expect(analysisStatusCards).toContain("@/components/brand/loading-mark");
    expect(analysisStatusCards).not.toContain("LoadingFlask");
    expect(analysisStatusCards).not.toContain("loading-flask");
    expect(constants).not.toContain("flask-conical");

    for (const file of brandFiles) {
      const source = readWebFile(file);
      expect(
        source,
        `${file} should not preserve legacy flask naming in brand primitives.`,
      ).not.toMatch(/LoadingFlask|loading-flask/u);
    }

    const loadingMark = readWebFile("src/components/brand/loading-mark.tsx");
    expect(loadingMark).toContain("PraviarMarkFrame");
    expect(loadingMark).toContain("<PraviarMarkFrame");
    expect(loadingMark).not.toMatch(/<PraviarMark(?:\s|>)/u);
  });

  it("keeps shared operational status states on the approved Praviar mark", () => {
    const globals = readWebFile("src/app/globals.css");
    const frame = readWebFile(
      "src/components/shared/operational-status-frame.tsx",
    );
    const statusSurfaces = [
      "src/components/shared/account-control-status-state.tsx",
      "src/components/shared/library-status-state.tsx",
      "src/components/shared/workspace-status-state.tsx",
    ];

    expect(globals).toContain(".praviar-operational-field");
    expect(globals).toContain("/brand/visuals/praviar-app-evidence-field.svg");
    expect(frame).toContain("PraviarMarkFrame");
    expect(frame).toContain("<PraviarMarkFrame");
    expect(frame).toContain("data-praviar-status-frame");
    expect(frame).toContain("praviar-operational-field");
    expect(frame).not.toContain("praviar-report-decision-field");
    expect(frame).not.toMatch(/<PraviarMark(?:\s|>)/u);
    expect(frame).not.toContain('variant="mono"');
    expect(frame).not.toContain("BenzeneArc");

    for (const file of statusSurfaces) {
      const source = readWebFile(file);
      expect(source).toContain("OperationalStatusFrame");
      expect(source).not.toContain("<PraviarMark");
    }
  });

  it("keeps retired logo migration scripts out of active tooling", () => {
    const scriptsDir = resolve(REPO_ROOT, "scripts");
    const retiredBrandTerms = [
      "swap-flaskconical",
      "FlaskConical",
      "BenzeneArc",
      "chemistry-stain",
      "benzene-arc mark",
    ];
    const absoluteWorkstationPath = /\/Users\/[^/]+\/Praviar/u;
    const scriptFiles = readdirSync(scriptsDir)
      .filter((file) => file.endsWith(".py") || file.endsWith(".sh"))
      .map((file) => `scripts/${file}`);

    for (const file of scriptFiles) {
      const source = readRepoFile(file);

      for (const term of retiredBrandTerms) {
        expect(
          source,
          `${file} still references retired Praviar logo migration term: ${term}`,
        ).not.toContain(term);
      }
      expect(source).not.toMatch(absoluteWorkstationPath);
    }
  });

  it("keeps active product UI free of retired lab-vessel brand metaphors", () => {
    const activeSourceFiles = walkWebDir("src").filter(
      (file) => file.endsWith(".ts") || file.endsWith(".tsx"),
    );
    const retiredTerms = ["FlaskConical", "Beaker"];
    const offenders = activeSourceFiles.flatMap((file) => {
      const source = readWebFile(file);
      return retiredTerms
        .filter((term) => source.includes(term))
        .map((term) => `${file}: ${term}`);
    });

    expect(
      offenders,
      "Retired lab-vessel icons should stay out of active UI; use evidence, library, or analysis icons instead.",
    ).toEqual([]);
  });

  it("keeps public tests free of retired brand-icon vocabulary", () => {
    const governanceAssertionFiles = new Set([
      "tests/design-system/brand-governance.test.ts",
      "tests/design-system/brand-governance-private-docs-and-ci.private.test.ts",
      "tests/unit/constants.test.ts",
    ]);
    const testSource = walkWebDir("tests")
      .filter((file) => /\.(?:ts|tsx)$/u.test(file))
      .filter((file) => !governanceAssertionFiles.has(file))
      .map((file) => [file, readWebFile(file)] as const);
    const retiredBrandTerms =
      /\b(?:flask-vial|FlaskConical|flask-conical|loading-flask|BenzeneArc|benzene-arc)\b/u;
    const offenders = testSource.flatMap(([file, source]) =>
      retiredBrandTerms.test(source) ? [`${file}: retired brand icon`] : [],
    );

    expect(
      offenders,
      "Tests should not normalize retired Praviar logo-era icon vocabulary.",
    ).toEqual([]);
  });

  it("keeps active design guidance free of retired mark-ring wording", () => {
    const designSource = readWebFile("DESIGN.md");

    expect(
      designSource,
      "The canonical evidence mark uses bands/strokes, not the retired ring-logo language.",
    ).not.toMatch(/\bmark\s+ring\b|\bring\s+segments\b|\blogo\s+ring\b/iu);
  });

  it("uses one shared evidence-field pattern for loading, empty, and status surfaces", () => {
    const globals = readWebFile("src/app/globals.css");
    const files = [
      "src/components/shared/route-loading-frame.tsx",
      "src/components/shared/operational-status-frame.tsx",
      "src/components/shared/empty-state.tsx",
      "src/components/analysis-wizard/evidence-launch-rail.tsx",
    ];

    expect(globals).toContain(".praviar-evidence-field-pattern");
    expect(globals).toContain("background-size: 28px 28px");

    for (const file of files) {
      const source = readWebFile(file);
      expect(source).toContain("praviar-evidence-field-pattern");
      expect(source).not.toContain("linear-gradient(135deg, transparent 0 48%");
      expect(source).not.toContain("backgroundSize");
    }
  });

  it("keeps shared state surfaces on the canonical mark frame", () => {
    const directMarkFrameSurfaces = [
      "src/components/auth/auth-surface.tsx",
      "src/components/analysis-wizard/evidence-launch-rail.tsx",
      "src/components/report-page/mobile-report-command-bar.tsx",
      "src/components/shared/app-error-state.tsx",
      "src/components/shared/empty-state.tsx",
      "src/components/shared/operational-status-frame.tsx",
      "src/components/shared/route-loading-frame.tsx",
      "src/components/shared/welcome-modal.tsx",
      "src/components/shared/welcome-modal-step-content.tsx",
    ];
    const sharedFrameSurfaces = [
      "src/components/analysis-detail/analysis-states.tsx",
      "src/components/report-page/report-status-state.tsx",
    ];

    for (const file of directMarkFrameSurfaces) {
      const source = readWebFile(file);

      expect(source, `${file} should import the shared mark frame`).toContain(
        "PraviarMarkFrame",
      );
      expect(
        source,
        `${file} should not render a raw state-surface PraviarMark`,
      ).not.toMatch(/<PraviarMark(?:\s|>)/u);
    }

    for (const file of sharedFrameSurfaces) {
      const source = readWebFile(file);

      expect(
        source,
        `${file} should use the shared status frame that owns the canonical mark`,
      ).toContain("OperationalStatusFrame");
      expect(
        source,
        `${file} should not render a raw state-surface PraviarMark`,
      ).not.toMatch(/<PraviarMark(?:\s|>)/u);
    }
  });

  it("keeps chart legend and tooltip markers on the shared swatch primitive", () => {
    const globals = readWebFile("src/app/globals.css");
    const chartSwatch = readWebFile("src/components/charts/chart-swatch.tsx");
    const chartSurfaces = [
      "src/components/admin-analytics/models-tab.tsx",
      "src/components/admin-analytics/tooltips.tsx",
      "src/components/charts/usage-chart.tsx",
      "src/components/charts/risk-donut.tsx",
    ];

    expect(globals).toContain(".praviar-chart-swatch");
    expect(chartSwatch).toContain("--chart-swatch-color");

    for (const file of chartSurfaces) {
      const source = readWebFile(file);
      expect(source, `${file} should use the shared chart swatch.`).toContain(
        "ChartSwatch",
      );
      expect(
        source,
        `${file} should not hand-paint chart markers with raw inline backgroundColor.`,
      ).not.toContain("backgroundColor");
    }
  });

  it("keeps report triage relevance markers on one neutral-safe swatch map", () => {
    const sharedMap = readWebFile("src/components/report/triage-relevance.ts");
    const markerSurfaces = [
      "src/components/report/audit-tab-triage-decisions-card.tsx",
      "src/components/report/funnel-explorer-triage-table.tsx",
    ];

    expect(sharedMap).toContain('not_relevant: "var(--text-tertiary)"');
    expect(sharedMap).not.toContain("bg-error");

    for (const file of markerSurfaces) {
      const source = readWebFile(file);
      expect(
        source,
        `${file} should render triage markers with ChartSwatch.`,
      ).toContain("ChartSwatch");
      expect(
        source,
        `${file} should not local-paint triage dots with Tailwind bg classes.`,
      ).not.toContain("h-2 w-2 rounded-full");
    }
  });

  it("keeps source health markers deterministic across browsers", () => {
    const helper = readWebFile("src/components/report/summary-tab-helpers.ts");
    const card = readWebFile(
      "src/components/report/summary-tab-source-health-card.tsx",
    );
    const patentRiskHelper = readWebFile(
      "src/components/patent/patent-risk-card-helpers.ts",
    );
    const patentRiskSummary = readWebFile(
      "src/components/patent/patent-risk-card-summary.tsx",
    );

    expect(helper).toContain("SOURCE_STATUS_SWATCH_COLORS");
    expect(helper).not.toContain("JURISDICTION_FLAGS");
    expect(helper).not.toContain("SOURCE_STATUS_DOT");
    expect(card).toContain("ChartSwatch");
    expect(card).toContain("formatJurisdictionScopeLabel");
    expect(card).toContain("not directly searched");
    expect(card).not.toContain("h-2 w-2 rounded-full");
    expect(patentRiskHelper).toContain("getPatentJurisdictionCode");
    expect(patentRiskHelper).not.toContain("JURISDICTION_FLAGS");
    expect(patentRiskSummary).toContain("Jurisdiction");
  });

  it("keeps active React surfaces free of negative letter spacing", () => {
    const activeReactFiles = walkWebDir("src").filter((file) =>
      /\.(?:ts|tsx)$/u.test(file),
    );

    for (const file of activeReactFiles) {
      const source = readWebFile(file);

      expect(
        source,
        `${file} should not compress premium typography with tracking-tight.`,
      ).not.toContain("tracking-tight");
      expect(
        source,
        `${file} should not use arbitrary negative tracking classes.`,
      ).not.toMatch(/tracking-\[-/u);
    }
  });

  it("keeps evidence charts from duplicating described-by data in hidden lists", () => {
    for (const file of [
      "src/components/charts/search-funnel.tsx",
      "src/components/charts/timing-waterfall.tsx",
      "src/components/charts/usage-chart.tsx",
      "src/components/charts/risk-donut.tsx",
    ]) {
      const source = readWebFile(file);
      expect(
        source,
        `${file} should keep detailed chart data in aria-describedby only.`,
      ).not.toContain('<ul className="sr-only">');
    }
  });

  it("keeps dashboard route loading fallbacks on the shared server-safe skeleton primitive", () => {
    const packageJson = JSON.parse(readWebFile("package.json")) as {
      dependencies?: Record<string, string>;
      devDependencies?: Record<string, string>;
    };
    const loadingFiles = walkWebDir("src/app/(dashboard)").filter((file) =>
      file.endsWith("/loading.tsx"),
    );

    expect(packageJson.dependencies).not.toHaveProperty(
      "react-loading-skeleton",
    );
    expect(packageJson.devDependencies).not.toHaveProperty(
      "react-loading-skeleton",
    );
    expect(loadingFiles.length).toBeGreaterThan(0);

    for (const file of loadingFiles) {
      const source = readWebFile(file);
      expect(source, `${file} should not need a client boundary`).not.toContain(
        '"use client"',
      );
      expect(
        source,
        `${file} should not use react-loading-skeleton in route fallbacks`,
      ).not.toContain("react-loading-skeleton");
      expect(
        source,
        `${file} should not use the ui skeleton alias in route fallbacks`,
      ).not.toContain("@/components/ui/skeleton");
      expect(
        source,
        `${file} should not hand-roll skeleton blocks`,
      ).not.toContain("SkeletonBlock");
      expect(
        source,
        `${file} should not hand-roll pulsing placeholders`,
      ).not.toContain("animate-pulse");
      expect(
        source,
        `${file} should not use raw surface-hover placeholder fills`,
      ).not.toContain("bg-[var(--surface-hover)]");
      expect(
        source,
        `${file} should rely on shared skeleton color tokens`,
      ).not.toMatch(
        /baseColor|highlightColor|--skeleton-base|--skeleton-highlight/u,
      );
    }
  });

  it("keeps fade-up entrance motion behind a no-preference media query", () => {
    const globals = readWebFile("src/app/globals.css");
    const baseFadeUp = globals.match(/\.animate-fade-up\s*\{(?<body>[^}]*)\}/u)
      ?.groups?.body;

    expect(baseFadeUp).toContain("opacity: 1");
    expect(baseFadeUp).not.toContain("animation:");
    expect(globals).toMatch(
      /@media\s*\(prefers-reduced-motion:\s*no-preference\)\s*\{[\s\S]*\.animate-fade-up\s*\{[\s\S]*animation:\s*slide-up/u,
    );
  });

  it("turns decorative motion fully off for reduced-motion users", () => {
    const globals = readWebFile("src/app/globals.css");
    const reduceMotionBlock = globals.match(
      /@media\s*\(prefers-reduced-motion:\s*reduce\)\s*\{(?<body>[\s\S]*)\}\s*$/u,
    )?.groups?.body;

    expect(reduceMotionBlock).toContain("scroll-behavior: auto !important");
    expect(reduceMotionBlock).toContain("animation: none !important");
    for (const selector of [
      ".hover-bond-rotate:hover svg",
      ".pulse-glow",
      ".skeleton-shimmer",
      ".animate-count-up",
      ".animate-fade-up",
    ]) {
      expect(
        reduceMotionBlock,
        `${selector} should be explicitly quiet in reduced motion`,
      ).toContain(selector);
    }
  });

  it("keeps imperative scroll calls motion-aware", () => {
    const sourceFiles = walkWebDir("src").filter((file) =>
      /\.(ts|tsx)$/u.test(file),
    );
    const offenders = sourceFiles.filter((file) =>
      readWebFile(file).includes('behavior: "smooth"'),
    );
    expect(
      offenders,
      `Imperative smooth scrolling ignores prefers-reduced-motion:\n${offenders.join("\n")}`,
    ).toEqual([]);

    for (const file of [
      "src/app/(dashboard)/analyses/[id]/report/page.tsx",
      "src/components/shared/onboarding-tooltip.tsx",
      "src/components/report/patents-tab.tsx",
      "src/components/report/chat-panel.tsx",
    ]) {
      const source = readWebFile(file);
      expect(source).toContain("motionAwareScrollBehavior");
    }
  });

  it("keeps dashboard route entry points wired to branded app headers", () => {
    const dashboardRouteContracts = [
      {
        file: "src/app/(dashboard)/dashboard/page.tsx",
        required: ["DashboardPageHeader"],
      },
      {
        file: "src/app/(dashboard)/analyses/page.tsx",
        required: ["AnalysesPageHeader"],
      },
      {
        file: "src/app/(dashboard)/analyses/[id]/page.tsx",
        required: ["AnalysisDetailContent"],
      },
      {
        file: "src/components/analysis-detail/analysis-detail-content.tsx",
        required: [
          "AnalysisHeader",
          "AnalysisAuthState",
          "AnalysisLoadingState",
        ],
      },
      {
        file: "src/app/(dashboard)/batch/page.tsx",
        required: ["BatchPageHeader"],
      },
      {
        file: "src/app/(dashboard)/billing/page.tsx",
        required: ["BillingHeader"],
      },
      {
        file: "src/app/(dashboard)/compounds/page.tsx",
        required: ["CompoundsPageHeader"],
      },
      {
        file: "src/app/(dashboard)/help/page.tsx",
        required: ["HelpPageHeader"],
      },
      {
        file: "src/app/(dashboard)/monitors/page.tsx",
        required: ["MonitorsPageHeader"],
      },
      {
        file: "src/app/(dashboard)/patents/page.tsx",
        required: ["PatentsPageHeader"],
      },
      {
        file: "src/app/(dashboard)/reviews/page.tsx",
        required: ["ReviewQueuePage"],
      },
      {
        file: "src/app/(dashboard)/settings/page.tsx",
        required: ["SettingsPageHeader"],
      },
      {
        file: "src/app/(dashboard)/settings/notifications/page.tsx",
        required: ["NotificationSettingsPage"],
      },
      {
        file: "src/app/(dashboard)/analyses/new/page.tsx",
        required: ["PraviarMarkFrame"],
      },
      {
        file: "src/app/(dashboard)/admin/page.tsx",
        required: ["AppSurfaceHeader"],
      },
      {
        file: "src/app/(dashboard)/admin/analytics/page.tsx",
        required: ["AppSurfaceHeader"],
      },
      {
        file: "src/app/(dashboard)/capabilities/page.tsx",
        required: ["AppSurfaceHeader"],
      },
      {
        file: "src/app/(dashboard)/config/page.tsx",
        required: ["AppSurfaceHeader"],
      },
    ];

    for (const contract of dashboardRouteContracts) {
      const source = readWebFile(contract.file);
      for (const required of contract.required) {
        expect(
          source,
          `${contract.file} should keep its first app surface wired to ${required}`,
        ).toContain(required);
      }
    }
  });

  it("keeps every app error and not-found surface on the Praviar recovery brand", () => {
    const recoverySurfaces = walkWebDir("src/app").filter((file) =>
      /(?:^|\/)(?:global-error|error|not-found)\.tsx$/u.test(file),
    );

    expect(recoverySurfaces.length).toBeGreaterThan(0);

    for (const file of recoverySurfaces) {
      const source = readWebFile(file);
      const hasPraviarRecovery =
        source.includes("RouteError") ||
        source.includes("PraviarMark") ||
        source.includes("AppErrorState") ||
        source.includes("EmptyState");

      expect(
        hasPraviarRecovery,
        `${file} should use the shared recovery surface or render the Praviar mark.`,
      ).toBe(true);
      expect(
        source,
        `${file} should not use a generic warning icon.`,
      ).not.toContain("AlertTriangle");
      expect(
        source,
        `${file} should not use a generic file icon.`,
      ).not.toContain("FileQuestion");
      expect(source, `${file} should avoid generic white fills.`).not.toContain(
        "#FFFFFF",
      );
      expect(
        source,
        `${file} should avoid generic bg-white utilities.`,
      ).not.toContain("bg-white");
    }
  });

  it("keeps every app loading surface on tokenized premium skeletons", () => {
    const loadingSurfaces = walkWebDir("src/app").filter((file) =>
      /(?:^|\/)loading\.tsx$/u.test(file),
    );

    expect(loadingSurfaces.length).toBeGreaterThan(0);

    for (const file of loadingSurfaces) {
      const source = readWebFile(file);
      const hasPremiumLoadingPrimitive = [
        "Skeleton",
        "skeleton-base",
        "skeleton-highlight",
        "surface-hover",
        "surface-muted",
        "ReportLoading",
        "StatusState",
      ].some((term) => source.includes(term));

      expect(
        hasPremiumLoadingPrimitive,
        `${file} should use tokenized skeletons or branded status-state loading.`,
      ).toBe(true);
      for (const forbidden of [
        "bg-white",
        "text-white",
        "#FFFFFF",
        "bg-gray-",
        "bg-slate-",
        "text-gray-",
        "text-slate-",
      ]) {
        expect(
          source,
          `${file} leaked generic loading color ${forbidden}`,
        ).not.toContain(forbidden);
      }
    }
  });

  it("keeps secondary marketing routes wired to generated evidence heroes", () => {
    const marketingRouteContracts = [
      {
        file: "src/app/page.tsx",
        required: ["MarketingHomePage"],
      },
      {
        file: "src/app/(marketing)/methodology/page.tsx",
        required: ["SecondaryEvidenceHero"],
      },
      {
        file: "src/app/(marketing)/compare/adaptive-agentic/page.tsx",
        required: ["SecondaryEvidenceHero"],
      },
      {
        file: "src/app/(marketing)/compare/lite-vs-agentic/page.tsx",
        required: ['redirect("/compare/adaptive-agentic")'],
      },
      {
        file: "src/app/(marketing)/for-biotech-founders/page.tsx",
        required: [
          "praviar-report-hero-field",
          "founder-conversation-v1.webp",
          "SyntheticEditorialDisclosure",
        ],
      },
      {
        file: "src/app/(marketing)/privacy/page.tsx",
        required: ["LegalDocumentPage"],
      },
      {
        file: "src/app/(marketing)/terms/page.tsx",
        required: ["LegalDocumentPage"],
      },
      {
        file: "src/app/(marketing)/trust/page.tsx",
        required: ["TrustPage"],
      },
    ];

    for (const contract of marketingRouteContracts) {
      const source = readWebFile(contract.file);
      for (const required of contract.required) {
        expect(
          source,
          `${contract.file} should keep its first public surface wired to ${required}`,
        ).toContain(required);
      }
    }
  });

  it("keeps the landing hero product story prominent without generated document imagery", () => {
    const hero = readWebFile("src/components/marketing/home-page.tsx");
    const heroShell = readWebFile(
      "src/components/marketing/home-page-hero-shell.tsx",
    );

    expect(hero).toContain("HomePageDemoPanel");
    expect(hero).not.toContain("compound-to-evidence-v1.webp");
    expect(heroShell).toContain('data-testid="homepage-public-preview"');
    expect(heroShell).toContain("PUBLIC_PRIMARY_ACTION");
    expect(heroShell).toContain("Informational only");
    expect(heroShell).toContain('data-testid="homepage-hero-caveat"');
    expect(heroShell).not.toContain("compound-to-evidence-v1.webp");
    expect(heroShell).not.toContain("/sign-up");
    expect(heroShell).not.toContain("/billing");
    expect(heroShell).not.toContain('data-testid="homepage-hero-brand-lockup"');
  });

  it("keeps public first-viewport surfaces paired with generated brand fields", () => {
    const publicSurfaces = [
      {
        file: "src/components/marketing/home-page.tsx",
        required: [
          "praviar-hero-field",
          "HomePageHeroShell",
          "HomePageDemoPanel",
        ],
      },
      {
        file: "src/app/(marketing)/sample-reports/page.tsx",
        required: [
          "praviar-report-hero-field",
          "sample-report-anatomy",
          "SampleReportDetailPreviewCard",
        ],
      },
      {
        file: "src/components/marketing/sample-report-detail-hero.tsx",
        required: ["Synthetic sample", "What the fictional scenario flags"],
      },
      {
        file: "src/app/(marketing)/sample-reports/[slug]/page.tsx",
        required: [
          "praviar-report-hero-field",
          "SampleReportDetailHero",
          "SampleReportDetailPreviewCard",
        ],
      },
      {
        file: "src/components/marketing/trust-page.tsx",
        required: [
          "praviar-trust-hero-field",
          "trust-control-visual",
          "The work stays visible",
        ],
      },
      {
        file: "src/components/marketing/secondary-evidence-hero.tsx",
        required: [
          "praviar-secondary-hero-field",
          "/brand/visuals/praviar-sample-report-field.svg",
          "PraviarMark",
        ],
      },
      {
        file: "src/components/marketing/legal-document-page.tsx",
        required: ["praviar-legal-hero-field", "PraviarMark"],
      },
    ];

    for (const surface of publicSurfaces) {
      const source = readWebFile(surface.file);
      for (const required of surface.required) {
        expect(
          source,
          `${surface.file} is missing required first-viewport brand signal ${required}`,
        ).toContain(required);
      }
    }
  });

  it("keeps synthetic editorial people disclosed and provenance-governed", () => {
    const disclosure = readWebFile(
      "src/components/marketing/synthetic-editorial-disclosure.tsx",
    );
    const manifest = JSON.parse(
      readWebFile("public/brand/editorial/provenance.public.webmanifest"),
    ) as {
      assets: Array<{
        approved_routes: string[];
        file: string;
        sha256: string;
        status: string;
      }>;
      public_disclosure: string;
      scene_policy: string;
    };
    const expectedHashes = new Map([
      [
        "team-conversation-v1.webp",
        "fb70e06255efc98bb5a10e2eb39d969bf0d4d50a0ae6c8878a37e08c608a071e",
      ],
      [
        "founder-conversation-v1.webp",
        "0bea99559cadb384ef6515d453f06b4b3ced586702fd9a05b55b9568f942a23c",
      ],
      [
        "counsel-conversation-v1.webp",
        "5fc9029e515ecb55a4e5b9bbfdf43f4ba209fb15f01da94dc6967a0a6cc3a840",
      ],
      [
        "deployment-conversation-v1.webp",
        "d830d0715b26e2c05e13965e39651e3c7691263e76e6144c30e18f5344d287ef",
      ],
      [
        "method-conversation-v1.webp",
        "9f2454cd88cce527187af947379882667ab48d07b30d4e61a112ed29e527c8d1",
      ],
    ]);

    expect(manifest.public_disclosure).toContain(
      "not Praviar staff, customers, facilities, or a case study",
    );
    expect(disclosure).toContain("AI-generated editorial illustration");
    expect(disclosure).toContain(
      "not Praviar staff, customers, facilities, or a case study",
    );
    expect(disclosure).toContain("text-xs");
    expect(manifest.assets).toHaveLength(expectedHashes.size);
    expect(manifest.scene_policy).toContain("Positive-only");
    expect(
      manifest.assets.map((asset) => [asset.file, asset.approved_routes]),
    ).toEqual([
      ["team-conversation-v1.webp", ["/"]],
      ["founder-conversation-v1.webp", ["/for-biotech-founders"]],
      ["counsel-conversation-v1.webp", ["/sample-reports"]],
      ["deployment-conversation-v1.webp", ["/trust"]],
      ["method-conversation-v1.webp", ["/methodology"]],
    ]);

    for (const asset of manifest.assets) {
      const expectedHash = expectedHashes.get(asset.file);
      const file = `public/brand/editorial/${asset.file}`;
      const bytes = readWebBinary(file);

      expect(expectedHash, `${asset.file} is not governed`).toBeTypeOf(
        "string",
      );
      expect(asset.status).toBe("approved_positive_only_human_scene");
      expect(asset.sha256).toBe(expectedHash);
      expect(sha256(bytes)).toBe(expectedHash);
      expect(bytes.byteLength).toBeLessThan(150_000);
    }
  });

  it("keeps fabricated technical collages out of public marketing routes", () => {
    const marketingSources = [
      "src/components/marketing/home-page.tsx",
      "src/components/marketing/home-page-hero-shell.tsx",
      "src/app/(marketing)/sample-reports/page.tsx",
      "src/app/(marketing)/methodology/page.tsx",
      "src/components/marketing/trust-page.tsx",
    ].map(readWebFile);
    const bannedLegacyAssets = [
      "compound-to-evidence-v1.webp",
      "evidence-chain-desk-v1.webp",
      "search-to-claim-field-v1.webp",
      "controlled-review-workspace-v1.webp",
    ];

    for (const source of marketingSources) {
      for (const asset of bannedLegacyAssets) {
        expect(
          source,
          `${asset} must not return to a public route`,
        ).not.toContain(asset);
      }
    }
  });

  it("keeps the trust page grounded without generated document imagery", () => {
    const globals = readWebFile("src/app/globals.css");
    const trustPage = readWebFile("src/components/marketing/trust-page.tsx");
    const boundaryArtifactStart = trustPage.indexOf(
      "function TrustBoundaryArtifact",
    );
    expect(boundaryArtifactStart).toBeGreaterThanOrEqual(0);
    const boundaryArtifact = trustPage.slice(boundaryArtifactStart);

    expect(globals).toContain(".praviar-ink-frame");
    expect(globals).toContain("pointer-events: none;");
    expect(
      globals.match(/\.praviar-trust-hero-field\s*\{[\s\S]*?\}/u)?.[0] ?? "",
    ).not.toContain("praviar-trust-control-field.svg");
    expect(trustPage).not.toContain("controlled-review-workspace-v1.webp");
    expect(trustPage).not.toContain("praviar-trust-control-field");
    expect(trustPage).toContain("praviar-ink-frame");
    expect(trustPage).not.toContain(
      "bg-[url('/brand/visuals/praviar-trust-control-field.svg')]",
    );
    expect(trustPage).not.toContain("opacity-[0.82]");
    expect(trustPage).not.toContain("opacity-[0.64]");
    expect(boundaryArtifact).not.toContain("border-[var(--border-default)]");
  });

  it("keeps secondary hero framed visuals distinct from the section background", () => {
    const secondaryHero = readWebFile(
      "src/components/marketing/secondary-evidence-hero.tsx",
    );

    expect(secondaryHero).toContain(
      'fieldClassName = "praviar-secondary-hero-field"',
    );
    expect(secondaryHero).toContain(
      'visualSrc = "/brand/visuals/praviar-sample-report-field.svg"',
    );
    expect(secondaryHero).toContain("PraviarMarkFrame");
    expect(secondaryHero).toContain('surface="dark"');
    expect(secondaryHero).toContain('loading="eager"');
    expect(secondaryHero).not.toContain("preload");
    expect(secondaryHero).not.toMatch(/\bpriority\b/u);
    expect(secondaryHero).not.toMatch(/<PraviarMark(?:\s|>)/u);
    expect(secondaryHero).not.toContain(
      'visualSrc = "/brand/visuals/praviar-hero-evidence.svg"',
    );
  });

  it("keeps the first-run brand step out of generic icon rendering", () => {
    const welcomeConstants = readWebFile(
      "src/components/shared/welcome-modal-constants.ts",
    );
    const welcomeStepContent = readWebFile(
      "src/components/shared/welcome-modal-step-content.tsx",
    );

    expect(welcomeConstants).toContain("icon: PraviarMark");
    expect(welcomeStepContent).toContain("isPraviarStep");
    expect(welcomeStepContent).toContain("PraviarMarkFrame");
    expect(welcomeStepContent).toContain('step.preview === "packet"');
  });

  it("keeps mobile app chrome visibly branded", () => {
    const topbar = readWebFile("src/components/layout/topbar.tsx");

    expect(topbar).toContain('aria-label="Praviar dashboard"');
    expect(topbar).toContain("PraviarLockup");
    expect(topbar).toContain('translate="no"');
  });

  it("keeps fixed logo variants on the selected evidence mark palette", () => {
    const mark = readWebFile("src/components/icons/praviar-mark-data.json");
    const globals = readWebFile("src/app/globals.css");

    expect(mark).toContain('"#F6F4EF"');
    expect(mark).toContain('"#0B1F24"');
    expect(mark).toContain('"#0E6F68"');
    expect(mark).toContain('"#5FB7A6"');
    expect(mark).toContain('"#B87333"');
    expect(mark).toContain('"#D7ECE5"');
    expect(mark).not.toContain('"#8ED7C9"');
    expect(mark).not.toContain("#D49A5A");
    expect(mark).not.toContain("#E7F5F0");
    expect(globals).toContain("--praviar-mark-paper: #f6f4ef;");
    expect(globals).toContain("--praviar-mark-ink: #0b1f24;");
    expect(globals).toContain("--praviar-mark-copper: #b87333;");
    expect(globals).toContain("--brand-soft-mint: #d7ece5;");
    expect(globals).toContain("--color-brand-soft-mint");
  });

  it("uses the outlined mark variant on public light evidence surfaces", () => {
    const publicLightSurfaces = [
      "src/app/global-error.tsx",
      "src/components/marketing/home-page-demo-panel.tsx",
      "src/components/marketing/legal-document-page.tsx",
    ];
    const framedLightSurfaces = [
      "src/components/brand/fto-dossier-preview.tsx",
    ];

    for (const file of publicLightSurfaces) {
      const source = readWebFile(file);

      expect(
        source,
        `${file} should outline direct light-surface marks`,
      ).toMatch(/<PraviarMark[\s\S]*variant="onLight"/u);
    }

    for (const file of framedLightSurfaces) {
      const source = readWebFile(file);

      expect(
        source,
        `${file} should use the shared mark frame on layered paper/mint surfaces.`,
      ).toContain("PraviarMarkFrame");
      expect(
        source,
        `${file} should not render a raw light-surface PraviarMark`,
      ).not.toMatch(/<PraviarMark(?:\s|>)/u);
    }
  });

  it("keeps active generated brand fields inside Palette A", () => {
    const generatedVisualFields = readdirSync(
      resolve(WEB_ROOT, "public/brand/visuals"),
    )
      .filter((file) => file.endsWith(".svg"))
      .map((file) => `public/brand/visuals/${file}`)
      .sort();
    const activeBrandFields = [
      "src/app/icon.svg",
      "public/brand/praviar-mark.svg",
      "public/brand/praviar-mark-on-dark.svg",
      "public/brand/praviar-mark-on-light.svg",
      ...generatedVisualFields,
    ];
    const generatedFieldCorePalette = corePaletteHexSet();
    const forbiddenGeneratedTints = [
      "#D49A5A",
      "#E7F5F0",
      "#EAF3EE",
      "#CFE7DE",
      "#DCECE5",
      "#E1F1EB",
      "#C9E5DC",
      "#FFFFFF",
      "#FFF",
    ];

    for (const file of activeBrandFields) {
      const svg = readWebFile(file).toUpperCase();
      for (const tint of forbiddenGeneratedTints) {
        expect(
          svg,
          `${file} contains off-palette generated tint ${tint}`,
        ).not.toContain(tint);
      }
      if (file.includes("/visuals/")) {
        const usedColors = extractHexColors(svg);
        expect(usedColors.length).toBeGreaterThan(0);
        for (const color of usedColors) {
          expect(
            generatedFieldCorePalette.has(color),
            `${file} uses ${color}; generated evidence fields should stay on the six-color core Praviar mark palette.`,
          ).toBe(true);
        }
      }
      for (const legacyTerm of [
        "methylene",
        "eosin",
        "iodine",
        "bromocresol",
        "permanganate",
        "gold-leaf",
        "chemistry-stain",
        "blueglow",
        "redsignal",
        "glowblue",
        "glowgold",
        "coolglow",
        "riskglow",
      ]) {
        expect(
          svg.toLowerCase(),
          `${file} contains legacy palette vocabulary ${legacyTerm}`,
        ).not.toContain(legacyTerm);
      }
    }
  });

  it("keeps the homepage demo artifact on evidence fields, not generic glows", () => {
    const demoPanel = readWebFile(
      "src/components/marketing/home-page-demo-panel.tsx",
    );

    expect(demoPanel).toContain("praviar-evidence-field-pattern");
    expect(demoPanel).toContain("homepage-demo-panel-underlay");
    expect(demoPanel).not.toContain("blur-xl");
    expect(demoPanel).not.toContain("Teal glow");
    expect(demoPanel).not.toContain("bg-[color:rgba(var(--brand-primary-rgb)");
  });

  it("keeps generated visual fields on one responsive artboard", () => {
    const visualFields = readdirSync(resolve(WEB_ROOT, "public/brand/visuals"))
      .filter((file) => file.endsWith(".svg"))
      .sort();

    expect(visualFields.length).toBeGreaterThan(0);

    for (const field of visualFields) {
      const svg = readWebFile(`public/brand/visuals/${field}`);

      expect(
        svg,
        `${field} should share the 1600x1000 visual field artboard so CSS background-size rules crop consistently.`,
      ).toContain('viewBox="0 0 1600 1000"');
      expect(
        svg,
        `${field} should not keep a retired 1440x720 crop.`,
      ).not.toContain('viewBox="0 0 1440 720"');
    }
  });

  it("keeps generated evidence fields logo-free and background-only", () => {
    const visualsDir = resolve(WEB_ROOT, "public/brand/visuals");
    const generatedFields = readdirSync(visualsDir)
      .filter((file) => file.endsWith(".svg"))
      .sort();
    const canonicalPathValues = readCanonicalPraviarMarkPaths();
    const retiredPseudoLogoFragments = [
      "l70-41",
      "l70-42",
      "l72 41",
      "l72-41",
      "l73 42",
      "l74-42",
      "l75 42",
      "l76 44",
      "v82l-70",
      "v83l-72",
      "v84l-73",
      "v86l-75",
      "v88l-76",
    ];

    expect(generatedFields.length).toBeGreaterThan(0);

    for (const field of generatedFields) {
      const svg = readWebFile(`public/brand/visuals/${field}`);

      for (const path of canonicalPathValues) {
        expect(
          svg,
          `${field} must stay a background image, not a generated logo source.`,
        ).not.toContain(path);
      }
      expect(svg, `${field} must not contain wordmark text.`).not.toMatch(
        /<text\b|>Praviar</u,
      );
      expect(
        svg,
        `${field} must not identify itself as a logo asset.`,
      ).not.toMatch(/\blogo\b|wordmark|brand mark/i);
      expect(
        svg,
        `${field} must stay decorative and should not expose image semantics.`,
      ).not.toMatch(/\brole=["']img["']/i);
      expect(
        svg,
        `${field} must not create accessible names when used as a CSS background.`,
      ).not.toMatch(/\baria-label=/i);
      for (const fragment of retiredPseudoLogoFragments) {
        expect(
          svg,
          `${field} must not include closed molecule-ring geometry that can read as an alternate logo: ${fragment}`,
        ).not.toContain(fragment);
      }
      expect(
        svg,
        `${field} must not describe background art as a molecule logo.`,
      ).not.toMatch(/\b(?:benzene|molecule logo|hex logo)\b/i);
    }
  });

  it("keeps every generated brand field actively used by the visual layer", () => {
    const visualsDir = resolve(WEB_ROOT, "public/brand/visuals");
    const generatedFields = readdirSync(visualsDir)
      .filter((file) => file.endsWith(".svg"))
      .sort();
    const globals = readWebFile("src/app/globals.css");

    expect(generatedFields.length).toBeGreaterThan(0);

    for (const field of generatedFields) {
      expect(
        globals,
        `Generated visual asset ${field} should be wired into globals.css`,
      ).toContain(`/brand/visuals/${field}`);
    }
  });

  it("keeps the generated credit ledger field on authenticated billing surfaces", () => {
    const globals = readWebFile("src/app/globals.css");
    const projectSection = readWebFile(
      "src/components/marketing/home-page-project-section.tsx",
    );
    const billingCreditPacks = readWebFile(
      "src/components/billing/credit-packs-card.tsx",
    );
    const billingPage = readWebFile("src/app/(dashboard)/billing/page.tsx");
    const fieldBackgroundAsset =
      "public/brand/visuals/praviar-credit-ledger-field.svg";
    const bannedRasterAssets = [
      "public/brand/visuals/praviar-credit-ledger-workspace.png",
      "public/brand/visuals/praviar-credit-ledger-workspace-v2.jpg",
    ];
    const fieldSvg = readWebFile(fieldBackgroundAsset);
    const activeCreditSource = [globals, billingCreditPacks, billingPage].join(
      "\n",
    );
    const creditLedgerBlocks = [
      ...globals.matchAll(/\.praviar-credit-ledger-field\s*\{[\s\S]*?\}/gu),
    ].map((match) => match[0]);
    const capacityRunwayBlocks = [
      ...globals.matchAll(/\.praviar-capacity-runway-field\s*\{[\s\S]*?\}/gu),
    ].map((match) => match[0]);

    expect(existsSync(resolve(WEB_ROOT, fieldBackgroundAsset))).toBe(true);
    for (const rasterAsset of bannedRasterAssets) {
      expect(existsSync(resolve(WEB_ROOT, rasterAsset))).toBe(false);
    }
    expect(fieldSvg).toContain('viewBox="0 0 1600 1000"');
    expect(fieldSvg).not.toMatch(/<text\b|>Praviar</u);
    expect(fieldSvg).not.toMatch(/\blogo\b|wordmark|brand mark/i);
    expect(creditLedgerBlocks.length).toBeGreaterThanOrEqual(2);
    expect(projectSection).not.toContain('import Image from "next/image"');
    expect(projectSection).not.toContain("praviar-credit-ledger-field");
    expect(projectSection).toContain('data-testid="project-surface-grid"');
    expect(projectSection).toContain("Open engineering project");
    expect(projectSection).toContain("PUBLIC_PURCHASING_NOTICE");
    expect(projectSection).toContain("PUBLIC_PRIMARY_ACTION");
    expect(projectSection).not.toContain("/sign-up");
    expect(projectSection).not.toContain('href="/billing');
    expect(billingCreditPacks).toContain(
      'data-testid="billing-credit-ledger-field"',
    );
    expect(billingCreditPacks).toContain(
      'data-testid="billing-credit-ledger-field-scrim"',
    );
    expect(billingCreditPacks).not.toContain(
      'data-testid="credit-pack-rate-ladder"',
    );
    expect(billingCreditPacks).toContain("bg-[var(--bg-surface)]/54");
    expect(billingPage).toContain("praviar-capacity-runway-field");
    expect(billingPage).toContain(
      'data-testid="billing-capacity-runway-field"',
    );
    expect(billingPage).not.toContain(
      "linear-gradient(110deg, rgba(215,236,229",
    );
    expect(projectSection).not.toContain("pricing-ledger-workspace-art");
    expect(activeCreditSource).not.toMatch(
      /\/brand\/visuals\/praviar-credit-ledger-workspace(?:-v2)?\.(?:png|jpg)/u,
    );

    for (const block of creditLedgerBlocks) {
      expect(block).not.toContain(
        "/brand/visuals/praviar-credit-ledger-workspace.png",
      );
      expect(block).not.toContain(
        "/brand/visuals/praviar-credit-ledger-workspace-v2.jpg",
      );
      expect(block).toContain("/brand/visuals/praviar-credit-ledger-field.svg");
      expect(block).toContain(
        "background-blend-mode: normal, screen, soft-light, normal",
      );
      expect(block).toContain("rgba(246, 244, 239, 0.99)");
    }

    expect(capacityRunwayBlocks.length).toBeGreaterThanOrEqual(2);
    for (const block of capacityRunwayBlocks) {
      expect(block).not.toContain(
        "/brand/visuals/praviar-credit-ledger-workspace.png",
      );
      expect(block).not.toContain(
        "/brand/visuals/praviar-credit-ledger-workspace-v2.jpg",
      );
      expect(block).toContain("/brand/visuals/praviar-credit-ledger-field.svg");
      expect(block).toContain("color-mix(in srgb, var(--brand-soft-mint)");
      expect(block).toContain(
        "background-blend-mode: normal, screen, soft-light",
      );
    }
  });

  it("keeps billing account controls on the premium account surface system", () => {
    const globals = readWebFile("src/app/globals.css");
    const currentPlanCard = readWebFile(
      "src/components/billing/current-plan-card.tsx",
    );
    const usageCard = readWebFile("src/components/billing/usage-card.tsx");
    const upgradePlansCard = readWebFile(
      "src/components/billing/upgrade-plans-card.tsx",
    );
    const invoiceHistoryCard = readWebFile(
      "src/components/billing/invoice-history-card.tsx",
    );
    const billingPage = readWebFile("src/app/(dashboard)/billing/page.tsx");
    const billingLoading = readWebFile(
      "src/app/(dashboard)/billing/loading.tsx",
    );
    const appErrorState = readWebFile(
      "src/components/shared/app-error-state.tsx",
    );
    const operationalStatusFrame = readWebFile(
      "src/components/shared/operational-status-frame.tsx",
    );

    for (const accountClass of [
      ".praviar-account-control-card",
      ".praviar-account-control-header",
      ".praviar-account-metric-panel",
      ".praviar-plan-option-card",
      ".praviar-plan-option-card-featured",
    ]) {
      expect(globals).toContain(accountClass);
    }

    for (const source of [
      currentPlanCard,
      usageCard,
      upgradePlansCard,
      invoiceHistoryCard,
      billingPage,
      billingLoading,
    ]) {
      expect(source).toContain("praviar-account-control-card");
      expect(source).toContain("praviar-account-control-header");
      expect(source).not.toContain("bg-[var(--surface-muted)]/35");
    }

    expect(currentPlanCard).toContain("praviar-account-metric-panel");
    expect(usageCard).toContain("praviar-account-metric-panel");
    expect(billingPage).toContain("data-praviar-billing-reconciliation");
    expect(billingPage).toContain("Stripe reconciliation");
    expect(billingPage).toContain("praviar-account-metric-panel");
    expect(billingLoading).toContain("praviar-credit-ledger-field");
    expect(billingLoading).toContain("billing-loading-capacity-runway-field");
    expect(billingLoading).not.toContain("praviar-surface-premium");
    expect(upgradePlansCard).toContain("praviar-plan-option-card");
    expect(upgradePlansCard).toContain("praviar-plan-option-card-featured");
    expect(upgradePlansCard).not.toContain("border-brand-primary/50");
    expect(appErrorState).toContain("praviar-operational-field");
    expect(appErrorState).toContain("praviar-evidence-field-pattern");
    expect(appErrorState).toContain("type-heading-sm");
    expect(operationalStatusFrame).toContain("type-heading-xl");
    expect(operationalStatusFrame).not.toContain("tracking-tight");
  });

  it("keeps the generated analysis launch workspace decorative and governed", () => {
    const globals = readWebFile("src/app/globals.css");
    const pngAsset =
      "public/brand/visuals/praviar-analysis-launch-workspace.png";
    const webpAsset =
      "public/brand/visuals/praviar-analysis-launch-workspace.webp";
    const avifAsset =
      "public/brand/visuals/praviar-analysis-launch-workspace.avif";
    const png = readWebBinary(pngAsset);
    const webp = readWebBinary(webpAsset);
    const avif = readWebBinary(avifAsset);
    const launchBlock = globals.match(
      /\.praviar-analysis-launch-field\s*\{[\s\S]*?\}\s*/u,
    )?.[0];

    expect(existsSync(resolve(WEB_ROOT, pngAsset))).toBe(true);
    expect(existsSync(resolve(WEB_ROOT, webpAsset))).toBe(true);
    expect(existsSync(resolve(WEB_ROOT, avifAsset))).toBe(true);
    expect(readPngDimensions(png)).toEqual({ width: 1672, height: 941 });
    expect(sha256(png)).toBe(
      "d4f6965696b2de98a0cff4c7d4dbd92061f24dcbf2ef43728d914da9cc0e4152",
    );
    expect(png.byteLength).toBeLessThan(2_200_000);
    expect(webp.byteLength).toBeLessThan(100_000);
    expect(avif.byteLength).toBeLessThan(100_000);
    expect(launchBlock, "Missing analysis launch field block").toBeTypeOf(
      "string",
    );
    expect(launchBlock).toContain(
      "/brand/visuals/praviar-analysis-launch-workspace.webp",
    );
    expect(launchBlock).toContain("/brand/visuals/praviar-dossier-thread.svg");
    expect(globals).toContain(
      "/brand/visuals/praviar-analysis-launch-workspace.avif",
    );
    expect(globals).toContain(
      "/brand/visuals/praviar-analysis-launch-workspace.png",
    );
    expect(globals).toContain('type("image/avif")');
    expect(globals).toContain('type("image/webp")');
    expect(globals).toContain('type("image/png")');
    expect(launchBlock).toContain(
      "background-blend-mode: normal, screen, soft-light, normal",
    );
    expect(launchBlock).toContain("rgba(246, 244, 239, 0.99)");
  });

  it("keeps the report decision workspace restrained and governed", () => {
    const globals = readWebFile("src/app/globals.css");
    const reportDecisionBlock = globals.match(
      /\.praviar-report-decision-field\s*\{[\s\S]*?\}\s*/u,
    )?.[0];

    expect(
      reportDecisionBlock,
      "Missing report decision field block",
    ).toBeTypeOf("string");
    expect(reportDecisionBlock).not.toContain("url(");
    expect(reportDecisionBlock).not.toContain("image-set(");
    expect(reportDecisionBlock).not.toContain("background-blend-mode");
    expect(reportDecisionBlock).toContain("rgba(246, 244, 239, 0.99)");
    expect(reportDecisionBlock).not.toContain(
      "/brand/visuals/praviar-report-decision-workspace.png",
    );

    const liveDossierBlock = globals.match(
      /\.praviar-live-dossier-field\s*\{[\s\S]*?\}\s*/u,
    )?.[0];
    expect(liveDossierBlock, "Missing live dossier field block").toBeTypeOf(
      "string",
    );
    expect(liveDossierBlock).not.toContain("url(");
    expect(liveDossierBlock).not.toContain("image-set(");
  });

  it("keeps the evidence desk raster lightweight and background-only", () => {
    const globals = readWebFile("src/app/globals.css");
    const heroShell = readWebFile(
      "src/components/marketing/home-page-hero-shell.tsx",
    );
    const reportPages = [
      "src/app/(marketing)/sample-reports/page.tsx",
      "src/app/(marketing)/sample-reports/[slug]/page.tsx",
      "src/app/(marketing)/for-biotech-founders/page.tsx",
    ].map((file) => readWebFile(file));
    const workspaceAssetWebp =
      "public/brand/visuals/praviar-evidence-desk-field-v2.webp";
    const webp = readWebBinary(workspaceAssetWebp);
    const activeSource = [globals, heroShell, ...reportPages].join("\n");

    expect(existsSync(resolve(WEB_ROOT, workspaceAssetWebp))).toBe(true);
    expect(sha256(webp)).toBe(
      "8ee757dfd6f34c3438bed58d492f090d97356bd84af9e1f1950e1c2d8d2f27f0",
    );
    expect(webp.byteLength).toBeLessThan(70_000);
    expect(activeSource).not.toContain(
      "/brand/visuals/praviar-evidence-desk-field-v2.avif",
    );
    expect(activeSource).toContain(
      "/brand/visuals/praviar-evidence-desk-field-v2.webp",
    );
    expect(activeSource).not.toMatch(
      /<Image[\s\S]+praviar-evidence-desk-field-v2\.(?:avif|webp)|<img[\s\S]+praviar-evidence-desk-field-v2\.(?:avif|webp)/u,
    );
    const heroBlock = globals.match(
      /\.praviar-hero-field\s*\{[\s\S]*?\}\s*/u,
    )?.[0];
    const reportHeroBlock = globals.match(
      /\.praviar-report-hero-field\s*\{[\s\S]*?\}\s*/u,
    )?.[0];

    expect(heroBlock, "Missing .praviar-hero-field block").toBeTypeOf("string");
    expect(heroBlock).toContain("/brand/visuals/praviar-hero-evidence.svg");
    expect(heroBlock).not.toContain(
      "/brand/visuals/praviar-evidence-desk-field-v2",
    );
    expect(heroBlock).toContain(
      "background-blend-mode: normal, screen, soft-light, normal",
    );
    expect(
      reportHeroBlock,
      "Missing .praviar-report-hero-field block",
    ).toBeTypeOf("string");
    expect(reportHeroBlock).toContain(
      "/brand/visuals/praviar-evidence-desk-field-v2.webp",
    );
    expect(reportHeroBlock).toContain(
      "background-blend-mode: normal, screen, soft-light, normal",
    );
  });

  it("pins active raster backgrounds to the governed asset allowlist", () => {
    const globals = readWebFile("src/app/globals.css");
    const activeRasterReferences = [
      ...globals.matchAll(
        /\/brand\/visuals\/[^")]+\.(?:avif|png|jpe?g|webp)/giu,
      ),
    ].map((match) => match[0]);
    const allowedRasterReferences = new Set([
      "/brand/visuals/praviar-analysis-launch-workspace.avif",
      "/brand/visuals/praviar-analysis-launch-workspace.png",
      "/brand/visuals/praviar-analysis-launch-workspace.webp",
      "/brand/visuals/praviar-evidence-desk-field-v2.webp",
      "/brand/visuals/praviar-workflow-atlas-field.webp",
    ]);

    expect(activeRasterReferences.length).toBeGreaterThan(0);
    expect(new Set(activeRasterReferences)).toEqual(allowedRasterReferences);
    expect(activeRasterReferences).not.toContain(
      "/brand/visuals/praviar-report-decision-workspace.png",
    );
    expect(activeRasterReferences).not.toContain(
      "/brand/visuals/praviar-report-provenance-field.avif",
    );
    expect(activeRasterReferences).not.toContain(
      "/brand/visuals/praviar-report-provenance-field.png",
    );
    expect(activeRasterReferences).not.toContain(
      "/brand/visuals/praviar-report-provenance-field.webp",
    );
    expect(activeRasterReferences).not.toContain(
      "/brand/visuals/praviar-admin-control-field.avif",
    );
    expect(activeRasterReferences).not.toContain(
      "/brand/visuals/praviar-admin-control-field.webp",
    );

    const publicRasterFiles = readdirSync(
      resolve(WEB_ROOT, "public/brand/visuals"),
    )
      .filter((file) => /\.(?:avif|png|jpe?g|webp)$/iu.test(file))
      .map((file) => `/brand/visuals/${file}`)
      .sort();
    for (const rasterReference of allowedRasterReferences) {
      expect(publicRasterFiles).toContain(rasterReference);
    }

    const sourceRasterReferences = walkWebDir("src")
      .filter((file) => /\.(?:css|tsx?|jsx?)$/u.test(file))
      .flatMap((file) => {
        const source = readWebFile(file);
        return [
          ...source.matchAll(
            /\/brand\/visuals\/[^"'`)]+\.(?:avif|png|jpe?g|webp)/giu,
          ),
        ].map((match) => ({ file, reference: match[0], source }));
      });

    expect(
      new Set(sourceRasterReferences.map(({ reference }) => reference)),
    ).toEqual(allowedRasterReferences);
    for (const { file, reference, source } of sourceRasterReferences) {
      expect(
        allowedRasterReferences.has(reference),
        `${file} references an ungoverned raster background ${reference}`,
      ).toBe(true);
      expect(
        source,
        `${file} should not render decorative generated raster fields as images`,
      ).not.toMatch(/<(?:Image|img)\b/u);
    }
  });

  it("uses the shared dossier thread to unify major background fields", () => {
    const globals = readWebFile("src/app/globals.css");
    const dossierThreadSvg = readWebFile(
      "public/brand/visuals/praviar-dossier-thread.svg",
    );
    const dossierThread = "/brand/visuals/praviar-dossier-thread.svg";
    const sharedFieldSelectors = [
      ".praviar-marketing-shell",
      ".praviar-hero-field",
      ".praviar-secondary-hero-field",
      ".praviar-report-hero-field",
      ".praviar-trust-hero-field",
      ".praviar-legal-hero-field",
      ".praviar-app-field",
      ".praviar-auth-field",
      ".praviar-auth-visual",
      ".praviar-sidebar-field",
      ".praviar-analysis-launch-field",
      ".praviar-credit-ledger-field",
      ".praviar-share-access-field",
      ".praviar-share-access-panel",
      ".praviar-share-handoff-field",
    ];

    for (const selector of sharedFieldSelectors) {
      const escapedSelector = selector.replace(".", "\\.");
      const block = globals.match(
        new RegExp(`${escapedSelector}\\s*\\{[\\s\\S]*?\\}`, "u"),
      )?.[0];

      expect(block, `${selector} should exist`).toBeTypeOf("string");
      expect(
        block,
        `${selector} should share the generated dossier evidence thread.`,
      ).toContain(dossierThread);
    }

    for (const selector of [
      ".praviar-report-decision-field",
      ".praviar-live-dossier-field",
    ]) {
      const escapedSelector = selector.replace(".", "\\.");
      const block = globals.match(
        new RegExp(`${escapedSelector}\\s*\\{[\\s\\S]*?\\}`, "u"),
      )?.[0];

      expect(block, `${selector} should exist`).toBeTypeOf("string");
      expect(
        block,
        `${selector} should stay free of generated dossier backgrounds.`,
      ).not.toContain(dossierThread);
    }

    expect(dossierThreadSvg).not.toContain("l58-34 58 34v68l-58 34-58-34z");
    expect(dossierThreadSvg).toContain("evidence");
  });

  it("keeps sidebar chrome on generated evidence fields instead of decorative orbs", () => {
    const globals = readWebFile("src/app/globals.css");
    const sidebarField = globals.match(
      /\.praviar-sidebar-field\s*\{[\s\S]*?\}\s*/u,
    )?.[0];

    expect(sidebarField, "Missing .praviar-sidebar-field block").toBeTypeOf(
      "string",
    );
    expect(sidebarField).toContain("/brand/visuals/praviar-dossier-thread.svg");
    expect(sidebarField).not.toContain(
      "/brand/visuals/praviar-app-evidence-field.svg",
    );
    expect(sidebarField).not.toContain("radial-gradient(");
    expect(sidebarField).not.toContain("circle at");

    const sidebarVisuals = [
      ...(sidebarField?.matchAll(/url\("\/brand\/visuals\/(.+?)"\)/gu) ?? []),
    ].map((match) => match[1]);

    for (const visual of sidebarVisuals) {
      const svg = readWebFile(`public/brand/visuals/${visual}`);
      expect(
        svg,
        `${visual} should avoid radial glow fields in the sidebar.`,
      ).not.toMatch(/radialGradient/iu);
    }
  });

  it("keeps report provenance maps on generated evidence fields instead of orbs", () => {
    const globals = readWebFile("src/app/globals.css");
    const provenanceSurface = globals.match(
      /\.praviar-provenance-map,\s*\.praviar-evidence-fact-card\s*\{[\s\S]*?\}\s*/u,
    )?.[0];
    const provenanceMapRules = [
      ...globals.matchAll(/\.praviar-provenance-map[^{]*\{[\s\S]*?\}/gu),
    ].map((match) => match[0]);

    expect(
      provenanceSurface,
      "Missing shared provenance map/fact card block",
    ).toBeTypeOf("string");
    expect(provenanceSurface).toContain(
      "/brand/visuals/praviar-dossier-thread.svg",
    );
    expect(provenanceSurface).toContain("repeating-linear-gradient(");
    expect(provenanceSurface).not.toContain("radial-gradient(");
    expect(provenanceSurface).not.toContain("circle");

    expect(globals).not.toContain(".praviar-provenance-map::after");
    expect(globals).not.toContain(".praviar-provenance-map::before");

    for (const rule of provenanceMapRules) {
      expect(rule).not.toContain("radial-gradient(");
      expect(rule).not.toContain("circle");
      expect(rule).not.toContain("border-radius: 999px");
    }
  });

  it("keeps static public molecule gallery assets on Praviar Ink", () => {
    const markushDir = resolve(WEB_ROOT, "public/brand/markush");
    const moleculeSvgs = readdirSync(markushDir).filter((file) =>
      file.endsWith(".svg"),
    );
    const allowedMarkushHexes = new Set(["#0B1F24", "#0E6F68"]);

    expect(moleculeSvgs.length).toBeGreaterThan(0);

    for (const file of moleculeSvgs) {
      const svg = readWebFile(`public/brand/markush/${file}`);
      const hexes = svg.match(/#[0-9A-Fa-f]{6}/g) ?? [];

      expect(
        svg,
        `${file} should use Praviar Ink for RDKit black strokes/fills.`,
      ).toContain("#0B1F24");
      expect(svg, `${file} still contains generic RDKit black.`).not.toContain(
        "#000000",
      );
      for (const hex of hexes) {
        expect(
          allowedMarkushHexes.has(hex.toUpperCase()),
          `${file} contains off-palette Markush color ${hex}`,
        ).toBe(true);
      }
    }
  });

  it("keeps the PDF viewer paper surface on brand tokens", () => {
    const pdfViewer = readWebFile("src/components/report/pdf-viewer.tsx");

    expect(pdfViewer).toContain("bg-[var(--brand-paper)]");
    expect(pdfViewer).not.toContain("bg-white");
  });

  it("keeps shared reports as one dossier surface instead of duplicate handoff cards", () => {
    const sharedReportPage = readWebFile("src/app/share/[token]/page.tsx");
    const sharedReportShell = readWebFile(
      "src/app/share/[token]/share-page-shell.tsx",
    );
    const sharedReport = readWebFile(
      "src/app/share/[token]/shared-report-card.tsx",
    );

    expect(sharedReportPage).toContain("Verify shared FTO packet");
    expect(sharedReportPage).toContain(
      "Mailbox-verified, read-only Praviar FTO report access",
    );
    expect(sharedReportPage).not.toContain("openGraph");
    expect(sharedReportPage).not.toContain("twitter");
    expect(sharedReportPage).toContain("index: false");
    expect(sharedReportPage).toContain("follow: false");
    expect(sharedReportPage).toContain("SharePageShell");
    expect(sharedReportShell).toContain(
      'className="light praviar-share-access-field',
    );
    expect(sharedReportShell).toContain(
      'className="light praviar-glass-panel overflow-hidden',
    );
    expect(sharedReportShell).toContain(
      "useState<SharedReportResult | null>(null)",
    );
    expect(sharedReportShell).toContain(
      "const result = unlockedResult ?? initialResult",
    );
    expect(sharedReportShell).toContain("onResultChange={handleResultChange}");
    expect(sharedReportShell).toContain("setUnlockedResult(nextResult)");
    expect(sharedReportShell).toContain(
      'document.getElementById("main-content")?.focus',
    );
    expect(sharedReportShell).not.toContain("praviar-marketing-shell");
    expect(sharedReportShell).not.toContain(
      "[font-family:var(--font-newsreader)]",
    );
    expect(sharedReportShell).not.toContain(
      'className="light praviar-evidence-paper overflow-hidden',
    );
    expect(sharedReportShell).not.toContain("praviar-app-field min-h-screen");
    expect(sharedReport).toContain("FtoDossierPreview");
    expect(sharedReport).toContain(
      'aria-label="Shared report access and evidence scope"',
    );
    expect(sharedReport).toContain("border-y border-[var(--border-default)]");
    expect(sharedReport).not.toContain("shared-report-handoff-title");
    expect(sharedReport).not.toContain("External FTO handoff");
    expect(sharedReport).not.toContain("praviar-share-handoff-field");
  });

  it("keeps the layout-level crash surface visibly branded", () => {
    const globalError = readWebFile("src/app/global-error.tsx");

    expect(globalError).toContain("PraviarMark");
    expect(globalError).toContain('<html lang="en" className="light">');
    expect(globalError).toContain("var(--bg-base, #F6F4EF)");
    expect(globalError).toContain("var(--surface-muted, #F2F6F4)");
    expect(globalError).toContain("Diagnostic context has been logged");
    expect(globalError).toContain("var(--brand-mint, #5FB7A6)");
    expect(globalError).not.toContain('variant="onDark"');
    expect(globalError).not.toContain("rgba(184, 115, 51");
    expect(globalError).not.toContain('border: "1px solid #5FB7A6"');
    expect(globalError).toContain("Praviar");
    expect(globalError).not.toContain(">!");
    expect(globalError).not.toContain('color: "white"');
  });

  it("keeps page-level hero/comparison sections as bands rather than large cards", () => {
    const dashboardHeader = readWebFile(
      "src/components/dashboard/page-header.tsx",
    );
    const appSurfaceHeader = readWebFile(
      "src/components/shared/app-surface-header.tsx",
    );
    const newAnalysisPage = readWebFile(
      "src/app/(dashboard)/analyses/new/page.tsx",
    );
    const adaptiveComparePage = readWebFile(
      "src/app/(marketing)/compare/adaptive-agentic/page.tsx",
    );

    expect(dashboardHeader).toContain('chrome="dashboard"');
    expect(appSurfaceHeader).toContain(
      "border-y border-[var(--border-default)]",
    );
    expect(dashboardHeader).not.toContain("praviar-surface-premium flex");
    expect(newAnalysisPage).toContain(
      "border-y border-[var(--border-default)]",
    );
    expect(newAnalysisPage).not.toContain(
      "praviar-surface-premium overflow-hidden rounded-lg",
    );
    expect(adaptiveComparePage).toContain(
      "border-y border-[var(--border-default)] bg-[var(--surface-muted)]",
    );
    expect(adaptiveComparePage).toContain(
      "border-y border-[var(--border-emphasis)] bg-[var(--surface-muted)]",
    );
    expect(adaptiveComparePage).not.toContain("praviar-surface-premium -mx-4");
    expect(adaptiveComparePage).not.toContain(
      "praviar-surface-premium rounded-lg border-dashed",
    );
  });

  it("keeps inverted premium surfaces on readable accent tokens", () => {
    const globals = readWebFile("src/app/globals.css");
    const lightBlock = globals.match(/\.light\s*\{[\s\S]*?\n\s*\}/u)?.[0] ?? "";
    const invertedSurface = readToken(lightBlock, "--surface-inverted");
    const invertedAccent = readToken(lightBlock, "--surface-inverted-accent");
    const invertedSurfaceFiles = [
      "src/app/(marketing)/compare/adaptive-agentic/page.tsx",
      "src/app/(marketing)/methodology/page.tsx",
      "src/components/marketing/trust-page.tsx",
    ];

    expect(invertedSurface).toBe("#0b1f24");
    expect(invertedAccent).toBe("#5fb7a6");
    expect(
      contrastRatio(invertedAccent!, invertedSurface!),
    ).toBeGreaterThanOrEqual(4.5);

    for (const file of invertedSurfaceFiles) {
      const source = readWebFile(file);
      expect(
        source,
        `${file} should not use low-contrast text-info on inverted ink surfaces.`,
      ).not.toContain("text-info");
      expect(source).toContain("surface-inverted");
    }
  });

  it("keeps counsel-facing risk badges static rather than pulsing", () => {
    const riskBadge = readWebFile("src/components/shared/risk-badge.tsx");

    expect(riskBadge).not.toContain("animate-pulse");
    expect(riskBadge).toContain("ring-current/10");
  });

  it("keeps themeable app surfaces on token-adaptive mark variants", () => {
    const appSourceFiles = [
      "src/app/(dashboard)/admin/page.tsx",
      "src/app/(dashboard)/admin/analytics/page.tsx",
      "src/app/(dashboard)/analyses/new/page.tsx",
      "src/app/(dashboard)/capabilities/page.tsx",
      "src/app/(dashboard)/config/page.tsx",
      "src/app/(dashboard)/settings/loading.tsx",
      "src/components/admin-analytics/status-state.tsx",
      "src/components/admin-dashboard/helpers.tsx",
      "src/components/analysis-detail/analysis-header.tsx",
      "src/components/analyses-page/analyses-page-header.tsx",
      "src/components/batch/batch-page-header.tsx",
      "src/components/billing/billing-header.tsx",
      "src/components/compounds/compounds-page-header.tsx",
      "src/components/dashboard/page-header.tsx",
      "src/components/help/page-header.tsx",
      "src/components/layout/topbar.tsx",
      "src/components/monitors/page-header.tsx",
      "src/components/patents-page/patents-page-header.tsx",
      "src/components/report-page/report-page-header.tsx",
      "src/components/reviews/review-queue-page.tsx",
      "src/components/settings/settings-page-header.tsx",
      "src/components/settings/notifications/notification-settings-page.tsx",
    ];

    for (const file of appSourceFiles) {
      const text = readWebFile(file);
      expect(
        text,
        `${file} should use the token-adaptive mark, not a fixed onLight variant.`,
      ).not.toContain('variant="onLight"');
      expect(
        text,
        `${file} should use the token-adaptive mark, not a fixed onDark variant.`,
      ).not.toContain('variant="onDark"');
    }
  });

  it("keeps high-traffic app headers on the shared Praviar mark frame", () => {
    const headerSourceFiles = [
      "src/app/(dashboard)/admin/page.tsx",
      "src/app/(dashboard)/admin/analytics/page.tsx",
      "src/app/(dashboard)/analyses/new/page.tsx",
      "src/app/(dashboard)/capabilities/page.tsx",
      "src/app/(dashboard)/config/page.tsx",
      "src/components/admin-analytics/status-state.tsx",
      "src/components/admin-dashboard/helpers.tsx",
      "src/components/analysis-detail/analysis-header.tsx",
      "src/components/analyses-page/analyses-page-header.tsx",
      "src/components/batch/batch-page-header.tsx",
      "src/components/billing/billing-header.tsx",
      "src/components/compounds/compounds-page-header.tsx",
      "src/components/dashboard/page-header.tsx",
      "src/components/help/page-header.tsx",
      "src/components/monitors/page-header.tsx",
      "src/components/patents-page/patents-page-header.tsx",
      "src/components/report-page/report-page-header.tsx",
      "src/components/reviews/review-queue-page.tsx",
      "src/components/settings/settings-page-header.tsx",
      "src/components/settings/notifications/notification-settings-page.tsx",
    ];

    for (const file of headerSourceFiles) {
      const text = readWebFile(file);

      expect(
        text,
        `${file} should import the shared mark frame or shared app surface header`,
      ).toMatch(/PraviarMarkFrame|AppSurfaceHeader/u);
      expect(
        text,
        `${file} should not render a raw page-header PraviarMark wrapper`,
      ).not.toMatch(/<PraviarMark(?:\s|>)/u);
    }
  });

  it("keeps library headers off report-decision artwork", () => {
    const libraryHeaders = [
      "src/components/analyses-page/analyses-page-header.tsx",
      "src/components/billing/billing-header.tsx",
      "src/components/compounds/compounds-page-header.tsx",
      "src/components/patents-page/patents-page-header.tsx",
    ];

    for (const file of libraryHeaders) {
      const text = readWebFile(file);

      expect(
        text,
        `${file} should use the app surface header instead of report artwork`,
      ).toContain("AppSurfaceHeader");
      expect(
        text,
        `${file} should reserve report-decision field styling for report surfaces`,
      ).not.toContain("praviar-report-decision-field");
    }
  });

  it("keeps non-report operational states off report-decision artwork", () => {
    const operationalStateFiles = [
      "src/components/shared/route-loading-frame.tsx",
      "src/components/shared/operational-status-frame.tsx",
      "src/components/shared/empty-state.tsx",
      "src/components/admin-analytics/status-state.tsx",
      "src/components/admin-dashboard/helpers.tsx",
    ];

    for (const file of operationalStateFiles) {
      const text = readWebFile(file);

      expect(text, `${file} should use the operational app field`).toContain(
        "praviar-operational-field",
      );
      expect(
        text,
        `${file} should reserve report-decision artwork for report surfaces`,
      ).not.toContain("praviar-report-decision-field");
    }
  });

  it("uses the app evidence field for premium app chrome", () => {
    const css = readWebFile("src/app/globals.css");
    const dashboardHeader = readWebFile(
      "src/components/dashboard/page-header.tsx",
    );
    const appSurfaceHeader = readWebFile(
      "src/components/shared/app-surface-header.tsx",
    );
    const appField = css.match(/\.praviar-app-field\s*\{[\s\S]*?\}\s*/u)?.[0];
    const dashboardCommandDeck = css.match(
      /\.praviar-dashboard-command-deck\s*\{[\s\S]*?\}\s*/u,
    )?.[0];
    const commandDeckArt = css.match(
      /\.praviar-command-deck-art\s*\{[\s\S]*?\}\s*/u,
    )?.[0];

    expect(appField, "Missing .praviar-app-field block").toBeTypeOf("string");
    expect(appField).toContain("/brand/visuals/praviar-app-evidence-field.svg");
    expect(appField).not.toContain(
      "/brand/visuals/praviar-report-evidence-paper.svg",
    );
    expect(dashboardHeader).toContain(
      'data-praviar-dashboard-command-deck="app-evidence"',
    );
    expect(dashboardHeader).toContain("AppSurfaceHeader");
    expect(dashboardHeader).toContain('chrome="dashboard"');
    expect(dashboardHeader).toContain(
      'dataTestId="dashboard-app-surface-header"',
    );
    expect(dashboardHeader).toContain('markSize="lg"');
    expect(dashboardHeader).toContain("lg:w-auto");
    expect(dashboardHeader).toContain('aria-hidden="true"');
    expect(dashboardHeader).toContain("pointer-events-none");
    expect(dashboardHeader).toContain("opacity-45");
    expect(dashboardHeader).not.toContain("<PraviarMarkFrame");
    expect(dashboardHeader).not.toContain("WorkspaceSignal");
    expect(appSurfaceHeader).toContain("praviar-dashboard-command-deck");
    expect(
      dashboardCommandDeck,
      "Missing dashboard command deck field",
    ).toBeTypeOf("string");
    expect(dashboardCommandDeck).toContain(
      "/brand/visuals/praviar-app-evidence-field.svg",
    );
    expect(dashboardCommandDeck).toContain(
      "/brand/visuals/praviar-dossier-thread.svg",
    );
    expect(dashboardCommandDeck).not.toContain(
      "/brand/visuals/praviar-report-decision-workspace.png",
    );
    expect(
      commandDeckArt,
      "Missing dashboard command deck art block",
    ).toBeTypeOf("string");
    expect(commandDeckArt).toContain(
      "/brand/visuals/praviar-app-evidence-field.svg",
    );
    expect(commandDeckArt).toContain(
      "/brand/visuals/praviar-dossier-thread.svg",
    );
    expect(commandDeckArt).not.toContain(
      "/brand/visuals/praviar-report-decision-workspace.png",
    );
    expect(dashboardCommandDeck).not.toMatch(/\.(?:png|jpe?g|webp)/iu);
    expect(commandDeckArt).not.toMatch(/\.(?:png|jpe?g|webp)/iu);
    expect(css).not.toContain(".light .praviar-app-field");
  });

  it("keeps utility app headers on the shared control-plane visual system", () => {
    const globals = readWebFile("src/app/globals.css");
    const appSurfaceHeader = readWebFile(
      "src/components/shared/app-surface-header.tsx",
    );
    const configGovernance = readWebFile(
      "src/components/config/config-workspace-status.tsx",
    );
    const helpSectionNav = readWebFile("src/components/help/section-nav.tsx");
    const settingsGovernance = readWebFile(
      "src/components/settings/settings-governance-rail.tsx",
    );
    const embeddedEmptyStateFiles = [
      "src/components/admin-dashboard/audit-logs-tab.tsx",
      "src/components/admin-dashboard/organizations-tab.tsx",
      "src/components/admin-dashboard/users-tab-table.tsx",
      "src/components/settings/api-keys-table.tsx",
    ];
    const utilityHeaderSources = [
      "src/app/(dashboard)/admin/page.tsx",
      "src/app/(dashboard)/config/page.tsx",
      "src/components/help/page-header.tsx",
      "src/components/reviews/review-queue-page.tsx",
      "src/components/settings/settings-page-header.tsx",
    ];
    const compactUtilityHeaderSources = [
      "src/app/(dashboard)/admin/page.tsx",
      "src/app/(dashboard)/config/page.tsx",
      "src/components/settings/settings-page-header.tsx",
    ];

    expect(globals).toContain(".praviar-control-plane-header");
    expect(globals).toContain("/brand/visuals/praviar-app-evidence-field.svg");
    expect(appSurfaceHeader).toContain("PraviarMarkFrame");
    expect(appSurfaceHeader).toContain("data-praviar-app-surface-header");
    expect(appSurfaceHeader).toContain("data-praviar-app-surface-density");
    expect(appSurfaceHeader).toContain('mobileDensity = "default"');
    expect(appSurfaceHeader).toContain("min-[420px]:grid-cols-3");
    expect(appSurfaceHeader).toContain("praviar-control-plane-header");
    expect(appSurfaceHeader).toContain("<h1");
    expect(appSurfaceHeader).not.toMatch(/<PraviarMark(?:\s|>)/u);
    expect(appSurfaceHeader).toContain("border-success/25 bg-success/10");
    expect(appSurfaceHeader).toContain("border-warning/25 bg-warning/10");
    expect(helpSectionNav).toContain("sticky top-16");
    expect(configGovernance).toContain("PATENT_SOURCES.length");
    expect(configGovernance).toContain("lg:self-start");
    expect(settingsGovernance).toContain("lg:self-start");

    for (const file of embeddedEmptyStateFiles) {
      const source = readWebFile(file);

      expect(
        source,
        `${file} should use the flat embedded empty-state surface inside cards`,
      ).toContain('surface="embedded"');
    }

    for (const file of utilityHeaderSources) {
      const source = readWebFile(file);

      expect(source, `${file} should use the shared app header`).toContain(
        "AppSurfaceHeader",
      );
      expect(
        source,
        `${file} should not render a bespoke utility-page h1 outside the shared header`,
      ).not.toMatch(/<h1/u);
    }

    for (const file of compactUtilityHeaderSources) {
      const source = readWebFile(file);

      expect(
        source,
        `${file} should opt into compact mobile rhythm for first-viewport utility work`,
      ).toContain('mobileDensity="compact"');
    }
  });

  it("keeps the report workspace quiet and generated-art free", () => {
    const css = readWebFile("src/app/globals.css");
    const reportPage = readWebFile(
      "src/app/(dashboard)/analyses/[id]/report/page.tsx",
    );
    const reportLoading = readWebFile(
      "src/app/(dashboard)/analyses/[id]/report/loading.tsx",
    );
    const reportWorkspaceLoading = readWebFile(
      "src/components/report-loading/report-workspace-loading.tsx",
    );
    const dashboardLoading = readWebFile(
      "src/app/(dashboard)/dashboard/loading.tsx",
    );
    const reportStatus = readWebFile(
      "src/components/report-page/report-status-state.tsx",
    );
    const reportTabs = readWebFile(
      "src/components/report-page/report-page-tabs.tsx",
    );
    const mobileCommandBar = readWebFile(
      "src/components/report-page/mobile-report-command-bar.tsx",
    );
    const analysisStates = readWebFile(
      "src/components/analysis-detail/analysis-states.tsx",
    );
    const appSurfaceHeader = readWebFile(
      "src/components/shared/app-surface-header.tsx",
    );
    const workspace = css.match(
      /\.praviar-report-workspace\s*\{[\s\S]*?\}\s*/u,
    )?.[0];
    const workspaceBackdrop = css.match(
      /\.praviar-report-workspace::before\s*\{[\s\S]*?\}\s*/u,
    )?.[0];

    expect(workspace, "Missing .praviar-report-workspace block").toBeTypeOf(
      "string",
    );
    expect(workspace).toContain("isolation: isolate;");
    expect(
      workspaceBackdrop,
      "Missing .praviar-report-workspace::before block",
    ).toBeTypeOf("string");
    expect(workspaceBackdrop).not.toContain("url(");
    expect(workspaceBackdrop).not.toContain("image-set(");
    expect(reportPage).toContain("praviar-report-workspace");
    expect(reportPage).toContain("max-w-[90rem]");
    expect(reportPage).not.toContain(
      "pb-[calc(10.25rem+env(safe-area-inset-bottom))]",
    );
    expect(reportPage).not.toContain("max-w-5xl");
    expect(mobileCommandBar).toContain("MOBILE_COMMAND_SURFACE_OFFSET");
    expect(mobileCommandBar).toContain("MOBILE_COMMAND_GEOMETRY");
    expect(mobileCommandBar).toContain(
      "top-[var(--praviar-mobile-command-rail-top)]",
    );
    expect(mobileCommandBar).toContain(
      "var(--praviar-mobile-command-rail-height)",
    );
    expect(mobileCommandBar).toContain(
      "praviar-mobile-command-surface no-print sticky",
    );
    expect(mobileCommandBar).not.toContain(
      "praviar-mobile-command-surface no-print fixed inset-x-0 bottom-0",
    );
    expect(reportLoading).toContain("ReportWorkspaceLoading");
    expect(reportWorkspaceLoading).toContain(
      "praviar-report-workspace mx-auto w-full min-w-0 max-w-[90rem]",
    );
    expect(reportWorkspaceLoading).toContain(
      "data-praviar-report-loading-identity",
    );
    expect(reportWorkspaceLoading).toContain(
      "data-praviar-report-loading-section-rail",
    );
    expect(reportWorkspaceLoading).toContain(
      "data-praviar-report-loading-command-rail",
    );
    expect(reportWorkspaceLoading).toContain(
      "data-praviar-report-loading-decision-brief",
    );
    expect(reportWorkspaceLoading).toContain(
      "data-praviar-report-loading-readiness-disclosure",
    );
    expect(reportWorkspaceLoading).not.toContain("ReportLoadingReviewerRail");
    expect(reportWorkspaceLoading).not.toContain("RouteLoadingFrame");
    expect(reportWorkspaceLoading).not.toContain("max-w-4xl flex-1");
    expect(dashboardLoading).toContain("data-praviar-dashboard-loading-header");
    expect(dashboardLoading).toContain(
      "dashboard-loading-executive-decision-brief",
    );
    expect(dashboardLoading).toContain("dashboard-loading-legal-workload");
    expect(dashboardLoading).not.toContain("RouteLoadingFrame");
    expect(dashboardLoading).not.toContain("KPI Cards");
    expect(dashboardLoading).not.toContain("Recent analyses table card");
    expect(reportStatus).toContain("max-w-[90rem]");
    expect(reportTabs).toContain('aria-label="Report section"');
    expect(reportTabs).toContain("data-praviar-report-tabs-stable-shell");
    expect(reportTabs).toContain("grid-cols-5");
    expect(reportTabs).not.toContain("[scrollbar-width:none]");
    expect(reportTabs).not.toContain(
      "data-praviar-report-tabs-scroll-affordance",
    );
    expect(analysisStates).toContain("max-w-[90rem]");
    expect(appSurfaceHeader).toContain("repeat(auto-fit,minmax(10.5rem,1fr))");
    expect(appSurfaceHeader).toContain("dashboard:");
    expect(appSurfaceHeader).toContain("praviar-dashboard-command-deck");
    expect(appSurfaceHeader).not.toContain("sm:grid-cols-3");
    expect(appSurfaceHeader).not.toContain("tracking-tight");
    expect(appSurfaceHeader).not.toContain("truncate text-sm font-semibold");
    expect(appSurfaceHeader).toContain("[overflow-wrap:anywhere]");
  });

  it("keeps the sample report command bar compact and available before the report body", () => {
    const globals = readWebFile("src/app/globals.css");
    const sampleReportPage = readWebFile(
      "src/app/(marketing)/sample-reports/[slug]/page.tsx",
    );
    const sampleCommandBar = readWebFile(
      "src/components/marketing/sample-report-mobile-command-bar.tsx",
    );

    expect(sampleReportPage).not.toContain(
      "pb-[calc(8rem+env(safe-area-inset-bottom))]",
    );
    expect(sampleCommandBar).toContain(
      'data-state={sectionsOpen ? "expanded" : "collapsed"}',
    );
    expect(sampleCommandBar).toContain(
      "praviar-mobile-command-surface no-print sticky top-14",
    );
    expect(sampleCommandBar).not.toContain(
      "praviar-mobile-command-surface no-print fixed inset-x-0 bottom-0",
    );
    expect(sampleCommandBar).toContain("min-h-11");
    expect(sampleCommandBar).not.toContain("min-h-14");
    expect(sampleCommandBar).not.toContain("env(safe-area-inset-bottom)");
    expect(globals).not.toContain(
      ".praviar-marketing-shell:has([data-sample-report-mobile-command-bar]) footer",
    );
    expect(
      sampleReportPage.indexOf("<SampleReportMobileCommandBar"),
    ).toBeLessThan(sampleReportPage.indexOf('id="sample-verdict-packet"'));
    expect(
      sampleReportPage.indexOf("<SampleReportMobileCommandBar"),
    ).toBeLessThan(sampleReportPage.indexOf('className="praviar-section-band'));
  });

  it("keeps active marketing badges and adaptive review on premium accent tokens", () => {
    const premiumMarketingSources = [
      "src/app/(marketing)/compare/adaptive-agentic/page.tsx",
      "src/components/landing/pipeline-comparison-config.ts",
      "src/components/landing/pipeline-comparison-execution-panel.tsx",
      "src/components/landing/pipeline-comparison-metrics.tsx",
      "src/components/landing/pipeline-comparison-traces.ts",
      "src/components/marketing/home-page.tsx",
      "src/components/marketing/home-page-hero-shell.tsx",
      "src/components/marketing/sample-report-card.tsx",
    ]
      .map(readWebFile)
      .join("\n");

    expect(premiumMarketingSources).toContain("from-warning via-brand-primary");
    expect(premiumMarketingSources).toContain("bg-warning/12");
    expect(premiumMarketingSources).toContain("var(--brand-ink, #0B1F24) 10%");

    for (const legacyAccent of [
      "stain-permanganate",
      "from-stain-permanganate",
      "via-stain-permanganate",
      "to-stain-eosin",
      "#0B1F24 10%",
      "black 10%",
      "Adaptive Agentic",
      "Agentic Escalation",
      "Single-Pass Stage",
      "single-pass stage",
      "agentic review",
      "agentic investigation",
    ]) {
      expect(premiumMarketingSources).not.toContain(legacyAccent);
    }
  });

  it("keeps unused orbital animation metaphors out of active CSS", () => {
    const globals = readWebFile("src/app/globals.css");

    expect(globals).not.toContain("@keyframes orbital");
    expect(globals).not.toContain(".orbital-indicator");
  });

  it("keeps onboarding spotlight overlays on Ink-derived alpha", () => {
    const spotlight = readWebFile(
      "src/components/shared/onboarding-tooltip-spotlight.tsx",
    );

    expect(spotlight).toContain("color-mix(in srgb, var(--brand-ink) 60%");
    expect(spotlight).toContain("color-mix(in srgb, var(--brand-ink) 50%");
    expect(spotlight).not.toContain("rgba(11,31,36");
    expect(spotlight).not.toContain("rgba(0,0,0");
    expect(spotlight).not.toContain("rgba(0, 0, 0");
  });

  it("keeps print/export artifacts on the premium palette", () => {
    const printSources = [
      "src/components/report/print-report-header.tsx",
      "src/components/report/print-report-footer.tsx",
      "src/components/report/print-report-styles.ts",
    ]
      .map(readWebFile)
      .join("\n");

    for (const brandColor of [
      "#0B1F24",
      "#0E6F68",
      "#B87333",
      "#D7ECE5",
      "#F6F4EF",
    ]) {
      expect(printSources).toContain(brandColor);
    }

    for (const legacyPrintColor of [
      "#333",
      "#666",
      "#999",
      "#ddd",
      "#f5f5f5",
      "#f9f9f9",
      "#244349",
      "#5E7271",
      "#C8D8D2",
      "#E7F0EB",
      "#EEF4F0",
      "231, 240, 235",
      "background: white",
      "color: black",
    ]) {
      expect(printSources).not.toContain(legacyPrintColor);
    }
  });
});
