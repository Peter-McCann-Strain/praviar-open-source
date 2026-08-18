import { describe, expect, it } from "vitest";
import fs from "fs";
import path from "path";

const srcDir = path.resolve(__dirname, "../../src");
const globalsPath = path.join(srcDir, "app/globals.css");

const SOURCE_EXTENSIONS = new Set([".css", ".ts", ".tsx"]);
const ALLOWED_EXTERNAL_PREFIXES = ["--radix-"];
const GLOBAL_DEFINITION_SELECTORS = [
  ":root",
  ".light",
  "@theme inline",
  "html",
];

interface SourceFile {
  absolutePath: string;
  relativePath: string;
}

interface VariableReference {
  name: string;
  file: string;
  line: number;
  content: string;
}

function collectSourceFiles(dir: string): SourceFile[] {
  const files: SourceFile[] = [];
  const entries = fs.readdirSync(dir, { withFileTypes: true });

  for (const entry of entries) {
    const absolutePath = path.join(dir, entry.name);

    if (absolutePath.includes("_archive")) continue;

    if (entry.isDirectory()) {
      files.push(...collectSourceFiles(absolutePath));
      continue;
    }

    if (SOURCE_EXTENSIONS.has(path.extname(entry.name))) {
      files.push({
        absolutePath,
        relativePath: path.relative(srcDir, absolutePath),
      });
    }
  }

  return files;
}

function collectVariablesFromText(content: string): Set<string> {
  const definitions = new Set<string>();
  const definitionRegex = /["']?(--[A-Za-z0-9_-]+)["']?\s*:/g;

  for (const match of content.matchAll(definitionRegex)) {
    definitions.add(match[1]);
  }

  return definitions;
}

function extractBlocks(css: string, selector: string): string[] {
  const blocks: string[] = [];
  let searchFrom = 0;

  while (searchFrom < css.length) {
    const selectorStart = css.indexOf(selector, searchFrom);
    if (selectorStart === -1) break;

    const blockStart = css.indexOf("{", selectorStart);
    if (blockStart === -1) break;

    let depth = 0;
    for (let i = blockStart; i < css.length; i++) {
      if (css[i] === "{") depth++;
      if (css[i] === "}") depth--;

      if (depth === 0) {
        blocks.push(css.slice(blockStart + 1, i));
        searchFrom = i + 1;
        break;
      }
    }
  }

  return blocks;
}

function collectGlobalDefinedVariables(globalsCss: string): Set<string> {
  const definitions = new Set<string>();

  for (const selector of GLOBAL_DEFINITION_SELECTORS) {
    for (const block of extractBlocks(globalsCss, selector)) {
      for (const name of collectVariablesFromText(block)) {
        definitions.add(name);
      }
    }
  }

  return definitions;
}

function collectFileDefinedVariables(
  files: SourceFile[],
): Map<string, Set<string>> {
  const definitions = new Map<string, Set<string>>();

  for (const file of files) {
    const content = fs.readFileSync(file.absolutePath, "utf-8");
    definitions.set(file.relativePath, collectVariablesFromText(content));
  }

  return definitions;
}

function collectVariableReferences(files: SourceFile[]): VariableReference[] {
  const references: VariableReference[] = [];
  const varReferenceRegex = /var\(\s*(--[A-Za-z0-9_-]+)/g;

  for (const file of files) {
    const lines = fs.readFileSync(file.absolutePath, "utf-8").split("\n");

    lines.forEach((line, index) => {
      for (const match of line.matchAll(varReferenceRegex)) {
        references.push({
          name: match[1],
          file: file.relativePath,
          line: index + 1,
          content: line.trim(),
        });
      }
    });
  }

  return references;
}

function isAllowedExternalVariable(name: string): boolean {
  return ALLOWED_EXTERNAL_PREFIXES.some((prefix) => name.startsWith(prefix));
}

function isDefinedForReference(
  reference: VariableReference,
  globalDefinitions: Set<string>,
  fileDefinitions: Map<string, Set<string>>,
): boolean {
  return (
    globalDefinitions.has(reference.name) ||
    fileDefinitions.get(reference.file)?.has(reference.name) === true ||
    isAllowedExternalVariable(reference.name)
  );
}

function formatReferences(references: VariableReference[]): string {
  return references
    .map(
      (reference) =>
        `  ${reference.file}:${reference.line} ${reference.name} -- ${reference.content}`,
    )
    .join("\n");
}

describe("Design System: CSS Variable References", () => {
  const sourceFiles = collectSourceFiles(srcDir);
  const globalsCss = fs.readFileSync(globalsPath, "utf-8");
  const globalDefinitions = collectGlobalDefinedVariables(globalsCss);
  const fileDefinitions = collectFileDefinedVariables(sourceFiles);
  const references = collectVariableReferences(sourceFiles);

  it("scans source files and CSS variable references", () => {
    expect(sourceFiles.length).toBeGreaterThan(0);
    expect(references.length).toBeGreaterThan(0);
  });

  it("all app-owned CSS variable references resolve to app definitions", () => {
    const missingDefinitions = references.filter(
      (reference) =>
        !isDefinedForReference(reference, globalDefinitions, fileDefinitions),
    );

    expect(
      missingDefinitions,
      `Found CSS variable references without app definitions:\n${formatReferences(missingDefinitions)}`,
    ).toEqual([]);
  });
});
