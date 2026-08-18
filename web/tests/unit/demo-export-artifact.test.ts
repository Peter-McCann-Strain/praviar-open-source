import { describe, expect, it } from "vitest";
import {
  buildDemoExportDescriptor,
  createDemoExportArtifact,
  createDemoReportPayload,
  DEMO_EXPORT_FORMATS,
  parseDemoExportDescriptor,
  sha256Hex,
} from "@/lib/demo-export-artifact";

describe("demo export artifacts", () => {
  it("round-trips only exact reviewed descriptors", () => {
    const descriptor = buildDemoExportDescriptor("attorney", "pdf");
    expect(descriptor).toBe("praviar-demo-export:v1:attorney:pdf");
    expect(parseDemoExportDescriptor(descriptor)).toEqual({
      audience: "attorney",
      format: "pdf",
    });
    expect(
      parseDemoExportDescriptor("praviar-demo-export:v1:attorney:pdf "),
    ).toBeNull();
    expect(
      parseDemoExportDescriptor("praviar-demo-export:v1:attorney:html"),
    ).toBeNull();
  });

  it.each(DEMO_EXPORT_FORMATS)(
    "builds a deterministic, non-empty %s artifact with the right extension",
    (format) => {
      const first = createDemoExportArtifact("attorney", format);
      const second = createDemoExportArtifact("attorney", format);
      expect(first.fileName).toBe(`praviar-demo-attorney.${format}`);
      expect(first.mediaType).not.toBe("application/octet-stream");
      expect(first.bytes.length).toBeGreaterThan(100);
      expect(first.bytes).toEqual(second.bytes);
    },
  );

  it("produces a PDF payload instead of HTML renamed as PDF", () => {
    const artifact = createDemoExportArtifact("executive", "pdf");
    const text = new TextDecoder().decode(artifact.bytes);
    expect(text.startsWith("%PDF-1.7")).toBe(true);
    expect(text).toContain("Praviar demonstration export");
    expect(text).toContain("Synthetic demonstration data only");
    expect(text.endsWith("%%EOF\n")).toBe(true);
  });

  it.each([
    ["docx", "word/document.xml"],
    ["pptx", "ppt/slides/slide1.xml"],
    ["xlsx", "xl/worksheets/sheet1.xml"],
  ] as const)("produces an actual OOXML %s package", (format, requiredPart) => {
    const artifact = createDemoExportArtifact("full", format);
    const packageText = new TextDecoder().decode(artifact.bytes);
    expect(Array.from(artifact.bytes.slice(0, 4))).toEqual([80, 75, 3, 4]);
    expect(packageText).toContain("[Content_Types].xml");
    expect(packageText).toContain(requiredPart);
    expect(packageText).toContain("Synthetic demonstration data only");
  });

  it("produces parseable CSV and JSON disclosures", () => {
    const csv = new TextDecoder().decode(
      createDemoExportArtifact("scientist", "csv").bytes,
    );
    const json = JSON.parse(
      new TextDecoder().decode(
        createDemoExportArtifact("investor", "json").bytes,
      ),
    ) as { disclaimer: string };
    expect(csv).toContain("Synthetic demonstration data only");
    expect(json.disclaimer).toContain("Synthetic demonstration data only");
  });

  it("hashes the exact artifact and report payload deterministically", async () => {
    const artifact = createDemoExportArtifact("attorney", "pdf");
    const artifactHash = await sha256Hex(artifact.bytes);
    const payloadHash = await sha256Hex(createDemoReportPayload("attorney"));
    expect(artifactHash).toMatch(/^[0-9a-f]{64}$/u);
    expect(payloadHash).toMatch(/^[0-9a-f]{64}$/u);
    expect(artifactHash).not.toBe(payloadHash);
  });
});
