import { readdirSync, readFileSync } from "node:fs";
import { extname, join, relative, resolve } from "node:path";
import { describe, expect, it } from "vitest";

const WEB_ROOT = resolve(import.meta.dirname, "../..");
const SOURCE_ROOT = resolve(WEB_ROOT, "src");
const SOURCE_EXTENSIONS = new Set([".ts", ".tsx"]);
const ARBITRARY_PIXEL_TEXT_SIZE =
  /\b(?:[a-z0-9-]+:)*text-\[(\d+(?:\.\d+)?)px\]/giu;

function sourceFiles(directory: string): string[] {
  return readdirSync(directory, { withFileTypes: true }).flatMap((entry) => {
    const path = join(directory, entry.name);
    if (entry.isDirectory()) {
      return sourceFiles(path);
    }
    return SOURCE_EXTENSIONS.has(extname(entry.name)) ? [path] : [];
  });
}

describe("Design system: minimum text size", () => {
  it("does not render product text below the 12px caption minimum", () => {
    const violations = sourceFiles(SOURCE_ROOT).flatMap((path) => {
      const source = readFileSync(path, "utf8");
      return [...source.matchAll(ARBITRARY_PIXEL_TEXT_SIZE)]
        .filter((match) => Number(match[1]) < 12)
        .map(
          (match) =>
            `${relative(WEB_ROOT, path)}:${source.slice(0, match.index).split("\n").length} (${match[0]})`,
        );
    });

    expect(
      violations,
      "Use text-xs or a larger design-system type token; product text must be at least 12px.",
    ).toEqual([]);
  });
});
