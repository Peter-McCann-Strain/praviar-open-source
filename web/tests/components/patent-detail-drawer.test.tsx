import { describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import type { PatentAnalysis, PatentHit } from "@praviar/shared-types";
import { createMotionMock } from "../helpers/mock-motion";

vi.mock("motion/react", () => createMotionMock());

import { PatentDetailDrawer } from "@/components/report/patent-detail-drawer";

const longClaimsText = `1. A process for producing succinic acid using a recombinant microorganism under aerobic fermentation conditions.\n${"Claim detail. ".repeat(80)}`;

function makePatent(overrides: Partial<PatentHit> = {}): PatentHit {
  return {
    patent_id: "US0000000001A1",
    title: "Fermentation process for succinic acid",
    abstract: "An improved fermentation process for producing succinic acid.",
    claims_text: longClaimsText,
    sources: [],
    confidence_score: 0.82,
    filing_date: "2018-01-10",
    priority_date: "2017-01-10",
    expiry_date: "2038-01-15",
    assignees: ["Fictional Meridian Therapeutics"],
    inventors: ["Jane Doe", "John Doe"],
    cpc_codes: ["C12P 7/46", "C12N 1/21"],
    legal_status: "active",
    match_type: "similarity",
    tanimoto_score: 0.73,
    is_granted: true,
    legal_events: [
      {
        event_date: "2020-04-01",
        event_code: "GRNT",
        event_description: "Patent granted",
        country: "US",
      },
    ],
    family: {
      family_id: "fam-1",
      members: [{ country: "US", doc_number: "11234567", kind: "B2" }],
    },
    patent_term_info: {
      patent_id: "US0000000001A1",
      effective_filing_date: "2018-01-10",
      grant_date: "2020-04-01",
      base_expiry: "2038-01-10",
      pta_days: 5,
      pte_days: 0,
      terminal_disclaimer: false,
      td_linked_patent: "",
      maintenance_fee_status: "paid",
      adjusted_expiry: "2038-01-15",
      calculation_confidence: 0.9,
      calculation_notes: [],
    },
    ...overrides,
  };
}

function makeAnalysis(): PatentAnalysis {
  return {
    patent_id: "US0000000001A1",
    title: "Fermentation process for succinic acid",
    assignee: "Fictional Meridian Therapeutics",
    expiry_date: "2038-01-15",
    claims_analyzed: [],
    risk_level: "high",
    risk_summary: "High risk",
    design_around_suggestions: [],
    orange_book_info: null,
    model_used: "claude-3-opus",
    thinking_text: "",
    input_tokens: 1000,
    output_tokens: 200,
  };
}

describe("PatentDetailDrawer", () => {
  it("renders the patent header, links, and key sections when open", () => {
    render(
      <PatentDetailDrawer
        patent={makePatent()}
        analysis={makeAnalysis()}
        open
        onClose={vi.fn()}
      />,
    );

    expect(screen.getByText("US0000000001A1")).toBeInTheDocument();
    expect(
      screen.getByText("Fermentation process for succinic acid"),
    ).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Google Patents" })).toHaveClass(
      "min-h-11",
    );
    expect(screen.getByRole("link", { name: "Espacenet" })).toHaveClass(
      "min-h-11",
    );
    expect(screen.getByText("Legal Status & Term")).toBeInTheDocument();
    expect(screen.getByText("Claims Text")).toBeInTheDocument();
    expect(screen.getByText("Patent Family")).toBeInTheDocument();
    expect(screen.getByText("CPC Classification")).toBeInTheDocument();
    expect(screen.getByText("Legal Events")).toBeInTheDocument();
  });

  it("uses modal dialog semantics, manages focus, and closes on Escape", () => {
    const onClose = vi.fn();
    const trigger = document.createElement("button");
    trigger.textContent = "Open patent drawer";
    document.body.appendChild(trigger);
    trigger.focus();

    const { unmount } = render(
      <PatentDetailDrawer
        patent={makePatent()}
        analysis={makeAnalysis()}
        open
        onClose={onClose}
      />,
    );

    const dialog = screen.getByRole("dialog", {
      name: "Patent details for US0000000001A1",
    });
    expect(dialog).toHaveAttribute("aria-modal", "true");
    expect(dialog).toHaveFocus();

    fireEvent.keyDown(dialog, { key: "Escape" });
    expect(onClose).toHaveBeenCalledTimes(1);

    unmount();
    expect(trigger).toHaveFocus();
    trigger.remove();
  });

  it("expands claims text and closes from the close button", () => {
    const onClose = vi.fn();

    render(
      <PatentDetailDrawer
        patent={makePatent()}
        analysis={makeAnalysis()}
        open
        onClose={onClose}
      />,
    );

    fireEvent.click(screen.getByText("Claims Text"));
    expect(screen.getByText(/Show all/)).toBeInTheDocument();
    fireEvent.click(screen.getByText(/Show all/));
    expect(screen.getByText("Show less")).toBeInTheDocument();

    const closeButton = screen.getByRole("button", {
      name: "Close patent details",
    });
    expect(closeButton).toHaveClass("h-11", "w-11");
    fireEvent.click(closeButton);
    expect(onClose).toHaveBeenCalled();
  });

  it("truncates long legal event lists", () => {
    const events = Array.from({ length: 16 }, (_, index) => ({
      event_date: `202${index}-01-01`,
      event_code: index === 0 ? "GRNT" : `E${index}`,
      event_description: `Event ${index + 1}`,
      country: "US",
    }));

    render(
      <PatentDetailDrawer
        patent={makePatent({ legal_events: events })}
        analysis={makeAnalysis()}
        open
        onClose={vi.fn()}
      />,
    );

    fireEvent.click(screen.getByText("Legal Events"));
    expect(screen.getByText("+ 1 more events")).toBeInTheDocument();
  });

  it("surfaces term confidence, maintenance due dates, and calculation caveats", () => {
    const linkedPatent =
      "US-terminal-disclaimer-linked-family-with-no-natural-breakpoints-2038123456789";
    const calculationNote =
      "Maintenance fee ledger is incomplete for EP/US family member " +
      "status-without-natural-breakpoints-".repeat(8);

    render(
      <PatentDetailDrawer
        patent={makePatent({
          patent_term_info: {
            patent_id: "US0000000001A1",
            effective_filing_date: "2018-01-10",
            grant_date: "2020-04-01",
            base_expiry: "2038-01-10",
            pta_days: 5,
            pte_days: 12,
            terminal_disclaimer: true,
            td_linked_patent: linkedPatent,
            td_linked_expiry: "2036-08-01",
            maintenance_fee_status: "grace_period",
            maintenance_fee_next_due: "2026-09-15",
            adjusted_expiry: "2036-08-01",
            calculation_confidence: 0.62,
            calculation_notes: [calculationNote],
          },
        })}
        analysis={makeAnalysis()}
        open
        onClose={vi.fn()}
      />,
    );

    expect(screen.getByText("Maintenance fees")).toBeInTheDocument();
    expect(screen.getByText("grace period")).toBeInTheDocument();
    expect(screen.getByText("Next fee due")).toBeInTheDocument();
    expect(screen.getByText("2026-09-15")).toBeInTheDocument();
    expect(screen.getByText("Term confidence")).toBeInTheDocument();
    expect(screen.getByText("62%")).toBeInTheDocument();
    expect(screen.getByText("Calculation caveats")).toBeInTheDocument();
    expect(screen.getByText(calculationNote)).toHaveClass(
      "break-words",
      "[overflow-wrap:anywhere]",
    );
    expect(screen.getByText(new RegExp(linkedPatent))).toHaveClass(
      "break-words",
      "[overflow-wrap:anywhere]",
    );
  });
});
