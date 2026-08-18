import { describe, expect, it } from "vitest";
import { classifyExportDownloadUrl } from "@/lib/export-download-url";

describe("classifyExportDownloadUrl", () => {
  it.each([
    [
      "/api/v1/exports/123e4567-e89b-42d3-a456-426614174000/download",
      {
        kind: "protected-api",
        path: "/api/v1/exports/123e4567-e89b-42d3-a456-426614174000/download",
      },
    ],
    [
      "praviar-demo-export:v1:attorney:pdf",
      {
        kind: "demo-artifact",
        audience: "attorney",
        format: "pdf",
      },
    ],
    [
      "praviar-demo-export:v1:executive:pptx",
      {
        kind: "demo-artifact",
        audience: "executive",
        format: "pptx",
      },
    ],
  ])("allows a reviewed relative download target: %s", (value, expected) => {
    expect(
      classifyExportDownloadUrl(value, { allowDemoArtifact: true }),
    ).toEqual(expected);
  });

  it("rejects demo descriptors unless the caller is explicitly in demo mode", () => {
    expect(
      classifyExportDownloadUrl("praviar-demo-export:v1:attorney:pdf"),
    ).toEqual({ kind: "invalid" });
  });

  it.each([
    "https://downloads.example.test/packet.pdf",
    "http://downloads.example.test/packet.pdf",
    "//downloads.example.test/packet.pdf",
    "javascript:alert(1)",
    "data:text/html,hostile",
    "file:///etc/passwd",
    "blob:https://praviar.io/attacker-controlled",
    "praviar-demo-export:v1:attorney:html",
    "praviar-demo-export:v1:unknown:pdf",
    "praviar-demo-export:v2:attorney:pdf",
    "praviar-demo-export:v1:attorney:pdf ",
    "/\\evil.example/packet.pdf",
    "/demo-exports/%2f%2fevil.example/packet.pdf",
    "/demo-exports/javascript%3aalert(1)",
    "/demo-exports/%2e%2e/private",
    "/demo-exports/../demo-exports/packet.pdf",
    "/demo-exports/packet.pdf#fragment",
    "/demo-exports/packet.pdf?version=1",
    "/demo-exports/nested/packet.pdf",
    "/demo-exports/packet.html",
    "/static/packet.pdf",
    "/demo-exports/report-123.pdf",
    "/static/exports/packet.docx",
    "/api/v1/exports/job-123/download",
    "/api/v1/exports/123e4567-e89b-12d3-a456-426614174000/download",
    "/api/v1/exports/123e4567-e89b-42d3-a456-426614174000/download?disposition=attachment",
    "/api/v1/exports/123e4567-e89b-42d3-a456-426614174000/download#preview",
    "/api/v1/exports/../exports/123e4567-e89b-42d3-a456-426614174000/download",
    "/api/v1/exports/%2e%2e/exports/123e4567-e89b-42d3-a456-426614174000/download",
    "/api/v2/exports/123e4567-e89b-42d3-a456-426614174000/download",
    "/api/v1/reports/123e4567-e89b-42d3-a456-426614174000/download",
    "/unreviewed/packet.pdf",
    " /demo-exports/packet.pdf",
  ])("fails closed for an unsafe or unreviewed target: %s", (value) => {
    expect(classifyExportDownloadUrl(value)).toEqual({ kind: "invalid" });
  });
});
