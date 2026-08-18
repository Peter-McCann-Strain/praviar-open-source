import {
  fireEvent,
  render,
  screen,
  waitFor,
  act,
} from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import React from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { ChatPanelEvidenceTab } from "@/components/report/chat-panel-evidence-tab";
import { REVIEW_HANDOFF_ERROR_MESSAGE } from "@/hooks/report-interaction-copy";
import { apiClient } from "@/lib/api-client";
import { emitAuthBoundaryChanged } from "@/lib/auth-events";

const mockUseReportEvidenceSearch = vi.fn();

vi.mock("@/lib/api-client", () => ({ apiClient: vi.fn() }));
vi.mock("@/hooks/use-auth-token", () => ({
  useAuthToken: () => "test-token",
}));
vi.mock("@/hooks/use-report-evidence-search", () => ({
  useReportEvidenceSearch: (...args: unknown[]) =>
    mockUseReportEvidenceSearch(...args),
}));

const mockApiClient = vi.mocked(apiClient);

function createWrapper() {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
      mutations: { retry: false },
    },
  });

  function Wrapper({ children }: { children: React.ReactNode }) {
    return (
      <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
    );
  }

  return { Wrapper };
}

describe("ChatPanelEvidenceTab", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockUseReportEvidenceSearch.mockReturnValue({
      data: null,
      interpretedQuery: "",
      resultQuery: "",
      failedQuery: null,
      isShowingPreviousResults: false,
      totalResults: 0,
      isSearching: false,
      error: null,
      search: vi.fn(),
      clear: vi.fn(),
    });
  });

  it("renders the governed evidence shell and report-grounded guidance", () => {
    render(<ChatPanelEvidenceTab analysisId="analysis-1" token="tok" />, {
      wrapper: createWrapper().Wrapper,
    });

    expect(screen.getByText("Evidence search")).toBeInTheDocument();
    expect(
      screen.getByRole("heading", { name: "Governed evidence search" }),
    ).toBeInTheDocument();
    expect(
      screen.getAllByText("Report-grounded evidence")[0],
    ).toBeInTheDocument();
    expect(
      screen.getByText(
        "This tab is using the current report record until governed workspace scope is available.",
      ),
    ).toBeInTheDocument();
    const retrievalMode = screen.getByRole("radiogroup", {
      name: "Evidence retrieval mode",
    });
    const reportMode = screen.getByRole("radio", { name: "Report-grounded" });
    const externalMode = screen.getByRole("radio", {
      name: "External expansion",
    });
    expect(retrievalMode).toBeInTheDocument();
    expect(reportMode).toHaveAttribute("aria-checked", "true");
    expect(externalMode).toHaveAttribute("aria-checked", "false");
    expect(reportMode).toHaveClass("min-h-11");
    expect(externalMode).toHaveClass("min-h-11");
    const searchButton = screen.getByRole("button", {
      name: "Search report evidence",
    });
    expect(searchButton).toBeEnabled();
    expect(searchButton).toHaveClass("min-h-11");
    expect(
      screen.getByText(
        "Report-grounded search stays inside collected report artifacts, provenance, and evidence logs; no fresh external retrieval runs in this mode.",
      ),
    ).toBeInTheDocument();
    expect(externalMode).toBeDisabled();
    const clearButton = screen.getByRole("button", { name: "Clear" });
    expect(clearButton).toBeDisabled();
    expect(clearButton).toHaveClass("min-h-11");
    expect(
      screen.getByRole("button", {
        name: "Which evidence items are most relevant?",
      }),
    ).toHaveClass("min-h-11");
  });

  it("seeds and runs a URL-provided report evidence query", async () => {
    const search = vi.fn().mockResolvedValue(undefined);
    mockUseReportEvidenceSearch.mockReturnValue({
      data: null,
      interpretedQuery: "",
      resultQuery: "",
      failedQuery: null,
      isShowingPreviousResults: false,
      totalResults: 0,
      isSearching: false,
      error: null,
      search,
      clear: vi.fn(),
    });

    render(
      <ChatPanelEvidenceTab
        analysisId="analysis-1"
        token="tok"
        initialQuery="  blocking claim elements  "
      />,
      { wrapper: createWrapper().Wrapper },
    );

    expect(screen.getByLabelText("Evidence search query")).toHaveValue(
      "blocking claim elements",
    );
    await waitFor(() => {
      expect(search).toHaveBeenCalledWith("blocking claim elements", {
        retrievalMode: "report_evidence",
      });
    });
  });

  it("blocks one-character evidence searches before hitting the backend", async () => {
    const search = vi.fn().mockResolvedValue(undefined);

    mockUseReportEvidenceSearch.mockReturnValue({
      data: null,
      interpretedQuery: "",
      resultQuery: "",
      failedQuery: null,
      isShowingPreviousResults: false,
      totalResults: 0,
      isSearching: false,
      error: null,
      search,
      clear: vi.fn(),
    });

    render(<ChatPanelEvidenceTab analysisId="analysis-1" token="tok" />, {
      wrapper: createWrapper().Wrapper,
    });

    fireEvent.change(screen.getByLabelText("Evidence search query"), {
      target: { value: "x" },
    });
    fireEvent.click(
      screen.getByRole("button", { name: "Search report evidence" }),
    );

    expect(
      await screen.findByText(
        "Enter at least 2 characters to search evidence.",
      ),
    ).toBeInTheDocument();
    expect(screen.getByLabelText("Evidence search query")).toHaveAttribute(
      "aria-invalid",
      "true",
    );
    expect(search).not.toHaveBeenCalled();
  });

  it("lets the user trigger governed external expansion distinctly from report-grounded search", async () => {
    const search = vi.fn().mockResolvedValue(undefined);

    mockUseReportEvidenceSearch.mockReturnValue({
      data: {
        scope: {
          external_live_retrieval: true,
          provider_capabilities: [
            {
              provider_id: "pubchem",
              provider_name: "PubChem SDQ",
              provider_class: "public_open",
              provider_status: "active",
              live_retrieval_supported: true,
              configured: true,
              configured_for_org: true,
              materialized_in_report: false,
              execution_mode: "live_api",
              modality_coverage: ["small_molecule"],
              jurisdiction_coverage: ["global"],
              governance_note: "Fresh PubChem retrieval is permitted.",
            },
          ],
        },
      },
      interpretedQuery: "",
      resultQuery: "",
      failedQuery: null,
      isShowingPreviousResults: false,
      totalResults: 0,
      isSearching: false,
      error: null,
      search,
      clear: vi.fn(),
    });

    render(
      <ChatPanelEvidenceTab
        analysisId="analysis-1"
        token="tok"
        workspaceMeta={{
          trust_mode: "counsel",
          mode_label: "Counsel workspace",
          capability_label: "Evidence-rich review",
          scope_label: "Full report",
          evidence_mode: "Governed evidence search",
          source_coverage: "Declared provider policy",
          tool_access: ["external_evidence_expand"],
        }}
      />,
      { wrapper: createWrapper().Wrapper },
    );

    fireEvent.keyDown(
      screen.getByRole("radiogroup", { name: "Evidence retrieval mode" }),
      { key: "End" },
    );
    expect(
      screen.getByRole("radio", { name: "External expansion" }),
    ).toHaveAttribute("aria-checked", "true");
    fireEvent.change(screen.getByLabelText("Evidence search query"), {
      target: { value: "expand to public evidence" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Expand externally" }));

    await waitFor(() => {
      expect(search).toHaveBeenCalledWith("expand to public evidence", {
        retrievalMode: "external_evidence",
      });
    });

    expect(
      screen.getByText(
        "External expansion can query only live governed provider layers declared active in this report scope.",
      ),
    ).toBeInTheDocument();
    expect(
      screen.getAllByText(
        "Live-capable provider layers are available for this workspace; execution basis is shown per provider and returned result.",
      ).length,
    ).toBeGreaterThan(0);
  });

  it("renders provider governance metadata when the backend emits capability layers", () => {
    mockUseReportEvidenceSearch.mockReturnValue({
      data: {
        interpreted_query: "find governed evidence",
        scope: {
          label: "Counsel workspace",
          mode: "Governed evidence search",
          jurisdictions: ["US", "EPC"],
          coverage: "Claims + prosecution + evidence log",
          source_name: "Hybrid evidence stack",
          artifact_type: "evidence workspace",
          status: "ready",
          summary: "Hybrid provider metadata is available.",
          governed_note:
            "Report-derived today, provider governance declared for future hybrid retrieval.",
          external_live_retrieval: true,
          provider_capabilities: [
            {
              provider_id: "report_derived",
              provider_name: "Report-derived evidence layer",
              provider_class: "report_derived",
              provider_status: "active",
              live_retrieval_supported: false,
              configured: true,
              configured_for_org: true,
              materialized_in_report: true,
              execution_mode: "report_materialized",
              modality_coverage: ["small_molecule"],
              jurisdiction_coverage: ["US", "EPC"],
              governance_note:
                "Uses report-collected artifacts and provenance only.",
              source_as_of: "Completed report snapshot",
              dataset_version: "report_record",
            },
            {
              provider_id: "licensed_overlay",
              provider_name: "Licensed overlay placeholder",
              provider_class: "licensed_overlay",
              provider_status: "active",
              live_retrieval_supported: true,
              configured: true,
              configured_for_org: true,
              materialized_in_report: false,
              execution_mode: "live_api",
              modality_coverage: ["small_molecule", "markush_candidate"],
              jurisdiction_coverage: ["US", "EPC", "JP"],
              governance_note:
                "Configured as a governed licensed overlay layer for this counsel workspace.",
              source_as_of: "Provider live endpoint",
            },
          ],
          hybrid_evidence_ready: true,
        },
        results: [],
      },
      interpretedQuery: "find governed evidence",
      totalResults: 0,
      isSearching: false,
      error: null,
      search: vi.fn(),
      clear: vi.fn(),
    });

    render(<ChatPanelEvidenceTab analysisId="analysis-1" token="tok" />, {
      wrapper: createWrapper().Wrapper,
    });

    expect(screen.getByText("Provider governance")).toBeInTheDocument();
    expect(
      screen.getByText("Hybrid evidence layers ready"),
    ).toBeInTheDocument();
    expect(
      screen.getByText("Report-derived evidence layer"),
    ).toBeInTheDocument();
    expect(
      screen.getByText("Licensed overlay placeholder"),
    ).toBeInTheDocument();
    expect(screen.getAllByText("report_derived").length).toBeGreaterThan(0);
    expect(screen.getAllByText("licensed_overlay").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Report materialized").length).toBeGreaterThan(
      0,
    );
    expect(screen.getAllByText("Live API").length).toBeGreaterThan(0);
    expect(
      screen.getAllByText("Materialized in report").length,
    ).toBeGreaterThan(0);
    expect(
      screen.getAllByText("Live retrieval eligible").length,
    ).toBeGreaterThan(0);
    expect(screen.getAllByText("Configured for org").length).toBeGreaterThan(0);
    expect(screen.getByText("Completed report snapshot")).toBeInTheDocument();
    expect(screen.getByText("report_record")).toBeInTheDocument();
    expect(screen.getByText("Provider live endpoint")).toBeInTheDocument();
    expect(screen.getAllByText("Active").length).toBeGreaterThan(0);
    expect(
      screen.getByText("Uses report-collected artifacts and provenance only."),
    ).toBeInTheDocument();
    expect(
      screen.getByText(
        "Configured as a governed licensed overlay layer for this counsel workspace.",
      ),
    ).toBeInTheDocument();
    expect(
      screen.getByText("small_molecule / markush_candidate"),
    ).toBeInTheDocument();
    expect(screen.getByText("US / EPC / JP")).toBeInTheDocument();
  });

  it("keeps external expansion disabled when only non-live overlays are declared for unsupported modalities", () => {
    mockUseReportEvidenceSearch.mockReturnValue({
      data: {
        interpreted_query: "sequence overlay governance",
        scope: {
          label: "Counsel workspace",
          mode: "report_evidence",
          jurisdictions: ["US"],
          coverage: "Report evidence plus declared overlay policy",
          source_name: "Governed provider policy",
          artifact_type: "evidence workspace",
          status: "ready",
          summary:
            "Declared overlays remain governance-only for this routing profile.",
          governed_note:
            "Licensed overlays are declared for governance review but remain non-live for this routing profile.",
          external_live_retrieval: false,
          provider_capabilities: [
            {
              provider_id: "report_derived",
              provider_name: "Report-derived evidence layer",
              provider_class: "report_derived",
              provider_status: "active",
              live_retrieval_supported: false,
              configured: true,
              configured_for_org: true,
              materialized_in_report: true,
              execution_mode: "report_materialized",
              modality_coverage: ["small_molecule"],
              jurisdiction_coverage: ["US"],
              governance_note:
                "Uses report-collected artifacts and provenance only.",
            },
            {
              provider_id: "sequence_overlay",
              provider_name: "Sequence overlay placeholder",
              provider_class: "licensed_overlay",
              provider_status: "declared_only",
              live_retrieval_supported: false,
              configured: false,
              configured_for_org: false,
              materialized_in_report: false,
              execution_mode: "placeholder_contract",
              modality_coverage: ["biologic_or_sequence"],
              jurisdiction_coverage: ["US", "EP"],
              governance_note:
                "Declared for governance only; unsupported for the current small-molecule routing profile.",
            },
          ],
          hybrid_evidence_ready: false,
        },
        results: [],
      },
      interpretedQuery: "sequence overlay governance",
      totalResults: 0,
      isSearching: false,
      error: null,
      search: vi.fn(),
      clear: vi.fn(),
    });

    render(
      <ChatPanelEvidenceTab
        analysisId="analysis-1"
        token="tok"
        workspaceMeta={{
          trust_mode: "counsel",
          mode_label: "Counsel workspace",
          capability_label: "Evidence-rich review",
          scope_label: "Full report",
          evidence_mode: "Governed evidence search",
          source_coverage: "Declared provider policy",
          tool_access: ["external_evidence_expand"],
        }}
      />,
      {
        wrapper: createWrapper().Wrapper,
      },
    );

    expect(
      screen.getByText("Hybrid evidence layers declared"),
    ).toBeInTheDocument();
    expect(
      screen.getByText(
        "Declared for governance only; unsupported for the current small-molecule routing profile.",
      ),
    ).toBeInTheDocument();
    expect(screen.getByText("biologic_or_sequence")).toBeInTheDocument();
    expect(screen.getByText("US / EP")).toBeInTheDocument();
    expect(
      screen.getByText("Hybrid evidence layers declared"),
    ).toBeInTheDocument();
    expect(screen.getByText("Declared Only")).toBeInTheDocument();
    expect(screen.getAllByText("sequence_overlay").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Declared contract").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Not configured").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Placeholder contract").length).toBeGreaterThan(
      0,
    );
    expect(
      screen.getByRole("radio", { name: "External expansion" }),
    ).toBeDisabled();
    fireEvent.keyDown(
      screen.getByRole("radiogroup", { name: "Evidence retrieval mode" }),
      { key: "End" },
    );
    expect(
      screen.getByRole("radio", { name: "External expansion" }),
    ).toHaveAttribute("aria-checked", "false");
    expect(
      screen.getByText(
        "External expansion is unavailable because no live governed provider is active for this report scope. No fresh external retrieval will run.",
      ),
    ).toBeInTheDocument();
  });

  it("renders external expansion results with mode-specific governance cues", () => {
    mockUseReportEvidenceSearch.mockReturnValue({
      data: {
        interpreted_query: "celecoxib formulation external evidence",
        scope: {
          label: "Counsel workspace",
          mode: "external_evidence",
          jurisdictions: ["US", "JP"],
          coverage: "Declared external provider policy",
          source_name: "Governed external providers",
          artifact_type: "external evidence workspace",
          status: "active",
          summary: "External expansion stayed within governed provider policy.",
          governed_note:
            "External provider retrieval is bounded to approved sources.",
          external_live_retrieval: true,
          sources_considered: ["pubchem_sdq", "patentsview"],
          provider_capabilities: [
            {
              provider_id: "pubchem",
              provider_name: "PubChem SDQ",
              provider_class: "public_open",
              provider_status: "active",
              live_retrieval_supported: true,
              configured: true,
              configured_for_org: true,
              materialized_in_report: false,
              execution_mode: "live_api",
              modality_coverage: ["small_molecule"],
              jurisdiction_coverage: ["global"],
              governance_note: "Public chemical evidence only.",
              retrieved_at: "2026-06-18T14:30:00Z",
              source_as_of: "Provider live endpoint",
            },
          ],
          hybrid_evidence_ready: true,
        },
        results: [],
      },
      interpretedQuery: "celecoxib formulation external evidence",
      totalResults: 0,
      isSearching: false,
      error: null,
      search: vi.fn(),
      clear: vi.fn(),
    });

    render(<ChatPanelEvidenceTab analysisId="analysis-1" token="tok" />, {
      wrapper: createWrapper().Wrapper,
    });

    expect(
      screen.getAllByText("Governed external expansion").length,
    ).toBeGreaterThan(0);
    expect(
      screen.getByText(
        "Live-capable provider layers are available for this workspace; execution basis is shown per provider and returned result.",
      ),
    ).toBeInTheDocument();
    expect(screen.getAllByText("pubchem").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Live API").length).toBeGreaterThan(0);
    expect(screen.getByText("2026-06-18T14:30:00Z")).toBeInTheDocument();
    expect(
      screen.getByText(
        'No governed external evidence matched "celecoxib formulation external evidence". Try broader claim language, provider names, or patent identifiers.',
      ),
    ).toBeInTheDocument();
  });

  it("sends a review handoff, shows pending and success state, and notifies the parent", async () => {
    const onReviewHandoffSuccess = vi.fn();
    let resolveHandoff:
      | ((value: {
          comment_id: string;
          review_status: string;
          escalated_to_review: boolean;
          target_type: string;
          target_id: string;
        }) => void)
      | undefined;

    mockUseReportEvidenceSearch.mockReturnValue({
      data: {
        interpreted_query: "Priority evidence for aspirin formulation",
        scope: {
          label: "Counsel workspace",
          mode: "Governed evidence search",
          jurisdictions: ["US", "EPC"],
          coverage: "Patent claims + prosecution history",
          source_name: "USPTO + EPO",
          artifact_type: "claim corpus",
          status: "complete",
          summary: "High-confidence governed scope",
        },
        results: [
          {
            result_id: "EV-US123-claim",
            title: "Aspirin formulation claim",
            summary:
              "A formulation claim recites enhanced bioavailability with stability controls.",
            source_name: "USPTO",
            authority_tier: "primary_source",
            freshness: "fresh",
            artifact_type: "claim",
            section: "claim_chart",
            patent_id: "US123",
            relevance: 0.92,
            provenance: [
              {
                label: "Record basis",
                value:
                  "Claims extracted from the issued patent and prosecution record.",
              },
            ],
            follow_up_target: {
              target_type: "patent",
              target_id: "US123",
              suggested_note: "Route this claim into counsel review.",
            },
          },
        ],
      },
      interpretedQuery: "",
      totalResults: 0,
      isSearching: false,
      error: null,
      search: vi.fn(),
      clear: vi.fn(),
    });

    mockApiClient.mockImplementationOnce(
      () =>
        new Promise((resolve) => {
          resolveHandoff = resolve;
        }),
    );

    render(
      <ChatPanelEvidenceTab
        analysisId="analysis-1"
        token="tok"
        patentId="US123"
        workspaceMeta={{
          trust_mode: "counsel",
          mode_label: "Counsel workspace",
          capability_label: "Evidence-rich review",
          scope_label: "Patent US123",
          evidence_mode: "Read-only evidence search",
          source_coverage: "Governed metadata",
          tool_access: ["report_grounded_qna", "monitor_delta_summary"],
        }}
        onReviewHandoffSuccess={onReviewHandoffSuccess}
      />,
      { wrapper: createWrapper().Wrapper },
    );

    expect(screen.getByText("Result EV-US123-claim")).toBeInTheDocument();
    expect(screen.getByText("Review-ready artifact")).toBeInTheDocument();
    expect(screen.getAllByText("92% relevance").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Primary Source").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Fresh").length).toBeGreaterThan(0);

    fireEvent.click(
      screen.getAllByRole("button", { name: "Send to review" })[0],
    );

    await waitFor(() => {
      expect(screen.getByText("Sending to review")).toBeInTheDocument();
    });

    await act(async () => {
      resolveHandoff?.({
        comment_id: "comment-123",
        review_status: {
          analysis_id: "analysis-1",
          status: "under_review",
          note: "Route this claim into counsel review.",
          reviewer_name: "Ada Lovelace",
          reviewer_email: "ada@example.com",
          reviewed_at: "2026-04-18T10:30:00Z",
          updated_at: "2026-04-18T10:30:00Z",
          decision_counts: { accept: 0, reject: 0, edit: 0 },
          findings_total: 0,
          findings_reviewed: 0,
          completion_pct: 0,
        },
        escalated_to_review: true,
        target_type: "patent",
        target_id: "US123",
      });
    });

    await waitFor(() => {
      expect(screen.getByText("Review handoff created")).toBeInTheDocument();
      expect(screen.getByText(/comment-123/i)).toBeInTheDocument();
    });

    await act(async () => {
      await new Promise((resolve) => window.setTimeout(resolve, 700));
    });

    expect(onReviewHandoffSuccess).toHaveBeenCalledWith({
      comment_id: "comment-123",
      review_status: {
        analysis_id: "analysis-1",
        status: "under_review",
        note: "Route this claim into counsel review.",
        reviewer_name: "Ada Lovelace",
        reviewer_email: "ada@example.com",
        reviewed_at: "2026-04-18T10:30:00Z",
        updated_at: "2026-04-18T10:30:00Z",
        decision_counts: { accept: 0, reject: 0, edit: 0 },
        findings_total: 0,
        findings_reviewed: 0,
        completion_pct: 0,
      },
      escalated_to_review: true,
      target_type: "patent",
      target_id: "US123",
    });

    expect(mockApiClient).toHaveBeenCalledWith(
      "/analyses/analysis-1/review-handoff",
      expect.objectContaining({
        method: "POST",
        token: "tok",
      }),
    );

    const [, handoffOptions] = mockApiClient.mock.calls[0];
    expect(JSON.parse(String(handoffOptions?.body))).toMatchObject({
      body: expect.stringContaining("Evidence result ID: EV-US123-claim"),
      review_note: "Route this claim into counsel review.",
      target_type: "patent",
      target_id: "US123",
      promote_to_under_review: true,
    });
    expect(JSON.parse(String(handoffOptions?.body)).body).toEqual(
      expect.stringContaining("Relevance: 92% relevance"),
    );
  });

  it("uses the response query in review handoff after the draft input changes", async () => {
    mockUseReportEvidenceSearch.mockReturnValue({
      data: {
        query: "aspirin",
        interpreted_query: "aspirin evidence search",
        scope: {
          label: "Counsel workspace",
          mode: "Governed evidence search",
          jurisdictions: ["US"],
          coverage: "Patent claims",
          comment_routing_available: true,
          summary: "High-confidence governed scope",
        },
        results: [
          {
            result_id: "EV-US123-query",
            title: "Aspirin formulation claim",
            summary: "A formulation claim recites enhanced bioavailability.",
            source_name: "USPTO",
            authority_tier: "primary_source",
            freshness: "fresh",
            artifact_type: "claim",
            section: "claim_chart",
            patent_id: "US123",
            relevance: 0.9,
            provenance: [
              { label: "Record basis", value: "Issued claim text." },
            ],
            follow_up_target: {
              target_type: "patent",
              target_id: "US123",
              suggested_note: "Route this claim into counsel review.",
            },
          },
        ],
      },
      interpretedQuery: "aspirin evidence search",
      resultQuery: "aspirin",
      totalResults: 1,
      isSearching: false,
      error: null,
      search: vi.fn(),
      clear: vi.fn(),
    });

    mockApiClient.mockResolvedValueOnce({
      comment_id: "comment-query",
      review_status: {
        analysis_id: "analysis-1",
        status: "under_review",
        note: "Route this claim into counsel review.",
        reviewer_name: null,
        reviewer_email: null,
        reviewed_at: null,
        updated_at: "2026-04-18T10:30:00Z",
        decision_counts: { accept: 0, reject: 0, edit: 0 },
        findings_total: 0,
        findings_reviewed: 0,
        completion_pct: 0,
      },
      escalated_to_review: true,
      target_type: "patent",
      target_id: "US123",
    });

    render(
      <ChatPanelEvidenceTab
        analysisId="analysis-1"
        token="tok"
        patentId="US123"
      />,
      { wrapper: createWrapper().Wrapper },
    );

    fireEvent.change(screen.getByLabelText("Evidence search query"), {
      target: { value: "celecoxib draft" },
    });
    fireEvent.click(
      screen.getByRole("button", {
        name: /Send to review: Aspirin formulation claim \(EV-US123-query\)/,
      }),
    );

    await waitFor(() => {
      expect(mockApiClient).toHaveBeenCalledTimes(1);
    });

    const [, handoffOptions] = mockApiClient.mock.calls[0];
    const handoffBody = JSON.parse(String(handoffOptions?.body)).body as string;
    expect(handoffBody).toContain("Search query: aspirin");
    expect(handoffBody).not.toContain("celecoxib draft");
  });

  it("does not notify the parent twice when comments are opened before the delayed success callback", async () => {
    const onReviewHandoffSuccess = vi.fn();

    mockUseReportEvidenceSearch.mockReturnValue({
      data: {
        query: "aspirin",
        interpreted_query: "aspirin evidence search",
        scope: {
          label: "Counsel workspace",
          mode: "Governed evidence search",
          jurisdictions: ["US"],
          coverage: "Patent claims",
          comment_routing_available: true,
          summary: "High-confidence governed scope",
        },
        results: [
          {
            result_id: "EV-US123-once",
            title: "Aspirin formulation claim",
            summary: "A formulation claim recites enhanced bioavailability.",
            source_name: "USPTO",
            authority_tier: "primary_source",
            freshness: "fresh",
            artifact_type: "claim",
            section: "claim_chart",
            patent_id: "US123",
            relevance: 0.9,
            provenance: [
              { label: "Record basis", value: "Issued claim text." },
            ],
            follow_up_target: {
              target_type: "patent",
              target_id: "US123",
              suggested_note: "Route this claim into counsel review.",
            },
          },
        ],
      },
      interpretedQuery: "aspirin evidence search",
      resultQuery: "aspirin",
      totalResults: 1,
      isSearching: false,
      error: null,
      search: vi.fn(),
      clear: vi.fn(),
    });

    const handoffResponse = {
      comment_id: "comment-once",
      review_status: {
        analysis_id: "analysis-1",
        status: "under_review",
        note: "Route this claim into counsel review.",
        reviewer_name: null,
        reviewer_email: null,
        reviewed_at: null,
        updated_at: "2026-04-18T10:30:00Z",
        decision_counts: { accept: 0, reject: 0, edit: 0 },
        findings_total: 0,
        findings_reviewed: 0,
        completion_pct: 0,
      },
      escalated_to_review: true,
      target_type: "patent",
      target_id: "US123",
    };

    mockApiClient.mockResolvedValueOnce(handoffResponse);

    render(
      <ChatPanelEvidenceTab
        analysisId="analysis-1"
        token="tok"
        patentId="US123"
        onReviewHandoffSuccess={onReviewHandoffSuccess}
      />,
      { wrapper: createWrapper().Wrapper },
    );

    fireEvent.click(
      screen.getByRole("button", {
        name: /Send to review: Aspirin formulation claim \(EV-US123-once\)/,
      }),
    );

    await waitFor(() => {
      expect(screen.getByText("Review handoff created")).toBeInTheDocument();
    });

    fireEvent.click(screen.getByRole("button", { name: "Open comments tab" }));

    await act(async () => {
      await new Promise((resolve) => window.setTimeout(resolve, 700));
    });

    expect(onReviewHandoffSuccess).toHaveBeenCalledTimes(1);
    expect(onReviewHandoffSuccess).toHaveBeenCalledWith(handoffResponse);
  });

  it("honors backend comment routing policy before enabling review handoff", () => {
    mockUseReportEvidenceSearch.mockReturnValue({
      data: {
        interpreted_query: "aspirin evidence search",
        scope: {
          label: "Counsel workspace",
          mode: "Governed evidence search",
          jurisdictions: ["US"],
          coverage: "Patent claims",
          comment_routing_available: false,
          summary: "Routing is disabled for this evidence scope.",
        },
        results: [
          {
            result_id: "EV-US123-locked",
            title: "Locked routing claim",
            summary: "A traceable result that cannot be routed in this scope.",
            source_name: "USPTO",
            authority_tier: "primary_source",
            freshness: "fresh",
            artifact_type: "claim",
            section: "claim_chart",
            patent_id: "US123",
            relevance: 0.91,
            provenance: [
              { label: "Record basis", value: "Issued claim text." },
            ],
            follow_up_target: {
              target_type: "patent",
              target_id: "US123",
              suggested_note: "Route this claim into counsel review.",
            },
          },
        ],
      },
      interpretedQuery: "aspirin evidence search",
      totalResults: 1,
      isSearching: false,
      error: null,
      search: vi.fn(),
      clear: vi.fn(),
    });

    render(
      <ChatPanelEvidenceTab
        analysisId="analysis-1"
        token="tok"
        patentId="US123"
      />,
      { wrapper: createWrapper().Wrapper },
    );

    expect(screen.getAllByText("Routing unavailable").length).toBeGreaterThan(
      0,
    );
    expect(
      screen.getByText(
        "Comment routing is unavailable for this evidence scope. Review the artifact in place or refresh after routing is enabled.",
      ),
    ).toBeInTheDocument();

    const resultButton = screen.getByRole("button", {
      name: /Review routing unavailable: Locked routing claim \(EV-US123-locked\)/,
    });
    expect(resultButton).toBeDisabled();
    expect(
      screen.getByRole("button", { name: "Send to review" }),
    ).toBeDisabled();
    fireEvent.click(resultButton);
    expect(mockApiClient).not.toHaveBeenCalled();
  });

  it("shows review handoff errors", async () => {
    mockUseReportEvidenceSearch.mockReturnValue({
      data: {
        interpreted_query: "Priority evidence for aspirin formulation",
        scope: {
          label: "Counsel workspace",
          mode: "Governed evidence search",
          jurisdictions: ["US", "EPC"],
          coverage: "Patent claims + prosecution history",
          source_name: "USPTO + EPO",
          artifact_type: "claim corpus",
          status: "complete",
          summary: "High-confidence governed scope",
        },
        results: [
          {
            title: "Aspirin formulation claim",
            summary:
              "A formulation claim recites enhanced bioavailability with stability controls.",
            source_name: "USPTO",
            authority_tier: "primary_source",
            freshness: "fresh",
            artifact_type: "claim",
            section: "claim_chart",
            patent_id: "US123",
            relevance: 0.92,
            provenance: [
              {
                label: "Record basis",
                value:
                  "Claims extracted from the issued patent and prosecution record.",
              },
            ],
            follow_up_target: {
              target_type: "patent",
              target_id: "US123",
              suggested_note: "Route this claim into counsel review.",
            },
          },
        ],
      },
      interpretedQuery: "",
      totalResults: 0,
      isSearching: false,
      error: null,
      search: vi.fn(),
      clear: vi.fn(),
    });

    mockApiClient.mockRejectedValueOnce(
      new Error("postgres://secret-token review handoff failed"),
    );

    render(
      <ChatPanelEvidenceTab
        analysisId="analysis-1"
        token="tok"
        patentId="US123"
      />,
      { wrapper: createWrapper().Wrapper },
    );

    fireEvent.click(
      screen.getAllByRole("button", { name: "Send to review" })[0],
    );

    await waitFor(() => {
      expect(screen.getByText("Review handoff failed")).toBeInTheDocument();
    });
    expect(screen.getByText(REVIEW_HANDOFF_ERROR_MESSAGE)).toBeInTheDocument();
    expect(
      screen.queryByText(/postgres:\/\/secret-token/),
    ).not.toBeInTheDocument();
  });

  it("gates review handoff when a result has a target but no provenance", () => {
    mockUseReportEvidenceSearch.mockReturnValue({
      data: {
        interpreted_query: "Priority evidence for aspirin formulation",
        scope: {
          label: "Counsel workspace",
          mode: "Governed evidence search",
          jurisdictions: ["US", "EPC"],
          coverage: "Patent claims + prosecution history",
          source_name: "USPTO + EPO",
          artifact_type: "claim corpus",
          status: "complete",
          summary: "High-confidence governed scope",
        },
        results: [
          {
            result_id: "EV-US123-untraced",
            title: "Untraced formulation claim",
            summary:
              "A formulation claim appears relevant, but the source trace is missing.",
            source_name: "USPTO",
            authority_tier: "primary_source",
            freshness: "fresh",
            artifact_type: "claim",
            section: "claim_chart",
            patent_id: "US123",
            relevance: 0.88,
            provenance: [],
            follow_up_target: {
              target_type: "patent",
              target_id: "US123",
              suggested_note: "Route this claim into counsel review.",
            },
          },
        ],
      },
      interpretedQuery: "",
      totalResults: 0,
      isSearching: false,
      error: null,
      search: vi.fn(),
      clear: vi.fn(),
    });

    render(
      <ChatPanelEvidenceTab
        analysisId="analysis-1"
        token="tok"
        patentId="US123"
      />,
      { wrapper: createWrapper().Wrapper },
    );

    expect(screen.getByText("Result EV-US123-untraced")).toBeInTheDocument();
    expect(screen.getByText("Needs provenance")).toBeInTheDocument();
    expect(screen.getAllByText("88% relevance").length).toBeGreaterThan(0);
    expect(
      screen.getByText(
        "Add or refresh source provenance before routing this evidence into review. Counsel handoff is intentionally gated until the artifact can be traced.",
      ),
    ).toBeInTheDocument();

    const provenanceButton = screen.getByRole("button", {
      name: /Provenance required before sending: Untraced formulation claim \(EV-US123-untraced\)/,
    });
    expect(provenanceButton).toBeDisabled();
    fireEvent.click(provenanceButton);
    expect(mockApiClient).not.toHaveBeenCalled();
  });

  it("labels previous evidence results and blocks review handoff after a failed refresh", () => {
    mockUseReportEvidenceSearch.mockReturnValue({
      data: {
        query: "aspirin",
        interpreted_query: "aspirin evidence search",
        scope: {
          label: "Counsel workspace",
          mode: "report_evidence",
          coverage: "Patent claims + prosecution history",
          summary: "Prior successful evidence search.",
        },
        results: [
          {
            title: "Aspirin formulation claim",
            summary:
              "A formulation claim recites enhanced bioavailability with stability controls.",
            source_name: "USPTO",
            authority_tier: "primary_source",
            freshness: "fresh",
            artifact_type: "claim",
            section: "claim_chart",
            patent_id: "US123",
            provenance: [],
            follow_up_target: {
              target_type: "patent",
              target_id: "US123",
              suggested_note: "Route this claim into counsel review.",
            },
          },
        ],
      },
      interpretedQuery: "aspirin evidence search",
      resultQuery: "aspirin",
      failedQuery: "celecoxib",
      isShowingPreviousResults: true,
      totalResults: 1,
      isSearching: false,
      error: "Evidence search failed. Existing results are unchanged.",
      search: vi.fn(),
      clear: vi.fn(),
    });

    render(
      <ChatPanelEvidenceTab
        analysisId="analysis-1"
        token="tok"
        patentId="US123"
      />,
      { wrapper: createWrapper().Wrapper },
    );

    expect(
      screen.getByText("Showing previous evidence results"),
    ).toBeInTheDocument();
    expect(
      screen.getByText(
        'The search for "celecoxib" did not complete. These results are still from "aspirin" and cannot be sent to review until the search refreshes.',
      ),
    ).toBeInTheDocument();
    expect(screen.getByText("Previous interpreted query:")).toBeInTheDocument();
    expect(
      screen.getByText(
        "Refresh the failed search before routing evidence into the comments workflow.",
      ),
    ).toBeInTheDocument();

    const refreshButtons = screen.getAllByRole("button", {
      name: "Refresh required",
    });
    expect(refreshButtons.length).toBeGreaterThan(0);
    refreshButtons.forEach((button) => expect(button).toBeDisabled());
    fireEvent.click(refreshButtons[0]);
    expect(mockApiClient).not.toHaveBeenCalled();
  });

  it("clears private evidence input and retrieval mode on auth boundary changes", () => {
    mockUseReportEvidenceSearch.mockReturnValue({
      data: {
        scope: {
          external_live_retrieval: true,
          provider_capabilities: [
            {
              provider_id: "pubchem",
              provider_name: "PubChem SDQ",
              provider_class: "public_open",
              provider_status: "active",
              live_retrieval_supported: true,
              configured: true,
              configured_for_org: true,
              materialized_in_report: false,
              execution_mode: "live_api",
              modality_coverage: ["small_molecule"],
              jurisdiction_coverage: ["global"],
              governance_note: "Fresh PubChem retrieval is permitted.",
            },
          ],
        },
      },
      interpretedQuery: "",
      resultQuery: "",
      failedQuery: null,
      isShowingPreviousResults: false,
      totalResults: 0,
      isSearching: false,
      error: null,
      search: vi.fn(),
      clear: vi.fn(),
    });

    mockApiClient.mockReset();

    render(
      <ChatPanelEvidenceTab
        analysisId="analysis-1"
        token="tok"
        workspaceMeta={{
          trust_mode: "counsel",
          mode_label: "Counsel workspace",
          capability_label: "Evidence-rich review",
          scope_label: "Full report",
          evidence_mode: "Governed evidence search",
          source_coverage: "Declared provider policy",
          tool_access: ["external_evidence_expand"],
        }}
      />,
      { wrapper: createWrapper().Wrapper },
    );

    fireEvent.click(screen.getByRole("radio", { name: "External expansion" }));
    fireEvent.change(screen.getByLabelText("Evidence search query"), {
      target: { value: "private external evidence draft" },
    });

    expect(screen.getByLabelText("Evidence search query")).toHaveValue(
      "private external evidence draft",
    );
    expect(
      screen.getByText(
        "External expansion can query only live governed provider layers declared active in this report scope.",
      ),
    ).toBeInTheDocument();

    act(() => {
      emitAuthBoundaryChanged({ refreshToken: false });
    });

    expect(screen.getByLabelText("Evidence search query")).toHaveValue("");
    expect(
      screen.getByText(
        "Report-grounded search stays inside collected report artifacts, provenance, and evidence logs; no fresh external retrieval runs in this mode.",
      ),
    ).toBeInTheDocument();
  });
});
