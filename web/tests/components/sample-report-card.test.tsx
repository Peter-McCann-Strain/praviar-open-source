import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { SampleReportCard } from "@/components/marketing/sample-report-card";
import { SAMPLE_REPORTS } from "@/marketing/content";

describe("SampleReportCard", () => {
  it("labels fixture-backed samples without live-proof language", () => {
    render(<SampleReportCard report={SAMPLE_REPORTS[0]} featured />);

    expect(screen.getByText("Synthetic sample")).toBeInTheDocument();
    expect(screen.getByText(/this sample is fictional/i)).toBeInTheDocument();
    expect(screen.queryByText(/live proof/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/live report surface/i)).not.toBeInTheDocument();
    expect(screen.getByText("praviar-fictional-showcase@1.0.0")).toHaveClass(
      "font-mono",
      "[overflow-wrap:anywhere]",
    );
    expect(
      screen.getByText("praviar-fictional-showcase@1.0.0"),
    ).not.toHaveClass("break-all");
    const detailsLink = screen.getByRole("link", { name: "View details" });
    expect(detailsLink).toHaveAttribute(
      "href",
      "/sample-reports/example-molecule-alpha",
    );
    expect(detailsLink).toHaveClass("min-h-11", "rounded-lg");
  });
});
