import { describe, it, expect, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import React from "react";

import { MonitorsTable } from "@/components/monitors/monitors-table";
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
    target_jurisdictions: ["US", "EP", "UK"],
    strategy_version: "2026-04-monitor-v1",
    monitoring_strategy: {},
    watch_targets: [],
    last_run_at: null,
    last_full_refresh_at: null,
    last_run_mode: "diff_only",
    last_run_status: "pending",
    last_run_summary: "Awaiting first run.",
    last_patent_count: 2,
    conclusion_status: "unbound",
    stale_conclusions: [],
    stale_conclusion_count: 0,
    created_at: "2026-04-24T10:00:00Z",
    ...overrides,
  };
}

describe("MonitorsTable", () => {
  it("renders context-aware empty states", () => {
    render(
      <MonitorsTable
        monitors={[]}
        emptyTitle="No paused monitors"
        emptyDescription="Switch filters to review active monitors."
        onToggleActive={vi.fn()}
        onViewAlerts={vi.fn()}
        onRun={vi.fn()}
        onDelete={vi.fn()}
      />,
    );

    expect(screen.getByText("No paused monitors")).toBeInTheDocument();
    expect(
      screen.getByText("Switch filters to review active monitors."),
    ).toBeInTheDocument();
    expect(screen.queryByText("No monitors yet")).not.toBeInTheDocument();
  });

  it("surfaces conclusion invalidation as the primary posture", () => {
    render(
      <MonitorsTable
        monitors={[
          makeMonitor({
            last_run_at: "2026-07-26T10:00:00Z",
            last_run_status: "review_required",
            conclusion_status: "review_required",
            stale_conclusion_count: 2,
          }),
        ]}
        onToggleActive={vi.fn()}
        onViewAlerts={vi.fn()}
        onRun={vi.fn()}
        onDelete={vi.fn()}
      />,
    );

    expect(screen.getByText("Attorney review required")).toBeInTheDocument();
    expect(
      screen.getByText("2 prior conclusions no longer current"),
    ).toBeInTheDocument();
    expect(screen.queryByText("Healthy")).not.toBeInTheDocument();
  });

  it("routes low-cost diff and bounded full refresh actions separately", () => {
    const onRun = vi.fn();

    render(
      <MonitorsTable
        monitors={[makeMonitor()]}
        onToggleActive={vi.fn()}
        onViewAlerts={vi.fn()}
        onRun={onRun}
        onDelete={vi.fn()}
      />,
    );

    const diffRunButton = screen.getByRole("button", {
      name: "Run low-cost diff monitor for Ethanol",
    });
    const fullRefreshButton = screen.getByRole("button", {
      name: "Force bounded full refresh for Ethanol",
    });
    expect(
      screen.getByRole("region", {
        name: "Monitoring watches horizontal scroll area",
      }),
    ).toHaveClass("md:overflow-x-auto");
    expect(
      screen.getByRole("region", {
        name: "Monitoring watches horizontal scroll area",
      }),
    ).toHaveAttribute("tabindex", "0");

    fireEvent.click(diffRunButton);
    fireEvent.click(fullRefreshButton);

    expect(onRun).toHaveBeenNthCalledWith(
      1,
      expect.objectContaining({ id: "monitor-1" }),
    );
    expect(onRun).toHaveBeenNthCalledWith(
      2,
      expect.objectContaining({ id: "monitor-1" }),
      { forceFullRefresh: true },
    );
  });

  it("uses monitor-specific accessible names for repeated row actions", () => {
    render(
      <MonitorsTable
        monitors={[
          makeMonitor({ id: "monitor-1", compound_name: "Ethanol" }),
          makeMonitor({
            id: "monitor-2",
            compound_name: "Aspirin",
            compound_smiles: "CC(=O)Oc1ccccc1C(=O)O",
          }),
        ]}
        onToggleActive={vi.fn()}
        onViewAlerts={vi.fn()}
        onRun={vi.fn()}
        onDelete={vi.fn()}
      />,
    );

    expect(
      screen.getByRole("button", { name: "View alerts for Ethanol" }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "View alerts for Aspirin" }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "Pause monitor for Ethanol" }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "Delete monitor for Aspirin" }),
    ).toBeInTheDocument();
  });

  it("locks all mutating row actions while a monitor update is pending", () => {
    render(
      <MonitorsTable
        monitors={[
          makeMonitor({ id: "monitor-1", compound_name: "Ethanol" }),
          makeMonitor({
            id: "monitor-2",
            compound_name: "Aspirin",
            compound_smiles: "CC(=O)Oc1ccccc1C(=O)O",
          }),
        ]}
        pendingMonitorId="monitor-1"
        onToggleActive={vi.fn()}
        onViewAlerts={vi.fn()}
        onRun={vi.fn()}
        onDelete={vi.fn()}
      />,
    );

    expect(screen.getByRole("status")).toHaveTextContent(
      "Applying watch update",
    );
    expect(
      screen.getByRole("button", { name: "View alerts for Aspirin" }),
    ).not.toBeDisabled();
    expect(
      screen.getByRole("button", {
        name: "Run low-cost diff monitor for Aspirin",
      }),
    ).toBeDisabled();
    expect(
      screen.getByRole("button", {
        name: "Force bounded full refresh for Aspirin",
      }),
    ).toBeDisabled();
    expect(
      screen.getByRole("button", { name: "Pause monitor for Aspirin" }),
    ).toBeDisabled();
    expect(
      screen.getByRole("button", { name: "Delete monitor for Aspirin" }),
    ).toBeDisabled();
  });

  it("marks selected alert rows as expanded", () => {
    render(
      <MonitorsTable
        monitors={[makeMonitor({ id: "monitor-1", compound_name: "Ethanol" })]}
        selectedMonitorId="monitor-1"
        onToggleActive={vi.fn()}
        onViewAlerts={vi.fn()}
        onRun={vi.fn()}
        onDelete={vi.fn()}
      />,
    );

    expect(
      screen.getByRole("button", { name: "View alerts for Ethanol" }),
    ).toHaveAttribute("aria-expanded", "true");
  });

  it("contains long compound names, SMILES, and jurisdictions", () => {
    const longName = `Highly-substituted-monitor-compound-${"x".repeat(120)}`;
    const longSmiles = `CC(=O)OC1=CC=CC=C1C(=O)O${"C".repeat(120)}`;
    const longJurisdiction = `PCT-NATIONAL-PHASE-${"Y".repeat(80)}`;

    render(
      <MonitorsTable
        monitors={[
          makeMonitor({
            compound_name: longName,
            compound_smiles: longSmiles,
            target_jurisdictions: [longJurisdiction, "US", "EP", "JP"],
          }),
        ]}
        onToggleActive={vi.fn()}
        onViewAlerts={vi.fn()}
        onRun={vi.fn()}
        onDelete={vi.fn()}
      />,
    );

    expect(screen.getByText(longName)).toHaveClass("max-w-full", "break-words");
    expect(screen.getByText(longSmiles)).toHaveAttribute("title", longSmiles);
    expect(screen.getByText(longSmiles)).toHaveClass("max-w-full", "break-all");
    expect(screen.getByText(longJurisdiction)).toHaveClass(
      "max-w-full",
      "break-all",
    );
    expect(screen.getByText("+1")).toBeInTheDocument();

    fireEvent.click(
      screen.getByRole("button", { name: `Delete monitor for ${longName}` }),
    );
    expect(
      screen.getByText((_content, element) =>
        Boolean(
          element?.tagName.toLowerCase() === "p" &&
          element.textContent?.includes(longName) &&
          element.textContent.includes("will stop future monitoring runs"),
        ),
      ),
    ).toHaveClass("break-words");
  });

  it("shows posture, jurisdictions, summary, and destructive confirmation context", () => {
    const onDelete = vi.fn();

    render(
      <MonitorsTable
        monitors={[
          makeMonitor({
            last_run_status: "error",
            last_run_summary: "2 new continuations surfaced.",
            target_jurisdictions: ["US", "EP", "JP", "CN"],
          }),
        ]}
        onToggleActive={vi.fn()}
        onViewAlerts={vi.fn()}
        onRun={vi.fn()}
        onDelete={onDelete}
      />,
    );

    expect(screen.getByText("Needs attention")).toBeInTheDocument();
    expect(
      screen.getByText("2 new continuations surfaced."),
    ).toBeInTheDocument();
    expect(screen.getByText("US")).toBeInTheDocument();
    expect(screen.getByText("+1")).toBeInTheDocument();

    fireEvent.click(
      screen.getByRole("button", { name: "Delete monitor for Ethanol" }),
    );
    expect(
      screen.getByText("Delete monitor and stop scheduled checks?"),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", {
        name: "Confirm delete monitor for Ethanol",
      }),
    ).toHaveClass("min-h-11");
    expect(
      screen.getByRole("button", {
        name: "Cancel delete monitor for Ethanol",
      }),
    ).toHaveClass("min-h-11");
    fireEvent.click(
      screen.getByRole("button", {
        name: "Confirm delete monitor for Ethanol",
      }),
    );
    expect(onDelete).toHaveBeenCalledWith("monitor-1");
  });
});
