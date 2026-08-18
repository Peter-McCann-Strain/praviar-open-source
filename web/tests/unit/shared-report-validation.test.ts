import { describe, expect, it } from "vitest";
import {
  isSharedReportExpired,
  isSharedReportVerificationSessionExpired,
  parseSharedReportPayload,
} from "@/app/share/[token]/shared-report-validation";

const VALID_PAYLOAD = {
  compound_name: "Succinic acid",
  overall_risk: "high",
  blocking_patents_count: 2,
  total_patents_found: 2417,
  executive_summary: "Two high-risk patent families need review.",
  key_findings: ["US0000000001A1 overlaps the proposed route."],
  generated_at: "2026-04-09T11:24:00.000Z",
  share_expires_at: "2027-05-09T11:24:00.000Z",
  verified_recipient_email: "counsel@example.com",
  attributable_view_number: 1,
  verified_session_expires_at: "2026-07-13T12:30:00.000Z",
};

describe("parseSharedReportPayload", () => {
  it("accepts a governed public share payload and keeps optional provenance", () => {
    const report = parseSharedReportPayload({
      ...VALID_PAYLOAD,
      report_id: "rpt_demo_succinic_001",
      packet_version: "public-share-v1",
      source_snapshot_at: "2026-04-09T11:00:00.000Z",
      pipeline_version: "pipeline-2026.06",
      model_version: "agentic-report-2026.06",
      integrity_digest: "sha256:abc123",
      source_coverage: ["patentsview", "pubchem_sdq"],
      jurisdiction_scope: ["US", "EP"],
      key_patents: [
        {
          patent_number: "US0000000001A1",
          risk_level: "high",
          assignee: "Example Pharma",
          expiry: "2037-04-09",
          patent_url: "https://patents.google.com/patent/US0000000001A1",
          source_reference: "Google Patents",
        },
        {
          patent_number: "US0000000002A1",
          patent_url: "https://evil.example/phish",
          source_reference: "Unsafe source",
        },
        { patent_number: "" },
      ],
    });

    expect(report).toMatchObject({
      compound_name: "Succinic acid",
      overall_risk: "high",
      share_expires_at: "2027-05-09T11:24:00.000Z",
      packet_version: "public-share-v1",
      source_snapshot_at: "2026-04-09T11:00:00.000Z",
      integrity_digest: "sha256:abc123",
      key_patents: [
        {
          patent_number: "US0000000001A1",
          risk_level: "high",
          assignee: "Example Pharma",
          patent_url: "https://patents.google.com/patent/US0000000001A1",
          source_reference: "Google Patents",
        },
        {
          patent_number: "US0000000002A1",
          source_reference: "Unsafe source",
        },
      ],
    });
  });

  it("fails closed when required public artifact fields are missing", () => {
    expect(
      parseSharedReportPayload({
        ...VALID_PAYLOAD,
        compound_name: "",
      }),
    ).toBeNull();
    expect(
      parseSharedReportPayload({
        ...VALID_PAYLOAD,
        total_patents_found: -1,
      }),
    ).toBeNull();
    expect(
      parseSharedReportPayload({
        ...VALID_PAYLOAD,
        share_expires_at: undefined,
      }),
    ).toBeNull();
    expect(
      parseSharedReportPayload({
        ...VALID_PAYLOAD,
        verified_recipient_email: "",
      }),
    ).toBeNull();
    expect(
      parseSharedReportPayload({
        ...VALID_PAYLOAD,
        attributable_view_number: 0,
      }),
    ).toBeNull();
    expect(
      parseSharedReportPayload({
        ...VALID_PAYLOAD,
        verified_session_expires_at: "not-a-date",
      }),
    ).toBeNull();
  });

  it("fails closed on invalid risk and malformed dates", () => {
    expect(
      parseSharedReportPayload({
        ...VALID_PAYLOAD,
        overall_risk: "unknown",
      }),
    ).toBeNull();
    expect(
      parseSharedReportPayload({
        ...VALID_PAYLOAD,
        generated_at: "not-a-date",
      }),
    ).toBeNull();
    expect(
      parseSharedReportPayload({
        ...VALID_PAYLOAD,
        source_snapshot_at: "not-a-date",
      }),
    ).not.toHaveProperty("source_snapshot_at");
  });

  it("classifies stale public share payloads as expired", () => {
    const report = parseSharedReportPayload({
      ...VALID_PAYLOAD,
      share_expires_at: "2026-05-09T11:24:00.000Z",
    });

    expect(report).not.toBeNull();
    expect(
      isSharedReportExpired(report!, new Date("2026-07-10T00:00:00.000Z")),
    ).toBe(true);
  });

  it("keeps future public share payloads active and fails closed on invalid expiry metadata", () => {
    const report = parseSharedReportPayload(VALID_PAYLOAD);

    expect(report).not.toBeNull();
    expect(
      isSharedReportExpired(report!, new Date("2026-07-10T00:00:00.000Z")),
    ).toBe(false);
    expect(isSharedReportExpired({ share_expires_at: undefined })).toBe(true);
    expect(isSharedReportExpired({ share_expires_at: "not-a-date" })).toBe(
      true,
    );
  });

  it("fails closed when the recipient verification session has expired", () => {
    const now = new Date("2026-07-13T12:30:00.000Z");

    expect(
      isSharedReportVerificationSessionExpired(
        { verified_session_expires_at: "2026-07-13T12:29:59.999Z" },
        now,
      ),
    ).toBe(true);
    expect(
      isSharedReportVerificationSessionExpired(
        { verified_session_expires_at: "2026-07-13T12:30:00.001Z" },
        now,
      ),
    ).toBe(false);
    expect(
      isSharedReportVerificationSessionExpired(
        { verified_session_expires_at: "not-a-date" },
        now,
      ),
    ).toBe(true);
  });
});
