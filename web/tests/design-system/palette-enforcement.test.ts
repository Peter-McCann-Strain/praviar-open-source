/**
 * Brand-system enforcement: no raw Tailwind palette utility classes in
 * customer-facing UI. Praviar's brand contract routes all color through the
 * Forensic Teal + Clinical Copper CSS vars exposed as Tailwind 4 theme tokens.
 * Runtime surfaces should use brand tokens and the semantic
 * success/warning/info/error scale, with no legacy stain/gold alias layer.
 *
 * Round-1 + Round-2 reviews each found leaks in components that the marketing
 * grep didn't reach (functional-group-badges.tsx, loading-mark.tsx). This
 * test prevents a Round-3 regression by scanning every .tsx/.ts source file
 * under web/src/ for any `(text|bg|border)-<tailwind-color>-<n>` token.
 *
 * If a chemistry/data-viz use-case legitimately needs a non-stain hue,
 * promote it into a CSS variable in globals.css (e.g. --chart-* tokens) and
 * use the var, instead of an ad-hoc Tailwind utility.
 */

import { readFileSync, readdirSync, statSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";

const SRC = join(__dirname, "..", "..", "src");

const FORBIDDEN_PALETTES = [
  "red",
  "blue",
  "green",
  "violet",
  "purple",
  "fuchsia",
  "pink",
  "rose",
  "indigo",
  "cyan",
  "sky",
  "teal",
  "emerald",
  "lime",
  "orange",
  "yellow",
  "amber",
  "slate",
  "gray",
  "neutral",
  "stone",
  "zinc",
];

const PALETTE_RE = new RegExp(
  `\\b(text|bg|border-[trblxy]|border|ring|from|to|via|outline|divide|fill|stroke|placeholder|accent|caret|decoration|shadow)-(${FORBIDDEN_PALETTES.join("|")})-(\\d{2,3})\\b`,
  "g",
);

const FORBIDDEN_RAW_HEX = [
  "#F87171",
  "#FCA5A5",
  "#FBBF24",
  "#FCD34D",
  "#34D399",
  "#6EE7B7",
  "#93C5FD",
  "#475569",
  "#0C0F1A",
  "#E2E8F0",
  "#94A3B8",
  "#64748B",
];

const FORBIDDEN_RAW_RGB_TUPLES = [
  "79,70,229",
  "79, 70, 229",
  "15,23,42",
  "15, 23, 42",
  "99,102,241",
  "99, 102, 241",
];

// Files that legitimately need raw palettes (escape hatch — keep this short).
// chart-* tokens in globals.css are intentional categorical data-viz hues.
const ALLOWED_FILES = new Set<string>([]);

function walk(dir: string): string[] {
  const out: string[] = [];
  for (const entry of readdirSync(dir)) {
    const full = join(dir, entry);
    const stat = statSync(full);
    if (stat.isDirectory()) {
      out.push(...walk(full));
    } else if (/\.(tsx?|jsx?|css)$/.test(entry)) {
      out.push(full);
    }
  }
  return out;
}

describe("Design system: premium palette enforcement", () => {
  it("no raw Tailwind palette utility class anywhere in web/src/", () => {
    const offenders: { file: string; line: number; match: string }[] = [];
    for (const file of walk(SRC)) {
      if (ALLOWED_FILES.has(file)) continue;
      const text = readFileSync(file, "utf-8");
      const lines = text.split("\n");
      lines.forEach((line, i) => {
        const trimmed = line.trim();
        if (
          trimmed.startsWith("//") ||
          trimmed.startsWith("*") ||
          trimmed.startsWith("/*")
        ) {
          return;
        }
        const matches = line.matchAll(PALETTE_RE);
        for (const m of matches) {
          offenders.push({
            file: file.replace(SRC, "web/src"),
            line: i + 1,
            match: m[0],
          });
        }
      });
    }
    expect(
      offenders,
      `Raw Tailwind palette utilities leaked outside the premium brand system:
${offenders.map((o) => `  ${o.file}:${o.line}  ${o.match}`).join("\n")}

Use premium brand tokens instead:
  text-brand-primary  bg-brand-primary/15  border-brand-primary/25
or semantic tokens:
  text-success  bg-warning/15  border-info/25
or hoist the color into a CSS variable in globals.css.`,
    ).toEqual([]);
  });

  it("runtime source avoids legacy stain utility aliases", () => {
    const sourceFiles = walk(SRC);
    const offenders: { file: string; line: number; match: string }[] = [];

    for (const file of sourceFiles) {
      const text = readFileSync(file, "utf-8");
      const lines = text.split("\n");
      lines.forEach((line, i) => {
        const match = line.match(/(?:stain-|gold-leaf|var\(--stain)/);
        if (match) {
          offenders.push({
            file: file.replace(SRC, "web/src"),
            line: i + 1,
            match: match[0],
          });
        }
      });
    }

    expect(
      offenders,
      `Legacy stain aliases leaked into runtime source:
${offenders.map((o) => `  ${o.file}:${o.line}  ${o.match}`).join("\n")}

Use brand tokens (brand-primary, brand-secondary) or semantic tokens
(success, warning, info, error) for runtime UI.`,
    ).toEqual([]);
  });

  it("reserves bright Clinical Copper for accents instead of normal text", () => {
    const sourceFiles = walk(SRC);
    const offenders: { file: string; line: number; match: string }[] = [];
    const accentAsTextRegex =
      /(?:text-brand-secondary|text-\[var\(--brand-secondary\)\]|color:\s*["']?(?:#B87333|var\(--brand-secondary\)))/i;

    for (const file of sourceFiles) {
      const text = readFileSync(file, "utf-8");
      const lines = text.split("\n");
      lines.forEach((line, i) => {
        const match = line.match(accentAsTextRegex);
        if (match) {
          offenders.push({
            file: file.replace(SRC, "web/src"),
            line: i + 1,
            match: match[0],
          });
        }
      });
    }

    expect(
      offenders,
      `Bright Clinical Copper is an accent, not a normal text color:
${offenders.map((o) => `  ${o.file}:${o.line}  ${o.match}`).join("\n")}

Use text-warning, text-warning-emphasis, or var(--brand-secondary-dim)
for readable copper text on Paper/Mint surfaces.`,
    ).toEqual([]);
  });

  it("no legacy raw risk or slate hex colors in customer-facing source", () => {
    const offenders: { file: string; line: number; match: string }[] = [];
    for (const file of walk(SRC)) {
      if (ALLOWED_FILES.has(file)) continue;
      const text = readFileSync(file, "utf-8");
      const lines = text.split("\n");
      lines.forEach((line, i) => {
        for (const hex of FORBIDDEN_RAW_HEX) {
          if (line.toLowerCase().includes(hex.toLowerCase())) {
            offenders.push({
              file: file.replace(SRC, "web/src"),
              line: i + 1,
              match: hex,
            });
          }
        }
      });
    }

    expect(
      offenders,
      `Legacy raw palette hexes leaked outside the premium brand system:
${offenders.map((o) => `  ${o.file}:${o.line}  ${o.match}`).join("\n")}

Use CSS variables such as var(--risk-high), var(--text-secondary), or
Forensic Teal + Clinical Copper tokens from globals.css.`,
    ).toEqual([]);
  });

  it("no legacy indigo or slate RGB tuples in customer-facing source", () => {
    const offenders: { file: string; line: number; match: string }[] = [];
    for (const file of walk(SRC)) {
      if (ALLOWED_FILES.has(file)) continue;
      const text = readFileSync(file, "utf-8");
      const lines = text.split("\n");
      lines.forEach((line, i) => {
        for (const tuple of FORBIDDEN_RAW_RGB_TUPLES) {
          if (line.includes(tuple)) {
            offenders.push({
              file: file.replace(SRC, "web/src"),
              line: i + 1,
              match: tuple,
            });
          }
        }
      });
    }

    expect(
      offenders,
      `Legacy raw RGB tuples leaked outside the premium brand system:
${offenders.map((o) => `  ${o.file}:${o.line}  ${o.match}`).join("\n")}

Use var(--brand-primary-rgb), color-mix with brand tokens, or named CSS
variables in globals.css instead of ad-hoc indigo/slate RGB values.`,
    ).toEqual([]);
  });
});
