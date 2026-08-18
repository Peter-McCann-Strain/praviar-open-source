import { act, fireEvent, render, screen } from "@testing-library/react";
import type { HTMLAttributes, ReactNode } from "react";
import { describe, expect, it, vi } from "vitest";
import { FunnelExplorer } from "@/components/report/funnel-explorer";
import { emitAuthBoundaryChanged } from "@/lib/auth-events";
import type { PipelineAuditTrail } from "@praviar/shared-types";

vi.mock("motion/react", () => ({
  AnimatePresence: ({ children }: { children: ReactNode }) => <>{children}</>,
  motion: {
    div: ({ children, ...props }: HTMLAttributes<HTMLDivElement>) => (
      <div {...props}>{children}</div>
    ),
  },
}));

const audit = {
  total_patents_discovered: 10,
  patents_after_hard_filter: 6,
  patents_after_ranking: 4,
  patents_after_triage: 2,
  patents_analyzed: 1,
  search_funnel: [
    {
      patent_id: "US-REMOVED",
      passed_hard_filter: false,
      filter_reason: "family excluded",
      included_in_triage: false,
      composite_score: 0.41,
    },
  ],
  triage_audit: [],
  analysis_audit: [],
  timing_data: [],
} as PipelineAuditTrail;

describe("FunnelExplorer", () => {
  it("clears private patent search result and drilldown state on auth boundary changes", () => {
    render(<FunnelExplorer audit={audit} />);

    const input = screen.getByLabelText("Find patent in funnel");
    expect(input).toHaveClass("min-h-11");
    fireEvent.change(input, { target: { value: "US-REMOVED" } });
    fireEvent.keyDown(input, { key: "Enter" });

    expect(input).toHaveValue("US-REMOVED");
    expect(
      screen.getByText(
        "US-REMOVED was removed at hard filter stage. Reason: family excluded",
      ),
    ).toBeInTheDocument();
    expect(screen.getByText(/Hard Filtered.*Details/)).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "Clear patent search" }),
    ).toHaveClass("h-11", "w-11");
    expect(
      screen.getByRole("button", {
        name: "Close Hard Filtered details",
      }),
    ).toHaveClass("h-11", "w-11");
    expect(screen.getByRole("button", { name: /^Hard Filtered/ })).toHaveClass(
      "ring-warning/30",
    );

    act(() => {
      emitAuthBoundaryChanged({ refreshToken: false });
    });

    expect(input).toHaveValue("");
    expect(
      screen.queryByText(
        "US-REMOVED was removed at hard filter stage. Reason: family excluded",
      ),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByText(/Hard Filtered.*Details/),
    ).not.toBeInTheDocument();
  });
});
