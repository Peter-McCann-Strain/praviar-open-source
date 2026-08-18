import { describe, it, expect } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { TEST_REPORT } from "../fixtures/report-fixture";
import { ReportCoverageBanner } from "@/components/report/coverage-banner";
import type { FTOReport, SourceHealth } from "@praviar/shared-types";

function withSourceHealth(source_health: SourceHealth): FTOReport {
  return { ...TEST_REPORT, source_health } as FTOReport;
}

const ALL_OK: SourceHealth = {
  entries: [
    {
      source: "pubchem_sdq",
      status: "ok",
      patent_count: 100,
      error_message: "",
    },
    { source: "surechembl", status: "ok", patent_count: 50, error_message: "" },
    { source: "bigquery", status: "ok", patent_count: 20, error_message: "" },
  ],
};

const SOME_SKIPPED: SourceHealth = {
  entries: [
    {
      source: "pubchem_sdq",
      status: "ok",
      patent_count: 100,
      error_message: "",
    },
    { source: "surechembl", status: "ok", patent_count: 50, error_message: "" },
    { source: "kipris", status: "skipped", patent_count: 0, error_message: "" },
  ],
};

const SOME_FAILED: SourceHealth = {
  entries: [
    {
      source: "pubchem_sdq",
      status: "ok",
      patent_count: 100,
      error_message: "",
    },
    { source: "surechembl", status: "ok", patent_count: 50, error_message: "" },
    {
      source: "lens",
      status: "failed",
      patent_count: 0,
      error_message: "HTTP 500 internal error from Lens API",
    },
    {
      source: "patentscope",
      status: "failed",
      patent_count: 0,
      error_message: "HTTP 504 timeout",
    },
  ],
};

const SOME_NOT_CONFIGURED: SourceHealth = {
  entries: [
    {
      source: "pubchem_sdq",
      status: "ok",
      patent_count: 100,
      error_message: "",
    },
    { source: "surechembl", status: "ok", patent_count: 50, error_message: "" },
    {
      source: "patcid",
      status: "not_configured",
      patent_count: 0,
      error_message: "",
    },
  ],
};

describe("ReportCoverageBanner", () => {
  it("renders a green all-OK pill when every source succeeded", () => {
    const report = withSourceHealth(ALL_OK);
    render(<ReportCoverageBanner report={report} />);
    expect(screen.getByTestId("coverage-banner-ok")).toBeInTheDocument();
    expect(screen.getByText(/All 3 sources OK/i)).toBeInTheDocument();
  });

  it("renders an amber pill when some sources were skipped but none failed", () => {
    const report = withSourceHealth(SOME_SKIPPED);
    render(<ReportCoverageBanner report={report} />);
    expect(
      screen.getByTestId("coverage-banner-incomplete"),
    ).toBeInTheDocument();
    expect(screen.getByText(/2 of 3 sources queried/i)).toBeInTheDocument();
    expect(screen.getByText(/1 skipped/i)).toBeInTheDocument();
  });

  it("renders an amber pill when a source is not configured", () => {
    const report = withSourceHealth(SOME_NOT_CONFIGURED);
    render(<ReportCoverageBanner report={report} />);
    expect(
      screen.getByTestId("coverage-banner-incomplete"),
    ).toBeInTheDocument();
    expect(screen.getByText(/2 of 3 sources queried/i)).toBeInTheDocument();
    expect(screen.getByText(/1 not configured/i)).toBeInTheDocument();
  });

  it("renders a red expandable banner when any source failed", () => {
    const report = withSourceHealth(SOME_FAILED);
    render(<ReportCoverageBanner report={report} />);

    const banner = screen.getByTestId("coverage-banner-failed");
    expect(banner).toBeInTheDocument();
    expect(banner).toHaveAttribute("role", "alert");
    expect(screen.getByText(/2 of 4 sources failed/i)).toBeInTheDocument();
    expect(screen.getByText(/results may be incomplete/i)).toBeInTheDocument();

    // Details collapsed by default — error messages hidden.
    expect(screen.queryByText(/HTTP 504 timeout/)).not.toBeInTheDocument();

    // Expand.
    fireEvent.click(screen.getByRole("button", { expanded: false }));
    expect(screen.getByText(/HTTP 504 timeout/)).toBeInTheDocument();
    expect(screen.getByText(/HTTP 500 internal error/)).toBeInTheDocument();
  });

  it("redacts backend diagnostics in expanded failure details", () => {
    const report = withSourceHealth({
      entries: [
        {
          source: "lens",
          status: "failed",
          patent_count: 0,
          error_message:
            "postgres://secret sk_live_abc sk-proj-abcdefghijklmnop eyJabc.def.ghi password=hunter2 UPDATE users SET role='admin'; at runWorker (/Users/example-user/app.ts:1:2) SELECT * FROM analyses Traceback boom",
        },
      ],
    });
    render(<ReportCoverageBanner report={report} />);

    fireEvent.click(screen.getByRole("button", { expanded: false }));

    expect(
      screen.getByText(/\[redacted connection string\]/),
    ).toBeInTheDocument();
    expect(screen.queryByText(/postgres:\/\/secret/)).not.toBeInTheDocument();
    expect(screen.queryByText(/sk_live_abc/)).not.toBeInTheDocument();
    expect(screen.queryByText(/sk-proj-/)).not.toBeInTheDocument();
    expect(screen.queryByText(/eyJabc/)).not.toBeInTheDocument();
    expect(screen.queryByText(/hunter2/)).not.toBeInTheDocument();
    expect(screen.queryByText(/UPDATE users/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/runWorker/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/SELECT \*/)).not.toBeInTheDocument();
    expect(screen.getAllByText(/\[redacted API key\]/).length).toBeGreaterThan(
      0,
    );
    expect(screen.getByText(/\[redacted token\]/)).toBeInTheDocument();
    expect(screen.getByText(/password=\[redacted\]/i)).toBeInTheDocument();
    expect(screen.getByText(/\[redacted query\]/)).toBeInTheDocument();
    expect(screen.getByText(/\[redacted stack frame\]/)).toBeInTheDocument();
  });

  it("renders nothing when source_health has no entries", () => {
    const report = withSourceHealth({ entries: [] });
    const { container } = render(<ReportCoverageBanner report={report} />);
    expect(container).toBeEmptyDOMElement();
  });
});
