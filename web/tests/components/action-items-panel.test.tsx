import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent, within } from "@testing-library/react";
import { TEST_REPORT } from "../fixtures/report-fixture";
import { ActionItemsPanel } from "@/components/report/action-items-panel";
import type { FTOReport } from "@praviar/shared-types";

const mockReplace = vi.fn();
vi.mock("next/navigation", () => ({
  useRouter: () => ({ replace: mockReplace }),
}));

describe("ActionItemsPanel", () => {
  it("renders null when action_items is empty", () => {
    const report = { ...TEST_REPORT, action_items: [] } as FTOReport;
    const { container } = render(<ActionItemsPanel report={report} />);
    expect(container.innerHTML).toBe("");
  });

  it("renders null when action_items is undefined", () => {
    const { action_items: _, ...rest } = TEST_REPORT;
    const report = rest as unknown as FTOReport;
    const { container } = render(<ActionItemsPanel report={report} />);
    expect(container.innerHTML).toBe("");
  });

  it("renders the counsel next-actions command center", () => {
    render(<ActionItemsPanel report={TEST_REPORT} />);
    expect(screen.getByText("Counsel next actions")).toBeInTheDocument();
    expect(screen.getByText("AI-assisted triage")).toBeInTheDocument();
    expect(
      screen.getByText(/No legal conclusion changed/i),
    ).toBeInTheDocument();
    expect(screen.getAllByText("Next actions").length).toBeGreaterThanOrEqual(
      1,
    );
    expect(screen.getByText("Urgent")).toBeInTheDocument();
    expect(screen.getByText("Evidence")).toBeInTheDocument();
  });

  it("renders all action items from TEST_REPORT", () => {
    render(<ActionItemsPanel report={TEST_REPORT} />);
    const panel = screen.getByTestId("counsel-next-actions");
    const list = within(panel).getByRole("list", {
      name: "Counsel next action queue",
    });
    expect(list).not.toBeNull();
    const items = within(list).getAllByRole("listitem");
    expect(items).toHaveLength(5);
    expect(list).toContainElement(items[0]);
  });

  it("shows priority badges", () => {
    render(<ActionItemsPanel report={TEST_REPORT} />);
    const criticalBadges = screen.getAllByText("Critical");
    expect(criticalBadges.length).toBeGreaterThanOrEqual(1);
  });

  it("shows patent ID pills", () => {
    render(<ActionItemsPanel report={TEST_REPORT} />);
    expect(screen.getAllByText("US0000000001A1").length).toBeGreaterThanOrEqual(
      1,
    );
  });

  it("clicking patent pill navigates to patents tab", () => {
    render(<ActionItemsPanel report={TEST_REPORT} />);
    const pills = screen.getAllByRole("button", {
      name: "Open patent US0000000001A1 in the patents tab",
    });
    expect(pills[0]).toHaveClass("min-h-11", "px-3", "py-1.5");
    fireEvent.click(pills[0]);
    expect(mockReplace).toHaveBeenCalledWith(
      "?tab=patents&patent=US0000000001A1",
    );
  });

  it("opens the primary action brief for the first affected patent", () => {
    render(<ActionItemsPanel report={TEST_REPORT} />);
    const buttons = screen.getAllByRole("button", {
      name: "Open Design brief for US0000000001A1",
    });

    expect(buttons[0]).toHaveClass("min-h-11", "justify-between");
    fireEvent.click(buttons[0]);
    expect(mockReplace).toHaveBeenCalledWith(
      "?tab=patents&patent=US0000000001A1",
    );
  });

  it("keeps long generated action prose and primary buttons wrapped", () => {
    const longDescription =
      "Evaluate launch-readiness for BLOCKING_MARKUSH_SUBSTITUTION_PATTERN_WITH_UNBROKEN_CHEMICAL_TOKEN_AND_EXTERNAL_COUNSEL_WORKFLOW_REFERENCE";
    const longReasoning =
      "Reasoning cites SMILES_like_C1CCCCC1NCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCC and a provider-reference-token-without-natural-breaks.";
    const longTimeline =
      "Outside-counsel review window depends on continuation-monitoring-and-design-around-briefing-without-natural-breakpoints.";
    const report = {
      ...TEST_REPORT,
      action_items: [
        {
          ...TEST_REPORT.action_items![2],
          description: longDescription,
          reasoning: longReasoning,
          estimated_timeline: longTimeline,
          patent_ids: ["US0000000001A1"],
        },
      ],
    } as FTOReport;

    render(<ActionItemsPanel report={report} />);

    expect(screen.getByText("Challenge (IPR)")).toHaveClass(
      "[overflow-wrap:anywhere]",
    );
    expect(screen.getByText(longDescription)).toHaveClass(
      "[overflow-wrap:anywhere]",
    );
    expect(screen.getByText(longTimeline)).toHaveClass(
      "[overflow-wrap:anywhere]",
    );

    const primaryAction = screen.getByRole("button", {
      name: "Open Challenge brief for US0000000001A1",
    });
    expect(primaryAction).toHaveClass(
      "min-w-0",
      "whitespace-normal",
      "leading-5",
    );
    expect(within(primaryAction).getByText("Open Challenge brief")).toHaveClass(
      "[overflow-wrap:anywhere]",
    );

    fireEvent.click(screen.getByRole("button", { name: "Reasoning" }));
    expect(screen.getByText(longReasoning)).toHaveClass(
      "praviar-code-surface",
      "[overflow-wrap:anywhere]",
    );
  });

  it("reasoning is collapsed by default", () => {
    render(<ActionItemsPanel report={TEST_REPORT} />);
    const buttons = screen.getAllByRole("button", { name: "Reasoning" });
    expect(buttons.length).toBeGreaterThanOrEqual(1);
    expect(buttons[0]).toHaveClass("min-h-11", "rounded-md");
    expect(buttons[0]).toHaveAttribute("aria-expanded", "false");
    expect(screen.queryByText(/eukaryotic host organism/)).toBeNull();
  });

  it("clicking reasoning expands it", () => {
    render(<ActionItemsPanel report={TEST_REPORT} />);
    const buttons = screen.getAllByRole("button", { name: "Reasoning" });
    fireEvent.click(buttons[0]);
    expect(buttons[0]).toHaveAttribute("aria-expanded", "true");
    expect(screen.getByText(/eukaryotic host organism/)).toBeInTheDocument();
  });
});
