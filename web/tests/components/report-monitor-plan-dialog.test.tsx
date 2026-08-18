import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { ReportMonitorPlanDialog } from "@/components/report-page/report-monitor-plan-dialog";
import { TEST_REPORT } from "../fixtures/report-fixture";

const handleWatchToggle = vi.fn();
const handleWatchRecoveryAction = vi.fn();
let mockWatchEnabled = false;
let mockWatchControlsLocked = false;
let mockWatchRecovery: {
  mode: "failed" | "outcome-unknown";
  variables: {
    kind: "start";
    variables: { analysis_id: string; schedule: string };
  };
} | null = null;
let mockMonitor:
  | {
      last_run_status: "pending" | "ready" | "running" | "error";
    }
  | undefined;

vi.mock("@/components/report-page/use-report-watch-control", () => ({
  useSharedReportWatchControl: () => ({
    monitor: mockMonitor,
    watchControlsLocked: mockWatchControlsLocked,
    watchEnabled: mockWatchEnabled,
    watchPending: false,
    watchRecovery: mockWatchRecovery,
    watchSchedule: "weekly",
    handleWatchRecoveryAction,
    handleWatchToggle,
  }),
}));

describe("ReportMonitorPlanDialog", () => {
  beforeEach(() => {
    handleWatchToggle.mockReset();
    handleWatchRecoveryAction.mockReset();
    mockWatchEnabled = false;
    mockWatchControlsLocked = false;
    mockWatchRecovery = null;
    mockMonitor = undefined;
  });

  it("summarizes report-derived monitor targets and starts the plan", () => {
    render(
      <ReportMonitorPlanDialog
        analysisId="analysis-1"
        open
        report={TEST_REPORT}
        workspaceSummary={{
          analysis_id: "analysis-1",
          report_id: "rpt_demo_succinic_001",
          trust_mode: "counsel",
          target_jurisdictions: ["US", "EP"],
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
          opinion_readiness: {},
          data_coverage: {},
          source_convergence: {},
          uncertainty_register: [],
          evidence_scope: {
            mode: "report_evidence",
            external_live_retrieval: false,
            comment_routing_available: true,
            sources_considered: [],
            governed_note: "Report grounded.",
            provider_capabilities: [],
            providers: [],
            hybrid_evidence_ready: false,
          },
        }}
        onOpenChange={vi.fn()}
      />,
    );

    expect(screen.getByText("Report-to-monitor plan")).toBeInTheDocument();
    expect(
      screen.getByText("rpt_demo_succinic_001 / Counsel"),
    ).toBeInTheDocument();
    expect(screen.getByText("US, EP")).toBeInTheDocument();
    expect(screen.getByText("Queued after activation")).toBeInTheDocument();
    expect(screen.getByText("US0000000001A1")).toBeInTheDocument();
    expect(screen.getByText("Report patent targets")).toBeInTheDocument();
    expect(
      screen.getByText(/activation seeds every report patent target/i),
    ).toBeInTheDocument();
    expect(screen.queryByText("Watched families")).not.toBeInTheDocument();
    expect(screen.getByText(/Prioritizes report patents/i)).toBeInTheDocument();
    expect(
      screen.queryByRole("option", { name: "Bi-weekly" }),
    ).not.toBeInTheDocument();

    fireEvent.change(screen.getByLabelText("Cadence"), {
      target: { value: "daily" },
    });
    const startMonitorPlan = screen.getByRole("button", {
      name: "Start monitor plan",
    });
    expect(startMonitorPlan).toHaveClass("min-h-11");
    fireEvent.click(startMonitorPlan);

    expect(handleWatchToggle).toHaveBeenCalledWith(true, "daily");
  });

  it("labels a definitive start failure as a revision action", () => {
    mockWatchControlsLocked = true;
    mockWatchRecovery = {
      mode: "failed",
      variables: {
        kind: "start",
        variables: { analysis_id: "analysis-1", schedule: "weekly" },
      },
    };

    render(
      <ReportMonitorPlanDialog
        analysisId="analysis-1"
        open
        report={TEST_REPORT}
        onOpenChange={vi.fn()}
      />,
    );

    fireEvent.click(
      screen.getByRole("button", { name: "Revise watch request" }),
    );

    expect(handleWatchRecoveryAction).toHaveBeenCalledTimes(1);
    expect(
      screen.queryByRole("button", { name: "Review watch plan" }),
    ).not.toBeInTheDocument();
  });

  it("shows existing monitor status and pause/update actions", () => {
    mockWatchEnabled = true;
    mockMonitor = { last_run_status: "ready" };

    render(
      <ReportMonitorPlanDialog
        analysisId="analysis-1"
        open
        report={TEST_REPORT}
        onOpenChange={vi.fn()}
      />,
    );

    expect(screen.getByText("Ready")).toBeInTheDocument();

    const pauseMonitor = screen.getByRole("button", { name: "Pause monitor" });
    expect(pauseMonitor).toHaveClass("min-h-11");
    fireEvent.click(pauseMonitor);
    expect(handleWatchToggle).toHaveBeenCalledWith(false, "weekly");

    const updateMonitorPlan = screen.getByRole("button", {
      name: "Update monitor plan",
    });
    expect(updateMonitorPlan).toHaveClass("min-h-11");
    fireEvent.click(updateMonitorPlan);
    expect(handleWatchToggle).toHaveBeenCalledWith(true, "weekly");
  });

  it("normalizes stale seeded cadences before monitor actions", () => {
    render(
      <ReportMonitorPlanDialog
        analysisId="analysis-1"
        open
        report={TEST_REPORT}
        workspaceSummary={{
          analysis_id: "analysis-1",
          report_id: "rpt_demo_succinic_001",
          trust_mode: "counsel",
          target_jurisdictions: ["US"],
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
            schedule: "biweekly" as "weekly",
            source_report_id: "rpt_demo_succinic_001",
            source_trust_mode: "counsel",
            requires_manual_input: false,
            missing_fields: [],
          },
          routing_profile: {},
          opinion_readiness: {},
          data_coverage: {},
          source_convergence: {},
          uncertainty_register: [],
          evidence_scope: {
            mode: "report_evidence",
            external_live_retrieval: false,
            comment_routing_available: true,
            sources_considered: [],
            governed_note: "Report grounded.",
            provider_capabilities: [],
            providers: [],
            hybrid_evidence_ready: false,
          },
        }}
        onOpenChange={vi.fn()}
      />,
    );

    expect(screen.getByDisplayValue("Weekly")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Start monitor plan" }));

    expect(handleWatchToggle).toHaveBeenCalledWith(true, "weekly");
  });

  it("keeps dialog controls locked beside a persistent start recovery", () => {
    mockWatchControlsLocked = true;
    mockWatchRecovery = {
      mode: "outcome-unknown",
      variables: {
        kind: "start",
        variables: { analysis_id: "analysis-1", schedule: "weekly" },
      },
    };

    render(
      <ReportMonitorPlanDialog
        analysisId="analysis-1"
        open
        report={TEST_REPORT}
        onOpenChange={vi.fn()}
      />,
    );

    expect(screen.getByTestId("report-watch-recovery-dialog")).toBeVisible();
    expect(screen.getByLabelText("Cadence")).toBeDisabled();
    expect(
      screen.getByRole("button", { name: "Start monitor plan" }),
    ).toBeDisabled();

    fireEvent.click(screen.getByTestId("report-watch-recovery-dialog-action"));
    expect(handleWatchRecoveryAction).toHaveBeenCalledTimes(1);
  });
});
