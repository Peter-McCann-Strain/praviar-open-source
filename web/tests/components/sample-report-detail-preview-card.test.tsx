import { fireEvent, render, screen, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

vi.mock("@/components/chemistry/molecule-viewer-2d", () => ({
  MoleculeViewer2D: ({ smiles }: { smiles: string }) => (
    <div data-testid="molecule-viewer">{smiles}</div>
  ),
}));

import { SampleReportDetailPreviewCard } from "@/components/marketing/sample-report-detail-preview-card";
import { getMarketingDemoArtifact } from "@/marketing/live-demo";

describe("SampleReportDetailPreviewCard", () => {
  it("uses an accessible mobile disclosure while leaving desktop detail available", () => {
    render(
      <SampleReportDetailPreviewCard
        demoArtifact={getMarketingDemoArtifact()}
        className="founder-grid-position"
        mobileDisclosure
      />,
    );

    const disclosure = screen.getByTestId("founder-dossier-disclosure");
    const trigger = screen.getByRole("button", {
      name: /Inspect synthetic dossier evidence/i,
    });
    const detail = screen.getByTestId("founder-dossier-content");

    expect(disclosure.parentElement).toHaveClass("founder-grid-position");
    expect(trigger).toHaveClass("lg:hidden");
    expect(trigger).toHaveAttribute("aria-expanded", "false");
    expect(trigger).toHaveAttribute(
      "aria-controls",
      "founder-dossier-mobile-content",
    );
    expect(detail).toHaveClass("hidden", "lg:block");
    expect(screen.getAllByTestId("fto-dossier-preview")).toHaveLength(1);
    const flaggedMetric = screen.getByText(
      "Sample families flagged",
    ).parentElement;
    expect(flaggedMetric).not.toBeNull();
    expect(within(flaggedMetric!).getByText("1")).toBeInTheDocument();
    expect(within(flaggedMetric!).queryByText("0")).not.toBeInTheDocument();

    fireEvent.click(trigger);
    expect(trigger).toHaveAttribute("aria-expanded", "true");
    expect(detail).toHaveClass("block", "lg:block");
  });

  it("keeps the full dossier directly visible when disclosure is not requested", () => {
    render(
      <SampleReportDetailPreviewCard
        demoArtifact={getMarketingDemoArtifact()}
        className="sample-report-layout"
      />,
    );

    expect(
      screen.queryByTestId("founder-dossier-disclosure"),
    ).not.toBeInTheDocument();
    expect(screen.getByTestId("fto-dossier-preview")).toHaveClass(
      "sample-report-layout",
    );
  });

  it("forwards the compact item limit used by the sample index", () => {
    render(
      <SampleReportDetailPreviewCard
        demoArtifact={getMarketingDemoArtifact()}
        compactItemLimit={1}
      />,
    );

    expect(screen.getByText("Driver 1")).toBeInTheDocument();
    expect(screen.queryByText("Driver 2")).not.toBeInTheDocument();
  });
});
