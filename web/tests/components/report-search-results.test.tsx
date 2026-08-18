import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { ReportSearchResults } from "@/components/report/report-search-results";

describe("ReportSearchResults", () => {
  it("renders reviewed evidence matches with patent actions", () => {
    const onOpenPatent = vi.fn();
    const onAskAboutPatent = vi.fn();

    render(
      <ReportSearchResults
        interpretedQuery='Interpreted as "claim 1 fermentation route"'
        results={[
          {
            patent_id: "US123",
            section: "claim_elements",
            relevance: 0.91,
            snippet:
              "Claim 1 overlaps the fermentation route in reviewed evidence.",
          },
        ]}
        onOpenPatent={onOpenPatent}
        onAskAboutPatent={onAskAboutPatent}
      />,
    );

    expect(
      screen.getByRole("region", { name: "Report search results" }),
    ).toBeInTheDocument();
    expect(screen.getByText("US123")).toHaveClass(
      "break-all",
      "[overflow-wrap:anywhere]",
    );
    expect(screen.getByText("claim elements")).toBeInTheDocument();
    expect(screen.getByText("91% relevant")).toBeInTheDocument();
    expect(screen.getByText("1 result")).toBeInTheDocument();
    expect(screen.getByRole("note")).toHaveTextContent(
      "Showing reviewed evidence only. Your report view remains unchanged.",
    );
    expect(
      screen.getByText(
        "Claim 1 overlaps the fermentation route in reviewed evidence.",
      ),
    ).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Open patent US123" }));
    fireEvent.click(
      screen.getByRole("button", { name: "Ask about patent US123" }),
    );

    expect(onOpenPatent).toHaveBeenCalledWith("US123");
    expect(onAskAboutPatent).toHaveBeenCalledWith("US123");
  });

  it("labels retained results as previous when the latest search fails", () => {
    render(
      <ReportSearchResults
        interpretedQuery='Interpreted as "aspirin"'
        resultQuery="aspirin"
        failedQuery="celecoxib"
        isShowingPreviousResults
        results={[
          {
            patent_id: "US123",
            section: "claim_elements",
            relevance: 0.91,
            snippet: "Prior reviewed evidence match.",
          },
        ]}
      />,
    );

    expect(
      screen.getByText("Previous reviewed evidence matches"),
    ).toBeInTheDocument();
    const status = screen.getByRole("status");
    expect(status).toHaveTextContent('Showing previous results for "aspirin".');
    expect(status).toHaveTextContent(
      'The search for "celecoxib" did not complete',
    );
    expect(status).toHaveTextContent(
      "should not be treated as the latest query result",
    );
    expect(screen.queryByRole("note")).not.toBeInTheDocument();
  });

  it("renders nothing before a search context exists", () => {
    const { container } = render(<ReportSearchResults results={[]} />);
    expect(container).toBeEmptyDOMElement();
  });

  it("renders a recoverable no-match state after report search", () => {
    const { container } = render(
      <ReportSearchResults
        interpretedQuery='Interpreted as "kinase formulation"'
        results={[]}
      />,
    );

    expect(
      screen.getByRole("region", { name: "Report search results" }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("heading", { name: "No reviewed evidence matches" }),
    ).toBeInTheDocument();
    expect(
      container.querySelector('svg[data-praviar-mark="praviar-evidence-mark"]'),
    ).toBeInTheDocument();
    expect(screen.getByText("Report view unchanged")).toBeInTheDocument();
    expect(
      screen.getByText(
        /Search interpreted as: Interpreted as "kinase formulation"/,
      ),
    ).toHaveClass("break-words", "[overflow-wrap:anywhere]");
  });

  it("does not render patent-specific actions for section-level matches", () => {
    const onOpenPatent = vi.fn();
    const onAskAboutPatent = vi.fn();

    render(
      <ReportSearchResults
        results={[
          {
            patent_id: "",
            section: "executive_summary",
            relevance: 0.82,
            snippet: "The summary mentions a material risk pattern.",
          },
        ]}
        onOpenPatent={onOpenPatent}
        onAskAboutPatent={onAskAboutPatent}
      />,
    );

    expect(screen.getByText("Report section")).toBeInTheDocument();
    expect(screen.getByText("executive summary")).toBeInTheDocument();
    expect(
      screen.getByText(/Section-level match from executive summary/i),
    ).toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: /Open patent/i }),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: /Ask about patent/i }),
    ).not.toBeInTheDocument();
    expect(onOpenPatent).not.toHaveBeenCalled();
    expect(onAskAboutPatent).not.toHaveBeenCalled();
  });

  it("contains long interpreted queries, patent ids, and snippets", () => {
    const longPatentId = `US${"1234567890".repeat(18)}B2`;
    const longQuery = `Interpreted as claim 1 plus InChI=1S/${"C".repeat(160)}`;
    const longSnippet = `Claim coverage note ${"continuation".repeat(80)}`;

    render(
      <ReportSearchResults
        interpretedQuery={longQuery}
        results={[
          {
            patent_id: longPatentId,
            section: "claim_elements",
            relevance: 0.91,
            snippet: longSnippet,
          },
        ]}
      />,
    );

    expect(screen.getByText(longQuery)).toHaveClass(
      "break-words",
      "[overflow-wrap:anywhere]",
    );
    expect(screen.getByText(longPatentId)).toHaveClass(
      "max-w-full",
      "min-w-0",
      "break-all",
      "[overflow-wrap:anywhere]",
    );
    expect(screen.getByText(longPatentId)).toHaveAttribute(
      "title",
      longPatentId,
    );
    expect(screen.getByText(longSnippet)).toHaveClass(
      "break-words",
      "[overflow-wrap:anywhere]",
    );
    expect(
      screen.getByRole("button", { name: `Open patent ${longPatentId}` }),
    ).toHaveTextContent(`Open ${longPatentId}`);
    expect(
      screen.getByRole("button", { name: `Ask about patent ${longPatentId}` }),
    ).toHaveTextContent(`Ask about ${longPatentId}`);
    expect(screen.getByText(`Open ${longPatentId}`)).toHaveClass(
      "break-all",
      "[overflow-wrap:anywhere]",
    );
    expect(screen.getByText(`Ask about ${longPatentId}`)).toHaveClass(
      "break-all",
      "[overflow-wrap:anywhere]",
    );
  });

  it("lets users reveal loaded matches beyond the initial result set", () => {
    const results = Array.from({ length: 8 }, (_, index) => ({
      patent_id: `US${index + 1}`,
      section: "claim_elements",
      relevance: 0.9 - index * 0.04,
      snippet: `Reviewed evidence match ${index + 1}`,
    }));

    render(<ReportSearchResults results={results} totalResults={12} />);

    expect(screen.getByText("Showing 6 of 12 results")).toBeInTheDocument();
    expect(screen.getAllByRole("listitem")).toHaveLength(6);
    expect(
      screen.getByRole("button", { name: /Show 2 more matches/i }),
    ).toBeInTheDocument();
    expect(screen.getByText("US6")).toBeInTheDocument();
    expect(screen.queryByText("US7")).not.toBeInTheDocument();

    fireEvent.click(
      screen.getByRole("button", { name: /Show 2 more matches/i }),
    );

    expect(screen.getByText("Showing 8 of 12 results")).toBeInTheDocument();
    expect(screen.getAllByRole("listitem")).toHaveLength(8);
    expect(screen.getByText("US7")).toBeInTheDocument();
    expect(screen.getByText("US8")).toBeInTheDocument();
    expect(
      screen.getByText(/Showing all 8 loaded matches/i),
    ).toBeInTheDocument();
  });
});
