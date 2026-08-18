import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

vi.mock("@/components/marketing/page-event-beacon", () => ({
  PageEventBeacon: () => null,
}));

vi.mock("@/components/marketing/sample-report-mobile-command-bar", () => ({
  SampleReportMobileCommandBar: () => null,
}));

vi.mock("@/components/marketing/sample-report-detail-hero", () => ({
  SampleReportDetailHero: () => <div>Fictional sample hero</div>,
}));

vi.mock("@/components/marketing/sample-report-detail-preview-card", () => ({
  SampleReportDetailPreviewCard: () => <div>Fictional sample preview</div>,
}));

vi.mock("@/components/marketing/sample-report-detail-live-sections", () => ({
  SampleReportDetailLiveSections: () => (
    <div id="sample-trace-packet">Fictional run record</div>
  ),
}));

import SampleReportDetailPage from "@/app/(marketing)/sample-reports/[slug]/page";

describe("sample report detail public actions", () => {
  it("keeps every action on an informational surface", async () => {
    const page = await SampleReportDetailPage({
      params: Promise.resolve({ slug: "example-molecule-alpha" }),
    });
    const { container } = render(page);

    expect(
      screen.getByText(/working open-source research system/i),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("link", { name: "Inspect the fictional run record" }),
    ).toHaveAttribute("href", "#sample-trace-packet");
    expect(
      screen.getByRole("link", { name: "Review the methodology" }),
    ).toHaveAttribute("href", "/methodology");
    expect(
      screen.getByRole("link", { name: "Review current assurance status" }),
    ).toHaveAttribute("href", "/trust#assurance-heading");

    for (const link of Array.from(container.querySelectorAll("a"))) {
      expect(link.getAttribute("href") ?? "").not.toMatch(
        /(?:sign-up|billing|checkout|pricing)/i,
      );
    }
  });
});
