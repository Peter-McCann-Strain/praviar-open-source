import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import {
  PatentDataTable,
  type PatentRow,
} from "@/components/report/patent-data-table";

const longTitle =
  "Therapeutic composition for extended release succinic acid derivatives in oncology";
const longAssignee = "Praviar Advanced Therapeutics International Holdings";

const patents: PatentRow[] = [
  {
    patentNumber: "US10123456B2",
    title: longTitle,
    assignee: longAssignee,
    filingDate: "2024-01-15",
    riskLevel: "medium",
    jurisdiction: "US",
    relevanceScore: 78,
  },
];

describe("PatentDataTable", () => {
  it("makes truncated title and assignee cells keyboard discoverable", () => {
    render(<PatentDataTable patents={patents} />);

    const titleCell = screen.getByLabelText(longTitle);
    const assigneeCell = screen.getByLabelText(longAssignee);
    const exportButton = screen.getByRole("button", { name: "Export all" });
    const patentButton = screen.getByRole("button", { name: "US10123456B2" });
    const selectAll = screen.getByRole("checkbox", {
      name: "Select all rows",
    });
    const selectPatent = screen.getByRole("checkbox", {
      name: "Select patent US10123456B2",
    });

    expect(titleCell).toHaveAttribute("tabIndex", "0");
    expect(titleCell).toHaveAttribute("title", longTitle);
    expect(titleCell.className).toContain(
      "focus-visible:ring-brand-primary/70",
    );

    expect(assigneeCell).toHaveAttribute("tabIndex", "0");
    expect(assigneeCell).toHaveAttribute("title", longAssignee);
    expect(exportButton).toHaveClass("min-h-11");
    expect(patentButton).toHaveClass("min-h-11");
    expect(selectAll.closest("label")).toHaveClass("min-h-11", "min-w-11");
    expect(selectPatent.closest("label")).toHaveClass("min-h-11", "min-w-11");
  });

  it("does not manufacture zero relevance when the report omits a score", () => {
    render(
      <PatentDataTable patents={[{ ...patents[0], relevanceScore: null }]} />,
    );

    expect(screen.getByText("Not reported")).toBeInTheDocument();
    expect(screen.queryByText("0%")).not.toBeInTheDocument();
    expect(
      screen.getByRole("columnheader", { name: "Reported relevance" }),
    ).toBeInTheDocument();
  });
});
