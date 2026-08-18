import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { SampleReportDetailHero } from "@/components/marketing/sample-report-detail-hero";
import { SAMPLE_REPORTS } from "@/marketing/content";

describe("SampleReportDetailHero", () => {
  it("keeps synthetic sample boundaries visible beside public review actions", () => {
    const report = SAMPLE_REPORTS[0];

    render(
      <SampleReportDetailHero
        entry={report}
        familiesFlaggedForReviewCount={1}
        isSyntheticSample
      />,
    );

    expect(
      screen.getByRole("heading", { name: report.compoundName }),
    ).toBeInTheDocument();
    expect(
      screen.queryByTestId("sample-report-detail-brand-lockup"),
    ).not.toBeInTheDocument();
    expect(screen.getByText(report.category)).toHaveClass(
      "uppercase",
      "tracking-[0.18em]",
    );
    expect(report.previewHref).toBeUndefined();
    expect(screen.getAllByText(/this sample is fictional/i)).toHaveLength(2);
    expect(
      screen.getByText("What the fictional scenario flags"),
    ).toBeInTheDocument();
    expect(
      screen.getByText(/Illustrative priority: Qualified review required/i),
    ).toBeInTheDocument();
    expect(
      screen.getByText(/1 sample family flagged for review/i),
    ).toBeInTheDocument();
    expect(
      screen.queryByText(/2 sample families flagged for review/i),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByRole("link", { name: "Open public share view" }),
    ).not.toBeInTheDocument();
    expect(screen.queryByText(/live proof/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/live report surface/i)).not.toBeInTheDocument();
    expect(
      screen.getByText("Synthetic sample · fictional patent data"),
    ).toBeInTheDocument();
    const evidenceLink = screen.getByRole("link", {
      name: "Inspect fictional evidence",
    });
    const methodologyLink = screen.getByRole("link", {
      name: "Review the methodology",
    });

    expect(evidenceLink).toHaveAttribute("href", "#sample-trace-packet");
    expect(evidenceLink).toHaveClass("w-full", "rounded-lg", "sm:w-auto");
    expect(methodologyLink).toHaveAttribute("href", "/methodology");
    expect(methodologyLink).toHaveClass("w-full", "rounded-lg", "sm:w-auto");
    expect(document.querySelector('a[href*="sign-up"]')).toBeNull();
    expect(document.querySelector('a[href*="billing"]')).toBeNull();
    for (const sourceReference of screen.getAllByText(
      "praviar-fictional-showcase@1.0.0",
    )) {
      expect(sourceReference).toHaveClass(
        "font-mono",
        "[overflow-wrap:anywhere]",
      );
    }
    for (const sourceReference of screen.getAllByText(
      "praviar-fictional-showcase@1.0.0",
    )) {
      expect(sourceReference).not.toHaveClass("break-all");
    }
    expect(screen.getAllByText("Sample data source")).toHaveLength(2);
    expect(
      screen.getAllByText(/Illustrative families reviewed/i).length,
    ).toBeGreaterThan(0);
  });
});
