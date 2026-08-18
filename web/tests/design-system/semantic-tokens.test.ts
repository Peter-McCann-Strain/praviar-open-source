import { describe, expect, it } from "vitest";
import fs from "fs";
import path from "path";

/**
 * Tests that the Praviar design system exposes one premium light color system:
 * :root is the resilient fallback, and .light mirrors it for SSR/hydration.
 */

const globalsPath = path.resolve(__dirname, "../../src/app/globals.css");
const css = fs.readFileSync(globalsPath, "utf-8");

/**
 * Extract CSS property/custom property definitions from a block of CSS.
 * Returns a Map of property name -> value.
 */
function extractVariables(blockContent: string): Map<string, string> {
  const vars = new Map<string, string>();
  const regex = /([\w-]+)\s*:\s*([^;]+);/g;
  let match: RegExpExecArray | null;
  while ((match = regex.exec(blockContent)) !== null) {
    vars.set(match[1], match[2].trim());
  }
  return vars;
}

/**
 * Extract the content between the first { and its matching }.
 * Handles nested braces.
 */
function extractBlock(source: string, selector: string): string {
  const idx = source.indexOf(selector);
  if (idx === -1) return "";
  const start = source.indexOf("{", idx);
  if (start === -1) return "";
  let depth = 0;
  let end = start;
  for (let i = start; i < source.length; i++) {
    if (source[i] === "{") depth++;
    if (source[i] === "}") depth--;
    if (depth === 0) {
      end = i;
      break;
    }
  }
  return source.slice(start + 1, end);
}

const rootBlock = extractBlock(css, ":root");
const lightBlock = extractBlock(css, ".light");
const rootVars = extractVariables(rootBlock);
const lightVars = extractVariables(lightBlock);

const isAlias = (_name: string, value: string) => value.startsWith("var(");

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

function tokenHex(vars: Map<string, string>, name: string) {
  const value = vars.get(name);
  expect(value, `${name} should be defined`).toMatch(/^#[0-9a-f]{6}$/iu);
  return value!;
}

const semanticRootVars = new Map<string, string>();
for (const [name, value] of rootVars) {
  if (isAlias(name, value)) continue;
  semanticRootVars.set(name, value);
}

describe("Design System: Semantic Tokens", () => {
  describe("premium light palette root", () => {
    it("has a :root fallback and .light mirror", () => {
      expect(rootBlock.length).toBeGreaterThan(0);
      expect(lightBlock.length).toBeGreaterThan(0);
    });

    it("sets both root and .light to light color-scheme", () => {
      expect(rootVars.get("color-scheme")).toBe("light");
      expect(lightVars.get("color-scheme")).toBe("light");
    });

    it("does not expose a Tailwind dark variant or dark color-scheme", () => {
      expect(css).not.toContain("@custom-variant dark");
      expect(css).not.toContain("color-scheme: dark");
      expect(css).not.toContain("end @layer base — dark theme");
      expect(css).not.toMatch(/(^|[{}]\s*)\.dark\b/u);
      expect(css).not.toMatch(/\[data-theme=["']dark["']\]/u);
      expect(css).not.toContain("prefers-color-scheme");
    });
  });

  describe("root and .light stay aligned", () => {
    const missingInLight: string[] = [];
    const mismatchedInLight: string[] = [];

    for (const [name, rootValue] of semanticRootVars) {
      const lightValue = lightVars.get(name);
      if (!lightValue) {
        missingInLight.push(name);
      } else if (lightValue !== rootValue) {
        mismatchedInLight.push(
          `${name}: root=${rootValue}; light=${lightValue}`,
        );
      }
    }

    it("all semantic root variables are defined in .light", () => {
      expect(
        missingInLight,
        `These variables are defined in :root but missing from .light:\n  ${missingInLight.join("\n  ")}`,
      ).toEqual([]);
    });

    it("semantic .light values mirror :root values", () => {
      expect(
        mismatchedInLight,
        `These variables drift between :root and .light:\n  ${mismatchedInLight.join("\n  ")}`,
      ).toEqual([]);
    });
  });

  describe("required design system variables exist", () => {
    const requiredVars = [
      "--brand-ink",
      "--brand-teal",
      "--brand-mint",
      "--brand-copper",
      "--brand-paper",
      "--brand-soft-mint",
      "--bg-base",
      "--bg-surface",
      "--bg-elevated",
      "--text-primary",
      "--text-secondary",
      "--border-default",
      "--surface-hover",
      "--surface-active",
      "--skeleton-base",
      "--chart-grid",
    ];

    for (const varName of requiredVars) {
      it(`${varName} is defined in :root`, () => {
        expect(rootVars.has(varName), `${varName} is missing from :root`).toBe(
          true,
        );
      });

      it(`${varName} is defined in .light`, () => {
        expect(
          lightVars.has(varName),
          `${varName} is missing from .light`,
        ).toBe(true);
      });
    }
  });

  describe("premium light surfaces", () => {
    it("uses Paper and Soft Mint instead of generic white for major surfaces", () => {
      for (const vars of [rootVars, lightVars]) {
        expect(vars.get("--bg-base")).toBe("#f6f4ef");
        expect(vars.get("--bg-surface")).toBe("#f6f4ef");
        expect(vars.get("--bg-overlay")).toBe("#f6f4ef");
        expect(vars.get("--bg-elevated")).toBe("#d7ece5");
        expect(vars.get("--bg-sidebar")).toBe("#d7ece5");
        expect(vars.get("--surface-glass")).toContain("var(--brand-paper)");
        expect(vars.get("--surface-glass")).not.toContain("255, 255, 255");
      }
    });

    it("keeps base premium panels on Paper and Soft Mint washes", () => {
      const premiumPanelSelectors = [
        ".praviar-app-field",
        ".praviar-auth-field",
        ".praviar-auth-visual",
        ".praviar-surface-premium",
        ".praviar-report-decision-field",
      ];

      for (const selector of premiumPanelSelectors) {
        const block = extractBlock(css, selector);
        expect(block, `${selector} should exist`).not.toBe("");
        expect(
          block,
          `${selector} should avoid generic white overlays`,
        ).not.toContain("rgba(255, 255, 255");
        expect(
          block,
          `${selector} should use branded Paper/Mint overlays`,
        ).toMatch(/rgba\(246, 244, 239|rgba\(215, 236, 229/);
      }
    });

    it("does not rely on .light repair rules for premium panels", () => {
      for (const selector of [
        ".light .praviar-app-field",
        ".light .praviar-auth-field",
        ".light .praviar-auth-visual",
        ".light .praviar-surface-premium",
        ".light .praviar-report-decision-field",
        ".light .solid-btn-hover",
      ]) {
        expect(css).not.toContain(selector);
      }
    });

    it("keeps hero and mobile fields on the selected Soft Mint wash", () => {
      expect(css).toContain("rgba(215, 236, 229");
      expect(css).not.toContain("rgba(231, 240, 235");
    });

    it("keeps premium foreground roles above WCAG AA contrast on branded surfaces", () => {
      for (const vars of [rootVars, lightVars]) {
        const paper = tokenHex(vars, "--brand-paper");
        const softMint = tokenHex(vars, "--brand-soft-mint");
        const ink = tokenHex(vars, "--brand-ink");
        const teal = tokenHex(vars, "--brand-teal");
        const tealDepth = tokenHex(vars, "--brand-primary-dim");
        const copperDepth = tokenHex(vars, "--brand-secondary-dim");
        const error = tokenHex(vars, "--semantic-error");
        const errorDepth = tokenHex(vars, "--semantic-error-emphasis");

        for (const [label, foreground, background] of [
          ["Ink body text on Paper", ink, paper],
          ["Ink body text on Soft Mint", ink, softMint],
          ["Forensic Teal links/actions on Paper", teal, paper],
          ["Forensic Teal links/actions on Soft Mint", teal, softMint],
          ["Clinical Copper text uses depth on Paper", copperDepth, paper],
          ["Error text on Paper", error, paper],
          ["Error emphasis text on Paper", errorDepth, paper],
          ["Paper text on Teal action", paper, teal],
          ["Paper text on Teal depth action", paper, tealDepth],
        ] as const) {
          expect(
            contrastRatio(foreground, background),
            `${label} should be at least 4.5:1 for normal text`,
          ).toBeGreaterThanOrEqual(4.5);
        }
      }
    });

    it("keeps focus and non-text accents above the 3:1 contrast floor", () => {
      for (const vars of [rootVars, lightVars]) {
        const paper = tokenHex(vars, "--brand-paper");
        const softMint = tokenHex(vars, "--brand-soft-mint");
        const focus = tokenHex(vars, "--focus-ring");
        const teal = tokenHex(vars, "--brand-teal");
        const tealDepth = tokenHex(vars, "--brand-primary-dim");

        for (const [label, foreground, background] of [
          ["Focus ring on Paper", focus, paper],
          ["Focus ring on Soft Mint", focus, softMint],
          ["Teal UI stroke on Paper", teal, paper],
          ["Teal depth UI stroke on Soft Mint", tealDepth, softMint],
        ] as const) {
          expect(
            contrastRatio(foreground, background),
            `${label} should be at least 3:1 for non-text UI contrast`,
          ).toBeGreaterThanOrEqual(3);
        }
      }
    });
  });
});
