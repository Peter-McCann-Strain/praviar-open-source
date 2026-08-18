import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import type { FTOReport } from "@praviar/shared-types";

import { RegulatoryTab } from "@/components/report/regulatory-tab";
import { TEST_REPORT } from "../fixtures/report-fixture";

function reportWithRegulatoryData(
  regulatory_exclusivity: FTOReport["regulatory_exclusivity"],
): FTOReport {
  return {
    ...TEST_REPORT,
    regulatory_exclusivity,
  };
}

describe("RegulatoryTab", () => {
  it("shows an empty state when no regulatory data is attached", () => {
    render(<RegulatoryTab report={reportWithRegulatoryData(null)} />);

    expect(
      screen.getByText("Exclusivity posture has not been enriched"),
    ).toBeInTheDocument();
  });

  it("renders Purple Book, PTE, Paragraph IV, and queried-source evidence", () => {
    render(
      <RegulatoryTab
        report={reportWithRegulatoryData({
          purple_book_entry: {
            bla_number: "761042",
            proprietary_name: "Examplemab",
            proper_name: "examplemab",
            applicant: "Praviar Biologics",
            bla_type: "351(a)",
            approval_date: "2024-02-14",
            marketing_status: "Rx",
            exclusivity_expiration: "2036-02-14",
          },
          bpcia_exclusivity_expiry: "2036-02-14",
          pte_extensions: [
            {
              patent_number: "US9988776",
              product_name: "Examplemab",
              extension_days: "411",
              status: "Granted",
            },
          ],
          paragraph_iv_challenges: [
            {
              drug_name: "Exampletab",
              nda_number: "209999",
              dosage_form: "Tablet",
              strength: "10 mg",
              submission_count: 3,
              first_filing_date: "2025-03-01",
              patent_expiry_date: "2031-09-30",
              has_180_day_exclusivity: true,
            },
          ],
          data_sources_queried: [
            "FDA Purple Book",
            "USPTO Patent Term Extension certificates",
            "FDA Paragraph IV certifications",
          ],
        })}
      />,
    );

    expect(screen.getByText("FDA Purple Book (Biologics)")).toBeInTheDocument();
    expect(screen.getByTestId("purple-book-grid")).toHaveClass(
      "grid-cols-1",
      "sm:grid-cols-[minmax(8rem,0.42fr)_minmax(0,1fr)]",
    );
    expect(screen.getAllByText("Examplemab")).toHaveLength(2);
    expect(
      screen.getByText("BPCIA 12-year exclusivity expiry:"),
    ).toBeInTheDocument();
    expect(screen.getByText("Patent Term Extensions (1)")).toBeInTheDocument();
    expect(screen.getByText("US9988776")).toBeInTheDocument();
    expect(screen.getByText("411 days")).toBeInTheDocument();
    expect(screen.getByText("Paragraph IV Challenges (1)")).toBeInTheDocument();
    expect(screen.getByText("Exampletab")).toBeInTheDocument();
    expect(screen.getByTestId("pte-entry")).toHaveClass(
      "border-b",
      "last:border-b-0",
    );
    expect(screen.getByTestId("paragraph-iv-entry")).toHaveClass(
      "border-b",
      "last:border-b-0",
    );
    expect(screen.getByText("180-day exclusivity")).toBeInTheDocument();
    expect(screen.getByText("Yes")).toBeInTheDocument();
    expect(screen.getByText("Data Sources Queried")).toBeInTheDocument();
    expect(
      screen.getByText("FDA Paragraph IV certifications"),
    ).toBeInTheDocument();
  });

  it("renders explicit false Paragraph IV exclusivity values", () => {
    render(
      <RegulatoryTab
        report={reportWithRegulatoryData({
          purple_book_entry: null,
          bpcia_exclusivity_expiry: null,
          pte_extensions: [],
          paragraph_iv_challenges: [
            {
              drug_name: "Exampletab",
              has_180_day_exclusivity: false,
            },
          ],
          data_sources_queried: ["FDA Paragraph IV certifications"],
        })}
      />,
    );

    expect(screen.getByText("180-day exclusivity")).toBeInTheDocument();
    expect(screen.getByText("No")).toBeInTheDocument();
  });

  it("shows regulatory source failures instead of presenting a clean no-hit result", () => {
    render(
      <RegulatoryTab
        report={reportWithRegulatoryData({
          purple_book_entry: null,
          bpcia_exclusivity_expiry: null,
          pte_extensions: [],
          paragraph_iv_challenges: [],
          data_sources_queried: ["FDA Purple Book", "USPTO PTE"],
          source_statuses: [
            {
              source: "FDA Purple Book",
              status: "failed",
              error_message: "Source timeout",
            },
            {
              source: "USPTO PTE",
              status: "not_configured",
            },
          ],
        })}
      />,
    );

    expect(screen.getByText("Regulatory Source Health")).toBeInTheDocument();
    expect(screen.getByText("Failed")).toBeInTheDocument();
    expect(screen.getByText("Not configured")).toBeInTheDocument();
    expect(screen.getByText("Source timeout")).toBeInTheDocument();
    expect(
      screen.getByText(
        /Review source status before treating this as a clean no-hit result/,
      ),
    ).toBeInTheDocument();
    expect(
      screen.queryByText(
        /Regulatory sources were queried but returned no matching entries/,
      ),
    ).not.toBeInTheDocument();
  });

  it("redacts raw regulatory source diagnostics", () => {
    render(
      <RegulatoryTab
        report={reportWithRegulatoryData({
          purple_book_entry: null,
          bpcia_exclusivity_expiry: null,
          pte_extensions: [],
          paragraph_iv_challenges: [],
          data_sources_queried: ["FDA Purple Book"],
          source_statuses: [
            {
              source: "FDA Purple Book",
              status: "failed",
              error_message:
                "Bearer abc123 postgres://secret SELECT * FROM regulatory Traceback boom",
            },
          ],
        })}
      />,
    );

    expect(
      screen.getByText(/\[redacted connection string\]/),
    ).toBeInTheDocument();
    expect(screen.queryByText(/Bearer abc123/)).not.toBeInTheDocument();
    expect(screen.queryByText(/postgres:\/\/secret/)).not.toBeInTheDocument();
    expect(screen.queryByText(/SELECT \*/)).not.toBeInTheDocument();
  });

  it("distinguishes queried regulatory sources from missing regulatory data", () => {
    render(
      <RegulatoryTab
        report={reportWithRegulatoryData({
          purple_book_entry: null,
          bpcia_exclusivity_expiry: null,
          pte_extensions: [],
          paragraph_iv_challenges: [],
          data_sources_queried: ["FDA Orange Book"],
        })}
      />,
    );

    expect(screen.getByText("Data Sources Queried")).toBeInTheDocument();
    expect(screen.getByText("FDA Orange Book")).toBeInTheDocument();
    expect(
      screen.getByText(
        /Regulatory sources were queried but returned no matching entries/,
      ),
    ).toBeInTheDocument();
  });
});
