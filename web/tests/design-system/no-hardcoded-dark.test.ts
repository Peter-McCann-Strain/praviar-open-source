import { describe, it, expect } from "vitest";
import fs from "fs";
import path from "path";

/**
 * Tests that source files do not use hardcoded dark-theme-only patterns.
 * The design system uses semantic CSS variables instead.
 *
 * Scans all .ts/.tsx files in src/, excluding _archive/.
 */

// Collect all TypeScript source files from a directory, recursively
function collectSourceFiles(dir: string): string[] {
  const files: string[] = [];
  if (!fs.existsSync(dir)) return files;

  const entries = fs.readdirSync(dir, { withFileTypes: true });
  for (const entry of entries) {
    const fullPath = path.join(dir, entry.name);

    // Skip archived dead code
    if (fullPath.includes("_archive")) continue;

    if (entry.isDirectory()) {
      files.push(...collectSourceFiles(fullPath));
    } else if (/\.(ts|tsx)$/.test(entry.name)) {
      files.push(fullPath);
    }
  }
  return files;
}

const srcDir = path.resolve(__dirname, "../../src");
const allFiles = collectSourceFiles(srcDir);

interface Violation {
  file: string;
  line: number;
  content: string;
}

function scanFiles(
  files: string[],
  pattern: RegExp,
  _label: string,
): Violation[] {
  const violations: Violation[] = [];
  for (const filePath of files) {
    const content = fs.readFileSync(filePath, "utf-8");
    const lines = content.split("\n");
    for (let i = 0; i < lines.length; i++) {
      if (pattern.test(lines[i])) {
        violations.push({
          file: path.relative(srcDir, filePath),
          line: i + 1,
          content: lines[i].trim(),
        });
      }
    }
  }
  return violations;
}

function formatViolations(violations: Violation[]): string {
  return violations
    .map((v) => `  ${v.file}:${v.line} — ${v.content}`)
    .join("\n");
}

describe("Design System: No Hardcoded Dark-Mode Patterns", () => {
  it("scans a non-empty set of files", () => {
    expect(
      allFiles.length,
      "Expected to find .tsx files to scan in src/components/ and src/app/",
    ).toBeGreaterThan(0);
  });

  it("no files use bg-white/[0. pattern (hardcoded semi-transparent white backgrounds)", () => {
    // This pattern was replaced by --surface-hover, --surface-active, etc.
    const violations = scanFiles(allFiles, /bg-white\/\[0\./, "bg-white/[0.");
    expect(
      violations,
      `Found bg-white/[0. in component files (use --surface-hover/active/muted instead):\n${formatViolations(violations)}`,
    ).toEqual([]);
  });

  it("no files use border-white/[0. pattern (hardcoded semi-transparent white borders)", () => {
    // This pattern was replaced by --border-default, --border-subtle, --border-emphasis
    const violations = scanFiles(
      allFiles,
      /border-white\/\[0\./,
      "border-white/[0.",
    );
    expect(
      violations,
      `Found border-white/[0. in component files (use --border-default/subtle/emphasis instead):\n${formatViolations(violations)}`,
    ).toEqual([]);
  });

  it("no files use hardcoded #1e293b or #334155 (old skeleton colors)", () => {
    // These hex values were the old hardcoded skeleton colors before the design system.
    // They should now come from --skeleton-base and --skeleton-highlight variables.
    const violations = scanFiles(
      allFiles,
      /#1e293b|#334155/i,
      "hardcoded skeleton hex colors",
    );
    expect(
      violations,
      `Found hardcoded skeleton hex colors in component files (use var(--skeleton-base)/var(--skeleton-highlight) instead):\n${formatViolations(violations)}`,
    ).toEqual([]);
  });

  it("no files use shadow-black/ pattern (hardcoded black shadows)", () => {
    // Shadows should use the --shadow-sm/md/lg variables from the design system.
    const violations = scanFiles(allFiles, /shadow-black\//, "shadow-black/");
    expect(
      violations,
      `Found shadow-black/ in component files (use var(--shadow-sm/md/lg) instead):\n${formatViolations(violations)}`,
    ).toEqual([]);
  });

  it("no source files reintroduce a second dark theme mechanism", () => {
    const violations = scanFiles(
      allFiles,
      /\bdark:|className=["'`{][^"'`}\n]*\bdark\b|classList\.(add|toggle)\(["'`]dark|data-theme=["'`]dark|prefers-color-scheme|setTheme\(/,
      "dark theme mechanism",
    );
    expect(
      violations,
      `Found a dark/system theme mechanism in source files:\n${formatViolations(violations)}`,
    ).toEqual([]);
  });
});
