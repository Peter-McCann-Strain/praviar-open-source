import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import type React from "react";

vi.mock("@/components/shared/animated-counter", () => ({
  AnimatedCounter: ({ value }: { value: number }) => <span>{value}</span>,
}));

vi.mock("@/components/shared/stagger-container", () => ({
  StaggerContainer: ({
    children,
    className,
  }: {
    children: React.ReactNode;
    className?: string;
  }) => <div className={className}>{children}</div>,
  StaggerItem: ({
    children,
    className,
  }: {
    children: React.ReactNode;
    className?: string;
  }) => <div className={className}>{children}</div>,
}));

import { MonitorSummaryCards } from "@/components/monitors/summary-cards";
import type { MonitorResponse } from "@/hooks/use-monitors";

function makeMonitor(
  overrides: Partial<MonitorResponse> = {},
): MonitorResponse {
  return {
    id: "monitor-1",
    compound_smiles: "CCO",
    compound_name: "Ethanol",
    source_analysis_id: null,
    source_report_id: "",
    source_trust_mode: "monitor",
    schedule: "weekly",
    is_active: true,
    jurisdiction_bundle: "custom",
    target_jurisdictions: ["US", "EP"],
    strategy_version: "2026-04-monitor-v1",
    monitoring_strategy: {},
    watch_targets: [],
    last_run_at: "2026-06-18T10:00:00.000Z",
    last_full_refresh_at: null,
    last_run_mode: "diff_only",
    last_run_status: "ready",
    last_run_summary: "No monitored changes detected.",
    last_patent_count: 4,
    conclusion_status: "fresh",
    stale_conclusions: [],
    stale_conclusion_count: 0,
    created_at: "2026-04-24T10:00:00.000Z",
    ...overrides,
  };
}

describe("MonitorSummaryCards", () => {
  it("renders a truthful readiness strip without clearance language", () => {
    render(
      <MonitorSummaryCards
        monitors={[
          makeMonitor(),
          makeMonitor({
            id: "monitor-2",
            is_active: false,
            last_run_status: "pending",
            last_run_at: null,
            target_jurisdictions: ["JP"],
            last_patent_count: 2,
          }),
          makeMonitor({
            id: "monitor-3",
            last_run_status: "error",
            last_run_at: "2026-06-15T08:00:00.000Z",
            target_jurisdictions: ["US", "CN"],
            last_patent_count: 3,
          }),
        ]}
      />,
    );

    expect(screen.getByText("No clearance inferred")).toBeInTheDocument();
    expect(screen.getByText("Scope watch")).toBeInTheDocument();
    expect(
      screen.getByText(
        "Monitoring surfaces changes for review; it is not a legal clearance opinion.",
      ),
    ).toBeInTheDocument();
    expect(screen.getByText("Visible fresh watches")).toBeInTheDocument();
    expect(
      screen.getByText("2 active, 1 paused on this page"),
    ).toBeInTheDocument();
    expect(screen.getByText("Visible attention queue")).toBeInTheDocument();
    expect(screen.getByText("Visible scope coverage")).toBeInTheDocument();
    expect(
      screen.getByText(/first runs pending on this page/i),
    ).toBeInTheDocument();
    expect(
      screen.getByText(
        /tracked patents on this page · latest visible ready run/i,
      ),
    ).toBeInTheDocument();
    expect(screen.getByText("Visible patents")).toBeInTheDocument();
    expect(screen.queryByText(/\bcleared\b/i)).not.toBeInTheDocument();
  });
});
