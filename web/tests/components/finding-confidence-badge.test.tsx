import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";

import { FindingConfidenceBadge } from "@/components/report/finding-confidence-badge";

describe("FindingConfidenceBadge", () => {
  it.each([
    { level: "HIGH", label: "High confidence" },
    { level: "MODERATE", label: "Moderate confidence" },
    { level: "LOW", label: "Low confidence" },
  ] as const)(
    "renders level $level with the right aria label",
    ({ level, label }) => {
      render(<FindingConfidenceBadge level={level} />);
      const badge = screen.getByTestId("finding-confidence-badge");
      expect(badge).toHaveAttribute("data-level", level);
      expect(badge).toHaveAttribute(
        "aria-label",
        expect.stringContaining(label),
      );
    },
  );

  it("falls back to UNKNOWN for null/undefined/unexpected values", () => {
    const { rerender } = render(<FindingConfidenceBadge level={null} />);
    expect(screen.getByTestId("finding-confidence-badge")).toHaveAttribute(
      "data-level",
      "UNKNOWN",
    );
    rerender(<FindingConfidenceBadge level="garbage" />);
    expect(screen.getByTestId("finding-confidence-badge")).toHaveAttribute(
      "data-level",
      "UNKNOWN",
    );
  });

  it("maps MEDIUM/MED synonyms onto MODERATE", () => {
    render(<FindingConfidenceBadge level="MEDIUM" />);
    expect(screen.getByTestId("finding-confidence-badge")).toHaveAttribute(
      "data-level",
      "MODERATE",
    );
  });

  it("renders the optional detail string", () => {
    render(<FindingConfidenceBadge level="HIGH" detail="3 of 3 prongs" />);
    expect(screen.getByTestId("finding-confidence-detail")).toHaveTextContent(
      "3 of 3 prongs",
    );
  });

  it("wraps the badge in a focusable trigger when rationale is provided", () => {
    render(
      <FindingConfidenceBadge
        level="HIGH"
        rationale="FWR test passed all 3 prongs"
      />,
    );
    // Radix tooltip renders on hover/focus, which is hard to exercise without
    // user-event. Confirm the structural change: the badge is wrapped in a
    // focusable button so keyboard users can reach the tooltip trigger.
    const trigger = screen
      .getByTestId("finding-confidence-badge")
      .closest("button");
    expect(trigger).not.toBeNull();
    expect(trigger).toHaveAttribute("type", "button");
    expect(trigger).toHaveClass("min-h-11");
  });

  it("renders without a button wrapper when no rationale is provided", () => {
    render(<FindingConfidenceBadge level="HIGH" />);
    const badge = screen.getByTestId("finding-confidence-badge");
    expect(badge.closest("button")).toBeNull();
  });
});
