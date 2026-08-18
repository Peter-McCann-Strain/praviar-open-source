import { createRef } from "react";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { MobileReportCommandBar } from "@/components/report-page/mobile-report-command-bar";
import type { FTOReport } from "@praviar/shared-types";

let mockWatchEnabled = false;
let mockWatchPending = false;
let mockWatchControlsLocked = false;
let mockWatchRecovery: {
  mode: "outcome-unknown";
  variables: {
    kind: "start";
    variables: { analysis_id: string; schedule: string };
  };
} | null = null;
const mockHandleWatchRecoveryAction = vi.fn();

vi.mock("@/components/report-page/use-report-watch-control", () => ({
  useSharedReportWatchControl: () => ({
    watchControlsLocked: mockWatchControlsLocked,
    watchEnabled: mockWatchEnabled,
    watchPending: mockWatchPending,
    watchRecovery: mockWatchRecovery,
    watchSchedule: "weekly",
    handleWatchRecoveryAction: mockHandleWatchRecoveryAction,
    handleWatchToggle: vi.fn(),
  }),
}));

vi.mock("@/components/report/reviewer-decision-button", () => ({
  ReviewerDecisionButton: ({
    ariaLabel,
    className,
    label,
    onBeforeOpen,
    testId,
  }: {
    ariaLabel?: string;
    className?: string;
    label?: string;
    onBeforeOpen?: () => void;
    testId?: string;
  }) => (
    <button
      type="button"
      aria-label={ariaLabel}
      className={className}
      data-testid={testId}
      onClick={onBeforeOpen}
    >
      {label}
    </button>
  ),
}));

vi.mock("@/components/report/watch-toggle", () => ({
  WatchToggle: ({
    enabled,
    isPending,
  }: {
    enabled?: boolean;
    isPending?: boolean;
  }) => (
    <button type="button" disabled={isPending}>
      {isPending ? "Watch updating" : enabled ? "Watching" : "Watch"}
    </button>
  ),
}));

vi.mock("@/components/collaboration/flag-button", () => ({
  FlagButton: () => <button type="button">Flag for Review</button>,
}));

const report = {
  report_id: "PRV-2026-0142",
  compound: { name: "Succinic acid" },
  risk_summary: { overall_risk: "medium" },
} as FTOReport;

const CLEAN_SOURCE_REPORT = {
  ...report,
  search_sources_used: ["pubchem_sdq", "surechembl"],
  source_health: {
    entries: [
      { source: "pubchem_sdq", status: "ok" },
      { source: "surechembl", status: "ok" },
    ],
  },
} as FTOReport;

const CAVEATED_SOURCE_REPORT = {
  ...report,
  search_sources_used: ["pubchem_sdq", "surechembl"],
  source_health: {
    entries: [
      { source: "pubchem_sdq", status: "ok" },
      { source: "surechembl", status: "failed" },
    ],
  },
} as FTOReport;

const READY_REVIEW_STATUS = {
  analysis_id: "analysis-1",
  status: "approved",
  note: "Approved by counsel.",
  reviewer_name: "Demo Counsel",
  reviewer_email: "counsel@example.test",
  reviewed_at: "2026-04-24T10:00:00.000Z",
  updated_at: "2026-04-24T10:00:00.000Z",
  decision_counts: { accept: 4, reject: 0, edit: 0 },
  findings_total: 4,
  findings_reviewed: 4,
  completion_pct: 100,
} as const;

const READY_WORKSPACE_SUMMARY = {
  analysis_id: "analysis-1",
  report_id: "PRV-2026-0142",
  trust_mode: "counsel",
  target_jurisdictions: ["US", "EP"],
  jurisdiction_matrix: [],
  report_summary: {
    overall_risk: "medium",
    blocking_patents_count: 1,
    total_patents_found: 142,
    executive_summary: "Counsel approved.",
  },
  capability_metadata: {},
  suggested_evidence_queries: [],
  monitor_seed_defaults: {
    analysis_id: "analysis-1",
    compound_name: "Succinic acid",
    compound_smiles: null,
    schedule: "weekly",
    source_report_id: "PRV-2026-0142",
    source_trust_mode: "counsel",
    requires_manual_input: false,
    missing_fields: [],
  },
  routing_profile: {},
  opinion_readiness: {
    export_ready: true,
    summary: "Counsel export readiness cleared.",
    jurisdictions_blocking_export: [],
  },
  data_coverage: {},
  source_convergence: {},
  uncertainty_register: [],
  evidence_scope: {
    mode: "report_evidence",
    external_live_retrieval: false,
    comment_routing_available: true,
    sources_considered: ["Report claims"],
    governed_note: "Report-grounded evidence only for this run.",
    provider_capabilities: [],
    providers: [],
    hybrid_evidence_ready: false,
  },
} as const;

const COMMAND_BAR_NAME = /Report command bar for PRV-2026-0142/u;

function renderCommandBar(overrides = {}) {
  const props = {
    analysisId: "analysis-1",
    token: "tok",
    report,
    chatOpen: false,
    currentUserRole: "attorney",
    askButtonRef: createRef<HTMLButtonElement>(),
    onAsk: vi.fn(),
    onSearch: vi.fn(),
    onExport: vi.fn(),
    onShare: vi.fn(),
    onFeedback: vi.fn(),
    onReviewOpen: vi.fn(),
    ...overrides,
  };

  const view = render(<MobileReportCommandBar {...props} />);
  return { ...props, ...view };
}

describe("MobileReportCommandBar", () => {
  beforeEach(() => {
    mockWatchEnabled = false;
    mockWatchPending = false;
    mockWatchControlsLocked = false;
    mockWatchRecovery = null;
    mockHandleWatchRecoveryAction.mockReset();
  });

  it("renders the primary mobile report commands", () => {
    renderCommandBar();

    const toolbar = screen.getByRole("toolbar", {
      name: COMMAND_BAR_NAME,
    });

    expect(toolbar).toBeInTheDocument();
    expect(toolbar).toHaveAttribute("data-praviar-mobile-command-bar");
    expect(toolbar).toHaveClass(
      "sticky",
      "rounded-lg",
      "top-[var(--praviar-mobile-command-rail-top)]",
      "[--praviar-mobile-command-rail-height:3.625rem]",
      "[--praviar-mobile-command-rail-top:6.25rem]",
      "sm:[--praviar-mobile-command-rail-top:6.75rem]",
    );
    expect(toolbar).not.toHaveClass("rounded-t-2xl");
    expect(
      screen.queryByRole("group", {
        name: /Current report PRV-2026-0142, Moderate Risk\. Owner Reviewer \/ counsel\. Next action Assign counsel review and close material findings\./u,
      }),
    ).not.toBeInTheDocument();
    expect(
      document.querySelector("[data-praviar-mobile-primary-actions]"),
    ).toHaveClass("grid-cols-3");
    expect(
      document.querySelector('svg[data-praviar-mark="praviar-evidence-mark"]'),
    ).not.toBeInTheDocument();
    expect(screen.queryByText("PRV-2026-0142")).not.toBeInTheDocument();
    expect(screen.queryByText("Succinic acid")).not.toBeInTheDocument();
    expect(screen.queryByText("Moderate Risk")).not.toBeInTheDocument();
    expect(
      screen.queryByText(
        "Owner: Reviewer / counsel · Assign counsel review and close material findings.",
      ),
    ).not.toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "Review findings" }),
    ).toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: "Search reviewed evidence" }),
    ).not.toBeInTheDocument();
    expect(
      screen.getByRole("button", {
        name: "AI-assisted report evidence gap check",
      }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "More report actions" }),
    ).toBeInTheDocument();
  });

  it("routes scientists to counsel instead of exposing unauthorized collaboration actions", () => {
    const onRequestCounsel = vi.fn();
    renderCommandBar({
      currentUserRole: "scientist",
      onRequestCounsel,
    });

    expect(
      screen.queryByRole("button", { name: "Review findings" }),
    ).not.toBeInTheDocument();
    fireEvent.click(
      screen.getByRole("button", { name: "Request counsel review" }),
    );
    expect(onRequestCounsel).toHaveBeenCalledTimes(1);

    fireEvent.click(
      screen.getByRole("button", { name: "More report actions" }),
    );
    expect(
      screen.queryByRole("button", { name: "Share report" }),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: "Submit feedback" }),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: /export/i }),
    ).not.toBeInTheDocument();
  });

  it("keeps collaboration restricted while exposing capability-authorized scientist export", () => {
    renderCommandBar({
      currentUserRole: "scientist",
      canExportReport: true,
      onRequestCounsel: vi.fn(),
    });

    fireEvent.click(
      screen.getByRole("button", { name: "More report actions" }),
    );

    expect(
      screen.getByRole("button", {
        name: "Review export blockers before exporting evidence packet",
      }),
    ).toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: "Share report" }),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: "Submit feedback" }),
    ).not.toBeInTheDocument();
  });

  it("fails closed while the mobile collaboration role is unresolved", () => {
    renderCommandBar({
      currentUserRole: null,
      onRequestCounsel: vi.fn(),
    });

    expect(
      screen.getByRole("button", { name: "Request counsel review" }),
    ).toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: "Review findings" }),
    ).not.toBeInTheDocument();
    fireEvent.click(
      screen.getByRole("button", { name: "More report actions" }),
    );
    expect(
      screen.queryByRole("button", { name: "Share report" }),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: "Submit feedback" }),
    ).not.toBeInTheDocument();
  });

  it("contains long mobile report metadata without resizing the command bar", () => {
    const longReportId = `PRV-2026-0142-${"LONG".repeat(20)}`;
    renderCommandBar({
      report: {
        ...report,
        report_id: longReportId,
        compound: {
          name: `N-(4-hydroxyphenyl)-${"very-long-compound-".repeat(8)}`,
        },
      } as FTOReport,
    });

    const toolbar = screen.getByRole("toolbar", {
      name: /Report command bar for PRV-2026-0142-LONG/u,
    });

    expect(toolbar).toHaveClass("sticky", "rounded-lg", "px-2", "py-1.5");
    expect(toolbar).not.toHaveClass("fixed", "bottom-0", "rounded-t-lg");
    expect(
      document.querySelector("[data-praviar-mobile-command-summary]"),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByText(/N-\(4-hydroxyphenyl\)/u),
    ).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Review findings" })).toHaveClass(
      "h-11",
    );
    expect(
      screen.getByRole("button", {
        name: "AI-assisted report evidence gap check",
      }),
    ).toHaveClass("h-11");

    fireEvent.click(
      screen.getByRole("button", { name: "More report actions" }),
    );

    expect(
      screen.getByRole("group", {
        name: /Current report PRV-2026-0142-LONG/u,
      }),
    ).toHaveAttribute("data-praviar-mobile-command-summary");
    expect(screen.getByText(longReportId)).toHaveAttribute(
      "title",
      longReportId,
    );
    expect(screen.getByText(longReportId)).toHaveClass(
      "min-w-0",
      "max-w-full",
      "break-all",
      "[overflow-wrap:anywhere]",
    );
    expect(
      document.querySelector("[data-praviar-mark-frame]"),
    ).toBeInTheDocument();
    expect(screen.getByText(/N-\(4-hydroxyphenyl\)/u)).toHaveClass(
      "break-words",
      "[overflow-wrap:anywhere]",
    );
    expect(screen.getByText("Moderate Risk")).toBeInTheDocument();
    expect(screen.getByText(/Owner: Reviewer \/ counsel/u)).toHaveAttribute(
      "data-praviar-mobile-lifecycle-context",
    );
    expect(screen.getByText(/Owner: Reviewer \/ counsel/u)).toHaveClass(
      "break-words",
      "[overflow-wrap:anywhere]",
    );
    expect(
      screen.getByText(/Next: Assign counsel review/u),
    ).toBeInTheDocument();
  });

  it("keeps active watch posture in the mobile actions sheet", () => {
    mockWatchEnabled = true;
    renderCommandBar();

    expect(
      screen.queryByRole("button", { name: "Watching" }),
    ).not.toBeInTheDocument();

    fireEvent.click(
      screen.getByRole("button", { name: "More report actions" }),
    );

    expect(
      screen.getByRole("button", { name: "Watching" }),
    ).toBeInTheDocument();
  });

  it("keeps mobile watch controls locked beside a persistent start recovery", () => {
    mockWatchControlsLocked = true;
    mockWatchRecovery = {
      mode: "outcome-unknown",
      variables: {
        kind: "start",
        variables: { analysis_id: "analysis-1", schedule: "weekly" },
      },
    };
    renderCommandBar();

    fireEvent.click(
      screen.getByRole("button", { name: "More report actions" }),
    );

    expect(screen.getByTestId("report-watch-recovery-mobile")).toBeVisible();
    expect(
      screen.getByRole("button", { name: "Watch updating" }),
    ).toBeDisabled();
    fireEvent.click(screen.getByTestId("report-watch-recovery-mobile-action"));
    expect(mockHandleWatchRecoveryAction).toHaveBeenCalledTimes(1);
  });

  it("opens the report monitor plan from the mobile actions sheet", () => {
    const onMonitorPlan = vi.fn();
    renderCommandBar({ onMonitorPlan });

    fireEvent.click(
      screen.getByRole("button", { name: "More report actions" }),
    );
    fireEvent.click(
      screen.getByRole("button", { name: "Open report-to-monitor plan" }),
    );

    expect(onMonitorPlan).toHaveBeenCalledTimes(1);
  });

  it("surfaces active external share posture without crowding the fixed bar", () => {
    renderCommandBar({
      shareActive: true,
      shareViewCount: 7,
      shareLastViewedAt: null,
    });

    const shareStatus = screen.getByRole("status", {
      name: "External share status",
    });

    expect(screen.queryByText(/Shared ·/u)).not.toBeInTheDocument();
    expect(shareStatus).toHaveTextContent("External share active");
    expect(shareStatus).toHaveTextContent("7 views");
    expect(shareStatus).toHaveTextContent("last viewed never");
    expect(shareStatus).toHaveClass("sr-only");

    fireEvent.click(
      screen.getByRole("button", { name: "More report actions" }),
    );

    expect(screen.getByText(/Shared · 7 views/u)).toBeInTheDocument();
  });

  it("uses singular copy for one active mobile share view", () => {
    renderCommandBar({
      shareActive: true,
      shareViewCount: 1,
      shareLastViewedAt: null,
    });

    const shareStatus = screen.getByRole("status", {
      name: "External share status",
    });

    expect(shareStatus).toHaveTextContent("1 view");
    expect(shareStatus).not.toHaveTextContent("1 views");
    expect(screen.queryByText(/Shared · 1 view/u)).not.toBeInTheDocument();

    fireEvent.click(
      screen.getByRole("button", { name: "More report actions" }),
    );

    expect(screen.getByText(/Shared · 1 view/u)).toBeInTheDocument();
  });

  it("removes the fixed command bar while mobile chat is open", () => {
    renderCommandBar({ chatOpen: true });

    expect(
      screen.queryByRole("toolbar", { name: /Report command bar/u }),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByRole("button", {
        name: "AI-assisted report evidence gap check",
      }),
    ).not.toBeInTheDocument();
  });

  it("closes an open action sheet when chat opens and keeps it closed", async () => {
    const view = renderCommandBar();

    fireEvent.click(
      screen.getByRole("button", { name: "More report actions" }),
    );
    expect(
      screen.getByRole("dialog", { name: "Report actions" }),
    ).toBeInTheDocument();

    view.rerender(
      <MobileReportCommandBar
        analysisId={view.analysisId}
        token={view.token}
        report={view.report}
        chatOpen
        askButtonRef={view.askButtonRef}
        onAsk={view.onAsk}
        onSearch={view.onSearch}
        onExport={view.onExport}
        onShare={view.onShare}
        onFeedback={view.onFeedback}
      />,
    );

    await waitFor(() => {
      expect(
        screen.queryByRole("dialog", { name: "Report actions" }),
      ).not.toBeInTheDocument();
    });
    expect(
      screen.queryByRole("toolbar", { name: /Report command bar/u }),
    ).not.toBeInTheDocument();

    view.rerender(
      <MobileReportCommandBar
        analysisId={view.analysisId}
        token={view.token}
        report={view.report}
        chatOpen={false}
        askButtonRef={view.askButtonRef}
        onAsk={view.onAsk}
        onSearch={view.onSearch}
        onExport={view.onExport}
        onShare={view.onShare}
        onFeedback={view.onFeedback}
      />,
    );

    expect(
      screen.getByRole("toolbar", { name: COMMAND_BAR_NAME }),
    ).toBeInTheDocument();
    expect(
      screen.queryByRole("dialog", { name: "Report actions" }),
    ).not.toBeInTheDocument();
  });

  it("routes Search and Ask to page-level handlers", () => {
    const props = renderCommandBar();

    fireEvent.click(
      screen.getByRole("button", { name: "More report actions" }),
    );
    fireEvent.click(
      screen.getByRole("button", { name: "Search reviewed evidence" }),
    );
    fireEvent.click(
      screen.getByRole("button", {
        name: "AI-assisted report evidence gap check",
      }),
    );

    expect(props.onSearch).toHaveBeenCalledTimes(1);
    expect(props.onAsk).toHaveBeenCalledTimes(1);
  });

  it("notifies the report page before opening mobile reviewer decisions", () => {
    const props = renderCommandBar();

    fireEvent.click(screen.getByRole("button", { name: "Review findings" }));

    expect(props.onReviewOpen).toHaveBeenCalledTimes(1);
  });

  it("opens report actions and closes the sheet before launching dialogs", async () => {
    const props = renderCommandBar();
    const readinessPanel = document.createElement("section");
    readinessPanel.id = "report-reliance-readiness";
    const readinessAction = document.createElement("button");
    readinessAction.type = "button";
    readinessAction.setAttribute(
      "data-testid",
      "report-export-recovery-ai-action",
    );
    readinessPanel.append(readinessAction);
    const readinessDisclosure = document.createElement("details");
    readinessDisclosure.append(readinessPanel);
    document.body.append(readinessDisclosure);

    fireEvent.click(
      screen.getByRole("button", { name: "More report actions" }),
    );

    expect(
      screen.getByRole("dialog", { name: "Report actions" }),
    ).toBeInTheDocument();
    expect(screen.getByRole("dialog", { name: "Report actions" })).toHaveClass(
      "top-[calc(var(--praviar-mobile-command-rail-top)+var(--praviar-mobile-command-rail-height)+0.5rem)]",
      "max-h-[calc(100dvh_-_var(--praviar-mobile-command-rail-top)_-_var(--praviar-mobile-command-rail-height)_-_1.25rem_-_env(safe-area-inset-bottom))]",
      "max-w-[calc(100vw-1.5rem)]",
      "overflow-x-hidden",
      "[--praviar-mobile-command-rail-height:3.625rem]",
      "[--praviar-mobile-command-rail-top:6.25rem]",
    );
    expect(
      screen.getByRole("group", {
        name: /Current report PRV-2026-0142, Moderate Risk/u,
      }),
    ).toHaveAttribute("data-praviar-mobile-command-summary");
    expect(
      screen.getByRole("dialog", { name: "Report actions" }),
    ).not.toHaveClass("bottom-[calc(4.25rem+env(safe-area-inset-bottom))]");
    expect(
      screen.getAllByRole("button", { name: "Close report actions" }),
    ).toHaveLength(1);
    expect(
      screen.getByRole("button", { name: "Search reviewed evidence" }),
    ).toHaveAccessibleDescription("Claims, citations, and reviewer notes");
    expect(
      screen.getByRole("button", {
        name: "Review export blockers before exporting evidence packet",
      }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", {
        name: "Review export blockers before exporting evidence packet",
      }),
    ).toHaveClass(
      "min-h-11",
      "h-auto",
      "min-w-0",
      "max-w-full",
      "py-2",
      "whitespace-normal",
      "justify-start",
    );
    expect(
      screen.getByRole("button", {
        name: "Review export blockers before exporting evidence packet",
      }),
    ).toHaveAccessibleDescription("Persisted legal review required");
    expect(screen.getByText("Review export blockers")).toBeInTheDocument();
    expect(screen.getByText("Persisted legal review required")).toHaveClass(
      "break-words",
      "[overflow-wrap:anywhere]",
    );
    expect(screen.getByText("Review export blockers")).toHaveClass(
      "break-words",
      "[overflow-wrap:anywhere]",
    );
    expect(
      screen.queryByText("Export readiness unavailable"),
    ).not.toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "Share report" }),
    ).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Watch" })).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "Print current section" }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "Flag for Review" }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "Submit feedback" }),
    ).toBeInTheDocument();

    fireEvent.click(
      screen.getByRole("button", {
        name: "Review export blockers before exporting evidence packet",
      }),
    );

    expect(props.onExport).not.toHaveBeenCalled();
    expect(
      screen.queryByRole("dialog", { name: "Report actions" }),
    ).not.toBeInTheDocument();
    expect(readinessDisclosure).toHaveAttribute("open");
    await waitFor(() => expect(readinessAction).toHaveFocus());
    readinessDisclosure.remove();
  });

  it("shows the clean export action only when review and workspace readiness are approved", () => {
    renderCommandBar({
      report: CLEAN_SOURCE_REPORT,
      reviewStatus: READY_REVIEW_STATUS,
      workspaceSummary: READY_WORKSPACE_SUMMARY,
    });

    fireEvent.click(
      screen.getByRole("button", { name: "More report actions" }),
    );

    expect(
      screen.getByRole("button", { name: "Export evidence packet" }),
    ).toBeInTheDocument();
    expect(
      screen.queryByText("Review export blockers"),
    ).not.toBeInTheDocument();
  });

  it("keeps unsafe active-share guidance visible in the mobile action sheet", () => {
    renderCommandBar({
      report: CLEAN_SOURCE_REPORT,
      reviewStatus: READY_REVIEW_STATUS,
      shareActive: true,
      shareRecipientBound: false,
      workspaceSummary: READY_WORKSPACE_SUMMARY,
    });

    fireEvent.click(
      screen.getByRole("button", { name: "More report actions" }),
    );

    const summary = screen.getByRole("group", {
      name: /Reissue the share to a named, mailbox-verified recipient/i,
    });

    expect(summary).toHaveTextContent(
      "Next: Reissue the share to a named, mailbox-verified recipient.",
    );
    expect(summary).not.toHaveTextContent("protected for external sharing");
  });

  it("shows export with source caveat when readiness is cleared but source health is caveated", () => {
    const onExport = vi.fn();
    renderCommandBar({
      onExport,
      report: CAVEATED_SOURCE_REPORT,
      reviewStatus: READY_REVIEW_STATUS,
      workspaceSummary: READY_WORKSPACE_SUMMARY,
    });

    fireEvent.click(
      screen.getByRole("button", { name: "More report actions" }),
    );

    const exportButton = screen.getByRole("button", {
      name: "Prepare evidence packet export with source caveat",
    });
    expect(exportButton).toHaveAccessibleDescription(
      "1 failed; coverage may be incomplete.",
    );
    expect(exportButton).toHaveTextContent("Prepare export with source caveat");
    expect(exportButton).toHaveClass("text-warning");

    fireEvent.click(exportButton);

    expect(onExport).toHaveBeenCalledTimes(1);
  });

  it("traps focus inside mobile report actions and restores focus on Escape", async () => {
    renderCommandBar();

    const actionsButton = screen.getByRole("button", {
      name: "More report actions",
    });
    actionsButton.focus();
    fireEvent.click(actionsButton);

    const dialog = screen.getByRole("dialog", { name: "Report actions" });
    const closeButton = screen.getByRole("button", {
      name: "Close report actions",
    });
    const submitFeedback = screen.getByRole("button", {
      name: "Submit feedback",
    });

    await waitFor(() => expect(closeButton).toHaveFocus());

    fireEvent.keyDown(dialog, { key: "Tab", shiftKey: true });
    expect(submitFeedback).toHaveFocus();

    fireEvent.keyDown(dialog, { key: "Tab" });
    expect(closeButton).toHaveFocus();

    fireEvent.keyDown(dialog, { key: "Escape" });
    await waitFor(() => expect(actionsButton).toHaveFocus());
    expect(
      screen.queryByRole("dialog", { name: "Report actions" }),
    ).not.toBeInTheDocument();
  });

  it("restores focus to Actions after non-dialog sheet actions", async () => {
    const printSpy = vi.spyOn(window, "print").mockImplementation(() => {});
    renderCommandBar();

    const actionsButton = screen.getByRole("button", {
      name: "More report actions",
    });
    fireEvent.click(actionsButton);

    const printButton = screen.getByRole("button", {
      name: "Print current section",
    });
    printButton.focus();
    fireEvent.click(printButton);

    expect(printSpy).toHaveBeenCalledTimes(1);
    await waitFor(() => expect(actionsButton).toHaveFocus());
    expect(
      screen.queryByRole("dialog", { name: "Report actions" }),
    ).not.toBeInTheDocument();

    printSpy.mockRestore();
  });
});
