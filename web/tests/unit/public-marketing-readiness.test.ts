import { readdirSync, readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";
import {
  PUBLIC_CONTACT_ACTION,
  PUBLIC_MARKETING_READINESS,
  PUBLIC_PRIMARY_ACTION,
} from "@/marketing/public-readiness";

const MARKETING_SOURCE_ROOTS = [
  "src/app/(marketing)",
  "src/components/marketing",
  "src/marketing/content.ts",
] as const;

function collectSourceFiles(path: string): string[] {
  if (/\.(?:ts|tsx)$/.test(path)) return [path];

  return readdirSync(path, { withFileTypes: true }).flatMap((entry) =>
    collectSourceFiles(join(path, entry.name)),
  );
}

describe("public marketing readiness", () => {
  it("keeps the informational launch fail-closed", () => {
    expect(PUBLIC_MARKETING_READINESS).toBe("informational_only");
    expect(PUBLIC_PRIMARY_ACTION.href).toBe(
      "/sample-reports/example-molecule-alpha",
    );
    expect(PUBLIC_CONTACT_ACTION.href).toBe(
      "https://github.com/Peter-McCann-Strain/chemical-patent-analysis",
    );

    const sourceFiles = MARKETING_SOURCE_ROOTS.flatMap(collectSourceFiles);
    const forbiddenTransactionalPaths =
      /["'`](?:\/sign-up|\/billing)(?:[?/#"'`])/;
    const forbiddenTransactionalCta =
      />\s*(?:Buy|Create a free workspace|Continue with)/i;

    for (const sourceFile of sourceFiles) {
      const source = readFileSync(sourceFile, "utf8");

      expect(source, sourceFile).not.toMatch(forbiddenTransactionalPaths);
      expect(source, sourceFile).not.toMatch(forbiddenTransactionalCta);
    }
  });
});
