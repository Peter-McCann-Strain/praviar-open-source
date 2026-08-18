import { describe, it, expect, vi, beforeEach } from "vitest";
import {
  render,
  screen,
  fireEvent,
  act,
  waitFor,
} from "@testing-library/react";
import { ExportDialog } from "@/components/collaboration/export-dialog";
import { ExportDialogActions } from "@/components/collaboration/export-dialog-actions";
import { APIError } from "@/lib/api-client";
import { buildClaimedUseReceiptLedger } from "../fixtures/claimed-use-receipts";
import { TEST_REPORT } from "../fixtures/report-fixture";

// Mock dependencies
vi.mock("@/hooks/use-auth-token", () => ({
  useAuthToken: () => "dev-token",
}));

vi.mock("@/lib/demo-mode", () => ({
  DEMO_MODE_ENABLED: true,
  isDemoMode: () => true,
}));

const mockMutateAsync = vi.fn();
const mockExportStatusData = vi.hoisted(() => ({ value: null as unknown }));
vi.mock("@/hooks/use-export", () => ({
  useExportReport: () => ({
    mutateAsync: mockMutateAsync,
    isPending: false,
  }),
  useExportStatus: () => ({
    data: mockExportStatusData.value,
  }),
}));

const mockAddToast = vi.fn();
vi.mock("@/stores/toast-store", () => ({
  useToastStore: () => ({
    addToast: mockAddToast,
  }),
}));
const mockClipboardWriteText = vi.fn();

describe("ExportDialog", () => {
  const sourceReadyReport = {
    ...TEST_REPORT,
    source_health: {
      entries: TEST_REPORT.search_sources_used.map((source) => ({
        source,
        status: "ok" as const,
        patent_count: 1,
        error_message: "",
      })),
    },
  } as typeof TEST_REPORT;
  const noClaimChartReport = {
    ...sourceReadyReport,
    patent_analyses: sourceReadyReport.patent_analyses.map((analysis) => ({
      ...analysis,
      claims_analyzed: [],
    })),
  } as typeof TEST_REPORT;
  const defaultProps = {
    reportId: "report-456",
    report: TEST_REPORT,
    open: true,
    currentUserRole: "attorney",
    onClose: vi.fn(),
  };
  const completeReviewerDecisions = {
    items: [
      {
        id: "decision-high-1-a",
        finding_type: "patent",
        finding_ref: "US0000000001A1",
        decision: "accept",
        note: "",
        edited_text: "",
        reviewer_user_id: "reviewer-a",
        reviewer_name: "Reviewer A",
        reviewer_email: "reviewer-a@example.test",
        created_at: "2026-04-24T10:00:00.000Z",
        updated_at: "2026-04-24T10:00:00.000Z",
      },
      {
        id: "decision-high-1-b",
        finding_type: "patent",
        finding_ref: "US0000000001A1",
        decision: "accept",
        note: "",
        edited_text: "",
        reviewer_user_id: "reviewer-b",
        reviewer_name: "Reviewer B",
        reviewer_email: "reviewer-b@example.test",
        created_at: "2026-04-24T10:01:00.000Z",
        updated_at: "2026-04-24T10:01:00.000Z",
      },
      {
        id: "decision-high-2-a",
        finding_type: "patent",
        finding_ref: "US0000000002A1",
        decision: "accept",
        note: "",
        edited_text: "",
        reviewer_user_id: "reviewer-a",
        reviewer_name: "Reviewer A",
        reviewer_email: "reviewer-a@example.test",
        created_at: "2026-04-24T10:02:00.000Z",
        updated_at: "2026-04-24T10:02:00.000Z",
      },
      {
        id: "decision-high-2-b",
        finding_type: "patent",
        finding_ref: "US0000000002A1",
        decision: "accept",
        note: "",
        edited_text: "",
        reviewer_user_id: "reviewer-b",
        reviewer_name: "Reviewer B",
        reviewer_email: "reviewer-b@example.test",
        created_at: "2026-04-24T10:03:00.000Z",
        updated_at: "2026-04-24T10:03:00.000Z",
      },
      {
        id: "decision-medium-1-a",
        finding_type: "patent",
        finding_ref: "US0000000003A1",
        decision: "accept",
        note: "",
        edited_text: "",
        reviewer_user_id: "reviewer-a",
        reviewer_name: "Reviewer A",
        reviewer_email: "reviewer-a@example.test",
        created_at: "2026-04-24T10:04:00.000Z",
        updated_at: "2026-04-24T10:04:00.000Z",
      },
    ],
    counts: { accept: 5, reject: 0, edit: 0 },
  } as any;
  const readyProps = {
    ...defaultProps,
    report: sourceReadyReport,
    reviewerDecisions: completeReviewerDecisions,
    reviewStatus: {
      analysis_id: "analysis-1",
      status: "approved",
      note: null,
      reviewer_name: "Counsel",
      reviewer_email: "counsel@example.test",
      reviewed_at: "2026-04-24T10:00:00.000Z",
      updated_at: "2026-04-24T10:00:00.000Z",
      decision_counts: { accept: 4, reject: 0, edit: 0 },
      findings_total: 4,
      findings_reviewed: 4,
      completion_pct: 100,
    },
    workspaceSummary: {
      trust_mode: "counsel",
      opinion_readiness: {
        export_ready: true,
        summary: "Export-grade caveats are preserved.",
        jurisdictions_blocking_export: [],
      },
    },
  } as const;

  beforeEach(() => {
    vi.resetAllMocks();
    mockExportStatusData.value = null;
    Object.defineProperty(URL, "createObjectURL", {
      configurable: true,
      value: vi.fn(() => "blob:praviar-demo-artifact"),
    });
    Object.defineProperty(URL, "revokeObjectURL", {
      configurable: true,
      value: vi.fn(),
    });
    Object.defineProperty(navigator, "clipboard", {
      configurable: true,
      value: {
        writeText: mockClipboardWriteText,
      },
    });
    Object.defineProperty(document, "execCommand", {
      configurable: true,
      value: vi.fn().mockReturnValue(true),
    });
    mockClipboardWriteText.mockResolvedValue(undefined);
  });

  function openReviewDetails() {
    const reviewDetailsButton = screen.getByRole("button", {
      name: /Readiness brief and receipt preview/i,
    });
    fireEvent.click(reviewDetailsButton);
    expect(reviewDetailsButton).toHaveAttribute("aria-expanded", "true");
    return screen.getByRole("region", { name: "Review details" });
  }

  describe("dialog rendering", () => {
    it("shows attributable claimed-use history in the export surface", () => {
      render(
        <ExportDialog
          {...defaultProps}
          claimedUseReceiptState={{
            data: buildClaimedUseReceiptLedger(),
            isError: false,
            isLoading: false,
          }}
        />,
      );

      const ledger = screen.getByTestId("claimed-use-receipt-ledger-export");
      expect(ledger).toHaveTextContent("Claimed-use receipt history");
      expect(ledger).toHaveTextContent("US12345678A1:grant-claims");
      expect(ledger).toHaveTextContent(
        "They do not rewrite or recertify the pipeline result",
      );
    });

    it("renders when open is true", () => {
      render(<ExportDialog {...defaultProps} />);
      expect(
        screen.getByRole("dialog", { name: "Export evidence packet" }),
      ).toBeInTheDocument();
    });

    it("does not render when open is false", () => {
      render(<ExportDialog {...defaultProps} open={false} />);
      expect(
        screen.queryByRole("dialog", { name: "Export evidence packet" }),
      ).not.toBeInTheDocument();
    });

    it("renders the report identity and counsel caveat", () => {
      render(<ExportDialog {...defaultProps} />);
      expect(
        screen.getByText(
          "Build a review evidence export with source links, section scope, and caveats preserved.",
        ),
      ).toBeInTheDocument();
      expect(screen.getByText(TEST_REPORT.report_id)).toHaveClass(
        "break-words",
        "[overflow-wrap:anywhere]",
      );
      expect(screen.getByText("succinic acid")).toHaveClass(
        "break-words",
        "[overflow-wrap:anywhere]",
      );
      expect(
        screen.getByText(
          "AI scoped evidence and blockers; counsel review required.",
        ),
      ).toBeInTheDocument();
      expect(
        document.querySelector(
          'svg[data-praviar-mark="praviar-evidence-mark"]',
        ),
      ).toBeInTheDocument();
    });

    it("uses semantic risk badge styling for clear reports", () => {
      render(
        <ExportDialog
          {...defaultProps}
          report={
            {
              ...TEST_REPORT,
              risk_summary: {
                ...TEST_REPORT.risk_summary,
                overall_risk: "clear",
              },
            } as typeof TEST_REPORT
          }
        />,
      );

      const badge = screen.getByText("No Blockers");
      expect(badge).toHaveClass("text-[var(--color-info-badge-fg)]");
      expect(badge.className).not.toContain("text-error");
      expect(badge.className).not.toContain("border-error");
    });

    it("renders export readiness context", () => {
      render(<ExportDialog {...defaultProps} />);
      const readiness = screen.getByRole("region", {
        name: "Export readiness",
      });
      const decisionSummary = screen.getByRole("region", {
        name: "Export decision summary",
      });
      const reviewDetailsButton = screen.getByRole("button", {
        name: /Readiness brief and receipt preview/i,
      });

      expect(readiness).toHaveTextContent("Source audit");
      expect(readiness).toHaveTextContent("Authoritative state");
      expect(readiness).toHaveTextContent("Ready for QA");
      expect(readiness).toHaveTextContent("Reviewer / counsel");
      expect(readiness).toHaveTextContent(
        "Assign counsel review and close material findings.",
      );
      expect(readiness).toHaveTextContent(
        "1 failed; coverage may be incomplete.",
      );
      expect(screen.getByText(/Source audit caveat:/)).toHaveTextContent(
        "1 failed; coverage may be incomplete.",
      );
      expect(readiness).toHaveTextContent("Review context");
      expect(readiness).toHaveTextContent("Counsel caveat included");
      expect(readiness).toHaveTextContent("Export caveats");
      expect(readiness).toHaveTextContent("Blocked");
      expect(readiness).toHaveTextContent(
        "Readiness verification has not loaded yet.",
      );
      expect(readiness).toHaveTextContent(
        "Persisted legal review status is pending, not approved.",
      );
      expect(readiness).not.toHaveTextContent("All ready");
      expect(reviewDetailsButton).toHaveAttribute("aria-expanded", "false");
      expect(reviewDetailsButton).toHaveTextContent("Review details");
      expect(reviewDetailsButton).toHaveTextContent(
        "Readiness brief and receipt preview",
      );
      expect(reviewDetailsButton).toHaveTextContent("3 blockers");
      expect(
        screen.queryByRole("region", { name: "Export readiness brief" }),
      ).not.toBeInTheDocument();
      expect(
        screen.queryByRole("region", { name: "Export manifest preview" }),
      ).not.toBeInTheDocument();

      const reviewDetails = openReviewDetails();
      const readinessBrief = screen.getByRole("region", {
        name: "Export readiness brief",
      });
      expect(readinessBrief).toHaveTextContent("Resolve blockers");
      expect(readinessBrief).toHaveTextContent("Full Report");
      expect(readinessBrief).toHaveTextContent("PDF Report");
      expect(readinessBrief).toHaveTextContent("4/4 content");
      expect(readinessBrief).toHaveTextContent(
        "export remains gated by persisted counsel review",
      );
      expect(readinessBrief).toHaveTextContent("Counsel handoff prompts");
      expect(readinessBrief).toHaveTextContent(
        "Export readiness unavailable: Readiness verification has not loaded yet.",
      );
      expect(reviewDetails).toHaveTextContent(
        "Receipt preview before generation",
      );
      expect(decisionSummary).toHaveTextContent("Artifact");
      expect(decisionSummary).toHaveTextContent("Full Report · PDF Report");
      expect(decisionSummary).toHaveTextContent(
        "4/4 content sections; 6 total sections.",
      );
      expect(decisionSummary).toHaveTextContent("Review");
      expect(decisionSummary).toHaveTextContent("Counsel review required");
      expect(decisionSummary).toHaveTextContent("Sources");
      expect(decisionSummary).toHaveTextContent("Caveated");
      expect(decisionSummary).toHaveTextContent("Reliance gate");
      expect(decisionSummary).toHaveTextContent("Resolve blockers");
      expect(
        screen.getByRole("button", { name: "Copy readiness brief" }),
      ).toBeInTheDocument();
      expect(
        screen.getByRole("button", { name: "Copy readiness brief" }),
      ).toHaveClass("min-h-11");

      const manifest = screen.getByRole("region", {
        name: "Export manifest preview",
      });
      expect(manifest).toHaveTextContent("Receipt preview before generation");
      expect(manifest).toHaveTextContent(
        "The final receipt is created after Praviar renders and hashes the file.",
      );
      expect(manifest).toHaveTextContent("Full Report · PDF Report");
      expect(manifest).toHaveTextContent("Persisted legal review pending");
      expect(manifest).toHaveTextContent("pubchem_sdq: ok");
      expect(manifest).toHaveTextContent("patcid: failed");
      expect(manifest).toHaveTextContent(
        "Source caveat requires acknowledgement",
      );
      expect(manifest).toHaveTextContent("Internal export file");
      expect(manifest).toHaveTextContent(
        "Exported files do not inherit recipient verification, read-only controls, view limits, or revocation.",
      );
      expect(manifest).toHaveTextContent("Backend readiness not confirmed");
      expect(manifest).toHaveTextContent("6 sections");
      expect(
        screen.getByRole("button", { name: "Copy manifest" }),
      ).toBeInTheDocument();
      expect(screen.getByRole("button", { name: "Copy manifest" })).toHaveClass(
        "min-h-11",
      );
    });

    it("keeps export dialog icon controls at accessible target size", () => {
      render(<ExportDialog {...defaultProps} />);

      expect(
        screen.getByRole("button", { name: "Close export dialog" }),
      ).toHaveClass("h-11", "w-11");
      openReviewDetails();
      expect(
        screen.getByRole("button", { name: "Copy readiness brief" }),
      ).toHaveClass("min-h-11");
      expect(screen.getByRole("button", { name: "Copy manifest" })).toHaveClass(
        "min-h-11",
      );
    });

    it("requires acknowledgement before exporting with source-health caveats", () => {
      render(
        <ExportDialog
          {...readyProps}
          report={
            {
              ...TEST_REPORT,
              source_health: {
                entries: [
                  { source: "pubchem", status: "ok", patent_count: 4 },
                  { source: "bigquery", status: "failed", patent_count: 0 },
                  { source: "patcid", status: "skipped", patent_count: 0 },
                  {
                    source: "surechembl",
                    status: "not_configured",
                    patent_count: 0,
                  },
                ],
              },
            } as any
          }
        />,
      );

      const readiness = screen.getByRole("region", {
        name: "Export readiness",
      });
      expect(readiness).toHaveTextContent("Caveated");
      expect(readiness).toHaveTextContent("Counsel-approved");
      expect(readiness).toHaveTextContent(
        "Acknowledge source caveats before export or sharing.",
      );
      expect(readiness).toHaveTextContent(
        "1 failed, 1 skipped, 1 not configured, 1 not reported; coverage may be incomplete.",
      );
      expect(
        screen.queryByRole("alert", { name: "Export blockers" }),
      ).not.toBeInTheDocument();
      const exportButton = screen.getByRole("button", {
        name: "Acknowledge caveats",
      });
      expect(exportButton).toBeDisabled();
      const reasonId = exportButton.getAttribute("aria-describedby");
      expect(reasonId).toBeTruthy();
      expect(document.getElementById(reasonId ?? "")).toHaveTextContent(
        "Acknowledge source audit caveats before exporting this packet.",
      );
      openReviewDetails();
      expect(
        screen.getByRole("region", { name: "Export readiness brief" }),
      ).toHaveTextContent("Acknowledge caveats");

      fireEvent.click(
        screen.getByRole("checkbox", {
          name: /I confirm this export preserves the source coverage caveat/i,
        }),
      );

      expect(
        screen.getByRole("region", { name: "Export readiness brief" }),
      ).toHaveTextContent("Export with caveat");
      const acknowledgedExportButton = screen.getByRole("button", {
        name: "Export packet",
      });
      expect(acknowledgedExportButton).toBeEnabled();
      expect(acknowledgedExportButton).not.toHaveAttribute("aria-describedby");
    });

    it("copies the readiness brief with packet context", async () => {
      render(<ExportDialog {...defaultProps} />);
      openReviewDetails();

      await act(async () => {
        fireEvent.click(
          screen.getByRole("button", { name: "Copy readiness brief" }),
        );
      });

      expect(mockClipboardWriteText).toHaveBeenCalledWith(
        expect.stringContaining("Praviar export readiness brief"),
      );
      expect(mockClipboardWriteText).toHaveBeenCalledWith(
        expect.stringContaining(`Report: ${TEST_REPORT.report_id}`),
      );
      expect(mockClipboardWriteText).toHaveBeenCalledWith(
        expect.stringContaining("Format: PDF Report"),
      );
      expect(mockClipboardWriteText).toHaveBeenCalledWith(
        expect.stringContaining(
          "Export readiness unavailable: Readiness verification has not loaded yet.",
        ),
      );
      expect(mockAddToast).toHaveBeenCalledWith(
        "Readiness brief copied",
        "success",
      );
    });

    it("copies the export manifest preview with audit context", async () => {
      render(
        <ExportDialog
          {...readyProps}
          shareActive
          shareLastViewedAt="2026-04-24T12:30:00.000Z"
          shareRecipientBound
          shareViewCount={7}
        />,
      );
      openReviewDetails();

      await act(async () => {
        fireEvent.click(screen.getByRole("button", { name: "Copy manifest" }));
      });

      expect(mockClipboardWriteText).toHaveBeenCalledWith(
        expect.stringContaining("Praviar export manifest preview"),
      );
      expect(mockClipboardWriteText).toHaveBeenCalledWith(
        expect.stringContaining(`Report: ${TEST_REPORT.report_id}`),
      );
      expect(mockClipboardWriteText).toHaveBeenCalledWith(
        expect.stringContaining("Pipeline: 0.9.4"),
      );
      expect(mockClipboardWriteText).toHaveBeenCalledWith(
        expect.stringContaining("Artifact: Full Report · PDF Report"),
      );
      expect(mockClipboardWriteText).toHaveBeenCalledWith(
        expect.stringContaining(
          "Review ledger: Approved; 4 / 4 findings reviewed; 4 accepted",
        ),
      );
      expect(mockClipboardWriteText).toHaveBeenCalledWith(
        expect.stringContaining(
          "Reviewer: Counsel at 2026-04-24T10:00:00.000Z",
        ),
      );
      expect(mockClipboardWriteText).toHaveBeenCalledWith(
        expect.stringContaining("Source records: pubchem_sdq: ok"),
      );
      expect(mockClipboardWriteText).toHaveBeenCalledWith(
        expect.stringContaining("patcid: ok"),
      );
      expect(mockClipboardWriteText).toHaveBeenCalledWith(
        expect.stringContaining("Backend gate: Backend ready"),
      );
      expect(mockClipboardWriteText).toHaveBeenCalledWith(
        expect.stringContaining(
          "Distribution posture: Share active; export separate",
        ),
      );
      expect(mockClipboardWriteText).toHaveBeenCalledWith(
        expect.stringContaining(
          "External share active; access is bound to a mailbox-verified recipient; 7 views; last viewed 2026-04-24T12:30:00.000Z",
        ),
      );
      expect(mockClipboardWriteText).toHaveBeenCalledWith(
        expect.stringContaining(
          "Exported files do not inherit recipient verification, read-only controls, view limits, or revocation.",
        ),
      );
      expect(mockAddToast).toHaveBeenCalledWith(
        "Export manifest copied",
        "success",
      );
    });

    it("enables export only when counsel mode, backend readiness, and legal review are approved", () => {
      render(
        <ExportDialog
          {...defaultProps}
          report={sourceReadyReport}
          reviewerDecisions={completeReviewerDecisions}
          reviewStatus={
            {
              analysis_id: "analysis-1",
              status: "approved",
              note: null,
              reviewer_name: "Counsel",
              reviewer_email: "counsel@example.test",
              reviewed_at: "2026-04-24T10:00:00.000Z",
              updated_at: "2026-04-24T10:00:00.000Z",
              decision_counts: { accept: 4, reject: 0, edit: 0 },
              findings_total: 4,
              findings_reviewed: 4,
              completion_pct: 100,
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
            } as any
          }
        />,
      );

      const readiness = screen.getByRole("region", {
        name: "Export readiness",
      });
      expect(readiness).toHaveTextContent("Final check");
      expect(readiness).toHaveTextContent("Approved");
      expect(readiness).toHaveTextContent("Backend ready");
      expect(
        screen.getByText(
          "AI scoped evidence and blockers; counsel review recorded.",
        ),
      ).toBeInTheDocument();
      expect(
        screen.getByRole("button", { name: "Export packet" }),
      ).toBeEnabled();
      openReviewDetails();
      const readinessBrief = screen.getByRole("region", {
        name: "Export readiness brief",
      });
      expect(readinessBrief).toHaveTextContent("Ready for final check");
      expect(readinessBrief).toHaveTextContent("Full Report");
      expect(readinessBrief).toHaveTextContent("PDF Report");
    });

    it("blocks export while readiness checks are still loading", () => {
      render(
        <ExportDialog
          {...defaultProps}
          reviewStatusLoading
          workspaceSummaryLoading
        />,
      );

      const readiness = screen.getByRole("region", {
        name: "Export readiness",
      });
      expect(readiness).toHaveTextContent("Verifying");
      expect(readiness).toHaveTextContent(
        "Readiness checks are still loading; export starts after verification completes.",
      );
      expect(readiness).toHaveTextContent(
        "Review status verification in progress",
      );
      expect(readiness).toHaveTextContent("Readiness verification in progress");
      expect(readiness).not.toHaveTextContent(
        "Known readiness blockers must be resolved before export.",
      );

      expect(
        screen.getByRole("status", { name: "Export blockers" }),
      ).toHaveTextContent("Readiness verification in progress");
      expect(
        screen.queryByRole("alert", { name: "Export blockers" }),
      ).not.toBeInTheDocument();
      const exportButton = screen.getByRole("button", {
        name: "Resolve blockers",
      });
      expect(exportButton).toBeDisabled();
      const reasonId = exportButton.getAttribute("aria-describedby");
      expect(reasonId).toBeTruthy();
      expect(document.getElementById(reasonId ?? "")).toHaveTextContent(
        "Wait for readiness verification before exporting.",
      );
      expect(document.getElementById(reasonId ?? "")).toHaveTextContent(
        "Wait for persisted legal review verification before exporting.",
      );
    });

    it("blocks export when the workspace is not in counsel trust mode", () => {
      render(
        <ExportDialog
          {...defaultProps}
          reviewStatus={
            {
              status: "approved",
              findings_total: 4,
              findings_reviewed: 4,
            } as any
          }
          workspaceSummary={
            {
              trust_mode: "explorer",
              opinion_readiness: {
                export_ready: true,
                summary: "Export-grade caveats are preserved.",
                jurisdictions_blocking_export: [],
              },
            } as any
          }
        />,
      );

      const readiness = screen.getByRole("region", {
        name: "Export readiness",
      });
      expect(readiness).toHaveTextContent("Blocked");
      expect(readiness).toHaveTextContent(
        "Current trust mode is explorer, not counsel.",
      );
      expect(
        screen.getByRole("alert", { name: "Export blockers" }),
      ).toHaveTextContent("Current trust mode is explorer, not counsel.");
      const exportButton = screen.getByRole("button", {
        name: "Resolve blockers",
      });
      expect(exportButton).toBeDisabled();
      const reasonId = exportButton.getAttribute("aria-describedby");
      expect(reasonId).toBeTruthy();
      expect(document.getElementById(reasonId ?? "")).toHaveTextContent(
        "Current trust mode is explorer, not counsel.",
      );
    });

    it("blocks export when workspace opinion readiness is closed", async () => {
      render(
        <ExportDialog
          {...defaultProps}
          reviewStatus={
            {
              status: "approved",
              findings_total: 4,
              findings_reviewed: 4,
            } as any
          }
          workspaceSummary={
            {
              trust_mode: "counsel",
              opinion_readiness: {
                export_ready: false,
                summary:
                  "Counsel export remains blocked until jurisdictions are reviewed.",
                jurisdictions_blocking_export: ["US", "EP"],
              },
            } as any
          }
        />,
      );

      const readiness = screen.getByRole("region", {
        name: "Export readiness",
      });
      expect(readiness).toHaveTextContent("Blocked");
      expect(readiness).toHaveTextContent(
        "Known readiness blockers must be resolved before export.",
      );
      expect(readiness).toHaveTextContent("US, EP lanes block export.");

      expect(
        screen.getByRole("alert", { name: "Export blockers" }),
      ).toHaveTextContent("US, EP lanes block export.");
      const exportButton = screen.getByRole("button", {
        name: "Resolve blockers",
      });
      expect(exportButton).toBeDisabled();

      await act(async () => {
        fireEvent.click(exportButton);
      });
      expect(mockMutateAsync).not.toHaveBeenCalled();
    });
  });

  describe("format options", () => {
    it("renders all six format options", () => {
      render(<ExportDialog {...defaultProps} />);
      expect(screen.getAllByText("PDF Report").length).toBeGreaterThanOrEqual(
        1,
      );
      expect(screen.getByText("Word Review Memo")).toBeInTheDocument();
      expect(screen.getByText("Board Deck")).toBeInTheDocument();
      expect(screen.getByText("CSV Data")).toBeInTheDocument();
      expect(screen.getByText("Excel Spreadsheet")).toBeInTheDocument();
      expect(screen.getByText("JSON Data")).toBeInTheDocument();
    });

    it("renders format descriptions", () => {
      render(<ExportDialog {...defaultProps} />);
      expect(
        screen.getByText(
          "Human-readable report with charts, tables, and annotations.",
        ),
      ).toBeInTheDocument();
      expect(
        screen.getByText(
          "Editable counsel work product with citations and caveats.",
        ),
      ).toBeInTheDocument();
      expect(
        screen.getByText(
          "Presentation-ready decision brief for board and investor review.",
        ),
      ).toBeInTheDocument();
      expect(
        screen.getByText(
          "Flat evidence tables for review queues and BI tools.",
        ),
      ).toBeInTheDocument();
      expect(
        screen.getByText(
          "Structured data with claim charts, metrics, and mappings.",
        ),
      ).toBeInTheDocument();
      expect(
        screen.getByText(
          "Machine-readable data for integration and downstream use.",
        ),
      ).toBeInTheDocument();
    });

    it("PDF is selected by default", () => {
      render(<ExportDialog {...defaultProps} />);
      const group = screen.getByRole("radiogroup", {
        name: "Export format",
      });
      const pdfButton = screen.getByRole("radio", { name: /PDF Report/ });

      expect(group).toBeInTheDocument();
      expect(pdfButton).toHaveAttribute("aria-checked", "true");
      expect(pdfButton.className).toContain("border-brand-primary");
    });

    it("clicking a different format selects it", () => {
      render(<ExportDialog {...defaultProps} />);
      const jsonButton = screen.getByRole("radio", { name: /JSON Data/ });
      fireEvent.click(jsonButton);
      expect(jsonButton).toHaveAttribute("aria-checked", "true");
      expect(jsonButton.className).toContain("border-brand-primary");
    });

    it("deselects previous format when a new one is chosen", () => {
      render(<ExportDialog {...defaultProps} />);
      const jsonButton = screen.getByRole("radio", { name: /JSON Data/ });
      fireEvent.click(jsonButton);

      const pdfButton = screen.getByRole("radio", { name: /PDF Report/ });
      expect(pdfButton).toHaveAttribute("aria-checked", "false");
      expect(pdfButton.className).not.toContain("border-brand-primary");
    });

    it("supports roving keyboard navigation inside the format radiogroup", () => {
      render(<ExportDialog {...readyProps} />);

      const pdfButton = screen.getByRole("radio", { name: /PDF Report/ });
      const csvButton = screen.getByRole("radio", { name: /CSV Data/ });
      const jsonButton = screen.getByRole("radio", { name: /JSON Data/ });

      expect(pdfButton).toHaveAttribute("aria-checked", "true");
      expect(pdfButton).toHaveAttribute("tabindex", "0");
      expect(csvButton).toHaveAttribute("tabindex", "-1");

      pdfButton.focus();
      fireEvent.keyDown(pdfButton, { key: "ArrowDown" });

      expect(
        screen.getByRole("radio", { name: /Word Review Memo/ }),
      ).toHaveAttribute("aria-checked", "true");

      fireEvent.keyDown(
        screen.getByRole("radio", { name: /Word Review Memo/ }),
        { key: "End" },
      );

      expect(jsonButton).toHaveAttribute("aria-checked", "true");
      expect(jsonButton).toHaveFocus();

      fireEvent.keyDown(jsonButton, { key: "Home" });

      expect(pdfButton).toHaveAttribute("aria-checked", "true");
      expect(pdfButton).toHaveFocus();
    });
  });

  describe("audience selector", () => {
    it("renders audience options as a radiogroup", () => {
      render(<ExportDialog {...defaultProps} />);

      const group = screen.getByRole("radiogroup", {
        name: "Report Audience",
      });
      const counsel = screen.getByRole("radio", {
        name: "Patent Counsel",
      });

      expect(group).toBeInTheDocument();
      expect(counsel).toHaveAttribute("aria-checked", "false");
      fireEvent.click(counsel);
      expect(counsel).toHaveAttribute("aria-checked", "true");
      expect(
        screen.getByText(
          "Review packet with claim charts, prosecution-history notes, and invalidity screening cues for counsel.",
        ),
      ).toBeInTheDocument();
      expect(
        screen.getByRole("region", { name: "Export decision summary" }),
      ).toHaveTextContent("Patent Counsel · PDF Report");
    });

    it("supports roving keyboard navigation inside the audience radiogroup", () => {
      render(<ExportDialog {...readyProps} />);

      const fullReport = screen.getByRole("radio", { name: "Full Report" });
      const executive = screen.getByRole("radio", {
        name: "Executive Brief",
      });
      const investor = screen.getByRole("radio", { name: "Investor Pack" });

      expect(fullReport).toHaveAttribute("aria-checked", "true");
      fullReport.focus();
      fireEvent.keyDown(fullReport, { key: "ArrowRight" });

      expect(executive).toHaveAttribute("aria-checked", "true");
      expect(executive).toHaveFocus();

      fireEvent.keyDown(executive, { key: "End" });

      expect(investor).toHaveAttribute("aria-checked", "true");
      expect(investor).toHaveFocus();
    });

    it("restores and locks required packet sections for the selected audience", () => {
      render(<ExportDialog {...readyProps} />);

      const claimCharts = screen.getByRole("checkbox", {
        name: /Claim Charts/,
      }) as HTMLInputElement;
      fireEvent.click(claimCharts);
      expect(claimCharts.checked).toBe(false);

      fireEvent.click(screen.getByRole("radio", { name: "Patent Counsel" }));

      expect(claimCharts.checked).toBe(true);
      expect(claimCharts).toBeDisabled();
      expect(
        screen.getAllByText("Required for audience").length,
      ).toBeGreaterThan(0);
      expect(
        screen.getByRole("region", { name: "Audience packet requirements" }),
      ).toHaveTextContent(
        "Counsel packet keeps material patents, claim charts, and validity posture with mandatory provenance.",
      );
    });

    it("applies a compact executive packet scope by default", () => {
      render(<ExportDialog {...readyProps} />);

      fireEvent.click(screen.getByRole("radio", { name: "Executive Brief" }));

      expect(screen.getByText("4 of 6 sections selected")).toBeInTheDocument();
      expect(
        screen.getByRole("checkbox", { name: /Executive Summary/ }),
      ).toBeChecked();
      expect(
        screen.getByRole("checkbox", { name: /Patent Analysis/ }),
      ).toBeChecked();
      expect(
        screen.getByRole("checkbox", { name: /Claim Charts/ }),
      ).not.toBeChecked();
      expect(
        screen.getByRole("checkbox", { name: /Invalidity Assessment/ }),
      ).not.toBeChecked();
      expect(
        screen.getByRole("region", { name: "Export decision summary" }),
      ).toHaveTextContent("2/4 content sections; 4 total sections.");
    });

    it("applies a counsel packet scope with validity posture by default", () => {
      render(<ExportDialog {...readyProps} />);

      fireEvent.click(screen.getByRole("radio", { name: "Patent Counsel" }));

      expect(screen.getByText("5 of 6 sections selected")).toBeInTheDocument();
      expect(
        screen.getByRole("checkbox", { name: /Executive Summary/ }),
      ).not.toBeChecked();
      expect(
        screen.getByRole("checkbox", { name: /Patent Analysis/ }),
      ).toBeDisabled();
      expect(
        screen.getByRole("checkbox", { name: /Claim Charts/ }),
      ).toBeDisabled();
      expect(
        screen.getByRole("checkbox", { name: /Invalidity Assessment/ }),
      ).toBeChecked();
      expect(
        screen.getByRole("region", { name: "Export decision summary" }),
      ).toHaveTextContent("3/4 content sections; 5 total sections.");
    });

    it("applies the verified claim-chart DOCX recipe through the export queue", async () => {
      mockMutateAsync.mockResolvedValue({ job_id: "job-claim-chart-docx" });
      render(<ExportDialog {...readyProps} />);

      fireEvent.click(
        screen.getByRole("button", { name: "Use verified packet" }),
      );

      expect(
        screen.getByRole("region", { name: "Verified claim-chart packet" }),
      ).toHaveTextContent("Verified claim-chart DOCX");
      expect(
        screen.getByRole("region", { name: "Verified claim-chart packet" }),
      ).toHaveTextContent("Counsel-role Word Review Memo");
      expect(
        screen.getByRole("button", { name: "Packet selected" }),
      ).toBeInTheDocument();
      expect(
        screen.getByRole("radio", { name: /Word Review Memo/ }),
      ).toHaveAttribute("aria-checked", "true");
      expect(
        screen.getByRole("radio", { name: "Patent Counsel" }),
      ).toHaveAttribute("aria-checked", "true");
      expect(
        screen.getByRole("checkbox", { name: /Claim Charts/ }),
      ).toBeChecked();
      expect(
        screen.getByRole("checkbox", { name: /Claim Charts/ }),
      ).toBeDisabled();
      expect(
        screen.getByRole("checkbox", { name: /Invalidity Assessment/ }),
      ).not.toBeChecked();

      const exportButton = screen.getByRole("button", {
        name: "Generate verified claim-chart DOCX",
      });
      await act(async () => {
        fireEvent.click(exportButton);
      });

      expect(mockMutateAsync).toHaveBeenCalledWith(
        expect.objectContaining({
          report_id: "report-456",
          format: "docx",
          audience: "attorney",
        }),
      );
      const payload = mockMutateAsync.mock.calls[0]?.[0];
      expect(payload.sections).toHaveLength(4);
      expect(new Set(payload.sections)).toEqual(
        new Set([
          "patent_analysis",
          "claim_charts",
          "audit_trail",
          "pipeline_metadata",
        ]),
      );
    });

    it("disables attorney-only export formats for scientist users before submit", () => {
      render(<ExportDialog {...readyProps} currentUserRole="scientist" />);

      const pdfOption = screen.getByRole("radio", { name: /PDF Report/ });
      const docxOption = screen.getByRole("radio", {
        name: /Word Review Memo/,
      });
      const pptxOption = screen.getByRole("radio", { name: /Board Deck/ });

      expect(pdfOption).not.toBeDisabled();
      expect(pdfOption).toHaveAttribute("aria-checked", "true");
      expect(docxOption).toBeDisabled();
      expect(pptxOption).toBeDisabled();
      expect(
        screen.getAllByText(
          /Attorney\/admin only\. Use PDF, CSV, XLSX, or JSON/i,
        ).length,
      ).toBeGreaterThanOrEqual(2);

      fireEvent.click(docxOption);

      expect(docxOption).toHaveAttribute("aria-checked", "false");
      expect(pdfOption).toHaveAttribute("aria-checked", "true");
      const verifiedShortcut = screen.getByRole("button", {
        name: "Use verified packet",
      });
      expect(verifiedShortcut).toBeDisabled();

      fireEvent.click(verifiedShortcut);
      expect(mockMutateAsync).not.toHaveBeenCalled();
    });

    it("fails closed when the Praviar export role is unavailable", () => {
      render(<ExportDialog {...readyProps} currentUserRole={null} />);

      const pdfOption = screen.getByRole("radio", { name: /PDF Report/ });
      const docxOption = screen.getByRole("radio", {
        name: /Word Review Memo/,
      });
      const pptxOption = screen.getByRole("radio", { name: /Board Deck/ });
      const csvOption = screen.getByRole("radio", { name: /CSV Data/ });
      const xlsxOption = screen.getByRole("radio", {
        name: /Excel Spreadsheet/,
      });
      const jsonOption = screen.getByRole("radio", { name: /JSON Data/ });

      for (const option of [
        pdfOption,
        docxOption,
        pptxOption,
        csvOption,
        xlsxOption,
        jsonOption,
      ]) {
        expect(option).toBeDisabled();
      }
      expect(
        screen.getAllByText(
          /Export role unavailable\. Refresh access before preparing a packet\./i,
        ).length,
      ).toBeGreaterThanOrEqual(1);
      expect(
        screen.getByRole("button", { name: "Choose another format" }),
      ).toBeDisabled();
      expect(
        screen.getByRole("button", { name: "Use verified packet" }),
      ).toBeDisabled();
    });

    it("shows a pending role confirmation instead of final role-denied copy", () => {
      render(
        <ExportDialog
          {...readyProps}
          currentUserRole={null}
          currentUserRoleState="loading"
        />,
      );

      expect(
        screen.getByRole("status", { name: "Export role confirmation" }),
      ).toHaveTextContent("Confirming export role");
      expect(
        screen.getAllByText(
          /Confirming export role before preparing a packet\./i,
        ).length,
      ).toBeGreaterThanOrEqual(1);
      expect(
        screen.queryByText(
          /Export role unavailable\. Refresh access before preparing a packet\./i,
        ),
      ).not.toBeInTheDocument();
      expect(
        screen.getByRole("button", { name: "Confirming role" }),
      ).toBeDisabled();
    });

    it("offers a metadata retry state when report role metadata fails to load", () => {
      const onRetry = vi.fn();

      render(
        <ExportDialog
          {...readyProps}
          currentUserRole={null}
          currentUserRoleState="unavailable"
          onRefreshCurrentUserRole={onRetry}
        />,
      );

      expect(
        screen.getByRole("alert", { name: "Export metadata retry" }),
      ).toHaveTextContent("Report metadata unavailable");
      expect(
        screen.getAllByText(
          /Report metadata unavailable\. Retry report access before preparing a packet\./i,
        ).length,
      ).toBeGreaterThanOrEqual(1);
      expect(
        screen.queryByText(
          /Export role unavailable\. Refresh access before preparing a packet\./i,
        ),
      ).not.toBeInTheDocument();
      fireEvent.click(
        screen.getByRole("button", { name: "Retry report access" }),
      );
      expect(onRetry).toHaveBeenCalledOnce();
    });

    it("does not promise a claim-chart DOCX when the report has no claim rows", () => {
      render(<ExportDialog {...readyProps} report={noClaimChartReport} />);

      const shortcut = screen.getByRole("region", {
        name: "Verified claim-chart packet",
      });
      expect(shortcut).toHaveTextContent("no claim-chart rows yet");

      const shortcutButton = screen.getByRole("button", {
        name: "No claim charts",
      });
      expect(shortcutButton).toBeDisabled();
      fireEvent.click(shortcutButton);

      expect(
        screen.queryByRole("button", {
          name: "Generate verified claim-chart DOCX",
        }),
      ).not.toBeInTheDocument();
      expect(mockMutateAsync).not.toHaveBeenCalled();
    });

    it("removes the special claim-chart label when users broaden the recipe", () => {
      render(<ExportDialog {...readyProps} />);

      fireEvent.click(
        screen.getByRole("button", { name: "Use verified packet" }),
      );
      fireEvent.click(
        screen.getByRole("checkbox", { name: /Invalidity Assessment/ }),
      );

      expect(
        screen.queryByRole("button", {
          name: "Generate verified claim-chart DOCX",
        }),
      ).not.toBeInTheDocument();
      expect(
        screen.getByRole("button", { name: "Export packet" }),
      ).toBeInTheDocument();
      expect(
        screen.getByRole("button", { name: "Use verified packet" }),
      ).toBeInTheDocument();
    });
  });

  describe("section checkboxes", () => {
    it("renders all section options", () => {
      render(<ExportDialog {...defaultProps} />);
      expect(
        screen.getByRole("checkbox", { name: /Executive Summary/ }),
      ).toBeInTheDocument();
      expect(
        screen.getByRole("checkbox", { name: /Patent Analysis/ }),
      ).toBeInTheDocument();
      expect(
        screen.getByRole("checkbox", { name: /Claim Charts/ }),
      ).toBeInTheDocument();
      expect(
        screen.getByRole("checkbox", { name: /Invalidity Assessment/ }),
      ).toBeInTheDocument();
      expect(
        screen.getByRole("checkbox", { name: /Audit Trail/ }),
      ).toBeInTheDocument();
      expect(
        screen.getByRole("checkbox", { name: /Pipeline Metadata/ }),
      ).toBeInTheDocument();
    });

    it("default-on sections are checked initially", () => {
      render(<ExportDialog {...defaultProps} />);
      const checkboxes = screen.getAllByRole("checkbox");
      // All sections default on so provenance travels with counsel packets.
      const checked = checkboxes.filter(
        (cb) => (cb as HTMLInputElement).checked,
      );
      expect(checked).toHaveLength(6);
    });

    it("provenance-heavy sections are checked initially", () => {
      render(<ExportDialog {...defaultProps} />);
      const auditCheckbox = screen.getByRole("checkbox", {
        name: /Audit Trail/,
      }) as HTMLInputElement;
      expect(auditCheckbox.checked).toBe(true);

      const metadataCheckbox = screen.getByRole("checkbox", {
        name: /Pipeline Metadata/,
      }) as HTMLInputElement;
      expect(metadataCheckbox.checked).toBe(true);
      expect(
        screen.getByText(
          "Defaults include provenance, review posture, and run metadata for downstream reliance review.",
        ),
      ).toBeInTheDocument();
    });

    it("shows correct section count text", () => {
      render(<ExportDialog {...defaultProps} />);
      expect(screen.getByText("6 of 6 sections selected")).toBeInTheDocument();
    });

    it("toggling a section off decreases the count", () => {
      render(<ExportDialog {...defaultProps} />);
      const summaryCheckbox = screen.getByRole("checkbox", {
        name: /Executive Summary/,
      });
      fireEvent.click(summaryCheckbox);
      expect(screen.getByText("5 of 6 sections selected")).toBeInTheDocument();
    });

    it("keeps provenance-heavy sections locked on for governed packets", () => {
      render(<ExportDialog {...defaultProps} />);
      const auditCheckbox = screen.getByRole("checkbox", {
        name: /Audit Trail/,
      }) as HTMLInputElement;
      const metadataCheckbox = screen.getByRole("checkbox", {
        name: /Pipeline Metadata/,
      }) as HTMLInputElement;

      expect(auditCheckbox).toBeDisabled();
      expect(metadataCheckbox).toBeDisabled();
      fireEvent.click(auditCheckbox);
      expect(auditCheckbox.checked).toBe(true);
      expect(screen.getByText("6 of 6 sections selected")).toBeInTheDocument();
      expect(screen.getAllByText("Required").length).toBeGreaterThanOrEqual(2);
    });

    it("toggling a section off and on again re-selects it", () => {
      render(<ExportDialog {...defaultProps} />);
      const claimCheckbox = screen.getByRole("checkbox", {
        name: /Claim Charts/,
      }) as HTMLInputElement;

      fireEvent.click(claimCheckbox);
      expect(claimCheckbox.checked).toBe(false);

      fireEvent.click(claimCheckbox);
      expect(claimCheckbox.checked).toBe(true);
    });
  });

  describe("export button", () => {
    it("renders the blocker-resolution button while export is not ready", () => {
      render(<ExportDialog {...defaultProps} />);
      expect(
        screen.getByRole("button", { name: "Resolve blockers" }),
      ).toBeInTheDocument();
    });

    it("uses warning tone for warning disabled reasons", () => {
      render(
        <ExportDialogActions
          disabledReason="Lane certification is still pending."
          disabledTone="warning"
          isDisabled
          isProcessing={false}
          onClose={vi.fn()}
          onExport={vi.fn()}
        />,
      );

      expect(
        screen.getByText("Lane certification is still pending."),
      ).toHaveClass("text-warning");
      expect(
        screen.getByText("Lane certification is still pending."),
      ).not.toHaveClass("text-error");
    });

    it("export button is enabled when sections are selected", () => {
      render(<ExportDialog {...readyProps} />);
      const exportButton = screen.getByRole("button", {
        name: "Export packet",
      });
      expect(exportButton).not.toBeDisabled();
    });

    it("export button is disabled when only required provenance sections remain", () => {
      render(<ExportDialog {...defaultProps} />);

      const optionalSectionLabels = [
        "Executive Summary",
        "Patent Analysis",
        "Claim Charts",
        "Invalidity Assessment",
      ];
      for (const label of optionalSectionLabels) {
        const checkbox = screen.getByRole("checkbox", {
          name: new RegExp(label),
        });
        fireEvent.click(checkbox);
      }

      expect(screen.getByText("2 of 6 sections selected")).toBeInTheDocument();
      expect(
        screen.getByText(/Select at least one report content section/i),
      ).toBeInTheDocument();
      const exportButton = screen.getByRole("button", {
        name: "Resolve blockers",
      });
      expect(exportButton).toBeDisabled();
    });

    it("blocks otherwise-ready exports when the packet has no report content section", () => {
      render(<ExportDialog {...readyProps} />);

      for (const label of [
        "Executive Summary",
        "Patent Analysis",
        "Claim Charts",
        "Invalidity Assessment",
      ]) {
        fireEvent.click(
          screen.getByRole("checkbox", { name: new RegExp(label) }),
        );
      }

      expect(screen.getByText("2 of 6 sections selected")).toBeInTheDocument();
      expect(
        screen.getByRole("button", { name: "Complete packet scope" }),
      ).toBeDisabled();
      const exportButton = screen.getByRole("button", {
        name: "Complete packet scope",
      });
      const reasonId = exportButton.getAttribute("aria-describedby");
      expect(reasonId).toBeTruthy();
      expect(document.getElementById(reasonId ?? "")).toHaveTextContent(
        "Select at least one report content section before exporting",
      );
    });

    it("calls mutateAsync with correct payload when Export is clicked", async () => {
      mockMutateAsync.mockResolvedValue({ job_id: "job-789" });
      render(<ExportDialog {...readyProps} />);

      const exportButton = screen.getByRole("button", {
        name: "Export packet",
      });
      await act(async () => {
        fireEvent.click(exportButton);
      });

      expect(mockMutateAsync).toHaveBeenCalledWith(
        expect.objectContaining({
          report_id: "report-456",
          format: "pdf",
          sections: expect.arrayContaining([
            "executive_summary",
            "patent_analysis",
            "claim_charts",
            "invalidity_assessment",
            "audit_trail",
            "pipeline_metadata",
          ]),
        }),
      );
    });

    it("calls mutateAsync with selected format", async () => {
      mockMutateAsync.mockResolvedValue({ job_id: "job-789" });
      render(<ExportDialog {...readyProps} />);

      // Select JSON format
      const jsonButton = screen.getByText("JSON Data").closest("button")!;
      fireEvent.click(jsonButton);
      openReviewDetails();
      expect(
        screen.getByRole("region", { name: "Export readiness brief" }),
      ).toHaveTextContent("JSON Data");
      expect(
        screen.getByRole("region", { name: "Export decision summary" }),
      ).toHaveTextContent("Full Report · JSON Data");

      const exportButton = screen.getByRole("button", {
        name: "Export packet",
      });
      await act(async () => {
        fireEvent.click(exportButton);
      });

      expect(mockMutateAsync).toHaveBeenCalledWith(
        expect.objectContaining({
          format: "json",
        }),
      );
    });

    it("locks verified DOCX packet controls when the backend forbids export", async () => {
      mockMutateAsync.mockRejectedValue(
        new APIError(403, "Scientists can export PDF, JSON, CSV, or XLSX"),
      );
      render(<ExportDialog {...readyProps} />);

      fireEvent.click(
        screen.getByRole("button", { name: "Use verified packet" }),
      );
      await act(async () => {
        fireEvent.click(
          screen.getByRole("button", {
            name: "Generate verified claim-chart DOCX",
          }),
        );
      });

      expect(
        screen.getByRole("alert", { name: "Export access restricted" }),
      ).toHaveTextContent("Packet controls and stale job state are locked");
      expect(
        screen.getByRole("button", { name: "Access restricted" }),
      ).toBeDisabled();
      expect(mockAddToast).toHaveBeenCalledWith(
        "Export access restricted. Packet controls are locked until access is restored.",
        "error",
      );
    });

    it("locks non-claim-chart forbidden export details without leaking them", async () => {
      mockMutateAsync.mockRejectedValue(
        new APIError(403, "Clients cannot export full reports"),
      );
      render(<ExportDialog {...readyProps} />);

      await act(async () => {
        fireEvent.click(screen.getByRole("button", { name: "Export packet" }));
      });

      expect(
        screen.getByRole("alert", { name: "Export access restricted" }),
      ).toHaveTextContent("Packet controls and stale job state are locked");
      expect(mockAddToast).toHaveBeenCalledWith(
        "Export access restricted. Packet controls are locked until access is restored.",
        "error",
      );
      const toastMessages = mockAddToast.mock.calls.map(([message]) => message);
      expect(toastMessages.join(" ")).not.toContain(
        "Clients cannot export full reports",
      );
    });
  });

  describe("cancel button", () => {
    it("renders the Cancel button", () => {
      render(<ExportDialog {...defaultProps} />);
      expect(screen.getByText("Cancel")).toBeInTheDocument();
    });

    it("calls onClose when Cancel is clicked", () => {
      const onClose = vi.fn();
      render(<ExportDialog {...defaultProps} onClose={onClose} />);
      fireEvent.click(screen.getByText("Cancel"));
      expect(onClose).toHaveBeenCalled();
    });
  });

  describe("overlay", () => {
    it("portals above page-local stacking contexts", () => {
      const { container } = render(
        <div data-testid="local-stack">
          <ExportDialog {...defaultProps} />
        </div>,
      );
      const dialog = screen.getByRole("dialog", {
        name: "Export evidence packet",
      });

      expect(container.querySelector('[role="dialog"]')).toBeNull();
      expect(dialog.parentElement?.parentElement).toBe(document.body);
    });

    it("pads the scroll body so the footer never crops readiness content", () => {
      render(<ExportDialog {...defaultProps} />);
      const dialog = screen.getByRole("dialog", {
        name: "Export evidence packet",
      });

      expect(dialog.querySelector(".overflow-y-auto")).toHaveClass(
        "pb-24",
        "sm:pb-28",
      );
    });

    it("calls onClose when clicking the backdrop overlay", () => {
      const onClose = vi.fn();
      render(<ExportDialog {...defaultProps} onClose={onClose} />);
      const overlay = document.body.querySelector(".praviar-overlay-scrim");

      expect(overlay).not.toBeNull();
      fireEvent.click(overlay!);
      expect(onClose).toHaveBeenCalled();
    });
  });

  describe("success toast on export", () => {
    it("shows success toast after starting export", async () => {
      mockMutateAsync.mockResolvedValue({ job_id: "job-789" });
      render(<ExportDialog {...readyProps} />);

      const exportButton = screen.getByRole("button", {
        name: "Export packet",
      });
      await act(async () => {
        fireEvent.click(exportButton);
      });

      await vi.waitFor(() => {
        expect(mockAddToast).toHaveBeenCalledWith(
          expect.stringContaining("Export started"),
          "success",
        );
      });
    });

    it("redacts unexpected export start failure details", async () => {
      const consoleSpy = vi
        .spyOn(console, "error")
        .mockImplementation(() => {});
      mockMutateAsync.mockRejectedValueOnce(
        new Error(
          "postgres://internal-db/export failed with token sk_live_secret",
        ),
      );
      render(<ExportDialog {...readyProps} />);

      await act(async () => {
        fireEvent.click(screen.getByRole("button", { name: "Export packet" }));
      });

      await vi.waitFor(() => {
        expect(mockAddToast).toHaveBeenCalledWith(
          "Export failed — please try again. If this repeats, use your deployment operator's approved support channel.",
          "error",
        );
      });
      const toastMessages = mockAddToast.mock.calls.map(([message]) => message);
      expect(toastMessages.join(" ")).not.toContain("postgres://internal-db");
      expect(toastMessages.join(" ")).not.toContain("sk_live_secret");
      const diagnosticOutput = JSON.stringify(consoleSpy.mock.calls);
      expect(diagnosticOutput).not.toContain("postgres://internal-db");
      expect(diagnosticOutput).not.toContain("sk_live_secret");
      expect(diagnosticOutput).toContain("Export could not be started");
    });

    it("locks packet controls when export access is revoked", async () => {
      mockMutateAsync.mockRejectedValueOnce(
        new APIError(
          403,
          "postgres://internal-db/export forbidden with token sk_live_secret",
        ),
      );
      const consoleSpy = vi
        .spyOn(console, "error")
        .mockImplementation(() => {});

      render(<ExportDialog {...readyProps} />);

      await act(async () => {
        fireEvent.click(screen.getByRole("button", { name: "Export packet" }));
      });

      await vi.waitFor(() => {
        expect(
          screen.getByRole("alert", { name: "Export access restricted" }),
        ).toHaveTextContent("Packet controls and stale job state are locked");
      });
      expect(
        screen.getByRole("button", { name: "Access restricted" }),
      ).toBeDisabled();
      expect(mockAddToast).toHaveBeenCalledWith(
        "Export access restricted. Packet controls are locked until access is restored.",
        "error",
      );
      const toastMessages = mockAddToast.mock.calls.map(([message]) => message);
      expect(toastMessages.join(" ")).not.toContain("postgres://internal-db");
      expect(toastMessages.join(" ")).not.toContain("sk_live_secret");
      expect(consoleSpy).not.toHaveBeenCalled();

      consoleSpy.mockRestore();
    });

    it("blocks packet export when approved review is missing reviewer decisions", () => {
      render(<ExportDialog {...readyProps} reviewerDecisions={undefined} />);

      expect(
        screen.getByRole("alert", { name: "Export blockers" }),
      ).toHaveTextContent("Reviewer decisions unavailable");
      expect(
        screen.getByRole("button", { name: "Resolve blockers" }),
      ).toBeDisabled();

      fireEvent.click(screen.getByRole("button", { name: "Resolve blockers" }));
      expect(mockMutateAsync).not.toHaveBeenCalled();
    });
  });

  describe("failed export status", () => {
    it("redacts worker-provided failure diagnostics", () => {
      mockExportStatusData.value = {
        job_id: "job-failed",
        status: "failed",
        format: "pdf",
        error_message:
          "Traceback: postgres://internal-db/export failed with token sk_live_secret",
      };

      render(<ExportDialog {...defaultProps} />);

      expect(
        screen
          .getAllByRole("alert")
          .some((alert) =>
            alert.textContent?.includes(
              "Export failed. Please review readiness and try again. If this repeats, use the operator-approved support channel for your deployment.",
            ),
          ),
      ).toBe(true);
      expect(
        screen.getByText(/Export failed\. Please review readiness/i),
      ).toBeInTheDocument();
      expect(
        screen.queryByText(/postgres:\/\/internal-db/i),
      ).not.toBeInTheDocument();
      expect(screen.queryByText(/sk_live_secret/i)).not.toBeInTheDocument();
    });

    it("shows retrying copy for retryable worker failures", () => {
      mockExportStatusData.value = {
        job_id: "job-retryable",
        status: "processing",
        format: "pdf",
        retryable: true,
        retry_after_seconds: 12,
      };

      render(<ExportDialog {...defaultProps} />);

      expect(screen.getByRole("status")).toHaveTextContent(
        "Export hit a temporary worker issue",
      );
      expect(
        screen.getByText(/Export hit a temporary worker issue/),
      ).toBeInTheDocument();
      expect(
        screen.getByText(/Retrying in about 12 seconds/),
      ).toBeInTheDocument();
      expect(
        screen.queryByText("Export failed: See worker logs for traceback"),
      ).not.toBeInTheDocument();
    });
  });

  describe("completed export status", () => {
    it("shows the prepared artifact size without rounding it to zero", async () => {
      mockExportStatusData.value = {
        job_id: "job-small-completed",
        status: "completed",
        format: "pdf",
        download_url: "praviar-demo-export:v1:attorney:pdf",
        file_size_bytes: 512,
        artifact_sha256: "b".repeat(64),
      };

      render(<ExportDialog {...defaultProps} />);

      await screen.findByRole("link", {
        name: "Download verified packet",
      });
      expect(
        screen.getAllByText(/\d(?:[\d,.]*)(?: B| kB| MB)$/).length,
      ).toBeGreaterThan(0);
      expect(screen.queryByText("0 kB")).not.toBeInTheDocument();
      expect(
        screen.queryByRole("button", { name: "Export packet" }),
      ).not.toBeInTheDocument();
      expect(screen.getByRole("button", { name: "Close" })).toBeInTheDocument();
    });

    it("refuses to mark an empty protected artifact ready", async () => {
      const originalCreateObjectUrl = URL.createObjectURL;
      const createObjectUrl = vi.fn(() => "blob:must-not-be-created");
      Object.defineProperty(URL, "createObjectURL", {
        configurable: true,
        value: createObjectUrl,
      });
      vi.stubGlobal(
        "fetch",
        vi.fn().mockResolvedValue(
          new Response(new Uint8Array(), {
            status: 200,
            headers: { "Content-Type": "application/json" },
          }),
        ),
      );
      mockExportStatusData.value = {
        job_id: "job-empty-artifact",
        status: "completed",
        format: "json",
        download_url:
          "/api/v1/exports/123e4567-e89b-42d3-a456-426614174000/download",
        file_size_bytes: 0,
      };

      try {
        render(<ExportDialog {...defaultProps} />);

        expect(
          await screen.findByText(
            "Export is ready, but the secure download could not be prepared.",
          ),
        ).toBeInTheDocument();
        expect(createObjectUrl).not.toHaveBeenCalled();
        expect(
          screen.queryByRole("link", { name: /download/i }),
        ).not.toBeInTheDocument();
      } finally {
        vi.unstubAllGlobals();
        Object.defineProperty(URL, "createObjectURL", {
          configurable: true,
          value: originalCreateObjectUrl,
        });
      }
    });

    it("shows a recovery alert when a completed export has no download link", () => {
      mockExportStatusData.value = {
        job_id: "job-completed-no-link",
        status: "completed",
        format: "pdf",
      };

      render(<ExportDialog {...defaultProps} />);

      expect(
        screen.getByText(/Export finished, but no download link was returned/i),
      ).toBeInTheDocument();
      expect(
        screen.queryByRole("link", {
          name: "Export ready — click to download",
        }),
      ).not.toBeInTheDocument();
    });

    it("announces receipt copy failure instead of claiming success", async () => {
      mockClipboardWriteText.mockRejectedValueOnce(
        new Error("clipboard blocked"),
      );
      Object.defineProperty(document, "execCommand", {
        configurable: true,
        value: vi.fn().mockReturnValue(false),
      });
      mockExportStatusData.value = {
        job_id: "job-copy-failure",
        status: "completed",
        format: "pdf",
        download_url: "praviar-demo-export:v1:attorney:pdf",
        artifact_sha256: "b".repeat(64),
        manifest_hash: "a".repeat(64),
        report_payload_sha256: "c".repeat(64),
      };

      render(<ExportDialog {...defaultProps} />);
      const copyReceiptButton = await screen.findByRole("button", {
        name: "Copy receipt",
      });
      expect(copyReceiptButton).toHaveClass("min-h-11");
      expect(screen.getByText("Receipt sealed")).toHaveClass(
        "text-success-emphasis",
      );
      await act(async () => {
        fireEvent.click(copyReceiptButton);
      });

      expect(screen.queryByText("Receipt copied")).not.toBeInTheDocument();
      expect(
        await screen.findByText(
          "Receipt could not be copied. Select the hashes manually.",
          {},
          { timeout: 3_000 },
        ),
      ).toHaveAttribute("role", "status");
    });

    it("prepares a governed local demo artifact with a real filename and revokes it", async () => {
      mockExportStatusData.value = {
        job_id: "job-demo-completed",
        status: "completed",
        format: "pdf",
        download_url: "praviar-demo-export:v1:attorney:pdf",
      };

      const { unmount } = render(<ExportDialog {...defaultProps} />);

      const download = await screen.findByRole("link", {
        name: "Export ready — click to download",
      });
      expect(download).toHaveAttribute("href", "blob:praviar-demo-artifact");
      expect(download).toHaveAttribute("download", "praviar-demo-attorney.pdf");
      expect(URL.createObjectURL).toHaveBeenCalledWith(
        expect.objectContaining({ type: "application/pdf" }),
      );
      expect(screen.getByTitle("Export Preview")).toBeInTheDocument();
      unmount();
      expect(URL.revokeObjectURL).toHaveBeenCalledWith(
        "blob:praviar-demo-artifact",
      );
    });

    it.each([
      "https://downloads.example.test/packet.pdf",
      "http://downloads.example.test/packet.pdf",
      "//downloads.example.test/packet.pdf",
      "javascript:alert(1)",
      "data:text/html,hostile",
      "file:///etc/passwd",
      "blob:https://praviar.io/api-supplied",
      "/demo-exports/report-456.pdf",
      "praviar-demo-export:v1:attorney:html",
      "praviar-demo-export:v1:unknown:pdf",
      "/demo-exports/javascript%3Aalert(1)",
      "/demo-exports/%2F%2Fevil.example/packet.pdf",
    ])(
      "fails closed without an anchor or PDF preview for %s",
      (downloadUrl) => {
        mockExportStatusData.value = {
          job_id: "job-hostile-download",
          status: "completed",
          format: "pdf",
          download_url: downloadUrl,
        };

        render(<ExportDialog {...defaultProps} />);

        expect(
          screen
            .getByText(
              "Export finished, but its download link did not pass security validation.",
            )
            .closest('[role="alert"]'),
        ).not.toBeNull();
        expect(
          screen.queryByRole("link", {
            name: /download|export ready/i,
          }),
        ).not.toBeInTheDocument();
        expect(screen.queryByTitle("Export Preview")).not.toBeInTheDocument();
      },
    );

    it("prepares protected downloads with auth and shows the PDF preview", async () => {
      const originalCreateObjectUrl = URL.createObjectURL;
      const originalRevokeObjectUrl = URL.revokeObjectURL;
      const pdfBytes = new Uint8Array(3145728);
      pdfBytes.set(new TextEncoder().encode("%PDF-1.7"));
      const fetchMock = vi.fn().mockResolvedValue(
        new Response(pdfBytes, {
          status: 200,
          headers: { "Content-Type": "application/pdf" },
        }),
      );
      Object.defineProperty(URL, "createObjectURL", {
        configurable: true,
        value: vi.fn(() => "blob:praviar-export-preview"),
      });
      Object.defineProperty(URL, "revokeObjectURL", {
        configurable: true,
        value: vi.fn(),
      });
      vi.stubGlobal("fetch", fetchMock);
      mockExportStatusData.value = {
        job_id: "job-completed",
        status: "completed",
        format: "pdf",
        download_url:
          "/api/v1/exports/123e4567-e89b-42d3-a456-426614174000/download",
        file_size_bytes: 3145728,
        manifest_schema_version: "export-manifest-v1",
        manifest_hash: "a".repeat(64),
        manifest_snapshot: {
          artifact: {
            file_size_bytes: 3145728,
            format: "pdf",
            sections: ["executive_summary", "patent_analysis", "audit_trail"],
            title: "Full Report · PDF Report",
          },
          readiness: {
            export_ready: true,
            review_status: "approved",
          },
          source_health: {
            healthy_count: 4,
            total_count: 4,
          },
        },
        artifact_sha256: "b".repeat(64),
        report_payload_sha256: "c".repeat(64),
        completed_at: "2026-07-04T15:40:00.000Z",
      };

      try {
        render(<ExportDialog {...defaultProps} />);

        expect(screen.getByRole("status")).toHaveTextContent(
          "Preparing secure download...",
        );
        const download = await screen.findByRole("link", {
          name: "Download verified packet",
        });

        expect(fetchMock).toHaveBeenCalledWith(
          expect.stringContaining(
            "/api/v1/exports/123e4567-e89b-42d3-a456-426614174000/download",
          ),
          expect.objectContaining({
            headers: expect.objectContaining({
              Authorization: "Bearer dev-token",
            }),
          }),
        );
        expect(screen.getByRole("status")).toHaveTextContent(
          "Download verified packet",
        );
        expect(download).toHaveAttribute("href", "blob:praviar-export-preview");
        await waitFor(() => expect(download).toHaveFocus());
        const receipt = screen.getByRole("region", {
          name: "Export verification receipt",
        });
        expect(screen.getByText("Evidence packet ready")).toBeInTheDocument();
        expect(
          screen.getAllByText("Full Report · PDF Report").length,
        ).toBeGreaterThan(0);
        expect(screen.getAllByText("3.0 MB").length).toBeGreaterThan(0);
        expect(receipt).toHaveTextContent("Verification receipt");
        expect(receipt).toHaveTextContent("3 sections sealed");
        expect(receipt).toHaveTextContent("4 / 4 sources healthy");
        expect(receipt).toHaveTextContent("Counsel review recorded");
        expect(receipt).toHaveTextContent("Export ready");
        expect(receipt).toHaveTextContent("Artifact SHA-256");
        expect(receipt).toHaveTextContent("b".repeat(64));
        expect(receipt).toHaveTextContent("Manifest SHA-256");
        expect(receipt).toHaveTextContent("a".repeat(64));
        expect(receipt).toHaveTextContent("Report payload SHA-256");
        expect(receipt).toHaveTextContent("c".repeat(64));
        expect(receipt).toHaveTextContent(
          "AI-assisted screening; counsel review required before reliance.",
        );
        await act(async () => {
          fireEvent.click(screen.getByRole("button", { name: "Copy receipt" }));
        });
        expect(mockClipboardWriteText).toHaveBeenCalledWith(
          expect.stringContaining("Praviar export verification receipt"),
        );
        expect(mockClipboardWriteText).toHaveBeenCalledWith(
          expect.stringContaining("Artifact: Full Report · PDF Report"),
        );
        expect(screen.getByTitle("Export Preview")).toBeInTheDocument();
      } finally {
        vi.unstubAllGlobals();
        Object.defineProperty(URL, "createObjectURL", {
          configurable: true,
          value: originalCreateObjectUrl,
        });
        Object.defineProperty(URL, "revokeObjectURL", {
          configurable: true,
          value: originalRevokeObjectUrl,
        });
      }
    });

    it("does not create a protected-download object URL after unmount", async () => {
      let resolveFetch: ((response: Response) => void) | undefined;
      const fetchMock = vi.fn(
        () =>
          new Promise<Response>((resolve) => {
            resolveFetch = resolve;
          }),
      );
      vi.stubGlobal("fetch", fetchMock);
      mockExportStatusData.value = {
        job_id: "job-unmounted-download",
        status: "completed",
        format: "pdf",
        download_url:
          "/api/v1/exports/123e4567-e89b-42d3-a456-426614174000/download",
      };

      try {
        const { unmount } = render(<ExportDialog {...defaultProps} />);
        expect(fetchMock).toHaveBeenCalledOnce();
        unmount();

        await act(async () => {
          resolveFetch?.(
            new Response("%PDF-1.7", {
              status: 200,
              headers: { "Content-Type": "application/pdf" },
            }),
          );
          await Promise.resolve();
          await Promise.resolve();
        });

        expect(URL.createObjectURL).not.toHaveBeenCalled();
      } finally {
        vi.unstubAllGlobals();
      }
    });

    it("does not embed an authenticated non-PDF response in a same-origin blob iframe", async () => {
      const originalCreateObjectUrl = URL.createObjectURL;
      const originalRevokeObjectUrl = URL.revokeObjectURL;
      const createObjectUrl = vi.fn(() => "blob:must-not-be-created");
      Object.defineProperty(URL, "createObjectURL", {
        configurable: true,
        value: createObjectUrl,
      });
      Object.defineProperty(URL, "revokeObjectURL", {
        configurable: true,
        value: vi.fn(),
      });
      vi.stubGlobal(
        "fetch",
        vi.fn().mockResolvedValue(
          new Response(
            "<script>parent.postMessage(document.cookie, '*')</script>",
            {
              status: 200,
              headers: { "Content-Type": "text/html" },
            },
          ),
        ),
      );
      mockExportStatusData.value = {
        job_id: "job-hostile-pdf-response",
        status: "completed",
        format: "pdf",
        download_url:
          "/api/v1/exports/123e4567-e89b-42d3-a456-426614174000/download",
      };

      try {
        render(<ExportDialog {...defaultProps} />);

        expect(
          await screen.findByText(
            "Export is ready, but the secure download could not be prepared.",
          ),
        ).toBeInTheDocument();
        expect(createObjectUrl).not.toHaveBeenCalled();
        expect(screen.queryByTitle("Export Preview")).not.toBeInTheDocument();
      } finally {
        vi.unstubAllGlobals();
        Object.defineProperty(URL, "createObjectURL", {
          configurable: true,
          value: originalCreateObjectUrl,
        });
        Object.defineProperty(URL, "revokeObjectURL", {
          configurable: true,
          value: originalRevokeObjectUrl,
        });
      }
    });

    it("labels completed verified claim-chart DOCX downloads explicitly", async () => {
      mockExportStatusData.value = {
        job_id: "job-claim-chart-docx",
        status: "completed",
        format: "docx",
        download_url: "praviar-demo-export:v1:attorney:docx",
        manifest_schema_version: "export-manifest-v1",
        manifest_hash: "d".repeat(64),
        artifact_sha256: "e".repeat(64),
        report_payload_sha256: "f".repeat(64),
        completed_at: "2026-07-04T15:40:00.000Z",
      };

      render(<ExportDialog {...readyProps} />);

      fireEvent.click(
        screen.getByRole("button", { name: "Use verified packet" }),
      );

      const download = await screen.findByRole("link", {
        name: "Download verified claim-chart DOCX",
      });
      expect(download).toHaveAttribute("href", "blob:praviar-demo-artifact");
      expect(download).toHaveAttribute(
        "download",
        "praviar-demo-attorney.docx",
      );
      expect(
        screen.getByRole("region", { name: "Export verification receipt" }),
      ).toHaveTextContent("Manifest SHA-256");
    });
  });
});
