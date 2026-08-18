import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";

const WEB_ROOT = resolve(import.meta.dirname, "../..");

function readSource(path: string) {
  return readFileSync(resolve(WEB_ROOT, path), "utf8");
}

describe("Design system: buyer-critical touch target policy", () => {
  it("keeps the shared dialog close action at least 44px square", () => {
    const source = readSource("src/components/ui/dialog.tsx");
    const close = source.match(
      /<DialogPrimitive\.Close[\s\S]*?<\/DialogPrimitive\.Close>/u,
    )?.[0];

    expect(close).toBeDefined();
    expect(close).toContain("h-11 w-11");
    expect(close).not.toContain("h-8 w-8");
  });

  it("keeps monitor creation and destructive confirmation actions at least 44px high", () => {
    const create = readSource(
      "src/components/monitors/create-monitor-form.tsx",
    );
    const table = readSource("src/components/monitors/monitors-table.tsx");

    expect(create).toMatch(
      /variant="outline"\s+size="sm"\s+className="min-h-11"[\s\S]*?>\s*Cancel/u,
    );
    expect(create).toMatch(
      /type="submit"\s+size="sm"\s+className="min-h-11"[\s\S]*?>\s*Create Monitor/u,
    );
    expect(table).toMatch(
      /variant="destructive"\s+size="sm"\s+className="min-h-11"[\s\S]*?Confirm delete monitor/u,
    );
    expect(table).toMatch(
      /variant="ghost"\s+size="sm"\s+className="min-h-11"[\s\S]*?Cancel delete monitor/u,
    );
  });

  it("keeps batch launch and report-search recovery actions at least 44px", () => {
    const batch = readSource("src/components/batch/create-batch-form.tsx");
    const search = readSource("src/components/report/report-search-bar.tsx");

    expect(batch).toMatch(
      /variant="outline"\s+size="sm"\s+className="min-h-11"[\s\S]*?>\s*Cancel/u,
    );
    expect(batch).toMatch(
      /type="submit"\s+size="sm"\s+className="min-h-11"[\s\S]*?>\s*Start Batch/u,
    );
    expect(search).toMatch(
      /className="[^"]*h-11 w-11[^"]*"[\s\S]*?aria-label="Clear search"/u,
    );
  });

  it("allows dense small controls while requiring explicit workflow overrides", () => {
    const button = readSource("src/components/ui/button.tsx");
    const select = readSource("src/components/ui/select.tsx");

    expect(button).toContain('sm: "h-8 rounded-md px-3 text-xs');
    expect(button).toContain("[@media(pointer:coarse)]:min-h-11");
    expect(button).toContain("[@media(pointer:coarse)]:min-w-11");
    expect(button).toContain("[@media(pointer:coarse)]:h-11");
    expect(button).toContain("[@media(pointer:coarse)]:w-11");
    expect(select).toContain("[@media(pointer:coarse)]:min-h-11");
  });
});
