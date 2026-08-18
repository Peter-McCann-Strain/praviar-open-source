import {
  act,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { useMemo } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { APIError } from "@/lib/api-client";

const navigationMocks = vi.hoisted(() => ({
  back: vi.fn(),
  prefetch: vi.fn(),
  push: vi.fn(),
  replace: vi.fn(),
  searchParams: new URLSearchParams(),
}));

const mockUseAuthToken = vi.fn();
const mockUsePrincipalCapabilities = vi.fn();
const mockUseReport = vi.fn();
const mockUseAnalysis = vi.fn();
const mockUseComments = vi.fn();
const mockUseAnalysisReviewStatus = vi.fn();
const mockUseReviewerDecisions = vi.fn();
const mockUseReportSearch = vi.fn();
const mockUseReportWorkspaceSummary = vi.fn();
const mockUseClaimedUseReceipts = vi.fn();
const mockUseReviewHandoff = vi.fn();
const mockAddToast = vi.fn();
const mockChatPanel = vi.fn();
const mockReportPageHeader = vi.fn();
const mockReportPageDialogs = vi.fn();
const mockReportReviewLifecycleControl = vi.fn();
const mockReportPageTabContent = vi.fn();
const mockReportSearchBar = vi.fn();

vi.mock("next/navigation", () => ({
  usePathname: () => "/analyses/ana-ready/report",
  useRouter: () => ({
    back: navigationMocks.back,
    prefetch: navigationMocks.prefetch,
    push: navigationMocks.push,
    replace: navigationMocks.replace,
  }),
  useSearchParams: () => navigationMocks.searchParams,
}));

vi.mock("@/hooks/use-auth-token", () => ({
  useAuthToken: () => mockUseAuthToken(),
}));

vi.mock("@/hooks/use-principal-capabilities", () => ({
  usePrincipalCapabilities: (...args: unknown[]) =>
    mockUsePrincipalCapabilities(...args),
}));

vi.mock("@/hooks/use-report", () => ({
  useReport: (...args: unknown[]) => mockUseReport(...args),
}));

vi.mock("@/hooks/use-analysis", () => ({
  useAnalysis: (...args: unknown[]) => mockUseAnalysis(...args),
}));

vi.mock("@/hooks/use-comments", () => ({
  useComments: (...args: unknown[]) => mockUseComments(...args),
}));

vi.mock("@/hooks/use-analysis-review-status", () => ({
  useAnalysisReviewStatus: (...args: unknown[]) =>
    mockUseAnalysisReviewStatus(...args),
}));

vi.mock("@/hooks/use-reviewer-decisions", () => ({
  useReviewerDecisions: (...args: unknown[]) =>
    mockUseReviewerDecisions(...args),
}));

vi.mock("@/hooks/use-report-search", () => ({
  useReportSearch: (...args: unknown[]) => mockUseReportSearch(...args),
}));

vi.mock("@/hooks/use-report-workspace-summary", () => ({
  useReportWorkspaceSummary: (...args: unknown[]) =>
    mockUseReportWorkspaceSummary(...args),
}));

vi.mock("@/hooks/use-claimed-use-receipts", () => ({
  useClaimedUseReceipts: (...args: unknown[]) =>
    mockUseClaimedUseReceipts(...args),
}));

vi.mock("@/hooks/use-review-handoff", () => ({
  useReviewHandoff: (...args: unknown[]) => mockUseReviewHandoff(...args),
}));

vi.mock("@/stores/toast-store", () => ({
  useToastStore: (
    selector: (state: { addToast: typeof mockAddToast }) => unknown,
  ) => selector({ addToast: mockAddToast }),
}));

vi.mock("@/components/report-page/use-report-watch-control", () => ({
  ReportWatchControlProvider: ({ children }: { children: React.ReactNode }) => (
    <>{children}</>
  ),
}));

vi.mock("@/components/report/chat-panel", () => ({
  ChatPanel: (props: any) => {
    mockChatPanel(props);
    return props.open ? (
      <aside data-testid="chat-panel">
        {props.launchContext?.title ?? "Report chat"}
        <button
          type="button"
          onClick={() =>
            props.onReviewHandoffSuccess?.({
              comment_id: "comment-chat-1",
              review_status: {
                analysis_id: "ana-ready",
                status: "under_review",
              },
              escalated_to_review: true,
              target_type: "claim",
              target_id: "US123 claim 1",
            })
          }
        >
          Complete chat review handoff
        </button>
        <button
          type="button"
          onClick={() =>
            props.onCreateReviewHandoff?.({
              body: "Generated AI brief body",
              promote_to_under_review: true,
              review_note: "Generated AI brief review note",
              target_id: "ana-ready",
              target_type: "analysis",
            })
          }
        >
          Send generated brief to review
        </button>
        <button
          type="button"
          onClick={() =>
            props.onCitationClick?.({
              cited_text: "Claim 1 covers the succinate formulation.",
              document_index: 0,
              document_title: "US1234567 claim text",
            })
          }
        >
          Open chat citation
        </button>
      </aside>
    ) : null;
  },
}));

vi.mock("@/components/report/citation-panel", () => ({
  CitationPanel: (props: any) =>
    props.citation ? (
      <aside role="dialog" aria-label="Citation source">
        <p>{props.citation.text}</p>
        <p>{props.citation.section}</p>
        {props.sourceText ? (
          <p data-testid="citation-source-text">{props.sourceText}</p>
        ) : null}
        <button type="button" onClick={props.onClose}>
          Close citation panel
        </button>
      </aside>
    ) : null,
}));

vi.mock("@/components/report-page/report-page-dialogs", () => ({
  ReportPageDialogs: (props: any) => {
    mockReportPageDialogs(props);
    return null;
  },
}));

vi.mock("@/components/report-page/report-page-header", () => ({
  ReportPageHeader: (props: any) => {
    mockReportPageHeader(props);
    return (
      <>
        <div>Report page header</div>
        {props.sectionNavigation}
        <button
          type="button"
          onClick={() =>
            props.onPrepareHandoff?.({
              body: "Readiness handoff body",
              promote_to_under_review: true,
              review_note: "Readiness handoff note",
              target_id: "ana-ready",
              target_type: "analysis",
            })
          }
        >
          Create review handoff
        </button>
        {props.reviewHandoffState?.commentId ? (
          <span>Review handoff created</span>
        ) : null}
      </>
    );
  },
}));

vi.mock("@/components/report-page/report-page-tab-content", () => ({
  ReportPageTabContent: (props: { tab?: string }) => {
    mockReportPageTabContent(props);
    return (
      <div>
        Report tab content
        {props.tab === "evidence" ? (
          <details>
            <summary>Search governed report evidence</summary>
            <input
              id="report-evidence-workbench-query"
              aria-label="Evidence search query"
            />
          </details>
        ) : null}
      </div>
    );
  },
}));

vi.mock("@/components/report-page/report-page-tabs", () => ({
  ReportPageTabs: () => <div>Report tabs</div>,
}));

vi.mock("@/components/report-page/report-review-lifecycle-control", () => ({
  ReportReviewLifecycleControl: (props: any) => {
    mockReportReviewLifecycleControl(props);
    return <div>Governed counsel review lifecycle</div>;
  },
}));

vi.mock("@/components/report-page/report-section-context-strip", () => ({
  ReportSectionContextStrip: () => <div>Report section context</div>,
}));

vi.mock("@/components/report-page/mobile-report-command-bar", () => ({
  MobileReportCommandBar: (props: any) =>
    props.chatOpen ? null : (
      <div>
        <button type="button" onClick={props.onSearch}>
          Mobile search reviewed evidence
        </button>
        <button type="button" onClick={props.onAsk}>
          Mobile verify report evidence
        </button>
      </div>
    ),
}));

vi.mock("@/components/report/report-search-bar", () => ({
  ReportSearchBar: (props: any) => {
    mockReportSearchBar(props);
    return <div>Report search bar {props.initialQuery}</div>;
  },
}));

vi.mock("@/components/report/report-search-results", () => ({
  ReportSearchResults: () => <div>Report search results</div>,
}));

import ReportPage from "@/app/(dashboard)/analyses/[id]/report/page";

type FulfilledReportParams = Promise<{ id: string }> & {
  status: "fulfilled";
  value: { id: string };
};

function createFulfilledReportParams(id: string): FulfilledReportParams {
  const params = Promise.resolve({ id }) as FulfilledReportParams;
  params.status = "fulfilled";
  params.value = { id };

  return params;
}

function ReportPageHarness({ id }: { id: string }) {
  const params = useMemo(() => createFulfilledReportParams(id), [id]);

  return <ReportPage params={params} />;
}

function renderReportContent(id: string) {
  return render(<ReportPageHarness id={id} />);
}

describe("ReportContent recovery states", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    navigationMocks.searchParams = new URLSearchParams();
    mockUseAuthToken.mockReturnValue("tok");
    mockUsePrincipalCapabilities.mockReturnValue({
      data: {
        role: "attorney",
        can_export_report: true,
        can_resolve_review: true,
      },
      isError: false,
      isFetching: false,
      isLoading: false,
      refetch: vi.fn(),
    });
    mockUseComments.mockReturnValue({ data: [] });
    mockUseAnalysisReviewStatus.mockReturnValue({ data: undefined });
    mockUseReviewerDecisions.mockReturnValue({
      data: { counts: { accept: 0, edit: 0, reject: 0 }, items: [] },
      isLoading: false,
    });
    mockUseReviewHandoff.mockReturnValue({
      isError: false,
      isPending: false,
      mutateAsync: vi.fn(),
    });
    mockAddToast.mockReset();
    mockUseReportSearch.mockReturnValue({
      clear: vi.fn(),
      error: null,
      interpretedQuery: "",
      isSearching: false,
      results: [],
      search: vi.fn(),
      totalResults: 0,
    });
    mockUseAnalysis.mockReturnValue({
      data: {
        id: "ana-404",
        status: "completed",
        current_step: 8,
        total_patents_found: 2417,
        updated_at: "2026-06-19T10:42:00Z",
      },
    });
    mockUseReportWorkspaceSummary.mockReturnValue({ data: undefined });
    mockUseClaimedUseReceipts.mockReturnValue({
      data: undefined,
      error: null,
      isError: false,
      isLoading: false,
      refetch: vi.fn(),
    });
  });

  it("keeps the rich report workspace skeleton during client report loading", () => {
    mockUseReport.mockReturnValue({
      data: undefined,
      isLoading: true,
      error: null,
      refetch: vi.fn(),
    });

    renderReportContent("ana-loading");

    expect(screen.getByText("Loading report workspace")).toHaveClass("sr-only");
    expect(
      document.querySelector("[data-praviar-report-loading-identity]"),
    ).toBeInTheDocument();
    expect(
      document.querySelector("[data-praviar-report-loading-section-rail]"),
    ).toBeInTheDocument();
    expect(
      document.querySelector("[data-praviar-report-loading-command-rail]"),
    ).toBeInTheDocument();
    expect(
      document.querySelector("[data-praviar-report-loading-decision-brief]"),
    ).toBeInTheDocument();
    expect(
      screen.queryByTestId("report-status-loading"),
    ).not.toBeInTheDocument();
    expect(mockUseComments).toHaveBeenCalledWith("ana-loading", null);
    expect(mockUseReportSearch).toHaveBeenCalledWith("ana-loading", null);
  });

  it("keeps report-only comments and search disabled while a missing report recovers", () => {
    const refetch = vi.fn();
    mockUseReport.mockReturnValue({
      data: undefined,
      isLoading: false,
      error: new APIError(404, "Report not found"),
      refetch,
    });

    renderReportContent("ana-404");

    expect(mockUseComments).toHaveBeenCalledWith("ana-404", null);
    expect(mockUseReportWorkspaceSummary).toHaveBeenCalledWith(null);
    expect(mockUseAnalysisReviewStatus).toHaveBeenCalledWith("");
    expect(mockUseReportSearch).toHaveBeenCalledWith("ana-404", null);
    expect(
      screen.getByRole("heading", { level: 1, name: "Report not available" }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "Retry report load" }),
    ).toBeInTheDocument();
    expect(screen.queryByText("Retry report build")).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Retry report load" }));
    expect(refetch).toHaveBeenCalledTimes(1);
  });

  it("does not confirm private artifacts for forbidden reports", () => {
    mockUseReport.mockReturnValue({
      data: undefined,
      isLoading: false,
      error: new APIError(403, "Forbidden"),
      refetch: vi.fn(),
    });

    renderReportContent("ana-forbidden");

    expect(mockUseComments).toHaveBeenCalledWith("ana-forbidden", null);
    expect(mockUseReportWorkspaceSummary).toHaveBeenCalledWith(null);
    expect(mockUseAnalysisReviewStatus).toHaveBeenCalledWith("");
    expect(mockUseReportSearch).toHaveBeenCalledWith("ana-forbidden", null);
    expect(
      screen.getByRole("heading", {
        level: 1,
        name: "Report access unavailable",
      }),
    ).toBeInTheDocument();
    expect(screen.queryByText("Evidence preserved")).not.toBeInTheDocument();
    expect(
      screen.queryByText(/reviewer records unchanged/i),
    ).not.toBeInTheDocument();
  });

  it("hides cached report workspace when report access is revoked", () => {
    const report = {
      report_id: "rpt-cached",
      generated_at: "2026-06-19T10:42:00Z",
      compound: { name: "cached private report" },
      risk_summary: {
        overall_risk: "high",
        blocking_patents_count: 1,
        total_patents_analyzed: 1,
      },
      patent_analyses: [],
      total_patents_found: 1,
      patents_after_triage: 1,
      source_health: { entries: [] },
      search_sources_used: [],
      clearance_decision: {},
    };

    mockUseReport.mockReturnValue({
      data: report,
      isLoading: false,
      error: new APIError(403, "Forbidden"),
      refetch: vi.fn(),
    });

    const { container } = renderReportContent("ana-cached-forbidden");

    expect(mockUseComments).toHaveBeenCalledWith("ana-cached-forbidden", null);
    expect(mockUseReportWorkspaceSummary).toHaveBeenCalledWith(null);
    expect(mockUseAnalysisReviewStatus).toHaveBeenCalledWith("");
    expect(mockUseReportSearch).toHaveBeenCalledWith(
      "ana-cached-forbidden",
      null,
    );
    expect(
      screen.getByRole("heading", {
        level: 1,
        name: "Report access unavailable",
      }),
    ).toBeInTheDocument();
    expect(screen.queryByText("cached private report")).not.toBeInTheDocument();
    expect(container.querySelector(".praviar-report-workspace")).toBeNull();
    expect(mockReportPageHeader).not.toHaveBeenCalled();
  });

  it("passes report workspace and review readiness into the authenticated header", async () => {
    const workspaceSummary = {
      analysis_id: "ana-ready",
      report_id: "rpt-ready",
      opinion_readiness: { export_ready: false },
    };
    const reviewStatus = {
      analysis_id: "ana-ready",
      status: "under_review",
      findings_total: 4,
      findings_reviewed: 2,
      completion_pct: 50,
    };
    const refetchAnalysis = vi.fn();
    const report = {
      report_id: "rpt-ready",
      generated_at: "2026-06-19T10:42:00Z",
      compound: { name: "succinic acid" },
      risk_summary: {
        overall_risk: "high",
        blocking_patents_count: 1,
        total_patents_analyzed: 1,
      },
      patent_analyses: [],
      total_patents_found: 1,
      patents_after_triage: 1,
      source_health: { entries: [] },
      search_sources_used: [],
      clearance_decision: {},
    };

    mockUseReport.mockReturnValue({
      data: report,
      isLoading: false,
      error: null,
      refetch: vi.fn(),
    });
    mockUseReportWorkspaceSummary.mockReturnValue({ data: workspaceSummary });
    mockUseAnalysisReviewStatus.mockReturnValue({ data: reviewStatus });
    mockUseAnalysis.mockReturnValue({
      data: {
        id: "ana-ready",
        status: "completed",
        current_step: 8,
        total_patents_found: 2417,
        updated_at: "2026-06-19T10:42:00Z",
        current_user_role: "scientist",
      },
      refetch: refetchAnalysis,
    });
    mockUsePrincipalCapabilities.mockReturnValue({
      data: {
        role: "attorney",
        can_export_report: true,
        can_resolve_review: true,
      },
      isError: false,
      isFetching: false,
      isLoading: false,
      refetch: vi.fn(),
    });

    const { container } = renderReportContent("ana-ready");

    expect(mockUseReportWorkspaceSummary).toHaveBeenCalledWith("ana-ready");
    expect(mockUseAnalysisReviewStatus).toHaveBeenCalledWith("ana-ready");
    expect(container.querySelector(".praviar-report-workspace")).toHaveClass(
      "overflow-x-clip",
    );
    expect(
      container.querySelector(".praviar-report-workspace"),
    ).not.toHaveClass("overflow-x-hidden");
    expect(mockReportPageHeader).toHaveBeenCalledWith(
      expect.objectContaining({
        canExportReport: true,
        reviewStatus,
        workspaceSummary,
      }),
    );
    expect(mockReportPageDialogs).toHaveBeenCalledWith(
      expect.objectContaining({
        currentUserRole: "attorney",
        currentUserRoleState: "ready",
        onShareStateRefresh: expect.any(Function),
      }),
    );
    expect(mockReportReviewLifecycleControl).toHaveBeenCalledWith(
      expect.objectContaining({
        analysisId: "ana-ready",
        status: reviewStatus,
        onRefresh: expect.any(Function),
      }),
    );

    act(() => {
      mockReportPageDialogs.mock.calls.at(-1)?.[0].onShareStateRefresh();
    });
    expect(refetchAnalysis).toHaveBeenCalledOnce();

    act(() => {
      mockReportPageHeader.mock.calls.at(-1)?.[0].onExport();
    });
    expect(mockReportPageDialogs.mock.calls.at(-1)?.[0]).toEqual(
      expect.objectContaining({ exportOpen: true }),
    );
  });

  it.each(["scientist", "client"] as const)(
    "keeps the internal counsel lifecycle restricted when the authoritative principal role is %s",
    (restrictedRole) => {
      const report = {
        report_id: "rpt-role-revoked",
        generated_at: "2026-06-19T10:42:00Z",
        compound: { name: "succinic acid" },
        risk_summary: {
          overall_risk: "medium",
          blocking_patents_count: 0,
          total_patents_analyzed: 1,
        },
        patent_analyses: [],
        total_patents_found: 1,
        patents_after_triage: 1,
        source_health: { entries: [] },
        search_sources_used: [],
        clearance_decision: {},
      };

      mockUseReport.mockReturnValue({
        data: report,
        isLoading: false,
        error: null,
        refetch: vi.fn(),
      });
      mockUseAnalysis.mockReturnValue({
        data: {
          id: "ana-role-revoked",
          status: "completed",
          current_step: 8,
          total_patents_found: 1,
          updated_at: "2026-06-19T10:42:00Z",
          current_user_role: "attorney",
        },
        refetch: vi.fn(),
      });
      mockUsePrincipalCapabilities.mockReturnValue({
        data: {
          role: restrictedRole,
          can_export_report: false,
          can_resolve_review: false,
        },
        isError: false,
        isFetching: false,
        isLoading: false,
        refetch: vi.fn(),
      });

      renderReportContent("ana-role-revoked");

      expect(mockUseReviewerDecisions).toHaveBeenCalledWith(
        "ana-role-revoked",
        null,
      );
      expect(mockUseAnalysisReviewStatus).toHaveBeenCalledWith("");
      expect(mockReportReviewLifecycleControl).not.toHaveBeenCalled();
      expect(mockReportPageTabContent).toHaveBeenCalledWith(
        expect.objectContaining({
          reviewerDecisionsUnavailable: true,
        }),
      );
      expect(mockReportPageHeader).toHaveBeenCalledWith(
        expect.objectContaining({
          canExportReport: false,
          currentUserRole: restrictedRole,
        }),
      );
      expect(mockReportPageDialogs).toHaveBeenCalledWith(
        expect.objectContaining({
          currentUserRole: restrictedRole,
          currentUserRoleState: "ready",
        }),
      );
    },
  );

  it("passes export role loading and retry state while analysis metadata resolves", () => {
    const report = {
      report_id: "rpt-ready",
      generated_at: "2026-06-19T10:42:00Z",
      compound: { name: "succinic acid" },
      risk_summary: {
        overall_risk: "medium",
        blocking_patents_count: 0,
        total_patents_analyzed: 1,
      },
      patent_analyses: [],
      total_patents_found: 1,
      patents_after_triage: 1,
      source_health: { entries: [] },
      search_sources_used: [],
      clearance_decision: {},
    };
    const refetchAnalysis = vi.fn();

    mockUseReport.mockReturnValue({
      data: report,
      isLoading: false,
      error: null,
      refetch: vi.fn(),
    });
    mockUseAnalysis.mockReturnValue({
      data: undefined,
      error: null,
      isLoading: true,
      refetch: refetchAnalysis,
    });
    mockUsePrincipalCapabilities.mockReturnValue({
      data: undefined,
      isError: false,
      isFetching: true,
      isLoading: true,
      refetch: vi.fn(),
    });

    renderReportContent("ana-ready");

    expect(mockReportPageDialogs).toHaveBeenCalledWith(
      expect.objectContaining({
        currentUserRole: undefined,
        currentUserRoleState: "loading",
        onExportRoleRetry: expect.any(Function),
      }),
    );
  });

  it("passes export role retry state when analysis metadata fails", () => {
    const report = {
      report_id: "rpt-ready",
      generated_at: "2026-06-19T10:42:00Z",
      compound: { name: "succinic acid" },
      risk_summary: {
        overall_risk: "medium",
        blocking_patents_count: 0,
        total_patents_analyzed: 1,
      },
      patent_analyses: [],
      total_patents_found: 1,
      patents_after_triage: 1,
      source_health: { entries: [] },
      search_sources_used: [],
      clearance_decision: {},
    };
    const refetchAnalysis = vi.fn();

    mockUseReport.mockReturnValue({
      data: report,
      isLoading: false,
      error: null,
      refetch: vi.fn(),
    });
    mockUseAnalysis.mockReturnValue({
      data: undefined,
      error: new Error("metadata failed"),
      isLoading: false,
      refetch: refetchAnalysis,
    });
    mockUsePrincipalCapabilities.mockReturnValue({
      data: undefined,
      isError: true,
      isFetching: false,
      isLoading: false,
      refetch: vi.fn(),
    });

    renderReportContent("ana-ready");

    expect(mockReportPageDialogs).toHaveBeenCalledWith(
      expect.objectContaining({
        currentUserRole: undefined,
        currentUserRoleState: "unavailable",
        onExportRoleRetry: expect.any(Function),
      }),
    );
  });

  it("does not open export while report role authority is still loading", () => {
    const report = {
      report_id: "rpt-ready",
      generated_at: "2026-06-19T10:42:00Z",
      compound: { name: "succinic acid" },
      risk_summary: {
        overall_risk: "medium",
        blocking_patents_count: 0,
        total_patents_analyzed: 1,
      },
      patent_analyses: [],
      total_patents_found: 1,
      patents_after_triage: 1,
      source_health: { entries: [] },
      search_sources_used: [],
      clearance_decision: {},
    };

    mockUseReport.mockReturnValue({
      data: report,
      isLoading: false,
      error: null,
      refetch: vi.fn(),
    });
    mockUseAnalysis.mockReturnValue({
      data: undefined,
      error: null,
      isFetching: true,
      isLoading: true,
      refetch: vi.fn(),
    });
    mockUsePrincipalCapabilities.mockReturnValue({
      data: undefined,
      isError: false,
      isFetching: true,
      isLoading: true,
      refetch: vi.fn(),
    });

    renderReportContent("ana-ready");

    act(() => {
      mockReportPageHeader.mock.calls.at(-1)?.[0].onExport();
    });

    expect(mockAddToast).toHaveBeenCalledWith(
      "Confirming export access. Try export again in a moment.",
      "info",
    );
    expect(mockReportPageDialogs.mock.calls.at(-1)?.[0]).toEqual(
      expect.objectContaining({ exportOpen: false }),
    );
  });

  it("retries analysis metadata instead of opening export after role load failure", () => {
    const report = {
      report_id: "rpt-ready",
      generated_at: "2026-06-19T10:42:00Z",
      compound: { name: "succinic acid" },
      risk_summary: {
        overall_risk: "medium",
        blocking_patents_count: 0,
        total_patents_analyzed: 1,
      },
      patent_analyses: [],
      total_patents_found: 1,
      patents_after_triage: 1,
      source_health: { entries: [] },
      search_sources_used: [],
      clearance_decision: {},
    };
    const refetchCapabilities = vi.fn();

    mockUseReport.mockReturnValue({
      data: report,
      isLoading: false,
      error: null,
      refetch: vi.fn(),
    });
    mockUseAnalysis.mockReturnValue({
      data: undefined,
      error: new Error("metadata failed"),
      isFetching: false,
      isLoading: false,
      refetch: vi.fn(),
    });
    mockUsePrincipalCapabilities.mockReturnValue({
      data: undefined,
      isError: true,
      isFetching: false,
      isLoading: false,
      refetch: refetchCapabilities,
    });

    renderReportContent("ana-ready");

    act(() => {
      mockReportPageHeader.mock.calls.at(-1)?.[0].onExport();
    });

    expect(mockAddToast).toHaveBeenCalledWith(
      "Export access is unavailable. Refresh capabilities before preparing a packet.",
      "error",
    );
    expect(refetchCapabilities).toHaveBeenCalledOnce();
    expect(mockReportPageDialogs.mock.calls.at(-1)?.[0]).toEqual(
      expect.objectContaining({ exportOpen: false }),
    );
  });

  it("opens export once report role authority is resolved", () => {
    const report = {
      report_id: "rpt-ready",
      generated_at: "2026-06-19T10:42:00Z",
      compound: { name: "succinic acid" },
      risk_summary: {
        overall_risk: "medium",
        blocking_patents_count: 0,
        total_patents_analyzed: 1,
      },
      patent_analyses: [],
      total_patents_found: 1,
      patents_after_triage: 1,
      source_health: { entries: [] },
      search_sources_used: [],
      clearance_decision: {},
    };

    mockUseReport.mockReturnValue({
      data: report,
      isLoading: false,
      error: null,
      refetch: vi.fn(),
    });
    mockUseAnalysis.mockReturnValue({
      data: {
        id: "ana-ready",
        status: "completed",
        current_step: 8,
        total_patents_found: 1,
        updated_at: "2026-06-19T10:42:00Z",
        current_user_role: "attorney",
      },
      error: null,
      isFetching: false,
      isLoading: false,
      refetch: vi.fn(),
    });

    renderReportContent("ana-ready");

    act(() => {
      mockReportPageHeader.mock.calls.at(-1)?.[0].onExport();
    });

    expect(mockAddToast).not.toHaveBeenCalledWith(
      expect.stringMatching(/export role/i),
      expect.any(String),
    );
    expect(mockReportPageDialogs.mock.calls.at(-1)?.[0]).toEqual(
      expect.objectContaining({
        currentUserRole: "attorney",
        currentUserRoleState: "ready",
        exportOpen: true,
      }),
    );
  });

  it("creates a readiness-console review handoff and routes to comments", async () => {
    const report = {
      report_id: "rpt-ready",
      generated_at: "2026-06-19T10:42:00Z",
      compound: { name: "succinic acid" },
      risk_summary: {
        overall_risk: "high",
        blocking_patents_count: 1,
        total_patents_analyzed: 1,
      },
      patent_analyses: [],
      total_patents_found: 1,
      patents_after_triage: 1,
      source_health: { entries: [] },
      search_sources_used: [],
      clearance_decision: {},
    };
    const mutateAsync = vi.fn().mockResolvedValue({
      comment_id: "comment-ready-1",
      review_status: {
        analysis_id: "ana-ready",
        status: "under_review",
      },
      escalated_to_review: true,
      target_type: "analysis",
      target_id: "ana-ready",
    });

    mockUseReport.mockReturnValue({
      data: report,
      isLoading: false,
      error: null,
      refetch: vi.fn(),
    });
    mockUseReviewHandoff.mockReturnValue({
      isError: false,
      isPending: false,
      mutateAsync,
    });

    renderReportContent("ana-ready");

    fireEvent.click(
      screen.getByRole("button", { name: "Create review handoff" }),
    );

    await waitFor(() => {
      expect(mutateAsync).toHaveBeenCalledWith({
        body: "Readiness handoff body",
        promote_to_under_review: true,
        review_note: "Readiness handoff note",
        target_id: "ana-ready",
        target_type: "analysis",
      });
    });
    expect(mockAddToast).toHaveBeenCalledWith(
      "Review handoff created",
      "success",
    );
    expect(navigationMocks.replace).toHaveBeenCalledWith("?tab=comments", {
      scroll: false,
    });
  });

  it("clears report-local handoff state when navigating to another analysis", async () => {
    const mutateAsync = vi.fn().mockResolvedValue({
      comment_id: "comment-ready-1",
      review_status: {
        analysis_id: "ana-ready",
        status: "under_review",
      },
      escalated_to_review: true,
      target_type: "analysis",
      target_id: "ana-ready",
    });

    mockUseReport.mockImplementation((analysisId: string) => ({
      data: {
        report_id: `rpt-${analysisId}`,
        generated_at: "2026-06-19T10:42:00Z",
        compound: { name: `compound-${analysisId}` },
        risk_summary: {
          overall_risk: "high",
          blocking_patents_count: 1,
          total_patents_analyzed: 1,
        },
        patent_analyses: [],
        total_patents_found: 1,
        patents_after_triage: 1,
        source_health: { entries: [] },
        search_sources_used: [],
        clearance_decision: {},
      },
      error: null,
      isLoading: false,
      refetch: vi.fn(),
    }));
    mockUseReviewHandoff.mockReturnValue({
      isError: false,
      isPending: false,
      mutateAsync,
    });

    function KeyedReport({ id }: { id: string }) {
      return <ReportPageHarness key={id} id={id} />;
    }

    const { rerender } = render(<KeyedReport id="ana-ready" />);

    fireEvent.click(
      await screen.findByRole("button", { name: "Create review handoff" }),
    );

    await screen.findByText("Review handoff created");

    rerender(<KeyedReport id="ana-next" />);

    await waitFor(() => {
      expect(mockReportPageHeader).toHaveBeenLastCalledWith(
        expect.objectContaining({
          analysisId: "ana-next",
          reviewHandoffState: expect.objectContaining({
            commentId: null,
          }),
        }),
      );
    });
  });

  it("opens report chat with dashboard AI launch context from the URL", async () => {
    navigationMocks.searchParams = new URLSearchParams({
      ai_context: "blocker_brief",
      tab: "patents",
    });
    const report = {
      report_id: "rpt-ready",
      generated_at: "2026-06-19T10:42:00Z",
      compound: { name: "succinic acid" },
      risk_summary: {
        overall_risk: "high",
        blocking_patents_count: 2,
        total_patents_analyzed: 5,
      },
      patent_analyses: [{ patent_number: "US-HIGH-1" }],
      total_patents_found: 2417,
      patents_after_triage: 47,
      source_health: { entries: [] },
      search_sources_used: [],
      clearance_decision: {},
    };

    mockUseReport.mockReturnValue({
      data: report,
      isLoading: false,
      error: null,
      refetch: vi.fn(),
    });
    mockUseAnalysis.mockReturnValue({
      data: {
        id: "ana-ready",
        share_active: true,
        share_view_count: 4,
        status: "completed",
      },
    });

    renderReportContent("ana-ready");

    expect(await screen.findByTestId("chat-panel")).toHaveTextContent(
      "succinic acid blocker brief",
    );
    expect(mockChatPanel).toHaveBeenLastCalledWith(
      expect.objectContaining({
        launchContext: expect.objectContaining({
          intent: "report",
          prompt: expect.stringContaining("blocking-patent brief"),
          title: "succinic acid blocker brief",
        }),
        open: true,
      }),
    );
    expect(mockChatPanel).toHaveBeenLastCalledWith(
      expect.objectContaining({
        launchContext: expect.objectContaining({
          metadata: expect.arrayContaining([
            { label: "Blockers", value: "2" },
            { label: "Patents", value: "1" },
          ]),
        }),
      }),
    );
  });

  it("routes chat evidence handoff success to the comments workflow", async () => {
    navigationMocks.searchParams = new URLSearchParams({
      ai_context: "review_questions",
    });
    const report = {
      report_id: "rpt-ready",
      generated_at: "2026-06-19T10:42:00Z",
      compound: { name: "succinic acid" },
      risk_summary: {
        overall_risk: "medium",
        blocking_patents_count: 1,
        total_patents_analyzed: 4,
      },
      patent_analyses: [{ patent_number: "US-HIGH-1" }],
      total_patents_found: 52,
      patents_after_triage: 8,
      source_health: { entries: [] },
      search_sources_used: [],
      clearance_decision: {},
    };

    mockUseReport.mockReturnValue({
      data: report,
      isLoading: false,
      error: null,
      refetch: vi.fn(),
    });

    renderReportContent("ana-ready");

    fireEvent.click(
      await screen.findByRole("button", {
        name: "Complete chat review handoff",
      }),
    );

    await waitFor(() => {
      expect(mockAddToast).toHaveBeenCalledWith(
        "Review handoff created",
        "success",
      );
    });
    expect(navigationMocks.replace).toHaveBeenCalledWith(
      "?ai_context=review_questions&tab=comments",
      { scroll: false },
    );
    expect(mockChatPanel).toHaveBeenLastCalledWith(
      expect.objectContaining({
        onReviewHandoffSuccess: expect.any(Function),
        open: false,
      }),
    );
    expect(mockReportPageHeader).toHaveBeenLastCalledWith(
      expect.objectContaining({
        reviewHandoffState: expect.objectContaining({
          commentId: "comment-chat-1",
          reviewStatusLabel: "Under review",
        }),
      }),
    );
  });

  it("persists a generated chat brief through the review handoff mutation", async () => {
    navigationMocks.searchParams = new URLSearchParams({
      ai_context: "review_questions",
    });
    const mutateAsync = vi.fn().mockResolvedValue({
      comment_id: "comment-ai-brief-1",
      review_status: {
        analysis_id: "ana-ready",
        status: "under_review",
      },
      escalated_to_review: true,
      target_type: "analysis",
      target_id: "ana-ready",
    });
    mockUseReviewHandoff.mockReturnValue({
      isError: false,
      isPending: false,
      mutateAsync,
    });
    const report = {
      report_id: "rpt-ready",
      generated_at: "2026-06-19T10:42:00Z",
      compound: { name: "succinic acid" },
      risk_summary: {
        overall_risk: "medium",
        blocking_patents_count: 1,
        total_patents_analyzed: 4,
      },
      patent_analyses: [{ patent_number: "US-HIGH-1" }],
      total_patents_found: 52,
      patents_after_triage: 8,
      source_health: { entries: [] },
      search_sources_used: [],
      clearance_decision: {},
    };

    mockUseReport.mockReturnValue({
      data: report,
      isLoading: false,
      error: null,
      refetch: vi.fn(),
    });

    renderReportContent("ana-ready");

    fireEvent.click(
      await screen.findByRole("button", {
        name: "Send generated brief to review",
      }),
    );

    await waitFor(() => {
      expect(mutateAsync).toHaveBeenCalledWith({
        body: "Generated AI brief body",
        promote_to_under_review: true,
        review_note: "Generated AI brief review note",
        target_id: "ana-ready",
        target_type: "analysis",
      });
    });
    expect(mockAddToast).toHaveBeenCalledWith(
      "Review handoff created",
      "success",
    );
    expect(navigationMocks.replace).toHaveBeenCalledWith(
      "?ai_context=review_questions&tab=comments",
      { scroll: false },
    );
    expect(mockChatPanel).toHaveBeenLastCalledWith(
      expect.objectContaining({
        open: false,
      }),
    );
  });

  it("opens mobile Verify with a structured reliance gap context", async () => {
    const report = {
      report_id: "rpt-ready",
      generated_at: "2026-06-19T10:42:00Z",
      compound: { name: "succinic acid" },
      risk_summary: {
        overall_risk: "medium",
        blocking_patents_count: 1,
        total_patents_analyzed: 4,
      },
      patent_analyses: [{ patent_number: "US-HIGH-1" }],
      total_patents_found: 52,
      patents_after_triage: 8,
      source_health: { entries: [] },
      search_sources_used: [],
      clearance_decision: {},
    };

    mockUseReport.mockReturnValue({
      data: report,
      isLoading: false,
      error: null,
      refetch: vi.fn(),
    });
    mockUseAnalysisReviewStatus.mockReturnValue({
      data: {
        status: "under_review",
        findings_reviewed: 2,
        findings_total: 4,
      },
    });
    mockUseReportWorkspaceSummary.mockReturnValue({
      data: {
        trust_mode: "counsel",
        opinion_readiness: {
          export_ready: false,
          summary: "US lane blocks export.",
          jurisdictions_blocking_export: ["US"],
        },
        target_jurisdictions: ["US", "EP"],
      },
    });

    renderReportContent("ana-ready");

    fireEvent.click(
      screen.getByRole("button", { name: "Mobile verify report evidence" }),
    );

    expect(await screen.findByTestId("chat-panel")).toHaveTextContent(
      "succinic acid reliance gap check",
    );
    expect(mockChatPanel).toHaveBeenLastCalledWith(
      expect.objectContaining({
        launchContext: expect.objectContaining({
          description: expect.stringContaining("mobile report command bar"),
          metadata: expect.arrayContaining([
            { label: "Report", value: "rpt-ready" },
            { label: "Analysis", value: "ana-ready" },
            { label: "Review", value: "2 / 4 findings reviewed" },
            {
              label: "Export readiness",
              value: expect.stringContaining("US lane blocks export"),
            },
            {
              label: "Source audit",
              value: expect.stringContaining("Source audit pending"),
            },
            { label: "Jurisdictions", value: "US, EP" },
          ]),
          prompt: expect.stringContaining("Critique the reliance readiness"),
          title: "succinic acid reliance gap check",
        }),
        open: true,
      }),
    );
  });

  it("routes mobile search to the Evidence workbench query on the Evidence tab", async () => {
    navigationMocks.searchParams = new URLSearchParams({ tab: "evidence" });
    const scrollIntoView = vi.fn();
    Object.defineProperty(window.HTMLElement.prototype, "scrollIntoView", {
      configurable: true,
      value: scrollIntoView,
    });
    const report = {
      report_id: "rpt-ready",
      generated_at: "2026-06-19T10:42:00Z",
      compound: { name: "succinic acid" },
      risk_summary: {
        overall_risk: "medium",
        blocking_patents_count: 1,
        total_patents_analyzed: 4,
      },
      patent_analyses: [{ patent_number: "US-HIGH-1" }],
      total_patents_found: 52,
      patents_after_triage: 8,
      source_health: { entries: [] },
      search_sources_used: [],
      clearance_decision: {},
    };

    mockUseReport.mockReturnValue({
      data: report,
      isLoading: false,
      error: null,
      refetch: vi.fn(),
    });

    renderReportContent("ana-ready");

    fireEvent.click(
      screen.getByRole("button", { name: "Mobile search reviewed evidence" }),
    );

    const evidenceSearch = screen.getByRole("textbox", {
      name: "Evidence search query",
    });
    await waitFor(() => expect(evidenceSearch).toHaveFocus());
    expect(evidenceSearch.closest("details")).toHaveAttribute("open");
    expect(scrollIntoView).toHaveBeenCalledWith(
      expect.objectContaining({ block: "center" }),
    );
  });

  it("mounts mobile report commands immediately below section navigation", () => {
    renderReportContent("ana-ready");

    const reportTabs = screen.getByText("Report tabs");
    const mobileCommands = screen.getByRole("button", {
      name: "Mobile search reviewed evidence",
    }).parentElement;
    const sectionContext = screen.getByText("Report section context");

    expect(
      reportTabs.compareDocumentPosition(mobileCommands as Node) &
        Node.DOCUMENT_POSITION_FOLLOWING,
    ).toBeTruthy();
    expect(
      (mobileCommands as Node).compareDocumentPosition(sectionContext) &
        Node.DOCUMENT_POSITION_FOLLOWING,
    ).toBeTruthy();
  });

  it("applies URL search params to the reviewed report search", async () => {
    navigationMocks.searchParams = new URLSearchParams({
      search: "  blocking claim elements  ",
      tab: "patents",
    });
    const scrollIntoView = vi.fn();
    Object.defineProperty(window.HTMLElement.prototype, "scrollIntoView", {
      configurable: true,
      value: scrollIntoView,
    });
    const originalRequestAnimationFrame = window.requestAnimationFrame;
    window.requestAnimationFrame = ((callback: FrameRequestCallback) => {
      callback(0);
      return 1;
    }) as typeof window.requestAnimationFrame;
    const search = vi.fn();
    mockUseReportSearch.mockReturnValue({
      clear: vi.fn(),
      error: null,
      failedQuery: "",
      interpretedQuery: "",
      isSearching: false,
      isShowingPreviousResults: false,
      resultQuery: "",
      results: [],
      search,
      totalResults: 0,
    });
    const report = {
      report_id: "rpt-ready",
      generated_at: "2026-06-19T10:42:00Z",
      compound: { name: "succinic acid" },
      risk_summary: {
        overall_risk: "medium",
        blocking_patents_count: 1,
        total_patents_analyzed: 4,
      },
      patent_analyses: [{ patent_number: "US-HIGH-1" }],
      total_patents_found: 52,
      patents_after_triage: 8,
      source_health: { entries: [] },
      search_sources_used: [],
      clearance_decision: {},
    };

    mockUseReport.mockReturnValue({
      data: report,
      isLoading: false,
      error: null,
      refetch: vi.fn(),
    });

    try {
      renderReportContent("ana-ready");

      await waitFor(() => {
        expect(search).toHaveBeenCalledWith("blocking claim elements");
      });
      expect(mockReportSearchBar).toHaveBeenLastCalledWith(
        expect.objectContaining({
          initialQuery: "blocking claim elements",
          onSearch: expect.any(Function),
        }),
      );
      expect(
        screen.getByText("Report search bar blocking claim elements"),
      ).toBeInTheDocument();
      expect(scrollIntoView).toHaveBeenCalledWith(
        expect.objectContaining({ block: "center" }),
      );
    } finally {
      window.requestAnimationFrame = originalRequestAnimationFrame;
    }
  });

  it("removes URL search params when reviewed report search is cleared", async () => {
    navigationMocks.searchParams = new URLSearchParams({
      search: "private claim query",
      tab: "patents",
    });
    const clear = vi.fn();
    const search = vi.fn();
    mockUseReportSearch.mockReturnValue({
      clear,
      error: null,
      failedQuery: "",
      interpretedQuery: "",
      isSearching: false,
      isShowingPreviousResults: false,
      resultQuery: "",
      results: [],
      search,
      totalResults: 0,
    });
    const report = {
      report_id: "rpt-ready",
      generated_at: "2026-06-19T10:42:00Z",
      compound: { name: "succinic acid" },
      risk_summary: {
        overall_risk: "medium",
        blocking_patents_count: 1,
        total_patents_analyzed: 4,
      },
      patent_analyses: [{ patent_number: "US-HIGH-1" }],
      total_patents_found: 52,
      patents_after_triage: 8,
      source_health: { entries: [] },
      search_sources_used: [],
      clearance_decision: {},
    };

    mockUseReport.mockReturnValue({
      data: report,
      isLoading: false,
      error: null,
      refetch: vi.fn(),
    });

    renderReportContent("ana-ready");

    const latestSearchBarProps = () =>
      mockReportSearchBar.mock.calls.at(-1)?.[0] as
        | { onClear?: () => void }
        | undefined;
    latestSearchBarProps()?.onClear?.();

    expect(clear).toHaveBeenCalledTimes(1);
    expect(navigationMocks.replace).toHaveBeenCalledWith("?tab=patents", {
      scroll: false,
    });
  });

  it("opens a unique publication-ID result in the patent drawer route", async () => {
    const search = vi.fn().mockResolvedValue({
      query: "WO2011123645",
      interpreted_query: 'Keyword search: "WO2011123645"',
      results: [
        {
          patent_id: "WO2011123645A1",
          section: "patent_analysis",
          relevance: 0.7,
          snippet: "Solid forms of an antiviral compound.",
        },
      ],
      total: 1,
    });
    mockUseReportSearch.mockReturnValue({
      clear: vi.fn(),
      error: null,
      interpretedQuery: "",
      isSearching: false,
      results: [],
      search,
      totalResults: 0,
    });
    mockUseReport.mockReturnValue({
      data: {
        report_id: "rpt-ready",
        generated_at: "2026-06-19T10:42:00Z",
        compound: { name: "sofosbuvir" },
        risk_summary: {
          overall_risk: "high",
          blocking_patents_count: 1,
          total_patents_analyzed: 1,
        },
        patent_analyses: [{ patent_id: "WO2011123645A1" }],
        total_patents_found: 1,
        patents_after_triage: 1,
        source_health: { entries: [] },
        search_sources_used: [],
        clearance_decision: {},
      },
      isLoading: false,
      error: null,
      refetch: vi.fn(),
    });

    renderReportContent("ana-ready");
    const searchBarProps = mockReportSearchBar.mock.calls.at(-1)?.[0] as {
      onSearch: (query: string) => Promise<void>;
    };
    await act(async () => {
      await searchBarProps.onSearch("WO2011123645");
    });

    expect(search).toHaveBeenCalledWith("WO2011123645");
    expect(navigationMocks.replace).toHaveBeenLastCalledWith(
      "?search=WO2011123645&tab=patents&patent=WO2011123645A1",
      { scroll: false },
    );
  });

  it("maps legacy assistant evidence links to the active report AI context", async () => {
    navigationMocks.searchParams = new URLSearchParams({
      assistant: "evidence",
      tab: "claims",
    });
    const report = {
      report_id: "rpt-ready",
      generated_at: "2026-06-19T10:42:00Z",
      compound: { name: "succinic acid" },
      risk_summary: {
        overall_risk: "medium",
        blocking_patents_count: 1,
        total_patents_analyzed: 4,
      },
      patent_analyses: [{ patent_number: "US-HIGH-1" }],
      total_patents_found: 52,
      patents_after_triage: 8,
      source_health: { entries: [] },
      search_sources_used: [],
      clearance_decision: {},
    };

    mockUseReport.mockReturnValue({
      data: report,
      isLoading: false,
      error: null,
      refetch: vi.fn(),
    });

    renderReportContent("ana-ready");

    expect(await screen.findByTestId("chat-panel")).toHaveTextContent(
      "succinic acid reviewer questions",
    );
    expect(mockChatPanel).toHaveBeenLastCalledWith(
      expect.objectContaining({
        launchContext: expect.objectContaining({
          prompt: expect.stringContaining("Prepare reviewer questions"),
          title: "succinic acid reviewer questions",
        }),
        open: true,
      }),
    );
  });

  it("opens a source panel from report chat citation chips", async () => {
    navigationMocks.searchParams = new URLSearchParams({
      ai_context: "blocker_brief",
    });
    const report = {
      report_id: "rpt-ready",
      generated_at: "2026-06-19T10:42:00Z",
      compound: { name: "succinic acid" },
      risk_summary: {
        overall_risk: "high",
        blocking_patents_count: 1,
        total_patents_analyzed: 1,
      },
      patent_analyses: [],
      total_patents_found: 1,
      patents_after_triage: 1,
      source_health: { entries: [] },
      search_sources_used: [],
      clearance_decision: {},
    };

    mockUseReport.mockReturnValue({
      data: report,
      isLoading: false,
      error: null,
      refetch: vi.fn(),
    });

    renderReportContent("ana-ready");

    fireEvent.click(
      await screen.findByRole("button", { name: "Open chat citation" }),
    );

    expect(
      screen.getByRole("dialog", { name: "Citation source" }),
    ).toBeInTheDocument();
    expect(
      screen.getByText("Claim 1 covers the succinate formulation."),
    ).toBeInTheDocument();
    expect(
      screen.getByText("Report chat citation: US1234567 claim text"),
    ).toBeInTheDocument();
    expect(
      screen.queryByTestId("citation-source-text"),
    ).not.toBeInTheDocument();
  });
});
