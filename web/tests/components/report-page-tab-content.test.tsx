import {
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { ReportPageTabContent } from "@/components/report-page/report-page-tab-content";
import { buildClaimedUseReceiptLedger } from "../fixtures/claimed-use-receipts";
import { TEST_REPORT } from "../fixtures/report-fixture";

const mockEvidenceTab = vi.hoisted(() => vi.fn());
const mockReplace = vi.fn();

vi.mock("@/components/report/chat-panel-evidence-tab", () => ({
  ChatPanelEvidenceTab: (props: Record<string, unknown>) => {
    mockEvidenceTab(props);
    return <div>Governed report evidence workspace</div>;
  },
}));

vi.mock("next/navigation", () => ({
  useRouter: () => ({ replace: mockReplace }),
  useSearchParams: () => new URLSearchParams("tab=overview"),
}));

describe("ReportPageTabContent", () => {
  it("keeps claimed-use history visible in live review and print output", () => {
    render(
      <ReportPageTabContent
        analysisId="analysis-1"
        tab="overview"
        report={TEST_REPORT}
        canManageCollaboration
        claimedUseReceiptState={{
          data: buildClaimedUseReceiptLedger(),
          isError: false,
          isLoading: false,
        }}
      />,
    );

    expect(
      screen.getByTestId("claimed-use-receipt-ledger-screen"),
    ).toBeInTheDocument();
    expect(
      screen.getByTestId("claimed-use-receipt-ledger-print"),
    ).toBeInTheDocument();
    expect(screen.getAllByText("Claimed-use receipt history")).toHaveLength(2);
  });

  it("uses the supplied label id for active overflow sections", () => {
    render(
      <>
        <button type="button" id="overflow-tab-meta">
          Coverage & quality
        </button>
        <ReportPageTabContent
          analysisId="analysis-1"
          tab="meta"
          labelId="overflow-tab-meta"
          report={TEST_REPORT}
        />
      </>,
    );

    const panel = screen.getByRole("tabpanel");
    expect(panel).toHaveAttribute("id", "tabpanel-meta");
    expect(panel).toHaveAttribute("aria-labelledby", "overflow-tab-meta");
    expect(
      document.getElementById(panel.getAttribute("aria-labelledby") ?? ""),
    ).toBeInTheDocument();
    expect(
      screen.getByText("Local report-section print - Coverage & quality"),
    ).toBeInTheDocument();
    expect(screen.getByText("Print scope")).toBeInTheDocument();
    expect(
      screen.getAllByText("Local browser print: Coverage & quality").length,
    ).toBeGreaterThanOrEqual(2);
    expect(
      screen.getByText(
        "Ungoverned local work product containing only the active report section; use governed export for the complete branded artifact.",
      ),
    ).toBeInTheDocument();
    expect(screen.getAllByText("rpt_demo_succinic_001").length).toBeGreaterThan(
      0,
    );
    expect(screen.getByText("Pipeline 0.9.4")).toBeInTheDocument();
    expect(screen.getByText("4/5 sources successful")).toBeInTheDocument();
    expect(screen.getByText("5 model roles recorded")).toBeInTheDocument();
    expect(screen.getAllByText("High Risk").length).toBeGreaterThanOrEqual(2);
    const packetSummary = document.querySelector(
      "[aria-label='Print packet readiness summary']",
    );
    expect(packetSummary).toHaveTextContent("Counsel review pending");
    expect(packetSummary).toHaveTextContent(
      "Local browser print: Coverage & quality",
    );
    expect(packetSummary).toHaveTextContent("4/5 sources healthy");
    expect(packetSummary).toHaveTextContent("5 material patents");
    const relianceBoundary = document.querySelector(
      "[aria-label='Print report reliance boundary']",
    );
    expect(relianceBoundary).toHaveTextContent("rpt_demo_succinic_001");
    expect(relianceBoundary).toHaveTextContent(
      "decision-evidence score not reported",
    );
    expect(relianceBoundary).toHaveTextContent("5 material patents");
    expect(relianceBoundary).toHaveTextContent("5 sources in scope");
    expect(relianceBoundary).toHaveTextContent("5 model roles recorded");
    expect(relianceBoundary).toHaveTextContent(
      "qualified counsel sign-off required",
    );
  });

  it("labels non-overview print output as a current-section artifact", () => {
    render(
      <ReportPageTabContent
        analysisId="analysis-1"
        tab="claims"
        report={TEST_REPORT}
      />,
    );

    expect(
      screen.getByText("Local report-section print - Claims"),
    ).toBeInTheDocument();
    expect(
      screen.getAllByText("Local browser print: Claims").length,
    ).toBeGreaterThanOrEqual(2);
    expect(screen.getByRole("tabpanel")).toHaveAttribute(
      "id",
      "tabpanel-claims",
    );
  });

  it("treats listed sources without source health as caveated in the print packet", () => {
    render(
      <ReportPageTabContent
        analysisId="analysis-1"
        tab="overview"
        report={
          {
            ...TEST_REPORT,
            search_sources_used: ["pubchem_sdq"],
            source_health: { entries: [] },
          } as any
        }
        reviewStatus={
          {
            status: "approved",
            findings_total: 2,
            findings_reviewed: 2,
          } as any
        }
        reviewerDecisions={
          {
            items: [
              {
                decision: "accept",
                finding_ref: "US0000000001A1",
                finding_type: "patent",
                reviewer_user_id: "reviewer-a",
              },
              {
                decision: "edit",
                finding_ref: "US0000000001A1",
                finding_type: "patent",
                reviewer_user_id: "reviewer-b",
              },
              {
                decision: "accept",
                finding_ref: "US0000000002A1",
                finding_type: "patent",
                reviewer_user_id: "reviewer-a",
              },
              {
                decision: "accept",
                finding_ref: "US0000000002A1",
                finding_type: "patent",
                reviewer_user_id: "reviewer-b",
              },
              {
                decision: "accept",
                finding_ref: "US0000000003A1",
                finding_type: "patent",
                reviewer_user_id: "reviewer-a",
              },
              {
                decision: "accept",
                finding_ref: "assertion-2",
                finding_type: "claim_element",
                reviewer_user_id: "reviewer-a",
              },
            ],
            counts: { accept: 5, reject: 0, edit: 1 },
          } as any
        }
        workspaceSummary={
          {
            trust_mode: "counsel",
            opinion_readiness: {
              export_ready: true,
              summary: "Backend export readiness cleared.",
              jurisdictions_blocking_export: [],
            },
          } as any
        }
      />,
    );

    const packetSummary = document.querySelector(
      "[aria-label='Print packet readiness summary']",
    );
    expect(packetSummary).toHaveTextContent("Exportable with source caveats");
    expect(packetSummary).toHaveTextContent("0/1 sources healthy");
    expect(packetSummary).toHaveTextContent("Source health not reported");
    expect(packetSummary).not.toHaveTextContent("Counsel-ready packet");
  });

  it("blocks counsel-ready print handoff until material reviewer decisions clear", () => {
    render(
      <ReportPageTabContent
        analysisId="analysis-1"
        tab="overview"
        report={TEST_REPORT}
        reviewStatus={
          {
            status: "approved",
            findings_total: 4,
            findings_reviewed: 4,
          } as any
        }
        reviewerDecisions={
          {
            items: [],
            counts: { accept: 0, reject: 0, edit: 0 },
          } as any
        }
        workspaceSummary={
          {
            trust_mode: "counsel",
            opinion_readiness: {
              export_ready: true,
              summary: "Backend export readiness cleared.",
              jurisdictions_blocking_export: [],
            },
          } as any
        }
      />,
    );

    const packetSummary = document.querySelector(
      "[aria-label='Print packet readiness summary']",
    );
    expect(packetSummary).toHaveTextContent("Reviewer decisions incomplete");
    expect(packetSummary).toHaveTextContent("has no reviewer decision");
    expect(packetSummary).not.toHaveTextContent("Counsel-ready packet");
  });

  it("renders the first-class Evidence tab with governed workspace context", () => {
    const onReviewHandoffSuccess = vi.fn();

    render(
      <ReportPageTabContent
        analysisId="analysis-1"
        tab="evidence"
        report={{
          ...TEST_REPORT,
          claim_source_span_map: {
            generated_from: "test",
            entries: [
              {
                assertion_id: "assertion-1",
                patent_id: "US0000000001A1",
                claim_number: 1,
                element_number: 1,
                report_section: "claim_element_analysis",
                assertion_text:
                  "Claim 1 element 1 is supported by the generated source span.",
                source_span_ids: ["span-1"],
                support_status: "supported",
                customer_visible: true,
              },
              {
                assertion_id: "assertion-2",
                patent_id: "US0000000001A1",
                claim_number: 1,
                element_number: 2,
                report_section: "claim_element_analysis",
                assertion_text:
                  "Claim 1 element 2 needs a missing span review.",
                source_span_ids: ["missing-span"],
                support_status: "needs_review",
                customer_visible: true,
              },
              {
                assertion_id: "assertion-3",
                patent_id: "US0000000001A1",
                claim_number: 1,
                element_number: 3,
                report_section: "claim_element_analysis",
                assertion_text: "Claim 1 element 3 is unsupported.",
                source_span_ids: ["span-1"],
                support_status: "unsupported",
                customer_visible: true,
              },
            ],
            spans: {
              "span-1": {
                span_id: "span-1",
                source_type: "element_evidence",
                patent_id: "US0000000001A1",
                claim_number: 1,
                element_number: 1,
                citation: "US0000000001A1 claim 1",
                excerpt:
                  "Succinic acid is a C4 dicarboxylic acid and E. coli is a prokaryotic organism.",
              },
            },
            needs_review_count: 1,
            unsupported_customer_visible_claim_count: 0,
          },
        }}
        token="tok-report"
        initialEvidenceQuery="blocking claim elements"
        onReviewHandoffSuccess={onReviewHandoffSuccess}
        reviewStatus={
          {
            status: "approved",
            findings_total: 2,
            findings_reviewed: 2,
          } as any
        }
        reviewerDecisions={
          {
            items: [
              {
                decision: "accept",
                finding_ref: "US0000000001A1",
                finding_type: "patent",
                reviewer_user_id: "reviewer-a",
              },
              {
                decision: "edit",
                finding_ref: "US0000000001A1",
                finding_type: "patent",
                reviewer_user_id: "reviewer-b",
              },
              {
                decision: "accept",
                finding_ref: "US0000000002A1",
                finding_type: "patent",
                reviewer_user_id: "reviewer-a",
              },
              {
                decision: "accept",
                finding_ref: "US0000000002A1",
                finding_type: "patent",
                reviewer_user_id: "reviewer-b",
              },
              {
                decision: "accept",
                finding_ref: "US0000000003A1",
                finding_type: "patent",
                reviewer_user_id: "reviewer-a",
              },
              {
                decision: "accept",
                finding_ref: "assertion-2",
                finding_type: "claim_element",
                reviewer_user_id: "reviewer-a",
              },
            ],
            counts: { accept: 5, reject: 0, edit: 1 },
          } as any
        }
        workspaceSummary={
          {
            trust_mode: "counsel",
            opinion_readiness: {
              export_ready: true,
              summary: "Export-grade caveats are preserved.",
              jurisdictions_blocking_export: [],
            },
            target_jurisdictions: ["US", "EP"],
            suggested_evidence_queries: [
              {
                query: "show blocking patent provenance",
                rationale: "Counsel needs the strongest evidence first.",
                source: "workspace",
              },
            ],
            evidence_scope: {
              mode: "report_evidence",
              external_live_retrieval: true,
              comment_routing_available: true,
              sources_considered: ["patents", "semantic_scholar"],
              governed_note: "Governed evidence scope.",
              provider_capabilities: [],
              providers: [],
              hybrid_evidence_ready: true,
            },
          } as any
        }
      />,
    );

    expect(
      screen.getByText("Local report-section print - Evidence"),
    ).toBeInTheDocument();
    expect(
      document.querySelector("[aria-label='Print packet readiness summary']"),
    ).toHaveTextContent("Exportable with source caveats");
    expect(mockEvidenceTab).toHaveBeenCalledWith(
      expect.objectContaining({
        initialQuery: "blocking claim elements",
      }),
    );
    expect(
      screen.getByRole("region", { name: "Evidence workbench" }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("heading", {
        name: "Source ledger and citation verification",
      }),
    ).toBeInTheDocument();
    expect(screen.getByText("4 / 5 healthy")).toBeInTheDocument();
    expect(screen.getByText("5 / 6")).toBeInTheDocument();
    expect(screen.getByText("patcid")).toBeInTheDocument();
    const evidenceWorkbench = screen.getByRole("region", {
      name: "Evidence workbench",
    });
    const patcidDiagnostics = within(evidenceWorkbench).getAllByText(
      /PatCID API returned HTTP 503 Service Unavailable/i,
    );
    expect(patcidDiagnostics.length).toBeGreaterThan(0);
    for (const diagnostic of patcidDiagnostics) {
      expect(diagnostic).not.toHaveClass("line-clamp-2");
    }
    expect(
      patcidDiagnostics.some((diagnostic) =>
        diagnostic.className.includes("[overflow-wrap:anywhere]"),
      ),
    ).toBe(true);
    for (const verifierDiagnostic of within(evidenceWorkbench).getAllByText(
      /The fictional report references are internally consistent/i,
    )) {
      expect(verifierDiagnostic).not.toHaveClass("line-clamp-3");
    }
    expect(
      within(evidenceWorkbench).getByText(
        /The sample equivalence assessment conflicts with its fictional prosecution-history note/i,
      ),
    ).not.toHaveClass("line-clamp-3");
    expect(
      within(evidenceWorkbench).getByText(
        /The sample equivalence assessment may be overconfident/i,
      ),
    ).not.toHaveClass("line-clamp-3");
    expect(
      within(evidenceWorkbench).getByText(
        /BigQuery annotations quota exceeded/i,
      ),
    ).toBeInTheDocument();
    expect(
      screen.getAllByText("US0000000001A1 / claim 1 / element 1").length,
    ).toBeGreaterThanOrEqual(1);
    expect(
      screen.getAllByRole("link", {
        name: /open in claims for US0000000001A1 \/ claim 1 \/ element 1/i,
      })[0],
    ).toHaveAttribute(
      "href",
      "?tab=claims&patent=US0000000001A1&claim=1&element=1#us0000000001a1-claim-1-element-1",
    );
    const ledger = screen.getByRole("region", {
      name: "Counsel evidence ledger",
    });
    expect(ledger).toHaveAttribute("data-testid", "counsel-evidence-ledger");
    expect(ledger).toHaveTextContent("Customer-visible claim assertions");
    expect(ledger).toHaveTextContent("Claim 1 element 1 is supported");
    expect(ledger).toHaveTextContent(
      "Claim 1 element 2 needs a missing span review",
    );
    expect(
      within(ledger)
        .getAllByText("Unsupported")
        .some(
          (element) =>
            element.className.includes("text-[var(--color-error-badge-fg)]") &&
            element.className.includes("bg-error/10"),
        ),
    ).toBe(true);
    expect(
      within(ledger).getByRole("link", {
        name: /open in claims for US0000000001A1 \/ claim 1 \/ element 2/i,
      }),
    ).toHaveAttribute(
      "href",
      "?tab=claims&patent=US0000000001A1&claim=1&element=2#us0000000001a1-claim-1-element-2",
    );
    expect(
      within(ledger).getByRole("link", {
        name: /open in claims for US0000000001A1 \/ claim 1 \/ element 2 \(assertion assertion-2\)/i,
      }),
    ).toBeInTheDocument();
    const downloadWorkPacket = within(ledger).getByRole("link", {
      name: "Download work packet",
    });
    expect(downloadWorkPacket).toHaveAttribute(
      "download",
      "rpt_demo_succinic_001-evidence-work-packet.txt",
    );
    expect(downloadWorkPacket).toHaveClass("min-h-11");
    expect(
      within(ledger).getByRole("button", { name: "Copy work packet" }),
    ).toHaveClass("min-h-11");
    for (const filter of within(ledger).getAllByRole("button")) {
      expect(filter).toHaveClass("min-h-11");
    }
    const artifactBinder = within(ledger).getByRole("region", {
      name: "Evidence artifact binder",
    });
    expect(artifactBinder).toHaveAttribute(
      "data-testid",
      "evidence-artifact-binder",
    );
    const evidenceFindingsRegion = within(ledger).getByRole("region", {
      name: "Evidence workbench findings table",
    });
    expect(evidenceFindingsRegion).toHaveAttribute("tabindex", "0");
    expect(evidenceFindingsRegion).not.toHaveClass("overflow-x-auto");
    expect(evidenceFindingsRegion).toHaveClass("sm:overflow-x-auto");
    const evidenceFindingsTable = within(evidenceFindingsRegion).getByRole(
      "table",
    );
    expect(evidenceFindingsTable).toHaveClass(
      "block",
      "min-w-0",
      "sm:table",
      "sm:min-w-[980px]",
    );
    const evidenceFindingsBody = evidenceFindingsRegion.querySelector("tbody");
    expect(evidenceFindingsBody).toHaveClass(
      "grid",
      "gap-3",
      "sm:table-row-group",
    );
    const firstFindingRow = evidenceFindingsBody?.querySelector("tr");
    expect(firstFindingRow).toHaveClass("grid", "rounded-md", "sm:table-row");
    expect(
      within(firstFindingRow as HTMLElement).getByText("Source span"),
    ).toHaveClass("sm:hidden");
    expect(artifactBinder).toHaveTextContent("Derived assertion index");
    expect(artifactBinder).toHaveTextContent(
      "rpt_demo_succinic_001:assertion-2",
    );
    expect(artifactBinder).toHaveTextContent("Needs Review");
    expect(artifactBinder).toHaveTextContent("Source scope incomplete");
    expect(
      within(artifactBinder).getByRole("link", {
        name: "Open artifact rpt_demo_succinic_001:assertion-2 in Claims",
      }),
    ).toHaveAttribute(
      "href",
      "?tab=claims&patent=US0000000001A1&claim=1&element=2#us0000000001a1-claim-1-element-2",
    );
    expect(
      screen.getAllByText("US0000000001A1 claim 1").length,
    ).toBeGreaterThanOrEqual(1);
    expect(
      screen.getAllByText(/Succinic acid is a C4 dicarboxylic acid/i).length,
    ).toBeGreaterThanOrEqual(1);
    expect(screen.getByText("Missing source spans")).toBeInTheDocument();
    expect(screen.getByText("Deterministic checks")).toBeInTheDocument();
    expect(screen.getByText("Gaps board")).toBeInTheDocument();
    expect(
      screen.getByText("Governed report evidence workspace"),
    ).toBeInTheDocument();
    expect(mockEvidenceTab).toHaveBeenCalledWith(
      expect.objectContaining({
        analysisId: "analysis-1",
        onReviewHandoffSuccess,
        queryInputId: "report-evidence-workbench-query",
        token: "tok-report",
        suggestedQueries: ["show blocking patent provenance"],
        workspaceMeta: expect.objectContaining({
          trust_mode: "counsel",
          capability_label: "Hybrid evidence review",
          evidence_mode: "Hybrid governed evidence",
          source_coverage: "2 sources considered",
          tool_access: ["external_evidence_expand", "review_handoff"],
        }),
      }),
    );
    expect(screen.getByRole("tabpanel")).toHaveAttribute(
      "id",
      "tabpanel-evidence",
    );
  });

  it("filters and copies a counsel evidence packet from the ledger", async () => {
    const writeText = vi.fn().mockResolvedValue(undefined);
    Object.defineProperty(navigator, "clipboard", {
      configurable: true,
      value: { writeText },
    });

    render(
      <ReportPageTabContent
        analysisId="analysis-1"
        tab="evidence"
        report={{
          ...TEST_REPORT,
          patent_analyses: [],
          claim_source_span_map: {
            generated_from: "test",
            entries: [
              {
                assertion_id: "assertion-1",
                patent_id: "US0000000001A1",
                claim_number: 1,
                element_number: 1,
                report_section: "claim_element_analysis",
                assertion_text: "Claim 1 element 1 is supported.",
                source_span_ids: ["span-1"],
                support_status: "supported",
                customer_visible: true,
              },
              {
                assertion_id: "assertion-2",
                patent_id: "US0000000001A1",
                claim_number: 1,
                element_number: 2,
                report_section: "claim_element_analysis",
                assertion_text: "Claim 1 element 2 needs review.",
                source_span_ids: ["missing-span"],
                support_status: "needs_review",
                customer_visible: true,
              },
            ],
            spans: {
              "span-1": {
                span_id: "span-1",
                source_type: "element_evidence",
                patent_id: "US0000000001A1",
                claim_number: 1,
                element_number: 1,
                citation: "US0000000001A1 claim 1",
                excerpt: "Supported source excerpt.",
              },
            },
          },
        }}
        reviewStatus={
          {
            status: "approved",
            findings_total: 1,
            findings_reviewed: 1,
          } as any
        }
        reviewerDecisions={
          {
            items: [
              {
                decision: "accept",
                finding_ref: "assertion-2",
                finding_type: "claim_element",
                reviewer_user_id: "reviewer-a",
              },
            ],
            counts: { accept: 1, reject: 0, edit: 0 },
          } as any
        }
        workspaceSummary={
          {
            trust_mode: "counsel",
            opinion_readiness: {
              export_ready: true,
              summary: "Backend export readiness cleared.",
              jurisdictions_blocking_export: [],
            },
          } as any
        }
      />,
    );

    const ledger = screen.getByRole("region", {
      name: "Counsel evidence ledger",
    });
    fireEvent.click(
      within(ledger).getByRole("button", { name: /Missing spans/i }),
    );

    expect(ledger).toHaveTextContent("Claim 1 element 2 needs review.");
    expect(ledger).not.toHaveTextContent("Claim 1 element 1 is supported.");
    expect(ledger).not.toHaveTextContent("Claim 1 element 3 is unsupported.");
    const filteredFindingsRegion = within(ledger).getByRole("region", {
      name: "Evidence workbench findings table",
    });
    const filteredFindingRows =
      filteredFindingsRegion.querySelectorAll("tbody tr");
    expect(filteredFindingRows).toHaveLength(1);
    expect(filteredFindingRows[0]).toHaveClass("grid", "sm:table-row");
    expect(
      within(filteredFindingRows[0] as HTMLElement).getByText("Source span"),
    ).toHaveClass("sm:hidden");
    const filteredBinder = within(ledger).getByRole("region", {
      name: "Evidence artifact binder",
    });
    expect(filteredBinder).toHaveTextContent(
      "rpt_demo_succinic_001:assertion-2",
    );
    expect(filteredBinder).not.toHaveTextContent(
      "rpt_demo_succinic_001:assertion-3",
    );

    fireEvent.click(
      within(ledger).getByRole("button", { name: "Copy work packet" }),
    );

    await waitFor(() => expect(writeText).toHaveBeenCalledTimes(1));
    const packet = writeText.mock.calls[0][0];
    expect(packet).toContain("Praviar local evidence work packet");
    expect(packet).toContain(
      "This packet is local work product from the Evidence tab, not an export-grade legal deliverable.",
    );
    expect(packet).toContain("Filter: Missing spans");
    expect(packet).toContain("Evidence artifact binder");
    expect(packet).toContain("Rows: 1 of 2");
    expect(packet).toContain("rpt_demo_succinic_001:assertion-2");
    expect(packet).toContain("Status: Needs Review");
    expect(packet).toContain("Evidence references: 1");
    expect(packet).toContain("Gate: Missing source span");
    expect(packet).toContain("Claim assertion ledger");
    expect(packet).toContain("Assertion ID: assertion-2");
    expect(packet).toContain("Source span: missing referenced span");
    expect(packet).toContain(
      "Claims link: ?tab=claims&patent=US0000000001A1&claim=1&element=2#us0000000001a1-claim-1-element-2",
    );
    expect(packet).not.toContain("assertion-1");
    expect(packet).not.toContain("assertion-3");
    expect(
      within(ledger).getByRole("button", { name: "Copied work packet" }),
    ).toBeInTheDocument();
  });

  it("blocks local evidence work-packet export when readiness is blocked", () => {
    render(
      <ReportPageTabContent
        analysisId="analysis-1"
        tab="evidence"
        report={TEST_REPORT}
        workspaceSummary={
          {
            trust_mode: "counsel",
            opinion_readiness: {
              export_ready: false,
              summary: "Counsel export remains blocked.",
              jurisdictions_blocking_export: ["US"],
            },
          } as any
        }
      />,
    );

    const ledger = screen.getByRole("region", {
      name: "Counsel evidence ledger",
    });
    expect(ledger).toHaveTextContent("Packet blocked");
    expect(ledger).toHaveTextContent("Work-packet export is blocked");
    expect(
      within(ledger).queryByRole("link", { name: "Download work packet" }),
    ).not.toBeInTheDocument();
  });

  it("blocks local evidence work-packet export until material reviewer decisions are complete", () => {
    render(
      <ReportPageTabContent
        analysisId="analysis-1"
        tab="evidence"
        report={TEST_REPORT}
        reviewStatus={
          {
            analysis_id: "analysis-1",
            status: "approved",
            note: "Approved after review.",
            reviewer_name: "Demo Counsel",
            reviewer_email: "counsel@example.test",
            reviewed_at: "2026-04-24T10:00:00.000Z",
            updated_at: "2026-04-24T10:00:00.000Z",
            decision_counts: { accept: 0, reject: 0, edit: 0 },
            findings_total: 4,
            findings_reviewed: 4,
            completion_pct: 100,
          } as any
        }
        reviewerDecisions={{
          items: [],
          counts: { accept: 0, reject: 0, edit: 0 },
        }}
        workspaceSummary={
          {
            trust_mode: "counsel",
            opinion_readiness: {
              export_ready: true,
              summary: "Backend export readiness cleared.",
              jurisdictions_blocking_export: [],
            },
          } as any
        }
      />,
    );

    const ledger = screen.getByRole("region", {
      name: "Counsel evidence ledger",
    });
    expect(ledger).toHaveTextContent("Packet blocked");
    expect(ledger).toHaveTextContent("Reviewer decisions incomplete");
    expect(ledger).toHaveTextContent("material finding");
    expect(
      within(ledger).getByRole("button", { name: "Copy work packet" }),
    ).toBeDisabled();
    expect(
      within(ledger).queryByRole("link", { name: "Download work packet" }),
    ).not.toBeInTheDocument();
  });

  it("does not render missing source health as healthy in Evidence", () => {
    render(
      <ReportPageTabContent
        analysisId="analysis-1"
        tab="evidence"
        report={{
          ...TEST_REPORT,
          search_sources_used: [],
          source_health: { entries: [] },
        }}
      />,
    );

    const workbench = screen.getByRole("region", {
      name: "Evidence workbench",
    });
    expect(workbench).toHaveTextContent("0 / 0");
    expect(workbench).toHaveTextContent("Source health ledger not reported");
    expect(workbench).toHaveTextContent(
      "No source health ledger was reported.",
    );
    expect(workbench).not.toHaveTextContent("All reported sources healthy");
    expect(workbench).not.toHaveTextContent("No recorded blockers");

    const ledger = screen.getByRole("region", {
      name: "Counsel evidence ledger",
    });
    expect(ledger).toHaveTextContent("Packet blocked");
    expect(ledger).toHaveTextContent("Export readiness unavailable");
  });

  it("treats absent verifier and claim-support ledgers as blockers", () => {
    render(
      <ReportPageTabContent
        analysisId="analysis-1"
        tab="evidence"
        report={
          {
            ...TEST_REPORT,
            verification: undefined,
            claim_source_span_map: undefined,
          } as any
        }
      />,
    );

    const workbench = screen.getByRole("region", {
      name: "Evidence workbench",
    });
    expect(workbench).toHaveTextContent("Verifier ledger not reported");
    expect(workbench).toHaveTextContent("Claim-support ledger not reported");
    expect(workbench).toHaveTextContent("Verifier ledger missing");
    expect(workbench).toHaveTextContent("Claim-support ledger missing");
    expect(workbench).not.toHaveTextContent("Deterministic checks passed");
    expect(workbench).not.toHaveTextContent("No recorded blockers");
  });

  it("counts a low decision-evidence score as a visible blocker", () => {
    render(
      <ReportPageTabContent
        analysisId="analysis-1"
        tab="evidence"
        report={{
          ...TEST_REPORT,
          clearance_decision: {
            ...TEST_REPORT.clearance_decision,
            evidence_quality: 0.79,
          },
        }}
      />,
    );

    const workbench = screen.getByRole("region", {
      name: "Evidence workbench",
    });
    expect(workbench).toHaveTextContent(
      "Decision-evidence score below review threshold",
    );
    expect(workbench).toHaveTextContent("79%");
    expect(workbench).not.toHaveTextContent("No recorded blockers");
  });

  it("counts a missing decision-evidence score as a visible blocker", () => {
    render(
      <ReportPageTabContent
        analysisId="analysis-1"
        tab="evidence"
        report={{
          ...TEST_REPORT,
          clearance_decision: {
            ...TEST_REPORT.clearance_decision,
            evidence_quality: undefined,
          },
        }}
      />,
    );

    const workbench = screen.getByRole("region", {
      name: "Evidence workbench",
    });
    expect(workbench).toHaveTextContent("Decision-evidence score missing");
    expect(workbench).not.toHaveTextContent("No recorded blockers");
  });

  it("sanitizes diagnostic details before rendering the Evidence workbench", () => {
    render(
      <ReportPageTabContent
        analysisId="analysis-1"
        tab="evidence"
        report={
          {
            ...TEST_REPORT,
            source_health: {
              entries: [
                {
                  source: "patcid",
                  status: "failed",
                  patent_count: 0,
                  error_message:
                    "Connection postgres://user:pass@localhost/db failed with Bearer abc123 at /Users/example-user/private Traceback stack",
                },
              ],
            },
            verification: {
              checks: [
                {
                  check_name: "citation_integrity",
                  passed: false,
                  severity: "warning",
                  details:
                    "Verifier saw sk_live_secret and SELECT * FROM private_table before Traceback stack",
                },
              ],
              issues: [
                "Issue contains sk_test_secret and /tmp/provider/raw.log",
              ],
            },
            analysis_failures: [
              {
                patent_id: "US123",
                step: "claim_analysis",
                error_type: "tool_error",
                error_message:
                  "postgres://hidden Bearer token456 /var/tmp/private Traceback stack",
              },
            ],
            data_limitations: [
              {
                category: "source_limit",
                description: "/var/tmp/raw Bearer limitation",
                impact: "sk" + "_test_" + "impacttoken",
              },
            ],
            coverage_gaps: [
              {
                gap_type: "provider_gap",
                description: "Traceback most recent provider call",
                suggested_action:
                  "SELECT secret FROM evidence_cache /tmp/follow-up",
              },
            ],
          } as any
        }
      />,
    );

    const workbench = screen.getByRole("region", {
      name: "Evidence workbench",
    });

    expect(workbench).not.toHaveTextContent("postgres://");
    expect(workbench).not.toHaveTextContent("Bearer abc123");
    expect(workbench).not.toHaveTextContent("sk_live_secret");
    expect(workbench).not.toHaveTextContent("sk_test_secret");
    expect(workbench).not.toHaveTextContent("/Users/example-user/private");
    expect(workbench).not.toHaveTextContent("/tmp/provider/raw.log");
    expect(workbench).not.toHaveTextContent("private_table");
    expect(workbench).toHaveTextContent("[redacted connection string]");
    expect(workbench).toHaveTextContent("Bearer [redacted]");
    expect(workbench).toHaveTextContent("[redacted API key]");
    expect(workbench).toHaveTextContent("[redacted path]");
    expect(workbench).toHaveTextContent(
      "Diagnostic details are available to support.",
    );
  });

  it("counts severity-only verifier passes as passed checks", () => {
    render(
      <ReportPageTabContent
        analysisId="analysis-1"
        tab="evidence"
        report={{
          ...TEST_REPORT,
          verification: {
            checks: [
              {
                check_name: "citation_integrity",
                severity: "pass",
                details: "Citation integrity passed.",
              },
            ],
            issues: [],
          } as any,
        }}
      />,
    );

    const workbench = screen.getByRole("region", {
      name: "Evidence workbench",
    });
    expect(workbench).toHaveTextContent("1 / 1");
    expect(workbench).toHaveTextContent("Deterministic checks passed");
    expect(workbench).toHaveTextContent("Citation Integrity");
    expect(workbench).toHaveTextContent("pass");
  });

  it("prints a fractional decision-evidence score as a percentage", () => {
    render(
      <ReportPageTabContent
        analysisId="analysis-1"
        tab="meta"
        report={{
          ...TEST_REPORT,
          clearance_decision: {
            ...TEST_REPORT.clearance_decision,
            evidence_quality: 0.85,
          },
        }}
      />,
    );

    expect(
      screen.getByText(/85% decision-evidence score across/i),
    ).toBeInTheDocument();
  });

  it("does not multiply a percentage decision-evidence score twice", () => {
    render(
      <ReportPageTabContent
        analysisId="analysis-1"
        tab="meta"
        report={{
          ...TEST_REPORT,
          clearance_decision: {
            ...TEST_REPORT.clearance_decision,
            evidence_quality: 85,
          },
        }}
      />,
    );

    expect(
      screen.getByText(/85% decision-evidence score across/i),
    ).toBeInTheDocument();
    expect(
      screen.queryByText(/8500% decision-evidence score/i),
    ).not.toBeInTheDocument();
  });

  it("keeps the summary reliability rail in printable report content", () => {
    render(
      <ReportPageTabContent
        analysisId="analysis-1"
        tab="overview"
        report={TEST_REPORT}
      />,
    );

    const rail = screen.getByRole("complementary", {
      name: "Report reliability and methodology",
    });

    expect(rail).toBeInTheDocument();
    expect(rail).not.toHaveAttribute("data-no-print");
    expect(rail.closest("[data-no-print]")).toBeNull();
    expect(rail).toHaveTextContent("Evidence Readiness");
    expect(
      screen.getByText("Compound Details & Search Methodology"),
    ).toBeInTheDocument();
  });
});
