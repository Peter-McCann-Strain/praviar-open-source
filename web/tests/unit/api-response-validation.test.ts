import { describe, expect, it, vi } from "vitest";
import { z } from "zod/v4";
import {
  ApiResponseValidationError,
  externalReportGrantActivityResponseSchema,
  externalReportGrantCreatedResponseSchema,
  externalReportGrantListResponseSchema,
  externalReportGrantRevokedResponseSchema,
  ftoReportResponseSchema,
  validateApiResponse,
} from "@/lib/validators";

describe("validateApiResponse", () => {
  function reportWithClaimElement() {
    return {
      report_id: "report-claim-contract",
      generated_at: "2026-07-12T11:00:00Z",
      compound: { name: "Aspirin", canonical_smiles: "CC(=O)O" },
      risk_summary: { overall_risk: "unclear", blocking_patents_count: 0 },
      patent_analyses: [
        {
          patent_id: "US123",
          risk_level: "high",
          risk_summary: "Test",
          claims_analyzed: [
            {
              claim_number: 1,
              claim_type: "independent",
              overall_status: "met",
              elements: [
                {
                  element_number: 1,
                  element_text: "a limitation",
                  status: "met",
                  reasoning: "Mapped",
                },
              ],
            },
          ],
        },
      ],
      claim_source_span_map: {
        entries: [],
        spans: {},
        unsupported_customer_visible_claim_count: 0,
        needs_review_count: 0,
      },
    };
  }

  it("logs only issue codes and paths when malformed values contain secrets", () => {
    const consoleSpy = vi.spyOn(console, "error").mockImplementation(() => {});
    const schema = z.object({
      compound: z.literal("expected"),
      reviewer_email: z.email(),
      authorization: z.literal("none"),
      database_url: z.url(),
    });
    const payload = {
      compound: "CC(=O)Oc1ccccc1C(=O)O",
      reviewer_email: "counsel-secret@example.test",
      authorization: "Bearer private-token",
      database_url: "postgres://private-host/praviar",
    };

    expect(() =>
      validateApiResponse(schema, payload, "/api/v1/reports/:id"),
    ).toThrow(ApiResponseValidationError);

    const output = JSON.stringify(consoleSpy.mock.calls);
    expect(output).toContain("API response contract validation failed");
    expect(output).toContain("compound");
    expect(output).not.toContain(payload.compound);
    expect(output).not.toContain(payload.reviewer_email);
    expect(output).not.toContain(payload.authorization);
    expect(output).not.toContain(payload.database_url);
  });

  it("preserves verified claim-text provenance fields", () => {
    const provenance = {
      span_id: "span-verified-1",
      source_type: "verified_claim_text" as const,
      patent_id: "US123",
      claim_number: 1,
      excerpt: "Verified claim text.",
      source_document_id: "US123",
      source_name: "USPTO Patent Center",
      source_text_sha256: "a".repeat(64),
      source_retrieved_at: "2026-07-12T10:00:00Z",
      source_artifact_locator: `https://search.patentsview.org/api/v1/patent/?patent_id=US123#sha256=${"a".repeat(64)}`,
      collector_identity: "uspto_claim_collector",
      collector_version: "2026.07",
      provenance_cassette_sha256: "b".repeat(64),
    };
    const report = {
      report_id: "report-1",
      generated_at: "2026-07-12T11:00:00Z",
      compound: { name: "Aspirin", canonical_smiles: "CC(=O)O" },
      risk_summary: { overall_risk: "unclear", blocking_patents_count: 0 },
      patent_analyses: [],
      claim_source_span_map: {
        generated_from: "verified_sources",
        entries: [],
        spans: { "span-verified-1": provenance },
        unsupported_customer_visible_claim_count: 0,
        needs_review_count: 0,
      },
    };

    const parsed = validateApiResponse(
      ftoReportResponseSchema,
      report,
      "/api/v1/reports/:id",
    );

    expect(parsed.claim_source_span_map.spans["span-verified-1"]).toEqual(
      provenance,
    );
  });

  it("rejects verified claim text without a complete provenance receipt", () => {
    const report = reportWithClaimElement();
    report.claim_source_span_map.spans = {
      incomplete: {
        span_id: "incomplete",
        source_type: "verified_claim_text",
        patent_id: "US123",
        claim_number: 1,
        element_number: 1,
        excerpt: "a limitation",
      },
    };

    const parsed = ftoReportResponseSchema.safeParse(report);
    expect(parsed.success).toBe(false);
    if (!parsed.success) {
      expect(parsed.error.issues.map((issue) => issue.path.join("."))).toEqual(
        expect.arrayContaining([
          "claim_source_span_map.spans.incomplete.source_document_id",
          "claim_source_span_map.spans.incomplete.source_text_sha256",
          "claim_source_span_map.spans.incomplete.source_retrieved_at",
        ]),
      );
    }
  });

  it("rejects malformed nested claim and doctrine-of-equivalents data", () => {
    const report = reportWithClaimElement();
    report.patent_analyses[0].claims_analyzed[0].elements[0].status =
      "guaranteed_infringement";
    Object.assign(report, {
      doe_assessments: [
        {
          patent_id: "US123",
          claim_number: 1,
          element_number: 1,
          confidence: 4,
        },
      ],
    });

    expect(ftoReportResponseSchema.safeParse(report).success).toBe(false);
  });

  it("rejects duplicate claim-element, DoE, and assertion identities", () => {
    const report = reportWithClaimElement();
    report.patent_analyses[0].claims_analyzed[0].elements.push({
      ...report.patent_analyses[0].claims_analyzed[0].elements[0],
    });
    Object.assign(report, {
      doe_assessments: [
        { patent_id: "US123", claim_number: 1, element_number: 1 },
        { patent_id: "US123", claim_number: 1, element_number: 1 },
      ],
    });
    report.claim_source_span_map.entries = [
      {
        assertion_id: "duplicate",
        report_section: "claim_element_analysis",
        assertion_text: "One",
        source_span_ids: [],
        support_status: "supported",
        customer_visible: true,
        review_required: false,
      },
      {
        assertion_id: "duplicate",
        report_section: "claim_element_analysis",
        assertion_text: "Two",
        source_span_ids: [],
        support_status: "supported",
        customer_visible: true,
        review_required: false,
      },
    ];

    const parsed = ftoReportResponseSchema.safeParse(report);
    expect(parsed.success).toBe(false);
    if (!parsed.success) {
      const paths = parsed.error.issues.map((issue) => issue.path.join("."));
      expect(paths).toEqual(
        expect.arrayContaining([
          "patent_analyses.0.claims_analyzed.0.elements.1.element_number",
          "doe_assessments.1.element_number",
          "claim_source_span_map.entries.1.assertion_id",
        ]),
      );
    }
  });
});

describe("external report grant response contracts", () => {
  const grant = {
    id: "123e4567-e89b-42d3-a456-426614174000",
    recipient_email: "counsel@example.com",
    recipient_domain: "example.com",
    invitation_sent_at: "2026-07-25T10:00:00Z",
    expires_at: "2026-08-01T10:00:00Z",
    revoked_at: null,
    max_views: 25,
    view_count: 2,
    download_allowed: false,
    max_downloads: 0,
    download_count: 0,
    last_accessed_at: "2026-07-25T10:05:00Z",
    status: "active",
  };

  it("accepts authoritative list, create, activity, and revoke payloads", () => {
    expect(
      externalReportGrantListResponseSchema.safeParse({ items: [grant] })
        .success,
    ).toBe(true);
    expect(
      externalReportGrantCreatedResponseSchema.safeParse({
        ...grant,
        share_token: "T".repeat(43),
        invitation_status: "provider_accepted",
        replayed: false,
      }).success,
    ).toBe(true);
    expect(
      externalReportGrantActivityResponseSchema.safeParse({
        items: [
          {
            id: "123e4567-e89b-42d3-a456-426614174001",
            event: "report_viewed",
            occurred_at: "2026-07-25T10:05:00Z",
            view_number: 2,
          },
        ],
      }).success,
    ).toBe(true);
    expect(
      externalReportGrantRevokedResponseSchema.safeParse({
        status: "revoked",
      }).success,
    ).toBe(true);
  });

  it.each([
    ["missing items", {}],
    ["non-array items", { items: grant }],
    ["invalid grant UUID", { items: [{ ...grant, id: "grant-1" }] }],
    [
      "invalid recipient email",
      { items: [{ ...grant, recipient_email: "not-an-email" }] },
    ],
    ["unknown grant status", { items: [{ ...grant, status: "maybe_active" }] }],
    [
      "timezone-free expiry",
      { items: [{ ...grant, expires_at: "2026-08-01T10:00:00" }] },
    ],
    ["fractional view count", { items: [{ ...grant, view_count: 1.5 }] }],
    ["view count above limit", { items: [{ ...grant, view_count: 26 }] }],
    [
      "download permission drift",
      { items: [{ ...grant, download_allowed: true }] },
    ],
    ["nonzero download limit", { items: [{ ...grant, max_downloads: 1 }] }],
  ])("rejects %s", (_label, payload) => {
    expect(
      externalReportGrantListResponseSchema.safeParse(payload).success,
    ).toBe(false);
  });

  it.each([
    ["short token", "short"],
    ["path-like token", "../recipient/token"],
    ["oversized token", "T".repeat(65)],
  ])("rejects a %s", (_label, shareToken) => {
    expect(
      externalReportGrantCreatedResponseSchema.safeParse({
        ...grant,
        share_token: shareToken,
        invitation_status: "provider_accepted",
        replayed: false,
      }).success,
    ).toBe(false);
  });

  it("rejects a missing token for a newly accepted invitation", () => {
    expect(
      externalReportGrantCreatedResponseSchema.safeParse({
        ...grant,
        share_token: null,
        invitation_status: "provider_accepted",
        replayed: false,
      }).success,
    ).toBe(false);
  });

  it.each([
    [
      "unknown event",
      {
        id: "123e4567-e89b-42d3-a456-426614174001",
        event: "recipient_probably_viewed",
        occurred_at: "2026-07-25T10:05:00Z",
        view_number: null,
      },
    ],
    [
      "zero view number",
      {
        id: "123e4567-e89b-42d3-a456-426614174001",
        event: "report_viewed",
        occurred_at: "2026-07-25T10:05:00Z",
        view_number: 0,
      },
    ],
    [
      "invalid event time",
      {
        id: "123e4567-e89b-42d3-a456-426614174001",
        event: "report_viewed",
        occurred_at: "yesterday",
        view_number: 1,
      },
    ],
  ])("rejects activity with %s", (_label, item) => {
    expect(
      externalReportGrantActivityResponseSchema.safeParse({ items: [item] })
        .success,
    ).toBe(false);
  });

  it("requires an exact revoke acknowledgement", () => {
    expect(
      externalReportGrantRevokedResponseSchema.safeParse({ status: "ok" })
        .success,
    ).toBe(false);
  });

  it("does not log recipient or token values on validation failure", () => {
    const consoleSpy = vi.spyOn(console, "error").mockImplementation(() => {});
    const recipient = "secret-counsel@example.test";
    const token = "../private-share-token";

    expect(() =>
      validateApiResponse(
        externalReportGrantCreatedResponseSchema,
        {
          ...grant,
          recipient_email: recipient,
          share_token: token,
          invitation_status: "provider_accepted",
          replayed: false,
        },
        "/reports/:analysis_id/share",
      ),
    ).toThrow(ApiResponseValidationError);

    const output = JSON.stringify(consoleSpy.mock.calls);
    expect(output).not.toContain(recipient);
    expect(output).not.toContain(token);
    consoleSpy.mockRestore();
  });
});
