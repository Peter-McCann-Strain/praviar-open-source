import { createRef, type ComponentProps } from "react";
import {
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { ReportPageHeader as ReportPageHeaderComponent } from "@/components/report-page/report-page-header";
import { TEST_REPORT } from "../fixtures/report-fixture";
import type { ReviewerDecisionListResponse } from "@/hooks/use-reviewer-decisions";

let mockWatchControlsLocked = false;
let mockWatchRecovery: {
  mode: "outcome-unknown";
  variables: {
    kind: "start";
    variables: { analysis_id: string; schedule: string };
  };
} | null = null;
const mockHandleWatchRecoveryAction = vi.fn();

function ReportPageHeader(
  props: ComponentProps<typeof ReportPageHeaderComponent>,
) {
  return <ReportPageHeaderComponent currentUserRole="attorney" {...props} />;
}

vi.mock("@/components/report-page/use-report-watch-control", () => ({
  useSharedReportWatchControl: () => ({
    watchControlsLocked: mockWatchControlsLocked,
    watchEnabled: false,
    watchPending: false,
    watchRecovery: mockWatchRecovery,
    watchSchedule: "weekly",
    handleWatchRecoveryAction: mockHandleWatchRecoveryAction,
    handleWatchToggle: vi.fn(),
  }),
}));

vi.mock("@/components/report/reviewer-decision-button", () => ({
  ReviewerDecisionButton: ({ onBeforeOpen }: { onBeforeOpen?: () => void }) => (
    <button type="button" onClick={onBeforeOpen}>
      Review findings
    </button>
  ),
}));

vi.mock("@/components/report/watch-toggle", () => ({
  WatchToggle: ({ isPending }: { isPending?: boolean }) => (
    <button type="button" disabled={isPending}>
      {isPending ? "Watch updating" : "Watch"}
    </button>
  ),
}));

vi.mock("@/components/collaboration/flag-button", () => ({
  FlagButton: () => <button type="button">Flag for Review</button>,
}));

vi.mock("@/components/report/share-analytics-stats", () => ({
  ShareAnalyticsStats: () => <div>Share analytics</div>,
}));

vi.mock("@/components/report/verdict-banner", () => ({
  VerdictBanner: ({
    approvalApprovedAt,
    approvalApprover,
    approvalStatus,
  }: {
    approvalApprovedAt?: string;
    approvalApprover?: string;
    approvalStatus?: string;
  }) => (
    <div
      data-testid="verdict-banner"
      data-approval-approved-at={approvalApprovedAt ?? ""}
      data-approval-approver={approvalApprover ?? ""}
      data-approval-status={approvalStatus ?? ""}
    >
      Verdict banner
    </div>
  ),
}));

vi.mock("@/components/report/coverage-banner", () => ({
  ReportCoverageBanner: () => <div>Coverage banner</div>,
}));

const BLOCKED_WORKSPACE_SUMMARY = {
  analysis_id: "analysis-1",
  report_id: "rpt_demo_succinic_001",
  trust_mode: "counsel",
  target_jurisdictions: ["US", "EP"],
  jurisdiction_matrix: [],
  report_summary: {
    overall_risk: "high",
    blocking_patents_count: 3,
    total_patents_found: 2417,
    executive_summary: "Review required.",
  },
  capability_metadata: {},
  suggested_evidence_queries: [],
  monitor_seed_defaults: {
    analysis_id: "analysis-1",
    compound_name: "succinic acid",
    compound_smiles: "OC(=O)CCC(O)=O",
    schedule: "weekly",
    source_report_id: "rpt_demo_succinic_001",
    source_trust_mode: "counsel",
    requires_manual_input: false,
    missing_fields: [],
  },
  routing_profile: {},
  opinion_readiness: {
    export_ready: false,
    summary: "Counsel export remains blocked until jurisdictions are reviewed.",
    jurisdictions_blocking_export: ["US", "EP"],
  },
  data_coverage: {},
  source_convergence: {},
  uncertainty_register: [{ id: "u-1" }],
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

const REVIEW_STATUS = {
  analysis_id: "analysis-1",
  status: "under_review",
  note: "Counsel review in progress.",
  reviewer_name: "Demo Counsel",
  reviewer_email: "counsel@example.test",
  reviewed_at: null,
  updated_at: "2026-04-24T10:00:00.000Z",
  decision_counts: { accept: 1, reject: 0, edit: 1 },
  findings_total: 4,
  findings_reviewed: 2,
  completion_pct: 50,
} as const;

const COMPLETE_REVIEWER_DECISIONS: ReviewerDecisionListResponse = {
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
      reviewer_email: "a@example.test",
      created_at: "2026-04-24T10:00:00.000Z",
      updated_at: "2026-04-24T10:00:00.000Z",
    },
    {
      id: "decision-high-1-b",
      finding_type: "patent",
      finding_ref: "US0000000001A1",
      decision: "edit",
      note: "",
      edited_text: "",
      reviewer_user_id: "reviewer-b",
      reviewer_name: "Reviewer B",
      reviewer_email: "b@example.test",
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
      reviewer_email: "a@example.test",
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
      reviewer_email: "b@example.test",
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
      reviewer_email: "a@example.test",
      created_at: "2026-04-24T10:04:00.000Z",
      updated_at: "2026-04-24T10:04:00.000Z",
    },
  ],
  counts: { accept: 4, reject: 0, edit: 1 },
};

const CLEAN_SOURCE_REPORT = {
  ...TEST_REPORT,
  search_sources_used: ["pubchem_sdq", "surechembl"],
  source_health: {
    entries: [
      { source: "pubchem_sdq", status: "ok" },
      { source: "surechembl", status: "ok" },
    ],
  },
};

const WARNING_CAVEAT_SOURCE_REPORT = {
  ...TEST_REPORT,
  search_sources_used: ["pubchem_sdq", "surechembl"],
  source_health: {
    entries: [
      { source: "pubchem_sdq", status: "ok" },
      { source: "surechembl", status: "skipped" },
    ],
  },
};

describe("ReportPageHeader", () => {
  beforeEach(() => {
    mockWatchControlsLocked = false;
    mockWatchRecovery = null;
    mockHandleWatchRecoveryAction.mockReset();
  });

  it("replaces attorney-only report actions with a working counsel handoff for scientists", () => {
    const onPrepareHandoff = vi.fn();
    render(
      <ReportPageHeader
        analysisId="analysis-1"
        token="token"
        report={TEST_REPORT}
        currentUserRole="scientist"
        onExport={vi.fn()}
        onShare={vi.fn()}
        onFeedback={vi.fn()}
        onPrepareHandoff={onPrepareHandoff}
      />,
    );

    expect(
      screen.queryByRole("button", { name: "Review findings" }),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: "Share" }),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: "Submit feedback" }),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByRole("button", {
        name: "Review export blockers before exporting evidence packet",
      }),
    ).not.toBeInTheDocument();

    fireEvent.click(
      screen.getByRole("button", { name: "Request counsel review" }),
    );
    expect(onPrepareHandoff).toHaveBeenCalledTimes(1);
  });

  it("shows export to scientists when the authoritative capability allows it", () => {
    render(
      <ReportPageHeader
        analysisId="analysis-1"
        token="token"
        report={TEST_REPORT}
        currentUserRole="scientist"
        canExportReport
        onExport={vi.fn()}
        onShare={vi.fn()}
        onFeedback={vi.fn()}
        onPrepareHandoff={vi.fn()}
      />,
    );

    expect(
      screen.getByRole("button", {
        name: "Review export blockers before exporting evidence packet",
      }),
    ).toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: "Share" }),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: "Submit feedback" }),
    ).not.toBeInTheDocument();
  });

  it("fails closed when report collaboration role metadata is unresolved", () => {
    render(
      <ReportPageHeaderComponent
        analysisId="analysis-1"
        token="token"
        report={TEST_REPORT}
        onExport={vi.fn()}
        onShare={vi.fn()}
        onFeedback={vi.fn()}
        onPrepareHandoff={vi.fn()}
      />,
    );

    expect(
      screen.getByRole("button", { name: "Request counsel review" }),
    ).toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: "Review findings" }),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: "Share" }),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: "Submit feedback" }),
    ).not.toBeInTheDocument();
  });

  it("keeps desktop watch controls locked beside a persistent start recovery", () => {
    mockWatchControlsLocked = true;
    mockWatchRecovery = {
      mode: "outcome-unknown",
      variables: {
        kind: "start",
        variables: { analysis_id: "analysis-1", schedule: "weekly" },
      },
    };

    render(
      <ReportPageHeader
        analysisId="analysis-1"
        token="token"
        report={TEST_REPORT}
        onExport={vi.fn()}
        onShare={vi.fn()}
        onFeedback={vi.fn()}
      />,
    );

    expect(screen.getByTestId("report-watch-recovery-desktop")).toBeVisible();
    expect(
      screen.getByRole("button", { name: "Watch updating" }),
    ).toBeDisabled();
    fireEvent.click(screen.getByTestId("report-watch-recovery-desktop-action"));
    expect(mockHandleWatchRecoveryAction).toHaveBeenCalledTimes(1);
  });

  it("places the section navigator after report identity and can omit the outcome cockpit", () => {
    render(
      <ReportPageHeader
        analysisId="analysis-1"
        token="token"
        report={TEST_REPORT}
        sectionNavigation={
          <nav aria-label="Test report sections">Section navigator</nav>
        }
        showDecisionCockpit={false}
        onExport={vi.fn()}
        onShare={vi.fn()}
        onFeedback={vi.fn()}
      />,
    );

    const identity = screen.getByRole("heading", { name: "succinic acid" });
    const sectionNavigation = screen.getByRole("navigation", {
      name: "Test report sections",
    });

    expect(
      identity.compareDocumentPosition(sectionNavigation) &
        Node.DOCUMENT_POSITION_FOLLOWING,
    ).toBeTruthy();
    expect(
      screen.queryByTestId("report-decision-memo"),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByRole("region", { name: "Report readiness console" }),
    ).not.toBeInTheDocument();
  });

  it("prioritizes the decision brief before section chrome on narrow screens", () => {
    render(
      <ReportPageHeader
        analysisId="analysis-1"
        token="token"
        report={TEST_REPORT}
        sectionNavigation={
          <nav aria-label="Test report sections">Section navigator</nav>
        }
        onExport={vi.fn()}
        onShare={vi.fn()}
        onFeedback={vi.fn()}
      />,
    );

    expect(screen.getByTestId("report-section-navigation-slot")).toHaveClass(
      "order-2",
      "sm:order-1",
    );
    expect(
      screen.getByRole("region", { name: "Report decision and readiness" }),
    ).toHaveClass("order-1", "sm:order-2");
  });

  it("surfaces evidence scope and source health in the first viewport", () => {
    render(
      <ReportPageHeader
        analysisId="analysis-1"
        token="token"
        report={TEST_REPORT}
        onExport={vi.fn()}
        onShare={vi.fn()}
        onFeedback={vi.fn()}
      />,
    );

    expect(screen.getByText("Praviar FTO decision packet")).toBeInTheDocument();
    expect(
      screen.getByRole("heading", { name: "succinic acid" }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("region", { name: "succinic acid" }),
    ).toHaveAttribute("data-no-print");
    expect(screen.getAllByText(TEST_REPORT.report_id).length).toBeGreaterThan(
      0,
    );
    expect(screen.getByRole("link", { name: "succinic acid" })).toHaveAttribute(
      "href",
      "/analyses/analysis-1",
    );
    expect(
      screen.getByRole("navigation", { name: "Report breadcrumb" }),
    ).toHaveClass("lg:hidden");
    expect(screen.getAllByText("High Risk").length).toBeGreaterThan(0);
    expect(
      document.querySelector('svg[data-praviar-mark="praviar-evidence-mark"]'),
    ).toBeInTheDocument();
    const decisionMemo = screen.getByTestId("report-decision-memo");
    expect(decisionMemo).toHaveTextContent("FTO decision brief");
    expect(decisionMemo).toHaveTextContent("Decision posture");
    expect(decisionMemo).toHaveTextContent("High Risk");
    expect(decisionMemo).toHaveTextContent("Top blocker");
    expect(decisionMemo).toHaveTextContent("Reliance gate");
    expect(decisionMemo).toHaveTextContent("Evidence basis");
    expect(decisionMemo).toHaveTextContent("Next counsel action");
    expect(decisionMemo).toHaveTextContent(
      "Assign counsel review; close material findings.",
    );
    const cockpit = screen.getByTestId("report-decision-cockpit");
    expect(cockpit).toHaveAttribute("role", "group");
    expect(cockpit).toHaveAccessibleName("Decision action rail");
    expect(cockpit).toHaveTextContent("Decision action rail");
    expect(cockpit).toHaveTextContent("AI gap check");
    expect(cockpit).toHaveTextContent("Next required action");
    expect(cockpit).toHaveTextContent("Owner");
    expect(cockpit).toHaveTextContent("Reviewer / counsel");
    expect(cockpit).toHaveTextContent("Export gate");
    expect(cockpit).toHaveTextContent("Review export blockers");
    expect(screen.getByText("Priority 1")).toHaveClass("sr-only");
    expect(
      screen.getByRole("button", {
        name: "Open AI gap check from decision cockpit",
      }),
    ).toHaveClass("min-h-11");
    expect(
      screen.getByRole("button", {
        name: "Open AI gap check from decision cockpit",
      }),
    ).toHaveTextContent("Check with AI");
    expect(
      screen.getByRole("button", {
        name: "Prepare review handoff from decision cockpit",
      }),
    ).toHaveClass("min-h-11");
    expect(
      screen.getByRole("button", {
        name: "Prepare review handoff from decision cockpit",
      }),
    ).toHaveTextContent("Prepare handoff");
    expect(
      screen.getByRole("group", { name: "Report actions" }),
    ).toHaveTextContent("Decision controls");
    expect(
      screen.getByRole("group", { name: "Report actions" }),
    ).toHaveTextContent(
      "Review, critique, share, and export this packet from one governed rail.",
    );
    expect(
      screen.getByRole("group", { name: "Primary report actions" }),
    ).toHaveTextContent("Check report gaps");
    expect(
      screen.getByRole("button", {
        name: "AI-assisted report critique: readiness and evidence gaps",
      }),
    ).toBeInTheDocument();
    expect(screen.getByTestId("verdict-banner")).toHaveAttribute(
      "data-approval-status",
      "pending",
    );
    expect(screen.getByTestId("verdict-banner")).toHaveAttribute(
      "data-approval-approver",
      "",
    );
    expect(
      screen.getByRole("group", { name: "Secondary report utilities" }),
    ).toHaveTextContent("Print section");
    expect(
      screen.getByRole("button", {
        name: "Review export blockers before exporting evidence packet",
      }),
    ).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Share" })).toHaveClass(
      "min-h-11",
    );
    expect(screen.getByRole("button", { name: "Share" })).not.toHaveClass(
      "sm:min-h-9",
    );
    expect(
      screen.getByRole("button", {
        name: "Review export blockers before exporting evidence packet",
      }),
    ).toHaveClass("min-h-11");
    expect(
      screen.getByRole("button", { name: "Print current report section" }),
    ).toHaveClass("min-h-11");
    expect(screen.getByRole("button", { name: "Submit feedback" })).toHaveClass(
      "min-h-11",
    );

    const rail = screen.getByRole("region", {
      name: "Report readiness console",
    });
    expect(rail).toHaveAttribute("data-testid", "report-evidence-handoff");
    expect(screen.getByTestId("report-reliance-readiness")).toHaveClass(
      "praviar-provenance-map",
    );
    expect(screen.getByTestId("report-reliance-readiness")).toHaveClass(
      "p-3",
      "sm:p-4",
    );
    const evidenceFacts = screen.getByTestId(
      "report-evidence-facts-disclosure",
    );
    expect(evidenceFacts.tagName).toBe("DETAILS");
    expect(evidenceFacts).toHaveTextContent("Evidence facts");
    expect(evidenceFacts).toHaveTextContent(
      "Coverage, source health, and screening facts",
    );
    expect(rail).toHaveTextContent("Report readiness console");
    expect(rail).toHaveTextContent("Reliance readiness");
    expect(rail).toHaveTextContent("Authoritative state");
    expect(rail).toHaveTextContent("Ready for QA");
    expect(rail).toHaveTextContent("Reviewer / counsel");
    expect(rail).toHaveTextContent("Persisted legal review has not started.");
    expect(rail).toHaveTextContent(
      "Assign counsel review and close material findings.",
    );
    expect(rail).toHaveTextContent("AI recovery plan");
    expect(rail).toHaveTextContent(
      "Prioritized from reliance gates, evidence scope, source audit, and reviewer state, with the proof and done state attached.",
    );
    expect(rail).toHaveTextContent("3 actions");
    expect(rail).toHaveTextContent("Next required action");
    expect(rail).toHaveTextContent("Owner: Reviewer / counsel");
    expect(rail).toHaveTextContent("Counsel review required");
    expect(rail).toHaveTextContent("Reviewer judgment remains separate");
    expect(rail).toHaveTextContent("Export readiness unavailable");
    expect(rail).toHaveTextContent(
      "Readiness verification has not loaded yet.",
    );
    expect(rail).toHaveTextContent("Share caveats");
    expect(rail).toHaveTextContent("Evidence scope");
    expect(rail).toHaveTextContent("Source coverage");
    expect(rail).toHaveTextContent("Jurisdictions");
    expect(rail).toHaveTextContent("Reviewer progress");
    expect(rail).toHaveTextContent("Check for gaps");
    expect(rail).toHaveTextContent("Create review handoff");
    expect(rail).toHaveTextContent("Screening verdict");
    expect(rail).toHaveTextContent(
      "Screening result still requires legal verification.",
    );
    expect(rail).toHaveTextContent("Evidence coverage");
    expect(rail).toHaveTextContent("5 patents");
    expect(rail).toHaveTextContent("47 triaged from 2,417 found");
    expect(rail).toHaveTextContent("Source audit");
    expect(rail).toHaveTextContent("4/5 sources");
    expect(rail).toHaveTextContent("1 failed; coverage may be incomplete.");
    expect(rail).toHaveTextContent("Decision evidence");
    expect(rail).toHaveTextContent("Counsel verify");
    expect(rail).toHaveTextContent(
      "Weighted decision-input coverage; source health is shown separately.",
    );
  });

  it("opens the report monitor plan from the primary action rail", () => {
    const onMonitorPlan = vi.fn();

    render(
      <ReportPageHeader
        analysisId="analysis-1"
        token="token"
        report={TEST_REPORT}
        onExport={vi.fn()}
        onShare={vi.fn()}
        onMonitorPlan={onMonitorPlan}
        onFeedback={vi.fn()}
      />,
    );

    fireEvent.click(
      screen.getByRole("button", { name: "Open report-to-monitor plan" }),
    );

    expect(onMonitorPlan).toHaveBeenCalledTimes(1);
  });

  it("does not invent execution profile claims and warns on low evidence quality", () => {
    render(
      <ReportPageHeader
        analysisId="analysis-1"
        token="token"
        report={{
          ...TEST_REPORT,
          execution_profile: undefined,
          clearance_decision: {
            ...TEST_REPORT.clearance_decision,
            evidence_quality: 0,
          },
        }}
        onExport={vi.fn()}
        onShare={vi.fn()}
        onFeedback={vi.fn()}
      />,
    );

    expect(
      screen.getByText("Execution profile not reported"),
    ).toBeInTheDocument();
    expect(screen.queryByText("Adaptive pipeline")).not.toBeInTheDocument();
    const rail = screen.getByRole("region", {
      name: "Report readiness console",
    });
    expect(rail).toHaveTextContent("Low decision-evidence score");
  });

  it.each([
    { score: 0.21, label: "Low decision-evidence score (21%)", tone: "danger" },
    { score: 0.59, label: "Low decision-evidence score (59%)", tone: "danger" },
    { score: 0.6, label: "60% decision-evidence score", tone: "warning" },
    { score: 0.79, label: "79% decision-evidence score", tone: "warning" },
    { score: 0.8, label: "80% decision-evidence score", tone: "neutral" },
  ])(
    "applies the confidence policy to a $score evidence score",
    ({ score, label, tone }) => {
      render(
        <ReportPageHeader
          analysisId="analysis-1"
          token="token"
          report={{
            ...TEST_REPORT,
            clearance_decision: {
              ...TEST_REPORT.clearance_decision,
              evidence_quality: score,
            },
          }}
          onExport={vi.fn()}
          onShare={vi.fn()}
          onFeedback={vi.fn()}
        />,
      );

      const evidenceValue = screen
        .getAllByText(label)
        .find((element) => element.closest(".praviar-evidence-fact-card"));
      expect(evidenceValue).toBeDefined();
      expect(
        evidenceValue?.closest(".praviar-evidence-fact-card"),
      ).toHaveAttribute("data-evidence-tone", tone);
    },
  );

  it("uses workspace and review readiness to block reliance and trigger high-value actions", async () => {
    const onAskAi = vi.fn();
    const onExport = vi.fn();
    const onPrepareHandoff = vi.fn();
    const askAiButtonRef = createRef<HTMLButtonElement>();

    render(
      <ReportPageHeader
        analysisId="analysis-1"
        token="token"
        report={TEST_REPORT}
        workspaceSummary={BLOCKED_WORKSPACE_SUMMARY}
        reviewStatus={REVIEW_STATUS}
        onExport={onExport}
        onShare={vi.fn()}
        onFeedback={vi.fn()}
        onAskAi={onAskAi}
        askAiButtonRef={askAiButtonRef}
        onPrepareHandoff={onPrepareHandoff}
      />,
    );

    const readiness = screen.getByTestId("report-reliance-readiness");
    expect(readiness).toHaveTextContent("Reliance readiness");
    expect(readiness).toHaveTextContent("Not ready for reliance");
    expect(readiness).toHaveTextContent("Not reviewable");
    expect(screen.getByTestId("verdict-banner")).toHaveAttribute(
      "data-approval-status",
      "under_review",
    );
    expect(screen.getByTestId("verdict-banner")).toHaveAttribute(
      "data-approval-approver",
      "Demo Counsel",
    );
    expect(screen.getByTestId("verdict-banner")).toHaveAttribute(
      "data-approval-approved-at",
      "",
    );
    expect(readiness).toHaveTextContent("Report owner");
    expect(readiness).toHaveTextContent(
      "Resolve the blocker, then rerun export readiness checks.",
    );
    expect(readiness).toHaveTextContent(
      "Counsel export remains blocked until jurisdictions are reviewed.",
    );
    expect(readiness).toHaveTextContent("AI recovery plan");
    expect(readiness).toHaveTextContent("Next required action");
    expect(readiness).toHaveTextContent("Owner: Report owner");
    expect(readiness).toHaveTextContent("US, EP lanes block export.");
    expect(readiness).toHaveTextContent(
      "Report-grounded evidence only for this run.",
    );
    expect(readiness).toHaveTextContent("2 in scope");
    expect(readiness).toHaveTextContent("50%");
    expect(readiness).toHaveTextContent(
      "2 / 4 findings reviewed; 1 accepted / 1 edited.",
    );
    const cockpit = screen.getByTestId("report-decision-cockpit");
    expect(cockpit).toHaveTextContent("Next required action");
    expect(cockpit).toHaveTextContent("Resolve the blocker");
    expect(cockpit).toHaveTextContent("Owner");
    expect(cockpit).toHaveTextContent("Report owner");
    expect(cockpit).toHaveTextContent("Export gate");
    expect(cockpit).toHaveTextContent("Review export blockers");

    const askAiButton = screen.getByRole("button", {
      name: "AI-assisted gap check: reliance readiness",
    });
    const exportRecoveryButton = screen.getByRole("button", {
      name: "Run recovery check with AI",
    });
    fireEvent.click(
      screen.getByRole("button", {
        name: "Open AI gap check from decision cockpit",
      }),
    );
    expect(askAiButtonRef.current).toBe(askAiButton);
    expect(
      screen.getByRole("button", {
        name: "Review export blockers before exporting evidence packet",
      }),
    ).toHaveTextContent("Review export blockers");

    fireEvent.click(askAiButton);
    fireEvent.click(
      screen.getByRole("button", { name: /Create review handoff/i }),
    );
    fireEvent.click(
      screen.getByRole("button", {
        name: "Review export blockers before exporting evidence packet",
      }),
    );

    expect(onAskAi).toHaveBeenCalledWith(
      expect.objectContaining({
        description: expect.stringContaining("report readiness console"),
        intent: "report",
        metadata: expect.arrayContaining([
          { label: "Export", value: "blocked" },
          { label: "Review", value: "50% complete" },
          { label: "Reliance state", value: "Not reviewable" },
          { label: "Reliance owner", value: "Report owner" },
          { label: "Jurisdictions", value: "US, EP" },
          expect.objectContaining({
            label: "Decision queue",
            value: expect.stringContaining("Next required action"),
          }),
        ]),
        prompt: expect.stringContaining("Critique the reliance readiness"),
        title: "succinic acid reliance gaps",
      }),
    );
    expect(onExport).not.toHaveBeenCalled();
    await waitFor(() => expect(exportRecoveryButton).toHaveFocus());
    expect(onPrepareHandoff).toHaveBeenCalledWith(
      expect.objectContaining({
        body: expect.stringContaining("**Praviar reliance handoff**"),
        promote_to_under_review: true,
        review_note: expect.stringContaining("report readiness console"),
        target_id: "analysis-1",
        target_type: "analysis",
      }),
    );
    const [handoffDraft] = onPrepareHandoff.mock.calls[0];
    expect(handoffDraft.body).toContain(`Report: ${TEST_REPORT.report_id}`);
    expect(handoffDraft.body).toContain("Compound: succinic acid");
    expect(handoffDraft.body).toContain("Risk: High Risk");
    expect(handoffDraft.body).toContain("Reliance state: Not reviewable");
    expect(handoffDraft.body).toContain("Reliance owner: Report owner");
    expect(handoffDraft.body).toContain(
      "Next action: Resolve the blocker, then rerun export readiness checks.",
    );
    expect(handoffDraft.body).toContain("Decision queue:");
    expect(handoffDraft.body).toContain(
      "P1 Next required action (Report owner): Resolve the blocker, then rerun export readiness checks.",
    );
    expect(handoffDraft.body).toContain("Export readiness: Blocked");
    expect(handoffDraft.body).toContain("Blocking jurisdictions: US, EP");
    expect(handoffDraft.body).toContain(
      "Reviewer progress: 2 / 4 findings reviewed",
    );
    expect(handoffDraft.body).toContain(
      "Evidence scope: Report evidence - Report-grounded evidence only for this run.",
    );
  });

  it("does not require counsel review again after approval is recorded", () => {
    render(
      <ReportPageHeader
        analysisId="analysis-1"
        token="token"
        report={TEST_REPORT}
        workspaceSummary={{
          ...BLOCKED_WORKSPACE_SUMMARY,
          opinion_readiness: {
            export_ready: true,
            summary: "Backend export readiness cleared.",
            jurisdictions_blocking_export: [],
          },
        }}
        reviewStatus={{
          ...REVIEW_STATUS,
          status: "approved",
          reviewed_at: "2026-04-24T10:00:00.000Z",
          findings_reviewed: 4,
          completion_pct: 100,
        }}
        reviewerDecisions={COMPLETE_REVIEWER_DECISIONS}
        onExport={vi.fn()}
        onShare={vi.fn()}
        onFeedback={vi.fn()}
      />,
    );

    const readiness = screen.getByTestId("report-reliance-readiness");

    expect(screen.getByTestId("verdict-banner")).toHaveAttribute(
      "data-approval-status",
      "approved",
    );
    expect(screen.getByTestId("verdict-banner")).toHaveAttribute(
      "data-approval-approver",
      "Demo Counsel",
    );
    expect(screen.getByTestId("verdict-banner")).toHaveAttribute(
      "data-approval-approved-at",
      "2026-04-24T10:00:00.000Z",
    );
    expect(readiness).toHaveTextContent("Not ready for reliance");
    expect(readiness).toHaveTextContent("Readiness signals");
    expect(readiness).not.toHaveTextContent("Readiness blockers");
    expect(readiness).toHaveTextContent("Reviewer approval is recorded");
    expect(readiness).not.toHaveTextContent("Counsel review required");
    expect(
      screen.getByRole("button", {
        name: "Prepare evidence packet export with source caveat",
      }),
    ).toHaveTextContent("Prepare export with source caveat");
  });

  it("uses a warning state for approved reports with warning-only source caveats", () => {
    render(
      <ReportPageHeader
        analysisId="analysis-1"
        token="token"
        report={WARNING_CAVEAT_SOURCE_REPORT as typeof TEST_REPORT}
        workspaceSummary={{
          ...BLOCKED_WORKSPACE_SUMMARY,
          opinion_readiness: {
            export_ready: true,
            summary: "Backend export readiness cleared.",
            jurisdictions_blocking_export: [],
          },
        }}
        reviewStatus={{
          ...REVIEW_STATUS,
          status: "approved",
          findings_reviewed: 4,
          completion_pct: 100,
        }}
        reviewerDecisions={COMPLETE_REVIEWER_DECISIONS}
        onExport={vi.fn()}
        onShare={vi.fn()}
        onFeedback={vi.fn()}
      />,
    );

    const readiness = screen.getByTestId("report-reliance-readiness");
    expect(readiness).toHaveTextContent("Counsel-approved with caveats");
    expect(readiness).not.toHaveTextContent("Not ready for reliance");
    expect(readiness).toHaveTextContent(
      "1 skipped; coverage may be incomplete.",
    );
  });

  it("labels clean approved readiness without caveats", () => {
    const onPrepareHandoff = vi.fn();
    render(
      <ReportPageHeader
        analysisId="analysis-1"
        token="token"
        report={CLEAN_SOURCE_REPORT as typeof TEST_REPORT}
        workspaceSummary={{
          ...BLOCKED_WORKSPACE_SUMMARY,
          opinion_readiness: {
            export_ready: true,
            summary: "Backend export readiness cleared.",
            jurisdictions_blocking_export: [],
          },
        }}
        reviewStatus={{
          ...REVIEW_STATUS,
          status: "approved",
          findings_reviewed: 4,
          completion_pct: 100,
        }}
        reviewerDecisions={COMPLETE_REVIEWER_DECISIONS}
        onExport={vi.fn()}
        onShare={vi.fn()}
        onFeedback={vi.fn()}
        onPrepareHandoff={onPrepareHandoff}
      />,
    );

    const readiness = screen.getByTestId("report-reliance-readiness");
    expect(readiness).toHaveTextContent("Counsel review recorded");
    expect(readiness).not.toHaveTextContent("Counsel-approved with caveats");
    expect(readiness).toHaveTextContent(
      "Backend readiness indicates export can proceed.",
    );
    expect(readiness).not.toHaveTextContent("proceed with caveats");
    expect(
      screen.getByRole("button", { name: "Export evidence packet" }),
    ).toHaveTextContent("Export evidence packet");

    fireEvent.click(
      screen.getByRole("button", { name: "Create review handoff" }),
    );

    expect(onPrepareHandoff).toHaveBeenCalledWith(
      expect.objectContaining({
        body: expect.stringContaining("Export readiness: Ready"),
      }),
    );
  });

  it("warns when an active external share is not recipient-bound", () => {
    render(
      <ReportPageHeader
        analysisId="analysis-1"
        token="token"
        report={CLEAN_SOURCE_REPORT as typeof TEST_REPORT}
        shareActive
        shareRecipientBound={false}
        workspaceSummary={{
          ...BLOCKED_WORKSPACE_SUMMARY,
          opinion_readiness: {
            export_ready: true,
            summary: "Backend export readiness cleared.",
            jurisdictions_blocking_export: [],
          },
        }}
        reviewStatus={{
          ...REVIEW_STATUS,
          status: "approved",
          findings_reviewed: 4,
          completion_pct: 100,
        }}
        reviewerDecisions={COMPLETE_REVIEWER_DECISIONS}
        onExport={vi.fn()}
        onShare={vi.fn()}
        onFeedback={vi.fn()}
      />,
    );

    const readiness = screen.getByTestId("report-reliance-readiness");

    expect(readiness).toHaveTextContent("Active share is not confirmed");
    expect(readiness).toHaveTextContent(
      "Reissue the share to a named, mailbox-verified recipient.",
    );
    expect(readiness).not.toHaveTextContent("protected for external sharing");
  });

  it("keeps export locked when approved review is missing material reviewer decisions", () => {
    const onExport = vi.fn();

    render(
      <ReportPageHeader
        analysisId="analysis-1"
        token="token"
        report={CLEAN_SOURCE_REPORT as typeof TEST_REPORT}
        workspaceSummary={{
          ...BLOCKED_WORKSPACE_SUMMARY,
          opinion_readiness: {
            export_ready: true,
            summary: "Backend export readiness cleared.",
            jurisdictions_blocking_export: [],
          },
        }}
        reviewStatus={{
          ...REVIEW_STATUS,
          status: "approved",
          findings_reviewed: 4,
          completion_pct: 100,
        }}
        reviewerDecisions={{
          ...COMPLETE_REVIEWER_DECISIONS,
          items: COMPLETE_REVIEWER_DECISIONS.items.filter(
            (item) =>
              item.id === "decision-high-1-a" ||
              item.id === "decision-medium-1-a",
          ),
        }}
        onExport={onExport}
        onShare={vi.fn()}
        onFeedback={vi.fn()}
      />,
    );

    const readiness = screen.getByTestId("report-reliance-readiness");
    expect(readiness).toHaveTextContent("Reviewer decisions incomplete");
    expect(readiness).toHaveTextContent(
      "HIGH finding US0000000002A1 has no reviewer decision.",
    );
    expect(readiness).toHaveTextContent(
      "HIGH finding US0000000001A1 requires dual review before export.",
    );

    const recoveryBrief = screen.getByTestId("report-export-recovery-brief");
    expect(recoveryBrief).toHaveTextContent("Export locked");
    expect(recoveryBrief).toHaveTextContent("AI-assisted recovery");
    expect(recoveryBrief).toHaveTextContent(
      "This recovery plan is decision support, not legal advice or a legal clearance opinion.",
    );
    expect(recoveryBrief).toHaveTextContent("Done when");
    expect(
      screen.getByRole("button", { name: "Run recovery check with AI" }),
    ).toHaveClass("min-h-11");
    expect(
      screen.getByRole("button", {
        name: "Prepare recovery handoff from export recovery brief",
      }),
    ).toHaveClass("min-h-11");

    const exportButton = screen.getByRole("button", {
      name: "Review export blockers before exporting evidence packet",
    });
    expect(exportButton).toHaveTextContent("Review export blockers");

    fireEvent.click(exportButton);

    expect(onExport).not.toHaveBeenCalled();
    expect(recoveryBrief.closest("details")).toHaveAttribute("open");
  });

  it("does not show export ready while persisted legal review still blocks export", () => {
    render(
      <ReportPageHeader
        analysisId="analysis-1"
        token="token"
        report={TEST_REPORT}
        workspaceSummary={{
          ...BLOCKED_WORKSPACE_SUMMARY,
          opinion_readiness: {
            export_ready: true,
            summary: "Backend export readiness cleared.",
            jurisdictions_blocking_export: [],
          },
        }}
        reviewStatus={REVIEW_STATUS}
        onExport={vi.fn()}
        onShare={vi.fn()}
        onFeedback={vi.fn()}
      />,
    );

    const readiness = screen.getByTestId("report-reliance-readiness");

    expect(readiness).toHaveTextContent("Counsel review required");
    expect(readiness).not.toHaveTextContent("Export review ready");
    expect(
      screen.getByRole("button", {
        name: "Review export blockers before exporting evidence packet",
      }),
    ).toHaveTextContent("Review export blockers");
  });

  it("shows verification-in-progress copy while desktop readiness queries are loading", () => {
    render(
      <ReportPageHeader
        analysisId="analysis-1"
        token="token"
        report={TEST_REPORT}
        reviewStatusLoading
        workspaceSummaryLoading
        onExport={vi.fn()}
        onShare={vi.fn()}
        onFeedback={vi.fn()}
      />,
    );

    const readiness = screen.getByTestId("report-reliance-readiness");

    expect(readiness).toHaveTextContent("Readiness verification in progress");
    expect(readiness).toHaveTextContent(
      "Review status verification in progress",
    );
    expect(readiness).not.toHaveTextContent("Export readiness unavailable");
    expect(readiness).not.toHaveTextContent("Persisted legal review required");
    expect(
      screen.getByRole("button", {
        name: "Verify export readiness before exporting evidence packet",
      }),
    ).toHaveTextContent("Verify export readiness");
  });

  it("mirrors export-dialog blockers when backend readiness is true outside counsel mode", () => {
    const onAskAi = vi.fn();
    const onPrepareHandoff = vi.fn();

    render(
      <ReportPageHeader
        analysisId="analysis-1"
        token="token"
        report={TEST_REPORT}
        workspaceSummary={{
          ...BLOCKED_WORKSPACE_SUMMARY,
          trust_mode: "explorer",
          opinion_readiness: {
            export_ready: true,
            summary: "Backend export readiness cleared.",
            jurisdictions_blocking_export: [],
          },
        }}
        reviewStatus={{
          ...REVIEW_STATUS,
          status: "approved",
          findings_reviewed: 4,
          completion_pct: 100,
        }}
        reviewerDecisions={COMPLETE_REVIEWER_DECISIONS}
        onExport={vi.fn()}
        onShare={vi.fn()}
        onFeedback={vi.fn()}
        onAskAi={onAskAi}
        onPrepareHandoff={onPrepareHandoff}
      />,
    );

    const readiness = screen.getByTestId("report-reliance-readiness");
    expect(readiness).toHaveTextContent("Counsel export mode required");
    expect(readiness).toHaveTextContent(
      "Current trust mode is explorer, not counsel.",
    );
    expect(readiness).not.toHaveTextContent("Export review ready");

    fireEvent.click(
      screen.getByRole("button", {
        name: "AI-assisted gap check: reliance readiness",
      }),
    );
    fireEvent.click(
      screen.getByRole("button", { name: /Create review handoff/i }),
    );

    expect(onAskAi).toHaveBeenCalledWith(
      expect.objectContaining({
        metadata: expect.arrayContaining([
          { label: "Export", value: "blocked" },
        ]),
      }),
    );
    const [handoffDraft] = onPrepareHandoff.mock.calls[0];
    expect(handoffDraft.body).toContain("Export readiness: Blocked");
  });

  it("keeps every readiness blocker in the panel, AI context, and handoff", () => {
    const onAskAi = vi.fn();
    const onPrepareHandoff = vi.fn();

    render(
      <ReportPageHeader
        analysisId="analysis-1"
        token="token"
        report={TEST_REPORT}
        workspaceSummary={{
          ...BLOCKED_WORKSPACE_SUMMARY,
          trust_mode: "explorer",
        }}
        reviewStatus={{
          ...REVIEW_STATUS,
          status: "approved",
          findings_reviewed: 4,
          completion_pct: 100,
        }}
        reviewerDecisions={COMPLETE_REVIEWER_DECISIONS}
        onExport={vi.fn()}
        onShare={vi.fn()}
        onFeedback={vi.fn()}
        onAskAi={onAskAi}
        onPrepareHandoff={onPrepareHandoff}
      />,
    );

    const readiness = screen.getByTestId("report-reliance-readiness");
    expect(readiness).toHaveTextContent("Counsel export mode required");
    expect(readiness).toHaveTextContent(
      "Current trust mode is explorer, not counsel.",
    );
    expect(readiness).toHaveTextContent("Export blocked");
    expect(readiness).toHaveTextContent("US, EP lanes block export.");
    expect(readiness).toHaveTextContent("Share caveats");

    fireEvent.click(
      screen.getByRole("button", {
        name: "AI-assisted gap check: reliance readiness",
      }),
    );
    fireEvent.click(
      screen.getByRole("button", { name: /Create review handoff/i }),
    );

    expect(onAskAi).toHaveBeenCalledWith(
      expect.objectContaining({
        metadata: expect.arrayContaining([
          expect.objectContaining({
            label: "Readiness blockers",
            value: expect.stringContaining("Counsel export mode required"),
          }),
        ]),
      }),
    );
    const aiContext = onAskAi.mock.calls[0][0];
    const readinessBlockers = aiContext.metadata.find(
      (entry: { label: string }) => entry.label === "Readiness blockers",
    );
    expect(readinessBlockers.value).toContain("Export blocked");
    expect(readinessBlockers.value).toContain("US, EP lanes block export.");

    const [handoffDraft] = onPrepareHandoff.mock.calls[0];
    expect(handoffDraft.body).toContain(
      "Counsel export mode required: Current trust mode is explorer, not counsel.",
    );
    expect(handoffDraft.body).toContain(
      "Export blocked: US, EP lanes block export.",
    );
  });

  it("does not invent a zero found count when total_patents_found is absent", () => {
    render(
      <ReportPageHeader
        analysisId="analysis-1"
        token="token"
        report={{
          ...TEST_REPORT,
          total_patents_found: undefined,
        }}
        onExport={vi.fn()}
        onShare={vi.fn()}
        onFeedback={vi.fn()}
      />,
    );

    const rail = screen.getByRole("region", {
      name: "Report readiness console",
    });

    expect(rail).toHaveTextContent("47 triaged; found count not reported.");
    expect(rail).not.toHaveTextContent("47 triaged from 0 found");
  });

  it("shows governed handoff status without opening export", () => {
    const onOpenComments = vi.fn();
    const onExport = vi.fn();

    render(
      <ReportPageHeader
        analysisId="analysis-1"
        token="token"
        report={TEST_REPORT}
        onExport={onExport}
        onShare={vi.fn()}
        onFeedback={vi.fn()}
        onOpenComments={onOpenComments}
        onPrepareHandoff={vi.fn()}
        reviewHandoffState={{
          commentId: "comment-1",
          reviewStatusLabel: "Under review",
        }}
      />,
    );

    expect(
      screen.getByRole("status", { name: "Review handoff status" }),
    ).toHaveTextContent("Review handoff created");
    expect(screen.getByText(/Comment comment-1/)).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: /Open comments tab/i }));

    expect(onOpenComments).toHaveBeenCalledTimes(1);
    expect(onExport).not.toHaveBeenCalled();
  });

  it("surfaces the adaptive execution profile when the report declares it", () => {
    render(
      <ReportPageHeader
        analysisId="analysis-1"
        token="token"
        report={{
          ...TEST_REPORT,
          execution_profile: "world_class_adaptive",
        }}
        onExport={vi.fn()}
        onShare={vi.fn()}
        onFeedback={vi.fn()}
      />,
    );

    expect(screen.getByText("Adaptive pipeline")).toBeInTheDocument();
    expect(
      screen.queryByText("Execution profile not reported"),
    ).not.toBeInTheDocument();
  });

  it("does not imply complete source health when source audit entries are absent", () => {
    render(
      <ReportPageHeader
        analysisId="analysis-1"
        token="token"
        report={{
          ...TEST_REPORT,
          source_health: { entries: [] },
        }}
        onExport={vi.fn()}
        onShare={vi.fn()}
        onFeedback={vi.fn()}
      />,
    );

    const rail = screen.getByRole("region", {
      name: "Report readiness console",
    });
    expect(rail).toHaveTextContent("5 sources listed");
    expect(rail).toHaveTextContent("Source health not reported");
    expect(rail).toHaveTextContent("verify coverage");
  });

  it("uses info styling for clear-risk screening without implying legal clearance", () => {
    render(
      <ReportPageHeader
        analysisId="analysis-1"
        token="token"
        report={{
          ...TEST_REPORT,
          risk_summary: {
            ...TEST_REPORT.risk_summary,
            overall_risk: "clear",
            blocking_patents_count: 0,
          },
        }}
        onExport={vi.fn()}
        onShare={vi.fn()}
        onFeedback={vi.fn()}
      />,
    );

    const headerBadge = screen
      .getAllByText("No Blockers")
      .find((element) => element.tagName.toLowerCase() === "span");
    expect(headerBadge).toHaveClass("text-[var(--color-info-badge-fg)]");
    expect(headerBadge?.className).not.toContain("text-error");

    const screeningFact = screen
      .getByText("Screening verdict")
      .closest(".praviar-evidence-fact-card");
    expect(screeningFact?.querySelector('[aria-hidden="true"]')).toHaveClass(
      "text-info",
    );
    expect(screeningFact).toHaveTextContent("Screening verdict");
    expect(screeningFact).toHaveTextContent(
      "Screening result still requires legal verification.",
    );
  });

  it("notifies the report page before opening reviewer decisions", () => {
    const onReviewOpen = vi.fn();

    render(
      <ReportPageHeader
        analysisId="analysis-1"
        token="token"
        report={TEST_REPORT}
        onExport={vi.fn()}
        onShare={vi.fn()}
        onFeedback={vi.fn()}
        onReviewOpen={onReviewOpen}
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: "Review findings" }));

    expect(onReviewOpen).toHaveBeenCalledTimes(1);
  });

  it("promotes active share handoff status into the command deck", () => {
    render(
      <ReportPageHeader
        analysisId="analysis-1"
        token="token"
        report={TEST_REPORT}
        shareActive
        shareViewCount={7}
        shareLastViewedAt={null}
        onExport={vi.fn()}
        onShare={vi.fn()}
        onFeedback={vi.fn()}
      />,
    );

    const actionGroup = screen.getByRole("group", { name: "Report actions" });

    expect(actionGroup).toHaveTextContent("External share active");
    expect(actionGroup).toHaveTextContent("7 views");
    expect(actionGroup).toHaveTextContent("Last viewed never");
    expect(
      screen.getByRole("status", { name: "External share status" }),
    ).toBeInTheDocument();
    expect(screen.getByText("Share analytics")).toBeInTheDocument();
  });

  it("uses singular copy for one active share view", () => {
    render(
      <ReportPageHeader
        analysisId="analysis-1"
        token="token"
        report={TEST_REPORT}
        shareActive
        shareViewCount={1}
        shareLastViewedAt={null}
        onExport={vi.fn()}
        onShare={vi.fn()}
        onFeedback={vi.fn()}
      />,
    );

    const actionGroup = screen.getByRole("group", { name: "Report actions" });

    expect(actionGroup).toHaveTextContent("1 view");
    expect(actionGroup).not.toHaveTextContent("1 views");
  });

  it("treats not configured sources as incomplete coverage", () => {
    render(
      <ReportPageHeader
        analysisId="analysis-1"
        token="token"
        report={{
          ...TEST_REPORT,
          source_health: {
            entries: [
              {
                source: "pubchem_sdq",
                status: "ok",
                patent_count: 847,
                error_message: "",
              },
              {
                source: "surechembl",
                status: "ok",
                patent_count: 1203,
                error_message: "",
              },
              {
                source: "bigquery",
                status: "ok",
                patent_count: 312,
                error_message: "",
              },
              {
                source: "bigquery_annotations",
                status: "ok",
                patent_count: 55,
                error_message: "",
              },
              {
                source: "patcid",
                status: "not_configured",
                patent_count: 0,
                error_message: "",
              },
            ],
          },
        }}
        onExport={vi.fn()}
        onShare={vi.fn()}
        onFeedback={vi.fn()}
      />,
    );

    const rail = screen.getByRole("region", {
      name: "Report readiness console",
    });
    expect(rail).toHaveAccessibleName("Report readiness console");
    expect(rail).toHaveTextContent("4/5 sources");
    expect(rail).toHaveTextContent("1 not configured");
    expect(rail).toHaveTextContent("coverage may be incomplete");
  });

  it("contains hostile long report identifiers and compound names in header chrome", () => {
    const longAnalysisId = `ana-2026-0142-${"LONG".repeat(20)}`;
    const artifactReportId = `rpt-2026-0142-${"ARTIFACT".repeat(12)}`;
    const longCompoundName = `N-(4-hydroxyphenyl)-${"very-long-compound-".repeat(
      8,
    )}`;

    render(
      <ReportPageHeader
        analysisId={longAnalysisId}
        token="token"
        report={{
          ...TEST_REPORT,
          report_id: artifactReportId,
          compound: {
            ...TEST_REPORT.compound,
            name: longCompoundName,
          },
        }}
        onExport={vi.fn()}
        onShare={vi.fn()}
        onFeedback={vi.fn()}
      />,
    );

    const breadcrumbLink = screen.getByRole("link", {
      name: longCompoundName,
    });
    const breadcrumbLabel = within(breadcrumbLink).getByText(longCompoundName);

    expect(breadcrumbLink).toHaveAccessibleName(longCompoundName);
    expect(breadcrumbLink).toHaveAttribute("title", longCompoundName);
    expect(breadcrumbLink).toHaveTextContent(longCompoundName);
    expect(breadcrumbLabel).toHaveClass(
      "w-full",
      "max-w-full",
      "overflow-hidden",
      "text-ellipsis",
      "whitespace-nowrap",
    );
    expect(screen.getByRole("heading", { name: longCompoundName })).toHaveClass(
      "[overflow-wrap:anywhere]",
    );
    expect(
      screen
        .getAllByText(artifactReportId)
        .some((element) =>
          element.className.includes("[overflow-wrap:anywhere]"),
        ),
    ).toBe(true);
    expect(
      screen
        .getAllByText(artifactReportId)
        .some((element) => element.className.includes("truncate")),
    ).toBe(true);
    expect(breadcrumbLink).toHaveAttribute(
      "href",
      `/analyses/${longAnalysisId}`,
    );
  });
});
