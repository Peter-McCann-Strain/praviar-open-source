import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import {
  ReviewStatusBadge,
  ReviewTierBanner,
} from "@/components/report/review-status-badge";

describe("ReviewStatusBadge", () => {
  it("renders AI Draft badge", () => {
    render(<ReviewStatusBadge status="ai_draft" />);
    expect(screen.getByText("AI Draft")).toBeInTheDocument();
  });

  it("renders Reviewed badge", () => {
    render(<ReviewStatusBadge status="reviewed" />);
    expect(screen.getByText("Reviewed")).toBeInTheDocument();
  });

  it("renders Approved badge", () => {
    render(<ReviewStatusBadge status="approved" />);
    expect(screen.getByText("Approved")).toBeInTheDocument();
  });

  it("renders exact persisted reviewer decision badges", () => {
    const { rerender } = render(<ReviewStatusBadge status="accepted" />);
    expect(screen.getByText("Accepted")).toBeInTheDocument();

    rerender(<ReviewStatusBadge status="edited" />);
    expect(screen.getByText("Edited")).toBeInTheDocument();

    rerender(<ReviewStatusBadge status="rejected" />);
    expect(screen.getByText("Rejected")).toBeInTheDocument();
  });

  it("renders compact mode (icon only)", () => {
    const { container } = render(
      <ReviewStatusBadge status="approved" compact />,
    );
    expect(container.textContent).not.toContain("Approved");
    // Still renders the SVG icon
    expect(container.querySelector("svg")).toBeTruthy();
  });

  it("describes the policy review tier without confidence automation", () => {
    render(<ReviewStatusBadge status="ai_draft" tier="suggest_review" />);

    expect(
      screen.getByTitle("AI Draft — Review Suggested"),
    ).toBeInTheDocument();
  });
});

describe("ReviewTierBanner", () => {
  it("renders suggest banner", () => {
    render(<ReviewTierBanner tier="suggest_review" />);
    expect(screen.getByText("Review suggested")).toBeInTheDocument();
  });

  it("renders mandate banner", () => {
    render(<ReviewTierBanner tier="mandate_review" />);
    expect(screen.getByText("Expert review required")).toBeInTheDocument();
  });
});
