import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { LiveResultsFeed } from "@/components/pipeline/live-results-feed";

describe("LiveResultsFeed", () => {
  it("keeps long live-result labels readable and the collapse toggle touch-sized", () => {
    render(
      <LiveResultsFeed
        maxVisible={1}
        title="Live Results"
        results={[
          {
            id: "result-1",
            label:
              "US20260345678A1-very-long-current-patent-result-without-natural-breakpoints",
            detail:
              "ClaimScopeDetailWithNoNaturalBreakpointsAndLongPipelineState",
          },
          {
            id: "result-2",
            label: "WO2026123456A1",
          },
        ]}
      />,
    );

    expect(
      screen.getByText(
        "US20260345678A1-very-long-current-patent-result-without-natural-breakpoints",
      ),
    ).toHaveClass("break-words", "[overflow-wrap:anywhere]");
    expect(
      screen.getByText(
        "ClaimScopeDetailWithNoNaturalBreakpointsAndLongPipelineState",
      ),
    ).toHaveClass("break-words", "[overflow-wrap:anywhere]");

    const toggle = screen.getByRole("button", { name: "See 1 more" });
    expect(toggle).toHaveClass("min-h-11", "min-w-11");

    fireEvent.click(toggle);
    expect(screen.getByRole("button", { name: "Show less" })).toHaveClass(
      "min-h-11",
      "min-w-11",
    );
  });
});
