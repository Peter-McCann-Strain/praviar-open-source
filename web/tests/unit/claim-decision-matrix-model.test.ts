import { describe, expect, it } from "vitest";

import {
  buildClaimDecisionMatrixModel,
  filterClaimDecisionRows,
} from "@/components/report/claim-decision-matrix-model";
import type {
  ReviewerDecision,
  ReviewerDecisionListResponse,
} from "@/hooks/use-reviewer-decisions";
import type { FTOReport } from "@praviar/shared-types";

const VERIFIED_RECEIPT = {
  source_document_id: "US123B2",
  source_name: "USPTO Patent Center",
  source_text_sha256: "a".repeat(64),
  source_retrieved_at: "2026-07-12T09:00:00.000Z",
  source_artifact_locator: `https://search.patentsview.org/api/v1/patent/?patent_id=US123B2#sha256=${"a".repeat(64)}`,
  collector_identity: "runtime.uspto_claims",
  collector_version: "2026.07",
  provenance_cassette_sha256: "b".repeat(64),
};

function decision(
  id: string,
  reviewerUserId: string,
  value: ReviewerDecision["decision"],
): ReviewerDecision {
  return {
    id,
    finding_type: "claim_element",
    finding_ref: "mapping-1",
    decision: value,
    note: "",
    edited_text: "",
    reviewer_user_id: reviewerUserId,
    reviewer_name: `Reviewer ${reviewerUserId}`,
    reviewer_email: `${reviewerUserId}@example.test`,
    created_at: "2026-07-12T10:00:00.000Z",
    updated_at: `2026-07-12T10:0${id === "decision-1" ? "0" : "1"}:00.000Z`,
  };
}

function report(): FTOReport {
  return {
    report_id: "report-1",
    generated_at: "2026-07-12T12:00:00.000Z",
    praviar_pipeline_version: "1.0.0",
    patent_analyses: [
      {
        patent_id: "US123B2",
        jurisdiction: "US",
        title: "Exact claim program",
        risk_level: "high",
        risk_summary: "Test",
        expiry_date: "2034-02-01",
        claims_analyzed: [
          {
            claim_number: 1,
            claim_type: "independent",
            elements: [
              {
                element_number: 1,
                element_text: "a verified compound limitation",
                status: "met",
                reasoning: "Mapped",
                confidence: 0.9,
                evidence: "Evidence",
              },
              {
                element_number: 2,
                element_text: "a missing limitation",
                status: "not_met",
                reasoning: "Not mapped",
                confidence: 0.8,
                evidence: "Evidence",
              },
            ],
            overall_status: "partially_met",
            overall_confidence: 0.85,
            reasoning: "Test",
          },
        ],
      },
    ],
    patent_details: {
      US123B2: {
        patent_id: "US123B2",
        title: "Exact member",
        abstract: "",
        claims_text: "",
        sources: [],
        confidence_score: 0.9,
        filing_date: "2020-01-01",
        expiry_date: "2034-02-01",
        assignees: [],
        inventors: [],
        cpc_codes: [],
        legal_status: "active",
        match_type: "exact",
        jurisdiction: "US",
        family_id: "fam-1",
        is_granted: true,
        legal_events: [],
      },
    },
    claim_source_span_map: {
      entries: [
        {
          assertion_id: "source-1",
          patent_id: "US123B2",
          claim_number: 1,
          element_number: 1,
          report_section: "claim_source",
          assertion_text: "Verified source",
          source_span_ids: [
            "structural-first",
            "verified-second",
            "wrong-tuple",
          ],
          support_status: "supported",
          customer_visible: true,
        },
        {
          assertion_id: "mapping-1",
          patent_id: "US123B2",
          claim_number: 1,
          element_number: 1,
          report_section: "claim_element_analysis",
          assertion_text: "Mapping needs review",
          source_span_ids: ["reasoning-context"],
          support_status: "needs_review",
          customer_visible: true,
          review_required: true,
        },
      ],
      spans: {
        "structural-first": {
          span_id: "structural-first",
          source_type: "claim_text",
          patent_id: "US123B2",
          claim_number: 1,
          element_number: 1,
          excerpt: "Unverified structural text",
        },
        "verified-second": {
          ...VERIFIED_RECEIPT,
          span_id: "verified-second",
          source_type: "verified_claim_text",
          patent_id: "US123B2",
          claim_number: 1,
          element_number: 1,
          excerpt: "Verified exact text",
        },
        "reasoning-context": {
          span_id: "reasoning-context",
          source_type: "claim_reasoning",
          patent_id: "US123B2",
          claim_number: 1,
          element_number: 1,
          excerpt: "Analysis context",
        },
        "wrong-tuple": {
          ...VERIFIED_RECEIPT,
          span_id: "wrong-tuple",
          source_type: "verified_claim_text",
          patent_id: "US123B2",
          claim_number: 1,
          element_number: 2,
          excerpt: "Wrong element",
        },
      },
    },
    doe_assessments: [
      {
        patent_id: "US123B2",
        claim_number: 1,
        element_number: 2,
        overall_equivalent: true,
        confidence: 0.72,
      },
    ],
  } as FTOReport;
}

function reviewerDecisions(): ReviewerDecisionListResponse {
  return {
    items: [
      decision("decision-1", "reviewer-a", "accept"),
      decision("decision-2", "reviewer-b", "reject"),
    ],
    counts: { accept: 1, reject: 1, edit: 0 },
  };
}

describe("claim decision matrix model", () => {
  it("keeps all exact-tuple purposes and separates verified evidence from context", () => {
    const model = buildClaimDecisionMatrixModel({
      report: report(),
      reviewerDecisions: reviewerDecisions(),
    });
    const row = model.rows.find((candidate) => candidate.elementNumber === 1);

    expect(row).toMatchObject({
      mappingSupport: "needs_review",
      reviewTargetAssertionId: "mapping-1",
      needsAction: true,
    });
    expect(row?.verifiedSpans.map((span) => span.span_id)).toEqual([
      "verified-second",
    ]);
    expect(row?.contextSpans.map((span) => span.span_id)).toEqual([
      "reasoning-context",
      "structural-first",
    ]);
    expect(row?.verifiedSpans).not.toEqual(
      expect.arrayContaining([
        expect.objectContaining({ span_id: "wrong-tuple" }),
      ]),
    );
  });

  it("aggregates reviewer disagreement without retaining reviewer identity", () => {
    const model = buildClaimDecisionMatrixModel({
      report: report(),
      reviewerDecisions: reviewerDecisions(),
    });
    const summary = model.rows.find(
      (candidate) => candidate.elementNumber === 1,
    )?.reviewSummary;

    expect(summary).toMatchObject({
      counts: { accept: 1, reject: 1, edit: 0 },
      label: "Conflict · 1 accept / 1 reject",
      reviewCount: 2,
      state: "conflict",
    });
    expect(JSON.stringify(summary)).not.toContain("example.test");
    expect(JSON.stringify(summary)).not.toContain("reviewer-a");
  });

  it("sorts missing verified source first and filters deterministically", () => {
    const model = buildClaimDecisionMatrixModel({ report: report() });

    expect(model.rows.map((row) => row.elementNumber)).toEqual([2, 1]);
    expect(filterClaimDecisionRows(model.rows, "needs_action")).toHaveLength(2);
    expect(
      filterClaimDecisionRows(model.rows, "not_met").map(
        (row) => row.elementNumber,
      ),
    ).toEqual([2]);
    expect(model.rows[0]).toMatchObject({
      doeStatus: "equivalent",
      jurisdiction: "US",
      legalStatus: "active",
      familyId: "fam-1",
    });
  });

  it("lets a completed review leave the action queue", () => {
    const resolvedDecisions: ReviewerDecisionListResponse = {
      items: [decision("decision-1", "reviewer-a", "accept")],
      counts: { accept: 1, reject: 0, edit: 0 },
    };
    const model = buildClaimDecisionMatrixModel({
      report: report(),
      reviewerDecisions: resolvedDecisions,
    });
    const resolvedRow = model.rows.find((row) => row.elementNumber === 1);

    expect(resolvedRow?.reviewSummary.state).toBe("accepted");
    expect(resolvedRow?.needsAction).toBe(false);
    expect(filterClaimDecisionRows(model.rows, "needs_action")).not.toContain(
      resolvedRow,
    );
  });

  it("does not trust a verified span reachable only from a needs-review assertion", () => {
    const unsafeReport = report();
    const entries = unsafeReport.claim_source_span_map?.entries ?? [];
    const sourceEntry = entries.find(
      (entry) => entry.assertion_id === "source-1",
    );
    const mappingEntry = entries.find(
      (entry) => entry.assertion_id === "mapping-1",
    );
    if (!sourceEntry || !mappingEntry) throw new Error("Fixture is incomplete");
    sourceEntry.source_span_ids = ["structural-first"];
    mappingEntry.source_span_ids = ["verified-second", "reasoning-context"];

    const model = buildClaimDecisionMatrixModel({ report: unsafeReport });
    const row = model.rows.find((candidate) => candidate.elementNumber === 1);

    expect(row?.verifiedSpans).toEqual([]);
    expect(row?.needsAction).toBe(true);
  });

  it("fails closed when claim element tuples are not unique", () => {
    const duplicateReport = report();
    const elements =
      duplicateReport.patent_analyses[0]?.claims_analyzed?.[0]?.elements;
    if (!elements?.[0]) throw new Error("Fixture is incomplete");
    elements.push({ ...elements[0] });

    expect(() =>
      buildClaimDecisionMatrixModel({ report: duplicateReport }),
    ).toThrow("Duplicate claim element tuple");
  });

  it("labels a failed decision ledger as unavailable instead of pending", () => {
    const model = buildClaimDecisionMatrixModel({
      decisionsUnavailable: true,
      report: report(),
    });
    const row = model.rows.find((candidate) => candidate.elementNumber === 1);

    expect(row?.reviewSummary).toMatchObject({
      label: "Decision ledger unavailable",
      state: "unknown",
    });
  });

  it("keeps missing mapping rationale and hash-unbound receipts actionable", () => {
    const incompleteReport = report();
    const element =
      incompleteReport.patent_analyses[0]?.claims_analyzed?.[0]?.elements?.[0];
    const span =
      incompleteReport.claim_source_span_map?.spans?.["verified-second"];
    if (!element || !span) throw new Error("Fixture is incomplete");
    element.reasoning = "";
    span.source_artifact_locator =
      "https://search.patentsview.org/api/v1/patent/?patent_id=US123B2#sha256=wrong";

    const model = buildClaimDecisionMatrixModel({
      report: incompleteReport,
      reviewerDecisions: {
        items: [decision("decision-1", "reviewer-a", "accept")],
        counts: { accept: 1, reject: 0, edit: 0 },
      },
    });
    const row = model.rows.find((candidate) => candidate.elementNumber === 1);

    expect(row?.mappingReasoning).toBe("");
    expect(row?.verifiedSpans).toEqual([]);
    expect(row?.needsAction).toBe(true);
  });
});
