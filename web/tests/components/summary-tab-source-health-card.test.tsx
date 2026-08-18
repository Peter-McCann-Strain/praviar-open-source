import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { TEST_REPORT } from "../fixtures/report-fixture";
import { SourceHealthCard } from "@/components/report/summary-tab-source-health-card";
import type { FTOReport } from "@praviar/shared-types";

describe("SourceHealthCard", () => {
  it("renders deterministic jurisdiction pills instead of platform emoji flags", () => {
    const { container } = render(<SourceHealthCard report={TEST_REPORT} />);

    expect(
      screen.getByText("Direct Jurisdiction Searches"),
    ).toBeInTheDocument();
    expect(screen.getByText("US")).toBeInTheDocument();
    expect(screen.getByText("EP")).toBeInTheDocument();
    expect(screen.getAllByText("Configured dataset").length).toBeGreaterThan(0);
    expect(screen.getByText("US not directly searched")).toBeInTheDocument();
    expect(screen.queryByText("US searched")).not.toBeInTheDocument();
    expect(container.textContent).not.toMatch(
      /[\u{1F1E6}-\u{1F1FF}\u{1F30D}]/u,
    );
  });

  it("does not treat configured patent datasets as direct jurisdiction searches", () => {
    const report = {
      ...TEST_REPORT,
      source_health: {
        entries: [
          {
            source: "bigquery",
            status: "ok",
            patent_count: 10,
            error_message: "",
          },
          {
            source: "patentscope",
            status: "ok",
            patent_count: 12,
            error_message: "",
          },
        ],
      },
    } as FTOReport;

    render(<SourceHealthCard report={report} />);

    expect(screen.getByText("US not directly searched")).toBeInTheDocument();
    expect(screen.getByText("EP not directly searched")).toBeInTheDocument();
    expect(screen.queryByText("US searched")).not.toBeInTheDocument();
    expect(screen.queryByText("EP searched")).not.toBeInTheDocument();
  });

  it("marks exact jurisdiction sources as direct searches", () => {
    const report = {
      ...TEST_REPORT,
      source_health: {
        entries: [
          {
            source: "epo_search",
            status: "success",
            patent_count: 25,
            error_message: "",
          },
          {
            source: "kipris",
            status: "available",
            patent_count: 8,
            error_message: "",
          },
        ],
      },
    } as FTOReport;

    render(<SourceHealthCard report={report} />);

    expect(screen.getByText("US searched")).toBeInTheDocument();
    expect(screen.getByText("EP searched")).toBeInTheDocument();
    expect(screen.getByText("KR searched")).toBeInTheDocument();
  });

  it("warns when sources are listed but source health is not reported", () => {
    const report = {
      ...TEST_REPORT,
      search_sources_used: ["epo_search", "kipris"],
      source_health: { entries: [] },
    } as FTOReport;

    render(<SourceHealthCard report={report} />);

    expect(screen.getByRole("status")).toHaveTextContent(
      "Source health not reported; verify coverage before relying on it.",
    );
    expect(screen.getByText("US not directly searched")).toBeInTheDocument();
  });

  it("uses shared chart swatches for source status markers", () => {
    const { container } = render(<SourceHealthCard report={TEST_REPORT} />);
    expect(
      screen.getByRole("region", {
        name: "Source health table horizontal scroll area",
      }),
    ).toHaveAttribute("tabindex", "0");
    const swatches = Array.from(
      container.querySelectorAll(".praviar-chart-swatch"),
    );

    expect(swatches.length).toBeGreaterThan(0);
    expect(
      swatches.some((swatch) =>
        swatch
          .getAttribute("style")
          ?.includes("--chart-swatch-color: var(--color-success)"),
      ),
    ).toBe(true);
    expect(
      swatches.some((swatch) =>
        swatch
          .getAttribute("style")
          ?.includes("--chart-swatch-color: var(--color-error)"),
      ),
    ).toBe(true);
    expect(container.querySelector(".bg-error")).toBeNull();
  });

  it("keeps rail source coverage compact without flag glyphs", () => {
    const { container } = render(
      <SourceHealthCard report={TEST_REPORT} variant="rail" />,
    );

    expect(screen.getByText("PubChem")).toBeInTheDocument();
    expect(screen.getByText("847")).toBeInTheDocument();
    expect(container.querySelector(".praviar-chart-swatch")).toBeTruthy();
    expect(container.textContent).not.toMatch(
      /[\u{1F1E6}-\u{1F1FF}\u{1F30D}]/u,
    );
  });
});
