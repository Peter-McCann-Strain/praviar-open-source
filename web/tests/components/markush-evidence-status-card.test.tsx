import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import type { PipelineAuditTrail } from "@praviar/shared-types";
import { MarkushEvidenceStatusCard } from "@/components/report/markush-evidence-status-card";

function auditWithQueryPlan(queryPlan: object): PipelineAuditTrail {
  return {
    search_funnel: [],
    triage_audit: [],
    analysis_audit: [],
    timing_data: [],
    total_patents_discovered: 0,
    patents_after_hard_filter: 0,
    patents_after_ranking: 0,
    patents_after_triage: 0,
    patents_analyzed: 0,
    query_plan: queryPlan,
  } as unknown as PipelineAuditTrail;
}

describe("MarkushEvidenceStatusCard", () => {
  it("shows a clearance-blocking state when the manual search was not run", () => {
    render(
      <MarkushEvidenceStatusCard
        audit={auditWithQueryPlan({
          true_markush_coverage_status: "not_run",
        })}
      />,
    );

    expect(
      screen.getByRole("region", { name: "Markush coverage evidence" }),
    ).toBeInTheDocument();
    expect(screen.getByText("Not run")).toBeInTheDocument();
    expect(screen.getByText("Clearance gate blocked")).toBeInTheDocument();
    expect(
      screen.getByText(
        /distinct reviewer verifies PATENTSCOPE Markush evidence/i,
      ),
    ).toBeInTheDocument();
  });

  it("shows reviewer, artifact, query, and result provenance when verified", () => {
    render(
      <MarkushEvidenceStatusCard
        audit={auditWithQueryPlan({
          true_markush_coverage_status: "verified_manual",
          markush_evidence: {
            schema_version: "patentscope-markush-evidence-v3",
            source: "wipo_patentscope_manual",
            source_url: "https://patentscope.wipo.int/search/en/structure.jsf",
            status: "verified_manual",
            organization_id: "00000000-0000-4000-8000-000000000001",
            target_structure_sha256: "6".repeat(64),
            query_structure_sha256: "1".repeat(64),
            query_role: "target_compound",
            chemical_search_mode: "substructure",
            markush_enabled: true,
            markush_method: "formula_matching",
            markush_match_mode: "substructure",
            wipo_query_field: null,
            family_grouping_enabled: true,
            executed_at: "2026-07-25T10:00:00Z",
            server_imported_at: "2026-07-25T10:30:00Z",
            analyst_identity: "user:analyst",
            reviewer_identity: "user:reviewer",
            artifact_filename: "patentscope-results.xlsx",
            artifact_media_type: "application/octet-stream",
            imported_artifact_sha256: "2".repeat(64),
            imported_artifact_size_bytes: 100,
            controls_artifact_filename: "patentscope-controls.png",
            controls_artifact_media_type: "image/png",
            controls_artifact_sha256: "7".repeat(64),
            controls_artifact_size_bytes: 100,
            result_count: 12,
            selected_publication_ids: ["WO2020123456A1", "EP1234567B1"],
            selected_publication_ids_sha256: "3".repeat(64),
            limitations: ["The export schema is not a stable API contract."],
            attestation_key_id: "checkpoint-key-2026",
            attestation_hmac_sha256: "5".repeat(64),
            receipt_sha256: "4".repeat(64),
          },
        })}
      />,
    );

    expect(screen.getByText("Independently verified")).toBeInTheDocument();
    expect(screen.getByText("Clearance gate satisfied")).toBeInTheDocument();
    expect(screen.getByText("12 / 2")).toBeInTheDocument();
    expect(
      screen.getByText(/substructure · formula matching · substructure/i),
    ).toBeInTheDocument();
    expect(screen.getByText("user:analyst")).toBeInTheDocument();
    expect(screen.getByText("user:reviewer")).toBeInTheDocument();
    expect(screen.getByText("patentscope-results.xlsx")).toBeInTheDocument();
    expect(screen.getByText(/1111111111…11111111/)).toBeInTheDocument();
    expect(screen.getByText("checkpoint-key-2026")).toBeInTheDocument();
    expect(
      screen.getByRole("link", { name: "WIPO PATENTSCOPE" }),
    ).toHaveAttribute(
      "href",
      "https://patentscope.wipo.int/search/en/structure.jsf",
    );
    expect(
      screen.getByText("The export schema is not a stable API contract."),
    ).toBeInTheDocument();
    expect(screen.getByText(/2222222222…22222222/)).toBeInTheDocument();
    expect(screen.getByText(/4444444444…44444444/)).toBeInTheDocument();
  });
});
